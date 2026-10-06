#!/usr/bin/env python3
"""Audit two saved live deliveries before registering cross-publisher aliases."""

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamejoa_market_materiality as materiality
import gamejoa_preopen_news_radar_full_compact_runner as radar


ROOT = Path(__file__).resolve().parent.parent
ALIAS_PATH = ROOT / "data/gamejoa_verified_event_aliases.json"
RECEIPTS = (
    (37472158800, 2339, (
        "https://www.newsis.com/view/NISX20261006_0003814993",
        "https://www.hankyung.com/article/202610065899i",
    )),
    (37480540629, 2343, (
        "https://www.etoday.co.kr/news/view/2632636",
        "https://www.etoday.co.kr/news/view/2632544",
    )),
)


def read_delivery(directory: Path, run_id: int, message_id: int) -> dict:
    report = json.loads((directory / "gamejoa_preopen_news_radar.json").read_text(encoding="utf-8"))
    delivery = json.loads((directory / "gamejoa_preopen_news_radar_delivery.json").read_text(encoding="utf-8"))
    markdown = (directory / "gamejoa_preopen_news_radar.md").read_bytes()
    assert delivery["status"] == "sent" and delivery["message_id"] == message_id
    assert hashlib.sha256(markdown).hexdigest() == delivery["report_sha256"]
    assert len(report["alerts"]) == 7
    assert all(alert.get("body_verified") and alert.get("source_body") for alert in report["alerts"])
    for alert in report["alerts"]:
        assert alert["link"] in markdown.decode("utf-8"), alert["link"]
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v98-artifact", type=Path, required=True)
    parser.add_argument("--v99-artifact", type=Path, required=True)
    parser.add_argument("--seen-state", type=Path)
    parser.add_argument("--write-aliases", action="store_true")
    args = parser.parse_args()
    reports = (
        read_delivery(args.v98_artifact, RECEIPTS[0][0], RECEIPTS[0][1]),
        read_delivery(args.v99_artifact, RECEIPTS[1][0], RECEIPTS[1][1]),
    )
    identities = []
    proofs = []
    for report, (run_id, message_id, urls) in zip(reports, RECEIPTS):
        for url in urls:
            alert = next(item for item in report["alerts"] if item["link"] == url)
            identity = materiality.source_event_identity(alert)
            assert identity.startswith("source_event:"), (url, identity)
            identities.append(identity)
            proofs.append({
                "source_title": alert["source_title"],
                "link": url,
                "source_published_kst": alert["published"],
                "source_body_sha256": hashlib.sha256(alert["source_body"].encode("utf-8")).hexdigest(),
                "source_event_identity": identity,
                "run_id": run_id,
                "message_id": message_id,
            })
    assert identities[0] == identities[2], "Research awards still have different event identities"
    assert identities[1] == identities[3], "Same-session Nasdaq closes still have different event identities"
    assert identities[0] != identities[1]
    latest = reports[1]["alerts"]
    german = next(item for item in latest if "독일 산업생산" in item["source_title"])
    roundup = next(item for item in latest if "뉴스프레소" in item["source_title"])
    intraday = next(item for item in latest if "유가·美 국채" in item["source_title"])
    assert materiality.assess(german["source_title"], german["source_body"])["reason"] == "source_primary_metric_conflict_production_vs_orders"
    assert materiality.assess(roundup["source_title"], roundup["source_body"])["reason"] == "us_equity_close_session_unverified"
    assert materiality.assess(intraday["source_title"], intraday["source_body"])["disposition"] == "keep"
    assert not materiality.us_equity_close_identity(intraday)
    ukraine = next(item for item in latest if "한국의 러 석유공급" in item["source_title"])
    ukraine_core = radar.verified_alert_core(ukraine, ukraine["source_title"])
    assert "17만6천t" in ukraine_core and "가디언" in ukraine_core and "포로" not in ukraine_core
    assert not radar.source_core_fact_errors({**ukraine, "telegram_core_fact": ukraine_core})
    nasdaq = next(item for item in latest if item["link"] == RECEIPTS[1][2][1])
    nasdaq_core = radar.verified_alert_core(nasdaq, nasdaq["source_title"])
    assert "2만7477.31" in nasdaq_core and "1.05%" in nasdaq_core
    assert not radar.source_core_fact_errors({**nasdaq, "telegram_core_fact": nasdaq_core})
    if args.seen_state:
        state = json.loads(args.seen_state.read_text(encoding="utf-8"))
        radar.telegram.migrate_seen_verified_event_aliases(state)
        for identity in (identities[0], identities[1]):
            key = "event:" + radar.telegram.digest_seen(identity)
            assert key in state["seen"], identity
        now = dt.datetime.fromisoformat(reports[1]["query_time_kst"])
        with patch.object(radar.telegram, "SEEN_PATH", args.seen_state), patch.object(radar.base, "kst_now", return_value=now):
            fresh, skipped = radar.telegram.filter_previously_seen_alerts(latest, now, "live")
            selected = radar.quality_display_alerts(fresh, 20)
        assert {item["link"] for item in skipped} == {proofs[0]["link"], proofs[1]["link"],
                                                       proofs[2]["link"], proofs[3]["link"]} & {item["link"] for item in latest}
        assert {item["link"] for item in selected} == {ukraine["link"], intraday["link"]}
    if args.write_aliases:
        payload = json.loads(ALIAS_PATH.read_text(encoding="utf-8"))
        existing = {(entry.get("run_id"), entry.get("link")): entry for entry in payload["entries"]}
        for proof in proofs:
            key = (proof["run_id"], proof["link"])
            if key in existing:
                assert existing[key] == proof, key
            else:
                payload["entries"].append(proof)
        ALIAS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "verified_full_bodies": sum(len(report["alerts"]) for report in reports),
        "research_event": identities[0],
        "nasdaq_close_event": identities[1],
        "review_reasons": [materiality.assess(item["source_title"], item["source_body"])["reason"] for item in (german, roundup)],
        "intraday_kept": True,
        "source_bound_cores": 2,
        "historical_seen_migrated": bool(args.seen_state),
        "replayed_unique_selected": 2 if args.seen_state else None,
        "alias_entries": len(proofs),
        "aliases_written": args.write_aliases,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
