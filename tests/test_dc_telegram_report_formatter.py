import pytest

from scripts.dc_telegram_report_formatter import sanitize_report


def test_only_original_label_is_clickable():
    text = (
        "🚨 미국 데이터센터 실행 병목 변화\n"
        "- 정확한 내용 요약: 대주단이 인허가와 지역사회 반대를 신용위험으로 더 엄격히 점검합니다.\n"
        '- 근거1: [신뢰보도] reuters.com · <a href="https://www.reuters.com/example">원문</a>\n'
        '- 근거2: [기타] nwitimes.com · 원문 (https://nwitimes.com/example)'
    )
    result = sanitize_report(text)
    assert '[신뢰보도] Reuters · <a href="https://www.reuters.com/example">원문</a>' in result
    assert '[기타] NWI Times · <a href="https://nwitimes.com/example">원문</a>' in result
    assert "reuters.com ·" not in result
    assert "원문 (https://" not in result


def test_google_news_link_is_blocked():
    text = (
        "- 정확한 내용 요약: 정상 요약입니다.\n"
        '- 근거1: [신뢰보도] Reuters · <a href="https://news.google.com/rss/articles/abc">원문</a>'
    )
    with pytest.raises(ValueError, match="Google News"):
        sanitize_report(text)


def test_login_boilerplate_summary_is_blocked():
    text = (
        "- 정확한 내용 요약: 귀하의 계정이 등록되었으며 이제 로그인되었습니다.\n"
        '- 근거1: [신뢰보도] Reuters · <a href="https://www.reuters.com/example">원문</a>'
    )
    with pytest.raises(ValueError, match="로그인/회원가입"):
        sanitize_report(text)


def test_visible_raw_url_is_blocked():
    text = (
        "- 정확한 내용 요약: 정상 요약입니다.\n"
        '- 참고: https://example.com/raw\n'
        '- 근거1: [신뢰보도] Reuters · <a href="https://www.reuters.com/example">원문</a>'
    )
    with pytest.raises(ValueError, match="긴 URL"):
        sanitize_report(text)
