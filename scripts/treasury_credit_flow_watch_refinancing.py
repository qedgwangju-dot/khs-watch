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
    rows = (r.json() or {}).get("data") or []
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
    bills_mil = total_mil = None
    for row in rows:
        if str(row.get("record_date") or "")[:10] != record_date:
            continue
        if row.get("security_type_desc") == "Marketable" and row.get("security_class_desc") == "Bills":
            bills_mil = _num(row.get("total_mil_amt"))
        elif row.get("security_type_desc") == "Total Marketable":
            total_mil = _num(row.get("total_mil_amt"))
    if not bills_mil or not total_mil:
        raise RuntimeError("Treasury MSPD summary totals missing")
    return total_mil, bills_mil


def get_refinancing_snapshot():
    latest = _get_rows(MSPD_DETAIL_URL, {
        "sort": "-record_date",
        "page[number]": 1,
        "page[size]": 1,
    })[0]
    record_date = str(latest.get("record_date") or "")[:10]
    rd = _date(record_date)
    if rd is None:
        raise RuntimeError("Treasury MSPD record date parse failed")

    total_mil, bills_mil = _get_summary(record_date)
    rows = _get_rows(MSPD_DETAIL_URL, {
        "filter": f"record_date:eq:{record_date}",
        "sort": "-record_date,maturity_date",
        "page[number]": 1,
        "page[size]": 10000,
    })

    cutoff = rd + dt.timedelta(days=365)
    next12_mil = 0.0
    by_year_mil = {2027: 0.0, 2028: 0.0}
    for row in rows:
        if str(row.get("record_date") or "")[:10] != record_date:
            continue
        md = _date(row.get("maturity_date"))
        if md is None or md <= rd:
            continue
        outstanding = _num(row.get("outstanding_amt"))
        if outstanding <= 0:
            continue
        cls = str(row.get("security_class1_desc") or "")
        if cls in ("Total Marketable", "Federal Financing Bank"):
            continue
        if md <= cutoff:
            next12_mil += outstanding
        if md.year in by_year_mil:
            by_year_mil[md.year] += outstanding

    to_t = lambda mil: mil / 1_000_000.0
    total_t = to_t(total_mil)
    bills_t = to_t(bills_mil)
    next12_t = to_t(next12_mil)
    coupon_t = max(0.0, next12_t - bills_t)
    return {
        "record_date": record_date,
        "total_t": total_t,
        "bills_t": bills_t,
        "bill_share": bills_t / total_t * 100.0,
        "next12_t": next12_t,
        "next12_share": next12_t / total_t * 100.0,
        "coupon_t": coupon_t,
        "y2027_t": to_t(by_year_mil[2027]),
        "y2028_t": to_t(by_year_mil[2028]),
        "plus75_b": bills_t * 1_000.0 * 0.0075,
    }


def _m(pattern, text, default="확인 대기"):
    m = re.search(pattern, text, re.M)
    return m.group(1).strip() if m else default


def _flow(ticker, text):
    m = re.search(
        rf"^{ticker} \([^\n]+\) — [^\n]+\n"
        rf"• 가격: [^\n]+\n"
        rf"• 일간 자금: ([^\n]+)\n"
        rf"• 최근 5회: ([^\n]+)",
        text,
        re.M,
    )
    if not m:
        return "확인 대기", "확인 대기"
    return m.group(1).strip(), m.group(2).strip()


def _oas(ticker, text):
    return _m(
        rf"^{ticker} \([^\n]+\) — [^\n]+\n"
        rf"• 가격: [^\n]+\n"
        rf"• 일간 자금: [^\n]+\n"
        rf"• 최근 5회: [^\n]+\n"
        rf"• 포트폴리오 OAS: ([^\n]+)",
        text,
    )


def _rate(tenor, text):
    return _m(rf"^• {re.escape(tenor)}: ([^\n]+)", text)


def _yield_value(text, tenor):
    m = re.search(rf"^• {re.escape(tenor)}: ([0-9]+(?:\.[0-9]+)?)%", text, re.M)
    return float(m.group(1)) if m else None


def _inflow(s):
    return "순유입" in s


def _outflow(s):
    return "순유출" in s


def _overall_direction(flows):
    shy, ief, tlt, lqd, hyg = [flows[x][0] for x in ("SHY", "IEF", "TLT", "LQD", "HYG")]
    if _inflow(ief) and _inflow(tlt) and _outflow(lqd) and _outflow(hyg):
        return (
            "회사채→중·장기 국채 이동·방어적",
            "IEF·TLT는 유입, LQD·HYG는 유출 → 장기금리 고점 베팅은 늘지만 기업 신용위험 노출은 줄이는 흐름",
        )
    if _inflow(shy) and _outflow(lqd) and _outflow(hyg):
        return "단기 국채 피신·품질 선호", "회사채에서 빠진 돈이 짧은 미 국채로 이동하는 방어적 흐름"
    if _inflow(lqd) and _inflow(hyg):
        return "신용 위험선호 회복", "투자등급·고수익 회사채에 자금이 함께 유입"
    return "혼조·추가 확인", "국채 만기 이동과 회사채 위험선호가 한 방향으로 완전히 정렬되지는 않음"


def _credit_summary(lqd_flow, hyg_flow, lqd_oas, hyg_oas):
    oas_widen = ("↑" in lqd_oas and "+0bp" not in lqd_oas) or ("↑" in hyg_oas and "+0bp" not in hyg_oas)
    if _outflow(lqd_flow) and _outflow(hyg_flow) and not oas_widen:
        return "선제 위험축소·신용경색 미확인", "LQD·HYG 자금은 빠지지만 OAS는 급확대하지 않아 아직 신용경색 단계는 아님"
    if _outflow(hyg_flow) and oas_widen:
        return "신용위험 경계 강화", "HYG 자금유출과 OAS 확대가 겹쳐 기업 신용위험이 실제 가격에 반영되기 시작"
    return "혼조", "자금흐름과 신용스프레드가 같은 방향인지 추가 확인"


def _compact_report(raw_text):
    flows = {t: _flow(t, raw_text) for t in ("SHY", "IEF", "TLT", "LQD", "HYG")}
    lqd_oas, hyg_oas = _oas("LQD", raw_text), _oas("HYG", raw_text)
    overall_head, overall_reason = _overall_direction(flows)
    credit_head, credit_reason = _credit_summary(flows["LQD"][0], flows["HYG"][0], lqd_oas, hyg_oas)

    r2, r10, r30 = _rate("2년", raw_text), _rate("10년", raw_text), _rate("30년", raw_text)
    s210 = _rate("2년-10년 금리차", raw_text)
    s1030 = _rate("10년-30년 금리차", raw_text)
    regime = _m(r"^• 현재 형태: ([^\n]+)", raw_text)
    easy = _m(r"^• 쉬운 해석: ([^\n]+)", raw_text)
    driver = _m(r"^• 오늘의 주도축: ([^\n]+)", raw_text)
    treasury_date = _m(r"^기준: ([0-9]{4}-[0-9]{2}-[0-9]{2}) \| 직전:", raw_text)

    y10, y30 = _yield_value(raw_text, "10년"), _yield_value(raw_text, "30년")
    tech_head, tech_reason = stress._market_stress(y10, y30)

    gr = readable.get_growth_cost_snapshot()
    if gr.get("ok"):
        gr_line = f"G-R: {gr['gap']:+.2f}%p | G {gr['g']:.2f}% vs R {gr['r']:.2f}% → {gr['state']}"
    else:
        gr_line = "G-R: 공식 최신값 조회 실패 → 판정 보류"

    try:
        refi = get_refinancing_snapshot()
        refi_line = (
            f"차환: 12개월 ${refi['next12_t']:.2f}T ({refi['next12_share']:.1f}%) | "
            f"Bills ${refi['bills_t']:.2f}T ({refi['bill_share']:.1f}%) | +75bp 단순 연율 +${refi['plus75_b']:.1f}B"
        )
        refi_date = refi["record_date"]
    except Exception:
        refi_line = "차환: MSPD 최신값 조회 실패 → 판정 보류"
        refi_date = "확인 대기"

    date_line = _m(r"^조회시각\(KST\): ([^\n]+)", raw_text)
    fx_line = _m(r"^환율: ([^\n]+)", raw_text)

    if credit_head.startswith("선제") and "앞단 Fed" in driver:
        conclusion = "앞단 Fed 압박은 강해졌지만 신용스프레드는 아직 버팀 → 현재는 금리 스트레스 + 선제 위험축소 단계"
    elif "신용위험 경계" in credit_head:
        conclusion = "금리 압박이 회사채 신용위험으로 번지는지 경계 강화"
    else:
        conclusion = overall_reason

    lines = [
        "[미 국채·회사채 방향성 일일 보고]",
        f"조회: {date_line}",
        f"환율: {fx_line}",
        "",
        "[한눈에 보기]",
        f"전체 방향: {overall_head}",
        f"→ {overall_reason}",
        "",
        f"국채 자금: SHY {flows['SHY'][0]} | IEF {flows['IEF'][0]} | TLT {flows['TLT'][0]}",
        f"회사채 자금: LQD {flows['LQD'][0]} | HYG {flows['HYG'][0]}",
        f"신용 위험: {credit_head} | LQD OAS {lqd_oas} | HYG OAS {hyg_oas}",
        f"→ {credit_reason}",
        "",
        f"금리: 2년 {r2} | 10년 {r10} | 30년 {r30}",
        f"커브: {regime} = {easy}",
        f"금리차: 2-10년 {s210} | 10-30년 {s1030}",
        f"오늘의 주도축: {driver}",
        "",
        f"시장 기술압력: {tech_head}",
        f"→ {tech_reason}",
        f"{gr_line}",
        f"{refi_line}",
        "",
        "[자금 상세 — 일간 / 최근 5회]",
        f"SHY: {flows['SHY'][0]} / {flows['SHY'][1]}",
        f"IEF: {flows['IEF'][0]} / {flows['IEF'][1]}",
        f"TLT: {flows['TLT'][0]} / {flows['TLT'][1]}",
        f"LQD: {flows['LQD'][0]} / {flows['LQD'][1]} | OAS {lqd_oas}",
        f"HYG: {flows['HYG'][0]} / {flows['HYG'][1]} | OAS {hyg_oas}",
        "",
        "[오늘의 결론]",
        conclusion,
        "다음 경보: 10년물 5% 돌파·HYG OAS 재확대·R>G 전환 여부",
        "",
        f"기준: ETF·미 재무부 {treasury_date} | MSPD {refi_date}",
        "출처: iShares · U.S. Treasury · Treasury FiscalData · BEA",
    ]
    return "\n".join(lines)


def _format_html(chunk):
    out = []
    bold_prefixes = (
        "전체 방향:", "국채 자금:", "회사채 자금:", "신용 위험:",
        "금리:", "커브:", "오늘의 주도축:", "시장 기술압력:",
        "G-R:", "차환:", "다음 경보:",
    )
    for line in chunk.splitlines():
        escaped = html.escape(line, quote=False)
        bold = line in ("[한눈에 보기]", "[자금 상세 — 일간 / 최근 5회]", "[오늘의 결론]") or line.startswith(bold_prefixes)
        out.append(f"<b>{escaped}</b>" if bold else escaped)
    return "\n".join(out)


def send_refinancing(raw_text):
    text = _compact_report(raw_text)
    (app.base.OUT / "treasury_etf_flow_telegram.txt").write_text(text + "\n", encoding="utf-8")
    (app.base.OUT / "treasury_etf_flow_status.md").write_text("```\n" + text + "\n```\n", encoding="utf-8")
    app.fmt_html = _format_html
    return _original_raw_send(text)


app.send_exact = send_refinancing


if __name__ == "__main__":
    app.main()
