from datetime import datetime, timezone

from scripts.alert_timeline_dates import (
    extract_original_dates,
    korean_date,
    parse_timestamp,
    timeline_lines,
    verified_age_days,
)


NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)


def test_utc_to_korean_date_boundary():
    assert korean_date("Tue, 01 Sep 2026 18:30:00 GMT") == "2026년 9월 2일"
    assert korean_date("2026-09-01") == "2026년 9월 1일"
    assert parse_timestamp("2026. 6. 24.").date().isoformat() == "2026-06-24"
    assert korean_date("2026년 9월 1일") == "2026년 9월 1일"


def test_original_publication_overrides_google_news_reindex():
    page = """
    <html><body><h1>송전용 ESS에 그리드포밍 기술 도입</h1>
    <p>등록일자 : 2026. 6. 24.</p>
    <p>2027년 12월 상업운전과 2029년 600MW 추진</p>
    </body></html>
    """
    evidence = extract_original_dates(page, now=NOW)
    assert korean_date(evidence["published"]) == "2026년 6월 24일"
    assert evidence["published_source"] == "원문 게시일 표기"
    assert verified_age_days(evidence, NOW) > 30
    lines = timeline_lines(evidence, rss_published="Tue, 01 Sep 2026 07:00:00 GMT")
    assert "원문 게시일  2026년 6월 24일" in lines
    assert not any("검색 노출일" in row for row in lines)


def test_modified_and_effective_dates_are_distinct():
    page = """
    <html><head>
      <meta property="article:published_time" content="2026-09-01T07:00:00+09:00">
      <meta property="article:modified_time" content="2026-09-02T15:01:00+09:00">
    </head>
    <body><p>[시행 2026. 10. 1.] 2030년 목표치 안내</p></body></html>
    """
    evidence = extract_original_dates(page, now=NOW)
    assert korean_date(evidence["published"]) == "2026년 9월 1일"
    assert korean_date(evidence["modified"]) == "2026년 9월 2일"
    assert korean_date(evidence["effective"]) == "2026년 10월 1일"
    lines = timeline_lines(evidence)
    assert len(lines) == 3


def test_jsonld_publication_verified_when_rss_different():
    page = """<html><head><script type="application/ld+json">
    {"@type":"NewsArticle","datePublished":"2026-09-25T08:23:00+09:00",
     "dateModified":"2026-09-25T12:15:00+09:00"}
    </script></head><body></body></html>"""
    evidence = extract_original_dates(page, now=NOW)
    assert korean_date(evidence["published"]) == "2026년 9월 25일"
    assert evidence["published_source"] == "원문 구조화자료"


def test_no_made_up_publication_date_from_target_or_effective_date():
    page = """<html><body>
    2040년 재생에너지 확대 목표, 2027년 12월 시행 예정
    [시행 2026. 6. 3.]
    </body></html>"""
    evidence = extract_original_dates(page, now=NOW)
    assert not evidence["published"]
    assert korean_date(evidence["effective"]) == "2026년 6월 3일"
    lines = timeline_lines(evidence, rss_published="Tue, 01 Sep 2026 07:00:00 GMT")
    assert "원문 게시일  확인 불가" in lines
    assert "검색 노출일(발표일 아님)  2026년 9월 1일" in lines


def test_future_target_cannot_be_selected_as_article_publication():
    page = """<html><head><meta property="article:published_time"
    content="2040-01-01T00:00:00+09:00"></head><body>사업 목표</body></html>"""
    assert not extract_original_dates(page, now=NOW)["published"]


def test_named_event_day_is_distinct_from_article_publication():
    page = """
    <html><body>
      <div>등록일 2026년 9월 25일</div>
      <article><p>회의 개최일: 2026년 9월 22일</p>
      <p>새로운 제12차 전기본 공론화 절차를 공개하였다.</p></article>
    </body></html>
    """
    evidence = extract_original_dates(page, now=NOW)
    assert korean_date(evidence["published"]) == "2026년 9월 25일"
    assert korean_date(evidence["event"]) == "2026년 9월 22일"
    assert evidence["event_label"] == "회의일"
    assert "회의일  2026년 9월 22일" in timeline_lines(evidence)
