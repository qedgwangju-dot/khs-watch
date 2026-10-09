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

if __name__ == '__main__':
    test_nominal_filter()
    print('buyback nominal filter test passed')
