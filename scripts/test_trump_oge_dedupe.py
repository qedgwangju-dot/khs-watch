#!/usr/bin/env python3
"""Regression guards for Trump OGE event dedupe and source-link rendering."""
import trump_oge_portfolio_watch_entry as oge


def main():
    mstr = {
        "id": "test-korean-mstr-repost",
        "title": "트럼프, 스트래티지 주식 또 샀다…최대 1.3억원 어치 매입",
        "period": "",
        "published": "2026-09-24",
    }
    assert oge._detail_kind(mstr) == "july-mstr-trades"
    assert oge._fallback_event_key(mstr) == "oge-detail:2026-07:july-mstr-trades"

    rendered = oge._telegram_html("원문: https://example.com/path")
    assert 'href="https://example.com/path"' in rendered
    assert ">원문</a>" in rendered

    print("Trump OGE dedupe regression checks passed.")


if __name__ == "__main__":
    main()
