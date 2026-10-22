#!/usr/bin/env python3
"""Meta Q3 earnings cash-flow, one-off charge, Class C and event dedupe tests."""
import meta_earnings_muse_cashflow_watch as m

def main():
    v=m.Q3_MILLIONS
    assert v["cash_from_ops"]-v["ppe"]-v["finance_lease"]==v["free_cash_flow"]==-2120
    assert v["op_income"]+v["legal_charge"]==22878
    assert v["capex_q3"]==34906
    assert v["q4_low"]==73000 and v["q4_high"]==76000
    assert v["fy_capex_low"]==135000 and v["fy_capex_high"]==145000
    msg=m.build_q3(1322.54,"2026-10-22","메타 공식 투자자관계")
    assert "메타(META) 2026년 3분기" in msg
    assert "646억100만달러(약 " in msg
    assert "-21억2,000만달러(약 -2.80조원)" in msg
    assert "일회성" in msg and "비의결권" in msg
    assert "2027년 1월 19일" in msg
    assert "2026년 연간 설비투자" in msg
    assert "<a href=" in msg
    enriched=m.build_q3(1322.54,"2026-10-22","메타 공식 투자자관계",enrichment=True)
    assert "검산 보강본" in enriched
    assert "새 분기 발표 아님" in enriched
    assert "광고 노출 +10%" in enriched and "광고당 평균가격 +14%" in enriched
    assert "전년 동기 대비 약 +11.4%" in enriched
    assert m.Q3_MILLIONS["forecast_fcf"]-m.Q3_MILLIONS["free_cash_flow"]==-6400
    assert m.Q3_MILLIONS["forecast_capex_q3"]-m.Q3_MILLIONS["capex_q3"]==6774
    assert "실제 유출은 지속" in enriched
    assert "실제 투자 집행 이연 여부는 확인되지 않았습니다." in enriched
    assert "FCF" not in enriched or "잉여현금흐름" in enriched

    print("Meta financial statements and event regression checks passed.")

if __name__=="__main__":
    main()
