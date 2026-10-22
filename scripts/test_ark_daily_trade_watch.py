#!/usr/bin/env python3
"""Synthetic regression tests for ARK's daily trade table and duplicate guard."""
import ark_daily_trade_watch as w
import ark_notional_enrichment as n


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
    close_price={"XE":{"close":10.74,"source":"Stooq"},
                 "OKLO":{"close":27.24,"source":"Yahoo Finance"},
                 "PLTR":{"close":100.00,"source":"Yahoo Finance"}}
    filled=w.build(rows,"2026-10-20",rate=1350.0,basis="2026-10-22",
                   prices=close_price,enrichment=True)
    assert "금액 보강본" in filled
    assert "484,895주" in filled
    assert "당일 종가 기준 추정" in filled
    assert "달러(약 " in filled
    assert "실제 체결대금 아님" in filled
    assert "거래대금: 체결단가 미공개·종가 추정 불가" not in n.estimated_amount("XE",100,close_price,1350.0)
    assert "거래대금: 체결단가 미공개·종가 추정 불가" in n.estimated_amount("HO",100,close_price,1350.0)
    assert abs(484895 * 10.74 * 1350.0 - 7030492605.0) < 1.0
    print("ARK daily trade parser regression tests passed.")

if __name__=="__main__":
    main()
