"""Read-only CI audit of real LS history and the collected UBM journal.

This probe never creates a market event, advances production state, or sends a
message. A held industry result remains held; a passing collection is not proof
of a qualifying surge or Telegram delivery.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
import os
import time
from pathlib import Path

from kosdaq_surge_industries import KST, industry_buy_context, industry_context_lines
from kospi_shock_episode_watch import get_token, ls_post, market_clock_epoch, _flow_surge_channel_pair
from krx_session_calendar import session_state


def run_probe(journal: Path) -> dict:
    now = dt.datetime.now(KST)
    sess = session_state(now)
    evidence = {"mode": "read_only_retained_source_windows", "telegram_sent": False,
                "production_state_changed": False, "queried_at_kst": now.isoformat(),
                "code_sha": os.getenv("GITHUB_SHA"), "run_id": os.getenv("GITHUB_RUN_ID"),
                "status": "outside_continuous_market", "contexts": []}
    if not (sess["is_session"] and sess.get("open") and sess.get("continuous_end")
            and sess["open"] <= now < sess["continuous_end"]):
        return evidence
    query = {"t1602InBlock": {"market": "2", "upcode": "301", "gubun1": "2",
                             "gubun2": "0", "cts_time": "", "cts_idx": 0,
                             "cnt": 100, "gubun3": "", "exchgubun": "U"}}
    body = ls_post(get_token(), "/stock/investor", "t1602", query,
                   max_attempts=2, request_timeout=8.0)
    retrieved = time.time()
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True).encode()
    evidence.update({"query": query, "response_json": body,
                     "decoded_response_json_sha256": hashlib.sha256(encoded).hexdigest(),
                     "response_received_at_kst": dt.datetime.fromtimestamp(retrieved, KST).isoformat()})
    raw = body.get("t1602OutBlock1") or []
    if isinstance(raw, dict):
        raw = [raw]
    snapshots = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        ts = market_clock_epoch(row.get("time"), retrieved)
        values = {}
        for actor, field in (("개인", "sv_08"), ("외국인", "sv_17"), ("기관", "sv_18")):
            try:
                value = float(row[field])
                if math.isfinite(value):
                    values[actor] = value
            except (KeyError, TypeError, ValueError, OverflowError):
                pass
        if ts is not None and len(values) == 3:
            snapshots.append({"ts": retrieved, "현물": {"sample_ts": ts, **values}})
    endpoints = sorted({x["현물"]["sample_ts"] for x in snapshots
                        if 0 <= retrieved - x["현물"]["sample_ts"] <= 45}, reverse=True)
    for endpoint in endpoints:
        retained = [x for x in snapshots if x["현물"]["sample_ts"] <= endpoint]
        pair = _flow_surge_channel_pair(retained, "현물", retrieved, sess["open"].timestamp())
        if pair is None:
            continue
        for actor in ("개인", "외국인", "기관"):
            block = industry_buy_context(pair["start_ts"], pair["end_ts"], actor,
                                         path=journal, session_open_ts=sess["open"].timestamp())
            assert block["market"] == "KOSDAQ" and block["investor"] == actor
            assert not block["unit_verified"] and block["display_unit"] is None
            for item in block["rows"]:
                assert item["code"].startswith("3")
                assert item["delta_raw"] == item["end_value_raw"] - item["start_value_raw"]
                for point in ("start", "end"):
                    assert item[point]["received_ts"] <= pair[point + "_ts"]
                    assert 0 <= item[point + "_gap_sec"] <= 30
            text = industry_context_lines(block, actor, pair["start_ts"], pair["end_ts"])
            evidence["contexts"].append({"market_window": [pair["start_ts"], pair["end_ts"]],
                                         "market_delta_eok": pair["deltas"][actor],
                                         "industry_context": block, "rendered_industry_lines": text})
    evidence["status"] = "industry_context_checked" if evidence["contexts"] else "market_window_unavailable"
    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("out/kosdaq_surge_industry_probe.json"))
    args = parser.parse_args()
    result = run_probe(args.journal)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("kosdaq_surge_industry_read_only_probe=" + result["status"],
          "contexts=" + str(len(result["contexts"])),
          "available=" + str(sum(bool(x["industry_context"]["available"]) for x in result["contexts"])),
          "telegram_sent=false unit_verified=false", flush=True)
