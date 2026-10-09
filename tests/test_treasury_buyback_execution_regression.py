import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import treasury_buyback_execution_watch as t

def test_nominal_filter():
    row = {"securityType": "Bond", "securityTerm": "30-Year"}
    assert t._is_30y_bond(row)
    assert not t._is_30y_bond({**row, "Tips": "Yes"})
    assert not t._is_30y_bond({**row, "securityType": "TIPS"})
    assert not t._is_30y_bond({**row, "securityTerm": "20-Year"})

def test_flat_is_not_mixed():
    r = {"target":{"2y":4.75,"10y":5.22,"20y":5.64,"30y":5.60},
         "target_date":"2026-10-08",
         "since_operation_bp":{"2y":-3,"10y":-2,"20y":0,"30y":-1},
         "since_pre_operation_bp":{"2y":-13,"10y":-7,"20y":-4,"30y":-4}}
    _, message, _ = t.build_persistence_followup("2026-10-01", 5, r)
    assert "하락·보합" in message

def test_state_race_merge():
    from treasury_buyback_state_commit import combine
    old = {"seen":["old"],"latest_long_end_operation_date":"2026-10-08",
           "latest_long_end_fingerprint":"latest",
           "yield_persistence_watches":[{"operation_date":"2026-10-08",
               "fingerprint":"a","completed_offsets":[1]}]}
    stale = {"seen":["new"],"latest_long_end_operation_date":"2026-10-01",
             "latest_long_end_fingerprint":"stale",
             "yield_persistence_watches":[{"operation_date":"2026-10-08",
                 "fingerprint":"a","completed_offsets":[3]}]}
    merged = combine(old, stale)
    assert set(merged["seen"]) == {"old","new"}
    assert merged["latest_long_end_fingerprint"] == "latest"
    assert merged["yield_persistence_watches"][0]["completed_offsets"] == [1,3]

def test_nominal_auction_average():
    import json
    from unittest.mock import patch
    days = ["2026-09-10","2026-08-13","2026-07-09",
            "2026-06-11","2026-05-13","2026-04-09"]
    ratios = [2.61,2.39,2.44,2.33,2.30,2.39]
    def row(day, btc, tips=False):
        return {"securityType":"Bond","securityTerm":"30-Year",
                "auctionDate":day,"inflationIndexSecurity":"Yes" if tips else "No",
                "bidToCoverRatio":btc,"competitiveAccepted":22000000000,
                "highYield":5.618,"indirectBidderAccepted":16000000000,
                "directBidderAccepted":4500000000,"primaryDealerAccepted":1500000000}
    entries = [row("2026-10-08",2.54)] + [row(d,v) for d,v in zip(days,ratios)]
    entries.append(row("2026-09-12",9.99,True))
    with patch.object(t, "fetch_text", return_value=json.dumps(entries)):
        result = t.latest_30y_auction_context("2026-10-08")
    assert result["sample_n"] == 6
    assert abs(result["avg_btc_6"] - 2.41) < 0.000001

if __name__ == '__main__':
    test_nominal_filter()
    test_flat_is_not_mixed()
    test_state_race_merge()
    test_nominal_auction_average()
    print('buyback nominal filter test passed')
