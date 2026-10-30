#!/usr/bin/env python3
"""Synthetic regression tests for ARK industry ranking, notional coverage and rolling daily averages."""
import math

import ark_daily_trade_watch as watch
import ark_notional_enrichment as notional
import ark_sector_rank as sector


def row(fund, ticker, action, shares, day="2026-10-23"):
    return {"date":day, "fund":fund, "ticker":ticker, "action":action,
            "shares":shares, "pct":None}


def main():
    buys=[
        row("ARKK","PACB","매수",202427),
        row("ARKG","FRNM","매수",169498),
        row("ARKG","PACB","매수",68266),
        row("ARKG","SCTX","매수",22479),
    ]
    sells=[
        row("ARKK","GOOG","매도",65812),
        row("ARKW","GOOG","매도",11355),
        row("ARKW","CRCL","매도",42499),
    ]
    prices={
        "PACB":{"close":2.11,"source":"검산"},
        "FRNM":{"close":12.77,"source":"검산"},
        "SCTX":{"close":15.39,"source":"검산"},
        "GOOG":{"close":317.3,"source":"검산"},
        "CRCL":{"close":85.9,"source":"검산"},
    }
    rate=1324.45
    rows=buys+sells
    totals, stocks=sector.aggregate(rows,prices)
    expected_buy=270693*2.11 + 169498*12.77 + 22479*15.39
    bio=totals["바이오·헬스케어"]
    assert math.isclose(bio["매수"],expected_buy,abs_tol=1e-8)
    assert bio["buy_rows"]==4 and bio["buy_priced"]==4
    assert len(bio["buy_tickers"])==3
    assert stocks[("매수","PACB")]["shares"]==270693
    assert stocks[("매수","PACB")]["rows"]==2

    output,snapshot,history=sector.build_sector_digest(
        rows,prices,rate,notional.usd_krw,day="2026-10-23",digest="a1"
    )
    msg="\n".join(output)
    assert "업종별 매수 순위" in msg
    assert "1위 바이오·헬스케어" in msg
    assert "거래행당 평균 매수 추정" in msg
    assert "전체 매수 거래행당 평균" in msg
    assert "270,693주" in msg and "169,498주" in msg
    assert "매도금액 상위 업종" in msg
    assert "순매도 우위" in msg
    assert "누적 관측 1거래일" in msg and "1/5일 확보" in msg
    assert snapshot["complete"] is True

    # Revising the same date must replace the previous day's snapshot, not double count.
    changed_snapshot=dict(snapshot)
    changed_snapshot["digest"]="a2"
    changed_snapshot["buy_usd"]={"바이오·헬스케어":42.5}
    revised=sector.merged_history(history,changed_snapshot)
    assert len(revised)==1 and revised[0]["buy_usd"]["바이오·헬스케어"]==42.5

    # Different tickers must not have their share counts added into a fake sector-share total.
    assert "462,670주" not in msg

    partial={"PACB":prices["PACB"],"GOOG":prices["GOOG"]}
    incomplete=sector.build_sector_digest(
        rows,partial,rate,notional.usd_krw,day="2026-10-23",digest="a3"
    )[0]
    partial_msg="\n".join(incomplete)
    assert "부분합" in partial_msg
    assert "전체 순액 미산출" in partial_msg
    assert "거래행당 평균 매수" not in partial_msg  # no sector-wide average on missing rows
    assert sector.snapshot("2026-10-23","a3",sector.aggregate(rows,partial)[0])["complete"] is False

    unknown=[row("ARKG","ZZZX","매수",100)]
    ranked=sector.build_sector_digest(
        unknown,{"ZZZX":{"close":25.0}},rate,notional.usd_krw,
        day="2026-10-23",digest="unknown"
    )[0]
    unknown_text="\n".join(ranked)
    assert "업종 미분류 매수" in unknown_text
    assert "1위 업종 미확인" not in unknown_text

    # Sector averages use one sample per fully price-covered *trading date*.
    three=[]
    for i in range(3):
        day=f"2026-10-{21+i:02d}"
        three.append({"date":day,"digest":str(i),"complete":True,
            "buy_usd":{"바이오·헬스케어":1000000*(i+1)},
            "sell_usd":{},"buy_rows":{"바이오·헬스케어":2}})
    rolling="\n".join(sector.recent_average_lines(three,rate,notional.usd_krw))
    assert "누적 관측 3거래일" in rolling
    assert notional.usd_krw(2_000_000,rate) in rolling
    assert "3/5일 확보" in rolling

    twenty = []
    for i in range(20):
        twenty.append({
            "date":f"2026-09-{i+1:02d}",
            "digest":str(i), "complete":True, "buy_complete":True,
            "sell_complete":False,
            "buy_usd":{"바이오·헬스케어":2_000_000,"AI·클라우드·기업용 소프트웨어":1_000_000},
            "sell_usd":{},
            "buy_rows":{"바이오·헬스케어":4},
        })
    five_and_twenty="\n".join(sector.recent_average_lines(twenty,rate,notional.usd_krw))
    assert "최근 5거래일 업종별 일평균" in five_and_twenty
    assert "최근 20거래일 업종별 일평균" in five_and_twenty
    assert notional.usd_krw(2_000_000,rate) in five_and_twenty

    # Missing sell prices must not invalidate a fully-priced buy-side average.
    buy_only_snapshot = sector.snapshot("2026-10-23","partial",sector.aggregate(rows,partial)[0])
    assert buy_only_snapshot["complete"] is False
    assert buy_only_snapshot["buy_complete"] is False

    full = watch.build(rows,"2026-10-23",rate=rate,basis="검산",
             prices=prices,history=[],digest="test",sector_upgrade=True)
    assert "업종 순위 보강본" in full
    assert full.index("업종별 매수 순위") < full.index("매수 · 펀드별 거래")
    assert full.index("업종별 매수 순위") < full.index("매도 · 펀드별 거래")
    assert "실제 체결대금 아님" in full

    # Current official Oct 29 names must no longer fall into the unknown sector.
    for ticker,expected in {
        "CBRS":"반도체·자동화 장비",
        "JOBY":"항공·도심항공교통",
        "KDK":"자동차·자율주행",
        "BEAM":"바이오·헬스케어",
        "ARCT":"바이오·헬스케어",
        "TEM":"바이오·헬스케어",
        "TXG":"바이오·헬스케어",
    }.items():
        assert sector.classify(ticker)[0]==expected

    # History length now keeps enough samples to build a real three-month view.
    samples=[{"date":f"2026-01-{i:02d}","digest":str(i)}
             for i in range(1,22)]
    assert len(sector.merged_history(samples,{"date":"2026-02-01","digest":"latest"}))==22

    # 2026 NYSE holidays are removed from the coverage denominator.
    import datetime as dt
    assert sector.expected_sessions(dt.date(2026,9,7),dt.date(2026,9,8))==1
    assert sector.expected_sessions(dt.date(2026,10,1),dt.date(2026,10,29))==21
    assert sector.period_windows("2026-10-29")[-1][1].isoformat()=="2026-07-30"
    assert sector.subtract_months(dt.date(2027,5,31),3)==dt.date(2027,2,28)

    # The five captured trading days must never masquerade as the full month.
    # Dollars are persisted estimated USD, NOT actual execution or ETF flow.
    history_cases=[
        ("2026-10-23", 3082053.125763, 47104513.502213),
        ("2026-10-26", 27017481.455112, 39141733.579038),
        ("2026-10-27", 28801316.718201, 26788076.094849),
        ("2026-10-28", 47097112.558195, 26520632.776778),
        ("2026-10-29", 8063262.141505, 1460763.031006),
    ]
    snapshots=[
        {"date":d,"digest":d,"complete":True,"buy_usd":{"바이오·헬스케어":b},
         "sell_usd":{"바이오·헬스케어":v}}
        for d,b,v in history_cases
    ]
    period="\n".join(sector.direction_summary(snapshots,"2026-10-29",
                                              rate,notional.usd_krw))
    assert "당일 (2026-10-29~2026-10-29)" in period
    assert "이번 주 (2026-10-26~2026-10-29)" in period
    assert "4/4거래일" in period and "거래일 전부 확보" in period
    assert "당월 누적 (2026-10-01~2026-10-29)" in period
    assert "5/21거래일" in period and "확보일 기준 부분합" in period
    assert "최근 3개월 (2026-07-30~2026-10-29)" in period
    assert "순매수 +" in period and "순매도 -" in period
    assert "매수 비중" in period
    assert "미확보 일자를 0원으로 채우지 않으며" in period

    # Missing market close forbids a fake "net buying" direction.
    broken=[dict(snapshots[0],complete=False)]
    blocked="\n".join(sector.direction_summary(broken,"2026-10-23",
                                               rate,notional.usd_krw))
    assert "순액 판정 보류(미확인 종가)" in blocked

    # Upgrades to the alert should not silently alter pre-existing dedup keys.
    full_with_history=watch.build(rows,"2026-10-23",rate=rate,basis="검산",
        prices=prices,history=[],digest="test")
    assert "당일·주간·당월·최근 3개월 매매 방향" not in full_with_history or "매매 방향 · 당일" in full_with_history
    assert full_with_history.index("매매 방향") < full_with_history.index("업종별 매수 순위")

    print("ARK sector ranking and rolling-mean regression checks passed.")


if __name__=="__main__":
    main()
