#!/usr/bin/env python3
"""Apple premium-demand leading indicator and iPhone Duo forecast watch.

This module is intentionally separate from direct iPhone Duo preorder/sales
tracking:
- iPhone 18 Pro demand is an Apple premium-demand proxy, never Duo direct demand.
- Duo forecasts are analyst shipment/sales expectations, never actual orders.
- Counterpoint's 2026-09-30 public China insight directly confirms +12% Week 38
  first-three-day Pro sales and 33% Apple weekly market share; the proprietary
  underlying weekly transaction table is not publicly available.
- Counterpoint's separate 2026-09-30 panel report tracks cumulative iPhone 18 Pro
  OLED procurement through October +2% YoY (a panel tracker projection, not
  October retail sales or a new Apple component purchase order).
- Counterpoint ~6m Duo forecast (Reuters) and TrendForce ~5m shipment forecast
  are tracked as separate institutional baselines.

Alerts append to the existing Apple Duo Telegram file; no new bot/workflow is
created.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "apple_premium_demand_duo_forecast_state.json"
OUT_DIR = ROOT / "out"
OUT_DIR.mkdir(exist_ok=True)
PENDING_PATH = OUT_DIR / "apple_premium_demand_duo_forecast_pending_state.json"
STATUS_PATH = OUT_DIR / "apple_premium_demand_duo_forecast_status.md"
FRAGMENT_PATH = OUT_DIR / "apple_premium_demand_duo_forecast_alert.html"
MAIN_ALERT_PATH = OUT_DIR / "apple_duo_supply_watch_telegram.txt"
KST = ZoneInfo("Asia/Seoul")

APPLE_PREORDER_KST = dt.datetime(2026, 10, 16, 21, 0, tzinfo=KST)
APPLE_LAUNCH_DATE = dt.date(2026, 10, 23)
APPLE_OFFICIAL = "https://www.apple.com/kr/shop/buy-iphone/iphone-duo"
COUNTERPOINT_DUO_REUTERS = "https://www.reuters.com/business/retail-consumer/apples-foldable-iphone-poses-1999-question-who-is-it-2026-09-10/"
TRENDFORCE_DUO = "https://www.trendforce.com/presscenter/news/20260910-13228.html"
COUNTERPOINT_CHINA_CONTEXT = "https://counterpointresearch.com/en/insights/china-smartphone-market-saw-sharper-contraction-after-618"
COUNTERPOINT_CHINA_PRO_OFFICIAL = "https://counterpointresearch.com/en/insights/iphone-18-pro-series-sales-up-12-percent-yoy-in-launch-week-in-china-as-apple-takes-hashtag-1-spot"
COUNTERPOINT_PRO_PANEL_OFFICIAL = "https://counterpointresearch.com/ko/reports/apples-iphone-18-pro-and-duo-panel-procurement-tracks-ahead-of-the-prior-cycle"
COUNTERPOINT_THREE_WEEK_OFFICIAL = "https://counterpointresearch.com/en/insights/apple-iphone-18-pro-series-off-to-a-mixed-start-recording-sales-growth-three-weeks-after-launched"
COUNTERPOINT_THREE_WEEK_REUTERS = "https://www.reuters.com/business/retail-consumer/initial-global-sales-apple-iphone-18-pro-higher-than-17-series-counterpoint-2026-10-27/"
SCOPE_ERROR_CORRECTION_KEY = "iphone18pro_scope_fix_message_352_20261029"

BASELINE = {
    "iphone18pro_china_yoy_pct": 12.0,
    "iphone18pro_china_first3weeks_yoy_pct": 29.0,
    "iphone18pro_global_first3weeks_yoy_pct": 3.1,
    "iphone18pro_us_first3weeks_yoy_pct": -4.0,
    "iphone18pro_japan_first3weeks_yoy_pct": -27.0,
    "iphone18pro_pro_max_first3weeks_share_pct": 56.0,
    "iphone18pro_pro_max_prior_first3weeks_share_pct": 57.0,
    "iphone18pro_three_weeks_confirmation": (
        "Counterpoint Research 2026-10-27 공식: 출시 첫 3주 중국 +29%, "
        "전 세계 +3.1%, 미국 -4%, 일본 -27%; Pro Max 비중 56%(전년 57%). "
        "중국 첫 3일 +12%와 지역·통계기간을 구분해야 함"
    ),
    "apple_china_week38_share_pct": 33.0,
    "counterpoint_duo_forecast_m": 6.0,
    "trendforce_duo_forecast_m": 5.0,
    "iphone18pro_confirmation": "Counterpoint 2026-09-30 공식: 중국 출시 초기 3일 판매 전년 대비 +12%, 38주차 Apple 점유율 33%; 10월 27일 세계 첫 3주 자료와 직접 비교 금지",
    "iphone18pro_panel_cumulative_through_oct_yoy_pct": 2.0,
    "iphone18pro_panel_confirmation": "Counterpoint 2026-09-30 공식: 2026년 10월까지의 Pro OLED 패널 누적 조달 추적 전년 대비 +2%; 10월 확정 실판매가 아닌 패널 추적치",
    "counterpoint_duo_confirmation": "Reuters가 Counterpoint 전망 약 600만대 인용",
    "trendforce_duo_confirmation": "TrendForce 공식 2026 출하 약 500만대",
}

QUERIES = [
    ("ko", '"아이폰 18 프로" 중국 판매 12% 점유율 33% Counterpoint'),
    ("ko", '"아이폰 18 Pro" 중국 38주차 판매 점유율 Counterpoint'),
    ("ko", '"아이폰 듀오" 600만대 Counterpoint 전망'),
    ("ko", '"아이폰 듀오" 500만대 TrendForce 출하 전망'),
    ("en", '"iPhone 18 Pro" China sales 12% 33% Counterpoint week 38'),
    ("en", '"iPhone 18 Pro" China weekly sales share Counterpoint'),
    ("en", '"iPhone 18 Pro" China 29 global 3.1 first three weeks Counterpoint'),
    ("ko", '"아이폰 18 프로" 세계 첫 3주 3.1 중국 29 Counterpoint'),
    ("en", '"iPhone Duo" 6 million Counterpoint forecast'),
    ("en", '"iPhone Duo" 5 million TrendForce shipments forecast'),
]

HIGH_SOURCES = (
    "counterpoint", "reuters", "trendforce", "bloomberg",
    "financial times", "wall street journal", "wsj", "nikkei",
)
MID_SOURCES = (
    "wallstreetcn", "华尔街见闻", "digitimes", "macrumors", "the elec",
    "etnews", "전자신문", "zdnet", "매일경제", "한국경제", "서울경제",
)
LOW_SOURCES = (
    "notebookcheck", "wccftech", "technobezz", "reddit", "note.com",
)

PREMIUM_MARKERS = (
    "iphone 18 pro", "iphone18 pro", "iphone 18 pro max",
    "아이폰 18 프로", "아이폰18 프로",
)
DUO_MARKERS = (
    "iphone duo", "apple foldable", "foldable iphone",
    "아이폰 듀오", "애플 폴더블", "폴더블 아이폰",
)
CHINA_MARKERS = ("china", "cn market", "중국", "中国")
SALES_MARKERS = (
    "sales", "sell-through", "sold", "판매", "판매량", "销量", "销售",
)
SHARE_MARKERS = (
    "share", "market share", "점유율", "份额", "市场份额",
)
FORECAST_MARKERS = (
    "forecast", "estimate", "expect", "expected", "project", "projection",
    "전망", "예상", "추정", "预测", "预计",
)

UA = "Mozilla/5.0 (compatible; khs-apple-premium-demand-watch/1.0)"


def _fetch(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept": "application/rss+xml,application/xml,text/xml,*/*"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def _clean(value: str | None) -> str:
    text = html.unescape(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize(value: str) -> str:
    text = _clean(value).lower()
    text = re.sub(r"\s+-\s+[^-]{1,80}$", "", text)
    text = re.sub(r"[^0-9a-z가-힣一-龥%.$~+\-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _source_rank(source: str) -> int:
    raw = _clean(source).lower().strip()
    low = _normalize(source)
    if raw in {"apple", "apple inc", "apple inc.", "apple newsroom", "apple.com"}:
        return 3
    # Publishers named after Apple must never receive Apple Inc. authority.
    if "applemagazine" in raw or "apple magazine" in raw:
        return 1
    if any(x.lower() in raw or x.lower() in low for x in HIGH_SOURCES):
        return 3
    if any(x.lower() in raw or x.lower() in low for x in MID_SOURCES):
        return 2
    if any(x.lower() in raw or x.lower() in low for x in LOW_SOURCES):
        return 0
    return 1


def _verified_sales_publisher(item: dict) -> bool:
    """A search redirect is not the original statistical report."""
    source = _clean(item.get("source") or "").lower()
    host = (urllib.parse.urlparse(item.get("link") or "").hostname or "").lower().removeprefix("www.")
    allowed = {"counterpointresearch.com", "reuters.com"}
    return (("counterpoint" in source or "reuters" in source)
            and any(host == d or host.endswith("." + d) for d in allowed))


def _regional_sales_percent(blob: str, region: str) -> float | None:
    """Choose the nearest geographic scope in the same sentence as sales growth."""
    names = {
        "china": r"\bchina\b|\bchinese\s+market\b|중국|中国",
        "global": r"\bglobal(?:ly)?\b|\bworldwide\b|전\s*세계|全球",
    }
    scopes = re.compile("|".join(f"(?P<{name}>{pattern})" for name, pattern in names.items()), re.I)
    for clause in re.split(r"(?<=[.!?。])\s+|[;；\n]+", blob):
        for match in re.finditer(r"([+\-]?\d{1,3}(?:\.\d+)?)\s*%", clause):
            base=max(0,match.start()-155)
            before=clause[base:match.start()].lower()
            after=clause[match.end():match.end()+35].lower()
            near=before[-105:]+" "+after[:20]
            if not any(k in near for k in (
                "sales","sold","sell-through","growth","grew","rose","increas",
                "up ","yoy","판매","销量","增长","上升",
            )):
                continue
            if any(k in before[-45:] for k in ("share","점유율","份额","占比")):
                continue
            postfix=re.match(
                r"\s*(?:globally|worldwide|in\s+china|in\s+the\s+chinese\s+market|"
                r"全球|在中国|중국에서|전\s*세계)", after, re.I,
            )
            if postfix:
                p=postfix.group(0)
                observed_scope=("china" if any(k in p for k in ("china","chinese","中国","중국"))
                                else "global")
            else:
                tags=list(scopes.finditer(before))
                if not tags:
                    continue
                last=tags[-1]
                observed_scope=last.lastgroup
                if len(before)-last.end()>90:
                    continue
            if observed_scope!=region:
                continue
            value=float(match.group(1))
            if not match.group(1).startswith(("+","-")):
                recent=before[-75:]
                if any(k in recent for k in (
                    "declin","fell","down ","drop","decreas","하락","감소","下降",
                )):
                    value=-abs(value)
                else:
                    value=abs(value)
            return round(value,2)
    return None


def _parse_date(value: str | None) -> dt.datetime | None:
    try:
        parsed = parsedate_to_datetime(value or "")
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(KST)
    except Exception:
        return None


def _rss_url(lang: str, query: str) -> str:
    if lang == "ko":
        params = {"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"}
    else:
        params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)


def _fingerprint(item: dict) -> str:
    base = f"{_normalize(item.get('title',''))}|{_normalize(item.get('source',''))}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:24]


def _near_percent(blob: str, markers: tuple[str, ...], context: tuple[str, ...]) -> float | None:
    low = blob.lower()
    candidates: list[tuple[int, float]] = []
    for m in re.finditer(r"([+\-]?\d{1,3}(?:\.\d+)?)\s*%", blob):
        window = low[max(0, m.start() - 140): min(len(low), m.end() + 140)]
        if not any(x in window for x in markers):
            continue
        if not any(x in window for x in context):
            continue
        value = float(m.group(1))
        # Prefer explicit sign; otherwise infer from common direction words.
        if not m.group(1).startswith(("+", "-")):
            if any(x in window for x in ("increase", "increased", "rose", "growth", "up ", "증가", "상승", "늘", "增长", "上升")):
                value = abs(value)
            elif any(x in window for x in ("decrease", "decline", "fell", "down ", "감소", "하락", "减少", "下降")):
                value = -abs(value)
        candidates.append((m.start(), round(value, 2)))
    return candidates[0][1] if candidates else None


def _premium_yoy(blob: str) -> float | None:
    """China launch-3-day Week 38 only, not global or a later three-week total."""
    low=blob.lower()
    if not any(k in low for k in PREMIUM_MARKERS):
        return None
    if not any(k in low for k in CHINA_MARKERS):
        return None
    if any(k in low for k in (
        "first three weeks","first 3 weeks","opening three weeks",
        "three weeks after launch","첫 3주","출시 3주","前三周",
    )):
        return None
    if not any(k in low for k in (
        "week 38","week38","38주차","第38周","first three days",
        "first 3 days","launch week",
    )):
        return None
    return _regional_sales_percent(blob,"china")


def _premium_three_week_yoy(blob: str, region: str) -> float | None:
    low=blob.lower()
    if not any(k in low for k in PREMIUM_MARKERS):
        return None
    if not any(k in low for k in (
        "first three weeks","first 3 weeks","opening three weeks",
        "three weeks after launch","first 3-week","첫 3주","출시 후 3주",
        "上市三周","前三周",
    )):
        return None
    return _regional_sales_percent(blob,region)


def _premium_share(blob: str) -> float | None:
    """Apple market share in China Week 38, not Pro Max model mix."""
    low=blob.lower()
    if not any(k in low for k in CHINA_MARKERS):
        return None
    if not any(k in low for k in ("week 38","week38","38주차","第38周")):
        return None
    for clause in re.split(r"(?<=[.!?。])\s+|[;\n]+",blob):
        for match in re.finditer(r"(\d{1,3}(?:\.\d+)?)\s*%",clause):
            before=clause[max(0,match.start()-110):match.start()].lower()
            if any(k in before[-75:] for k in ("pro max","model mix")):
                continue
            if (any(k in before for k in ("share","market share","점유율","份额"))
                    and any(k in before for k in ("apple","애플","苹果"))):
                n=float(match.group(1))
                if 1<=n<=80:
                    return round(n,2)
    return None


def _million_forecast(blob: str) -> float | None:
    low = blob.lower().replace(",", "")
    # Analyst calendar-year outlook ≠ first-12-month supplier build target.
    if any(x in low for x in (
        "12-month", "12 months", "12 month", "first year",
        "12개월", "첫 1년", "첫해", "1년간",
    )) and any(x in low for x in DUO_MARKERS):
        return None
    if ("44%" in low or "44 percent" in low) and any(x in low for x in (
        "14 million", "1400만", "14m units",
    )) and any(x in low for x in DUO_MARKERS):
        return None
    if not any(x in low for x in DUO_MARKERS):
        return None
    if not any(x in low for x in FORECAST_MARKERS):
        return None
    vals: list[float] = []
    patterns = [
        (r"(\d+(?:\.\d+)?)\s*(?:million|mn)\s*(?:units|iphones|devices|phones)?", 1.0),
        (r"(\d+(?:\.\d+)?)\s*백만\s*(?:대)?", 1.0),
        (r"(\d+(?:\.\d+)?)\s*万\s*部", 0.01),
        (r"(\d+(?:\.\d+)?)\s*만\s*대", 0.01),
    ]
    for pattern, mult in patterns:
        for m in re.finditer(pattern, low):
            value = float(m.group(1)) * mult
            if 1 <= value <= 30:
                vals.append(value)
    return round(max(vals), 2) if vals else None


def _forecast_source(source: str, blob: str) -> str:
    low = f"{source} {blob}".lower()
    if "counterpoint" in low:
        return "counterpoint"
    if "trendforce" in low:
        return "trendforce"
    return ""


def _load_state() -> dict:
    if STATE_PATH.exists():
        try:
            data=json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError("Premium demand state corrupt: fail closed to prevent duplicate alert") from exc
        if not isinstance(data,dict):
            raise RuntimeError("Premium demand state is invalid: fail closed")
        data.setdefault("seen", [])
        data.setdefault("metrics", {})
        data.setdefault("seen_fact_keys", [])
        return data
    return {
        "schema_version": 1,
        "initial_alert_sent": False,
        "seen": [],
        "seen_fact_keys": [],
        "metrics": dict(BASELINE),
        "last_alert": None,
    }


def collect() -> tuple[list[dict], list[str]]:
    now = dt.datetime.now(KST)
    cutoff = now - dt.timedelta(days=14)
    rows: dict[str, dict] = {}
    errors: list[str] = []
    for lang, query in QUERIES:
        try:
            root = ET.fromstring(_fetch(_rss_url(lang, query)))
        except Exception as exc:
            errors.append(f"{lang}:{query[:45]} -> {type(exc).__name__}")
            continue
        for node in root.findall(".//item"):
            title = _clean(node.findtext("title"))
            description = _clean(node.findtext("description"))
            link = _clean(node.findtext("link"))
            source_node = node.find("source")
            source = _clean(source_node.text if source_node is not None else "")
            published = _parse_date(_clean(node.findtext("pubDate")))
            if not title or not published or published < cutoff or published > now + dt.timedelta(minutes=15):
                continue
            blob = f"{title} {description} {source}".lower()
            if not any(x in blob for x in PREMIUM_MARKERS + DUO_MARKERS):
                continue
            item = {
                "title": title,
                "description": description,
                "link": link,
                "source": source or "출처 미표시",
                "published_at_kst": published.isoformat(timespec="seconds"),
            }
            rows[_fingerprint(item)] = item
    return sorted(rows.values(), key=lambda x: x["published_at_kst"]), errors


def _signal(item: dict, state: dict) -> dict | None:
    blob = f"{item['title']} {item.get('description','')} {item.get('source','')}"
    rank = _source_rank(item.get("source", ""))
    if rank < 2:
        return None

    metrics = state.get("metrics") or {}
    reasons: list[str] = []
    changes: dict[str, float] = {}
    stage = 0
    direction = 0

    yoy = _premium_yoy(blob) if _verified_sales_publisher(item) else None
    if yoy is not None:
        previous = float(metrics.get("iphone18pro_china_yoy_pct") or 0)
        if not previous or abs(yoy - previous) >= 5 or (yoy > 0) != (previous > 0):
            reasons.append(f"중국 iPhone 18 Pro 판매 증가율 {previous:+g}%→{yoy:+g}%")
            changes["iphone18pro_china_yoy_pct"] = yoy
            stage = max(stage, 1)
            direction = 1 if yoy > previous else -1

    if _verified_sales_publisher(item):
        for region, key, name in (
            ("china", "iphone18pro_china_first3weeks_yoy_pct", "중국"),
            ("global", "iphone18pro_global_first3weeks_yoy_pct", "세계"),
        ):
            observed = _premium_three_week_yoy(blob, region)
            if observed is None:
                continue
            previous = float(metrics.get(key, BASELINE[key]))
            if abs(observed - previous) >= 5 or (observed > 0) != (previous > 0):
                reasons.append(
                    f"{name} iPhone 18 Pro 출시 첫 3주 판매 증가율 "
                    f"{previous:+g}%→{observed:+g}% (동일 지역·기간)"
                )
                changes[key] = observed
                stage = max(stage, 1)
                direction = 1 if observed > previous else -1

    share = _premium_share(blob) if _verified_sales_publisher(item) else None
    if share is not None:
        previous = float(metrics.get("apple_china_week38_share_pct") or 0)
        if not previous or abs(share - previous) >= 3:
            reasons.append(f"중국 Apple 주간 점유율 {previous:g}%→{share:g}%")
            changes["apple_china_week38_share_pct"] = share
            stage = max(stage, 1)
            direction = 1 if share > previous else -1

    forecast = _million_forecast(blob)
    source_key = _forecast_source(item.get("source", ""), blob)
    if forecast is not None and source_key:
        metric_key = f"{source_key}_duo_forecast_m"
        previous = float(metrics.get(metric_key) or 0)
        if not previous or abs(forecast - previous) >= 1.0:
            reasons.append(f"{source_key.title()} Duo 전망 {previous:g}→{forecast:g}백만대")
            changes[metric_key] = forecast
            stage = max(stage, 2 if forecast < 5 or forecast > 7 else 1)
            direction = 1 if forecast > previous else -1

    if not reasons:
        return None

    return {
        "item": item,
        "rank": rank,
        "stage": stage,
        "direction": direction,
        "reasons": reasons[:3],
        "changes": changes,
    }


def _needs_scope_correction(state: dict) -> bool:
    if state.get("false_china_scope_correction_sent"):
        return False
    try:
        return abs(float((state.get("metrics") or {}).get("iphone18pro_china_yoy_pct",12)) - 3.1)<0.02
    except (TypeError,ValueError):
        return False


def _scope_correction_alert() -> str:
    return "\n".join([
        "🍎 <b>[정정 | Apple iPhone 18 Pro 판매 증가율]</b>",
        "━━━━━━━━━━━━━━━━",
        "• 앞선 알림(메시지 ID 352)의 <b>'중국 +12% → +3.1%'</b> 비교는 오류이므로 철회합니다.",
        "• <b>중국 +12%</b>: 9월 30일 공개된 출시 초기 <b>3일</b> 판매 증가율.",
        "• <b>중국 +29%</b>: 10월 27일 공개된 출시 후 <b>첫 3주</b> 판매 증가율.",
        "• <b>전 세계 +3.1%</b>: 같은 10월 27일 발표의 출시 후 <b>첫 3주</b> 판매 증가율.",
        "• 같은 3주 기준 미국 -4%, 일본 -27%. Pro Max 비중 56%(전년 57%).",
        "• <b>원인:</b> 세계 수치를 중국 수치로 오인했고, 서로 다른 지역·기간을 직접 비교했습니다.",
        "• <b>판정:</b> 중국 수요 둔화의 증거가 아닙니다. 전 세계 성장은 중국의 높은 증가율에 의존했습니다.",
        "• Counterpoint의 판매 추정 자료이며 Apple 공식 판매 대수·Duo 직접 판매량과 다릅니다.",
        "",
        f'<a href="{COUNTERPOINT_CHINA_PRO_OFFICIAL}">Counterpoint 중국 초기 3일 원문</a>',
        f'<a href="{COUNTERPOINT_THREE_WEEK_OFFICIAL}">Counterpoint 국가별 첫 3주 원문</a>',
        f'<a href="{COUNTERPOINT_THREE_WEEK_REUTERS}">Reuters 교차 확인</a>',
    ])+"\n"


def _baseline_alert(metrics: dict) -> str:
    return "\n".join([
        "🍎 <b>[Apple 프리미엄 수요·Duo 전망 | 기준선]</b>",
        "━━━━━━━━━━━━━━━━",
        "<b>[Apple 프리미엄 수요 선행지표]</b>",
        f"• 중국 iPhone 18 Pro 초기 판매: <b>전년 대비 +{metrics['iphone18pro_china_yoy_pct']:g}%</b>",
        f"• 중국 38주차 Apple 점유율: <b>{metrics['apple_china_week38_share_pct']:g}%</b>",
        "• 위 두 수치는 <b>Counterpoint 2026-09-30 공식 공개 해설에서 검증</b>했습니다(원시 주간 거래표는 별도).",
        f"• Counterpoint Pro OLED 패널: <b>10월까지 누적 전년 대비 +{metrics['iphone18pro_panel_cumulative_through_oct_yoy_pct']:g}% 추적</b> — 패널 조달이며 Pro 소비자 실판매가 아닙니다.",
        "• 중국 판매 +12%·주간 점유율 33%·누적 패널 +2%는 서로 다른 지표이며, iPhone Duo 직접 수요로 승격하지 않습니다.",
        f"• 중국 출시 후 첫 3주 +{metrics['iphone18pro_china_first3weeks_yoy_pct']:g}%, "
        f"세계 첫 3주 +{metrics['iphone18pro_global_first3weeks_yoy_pct']:g}% — Counterpoint 10/27 별도 자료.",
        "",
        "<b>[Duo 기관 전망]</b>",
        f"• Counterpoint: <b>약 {metrics['counterpoint_duo_forecast_m']:g}백만대</b> — Reuters 인용 확인",
        f"• TrendForce: <b>약 {metrics['trendforce_duo_forecast_m']:g}백만대</b> — 공식 2026 출하 전망",
        "• 현재 기관 기준 범위는 <b>500만~600만대</b>. 700만대 초과 또는 500만대 미만으로 바뀌면 재평가 경고를 강화합니다.",
        "",
        "<b>[현재 판정]</b>",
        "• 🟡 <b>Apple 프리미엄 수요 선행 확인</b>",
        "• Duo 사전주문 전이므로 Pro 판매 강세를 Duo 판매 강세로 치환하지 않습니다.",
        "",
        "<b>[다음 알림 조건]</b>",
        "• 중국 iPhone 18 Pro 증가율이 기준 +12%에서 ±5%p 이상 변화 또는 방향 반전",
        "• Apple 중국 주간 점유율이 기준 33%에서 ±3%p 이상 변화",
        "• Counterpoint·TrendForce Duo 전망이 기존 대비 100만대 이상 변경",
        "• Duo 전망이 700만대 초과 또는 500만대 미만으로 이동",
        "• 10월16일 이후 Duo 예약·배송대기·개통은 기존 직접수요 모듈에서 별도 확인",
        "",
        f'<a href="{COUNTERPOINT_DUO_REUTERS}">Reuters · Counterpoint Duo 약 600만대</a>',
        f'<a href="{TRENDFORCE_DUO}">TrendForce · Duo 약 500만대</a>',
        f'<a href="{COUNTERPOINT_CHINA_PRO_OFFICIAL}">Counterpoint 공식 · 중국 첫 3일 판매 +12%, 점유율 33%</a>',
        f'<a href="{COUNTERPOINT_PRO_PANEL_OFFICIAL}">Counterpoint 공식 · Pro 패널 조달 누적 +2% 추적</a>',
        f'<a href="{COUNTERPOINT_CHINA_CONTEXT}">Counterpoint · 중국 시장 수요 배경</a>',
        f'<a href="{COUNTERPOINT_THREE_WEEK_OFFICIAL}">Counterpoint · 첫 3주 국가별 자료</a>',
        f'<a href="{APPLE_OFFICIAL}">Apple 공식 일정</a>',
    ]) + "\n"


def _change_alert(signals: list[dict]) -> str:
    best = max(signals, key=lambda s: (s["stage"], s["rank"], s["item"]["published_at_kst"]))
    stage_text = "🟠 전망 재평가" if int(best["stage"]) >= 2 else "🟡 프리미엄 수요 선행 변화"
    selected = sorted(
        signals,
        key=lambda s: (s["stage"], s["rank"], s["item"]["published_at_kst"]),
        reverse=True,
    )[:3]

    lines = [
        "🍎 <b>[Apple 프리미엄 수요·Duo 전망 변화]</b>",
        "━━━━━━━━━━━━━━━━",
        f"• <b>{stage_text}</b>",
    ]
    for signal in selected:
        item = signal["item"]
        lines.append("• " + html.escape(" / ".join(signal["reasons"])))
        lines.append(f"  └ {html.escape(item['source'])} · {html.escape(item['published_at_kst'])}")

    lines += [
        "",
        "<b>[해석 규칙]</b>",
        "• iPhone 18 Pro 중국 판매는 Duo 직접수요가 아니라 Apple 프리미엄 수요 선행지표입니다.",
        "• 기관 전망은 실제 판매·발주가 아니라 전망치입니다.",
        "• Duo 직접 수요는 10월16일 사전주문 이후 기존 직접수요 모듈에서 별도로 판단합니다.",
        "",
    ]
    for signal in selected:
        item = signal["item"]
        lines.append(f'<a href="{html.escape(item["link"], quote=True)}">원문 · {html.escape(item["source"])}</a>')
    lines.append(f'<a href="{APPLE_OFFICIAL}">Apple 공식 일정</a>')
    return "\n".join(lines) + "\n"


def _append_alert(alert: str) -> None:
    existing = MAIN_ALERT_PATH.read_text(encoding="utf-8").strip() if MAIN_ALERT_PATH.exists() else ""
    if existing:
        MAIN_ALERT_PATH.write_text(existing + "\n\n━━━━━━━━━━━━━━━━\n\n" + alert, encoding="utf-8")
    else:
        MAIN_ALERT_PATH.write_text(alert, encoding="utf-8")


def main() -> None:
    now = dt.datetime.now(KST)
    state = _load_state()
    seen = set(state.get("seen") or [])
    metrics = dict(BASELINE)
    metrics.update(state.get("metrics") or {})
    correction_due = _needs_scope_correction(state)
    if correction_due or state.get("false_china_scope_correction_sent"):
        metrics["iphone18pro_china_yoy_pct"] = BASELINE["iphone18pro_china_yoy_pct"]
    # Official source status supersedes the initial paid-tracker-only note, even
    # when an old state was saved by a previous release. This is metadata, not
    # a fresh sell-through/change signal.
    for key in (
        "iphone18pro_confirmation",
        "iphone18pro_three_weeks_confirmation",
        "iphone18pro_panel_cumulative_through_oct_yoy_pct",
        "iphone18pro_panel_confirmation",
    ):
        metrics[key] = BASELINE[key]
    items, errors = collect()
    signals: list[dict] = []

    initial_pending = not bool(state.get("initial_alert_sent"))
    if not initial_pending:
        for item in items:
            fid = _fingerprint(item)
            if fid in seen:
                continue
            signal = _signal(item, {**state, "metrics": metrics})
            seen.add(fid)
            if signal:
                signals.append(signal)
                metrics.update(signal.get("changes") or {})
    else:
        # Absorb current search results into the baseline so today's already-known
        # figures do not immediately replay as a second alert after the baseline.
        for item in items:
            seen.add(_fingerprint(item))

    pending = {
        "schema_version": 1,
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "initial_alert_sent": True,
        "false_china_scope_correction_sent": bool(
            state.get("false_china_scope_correction_sent") or correction_due
        ),
        "seen_fact_keys": sorted(set(state.get("seen_fact_keys") or []) |
            ({SCOPE_ERROR_CORRECTION_KEY} if correction_due else set())),
        "scope_correction_audit": (
            {
                "incorrect_message_id": 352,
                "wrong_claim": "China first 3 days +12% to global first 3 weeks +3.1%",
                "china_first3days_pct": 12.0,
                "china_first3weeks_pct": 29.0,
                "world_first3weeks_pct": 3.1,
                "corrected_at_kst": now.isoformat(timespec="seconds")
            } if correction_due else state.get("scope_correction_audit")
        ),
        "preorder_at_kst": APPLE_PREORDER_KST.isoformat(timespec="seconds"),
        "launch_date": APPLE_LAUNCH_DATE.isoformat(),
        "seen": sorted(seen)[-600:],
        "metrics": metrics,
        "confirmations": {
            "iphone18pro_china": BASELINE["iphone18pro_confirmation"],
            "iphone18pro_panel": BASELINE["iphone18pro_panel_confirmation"],
            "counterpoint_duo": BASELINE["counterpoint_duo_confirmation"],
            "trendforce_duo": BASELINE["trendforce_duo_confirmation"],
        },
        "last_scan_items": len(items),
        "last_signal_count": len(signals),
        "last_correction_count": int(correction_due),
        "last_alert": (
            {
                "at_kst": now.isoformat(timespec="seconds"),
                "kind": "scope_correction" if correction_due
                        else "baseline" if initial_pending else "change",
            }
            if initial_pending or signals or correction_due
            else state.get("last_alert")
        ),
    }
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if initial_pending:
        alert = _baseline_alert(metrics)
        FRAGMENT_PATH.write_text(alert, encoding="utf-8")
        _append_alert(alert)
    elif correction_due or signals:
        chunks=[]
        if correction_due:
            chunks.append(_scope_correction_alert())
        if signals:
            chunks.append(_change_alert(signals))
        alert="\n\n━━━━━━━━━━━━━━━━\n\n".join(chunks)
        FRAGMENT_PATH.write_text(alert, encoding="utf-8")
        _append_alert(alert)
    elif FRAGMENT_PATH.exists():
        FRAGMENT_PATH.unlink()

    STATUS_PATH.write_text(
        "# Apple premium demand / Duo forecast watch\n"
        f"- checked_at_kst: {now.isoformat(timespec='seconds')}\n"
        f"- items: {len(items)}\n"
        f"- new_signals: {len(signals)}\n"
        f"- initial_alert_pending: {str(initial_pending).lower()}\n"
        f"- iphone18pro_china_yoy_pct: {metrics.get('iphone18pro_china_yoy_pct')}\n"
        f"- apple_china_week38_share_pct: {metrics.get('apple_china_week38_share_pct')}\n"
        f"- iphone18pro_panel_cumulative_through_oct_yoy_pct: {metrics.get('iphone18pro_panel_cumulative_through_oct_yoy_pct')}\n"
        f"- counterpoint_duo_forecast_m: {metrics.get('counterpoint_duo_forecast_m')}\n"
        f"- trendforce_duo_forecast_m: {metrics.get('trendforce_duo_forecast_m')}\n"
        f"- errors: {len(errors)}\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
