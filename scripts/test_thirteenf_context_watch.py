#!/usr/bin/env python3
"""Regression checks: CDW follow-up must not be announced as a new SEC 13F."""
import thirteenf_context_watch as c

def main():
    state={"managers":{"Duquesne Family Office":{
       "report_date":"2026-06-30","accession":"0001536411-26-000006"
    }},"seen_context_events":[]}
    assert c.should_send(state)
    assert "신규" in c.build(1342.78,"검산") and "새 13F 공시 아님" in c.build(1342.78,"검산")
    assert "743,950주" in c.build(1342.78,"검산")
    assert "250,000주" in c.build(1342.78,"검산")
    assert "옵션 매입 비용" in c.build(1342.78,"검산")
    # The one-time Q3 monetary addendum must use the same compact Korean
    # display as future recurring 13F sector alerts (display rounded only).
    assert c.amount(202_721_373,1334.87)=="2.03억달러 (약 2,706억원)"
    assert c.amount(146_045_336,1334.87)=="1.46억달러 (약 1,950억원)"
    assert c.amount(57_553_563,1334.87)=="5,760만달러 (약 768억원)"
    assert c.amount(5_573_819_392,1334.87)=="55.74억달러 (약 7.44조원)"

    state["seen_context_events"]=[c.KEY]
    assert not c.should_send(state)
    state["seen_context_events"]=[]
    state["managers"]["Duquesne Family Office"]["report_date"]="2026-09-30"
    assert not c.should_send(state)

    # 13F information table can repeat the same CUSIP by investment
    # discretion; overwriting a row creates false position exits.
    import thirteenf_sector_watch as w
    original_xml=w.info_xml_url
    xml=('<informationTable>'
         '<infoTable><nameOfIssuer>TEST CO</nameOfIssuer>'
         '<titleOfClass>COM</titleOfClass><cusip>123456789</cusip>'
         '<value>300</value><shrsOrPrnAmt><sshPrnamt>3</sshPrnamt></shrsOrPrnAmt></infoTable>'
         '<infoTable><nameOfIssuer>TEST CO</nameOfIssuer>'
         '<titleOfClass>COM</titleOfClass><cusip>123456789</cusip>'
         '<value>400</value><shrsOrPrnAmt><sshPrnamt>4</sshPrnamt></shrsOrPrnAmt></infoTable>'
         '</informationTable>')
    try:
        w.info_xml_url=lambda *_:("https://www.sec.gov/test",xml)
        positions,_=w.parse_holdings("0001536411","0001536411-26-000011")
        merged=positions["123456789|COM|"]
        assert merged["shares"]==7 and merged["value"]==700 and merged["source_rows"]==2
        w.info_xml_url=lambda *_:("https://www.sec.gov/test",xml.replace("<value>300</value>","<value>BAD</value>"))
        try:
            w.parse_holdings("0001536411","0001536411-26-000011")
            raise AssertionError("Invalid SEC valuation must fail, not create zero-valued exits")
        except ValueError:
            pass
        w.info_xml_url=lambda *_:("https://www.sec.gov/test","<informationTable/>")
        try:
            w.parse_holdings("0001536411","0001536411-26-000011")
            raise AssertionError("Empty SEC info table must fail closed")
        except RuntimeError:
            pass
    finally:
        w.info_xml_url=original_xml

    def row(issuer,shares,pc="",cusip="123456789"):
        return {"issuer":issuer,"shares":shares,"value":shares*100,
                "putcall":pc,"title":"COM","cusip":cusip}
    def make(prev=None,cur=None,url=None):
        return {"previous":{str(i):row(*x) for i,x in enumerate(prev or [])},
                "current":{str(i):row(*x) for i,x in enumerate(cur or [])},
                "url":url or "https://www.sec.gov/Archives/test/infoTable.xml",
                "accession":"0000000000-26-000001"}
    holdings={
        "Duquesne Family Office":make(
            prev=[("SEAGATE TECHNOLOGY",122000),("UNITY SOFTWARE",738000),
                  ("AMAZON.COM INC",541500),("TAIWAN SEMICONDUCTOR",606000),
                  ("ALPHABET INC",10000,"","02079K305")],
            cur=[("SEAGATE TECHNOLOGY",341790),("UNITY SOFTWARE",3956385),
                 ("AMAZON.COM INC",772600),("TAIWAN SEMICONDUCTOR",49000)]),
        "Situational Awareness":make(
            prev=[("SHARONAI HOLDINGS INC",5400000),("MICRON TECHNOLOGY",4828000),
                  ("SANDISK CORP",2495300),("BLOOM ENERGY CORP",6272800),
                  ("NEBIUS GROUP N.V.",4464300)],
            cur=[("SHARONAI HOLDINGS INC",8070000),
                 ("SANDISK CORP",105000,"CALL"),("NEBIUS GROUP N.V.",1410000,"CALL")]),
        "Third Point":make(prev=[],cur=[("NVIDIA CORPORATION",1500000)]),
        "Appaloosa":make(prev=[("MICRON TECHNOLOGY",100000)],
                        cur=[("MICRON TECHNOLOGY",375000),("NVIDIA CORPORATION",475000)]),
        "NVIDIA":make(prev=[("INTEL CORP",214776632),("SPACE EXPLORATION",122764805)],
                      cur=[("INTEL CORP",161082488),("SPACE EXPLORATION",130472925)]),
        "Berkshire Hathaway":make(prev=[("DELTA AIR LINES",100000),("LENNAR CORP",100000)],
                                   cur=[("DELTA AIR LINES",112400),("LENNAR CORP",198600)]),
    }
    ready={"managers":{label:{"report_date":"2026-09-30",
                            "accession":"0000000000-26-000001"}
                       for label in c.Q3_FOCUS_MANAGERS},
           "seen_context_events":[]}
    assert c.q3_ready(ready)
    message=c.build_q3_cross_report(holdings)
    for phrase in ("마이크론 신고상 소멸", "샌디스크 콜옵션",
                   "엔비디아 신규보고", "시게이트 +180.2%",
                   "인텔 -25.0%", "스페이스X +6.3%", "GOOGL 신고상 소멸",
                   "지분 75.1%", "초과편입 1%→3%",
                   "매도 확정 금지", "달러 단위"):
        assert phrase in message, phrase
    assert len(message)<3750,len(message)
    ready["seen_context_events"]=[c.Q3_COMPARE_KEY]
    assert not c.q3_ready(ready)
    ready["seen_context_events"]=[]
    ready["q3_pending_delivery"]={"key":c.Q3_COMPARE_KEY}
    assert not c.q3_ready(ready)
    del ready["q3_pending_delivery"]
    ready["managers"]["NVIDIA"]["report_date"]="2026-06-30"
    assert not c.q3_ready(ready)
    try:
        c.build_q3_cross_report({"NVIDIA":holdings["NVIDIA"]})
        raise AssertionError("Missing cross-manager sources should not alert")
    except ValueError:
        pass

    # Q3 13F amount supplement has a separate one-shot deduplication key.
    ready={"managers":{label:{"report_date":"2026-09-30","accession":"test"}
                       for label in c.Q3_FOCUS_MANAGERS},
           "seen_context_events":[c.Q3_COMPARE_KEY]}
    assert c.q3_amount_ready(ready)
    ready["q3_value_pending_delivery"]={"key":c.Q3_VALUE_KEY}
    assert not c.q3_amount_ready(ready)
    ready.pop("q3_value_pending_delivery")
    ready["seen_context_events"].append(c.Q3_VALUE_KEY)
    assert not c.q3_amount_ready(ready)

    # Verified monetary addendum; synthetic SEC snapshots, never sends a message.
    import copy
    audit=copy.deepcopy(holdings)
    for label in c.Q3_FOCUS_MANAGERS:
        audit[label]["previous_accession"]="0009999999-26-000002"
    audit["Duquesne Family Office"]["accession"]="0001536411-26-000011"
    audit["Duquesne Family Office"]["previous_accession"]="0001536411-26-000006"
    for entry in audit["Duquesne Family Office"]["current"].values():
        if "SEAGATE" in entry["issuer"]:
            entry["value"]=315247
    for entry in audit["Duquesne Family Office"]["previous"].values():
        if "SEAGATE" in entry["issuer"]:
            entry["value"]=117728
    for entry in audit["Situational Awareness"]["current"].values():
        if "SHARONAI" in entry["issuer"]:
            entry["value"]=440670000
    valid=c.build_q3_amount_addendum(audit,1334.87,"2026-11-16 ECB 테스트")
    assert "시게이트(STX)" in valid and "약" in valid and "억원" in valid
    assert "아팔루사 MU" in valid and "엔비디아 INTC" in valid
    assert "원문 단위 차이에 한해 ×1,000" in valid
    assert "보강본이며 신규 13F 공시는 아닙니다" in valid
    assert len(valid)<3600
    audit["Duquesne Family Office"]["accession"]="0001536411-27-000001"
    try:
        c.build_q3_amount_addendum(audit,1334.87,"미검증 단위")
        raise AssertionError("An unaudited filing must not show corrected cash amounts")
    except RuntimeError as error:
        assert "valuation unit not verified" in str(error)
    audit["Duquesne Family Office"]["accession"]="0001536411-26-000011"
    for entry in audit["Duquesne Family Office"]["current"].values():
        if "SEAGATE" in entry["issuer"]:
            entry["value"]=315
    try:
        c.build_q3_amount_addendum(audit,1334.87,"규모 오류")
        raise AssertionError("An incorrectly scaled 13F must be suppressed")
    except RuntimeError as error:
        assert "reference" in str(error)


    # WallstreetCN/Dow Jones 2026Q3 Duquesne follow-up is checked against
    # SEC Q2+Q3 share deltas, dollar units and portfolio-weight denominator.
    duq={"managers":{"Duquesne Family Office":{
           "cik":"0001536411","report_date":"2026-09-30",
           "accession":c.DUQ_Q3_ACCESSION}},
         "seen_context_events":[c.Q3_COMPARE_KEY]}
    assert c.duq_article_ready(duq)
    duq["duq_article_pending_delivery"]={"key":c.DUQ_ARTICLE_KEY}
    assert not c.duq_article_ready(duq)
    del duq["duq_article_pending_delivery"]
    duq["seen_context_events"].append(c.DUQ_ARTICLE_KEY)
    assert not c.duq_article_ready(duq)

    def secrow(issuer,shares,value,cusip=""):
        return {"issuer":issuer,"shares":shares,"value":value,
                "cusip":cusip,"title":"COM","putcall":""}
    before=[
        secrow("ADVANCED MICRO DEVICES",72900,42300),
        secrow("SANDISK CORP",34900,79400),
        secrow("ALPHABET INC",336300,120200,"02079K305"),
        secrow("TAIWAN SEMICONDUCTOR",589680,281600),
        secrow("NATERA INC",3186306,1260000),
        secrow("SEAGATE TECHNOLOGY",122000,117728),
    ]
    current=[
        secrow("SPACE EXPLORATION TECHN CORP",202125,30493),
        secrow("PALANTIR TECHNOLOGIES",80100,14983),
        secrow("APPLOVIN CORP",109460,31790),
        secrow("TAIWAN SEMICONDUCTOR",32700,14917),
        secrow("NATERA INC",3160666,1306335),
        secrow("SEAGATE TECHNOLOGY",341790,315247),
        secrow("NEWMONT CORP",380400,43875),
        secrow("BARRICK MNG CORP",1054600,42891),
        secrow("AGNICO EAGLE MINES",231050,42345),
    ]
    remaining=4470867-sum(row0["value"] for row0 in current)
    assert remaining>0
    current.append(secrow("OTHER HOLDINGS INC",100000,remaining))
    snapshot={"current":{str(i):z for i,z in enumerate(current)},
              "previous":{str(i):z for i,z in enumerate(before)},
              "factors":(1000,1000),"url":"https://www.sec.gov/Archives/edgar/data/1536411/000153641126000011/form13f_20260930.xml"}
    report=c.build_duq_article_followup(snapshot,1334.87,"2026-11-16 ECB 테스트")
    for phrase in (
        "스페이스X: 신규 202,125주",
        "팔란티어(PLTR): 신규 80,100주",
        "앱러빈(APP): 신규 109,460주",
        "AMD: 2분기 72,900주 → 3분기 신고 없음",
        "샌디스크(SNDK): 2분기 34,900주",
        "알파벳 A(GOOGL): 2분기 336,300주",
        "TSMC 589,680→32,700주 (-94.5%)",
        "나테라(NTRA) 3,160,666주",
        "29.2%로 1위",
        "매도일·매도가격은 미공개",
        "3분기말", "억원",
    ):
        assert phrase in report,phrase
    assert len(report)<3750,len(report)
    snapshot["current"]["0"]["shares"]=202124
    try:
        c.build_duq_article_followup(snapshot,1334.87,"unit regression")
        raise AssertionError("Bad SpaceX position must block article alert")
    except RuntimeError as error:
        assert "SEC article disagreement" in str(error)


    # 13F source uses the same CUSIP with a renamed security class title:
    # YPF sponsored ADR class D -> sponsored ADS. It is not both a new and
    # liquidated position; original issuer and put/call must be unchanged.
    old_ypf={"YPF_OLD":{"issuer":"Ypf Sociedad Anonima",
             "cusip":"984245100","title":"SPON ADR CL D","putcall":"",
             "shares":3138897,"value":143000000}}
    new_ypf={"YPF_NEW":{"issuer":"Ypf Sociedad Anonima",
             "cusip":"984245100","title":"SPONSORED ADS","putcall":"",
             "shares":3541897,"value":177600000}}
    matched=w.classify_changes(new_ypf,old_ypf)
    assert len(matched)==1 and matched[0]["action"]=="보유 확대"
    assert matched[0]["delta_shares"]==403000
    assert matched[0]["prev_value"]==143000000
    # Options are a distinct security even with the same CUSIP.
    opt=dict(old_ypf["YPF_OLD"],putcall="CALL",title="CALL",shares=250000)
    second=w.classify_changes({"current":new_ypf["YPF_NEW"]},
                              {"prior":old_ypf["YPF_OLD"],"option":opt})
    assert len(second)==2
    assert {x["action"] for x in second}=={"보유 확대","전량 청산"}
    assert any(x.get("putcall")=="CALL" and x["action"]=="전량 청산"
               for x in second)

    print("13F CDW manager-context regression checks passed.")

if __name__=="__main__":
    main()
