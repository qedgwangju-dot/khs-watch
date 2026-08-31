#!/usr/bin/env python3
"""Regression gate for heat-driven Korean distribution-grid outage alerts."""

from datetime import datetime
from pathlib import Path
import sys

# The wrapper can execute this file from the project root, where another
# checkout may expose modules with the same names. Pin every radar import to
# the sibling scripts directory so this gate tests the code under test.
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path = [str(SCRIPT_DIR)] + [
    path
    for path in sys.path
    if Path(path or ".").resolve() not in {SCRIPT_DIR, SCRIPT_DIR.parent}
]
for module_name in (
    "gamejoa_preopen_news_radar_fda_quality_runner",
    "gamejoa_preopen_news_radar_semisupply_runner",
    "gamejoa_preopen_news_radar_memory_antitrust_runner",
    "gamejoa_preopen_news_radar_korea_nuclear_siting_runner",
    "gamejoa_preopen_news_radar_full_compact_runner",
):
    loaded = sys.modules.get(module_name)
    loaded_path = getattr(loaded, "__file__", "") if loaded else ""
    if loaded_path and Path(loaded_path).resolve().parent != SCRIPT_DIR:
        del sys.modules[module_name]

import gamejoa_preopen_news_radar_fda_quality_runner as quality

if Path(quality.__file__).resolve().parent != SCRIPT_DIR:
    raise SystemExit(
        "heat_grid_contract=wrong_runner_path:" + str(quality.__file__)
    )


def main() -> int:
    now = datetime.now().astimezone()
    search_names = {item[0] for item in quality.runner.KOREAN_BUSINESS_SEARCH_SOURCES}
    if "국내 폭염·전력피크·아파트 정전" not in search_names:
        raise SystemExit("heat_grid_contract=missing_search")

    row = {
        "title": "서울 아파트 정전 잇따라…극한 폭염에 변압기 과부하",
        "source_title": "서울 아파트 정전 잇따라…극한 폭염에 변압기 과부하",
        "source_body": (
            "극한 폭염과 열대야로 냉방 전력 사용량이 급증하면서 서울 곳곳의 "
            "아파트에서 정전 사고가 발생했다. 변압기 불량과 과부하가 원인으로 확인됐다."
        ),
        "published": now,
        "link": "https://www.newsis.com/view/NISX20260804_0003736539",
    }
    text = f"{row['source_title']} {row['source_body']}".lower()
    alert = quality.heat_grid_outage_alert(row, now, text)
    if not alert:
        raise SystemExit("heat_grid_contract=material_event_blocked")
    if alert.get("korean_business_kind") != "korea_heat_grid_outage":
        raise SystemExit("heat_grid_contract=wrong_kind")
    if "배전용 변압기/차단기" not in alert.get("sectors", []):
        raise SystemExit("heat_grid_contract=missing_sector")
    if "정전" not in str(alert.get("telegram_core_fact") or ""):
        raise SystemExit("heat_grid_contract=source_fact_missing")
    if not quality.source_output_aligned(alert):
        raise SystemExit("heat_grid_contract=valid_source_rejected")

    weather_only = {
        "title": "서울 폭염과 열대야 이어져",
        "source_body": "서울의 낮 기온이 크게 올라 무더위가 이어졌다.",
        "published": now,
    }
    weather_text = f"{weather_only['title']} {weather_only['source_body']}".lower()
    if quality.heat_grid_outage_alert(weather_only, now, weather_text):
        raise SystemExit("heat_grid_contract=generic_weather_promoted")

    contaminated = {
        "title": "폭염 속 서울 아파트 정전 잇따라…영등포·동대문 주민 불편(종합)",
        "source_title": "폭염 속 서울 아파트 정전 잇따라…영등포·동대문 주민 불편(종합)",
        "source_body": (
            "하태경 금융위 AI 투자 반대로 사업 좌초 위기라고 말했다. "
            "삼전닉스 본격 반등과 외국인 수급을 점검해야 한다."
        ),
        "published": now,
        "link": "https://example.com/contaminated-newsis-page",
    }
    contaminated_text = f"{contaminated['source_title']} {contaminated['source_body']}".lower()
    if quality.heat_grid_outage_alert(contaminated, now, contaminated_text):
        raise SystemExit("heat_grid_contract=unrelated_body_promoted")

    poisoned = dict(alert)
    poisoned["telegram_core_fact"] = (
        "하태경 금융위 AI 투자 반대와 삼성전자·SK하이닉스 외국인 수급을 점검한다."
    )
    poisoned["policy_plain_summary"] = poisoned["telegram_core_fact"]
    if quality.source_output_aligned(poisoned):
        raise SystemExit("heat_grid_contract=title_body_mismatch_sent")

    print(
        "heat_grid_contract=passed material_outage=yes generic_weather=blocked "
        "contaminated_body=blocked title_body_mismatch=blocked"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

