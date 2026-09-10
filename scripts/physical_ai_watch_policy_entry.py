#!/usr/bin/env python3
"""Final physical-AI watcher entrypoint with Korean rendering and policy lane."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Import display first so its rendering-only Korean hook stays active.
import physical_ai_watch_korean_display as display
import physical_ai_watch_humanoid_component_policy as policy

base = policy.base

if __name__ == '__main__':
    base.main()
    if base.ALERT_PATH.exists():
        rendered = base.ALERT_PATH.read_text(encoding='utf-8')
        base.ALERT_PATH.write_text(display._inline_original_link(rendered), encoding='utf-8')
