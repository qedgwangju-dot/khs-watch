#!/usr/bin/env python3
import time
from collections import deque
from kospi_shock_episode_watch import Watch, fmt_clock

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
assert "KOSPI realtime feed stale >75s" in src
assert "KOSPI200 futures feed stale >90s" in src
assert "flow snapshot stale >120s" in src
print("feed_health_regression=true")
