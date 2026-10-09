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

if __name__ == '__main__':
    test_nominal_filter()
    test_flat_is_not_mixed()
    print('buyback nominal filter test passed')
