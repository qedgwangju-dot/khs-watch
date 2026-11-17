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


    # Tests exact issuers, not broad ticker prefixes.
    import thirteenf_sector_watch_entry as entry
    import thirteenf_sector_watch as watch
    for issuer,sector_name in {
        "SEAGATE TECHNOLOGY HOLDINGS":"메모리·저장장치",
        "SANDISK CORP":"메모리·저장장치",
        "SHARONAI HOLDINGS INC":"AI 데이터센터·전력",
        "NEWMONT CORP":"금·귀금속",
        "AGNICO EAGLE MINES":"금·귀금속",
        "UNITY SOFTWARE INC":"게임·3D 소프트웨어",
        "PALANTIR TECHNOLOGIES":"기업·응용 소프트웨어",
        "SPACE EXPLORATION TECHNOLOGIES":"우주·위성·발사체",
    }.items():
        assert watch.sector_for(issuer)==sector_name,(issuer,watch.sector_for(issuer))
    stx=change("보유 확대",180,280,280_000_000,80_000_000,"메모리·저장장치")
    stx["issuer"]="SEAGATE TECHNOLOGY HOLDINGS"
    sndk=change("전량 청산",-100,100,0,120_000_000,"메모리·저장장치")
    sndk["issuer"]="SANDISK CORP"
    tsm=change("보유 축소",-95,5,10_000_000,180_000_000,"반도체·파운드리·장비")
    tsm["issuer"]="TAIWAN SEMICONDUCTOR"
    shaz=change("보유 확대",50,150,150_000_000,90_000_000,"AI 데이터센터·전력")
    shaz["issuer"]="SHARONAI HOLDINGS INC"
    gold=change("신규 매수",200,200,80_000_000,0,"금·귀금속")
    gold["issuer"]="NEWMONT CORP"
    unknown=change("보유 확대",100,100,1_000_000_000,0,"기타")
    unknown["issuer"]="UNMAPPED ISSUER"
    opted=change("신규 매수",100,100,999_000_000,0,
                 "반도체·파운드리·장비",putcall="CALL")
    opted["issuer"]="NVIDIA"
    cases=[stx,sndk,tsm,shaz,gold,unknown,opted]
    short=sector.build_sector_brief(
        cases,lambda value:"$"+format(value,",.0f")+" (원화 병기)",
        watch.security_name_kr,top_n=3)
    for required in (
        "업종별 신규편입·보유확대","업종별 축소·전량청산",
        "메모리·저장장치","시게이트(STX) +180.0%","샌디스크(SNDK) 전량",
        "TSMC(TSM) -95.0%","샤론AI(SHAZ) +50.0%",
        "뉴몬트(NEM) 신규","같은 업종 양방향","업종 미분류",
        "콜 1건 / 풋 0건","순매수 금액으로 차감하지 않으며",
    ):
        assert required in short,required
    assert "$999,000,000" not in short

    # No network request or Telegram send: only the presentation is tested.
    old_rate,old_basis=entry.FX_RATE,entry.FX_BASIS
    try:
        entry.FX_RATE,entry.FX_BASIS=1350.0,"검증용"
        text=entry.build_message_with_owner(
            "Duquesne Family Office",
            {"report_date":"2026-09-30","filing_date":"2026-11-16","form":"13F-HR"},
            {"report_date":"2026-06-30"},cases,
            "https://www.sec.gov/Archives/test")
        assert text.startswith("[13F 산업별 매수·매도 방향] 스탠리 드러켄밀러")
        assert text.index("업종별 신규편입·보유확대") < text.index("업종별 축소·전량청산")
        assert "원화 환산 1달러=1,350.00원" in text
        assert "SEC 공식 원문:" in text
        assert "▶ 주요 신규 매수·보유 확대" not in text
        assert len(text)<3800,len(text)
    finally:
        entry.FX_RATE,entry.FX_BASIS=old_rate,old_basis

    print("13F sector position-ranking regression checks passed.")

if __name__=="__main__":
    main()
