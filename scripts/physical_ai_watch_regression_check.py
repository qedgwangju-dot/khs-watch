#!/usr/bin/env python3
"""Regression guards for the active Physical-AI Telegram watcher.

These checks encode failures that previously reached Telegram:
- price-reaction rewrites must not alert;
- Tesla Gen 3 APK rewrites must collapse to one semantic event;
- generic unclassified Tesla/Optimus stories must stay silent;
- ESS 25-year lifetime-rule stories must use the lifetime category/key;
- Korea supplier scouting must remain a distinct pre-award stage.

The script performs no network requests.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Catch accidental deletion of existing watcher lanes before importing them.
# This protects all active categories during targeted article-source edits.
_watcher_source_path = Path(__file__).with_name("physical_ai_watch_airan_guard.py")
_watcher_source = _watcher_source_path.read_text(encoding="utf-8")
for _required in (
    "ROBOT_POSTTRAIN_FUNDA_URL =",
    "DONGKUK_NPS_RECOVERY =",
    "DKT_HUMANOID_RECOVERY =",
    "TESLA_TOUCH_PATENT_RECOVERY =",
    "S24H_20261020_RECOVERY =",
    "KREG_OCT23_RECOVERY =",
    "def _s24h_recovery(",
    "def _kreg_oct23_recovery(",
    "DIGITAL_OPTIMUS_GAME_RECOVERY =",
    "BESS_SEP26_RECOVERY =",
    "def _bess_bmi_recovery(",
    "SDI_BBU_LFP_RE =",
    "HUMANOID_DRAM_RECOVERY =",
    "OPENAI_HUMANOID_RECOVERY =",
    "BMW_GEN6_PACK_RECOVERY =",
    "JPM_SRI_DEPLOYMENT_RECOVERY =",
    "JPM_SRI_FX_CORRECTION_RECOVERY =",
    "VW_EU_BATTERY_RECALL_RECOVERY =",
    "def _vw_eu_recall_recovery(",
    "TESLA_AGM26_EVENT =",
    "def _agm26_recovery(",
    "def _sum26_stage(",
    "def _jpm_sri_fx_correction_recovery(",
    "def _bmw_gen6_pack_recovery(",
    "def _jpm_sri_recovery(",
    "def _openai_humanoid_recovery(",
    "OPTIMUS_HAND_MAGNET_RECOVERY =",
    "LFP_NA_CIF_PRICE_RECOVERY =",
    "VNET_EQUITY_RECOVERY =",
    "CATL_INTILION_RECOVERY =",
    "DEXMATE_LG_RECOVERY =",
    "STOCK_218_CORRECTION =",
    "FLUENCE_VATTENFALL_RECOVERY =",
    "ROBOT_OCT16_PREFIX =",
    "MICRON_EIM_RECOVERY =",
    "CN_ESS_US_RETREAT_ID =",
    "def _cn_ess_us_retreat_recovery(",
    "def _micron_eim_recovery(",
    "def _micron_eim_stage(",
    "ROBOT_OCT16_EVENTS =",
    "def _oct16_recovery(",
    "def _oct16_group(",
    "def _oct16_stage(",
    "def _fluence_vattenfall_recovery(",
    "def _stock_218_correction_recovery(",
    "def _catl_intilion_recovery(",
    "def _dexmate_lg_recovery(",
    "def _vnet_equity_recovery(",
    "def _lfp_na_price_recovery(",
    "def _humanoid_dram_recovery(",
    "def _digital_optimus_game_recovery(",
    "def _dongkuk_report_recovery(",
    "def _dkt_humanoid_recovery(",
    "def _tesla_touch_patent_recovery(",
    "def query_news(",
    "base.query_news = query_news",
    "base.topic_group = topic_group",
):
    assert _required in _watcher_source, f"Existing Physical-AI lane missing: {_required}"
compile(_watcher_source, str(_watcher_source_path), "exec")

import physical_ai_watch_airan_guard as watcher
import physical_ai_watch_figure_entry as figure_lane

base = watcher.base


def make(title: str, desc: str, source: str) -> dict:
    return {
        "title": title,
        "description": desc,
        "source": source,
        "link": "https://example.com/regression",
        "published": None,
    }


def classify(item: dict):
    text = f"{item['title']} {item.get('description','')} {item.get('source','')}"
    group = base.topic_group(text)
    score = base.score(item)
    category = base.category(text, group) if group else None
    key = base.key(item) if group else None
    return group, score, category, key


# 1) Stock-price/sector-reaction article that only recycles an older Tesla audit story.
price_reaction = make(
    "A股异动丨特斯拉供应链审厂传闻发酵，人形机器人概念集体走强，均胜电子涨超4%",
    "近日有媒体称特斯拉正在长三角推进Optimus人形机器人供应链审厂，相关订单此前已经下达。",
    "新浪财经",
)
g, s, c, k = classify(price_reaction)
assert g == "tesla", (g, s, c)
assert s < 11, ("price-reaction rewrite must stay below alert threshold", s, c)

# 2) A later Chinese Gen-3 rewrite must map to the durable APK event key,
# rather than surface as a new generic "Optimus production/supply-chain" item.
gen3_rewrite = make(
    "特斯拉第三代Optimus设计意外泄露：更契合工厂流水线任务环境",
    "用户解锁特斯拉安卓应用程序包，发现第三代Optimus渲染图以及2.5代和第三代并排素材。",
    "财联社",
)
g2, s2, c2, k2 = classify(gen3_rewrite)
expected_gen3_key = hashlib.sha256(
    b"tesla-optimus|gen3-apk-assets|4.60.5-4573"
).hexdigest()
assert g2 == "tesla", g2
assert "Gen 3 앱 자산" in c2, c2
assert k2 == expected_gen3_key, (
    "Gen3 publisher rewrite must reuse the durable APK semantic key",
    k2,
    expected_gen3_key,
)
assert s2 >= 11, s2

# 3) Generic Tesla/Optimus background with no stage must not alert.
generic = make(
    "Tesla Optimus supply chain update",
    "Optimus remains an important humanoid program and suppliers are watching the market.",
    "Reuters",
)
g, s, c, k = classify(generic)
assert g == "tesla", (g, s, c)
assert s < 11, ("unclassified generic Tesla item must stay silent", s, c)

# 4) ESS 25-year lifetime rule must be classified as lifetime/guarantee, not generic price/supply.
ess_a = make(
    "ESS 계약 15년서 25년으로…배터리 3사 수명 경쟁",
    "전력거래소 제주 ESS 중앙계약시장에 25년 계약이 추가되고 연 730회, 총 18,250회 충방전 및 잔존용량 평가가 적용된다.",
    "글로벌이코노믹",
)
ess_b = make(
    "2026년 ESS 중앙계약시장 제주 경쟁입찰 공고",
    "25년 계약, 보증수명과 잔존용량 평가, 730회 운전 조건을 포함한다.",
    "전력거래소",
)
g1, s1, c1, k1 = classify(ess_a)
g2, s2, c2, k2 = classify(ess_b)
assert g1 == g2 == "ess_battery", (g1, g2)
assert c1 == c2 == "ESS 배터리 · 장기계약·수명보증", (c1, c2)
assert k1 == k2, ("ESS lifetime rewrites must share one event key", k1, k2)

# 5) Korea supplier scouting stays a scouting event, not an awarded supplier.
korea = make(
    "테슬라, 한국 로봇 부품 공급망 생산시설·기술력 점검 보도",
    "Tesla reportedly visited several Korean robot-component firms and reviewed reducers, motors, sensors and actuators. No Korean supplier has been officially selected.",
    "한국경제",
)
g, s, c, k = classify(korea)
assert g == "tesla", (g, s, c)
assert c == "Optimus 한국 공급망 생산시설·기술 점검", c
assert s >= 11, s

# 6) Detailed Optimus ramp rewrites that focus on tooling rework, sensing glove,
# AI generalization or lease-first commercialization must still map to the same
# production-ramp bottleneck event instead of being dropped or re-alerted.
rich_ramp = make(
    "Tesla Optimus output rises 10x to hundreds per week",
    (
        "Fixtures and jigs at hand, joint and electronics-test stations cannot align tiny tight-tolerance parts consistently, causing rework. "
        "Tesla plans a replaceable sensing glove next year. Optimus can be unpredictable in untrained situations and takes several days to learn a basic task. "
        "Training hubs are being set up in Colorado, Arizona and Florida. Early external commercial robots are planned to be leased to warehouse or factory customers, "
        "so Tesla can retrieve, upgrade or refurbish the hardware and collect customer-site data."
    ),
    "Electrek",
)
g, s, c, k = classify(rich_ramp)
expected_ramp_key = hashlib.sha256(
    b"tesla-optimus|2026-09|production-ramp-bottleneck|hands-supply-data"
).hexdigest()
assert g == "tesla", (g, s, c)
assert c == "Optimus 주간 생산 램프·손·공급망 병목", c
assert s >= 11, s
assert k == expected_ramp_key, (
    "detailed ramp rewrite must dedupe to the existing September ramp event",
    k,
    expected_ramp_key,
)

# 7) Electronic-skin discovery must separate market-size noise from real commercial state changes.
eskin_tam = make(
    "2030年人形机器人电子皮肤市场规模预计274亿元",
    "行业预测2030年人形机器人电子皮肤需求152.5万平方米，市场规模约274亿元。",
    "央广网",
)
g, s, c, k = classify(eskin_tam)
assert g != "humanoid_component_global", ("TAM-only e-skin story must not become commercialization alert", g, s, c)

eskin_delivery = make(
    "福莱新材触觉传感器批量交付",
    "福莱新材向灵心巧手人形机器人采购订单累计交付超3万套触觉传感器，10万套订单兑现超三成并继续量产交付。",
    "上海证券报",
)
g, s, c, k = classify(eskin_delivery)
assert g == "humanoid_component_global", (g, s, c)
assert c == "글로벌 휴머노이드 부품 · 힘·토크·촉각센서 · 고객선정·수주·수주잔고", c
assert s >= 11, s

# 8) Giga Berlin real-world worker-data collection is a new operating-stage signal.
# A static showroom/display sighting alone must not be enough.
berlin_static = make(
    "Tesla Optimus spotted behind frosted glass at Giga Berlin",
    "An Optimus robot is displayed on site with a Work in progress sign.",
    "Basenor",
)
g, s, c, k = classify(berlin_static)
assert s < 11, ("static Berlin display alone must stay silent", g, s, c)

berlin_training = make(
    "Tesla Optimus, Giga Berlin field training expands",
    (
        "At Giga Berlin in Gruenheide selected factory workers will wear camera-equipped backpacks and helmets "
        "to collect movement data for Optimus training. Tesla Q2 materials say initial Optimus builds are used in "
        "Optimus Academy for training data collection and functionality development. Secondary reports also describe "
        "an Optimus pilot in internal logistics and 4680-related battery-cell areas."
    ),
    "Handelsblatt",
)
g, s, c, k = classify(berlin_training)
expected_berlin_key = hashlib.sha256(
    b"tesla-optimus|giga-berlin|2026-08|field-training-data-pilot"
).hexdigest()
assert g == "tesla", (g, s, c)
assert c == "Optimus Giga Berlin · 현장 데이터 수집·파일럿 배치", c
assert s >= 11, s
assert k == expected_berlin_key, (k, expected_berlin_key)

# 9) Samsung SDI SolidStack baseline guidance must stay silent until a real
# sample/customer/line/SOP milestone changes.
sdi_asb_baseline = make(
    "삼성SDI SolidStack 휴머노이드 전고체 배터리 개발",
    "삼성SDI는 휴머노이드용 SolidStack 전고체 배터리를 개발 중이며 2027년 하반기 양산을 목표로 한다. 첫 상용화 프로젝트가 휴머노이드가 될 가능성이 높아 고객들과 협의를 진행 중이다.",
    "삼성SDI",
)
g, s, c, k = classify(sdi_asb_baseline)
assert g == "battery", (g, s, c)
assert s < 11, ("repeated SolidStack 2027H2 guidance must stay silent", s, c)

sdi_asb_sample = make(
    "삼성SDI, Figure AI에 SolidStack 휴머노이드 전고체 샘플 공급 개시",
    "Samsung SDI has started delivering SolidStack all-solid-state battery samples to Figure AI for humanoid customer qualification.",
    "삼성SDI",
)
g, s, c, k = classify(sdi_asb_sample)
assert g == "battery", (g, s, c)
assert c.endswith("삼성SDI SolidStack · 휴머노이드 샘플 공급"), c
assert s >= 11, s
sdi_asb_sample_rewrite = make(
    "Samsung SDI starts SolidStack samples for Figure humanoid qualification",
    "Samsung SDI started delivering SolidStack all-solid-state battery samples to Figure AI for humanoid customer qualification.",
    "Reuters",
)
g2, s2, c2, k2 = classify(sdi_asb_sample_rewrite)
assert g2 == "battery", (g2, s2, c2)
assert k2 == k, ("SolidStack sample rewrites must share one semantic event key", k, k2)

# 10) Analyst ESS mix/margin estimates stay silent; official realized figures alert.
sdi_ess_forecast = make(
    "삼성SDI 3분기 ESS 매출 비중 31%, 영업이익률 13% 전망",
    "증권가는 AI 데이터센터 UPS·BBU 수요로 삼성SDI ESS 매출 비중이 31%, 영업이익률이 13%에 이를 것으로 추정했다.",
    "글로벌이코노믹",
)
g, s, c, k = classify(sdi_ess_forecast)
assert g == "ess_battery", (g, s, c)
assert s < 11, ("analyst ESS mix/margin forecast must stay silent", s, c)

sdi_ess_actual = make(
    "삼성SDI 3분기 실적 발표, ESS 매출 비중 31% 확인",
    "Samsung SDI reported Q3 earnings results with ESS, UPS and BBU sales mix at 31% and operating margin at 13%. AMPC benefits and tariff refund effects were separately disclosed.",
    "삼성SDI",
)
g, s, c, k = classify(sdi_ess_actual)
assert g == "ess_battery", (g, s, c)
assert c == "ESS 배터리 · 삼성SDI 실적 질·본업 수익성", c
assert s >= 11, s

# 11) SynergyCells ownership/construction baseline is not a new alert; equipment,
# trial production, SOP, capacity/utilization and customer awards are.
synergy_baseline = make(
    "삼성SDI, GM 49.99% 지분 인수해 SynergyCells 단독법인 전환",
    "New Carlisle Indiana SynergyCells plant is under construction and Samsung SDI plans to use it for ESS batteries.",
    "삼성SDI",
)
g, s, c, k = classify(synergy_baseline)
assert g == "ess_battery", (g, s, c)
assert s < 11, ("SynergyCells acquisition/construction baseline must stay silent", s, c)

synergy_sop = make(
    "삼성SDI SynergyCells ESS LFP 양산 시작",
    "Samsung SDI started mass production of ESS LFP batteries at the New Carlisle SynergyCells plant with 20 GWh production capacity.",
    "삼성SDI",
)
g, s, c, k = classify(synergy_sop)
assert g == "ess_battery", (g, s, c)
assert c == "ESS 배터리 · 삼성SDI SynergyCells 가동 전환", c
assert s >= 11, s

# 12) U.S. ESS baseline numbers from September 2026 are registered but must
# not re-alert from syndicated articles. New actual quarters or revisions do alert.
us_q2_baseline = make(
    "REPORT: U.S. Adds 20 GWh of Energy Storage Capacity in Q2, Largest Quarter on Record",
    "The U.S. energy storage industry installed a record 20.2 GWh in Q2 2026, bringing first-half installations to 30.8 GWh.",
    "SEIA",
)
g, s, c, k = classify(us_q2_baseline)
assert g == "ess_battery", (g, s, c)
assert s < 11, ("Q2 2026 20.2GWh / H1 30.8GWh baseline must stay silent", s, c)

us_target_baseline = make(
    "Energy storage industry targets 225 GW / 1 TWh by end-2032",
    "The U.S. Energy Storage Coalition says the U.S. energy storage industry is targeting 225 GW and 1 TWh of deployment by the end of 2032.",
    "U.S. Energy Storage Coalition",
)
g, s, c, k = classify(us_target_baseline)
assert g == "ess_battery", (g, s, c)
assert s < 11, ("225GW / 1TWh / 2032 target baseline must stay silent", s, c)

us_q3_actual = make(
    "U.S. installs record 27.4 GWh of energy storage in Q3 2026",
    "SEIA reported the United States installed 27.4 GWh of new energy storage capacity in Q3, a new quarterly record.",
    "SEIA",
)
g, s, c, k = classify(us_q3_actual)
assert g == "ess_battery", (g, s, c)
assert c == "ESS 배터리 · 미국 실설치·수요", c
assert s >= 11, s

us_target_revision = make(
    "U.S. Energy Storage Coalition raises 2032 storage target to 1.2 TWh",
    "The U.S. Energy Storage Coalition revised its goal to 250 GW / 1.2 TWh of energy storage deployment by 2032.",
    "U.S. Energy Storage Coalition",
)
g, s, c, k = classify(us_target_revision)
assert g == "ess_battery", (g, s, c)
assert c == "ESS 배터리 · 미국 2032 목표 변경", c
assert s >= 11, s

us_forecast_revision = make(
    "U.S. energy storage forecast raised to 115 GWh for 2027",
    "SEIA and Benchmark Mineral Intelligence revised the United States energy storage outlook upward to 115 GWh for 2027.",
    "SEIA",
)
g, s, c, k = classify(us_forecast_revision)
assert g == "ess_battery", (g, s, c)
assert c == "ESS 배터리 · 미국 설치 전망 변경", c
assert s >= 11, s

# 13) XPENG IRON: the Sep-8 production-line commissioning and future schedule
# are baselines. Supplier nomination, actual SOP and real deliveries are new stages.
xpeng_line_baseline = make(
    "XPENG IRON walks off new production line with 80%+ core-process automation",
    "XPENG officially commissioned its IRON humanoid production line on September 8, 2026 and targets mass production by year-end and deliveries in 2027.",
    "XPENG",
)
g, s, c, k = classify(xpeng_line_baseline)
assert g == "xpeng", (g, s, c)
assert s < 11, ("XPENG line-commissioned baseline must stay silent", s, c)

xpeng_supplier = make(
    "小鹏机器人完成供应链审厂及核心零部件定点",
    "9月22日小鹏集团举行首届机器人供应链合作伙伴大会，小鹏 IRON 已完成供应链审厂及核心零部件定点，执行器、灵巧手、传感器、AI芯片核心供应商进入量产准备。",
    "第一财经",
)
g, s, c, k = classify(xpeng_supplier)
assert g == "xpeng", (g, s, c)
assert s < 11, ("known Sep-22 XPENG supplier event must stay silent", s, c)

xpeng_supplier_new = make(
    "小鹏机器人启动第二轮量产审厂并新增核心供应商定点",
    "XPENG IRON started a second-round supplier audit and nominated a new core component supplier for mass-production allocation.",
    "第一财经",
)
g, s, c, k = classify(xpeng_supplier_new)
assert g == "xpeng", (g, s, c)
assert c.endswith("IRON 핵심부품 공급사 선정"), c
assert s >= 11, s

xpeng_sop = make(
    "XPENG IRON mass production started in December 2026",
    "XPENG officially started mass production of IRON humanoid robots at its dedicated production line.",
    "XPENG",
)
g, s, c, k = classify(xpeng_sop)
assert g == "xpeng", (g, s, c)
assert c.endswith("IRON 실제 양산 개시"), c
assert s >= 11, s
assert k != classify(xpeng_supplier_new)[3], ("new supplier nomination and SOP must remain separate events", k)

# 14) RFM: generic industry explainers and the existing NC AI-POSCO DX MOU stay
# silent. New quantitative cross-embodiment results and multi-robot field use alert.
rfm_explainer = make(
    "로봇은 달라도 두뇌는 하나로…범용 로봇 지능 뜬다",
    "Open X-Embodiment는 22종 로봇 데이터를 모았고 Physical Intelligence π0와 NVIDIA Isaac GR00T가 범용 RFM 경쟁을 이끈다.",
    "한국경제",
)
g, s, c, k = classify(rfm_explainer)
assert g == "rfm_general_intelligence", (g, s, c)
assert s < 11, ("generic RFM explainer must stay silent", s, c)

rfm_mou = make(
    "포스코DX-NC AI, 산업용 로봇 파운데이션 모델 공동개발",
    "POSCO DX와 NC AI가 MOU를 체결해 산업현장용 RFM과 VLA를 공동개발한다.",
    "POSCO DX",
)
g, s, c, k = classify(rfm_mou)
assert g == "rfm_general_intelligence", (g, s, c)
assert s < 11, ("existing NC AI-POSCO DX MOU baseline must stay silent", s, c)

rfm_benchmark = make(
    "New RFM improves cross-embodiment robot success rate by 42%",
    "Google DeepMind released a robot foundation model benchmark across multiple different robot embodiments, improving success rate by 42% on held-out robots.",
    "Google DeepMind",
)
g, s, c, k = classify(rfm_benchmark)
assert g == "rfm_general_intelligence", (g, s, c)
assert c.endswith("크로스 임바디먼트 정량 검증"), c
assert s >= 11, s

rfm_field = make(
    "NC AI-POSCO DX RFM enters industrial-site pilot",
    "NC AI and POSCO DX deployed one RFM across a humanoid, quadruped and robot arm at an industrial site pilot, reporting task success rate of 88%.",
    "POSCO DX",
)
g, s, c, k = classify(rfm_field)
assert g == "rfm_general_intelligence", (g, s, c)
assert c.endswith("RFM 다종 로봇 현장 실증"), c
assert s >= 11, s

# 15) Agility: the wheeled rendering/exploration is a concept baseline, not a
# product alert. A real physical prototype/product/customer milestone is new.
agility_concept = make(
    "Agility Robotics exploring wheeled robots after Digit 5 video",
    "Jonathan Hurst said the company is exploring robot designs and form factors including wheels. The wheeled robot shown was a concept rendering and no product, launch date, price or customer was announced.",
    "The Robot Report",
)
g, s, c, k = classify(agility_concept)
assert g == "agility_platform", (g, s, c)
assert s < 11, ("Agility wheeled concept must stay silent", s, c)

agility_proto = make(
    "Agility Robotics unveils working wheeled humanoid prototype",
    "Agility Robotics demonstrated a physical working prototype of its wheeled humanoid platform for warehouse operations.",
    "Agility Robotics",
)
g, s, c, k = classify(agility_proto)
assert g == "agility_platform", (g, s, c)
assert c.endswith("바퀴형 플랫폼 실물 시제품"), c
assert s >= 11, s

# 16) CATL Debrecen: Sep-22 trial production and syndicated "formal production"
# rewrites are one baseline. Actual series production / commercial shipment are new.
catl_trial = make(
    "CATL Debrecen kicks off trial operations in new cell building",
    "CATL began trial production on September 22, 2026 on the first two cell lines in Debrecen. The full project is planned for 100 GWh after all facilities are ready.",
    "CATL",
)
g, s, c, k = classify(catl_trial)
assert g == "global_battery_capacity", (g, s, c)
assert s < 11, ("CATL Debrecen Sep-22 trial baseline must stay silent", s, c)

catl_rewrite = make(
    "宁德时代匈牙利德布勒森新电芯工厂正式启动生产，规划产能100GWh",
    "项目总投资73.4亿欧元，占地约221公顷，建成后年产能100GWh，可为超过100万辆电动车供电。",
    "中国基金报",
)
g, s, c, k = classify(catl_rewrite)
assert g == "global_battery_capacity", (g, s, c)
assert s < 11, ("syndicated CATL 100GWh formal-production rewrite must remain trial baseline", s, c)

catl_series = make(
    "CATL Debrecen begins series production of battery cells",
    "CATL officially commenced series production at its Debrecen cell plant after completing trial operations.",
    "CATL",
)
g, s, c, k = classify(catl_series)
assert g == "global_battery_capacity", (g, s, c)
assert c.endswith("CATL Debrecen 셀 양산 개시"), c
assert s >= 11, s

catl_ship = make(
    "CATL Debrecen starts first commercial battery-cell shipments",
    "Battery cells from CATL's Debrecen plant started first shipments to European automotive customers.",
    "CATL",
)
g, s, c, k = classify(catl_ship)
assert g == "global_battery_capacity", (g, s, c)
assert c.endswith("CATL Debrecen 첫 상업 출하"), c
assert s >= 11, s

# 17) ISU Specialty Chemical Li2S: June completion / Oct production plan are
# baselines; actual commercial production, paid shipment and supply contracts alert.
isu_plan = make(
    "이수스페셜티케미컬 황화리튬 다음 달 상업생산 예정",
    "6월 준공한 연 150톤 황화리튬 마더플랜트는 시운전과 품질 안정화 중이며 10월 넷째 주 상업생산을 시작할 계획이다. 최대 500톤까지 확장 가능하다.",
    "한국경제TV",
)
g, s, c, k = classify(isu_plan)
assert g == "solid_state_material", (g, s, c)
assert s < 11, ("Li2S Oct commercial-production plan baseline must stay silent", s, c)

isu_plan_rewrite = make(
    "이수스페셜티케미컬, 10월 황화리튬 상업생산 돌입…전고체 배터리 '원가 장벽' 깬다",
    "다음 달 본격적인 상업생산에 나설 예정이며 고객사 납품을 시작하는 동시에 국내외 기업 10곳과 추가 샘플 테스트를 진행한다. 지난 6월 공장을 준공한 뒤 시운전과 품질 안정화 작업을 진행 중이며 10월 넷째 주 공장 가동식을 열고 본격적인 상업생산에 들어갈 예정이다. 초기 생산능력은 연간 150톤이며 최대 500톤까지 확대할 계획이다. 올해 황화리튬 판매량은 20톤 안팎으로 추정된다.",
    "리드경제",
)
g, s, c, k = classify(isu_plan_rewrite)
assert g == "solid_state_material", (g, s, c)
assert s < 11, ("future-tense Li2S 'commercial production' rewrite must stay silent", s, c)

isu_plan_rewrite = make(
    "이수스페셜티케미컬, 10월 황화리튬 상업생산 돌입…전고체 배터리 원가 장벽 깬다",
    "10월 넷째 주 공장 가동식을 열고 본격적인 상업생산에 들어갈 예정이다. 연산 150톤 생산설비를 갖췄고 최대 500톤까지 확장 가능하다.",
    "리드경제",
)
g, s, c, k = classify(isu_plan_rewrite)
assert g == "solid_state_material", (g, s, c)
assert s < 11, ("headline 'commercial production' rewrite must remain a future-plan baseline", s, c)

isu_start = make(
    "이수스페셜티케미컬 황화리튬 상업생산 개시",
    "이수스페셜티케미컬이 울산 공장에서 황화리튬 상업생산을 시작했다. 초기 연산 150톤 생산설비가 가동에 들어갔다.",
    "이수스페셜티케미컬",
)
g, s, c, k = classify(isu_start)
assert g == "solid_state_material", (g, s, c)
assert c.endswith("이수스페셜티 황화리튬 상업생산 개시"), c
assert s >= 11, s

isu_contract = make(
    "이수스페셜티케미컬, A사와 황화리튬 장기 공급계약 체결",
    "이수스페셜티케미컬이 전고체 배터리 고객과 황화리튬 장기 공급계약을 체결했다.",
    "이수스페셜티케미컬",
)
g, s, c, k = classify(isu_contract)
assert g == "solid_state_material", (g, s, c)
assert c.endswith("이수스페셜티 황화리튬 공급계약"), c
assert s >= 11, s

isu_delay = make(
    "이수스페셜티케미컬 황화리튬 상업생산 일정 연기",
    "품질 안정화 지연으로 황화리튬 상업생산 개시 일정이 연기됐다.",
    "뉴시스",
)
g, s, c, k = classify(isu_delay)
assert g == "solid_state_material", (g, s, c)
assert c.endswith("이수스페셜티 황화리튬 일정 지연"), c
assert s >= 11, s


# 18) Hyundai Mobis lighting divestiture: the Sep-30 definitive agreement is
# the baseline. Legal/approval/spin-off/closing/cash/reinvestment changes alert.
mobis_lamp_spa = make(
    "OPmobility to acquire 100% of Hyundai Mobis lighting business for KRW 600 billion",
    "Hyundai Mobis and OPmobility signed the definitive agreement on September 30, 2026. The lighting business has about KRW 2.5 trillion of annual revenue.",
    "OPmobility",
)
g, s, c, k = classify(mobis_lamp_spa)
assert g == "mobis_lamp_divestiture", (g, s, c)
assert s < 11, ("Sep-30 Mobis lamp SPA must be a silent baseline", s, c)

mobis_lamp_plan = make(
    "현대모비스 램프사업 물적분할 2027년 4월 예정",
    "현대모비스는 램프사업을 물적분할한 뒤 OPmobility에 매각할 계획이다.",
    "연합뉴스",
)
g, s, c, k = classify(mobis_lamp_plan)
assert g == "mobis_lamp_divestiture", (g, s, c)
assert s < 11, ("announced spin-off plan must stay silent until completion", s, c)

mobis_lamp_approval = make(
    "현대모비스 램프사업 매각 주주총회 승인",
    "주주총회에서 램프사업 물적분할 및 OPmobility 매각 안건을 승인했다.",
    "현대모비스",
)
g, s, c, k = classify(mobis_lamp_approval)
assert g == "mobis_lamp_divestiture", (g, s, c)
assert c.endswith("주주총회 승인"), c
assert s >= 11, s

mobis_lamp_closing = make(
    "현대모비스-OPmobility 램프사업 거래 종결 완료",
    "규제 승인을 모두 마치고 OPmobility의 Hyundai Mobis lighting business acquisition closing was completed.",
    "OPmobility",
)
g, s, c, k = classify(mobis_lamp_closing)
assert g == "mobis_lamp_divestiture", (g, s, c)
assert c.endswith("거래 종결"), c
assert s >= 11, s


mobis_lamp_closing_no_lamp_word = make(
    "Hyundai Mobis-OPmobility transaction closing completed",
    "Hyundai Mobis and OPmobility completed the acquisition transaction after regulatory clearance.",
    "OPmobility",
)
g, s, c, k = classify(mobis_lamp_closing_no_lamp_word)
assert g == "mobis_lamp_divestiture", (g, s, c)
assert c.endswith("거래 종결"), c
assert s >= 11, s

mobis_lamp_injunction = make(
    "현대모비스 램프사업 매각 가처분 신청 접수",
    "노조가 램프사업 분할 및 매각 관련 가처분 신청을 법원에 접수했다.",
    "연합뉴스",
)
g, s, c, k = classify(mobis_lamp_injunction)
assert g == "mobis_lamp_divestiture", (g, s, c)
assert c.endswith("소송·지연·조건변경"), c
assert s >= 11, s

mobis_lamp_reinvest = make(
    "현대모비스, 램프 매각재원으로 로보틱스 신규 설비투자 결정",
    "현대모비스는 램프 사업 매각재원을 활용해 로보틱스 액추에이터 신규 시설 투자 3,000억원을 집행하기로 확정했다.",
    "현대모비스",
)
g, s, c, k = classify(mobis_lamp_reinvest)
assert g == "mobis_lamp_divestiture", (g, s, c)
assert c.endswith("미래사업 자금 재배치"), c
assert s >= 11, s

# 19) Hyundai Mobis Atlas actuator: CES supply and Tech Day reveal are baselines.
# Customer validation, actual SOP, first shipment, capacity and external OEMs alert.
mobis_atlas_supply = make(
    "현대모비스, Boston Dynamics Atlas 액추에이터 공급",
    "현대모비스는 CES 2026에서 보스턴다이내믹스 차세대 Atlas에 액추에이터를 공급하기로 했다고 밝혔다.",
    "현대모비스",
)
g, s, c, k = classify(mobis_atlas_supply)
assert g == "hyundai_mobis_atlas", (g, s, c)
assert s < 11, ("CES Atlas actuator supply must remain the baseline", s, c)

mobis_atlas_reveal = make(
    "현대모비스 R&D Tech Day, Atlas용 로봇 액추에이터 최초 공개",
    "현대모비스가 개발 중인 휴머노이드 로봇 액추에이터 실물을 처음 공개했다.",
    "현대모비스",
)
g, s, c, k = classify(mobis_atlas_reveal)
assert g == "hyundai_mobis_atlas", (g, s, c)
assert s < 11, ("Sep-2026 actuator reveal must remain the baseline", s, c)

mobis_atlas_validation = make(
    "현대모비스 Atlas 액추에이터 PPAP 고객 승인 완료",
    "Boston Dynamics Atlas용 액추에이터가 PPAP와 신뢰성 검증을 완료했다.",
    "현대모비스",
)
g, s, c, k = classify(mobis_atlas_validation)
assert g == "hyundai_mobis_atlas", (g, s, c)
assert c.endswith("고객 승인·신뢰성·양산검증"), c
assert s >= 11, s


mobis_atlas_order = make(
    "현대모비스, Boston Dynamics Atlas 액추에이터 3만개 양산 공급계약 수주",
    "현대모비스가 Atlas용 액추에이터 30,000개 양산 공급계약을 체결하고 생산 발주를 확보했다.",
    "현대모비스",
)
g, s, c, k = classify(mobis_atlas_order)
assert g == "hyundai_mobis_atlas", (g, s, c)
assert c.endswith("아틀라스 액추에이터 양산계약·수주"), c
assert s >= 11, s

mobis_atlas_sop = make(
    "현대모비스 Atlas 액추에이터 양산 개시",
    "Hyundai Mobis commenced mass production of actuators for Boston Dynamics Atlas.",
    "현대모비스",
)
g, s, c, k = classify(mobis_atlas_sop)
assert g == "hyundai_mobis_atlas", (g, s, c)
assert c.endswith("아틀라스 액추에이터 실제 양산 개시"), c
assert s >= 11, s

mobis_atlas_ship = make(
    "현대모비스 Atlas 액추에이터 첫 양산 출하",
    "현대모비스가 Boston Dynamics에 Atlas용 액추에이터 첫 양산 납품을 시작했다.",
    "현대모비스",
)
g, s, c, k = classify(mobis_atlas_ship)
assert g == "hyundai_mobis_atlas", (g, s, c)
assert c.endswith("아틀라스 액추에이터 첫 양산 출하"), c
assert s >= 11, s

mobis_atlas_delay = make(
    "현대모비스 Atlas 액추에이터 양산 일정 지연",
    "초기 수율 문제로 Atlas 액추에이터 SOP 일정이 지연됐다.",
    "연합뉴스",
)
g, s, c, k = classify(mobis_atlas_delay)
assert g == "hyundai_mobis_atlas", (g, s, c)
assert c.endswith("아틀라스 액추에이터 양산·검증 지연"), c
assert s >= 11, s


# 20) Figure founder teasers: the alert unit is the promised reveal,
# not the X post id. Same-event Oct-1 follow-ups must dedupe, while a Sep-30
# teaser promising an Oct-1 reveal remains separate from Oct-1 posts promising
# an Oct-2 reveal.
figure_teaser_prior_day = make(
    "Figure AI, AI 돌파구 공개 예고",
    "Major robotics AI breakthrough reveal tomorrow.",
    "Brett Adcock (Figure AI/X)",
)
figure_teaser_prior_day.update({
    "x_status_id": "2105138104009199977",
    "direct_primary": True,
    "published": "2026-09-30T03:30:00+00:00",
})
figure_teaser_b = make(
    "Figure AI, AI·휴머노이드 핵심 업데이트",
    "Robotics AI update tomorrow. See you in the AM.",
    "Brett Adcock (Figure AI/X)",
)
figure_teaser_b.update({
    "x_status_id": "2105316680251650555",
    "direct_primary": True,
    "published": "2026-09-30T15:19:46.121000+00:00",
})
figure_teaser_c = make(
    "Figure AI, AI·휴머노이드 핵심 업데이트",
    "AI robotics announcement tomorrow morning.",
    "Brett Adcock (Figure AI/X)",
)
figure_teaser_c.update({
    "x_status_id": "2105322505934410007",
    "direct_primary": True,
    "published": "2026-09-30T15:42:55.072000+00:00",
})
g0, s0, c0, k0 = classify(figure_teaser_prior_day)
g2, s2, c2, k2 = classify(figure_teaser_b)
g3t, s3t, c3t, k3t = classify(figure_teaser_c)
assert g0 == g2 == g3t == "figure_ai", (g0, g2, g3t, c0, c2, c3t)
assert c0.endswith("공식 사전예고·공개 시간표"), c0
assert c2.endswith("공식 사전예고·공개 시간표"), c2
assert c3t.endswith("공식 사전예고·공개 시간표"), c3t
assert k2 == k3t, (
    "same Oct-2 Figure reveal teasers must dedupe across post ids",
    k2, k3t,
)
assert k0 != k2, (
    "different promised reveal days must remain separate events",
    k0, k2,
)

figure_actual = make(
    "Figure AI, Helix 2.5 실제 공개",
    "Helix 2.5 zero-shot generalization improved across 30 unseen homes.",
    "Figure AI",
)
g3, s3, c3, k3 = classify(figure_actual)
assert g3 == "figure_ai", (g3, s3, c3)
assert k3 != k2, ("actual reveal must remain independent from teaser", k3, k2)

# 21) Korean display must not leave a duplicated English tail after Pollen Robotics.
rendered_pollen = base.esc_text("Pollen Robotics의 실제 생산 목표")
assert "폴렌 로보틱스의 실제 생산 목표" in rendered_pollen, rendered_pollen
assert "Robotics의" not in rendered_pollen, rendered_pollen

# 22) Microduck production-plan quantity view must distinguish plan, per-robot
# architecture, conditional actuator demand and unconfirmed ROBOTIS orders.
microduck_value = watcher.qty._microduck_block(
    "마이크로덕 실제 생산 목표 2만대 계획. XL330 모터 15개/대.",
    1400.0,
    {"microduck": 399.0, "reachy_lite": 399.0, "reachy_wireless": 499.0, "xl330": 27.49},
    {"microduck": False, "reachy_lite": False, "reachy_wireless": False, "xl330": False},
)
assert microduck_value is not None
assert "20,000대" in microduck_value, microduck_value
assert "300,000개" in microduck_value, microduck_value
assert "로보티즈 확정 발주" in microduck_value, microduck_value
assert "아직 미확인" in microduck_value, microduck_value
assert "소매가로 로보티즈 매출을 추정하지 않음" in microduck_value, microduck_value


# 23) Korea 2030 AI-robot policy: Sep-30 200k diffusion / 1,700 public purchase /
# Daegu-Gyeongbuk cluster is a baseline. Actual procurement, awards, deployment,
# capex execution and reversals are new events.
korea_robot_baseline = make(
    "정부, 2030년까지 AI로봇 20만대 보급…대구·경북 로봇 특화단지",
    "2027년 정부가 1,700대 이상을 구매하고 2030년까지 민관합동 20만대를 보급한다. 대구·경북 구미·포항을 국가첨단전략산업 특화단지로 지정했다.",
    "산업통상부",
)
g, s, c, k = classify(korea_robot_baseline)
assert g == "korea_robot_scale_policy", (g, s, c)
assert s < 11, ("Sep-30 200k robot policy must be a silent baseline", s, c)

korea_robot_tender = make(
    "소방청, 2027년 AI 재난로봇 120대 조달공고",
    "정부 AI로봇 보급계획에 따라 소방청이 나라장터에 재난·인명구조 AI로봇 120대 구매 입찰공고를 게시했다. 예산은 240억원이다.",
    "조달청",
)
g, s, c, k = classify(korea_robot_tender)
assert g == "korea_robot_scale_policy", (g, s, c)
assert c.endswith("실제 조달공고"), c
assert s >= 11, s

korea_robot_award = make(
    "정부 AI로봇 120대 구매계약 체결",
    "소방청 AI로봇 조달에서 A사가 120대, 228억원 규모 구매계약을 체결했다.",
    "조달청",
)
g, s, c, k = classify(korea_robot_award)
assert g == "korea_robot_scale_policy", (g, s, c)
assert c.endswith("낙찰·구매계약"), c
assert s >= 11, s

korea_robot_plant = make(
    "구미 휴머노이드 양산공장 착공",
    "대구·경북 로봇 특화단지에서 선도기업이 휴머노이드 생산라인 설비투자를 확정하고 구미 공장 착공에 들어갔다.",
    "산업통상부",
)
g, s, c, k = classify(korea_robot_plant)
assert g == "korea_robot_scale_policy", (g, s, c)
assert c.endswith("대경권·새만금 양산설비 실행"), c
assert s >= 11, s

korea_robot_reverse = make(
    "AI로봇 20만대 보급 일정 연기",
    "정부가 예산 감액으로 2030년 20만대 AI로봇 보급 목표 일정을 1년 연기했다.",
    "산업통상부",
)
g, s, c, k = classify(korea_robot_reverse)
assert g == "korea_robot_scale_policy", (g, s, c)
assert c.endswith("목표·예산·일정 후퇴"), c
assert s >= 11, s

# 24) Samsung Electronics robotics: manufacturing-first/home expansion, 99.99%
# required reliability, millions-unit potential and WAM/retargeting are baselines.
# Actual deployment/measurement/scaling/SOP/product/supplier events alert.
samsung_robot_baseline = make(
    "삼성전자 로봇 제조현장서 홈으로…수백만대 판매 잠재력",
    "RX사업추진실은 제조 현장부터 가정으로 확장하고 99.99% 성공률이 필요하다고 설명했다. World Action Models와 Human Motion Retargeting을 유망 기술로 제시했다.",
    "삼성전자",
)
g, s, c, k = classify(samsung_robot_baseline)
assert g == "samsung_robot_scale", (g, s, c)
assert s < 11, ("Samsung Sep-30 robotics strategy must be a silent baseline", s, c)

samsung_robot_factory = make(
    "삼성전자 구미공장 휴머노이드 50대 현장 배치 시작",
    "삼성전자가 구미 사업장 생산라인에 휴머노이드 로봇 50대를 투입해 조립 공정 파일럿 운영을 시작했다.",
    "삼성전자",
)
g, s, c, k = classify(samsung_robot_factory)
assert g == "samsung_robot_scale", (g, s, c)
assert c.endswith("실제 공장 배치"), c
assert s >= 11, s

samsung_robot_reliability_target = make(
    "삼성전자 제조 로봇 성공률 99.99% 필요",
    "Kris Hauser는 제조현장 적용을 위해 성공률 99.99%가 필요하다는 목표를 제시했다.",
    "Samsung AI Forum",
)
g, s, c, k = classify(samsung_robot_reliability_target)
assert g == "samsung_robot_scale", (g, s, c)
assert s < 11, ("99.99% requirement is a target baseline, not achieved performance", s, c)

samsung_robot_reliability_actual = make(
    "삼성전자 제조 로봇 작업 성공률 99.99% 달성",
    "삼성전자는 구미 생산라인 100만회 작업 시험에서 성공률 99.99%를 측정해 달성했다고 밝혔다.",
    "삼성전자",
)
g, s, c, k = classify(samsung_robot_reliability_actual)
assert g == "samsung_robot_scale", (g, s, c)
assert c.endswith("산업 신뢰성 정량 달성"), c
assert s >= 11, s

samsung_robot_scaling = make(
    "삼성전자 인간행동 영상 8배 확대, 로봇 제로샷 성공률 31%→62%",
    "삼성전자는 인간 행동 영상 사전학습 데이터셋을 8배 확대하면서 처음 보는 작업의 zero-shot 성공률이 31%에서 62%로 개선됐다고 공개했다.",
    "삼성전자",
)
g, s, c, k = classify(samsung_robot_scaling)
assert g == "samsung_robot_scale", (g, s, c)
assert c.endswith("인간영상 사전학습 정량 스케일링"), c
assert s >= 11, s

samsung_robot_sop = make(
    "삼성전자 휴머노이드 로봇 양산 시작",
    "삼성전자가 구미 로봇 생산라인에서 휴머노이드 로봇 양산을 개시했다.",
    "삼성전자",
)
g, s, c, k = classify(samsung_robot_sop)
assert g == "samsung_robot_scale", (g, s, c)
assert c.endswith("실제 양산 개시"), c
assert s >= 11, s

samsung_robot_supplier = make(
    "삼성전자 휴머노이드 액추에이터 공급사 선정·발주",
    "삼성전자가 휴머노이드 로봇 양산용 액추에이터 공급사를 선정하고 5만개 발주 계약을 체결했다.",
    "삼성전자",
)
g, s, c, k = classify(samsung_robot_supplier)
assert g == "samsung_robot_scale", (g, s, c)
assert c.endswith("핵심부품 공급사·발주"), c
assert s >= 11, s


# 25) U.S. autonomous warfare: Sep-30 AUTOWARCOM / Project Agincourt /
# Project Meridian announcements are baselines. Legislation, funding, formal
# stand-up, acquisition authority, contracts, deployments and the Meridian report
# are new stages.
autowar_baseline = make(
    "Pentagon announces Autonomous Warfare Command and Project Meridian",
    "Defense Secretary Pete Hegseth announced a planned four-star Autonomous Warfare Command (AUTOWARCOM). Project Agincourt is the interim step. Project Meridian will be co-led by Elon Musk, Palmer Luckey and Newt Gingrich to study future warfare.",
    "Breaking Defense",
)
g, s, c, k = classify(autowar_baseline)
assert g == "us_autonomous_warfare", (g, s, c)
assert s < 11, ("Sep-30 AUTOWARCOM and Meridian announcements must be baseline", s, c)

autowar_musk_headline = make(
    "美 국방, 머스크에 전쟁 대비 맡긴다…로봇으로 싸우는 자율전쟁사령부도 신설",
    "Project Meridian은 일론 머스크, 팔머 럭키, 뉴트 깅리치가 공동으로 미래전 능력 격차와 대안을 연구한다. 국방부는 AUTOWARCOM 창설 계획도 발표했다.",
    "서울경제",
)
g, s, c, k = classify(autowar_musk_headline)
assert g == "us_autonomous_warfare", (g, s, c)
assert s < 11, ("syndicated Musk/Autowarcom baseline headline must stay silent", s, c)

autowar_law = make(
    "Congress passes AUTOWARCOM authorization in FY2027 NDAA",
    "Congress passed legislation authorizing the Autonomous Warfare Command and its service-like acquisition authorities.",
    "Congress.gov",
)
g, s, c, k = classify(autowar_law)
assert g == "us_autonomous_warfare", (g, s, c)
assert c.endswith("AUTOWARCOM 법제화·승인"), c
assert s >= 11, s

autowar_standup = make(
    "Pentagon formally activates Autonomous Warfare Command",
    "The Department of Defense officially established AUTOWARCOM and declared initial operating capability.",
    "U.S. Department of Defense",
)
g, s, c, k = classify(autowar_standup)
assert g == "us_autonomous_warfare", (g, s, c)
assert c.endswith("AUTOWARCOM 정식 창설·작전능력"), c
assert s >= 11, s

autowar_commander = make(
    "Pentagon names four-star commander for AUTOWARCOM",
    "The President nominated a four-star commander to lead the Autonomous Warfare Command.",
    "U.S. Department of Defense",
)
g, s, c, k = classify(autowar_commander)
assert g == "us_autonomous_warfare", (g, s, c)
assert c.endswith("AUTOWARCOM 사령관 지명·인준"), c
assert s >= 11, s

agincourt_contract = make(
    "Project Agincourt awards autonomous drone prototype contracts",
    "Defense Innovation Unit awarded Project Agincourt prototype agreements for 2,000 autonomous drones worth $450 million.",
    "Defense Innovation Unit",
)
g, s, c, k = classify(agincourt_contract)
assert g == "us_autonomous_warfare", (g, s, c)
assert c.endswith("Project Agincourt 시제품·양산계약"), c
assert s >= 11, s

meridian_report = make(
    "Project Meridian releases future warfare report",
    "Project Meridian published its report with recommendations on autonomous systems, robotics and AI procurement.",
    "U.S. Department of Defense",
)
g, s, c, k = classify(meridian_report)
assert g == "us_autonomous_warfare", (g, s, c)
assert c.endswith("Project Meridian 보고서·권고"), c
assert s >= 11, s

autowar_reverse = make(
    "AUTOWARCOM stand-up delayed",
    "Congressional authorization delay postponed the Autonomous Warfare Command stand-up beyond October 2027.",
    "Reuters",
)
g, s, c, k = classify(autowar_reverse)
assert g == "us_autonomous_warfare", (g, s, c)
assert c.endswith("일정·예산·승인 후퇴"), c
assert s >= 11, s

# 26) Distinguish the older SOUTHCOM regional Autonomous Warfare Command from
# the Pentagon-wide four-star AUTOWARCOM, and treat FY2027 Drone Dominance as a
# proposal baseline until Congress actually appropriates money.
southcom_old = make(
    "Southcom establishes Autonomous Warfare Command",
    "On April 23, 2026 U.S. Southern Command directed establishment of the Southcom Autonomous Warfare Command for autonomous, semiautonomous and unmanned systems.",
    "U.S. Southern Command",
)
g, s, c, k = classify(southcom_old)
assert g == "us_autonomous_warfare", (g, s, c)
assert c.endswith("SOUTHCOM 지역사령부 기준선"), c
assert s < 11, ("older SOUTHCOM regional command must stay a baseline", s, c)

drone_budget_proposal = make(
    "FY2027 Drone Dominance Requirement totals $53.6 billion",
    "The Department of War FY2027 budget request proposes a $53.6 billion Drone Dominance Requirement including Collaborative Autonomy.",
    "U.S. Department of War",
)
g, s, c, k = classify(drone_budget_proposal)
assert g == "us_autonomous_warfare", (g, s, c)
assert c.endswith("FY2027 드론예산 제안 기준선"), c
assert s < 11, ("FY2027 $53.6bn request is not enacted spending", s, c)

autowar_vendor_contract = make(
    "Defense Autonomous Warfare Group awards Anduril contract",
    "The Defense Autonomous Warfare Group awarded Anduril a $780 million contract for 4,000 autonomous systems under the Pentagon autonomy initiative.",
    "U.S. Department of War",
)
g, s, c, k = classify(autowar_vendor_contract)
assert g == "us_autonomous_warfare", (g, s, c)
assert c.endswith("AUTOWARCOM·DAWG 실제 조달·수주"), c
assert s >= 11, s

autowar_production = make(
    "AUTOWARCOM supplier expands drone mass production",
    "Under an AUTOWARCOM production award, Anduril increased monthly output to 5,000 autonomous drones.",
    "U.S. Department of War",
)
g, s, c, k = classify(autowar_production)
assert g == "us_autonomous_warfare", (g, s, c)
assert c.endswith("드론·로봇 양산 확대"), c
assert s >= 11, s

# 27) Dexterous-hand architecture lane: current Atlas/Clone demos are baselines,
# while later supplier awards, autonomous manipulation and new product architecture
# must alert through the existing humanoid-component route.
atlas_hand_baseline = make(
    "Robot Hands for Modern AI and Real Work",
    "Boston Dynamics unveiled the new generation Atlas robot hand with four fingers, 13 DOF, direct actuation, dense tactile pressure sensors and sim2real reinforcement learning.",
    "Boston Dynamics",
)
g, s, c, k = classify(atlas_hand_baseline)
assert g == "humanoid_component_global", (g, s, c)
assert "로봇핸드·그리퍼" in c and "핸드설계·제어 아키텍처" in c, c
assert s < 11, ("current 2026-10-01 Atlas hand architecture must be a silent baseline", s, c)

atlas_hand_award = make(
    "Boston Dynamics names Atlas hand supplier",
    "Boston Dynamics selected a supplier for 20,000 Atlas 13 DOF tactile robot hands under a production contract.",
    "Boston Dynamics",
)
g, s, c, k = classify(atlas_hand_award)
assert g == "humanoid_component_global", (g, s, c)
assert c.endswith("고객선정·수주·수주잔고"), c
assert s >= 11, s

clone_hand_baseline = make(
    "Clone Robotics shows Torso 3 robotic hand",
    "Clone Robotics shared a teleoperation demo of the Torso 3 five-finger robot hand using Myofiber water hydraulic artificial muscles.",
    "Clone Robotics",
)
g, s, c, k = classify(clone_hand_baseline)
assert g == "humanoid_component_global", (g, s, c)
assert "로봇핸드·그리퍼" in c and "핸드설계·제어 아키텍처" in c, c
assert s < 11, ("Torso 3 teleoperation demo must remain a silent technology baseline", s, c)

clone_torso4_launch = make(
    "Clone Robotics launches redesigned Torso 4 hand",
    "Clone Robotics introduced a new five-finger 27 DOF robot hand using Myofiber hydraulic artificial muscles with autonomous manipulation on real hardware.",
    "Clone Robotics",
)
g, s, c, k = classify(clone_torso4_launch)
assert g == "humanoid_component_global", (g, s, c)
assert "자율조작·실물검증" in c, c
assert s >= 11, s

robotis_hand_upgrade = make(
    "ROBOTIS unveils next generation dexterous robot hand",
    "ROBOTIS introduced a new five-finger 24 DOF robot hand with direct drive joints and fingertip tactile sensors for humanoid manipulation.",
    "ROBOTIS",
)
g, s, c, k = classify(robotis_hand_upgrade)
# ROBOTIS already has a dedicated first-party/commercial lane; do not steal its
# event into the generic component group. The new discovery query only needs to
# guarantee that a material next-generation hand change stays alertable.
assert g in {"robotis", "humanoid_component_global"}, (g, s, c)
assert s >= 11, s

# 28) Hyundai/Boston Dynamics mass-production execution lane. The known
# 30,000-unit factory plan and financing exploration are baselines; legal entity,
# site/capex/construction/equipment/SOP and actual Atlas finance/RaaS launch alert.
robot_factory_baseline = make(
    "Hyundai Motor Group plans new U.S. robotics facility",
    "Hyundai Motor Group plans to establish a new robotics facility with annual capacity of 30,000 robots by 2028.",
    "Hyundai Motor Group",
)
g, s, c, k = classify(robot_factory_baseline)
assert g == "hyundai_atlas_rollout", (g, s, c)
assert s < 11, ("known 30,000-unit factory plan must remain a silent baseline", s, c)

robot_factory_legal = make(
    "Hyundai Motor Group establishes Robotics America",
    "Hyundai Motor Group established and registered Robotics America as a new robot production subsidiary for its U.S. robotics facility and Atlas mass production.",
    "Hyundai Motor Group",
)
g, s, c, k = classify(robot_factory_legal)
assert g == "hyundai_atlas_rollout", (g, s, c)
assert c.endswith("미국 로봇 생산법인 설립·등록"), c
assert s >= 11, s

robot_factory_site = make(
    "Hyundai selects Georgia site for new robot factory",
    "Hyundai Motor Group finalized the Georgia site for a robot factory with annual capacity of 30,000 robots and signed the land acquisition agreement.",
    "Hyundai Motor Group",
)
g, s, c, k = classify(robot_factory_site)
assert g == "hyundai_atlas_rollout", (g, s, c)
assert c.endswith("미국 로봇공장 부지·입지 확정"), c
assert s >= 11, s

robot_factory_sop = make(
    "Hyundai U.S. robot factory starts Atlas mass production",
    "Hyundai Motor Group started mass production at its U.S. robotics facility and completed the first 100 Atlas robots.",
    "Hyundai Motor Group",
)
g, s, c, k = classify(robot_factory_sop)
assert g == "hyundai_atlas_rollout", (g, s, c)
assert c.endswith("미국 로봇공장 양산개시·첫 생산"), c
assert s >= 11, s

robot_finance_baseline = make(
    "Hyundai explores robot financing",
    "Hyundai Capital is exploring the feasibility to finance sales of Atlas robots through Hyundai dealer partners.",
    "Hyundai Motor",
)
g, s, c, k = classify(robot_finance_baseline)
assert g == "hyundai_atlas_rollout", (g, s, c)
assert s < 11, ("financing exploration is a baseline, not a launch", s, c)

robot_finance_launch = make(
    "Hyundai Capital launches Atlas robot financing program",
    "Hyundai Capital launched a 36-month lease and subscription financing program for Atlas robot sales through dealer partners, with the first customer contract signed.",
    "Hyundai Capital",
)
g, s, c, k = classify(robot_finance_launch)
assert g == "hyundai_atlas_rollout", (g, s, c)
assert c.endswith("Atlas 판매·RaaS·금융채널 상용화"), c
assert s >= 11, s

# 29) Optimus AI5/AI6 onboard-memory lane. The Oct. 1, 2026 Musk
# statement is a silent baseline because the user already surfaced it; later
# capacity/type/bandwidth or named-memory-supplier changes must alert.
optimus_memory_baseline = make(
    "Elon Musk updates Tesla AI5 and AI6 RAM for Optimus",
    "Elon Musk: We cut our RAM in half for the Tesla AI5 chip, now 72GB of LP5, and 1/3 for AI6, now 144GB of LP6. This was the only way to have sufficient volume for Optimus production and significantly lowers cost. Memory bandwidth is unchanged.",
    "Elon Musk (X)",
)
g, s, c, k = classify(optimus_memory_baseline)
assert g == "tesla", (g, s, c)
assert c == "Optimus AI5·AI6 메모리 사양 기준선", c
assert s < 11, ("known Oct 1 memory-spec statement must be a silent baseline", s, c)

optimus_memory_change = make(
    "Elon Musk changes Tesla AI5 RAM for Optimus",
    "Elon Musk says Tesla changed AI5 RAM for Optimus production to 96GB LP5 while keeping memory bandwidth unchanged to improve local model capacity.",
    "Elon Musk (X)",
)
g, s, c, k = classify(optimus_memory_change)
assert g == "tesla", (g, s, c)
assert c == "Optimus AI5·AI6 온디바이스 메모리·대역폭 사양 변경", c
assert s >= 11, s

optimus_memory_vendor = make(
    "Tesla selects Samsung for Optimus AI5 memory supply",
    "Tesla selected Samsung as an AI5 RAM supplier for Optimus under a production contract for 72GB LP5 memory per AI5 system.",
    "Tesla",
)
g, s, c, k = classify(optimus_memory_vendor)
assert g == "tesla", (g, s, c)
assert c == "Optimus AI5·AI6 메모리 공급사·물량 확정", c
assert s >= 11, s

# 30) Gemini Robotics platform lane. Current July-2026 partner/model
# announcements stay as the baseline; new hardware partners, public availability
# and paid/customer deployments are separate high-signal transitions.
gemini_new_partner = make(
    "Google DeepMind announces new Gemini Robotics partnership with NEURA Robotics",
    "Google DeepMind announced a new partnership with NEURA Robotics to integrate Gemini Robotics into a humanoid robot platform.",
    "Google DeepMind",
)
g, s, c, k = classify(gemini_new_partner)
assert g == "frontier_ai", (g, s, c)
assert c.endswith("Gemini Robotics 신규 하드웨어 파트너"), c
assert s >= 11, s

gemini_ga = make(
    "Gemini Robotics On-Device 2 generally available",
    "Google DeepMind made Gemini Robotics On-Device 2 generally available through a public API for robotics developers.",
    "Google DeepMind",
)
g, s, c, k = classify(gemini_ga)
assert g == "frontier_ai", (g, s, c)
assert c.endswith("Gemini Robotics 모델·API 일반 공개"), c
assert s >= 11, s

gemini_commercial = make(
    "Gemini Robotics wins first paid production deployment",
    "Google DeepMind signed a commercial contract to deploy Gemini Robotics on 2,000 humanoid robots at a customer production site.",
    "Google DeepMind",
)
g, s, c, k = classify(gemini_commercial)
assert g == "frontier_ai", (g, s, c)
assert c.endswith("Gemini Robotics 유료계약·상용 배치"), c
assert s >= 11, s

# 31) Gemini Robotics access-state baseline. ER 2 is already public
# preview via Google AI Studio / Gemini API, while VLA and On-Device 2 remain
# private preview / early access. Rewrites of those statuses must stay silent;
# widening VLA/On-Device access must alert.
gemini_er2_public_preview_baseline = make(
    "Gemini Robotics ER 2 public preview",
    "Google DeepMind says Gemini Robotics ER 2 is in public preview on Google AI Studio and the Gemini API for robotics developers.",
    "Google DeepMind",
)
g, s, c, k = classify(gemini_er2_public_preview_baseline)
assert s < 11, ("ER 2 public preview is current baseline, not general availability", g, s, c)

gemini_vla_private_preview_baseline = make(
    "Gemini Robotics 2 private preview",
    "Google DeepMind says Gemini Robotics 2 VLA is in private preview for robotics trusted testers.",
    "Google DeepMind",
)
g, s, c, k = classify(gemini_vla_private_preview_baseline)
assert s < 11, ("VLA private preview is current baseline", g, s, c)

gemini_vla_public_preview = make(
    "Gemini Robotics 2 expands to public preview",
    "Google DeepMind opened Gemini Robotics 2 VLA to public preview through the Gemini API for robotics developers.",
    "Google DeepMind",
)
g, s, c, k = classify(gemini_vla_public_preview)
assert g == "frontier_ai", (g, s, c)
assert c.endswith("Gemini Robotics 모델 공개 범위 확대"), c
assert s >= 11, s

gemini_ondevice_public_api = make(
    "Gemini Robotics On-Device 2 expands access",
    "Google DeepMind opened Gemini Robotics On-Device 2 through a public API for robotics developers.",
    "Google DeepMind",
)
g, s, c, k = classify(gemini_ondevice_public_api)
assert g == "frontier_ai", (g, s, c)
assert c.endswith("Gemini Robotics 모델 공개 범위 확대"), c
assert s >= 11, s

# 32) 46-series EV cylindrical battery lane. Current contracts/plans
# surfaced by the user are baselines; new OEM confirmation, binding orders,
# equipment execution, SOP, first shipment, ramp metrics and reversals alert.
ev46_lges_backlog_baseline = make(
    "LG Energy Solution 46-series backlog exceeds 440GWh",
    "LG Energy Solution secured more than 100GWh of new 46-series orders in Q1 2026, bringing its 46-series order backlog above 440GWh.",
    "LG Energy Solution",
)
g, s, c, k = classify(ev46_lges_backlog_baseline)
assert g == "ev_46_series", (g, s, c)
assert s < 11, ("440GWh / 100GWh Q1 figures are current baseline", s, c)

ev46_rivian_baseline = make(
    "LG Energy Solution to supply Rivian 4695 batteries",
    "LG Energy Solution signed a 67GWh five-year supply contract for 4695 46-series cylindrical batteries for Rivian R2.",
    "LG Energy Solution",
)
g, s, c, k = classify(ev46_rivian_baseline)
assert g == "ev_46_series", (g, s, c)
assert s < 11, ("Rivian 67GWh 4695 contract is current baseline", s, c)

ev46_mercedes_baseline = make(
    "LG Energy Solution to supply Mercedes-Benz 46100 cells from Poland",
    "TheElec reports LG Energy Solution plans a 46100 line at Wroclaw in 2027 for Mercedes-Benz supply from 2028 and is considering BMA equipment investment.",
    "디일렉",
)
g, s, c, k = classify(ev46_mercedes_baseline)
assert g == "ev_46_series", (g, s, c)
assert s < 11, ("Mercedes 46100 2028 report is user-surfaced baseline", s, c)

ev46_indigo_mou = make(
    "LG Energy Solution and indiGOtech sign 46-series MOU",
    "The companies signed a nonbinding MOU to explore 46-series battery supply for Flow Ride and Flow Cargo from 2027 to 2030.",
    "LG Energy Solution",
)
g, s, c, k = classify(ev46_indigo_mou)
assert g == "ev_46_series", (g, s, c)
assert s < 11, ("nonbinding indiGOtech MOU must not be treated as firm order", s, c)

ev46_volvo_format = make(
    "Volvo confirms 4695 cylindrical battery format",
    "Volvo officially confirmed adoption of 4695 46mm cylindrical batteries for its next EV platform.",
    "Volvo",
)
g, s, c, k = classify(ev46_volvo_format)
assert g == "ev_46_series", (g, s, c)
assert c.endswith("완성차 46파이 규격 공식 채택"), c
assert s >= 11, s

ev46_arizona_sop = make(
    "LG Energy Solution starts 46-series mass production in Arizona",
    "LG Energy Solution started mass production of 4680, 4695, 46100 and 46120 46-series cells at its Queen Creek Arizona plant.",
    "LG Energy Solution",
)
g, s, c, k = classify(ev46_arizona_sop)
assert g == "ev_46_series", (g, s, c)
assert c.endswith("46시리즈 실제 양산 개시"), c
assert s >= 11, s

ev46_poland_equipment = make(
    "LG Energy Solution orders equipment for Poland 46100 line",
    "LG Energy Solution placed equipment orders and began production-line installation for a 46100 46-series line in Wroclaw Poland.",
    "LG Energy Solution",
)
g, s, c, k = classify(ev46_poland_equipment)
assert g == "ev_46_series", (g, s, c)
assert c.endswith("46시리즈 장비발주·반입·라인 구축"), c
assert s >= 11, s

ev46_bma = make(
    "LG Energy Solution confirms Mercedes 46100 BMA investment",
    "LG Energy Solution approved investment and equipment orders for battery module assembly BMA alongside its Mercedes-Benz 46100 cell line.",
    "LG Energy Solution",
)
g, s, c, k = classify(ev46_bma)
assert g == "ev_46_series", (g, s, c)
assert c.endswith("46시리즈 모듈조립 내재화·투자"), c
assert s >= 11, s

ev46_component_order = make(
    "KNS wins 46-series assembly equipment order",
    "KNS won a contract to supply rivet and inspection equipment for a 4695 46-series battery production line for LG Energy Solution.",
    "KNS",
)
g, s, c, k = classify(ev46_component_order)
assert g == "ev_46_series", (g, s, c)
assert c.endswith("46시리즈 소재·장비 직접 수주"), c
assert s >= 11, s

# 33) FieldAI funding/commercialization lane. The Oct. 2 funding report
# and $135M revenue+contracts / 30+ customer figures are user-surfaced baselines.
# Alert only on an actual close/terms change, new commercial metrics, a new
# production partner/deployment, or direct Hyundai/Atlas/RMAC integration.
fieldai_funding_proposed_baseline = make(
    "FieldAI set to raise $700 million at $10 billion valuation",
    "FieldAI is raising $700 million at a $10 billion valuation. The funding has not formally closed and final investment commitments are not yet finalized.",
    "Business Insider",
)
g, s, c, k = classify(fieldai_funding_proposed_baseline)
assert g == "fieldai", (g, s, c)
assert c.endswith("기업가치 100억달러·7억달러 조달 추진 기준선"), c
assert s < 11, ("current FieldAI financing proposal must stay silent", s, c)

fieldai_commercial_baseline = make(
    "FieldAI passes $135 million in revenue and customer contracts",
    "FieldAI has more than $135 million in revenue and customer contracts across more than 30 customers.",
    "Business Insider",
)
g, s, c, k = classify(fieldai_commercial_baseline)
assert g == "fieldai", (g, s, c)
assert c.endswith("고객 30곳+·매출+계약 1.35억달러 기준선"), c
assert s < 11, ("$135M + 30 customers is current baseline", s, c)

fieldai_funding_close = make(
    "FieldAI closes $700 million funding round at $10 billion valuation",
    "FieldAI announced that its funding round closed and completed at $700 million with a $10 billion valuation.",
    "FieldAI",
)
g, s, c, k = classify(fieldai_funding_close)
assert g == "fieldai", (g, s, c)
assert c.endswith("투자유치 종결"), c
assert s >= 11, s

fieldai_commercial_change = make(
    "FieldAI commercial contracts expand",
    "FieldAI said revenue and customer contracts increased to $200 million across 45 customers, surpassing its prior level.",
    "FieldAI",
)
g, s, c, k = classify(fieldai_commercial_change)
assert g == "fieldai", (g, s, c)
assert c.endswith("매출·계약·수주잔고·고객수 증가"), c
assert s >= 11, s

fieldai_hyundai_atlas = make(
    "FieldAI and Hyundai integrate FFM with Atlas",
    "FieldAI and Hyundai announced a production deployment partnership integrating Field Foundation Models with Atlas at HMGMA after RMAC validation.",
    "FieldAI",
)
g, s, c, k = classify(fieldai_hyundai_atlas)
assert g == "fieldai", (g, s, c)
assert c.endswith("현대차·Atlas·RMAC 직접 통합"), c
assert s >= 11, s

fieldai_hyundai_stake = make(
    "Hyundai discloses FieldAI equity stake",
    "Hyundai disclosed that it owns a 2.5% equity stake in FieldAI following an additional investment.",
    "Hyundai Motor Group",
)
g, s, c, k = classify(fieldai_hyundai_stake)
assert g == "fieldai", (g, s, c)
assert c.endswith("현대차 추가투자·지분 공개"), c
assert s >= 11, s

fieldai_partner_baseline = make(
    "Boston Dynamics and FieldAI partner on construction autonomy",
    "Boston Dynamics and FieldAI announced a strategic partnership for FieldAI Field Foundation Models on Spot in construction deployments.",
    "FieldAI",
)
g, s, c, k = classify(fieldai_partner_baseline)
assert g == "fieldai", (g, s, c)
assert s < 11, ("existing Boston Dynamics partnership must remain baseline", s, c)

# 34) NVIDIA/Jensen robotics inflection timeline lane.
# Official 2025/2026 ChatGPT-moment rhetoric is already the baseline. The
# user-surfaced "within a year" roadshow note is not publicly corroborated, so
# it must remain silent until an official/direct-quote source confirms it.
nvidia_robotics_official_baseline = make(
    "NVIDIA: The ChatGPT moment for robotics is here",
    "Jensen Huang said the ChatGPT moment for robotics is here as physical AI models understand the real world, reason and plan actions.",
    "NVIDIA",
)
g, s, c, k = classify(nvidia_robotics_official_baseline)
assert g == "nvidia_robotics_exec", (g, s, c)
assert c.endswith("로보틱스 ChatGPT 모먼트 공식 수사 기준선"), c
assert s < 11, ("official CES 2026 ChatGPT-moment rhetoric is already baseline", s, c)

nvidia_robotics_roadshow_unverified = make(
    "Jensen Huang roadshow meeting comment",
    "Roadshow investor meeting note: robotics ChatGPT moment is very close, within a year.",
    "Roadshow meeting note",
)
g, s, c, k = classify(nvidia_robotics_roadshow_unverified)
assert g == "nvidia_robotics_exec", (g, s, c)
assert c.endswith("로드쇼 1년 이내 코멘트 미확인 기준선"), c
assert s < 11, ("unverified roadshow quote must not alert", s, c)

nvidia_robotics_within_year_confirmed = make(
    "Jensen Huang says robotics inflection is within a year",
    "NVIDIA CEO Jensen Huang said the ChatGPT moment for robotics will occur within a year as general-purpose robot brains mature.",
    "NVIDIA",
)
g, s, c, k = classify(nvidia_robotics_within_year_confirmed)
assert g == "nvidia_robotics_exec", (g, s, c)
assert c.endswith("1년 이내 로보틱스 변곡점 시간표"), c
assert s >= 11, s

nvidia_robotics_timeline_change = make(
    "Jensen Huang changes robotics timeline",
    "Jensen Huang said the general-purpose brain for robotics is likely within two years rather than the near-term window.",
    "Reuters",
)
g, s, c, k = classify(nvidia_robotics_timeline_change)
assert g == "nvidia_robotics_exec", (g, s, c)
assert c.endswith("로보틱스 변곡점 시간표 변경"), c
assert s >= 11, s

nvidia_robotics_quantified = make(
    "NVIDIA expands production robot deployments",
    "NVIDIA said its robotics platform is now deployed across 120 production sites with 8,000 robots using Jetson and GR00T.",
    "NVIDIA",
)
g, s, c, k = classify(nvidia_robotics_quantified)
assert g == "nvidia_robotics_exec", (g, s, c)
assert c.endswith("로봇 배치·생산·고객 정량 확대"), c
assert s >= 11, s

# 35) 46-series second-pass baseline and execution guards.
# Lock the newly verified Samsung SDI / LGES / SK On / SNE facts as silent
# baselines, but alert when customer identity, quantity, qualification, order,
# shipment metrics or market forecasts materially advance.

ev46_sdi_europe_order_baseline = make(
    "Samsung SDI secured 46-phi order for European global EV",
    "Samsung SDI secured an order for 46-phi cylindrical batteries for a European global EV premium lineup. The project targets mass production in 2028 through a new production line at the Hungary site. Customer, GWh and exact 46xx format were not disclosed.",
    "Samsung SDI",
)
g, s, c, k = classify(ev46_sdi_europe_order_baseline)
assert g == "ev_46_series", (g, s, c)
assert c.endswith("현재 계약·양산 기준선"), c
assert s < 11, ("Samsung SDI anonymous Europe order is current baseline", s, c)

ev46_sdi_detail = make(
    "Samsung SDI discloses 4695 customer for Europe order",
    "Samsung SDI confirmed BMW as the customer for its 4695 46-series project at the Hungary plant with 40GWh supply and mass production from 2028.",
    "Samsung SDI",
)
g, s, c, k = classify(ev46_sdi_detail)
assert g == "ev_46_series", (g, s, c)
assert c.endswith("삼성SDI 유럽 46파이 고객·물량·규격 공개"), c
assert s >= 11, s

ev46_kgm_mou_baseline = make(
    "Samsung SDI and KGM sign MOU for 46-series battery pack",
    "Samsung SDI and KG Mobility signed an MOU to jointly develop next-generation EV battery pack technologies using 46-series cylindrical batteries.",
    "Samsung SDI",
)
g, s, c, k = classify(ev46_kgm_mou_baseline)
assert g == "ev_46_series", (g, s, c)
assert c.endswith("현재 계약·양산 기준선"), c
assert s < 11, ("KGM 46-series pack MOU is current baseline", s, c)

ev46_kgm_binding = make(
    "Samsung SDI signs KGM 46-series supply contract",
    "Samsung SDI signed a binding supply contract with KG Mobility for 46-series cylindrical batteries for a next-generation EV.",
    "Samsung SDI",
)
g, s, c, k = classify(ev46_kgm_binding)
assert g == "ev_46_series", (g, s, c)
assert c.endswith("완성차 공급계약·GWh 수주"), c
assert s >= 11, s

ev46_skon_dev_baseline = make(
    "SK On completes 46-series battery development",
    "SK On completed development of 46-series cylindrical cells including 4680, 4695 and 46120 and is preparing production technology.",
    "SK On",
)
g, s, c, k = classify(ev46_skon_dev_baseline)
assert g == "ev_46_series", (g, s, c)
assert c.endswith("현재 계약·양산 기준선"), c
assert s < 11, ("SK On development completion is current baseline", s, c)

ev46_skon_proto_baseline = make(
    "SK On runs 46-series prototypes in Changzhou",
    "SK On is producing 46-series cylindrical battery prototypes at Changzhou on a research line capable of 300,000 units per year.",
    "TheElec",
)
g, s, c, k = classify(ev46_skon_proto_baseline)
assert g == "ev_46_series", (g, s, c)
assert c.endswith("현재 계약·양산 기준선"), c
assert s < 11, ("SK On 300k prototype line is current baseline", s, c)

ev46_skon_qualification = make(
    "SK On 46-series passes customer qualification",
    "SK On's 4695 46-series cells passed customer qualification and approval for an EV program.",
    "SK On",
)
g, s, c, k = classify(ev46_skon_qualification)
assert g == "ev_46_series", (g, s, c)
assert c.endswith("SK온 46파이 고객 검증·승인"), c
assert s >= 11, s

ev46_lges_15x_baseline = make(
    "LG Energy Solution Q2 cylindrical shipments rise 1.5x",
    "LG Energy Solution said cylindrical battery shipments including 46-Series increased 1.5x year-on-year in Q2 2026.",
    "LG Energy Solution",
)
g, s, c, k = classify(ev46_lges_15x_baseline)
assert g == "ev_46_series", (g, s, c)
assert c.endswith("현재 계약·양산 기준선"), c
assert s < 11, ("LGES 1.5x cylindrical shipment figure is current baseline", s, c)

ev46_market_baseline = make(
    "SNE Research 46-series market outlook",
    "SNE Research forecasts the global 46-series cylindrical battery market to grow from 155GWh in 2025 to 650GWh in 2030, a 33% CAGR.",
    "SNE Research",
)
g, s, c, k = classify(ev46_market_baseline)
assert g == "ev_46_series", (g, s, c)
assert c.endswith("현재 계약·양산 기준선"), c
assert s < 11, ("155GWh to 650GWh forecast is current baseline", s, c)

ev46_market_revision = make(
    "SNE Research revises 46-series outlook",
    "SNE Research revised its 2030 46-series cylindrical battery market forecast upward to 800GWh.",
    "SNE Research",
)
g, s, c, k = classify(ev46_market_revision)
assert g == "ev_46_series", (g, s, c)
assert c.endswith("46시리즈 시장전망 수정"), c
assert s >= 11, s

# 35) Sodium-ion commercialization lane. Current CATL/EVE/Korean
# development milestones are baselines; actual shipments, customer validation,
# price parity transactions, new contracts and safety/reversal events must alert.
sodium_catl_contract_baseline = make(
    "CATL and HyperStrong sign sodium-ion ESS cooperation",
    "CATL and HyperStrong signed a three-year 60GWh sodium-ion battery supply agreement for energy storage.",
    "CATL",
)
g, s, c, k = classify(sodium_catl_contract_baseline)
assert g == "sodium_ion_battery", (g, s, c)
assert c.endswith("현재 상용화 기준선"), c
assert s < 11, ("CATL-HyperStrong 60GWh contract is current baseline", s, c)

sodium_catl_capacity_baseline = make(
    "CATL expands sodium-ion storage capacity",
    "CATL added 40GWh at Fuding and plans 160GWh at Jining for sodium-ion energy storage.",
    "CATL",
)
g, s, c, k = classify(sodium_catl_capacity_baseline)
assert g == "sodium_ion_battery", (g, s, c)
assert s < 11, ("CATL 40+160GWh capacity figures are current baseline", s, c)

sodium_lges_baseline = make(
    "LG Energy Solution develops sodium-ion battery",
    "LG Energy Solution plans commercialization in 2027, preparing production lines for sodium-ion ESS batteries and 12V applications.",
    "LG Energy Solution",
)
g, s, c, k = classify(sodium_lges_baseline)
assert g == "sodium_ion_battery", (g, s, c)
assert s < 11, ("LGES 2027 commercialization plan is current baseline", s, c)

sodium_sdi_baseline = make(
    "Samsung SDI develops sodium-ion batteries",
    "Samsung SDI is developing sodium-ion batteries for AI data center UPS and utility-scale ESS with long life, high power and safety.",
    "Samsung SDI",
)
g, s, c, k = classify(sodium_sdi_baseline)
assert g == "sodium_ion_battery", (g, s, c)
assert s < 11, ("Samsung SDI sodium development is current baseline", s, c)

sodium_skon_baseline = make(
    "SK On develops sodium-ion batteries for ESS",
    "SK On aims to complete sodium-ion ESS prototype development by 2027.",
    "매일경제",
)
g, s, c, k = classify(sodium_skon_baseline)
assert g == "sodium_ion_battery", (g, s, c)
assert s < 11, ("SK On 2027 prototype target is current baseline", s, c)

sodium_eve_baseline = make(
    "EVE Energy validates NF155L sodium-ion ESS",
    "EVE Energy's NF155L sodium-ion cell was used in a 180kWh grid-connected energy storage system and batch delivery is planned by the end of 2026.",
    "EVE Energy",
)
g, s, c, k = classify(sodium_eve_baseline)
assert g == "sodium_ion_battery", (g, s, c)
assert s < 11, ("EVE 180kWh grid-connected system and 2026 delivery plan are baseline", s, c)

sodium_hina_baseline = make(
    "HiNa Battery completes sodium-ion heavy truck test",
    "HiNa Battery completed nearly 7 months and more than 15,000 km of road testing with a 339kWh sodium-ion battery.",
    "HiNa Battery",
)
g, s, c, k = classify(sodium_hina_baseline)
assert g == "sodium_ion_battery", (g, s, c)
assert s < 11, ("HiNa 339kWh 15,000km validation is current baseline", s, c)

sodium_enertech_baseline = make(
    "Enertech plans sodium-ion mass production",
    "Enertech developed a 140-160 Wh/kg sodium-ion prototype and plans mass production at Chungju in January 2027.",
    "Enertech International",
)
g, s, c, k = classify(sodium_enertech_baseline)
assert g == "sodium_ion_battery", (g, s, c)
assert s < 11, ("Enertech January 2027 production plan is current baseline", s, c)

sodium_catl_shipment = make(
    "CATL begins sodium-ion ESS customer shipments",
    "CATL completed its first commercial delivery of 1.2GWh of sodium-ion energy storage systems to customers.",
    "CATL",
)
g, s, c, k = classify(sodium_catl_shipment)
assert g == "sodium_ion_battery", (g, s, c)
assert c.endswith("나트륨이온 첫·대량 출하"), c
assert s >= 11, s

sodium_lges_validation = make(
    "LG Energy Solution completes sodium-ion ESS customer validation",
    "LG Energy Solution completed customer validation of sodium-ion ESS samples and received customer approval for a 2027 production program.",
    "LG Energy Solution",
)
g, s, c, k = classify(sodium_lges_validation)
assert g == "sodium_ion_battery", (g, s, c)
assert c.endswith("한국 나트륨이온 고객 검증·승인"), c
assert s >= 11, s

sodium_price_parity = make(
    "CATL sodium-ion ESS contract price reaches LFP parity",
    "CATL disclosed an actual contract price of 0.35 yuan/Wh for sodium-ion ESS cells versus 0.35 yuan/Wh for comparable LFP cells.",
    "CATL",
)
g, s, c, k = classify(sodium_price_parity)
assert g == "sodium_ion_battery", (g, s, c)
assert c.endswith("나트륨이온 실제 가격·LFP 패리티"), c
assert s >= 11, s

sodium_safety = make(
    "Sodium-ion ESS fire incident under investigation",
    "CATL said a sodium-ion energy storage system fire incident is under investigation after thermal runaway was reported.",
    "CATL",
)
g, s, c, k = classify(sodium_safety)
assert g == "sodium_ion_battery", (g, s, c)
assert c.endswith("나트륨이온 안전성 역풍"), c
assert s >= 11, s

sodium_generic_market_explainer = make(
    "차세대 ESS 배터리로 떠오른 나트륨…한·중 대표기업 시장 선점 나서",
    "나트륨이온 배터리는 ESS에서 LFP와 경쟁할 차세대 기술로 주목받고 있다.",
    "한국경제",
)
g, s, c, k = classify(sodium_generic_market_explainer)
assert g == "sodium_ion_battery", (g, s, c)
assert s < 11, ("generic sodium-ion ESS market explainer must stay silent", s, c)

# 36) Quantity enrichment must never parse opaque link payloads as physical quantities.
# A prior Google News article URL contained the substring "25kM" and produced a
# false "확인 물량 25kM" line. Only user-visible alert text may feed quantity parsing.
url_quantity_noise = (
    '<b>출처</b> 한국경제 · <a href="https://news.google.com/rss/articles/ABC25kMnNoSm1z?oc=5">'
    '<b>원문</b></a>'
)
assert watcher.qty._qty_summary(url_quantity_noise) == "", (
    "opaque URL payload must not become a quantity",
    watcher.qty._qty_summary(url_quantity_noise),
)
visible_quantity = url_quantity_noise + "\\n현장 검증 주행거리 15,000km 완료"
assert watcher.qty._qty_summary(visible_quantity) == "15,000km", (
    "visible physical quantity must still be preserved",
    watcher.qty._qty_summary(visible_quantity),
)

# 37) Brett Adcock's personal X account is not Figure-exclusive anymore.
# Hark/Handoff product posts and generic ambiguous AI teasers must not be
# attributed to Figure AI. Only explicit Figure/Helix/robot/humanoid context
# can enter the Figure lane.
hark_launch = figure_lane._make_figure_item(
    "2106889503919292529",
    "Hark launches this week. The first 100,000 sign-ups get the paid plan free. Join the waitlist.",
    watcher.base.NOW,
)
assert hark_launch is None, "Hark launch post must not become a Figure AI alert"

hark_benchmark = figure_lane._make_figure_item(
    "2106889503919292530",
    "Handoff is our personal AI browser agent. It launches this week with a 97.7% benchmark score.",
    watcher.base.NOW,
)
assert hark_benchmark is None, "Handoff benchmark must stay outside Figure AI"

ambiguous_founder_teaser = figure_lane._make_figure_item(
    "2106889503919292531",
    "Major AI update tomorrow. See you in the AM.",
    watcher.base.NOW,
)
assert ambiguous_founder_teaser is None, "Ambiguous founder AI teaser must stay silent"

explicit_figure_teaser = figure_lane._make_figure_item(
    "2106889503919292532",
    "Figure 03 AI update tomorrow. New humanoid autonomy results in the AM.",
    watcher.base.NOW,
)
assert explicit_figure_teaser is not None, "Explicit Figure humanoid teaser must still alert"
g, s, c, k = classify(explicit_figure_teaser)
assert g == "figure_ai", (g, s, c)
assert s >= 11, s

third_party_hark = make(
    "Figure founder Brett Adcock launches personal AI product Hark this week",
    "Hark will launch this week and the first 100,000 users get the paid plan free. Handoff is a browser agent.",
    "Reuters",
)
g, s, c, k = classify(third_party_hark)
assert g != "figure_ai", ("third-party Hark story must not become Figure AI", g, s, c)

# 38) Project Meridian robotics-advisory lane.
# Peggy Johnson's Oct-5 selection is now a known advisory baseline: individual
# consultant, explicitly separate from Agility commercial operations. Future
# roster changes may alert, but only from official/trusted sources; an actual
# Agility/Digit military pilot or procurement must upgrade to an execution stage.
meridian_peggy_baseline = make(
    "Agility Robotics CEO Peggy Johnson Selected to Join Project Meridian",
    (
        "Agility Robotics announced that CEO Peggy Johnson will participate in Project Meridian, "
        "a Department of War-commissioned MITRE initiative. Johnson participates in an individual "
        "consultant capacity, separate from Agility's commercial operations, and will contribute "
        "commercial humanoid robotics experience to future warfare logistics and operational support."
    ),
    "Agility Robotics",
)
g, s, c, k = classify(meridian_peggy_baseline)
assert g == "us_autonomous_warfare", (g, s, c)
assert c.endswith("Project Meridian 휴머노이드 자문 참여 기준선"), c
assert s < 11, ("Peggy Johnson individual-consultant selection is known baseline", s, c)

meridian_new_robotics_member = make(
    "Boston Dynamics CEO Jane Example Selected to Join Project Meridian",
    (
        "MITRE added Boston Dynamics CEO Jane Example as a new Project Meridian participant "
        "to advise on humanoid robotics, autonomous logistics and future warfare capability priorities."
    ),
    "MITRE",
)
g, s, c, k = classify(meridian_new_robotics_member)
assert g == "us_autonomous_warfare", (g, s, c)
assert c.endswith("Project Meridian 로봇·AI 자문진 확대"), c
assert s >= 11, s

meridian_unverified_member = make(
    "Robotics executive reportedly joins Project Meridian",
    (
        "An unnamed blog claims a new robotics executive was selected to join Project Meridian "
        "for autonomous logistics advice."
    ),
    "Unknown Blog",
)
g, s, c, k = classify(meridian_unverified_member)
assert g == "us_autonomous_warfare", (g, s, c)
assert s < 11, ("unverified Meridian roster rumor must stay silent", s, c)

agility_defense_pilot = make(
    "Agility Digit begins Department of War logistics pilot",
    (
        "Agility Robotics began a military evaluation pilot with the Department of War, "
        "deploying 20 Digit humanoid robots at a logistics site for operational evaluation."
    ),
    "Agility Robotics",
)
g, s, c, k = classify(agility_defense_pilot)
assert g == "us_autonomous_warfare", (g, s, c)
assert c.endswith("Agility Digit 국방 실증·운용평가"), c
assert s >= 11, s

agility_defense_contract = make(
    "Department of War awards Agility Robotics Digit procurement contract",
    (
        "The Department of War awarded Agility Robotics a $120 million procurement contract "
        "for 250 Digit humanoid robots for logistics support."
    ),
    "U.S. Department of War",
)
g, s, c, k = classify(agility_defense_contract)
assert g == "us_autonomous_warfare", (g, s, c)
assert c.endswith("Agility Digit 국방 조달·수주"), c
assert s >= 11, s

# 39) Figure X mirror-context contamination guard.
# A broad profile mirror may place a genuine Figure teaser next to an unrelated
# reply/post. Such context is discovery-only and must never trigger Telegram.
mirror_context_item = figure_lane._make_figure_item(
    "2107256785694609428",
    (
        "@is_OwenLewis Hour "
        "Nearby profile context: Figure 03 humanoid AI breakthrough will be showcased tomorrow"
    ),
    watcher.base.NOW,
    text_integrity="mirror_context",
    fetch_path="profile_mirror",
)
assert mirror_context_item is not None, "test fixture should classify before provenance gate"
g, s, c, k = classify(mirror_context_item)
assert g == "figure_ai", (g, s, c)
assert s < 11, ("mirror-context Figure contamination must stay silent", s, c)

exact_figure_teaser = figure_lane._make_figure_item(
    "2107220541400814028",
    "We’ve had an AI breakthrough at Figure and will be showcasing this tomorrow",
    watcher.base.NOW,
    text_integrity="exact_tweet",
    fetch_path="x_syndication",
)
assert exact_figure_teaser is not None
g, s, c, k = classify(exact_figure_teaser)
assert g == "figure_ai", (g, s, c)
assert c.endswith("공식 사전예고·공개 시간표"), c
assert s >= 11, s

# 40) Robot/physical-AI compute semiconductor lane.
# Marc Raibert's SLW 2026 comment is an industry outlook, not confirmation that
# Samsung/Google have a robot-chip program. Existing NVIDIA/AMD/Arm platforms are
# baselines; only company execution stages alert.
raibert_robot_chip_outlook = make(
    "보스턴다이나믹스 창립자 삼성도 로봇 칩 가능",
    (
        "마크 레이버트는 SLW 2026에서 현재 엔비디아가 지배적이지만 "
        "Google, Samsung Electronics, AMD, Arm 등도 로봇에 특화된 칩 프로그램이 있을 수 있고 "
        "아직 로봇용 칩을 만들지 않는 기업들도 시작할 수 있다고 전망했다."
    ),
    "뉴스1",
)
g, s, c, k = classify(raibert_robot_chip_outlook)
assert g == "robot_compute_semiconductor", (g, s, c)
assert c.endswith("레이버트 전망 기준선"), c
assert s < 11, ("expert outlook must not become Samsung/Google chip confirmation", s, c)

amd_robot_compute_baseline = make(
    "AMD Ryzen AI Embedded for autonomous robotics and physical AI",
    (
        "AMD Ryzen AI Embedded X100 processors combine CPU GPU and NPU and are optimized "
        "for real-time AI, robotics, automation and physical AI."
    ),
    "AMD",
)
g, s, c, k = classify(amd_robot_compute_baseline)
assert g == "robot_compute_semiconductor", (g, s, c)
assert c.endswith("기존 상용 플랫폼 기준선"), c
assert s < 11, ("existing AMD robotics compute portfolio is baseline", s, c)

arm_robot_compute_baseline = make(
    "Arm Total Design expands to Physical AI robotics",
    (
        "Arm Total Design for Physical AI and the Robotics Capability Framework provide "
        "a compute foundation for robotics and autonomous systems."
    ),
    "Arm",
)
g, s, c, k = classify(arm_robot_compute_baseline)
assert g == "robot_compute_semiconductor", (g, s, c)
assert c.endswith("기존 상용 플랫폼 기준선"), c
assert s < 11, ("existing Arm physical-AI platform is baseline", s, c)

samsung_robot_chip_program = make(
    "Samsung System LSI announces dedicated humanoid robotics processor program",
    (
        "Samsung Electronics System LSI officially announced development of a purpose-built "
        "robotics SoC for humanoid physical AI, with customer samples planned for 2027."
    ),
    "Samsung Electronics",
)
g, s, c, k = classify(samsung_robot_chip_program)
assert g == "robot_compute_semiconductor", (g, s, c)
assert c.endswith("공식 개발·로드맵 착수"), c
assert s >= 11, s

samsung_robot_chip_sample = make(
    "Samsung robot SoC tapeout completed",
    (
        "Samsung Electronics completed tapeout of its dedicated humanoid robotics SoC "
        "and started customer sample validation."
    ),
    "Samsung Electronics",
)
g, s, c, k = classify(samsung_robot_chip_sample)
assert g == "robot_compute_semiconductor", (g, s, c)
assert c.endswith("테이프아웃·고객 샘플"), c
assert s >= 11, s

samsung_robot_foundry_contract = make(
    "Samsung Foundry wins physical AI robot-chip production contract",
    (
        "Samsung Electronics Foundry was selected for a production contract to manufacture "
        "a humanoid robotics AI processor for a named robot customer."
    ),
    "Samsung Electronics",
)
g, s, c, k = classify(samsung_robot_foundry_contract)
assert g == "robot_compute_semiconductor", (g, s, c)
assert c.endswith("삼성 파운드리 생산수주"), c
assert s >= 11, s

robot_chip_rumor = make(
    "Samsung may develop a robot NPU",
    "An unnamed blog says Samsung could possibly develop a humanoid robot NPU in the future.",
    "Unknown Blog",
)
g, s, c, k = classify(robot_chip_rumor)
assert s < 11, ("unverified robot-chip rumor must stay silent", g, s, c)

# 41) Physical-AI onboard memory/storage lane.
# Secondary "HBM next is robot memory" narratives and already-public Samsung/SK
# products are silent baselines. Named robot customer execution must alert.
phys_mem_media_baseline = make(
    "HBM 다음은 로봇 반도체…삼성·SK하이닉스, 피지컬AI 메모리 선점",
    (
        "삼성전자와 SK하이닉스가 로봇과 휴머노이드용 저전력 메모리 시장을 준비한다. "
        "HBM 다음 성장축으로 LPDDR6, LPDDR5X, NAND와 스토리지가 거론된다."
    ),
    "뉴스핌",
)
g, s, c, k = classify(phys_mem_media_baseline)
assert g == "physical_ai_memory", (g, s, c)
assert c.endswith("HBM 이후 로봇수요 기사 기준선"), c
assert s < 11, ("secondary robot-memory thesis must stay silent", s, c)

sk_robotics_lpddr_baseline = make(
    "SK hynix shows Auto/Robotics LPDDR5/5X at MWC 2026",
    (
        "SK hynix showcased Auto/Robotics LPDDR5/5X and Automotive LPDDR6 "
        "for robotics, autonomous systems and physical AI."
    ),
    "SK hynix",
)
g, s, c, k = classify(sk_robotics_lpddr_baseline)
assert g == "physical_ai_memory", (g, s, c)
assert c.endswith("기존 제품·로드맵 기준선"), c
assert s < 11, ("existing SK hynix robotics LPDDR must be baseline", s, c)

samsung_pim_baseline = make(
    "Samsung LPDDR5X-PIM accelerates Edge AI",
    (
        "Samsung Electronics LPDDR5X-PIM delivers up to 8x effective bandwidth, "
        "up to 3x LLM TPS and up to 2.2x lower runtime for Edge AI."
    ),
    "Samsung Electronics",
)
g, s, c, k = classify(samsung_pim_baseline)
assert g == "physical_ai_memory", (g, s, c)
assert c.endswith("기존 제품·로드맵 기준선"), c
assert s < 11, ("existing Samsung LPDDR5X-PIM benchmark must be baseline", s, c)

samsung_autossd_baseline = make(
    "Samsung Detachable AutoSSD targets future humanoid systems",
    (
        "Samsung Electronics said Detachable AutoSSD is designed for future autonomous vehicles "
        "and humanoid robotic systems as physical AI expands."
    ),
    "Samsung Electronics",
)
g, s, c, k = classify(samsung_autossd_baseline)
assert g == "physical_ai_memory", (g, s, c)
assert c.endswith("기존 제품·로드맵 기준선"), c
assert s < 11, ("future humanoid AutoSSD target is baseline, not a robot design win", s, c)

phys_mem_sample = make(
    "SK hynix starts LPDDR6 samples for Figure 03 humanoid",
    (
        "SK hynix started supplying customer samples of 64GB LPDDR6 to Figure AI "
        "for Figure 03 humanoid qualification."
    ),
    "SK hynix",
)
g, s, c, k = classify(phys_mem_sample)
assert g == "physical_ai_memory", (g, s, c)
assert c.endswith("로봇 고객 샘플 공급"), c
assert s >= 11, s

phys_mem_design_win = make(
    "Boston Dynamics selects Samsung LPDDR6 for Atlas",
    (
        "Boston Dynamics selected and adopted Samsung Electronics 96GB LPDDR6 "
        "for the Atlas humanoid production platform."
    ),
    "Samsung Electronics",
)
g, s, c, k = classify(phys_mem_design_win)
assert g == "physical_ai_memory", (g, s, c)
assert c.endswith("로봇 OEM 채택·디자인윈"), c
assert s >= 11, s

phys_mem_contract = make(
    "Agility signs volume memory contract with SK hynix for Digit",
    (
        "Agility Robotics signed a binding supply contract with SK hynix for LPDDR6 "
        "memory for 100,000 Digit humanoid robots."
    ),
    "SK hynix",
)
g, s, c, k = classify(phys_mem_contract)
assert g == "physical_ai_memory", (g, s, c)
assert c.endswith("로봇 OEM 본계약·물량수주"), c
assert s >= 11, s

phys_mem_content = make(
    "Figure discloses memory content for Figure 03",
    (
        "Figure AI said each Figure 03 humanoid uses 256GB of Samsung LPDDR6 "
        "and 4TB of onboard storage."
    ),
    "Samsung Electronics",
)
g, s, c, k = classify(phys_mem_content)
assert g == "physical_ai_memory", (g, s, c)
assert c.endswith("로봇 1대당 탑재량 공개"), c
assert s >= 11, s

phys_mem_rumor = make(
    "Samsung may win humanoid memory supply",
    "An unnamed blog says Samsung could supply LPDDR6 memory to a future humanoid robot.",
    "Unknown Blog",
)
g, s, c, k = classify(phys_mem_rumor)
assert s < 11, ("unverified physical-AI memory rumor must stay silent", g, s, c)

# 42) Morgan Stanley Humanoid 100 / long-run research benchmark lane.
# The 2025 1bn-unit / $5tn market, $40tn labor-pool TAM, ~$200k NPV and
# Brain/Body/Integrator mapping are established baselines. Reposts stay silent.
ms_humanoid_baseline_repost = make(
    "Morgan Stanley: Humanoid 100 and autonomous industrial revolution",
    (
        "Morgan Stanley says nearly 1 billion humanoids could be in use by 2050 and the humanoid "
        "market could reach $5 trillion. The global labor market TAM is about $40 trillion based on "
        "nearly 4 billion workers at about $10,000 annual wages. A humanoid leased at $5/hour replacing "
        "two $25/hour workers supports about $200,000 NPV. The Humanoid 100 maps Brain, Body and Integrators."
    ),
    "X repost",
)
g, s, c, k = classify(ms_humanoid_baseline_repost)
assert g == "ms_humanoid_research", (g, s, c)
assert c.endswith("2025 장기전망·Humanoid 100 기준선"), c
assert s < 11, ("known Morgan Stanley long-run thesis must stay silent", s, c)

ms_h100_involvement_baseline = make(
    "Morgan Stanley Humanoid 100 involvement split",
    (
        "Morgan Stanley Research says 52% of Humanoid 100 companies are currently involved in humanoids, "
        "while 48% are competitors or companies with material potential to become involved."
    ),
    "Morgan Stanley Research",
)
g, s, c, k = classify(ms_h100_involvement_baseline)
assert g == "ms_humanoid_research", (g, s, c)
assert c.endswith("2025 장기전망·Humanoid 100 기준선"), c
assert s < 11, ("52/48 Humanoid 100 involvement split is baseline", s, c)

ms_unverified_revision = make(
    "Morgan Stanley reportedly raises humanoid 2050 forecast",
    "A social post says Morgan Stanley updated its 2050 humanoid forecast from 1 billion to 1.2 billion units.",
    "X repost",
)
g, s, c, k = classify(ms_unverified_revision)
assert g == "ms_humanoid_research", (g, s, c)
assert c.endswith("2050 보급·시장·경제성 전망 수정"), c
assert s < 11, ("secondary-only Morgan Stanley revision must not alert", s, c)

ms_official_revision = make(
    "Morgan Stanley updates humanoid 2050 outlook",
    "Morgan Stanley Research revised its 2050 humanoid installed-base forecast from 1 billion to 1.2 billion units.",
    "Morgan Stanley Research",
)
g, s, c, k = classify(ms_official_revision)
assert g == "ms_humanoid_research", (g, s, c)
assert c.endswith("2050 보급·시장·경제성 전망 수정"), c
assert s >= 11, s

ms_h100_revision = make(
    "Morgan Stanley updates Humanoid 100 list",
    "Morgan Stanley Research released an updated Humanoid 100 list and added Samsung Electro-Mechanics to Body components.",
    "Morgan Stanley Research",
)
g, s, c, k = classify(ms_h100_revision)
assert g == "ms_humanoid_research", (g, s, c)
assert c.endswith("Humanoid 100 구성·역할 개정"), c
assert s >= 11, s

# 43) Panasonic humanoid commercialization lane.
# The Sep-30 Nikkei interview / 2029 manufacturing target is a known baseline.
# Panasonic Industry component capability and Panasonic Energy battery relevance
# are not evidence of an already-integrated proprietary humanoid platform.
panasonic_2029_baseline = make(
    "Panasonic develops humanoid, aims to manufacture by 2029",
    (
        "Panasonic Holdings Group CAIO Akira Sakakibara said Panasonic has begun humanoid R&D "
        "and aims to manufacture by 2029, initially for factory production lines and warehouses. "
        "He said there is not yet a concrete result that can be disclosed."
    ),
    "Nikkei",
)
g, s, c, k = classify(panasonic_2029_baseline)
assert g == "panasonic_humanoid", (g, s, c)
assert c.endswith("2029 제조목표 진입 기준선"), c
assert s < 11, ("Panasonic 2029 entry target is now baseline", s, c)

panasonic_rd_org_baseline = make(
    "Panasonic establishes AI & Robotics Research Laboratory",
    (
        "Panasonic Holdings established the AI & Robotics Research Laboratory led by Group CAIO "
        "Akira Sakakibara to accelerate Physical AI and robotics R&D."
    ),
    "Panasonic Holdings",
)
g, s, c, k = classify(panasonic_rd_org_baseline)
assert g == "panasonic_humanoid", (g, s, c)
assert c.endswith("AI·로보틱스 연구조직 기준선"), c
assert s < 11, ("Panasonic AI/robotics R&D organization is baseline", s, c)

panasonic_component_baseline = make(
    "Panasonic Industry Humanoid Robotics Solution",
    (
        "Panasonic Industry presents humanoid robotics technologies including a mechatronics-integrated "
        "servo motor, EDLC, capacitors and pressure sensors for humanoid systems."
    ),
    "Panasonic Industry",
)
g, s, c, k = classify(panasonic_component_baseline)
assert g == "panasonic_humanoid", (g, s, c)
assert c.endswith("기존 부품·배터리 역량 기준선"), c
assert s < 11, ("component portfolio is not integrated Panasonic humanoid proof", s, c)

panasonic_proto = make(
    "Panasonic unveils working humanoid prototype",
    (
        "Panasonic Holdings unveiled and demonstrated a working humanoid prototype for factory "
        "and warehouse tasks."
    ),
    "Panasonic Holdings",
)
g, s, c, k = classify(panasonic_proto)
assert g == "panasonic_humanoid", (g, s, c)
assert c.endswith("실물 시제품·모델 공개"), c
assert s >= 11, s

panasonic_internal_pilot = make(
    "Panasonic humanoid enters factory pilot",
    (
        "Panasonic deployed 50 humanoid robots at its Osaka factory production line for a field pilot "
        "and started operations in material handling."
    ),
    "Panasonic Holdings",
)
g, s, c, k = classify(panasonic_internal_pilot)
assert g == "panasonic_humanoid", (g, s, c)
assert c.endswith("자사 공장·창고 현장실증"), c
assert s >= 11, s

panasonic_battery_integration = make(
    "Panasonic integrates own battery into humanoid prototype",
    (
        "Panasonic's own humanoid integrates a Panasonic Energy 2.4kWh battery pack with 300Wh/kg "
        "energy density and 6 hours operating time."
    ),
    "Panasonic Energy",
)
g, s, c, k = classify(panasonic_battery_integration)
assert g == "panasonic_humanoid", (g, s, c)
assert c.endswith("자체 배터리 통합"), c
assert s >= 11, s

panasonic_actuator_integration = make(
    "Panasonic integrates in-house servo actuator into humanoid",
    (
        "Panasonic's own humanoid adopted a Panasonic Industry servo motor actuator rated at 180Nm "
        "for major joints."
    ),
    "Panasonic Industry",
)
g, s, c, k = classify(panasonic_actuator_integration)
assert g == "panasonic_humanoid", (g, s, c)
assert c.endswith("자체 액추에이터 통합"), c
assert s >= 11, s

panasonic_external_order = make(
    "Panasonic signs humanoid supply contract with external logistics customer",
    (
        "Panasonic signed a binding supply contract with an external logistics customer for "
        "1,000 humanoid robots with deliveries starting in 2029."
    ),
    "Panasonic Holdings",
)
g, s, c, k = classify(panasonic_external_order)
assert g == "panasonic_humanoid", (g, s, c)
assert c.endswith("외부 고객 본계약·수주"), c
assert s >= 11, s

panasonic_unverified_integrated_platform = make(
    "Panasonic launches high-torque actuator and dedicated battery integrated humanoid platform",
    (
        "An unnamed social post says Panasonic officially launched an integrated humanoid platform "
        "with a high-torque actuator and dedicated battery for commercialization in 2029."
    ),
    "Unknown Blog",
)
g, s, c, k = classify(panasonic_unverified_integrated_platform)
assert s < 11, ("unverified integrated-platform claim must stay silent", g, s, c)

# 42) NVIDIA/Foxconn GB300 live-factory robot KPI lane.
# These are task success rates, not overall GB300 manufacturing yield.
foxconn_gb300_kpi = make(
    "NVIDIA robots clear 95% assembly success on GB300 NVL72",
    (
        "NVIDIA and Foxconn reported live production results at the Houston factory for GB300 NVL72 tester-tray assembly. "
        "Robots exceeded 95% success on busbar assembly and reached 90-95% on multi-connector insertion. "
        "The busbar cycle time is about 160 seconds versus a 124-second target, and both tasks target 99.5% success."
    ),
    "Tech Times",
)
g, s, c, k = classify(foxconn_gb300_kpi)
assert g == "nvidia_robotics_exec", (g, s, c)
assert c.endswith("NVIDIA·Foxconn GB300 조립 KPI 첫 정량화"), c
assert s >= 11, s

assert "휴스턴" not in watcher.base.meaning(c) or "단정하지" in watcher.base.meaning(c), (
    "GB300 KPI meaning must not present Houston as confirmed measurement location",
    watcher.base.meaning(c),
)

foxconn_gb300_target_wording = make(
    "NVIDIA Foxconn GB300 live production robot assembly",
    (
        "NVIDIA and Foxconn reported live-production GB300 NVL72 tester-tray robot assembly results in Houston. "
        "Busbar assembly task success exceeded 95%, multi-connector insertion reached 90-95%. "
        "The busbar target is under 124 seconds and both tasks target 99.5% success; "
        "current busbar cycle time is about 160 seconds."
    ),
    "Focus Taiwan",
)
gt, st, ct, kt = classify(foxconn_gb300_target_wording)
assert gt == "nvidia_robotics_exec", (gt, st, ct)
assert ct.endswith("NVIDIA·Foxconn GB300 조립 KPI 첫 정량화"), (
    "target wording must not be misread as target achieved",
    ct,
)
assert st >= 11, st

foxconn_gb300_kpi_rewrite = make(
    "Nvidia, Hon Hai use robots to improve GB300 assembly success rates",
    (
        "NVIDIA and Hon Hai said robots assembling the GB300 NVL72 tester tray achieved more than 95% success "
        "for busbar assembly and 90 to 95 percent for connector insertion, with a 124-second busbar target "
        "and 99.5% target success."
    ),
    "Focus Taiwan",
)
g2, s2, c2, k2 = classify(foxconn_gb300_kpi_rewrite)
assert g2 == "nvidia_robotics_exec", (g2, s2, c2)
assert c2.endswith("NVIDIA·Foxconn GB300 조립 KPI 첫 정량화"), c2
assert s2 >= 11, s2
assert k2 == k, ("same GB300 factory KPI must dedupe across publishers", k, k2)

foxconn_gb300_unverified = make(
    "NVIDIA Foxconn GB300 robot yield rumor",
    (
        "An unnamed blog claims NVIDIA and Foxconn GB300 NVL72 robot assembly reached 97% success "
        "and a 140 second cycle time at a factory."
    ),
    "Unknown Blog",
)
g3, s3, c3, k3 = classify(foxconn_gb300_unverified)
assert g3 == "nvidia_robotics_exec", (g3, s3, c3)
assert s3 < 11, ("unverified factory KPI rumor must stay silent", s3, c3)

foxconn_gb300_target_hit = make(
    "NVIDIA Foxconn GB300 robots reach manufacturing targets",
    (
        "NVIDIA and Foxconn confirmed that GB300 NVL72 tester-tray robots achieved 99.5% task success "
        "and reduced busbar cycle time to 124 seconds or less in Houston production."
    ),
    "NVIDIA",
)
g4, s4, c4, k4 = classify(foxconn_gb300_target_hit)
assert g4 == "nvidia_robotics_exec", (g4, s4, c4)
assert c4.endswith("폭스콘 GB300 로봇 조립 99.5%·사이클타임 목표 달성"), c4
assert s4 >= 11, s4
assert k4 != k, "future target achievement must be a new event, not deduped to the initial KPI"

# 43) NVIDIA Korea / Madison Huang physical-AI schedule lane.
ai_day = make(
    "NVIDIA AI Day Seoul 2026 physical AI",
    "NVIDIA AI Day Seoul runs November 9-10 in Seoul with physical AI and robotics sessions.",
    "NVIDIA",
)
g, s, c, k = classify(ai_day)
assert g == "nvidia_robotics_exec", (g, s, c)
assert c.endswith("AI Day Seoul 피지컬AI 행사 기준선"), c
assert s < 11, s

madison_discussion = make(
    "Madison Huang Korea visit under discussion",
    "Industry sources say NVIDIA is discussing Madison Huang attending NVIDIA AI Day Seoul on November 9-10 for physical AI and robotics.",
    "MoneyToday",
)
g, s, c, k = classify(madison_discussion)
assert g == "nvidia_robotics_exec", (g, s, c)
assert c.endswith("매디슨 황 AI Day Seoul 참석 시간표"), c
assert s < 11, s

madison_report = make(
    "Madison Huang November Korea visit confirmed",
    "Industry sources say Madison Huang will attend NVIDIA AI Day Seoul on November 9-10 for physical AI and robotics, with attendance now confirmed.",
    "MoneyToday",
)
g, s, c, k_report = classify(madison_report)
assert g == "nvidia_robotics_exec", (g, s, c)
assert c.endswith("매디슨 황 AI Day Seoul 참석 시간표"), c
assert s >= 11, s

madison_official = make(
    "NVIDIA confirms Madison Huang at AI Day Seoul",
    "NVIDIA confirmed Madison Huang will attend NVIDIA AI Day Seoul 2026 in Seoul on November 9-10 for physical AI and robotics.",
    "NVIDIA",
)
g, s, c, k_official = classify(madison_official)
assert g == "nvidia_robotics_exec", (g, s, c)
assert c.endswith("매디슨 황 AI Day Seoul 참석 시간표"), c
assert s >= 11, s
assert k_official != k_report, "NVIDIA first-party confirmation must upgrade beyond trusted-media confirmation"

madison_mou = make(
    "NVIDIA and LG Electronics sign physical AI MOU",
    "Madison Huang and LG Electronics signed an MOU for NVIDIA Isaac and GR00T physical AI robotics in Seoul.",
    "NVIDIA",
)
g, s, c, k = classify(madison_mou)
assert g == "nvidia_robotics_exec", (g, s, c)
assert c.endswith("NVIDIA·한국기업 피지컬AI 협력계약·업무협약"), c
assert s >= 11, s

# 44) Rendering guard: newly added categories must resolve meaning/risk without
# evaluating legacy dictionary fallbacks that can raise KeyError.
render_cat = "NVIDIA 로보틱스 · 폭스콘 GB300 로봇 조립 99.5%·사이클타임 목표 달성"
assert "작업 성공률" in watcher.base.meaning(render_cat), watcher.base.meaning(render_cat)
assert watcher.base.risk(render_cat), "GB300 risk rendering must not fail"
render_korea_cat = "NVIDIA 로보틱스 · NVIDIA·한국기업 피지컬AI 협력계약·업무협약"
assert "협약" in watcher.base.meaning(render_korea_cat), watcher.base.meaning(render_korea_cat)
assert watcher.base.risk(render_korea_cat), "NVIDIA Korea risk rendering must not fail"

# 45) User-facing criteria must remain compact even if an upstream wrapper
# accidentally expands the internal rule list.
_original_alert_path = base.ALERT_PATH
try:
    with tempfile.TemporaryDirectory() as td:
        base.ALERT_PATH = Path(td) / "criteria.txt"
        base.ALERT_PATH.write_text(
            "본문 한 줄\n<b>판정 기준</b>\n" + ("긴 내부 규칙·" * 120),
            encoding="utf-8",
        )
        watcher._finalize_airan_criteria()
        rendered = base.ALERT_PATH.read_text(encoding="utf-8")
        criteria = rendered.split("<b>판정 기준</b>", 1)[1].strip()
        assert criteria == "실적·수급·시간표를 바꾸는 새 사실만 알림. 단순 주가·ETF·테마 반복은 제외.", criteria
        assert len(criteria) < 60, criteria
finally:
    base.ALERT_PATH = _original_alert_path

# 46) Dongkuk nickel-plated steel is a battery-can material milestone, not
# evidence that Tesla Optimus or Boston Dynamics Atlas use its specific cells.
# The 09/14 company qualification, 10/08 analyst-reported first shipments and a
# future official shipment are three separate evidence / commercial stages.
dongkuk_qual = make(
    "동국산업 북미 46시리즈 니켈도금강판 품질인증 완료",
    "동국산업은 2026년 9월 14일 북미 고객 46시리즈 니켈도금강판 품질 인증을 완료했고 "
    "4분기부터 양산 공급할 예정이라고 밝혔다. Tesla Optimus Atlas 로봇 원통형 수요도 거론된다.",
    "뉴스씬",
)
g, sc, cat, k_qual = classify(dongkuk_qual)
assert g == 'dongkuk_nps', (g, sc, cat)
assert sc < 11, (sc, cat)

dongkuk_reported = make(
    "테슬라·보스턴다이내믹스도 휴머노이드 원통형 택했다…동국산업 북미 테스트 완료",
    "동국산업의 46시리즈 니켈도금강판은 9월 북미 고객 품질 인증이 완료됐으며 "
    "증권가 기업 탐방 내용에 따르면 10월부터 초도 납품을 시작한 것으로 전해졌다. "
    "애널리스트는 올해 2,000톤에서 2027년 20,000톤으로 늘어날 것으로 예상. "
    "테슬라 Optimus·보스턴다이내믹스 Atlas 원통형 배터리 언급은 산업 잠재 수요다.",
    "뉴스씬",
)
g, sc, cat, k_report = classify(dongkuk_reported)
assert g == 'dongkuk_nps', (g, sc, cat)
assert sc >= 11 and cat.endswith('10월 초도 납품 보도'), (sc, cat)
assert k_report != k_qual, "analyst shipment claim must be an upgrade from September qualification"
assert "직접 공급 미확인" in watcher.clean_title(dongkuk_reported["title"], "뉴스씬")
assert "직접 공급 증거가 아닙니다" in base.risk(cat), base.risk(cat)
assert "애널리스트 전망" in base.meaning(cat), base.meaning(cat)

dongkuk_rewrite = make(
    "동국산업 북미 46 시리즈 원통형 배터리 첫 공급 주목",
    "니켈도금강판에 대해 증권가에서는 10월부터 초도 납품을 시작한 것으로 전해졌다. "
    "고객사는 공개되지 않았고 테슬라 Optimus·Atlas 공급은 확인되지 않았다.",
    "아이티인사이트",
)
g2, sc2, cat2, k_rewrite = classify(dongkuk_rewrite)
assert g2 == 'dongkuk_nps' and sc2 >= 11, (g2, sc2, cat2)
assert k_rewrite == k_report, "syndication must not generate a duplicate alert"

dongkuk_official_ship = make(
    "동국산업 46시리즈 니켈도금강판 초도 공급 공식 발표",
    "동국산업은 북미 고객에 대한 46시리즈 니켈도금강판 10월 초도 납품을 시작했다고 발표했다.",
    "동국산업",
)
g, sc, cat, k_official = classify(dongkuk_official_ship)
assert g == 'dongkuk_nps' and sc >= 11, (g, sc, cat)
assert cat.endswith('첫 출하 공식 확인'), cat
assert k_official != k_report, "future company confirmation must trigger a distinct upgrade"

dongkuk_theme = make(
    "테슬라·보스턴다이내믹스 로봇 배터리 테마 동국산업 관심",
    "동국산업 니켈도금강판은 46시리즈 원통형 배터리 케이스 소재이며 "
    "Optimus Atlas 로봇이 원통형 배터리를 쓴다는 보도에 관련주로 주목된다.",
    "경제뉴스",
)
g, sc, cat, k_theme = classify(dongkuk_theme)
assert g == 'dongkuk_nps' and sc < 11, (g, sc, cat)
assert k_theme != k_report, "robot theme alone must not become shipment evidence"

dongkuk_forecast = make(
    "동국산업 니켈도금강판 46시리즈 공급량 전망",
    "동국산업 46시리즈 니켈도금강판은 2026년 2,000톤과 2027년 2만톤 판매가 예상된다. "
    "이는 애널리스트 전망이며 공식 출하는 발표되지 않았다.",
    "증권가",
)
g, sc, cat, k_forecast = classify(dongkuk_forecast)
assert g == 'dongkuk_nps' and sc < 11, (g, sc, cat)
assert k_forecast != k_report

# Recovery must keep exact source category and 2026-10-08 publication timestamp
# while remaining within the original workflow/script/state/Telegram route.
recovered_dongkuk = watcher.query_news(watcher.DONGKUK_NPS_RECOVERY)
assert len(recovered_dongkuk) == 1, recovered_dongkuk
assert recovered_dongkuk[0]['source'] == '뉴스씬', recovered_dongkuk
assert recovered_dongkuk[0]['published'] == '2026-10-08T00:35:00+00:00'
rg, rs, rc, rk = classify(recovered_dongkuk[0])
assert rg == 'dongkuk_nps' and rs >= 11 and rk == k_report, (rg, rs, rc)


# 46) DKT alert: separate the 2026-07 BMS discussions, the 2026-08
# company production *plan*, the 2026-09 broker-observed robot battery
# module ramp, actual ESS BMS shipment, and a future company confirmation.
dkt_july = make(
    "디케이티, ESS용 BMS 기술력으로 휴머노이드 배터리 시장 정조준",
    "디케이티가 휴머노이드에 탑재할 배터리팩과 BMS 개발 협력을 논의하고 있다.",
    "전자신문",
)
dg, ds, dc, dk = classify(dkt_july)
assert dg == 'dkt_humanoid' and ds < 11, (dg, ds, dc)

dkt_plan = make(
    "디케이티, 휴머노이드 소형 배터리팩 모듈 9월 양산 계획",
    "디케이티는 북미 휴머노이드 기업향 소형 배터리팩 모듈을 9월부터 양산할 예정이다.",
    "디케이티",
)
pg, ps, pc, pk = classify(dkt_plan)
assert pg == 'dkt_humanoid' and ps < 11, (pg, ps, pc)

dkt_report = make(
    "디케이티 휴머노이드 배터리 모듈 양산공급 시작",
    "디케이티 북미 전기차 고객사의 휴머노이드 이머전시 디바이스 배터리 모듈은 "
    "주당 1,500~2,000대 초기 공급으로 검증을 마쳤고 8월 말 승인과 함께 "
    "양산 공급이 시작된 것으로 파악된다.",
    "하나증권",
)
rg, rs, rc, rk = classify(dkt_report)
assert rg == 'dkt_humanoid' and rs >= 11, (rg, rs, rc)
assert rc.endswith('양산 공급 증권사 확인'), rc
assert '익명 고객' in base.risk(rc), base.risk(rc)
assert '현재 정규 출하량 확정치가 아닙니다' in base.meaning(rc), base.meaning(rc)
assert '회사 직접 출하' in base.verification(dkt_report, rg,
       dkt_report['title'] + ' ' + dkt_report['description']), 'source tier lost'

dkt_copy = make(
    "디케이티 북미 휴머노이드 배터리 모듈 공급 단계",
    "디케이티 휴머노이드용 배터리 모듈 8월 말 승인과 함께 양산 공급 시작, "
    "주당 2,000대 초기 검증 이력, 회사 직접 양산 발표는 없다.",
    "프라임경제",
)
cg, cs, cc, ck = classify(dkt_copy)
assert cg == 'dkt_humanoid' and cs >= 11 and ck == rk, (cg, cs, cc, ck)

dkt_official = make(
    "디케이티 휴머노이드 배터리 모듈 양산 공식 발표",
    "디케이티는 휴머노이드용 배터리 모듈의 8월 말 승인에 따라 "
    "양산 공급을 시작했다고 직접 발표했다.",
    "디케이티",
)
og, os, oc, ok = classify(dkt_official)
assert og == 'dkt_humanoid' and os >= 11, (og, os, oc)
assert oc.endswith('양산 회사 공식 확인'), oc
assert ok != rk, "company confirmation must alert after broker-reported production"

dkt_ess_shipment = make(
    "디케이티 북미 LFP ESS용 BMS 첫 출하",
    "디케이티는 8월 19일 북미 ESS용 LFP 배터리관리시스템을 첫 출하했다.",
    "전자신문",
)
eg, es, ec, ek = classify(dkt_ess_shipment)
assert eg != 'dkt_humanoid', (eg, es, ec)

dkt_tesla_theme = make(
    "테슬라 휴머노이드 로봇 관련주 디케이티 주가 급등",
    "디케이티는 휴머노이드 BMS 관련 기대와 테슬라 테마로 강세다.",
    "종목뉴스",
)
tg, ts, tc, tk = classify(dkt_tesla_theme)
assert tg == 'dkt_humanoid' and ts < 11, (tg, ts, tc)

dkt_real_bms_contract = make(
    "디케이티 휴머노이드 BMS 정식 공급계약",
    "디케이티는 휴머노이드용 BMS 정식 공급계약을 체결했다고 발표했다.",
    "디케이티",
)
bg, bs, bc, bk = classify(dkt_real_bms_contract)
assert bg == 'dkt_humanoid' and bs >= 11 and bk not in {rk, ok}, (bg, bs, bc)

retrieved_dkt = watcher.query_news(watcher.DKT_HUMANOID_RECOVERY)
if base.NOW.astimezone(base.KST).date() <= dt.date(2026, 10, 15):
    assert len(retrieved_dkt) == 1 and retrieved_dkt[0]['source'] == '하나증권', retrieved_dkt
    assert retrieved_dkt[0].get('published') is None, 'never invent an intraday report timestamp'
    rgg, rss, rcc, rkk = classify(retrieved_dkt[0])
    assert rgg == 'dkt_humanoid' and rss >= 11 and rkk == rk, (rgg, rss, rcc, rkk)
else:
    assert retrieved_dkt == [], 'expired backfill must not replay or fail regression'
assert watcher.qty._skip_quantity_enrichment(
    "디케이티 휴머노이드 배터리\n주당 1,500~2,000대 초기 공급 규모\n"
), 'do not render unverified priced robot shipments for DKT'


# 47) The actual Telegram renderer calls category(title + description)
# without source and clean_title(title, source) without description.
# This exact interface mismatch previously sent message_id=197 with a
# "prior discussion" label despite the high-signal production report.
dkt_rendered_prose = f"{dkt_report['title']} {dkt_report['description']}"
dkt_rendered_category = base.category(dkt_rendered_prose, base.topic_group(dkt_rendered_prose))
assert dkt_rendered_category.endswith('양산 공급 증권사 확인'), dkt_rendered_category
assert '8월 말 양산 공급 시작' in base.meaning(dkt_rendered_category), base.meaning(dkt_rendered_category)
assert '기존 기준선' not in base.meaning(dkt_rendered_category), base.meaning(dkt_rendered_category)

dkt_official_prose = f"{dkt_official['title']} {dkt_official['description']}"
assert base.category(dkt_official_prose, base.topic_group(dkt_official_prose)).endswith(
    '양산 회사 공식 확인'
), 'first-party confirmation must not be downgraded to a report'

dkt_contract_prose = f"{dkt_real_bms_contract['title']} {dkt_real_bms_contract['description']}"
assert base.category(dkt_contract_prose, base.topic_group(dkt_contract_prose)).endswith(
    '휴머노이드용 BMS 정식 계약'
), 'BMS contract must not become an ESS shipment or battery-module report'

if retrieved_dkt:
    recovered_dkt_rendered_prose = (
        f"{retrieved_dkt[0]['title']} {retrieved_dkt[0]['description']}"
    )
    recovered_dkt_rendered_category = base.category(
        recovered_dkt_rendered_prose, base.topic_group(recovered_dkt_rendered_prose)
    )
    assert recovered_dkt_rendered_category.endswith('양산 공급 증권사 확인'), (
        recovered_dkt_rendered_category
    )
    corrected_title = base.clean_title(
        retrieved_dkt[0]['title'], retrieved_dkt[0]['source']
    )
    assert corrected_title.startswith('정정: 디케이티'), corrected_title

# The backfill expires; future genuine company announcements remain eligible,
# but an old 9/9 report cannot be replayed after state-file rotation.
old_now = base.NOW
try:
    base.NOW = dt.datetime(2026, 10, 16, 12, 0, tzinfo=dt.timezone.utc)
    assert watcher.query_news(watcher.DKT_HUMANOID_RECOVERY) == []
finally:
    base.NOW = old_now


# 48) Tesla patent US20260310299A1: application PUBLICATION, not grant,
# SOP, Optimus installed unit, vendor contract, or any unit-volume sales.
tesla_patent_report = make(
    "Tesla publishes US 2026/0310299 A1 3D tactile sensor patent application",
    "Tesla 3D tactile array sensor patent US20260310299A1 publication on Oct 8, 2026. "
    "The regular application was filed September 11 2025 and the provisional "
    "on April 4 2025. Screen printing and thermoforming plus direct curved-surface "
    "deposition are scalable manufacturing methods, not production evidence.",
    "Robotics News",
)
pg, ps, pc, pk = classify(tesla_patent_report)
assert pg == 'tesla_touch_patent' and ps >= 11, (pg, ps, pc)
assert pc == '테슬라 촉각센서 · 미국 특허출원 공개 A1', pc
assert 'B2' in base.risk(pc) and '특허등록' in base.risk(pc), base.risk(pc)
assert '2025-09-11' in base.meaning(pc), base.meaning(pc)
assert any(t in base.risk(pc) for t in ('양품률', '수율')), base.risk(pc)

tesla_patent_rewrite = make(
    "테슬라 US20260310299A1 촉각 로봇 피부 제조기술 공개",
    "Tesla 미국 특허 US20260310299A1 공개: flexible tactile array sensor "
    "curved fingers, TPU, screen printing and thermoforming.",
    "Patent Technology Media",
)
pg2, ps2, pc2, pk2 = classify(tesla_patent_rewrite)
assert pg2 == 'tesla_touch_patent' and ps2 >= 11, (pg2, ps2, pc2)
assert pk2 == pk, 'different media describing one publication must share one state key'

tesla_old_filing = make(
    "Tesla tactile patent filing",
    "Tesla US20260310299A1 sensor application was filed September 11 2025.",
    "Patent Blog",
)
fg, fs, fc, fk = classify(tesla_old_filing)
assert fg == 'tesla_touch_patent' and fs < 11, (fg, fs, fc)

tesla_patent_media_grant_rumor = make(
    "Tesla US20260310299A1 tactile patent granted",
    "Tesla patent US20260310299A1 3D tactile sensor has been granted.",
    "Unknown News",
)
mg, ms, mc, mk = classify(tesla_patent_media_grant_rumor)
assert mg == 'tesla_touch_patent' and ms < 11, (mg, ms, mc)

tesla_patent_official_grant = make(
    "USPTO: Tesla US20260310299A1 tactile patent granted",
    "USPTO official record reports the Tesla patent US20260310299A1 tactile "
    "sensor patent granted. Actual grant number and claims must be checked.",
    "USPTO",
)
gg, gs, gc, gk = classify(tesla_patent_official_grant)
assert gg == 'tesla_touch_patent' and gs >= 11, (gg, gs, gc)
assert gc == '테슬라 촉각센서 · 특허 등록 공식확인 단계', gc
assert gk != pk, 'future official grant must be distinct from A1 publication'
assert '등록 상태' in base.meaning(gc), base.meaning(gc)

tesla_not_granted = make(
    "Tesla US20260310299A1 tactile patent publication, not yet granted",
    "Tesla tactile sensor US 2026/0310299 A1 was published October 8, 2026. "
    "It is not yet granted and is not an installed Optimus production part.",
    "Robotics News",
)
ng, ns, nc, nk = classify(tesla_not_granted)
assert ng == 'tesla_touch_patent' and ns >= 11 and nk == pk, (ng, ns, nc, nk)

tesla_other_patent = make(
    "Tesla patent unrelated to tactile sensing",
    "Tesla patent US20260123456A1 for unrelated vehicle body parts was published.",
    "Tesla News",
)
og, os, oc, ok = classify(tesla_other_patent)
assert og != 'tesla_touch_patent', (og, os, oc)

patent_backfill = watcher.query_news(watcher.TESLA_TOUCH_PATENT_RECOVERY)
if base.NOW.astimezone(base.KST).date() <= dt.date(2026, 10, 12):
    assert len(patent_backfill) == 1, patent_backfill
    p = patent_backfill[0]
    assert p.get('published') is None, 'no invented intraday publication time'
    assert p['source'] == '사용자제공 특허표지·기사 전문', p
    bg, bs, bc, bk = classify(p)
    assert bg == 'tesla_touch_patent' and bs >= 11 and bk == pk, (bg, bs, bc, bk)
    # Renderer specifically loses the source in category(title + description);
    # verify EXACT production rendering contract to avoid the previous DKT bug.
    rendered_text = f"{p['title']} {p['description']}"
    rendered_group = base.topic_group(rendered_text)
    rendered_category = base.category(rendered_text, rendered_group)
    assert rendered_group == 'tesla_touch_patent', rendered_group
    assert rendered_category == pc, rendered_category
    assert '특허출원 공개' in base.clean_title(p['title'], p['source'])
    detail = base.verification(p, rendered_group, rendered_text)
    assert '기사 전문 확인' in detail, detail
    assert '기사 웹페이지·USPTO 문서 전체 직접 열람 미완료' in detail, detail
    assert '기사 본문 직접 열람 실패' not in detail, detail
    brief = base.meaning(rendered_category)
    for needle in ['20개', 'Optimus가 직접 등장하지', '감지점', '정전용량식·저항식', '내구성']:
        assert needle in brief, (needle, brief)
    assert '특허 본문에 Optimus 제품명이 직접 기재되지' in p['description']
    assert '청구항은 20개' in p['description']
    assert '전단력·미끄러짐·온도를 별개로 감지한다고 입증하지 않는다' in p['description']
    assert watcher.qty._skip_quantity_enrichment(
        f'<b>1. 테슬라 촉각센서 특허</b>\n<b>분류</b>  {rendered_category}\n'
        '<b>핵심</b>  US 2026/0310299 A1·2개 유연층·3차원 센서'
    ), 'A1 identifier/layer counts are not real unit sales'

old_patent_now = base.NOW
try:
    base.NOW = dt.datetime(2026, 10, 13, tzinfo=dt.timezone.utc)
    assert watcher.query_news(watcher.TESLA_TOUCH_PATENT_RECOVERY) == [], (
        'historical publication cannot replay as news after backfill expiry'
    )
finally:
    base.NOW = old_patent_now



# 49) Digital Optimus gaming lane (2026-10-10 Musk X).
# Product classification, reporter quality and replay gates must be separated.
digital_progress = make(
    "Elon Musk: Digital Optimus can play Diablo halfway and Counter-Strike",
    "Elon Musk X post 2108823477071303109 on Oct 10 2026 says Digital Optimus "
    "can play about halfway through the Diablo campaign looking at the screen. "
    "Counter-Strike skill is good, League of Legends is training, and the aim "
    "is generalization across games. No independent benchmark was published.",
    "Elon Musk (X)",
)
dg, ds, dc, dk = classify(digital_progress)
assert dg == "digital_optimus_games" and ds >= 11, (dg, ds, dc)
assert dc == "Digital Optimus · 게임 수행 경영진 진전 발언", dc
assert "머스크 X" in base.meaning(dc) and "주장" in base.meaning(dc), base.meaning(dc)
assert "독립" in base.risk(dc), base.risk(dc)
assert "50%" not in base.meaning(dc), "campaign halfway must not mean 50% win rate"
assert "물리" in base.risk(dc), base.risk(dc)

digital_rewrite = make(
    "Digital Optimus Diablo game progress",
    "Musk X 2108823477071303109: Digital Optimus is playing the "
    "Diablo campaign halfway and learning League of Legends.",
    "Elon Musk (X)",
)
dg2, ds2, dc2, dk2 = classify(digital_rewrite)
assert dg2 == dg and ds2 >= 11 and dk2 == dk, (dg2, ds2, dk2)

digital_unverified = make(
    "Digital Optimus achieves game-changing Diablo performance",
    "Digital Optimus plays halfway into Diablo; Counter-Strike success proves "
    "general AI according to anonymous sources.",
    "Finance Influencer Blog",
)
ug, us, uc, uk = classify(digital_unverified)
assert ug == "digital_optimus_games" and us < 11, (ug, us, uc)

digital_job_only = make(
    "Tesla hiring real-time Games Digital Optimus AI researcher",
    "Tesla job posting for Digital Optimus in games focused on training agents, "
    "memory, and a general computer-use future.",
    "Tesla",
)
jg, js, jc, jk = classify(digital_job_only)
assert jg == "digital_optimus_games" and js < 11, (jg, js, jc)

digital_official_benchmark = make(
    "Tesla Digital Optimus games benchmark",
    "Tesla officially publishes Digital Optimus benchmark of 75% success "
    "across 100 episodes in new unseen games, with response latency.",
    "Tesla",
)
bg, bs, bc, bk = classify(digital_official_benchmark)
assert bg == "digital_optimus_games" and bs >= 11, (bg, bs, bc)
assert bc == "Digital Optimus · 회사 공식 다중게임 성능 검증", bc
assert bk != dk, "future official test must be distinct from CEO X claim"

digital_commercial = make(
    "Tesla Digital Optimus game agent commercial launch",
    "Tesla Digital Optimus games service commercial launch with "
    "paid customer contract and enterprise deployment.",
    "Tesla",
)
cg, cs, cc, ck = classify(digital_commercial)
assert cg == "digital_optimus_games" and cs >= 11, (cg, cs, cc)
assert cc == "Digital Optimus · 정식 상용화·유료 계약", cc
assert ck not in {dk, bk}, (ck, dk, bk)

physical_opt = make(
    "Tesla Optimus humanoid robot hand",
    "Tesla Optimus has 25 actuators and manipulates objects; "
    "its physical hand is not Digital Optimus screen control.",
    "Tesla",
)
pg, ps, pc, pk = classify(physical_opt)
assert pg != "digital_optimus_games", (pg, ps, pc)

old_digital_now = base.NOW
try:
    base.NOW = dt.datetime(2026, 10, 10, 12, 0, tzinfo=dt.timezone.utc)
    recovered_digital = watcher.query_news(watcher.DIGITAL_OPTIMUS_GAME_RECOVERY)
    assert len(recovered_digital) == 1, recovered_digital
    raw_digital = recovered_digital[0]
    assert raw_digital['source'] == 'Elon Musk (X)', raw_digital
    assert raw_digital['link'] == 'https://x.com/elonmusk/status/2108823477071303109'
    assert raw_digital['published'] == '2026-10-10T07:34:00+00:00', raw_digital
    rdg, rds, rdc, rdk = classify(raw_digital)
    assert rdg == dg and rds >= 11 and rdk == dk, (rdg, rds, rdk)
    rendered_text = f"{raw_digital['title']} {raw_digital['description']}"
    # Same source-loss interface as the real Telegram renderer:
    rendered_category = base.category(rendered_text, base.topic_group(rendered_text))
    assert rendered_category == dc, rendered_category
    assert "머스크:" in base.clean_title(raw_digital['title'], raw_digital['source'])
    review = base.verification(raw_digital, rdg, rendered_text)
    assert "X 직접 열람 제한" in review, review
    assert "독립 검증 없음" in review, review
    assert "물리" in base.risk(rendered_category), base.risk(rendered_category)
    assert base.key(raw_digital) == dk, "semantic deduplication across reprints failed"
    base.NOW = dt.datetime(2026, 10, 15, 4, 0, tzinfo=dt.timezone.utc)
    assert watcher.query_news(watcher.DIGITAL_OPTIMUS_GAME_RECOVERY) == [], (
        "old 10/10 Musk post must not replay after backfill expires"
    )
finally:
    base.NOW = old_digital_now


# Digital Optimus reports describe a software agent, not robot shipments.
assert watcher.qty._skip_quantity_enrichment(
    '<b>2. 테슬라 디지털 에이전트 Digital Optimus</b>\n'
    '<b>분류</b>  Digital Optimus · 게임 수행 경영진 진전 발언\n'
    'Diablo 캠페인 절반, League of Legends 학습 중'
), 'No fictitious physical unit count for Digital Optimus'


# 50) Counterpoint's 2026-10-10 humanoid BRAIN-DRAM outlook:
# numeric 2026 and 2030 scenarios must not be turned into sales,
# NAND capacity, physical robot shipments, or server HBM.
robot_memory_primary = make(
    "Counterpoint humanoid robot DRAM demand outlook",
    "Counterpoint Research says 2026 humanoid robot brain DRAM demand is "
    "8,300Tbit with 19GB blended DRAM per robot; in 2030 it forecasts "
    "172,000Tbit with 39GB average DRAM. LPDDR memory and NAND storage "
    "are distinct, while HBM is mainly used in AI servers.",
    "카운터포인트리서치",
)
mmg, mms, mmc, mmk = classify(robot_memory_primary)
assert mmg == 'humanoid_brain_dram' and mms >= 11, (mmg, mms, mmc)
assert mmc == '휴머노이드 두뇌 D램 · 2030년 수요 신규 전망', mmc
assert '전망' in mmc and '고객' not in mmc
body = base.meaning(mmc)
for required in ('19GB', '39GB', '8,300', '172,000', '1,037,500GB',
                 '21,500,000GB', '215억원', '실거래 단가·매출 가이던스가 아닙니다'):
    assert required in body, (required, body)
assert 'LPDDR' in body and '낸드' in body and 'HBM' in body, body
assert '25%' in base.risk(mmc) and '43,000Tbit' in base.risk(mmc)

# Alternate sources and headlines discussing SAME forecast must map to
# the same event key. No new message merely because a newspaper rewrites it.
robot_memory_reprint = make(
    "휴머노이드 브레인용 메모리 19GB서 39GB, 카운터포인트 전망",
    "2026년 휴머노이드 D램 8,300Tbit에서 2030년 172,000Tbit로 "
    "확대, 로봇당 19GB에서 39GB. 이는 블렌디드 DRAM 용량 전망이다.",
    "연합뉴스",
)
rng, rns, rnc, rnk = classify(robot_memory_reprint)
assert rng == mmg and rns >= 11 and rnk == mmk, (rng, rns, rnc, rnk)

# Macro-only or speculative HBM cross-over is not an installed order.
memory_theme = make(
    "휴머노이드 로봇 메모리 시장 20배 테마",
    "카운터포인트리서치는 로봇 DRAM이 성장할 것으로 예측하지만 이 보도는 "
    "정식 고객·로봇 탑재량 수치 없이 주가 테마만 소개한다.",
    "증시 테마 블로그",
)
tg, ts, tc, tk = classify(memory_theme)
assert tg == mmg and ts < 11, (tg, ts, tc)

memory_hbm_misread = make(
    "테슬라 휴머노이드 HBM 39GB 출하 확정이라는 루머",
    "Tesla humanoid robotics robot HBM 39GB capacity rumor "
    "without official LPDDR DRAM supply confirmation.",
    "익명 SNS",
)
hg, hs, hc, hk = classify(memory_hbm_misread)
assert hg != mmg, (hg, hs, hc)

memory_micron_longterm = make(
    "마이크론 휴머노이드 200GB 장기 기대",
    "Micron says humanoid robots may require over 200GB LPDDR "
    "memory and multiple TB of NAND storage, not a 2030 blended average.",
    "Micron",
)
mg, ms, mc, mk = classify(memory_micron_longterm)
assert mg != mmg, (mg, ms, mc)

revision_media_only = make(
    "카운터포인트 휴머노이드 메모리 수요 수정 보도",
    "Counterpoint humanoid DRAM 2030 demand forecast revised from "
    "172,000Tbit at 39GB to 180,000Tbit with 41GB per robot.",
    "익명 뉴스",
)
zg, zs, zc, zk = classify(revision_media_only)
assert zg == mmg and zs < 11, (zg, zs, zc)

revision_official = make(
    "Counterpoint revised humanoid DRAM forecast",
    "Counterpoint Research officially revised its 2030 humanoid robot "
    "brain DRAM forecast to 180,000Tbit at 41GB from the earlier "
    "172,000Tbit and 39GB. This is a future hypothetical regression case.",
    "카운터포인트리서치",
)
og, os, oc, ok = classify(revision_official)
assert og == mmg and os >= 11, (og, os, oc)
assert oc == '휴머노이드 두뇌 D램 · 조사기관 전망치 공식 수정', oc
assert ok != mmk, "true future revision must upgrade beyond current forecast"
assert '기존 전망' in base.verification(revision_official,og,
        revision_official['title']+' '+revision_official['description'])

# Validate algebra independently of market forecasts:
# 1 Tbit = 1,000,000,000,000 bits = 125 GB decimal.
assert 8300*125 == 1_037_500
assert 172000*125 == 21_500_000
assert round((172000/8300),2) == 20.72
assert round((39/19),2) == 2.05
assert round((8300*125/19)) == 54605
assert round((172000*125/39)) == 551282
assert 21_500_000*1000 == 21_500_000_000  # KRW 215eok, illustrative
assert 1_037_500*1000 == 1_037_500_000    # KRW 10eok3750man, illustrative

memory_recovered = watcher.query_news(watcher.HUMANOID_DRAM_RECOVERY)
if base.NOW.astimezone(base.KST).date() <= dt.date(2026,10,18):
    assert len(memory_recovered) == 1, memory_recovered
    mr = memory_recovered[0]
    assert mr['source'] == '카운터포인트리서치'
    assert mr['link'] == watcher.HUMANOID_DRAM_URL
    assert mr['published'] is None, 'do not invent an intraday time'
    rg, rs, rc, rk = classify(mr)
    assert rg == mmg and rs>=11 and rk==mmk, (rg,rs,rc,rk)
    render_text = mr['title']+' '+mr['description']
    assert base.category(render_text,base.topic_group(render_text)) == mmc
    assert '실출하·공급계약 아님' in base.verification(mr,rg,render_text)
    assert watcher.qty._skip_quantity_enrichment(
        '<b>1. 휴머노이드 메모리 로봇 D램</b>\n'
        '<b>분류</b>  휴머노이드 두뇌 D램 · 2030년 수요 신규 전망\n'
        '역산 출하량 55만대, 8,300Tbit, 19GB, 39GB'
    ), 'forecast robot equivalents may not be labelled confirmed shipment units'
old_counterpoint_now = base.NOW
try:
    base.NOW = dt.datetime(2026,10,19,12,0,tzinfo=dt.timezone.utc)
    assert watcher.query_news(watcher.HUMANOID_DRAM_RECOVERY) == []
finally:
    base.NOW = old_counterpoint_now



# 51) A later real humanoid low-power DRAM supply agreement is an
# upgrade only with a named robotics customer and memory VENDOR origin.
memory_vendor_order = make(
    "SK hynix NVIDIA Jetson Thor 휴머노이드 로봇 LPDDR5X 정식 공급계약 체결",
    "SK하이닉스는 NVIDIA Jetson Thor 휴머노이드 로봇 플랫폼용 "
    "LPDDR5X D램 정식 공급계약 체결을 발표했다.",
    "SK하이닉스",
)
vg, vs, vc, vk = classify(memory_vendor_order)
assert vg == 'humanoid_brain_dram' and vs >= 11, (vg,vs,vc)
assert vc == '휴머노이드 두뇌 D램 · 고객 실명 양산 공급계약 확인',vc
assert vk != mmk, "real supplier contract must be new event vs demand forecast"
vendor_text=memory_vendor_order['title']+' '+memory_vendor_order['description']
assert base.category(vendor_text,base.topic_group(vendor_text))==vc
assert '원문 확인 단계' in base.verification(memory_vendor_order,vg,vendor_text)

memory_vendor_alias = make(
    "SK hynix NVIDIA Jetson Thor humanoid robot LPDDR5X signed supply contract",
    "SK hynix signed supply contract to deliver LPDDR5X DRAM to NVIDIA "
    "Jetson Thor humanoid robot platform.",
    "SK hynix",
)
ag, a_score, ac, ak = classify(memory_vendor_alias)
assert ag == vg and a_score >= 11 and ac == vc, (ag,a_score,ac)
assert ak == vk, "Korean/English official customer and supplier aliases are one event"

memory_media_contract_claim = dict(memory_vendor_order,source='테마 뉴스')
ng, ns, nc, nk = classify(memory_media_contract_claim)
assert ng == vg and ns < 11, (ng,ns,nc)
memory_mou_only = make(
    "SK하이닉스 NVIDIA 휴머노이드 로봇 LPDDR5X 공동개발",
    "SK hynix NVIDIA Jetson Thor 로봇 D램 공동개발 협약으로 "
    "향후 공급 계약은 아직 확정되지 않았다.",
    "SK하이닉스",
)
mg, ms, mc, mk = classify(memory_mou_only)
assert mg != 'humanoid_brain_dram' or ms < 11,(mg,ms,mc)


# X Takeover: historical 2025 magnet disruption is not new 2026 delay.
hand_recovered = watcher.query_news(watcher.OPTIMUS_HAND_MAGNET_RECOVERY)
if base.NOW.astimezone(base.KST).date() <= dt.date(2026,10,16):
    assert len(hand_recovered)==1,hand_recovered
    item=hand_recovered[0]
    g, sc, cat, key = classify(item)
    assert g=='optimus_hand_magnet' and sc>=11,(g,sc,cat)
    assert cat == 'Optimus 손·자석 · 2025년 공급망 차질 경영진 회고',cat
    assert '2025년' in base.meaning(cat) and '2~3개월' in base.meaning(cat)
    assert '현재 V3 일정이 2~3개월 새로 지연' in base.meaning(cat)
    assert watcher.qty._skip_quantity_enrichment(
        'Optimus 손·자석 · 2025년 공급망 차질 경영진 회고\n2~3개월 지연'
    )
    # The base renderer discards item source while preparing the category.
    rendered=item['title']+' '+item['description']
    assert base.category(rendered,base.topic_group(rendered))==cat
hand_theme=make(
    'Optimus hand magnet China risk X Takeover',
    'Elon Musk noted general magnet shortage and fine manipulation challenges.',
    '테마 뉴스'
)
hg, hs, hc, hk=classify(hand_theme)
assert hg=='optimus_hand_magnet' and hs<11,(hg,hs,hc)
oldnow=base.NOW
try:
    base.NOW=dt.datetime(2026,10,17,0,0,tzinfo=dt.timezone.utc)
    assert watcher.query_news(watcher.OPTIMUS_HAND_MAGNET_RECOVERY)==[]
finally:
    base.NOW=oldnow


# 53) Sep 2026 BMI 314Ah price observation; no unconditional 40.9% duty
# or 50GWh company revenue inference, no rerun of two old October headlines.
bmi_price = make(
    "Benchmark LFP 314Ah September 2026 cell price review",
    "Benchmark Mineral Intelligence September 2026: Chinese 314Ah LFP EXW China "
    "$51.62/kWh, CIF North America $61.99/kWh and CIF Europe $59.18/kWh. "
    "These are assessed cell prices without US import duties.",
    "Benchmark Mineral Intelligence",
)
bg, bs, bc, bk = classify(bmi_price)
assert bg == 'lfp_314_cif_north_america' and bs >= 11,(bg,bs,bc)
assert bc == 'ESS LFP 북미 조달 · 314Ah 9월 CIF 가격·관세 가정',bc
info = base.meaning(bc)
for piece in ('51.62', '61.99', '10.37', '20.09%', '40.9%', '조건', '831.21억원', '1,171.18억원', '339.97억원'):
    assert piece in info,(piece,info)
risk_note=base.risk(bc)
assert '관세' in risk_note and '화재' in risk_note or ('열폭주' in risk_note and '보험' in risk_note), risk_note
assert '실제' in base.verification(bmi_price,bg,bmi_price['title']+" "+bmi_price['description'])
assert watcher.qty._skip_quantity_enrichment(
    '<b>1. 북미 ESS LFP 조달원가</b>\n'
    '<b>분류</b>  ESS LFP 북미 조달 · 314Ah 9월 CIF 가격·관세 가정\n'
    '1GWh 기준 100만kWh·314Ah 셀 가정'
), 'Do not invent robot quantities or 1GW supply contracts from GWh'

elec_rewrite = make(
    "중국산 배터리 314Ah LFP 북미 CIF 61.99달러, 중국 EXW 51.62달러",
    "THE ELEC quoted BMI Sep 2026 314Ah LFP cell North America price "
    "$61.99/kWh and China exworks $51.62, up to 40.9% tariff is scenario.",
    "디일렉",
)
eg, es, ec, ek = classify(elec_rewrite)
assert eg == bg and es >= 11 and ec == bc and ek == bk, (eg,es,ec,ek)

price_blog_rewrite = dict(elec_rewrite,source="무명주식블로그")
pg, ps, pc, pk = classify(price_blog_rewrite)
assert pg == bg and ps < 11 and pk == bk, (pg,ps,pc,pk)

budget_oct_reprint = make(
    "전고체·나트륨 투 트랙 배터리 전쟁…정부, 3000억 투입 초협력 생태계",
    "산업통상부 배터리 산업기술 로드맵 2027~2031 나트륨·전고체 "
    "3000억원 정부 R&D, 민간 8조원, 610억원 로봇·드론 배터리 조기 상용화.",
    "이투데이",
)
pg, ps, pc, pk = classify(budget_oct_reprint)
assert pg == 'battery_roadmap_2026_baseline' and ps < 11,(pg,ps,pc)

budget_official_original = make(
    "K-배터리 산업기술 로드맵 나트륨 전고체 정부 4000억원 민간 8조원",
    "산업통상부 2026년 9월 22일 배터리 산업기술 로드맵 "
    "2027~2031 정부 4000억원 R&D 신설, 2026~2030 민간 8조원 설비투자.",
    "산업통상부",
)
og, os, oc, ok = classify(budget_official_original)
assert og == pg and os < 11,(og,os,oc)

oversupply_rewrite = make(
    "1000억달러 쏟았는데 북미 배터리 ESS로 전환",
    "미국 EV 배터리 공장 275GWh 설비용량 대 수요 182GWh, "
    "북미 1000억달러 투자 후 전기차 수요 부진에 ESS 전환.",
    "글로벌이코노믹",
)
vg, vs, vc, vk = classify(oversupply_rewrite)
assert vg == 'ev_to_ess_oversupply_baseline' and vs < 11,(vg,vs,vc)

real_lges_ess = make(
    "LG에너지솔루션 북미 ESS LFP 현지공장 실제 양산 시작",
    "LG에너지솔루션이 북미 35GWh 공장에서 새로운 ESS LFP 셀 "
    "실제 양산 개시를 공식 발표했다.",
    "LG에너지솔루션",
)
cg, cs, cc, ck = classify(real_lges_ess)
assert cg != 'ev_to_ess_oversupply_baseline',(cg,cs,cc)

recovered_lfp = watcher.query_news(watcher.LFP_NA_CIF_PRICE_RECOVERY)
if base.NOW.astimezone(base.KST).date() <= dt.date(2026,10,18):
    assert len(recovered_lfp) == 1,recovered_lfp
    assessed = recovered_lfp[0]
    assert assessed.get('published') is None,'Do not make up publication hour'
    assert assessed['source'] == 'Benchmark Mineral Intelligence'
    assert assessed['link'] == watcher.LFP_NA_CIF_PRICE_URL
    ag, a_s, a_cat, a_key=classify(assessed)
    assert ag==bg and a_s>=11 and a_key==bk,(ag,a_s,a_key)
    render_text=assessed['title']+' '+assessed['description']
    assert base.category(render_text,base.topic_group(render_text)) == bc
    assert '관세' in base.verification(assessed,ag,render_text)
    assert base.clean_title(assessed['title'],assessed['source']) != ''
past_now=base.NOW
try:
    base.NOW=dt.datetime(2026,10,19,6,0,tzinfo=dt.timezone.utc)
    assert watcher.query_news(watcher.LFP_NA_CIF_PRICE_RECOVERY) == []
finally:
    base.NOW=past_now
assert abs((61.99-51.62)/51.62*100-20.089112747)<0.00001
assert abs(61.99*1.409-87.34391)<0.00000001
assert abs((61.99*1.409-61.99)*1e6*1340.88/1e8-339.965508408)<0.00001
assert abs((61.99-51.62)*1e6*1340.88/1e8-139.049256)<0.00001
assert 314*3.2 == 1004.8000000000001  # one cell at 3.2V nominal



# 54) Production-alert false-positive found in Run #553, message_id=207:
# "ESS 올라탄 K배터리…LG엔솔·삼성SDI 3분기 실적 기대감↑"
# is market expectation, not new actual operating profit or ESS contracts.
ess_earnings_hope = make(
    "ESS 올라탄 K배터리…LG엔솔·삼성SDI 3분기 실적 기대감↑",
    "중국의 ESS LFP 수출 비용 증가로 한국 기업의 실적 개선 기대감이 높아졌다. "
    "고객 실명 신규 계약이나 판매량 증가 확인은 발표되지 않았다.",
    "전자신문",
)
hope_g, hope_s, hope_c, hope_k = classify(ess_earnings_hope)
assert hope_s < 11, ("editorial ESS earning hope cannot be new high-signal",hope_g,hope_s,hope_c)
assert watcher._is_ess_expectation_only(ess_earnings_hope), ess_earnings_hope

hope_synonym = make(
    "ESS 배터리 업계 3분기 실적 기대감 고조",
    "ESS 테마 선호는 커지지만 새로운 계약이나 출하 숫자는 없다.",
    "경제뉴스",
)
_, hope_syn_s, _, _ = classify(hope_synonym)
assert hope_syn_s < 11, hope_syn_s

# Do not suppress signed contracts merely because analysis text
# mentions potential earnings, or direct company quarterly releases.
ess_new_contract = make(
    "삼성SDI 신규 공급계약 체결, ESS 실적 기대감 확대",
    "삼성SDI가 신규 ESS 배터리 본계약을 체결했다고 발표했다.",
    "삼성SDI",
)
assert not watcher._is_ess_expectation_only(ess_new_contract), ess_new_contract

ess_actual_earnings = make(
    "LG에너지솔루션 3분기 잠정 실적 발표, ESS 성장",
    "LG에너지솔루션 공식 발표로 3Q 매출 9조6434억원과 영업이익 7560억원을 기록.",
    "LG에너지솔루션",
)
assert not watcher._is_ess_expectation_only(ess_actual_earnings),ess_actual_earnings




# This was an actual 2026-10-12 false positive in Telegram message_id=208.
# Both reputable publishers produced price-response articles, NOT new orders.
ess_stock_fake_one=make(
    "[특징주] 'ESS 기대감' 삼성SDI 3%·LG에너지솔루션 2% 상승",
    "ESS 기대감에 중국 관세와 공급망 우려로 주가가 상승했다고 보도했다.",
    "아이뉴스24",
)
ess_stock_fake_two=make(
    "[특징주] 삼성SDI·LG에너지솔루션 강세…실적 개선·ESS 수주 기대",
    "ESS 수주 기대감으로 주가가 올랐지만 신규 계약 체결 공시는 없다.",
    "이투데이",
)
for stock_article in (ess_stock_fake_one,ess_stock_fake_two):
    _,stock_score,_,_=classify(stock_article)
    assert stock_score<11, ("Stock-price rewrite reached telegram",stock_score)
    assert watcher._is_stock_reaction_only(stock_article),stock_article

# 54) CATL and VNET: 2026-09-21 indirect secondary equity closing
# is NOT VNET sodium-ion 60GWh supply (HyperStrong is the actual buyer).
vnet_recovered = watcher.query_news(watcher.VNET_EQUITY_RECOVERY)
if base.NOW.astimezone(base.KST).date() <= dt.date(2026,10,19):
    assert len(vnet_recovered)==1 and vnet_recovered[0]['source']=='VNET',vnet_recovered
    assert vnet_recovered[0]['published'] is None, 'never invent the filing hour'
    vg,vs,vc,vk=classify(vnet_recovered[0])
    assert vg=='catl_vnet_infrastructure' and vs>=11,(vg,vs,vc)
    assert vc=='CATL 관계사–VNET · 10/12 주가 기사 오탐 정정',vc
    assert '기존주' in base.meaning(vc) and '독점' in base.meaning(vc),base.meaning(vc)
    assert '1,007MW' in base.meaning(vc) and '889MW' in base.meaning(vc)
    assert '60GWh' in base.meaning(vc)
    assert '208' in base.meaning(vc) and '1·3번' in base.meaning(vc)
    assert vnet_recovered[0].get('correction_for_false_stock_alerts') is True
    assert base.key(vnet_recovered[0]) != hashlib.sha256(b'vnet|PJ-Millennium|CATL-affiliate|20260921|38.1|650424192|SECONDARY').hexdigest(), 'correction must be one different semantic event'
    assert base.clean_title(vnet_recovered[0]['title'],vnet_recovered[0]['source']).startswith('정정:'), 'corrective alert title overwritten'
    visible=vnet_recovered[0]['title']+' '+vnet_recovered[0]['description']
    assert base.category(visible,vg)==vc,'source loss in Telegram renderer'
    assert base.key(vnet_recovered[0])==vk
    assert watcher.qty._skip_quantity_enrichment(
        '<b>CATL 관계사–VNET · 9/21 간접지분 38.1% 인수 종결</b> '
        'VNET 도매 IDC 889MW→1,007MW 주식 650,424,192주'
    ), 'IDC MW are not BESS MWh or confirmed battery shipments'
else:
    vnet_recovered=[]

vnet_old_cooperation=make(
    'CATL VNET strategic cooperation for data-center energy',
    'VNET and CATL announced compute energy integration cooperation in August 2026, '
    'with no signed sodium ESS purchase agreement.',
    'VNET',
)
vg,vs,vc,vk2=classify(vnet_old_cooperation)
assert vg=='catl_vnet_infrastructure' and vs<11,(vg,vs,vc)

vnet_stale_mw=make(
    'CATL VNET 889MW exclusive sodium-ion ESS 60GWh claim',
    'CATL and HyperStrong signed 60 GWh sodium-ion supply agreement in April, '
    'while VNET and CATL discussed compute-energy cooperation. '
    'The 889MW value was end-2025 wholesale IDC installed capacity, '
    'not 60 GWh or an exclusive order by VNET.',
    'VNET',
)
sg,ss,sc,sk=classify(vnet_stale_mw)
assert sg=='catl_vnet_infrastructure' and ss<11,(sg,ss,sc)
assert sc.endswith('간접지분 38.1% 인수 종결'),sc

vnet_future_real_contract=make(
    'CATL VNET sodium-ion 2 GWh ESS new supply contract',
    'VNET and CATL signed binding supply agreement for sodium-ion 2 GWh '
    'battery storage for a named VNET data center, with actual delivery schedule.',
    'VNET',
)
ng,ns,nc,nk=classify(vnet_future_real_contract)
assert ng=='catl_vnet_infrastructure' and ns>=11,(ng,ns,nc)
assert nc=='CATL–VNET · 나트륨 ESS 실명 공급계약',nc
assert nk!=vk,'future confirmed sodium order must be separate from equity'
assert 'MWh' in base.risk(nc),'future order must trace deployed ESS energy capacity'
assert '공식 납품 계약' in base.clean_title(vnet_future_real_contract['title'],vnet_future_real_contract['source']), 'new sodium contract must not carry old equity-title'

vnet_false_press=dict(vnet_future_real_contract,source='Unknown Financial Blog')
bg,bs,bc,bk=classify(vnet_false_press)
assert bg=='catl_vnet_infrastructure' and bs<11,(bg,bs,bc)

old_vnet_date=base.NOW
try:
    base.NOW=dt.datetime(2026,10,20,0,0,tzinfo=dt.timezone.utc)
    assert watcher.query_news(watcher.VNET_EQUITY_RECOVERY)==[]
finally:
    base.NOW=old_vnet_date



# 53) FUNDA 2026-10-12 channel-check estimate of 3–4x robot
# post-training GPU resources on 7–13B models. The original article text
# is available from indexed search; direct URL-open failed. Raw same-hardware
# metered GPU-hours and an independent reproduction remain unavailable.
funda_claim = make(
    "FUNDA Physical AI robot data race to second compute demand curve",
    "FUNDA industry interviews estimate robot VLA model post-training with "
    "video, joint and action signals takes 3-4x GPU resources versus "
    "text-only model post-training at the same parameter count. "
    "No benchmark GPU-hours, server order, named training cluster or "
    "independent same-condition replication was disclosed.",
    "FUNDA",
)
fg, fs, fc, fk = classify(funda_claim)
assert fg == 'robot_posttrain_compute' and fs < 11, (fg,fs,fc)
assert fc == '로봇 사후학습 · Funda AI 3~4배 추정 기준선', fc
assert '독립' in base.verification(funda_claim,fg,funda_claim['title']+' '+funda_claim['description'])
assert '3~4배' in base.meaning(fc), base.meaning(fc)
assert '70억~130억' in base.meaning(fc), base.meaning(fc)
assert '사전학습보다' in base.meaning(fc), base.meaning(fc)
assert '실제 산업 GPU 수요' in base.meaning(fc), base.meaning(fc)
assert '원문 검색 결과의 본문 확인' in base.verification(
    funda_claim,fg,funda_claim['title']+' '+funda_claim['description']
), 'Public source retrieved through indexed search; no longer only a user excerpt'
assert '직접 URL 열람 실패' in base.verification(
    funda_claim,fg,funda_claim['title']+' '+funda_claim['description']
), 'A failed direct open must not be represented as a successful full URL fetch'

funda_reprint = make(
    "Funda AI physical robotics compute GPU 3~4x post-training estimate",
    "An outside news article quotes FUNDA robot VLA post-training 3~4x "
    "GPU resources against text-only; hardware purchases not confirmed.",
    "Thematic News Blog",
)
rg, rs, rc, rk = classify(funda_reprint)
assert rg == fg and rs < 11 and rk == fk, (rg,rs,rc,rk)

nvidia_pretraining_only = make(
    "NVIDIA GR00T robot pretraining compute",
    "NVIDIA GR00T robot VLA model pretraining consumed "
    "50,000 H100 GPU-hours, not a post-training benchmark.",
    "NVIDIA",
)
pg, ps, pc, pk = classify(nvidia_pretraining_only)
assert pg != 'robot_posttrain_compute' or ps < 11, (pg,ps,pc)

independent_news_gpu_hours = make(
    "Robot policy post-training used 12,000 GPU-hours, media report",
    "Research blogger claims a VLA robot post-training benchmark "
    "measured 12,000 H100 GPU-hours, without official results.",
    "Unverified Robotics Blog",
)
ng, ns, nc, nk = classify(independent_news_gpu_hours)
assert ng == 'robot_posttrain_compute' and ns < 11, (ng,ns,nc)

future_official_measurement = make(
    "NVIDIA Isaac GR00T VLA robot post-training GPU-hour benchmark",
    "NVIDIA officially reported measured robot VLA post-training "
    "using 12,000 H100 GPU-hours on a named task/data setup. "
    "This is a hypothetical future regression fixture.",
    "NVIDIA",
)
og, os, oc, ok = classify(future_official_measurement)
assert og == 'robot_posttrain_compute' and os >= 11, (og,os,oc)
assert oc == '로봇 사후학습 · GPU시간 실측 공개', oc
assert ok != fk, 'official measured training workload must be a new alert'
render_text = future_official_measurement['title'] + ' ' + future_official_measurement['description']
assert base.category(render_text,base.topic_group(render_text)) == oc
assert '실측' in base.verification(future_official_measurement,og,render_text)

# A generic "reported" or "benchmark" in an official article does NOT
# prove actual metered GPU-hours: it must contain measured/instrumented data.
nvidia_unspecified_report = make(
    "NVIDIA robot post-training GPU-hour report",
    "NVIDIA reported a benchmark estimate of 12,000 H100 GPU-hours for "
    "robot VLA post-training but published no measured training logs.",
    "NVIDIA",
)
xg, xs, xc, xk = classify(nvidia_unspecified_report)
assert xg == 'robot_posttrain_compute' and xs < 11, (xg,xs,xc)

# A Figure–Nscale 2026-09-03 official COMPUTE SERVICE commitment is
# separate from a post-training GPU-hour measurement and not new on 10/12.
figure_nscale_old = make(
    "Figure Nscale up to 100,000 NVIDIA GPUs on Vera Rubin",
    "Figure and Nscale signed a 3.5 billion USD multi-year compute services "
    "commitment for 100,000 GPUs with first deployment planned H2 2027; "
    "robot simulation training and post-training are possible workloads "
    "but GPU-hours measured for a named training run are NOT disclosed.",
    "Figure AI",
)
nxg, nxs, nxc, nxk = classify(figure_nscale_old)
assert nxg != 'robot_posttrain_compute' or nxs < 11, (nxg,nxs,nxc)

non_robot_training = make(
    "NVIDIA LLM text post-training compute",
    "NVIDIA text-only LLM post-training measured 12,000 GPU-hours.",
    "NVIDIA",
)
tg, ts, tc, tk = classify(non_robot_training)
assert tg != 'robot_posttrain_compute', (tg,ts,tc)

assert watcher.qty._skip_quantity_enrichment(
    '<b>1. 피지컬AI 학습 연산</b>\n'
    '<b>분류</b>  로봇 사후학습 · GPU시간 실측 공개\n'
    '모델 사후학습 12,000 GPU시간은 실제 출하 대수가 아니다'
), 'GPU-hours must not be counted as priced robot units'
assert watcher.qty._skip_quantity_enrichment(
    '<b>1. Funda AI 로봇 사후학습 GPU 3~4배</b>\n'
    '동영상·행동 신호의 사후학습 추정치'
)


# 54) 2026-10-13 Korean ministry original 14-page sandbox approval.
# This already generated Telegram message_id=213 in Run #573.
# It is a conditional 20-robot PLAN and must not be resent or rendered
# as 20 delivered sales; actual site KPIs/contracts are separate upgrades.
robros_approval = make(
    "산업통상부 제6차 규제특례 승인 로브로스 휴머노이드 20대",
    "산업통상부는 로브로스 이동형 휴머노이드 20대를 네패스 반도체, "
    "성우하이텍 자동차, HD현대삼호 조선, 딜리버리랩 물류 "
    "현장에서 실증특례 승인했다. 위험성평가와 위험감소 조건을 따른다.",
    "파이낸셜뉴스",
)
arg, ars, arc, ark = classify(robros_approval)
assert arg == "robros_industrial_sandbox" and ars >= 11, (arg,ars,arc)
assert arc == "로브로스 산업실증 · 이동형 휴머노이드 20대 규제특례 승인",arc
assert "20대를" in base.meaning(arc) and "30억원" in base.meaning(arc)
assert "정부 예산·확정 매출이 아닙니다" in base.meaning(arc)
assert "14쪽 공식 보도자료" in base.verification(
    robros_approval,arg,robros_approval["title"]+" "+robros_approval["description"]
)
assert "작업 성공률" in base.risk(arc)
assert "보험" in base.risk(arc) and "6~12개월" in base.risk(arc)

robros_reprint = make(
    "로브로스 반도체 자동차 조선 물류 휴머노이드 20대 규제특례 승인",
    "로브로스가 네패스·성우하이텍·HD현대삼호·딜리버리랩 "
    "현장에 휴머노이드 로봇 20대 실증특례 승인을 받았다.",
    "연합뉴스",
)
rpg,rps,rpc,rpk=classify(robros_reprint)
assert rpg==arg and rps>=11 and rpk==ark, (rpg,rps,rpc,rpk)

robros_old_yield = make(
    "로브로스 과거 IGRIS-C 9대 유상공급",
    "로브로스 2026-08-19 이그리스-C 9대 유상 공급을 발표했다. "
    "휴머노이드 20대 규제특례 승인 전의 기존 납품 건이다.",
    "로브로스",
)
yg,ys,yc,yk=classify(robros_old_yield)
assert yg != "robros_industrial_sandbox" or ys < 11, (yg,ys,yc)

robros_installed = make(
    "로브로스 네패스 반도체 제조현장 휴머노이드 실제 배치 완료",
    "로브로스가 네패스 반도체 클리닝 제조현장에 "
    "휴머노이드 이그리스 실증 로봇 실제 배치 완료를 발표했다.",
    "로브로스",
)
dg,ds,dc,dk=classify(robros_installed)
assert dg==arg and ds>=11 and dc.endswith("실제 배치 개시"),(dg,ds,dc)
assert dk!=ark,"Site deployment must upgrade from government approval"

robros_kpi = make(
    "로브로스 성우하이텍 휴머노이드 로봇 작업 성공률 92% 측정",
    "로브로스가 성우하이텍 자동차 현장 휴머노이드 작업 성공률 "
    "92% 측정 결과를 발표했다.",
    "로브로스",
)
kg,ks,kc,kk=classify(robros_kpi)
assert kg==arg and ks>=11 and kc.endswith("작업 KPI 실측"), (kg,ks,kc)
assert kk not in {ark,dk}

robros_order = make(
    "로브로스 HD현대삼호 휴머노이드 정식 구매 계약 체결",
    "로브로스는 HD현대삼호 조선소 휴머노이드 로봇 정식 "
    "납품 계약 체결을 발표했다.",
    "로브로스",
)
og,os,oc,ok=classify(robros_order)
assert og==arg and os>=11 and oc.endswith("고객 정식 유상계약"),(og,os,oc)
assert ok not in {ark,dk,kk}

robros_news_expectation = dict(robros_order,source="출처 불명 테마 블로그")
ng,ns,nc,nk=classify(robros_news_expectation)
assert ng==arg and ns<11,(ng,ns,nc)

robros_recovered = watcher.query_news(watcher.ROBROS_PILOT_20261013)
if base.NOW.astimezone(base.KST).date()<=dt.date(2026,10,20):
    expected_count = 2 if base.NOW.astimezone(base.KST).date() <= dt.date(2026,10,16) else 1
    assert len(robros_recovered) == expected_count, robros_recovered
    p=robros_recovered[0]
    assert p["published"]=="2026-10-13T06:00:00+00:00",p
    assert "공식 보도자료" in p["description"],p
    assert "실제 현장 운영일자" in p["description"],p
    bg,bs,bc,bk=classify(p)
    assert bg==arg and bs>=11 and bk==ark,(bg,bs,bc,bk)
    assert "규제특례 승인" in base.category(p["title"]+" "+p["description"],bg)

# Real false positives seen in Run #573 (message_id=213).
price_only_false_alert=make(
    "24만4500원…로봇 양산 기대 속 4.86% 조정",
    "로보티즈 주가는 조정됐지만 신규 발주·출하량 발표는 없다.",
    "잡포스트",
)
assert watcher._is_stock_reaction_only(price_only_false_alert)
pg,ps,pc,pk=classify(price_only_false_alert)
assert ps<11,(pg,ps,pc)

editorial_only_false_alert=make(
    "[심층분석] LG전자, 가전 넘어 AI 데이터센터·스마트팩토리로…생활기술의 산업화 시험대",
    "LG전자의 스마트팩토리 사업과 AI데이터센터 기회에 관한 일반 전망",
    "뉴스밸류",
)
assert watcher._is_stock_reaction_only(editorial_only_false_alert)
eg,es,ec,ek=classify(editorial_only_false_alert)
assert es<11,(eg,es,ec)

material_editorial=make(
    "[심층분석] 로브로스 신규 공급계약 체결",
    "로브로스·네패스 산업현장 휴머노이드 20대 정식 신규 공급계약 체결",
    "연합뉴스",
)
assert not watcher._is_stock_reaction_only(material_editorial),material_editorial



# Real Run #574 false positive: generic AI data-center ESS demand, no
# contracted deployment, meter reading, or price observation.
ess_ai_demand_only=make(
    '"AI가 삼키는 전력, 배터리가 받친다"… AI 데이터센터發 ESS 수요 폭증',
    '기존 자료를 인용한 AI 데이터센터 ESS 수요 시장 전망으로 '
    '별도 신규 수주 계약액·실제 현장 설치·관측 가격 발표는 없음',
    '글로벌이코노믹',
)
assert watcher._is_generic_ess_demand_story(ess_ai_demand_only)
eg, es, ec, ek = classify(ess_ai_demand_only)
assert es < 11, (eg,es,ec)

material_ess_headline=make(
    'ESS 수요 급증 속 삼성SDI 신규 공급계약 체결',
    '삼성SDI의 고객 실명 공식 신규 수주가 별도로 공시됐다.',
    '연합뉴스',
)
assert not watcher._is_generic_ess_demand_story(material_ess_headline)

# One-time, user-visible correction of three false positives from messages
# #213 (two invalid topics) and #214 (one general demand article).
old_robros_now=base.NOW
try:
    base.NOW=dt.datetime(2026,10,13,10,0,tzinfo=dt.timezone.utc)
    recovered=watcher.query_news(watcher.ROBROS_PILOT_20261013)
    corrections=[x for x in recovered if x.get('robros_false_alert_correction')]
    assert len(corrections)==1, corrections
    corr=corrections[0]
    cg,cs,cc,ck=classify(corr)
    assert cg=="robros_industrial_sandbox" and cs>=11, (cg,cs,cc)
    assert cc=="로브로스 실증특례 · Telegram 오탐 정정",cc
    assert ck!=ark,"Correction must not reissue the approval event key"
    rendered=corr["title"]+" "+corr["description"]
    assert base.category(rendered,base.topic_group(rendered))==cc
    assert base.clean_title(corr["title"],corr["source"]).startswith("정정:")
    assert "실발송" in base.verification(corr,cg,rendered)
    for expected in ["213번 1번","3번 LG전자","214번 ESS","공식 보도자료","30억원"]:
        assert expected in base.meaning(cc),(expected,base.meaning(cc))
    # Historical correction cannot be replayed after de-dup state rotation.
    base.NOW=dt.datetime(2026,10,17,10,0,tzinfo=dt.timezone.utc)
    assert watcher._robros_213_214_correction()==[]
finally:
    base.NOW=old_robros_now



def _historical_one_shot_query(query: str) -> list[dict]:
    """Check date-limited historical recoveries without replaying them today."""
    previous_now = base.NOW
    try:
        base.NOW = dt.datetime(2026, 10, 20, 10, 0, tzinfo=dt.timezone.utc)
        return watcher.query_news(query)
    finally:
        base.NOW = previous_now


# 57) CATL–INTILION 3GWh/5y: joint DEVELOPMENT target only;
# no confirmed procurement, 10+3 GWh sum or current revenue.
ci=make("CATL INTILION sodium-ion 3 GWh five-year cooperation",
    "INTILION and CATL jointly develop up to 3 GWh sodium-ion ESS over five years "
    "in Germany Austria Switzerland, no firm purchase obligation or deliveries.",
    "INTILION CEO")
cg,cs,cc,ck=classify(ci)
assert cg=='catl_intilion_sodium' and cs>=11,(cg,cs,cc)
assert cc=='CATL–INTILION · 유럽 5년 최대 3GWh 공동개발 목표',cc
assert '13GWh로 집계하지' in base.meaning(cc) and '300억원' in base.meaning(cc)
assert '25℃' in base.risk(cc) and '45℃' in base.risk(cc)

ci_report=make("CATL INTILION 3GWh sodium-ion European cooperation",
    "CATL and INTILION signed a five-year deal targeting up to 3GWh "
    "sodium-ion energy storage projects, without firm purchase orders.",
    "pv magazine")
cg2,cs2,cc2,ck2=classify(ci_report)
assert cg2==cg and cs2>=11 and cc2==cc and ck2==ck,(cg2,cs2,cc2,ck2)

ci_old=make("CATL INTILION 10GWh TENER agreement",
    "CATL and INTILION agreed in 2025 on 10GWh lithium-ion storage for five years.",
    "pv magazine")
og,os,oc,ok=classify(ci_old)
assert og!='catl_intilion_sodium' or os<11,(og,os,oc)

ci_contract=make("CATL INTILION binding sodium-ion ESS procurement",
    "CATL and INTILION signed binding purchase contract for sodium-ion "
    "0.5GWh systems at a named project with first firm orders.",
    "CATL")
pg,ps,pc,pk=classify(ci_contract)
assert pg==cg and ps>=11 and pc=='CATL–INTILION · 실제 구속력 있는 구매계약',(pg,ps,pc)
assert pk!=ck

ci_rumor=dict(ci_contract,source='익명 시장게시글')
rg,rs,rc,rk=classify(ci_rumor)
assert rg==cg and rs<11,(rg,rs,rc)

ci_rec=_historical_one_shot_query(watcher.CATL_INTILION_RECOVERY)
assert len(ci_rec)==1 and ci_rec[0]['published'] is None,ci_rec
ci_rg,ci_rs,ci_rc,ci_rk=classify(ci_rec[0])
assert ci_rg==cg and ci_rs>=11 and ci_rc==cc and ci_rk==ck,(ci_rg,ci_rs,ci_rc)
assert base.category(ci_rec[0]['title']+' '+ci_rec[0]['description'],ci_rg)==cc
assert '3GWh 공동개발 목표' in base.clean_title(ci_rec[0]['title'],ci_rec[0]['source'])
assert watcher.qty._skip_quantity_enrichment(
    '<b>CATL–INTILION · 유럽 5년 최대 3GWh 공동개발 목표</b>\n'
    '3GWh target 10GWh previous plan 1GWh 2027 targets')
assert '확정 구매·수주·납품 아님' in base.verification(ci_rec[0],ci_rg,
        ci_rec[0]['title']+' '+ci_rec[0]['description'])

# 58) RoboStrategy's 2-3y/5y outlook remains opinion. Dexmate CEO
# adds self-reported use/distribution, NOT LG CNS paid sales or 99.99% achieved.
dex=make("Dexmate CEO Tao Chen LG CNS uses robots distribution support",
    "At a New York interview Dexmate CEO Tao Chen said LG CNS is using "
    "Dexmate robots and supporting distribution in Korea. Hundreds worldwide "
    "are a CEO claim and 99.99% task success is required, not measured.",
    "이데일리")
dg,ds,dc,dk=classify(dex)
assert dg=='dexmate_lg_commercial' and ds>=11,(dg,ds,dc)
assert dc=='Dexmate–LG CNS · 사용·유통 CEO 현장발언',dc
assert '독점 유상 유통계약' in base.meaning(dc)
assert '요구수준이지' in base.risk(dc)

old_lg=make("LG CNS invests in Dexmate",
    "LG CNS and Dexmate announced strategic investment and robot proof of concept in March.",
    "LG CNS")
lg,ls,lc,lk=classify(old_lg)
assert lg==dg and ls<11,(lg,ls,lc)

opinion=make("RoboStrategy robot commercialization in 2-3 years",
    "RoboStrategy COO forecasts specific-task robots in two or three years "
    "and general-purpose robots around five years. No new customer order.",
    "이데일리")
og,os,oc,ok=classify(opinion)
assert og!='dexmate_lg_commercial',(og,os,oc)

req=make("Dexmate LG CNS needs 99.99% successful tasks",
    "Dexmate and LG CNS robotics need a 99.99% target, not achieved.",
    "Dexmate")
rg,rs,rc,rk=classify(req)
assert rg==dg and rs<11,(rg,rs,rc)

paid=make("Dexmate LG CNS signed purchase contract for robots",
    "Dexmate and LG CNS signed purchase contract for robots and paid deployment.",
    "Dexmate")
pg,ps,pc,pk=classify(paid)
assert pg==dg and ps>=11 and pc=='Dexmate–LG CNS · 공식 유료 공급계약',(pg,ps,pc)
assert pk!=dk

dex_rec=_historical_one_shot_query(watcher.DEXMATE_LG_RECOVERY)
assert len(dex_rec)==1 and dex_rec[0]['source']=='이데일리' and dex_rec[0]['published'] is None,dex_rec
rg,rs,rc,rk=classify(dex_rec[0])
assert rg==dg and rs>=11 and rc==dc and rk==dk,(rg,rs,rc,rk)
assert base.category(dex_rec[0]['title']+' '+dex_rec[0]['description'],rg)==dc
assert 'Dexmate CEO:' in base.clean_title(dex_rec[0]['title'],dex_rec[0]['source'])
assert watcher.qty._skip_quantity_enrichment(
    '<b>Dexmate–LG CNS · 사용·유통 CEO 현장발언</b>\n'
    '99.99% target and hundreds of global robots')
assert '독점 계약' in base.verification(dex_rec[0],rg,dex_rec[0]['title']+' '+dex_rec[0]['description'])

time_before=base.NOW
try:
    base.NOW=dt.datetime(2026,10,22,11,0,tzinfo=dt.timezone.utc)
    assert watcher.query_news(watcher.CATL_INTILION_RECOVERY)==[]
    assert watcher.query_news(watcher.DEXMATE_LG_RECOVERY)==[]
finally:
    base.NOW=time_before



# 59) Real Telegram #218 item 1: Samsung SDI 5% "오르며" stock
# reaction is NOT a new ESS customer, order, shipment or quarter.
run584_false_stock=make(
    "AI 전력發 ESS 기대…삼성SDI 5% 오르며 2차전지株 ‘강세’[줍줍리포트]",
    "증시에서 삼성SDI 등 관련주가 올랐다는 시장 반응으로 "
    "실제 공급계약·발주·매출 공시는 전혀 없는 기사.",
    "서울경제",
)
assert watcher._is_stock_reaction_only(run584_false_stock)
sg,ss,sc,sk=classify(run584_false_stock)
assert ss<11,(sg,ss,sc)

stock_synonym_down=make("AI 배터리 관련주 4.2% 내리며 약세",
    "실적과 계약 내용 없는 단순 증시 반응","경제뉴스")
assert watcher._is_stock_reaction_only(stock_synonym_down)

real_new_event_headline=make(
    "삼성SDI 5% 오르며 신규 ESS 공급계약 체결",
    "확정 계약을 특정 고객과 신규 공시했다.",
    "연합뉴스",
)
assert not watcher._is_stock_reaction_only(real_new_event_headline),(
    "material signed order headlines must not be hidden just because stock rose"
)

corr=watcher.query_news(watcher.STOCK_218_CORRECTION)
if base.NOW.astimezone(base.KST).date() > dt.date(2026,10,18):
    assert corr == [], 'expired one-time correction must not replay'
    # Regression checks for correction content run against their original
    # active window, then restore the real current clock.
    _restore_now = base.NOW
    base.NOW = dt.datetime(2026,10,17,12,0,tzinfo=dt.timezone.utc)
    try:
        corr = watcher.query_news(watcher.STOCK_218_CORRECTION)
    finally:
        base.NOW = _restore_now
assert len(corr)==1 and corr[0].get('correction_218_stock'),corr
cg,cs,cc,ck=classify(corr[0])
assert cg=='alert_quality_correction' and cs>=11,(cg,cs,cc)
assert cc=='알림 품질 정정 · Telegram 218번 1번 오탐',cc
assert '2번 CATL–INTILION' in base.meaning(cc)
assert '3번 Dexmate–LG CNS' in base.meaning(cc)
txt=corr[0]['title']+' '+corr[0]['description']
assert base.category(txt,base.topic_group(txt))==cc
assert base.clean_title(corr[0]['title'],corr[0]['source']).startswith('정정:')
assert 'Run #584' in base.verification(corr[0],cg,txt)
assert watcher.qty._skip_quantity_enrichment(
    '<b>알림 품질 정정</b>\n정정: Telegram 218번 1번'
)
seen_before=base.NOW
try:
    base.NOW=dt.datetime(2026,10,19,12,0,tzinfo=dt.timezone.utc)
    assert watcher.query_news(watcher.STOCK_218_CORRECTION)==[]
finally:
    base.NOW=seen_before



# 60) Vattenfall Brunsbuettel: September final investment decision and
# October Fluence signed 1 GWh EPC award are distinct milestones. This test
# models future milestones but does not assert they have happened.
fluence_fid = make(
    "Vattenfall Fluence Brunsbüttel September FID",
    "Vattenfall takes final investment decision for 254MW and 1,000MWh "
    "Brunsbüttel battery in September 2026, construction planned for 2027.",
    "Vattenfall",
)
ffg,ffs,ffc,ffk=classify(fluence_fid)
assert ffg=='fluence_vattenfall_bess' and ffs<11,(ffg,ffs,ffc)

fluence_signed = make(
    "Vattenfall Fluence Brunsbüttel 1 GWh signed turnkey contract",
    "Fluence and Vattenfall signed an agreement for the 254MW/1,000MWh "
    "Brunsbüttel Gridstack Pro 5000 battery facility. Includes EPC, "
    "commissioning and long-term service. Construction planned 2027, "
    "commercial operation expected end 2028, 380kV grid.",
    "Fluence (GlobeNewswire)",
)
fsg,fss,fsc,fsk=classify(fluence_signed)
assert fsg=='fluence_vattenfall_bess' and fss>=11,(fsg,fss,fsc)
assert fsc=='Fluence–Vattenfall · 독일 1GWh ESS 정식 턴키 공급계약',fsc
assert fsk!=ffk,'2026-09 FID cannot dedup into 2026-10 signed vendor award'
fc=base.meaning(fsc)
for needle in ('254MW','1,000MWh','380kV','2027년','2028년','장기 유지보수','4,201억','6,751억원','계약액'):
    assert needle in fc,(needle,fc)
assert '삼성SDI 매출로' in base.risk(fsc),base.risk(fsc)

fluence_signed_other_official = make(
    "Fluence Vattenfall Brunsbüttel contract 254MW 1GWh",
    "Fluence and Vattenfall signed an agreement for Brunsbüttel 254MW "
    "1GWh battery EPC and long term services.",
    "Vattenfall",
)
c2g,c2s,c2c,c2k=classify(fluence_signed_other_official)
assert c2g==fsg and c2s>=11 and c2k==fsk,(c2g,c2s,c2c,c2k)

fluence_media_only=make(
    "Fluence Vattenfall Brunsbüttel 1GWh 계약설",
    "Vattenfall Fluence Brunsbüttel project 254MW contract signed "
    "according to unnamed industry sources.",
    "테마주 블로그",
)
fmg,fms,fmc,fmk=classify(fluence_media_only)
assert fmg==fsg and fms<11,(fmg,fms,fmc)

fluence_future_construction=make(
    "Fluence Vattenfall Brunsbüttel construction started",
    "Fluence and Vattenfall confirm Brunsbüttel battery construction "
    "has started on the 254 MW project.",
    "Fluence",
)
fcg,fcs,fcc,fck=classify(fluence_future_construction)
assert fcg==fsg and fcs>=11 and fck!=fsk,(fcg,fcs,fcc)
assert '실제 착공' in fcc,fcc

fluence_future_energized=make(
    "Fluence Vattenfall Brunsbüttel grid connection completed",
    "Fluence and Vattenfall Brunsbüttel 254MW BESS "
    "grid connection completed and commercial operation started.",
    "Fluence",
)
feg,fes,fec,fek=classify(fluence_future_energized)
assert feg==fsg and fes>=11 and fek!=fsk and fek!=fck,(feg,fes,fec)
assert '전원 인가' in fec,fec

fluence_future_cancel=make(
    "Fluence Vattenfall Brunsbüttel cancelled contract",
    "Fluence and Vattenfall Brunsbüttel 254MW BESS "
    "have cancelled their supply contract.",
    "Fluence",
)
frg,frs,frc,frk=classify(fluence_future_cancel)
assert frg==fsg and frs>=11 and frk not in {fsk,fck,fek},(frg,frs,frc)

fluence_backfill=watcher.query_news(watcher.FLUENCE_VATTENFALL_RECOVERY)
if base.NOW.astimezone(base.KST).date()<=dt.date(2026,10,20):
    assert len(fluence_backfill)==1,fluence_backfill
    fb=fluence_backfill[0]
    assert fb['source']=='Fluence (GlobeNewswire)',fb
    assert fb['published']=='2026-10-14T07:00:00+00:00',fb
    fg,fs,fc,fk=classify(fb)
    assert fg==fsg and fs>=11 and fk==fsk,(fg,fs,fc,fk)
    rendered=fb['title']+' '+fb['description']
    assert base.category(rendered,base.topic_group(rendered))==fsc,rendered
    assert 'Fluence' in base.clean_title(fb['title'],fb['source'])
    verify=base.verification(fb,fg,rendered)
    assert 'GlobeNewswire' in verify and '9/10' in verify,verify
    assert watcher.qty._skip_quantity_enrichment(
        '<b>1. Fluence·Vattenfall ESS</b>\n'
        '<b>분류</b> Fluence–Vattenfall · 독일 1GWh ESS 정식 턴키 공급계약\n'
        '254MW, 1,000MWh, 2028년'
    )
old_bess_now=base.NOW
try:
    base.NOW=dt.datetime(2026,10,21,12,0,tzinfo=dt.timezone.utc)
    assert watcher.query_news(watcher.FLUENCE_VATTENFALL_RECOVERY)==[]
finally:
    base.NOW=old_bess_now

# 61) Samsung SDI October 8 DS preview is not confirmed Q3 profit,
# new customer contract, completed proceeds allocation or 10GWh tooling.
sdi_ds_preview=make(
    "삼성SDI 3Q26 Preview 본업 흑자 DS투자증권 최태용",
    "삼성SDI 3분기 영업이익 2575억원 전망 중 정산이익 1500억원 예상, "
    "4분기 추가 수주 기대 및 시너지셀즈 2028년 10GWh 생산라인 검토.",
    "뉴스핌",
)
sg,ss,sc,sk=classify(sdi_ds_preview)
assert sg=='sdi_oct08_broker_preview' and ss<11,(sg,ss,sc)
assert '증권사' in base.category(sdi_ds_preview['title']+' '+sdi_ds_preview['description'],sg),sc
assert '추정치' in base.meaning(sc),base.meaning(sc)
sdi_official_earnings=make(
    "삼성SDI 3분기 공식 실적 발표",
    "삼성SDI는 3분기 실적 발표에서 ESS와 UPS용 배터리 "
    "영업이익률과 AMPC를 구분하여 실제 실적을 공개했다.",
    "삼성SDI",
)
og,os,oc,ok=classify(sdi_official_earnings)
assert og!='sdi_oct08_broker_preview',og

# 62) Basic unit parsing: MW is not MWh; there are no invented
# robot units in a grid-scale battery contract.
assert watcher.qty.QTY_RE.findall('254MW 1000MWh 1GWh 1GW')==[
    ('254','MW'),('1','GW')
],watcher.qty.QTY_RE.findall('254MW 1000MWh 1GWh 1GW')


# 52) October 12-15 robot events: primary issuer status vs press,
# honest anonymous customers, prototype aims vs proven production.
oct15_expected = {
    'agility_s4_effective': ('agility_spac_2026', 'S-4 효력'),
    'rainbow_fcc_filed': ('rainbow_fcc_compliance', '조건부승인 신청'),
    'xinjian_ipo_response': ('xinjian_prs_ipo', '익명 A사'),
    'unichem_loomia_signed': ('unichem_loomia_acquisition', '인수 본계약'),
    'atlas_protoops_goal': ('atlas_protoops_build', '제작시간 단축 목표'),
    'alert223_quality_correction': ('alert_quality_223', 'ESS 오탐'),
    'alert224225_quantity_correction': ('alert_quality_qty_224225', '수량 표기 오탐'),
}
oct15_keys = []
for event_key, (expected_group, expected_phrase) in oct15_expected.items():
    rows = watcher.query_news(watcher.ROBOT_OCT15_PREFIX + event_key)
    if base.NOW.astimezone(base.KST).date() <= dt.date(2026, 10, 20):
        assert len(rows) == 1, (event_key,rows)
        item = rows[0]
        group, points, cat, dedupe_key = classify(item)
        assert group == expected_group and points >= 11, (event_key,group,points,cat)
        assert expected_phrase in cat, (event_key,cat)
        assert item['published'] is None, (event_key,'publication time invented')
        assert base.risk(cat) and base.meaning(cat), (event_key,cat)
        assert base.verification(item,group,item['title']+' '+item['description'])
        assert base.category(item['title']+' '+item['description'],group) == cat
        oct15_keys.append(dedupe_key)
assert len(set(oct15_keys)) == len(oct15_keys), "Oct15 different events collapsed"

# Reject reprinted bank target prices and already-discussed Japan ESS market
# positioning: four exact headline families from the real Telegram #223.
for title, source in (
    ("[리포트 브리핑] 삼성SDI, '미국 ESS 시장 점유율 확대 기대' 목표가 900,000원 - 다올투자증권", "뉴스핌"),
    ("LG에너지솔루션, ESS 성장 기대…목표가 51만원으로 상향", "파이낸셜뉴스"),
    ("“中 사이버 보안 인증 탈락 틈새” 삼성SDI·대만 연합, 日 ESS 시장 '대공세'", "글로벌이코노믹"),
    ("삼성SDI, 중국산 배제된 일본 ESS 시장 판도 변화 선봉…'가격·보안' 투트랙 공략", "더구루"),
):
    test_news = make(title,"업계 시장 전망 및 기존 기사 해설, 신규 본계약 확인 없음",source)
    assert watcher._is_oct15_market_noise(test_news), (title,source)
    assert base.score(test_news) == 0, (title,base.score(test_news))

# An actual explicit newly signed order headline must not be removed just
# because a broker simultaneously lifts its target price.
confirmed_ess_order = make(
    "삼성SDI, 일본 고객 신규 ESS 공급계약 체결…목표가 상향",
    "삼성SDI 신규 일본 ESS 공급계약을 체결했다고 밝혔다.",
    "연합뉴스",
)
assert not watcher._is_oct15_market_noise(confirmed_ess_order)

# The 2027 Q1 CLOiD plan and general CES event aren't new statuses in
# the six targeted commercial/approval lanes.
for story in (
    "LG전자 2027년 초 CLOiD 이족보행 휴머노이드 공개 예정",
    "CES 2027 AI 휴머노이드 전시 키워드",
    "Boston Dynamics Atlas 외부 고객 신규 정식 공급계약",
):
    assert watcher._oct15_group(story) == '', story

# Future approval, closing, or actual measured throughput must be separate
# semantic keys from the first-stage milestones.
future_oct15 = [
    (
        "Agility Robotics Churchill Capital Corp XI shareholders approved the merger proposal",
        "Agility Robotics","agility_spac_2026",
        "주주총회 승인·거래종결 대기",
    ),
    (
        "Agility Robotics Churchill XI business combination completed AGLT trading started",
        "Agility Robotics","agility_spac_2026",
        "실제 합병 거래종결 공식확인",
    ),
    (
        "레인보우로보틱스 RB-Y1 FCC DoW 조건부 승인 발급",
        "DoW","rainbow_fcc_compliance",
        "조건부 승인 공식확인",
    ),
    (
        "신젠전동 新剑传动 A사 첫 양산 출하 확인",
        "新剑传动","xinjian_prs_ipo",
        "첫 양산 출하 공식확인",
    ),
    (
        "유니켐 Loomia 거래 종결 완료",
        "유니켐","unichem_loomia_acquisition",
        "인수 종결 공식확인",
    ),
    (
        "Boston Dynamics Atlas 실제 1시간 실측 달성",
        "Boston Dynamics","atlas_protoops_build",
        "실제 달성",
    ),
]
for title,source,expected_group,expected_suffix in future_oct15:
    it = make(title,title,source)
    g,score,cat,semantic = classify(it)
    assert g == expected_group and score >= 11, (title,g,score,cat)
    assert expected_suffix in cat, (title,cat)
    assert semantic not in oct15_keys, (title,'new stage silenced as duplicate')

# DoW's general conditional-approval process is not company approval.
dow_process_only = make(
    "레인보우로보틱스 RB-Y1 FCC DoW conditional approval process",
    "DoW opened general conditional approval process, not granted RB-Y1",
    "DoW",
)
dg,ds,dc,dk = classify(dow_process_only)
assert dg == 'rainbow_fcc_compliance' and ds < 11,(dg,ds,dc)
# A material announcement of other Atlas robot business must NOT get
# swallowed by the specialized prototype-assembly stage.
atlas_real_customer_order = make(
    "Boston Dynamics Atlas receives first binding customer robot order",
    "Boston Dynamics Atlas production robots are ordered by external buyer.",
    "Boston Dynamics",
)
assert watcher._oct15_group(atlas_real_customer_order['title']) == ''

future_now = base.NOW
try:
    base.NOW = dt.datetime(2026,10,22,12,0,tzinfo=dt.timezone.utc)
    for event_key in oct15_expected:
        assert watcher.query_news(watcher.ROBOT_OCT15_PREFIX + event_key) == []
finally:
    base.NOW = future_now



# 53) No generic quantity badges. In particular, 6~12개월 is
# a time horizon, not 12 products; sites and targets aren't shipments.
for fake_qty_sentence in (
    "공급망 지연은 6~12개월 위험구간",
    "내년 1시간 목표, 6~12개월 내 수율 검증",
    "9개 시설 가동 → 2027년 25개 시설 목표",
    "2028년 로봇 1,000대 주문 확보 목표",
):
    assert watcher.qty._unknown_block(fake_qty_sentence) is None, (
        "generic quantity block reintroduced", fake_qty_sentence
    )
assert watcher.qty.QTY_RE.findall("6~12개월") == [], (
    "12 months parsed as 12 individual parts",
    watcher.qty.QTY_RE.findall("6~12개월"),
)
assert watcher.qty.QTY_RE.findall("15개소") == [], "15 sites suffix is not 15 products"
assert watcher.qty.QTY_RE.findall("9개 시설") == [('9','개')], (
    "raw unit lexer still detects true explicit counts, but must not call"
    " them confirmed shipments"
)
assert watcher.qty.QTY_RE.findall("254MW 1000MWh 1GWh 1GW") == [
    ('254','MW'),('1','GW')
], "power MW is not energy MWh"

oct15_qty_correction = watcher.query_news(
    watcher.ROBOT_OCT15_PREFIX + 'alert224225_quantity_correction'
)
if base.NOW.astimezone(base.KST).date() <= dt.date(2026,10,20):
    assert len(oct15_qty_correction) == 1, oct15_qty_correction
    qi=oct15_qty_correction[0]
    qg,qs,qc,qk=classify(qi)
    assert qg=='alert_quality_qty_224225' and qs>=11, (qg,qs,qc)
    assert '224·225' in qc and '수량' in qc, qc
    assert '12개월' in qi['description'] and '12개' in qi['description']
    assert '목표' in base.meaning(qc)
    assert qk not in oct15_keys[:-1], 'quantity correction must be separate event'



# 62) October 15/16 status changes: ESS actual government classification
# guidance, BRILS manufacturing PLAN vs production and signed orders,
# Hyundai RX internal strategy team, LG robotics SW subteam, and already
# released ROBOTIS software (do not turn future hardware plan into a launch).
new_event_specs = (
    ('ess_outdoor_guideline','ess_outdoor_policy','official_guideline',
     '기후부 · 옥외형 ESS 분류지침 전국 배포'),
    ('brils_us_amr_production_plan','brils_us_localization','reported_local_production_plan',
     '브릴스 · 미시간 AMR 현지 생산체계 추진'),
    ('hyundai_rx_strategy_team','hyundai_robot_rx_team','company_sourced_team_report',
     '현대차그룹 · RX사업전략팀 신설'),
    ('lg_robot_software_platform_team','lge_robot_sw_platform','industry_sourced_sw_team',
     'LG전자 · 로봇 소프트웨어 플랫폼 조직 신설 보도'),
)
keys = set()
for event_id, expected_group, expected_stage, expected_category in new_event_specs:
    samples = _historical_one_shot_query(watcher.ROBOT_OCT16_PREFIX + event_id)
    assert len(samples) == 1, (event_id,samples)
    item = samples[0]
    assert item.get('published') is None, "Date-only press coverage needs no fabricated hour"
    group, points, cat, digest = classify(item)
    assert group == expected_group and points >= 11, (event_id,group,points)
    assert cat == expected_category, (event_id,cat)
    assert item['oct16_stage'] == expected_stage
    assert digest not in keys, (event_id,'dedup keys unexpectedly overlap')
    keys.add(digest)
    assert base.meaning(cat), (event_id,'empty meaning')
    assert base.risk(cat), (event_id,'empty risk')
    visible = f"{item['title']} {item['description']}"
    assert base.category(visible,base.topic_group(visible)) == cat, (event_id,'render loses source evidence')
    assert '원' in base.meaning(cat) if expected_group in {
        'ess_outdoor_policy','brils_us_localization'
    } else True
    assert watcher.qty._skip_quantity_enrichment(
        f'<b>1. {item["title"]}</b>\n<b>분류</b>  {cat}\n'
        '3개월 7,000만원, 100개 사업장, 2028년 로봇 예정 100대'
    ), ('false "confirmed product quantity" added to policy/organization', event_id)

ess_doc = watcher.ROBOT_OCT16_EVENTS['ess_outdoor_guideline']['description']
assert '공작물' in ess_doc and '가설건축물' in ess_doc and '건축물' in ess_doc
assert '7,000만원' in ess_doc and '3개월' in ess_doc
assert '국비' not in base.meaning('기후부 · 옥외형 ESS 분류지침 전국 배포').split('아닙니다')[1], (
    "Guideline should not be called subsidy"
)
assert 100*70_000_000 == 7_000_000_000, '100 * maximum KRW saving = 70eok upper bound'

b = watcher.ROBOT_OCT16_EVENTS['brils_us_amr_production_plan']['description']
assert '371만달러' in b and '1,504만달러' in b
assert '상반기' in b and '북미 누적' in b
assert int(3_710_000*1338.60) == 4_966_206_000
assert int(15_040_000*1338.60) == 20_132_544_000
assert '미공개' in b and '협의 중' in b
assert 'Navigation' in b and 'FMS' in b
assert '장기 유지보수' not in b or '잠재' in b

brils_reprint = make(
    '브릴스, 미시간 미국 AMR 현지 생산 체제 구축 추진',
    '브릴스 BRILS USA Michigan 법인에서 저상형 AMR 현지 생산을 추진한다. '
    '미국 고객사 공급은 협의 중이고 첫 출하는 미확정이다.',
    '이데일리',
)
bg, bs, bc, bk = classify(brils_reprint)
brils_original = _historical_one_shot_query(
    watcher.ROBOT_OCT16_PREFIX + 'brils_us_amr_production_plan'
)[0]
assert bg == 'brils_us_localization' and bs >= 11, (bg,bs,bc)
assert bk == base.key(brils_original), 'Same US-production PLAN must not resend from another paper'

brils_plan_only = make(
    '브릴스, 미시간 미국 AMR 현지 생산 검토 중',
    '브릴스 BRILS USA 미시간 AMR 로봇 현지 생산은 아직 추진 중.',
    '광고블로그',
)
pg, ps, pc, pk = classify(brils_plan_only)
assert pg == 'brils_us_localization' and ps < 11, (pg,ps,pc)

brils_real_start = make(
    '브릴스, 미국 실제 AMR 생산 개시 공식 확인',
    '브릴스는 미시간 BRILS USA AMR 미국 실제 생산 개시를 공식 발표했다. '
    '생산 첫 물량을 실제 검수했다고 밝혔다.',
    '브릴스',
)
rg, rs, rc, rk = classify(brils_real_start)
assert rg == 'brils_us_localization' and rs >= 11 and rk != bk, (rg,rs,rc)
assert '실제 생산' in rc, rc

rx_press_copy = make(
    '현대차그룹 RX사업전략팀 신설 로봇 사업화 강화',
    '현대차그룹 미래사업전략실 산하 RX사업전략팀 신설, '
    'Atlas 2028년 HMGMA 투입은 기존 목표다.',
    '이데일리',
)
hg, hs, hc, hk = classify(rx_press_copy)
rx_original = _historical_one_shot_query(
    watcher.ROBOT_OCT16_PREFIX + 'hyundai_rx_strategy_team'
)[0]
assert hg == 'hyundai_robot_rx_team' and hs>=11 and hk==base.key(rx_original), (hg,hs,hk)
rx_official = make(
    '현대차그룹 RX사업전략팀 회사 공식 확인',
    '현대차그룹은 RX사업전략팀 조직 신설을 회사 공식 확인했다.',
    '현대자동차그룹',
)
rg2,rs2,rc2,rk2=classify(rx_official)
assert rg2=='hyundai_robot_rx_team' and rs2>=11 and rk2!=hk,(rg2,rs2,rc2)

lg_report_clone = make(
    'LG전자 로봇 소프트웨어 플랫폼 조직 신설',
    'LG전자 로봇 소프트웨어 플랫폼 조직을 신설하고 제어·학습 인력을 통합했다.',
    'ZDNet korea',
)
lg,ls,lc,lk=classify(lg_report_clone)
lg_original=_historical_one_shot_query(
    watcher.ROBOT_OCT16_PREFIX+'lg_robot_software_platform_team'
)[0]
assert lg=='lge_robot_sw_platform' and ls>=11 and lk==base.key(lg_original),(lg,ls,lk)
lg_official=make(
    'LG전자 로봇 소프트웨어 플랫폼 조직 회사 공식 확인',
    'LG전자는 로봇 소프트웨어 플랫폼 조직 신설을 회사 공식 확인했다.',
    'LG전자',
)
og,os,oc,ok=classify(lg_official)
assert og=='lge_robot_sw_platform' and os>=11 and ok!=lk,(og,os,oc)

robotis_open_older=make(
    '로보티즈 SW·HW 전면 개방 오픈소스 휴머노이드',
    '로보티즈 AI 사피엔스 소프트웨어 구동 코드는 이미 8월 공개됐고 '
    '하드웨어 설계도는 향후 공개 예정이라고 다시 설명했다.',
    'ZDNet korea',
)
rog,ros,roc,rok=classify(robotis_open_older)
assert rog=='robotis_open_source_baseline' and ros<11,(rog,ros,roc)
robotis_future_cad=make(
    'ROBOTIS AI 사피엔스 하드웨어 CAD 설계도 실제 공개 완료',
    'ROBOTIS AI 사피엔스 휴머노이드 하드웨어 CAD 설계도 실제 공개 완료. '
    '공식 GitHub 배포와 라이선스를 공개했다.',
    'ROBOTIS',
)
fg,fs,fc,fk=classify(robotis_future_cad)
assert fg=='robotis_hardware_release' and fs>=11, (fg,fs,fc)
robotis_media_cad=dict(robotis_future_cad,source='무명 유튜버')
mg,ms,mc,mk=classify(robotis_media_cad)
assert mg=='robotis_hardware_release' and ms<11, (mg,ms,mc)

# One-shot recovery expires, preventing future replay after dedup rotation.
now_saved=base.NOW
try:
    base.NOW=dt.datetime(2026,10,26,12,0,tzinfo=dt.timezone.utc)
    for event_id,_,_,_ in new_event_specs:
        assert watcher.query_news(watcher.ROBOT_OCT16_PREFIX+event_id)==[], event_id
finally:
    base.NOW=now_saved


# 63) Actual 2026-10-18 Telegram 233 artifact regression.
# A general ESS quarterly-earnings preview is not a signed order.
ess_outlook_title = make(
    'K배터리 3Q도 실적 청신호..美 ESS 분기 설치량 최대 지속 - 머니투데이',
    '올해 미국 ESS 설치 규모 확대와 K배터리의 실적 회복 기대감을 전했다.',
    '머니투데이',
)
eg,es,ec,ek=classify(ess_outlook_title)
assert es < 11, ('ESS general market outlook incorrectly promoted',eg,es,ec)
# A primary official metric release should not be prohibited just because
# it contains "ESS" or "quarter": it must be evaluated on its own evidence.
ess_factual_primary = make(
    'ESS 산업 3분기 확정 설치량 공식 발표',
    '공식 기관이 2026년 3분기 실제 ESS 설치 2GWh를 발표했다.',
    '미국 에너지정보청',
)
fg,fs,fc,fk=classify(ess_factual_primary)
assert not watcher.ESS_CONCRETE_NEW_EVENT.search(ess_outlook_title['title'])

corrected = watcher.query_news(
    watcher.ROBOT_OCT16_PREFIX + 'telegram233_quality_correction'
)
if base.NOW.astimezone(base.KST).date() <= dt.date(2026,10,25):
    assert len(corrected)==1,corrected
    cg,cs,cc,ck=classify(corrected[0])
    assert cg=='alert_quality_oct18' and cs>=11,(cg,cs,cc)
    assert 'Telegram 233' in cc and '정정' in cc,cc
    assert '엔비디아' in base.meaning(cc)
    assert '철회' in base.meaning(cc)
    assert watcher.qty._unknown_block('6~12개월 12개 제품이라고 오해') is None
    assert '새 계약' not in corrected[0].get('title','')


# 64) Micron EIM edge-inference-memory R&D: 10/16 executive quote is a
# new R&D lane, not a 2028 mass-production commitment or a Robot OEM order.
micron_eim_report = make(
    '마이크론 휴머노이드용 EIM 엣지 추론 메모리 LPDDR 개발',
    '이철 마이크론 상무는 SEDEX 2026에서 EIM Edge Inference Memory 개발과 '
    '주요 고객 요구사항 논의를 설명했다. 로봇용 LPDDR6를 논리 칩 위 적층한다. '
    '2028년 하반기 양산은 회사 공식 일정이 아니라 업계 예상이다. '
    '대역폭·지연시간·전력·수율·고객 양산 계약은 미공개다.',
    '디일렉',
)
micron_eim_report['link'] = watcher.MICRON_EIM_SOURCE_URL
eg, es, ec, ek = classify(micron_eim_report)
assert eg == 'micron_eim_edge' and es >= 11, (eg, es, ec)
assert ec == '마이크론 EIM · SEDEX 경영진 개발·고객 협의 보도', ec
assert '2028년 하반기' in base.meaning(ec)
assert '회사 공식 일정이 아닌 업계 예상' in base.meaning(ec)
assert 'PIM' in base.meaning(ec) and 'HBM' in base.meaning(ec)
assert '200억원' in base.meaning(ec)
assert '휨' in base.risk(ec) and '검사 시간' in base.risk(ec)
rendered_eim = micron_eim_report['title']+' '+micron_eim_report['description']
assert base.category(rendered_eim,base.topic_group(rendered_eim)) == ec
assert '회사 명의 EIM 시제품' in base.verification(micron_eim_report,eg,rendered_eim)

eim_republished = dict(
    micron_eim_report,
    title='美光 Micron EIM Edge Inference Memory 로봇용 개발 협의',
    description='마이크론 EIM Edge Inference Memory 논리 칩 위 LPDDR 적층 개발. '
                '이철 상무 SEDEX에서 2028년 양산 예상 보도.',
)
dg, ds, dc, dk = classify(eim_republished)
assert dg == eg and ds >= 11 and dk == ek, (dg,ds,dc,dk)

# Only a source on Micron's own domain may raise the official evidence tier.
eim_official_dev = make(
    'Micron official EIM Edge Inference Memory robot LPDDR development announced',
    'Micron officially confirms EIM edge inference memory research for humanoid '
    'robots with LPDDR6 on a logic die.',
    'Micron',
)
eim_official_dev['link'] = 'https://www.micron.com/about/press/eim-research-example'
og, os, oc, ok = classify(eim_official_dev)
assert og == eg and os >= 11 and ok != ek, (og,os,oc)
assert oc == '마이크론 EIM · 개발 공식 확인', oc

eim_official_spoof = dict(eim_official_dev,link='https://news.example.com/micron-eim')
sg, ss, sc, sk = classify(eim_official_spoof)
assert sg == eg and ss < 11, (sg,ss,sc)
assert sk != ok

eim_official_samples = make(
    'Micron EIM robot LPDDR customer samples shipped',
    'Micron EIM edge inference memory customer samples shipped for robot '
    'manufacturer qualification and system validation.',
    'Micron',
)
eim_official_samples['link'] = 'https://www.micron.com/about/press/eim-robot-samples-example'
pg, ps, pc, pk = classify(eim_official_samples)
assert pg == eg and ps >= 11 and pk not in {ek,ok}, (pg,ps,pc)
assert pc == '마이크론 EIM · 고객 시제품 제공·검증', pc

eim_official_sop = make(
    'Micron EIM robot LPDDR mass production started',
    'Micron EIM Edge Inference Memory LPDDR production started, '
    'with commercial shipments begun for physical AI robots.',
    'Micron',
)
eim_official_sop['link'] = 'https://www.micron.com/about/press/eim-started-example'
rg, rs, rc, rk = classify(eim_official_sop)
assert rg == eg and rs >= 11 and rk not in {ek,ok,pk}, (rg,rs,rc)
assert rc == '마이크론 EIM · 실제 양산·상업 출하', rc

eim_production_rumor = dict(eim_official_sop,source='익명 투자 블로그')
bg, bs, bc, bk = classify(eim_production_rumor)
assert bg == eg and bs < 11,(bg,bs,bc)

eim_hbm_unrelated = make(
    'Micron HBM market price rises amid AI datacenter shortage',
    'Micron server HBM price rises; no EIM product development or humanoid '
    'robot edge inference memory announcement.',
    '반도체 테마 뉴스',
)
ug, us, uc, uk = classify(eim_hbm_unrelated)
assert us < 11, ('HBM-price story with a negative EIM mention must stay silent',ug,us,uc)

# Do not turn technology parameters (1-2 billion weights; 200GB; 4TB)
# into "12개 확인 물량" or phantom $ / KRW device pricing.
assert watcher.qty._skip_quantity_enrichment(
    '<b>1. 마이크론 EIM 로봇 메모리</b>\n'
    '<b>분류</b>  마이크론 EIM · SEDEX 경영진 개발·고객 협의 보도\n'
    'AI 모델 10억~20억 개 파라미터·200GB LPDDR·4TB 스토리지'
)

recovery = watcher.query_news(watcher.MICRON_EIM_RECOVERY)
if base.NOW.astimezone(base.KST).date() <= dt.date(2026,10,24):
    assert len(recovery)==1,recovery
    news=recovery[0]
    assert news['link'] == watcher.MICRON_EIM_SOURCE_URL
    assert news['source'] == '디일렉' and news['published'] is None
    eg2,es2,ec2,ek2 = classify(news)
    assert eg2==eg and es2>=11 and ek2==ek,(eg2,es2,ec2,ek2)
    assert base.category(news['title']+' '+news['description'],eg2)==ec
    assert '2028년 하반기' in news['description']
    assert '업계 예상' in news['description']
    assert 'EIM 자체의 시제품' in news['description']
    assert '카운터포인트리서치 전망' in news['description']

saved_micron_now=base.NOW
try:
    base.NOW=dt.datetime(2026,10,25,0,0,tzinfo=dt.timezone.utc)
    assert watcher.query_news(watcher.MICRON_EIM_RECOVERY)==[],(
        'dated 10/16 R&D report must not replay after 10/24 expiry'
    )
finally:
    base.NOW=saved_micron_now

# Broad political productivity rhetoric and technology-theme roundups
# cannot become manufacturing, shipment or customer-order signals.
musk_debt_comment=make(
    'Elon Musk says AI and robots can fix national debt; DOGE failed',
    'Axios Walter Isaacson podcast Elon Musk argues AI and robotics '
    'productivity can solve the US national debt, no newly signed '
    'Optimus robot supply order or production numbers.',
    'Axios',
)
g,s,c,k=classify(musk_debt_comment)
assert g!='micron_eim_edge' and s < 11,(g,s,c)

generic_solidstate=make(
    '전고체 배터리 잡는 자가 車·로봇·ESS 주도…시장 선점 경쟁 치열',
    '삼성SDI·LG에너지솔루션·SK온 기존 로봇 배터리 샘플 개발과 '
    '전고체 기술 경쟁을 설명하나 신규 계약·양산 발표는 없다.',
    '국민일보',
)
g,s,c,k=classify(generic_solidstate)
assert g!='micron_eim_edge' and s < 11,(g,s,c)

# Filtering a generic competition article must not prevent genuine, newly
# signed battery supply agreements with an explicit concrete contract.
solid_state_real_contract = dict(
    generic_solidstate,
    title='삼성SDI 전고체 배터리 최초 공급계약 체결로 시장 선점 경쟁',
)
assert not watcher._is_generic_ess_demand_story(solid_state_real_contract), (
    'market-noise guard must not block explicit first signed awards'
)


# 60) 2026-10-19 DIGITIMES Chinese BESS-system-integrator market exit:
# anonymous supply-chain interview is not verified company closure.
cn_ess_retreat = watcher.query_news(watcher.CN_ESS_US_RETREAT_ID)
if base.NOW.astimezone(base.KST).date() <= dt.date(2026,10,23):
    assert len(cn_ess_retreat)==1, cn_ess_retreat
    cr=cn_ess_retreat[0]
    assert cr['source']=='DIGITIMES'
    assert '0000771701_AKR6XDK313NXUP0KYL64J' in cr['link']
    assert cr['published']=='2026-10-18T19:00:00+00:00', cr
    cg,cs,cc,ck=classify(cr)
    assert cg=='china_ess_us_exit_report' and cs>=11, (cg,cs,cc)
    assert cc=='미국 ESS 공급망 · 중국계 시스템업체 집단 철수설 보도',cc
    render=cr['title']+' '+cr['description']
    assert base.category(render,base.topic_group(render))==cc
    assert '미확인' in cr['title'] or '철수설' in cr['title']
    assert '유료 본문 직접 열람 실패' in base.verification(cr,cg,render)
    assert '55%' in base.risk(cc) and '75%' in base.risk(cc)
    assert '개별 업체 철수 공시' in base.meaning(cc)
    assert re.search(r'과거|기존',base.meaning(cc)) and '7.5GWh' in base.meaning(cc)
    assert watcher.qty._skip_quantity_enrichment(
        '<b>1. 미국 ESS 공급망</b>\n'
        '<b>분류</b>  미국 ESS 공급망 · 중국계 시스템업체 집단 철수설 보도\n'
        'DIGITIMES 2026; 2025년 ESS 1.5조원 7.5GWh'
    ),'must not mislabel previous ESS contracts as fresh confirmed quantities'

cn_ess_rewrite=make(
    '중국계 ESS 기업 미국 철수설 DIGITIMES 재인용',
    'DIGITIMES 2026-10-19 중국 ESS 미국 집단 철수설이 주식 테마로 재확산.',
    '시장 테마 뉴스'
)
rg,rs,rc,rk=classify(cn_ess_rewrite)
assert rg=='china_ess_us_exit_report' and rs<11,(rg,rs,rc)
if cn_ess_retreat:
    assert rk==ck, 'reprints cannot create an independent retreat event'

cn_ess_unrelated=make(
    'Sungrow inverter sales grow in Europe',
    'European ESS battery storage growth with no US market exit confirmation',
    'Sungrow'
)
ug,us,uc,uk=classify(cn_ess_unrelated)
assert us<11,(ug,us,uc)

# Hypothetical future CATL company announcement, not an observed Oct-19 fact.
catl_official_exit=make(
    'CATL 中国 ESS 美国 业务退出',
    'CATL 中国 ESS 美国 业务美国 ESS 事业 业务 已退出. '
    'CATL 중국 ESS 미국 사업 철수 완료를 회사가 발표했다고 가정한다.',
    'CATL'
)
catl_official_exit['link']='https://www.catl.com/en/news/hypothetical-exit'
eg,es,ec,ek=classify(catl_official_exit)
assert eg=='china_ess_us_exit_report' and es>=11,(eg,es,ec)
assert ec=='미국 ESS 공급망 · 중국계 개별업체 철수 공식확인',ec
assert '별도 상위 단계' in base.meaning(ec)
if cn_ess_retreat:
    assert ek!=ck,'actual company shutdown must be separate upgrade'

fake_origin=dict(catl_official_exit,link='https://www.catl.com.fake-site.example/news')
fg,fs,fc,fk=classify(fake_origin)
assert fg==eg and fs<11, (fg,fs,fc)

untrusted_copy=dict(catl_official_exit,source='증시 테마 뉴스')
sg,ss,sc,sk=classify(untrusted_copy)
assert sg==eg and ss<11,(sg,ss,sc)

denial=dict(catl_official_exit)
denial['description']+=' 하지만 CATL은 미국 ESS 사업 철수 부인 공식 확인.'
dg,ds,dc,dk=classify(denial)
assert dg==eg and ds<11,(dg,ds,dc)

old_cn_ess_now=base.NOW
try:
    base.NOW=dt.datetime(2026,10,24,0,0,tzinfo=dt.timezone.utc)
    assert watcher.query_news(watcher.CN_ESS_US_RETREAT_ID)==[],(
        'DIGITIMES one-off story must expire instead of replaying'
    )
finally:
    base.NOW=old_cn_ess_now


# 76) 2026-09 WORLDWIDE GRID-SCALE BESS commissioning is a monthly
# measured operational statistic (not forecast, cell sales, AI-DC only).
bess_sep = make(
    "Benchmark Mineral Intelligence: September 2026 global grid-scale BESS 20.4GWh commissioned",
    "Benchmark Mineral Intelligence reported worldwide grid-scale BESS actual "
    "commissioned installations in September 2026 of 20.4GWh, up 61% YoY; "
    "2026 YTD commissioned installations are 208GWh, up 43%. "
    "China more than 12GWh and Europe YTD 22GWh.",
    "Energy-Storage.News",
)
bg,bs,bc,bk = classify(bess_sep)
assert bg == 'global_bess_commissioned' and bs >= 11,(bg,bs,bc)
assert bc == '글로벌 계통용 BESS · 2026년 9월 신규 가동량',bc
assert '20.4GWh' in base.meaning(bc) and '208GWh' in base.meaning(bc)
assert '한 국' not in base.meaning(bc)
assert '화재' not in base.risk(bc) or '열폭주' in base.risk(bc)
assert 'KETEP' not in base.verification(bess_sep,bg,bess_sep['title']) or \
       '한국에너지기술평가원' in base.verification(bess_sep,bg,bess_sep['title'])
assert watcher._bess_bmi_period(bess_sep['title']+' '+bess_sep['description'])=='2026-09'
assert watcher._bess_bmi_period('2026년 9월 계통용 BESS 가동')=='2026-09'
bess_reprint = make(
    "2026년 9월 전 세계 계통용 BESS 20.4GWh 신규 가동",
    "Benchmark Mineral Intelligence 집계 2026년 9월 세계 전력망 계통용 BESS "
    "실제 신규 가동 20.4GWh, 1~9월 누적 208GWh, 전년 대비 61%/43%.",
    "한국에너지기술평가원",
)
rg,rs,rc,rk=classify(bess_reprint)
assert rg==bg and rs>=11 and rk==bk,(rg,rs,rc,rk)
bess_noise = dict(bess_sep,source='테마 주식 블로그')
ng,ns,nc,nk=classify(bess_noise)
assert ng==bg and ns<11,(ng,ns,nc)
bess_next_month=make(
    "October 2026 global grid-scale BESS 18.7GWh commissioned",
    "Benchmark Mineral Intelligence says worldwide grid-scale BESS installed "
    "18.7GWh in October 2026 and YTD reaches 226.7GWh, up 20% YoY.",
    "Energy-Storage.News",
)
fg,fs,fc,fk=classify(bess_next_month)
assert fg==bg and fs>=11 and fk!=bk,(fg,fs,fc,fk)
assert fc=='글로벌 계통용 BESS · 이후 월간 실제 가동량',fc

# September 2026 quantity validation: decimal GWh not GW, no signed
# Samsung SDI or LG Energy Solution purchase contract implied.
assert 20.4*1_000_000==20_400_000
assert 208*1_000_000==208_000_000
assert round(20.4/1.61,2)==12.67  # imputed prior-year month, approximate
assert round(208/1.43,2)==145.45  # imputed prior-year YTD, approximate

recovered_bess = watcher.query_news(watcher.BESS_SEP26_RECOVERY)
if base.NOW.astimezone(base.KST).date() <= dt.date(2026,10,23):
    assert len(recovered_bess)==1,recovered_bess
    rec = recovered_bess[0]
    assert rec['source']=='Energy-Storage.News' and rec['published'] is None,rec
    gb,sc,cat,k=classify(rec)
    assert gb==bg and sc>=11 and k==bk,(gb,sc,cat)
    assert cat==bc,cat
    text=rec['title']+' '+rec['description']
    assert base.category(text,gb)==bc
    assert '한국에너지기술평가원' in base.verification(rec,gb,text)
    assert watcher.qty._skip_quantity_enrichment(
        '<b>1. 글로벌 계통용 BESS</b>\n'
        '<b>분류</b> 글로벌 계통용 BESS · 2026년 9월 신규 가동량\n'
        '20.4GWh·208GWh 실제 가동량'
    ),"BESS GWh may not become phantom 4GW or unit count"

old_bmi_now=base.NOW
try:
    base.NOW=dt.datetime(2026,10,24,12,0,tzinfo=dt.timezone.utc)
    assert watcher.query_news(watcher.BESS_SEP26_RECOVERY)==[]
finally:
    base.NOW=old_bmi_now

# 77) Samsung SDI 21700 LFP BBU 2026-09-29 product exhibit was an
# existing baseline. 2026-10-18 media 2027 Q2 schedule is a plan,
# NOT 2027 production or an official customer agreement.
sdi_bbu_media=make(
    "삼성SDI, AI서버 BBU용 21700 LFP 2027년 2분기 양산 추진",
    "아시아투데이는 삼성SDI가 말레이시아 스름반 2공장에 21700 원통형 LFP BBU "
    "극판 설비를 설치하는 방안을 추진하고 이르면 2027년 2분기 양산 예정이라고 보도했다.",
    "아시아투데이",
)
bgu,bsc,bcat,bkey=classify(sdi_bbu_media)
assert bgu=='sdi_lfp_bbu' and bsc<11,(bgu,bsc,bcat)
assert bcat.endswith('기존 제품·2027년 2분기 보도 계획'),bcat

sdi_bbu_old_company=make(
    "삼성SDI 서버 BBU용 21700 원통형 LFP 첫 제품 공개",
    "삼성SDI가 싱가포르 데이터센터 월드 아시아에서 BBU용 21700 원통형 "
    "리튬인산철 LFP 셀을 공개했다.",
    "삼성SDI",
)
gsc,ssc,ccc,kcc=classify(sdi_bbu_old_company)
assert gsc=='sdi_lfp_bbu' and ssc<11,(gsc,ssc,ccc)

sdi_bbu_future=make(
    "삼성SDI BBU LFP 21700 원통형 배터리 양산 시작",
    "삼성SDI는 데이터센터 BBU용 LFP 21700 원통형 셀 "
    "양산 시작을 공식 발표했다.",
    "삼성SDI",
)
gfu,sfu,cfu,kfu=classify(sdi_bbu_future)
assert gfu=='sdi_lfp_bbu' and sfu>=11,(gfu,sfu,cfu)
assert cfu=='삼성SDI LFP BBU · 양산·첫 출하 공식 확인',cfu
assert kfu!=bkey
sdi_bbu_media_fake=dict(sdi_bbu_future,source="증시 테마 언론")
gf,sf,cf,kf=classify(sdi_bbu_media_fake)
assert gf=='sdi_lfp_bbu' and sf<11,(gf,sf,cf)


# 78) Run #664 / Telegram 238 item 1 was a price ONLY headline.
# The original regex missed "8%대 올라". The final HTML guard must also
# remove such a block while preserving item 2 (measured BMI BESS demand).
bad_stock_238 = make(
    "삼성SDI 주가 장중 8%대 올라, ESS 수요 증가 기대감에 2차전지주 강세",
    "주가 움직임과 ESS 업황 기대감만 보도하고 신규 계약이나 실적 공시는 없다.",
    "비즈니스포스트",
)
sg,ss,sc,sk = classify(bad_stock_238)
assert ss < 11, (sg,ss,sc)
assert watcher._is_stock_reaction_only(bad_stock_238), "8%대 올라 must be filtered"
assert not watcher._is_stock_reaction_only({
    "title":"삼성SDI 신규 ESS 공급계약 체결 사실 발표",
    "source":"비즈니스포스트",
}),"New contracted deal without share-price headline is not market reaction"

fake_alert_html=(
    '🚨 <b>피지컬AI·로봇 공급망 구조 변화 감지</b>\n'
    '<b>신규 고신호 2건</b>\n'
    '━━━━━━━━━━━━━━━━━━\n\n'
    '<b>1. 삼성SDI 주가 장중 8%대 올라, ESS 수요 증가 기대감에 2차전지주 강세</b>\n'
    '<b>분류</b>  ESS 배터리·한국 공급망\n'
    '──────────────────\n\n'
    '<b>2. 글로벌 계통용 BESS 9월 실제 가동 20.4GWh</b>\n'
    '<b>분류</b>  글로벌 계통용 BESS · 2026년 9월 신규 가동량\n'
    '──────────────────\n'
    '<b>판정 기준</b>  실제 사업만 알림.'
)
filtered=watcher._drop_stock_price_sections(fake_alert_html)
assert '주가 장중' not in filtered,filtered
assert '<b>신규 고신호 1건</b>' in filtered,filtered
assert '<b>1. 글로벌 계통용 BESS 9월 실제 가동' in filtered,filtered
assert '<b>2. 글로벌 계통용 BESS' not in filtered,filtered
assert '<b>판정 기준</b>' in filtered,filtered
bad_alone = fake_alert_html.split('──────────────────')[0] + (
    '──────────────────\n<b>판정 기준</b>  실제 사업만 알림.'
)
assert watcher._drop_stock_price_sections(bad_alone) == '', \
    'A sole stock-only signal must not reach Telegram'

correct_238=watcher.query_news(watcher.ALERT238_CORRECTION_ID)
if base.NOW.astimezone(base.KST).date()<=dt.date(2026,10,24):
    assert len(correct_238)==1,correct_238
    correction=correct_238[0]
    cg,css,cc,ck=classify(correction)
    assert cg=='alert_quality_238' and css >= 11,(cg,css,cc)
    assert cc=='알림 품질 정정 · Telegram 238번 주가 반응 오탐',cc
    assert ck!=bk, 'Correction cannot collide with September global actuals'
    assert 'message_id=238' in base.meaning(cc)
    assert '오탐' in base.clean_title(correction['title'],correction['source'])
    assert 'Run #664' in base.verification(correction,cg,
        correction['title']+' '+correction['description'])
    corrected_html=(
        '🚨 <b>피지컬AI·로봇 공급망 구조 변화 감지</b>\n'
        '<b>신규 고신호 1건</b>\n'
        '━━━━━━━━━━━━━━━━━━\n\n'
        '<b>1. 정정: Telegram 238번 삼성SDI 주가 반응 오탐 제외</b>\n'
        '──────────────────\n<b>판정 기준</b>  실제 사업만 알림.'
    )
    assert watcher._drop_stock_price_sections(corrected_html) == corrected_html
old_238_now=base.NOW
try:
    base.NOW=dt.datetime(2026,10,25,10,0,tzinfo=dt.timezone.utc)
    assert watcher.query_news(watcher.ALERT238_CORRECTION_ID)==[]
finally:
    base.NOW=old_238_now


# 2026-10-19: Sam Altman first-person Fortune interview was published on
# 2026-09-15. The October article is a RETROSPECTIVE rediscovery, not a
# newly announced 2027 product launch, customer contract, or demo video.
_openai_ceo = make(
    "OpenAI humanoid robot 2027 cool demo Sam Altman interview",
    "OpenAI CEO Sam Altman said in the Fortune interview on Sept 15 2026: "
    "we will definitely do a humanoid and we should have a cool demo in "
    "2027. Widespread public robots will take years longer. This is a "
    "2027 demonstration goal, not commercialization.",
    "Fortune",
)
oa_g,oa_s,oa_c,oa_k = classify(_openai_ceo)
assert oa_g == 'openai_own_humanoid' and oa_s >= 11, (oa_g,oa_s,oa_c)
assert oa_c == 'OpenAI 휴머노이드 · 2027년 시연 목표 CEO 인터뷰',oa_c
assert '9/15' not in base.meaning(oa_c) or '2027' in base.meaning(oa_c)
assert '2027년' in base.risk(oa_c) and '목표' in base.risk(oa_c)
assert '회사 신규' not in base.meaning(oa_c) or '10/19' in base.meaning(oa_c)

_openai_second_headline = make(
    "OpenAI Sam Altman 2027 humanoid demo",
    "Sam Altman Fortune confirms we will definitely do a humanoid, "
    "a great demo is expected in 2027; no confirmed robot order.",
    "Fortune",
)
oa2_g,oa2_s,oa2_c,oa2_k = classify(_openai_second_headline)
assert oa2_g==oa_g and oa2_s>=11 and oa2_k==oa_k,(oa2_g,oa2_s,oa2_k)

_openai_second_hand = dict(_openai_ceo,source='DigitalToday')
osh_g,osh_s,osh_c,osh_k=classify(_openai_second_hand)
assert osh_g==oa_g and osh_s<11,(osh_g,osh_s,osh_c)

_openai_jobs = make(
    "OpenAI robotics actuator motor manufacturing jobs",
    "OpenAI is hiring actuator and robotics motor engineers and prototype "
    "testing workers for an unannounced humanoid program.",
    "OpenAI",
)
oj_g,oj_s,oj_c,oj_k=classify(_openai_jobs)
assert oj_g==oa_g and oj_s<11,(oj_g,oj_s,oj_c)

_openai_goal_reprint = make(
    "OpenAI 2027 humanoid demo likely in the future",
    "OpenAI is targeting a 2027 humanoid demo but no physical demo "
    "has yet been completed.",
    "OpenAI",
)
og_g,og_s,og_c,og_k=classify(_openai_goal_reprint)
assert og_g==oa_g and og_s<11,(og_g,og_s,og_c)

_openai_demo_done = make(
    "OpenAI publicly demonstrated its own humanoid robot",
    "OpenAI publicly demonstrated its own humanoid robot with an "
    "independently observable manipulation task and completed demo.",
    "OpenAI",
)
od_g,od_s,od_c,od_k=classify(_openai_demo_done)
assert od_g==oa_g and od_s>=11,(od_g,od_s,od_c)
assert od_c=='OpenAI 휴머노이드 · 실물 시연 완료 공식 확인',od_c
assert od_k!=oa_k,(od_k,oa_k)

_openai_paid_contract = make(
    "OpenAI humanoid signed paid supply contract",
    "OpenAI humanoid signed paid supply contract for real-world deployments.",
    "OpenAI",
)
oc_g,oc_s,oc_c,oc_k=classify(_openai_paid_contract)
assert oc_g==oa_g and oc_s>=11,(oc_g,oc_s,oc_c)
assert oc_c=='OpenAI 휴머노이드 · 실제 고객 유상계약 공식 확인',oc_c
assert len({oa_k,od_k,oc_k})==3

_roadster_theme = make(
    "Tesla flying Roadster means Optimus supply chain gains",
    "The flying Roadster prototype launched, so Optimus suppliers will "
    "benefit despite no confirmed robot parts order or robot shipment.",
    "BigGo Finance",
)
r_g,r_s,r_c,r_k = classify(_roadster_theme)
assert r_s < 11, "Roadster hype cannot create a humanoid supplier alert"

_dated = base.query_news(watcher.OPENAI_HUMANOID_RECOVERY)
if base.NOW.astimezone(base.KST).date() <= dt.date(2026,10,23):
    assert len(_dated)==1,_dated
    event=_dated[0]
    assert event['source']=='Fortune' and event['published'] is None
    assert event['link']==watcher.OPENAI_HUMANOID_FORTUNE_URL
    dg,ds,dc,dk=classify(event)
    assert dg==oa_g and ds>=11 and dc==oa_c and dk==oa_k,(dg,ds,dc,dk)
    ctext=f"{event['title']} {event['description']}"
    assert base.category(ctext,base.topic_group(ctext))==oa_c
    assert '9월 CEO 인터뷰' in base.clean_title(event['title'],event['source'])
    assert '9/15 Fortune' in base.verification(event,dg,ctext)
    assert '2026-09-01 Sources' in event['description']
    assert '2026-09-15 Fortune' in event['description']
    assert '2027년' in base.meaning(oa_c)
    assert watcher.qty._skip_quantity_enrichment(
        '<b>1. OpenAI 자체 휴머노이드</b>\n'
        '<b>분류</b>  OpenAI 휴머노이드 · 2027년 시연 목표 CEO 인터뷰\n'
        '27개 구인 직무와 2027년 시연 목표'
    ), 'recruitment numbers are not priced completed robots'
_old_openai_now=base.NOW
try:
    base.NOW=dt.datetime(2026,10,24,12,0,tzinfo=dt.timezone.utc)
    assert base.query_news(watcher.OPENAI_HUMANOID_RECOVERY)==[], (
        'historical OpenAI September claim cannot replay after recovery expiry'
    )
finally:
    base.NOW=_old_openai_now


# 90) BMW actual Shenyang high-voltage PACK assembly started Oct 15.
# Do NOT treat it as BMW cell-manufacturing SOP or a confirmed CATL
# Shenyang production-line supply contract.
bmw_pack=make(
    "BMW Gen6 Shenyang 46mm high-voltage battery pack series production begun",
    "BMW Group 2026-10-15 Shenyang Gen6 battery packs actual series production "
    "begun. Third battery assembly location after Debrecen and Irlbach. "
    "Battery cells supplied by partners; finished pack first customer delivery not announced.",
    "BMW Group",
)
bg,bs,bc,bk=classify(bmw_pack)
assert bg=='bmw_gen6_pack' and bs>=11,(bg,bs,bc)
assert bc=='BMW Gen6 · 선양 배터리팩 양산 공식 개시',bc
assert '원통형 셀 제조' in base.meaning(bc),base.meaning(bc)
assert '양산 공정' in base.meaning(bc),base.meaning(bc)
assert '용접부' in base.risk(bc),base.risk(bc)

bmw_pack_headline=make(
    "BMW Gen6 Shenyang 46mm battery pack started series production",
    "BMW Gen6 battery Shenyang begun series production based on "
    "the same official October 15 announcement.",
    "BMW Group",
)
bg2,bs2,bc2,bk2=classify(bmw_pack_headline)
assert bg2==bg and bs2>=11 and bk2==bk,(bg2,bs2,bc2,bk2)

bmw_pack_past_plan=make(
    "BMW Gen6 Shenyang 46mm battery factory plan",
    "BMW expects battery Gen6 factory assembly in Shenyang to start in the future.",
    "BMW Group",
)
pb,ps,pc,pk=classify(bmw_pack_past_plan)
assert pb==bg and ps<11,(pb,ps,pc)

bmw_pack_rumor=dict(bmw_pack,source='unverified blog')
rb,rs,rc,rk=classify(bmw_pack_rumor)
assert rb==bg and rs<11,(rb,rs,rc)

bmw_vehicle_actual=make(
    "BMW Gen6 Shenyang China iX3 first actual customer deliveries completed",
    "BMW Gen6 battery Shenyang China iX3 first customer deliveries completed "
    "after pack production began.",
    "BMW Group",
)
vg,vs,vc,vk=classify(bmw_vehicle_actual)
assert vg==bg and vs>=11 and vk!=bk,(vg,vs,vc,vk)
assert vc=='BMW Gen6 · 중국 신세대 전기차 실제 고객 인도',vc

bmw_backfill=base.query_news(watcher.BMW_GEN6_PACK_RECOVERY)
if base.NOW.astimezone(base.KST).date()<=dt.date(2026,10,26):
    assert len(bmw_backfill)==1,bmw_backfill
    br=bmw_backfill[0]
    assert br['source']=='BMW Group' and br['published'] is None
    xg,xs,xc,xk=classify(br)
    assert xg==bg and xs>=11 and xc==bc and xk==bk,(xg,xs,xc,xk)
    br_text=br['title']+' '+br['description']
    assert base.category(br_text,base.topic_group(br_text))==bc
    assert '배터리팩 양산 확정' in base.verification(br,xg,br_text)
    assert 'BMW가 원통형 배터리 셀 자체를' in br_text
    assert watcher.qty._skip_quantity_enrichment(
        '<b>BMW Gen6 · 선양 배터리팩 양산 공식 개시</b> 20GWh '
        '삼성SDI 4695 2개·2026년'
    ), 'gen6 pack capacity cannot be rendered as robot unit counts'

# JPM 50eok USD is ALREADY deployed cumulatively, not a fresh
# 50eok USD contract; 230bn finance/facilitate is not additive.
jpm_progress=make(
    "JPMorganChase SRI $5 billion equity invested first year",
    "JPMorganChase 2026-10-19 Security and Resiliency Initiative "
    "$5 billion equity deployed out of initial $10 billion target; "
    "$230 billion financed and facilitated. Initial program was $1.5 trillion in 2025.",
    "JPMorganChase",
)
jg,js,jc,jk=classify(jpm_progress)
assert jg=='jpm_sri_2026' and js>=11,(jg,js,jc)
assert jc=='JP모건 SRI · 50억달러 지분투자 누적 집행',jc
assert '신규 50억달러 발주' in base.meaning(jc),base.meaning(jc)
assert '305조9,759억원' in base.meaning(jc),base.meaning(jc)
assert '서로 다른 금액' in base.meaning(jc),base.meaning(jc)

jpm_press=make(
    "JPMorganChase SRI $5 billion deployed, $230 billion financed",
    "JPMorganChase Security and Resiliency Initiative already invested "
    "$5 billion in equity with $230 billion of financing arranged.",
    "Reuters",
)
pg,ps,pc,pk=classify(jpm_press)
assert pg==jg and ps>=11 and pk==jk,(pg,ps,pc,pk)

jpm_plan=make(
    "JPMorganChase SRI $10 billion equity investment plan",
    "JPMorganChase 2025 Security and Resiliency Initiative plans to invest "
    "$10 billion in strategic companies over a 10-year period.",
    "JPMorganChase",
)
bg0,bs0,bc0,bk0=classify(jpm_plan)
assert bg0==jg and bs0<11,(bg0,bs0,bc0)

jpm_rumor=make(
    "JPMorganChase SRI $5 billion in new robot-factory contracts",
    "JPMorganChase Security and Resiliency Initiative $5 billion invested "
    "and $230 billion financed claim from unknown theme blog.",
    "speculative theme blog",
)
rg0,rs0,rc0,rk0=classify(jpm_rumor)
assert rg0==jg and rs0<11,(rg0,rs0,rc0)

jpm_backfill=base.query_news(watcher.JPM_SRI_DEPLOYMENT_RECOVERY)
if base.NOW.astimezone(base.KST).date()<=dt.date(2026,10,26):
    assert len(jpm_backfill)==1,jpm_backfill
    jr=jpm_backfill[0]
    assert jr['source']=='JPMorganChase' and jr['published'] is None
    y_g,y_s,y_c,y_k=classify(jr)
    assert y_g==jg and y_s>=11 and y_c==jc and y_k==jk,(y_g,y_s,y_c,y_k)
    assert '기존 계획' in jr['description']
    assert '서로 다른' in base.meaning(jc)
    assert watcher.qty._skip_quantity_enrichment(
        '<b>JP모건 SRI · 50억달러 지분투자 누적 집행</b>\n'
        '10개 기업, 100억달러 계획·2,300억달러 금융주선'
    ), 'equity tally cannot become hardware shipment volume'

# Cumulative records should not be replayed after the bounded recovery
# window, even when dedup state later rotates.
_saved_bmw_jpm_now=base.NOW
try:
    base.NOW=dt.datetime(2026,10,27,12,0,tzinfo=dt.timezone.utc)
    assert base.query_news(watcher.BMW_GEN6_PACK_RECOVERY)==[]
    assert base.query_news(watcher.JPM_SRI_DEPLOYMENT_RECOVERY)==[]
finally:
    base.NOW=_saved_bmw_jpm_now

# Currency arithmetic, exactly 1 USD = 1330.33 KRW on 2026-10-19 19:05 KST.
# Monetary display rounds half-up at the 100m-KRW precision, not Python's banker's rounding.
assert int(5e9*1330.33/1e8+0.5)==66517
assert round(10e9*1330.33/1e8)==133033
assert round(230e9*1330.33/1e8)==3059759
assert round(1.5e12*1330.33/1e8)==19954950


# 91) Regression: correction of mixed-rate JPM Telegram body was a
# one-time ERRATUM, not fresh corporate financing; preserve source dates.
jpm_corrected=base.query_news(watcher.JPM_SRI_FX_CORRECTION_RECOVERY)
if base.NOW.astimezone(base.KST).date()<=dt.date(2026,10,23):
    assert len(jpm_corrected)==1,jpm_corrected
    fix=jpm_corrected[0]
    assert fix['source']=='원화 계산 정정',fix
    fg,fs,fc,fk=classify(fix)
    assert fg==jg and fs>=11,(fg,fs,fc)
    assert fc=='JP모건 SRI · 환율 표기 정정(기존 알림)',fc
    assert fk not in {jk,pk},(fk,jk,pk)
    assert '회사 신규 발표가 아님' in base.verification(
        fix,fg,fix['title']+' '+fix['description']
    )
    assert '신규 투자' in base.meaning(fc),base.meaning(fc)
    assert base.clean_title(fix['title'],fix['source']).startswith('정정: JP모건 SRI')

# Stable currency basis across formatted headline/category/core: do not
# allow the automatic postprocessor to mix an older daily ECB rate
# with the separately checked 2026-10-19 19:05 KST spot quote.
fx_block=(
    '<b>4. JP모건 전략적 투자 JP모건 SRI 50억달러 누적 집행</b>\n'
    '<b>분류</b> JP모건 SRI · 50억달러 지분투자 누적 집행\n'
    '💡 <b>핵심</b> 50억달러(약 6조6,517억원) 중 '
    '100억달러 2,300억달러 1조5,000억달러를 분리한다'
)
normalized=watcher._correct_jpm_sri_krw_at_source_rate(fx_block)
for expected in ('50억달러(약 6조6,517억원)',
                 '100억달러(약 13조3,033억원)',
                 '2,300억달러(약 305조9,759억원)',
                 '1조5,000억달러(약 1,995조4,950억원)'):
    assert expected in normalized,(expected,normalized)
assert '6조6,605억원' not in normalized,normalized
assert watcher._correct_jpm_sri_krw_at_source_rate(normalized)==normalized

not_jpm='BMW Gen6 · 선양 배터리팩 양산 공식 개시, 50억달러와는 무관'
assert watcher._correct_jpm_sri_krw_at_source_rate(not_jpm)==not_jpm

sample_alert=(
    '<b>피지컬AI 고신호</b>\n<b>신규 고신호 5건</b>\n━━━━━━━━━━━━━━━━━━\n'
    '<b>1. 배터리주 들썩…中 ESS 업체 美서 철수</b>\n'+'A\n'
    '──────────────────\n'
    '<b>2. BMW Gen6 선양 46mm 배터리팩 실제 양산</b>\n'+'B\n'
    '──────────────────\n'
    '<b>3. 백조세탁기부터 클로이드까지…타임스스퀘어 가전 혁신 영상</b>\n'+'C\n'
    '──────────────────\n'
    '<b>4. 증시 주인공된 배터리주…삼성SDI·LG엔솔 강세</b>\n'+'D\n'
    '──────────────────\n'
    '<b>5. JP모건 SRI 누적 지분투자 50억달러</b>\n'+'E\n'
)
filtered=watcher._drop_stock_price_sections(sample_alert)
assert '신규 고신호 2건' in filtered,filtered
assert '배터리주 들썩' not in filtered,filtered
assert '백조세탁기' not in filtered,filtered
assert '증시 주인공' not in filtered,filtered
assert '<b>1. BMW Gen6' in filtered,filtered
assert '<b>2. JP모건 SRI' in filtered,filtered
assert watcher._drop_stock_price_sections(filtered)==filtered

_now_for_fx=base.NOW
try:
    base.NOW=dt.datetime(2026,10,27,12,0,tzinfo=dt.timezone.utc)
    assert base.query_news(watcher.JPM_SRI_FX_CORRECTION_RECOVERY)==[],(
        'old erratum must not repeat forever when state rotates'
    )
finally:
    base.NOW=_now_for_fx



# 80) Volkswagen Europe 93MF / 93MV cell safety campaigns, not US 26V630.
# Distinct regulators, OEM evidence, 80% charging limit, and unnamed EU
# supplier. The 22,524 US vehicles are NOT EU recall quantity.
vw_eu_primary = make(
    "폭스바겐 유럽 고전압 배터리 리콜: 영국 93MF·93MV 80% 제한 공식 안내",
    "Volkswagen UK 93MF 93MV high-voltage battery cell safety recall. "
    "Some ID.3, ID.4, ID.7 and ID.Buzz vehicles with supplier cells "
    "produced between 2022 and 2025 need checks; charge cap 80% "
    "because of overheating and fire risk. "
    "Germany KBA registration pending; no named EU supplier. "
    "US ID.4 26V630 22,524 SK Battery America is a different recall.",
    "Volkswagen UK",
)
vg, vs, vc, vk = classify(vw_eu_primary)
assert vg == 'vw_europe_battery_recall' and vs >= 11, (vg,vs,vc)
assert vc == '폭스바겐 유럽 배터리 리콜 · 영국 93MF·93MV 충전 제한',vc
assert '유럽과 합산하지' in base.meaning(vc),base.meaning(vc)
assert 'SK Battery America' in base.meaning(vc),base.meaning(vc)
assert '공급사' in base.verification(vw_eu_primary,vg,
    vw_eu_primary['title']+' '+vw_eu_primary['description'])
assert '충당금' in base.risk(vc) and '1만 정비시간' in base.risk(vc)
assert '실제 교체율은 미확정' in base.meaning(vc),base.meaning(vc)
assert base.clean_title(vw_eu_primary['title'],vw_eu_primary['source']).startswith('영국 93MF')

vw_vans_official = make(
    "폭스바겐 영국 93MF 고전압 배터리 리콜 80% 충전 제한",
    "Volkswagen Vans UK official 93MF high-voltage battery safety recall "
    "for ID.Buzz. Production defect and fire risk; maximum 80% charge cap.",
    "Volkswagen Vans UK",
)
vg2, vs2, vc2, vk2 = classify(vw_vans_official)
assert vg2 == vg and vs2 >= 11 and vk2 == vk, (vg2,vs2,vc2,vk2)

vw_reprinted = dict(vw_eu_primary,source="더구루")
vg3, vs3, vc3, vk3 = classify(vw_reprinted)
assert vg3 == vg and vs3 < 11 and vk3 != "future_germany_kba", (vg3,vs3,vc3)

vw_us_old = make(
    "Volkswagen ID.4 HV battery recall 26V630 22524 vehicles",
    "Volkswagen Group of America recalled 22,524 US ID.4 in 93EX "
    "on September 30, 2026. SK Battery America supplied cells. "
    "Charge only to 80% due to high-voltage battery overheating.",
    "NHTSA",
)
ug, us, uc, uk = classify(vw_us_old)
assert ug == vg and us < 11 and uk != vk,(ug,us,uc,uk)

vw_eu_skba_rumour = make(
    "폭스바겐 유럽 93MF 고전압 배터리 리콜 공급사 SK온이라는 추측",
    "폭스바겐 UK 93MF 80% 제한, 루머에 따르면 유럽 결함 셀 "
    "공급사는 SK Battery America일 것이라는 미확인 해석이다.",
    "시장 루머",
)
sg, ss, sc, sk = classify(vw_eu_skba_rumour)
assert sg == vg and ss < 11,(sg,ss,sc)

vw_germany_unready = make(
    "독일 KBA 폭스바겐 93MF 고전압 배터리 리콜 준비",
    "KBA German Federal Motor Transport Authority 아직 등록 준비 단계; "
    "Volkswagen 93MF high-voltage battery recall 80% cap pending.",
    "KBA",
)
pg, ps, pc, pk = classify(vw_germany_unready)
assert pg == vg and ps < 11,(pg,ps,pc)


vw_other_kba = make(
    "폭스바겐 독일 KBA 구형 93EA 고전압 배터리 리콜 공식 등록",
    "KBA officially issued Volkswagen high-voltage battery recall 93EA.",
    "KBA",
)
og, os, oc, ok = classify(vw_other_kba)
assert og == vg and os < 11, (og,os,oc)

vw_germany_official_future = make(
    "폭스바겐 독일 KBA 93MV 고전압 배터리 리콜 공식 등록 개시",
    "KBA German Federal Motor Transport Authority Volkswagen 93MV "
    "high-voltage battery campaign issued and activated, 80% charge limit.",
    "KBA",
)
kg, ks, kc, kk = classify(vw_germany_official_future)
assert kg == vg and ks >= 11 and kk != vk,(kg,ks,kc,kk)
assert kc == '폭스바겐 유럽 배터리 리콜 · 독일 KBA 공식 시행',kc

# Recovery uses an official VW page and preserves only a calendar date.
_vw_now=base.NOW
try:
    base.NOW=dt.datetime(2026,10,19,13,0,tzinfo=dt.timezone.utc)
    recovered=base.query_news(watcher.VW_EU_BATTERY_RECALL_RECOVERY)
    assert len(recovered)==1,recovered
    vv=recovered[0]
    assert vv['source']=='Volkswagen UK' and vv['published'] is None,vv
    assert vv['link']=='https://www.volkswagen.co.uk/en/owners-and-services/my-car/battery-recall-campaign.html'
    rg,rs,rc,rk=classify(vv)
    assert rg==vg and rs>=11 and rk==vk,(rg,rs,rc,rk)
    renderer_text=vv['title']+' '+vv['description']
    assert base.category(renderer_text,base.topic_group(renderer_text))==vc
    assert '유럽 공급사 실명' in vv['description']
    assert 'SK Battery America' in vv['description']
    assert '배터리 점검 소요시간은 약 1시간' in vv['description']
    assert watcher.qty._skip_quantity_enrichment(
        "<b>1. 폭스바겐 유럽 배터리 리콜</b>\n"
        "<b>분류</b> 폭스바겐 유럽 배터리 리콜 · 영국 93MF·93MV 충전 제한\n"
        "미국 ID.4 22,524대 별도 26V630"
    ),'The US count may never be priced as EU recall inventory'
    base.NOW=dt.datetime(2026,10,26,12,0,tzinfo=dt.timezone.utc)
    assert base.query_news(watcher.VW_EU_BATTERY_RECALL_RECOVERY)==[],(
        'Expired backfill must not replay as new European recall')
finally:
    base.NOW=_vw_now


# 90) Tesla official 2026 AGM date and conditional Silicon Valley
# Humanoids Summit appearance: an actual SEC proxy is NOT a V3 demo.
agm_notice = make(
    "Tesla 2026 annual shareholder meeting December 3, 2026 DEF14A",
    "Tesla official 2026 annual shareholder meeting notice for December 3, "
    "2026 at 3:00 PM CST; record date Oct 13, 2026; Class I nominees "
    "Elon Musk, Robyn Denholm and JB Straubel. 2025 executive comp "
    "advisory vote and PwC 2026 audit ratification.",
    "Tesla IR",
)
agm_notice['link']=watcher.TESLA_AGM26_SEC
ag,ascore,ac,ak=classify(agm_notice)
assert ag=='tesla_agm_2026' and ascore>=11,(ag,ascore,ac)
assert ac=='테슬라 2026 주주총회 · 12월 3일 공식 일정',ac
assert '12/4 오전 6시' in base.meaning(ac),base.meaning(ac)
assert '3개' in base.meaning(ac) and 'V3' in base.meaning(ac),base.meaning(ac)
assert 'SEC 원본 HTML 직접 열람 실패' in base.verification(
    agm_notice,ag,agm_notice['title']+' '+agm_notice['description']
)

agm_news_mirror=dict(agm_notice,source='Reuters')
ng,ns,nc,nk=classify(agm_news_mirror)
assert ng==ag and ns<11, (ng,ns,nc)
agm_source_spoof=dict(agm_notice,link='https://example.com/not-sec')
sg,ss,sc,sk=classify(agm_source_spoof)
assert sg==ag and ss<11, (sg,ss,sc)

agm_again=dict(agm_notice,title='Tesla 2026 annual shareholder meeting December 3 2026 details')
rg,rs,rc,rk=classify(agm_again)
assert rg==ag and rs>=11 and rk==ak, (rg,rs,rc,rk)
assert watcher.qty._skip_quantity_enrichment(
    '<b>1. 테슬라 2026 주주총회</b>\n'
    '<b>분류</b>  테슬라 2026 주주총회 · 12월 3일 공식 일정\n'
    'Class I 이사 3명 및 안건 3개'
), 'Governance agenda counts are not manufactured robot units'

agm_votes=make(
    'Tesla 2026 annual shareholder meeting December 3 2026 final voting results',
    'Tesla final voting results December 3 2026 official tally of Class I directors.',
    'Tesla IR',
)
agm_votes['link']='https://ir.tesla.com/2026-voting-results'
vg,vs,vc,vk=classify(agm_votes)
assert vg==ag and vs>=11 and vk!=ak,(vg,vs,vc,vk)

# An organizer EVENT date is verified; the analyst excerpt alone cannot
# certify Tesla's specific demonstration or the Optimus V3 model.
summit_report=make(
    'Tesla Optimus Humanoids Summit December 1-2, 2026 demo reported',
    'Broker says official partner Tesla offers hands-on Optimus and FSD rides. '
    'Promotional image looks like V2, V3 not confirmed.',
    'Analyst Telegram',
)
summit_report['link']='https://www.linkedin.com/company/humanoidssummit'
sg,ss,sc,sk=classify(summit_report)
assert sg=='tesla_humanoids_summit_2026' and ss<11,(sg,ss,sc)

summit_organizer=dict(summit_report)
summit_organizer.update({
    'source':'Humanoids Summit',
    'title':'Tesla Optimus hands-on at Humanoids Summit December 1-2, 2026',
    'description':'Official Humanoids Summit live demo Tesla Optimus hands-on '
                  'display for all attendees, FSD test drives.',
    'link':'https://www.linkedin.com/posts/humanoidssummit_example-official-post',
})
og,os,oc,ok=classify(summit_organizer)
assert og==sg and os>=11,(og,os,oc)
assert oc=='테슬라 Humanoids Summit · Optimus 현장 시연 공식 확인',oc
assert 'V3' in base.meaning(oc) and 'V2' in base.meaning(oc),base.meaning(oc)
assert '원격' in base.risk(oc),base.risk(oc)

summit_repost=dict(summit_organizer,source='Market Commentary')
xg,xs,xc,xk=classify(summit_repost)
assert xg==og and xs<11,(xg,xs,xc)
summit_company_profile=dict(summit_organizer,link='https://www.linkedin.com/company/humanoidssummit')
pg,ps,pc,pk=classify(summit_company_profile)
assert pg==og and ps<11,(pg,ps,pc)

summit_negative=dict(summit_organizer,
    title='Tesla Optimus V3 not confirmed for Humanoids Summit December 1-2 2026')
ng,ns,nc,nk=classify(summit_negative)
assert ng==og and ns>=11 and nk==ok,(ng,ns,nc,nk)

summit_tesla=dict(summit_organizer,source='Tesla',
    link='https://www.tesla.com/event/optimus-summit')
tg,ts,tc,tk=classify(summit_tesla)
assert tg==og and ts>=11 and tk!=ok,(tg,ts,tc,tk)

summit_tesla_v3=dict(summit_tesla,
    title='Tesla Optimus Gen 3 live reveal at Humanoids Summit December 1-2 2026',
    description='Tesla announces official Optimus Gen 3 debut at the event.')
vg,vs,vc,vk=classify(summit_tesla_v3)
assert vg==og and vs>=11 and vk!=tk,(vg,vs,vc,vk)
assert 'V3 공식 공개' in vc,vc
summit_v3_rumour=dict(summit_tesla_v3,source='Market Commentary')
mg,ms,mc,mk=classify(summit_v3_rumour)
assert mg==og and ms<11,(mg,ms,mc)

agm_backfill=base.query_news(watcher.TESLA_AGM26_EVENT)
if base.NOW.astimezone(base.KST).date()<=dt.date(2026,10,27):
    assert len(agm_backfill)==1,agm_backfill
    a=agm_backfill[0]
    assert a['source']=='Tesla IR' and a['published'] is None,a
    assert a['link']==watcher.TESLA_AGM26_SEC,a
    bg,bs,bc,bk=classify(a)
    assert bg==ag and bs>=11 and bc==ac and bk==ak,(bg,bs,bc,bk)
    assert base.category(a['title']+' '+a['description'],bg)==ac
    assert '주최 측' in base.meaning(bc)
_old_tesla_agm_now=base.NOW
try:
    base.NOW=dt.datetime(2026,10,28,13,0,tzinfo=dt.timezone.utc)
    assert base.query_news(watcher.TESLA_AGM26_EVENT)==[],(
        'Fixed 10/19 proxy notice must expire to prevent repeat after state rollover')
finally:
    base.NOW=_old_tesla_agm_now



# 91) Do not equate an official Tesla event partnership, a hands-on
# Optimus demo, and a first-party V3 reveal; verify official X separately.
summit_partner=dict(summit_organizer,
    title='Tesla official partner at Humanoids Summit December 1-2 2026',
    description='Humanoids Summit confirms Tesla as official partner.',
)
pg,ps,pc,pk=classify(summit_partner)
assert pg=='tesla_humanoids_summit_2026' and ps>=11,(pg,ps,pc)
assert pc=='테슬라 Humanoids Summit · 파트너 참가 공식 확인',pc
assert pk not in {ok,tk,vk},'Partner stage must be distinct from demo/V3'
assert 'V3' in base.meaning(pc) and '단정할 수 없습니다' in base.meaning(pc)
assert '시연·V3 여부 별도' in base.clean_title(summit_partner['title'],summit_partner['source'])

summit_partner_repost=dict(summit_partner,source='Unverified Media')
pg2,ps2,pc2,pk2=classify(summit_partner_repost)
assert pg2==pg and ps2<11,(pg2,ps2,pc2)

summit_ceo_x=dict(summit_tesla_v3,source='Elon Musk (X)',
    link='https://x.com/elonmusk/status/9999999999999999999')
xg,xs,xc,xk=classify(summit_ceo_x)
assert xg=='tesla_humanoids_summit_2026' and xs>=11,(xg,xs,xc)
assert xc=='테슬라 Humanoids Summit · V3 공식 공개 예고',xc
assert xk==vk,'Tesla CEO direct confirmation and Tesla.com are same event'

summit_fake_x=dict(summit_ceo_x,link='https://x.com/someone_else/status/9999999999999999999')
fg,fs,fc,fk=classify(summit_fake_x)
assert fg==xg and fs<11,(fg,fs,fc)

assert base.clean_title(agm_notice['title'],'Tesla IR').startswith('12월 3일'),(
    'Base display label already supplies Tesla name; avoid duplicate headline')



# 2026-10-20 Samsung RX 24h and Oct23 regulatory meeting:
# REPORTS / DISCUSSION vs official performance / legal adoption.
samsung_24_report=make(
    "삼성전자 RX사업추진실 24시간 이족보행 로봇 제조현장 실증 보도",
    "중앙일보 업계 취재: 삼성전자 서울R&D캠퍼스 우면동에서 "
    "24시간 3교대 모니터링을 하며 로봇의 물류 반복 작업을 검증하고 "
    "CES 2027 전시를 검토 중. 완전 무인 연속가동 성능은 미확인.",
    "중앙일보",
)
sg, ss, sc, sk = classify(samsung_24_report)
assert sg=="samsung_24h_rx" and ss>=11, (sg,ss,sc)
assert sc=="삼성전자 RX · 24시간 운용 목표 현장검증 보도",sc
assert "CES" in base.meaning(sc) and "검토" in base.meaning(sc)
assert "24시간" in base.risk(sc) and "가정" in base.risk(sc)

samsung_24_rewrite=make(
    "삼성전자 RX 로봇 24시간 생산근무 목표",
    "삼성전자 우면동 이족보행 휴머노이드 로봇의 24시간 연속작업 목표를 시험 검증 중.",
    "연합뉴스",
)
sg2,ss2,sc2,sk2=classify(samsung_24_rewrite)
assert sg2==sg and ss2>=11 and sk2==sk, (sg2,ss2,sc2,sk2)

samsung_ces_review=make(
    "삼성전자 CES 2027 휴머노이드 검토",
    "삼성전자 RX 24시간 산업용 로봇 CES 2027 출품을 검토 중이지만 아직 공식 참가 확정은 없다.",
    "투자자 블로그",
)
sg3,ss3,sc3,sk3=classify(samsung_ces_review)
assert sg3==sg and ss3<11,(sg3,ss3,sc3)

samsung_official_uptime=make(
    "삼성전자 RX 24시간 휴머노이드 연속 가동 시험 통과 발표",
    "삼성전자 RX 이족보행 휴머노이드 로봇이 24시간 연속 무인 시험 통과를 공식 발표했다.",
    "삼성전자",
)
ug,us,uc,uk=classify(samsung_official_uptime)
assert ug==sg and us>=11 and uk!=sk,(ug,us,uc,uk)
assert uc=="삼성전자 RX · 24시간 무인 연속가동 공식 검증",uc

samsung_ces_official=make(
    "삼성전자 CES 2027 이족보행 휴머노이드 로봇 공식 공개",
    "삼성전자 RX CES 2027에서 이족보행 휴머노이드 로봇 공식 공개를 직접 발표했다.",
    "삼성전자",
)
cg,cs,cc,ck=classify(samsung_ces_official)
assert cg==sg and cs>=11 and ck not in {sk,uk},(cg,cs,cc,ck)
assert cc=="삼성전자 RX · CES 2027 제품 공개 공식확인",cc

reg_agenda=make(
    "10월 23일 규제합리화위원회 로봇·AI 데이터센터 규제 논의 예고",
    "청와대 20일 브리핑: 2026-10-23 규제합리화위원회 제2차 전체회의에서 "
    "로봇, 반도체, AI 데이터센터의 규제 개선 방향을 논의할 예정이다. "
    "개별 특례 시행은 확정 전.",
    "연합뉴스",
)
rg,rs,rc,rk=classify(reg_agenda)
assert rg=="robot_reg_oct23" and rs>=11,(rg,rs,rc)
assert rc=="정부 규제합리화위 · 10월 23일 개최 예고",rc
assert "이미 개정" in base.meaning(rc) and "뜻은 아닙니다" in base.meaning(rc)

reg_reprint=make(
    "규제합리화위 제2차 전체회의 로봇 관련 규제해소 발표",
    "대통령이 10월 23일 규제합리화위원회 제2차 전체회의를 주재하고 "
    "로봇과 AI 데이터센터의 현장 규제 개선 방향을 발표한다.",
    "뉴스1",
)
rg2,rs2,rc2,rk2=classify(reg_reprint)
assert rg2==rg and rs2>=11 and rk2==rk,(rg2,rs2,rc2,rk2)

reg_official_decision=make(
    "국무조정실 10월 23일 제2차 규제합리화위원회 로봇 실증특례 의결",
    "국무조정실은 2026-10-23 규제합리화위원회 제2차 전체회의에서 "
    "로봇 현장 실증특례 최종 확정을 공식 발표했다.",
    "국무조정실",
)
og,os,oc,ok=classify(reg_official_decision)
assert og==rg and os>=11 and ok!=rk,(og,os,oc,ok)
assert oc=="정부 규제합리화위 · 23일 구체 제도변경 공식의결",oc

reg_unapproved=make(
    "규제합리화위원회 로봇 규제 논의 예정",
    "정부가 10월 23일 규제합리화위원회 제2차 전체회의에서 "
    "로봇 규제특례를 검토 중이며 시행은 미확정이다.",
    "국무조정실",
)
g0,s0,c0,k0=classify(reg_unapproved)
assert g0==rg and c0==rc and k0==rk,(g0,s0,c0,k0)

# Two recoveries must be independently sourced, date-scoped, and not
# fabricate 24h reliable operation, new capital budgets or legislation.
old_now=base.NOW
try:
    base.NOW=dt.datetime(2026,10,20,12,0,tzinfo=dt.timezone.utc)
    sampler=watcher.base.query_news(watcher.S24H_20261020_RECOVERY)
    dater=watcher.base.query_news(watcher.KREG_OCT23_RECOVERY)
    assert len(sampler)==1 and len(dater)==1,(sampler,dater)
    assert sampler[0]["source"]=="중앙일보" and sampler[0]["published"] is None
    assert dater[0]["source"]=="연합뉴스"
    assert dater[0]["published"]=="2026-10-20T00:36:00+00:00"
    rsg,rss,rsc,rsk=classify(sampler[0])
    rrg,rrs,rrc,rrk=classify(dater[0])
    assert rsg==sg and rss>=11 and rsc==sc and rsk==sk,(rsg,rss,rsc,rsk)
    assert rrg==rg and rrs>=11 and rrc==rc and rrk==rk,(rrg,rrs,rrc,rrk)
    for item,expected_cat in ((sampler[0],sc),(dater[0],rc)):
        t=item["title"]+" "+item["description"]
        shown=base.category(t,base.topic_group(t))
        assert shown==expected_cat,(shown,expected_cat)
        assert base.verification(item,base.topic_group(t),t)
    assert watcher.qty._skip_quantity_enrichment(
        "<b>1. 삼성전자 RX</b>\n<b>분류</b>  "+sc+"\n24시간 3교대"
    ),"Pilot duration is not sold robot units"
    assert watcher.qty._skip_quantity_enrichment(
        "<b>2. 규제합리화위원회</b>\n<b>분류</b>  "+rc+"\n23일 참석 100명"
    ),"Meeting attendees are not shipped robots"
    base.NOW=dt.datetime(2026,10,25,0,0,tzinfo=dt.timezone.utc)
    assert watcher.base.query_news(watcher.S24H_20261020_RECOVERY)==[]
    assert watcher.base.query_news(watcher.KREG_OCT23_RECOVERY)==[]
finally:
    base.NOW=old_now



# 2026-05 Daishin 2027-29 roadmap tables re-circulated as screenshots
# are analyst forecasts, NOT new actual 2026-10 production, contracts,
# capacity ramp, customer acceptance, or newly issued company guidance.
roadmap_forecasts = [
    make(
        "표 21 전고체 배터리 업체별 타임라인 2027년 2028년 2029년",
        "대신증권 Research Center 2026년 5월 전망표: LGES 2027 황화물계 "
        "파일럿, 2029 흑연계 EV 초기 상용화 예정. 삼성SDI 2027 황화물계 "
        "양산 개시 목표, 2028 라인 최적화·수율 안정화 전망. "
        "에코프로비엠 2028년 300톤 증산 계획, 포스코퓨처엠 "
        "2029년 대량 생산 준비, CATL 2027년 전고체 500Wh/kg "
        "소규모 시험생산 목표이며 2030년 대량 양산 계획.",
        "대신증권",
    ),
    make(
        "표 20 나트륨 배터리 업체별 개발 타임라인 2027년 2028년 2029년",
        "대신증권 Research Center 2026년 5월 전망표: LG에너지솔루션 "
        "2027년 나트륨이온 1세대 양산 목표와 2028년 2세대 개발 "
        "계획, 삼성SDI 공식 나트륨이온 양산 로드맵 없음. "
        "에코프로비엠 양극재 고객사 일정 연동 개발, 엘앤에프 "
        "초기 개발 단계. CATL 2027년 2세대 양산 체계 "
        "완성과 2029년 글로벌 확산 전망. "
        "BYD 2027년 3세대 나트륨 플랫폼 개발 및 "
        "2030년 이후 대량 상용화라는 이미지상 예상 목표.",
        "대신증권",
    ),
]
for _item in roadmap_forecasts:
    _g,_score,_cat,_key=classify(_item)
    assert _score < 11, (
        "Old analyst roadmap must not be mistaken for a newly achieved milestone",
        _g,_score,_cat
    )
# Keep original image provenance separate: the recoverable 2026-05
# research PDF uses tables 6/18/33, while the user images say 21/20
# and add a BYD sodium row; this is NOT authenticated as a primary
# Daishin update without a newer dated original report.


# Verified rescheduling remains actionable; a forecast or analyst's repeated
# multi-year milestone table alone is NOT official postponement/acceleration.
sodium_true_acceleration = make(
    "LG에너지솔루션 나트륨이온 배터리 상용화 일정 앞당겨",
    "LG에너지솔루션은 2027년으로 계획했던 나트륨이온 배터리 "
    "상용화 일정을 2026년으로 앞당겼다고 공식 발표했다.",
    "LG에너지솔루션",
)
sg, ss, sc, sk = classify(sodium_true_acceleration)
assert sg == "sodium_ion_battery" and ss >= 11, (sg, ss, sc)
assert sc.endswith("나트륨이온 상용화 일정 변경"),sc

sodium_rumor_acceleration = dict(sodium_true_acceleration, source="주가테마 블로그")
rg, rs, rc, rk = classify(sodium_rumor_acceleration)
assert rg == "sodium_ion_battery" and rs < 11, (rg, rs, rc)

sodium_static_trusted = make(
    "LG에너지솔루션 2027년 나트륨 양산 목표 다시 주목",
    "LG에너지솔루션은 나트륨이온 배터리 2027년 상용화를 목표로 "
    "2028년 2세대 공정을 개발할 계획이다. 신규 결정은 없다.",
    "연합뉴스",
)
tg, ts, tc, tk = classify(sodium_static_trusted)
assert ts < 11, (tg, ts, tc)



# CATL-INTILION 10/20 iNews24 reprint omitted buyer's name in RSS
# headline: message_id=246 from Run #693 is a DUPLICATE of message 218
# original 10/09 5-year up-to-3GWh development-framework event.
catl_reprint_246 = make(
    "CATL, '나트륨 배터리'로 유럽 ESS 공략⋯저온·장수명 기술 앞세워",
    "독 인틸리온과 최대 3GWh 공동개발 목표, "
    "CATL 나트륨 ESS 1만5천 회 수명, 2027년 글로벌 공급 추진",
    "아이뉴스24",
)
cg, cs, cc, ck = classify(catl_reprint_246)
assert cs < 11, ('October 20 CATL-INTILION reprint must stay silent', cg,cs,cc)
assert ck == hashlib.sha256(
    b'catl-intilion|sodium|dach|20261009|3gwh-target|five-years'
).hexdigest(), 'Missing buyer in headline must still reuse old CATL-INTILION event key'
catl_other_new_news = make(
    "CATL and Solarpro confirm first sodium-ion ESS commissioning",
    "CATL and Solarpro jointly commissioned a new 500MWh sodium-ion site, "
    "distinct from Intilion DACH 3GWh program.",
    "CATL",
)
assert watcher._catl_intilion_oct20_reprint(catl_reprint_246)
assert not watcher._catl_intilion_oct20_reprint(catl_other_new_news)
previous_now=base.NOW
try:
    base.NOW=dt.datetime(2026,10,20,9,0,tzinfo=dt.timezone.utc)
    r=watcher.query_news(watcher.ALERT246_CORRECTION_ID)
    assert len(r)==1 and r[0].get('quality_correction_246'),r
    ag,ass,ac,ak=classify(r[0])
    assert ag=='alert_quality_246' and ass >= 11,(ag,ass,ac)
    assert '중복 제외' in ac and '218번' in base.meaning(ac),(ac,base.meaning(ac))
    p=r[0]['title']+' '+r[0]['description']
    assert base.category(p,base.topic_group(p))==ac
    assert 'Run #693' in base.verification(r[0],ag,p)
    assert 'Telegram 246' in base.clean_title(r[0]['title'],r[0]['source'])
    assert base.key(r[0])==ak
    base.NOW=dt.datetime(2026,10,26,0,0,tzinfo=dt.timezone.utc)
    assert watcher.query_news(watcher.ALERT246_CORRECTION_ID)==[], 'old correction must expire'
finally:
    base.NOW=previous_now


# 75) Two 2026-10-19/20 new events: Boston Dynamics actual CFO interview
# about actuator *BOM* and Eka company Series A with Samsung Next; preserve
# 2025 RB-Y1 research relationship, deny false client orders and unit sales.
assert watcher.ATLAS_COST_20261019_RECOVERY in base.QUERIES
assert watcher.EKA_ROBOTICS_20261020_RECOVERY in base.QUERIES
bd_event=watcher.base.query_news(watcher.ATLAS_COST_20261019_RECOVERY)
eka_event=watcher.base.query_news(watcher.EKA_ROBOTICS_20261020_RECOVERY)
if base.NOW.astimezone(base.KST).date()<=dt.date(2026,10,27):
    assert len(bd_event)==1 and len(eka_event)==1
    bd_item=bd_event[0]
    eka_item=eka_event[0]
    assert bd_item["source"]=="Fortune"
    assert eka_item["source"]=="Eka Robotics"
    assert bd_item["published"] is None and eka_item["published"] is None
    bd_g,bd_s,bd_cat,bd_k=classify(bd_item)
    ek_g,ek_s,ek_cat,ek_k=classify(eka_item)
    assert bd_g=="atlas_actuator_bom" and bd_s>=11,(bd_g,bd_s,bd_cat)
    assert ek_g=="eka_dexterous_funding" and ek_s>=11,(ek_g,ek_s,ek_cat)
    assert bd_cat=="Atlas 액추에이터 · CFO 부품원가 70% 발언",bd_cat
    assert ek_cat=="Eka Robotics · 시리즈 A 공식 조달·삼성넥스트 참여",ek_cat
    assert bd_k!=ek_k
    for item,cat in ((bd_item,bd_cat),(eka_item,ek_cat)):
        x=item["title"]+" "+item["description"]
        # Check the real Telegram renderer, which omits source in category().
        assert base.category(x,base.topic_group(x))==cat,(cat,base.category(x,base.topic_group(x)))
        assert base.key(item)==(bd_k if item==bd_item else ek_k)
        assert base.meaning(cat) and base.risk(cat)
    assert '부품·재료비' in base.meaning(bd_cat)
    assert 'Atlas 5만 대 확정 발주가 아닙니다' in base.meaning(bd_cat)
    assert 'Spot 판매가' in base.meaning(bd_cat)
    assert '개별 투자액·지분율 미공개' in base.meaning(ek_cat)
    assert '기존' not in base.category(eka_item['title']+' '+eka_item['description'],ek_g)
    assert watcher.qty._skip_quantity_enrichment(
        "<b>1. 보스턴다이내믹스 CFO: Atlas 액추에이터 부품원가 70%</b>\n"
        "그룹 50,000대 배치 구상, 액추에이터 공급 단가 미공개"
    )
    assert watcher.qty._skip_quantity_enrichment(
        "<b>2. Eka Robotics 공식 1억5000만달러 조달·Samsung Next 투자 참여</b>\n"
        "기술 성능 시간당 1,500회, 투자 150 million dollars"
    )




bd_old=make(
    "보스턴다이내믹스 Atlas 액추에이터 전략적 공급협력 현대모비스",
    "현대모비스는 CES 2026에서 Atlas 액추에이터 공급협력 발표. "
    "부품 재료비 60% 초과로 추정된다.",
    "현대모비스",
)
bdog,bdos,bdoc,bdok=classify(bd_old)
assert bdog!="atlas_actuator_bom", (bdog,bdos,bdoc)

bd_media_copy=make(
    "Boston Dynamics Atlas actuator cost 70% new briefing",
    "Boston Dynamics Atlas actuator materials make up 70% BOM and "
    "Hyundai Mobis will manufacture at cost, according to Fortune CFO interview.",
    "뉴스 재인용",
)
bdcg,bdcs,bdcc,bdck=classify(bd_media_copy)
assert bdcg=="atlas_actuator_bom" and bdcs<11,(bdcg,bdcs,bdcc)

bd_primary=make(
    "보스턴다이내믹스 Atlas 액추에이터 BOM 70% 공식 발표",
    "Boston Dynamics official announcement: Atlas actuator materials "
    "70% of BOM and Hyundai Mobis supplying at cost.",
    "Boston Dynamics",
)
bp_g,bp_s,bp_cat,bp_k=classify(bd_primary)
assert bp_g=="atlas_actuator_bom" and bp_s>=11,(bp_g,bp_s,bp_cat)
assert bp_cat=="Atlas 액추에이터 · 제조사 직접 원가비중 확인",bp_cat
if bd_event:
    assert bp_k!=base.key(bd_event[0]),"Direct official evidence must be distinct"

eka_media_copy=make(
    "Eka Robotics raises $150 million Series A with Samsung Next",
    "Eka Robotics Series A 150 million dollars with Samsung Next as one participant.",
    "일반 경제뉴스",
)
mg,ms,mc,mk=classify(eka_media_copy)
assert mg=="eka_dexterous_funding" and ms<11,(mg,ms,mc)

eka_legacy=make(
    "Eka Robotics RB-Y1 dexterous hand research",
    "Eka Robotics used Rainbow Robotics RB-Y1 for dexterous hand research in 2025.",
    "레인보우로보틱스",
)
lg,ls,lc,lk=classify(eka_legacy)
assert lg=="eka_dexterous_funding" and ls<11,(lg,ls,lc)

eka_new_order=make(
    "Eka Robotics RB-Y1 신규 공급계약 체결 발표",
    "Eka Robotics RB-Y1 신규 공급계약 체결, robotics hand research platform orders.",
    "레인보우로보틱스",
)
og,os,oc,ok=classify(eka_new_order)
assert og=="eka_dexterous_funding" and os>=11,(og,os,oc)
assert oc=="Eka Robotics–레인보우로보틱스 · RB-Y1 신규 주문",oc
if eka_event:
    assert ok!=base.key(eka_event[0]), "New OEM order must not be funding replay"

t_ae=base.NOW
try:
    base.NOW=dt.datetime(2026,10,28,12,0,tzinfo=dt.timezone.utc)
    assert watcher.base.query_news(watcher.ATLAS_COST_20261019_RECOVERY)==[]
    assert watcher.base.query_news(watcher.EKA_ROBOTICS_20261020_RECOVERY)==[]
finally:
    base.NOW=t_ae


# 76) Telegram 249 mixed a historical hardcoded KRW conversion and the
# live common FX pass. Verify the source leaves only foreign currency
# figures, that the common renderer uses one mocked rate for every amount,
# and that the correction is ONE deduplicated event.
if bd_event and eka_event:
    no_static = (base.meaning(bd_cat)+base.meaning(ek_cat)
                 +bd_event[0]["description"]+eka_event[0]["description"])
    for old_conversion in ("1억3,272만원","3억9,816만원",
                           "약 1,991억원","1조9,245억원"):
        assert old_conversion not in no_static, old_conversion

import currency_krw_guard as _fxguard249
_old_fx249=_fxguard249._rate
_old_used_fx249=dict(_fxguard249._USED_FX)
try:
    _fxguard249._rate=lambda curr:(1327.84,"2026-10-20 test") if curr=="USD" else (None,"unknown")
    _fxguard249._USED_FX.clear()
    sample=("Eka 1억5000만달러 투자. Spot 기본 10만달러, "
            "옵션 30만달러. 같은 1억5000만달러 투자")
    converted=_fxguard249.enforce_text(sample)
    assert converted.count("1억5000만달러(약 1,992억원)")==2,converted
    assert "10만달러(약 1억3,278만원)" in converted,converted
    assert "30만달러(약 3억9,835만원)" in converted,converted
    assert "USD/KRW 1,327.8400원" in converted,converted
    _fxguard249.validate_text(converted)
finally:
    _fxguard249._rate=_old_fx249
    _fxguard249._USED_FX.clear()
    _fxguard249._USED_FX.update(_old_used_fx249)

correction_item=watcher.base.query_news(watcher.FX249_CORRECTION_RECOVERY)
if base.NOW.astimezone(base.KST).date() <=dt.date(2026,10,26):
    assert len(correction_item)==1,correction_item
    fxitem=correction_item[0]
    fg,fs,fc,fk=classify(fxitem)
    assert fg=="alert_quality_fx_249" and fs>=11 and "환산" in fc,(fg,fs,fc)
    assert "1,992억원" in base.meaning(fc) and "1,991억원" in base.meaning(fc)
    assert fk!=bd_k and fk!=ek_k
    fx_text=fxitem["title"]+" "+fxitem["description"]
    assert base.category(fx_text,base.topic_group(fx_text))==fc
    assert base.key(fxitem)==fk
_correction_old_now=base.NOW
try:
    base.NOW=dt.datetime(2026,10,27,1,0,tzinfo=dt.timezone.utc)
    assert watcher.base.query_news(watcher.FX249_CORRECTION_RECOVERY)==[]
finally:
    base.NOW=_correction_old_now


# 59) LGES sodium-ion North American 30MWh trial: previously reported
# October-13 PLAN, repeated October-21. Planned test is NOT official
# testing commencement, approval, shipment, mass production or sales.
lges_na_sodium_plan = make(
    "LG에너지솔루션 오창 소듐이온 30MWh 북미 ESS 테스트 내년 상반기 계획",
    "LG에너지솔루션은 오창 파일럿 라인을 구축하고 소듐이온 ESS용 북미 "
    "고객 대상 30MWh 샘플 테스트를 내년 상반기 추진할 예정이다. "
    "2027년 첫 양산 목표는 아직 양산 개시 확정이 아니다.",
    "뉴스1",
)
g,s_,c,k = classify(lges_na_sodium_plan)
assert type(s_) is int, ('Score must be int, not human-facing verification text',s_)
assert g=="sodium_ion_battery" and s_ < 11, (g,s_,c)
assert c.endswith("현재 상용화 기준선"),c
assert "30mwh" not in c.lower(), "Plan must not be titled as actual approved customer shipment"

lges_na_oct21_reprint = make(
    "국내 배터리 3사 소금 배터리 시대 연다",
    "LG에너지솔루션은 충북 청주 오창 소듐이온배터리 파일럿 라인을 구축했다. "
    "북미 고객사 대상으로 30MWh 규모 ESS용 소듐이온 샘플 테스트를 진행하고 "
    "내년 첫 양산을 목표로 한다. 삼성SDI는 UPS용 소듐이온을 개발 중이고 "
    "SK온은 2027년 시제품 개발을 완료하고 2028년 상용화를 추진한다. "
    "CATL은 HyperStrong과 2026년 4월 3년간 60GWh 공급 협력계약을 체결했다. "
    "모건스탠리는 2030년 830GWh 시장을 전망한다.",
    "머니S",
)
rg,rs,rc,rk=classify(lges_na_oct21_reprint)
assert type(rs) is int, ('Sodium press score type invalid',rs)
assert rg=="sodium_ion_battery" and rs<11,(rg,rs,rc)
assert rk==k, "Same 30MWh test plan on 10/13 and 10/21 must share event key"

lges_press_test_start = make(
    "LG에너지솔루션, 북미 30MWh 소듐이온 ESS 고객 샘플 시험 개시",
    "LG에너지솔루션은 북미 고객용 소듐이온 ESS 30MWh 샘플 시험을 "
    "실제 시작했다고 발표했다. 아직 고객 승인·양산 계약은 없다.",
    "LG에너지솔루션",
)
pg,ps,pc,pk=classify(lges_press_test_start)
assert type(ps) is int, ('Official sodium trial score type invalid',ps)
assert pg==g and ps>=11 and pk!=k,(pg,ps,pc,pk)
assert pc.endswith("LG엔솔 북미 30MWh 나트륨 ESS 샘플 시험 공식 착수"),pc
assert "상업 수주나 양산 출하가 아닙니다" in base.meaning(pc),base.meaning(pc)
actual_render_text=lges_press_test_start["title"]+" "+lges_press_test_start["description"]
assert base.category(actual_render_text,pg)==pc,"Rendered stage must not downgrade to plan"

lges_press_approved = make(
    "LG에너지솔루션 북미 30MWh 소듐이온 ESS 고객 승인",
    "LG에너지솔루션은 북미 고객의 소듐이온 ESS 30MWh "
    "샘플 검증 완료와 고객 승인을 공식 발표했다.",
    "LG에너지솔루션",
)
ag,aps,ac,ak=classify(lges_press_approved)
assert type(aps) is int, ('Sodium customer approval score type invalid',aps)
assert ag==g and aps>=11 and ak not in {k,pk},(ag,aps,ac,ak)
assert ac.endswith("한국 나트륨이온 고객 검증·승인"),ac
assert base.category(lges_press_approved["title"]+" "+lges_press_approved["description"],ag)==ac

lges_media_claim = make(
    lges_press_approved["title"],
    lges_press_approved["description"],
    "익명 뉴스",
)
mg,ms,mc,mk=classify(lges_media_claim)
assert mg==g and ms<11,(mg,ms,mc)

# CATL's existing April 60 GWh actual cooperation and SamsungSDI UPS R&D
# remain distinct baselines, not new Korean sodium contracts.
catl_sodium_prior=make(
    "CATL HyperStrong 60 GWh sodium-ion supply agreement",
    "CATL and HyperStrong signed 3 year 60GWh ESS sodium-ion cooperation agreement April 27 2026.",
    "CATL",
)
cg,cs,cc,ck=classify(catl_sodium_prior)
assert cg=="sodium_ion_battery" and cs<11,(cg,cs,cc)
assert ck != k,"Chinese contracted volume and Korean test plan must have different IDs"


# Oct-21 SEM Mexico investment REPORTED and Samsung RX visit PLANNED.
assert "SAMSUNG_ROBOT_OCT21_RECOVERY=" in watcher.__dict__.get(
    "_watcher_source", Path(__file__).with_name("physical_ai_watch_airan_guard.py").read_text()
)
sem_recovery=base.query_news(watcher.SAMSUNG_ROBOT_OCT21_RECOVERY+"sem_mexico")
rx_recovery=base.query_news(watcher.SAMSUNG_ROBOT_OCT21_RECOVERY+"samsung_rx_visit")
if base.NOW.astimezone(base.KST).date()<=dt.date(2026,10,26):
    assert len(sem_recovery)==1 and len(rx_recovery)==1
    sem=sem_recovery[0]
    sem_group=base.topic_group(sem["title"]+" "+sem["description"]+" "+sem["source"])
    assert sem_group=="sem_mexico_camera_robot",sem_group
    assert base.score(sem)>=11
    assert "미확인" in base.meaning(base.category(sem["title"]+" "+sem["description"],sem_group))
    assert base.key(sem)==base.key(dict(sem,title=sem["title"]+" (재게시)"))
    rx=rx_recovery[0]
    rx_group=base.topic_group(rx["title"]+" "+rx["description"]+" "+rx["source"])
    assert rx_group=="samsung_rx_leadership_visit",rx_group
    assert base.score(rx)==0, "planned CEO visit cannot be sent as achieved event"
    assert base.score(dict(rx,source="삼성전자"))==0
    assert "회사의 공식" not in rx["description"]
else:
    assert sem_recovery==[] and rx_recovery==[]

# Duplicate syndicated Google RSS URLs must not use two Telegram slots.
_ipo_stamp = "2026-10-23T05:32:00+00:00"
_ipo_one = dict(
    title="보스턴다이내믹스 기업공개 일정·조건 변화",
    description="IPO timetable article version A",
    source="머니투데이", published=_ipo_stamp,
    group="hyundai_atlas_rollout", score=13, key="duplicate-feed-a",
    link="https://news.google.com/rss/articles/one",
)
_ipo_two = dict(_ipo_one, key="duplicate-feed-b",
                link="https://news.google.com/rss/articles/two",
                description="IPO timetable article version B")
_ipo_other_day = dict(_ipo_one, key="other-day-event",
                      published="2026-10-24T05:32:00+00:00")
_unique_robot = dict(_ipo_one, key="distinct-news", group="robotis",
                     title="로보티즈 별개 수주 발표")
_ipo_selection = watcher._sro_select(
    [_ipo_one, _ipo_two, _ipo_other_day, _unique_robot], set(), False, 8
)
assert sum(x.get("published")==_ipo_stamp and x.get("group")=="hyundai_atlas_rollout"
           for x in _ipo_selection) <= 1, _ipo_selection
_ipo_pair_only = watcher._sro_select([_ipo_one, _ipo_two], set(), False, 8)
assert len(_ipo_pair_only) == 1, _ipo_pair_only
assert any(x.get("key") == "other-day-event" for x in _ipo_selection), _ipo_selection
assert any(x.get("key") == "distinct-news" for x in _ipo_selection), _ipo_selection


# 2026-10-25 physical-AI verified transitions, stale press recaps and first-party gates.
_now_robot26 = base.NOW
try:
    base.NOW = dt.datetime(2026,10,25,3,0,tzinfo=dt.timezone.utc)
    _robot26_keys = set()
    for event_id in watcher.R26_PRIORITY:
        event = watcher.R26_EVENTS[event_id]
        rows = base.query_news(watcher.R26_PREFIX + event_id)
        assert len(rows) == 1, (event_id, rows)
        row = rows[0]
        group,points,cat,event_key = classify(row)
        assert group == event["group"] and points >= 11 and cat == event["category"], (event_id,group,points,cat)
        assert base.meaning(cat) and base.risk(cat) and base.verification(row,group,row["description"])
        assert event_key not in _robot26_keys, "distinct milestones must never share state key"
        _robot26_keys.add(event_key)
        duplicate = dict(row, link="https://example.com/another-republished-link",
                         source="검증 없는 금융 블로그", r26_verified=False)
        dgroup,dscore,dcat,dkey = classify(duplicate)
        assert dgroup == group and dscore < 11 and dkey == event_key, (event_id,dgroup,dscore,dkey)
        assert event["stage"] == watcher._r26_stage(row,event_id)
    # A published product demo is not a supply contract or customer production.
    _hsb_news = make("LG이노텍 NVIDIA HSB 로봇 카메라 개발 검토",
                     "300만 화소 HSB 공개와 향후 양산·고객 계약 기대",
                     "무명테마블로그")
    g,s,c,k=classify(_hsb_news)
    assert g == "lge_nvidia_hsb_robot_sensing" and s < 11, (g,s,c)
    # Official actual milestone must not dedup into the existing launch baseline.
    _tesla_actual = make("Tesla Optimus Fremont first customer deliveries began",
                         "Tesla official first external deliveries began for paid factory customers.",
                         "Tesla")
    g,s,c,k = classify(_tesla_actual)
    assert g == "tesla_optimus_q3_fremont" and s >= 11, (g,s,c)
    assert k != base.key(base.query_news(watcher.R26_PREFIX+"tesla_fremont")[0])
    # Aspirational dates and 2028 Shanghai factory target do not create later stages.
    _policy_plan = make("상하이 산업서비스 AI 2027~2028년 지원",
                        "上海 工业服务业 人工智能 每项目最高2000万元 拟部署机器人8000台",
                        "자체 블로그")
    g,s,c,k=classify(_policy_plan)
    assert g == "shanghai_physical_ai_2027_policy" and s < 11, (g,s,c)
    base.NOW = dt.datetime(2026,10,31,3,0,tzinfo=dt.timezone.utc)
    for event_id in watcher.R26_PRIORITY:
        assert base.query_news(watcher.R26_PREFIX+event_id)==[],event_id
finally:
    base.NOW=_now_robot26

# The final shortlist must retain all six verified R26 events even when
# legacy selection already includes the LAST R26 event (Flora).
_now_r26_selection = base.NOW
try:
    base.NOW = dt.datetime(2026,10,25,3,0,tzinfo=dt.timezone.utc)
    _r26_candidates = []
    for _name in watcher.R26_PRIORITY:
        _event = base.query_news(watcher.R26_PREFIX + _name)[0]
        _text = _event["title"]+" "+_event.get("description","")+" "+_event.get("source","")
        _event = dict(_event, group=base.topic_group(_text),
                      score=base.score(_event), key=base.key(_event))
        _r26_candidates.append(_event)
    _chosen = base.select_diverse(_r26_candidates, set(), False, 8)
    assert len(_chosen) == 6, _chosen
    assert {x["group"] for x in _chosen} == {watcher.R26_EVENTS[n]["group"] for n in watcher.R26_PRIORITY}
    # Full shortlist with 8 old filler stories must still include 6 upgrades.
    _other_news = [dict(_r26_candidates[0], group="robotis", key=f"old-noise-{k}",
                        score=13, title=f"older robot headline {k}") for k in range(8)]
    _chosen = base.select_diverse(_other_news+_r26_candidates, set(), False, 8)
    assert {watcher.R26_EVENTS[n]["group"] for n in watcher.R26_PRIORITY}.issubset(
        {x["group"] for x in _chosen}), _chosen
finally:
    base.NOW=_now_r26_selection

_fake_sent = (
    "<b>신규 고신호 2건</b>\n━━━━━━━━━━━━━━━━━━\n"
    "<b>1. 22만5000원…로봇 양산·해외 수요 점검</b>\n"
    "──────────────────\n"
    "<b>2. 로봇 고객 공급계약 체결</b>\n"
    "──────────────────\n"
    "<b>판정 기준</b> 새 사실만\n"
)
_usable = watcher._drop_stock_price_sections(_fake_sent)
assert "22만5000원" not in _usable, _usable
assert "신규 고신호 1건" in _usable and "고객 공급계약" in _usable, _usable
assert watcher._r26_category("베어로보틱스 키노-2 신제품 공개", "lg_robotics") == watcher.R26_KINO_CAT
assert "외부 고객 수주나" in base.meaning(watcher.R26_KINO_CAT)

# One signed 2026-10-22 LG/K-water cooperation MOU recapped by multiple
# publishers must NEVER become 4 separate new customer-order alerts.
_sihwa_one = make(
    "LG전자 시화호 조력발전소 AI 전환·로봇 사업 협력",
    "LG전자는 K-water와 시화호 조력발전소 기술협력 MOU 체결, "
    "AI 디지털트윈 실증과 패트롤 로봇 적용 가능성 검토.",
    "연합뉴스")
_sihwa_two = make(
    "LG전자, 세계 최대 시화호 조력발전소 스마트팩토리 수주 확대 기대",
    "LG전자, 시화호 조력발전소 AI 전환 양해각서. "
    "스마트팩토리 누적 수주 1조원은 기존 회사 전체 사업 실적.",
    "지디넷코리아")
_sihwa_official_mou = make(
    "LG전자 K-water 시화호 조력발전소 AI 기술협력 MOU 체결",
    "LG전자·한국수자원공사 시화호 조력발전소에 AI 로봇 실증 협력 추진",
    "LG전자")
_sihwa_rows = [classify(x) for x in (_sihwa_one,_sihwa_two,_sihwa_official_mou)]
assert all(x[0]=="lg_sihwa_tidal_ai" and x[1]<11 for x in _sihwa_rows), _sihwa_rows
assert len({x[3] for x in _sihwa_rows})==1, _sihwa_rows
assert all(x[2]==watcher.R26_SIHWA_MOU_CAT for x in _sihwa_rows)
_sihwa_real = make(
    "LG전자 시화호 조력발전소 유상 공급계약 체결",
    "LG전자 한국수자원공사 시화호 조력발전소 유상 공급계약 체결 "
    "고객 부품 공급 업무 본계약 발표.",
    "LG전자")
g,s,c,k=classify(_sihwa_real)
assert g=="lg_sihwa_tidal_ai" and s>=11 and k!=_sihwa_rows[0][3], (g,s,c,k)
assert c==watcher.R26_SIHWA_ORDER_CAT,(c,k)
_ess_editorial = make("ESS 경쟁 격화…美·유럽 공급망 재편에 K-배터리 기회",
                      "에너지저장장치 가격 기대감과 공급망 재편 수혜 의견", "매일일보")
assert classify(_ess_editorial)[1]<11, classify(_ess_editorial)


# Microduck vs ROBOTIS actual order, and Giga Berlin car / battery / hall
# are independent semantic stages. Historical article recaps stay silent.
_r27_expected=(
    ("microduck_20k","microduck_pollen_robotis_orders",
     "Microduck · 회사 경영진 2만대 초과 사전주문"),
    ("berlin_7000","tesla_giga_berlin_modely_week",
     "Tesla 베를린 · 회사 발표 주간 7000대 실제 생산"),
)
_r27_baseline=[]
for eid,group,category in _r27_expected:
    row=base.query_news(watcher.R27_ROBOT_COMMERCE_PREFIX+eid)
    assert len(row)==1,(eid,row)
    g,s,c,k=classify(row[0])
    assert g==group and s>=11 and c==category,(eid,g,s,c)
    assert k not in {i[3] for i in _r27_baseline}
    _r27_baseline.append((g,s,c,k,dict(row[0],group=g,score=s,key=k)))
assert len(watcher.R27_LIVE_QUERIES)==5
_m_reprint=make("Microduck 4000 sales after NVIDIA keynote",
                "Microduck 10000 earlier preorders, 15 motors",
                "재인용언론")
mg,ms,mc,mk=classify(_m_reprint)
assert mg=="microduck_pollen_robotis_orders" and ms==0 and mk==_r27_baseline[0][3],(mg,ms,mk)
_false_order=make("Microduck ROBOTIS XL330 150000 units confirmed",
                  "These are 10000 robots times 15 servos, an estimated need, not a signed order",
                  "증권사 자료")
assert classify(_false_order)[1]==0
_real_order=make("Microduck XL330 signed firm purchase order 300000 units",
                 "Microduck DYNAMIXEL XL330 signed firm purchase order 300000 units",
                 "ROBOTIS")
og,os,oc,ok=classify(_real_order)
assert og==mg and os>=11 and ok!=mk,(og,os,oc)
_real_ship=make("Microduck first orders shipped", "Microduck first orders shipped today",
                "Pollen Robotics")
sg,ss,sc,sk=classify(_real_ship)
assert sg==mg and ss>=11 and sk!=mk and sk!=ok,(sg,ss,sc)
_preorder_target=make("Microduck preorders target 50000 units",
                       "Microduck preorders target 50000 units in 2027",
                       "Pollen Robotics")
assert classify(_preorder_target)[1]==0
_b_reprint=make("Tesla Giga Berlin built 7000 Model Y this week",
                "Tesla built 7000 Model Y in one week, annualized 364000 is mathematical only",
                "자동차기사")
bg,bs,bc,bk=classify(_b_reprint)
assert bg=="tesla_giga_berlin_modely_week" and bs==0 and bk==_r27_baseline[1][3]
_b_actual=make("Tesla Giga Berlin 7500 Model Y actually produced in one week",
               "Tesla Giga Berlin built 7500 Model Y in a week",
               "Tesla Manufacturing")
ag,ap,ac,ak=classify(_b_actual)
assert ag==bg and ap>=11 and ak!=bk,(ag,ap,ac)
_b_target=make("Tesla Giga Berlin target 7500 Model Y weekly production",
               "Tesla aims for 7500 Model Y per week",
               "Tesla Manufacturing")
assert classify(_b_target)[1]==0
_hall_planned=make("Tesla Giga Berlin second hall permit filing planned",
                    "Tesla Giga Berlin second hall 536000 square metres, planned permit application",
                    "Tesla Manufacturing")
assert classify(_hall_planned)[1]==0
_hall_filed=make("Tesla Giga Berlin second hall permit filed",
                  "Tesla Giga Berlin second hall permit filed with Brandenburg authority",
                  "Tesla Manufacturing")
hg,hs,hc,hk=classify(_hall_filed)
assert hg=="tesla_berlin_second_hall" and hs>=11,(hg,hs,hc)
_cells_plan=make("Tesla Giga Berlin 4680 battery 18GWh planned",
                  "Tesla Giga Berlin 4680 18GWh 2027 target, not started",
                  "Tesla Manufacturing")
assert classify(_cells_plan)[1]==0
_cells_actual=make("Tesla Giga Berlin 4680 cell production started",
                    "Tesla Giga Berlin 4680 cell production started this week",
                    "Tesla Manufacturing")
cg,cs,cc,ck=classify(_cells_actual)
assert cg=="tesla_berlin_4680_cells" and cs>=11,(cg,cs,cc)
_r27_selected=watcher._r27_select([_r27_baseline[1][4],_r27_baseline[0][4]],set(),False,8)
assert len(_r27_selected)==2 and len({x["key"] for x in _r27_selected})==2,_r27_selected


# Oct-26 Atlas ETNews supplier report is distinct from confirmed contracts.
_atlas_save_now=base.NOW
try:
  base.NOW=dt.datetime(2026,10,27,0,0,tzinfo=dt.timezone.utc)
  ar=base.query_news(watcher.ATLAS26_REPORT_QUERY)
  assert len(ar)==1,ar
  ag,ass,ac,ak=classify(ar[0])
  assert ag=="atlas_etnews_parts_report" and ass>=11 and "업계 취재" in ac,(ag,ass,ac)
  assert base.tag_for(ag)=="현대차 Atlas 공급망(보도)"
  assert "공식 확인 전" in base.meaning(ac)
  known=[dict(ar[0],key=ak,group=ag,score=ass)]
  assert watcher._atlas26_select(known,set(),False,8)[0]["key"]==ak
  syndicated=make(
    "Atlas 공급망 현대모비스·삼성SDI·나무가·엠씨넥스·캠시스",
    "Atlas 카메라 나무가 엠씨넥스 캠시스 삼성SDI 배터리 보도 재인용",
    "일반 언론"
  )
  assert classify(syndicated)[1]==0, "Reprint is not new vendor confirmation"
  actual=make(
    "Atlas 카메라 공급계약 체결 공식 확인",
    "나무가 Atlas 카메라 공급계약 체결 및 구매 발주서 확정",
    "나무가"
  )
  ug,us,uc,uk=classify(actual)
  assert ug=="atlas_part_supplier_official_upgrade" and us>=11 and uk!=ak,(ug,us,uc)
  assert base.tag_for(ug)=="Atlas 공급사 공식 단계"
  assert "검수" in base.risk(uc)
  replay=make(
    "삼성SDI 美 AOP ESS 1GWh 2차 공급 보도",
    "삼성SDI 미국 알파오메가 ESS 1GWh 추가 공급 1.5GWh 누적",
    "기존 기사"
  )
  replay["published"]="2026-10-26T09:00:00+09:00"
  assert classify(replay)[1]==0, "AOP October 26 repeat should stay silent"
  distinct=make(
    "삼성SDI 미국 다른 고객 ESS 2GWh 공급계약",
    "삼성SDI 새로운 미국 고객과 ESS 2GWh 신규 공급계약",
    "삼성SDI"
  )
  assert not watcher._atlas26_aop_reprint(distinct)
  base.NOW=dt.datetime(2026,11,2,0,0,tzinfo=dt.timezone.utc)
  assert base.query_news(watcher.ATLAS26_REPORT_QUERY)==[]
finally:
  base.NOW=_atlas_save_now

# Oct 26-27 added robotics lanes: press vs official upgrade, recurring press
# aliases, and source-unverified customer speculation must not become sales.
_oct27_now=base.NOW
try:
    base.NOW=dt.datetime(2026,10,27,7,0,tzinfo=dt.timezone.utc)
    for _code,_group,_label in (
        ("DIRECT_TIROBOTICS_DOW_PRESS_20261026","tirobotics_dow_reported",
         "조건부 승인 회사발표"),
        ("DIRECT_SAMSUNG_ATLAS_FINGER_PRESS_20261026",
         "samsung_hand_10_atlas_8_reported","10개 대 8개"),
    ):
        _rows=base.query_news(_code)
        assert len(_rows)==1,(_code,_rows)
        _g,_s,_cat,_k=classify(_rows[0])
        assert _g==_group and _s>=11,(_code,_g,_s,_cat)
        assert _label in _cat,(_code,_cat)
        if _group=="tirobotics_dow_reported":
            assert "승인서" in base.risk(_cat), (_group,_cat,base.risk(_cat))
        else:
            assert "수율" in base.risk(_cat), (_group,_cat,base.risk(_cat))
    _t2=make("티로보틱스 AMR 미국 조건부 승인 재보도",
             "티로보틱스 AGV AMR DoW 조건부 승인 보도 재인용","언론사")
    assert classify(_t2)[0]=="tirobotics_dow_reported"
    assert classify(_t2)[1]==0,classify(_t2)
    _on=make("티로보틱스 AMR 정부 공식 승인번호 공개",
             "티로보틱스 AMR DoW 조건부 승인 공식 승인번호 제품별 승인 목록 공개",
             "티로보틱스")
    _og,_os,_oc,_ok=classify(_on)
    assert _og=="tirobotics_dow_reported" and _os>=11 and _ok!=classify(_t2)[3]
    _ep=make("LG에너지솔루션 에너직스 유럽 ESS 공급 협력",
             "LG에너지솔루션 에너직스 2GWh ESS 최대 4.5GWh 협력 추진","전자신문")
    _ep2=make("LG에너지솔루션 Energix 최대 4.5GWh 협력",
              "LG Energy Solution Energix ESS 2GWh 유럽 북미","조세일보")
    for _r in (_ep,_ep2):
        _rg,_rs,_rc,_rk=classify(_r)
        assert _rg=="lges_energix_ess_20261027" and _rs==0,(_rg,_rs)
        assert _rk==watcher.LGES_ENERGIX_ALREADY_SENT_KEY,(_rk,_rg)
    _contract=make("LG에너지솔루션 Energix ESS 정식 공급계약 체결",
                   "LG에너지솔루션은 Energix ESS 2GWh 정식 공급 계약 체결", "LG에너지솔루션")
    _cg,_cs,_cc,_ck=classify(_contract)
    assert _cg=="lges_energix_ess_20261027" and _cs>=11,(_cg,_cs)
    assert _ck!=watcher.LGES_ENERGIX_ALREADY_SENT_KEY
    _pim=make("한국피아이엠 북미 휴머노이드 관절부품 3종 개발 공급",
              "한국피아이엠 북미 고객 손 관절용 감속기 3종 개발 협력","일반 보도")
    assert classify(_pim)[1]==0, "Unverified PIM customer must not become contracted sales"
    _pim_signed=make("한국피아이엠 북미 휴머노이드 감속기 공식 계약",
              "한국피아이엠 북미 고객 휴머노이드 손 감속기 3종 정식 공급계약 체결",
              "한국피아이엠")
    assert classify(_pim_signed)[1]>=11
    base.NOW=dt.datetime(2026,11,2,0,0,tzinfo=dt.timezone.utc)
    for _code in watcher.OCT27_UPDATES:
        assert base.query_news(_code)==[],_code
finally:
    base.NOW=_oct27_now

print("Physical-AI watcher regression guards: PASS")
