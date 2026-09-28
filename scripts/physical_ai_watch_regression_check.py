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

print("Physical-AI watcher regression guards: PASS")
