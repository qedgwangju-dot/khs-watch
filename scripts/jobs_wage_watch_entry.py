from __future__ import annotations

# Import the production runner first so the BLS fallback and per-run parser
# cache are installed without executing watch.main().
import jobs_wage_watch_runner  # noqa: F401
import jobs_wage_watch as watch
import jobs_wage_watch_full_report_v8 as full_report

# v8 preserves the readable v7 Telegram layout and full v6 analysis, while
# strengthening the Fed reaction-function section with live official FOMC
# statement context and a separate labor-axis vs final-policy judgment.
watch.build_report = full_report.build_report

if __name__ == "__main__":
    raise SystemExit(watch.main())
