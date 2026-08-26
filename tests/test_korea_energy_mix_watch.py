import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.korea_energy_mix_watch import classify, korean_date, parse_rss, render, topic_match


def test_topic_match_requires_power_plan_and_energy_mix_term():
    assert topic_match("제12차 전기본 재생에너지 2040년 220GW 전망") is True
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


def test_render_is_readable_without_losing_core_fields():
    body = render([
        {
            "title": "제12차 전기본 재생에너지 220GW 전망",
            "publisher": "연합뉴스",
            "source": "국내 주요 언론",
            "official": False,
            "url": "https://example.com/story",
            "published": "Wed, 26 Aug 2026 07:00:00 GMT",
            "category": "재생에너지·전원믹스",
            "stage": 5,
            "id": "x",
        }
    ])
    assert "#" not in body
    assert "2026년 8월 26일" in body
    assert "<b>핵심 분야</b>" in body
    assert "<b>확인 상태</b>" in body
    assert "<b>투자 의미</b>" in body
    assert '<a href="https://example.com/story"><b>공식 원문 보기</b></a>' in body
