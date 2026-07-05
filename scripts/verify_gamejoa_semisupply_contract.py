#!/usr/bin/env python3
"""Verify GAMEJOA semiconductor supply-chain source coverage."""

from __future__ import annotations

import datetime as dt
import importlib
import sys
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


SAMPLES = [
    {
        "publisher": "TrendForce",
        "source": "TrendForce semiconductor research",
        "title": "New HBM Market Outlook: HBM Suppliers Seize Pricing Power as AI Demand Fuels Explosive Contract Price Surge",
        "summary": "As 2027 HBM4 supply negotiations launch in 2Q26, TrendForce expects suppliers to push through substantial contract price hikes, reflecting acute supply-demand imbalance and rising next-generation manufacturing costs.",
        "link": "https://www.trendforce.com/research/download/RP260527UC",
        "expected": "TrendForce, 2027년 HBM4 계약가 대폭 인상 전망",
    },
    {
        "publisher": "TrendForce",
        "source": "Trusted news TrendForce notebook",
        "title": "Apple's Across-the-Board Price Increases Add Uncertainty to Consumer Demand; Global Notebook Shipments Forecast to Decline 13.6% in 2026, Says TrendForce",
        "summary": "MacBook price increases consumer demand notebook shipments memory costs AI server demand",
        "link": "https://www.trendforce.com/presscenter/news/20260701-13130.html",
        "expected": "TrendForce, 맥북 가격 인상 여파로 2026년 노트북 수요 둔화 전망",
    },
    {
        "publisher": "TrendForce",
        "source": "Trusted news TrendForce MLCC",
        "title": "[News] Passive Component Prices Rise as YAGEO Reportedly Begins Broadest Capacitor Hike in Years on July 1",
        "summary": "MLCC aluminum electrolytic capacitors price hike X6S AI ASIC shortage lead time",
        "link": "https://www.trendforce.com/news/2026/07/01/news-passive-component-prices-rise-as-yageo-reportedly-begins-broadest-capacitor-hike-in-years-on-july-1/",
        "expected": "TrendForce, MLCC·알루미늄 콘덴서 가격 인상/쇼티지 신호",
    },
    {
        "publisher": "Wccftech",
        "source": "Trusted news CO2",
        "title": "CO2 Shortage Threatens Advanced Semiconductor Supply as South Korean Refineries Slash Output Amid Middle East Crude Uncertainty",
        "summary": "high-purity CO2 Samsung SK Hynix advanced semiconductor packaging HBM 3D NAND",
        "link": "https://wccftech.com/co2-shortage-threatens-advanced-semiconductor-supply/",
        "expected": "반도체용 고순도 CO₂ 재고 부족: 삼성전자·SK하이닉스 소재 리스크",
    },
    {
        "publisher": "Tom's Hardware",
        "source": "Tom's Hardware RSS",
        "title": "Intel 18A wafer-to-wafer yield issues fixed, report claims - says production up to 15,000 wafers per month at both sites",
        "summary": "Intel 18A wafer-to-wafer yield BlueFin foundry process wafers",
        "link": "https://www.tomshardware.com/tech-industry/semiconductors/intel-18a-wafer-to-wafer-yield-issues-fixed-report-claims-says-production-up-to-15-000-wafers-per-month-at-both-sites",
        "expected": "Intel 18A 수율 개선·애플 듀얼 파운드리 가능성 체크",
    },
    {
        "publisher": "ServeTheHome",
        "source": "ServeTheHome RSS",
        "title": "AMD Pivots From HBM to LPDDR5X For New Versal Premium Gen 2 Memory on Package Chips",
        "summary": "AMD Versal Premium Gen 2 memory on package LPDDR5X HBM shortage adaptive SoC",
        "link": "https://www.servethehome.com/amd-pivots-from-hbm-to-lpddr5x-for-new-versal-premium-gen-2-memory-on-package-chips/",
        "expected": "AMD Versal, HBM 대신 LPDDR5X 채택: HBM 병목 대체 설계 신호",
    },
]


def main() -> int:
    prod = importlib.import_module("gamejoa_preopen_news_radar_fda_quality_runner")
    now = dt.datetime(2026, 7, 4, 6, 30, tzinfo=ZoneInfo("Asia/Seoul"))
    errors: list[str] = []

    research_html = """
    <a href="/research/download/RP260527UC">New HBM Market Outlook：HBM Suppliers Seize Pricing Power as AI Demand Fuels Explosive Contract Price Surge</a>
    2026/05/27
    As 2027 HBM4 supply negotiations launch in 2Q26, TrendForce expects suppliers to push through substantial contract price hikes,
    reflecting acute supply-demand imbalance and rising next-generation manufacturing costs.
    """
    fresh_research_now = dt.datetime(2026, 5, 28, 6, 30, tzinfo=ZoneInfo("Asia/Seoul"))
    research_rows = prod.current.parse_trendforce_research_items(research_html, fresh_research_now)
    if not research_rows:
        errors.append("TrendForce research parser missed HBM4 contract price item")
    elif research_rows[0].get("source_published") is None:
        errors.append("TrendForce research parser missed source date")
    elif research_rows[0].get("published") != research_rows[0].get("source_published"):
        errors.append("TrendForce research parser must keep source date as published date")

    stale_research_rows = prod.current.parse_trendforce_research_items(research_html, now)
    if stale_research_rows:
        errors.append("stale TrendForce HBM4 research item was not excluded")

    duplicate_a = {
        "news": "TrendForce, AI 서버가 메모리 가격 지지하나 소비 수요 둔화 체크",
        "original_news": "AI Server Demand Continues to Support Memory Prices in 3Q26, but Gains Moderate as Consumer Demand Weakens and High Base Effects Take Hold, Says TrendForce",
        "publisher": "TrendForce semiconductor RSS",
        "published": "2026-07-03T14:49+09:00",
    }
    duplicate_b = dict(duplicate_a, publisher="TrendForce", original_news=f"{duplicate_a['original_news']} - TrendForce")
    if prod.runner.alert_dedup_key(duplicate_a) != prod.runner.alert_dedup_key(duplicate_b):
        errors.append("TrendForce duplicate dedupe key mismatch")

    for sample in SAMPLES:
        row = dict(sample)
        expected = row.pop("expected")
        row["published"] = now
        alert = prod.contract.strict.classify(row, now)
        if not alert:
            errors.append(f"not selected: {sample['title']}")
            continue
        title = prod.runner.korean_title(alert)
        if title != expected:
            errors.append(f"title mismatch: {title} != {expected}")
        impacts = set(alert.get("impacts") or [])
        if not impacts.intersection({"매출·마진·현금흐름", "밸류에이션/할인율", "수급", "시간표"}):
            errors.append(f"decision impact missing: {sample['title']}")
        sectors = prod.runner.curated_sectors(alert)
        if not sectors:
            errors.append(f"sectors missing: {sample['title']}")

    if errors:
        for error in errors:
            print(f"GAMEJOA semisupply contract error: {error}")
        return 1
    print("GAMEJOA semisupply contract OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
