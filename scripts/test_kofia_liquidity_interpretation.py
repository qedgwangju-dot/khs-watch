#!/usr/bin/env python3
"""Regression tests for the existing KOFIA Telegram interpretation step.

The exact embedded production Python is executed using synthetic KOFIA state.
No web access, Telegram calls, or modification of production state is required.
"""
import json
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

WORKFLOW = Path(".github/workflows/kofia-liquidity-telegram-watch.yml")
START = "      - name: Build detailed current interpretation"
HEREDOC = "          python - <<'PY'\n"
END = "\n          PY"


def production_python():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    section = workflow.split(START, 1)[1]
    python_section = section.split(HEREDOC, 1)[1].split(END, 1)[0]
    return textwrap.dedent(python_section)


def trial(name, mmf_1d, mmf_5d, expected, forbidden=(), bad_dates=False):
    with tempfile.TemporaryDirectory(prefix="kofia_interpret_") as root:
        base = Path(root)
        (base / "out").mkdir()
        (base / "out/kofia_liquidity_alert.html").write_text(
            "<b>[국내 증시 대기자금 추적]</b>\n"
            "<b>무엇이 달라졌나</b>\n• MMF 설정원본 <b>262.89조</b>\n"
            "<b>현재 판정</b>\n• 원본 간략 판정\n\n"
            "<b>검증</b>\n• 공식 원천\n",
            encoding="utf-8",
        )
        values = {
            "deposit": {"date": "20261007", "value": 100379607, "d1": -669020, "d5": -7346063},
            "mmf": {"date": "20261007", "value": 262894698, "d1": mmf_1d, "d5": mmf_5d},
            "cma": {"date": "20261007", "value": 105624312, "d1": 2628244, "d5": -949377},
            "credit": {"date": "20261007", "value": 33516739, "d1": -42404, "d5": 596734},
        }
        dates = {key: "20261007" for key in ("deposit", "mmf", "cma", "credit")}
        if bad_dates:
            dates["mmf"] = "20261006"
        pending = {
            "values": values,
            "dates": dates,
            "alignment_ready": True,
            "snapshot_date": "20261007",
        }
        (base / "out/kofia_liquidity_pending_state.json").write_text(
            json.dumps(pending), encoding="utf-8"
        )
        done = subprocess.run(
            [sys.executable, "-c", production_python()],
            cwd=base, text=True, capture_output=True,
        )
        if bad_dates:
            assert done.returncode != 0, (name, done.stdout, done.stderr)
            assert "date quality gate failed" in done.stderr, (name, done.stderr)
            print(f"PASS {name}: mismatched reference date blocks interpretation")
            return
        assert done.returncode == 0, (name, done.stdout, done.stderr)
        text = (base / "out/kofia_liquidity_alert.html").read_text(encoding="utf-8")
        assert expected in text, (name, expected, text)
        for phrase in forbidden:
            assert phrase not in text, (name, phrase, text)
        assert text.count("<b>현재 판정</b>") == 1, (name, text)
        assert "<b>검증</b>" in text, (name, text)
        print(f"PASS {name}: narrative direction and output structure")


if __name__ == "__main__":
    trial(
        "current actual 2026-10-07", 4928506, 24445118,
        "당일에도 MMF가 증가해 5거래일 누적 증가 방향과 일치합니다.",
        ("당일 MMF 급감", "당일 MMF는 감소", "당일 MMF 감소"),
    )
    trial(
        "one-day MMF decrease with five-day growth", -6000000, 24445118,
        "당일 MMF는 감소해 5거래일 누적 증가 방향과 반대로 움직였습니다.",
        ("당일에도 MMF가 증가", "당일 MMF 급증"),
    )
    trial(
        "one-day MMF unchanged", 0, 24445118,
        "당일 MMF는 유의미한 증감 없이 보합입니다.",
        ("당일 MMF 급감", "당일 MMF 급증"),
    )
    trial(
        "one-day increase with five-day decline", 4928506, -24445118,
        "당일 MMF가 증가했으나 5거래일 추세와 방향이 다릅니다.",
        ("당일 MMF 급감", "당일 MMF는 감소"),
    )
    trial("mismatched KOFIA dates", 4928506, 24445118, "", bad_dates=True)
    print("PASS all five KOFIA narrative regression scenarios")
