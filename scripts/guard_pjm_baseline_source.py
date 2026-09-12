#!/usr/bin/env python3
from pathlib import Path

PATH = Path("scripts/pjm_data_center_policy_watch.py")

OLD = "baseline = parse_baseline()\nitems = []"
NEW = '''_saved_baseline = old.get("baseline", {})
_required_baseline_keys = (
    "target_mw",
    "max_price_usd_mw_day",
    "max_years",
    "planned_start",
)
try:
    baseline = parse_baseline()
except requests.RequestException as _exc:
    if not all(_saved_baseline.get(_k) is not None for _k in _required_baseline_keys):
        raise
    baseline = dict(_saved_baseline)
    print(
        "PJM baseline source temporarily unavailable; "
        f"keeping last verified official baseline ({type(_exc).__name__})"
    )
for _k in _required_baseline_keys:
    if baseline.get(_k) is None and _saved_baseline.get(_k) is not None:
        baseline[_k] = _saved_baseline[_k]
items = []'''

text = PATH.read_text(encoding="utf-8")
if OLD not in text:
    raise SystemExit("PJM baseline guard insertion point not found")
PATH.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
print("PJM baseline guard inserted")
