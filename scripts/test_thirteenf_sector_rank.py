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

    # New industry-first alert is quantity-based, not an unverified cash-flow table.
    direction=sector.build_sector_direction(
        cases,watch.security_name_kr,top_n=3)
    assert direction.index("▶ 신규 편입·보유 확대") < direction.index("▶ 보유 축소·전량 청산")
    assert "■ 집중 확대:" in direction and "■ 집중 축소:" in direction
    assert "시게이트(STX) +180주 (180.0%)" in direction
    assert "샌디스크(SNDK) 전량 -100주" in direction
    assert "TSMC(TSM) -95주 (95.0%)" in direction
    assert "업종 분류 5/6행 (83%)" in direction
    assert "미분류 확대 1행 / 축소 0행" in direction
    assert "옵션 별도: 콜 1행 / 풋 0행" in direction
    assert "달러·원화 금액은 표시하지 않습니다" in direction
    assert "$" not in direction
    assert "실제 체결대금" not in direction
    assert len(direction)<2400,len(direction)

    # On mixed sectors, do not convert different quarter-end marks to a net cash buy.
    mix=change("보유 축소",-30,70,10000000,12000000,
               "메모리·저장장치")
    mix["issuer"]="SEAGATE TECHNOLOGY HOLDINGS"
    mixed=sector.build_sector_direction([stx,mix],watch.security_name_kr,top_n=3)
    assert "동일 업종 내 양방향 변화" in mixed
    assert "확대 1행 / 축소 1행" in mixed
    assert "금액 순매수 판정 안 함" in mixed

    # Mark low sector coverage as incomplete, without showing all funds as sold.
    limited=sector.build_sector_direction(
        [unknown,unknown,unknown,unknown,new],watch.security_name_kr)
    assert "전체 포트폴리오 방향을 대표하지 못할 수 있습니다" in limited

    # SEC Q3/Q2 Duquesne values are demonstrably thousand-scaled outliers.
    cur={"accession":"0001536411-26-000011"}
    prev={"accession":"0001536411-26-000006"}
    assert sector.verified_scale("Duquesne Family Office",cur)==1000
    assert sector.verified_scale("Duquesne Family Office",prev)==1000
    assert sector.verified_scale("Appaloosa",cur)==1
    assert sector.verified_scale("Duquesne Family Office",
                                 {"accession":"0001536411-27-000001"}) is None
    seagate=change("보유 확대",219790,341790,315247,117728,"메모리·저장장치")
    seagate["issuer"]="SEAGATE TECHNOLOGY HLDNGS"
    checked=sector.verified_change_values([seagate],"Duquesne Family Office",cur,prev)
    assert checked[0]["valuation_verified"]
    assert checked[0]["cur_value"]==315_247_000
    assert checked[0]["prev_value"]==117_728_000
    side,amount=sector.changed_share_reference_value(checked[0])
    assert side=="buy" and 202_000_000<amount<204_000_000
    display_money=lambda x:f"{x/1_000_000:,.1f}백만달러(약 {x*1350/100_000_000:,.1f}억원)"
    rendered=sector.build_sector_direction(checked,watch.security_name_kr,
                                           money=display_money,top_n=3)
    assert "변경분" in rendered and "백만달러(약" in rendered
    assert "202." in rendered

    unknown_filing=sector.verified_change_values(
        [seagate],"Duquesne Family Office",
        {"accession":"0001536411-27-000001"},prev)
    no_amount=sector.build_sector_direction(
        unknown_filing,watch.security_name_kr,money=display_money)
    assert "평가액 단위 확인 전" in no_amount
    assert "변경분 평가액 미검증" in no_amount
    assert "202." not in no_amount

    # No network request or Telegram send: only the presentation is tested.
    old_rate,old_basis=entry.FX_RATE,entry.FX_BASIS
    try:
        entry.FX_RATE,entry.FX_BASIS=1350.0,"검증용"
        text=entry.build_message_with_owner(
            "Duquesne Family Office",
            {"report_date":"2026-09-30","filing_date":"2026-11-16",
             "form":"13F-HR","accession":"0001536411-26-000011"},
            {"report_date":"2026-06-30","accession":"0001536411-26-000006"},cases,
            "https://www.sec.gov/Archives/test")
        assert text.startswith("[13F 핵심 변화 자동 추출] 스탠리 드러켄밀러")
        assert text.index("▶ 신규 편입·보유 확대") < text.index("▶ 보유 축소·전량 청산")
        assert "■ 집중 확대:" in text and "■ 집중 축소:" in text
        assert "보유 기준 2026-09-30" in text
        assert "시게이트(STX)" in text and "샌디스크(SNDK)" in text
        assert "메모리·저장장치" in text and "반도체·파운드리·장비" in text
        assert "SEC 공식 원문:" in text
        assert "환율 1달러=1,350.00원" in text
        assert "변경분" in text and "달러" in text and "원" in text
        assert "▶ 주요 신규 매수·보유 확대" not in text
        assert "<b>" not in text
        assert len(text)<3800,len(text)
    finally:
        entry.FX_RATE,entry.FX_BASIS=old_rate,old_basis

    # Korean currency rendering is display-only: USD amounts retain their
    # exact source values for all valuation and USD/KRW calculations.
    assert sector.compact_usd(202_721_373)=="2.03억달러"
    assert sector.compact_usd(131_696_500)=="1.32억달러"
    assert sector.compact_usd(265_996_487)=="2.66억달러"
    assert sector.compact_usd(146_045_336)=="1.46억달러"
    assert sector.compact_usd(57_553_563)=="5,760만달러"
    assert sector.compact_usd(105_000)=="11만달러"
    assert sector.compact_usd(10_000)=="1만달러"
    assert sector.compact_usd(100_500_000)=="1.01억달러"  # half-up not bankers
    assert sector.compact_usd(0)=="0달러"
    assert sector.compact_krw(202_721_373*1334.87)=="약 2,706억원"
    assert sector.compact_krw(131_696_500*1334.87)=="약 1,758억원"
    assert sector.compact_krw(146_045_336*1334.87)=="약 1,950억원"
    assert sector.compact_krw(7_573_700_000_000)=="약 7.57조원"
    assert sector.compact_krw(950_000_000)=="약 9.5억원"
    assert sector.compact_krw(1_250_000_000)=="약 13억원"
    assert sector.compact_krw(1_000_000_000)=="약 10억원"
    assert entry._usd_text(202_721_373)=="2.03억달러"
    assert entry._krw_text(270_606_679_000)=="약 2,706억원"
    old_rate,old_basis=entry.FX_RATE,entry.FX_BASIS
    try:
        entry.FX_RATE,entry.FX_BASIS=1334.87,"회귀 검증"
        assert entry.money_with_krw(0)=="0달러 (약 0원)"
        assert entry.money_with_krw(202_721_373)=="2.03억달러 (약 2,706억원)"
        assert entry.money_with_krw(146_045_336)=="1.46억달러 (약 1,950억원)"
    finally:
        entry.FX_RATE,entry.FX_BASIS=old_rate,old_basis


    # Crucially, no article or ticker allowlist is supplied to the generic
    # filing renderer: scan the full diff, even if a position's sector is '기타'.
    def position(issuer,ticker,shares,value,sector_name="기타"):
        return {"issuer":issuer,"title":"COM","cusip":ticker,
                "shares":shares,"value":value,"putcall":"","sector":sector_name}
    holdings={
        "ntra":position("NATERA INC","NTRA",3160666,1306335000,"헬스케어"),
        "stx":position("SEAGATE TECHNOLOGY HOLDINGS","STX",341790,315247000,
                       "메모리·저장장치"),
        "spcx":position("SPACE EXPLORATION TECHNOLOGIES","SPCX",202125,30493000,
                        "우주·위성·발사체"),
        "pltr":position("PALANTIR TECHNOLOGIES","PLTR",80100,14983000,
                        "기업·응용 소프트웨어"),
        "app":position("APPLOVIN CORP","APP",109460,31790000,
                       "디지털 광고·AI 앱 플랫폼"),
        "other1":position("OTHER ONE","OT1",100000,1000000000),
        "other2":position("OTHER TWO","OT2",100000,1000000000),
        "other3":position("OTHER THREE","OT3",100000,774902000),
    }
    def move(issuer,action,delta,current_shares,cur_value,prev_value,sector_name):
        return {"issuer":issuer,"title":"COM","cusip":issuer,
                "action":action,"delta_shares":delta,"shares":current_shares,
                "cur_value":cur_value,"prev_value":prev_value,"sector":sector_name,
                "putcall":"","valuation_verified":True}
    list_changes=[
        move("SOMNIGROUP","신규 매수",200000,200000,61700000,0,"소비재·가구"),
        move("NEWMONT CORP","신규 매수",380400,380400,43900000,0,"금·귀금속"),
        move("BARRICK CORP","신규 매수",1054600,1054600,42900000,0,"금·귀금속"),
        move("AGNICO EAGLE","신규 매수",231050,231050,42300000,0,"금·귀금속"),
        move("WESTERN DIGITAL","신규 매수",100000,100000,36800000,0,"메모리·저장장치"),
        move("APPLOVIN CORP","신규 매수",109460,109460,31790000,0,"디지털 광고·AI 앱 플랫폼"),
        move("SPACE EXPLORATION TECHNOLOGIES","신규 매수",202125,202125,30493000,0,"우주·위성·발사체"),
        move("PALANTIR TECHNOLOGIES","신규 매수",80100,80100,14983000,0,"기업·응용 소프트웨어"),
        move("UNITED AIR LINES","전량 청산",-794795,794795,0,164000000,"항공·항공우주·여행"),
        move("ALPHABET INC","전량 청산",-336300,336300,0,120200000,"AI 플랫폼·클라우드"),
        move("SANDISK CORP","전량 청산",-34900,34900,0,79400000,"메모리·저장장치"),
        move("ADVANCED MICRO DEVICES","전량 청산",-72900,72900,0,42300000,"반도체·파운드리·장비"),
        move("SEAGATE TECHNOLOGY HOLDINGS","보유 확대",219790,341790,315247000,117728000,"메모리·저장장치"),
        move("UNITY SOFTWARE","보유 확대",3217600,3956385,161900000,30500000,"게임·3D 소프트웨어"),
        move("AMAZON.COM INC","보유 확대",231000,772600,192500000,135000000,"AI 플랫폼·클라우드"),
        move("TAIWAN SEMICONDUCTOR","보유 축소",-556980,32700,16000000,281600000,"반도체·파운드리·장비"),
    ]
    # Alphabet A and C shares are distinct CUSIPs/13F security classes.
    next(x for x in list_changes if x["issuer"]=="ALPHABET INC")["title"]="CAP STK CL A"
    rank_output=sector.build_automatic_13f_digest(
        list_changes,holdings,watch.security_name_kr,lambda x:sector.compact_usd(x),
        report_scale=1,max_chars=3300)
    for required in ("스페이스X","팔란티어(PLTR)","앱러빈(APP)",
                     "AMD","샌디스크(SNDK)","알파벳 A(GOOGL)",
                     "시게이트(STX)","유니티(U)","아마존(AMZN)",
                     "TSMC(TSM)","나테라(NTRA)","29.2%"):
        assert required in rank_output, (required,rank_output)
    assert "신고상 종료" in rank_output and "실제" in rank_output
    assert len(rank_output)<=3300
    assert "전체 13F 신고 평가액" in rank_output
    # A missing verified unit must never silently become a dollar amount.
    unknown_scale=[dict(list_changes[6],valuation_verified=False)]
    check=sector.build_automatic_13f_digest(
        unknown_scale,{"test":holdings["spcx"]},watch.security_name_kr,
        lambda x:sector.compact_usd(x),report_scale=None)
    assert "금액 미검증" in check and "3,049만달러" not in check

    print("13F sector position-ranking regression checks passed.")

if __name__=="__main__":
    main()
