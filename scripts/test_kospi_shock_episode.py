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
