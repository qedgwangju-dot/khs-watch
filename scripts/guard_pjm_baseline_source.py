#!/usr/bin/env python3
from pathlib import Path

PATH = Path("scripts/pjm_data_center_policy_watch.py")

# Keep the existing PJM watcher, but make sure its live run also covers the
# FERC/PJM large-load consumer-protection track agreed for this alert family.
POLICY_PATCHES = (
    (
        'DOCKETS = ("ER26-3380", "ER26-3515")',
        'DOCKETS = ("ER26-3380", "ER26-3515", "EL26-67", "RM26-4")',
    ),
    (
        '    "capacity shortfall", "backstop procurement",\n)',
        '    "capacity shortfall", "backstop procurement",\n'
        '    "cost recovery agreement", "transmission security agreement",\n'
        '    "construction service agreement", "readiness requirement",\n'
        '    "site control", "financial security", "speculative load",\n'
        ')',
    ),
    (
        '    \'PJM data center large load FERC\',\n)',
        '    \'PJM data center large load FERC\',\n'
        '    \'PJM "EL26-67" large load\',\n'
        '    \'PJM "Cost Recovery Agreement" data center\',\n'
        '    \'PJM large load readiness "site control"\',\n'
        ')',
    ),
    (
        '    (PJM_RBP, "PJM RBP 공식 페이지"),\n):',
        '    (PJM_RBP, "PJM RBP 공식 페이지"),\n'
        '    (FERC_DECISIONS, "FERC 결정·명령"),\n'
        '):',
    ),
)

BASELINE_OLD = "baseline = parse_baseline()\nitems = []"
BASELINE_NEW = '''_saved_baseline = old.get("baseline", {})
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
for old, new in POLICY_PATCHES:
    if old not in text:
        raise SystemExit(f"PJM policy guard insertion point not found: {old[:80]}")
    text = text.replace(old, new, 1)

if BASELINE_OLD not in text:
    raise SystemExit("PJM baseline guard insertion point not found")
text = text.replace(BASELINE_OLD, BASELINE_NEW, 1)
PATH.write_text(text, encoding="utf-8")
print("PJM baseline + FERC large-load policy guard inserted")
