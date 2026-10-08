#!/usr/bin/env python3
"""Use the exact production workflow narrative Python and a separate final-message
semantic validator on synthetic KOFIA states. No live Telegram or state mutation."""
import json
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

from kofia_liquidity_semantic_guard import validate

WORKFLOW = Path(".github/workflows/kofia-liquidity-telegram-watch.yml")
START = "      - name: Build detailed current interpretation"
HEREDOC = "          python - <<'PY'\n"
END = "\n          PY"

BASE = {
    "deposit": {"date": "20261007", "value": 100379607, "d1": -669020, "d5": -7346063},
    "mmf": {"date": "20261007", "value": 262894698, "d1": 4928506, "d5": 24445118},
    "cma": {"date": "20261007", "value": 105624312, "d1": 2628244, "d5": -949377},
    "credit": {"date": "20261007", "value": 33516739, "d1": -42404, "d5": 596734},
}


def production_python():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    section = workflow.split(START, 1)[1]
    script = section.split(HEREDOC, 1)[1].split(END, 1)[0]
    return textwrap.dedent(script)


SCRIPT = production_python()


def trial(name, overrides=None, expected=None, forbidden=(), bad_dates=False, corrupt=None):
    with tempfile.TemporaryDirectory(prefix="kofia_narrative_") as root:
        base = Path(root)
        (base / "out").mkdir()
        (base / "out/kofia_liquidity_alert.html").write_text(
            "<b>[국내 증시 대기자금 추적]</b>\n"
            "• 핵심 4개 지표 기준일 동기화: <b>10/7</b>\n"
            "<b>무엇이 달라졌나</b>\n"
            "• 투자자예탁금 <b>100.38조</b> (10/7) | 1D -0.67조 | 5D -7.35조\n"
            "• MMF 설정원본 <b>262.89조</b> (10/7) | 1D +4.93조 | 5D +24.45조\n"
            "• CMA 잔고 <b>105.62조</b> (10/7) | 1D +2.63조 | 5D -0.95조\n"
            "• 신용융자 <b>33.52조</b> (10/7) | 1D -0.04조 | 5D +0.60조\n"
            "<b>현재 판정</b>\n• 원본 간략 판정\n\n"
            "<b>검증</b>\n• MMF 1D는 공식 전일대비증감과 재계산값 일치 확인\n",
            encoding="utf-8",
        )
        values = json.loads(json.dumps(BASE))
        for k, changes in (overrides or {}).items():
            values[k].update(changes)
        dates = {k: "20261007" for k in BASE}
        if bad_dates:
            dates["mmf"] = "20261006"
        state = {
            "values": values,
            "dates": dates,
            "alignment_ready": True,
            "snapshot_date": "20261007",
            "reference_dates": ["20261007","20261006","20261002","20261001","20260930","20260929"],
        }
        (base / "out/kofia_liquidity_pending_state.json").write_text(json.dumps(state), encoding="utf-8")
        done = subprocess.run(
            [sys.executable, "-c", SCRIPT],
            cwd=base, text=True, capture_output=True,
        )
        if bad_dates:
            assert done.returncode != 0, (name, done.stdout, done.stderr)
            assert "date quality gate failed" in done.stderr, (name, done.stderr)
            print(f"PASS {name}: mismatched dates block interpretation")
            return
        assert done.returncode == 0, (name, done.stdout, done.stderr)
        text = (base / "out/kofia_liquidity_alert.html").read_text(encoding="utf-8")
        if expected:
            assert expected in text, (name, expected, text)
        for phrase in forbidden:
            assert phrase not in text, (name, phrase, text)
        if corrupt:
            bad_text = corrupt(text)
            try:
                validate(bad_text, state)
            except RuntimeError:
                print(f"PASS {name}: tampered output blocked")
                return
            raise AssertionError(f"{name}: semantic guard accepted corrupted output")
        # Rebuild the synthetic headline numbers for the overridden state
        # without changing the real production narrative generator.
        for k, full in (
            ("deposit", "투자자예탁금"),
            ("mmf", "MMF 설정원본"),
            ("cma", "CMA 잔고"),
            ("credit", "신용융자"),
        ):
            v = values[k]
            import re
            pattern = rf"^• {re.escape(full)}(?:\([^\n)]*\))? <b>[\d.]+조</b> \(10/7\) \| 1D [+-]?\d+\.\d{{2}}조 \| 5D [+-]?\d+\.\d{{2}}조$"
            row = (
                f"• {full}"
                + ("(단기금융상품에 투자하는 펀드의 투자원금 기준 규모)" if k == "mmf"
                   else "(증권사 현금관리계좌에 머무는 단기자금)" if k == "cma" else "")
                + f" <b>{v['value']/1_000_000:.2f}조</b> (10/7)"
                + f" | 1D {v['d1']/1_000_000:+.2f}조 | 5D {v['d5']/1_000_000:+.2f}조"
            )
            text = re.sub(pattern, lambda _: row, text, flags=re.M)
        assert validate(text, state), (name, text)
        print(f"PASS {name}")


def run_all():
    trial(
        "2026-10-07 real positive MMF", expected="당일에도 MMF가 증가해 5거래일 누적 증가 방향과 일치합니다.",
        forbidden=("당일 MMF 급감", "당일 MMF는 감소", "당일 MMF 감소"),
    )

    # Each MMF sign is checked against all three possible five-day trend states.
    for d1, day_word in (
        (4_928_506, "증가"),
        (-6_007_744, "감소"),
        (0, "보합"),
    ):
        for d5 in (24_445_118, -24_445_118, 0):
            expected = (
                "당일에도 MMF가 증가" if d1 > 0 and d5 > 0 else
                "당일 MMF가 증가했으나" if d1 > 0 and d5 < 0 else
                "당일 MMF가 증가했지만" if d1 > 0 else
                "당일 MMF는 감소" if d1 < 0 and d5 >= 0 else
                "당일 MMF도 감소" if d1 < 0 else
                "당일 MMF는 유의미한 증감 없이 보합"
            )
            trial(f"MMF day={day_word}, five={d5}", overrides={"mmf":{"d1":d1,"d5":d5}}, expected=expected)

    # Cash-direction branches, higher leverage/lower cash despite a positive MMF day,
    # materiality boundary and the high-quality cash-day override.
    trial("deposit/cma increase with MMF decrease and credit decrease", overrides={
        "deposit":{"d1":3_000_000}, "mmf":{"d1":-4_000_000},
        "cma":{"d1":3_000_000}, "credit":{"d1":-100_000},
    }, expected="당일 수급의 질은 개선")
    trial("deposit decrease with MMF decrease and CMA increase", overrides={
        "deposit":{"d1":-3_000_000}, "mmf":{"d1":-4_000_000},
        "cma":{"d1":3_000_000},
    }, expected="MMF 자금이 감소했지만")
    trial("five-day low cash and high leverage", expected="수급의 질이 이전보다 취약")
    trial("five-day improving cash", overrides={
        "deposit":{"d5":5_000_000}, "credit":{"d5":-150_000}
    }, expected="현금 매수 여력 개선")
    trial("MMF smaller-than-material movement", overrides={
        "mmf":{"d1":125_000}
    }, expected="당일 MMF는 유의미한 증감 없이 보합")
    trial("MMF just-above-material movement", overrides={
        "mmf":{"d1":200_000}
    }, expected="당일에도 MMF가 증가")
    trial("CMA one-day flat and five-day drop", overrides={
        "cma":{"d1":0, "d5":-2_000_000}
    }, expected="CMA</b>: 1D +0.00조≈")
    trial("MMF five-day decline cannot claim MMF inflow", overrides={
        "mmf":{"d1":-4_000_000, "d5":-8_000_000}
    }, expected="MMF의 변화분을 주식시장 자금과 동일 자금의 직접 이동으로 단정하지 않습니다.",
       forbidden=("MMF 증가분이 주식에서",))
    trial("MMF five-day flat cannot claim matching daily direction", overrides={
        "mmf":{"d1":-4_000_000, "d5":0}
    }, expected="당일 MMF는 감소했지만 5거래일 기준으로는 보합입니다.",
       forbidden=("5거래일 흐름과 같은 방향",))

    # This catches mutations after the narrative builder has completed.
    trial("tampered MMF narrative", corrupt=lambda text: text.replace(
        "당일에도 MMF가 증가", "당일 MMF는 감소", 1
    ))
    trial("tampered MMF cash-direction arrow", corrupt=lambda text: text.replace(
        "MMF +4.93조↑", "MMF +4.93조↓", 1
    ))
    trial("tampered signed MMF headline", corrupt=lambda text: text.replace(
        "1D +4.93조 | 5D +24.45조", "1D -4.93조 | 5D +24.45조", 1
    ))
    trial("mismatched KOFIA dates", bad_dates=True)
    print("PASS all KOFIA directional and final-message regression scenarios")


if __name__ == "__main__":
    run_all()
