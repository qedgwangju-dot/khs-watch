"""Read-only LS source audit for both markets' spot industry context.

Retains actual public market-data HTTP bytes. It cannot create an event, send a
message, or write production state. Retained historical windows are explicitly
separate from the HTTP input and receipt of any earlier production alert.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import time
from pathlib import Path

from kosdaq_surge_industries import KST, _industry, industry_buy_context
from kospi_shock_enrichment import _display_name
from kospi_shock_episode_watch import (
    get_token, ls_post, market_clock_epoch, _flow_surge_channel_pair, fnum,
)
from krx_session_calendar import session_state


def main(out: Path) -> None:
    now = dt.datetime.now(KST)
    session = session_state(now)
    result = {"mode": "read_only_dated_source_audit", "code_sha": os.getenv("GITHUB_SHA"),
              "run_id": os.getenv("GITHUB_RUN_ID"), "queried_at": now.isoformat(),
              "telegram_sent": False, "production_state_changed": False,
              "prior_operating_http_preserved": False, "masters": [], "markets": {}}
    out.parent.mkdir(parents=True, exist_ok=True)
    if not session["is_session"] or not (session["open"] <= now < session["continuous_end"]):
        result["status"] = "outside_continuous_session"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return
    token = get_token()
    master = {}
    for group in ("1", "2", "0"):
        capture = {}
        try:
            body = ls_post(token, "/indtp/market-data", "t8424",
                           {"t8424InBlock": {"gubun1": group}},
                           max_attempts=1, request_timeout=12, capture=capture)
            capture["response_json"] = body
            rows = body.get("t8424OutBlock") or []
            for row in [rows] if isinstance(rows, dict) else rows:
                code, name = str(row.get("upcode") or ""), _display_name(row.get("hname"))
                for market in ("KOSPI", "KOSDAQ"):
                    if _industry(code, name, market):
                        master[(market, code)] = {"code": code, "name": name, "market": market}
        except Exception as exc:
            capture["error_type"] = type(exc).__name__
        result["masters"].append(capture)
        time.sleep(1.1)
    journal = out.with_suffix(".jsonl")
    all_records = []
    for market in ("KOSPI", "KOSDAQ"):
        sectors = [x for (m, _), x in master.items() if m == market]
        all_records.append({"record_type": "subscription_coverage", "market": market,
                            "source_tr": "UBM", "ts": time.time(), "expected": sectors})
    # The same documented t1621 endpoint and one shared rate limit as production.
    for (market, code), item in master.items():
        started = time.monotonic()
        request = {"t1621InBlock": {"upcode": code, "cnt": 500,
                                    "bgubun": "0", "exchgubun": "U"}}
        record = {"record_type": "industry_history_snapshot", "source_tr": "t1621",
                  "market": market, "upcode": code, "industry": item["name"],
                  "source_unit": "UNVERIFIED", "request": request, "http_capture": {}}
        try:
            record["response"] = ls_post(token, "/stock/investor", "t1621", request,
                                          max_attempts=1, request_timeout=8,
                                          capture=record["http_capture"])
            record["status"] = "success"
        except Exception as exc:
            record.update(status="request_failed", error_type=type(exc).__name__)
        record["received_ts"] = time.time()
        all_records.append(record)
        time.sleep(max(0, 1.1 - (time.monotonic() - started)))
    journal.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in all_records), encoding="utf-8")
    # Choose an explicitly historical, common window preceding collection.
    cutoff = now.replace(second=0, microsecond=0).timestamp() - 60
    for market, selector, upcode in (("KOSPI", "1", "001"), ("KOSDAQ", "3", "301")):
        capture = {}
        market_result = {"spot_http": capture, "contexts": [], "status": "pending"}
        result["markets"][market] = market_result
        query = {"t1602InBlock": {"market": selector, "upcode": upcode,
                                 "gubun1": "2", "gubun2": "0", "cts_time": "", "cts_idx": 0,
                                 "cnt": 500, "gubun3": "", "exchgubun": "U"}}
        try:
            body = ls_post(token, "/stock/investor", "t1602", query,
                           max_attempts=1, request_timeout=12, capture=capture)
            capture["response_json"] = body
            rows = body.get("t1602OutBlock1") or []
            if isinstance(rows, dict):
                rows = [rows]
            snapshots = []
            for row in rows:
                ts = market_clock_epoch(row.get("time"), capture["received_ts"])
                values = {a: fnum(row.get(f)) for a, f in
                          (("개인", "sv_08"), ("외국인", "sv_17"), ("기관", "sv_18"))}
                if ts is not None and ts <= cutoff and all(x is not None for x in values.values()):
                    snapshots.append({"ts": capture["received_ts"], "현물": {"sample_ts": ts, **values}})
            pair = _flow_surge_channel_pair(snapshots, "현물", cutoff + 5, session["open"].timestamp())
            if pair:
                for actor in ("개인", "외국인", "기관"):
                    context = industry_buy_context(pair["start_ts"], pair["end_ts"], actor,
                                                   market=market, path=journal,
                                                   session_open_ts=session["open"].timestamp())
                    market_result["contexts"].append({"spot_delta_eok": pair["deltas"][actor],
                                                       "industry_context": context})
                market_result["status"] = "retained_window_checked"
            else:
                market_result["status"] = "retained_spot_window_unavailable"
        except Exception as exc:
            market_result.update(status="request_failed", error_type=type(exc).__name__)
    result["status"] = "source_audit_finished"
    result["journal"] = journal.name
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("market_industry_source_audit=true telegram_sent=false production_state_changed=false",
          {m: r["status"] for m, r in result["markets"].items()}, flush=True)
    assert all(result["markets"][m]["status"] == "retained_window_checked"
               and any(c["industry_context"]["rows"] for c in result["markets"][m]["contexts"])
               for m in ("KOSPI", "KOSDAQ")), "Source audit held; inspect retained bytes and identities"


if __name__ == "__main__":
    main(Path("out/market_surge_industry_source.json"))
