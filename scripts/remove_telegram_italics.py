#!/usr/bin/env python3
from pathlib import Path
import json
import shutil
import subprocess

FILES = (
    Path("out/pjm_data_center_policy_alert.txt"),
    Path("out/us_data_center_time_to_power_alert.txt"),
    Path("out/us_data_center_generation_buildout_alert.txt"),
    Path("out/us_data_center_cancellation_risk_alert.txt"),
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
    (
        Path("out/us_data_center_generation_buildout_alert.txt"),
        Path("out/us_data_center_generation_buildout_pending_state.json"),
        Path("data/us_data_center_generation_buildout_state.json"),
    ),
    (
        Path("out/us_data_center_cancellation_risk_alert.txt"),
        Path("out/us_data_center_cancellation_risk_pending_state.json"),
        Path("data/us_data_center_cancellation_risk_state.json"),
    ),
)


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> None:
    changed = 0
    suppressed = 0
    frozen_states = 0
    migration_suppressed: set[str] = set()

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

    # The first power-bottleneck upgrade messages were already delivered on the
    # preceding run, but that run failed only while committing state because the
    # generation watcher was still runtime-patched.  Suppress only that migration
    # replay while preserving the pending state so the next successful run can
    # lock the delivered baseline without sending duplicates.
    pjm_alert = Path("out/pjm_data_center_policy_alert.txt")
    pjm_pending_path = Path("out/pjm_data_center_policy_pending_state.json")
    pjm_confirmed_path = Path("data/pjm_data_center_policy_state.json")
    pjm_pending = load_json(pjm_pending_path)
    pjm_confirmed = load_json(pjm_confirmed_path)
    if (
        pjm_alert.exists()
        and int(pjm_confirmed.get("format_version", 0) or 0) < 6
        and int(pjm_pending.get("format_version", 0) or 0) >= 6
        and (pjm_pending.get("baseline") or {}).get("capacity_delivery_year")
    ):
        pjm_alert.unlink()
        suppressed += 1
        migration_suppressed.add(pjm_alert.name)

    gen_alert = Path("out/us_data_center_generation_buildout_alert.txt")
    gen_pending_path = Path("out/us_data_center_generation_buildout_pending_state.json")
    gen_confirmed_path = Path("data/us_data_center_generation_buildout_state.json")
    gen_pending = load_json(gen_pending_path)
    gen_confirmed = load_json(gen_confirmed_path)
    if (
        gen_alert.exists()
        and not gen_confirmed.get("power_metrics")
        and bool(gen_pending.get("power_metrics"))
    ):
        gen_alert.unlink()
        suppressed += 1
        migration_suppressed.add(gen_alert.name)

    # The workflow's save step copies pending state unconditionally. When there
    # is no Telegram alert, replace that pending state with the last confirmed
    # repository state so silent checks cannot advance dedupe/baseline state.
    # Migration-suppressed alerts are the exception: their Telegram delivery was
    # already confirmed, so preserve pending state to lock that delivered baseline.
    for alert_path, pending_path, confirmed_path in STATE_GATES:
        if alert_path.name in migration_suppressed:
            continue
        if alert_path.exists() and alert_path.read_text(encoding="utf-8").strip():
            continue
        if pending_path.exists() and confirmed_path.exists():
            shutil.copyfile(confirmed_path, pending_path)
            frozen_states += 1

    # guard_us_time_to_power_metrics_source.py runtime-patches the generation
    # watcher. Restore that tracked file before the workflow later runs
    # `git pull --rebase`, otherwise Git correctly refuses to rebase over the
    # unstaged runtime patch.
    subprocess.run(
        ["git", "restore", "scripts/us_data_center_generation_buildout_watch.py"],
        check=True,
    )

    print(
        f"telegram_italics_removed files={changed} "
        f"suppressed={suppressed} migration_suppressed={len(migration_suppressed)} "
        f"silent_states_frozen={frozen_states} generation_runtime_restored=true"
    )


if __name__ == "__main__":
    main()
