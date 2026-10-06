#!/usr/bin/env python3
from pathlib import Path

p = Path("scripts/khs_nuclear_policy_watch.py")
s = p.read_text(encoding="utf-8")

s = s.replace("BWRX_US_STATE_MODEL_VERSION = 1", "BWRX_US_STATE_MODEL_VERSION = 2", 1)

old = '''    # 미국 BWRX-300은 2026-09 건설허가를 이미 알림한 기준선으로 고정하고,
    # 그 이후 실제 실행단계가 공식적으로 상승할 때만 새 알림을 만든다.
    seen["bwrx300_us_state_model_version"] = BWRX_US_STATE_MODEL_VERSION
    previous_bwrx = seen.get("bwrx300_us_state") or {}
    if not previous_bwrx:
        seen["bwrx300_us_state"] = {
            **BWRX_FIXED_BASELINE,
            "first_seen_kst": now.isoformat(timespec="seconds"),
        }
        previous_bwrx = seen["bwrx300_us_state"]
        print("bwrx300_us_baseline_restored=construction_permit_issued")

    bwrx_items = collect_bwrx_us_items(now)
    latest_bwrx = bwrx_items[0] if bwrx_items else None
    if latest_bwrx:
        prev_rank = int(previous_bwrx.get("rank") or BWRX_STAGE_RANK.get(str(previous_bwrx.get("stage") or ""), 0))
        new_rank = int(latest_bwrx.get("rank") or 0)
        if new_rank > prev_rank and bool(latest_bwrx.get("official")):
            latest_bwrx["trigger"] = "official_bwrx300_execution_stage_change"
            alerts.append(latest_bwrx)
            seen["bwrx300_us_state"] = {
                **latest_bwrx,
                "first_seen_kst": now.isoformat(timespec="seconds"),
            }
'''

new = '''    # 미국 BWRX-300은 단계 순서를 하나의 rank로 직렬화하지 않는다.
    # 실제 프로젝트에서는 자본승인·장주기 발주·운영허가 신청 등이 일부 겹치거나
    # 순서가 달라질 수 있으므로 각 공식 마일스톤을 독립적으로 1회씩 추적한다.
    seen["bwrx300_us_state_model_version"] = BWRX_US_STATE_MODEL_VERSION
    previous_bwrx = seen.get("bwrx300_us_state") or {}
    milestones = dict(seen.get("bwrx300_us_milestones") or {})
    if "construction_permit_issued" not in milestones:
        milestones["construction_permit_issued"] = {
            **BWRX_FIXED_BASELINE,
            "first_seen_kst": now.isoformat(timespec="seconds"),
        }
    if not previous_bwrx:
        previous_bwrx = dict(milestones["construction_permit_issued"])
        seen["bwrx300_us_state"] = previous_bwrx
        print("bwrx300_us_baseline_restored=construction_permit_issued")

    bwrx_items = collect_bwrx_us_items(now)
    latest_by_stage = {}
    for item in bwrx_items:
        if not bool(item.get("official")):
            continue
        stage = str(item.get("stage") or "")
        if not stage:
            continue
        current = latest_by_stage.get(stage)
        if current is None or str(item.get("published_utc") or "") > str(current.get("published_utc") or ""):
            latest_by_stage[stage] = item

    for stage, item in sorted(
        latest_by_stage.items(),
        key=lambda kv: (int(kv[1].get("rank") or 0), str(kv[1].get("published_utc") or "")),
    ):
        if stage in milestones:
            continue
        item = dict(item)
        item["trigger"] = "official_bwrx300_execution_milestone"
        alerts.append(item)
        milestones[stage] = {
            **item,
            "first_seen_kst": now.isoformat(timespec="seconds"),
        }
        current_rank = int((seen.get("bwrx300_us_state") or previous_bwrx).get("rank") or 0)
        if int(item.get("rank") or 0) >= current_rank:
            seen["bwrx300_us_state"] = dict(milestones[stage])
        print(f"bwrx300_us_new_official_milestone={stage}")

    seen["bwrx300_us_milestones"] = milestones
'''

if old not in s:
    raise SystemExit("BWRX linear-rank runtime block not found")
s = s.replace(old, new, 1)

test_anchor = '''    # 허가 '신청 검토' 문구는 허가 발급으로 오인하지 않는다.
    if _bwrx_stage("NRC reviews TVA Clinch River BWRX-300 construction permit application") is not None:
        raise RuntimeError("BWRX permit-application false-positive regression")
'''
if test_anchor not in s:
    raise SystemExit("BWRX self-test anchor missing")
s = s.replace(
    test_anchor,
    test_anchor + '''
    # 운영허가 신청은 착공 뒤에도 올 수 있으므로 순위 비교로 억제하면 안 된다.
    if BWRX_STAGE_RANK["operating_license_application"] >= BWRX_STAGE_RANK["construction_start"]:
        raise RuntimeError("BWRX milestone ordering test requires independent-state handling")
''',
    1,
)

p.write_text(s, encoding="utf-8")
print("BWRX-300 independent official milestone patch applied")
