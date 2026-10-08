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


# Regression: Telegram 일시 네트워크 장애는 재시도 후 같은 알림을 정상 전송한다.
import json as _json
import urllib.error as _urlerror
_orig_urlopen = ks.urllib.request.urlopen
_orig_sleep3 = ks.time.sleep
_env = __import__("os").environ
_old_env = {k: _env.get(k) for k in (
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID_PRIMARY", "TELEGRAM_CHAT_ID_FALLBACK",
    "EXPECTED_TELEGRAM_BOT_USERNAME",
)}
_url_calls = {"send": 0}
class _DummyURLResponse:
    def __init__(self, obj):
        self._payload = _json.dumps(obj).encode("utf-8")
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self): return self._payload

def _flaky_urlopen(req, timeout=0):
    url = req if isinstance(req, str) else req.full_url
    if "/getMe" in url:
        return _DummyURLResponse({"ok": True, "result": {"username": "khs887900887900008879_bot"}})
    if "/sendMessage" in url:
        _url_calls["send"] += 1
        if _url_calls["send"] < 3:
            raise _urlerror.URLError("synthetic telegram disconnect")
        return _DummyURLResponse({"ok": True, "result": {"message_id": 999}})
    raise AssertionError(url)

try:
    _env["TELEGRAM_BOT_TOKEN"] = "token"
    _env["TELEGRAM_CHAT_ID_PRIMARY"] = "chat"
    _env["EXPECTED_TELEGRAM_BOT_USERNAME"] = "khs887900887900008879_bot"
    ks.urllib.request.urlopen = _flaky_urlopen
    ks.time.sleep = lambda *_args, **_kwargs: None
    assert ks.telegram_send("test") == 999
    assert _url_calls["send"] == 3, _url_calls
finally:
    ks.urllib.request.urlopen = _orig_urlopen
    ks.time.sleep = _orig_sleep3
    for _k, _v in _old_env.items():
        if _v is None:
            _env.pop(_k, None)
        else:
            _env[_k] = _v
print("telegram_transport_retry_regression=true")


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
