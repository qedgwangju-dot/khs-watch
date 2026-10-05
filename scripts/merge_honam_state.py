#!/usr/bin/env python3
import json
import pathlib
import sys

latest_path = pathlib.Path(sys.argv[1])
pending_path = pathlib.Path(sys.argv[2])
out_path = pathlib.Path(sys.argv[3])

latest = json.loads(latest_path.read_text(encoding='utf-8')) if latest_path.exists() else {}
pending = json.loads(pending_path.read_text(encoding='utf-8')) if pending_path.exists() else {}
merged = dict(latest)
merged.update(pending)

for key, limit in [
    ('seen_ids', 3000),
    ('seen_story_keys', 3000),
    ('seen_headline_keys', 3000),
    ('seen_url_keys', 3000),
    ('seen_event_keys', 3000),
]:
    vals = []
    for src in [pending.get(key, []), latest.get(key, [])]:
        for v in src:
            if v not in vals:
                vals.append(v)
    merged[key] = vals[:limit]

# Merge per-event verification/action levels monotonically so concurrent runs
# cannot lower a previously confirmed state.
for dict_key in ('event_status_levels', 'event_action_levels'):
    merged_levels = {}
    for src in [latest.get(dict_key, {}), pending.get(dict_key, {})]:
        for key, value in (src or {}).items():
            try:
                level = int(value)
            except (TypeError, ValueError):
                continue
            merged_levels[str(key)] = max(level, merged_levels.get(str(key), 0))
    merged[dict_key] = merged_levels

# Preserve the earliest monitor start and the newest explicit event-state policy.
if latest.get('monitor_started_at_kst'):
    merged['monitor_started_at_kst'] = latest['monitor_started_at_kst']
merged['alert_basis'] = 'topic_event_official_state_change'
merged['article_role'] = 'evidence_and_crosscheck_only'

out_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('state_merged=true')
