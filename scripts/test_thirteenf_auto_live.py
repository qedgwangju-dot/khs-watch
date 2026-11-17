#!/usr/bin/env python3
"""Read-only SEC 2026-Q3 regression: prove 13F highlights emerge WITHOUT news."""
import thirteenf_sector_watch_entry as entry

def main():
    w=entry.watch
    cik="0001536411"
    docs=w.recent_13f(cik)
    q3=next((x for x in docs if x["report_date"]=="2026-09-30"
             and x["accession"]=="0001536411-26-000011"),None)
    q2=next((x for x in docs if x["report_date"]=="2026-06-30"
             and x["accession"]=="0001536411-26-000006"),None)
    if not q3 or not q2:
        raise RuntimeError("Q3/Q2 actual SEC 13F filing not accessible")
    current,source=w.parse_holdings(cik,q3["accession"])
    previous,_=w.parse_holdings(cik,q2["accession"])
    if len(current)<55 or len(previous)<80:
        raise RuntimeError("SEC holdings truncated: refuse false liquidation")
    # Distinguish issuer name from CUSIP/title: both can change between
    # filings, so an apparent exit+new position may be a security ID change.
    for when,positions in (("current",current),("previous",previous)):
        evidence=[(k,r["issuer"],r["title"],int(r["shares"]))
                  for k,r in positions.items()
                  if "YPF" in str(r.get("issuer") or "").upper()]
        print(f"SEC_ISSUER_IDENTITY_DIAGNOSTIC period={when} rows={evidence}")
    changes=w.classify_changes(current,previous)
    # Diagnostic: apparent exit/new pairs for the same issuer can be SEC
    # identifier or share-class changes, not independent portfolio actions.
    entrants=[x for x in changes if x["action"]=="신규 매수"]
    departures=[x for x in changes if x["action"]=="전량 청산"]
    candidate_pairs=[
        (e.get("issuer"),e.get("cusip"),e.get("title"),int(e.get("shares") or 0),
         d.get("cusip"),d.get("title"),int(d.get("shares") or 0))
        for e in entrants for d in departures
        if str(e.get("issuer") or "").strip().upper()
            ==str(d.get("issuer") or "").strip().upper()
        and str(e.get("putcall") or "").upper()==str(d.get("putcall") or "").upper()
    ]
    print(f"SEC_POTENTIAL_ID_RECLASSIFICATION_PAIRED rows={candidate_pairs}")
    # Same CUSIP, revised SEC security title: not two offsetting trades.
    ypf=[x for x in changes if "YPF" in str(x.get("issuer") or "").upper()]
    if (len(ypf)!=1 or ypf[0]["action"]!="보유 확대"
            or int(ypf[0]["delta_shares"])!=403000):
        raise AssertionError(f"YPF false new+exit from title change: {ypf}")
    old_rate,old_basis=entry.FX_RATE,entry.FX_BASIS
    try:
        entry.FX_RATE=1334.87  # historical test rate, NOT live FX
        entry.FX_BASIS="2026-11-16 기준 SEC 자동발굴 회귀 검증"
        summary=entry.build_message_with_owner(
            "Duquesne Family Office",q3,q2,changes,source,
            current_holdings=current,previous_holdings=previous)
    finally:
        entry.FX_RATE,entry.FX_BASIS=old_rate,old_basis
    # These examples must emerge from the whole SEC holdings comparison;
    # no article is read, and no output is sent to Telegram.
    for needle in (
        "스페이스X","팔란티어(PLTR)","앱러빈(APP)",
        "AMD(AMD)","샌디스크(SNDK)","알파벳 A(GOOGL)",
        "유니티(U)","시게이트(STX)","아마존(AMZN)",
        "TSMC(TSM)","나테라(NTRA)","29.2%",
        "신규 편입","신고상 보유 종료",
    ):
        if needle not in summary:
            raise AssertionError(f"Important 13F fact omitted from automatic digest: {needle}")
    if "Ypf Sociedad Anonima 신고상 종료" in summary or "Ypf Sociedad Anonima 신규" in summary:
        raise AssertionError("Same-CUSIP title change still classified as liquidation/new entry")
    if not summary.startswith("[13F 핵심 변화 자동 추출]"):
        raise AssertionError("Old sector-only template still active")
    if len(summary)>3700:
        raise AssertionError("Automatic highlights exceed one Telegram message")
    print(f"13F_AUTO_OFFICIAL_REGRESSION_PASS source=SEC filings_current={len(current)}"
          f" filings_prior={len(previous)} changes={len(changes)}"
          f" report_chars={len(summary)} article_input=false telegram_sent=false")
    print("13F_AUTO_PREVIEW_BEGIN\n"+summary+"\n13F_AUTO_PREVIEW_END")

if __name__=="__main__":
    main()
