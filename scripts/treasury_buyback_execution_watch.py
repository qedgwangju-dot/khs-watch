#!/usr/bin/env python3
"""Execution-only Treasury long-end buyback watcher.

Owns only official execution results for nominal 10Y-20Y / 20Y-30Y
liquidity-support buybacks. Policy announcements/schedule changes and
full auction/WI-tail analysis remain in their existing separate watchers.
"""
from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "out"

STATE = DATA / "treasury_buyback_media_state.json"
NEXT_STATE = DATA / "treasury_buyback_media_state_next.json"
ALERT = OUT / "treasury_buyback_media_alert.html"
TITLE = OUT / "treasury_buyback_media_title.txt"
DETAIL = OUT / "treasury_buyback_media_detail.json"
STATUS = OUT / "treasury_buyback_media_status.md"

FORMAT_REVISION = 13

# Official structured source. The public HTML results page is JS-rendered and
# previously caused a missed 2026-09-10 result, so execution fingerprints must
# come from Fiscal Data instead.
BUYBACK_API = (
    "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/"
    "accounting/od/buybacks_operations?sort=-operation_date&page%5Bsize%5D=12"
)
BUYBACK_RESULTS_PAGE = (
    "https://www.treasurydirect.gov/auctions/announcements-data-results/buy-backs/"
)
BUYBACK_FAQ = "https://www.treasurydirect.gov/help-center/faqs/buyback-faqs/"
TREASURY_AUCTION_API = (
    "https://www.treasurydirect.gov/TA_WS/securities/auctioned?"
    "format=json&days=400"
)
TREASURY_AUCTION_QUERY = "https://www.treasurydirect.gov/auctions/auction-query/"
TREASURY_YIELD_PAGE = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "TextView?type=daily_treasury_yield_curve"
)

SEP10_INFOMAX = "https://news.einfomax.co.kr/news/articleView.html?idxno=4434361"
SEP10_BLOOMBERG = (
    "https://www.bloomberg.com/news/articles/2026-09-10/"
    "bessent-dismisses-concern-on-buyback-says-treasuries-are-strong"
)
SEP10_REUTERS = (
    "https://www.reuters.com/legal/transactional/"
    "edgy-bond-investors-unconsoled-by-bessents-big-buyback-2026-09-10/"
)
SEP10_WSJ = (
    "https://www.wsj.com/livecoverage/stock-market-today-dow-sp-500-nasdaq-09-10-2026/"
    "card/treasury-yields-rise-further-after-buybacks-fall-short-of-6-billion-"
    "80SkvHXBE1bsv02PjDet"
)

LONG_END_BUCKETS = {"10Y to 20Y", "20Y to 30Y"}


def fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 khs-watch/3.1"})
    errors = []
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                return response.read().decode("utf-8", errors="replace")
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"자료 조회 실패: {url} / {' | '.join(errors)}")


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _num(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "").replace("$", ""))
    except Exception:
        return None


def latest_fx():
    from fx_api import daily_krw
    q = daily_krw()
    return q.rate, q.basis


def fmt_krw_from_usd(usd: float, fx: float) -> str:
    krw = usd * fx
    if krw >= 1_000_000_000_000:
        return f"약 {krw / 1_000_000_000_000:,.2f}조원"
    if krw >= 100_000_000:
        return f"약 {krw / 100_000_000:,.0f}억원"
    if krw >= 10_000:
        return f"약 {krw / 10_000:,.0f}만원"
    return f"약 {krw:,.0f}원"


def fmt_usd_krw(usd: float | None, fx: float) -> str:
    if usd is None:
        return "확인 불가"
    return f"${usd:,.0f}({fmt_krw_from_usd(usd, fx)})"


def _api_rows() -> list[dict]:
    payload = json.loads(fetch_text(BUYBACK_API))
    rows = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise RuntimeError("Fiscal Data 바이백 API 형식이 예상과 다릅니다.")
    return [row for row in rows if isinstance(row, dict)]


def _is_long_end(row: dict) -> bool:
    return (
        str(row.get("operation_type") or "").strip().lower() == "liquidity support"
        and str(row.get("security_type") or "").strip().lower() == "nominal coupons"
        and str(row.get("maturity_bucket") or "").strip() in LONG_END_BUCKETS
        and _num(row.get("total_par_amt_accepted")) is not None
    )


def latest_long_end_result() -> dict:
    rows = [row for row in _api_rows() if _is_long_end(row)]
    if not rows:
        raise RuntimeError("공식 Fiscal Data에서 장기 명목채 바이백 결과를 찾지 못했습니다.")
    rows.sort(key=lambda row: str(row.get("operation_date") or ""), reverse=True)
    return rows[0]


def result_fingerprint(row: dict) -> str:
    payload = {
        "operation_date": str(row.get("operation_date") or ""),
        "operation_type": str(row.get("operation_type") or ""),
        "security_type": str(row.get("security_type") or ""),
        "maturity_bucket": str(row.get("maturity_bucket") or ""),
        "max": _num(row.get("max_par_amt_redeemed")),
        "offered": _num(row.get("total_par_amt_offered")),
        "accepted": _num(row.get("total_par_amt_accepted")),
        "results_pdf": str(row.get("results_pdf") or ""),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _is_30y_bond(row: dict) -> bool:
    """Nominal 30-year bond only; exclude all inflation-indexed securities."""
    st = str(row.get("securityType") or row.get("SecurityType") or row.get("type") or "").strip().lower()
    if st != "bond":
        return False
    if any(str(row.get(key) or "").strip().lower() in {"yes", "true", "y", "t", "1"}
           for key in ("inflationIndexSecurity", "inflation_index_security", "Tips", "tips")):
        return False
    raw = (row.get("securityTerm") or row.get("term") or "",
           row.get("originalSecurityTerm") or "")
    terms = {"".join(ch for ch in str(t).lower() if ch.isalnum()) for t in raw}
    return bool(terms.intersection({"30year", "29year10month", "29year11month"}))


def _share(row: dict, key: str) -> float | None:
    accepted = _num(row.get("competitiveAccepted"))
    value = _num(row.get(key))
    if not accepted or value is None:
        return None
    return value / accepted * 100.0


def _date10(value) -> str:
    text = str(value or "").strip()
    return text[:10]


def latest_30y_auction_context(op_date: str) -> dict | None:
    """Latest official 30Y auction on or before the buyback operation date."""
    try:
        rows = json.loads(fetch_text(TREASURY_AUCTION_API))
    except Exception:
        return None
    if not isinstance(rows, list):
        return None

    bonds = [row for row in rows if isinstance(row, dict) and _is_30y_bond(row)]
    bonds.sort(key=lambda row: _date10(row.get("auctionDate")), reverse=True)
    current = next(
        (
            row for row in bonds
            if _date10(row.get("auctionDate"))
            and _date10(row.get("auctionDate")) <= op_date
        ),
        None,
    )
    if not current:
        return None

    current_date = _date10(current.get("auctionDate"))
    previous = [
        row for row in bonds
        if _date10(row.get("auctionDate")) < current_date
    ][:6]

    def avg(field: str) -> float | None:
        values = [_num(row.get(field)) for row in previous]
        clean = [v for v in values if v is not None]
        return sum(clean) / len(clean) if clean else None

    def avg_share(field: str) -> float | None:
        values = [_share(row, field) for row in previous]
        clean = [v for v in values if v is not None]
        return sum(clean) / len(clean) if clean else None

    return {
        "auction_date": current_date,
        "high_yield": _num(current.get("highYield")),
        "btc": _num(current.get("bidToCoverRatio")),
        "indirect_pct": _share(current, "indirectBidderAccepted"),
        "direct_pct": _share(current, "directBidderAccepted"),
        "dealer_pct": _share(current, "primaryDealerAccepted"),
        "avg_btc_6": avg("bidToCoverRatio"),
        "avg_indirect_pct_6": avg_share("indirectBidderAccepted"),
        "avg_direct_pct_6": avg_share("directBidderAccepted"),
        "avg_dealer_pct_6": avg_share("primaryDealerAccepted"),
        "sample_n": len(previous),
    }


def _treasury_yield_xml_url(year: str) -> str:
    return (
        "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
        f"?data=daily_treasury_yield_curve&field_tdr_date_value={year}"
    )


def official_curve_rows(year: str) -> list[dict]:
    raw = fetch_text(_treasury_yield_xml_url(year))
    root = ET.fromstring(raw)
    rows: list[dict] = []
    for props in root.findall(".//{*}properties"):
        row = {"date": None, "2y": None, "10y": None, "20y": None, "30y": None}
        for child in list(props):
            name = child.tag.split("}")[-1]
            text = (child.text or "").strip()
            if name == "NEW_DATE":
                row["date"] = text[:10]
            elif name == "BC_2YEAR" and text:
                row["2y"] = float(text)
            elif name == "BC_10YEAR" and text:
                row["10y"] = float(text)
            elif name == "BC_20YEAR" and text:
                row["20y"] = float(text)
            elif name == "BC_30YEAR" and text:
                row["30y"] = float(text)
        if row["date"] and all(row[k] is not None for k in ("2y", "10y", "20y", "30y")):
            rows.append(row)
    rows.sort(key=lambda x: x["date"])
    return rows


def official_yield_reaction(op_date: str) -> dict | None:
    """Official Treasury CMT close for the operation date versus prior business day."""
    try:
        rows = official_curve_rows(op_date[:4])
    except Exception:
        return None
    idx = next((i for i, row in enumerate(rows) if row["date"] == op_date), None)
    if idx is None or idx == 0:
        return None
    cur, prev = rows[idx], rows[idx - 1]
    changes = {
        key: (cur[key] - prev[key]) * 100.0
        for key in ("2y", "10y", "20y", "30y")
    }
    s210_cur = (cur["10y"] - cur["2y"]) * 100.0
    s210_prev = (prev["10y"] - prev["2y"]) * 100.0
    s230_cur = (cur["30y"] - cur["2y"]) * 100.0
    s230_prev = (prev["30y"] - prev["2y"]) * 100.0
    return {
        "date": op_date,
        "prev_date": prev["date"],
        "current": cur,
        "previous": prev,
        "changes_bp": changes,
        "d2s10s_bp": s210_cur - s210_prev,
        "d2s30s_bp": s230_cur - s230_prev,
    }


def _yield_verdict(reaction: dict) -> str:
    c = reaction["changes_bp"]
    longs = [c["10y"], c["20y"], c["30y"]]
    if all(x < 0 for x in longs):
        return "🟢 장기금리 하락 — 바이백 수급 방향과 같은 쪽"
    if all(x > 0 for x in longs):
        return "🔴 장기금리 상승 — 바이백 수급 완충보다 다른 상승 압력이 우세"
    return "🟡 장기금리 혼조 — 바이백 효과를 한 방향으로 판정하기 어려움"


def yield_reaction_lines(op_date: str) -> tuple[list[str], dict | None]:
    reaction = official_yield_reaction(op_date)
    if not reaction:
        return [
            "<b>집행 당일 금리 결과</b>",
            "• 미 재무부 공식 일일 CMT가 아직 해당 운영일 종가를 게시하지 않았습니다.",
            "• 공식값이 게시되면 같은 기존 감시에서 2년·10년·20년·30년 종가와 전일 대비 bp를 1회 후속 전송합니다.",
            f'<a href="{TREASURY_YIELD_PAGE}">미 재무부 공식 금리</a>',
        ], None

    cur = reaction["current"]
    c = reaction["changes_bp"]
    d210 = reaction["d2s10s_bp"]
    d230 = reaction["d2s30s_bp"]
    return [
        "<b>집행 당일 금리 결과 — 미 재무부 공식 CMT(약 오후 3:30 ET)</b>",
        (
            f"• 2년 {cur['2y']:.2f}% ({c['2y']:+.1f}bp) | "
            f"10년 {cur['10y']:.2f}% ({c['10y']:+.1f}bp) | "
            f"20년 {cur['20y']:.2f}% ({c['20y']:+.1f}bp) | "
            f"30년 {cur['30y']:.2f}% ({c['30y']:+.1f}bp)"
        ),
        f"• 비교 기준: 전 영업일({reaction['prev_date']})의 같은 공식 CMT 스냅샷",
        f"• 2년-10년 금리차 변화 {d210:+.1f}bp | 2년-30년 금리차 변화 {d230:+.1f}bp",
        f"• 판정: <b>{_yield_verdict(reaction)}</b>",
        "• CMT는 거래소 종가가 아니라 뉴욕연은이 각 거래일 약 오후 3:30 ET에 수집한 지표성 매수호가를 바탕으로 재무부가 산출한 금리입니다. 일중 고점·저점은 별도 시장자료로 확인합니다.",
        "• 주의: 같은 날 금리 변화에는 연준 발언·물가·유가·재정·국채 공급 등도 함께 작용하므로 바이백만의 인과효과로 단정하지 않습니다.",
        f'<a href="{TREASURY_YIELD_PAGE}">미 재무부 공식 금리</a>',
    ], reaction


def next_long_end_operation(after_date: str) -> dict | None:
    try:
        rows = _api_rows()
    except Exception:
        return None
    candidates = []
    for row in rows:
        if (
            str(row.get("operation_type") or "").strip().lower() == "liquidity support"
            and str(row.get("security_type") or "").strip().lower() == "nominal coupons"
            and str(row.get("maturity_bucket") or "").strip() in LONG_END_BUCKETS
        ):
            d = _date10(row.get("operation_date"))
            if d and d > after_date:
                candidates.append(row)
    if not candidates:
        return None
    candidates.sort(key=lambda row: _date10(row.get("operation_date")))
    return candidates[0]


def _fmt_cmp(value: float | None, average: float | None, suffix: str = "", places: int = 1) -> str:
    if value is None:
        return "확인 불가"
    out = f"{value:.1f}{suffix}"
    if average is not None:
        out += f" (직전 6회 평균 {average:.1f}{suffix}, {value-average:+.1f}{suffix})"
    return out


def classify_execution(
    cap_use: float | None,
    offer_cap: float | None,
    offer_accept: float | None,
) -> tuple[str, str]:
    if cap_use is None:
        return "⚪", "집행 강도 확인 불가"

    if cap_use >= 99.95:
        return "🟢", "상한 전액 집행"
    if cap_use >= 95:
        return "🟢", "상한 거의 전액 집행"
    if cap_use >= 80 and offer_cap is not None and offer_cap >= 1.25:
        return "🟡", "매도 제시는 충분했지만 가격 선별로 상한 일부 미소진"
    if cap_use >= 60:
        return "🟡", "상한의 과반 이상 집행 — 제시 강도와 가격을 함께 확인"
    if offer_accept is not None and offer_accept >= 1.5:
        return "🟡", "제시는 많았지만 재무부가 가격을 강하게 선별"
    return "🔴", "확대된 상한 대비 실제 집행·제시 모두 약함"


def auction_lines(op_date: str) -> list[str]:
    auction = latest_30y_auction_context(op_date)
    if not auction:
        return [
            "<b>최근 30년물 신규 공급 대조군</b>",
            "• 공식 TreasuryDirect 결과를 이번 실행에서 결합하지 못했습니다. 별도 미국 국채 입찰 알림의 공식 판정을 우선합니다.",
            f'<a href="{TREASURY_AUCTION_QUERY}">미 재무부 30년물 입찰</a>',
        ]

    btc = auction.get("btc")
    indirect = auction.get("indirect_pct")
    dealer = auction.get("dealer_pct")
    avg_btc = auction.get("avg_btc_6")
    avg_indirect = auction.get("avg_indirect_pct_6")
    avg_dealer = auction.get("avg_dealer_pct_6")

    if (
        btc is not None
        and avg_btc is not None
        and indirect is not None
        and avg_indirect is not None
        and dealer is not None
        and avg_dealer is not None
    ):
        if btc >= avg_btc and indirect >= avg_indirect - 1.0 and dealer <= avg_dealer:
            verdict = "🟢 최종수요 강함"
        elif btc < avg_btc and indirect < avg_indirect and dealer > avg_dealer:
            verdict = "🔴 최종수요 약함"
        else:
            verdict = "🟡 혼조"
    else:
        verdict = "⚪ 일부 지표 확인 불가"

    high_yield = auction.get("high_yield")
    return [
        f"<b>최근 30년물 신규 공급 대조군 — {auction.get('auction_date')}</b>",
        (
            f"• High Yield: {high_yield:.3f}%"
            if high_yield is not None
            else "• High Yield: 확인 불가"
        ),
        f"• 응찰배율: {_fmt_cmp(btc, avg_btc, '배', 2)}",
        f"• 간접낙찰: {_fmt_cmp(indirect, avg_indirect, '%')}",
        f"• Primary Dealer 인수: {_fmt_cmp(dealer, avg_dealer, '%')}",
        f"• 판정: <b>{verdict}</b>",
        "• WI 꼬리는 이 결합 알림에서 임의 계산하지 않고 기존 미국 국채 입찰 알림의 WI 판정을 우선합니다.",
        f'<a href="{TREASURY_AUCTION_QUERY}">미 재무부 30년물 입찰</a>',
    ]



def official_yield_persistence(op_date: str, offset_days: int) -> dict | None:
    """Official CMT on the +N Treasury business-day observation after a buyback."""
    try:
        rows = official_curve_rows(op_date[:4])
    except Exception:
        return None
    idx = next((i for i, row in enumerate(rows) if row["date"] == op_date), None)
    if idx is None or idx == 0 or idx + offset_days >= len(rows):
        return None
    base = rows[idx]
    pre = rows[idx - 1]
    target = rows[idx + offset_days]
    since_op = {
        key: (target[key] - base[key]) * 100.0
        for key in ("2y", "10y", "20y", "30y")
    }
    since_pre = {
        key: (target[key] - pre[key]) * 100.0
        for key in ("2y", "10y", "20y", "30y")
    }
    return {
        "operation_date": op_date,
        "offset_business_days": offset_days,
        "target_date": target["date"],
        "operation": base,
        "pre_operation": pre,
        "target": target,
        "since_operation_bp": since_op,
        "since_pre_operation_bp": since_pre,
    }


def build_persistence_followup(op_date: str, offset_days: int, reaction: dict) -> tuple[str, str, dict]:
    target = reaction["target"]
    since_op = reaction["since_operation_bp"]
    since_pre = reaction["since_pre_operation_bp"]
    long_moves = [since_op[k] for k in ("10y", "20y", "30y")]
    if all(x <= 0.1 for x in long_moves) and any(x < -0.1 for x in long_moves):
        verdict = "🟢 집행 뒤 장기금리 하락·보합"
    elif all(x >= -0.1 for x in long_moves) and any(x > 0.1 for x in long_moves):
        verdict = "🔴 집행 뒤 장기금리 상승·보합"
    else:
        verdict = "🟡 집행 뒤 장기금리 방향 혼조"

    title = (
        f"📊 미 재무부 장기물 바이백 +{offset_days}영업일 금리 추적 — "
        f"10년 {target['10y']:.2f}%·30년 {target['30y']:.2f}%"
    )
    body = "\n".join([
        "<b>🎯 바이백 이후 금리 지속성</b>",
        f"• 바이백 운영일: {op_date} · 확인일: {reaction['target_date']} (+{offset_days}영업일)",
        (
            f"• 현재 CMT: 2년 {target['2y']:.2f}% | 10년 {target['10y']:.2f}% | "
            f"20년 {target['20y']:.2f}% | 30년 {target['30y']:.2f}%"
        ),
        (
            f"• 운영일 대비: 2년 {since_op['2y']:+.1f}bp | 10년 {since_op['10y']:+.1f}bp | "
            f"20년 {since_op['20y']:+.1f}bp | 30년 {since_op['30y']:+.1f}bp"
        ),
        (
            f"• 운영 전 영업일 대비 누적: 2년 {since_pre['2y']:+.1f}bp | "
            f"10년 {since_pre['10y']:+.1f}bp | 20년 {since_pre['20y']:+.1f}bp | "
            f"30년 {since_pre['30y']:+.1f}bp"
        ),
        f"• 판정: <b>{verdict}</b>",
        "• CMT는 거래소 종가가 아니라 뉴욕연은이 각 거래일 약 오후 3:30 ET에 수집한 지표성 매수호가를 바탕으로 재무부가 산출한 금리입니다.",
        "• 이 추적은 바이백 뒤 시장 방향의 지속성을 보는 것이며, 금리 변화를 바이백 하나의 인과효과로 단정하지 않습니다.",
        f'<a href="{TREASURY_YIELD_PAGE}">미 재무부 공식 금리</a>',
    ])
    return title, body, {
        "mode": "yield_persistence_followup",
        "operation_date": op_date,
        "offset_business_days": offset_days,
        "reaction": reaction,
        "checked_kst": datetime.now(KST).isoformat(timespec="seconds"),
    }

def build_yield_followup(op_date: str, reaction: dict) -> tuple[str, str, dict]:
    lines, _ = yield_reaction_lines(op_date)
    cur = reaction["current"]
    title = (
        "📉 미 재무부 장기물 바이백 당일 CMT 확인 — "
        f"10년 {cur['10y']:.2f}%·30년 {cur['30y']:.2f}%"
    )
    body = "\n".join(
        [
            "<b>🎯 바이백 집행 후 공식 CMT 확인</b>",
            f"• 운영일: {op_date}",
            *lines,
            "",
            "<b>해석</b>",
            "• 이것은 바이백이 금리를 단독으로 움직였다는 인과판정이 아니라, 같은 거래일의 공식 수익률곡선 결과입니다.",
            "• 이후 +1·+3·+5 영업일 지속성은 기존 금리곡선 감시에서 이어서 확인합니다.",
        ]
    )
    return title, body, {
        "mode": "yield_followup",
        "operation_date": op_date,
        "reaction": reaction,
        "checked_kst": datetime.now(KST).isoformat(timespec="seconds"),
    }


def build_alert(row: dict, fx: float, fx_date: str) -> tuple[str, str, dict]:
    op_date = _date10(row.get("operation_date"))
    bucket = str(row.get("maturity_bucket") or "장기물")
    maximum = _num(row.get("max_par_amt_redeemed"))
    offered = _num(row.get("total_par_amt_offered"))
    accepted = _num(row.get("total_par_amt_accepted"))

    cap_use = accepted / maximum * 100 if maximum and accepted is not None else None
    accept_pct = accepted / offered * 100 if offered and accepted is not None else None
    offer_cap = offered / maximum if maximum and offered is not None else None
    offer_accept = offered / accepted if accepted and offered is not None else None
    unfilled = maximum - accepted if maximum and accepted is not None else None

    icon, verdict = classify_execution(cap_use, offer_cap, offer_accept)
    title = (
        f"{icon} 미 재무부 장기물 바이백 실제 집행 — "
        f"{accepted/1e9:.3f}B 매입·상한 {cap_use:.1f}% 사용"
        if accepted is not None and cap_use is not None
        else "🇺🇸 미 재무부 장기물 바이백 — 실제 집행 결과 변경"
    )

    lines = [
        "<b>🎯 핵심 판단</b>",
        f"{icon} <b>{verdict}</b>",
        "• 60억달러는 사전 최대 한도이고, 이번에 실제 사들인 금액은 51억8,700만달러입니다." if op_date == "2026-09-10" else f"• 공식 Fiscal Data의 {op_date} 실제 집행 결과입니다.",
        "",
        "<b>실제 집행 숫자</b>",
        f"• 대상: {bucket} · {op_date}",
        f"• 총 제시액: {fmt_usd_krw(offered, fx)}",
        f"• 실제 매입액: <b>{fmt_usd_krw(accepted, fx)}</b>",
        f"• 매입상한: {fmt_usd_krw(maximum, fx)}",
    ]

    if cap_use is not None:
        lines.append(f"• 상한 소진율: <b>{cap_use:.1f}%</b>")
    if unfilled is not None:
        lines.append(f"• 미사용 한도: {fmt_usd_krw(unfilled, fx)}")
    if offer_accept is not None:
        lines.append(f"• 매도 제시배율(제시액÷실제 매입액): <b>{offer_accept:.2f}배</b>")
    if offer_cap is not None:
        lines.append(f"• 제시액÷상한: {offer_cap:.2f}배")
    if accept_pct is not None:
        lines.append(f"• 제시액 대비 실제 매입률: {accept_pct:.1f}%")

    if op_date == "2026-09-10":
        lines += [
            "",
            "<b>왜 60억달러를 다 안 샀나</b>",
            "• 제시액 104억8,900만달러는 60억달러 상한의 약 1.75배였습니다. 즉 ‘팔려는 물량 자체가 상한보다 부족해서’ 51.87억달러에 그친 것은 아닙니다.",
            "• 재무부 규정은 시장가격·상대가치가 적절한 제시만 받아들이며, 공고액보다 적게 사거나 전혀 사지 않을 권리를 명시합니다.",
            "• 따라서 이번 86.5% 집행은 <b>제시 부족과 가격 선별을 분리</b>해 읽어야 합니다.",
            "",
            "<b>베센트 설명 vs 시장 해석</b>",
            "• 베센트: 최근 10년·30년 입찰 수요가 강했고 국채시장은 양호하다고 평가. 이번에는 장기채 보유자의 매도 의지가 낮아 제시액이 평소보다 적었다는 설명입니다.",
            "• 시장: 사전 80억~100억달러 기대보다 60억달러 상한이 작았고, 실제 매입도 51.87억달러에 그쳐 금리 안정 신호가 약했다는 해석입니다.",
            "• 두 해석은 동시에 가능하지만, 총 제시액만으로 ‘국채 최종수요 악화’ 또는 ‘보유자의 강한 확신’을 단정하지 않습니다.",
        ]

    rate_lines, reaction = yield_reaction_lines(op_date)
    op_start = str(row.get("operation_start_time_est") or "").strip()
    op_close = str(row.get("operation_close_time_est") or "").strip()
    if op_start and op_close and reaction:
        rate_lines.insert(
            1,
            f"• 바이백 운영 {op_start}~{op_close} ET 종료 후 약 오후 3:30 ET의 공식 CMT 스냅샷입니다.",
        )
    lines += [""] + rate_lines
    lines += [""] + auction_lines(op_date)

    next_op = next_long_end_operation(op_date)
    if next_op:
        next_text = (
            f"⑤ 다음 장기물 바이백 — {_date10(next_op.get('operation_date'))} "
            f"{next_op.get('maturity_bucket')}"
        )
    else:
        next_text = "⑤ 다음 장기물 바이백 — 미 재무부 공식 예정 일정 재확인"

    lines += [
        "",
        "<b>다음 판정</b>",
        "① 집행 당일 공식 금리 — 위 CMT 결과",
        "② +1·+3·+5 영업일 10·20·30년 금리 지속성",
        "③ 다음 30년 신규 입찰 — 간접낙찰·딜러 인수·Bid-to-Cover·별도 WI 꼬리",
        "④ 결제일 TGA와 이후 Bill·CMB 공급 — 장기물 부담이 단기물로 이동하는지",
        next_text,
        "",
        "<b>실패 경로</b>",
        "• 상한을 크게 늘리고 실제 매입도 충분한데 10·30년 금리가 계속 오른다면, 유동성보다 유가·인플레이션·재정 공급·기간 프리미엄이 더 강한 국면으로 판정합니다.",
        "",
        f"환율 기준: {fx_date}, 1달러={fx:,.2f}원",
    ]

    source_links = [
        f'<a href="{BUYBACK_RESULTS_PAGE}">미 재무부 공식 바이백 결과</a>',
        f'<a href="{BUYBACK_FAQ}">바이백 규정</a>',
        f'<a href="{TREASURY_YIELD_PAGE}">미 재무부 공식 금리</a>',
        f'<a href="{TREASURY_AUCTION_QUERY}">미 재무부 국채 입찰</a>',
    ]
    if op_date == "2026-09-10":
        source_links += [
            f'<a href="{SEP10_INFOMAX}">연합인포맥스</a>',
            f'<a href="{SEP10_BLOOMBERG}">베센트 발언</a>',
            f'<a href="{SEP10_REUTERS}">시장 검증</a>',
        ]
    lines.append(" · ".join(source_links))

    body = "\n".join(lines)
    detail = {
        "mode": "execution_results_only",
        "format_revision": FORMAT_REVISION,
        "source": "Fiscal Data Treasury Securities Buybacks API",
        "operation": row,
        "metrics": {
            "cap_use_pct": cap_use,
            "accept_pct": accept_pct,
            "offer_cap_ratio": offer_cap,
            "offer_accept_ratio": offer_accept,
            "unfilled_cap": unfilled,
        },
        "execution_strength": verdict,
        "official_yield_reaction": reaction,
        "fx": fx,
        "fx_date": fx_date,
        "checked_kst": datetime.now(KST).isoformat(timespec="seconds"),
    }
    return title, body, detail


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    for path in (ALERT, TITLE, DETAIL):
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    state = load_state()
    row = latest_long_end_result()
    fingerprint = result_fingerprint(row)
    checked = datetime.now(KST).isoformat(timespec="seconds")
    op_date = _date10(row.get("operation_date"))

    old_fingerprint = state.get("latest_long_end_fingerprint")
    is_new = old_fingerprint != fingerprint
    force_format_resend = (
        int(state.get("format_revision", 0) or 0) < FORMAT_REVISION
        and state.get("latest_long_end_operation_date") == op_date
    )
    should_alert = (is_new or force_format_resend) and (
        old_fingerprint is not None or op_date >= "2026-09-10"
    )

    next_state = {
        **state,
        "last_checked_kst": checked,
        "latest_long_end_fingerprint": fingerprint,
        "latest_long_end_operation_date": op_date,
        "format_revision": FORMAT_REVISION,
        "results_source": "fiscaldata_buybacks_operations",
    }

    watches = list(state.get("yield_persistence_watches", []) or [])
    if not any(
        str(w.get("fingerprint") or "") == fingerprint
        for w in watches
        if isinstance(w, dict)
    ):
        watches.append({
            "operation_date": op_date,
            "fingerprint": fingerprint,
            "completed_offsets": [],
        })
    watches = [w for w in watches if isinstance(w, dict)][-10:]
    next_state["yield_persistence_watches"] = watches

    alert_kind = None
    if should_alert:
        fx, fx_date = latest_fx()
        title, body, detail = build_alert(row, fx, fx_date)
        text_length = len(title) + 2 + len(body)
        if text_length > 4096:
            raise RuntimeError(f"Telegram message too long: {text_length}")
        TITLE.write_text(title + "\n", encoding="utf-8")
        ALERT.write_text(body.rstrip() + "\n", encoding="utf-8")
        DETAIL.write_text(
            json.dumps(detail, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        reaction = detail.get("official_yield_reaction")
        if reaction:
            next_state.pop("pending_yield_followup", None)
            next_state["latest_yield_followup_operation_date"] = op_date
        else:
            next_state["pending_yield_followup"] = {
                "operation_date": op_date,
                "fingerprint": fingerprint,
            }
        next_state["pending_items"] = [
            f"buyback:{op_date}:{row.get('maturity_bucket')}:{fingerprint}:fmt{FORMAT_REVISION}"
        ]
        alert_kind = "execution"

    if not should_alert:
        pending = state.get("pending_yield_followup") or {}
        pending_date = str(pending.get("operation_date") or "")
        if pending_date and pending_date == op_date:
            reaction = official_yield_reaction(pending_date)
            if reaction:
                title, body, detail = build_yield_followup(pending_date, reaction)
                if len(title) + 2 + len(body) > 4096:
                    raise RuntimeError("Telegram yield-followup message too long")
                TITLE.write_text(title + "\n", encoding="utf-8")
                ALERT.write_text(body.rstrip() + "\n", encoding="utf-8")
                DETAIL.write_text(
                    json.dumps(detail, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                next_state.pop("pending_yield_followup", None)
                next_state["latest_yield_followup_operation_date"] = pending_date
                next_state["pending_items"] = [
                    f"buyback-yield:{pending_date}:{fingerprint}"
                ]
                alert_kind = "yield_followup"

    if not should_alert and alert_kind is None:
        sent_persistence = False
        for watch in watches:
            watch_date = str(watch.get("operation_date") or "")
            watch_fp = str(watch.get("fingerprint") or "")
            completed = [int(x) for x in (watch.get("completed_offsets") or [])]
            for offset_days in (1, 3, 5):
                if offset_days in completed:
                    continue
                reaction = official_yield_persistence(watch_date, offset_days)
                if not reaction:
                    continue
                title, body, detail = build_persistence_followup(
                    watch_date, offset_days, reaction
                )
                if len(title) + 2 + len(body) > 4096:
                    raise RuntimeError("Telegram persistence-followup message too long")
                TITLE.write_text(title + "\n", encoding="utf-8")
                ALERT.write_text(body.rstrip() + "\n", encoding="utf-8")
                DETAIL.write_text(
                    json.dumps(detail, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                completed.append(offset_days)
                watch["completed_offsets"] = sorted(set(completed))
                next_state["yield_persistence_watches"] = watches
                next_state["pending_items"] = [
                    f"buyback-yield-persistence:{watch_date}:+{offset_days}:{watch_fp}"
                ]
                alert_kind = f"yield_persistence_+{offset_days}"
                sent_persistence = True
                break
            if sent_persistence:
                break

    NEXT_STATE.write_text(
        json.dumps(next_state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    STATUS.write_text(
        "# 미 재무부 장기물 바이백 실제 집행 점검\n\n"
        f"- 조회시각: {checked}\n"
        f"- 최신 운영일: {op_date}\n"
        f"- 만기구간: {row.get('maturity_bucket')}\n"
        f"- 공식 데이터원: Fiscal Data buybacks_operations\n"
        f"- 신규 실제 집행: {'예' if should_alert else '아니오'}\n"
        f"- 공식 금리 후속: {'예' if alert_kind == 'yield_followup' else '아니오'}\n"
        f"- 이번 알림 종류: {alert_kind or '없음'}\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
