#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import hormuz_maritime_watch as mod


def check(name, cond):
    if not cond:
        raise AssertionError(name)
    print(f"PASS {name}")


def row(source, *, origin=None, count=1, details=(), authority=True, t=1000.0):
    return {
        "source": source,
        "origin_source": origin or source,
        "event_kind": "strike",
        "location": "hormuz",
        "projectile_count": count,
        "incident_details": list(details),
        "mentions_authority": authority,
        "published_epoch": t,
        "published_utc": "2026-10-02T16:00:00Z",
        "warning": None,
        "title": "Tanker struck by unknown projectile in Strait of Hormuz",
        "description": "",
        "url": "https://example.com/" + source.replace(" ", "-"),
        "resolved_url": "https://example.com/" + source.replace(" ", "-"),
    }


# 1) 동일 사건 세부정보가 맞는 AP + Anadolu는 교차검증 가능.
a = row(
    "Arab News",
    origin="Associated Press",
    details=("outbound", "fire", "blackout", "crew_safe", "no_env", "time:1122"),
    t=1000.0,
)
b = row(
    "Anadolu Ajansı",
    details=("outbound", "fire", "blackout", "crew_safe", "no_env", "time:1122"),
    t=1100.0,
)
check("strict-compatible-same-event", mod.strict_compatible(a, b))
check("strict-source-independent", mod.strict_source_confidence([a, b]))
clusters = mod.strict_clusters([a, b])
check("strict-cluster-created", len(clusters) == 1)
check("projectile-count-two-origin-support", clusters[0]["projectile_count"] == 1)
check("projectile-count-support-number", clusters[0]["projectile_count_sources"] == 2)

# 2) 수량이 한 출처에서만 확인되면 '1발' 확정 표기를 금지.
b_no_count = dict(b)
b_no_count["projectile_count"] = None
clusters = mod.strict_clusters([a, b_no_count])
check("single-source-count-not-promoted", len(clusters) == 1 and clusters[0]["projectile_count"] is None)

# 3) 같은 해협·같은 시간대라도 사건 세부앵커가 없으면 별개 사건일 수 있으므로 묶지 않는다.
c = row("Reuters", details=(), t=1000.0)
d = row("Anadolu Ajansı", details=(), t=1100.0)
check("generic-hormuz-strikes-not-compatible", not mod.strict_compatible(c, d))
check("generic-hormuz-strikes-no-cluster", mod.strict_clusters([c, d]) == [])

# 4) 서로 다른 매체에 실렸어도 원출처가 같은 AP 재전재면 독립 2곳으로 세지 않는다.
e = row("Arab News", origin="Associated Press", details=("fire", "crew_safe"), t=1000.0)
f = row("Another Outlet", origin="Associated Press", details=("fire", "crew_safe"), t=1100.0)
check("same-wire-not-independent", not mod.strict_source_confidence([e, f]))

# 5) 세부사건 시간이 다르면 같은 사건으로 묶지 않는다.
g = row("Reuters", details=("time:1122", "fire"), t=1000.0)
h = row("Anadolu Ajansı", details=("time:1430", "fire"), t=1100.0)
check("different-incident-time-split", not mod.strict_compatible(g, h))

# 6) 미상 발사체는 무기종류로 승격하지 않는다.
check("unknown-projectile-singular-count", mod.watcher.projectile_count("tanker struck by an unknown projectile") == 1)
alert = mod.readable_cluster_alert_v5(mod.strict_clusters([a, b])[0])
check("alert-keeps-unknown-weapon-rule", "미상 발사체" in alert and "공격주체·미사일·포탄·드론은 공식 확인 전 단정하지 않습니다" in alert)

print("HORMUZ_MARITIME_REGRESSION_OK")
