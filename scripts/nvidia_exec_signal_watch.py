from __future__ import annotations

# EDA lane test marker

import hashlib
import html
import json
import os
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
STATE = ROOT / "data" / "nvidia_exec_signal_state.json"
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)
ALERT = OUT / "nvidia_exec_signal_alert.html"
STATUS = OUT / "nvidia_exec_signal_status.md"

UA = "Mozilla/5.0 (compatible; khs-watch/1.0; +https://github.com/qedgwangju-dot/khs-watch)"
FRESH_HOURS = 36
FORMAT_VERSION = 3
CAPITAL_RETURN_TRACK_VERSION = 1
CAPITAL_RETURN_CORRECTION_VERSION = 1
CAPITAL_RETURN_DEDUPE_VERSION = 1
SCHEDULE_AUDIT_VERSION = 1

OFFICIAL_Q2_TRANSCRIPT = (
    "https://investor.nvidia.com/files/content_files/TRANSCRIPT_-NVIDIA-Corp-NVDA-US-Q2-2027-"
    "Earnings-Call-26-August-2026-5_00-PM-ET.pdf"
)
REUTERS_SCOTLAND = (
    "https://www.reuters.com/world/uk/king-charles-urge-ai-leaders-protect-humanity-scottish-meeting-2026-09-17/"
)
OFFICIAL_Q2_10Q = (
    "https://investor.nvidia.com/files/doc_financials/2027/NVDA-2027-Q2-10Q-Final-including-exhibits.pdf"
)
OFFICIAL_PRESS_RELEASES = "https://investor.nvidia.com/news-and-events/press-releases/default.aspx"
OFFICIAL_BUYBACK_CANDIDATES = [
    "https://investor.nvidia.com/news/press-release-details/2026/NVIDIA-Announces-a-150-Billion-Share-Repurchase-Authorization-Increase/default.aspx",
    "https://investor.nvidia.com/news/press-release-details/2026/NVIDIA-Announces-a-150-Billion-Share-Repurchase-Authorization-Increase/",
]

CAPITAL_RETURN_BASELINE = {
    "remaining_authorization_usd_b": 99.3,
    "actual_q2_repurchase_usd_b": 19.7,
    "actual_h1_repurchase_usd_b": 39.8,
    "as_of": "2026-07-26",
    "source_url": OFFICIAL_Q2_10Q,
}

QUERIES = [
    '"Jensen Huang" Nvidia (double OR doubling OR twice) chip sales 2027',
    '"Jensen Huang" Nvidia (sales OR demand OR growth OR shipments) next year',
    '"NVIDIA" "customer forecasts" doubling next year',
    '"Jensen Huang" AI safety unsafe product release pause',
    '"Jensen Huang" safety engineering problem unsafe products',
    '"젠슨 황" 엔비디아 내년 칩 판매 두 배',
    '"젠슨 황" AI 안전 제품 출시 보류',
    '"NVIDIA" "share repurchase" authorization',
    '"NVIDIA" buyback authorization 150 billion 235 billion',
    '"NVIDIA" capital return repurchase dividend',
    '"엔비디아" 자사주 매입 승인',
    '"엔비디아" 자사주 매입 1500억 달러',
]

TRUSTED = (
    "reuters", "bloomberg", "nvidia", "financial times", "ft.com", "techcrunch",
    "associated press", "ap news", "barron's", "barrons", "marketscreener", "mt newswires",
    "cnbc", "wall street journal", "wsj", "연합뉴스", "yonhap",
)


def fetch(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
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


def source_rank(source: str, title: str = "") -> int:
    low = f"{source} {title}".lower()
    if "nvidia" in low and ("investor" in low or "newsroom" in low):
        return 100
    if "reuters" in low:
        return 95
    if "bloomberg" in low:
        return 90
    if "financial times" in low or "ft.com" in low:
        return 85
    if "techcrunch" in low:
        return 80
    if "associated press" in low or "ap news" in low:
        return 78
    if "barron" in low:
        return 75
    if "marketscreener" in low or "mt newswires" in low:
        return 70
    if "cnbc" in low or "wall street journal" in low or "wsj" in low:
        return 70
    if "yonhap" in low or "연합뉴스" in low:
        return 65
    return 10


def classify(text: str) -> str:
    low = text.lower()
    nvidia = "nvidia" in low or "엔비디아" in low
    jensen = "jensen huang" in low or "젠슨 황" in low
    if not (nvidia or jensen):
        return ""

    demand_terms = (
        "double", "doubling", "twice", "70%", "sales", "revenue", "demand", "shipments",
        "chip sales", "growth", "두 배", "판매", "수요", "매출", "출하",
    )
    safety_terms = (
        "safety", "unsafe", "don't release", "do not release", "pause", "engineering problem",
        "안전", "출시 보류", "출시하지", "보류",
    )
    capital_terms = (
        "share repurchase", "repurchase authorization", "stock repurchase", "buyback",
        "capital return", "return capital", "자사주", "주식 매입", "주주환원", "주주 환원",
    )

    if any(k in low for k in capital_terms):
        return "capital_return"
    if any(k in low for k in demand_terms):
        return "demand"
    if jensen and any(k in low for k in safety_terms):
        return "safety"
    return ""


def _money_billion(text: str, label_patterns: tuple[str, ...]) -> float | None:
    for label in label_patterns:
        patterns = [
            label + r"[^$0-9]{0,100}\$\s*([0-9]+(?:\.[0-9]+)?)\s*(?:billion|bn|b)\b",
            r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*(?:billion|bn|b)\b[^.]{0,100}" + label,
            label + r"[^0-9]{0,100}([0-9]+(?:\.[0-9]+)?)\s*(?:십억|billion)\s*달러",
            label + r"[^0-9]{0,100}([0-9]+(?:\.[0-9]+)?)\s*억\s*달러",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.I)
            if not m:
                continue
            value = float(m.group(1))
            if "억" in pat:
                value /= 10.0
            if 0 < value < 5000:
                return value
    return None


def extract_capital_return(text: str) -> dict:
    low = text.lower()
    additional = _money_billion(text, (
        # "increasing the total remaining amount to $235B" is a new total,
        # not a $235B incremental authorization. Incremental parsing therefore
        # requires "additional" or an explicit "increase by" construction.
        r"(?:additional|increase(?:d)?\s+by|authorization increase(?:d)?\s+by|추가(?:로)?|증액)",
        r"(?:authorized|approved|승인)[^.]{0,60}(?:additional|추가)",
    ))
    remaining = _money_billion(text, (
        r"(?:total remaining|remaining total|remaining amount|total authorization|total remaining amount|잔여|남은|총 승인)",
        r"(?:increase(?:s|d)?|raising|bringing)[^.]{0,70}(?:to|총)",
    ))
    fy = None
    for pat in (
        r"(?:through|by)\s+(?:fiscal\s+year|fiscal|FY)\s*'?20?([0-9]{2,4})",
        r"(?:회계연도|FY)\s*20?([0-9]{2,4})[^.]{0,40}(?:까지|through)",
    ):
        m = re.search(pat, text, re.I)
        if m:
            raw = m.group(1)
            fy = int(raw) + 2000 if len(raw) == 2 else int(raw)
            break
    actual = None
    m = re.search(r"(?:repurchased|bought back|실제 매입)[^$]{0,60}\$\s*([0-9]+(?:\.[0-9]+)?)\s*(?:billion|bn|b)\b", text, re.I)
    if m:
        actual = float(m.group(1))
    return {
        "additional_authorization_usd_b": additional,
        "remaining_authorization_usd_b": remaining,
        "execution_through_fy": fy,
        "actual_repurchase_usd_b": actual,
    }


def _key_number(value) -> str:
    if value is None:
        return "na"
    return str(float(value)).replace(".", "_")


def fact_key(kind: str, text: str) -> str:
    low = text.lower()
    if kind == "capital_return":
        cap = extract_capital_return(text)
        actual = cap.get("actual_repurchase_usd_b")
        remaining = cap.get("remaining_authorization_usd_b")
        additional = cap.get("additional_authorization_usd_b")
        fy = cap.get("execution_through_fy")
        # Authorization republishers often omit the incremental amount while
        # repeating the same total remaining authorization. Normalize on the
        # resulting total + horizon so partial recaps cannot re-alert the same fact.
        if actual is not None:
            return "nvidia_capital_return_execution_" + _key_number(actual)
        if remaining is not None:
            return "nvidia_capital_return_authorization_" + _key_number(remaining) + "_fy_" + _key_number(fy)
        if additional is not None:
            return "nvidia_capital_return_additional_" + _key_number(additional) + "_fy_" + _key_number(fy)
        return "nvidia_capital_return_unspecified"
    if kind == "demand":
        if any(k in low for k in ("double", "doubling", "twice", "두 배")) and "2027" in low:
            return "nvidia_2027_chip_sales_double"
        if "70%" in low and any(k in low for k in ("growth", "revenue", "매출", "성장")):
            return "nvidia_fy28_revenue_growth_70pct"
        nums = "_".join(re.findall(r"\d+(?:\.\d+)?%", text)[:2])
        return "nvidia_demand_" + (nums.replace("%", "pct") or hashlib.sha1(text.encode()).hexdigest()[:10])
    if kind == "safety":
        if any(k in low for k in ("unsafe", "don't release", "do not release", "pause", "출시 보류", "출시하지")):
            return "nvidia_safety_do_not_release_unsafe"
        return "nvidia_safety_" + hashlib.sha1(text.encode()).hexdigest()[:10]
    return hashlib.sha1(text.encode()).hexdigest()[:12]


def _official_press_release_events() -> list[dict]:
    urls = list(OFFICIAL_BUYBACK_CANDIDATES)
    try:
        listing = fetch(OFFICIAL_PRESS_RELEASES, timeout=20).decode("utf-8", errors="ignore")
        for m in re.finditer(r'href=["\']([^"\']+/news/press-release-details/2026/[^"\']+)["\']', listing, re.I):
            url = urllib.parse.urljoin(OFFICIAL_PRESS_RELEASES, html.unescape(m.group(1)))
            if url not in urls:
                urls.append(url)
    except Exception:
        pass

    rows = []
    for url in urls[:30]:
        try:
            raw = fetch(url, timeout=16).decode("utf-8", errors="ignore")
        except Exception:
            continue
        text = clean(raw)
        if "nvidia" not in text.lower():
            continue
        kind = classify(text)
        if kind != "capital_return":
            continue
        title_m = re.search(r"<title[^>]*>(.*?)</title>", raw, re.I | re.S)
        title = clean(title_m.group(1)) if title_m else "NVIDIA 자본환원 발표"
        pub = ""
        for pat in (
            r"(?:Sept\.?|September)\s+([0-9]{1,2}),\s*(20[0-9]{2})",
            r"(20[0-9]{2})[-/]([0-9]{2})[-/]([0-9]{2})",
        ):
            m = re.search(pat, text, re.I)
            if not m:
                continue
            try:
                if len(m.group(1)) == 4:
                    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                else:
                    y, mo, d = int(m.group(2)), 9, int(m.group(1))
                pub = datetime(y, mo, d, 9, 0, tzinfo=ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")
                break
            except Exception:
                pass
        rows.append({
            "id": event_id(title, "NVIDIA Investor Relations"),
            "kind": "capital_return",
            "fact_key": fact_key("capital_return", text),
            "title": title,
            "description": text[:20000],
            "source": "NVIDIA Investor Relations",
            "published_at_kst": pub,
            "direct_link": url,
            "rank": 100,
        })
    return rows


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
                text = f"{title} {desc}"
                kind = classify(text)
                if not title or not link or not kind:
                    continue
                if not any(k in source.lower() for k in TRUSTED):
                    # MarketScreener often republishes MT/Bloomberg headlines; allow when title names Bloomberg.
                    if not ("bloomberg" in title.lower() and "marketscreener" in source.lower()):
                        continue
                direct = decode_google(link)
                if not direct:
                    continue
                key = event_id(title, source)
                rows[key] = {
                    "id": key,
                    "kind": kind,
                    "fact_key": fact_key(kind, text),
                    "title": title,
                    "description": desc,
                    "source": source or "출처 미표시",
                    "published_at_kst": pub.isoformat(timespec="seconds") if pub else "",
                    "direct_link": direct,
                    "rank": source_rank(source, title),
                }
    for e in _official_press_release_events():
        rows[e["id"]] = e
    return sorted(rows.values(), key=lambda x: x.get("published_at_kst") or "")


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"seen_ids": [], "seen_fact_keys": []}


def write_state(state: dict) -> None:
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def preserve_runtime_audit(new_state: dict, previous: dict, now: datetime, event_name: str | None = None) -> dict:
    """Preserve confirmed delivery receipts and make scheduler health auditable.

    Quiet monitoring runs must never erase the last acknowledged Telegram delivery.
    """
    out = dict(new_state)
    for key in (
        "last_successful_delivery_kst",
        "telegram_message_id",
        "bot_username",
        "delivery_receipt",
    ):
        if previous.get(key) is not None:
            out[key] = previous[key]

    event_name = (event_name if event_name is not None else os.getenv("GITHUB_EVENT_NAME", "")).strip()
    out["schedule_audit_version"] = SCHEDULE_AUDIT_VERSION
    out["last_run_event"] = event_name or previous.get("last_run_event") or "unknown"

    prior_schedule = previous.get("last_schedule_check_kst") or ""
    if event_name == "schedule":
        out["last_schedule_check_kst"] = now.isoformat(timespec="seconds")
        gap = None
        if prior_schedule:
            try:
                old = datetime.fromisoformat(prior_schedule)
                if old.tzinfo is not None:
                    gap = max(0.0, (now - old).total_seconds() / 60.0)
            except Exception:
                gap = None
        out["schedule_gap_minutes"] = round(gap, 1) if gap is not None else None
    elif prior_schedule:
        out["last_schedule_check_kst"] = prior_schedule
        if previous.get("schedule_gap_minutes") is not None:
            out["schedule_gap_minutes"] = previous.get("schedule_gap_minutes")

    if event_name == "push":
        out["last_push_check_kst"] = now.isoformat(timespec="seconds")
    elif previous.get("last_push_check_kst"):
        out["last_push_check_kst"] = previous.get("last_push_check_kst")
    return out


def link(url: str, label: str = "원문") -> str:
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'


def capital_state_changes(current: dict, cap: dict) -> bool:
    """Only alert a capital-return item when it changes a known economic state."""
    fields = (
        "additional_authorization_usd_b",
        "remaining_authorization_usd_b",
        "execution_through_fy",
        "actual_repurchase_usd_b",
    )
    observed = False
    for key in fields:
        value = cap.get(key)
        if value is None:
            continue
        observed = True
        if current.get(key) != value:
            return True
    return False if observed else False


def choose_new(events: list[dict], seen_ids: set[str], seen_fact_keys: set[str], now: datetime) -> list[dict]:
    cutoff = now - timedelta(hours=FRESH_HOURS)
    candidates: list[dict] = []
    for e in events:
        try:
            dt = datetime.fromisoformat(e.get("published_at_kst") or "")
        except Exception:
            continue
        if not (cutoff <= dt <= now + timedelta(minutes=10)):
            continue
        if e["id"] in seen_ids or e["fact_key"] in seen_fact_keys:
            continue
        candidates.append(e)

    # One best source per fact.
    chosen: dict[str, dict] = {}
    for e in candidates:
        old = chosen.get(e["fact_key"])
        if old is None or e["rank"] > old["rank"] or (
            e["rank"] == old["rank"] and e.get("published_at_kst", "") > old.get("published_at_kst", "")
        ):
            chosen[e["fact_key"]] = e
    return sorted(chosen.values(), key=lambda x: x.get("published_at_kst") or "")


def build_alert(events: list[dict], now: datetime) -> str:
    demand = next((e for e in reversed(events) if e["kind"] == "demand"), None)
    safety = next((e for e in reversed(events) if e["kind"] == "safety"), None)
    capital = next((e for e in reversed(events) if e["kind"] == "capital_return"), None)

    lines = [
        "🚨 <b>NVIDIA 경영진·AI 수요·안전 전략 변화</b>",
        "━━━━━━━━━━━━━━━━",
        "<b>[무엇이 달라졌나]</b>",
    ]

    if capital:
        cap = extract_capital_return(clean(f"{capital.get('title','')} {capital.get('description','')}"))
        add = cap.get("additional_authorization_usd_b")
        rem = cap.get("remaining_authorization_usd_b")
        fy = cap.get("execution_through_fy")
        lines += [
            "• <b>자본환원</b>: NVIDIA 이사회가 자사주 매입 승인 규모를 대폭 확대했습니다.",
        ]
        if add is not None:
            lines.append(f"• 추가 승인: <b>${add:g} billion</b>")
        if rem is not None:
            lines.append(f"• 총 잔여 승인한도: <b>${rem:g} billion</b>")
        if fy is not None:
            lines.append(f"• 실행 계획: <b>FY{str(fy)[2:]}</b>까지")
        lines += [
            "• <b>중요:</b> 승인한도는 실제 매입 완료액이 아닙니다. 실제 집행액은 이후 10-Q·10-K의 매입 주식수·평균매입가와 별도로 추적합니다.",
            f"• 직전 공식 기준(2026-07-26): 잔여 승인한도 <b>${CAPITAL_RETURN_BASELINE['remaining_authorization_usd_b']:g} billion</b> · Q2 실제 매입 <b>${CAPITAL_RETURN_BASELINE['actual_q2_repurchase_usd_b']:g} billion</b> · FY27 상반기 실제 매입 <b>${CAPITAL_RETURN_BASELINE['actual_h1_repurchase_usd_b']:g} billion</b>",
        ]
    if demand:
        lines += [
            "• 9월 17일 스코틀랜드에서 Jensen Huang은 찰스 3세 AI 정상회의 전 취재진에게 <b>2027년에 올해보다 약 2배 많은 칩을 판매할 것으로 예상</b>한다고 말했습니다.",
            "• 여기서 ‘칩’은 AI GPU만이 아니라 <b>CPU·스위치·광 네트워킹·노트북·Jetson 등 NVIDIA 전체 반도체 제품군</b>을 포함합니다.",
            "• 따라서 이 발언을 <b>GPU 출하 2배 또는 HBM 수요 2배</b>로 바로 환산하면 안 됩니다.",
        ]
    if safety:
        lines += [
            "• 같은 스코틀랜드 회의 현장에서 Huang은 AI 안전과 관련해 <b>제품이 준비되지 않았으면 출시를 보류하고 더 개발해야 한다</b>는 원칙을 강조했습니다.",
        ]

    lines += [
        "",
        "<b>[공식 기준선과 비교]</b>",
        "• NVIDIA의 2026년 8월 26일 FY27 2분기 공식 실적발표에서는 <b>고객 수요 전망상 다음 해 성장 잠재력이 약 2배</b>라고 설명했습니다.",
        "• 그러나 회사가 공식적으로 제시한 FY28 매출 성장 전망은 <b>약 +70%</b>였습니다.",
        "• 차이는 수요가 부족해서가 아니라 <b>공급 제약</b> 때문이라고 회사가 명시했습니다.",
        "→ 따라서 ‘판매 2배’는 수요 강도의 상단 신호이고, 실제 매출은 HBM·DRAM·파운드리·첨단패키징·전력 등 공급망이 얼마나 따라오느냐에 달려 있습니다.",
        "",
        "<b>[출처·맥락 구분]</b>",
        "• <b>칩 판매 2배</b>: 9월 17일 스코틀랜드 찰스 3세 AI 정상회의 전 취재진 발언으로 CNBC·Bloomberg가 보도했습니다.",
        "• <b>안전 발언</b>: Reuters도 같은 스코틀랜드 회의 현장에서 Huang이 ‘준비되지 않았으면 보류하라’고 말했다고 확인했습니다.",
        "• 두 발언 모두 스코틀랜드 행사 맥락이지만, <b>칩 판매 2배는 수량 전망</b>, <b>안전 발언은 출시 원칙</b>으로 분리해서 해석합니다.",
        "",
        "<b>[투자적으로 왜 중요한가]</b>",
        "• 자사주 매입 <b>승인 확대</b>는 현금창출력과 자본배분 의지를 보여주지만, 승인 즉시 같은 금액이 시장에서 매수되는 것은 아닙니다.",
        "• 실제 주당가치 효과는 <b>실제 집행액·평균 매입가격·주식보상으로 인한 희석·잉여현금흐름</b>을 함께 봐야 합니다.",
        "• <b>전체 칩 수량 2배 전망 + FY28 매출 +70% 공식 전망</b>의 차이는 제품혼합과 공급 제약을 함께 봐야 한다는 뜻입니다.",
        "• HBM·서버 DRAM·첨단패키징·파운드리 생산능력이 늘면 NVIDIA가 현재 못 받는 주문을 추가 매출로 전환할 여지가 큽니다.",
        "• 다만 CPU·스위치·광통신·노트북용 칩까지 포함된 수량 전망이므로 <b>HBM 업체 매출을 2배로 직접 계산하지 않습니다.</b>",
        "• 반대로 안전 발언만으로 제품 출시 지연을 의미하지는 않습니다. 실제 <b>Blackwell·Rubin 일정 변경이나 고객 승인 지연</b>이 확인될 때만 실적 시간표 악화로 판정합니다.",
        "",
        "<b>[다음 알림 조건]</b>",
        "• 자사주 매입 <b>추가 승인·총 잔여한도·실행기한</b>이 변경",
        "• 10-Q·10-K에서 <b>실제 분기 매입액·매입주식수·평균매입가</b> 신규 확정",
        "• 배당금·배당성향 또는 주주환원 정책 변경",
        "• NVIDIA가 FY28 매출 성장률을 <b>+70%에서 상향·하향</b>",
        "• GPU·AI 가속기와 CPU·네트워킹 등 <b>제품별 출하량·판매량 목표</b>를 새로 제시",
        "• 전체 칩 2배 전망 중 <b>AI GPU가 차지하는 비중</b>이 공개",
        "• 고객 수요가 2배인데 실제 공급 가능 비율이 <b>70%에서 변화</b>",
        "• HBM·DRAM·CoWoS·파운드리·전력 가운데 병목 순위가 구체화",
        "• Blackwell·Rubin 또는 신규 AI 제품이 <b>안전·신뢰성 이유로 실제 연기·출시 보류</b>",
        "• AI 규제·안전 기준이 NVIDIA 제품 출시·데이터센터 도입 일정에 직접 영향",
        "",
        f"<b>조회</b>: {now.strftime('%Y-%m-%d %H:%M:%S KST')}",
        f"<b>공식 기준</b>: {link(OFFICIAL_Q2_TRANSCRIPT, 'NVIDIA FY27 2Q 실적발표 원문')}",
        f"<b>스코틀랜드 회의</b>: {link(REUTERS_SCOTLAND, 'Reuters 원문')}",
    ]

    if demand:
        lines.append(
            f"<b>수요·판매 전망 출처</b>: {html.escape(demand['source'])} · {link(demand['direct_link'])}"
        )
    if safety:
        lines.append(
            f"<b>안전 발언 출처</b>: {html.escape(safety['source'])} · {link(safety['direct_link'])}"
        )
    if capital:
        lines.append(
            f"<b>자본환원 출처</b>: {html.escape(capital['source'])} · {link(capital['direct_link'])}"
        )
        lines.append(
            f"<b>직전 공식 자사주 기준</b>: {link(OFFICIAL_Q2_10Q, 'NVIDIA FY27 2Q 10-Q')}"
        )

    return "\n".join(lines) + "\n"


def main() -> None:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    previous_state = load_state()
    state = dict(previous_state)
    seen_ids = set(state.get("seen_ids") or [])
    seen_fact_keys = set(state.get("seen_fact_keys") or [])
    capital_state = dict(state.get("capital_return_state") or {})
    if int(state.get("capital_return_track_version") or 0) < CAPITAL_RETURN_TRACK_VERSION:
        capital_state = dict(CAPITAL_RETURN_BASELINE)
        state["capital_return_track_version"] = CAPITAL_RETURN_TRACK_VERSION

    # Migrate already-known capital-return state into the normalized dedupe key.
    if int(state.get("capital_return_dedupe_version") or 0) < CAPITAL_RETURN_DEDUPE_VERSION:
        remaining = capital_state.get("remaining_authorization_usd_b")
        fy = capital_state.get("execution_through_fy")
        if remaining is not None:
            seen_fact_keys.add(
                "nvidia_capital_return_authorization_" + _key_number(remaining) + "_fy_" + _key_number(fy)
            )
        state["capital_return_dedupe_version"] = CAPITAL_RETURN_DEDUPE_VERSION

    events = read_events()
    new_events = choose_new(events, seen_ids, seen_fact_keys, now)

    # Suppress partial/republished capital-return stories that do not change
    # the already-known authorization or execution state.
    suppressed_fact_keys = set()
    material_events = []
    for e in new_events:
        if e.get("kind") == "capital_return":
            cap = extract_capital_return(clean(f"{e.get('title','')} {e.get('description','')}"))
            if not capital_state_changes(capital_state, cap):
                suppressed_fact_keys.add(e.get("fact_key") or "")
                continue
        material_events.append(e)
    new_events = material_events

    # One-time repair for the 2026-09-28 buyback miss: an earlier v3 code run
    # detected the new capital-return facts but the old pretty-printer stripped
    # them from the Telegram body before delivery. Re-emit the already-verified
    # Reuters-backed state once, then permanently mark the correction complete.
    if (
        not new_events
        and int(state.get("capital_return_correction_version") or 0) < CAPITAL_RETURN_CORRECTION_VERSION
        and float(capital_state.get("additional_authorization_usd_b") or 0) == 150.0
        and float(capital_state.get("remaining_authorization_usd_b") or 0) == 235.0
        and capital_state.get("source_url")
    ):
        correction_text = (
            "NVIDIA announced that its board authorized an additional $150 billion under the existing "
            "share repurchase program, increasing the total remaining amount authorized to $235 billion. "
            "The company expects to execute the total remaining program through fiscal year 2028."
        )
        new_events = [{
            "id": "capital_return_correction_20260928",
            "kind": "capital_return",
            "fact_key": "nvidia_capital_return_correction_20260928",
            "title": "NVIDIA 자사주 매입 승인 확대",
            "description": correction_text,
            "source": capital_state.get("source") or "Reuters",
            "published_at_kst": capital_state.get("observed_at_kst") or now.isoformat(timespec="seconds"),
            "direct_link": capital_state.get("source_url") or "",
            "rank": 99,
        }]

    # Preserve the prior v2 context-correction behavior only for pre-v2 states.
    # The v3 migration adds capital-return coverage; it must not resend old demand/safety facts.
    old_format = int(state.get("format_version") or 0)
    if not new_events and old_format < 2:
        cutoff = now - timedelta(hours=FRESH_HOURS)
        best_by_kind: dict[str, dict] = {}
        for e in events:
            if e.get("kind") not in ("demand", "safety"):
                continue
            try:
                dt = datetime.fromisoformat(e.get("published_at_kst") or "")
            except Exception:
                continue
            if not (cutoff <= dt <= now + timedelta(minutes=10)):
                continue
            old = best_by_kind.get(e["kind"])
            if old is None or e["rank"] > old["rank"] or (
                e["rank"] == old["rank"] and e.get("published_at_kst", "") > old.get("published_at_kst", "")
            ):
                best_by_kind[e["kind"]] = e
        new_events = sorted(best_by_kind.values(), key=lambda x: x.get("published_at_kst") or "")
    elif not new_events and old_format < FORMAT_VERSION:
        cutoff = now - timedelta(hours=FRESH_HOURS)
        capital_candidates = []
        for e in events:
            if e.get("kind") != "capital_return":
                continue
            try:
                dt = datetime.fromisoformat(e.get("published_at_kst") or "")
            except Exception:
                continue
            if cutoff <= dt <= now + timedelta(minutes=10):
                capital_candidates.append(e)
        if capital_candidates:
            best = max(capital_candidates, key=lambda e: (e.get("rank", 0), e.get("published_at_kst", "")))
            new_events = [best]

    # For the first run, intentionally allow fresh current signals to be sent once.
    if new_events:
        ALERT.write_text(build_alert(new_events, now), encoding="utf-8")
    elif ALERT.exists():
        ALERT.unlink()

    seen_ids.update(e["id"] for e in events)
    seen_fact_keys.update(e["fact_key"] for e in new_events)
    seen_fact_keys.update(x for x in suppressed_fact_keys if x)
    for e in new_events:
        if e.get("kind") != "capital_return":
            continue
        cap = extract_capital_return(clean(f"{e.get('title','')} {e.get('description','')}"))
        for key in ("additional_authorization_usd_b", "remaining_authorization_usd_b", "execution_through_fy", "actual_repurchase_usd_b"):
            if cap.get(key) is not None:
                capital_state[key] = cap[key]
        event_rank = int(e.get("rank") or 0)
        old_rank = int(capital_state.get("source_rank") or source_rank(capital_state.get("source") or "", ""))
        if event_rank >= old_rank:
            capital_state["observed_at_kst"] = e.get("published_at_kst") or now.isoformat(timespec="seconds")
            capital_state["source"] = e.get("source") or ""
            capital_state["source_url"] = e.get("direct_link") or ""
            capital_state["source_rank"] = event_rank
    state = {
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "seen_ids": sorted(seen_ids)[-1000:],
        "seen_fact_keys": sorted(seen_fact_keys)[-300:],
        "last_event_count": len(events),
        "last_new_event_count": len(new_events),
        "alert_generated": bool(new_events),
        "format_version": FORMAT_VERSION,
        "capital_return_track_version": CAPITAL_RETURN_TRACK_VERSION,
        "capital_return_dedupe_version": CAPITAL_RETURN_DEDUPE_VERSION,
        "capital_return_correction_version": CAPITAL_RETURN_CORRECTION_VERSION if any(
            e.get("fact_key") == "nvidia_capital_return_correction_20260928" for e in new_events
        ) else int(state.get("capital_return_correction_version") or 0),
        "capital_return_state": capital_state,
    }
    state = preserve_runtime_audit(state, previous_state, now)
    write_state(state)

    STATUS.write_text(
        "# NVIDIA executive signal watch\n"
        f"- checked_at_kst: {now.isoformat(timespec='seconds')}\n"
        f"- events: {len(events)}\n"
        f"- new_events: {len(new_events)}\n"
        f"- alert_generated: {str(bool(new_events)).lower()}\n"
        f"- run_event: {state.get('last_run_event','unknown')}\n"
        f"- last_schedule_check_kst: {state.get('last_schedule_check_kst','none')}\n"
        f"- schedule_gap_minutes: {state.get('schedule_gap_minutes','none')}\n"
        f"- last_successful_delivery_kst: {state.get('last_successful_delivery_kst','none')}\n"
        f"- telegram_message_id: {state.get('telegram_message_id','none')}\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
