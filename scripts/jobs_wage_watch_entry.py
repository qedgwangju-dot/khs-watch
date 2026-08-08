from __future__ import annotations

# Import the production runner first so the BLS fallback and per-run parser
# cache are installed without executing watch.main().
import jobs_wage_watch_runner  # noqa: F401
import jobs_wage_watch as watch
import jobs_wage_watch_full_report_v5 as full_report

# v5 keeps the v4 full report but bounds ancillary FRED latency and preserves
# fail-honest partial status if those rate comparisons are temporarily missing.
watch.build_report = full_report.build_report

if __name__ == "__main__":
    raise SystemExit(watch.main())
