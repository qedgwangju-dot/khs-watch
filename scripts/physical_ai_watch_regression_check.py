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
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Catch accidental deletion of existing watcher lanes before importing them.
# This protects all active categories during targeted article-source edits.
_watcher_source_path = Path(__file__).with_name("physical_ai_watch_airan_guard.py")
_watcher_source = _watcher_source_path.read_text(encoding="utf-8")
for _required in (
    "DONGKUK_NPS_RECOVERY =",
    "DKT_HUMANOID_RECOVERY =",
    "TESLA_TOUCH_PATENT_RECOVERY =",
    "DIGITAL_OPTIMUS_GAME_RECOVERY =",
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


print("Physical-AI watcher regression guards: PASS")
