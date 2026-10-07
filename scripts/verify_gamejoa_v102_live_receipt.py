#!/usr/bin/env python3
"""Replay one acknowledged live packet against the current selection rules."""

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamejoa_preopen_news_radar_full_compact_runner as radar
import verify_gamejoa_generated_report as generated_guard


ROOT = Path(__file__).resolve().parent.parent
PROOF_PATH = ROOT / "data/gamejoa_verified_core_receipts.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, required=True)
    args = parser.parse_args()
    report_path = args.artifact_dir / "out/gamejoa_preopen_news_radar.json"
    delivery_path = args.artifact_dir / "out/gamejoa_preopen_news_radar_delivery.json"
    markdown_path = args.artifact_dir / "out/gamejoa_preopen_news_radar.md"
    seen_path = args.artifact_dir / "data/gamejoa_preopen_news_radar_seen.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    delivery = json.loads(delivery_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_bytes()
    proofs = json.loads(PROOF_PATH.read_text(encoding="utf-8"))["entries"]
    assert delivery["status"] == "sent" and delivery["message_id"] == 2373
    assert hashlib.sha256(markdown).hexdigest() == delivery["report_sha256"]
    assert len(report["alerts"]) == 7
    assert all(item.get("body_verified") and item.get("source_body") for item in report["alerts"])
    assert generated_guard.duplicate_event_errors(report["alerts"], radar)
    for proof in proofs:
        item = next(row for row in report["alerts"] if row["link"] == proof["link"])
        assert item["source_title"] == proof["source_title"]
        assert item["published"] == proof["source_published_kst"]
        assert item["telegram_core_fact"] == proof["telegram_core_fact"]
        assert hashlib.sha256(item["source_body"].encode("utf-8")).hexdigest() == proof["source_body_sha256"]
        assert radar.market_materiality.verified_source_body_digest(item) == proof["source_body_digest"]
        assert item["link"] in markdown.decode("utf-8")
    assert len({proof["telegram_core_fact"] for proof in proofs}) == 1

    now = dt.datetime.fromisoformat(report["query_time_kst"])
    with patch.object(radar.base, "kst_now", return_value=now), patch.dict(os.environ, {"RADAR_RUN_MODE": "live"}):
        selected = radar.quality_display_alerts(report["alerts"], 20)
    selected_titles = [item["source_title"] for item in selected]
    assert len(selected) == 4, selected_titles
    assert sum("리사 수" in title for title in selected_titles) == 1, selected_titles
    assert not any("PEF 순기능" in title for title in selected_titles), selected_titles
    boston = next(item for item in report["alerts"] if "보스턴다이나믹스" in item["source_title"])
    observed_boston = radar.source_headline_event_fact(boston["source_title"], boston["source_body"])
    assert "로히트 프라사드" in observed_boston and "신임 CEO" in observed_boston
    assert boston["_exclusion_reason"].startswith("core_fact_guard:"), boston["_exclusion_reason"]
    assert not any("보스턴다이나믹스" in title for title in selected_titles), selected_titles
    assert not generated_guard.duplicate_event_errors(selected, radar)

    state = json.loads(seen_path.read_text(encoding="utf-8"))
    radar.telegram.migrate_seen_verified_core_receipts(state)
    core = radar.telegram.base.norm(proofs[0]["telegram_core_fact"])
    core_key = "core:" + radar.telegram.digest_seen(core)
    assert state["seen"][core_key]["core_alias_evidence_message_id"] == 2373
    replay = dict(next(item for item in report["alerts"] if item["link"] == proofs[0]["link"]))
    replay["link"] = "https://example.com/independent-syndication"
    with patch.object(radar.telegram, "load_seen_state", return_value={"seen": {core_key: state["seen"][core_key]}}):
        fresh, skipped = radar.telegram.filter_previously_seen_alerts([replay], now + dt.timedelta(minutes=5), "live")
    assert not fresh and len(skipped) == 1
    print(json.dumps({
        "acknowledged_message_id": 2373,
        "source_bodies_checked": len(report["alerts"]),
        "old_packet_duplicate_errors": len(generated_guard.duplicate_event_errors(report["alerts"], radar)),
        "selected_after_fix": len(selected),
        "same_core_in_packet": sum("리사 수" in title for title in selected_titles),
        "opinion_excluded": True,
        "prior_receipt_blocks_new_url": True,
        "boston_weak_market_change_withheld": True,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
