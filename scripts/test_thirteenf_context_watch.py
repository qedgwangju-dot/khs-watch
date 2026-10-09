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
    print("13F CDW manager-context regression checks passed.")

if __name__=="__main__":
    main()
