#!/usr/bin/env python3
"""Regression: 13F sector ranks are values of position deltas, never purchase cash."""
import math
import thirteenf_sector_rank as sector

def change(action, delta, shares, cur_value, prev_value, name="바이오·헬스케어", putcall=""):
    return {
        "action":action,"delta_shares":delta,"shares":shares,
        "cur_value":cur_value,"prev_value":prev_value,
        "sector":name,"putcall":putcall,
    }


def main():
    new = change("신규 매수", 100, 100, 2000, 0)
    increase = change("보유 확대", 50, 150, 3000, 1400)
    shrink = change("보유 축소", -60, 40, 450, 1000, name="반도체")
    exit_row = change("전량 청산", -200, 200, 0, 2000, name="소프트웨어")
    calls = change("신규 매수", 100000, 100000, 10000000, 0, putcall="CALL")

    assert sector.changed_share_reference_value(new)==("buy",2000)
    side,value=sector.changed_share_reference_value(increase)
    assert side=="buy" and math.isclose(value,1000)
    side,value=sector.changed_share_reference_value(shrink)
    assert side=="sell" and math.isclose(value,600)
    assert sector.changed_share_reference_value(exit_row)==("sell",2000)
    assert sector.changed_share_reference_value(calls)==(None,0.0)

    result=sector.build_ranking([new,increase,shrink,exit_row,calls],
                                lambda x:f"{x:.1f}달러(원화 병기 테스트)")
    assert "1위 바이오·헬스케어: 3000.0달러" in result
    assert "행당 평균 1500.0달러" in result
    assert "600.0달러" in result and "2000.0달러" in result
    assert "콜·풋옵션 1개" in result
    assert "실제 매수대금 아님" in result
    assert "매도대금 아님" in result
    assert "현금 순매수" in result
    assert "10000000" not in result

    print("13F sector position-ranking regression checks passed.")

if __name__=="__main__":
    main()
