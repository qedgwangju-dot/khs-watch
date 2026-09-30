#!/usr/bin/env python3
import datetime as dt
from zoneinfo import ZoneInfo

from kospi_shock_enrichment import _nearest_row, _theme_keywords, select_etfs

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
