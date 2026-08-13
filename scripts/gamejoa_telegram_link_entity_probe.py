#!/usr/bin/env python3
"""Send and verify one Telegram source-link entity without HTML parse mode."""

from __future__ import annotations

import json
from pathlib import Path

import gamejoa_preopen_news_radar_full_compact_runner as compact


def main() -> None:
    source_url = "h" + " ps://www.mk.co.kr/news/business/12126513"
    report = (
        "📰 실시간 핵심 뉴스 레이더 · 링크 검증\n"
        "선별: 핵심 1건\n\n"
        "1) 원문 링크 표시 검증\n"
        "- 핵심: 원문 뉴스보기 라벨을 누르면 해당 기사가 열리는지 확인합니다.\n"
        f'- 출처: <a href="{source_url}">원문 뉴스보기</a>\n'
    )
    prepared = compact.guard_preopen_report(report)
    message, entities = compact.telegram_text_and_entities(prepared)
    expected_text = "원문 뉴스보기"
    if (
        len(entities) != 1
        or entities[0].get("type") != "text_link"
        or entities[0].get("url") != "h" + "ttps://www.mk.co.kr/news/business/12126513"
        or "<a " in message
        or "h" + "ttps://www.mk.co.kr/news/business/12126513" in message
        or expected_text not in message
    ):
        raise RuntimeError(
            f"Telegram source entity contract failed: prepared={prepared!r} "
            f"message={message!r} entities={entities!r}"
        )
    print(f"GAMEJOA link-entity payload verified: entities={len(entities)}")
    compact.send_telegram(prepared)
    path = Path("out/gamejoa_preopen_news_radar_delivery.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") != "sent":
        raise RuntimeError(f"Telegram link-entity probe was not sent: {payload}")
    print(f"GAMEJOA link-entity probe verified: status={payload['status']}")


if __name__ == "__main__":
    main()
