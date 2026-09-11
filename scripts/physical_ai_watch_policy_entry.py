#!/usr/bin/env python3
"""Final physical-AI watcher entrypoint with Korean rendering and policy lane."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Import display first so its rendering-only Korean hook stays active.
import physical_ai_watch_korean_display as display
import physical_ai_watch_humanoid_component_policy as policy
import physical_ai_watch_hyundai_atlas_rollout as atlas_rollout

base = atlas_rollout.base
_orig_select_diverse = base.select_diverse
_orig_same_event = atlas_rollout.ext._same_event

_CZECH_SITE = re.compile(r'체코|Czech|노쇼비체|Nosovice|Nošovice|\bHMMC\b', re.I)
_ATLAS = re.compile(r'아틀라스|\bAtlas\b|Boston\s*Dynamics|보스턴다이내믹스|보스턴\s*다이내믹스', re.I)
_STRONG_CZECH_MILESTONE = re.compile(
    r'(?:시험|테스트|실증|검증).{0,12}(?:시작|개시|완료)|'
    r'(?:배치|투입).{0,12}(?:확정|시작|개시|완료)|'
    r'\b\d{1,5}\s*대\b|설비\s*투자|투자액|capex|발주|본계약|공급\s*계약|'
    r'pilot\s+(?:start|begin)|deployment\s+(?:confirmed|start)|purchase\s+order',
    re.I,
)


def same_event_with_czech_rollout_dedupe(a: dict, b: dict) -> bool:
    """Collapse syndicated Czech Atlas discussion stories without hiding new milestones."""
    if _orig_same_event(a, b):
        return True
    if a.get('group') != 'hyundai_atlas_rollout' or b.get('group') != 'hyundai_atlas_rollout':
        return False

    ta = f"{a.get('title', '')} {a.get('description', '')}"
    tb = f"{b.get('title', '')} {b.get('description', '')}"
    title_a = a.get('title', '')
    title_b = b.get('title', '')

    # Same Czech/Nošovice rollout discussion is often rewritten as
    # '검토', '추진', or '글로벌 확대'. Treat these as one event unless
    # either headline contains a genuinely stronger operating milestone.
    if _CZECH_SITE.search(ta) and _CZECH_SITE.search(tb) and _ATLAS.search(ta) and _ATLAS.search(tb):
        if not _STRONG_CZECH_MILESTONE.search(title_a) and not _STRONG_CZECH_MILESTONE.search(title_b):
            return True
    return False


atlas_rollout.ext._same_event = same_event_with_czech_rollout_dedupe


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
