from __future__ import annotations

import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "bok_asset_tokenization_state.json"
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)

SOURCES = [
    {
        "name": "한국은행 보도자료",
        "url": "https://www.bok.or.kr/portal/bbs/B0000502/list.do?menuNo=201265",
        "base": "https://www.bok.or.kr",
    },
    {
        "name": "한국은행 조사연구",
        "url": "https://www.bok.or.kr/portal/bbs/P0002353/list.do?menuNo=200433",
        "base": "https://www.bok.or.kr",
    },
    {
        "name": "금융위원회 금융정책",
        "url": "https://www.fsc.go.kr/po010101",
        "base": "https://www.fsc.go.kr",
    },
    {
        "name": "한국예탁결제원",
        "url": "https://www.ksd.or.kr/ko/",
        "base": "https://www.ksd.or.kr",
    },
]

PRIMARY = (
    "자산토큰", "자산 토큰", "국채토큰", "국채 토큰", "토큰화 국채", "국채 토큰화",
    "통합원장", "통합 원장", "프로젝트 한강", "예금토큰", "예금 토큰",
    "토큰증권", "토큰 증권", "디지털화폐", "CBDC",
)
SECONDARY = (
    "참여기관", "참여 기관", "참여은행", "참여 은행", "증권사", "예탁결제원",
    "사업자", "시스템 구축", "구축사업", "입찰", "조달", "우선협상", "수주",
    "시범사업", "실증", "실거래", "2027",
)

UA = "Mozilla/5.0 (compatible; khs-watch/1.0; +https://github.com/qedgwangju-dot/khs-watch)"

CATEGORY_ICON = {
    "시스템 구축·조달": "🛠",
    "참여기관·당사자": "🏦",
    "국채 토큰화": "🏛",
    "통합원장": "🔗",
    "프로젝트 한강·예금토큰": "💳",
    "자산 토큰화": "📄",
}


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        ctype = r.headers.get_content_charset() or "utf-8"
    return raw.decode(ctype, errors="replace")


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def relevant(text: str) -> bool:
    low = text.lower()
    return any(k.lower() in low for k in PRIMARY)


def classify(text: str) -> str:
    low = text.lower()
    if any(k.lower() in low for k in ("입찰", "조달", "우선협상", "수주", "시스템 구축", "구축사업")):
        return "시스템 구축·조달"
    if any(k.lower() in low for k in ("참여기관", "참여 기관", "참여은행", "참여 은행", "증권사", "예탁결제원", "사업자")):
        return "참여기관·당사자"
    if any(k.lower() in low for k in ("국채토큰", "국채 토큰", "토큰화 국채", "국채 토큰화")):
        return "국채 토큰화"
    if any(k.lower() in low for k in ("통합원장", "통합 원장")):
        return "통합원장"
    if any(k.lower() in low for k in ("프로젝트 한강", "예금토큰", "예금 토큰")):
        return "프로젝트 한강·예금토큰"
    return "자산 토큰화"


def extract(source: dict) -> list[dict]:
    page = fetch(source["url"])
    soup = BeautifulSoup(page, "html.parser")
    rows: dict[str, dict] = {}
    for a in soup.find_all("a", href=True):
        title = clean(a.get_text(" ", strip=True))
        if len(title) < 4:
            continue
        href = urllib.parse.urljoin(source["base"], a.get("href", ""))
        parent_text = clean(a.parent.get_text(" ", strip=True)) if a.parent else title
        combined = title if len(parent_text) > 400 else parent_text
        if not relevant(combined):
            continue
        key = hashlib.sha256((source["name"] + "|" + title + "|" + href).encode()).hexdigest()[:24]
        rows[key] = {
            "id": key,
            "source": source["name"],
            "title": title[:300],
            "context": combined[:500],
            "url": href,
            "category": classify(combined),
        }
    return list(rows.values())


def source_link(url: str, label: str = "원문") -> str:
    safe_url = html.escape(url, quote=True)
    if url.startswith(("https://", "http://")):
        return f'<a href="{safe_url}"><b>{html.escape(label)}</b></a>'
    return "원문 링크 없음"


def display_time(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M KST")


def readable_title(raw: str) -> str:
    text = clean(raw)
    extension = ""
    ext_match = re.search(r"\.(pdf|hwp|hwpx|docx?)$", text, flags=re.I)
    if ext_match:
        extension = ext_match.group(1).upper()
        text = text[:ext_match.start()].strip()

    tag = ""
    lead = re.match(r"^\d{6}\s*(?:\(([^)]+)\)|\[([^\]]+)\])?\s*", text)
    if lead:
        tag = clean(lead.group(1) or lead.group(2) or "")
        text = text[lead.end():].strip()
    else:
        bracket = re.match(r"^\[([^\]]+)\]\s*", text)
        if bracket:
            tag = clean(bracket.group(1))
            text = text[bracket.end():].strip()

    text = clean(text).strip("-–— ") or clean(raw)
    suffix = ""
    if tag:
        suffix += f" · {tag}"
    if extension:
        suffix += f" · {extension}"
    return f"{text}{suffix}"


def core_interpretation(item: dict) -> str:
    text = clean(f"{item.get('title', '')} {item.get('context', '')}").lower()
    category = item.get("category", "")

    if "분산원장" in text and ("표준요건" in text or "가이드라인" in text):
        return "토큰증권을 실제 금융시스템에 올릴 때 필요한 분산원장 기술·운영 기준을 구체화한 실무 가이드입니다."
    if "토큰증권" in text and "정책방향" in text:
        return "토큰증권을 조각투자 중심 논의에서 주식·채권·펀드와 스테이블코인 결제까지 확장하는 단계별 국가 인프라 로드맵입니다."
    if any(k in text for k in ("국채토큰", "국채 토큰", "토큰화 국채", "국채 토큰화")):
        return "CBDC·예금토큰과 국채토큰을 연결하는 실증의 일정·참여기관·결제 구조를 확인할 핵심 업데이트입니다."
    if "통합원장" in text or "통합 원장" in text:
        return "중앙은행화폐·예금토큰·자산토큰을 같은 원장에서 처리하는 통합원장 구축 방향과 관련된 업데이트입니다."
    if "프로젝트 한강" in text or "예금토큰" in text or "예금 토큰" in text:
        return "예금토큰의 결제·송금·국고금 활용과 실거래 확대 단계가 어디까지 진행됐는지 보여주는 업데이트입니다."
    if category == "시스템 구축·조달":
        return "정책·실증이 실제 시스템 구축·발주·수주 단계로 넘어가는지 확인할 실행 단계 업데이트입니다."
    if category == "참여기관·당사자":
        return "어떤 은행·증권사·인프라 기관이 실제 실증·구축에 참여하는지 확인할 당사자 업데이트입니다."
    return "자산 토큰화 제도·실증·인프라의 진행 단계가 바뀌었는지 확인할 공식 업데이트입니다."


def fsc_article_id(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    if query.get("upperNo"):
        return str(query["upperNo"][0])
    match = re.search(r"/(?:po010101|no010101|po010106)/(\d+)", parsed.path)
    return match.group(1) if match else ""


def event_key(item: dict) -> str:
    if item.get("source") == "금융위원회 금융정책":
        article_id = fsc_article_id(item.get("url", ""))
        if article_id:
            return f"FSC:{article_id}"
    return f"ITEM:{item.get('id', '')}"


def group_items(items: list[dict]) -> list[list[dict]]:
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for item in items:
        key = event_key(item)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(item)
    return [groups[key] for key in order]


def representative_item(group: list[dict]) -> dict:
    pages = [item for item in group if "/comm/getFile" not in item.get("url", "")]
    candidates = pages or group
    return max(candidates, key=lambda item: len(clean(item.get("title", ""))))


def link_label(item: dict) -> str:
    title = clean(item.get("title", "")).lower()
    url = item.get("url", "")
    if "/comm/getFile" not in url:
        return "정책본문"
    if "별첨3" in title or ("분산원장" in title and "가이드라인" in title):
        return "표준요건"
    if "별첨2" in title or "모범규준" in title:
        return "조각투자 모범규준"
    if "별첨1" in title:
        return "정책방향"
    if "보도자료" in title and title.endswith(".pdf"):
        return "보도자료 PDF"
    if "보도자료" in title and title.endswith(".hwpx"):
        return "보도자료 HWPX"
    return readable_title(item.get("title", ""))


def event_links(group: list[dict]) -> str:
    if len(group) == 1:
        return f"원문  {source_link(group[0].get('url', ''))}"
    links: list[str] = []
    seen: set[tuple[str, str]] = set()
    for item in group:
        url = item.get("url", "")
        if not url.startswith(("https://", "http://")):
            continue
        label = link_label(item)
        key = (label, url)
        if key in seen:
            continue
        seen.add(key)
        links.append(source_link(url, label))
    return "원문  " + " · ".join(links[:7]) if links else "원문 링크 없음"


def special_event_details(group: list[dict]) -> list[tuple[str, str]]:
    article_ids = {fsc_article_id(item.get("url", "")) for item in group}
    if "87650" not in article_ids:
        return []
    return [
        (
            "핵심 내용",
            "금융위가 조각투자뿐 아니라 주식·채권·펀드까지 토큰화 범위를 넓히고, 발행·유통·결제를 단계별로 제도권 인프라에 올리는 정책방향을 확정했습니다.",
        ),
        (
            "1단계 · 2027.2.4",
            "기관투자자 전용 사모MMF·사모사채, 신탁방식 비상장주식, 공모 조각투자증권 토큰화를 시작합니다.",
        ),
        (
            "한국거래소",
            "NYSE·Nasdaq 파일럿을 참고해 상장주식 토큰화 모델검증·시범사업을 병행합니다.",
        ),
        (
            "2단계",
            "1단계의 안정성·효율성과 시장수요를 점검하면서 공모증권 등 기술적으로 가능한 범위까지 확대합니다.",
        ),
        (
            "3단계",
            "스테이블코인 등을 결제수단으로 연결해 온체인 결제를 구현합니다.",
        ),
        (
            "전환 조건",
            "2·3단계 시점은 1단계 안정성·효율성, 시장의 기술혁신 속도, 스테이블코인 법제화에 따라 달라집니다.",
        ),
        (
            "유통",
            "기존 증권사·장외거래소는 인가받은 업무범위 안에서 별도 추가인가 없이 취급할 수 있고, 장외거래소 일반투자자 한도는 거래소별 연간 순매수 1억원입니다.",
        ),
        (
            "등록요건",
            "발행인 계좌관리기관은 자기자본 40억원과 계좌관리·내부통제·전산 전문인력, 전산·보안 요건을 갖추는 방향입니다.",
        ),
        (
            "다음 일정",
            "2026년 9월말 하위법규 개정안을 입법예고하고, 예탁원·증권사가 인프라를 구축해 2027년 2월 4일 1단계를 시행할 계획입니다.",
        ),
    ]


def main() -> None:
    now_dt = datetime.now(ZoneInfo("Asia/Seoul"))
    now = now_dt.isoformat(timespec="seconds")
    all_items: dict[str, dict] = {}
    errors: list[str] = []
    for src in SOURCES:
        try:
            for item in extract(src):
                all_items[item["id"]] = item
        except Exception as e:
            errors.append(f"{src['name']}: {type(e).__name__}: {e}")

    previous = {"items": {}}
    first_run = not DATA.exists()
    if DATA.exists():
        try:
            previous = json.loads(DATA.read_text(encoding="utf-8"))
        except Exception:
            previous = {"items": {}}

    old_ids = set((previous.get("items") or {}).keys())
    new_items = [v for k, v in all_items.items() if k not in old_ids]

    pending = {
        "updated_at_kst": now,
        "items": all_items,
        "errors": errors,
    }
    (OUT / "bok_asset_tokenization_pending_state.json").write_text(
        json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    if first_run:
        (OUT / "bok_asset_tokenization_rebaseline.txt").write_text(
            "Initial baseline created; no Telegram alert sent.\n", encoding="utf-8"
        )

    if (not first_run) and new_items:
        priority = sorted(
            new_items,
            key=lambda x: (
                0 if x["category"] in {"참여기관·당사자", "시스템 구축·조달", "국채 토큰화"} else 1,
                x["source"],
                x["title"],
            ),
        )
        groups = group_items(priority)
        visible = groups[:6]
        lines = [
            "🔔 <b>한국은행 자산토큰화·국채토큰화</b>",
            "<b>새 공식 업데이트</b>",
            "",
            f"<b>신규 {len(priority)}건 · {len(groups)}개 이슈</b>  ·  {html.escape(display_time(now_dt))}",
        ]
        for idx, group in enumerate(visible, 1):
            item = representative_item(group)
            icon = CATEGORY_ICON.get(item["category"], "•")
            category = html.escape(item["category"])
            title = html.escape(readable_title(item["title"]))
            interpretation = html.escape(core_interpretation(item))
            source = html.escape(item["source"])
            lines += [
                "",
                "<blockquote>",
                f"{icon} <b>{idx}. {category}</b>",
                f"<b>{title}</b>",
                f"<b>핵심 해석</b>  {interpretation}",
            ]
            details = special_event_details(group)
            if details:
                lines.append("")
                for label, value in details:
                    lines.append(f"<b>{html.escape(label)}</b>  {html.escape(value)}")
            lines += [
                "",
                f"출처  {source}",
                event_links(group),
                "</blockquote>",
            ]
        if len(groups) > len(visible):
            lines += ["", f"그 외 신규 이슈 {len(groups)-len(visible)}건"]
        if errors:
            lines += [
                "",
                "⚠️ <b>일부 공식 페이지 조회 오류</b>",
                html.escape(" | ".join(errors[:3])),
            ]
        (OUT / "bok_asset_tokenization_alert.md").write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

    status = [
        "# BOK Asset Tokenization Watch",
        f"- checked_at_kst: {now}",
        f"- official_items: {len(all_items)}",
        f"- new_items: {0 if first_run else len(new_items)}",
        f"- first_run_baseline: {str(first_run).lower()}",
        f"- source_errors: {len(errors)}",
    ]
    if errors:
        status.extend([f"  - {e}" for e in errors])
    (OUT / "bok_asset_tokenization_status.md").write_text("\n".join(status) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
