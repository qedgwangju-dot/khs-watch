#!/usr/bin/env python3
from pathlib import Path

FILES = (
    Path("out/pjm_data_center_policy_alert.txt"),
    Path("out/us_data_center_time_to_power_alert.txt"),
)

PJM_FORMAT_ONLY_TITLE = "PJM 데이터센터 전력정책 알림 표시방식 업그레이드 완료"


def main() -> None:
    changed = 0
    suppressed = 0
    for path in FILES:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")

        # A presentation-format version change is not an underlying policy/data
        # change. Keep the pending state migration, but do not emit a Telegram
        # alert solely because FORMAT_VERSION changed.
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
    print(f"telegram_italics_removed files={changed} format_only_suppressed={suppressed}")


if __name__ == "__main__":
    main()
