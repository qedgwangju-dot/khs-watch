#!/usr/bin/env python3
from pathlib import Path

PATH = Path("scripts/pjm_data_center_policy_watch.py")

OLD = "baseline = parse_baseline()\nitems = []"
NEW = '''baseline = parse_baseline()
_saved_baseline = old.get("baseline", {})
_verified_fallback = {
    "target_mw": 6831,
    "max_price_usd_mw_day": 555.0,
    "max_years": 15,
    "planned_start": "2026-09-30",
}
for _k in ("target_mw", "max_price_usd_mw_day", "max_years", "planned_start"):
    if baseline.get(_k) is None:
        baseline[_k] = _saved_baseline.get(_k)
    if baseline.get(_k) is None:
        baseline[_k] = _verified_fallback[_k]
items = []'''

text = PATH.read_text(encoding="utf-8")
if OLD not in text:
    raise SystemExit("PJM baseline guard insertion point not found")
PATH.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
print("PJM baseline guard inserted")
