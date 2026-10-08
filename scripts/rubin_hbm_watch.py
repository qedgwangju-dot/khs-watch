from __future__ import annotations

import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

try:
    from googlenewsdecoder import gnewsdecoder
except Exception:  # pragma: no cover - dependency failure is handled explicitly
    gnewsdecoder = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "rubin_hbm_watch_state.json"
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)

UA = "Mozilla/5.0 (compatible; khs-watch/2.0; +https://github.com/qedgwangju-dot/khs-watch)"
FX_URL = "https://api.frankfurter.dev/v2/rate/USD/KRW"

OFFICIAL_RUBIN_GB = 288
RUMORED_ULTRA_GB = 192
BREAKEVEN_GPU_GROWTH = OFFICIAL_RUBIN_GB / RUMORED_ULTRA_GB - 1
BERNSTEIN_RUBIN_PREVIOUS_GB = 1024
BERNSTEIN_RUBIN_CURRENT_GB = 640
BERNSTEIN_RUBIN_REDUCTION_PCT = (BERNSTEIN_RUBIN_CURRENT_GB / BERNSTEIN_RUBIN_PREVIOUS_GB - 1) * 100
BERNSTEIN_RUBIN_BREAK_EVEN_GPU_GROWTH = BERNSTEIN_RUBIN_PREVIOUS_GB / BERNSTEIN_RUBIN_CURRENT_GB - 1
BASE_NVLINK_GPU = 72
ULTRA_NVLINK_GPU = 576
BASE_SYSTEM_GB = BASE_NVLINK_GPU * OFFICIAL_RUBIN_GB
ULTRA_SYSTEM_GB = ULTRA_NVLINK_GPU * RUMORED_ULTRA_GB
SYSTEM_HBM_GROWTH = ULTRA_SYSTEM_GB / BASE_SYSTEM_GB - 1
SEND_FRESHNESS_HOURS = 72
SAMSUNG_HBM4_PRICE_TRACK_VERSION = 2
SAMSUNG_HBM4_PRICE_BASELINE = {
    "stage": "negotiation",
    "offered_price_band": "mid_to_high_4_usd_per_gb",
    "offered_price_usd_per_gb_min": None,
    "offered_price_usd_per_gb_max": None,
    "reference_hbm3e_usd_per_gb": 1.5,
    "price_multiple_floor": 3.0,
    "volume_stage": "largely_agreed",
    "target_close_month": "2026-10",
    "reported_supply_status": "virtually_sold_out_reported",
    "pricing_power_stage": "strengthened_reported",
    "pricing_power_driver": "high_spec_performance_and_limited_supply",
    "performance_stable_gbps": 11.7,
    "performance_max_gbps": 13.0,
    "industry_standard_gbps": 8.0,
    "stack_bandwidth_tbps": 3.3,
    "customer_requirement_tbps": 3.0,
    "industry_hbm_dram_wafer_share_current_band": "20s_pct_reported",
    "industry_hbm_dram_wafer_share_2027_pct": 30.0,
    "source": "매일경제 단독 + 삼성전자 공식자료",
    "source_url": "https://www.mk.co.kr/news/business/12167164",
    "premium_source_url": "https://www.mk.co.kr/news/business/12167424",
    "official_performance_source_url": "https://news.samsung.com/kr/%EC%82%BC%EC%84%B1%EC%A0%84%EC%9E%90-%EC%84%B8%EA%B3%84-%EC%B5%9C%EC%B4%88-%EC%97%85%EA%B3%84-%EC%B5%9C%EA%B3%A0-%EC%84%B1%EB%8A%A5%EC%9D%98-hbm4-%EC%96%91%EC%82%B0-%EC%B6%9C%ED%95%98",
    "as_of": "2026-10-02",
    "note": "4달러대 중후반은 제시·협상 가격으로 보존. '사실상 완판'과 협상력 강화는 매일경제 보도 단계이며 실제 고객별 체결물량·체결가격으로 승격하지 않음.",
}
HBM_HYBRID_BOND_TRACK_VERSION = 2
HBM_HYBRID_BOND_PRIMARY = "https://www.damnang.com/p/the-next-memory-race-will-not-be"
HBM_HYBRID_BOND_REPUBLISHER = "https://www.techpowerup.com/353458/sk-hynix-reportedly-faces-difficulties-in-hbm-hybrid-bonding-trailing-samsung"
HBM_HYBRID_SK_OFFICIAL = "https://news.skhynix.com/en/sk-hynix-ships-samples-of-12-layer-next-gen-hbm4e-2/"
HBM_HYBRID_SK_FEASIBILITY = "https://www.skhynix.com/ir/UI-FR-IR12_T7/"
HBM_HYBRID_SAMSUNG_OFFICIAL = "https://news.samsung.com/kr/%EC%82%BC%EC%84%B1%EC%A0%84%EC%9E%90-fms-2026%EC%84%9C-%EC%B0%A8%EC%84%B8%EB%8C%80-3d-%EB%A9%94%EB%AA%A8%EB%A6%AC-%EB%B9%84%EC%A0%84-%EC%A0%9C%EC%8B%9C"
HBM_HYBRID_SHARE_SOURCE = "https://counterpointresearch.com/ko/insights/global-hbm-market-share-q2-2026"
# A single paid, anonymously sourced expert interview, repercussed by
# TechPowerUp. This is NOT a verified "SK made no samples" corporate fact.
HBM_HYBRID_BOND_BASELINE = {
    "reported_origin": "Damnang",
    "reported_origin_count": 1,
    "source_evidence": "single_anonymous_engineer_report_not_official",
    "reported_sk_hybrid_difficulty": True,
    "reported_sk_hybrid_customer_sample_not_started": True,
    "reported_samsung_hybrid_customer_sample_sent": True,
    "skhynix_official_hybrid_stage": "technical_feasibility",
    "samsung_official_hybrid_stage": "technology_showcase",
    "skhynix_official_hybrid_customer_sample_verified": False,
    "samsung_official_hybrid_customer_sample_verified": False,
    "sk_hbm4e_mr_muf_sample_shipped": True,
    "samsung_hbm4e_sample_shipped": True,
    "sk_revenue_share_q2_2026_pct": 50.0,
    "samsung_revenue_share_q2_2026_pct": 33.0,
    "interview_date": "2026-09-19",
    "reported_at": "2026-10-06",
    "primary_url": HBM_HYBRID_BOND_PRIMARY,
    "republisher_url": HBM_HYBRID_BOND_REPUBLISHER,
    "sk_official_url": HBM_HYBRID_SK_OFFICIAL,
    "samsung_official_url": HBM_HYBRID_SAMSUNG_OFFICIAL,
    "share_source_url": HBM_HYBRID_SHARE_SOURCE,
    "last_official_stage_change_at": None,
}
HBM_HYBRID_STAGE_RANK = {
    "technical_feasibility": 0,
    "technology_showcase": 0,
    "internal_hbm_prototype": 1,
    "customer_hbm_sample_shipped": 2,
    "customer_qualification_passed": 3,
    "pilot_line_running": 4,
    "hbm_mass_production_started": 5,
}

SAMSUNG_HBM4E_THERMAL_TRACK_VERSION = 1
SAMSUNG_HBM4E_THERMAL_BASELINE = {
    "industry_current_interposer_reticle_x": 5.5,
    "reported_future_interposer_reticle_x": 40.0,
    "reported_future_interposer_stage": "industry_projection",
    "tsmc_official_2028_cowos_reticle_x": 14.0,
    "hbm4e_thermal_resistance_improvement_pct": 14.0,
    "hcb_thermal_resistance_improvement_pct": 20.0,
    "hcb_stage": "technology_showcase",
    "hpb_stage": "hbm4e_validation",
    "hpb_target_generation": "hbm5",
    "package_system_cooling_stage": "reported_review",
    "source": "조선비즈 + 삼성전자 공식자료 + TSMC 공식자료",
    "source_url": "https://biz.chosun.com/it-science/ict/2026/10/02/MHAFNCALYJDI5P3MKV3F3MXINE/?outputType=amp",
    "as_of": "2026-10-02",
    "note": "40배는 장비업계의 장기 전망으로 저장하고 삼성 HBM4E 확정 로드맵으로 승격하지 않음. TSMC 공식 CoWoS 로드맵은 2028년 14배, 2029년 14배 초과이며 40배는 SoW-X 별도 구조.",
}
RUBIN_ULTRA_HBM_OPTIONS_TRACK_VERSION = 2
RUBIN_ULTRA_HBM_OPTIONS_BASELINE = {
    "stage": "reported_evaluation",
    "candidate_options": ["HBM4E_12hi", "HBM4E_8hi", "HBM4_12hi", "HBM4_8hi"],
    "original_reported_option": "HBM4E_12hi",
    "reported_preferred_option": "HBM4_12hi",
    "previous_reported_preferred_option": "HBM4_8hi",
    "reported_preference_direction": "8hi_to_12hi_reversal",
    "reported_preference_stage": "single_industry_source",
    "reported_preference_support_sources": ["Damnang"],
    "reported_preference_source_url": "https://x.com/damnang2/status/2106970721612386304",
    "reported_preference_as_of": "2026-10-05",
    "reported_preference_direct_source_kind": "user_provided_x_quote",
    "reported_preference_direct_fetch_verified": False,
    "public_context_crosscheck": True,
    "public_context_source_url": "https://www.trendforce.com/presscenter/news/20260804-13166.html",
    "official_rubin_context_url": "https://developer.nvidia.com/blog/inside-nvidia-rubin-gpu-architecture-powering-the-era-of-agentic-ai/",
    "source": "매일경제 + TrendForce + 사용자 제공 Damnang X",
    "source_url": "https://www.mk.co.kr/news/business/12167424",
    "as_of": "2026-10-05",
    "note": "TrendForce는 Rubin Ultra가 HBM4E 12단·8단, HBM4 12단·8단을 병행 평가하며 최종 사양은 미정이라고 확인. 사용자 제공 Damnang X의 'HBM4 will have to go back to 12Hi instead of 8Hi'는 8단 우세론에서 12단 우세론으로의 단일 업계 신호로 저장하고 NVIDIA 최종 사양으로 승격하지 않음. X 직접 열람 검증은 미완료.",
}
SAMSUNG_NEXTGEN_HBM_TRACK_VERSION = 3
SAMSUNG_NEXTGEN_HBM_BASELINE = {
    "custom_hbm_stage": "official_sampling_plan",
    "custom_hbm_sample_start_year": 2027,
    "custom_hbm_customer_specific": True,
    "custom_hbm_interface_customization": True,
    "hbm5_customization_stage": "industry_expected",
    "zhbm_stage": "concept_development",
    "zhbm_customer_specific_design": True,
    "zhbm_performance_vs_hbm5_x": 8.0,
    "zhbm_energy_efficiency_vs_hbm5_x": 3.0,
    "zhbm_thermal_resistance_reduction_floor_pct": 50.0,
    "zhbm_memory_density_floor_vs_hbm5_x": 10.0,
    "source": "삼성전자 HBM4 공식자료 + FMS 2026 공식자료 + 매일경제",
    "source_url": "https://semiconductor.samsung.com/kr/news-events/news/samsung-ships-industry-first-commercial-hbm4-with-ultimate-performance-for-ai-computing/",
    "secondary_source_url": "https://www.mk.co.kr/news/business/12167424",
    "as_of": "2026-10-03",
    "note": "삼성 Custom HBM은 2027년부터 고객사별 사양에 맞춰 순차 샘플링을 시작한다는 공식 계획. HBM5 맞춤형 본격화는 업계 전망 단계. zHBM은 공식 콘셉트·개발 단계이며 확정 고객·계약·양산으로 승격하지 않음.",
}

NVHBM_ARCH_TRACK_VERSION = 1
NVHBM_ARCH_BASELINE = {
    "nvidia_stage": "official_announced",
    "feynman_custom_hbm_official": True,
    "first_collaborator": "Amazon Annapurna Labs",
    "memory_controller_location": "hbm_base_die",
    "bandwidth_gain_pct_max": 30.0,
    "compute_die_area_gain_pct_max": 25.0,
    "phy_support_area_reduction_pct_max": 67.0,
    "layout_usable_silicon_gain_pct_max": 80.0,
    "main_die_silicon_gain_pct_max": 30.0,
    "hbm_power_reduction_pct_max": 15.0,
    "xpu_end_to_end_performance_gain_pct_max": 30.0,
    "one_gw_additional_xpu_headroom_max": 15000,
    "official_memory_vendors": [],
    "rubin_hbm_logic_phy_die_share_estimate_pct": 16.0,
    "feynman_nvhbm_interface_die_share_estimate_pct": 4.0,
    "samsung_standard_hbm4_phy_width_mm": 8.0,
    "samsung_standard_hbm4_phy_height_mm": 4.0,
    "samsung_custom_d2d_width_mm": 8.5,
    "samsung_custom_d2d_height_mm": 1.5,
    "samsung_custom_d2d_area_reduction_pct_estimate": 60.15625,
    "official_source": "NVIDIA NVLink Fusion NVHBM Technical Blog",
    "official_source_url": "https://developer.nvidia.com/blog/nvidia-nvlink-fusion-brings-nvhbm-to-next-generation-ai-infrastructure/",
    "feynman_official_source_url": "https://images.nvidia.com/nvimages/gtc/pdf/GTC26_SanJose_Highlights_Final.pdf",
    "samsung_official_source_url": "https://semiconductor.samsung.com/foundry/application-specific-service/hpc-ai/",
    "research_source": "SemiAnalysis",
    "research_source_url": "https://newsletter.semianalysis.com/p/ectc2026",
    "as_of": "2026-10-03",
    "note": "NVIDIA 공식 수치와 SemiAnalysis 추정치를 분리 저장. Rubin 16%→Feynman 약 4% 및 Samsung PHY 8×4mm→D2D 8.5×1.5mm(약 60.2% 축소)는 SemiAnalysis 추정·Samsung Hot Chips 자료 인용이며 NVIDIA 공식 다이면적 실측치로 승격하지 않음. NVIDIA의 +25% compute die area와 상세 본문의 +30% main-die silicon은 서로 다른 공식 표현이라 합치지 않음.",
}
MORGAN_STANLEY_NVIDIA_HBM_MARGIN_TRACK_VERSION = 1
MORGAN_STANLEY_NVIDIA_HBM_MARGIN_BASELINE = {
    "gross_margin_floor_pct_reported": 72.0,
    "base_hbm_unit_price_tolerance_pct_reported": 91.7,
    "despec_hbm_unit_price_tolerance_pct_reported": 187.5,
    "exact_tolerance_public_source_verified": False,
    "full_spec_hbm_gb": OFFICIAL_RUBIN_GB,
    "despec_hbm_gb": RUMORED_ULTRA_GB,
    "derived_despec_tolerance_pct": ((1.0 + 91.7 / 100.0) * (OFFICIAL_RUBIN_GB / RUMORED_ULTRA_GB) - 1.0) * 100.0,
    "despec_math_consistent": True,
    "vr200_nvl72_rack_value_usd": 7803148.0,
    "vr200_memory_line_usd": 2001600.0,
    "vr200_memory_line_growth_pct": 435.0,
    "vr200_memory_line_share_pct": 25.65,
    "vr200_memory_line_scope": "public_recaps_conflict_on_hbm_inclusion_not_hbm_only_confirmed",
    "nvidia_q2_fy27_gross_margin_pct": 75.0,
    "nvidia_q3_fy27_gross_margin_outlook_mid_pct": 74.0,
    "nvidia_q3_fy27_gross_margin_outlook_plusminus_pct": 0.5,
    "morgan_stanley_next_year_gross_margin_range_low_pct": 72.0,
    "morgan_stanley_next_year_gross_margin_range_high_pct": 73.0,
    "morgan_stanley_next_year_gross_margin_estimate_pct": 72.5,
    "source_kind": "user_provided_morgan_stanley_summary_for_exact_tolerance",
    "source_url": "",
    "public_bom_source_url": "https://www.tomshardware.com/tech-industry/artificial-intelligence/nvidias-memory-costs-soar-485-percent-latest-ai-systems-now-cost-usd7-8-million-to-build-memory-now-comprises-25-percent-of-the-total-cost-rubin-gpus-a-mere-usd50-000-apiece",
    "public_bom_secondary_url": "https://longbridge.com/news/287728024",
    "nvidia_official_results_url": "https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-second-quarter-fiscal-2027/",
    "morgan_stanley_public_recap_url": "https://finance.yahoo.com/markets/stocks/articles/nvidia-delivers-strong-q2-long-150300603.html",
    "as_of": "2026-10-04",
    "note": "91.7%·187.5%·72% 조합은 사용자 제공 Morgan Stanley 요약으로 기준선에 보존하되, 공개 검색에서 원문 또는 exact 수치의 독립 2중 재확인은 아직 확보하지 못했으므로 exact_tolerance_public_source_verified=false. 187.5%는 288→192GB(-33.3%) 가정에서 91.7% 허용치를 용량비 1.5배로 조정하면 약 187.55%로 산술상 일치. VR200 $2.0016M memory line은 공개 2차 자료가 HBM 포함 여부를 다르게 설명하므로 HBM-only 비용으로 승격 금지.",
}

JPM_HBM_STRUCTURAL_TRACK_VERSION = 1
JPM_HBM_STRUCTURAL_BASELINE = {
    "demand_cagr_2026_2028_pct": 63.0,
    "demand_cagr_period": "2026-2028",
    "cumulative_bit_demand_2026_2028_billion_gb": 163.0,
    "asp_2027_yoy_pct": 54.0,
    "asp_2028_yoy_pct": 25.0,
    "asp_2028_usd_per_gb": 3.8,
    "supply_demand_gap_initial_pct": -20.0,
    "supply_demand_gap_later_pct": -16.0,
    "new_dram_capacity_to_hbm_pct_2025_2028": 58.0,
    "hbm_share_dram_capacity_start_pct": 19.0,
    "hbm_share_dram_capacity_2028_pct": 31.0,
    "sixteen_hi_earliest_year": 2029,
    "asic_hbm_demand_share_2027_pct": 48.0,
    "nvidia_hbm_demand_share_2027_pct": 43.0,
    "nvidia_hbm_demand_share_2026_pct": 58.0,
    "source": "J.P. Morgan 리서치 재인용 2곳 교차",
    "source_url": "https://www.itiger.com/news/1184910027",
    "secondary_source_url": "https://gmt8press.com/content/detail/434514",
    "as_of": "2026-09-23",
    "note": "63%는 2026~2028 HBM 비트수요 CAGR로 저장. 2027 단년 비트성장률로 재해석하거나 2027 ASP +54%와 곱해 2.5배 매출을 J.P. Morgan 확정치로 승격하지 않음.",
}
MICRON_SCA_TRACK_VERSION = 1
MICRON_SCA_BASELINE = {
    "sca_count": 26,
    "rpo_usd_bn": 150.0,
    "rpo_definition": "remaining_performance_obligations_sca_defined_pricing",
    "rpo_basis": "committed_volumes_minimum_pricing",
    "take_or_pay": True,
    "financial_commitments_usd_bn": 32.0,
    "financial_commitments_majority_cash_deposits": True,
    "rpo_and_financial_commitments_are_separate": True,
    "sca_revenue_coverage_through_2030_min_pct": 35.0,
    "defined_pricing_framework_share_pct": 75.0,
    "output_committed_2027_min_pct": 75.0,
    "output_committed_scope": "total_output_sca_and_non_sca",
    "hbm_2027_bit_supply_stage": "vast_majority_agreements_completed",
    "customer_discussion_focus_year": 2028,
    "sca_max_year": 2031,
    "source": "Micron FY2026 Q4 prepared remarks/call + Reuters",
    "source_url": "https://stockanalysis.com/stocks/mu/transcripts/699706-q4-2026/",
    "secondary_source_url": "https://www.reuters.com/business/micron-forecasts-quarterly-revenue-above-estimates-2026-09-30/",
    "official_source_url": "https://micron.gcs-web.com/node/50991",
    "as_of": "2026-09-30",
    "note": "RPO 1500억달러는 구매주문 총액이 아니라 가격 프레임워크가 확정된 SCA의 미인식 계약가치(최소가격 기준). 320억달러는 별도 고객 금융약정이며 대부분 현금예치금이므로 RPO와 합산 금지. 2027년 75%+는 Micron 전체 output 커밋으로, HBM 전용 수치와 분리.",
}
CITI_HBM_TRACK_VERSION = 1
CITI_HBM_BASELINE = {
    "demand_2027_yoy_pct": 62.0,
    "demand_2027_100m_gb": 752.0,
    "demand_2028_yoy_pct": 69.0,
    "demand_2028_100m_gb": 1270.0,
    "supply_2027_yoy_pct": 64.0,
    "supply_2027_100m_gb": 593.0,
    "supply_2028_yoy_pct": 36.0,
    "supply_2028_100m_gb": 809.0,
    "deficit_2027_pct": -21.0,
    "deficit_2028_pct": -36.0,
    "samsung_2027_wpm": 240000.0,
    "skhynix_2027_wpm": 270000.0,
    "micron_2027_wpm": 140000.0,
    "samsung_2027_capacity_yoy_pct": 50.0,
    "skhynix_2027_capacity_yoy_pct": 67.0,
    "micron_2027_capacity_yoy_pct": 52.0,
    "hbm4_12hi_usd_per_gb_min": 4.0,
    "hbm4_12hi_usd_per_gb_max": 5.0,
    "hbm4_12hi_price_yoy_min_pct": 100.0,
    "hbm4_12hi_price_yoy_max_pct": 150.0,
    "eight_hi_premium_min_pct": 20.0,
    "eight_hi_premium_max_pct": 30.0,
    "source": "Citi 리서치 재인용",
    "source_url": "https://www.aastocks.com/tc/stocks/news/aafn-con/NOW.1547209/latest-news/AAFN",
    "secondary_source_url": "https://newsis.com/view/NISX20260930_0003808711",
    "as_of": "2026-09-30",
}
STRUCTURE_BASELINE_VERSION = 3
KNOWN_STRUCTURE_FACT_KEYS = {
    "hbm_capacity_kv_offload_mainstream_8hi_12hi_niche_4hi",
    "bernstein_rubin_ultra_model_1024_to_640_8hi50_12hi50",
    "bernstein_hbm_supplier_relative_samsung_up_skhynix_down",
    "bernstein_hbm_supplier_relative_samsung_up",
    "bernstein_hbm_supplier_relative_skhynix_down",
}

QUERIES = [
    (
        "rubin_spec",
        '"Rubin Ultra" (HBM OR HBM4 OR HBM4E OR 192GB OR 288GB OR 1TB OR 8-Hi OR 12-Hi)',
    ),
    (
        "rubin_broker_model",
        '"Rubin Ultra" Bernstein (1024GB OR 640GB OR "8-Hi" OR "12-Hi" OR HBM)',
    ),
    (
        "hbm_supplier_relative",
        'Bernstein HBM Samsung share "SK hynix" progress pricing market share',
    ),
    (
        "hbm4e_validation",
        'HBM4E (qualification OR validation OR sample OR mass production OR production) (Samsung OR "SK hynix" OR Micron)',
    ),
    (
        "hbm_hybrid_bonding",
        '("SK hynix" OR SK하이닉스 OR Samsung OR 삼성전자) HBM ("hybrid bonding" OR 하이브리드본딩 OR "하이브리드 본딩") (sample OR 샘플 OR pilot OR 파일럿 OR validation OR 인증 OR 양산 OR difficulty OR 지연 OR 난항)',
    ),
    (
        "hbm4e_thermal_package",
        'Samsung HBM4E (thermal OR heat OR cooling OR HCB OR HPB OR "hybrid bonding" OR interposer OR reticle OR package OR 발열 OR 냉각 OR 하이브리드본딩 OR 하이브리드 본딩 OR 인터포저 OR 열저항 OR 패키지)',
    ),
    (
        "rubin_shipments",
        '"Rubin Ultra" (NVL576 OR shipment OR production OR deployment OR order OR ramp OR customer)',
    ),
    (
        "rubin_hbm_option_set",
        '("Rubin Ultra" OR 루빈 울트라 OR Damnang) (HBM4E OR HBM4) (8-Hi OR 8Hi OR 12-Hi OR 12Hi OR 8단 OR 12단) (evaluation OR evaluating OR final OR selected OR back OR revert OR instead OR switch OR 확정 OR 평가 OR 검토 OR 회귀 OR 복귀 OR 전환)',
    ),
    (
        "samsung_hbm4_price",
        'Samsung HBM4 2027 (price OR pricing OR contract OR negotiation OR annual supply OR sold out OR pricing power OR premium OR 4 dollars OR 3x OR triple OR 가격 OR 협상 OR 공급가 OR 완판 OR 협상력 OR 프리미엄)',
    ),
    (
        "samsung_nextgen_hbm",
        'Samsung ("Custom HBM" OR "custom HBM" OR HBM5 OR zHBM OR "커스텀 HBM" OR "맞춤형 HBM") (sample OR sampling OR customer-specific OR interface OR custom OR validation OR contract OR mass production OR performance OR power efficiency OR thermal OR 샘플 OR 샘플링 OR 고객사별 OR 인터페이스 OR 검증 OR 계약 OR 양산 OR 성능 OR 전력효율 OR 열저항)',
    ),
    (
        "nvhbm_architecture",
        '(NVHBM OR "custom HBM" OR "Custom HBM") (NVIDIA OR Feynman OR Rubin OR "Annapurna Labs" OR Samsung OR "SK hynix" OR Micron OR "memory controller" OR "base die" OR PHY OR "NV-HBI")',
    ),
    (
        "hbm_2027_contract",
        '2027 HBM (contract OR price OR pricing OR LTA OR supply OR allocation OR volume OR negotiation OR agreement) (Samsung OR "SK hynix" OR Micron OR NVIDIA)',
    ),
    (
        "morgan_stanley_nvidia_hbm_margin",
        '("Morgan Stanley" OR 모건스탠리) NVIDIA Rubin HBM ("gross margin" OR margin OR "price increase" OR "unit price" OR tolerance OR "de-spec" OR despec OR 91.7 OR 187.5 OR 72% OR 매출총이익률 OR 단가 OR 가격 OR 디스펙)',
    ),
    (
        "jpm_hbm_structural",
        '("J.P. Morgan" OR JPMorgan OR JP모건) HBM (63% OR 54% OR 31% OR 163 billion OR 1630억 OR shortage OR deficit OR capacity OR wafer OR ASP OR ASIC)',
    ),
    (
        "micron_sca_visibility",
        'Micron (SCA OR "strategic customer agreement" OR RPO OR "remaining performance obligations" OR "75% of output" OR "output committed" OR "32 billion" OR "150 billion" OR take-or-pay)',
    ),
    (
        "citi_hbm_outlook",
        'Citi HBM 2027 2028 (demand OR supply OR deficit OR shortage OR wafer OR WPM OR 12-Hi OR 8-Hi OR 752 OR 593 OR 1270 OR 809)',
    ),
    (
        "hbm_wafer_economics",
        '(HBM AND DDR5) (wafer revenue OR profitability OR economics OR "64GB RDIMM" OR 웨이퍼 매출 OR 수익성 OR 채산성) (TrendForce OR contract OR pricing OR allocation)',
    ),
    (
        "memory_migration",
        '(Rubin OR "Rubin Ultra" OR HBM) (DDR5 OR SOCAMM2 OR eSSD OR "enterprise SSD" OR "KV cache" OR offload OR pooling OR "8-Hi" OR "12-Hi" OR "4-Hi" OR 8단 OR 12단 OR 4단)',
    ),
    (
        "memory_migration",
        'TrendForce HBM "KV cache" (offload OR offloading OR HBF OR "SSD POD" OR CMX OR "8-Hi" OR "12-Hi" OR "4-Hi")',
    ),
]

CATEGORY_KO = {
    "rubin_spec": "Rubin Ultra 최종 HBM 사양",
    "rubin_broker_model": "Bernstein Rubin Ultra HBM 모델 가정",
    "hbm_supplier_relative": "삼성전자↔SK하이닉스 HBM 상대 변화",
    "hbm4e_validation": "HBM4E 고객 검증·양산",
    "hbm_hybrid_bonding": "별도 알림 · HBM 하이브리드 본딩 개발·고객 검증 격차",
    "hbm4e_thermal_package": "삼성 HBM4E 발열·인터포저·패키징 병목",
    "rubin_shipments": "Rubin Ultra·NVL576 실제 출하",
    "rubin_hbm_option_set": "별도 알림 · Rubin Ultra HBM4/HBM4E 옵션 변화",
    "samsung_hbm4_price": "삼성전자 2027 HBM4 계약가격·협상력",
    "samsung_nextgen_hbm": "별도 알림 · 삼성 Custom HBM·HBM5·zHBM 맞춤형 로드맵",
    "nvhbm_architecture": "별도 알림 · NVIDIA NVHBM·Custom HBM 구조 전환",
    "hbm_2027_contract": "2027 HBM 계약가격·물량",
    "morgan_stanley_nvidia_hbm_margin": "별도 알림 · Morgan Stanley NVIDIA HBM 가격 감내력·마진",
    "jpm_hbm_structural": "별도 알림 · J.P. Morgan HBM 구조적 수급·가격",
    "micron_sca_visibility": "별도 알림 · Micron 장기계약·RPO·예치금",
    "citi_hbm_outlook": "Citi HBM 2027~2028 수요·공급·가격",
    "hbm_wafer_economics": "HBM↔DDR5 웨이퍼 경제성",
    "memory_migration": "별도 알림 · HBM 용량 축소→KV 캐시 외부 메모리 전환",
}

OFFICIAL_SOURCE_HINTS = (
    "nvidia", "samsung newsroom", "삼성전자 뉴스룸", "samsung semiconductor", "semiconductor.samsung",
    "sk hynix", "sk하이닉스 뉴스룸", "micron technology", "micron newsroom",
)
TRUSTED_SOURCE_HINTS = (
    "trendforce", "reuters", "bloomberg", "the information", "semianalysis", "digitimes",
    "tom's hardware", "toms hardware", "financial times", "wall street journal", "wsj", "cnbc",
    "investing.com",
    "thelec", "the elec", "연합뉴스", "yonhap", "매일경제", "mk.co.kr",
    "yahoo finance", "mt newswires", "marketwatch", "investor's business daily", "investors.com",
    "damnang", "damnang research",
)
LOW_VALUE_SOURCE_HINTS = (
    "finance.biggo", "aol", "24/7 wall st", "247wallst", "cryptobriefing",
)


def fetch(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def rss_url(query: str, lang: str) -> str:
    q = urllib.parse.quote(query)
    if lang == "ko":
        return f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def parse_pubdate(value: str) -> datetime | None:
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo("Asia/Seoul"))
    except Exception:
        return None


def relevant(category: str, text: str) -> bool:
    low = text.lower()
    if category == "rubin_spec":
        return "rubin ultra" in low and any(k in low for k in ("hbm", "192gb", "288gb", "768gb", "1tb", "8-hi", "8hi", "12-hi", "12hi"))
    if category == "rubin_broker_model":
        return (
            "rubin ultra" in low
            and ("bernstein" in low or "伯恩斯坦" in text)
            and "hbm" in low
            and any(k in low for k in ("1024gb", "1,024gb", "640gb", "8-hi", "8hi", "12-hi", "12hi"))
        )
    if category == "hbm_supplier_relative":
        return (
            ("bernstein" in low or "伯恩斯坦" in text)
            and "hbm" in low
            and "samsung" in low
            and any(k in low for k in ("sk hynix", "sk하이닉스"))
            and any(k in low for k in ("share", "market share", "progress", "pricing", "점유율", "진척", "가격"))
        )
    if category == "hbm4e_validation":
        return "hbm4e" in low and any(k in low for k in ("samsung", "sk hynix", "sk하이닉스", "micron")) and any(k in low for k in ("qualification", "validation", "sample", "mass production", "production", "yield", "수율", "양산", "검증", "샘플"))
    if category == "hbm_hybrid_bonding":
        return (
            "hbm" in low
            and any(t in low for t in ("hybrid bonding", "hybrid copper bonding", "하이브리드 본딩", "하이브리드본딩"))
            and any(t in low for t in ("sk hynix", "sk하이닉스", "samsung", "삼성전자"))
            and any(t in low for t in ("sample", "샘플", "customer", "고객", "pilot", "파일럿", "mass production", "양산", "difficulty", "지연", "난항", "qualification", "검증", "bonding"))
        )
    if category == "hbm4e_thermal_package":
        return (
            ("samsung" in low or "삼성전자" in low or "삼성" in low)
            and "hbm4e" in low
            and any(k in low for k in (
                "thermal", "heat", "cooling", "hcb", "hpb", "hybrid bonding",
                "interposer", "reticle", "package", "발열", "냉각", "열저항",
                "하이브리드 본딩", "하이브리드본딩", "인터포저", "패키지",
            ))
        )
    if category == "rubin_shipments":
        return ("rubin ultra" in low or "nvl576" in low) and any(k in low for k in ("shipment", "ship", "production", "deployment", "order", "ramp", "customer", "출하", "양산", "도입", "주문"))
    if category == "rubin_hbm_option_set":
        has_layers = any(k in low for k in ("8-hi", "8hi", "8단")) and any(k in low for k in ("12-hi", "12hi", "12단"))
        reversal = (
            ("hbm4" in low or "hbm4e" in low)
            and has_layers
            and any(k in low for k in ("go back", "back to", "revert", "instead of", "switch back", "복귀", "회귀", "대신", "전환"))
        )
        regular = (
            ("rubin ultra" in low or "루빈 울트라" in low)
            and ("hbm4e" in low or "hbm4" in low)
            and any(k in low for k in ("8-hi", "8hi", "12-hi", "12hi", "8단", "12단"))
            and any(k in low for k in ("evaluation", "evaluating", "consider", "final", "selected", "평가", "검토", "확정", "선택"))
        )
        return regular or reversal
    if category == "samsung_hbm4_price":
        return (
            ("samsung" in low or "삼성전자" in low or "삼성" in low)
            and "hbm4" in low
            and any(k in low for k in ("2027", "내년", "next year"))
            and any(k in low for k in (
                "price", "pricing", "contract", "negotiation", "annual supply", "sold out",
                "pricing power", "premium", "가격", "공급가", "협상", "계약", "완판", "협상력", "프리미엄",
            ))
        )
    if category == "samsung_nextgen_hbm":
        return (
            ("samsung" in low or "삼성전자" in low or "삼성" in low)
            and any(k in low for k in ("custom hbm", "커스텀 hbm", "맞춤형 hbm", "hbm5", "zhbm"))
            and any(k in low for k in (
                "custom", "customer-specific", "concept", "mock-up", "mockup", "sample", "sampling", "validation",
                "contract", "mass production", "performance", "power efficiency", "thermal", "interface",
                "맞춤형", "커스텀", "콘셉트", "목업", "샘플", "샘플링", "검증", "계약", "양산", "성능", "전력효율", "열저항", "인터페이스",
            ))
        )
    if category == "nvhbm_architecture":
        return (
            ("nvhbm" in low or "custom hbm" in low or "커스텀 hbm" in low or "맞춤형 hbm" in low)
            and any(k in low for k in (
                "nvidia", "feynman", "rubin", "annapurna", "samsung", "sk hynix", "sk하이닉스", "micron",
                "memory controller", "메모리 컨트롤러", "base die", "베이스 다이", "phy", "nv-hbi", "bandwidth",
                "대역폭", "power", "전력", "die area", "다이 면적", "interface", "인터페이스",
            ))
        )
    if category == "hbm_2027_contract":
        return "2027" in low and "hbm" in low and any(k in low for k in ("contract", "price", "pricing", "lta", "supply", "allocation", "volume", "agreement", "negotiation", "계약", "가격", "공급", "물량", "협상", "타결"))
    if category == "morgan_stanley_nvidia_hbm_margin":
        return (
            ("morgan stanley" in low or "모건스탠리" in low)
            and ("nvidia" in low or "엔비디아" in low or "vr200" in low or "vera rubin" in low)
            and ("rubin" in low or "루빈" in low or "vera rubin" in low or "vr200" in low or "hbm" in low)
            and any(k in low for k in (
                "gross margin", "margin", "매출총이익률", "hbm", "price", "pricing", "단가", "가격",
                "tolerance", "감내", "de-spec", "despec", "디스펙", "91.7", "187.5", "72%",
                "memory", "메모리", "bom", "rack", "nvl72",
            ))
        )
    if category == "jpm_hbm_structural":
        return (
            ("j.p. morgan" in low or "jp morgan" in low or "jpmorgan" in low or "jp모건" in low)
            and "hbm" in low
            and any(k in low for k in ("2027", "2028"))
            and any(k in low for k in ("63%", "54%", "31%", "163", "shortage", "deficit", "capacity", "wafer", "asp", "asic", "부족", "생산능력", "웨이퍼", "가격"))
        )
    if category == "micron_sca_visibility":
        return (
            ("micron" in low or "마이크론" in low)
            and any(k in low for k in ("sca", "strategic customer agreement", "rpo", "remaining performance obligations", "take-or-pay", "75% of output", "output committed", "cash deposit", "financial commitments", "장기계약", "예치금"))
        )
    if category == "citi_hbm_outlook":
        return (
            ("citi" in low or "citigroup" in low or "씨티" in low or "花旗" in text)
            and "hbm" in low
            and any(k in low for k in ("2027", "2028"))
            and any(k in low for k in ("demand", "supply", "deficit", "shortage", "wafer", "wpm", "12-hi", "12hi", "8-hi", "8hi", "수요", "공급", "부족", "웨이퍼"))
        )
    if category == "hbm_wafer_economics":
        return "hbm" in low and "ddr5" in low and any(k in low for k in ("wafer revenue", "profitability", "economics", "64gb rdimm", "웨이퍼 매출", "수익성", "채산성"))
    if category == "memory_migration":
        return any(k in low for k in ("rubin", "hbm")) and any(k in low for k in ("ddr5", "socamm2", "essd", "enterprise ssd", "kv cache", "offload", "pooling", "오프로드", "풀링"))
    return False


def source_quality(source: str) -> str:
    low = (source or "").lower().strip()
    if any(k in low for k in OFFICIAL_SOURCE_HINTS):
        return "공식·회사자료"
    if any(k in low for k in TRUSTED_SOURCE_HINTS):
        return "신뢰 리서치·보도"
    return "일반 보도"


def quality_rank(value: str) -> int:
    if value.startswith("공식"):
        return 4
    if "Reuters" in value or value.startswith("신뢰"):
        return 3
    if value.startswith("교차검증"):
        return 2
    return 1


def normalized_title(title: str) -> str:
    value = clean_text(title).lower()
    if " - " in value:
        value = value.rsplit(" - ", 1)[0]
    value = re.sub(r"[^a-z0-9가-힣]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def event_id(category: str, title: str, link: str) -> str:
    raw = f"{category}|{title}|{link}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def is_fresh_for_send(event: dict, now: datetime) -> bool:
    raw = event.get("published_at_kst") or ""
    if not raw:
        return False
    try:
        dt = datetime.fromisoformat(raw)
    except Exception:
        return False
    return now - timedelta(hours=SEND_FRESHNESS_HOURS) <= dt <= now + timedelta(minutes=10)


def read_feed(category: str, query: str, lang: str) -> tuple[list[dict], list[str]]:
    errors: list[str] = []
    out: list[dict] = []
    url = rss_url(query, lang)
    try:
        root = ET.fromstring(fetch(url))
        for item in root.findall("./channel/item"):
            title = clean_text(item.findtext("title") or "")
            link = clean_text(item.findtext("link") or "")
            desc = clean_text(item.findtext("description") or "")
            pub = clean_text(item.findtext("pubDate") or "")
            source_node = item.find("source")
            source = clean_text(source_node.text if source_node is not None and source_node.text else "")
            text = f"{title} {desc}"
            if not title or not link or not relevant(category, text):
                continue
            dt = parse_pubdate(pub)
            out.append({
                "id": event_id(category, title, link),
                "category": category,
                "title": title,
                "link": link,
                "source": source or "출처 미표시",
                "published_at_kst": dt.isoformat(timespec="seconds") if dt else "",
                "description": desc[:900],
                "quality": source_quality(source),
                "lang": lang,
            })
    except Exception as e:
        errors.append(f"{category}/{lang}: {type(e).__name__}: {e}")
    return out, errors


def decode_google_news_url(link: str) -> str:
    if "news.google.com" not in (link or ""):
        return link
    if gnewsdecoder is None:
        return ""
    try:
        result = gnewsdecoder(link, interval=0.2)
        if isinstance(result, dict) and result.get("status"):
            decoded = str(result.get("decoded_url") or "").strip()
            if decoded.startswith("http") and "news.google.com" not in decoded:
                return decoded
    except Exception:
        pass
    return ""


def meta_content(raw_html: str, key: str) -> str:
    patterns = [
        rf'<meta[^>]+(?:property|name)=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']+)["\']',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{re.escape(key)}["\']',
    ]
    for pattern in patterns:
        m = re.search(pattern, raw_html, re.I)
        if m:
            return clean_text(m.group(1))
    return ""


def article_text_from_html(raw_html: str) -> str:
    value = re.sub(r"<(script|style|svg|noscript)[^>]*>.*?</\1>", " ", raw_html, flags=re.I | re.S)
    value = re.sub(r"<!--.*?-->", " ", value, flags=re.S)
    value = clean_text(value)
    return value[:16000]


def enrich_event(event: dict) -> dict:
    e = dict(event)
    direct = decode_google_news_url(e.get("link") or "")
    e["direct_link"] = direct
    e["link_verified"] = bool(direct)
    # URL decoding is NOT proof that an official article body was fetched.
    e["article_fetch_succeeded"] = False
    e["article_title"] = e.get("title") or ""
    e["article_description"] = e.get("description") or ""
    e["article_text"] = ""
    e["origin_source"] = e.get("source") or "출처 미표시"

    if not direct:
        return e

    try:
        raw = fetch(direct, timeout=18).decode("utf-8", errors="ignore")
        og_title = meta_content(raw, "og:title") or meta_content(raw, "twitter:title")
        desc = meta_content(raw, "og:description") or meta_content(raw, "description")
        body = article_text_from_html(raw)
        e["article_fetch_succeeded"] = True
        if og_title:
            e["article_title"] = og_title
        if desc:
            e["article_description"] = desc
        e["article_text"] = body

        source_low = (e.get("source") or "").lower()
        direct_host = (urlparse(direct).hostname or "").lower()
        body_low = body.lower()
        if "reuters" in body_low and "reuters" not in source_low:
            republisher = e.get("source") or direct_host
            e["origin_source"] = f"Reuters (재전재: {republisher})"
            e["quality"] = "신뢰 리서치·보도"
        elif "thelec" in direct_host:
            e["origin_source"] = "THE ELEC"
            e["quality"] = "신뢰 리서치·보도"
        elif "news.skhynix.com" in direct_host or "skhynix.com" in direct_host:
            e["origin_source"] = "SK하이닉스 공식자료"
            e["quality"] = "공식·회사자료"
    except Exception as ex:
        e["enrich_error"] = f"{type(ex).__name__}: {ex}"
    return e


def compact_fact_text(event: dict) -> str:
    return " ".join(
        x for x in (
            event.get("title") or "",
            event.get("description") or "",
            event.get("article_title") or "",
            event.get("article_description") or "",
            event.get("article_text") or "",
        ) if x
    )


def pct_tokens(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"[+-]?\d+(?:\.\d+)?%", text)))


def money_tokens(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"\$\s*\d+(?:\.\d+)?\s*(?:billion|million|B|M)\b", text, re.I)))



def _bernstein_rubin_model_values(text: str) -> tuple[int | None, int | None, int | None, int | None]:
    low = clean_text(text).lower().replace(",", "")
    old_gb = new_gb = None
    patterns = (
        r"(?:from|기존|종전|由)\s*(\d{3,4})\s*gb[^.]{0,90}?(?:to|에서|→|하향|下调至|降至)\s*(\d{3,4})\s*gb",
        r"(\d{3,4})\s*gb\s*(?:→|->|에서)\s*(\d{3,4})\s*gb",
    )
    for pat in patterns:
        m = re.search(pat, low, re.I)
        if m:
            old_gb, new_gb = int(m.group(1)), int(m.group(2))
            break
    if old_gb is None and "1024gb" in low and "640gb" in low:
        old_gb, new_gb = 1024, 640

    share_8 = share_12 = None
    has_8 = any(k in low for k in ("8-hi", "8hi", "8-layer", "8 layer", "8단", "8层"))
    has_12 = any(k in low for k in ("12-hi", "12hi", "12-layer", "12 layer", "12단", "12层"))
    half_split = any(k in low for k in ("half", "50%", "50 percent", "절반", "一半"))
    if has_8 and has_12 and half_split:
        share_8 = share_12 = 50
    return old_gb, new_gb, share_8, share_12


def _bernstein_supplier_relative_signature(text: str) -> str:
    low = clean_text(text).lower()
    if not (("bernstein" in low or "伯恩斯坦" in text) and "hbm" in low and "samsung" in low):
        return ""
    if not any(k in low for k in ("sk hynix", "sk하이닉스")):
        return ""
    samsung_up = any(k in low for k in ("gaining hbm share", "gain share", "share gain", "점유율 확대", "점유율 상승"))
    sk_down = (
        ("sk hynix" in low or "sk하이닉스" in low)
        and any(k in low for k in ("more conservative", "conservative assumptions", "progress and pricing", "진척", "가격 가정 하향", "목표주가 하향"))
    )
    if samsung_up and sk_down:
        return "bernstein_hbm_supplier_relative_samsung_up_skhynix_down"
    if samsung_up:
        return "bernstein_hbm_supplier_relative_samsung_up"
    if sk_down:
        return "bernstein_hbm_supplier_relative_skhynix_down"
    return ""



def _citi_pct(text: str, year: int, words: tuple[str, ...]) -> float | None:
    low = clean_text(text).lower()
    word = "(?:" + "|".join(re.escape(x.lower()) for x in words) + ")"
    for pat in (
        rf"{year}[^.%]{{0,140}}?{word}[^.%]{{0,120}}?([+-]?\d{{1,3}}(?:\.\d+)?)\s*%",
        rf"{word}[^.%]{{0,120}}?{year}[^.%]{{0,120}}?([+-]?\d{{1,3}}(?:\.\d+)?)\s*%",
    ):
        m = re.search(pat, low, re.I)
        if m:
            return float(m.group(1))
    return None


def _citi_100m_gb(text: str, year: int, words: tuple[str, ...]) -> float | None:
    low = clean_text(text).lower().replace(",", "")
    word = "(?:" + "|".join(re.escape(x.lower()) for x in words) + ")"
    for pat in (
        rf"{year}[^.]{{0,180}}?{word}[^.]{{0,160}}?(\d+(?:\.\d+)?)\s*(?:억|億)\s*gb",
        rf"{word}[^.]{{0,160}}?{year}[^.]{{0,160}}?(\d+(?:\.\d+)?)\s*(?:억|億)\s*gb",
    ):
        m = re.search(pat, low, re.I)
        if m:
            return float(m.group(1))
    for pat in (
        rf"{year}[^.]{{0,180}}?{word}[^.]{{0,160}}?(\d+(?:\.\d+)?)\s*billion\s*gb",
        rf"{word}[^.]{{0,160}}?{year}[^.]{{0,160}}?(\d+(?:\.\d+)?)\s*billion\s*gb",
    ):
        m = re.search(pat, low, re.I)
        if m:
            return float(m.group(1)) * 10.0
    return None


def _citi_wpm(text: str, aliases: tuple[str, ...]) -> float | None:
    low = clean_text(text).lower().replace(",", "")
    alias = "(?:" + "|".join(re.escape(x.lower()) for x in aliases) + ")"
    for pat in (
        rf"{alias}[^.]{{0,140}}?(\d+(?:\.\d+)?)\s*만\s*(?:장|wafers?)",
        rf"{alias}[^.]{{0,140}}?(\d+(?:\.\d+)?)\s*(?:k|thousand)\s*(?:wafers?)",
        rf"{alias}[^.]{{0,140}}?(\d{{5,6}})\s*(?:wpm|wafers?\s*per\s*month|wafers?/month)",
    ):
        m = re.search(pat, low, re.I)
        if m:
            value = float(m.group(1))
            if "만" in m.group(0):
                return value * 10000.0
            if re.search(r"(?:k|thousand)", m.group(0), re.I):
                return value * 1000.0
            return value
    return None


def _ms_nvidia_margin_math(base_tolerance_pct: float, full_gb: float, despec_gb: float) -> float:
    if full_gb <= 0 or despec_gb <= 0:
        raise ValueError("positive HBM capacities required")
    return ((1.0 + float(base_tolerance_pct) / 100.0) * (float(full_gb) / float(despec_gb)) - 1.0) * 100.0


def extract_morgan_stanley_nvidia_hbm_margin(event: dict) -> dict | None:
    text = compact_fact_text(event)
    low = text.lower()
    if not relevant("morgan_stanley_nvidia_hbm_margin", text):
        return None

    obs: dict = {}

    # Exact HBM unit-price tolerance. Require local HBM/price/tolerance context.
    for pat in (
        r"(?:hbm)[^.]{0,180}?(?:unit\s*price|price|pricing|단가|가격)[^.]{0,160}?(?:increase|rise|인상|상승|감내|tolerat)[^%]{0,80}?([0-9]+(?:\.[0-9]+)?)\s*%",
        r"([0-9]+(?:\.[0-9]+)?)\s*%[^.]{0,100}?(?:hbm)[^.]{0,140}?(?:unit\s*price|price|단가|가격)[^.]{0,100}?(?:increase|인상|감내|tolerat)",
    ):
        m = re.search(pat, low, re.I)
        if m:
            v = float(m.group(1))
            if 20.0 <= v <= 300.0:
                obs["base_hbm_unit_price_tolerance_pct_reported"] = v
                break

    # De-spec tolerance must appear in the same local clause as de-spec wording.
    for pat in (
        r"(?:de[- ]?spec|despec|디스펙)[^.]{0,180}?(?:hbm)[^.]{0,160}?(?:unit\s*price|price|단가|가격)?[^%]{0,120}?([0-9]+(?:\.[0-9]+)?)\s*%",
        r"(?:de[- ]?spec|despec|디스펙)[^.]{0,180}?([0-9]+(?:\.[0-9]+)?)\s*%[^.]{0,120}?(?:hbm|price|단가|가격|감내|tolerat)",
        r"([0-9]+(?:\.[0-9]+)?)\s*%[^.]{0,100}?(?:de[- ]?spec|despec|디스펙)[^.]{0,120}?(?:hbm|price|단가|가격|감내|tolerat)",
    ):
        m = re.search(pat, low, re.I)
        if m:
            v = float(m.group(1))
            if 50.0 <= v <= 400.0:
                obs["despec_hbm_unit_price_tolerance_pct_reported"] = v
                break

    # 72% is only eligible when tied to gross-margin floor/defense language.
    for pat in (
        r"(?:gross\s*margin|매출총이익률)[^.]{0,120}?(?:floor|lower\s*bound|하단|방어|유지)[^%]{0,60}?([0-9]+(?:\.[0-9]+)?)\s*%",
        r"([0-9]+(?:\.[0-9]+)?)\s*%[^.]{0,80}?(?:gross\s*margin|매출총이익률)[^.]{0,100}?(?:floor|lower\s*bound|하단|방어|유지)",
    ):
        m = re.search(pat, low, re.I)
        if m:
            v = float(m.group(1))
            if 50.0 <= v <= 90.0:
                obs["gross_margin_floor_pct_reported"] = v
                break

    # Capacity assumptions. Never infer 192GB from the tolerance percentages alone.
    full = re.search(r"(?:full[- ]?spec|standard|기존|원래|full)[^.]{0,100}?([0-9]{2,4})\s*gb[^.]{0,80}?(?:hbm)", low, re.I)
    if not full:
        full = re.search(r"(?:hbm)[^.]{0,80}?([0-9]{2,4})\s*gb[^.]{0,100}?(?:full[- ]?spec|standard|기존|원래)", low, re.I)
    despec = re.search(r"(?:de[- ]?spec|despec|디스펙)[^.]{0,120}?([0-9]{2,4})\s*gb", low, re.I)
    if full:
        obs["full_spec_hbm_gb"] = float(full.group(1))
    if despec:
        obs["despec_hbm_gb"] = float(despec.group(1))

    # Morgan Stanley VR200 rack value distribution. Keep "memory line" generic:
    # public secondary sources disagree on whether HBM is in this line or inside GPU.
    m = re.search(r"(?:vr200|vera\s+rubin)[^.]{0,180}?(?:rack|nvl72)[^.]{0,120}?(?:\$|usd\s*)?([0-9]+(?:\.[0-9]+)?)\s*(?:m|million)", low, re.I)
    if m:
        obs["vr200_nvl72_rack_value_usd"] = float(m.group(1)) * 1_000_000.0
    m = re.search(r"(?:memory|메모리)[^.]{0,120}?(?:\$|usd\s*)?([0-9]+(?:\.[0-9]+)?)\s*(?:m|million)", low, re.I)
    if m:
        obs["vr200_memory_line_usd"] = float(m.group(1)) * 1_000_000.0
        obs["vr200_memory_line_scope"] = "public_recaps_conflict_on_hbm_inclusion_not_hbm_only_confirmed"
    m = re.search(r"(?:memory|메모리)[^.]{0,120}?([0-9]+(?:\.[0-9]+)?)\s*%[^.]{0,80}?(?:increase|jump|rise|증가|급증)", low, re.I)
    if m:
        v = float(m.group(1))
        if 100.0 <= v <= 1000.0:
            obs["vr200_memory_line_growth_pct"] = v

    if not obs:
        return None

    full_gb = float(obs.get("full_spec_hbm_gb") or OFFICIAL_RUBIN_GB)
    despec_gb = float(obs.get("despec_hbm_gb") or RUMORED_ULTRA_GB)
    base = obs.get("base_hbm_unit_price_tolerance_pct_reported")
    if base is not None:
        derived = _ms_nvidia_margin_math(float(base), full_gb, despec_gb)
        obs["derived_despec_tolerance_pct"] = derived
        reported_despec = obs.get("despec_hbm_unit_price_tolerance_pct_reported")
        if reported_despec is not None:
            obs["despec_math_consistent"] = abs(float(reported_despec) - derived) <= 0.25

    obs.update({
        "source": event.get("origin_source") or event.get("source") or "",
        "source_url": event.get("direct_link") or "",
        "observed_at": event.get("published_at_kst") or "",
    })
    return obs


def merge_morgan_stanley_nvidia_hbm_margin(old: dict, obs: dict) -> dict:
    out = dict(old or {})
    for key, value in obs.items():
        if value not in (None, ""):
            out[key] = value
    return out


def morgan_stanley_nvidia_hbm_margin_changes(old: dict, new: dict) -> list[str]:
    reasons: list[str] = []
    for field, label, threshold in (
        ("gross_margin_floor_pct_reported", "매출총이익률 하단", 1.0),
        ("base_hbm_unit_price_tolerance_pct_reported", "풀스펙 HBM 단가 인상 감내폭", 10.0),
        ("despec_hbm_unit_price_tolerance_pct_reported", "디스펙 HBM 단가 인상 감내폭", 10.0),
    ):
        a, b = old.get(field), new.get(field)
        if a is not None and b is not None and abs(float(b) - float(a)) >= threshold:
            reasons.append(f"{label} {float(a):g}%→{float(b):g}%")
        elif a is None and b is not None:
            reasons.append(f"{label} {float(b):g}% 신규 확인")

    for field, label in (
        ("full_spec_hbm_gb", "풀스펙 HBM 용량"),
        ("despec_hbm_gb", "디스펙 HBM 용량"),
    ):
        a, b = old.get(field), new.get(field)
        if a is not None and b is not None and float(a) != float(b):
            reasons.append(f"{label} {float(a):g}→{float(b):g}GB")

    a, b = old.get("vr200_memory_line_usd"), new.get("vr200_memory_line_usd")
    if a and b:
        pct = (float(b) / float(a) - 1.0) * 100.0
        if abs(pct) >= 10.0:
            reasons.append(f"VR200 rack memory line {float(a)/1e6:.2f}→{float(b)/1e6:.2f}백만달러 ({pct:+.1f}%)")

    if old.get("exact_tolerance_public_source_verified") is not True and new.get("exact_tolerance_public_source_verified") is True:
        reasons.append("91.7%·187.5%·72% exact 수치 공개 원문/2중 출처 검증 완료")

    if new.get("despec_math_consistent") is False:
        reasons.append("디스펙 감내폭 산술 불일치 감지")
    return reasons


def morgan_stanley_nvidia_hbm_margin_event(state: dict, reasons: list[str]) -> dict:
    return {
        "category": "morgan_stanley_nvidia_hbm_margin",
        "fact_key": "morgan_stanley_nvidia_hbm_margin_" + hashlib.sha256(("|".join(reasons) + "|" + (state.get("observed_at") or state.get("as_of") or "")).encode()).hexdigest()[:16],
        "headline_ko": "Morgan Stanley NVIDIA HBM 가격 감내력·마진 변화",
        "fact_bullets": reasons,
        "verdict": (
            "HBM 단가 감내력은 NVIDIA의 가격·원가·매출총이익률 가정을 묶은 시나리오이며 HBM 공급사 확정 계약가격이 아닙니다. "
            "91.7%·187.5% exact 수치는 공개 원문 또는 독립 2중 출처가 확인될 때만 검증 완료로 승격합니다. "
            "VR200 약 200만달러 'memory' line은 공개 2차 자료가 HBM 포함 범위를 다르게 설명하므로 HBM-only 비용으로 사용하지 않습니다."
        ),
        "verification": "Morgan Stanley 원문 우선·exact 수치 2중 검증·NVIDIA 공식 마진 교차",
        "quality": "리서치 시나리오·공식 실적 분리",
        "origin_source": state.get("source") or "Morgan Stanley 관련 공개자료",
        "source": state.get("source") or "Morgan Stanley 관련 공개자료",
        "published_at_kst": state.get("observed_at") or state.get("as_of") or "",
        "direct_link": state.get("source_url") or state.get("morgan_stanley_public_recap_url") or "",
        "article_text": "",
        "morgan_stanley_nvidia_hbm_margin_state": state,
    }


def extract_jpm_hbm_structural(event: dict) -> dict | None:
    text = compact_fact_text(event)
    low = text.lower()
    if not relevant("jpm_hbm_structural", text):
        return None

    obs: dict = {}

    m = re.search(
        r"(?:cagr|compound[^.%]{0,40}?growth|복합[^.%]{0,40}?성장률|연평균[^.%]{0,40}?성장률)[^%]{0,100}?([0-9]+(?:\.[0-9]+)?)\s*%",
        low, re.I,
    )
    if m and "2026" in low and "2028" in low:
        obs["demand_cagr_2026_2028_pct"] = float(m.group(1))
        obs["demand_cagr_period"] = "2026-2028"

    m = re.search(
        r"(?:cumulative|누적)[^.]{0,100}?(?:bit\s+demand|비트\s*수요)[^0-9]{0,40}?([0-9]+(?:\.[0-9]+)?)\s*(?:billion\s*gb|십억\s*gb)",
        low, re.I,
    )
    if not m:
        m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*billion\s*gb[^.]{0,80}?(?:cumulative|누적)", low, re.I)
    if m:
        obs["cumulative_bit_demand_2026_2028_billion_gb"] = float(m.group(1))

    for year in (2027, 2028):
        m = re.search(
            rf"([+-]?\d+(?:\.\d+)?)\s*%\s*(?:y/?y\s*)?(?:in|for|during|\(|,)?\s*{year}",
            low, re.I,
        )
        if not m:
            m = re.search(
                rf"{year}[^.%]{{0,100}}?(?:hbm[^.%]{{0,50}}?)?(?:asp|average selling price|평균판매단가|가격)[^%]{{0,80}}?([+-]?\d+(?:\.\d+)?)\s*%",
                low, re.I,
            )
        if not m:
            # 마지막 보조패턴은 같은 문장 안에서 해당 연도와 가장 가까운 ASP 증가율을 찾는다.
            sentence_candidates = [
                part for part in re.split(r"[.!?]", low)
                if str(year) in part and any(k in part for k in ("asp", "average selling price", "평균판매단가", "가격"))
            ]
            for part in sentence_candidates:
                near = re.search(rf"([+-]?\d+(?:\.\d+)?)\s*%[^%]{{0,45}}?(?:in|for)?\s*{year}", part, re.I)
                if near:
                    m = near
                    break
        if m:
            obs[f"asp_{year}_yoy_pct"] = float(m.group(1))

    m = re.search(r"(?:2028)[^.]{0,120}?(?:\$|usd\s*)?([0-9]+(?:\.[0-9]+)?)\s*(?:per\s*gb|/\s*gb|달러\s*/?\s*gb)", low, re.I)
    if m:
        obs["asp_2028_usd_per_gb"] = float(m.group(1))

    m = re.search(
        r"(?:supply[- ]?demand|수급)[^.]{0,160}?(-?\d+(?:\.\d+)?)\s*%[^.]{0,120}?(?:to|→|에서)[^0-9-]{0,20}(-?\d+(?:\.\d+)?)\s*%",
        low, re.I,
    )
    if m:
        obs["supply_demand_gap_initial_pct"] = float(m.group(1))
        obs["supply_demand_gap_later_pct"] = float(m.group(2))

    m = re.search(
        r"([0-9]+(?:\.[0-9]+)?)\s*%[^.]{0,100}?(?:new\s+dram\s+capacity|신규\s*dram\s*생산능력)[^.]{0,100}?(?:hbm|allocated|directed)",
        low, re.I,
    )
    if not m:
        m = re.search(
            r"(?:new\s+dram\s+capacity|신규\s*dram\s*생산능력)[^.]{0,120}?([0-9]+(?:\.[0-9]+)?)\s*%[^.]{0,80}?(?:hbm)",
            low, re.I,
        )
    if m:
        obs["new_dram_capacity_to_hbm_pct_2025_2028"] = float(m.group(1))

    m = re.search(
        r"(?:hbm)[^.]{0,140}?(?:share|비중)[^.]{0,120}?([0-9]+(?:\.[0-9]+)?)\s*%[^.]{0,100}?(?:to|→|에서)[^0-9]{0,20}([0-9]+(?:\.[0-9]+)?)\s*%",
        low, re.I,
    )
    if not m:
        m = re.search(
            r"(?:from)[^0-9]{0,20}([0-9]+(?:\.[0-9]+)?)\s*%[^.]{0,100}?(?:to)[^0-9]{0,20}([0-9]+(?:\.[0-9]+)?)\s*%[^.]{0,120}?(?:dram\s+capacity|capacity)",
            low, re.I,
        )
    if m:
        obs["hbm_share_dram_capacity_start_pct"] = float(m.group(1))
        obs["hbm_share_dram_capacity_2028_pct"] = float(m.group(2))

    m = re.search(r"(?:16\s*[- ]?hi|16단)[^.]{0,140}?(?:2029)", low, re.I)
    if m:
        obs["sixteen_hi_earliest_year"] = 2029

    for label, field in (("asic", "asic_hbm_demand_share_2027_pct"), ("nvidia", "nvidia_hbm_demand_share_2027_pct")):
        m = re.search(rf"2027[^.%]{{0,120}}?{label}[^%]{{0,80}}?([0-9]+(?:\.\d+)?)\s*%", low, re.I)
        if not m:
            for part in re.split(r"[.!?]", low):
                if "2027" not in part or label not in part:
                    continue
                near = re.search(rf"{label}[^%]{{0,100}}?([0-9]+(?:\.\d+)?)\s*%", part, re.I)
                if near:
                    m = near
                    break
        if not m:
            m = re.search(rf"{label}[^.%]{{0,120}}?([0-9]+(?:\.\d+)?)\s*%[^.]{{0,100}}?2027", low, re.I)
        if m:
            obs[field] = float(m.group(1))

    if not obs:
        return None
    obs.update({
        "source": event.get("origin_source") or event.get("source") or "J.P. Morgan 관련 재인용",
        "source_url": event.get("direct_link") or "",
        "as_of": (event.get("published_at_kst") or "")[:10],
        "observed_at": event.get("published_at_kst") or "",
    })
    return obs


def merge_jpm_hbm_structural(old: dict, obs: dict) -> dict:
    merged = dict(old or {})
    for key, value in obs.items():
        if value not in (None, ""):
            merged[key] = value
    return merged


def jpm_hbm_structural_changes(old: dict, new: dict) -> list[str]:
    changes: list[str] = []
    for key, label, threshold, unit in (
        ("demand_cagr_2026_2028_pct", "2026~2028 HBM 비트수요 CAGR", 5.0, "%"),
        ("asp_2027_yoy_pct", "2027 HBM 평균판매단가 증가율", 5.0, "%"),
        ("asp_2028_yoy_pct", "2028 HBM 평균판매단가 증가율", 5.0, "%"),
        ("hbm_share_dram_capacity_2028_pct", "2028 HBM의 DRAM 생산능력 비중", 2.0, "%"),
        ("new_dram_capacity_to_hbm_pct_2025_2028", "2025~2028 신규 DRAM 생산능력의 HBM 배분 비중", 5.0, "%"),
        ("supply_demand_gap_later_pct", "HBM 수급 부족률 후반값", 3.0, "%"),
        ("asic_hbm_demand_share_2027_pct", "2027 ASIC HBM 수요 비중", 3.0, "%"),
        ("nvidia_hbm_demand_share_2027_pct", "2027 NVIDIA HBM 수요 비중", 3.0, "%"),
        ("asp_2028_usd_per_gb", "2028 HBM 평균판매단가", 0.3, "달러/Gb"),
    ):
        a, b = old.get(key), new.get(key)
        if a is not None and b is not None and abs(float(b) - float(a)) >= threshold:
            changes.append(f"{label} {float(a):g}→{float(b):g}{unit}")
        elif a is None and b is not None:
            changes.append(f"{label} {float(b):g}{unit} 신규 확인")

    a, b = old.get("cumulative_bit_demand_2026_2028_billion_gb"), new.get("cumulative_bit_demand_2026_2028_billion_gb")
    if a and b and abs(float(b) / float(a) - 1.0) >= 0.10:
        changes.append(f"2026~2028 누적 HBM 비트수요 {float(a):g}→{float(b):g}십억 GB")

    if old.get("sixteen_hi_earliest_year") != new.get("sixteen_hi_earliest_year") and new.get("sixteen_hi_earliest_year"):
        changes.append(f"16단 상용화 최소 시점 {old.get('sixteen_hi_earliest_year') or '미확인'}→{new.get('sixteen_hi_earliest_year')}")
    return changes


def jpm_hbm_structural_event(state: dict, changes: list[str]) -> dict:
    return {
        "category": "jpm_hbm_structural",
        "fact_key": "jpm_hbm_structural_" + (state.get("observed_at") or state.get("as_of") or ""),
        "headline_ko": "J.P. Morgan HBM 구조적 수급·가격 전망 변화",
        "fact_bullets": changes,
        "verdict": (
            "63%는 2026~2028 비트수요 CAGR이고 54%는 2027 평균판매단가 증가율이므로 서로 다른 기간 기준입니다. "
            "두 수치를 곱해 2027 매출 2.5배를 J.P. Morgan 확정 전망으로 자동 계산하지 않습니다."
        ),
        "verification": "J.P. Morgan 재인용 2곳 이상 또는 직접 출처",
        "quality": "리서치 재인용 교차",
        "origin_source": state.get("source") or "J.P. Morgan",
        "source": state.get("source") or "J.P. Morgan",
        "published_at_kst": state.get("observed_at") or state.get("as_of") or "",
        "direct_link": state.get("source_url") or "",
        "article_text": "",
        "jpm_hbm_state": state,
    }


def extract_micron_sca_visibility(event: dict) -> dict | None:
    text = compact_fact_text(event)
    low = text.lower()
    if not relevant("micron_sca_visibility", text):
        return None

    obs: dict = {}

    m = re.search(r"(?:signed|total|총)[^.]{0,80}?([0-9]{1,3})\s*(?:scas?|strategic customer agreements?|전략적 고객 계약)", low, re.I)
    if not m:
        m = re.search(r"([0-9]{1,3})\s*(?:signed\s+)?(?:scas?|strategic customer agreements?)", low, re.I)
    if m:
        obs["sca_count"] = int(m.group(1))

    m = re.search(r"(?:remaining performance obligations?|\brpo\b)[^$0-9]{0,80}?\$?\s*([0-9]+(?:\.[0-9]+)?)\s*billion", low, re.I)
    if m:
        obs["rpo_usd_bn"] = float(m.group(1))
        obs["rpo_definition"] = "remaining_performance_obligations_sca_defined_pricing"

    m = re.search(r"(?:financial commitments?|customer commitments?)[^$0-9]{0,100}?\$?\s*([0-9]+(?:\.[0-9]+)?)\s*billion", low, re.I)
    if m:
        obs["financial_commitments_usd_bn"] = float(m.group(1))
    if "cash deposit" in low or "cash deposits" in low:
        if any(k in low for k in ("vast majority", "mostly", "대부분")):
            obs["financial_commitments_majority_cash_deposits"] = True

    if "take-or-pay" in low or "take or pay" in low:
        obs["take_or_pay"] = True
    if any(k in low for k in ("minimum pricing", "floor prices", "price floor", "minimum price")):
        obs["rpo_basis"] = "committed_volumes_minimum_pricing"

    m = re.search(r"(?:over|more than|greater than|약|약간 넘는)\s*([0-9]+(?:\.[0-9]+)?)\s*%[^.]{0,120}?(?:revenue)[^.]{0,80}?(?:2030)", low, re.I)
    if not m:
        m = re.search(r"(?:revenue)[^.]{0,120}?(?:2030)[^%]{0,100}?(?:over|more than)?\s*([0-9]+(?:\.[0-9]+)?)\s*%", low, re.I)
    if m:
        obs["sca_revenue_coverage_through_2030_min_pct"] = float(m.group(1))

    if any(k in low for k in ("three-quarters", "three quarters", "75%")) and any(k in low for k in ("defined pricing", "pricing framework", "가격 프레임워크")):
        obs["defined_pricing_framework_share_pct"] = 75.0

    m = re.search(r"(?:2027)[^.]{0,140}?(?:more than|over|greater than)[^0-9]{0,20}([0-9]+(?:\.[0-9]+)?)\s*%[^.]{0,100}?(?:output|생산량)[^.]{0,80}?(?:committed|확보|약정)", low, re.I)
    if not m:
        m = re.search(r"(?:more than|over|greater than)[^0-9]{0,20}([0-9]+(?:\.[0-9]+)?)\s*%[^.]{0,120}?(?:output|생산량)[^.]{0,100}?2027", low, re.I)
    if m:
        obs["output_committed_2027_min_pct"] = float(m.group(1))
        obs["output_committed_scope"] = "total_output_sca_and_non_sca"

    if (
        "2027" in low and "hbm" in low
        and any(k in low for k in ("vast majority", "대부분", "대다수"))
        and any(k in low for k in ("completed agreements", "agreements for", "계약", "협의"))
    ):
        obs["hbm_2027_bit_supply_stage"] = "vast_majority_agreements_completed"

    if "2028" in low and any(k in low for k in ("majority of discussions", "discussions with customers", "customer discussions", "논의")):
        obs["customer_discussion_focus_year"] = 2028

    if "2031" in low and any(k in low for k in ("sca", "agreement", "agreements", "계약")):
        obs["sca_max_year"] = 2031

    if not obs:
        return None
    obs.update({
        "rpo_and_financial_commitments_are_separate": True,
        "source": event.get("origin_source") or event.get("source") or "Micron 관련 자료",
        "source_url": event.get("direct_link") or "",
        "as_of": (event.get("published_at_kst") or "")[:10],
        "observed_at": event.get("published_at_kst") or "",
    })
    return obs


def merge_micron_sca_visibility(old: dict, obs: dict) -> dict:
    merged = dict(old or {})
    for key, value in obs.items():
        if value not in (None, ""):
            merged[key] = value
    return merged


def micron_sca_visibility_changes(old: dict, new: dict) -> list[str]:
    changes: list[str] = []
    for key, label, threshold, unit in (
        ("rpo_usd_bn", "RPO", 10.0, "십억달러"),
        ("financial_commitments_usd_bn", "고객 금융약정", 5.0, "십억달러"),
        ("output_committed_2027_min_pct", "2027 전체 output 커밋 하한", 5.0, "%"),
        ("sca_revenue_coverage_through_2030_min_pct", "2030년까지 SCA 매출커버리지 하한", 5.0, "%"),
        ("defined_pricing_framework_share_pct", "가격 프레임워크 확정 SCA 매출비중", 10.0, "%"),
    ):
        a, b = old.get(key), new.get(key)
        if a is not None and b is not None and abs(float(b) - float(a)) >= threshold:
            changes.append(f"{label} {float(a):g}→{float(b):g}{unit}")
        elif a is None and b is not None:
            changes.append(f"{label} {float(b):g}{unit} 신규 확인")

    a, b = old.get("sca_count"), new.get("sca_count")
    if a is not None and b is not None and int(a) != int(b):
        changes.append(f"SCA 건수 {int(a)}→{int(b)}건")
    elif a is None and b is not None:
        changes.append(f"SCA {int(b)}건 신규 확인")

    for key, label in (
        ("hbm_2027_bit_supply_stage", "2027 HBM 비트공급 계약 단계"),
        ("output_committed_scope", "2027 커밋 범위"),
    ):
        if old.get(key) != new.get(key) and new.get(key):
            changes.append(f"{label} {old.get(key) or '미확인'}→{new.get(key)}")

    for key, label in (
        ("customer_discussion_focus_year", "고객 협의 중심연도"),
        ("sca_max_year", "SCA 최대 계약연도"),
    ):
        if old.get(key) != new.get(key) and new.get(key):
            changes.append(f"{label} {old.get(key) or '미확인'}→{new.get(key)}")
    return changes


def micron_sca_visibility_event(state: dict, changes: list[str]) -> dict:
    return {
        "category": "micron_sca_visibility",
        "fact_key": "micron_sca_visibility_" + (state.get("observed_at") or state.get("as_of") or ""),
        "headline_ko": "Micron 장기계약·RPO·고객 예치금 상태 변화",
        "fact_bullets": changes,
        "verdict": (
            "RPO는 구매주문 금액이 아니라 가격 프레임워크가 확정된 SCA의 잔존 이행의무이며 최소가격 기준입니다. "
            "고객 금융약정 320억달러는 별도 항목이고 대부분 현금예치금이므로 RPO 1500억달러와 합산하지 않습니다. "
            "2027년 75%+ 커밋은 전체 output 범위이며, HBM은 별도로 '대부분의 2027 비트공급 계약 완료'로 관리합니다."
        ),
        "verification": "Micron 공식/실적콜·Reuters 교차",
        "quality": "공식자료·신뢰보도 교차",
        "origin_source": state.get("source") or "Micron",
        "source": state.get("source") or "Micron",
        "published_at_kst": state.get("observed_at") or state.get("as_of") or "",
        "direct_link": state.get("source_url") or "",
        "article_text": "",
        "micron_sca_state": state,
    }


def extract_citi_hbm_outlook(event: dict) -> dict | None:
    text = compact_fact_text(event)
    low = text.lower()
    if not relevant("citi_hbm_outlook", text):
        return None
    obs: dict = {}
    for year in (2027, 2028):
        obs[f"demand_{year}_yoy_pct"] = _citi_pct(text, year, ("demand", "수요", "需求"))
        obs[f"supply_{year}_yoy_pct"] = _citi_pct(text, year, ("supply", "공급", "供給", "供应"))
        obs[f"deficit_{year}_pct"] = _citi_pct(text, year, ("deficit", "shortage", "공급부족률", "공급 부족률", "缺口", "短缺"))
        obs[f"demand_{year}_100m_gb"] = _citi_100m_gb(text, year, ("demand", "수요", "需求"))
        obs[f"supply_{year}_100m_gb"] = _citi_100m_gb(text, year, ("supply", "공급", "供給", "供应"))
    obs["samsung_2027_wpm"] = _citi_wpm(text, ("samsung", "삼성전자", "삼성"))
    obs["skhynix_2027_wpm"] = _citi_wpm(text, ("sk hynix", "sk하이닉스", "하이닉스"))
    obs["micron_2027_wpm"] = _citi_wpm(text, ("micron", "마이크론"))
    for field, aliases in (
        ("samsung_2027_capacity_yoy_pct", ("samsung", "삼성전자", "삼성")),
        ("skhynix_2027_capacity_yoy_pct", ("sk hynix", "sk하이닉스", "하이닉스")),
        ("micron_2027_capacity_yoy_pct", ("micron", "마이크론")),
    ):
        alias = "(?:" + "|".join(re.escape(x.lower()) for x in aliases) + ")"
        m = re.search(rf"{alias}[^.%]{{0,120}}?2027[^.%]{{0,120}}?([+-]?\d{{1,3}}(?:\.\d+)?)\s*%", low, re.I)
        if not m:
            m = re.search(rf"{alias}[^.%]{{0,160}}?([+-]?\d{{1,3}}(?:\.\d+)?)\s*%[^.]{{0,80}}?(?:2027|yoy)", low, re.I)
        obs[field] = float(m.group(1)) if m else None
    price = re.search(
        r"(?:hbm4[^.]{0,80}?12\s*[- ]?(?:hi|단)|12\s*[- ]?(?:hi|단)[^.]{0,80}?hbm4)[^$\d]{0,80}?\$?\s*(\d+(?:\.\d+)?)\s*(?:~|[-–—]|to)\s*\$?\s*(\d+(?:\.\d+)?)\s*/?\s*gb",
        low, re.I,
    )
    if price:
        obs["hbm4_12hi_usd_per_gb_min"] = float(price.group(1))
        obs["hbm4_12hi_usd_per_gb_max"] = float(price.group(2))
    price_yoy = re.search(
        r"(?:hbm4[^.]{0,100}?12\s*[- ]?(?:hi|단)|12\s*[- ]?(?:hi|단)[^.]{0,100}?hbm4)[^%]{0,180}?(\d{2,3})\s*(?:~|[-–—]|to)\s*(\d{2,3})\s*%",
        low, re.I,
    )
    if price_yoy:
        obs["hbm4_12hi_price_yoy_min_pct"] = float(price_yoy.group(1))
        obs["hbm4_12hi_price_yoy_max_pct"] = float(price_yoy.group(2))
    premium = re.search(
        r"8\s*[- ]?(?:hi|단)[^.]{0,160}?12\s*[- ]?(?:hi|단)[^.]{0,160}?(\d{1,2})\s*(?:~|[-–—]|to)\s*(\d{1,2})\s*%[^.]{0,80}?(?:higher|premium|높|비싸)",
        low, re.I,
    )
    if premium:
        obs["eight_hi_premium_min_pct"] = float(premium.group(1))
        obs["eight_hi_premium_max_pct"] = float(premium.group(2))
    if not any(v is not None for v in obs.values()):
        return None
    obs.update({
        "source": event.get("origin_source") or event.get("source") or "Citi 관련 보도",
        "source_url": event.get("direct_link") or event.get("link") or "",
        "as_of": (event.get("published_at_kst") or "")[:10],
        "observed_at": event.get("published_at_kst") or "",
    })
    return obs


def merge_citi_hbm_outlook(old: dict, obs: dict) -> dict:
    if old.get("as_of") and obs.get("as_of") and obs["as_of"] < old["as_of"]:
        return dict(old)
    merged = dict(old or {})
    for key, value in obs.items():
        if value is not None and value != "":
            merged[key] = value
    return merged


def citi_hbm_material_changes(old: dict, new: dict) -> list[str]:
    changes: list[str] = []
    for year in (2027, 2028):
        for kind, label in (("demand", "수요 증가율"), ("supply", "공급 증가율")):
            key = f"{kind}_{year}_yoy_pct"
            a, b = old.get(key), new.get(key)
            if a is not None and b is not None and abs(float(b) - float(a)) >= 10:
                changes.append(f"{year}년 {label} {float(a):+.0f}%→{float(b):+.0f}% ({float(b)-float(a):+.0f}%p)")
        key = f"deficit_{year}_pct"
        a, b = old.get(key), new.get(key)
        if a is not None and b is not None and abs(float(b) - float(a)) >= 5:
            changes.append(f"{year}년 수급 부족률 {float(a):+.0f}%→{float(b):+.0f}% ({float(b)-float(a):+.0f}%p)")
        for kind, label in (("demand", "수요"), ("supply", "공급")):
            key = f"{kind}_{year}_100m_gb"
            a, b = old.get(key), new.get(key)
            if a and b and abs(float(b) / float(a) - 1.0) >= 0.10:
                changes.append(f"{year}년 {label} {float(a):,.0f}억→{float(b):,.0f}억 Gb")
    for key, label in (
        ("samsung_2027_wpm", "삼성전자"),
        ("skhynix_2027_wpm", "SK하이닉스"),
        ("micron_2027_wpm", "Micron"),
    ):
        a, b = old.get(key), new.get(key)
        if a and b and abs(float(b) / float(a) - 1.0) >= 0.10:
            changes.append(f"{label} 2027 월 웨이퍼 생산능력 {float(a):,.0f}→{float(b):,.0f}장")
    for key, label in (
        ("samsung_2027_capacity_yoy_pct", "삼성전자 생산능력 증가율"),
        ("skhynix_2027_capacity_yoy_pct", "SK하이닉스 생산능력 증가율"),
        ("micron_2027_capacity_yoy_pct", "Micron 생산능력 증가율"),
        ("hbm4_12hi_price_yoy_min_pct", "HBM4 12단 가격 상승률 하단"),
        ("hbm4_12hi_price_yoy_max_pct", "HBM4 12단 가격 상승률 상단"),
    ):
        a, b = old.get(key), new.get(key)
        if a is not None and b is not None and abs(float(b) - float(a)) >= 10:
            changes.append(f"{label} {float(a):.0f}%→{float(b):.0f}%")
    for key, label in (
        ("hbm4_12hi_usd_per_gb_min", "HBM4 12단 가격 하단"),
        ("hbm4_12hi_usd_per_gb_max", "HBM4 12단 가격 상단"),
    ):
        a, b = old.get(key), new.get(key)
        if a is not None and b is not None and abs(float(b) - float(a)) >= 0.5:
            changes.append(f"{label} {float(a):.1f}→{float(b):.1f}달러/Gb")
    for key, label in (
        ("eight_hi_premium_min_pct", "8단 프리미엄 하단"),
        ("eight_hi_premium_max_pct", "8단 프리미엄 상단"),
    ):
        a, b = old.get(key), new.get(key)
        if a is not None and b is not None and abs(float(b) - float(a)) >= 5:
            changes.append(f"{label} {float(a):.0f}%→{float(b):.0f}%")
    return changes


def citi_hbm_change_event(state: dict, changes: list[str]) -> dict:
    bullets = [
        f"• 수요: 2027년 +{state.get('demand_2027_yoy_pct', 0):.0f}% · {state.get('demand_2027_100m_gb', 0):,.0f}억 Gb / 2028년 +{state.get('demand_2028_yoy_pct', 0):.0f}% · {state.get('demand_2028_100m_gb', 0):,.0f}억 Gb",
        f"• 공급: 2027년 +{state.get('supply_2027_yoy_pct', 0):.0f}% · {state.get('supply_2027_100m_gb', 0):,.0f}억 Gb / 2028년 +{state.get('supply_2028_yoy_pct', 0):.0f}% · {state.get('supply_2028_100m_gb', 0):,.0f}억 Gb",
        f"• 수급 부족률: 2027년 {state.get('deficit_2027_pct', 0):+.0f}% → 2028년 {state.get('deficit_2028_pct', 0):+.0f}%",
        f"• 2027 월 웨이퍼 생산능력: 삼성전자 {state.get('samsung_2027_wpm', 0):,.0f}장(+{state.get('samsung_2027_capacity_yoy_pct', 0):.0f}%) / SK하이닉스 {state.get('skhynix_2027_wpm', 0):,.0f}장(+{state.get('skhynix_2027_capacity_yoy_pct', 0):.0f}%) / Micron {state.get('micron_2027_wpm', 0):,.0f}장(+{state.get('micron_2027_capacity_yoy_pct', 0):.0f}%)",
        f"• 8단 Gb당 프리미엄: 12단 대비 +{state.get('eight_hi_premium_min_pct', 0):.0f}~{state.get('eight_hi_premium_max_pct', 0):.0f}%",
        "• 이번 변화: " + " · ".join(changes),
    ]
    return {
        "id": "typed|citi_hbm_outlook",
        "category": "citi_hbm_outlook",
        "headline_ko": "Citi HBM 수급·가격 전망 상태 변화",
        "fact_bullets": bullets,
        "verdict": "Citi 전망은 TrendForce 시장 Blended ASP와 별도 관리합니다. 수요·공급·가격·생산능력의 실제 수정만 재알림합니다.",
        "verification": "Citi 리서치 재인용 상태값",
        "origin_source": state.get("source") or "Citi",
        "source": state.get("source") or "Citi",
        "published_at_kst": state.get("observed_at") or state.get("as_of") or "",
        "direct_link": state.get("source_url") or "",
        "article_text": "",
        "citi_state": state,
    }

SAMSUNG_HBM4_STAGE_RANK = {
    "reported_offer": 0,
    "negotiation": 1,
    "final_stage": 2,
    "signed": 3,
}


def _relative_month_from_event(event: dict) -> str:
    stamp = event.get("published_at_kst") or ""
    try:
        dt = datetime.fromisoformat(stamp)
        return f"{dt.year:04d}-{dt.month:02d}"
    except Exception:
        return ""


def extract_samsung_hbm4_price(event: dict) -> dict | None:
    text = compact_fact_text(event)
    low = text.lower()
    if not relevant("samsung_hbm4_price", text):
        return None

    obs: dict = {}
    if any(k in low for k in ("계약 체결", "가격 확정", "협상 타결", "contract signed", "price finalized", "pricing finalized", "negotiations concluded")):
        obs["stage"] = "signed"
    else:
        future_final = bool(re.search(
            r"(?:마무리\s*수순|final\s+stages|nearing\s+completion|close\s+to\s+finalizing)"
            r"[^.]{0,50}?(?:전망|예상|것으로|expected|likely|planned)"
            r"|(?:전망|예상|것으로|expected|likely|planned)[^.]{0,50}?"
            r"(?:마무리\s*수순|final\s+stages|nearing\s+completion|close\s+to\s+finalizing)",
            low, re.I
        ))
        if any(k in low for k in ("마무리 수순", "final stages", "nearing completion", "close to finalizing")) and not future_final:
            obs["stage"] = "final_stage"
        elif any(k in low for k in ("협상", "negotiation", "negotiating")):
            obs["stage"] = "negotiation"
        elif any(k in low for k in ("제시", "offered", "quoted")):
            obs["stage"] = "reported_offer"
        # 가격·공급·성능·웨이퍼 구조 기사에는 계약 단계 문구가 없을 수 있으므로
        # 여기서 버리지 않고 아래의 구조화 필드를 계속 추출한다.
    # Exact range only when the article gives explicit endpoints.
    pm = re.search(
        r"(?:hbm4[^.]{0,120}?)(?:\$|미화\s*)?([0-9]+(?:\.[0-9]+)?)\s*(?:~|[-–—]|to)\s*(?:\$|미화\s*)?([0-9]+(?:\.[0-9]+)?)\s*(?:/\s*)?gb",
        low, re.I,
    )
    if not pm:
        pm = re.search(
            r"(?:hbm4[^.]{0,120}?)(?:1\s*)?gb\s*(?:당|per)?[^0-9]{0,30}?(?:\$|미화\s*)?([0-9]+(?:\.[0-9]+)?)\s*(?:~|[-–—]|to)\s*(?:\$|미화\s*)?([0-9]+(?:\.[0-9]+)?)\s*(?:달러|usd|\$)?",
            low, re.I,
        )
    if pm:
        obs["offered_price_usd_per_gb_min"] = float(pm.group(1))
        obs["offered_price_usd_per_gb_max"] = float(pm.group(2))

    if re.search(r"4\s*달러대\s*중후반|mid[- ]?to[- ]?high\s*\$?4", text, re.I):
        obs["offered_price_band"] = "mid_to_high_4_usd_per_gb"

    ref = re.search(r"(?:hbm3e)[^.]{0,100}?([0-9]+(?:\.[0-9]+)?)\s*(?:달러|\$)[^.]{0,30}?(?:/\s*)?gb", low, re.I)
    if not ref:
        ref = re.search(r"(?:hbm3e)[^.]{0,100}?(?:gb당|per\s+gb)[^0-9]{0,30}?([0-9]+(?:\.[0-9]+)?)\s*(?:달러|\$)", low, re.I)
    if ref:
        obs["reference_hbm3e_usd_per_gb"] = float(ref.group(1))

    mult = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*배\s*이상|(?:more\s+than|over|at\s+least)\s*([0-9]+(?:\.[0-9]+)?)\s*(?:times|x)", text, re.I)
    if mult:
        obs["price_multiple_floor"] = float(mult.group(1) or mult.group(2))

    if any(k in low for k in ("물량이 상당 부분", "물량 상당 부분", "substantial portion of volume", "most volume")) and any(k in low for k in ("협의가 끝", "agreed", "settled")):
        obs["volume_stage"] = "largely_agreed"
    elif any(k in low for k in ("물량 확정", "volume finalized", "volume contracted")):
        obs["volume_stage"] = "finalized"

    if any(k in low for k in ("사실상 완판", "virtually sold out", "effectively sold out")):
        obs["reported_supply_status"] = "virtually_sold_out_reported"
    elif any(k in low for k in ("전량 계약", "fully contracted", "fully booked under contract")):
        obs["reported_supply_status"] = "fully_contracted"

    if (
        any(k in low for k in ("협상력", "pricing power"))
        and any(k in low for k in ("강해", "강화", "확대", "strengthen", "expand", "improv"))
    ):
        obs["pricing_power_stage"] = "strengthened_reported"
    elif any(k in low for k in ("가격 인하 압력", "가격 압박", "pricing pressure", "discount pressure")):
        obs["pricing_power_stage"] = "weakening_reported"

    if (
        any(k in low for k in ("최고 사양", "최고성능", "업계 최고", "higher specification", "high-spec", "industry-leading"))
        and any(k in low for k in ("공급", "supply", "업체가 제한", "limited"))
    ):
        obs["pricing_power_driver"] = "high_spec_performance_and_limited_supply"

    stable = re.search(r"(?:hbm4)[^.]{0,160}?([0-9]+(?:\.[0-9]+)?)\s*gbps[^.]{0,80}?(?:안정|stable|consistent)", low, re.I)
    if not stable:
        stable = re.search(r"(?:안정|stable|consistent)[^.]{0,80}?([0-9]+(?:\.[0-9]+)?)\s*gbps[^.]{0,120}?(?:hbm4)", low, re.I)
    if stable:
        obs["performance_stable_gbps"] = float(stable.group(1))

    max_speed = re.search(r"(?:hbm4)[^.]{0,240}?(?:최대|up\s+to)[^0-9]{0,30}?([0-9]+(?:\.[0-9]+)?)\s*gbps", low, re.I)
    if not max_speed and "hbm4" in low:
        max_speed = re.search(r"(?:최대|up\s+to)[^0-9]{0,30}?([0-9]+(?:\.[0-9]+)?)\s*gbps", low, re.I)
    if max_speed:
        obs["performance_max_gbps"] = float(max_speed.group(1))

    standard = re.search(r"(?:jedec|업계\s*표준)[^.]{0,100}?([0-9]+(?:\.[0-9]+)?)\s*gbps", low, re.I)
    if standard:
        obs["industry_standard_gbps"] = float(standard.group(1))

    bandwidth = re.search(r"(?:hbm4)[^.]{0,180}?(?:대역폭|bandwidth)[^.]{0,80}?([0-9]+(?:\.[0-9]+)?)\s*tb/s", low, re.I)
    if bandwidth:
        obs["stack_bandwidth_tbps"] = float(bandwidth.group(1))

    requirement = re.search(r"(?:고객사?\s*요구|customer\s+requirement)[^.]{0,80}?([0-9]+(?:\.[0-9]+)?)\s*tb/s", low, re.I)
    if requirement:
        obs["customer_requirement_tbps"] = float(requirement.group(1))

    wafer_share = re.search(
        r"(?:hbm)[^.]{0,220}?(?:웨이퍼\s*생산능력|wafer\s+capacity)[^.]{0,140}?(?:현재|current)[^0-9]{0,30}?20\s*%\s*대[^.]{0,160}?(?:내년|2027|next\s+year)[^0-9]{0,30}?([0-9]+(?:\.[0-9]+)?)\s*%",
        low, re.I,
    )
    if wafer_share:
        obs["industry_hbm_dram_wafer_share_current_band"] = "20s_pct_reported"
        obs["industry_hbm_dram_wafer_share_2027_pct"] = float(wafer_share.group(1))

    if any(k in low for k in ("이달 중", "this month")) and any(k in low for k in ("마무리", "finaliz", "conclud")):
        obs["target_close_month"] = _relative_month_from_event(event)

    if not obs:
        return None
    obs.update({
        "source": event.get("origin_source") or event.get("source") or "",
        "source_url": event.get("direct_link") or "",
        "observed_at": event.get("published_at_kst") or "",
    })
    return obs


def merge_samsung_hbm4_price(old: dict, obs: dict) -> dict:
    out = dict(old or {})
    for key, value in obs.items():
        if value not in (None, ""):
            out[key] = value
    return out


def samsung_hbm4_price_changes(old: dict, new: dict) -> list[str]:
    reasons: list[str] = []
    old_stage, new_stage = old.get("stage"), new.get("stage")
    if old_stage != new_stage and new_stage:
        reasons.append(f"계약가격 단계 {old_stage or '미확인'}→{new_stage}")

    for field, label in (
        ("offered_price_usd_per_gb_min", "제시가격 하단"),
        ("offered_price_usd_per_gb_max", "제시가격 상단"),
    ):
        a, b = old.get(field), new.get(field)
        if a is not None and b is not None:
            pct = (float(b) / float(a) - 1.0) * 100 if float(a) else 0
            if abs(float(b)-float(a)) >= 0.20 or abs(pct) >= 5:
                reasons.append(f"{label} {float(a):.2f}→{float(b):.2f}달러/Gb")
        elif a is None and b is not None:
            reasons.append(f"{label} {float(b):.2f}달러/Gb 신규 확인")

    if old.get("offered_price_band") != new.get("offered_price_band") and new.get("offered_price_band"):
        reasons.append(f"제시가격 밴드 {old.get('offered_price_band') or '미확인'}→{new.get('offered_price_band')}")

    a, b = old.get("reference_hbm3e_usd_per_gb"), new.get("reference_hbm3e_usd_per_gb")
    if a is not None and b is not None and abs(float(b)-float(a)) >= 0.10:
        reasons.append(f"HBM3E 비교가격 {float(a):.2f}→{float(b):.2f}달러/Gb")

    a, b = old.get("price_multiple_floor"), new.get("price_multiple_floor")
    if a is not None and b is not None and abs(float(b)-float(a)) >= 0.25:
        reasons.append(f"HBM3E 대비 가격배수 하한 {float(a):.2f}배→{float(b):.2f}배")

    if old.get("volume_stage") != new.get("volume_stage") and new.get("volume_stage"):
        reasons.append(f"물량 협의 단계 {old.get('volume_stage') or '미확인'}→{new.get('volume_stage')}")
    if old.get("reported_supply_status") != new.get("reported_supply_status") and new.get("reported_supply_status"):
        reasons.append(f"공급 상태 {old.get('reported_supply_status') or '미확인'}→{new.get('reported_supply_status')}")
    if old.get("pricing_power_stage") != new.get("pricing_power_stage") and new.get("pricing_power_stage"):
        reasons.append(f"가격 협상력 {old.get('pricing_power_stage') or '미확인'}→{new.get('pricing_power_stage')}")
    if old.get("pricing_power_driver") != new.get("pricing_power_driver") and new.get("pricing_power_driver"):
        reasons.append(f"가격 프리미엄 근거 {old.get('pricing_power_driver') or '미확인'}→{new.get('pricing_power_driver')}")

    for field, label, threshold in (
        ("performance_stable_gbps", "HBM4 안정 동작속도", 0.2),
        ("performance_max_gbps", "HBM4 최대 동작속도", 0.2),
        ("industry_standard_gbps", "HBM4 업계표준 속도", 0.2),
        ("stack_bandwidth_tbps", "HBM4 스택 대역폭", 0.1),
        ("customer_requirement_tbps", "고객 요구 대역폭", 0.1),
        ("industry_hbm_dram_wafer_share_2027_pct", "2027 HBM의 D램 웨이퍼 생산능력 비중", 2.0),
    ):
        a, b = old.get(field), new.get(field)
        if a is not None and b is not None and abs(float(b) - float(a)) >= threshold:
            unit = "Gbps" if "gbps" in field else "%" if "share" in field else "TB/s"
            reasons.append(f"{label} {float(a):g}→{float(b):g}{unit}")
        elif a is None and b is not None:
            unit = "Gbps" if "gbps" in field else "%" if "share" in field else "TB/s"
            reasons.append(f"{label} {float(b):g}{unit} 신규 확인")

    if old.get("target_close_month") != new.get("target_close_month") and new.get("target_close_month"):
        reasons.append(f"가격협상 마무리 목표 {old.get('target_close_month') or '미확인'}→{new.get('target_close_month')}")
    return reasons


def samsung_hbm4_price_event(state: dict, reasons: list[str]) -> dict:
    return {
        "category": "samsung_hbm4_price",
        "fact_key": "samsung_hbm4_price_" + (state.get("stage") or "state") + "_" + (state.get("observed_at") or state.get("as_of") or ""),
        "headline_ko": "삼성전자 2027 HBM4 계약가격 변화",
        "fact_bullets": reasons,
        "verdict": "🟢 계약 체결·가격 확정이면 실제 2027 ASP에 직접 연결됩니다." if state.get("stage") == "signed" else "🟡 현재는 제시·협상 가격입니다. 고객과 확정된 체결가격으로 승격하지 않습니다.",
        "verification": "상태값 변화",
        "quality": "신뢰 리서치·보도",
        "origin_source": state.get("source") or "",
        "source": state.get("source") or "",
        "published_at_kst": state.get("observed_at") or state.get("as_of") or "",
        "direct_link": state.get("source_url") or "",
        "article_text": "",
        "samsung_hbm4_price_state": state,
    }


def _rubin_preference_source_id(event: dict) -> str:
    source = ((event.get("origin_source") or event.get("source") or "") + " " + (event.get("direct_link") or "")).lower()
    for token, label in (
        ("nvidia", "NVIDIA"),
        ("trendforce", "TrendForce"),
        ("semianalysis", "SemiAnalysis"),
        ("damnang", "Damnang"),
        ("reuters", "Reuters"),
        ("bloomberg", "Bloomberg"),
        ("morgan stanley", "Morgan Stanley"),
    ):
        if token in source:
            return label
    return ""


def extract_rubin_ultra_hbm_options(event: dict) -> dict | None:
    text = compact_fact_text(event)
    low = text.lower()
    if not relevant("rubin_hbm_option_set", text):
        return None

    source_low = ((event.get("origin_source") or event.get("source") or "") + " " + text).lower()
    final_words = any(k in low for k in ("최종 확정", "final specification", "officially selected", "탑재 확정"))
    evaluation_words = any(k in low for k in ("평가 중", "평가중", "검토", "evaluation", "evaluating", "considering", "선택지를 넓혀"))

    # Directional wording must identify the target, not merely contain both
    # layer counts in one sentence. "go back to 12Hi instead of 8Hi" must not
    # accidentally match 8Hi as another "go back" target.
    to_12 = bool(
        re.search(r"(?:12\s*[- ]?(?:hi|단))[^.]{0,80}?(?:instead\s+of|rather\s+than|대신)[^.]{0,60}?(?:8\s*[- ]?(?:hi|단))", low, re.I)
        or re.search(r"(?:go\s+back|switch\s+back|revert)\s+(?:to\s+)?12\s*[- ]?(?:hi|단)", low, re.I)
        or re.search(r"(?:12\s*[- ]?(?:hi|단))(?:으로)?[^.]{0,20}?(?:복귀|회귀|전환)", low, re.I)
    )
    to_8 = bool(
        re.search(r"(?:8\s*[- ]?(?:hi|단))[^.]{0,80}?(?:instead\s+of|rather\s+than|대신)[^.]{0,60}?(?:12\s*[- ]?(?:hi|단))", low, re.I)
        or re.search(r"(?:go\s+back|switch\s+back|revert)\s+(?:to\s+)?8\s*[- ]?(?:hi|단)", low, re.I)
        or re.search(r"(?:8\s*[- ]?(?:hi|단))(?:으로)?[^.]{0,20}?(?:복귀|회귀|전환)", low, re.I)
    )
    directional = to_12 != to_8

    obs: dict = {}
    if directional:
        product = "HBM4E" if "hbm4e" in low else "HBM4"
        target_layers = 12 if to_12 else 8
        prior_layers = 8 if to_12 else 12
        obs.update({
            "reported_preferred_option": f"{product}_{target_layers}hi",
            "previous_reported_preferred_option": f"{product}_{prior_layers}hi",
            "reported_preference_direction": f"{prior_layers}hi_to_{target_layers}hi_reversal",
            "reported_preference_stage": "single_industry_source",
            "reported_preference_source_url": event.get("direct_link") or "",
            "reported_preference_as_of": (event.get("published_at_kst") or "")[:10],
        })
        sid = _rubin_preference_source_id(event)
        if sid:
            obs["reported_preference_support_sources"] = [sid]

    options: list[str] = []
    for product in ("hbm4e", "hbm4"):
        token = r"hbm4e" if product == "hbm4e" else r"hbm4(?!e)"
        for layers in (12, 8):
            pats = (
                rf"{layers}\s*[- ]?(?:hi|단)[^.]{0,50}?{token}",
                rf"{token}[^.]{{0,50}}?{layers}\s*[- ]?(?:hi|단)",
            )
            if any(re.search(p, low, re.I) for p in pats):
                options.append(f"{product.upper()}_{layers}hi")

    # A short directional post ("back to 12Hi instead of 8Hi") changes the
    # reported preference, not the full candidate set. Keep all existing
    # candidates until an evaluation/final-spec source explicitly changes them.
    if options and (evaluation_words or final_words or not directional):
        obs["candidate_options"] = sorted(set(options))

    if final_words:
        obs["stage"] = "official_final" if "nvidia" in source_low else "reported_final"
        if obs.get("candidate_options") and len(obs["candidate_options"]) == 1:
            obs["reported_preferred_option"] = obs["candidate_options"][0]
            obs["reported_preference_stage"] = "official_final" if "nvidia" in source_low else "reported_final"
    elif evaluation_words:
        obs["stage"] = "reported_evaluation"
    elif not directional:
        obs["stage"] = "reported_options"

    if not obs:
        return None
    obs.update({
        "source": event.get("origin_source") or event.get("source") or "",
        "source_url": event.get("direct_link") or "",
        "observed_at": event.get("published_at_kst") or "",
    })
    return obs


def merge_rubin_ultra_hbm_options(old: dict, obs: dict) -> dict:
    out = dict(old or {})
    old_preference = out.get("reported_preferred_option")
    new_preference = obs.get("reported_preferred_option")
    for key, value in obs.items():
        if key == "reported_preference_support_sources":
            continue
        if value not in (None, ""):
            out[key] = value

    if new_preference:
        new_sources = set(obs.get("reported_preference_support_sources") or [])
        if old_preference and new_preference != old_preference:
            out["reported_preference_support_sources"] = sorted(new_sources)
        else:
            out["reported_preference_support_sources"] = sorted(
                set(out.get("reported_preference_support_sources") or []) | new_sources
            )

        sources = set(out.get("reported_preference_support_sources") or [])
        if out.get("stage") == "official_final" and "NVIDIA" in sources:
            out["reported_preference_stage"] = "official_final"
        elif len(sources) >= 2:
            out["reported_preference_stage"] = "cross_verified"
        elif sources:
            out["reported_preference_stage"] = "single_industry_source"

    return out


def rubin_ultra_hbm_options_changes(old: dict, new: dict) -> list[str]:
    reasons: list[str] = []
    if old.get("stage") != new.get("stage") and new.get("stage"):
        reasons.append(f"Rubin Ultra HBM 옵션 단계 {old.get('stage') or '미확인'}→{new.get('stage')}")

    old_opts = sorted(old.get("candidate_options") or [])
    new_opts = sorted(new.get("candidate_options") or [])
    if old_opts != new_opts and new_opts:
        reasons.append("HBM 후보 조합 " + ", ".join(old_opts or ["미확인"]) + "→" + ", ".join(new_opts))

    a, b = old.get("reported_preferred_option"), new.get("reported_preferred_option")
    if a != b and b:
        reasons.append(f"업계 우세 신호 {a or '미확인'}→{b}")

    a, b = old.get("reported_preference_stage"), new.get("reported_preference_stage")
    if a != b and b:
        reasons.append(f"우세 신호 검증 단계 {a or '미확인'}→{b}")

    a, b = old.get("reported_preference_direction"), new.get("reported_preference_direction")
    if a != b and b:
        reasons.append(f"적층 방향 변화 {a or '미확인'}→{b}")

    old_sources = set(old.get("reported_preference_support_sources") or [])
    new_sources = set(new.get("reported_preference_support_sources") or [])
    added = sorted(new_sources - old_sources)
    if added and len(new_sources) >= 2:
        reasons.append("우세 신호 독립 출처 추가: " + ", ".join(added))
    return reasons


def rubin_ultra_hbm_options_event(state: dict, reasons: list[str]) -> dict:
    final = state.get("stage") == "official_final"
    preference_stage = state.get("reported_preference_stage") or "미확인"
    return {
        "category": "rubin_hbm_option_set",
        "fact_key": "rubin_hbm_options_" + (state.get("stage") or "state") + "_" + (state.get("reported_preferred_option") or "no_preference") + "_" + (state.get("observed_at") or state.get("reported_preference_as_of") or state.get("as_of") or ""),
        "headline_ko": "Rubin Ultra HBM4/HBM4E 후보·8단↔12단 방향 변화",
        "fact_bullets": reasons,
        "verdict": (
            "NVIDIA 공식 최종 HBM 조합으로 확인됐습니다. GPU당 HBM 용량·스택 수·공급사 물량을 다시 계산해야 합니다."
            if final else
            f"현재 우세 신호 검증 단계는 {preference_stage}입니다. 8단↔12단 방향 전환 신호와 후보군을 추적하되 NVIDIA 공식 최종 사양으로 승격하지 않습니다."
        ),
        "verification": "후보군·우세 신호·공식 최종사양 분리",
        "quality": "공식자료·신뢰보도·단일 업계신호 분리",
        "origin_source": state.get("source") or "",
        "source": state.get("source") or "",
        "published_at_kst": state.get("observed_at") or state.get("reported_preference_as_of") or state.get("as_of") or "",
        "direct_link": state.get("reported_preference_source_url") or state.get("source_url") or "",
        "article_text": "",
        "rubin_hbm_options_state": state,
    }


def extract_samsung_nextgen_hbm(event: dict) -> dict | None:
    text = compact_fact_text(event)
    low = text.lower()
    if not relevant("samsung_nextgen_hbm", text):
        return None

    obs: dict = {}

    if any(k in low for k in ("custom hbm", "커스텀 hbm", "맞춤형 hbm")):
        if any(k in low for k in ("양산 시작", "양산한다", "mass production", "in production")):
            obs["custom_hbm_stage"] = "mass_production"
        elif any(k in low for k in ("계약 체결", "공급 계약", "contract signed", "supply contract")):
            obs["custom_hbm_stage"] = "contract_signed"
        elif any(k in low for k in ("고객 검증", "고객사 검증", "customer validation", "qualification")):
            obs["custom_hbm_stage"] = "customer_validation"
        elif any(k in low for k in ("샘플 출하를 시작", "샘플링을 시작했다", "began sampling", "samples shipped", "sample shipments began")):
            obs["custom_hbm_stage"] = "customer_sample"
        elif (
            "2027" in low
            and any(k in low for k in ("샘플링", "샘플 출하", "sampling", "samples will", "samples to"))
            and any(k in low for k in ("예정", "계획", "start", "begin", "will"))
        ):
            obs["custom_hbm_stage"] = "official_sampling_plan"
            obs["custom_hbm_sample_start_year"] = 2027

        if any(k in low for k in ("고객사별", "고객 맞춤형", "customer-specific", "according to their respective specifications")):
            obs["custom_hbm_customer_specific"] = True
        if "interface" in low or "인터페이스" in low:
            obs["custom_hbm_interface_customization"] = True

    if "hbm5" in low and any(k in low for k in ("맞춤형", "커스텀", "custom", "customer-specific")):
        if any(k in low for k in ("업계는 보고", "전망", "예상", "expected", "industry expects", "industry views")):
            obs["hbm5_customization_stage"] = "industry_expected"
        elif any(k in low for k in ("공동개발", "joint development", "co-develop")):
            obs["hbm5_customization_stage"] = "customer_joint_development"
        else:
            obs["hbm5_customization_stage"] = "company_development"

    if "zhbm" in low:
        if any(k in low for k in ("양산 시작", "양산한다", "mass production", "in production")):
            obs["zhbm_stage"] = "mass_production"
        elif any(k in low for k in ("계약 체결", "공급 계약", "contract signed", "supply contract")):
            obs["zhbm_stage"] = "contract_signed"
        elif any(k in low for k in ("고객 검증", "고객사 검증", "customer validation", "qualification")):
            obs["zhbm_stage"] = "customer_validation"
        elif any(k in low for k in ("샘플", "sample shipment", "samples shipped")):
            obs["zhbm_stage"] = "customer_sample"
        elif any(k in low for k in ("콘셉트", "concept", "목업", "mock-up", "mockup", "개발하고", "in development", "developing")):
            obs["zhbm_stage"] = "concept_development"

        if any(k in low for k in ("고객 맞춤형", "customer-specific", "customized ip", "맞춤형 ip")):
            obs["zhbm_customer_specific_design"] = True

        perf = re.search(r"(?:zhbm)[^.]{0,180}?(?:hbm5)[^.]{0,100}?(?:최대\s*)?([0-9]+(?:\.[0-9]+)?)\s*배[^.]{0,60}?(?:성능|performance)", low, re.I)
        if not perf:
            perf = re.search(r"(?:zhbm)[^.]{0,180}?(?:성능|performance)[^.]{0,80}?(?:최대\s*)?([0-9]+(?:\.[0-9]+)?)\s*배[^.]{0,100}?(?:hbm5)", low, re.I)
        if perf:
            obs["zhbm_performance_vs_hbm5_x"] = float(perf.group(1))

        energy = re.search(r"(?:zhbm)[^.]{0,220}?(?:전성비|전력\s*효율|energy\s+efficiency|performance\s+per\s+watt)[^.]{0,100}?(?:최대\s*)?([0-9]+(?:\.[0-9]+)?)\s*배", low, re.I)
        if energy:
            obs["zhbm_energy_efficiency_vs_hbm5_x"] = float(energy.group(1))

        if any(k in low for k in ("열 저항을 절반 이상", "thermal resistance by more than half", "thermal resistance more than half")):
            obs["zhbm_thermal_resistance_reduction_floor_pct"] = 50.0

        density = re.search(r"(?:zhbm)[^.]{0,240}?(?:메모리\s*밀도|memory\s+density)[^.]{0,100}?(?:10\s*배|10\s*times)", low, re.I)
        if density:
            obs["zhbm_memory_density_floor_vs_hbm5_x"] = 10.0

    if not obs:
        return None
    obs.update({
        "source": event.get("origin_source") or event.get("source") or "",
        "source_url": event.get("direct_link") or "",
        "observed_at": event.get("published_at_kst") or "",
    })
    return obs


def merge_samsung_nextgen_hbm(old: dict, obs: dict) -> dict:
    out = dict(old or {})
    for key, value in obs.items():
        if value not in (None, ""):
            out[key] = value
    return out


def samsung_nextgen_hbm_changes(old: dict, new: dict) -> list[str]:
    reasons: list[str] = []
    for field, label in (
        ("custom_hbm_stage", "Custom HBM 단계"),
        ("hbm5_customization_stage", "HBM5 맞춤형 단계"),
        ("zhbm_stage", "zHBM 단계"),
    ):
        a, b = old.get(field), new.get(field)
        if a != b and b:
            reasons.append(f"{label} {a or '미확인'}→{b}")

    a, b = old.get("custom_hbm_sample_start_year"), new.get("custom_hbm_sample_start_year")
    if a != b and b:
        reasons.append(f"Custom HBM 샘플링 시작 연도 {a or '미확인'}→{b}")

    for field, label in (
        ("custom_hbm_customer_specific", "Custom HBM 고객사별 맞춤 설계"),
        ("custom_hbm_interface_customization", "Custom HBM 인터페이스 맞춤 설계"),
        ("zhbm_customer_specific_design", "zHBM 고객 맞춤형 설계"),
    ):
        a, b = old.get(field), new.get(field)
        if a != b and b is True:
            reasons.append(f"{label} 확인")

    for field, label, threshold, unit in (
        ("zhbm_performance_vs_hbm5_x", "zHBM 성능", 0.5, "배"),
        ("zhbm_energy_efficiency_vs_hbm5_x", "zHBM 전력효율", 0.25, "배"),
        ("zhbm_thermal_resistance_reduction_floor_pct", "zHBM 열저항 감소 하한", 5.0, "%"),
        ("zhbm_memory_density_floor_vs_hbm5_x", "zHBM 메모리 밀도 하한", 1.0, "배"),
    ):
        a, b = old.get(field), new.get(field)
        if a is not None and b is not None and abs(float(b)-float(a)) >= threshold:
            reasons.append(f"{label} {float(a):g}→{float(b):g}{unit}")
        elif a is None and b is not None:
            reasons.append(f"{label} {float(b):g}{unit} 신규 확인")
    return reasons


def samsung_nextgen_hbm_event(state: dict, reasons: list[str]) -> dict:
    zhbm_stage = state.get("zhbm_stage") or "미확인"
    custom_stage = state.get("custom_hbm_stage") or "미확인"
    advanced = (
        zhbm_stage in ("customer_sample", "customer_validation", "contract_signed", "mass_production")
        or custom_stage in ("customer_sample", "customer_validation", "contract_signed", "mass_production")
    )
    return {
        "category": "samsung_nextgen_hbm",
        "fact_key": "samsung_nextgen_hbm_" + str(custom_stage) + "_" + str(zhbm_stage) + "_" + (state.get("observed_at") or state.get("as_of") or ""),
        "headline_ko": "삼성 Custom HBM·HBM5·zHBM 맞춤형 로드맵 변화",
        "fact_bullets": reasons,
        "verdict": (
            "Custom HBM 또는 zHBM이 계획·콘셉트 단계를 넘어 고객 샘플·검증·계약·양산 쪽으로 진전했습니다."
            if advanced else
            "삼성 Custom HBM은 2027년 고객사별 순차 샘플링 계획이 공식 확인됐습니다. HBM5 맞춤형 확대 전망과 zHBM 콘셉트·개발 단계는 별도로 관리하며, 확정 고객·계약·양산으로 승격하지 않습니다."
        ),
        "verification": "상태값 변화",
        "quality": "공식자료·신뢰보도 교차",
        "origin_source": state.get("source") or "",
        "source": state.get("source") or "",
        "published_at_kst": state.get("observed_at") or state.get("as_of") or "",
        "direct_link": state.get("source_url") or "",
        "article_text": "",
        "samsung_nextgen_hbm_state": state,
    }


def extract_nvhbm_architecture(event: dict) -> dict | None:
    text = compact_fact_text(event)
    low = text.lower()
    if not relevant("nvhbm_architecture", text):
        return None

    obs: dict = {}
    source = event.get("origin_source") or event.get("source") or ""
    official = source_quality(source) == "공식·회사자료"
    semianalysis = "semianalysis" in source.lower() or "semianalysis" in low

    if "nvhbm" in low and official:
        obs["nvidia_stage"] = "official_announced"

    if (
        ("memory controller" in low or "메모리 컨트롤러" in low)
        and any(k in low for k in ("base die", "hbm stack", "베이스 다이", "hbm 스택", "3d hbm"))
        and any(k in low for k in ("move", "moving", "moved", "inside", "into", "이동", "옮", "통합"))
    ):
        obs["memory_controller_location"] = "hbm_base_die"

    def pct(patterns):
        for pat in patterns:
            m = re.search(pat, low, re.I)
            if m:
                return float(m.group(1))
        return None

    if official:
        v = pct((
            r"(?:up to|max(?:imum)?|최대)\s*([0-9]+(?:\.[0-9]+)?)\s*%[^%.]{0,80}?(?:more|higher|increase|향상|증가)[^%.]{0,80}?(?:memory\s+bandwidth|bandwidth|메모리\s*대역폭|대역폭)",
            r"(?:memory\s+bandwidth|bandwidth|메모리\s*대역폭|대역폭)[^%]{0,100}?(?:up to|max(?:imum)?|최대)\s*([0-9]+(?:\.[0-9]+)?)\s*%",
        ))
        if v is not None:
            obs["bandwidth_gain_pct_max"] = v

        v = pct((
            r"(?:up to|max(?:imum)?|최대)\s*([0-9]+(?:\.[0-9]+)?)\s*%[^%.]{0,100}?(?:more|additional|추가|증가)[^%.]{0,80}?(?:compute\s+die\s+area|연산\s*다이\s*면적)",
            r"(?:compute\s+die\s+area|연산\s*다이\s*면적)[^%]{0,120}?(?:up to|max(?:imum)?|최대)\s*([0-9]+(?:\.[0-9]+)?)\s*%",
        ))
        if v is not None:
            obs["compute_die_area_gain_pct_max"] = v

        v = pct((
            r"(?:phy)[^.]{0,80}?(?:support|지원)[^.]{0,100}?(?:area|면적)[^%]{0,100}?(?:reduce|reduced|reduction|줄|감소)[^%]{0,80}?(?:by\s*)?(?:up to|max(?:imum)?|최대)\s*([0-9]+(?:\.[0-9]+)?)\s*%",
            r"(?:phy)[^.]{0,80}?(?:support|지원)[^.]{0,100}?(?:area|면적)[^%]{0,100}?(?:up to|max(?:imum)?|최대)\s*([0-9]+(?:\.[0-9]+)?)\s*%[^.]{0,60}?(?:reduce|reduced|reduction|줄|감소)",
            r"(?:reduce|reduced|reduction|줄|감소)[^%]{0,80}?(?:phy)[^.]{0,100}?(?:area|면적)[^%]{0,80}?([0-9]+(?:\.[0-9]+)?)\s*%",
        ))
        if v is not None:
            obs["phy_support_area_reduction_pct_max"] = v

        v = pct((
            r"(?:up to|max(?:imum)?|최대)\s*([0-9]+(?:\.[0-9]+)?)\s*%[^%.]{0,100}?(?:more|증가)[^%.]{0,100}?(?:usable\s+silicon|사용할\s*수\s*있는\s*실리콘|가용\s*실리콘)",
            r"(?:usable\s+silicon|사용할\s*수\s*있는\s*실리콘|가용\s*실리콘)[^%]{0,120}?(?:up to|max(?:imum)?|최대)\s*([0-9]+(?:\.[0-9]+)?)\s*%",
        ))
        if v is not None:
            obs["layout_usable_silicon_gain_pct_max"] = v

        v = pct((
            r"(?:up to|max(?:imum)?|최대)\s*(?:a\s*)?([0-9]+(?:\.[0-9]+)?)\s*%[^%.]{0,100}?(?:increase|증가)[^%.]{0,100}?(?:main[- ]die\s+silicon|메인\s*다이\s*실리콘)",
            r"(?:main[- ]die\s+silicon|메인\s*다이\s*실리콘)[^%]{0,120}?(?:up to|max(?:imum)?|최대)\s*([0-9]+(?:\.[0-9]+)?)\s*%",
        ))
        if v is not None:
            obs["main_die_silicon_gain_pct_max"] = v

        v = pct((
            r"(?:up to|max(?:imum)?|최대)\s*([0-9]+(?:\.[0-9]+)?)\s*%[^%.]{0,100}?(?:lower|reduce|reduction|낮|절감|감소)[^%.]{0,80}?(?:hbm\s+power|hbm\s+전력)",
            r"(?:hbm\s+power|hbm\s+전력)[^%]{0,100}?(?:up to|max(?:imum)?|최대)\s*([0-9]+(?:\.[0-9]+)?)\s*%[^.]{0,40}?(?:lower|낮|절감|감소)",
        ))
        if v is not None:
            obs["hbm_power_reduction_pct_max"] = v

        v = pct((
            r"([0-9]+(?:\.[0-9]+)?)\s*%[^.]{0,90}?(?:overall\s+end-to-end\s+performance|end-to-end\s+performance|엔드투엔드\s*성능)",
            r"(?:overall\s+end-to-end\s+performance|end-to-end\s+performance|엔드투엔드\s*성능)[^%]{0,100}?([0-9]+(?:\.[0-9]+)?)\s*%",
        ))
        if v is not None:
            obs["xpu_end_to_end_performance_gain_pct_max"] = v

        m = re.search(r"(?:up to|최대)\s*([0-9][0-9,]*)\s*(?:additional\s+)?xpus?", low, re.I)
        if m:
            obs["one_gw_additional_xpu_headroom_max"] = int(m.group(1).replace(",", ""))

        if "annapurna labs" in low and any(k in low for k in ("first", "첫", "collaborat", "협력")):
            obs["first_collaborator"] = "Amazon Annapurna Labs"

        if "feynman" in low and any(k in low for k in ("custom hbm", "custom high-bandwidth memory", "맞춤형 hbm", "커스텀 hbm")):
            obs["feynman_custom_hbm_official"] = True

        confirmed_vendors = []
        for vendor, aliases in (
            ("Samsung Electronics", ("samsung", "삼성전자")),
            ("SK hynix", ("sk hynix", "sk하이닉스")),
            ("Micron", ("micron", "마이크론")),
        ):
            if any(a in low for a in aliases) and any(k in low for k in ("validated", "validation partner", "memory partner", "memory provider", "검증", "파트너", "공급사")):
                confirmed_vendors.append(vendor)
        if confirmed_vendors:
            obs["official_memory_vendors"] = sorted(set(confirmed_vendors))

    if semianalysis:
        m = re.search(r"(?:rubin)[^.]{0,180}?(?:hbm4?\s*(?:controllers?|컨트롤러)?|hbm)[^.]{0,120}?(?:logic|phy|로직)[^%]{0,80}?([0-9]+(?:\.[0-9]+)?)\s*%", low, re.I)
        if not m:
            m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%[^.]{0,100}?(?:rubin)[^.]{0,100}?(?:hbm)[^.]{0,80}?(?:logic|phy)", low, re.I)
        if not m:
            m = re.search(
                r"(?:hbm4?)[^.]{0,120}?(?:controllers?|컨트롤러|logic|phy)[^.]{0,120}?([0-9]+(?:\.[0-9]+)?)\s*%[^.]{0,140}?(?:rubin)",
                low, re.I,
            )
        if m:
            obs["rubin_hbm_logic_phy_die_share_estimate_pct"] = float(m.group(1))

        m = re.search(r"(?:feynman)[^.]{0,180}?(?:nvhbm|hbm)[^%]{0,120}?([0-9]+(?:\.[0-9]+)?)\s*%", low, re.I)
        if not m:
            m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%[^.]{0,100}?(?:feynman)[^.]{0,100}?(?:nvhbm|hbm)", low, re.I)
        if not m:
            m = re.search(
                r"(?:feynman)[^.]{0,140}?(?:nvhbm|custom\s+hbm)[^.]{0,140}?(?:falls?|drop|reduce|낮)[^0-9]{0,30}([0-9]+(?:\.[0-9]+)?)\s*%",
                low, re.I,
            )
        if m:
            obs["feynman_nvhbm_interface_die_share_estimate_pct"] = float(m.group(1))

        std = re.search(r"(?:standard\s+hbm4\s+phy|hbm4\s+phy)[^.]{0,100}?([0-9]+(?:\.[0-9]+)?)\s*mm\s*[x×]\s*([0-9]+(?:\.[0-9]+)?)\s*mm", low, re.I)
        custom = re.search(r"(?:custom\s+(?:d2d|die-to-die)\s+(?:interface|link)|d2d\s+interface)[^.]{0,100}?([0-9]+(?:\.[0-9]+)?)\s*mm\s*[x×]\s*([0-9]+(?:\.[0-9]+)?)\s*mm", low, re.I)
        if std:
            obs["samsung_standard_hbm4_phy_width_mm"] = float(std.group(1))
            obs["samsung_standard_hbm4_phy_height_mm"] = float(std.group(2))
        if custom:
            obs["samsung_custom_d2d_width_mm"] = float(custom.group(1))
            obs["samsung_custom_d2d_height_mm"] = float(custom.group(2))
        if std and custom:
            std_area = float(std.group(1)) * float(std.group(2))
            custom_area = float(custom.group(1)) * float(custom.group(2))
            if std_area > 0:
                obs["samsung_custom_d2d_area_reduction_pct_estimate"] = (1.0 - custom_area / std_area) * 100.0

    if not obs:
        return None
    obs.update({
        "source": source,
        "source_url": event.get("direct_link") or "",
        "observed_at": event.get("published_at_kst") or "",
    })
    return obs


def merge_nvhbm_architecture(old: dict, obs: dict) -> dict:
    out = dict(old or {})
    for key, value in obs.items():
        if value in (None, ""):
            continue
        if key == "official_memory_vendors":
            out[key] = sorted(set(out.get(key) or []) | set(value or []))
        else:
            out[key] = value
    return out


def nvhbm_architecture_changes(old: dict, new: dict) -> list[str]:
    reasons: list[str] = []

    for field, label in (
        ("nvidia_stage", "NVIDIA NVHBM 단계"),
        ("first_collaborator", "첫 협력사"),
        ("memory_controller_location", "메모리 컨트롤러 위치"),
    ):
        a, b = old.get(field), new.get(field)
        if a != b and b:
            reasons.append(f"{label} {a or '미확인'}→{b}")

    if old.get("feynman_custom_hbm_official") != new.get("feynman_custom_hbm_official") and new.get("feynman_custom_hbm_official") is True:
        reasons.append("Feynman Custom HBM 공식 로드맵 확인")

    old_vendors = set(old.get("official_memory_vendors") or [])
    new_vendors = set(new.get("official_memory_vendors") or [])
    added = sorted(new_vendors - old_vendors)
    if added:
        reasons.append("공식 NVHBM 메모리 파트너 실명 신규 확인: " + ", ".join(added))

    for field, label, threshold in (
        ("bandwidth_gain_pct_max", "NVIDIA 공식 대역폭 향상 최대치", 2.0),
        ("compute_die_area_gain_pct_max", "NVIDIA 공식 연산 다이 면적 추가 확보 최대치", 2.0),
        ("phy_support_area_reduction_pct_max", "NVIDIA 공식 PHY·지원 면적 감소 최대치", 2.0),
        ("layout_usable_silicon_gain_pct_max", "NVIDIA 공식 전체 레이아웃 가용 실리콘 증가 최대치", 3.0),
        ("main_die_silicon_gain_pct_max", "NVIDIA 공식 메인 다이 실리콘 증가 최대치", 2.0),
        ("hbm_power_reduction_pct_max", "NVIDIA 공식 HBM 전력 감소 최대치", 2.0),
        ("xpu_end_to_end_performance_gain_pct_max", "NVIDIA 공식 XPU 엔드투엔드 성능 향상 최대치", 2.0),
        ("rubin_hbm_logic_phy_die_share_estimate_pct", "SemiAnalysis Rubin HBM 로직·PHY 다이 비중 추정", 2.0),
        ("feynman_nvhbm_interface_die_share_estimate_pct", "SemiAnalysis Feynman NVHBM 인터페이스 다이 비중 추정", 1.0),
        ("samsung_custom_d2d_area_reduction_pct_estimate", "SemiAnalysis 인용 Samsung Custom D2D 면적 감소 추정", 5.0),
    ):
        a, b = old.get(field), new.get(field)
        if a is not None and b is not None and abs(float(b) - float(a)) >= threshold:
            reasons.append(f"{label} {float(a):g}%→{float(b):g}%")
        elif a is None and b is not None:
            reasons.append(f"{label} {float(b):g}% 신규 확인")

    a, b = old.get("one_gw_additional_xpu_headroom_max"), new.get("one_gw_additional_xpu_headroom_max")
    if a is not None and b is not None and abs(int(b) - int(a)) >= 1000:
        reasons.append(f"1GW 데이터센터 추가 XPU 헤드룸 최대 {int(a):,}→{int(b):,}대")
    elif a is None and b is not None:
        reasons.append(f"1GW 데이터센터 추가 XPU 헤드룸 최대 {int(b):,}대 신규 확인")

    return reasons


def nvhbm_architecture_event(state: dict, reasons: list[str]) -> dict:
    return {
        "category": "nvhbm_architecture",
        "fact_key": "nvhbm_architecture_" + hashlib.sha256(("|".join(reasons) + "|" + (state.get("observed_at") or state.get("as_of") or "")).encode()).hexdigest()[:16],
        "headline_ko": "NVIDIA NVHBM·Custom HBM 구조 변화",
        "fact_bullets": reasons,
        "verdict": (
            "NVHBM은 단순 HBM 속도 상향이 아니라 메모리 컨트롤러를 XPU에서 HBM 베이스 다이로 옮기고 "
            "표준 PHY를 맞춤형 다이투다이 인터페이스로 바꾸는 구조 변화입니다. "
            "NVIDIA 공식 수치와 SemiAnalysis 추정치를 분리하며, 메모리 공급사 실명은 회사 공식 확인 전까지 확정하지 않습니다."
        ),
        "verification": "NVIDIA·메모리사 공식자료 우선, SemiAnalysis 추정 별도",
        "quality": "공식자료·신뢰 리서치 분리",
        "origin_source": state.get("source") or state.get("official_source") or "",
        "source": state.get("source") or state.get("official_source") or "",
        "published_at_kst": state.get("observed_at") or state.get("as_of") or "",
        "direct_link": state.get("source_url") or state.get("official_source_url") or "",
        "article_text": "",
        "nvhbm_architecture_state": state,
    }


def extract_samsung_hbm4e_thermal_package(event: dict) -> dict | None:
    text = compact_fact_text(event)
    low = text.lower()
    if not relevant("hbm4e_thermal_package", text):
        return None

    obs: dict = {}

    current = re.search(
        r"(?:현재|current(?:ly)?)[^.]{0,100}?(?:interposer|인터포저)[^.]{0,100}?([0-9]+(?:\.[0-9]+)?)\s*(?:배|x|times)",
        text, re.I,
    )
    if not current:
        current = re.search(
            r"(?:interposer|인터포저)[^.]{0,100}?(?:현재|current(?:ly)?)[^.]{0,80}?([0-9]+(?:\.[0-9]+)?)\s*(?:배|x|times)",
            text, re.I,
        )
    if current:
        obs["industry_current_interposer_reticle_x"] = float(current.group(1))

    future = re.search(
        r"(?:interposer|인터포저)[^.]{0,180}?(?:as\s+much\s+as|up\s+to)[^0-9]{0,20}?([0-9]+(?:\.[0-9]+)?)\s*(?:배|x|times)",
        text, re.I,
    )
    if not future:
        future = re.search(
            r"(?:interposer|인터포저)[^.]{0,180}?([0-9]+(?:\.[0-9]+)?)\s*(?:배|x|times)\s*까지",
            text, re.I,
        )
    if not future:
        future = re.search(
            r"([0-9]+(?:\.[0-9]+)?)\s*(?:배|x|times)[^.]{0,80}?(?:interposer|인터포저)",
            text, re.I,
        )
    if future:
        obs["reported_future_interposer_reticle_x"] = float(future.group(1))
        if any(k in low for k in ("보인다", "전망", "예상", "looks set", "expected", "projected")):
            obs["reported_future_interposer_stage"] = "industry_projection"

    tm = re.search(
        r"(?:hbm4e)[^.]{0,160}?(?:열\s*저항|thermal\s+resistance)[^%]{0,80}?([0-9]+(?:\.[0-9]+)?)\s*%",
        text, re.I,
    )
    if tm:
        obs["hbm4e_thermal_resistance_improvement_pct"] = float(tm.group(1))

    hm = re.search(
        r"(?:hcb|hybrid\s+copper\s+bonding|하이브리드\s*구리\s*본딩)[^.]{0,180}?(?:열\s*저항|thermal\s+resistance)[^%]{0,80}?([0-9]+(?:\.[0-9]+)?)\s*%",
        text, re.I,
    )
    if hm:
        obs["hcb_thermal_resistance_improvement_pct"] = float(hm.group(1))

    if any(k in low for k in ("hcb", "hybrid copper bonding", "하이브리드 구리 본딩", "하이브리드 본딩")):
        hcb_mass_production = (
            "hbm4e" in low
            and (
                any(k in low for k in ("양산 적용", "양산에 적용", "mass production adoption", "adopted for mass production"))
                or bool(re.search(
                    r"hbm4e[^.]{0,80}?양산[^.]{0,80}?(?:hcb|하이브리드\s*(?:구리\s*)?본딩)[^.]{0,80}?적용",
                    low, re.I,
                ))
                or bool(re.search(
                    r"(?:hcb|하이브리드\s*(?:구리\s*)?본딩)[^.]{0,80}?hbm4e[^.]{0,80}?양산[^.]{0,80}?적용",
                    low, re.I,
                ))
            )
        )
        if hcb_mass_production:
            obs["hcb_stage"] = "hbm4e_mass_production"
        elif (
            "hbm4e" in low
            and any(k in low for k in ("일부 사업화", "partial commercialization", "commercialization starting"))
        ):
            obs["hcb_stage"] = "hbm4e_partial_commercialization"
        elif any(k in low for k in ("customer sample", "샘플을 고객", "고객사에 보냈")):
            obs["hcb_stage"] = "customer_sample"
        elif any(k in low for k in ("gtc 2026", "소개했다", "showcase", "showcased", "공개했다")):
            obs["hcb_stage"] = "technology_showcase"

    if "hpb" in low or "heat path block" in low or "히트패스블록" in low:
        if (
            "hbm4e" in low
            and any(k in low for k in ("양산 적용", "양산에 적용", "mass production adoption", "adopted for mass production"))
        ):
            obs["hpb_stage"] = "hbm4e_mass_production"
        elif "hbm4e" in low and any(k in low for k in ("검증 중", "검증중", "validating", "validation")):
            obs["hpb_stage"] = "hbm4e_validation"
        if "hbm5" in low and any(k in low for k in ("적용 계획", "적용할 계획", "plans to adopt", "planned for")):
            obs["hpb_target_generation"] = "hbm5"

    package_system = (
        ("패키지" in text and ("시스템" in text or "server" in low))
        and ("냉각" in text or "cooling" in low)
    )
    if package_system:
        if any(k in low for k in ("도입했다", "도입한다", "adopted", "deployed", "in production")):
            obs["package_system_cooling_stage"] = "adopted"
        elif any(k in low for k in ("검토", "가능성", "consider", "under review", "possibility")):
            obs["package_system_cooling_stage"] = "reported_review"

    if not obs:
        return None
    obs.update({
        "source": event.get("origin_source") or event.get("source") or "",
        "source_url": event.get("direct_link") or "",
        "observed_at": event.get("published_at_kst") or "",
    })
    return obs


def merge_samsung_hbm4e_thermal_package(old: dict, obs: dict) -> dict:
    out = dict(old or {})
    for key, value in obs.items():
        if value not in (None, ""):
            out[key] = value
    return out


def samsung_hbm4e_thermal_changes(old: dict, new: dict) -> list[str]:
    reasons: list[str] = []

    for field, label, threshold in (
        ("industry_current_interposer_reticle_x", "현재 인터포저 면적", 0.5),
        ("reported_future_interposer_reticle_x", "장기 인터포저 전망", 2.0),
        ("hbm4e_thermal_resistance_improvement_pct", "HBM4E 열저항 개선", 2.0),
        ("hcb_thermal_resistance_improvement_pct", "HCB 열저항 개선", 2.0),
    ):
        a, b = old.get(field), new.get(field)
        if a is not None and b is not None and abs(float(b) - float(a)) >= threshold:
            suffix = "배" if "reticle" in field else "%p"
            reasons.append(f"{label} {float(a):g}→{float(b):g}{suffix}")
        elif a is None and b is not None:
            suffix = "배" if "reticle" in field else "%"
            reasons.append(f"{label} {float(b):g}{suffix} 신규 확인")

    for field, label in (
        ("hcb_stage", "HCB 단계"),
        ("hpb_stage", "HPB 단계"),
        ("hpb_target_generation", "HPB 목표 세대"),
        ("package_system_cooling_stage", "패키지·시스템 냉각 단계"),
    ):
        a, b = old.get(field), new.get(field)
        if a != b and b:
            reasons.append(f"{label} {a or '미확인'}→{b}")

    return reasons


def samsung_hbm4e_thermal_event(state: dict, reasons: list[str]) -> dict:
    advanced = any(
        state.get(k) in ("hbm4e_mass_production", "adopted")
        for k in ("hcb_stage", "hpb_stage", "package_system_cooling_stage")
    )
    return {
        "category": "hbm4e_thermal_package",
        "fact_key": "samsung_hbm4e_thermal_" + (state.get("observed_at") or state.get("as_of") or ""),
        "headline_ko": "삼성 HBM4E 발열·인터포저·패키징 병목 변화",
        "fact_bullets": reasons,
        "verdict": (
            "HBM4E 양산 열관리 수단의 실제 채택 단계가 올라갔습니다. 수율·신뢰성·고객 승인과 함께 확인해야 합니다."
            if advanced else
            "발열·패키징 구조의 상태 변화입니다. 장기 인터포저 전망과 실제 HBM4E 양산 적용을 분리해 봅니다."
        ),
        "verification": "상태값 변화",
        "quality": "공식자료·신뢰보도 교차",
        "origin_source": state.get("source") or "",
        "source": state.get("source") or "",
        "published_at_kst": state.get("observed_at") or state.get("as_of") or "",
        "direct_link": state.get("source_url") or "",
        "article_text": "",
        "hbm4e_thermal_state": state,
    }



def extract_hbm_hybrid_official_observation(event: dict) -> dict | None:
    """Promote *explicit official HBM hybrid-bonding* milestones, not rumour.
    
    HBM4E MR-MUF shipments and generic hybrid-bonding research are excluded
    unless one sentence explicitly links hybrid bonding, HBM, and the stage.
    """
    # Without successfully fetching the *publisher's* article HTML, a
    # headline or syndicated RSS snippet cannot be promoted to official fact.
    if event.get("article_fetch_succeeded") is not True:
        return None
    url = event.get("direct_link") or ""
    host = (urlparse(url).hostname or "").lower()
    if host in ("news.skhynix.com", "news.skhynix.co.kr", "www.skhynix.com", "skhynix.com"):
        vendor = "skhynix"
    elif host in ("news.samsung.com", "semiconductor.samsung.com", "www.samsung.com", "samsung.com"):
        vendor = "samsung"
    else:
        return None
    # Keep title, summary, and body in separate semantic segments: joining
    # them with spaces could falsely attach an unrelated HBM4E shipment to
    # a hybrid-bonding headline.
    article = "\n".join(
        str(event.get(key) or "") for key in
        ("article_title", "article_description", "article_text")
    )
    sentences = re.split(r"(?<=[.!?。])\s+|\n+", article)
    best = ""
    for sentence in sentences:
        lower = sentence.lower().strip()
        # Newsroom articles regularly mention competitors. The issuer host
        # alone does not identify WHO achieved the milestone; require one
        # unambiguous issuer in the same short sentence.
        if not lower or len(lower) > 480:
            continue
        is_sk = bool(re.search(r"\bsk[\s-]*hynix\b|sk하이닉스|에스케이하이닉스", lower, re.I))
        is_samsung = bool(re.search(r"\bsamsung(?: electronics)?\b|삼성전자", lower, re.I))
        if (vendor == "skhynix" and not is_sk) or (vendor == "samsung" and not is_samsung):
            continue
        if is_sk and is_samsung:
            continue
        if not re.search(r"\bhbm(?:3e|4e?|5)?\b|고대역폭\s*메모리", lower, re.I):
            continue
        if not re.search(r"hybrid[\s-]*(?:copper[\s-]*)?bonding|hcb|하이브리드\s*(?:구리\s*)?본딩", lower, re.I):
            continue
        # Plans, forecasts, denials and rhetorical challenges are not actual
        # completed milestones. This is intentionally conservative.
        if re.search(
            r"\b(?:planned?|planning|will|aims?|targets?|expected|could|might|may|"
            r"not yet|not shipped|hasn't|has not|without|challenge|difficult|no|never)\b|"
            r"예정|계획|목표|추진|검토|예상|전망|고려|아직|미출하|미제공|어려움|난항",
            lower, re.I
        ):
            continue
        stage = ""
        if re.search(
            r"(?:양산\s*(?:돌입|개시|시작|출하)|"
            r"(?:began|started|commenced)\s+(?:mass|volume)\s+production|"
            r"mass[- ]production\s+(?:has\s+)?(?:begun|started))",
            lower, re.I
        ):
            stage = "hbm_mass_production_started"
        elif re.search(
            r"(?:파일럿|시험생산)\s*(?:라인|설비)?\s*(?:가동|시작|개시)|"
            r"(?:pilot\s*(?:line|production))\s*(?:began|started|running|operational)",
            lower, re.I
        ):
            stage = "pilot_line_running"
        elif re.search(
            r"(?:고객|customer)[^.]{0,90}?(?:신뢰성\s*검증|품질\s*인증|qualification|validation)[^.]{0,50}?"
            r"(?:통과|완료|passed|completed)|"
            r"(?:passed|completed)[^.]{0,45}?(?:customer\s+qualification|customer\s+validation|고객\s*검증)",
            lower, re.I
        ):
            stage = "customer_qualification_passed"
        elif (
            "mr-muf" not in lower and "mr muf" not in lower
            and re.search(r"customer|clients?|고객(?:사)?", lower, re.I)
            and re.search(
                r"(?:samples?|샘플)[^.]{0,75}?(?:shipped|delivered|sent|supplied|출하|전달|공급|발송)|"
                r"(?:shipped|delivered|sent|supplied|출하|전달|공급|발송)[^.]{0,75}?(?:samples?|샘플)",
                lower, re.I
            )
        ):
            stage = "customer_hbm_sample_shipped"
        elif re.search(
            r"(?:internal|in-house|test)\s+(?:prototype|sample)[^.]{0,30}?(?:made|produced|fabricated)|"
            r"(?:내부|시험)\s*(?:시제품|샘플)[^.]{0,30}?(?:제작|생산|완료)",
            lower, re.I
        ):
            stage = "internal_hbm_prototype"
        if stage and (
            not best or HBM_HYBRID_STAGE_RANK[stage] > HBM_HYBRID_STAGE_RANK[best]
        ):
            best = stage
    if not best:
        return None
    return {
        "vendor": vendor,
        "stage": best,
        "evidence": "official",
        "source_url": url,
        "observed_at": event.get("published_at_kst") or "",
    }


def merge_hbm_hybrid_official_observation(old: dict, observation: dict) -> dict:
    out = dict(old or {})
    vendor = observation.get("vendor")
    stage = observation.get("stage")
    if vendor not in ("skhynix", "samsung") or stage not in HBM_HYBRID_STAGE_RANK:
        return out
    if observation.get("evidence") != "official":
        return out
    # Revalidate the issuer's hostname even when a function caller has
    # erroneously tagged a non-official report as official.
    obs_host = (urlparse(observation.get("source_url") or "").hostname or "").lower()
    hosts = {
        "skhynix": {"news.skhynix.com", "news.skhynix.co.kr", "www.skhynix.com", "skhynix.com"},
        "samsung": {"news.samsung.com", "semiconductor.samsung.com", "www.samsung.com", "samsung.com"},
    }
    if obs_host not in hosts[vendor]:
        return out
    key = f"{vendor}_official_hybrid_stage"
    prev = out.get(key) or "technical_feasibility"
    if HBM_HYBRID_STAGE_RANK[stage] <= HBM_HYBRID_STAGE_RANK.get(prev, -1):
        return out
    out[key] = stage
    out[f"{vendor}_official_hybrid_customer_sample_verified"] = (
        HBM_HYBRID_STAGE_RANK[stage]
        >= HBM_HYBRID_STAGE_RANK["customer_hbm_sample_shipped"]
    )
    out[f"{vendor}_official_stage_source_url"] = observation["source_url"]
    out["last_official_stage_change_at"] = observation.get("observed_at") or ""
    return out


def hbm_hybrid_official_changes(old: dict, new: dict) -> list[str]:
    names = {"skhynix": "SK하이닉스", "samsung": "삼성전자"}
    changes = []
    for vendor, name in names.items():
        key = f"{vendor}_official_hybrid_stage"
        if HBM_HYBRID_STAGE_RANK.get(new.get(key), -1) > HBM_HYBRID_STAGE_RANK.get(old.get(key), -1):
            changes.append(f"{name} 하이브리드 본딩 HBM 공식 단계 {old.get(key) or '미확인'}→{new.get(key)}")
    return changes


def hbm_hybrid_bond_event(state: dict, reasons: list[str], *, initial: bool = False) -> dict:
    source = (
        state.get("primary_url") if initial else
        state.get("samsung_official_stage_source_url")
        or state.get("skhynix_official_stage_source_url")
        or state.get("primary_url")
    )
    change_at = state.get("last_official_stage_change_at") or "2026-10-08T16:04:00+09:00"
    return {
        "category": "hbm_hybrid_bonding",
        "fact_key": ("hbm_hybrid_bonding_report_20261008" if initial else
                     "hbm_hybrid_official_" + change_at),
        "headline_ko": ("하이브리드 본딩 경쟁력 격차 보도 · 공식 양산과 분리"
                        if initial else "하이브리드 본딩 고객 샘플·양산 단계 공식 변화"),
        "fact_bullets": list(reasons),
        "verdict": ("단일 익명 엔지니어 인터뷰로 양산 격차·실패를 확정할 수 없습니다."
                    if initial else "공식 고객 샘플·인증·양산 상태의 신규 변화를 확인합니다."),
        "verification": ("Damnang 원문 서두 확인 / TechPowerUp 재인용 / 양사 공식 HBM 실적과 구분"
                         if initial else "해당 제조사 공식 고객 샘플·생산 발표"),
        "quality": ("신뢰 보도·회사 공식자료 구분" if initial else "공식·회사자료"),
        "origin_source": ("Damnang(익명 전문가)" if initial else "공식 기업자료"),
        "source": "Damnang" if initial else "공식 기업자료",
        "published_at_kst": (change_at if not initial else "2026-10-08T16:04:00+09:00"),
        "direct_link": source,
        "article_text": "",
        "hybrid_bonding_state": dict(state),
    }


def render_hbm_hybrid_bonding_notice(e: dict, now: datetime) -> str:
    st = e["hybrid_bonding_state"]
    stage_ko = {
        "technical_feasibility": "기술 가능성 확인",
        "technology_showcase": "기술 공개·시연",
        "internal_hbm_prototype": "내부 HBM 시제품",
        "customer_hbm_sample_shipped": "고객용 HBM 샘플 발송",
        "customer_qualification_passed": "고객 검증 통과",
        "pilot_line_running": "파일럿 설비 가동",
        "hbm_mass_production_started": "HBM 양산 개시",
    }
    initial = e.get("fact_key") == "hbm_hybrid_bonding_report_20261008"
    lines = [
        "🚨 HBM 하이브리드 본딩 · 삼성전자 vs SK하이닉스",
        f"조회: {now.strftime('%Y-%m-%d %H:%M KST')}",
        ("정정 안내: 기존 단일 인터뷰 보도 알림의 표시·링크·단계 이름 수정. 새 기술 진전 아님."
         if e.get("format_correction") else ""),
        ("상태: 단일 익명 전문가 인터뷰 보도 · 회사 미확정"
         if initial else "상태: 하이브리드 본딩 HBM 공식 단계 신규 변화"),
        "",
        "■ 현재 제품과 미래 공정은 다릅니다",
        "• SK하이닉스 12단 HBM4E 고객 샘플(2026-06-18): 공식 확인, 어드밴스드 MR-MUF 적용. 하이브리드 본딩 샘플로 계산 금지.",
        "• 삼성전자 HBM4E 고객 샘플: 공식 확인. 하이브리드 본딩을 적용한 고객 샘플인지 별도 공식 확인 필요.",
        "• SK하이닉스 16단용 하이브리드 본딩 기술적 가능성 설명(공식 IR)과 고객사로 전달된 완성 HBM 샘플은 서로 다릅니다.",
        "",
        "■ 하이브리드 본딩 고객 샘플 검증",
        ("• SK하이닉스: 샘플 제작 지연 주장(익명 인터뷰) · 회사 공식 고객 샘플 확인: "
         + ("확인" if st.get("skhynix_official_hybrid_customer_sample_verified") else "미확인")),
        ("• 삼성전자: 고객에게 하이브리드 본딩 HBM 샘플 발송 주장(같은 인터뷰) · 회사 공식 확인: "
         + ("확인" if st.get("samsung_official_hybrid_customer_sample_verified") else "미확인")),
        f"• 공식 추적 단계: SK하이닉스 {stage_ko.get(st.get('skhynix_official_hybrid_stage'), '미확인')} / 삼성전자 {stage_ko.get(st.get('samsung_official_hybrid_stage'), '미확인')}",
        "• 원보도: Damnang 인터뷰 1곳 → TechPowerUp 재보도. 독립 검증 2곳 아님.",
        "",
        "■ 현재 돈 버는 사업과 실적",
        "• Counterpoint 2026년 2분기 HBM 매출점유율: SK하이닉스 50% / 삼성전자 33%. 이는 차세대 본딩 성숙도를 나타내는 값이 아닙니다.",
        "• 하이브리드 본딩 개발 지연이 기존 MR-MUF 기반 HBM 출하 중단 또는 즉시 매출 하락을 뜻하지 않습니다.",
        "",
        "■ 공정 병목·실패 경로",
        "• 정렬·표면 오염·구리 단차 → 접합 불량 → 다층 누적수율 저하 → 고온 동작 검사·신뢰성 검증 지연 → 고객 승인 연기.",
        "• 민감도 예시(실측 아님): 각 층 접합 양품률 99%이고 16개 독립 접합을 가정하면 0.99^16≈85.1%. 실제 수율·접합 횟수는 미공개.",
        "• 위험 관찰 기간: 향후 6~12개월 고객 샘플·인증·양산 전환. MR-MUF 개선은 대안이며 하이브리드 본딩 채택 시점은 고객 결정에 달립니다.",
        "",
        "■ 다음 새 알림",
        "• 공식 시제품 제작 → 고객 샘플 발송 → 고객 인증 완료 → 파일럿 → 양산을 분리해 추적.",
        "• 삼성전자/ SK하이닉스 실제 공식 발표, 장비 수주·공정시간·수율·고객 채택 변화만 단계 승격.",
        "• 원출처에 새로운 정보 없이 TechPowerUp 기사가 반복 인용되면 재전송하지 않음.",
        "",
        "출처:",
        "Damnang " + st.get("primary_url", ""),
        "TechPowerUp " + st.get("republisher_url", ""),
        "SK하이닉스 공식 " + HBM_HYBRID_SK_OFFICIAL,
        "삼성전자 공식 " + HBM_HYBRID_SAMSUNG_OFFICIAL,
        "Counterpoint " + HBM_HYBRID_SHARE_SOURCE,
    ]
    if not initial and e.get("fact_bullets"):
        lines.insert(5, "• 이번 공식 변화: " + " / ".join(e["fact_bullets"]))
    return "\n".join(line for line in lines if line).strip() + "\n"


def make_fact(event: dict) -> dict | None:
    e = dict(event)
    text = compact_fact_text(e)
    low = text.lower()
    cat = e.get("category") or ""
    bullets: list[str] = []
    headline = ""
    verdict = ""
    fact_key = ""

    if cat == "rubin_broker_model":
        old_gb, new_gb, share_8, share_12 = _bernstein_rubin_model_values(text)
        if old_gb is None or new_gb is None or old_gb <= 0 or new_gb <= 0:
            return None
        reduction_pct = (new_gb / old_gb - 1.0) * 100.0
        break_even = old_gb / new_gb - 1.0
        split = f"_8hi{share_8}_12hi{share_12}" if share_8 is not None and share_12 is not None else ""
        fact_key = f"bernstein_rubin_ultra_model_{old_gb}_to_{new_gb}{split}"
        headline = f"Bernstein Rubin Ultra HBM 모델 가정 {old_gb:,}GB→{new_gb:,}GB"
        bullets.append(f"• 증권사 모델 가정: 평균 HBM 용량을 {old_gb:,}GB→{new_gb:,}GB로 조정했습니다. NVIDIA 공식 최종 사양과 분리합니다.")
        bullets.append(f"• 변화율: {reduction_pct:.1f}% · 같은 HBM 비트 수요를 유지하려면 GPU 출하량이 약 +{break_even*100:.1f}% 필요합니다.")
        if share_8 is not None and share_12 is not None:
            bullets.append(f"• 적층 가정: 8단 {share_8}% / 12단 {share_12}%로 분리합니다.")
        if "server dram" in low or "conventional dram" in low:
            bullets.append("• 대체 경로: 줄어든 HBM 웨이퍼 여력이 conventional server DRAM으로 이동할 수 있다는 가정을 함께 확인합니다.")
        verdict = "🟡 HBM 비트 수요의 구조 변화 신호이지만 증권사 모델 가정입니다. NVIDIA 최종 사양·GPU 출하량·HBM4 고객 승인을 함께 확인합니다."

    elif cat == "hbm_supplier_relative":
        fact_key = _bernstein_supplier_relative_signature(text)
        if not fact_key:
            return None
        headline = "Bernstein HBM 공급사 상대가정 변화 — 삼성전자 점유율↑·SK하이닉스 진척/가격 가정↓"
        if "samsung" in low:
            bullets.append("• 삼성전자: Bernstein이 HBM 점유율 확대 방향을 반영했습니다.")
        if "sk hynix" in low or "sk하이닉스" in low:
            bullets.append("• SK하이닉스: HBM 진척·가격에 더 보수적인 가정을 반영한 신호입니다.")
        if "3.3 million" in low and "2.7 million" in low:
            bullets.append("• 목표주가 변화는 결과값으로만 기록하고, 알림 트리거는 HBM 점유율·진척·가격 가정 변화로 제한합니다.")
        verdict = "🟡 목표주가 변경만으로는 발송하지 않습니다. 공급사별 HBM 점유율·가격·고객 승인·양산 가정이 실제로 바뀐 경우에만 상태 변화로 봅니다."

    # SK hynix Indiana HBM4E: classify it correctly as a packaging/production-base event,
    # not as customer qualification.
    elif cat == "hbm4e_validation" and "hbm4e" in low and "indiana" in low and "2029" in low and ("sk hynix" in low or "sk hynix" in low.replace("-", " ")):
        fact_key = "skhynix_indiana_hbm4e_2029"
        headline = "SK하이닉스, 인디애나 HBM4E 첨단 패키징 양산을 2029년 3분기에 시작 계획"
        bullets.append("• 확인된 사실: 미국 인디애나 거점에서 차세대 HBM4E의 첨단 패키징·양산을 2029년 3분기부터 시작할 계획입니다.")
        if "cleanroom" in low and "2028" in low:
            bullets.append("• 일정: 클린룸은 2028년 하반기 가동을 목표로 합니다.")
        if "hundreds of thousands" in low and "wafer" in low:
            bullets.append("• 생산 규모: 장기적으로 연간 수십만 장 수준의 웨이퍼를 처리하는 생산능력을 목표로 제시했습니다.")
        if ("$4 billion" in low or "$4b" in low or "4 billion" in low) and "indiana" in low:
            bullets.append("• 투자: 인디애나 프로젝트는 40억달러 이상 규모입니다.")
        if "shortage" in low and "2030" in low:
            bullets.append("• 수요 신호: 곽노정 CEO는 메모리 공급 부족이 2030년 말까지 이어질 것으로 전망했습니다.")
        bullets.append("• 구분: 이 소식은 2027년 HBM4E 고객 인증 완료 뉴스가 아니라, 2029년 미국 후공정·첨단패키징 생산기지 일정입니다.")
        verdict = "🟢 중장기 HBM 공급 확대와 수요 강도를 확인하는 긍정 신호. 다만 단기 고객 인증 완료 신호로 해석하면 안 됩니다."

    elif cat == "hbm4e_validation" and "hbm4e" in low:
        company = ""
        if "sk hynix" in low or "sk하이닉스" in low:
            company = "SK하이닉스"
        elif "samsung" in low or "삼성전자" in low:
            company = "삼성전자"
        elif "micron" in low:
            company = "Micron"
        if not company:
            return None

        if any(k in low for k in ("qualification completed", "qualified", "validation completed", "certification completed", "인증 완료", "검증 완료")):
            fact_key = f"{company}_hbm4e_customer_validation"
            headline = f"{company}, HBM4E 고객 검증 완료 신호"
            bullets.append("• 확인된 사실: 기사에서 HBM4E 고객 검증·인증 완료를 명시했습니다.")
            verdict = "🟢 가장 중요한 강세 조건 중 하나인 고객 인증 완료에 해당합니다. 실제 양산 개시일과 계약물량을 다음으로 확인해야 합니다."
        elif any(k in low for k in ("yield", "수율")):
            ym = re.search(r"(?:yield|수율)[^%]{0,80}?([0-9]{1,3}(?:\.[0-9]+)?)\s*%", text, re.I)
            if not ym:
                ym = re.search(r"([0-9]{1,3}(?:\.[0-9]+)?)\s*%[^.]{0,80}?(?:yield|수율)", text, re.I)
            state = "개선" if any(k in low for k in ("improve", "improved", "ramp", "개선", "상승")) else "병목" if any(k in low for k in ("low yield", "bottleneck", "constraint", "낮은 수율", "병목", "제약")) else "변화"
            suffix = f"_{ym.group(1).replace('.','p')}pct" if ym else f"_{state}"
            fact_key = f"{company}_hbm4e_yield{suffix}"
            headline = f"{company}, HBM4E 수율 {state} 신호"
            if ym:
                bullets.append(f"• 수율: 기사에서 HBM4E 수율 {ym.group(1)}%가 제시됐습니다.")
            else:
                bullets.append(f"• 수율: 기사에서 HBM4E 수율 {state}가 명시됐습니다.")
            bullets.append("• 구분: 수율 변화는 고객 인증·양산 물량과 별도 상태로 추적합니다.")
            verdict = "🟡 수율이 개선되면 Rubin Ultra 공급 병목 완화 신호이고, 낮은 수율·병목이면 고객 승인과 양산 램프 지연 위험 신호입니다."
        elif any(k in low for k in ("mass production", "volume production", "양산")):
            year = next(iter(re.findall(r"20\d{2}", text)), "")
            q = ""
            if any(k in low for k in ("third quarter", "q3", "3분기")):
                q = " 3분기"
            elif any(k in low for k in ("second half", "h2", "하반기")):
                q = " 하반기"
            fact_key = f"{company}_hbm4e_mass_production_{year}_{q.strip()}"
            headline = f"{company}, HBM4E 양산 일정 구체화{(' — ' + year + q) if year else ''}"
            bullets.append(f"• 확인된 사실: HBM4E 양산 일정이 {year + q if year else '기사에서 구체화'}됐습니다.")
            verdict = "🟢 양산 일정 구체화는 긍정적이지만, 고객 인증 완료·실제 출하와는 별도로 확인합니다."
        elif any(k in low for k in ("sample", "samples", "샘플")):
            year = next(iter(re.findall(r"20\d{2}", text)), "")
            fact_key = f"{company}_hbm4e_sample_{year}"
            headline = f"{company}, HBM4E 샘플 공급 일정 확인"
            bullets.append("• 확인된 사실: HBM4E 샘플 공급·출하 단계에 관한 일정이 확인됐습니다.")
            verdict = "🟡 샘플 출하는 개발 진척 신호지만 고객 인증 완료나 매출 인식과 동일하지 않습니다."
        else:
            return None

    elif cat == "rubin_spec" and "rubin ultra" in low:
        capacities = [x for x in ("192GB", "288GB", "768GB", "1TB") if x.lower() in low]
        layers = []
        if "8-hi" in low or "8hi" in low or "8단" in low:
            layers.append("8hi")
        if "12-hi" in low or "12hi" in low or "12단" in low:
            layers.append("12hi")
        if not capacities and not layers:
            return None
        final_spec = any(k in low for k in ("final specification", "final spec", "finalized", "confirmed specification", "사양 확정", "최종 사양", "확정 사양"))
        stage = "final" if final_spec else "evaluation"
        key_bits = [stage] + [x.lower() for x in capacities] + layers
        fact_key = "rubin_ultra_spec_" + "_".join(key_bits)
        cap = "/".join(capacities)
        headline = f"Rubin Ultra HBM {'최종 사양 확정' if final_spec else '사양 변화 감지'}" + (f" — {cap}" if cap else "")
        if capacities:
            bullets.append(f"• 확인된 사양 후보: {cap}")
        bullets.append(f"• 단계: {'최종 사양 확정' if final_spec else '평가·검토 단계'}로 분리해 저장합니다.")
        if "8hi" in layers:
            bullets.append("• 적층 후보: 8단 HBM 구성이 언급됐습니다.")
        if "12hi" in layers:
            bullets.append("• 적층 후보: 12단 HBM 구성이 언급됐습니다.")
        bw = re.findall(r"\d+(?:\.\d+)?\s*TB/s", text, re.I)
        if bw:
            bullets.append(f"• 대역폭: {', '.join(dict.fromkeys(bw))}")
        if "192gb" in low:
            bullets.append(f"• 숫자: 288GB→192GB면 GPU당 HBM은 -33.3%, 총 비트 수요 상쇄에는 GPU 출하 +{BREAKEVEN_GPU_GROWTH*100:.0f}%가 필요합니다.")
            verdict = "🟡 192GB만으로 수요 붕괴 판정 금지. 최종 사양·대역폭·GPU 총출하를 함께 확인해야 합니다."
        elif final_spec:
            verdict = "🟢 Rubin Ultra 최종 HBM 적층·용량 사양이 확정된 신호입니다. 공급사 고객 승인과 양산 물량을 다음 단계로 확인합니다."
        else:
            verdict = "🟡 공급망 사양 정보입니다. NVIDIA 공식 확정 여부를 별도로 확인합니다."

    elif cat == "rubin_shipments" and ("rubin ultra" in low or "nvl576" in low):
        if not any(k in low for k in ("shipment", "ship", "deployment", "order", "production", "ramp", "출하", "도입", "주문", "양산")):
            return None
        fact_key = "rubin_ultra_nvl576_shipments_" + "_".join(re.findall(r"20\d{2}", text)[:1])
        headline = "Rubin Ultra·NVL576 출하·도입 변화 확인"
        bullets.append("• 확인된 사실: Rubin Ultra 또는 NVL576의 출하·도입·양산 일정 변화가 기사에서 명시됐습니다.")
        numbers = re.findall(r"\b\d{2,6}\s*(?:GPU|GPUs|대)\b", text, re.I)
        if numbers:
            bullets.append(f"• 물량 단서: {', '.join(dict.fromkeys(numbers))}")
        bullets.append(f"• 상쇄선: GPU당 HBM이 288GB→192GB로 줄면 전체 HBM 비트를 유지하려면 GPU 출하가 최소 +{BREAKEVEN_GPU_GROWTH*100:.0f}% 늘어야 합니다.")
        verdict = "🟢 실제 출하·고객 도입 확대면 HBM 총수요 판단에 직접 반영합니다. 단순 로드맵 재언급은 제외합니다."

    elif cat == "hbm_2027_contract" and "2027" in low and "hbm" in low:
        pcts = pct_tokens(text)
        has_price = any(k in low for k in ("price", "pricing", "asp", "가격", "판가"))
        has_volume = any(k in low for k in ("volume", "allocation", "supply", "contract", "lta", "agreement", "물량", "공급", "계약"))
        signed = any(k in low for k in ("contract signed", "agreement signed", "agreement finalized", "deal finalized", "negotiations concluded", "계약 체결", "협상 타결", "가격 확정", "계약 확정"))
        stalled = any(k in low for k in ("stalled", "unresolved", "deadlock", "협상 교착", "미타결", "협상 난항"))
        if not (has_price or has_volume or signed or stalled):
            return None
        if not pcts and not (signed or stalled):
            return None
        stage = "signed" if signed else "stalled" if stalled else "quoted"
        key_parts = [stage] + [p.replace("%", "pct") for p in pcts[:3]]
        fact_key = "hbm_2027_contract_" + "_".join(key_parts)
        suffix = f" — {' / '.join(pcts[:3])}" if pcts else ""
        headline = f"2027 HBM 계약가격·물량 변화 ({'체결·확정' if signed else '협상 교착' if stalled else '가격 제시'}){suffix}"
        if pcts and has_price:
            bullets.append(f"• 가격: 기사에서 2027년 HBM 가격·평균판매단가 관련 수치 {' / '.join(pcts[:3])}가 제시됐습니다.")
        if signed:
            bullets.append("• 계약 단계: 협상 전망이 아니라 계약 체결·가격 확정 단계로 올라갔습니다.")
        elif stalled:
            bullets.append("• 계약 단계: 2027년 공급·가격 협상이 아직 타결되지 않은 상태입니다.")
        if has_volume:
            bullets.append("• 물량: 계약물량·공급배정이 유지 또는 증가하는지 반드시 가격과 함께 판정합니다.")
        verdict = "🟢 가격 상승과 계약물량 유지·증가가 동시에 확인되면 강한 신호입니다." if signed else "🟡 협상 단계에서는 전망치와 실제 계약가격·물량을 분리합니다."

    elif cat == "hbm_wafer_economics" and "hbm" in low and "ddr5" in low:
        if not any(k in low for k in ("wafer revenue", "profitability", "economics", "64gb rdimm", "웨이퍼 매출", "수익성", "채산성")):
            return None
        hbm_below = any(k in low for k in ("overtaken by ddr5", "fell below", "lower than ddr5", "ddr5 overtook", "ddr5가 추월", "ddr5보다 낮"))
        hbm_above = any(k in low for k in ("hbm overtook", "hbm surpassed", "hbm higher than", "hbm이 추월", "hbm이 상회"))
        state = "hbm_below_ddr5" if hbm_below else "hbm_above_ddr5" if hbm_above else "economics_update"
        fact_key = "hbm_ddr5_wafer_economics_" + state
        headline = "HBM↔DDR5 웨이퍼 경제성 변화"
        if hbm_below:
            bullets.append("• 현재 방향: HBM의 웨이퍼당 매출·수익성이 DDR5 64GB RDIMM보다 낮아진 신호입니다.")
        elif hbm_above:
            bullets.append("• 현재 방향: HBM의 웨이퍼당 매출·수익성이 DDR5보다 다시 높아진 신호입니다.")
        else:
            bullets.append("• 현재 방향: HBM과 DDR5의 웨이퍼당 매출·수익성 비교가 새로 갱신됐습니다.")
        bullets.append("• 의미: 이 격차가 HBM 가격 협상과 DRAM 웨이퍼 배분의 경제적 기준이 됩니다.")
        verdict = "🟡 HBM 경제성이 DDR5보다 낮으면 HBM 가격 인상 압력·배분 제약이 커지고, 다시 상회하면 HBM 증산 유인이 개선됩니다."

    elif cat == "memory_migration":
        if (
            "kv cache" in low
            and any(k in low for k in ("offload", "offloading", "오프로드"))
            and "hbm" in low
            and any(k in low for k in (
                "capacity", "reduce", "reduction", "lower", "smaller",
                "용량", "축소", "하향", "줄", "8-hi", "8hi", "12-hi", "12hi", "4-hi", "4hi", "8단", "12단", "4단",
            ))
        ):
            stacks = []
            for label, aliases in (
                ("4단", ("4-hi", "4hi", "4단")),
                ("8단", ("8-hi", "8hi", "8단")),
                ("12단", ("12-hi", "12hi", "12단")),
            ):
                if any(a in low for a in aliases):
                    stacks.append(label)
            capacities = list(dict.fromkeys(re.findall(r"\b\d+(?:\.\d+)?\s*(?:GB|TB)\b", text, re.I)))[:4]
            mainstream = []
            niche = []
            if any(k in low for k in ("mainstream", "주류", "중심", "유지")):
                if "8단" in stacks:
                    mainstream.append("8hi")
                if "12단" in stacks:
                    mainstream.append("12hi")
            if any(k in low for k in ("niche", "limited", "제한", "니치")) and "4단" in stacks:
                niche.append("4hi")

            if mainstream or niche:
                key_parts = []
                if mainstream:
                    key_parts.append("mainstream_" + "_".join(mainstream))
                if niche:
                    key_parts.append("niche_" + "_".join(niche))
            else:
                key_parts = [x.replace("단", "hi") for x in stacks]
            key_parts += [re.sub(r"\s+", "", x).lower() for x in capacities]
            fact_key = "hbm_capacity_kv_offload_" + ("_".join(key_parts) if key_parts else "shift")
            headline = "HBM 용량 축소·KV 캐시 오프로딩 구조 변화"
            bullets.append("• 상태 변화: GPU 내부 HBM 용량을 줄이는 방향과 KV 캐시를 외부 메모리 계층으로 넘기는 오프로딩이 함께 거론됐습니다.")
            if stacks:
                bullets.append(f"• 적층 구성: {', '.join(stacks)} HBM 구성이 언급됐습니다.")
            if capacities:
                bullets.append(f"• 용량 단서: {', '.join(capacities)}")
            if any(k in low for k in ("cpu ram", "host memory", "cxl", "ssd pod", "enterprise ssd", "essd", "local ssd")):
                tiers = []
                for label, aliases in (
                    ("CPU 메모리", ("cpu ram", "host memory")),
                    ("CXL", ("cxl",)),
                    ("기업용 eSSD", ("enterprise ssd", "essd")),
                    ("SSD POD", ("ssd pod",)),
                    ("로컬 SSD", ("local ssd",)),
                ):
                    if any(a in low for a in aliases):
                        tiers.append(label)
                if tiers:
                    bullets.append(f"• 대체 계층: {', '.join(tiers)}로 KV 캐시 수요가 이동하는 신호입니다.")
            bullets.append("• 해석: HBM 용량 감소를 HBM 수요 감소로 바로 등치하지 않습니다. 대역폭 요구, GPU 출하량, CPU 메모리·CXL·eSSD 수요 이동을 함께 봅니다.")
            verdict = "🟡 HBM 비트 수요에는 역풍이 될 수 있지만, KV 캐시 오프로딩이 CPU 메모리·CXL·eSSD 수요를 키우는 구조적 이동 신호입니다."
        elif "hbm3e" in low and "ddr5" in low and ("3x" in low or "3 x" in low or "three times" in low or "3배" in low):
            fact_key = "hbm3e_wafer_capacity_3x_ddr5"
            headline = "Micron: HBM3E가 DDR5보다 웨이퍼 생산능력을 약 3배 더 소모"
            bullets.append("• 확인된 사실: HBM3E는 같은 비트 생산 기준으로 DDR5보다 웨이퍼 생산능력을 약 3배 더 소모한다는 설명입니다.")
            bullets.append("• 의미: HBM 세대가 올라갈수록 웨이퍼 투입 부담이 커져, 공급 확대 속도가 비트 수요 증가를 따라가기 어려울 수 있습니다.")
            verdict = "🟢 HBM 공급 제약과 가격결정력을 뒷받침하는 신호. 다만 DDR5·SOCAMM2·eSSD 수요 이동과는 별개의 공급효율 이슈입니다."
        elif "socamm2" in low and any(k in low for k in ("mass production", "shipment", "supply", "order", "양산", "출하", "공급", "주문")):
            fact_key = "socamm2_demand_supply_" + "_".join(re.findall(r"20\d{2}", text)[:1])
            headline = "SOCAMM2 공급·주문 변화 확인"
            bullets.append("• 확인된 사실: SOCAMM2의 양산·출하·공급 또는 주문 변화가 기사에서 명시됐습니다.")
            verdict = "🟢 HBM 밖으로 내려가는 대용량 메모리 계층 수요가 실제 주문으로 연결되는지 확인하는 긍정 신호입니다."
        elif any(k in low for k in ("enterprise ssd", "essd")) and any(k in low for k in ("demand", "order", "shipment", "supply", "수요", "주문", "출하", "공급")):
            fact_key = "enterprise_ssd_ai_demand_" + "_".join(re.findall(r"20\d{2}", text)[:1])
            headline = "기업용 eSSD AI 수요·주문 변화 확인"
            bullets.append("• 확인된 사실: 기업용 eSSD의 AI 관련 수요·주문·출하 변화가 기사에서 명시됐습니다.")
            verdict = "🟢 HBM 용량 보완 계층으로 기업용 SSD 수요가 실제 증가하는지 확인하는 신호입니다."
        else:
            return None
    else:
        return None

    e["fact_key"] = fact_key
    e["headline_ko"] = headline
    e["fact_bullets"] = bullets
    e["verdict"] = verdict
    return e


def fact_signature_from_raw(event: dict) -> str:
    text = f"{event.get('title','')} {event.get('description','')}".lower()
    cat = event.get("category") or ""
    if "hbm4e" in text and "indiana" in text and "2029" in text and "sk hynix" in text:
        return "skhynix_indiana_hbm4e_2029"
    if (
        "kv cache" in text
        and any(k in text for k in ("offload", "offloading", "오프로드"))
        and "hbm" in text
        and any(k in text for k in ("capacity", "reduce", "reduction", "용량", "축소", "하향", "8-hi", "8hi", "12-hi", "12hi", "4-hi", "4hi", "8단", "12단", "4단"))
    ):
        stacks = []
        for label, aliases in (
            ("4hi", ("4-hi", "4hi", "4단")),
            ("8hi", ("8-hi", "8hi", "8단")),
            ("12hi", ("12-hi", "12hi", "12단")),
        ):
            if any(a in text for a in aliases):
                stacks.append(label)
        mainstream = []
        niche = []
        if any(k in text for k in ("mainstream", "주류", "중심", "유지")):
            if "8hi" in stacks:
                mainstream.append("8hi")
            if "12hi" in stacks:
                mainstream.append("12hi")
        if any(k in text for k in ("niche", "limited", "제한", "니치")) and "4hi" in stacks:
            niche.append("4hi")
        if mainstream or niche:
            parts = []
            if mainstream:
                parts.append("mainstream_" + "_".join(mainstream))
            if niche:
                parts.append("niche_" + "_".join(niche))
            return "hbm_capacity_kv_offload_" + "_".join(parts)
        return "hbm_capacity_kv_offload_" + ("_".join(stacks) if stacks else "shift")
    if "hbm3e" in text and "ddr5" in text and ("3x" in text or "three times" in text or "3배" in text):
        return "hbm3e_wafer_capacity_3x_ddr5"
    if cat == "rubin_broker_model":
        old_gb, new_gb, share_8, share_12 = _bernstein_rubin_model_values(text)
        if old_gb is not None and new_gb is not None:
            split = f"_8hi{share_8}_12hi{share_12}" if share_8 is not None and share_12 is not None else ""
            return f"bernstein_rubin_ultra_model_{old_gb}_to_{new_gb}{split}"
    if cat == "hbm_supplier_relative":
        return _bernstein_supplier_relative_signature(text)
    if cat == "rubin_spec" and "rubin ultra" in text:
        caps = [x for x in ("192gb", "288gb", "768gb", "1tb") if x in text]
        if caps:
            return "rubin_ultra_spec_" + "_".join(caps)
    if cat == "hbm_2027_contract" and "2027" in text:
        pcts = re.findall(r"[+-]?\d+(?:\.\d+)?%", text)
        if pcts:
            return "hbm_2027_contract_" + "_".join(p.replace("%", "pct") for p in pcts[:3])
    return ""


def verification_for(event: dict, raw_events: list[dict]) -> str:
    quality = event.get("quality") or ""
    origin = event.get("origin_source") or ""
    if quality.startswith("공식"):
        return "공식자료 확인"
    if "Reuters" in origin:
        return "Reuters 원문/재전재 확인"
    if quality.startswith("신뢰"):
        return "신뢰 보도 확인"

    key = event.get("fact_key") or ""
    if not key:
        return ""
    sources = set()
    for raw in raw_events:
        if fact_signature_from_raw(raw) == key:
            sources.add((raw.get("source") or "").lower())
    sources.discard("")
    if len(sources) >= 2:
        return f"교차검증 {len(sources)}곳"
    return ""


def choose_verified_events(fresh_unseen: list[dict], raw_events: list[dict], seen_fact_keys: set[str]) -> tuple[list[dict], list[str]]:
    errors: list[str] = []
    candidates: list[dict] = []
    for raw in fresh_unseen:
        if raw.get("category") in ("citi_hbm_outlook", "jpm_hbm_structural", "micron_sca_visibility", "samsung_hbm4_price", "hbm4e_thermal_package", "hbm_hybrid_bonding", "samsung_nextgen_hbm", "nvhbm_architecture", "morgan_stanley_nvidia_hbm_margin", "rubin_hbm_option_set"):
            continue
        source_low = (raw.get("source") or "").lower()
        if any(k in source_low for k in LOW_VALUE_SOURCE_HINTS):
            # 저품질 집계 사이트는 단독 발송 금지. 같은 사실의 더 나은 출처가 있으면 그쪽을 사용한다.
            continue
        enriched = enrich_event(raw)
        if not enriched.get("link_verified"):
            errors.append(f"원문 URL 확인 실패: {raw.get('source')} | {raw.get('title')}")
            continue
        fact = make_fact(enriched)
        if not fact:
            errors.append(f"핵심 사실 자동추출 실패로 발송 제외: {raw.get('source')} | {raw.get('title')}")
            continue
        if fact.get("fact_key") in seen_fact_keys:
            continue
        verification = verification_for(fact, raw_events)
        if not verification:
            errors.append(f"교차검증 부족으로 발송 제외: {raw.get('source')} | {raw.get('title')}")
            continue
        fact["verification"] = verification
        candidates.append(fact)

    # 같은 사실이 여러 매체에 재전재된 경우 가장 좋은 출처 한 건만 남긴다.
    chosen: dict[str, dict] = {}
    for e in candidates:
        key = e.get("fact_key") or normalized_title(e.get("headline_ko") or e.get("title") or "")
        old = chosen.get(key)
        if old is None:
            chosen[key] = e
            continue
        if quality_rank(e.get("quality") or "") > quality_rank(old.get("quality") or ""):
            chosen[key] = e
        elif quality_rank(e.get("quality") or "") == quality_rank(old.get("quality") or "") and (e.get("published_at_kst") or "") > (old.get("published_at_kst") or ""):
            chosen[key] = e
    return sorted(chosen.values(), key=lambda x: x.get("published_at_kst") or ""), errors


def fetch_fx():
    from fx_api import daily_krw
    try:
        q = daily_krw()
        return {"rate": q.rate, "date": q.basis, "source": q.source, "error": ""}
    except RuntimeError as exc:
        return {"rate": None, "date": "", "source": "환율 API", "error": str(exc)}


def load_state() -> tuple[dict, bool]:
    if not DATA.exists():
        return {}, True
    try:
        return json.loads(DATA.read_text(encoding="utf-8")), False
    except Exception:
        return {}, True


def write_json(path: pathlib.Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fmt_krw_usd(value: float, rate: float | None) -> str:
    if rate is None:
        return "원화 환산 불가"
    won = value * rate
    return f"약 {won:,.0f}원"


def krw_large_usd(value: float, rate: float | None) -> str:
    if rate is None:
        return "원화 환산 불가"
    won = value * rate
    eok = int(round(won / 100_000_000))
    if eok >= 10000:
        jo, rem = divmod(eok, 10000)
        return f"약 {jo:,}조{rem:,}억원" if rem else f"약 {jo:,}조원"
    return f"약 {eok:,}억원"


def extract_price_notes(text: str, rate: float | None) -> list[str]:
    notes: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*/\s*(GB|Gb)", text, re.I):
        usd = float(m.group(1))
        unit = m.group(2)
        key = f"{usd}/{unit}"
        if key not in seen:
            seen.add(key)
            notes.append(f"• 가격 환산: ${usd:g}/{unit} = {fmt_krw_usd(usd, rate)}/{unit}")
    for m in re.finditer(r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*(billion|million|B|M)\b", text, re.I):
        suffix = m.group(2).lower()
        val = float(m.group(1)) * (1_000_000_000 if suffix in ("b", "billion") else 1_000_000)
        key = f"{val}usd"
        if key not in seen:
            seen.add(key)
            notes.append(f"• 금액 환산: {m.group(0)} = {krw_large_usd(val, rate)}")
    return notes


def build_alert(now: datetime, events: list[dict], fx: dict) -> str:
    # Give each hybrid-bonding alert an independent Telegram message, even
    # when another HBM event is found in the same hourly collector run.
    # Do not put speculative Rubin demand/GPU scenario text above this risk.
    hybrid = [e for e in events if e.get("category") == "hbm_hybrid_bonding"]
    if hybrid:
        normal = [e for e in events if e.get("category") != "hbm_hybrid_bonding"]
        sections = ([build_alert(now, normal, fx)] if normal else [])
        sections += [render_hbm_hybrid_bonding_notice(e, now) for e in hybrid]
        return "\n\n<<<TELEGRAM_MESSAGE_BREAK>>>\n\n".join(
            section.strip() for section in sections if section.strip()
        ) + "\n"
    rate = fx.get("rate")
    lines = [
        "🚨 Rubin/HBM 구조 변화 감시",
        "",
        f"조회시각: {now.strftime('%Y-%m-%d %H:%M:%S KST')}",
        f"신규 핵심 변화: {len(events)}건",
        f"기준선: 일반 Rubin 288GB HBM4 / 디스펙 상쇄선 GPU 출하 +{BREAKEVEN_GPU_GROWTH*100:.0f}%",
    ]
    if rate is not None:
        lines.append(f"원화 환산: 1달러={rate:,.2f}원 / 기준일 {fx.get('date') or '미표시'}")

    grouped: dict[str, list[dict]] = {}
    for e in events:
        grouped.setdefault(e["category"], []).append(e)

    n = 1
    for category in ("rubin_spec", "rubin_broker_model", "hbm_supplier_relative", "hbm4e_validation", "hbm4e_thermal_package", "hbm_hybrid_bonding", "rubin_shipments", "rubin_hbm_option_set", "samsung_hbm4_price", "samsung_nextgen_hbm", "nvhbm_architecture", "hbm_2027_contract", "morgan_stanley_nvidia_hbm_margin", "jpm_hbm_structural", "micron_sca_visibility", "citi_hbm_outlook", "hbm_wafer_economics", "memory_migration"):
        group = grouped.get(category) or []
        if not group:
            continue
        if category == "hbm_hybrid_bonding":
            lines += ["", "<<<TELEGRAM_MESSAGE_BREAK>>>", ""]
            for item in group:
                lines.append(render_hbm_hybrid_bonding_notice(item, now).strip())
                n += 1
            continue
        if category == "hbm4e_thermal_package" and n > 1:
            lines += ["", "<<<TELEGRAM_MESSAGE_BREAK>>>", "🚨 삼성 HBM4E 발열·패키징 병목 감시", ""]
        if category == "rubin_hbm_option_set" and n > 1:
            lines += ["", "<<<TELEGRAM_MESSAGE_BREAK>>>", "🚨 Rubin Ultra HBM4/HBM4E 옵션 감시", ""]
        if category == "samsung_hbm4_price" and n > 1:
            lines += ["", "<<<TELEGRAM_MESSAGE_BREAK>>>", "🚨 삼성전자 2027 HBM4 계약가격·협상력 감시", ""]
        if category == "samsung_nextgen_hbm" and n > 1:
            lines += ["", "<<<TELEGRAM_MESSAGE_BREAK>>>", "🚨 삼성 Custom HBM·HBM5·zHBM 맞춤형 로드맵 감시", ""]
        if category == "nvhbm_architecture" and n > 1:
            lines += ["", "<<<TELEGRAM_MESSAGE_BREAK>>>", "🚨 NVIDIA NVHBM·Custom HBM 구조 전환 감시", ""]
        if category == "morgan_stanley_nvidia_hbm_margin" and n > 1:
            lines += ["", "<<<TELEGRAM_MESSAGE_BREAK>>>", "🚨 Morgan Stanley NVIDIA HBM 가격 감내력·마진 감시", ""]
        if category == "jpm_hbm_structural" and n > 1:
            lines += ["", "<<<TELEGRAM_MESSAGE_BREAK>>>", "🚨 J.P. Morgan HBM 구조적 수급·가격 감시", ""]
        if category == "micron_sca_visibility" and n > 1:
            lines += ["", "<<<TELEGRAM_MESSAGE_BREAK>>>", "🚨 Micron 장기계약·RPO·고객예치금 감시", ""]
        if category == "citi_hbm_outlook" and n > 1:
            lines += ["", "<<<TELEGRAM_MESSAGE_BREAK>>>", "🚨 Citi HBM 2027~2028 수급·가격 감시", ""]
        if category == "memory_migration" and n > 1:
            lines += ["", "<<<TELEGRAM_MESSAGE_BREAK>>>", "🚨 HBM 용량 축소→KV 캐시 외부 메모리 전환", ""]
        lines += ["", f"■ {CATEGORY_KO[category]}"]
        for e in group[:5]:
            full_text = compact_fact_text(e)
            lines += [
                f"{n}. {e['headline_ko']}",
                f"- 출처: {e.get('origin_source') or e.get('source')} / {e.get('verification')}",
                f"- 공개시각: {e.get('published_at_kst') or '확인 불가'}",
            ]
            lines.extend(e.get("fact_bullets") or [])
            if category == "rubin_hbm_option_set" and e.get("rubin_hbm_options_state"):
                rs = e["rubin_hbm_options_state"]
                lines.append(f"• 단계: {rs.get('stage') or '미확인'}")
                lines.append("• 후보 조합: " + ", ".join(rs.get("candidate_options") or ["미확인"]))
                if rs.get("reported_preferred_option"):
                    lines.append(
                        f"• 현재 업계 우세 신호: {rs.get('previous_reported_preferred_option') or '미확인'}→"
                        f"{rs.get('reported_preferred_option')} · {rs.get('reported_preference_stage') or '미확인'}"
                    )
                    lines.append(
                        "• 우세 신호 근거: " + ", ".join(rs.get("reported_preference_support_sources") or ["미확인"])
                    )
                    if rs.get("reported_preference_direct_fetch_verified") is False:
                        lines.append("• X 직접 열람: 미검증 — 사용자 제공 원문은 기준선으로만 저장하고 독립 출처 확인 전 공식 사양으로 승격하지 않습니다.")
                lines.append("• 구분: 후보군, 단일 업계 우세 신호, 교차검증 우세 신호, NVIDIA 공식 최종 사양을 서로 분리합니다.")
            if category == "samsung_hbm4_price" and e.get("samsung_hbm4_price_state"):
                ss = e["samsung_hbm4_price_state"]
                band = ss.get("offered_price_band")
                if band == "mid_to_high_4_usd_per_gb":
                    lines.append("• 삼성 제시가격: 1Gb당 4달러대 중후반(기사 표현 그대로, 임의 범위 환산 안 함)")
                lo, hi = ss.get("offered_price_usd_per_gb_min"), ss.get("offered_price_usd_per_gb_max")
                if lo is not None and hi is not None:
                    if rate is not None:
                        lines.append(f"• 확정 공개 숫자: {float(lo):.2f}~{float(hi):.2f}달러/Gb (약 {float(lo)*rate:,.0f}~{float(hi)*rate:,.0f}원/Gb)")
                    else:
                        lines.append(f"• 확정 공개 숫자: {float(lo):.2f}~{float(hi):.2f}달러/Gb")
                if ss.get("reference_hbm3e_usd_per_gb") is not None:
                    lines.append(f"• 비교 HBM3E: 약 {float(ss['reference_hbm3e_usd_per_gb']):.2f}달러/Gb")
                if ss.get("price_multiple_floor") is not None:
                    lines.append(f"• 가격배수: HBM3E 대비 {float(ss['price_multiple_floor']):.1f}배 이상")
                lines.append(f"• 계약 단계: {ss.get('stage') or '미확인'} · 물량 단계: {ss.get('volume_stage') or '미확인'}")
                if ss.get("reported_supply_status"):
                    lines.append(f"• 공급 상태: {ss['reported_supply_status']} — '사실상 완판' 보도와 실제 고객별 체결물량을 분리")
                if ss.get("pricing_power_stage"):
                    lines.append(f"• 가격 협상력: {ss['pricing_power_stage']} · 근거: {ss.get('pricing_power_driver') or '미확인'}")
                if ss.get("performance_stable_gbps") is not None or ss.get("performance_max_gbps") is not None:
                    lines.append(
                        f"• 성능 근거: 안정 {float(ss.get('performance_stable_gbps') or 0):g}Gbps · "
                        f"최대 {float(ss.get('performance_max_gbps') or 0):g}Gbps · "
                        f"업계표준 {float(ss.get('industry_standard_gbps') or 0):g}Gbps"
                    )
                if ss.get("stack_bandwidth_tbps") is not None:
                    lines.append(
                        f"• 스택 대역폭: 최대 {float(ss['stack_bandwidth_tbps']):g}TB/s · "
                        f"고객 요구 {float(ss.get('customer_requirement_tbps') or 0):g}TB/s"
                    )
                if ss.get("industry_hbm_dram_wafer_share_2027_pct") is not None:
                    lines.append(
                        f"• HBM의 D램 웨이퍼 생산능력 비중: 현재 20%대 보도 → "
                        f"2027년 약 {float(ss['industry_hbm_dram_wafer_share_2027_pct']):g}% 전망"
                    )
                if ss.get("target_close_month"):
                    lines.append(f"• 협상 마무리 목표: {ss['target_close_month']}")
                lines.append("• 구분: 제시가격·협상가격·'사실상 완판' 보도와 실제 고객별 체결가격·체결물량을 절대 같은 값으로 취급하지 않습니다.")
            if category == "hbm4e_thermal_package" and e.get("hbm4e_thermal_state"):
                ts = e["hbm4e_thermal_state"]
                if ts.get("industry_current_interposer_reticle_x") is not None:
                    lines.append(f"• 현재 인터포저 면적: reticle 기준 약 {float(ts['industry_current_interposer_reticle_x']):g}배")
                if ts.get("reported_future_interposer_reticle_x") is not None:
                    lines.append(
                        f"• 장기 전망: 최대 {float(ts['reported_future_interposer_reticle_x']):g}배 "
                        f"({ts.get('reported_future_interposer_stage') or '단계 미확인'})"
                    )
                lines.append(
                    f"• HCB: {ts.get('hcb_stage') or '미확인'} · "
                    f"HPB: {ts.get('hpb_stage') or '미확인'} · "
                    f"패키지·시스템 냉각: {ts.get('package_system_cooling_stage') or '미확인'}"
                )
                lines.append("• 구분: 40배는 장기 업계 전망이며 삼성 HBM4E 확정 양산 로드맵으로 승격하지 않습니다.")
            if category == "samsung_nextgen_hbm" and e.get("samsung_nextgen_hbm_state"):
                ns = e["samsung_nextgen_hbm_state"]
                lines.append(
                    f"• Custom HBM: {ns.get('custom_hbm_stage') or '미확인'} · "
                    f"샘플링 시작 {ns.get('custom_hbm_sample_start_year') or '미확인'}년 · "
                    f"고객사별 맞춤 {'예' if ns.get('custom_hbm_customer_specific') else '미확인'}"
                )
                lines.append(
                    f"• HBM5 맞춤형 단계: {ns.get('hbm5_customization_stage') or '미확인'} · "
                    f"zHBM 단계: {ns.get('zhbm_stage') or '미확인'}"
                )
                lines.append(
                    f"• zHBM 공식 목표: HBM5 대비 성능 최대 {float(ns.get('zhbm_performance_vs_hbm5_x') or 0):g}배 · "
                    f"전력효율 최대 {float(ns.get('zhbm_energy_efficiency_vs_hbm5_x') or 0):g}배 · "
                    f"열저항 50% 이상 감소"
                )
                lines.append(
                    "• 구분: Samsung Custom HBM 공식 샘플링 계획, zHBM 콘셉트, NVIDIA NVHBM은 서로 다른 상태값으로 관리합니다."
                )
            if category == "nvhbm_architecture" and e.get("nvhbm_architecture_state"):
                nv = e["nvhbm_architecture_state"]
                lines.append(
                    f"• NVIDIA 공식 구조: 메모리 컨트롤러 {nv.get('memory_controller_location') or '미확인'} · "
                    f"Feynman Custom HBM 로드맵 {'확인' if nv.get('feynman_custom_hbm_official') else '미확인'}"
                )
                lines.append(
                    f"• NVIDIA 공식 효과: 대역폭 최대 +{float(nv.get('bandwidth_gain_pct_max') or 0):g}% · "
                    f"HBM 전력 최대 -{float(nv.get('hbm_power_reduction_pct_max') or 0):g}% · "
                    f"PHY·지원 면적 최대 -{float(nv.get('phy_support_area_reduction_pct_max') or 0):g}%"
                )
                lines.append(
                    f"• 면적 수치 구분: compute die area 최대 +{float(nv.get('compute_die_area_gain_pct_max') or 0):g}% · "
                    f"main-die silicon 최대 +{float(nv.get('main_die_silicon_gain_pct_max') or 0):g}% · "
                    f"전체 레이아웃 usable silicon 최대 +{float(nv.get('layout_usable_silicon_gain_pct_max') or 0):g}%"
                )
                lines.append(
                    f"• NVIDIA 공식 XPU 엔드투엔드 성능: 최대 +{float(nv.get('xpu_end_to_end_performance_gain_pct_max') or 0):g}% · "
                    f"1GW·2,000W XPU 가정 추가 헤드룸 최대 {int(nv.get('one_gw_additional_xpu_headroom_max') or 0):,}대"
                )
                lines.append(
                    f"• 첫 협력사: {nv.get('first_collaborator') or '미확인'} · "
                    f"공식 실명 메모리 파트너: {', '.join(nv.get('official_memory_vendors') or []) or '아직 미공개'}"
                )
                lines.append(
                    f"• SemiAnalysis 추정: Rubin HBM 컨트롤러·PHY 약 {float(nv.get('rubin_hbm_logic_phy_die_share_estimate_pct') or 0):g}% → "
                    f"Feynman NVHBM 약 {float(nv.get('feynman_nvhbm_interface_die_share_estimate_pct') or 0):g}%"
                )
                std_area = float(nv.get("samsung_standard_hbm4_phy_width_mm") or 0) * float(nv.get("samsung_standard_hbm4_phy_height_mm") or 0)
                d2d_area = float(nv.get("samsung_custom_d2d_width_mm") or 0) * float(nv.get("samsung_custom_d2d_height_mm") or 0)
                lines.append(
                    f"• SemiAnalysis가 인용한 Samsung 예시: 표준 PHY {std_area:g}mm² → Custom D2D {d2d_area:g}mm² · "
                    f"면적 약 -{float(nv.get('samsung_custom_d2d_area_reduction_pct_estimate') or 0):.1f}%"
                )
                lines.append(
                    "• 정확성 잠금: 16%→4%와 Samsung 약 60%는 리서치·발표자료 기반 추정/인용이고 NVIDIA 공식 다이면적 실측값이 아닙니다. +25%와 +30%도 서로 다른 NVIDIA 공식 면적 정의라 합산하지 않습니다."
                )
            if category == "morgan_stanley_nvidia_hbm_margin" and e.get("morgan_stanley_nvidia_hbm_margin_state"):
                ms = e["morgan_stanley_nvidia_hbm_margin_state"]
                lines.append(
                    f"• HBM 단가 감내 시나리오: 풀스펙 +{float(ms.get('base_hbm_unit_price_tolerance_pct_reported') or 0):g}% · "
                    f"디스펙 +{float(ms.get('despec_hbm_unit_price_tolerance_pct_reported') or 0):g}% · "
                    f"매출총이익률 하단 {float(ms.get('gross_margin_floor_pct_reported') or 0):g}%"
                )
                lines.append(
                    f"• 용량 가정: {float(ms.get('full_spec_hbm_gb') or 0):g}GB→{float(ms.get('despec_hbm_gb') or 0):g}GB · "
                    f"산술 재계산 +{float(ms.get('derived_despec_tolerance_pct') or 0):.1f}% · "
                    f"일치 {'예' if ms.get('despec_math_consistent') else '아니오'}"
                )
                lines.append(
                    f"• exact 수치 공개 검증: {'완료' if ms.get('exact_tolerance_public_source_verified') else '미완료 — 원문/독립 2중 출처 확보 전'}"
                )
                if ms.get("vr200_nvl72_rack_value_usd") is not None:
                    rack = float(ms["vr200_nvl72_rack_value_usd"])
                    mem = float(ms.get("vr200_memory_line_usd") or 0)
                    if rate:
                        lines.append(
                            f"• VR200 NVL72 가치배분: 랙 {rack/1e6:.3f}백만달러(약 {rack*rate/1e8:,.1f}억원) · "
                            f"memory line {mem/1e6:.3f}백만달러(약 {mem*rate/1e8:,.1f}억원)"
                        )
                    else:
                        lines.append(f"• VR200 NVL72 가치배분: 랙 {rack/1e6:.3f}백만달러 · memory line {mem/1e6:.3f}백만달러")
                lines.append(
                    "• 범위 잠금: 약 200만달러 memory line은 공개 2차 자료 간 HBM 포함 범위가 충돌하므로 HBM-only 비용으로 계산하지 않습니다."
                )
                lines.append(
                    f"• NVIDIA 공식 마진: FY27 Q2 {float(ms.get('nvidia_q2_fy27_gross_margin_pct') or 0):g}% · "
                    f"FY27 Q3 가이던스 {float(ms.get('nvidia_q3_fy27_gross_margin_outlook_mid_pct') or 0):g}%±"
                    f"{float(ms.get('nvidia_q3_fy27_gross_margin_outlook_plusminus_pct') or 0):g}%p"
                )
            if category == "jpm_hbm_structural" and e.get("jpm_hbm_state"):
                js = e["jpm_hbm_state"]
                lines.append(
                    f"• HBM 비트수요: 2026~2028 CAGR {float(js.get('demand_cagr_2026_2028_pct') or 0):g}% · "
                    f"3년 누적 {float(js.get('cumulative_bit_demand_2026_2028_billion_gb') or 0):g}십억 GB"
                )
                lines.append(
                    f"• 평균판매단가: 2027 +{float(js.get('asp_2027_yoy_pct') or 0):g}% · "
                    f"2028 +{float(js.get('asp_2028_yoy_pct') or 0):g}% · "
                    f"2028 {float(js.get('asp_2028_usd_per_gb') or 0):g}달러/Gb"
                )
                lines.append(
                    f"• DRAM 생산능력: HBM 비중 {float(js.get('hbm_share_dram_capacity_start_pct') or 0):g}%→"
                    f"{float(js.get('hbm_share_dram_capacity_2028_pct') or 0):g}% · "
                    f"2025~2028 신규 DRAM 캐파 중 HBM {float(js.get('new_dram_capacity_to_hbm_pct_2025_2028') or 0):g}%"
                )
                lines.append(
                    f"• 2027 HBM 수요처: ASIC {float(js.get('asic_hbm_demand_share_2027_pct') or 0):g}% · "
                    f"NVIDIA {float(js.get('nvidia_hbm_demand_share_2027_pct') or 0):g}%"
                )
                lines.append("• 구분: 63%는 2026~2028 CAGR입니다. 2027 단년 비트성장률로 바꾸거나 +54% ASP와 곱해 2.5배 매출을 확정치로 쓰지 않습니다.")
            if category == "micron_sca_visibility" and e.get("micron_sca_state"):
                ms = e["micron_sca_state"]
                rpo = float(ms.get("rpo_usd_bn") or 0)
                fin = float(ms.get("financial_commitments_usd_bn") or 0)
                if rate is not None:
                    lines.append(
                        f"• RPO: {rpo:g}0억달러(약 {rpo*1_000_000_000*rate/1e12:,.1f}조원) · "
                        f"고객 금융약정: {fin:g}0억달러(약 {fin*1_000_000_000*rate/1e12:,.1f}조원)"
                    )
                else:
                    lines.append(f"• RPO: {rpo:g}0억달러 · 고객 금융약정: {fin:g}0억달러")
                lines.append(
                    f"• SCA: {int(ms.get('sca_count') or 0)}건 · 2030년까지 매출커버리지 35%+ · "
                    f"가격 프레임워크 확정 매출비중 {float(ms.get('defined_pricing_framework_share_pct') or 0):g}%"
                )
                lines.append(
                    f"• 2027 전체 output 커밋: {float(ms.get('output_committed_2027_min_pct') or 0):g}%+ "
                    f"(SCA+비SCA) · HBM: {ms.get('hbm_2027_bit_supply_stage') or '미확인'}"
                )
                lines.append(
                    f"• 고객 협의 중심: {int(ms.get('customer_discussion_focus_year') or 0)}년 · "
                    f"SCA 최장 {int(ms.get('sca_max_year') or 0)}년"
                )
                lines.append("• 구분: RPO는 구매주문 총액이 아니며, 320억달러 금융약정은 별도 항목이고 대부분 현금예치금입니다. 두 금액은 합산하지 않습니다.")
            if category == "citi_hbm_outlook" and e.get("citi_state"):
                cs = e["citi_state"]
                lo, hi = cs.get("hbm4_12hi_usd_per_gb_min"), cs.get("hbm4_12hi_usd_per_gb_max")
                if lo is not None and hi is not None:
                    if rate is not None:
                        lines.append(
                            f"• HBM4 12단 가격: {float(lo):g}~{float(hi):g}달러/Gb "
                            f"(약 {float(lo)*rate:,.0f}~{float(hi)*rate:,.0f}원/Gb)"
                        )
                    else:
                        lines.append(f"• HBM4 12단 가격: {float(lo):g}~{float(hi):g}달러/Gb (원화 환산 불가)")
                pymin, pymax = cs.get("hbm4_12hi_price_yoy_min_pct"), cs.get("hbm4_12hi_price_yoy_max_pct")
                if pymin is not None and pymax is not None:
                    lines.append(f"• HBM4 12단 가격 상승률 전망: +{float(pymin):.0f}~{float(pymax):.0f}% YoY")
            lines += extract_price_notes(full_text, rate)
            lines.append(f"• 판정: {e.get('verdict')}")
            lines.append(f"- 원문: {e.get('direct_link')}")
            n += 1

    lines += [
        "",
        "■ 자동 판정 원칙",
        "• 원문 URL을 직접 확인하지 못한 기사는 발송하지 않습니다.",
        "• 일반 매체 단독 보도는 발송하지 않고 공식자료·Reuters·신뢰 매체 또는 2곳 이상 교차검증이 있어야 발송합니다.",
        "• 기사 제목만 전달하지 않고, 원문에서 확인된 핵심 사실·일정·물량·금액·판정을 함께 적습니다.",
        "• 192GB 확정만으로 HBM 수요 붕괴로 판정하지 않습니다.",
        f"• GPU당 288→192GB(-33.3%)일 때 GPU 출하가 +{BREAKEVEN_GPU_GROWTH*100:.0f}% 이상이면 총 HBM 비트 수요는 상쇄 가능합니다.",
        f"• Bernstein의 {BERNSTEIN_RUBIN_PREVIOUS_GB:,}→{BERNSTEIN_RUBIN_CURRENT_GB:,}GB는 증권사 모델 가정으로 별도 관리하며, NVIDIA 공식 사양으로 승격하지 않습니다.",
    ]
    return "\n".join(lines).strip() + "\n"


def main() -> None:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    history_cutoff = now - timedelta(days=14)
    state, first_run = load_state()
    seen_before = set(state.get("seen_ids") or [])
    seen_fact_keys = set(state.get("seen_fact_keys") or [])
    if int(state.get("structure_baseline_version") or 0) < STRUCTURE_BASELINE_VERSION:
        seen_fact_keys.update(KNOWN_STRUCTURE_FACT_KEYS)
        state["structure_baseline_version"] = STRUCTURE_BASELINE_VERSION

    raw_events_by_id: dict[str, dict] = {}
    errors: list[str] = []
    for category, query in QUERIES:
        for lang in ("en", "ko"):
            events, errs = read_feed(category, query, lang)
            errors.extend(errs)
            for e in events:
                try:
                    dt = datetime.fromisoformat(e["published_at_kst"])
                    if dt < history_cutoff:
                        continue
                except Exception:
                    pass
                raw_events_by_id[e["id"]] = e

    raw_events = sorted(raw_events_by_id.values(), key=lambda x: x.get("published_at_kst") or "")
    current_ids = {e["id"] for e in raw_events}
    unseen_raw = [e for e in raw_events if e["id"] not in seen_before]
    fresh_unseen = [e for e in unseen_raw if is_fresh_for_send(e, now)]

    verified_events, verify_errors = choose_verified_events(fresh_unseen, raw_events, seen_fact_keys)
    errors.extend(verify_errors)

    rubin_options_state = dict(state.get("rubin_ultra_hbm_options") or {})
    rubin_options_track_version = int(state.get("rubin_ultra_hbm_options_track_version") or 0)
    if rubin_options_track_version < RUBIN_ULTRA_HBM_OPTIONS_TRACK_VERSION:
        seeded = dict(RUBIN_ULTRA_HBM_OPTIONS_BASELINE)
        seeded.update({k: v for k, v in rubin_options_state.items() if v not in (None, "")})
        rubin_options_state = seeded
        rubin_options_track_version = RUBIN_ULTRA_HBM_OPTIONS_TRACK_VERSION

    rubin_options_changes: list[str] = []
    for raw in raw_events:
        if raw.get("category") != "rubin_hbm_option_set":
            continue
        enriched = enrich_event(raw)
        if not enriched.get("link_verified"):
            continue
        quality = source_quality(enriched.get("origin_source") or enriched.get("source") or "")
        if quality == "일반 보도":
            continue
        obs = extract_rubin_ultra_hbm_options(enriched)
        if not obs:
            continue
        merged = merge_rubin_ultra_hbm_options(rubin_options_state, obs)
        changes = rubin_ultra_hbm_options_changes(rubin_options_state, merged)
        rubin_options_state = merged
        if changes:
            rubin_options_changes.extend(changes)
    if rubin_options_changes and not first_run:
        verified_events.append(rubin_ultra_hbm_options_event(rubin_options_state, list(dict.fromkeys(rubin_options_changes))))

    samsung_price_state = dict(state.get("samsung_hbm4_price") or {})
    samsung_price_track_version = int(state.get("samsung_hbm4_price_track_version") or 0)
    if samsung_price_track_version < SAMSUNG_HBM4_PRICE_TRACK_VERSION:
        seeded = dict(SAMSUNG_HBM4_PRICE_BASELINE)
        seeded.update({k: v for k, v in samsung_price_state.items() if v not in (None, "")})
        samsung_price_state = seeded
        samsung_price_track_version = SAMSUNG_HBM4_PRICE_TRACK_VERSION

    samsung_price_changes: list[str] = []
    for raw in raw_events:
        if raw.get("category") != "samsung_hbm4_price":
            continue
        enriched = enrich_event(raw)
        if not enriched.get("link_verified"):
            continue
        obs = extract_samsung_hbm4_price(enriched)
        if not obs:
            continue
        merged = merge_samsung_hbm4_price(samsung_price_state, obs)
        changes = samsung_hbm4_price_changes(samsung_price_state, merged)
        samsung_price_state = merged
        if changes:
            samsung_price_changes.extend(changes)
    if samsung_price_changes and not first_run:
        verified_events.append(samsung_hbm4_price_event(samsung_price_state, list(dict.fromkeys(samsung_price_changes))))

    nextgen_state = dict(state.get("samsung_nextgen_hbm") or {})
    nextgen_track_version = int(state.get("samsung_nextgen_hbm_track_version") or 0)
    if nextgen_track_version < SAMSUNG_NEXTGEN_HBM_TRACK_VERSION:
        previous_nextgen_track_version = nextgen_track_version
        seeded = dict(SAMSUNG_NEXTGEN_HBM_BASELINE)
        seeded.update({k: v for k, v in nextgen_state.items() if v not in (None, "")})
        # v3 only corrects provenance for the already-known 2027 Custom HBM
        # sampling baseline. Do not let legacy zHBM/MK metadata overwrite the
        # newer Samsung official Custom HBM source.
        if previous_nextgen_track_version < 3 and seeded.get("custom_hbm_stage") == "official_sampling_plan":
            for key in ("source", "source_url", "secondary_source_url", "as_of", "note"):
                seeded[key] = SAMSUNG_NEXTGEN_HBM_BASELINE[key]
        nextgen_state = seeded
        nextgen_track_version = SAMSUNG_NEXTGEN_HBM_TRACK_VERSION

    nextgen_changes: list[str] = []
    for raw in raw_events:
        if raw.get("category") != "samsung_nextgen_hbm":
            continue
        enriched = enrich_event(raw)
        if not enriched.get("link_verified"):
            continue
        quality = source_quality(enriched.get("origin_source") or enriched.get("source") or "")
        if quality == "일반 보도":
            continue
        obs = extract_samsung_nextgen_hbm(enriched)
        if not obs:
            continue
        merged = merge_samsung_nextgen_hbm(nextgen_state, obs)
        changes = samsung_nextgen_hbm_changes(nextgen_state, merged)
        nextgen_state = merged
        if changes:
            nextgen_changes.extend(changes)
    if nextgen_changes and not first_run:
        verified_events.append(samsung_nextgen_hbm_event(nextgen_state, list(dict.fromkeys(nextgen_changes))))

    nvhbm_state = dict(state.get("nvhbm_architecture") or {})
    nvhbm_track_version = int(state.get("nvhbm_architecture_track_version") or 0)
    if nvhbm_track_version < NVHBM_ARCH_TRACK_VERSION:
        seeded = dict(NVHBM_ARCH_BASELINE)
        seeded.update({k: v for k, v in nvhbm_state.items() if v not in (None, "")})
        nvhbm_state = seeded
        nvhbm_track_version = NVHBM_ARCH_TRACK_VERSION

    nvhbm_changes: list[str] = []
    for raw in raw_events:
        if raw.get("category") != "nvhbm_architecture":
            continue
        enriched = enrich_event(raw)
        if not enriched.get("link_verified"):
            continue
        quality = source_quality(enriched.get("origin_source") or enriched.get("source") or "")
        if quality == "일반 보도":
            continue
        obs = extract_nvhbm_architecture(enriched)
        if not obs:
            continue
        merged = merge_nvhbm_architecture(nvhbm_state, obs)
        changes = nvhbm_architecture_changes(nvhbm_state, merged)
        nvhbm_state = merged
        if changes:
            nvhbm_changes.extend(changes)
    if nvhbm_changes and not first_run:
        verified_events.append(nvhbm_architecture_event(nvhbm_state, list(dict.fromkeys(nvhbm_changes))))

    thermal_state = dict(state.get("samsung_hbm4e_thermal_package") or {})
    thermal_track_version = int(state.get("samsung_hbm4e_thermal_track_version") or 0)
    if thermal_track_version < SAMSUNG_HBM4E_THERMAL_TRACK_VERSION:
        seeded = dict(SAMSUNG_HBM4E_THERMAL_BASELINE)
        seeded.update({k: v for k, v in thermal_state.items() if v not in (None, "")})
        thermal_state = seeded
        thermal_track_version = SAMSUNG_HBM4E_THERMAL_TRACK_VERSION

    thermal_changes: list[str] = []
    for raw in raw_events:
        if raw.get("category") != "hbm4e_thermal_package":
            continue
        enriched = enrich_event(raw)
        if not enriched.get("link_verified"):
            continue
        obs = extract_samsung_hbm4e_thermal_package(enriched)
        if not obs:
            continue
        merged = merge_samsung_hbm4e_thermal_package(thermal_state, obs)
        changes = samsung_hbm4e_thermal_changes(thermal_state, merged)
        thermal_state = merged
        if changes:
            thermal_changes.extend(changes)
    if thermal_changes and not first_run:
        verified_events.append(samsung_hbm4e_thermal_event(thermal_state, list(dict.fromkeys(thermal_changes))))

    ms_margin_state = dict(state.get("morgan_stanley_nvidia_hbm_margin") or {})
    ms_margin_track_version = int(state.get("morgan_stanley_nvidia_hbm_margin_track_version") or 0)
    if ms_margin_track_version < MORGAN_STANLEY_NVIDIA_HBM_MARGIN_TRACK_VERSION:
        seeded = dict(MORGAN_STANLEY_NVIDIA_HBM_MARGIN_BASELINE)
        seeded.update({k: v for k, v in ms_margin_state.items() if v not in (None, "")})
        ms_margin_state = seeded
        ms_margin_track_version = MORGAN_STANLEY_NVIDIA_HBM_MARGIN_TRACK_VERSION

    ms_margin_observations: list[dict] = []
    ms_exact_sources: set[str] = set()
    ms_direct = False
    for raw in raw_events:
        if raw.get("category") != "morgan_stanley_nvidia_hbm_margin":
            continue
        enriched = enrich_event(raw)
        if not enriched.get("link_verified"):
            continue
        obs = extract_morgan_stanley_nvidia_hbm_margin(enriched)
        if not obs:
            continue
        ms_margin_observations.append(obs)
        src = (enriched.get("origin_source") or enriched.get("source") or "").strip().lower()
        exact_bundle = (
            obs.get("base_hbm_unit_price_tolerance_pct_reported") is not None
            and obs.get("despec_hbm_unit_price_tolerance_pct_reported") is not None
            and obs.get("gross_margin_floor_pct_reported") is not None
            and obs.get("despec_math_consistent") is not False
        )
        if exact_bundle:
            if src:
                ms_exact_sources.add(src)
            if "morgan stanley" in src or "모건스탠리" in src:
                ms_direct = True

    ms_margin_changes: list[str] = []
    if ms_margin_observations:
        candidate = dict(ms_margin_state)
        for obs in sorted(ms_margin_observations, key=lambda x: x.get("observed_at") or ""):
            # Never accept an internally inconsistent 91.7/187.5/capacity bundle.
            if obs.get("despec_math_consistent") is False:
                errors.append("Morgan Stanley HBM 감내폭 산술 불일치로 exact 수치 상태 갱신 보류")
                filtered = {k: v for k, v in obs.items() if k not in (
                    "base_hbm_unit_price_tolerance_pct_reported",
                    "despec_hbm_unit_price_tolerance_pct_reported",
                    "gross_margin_floor_pct_reported",
                    "derived_despec_tolerance_pct",
                    "despec_math_consistent",
                )}
                candidate = merge_morgan_stanley_nvidia_hbm_margin(candidate, filtered)
            else:
                candidate = merge_morgan_stanley_nvidia_hbm_margin(candidate, obs)
        if ms_direct or len(ms_exact_sources) >= 2:
            candidate["exact_tolerance_public_source_verified"] = True
        ms_margin_changes = morgan_stanley_nvidia_hbm_margin_changes(ms_margin_state, candidate)
        ms_margin_state = candidate
    if ms_margin_changes and not first_run:
        verified_events.append(morgan_stanley_nvidia_hbm_margin_event(ms_margin_state, list(dict.fromkeys(ms_margin_changes))))

    jpm_state = dict(state.get("jpm_hbm_structural") or {})
    jpm_track_version = int(state.get("jpm_hbm_structural_track_version") or 0)
    if jpm_track_version < JPM_HBM_STRUCTURAL_TRACK_VERSION:
        seeded = dict(JPM_HBM_STRUCTURAL_BASELINE)
        seeded.update({k: v for k, v in jpm_state.items() if v not in (None, "")})
        jpm_state = seeded
        jpm_track_version = JPM_HBM_STRUCTURAL_TRACK_VERSION

    jpm_observations: list[dict] = []
    jpm_sources: set[str] = set()
    jpm_direct = False
    for raw in raw_events:
        if raw.get("category") != "jpm_hbm_structural":
            continue
        enriched = enrich_event(raw)
        if not enriched.get("link_verified"):
            continue
        obs = extract_jpm_hbm_structural(enriched)
        if not obs:
            continue
        jpm_observations.append(obs)
        src = (enriched.get("origin_source") or enriched.get("source") or "").strip().lower()
        if src:
            jpm_sources.add(src)
        if any(k in src for k in ("j.p. morgan", "jp morgan", "jpmorgan")):
            jpm_direct = True

    jpm_changes: list[str] = []
    if jpm_direct or len(jpm_sources) >= 2:
        candidate = dict(jpm_state)
        for obs in sorted(jpm_observations, key=lambda x: x.get("observed_at") or ""):
            candidate = merge_jpm_hbm_structural(candidate, obs)
        jpm_changes = jpm_hbm_structural_changes(jpm_state, candidate)
        jpm_state = candidate
    if jpm_changes and not first_run:
        verified_events.append(jpm_hbm_structural_event(jpm_state, jpm_changes))

    micron_state = dict(state.get("micron_sca_visibility") or {})
    micron_track_version = int(state.get("micron_sca_visibility_track_version") or 0)
    if micron_track_version < MICRON_SCA_TRACK_VERSION:
        seeded = dict(MICRON_SCA_BASELINE)
        seeded.update({k: v for k, v in micron_state.items() if v not in (None, "")})
        micron_state = seeded
        micron_track_version = MICRON_SCA_TRACK_VERSION

    micron_observations: list[dict] = []
    micron_sources: set[str] = set()
    micron_authoritative = False
    for raw in raw_events:
        if raw.get("category") != "micron_sca_visibility":
            continue
        enriched = enrich_event(raw)
        if not enriched.get("link_verified"):
            continue
        obs = extract_micron_sca_visibility(enriched)
        if not obs:
            continue
        micron_observations.append(obs)
        src = (enriched.get("origin_source") or enriched.get("source") or "").strip().lower()
        if src:
            micron_sources.add(src)
        if any(k in src for k in ("micron", "reuters")):
            micron_authoritative = True

    micron_changes: list[str] = []
    if micron_authoritative or len(micron_sources) >= 2:
        candidate = dict(micron_state)
        for obs in sorted(micron_observations, key=lambda x: x.get("observed_at") or ""):
            candidate = merge_micron_sca_visibility(candidate, obs)
        micron_changes = micron_sca_visibility_changes(micron_state, candidate)
        micron_state = candidate
    if micron_changes and not first_run:
        verified_events.append(micron_sca_visibility_event(micron_state, micron_changes))

    citi_state = dict(state.get("citi_hbm_outlook") or {})
    citi_track_version = int(state.get("citi_hbm_track_version") or 0)
    if citi_track_version < CITI_HBM_TRACK_VERSION:
        seeded = dict(CITI_HBM_BASELINE)
        seeded.update({k: v for k, v in citi_state.items() if v not in (None, "")})
        citi_state = seeded
        citi_track_version = CITI_HBM_TRACK_VERSION

    citi_changes: list[str] = []
    for raw in raw_events:
        if raw.get("category") != "citi_hbm_outlook":
            continue
        enriched = enrich_event(raw)
        if not enriched.get("link_verified"):
            continue
        obs = extract_citi_hbm_outlook(enriched)
        if not obs:
            continue
        merged = merge_citi_hbm_outlook(citi_state, obs)
        changes = citi_hbm_material_changes(citi_state, merged)
        citi_state = merged
        if changes:
            citi_changes.extend(changes)
    if citi_changes and not first_run:
        verified_events.append(citi_hbm_change_event(citi_state, list(dict.fromkeys(citi_changes))))

    # A dedicated technology-risk lane within the existing Rubin HBM
    # collector. Its initial item is an attributed SINGLE-source report,
    # not a claim that either vendor has confirmed hybrid-bonded HBM output.
    hybrid_version_before = int(state.get("hbm_hybrid_bond_track_version") or 0)
    hybrid_state = dict(state.get("hbm_hybrid_bonding") or {})
    hybrid_version = HBM_HYBRID_BOND_TRACK_VERSION
    if hybrid_version_before < HBM_HYBRID_BOND_TRACK_VERSION:
        seeded = dict(HBM_HYBRID_BOND_BASELINE)
        seeded.update({k: v for k, v in hybrid_state.items() if v is not None})
        # State v1 wrote "sk_*" while the parser/renderer expected
        # "skhynix_*". This made the SK official stage show "미확인".
        # Migrate without promoting any reported sample to an official one.
        if "sk_official_hybrid_stage" in seeded:
            seeded["skhynix_official_hybrid_stage"] = seeded.pop("sk_official_hybrid_stage")
        if "sk_official_hybrid_customer_sample_verified" in seeded:
            seeded["skhynix_official_hybrid_customer_sample_verified"] = seeded.pop(
                "sk_official_hybrid_customer_sample_verified"
            )
        hybrid_state = seeded

    initial_hybrid_notice = (
        hybrid_version_before < HBM_HYBRID_BOND_TRACK_VERSION and not first_run
    )
    hybrid_old = dict(hybrid_state)
    for raw in raw_events:
        if raw.get("category") != "hbm_hybrid_bonding":
            continue
        enriched = enrich_event(raw)
        if not enriched.get("link_verified"):
            continue
        observation = extract_hbm_hybrid_official_observation(enriched)
        if observation:
            hybrid_state = merge_hbm_hybrid_official_observation(hybrid_state, observation)
    hybrid_changes = hbm_hybrid_official_changes(hybrid_old, hybrid_state)
    if initial_hybrid_notice:
        correction_only = bool(hybrid_version_before > 0)
        notice = hbm_hybrid_bond_event(
            hybrid_state,
            (["이전 알림의 표시·출처 링크·하이닉스 단계 표기 정정; 동일 보도이며 새 공정 진척 아님"]
             if correction_only else
             ["익명 엔지니어 보도 신규 위험 감시 시작 · 회사 공식 고객 샘플 여부 미확인"]),
            initial=True,
        )
        if correction_only:
            notice["format_correction"] = True
        verified_events.append(notice)
    if hybrid_changes and not first_run:
        verified_events.append(hbm_hybrid_bond_event(hybrid_state, hybrid_changes, initial=False))

    fx = fetch_fx()
    if fx.get("error"):
        errors.append(fx["error"])

    send_events = [] if first_run else verified_events
    send_events = send_events[-12:]
    new_fact_keys = {e.get("fact_key") for e in verified_events if e.get("fact_key")}

    # 첫 실행은 최근 기사들의 인식 가능한 사실키도 기준선에 저장해 재전재 폭탄을 막는다.
    if first_run:
        for raw in raw_events:
            key = fact_signature_from_raw(raw)
            if key:
                new_fact_keys.add(key)

    pending = {
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "seen_ids": sorted((seen_before | current_ids))[-1200:],
        "seen_fact_keys": sorted(seen_fact_keys | new_fact_keys)[-500:],
        "structure_baseline_version": STRUCTURE_BASELINE_VERSION,
        "rubin_ultra_hbm_options_track_version": rubin_options_track_version,
        "rubin_ultra_hbm_options": rubin_options_state,
        "samsung_hbm4_price_track_version": samsung_price_track_version,
        "samsung_hbm4_price": samsung_price_state,
        "samsung_nextgen_hbm_track_version": nextgen_track_version,
        "samsung_nextgen_hbm": nextgen_state,
        "nvhbm_architecture_track_version": nvhbm_track_version,
        "nvhbm_architecture": nvhbm_state,
        "samsung_hbm4e_thermal_track_version": thermal_track_version,
        "samsung_hbm4e_thermal_package": thermal_state,
        "hbm_hybrid_bond_track_version": hybrid_version,
        "hbm_hybrid_bonding": hybrid_state,
        "morgan_stanley_nvidia_hbm_margin_track_version": ms_margin_track_version,
        "morgan_stanley_nvidia_hbm_margin": ms_margin_state,
        "jpm_hbm_structural_track_version": jpm_track_version,
        "jpm_hbm_structural": jpm_state,
        "micron_sca_visibility_track_version": micron_track_version,
        "micron_sca_visibility": micron_state,
        "citi_hbm_track_version": citi_track_version,
        "citi_hbm_outlook": citi_state,
        "last_unseen_raw_count": len(unseen_raw),
        "last_verified_event_count": len(verified_events),
        "last_send_event_count": len(send_events),
        "freshness_hours": SEND_FRESHNESS_HOURS,
        "usdkrw": fx,
        "errors": errors,
    }
    write_json(OUT / "rubin_hbm_pending_state.json", pending)

    if first_run:
        (OUT / "rubin_hbm_rebaseline.txt").write_text(
            f"Initial verified baseline at {now.isoformat(timespec='seconds')}; {len(raw_events)} recent items stored; no Telegram alert sent.\n",
            encoding="utf-8",
        )

    if send_events:
        (OUT / "rubin_hbm_alert.md").write_text(build_alert(now, send_events, fx), encoding="utf-8")

    status = [
        "# Rubin HBM Watch",
        f"- checked_at_kst: {now.isoformat(timespec='seconds')}",
        f"- first_run_baseline: {str(first_run).lower()}",
        f"- recent_raw_events: {len(raw_events)}",
        f"- unseen_raw_events: {len(unseen_raw)}",
        f"- verified_events: {len(verified_events)}",
        f"- Rubin Ultra HBM option typed changes: {len(rubin_options_changes)}",
        f"- Samsung HBM4 price typed changes: {len(samsung_price_changes)}",
        f"- Samsung next-gen HBM typed changes: {len(nextgen_changes)}",
        f"- NVIDIA NVHBM/custom-HBM typed changes: {len(nvhbm_changes)}",
        f"- Samsung HBM4E thermal/package typed changes: {len(thermal_changes)}",
        f"- HBM hybrid bond reported-risk initial: {str(initial_hybrid_notice).lower()}",
        f"- HBM hybrid bond official milestones: {len(hybrid_changes)}",
        f"- Morgan Stanley NVIDIA HBM margin typed changes: {len(ms_margin_changes)}",
        f"- J.P. Morgan HBM structural typed changes: {len(jpm_changes)}",
        f"- Micron SCA/RPO typed changes: {len(micron_changes)}",
        f"- Citi HBM typed changes: {len(citi_changes)}",
        f"- send_events: {len(send_events)}",
        f"- freshness_hours: {SEND_FRESHNESS_HOURS}",
        f"- break_even_gpu_growth: {BREAKEVEN_GPU_GROWTH*100:.1f}%",
        f"- source_errors_or_suppressed: {len(errors)}",
    ]
    for e in errors[:12]:
        status.append(f"  - {e}")
    (OUT / "rubin_hbm_status.md").write_text("\n".join(status) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
