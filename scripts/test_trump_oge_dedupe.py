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

    from trump_oge_2026_08_event import (
        EVENT_KEY, is_august_news, is_august_official_filing, build_august_report
    )

    cnbc = {
        "title": "Trump bought up to $25 million in Meta and millions in SpaceX debt in August",
        "desc": "517 trades in the latest financial disclosure",
        "published": "Thu, 08 Oct 2026 15:00:00 GMT",
    }
    reuters = {
        "title": "Trump discloses Nvidia stock trades as he prepares to honor CEO Huang",
        "desc": "According to August financial disclosure",
        "published": "Thu, 08 Oct 2026 15:30:00 GMT",
    }
    old = {
        "title": "Trump bought shares in Elon Musk's SpaceX in June, financial disclosure shows",
        "desc": "Previously disclosed purchase",
        "published": "Tue, 22 Sep 2026 12:00:00 GMT",
    }
    assert is_august_news(cnbc)
    assert is_august_news(reuters)
    assert not is_august_news(old)
    assert oge._fallback_event_key(cnbc) == EVENT_KEY
    assert oge._fallback_event_key(reuters) == EVENT_KEY
    assert oge._fallback_event_key(old) != EVENT_KEY
    assert is_august_official_filing(
        "https://example.org/Donald-J-Trump-09.17.2026-278T.pdf"
    )

    msg = build_august_report(1342.78, "2026-10-09", oge.watch.krw_range)
    assert "517건" in msg
    assert "메타(META) 주식" in msg
    assert "SpaceX 선순위 무담보 회사채" in msg
    assert "2031년 7월" in msg
    assert "500만~2,500만달러 (약 " in msg
    assert "100만~500만달러 (약 " in msg
    assert "7월 신고" not in msg or "기존 6·7월 재보도 아님" in msg
    assert "전체 보유자산" in msg
    assert not oge._has_verified_oge_rows([], set())
    assert not oge._has_verified_oge_rows([{"date":"8/21/2026"}], {"2026-08"})
    assert oge._has_verified_oge_rows([{}, {}, {}], {"2026-08"})

    print("Trump OGE dedupe regression checks passed.")


if __name__ == "__main__":
    main()
