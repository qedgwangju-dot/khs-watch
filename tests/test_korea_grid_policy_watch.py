import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.korea_grid_policy_watch import (
    classify_item,
    extract_law_version,
    parse_html_items,
    parse_rss,
    setup_report,
    topic_match,
)


def test_local_distribution_undergrounding_is_not_misclassified():
    assert topic_match("양평군 시민로 배전선 지중화 확정지역 공고") is False
    assert topic_match("345kV 송전선로 민가 밀집지역 지중화 공고") is True


def test_procurement_is_classified_as_real_order():
    category, stage = classify_item("345kV 송전선로 지중화 공사 입찰 공고")
    assert category == "실제 발주·착공"
    assert stage == 4


def test_mcee_html_item_is_detected():
    html = """
    <ul><li><a href="/home/web/board/read.do?boardId=1">전력망 건설 주민 수용성 제고 방안 최종 확정</a>
    <span>2026-09-05</span></li></ul>
    """
    items = parse_html_items(html, "https://www.mcee.go.kr/", "기후에너지환경부")
    assert len(items) == 1
    assert items[0]["category"] == "최종 대책"
    assert items[0]["published"] == "2026-09-05"


def test_official_rss_item_is_detected():
    xml = """
    <rss><channel><item>
      <title>입지선정위원회 관련 고시 전면 개정 - 기후에너지환경부</title>
      <source>기후에너지환경부</source>
      <link>https://www.mcee.go.kr/example</link>
      <guid>grid-rule-1</guid>
      <pubDate>Sat, 05 Sep 2026 01:00:00 GMT</pubDate>
    </item></channel></rss>
    """
    items = parse_rss(xml, "기후에너지환경부 공식 검색")
    assert len(items) == 1
    assert items[0]["category"] == "법령·고시 개정"


def test_law_version_extraction():
    html = """
    <html><head><title>송전설비주변법 시행령</title></head><body>
    [시행 2026. 6. 3.] [대통령령 제36372호, 2026. 6. 2., 일부개정]
    </body></html>
    """
    version = extract_law_version(html, "송전설비주변법 시행령")
    assert "[시행 2026. 6. 3.]" in version
    assert "[대통령령 제36372호, 2026. 6. 2., 일부개정]" in version


def test_setup_report_is_locked_to_alert_bot():
    report = setup_report()
    assert "@hs8879887988798879_bot" in report
    assert "@hs887988798879_bot" not in report
