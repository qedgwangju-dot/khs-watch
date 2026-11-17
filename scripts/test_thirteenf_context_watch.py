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

    print("13F CDW manager-context regression checks passed.")

if __name__=="__main__":
    main()
