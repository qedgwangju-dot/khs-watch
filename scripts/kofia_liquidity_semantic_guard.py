#!/usr/bin/env python3
"""Fail-closed validation of the *final* KOFIA Telegram message, not a draft.

This validates the exact text after the workflow's narrative replacement, and
the exact pending state that will be persisted after Telegram acknowledges it.
"""
import json
import datetime as dt
import math
import re
from pathlib import Path

ALERT = Path("out/kofia_liquidity_alert.html")
PENDING = Path("out/kofia_liquidity_pending_state.json")

LABELS = {
    "deposit": ("투자자예탁금", "예탁금"),
    "mmf": ("MMF 설정원본", "MMF"),
    "cma": ("CMA 잔고", "CMA"),
    "credit": ("신용융자", "신용융자"),
}


def expect(ok, message):
    if not ok:
        raise RuntimeError("KOFIA semantic quality gate: " + message)


def amount(raw):
    expect(type(raw) in (int, float) and math.isfinite(raw), "invalid numeric value")
    return f"{raw / 1_000_000:+.2f}"


def level(raw):
    expect(type(raw) in (int, float) and math.isfinite(raw), "invalid balance")
    return f"{raw / 1_000_000:.2f}"


def date_label(d):
    expect(bool(re.fullmatch(r"\d{8}", str(d))), "invalid date " + str(d))
    dt.datetime.strptime(d, "%Y%m%d")
    return f"{int(d[4:6])}/{int(d[6:8])}"


def full_date_label(d):
    expect(bool(re.fullmatch(r"\d{8}", str(d))), "invalid full date " + str(d))
    dt.datetime.strptime(d, "%Y%m%d")
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}"


def direction(value, balance):
    floor = max(50_000.0, abs(balance) * 0.0005)
    if abs(value) < floor:
        return "보합"
    return "증가" if value > 0 else "감소"


def arrow(value, balance):
    return {"증가": "↑", "감소": "↓", "보합": "≈"}[direction(value, balance)]


def horizon_delta(window, key):
    item = (window.get("changes") or {}).get(key) or {}
    delta = item.get("delta")
    if type(delta) not in (int, float) or not math.isfinite(delta):
        return "비교불가"
    arrow = "↑" if delta > 0 else "↓" if delta < 0 else "≈"
    return f"{delta / 1_000_000:+.2f}조{arrow}"


def validate(text, state):
    expect(isinstance(text, str) and 0 < len(text) < 4096, "Telegram message empty or over 4096 characters")
    for heading in ("<b>무엇이 달라졌나</b>", "<b>현재 판정</b>", "<b>검증</b>"):
        expect(text.count(heading) == 1, "missing/duplicate heading " + heading)

    values = state["values"]
    dates = state["dates"]
    fields = tuple(LABELS)
    expect(state.get("alignment_ready") is True, "alignment_ready is not true")
    ref_dates = state.get("reference_dates")
    expect(isinstance(ref_dates, list) and len(ref_dates) == 6, "1D/5D date references missing")
    expect(len(set(ref_dates)) == 6 and ref_dates == sorted(ref_dates, reverse=True), "reference dates not distinct/descending")
    expect(all(dates[k] == state.get("snapshot_date") == values[k]["date"] == ref_dates[0] for k in fields),
           "critical dates/values not aligned")
    horizons = values.get("balance_horizons")
    monthly_version = state.get("message_version") == "kofia-balances-v5-calendar-month-balances"
    legacy_version = state.get("message_version") in (
        None, "kofia-balances-v4", "kofia-balances-20261013-v2"
    )
    expect(monthly_version or legacy_version, "unknown KOFIA message version")
    if monthly_version:
        expect(isinstance(horizons, dict) and set(horizons) == {"m1", "m3"},
               "1M/3M balance horizon data missing")
        for months, key in ((1, "m1"), (3, "m3")):
            window = horizons[key]
            target = (dt.datetime.strptime(state["snapshot_date"], "%Y%m%d").date())
            month_index = target.year * 12 + target.month - 1 - months
            year, month0 = divmod(month_index, 12)
            month = month0 + 1
            import calendar
            target_day = min(target.day, calendar.monthrange(year, month)[1])
            target_text = f"{year:04d}{month:02d}{target_day:02d}"
            expect(window.get("months_back") == months and window.get("target_date") == target_text,
                   f"{months}M calendar target mismatch")
            anchor = window.get("anchor_date")
            if anchor is not None:
                date_label(anchor)
                gap = (dt.datetime.strptime(target_text, "%Y%m%d").date()
                       - dt.datetime.strptime(anchor, "%Y%m%d").date()).days
                expect(anchor <= target_text and 0 <= gap <= 7 and window.get("max_anchor_gap_days") == 7,
                       f"{months}M anchor outside prior 7-day window")
            expect(window.get("end_date") == state["snapshot_date"], f"{months}M end date mismatch")
            expect(set((window.get("changes") or {})) == set(fields), f"{months}M metrics incomplete")
            for metric_key in fields:
                item = window["changes"][metric_key]
                delta = item.get("delta")
                if delta is None:
                    expect(bool(item.get("reason")), f"{months}M {metric_key} missing reason")
                else:
                    expect(type(delta) in (int, float) and math.isfinite(delta)
                           and item.get("start_date") == anchor
                           and item.get("end_date") == state["snapshot_date"]
                           and item.get("reason") is None,
                           f"{months}M {metric_key} delta/date invalid")
    else:
        expect(horizons is None, "legacy KOFIA state unexpectedly carries monthly values")

    head, rest = text.split("<b>현재 판정</b>", 1)
    assessment, verification = rest.split("<b>검증</b>", 1)
    expect("MMF 1D는 공식 전일대비증감" in verification, "source cross-check description absent")

    # Verify every exact displayed number, including sign and date, against
    # independent, unrounded integer KOFIA values stored in pending state.
    for key, (full_name, short_name) in LABELS.items():
        v = values[key]
        for period in ("value", "d1", "d5"):
            expect(type(v[period]) in (int, float) and math.isfinite(v[period]),
                   f"{key} {period} invalid")
        pat = (
            r"^• " + re.escape(full_name) +
            r"(?:\([^\n)]*\))? <b>([\d,]+\.\d{2})조</b> " +
            r"\((\d{1,2}/\d{1,2})\) \| 1D ([+-]?\d+\.\d{2})조 \| 5D ([+-]?\d+\.\d{2})조"
            + (r" \| 1M ([^|]+) \| 3M ([^|]+)$" if monthly_version else r"$")
        )
        found = re.findall(pat, head, re.M)
        expect(len(found) == 1, f"{key} numeric row missing/duplicated")
        display_level, day, display_d1, display_d5, *monthly_values = found[0]
        expect(display_level == level(v["value"]) and day == date_label(v["date"]),
               f"{key} level/date mismatch")
        expect(display_d1 == amount(v["d1"]) and display_d5 == amount(v["d5"]),
               f"{key} signed 1D/5D amount mismatch")
        if monthly_version:
            display_m1, display_m3 = monthly_values
            expect(display_m1.strip() == horizon_delta(horizons["m1"], key)
                   and display_m3.strip() == horizon_delta(horizons["m3"], key),
                   f"{key} signed 1M/3M balance change mismatch")

    # The receivable and actual forced-sale amounts are also Telegram-facing
    # financial figures. An incorrect amount here must block the whole alert.
    rec = values.get("receivable") or {}
    forced = values.get("forced") or {}
    expect(type(rec.get("value")) in (int, float) and math.isfinite(rec["value"]) and rec["value"] >= 0,
           "invalid KOFIA receivable")
    expect(type(forced.get("value")) in (int, float) and math.isfinite(forced["value"]) and forced["value"] >= 0,
           "invalid KOFIA forced-sale amount")
    # New alerts identify the forced-sale scope: unpaid-settlement trades, not
    # every credit-margin liquidation. Historical fixture messages remain testable.
    modern_scope = state.get("message_version") is not None
    if modern_scope:
        expect("실제 반대매매" not in text, "ambiguous all-market forced-sale label")
    scope_pattern = (
        r"^• 위탁매매 미수금 ([\d,]+\.\d{2})조 \| 미수거래 반대매매 ([\d,]+)억원$"
        if modern_scope else
        r"^• (?:위탁매매 )?미수금 ([\d,]+\.\d{2})조 \| (?:실제 반대매매|미수거래 반대매매) ([\d,]+)억원$"
    )
    rec_forced = re.findall(scope_pattern, head, re.M)
    expect(len(rec_forced) == 1, "receivable/forced-sale row missing or duplicated")
    rec_print, forced_print = rec_forced[0]
    expected_forced_eok = int(math.floor(forced["value"] / 100.0 + 0.5))
    expect(rec_print == level(rec["value"]) and
           forced_print.replace(",", "") == str(expected_forced_eok),
           "receivable or forced-sale displayed value differs from KOFIA source")

    rows = assessment.splitlines()
    def find(prefix):
        matching = [r for r in rows if r.startswith(prefix)]
        expect(len(matching) == 1, "missing/duplicate assessment line " + prefix)
        return matching[0]

    cash = find("• <b>자금 방향</b>:")
    persistence = find("• <b>지속성</b>:")
    cma = find("• <b>CMA</b>:")
    leverage = find("• <b>레버리지</b>:")
    monthly = find("• <b>1M/3M 잔액 방향</b>:") if monthly_version else None
    summary = find("• <b>종합</b>:")

    for key, (_, short_name) in LABELS.items():
        v = values[key]
        expect(f"{short_name} {amount(v['d1'])}조{arrow(v['d1'],v['value'])}" in cash,
               f"{key} 1D assessment sign/arrow mismatch")
        expect(f"{short_name} {amount(v['d5'])}조{arrow(v['d5'],v['value'])}" in persistence,
               f"{key} 5D assessment sign/arrow mismatch")

    v = values["cma"]
    expect(f"1D {amount(v['d1'])}조{arrow(v['d1'],v['value'])}" in cma, "CMA 1D sign mismatch")
    expect(f"5D {amount(v['d5'])}조{arrow(v['d5'],v['value'])}" in cma, "CMA 5D sign mismatch")

    v = values["credit"]
    expect(f"신용융자 1D {amount(v['d1'])}조{arrow(v['d1'],v['value'])}" in leverage,
           "credit 1D sign mismatch")
    expect(f"5D {amount(v['d5'])}조{arrow(v['d5'],v['value'])}" in leverage,
           "credit 5D sign mismatch")

    def horizon_direction_text(months):
        window = (horizons or {}).get(f"m{months}", {})
        parts = []
        for metric_key, (_, short_name) in LABELS.items():
            item = (window.get("changes") or {}).get(metric_key, {})
            delta = item.get("delta")
            if delta is None:
                parts.append(f"{short_name} 확인불가")
            else:
                parts.append(f"{short_name} {amount(delta)}조{arrow(delta, values[metric_key]['value'])}")
        return f"{months}M " + " · ".join(parts)

    expected_monthly = (
        f"• <b>1M/3M 잔액 방향</b>: {horizon_direction_text(1)} / "
        f"{horizon_direction_text(3)} → 잔액의 시점 간 차이이며 누적 순유입이나 상품 간 이동을 뜻하지 않습니다."
    )
    if monthly_version:
        expect(monthly == expected_monthly, "1M/3M directional interpretation differs from source values")

    mmf = values["mmf"]
    d1 = direction(mmf["d1"], mmf["value"])
    d5 = direction(mmf["d5"], mmf["value"])
    if d1 == "증가":
        expected = ("당일에도 MMF가 증가" if d5 == "증가" else
                    "당일 MMF가 증가했으나" if d5 == "감소" else
                    "당일 MMF가 증가했지만")
        forbidden = ("당일 MMF는 감소", "당일 MMF 급감", "당일 MMF 감소", "당일 MMF 유출")
    elif d1 == "감소":
        expected = "당일 MMF는 감소" if d5 != "감소" else "당일 MMF도 감소"
        forbidden = ("당일에도 MMF가 증가", "당일 MMF 급증", "당일 MMF 증가", "당일 MMF 유입")
    else:
        expected = "당일 MMF는 유의미한 증감 없이 보합"
        forbidden = ("당일 MMF 급감", "당일 MMF 급증", "당일에도 MMF가 증가", "당일 MMF는 감소")
    expect(expected in persistence, "MMF 1D/5D verbal explanation contradicts raw direction")
    expect(not any(s in assessment for s in forbidden), "opposite MMF direction claim in assessment")
    if d5 != "증가":
        expect("MMF 증가분이 주식에서" not in assessment,
               "MMF 5D non-increase mislabeled as increase in summary")
    if d5 == "보합":
        expect("5개 공표구간 흐름과 같은 방향" not in persistence,
               "MMF daily non-flat move wrongly equated with flat five-day trend")

    # Recalculate the period relationship independently from signed raw values,
    # including materiality/flat boundaries, after the final text replacement.
    pairs = [(name, direction(values[key]['d1'], values[key]['value']),
              direction(values[key]['d5'], values[key]['value']))
             for key, (_, name) in LABELS.items()]
    opposite = [name for name, daily, five in pairs
                if daily != five and daily != '보합' and five != '보합']
    flat_change = [name for name, daily, five in pairs
                   if daily != five and '보합' in (daily, five)]
    period_claims = []
    if opposite:
        period_claims.append(f"1D와 5D의 방향이 반대인 항목은 {', '.join(opposite)}입니다.")
    if flat_change:
        period_claims.append(f"1D와 5D의 보합 여부가 다른 항목은 {', '.join(flat_change)}입니다.")
    if not period_claims:
        period_claims.append(
            '네 지표 모두 1D와 5D 기준으로 보합입니다.'
            if all(daily == five == '보합' for _, daily, five in pairs) else
            '네 지표의 1D와 5D 방향은 각 항목별로 일치합니다.'
        )
    expect(summary.startswith('• <b>종합</b>: ' + ' '.join(period_claims) + ' '),
           'summary daily/five-period relationship differs from raw values')
    if not opposite and not flat_change:
        expect('일치하지 않습니다' not in summary,
               'matching daily/five-period directions mislabeled as disagreement')

    comparison = (
        f"• 비교 기준: 1D {date_label(ref_dates[1])} → {date_label(ref_dates[0])} / "
        f"5D {date_label(ref_dates[5])} → {date_label(ref_dates[0])}"
    )
    if monthly_version:
        comparison += (
            f" / 1M 목표 {full_date_label(horizons['m1']['target_date'])}·기준 "
            f"{full_date_label(horizons['m1']['anchor_date']) if horizons['m1'].get('anchor_date') else '확인불가'} / "
            f"3M 목표 {full_date_label(horizons['m3']['target_date'])}·기준 "
            f"{full_date_label(horizons['m3']['anchor_date']) if horizons['m3'].get('anchor_date') else '확인불가'}"
        )
    expect(text.splitlines().count(comparison) == 1, "comparison dates absent or inconsistent")
    expect("5D는 최근 5개 공표구간의 잔액 차이" in text,
           "five-period balance basis missing")
    if monthly_version:
        expect("1M/3M은 달력월 목표일 직전 공표 잔액과의 차이" in text
               and "1M/3M은 잔액 수준의 시점 간 변화이며 누적 순유입·실제 자금 이동이 아님" in text,
               "balance-change period basis missing")
    if state.get('queried_at_kst'):
        expected_query = '• 원자료 조회: ' + state['queried_at_kst'].replace('T', ' ').replace('+09:00', ' KST')
        expect(text.splitlines().count(expected_query) == 1, 'query time differs from pending')
    if state.get('mmf_daily_rounding_difference'):
        expect('백만원 표시 반올림 차이 1 이내' in verification, 'MMF rounding difference is not disclosed')
    for phrase in ("위험자산 쪽 이동 가능성이 커", "수급의 질은 개선", "수급의 질이 이전보다 취약", "빚을 늘리지 않고"):
        expect(phrase not in assessment, "unsupported transfer/trade/leverage claim: " + phrase)
    triggers = [("투자자예탁금", "deposit", 2000000, "±2조"), ("MMF", "mmf", 3000000, "±3조"),
                ("CMA", "cma", 2000000, "±2조"), ("신용융자", "credit", 500000, "±0.5조")]
    expected = [f"{label} {amount(values[key]['d1'])}조(경보 기준 {limit} 이상)"
                for label, key, threshold, limit in triggers if abs(values[key]['d1']) >= threshold]
    actual = find("• <b>큰 변동 항목</b>:")
    required = " / ".join(expected) if expected else "1D 큰 변동 기준을 넘은 항목 없음"
    expect(actual == "• <b>큰 변동 항목</b>: " + required + " (기준: 예탁금 ±2조 / MMF ±3조 / CMA ±2조 / 신용융자 ±0.5조)",
           "large-change threshold verdict differs from source")
    return True


def main():
    state = json.loads(PENDING.read_text(encoding="utf-8"))
    text = ALERT.read_text(encoding="utf-8")
    validate(text, state)
    print("kofia_final_message_semantic_gate=true signed_values=true arrows=true narrative=true aligned_dates=true")


if __name__ == "__main__":
    main()
