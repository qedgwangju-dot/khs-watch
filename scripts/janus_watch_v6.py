#!/usr/bin/env python3
from pathlib import Path
import sys

import janus_watch_v2 as j2
import janus_watch_v5 as j5

# Westinghouse 지분 알림만 별도 파일로 분리한다.
# 일반 Janus·원전 정책 알림은 기존 @hs... 경로를 유지하고,
# Westinghouse 지분·원전동맹 알림은 전용 @khs887900_bot 경로로 보낸다.
WEC_ALERT_PATH = Path(__file__).resolve().parents[1] / "out" / "westinghouse_alert.html"


def _render_split(events, fact_changes):
    wec_events = [e for e in events if e.get("kind") == "westinghouse_stake"]
    other_events = [e for e in events if e.get("kind") != "westinghouse_stake"]

    try:
        WEC_ALERT_PATH.unlink()
    except FileNotFoundError:
        pass

    if wec_events:
        wec_text = j5._render_wec_cluster(wec_events)
        if wec_text:
            WEC_ALERT_PATH.parent.mkdir(parents=True, exist_ok=True)
            WEC_ALERT_PATH.write_text(wec_text, encoding="utf-8")

    # Westinghouse 이슈는 여기서 제외해 기존 Janus 봇으로 중복 전송되지 않게 한다.
    if other_events or fact_changes:
        return j5._ORIGINAL_RENDER(other_events, fact_changes)
    return ""


j2.base.render_alert = _render_split

if __name__ == "__main__":
    sys.exit(j2.base.main())
