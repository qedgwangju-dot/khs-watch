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

print("Physical-AI watcher regression guards: PASS")
