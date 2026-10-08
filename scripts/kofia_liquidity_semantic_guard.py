#!/usr/bin/env python3
"""Fail-closed validation of the *final* KOFIA Telegram message, not a draft.

This validates the exact text after the workflow's narrative replacement, and
the exact pending state that will be persisted after Telegram acknowledges it.
"""
import json
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
    expect(isinstance(raw, (int, float)) and math.isfinite(raw), "invalid numeric value")
    return f"{raw / 1_000_000:+.2f}"


def level(raw):
    expect(isinstance(raw, (int, float)) and math.isfinite(raw), "invalid balance")
    return f"{raw / 1_000_000:.2f}"


def date_label(d):
    expect(bool(re.fullmatch(r"\d{8}", str(d))), "invalid date " + str(d))
    return f"{int(d[4:6])}/{int(d[6:8])}"


def direction(value, balance):
    floor = max(50_000.0, abs(balance) * 0.0005)
    if abs(value) < floor:
        return "보합"
    return "증가" if value > 0 else "감소"


def arrow(value, balance):
    return {"증가": "↑", "감소": "↓", "보합": "≈"}[direction(value, balance)]


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

    head, rest = text.split("<b>현재 판정</b>", 1)
    assessment, verification = rest.split("<b>검증</b>", 1)
    expect("MMF 1D는 공식 전일대비증감" in verification, "source cross-check description absent")

    # Verify every exact displayed number, including sign and date, against
    # independent, unrounded integer KOFIA values stored in pending state.
    for key, (full_name, short_name) in LABELS.items():
        v = values[key]
        for period in ("value", "d1", "d5"):
            expect(isinstance(v[period], (int, float)) and math.isfinite(v[period]),
                   f"{key} {period} invalid")
        pat = (
            r"^• " + re.escape(full_name) +
            r"(?:\([^\n)]*\))? <b>([\d,]+\.\d{2})조</b> " +
            r"\((\d{1,2}/\d{1,2})\) \| 1D ([+-]?\d+\.\d{2})조 \| 5D ([+-]?\d+\.\d{2})조$"
        )
        found = re.findall(pat, head, re.M)
        expect(len(found) == 1, f"{key} numeric row missing/duplicated")
        display_level, day, display_d1, display_d5 = found[0]
        expect(display_level == level(v["value"]) and day == date_label(v["date"]),
               f"{key} level/date mismatch")
        expect(display_d1 == amount(v["d1"]) and display_d5 == amount(v["d5"]),
               f"{key} signed 1D/5D amount mismatch")

    rows = assessment.splitlines()
    def find(prefix):
        matching = [r for r in rows if r.startswith(prefix)]
        expect(len(matching) == 1, "missing/duplicate assessment line " + prefix)
        return matching[0]

    cash = find("• <b>자금 방향</b>:")
    persistence = find("• <b>지속성</b>:")
    cma = find("• <b>CMA</b>:")
    leverage = find("• <b>레버리지</b>:")
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

    mmf = values["mmf"]
    d1 = direction(mmf["d1"], mmf["value"])
    d5 = direction(mmf["d5"], mmf["value"])
    if d1 == "증가":
        expected = "당일에도 MMF가 증가" if d5 == "증가" else "당일 MMF가 증가했으나"
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
        expect("5거래일 흐름과 같은 방향" not in persistence,
               "MMF daily non-flat move wrongly equated with flat five-day trend")
    dep = values["deposit"]
    cr = values["credit"]
    if (direction(dep["d1"],dep["value"]) == "증가"
        and direction(values["cma"]["d1"],values["cma"]["value"]) == "증가"
        and d1 == "감소" and direction(cr["d1"],cr["value"]) == "감소"):
        expect("당일 수급의 질은 개선" in summary, "strong day improvement not reflected")
    elif (direction(dep["d5"],dep["value"]) == "감소" and
          direction(cr["d5"],cr["value"]) == "증가"):
        expect("수급의 질이 이전보다 취약" in summary, "5D risk mismatch")
    return True


def main():
    state = json.loads(PENDING.read_text(encoding="utf-8"))
    text = ALERT.read_text(encoding="utf-8")
    validate(text, state)
    print("kofia_final_message_semantic_gate=true signed_values=true arrows=true narrative=true aligned_dates=true")


if __name__ == "__main__":
    main()
