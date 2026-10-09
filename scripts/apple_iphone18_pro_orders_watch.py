#!/usr/bin/env python3
"""Track iPhone 18 Pro / Pro Max component-order revisions, separately from Duo.

Production guardrails:
- Nikkei's 2026-10-09 report, reprinted by Reuters/Investing/Newsquawk, is ONE
  sourcing root, not three independent confirmations.
- "15-20% October component orders vs original supplier request" is a
  manufacturing PROCUREMENT signal, not a 15-20% reduction in iPhone retail
  sales, global shipments, or every supplier's revenue.
- IDC 2026 annual -16.7% shipments / +27.6% ASP is an August FORECAST,
  not an Apple October order cut and not a new IDC publication.
- China week-38 iPhone 18 Pro +12% sell-through (unverified paid-tracker data)
  and later October plan changes can coexist. Never let the number migrate
  between subject, region, date, metric or comparison basis.
- Another article quoting the Nikkei story is not a new fact.
- State changes are staged and confirmed by the existing Telegram workflow.
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
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "apple_iphone18_pro_orders_state.json"
OUT_DIR = ROOT / "out"
OUT_DIR.mkdir(exist_ok=True)
PENDING_PATH = OUT_DIR / "apple_iphone18_pro_orders_pending_state.json"
STATUS_PATH = OUT_DIR / "apple_iphone18_pro_orders_status.md"
FRAGMENT_PATH = OUT_DIR / "apple_iphone18_pro_orders_alert.html"
MAIN_ALERT_PATH = OUT_DIR / "apple_duo_supply_watch_telegram.txt"
KST = ZoneInfo("Asia/Seoul")
REPORT_DATE = dt.date(2026, 10, 9)

REUTERS = "https://www.reuters.com/business/retail-consumer/apple-cuts-iphone-18-pro-orders-due-soft-demand-nikkei-asia-reports-2026-10-09/"
NIKKEI_REPRINT = "https://ca.investing.com/news/stock-market-news/apple-cuts-iphone18-pro-component-orders-amid-sluggish-demand-nikkei-4872814"
APPLE_PRICE = "https://www.apple.com/newsroom/2026/09/apple-debuts-iphone-18-pro-and-iphone-18-pro-max/"
IDC = "https://www.idc.com/resource-center/blog/smartphone-shipments-set-for-record-16-7-drop-in-2026-as-the-memory-crisis-hits-full-force/"
DUO_OFFICIAL = "https://www.apple.com/kr/iphone-duo/"
SOURCE_ROOT = "nikkei_2026_10_09_supplier_interviews"
BASELINE_FACT = "iphone18_pro_pro_max|2026-10|component_orders|original_requested_plan|cut_15_to_20|nikkei_2026_10_09"
BASELINE = {
    "reported_at": "2026-10-09",
    "products": ["iPhone 18 Pro", "iPhone 18 Pro Max"],
    "period": "2026-10",
    "measure": "component_purchase_orders",
    "comparison": "originally requested October supplier volumes",
    "reported_cut_low_pct": 15.0,
    "reported_cut_high_pct": 20.0,
    "reuters_confirmed_floor": 15.0,
    "reuters_independent_confirmation": False,
    "source_root": SOURCE_ROOT,
    "certainty": "니케이 공급망 취재 보도·Reuters 독립 확인 실패·Apple 공식 미확인",
    "named_supplier_orders_confirmed": [],
    "actual_finished_device_sales_cut_confirmed": False,
    "idc_2026_worldwide_shipments_yoy_forecast_pct": -16.7,
    "idc_2026_worldwide_asp_yoy_forecast_pct": 27.6,
    "idc_publication_date": "2026-08-26",
    "apple_us_pro_price_usd": 1199,
    "apple_us_pro_max_price_usd": 1299,
    "china_week38_sales_yoy_pct_user_provided": 12.0,
    "china_week38_direct_tracker_publicly_verified": False,
    "ubs_delivery_lead_time_publicly_verified": False,
}

QUERIES = [
    ("en", '"iPhone 18 Pro" "component orders" "October" cut Nikkei'),
    ("en", '"iPhone 18 Pro Max" supplier production orders reduced October'),
    ("en", '"iPhone 18 Pro" Nikkei order cuts 15 20 percent suppliers'),
    ("en", '"iPhone 18 Pro" Foxconn camera OLED panel component orders November'),
    ("en", '"iPhone 18 Pro" UBS delivery lead times demand October'),
    ("ko", '"아이폰 18 프로" 10월 부품 발주 주문 감축 니케이'),
    ("ko", '"아이폰18 프로 맥스" 생산 주문 감소 15% 20%'),
    ("ko", '"아이폰 18 프로" LG이노텍 삼성디스플레이 부품 주문 축소'),
]

HIGH_SOURCES = ("nikkei", "reuters", "bloomberg", "financial times",
                "wall street journal", "wsj", "the information", "ubs")
MID_SOURCES = ("investing.com", "newsquawk", "digitimes", "the elec",
               "전자신문", "etnews", "zdnet", "매일경제", "한국경제",
               "서울경제", "파이낸셜뉴스", "연합뉴스", "yonhap")
LOW_SOURCES = ("notebookcheck", "wccftech", "reddit", "note.com", "technobezz")

PRO_RE = re.compile(
    r"(?:iphone\s*18\s*pro(?:\s*max)?|iphone18\s*pro(?:\s*max)?"
    r"|아이폰\s*18\s*프로(?:\s*맥스)?|아이폰18\s*프로(?:\s*맥스)?)",
    re.I,
)
COMPONENT_WORDS = ("component", "parts", "suppliers", "supplier",
                   "oled", "display", "panel", "camera", "modules", "memory",
                   "lpddr", "nand", "foxconn", "부품", "공급사", "공급망",
                   "패널", "카메라", "메모리", "조립")
ORDER_WORDS = ("orders", "order", "p.o.", "purchase", "production",
               "build", "생산", "주문", "발주", "요청", "조달")
CUT_WORDS = ("cut", "cuts", "slashed", "slash", "reduced", "reduce",
             "lowered", "lower", "trimmed", "trim", "감축", "삭감", "축소",
             "하향", "줄이", "줄였", "감소")
BASIS_WORDS = ("original", "originally", "planned", "initial",
               "requested", "previous plan", "기존", "당초", "원래",
               "기존 계획", "초기 요청", "초기 계획")
SCOPE_WORDS = {
    "LG이노텍": ("lg innotek", "lg이노텍"),
    "삼성디스플레이": ("samsung display", "삼성디스플레이"),
    "Foxconn": ("foxconn", "폭스콘", "hon hai", "홍하이"),
    "비에이치": ("비에이치", "bh electronics"),
    "SK하이닉스": ("sk hynix", "sk하이닉스"),
    "삼성전자 메모리": ("samsung memory", "삼성전자 메모리"),
}
UA = "Mozilla/5.0 (compatible; khs-iphone18pro-orders-watch/1.0)"

def _fetch(url: str, timeout: int = 22) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA,
        "Accept": "application/rss+xml,application/xml,text/xml,*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def _clean(value: str | None) -> str:
    raw = html.unescape(value or "")
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw)).strip()

def _parse_date(raw: str) -> dt.datetime | None:
    try:
        parsed = parsedate_to_datetime(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(KST)
    except Exception:
        return None

def _rank(source: str) -> int:
    low = _clean(source).lower()
    if any(x in low for x in LOW_SOURCES):
        return 0
    if any(x in low for x in HIGH_SOURCES):
        return 3
    if any(x in low for x in MID_SOURCES):
        return 2
    return 1

def _fingerprint(item: dict) -> str:
    raw = f"{_clean(item.get('title'))}|{_clean(item.get('source'))}".lower()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

def _root(item: dict) -> str:
    blob = (str(item.get("title") or "") + " " +
            str(item.get("description") or "") + " " +
            str(item.get("source") or "")).lower()
    if "nikkei" in blob or "니케이" in blob or "日经" in blob or "日経" in blob:
        return SOURCE_ROOT
    return "independent_root_unverified"

def _period_near(text: str) -> str | None:
    low = text.lower()
    months = []
    for label, keys in (
        ("2026-10", ("october", "oct.", "10월", "十月", "10月份")),
        ("2026-11", ("november", "nov.", "11월", "十一月", "11月份")),
        ("2026-12", ("december", "dec.", "12월", "十二月", "12月份")),
        ("2027-01", ("january", "jan.", "1월", "一月", "1月份")),
    ):
        if any(k in low for k in keys):
            months.append(label)
    return months[0] if len(months) == 1 else None

def _extract_cut(text: str) -> dict | None:
    """Typed numerical cut: Pro component orders, explicit period AND basis."""
    low = _clean(text).lower()
    if not PRO_RE.search(low):
        return None
    if not any(w in low for w in COMPONENT_WORDS):
        return None
    if not any(w in low for w in ORDER_WORDS):
        return None
    if not any(w in low for w in CUT_WORDS):
        return None
    if not any(w in low for w in BASIS_WORDS):
        return None
    period = _period_near(low)
    if period is None:
        return None
    range_pattern = re.compile(
        r"(?<!\d)(\d{1,2}(?:\.\d+)?)\s*%\s*(?:-|~|–|—|to|and|에서|부터)\s*"
        r"(\d{1,2}(?:\.\d+)?)\s*%", re.I,
    )
    candidates: list[tuple[int, float, float]] = []
    for m in range_pattern.finditer(low):
        left, right = float(m.group(1)), float(m.group(2))
        if 5 <= left <= right <= 60:
            candidates.append((m.start(), left, right))
    for m in re.finditer(r"(?<!\d)(\d{1,2}(?:\.\d+)?)\s*%", low):
        val = float(m.group(1))
        if not 5 <= val <= 60 or any(a <= m.start() < a + 24 for a, _, _ in candidates):
            continue
        candidates.append((m.start(), val, val))
    for pos, low_pct, high_pct in sorted(candidates):
        snippet = low[max(0, pos - 125): min(len(low), pos + 85)]
        # Reject an unrelated IDC shipping drop or global ASP increase.
        if not any(w in snippet for w in CUT_WORDS):
            continue
        if not any(w in snippet for w in ORDER_WORDS):
            continue
        if not any(w in snippet for w in COMPONENT_WORDS):
            continue
        return {"period": period, "low": low_pct, "high": high_pct,
                "basis": "original_supplier_request"}
    return None

def _known_baseline_repeat(cut: dict, item: dict) -> bool:
    if cut["period"] != "2026-10":
        return False
    # The same October 15-20% source can be republished as "at least 15%"
    # or a standalone "20%" or "15-20%" by many publishers.
    within = 15 <= cut["low"] <= 20 and 15 <= cut["high"] <= 20
    if within:
        return True
    return False

def _fact_key(cut: dict, item: dict) -> str:
    return (
        f"iphone18_pro_family|{cut['period']}|component_orders|"
        f"{cut['basis']}|cut_{cut['low']:g}_{cut['high']:g}|{_root(item)}"
    )

def _relevant_news(item: dict, state: dict) -> dict | None:
    rank = _rank(item.get("source") or "")
    if rank < 2:
        return None
    blob = f"{item.get('title','')} {item.get('description','')}"
    cut = _extract_cut(blob)
    if cut is None:
        return None
    if _known_baseline_repeat(cut, item):
        return None
    previously = (state.get("metrics") or {}).get("reported_baseline") or BASELINE
    if cut["period"] == "2026-10":
        delta = max(abs(cut["low"] - 15), abs(cut["high"] - 20))
        if delta < 5:
            return None
    fact = _fact_key(cut, item)
    if fact in set(state.get("seen_fact_keys") or []):
        return None
    # A publisher only repeating the original Nikkei story is no second source.
    return {"item": item, "cut": cut, "rank": rank, "fact_key": fact,
            "source_root": _root(item), "stage": 2 if rank == 3 else 1}

def _rss(lang: str, query: str) -> str:
    args = {"q": query, "hl": "ko" if lang == "ko" else "en-US",
            "gl": "KR" if lang == "ko" else "US",
            "ceid": "KR:ko" if lang == "ko" else "US:en"}
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(args)

def collect() -> tuple[list[dict], list[str]]:
    now = dt.datetime.now(KST)
    earliest = now - dt.timedelta(days=21)
    rows: dict[str, dict] = {}
    errors: list[str] = []
    for lang, query in QUERIES:
        try:
            root = ET.fromstring(_fetch(_rss(lang, query)))
        except Exception as exc:
            errors.append(f"{lang}:{type(exc).__name__}")
            continue
        for node in root.findall(".//item"):
            title = _clean(node.findtext("title"))
            desc = _clean(node.findtext("description"))
            link = _clean(node.findtext("link"))
            source_node = node.find("source")
            source = _clean(source_node.text if source_node is not None else "")
            date = _parse_date(_clean(node.findtext("pubDate")))
            if not title or not link or not date or date < earliest or date > now + dt.timedelta(minutes=15):
                continue
            if not PRO_RE.search(f"{title} {desc}"):
                continue
            item = {"title": title, "description": desc, "link": link,
                    "source": source or "출처 미표시",
                    "published_at_kst": date.isoformat(timespec="seconds")}
            rows[_fingerprint(item)] = item
    return sorted(rows.values(), key=lambda r: r["published_at_kst"]), errors

def _load_state() -> dict:
    if STATE_PATH.exists():
        try:
            data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("initial_alert_sent"), bool):
                raise ValueError("unexpected schema")
            data.setdefault("seen", [])
            data.setdefault("seen_fact_keys", [])
            data.setdefault("metrics", {})
            return data
        except Exception as exc:
            raise RuntimeError("Pro order state damaged — stop instead of resending baseline") from exc
    return {"schema_version": 1, "initial_alert_sent": False,
            "baseline_at_kst": "2026-10-09T15:05:00+09:00",
            "seen": [], "seen_fact_keys": [BASELINE_FACT],
            "metrics": {"reported_baseline": BASELINE},
            "last_alert": None}

def _fx_info() -> tuple[str, str]:
    """No unconverted foreign-currency numbers when FX sources fail."""
    try:
        from fx_api import daily_krw
        quote = daily_krw("USD")
        lines = (
            f"• 미국 공식 시작가: Pro 1,199달러(약 {1199*quote.rate:,.0f}원), "
            f"Pro Max 1,299달러(약 {1299*quote.rate:,.0f}원)\n"
            f"• 전작 대비 모델별 100달러(약 {100*quote.rate:,.0f}원) 인상\n"
            f"• 원화 환산 기준: 1달러={quote.rate:,.2f}원, {quote.date} "
            f"({quote.source}; {quote.check})"
        )
        return lines, "confirmed"
    except Exception as exc:
        return "• 공식 미국 출고가 원화 환산은 환율 검증 실패로 표기 보류", type(exc).__name__

def _baseline_alert(fx_text: str) -> str:
    lines = [
        "📱 <b>[Apple iPhone 18 Pro·Pro Max 부품 발주 감축 | 최초 기준선]</b>",
        "━━━━━━━━━━━━━━━━",
        "<b>[확인된 보도 범위]</b>",
        "• <b>2026년 10월</b> 두 모델용 <b>일부 공급사 부품 주문</b>: "
        "당초 요청 물량보다 <b>15~20% 축소</b>됐다는 니케이아시아 공급망 보도",
        "• Reuters의 직접 재확인 범위는 <b>최소 15% 감축</b>; "
        "상단 20%는 동일 니케이 보도를 인용한 매체에서 확인됩니다.",
        "• <b>Apple 공식 확인 및 독립 공급사별 감축 공시는 없음.</b> "
        "Reuters도 원보도를 독립적으로 확인하지 못했다고 명시했습니다.",
        "• 11월 이후 추가 감축/복원, 총 주문 대수와 협력사별 물량은 미공개.",
        "",
        "<b>[가격·연간 시장과 분리]</b>",
        fx_text,
        "• IDC의 2026년 전 세계 스마트폰 출하 -16.7%·평균판매단가 +27.6%는 "
        "<b>8월 26일 전망치</b>이며 오늘 Apple 감축의 추가 검증 증거가 아닙니다.",
        "• 중국 38주차 iPhone 18 Pro 초기 판매 +12%는 사용자 제공 "
        "Counterpoint 유료 지표로 공개 원표 미열람. "
        "지역·시점·실판매와 부품발주를 섞지 않습니다.",
        "",
        "<b>[현재 판정]</b>",
        "🟠 <b>중요한 공급망 발주 감축 보도, 공식 미확정</b>",
        "• <b>완제품 판매 -15~20% 확정이 아닙니다.</b> "
        "부품 발주량을 Apple 전체 판매/매출 감소율로 환산하지 않습니다.",
        "• 납품 대상·검수·재고·가격 조정에 따라 개별 공급사 실적 민감도가 달라집니다.",
        "",
        "<b>[다음 확인 조건]</b>",
        "• 11~12월 Pro·Pro Max 실제 부품 발주 추가 하향/복원",
        "• Foxconn 조립 물량, 삼성디스플레이 OLED, LG이노텍 카메라 등 "
        "협력사 실명·물량·영향 범위의 독립 확인",
        "• UBS 배송기간의 국가별 원자료 및 예약·개통량 추세",
        "• 10월 16일 예약 개시 예정인 iPhone Duo의 실제 주문은 <b>별개</b>로 확인",
        "",
        f'<a href="{REUTERS}">Reuters · 니케이 보도 인용(독립확인 실패)</a>',
        f'<a href="{NIKKEI_REPRINT}">니케이 15~20% 재전달 보도</a>',
        f'<a href="{APPLE_PRICE}">Apple 공식 Pro 출고가</a>',
        f'<a href="{IDC}">IDC 8월 글로벌 시장 전망</a>',
        f'<a href="{DUO_OFFICIAL}">Apple 공식 Duo 출시 일정</a>',
    ]
    return "\n".join(lines) + "\n"

def _change_alert(changes: list[dict]) -> str:
    lines = [
        "📱 <b>[Apple iPhone 18 Pro 부품 발주 | 후속 변동]</b>",
        "━━━━━━━━━━━━━━━━",
        "🟠 <b>추가 공급망 발주 조정 보도·계약 확정 여부 미확인</b>",
    ]
    for signal in changes:
        item, cut = signal["item"], signal["cut"]
        lines.append(
            f"• {cut['period']} Pro 계열 부품 발주 조정 "
            f"{cut['low']:g}~{cut['high']:g}% (당초 공급사 요청 대비)"
        )
        lines.append(
            f"  └ {html.escape(item['source'])} · {html.escape(item['published_at_kst'])}"
        )
        lines.append(
            f'<a href="{html.escape(item["link"], quote=True)}">해당 보도</a>'
        )
    lines += [
        "• 동일 니케이 원보도 재인용은 별도의 독립 확인으로 세지 않습니다.",
        "• 부품 발주, 완제품 생산, 소비자 실판매 및 회사 매출을 분리합니다.",
    ]
    return "\n".join(lines) + "\n"

def _append_alert(alert: str) -> None:
    existing = MAIN_ALERT_PATH.read_text(encoding="utf-8").strip() if MAIN_ALERT_PATH.exists() else ""
    # Append last in the existing workflow. The sender already supports line
    # splitting and every HTML line here closes its own tags.
    if existing:
        MAIN_ALERT_PATH.write_text(existing + "\n\n━━━━━━━━━━━━━━━━\n\n" + alert,
                                   encoding="utf-8")
    else:
        MAIN_ALERT_PATH.write_text(alert, encoding="utf-8")

def main() -> None:
    now = dt.datetime.now(KST)
    state = _load_state()
    seen = set(state.get("seen") or [])
    fact_keys = set(state.get("seen_fact_keys") or [])
    fact_keys.add(BASELINE_FACT)
    items, errors = collect()
    if not items and len(errors) == len(QUERIES):
        raise RuntimeError("All iPhone 18 Pro news feeds unavailable: fail closed")
    is_initial = not state["initial_alert_sent"]
    updates: list[dict] = []
    if not is_initial:
        for item in items:
            fid = _fingerprint(item)
            if fid in seen:
                continue
            seen.add(fid)
            signal = _relevant_news(item, {**state, "seen_fact_keys": list(fact_keys)})
            if signal and signal["fact_key"] not in fact_keys:
                updates.append(signal)
                fact_keys.add(signal["fact_key"])
    else:
        seen.update(_fingerprint(item) for item in items)

    fx_status = "not_needed"
    if is_initial:
        fx_line, fx_status = _fx_info()
        alert = _baseline_alert(fx_line)
    elif updates:
        alert = _change_alert(updates[:3])
    else:
        alert = ""
    pending = {
        "schema_version": 1,
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "initial_alert_sent": True,
        "baseline_at_kst": state.get("baseline_at_kst") or "2026-10-09T15:05:00+09:00",
        "seen": sorted(seen)[-700:],
        "seen_fact_keys": sorted(fact_keys)[-400:],
        "metrics": state.get("metrics") or {"reported_baseline": BASELINE},
        "last_scan_items": len(items),
        "feed_errors": errors[-20:],
        "new_signal_count": len(updates),
        "last_alert": (
            {"at_kst": now.isoformat(timespec="seconds"),
             "kind": "baseline" if is_initial else "follow_up"}
            if alert else state.get("last_alert")
        ),
        "fx_verification": fx_status,
    }
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if alert:
        FRAGMENT_PATH.write_text(alert, encoding="utf-8")
        _append_alert(alert)
    else:
        FRAGMENT_PATH.unlink(missing_ok=True)
    STATUS_PATH.write_text(
        "# iPhone 18 Pro·Pro Max 부품 발주 감시\n"
        f"- checked_at_kst: {now.isoformat(timespec='seconds')}\n"
        f"- items: {len(items)}\n"
        f"- feed_errors: {len(errors)}\n"
        f"- first_alert_pending: {str(is_initial).lower()}\n"
        f"- new_signals: {len(updates)}\n"
        f"- fx_verification: {fx_status}\n"
        f"- alert_generated: {str(bool(alert)).lower()}\n",
        encoding="utf-8",
    )

if __name__ == "__main__":
    main()
