#!/usr/bin/env python3
"""Inspect real source-alignment failures without publishing or changing seen state."""

import json
import os
from pathlib import Path
import sys

os.environ["SEND_TELEGRAM"] = "false"
os.environ["RADAR_RUN_MODE"] = "live"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamejoa_preopen_news_radar_fda_quality_runner as production


def main() -> int:
    radar = production.runner
    now = radar.base.kst_now()
    rows, _notes = production.contract.strict.collect_items(now)
    inspected = 0
    for row in rows:
        if not row.get("body_verified"):
            continue
        alert = production.contract.strict.classify(row, now)
        if not alert or not alert.get("korean_business_news"):
            continue
        normalized = radar.normalize_alert_for_output(alert)
        if radar.source_output_aligned(normalized):
            continue
        title = str(normalized.get("source_title") or "")
        core = str(normalized.get("telegram_core_fact") or normalized.get("policy_plain_summary") or "")
        print(json.dumps({
            "source_title": title,
            "rendered_title": normalized.get("news"),
            "core": core,
            "link": normalized.get("link"),
            "kind": normalized.get("korean_business_kind"),
            "body_verified": normalized.get("body_verified"),
            "title_core_aligned": radar.korean_title_core_aligned(title, core),
            "core_has_ui_garbage": radar.core_has_ui_garbage(core),
            "source_allowed": radar.korean_business_source_allowed(normalized),
            "body_start": str(row.get("source_body") or "")[:1100],
        }, ensure_ascii=False))
        inspected += 1
        if inspected == 8:
            break
    print(f"source_alignment_samples={inspected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
