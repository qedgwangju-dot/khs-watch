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
    assert "nwitimes.com ·" not in result
    assert "원문 (https://" not in result


def test_google_news_link_is_blocked():
    text = (
        "- 정확한 내용 요약: 데이터센터 인허가와 금융 조달 조건이 강화됐습니다.\n"
        '- 근거1: [신뢰보도] Reuters · <a href="https://news.google.com/rss/articles/abc">원문</a>'
    )
    with pytest.raises(ValueError, match="Google News"):
        sanitize_report(text)


def test_mixed_login_boilerplate_is_removed_but_fact_is_kept():
    text = (
        "- 정확한 내용 요약: - USA Today - Vertical 뉴욕 — 미국의 데이터 센터 붐에 자금을 조달하기 위한 경쟁으로 인해 은행과 자산 관리자는 정치적 및 지역 사회의 반대라는 추가 위험에 직면하게 되었습니다. 최신 뉴스를 기기로 바로 받아보세요. 귀하의 계정이 등록되었으며 이제 로그인되었습니다. 아래 양식을 제출하면 비밀번호 변경 링크가 포함된 메시지가 귀하의 이메일로 전송됩니다.\n"
        '- 근거1: [신뢰보도] reuters.com · <a href="https://www.reuters.com/example">원문</a>'
    )
    result = sanitize_report(text)
    assert "미국의 데이터 센터 붐에 자금을 조달" in result
    assert "최신 뉴스를 기기로" not in result
    assert "로그인되었습니다" not in result
    assert "비밀번호 변경 링크" not in result


def test_only_login_boilerplate_summary_is_blocked():
    text = (
        "- 정확한 내용 요약: 귀하의 계정이 등록되었으며 이제 로그인되었습니다.\n"
        '- 근거1: [신뢰보도] Reuters · <a href="https://www.reuters.com/example">원문</a>'
    )
    with pytest.raises(ValueError, match="로그인/회원가입"):
        sanitize_report(text)


def test_visible_raw_url_is_blocked():
    text = (
        "- 정확한 내용 요약: 데이터센터 금융과 인허가 위험을 대주단이 더 엄격히 점검합니다.\n"
        '- 참고: https://example.com/raw\n'
        '- 근거1: [신뢰보도] Reuters · <a href="https://www.reuters.com/example">원문</a>'
    )
    with pytest.raises(ValueError, match="긴 URL"):
        sanitize_report(text)
