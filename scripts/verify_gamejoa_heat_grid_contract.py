
#!/usr/bin/env python3
"""Regression gate for heat-driven Korean distribution-grid outage alerts."""

from datetime import datetime

import gamejoa_preopen_news_radar_fda_quality_runner as quality


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
        "link": "https://example.com/seoul-heat-grid-outage",
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

    weather_only = {
        "title": "서울 폭염과 열대야 이어져",
        "source_body": "서울의 낮 기온이 크게 올라 무더위가 이어졌다.",
        "published": now,
    }
    weather_text = f"{weather_only['title']} {weather_only['source_body']}".lower()
    if quality.heat_grid_outage_alert(weather_only, now, weather_text):
        raise SystemExit("heat_grid_contract=generic_weather_promoted")

    print("heat_grid_contract=passed material_outage=yes generic_weather=blocked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

