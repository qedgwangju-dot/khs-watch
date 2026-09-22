#!/usr/bin/env python3
from kospi_flow_attribution_ls import classify_attribution

def block(delta=None, stale=False, base=True):
    return {
        "stale": stale,
        "base_time": "145000" if base else None,
        "delta": delta or {},
        "current": {},
    }

# 1) 현물 없이 KOSPI200+선물에서 기관이 팔아도 '기관 주도'로 확정하면 안 된다.
d1 = {
    "kospi": block(stale=True, base=False),
    "kp200": block({"외국인": 23, "기관계": -316, "개인": -283}),
    "futures": block({"외국인": 1608, "기관계": -1711, "개인": 2}),
    "program": block(stale=True, base=False),
}
r1 = classify_attribution(d1)
assert r1["confidence"] == "낮음", r1
assert "현물·선물 핵심축" in r1["verdict"], r1
assert "기관계 매도가 2개 이상 시장" not in r1["verdict"], r1

# 2) 현물과 선물 최다 매도자가 다르면 단일 주도자 보류.
d2 = {
    "kospi": block({"외국인": -944, "기관계": 321, "개인": -378}),
    "kp200": block({"외국인": 0, "기관계": 0, "개인": 0}),
    "futures": block({"외국인": 822, "기관계": -859, "개인": -254}),
    "program": block({"전체": 20, "차익": 10, "비차익": 10}),
}
r2 = classify_attribution(d2)
assert r2["spot_leader"]["actor"] == "외국인", r2
assert r2["futures_leader"]["actor"] == "기관계", r2
assert "주체 분산" in r2["verdict"], r2

# 3) 현물·선물 모두 외국인이 최다 매도 + 프로그램 매도면 높은 확신도.
d3 = {
    "kospi": block({"외국인": -1000, "기관계": 100, "개인": -200}),
    "kp200": block({"외국인": -500, "기관계": 50, "개인": 10}),
    "futures": block({"외국인": -1800, "기관계": 300, "개인": 100}),
    "program": block({"전체": -900, "차익": -200, "비차익": -700}),
}
r3 = classify_attribution(d3)
assert r3["confidence"] == "높음", r3
assert "외국인" in r3["verdict"] and "프로그램 매도" in r3["verdict"], r3

print("strict_attribution_regression=true")
