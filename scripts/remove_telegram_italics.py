#!/usr/bin/env python3
from pathlib import Path
import shutil

FILES = (
    Path("out/pjm_data_center_policy_alert.txt"),
    Path("out/us_data_center_time_to_power_alert.txt"),
)

PJM_FORMAT_ONLY_TITLE = "PJM 데이터센터 전력정책 알림 표시방식 업그레이드 완료"

STATE_GATES = (
    (
        Path("out/data_center_growth_alert.txt"),
        Path("out/data_center_growth_pending_state.json"),
        Path("data/data_center_growth_state.json"),
    ),
    (
        Path("out/pjm_data_center_policy_alert.txt"),
        Path("out/pjm_data_center_policy_pending_state.json"),
        Path("data/pjm_data_center_policy_state.json"),
    ),
    (
        Path("out/us_data_center_time_to_power_alert.txt"),
        Path("out/us_data_center_time_to_power_pending_state.json"),
        Path("data/us_data_center_time_to_power_state.json"),
    ),
)


def main() -> None:
    changed = 0
    suppressed = 0
    frozen_states = 0
    for path in FILES:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")

        # A presentation-format version change is not an underlying policy/data
        # change. Keep it out of Telegram entirely.
        if path.name == "pjm_data_center_policy_alert.txt" and PJM_FORMAT_ONLY_TITLE in text:
            path.unlink()
            suppressed += 1
            continue

        cleaned = (
            text.replace("<i>", "")
                .replace("</i>", "")
                .replace("<em>", "")
                .replace("</em>", "")
        )
        if cleaned != text:
            path.write_text(cleaned, encoding="utf-8")
            changed += 1

    # The workflow's save step copies pending state unconditionally. When there
    # is no Telegram alert, replace that pending state with the last confirmed
    # repository state so silent checks cannot advance dedupe/baseline state.
    # If an alert exists, leave the pending state untouched; a send failure
    # stops the job before the save step, while a successful send can persist it.
    for alert_path, pending_path, confirmed_path in STATE_GATES:
        if alert_path.exists() and alert_path.read_text(encoding="utf-8").strip():
            continue
        if pending_path.exists() and confirmed_path.exists():
            shutil.copyfile(confirmed_path, pending_path)
            frozen_states += 1

    print(
        f"telegram_italics_removed files={changed} "
        f"format_only_suppressed={suppressed} silent_states_frozen={frozen_states}"
    )


if __name__ == "__main__":
    main()
