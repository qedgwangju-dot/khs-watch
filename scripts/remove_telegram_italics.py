#!/usr/bin/env python3
from pathlib import Path

FILES = (
    Path("out/pjm_data_center_policy_alert.txt"),
    Path("out/us_data_center_time_to_power_alert.txt"),
)


def main() -> None:
    changed = 0
    for path in FILES:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        cleaned = (
            text.replace("<i>", "")
                .replace("</i>", "")
                .replace("<em>", "")
                .replace("</em>", "")
        )
        if cleaned != text:
            path.write_text(cleaned, encoding="utf-8")
            changed += 1
    print(f"telegram_italics_removed files={changed}")


if __name__ == "__main__":
    main()
