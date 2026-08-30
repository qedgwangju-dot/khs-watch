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
from scripts.korea_energy_mix_watch_runner import interpret_article_body


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


def test_nuclear_coal_lng_article_gets_real_body_interpretation():
    article_body = """
    정부와 제12차 전력수급기본계획 수립 총괄위원회는 다음 달부터 신규 원전 확대 여부와 2040년 석탄발전 폐지 등을 주제로 공청회를 개최할 예정이다.
    제11차 전기본에 반영된 대형원전 2기와 소형모듈원전(SMR) 1기는 확정됐고 대형원전은 경북 영덕군, SMR은 부산 기장군으로 부지가 정해졌다. SMR은 2035년, 대형원전은 2037년과 2038년 준공이 예상된다.
    김성환 장관은 호남 반도체 산단이 당초 팹 4기보다 커질 경우 원전을 더 지어야 할지 추가 대책을 찾아야 한다고 말했다. 한빛 원전은 현재 6개이고 2개를 더 지을 부지가 있다고 언급했다. 업계에서는 최대 9기의 팹 가능성이 제기된다.
    정부는 2040년 석탄발전 폐지 로드맵을 논의하고 있으며 발전 공백과 정의로운 전환을 함께 고민하고 있다. 발전공기업 5사 재편과 1사 통합안도 연구용역 권고 단계다.
    LNG 발전은 재생에너지 간헐성을 보완하고 원전보다 건설기간이 짧아 대안으로 거론된다. 호남 반도체 산단은 열 스팀 수요 때문에 LNG 발전소 가능성도 열어뒀다.
    정부는 다음 달부터 토론회를 열고 10월 정부안을 낸 뒤 연내 제12차 전기본을 확정할 방침이다.
    """
    result = interpret_article_body(
        {"title": "전력수요 폭증에 2040 석탄폐지까지…신규 원전 공론화 개시"},
        article_body,
        "",
    )
    assert "추가 원전" in result
    assert "확정 계획" in result
    assert "검토 가능성" in result
    assert "LNG" in result
    assert "10월 정부안" in result
    assert "임의 해석은 생략" not in result
