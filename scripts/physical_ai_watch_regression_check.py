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

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import physical_ai_watch_airan_guard as watcher

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
assert c.endswith("7억달러 투자유치 공식 종결"), c
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

print("Physical-AI watcher regression guards: PASS")
