#!/usr/bin/env python3
"""Conservative event-level guard for space launch monitoring."""
from __future__ import annotations
import space_launch_bottleneck_watch as watch
import space_launch_event_guard as guard

import datetime as dt
import re
_ORIG_SCORE=watch.signal_score

def score(category,item):
    if not guard.eligible(category.key,item,watch.NOW):return -100
    return _ORIG_SCORE(category,item)

def corroboration(category,item,peers):
    if not guard.eligible(category.key,item,watch.NOW):return False
    if watch.source_is_official(item):return True
    if not watch.source_is_trusted(item):return False
    return any(peer is not item and watch.source_is_trusted(peer)
               and guard.semantic_pair(category.key,item,peer) for peer in peers)
