#!/usr/bin/env python3
"""Run the regime/flow upgrade with the official MOF weekly-PDF parser."""
from __future__ import annotations

import global_rates_regime_flow_upgrade as core
from global_rates_weekly_flow_pdf import fetch_weekly_outward_flows as fetch_pdf_flows


def official_weekly_flows():
    return fetch_pdf_flows(core.get_bytes)


def main() -> int:
    # The fixed official PDF is the authoritative current release. It avoids the
    # historical CSV layout mismatch while preserving the same normalized output.
    core.fetch_weekly_outward_flows = official_weekly_flows
    return core.main()


if __name__ == "__main__":
    raise SystemExit(main())
