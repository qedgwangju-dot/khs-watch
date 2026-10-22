#!/usr/bin/env python3
"""Synthetic regression tests for ARK's daily trade table and duplicate guard."""
import ark_daily_trade_watch as w

def main():
    payload=(
      "date,fund,direction,ticker,cusip,name,shares,% of etf\n"
      "10/20/2026,ARKK,Buy,XE,000000,EX ENERGY,292022,0.0504\n"
      "10/20/2026,ARKQ,Buy,XE,000000,EX ENERGY,126437,0.0755\n"
      "10/20/2026,ARKX,Buy,XE,000000,EX ENERGY,66436,0.1004\n"
      "10/20/2026,ARKQ,Buy,OKLO,000000,OKLO,150998,0.234\n"
      "10/20/2026,ARKK,Sell,PLTR,000000,PALANTIR,27790,0.0875\n"
      "10/20/2026,ARKK,Sell,PLTR,000000,PALANTIR,27790,0.0875\n"
    ).encode()
    rows=w.parse(payload)
    assert len(rows)==5,rows
    assert sum(x["shares"] for x in rows if x["ticker"]=="XE")==484895
    assert sum(x["shares"] for x in rows if x["ticker"]=="OKLO")==150998
    digest=w._fingerprint(rows)
    assert w._fingerprint(rows)==digest
    msg=w.build(rows,"2026-10-20")
    assert "484,895주" in msg
    assert "27,790주" in msg
    assert "잠정 자료" in msg
    assert "실제 체결단가" in msg
    assert "공식 당일 매매 파일" in msg
    print("ARK daily trade parser regression tests passed.")

if __name__=="__main__":
    main()
