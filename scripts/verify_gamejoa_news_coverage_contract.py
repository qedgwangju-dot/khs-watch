Warning: truncated output (original token count: 12299)
Total output lines: 951

from datetime import datetime
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import gamejoa_preopen_news_radar_full_compact_runner as radar
import gamejoa_preopen_news_radar_fda_quality_runner as quality
from khs_article_detail import extract_article_detail


CASES = (
    ("NAVER, 엔비디아 대상 1조4809억 규모 유상증자 결정", "유상증자", "수급"),
    ("SK하이닉스, 10개사와 LTA 장기공급계약 체결", "lta", "돈 버는 능력"),
    ("코스피, 2거래일 연속 매도 사이드카 발동", "사이드카", "수급"),
    ("코스닥 서킷브레이커 1단계 발동", "서킷브레이커", "수급"),
    ("구마모토 규모 7.1 강진, TSMC 공장 중단", "강진", "돈 버는 능력"),
    ("10년물 미국채 금리 4.7%, 트럼프 2기 최고", "미국채", "할인율"),
    ("삼성전기, 10개 고객과 MLCC 장기공급계약", "mlcc", "돈 버는 능력"),
    ("미국, 외국산 휴머노이드 수입 제한", "수입 제한", "할인율"),
    ("엔비디아, AI 순환금융 우려 재점화", "순환금융", "돈 버는 능력"),
    ("미국, 글로벌파운드리스에 AI 광반도체 개발비 3억달러 지원", "개발비", "돈 버는 능력"),
    ("중국 정치국, 성장 둔화 대응 정책 지원·재정 지출 약속", "정치국", "할인율"),
    ("국민연금, 국내주식 수익률 106% 기록", "국민연금", "수급"),
    ("국고채 금리, 미국 금리 여파에 동반 상승", "국고채", "할인율"),
    ("LG디스플레이, 1.5조 국민성장펀드 투자 유치", "국민성장펀드", "돈 버는 능력"),
    ("최태원 회장, SK하이닉스 주식 3620주 매수", "내부자 직접매수", "수급"),
    ("양현석 총괄 프로듀서, YG 주식 46만1940주 장내매수", "내부자 직접매수", "수급"),
    (
        "유안타증권, 단일종목 레버리지 ETF 규제 …11299 tokens truncated…     if "정전" not in str(heat_outage.get("telegram_core_fact") or ""):
            failures.append("heat_grid_outage=missing_article_fact")

    generic_heat_row = {
        "title": "서울 폭염과 열대야 이어져",
        "source_body": "서울의 낮 기온이 크게 올라 무더위가 이어졌다.",
        "published": now,
    }
    if quality.heat_grid_outage_alert(
        generic_heat_row,
        now,
        f"{generic_heat_row['title']} {generic_heat_row['source_body']}".lower(),
    ):
        failures.append("heat_grid_outage=generic_weather_not_blocked")

    shipbuilding_row = {
        "title": "HD현대, 미국 군함 조선소에 AI 용접기술 투입…한미 조선협력 본격화",
        "summary": "HD현대가 미국 군함 조선소에 AI 용접기술을 적용하는 협력을 추진한다.",
        "published": now,
    }
    shipbuilding_score, _ = radar.korean_business_detail_priority(shipbuilding_row)
    shipbuilding_text = f"{shipbuilding_row['title']} {shipbuilding_row['summary']}".lower()
    shipbuilding_material = [
        term
        for term in radar.KOREAN_BUSINESS_MATERIAL_TERMS
        if radar.korean_business_title_has_material_term(shipbuilding_text, term)
    ]
    shipbuilding_impacts = radar.korean_business_impacts(shipbuilding_text, [])
    if shipbuilding_score < 10:
        failures.append(f"shipbuilding_ai_welding=priority:{shipbuilding_score}")
    if "ai 용접" not in shipbuilding_material:
        failures.append(f"shipbuilding_ai_welding=material:{shipbuilding_material}")
    if not shipbuilding_impacts:
        failures.append(f"shipbuilding_ai_welding=missing_impact:{shipbuilding_impacts}")

    if failures:
        print("GAMEJOA news coverage contract failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"GAMEJOA news coverage contract OK: cases={len(CASES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

