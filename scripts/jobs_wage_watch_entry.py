from __future__ import annotations

# Import the production runner first so the BLS fallback and per-run parser
# cache are installed without executing watch.main().
import jobs_wage_watch_runner  # noqa: F401
import jobs_wage_watch as watch
import jobs_wage_watch_full_report_v7 as full_report

# v7 preserves the full v6 analysis and trigger/dedupe behavior, but reformats
# the Telegram body for scanability: a verified 5~8-line overview, plain-text
# section dividers, grouped market data, and no visible Markdown #/** markers.
watch.build_report = full_report.build_report

if __name__ == "__main__":
    raise SystemExit(watch.main())
