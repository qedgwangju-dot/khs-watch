"""Read-only source audit: no events, Telegram imports, delivery or market state."""
from __future__ import annotations
import datetime as dt
import json
import os
from pathlib import Path
import sys
import time

import market_kiwoom_flow as flow


def main() -> int:
    started = time.time()
    report = dict(started_at_kst=dt.datetime.now(flow.KST).isoformat(),
                  code_sha=flow.code_sha(), header_sha=os.getenv("GITHUB_SHA"), run_id=os.getenv("GITHUB_RUN_ID"),
                  credentials_configured=flow.configured(), telegram_sent=False, production_state_changed=False,
                  observations={}, limits=["ka10051 returns no source date/time echo; cumulative supplement only.",
                  "No Kiwoom index-futures investor or program-by-investor coverage is claimed.",
                  "Program values require independent same-day/same-clock KRX+NXT KRW rows; stale values are held."])
    valid_cash = 0
    for market in flow.CODES:
        report["observations"][market] = {}
        for kind, collect in (("cash", flow.cash_current), ("program", flow.program_current)):
            try:
                result = collect(market)
                if kind == "cash":
                    valid_cash += 1
                    result["rendered_cumulative_supplement"] = flow.cash_lines(result, market)
                else:
                    age = time.time() - result["sample_ts"]
                    result.update(source_age_seconds=age, eligible_for_intraday=-5 <= age <= 90)
                report["observations"][market][kind] = dict(status="verified", result=result)
            except Exception as exc:
                reason = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
                report["observations"][market][kind] = dict(status="held", reason=reason)
    report.update(finished_at_kst=dt.datetime.now(flow.KST).isoformat(), elapsed_seconds=time.time()-started,
                  verified_cash_markets=valid_cash, interval_cash_coverage=False, coverage="PARTIAL",
                  full_market_flow_coverage_verified=False)
    directory = Path(os.getenv("MARKET_SOURCE_EVIDENCE_DIR", "out/market_source_evidence"))
    directory.mkdir(parents=True, exist_ok=True)
    output = directory.parent / "market_kiwoom_source_probe.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(dict(code_sha=report["code_sha"], verified_cash_markets=valid_cash, coverage=report["coverage"],
                         observations={m: {k: v["status"] for k,v in values.items()} for m,values in report["observations"].items()},
                         telegram_sent=False, production_state_changed=False), ensure_ascii=False))
    return 0 if valid_cash == 2 else 2


if __name__ == "__main__":
    sys.exit(main())
