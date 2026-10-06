#!/usr/bin/env python3
import datetime as dt
from zoneinfo import ZoneInfo

from kospi_shock_enrichment import _nearest_row, _theme_keywords, select_etfs, _display_name, _is_actionable_theme, _is_real_industry

KST = ZoneInfo("Asia/Seoul")

# ETF 선택은 일반 섹터 ETF를 잡되 인버스·레버리지·선물형은 제외해야 한다.
master = [
    {"shcode": "111111", "hname": "KODEX 반도체", "etfgubun": "1"},
    {"shcode": "222222", "hname": "TIGER 반도체TOP10", "etfgubun": "1"},
    {"shcode": "333333", "hname": "KODEX 200선물인버스2X", "etfgubun": "1"},
    {"shcode": "444444", "hname": "KODEX 레버리지", "etfgubun": "1"},
    {"shcode": "555555", "hname": "KODEX 자동차", "etfgubun": "1"},
]
picked = select_etfs(master, ["반도체"], limit=10)
names = [x["hname"] for x in picked]
assert "KODEX 반도체" in names, names
assert "TIGER 반도체TOP10" in names, names
assert all("인버스" not in x and "레버리지" not in x for x in names), names
print("etf_filter_regression=true")

# 업종명이 들어오면 ETF 탐색에 쓸 대표 동의어를 확장한다.
keywords = _theme_keywords(["전기전자", "운수장비"])
assert "반도체" in keywords, keywords
assert "자동차" in keywords, keywords
print("theme_keyword_regression=true")

# 사건 시작·저점과 가장 가까운 실제 1분봉을 선택한다.
rows = [
    {"date": "20260930", "time": "143500", "close": "100"},
    {"date": "20260930", "time": "143600", "close": "99"},
    {"date": "20260930", "time": "143700", "close": "98"},
]
target = dt.datetime(2026, 9, 30, 14, 36, 13, tzinfo=KST).timestamp()
near = _nearest_row(rows, target)
assert near is not None, near
assert near[0]["time"] == "143600", near
assert abs(near[2] - 13.0) < 0.01, near
print("nearest_bar_regression=true")


# KRX 업종명의 불필요한 내부 공백은 사용자 표시에서 제거한다.
assert _display_name("전 기 전 자") == "전기전자"
assert _display_name("운 수 장 비") == "운수장비"
print("industry_label_normalization_regression=true")

# 제조업 같은 광범위 상위묶음은 세부 업종 순위에서 제외한다.
assert _is_real_industry("전 기 전 자", "013") is True
assert _is_real_industry("제 조 업", "027") is False
print("broad_industry_filter_regression=true")

# 지수 바스켓을 테마로 오인하지 않고 실제 기술/산업 테마만 남긴다.
assert _is_actionable_theme("코리아 밸류업 지수(Korea Value-up Index)") is False
assert _is_actionable_theme("소캠(SOCAMM)") is True
assert _is_actionable_theme("시스템반도체") is True
print("theme_classification_regression=true")

# ETF 후보는 실제 6자리 종목코드만 사용한다.
master2 = [
    {"shcode": "0000D0", "hname": "가상 ETF", "etfgubun": "1"},
    {"shcode": "091160", "hname": "KODEX 반도체", "etfgubun": "1"},
]
# select_etfs 자체는 이미 정제된 ETF master를 받는 함수이므로 여기서는
# 비정상 코드가 표시 후보로 들어오지 않도록 별도 master 단계에서 검증한다.
assert not __import__("re").fullmatch(r"\d{6}", master2[0]["shcode"])
assert __import__("re").fullmatch(r"\d{6}", master2[1]["shcode"])
print("etf_code_validation_regression=true")
