"""Authenticated quote reachability only; never sends an alert or writes state."""
import datetime as dt
import json
from pathlib import Path

import market_namuh_flow as nh


def main():
    result = {"provider": "Namuh", "actual_checkout_sha": nh.code_sha(),
              "started_at": dt.datetime.now(dt.timezone.utc).isoformat(), "sources": [],
              "telegram_sent": False, "production_state_written": False, "coverage_complete": False,
              "unit_verification": "PENDING_SEPARATE_MARKET_SOURCE_COMPARISON"}
    for market in ("KOSPI", "KOSDAQ"):
        for kind, path, inputs in (
            ("cash", nh.INVESTORS, nh.investor_request(market)),
            ("futures_quantity", nh.INVESTORS, nh.investor_request(market, futures=True, quantity=True)),
            ("program", nh.PROGRAM, nh.program_request(market))):
            item = {"market": market, "kind": kind, "request": inputs, "status": "held"}
            try:
                entry = nh.request(path, inputs)
                body = nh.checked(entry)
                item.update({"status": "received", "row_count": len(body["Output_0"]),
                             "first_row": body["Output_0"][0], "raw_sha256": entry["raw_sha256"],
                             "evidence": entry["retained_evidence"], "response_headers": entry["response_headers"],
                             "rsp_cd": body.get("rsp_cd"), "rsp_msg": body.get("rsp_msg")})
            except Exception as exc:
                item.update({"error_type": type(exc).__name__, "reason": nh._redact(str(exc))})
            result["sources"].append(item)
            print(json.dumps(item, ensure_ascii=False), flush=True)
    received = sum(item["status"] == "received" for item in result["sources"])
    result.update({"received": received, "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                   "source_reachability": "PASS" if received == 6 else "HELD"})
    out = Path("out/market_namuh_source_probe.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"source_reachability": result["source_reachability"], "received": received,
                      "coverage_complete": False, "telegram_sent": False, "production_state_written": False}))
    return 0 if received == 6 else 1


if __name__ == "__main__":
    raise SystemExit(main())
