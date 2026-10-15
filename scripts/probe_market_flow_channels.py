"""Read current LS channels without creating events, messages or live state."""
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

import kospi_shock_episode_watch as watch
from market_flow_channels import MARKET_SPECS, KST, decoded_hash


def main(path: Path) -> int:
    evidence = {"code_sha": os.getenv("GITHUB_SHA"), "run_id": os.getenv("GITHUB_RUN_ID"),
                "queried_at_kst": dt.datetime.now(KST).isoformat(),
                "telegram_sent": False, "production_state_changed": False,
                "requests": [], "markets": {}, "status": "pending"}
    original = watch.ls_post

    def retained_post(token, api_path, tr, body, **kwargs):
        record = {"tr": tr, "api_path": api_path, "request": body, "started_ts": time.time()}
        evidence["requests"].append(record)
        try:
            response = original(token, api_path, tr, body, **kwargs)
            record.update(response_json=response, decoded_response_json_sha256=decoded_hash(response),
                          received_ts=time.time(), status="success")
            return response
        except Exception as exc:
            record.update(status="request_failed", error_type=type(exc).__name__, received_ts=time.time())
            raise

    failed = []
    try:
        token = watch.get_token()
        watch.ls_post = retained_post
        for market in MARKET_SPECS:
            snapshot = watch.fetch_flow_snapshot(token, market)
            spec = MARKET_SPECS[market]
            checks = {
                "spot_selector": (snapshot.get("현물") or {}).get("request_market") == spec["spot_market"],
                "spot_code": (snapshot.get("현물") or {}).get("upcode") == spec["upcode"],
                "spot_actors": all(watch.fnum((snapshot.get("현물") or {}).get(a)) is not None
                                   for a in ("외국인", "기관", "개인")),
                "futures_product": (snapshot.get("지수선물") or {}).get("asset") == spec["asset"],
                "futures_scope": (snapshot.get("지수선물") or {}).get("source_scope_verified") is True,
                "futures_dated_clock": (snapshot.get("지수선물") or {}).get("timestamp_basis") == "provider_date_time",
                "futures_raw_unit": (snapshot.get("지수선물") or {}).get("unit_verified") is False,
                "program_market": (snapshot.get("프로그램") or {}).get("market") == market,
                "program_components": all(watch.fnum((snapshot.get("프로그램") or {}).get(k)) is not None
                                          for k in ("전체", "차익", "비차익")),
                "program_query_clock": (snapshot.get("프로그램") or {}).get("source_time_verified") is False,
            }
            issues = [key for key, ok in checks.items() if not ok]
            failed.extend(market + ":" + key for key in issues)
            evidence["markets"][market] = {"snapshot": snapshot, "checks": checks,
                                            "health": watch.flow_snapshot_health(snapshot)}
        # A bounded readback exposes earlier dated rows for incident audits.
        # These later reads are not the HTTP responses used for a live message.
        try:
            query = {"t8463InBlock": {"tm_rng": "D", "fot_clsf_cd": "F",
                     "bsc_asts_id": "KQI", "cnt": 300, "bgubun": "0"}}
            history = retained_post(token, "/futureoption/investor", "t8463", query,
                                    max_attempts=1, request_timeout=45.0)
            evidence["kosdaq_futures_history_readback"] = {
                "status": "received", "request": query, "response": history,
                "original_operating_response": False,
            }
        except Exception as exc:
            evidence["kosdaq_futures_history_readback"] = {
                "status": "request_failed", "error_type": type(exc).__name__,
                "original_operating_response": False,
            }
        if failed:
            # Source diagnosis only. U includes another session; its amounts
            # cannot substitute for the event's D request in either monitor.
            evidence["diagnostics"] = {}
            for market in MARKET_SPECS:
                asset = MARKET_SPECS[market]["asset"]
                try:
                    result = retained_post(token, "/futureoption/investor", "t8463",
                        {"t8463InBlock": {"tm_rng": "U", "fot_clsf_cd": "F",
                         "bsc_asts_id": asset, "cnt": 10, "bgubun": "0"}},
                        max_attempts=1, request_timeout=25.0)
                    evidence["diagnostics"][market + "_combined_session"] = result
                except Exception as exc:
                    evidence["diagnostics"][market + "_combined_session"] = {"error_type": type(exc).__name__}
            for tr, api_path, query in (
                ("t8424", "/indtp/market-data", {"t8424InBlock": {"gubun1": ""}}),
                ("t1615", "/stock/investor", {"t1615InBlock": {"gubun1": "2", "gubun2": "2", "exchgubun": "U"}}),
            ):
                try:
                    evidence["diagnostics"][tr] = retained_post(token, api_path, tr, query,
                                                                max_attempts=1, request_timeout=15.0)
                except Exception as exc:
                    evidence["diagnostics"][tr] = {"error_type": type(exc).__name__}
        evidence.update(status="contract_checked" if not failed else "source_contract_held", failed_checks=failed)
    except Exception as exc:
        # Token transport exceptions can contain URLs with query credentials.
        evidence.update(status="collection_failed", error_type=type(exc).__name__)
        failed.append("collection_failed")
    finally:
        watch.ls_post = original
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("market_flow_source_audit=" + evidence["status"], "telegram_sent=false production_state_changed=false")
    if failed:
        print("held_checks=" + ",".join(failed))
    return int(bool(failed))


if __name__ == "__main__":
    sys.exit(main(Path("out/market_flow_channel_probe.json")))
