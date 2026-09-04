from __future__ import annotations

# Import the production runner first so the BLS fallback and per-run parser
# cache are installed without executing watch.main().
import jobs_wage_watch_runner  # noqa: F401
import jobs_wage_watch as watch
import jobs_wage_watch_full_report_v9 as full_report

# v9 preserves the readable Telegram layout and full analysis, while forcing
# an explicit first-line rate direction such as '인하 쪽' / '동결·인상 쪽'
# before the final Fed policy judgment. Labor-axis direction and final Fed
# decision are intentionally separated.
watch.build_report = full_report.build_report

if __name__ == "__main__":
    raise SystemExit(watch.main())
