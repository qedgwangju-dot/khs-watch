#!/usr/bin/env python3
"""Regression gate for cross-market and next-generation semiconductor coverage."""

from datetime import datetime, timezone
from pathlib import Path
import sys

# Prefer the runner checked into this scripts directory over any same-named
# module in the caller's working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import gamejoa_preopen_news_radar_full_compact_runner as radar


SEARCH_NAMES = {
    "미국장 빅테크 실적·한국 ADR·반도체 수급",
    "HBM5·zHBM·HBF 차세대 메모리 기술·상용화",
    "메모리 장기공급·수요전망·고객 사양 변경",
    "삼성 파운드리 가동률·풀캐파·공정 주문",
    "핵심 원자재 사상최고·공급차질",
    "레버리지 규제 후 거래대금·자금이동",
    "SK하이닉스 해외 HBM 생산거점",
    "엔비디아 AI 서버 가격·메모리 공급부족",
    "YMTC 낸드 IPO·중국 메모리 공급",
    "앤트로픽 IPO·AI 인프라 자금",
    "삼성·SK HBM 핫칩스·기술공개",
    "빅테크 AI 회사채·미국 국채금리",
    "미국·캐나다 무역협정·관세",
    "이란·중국 원유·브렌트",
    "삼성 TV 출하·메모리 원가",
    "반도체 노조·성과급·가동 리스크",
    "트럼프 자산공시·대형 주식거래",
    "미국 쇠고기 관세·통상",
    "중동 경제전·원유·해운 리스크",
    "러시아·우크라이나 경제목표·에너지·물류",
    "AGI·HBM 첨단패키징 병목",
    "삼성 엑시노스·2나노·퀄컴 성능",
    "엔비디아 실적·잭슨홀 일정",
    "미 재정적자·장기국채 금리",
    "고배당·커버드콜 ETF 순매수",
    "엔비디아·삼성 파운드리 추론칩 양산",
    "AI 반도체·퇴직연금 ETF 신규 상장",
    "중국 휴머노이드 로봇·대규모 투자",
    "SK하이닉스 HBM 열관리·하이브리드 본딩",
    "AI·반도체 슈퍼예산·재정지원",
    "CXMT·SMIC 메모리 자립·공급",
    "엔비디아 베라루빈·총마진·양산",
    "삼성 PIM·AI PC 상용화",
    "엔비디아·앰코 첨단패키징 장기계약",
    "삼성·SK 레버리지 ETF 자금유출",
    "AI MLCC 공급부족·리드타임",
    "오픈AI·브로드컴 자체 AI칩·HBM",
    "SK하이닉스·인텔 EMIB·HBM 패키징",
    "AI 반도체 절연필름·기판 공급병목",
    "아마존·엔비디아 GPU 대형도입",
    "엔비디아 메모리·생산능력 구매약정",
    "CATL 리튬광산 재가동·환경평가",
    "엔비디아 NVHBM·아마존 협력",
    "엔비디아 루빈·베라 HBM4·LPDDR5X 메모리 공급",
    "이란 전쟁·중국·OPEC+ 원유시장 영향",
    "트럼프 관세·미국 데이터센터 CAPEX",
    "SK하이닉스 미국 HBM 첨단패키징 투자",
    "키옥시아 이와테 낸드 공장 CAPEX",
    "트럼프 H-1B 비자 수수료 정책",
    "반도체 소재·패키징·황산 증설",
    "ESS 규제·NXT 거래제도",
    "중국 메모리 생산능력·LPDDR6",
    "미국 반도체 관세·내장제품",
    "삼성·SK 주주환원·자사주",
    "신용융자·삼성·SK 수급",
    "한국 로보택시·ESS 합작법인",
    "미국·베네수엘라 원유협정",
}

CASES = (
    (
        "뉴욕증시, 아마존 실적 훈풍…SK하이닉스 ADR 3.5% 하락",
        "adr",
        {"돈 버는 능력", "수급"},
    ),
    (
        "삼성전자, HBM5보다 8배 빠른 zHBM 공개",
        "zhbm",
        {"돈 버는 능력", "시간표"},
    ),
    (
        "삼성 파운드리 4나노 풀캐파·5나노 주문 증가",
        "풀캐파",
        {"돈 버는 능력", "시간표"},
    ),
    (
        "구리값 사상 최고…광산 사고로 공급난 가중",
        "공급난",
        {"돈 버는 능력", "시간표"},
    ),
    (
        "삼전닉스 레버리지 규제 후 코스피200으로 자금 이동",
        "자금 이동",
        {"수급", "시간표"},
    ),
)

# The 2026-08-22 attachment had 35 source articles. Duplicated wire stories are
# retained in the source count, while operational coverage is decided per theme.
ATTACHMENT_20260822_GROUPS = {
    "iran_china_trade_policy": {"source_items": 1, "route": "policy"},
    "iran_china_oil_trade": {"source_items": 1, "route": "send"},
    "us_equity_market_recap": {"source_items": 1, "route": "conditional"},
    "samsung_labor_compensation": {"source_items": 1, "route": "conditional"},
    "skhynix_overseas_hbm_production": {"source_items": 1, "route": "send"},
    "samsung_tv_memory_cost_share": {"source_items": 1, "route": "send"},
    "trump_asset_trade_disclosure": {"source_items": 8, "route": "policy"},
    "skhynix_stock_split_commentary": {"source_items": 1, "route": "exclude"},
    "ymtc_nand_ipo": {"source_items": 1, "route": "send"},
    "us_canada_tariff_trade": {"source_items": 4, "route": "send"},
    "anthropic_ipo_ai_infrastructure": {"source_items": 2, "route": "send"},
    "samsung_skhynix_hbm_hotchips": {"source_items": 1, "route": "send"},
    "us_beef_tariff_policy": {"source_items": 3, "route": "policy"},
    "samsung_social_support": {"source_items": 1, "route": "exclude"},
    "nvidia_ai_server_memory_price": {"source_items": 1, "route": "send"},
    "high_yield_stock_recommendation": {"source_items": 1, "route": "exclude"},
    "samsung_skhynix_fcf_returns": {"source_items": 1, "route": "send"},
    "skhynix_return_leverage_etf": {"source_items": 1, "route": "send"},
    "korea_etf_asset_valuation": {"source_items": 1, "route": "send"},
    "bigtech_ai_credit_yield": {"source_items": 1, "route": "send"},
    "us_apec_china_policy": {"source_items": 1, "route": "policy"},
    "us_midterm_seasonality": {"source_items": 1, "route": "exclude"},
}

ATTACHMENT_ALERT_CASES = (
    (
        "트럼프, 이란의 최대 무역 상대국 중국에 경제적 D-Day 경고",
        "이란의 최대 무역 상대국 중국을 겨냥해 트럼프가 경제적 D-Day를 예고했습니다.",
        "iran_china_trade_policy",
        "이란",
    ),
    (
        "이란 휴전 기대 후퇴에 중국 원유 수입 차질·브렌트 상승",
        "이란 휴전 기대가 후퇴하며 중국 원유 수입 차질 우려와 브렌트 상승이 나왔습니다.",
        "iran_china_oil_trade",
        "이란",
    ),
    (
        "SK하이닉스, 일본 반도체 공장 건설 검토",
        "SK하이닉스가 HBM 생산 확대를 위해 일본 반도체 공장 건설을 검토합니다.",
        "skhynix_overseas_hbm_production",
        "SK하이닉스",
    ),
    (
        "삼성전자 TV 출하 1위…미니 LED 확대와 메모리 원가 부담",
        "삼성전자가 TV 출하량 1위를 지켰지만 미니 LED 확대와 메모리 가격 상승이 원가를 압박합니다.",
        "samsung_tv_memory_cost_share",
        "삼성전자",
    ),
    (
        "삼성전자 노조, 성과급·임단협 재협상 요구",
        "삼성전자 노조가 성과급과 임단협 재협상을 요구해 반도체 가동 리스크가 커졌습니다.",
        "samsung_labor_compensation_risk",
        "삼성전자",
    ),
    (
        "YMTC, 낸드 생산 확대 위한 IPO 추진",
        "YMTC가 낸드와 SSD 생산 확대 자금을 조달하기 위해 IPO를 추진합니다.",
        "ymtc_nand_ipo",
        "YMTC",
    ),
    (
        "미국·캐나다 무역협정 결렬, 관세 50% 보복 우려",
        "미국과 캐나다의 무역협정이 결렬돼 관세 50%와 북미 공급망 불확실성이 커졌습니다.",
        "us_canada_tariff_trade",
        "캐나다",
    ),
    (
        "앤트로픽, AI 데이터센터 투자 확대 앞두고 IPO 검토",
        "앤트로픽이 AI 데이터센터 투자 확대를 위해 기업가치 산정과 IPO를 검토합니다.",
        "anthropic_ipo_ai_infrastructure",
        "앤트로픽",
    ),
    (
        "삼성전자·SK하이닉스, 핫칩스에서 HBM 기술 공개",
        "삼성전자와 SK하이닉스가 핫칩스에서 HBM 기술을 공개하고 고객 인증 일정을 제시합니다.",
        "samsung_skhynix_hbm_hotchips",
        "HBM",
    ),
    (
        "엔비디아, 메모리 부족에 AI 서버 가격 15% 인상",
        "엔비디아가 메모리 부족으로 AI 서버 가격을 15% 인상하겠다고 고객사에 통보했습니다.",
        "nvidia_ai_server_memory_price",
        "엔비디아",
    ),
    (
        "빅테크 AI 투자 확대에 회사채 발행·미국 국채 금리 상승",
        "빅테크의 AI 데이터센터 투자 확대가 회사채 발행과 미국 국채 금리 상승으로 이어졌습니다.",
        "bigtech_ai_credit_yield",
        "빅테크",
    ),
    (
        "APEC 앞두고 미국 우선주의 의제와 중국 정상회담 주목",
        "APEC에서 미국 우선주의 의제와 중국 정상회담이 수출통제 위험을 바꿀 수 있습니다.",
        "us_apec_china_policy",
        "APEC",
    ),
    (
        "트럼프, 미국산 쇠고기 관세 철폐 검토",
        "트럼프 행정부가 미국산 쇠고기 수입 관세 철폐와 통상 협상을 검토합니다.",
        "us_beef_tariff_policy",
        "쇠고기",
    ),
    (
        "트럼프 자산공시, 대형 주식 거래 내역 공개",
        "트럼프 자산공시에 투자계좌와 대형 주식 거래 내역이 공개됐습니다.",
        "trump_asset_trade_disclosure",
        "트럼프",
    ),
    (
        "국내 ETF 순자산 두 달 새 60조원 감소",
        "국내 주식형 ETF 순자산이 기초자산 가격 하락과 레버리지 규제 영향으로 두 달 새 60조원 감소했습니다.",
        "korea_etf_asset_flow",
        "60조원 감소",
    ),
)


ATTACHMENT_20260823_GROUPS = {
    "iran_economic_war_trade_risk": {"source_items": 1, "route": "policy"},
    "russia_ukraine_economic_targets": {"source_items": 1, "route": "conditional"},
    "agi_advanced_packaging_hbm_bottleneck": {"source_items": 1, "route": "send"},
    "active_covered_call_etf_net_buy": {"source_items": 1, "route": "send"},
    "samsung_exynos_2nm_performance": {"source_items": 1, "route": "send"},
    "nvidia_earnings_jackson_hole_calendar": {"source_items": 1, "route": "send"},
    "nvidia_ai_server_memory_price": {"source_items": 1, "route": "send"},
    "us_fiscal_deficit_treasury_yield": {"source_items": 1, "route": "send"},
}

ATTACHMENT_20260823_ALERT_CASES = (
    (
        "테헤란, 미국 경제 전쟁 무력화 다짐",
        "테헤란은 미국의 경제 전쟁을 무력화하겠다고 다짐하며 제재와 원유 수출 불확실성이 이어졌습니다.",
        "iran_economic_war_trade_risk",
        "테헤란",
    ),
    (
        "푸틴, 우크라이나 경제적 목표물 공격은 판도라의 상자",
        "푸틴은 우크라이나 경제적 목표물 공격이 판도라의 상자를 열었다고 말해 에너지·물류 위험을 경고했습니다.",
        "russia_ukraine_economic_targets",
        "푸틴",
    ),
    (
        "반도체 패키징이 AGI 성패 좌우…HBM 병목 심화",
        "AGI 연산 확대에 반도체 패키징과 HBM 병목이 심해지면 한국 공급망에 기회가 커질 수 있습니다.",
        "agi_advanced_packaging_hbm_bottleneck",
        "AGI",
    ),
    (
        "ACE 고배당주PLUS커버드콜액티브 순매수 1천억 돌파",
        "ACE 고배당주PLUS커버드콜액티브 ETF 순매수가 1천억원을 돌파했습니다.",
        "active_covered_call_etf_net_buy",
        "ACE",
    ),
    (
        "삼성 엑시노스 사내 테스트서 퀄컴칩 압도",
        "엑시노스가 사내 테스트에서 퀄컴칩을 앞섰고 삼성 2나노 공정 적용 가능성이 거론됐습니다.",
        "samsung_exynos_2nm_performance",
        "엑시노스",
    ),
    (
        "엔비디아 실적 발표와 잭슨홀 미팅에 주목",
        "엔비디아 실적 발표와 잭슨홀 회의가 AI 투자심리와 금리 경로를 가를 일정으로 주목됩니다.",
        "nvidia_earnings_jackson_hole_calendar",
        "엔비디아",
    ),
    (
        "엔비디아도 메모리 부족에 AI 서버 가격 15% 인상",
        "엔비디아가 메모리 부족으로 AI 서버 가격을 15% 인상하겠다고 고객사에 통보했습니다.",
        "nvidia_ai_server_memory_price",
        "엔비디아",
    ),
    (
        "미국 재정적자 40조달러, 장기 국채 금리 상승 경고",
        "미국 재정적자가 40조달러로 늘면서 30년물 국채 금리 상승과 달러 경로가 경고 요인으로 지목됐습니다.",
        "us_fiscal_deficit_treasury_yield",
        "미국",
    ),
)



# The 2026-08-25/26 attachment had 38 source articles. Duplicate coverage is
# retained in this ledger; delivery is deduplicated by the canonical event key.
ATTACHMENT_20260826_GROUPS = {
    "nvidia_samsung_foundry_inference_mass_production": {"source_items": 4, "route": "send"},
    "samsung_skhynix_bond_mixed_etf_performance": {"source_items": 1, "route": "conditional"},
    "samsung_skhynix_ir_price_recap": {"source_items": 1, "route": "conditional"},
    "trump_spacex_personal_investment": {"source_items": 1, "route": "conditional"},
    "bok_rate_survey": {"source_items": 1, "route": "conditional"},
    "nvidia_earnings_jackson_hole_calendar": {"source_items": 3, "route": "send"},
    "korea_ai_semiconductor_etf_listing": {"source_items": 1, "route": "send"},
    "china_humanoid_robot_funding": {"source_items": 1, "route": "send"},
    "index_etf_product_launch": {"source_items": 1, "route": "conditional"},
    "skhynix_advanced_memory_thermal_packaging": {"source_items": 3, "route": "send"},
    "korea_ai_semiconductor_budget": {"source_items": 1, "route": "policy"},
    "china_semiconductor_general_commentary": {"source_items": 1, "route": "exclude"},
    "nvidia_rubin_margin_ramp": {"source_items": 1, "route": "send"},
    "china_memory_self_sufficiency_forecast": {"source_items": 2, "route": "send"},
    "wealthy_investor_portfolio_commentary": {"source_items": 1, "route": "exclude"},
    "ai_memory_revenue_growth_outlook": {"source_items": 1, "route": "send"},
    "korea_single_stock_leverage_etf_volatility": {"source_items": 1, "route": "send"},
    "china_listed_company_tax_recovery": {"source_items": 1, "route": "conditional"},
    "global_hbm_etf_performance": {"source_items": 3, "route": "exclude"},
    "us_market_nvidia_yield_recap": {"source_items": 1, "route": "conditional"},
    "samsung_pim_ai_pc_commercialization": {"source_items": 2, "route": "send"},
    "nvidia_amkor_advanced_packaging_contract": {"source_items": 1, "route": "send"},
    "lgchem_semiconductor_material_showcase": {"source_items": 1, "route": "conditional"},
    "samsung_skhynix_leveraged_etf_outflow": {"source_items": 1, "route": "send"},
    "samsung_hbm4_expo_photo": {"source_items": 1, "route": "exclude"},
    "ai_mlcc_supply_bottleneck": {"source_items": 1, "route": "conditional"},
    "group_etf_rotation": {"source_items": 1, "route": "exclude"},
}

ATTACHMENT_20260826_ALERT_CASES = (
    (
        "엔비디아, 삼성 파운드리에 그록3 LPX 추론가속기 양산 위탁",
        "엔비디아가 삼성전자 파운드리에 그록3 LPX 추론가속기 양산을 맡겼다고 보도됐습니다.",
        "nvidia_samsung_foundry_inference_mass_production",
        "그록3",
    ),
    (
        "삼성전자·SK하이닉스·삼성전기 담은 퇴직연금 AI반도체 ETF 상장",
        "삼성전자와 SK하이닉스, 삼성전기를 담은 퇴직연금 AI반도체 ETF가 상장됩니다.",
        "korea_ai_semiconductor_etf_listing",
        "퇴직연금",
    ),
    (
        "샤오펑 로봇 자회사 도고틱스, 신주 발행으로 9억달러 자금조달",
        "도고틱스가 휴머노이드 로봇 개발을 위해 신주 발행으로 9억달러 자금을 조달합니다.",
        "china_humanoid_robot_funding",
        "도고틱스",
    ),
    (
        "SK하이닉스, HBM 열관리 위해 하이브리드 본딩·I-HBM·EMIB 활용",
        "SK하이닉스가 HBM 열 문제 대응으로 하이브리드 본딩과 I-HBM, 인텔 EMIB 활용을 제시했습니다.",
        "skhynix_advanced_memory_thermal_packaging",
        "하이브리드 본딩",
    ),
    (
        "정부, AI·반도체 경쟁력 위해 800조원대 슈퍼예산 편성 추진",
        "정부가 AI와 반도체 경쟁력 강화를 위해 800조원대 슈퍼예산 편성을 추진한다고 보도됐습니다.",
        "korea_ai_semiconductor_budget",
        "800조원대",
    ),
    (
        "골드만삭스, CXMT 2028년 중국 D램·HBM 수요 상당 부분 충족 전망",
        "골드만삭스는 CXMT가 2028년 중국 D램과 HBM 수요의 상당 부분을 충족할 수 있다고 전망했습니다.",
        "china_memory_self_sufficiency_forecast",
        "CXMT",
    ),
    (
        "엔비디아 베라루빈 양산 속도·75% 마진 유지 주목",
        "엔비디아 베라루빈의 양산 속도와 75% 마진 유지, HBM 수요가 투자심리의 핵심 변수입니다.",
        "nvidia_rubin_margin_ramp",
        "베라루빈",
    ),
    (
        "AI 데이터센터 투자로 삼성전자·SK하이닉스 메모리 매출 280% 급증 전망",
        "AI 데이터센터 투자 확대로 삼성전자와 SK하이닉스의 HBM·D램 메모리 매출이 280% 급증할 수 있다는 전망이 나왔습니다.",
        "ai_memory_revenue_growth_outlook",
        "280%",
    ),
    (
        "삼성전자·SK하이닉스 단일종목 2배 ETF가 증시 변동성 확대",
        "삼성전자와 SK하이닉스 단일종목 2배 ETF의 거래량과 변동성이 확대됐다는 분석이 나왔습니다.",
        "korea_single_stock_leverage_etf_volatility",
        "2배 ETF",
    ),
    (
        "삼성전자, 가이아 AI PC에 LPDDR5X-PIM 탑재해 PIM 상용화",
        "삼성전자가 가이아 AI PC에 LPDDR5X-PIM을 탑재해 PIM 상용화를 추진한다고 밝혔습니다.",
        "samsung_pim_ai_pc_commercialization",
        "LPDDR5X-PIM",
    ),
    (
        "엔비디아, 앰코와 15억달러 첨단패키징 장기계약·선급금 제공",
        "엔비디아가 앰코와 15억달러 첨단패키징 장기계약을 맺고 선급금을 제공했다는 보도가 나왔습니다.",
        "nvidia_amkor_advanced_packaging_contract",
        "앰코",
    ),
    (
        "삼성전자·SK하이닉스 연계 레버리지 ETF에서 10억달러 순유출",
        "삼성전자와 SK하이닉스 연계 레버리지 ETF에서 10억달러가 빠져나갔다고 보도됐습니다.",
        "samsung_skhynix_leveraged_etf_outflow",
        "10억달러",
    ),
)


# The 2026-08-26/27 attachment had 49 source articles. Repeated collection
# rows remain visible here; canonical event keys, not the collection count,
# decide Telegram delivery.
ATTACHMENT_20260827_GROUPS = {
    "us_h1b_visa_fee_proposal": {"source_items": 3, "route": "policy"},
    "samsung_labor_separate_bargaining": {"source_items": 3, "route": "conditional"},
    "korea_single_stock_leverage_etf_volume_drop": {"source_items": 3, "route": "send"},
    "openai_broadcom_jalapeno_inference_chip": {"source_items": 4, "route": "send"},
    "china_ai_price_war_short_interest": {"source_items": 2, "route": "conditional"},
    "skhynix_emib_hbm_2p5d_packaging": {"source_items": 2, "route": "send"},
    "nvidia_earnings_hbm_calendar": {"source_items": 1, "route": "send"},
    "china_dram_self_supply_outlook": {"source_items": 1, "route": "send"},
    "samsung_group_dividend_expectation": {"source_items": 1, "route": "conditional"},
    "retail_nvidia_portfolio_story": {"source_items": 1, "route": "exclude"},
    "ymtc_nand_top_share_target": {"source_items": 1, "route": "conditional"},
    "korea_japan_wealth_management_app": {"source_items": 1, "route": "conditional"},
    "mirae_toss_japan_brokerage_mna": {"source_items": 1, "route": "conditional"},
    "x_client_shutdown": {"source_items": 1, "route": "exclude"},
    "ai_memory_revenue_structural_shift": {"source_items": 1, "route": "send"},
    "ai_semiconductor_insulation_film_bottleneck": {"source_items": 1, "route": "send"},
    "cxmt_ipo_valuation_supply_challenge": {"source_items": 1, "route": "send"},
    "us_debt_limit_treasury_bond_risk": {"source_items": 1, "route": "policy"},
    "bill_gates_xi_ai_commentary": {"source_items": 1, "route": "exclude"},
    "canada_us_retaliatory_tariff": {"source_items": 1, "route": "policy"},
    "samsung_electro_mlcc_lta": {"source_items": 1, "route": "send"},
    "korea_bok_rate_decision": {"source_items": 3, "route": "policy"},
    "amazon_nvidia_gpu_2m_capex": {"source_items": 1, "route": "send"},
    "us_pce_ndf_rate_shift": {"source_items": 1, "route": "send"},
    "nvidia_earnings_actual": {"source_items": 2, "route": "send"},
    "nvidia_memory_purchase_commitments": {"source_items": 1, "route": "send"},
    "trump_iran_sanction_oil_comment": {"source_items": 1, "route": "policy"},
    "catl_lithium_mine_restart_halted": {"source_items": 1, "route": "send"},
    "nvidia_nvhbm_amazon_collaboration": {"source_items": 1, "route": "send"},
    "skhynix_us_hbm_advanced_packaging_capex": {"source_items": 2, "route": "send"},
    "iran_china_sanctions_policy": {"source_items": 2, "route": "policy"},
    "hanwha_sp500_etf_fee_cut": {"source_items": 1, "route": "conditional"},
    "kioxia_iwate_nand_factory_capex": {"source_items": 1, "route": "send"},
}

ATTACHMENT_20260827_ALERT_CASES = (
    (
        "트럼프 행정부, H-1B 비자 수수료 인상안 제안",
        "트럼프 행정부가 H-1B 전문직 비자에 수수료를 부과하는 방안을 제안했습니다.",
        "us_h1b_visa_fee_proposal",
        "H-1B",
    ),
    (
        "삼성전자·SK하이닉스 단일종목 레버리지 ETF 거래대금 91% 급감",
        "삼성전자와 SK하이닉스 단일종목 레버리지 ETF 거래대금이 한 달 만에 91% 급감했습니다.",
        "korea_single_stock_leverage_etf_volume_drop",
        "91% 감소",
    ),
    (
        "오픈AI, 브로드컴과 자체 AI칩 할라페뇨 연내 가동",
        "오픈AI가 브로드컴과 개발한 자체 AI칩 할라페뇨를 연내 추론 서비스 운영에 투입합니다.",
        "openai_broadcom_jalapeno_inference_chip",
        "할라페뇨",
    ),
    (
        "SK하이닉스, 인텔 EMIB 기반 2.5D HBM 패키징 다변화",
        "SK하이닉스가 인텔 EMIB가 적용된 기판으로 HBM과 시스템 반도체를 결합하는 2.5D 패키징을 모색합니다.",
        "skhynix_emib_hbm_2p5d_packaging",
        "EMIB",
    ),
    (
        "AI칩 새 병목 절연필름…패키지기판 생산량 감소",
        "AI칩 대형화로 패키지기판 절연필름 수요가 늘어 공급부족과 기판 생산 병목이 커지고 있습니다.",
        "ai_semiconductor_insulation_film_bottleneck",
        "절연필름",
    ),
    (
        "삼성전기, 빅테크·반도체 고객 10여곳과 MLCC LTA 진행",
        "삼성전기가 빅테크와 주요 반도체 고객 10여곳을 상대로 고부가 MLCC 장기공급 협의를 진행 중입니다.",
        "samsung_electro_mlcc_lta",
        "MLCC",
    ),
    (
        "아마존, 엔비디아 GPU 200만개 추가 도입",
        "AWS가 AI 수요 대응을 위해 엔비디아 GPU 200만개를 추가 확보하기로 했습니다.",
        "amazon_nvidia_gpu_2m_capex",
        "200만개",
    ),
    (
        "미국 PCE 예상 상회에 원·달러 NDF 상승",
        "미국 7월 PCE가 예상을 상회하며 원·달러 NDF와 연준 금리 인상 기대가 높아졌습니다.",
        "us_pce_ndf_rate_shift",
        "PCE",
    ),
    (
        "엔비디아, 15분기 연속 월가 예상 상회",
        "엔비디아가 15분기 연속 월가 예상을 웃도는 깜짝 실적을 발표했습니다.",
        "nvidia_earnings_actual",
        "15분기",
    ),
    (
        "엔비디아, 메모리·생산능력 구매약정 2790억달러",
        "엔비디아의 메모리와 생산능력 구매약정이 2790억달러로 석 달 새 134% 늘었습니다.",
        "nvidia_memory_purchase_commitments",
        "2790억달러",
    ),
    (
        "CATL 리튬광산 재가동 절차, 환경영향평가 공시 철회로 중단",
        "CATL 핵심 리튬광산 재가동 절차가 환경영향평가 EIA 공시 철회로 중단됐습니다.",
        "catl_lithium_mine_restart_halted",
        "CATL",
    ),
    (
        "엔비디아, NVHBM 공개하고 아마존과 공동 개발",
        "엔비디아가 맞춤형 HBM 기술 NVHBM을 공개하고 아마존과 공동 개발을 추진합니다.",
        "nvidia_nvhbm_amazon_collaboration",
        "NVHBM",
    ),
    (
        "SK하이닉스, 웨스트라피엣 HBM 첨단패키징 생산시설 투자",
        "SK하이닉스가 미국 웨스트라피엣에 AI용 HBM 첨단패키징 생산시설을 구축하기로 했습니다.",
        "skhynix_us_hbm_advanced_packaging_capex",
        "웨스트라피엣",
    ),
    (
        "한국은행, 물가·환율 반영해 기준금리 인상",
        "한국은행이 물가와 원·달러 환율을 고려해 기준금리를 인상했습니다.",
        "korea_bok_rate_policy_event",
        "한국은행",
    ),
    (
        "이란 제재 강화에 중국 보복 경고",
        "미국의 이란 제재 강화에 중국이 보복을 공언하며 원유와 해운 위험이 커졌습니다.",
        "iran_china_sanctions_policy",
        "이란",
    ),
    (
        "키옥시아, 이와테 낸드 공장 투자 추진",
        "키옥시아가 일본 이와테에 낸드 생산능력을 늘리기 위한 공장 투자를 추진합니다.",
        "kioxia_iwate_nand_factory_capex",
        "키옥시아",
    ),
)


ATTACHMENT_20260827_EVENING_GROUPS = {
    "nvidia_hbm4_rubin_vera_memory_shortage": {"source_items": 2, "route": "send"},
    "nvidia_nvhbm_amazon_collaboration": {"source_items": 3, "route": "send"},
    "iran_opec_china_oil_market_shift": {"source_items": 1, "route": "conditional"},
    "us_datacenter_tariff_cost_pressure": {"source_items": 1, "route": "conditional"},
}

ATTACHMENT_20260827_EVENING_ALERT_CASES = (
    (
        "엔비디아 메모리 부족에 HBM4·LPDDR5X 수요 확대",
        "엔비디아 루빈 GPU와 베라 CPU의 HBM4·LPDDR5X 수요가 메모리 부족 우려로 부각됐고 삼성전자와 SK하이닉스가 핵심 공급사입니다.",
        "nvidia_hbm4_rubin_vera_memory_shortage",
        "HBM4·LPDDR5X",
        "News1",
    ),
    (
        "엔비디아, 맞춤형 HBM 기술 NVHBM 공개",
        "엔비디아가 NVHBM을 공개하고 아마존 안나푸르나랩과 공동 개발을 추진합니다.",
        "nvidia_nvhbm_amazon_collaboration",
        "NVHBM",
        "매일경제",
    ),
    (
        "이란 전쟁으로 중국 영향력 커져 OPEC+ 지배력 약화",
        "이란 전쟁 장기화로 중국의 원유 조달 영향력이 커지고 OPEC+의 석유 시장 가격 조절력이 약화됐다고 Reuters가 보도했습니다.",
        "iran_opec_china_oil_market_shift",
        "OPEC+",
        "Reuters",
    ),
    (
        "트럼프 관세, 미국 데이터센터 비용 압박",
        "트럼프 관세가 수입 장비와 건설비를 높여 미국 데이터센터 CAPEX를 압박할 수 있다고 Reuters가 보도했습니다.",
        "us_datacenter_tariff_cost_pressure",
        "데이터센터",
        "Reuters",
    ),
)


# The 2026-08-27 through 2026-08-30 attachment contained 93 raw article
# entries. Every raw index is retained here, including repeated wire stories;
# only the canonical theme is eligible for one Telegram delivery.
ATTACHMENT_20260827_30_FULL_GROUPS = {
    "nvidia_ai_hbm_demand_outlook": {
        "source_indexes": (1, 3, 16, 53),
        "route": "send",
        "reason": "AI 수요·메모리 공급과 한국 메모리 실적 연결",
    },
    "iran_opec_china_oil_market_shift": {
        "source_indexes": (2,),
        "route": "conditional",
        "reason": "신뢰외신 원문·실제 공급정책 확인 전",
    },
    "nvidia_nvhbm_amazon_collaboration": {
        "source_indexes": (4, 5, 7),
        "route": "send",
        "reason": "맞춤형 HBM 공개와 고객 협력의 동일 사건",
    },
    "us_datacenter_tariff_cost_pressure": {
        "source_indexes": (6,),
        "route": "conditional",
        "reason": "관세 적용범위·공식 시행문서 확인 전",
    },
    "russia_film_entertainment": {
        "source_indexes": (8,),
        "route": "exclude",
        "reason": "시장·기업 현금흐름과 직접 연결되지 않음",
    },
    "trump_social_media_commentary": {
        "source_indexes": (9,),
        "route": "exclude",
        "reason": "정책·가격 변수 없는 정치·SNS 해설",
    },
    "russia_ukraine_infrastructure_escalation": {
        "source_indexes": (10,),
        "route": "conditional",
        "reason": "에너지·물류 시설 피해의 신뢰원문 교차확인 필요",
    },
    "iran_us_navy_deployment": {
        "source_indexes": (11,),
        "route": "conditional",
        "reason": "군사배치 보도만으로 경제효과 확정 불가",
    },
    "ukraine_starlink_military_request": {
        "source_indexes": (12,),
        "route": "conditional",
        "reason": "승인·계약·사용범위가 확인돼야 수급 연결",
    },
    "iran_china_sanctions_policy": {
        "source_indexes": (13,),
        "route": "policy",
        "reason": "대이란 제재와 중국 대응은 정책 워치 대상",
    },
    "musk_wisconsin_legal": {
        "source_indexes": (14,),
        "route": "exclude",
        "reason": "상장사 실적·정책 변수와 직접 연결되지 않음",
    },
    "market_preview_mixed_headlines": {
        "source_indexes": (15,),
        "route": "exclude",
        "reason": "여러 기사 예고를 한 건으로 검증할 수 없음",
    },
    "us_china_trade_truce_calendar": {
        "source_indexes": (17,),
        "route": "policy",
        "reason": "미·중 통상 일정과 수출통제 정책 변수",
    },
    "iran_ceasefire_oil_price_move": {
        "source_indexes": (18,),
        "route": "send",
        "reason": "휴전 조건과 유가의 즉시 시장 반응",
    },
    "skhynix_us_hbm_advanced_packaging_capex": {
        "source_indexes": (19, 21, 24, 28, 30, 34, 36, 68),
        "route": "send",
        "reason": "미국 HBM 공장·착공·양산 일정의 중복 보도",
    },
    "hbm_glass_carrier_yield_inspection": {
        "source_indexes": (20,),
        "route": "send",
        "reason": "HBM 수율과 검사 생산성에 직접 연결",
    },
    "samsung_china_semiconductor_localization_research": {
        "source_indexes": (22, 25),
        "route": "conditional",
        "reason": "증권사 전망은 원문·수치 확인 후 송출",
    },
    "sp500_etf_fee_cut": {
        "source_indexes": (23, 26),
        "route": "conditional",
        "reason": "보수 인하만으로 실제 자금유입 확정 불가",
    },
    "consumer_experience_award": {
        "source_indexes": (27,),
        "route": "exclude",
        "reason": "고객만족도 수상은 즉시 이익·수급 변화가 아님",
    },
    "us_fiscal_debt_policy_commentary": {
        "source_indexes": (29,),
        "route": "conditional",
        "reason": "부채 해설은 국채금리·공식 조달계획 확인 필요",
    },
    "space_datacenter_speculation": {
        "source_indexes": (31,),
        "route": "conditional",
        "reason": "궤도 데이터센터는 공식 발주·CAPEX 전 확인 필요",
    },
    "samsung_skhynix_shareholder_return_program": {
        "source_indexes": (32,),
        "route": "send",
        "reason": "대규모 자사주 매입·소각은 유통주식·수급 변수",
    },
    "korea_ess_regulatory_improvement": {
        "source_indexes": (33,),
        "route": "send",
        "reason": "ESS 분류·이격거리 규정은 프로젝트 시간표 변수",
    },
    "tsmc_foundry_share_gap": {
        "source_indexes": (35, 37),
        "route": "send",
        "reason": "분기 파운드리 점유율은 경쟁구도 데이터",
    },
    "korea_zinc_semiconductor_sulfuric_acid_capacity": {
        "source_indexes": (38,),
        "route": "send",
        "reason": "반도체 소재 생산능력 증설과 매출 기반",
    },
    "samsung_skhynix_hbm_packaging_roadmap": {
        "source_indexes": (39,),
        "route": "send",
        "reason": "차세대 HBM 패키징 기술 경쟁",
    },
    "nxt_premarket_microstructure_rule": {
        "source_indexes": (40,),
        "route": "send",
        "reason": "프리마켓 가격발견·거래규칙 변경",
    },
    "honam_semiconductor_hearing": {
        "source_indexes": (41,),
        "route": "policy",
        "reason": "국회 청문회는 투자정책·집행 일정 워치 대상",
    },
    "grok_starlink_usage_metrics": {
        "source_indexes": (42,),
        "route": "exclude",
        "reason": "한국 상장사·계약·공식 매출 연결이 불명확",
    },
    "treasury_yield_gold_rotation": {
        "source_indexes": (43,),
        "route": "conditional",
        "reason": "시장 해설은 금리·금 가격 실제 수치 확인 필요",
    },
    "spacex_revenue_projection": {
        "source_indexes": (44,),
        "route": "exclude",
        "reason": "검증된 계약·공시 없는 장기 매출 전망",
    },
    "us_chip_tariff_embedded_products": {
        "source_indexes": (45,),
        "route": "policy",
        "reason": "반도체 관세 적용대상 확대는 정책 워치 대상",
    },
    "us_monetary_policy_warsh_rate_outlook": {
        "source_indexes": (46, 55, 57, 70, 77, 78, 86, 87),
        "route": "conditional",
        "reason": "연준 발언·전망은 FOMC·금리선물 확인 전 중복 송출 방지",
    },
    "trump_coupang_asset_trade_disclosure": {
        "source_indexes": (47, 54, 58),
        "route": "policy",
        "reason": "대통령 자산거래·이해충돌 공시는 정책 워치 대상",
    },
    "openai_samsung_computational_memory": {
        "source_indexes": (48,),
        "route": "send",
        "reason": "자체 AI칩·연산메모리의 공급망 경쟁",
    },
    "ai_public_opinion_survey": {
        "source_indexes": (49,),
        "route": "exclude",
        "reason": "여론조사만으로 기업 실적·수급 변화를 확정할 수 없음",
    },
    "us_venezuela_oil_agreement": {
        "source_indexes": (50, 51, 52, 56, 64, 73, 74),
        "route": "send",
        "reason": "신뢰외신이 반복 확인한 원유정책·공급 변수",
    },
    "cxmt_memory_revenue_growth": {
        "source_indexes": (59, 61, 62),
        "route": "send",
        "reason": "CXMT 실적 급증과 중국 메모리 경쟁 심화",
    },
    "generic_ai_memory_supply_beneficiary": {
        "source_indexes": (60,),
        "route": "conditional",
        "reason": "기업 식별·원문 수치가 부족한 제목형 기사",
    },
    "oil_rate_hold_commentary": {
        "source_indexes": (63,),
        "route": "conditional",
        "reason": "유가·금리 연동 전망은 실제 정책·가격 확인 필요",
    },
    "trump_debt_inflation_election_commentary": {
        "source_indexes": (65,),
        "route": "exclude",
        "reason": "정치 해설 중심으로 직접 시장 조치가 없음",
    },
    "korea_silicon_valley_ai_alliance": {
        "source_indexes": (66,),
        "route": "conditional",
        "reason": "협력 의향과 실제 계약·투자를 분리 확인",
    },
    "china_russia_pipeline_meeting": {
        "source_indexes": (67,),
        "route": "policy",
        "reason": "에너지 공급망 외교 일정은 정책 워치 대상",
    },
    "ymtc_nand_wafer_capacity_expansion": {
        "source_indexes": (69, 75),
        "route": "send",
        "reason": "낸드 웨이퍼 증설과 한국 업체 점유율 위협",
    },
    "korea_equity_weekly_outlook": {
        "source_indexes": (71,),
        "route": "exclude",
        "reason": "주간 전망은 개별 새 사실·촉매가 아님",
    },
    "semiconductor_trickle_down_household_debt": {
        "source_indexes": (72,),
        "route": "conditional",
        "reason": "거시 해설은 가계금리·소득 공식지표 확인 필요",
    },
    "samsung_skhynix_corporate_tax": {
        "source_indexes": (76, 84, 88),
        "route": "exclude",
        "reason": "동일 법인세 추정의 반복·파생 수치",
    },
    "canada_usa_boycott": {
        "source_indexes": (79,),
        "route": "exclude",
        "reason": "소비자 반응 해설이며 한국 기업 직접 노출 부족",
    },
    "musk_johnson_meeting": {
        "source_indexes": (80,),
        "route": "exclude",
        "reason": "회동 계획만으로 정책·계약 변화가 없음",
    },
    "semiconductor_etf_thematic_expansion": {
        "source_indexes": (81,),
        "route": "conditional",
        "reason": "ETF 테마 확장은 실제 설정액·편입 확인 필요",
    },
    "single_stock_leverage_etf_rule_effect": {
        "source_indexes": (82,),
        "route": "send",
        "reason": "거래대금 급감은 직접적인 수급 변화",
    },
    "korea_robotaxi_commercialization": {
        "source_indexes": (83,),
        "route": "send",
        "reason": "상용화·자율주행 도입 일정의 사업화 신호",
    },
    "samsung_sdi_gm_ess_jv_restructure": {
        "source_indexes": (85,),
        "route": "send",
        "reason": "ESS 합작법인 생산능력·지분 변경",
    },
    "bigtech_ai_profitability_commentary": {
        "source_indexes": (89,),
        "route": "conditional",
        "reason": "산업 해설은 실제 실적·CAPEX 자료 확인 필요",
    },
    "china_mobile_lpddr6_commercialization": {
        "source_indexes": (90,),
        "route": "send",
        "reason": "LPDDR6 양산·고객 탑재는 경쟁제품 상용화 신호",
    },
    "korea_ai_megaproject_personnel_policy": {
        "source_indexes": (91,),
        "route": "policy",
        "reason": "정부 AI 산업정책 집행 인사는 정책 워치 대상",
    },
    "china_memory_competition_general": {
        "source_indexes": (92,),
        "route": "conditional",
        "reason": "경쟁위협의 원문 수치·생산능력 확인 필요",
    },
    "samsung_skhynix_margin_credit_concentration": {
        "source_indexes": (93,),
        "route": "send",
        "reason": "신용자금 집중은 대형주 수급·변동성 변수",
    },
}


ATTACHMENT_20260827_30_ALERT_CASES = (
    (
        "엔비디아 AI 수요·메모리 공급 부족에 삼전닉스 내년 기대",
        "엔비디아가 AI 수요와 메모리 공급 부족을 재확인했고 삼성전자와 SK하이닉스의 내년 호조 전망이 나왔습니다.",
        "nvidia_ai_hbm_demand_outlook",
        "삼성전자·SK하이닉스",
        "뉴스1",
    ),
    (
        "트럼프 이란 휴전 조건 거부 뒤 유가 2% 상승",
        "트럼프가 이란 휴전 조건 복귀를 거부한 뒤 국제유가가 2% 상승 마감했습니다.",
        "iran_ceasefire_oil_price_move",
        "2%",
        "Reuters",
    ),
    (
        "AI 활용 글라스 캐리어 결함검사로 HBM 수율 개선",
        "AI 기술로 HBM 글라스 캐리어 유리 웨이퍼의 보이지 않는 결함을 검사해 수율 개선을 추진합니다.",
        "hbm_glass_carrier_yield_inspection",
        "결함",
        "한국일보",
    ),
    (
        "삼성전자·SK하이닉스 총 46조원 자사주 매입·소각",
        "삼성전자와 SK하이닉스가 총 46조원 규모 자사주 매입과 소각을 결정했습니다.",
        "samsung_skhynix_shareholder_return_program",
        "46조원",
        "한국경제TV",
    ),
    (
        "ESS 법적 분류·이격거리 기준 신설",
        "정부가 ESS 법적 분류를 명확히 하고 이격거리 기준을 신설하는 규제개선을 추진합니다.",
        "korea_ess_regulatory_improvement",
        "이격거리",
        "아이뉴스24",
    ),
    (
        "TSMC 파운드리 점유율 73%·삼성전자 7%",
        "2분기 파운드리 점유율은 TSMC 73%, 삼성전자 7%로 격차가 확대됐습니다.",
        "tsmc_foundry_share_gap",
        "73%",
        "이데일리",
    ),
    (
        "고려아연, 반도체황산 라인 4만톤 증설",
        "고려아연이 반도체황산 생산라인을 연 4만톤 증설합니다.",
        "korea_zinc_semiconductor_sulfuric_acid_capacity",
        "4만톤",
        "한국경제",
    ),
    (
        "NXT, 하이닉스 하한가 뒤 프리마켓 거래방식 개편 검토",
        "NXT가 프리마켓 가격 급변을 막기 위해 거래방식 개편을 검토합니다.",
        "nxt_premarket_microstructure_rule",
        "거래방식",
        "데일리안",
    ),
    (
        "미국, 칩 내장 제품까지 반도체 관세 확대 검토",
        "미국이 반도체뿐 아니라 칩이 들어간 제품까지 관세 대상을 넓히는 방안을 검토합니다.",
        "us_chip_tariff_embedded_products",
        "칩 내장 제품",
        "Reuters",
    ),
    (
        "오픈AI 자체칩·삼성 연산메모리로 AI 병목 대응",
        "오픈AI는 자체 AI칩을, 삼성전자는 연산 메모리를 추진하며 AI 반도체 병목 완화 경쟁이 커졌습니다.",
        "openai_samsung_computational_memory",
        "연산메모리",
        "한국경제",
    ),
    (
        "트럼프, 베네수엘라 원유 매장량 통제 합의 주장",
        "트럼프가 베네수엘라의 650억 배럴 원유 매장량 통제 관련 합의가 있었다고 밝혔습니다.",
        "us_venezuela_oil_agreement",
        "650억 배럴",
        "Reuters",
    ),
    (
        "CXMT 상반기 매출 10배 증가",
        "CXMT 상반기 매출이 10배 증가하며 중국 D램 경쟁력 확대 신호가 나왔습니다.",
        "cxmt_memory_revenue_growth",
        "10배",
        "머니투데이",
    ),
    (
        "YMTC, 낸드 웨이퍼 생산 내년 250만장 확대",
        "YMTC가 낸드 웨이퍼 생산을 내년 250만장으로 늘려 점유율 경쟁을 키웁니다.",
        "ymtc_nand_wafer_capacity_expansion",
        "250만장",
        "이데일리",
    ),
    (
        "단일종목 레버리지 ETF 거래대금 19조원에서 5000억원",
        "단일종목 레버리지 ETF 규제 후 거래대금이 19조원에서 5000억원으로 줄었습니다.",
        "single_stock_leverage_etf_rule_effect",
        "5000억원",
        "이데일리",
    ),
    (
        "포니AI, 퓨처링크와 한국 로보택시 상용화 추진",
        "포니AI가 퓨처링크와 한국 로보택시 상용화와 7세대 자율주행 도입을 추진합니다.",
        "korea_robotaxi_commercialization",
        "퓨처링크",
        "이데일리",
    ),
    (
        "삼성SDI, GM 합작법인 지분 인수로 ESS 26GWh 확보 추진",
        "삼성SDI가 GM 합작법인 지분 인수로 ESS 셀 26GWh 생산능력 확보를 추진합니다.",
        "samsung_sdi_gm_ess_jv_restructure",
        "26GWh",
        "머니투데이",
    ),
    (
        "CXMT LPDDR6 양산·샤오미 스마트폰 첫 탑재",
        "CXMT가 LPDDR6을 양산해 샤오미 스마트폰에 처음 탑재했습니다.",
        "china_mobile_lpddr6_commercialization",
        "LPDDR6",
        "매일경제",
    ),
    (
        "증시 신용자금 증가분, 삼성전자·SK하이닉스에 집중",
        "증시에서 늘어난 신용자금의 40% 이상이 삼성전자와 SK하이닉스로 향했습니다.",
        "samsung_skhynix_margin_credit_concentration",
        "신용자금",
        "머니투데이",
    ),
    (
        "HBM 다음은 패키징…삼성·SK, 차세대 기술 경쟁 본격화",
        "삼성전자와 SK하이닉스가 HBM 패키징과 Cube-E·2.3D 기술 경쟁을 본격화합니다.",
        "samsung_skhynix_hbm_packaging_roadmap",
        "차세대 패키징",
        "한국경제",
    ),
    (
        "AI·메가프로젝트 '핀셋인사'…미래 먹거리 육성 의지 재천명",
        "정부가 AI 메가프로젝트 추진을 위한 핀셋인사를 단행했습니다.",
        "korea_ai_megaproject_personnel_policy",
        "AI 메가프로젝트",
        "정부",
    ),
    (
        "무역 휴전 연장 가능성에 시진핑 방미 일정 주목",
        "미·중 무역 휴전 연장과 시진핑 방미 가능성이 통상 일정 변수로 부각됐습니다.",
        "us_china_trade_truce_calendar",
        "무역 휴전",
        "Reuters",
    ),
)


def source_row(
    title: str,
    body: str,
    *,
    publisher: str = "contract fixture",
) -> dict:
    return {
        "source_title": title,
        "title": title,
        "source_body": body,
        "source_abstract": body,
        "source": publisher,
        "publisher": publisher,
        "link": "https://example.com/article",
        "published": datetime(2026, 8, 22, tzinfo=timezone.utc),
        "body_verified": True,
    }


def main() -> int:
    failures = []
    configured = {item[0] for item in radar.KOREAN_BUSINESS_SEARCH_SOURCES}
    missing = SEARCH_NAMES - configured
    if missing:
        failures.append(f"missing_searches={sorted(missing)}")

    for title, required_term, required_impacts in CASES:
        lowered = title.lower()
        material = {
            term
            for term in radar.KOREAN_BUSINESS_MATERIAL_TERMS
            if radar.korean_business_title_has_material_term(lowered, term)
        }
        impacts = set(radar.korean_business_impacts(lowered, []))
        if required_term not in material:
            failures.append(f"missing_material={required_term}:{title}")
        if not required_impacts.issubset(impacts):
            failures.append(
                f"missing_impacts={sorted(required_impacts - impacts)}:{title}"
            )

    route_counts = {}
    for group, item in ATTACHMENT_20260822_GROUPS.items():
        route = item["route"]
        route_counts[route] = route_counts.get(route, 0) + int(item["source_items"])
        if route not in {"send", "policy", "conditional", "exclude"}:
            failures.append(f"invalid_attachment_route={group}:{route}")
    source_item_count = sum(
        int(item["source_items"]) for item in ATTACHMENT_20260822_GROUPS.values()
    )
    if source_item_count != 35:
        failures.append(f"attachment_source_count={source_item_count}:expected=35")
    if route_counts.get("send", 0) < 14:
        failures.append(f"attachment_send_coverage={route_counts.get('send', 0)}")

    now = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
    for title, body, expected_kind, required_fact in ATTACHMENT_ALERT_CASES:
        row = source_row(title, body)
        alert = radar.build_attachment_verified_event_alert(
            row, now, f"{title} {body}".lower()
        )
        if not alert:
            failures.append(f"attachment_alert_missing={expected_kind}:{title}")
            continue
        if alert.get("korean_business_kind") != expected_kind:
            failures.append(
                f"attachment_alert_kind={alert.get('korean_business_kind')}:"
                f"expected={expected_kind}:{title}"
            )
        core = str(alert.get("telegram_core_fact") or "")
        if required_fact.lower() not in core.lower():
            failures.append(
                f"attachment_alert_core_mismatch={expected_kind}:{core!r}"
            )
        if not radar.core_sentence_is_complete(core, limit=160):
            failures.append(
                f"attachment_alert_incomplete_core={expected_kind}:{core!r}"
            )

    attachment23_route_counts = {}
    for group, item in ATTACHMENT_20260823_GROUPS.items():
        route = item["route"]
        attachment23_route_counts[route] = (
            attachment23_route_counts.get(route, 0) + int(item["source_items"])
        )
        if route not in {"send", "policy", "conditional", "exclude"}:
            failures.append(f"invalid_attachment23_route={group}:{route}")
    attachment23_source_item_count = sum(
        int(item["source_items"]) for item in ATTACHMENT_20260823_GROUPS.values()
    )
    if attachment23_source_item_count != 8:
        failures.append(
            f"attachment23_source_count={attachment23_source_item_count}:expected=8"
        )
    if attachment23_route_counts.get("send", 0) < 6:
        failures.append(
            f"attachment23_send_coverage={attachment23_route_counts.get('send', 0)}"
        )

    for title, body, expected_kind, required_fact in ATTACHMENT_20260823_ALERT_CASES:
        row = source_row(title, body)
        alert = radar.build_attachment_verified_event_alert(
            row, now, f"{title} {body}".lower()
        )
        if not alert:
            failures.append(f"attachment23_alert_missing={expected_kind}:{title}")
            continue
        if alert.get("korean_business_kind") != expected_kind:
            failures.append(
                f"attachment23_alert_kind={alert.get('korean_business_kind')}:"
                f"expected={expected_kind}:{title}"
            )
        core = str(alert.get("telegram_core_fact") or "")
        if required_fact.lower() not in core.lower():
            failures.append(
                f"attachment23_alert_core_mismatch={expected_kind}:{core!r}"
            )
        if not radar.core_sentence_is_complete(core, limit=160):
            failures.append(
                f"attachment23_alert_incomplete_core={expected_kind}:{core!r}"
            )

    attachment26_route_counts = {}
    for group, item in ATTACHMENT_20260826_GROUPS.items():
        route = item["route"]
        attachment26_route_counts[route] = (
            attachment26_route_counts.get(route, 0) + int(item["source_items"])
        )
        if route not in {"send", "policy", "conditional", "exclude"}:
            failures.append(f"invalid_attachment26_route={group}:{route}")
    attachment26_source_item_count = sum(
        int(item["source_items"]) for item in ATTACHMENT_20260826_GROUPS.values()
    )
    if attachment26_source_item_count != 38:
        failures.append(
            f"attachment26_source_count={attachment26_source_item_count}:expected=38"
        )
    if attachment26_route_counts.get("send", 0) < 20:
        failures.append(
            f"attachment26_send_coverage={attachment26_route_counts.get('send', 0)}"
        )

    attachment26_now = datetime(2026, 8, 26, 12, tzinfo=timezone.utc)
    for title, body, expected_kind, required_fact in ATTACHMENT_20260826_ALERT_CASES:
        row = source_row(title, body)
        alert = radar.build_attachment_verified_event_alert(
            row, attachment26_now, f"{title} {body}".lower()
        )
        if not alert:
            failures.append(f"attachment26_alert_missing={expected_kind}:{title}")
            continue
        if alert.get("korean_business_kind") != expected_kind:
            failures.append(
                f"attachment26_alert_kind={alert.get('korean_business_kind')}:"
                f"expected={expected_kind}:{title}"
            )
        core = str(alert.get("telegram_core_fact") or "")
        if required_fact.lower() not in core.lower():
            failures.append(
                f"attachment26_alert_core_mismatch={expected_kind}:{core!r}"
            )
        if not radar.core_sentence_is_complete(core, limit=160):
            failures.append(
                f"attachment26_alert_incomplete_core={expected_kind}:{core!r}"
            )

    attachment27_route_counts = {}
    for group, item in ATTACHMENT_20260827_GROUPS.items():
        route = item["route"]
        attachment27_route_counts[route] = (
            attachment27_route_counts.get(route, 0) + int(item["source_items"])
        )
        if route not in {"send", "policy", "conditional", "exclude"}:
            failures.append(f"invalid_attachment27_route={group}:{route}")
    attachment27_source_item_count = sum(
        int(item["source_items"]) for item in ATTACHMENT_20260827_GROUPS.values()
    )
    if attachment27_source_item_count != 49:
        failures.append(
            f"attachment27_source_count={attachment27_source_item_count}:expected=49"
        )
    expected_attachment27_routes = {
        "send": 25,
        "policy": 11,
        "conditional": 10,
        "exclude": 3,
    }
    if attachment27_route_counts != expected_attachment27_routes:
        failures.append(
            f"attachment27_routes={attachment27_route_counts}:expected={expected_attachment27_routes}"
        )

    attachment27_now = datetime(2026, 8, 27, 12, tzinfo=timezone.utc)
    for title, body, expected_kind, required_fact in ATTACHMENT_20260827_ALERT_CASES:
        row = source_row(title, body)
        alert = radar.build_attachment_verified_event_alert(
            row, attachment27_now, f"{title} {body}".lower()
        )
        if not alert:
            failures.append(f"attachment27_alert_missing={expected_kind}:{title}")
            continue
        if alert.get("korean_business_kind") != expected_kind:
            failures.append(
                f"attachment27_alert_kind={alert.get('korean_business_kind')}:"
                f"expected={expected_kind}:{title}"
            )
        core = str(alert.get("telegram_core_fact") or "")
        if required_fact.lower() not in core.lower():
            failures.append(
                f"attachment27_alert_core_mismatch={expected_kind}:{core!r}"
            )
        if not radar.core_sentence_is_complete(core, limit=160):
            failures.append(
                f"attachment27_alert_incomplete_core={expected_kind}:{core!r}"
            )
        alert["fx_conversion"] = radar.build_alert_fx_conversion(
            alert,
            {
                "rates": {
                    "USD": {
                        "value": 1400.0,
                        "status": "확정",
                        "reference_time_kst": "2026-08-27T12:00:00+09:00",
                        "query_time_kst": "2026-08-27T12:00:00+09:00",
                        "source": "contract fixture FX",
                        "url": "https://example.com/usdkrw",
                    }
                }
            },
            attachment27_now,
        )
        rendered = radar.compact_alert(alert, 1, attachment27_now, {}, {})
        rendered_errors = radar.compact_alert_block_errors(rendered)
        if rendered_errors:
            failures.append(
                f"attachment27_rendered_block={expected_kind}:{rendered_errors}:{rendered!r}"
            )
        if (
            expected_kind == "us_pce_ndf_rate_shift"
            and "미국 7월 PCE 예상 상회" not in rendered
        ):
            failures.append(f"attachment27_pce_headline_missing={rendered!r}")
        if (
            expected_kind == "us_pce_ndf_rate_shift"
            and alert.get("news")
            != "미국 7월 PCE 예상 상회…원·달러 NDF·연준 금리 경로 재평가"
        ):
            failures.append(f"attachment27_pce_send_title={alert.get('news')!r}")

    attachment27_evening_route_counts = {}
    for group, item in ATTACHMENT_20260827_EVENING_GROUPS.items():
        route = item["route"]
        attachment27_evening_route_counts[route] = (
            attachment27_evening_route_counts.get(route, 0)
            + int(item["source_items"])
        )
        if route not in {"send", "policy", "conditional", "exclude"}:
            failures.append(f"invalid_attachment27_evening_route={group}:{route}")
    attachment27_evening_source_item_count = sum(
        int(item["source_items"])
        for item in ATTACHMENT_20260827_EVENING_GROUPS.values()
    )
    if attachment27_evening_source_item_count != 7:
        failures.append(
            "attachment27_evening_source_count="
            f"{attachment27_evening_source_item_count}:expected=7"
        )
    expected_attachment27_evening_routes = {"send": 5, "conditional": 2}
    if attachment27_evening_route_counts != expected_attachment27_evening_routes:
        failures.append(
            "attachment27_evening_routes="
            f"{attachment27_evening_route_counts}:expected={expected_attachment27_evening_routes}"
        )

    for title, body, expected_kind, required_fact, publisher in ATTACHMENT_20260827_EVENING_ALERT_CASES:
        row = source_row(title, body, publisher=publisher)
        alert = radar.build_attachment_verified_event_alert(
            row, attachment27_now, f"{title} {body}".lower()
        )
        if not alert:
            failures.append(f"attachment27_evening_alert_missing={expected_kind}:{title}")
            continue
        if alert.get("korean_business_kind") != expected_kind:
            failures.append(
                "attachment27_evening_alert_kind="
                f"{alert.get('korean_business_kind')}:expected={expected_kind}:{title}"
            )
        core = str(alert.get("telegram_core_fact") or "")
        if required_fact.lower() not in core.lower():
            failures.append(
                f"attachment27_evening_alert_core_mismatch={expected_kind}:{core!r}"
            )
        if not radar.core_sentence_is_complete(core, limit=160):
            failures.append(
                f"attachment27_evening_alert_incomplete_core={expected_kind}:{core!r}"
            )
        rendered = radar.compact_alert(alert, 1, attachment27_now, {}, {})
        rendered_errors = radar.compact_alert_block_errors(rendered)
        if rendered_errors:
            failures.append(
                "attachment27_evening_rendered_block="
                f"{expected_kind}:{rendered_errors}:{rendered!r}"
            )

    nvhbm_duplicates = (
        source_row(
            "엔비디아, 맞춤형 HBM 기술 NVHBM 공개",
            "엔비디아가 NVHBM을 공개하고 아마존 안나푸르나랩과 공동 개발을 추진합니다.",
        ),
        source_row(
            "엔비디아, NVHBM 기반 맞춤형 HBM 협력 발표",
            "엔비디아는 아마존과 NVHBM 공동 개발 협력을 공식화했습니다.",
        ),
        source_row(
            "엔비디아, 메모리 대역폭 높인 NVHBM 공개",
            "엔비디아가 주요 메모리 공급사와 설계·검증한 맞춤형 HBM NVHBM을 공개했습니다.",
        ),
    )
    nvhbm_duplicate_themes = {
        str(
            (radar.build_attachment_verified_event_alert(
                row,
                attachment27_now,
                f"{row['source_title']} {row['source_body']}".lower(),
            ) or {}).get("supply_chain_theme") or ""
        )
        for row in nvhbm_duplicates
    }
    if len(nvhbm_duplicate_themes) != 1 or "" in nvhbm_duplicate_themes:
        failures.append(
            f"attachment27_evening_duplicate_theme={sorted(nvhbm_duplicate_themes)}"
        )

    attachment27_duplicates = (
        source_row(
            "오픈AI, 브로드컴과 자체 AI칩 할라페뇨 연내 가동",
            "오픈AI가 브로드컴과 개발한 자체 AI칩 할라페뇨를 연내 추론 서비스에 투입합니다.",
        ),
        source_row(
            "오픈AI 자체 AI칩 할라페뇨 성능 공개",
            "오픈AI의 자체 AI칩 할라페뇨는 브로드컴과 개발됐고 HBM4 채택 가능성이 거론됩니다.",
        ),
    )
    attachment27_duplicate_themes = {
        str(
            (radar.build_attachment_verified_event_alert(
                row,
                attachment27_now,
                f"{row['source_title']} {row['source_body']}".lower(),
            ) or {}).get("supply_chain_theme") or ""
        )
        for row in attachment27_duplicates
    }
    if len(attachment27_duplicate_themes) != 1 or "" in attachment27_duplicate_themes:
        failures.append(
            f"attachment27_duplicate_theme={sorted(attachment27_duplicate_themes)}"
        )

    full_indexes = [
        index
        for item in ATTACHMENT_20260827_30_FULL_GROUPS.values()
        for index in item["source_indexes"]
    ]
    if len(ATTACHMENT_20260827_30_FULL_GROUPS) != 58:
        failures.append(
            "attachment27_30_group_count="
            f"{len(ATTACHMENT_20260827_30_FULL_GROUPS)}:expected=58"
        )
    if len(full_indexes) != 93 or sorted(full_indexes) != list(range(1, 94)):
        failures.append(
            "attachment27_30_full_index_coverage="
            f"count={len(full_indexes)} unique={len(set(full_indexes))}"
        )
    full_route_counts = {}
    for group, item in ATTACHMENT_20260827_30_FULL_GROUPS.items():
        route = item["route"]
        full_route_counts[route] = full_route_counts.get(route, 0) + len(
            item["source_indexes"]
        )
        if route not in {"send", "policy", "conditional", "exclude"}:
            failures.append(f"invalid_attachment27_30_route={group}:{route}")
        if not item.get("reason"):
            failures.append(f"attachment27_30_missing_reason={group}")
    expected_full_route_counts = {
        "send": 42,
        "policy": 9,
        "conditional": 27,
        "exclude": 15,
    }
    if full_route_counts != expected_full_route_counts:
        failures.append(
            "attachment27_30_routes="
            f"{full_route_counts}:expected={expected_full_route_counts}"
        )

    attachment27_30_now = datetime(2026, 8, 30, 12, tzinfo=timezone.utc)
    for title, body, expected_kind, required_fact, publisher in ATTACHMENT_20260827_30_ALERT_CASES:
        row = source_row(title, body, publisher=publisher)
        alert = radar.build_attachment_verified_event_alert(
            row, attachment27_30_now, f"{title} {body}".lower()
        )
        if not alert:
            failures.append(f"attachment27_30_alert_missing={expected_kind}:{title}")
            continue
        if alert.get("korean_business_kind") != expected_kind:
            failures.append(
                "attachment27_30_alert_kind="
                f"{alert.get('korean_business_kind')}:expected={expected_kind}:{title}"
            )
        core = str(alert.get("telegram_core_fact") or "")
        if required_fact.lower() not in core.lower():
            failures.append(
                f"attachment27_30_alert_core_mismatch={expected_kind}:{core!r}"
            )
        if not radar.core_sentence_is_complete(core, limit=160):
            failures.append(
                f"attachment27_30_alert_incomplete_core={expected_kind}:{core!r}"
            )
        rendered = radar.compact_alert(alert, 1, attachment27_30_now, {}, {})
        rendered_errors = radar.compact_alert_block_errors(rendered)
        if rendered_errors:
            failures.append(
                "attachment27_30_rendered_block="
                f"{expected_kind}:{rendered_errors}:{rendered!r}"
            )

    full_duplicate_rows = (
        source_row(
            "트럼프, 베네수엘라 석유 합의로 650억 배럴 통제 주장",
            "트럼프가 미국과 베네수엘라가 650억 배럴 원유 매장량 통제 합의에 도달했다고 밝혔습니다.",
            publisher="Reuters",
        ),
        source_row(
            "미국, 베네수엘라 원유 매장량 부분 통제권 확보",
            "미국이 베네수엘라의 650억 배럴 석유 매장량에 대한 부분 통제권을 확보했다는 보도입니다.",
            publisher="CNBC",
        ),
    )
    full_duplicate_themes = {
        str(
            (radar.build_attachment_verified_event_alert(
                row,
                attachment27_30_now,
                f"{row['source_title']} {row['source_body']}".lower(),
            ) or {}).get("supply_chain_theme")
            or ""
        )
        for row in full_duplicate_rows
    }
    if len(full_duplicate_themes) != 1 or "" in full_duplicate_themes:
        failures.append(
            f"attachment27_30_duplicate_theme={sorted(full_duplicate_themes)}"
        )

    commitment_title, commitment_body, _, _ = next(
        case
        for case in ATTACHMENT_20260827_ALERT_CASES
        if case[2] == "nvidia_memory_purchase_commitments"
    )
    commitment_row = source_row(commitment_title, commitment_body)
    commitment_alert = radar.build_attachment_verified_event_alert(
        commitment_row,
        attachment27_now,
        f"{commitment_title} {commitment_body}".lower(),
    )
    commitment_alert["fx_conversion"] = radar.build_alert_fx_conversion(
        commitment_alert,
        {
            "rates": {
                "USD": {
                    "value": 1400.0,
                    "status": "확정",
                    "reference_time_kst": "2026-08-27T12:00:00+09:00",
                    "query_time_kst": "2026-08-27T12:00:00+09:00",
                    "source": "contract fixture FX",
                    "url": "https://example.com/usdkrw",
                }
            }
        },
        attachment27_now,
    )
    commitment_block = radar.compact_alert(
        commitment_alert, 1, attachment27_now, {}, {}
    )
    if "2790억달러(약 391조원)" not in commitment_block:
        failures.append(f"attachment27_fx_conversion={commitment_block!r}")
    if radar.compact_alert_block_errors(commitment_block):
        failures.append(f"attachment27_fx_quality={commitment_block!r}")

    mixed_etf_row = source_row(
        "미래에셋운용, '삼전닉스+미국 단기국채' 혼합 ETF 상장 | 연합뉴스",
        (
            "미래에셋자산운용은 삼성전자와 SK하이닉스에 각각 25%를 투자하고 "
            "나머지 50%는 잔존만기 0~1년의 미국 단기국채에 투자하는 "
            "채권혼합형 ETF를 상장했다고 밝혔습니다."
        ),
    )
    mixed_etf_alert = radar.build_attachment_verified_event_alert(
        mixed_etf_row,
        attachment26_now,
        f"{mixed_etf_row['source_title']} {mixed_etf_row['source_body']}".lower(),
    )
    mixed_etf_core = str((mixed_etf_alert or {}).get("telegram_core_fact") or "")
    if (mixed_etf_alert or {}).get("korean_business_kind") != "korea_samsung_skhynix_us_treasury_mixed_etf":
        failures.append(f"mixed_etf_kind={mixed_etf_alert!r}")
    if not all(term in mixed_etf_core for term in ("미국 단기국채", "50%", "삼성전자", "SK하이닉스")):
        failures.append(f"mixed_etf_core_mismatch={mixed_etf_core!r}")
    mixed_block = radar.compact_alert(mixed_etf_alert or {}, 1, attachment26_now, {}, {})
    if radar.compact_alert_block_errors(mixed_block):
        failures.append(f"mixed_etf_block_quality={mixed_block!r}")
    linked_report = radar.strip_article_boilerplate_from_report(
        '출처: <a href="https://www.yna.co.kr/view/AKR20260825057300008">원문</a>'
    )
    linked_text, linked_entities = radar.telegram_text_and_entities(linked_report)
    if "h ps://" in linked_report or "https://" not in linked_report:
        failures.append(f"source_link_scheme_corrupted={linked_report!r}")
    if linked_text != "출처: 원문" or linked_entities != [
        {
            "type": "text_link",
            "offset": 4,
            "length": 2,
            "url": "https://www.yna.co.kr/view/AKR20260825057300008",
        }
    ]:
        failures.append(f"telegram_link_entity={linked_text!r}:{linked_entities!r}")
    duplicate_rows = (
        source_row(
            "엔비디아, 삼성 파운드리에 그록3 LPX 추론가속기 양산 위탁",
            "엔비디아가 삼성전자 파운드리에 그록3 LPX 추론가속기 양산을 맡겼다고 보도됐습니다.",
        ),
        source_row(
            "삼성 파운드리, 엔비디아 그록3 LPX 추론칩 생산",
            "삼성전자 파운드리가 엔비디아 그록3 LPX 추론가속기 생산을 맡았다고 보도됐습니다.",
        ),
    )
    duplicate_themes = {
        str(
            (radar.build_attachment_verified_event_alert(
                row, attachment26_now, f"{row['source_title']} {row['source_body']}".lower()
            ) or {}).get("supply_chain_theme") or ""
        )
        for row in duplicate_rows
    }
    if len(duplicate_themes) != 1 or "" in duplicate_themes:
        failures.append(f"attachment26_duplicate_theme={sorted(duplicate_themes)}")

    ymtc_row = source_row(
        "YMTC, 낸드 생산 확대 위한 IPO 추진",
        "YMTC가 낸드와 SSD 생산 확대 자금을 조달하기 위해 IPO를 추진합니다.",
    )
    ymtc_alert = radar.build_china_memory_ipo_alert(
        ymtc_row, now, "ymtc 낸드 ssd ipo 상장 추진"
    )
    if not ymtc_alert or "YMTC" not in str(ymtc_alert.get("telegram_core_fact")):
        failures.append("ymtc_memory_ipo_builder_missing")

    etf_row = source_row(
        "국내 ETF 순자산 두 달 새 60조원 감소",
        "국내 주식형 ETF 순자산이 기초자산 가격 하락과 레버리지 규제 영향으로 두 달 새 60조원 감소했습니다.",
    )
    etf_alert = radar.build_attachment_verified_event_alert(
        etf_row, now, "국내 주식형 etf 순자산 기초자산 가격 하락 레버리지 규제 60조원 감소"
    )
    etf_core = str((etf_alert or {}).get("telegram_core_fact") or "")
    if "60조원 감소" not in etf_core or "유입" in etf_core or "유출" in etf_core:
        failures.append(f"etf_valuation_not_flow={etf_core!r}")

    # A clipped source fragment must be rejected, never completed by invention.
    prose_cases = (
        ("MSCI 반영 시 1조원대 자금 유입을 기대할…", ""),
        ("및 수주잔고 20억달러를 기록했습니다.", "수주잔고 20억달러를 기록했습니다."),
        ("그리고 이번 레버리지 ETF 사태의 배후를 조사해야 한다.", ""),
    )
    for raw, expected in prose_cases:
        actual = radar.complete_prose_text(raw, limit=100)
        if actual != expected:
            failures.append(f"damaged_core_prose={actual!r}:expected={expected!r}")
        if actual and not radar.core_sentence_is_complete(actual, limit=100):
            failures.append(f"incomplete_core_prose={actual!r}")

    ui_core = radar.detailed_article_core(
        "[오늘의 투자전략] 코스피, 7000선 재진입 시도 전망",
        (
            "이번 주 국내 증시는 코스피 7000선 재진입을 시도할 전망이다. "
            "이투데이 마켓 일반 [오늘의 투자전략] 코스피, 7000선 재진입 시도 전망 "
            "입력 2026-08-31 07:55 정수천 기자 북마크 되었습니다. "
            "마이페이지에서 확인하세요. 카카오톡 페이스북 엑스 URL공유 "
            "가장크게 작게 기본 크게 이번 주 국내 증시는 잭슨홀 이후 금리와 수출을 주목한다."
        ),
    )
    if radar.core_has_ui_garbage(ui_core) or not radar.core_sentence_is_complete(ui_core, limit=160):
        failures.append(f"ui_core_cleanup_failed={ui_core!r}")
    if "입력" in ui_core or "북마크" in ui_core or "이번 주 국내 증시" not in ui_core:
        failures.append(f"ui_core_content_failed={ui_core!r}")

    profile_rows = (
        (
            "곽노정 \"2030년말까지 반도체 공급 부족 지속\"",
            "SK하이닉스 CEO 곽노정은 메모리 공급 부족이 2030년 말까지 이어질 수 있다고 전망했습니다.",
            "skhynix_2030_memory_shortage_outlook",
        ),
        (
            "엔비디아 마진 깎은 메모리값…삼전닉스 몰래 웃는다",
            "엔비디아는 메모리 가격 상승으로 4분기 매출총이익률을 71~72%로 전망했습니다. 곽노정은 공급 부족이 2030년까지 이어질 수 있다고 말했습니다.",
            "nvidia_memory_cost_margin_pressure",
        ),
    )
    for title, body, expected_kind in profile_rows:
        profile_alert = radar.build_attachment_verified_event_alert(
            source_row(title, body),
            attachment27_30_now,
            f"{title} {body}".lower(),
        )
        if not profile_alert or profile_alert.get("korean_business_kind") != expected_kind:
            failures.append(
                f"specific_profile_not_selected={expected_kind}:"
                f"{(profile_alert or {}).get('korean_business_kind')}"
            )

    mismatched_alert = {
        "korean_business_news": True,
        "body_verified": True,
        "source_title": "SK하이닉스 미국 인디애나 HBM 생산기지 착공",
        "news": "SK하이닉스 미국 인디애나 HBM 생산기지 착공",
        "policy_plain_summary": "엔비디아 AI 수요와 메모리 공급 부족이 삼성전자·SK하이닉스의 내년 실적 기대를 높였습니다.",
        "telegram_core_fact": "엔비디아 AI 수요와 메모리 공급 부족이 삼성전자·SK하이닉스의 내년 실적 기대를 높였습니다.",
        "source_abstract": "SK하이닉스가 미국 인디애나주에 HBM 후공정 생산기지를 착공합니다.",
        "publisher": "뉴시스",
        "link": "https://www.newsis.com/view/NISX20260828_0003766487",
    }
    if radar.source_output_aligned(mismatched_alert):
        failures.append("title_body_mismatch_not_blocked_in_cross_contract")

    if failures:
        print("GAMEJOA cross-market coverage contract failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(
        "cross_market_coverage_contract=passed "
        f"cases={len(CASES)} attachment_cases={len(ATTACHMENT_ALERT_CASES)} "
        f"attachment_groups={len(ATTACHMENT_20260822_GROUPS)} "
        f"source_items={source_item_count} "
        f"attachment23_cases={len(ATTACHMENT_20260823_ALERT_CASES)} "
        f"attachment23_groups={len(ATTACHMENT_20260823_GROUPS)} "
        f"attachment23_source_items={attachment23_source_item_count} "
        f"attachment26_cases={len(ATTACHMENT_20260826_ALERT_CASES)} "
        f"attachment26_groups={len(ATTACHMENT_20260826_GROUPS)} "
        f"attachment26_source_items={attachment26_source_item_count} "
        f"attachment27_cases={len(ATTACHMENT_20260827_ALERT_CASES)} "
        f"attachment27_groups={len(ATTACHMENT_20260827_GROUPS)} "
        f"attachment27_source_items={attachment27_source_item_count} "
        f"attachment27_30_cases={len(ATTACHMENT_20260827_30_ALERT_CASES)} "
        f"attachment27_30_groups={len(ATTACHMENT_20260827_30_FULL_GROUPS)} "
        f"attachment27_30_source_items={len(full_indexes)} "
        f"attachment27_30_routes={full_route_counts}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

