#!/usr/bin/env python3
"""Contract tests for KHS policy Telegram delivery quality.

These checks encode regressions that already reached Telegram once:
raw English titles, low-impact FCC administrative notices, and wrong sector
explanations. The workflow runs this before sending Telegram alerts.
"""

from __future__ import annotations

import json
from pathlib import Path

import khs_policy_alert_guardrails
import khs_policy_alert_router
import khs_telegram_delivery_guard


OUT_DIR = Path("out")
POLICY_FILES = [
    OUT_DIR / "khs_policy_watch_alerts.json",
    OUT_DIR / "khs_policy_watch_alert.md",
    OUT_DIR / "khs_policy_watch_alert_title.txt",
    OUT_DIR / "khs_policy_watch.md",
]


def main() -> int:
    OUT_DIR.mkdir(exist_ok=True)
    cleanup()
    try:
        write_fcc_regression_fixture()
        khs_policy_alert_guardrails.main()
        khs_policy_alert_router.main()
        khs_telegram_delivery_guard.main()
        assert_policy_output()
    finally:
        cleanup()
    print("khs_policy_delivery_contract=passed")
    return 0


def cleanup() -> None:
    for path in POLICY_FILES:
        if path.exists():
            path.unlink()


def write_fcc_regression_fixture() -> None:
    alerts = [
        {
            "source": "Federal Register FCC",
            "title": "Petition for Reconsideration of Action in Rulemaking Proceeding",
            "original_title": "Petition for Reconsideration of Action in Rulemaking Proceeding",
            "link": "https://www.federalregister.gov/documents/2026/07/06/2026-13611/petition-for-reconsideration-of-action-in-rulemaking-proceeding",
            "importance": "상",
            "status": "확정",
            "published_kst": "2026-07-06T09:00:00+09:00",
            "matched": {"fcc_decision_notice": ["proposed rule", "rulemaking"]},
            "impacts": ["시간표", "수급"],
            "paths": ["정책 타임라인", "주파수/통신 규제", "수급"],
            "sectors": ["통신/FCC/위성", "통신장비", "위성통신"],
        },
        {
            "source": "Federal Register FCC",
            "title": "Prohibiting Importation and Marketing of Previously Authorized Covered Communications Equipment Added to the Covered List",
            "original_title": "Prohibiting Importation and Marketing of Previously Authorized Covered Communications Equipment Added to the Covered List",
            "link": "https://www.federalregister.gov/documents/2026/07/06/2026-13518/prohibiting-importation-and-marketing-of-previously-authorized-covered-communications-equipment",
            "importance": "상",
            "status": "확정",
            "published_kst": "2026-07-06T09:00:00+09:00",
            "matched": {"fcc_decision_notice": ["covered list", "national security", "prohibit", "public notice"]},
            "impacts": ["매출·마진·현금흐름", "수급", "시간표"],
            "paths": ["정책 타임라인", "공급망", "밸류체인", "수급"],
            "sectors": ["통신장비", "위성통신", "네트워크 장비"],
        },
    ]
    (OUT_DIR / "khs_policy_watch_alerts.json").write_text(
        json.dumps(alerts, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def assert_policy_output() -> None:
    body_path = OUT_DIR / "khs_policy_watch_alert.md"
    if not body_path.exists():
        raise AssertionError("policy alert body was removed unexpectedly")
    body = body_path.read_text(encoding="utf-8-sig")
    lines = body.splitlines()

    must_contain = [
        "FCC, 보안 위험 통신장비 수입·판매 제한 절차 공표",
        "- 핵심:",
        "- 의사결정 영향:",
        "- 투자 영향:",
        "- 한국장:",
        "- 반영 가능성:",
        "- 반대 근거:",
        "- 실패 신호:",
        "- 출처:",
    ]
    for marker in must_contain:
        if marker not in body:
            raise AssertionError(f"missing compact Telegram marker: {marker}")

    forbidden = [
        "- 원제:",
        "- 상태 변화:",
        "- 즉시 체크:",
        "Petition for Reconsideration",
        "Prohibiting Importation and Marketing",
        "Previously Authorized Covered Communications Equipment",
        "인버터",
        "inverter",
        "신뢰외신",
        "fcc_decision_notice",
    ]
    low = body.lower()
    for marker in forbidden:
        haystack = low if marker.islower() else body
        needle = marker if marker.islower() else marker
        if needle in haystack:
            raise AssertionError(f"forbidden Telegram text leaked: {marker}")

    long_lines = [line for line in lines if len(line) > khs_telegram_delivery_guard.MAX_BODY_LINE_CHARS]
    if long_lines:
        raise AssertionError(f"overlong Telegram line leaked: {long_lines[0][:120]}")

    alert_count = sum(1 for line in lines if line.startswith("## "))
    if alert_count != 1:
        raise AssertionError(f"expected only one delivered alert, got {alert_count}")


if __name__ == "__main__":
    raise SystemExit(main())
