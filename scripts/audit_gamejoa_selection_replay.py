#!/usr/bin/env python3
"""Read-only replay of downloaded delivery receipts and a full user inventory."""

import argparse
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import gamejoa_preopen_news_radar_fda_quality_runner as production


radar = production.runner


def replay(runs):
    state = {"seen": {}}
    rows, identities, sent_runs = [], {}, 0
    for run in sorted(runs, key=lambda item: item["query_time"]):
        if run["delivery"].get("status") != "sent":
            continue
        sent_runs += 1
        now = dt.datetime.fromisoformat(run["query_time"])
        lane = "preopen" if (now.hour, now.minute) >= (6, 30) and (now.hour, now.minute) < (6, 40) else "live"
        candidates = copy.deepcopy(run["alerts"])
        with patch.dict("os.environ", {"RADAR_RUN_MODE": lane}), \
                patch.object(radar.base, "kst_now", return_value=now), \
                patch.object(radar.telegram, "load_seen_state", return_value=state), \
                patch.object(radar.telegram, "save_seen_state", side_effect=lambda *_args: None):
            qualifying = radar.quality_display_alerts(candidates, max(7, len(candidates)))
            fresh, duplicates = radar.telegram.filter_previously_seen_alerts(qualifying, now, lane)
            fresh_links = {item["link"] for item in fresh}
            duplicate_links = {item["link"] for item in duplicates}
            radar.telegram.record_seen_alerts(fresh, now)
        for item in candidates:
            identity = radar.market_materiality.source_event_identity(item)
            if identity and lane == "live":
                identities.setdefault(identity, []).append({"run_id": run["run_id"], "title": item["news"]})
            duplicate = item["link"] in duplicate_links or item.get("_exclusion_reason") == "semantic_duplicate"
            result = "retained" if item["link"] in fresh_links else "duplicate" if duplicate else "quality_excluded"
            normalized = radar.normalize_alert_for_output(item)
            rows.append({
                "run_id": run["run_id"], "query_time": run["query_time"], "lane": lane,
                "title": item.get("source_title") or item["news"], "link": item["link"],
                "original_core": item.get("telegram_core_fact"),
                "revalidated_core": normalized.get("telegram_core_fact"),
                "result": result, "reason": item.get("_exclusion_reason") if result == "quality_excluded" else result,
                "source_event_identity": identity,
            })
    return {
        "sent_runs": sent_runs, "original_article_rows": len(rows),
        "retained": sum(item["result"] == "retained" for item in rows),
        "duplicate": sum(item["result"] == "duplicate" for item in rows),
        "quality_excluded": sum(item["result"] == "quality_excluded" for item in rows),
        "repeated_source_events": {key: entries for key, entries in identities.items() if len(entries) > 1},
        "articles": rows,
    }


def inventory(sources, now):
    results = []
    for source in sources:
        detail = source["detail"]
        verified = bool(detail.get("body_verified") and detail.get("body"))
        title = detail.get("title") if verified else source["provided_title"]
        entry = {
            "id": source["id"], "provided_title": source["provided_title"], "source_title": title,
            "link": source["url"], "body_verified": verified,
            "source_body_sha256": hashlib.sha256(detail.get("body", "").encode()).hexdigest() if verified else None,
            "published_kst": detail.get("published_kst"), "fetch_error": source.get("error"),
        }
        if not verified:
            entry.update(disposition="unresolved_source", reason="google_news_shell_is_not_article_body", core="")
        else:
            entry["materiality"] = radar.market_materiality.assess(title, radar.article_summary_body(detail["body"]))
            publisher = "ZDNet Korea" if "zdnet.co.kr" in source["url"] else "연합뉴스" if "yna.co.kr" in source["url"] else "South China Morning Post"
            classified = production.contract.strict.classify({
                "title": title, "summary": detail.get("abstract"), "source_abstract": detail.get("abstract"),
                "source_body": detail["body"], "body_verified": True, "layer": "trusted",
                "publisher": publisher, "published": radar.detail_queue.parse_time(detail["published_kst"]),
                "link": source["url"],
            }, now)
            if classified:
                candidate = copy.deepcopy(classified)
                with patch.object(radar.base, "kst_now", return_value=now):
                    selected = radar.quality_display_alerts([candidate], 7)
                normalized = radar.normalize_alert_for_output(candidate)
                entry.update(
                    disposition="eligible" if selected else "not_selected",
                    reason=None if selected else candidate.get("_exclusion_reason"),
                    materiality=radar.source_market_materiality(candidate),
                    core=normalized.get("telegram_core_fact"),
                    core_errors=radar.source_core_fact_errors(normalized),
                    source_output_aligned=radar.source_output_aligned(normalized),
                )
            else:
                entry.update(disposition="not_selected", reason="classifier_not_eligible", core="")
        results.append(entry)
    assert len(results) == len(sources)
    return {"original_count": len(sources), "unique_count": len({item["url"] for item in sources}),
            "body_verified": sum(item["body_verified"] for item in results), "articles": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runs = json.loads(args.runs.read_text(encoding="utf-8-sig"))
    now = max(dt.datetime.fromisoformat(run["query_time"]) for run in runs)
    result = {
        "read_only": True, "telegram_api_called": False, "production_seen_state_modified": False,
        "materiality_version": radar.market_materiality.VERSION,
        "input_sha256": {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in (args.runs, args.sources)},
        "production_replay": replay(runs),
        "user_inventory": inventory(json.loads(args.sources.read_text(encoding="utf-8-sig")), now),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "production_replay": {key: value for key, value in result["production_replay"].items() if key not in ("articles", "repeated_source_events")},
        "user_inventory": result["user_inventory"],
        "output": str(args.output),
    }, ensure_ascii=False, indent=2))
