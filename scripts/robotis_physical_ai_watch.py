#!/usr/bin/env python3
"""ROBOTIS / physical-AI high-signal news watcher.

Watches ROBOTIS, DYNAMIXEL, AI Sapiens K1, CJ Logistics deployments,
Pollen Robotics/Microduck actuator adoption, Uzbekistan capacity expansion,
and institutional/major-shareholder events. Google News RSS is used as a
broad discovery layer. The first scheduled run seeds a baseline; later runs
only emit new, high-signal items. Set FORCE_SUMMARY=1 for a manual current
summary.
"""
from __future__ import annotations

import datetime as dt
import email.utils
import hashlib
import html
import json
import os
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "robotis_physical_ai_watch_state.json"
OUT_DIR = ROOT / "out"
PENDING_PATH = OUT_DIR / "robotis_physical_ai_watch_pending_state.json"
ALERT_PATH = OUT_DIR / "robotis_physical_ai_watch_telegram.txt"
STATUS_PATH = OUT_DIR / "robotis_physical_ai_watch_status.md"

KST = ZoneInfo("Asia/Seoul")
NOW = dt.datetime.now(dt.timezone.utc)
FORCE = os.getenv("FORCE_SUMMARY", "").strip().lower() in {"1", "true", "yes", "on"}

QUERIES = [
    '로보티즈 (휴머노이드 OR "AI 사피엔스" OR K1 OR "AI Worker" OR 액추에이터 OR 다이나믹셀 OR 우즈베키스탄 OR CJ대한통운)',
    'ROBOTIS (humanoid OR "AI Sapiens" OR K1 OR DYNAMIXEL OR actuator OR Uzbekistan OR "CJ Logistics")',
    '(Microduck OR "Reachy Mini") (ROBOTIS OR Dynamixel OR actuator OR "Pollen Robotics")',
    '("Pollen Robotics" OR "Hugging Face") (Dynamixel OR ROBOTIS OR Microduck OR actuator)',
    '("Goldman Sachs" OR 골드만삭스) (ROBOTIS OR 로보티즈 OR Microduck OR actuator OR 액추에이터)',
    '로보티즈 (블록딜 OR 외국계 OR 기관 OR 지분 OR 수주잔고 OR 생산능력 OR 출하량 OR 완판 OR 공급계약 OR 양산)',
    '(DYNAMIXEL-Q OR "DYNAMIXEL Q" OR XL330) (humanoid OR robot OR Microduck OR 로봇)',
]

TRUSTED = {
    "Reuters", "Bloomberg", "The Wall Street Journal", "Financial Times",
    "파이낸셜뉴스", "연합뉴스", "한국경제", "매일경제", "전자신문",
    "ZDNet Korea", "시사저널e", "뉴스핌", "로봇신문", "ROBOTIS",
    "CJ대한통운", "Pollen Robotics", "Hugging Face",
}

HIGH = [
    r"공급계약|수주|주문|수주잔고|backlog|order|contract|supply",
    r"양산|생산능력|캐파|capa|capacity|factory|plant|공장|출하|shipment|production",
    r"고객|customer|채택|adopt|qualification|인증|검증|deployment|투입|배치",
    r"완판|sold out|예약|preorder|사전주문|판매|launch|출시",
    r"액추에이터|actuator|DYNAMIXEL|다이나믹셀|XL330|DYNAMIXEL-Q",
    r"Microduck|Reachy Mini|Pollen Robotics|Hugging Face",
    r"AI 사피엔스|AI Sapiens|\bK1\b|AI Worker|세미 휴머노이드|humanoid",
    r"우즈베키스탄|Uzbekistan|CJ대한통운|CJ Logistics|올리브영|Olive Young",
    r"Goldman Sachs|골드만삭스|목표주가|price target|리포트|report",
    r"블록딜|block deal|외국계|기관|institution|지분|stake|5%",
]

NUMERIC = re.compile(
    r"(?:\b\d+(?:\.\d+)?\s*(?:만|억|조|백만|million|billion|%|대|개|달러|원|USD|KRW)\b|"
    r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b)", re.I
)
NOISE = re.compile(
    r"오늘의 종목|급등주|상한가 종목|주가 전망|테마주|관련주 정리|단순 추천|"
    r"stock to buy|top stocks|technical analysis", re.I
)


def fetch(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 khs-watch/1.0",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def norm(v: str | None) -> str:
    v = html.unescape(v or "")
    v = re.sub(r"<[^>]+>", " ", v)
    return re.sub(r"\s+", " ", v).strip()


def parse_date(v: str | None) -> dt.datetime | None:
    if not v:
        return None
    try:
        x = email.utils.parsedate_to_datetime(v)
        if x.tzinfo is None:
            x = x.replace(tzinfo=dt.timezone.utc)
        return x.astimezone(dt.timezone.utc)
    except Exception:
        return None


def query_news(q: str) -> list[dict]:
    p = urllib.parse.urlencode({"q": q, "hl": "ko", "gl": "KR", "ceid": "KR:ko"})
    root = ET.fromstring(fetch(f"https://news.google.com/rss/search?{p}"))
    out = []
    for it in root.findall("./channel/item")[:30]:
        title = norm(it.findtext("title"))
        link = norm(it.findtext("link"))
        desc = norm(it.findtext("description"))
        pub = parse_date(it.findtext("pubDate"))
        src_node = it.find("source")
        src = norm(src_node.text if src_node is not None else "")
        if title and link:
            out.append({
                "title": title,
                "link": link,
                "description": desc,
                "published": pub.isoformat() if pub else None,
                "source": src,
            })
    return out


def key(item: dict) -> str:
    base = f"{item['title'].lower()}|{item.get('source','').lower()}"
    return hashlib.sha256(base.encode()).hexdigest()


def score(item: dict) -> int:
    text = f"{item['title']} {item.get('description','')} {item.get('source','')}"
    if NOISE.search(text):
        return -20
    s = 0
    if re.search(r"로보티즈|ROBOTIS|DYNAMIXEL|다이나믹셀", text, re.I):
        s += 5
    elif re.search(r"Microduck|Reachy Mini|Pollen Robotics", text, re.I):
        s += 3
    else:
        return -10
    for pat in HIGH:
        if re.search(pat, text, re.I):
            s += 2
    if NUMERIC.search(text):
        s += 3
    if item.get("source") in TRUSTED:
        s += 2
    if re.search(r"공급계약|수주|customer|고객|양산|production|shipment|출하|완판|sold out", text, re.I):
        s += 3
    if re.search(r"생산능력|capa|capacity|우즈베키스탄|Uzbekistan", text, re.I):
        s += 3
    return s


def category(text: str) -> str:
    if re.search(r"블록딜|block deal|외국계|institution|지분|stake", text, re.I):
        return "수급·지분"
    if re.search(r"Goldman Sachs|골드만삭스|목표주가|price target|리포트", text, re.I):
        return "리서치·재평가"
    if re.search(r"우즈베키스탄|Uzbekistan|생산능력|capa|capacity|공장|factory|plant", text, re.I):
        return "생산능력·원가"
    if re.search(r"CJ대한통운|CJ Logistics|올리브영|Olive Young|투입|배치|deployment", text, re.I):
        return "현장 배치·고객 검증"
    if re.search(r"공급계약|수주|order|contract|customer|고객|납품|supply", text, re.I):
        return "수주·고객"
    if re.search(r"Microduck|Reachy Mini|Pollen Robotics|XL330", text, re.I):
        return "대당 액추에이터 탑재가치"
    if re.search(r"AI 사피엔스|AI Sapiens|\bK1\b|완판|sold out|판매|launch", text, re.I):
        return "완제품·플랫폼"
    return "액추에이터·피지컬AI"


def meaning(cat: str) -> str:
    return {
        "수급·지분": "본업 매출보다 외국인·기관 수급과 오버행을 바꾸는 신호입니다. 기관 실명·보호예수·추가 지분변동을 확인합니다.",
        "리서치·재평가": "로봇 출하량뿐 아니라 로봇 1대당 액추에이터 수·탑재금액이 늘어나는 이중 물량 레버리지를 숫자로 확인하는 신호입니다.",
        "생산능력·원가": "현재 수요보다 생산능력이 병목인지를 확인합니다. 실제 가동률·수율·외부 OEM 주문이 매출과 총자산이익률을 좌우합니다.",
        "현장 배치·고객 검증": "연구용 시연에서 실제 물류·산업 작업으로 넘어가는 신호입니다. 2대 실증이 수십·수백대로 확대되는지가 핵심입니다.",
        "수주·고객": "테마가 실제 고객·수주·반복발주로 바뀌는 가장 강한 매출 확인 신호입니다.",
        "대당 액추에이터 탑재가치": "로봇 고도화로 관절 수가 늘면 완제품 출하 증가와 별개로 로봇 1대당 ROBOTIS 부품 매출 기회가 커집니다.",
        "완제품·플랫폼": "K1 자체 매출보다 연구자가 DYNAMIXEL-Q와 제어환경에 락인돼 향후 외부 OEM 액추에이터 수요로 이어지는지가 중요합니다.",
        "액추에이터·피지컬AI": "DYNAMIXEL이 연구용 부품에서 휴머노이드 양산 부품으로 전환되는지를 확인하는 신호입니다.",
    }[cat]


def risk(cat: str) -> str:
    if cat == "생산능력·원가":
        return "증설보다 고객 채택이 늦으면 감가상각·운전자본 부담이 먼저 커질 수 있습니다."
    if cat == "현장 배치·고객 검증":
        return "작업 성공률·가동률·안전 검증이 낮으면 고객 확대가 지연될 수 있습니다."
    if cat == "수급·지분":
        return "클럽딜·외국계 인수만으로 장기 보유를 확정할 수 없으며 보호예수 미확인이 핵심 역풍입니다."
    if cat == "리서치·재평가":
        return "증권사 탑재가치는 실제 OEM 납품단가가 아니며 액추에이터 평균판매단가 상승과 혼동하면 안 됩니다."
    if cat == "대당 액추에이터 탑재가치":
        return "대량양산 과정에서 저가 대체품이나 자체 액추에이터로 전환되면 탑재가치가 낮아질 수 있습니다."
    return "실제 고객명·납품량·반복주문이 확인되지 않으면 기대감에 그칠 수 있습니다."


def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"seen": [], "seeded": False}


def clean_title(title: str, source: str) -> str:
    """Remove the Google News source suffix because source is shown separately."""
    if source:
        suffix = f" - {source}"
        if title.endswith(suffix):
            return title[:-len(suffix)].strip()
    return title.strip()


def esc_text(value: str) -> str:
    return html.escape(value or "", quote=False)


def esc_attr(value: str) -> str:
    return html.escape(value or "", quote=True)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()
    seen = set(state.get("seen", []))
    all_items: dict[str, dict] = {}
    errors = []
    ok_queries = 0

    for q in QUERIES:
        try:
            items = query_news(q)
            ok_queries += 1
            for x in items:
                k = key(x)
                x["key"] = k
                x["score"] = score(x)
                prev = all_items.get(k)
                if prev is None or x["score"] > prev["score"]:
                    all_items[k] = x
        except Exception as e:
            errors.append(f"{q}: {type(e).__name__}: {e}")

    if ok_queries == 0:
        raise SystemExit("All Google News RSS queries failed")

    cutoff = NOW - dt.timedelta(days=4)
    recent = []
    for x in all_items.values():
        pub = None
        if x.get("published"):
            try:
                pub = dt.datetime.fromisoformat(x["published"])
            except Exception:
                pass
        if pub and pub < cutoff:
            continue
        if x["score"] >= 10:
            recent.append(x)
    recent.sort(key=lambda x: (x["score"], x.get("published") or ""), reverse=True)

    first = not bool(state.get("seeded"))
    if FORCE:
        selected = recent[:6]
    elif first:
        selected = []
    else:
        selected = [x for x in recent if x["key"] not in seen][:6]

    for x in recent:
        seen.add(x["key"])
    seen_list = list(seen)[-2500:]
    pending = {
        "seeded": True,
        "updated_at": NOW.isoformat(),
        "seen": seen_list,
        "last_selected": [x["key"] for x in selected],
    }
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: list[str] = []
    if selected:
        lines.extend([
            "🚨 <b>로보티즈·피지컬AI 구조 변화 감지</b>",
            f"<b>신규 고신호 {len(selected)}건</b>",
            "━━━━━━━━━━━━━━━━━━",
            "",
        ])
        for i, x in enumerate(selected, 1):
            text = f"{x['title']} {x.get('description','')}"
            cat = category(text)
            when = ""
            if x.get("published"):
                try:
                    when = dt.datetime.fromisoformat(x["published"]).astimezone(KST).strftime("%m/%d %H:%M")
                except Exception:
                    pass

            source = x.get("source") or "미상"
            title = clean_title(x["title"], source)
            source_time = esc_text(source)
            if when:
                source_time += f" · {esc_text(when)} KST"

            lines.extend([
                f"<b>{i}. {esc_text(title)}</b>",
                f"<b>분류</b>  {esc_text(cat)}",
                f"<b>출처</b>  {source_time}",
                "",
                f"💡 <b>핵심</b>  {esc_text(meaning(cat))}",
                f"⚠️ <b>체크</b>  {esc_text(risk(cat))}",
                f"🔗 <a href=\"{esc_attr(x['link'])}\"><b>원문</b></a>",
                "",
                "──────────────────",
                "",
            ])

        lines.extend([
            "<b>판정 기준</b>",
            "신규 수주·고객 실명·양산/출하·생산능력·현장 배치·대당 액추에이터 탑재가치·기관 지분 변화처럼 돈 버는 능력·수급·시간표를 바꾸는 내용만 알림.",
            "단순 주가 기사·테마 반복은 제외.",
        ])

    ALERT_PATH.write_text("\n".join(lines).strip(), encoding="utf-8")

    status = [
        "# ROBOTIS Physical AI Watch",
        f"- checked_at_kst: {NOW.astimezone(KST).isoformat()}",
        f"- queries_ok: {ok_queries}/{len(QUERIES)}",
        f"- high_signal_recent: {len(recent)}",
        f"- selected_new: {len(selected)}",
        f"- first_seed: {first}",
        f"- force_summary: {FORCE}",
        "- telegram_format: HTML",
    ]
    if errors:
        status.append("- errors:")
        status.extend(f"  - {e}" for e in errors)
    STATUS_PATH.write_text("\n".join(status) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
