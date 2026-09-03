#!/usr/bin/env python3
"""JGB regime/flow watcher entrypoint using the official current weekly PDF."""
from __future__ import annotations

import global_rates_regime_flow_core as core
from global_rates_regime_flow_core import *  # re-export classifier helpers for tests
from global_rates_weekly_flow_pdf import fetch_weekly_outward_flows as _fetch_pdf_flows


def fetch_weekly_outward_flows():
    return _fetch_pdf_flows(core.get_bytes)


def main() -> int:
    core.fetch_weekly_outward_flows = fetch_weekly_outward_flows
    return core.main()


if __name__ == "__main__":
    raise SystemExit(main())
