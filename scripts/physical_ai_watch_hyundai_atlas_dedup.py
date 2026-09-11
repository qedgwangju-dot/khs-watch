#!/usr/bin/env python3
"""Tighten same-event dedup for Hyundai Atlas Czech/Europe rollout coverage.

This layer keeps the existing Atlas rollout watcher intact, but collapses syndicated
rewrites of the same Czech/Nošovice discussion. A later Czech-local hard milestone
(test start, signed order, unit count, capex, named process, or formal deployment)
remains eligible as a genuinely new event.
"""
from __future__ import annotations

import re

import physical_ai_watch_hyundai_atlas_rollout as rollout

base = rollout.base
ext = rollout.ext
_orig_same_event = ext._same_event

# Media often rewrites the same HMMC executive quote as "논의", "검토", or "추진".
# Treat those as the same pre-deployment stage unless a Czech-local hard milestone appears.
rollout.DISCUSSION = re.compile(
    r'논의|협의|검토|추진|타진|도입\s*(?:논의|검토|추진)|가능한\s*한\s*빨리|희망|원한다|'
    r'discuss|talks?|consider|pursu(?:e|ing)|explor(?:e|ing)|would\s+like|as\s+soon\s+as\s+possible',
    re.I,
)

CZECH = re.compile(
    r'체코|Czech|노쇼비체|Nosovice|Nošovice|Hyundai\s*Motor\s*Manufacturing\s*Czech|\bHMMC\b',
    re.I,
)
ATLAS = rollout.ATLAS

# Require the concrete milestone to be locally tied to the Czech site. This avoids
# treating the already-known US 2028 sequencing plan, often repeated in Czech stories,
# as a new Czech milestone.
LOCAL_HARD = re.compile(
    r'(?:체코|Czech|노쇼비체|Nosovice|Nošovice|\bHMMC\b).{0,140}'
    r'(?:시험\s*(?:시작|개시)|테스트\s*(?:시작|개시)|실증\s*(?:시작|개시)|'
    r'정식\s*(?:배치|투입|운영)|계약\s*(?:체결|확정)|발주|수주|'
    r'\d[\d,]*\s*대|설비\s*투자|투자액|capex|시퀀싱|sequencing|조립|assembly|'
    r'pilot\s*(?:start|launch)|deployment\s*(?:start|date)|signed\s*(?:order|contract))'
    r'|'
    r'(?:시험\s*(?:시작|개시)|테스트\s*(?:시작|개시)|실증\s*(?:시작|개시)|'
    r'정식\s*(?:배치|투입|운영)|계약\s*(?:체결|확정)|발주|수주|'
    r'\d[\d,]*\s*대|설비\s*투자|투자액|capex|시퀀싱|sequencing|조립|assembly|'
    r'pilot\s*(?:start|launch)|deployment\s*(?:start|date)|signed\s*(?:order|contract))'
    r'.{0,140}(?:체코|Czech|노쇼비체|Nosovice|Nošovice|\bHMMC\b)',
    re.I | re.S,
)


def _same_event(a: dict, b: dict) -> bool:
    if _orig_same_event(a, b):
        return True
    if a.get('group') != 'hyundai_atlas_rollout' or b.get('group') != 'hyundai_atlas_rollout':
        return False

    ta = f"{a.get('title','')} {a.get('description','')}"
    tb = f"{b.get('title','')} {b.get('description','')}"

    # Collapse same-day/syndicated Czech rollout rewrites while preserving a later
    # operational milestone as a separate alert.
    if (
        CZECH.search(ta) and CZECH.search(tb)
        and ATLAS.search(ta) and ATLAS.search(tb)
        and not LOCAL_HARD.search(ta) and not LOCAL_HARD.search(tb)
    ):
        return True
    return False


ext._same_event = _same_event

if __name__ == '__main__':
    base.main()
