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
    # Independent prices must be from exactly the specified trade date.
    import json, datetime as dt
    timestamp=int(dt.datetime(2026,10,20,20,0,tzinfo=dt.timezone.utc).timestamp())
    old_request=n._request
    try:
        def fake_request(url,timeout=8):
            if "stooq.com" in url:
                return b"Date,Open,High,Low,Close,Volume\n2026-10-20,10.10,10.99,10.02,10.74,5000000\n"
            if "finance.yahoo.com" in url:
                return json.dumps({"chart":{"result":[{"timestamp":[timestamp],
                   "indicators":{"quote":[{"close":[10.74]}]}}]}}).encode()
            raise AssertionError("Unexpected price source")
        n._request=fake_request
        assert n.stooq_close("XE","2026-10-20")==10.74
        assert n.yahoo_close("XE","2026-10-20")==10.74
        assert n.close_prices([{"ticker":"XE"}],"2026-10-20")["XE"]["close"]==10.74
        assert n.stooq_close("XE","2026-10-21") is None
    finally:
        n._request=old_request

    # Full Oct 20 ARK direction/fund coverage: no rows silently omitted.
    # The trade-notice shares are exact; prices in the output remain estimates.
    rows_20261020 = [
        ("ARKK","Buy","XE",292022),("ARKQ","Buy","XE",126437),
        ("ARKX","Buy","XE",66436),("ARKQ","Buy","OKLO",150998),
        ("ARKX","Buy","LUNR",120900),("ARKG","Buy","IAM",101248),
        ("ARKG","Buy","SCTX",10832),("ARKK","Buy","PACB",225455),
        ("ARKG","Buy","PACB",77416),
        ("ARKK","Sell","PLTR",27790),("ARKK","Sell","SHOP",24430),
        ("ARKQ","Sell","TER",15964),("ARKQ","Sell","ESLT",1428),
        ("ARKX","Sell","ESLT",1500),("ARKG","Sell","PSNL",385778),
    ]
    full = ("date,fund,direction,ticker,cusip,name,shares,% of etf\n" +
            "".join(
                f"10/20/2026,{fund},{action},{ticker},000000,{ticker},{shares},0.1\n"
                for fund,action,ticker,shares in rows_20261020
            )).encode()
    parsed = w.parse(full)
    assert len(parsed)==len(rows_20261020)
    assert sum(r["shares"] for r in parsed if r["ticker"]=="XE" and r["action"]=="매수")==484895
    assert sum(r["shares"] for r in parsed if r["ticker"]=="PACB" and r["action"]=="매수")==302871
    assert {(r["fund"],r["ticker"]) for r in parsed if r["ticker"]=="ESLT"}=={("ARKQ","ESLT"),("ARKX","ESLT")}
    all_note = w.build(parsed,"2026-10-20",rate=1322.35,basis="2026-10-22",
                       prices={"XE":{"close":10.74,"source":"검산"}})
    assert "ARKX | 엑스에너지(XE)" in all_note
    assert "ARKK | 팩바이오(PACB)" in all_note
    assert "ARKG | 팩바이오(PACB)" in all_note
    assert "ARKX | 엘빗 시스템즈(ESLT)" in all_note
    assert "ARKQ | 엘빗 시스템즈(ESLT)" in all_note
    assert "당일 종가 기준 추정" in all_note
    assert "가격 확인 3/9개 거래행" in all_note
    assert "실제 체결단가·실제 체결대금" in all_note

    # Official share quantities are never presented as exact cash spent.
    # All selected names must be visible in Korean with the trade date and a
    # dollar amount immediately followed by converted KRW when a price exists.
    new_rows=[
        {"date":"2026-10-22","fund":"ARKK","ticker":"META","action":"매수","shares":28069,"pct":0.2901},
        {"date":"2026-10-22","fund":"ARKG","ticker":"SCTX","action":"매수","shares":99254,"pct":0.0877},
        {"date":"2026-10-22","fund":"ARKG","ticker":"FRNM","action":"매수","shares":35377,"pct":0.0229},
        {"date":"2026-10-22","fund":"ARKQ","ticker":"TER","action":"매도","shares":5222,"pct":0.1},
    ]
    close={"META":{"close":697.50,"source":"검산"},
           "SCTX":{"close":19.34,"source":"검산"}}
    report=w.build(new_rows,"2026-10-22",rate=1342.78,basis="검산",prices=close)
    assert "메타 플랫폼스(META)" in report
    assert "스크라이브 테라퓨틱스(SCTX)" in report
    assert "프리놈(FRNM)" in report
    assert "테라다인(TER)" in report
    assert "28,069주 매수" in report
    assert "종가 기준 추정" in report
    assert "달러(약 " in report
    assert "가격 확인 2/3개 거래행" in report
    assert "거래대금: 체결단가 미공개·종가 추정 불가" in report


    # A prepared but unconfirmed send must block the next scheduled replay.
    # Mock the official source and state: never invoke real internet or Telegram.
    old_fetch,old_parse,old_load=w._fetch,w.parse,w._load
    try:
        today=w.dt.datetime.now(w.ET).date().isoformat()
        w._fetch=lambda: (b"mock ark trade table","text/plain")
        w.parse=lambda _:[{"date":today,"fund":"ARKK","ticker":"CBRS",
                            "action":"매수","shares":10,"pct":0.1}]
        w._load=lambda: {"version":1,"last_date":"2026-10-29",
                          "digest":"previous","format_version":3,
                          "pending_delivery":{"last_date":today,"digest":"reserved"}}
        try:
            w.main()
            raise AssertionError("An unconfirmed Telegram send must block auto replay")
        except RuntimeError as e:
            assert "ARK_DELIVERY_UNCERTAIN" in str(e)
    finally:
        w._fetch,w.parse,w._load=old_fetch,old_parse,old_load

    print("ARK daily trade parser regression tests passed.")

if __name__=="__main__":
    main()
