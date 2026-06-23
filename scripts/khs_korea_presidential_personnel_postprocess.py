#!/usr/bin/env python3
"""Render Korea presidential personnel alerts as a separate Telegram lane."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

OUT_DIR = Path("out")
MODULE_PATH = Path("scripts/korea_presidential_postprocess.py")

REPORT_PATH = OUT_DIR / "khs_korea_presidential_personnel.md"
ALERT_PATH = OUT_DIR / "khs_korea_presidential_personnel_alert.md"
TITLE_PATH = OUT_DIR / "khs_korea_presidential_personnel_title.txt"
ALERTS_JSON_PATH = OUT_DIR / "khs_korea_presidential_personnel_alerts.json"


def load_renderer():
    spec = importlib.util.spec_from_file_location("korea_presidential_postprocess", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rebrand_output() -> None:
    for path in (REPORT_PATH, ALERT_PATH):
        if not path.exists():
            continue
        body = path.read_text(encoding="utf-8")
        body = body.replace(
            "🚨 KHS 정책·규제 고충격 워치",
            "🚨 KHS 대통령실/청와대 고위급 인사 워치",
            1,
        )
        body = body.replace(
            "대통령실/청와대 고위급 인사 브리핑:",
            "공식 인사 브리핑:",
            1,
        )
        path.write_text(body, encoding="utf-8")

    if TITLE_PATH.exists():
        title = TITLE_PATH.read_text(encoding="utf-8")
        count_match = re.search(r"(\d+)건", title)
        count_text = count_match.group(1) if count_match else "확인"
        TITLE_PATH.write_text(
            f"KHS 청와대 인사 워치: 고위급 인사 {count_text}건 확인\n",
            encoding="utf-8",
        )


def main() -> int:
    renderer = load_renderer()
    renderer.REPORT_PATH = REPORT_PATH
    renderer.ALERT_PATH = ALERT_PATH
    renderer.TITLE_PATH = TITLE_PATH
    renderer.ALERTS_JSON_PATH = ALERTS_JSON_PATH
    code = renderer.main()
    rebrand_output()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
