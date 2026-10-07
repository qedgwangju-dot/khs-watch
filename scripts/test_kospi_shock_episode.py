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
with tempfile.TemporaryDirectory() as td:
    hp = Path(td) / "handoff.json"
    w6.save_handoff(hp)
    w7 = Watch("dummy", [], "dummy", True)
    w7.load_handoff(hp)
    assert len(w7.flows) == 1, len(w7.flows)
    assert w7.episode and w7.episode["start_price"] == 7000.0, w7.episode
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
