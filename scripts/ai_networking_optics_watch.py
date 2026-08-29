#!/usr/bin/env python3
"""AI networking / optics structural-change web watcher.

Sources are Google News RSS queries spanning official company releases and major media.
The watcher is deliberately event-driven: first run establishes a baseline and later
runs emit Telegram-ready HTML only for new, high-signal items.
"""

from __future__ import annotations

import datetime as dt
import email.utils
import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "ai_networking_optics_watch_state.json"
PENDING_PATH = ROOT / "out" / "ai_networking_optics_watch_pending_state.json"
ALERT_PATH = ROOT / "out" / "ai_networking_optics_watch_telegram.html"
STATUS_PATH = ROOT / "out" / "ai_networking_optics_watch_status.md"

KST = ZoneInfo("Asia/Seoul")
NOW = dt.datetime.now(dt.timezone.utc)

COMPANIES = {
    "NVIDIA": {
        "ticker": "NVDA",
        "aliases": ["NVIDIA", "Nvidia"],
        "query": 'NVIDIA (Spectrum-X OR NVLink OR BlueField OR networking OR Ethernet OR CPO OR "co-packaged optics" OR "silicon photonics" OR 1.6T OR 3.2T)',
    },
    "Broadcom": {
        "ticker": "AVGO",
        "aliases": ["Broadcom"],
        "query": 'Broadcom (AI Ethernet OR Tomahawk OR Thor OR networking OR optical OR CPO OR "co-packaged optics" OR 1.6T OR 3.2T)',
    },
    "Arista Networks": {
        "ticker": "ANET",
        "aliases": ["Arista Networks", "Arista"],
        "query": '"Arista Networks" (AI networking OR Ethernet OR 800G OR 1.6T OR 3.2T OR optics OR optical OR cluster OR hyperscaler)',
    },
    "Marvell": {
        "ticker": "MRVL",
        "aliases": ["Marvell"],
        "query": 'Marvell (optical DSP OR SerDes OR interconnect OR networking OR 800G OR 1.6T OR 3.2T OR CPO OR "co-packaged optics")',
    },
    "Lumentum": {
        "ticker": "LITE",
        "aliases": ["Lumentum"],
        "query": 'Lumentum (AI datacenter OR data center OR optical OR laser OR CPO OR 800G OR 1.6T OR 3.2T OR transceiver)',
    },
    "Coherent": {
        "ticker": "COHR",
        "aliases": ["Coherent"],
        "query": 'Coherent (AI datacenter OR data center OR optical OR laser OR CPO OR 800G OR 1.6T OR 3.2T OR transceiver)',
    },
    "Astera Labs": {
        "ticker": "ALAB",
        "aliases": ["Astera Labs", "Astera"],
        "query": '"Astera Labs" (PCIe OR CXL OR Scorpio OR fabric OR interconnect OR retimer OR AI rack OR networking)',
    },
    "Corning": {
        "ticker": "GLW",
        "aliases": ["Corning"],
        "query": 'Corning (AI data center OR datacenter OR optical communications OR fiber OR fibre OR cable OR connector OR CPO OR "co-packaged optics" OR photonics OR "glass substrate" OR advanced packaging)',
    },
}

TRUSTED_SOURCES = {
    "Reuters", "Bloomberg", "Financial Times", "The Wall Street Journal", "CNBC",
    "DigiTimes", "DIGITIMES", "Investing.com", "Barron's", "MarketWatch",
    "NVIDIA Blog", "NVIDIA Newsroom", "Broadcom", "Arista Networks", "Marvell",
    "Lumentum", "Coherent", "Astera Labs", "Corning",
}

HIGH_SIGNAL_PATTERNS = [
    r"\b3\.2\s*[Tt]\b", r"\b1\.6\s*[Tt]\b", r"\b800\s*[Gg]\b",
    r"co[- ]?packaged optics?", r"\bCPO\b", r"silicon photonics?",
    r"mass production", r"volume production", r"volume shipment", r"shipments?",
    r"customer qualification", r"customer certification", r"qualified", r"certified",
    r"adopt(?:ed|ion)?", r"deploy(?:ed|ment)?", r"production ramp", r"ramp(?:ing)?",
    r"backlog", r"bookings?", r"orders?", r"guidance", r"revenue",
    r"capacity expansion", r"expand(?:ing|s|ed)? capacity", r"new factory", r"new plant",
    r"shortage", r"constraint", r"bottleneck", r"supply tight", r"pricing", r"price increase",
    r"copper", r"optical", r"fiber", r"fibre", r"transceiver", r"laser",
    r"data movement", r"interconnect", r"fabric", r"retimer", r"PCIe", r"CXL",
]

ACTION_PATTERNS = [
    r"mass production", r"volume production", r"shipment", r"customer", r"qualified",
    r"certified", r"adopt", r"deploy", r"ramp", r"backlog", r"booking", r"order",
    r"guidance", r"revenue", r"capacity", r"factory", r"plant", r"shortage",
    r"constraint", r"bottleneck", r"price", r"pricing", r"launch", r"introduc",
]

NOISE_PATTERNS = [
    r"stock price", r"price target", r"analyst rating", r"upgrade[s]? .* stock",
    r"downgrade[s]? .* stock", r"options activity", r"insider sells?", r"dividend",
]


def fetch(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 khs-watch/1.0",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def parse_date(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except Exception:
        return None


def normalize_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def event_key(company: str, title: str, source: str) -> str:
    normalized = f"{company}|{title.lower()}|{source.lower()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def query_google_news(query: str) -> list[dict]:
    params = urllib.parse.urlencode({
        "q": query,
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    })
    url = f"https://news.google.com/rss/search?{params}"
    root = ET.fromstring(fetch(url))
    items: list[dict] = []
    for item in root.findall("./channel/item")[:20]:
        title = normalize_text(item.findtext("title") or "")
        link = normalize_text(item.findtext("link") or "")
        pub = parse_date(item.findtext("pubDate"))
        source_node = item.find("source")
        source = normalize_text(source_node.text if source_node is not None and source_node.text else "")
        source_url = normalize_text(source_node.attrib.get("url", "") if source_node is not None else "")
        if title and link:
            items.append({
                "title": title,
                "link": link,
                "published": pub.isoformat() if pub else None,
                "source": source,
                "source_url": source_url,
            })
    return items


def is_noise(text: str) -> bool:
    return any(re.search(pattern, text, flags=re.I) for pattern in NOISE_PATTERNS)


def signal_score(title: str, source: str) -> int:
    text = f"{title} {source}"
    if is_noise(text):
        return -10
    score = 0
    if re.search(r"\b3\.2\s*[Tt]\b", text, re.I):
        score += 6
    if re.search(r"\b1\.6\s*[Tt]\b", text, re.I):
        score += 5
    if re.search(r"co[- ]?packaged optics?|\bCPO\b|silicon photonics?", text, re.I):
        score += 5
    if re.search(r"mass production|volume production|customer qualification|customer certification|qualified|certified", text, re.I):
        score += 5
    if re.search(r"adopt|deploy|ramp|shipment", text, re.I):
        score += 4
    if re.search(r"backlog|bookings?|orders?|guidance|revenue", text, re.I):
        score += 4
    if re.search(r"shortage|constraint|bottleneck|supply tight|price increase|pricing", text, re.I):
        score += 4
    if re.search(r"capacity expansion|factory|plant|capex", text, re.I):
        score += 3
    if re.search(r"copper|optical|fiber|fibre|transceiver|laser|data movement|interconnect|fabric|retimer|PCIe|CXL", text, re.I):
        score += 2
    if re.search(r"AI|data ?center|datacenter|hyperscaler|GPU|XPU", text, re.I):
        score += 2
    if any(source.lower() == trusted.lower() for trusted in TRUSTED_SOURCES):
        score += 2
    return score


def stage_for(title: str) -> str:
    if re.search(r"revenue|guidance|backlog|bookings?|orders?", title, re.I):
        return "실적·수주 확인"
    if re.search(r"mass production|volume production|shipment|ramp", title, re.I):
        return "양산·출하"
    if re.search(r"qualified|certified|customer qualification|customer certification|adopt|deploy", title, re.I):
        return "고객 검증·채택"
    if re.search(r"shortage|constraint|bottleneck|supply tight|pricing|price increase", title, re.I):
        return "공급 병목·가격"
    if re.search(r"capacity expansion|factory|plant|capex", title, re.I):
        return "설비투자"
    return "기술·제품 준비"


def category_for(title: str, company: str) -> str:
    if re.search(r"\b3\.2\s*[Tt]\b", title, re.I):
        return "3.2T 전환"
    if re.search(r"co[- ]?packaged optics?|\bCPO\b|silicon photonics?", title, re.I):
        return "CPO·실리콘 포토닉스"
    if re.search(r"\b1\.6\s*[Tt]\b", title, re.I):
        return "1.6T 전환"
    if re.search(r"shortage|constraint|bottleneck|supply tight|pricing|price increase", title, re.I):
        return "공급 병목·가격"
    if re.search(r"backlog|bookings?|orders?|guidance|revenue", title, re.I):
        return "수주·실적"
    if company == "Corning" and re.search(r"glass substrate|advanced packaging", title, re.I):
        return "유리기판·첨단 패키징"
    if re.search(r"fiber|fibre|optical|transceiver|laser", title, re.I):
        return "광통신"
    if re.search(r"PCIe|CXL|retimer|fabric|interconnect", title, re.I):
        return "랙 내부 인터커넥트"
    return "AI 네트워킹"


def meaning_for(category: str) -> str:
    mapping = {
        "3.2T 전환": "차세대 광링크가 시제품에서 고객 검증·양산으로 넘어가면 광 DSP·레이저·모듈의 다음 매출 사이클 선행신호입니다.",
        "CPO·실리콘 포토닉스": "스위치와 광학을 더 가깝게 결합해 전력·대역폭 병목을 줄이는 구조 변화로, 기존 플러거블 광모듈의 가치 배분까지 바꿀 수 있습니다.",
        "1.6T 전환": "800G에서 1.6T로 실제 출하가 이동하는 신호로, 광 DSP·레이저·고밀도 연결부품의 현재 매출 증가와 직접 연결됩니다.",
        "공급 병목·가격": "수요가 공급능력을 앞서는지 확인하는 신호입니다. 평균판매단가에는 긍정적일 수 있지만 고객 데이터센터 가동 지연은 역풍입니다.",
        "수주·실적": "기술 기대가 실제 고객 주문·백로그·매출로 전환되는지 확인하는 가장 강한 검증 신호입니다.",
        "유리기판·첨단 패키징": "고밀도 AI 패키징의 휨·배선·열 문제를 줄이는 방향으로 채택이 늘면 Corning의 신규 AI 매출 경로가 열릴 수 있습니다.",
        "광통신": "GPU 수 증가로 랙·데이터센터 사이 데이터 이동량이 커지면서 구리 대신 광 연결 비중이 상승하는 구조적 수혜 신호입니다.",
        "랙 내부 인터커넥트": "GPU·CPU·메모리 사이 데이터 이동 지연을 줄여 비싼 가속기의 실제 이용률을 높이는 부품 수요와 연결됩니다.",
        "AI 네트워킹": "AI 성능 병목이 단일 GPU 연산력에서 데이터 이동·네트워크 전체로 넓어지는 흐름을 확인하는 신호입니다.",
    }
    return mapping[category]


def risk_for(category: str) -> str:
    mapping = {
        "3.2T 전환": "고객 인증·대량생산 수율이 지연되면 매출 시점이 뒤로 밀릴 수 있습니다.",
        "CPO·실리콘 포토닉스": "레이저 신뢰성·수율·현장 교체 난도와 플러거블 대비 경제성이 핵심 실패 경로입니다.",
        "1.6T 전환": "물량 증가보다 평균판매단가 하락이 빠르면 매출 성장 폭이 제한될 수 있습니다.",
        "공급 병목·가격": "가격 상승이 고객의 AI 랙 배치를 늦추면 단기 출하량에는 오히려 역풍이 될 수 있습니다.",
        "수주·실적": "한두 고객 집중이나 선주문이 실제 반복매출로 이어지지 않는지 확인해야 합니다.",
        "유리기판·첨단 패키징": "고객 인증·수율·기존 유기기판 대비 원가 우위가 확보되지 않으면 채택이 늦어질 수 있습니다.",
        "광통신": "전력·열·레이저 공급 및 고객 설계 전환 일정이 광부품 출하 시점을 늦출 수 있습니다.",
        "랙 내부 인터커넥트": "PCIe/CXL 세대 전환 지연이나 고객 자체 설계가 범용 부품 시장을 축소할 수 있습니다.",
        "AI 네트워킹": "GPU 설비투자가 둔화하거나 하이퍼스케일러가 네트워크 투자를 뒤로 미루면 수혜 시점이 지연될 수 있습니다.",
    }
    return mapping[category]


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"initialized": False, "seen_keys": []}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"initialized": False, "seen_keys": []}


def main() -> None:
    (ROOT / "out").mkdir(parents=True, exist_ok=True)
    (ROOT / "data").mkdir(parents=True, exist_ok=True)

    state = load_state()
    seen = set(state.get("seen_keys") or [])
    all_relevant: list[dict] = []
    errors: list[str] = []

    cutoff = NOW - dt.timedelta(days=7)
    for company, meta in COMPANIES.items():
        try:
            feed_items = query_google_news(meta["query"])
        except Exception as exc:
            errors.append(f"{company}: {type(exc).__name__}: {exc}")
            continue
        for item in feed_items:
            published = dt.datetime.fromisoformat(item["published"]) if item.get("published") else None
            if published and published < cutoff:
                continue
            title = item["title"]
            source = item.get("source") or ""
            score = signal_score(title, source)
            # Require both a technology/data-movement term and an action/commercial term,
            # except for especially strong 3.2T/CPO signals.
            has_high = any(re.search(p, title, re.I) for p in HIGH_SIGNAL_PATTERNS)
            has_action = any(re.search(p, title, re.I) for p in ACTION_PATTERNS)
            very_strong = bool(re.search(r"\b3\.2\s*[Tt]\b|co[- ]?packaged optics?|\bCPO\b", title, re.I))
            if score < 7 or not has_high or (not has_action and not very_strong):
                continue
            key = event_key(company, title, source)
            item.update({
                "company": company,
                "ticker": meta["ticker"],
                "score": score,
                "key": key,
                "stage": stage_for(title),
                "category": category_for(title, company),
            })
            all_relevant.append(item)

    # Stable order: newest first, then score.
    def sort_key(item: dict):
        published = item.get("published") or "1970-01-01T00:00:00+00:00"
        return (published, item.get("score", 0))

    all_relevant.sort(key=sort_key, reverse=True)
    # De-duplicate feed mirrors with same normalized headline.
    deduped: list[dict] = []
    titles_seen: set[str] = set()
    for item in all_relevant:
        normalized_title = re.sub(r"\W+", " ", item["title"].lower()).strip()
        if normalized_title in titles_seen:
            continue
        titles_seen.add(normalized_title)
        deduped.append(item)

    new_items = [item for item in deduped if item["key"] not in seen]
    initialized = bool(state.get("initialized"))

    updated_seen = list(dict.fromkeys([item["key"] for item in deduped] + list(seen)))[:1500]
    pending = {
        "initialized": True,
        "last_checked_kst": dt.datetime.now(KST).isoformat(timespec="seconds"),
        "seen_keys": updated_seen,
        "relevant_item_count": len(deduped),
        "source_errors": errors,
    }
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    alert_items = new_items[:8] if initialized else []
    if ALERT_PATH.exists():
        ALERT_PATH.unlink()

    if alert_items:
        lines = [
            "🚨 <b>AI 네트워킹·광통신 구조 변화 감지</b>",
            f"조회시각(KST): {html.escape(dt.datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S'))}",
            f"신규 변화: <b>{len(alert_items)}건</b>",
            "",
        ]
        for idx, item in enumerate(alert_items, 1):
            pub = ""
            if item.get("published"):
                try:
                    pub_dt = dt.datetime.fromisoformat(item["published"]).astimezone(KST)
                    pub = pub_dt.strftime("%Y-%m-%d %H:%M KST")
                except Exception:
                    pub = item["published"]
            category = item["category"]
            lines.extend([
                f"<b>{idx}) {html.escape(item['company'])} ({html.escape(item['ticker'])}) — {html.escape(category)}</b>",
                f"• 단계: {html.escape(item['stage'])}",
                f"• 원문 제목: {html.escape(item['title'])}",
                f"• 출처·시각: {html.escape(item.get('source') or '미표기')} / {html.escape(pub or '시각 미표기')}",
                f"• 투자 의미: {html.escape(meaning_for(category))}",
                f"• 역풍 확인: {html.escape(risk_for(category))}",
                f"• <a href=\"{html.escape(item['link'], quote=True)}\">원문 링크</a>",
                "",
            ])
        lines.extend([
            "<b>감시 기준</b>",
            "1.6T 대량출하·고객 채택 / 3.2T 고객 인증·양산 / NVIDIA CPO 실제 배치 / 광부품·DSP·레이저·리타이머 병목·가격 / 하이퍼스케일러 네트워크 수주·백로그 / Corning 광통신·유리기판 신규 AI 매출 경로",
        ])
        ALERT_PATH.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

    status_lines = [
        "# AI 네트워킹·광통신 감시 상태",
        "",
        f"- 조회시각(KST): {dt.datetime.now(KST).isoformat(timespec='seconds')}",
        f"- 기준선 초기화 여부: {'예' if initialized else '아니오 — 이번 실행은 기준선만 저장'}",
        f"- 관련 신규 후보: {len(new_items)}건",
        f"- Telegram 발송 후보: {len(alert_items)}건",
        f"- 현재 관련 기사 기준선: {len(deduped)}건",
        f"- 소스 오류: {len(errors)}건",
    ]
    if errors:
        status_lines.extend(["", "## 소스 오류"] + [f"- {e}" for e in errors])
    STATUS_PATH.write_text("\n".join(status_lines).strip() + "\n", encoding="utf-8")

    print(f"initialized_before={initialized}")
    print(f"relevant={len(deduped)} new={len(new_items)} alert={len(alert_items)} errors={len(errors)}")


if __name__ == "__main__":
    main()
