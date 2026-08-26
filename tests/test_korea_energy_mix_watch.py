import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.korea_energy_mix_watch import (
    classify,
    collapse_events,
    event_key,
    event_level,
    korean_date,
    parse_rss,
    render,
    topic_match,
)


def test_topic_match_all_power_plan_mentions():
    assert topic_match("제12차 전기본 재생에너지 2040년 220GW 전망") is True
    assert topic_match("제12차 전기본 총괄위원회 회의") is True
    assert topic_match("제12차 전력수급기본계획 정부안 확정") is True
    assert topic_match("일반 태양광 기업 신제품 출시") is False


def test_classifies_renewable_and_nuclear():
    assert classify("12차 전기본 재생에너지 220GW")[0] == "재생에너지·전원믹스"
    assert classify("12차 전기본 신규 원전 논의")[0] == "원전·전원믹스"


def test_rss_trusted_media_filter_and_korean_date():
    xml = """
    <rss><channel><item>
      <title>제12차 전력수급기본계획 재생에너지 220GW 전망</title>
      <source>연합뉴스</source>
      <link>https://example.com/story</link>
      <guid>story-1</guid>
      <pubDate>Wed, 26 Aug 2026 07:00:00 GMT</pubDate>
    </item></channel></rss>
    """
    rows = parse_rss(xml, "국내 주요 언론", False)
    assert len(rows) == 1
    assert korean_date(rows[0]["published"]) == "2026년 8월 26일"


def test_render_is_readable_and_ranks_2040_capacity():
    body = render([
        {
            "title": "2040년 재생에너지 220GW 보급…태양광 155GW·풍력 61GW - 뉴시스",
            "publisher": "뉴시스",
            "source": "국내 주요 언론",
            "official": False,
            "url": "https://example.com/story",
            "published": "Wed, 26 Aug 2026 07:00:00 GMT",
            "category": "재생에너지·전원믹스",
            "plan_stage": "전망·잠정안",
            "stage": 6,
            "id": "x",
        }
    ])
    assert "#" not in body
    assert "2026년 8월 26일" in body
    assert "<b>핵심 분야</b>" in body
    assert "<b>전기본 단계</b>" in body
    assert "<b>2040년 보급량 순위</b>" in body
    assert "1위  태양광  <b>155GW</b>" in body
    assert "2위  해상풍력  <b>45GW</b>" in body
    assert "3위  육상풍력  <b>16GW</b>" in body
    assert "자가용 태양광 포함 전체  <b>약 236GW</b>" in body
    assert "해상풍력 0.4 → 45GW  <b>112.5배</b>" in body
    assert "<b>투자 의미</b>" in body
    assert '<a href="https://example.com/story"><b>기사 원문 보기</b></a>' in body


def _row(title: str, publisher: str, item_id: str, official: bool = False):
    return {
        "title": title,
        "publisher": publisher,
        "source": "기후에너지환경부 공식" if official else "국내 주요 언론",
        "official": official,
        "url": f"https://example.com/{item_id}",
        "published": "Wed, 26 Aug 2026 07:00:00 GMT",
        "category": "재생에너지·전원믹스",
        "plan_stage": "전망·잠정안",
        "stage": 6,
        "id": item_id,
    }


def test_same_renewable_event_has_same_semantic_key():
    rows = [
        _row('"15년 뒤 재생에너지 설비 용량, 현재의 5.6배로 증가 전망" - 연합뉴스', "연합뉴스", "a"),
        _row("2040년 재생에너지 6배 확대…태양광 155GW·육해상풍력 61GW - 머니투데이", "머니투데이", "b"),
        _row("2040년 재생E 220GW…기후부, 12차 전기본 토론회 - 뉴스1", "뉴스1", "c"),
    ]
    keys = {event_key(row) for row in rows}
    assert len(keys) == 1


def test_collapse_events_keeps_only_one_media_item():
    rows = [
        _row('"15년 뒤 재생에너지 설비 용량, 현재의 5.6배로 증가 전망" - 연합뉴스', "연합뉴스", "a"),
        _row("2040년 재생E 220GW…기후부, 12차 전기본 토론회 - 뉴스1", "뉴스1", "b"),
        _row("2040년 재생E 220GW…기후부, 12차 전기본 토론회 - 뉴스1", "뉴스1", "c"),
    ]
    collapsed = collapse_events(rows)
    assert len(collapsed) == 1
    assert len(collapsed[0]["members"]) == 3
    assert collapsed[0]["publisher"] == "연합뉴스"


def test_official_source_is_a_material_upgrade():
    media = _row("2040년 재생에너지 220GW 전망 - 연합뉴스", "연합뉴스", "a")
    official = _row("제12차 전기본 재생에너지 2040년 220GW 전망", "기후에너지환경부", "b", official=True)
    assert event_level(media) == 1
    assert event_level(official) == 2
    collapsed = collapse_events([media, official])
    assert len(collapsed) == 1
    assert collapsed[0]["official"] is True
