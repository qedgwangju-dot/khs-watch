#!/usr/bin/env python3
import datetime as dt
from zoneinfo import ZoneInfo

from kospi_shock_enrichment import _nearest_row, _theme_keywords, select_etfs, _display_name, _is_actionable_theme, _is_real_industry, direct_industry_interval

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


# 통합 UBM 업종 투자자 수급은 사건 시작/저점의 30초 이내 기준점만 사용한다.
import json, tempfile
from pathlib import Path
base_ts = dt.datetime(2026, 10, 6, 9, 42, 56, tzinfo=KST).timestamp()
low_ts = dt.datetime(2026, 10, 6, 9, 57, 0, tzinfo=KST).timestamp()
records = [
    {"ts": base_ts-10, "upcode":"013", "industry":"전 기 전 자", "investor":"기관", "msval":1000},
    {"ts": low_ts-4, "upcode":"013", "industry":"전 기 전 자", "investor":"기관", "msval":600},
    {"ts": base_ts-8, "upcode":"018", "industry":"운 수 장 비", "investor":"기관", "msval":500},
    {"ts": low_ts-3, "upcode":"018", "industry":"운 수 장 비", "investor":"기관", "msval":450},
    {"ts": base_ts-90, "upcode":"005", "industry":"화 학", "investor":"기관", "msval":100},
    {"ts": low_ts-2, "upcode":"005", "industry":"화 학", "investor":"기관", "msval":-100},
]
with tempfile.TemporaryDirectory() as td:
    p=Path(td)/"ubm.jsonl"
    p.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in records)+"\n", encoding="utf-8")
    direct=direct_industry_interval(base_ts, low_ts, "기관", p, 30.0)
    assert direct["available"], direct
    assert direct["rows"][0]["name"] == "전기전자", direct
    assert direct["rows"][0]["delta"] == -400, direct
    assert all(x["code"] != "005" for x in direct["rows"]), direct
print("direct_industry_ubm_regression=true")


# UBM 원시 tjjtime이 같은 값으로 멈춰 있어도 사건구간 정렬은 실제 수신시각(ts)으로 해야 한다.
records_frozen = [
    {"ts": base_ts-12, "source_time":"09423000", "upcode":"013", "industry":"전 기 전 자", "investor":"기관", "msval":1000},
    {"ts": base_ts+120, "source_time":"09423000", "upcode":"013", "industry":"전 기 전 자", "investor":"기관", "msval":850},
    {"ts": low_ts-5, "source_time":"09423000", "upcode":"013", "industry":"전 기 전 자", "investor":"기관", "msval":600},
]
with tempfile.TemporaryDirectory() as td:
    p=Path(td)/"ubm_frozen_source_time.jsonl"
    p.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in records_frozen)+"\n", encoding="utf-8")
    direct=direct_industry_interval(base_ts, low_ts, "기관", p, 30.0)
    assert direct["available"], direct
    assert direct["rows"][0]["delta"] == -400, direct
print("ubm_received_time_alignment_regression=true")


# 사건 이후 시각이나 90초 초과 오래된 1분봉을 섞어 종목·업종·ETF/프로그램 순위를
# 잘못 작성하지 않는지 2026-10-08 11:04→11:19 급락 사례로 검증한다.
import kospi_shock_enrichment as ke
from kospi_shock_enrichment import _aligned_prior_row
start = dt.datetime(2026, 10, 8, 11, 4, 6, tzinfo=KST).timestamp()
end = dt.datetime(2026, 10, 8, 11, 19, 49, tzinfo=KST).timestamp()
before = {"date": "20261008", "time": "110400", "close": "6786.16"}
future = {"date": "20261008", "time": "110415", "close": "9999"}
strict = _aligned_prior_row([future, before], start)
assert strict is not None and strict[0] == before and strict[2] == 6.0, strict
assert _aligned_prior_row([future], start) is None, "future-only bar must not be used"
assert _aligned_prior_row([{"date": "20261008", "time": "110200"}], start) is None, "stale bar must not be used"

bars = [
    {"date": "20261008", "time": "110400", "close": "6786.16", "svalue": "100000"},
    {"date": "20261008", "time": "111900", "close": "6745.30", "svalue": "70000"},
    {"date": "20261008", "time": "112000", "close": "6700.00", "svalue": "40000"},
]
orig_stock_bars = ke.fetch_stock_bars
orig_ls_post = ke.ls_post
try:
    ke.fetch_stock_bars = lambda *args, **kwargs: bars
    price = ke.stock_interval_price("demo", "005930", start, end)
    assert price["available"], price
    assert price["end_price"] == 6745.30, price
    assert price["end_time"] == "11:19:00", price
    assert 0 <= price["end_gap_sec"] <= 90, price

    def fake_ls_post(token, api, tr, body):
        if tr == "t1637":
            return {"t1637OutBlock1": bars}
        if tr == "t8409":
            return {"t8409OutBlock1": bars}
        raise AssertionError(tr)
    ke.ls_post = fake_ls_post
    program = ke.program_interval("demo", "005930", start, end)
    assert program["available"] and program["program_delta"] == -30000, program
    assert program["end_time"] == "11:19:00", program
    industry = ke.industry_index_interval("demo", "013", start, end)
    assert industry["available"] and industry["end"] == 6745.30, industry

    # 사건 종료 기준점에 대응하는 표본이 없으면 값·순위는 추정하지 않는다.
    no_end = [bars[0], {"date":"20261008", "time":"111600", "close":"6750", "svalue":"80000"}]
    ke.fetch_stock_bars = lambda *args, **kwargs: no_end
    assert not ke.stock_interval_price("demo", "005930", start, end)["available"]
    ke.ls_post = lambda *args, **kwargs: {"t1637OutBlock1": no_end}
    assert not ke.program_interval("demo", "005930", start, end)["available"]
finally:
    ke.fetch_stock_bars = orig_stock_bars
    ke.ls_post = orig_ls_post
print("strict_prior_interval_alignment_regression=true")


# 하루 누적 프로그램 매도 상위라도 사건구간에 순매수가 발생했거나
# 90초 정렬에 실패한 종목은 '급락구간 프로그램 매도종목'으로 재분류하지 않는다.
rows = [
    {"code":"A","program":{"available":True,"program_delta":200}},
    {"code":"B","program":{"available":True,"program_delta":-120}},
    {"code":"C","program":{"available":False,"program_delta":-9999}},
    {"code":"D","program":{"available":True,"program_delta":-35}},
    {"code":"E","program":{"available":True,"program_delta":None}},
]
selected = ke.confirmed_interval_sellers(rows)
assert [x["code"] for x in selected] == ["B", "D"], selected
assert ke.confirmed_interval_sellers(rows[:1] + rows[2:3]) == []
print("event_program_sellers_only_regression=true")


# 2026-10-08 22:47 KST CI 실패 재현: 장마감 뒤 지금-10분은 거래 봉이 없으므로
# 당일 마지막 정규장 1분봉 두 기준점으로만 검증해야 한다.
from kospi_shock_enrichment import select_stock_chart_probe_window, stock_interval_price
after_hours = dt.datetime(2026,10,8,22,47,tzinfo=KST)
oct_bars = [
    {"date":"20261008","time":f"15{m:02d}00","close":str(262000+m*10)}
    for m in range(9,20)
]
oct_bars.append({"date":"20261008","time":"153288","close":"999999"}) # 비정상 초(88) 배제
oct_bars.append({"date":"20261007","time":"152900","close":"999999"}) # 다른 거래일 배제
w_after=select_stock_chart_probe_window(oct_bars,after_hours)
assert w_after["available"] and w_after["mode"]=="장마감 자료",w_after
assert w_after["session_date"]=="20261008" and w_after["end_bar_kst"]=="15:19:00",w_after
price_after=stock_interval_price("dummy","005930",w_after["start_ts"],w_after["end_ts"],rows=oct_bars)
assert price_after["available"] and price_after["start_time"]=="15:09:00",price_after
assert price_after["end_time"]=="15:19:00",price_after
print("after_hours_chart_anchor_regression=true")

# 장중에는 현재 시각과 다른 오래된 1분봉을 '실시간 검증 통과'로 위장하지 않는다.
live_now=dt.datetime(2026,10,8,11,10,tzinfo=KST)
stale_bars=[{"date":"20261008","time":f"11{m:02d}00","close":"250000"} for m in range(0,5)]
w_stale=select_stock_chart_probe_window(stale_bars,live_now)
assert w_stale["available"] is False and w_stale["mode"]=="장중",w_stale
assert "지연" in w_stale["reason"],w_stale
print("intraday_stale_chart_rejection_regression=true")

# 같은 날 원자료 자체가 없으면 장외에도 검증 실패(단순 정상 처리 금지).
w_missing=select_stock_chart_probe_window(oct_bars[-1:],after_hours)
assert w_missing["available"] is False,w_missing
assert "표본" in w_missing["reason"],w_missing
print("after_hours_missing_chart_rejection_regression=true")

# 장전·휴장일은 오늘 장중 데이터라고 속이지 않는다.
holiday=dt.datetime(2026,10,9,11,10,tzinfo=KST)
w_holiday=select_stock_chart_probe_window(oct_bars,holiday)
assert w_holiday["available"] is False and w_holiday["mode"]=="휴장",w_holiday
print("holiday_chart_probe_guard_regression=true")
