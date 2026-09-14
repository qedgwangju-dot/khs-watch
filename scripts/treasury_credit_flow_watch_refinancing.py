#!/usr/bin/env python3
import datetime as dt
import html
import re

import requests

import treasury_credit_flow_watch_marketstress as stress

app = stress.app
readable = stress.readable
_original_raw_send = stress._original_raw_send

MSPD_DETAIL_URL = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/debt/mspd/mspd_table_3_market"
MSPD_SUMMARY_URL = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/debt/mspd/mspd_table_1"


def _num(value):
    if value in (None, "", "null"):
        return 0.0
    try:
        return float(str(value).replace(",", ""))
    except Exception:
        return 0.0


def _date(value):
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except Exception:
        return None


def _get_rows(url, params):
    r = requests.get(url, params=params, headers=app.base.HEADERS, timeout=(8, 30))
    r.raise_for_status()
    payload = r.json()
    rows = payload.get("data") or []
    if not rows:
        raise RuntimeError("Treasury MSPD returned no rows")
    return rows


def _get_summary(record_date):
    rows = _get_rows(MSPD_SUMMARY_URL, {
        "filter": f"record_date:eq:{record_date}",
        "sort": "-record_date,src_line_nbr",
        "page[number]": 1,
        "page[size]": 50,
    })
    bills_mil = None
    total_mil = None
    for row in rows:
        if str(row.get("record_date") or "")[:10] != record_date:
            continue
        if row.get("security_type_desc") == "Marketable" and row.get("security_class_desc") == "Bills":
            bills_mil = _num(row.get("total_mil_amt"))
        elif row.get("security_type_desc") == "Total Marketable":
            total_mil = _num(row.get("total_mil_amt"))
    if not bills_mil or not total_mil:
        raise RuntimeError("Treasury MSPD table 1 summary totals missing")
    return total_mil, bills_mil


def get_refinancing_snapshot():
    latest_row = _get_rows(MSPD_DETAIL_URL, {"sort": "-record_date", "page[number]": 1, "page[size]": 1})[0]
    record_date = str(latest_row.get("record_date") or "")[:10]
    rd = _date(record_date)
    if rd is None:
        raise RuntimeError("Treasury MSPD latest record_date parse failed")

    # Use Table I for current stock totals. Table III contains issue/reopening detail and
    # subtotal-style rows, so summing every outstanding_amt overstates the current stock.
    total_mil, bills_mil = _get_summary(record_date)

    rows = _get_rows(MSPD_DETAIL_URL, {
        "filter": f"record_date:eq:{record_date}",
        "sort": "-record_date,maturity_date",
        "page[number]": 1,
        "page[size]": 10000,
    })

    next12_mil = 0.0
    next12_bills_mil = 0.0
    by_year_mil = {2027: 0.0, 2028: 0.0}
    cutoff = rd + dt.timedelta(days=365)
    matched_rows = 0

    # Only rows with an actual future maturity date and a positive outstanding balance
    # enter the maturity schedule. This excludes Table III subtotal lines with null dates.
    for row in rows:
        if str(row.get("record_date") or "")[:10] != record_date:
            continue
        matched_rows += 1
        md = _date(row.get("maturity_date"))
        if md is None or md <= rd:
            continue
        outstanding = _num(row.get("outstanding_amt"))
        if outstanding <= 0:
            continue
        cls = str(row.get("security_class1_desc") or row.get("security_class_desc") or "")
        if cls in ("Total Marketable", "Federal Financing Bank"):
            continue
        is_bill = "bill" in cls.lower()
        if md <= cutoff:
            next12_mil += outstanding
            if is_bill:
                next12_bills_mil += outstanding
        if md.year in by_year_mil:
            by_year_mil[md.year] += outstanding

    if matched_rows <= 0 or next12_mil <= 0:
        raise RuntimeError("Treasury MSPD maturity aggregation failed")

    to_tril = lambda mil: mil / 1_000_000.0
    total_t = to_tril(total_mil)
    bills_t = to_tril(bills_mil)
    next12_t = to_tril(next12_mil)

    # All current Treasury bills mature within one year. Use the authoritative Table I
    # bill stock as the bill component and derive coupon/FRN/TIPS maturities as the residual.
    next12_bills_t = bills_t
    next12_coupon_t = max(0.0, next12_t - next12_bills_t)
    bill_share = bills_t / total_t * 100.0
    next12_share = next12_t / total_t * 100.0

    sensitivity_b = {
        25: bills_t * 1_000.0 * 0.0025,
        50: bills_t * 1_000.0 * 0.0050,
        75: bills_t * 1_000.0 * 0.0075,
    }

    return {
        "record_date": record_date,
        "matched_rows": matched_rows,
        "total_t": total_t,
        "bills_t": bills_t,
        "bill_share": bill_share,
        "next12_t": next12_t,
        "next12_share": next12_share,
        "next12_bills_t": next12_bills_t,
        "next12_coupon_t": next12_coupon_t,
        "y2027_t": to_tril(by_year_mil[2027]),
        "y2028_t": to_tril(by_year_mil[2028]),
        "sensitivity_b": sensitivity_b,
    }


def _yield_value(text, tenor):
    m = re.search(rf"^• {re.escape(tenor)}: ([0-9]+(?:\.[0-9]+)?)%", text, re.M)
    return float(m.group(1)) if m else None


def _refi_block(text):
    try:
        snap = get_refinancing_snapshot()
    except Exception:
        return (
            "차환·재정 민감도: 공식 MSPD 최신값 조회 실패 → 차환벽 판정 보류\n"
            "→ 기존 금리·ETF·OAS·G-R 판정은 계속 수행하고 차환 규모는 추정하지 않음"
        )

    y10 = _yield_value(text, "10년")
    y30 = _yield_value(text, "30년")
    if (y10 is not None and y10 >= 5.00) or (y30 is not None and y30 >= 5.30):
        state = "경계 — 높은 시장금리 속 대규모 차환"
    elif snap["next12_share"] >= 30:
        state = "주의 — 향후 12개월 만기 비중 매우 높음"
    elif snap["next12_share"] >= 20:
        state = "관찰 강화 — 향후 12개월 차환 비중 높음"
    else:
        state = "관찰 — 차환벽 상시 점검"

    s = snap["sensitivity_b"]
    return "\n".join([
        f"차환·재정 민감도: {state}",
        f"향후 12개월 만기: ${snap['next12_t']:.2f}T | 시장성 국채 ${snap['total_t']:.2f}T의 {snap['next12_share']:.1f}% | Bills ${snap['next12_bills_t']:.2f}T / 쿠폰물·기타 ${snap['next12_coupon_t']:.2f}T",
        f"현재 Bills: ${snap['bills_t']:.2f}T | 시장성 국채의 {snap['bill_share']:.1f}%",
        f"금리 민감도(Bills 단순 연율): +25bp ≈ +${s[25]:.1f}B/년 | +50bp ≈ +${s[50]:.1f}B/년 | +75bp ≈ +${s[75]:.1f}B/년",
        f"연도별 현재 잔존 만기: 2027 ${snap['y2027_t']:.2f}T | 2028 ${snap['y2028_t']:.2f}T",
        "→ 만기액은 신규 적자와 다름: 만기채는 대부분 재발행해 갈아타는 총차환 물량이고, 재정적자는 여기에 더해지는 순신규 조달 수요.",
        "→ Bills는 짧게 반복 차환돼 Fed 금리 변화가 이자비용에 빨리 반영. 쿠폰물은 만기 시점에 재가격되므로 전체 국가부채가 한꺼번에 같은 금리로 바뀌는 것은 아님.",
        "→ 민감도는 현재 Bills 잔액에 금리 변화폭을 단순 적용한 연율 추정이며 실제 현금 이자비용은 재발행 시점·만기구성·낙찰금리에 따라 달라짐.",
        f"자료 기준: U.S. Treasury MSPD {snap['record_date']} (월말 공식 잔액·만기표)",
    ])


def _insert_refi(text):
    block = _refi_block(text)
    marker = "\n자료 기준일:"
    if marker in text:
        return text.replace(marker, "\n\n" + block + marker, 1)
    return text + "\n\n" + block


def _format_html(chunk):
    out = []
    bold_prefixes = (
        "전체 방향:", "국채 자금:", "회사채 자금:", "신용 위험:",
        "성장-차입비용:", "기업이익:", "위험 전환 경보:",
        "금리:", "커브:", "2년-10년:", "10년-30년:",
        "오늘의 주도축:", "시장 기술압력:", "차환·재정 민감도:",
        "향후 12개월 만기:", "현재 Bills:", "금리 민감도(Bills 단순 연율):",
        "연도별 현재 잔존 만기:", "자료 기준일:",
        "전체 자금 방향:", "ETF 자금 방향:", "신용자금 방향:",
        "• 현재 형태:", "• 오늘의 주도축:", "• 신용 위험:",
    )
    for line in chunk.splitlines():
        escaped = html.escape(line, quote=False)
        bold = line in ("[한눈에 보기]", "[오늘의 결론]") or line.startswith(bold_prefixes)
        out.append(f"<b>{escaped}</b>" if bold else escaped)
    return "\n".join(out)


def send_refinancing(raw_text):
    text = readable.improve_overview(raw_text)
    text = stress._insert_market_stress(text)
    text = _insert_refi(text)
    (app.base.OUT / "treasury_etf_flow_telegram.txt").write_text(text + "\n", encoding="utf-8")
    (app.base.OUT / "treasury_etf_flow_status.md").write_text("```\n" + text + "\n```\n", encoding="utf-8")
    app.fmt_html = _format_html
    return _original_raw_send(text)


app.send_exact = send_refinancing


if __name__ == "__main__":
    app.main()
