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
    parser.add_argument("--market-scope-artifact-dir", type=Path)
    parser.add_argument("--follow-on-artifact-dir", type=Path)
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
    market_scope = None
    if args.market_scope_artifact_dir:
        scope_out = args.market_scope_artifact_dir / "out"
        scope_report = json.loads((scope_out / "gamejoa_preopen_news_radar.json").read_text(encoding="utf-8"))
        scope_delivery = json.loads((scope_out / "gamejoa_preopen_news_radar_delivery.json").read_text(encoding="utf-8"))
        scope_markdown = (scope_out / "gamejoa_preopen_news_radar.md").read_bytes()
        assert scope_delivery["status"] == "sent" and scope_delivery["message_id"] == 2388
        assert hashlib.sha256(scope_markdown).hexdigest() == scope_delivery["report_sha256"]
        assert len(scope_report["alerts"]) == 7
        assert all(item.get("body_verified") and item.get("source_body") for item in scope_report["alerts"])
        scope_now = dt.datetime.fromisoformat(scope_report["query_time_kst"])
        with patch.object(radar.base, "kst_now", return_value=scope_now), patch.dict(os.environ, {"RADAR_RUN_MODE": "live"}):
            scope_selected = radar.quality_display_alerts(scope_report["alerts"], 20)
        assert len(scope_selected) == 4, [item["source_title"] for item in scope_selected]
        selected_links = {item["link"] for item in scope_selected}
        rejected = {item["source_title"]: item.get("_exclusion_reason", "") for item in scope_report["alerts"]
                    if item["link"] not in selected_links}
        assert len(rejected) == 3, rejected
        assert any("인도 9월 서비스업 PMI" in title and "foreign_local_measure" in reason
                   for title, reason in rejected.items())
        assert any("파키스탄, 저소득층" in title and "foreign_local_measure" in reason
                   for title, reason in rejected.items())
        assert any("인천시, 글로벌캠퍼스" in title and "regional_pilot_facility" in reason
                   for title, reason in rejected.items())
        kept = {item["source_title"]: item["telegram_core_fact"] for item in scope_selected}
        assert any("LG전자" in title and "7천818억원" in core for title, core in kept.items())
        assert any("신규택지" in title and "7만3000가구" in core and "16만 가구" in core
                   for title, core in kept.items())
        assert any("포스코홀딩스" in title and "준공했다" in core and "2만3000톤" in core
                   and "4만8000톤" in core for title, core in kept.items())
        assert any("효성중공업" in title and "매출 인식 이연" in core and "2961억원" in core
                   for title, core in kept.items())
        assert not generated_guard.duplicate_event_errors(scope_selected, radar)
        assert all(not radar.source_core_fact_errors(item) for item in scope_selected)
        market_scope = {"acknowledged_message_id": 2388, "source_bodies_checked": 7,
                        "selected_after_fix": 4, "foreign_local_and_regional_pilot_withheld": 3,
                        "retained_cores_source_bound": 4}
    follow_on = None
    if args.follow_on_artifact_dir:
        follow_out = args.follow_on_artifact_dir / "out"
        follow_report = json.loads((follow_out / "gamejoa_preopen_news_radar.json").read_text(encoding="utf-8"))
        follow_delivery = json.loads((follow_out / "gamejoa_preopen_news_radar_delivery.json").read_text(encoding="utf-8"))
        follow_markdown = (follow_out / "gamejoa_preopen_news_radar.md").read_bytes()
        assert follow_delivery["status"] == "sent" and follow_delivery["message_id"] == 2389
        assert hashlib.sha256(follow_markdown).hexdigest() == follow_delivery["report_sha256"]
        assert len(follow_report["alerts"]) == 7
        assert all(item.get("body_verified") and item.get("source_body") for item in follow_report["alerts"])
        follow_now = dt.datetime.fromisoformat(follow_report["query_time_kst"])
        with patch.object(radar.base, "kst_now", return_value=follow_now), patch.dict(os.environ, {"RADAR_RUN_MODE": "live"}):
            follow_selected = radar.quality_display_alerts(follow_report["alerts"], 20)
        assert len(follow_selected) == 5, [item["source_title"] for item in follow_selected]
        follow_kept = {item["source_title"]: item["telegram_core_fact"] for item in follow_selected}
        assert any("우크라" in title and "17만 6000t" in core and "가디언" in core
                   for title, core in follow_kept.items())
        assert any("삼미금속" in title and "한화파워" in core and "본격 공급을 시작" in core
                   for title, core in follow_kept.items())
        assert any("한성크린텍" in title and "삼성이앤에이" in core and "230억원" in core
                   and "2027년 6월 30일" in core for title, core in follow_kept.items())
        assert any("삼전닉스" in title and "대신증권" in core and "110조원" in core
                   for title, core in follow_kept.items())
        assert any("블룸버그" in title and "23%포인트" in core and "40%" in core
                   and "25%" in core for title, core in follow_kept.items())
        follow_rejected = {item["source_title"]: item.get("_exclusion_reason", "")
                           for item in follow_report["alerts"] if item["link"] not in
                           {kept["link"] for kept in follow_selected}}
        assert len(follow_rejected) == 2, follow_rejected
        assert any("한화, AI 에너지" in title and "media_recognition" in reason
                   for title, reason in follow_rejected.items())
        assert any("[株토피아]" in title and "multi_issuer_analyst_roundup" in reason
                   for title, reason in follow_rejected.items())
        assert not generated_guard.duplicate_event_errors(follow_selected, radar)
        assert all(not radar.source_core_fact_errors(item) for item in follow_selected)
        follow_on = {"acknowledged_message_id": 2389, "source_bodies_checked": 7,
                     "selected_after_fix": 5, "roundup_and_award_withheld": 2,
                     "retained_cores_source_bound": 5}
    print(json.dumps({
        "acknowledged_message_id": 2373,
        "source_bodies_checked": len(report["alerts"]),
        "old_packet_duplicate_errors": len(generated_guard.duplicate_event_errors(report["alerts"], radar)),
        "selected_after_fix": len(selected),
        "same_core_in_packet": sum("리사 수" in title for title in selected_titles),
        "opinion_excluded": True,
        "prior_receipt_blocks_new_url": True,
        "boston_weak_market_change_withheld": True,
        "market_scope_replay": market_scope,
        "follow_on_replay": follow_on,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
