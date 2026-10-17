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

# A contract and a development delay require different alert labels.


def check_development(category, title):
    if category.key=='rocketlab':
        return guard.kind('rocketlab',title)=='development'
    return False

from dataclasses import replace
_RENDER=watch.render_item

def compact_report(cat,item,rate):
    tag=cat.tag
    if cat.key=='rocketlab':
        tag='[계약]' if guard.kind(cat.key,item['title'])=='contract' else '[개발]'
    value=_RENDER(replace(cat,tag=tag),item,rate)
    return '\n'.join(x for x in value.splitlines() if '제목·공개요약에서 핵심 수치 미추출' not in x)

def main():
    import os
    import json
    if os.getenv('SPACE_LAUNCH_GUARD_SELF_TEST')=='1':
        guard.self_test()
        guard.correction_self_test()
        return 0
