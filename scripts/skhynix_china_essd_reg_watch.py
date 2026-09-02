#!/usr/bin/env python3
"""SK hynix China eSSD / Intel NAND merger-remedy web watcher.

Purpose
- Track whether China's SAMR five-year behavioral remedies tied to SK hynix's
  2021 acquisition of Intel's NAND/SSD business are applied to be lifted,
  actually lifted, extended, rejected, or otherwise changed.
- Track the related Dalian NAND capacity ramp and China eSSD pricing/profitability
  signals only when they materially change the investment thesis.

The watcher is event-driven. It sends one setup/baseline message on the first
successful run, then remains silent unless a new high-signal item appears.
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
STATE_PATH = ROOT / "data" / "skhynix_china_essd_reg_watch_state.json"
PENDING_PATH = ROOT / "out" / "skhynix_china_essd_reg_watch_pending_state.json"
ALERT_PATH = ROOT / "out" / "skhynix_china_essd_reg_watch_telegram.html"
STATUS_PATH = ROOT / "out" / "skhynix_china_essd_reg_watch_status.md"

KST = ZoneInfo("Asia/Seoul")
NOW_UTC = dt.datetime.now(dt.timezone.utc)
NOW_KST = NOW_UTC.astimezone(KST)

OFFICIAL_DECISION_URL = (
    "https://www.samr.gov.cn/fldes/tzgg/ftj/art/2023/"
    "art_f03608bf1b8042b78705f412e3948588.html"
)
TREND_FORCE_BASELINE_URL = (
    "https://www.trendforce.com/news/2026/09/02/"
    "news-sk-hynixs-china-essd-business-hits-turning-point-as-intel-nand-deal-restrictions-near-expiry-by-end-2026/"
)

QUERIES = [
    # Korean
    'SK하이닉스 중국 eSSD 가격 규제 해제 인텔 NAND SAMR',
    'SK하이닉스 인텔 낸드 5년 조건 해제 중국 기업용 SSD',
    'SK하이닉스 다롄 2공장 NAND 2027 eSSD',
    # English
    'SK hynix China eSSD price cap SAMR Intel NAND restrictions removal',
    'SK hynix Intel NAND five-year remedies China enterprise SSD',
    'SK hynix Dalian Fab 2 NAND 2027 eSSD',
    # Chinese / official-site focused
    'SK海力士 英特尔 NAND 企业级固态硬盘 限制性条件 解除',
    'SK海力士 英特尔 企业级固态硬盘 市场监管总局 解除 条件',
    'site:samr.gov.cn SK海力士 英特尔 企业级固态硬盘 解除 限制性条件',
]

TRUSTED_SOURCES = {
    "Reuters",
    "Bloomberg",
    "Yonhap News Agency",
    "Yonhap News",
    "연합뉴스",
    "TrendForce",
    "DealSite",
    "딜사이트",
    "Seoul Economic Daily",
    "서울경제",
    "The Elec",
    "전자신문",
    "SK hynix Newsroom",
    "SK hynix",
    "State Administration for Market Regulation",
    "SAMR",
    "国家市场监督管理总局",
}

OFFICIAL_TERMS = [
    r"市场监管总局",
    r"SAMR",
    r"국가시장감독관리총국",
    r"SK hynix newsroom",
    r"SK하이닉스.*공시",
]

RELIEF_TERMS = [
    r"解除", r"解禁", r"取消.*限制", r"解除.*限制", r"解除.*条件",
    r"해제", r"규제.*종료", r"조건.*해제", r"제한.*해제", r"면제.*신청",
    r"lift(?:ed|ing)?", r"remove(?:d|al)?", r"relief", r"terminate(?:d|ion)?",
]

APPLICATION_TERMS = [
    r"申请.*解除", r"提出.*解除", r"申请.*豁免",
    r"해제.*신청", r"면제.*신청", r"신청.*해제",
    r"apply.*lift", r"application.*lift", r"seek.*removal", r"petition.*relief",
]

NEGATIVE_TERMS = [
    r"延长", r"继续履行", r"不予解除", r"拒绝", r"维持.*限制",
    r"연장", r"계속.*이행", r"해제.*거부", r"규제.*유지", r"조건.*유지",
    r"extend(?:ed|s|ing)?", r"remain(?:s|ed)? in force", r"reject(?:ed|ion)?",
    r"deny|denied|continue.*restriction",
]

PRICE_TERMS = [
    r"price cap", r"pricing restriction", r"price restriction", r"24[- ]month average",
    r"가격.*상한", r"가격.*제한", r"24개월.*평균", r"가격.*통제",
    r"价格.*限制", r"价格上限", r"24个月.*平均", r"不得高于",
]

ESSD_TERMS = [
    r"eSSD", r"enterprise SSD", r"기업용 SSD", r"企业级固态硬盘",
    r"PCIe.*SSD", r"SATA.*SSD",
]

DALIAN_TERMS = [
    r"Dalian", r"다롄", r"大连", r"Fab 2", r"2공장", r"二厂",
    r"50%.*capacity", r"capacity.*50%", r"5만장", r"50k.*wpm",
    r"mass production", r"양산", r"量产", r"ramp",
]

MARKET_TERMS = [
    r"margin", r"profitability", r"영업이익률", r"수익성", r"利润率", r"盈利",
    r"ASP", r"average selling price", r"평균판매단가", r"价格",
    r"market share", r"점유율", r"市占率", r"份额",
]

NOISE_TERMS = [
    r"price target", r"목표주가", r"stock price", r"주가", r"technical analysis",
    r"options activity", r"ETF", r"short interest",
]


def fetch(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 khs-watch/1.0 (+https://github.com/qedgwangju-dot/khs-watch)",
            "Accept": "application/rss+xml, application/xml, text/xml, text/html, */*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def normalize(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


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


def event_key(title: str, source: str, link: str) -> str:
    raw = f"{normalize(title).lower()}|{normalize(source).lower()}|{normalize(link)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def query_google_news(query: str) -> list[dict]:
    params = urllib.parse.urlencode({
        "q": query,
        "hl": "ko",
        "gl": "KR",
        "ceid": "KR:ko",
    })
    url = f"https://news.google.com/rss/search?{params}"
    root = ET.fromstring(fetch(url))
    rows: list[dict] = []
    for item in root.findall("./channel/item")[:30]:
        title = normalize(item.findtext("title") or "")
        link = normalize(item.findtext("link") or "")
        pub = parse_date(item.findtext("pubDate"))
        source_node = item.find("source")
        source = normalize(source_node.text if source_node is not None and source_node.text else "")
        source_url = normalize(source_node.attrib.get("url", "") if source_node is not None else "")
        if title and link:
            rows.append({
                "title": title,
                "link": link,
                "published": pub.isoformat() if pub else None,
                "source": source,
                "source_url": source_url,
                "query": query,
            })
    return rows


def any_pat(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text, re.I) for p in patterns)


def source_is_trusted(source: str) -> bool:
    s = source.lower().strip()
    return any(s == trusted.lower() or trusted.lower() in s for trusted in TRUSTED_SOURCES)


def classify(row: dict) -> tuple[int, str, str]:
    text = f"{row.get('title','')} {row.get('source','')} {row.get('query','')}"
    if any_pat(NOISE_TERMS, text) and not any_pat(RELIEF_TERMS + APPLICATION_TERMS + NEGATIVE_TERMS, text):
        return (-10, "소음", "")

    essd = any_pat(ESSD_TERMS, text)
    relief = any_pat(RELIEF_TERMS, text)
    apply = any_pat(APPLICATION_TERMS, text)
    negative = any_pat(NEGATIVE_TERMS, text)
    price = any_pat(PRICE_TERMS, text)
    dalian = any_pat(DALIAN_TERMS, text)
    market = any_pat(MARKET_TERMS, text)
    official = any_pat(OFFICIAL_TERMS, text) or source_is_trusted(row.get("source", ""))

    score = 0
    category = "관련 업데이트"
    meaning = ""

    if negative and essd:
        score += 11
        category = "규제 유지·연장·거부"
        meaning = "가격·공급 제한이 예상보다 오래 지속될 수 있어 중국향 eSSD 수익성 개선 시점이 뒤로 밀릴 수 있습니다."
    elif relief and essd:
        score += 10
        category = "규제 해제"
        meaning = "중국향 PCIe·SATA eSSD 가격·물량 운용 자유도가 커져 NAND/eSSD 수익성 상방이 열릴 수 있습니다."
    elif apply and essd:
        score += 9
        category = "해제 신청"
        meaning = "5년 조건 종료 후 실제 해제 절차가 시작됐다는 신호로, 다음 핵심 확인점은 SAMR 승인 여부입니다."
    elif price and essd:
        score += 7
        category = "가격 제한·가격 재설정"
        meaning = "중국향 eSSD 가격이 시장 NAND/eSSD 가격을 얼마나 따라갈 수 있는지가 직접 바뀌는 신호입니다."
    elif dalian:
        score += 5
        category = "다롄 증설·양산"
        meaning = "다롄 NAND 생산능력 확대가 실제 장비 반입·양산으로 이어지면 2027년 물량 증가가 확인됩니다."
    elif market and essd:
        score += 4
        category = "eSSD 수익성·점유율"
        meaning = "가격규제 해제의 실적 효과를 검증할 보조지표입니다. 중국향 가격과 글로벌 eSSD 마진을 함께 봐야 합니다."

    if official:
        score += 2
    if any_pat([r"SK hynix", r"SK하이닉스", r"SK海力士", r"Solidigm", r"솔리다임"], text):
        score += 2
    if any_pat([r"Intel", r"인텔", r"英特尔", r"NAND"], text):
        score += 1

    return (score, category, meaning)


def html_link(text: str, url: str) -> str:
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(text)}</a>'


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def official_snapshot() -> dict:
    result = {"ok": False, "sha256": None, "checked_at_kst": NOW_KST.isoformat(timespec="seconds")}
    try:
        body = fetch(OFFICIAL_DECISION_URL).decode("utf-8", errors="ignore")
        text = normalize(body)
        result.update({
            "ok": True,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "contains_price_cap": bool(re.search(r"不得高于.*24个月.*平均价格", text)),
            "contains_five_year_relief": bool(re.search(r"5年后.*提出解除条件的申请", text)),
        })
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def build_setup_message() -> str:
    return (
        "<b>SK하이닉스 중국 eSSD 규제 해제 감시 시작</b>\n\n"
        "<b>현재 기준</b>\n"
        "• 2021-12-22 중국 SAMR이 Intel NAND/SSD 인수 승인 조건으로 중국 내 PCIe·SATA eSSD 가격을 "
        "동일 거래조건 기준 승인 전 24개월 평균보다 높이지 못하도록 제한했습니다.\n"
        "• 조건은 5년 뒤 자동 종료가 아니라 <b>해제 신청 가능</b>이며, SAMR 승인 전까지 계속 이행해야 합니다.\n"
        "• 따라서 핵심 시점은 <b>2026-12-22 전후의 해제 신청 → SAMR 승인/거부/연장</b>입니다.\n"
        "• 다롄 NAND 증설·2027년 양산, 중국 eSSD 가격·마진 변화도 함께 감시합니다.\n\n"
        "<b>알림 조건</b>\n"
        "① SAMR 해제 승인·거부·연장 ② SK하이닉스 해제 신청 ③ 가격제한 조건 변경 "
        "④ 다롄 2공장 장비 반입·양산 ⑤ 중국 eSSD 수익성에 직접 영향을 주는 새 사실\n\n"
        f"{html_link('SAMR 2021 원문', OFFICIAL_DECISION_URL)} · "
        f"{html_link('TrendForce 최신 정리', TREND_FORCE_BASELINE_URL)}\n"
        "중복 기사와 단순 목표주가·주가 기사에는 알림을 보내지 않습니다."
    )


def build_event_message(events: list[dict]) -> str:
    parts = ["<b>SK하이닉스 중국 eSSD 규제 감시 변화</b>"]
    for idx, event in enumerate(events[:6], 1):
        published = event.get("published")
        when = ""
        if published:
            try:
                when_dt = dt.datetime.fromisoformat(published).astimezone(KST)
                when = when_dt.strftime("%Y-%m-%d %H:%M KST")
            except Exception:
                when = ""
        parts.append(
            f"\n<b>{idx}. {html.escape(event['category'])}</b>"
            f"\n• {html.escape(event['title'])}"
            + (f"\n• 출처: {html.escape(event['source'])}" if event.get("source") else "")
            + (f" · {html.escape(when)}" if when else "")
            + f"\n• 의미: {html.escape(event['meaning'])}"
            + f"\n• {html_link('원문', event['link'])}"
        )

    parts.append(
        "\n<b>판정 기준</b>\n"
        "• 해제 신청은 확정 수익이 아니라 절차 시작입니다.\n"
        "• SAMR의 공식 해제 승인 전까지 기존 조건은 계속 유효합니다.\n"
        "• 가격 해제 효과는 중국향 PCIe·SATA eSSD에 한정해 보고, SK하이닉스 전체 NAND 이익과 동일시하지 않습니다."
    )
    return "\n".join(parts)


def main() -> None:
    state = load_state()
    initialized = bool(state.get("initialized"))
    seen = set(state.get("seen", []))

    snapshot = official_snapshot()
    old_snapshot_hash = ((state.get("official_snapshot") or {}).get("sha256"))
    official_changed = bool(
        initialized
        and snapshot.get("ok")
        and old_snapshot_hash
        and snapshot.get("sha256") != old_snapshot_hash
    )

    rows: list[dict] = []
    errors: list[str] = []
    for query in QUERIES:
        try:
            rows.extend(query_google_news(query))
        except Exception as exc:
            errors.append(f"{query}: {type(exc).__name__}: {exc}")

    # Deduplicate current results across queries.
    unique: dict[str, dict] = {}
    for row in rows:
        key = event_key(row.get("title", ""), row.get("source", ""), row.get("link", ""))
        row["key"] = key
        current = unique.get(key)
        if current is None:
            unique[key] = row

    # Only consider recent items; old items still become part of the baseline/seen set.
    high_signal: list[dict] = []
    for row in unique.values():
        score, category, meaning = classify(row)
        row.update({"score": score, "category": category, "meaning": meaning})
        if score < 8:
            continue
        pub = row.get("published")
        if pub:
            try:
                age = NOW_UTC - dt.datetime.fromisoformat(pub).astimezone(dt.timezone.utc)
                if age > dt.timedelta(days=14):
                    continue
            except Exception:
                pass
        if row["key"] not in seen:
            high_signal.append(row)

    high_signal.sort(key=lambda x: (x.get("score", 0), x.get("published") or ""), reverse=True)

    # If the official page itself changed, surface that as the highest-priority event.
    if official_changed:
        high_signal.insert(0, {
            "key": hashlib.sha256(("official-change|" + str(snapshot.get("sha256"))).encode()).hexdigest(),
            "title": "중국 SAMR의 2021년 SK하이닉스-Intel NAND 조건부 승인 원문이 변경되었습니다.",
            "source": "国家市场监督管理总局 (SAMR)",
            "link": OFFICIAL_DECISION_URL,
            "published": NOW_UTC.isoformat(),
            "score": 20,
            "category": "공식 원문 변경",
            "meaning": "규제 조건·해제 절차 문구가 바뀌었을 가능성이 있어 SAMR 원문 재확인이 필요합니다.",
        })

    # Persist every current result as seen to prevent query-overlap duplicates.
    seen.update(unique.keys())
    for event in high_signal:
        seen.add(event["key"])

    pending = {
        "initialized": True,
        "updated_at_kst": NOW_KST.isoformat(timespec="seconds"),
        "seen": list(seen)[-1200:],
        "official_snapshot": snapshot,
        "latest_high_signal": [
            {
                "title": e["title"],
                "source": e.get("source"),
                "link": e["link"],
                "published": e.get("published"),
                "category": e["category"],
                "score": e["score"],
            }
            for e in high_signal[:10]
        ],
    }

    PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if not initialized:
        ALERT_PATH.write_text(build_setup_message() + "\n", encoding="utf-8")
        alert_status = "초기 기준선 알림 생성"
    elif high_signal:
        ALERT_PATH.write_text(build_event_message(high_signal) + "\n", encoding="utf-8")
        alert_status = f"고신호 변화 {len(high_signal)}건 알림 생성"
    else:
        if ALERT_PATH.exists():
            ALERT_PATH.unlink()
        alert_status = "새 고신호 변화 없음"

    status_lines = [
        "# SK하이닉스 중국 eSSD 규제 감시 상태",
        "",
        f"- 확인시각: {NOW_KST.isoformat(timespec='seconds')}",
        f"- 상태: {alert_status}",
        f"- RSS 수집 항목: {len(unique)}건",
        f"- 신규 고신호: {len(high_signal)}건",
        f"- SAMR 원문 접근: {'성공' if snapshot.get('ok') else '실패'}",
        f"- SAMR 원문 변경: {'예' if official_changed else '아니오'}",
        f"- 수집 오류: {len(errors)}건",
    ]
    if errors:
        status_lines.extend(["", "## 오류", *[f"- {e}" for e in errors[:8]]])
    STATUS_PATH.write_text("\n".join(status_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
