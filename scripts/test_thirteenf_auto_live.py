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
    changes=w.classify_changes(current,previous)
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
