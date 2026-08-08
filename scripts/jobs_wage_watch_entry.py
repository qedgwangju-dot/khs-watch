from __future__ import annotations

# Import the production runner first so the BLS fallback and per-run parser
# cache are installed without executing watch.main().
import jobs_wage_watch_runner  # noqa: F401
import jobs_wage_watch as watch
import jobs_wage_watch_full_report_v6 as full_report

# v6 preserves the full v4/v5 report, fetches FRED official rates first, then
# checks market 5-minute reactions, and stays fail-honest if ancillary data fail.
watch.build_report = full_report.build_report

if __name__ == "__main__":
    raise SystemExit(watch.main())
