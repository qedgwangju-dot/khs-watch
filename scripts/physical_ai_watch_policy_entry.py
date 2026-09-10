#!/usr/bin/env python3
"""Final physical-AI watcher entrypoint with Korean rendering and policy lane."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Import display first so its rendering-only Korean hook stays active.
import physical_ai_watch_korean_display as display
import physical_ai_watch_humanoid_component_policy as policy

base = policy.base
_orig_select_diverse = base.select_diverse


def select_diverse_with_ess_priority(items: list[dict], seen: set[str], force: bool, limit: int) -> list[dict]:
    """Keep the separate stationary ESS lane from being crowded out by other lanes."""
    chosen = _orig_select_diverse(items, seen, force, limit)
    candidates = items if force else [x for x in items if x.get('key') not in seen]
    ess = next((x for x in candidates if x.get('group') == 'ess_battery'), None)
    if not ess or any(x.get('key') == ess.get('key') for x in chosen):
        return chosen

    if len(chosen) < limit:
        return [ess, *chosen]

    # Preserve the limit while guaranteeing that one new ESS policy/price event
    # can surface when many physical-AI lanes fire at the same time.
    return [ess, *chosen[:-1]]


def repair_pending_seen(pre_state: dict) -> None:
    """Do not mark high-signal items as seen until they were actually selected.

    The base watcher intentionally seeds every current item on its very first run.
    After that baseline exists, only selected alerts should enter the dedup state;
    otherwise an item that lost the MAX_ALERTS competition can disappear forever
    without ever reaching Telegram.
    """
    if not pre_state.get('seeded') or not base.PENDING_PATH.exists():
        return

    pending = json.loads(base.PENDING_PATH.read_text(encoding='utf-8'))
    old_seen = list(pre_state.get('seen', []))
    old_seen_set = set(old_seen)
    repaired = list(old_seen)
    for key in pending.get('last_selected', []):
        if key not in old_seen_set:
            repaired.append(key)
            old_seen_set.add(key)
    pending['seen'] = repaired[-3500:]
    base.PENDING_PATH.write_text(
        json.dumps(pending, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )


base.select_diverse = select_diverse_with_ess_priority

if __name__ == '__main__':
    pre_state = base.load_state()
    base.main()
    repair_pending_seen(pre_state)
    if base.ALERT_PATH.exists():
        rendered = base.ALERT_PATH.read_text(encoding='utf-8')
        base.ALERT_PATH.write_text(display._inline_original_link(rendered), encoding='utf-8')
