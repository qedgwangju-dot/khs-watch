from __future__ import annotations

import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

try:
    from googlenewsdecoder import gnewsdecoder
except Exception:
    gnewsdecoder = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "samsung_hbm_watch_state.json"
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)
ALERT = OUT / "samsung_hbm_alert.html"
STATUS = OUT / "samsung_hbm_status.md"

UA = "Mozilla/5.0 (compatible; khs-watch/1.0; +https://github.com/qedgwangju-dot/khs-watch)"
FRESH_HOURS = 96
MONTHLY_DAY = 15

SAMSUNG_HBM4_OFFICIAL = "https://news.samsung.com/global/samsung-ships-industry-first-commercial-hbm4-with-ultimate-performance-for-ai-computing"
SAMSUNG_HBM4E_OFFICIAL = "https://news.samsung.com/global/samsung-electronics-begins-shipment-of-industry-first-hbm4e-samples"
COUNTERPOINT_HBM_SHARE = "https://counterpointresearch.com/en/insights/global-dram-and-hbm-market-share"
BERNSTEIN_EXPORT = "https://www.investing.com/news/company-news/samsung-leads-hbm4-shipments-as-korea-export-data-shows-strength--report-93CH-4871213"
LS_HBM4_MIX = "https://en.sedaily.com/finance/2026/08/31/ls-securities-cuts-sk-hynix-target-27-percent-raises"

QUERIES = [
    '"Samsung" HBM4 HBM4E NVIDIA qualification shipment mass production',
    '"Samsung Electronics" HBM market share Counterpoint',
    '"Samsung" HBM Bernstein export Chungcheong revenue',
    '"Samsung" HBM4 shipment share mix LS Securities',
    '"Samsung" HBM Broadcom AMD NVIDIA Google custom HBM',
    '"삼성전자" HBM4 HBM4E 엔비디아 공급 출하 점유율',
    '"삼성전자" HBM 충남 수출 Bernstein',
]

TRUSTED = (
    "samsung", "reuters", "bloomberg", "trendforce", "counterpoint", "investing.com",
    "sedaily", "seoul economic", "zdnet", "the elec", "thelec", "digitimes",
    "yonhap", "연합뉴스", "chosunbiz", "조선비즈",
)

LOW_VALUE = ("aol", "finance.biggo", "24/7 wall st", "247wallst", "cryptobriefing")


def fetch(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def clean(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def parse_pub(value: str) -> datetime | None:
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo("Asia/Seoul"))
    except Exception:
        return None


def rss_url(query: str, lang: str) -> str:
    q = urllib.parse.quote(query)
    if lang == "ko":
        return f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def decode_google(link: str) -> str:
    if "news.google.com" not in (link or ""):
        return link
    if gnewsdecoder is None:
        return ""
    try:
        result = gnewsdecoder(link, interval=0.2)
        if isinstance(result, dict) and result.get("status"):
            decoded = str(result.get("decoded_url") or "").strip()
            if decoded.startswith("http") and "news.google.com" not in decoded:
                return decoded
    except Exception:
        pass
    return ""


def event_id(title: str, source: str) -> str:
    return hashlib.sha256(f"{title}|{source}".encode()).hexdigest()[:24]


def source_rank(source: str) -> int:
    low = (source or "").lower()
    if "samsung" in low or "삼성전자" in low:
        return 100
    if "reuters" in low:
        return 95
    if "counterpoint" in low or "trendforce" in low:
        return 90
    if "bloomberg" in low or "digitimes" in low:
        return 85
    if "investing.com" in low or "sedaily" in low or "seoul economic" in low:
        return 80
    if "zdnet" in low or "thelec" in low or "the elec" in low or "yonhap" in low or "연합뉴스" in low:
        return 75
    return 20


def relevant(text: str) -> bool:
    low = text.lower()
    samsung = "samsung" in low or "삼성전자" in low or "삼성" in low
    hbm = "hbm" in low
    signal = any(k in low for k in (
        "shipment", "ship", "mass production", "qualification", "validation", "customer",
        "market share", "revenue", "export", "mix", "allocation", "contract", "price",
        "출하", "양산", "인증", "검증", "고객", "점유율", "매출", "수출", "비중", "계약", "가격",
    ))
    return samsung and hbm and signal


def read_events() -> list[dict]:
    rows: dict[str, dict] = {}
    for query in QUERIES:
        for lang in ("en", "ko"):
            try:
                root = ET.fromstring(fetch(rss_url(query, lang)))
            except Exception:
                continue
            for item in root.findall("./channel/item"):
                title = clean(item.findtext("title") or "")
                desc = clean(item.findtext("description") or "")
                link = clean(item.findtext("link") or "")
                source_node = item.find("source")
                source = clean(source_node.text if source_node is not None and source_node.text else "")
                pub = parse_pub(clean(item.findtext("pubDate") or ""))
                if not title or not link or not relevant(f"{title} {desc}"):
                    continue
                low_source = source.lower()
                if any(x in low_source for x in LOW_VALUE):
                    continue
                if not any(x in low_source for x in TRUSTED):
                    continue
                direct = decode_google(link)
                if not direct:
                    continue
                key = event_id(title, source)
                rows[key] = {
                    "id": key,
                    "title": title,
                    "description": desc,
                    "source": source or "출처 미표시",
                    "published_at_kst": pub.isoformat(timespec="seconds") if pub else "",
                    "direct_link": direct,
                    "rank": source_rank(source),
                }
    return sorted(rows.values(), key=lambda x: x.get("published_at_kst") or "")


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"seen_ids": [], "last_monthly_digest": ""}


def save_state(obj: dict) -> None:
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def href(url: str, label: str = "원문") -> str:
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'


def krw_large(usd: float, rate: float | None) -> str:
    if rate is None:
        return "원화 환산 확인 불가"
    eok = int(round(usd * rate / 100_000_000))
    if eok >= 10000:
        jo, rem = divmod(eok, 10000)
        return f"약 {jo:,}조{rem:,}억원" if rem else f"약 {jo:,}조원"
    return f"약 {eok:,}억원"


def fx_quote() -> tuple[float | None, str]:
    try:
        from fx_api import daily_krw
        q = daily_krw()
        return q.rate, q.basis
    except Exception as exc:
        return None, f"환율 확인 실패: {type(exc).__name__}"


def classify_event(e: dict) -> tuple[str, str]:
    text = f"{e.get('title','')} {e.get('description','')}".lower()
    if "counterpoint" in e.get("source","").lower() and "market share" in text:
        return "점유율", "삼성 HBM 점유율 변화"
    if "bernstein" in text or ("chung" in text and "export" in text) or "충남" in text:
        return "수출 대용지표", "충남·한국 수출 대용지표 변화"
    if "hbm4e" in text and any(k in text for k in ("qualification", "validation", "mass production", "인증", "검증", "양산")):
        return "HBM4E 검증·양산", "HBM4E 고객 검증·양산 변화"
    if "hbm4" in text and any(k in text for k in ("shipment", "mix", "share", "출하", "비중")):
        return "HBM4 출하", "HBM4 출하·제품혼합 변화"
    if any(k in text for k in ("nvidia", "amd", "broadcom", "google")):
        return "고객", "주요 AI 고객 연결 변화"
    return "기타", "삼성 HBM 관련 신규 변화"


def event_summary(e: dict) -> list[str]:
    category, headline = classify_event(e)
    text = clean(f"{e.get('title','')} {e.get('description','')}")
    pcts = list(dict.fromkeys(re.findall(r"[+-]?\d+(?:\.\d+)?%", text)))[:4]
    dollars = list(dict.fromkeys(re.findall(r"\$\s*\d+(?:\.\d+)?\s*(?:billion|million|B|M)\b", text, re.I)))[:2]
    nums = []
    if pcts:
        nums.append(" / ".join(pcts))
    if dollars:
        nums.append(" / ".join(dollars))
    lines = [
        f"<b>{headline}</b>",
        f"• 구분: {category}",
        f"• 출처: {html.escape(e.get('source') or '미표시')} · 공개 {html.escape(e.get('published_at_kst') or '확인 불가')}",
    ]
    if nums:
        lines.append(f"• 핵심 숫자: <b>{html.escape(' · '.join(nums))}</b>")
    lines += [
        f"• 제목: {html.escape(e.get('title') or '')}",
        href(e.get("direct_link") or ""),
    ]
    return lines


def build_monthly(now: datetime, rate: float | None, fx_basis: str) -> str:
    july_krw = krw_large(2_200_000_000, rate)
    lines = [
        "🚨 <b>삼성전자 HBM 월간 점검</b>",
        "━━━━━━━━━━━━━━━━",
        "<b>[한눈에 보기]</b>",
        "• HBM 시장점유율: <b>삼성 33%</b> · SK하이닉스 50% · Micron 18% (2026년 2분기, Counterpoint)",
        "• 삼성 내부 HBM 출하 중 HBM4 비중: <b>1Q 약 5% → 2Q 약 35%</b> (LS증권 추정)",
        f"• 충남 7월 HBM 수출 대용지표: <b>약 22억달러 · {july_krw}</b>, 4월 대비 <b>+122%</b> (Bernstein)",
        "• Bernstein 3Q26 삼성 HBM 매출 추정: <b>QoQ +80%</b>, 기존 전망 대비 <b>+30%</b>",
        "",
        "<b>[현재 양산·개발]</b>",
        "• HBM4: 삼성 공식 기준 <b>양산·상업 출하</b>, NVIDIA Vera Rubin용으로 설계",
        "• HBM4E: <b>12단 샘플 출하</b> 시작, 최대 <b>16Gbps</b>",
        "• 다음 강한 확인 신호: <b>HBM4E 고객 인증 완료 → 양산 → 계약물량</b>",
        "",
        "<b>[이번 달 판정]</b>",
        "• 삼성 HBM은 <b>점유율 회복 + HBM4 믹스 상승 + 수출 대용지표 개선</b>이 동시에 확인된 상태입니다.",
        "• 다만 충남 수출은 삼성 HBM의 <b>대용지표</b>이지 삼성전자 공식 HBM 매출과 1:1 대응하지 않습니다.",
        "",
        "<b>[다음 알림에서 반드시 갱신]</b>",
        "• 충남 월간 수출액·중량당 단가",
        "• 삼성 HBM 실제 매출 또는 신뢰 리서치 추정",
        "• HBM 시장점유율",
        "• HBM4/HBM4E 출하 비중·고객 인증·양산",
        "• NVIDIA·AMD·Broadcom 등 고객별 공급 변화",
        "",
        f"<b>환율</b>: {html.escape(fx_basis)}",
        f"<b>기준일</b>: {now.strftime('%Y-%m-%d %H:%M KST')}",
        "",
        f"Counterpoint {href(COUNTERPOINT_HBM_SHARE)} · Bernstein {href(BERNSTEIN_EXPORT)}",
        f"Samsung HBM4 {href(SAMSUNG_HBM4_OFFICIAL)} · Samsung HBM4E {href(SAMSUNG_HBM4E_OFFICIAL)}",
        f"LS증권 인용 {href(LS_HBM4_MIX)}",
    ]
    return "\n".join(lines) + "\n"


def build_event_alert(events: list[dict], now: datetime) -> str:
    lines = [
        "🚨 <b>삼성전자 HBM 신규 변화</b>",
        "━━━━━━━━━━━━━━━━",
        f"<b>신규 변화 {len(events)}건</b> · {now.strftime('%Y-%m-%d %H:%M KST')}",
        "",
    ]
    for i, e in enumerate(events[:4], 1):
        lines.append(f"<b>{i}.</b>")
        lines.extend(event_summary(e))
        lines.append("")
    lines += [
        "<b>판정 원칙</b>",
        "• 기사 제목만으로 호재·악재를 정하지 않고 <b>물량·가격·고객 인증·실제 출하</b>를 같이 봅니다.",
        "• 충남 수출과 증권사 추정은 <b>삼성 공식 HBM 매출과 분리</b>해서 표시합니다.",
    ]
    return "\n".join(lines).strip() + "\n"


def main() -> None:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    state = load_state()
    seen = set(state.get("seen_ids") or [])
    month_key = now.strftime("%Y-%m")

    events = read_events()
    cutoff = now - timedelta(hours=FRESH_HOURS)
    fresh_new = []
    for e in events:
        try:
            dt = datetime.fromisoformat(e.get("published_at_kst") or "")
        except Exception:
            continue
        if cutoff <= dt <= now + timedelta(minutes=10) and e["id"] not in seen:
            fresh_new.append(e)

    chosen: dict[str, dict] = {}
    for e in fresh_new:
        category, _ = classify_event(e)
        old = chosen.get(category)
        if old is None or e["rank"] > old["rank"] or (
            e["rank"] == old["rank"] and e.get("published_at_kst","") > old.get("published_at_kst","")
        ):
            chosen[category] = e
    send_events = sorted(chosen.values(), key=lambda x: x.get("published_at_kst") or "")

    rate, fx_basis = fx_quote()
    monthly_due = state.get("last_monthly_digest") != month_key and now.day >= MONTHLY_DAY

    if monthly_due:
        ALERT.write_text(build_monthly(now, rate, fx_basis), encoding="utf-8")
        state["last_monthly_digest"] = month_key
        # Baseline current search results so old September articles do not immediately re-alert after catch-up.
        seen.update(e["id"] for e in events)
    elif send_events:
        ALERT.write_text(build_event_alert(send_events, now), encoding="utf-8")
        seen.update(e["id"] for e in events)
    elif ALERT.exists():
        ALERT.unlink()

    state.update({
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "seen_ids": sorted(seen)[-1500:],
        "last_event_count": len(events),
        "last_fresh_new_count": len(fresh_new),
        "last_send_event_count": len(send_events),
        "monthly_due": monthly_due,
    })
    save_state(state)

    STATUS.write_text(
        "# Samsung HBM Watch\n"
        f"- checked_at_kst: {now.isoformat(timespec='seconds')}\n"
        f"- events: {len(events)}\n"
        f"- fresh_new: {len(fresh_new)}\n"
        f"- monthly_due: {str(monthly_due).lower()}\n"
        f"- alert_generated: {str(monthly_due or bool(send_events)).lower()}\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
