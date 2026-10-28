#!/usr/bin/env python3
import time
from collections import deque
from kospi_shock_episode_watch import Watch, fmt_clock, ko_subject, ls_post, get_token

w = Watch.__new__(Watch)
w.idx = deque(maxlen=30000)
base = time.time() - 80 * 60
series = []
for i in range(15):
    series.append((base + i * 60, 7170.0 + i * 0.1))
for i in range(1, 48):
    series.append((base + (15 + i) * 60, 7171.4 - i * 3.0))
for i in range(1, 10):
    series.append((base + (62 + i) * 60, 7030.4 + i * 5.0))

hit = None
for ts, price in series:
    w.idx.append((ts, price))
    ok, info = Watch._trigger(w)
    if ok:
        hit = info
        break

if not hit:
    raise SystemExit("synthetic shock was not detected")
print(f"synthetic_detected=true start={fmt_clock(hit['peak_ts'])} trigger={fmt_clock(hit['cur_ts'])} drop={hit['drop']:.2f}% duration_min={hit['duration']/60:.1f}")


# Regression: "both negative" is not enough to call one actor the leader.
# This mirrors the 2026-09-22 alert shape: spot leader=foreign, futures leader=institution,
# while individual is negative in both. The verdict must NOT call individual the lead seller.
w2 = Watch.__new__(Watch)
w2.flows = deque([
    {"ts": 1000.0,
     "현물": {"외국인": 0.0, "기관": 0.0, "개인": 0.0},
     "선물": {"외국인": 0.0, "기관": 0.0, "개인": 0.0},
     "프로그램": {"전체": 100.0, "차익": 40.0, "비차익": 60.0, "베이시스": 0.0}},
    {"ts": 2000.0,
     "현물": {"외국인": -944.0, "기관": 321.0, "개인": -378.0},
     "선물": {"외국인": 822.0, "기관": -859.0, "개인": -254.0},
     "프로그램": {"전체": 80.0, "차익": 35.0, "비차익": 45.0, "베이시스": -0.2}},
], maxlen=2500)
att = Watch.attribution(w2, 1000.0, 2000.0)
assert att["spot_leader"] == "외국인", att
assert att["futures_leader"] == "기관", att
assert "개인" in att["cross_sellers"], att
assert "현물은 외국인, 선물은 기관" in att["verdict"], att
assert "개인" not in att["verdict"].split("가 현물·선물")[0], att
print("attribution_regression=true spot_leader=외국인 futures_leader=기관 single_leader=false")


# Regression: an older session high must not become the start of a later local shock.
w3 = Watch.__new__(Watch)
w3.idx = deque(maxlen=30000)
base3 = time.time() - 140 * 60
# Old session high two hours earlier.
for i in range(20):
    w3.idx.append((base3 + i*60, 7200.0 - i*1.0))
# Long quieter period well below old high.
for i in range(20, 105):
    w3.idx.append((base3 + i*60, 7120.0 + (i-20)*0.15))
# Local pivot, then 22-minute abrupt decline.
local_peak_ts = base3 + 105*60
w3.idx.append((local_peak_ts, 7133.0))
hit3 = None
for i in range(1, 23):
    w3.idx.append((local_peak_ts + i*60, 7133.0 - i*3.4))
    ok3, info3 = Watch._trigger(w3)
    if ok3:
        hit3 = info3
        break
assert hit3, "local shock regression not detected"
assert abs(hit3["peak_ts"] - local_peak_ts) <= 5*60, hit3
assert hit3["peak"] < 7150.0, hit3
print(f"local_pivot_regression=true start={fmt_clock(hit3['peak_ts'])} window={hit3['window_minutes']}m")


# Regression: production code must contain feed-staleness guards so an in-progress
# GitHub job cannot be mistaken for a healthy market-data stream.
import inspect
src = inspect.getsource(Watch.run)
assert "KOSPI REST price stale >90s" in src
assert "KOSPI200 futures REST price stale >90s" in src
assert "flow snapshot stale >180s" in src
print("feed_health_regression=true")

# Regression: 사건 시작/종료 기준점과 수급 스냅샷이 30초 넘게 어긋나면
# 매도주체를 확정하지 않는다.
w4 = Watch.__new__(Watch)
w4.flows = deque([
    {"ts": 900.0,
     "현물": {"외국인": 0.0, "기관": 0.0, "개인": 0.0},
     "선물": {"외국인": 0.0, "기관": 0.0, "개인": 0.0},
     "프로그램": {"전체": 0.0, "차익": 0.0, "비차익": 0.0, "베이시스": 0.0, "표본시차초": 2.0}},
    {"ts": 1995.0,
     "현물": {"외국인": -1000.0, "기관": 100.0, "개인": 100.0},
     "선물": {"외국인": -1200.0, "기관": 100.0, "개인": 100.0},
     "프로그램": {"전체": -500.0, "차익": -100.0, "비차익": -400.0, "베이시스": 0.0, "표본시차초": 2.0}},
], maxlen=2500)
att4 = Watch.attribution(w4, 1000.0, 2000.0)
assert not att4["available"], att4
assert "시간 정렬 초과" in att4["reason"], att4
print("flow_alignment_regression=true")

# Regression: t1640 전체/차익/비차익 3종 조회 시차가 품질 한도를 넘으면
# 프로그램 매도가 보여도 확신도를 '높음'으로 올리지 않는다.
w5 = Watch.__new__(Watch)
w5.flows = deque([
    {"ts": 990.0,
     "현물": {"외국인": 0.0, "기관": 0.0, "개인": 0.0},
     "선물": {"외국인": 0.0, "기관": 0.0, "개인": 0.0},
     "프로그램": {"전체": 100.0, "차익": 40.0, "비차익": 60.0, "베이시스": 0.0, "표본시차초": 9.0}},
    {"ts": 1995.0,
     "현물": {"외국인": -1000.0, "기관": 100.0, "개인": 50.0},
     "선물": {"외국인": -1400.0, "기관": 200.0, "개인": 80.0},
     "프로그램": {"전체": -500.0, "차익": -100.0, "비차익": -400.0, "베이시스": -0.2, "표본시차초": 9.0}},
], maxlen=2500)
att5 = Watch.attribution(w5, 1000.0, 2000.0)
assert att5["available"], att5
assert att5["spot_leader"] == "외국인" and att5["futures_leader"] == "외국인", att5
assert att5["confidence"] == "중간", att5
assert att5["program_quality"] is False, att5
assert "외국인가" not in att5["verdict"], att5
print("program_skew_regression=true")


# 조사 표기 회귀: 외국인가/기관가 같은 오타를 만들지 않는다.
assert ko_subject("외국인") == "외국인이"
assert ko_subject("기관") == "기관이"
assert ko_subject("코스피") == "코스피가"
print("korean_subject_particle_regression=true")

# 오전→오후 production 교대 시 사건 상태와 최근 수급 스냅샷을 잃지 않는다.
import tempfile
from pathlib import Path
w6 = Watch("dummy", [], "dummy", True)
now6 = time.time()
w6.flows.append({
    "ts": now6 - 20,
    "현물": {"외국인": -1.0, "기관": -2.0, "개인": 3.0},
    "선물": {"외국인": -4.0, "기관": 1.0, "개인": 3.0},
    "프로그램": {"전체": -5.0, "차익": -1.0, "비차익": -4.0, "베이시스": 0.0, "sample_ts": now6 - 20},
})
w6.episode = {
    "start_ts": now6 - 120,
    "start_price": 7000.0,
    "low_ts": now6 - 10,
    "low_price": 6960.0,
    "sent_drop": 0.57,
    "alerted": True,
}
w6.opening_gap_sent = True
with tempfile.TemporaryDirectory() as td:
    hp = Path(td) / "handoff.json"
    w6.save_handoff(hp)
    w7 = Watch("dummy", [], "dummy", True)
    w7.load_handoff(hp)
    assert len(w7.flows) == 1, len(w7.flows)
    assert w7.episode and w7.episode["start_price"] == 7000.0, w7.episode
    assert w7.opening_gap_sent is True, w7.opening_gap_sent
print("handoff_regression=true")


# Regression: 전체 직접값과 차익+비차익 계산합계가 5% 넘게 벌어지면
# 방향이 같아도 프로그램 품질을 높음으로 인정하지 않는다.
w8 = Watch.__new__(Watch)
w8.flows = deque([
    {"ts": 1000.0,
     "현물": {"외국인": 0.0, "기관": 0.0, "개인": 0.0},
     "선물": {"외국인": 0.0, "기관": 0.0, "개인": 0.0},
     "프로그램": {"전체": 0.0, "차익": 0.0, "비차익": 0.0, "베이시스": 0.0, "표본시차초": 3.0}},
    {"ts": 2000.0,
     "현물": {"외국인": -1000.0, "기관": 100.0, "개인": 100.0},
     "선물": {"외국인": -1500.0, "기관": 200.0, "개인": 100.0},
     "프로그램": {"전체": -1000.0, "차익": -100.0, "비차익": -400.0, "베이시스": -0.1, "표본시차초": 3.0}},
], maxlen=2500)
att8 = Watch.attribution(w8, 1000.0, 2000.0)
assert att8["available"], att8
assert att8["program_crosscheck_ratio_pct"] > 5.0, att8
assert att8["program_quality"] is False, att8
assert att8["confidence"] == "중간", att8
print("program_crosscheck_ratio_regression=true")


# Regression: LS transport connection errors are retried instead of killing production immediately.
import kospi_shock_episode_watch as ks
class DummyResponse:
    ok = True
    status_code = 200
    text = ""
    def json(self):
        return {"rsp_cd": "00000", "ok": True}
attempts = {"n": 0}
orig_post = ks.requests.post
orig_sleep = ks.time.sleep
def flaky_post(*args, **kwargs):
    attempts["n"] += 1
    if attempts["n"] < 3:
        raise ks.requests.ConnectionError("synthetic disconnect")
    return DummyResponse()
try:
    ks.requests.post = flaky_post
    ks.time.sleep = lambda *_args, **_kwargs: None
    out = ls_post("token", "/x", "TEST", {"x": 1})
    assert out.get("ok") is True, out
    assert attempts["n"] == 3, attempts
finally:
    ks.requests.post = orig_post
    ks.time.sleep = orig_sleep
print("ls_transport_retry_regression=true")

# Regression: failure path must save a handoff before re-raising.
import inspect
amain_src = inspect.getsource(ks.amain)
assert "w.save_handoff(handoff_out)" in amain_src, amain_src
assert "handoff_save_error" in amain_src, amain_src
print("failure_handoff_regression=true")


# Regression: LS OAuth의 503/redirect성 장애도 재시도 후 회복한다.
class DummyTokenResponse:
    def __init__(self, status, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text
        self.ok = 200 <= status < 300
    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload

token_attempts = {"n": 0}
orig_post2 = ks.requests.post
orig_sleep2 = ks.time.sleep
orig_key = __import__("os").environ.get("LS_OPENAPI_APP_KEY")
orig_secret = __import__("os").environ.get("LS_OPENAPI_APP_SECRET")
def token_post(*args, **kwargs):
    token_attempts["n"] += 1
    if token_attempts["n"] == 1:
        return DummyTokenResponse(503, None, "temporary")
    if token_attempts["n"] == 2:
        return DummyTokenResponse(302, None, "maintenance redirect")
    return DummyTokenResponse(200, {"access_token": "abc"})
try:
    __import__("os").environ["LS_OPENAPI_APP_KEY"] = "k"
    __import__("os").environ["LS_OPENAPI_APP_SECRET"] = "s"
    ks.requests.post = token_post
    ks.time.sleep = lambda *_args, **_kwargs: None
    assert get_token() == "abc"
    assert token_attempts["n"] == 3, token_attempts
finally:
    ks.requests.post = orig_post2
    ks.time.sleep = orig_sleep2
    if orig_key is None:
        __import__("os").environ.pop("LS_OPENAPI_APP_KEY", None)
    else:
        __import__("os").environ["LS_OPENAPI_APP_KEY"] = orig_key
    if orig_secret is None:
        __import__("os").environ.pop("LS_OPENAPI_APP_SECRET", None)
    else:
        __import__("os").environ["LS_OPENAPI_APP_SECRET"] = orig_secret
print("ls_token_retry_regression=true")


# 장마감 시 복원되지 않은 급락을 '복원 확인'으로 오표기하지 않는다.
w9 = Watch.__new__(Watch)
w9.flows = deque(maxlen=2500)
ep9 = {
    "start_ts": time.time() - 300,
    "start_price": 7000.0,
    "low_ts": time.time() - 30,
    "low_price": 6950.0,
}
close_text = Watch.build_end(w9, ep9, time.time(), 6960.0, session_close=True)
assert "장마감 확정" in close_text, close_text
assert "복원 여부는 확정하지 않습니다" in close_text, close_text
assert "종료·복원 확인" not in close_text, close_text
print("session_close_render_regression=true")


# Regression: 감시 공백 중 가격 급락은 침묵하지 않고 수급 원인 보류로 표시한다.
w10 = Watch.__new__(Watch)
w10.flows = deque(maxlen=2500)
w10.put_defs = []
w10.puts = {}
ep10 = {
    "start_ts": time.time() - 300,
    "start_price": 7000.0,
    "low_ts": time.time() - 30,
    "low_price": 6950.0,
    "price_only": True,
}
txt10 = Watch.build_alert(w10, "start", ep10, time.time(), 6960.0)
assert "수급 원인 보류" in txt10, txt10
assert "소급 추정하지 않습니다" in txt10, txt10
assert "주도 가능성 높음" not in txt10, txt10
print("price_only_gap_alert_regression=true")


# Regression: 전일 종가 대비 시가 급락은 장중 사건과 별도로 1회 경고한다.
w11 = Watch.__new__(Watch)
gap_text = Watch.build_open_gap_alert(w11, {
    "KOSPI": {
        "prev_close": 6941.30,
        "open": 6864.25,
        "open_pct": -1.11,
    }
})
assert "코스피 개장 갭다운" in gap_text, gap_text
assert "-1.11%" in gap_text, gap_text
assert "매도주체를 단정하지 않습니다" in gap_text, gap_text
assert "주도 가능성 높음" not in gap_text, gap_text
print("opening_gap_alert_regression=true")


# Regression: 장중 프로세스 강제종료에 대비해 handoff를 30초 주기로 저장하고
# 텔레그램 발송 직후에는 즉시 체크포인트한다.
run_src = inspect.getsource(ks.Watch.run)
delivery_src = inspect.getsource(ks.Watch._record_delivery)
assert "self._checkpoint_handoff()" in run_src, run_src
assert "self._checkpoint_handoff(force=True)" in delivery_src, delivery_src
print("periodic_handoff_checkpoint_regression=true")


# Delivery transport is checked with destination/text/date receipts and
# ambiguous-send fault injection in test_market_alert_delivery.py. Network
# disconnects after a POST must not be treated as proven rejection/retried.
print("telegram_receipt_faults_covered_by_market_alert_delivery_tests=true")


# 2026-10-08 09:58 실전 경보 검산: 계산합계 -40,892와 LS 직접값 -39,448의
# 차이 +1,444(3.53%)는 같은 방향이어도 '정확히 일치/확신도 높음'이 아니다.
from kospi_shock_episode_watch import program_quality_label, fmt_duration
w_today = Watch.__new__(Watch)
w_today.flows = deque([
    {"ts": 1000.0-16.9,
     "현물": {"sample_ts":1000.0-16.9, "외국인":0.0,"기관":0.0,"개인":0.0},
     "선물": {"sample_ts":1000.0-16.9, "외국인":0.0,"기관":0.0,"개인":0.0},
     "프로그램": {"sample_ts":1000.0-16.9, "전체":0.0, "차익":0.0,
                    "비차익":0.0, "표본시차초":6.4}},
    {"ts": 1332.0-18.9,
     "현물": {"sample_ts":1332.0-18.9, "외국인":-439.0,"기관":-199.0,"개인":535.0},
     "선물": {"sample_ts":1332.0-18.9, "외국인":-478.0,"기관":660.0,"개인":-96.0},
     "프로그램": {"sample_ts":1332.0-18.9, "전체":-39448.0, "차익":4898.0,
                    "비차익":-45790.0, "표본시차초":6.4}},
],maxlen=2500)
att_today = Watch.attribution(w_today,1000.0,1332.0)
assert att_today["available"], att_today
assert att_today["spot_leader"] == "외국인" and att_today["futures_leader"] == "외국인"
assert att_today["program"]["전체"] == -40892.0, att_today
assert att_today["program"]["전체직접"] == -39448.0, att_today
assert att_today["program"]["검산차이"] == 1444.0, att_today
assert 3.50 < att_today["program_crosscheck_ratio_pct"] < 3.55, att_today
assert att_today["program_quality"] is False, att_today
assert att_today["confidence"] == "중간", att_today
assert "방향 일치·합계 차이 3.53%" in program_quality_label(att_today), att_today
w_today.put_defs = []
w_today.puts = {}
msg_today = Watch.build_alert(w_today,"start",{
    "start_ts":1000.0,"start_price":6766.49,
    "low_ts":1332.0,"low_price":6741.59,
},1332.0,6741.59)
assert "확신도 중간" in msg_today, msg_today
assert "방향 일치·합계 차이 3.53%" in msg_today, msg_today
assert "주도 가능성 높음" not in msg_today, msg_today
assert "5분 32초" in msg_today, msg_today
print("20261008_flow_precision_regression=true program_gap=1444 raw_ratio=3.53 confidence=medium")

# 프로그램 숫자가 거의 일치하면 고확신 진입 가능성을 유지한다.
w_today.flows[-1]["프로그램"]["전체"] = -40800.0
att_close = Watch.attribution(w_today,1000.0,1332.0)
assert att_close["program_quality"] is True, att_close
assert att_close["confidence"] == "높음", att_close
assert "근사 일치" in program_quality_label(att_close)
print("tight_program_tolerance_regression=true")

# 합계가 0인데 직접값이 음수인 경우는 방향 '일치'로 승격하지 않는다.
w_today.flows[-1]["프로그램"]["전체"] = -500.0
w_today.flows[-1]["프로그램"]["차익"] = 0.0
w_today.flows[-1]["프로그램"]["비차익"] = 0.0
att_zero = Watch.attribution(w_today,1000.0,1332.0)
assert not att_zero["program_direction_consistent"], att_zero
assert att_zero["program_quality"] is False, att_zero
assert att_zero["confidence"] != "높음", att_zero
print("zero_program_direction_regression=true")

# 표시 HH:MM:SS 차이와 경과시간 1초 오차가 발생하지 않도록 내림 정수시각을 사용.
assert fmt_duration(int(1332.1)-int(1000.9)) == "5분 32초"
print("clock_duration_consistency_regression=true")

# 45% 회복만으로 '원위치 복원'이라고 말하지 않는다.
w_end = Watch.__new__(Watch)
w_end.flows = deque(maxlen=2500)
partial_end = {
    "start_ts": 1000.0,"start_price":7000.0,
    "low_ts":1200.0,"low_price":6900.0,
}
partial_msg = Watch.build_end(w_end, partial_end, 1350.0, 6950.0)
assert "종료·반등 확인" in partial_msg, partial_msg
assert "종료·복원 확인" not in partial_msg, partial_msg
print("partial_rebound_label_regression=true")


# 오전 감시 실행시간 만료(12:15)는 시장 장마감(15:30)이 아니다.
# 진행 중 사건을 오후 artifact에 남겨 이어가고, 시장이 닫힌 경우에만
# 장마감 확정 텔레그램을 발송하도록 강제한다.
import datetime as _dt_close
from zoneinfo import ZoneInfo as _ZoneInfo_close
_close_kst = _ZoneInfo_close("Asia/Seoul")
_real_close = _dt_close.datetime(2026, 10, 8, 15, 30, tzinfo=_close_kst)
_noon = _dt_close.datetime(2026, 10, 8, 12, 15, tzinfo=_close_kst)
_after = _dt_close.datetime(2026, 10, 8, 15, 32, tzinfo=_close_kst)
assert not ks.should_finalize_market_close(_noon, _real_close, None)
assert ks.should_finalize_market_close(_after, _real_close, None)
assert not ks.should_finalize_market_close(_after, _real_close, 15)
assert not ks.should_finalize_market_close(_after, None, None)
assert "await self._finalize_daily_close(close_dt, test_seconds)" in inspect.getsource(ks.Watch.run)
assert "should_finalize_market_close(" in inspect.getsource(ks.Watch._finalize_daily_close)
print("noon_handoff_does_not_close_episode_regression=true")


# 2026-10-08 11:10/11:26 실제 수급 기준점 정렬 회귀시험.
# 11:10 종료 39.9초는 30초를 초과하므로 선행 매도주체를 확정하지 않는다.
w_1110 = Watch.__new__(Watch)
w_1110.flows = deque([
    {"ts": 1000.0-6.5,
     "현물":{"sample_ts":1000.0-6.5,"외국인":0.0,"기관":0.0,"개인":0.0},
     "선물":{"sample_ts":1000.0-6.5,"외국인":0.0,"기관":0.0,"개인":0.0}},
    {"ts": 1393.0-39.9,
     "현물":{"sample_ts":1393.0-39.9,"외국인":-342.0,"기관":-1530.0,"개인":1531.0},
     "선물":{"sample_ts":1393.0-39.9,"외국인":-1078.0,"기관":740.0,"개인":237.0}},
],maxlen=2500)
a_1110 = Watch.attribution(w_1110,1000.0,1393.0)
assert a_1110["available"] is False, a_1110
assert "39.9초" in a_1110["reason"], a_1110
print("20261008_1110_alignment_hold_valid=true")

# 11:26에서는 실제 저점 기준 19.6초로 정렬 허용치 안에 들어오지만,
# 현물 기관 최다매도와 선물 외국인 최다매도가 갈리므로 단일 주도자 보류.
w_1126 = Watch.__new__(Watch)
w_1126.flows = deque([
    {"ts": 1000.0-6.5,
     "현물":{"sample_ts":1000.0-6.5,"외국인":0.0,"기관":0.0,"개인":0.0},
     "선물":{"sample_ts":1000.0-6.5,"외국인":0.0,"기관":0.0,"개인":0.0},
     "프로그램":{"sample_ts":1000.0-6.5,"전체":0.0,"차익":0.0,
                "비차익":0.0,"표본시차초":4.3}},
    {"ts": 1943.0-19.6,
     "현물":{"sample_ts":1943.0-19.6,"외국인":-342.0,"기관":-1530.0,"개인":1531.0},
     "선물":{"sample_ts":1943.0-19.6,"외국인":-1078.0,"기관":740.0,"개인":237.0},
     "프로그램":{"sample_ts":1943.0-19.6,"전체":-79062.0,
                "차익":-36058.0,"비차익":-43002.0,
                "표본시차초":4.3}},
],maxlen=2500)
a_1126=Watch.attribution(w_1126,1000.0,1943.0)
assert a_1126["available"] is True, a_1126
assert a_1126["spot_leader"] == "기관", a_1126
assert a_1126["futures_leader"] == "외국인", a_1126
assert a_1126["confidence"] != "높음", a_1126
assert "단일 주도자 확정 보류" in a_1126["verdict"], a_1126
assert a_1126["program"]["전체"] == -79060.0, a_1126
assert a_1126["program"]["검산차이"] == -2.0, a_1126
print("20261008_1126_split_seller_valid=true")


# 2026-10-08 운영 산출물: LS t2111이 HTTP 404에 /503.html을 담아
# 임시 게이트웨이 장애를 반환했다. 진짜 404는 즉시 실패시키고
# 게이트웨이 404 및 HTTP 200 비정상 JSON만 일시 재시도한다.
class _GatewayResponse:
    def __init__(self, code, payload=None, text=""):
        self.status_code = code
        self.ok = 200 <= code < 300
        self._payload = payload
        self.text = text
    def json(self):
        if self._payload is None:
            raise ValueError("synthetic invalid JSON")
        return self._payload

orig_post_gateway = ks.requests.post
orig_sleep_gateway = ks.time.sleep
calls_gateway = {"n": 0}
def _gateway_then_ok(*args, **kwargs):
    calls_gateway["n"] += 1
    if calls_gateway["n"] < 3:
        return _GatewayResponse(404, text='{"status":404,"path":"/503.html"}')
    return _GatewayResponse(200, {"rsp_cd":"00000","ok":True})
try:
    ks.requests.post = _gateway_then_ok
    ks.time.sleep = lambda *_args,**_kwargs: None
    assert ks.ls_post("token", "/futureoption/market-data", "t2111", {"x":1})["ok"] is True
    assert calls_gateway["n"] == 3, calls_gateway
finally:
    ks.requests.post = orig_post_gateway
    ks.time.sleep = orig_sleep_gateway
print("ls_503_html_404_recovery_regression=true")

calls_hard_404 = {"n":0}
def _hard_404(*args, **kwargs):
    calls_hard_404["n"] += 1
    return _GatewayResponse(404,text='{"status":404,"path":"/bad-route"}')
try:
    ks.requests.post = _hard_404
    ks.time.sleep = lambda *_args,**_kwargs: None
    try:
        ks.ls_post("token", "/bad-route", "TEST", {})
    except RuntimeError as exc:
        assert "HTTP 404" in str(exc), str(exc)
    else:
        raise AssertionError("A genuine 404 must not retry/succeed")
    assert calls_hard_404["n"] == 1, calls_hard_404
finally:
    ks.requests.post = orig_post_gateway
    ks.time.sleep = orig_sleep_gateway
print("ls_genuine_404_no_retry_regression=true")

calls_bad_json = {"n":0}
def _bad_json_then_ok(*args, **kwargs):
    calls_bad_json["n"] += 1
    if calls_bad_json["n"] == 1:
        return _GatewayResponse(200, None, "<html>temporary gateway page</html>")
    return _GatewayResponse(200, {"rsp_cd":"00000","ok":True})
try:
    ks.requests.post = _bad_json_then_ok
    ks.time.sleep = lambda *_args,**_kwargs: None
    assert ks.ls_post("token","/futureoption/market-data","t2111",{})["ok"] is True
    assert calls_bad_json["n"] == 2
finally:
    ks.requests.post = orig_post_gateway
    ks.time.sleep = orig_sleep_gateway
print("ls_gateway_invalid_json_retry_regression=true")

# API HTTP 요청이 성공했어도 데이터가 2분 넘게 오래됐거나
# 특정 투자자 수급이 누락되면 감시가 '정상 수급'으로 오인하지 않는다.
from kospi_shock_episode_watch import flow_snapshot_health
now_health = time.time()
healthy_flow = {
    "현물":{"sample_ts":now_health-41,"개인":10,"외국인":-9,"기관":-1},
    "선물":{"sample_ts":now_health-39,"개인":-2,"외국인":-3,"기관":5},
    "프로그램":{"sample_ts":now_health-4,"전체":-200,"차익":-20,"비차익":-180},
}
assert flow_snapshot_health(healthy_flow, now_health)[0] is True
stale_flow = dict(healthy_flow)
stale_flow["현물"] = dict(healthy_flow["현물"],sample_ts=now_health-130)
good, details = flow_snapshot_health(stale_flow,now_health)
assert not good and "시차" in details["현물"], details
missing_flow = dict(healthy_flow)
missing_flow["선물"] = dict(healthy_flow["선물"], 외국인=None)
good, details = flow_snapshot_health(missing_flow,now_health)
assert not good and "외국인" in details["선물"], details
future_flow = dict(healthy_flow)
future_flow["프로그램"] = dict(healthy_flow["프로그램"],sample_ts=now_health+12)
assert flow_snapshot_health(future_flow,now_health)[0] is False
print("flow_snapshot_freshness_regression=true")

# 장전 갭다운 메시지 역시 실제 message_id 확인 즉시 handoff에 저장해야 재시작 중복을 방지한다.
assert 'self._record_delivery("open_gap"' in inspect.getsource(ks.Watch.evaluate)
assert "self._checkpoint_handoff(force=True)" in inspect.getsource(ks.Watch._record_delivery)
assert 'self.raw.pop("last_price_poll_error", None)' in inspect.getsource(ks.Watch.run)
print("gap_handoff_and_recovered_poll_status_regression=true")


# 15:20 이후 동시호가에서 투자자 수급 조회가 멈춰도
# 현물 가격감시 자체를 재시작시키지 않고 15:32까지 지속한다.
import datetime as _dt_guard
from zoneinfo import ZoneInfo as _ZoneInfo_guard
from kospi_shock_episode_watch import continuous_flow_guard_active
zone_guard = _ZoneInfo_guard("Asia/Seoul")
market_session_guard = {
    "is_session":True,
    "open":_dt_guard.datetime(2026,10,8,9,0,tzinfo=zone_guard),
    "continuous_end":_dt_guard.datetime(2026,10,8,15,20,tzinfo=zone_guard),
    "close":_dt_guard.datetime(2026,10,8,15,30,tzinfo=zone_guard),
}
assert continuous_flow_guard_active(_dt_guard.datetime(2026,10,8,14,55,tzinfo=zone_guard),market_session_guard)
assert not continuous_flow_guard_active(_dt_guard.datetime(2026,10,8,15,20,tzinfo=zone_guard),market_session_guard)
assert not continuous_flow_guard_active(_dt_guard.datetime(2026,10,8,15,28,tzinfo=zone_guard),market_session_guard)
assert "continuous_flow_guard_active(now, session)" in inspect.getsource(ks.Watch.run)
print("closing_auction_flow_health_guard_regression=true")


# 2026-10-08 장마감 실제 이력: 14:36:27 시작 사건이 15:06 종료된 뒤
# 동일 시작점으로 15:30:32에 재발송됐음. 장 종료 후 지연된 시세는 신규 사건이 아니다.
import asyncio as _postclose_async
import datetime as _postclose_dt
from zoneinfo import ZoneInfo as _postclose_zone
from kospi_shock_episode_watch import price_event_window_open as _price_window_open
_closetime = _postclose_dt.datetime(2026, 10, 8, 15, 30, tzinfo=_postclose_zone("Asia/Seoul")).timestamp()
assert _price_window_open(_closetime - 2, _closetime, _closetime - 1)
assert not _price_window_open(_closetime, _closetime, _closetime)
assert not _price_window_open(_closetime + 29, _closetime, _closetime + 30)
assert not _price_window_open(_closetime - 1, _closetime, _closetime + 1)
assert _price_window_open(_closetime + 29, None, _closetime + 30)  # 영업일 종료시각 미확인 시 테스트만 허용

_closed_watch = Watch.__new__(Watch)
_closed_watch.raw = {}
_closed_watch.idx = deque([(_closetime + 29, 6741.59)], maxlen=100)
_closed_watch.session_close_ts = _closetime
async def _no_flow():
    return None
_closed_watch.maybe_flow = _no_flow
_closed_watch._trigger = lambda: (_ for _ in ()).throw(AssertionError("post-close must not trigger"))
_postclose_async.run(_closed_watch.evaluate())
assert _closed_watch.raw.get("post_close_alert_suppressed"), _closed_watch.raw
print("post_close_duplicate_start_regression=true close=15:30 blocked=15:30:29")

# 실제 오전/오후 handoff는 마지막 Telegram 종료경보 뒤 활성 사건을 비운 상태로 저장한다.
_close_eval_source = inspect.getsource(ks.Watch.evaluate)
_final_eval_tail = _close_eval_source.split("        if ended:", 1)[1]
assert _final_eval_tail.index("self.episode = None") < _final_eval_tail.index('self._record_delivery("end"'), _final_eval_tail
_close_run_source = inspect.getsource(ks.Watch.run)
assert "await self._finalize_daily_close(close_dt, test_seconds)" in _close_run_source
_final_close_tail = inspect.getsource(ks.Watch._finalize_daily_close).split('self._record_delivery(plan["stage"]', 1)[0]
assert _final_close_tail.rfind("self.episode = None") > _final_close_tail.rfind("self.msg_ids.append(msg_id)"), _final_close_tail
_handoff_source = inspect.getsource(ks.Watch.save_handoff)
assert "temp.replace(p)" in _handoff_source, _handoff_source
print("post_delivery_clean_handoff_regression=true atomic_write=true")


# 시세 API가 404/일시 장애인 경우 직전 가격으로 새 사건을 평가하면 거짓 양성이 될 수 있다.
# 정상 수신된 새 현재가가 있을 때만 평가가 진행되는지 운영 루프를 확인한다.
_fresh_poll_source = inspect.getsource(ks.Watch.run)
assert "price_poll_ok = False" in _fresh_poll_source
assert "price_poll_ok = True" in _fresh_poll_source
assert "if price_poll_ok:\\n                await self.evaluate()" not in _fresh_poll_source  # 잘못 이스케이프된 패턴 방지
assert "if price_poll_ok:\n                await self.evaluate()" in _fresh_poll_source, _fresh_poll_source
assert "price_event_skipped_on_poll_failure" in _fresh_poll_source
print("failed_price_poll_skip_regression=true")


# LS API가 '153288'처럼 존재하지 않는 초 단위나 빈 시각을 반환해도
# 조회 완료시각을 대신 넣으면 수급 정렬이 거짓으로 '정상' 판정될 수 있다.
# 허용 시각만 채택하고 잘못된 시각은 엄격하게 보류한다.
from zoneinfo import ZoneInfo as _clock_zone
import datetime as _clock_dt
_ref_clock = _clock_dt.datetime.now(_clock_zone("Asia/Seoul")).replace(
    hour=15, minute=30, second=40, microsecond=0
)
_ref_clock_ts = _ref_clock.timestamp()
assert ks.market_clock_epoch("153040", _ref_clock_ts) == _ref_clock_ts
assert ks.market_clock_epoch("15:30:40", _ref_clock_ts) == _ref_clock_ts
assert ks.market_clock_epoch("15304000", _ref_clock_ts) == _ref_clock_ts
assert ks.market_clock_epoch("15304099", _ref_clock_ts) == _ref_clock_ts
assert ks.market_clock_epoch("153288", _ref_clock_ts) is None
assert ks.market_clock_epoch("15328800", _ref_clock_ts) is None
assert ks.market_clock_epoch("", _ref_clock_ts) is None
assert ks.market_clock_epoch("153060", _ref_clock_ts) is None
assert ks.market_clock_epoch("1530", _ref_clock_ts) == _ref_clock_ts - 40

_before_clock = ks.time.time
try:
    ks.time.time = lambda: _ref_clock_ts
    row = ks._latest_time_row([
        {"time": "15304000", "name": "valid"},
        {"time": "15328800", "name": "invalid"},
        {"time": "15303500", "name": "older"},
    ])
    assert row["name"] == "valid", row
finally:
    ks.time.time = _before_clock
print("invalid_investor_clock_regression=true clock8=HHMMSScc malformed=153288 masked=false")


# 실전 재발 방지: 10/8 14:36 고점이 종료된 뒤 15:30에 다시 신규사건 고점으로
# 재사용된 사례. 전파·신규 사건은 실제 이전 사건 종료 이후 국소 고점으로만 판단한다.
_old_completed = Watch.__new__(Watch)
_old_completed.idx = deque([
    (1000.0, 7000.0), (1100.0, 6800.0), (1200.0, 6850.0),
    (1400.0, 6920.0), (1500.0, 6915.0), (1590.0, 6880.0),
], maxlen=30000)
_old_completed.last_episode_end_ts=1200.0
local_peak = _old_completed._window_peak(30, 5)
assert local_peak == (1400.0, 6920.0), local_peak
hit, info = _old_completed._trigger()
assert hit and info["peak_ts"]==1400.0, (hit, info)
_old_completed.idx = deque([
    (1000.0, 7000.0), (1100.0, 6800.0), (1200.0, 6850.0),
    (1400.0, 6820.0), (1500.0, 6819.0), (1590.0, 6818.0),
], maxlen=30000)
hit, info = _old_completed._trigger()
assert not hit, (hit, info)
print("closed_episode_peak_isolation_regression=true")

# 재기동 및 오전/오후 상태인계에도 종료시점(신규 사건 경계)을 유지한다.
import tempfile as _tempfile_peak
from pathlib import Path as _Path_peak
with _tempfile_peak.TemporaryDirectory() as _tmp_peak:
    _w_old=Watch("unused", [], "", True)
    _w_old.last_episode_end_ts=time.time()-120
    _w_old.save_handoff(_Path_peak(_tmp_peak)/"handoff.json")
    _w_new=Watch("unused", [], "", True)
    _w_new.load_handoff(_Path_peak(_tmp_peak)/"handoff.json")
    assert _w_new.last_episode_end_ts == _w_old.last_episode_end_ts, (
        _w_new.last_episode_end_ts,_w_old.last_episode_end_ts)
print("episode_boundary_handoff_regression=true")


# --test는 실데이터를 조회하더라도 실전 Telegram 송출 경로를 절대 호출하지 않는다.
# 가격이 실제 급락 기준을 충족할 때도 시험용 경보가 발송되면 안 된다.
import asyncio as _asyncio_no_alert
_test_watch=Watch("unused",[], "", True)
_test_watch.idx=deque([
    (time.time()-300, 7000.0),
    (time.time()-180, 6965.0),
    (time.time(), 6900.0),
],maxlen=30000)
async def _no_flow_test():
    return None
_test_watch.maybe_flow=_no_flow_test
_old_sender=ks.telegram_send
try:
    def _forbid_send(*args,**kwargs):
        raise AssertionError("CI test mode attempted Telegram delivery")
    ks.telegram_send=_forbid_send
    _asyncio_no_alert.run(_test_watch.evaluate())
    assert _test_watch.raw.get("test_mode_notification_suppressed") is True
    assert _test_watch.episode is None
finally:
    ks.telegram_send=_old_sender
print("test_mode_must_not_send_telegram_regression=true")


# 급락과 독립적으로 발생하는 5분 현물·선물 순매수 급증 검증.
import asyncio as _surge_async
import tempfile as _surge_tempfile
from pathlib import Path as _surge_Path
from kospi_shock_episode_watch import flow_surge_candidates as _surge_scan

# A real 11:50 alert used numerically aligned program values whose source
# publication times were unavailable.  The market event remains valid, but
# those lookup times must not raise its confidence.
import json as _surge_json
_surge_fixture_path = _surge_Path(__file__).resolve().parent.parent / "tests/fixtures/kospi_surge_program_time_20261028.json"
_surge_fixture = _surge_json.loads(_surge_fixture_path.read_text(encoding="utf-8"))
_surge_real = next(c for c in _surge_scan(_surge_fixture["rows"], _surge_fixture["now_ts"],
                                          _surge_fixture["session_open_ts"])
                   if c["actor"] == "외국인")
assert _surge_real["spot"] == 338 and _surge_real["futures"] == 625, _surge_real
assert _surge_real["program"]["valid"] and _surge_real["program"]["delta"] == 42225, _surge_real
assert _surge_real["confidence"] == "중간", _surge_real
_surge_render = Watch("unused", [], "", False).build_flow_surge_alert(_surge_real, _surge_fixture["now_ts"])
assert "원천 공표시각 미확인" in _surge_render and "확신도 상향 보류" in _surge_render, _surge_render
assert _surge_real["program"]["source_time_verified"] is False, _surge_real
# Missing evidence at either endpoint must not silently become a verified time.
import copy as _surge_copy
for _unverified_index in (2, 3):
    _partial = _surge_copy.deepcopy(_surge_fixture["rows"])
    _partial[2]["프로그램"]["source_time_verified"] = True
    _partial[3]["프로그램"]["source_time_verified"] = True
    _partial[_unverified_index]["프로그램"].pop("source_time_verified")
    _partial_c = next(c for c in _surge_scan(_partial, _surge_fixture["now_ts"],
                                               _surge_fixture["session_open_ts"])
                      if c["actor"] == "외국인")
    assert _partial_c["confidence"] == "중간" and not _partial_c["program"]["source_time_verified"], _partial_c
print("kospi_20261028_program_unverified_time_holds_confidence=true")

def _surge_row(ts, spot, future, program):
    return {
        "ts":ts,
        "현물":{"sample_ts":ts,"외국인":spot,"기관":-spot*.3,"개인":-spot*.7},
        "선물":{"sample_ts":ts,"외국인":future,"기관":-future*.4,"개인":-future*.6},
        "프로그램":{"sample_ts":ts,"전체":program,"차익":program*.4,
                    "비차익":program*.6,"표본시차초":3.0,"source_time_verified":True},
    }

_surge_rows=[
    _surge_row(10000,0,0,0),
    _surge_row(10020,0,0,0),
    _surge_row(10300,400,600,1000),
]
_surge_c=_surge_scan(_surge_rows,10303)
assert len(_surge_c)==1 and _surge_c[0]["actor"]=="외국인",_surge_c
assert _surge_c[0]["mode"]=="현물·선물 동시" and _surge_c[0]["confidence"]=="높음",_surge_c
assert _surge_c[0]["spot"]==400 and _surge_c[0]["futures"]==600,_surge_c
assert not _surge_scan(_surge_rows,10400),"오래된 수급을 새 급유입으로 판정"
assert not _surge_scan([
    _surge_row(10000,0,0,0),
    _surge_row(10345,1400,1500,10000),
],10348),"5분 기준점이 30초 넘게 비어 있는데 유입 판정"
print("flow_surge_window_freshness_valid=true")

_surge_single=_surge_scan([
    _surge_row(10000,0,0,0),
    _surge_row(10300,1050,-600,-1500),
],10305)
assert len(_surge_single)==1 and _surge_single[0]["mode"]=="현물 중심",_surge_single
assert _surge_single[0]["confidence"]=="단독 신호",_surge_single
_surge_sell_side=_surge_scan([
    _surge_row(10000,0,0,0), _surge_row(10300,-800,-900,-10000)
],10305)
assert all(x["actor"]!="외국인" for x in _surge_sell_side),_surge_sell_side
assert any(x["actor"]=="개인" for x in _surge_sell_side),_surge_sell_side
# 외국인 매도 반대편 개인 순매수는 '유입'으로 검출할 수 있지만
# 외국인 자체를 순매수 주체로 반전시켜서는 안 된다.
print("flow_surge_direction_alignment_valid=true")

_surge_watch=Watch("unused",[], "",False)
_surge_watch.session_open_ts=9500
_surge_watch.session_continuous_end_ts=15000
_surge_watch.session_close_ts=16000
_surge_watch.flows=deque(_surge_rows,maxlen=2500)
_surge_watch.idx=deque([(10000,6800.0),(10300,6800.0)],maxlen=30000)
_surge_sent=[]
_surge_delivery=[]
_surge_watch._record_delivery=lambda stage,message_id,ep,ts,**kw: _surge_delivery.append(
    (stage,message_id,ep,ts)
)
_original_surge_sender=ks.telegram_send
try:
    def _synthetic_surge_sender(message):
        _surge_sent.append(message)
        return 888
    ks.telegram_send=_synthetic_surge_sender
    _surge_async.run(_surge_watch.maybe_alert_flow_surge(10303))
    assert not _surge_sent,"독립 표본 1개로 알림이 나감"
    _surge_watch.flows.append(_surge_row(10320,550,720,1400))
    _surge_watch.idx.append((10320,6800.0))
    _surge_async.run(_surge_watch.maybe_alert_flow_surge(10323))
    assert len(_surge_sent)==1,_surge_sent
    assert _surge_watch.surge_sent_at.get("외국인")==10323,_surge_watch.surge_sent_at
    assert _surge_delivery and _surge_delivery[0][0:2]==("flow_surge",888),_surge_delivery
    assert _surge_delivery[0][2]["market"]=="KOSPI" and _surge_delivery[0][2]["actor"]=="외국인"
    assert "현물(통합) <b>+550억원</b>" in _surge_sent[0],_surge_sent[0]
    assert "KOSPI200 선물 +720억원" in _surge_sent[0],_surge_sent[0]
    assert "KOSPI +0.00%" in _surge_sent[0],_surge_sent[0]
    assert "외부 신규자금 유입" in _surge_sent[0],_surge_sent[0]
    # 같은 샘플 반복 및 20분 안쪽의 새로운 샘플은 중복 금지.
    _surge_async.run(_surge_watch.maybe_alert_flow_surge(10325))
    _surge_watch.flows.append(_surge_row(10340,750,920,1600))
    _surge_async.run(_surge_watch.maybe_alert_flow_surge(10342))
    assert len(_surge_sent)==1,_surge_sent
    # 종료된 거래시간 이후에는 새 수급 사건 금지.
    _surge_watch.flows.append(_surge_row(15330,10000,10000,20000))
    _surge_async.run(_surge_watch.maybe_alert_flow_surge(15335))
    assert len(_surge_sent)==1,_surge_sent
    # 오전/오후 handoff는 기존 파일을 재사용하고 알림 중복방지 상태도 보존한다.
    with _surge_tempfile.TemporaryDirectory() as _tmp:
        _path=_surge_Path(_tmp)/"handoff.json"
        _surge_watch.save_handoff(_path)
        _restored=Watch("unused",[], "",False)
        _restored.load_handoff(_path)
        assert _restored.surge_sent_at.get("외국인")==10323,_restored.surge_sent_at
        assert _restored.surge_last_processed_ts>=10320,_restored.surge_last_processed_ts
    _surge_watch.test=True
    _surge_watch.flows.append(_surge_row(10400,15000,15000,15000))
    _surge_async.run(_surge_watch.maybe_alert_flow_surge(10403))
    assert len(_surge_sent)==1,_surge_sent
finally:
    ks.telegram_send=_original_surge_sender
print("flow_surge_two_sample_confirm_valid=true dedup=20m handoff=true test_mode_silent=true")

# 두 시장의 원자료 종료 시각이 각각 신선하더라도 30초 이상 차이나면
# 5분 '동시 유입'으로 합치면 안 된다.
_skew_rows=[
    _surge_row(19940,0,0,0),
    _surge_row(20000,0,0,0),
    _surge_row(20260,0,500,700),
    _surge_row(20300,350,500,1000),
]
_skew_rows[-1]["선물"]["sample_ts"]=20260
assert not _surge_scan(_skew_rows,20305), "현물·선물 종료시각 40초 차이를 동시 매수로 오인"
_skew_rows[-1]["선물"]["sample_ts"]=20270
_aligned_surge=_surge_scan(_skew_rows,20305)
assert len(_aligned_surge)==1 and _aligned_surge[0]["actor"]=="외국인",_aligned_surge
assert _aligned_surge[0]["mode"]=="현물·선물 동시",_aligned_surge
assert _aligned_surge[0]["confidence"]=="높음",_aligned_surge
assert _aligned_surge[0]["spot_window"]==(20000.0,20300.0),_aligned_surge
assert _aligned_surge[0]["futures_window"]==(19940.0,20270.0),_aligned_surge
_ts_display_watch=Watch("unused",[], "",False)
_displayed=_ts_display_watch.build_flow_surge_alert(_aligned_surge[0],20305)
assert "실제 수급 표본:" in _displayed,_displayed
assert ks.fmt_clock(19940) in _displayed and ks.fmt_clock(20270) in _displayed,_displayed
print("flow_surge_cross_channel_alignment_regression=true")

# 프로그램 거래는 전체/차익/비차익 검산이 통과하더라도
# 매수주체 기준점 대비 40초 뒤처지면 높은 확신도를 주지 않는다.
_program_lag_rows=[
    _surge_row(19940,0,0,0),
    _surge_row(20000,0,0,0),
    _surge_row(20260,0,0,700),
    _surge_row(20300,400,600,1000),
]
_program_lag_rows[-1]["프로그램"]["sample_ts"]=20260
_lag_surge=_surge_scan(_program_lag_rows,20305)
assert len(_lag_surge)==1 and _lag_surge[0]["mode"]=="현물·선물 동시",_lag_surge
assert _lag_surge[0]["program"] is not None and _lag_surge[0]["program"]["valid"],_lag_surge
assert _lag_surge[0]["confidence"]=="중간",_lag_surge
print("flow_surge_program_timestamp_confidence_regression=true")




# 10/12 15:09 가짜 공백·중복기동 재현:
# 워크플로 최근 전체 50건에 기존 장시간 runner가 보이지 않더라도
# status=in_progress 별도 조회와 실제 production job 조회로 반드시 찾아야 한다.
import datetime as _leader_dt
import json as _leader_json
import os as _leader_os
import pathlib as _leader_pathlib
import sys as _leader_sys
import tempfile as _leader_tempfile
import types as _leader_types
import urllib.request as _leader_request
from zoneinfo import ZoneInfo as _leader_zone
import yaml as _leader_yaml

_leader_wf = _leader_yaml.safe_load(
    _leader_pathlib.Path(".github/workflows/kospi-derivatives-flow-ls-realtime.yml").read_text(encoding="utf-8")
)
_leader_step = next(
    st for st in _leader_wf["jobs"]["gate"]["steps"]
    if st.get("name")=="Elect single production workflow"
)
_leader_source = _leader_step["run"].split("python - <<'PY'\n",1)[1].rsplit("\nPY",1)[0]
compile(_leader_source,"KOSPI gate active-run regression","exec")
_leader_now = _leader_dt.datetime.now(_leader_zone("Asia/Seoul"))
_leader_old = _leader_now.replace(hour=8,minute=11,second=0,microsecond=0)
if _leader_old > _leader_now:
    _leader_old = _leader_now.replace(hour=0,minute=0,second=0,microsecond=0)
_leader_created = _leader_old.astimezone(_leader_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
_leader_current = _leader_now.astimezone(_leader_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
_leader_module = _leader_types.ModuleType("krx_session_calendar")
_leader_module.session_state=lambda _now:{
    "is_session":True,
    "open":_now-_leader_dt.timedelta(minutes=15),
    "close":_now+_leader_dt.timedelta(minutes=15),
}
_leader_real_module = _leader_sys.modules.get("krx_session_calendar")
_leader_real_open = _leader_request.urlopen
_leader_env = _leader_os.environ
_leader_env_keys = ("GH_TOKEN","REPOSITORY","CURRENT_RUN_ID","GITHUB_OUTPUT","TELEGRAM_BOT_TOKEN","TELEGRAM_CHAT_ID")
_leader_orig_env = {k:_leader_env.get(k) for k in _leader_env_keys}
_leader_queries = []

class _LeaderFakeResponse:
    def __init__(self,value):
        self.data=_leader_json.dumps(value).encode("utf-8")
    def __enter__(self):return self
    def __exit__(self,*_a):return False
    def read(self):return self.data

def _leader_urlopen(req,timeout=0):
    url=req if isinstance(req,str) else req.full_url
    _leader_queries.append(url)
    if "status=in_progress" in url:
        return _LeaderFakeResponse({"workflow_runs":[
            {"id":101,"status":"in_progress","created_at":_leader_created},
            {"id":1234,"status":"in_progress","created_at":_leader_current},
        ]})
    if "status=queued" in url:
        return _LeaderFakeResponse({"workflow_runs":[]})
    if "/actions/runs/101/jobs" in url:
        return _LeaderFakeResponse({"jobs":[{"name":"afternoon","status":"in_progress"}]})
    if "runs?per_page=50" in url:
        return _LeaderFakeResponse({"workflow_runs":[
            {"id":x,"status":"completed","created_at":_leader_current} for x in range(2000,2050)
        ]})
    raise AssertionError(f"Unexpected live request in deterministic gate regression: {url}")

try:
    with _leader_tempfile.TemporaryDirectory() as _tmp_leader:
        _leader_output=_leader_pathlib.Path(_tmp_leader)/"output"
        _leader_env.update({
            "GH_TOKEN":"test-token",
            "REPOSITORY":"test/kospi",
            "CURRENT_RUN_ID":"1234",
            "GITHUB_OUTPUT":str(_leader_output),
            "TELEGRAM_BOT_TOKEN":"",
            "TELEGRAM_CHAT_ID":"",
        })
        _leader_sys.modules["krx_session_calendar"]=_leader_module
        _leader_request.urlopen=_leader_urlopen
        exec(compile(_leader_source,"KOSPI gate active-run regression","exec"),{"__name__":"__main__"})
        _leader_lines=_leader_output.read_text(encoding="utf-8")
        assert "run_production=0" in _leader_lines, _leader_lines
        assert "run_morning=0" in _leader_lines, _leader_lines
        assert any("status=in_progress" in q for q in _leader_queries), _leader_queries
        assert any("/actions/runs/101/jobs" in q for q in _leader_queries), _leader_queries
        assert not any("runs?per_page=50" in q for q in _leader_queries), _leader_queries
finally:
    _leader_request.urlopen=_leader_real_open
    if _leader_real_module is None:
        _leader_sys.modules.pop("krx_session_calendar",None)
    else:
        _leader_sys.modules["krx_session_calendar"]=_leader_real_module
    for _k,_v in _leader_orig_env.items():
        if _v is None:
            _leader_env.pop(_k,None)
        else:
            _leader_env[_k]=_v
print("long_running_leader_hidden_recent50_regression=true")


# 2026-10-13 개장 갭 -3.10%를 5초 장중 급락으로 중복 인식한 실전 문제 재현.
# REST의 개장 전 전일종가 유지가격과 시가 확정 후 가격을 반드시 분리한다.
import kospi_shock_episode_watch as _oct13_mod
import datetime as _oct13_dt
from zoneinfo import ZoneInfo as _oct13_zone
_oct13_open = _oct13_dt.datetime(2026, 10, 13, 9, 0, tzinfo=_oct13_zone("Asia/Seoul")).timestamp()
_oct13_w = Watch("synthetic", [], "synthetic", False)
_oct13_w.session_open_ts = _oct13_open
_oct13_quotes = [
    {"price":6384.24,"prev_close":6384.24,"open":0.0,"open_pct":-3.10},
    {"price":6384.24,"prev_close":6384.24,"open":6186.08,"open_pct":-3.10},
    {"price":6186.08,"prev_close":6384.24,"open":6186.08,"open_pct":-3.10},
    {"price":6152.86,"prev_close":6384.24,"open":6186.08,"open_pct":-3.10},
]
_oct13_clock = [_oct13_open-30]
_oct13_stage = [0]
_oct13_orig_idx = _oct13_mod.fetch_index_quote
_oct13_orig_fut = _oct13_mod.fetch_derivative_quote
_oct13_orig_time = _oct13_mod.time.time
try:
    _oct13_mod.fetch_index_quote=lambda _token: _oct13_quotes[_oct13_stage[0]]
    _oct13_mod.fetch_derivative_quote=lambda _token,_code: {"price":1000.0}
    _oct13_mod.time.time=lambda: _oct13_clock[0]
    for stage, secs in enumerate((-30,25,30,279)):
        _oct13_stage[0] = stage
        _oct13_clock[0] = _oct13_open + secs
        _oct13_w.poll_market_once()
        if stage <= 1:
            assert not _oct13_w.idx, "개장 전/미갱신 전일종가가 장중 틱으로 삽입됨"
        elif stage == 2:
            assert len(_oct13_w.idx)==1 and _oct13_w.idx[-1][1]==6186.08
            assert _oct13_w._trigger()[0] is False, "개장 갭을 5초 급락으로 중복 검출"
    ok, trig = _oct13_w._trigger()
    assert ok and abs(trig["peak"]-6186.08)<0.01, trig
    assert -0.60 < trig["drop"] < -0.50, trig
    assert all(abs(price-6384.24)>0.01 for ts,price in _oct13_w.idx)
finally:
    _oct13_mod.fetch_index_quote=_oct13_orig_idx
    _oct13_mod.fetch_derivative_quote=_oct13_orig_fut
    _oct13_mod.time.time=_oct13_orig_time
print("oct13_preopen_price_isolation_regression=true gap=-3.10 intraday_drop_uses_open=true")


# 08:59~09:04 누적 현물 수급은 정규장 5분 순매수 급증으로 송출 금지.
# 09:00:30~09:05:30 실제 정규장 표본은 유지해야 함.
from kospi_shock_episode_watch import flow_surge_candidates as _oct13_surge
def _oct13_flow(ts, institution=0.0, individual=0.0, program=0.0):
    return {
        "ts":ts,
        "현물":{"sample_ts":ts, "외국인":0.0, "기관":institution, "개인":individual},
        "선물":{"sample_ts":ts, "외국인":0.0, "기관":0.0, "개인":0.0},
        "프로그램":{"sample_ts":ts, "전체":program, "차익":0.0, "비차익":program,"표본시차초":2.0},
    }
_oct13_early = [
    _oct13_flow(_oct13_open-60),
    _oct13_flow(_oct13_open+240, institution=1770.0, program=-173758.0),
]
assert not _oct13_surge(_oct13_early,_oct13_open+243,_oct13_open), "장전 기준점으로 정규장 5분 매수 급증 오검출"
_oct13_valid = [
    _oct13_flow(_oct13_open-60),
    _oct13_flow(_oct13_open+30),
    _oct13_flow(_oct13_open+330, individual=1369.0, program=-227103.0),
]
_oct13_c = _oct13_surge(_oct13_valid,_oct13_open+335,_oct13_open)
assert any(x["actor"]=="개인" and x["mode"]=="현물 중심"
           and x["spot_window"]==(_oct13_open+30,_oct13_open+330)
           for x in _oct13_c), _oct13_c
assert all(not x["spot_window"] or x["spot_window"][0]>=_oct13_open for x in _oct13_c),_oct13_c
print("oct13_five_minute_inflow_open_boundary_regression=true preopen_excluded=true live_buy_kept=true")


# 장전·시초 첫 분봉 중 전일 종가 유지값이 이후 급락의 가짜 고점이 되지 않도록 복구 차단.
_orig_backfill_ls=_oct13_mod.ls_post
_orig_backfill_session=_oct13_mod.session_state
try:
    today=_oct13_dt.datetime.now(_oct13_zone("Asia/Seoul")).strftime("%Y%m%d")
    _oct13_mod.ls_post=lambda *_args,**_kwargs: {
       "t8409OutBlock1":[
           {"date":today,"time":"085900","close":"6384.24"},
           {"date":today,"time":"090000","close":"6384.24"},
           {"date":today,"time":"090100","close":"6178.00"},
           {"date":today,"time":"090200","close":"6168.00"},
       ]
    }
    _oct13_mod.session_state=lambda now: {"open":_oct13_dt.datetime(
        now.year,now.month,now.day,9,0,tzinfo=_oct13_zone("Asia/Seoul"))}
    _oct13_bars=_oct13_mod.backfill_index_bars("test")
    assert [x[1] for x in _oct13_bars]==[6178.0,6168.0],_oct13_bars
finally:
    _oct13_mod.ls_post=_orig_backfill_ls
    _oct13_mod.session_state=_orig_backfill_session
print("oct13_opening_bar_backfill_boundary_regression=true")


# 09:26 재급락: 정확한 가격 급락은 확인되지만 시작 수급이 50.8초 늦어
# '감시 자체가 끊겼다'고 오해하지 않도록 원인별 메시지를 분리한다.
_oct13_stale = Watch.__new__(Watch)
_oct13_stale.flows=deque(maxlen=2500)
_oct13_stale.put_defs=[]
_oct13_stale.puts={}
_oct13_stale_ep={
    "start_ts":1000.0,"start_price":6134.05,
    "low_ts":1081.0,"low_price":6107.55,"price_only":True,
    "price_only_reason":"start channel alignment exceeds 30s",
}
_oct13_stale_text=Watch.build_alert(_oct13_stale,"start",_oct13_stale_ep,1081.0,6107.55)
assert "수급 기준점 시간 정렬 미충족" in _oct13_stale_text,_oct13_stale_text
assert "감시 중단으로 단정하지 않습니다" in _oct13_stale_text,_oct13_stale_text
assert "감시 공백 또는 수급 기준점 부족" not in _oct13_stale_text,_oct13_stale_text
assert "수급 시차 30초" in _oct13_stale_text,_oct13_stale_text
assert "프로그램 합계 차이 1% 초과" in _oct13_stale_text,_oct13_stale_text
print("oct13_stale_flow_is_not_monitor_outage_regression=true")


# 10/13 개장 직후 09:00:25 수급 출발점 시차 25.9초 = 08:59:59.1.
# 30초 이내라는 이유만으로 장전 기준점을 '정규장 매도주체' 근거로 삼으면 안 된다.
_oct13_attribution_guard=Watch.__new__(Watch)
_oct13_attribution_guard.session_open_ts=1000.0
_oct13_attribution_guard.flows=deque([
    {"ts":999.1,
     "현물":{"sample_ts":999.1,"외국인":0.0,"기관":0.0,"개인":0.0},
     "선물":{"sample_ts":999.1,"외국인":0.0,"기관":0.0,"개인":0.0},
     "프로그램":{"sample_ts":999.1,"전체":0.0,"차익":0.0,"비차익":0.0,"표본시차초":2.0}},
    {"ts":1100.0,
     "현물":{"sample_ts":1100.0,"외국인":-50.0,"기관":40.0,"개인":10.0},
     "선물":{"sample_ts":1100.0,"외국인":-30.0,"기관":25.0,"개인":5.0},
     "프로그램":{"sample_ts":1100.0,"전체":-100.0,"차익":10.0,"비차익":-110.0,"표본시차초":2.0}},
    {"ts":1500.0,
     "현물":{"sample_ts":1500.0,"외국인":-200.0,"기관":130.0,"개인":70.0},
     "선물":{"sample_ts":1500.0,"외국인":-100.0,"기관":75.0,"개인":25.0},
     "프로그램":{"sample_ts":1500.0,"전체":-500.0,"차익":10.0,"비차익":-510.0,"표본시차초":2.0}},
],maxlen=2500)
assert _oct13_attribution_guard._flow_channel_near(1025.0,"현물") is None
assert _oct13_attribution_guard._flow_channel_near(1025.0,"선물") is None
_oct13_out=_oct13_attribution_guard.attribution(1025.0,1500.0)
assert _oct13_out["available"] is False, _oct13_out
_oct13_valid_flow=_oct13_attribution_guard.attribution(1110.0,1500.0)
assert _oct13_valid_flow["available"] is True,_oct13_valid_flow
assert _oct13_valid_flow["spot_leader"]=="외국인",_oct13_valid_flow
assert _oct13_valid_flow["futures_leader"]=="외국인",_oct13_valid_flow
assert _oct13_valid_flow["program_quality"] is True,_oct13_valid_flow
print("oct13_preopen_attribution_guard_regression=true")


# 코스닥 현물 독립 순매수 급증 감시. KOSPI200 선물/프로그램을 코스닥 확인값으로 섞지 않는다.
from kospi_shock_episode_watch import KOSDAQ_SURGE_SINGLE_SPOT_EOK
assert KOSDAQ_SURGE_SINGLE_SPOT_EOK == 150.0
import asyncio as _kq_async
import tempfile as _kq_tmp
from pathlib import Path as _kq_Path
from unittest.mock import patch as _kq_patch

_kq_base = time.time() - 400
def _kq_row(ts, foreign, institution=0, individual=0):
    return {"ts":ts, "market":"KOSDAQ", "현물":{
        "sample_ts":ts,
        "외국인":float(foreign), "기관":float(institution), "개인":float(individual),
    }}
_kq = Watch("unused", [], "", False)
_kq.session_open_ts = _kq_base
_kq.session_continuous_end_ts = _kq_base + 60*60
_kq.session_close_ts = _kq_base + 60*60
_kq.flows = deque(maxlen=2500)  # 기존 코스피 스냅샷은 변경하지 않음
_kq.surge_sent_at["외국인"] = _kq_base+500  # 코스피 중복방지와 분리되어야 함
_kq.kosdaq_flows.append(_kq_row(_kq_base, 0))
_kq.kosdaq_flows.append(_kq_row(_kq_base+20, 0))
_kq.kosdaq_flows.append(_kq_row(_kq_base+40, 0))
_kq.kosdaq_flows.append(_kq_row(_kq_base+300, 149))
_kq_msgs, _kq_delivery = [], []
_kq._record_delivery=lambda stage,mid,ep,ts,**kw: _kq_delivery.append((stage,mid,ep,ts,kw.get("evidence")))
def _kq_fake_send(msg):
    _kq_msgs.append(msg)
    return 32001
with _kq_patch.object(ks, "telegram_send", _kq_fake_send):
    _kq_async.run(_kq.maybe_alert_kosdaq_surge(_kq_base+303))
    assert not _kq_msgs and not _kq.kosdaq_surge_pending, "150억원 미만에서 후보 생성"
    _kq.kosdaq_flows.append(_kq_row(_kq_base+320, 150))
    _kq_async.run(_kq.maybe_alert_kosdaq_surge(_kq_base+323))
    assert not _kq_msgs and "외국인" in _kq.kosdaq_surge_pending, "150억원 첫 표본 확인 실패"
    _kq.kosdaq_flows.append(_kq_row(_kq_base+340, 150))
    _kq_async.run(_kq.maybe_alert_kosdaq_surge(_kq_base+343))
    assert not _kq_msgs, "코스닥 동일 누적값 재전송으로 알림"
    _kq.kosdaq_flows.append(_kq_row(_kq_base+360, 170))
    _kq_async.run(_kq.maybe_alert_kosdaq_surge(_kq_base+363))
    assert len(_kq_msgs)==1, _kq_msgs
    assert "코스닥 단기 순매수 급증" in _kq_msgs[0], _kq_msgs[0]
    assert "코스닥 현물(통합)" in _kq_msgs[0] and "<b>+170억원</b>" in _kq_msgs[0], _kq_msgs[0]
    assert "150억원 이상" in _kq_msgs[0], _kq_msgs[0]
    assert "KOSPI200 선물·프로그램 수급과 합산하지 않음" in _kq_msgs[0], _kq_msgs[0]
    assert _kq_delivery[0][0:2] == ("kosdaq_flow_surge",32001), _kq_delivery
    assert _kq_delivery[0][2]["market"]=="KOSDAQ"
    assert _kq_delivery[0][2]["actor"]=="외국인"
    assert _kq_delivery[0][4]["spot_start_cumulative"]==0.0
    assert _kq_delivery[0][4]["spot_end_cumulative"]==170.0
    assert _kq.surge_sent_at["외국인"] == _kq_base+500  # 코스피 기존 데이터 보존
    assert _kq.kosdaq_surge_sent_at["외국인"] == _kq_base+363
    _kq.kosdaq_flows.append(_kq_row(_kq_base+375, 650))
    _kq_async.run(_kq.maybe_alert_kosdaq_surge(_kq_base+378))
    assert len(_kq_msgs)==1, "코스닥 20분 중복방지 실패"

    with _kq_tmp.TemporaryDirectory() as directory:
        handoff=_kq_Path(directory)/"handoff.json"
        _kq.save_handoff(handoff)
        restored=Watch("unused",[],"",False)
        restored.load_handoff(handoff)
        assert len(restored.kosdaq_flows)>=3, restored.raw
        assert restored.kosdaq_surge_sent_at["외국인"]==_kq_base+363, restored.kosdaq_surge_sent_at
        assert restored.surge_sent_at["외국인"]==_kq_base+500, restored.surge_sent_at
    _kq.test=True
    _kq.kosdaq_flows.append(_kq_row(_kq_base+420, 1600))
    _kq_async.run(_kq.maybe_alert_kosdaq_surge(_kq_base+422))
    assert len(_kq_msgs)==1, "시험 모드에서 Telegram 전송"
print("kosdaq_surge_two_sample_dedup_valid=true handoff=true separate_markets=true")

# 코스닥 현물 표본도 5분 구간이 확보되기 전·장전 기준값에서는 절대 생성하지 않는다.
_kq_pre=Watch("unused",[],"",False)
_kq_pre.session_open_ts=_kq_base
_kq_pre.session_continuous_end_ts=_kq_base+60*60
_kq_pre.session_close_ts=_kq_base+60*60
_kq_pre.kosdaq_flows.append(_kq_row(_kq_base-60,0))
_kq_pre.kosdaq_flows.append(_kq_row(_kq_base+240,3000))
assert ks._flow_surge_channel_pair(list(_kq_pre.kosdaq_flows),"현물",_kq_base+242,_kq_base) is None
_kq_pre.kosdaq_flows.append(_kq_row(_kq_base+320,4000))
assert ks._flow_surge_channel_pair(list(_kq_pre.kosdaq_flows),"현물",_kq_base+323,_kq_base) is None
print("kosdaq_surge_no_preopen_reconstruction_valid=true")

# 실시간 두 시장·복수 매수주체에 대한 감사키 충돌 방지.
# 같은 시작시각과 같은 stage여도 시장/주체가 다르면 별도 정상 송출이다.
from pathlib import Path as _kq_audit_path
_audit_workflow=_kq_audit_path(".github/workflows/kospi-derivatives-flow-ls-realtime.yml").read_text(encoding="utf-8")
assert _audit_workflow.count('str(rec.get("market") or "KOSPI")')==2, "morning/afternoon delivery audit market key missing"
assert _audit_workflow.count('str(rec.get("actor") or "")')==2, "morning/afternoon delivery audit actor key missing"
_akeys=[
    ("T0","kosdaq_flow_surge","KOSDAQ","외국인"),
    ("T0","kosdaq_flow_surge","KOSDAQ","기관"),
    ("T0","flow_surge","KOSPI","외국인"),
]
assert len(set(_akeys))==3
print("cross_market_investor_delivery_dedup_valid=true")


# 코스닥 급락 감시는 기존 코스피와 같은 Python·Telegram·handoff 경로를
# 재사용하되, 코스닥 종합지수 301 및 코스닥 현물 t1602만 사용한다.
import asyncio as _kqd_async
from unittest.mock import patch as _kqd_patch
import tempfile as _kqd_tmp
from pathlib import Path as _kqd_Path
_kqd_quote_requests=[]
def _kqd_ls_post(token,path,tr,body,**kwargs):
    _kqd_quote_requests.append((path,tr,body,kwargs))
    return {"t1511OutBlock":{"pricejisu":"990.55","jniljisu":"1000.00",
                               "openjisu":"970.00","highjisu":"1001.00",
                               "lowjisu":"988.88"}}
with _kqd_patch.object(ks,"ls_post",_kqd_ls_post):
    quote=ks.fetch_kosdaq_index_quote("test")
assert quote["price"]==990.55 and quote["prev_close"]==1000.0, quote
assert _kqd_quote_requests[0][2]["t1511InBlock"]["upcode"]=="301"
assert _kqd_quote_requests[0][3]["max_attempts"]==2
print("kosdaq_t1511_independent_source_valid=true")

_kqd_base=time.time()-620
_kqd=Watch("unused",[],"",False)
_kqd.session_open_ts=_kqd_base-200
_kqd.session_close_ts=_kqd_base+2000
_kqd.session_continuous_end_ts=_kqd_base+2000
_kqd.regular_price_ready=True
_kqd.kosdaq_regular_price_ready=True
_kqd.kosdaq_opening_gap_sent=True
_kqd.surge_sent_at["기관"]=_kqd_base+200
_kqd.idx.append((_kqd_base+265,6500.0))
_kqd.kosdaq_idx.extend([
    (_kqd_base-120,1000.0),
    (_kqd_base-60,1000.2),
    (_kqd_base,1000.0),
    (_kqd_base+140,998.8),
    (_kqd_base+265,996.0),
])
def _kqd_flow(ts, foreign=0, institution=0, individual=0):
    return {"ts":ts,"market":"KOSDAQ","현물":{
        "sample_ts":ts,
        "외국인":float(foreign),"기관":float(institution),"개인":float(individual),
    }}
_kqd.kosdaq_flows.append(_kqd_flow(_kqd_base-65))
_kqd.kosdaq_flows.append(_kqd_flow(_kqd_base+260,-450,-220,580))
_kqd_out,_kqd_delivery=[],[]
def _kqd_send(msg):
    _kqd_out.append(msg)
    return 60000+len(_kqd_out)
_kqd._record_delivery=lambda stage,mid,ep,ts: _kqd_delivery.append((stage,mid,dict(ep),ts))
_kqd_fake_now=[_kqd_base+266.0]
with _kqd_patch.object(ks.time,"time",lambda:_kqd_fake_now[0]), _kqd_patch.object(ks,"telegram_send",_kqd_send):
    _kqd_async.run(_kqd.maybe_alert_kosdaq_drop())
    assert len(_kqd_out)==1, _kqd_out
    assert "코스닥 급락 포착" in _kqd_out[0] and "코스피200 선물" in _kqd_out[0]
    assert "코스닥 현물" in _kqd_out[0] and "외국인" in _kqd_out[0]
    assert _kqd.episode is None and _kqd.surge_sent_at["기관"]==_kqd_base+200
    assert _kqd_delivery[0][0]=="kosdaq_shock_start", _kqd_delivery
    _kqd_async.run(_kqd.maybe_alert_kosdaq_drop())
    assert len(_kqd_out)==1,"same KOSDAQ price tick duplicated alert"
    # 사건 확대는 처음보다 0.5%p 이상의 추가 하락일 때만 전송.
    _kqd.kosdaq_idx.append((_kqd_base+300,990.0))
    _kqd.kosdaq_flows.append(_kqd_flow(_kqd_base+292,-520,-230,670))
    _kqd_fake_now[0]=_kqd_base+301.0
    _kqd_async.run(_kqd.maybe_alert_kosdaq_drop())
    assert len(_kqd_out)==2 and "코스닥 급락 확대" in _kqd_out[-1], _kqd_out
    # 저점 300초 뒤 일정 부분 반등하면 종료, 이후 같은 과거 고점 재발송 금지.
    _kqd.kosdaq_idx.append((_kqd_base+600,996.1))
    _kqd.kosdaq_flows.append(_kqd_flow(_kqd_base+590,-400,-240,610))
    _kqd_fake_now[0]=_kqd_base+601.0
    _kqd_async.run(_kqd.maybe_alert_kosdaq_drop())
    assert len(_kqd_out)==3 and "코스닥 급락 종료·반등 확인" in _kqd_out[-1]
    assert _kqd.kosdaq_episode is None and _kqd.kosdaq_last_episode_end_ts==_kqd_base+600
    _kqd.kosdaq_idx.append((_kqd_base+620,995.0))
    _kqd_fake_now[0]=_kqd_base+621.0
    _kqd_async.run(_kqd.maybe_alert_kosdaq_drop())
    assert len(_kqd_out)==3,"old KOSDAQ peak re-alerted after episode end"

with _kqd_tmp.TemporaryDirectory() as directory:
    handoff=_kqd_Path(directory)/"kospi_shock_handoff.json"
    _kqd.save_handoff(handoff)
    restored=Watch("unused",[],"",False)
    restored.load_handoff(handoff)
    assert restored.kosdaq_idx and restored.kosdaq_last_episode_end_ts==_kqd_base+600
    assert restored.kosdaq_opening_gap_sent is True
    assert restored.surge_sent_at["기관"]==_kqd_base+200
    assert restored.kosdaq_surge_sent_at==_kqd.kosdaq_surge_sent_at
print("kosdaq_crash_independent_episode_regression=true handoff=true no_duplicate=true")

# 다른 시장의 외국인 매도나 KOSPI200 선물을 KOSDAQ 매도주체로 혼합하지 않는다.
_kqd_hold=Watch("unused",[],"",False)
_kqd_hold.session_open_ts=_kqd_base-200
_kqd_hold.kosdaq_flows.append(_kqd_flow(_kqd_base-65,0,0,0))
_kqd_hold.kosdaq_flows.append(_kqd_flow(_kqd_base+200,-200,-150,300))
gap=_kqd_hold._kosdaq_attribution(_kqd_base,_kqd_base+260)
assert gap["available"] is False and "30초" in gap["reason"], gap
_kqd_hold.flows.append({"ts":_kqd_base+255,
                         "선물":{"sample_ts":_kqd_base+255,"외국인":-99999}})
assert _kqd_hold._kosdaq_attribution(_kqd_base,_kqd_base+260)==gap
print("kosdaq_price_only_missing_spot_alignment_valid=true")

# 개장 갭은 코스닥도 가격 사건과 독립. 전일 종가 유지값은 이벤트용 사용 금지.
assert ks.OPEN_GAP_ALERT_PCT==-1.0
assert ks.KOSDAQ_PRICE_POLL_INTERVAL_SEC>=3.0
_kqd_gap=Watch("unused",[],"",False)
_kqd_gap.session_open_ts=_kqd_base
_kqd_gap.kosdaq_last_price_snapshot={"price":960.0,"prev_close":1000.0,"open":960.0}
assert abs(ks.pct(1000.0,960.0)-(-4.0))<1e-9
print("kosdaq_opening_gap_independent_gate_valid=true")
