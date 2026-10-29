#!/usr/bin/env python3
import datetime as dt
import html
import os
import re

import requests

import treasury_credit_flow_watch_marketstress as stress
import treasury_real_yield_signal as real_yield

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


def _ofr_points(mnemonic, days=45):
    start = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    r = requests.get(
        "https://data.financialresearch.gov/v1/series/full",
        params={"mnemonic": mnemonic, "start_date": start},
        headers=app.base.HEADERS,
        timeout=(8, 30),
    )
    r.raise_for_status()
    payload = r.json()

    found = []
    def walk(obj):
        if isinstance(obj, list):
            if obj and all(
                isinstance(x, list) and len(x) >= 2 and
                isinstance(x[0], str) and re.fullmatch(r"20\d{2}-\d{2}-\d{2}", x[0][:10])
                for x in obj
            ):
                for x in obj:
                    try:
                        found.append((x[0][:10], float(x[1])))
                    except Exception:
                        pass
            else:
                for x in obj:
                    walk(x)
        elif isinstance(obj, dict):
            for v in obj.values():
                walk(v)
    walk(payload)

    if not found:
        raise RuntimeError(f"OFR series empty: {mnemonic}")
    dedup = {}
    for d, v in found:
        dedup[d] = v
    return sorted(dedup.items())


def get_repo_stress():
    sofr = dict(_ofr_points("FNYR-SOFR-A"))
    tgcr = dict(_ofr_points("FNYR-TGCR-A"))
    common = sorted(set(sofr) & set(tgcr))
    if not common:
        raise RuntimeError("SOFR/TGCR common date missing")

    d = common[-1]
    prev_dates = [x for x in common if x < d]
    prev = prev_dates[-1] if prev_dates else None
    s = sofr[d]
    t = tgcr[d]
    spread_bp = (s - t) * 100.0
    move_bp = (s - sofr[prev]) * 100.0 if prev else 0.0

    # Internal monitoring bands. This is a compact funding-stress signal, not an official OFR label.
    if spread_bp >= 10 or move_bp >= 10:
        state = "스트레스"
    elif spread_bp >= 5 or move_bp >= 5:
        state = "주의"
    else:
        state = "안정"

    sign1 = "+" if spread_bp >= 0 else ""
    sign2 = "+" if move_bp >= 0 else ""
    return (
        f"Repo: {state} | SOFR {s:.2f}% / TGCR {t:.2f}% | "
        f"스프레드 {sign1}{spread_bp:.0f}bp | SOFR 전일 {sign2}{move_bp:.0f}bp | 기준 {d} (최신 공식 공표값)"
    )


def _jpm_30y_signal(y30):
    if y30 is None:
        return "JPM 30년 기술선: 확인 대기 | 공식 30년 금리 조회 실패"
    if y30 >= 6.00:
        state = "6.00% 이상 → 장기금리 극단 스트레스"
    elif y30 >= 5.78:
        state = "5.78% 이상 → JPM Equal Swings 약세 목표 구간"
    elif y30 >= 5.59:
        state = "5.59% 이상 → 채권 약세 구간(신규 돌파 여부는 공식 전일 종가 비교로 별도 판정)"
    elif y30 > 5.25:
        state = "5.59% 아래·5.25% 위 → 반전 미확인"
    elif y30 > 5.15:
        state = "5.25% 이하 유지 → 숏커버·CTA 전환 가능성"
    else:
        state = "5.15% 이하 유지 → 채권 반전 신호 강화"
    return (
        f"JPM 30년 기술선: 현재 {y30:.2f}% | {state} | "
        "상단 5.59→5.78→6.00 / 하단 5.25→5.15"
    )


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


def _oas_delta(oas_text):
    m = re.search(r"직전(?: 저장값)? 대비\s+[↑↓→]\s+([+-]?\d+(?:\.\d+)?)bp", oas_text or "")
    return float(m.group(1)) if m else None


def _oas_asof(oas_text):
    m = re.search(r"기준\s+(20\d{2}-\d{2}-\d{2})", oas_text or "")
    return m.group(1) if m else None


def _fund_date(ticker, text):
    m = re.search(
        rf"^{re.escape(ticker)} \([^\n]+\) — (20\d{{2}}-\d{{2}}-\d{{2}})",
        text or "",
        re.M,
    )
    return m.group(1) if m else None


def _rate_move_bp(rate_text):
    m = re.search(r"([+-]?\d+(?:\.\d+)?)bp", rate_text or "")
    return float(m.group(1)) if m else None


def _display_overall_head(head):
    labels = {
        "국채금리 하락·선행 신용경계": "장기 국채금리 하락 · 회사채 신용 경계",
        "국채금리 하락·신용경계": "장기 국채금리 하락 · 회사채 신용 경계",
        "장기금리 상승·선행 신용경계": "장기 국채금리 상승 · 회사채 신용 경계",
        "금리·신용 위험경계 강화": "장기 국채금리 상승 · 회사채 신용 경계",
        "금리 방향 혼조·선행 신용경계": "국채금리 혼조 · 회사채 신용 경계",
        "금리 방향 혼조·신용경계": "국채금리 혼조 · 회사채 신용 경계",
    }
    return labels.get(head, head)


def _flow_direction(flow):
    if _inflow(flow):
        return "유입"
    if _outflow(flow):
        return "유출"
    if "→" in flow and ("변화" in flow or "±$0" in flow):
        return "변화 없음"
    return "확인 대기"


def _period_flow_direction(flow):
    """Read the signed USD flow, including the wordless recent-five display."""
    if any(mark in flow for mark in ("확인 대기", "확인 불가", "미확인", "조회 실패")):
        return "확인 대기"
    amount = re.search(r"([+\-±]?)\$([+\-±]?)([0-9][0-9,]*(?:\.[0-9]+)?)", flow)
    if not amount:
        return "확인 대기"
    before, after, value = amount.groups()
    if before and after and before != after:
        return "확인 대기"
    sign = before or after
    value = float(value.replace(",", ""))
    if value == 0:
        return "변화 없음" if "→" in flow or sign == "±" else "확인 대기"
    if sign == "±":
        return "확인 대기"
    direction = "유출" if sign == "-" else "유입" if sign == "+" else _flow_direction(flow)
    if direction == "확인 대기":
        return direction
    word_direction = _flow_direction(flow)
    if word_direction in ("유입", "유출") and word_direction != direction:
        return "확인 대기"
    if ("↑" in flow and direction != "유입") or ("↓" in flow and direction != "유출"):
        return "확인 대기"
    return direction


def _flow_preference(flows, fund_dates, tickers, period, kind):
    dates = [fund_dates.get(ticker) for ticker in tickers]
    if not all(dates) or len(set(dates)) != 1:
        return "판단 보류 (ETF 기준일 미확인·불일치)"
    directions = tuple(_period_flow_direction(flows[ticker][period]) for ticker in tickers)
    if "확인 대기" in directions:
        return "판단 보류 (자금 자료 미확인)"
    if kind == "국채":
        if directions == ("유입", "유출", "유출"):
            return "짧은 만기 선호 신호"
        if directions == ("유출", "유입", "유입"):
            return "긴 만기 선호 신호"
        if len(set(directions)) == 1:
            return "전 만기 " + directions[0]
        return "만기별 혼조"
    if directions == ("유입", "유출"):
        return "투자등급 선호 신호"
    if directions == ("유출", "유입"):
        return "고수익 선호 신호"
    if len(set(directions)) == 1:
        return "투자등급·고수익 모두 " + directions[0]
    return f"투자등급 {directions[0]} · 고수익 {directions[1]}"


def _flow_interpretation_panel(flows, fund_dates):
    lines = []
    for kind, tickers in (("국채", ("SHY", "IEF", "TLT")), ("회사채", ("LQD", "HYG"))):
        day = _flow_preference(flows, fund_dates, tickers, 0, kind)
        recent = _flow_preference(flows, fund_dates, tickers, 1, kind)
        lines.append(f"{kind} 해석(ETF 추정): 당일 {day} / 최근 5회 {recent}")
    opposite = {("유출", "유입"): [], ("유입", "유출"): []}
    for ticker in ("SHY", "IEF", "TLT", "LQD", "HYG"):
        if not fund_dates.get(ticker):
            continue
        pair = tuple(_period_flow_direction(flow) for flow in flows[ticker])
        if pair in opposite:
            opposite[pair].append(ticker)
    contrasts = [
        f"{'·'.join(tickers)}는 당일 {day} / 최근 5회 {recent}"
        for (day, recent), tickers in opposite.items() if tickers
    ]
    if contrasts:
        lines.append("기간 차이: " + " | ".join(contrasts))
    return lines


def _rate_direction(move):
    if move is None:
        return "확인 대기"
    if move > 0:
        return "↑ 상승"
    if move < 0:
        return "↓ 하락"
    return "→ 보합"


def _direction_panel(flows, r2, r10, r30, credit_head, hyg_oas):
    d2, d10, d30 = [_rate_move_bp(r) for r in (r2, r10, r30)]
    if d10 is None or d30 is None:
        long_direction = "확인 대기"
    elif d10 < 0 and d30 < 0:
        long_direction = "↓ 하락"
    elif d10 > 0 and d30 > 0:
        long_direction = "↑ 상승"
    elif d10 == d30 == 0:
        long_direction = "→ 보합"
    else:
        long_direction = f"혼조 (10년 {_rate_direction(d10)} · 30년 {_rate_direction(d30)})"
    hdelta = _oas_delta(hyg_oas)
    if hdelta is None:
        spread_move = "변화 비교 확인 대기"
    elif abs(hdelta) < 0.05:
        spread_move = "→ 0.0bp"
    else:
        spread_move = f"{'↑' if hdelta > 0 else '↓'} {hdelta:+.1f}bp"
    credit_label = credit_head.removeprefix("기준일 시차 있는 ").removeprefix("신용위험 ")
    return [
        f"금리 방향: 장기 {long_direction} · 2년 {_rate_direction(d2)}",
        "국채 자금: " + " · ".join(
            f"{label}({ticker}) {_flow_direction(flows[ticker][0])}"
            for ticker, label in (("SHY", "단기"), ("IEF", "중기"), ("TLT", "장기"))
        ) + " (ETF 추정)",
        "회사채 자금: " + " · ".join(
            f"{label}({ticker}) {_flow_direction(flows[ticker][0])}"
            for ticker, label in (("LQD", "투자등급"), ("HYG", "고수익"))
        ) + " (ETF 추정)",
        f"신용 위험: {credit_label} · HYG 신용스프레드(OAS) {spread_move} (직전 저장값 대비)",
    ]


def _credit_alert_line(hyg_flow, hyg_oas, hyg_fund_date=None):
    hdoas = _oas_delta(hyg_oas)
    if hdoas is None or hdoas < 5:
        return None
    asof = _oas_asof(hyg_oas)
    asof_text = f" (OAS 기준 {asof})" if asof else ""
    if asof and hyg_fund_date and asof != hyg_fund_date:
        fund_signal = (
            "추정 순유출" if _outflow(hyg_flow)
            else "추정 순유입" if _inflow(hyg_flow)
            else "흐름 미확정"
        )
        return (
            f"현재 신용경보: HYG OAS {hdoas:+.1f}bp "
            f"{'급확대' if hdoas >= 10 else '확대'} (기준 {asof}) · "
            f"HYG ETF {fund_signal} (기준 {hyg_fund_date}) → "
            "관측일이 달라 같은 거래일 동시 위험회피로 단정하지 않음"
        )
    if hdoas >= 10:
        if _outflow(hyg_flow):
            return f"현재 신용경보: HYG OAS {hdoas:+.1f}bp 급확대{asof_text} + HYG 자금유출 → 신용위험 확대 경계"
        return f"현재 신용경보: HYG OAS {hdoas:+.1f}bp 급확대{asof_text} → 신용위험 경계 강화. HYG 자금은 유입이라 전면 위험회피 확정은 아님"
    if _outflow(hyg_flow):
        return f"현재 신용경보: HYG OAS {hdoas:+.1f}bp 확대{asof_text} + HYG 자금유출 → 신용위험 경계 강화"
    return f"현재 신용경보: HYG OAS {hdoas:+.1f}bp 확대{asof_text} → 신용가격 악화. 자금유입과 신용가격 신호가 엇갈림"


def _fx_rate_from_line(fx_line):
    m = re.search(r"1달러=([0-9,]+(?:\.[0-9]+)?)원", fx_line or "")
    return float(m.group(1).replace(",", "")) if m else None


def _fmt_krw_trillion(value_trillion):
    if value_trillion is None:
        return "원화 환산 확인 대기"
    if value_trillion >= 10000:
        gyeong = int(value_trillion // 10000)
        jo = int(round(value_trillion - gyeong * 10000))
        if jo >= 10000:
            gyeong += 1
            jo -= 10000
        return f"약 {gyeong}경{jo:,}조원"
    if value_trillion >= 1000:
        return f"약 {value_trillion:,.0f}조원"
    if value_trillion >= 100:
        return f"약 {value_trillion:,.1f}조원"
    return f"약 {value_trillion:,.2f}조원"


def _refinancing_line(refi, fx_rate):
    # Convert the source precision, then round only the displayed currency.
    # Converting rounded USD displays can shift the KRW result by trillions.
    next12_krw = _fmt_krw_trillion(refi["next12_t"] * fx_rate if fx_rate else None)
    bills_krw = _fmt_krw_trillion(refi["bills_t"] * fx_rate if fx_rate else None)
    plus75_krw = _fmt_krw_trillion(refi["plus75_b"] * fx_rate / 1000.0 if fx_rate else None)
    return (
        f"차환: 12개월 ${refi['next12_t']:.2f}T ({next12_krw}) ({refi['next12_share']:.1f}%) | "
        f"Bills ${refi['bills_t']:.2f}T ({bills_krw}) ({refi['bill_share']:.1f}%) | "
        f"Bills에 +75bp 적용 시 단순 연율 이자부담 +${refi['plus75_b']:.1f}B ({plus75_krw})"
    )


def _next_alert(y10, y30, hyg_flow, hyg_oas):
    parts = []
    if y10 is not None:
        if y10 < 5.00:
            parts.append("10년물 5.00% 상향 돌파")
        elif y10 < 5.10:
            parts.append("10년물 5.10% 상향")
        elif y10 < 5.20:
            parts.append("10년물 5.20% 상향")
    if y30 is not None:
        if y30 < 5.59:
            parts.append("30년물 JPM 5.59% 상향")
        elif y30 < 5.78:
            parts.append("30년물 JPM 5.78% 상향")
        elif y30 < 6.00:
            parts.append("30년물 JPM 6.00% 상향")
        else:
            parts.append("30년물 JPM 5.25% 하향 반전")
    parts.append("Repo 주의·스트레스 전환")

    hdoas = _oas_delta(hyg_oas)
    if hdoas is not None and hdoas >= 5:
        if _inflow(hyg_flow):
            parts.append("HYG OAS 추가 확대 또는 HYG 자금유출 전환")
        else:
            parts.append("HYG OAS 추가 확대 지속 여부")
    else:
        parts.append("HYG 자금유출 + OAS 일간 +5bp 이상")
    parts.append("R>G 전환")
    return "다음 경보: " + " · ".join(parts)


def _validate_compact_report(text, overall_head, y10, hyg_oas):
    expected = f"전체 방향: {overall_head}"
    if expected not in text:
        raise RuntimeError(f"final report overall mismatch: expected {expected}")
    if re.search(r"[↑↓]\s+[+-]0(?:\.0+)?bp", text):
        raise RuntimeError("final report contains signed zero bp")
    if y10 is not None and y10 >= 5.00 and "다음 경보: 10년물 5% 돌파" in text:
        raise RuntimeError("final report repeats an already-crossed 10Y 5% alert")
    refi = next((line for line in text.splitlines() if line.startswith("차환:")), "")
    if "$" in refi and "원" not in refi:
        raise RuntimeError("refinancing foreign amounts are missing KRW conversion")
    if "$" in refi and "Bills에 +75bp" not in refi:
        raise RuntimeError("refinancing +75bp cost must state that it applies to Bills")
    if "발행좌수 변화 × 해당일 NAV로 계산한 추정치" not in text:
        raise RuntimeError("ETF flow estimation method disclosure missing")
    hdoas = _oas_delta(hyg_oas)
    if hdoas is None:
        rendered = re.search(r"HYG OAS [^\n]*직전(?: 저장값)? 대비\s+↑\s+\+(\d+(?:\.\d+)?)bp", text)
        hdoas = float(rendered.group(1)) if rendered else None
    if hdoas is not None and hdoas >= 5:
        if "신용 위험: 혼조" in text:
            raise RuntimeError("HYG OAS widening >=5bp cannot be flattened to generic mixed credit")
        if "현재 신용경보:" not in text:
            raise RuntimeError("active HYG OAS alert is missing from final report")
        if "자료시점 구분:" not in text and "[한눈에 보기]" in text:
            raise RuntimeError("HYG spread and ETF observation dates must be explicit")
        if "HYG 자금유출 + OAS 일간 +5bp 이상" in text:
            raise RuntimeError("already-triggered HYG OAS threshold repeated as a future alert")


def _compact_report(raw_text):
    flows = {t: _flow(t, raw_text) for t in ("SHY", "IEF", "TLT", "LQD", "HYG")}
    fund_dates = {t: _fund_date(t, raw_text) for t in flows}
    lqd_oas, hyg_oas = _oas("LQD", raw_text), _oas("HYG", raw_text)
    overall_head, overall_reason = readable._direction_pair("전체 자금 방향", raw_text)
    overall_head = _display_overall_head(overall_head)
    credit_head, _ = readable._direction_pair("신용자금 방향", raw_text)
    hyg_fund_date = _fund_date("HYG", raw_text)
    credit_alert_line = _credit_alert_line(flows["HYG"][0], hyg_oas, hyg_fund_date)

    r2, r10, r30 = _rate("2년", raw_text), _rate("10년", raw_text), _rate("30년", raw_text)
    s210 = _rate("2년-10년 금리차", raw_text)
    s1030 = _rate("10년-30년 금리차", raw_text)
    regime = _m(r"^• 현재 형태: ([^\n]+)", raw_text)
    easy = _m(r"^• 쉬운 해석: ([^\n]+)", raw_text)
    driver = _m(r"^• 오늘의 주도축: ([^\n]+)", raw_text)
    treasury_date = _m(r"^기준: ([0-9]{4}-[0-9]{2}-[0-9]{2}) \| 직전:", raw_text)

    y10, y30 = _yield_value(raw_text, "10년"), _yield_value(raw_text, "30년")
    d10_bp = _rate_move_bp(r10)
    d30_bp = _rate_move_bp(r30)
    tech_head, tech_reason = stress._market_stress(y10, y30, d10_bp, d30_bp)
    jpm_30y_line = _jpm_30y_signal(y30)
    # This is an optional added signal. A stale or failed real-yield source must
    # not be fabricated and must not suppress the existing nominal-rate report.
    try:
        if not y10 or treasury_date == "확인 대기":
            raise real_yield.CurveMismatch("10년 명목금리 또는 기준일 누락")
        real_yield_block = real_yield.build_block(treasury_date, y10)
    except real_yield.CurveMismatch as exc:
        real_yield_block = (
            "[실질금리·시장 내재 물가상승률]\n"
            f"자료 보류: {exc} · 같은 거래일 미 재무부 명목·실질 수치 검증 전 경보 미발동"
        )
    except Exception as exc:
        real_yield_block = (
            "[실질금리·시장 내재 물가상승률]\n"
            f"자료 확인 불가: {type(exc).__name__} · 공식 원천 조회 실패, 경보 미발동"
        )

    try:
        repo_line = get_repo_stress()
    except Exception:
        repo_line = "Repo: 확인 대기 | OFR/NY Fed 공식값 조회 실패"

    gr = readable.get_growth_cost_snapshot()
    if gr.get("ok"):
        gr_line = (
            f"G-R 보조 프록시(명목GDP 연율-HYG 평균 만기수익률): {gr['gap']:+.2f}%p | "
            f"G {gr['g']:.2f}% ({gr.get('g_period') or '기준기간 확인 대기'}) vs "
            f"R {gr['r']:.2f}% (HYG 기준 {gr.get('r_date') or '기준일 확인 대기'}) → {gr['state']}"
        )
    else:
        gr_line = "G-R: 공식 최신값 조회 실패 → 판정 보류"

    date_line = _m(r"^조회시각\(KST\): ([^\n]+)", raw_text)
    fx_line = _m(r"^환율: ([^\n]+)", raw_text)
    fx_rate = _fx_rate_from_line(fx_line)

    try:
        refi = get_refinancing_snapshot()
        refi_line = _refinancing_line(refi, fx_rate)
        refi_date = refi["record_date"]
    except Exception:
        refi_line = "차환: MSPD 최신값 조회 실패 → 판정 보류"
        refi_date = "확인 대기"

    next_alert_line = _next_alert(y10, y30, flows["HYG"][0], hyg_oas)
    latest_oas_date = _oas_asof(hyg_oas)
    if treasury_date != "확인 대기" and latest_oas_date and latest_oas_date != treasury_date:
        credit_date_note = (
            f"자료시점 구분: 국채·ETF {treasury_date} / 회사채 OAS {latest_oas_date}. "
            "거래일이 달라 당일 동시 악화로 단정하지 않음"
        )
    else:
        credit_date_note = (
            f"자료시점 구분: 국채·ETF {treasury_date} / "
            f"회사채 OAS {latest_oas_date or '기준일 확인 대기'}"
        )

    lines = [
        "[미 국채·회사채 방향성 일일 보고]",
        f"조회: {date_line}",
        "",
        "[한눈에 보기]",
        f"전체 방향: {overall_head}",
        *_direction_panel(flows, r2, r10, r30, credit_head, hyg_oas),
        *_flow_interpretation_panel(flows, fund_dates),
        credit_date_note,
        "",
        "[금리 상세]",
        f"2년: {r2}",
        f"10년: {r10}",
        f"30년: {r30}",
        f"커브: {regime} = {easy}",
        f"금리차: 2-10년 {s210} | 10-30년 {s1030}",
        f"오늘의 주도축: {driver}",
        "",
        "[자금 상세 — 일간 / 최근 5회]",
        f"SHY (단기 국채): {flows['SHY'][0]} / {flows['SHY'][1]}",
        f"IEF (중기 국채): {flows['IEF'][0]} / {flows['IEF'][1]}",
        f"TLT (장기 국채): {flows['TLT'][0]} / {flows['TLT'][1]}",
        f"LQD (투자등급 회사채): {flows['LQD'][0]} / {flows['LQD'][1]}",
        f"HYG (고수익 회사채): {flows['HYG'][0]} / {flows['HYG'][1]}",
        "",
        "[신용 상세]",
        f"LQD OAS: {lqd_oas}",
        f"HYG OAS: {hyg_oas}",
        *([credit_alert_line] if credit_alert_line else []),
        "",
        "[추가 경계 요인]",
        f"시장 기술압력: {tech_head}",
        f"→ {tech_reason}",
        f"{jpm_30y_line}",
        "",
        real_yield_block,
        "",
        f"{repo_line}",
        f"{gr_line}",
        f"{refi_line}",
        "",
        "[판정 근거·다음 확인]",
        overall_reason,
        next_alert_line,
        "",
        "[자료 기준]",
        f"환율: {fx_line}",
        f"기준: ETF·미 재무부 {treasury_date} | MSPD {refi_date}",
        "자금흐름: iShares 공식 발행좌수 변화 × 해당일 NAV로 계산한 추정치이며 iShares가 공표한 공식 일간 순유입액은 아님.",
        "OAS: iShares LQD·HYG ETF 보유채권 포트폴리오 특성치이며 회사채 시장 전체 스프레드는 아님.",
        "출처: iShares · U.S. Treasury · Treasury FiscalData · OFR/NY Fed · BEA · JPM 기술기준(사용자 제공 2026-09-29 자료)",
    ]
    report = "\n".join(lines)
    _validate_compact_report(report, overall_head, y10, hyg_oas)
    return report


def _format_real_yield_sources(line):
    base = re.escape(real_yield.BASE)
    match = re.fullmatch(
        rf"공식 원천: (?P<nominal>{base}\?data=daily_treasury_yield_curve"
        rf"&field_tdr_date_value=(?P<year>[0-9]{{4}})) \| "
        rf"(?P<real>{base}\?data=daily_treasury_real_yield_curve"
        rf"&field_tdr_date_value=(?P=year))",
        line,
    )
    if not match:
        return None
    nominal_url = html.escape(match.group("nominal"), quote=True)
    real_url = html.escape(match.group("real"), quote=True)
    return (
        f'공식 원천: <a href="{nominal_url}">미 재무부 명목금리</a>'
        f' · <a href="{real_url}">미 재무부 실질금리</a>'
    )


def _format_html(chunk):
    out = []
    bold_prefixes = (
        "전체 방향:", "금리 방향:", "국채 자금:", "회사채 자금:", "신용 위험:",
        "국채 해석(ETF 추정):", "회사채 해석(ETF 추정):",
    )
    for line in chunk.splitlines():
        source_links = _format_real_yield_sources(line)
        if source_links is not None:
            out.append(source_links)
            continue
        escaped = html.escape(line, quote=False)
        bold = (line.startswith("[") and line.endswith("]")) or line.startswith(bold_prefixes)
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
    if os.getenv("TREASURY_REPORT_VALIDATE_ONLY", "").lower() in ("1", "true", "yes"):
        raw_path = app.base.OUT / "treasury_etf_flow_telegram.txt"
        if raw_path.exists():
            raw_report = raw_path.read_text(encoding="utf-8")
            final_report = _compact_report(raw_report)
            # Validate actual final rendering, not only the unformatted feeder.
            if "[실질금리·시장 내재 물가상승률]" not in final_report:
                raise RuntimeError("real yield block missing from final report")
            if "자료 보류:" in final_report or "자료 확인 불가:" in final_report:
                raise RuntimeError("official real-yield feed did not produce a verified signal")
            (app.base.OUT / "treasury_real_yield_validation.txt").write_text(
                final_report + "\n", encoding="utf-8"
            )
            real_lines = final_report.split("[실질금리·시장 내재 물가상승률]", 1)[1].split("\n\n", 1)[0]
            print(
                "treasury_real_yield_validation=ok telegram_sent=false "
                + real_lines.replace("\n", " | ")[:900]
            )
        else:
            print("treasury_real_yield_validation=skipped feeder_report_unavailable")
