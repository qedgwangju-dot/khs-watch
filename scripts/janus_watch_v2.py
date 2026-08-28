#!/usr/bin/env python3
from pathlib import Path
import sys

import janus_watch as base

ROOT = Path(__file__).resolve().parents[1]

# war.gov is protected against GitHub-hosted runners (HTTP 403). Replace it with
# DOE's official Reactor Pilot Program page, which tracks Antares/Radiant and
# related reactor criticality/deployment milestones that can affect Janus supply.
base.SOURCES = [
    source for source in base.SOURCES
    if source.get("name") != "미 전쟁부 Janus 발표"
]
base.SOURCES.insert(
    2,
    {
        "name": "미 에너지부 원자로 실증 프로그램",
        "url": "https://www.energy.gov/ne/us-department-energy-reactor-pilot-program",
        "kind": "official",
    },
)

# Keep v2 state/output isolated so the first successful run establishes a clean
# baseline and does not replay old Janus headlines as new alerts.
base.STATE_PATH = ROOT / "data" / "janus_watch_v2_state.json"
base.PENDING_STATE_PATH = ROOT / "out" / "janus_watch_v2_state_pending.json"
base.ALERT_PATH = ROOT / "out" / "janus_alert_v2.html"
base.STATUS_PATH = ROOT / "out" / "janus_status_v2.md"
base.ERROR_PATH = ROOT / "out" / "janus_errors_v2.log"
base.CONNECTION_TEST_PATH = ROOT / "out" / "janus_connection_test_v2.html"

if __name__ == "__main__":
    sys.exit(base.main())
