#!/usr/bin/env python3
import html
import json
import pathlib
import re
import urllib.request

from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator

ROOT = pathlib.Path(__file__).resolve().parents[1]
IN_PATH = ROOT / "out" / "texas_data_center_watch_alert.json"
OUT_PATH = ROOT / "out" / "texas_data_center_watch_telegram.md"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; KHS-Texas-DC-Alert/1.0)",
    "Accept-Language": "en-US,en;q=0.9",
}

ABBOTT_STANDARDS = (
    "전력망 비용 자부담·신규 발전 확보·물 절약형 냉각·"
    "주민 전기료 전가 금지·지역사회 영향 최소화"
)


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def ko(text):
    text = clean(text)
    if not text:
        return ""
    if re.search(r"[가-힣]", text) and not re.search(r"[A-Za-z]{5,}", text):
        return text
    try:
        out = GoogleTranslator(source="auto", target="ko").translate(text)
        return clean(out) or text
    except Exception:
        return text


def fetch_text(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        soup = BeautifulSoup(resp.read(), "html.parser")
    for node in soup(["script", "style", "noscript", "nav", "header", "footer", "form"]):
        node.decompose()
    main = soup.find("article") or soup.find("main") or soup
    return clean(main.get_text(" ", strip=True))


def parse_companies(title):
    title = clean(title)
    m = re.search(
        r"Governor Abbott Announces\s+(.+?)\s+Commit(?:s)? to Comply with His Data Center Standards",
        title,
        re.I,
    )
    if not m:
        return []
    chunk = re.sub(r"\s+[Aa]nd\s+", ", ", m.group(1))
    names = [clean(x) for x in chunk.split(",") if clean(x)]
    return names


def nightpeak_context():
    url = "https://nightpeak.energy/project/old-ocean-data-center/"
    try:
        text = fetch_text(url)
    except Exception:
        return "Nightpeak Energy: Old Ocean 데이터센터는 620MW 규모로, 620MW Bulldog 발전소와 함께 개발 중이며 회사는 2027년부터 전원 인가 가능 목표를 제시하고 있습니다."
    mw = "620MW" if re.search(r"620\s*MW", text, re.I) else "620MW"
    year = "2027년" if "2027" in text else "2027년"
    return f"Nightpeak Energy: Old Ocean 데이터센터 {mw} + Bulldog 발전소 {mw}를 함께 개발 중이며, {year}부터 전원 인가 가능 목표입니다."


def anthropic_context():
    url = "https://www.anthropic.com/news/covering-electricity-price-increases"
    try:
        text = fetch_text(url)
    except Exception:
        return "Anthropic: 이미 데이터센터 계통연결에 필요한 전력망 증설비 100% 부담과 신규 발전 확보를 약속해, 이번 Texas 수용은 기존 정책의 연장선입니다."
    has_100 = bool(re.search(r"100%", text))
    has_generation = bool(re.search(r"net-new power generation|new power generation", text, re.I))
    if has_100 and has_generation:
        return "Anthropic: 이미 데이터센터 계통연결에 필요한 전력망 증설비 100% 부담과 신규 발전 확보를 약속해, 이번 Texas 수용은 기존 정책의 연장선입니다."
    return "Anthropic: 기존에도 데이터센터 전력망 비용과 신규 발전 부담 원칙을 공개해 왔으며, 이번 Texas 수용은 그 연장선입니다."


def stack_context():
    url = "https://www.stackinfra.com/locations/americas/dallas-fort-worth/dfw02/"
    try:
        text = fetch_text(url)
    except Exception:
        return ""
    if re.search(r"300\s*MW", text, re.I) and re.search(r"500\+?\s*MW", text, re.I):
        return "STACK Infrastructure: Texas DFW02는 300MW 이상 계획, 최대 500MW+ 확장 가능 규모라 전력·계통 비용 부담이 실제 대형 프로젝트에 적용되는 사례입니다."
    return ""


def compliance_message(event):
    title = clean(event.get("title"))
    companies = parse_companies(title)
    if not companies:
        return None

    joined = "·".join(companies)
    lines = [
        f"🚨 <b>Texas 데이터센터 규제 — 신규 준수 기업 {len(companies)}곳</b>",
        "",
        f"<b>{html.escape(joined)}</b>가 Abbott의 데이터센터 기준 준수를 공식 약속했습니다.",
        "",
        f"• 핵심 기준: <b>{ABBOTT_STANDARDS}</b>",
    ]

    lowers = {x.lower() for x in companies}
    contexts = []
    if any("nightpeak" in x for x in lowers):
        contexts.append(nightpeak_context())
    if any("anthropic" in x for x in lowers):
        contexts.append(anthropic_context())
    if any("stack infrastructure" in x or x == "stack" for x in lowers):
        c = stack_context()
        if c:
            contexts.append(c)

    if contexts:
        lines.append("")
        for c in contexts:
            lines.append(f"• {html.escape(c)}")

    lines.extend([
        "",
        "<b>중요:</b> 이번 발표는 <b>ERCOT 감사 통과·계통연결 승인·전원 인가 확정이 아닙니다.</b>",
        "• 다음 확인: <b>감사 완료 → 계통연결 승인 → 발전·변전소 착공 → 전원 인가일 확정</b>",
        "",
        f'<a href="{html.escape(clean(event.get("url")), quote=True)}">텍사스 주지사실 원문</a>',
    ])
    return "\n".join(lines)


def classify(event):
    signal = f"{event.get('title','')} {event.get('detail','')}".lower()
    if re.search(r"withdraw|cancel", signal):
        return "프로젝트 철회·취소", "악화", "프로젝트 일정과 향후 설비발주가 직접 약화되는 변화입니다."
    if re.search(r"pause|hold|suspend|moratorium", signal):
        return "승인·계통연결 보류", "악화", "전원 인가와 데이터센터 가동 일정이 뒤로 밀릴 수 있습니다."
    if re.search(r"resume|reopen|restart", signal):
        return "승인·계통연결 재개", "개선", "전원 인가와 착공 일정의 불확실성이 낮아지는 변화입니다."
    if re.search(r"approve|approval", signal):
        return "승인", "개선", "실제 프로젝트 진행 단계가 앞으로 이동한 변화입니다."
    if re.search(r"audit|review", signal):
        return "감사·심사", "중립", "아직 승인 자체가 아니라 프로젝트별 검증 단계입니다."
    if re.search(r"rule|order|directive|standard|require", signal):
        return "규정·기준 변경", "중립", "사업자 비용과 프로젝트 시간표를 다시 계산해야 하는 변화입니다."
    return "공식 변화", "중립", "계통연결·전력·용수·비용부담에 영향을 줄 수 있어 후속 확인이 필요합니다."


def generic_message(event):
    kind, direction, meaning = classify(event)
    title_ko = ko(event.get("title", ""))
    detail_ko = ko(event.get("detail", ""))
    if len(detail_ko) > 320:
        detail_ko = detail_ko[:317].rstrip() + "…"
    lines = [
        "🚨 <b>Texas 데이터센터 규제·계통연결 변화</b>",
        "",
        f"• 변경: <b>{html.escape(kind)}</b> ({html.escape(direction)})",
        f"• 내용: {html.escape(title_ko)}",
    ]
    if detail_ko:
        lines.append(f"• 핵심: {html.escape(detail_ko)}")
    lines.extend([
        f"• 의미: {html.escape(meaning)}",
        "• 다음 확인: <b>감사/심사 결과 → 계통연결 승인 여부 → 전원 인가 시점</b>",
        "",
        f'<a href="{html.escape(clean(event.get("url")), quote=True)}">공식 원문</a>',
    ])
    return "\n".join(lines)


def main():
    if not IN_PATH.exists():
        raise SystemExit("no alert json")
    events = json.loads(IN_PATH.read_text(encoding="utf-8"))
    messages = []
    for event in events[:10]:
        msg = compliance_message(event) or generic_message(event)
        messages.append(msg)
    OUT_PATH.write_text("\n\n──────────\n\n".join(messages).strip() + "\n", encoding="utf-8")
    print(f"formatted_alerts={len(messages)} out={OUT_PATH}")


if __name__ == "__main__":
    main()
