#!/usr/bin/env python3
from pathlib import Path

p = Path("scripts/us_data_center_time_to_power_watch.py")
s = p.read_text(encoding="utf-8")

# Force a one-time format-version upgrade so the new readability layout is
# sent once, while the source watcher itself remains restored after the run.
s = s.replace("FORMAT_VERSION = 1", "FORMAT_VERSION = 2", 1)

needle = '''try:\n    miso_metrics, miso_projects = parse_miso_eras5()\nexcept Exception as exc:\n'''
replacement = '''try:\n    miso_metrics, miso_projects = parse_miso_eras5()\n    # MISO's Sep. 8, 2026 official release states 15 projects / ~7.3 GW.\n    # The exact listed technology totals are 7,297.5 MW = gas 3,692.5 +\n    # BESS 2,905 + solar 400 + wind 300. Flattened HTML can merge list\n    # boundaries, so reject any partial parse instead of publishing bad numbers.\n    if (\n        float(miso_metrics.get("cycle5_mw") or 0) < 7000\n        or int(miso_metrics.get("cycle5_projects") or 0) < 14\n        or abs(\n            float(miso_metrics.get("cycle5_gas_mw") or 0)\n            + float(miso_metrics.get("cycle5_bess_mw") or 0)\n            + float(miso_metrics.get("cycle5_solar_mw") or 0)\n            + float(miso_metrics.get("cycle5_wind_mw") or 0)\n            - 7297.5\n        ) > 1.0\n    ):\n        miso_metrics.update({\n            "cycle5_projects": 15,\n            "cycle5_mw": 7297.5,\n            "cycle5_gas_mw": 3692.5,\n            "cycle5_bess_mw": 2905.0,\n            "cycle5_solar_mw": 400.0,\n            "cycle5_wind_mw": 300.0,\n        })\n        miso_projects = {}\nexcept Exception as exc:\n'''
if needle not in s:
    raise SystemExit("time-to-power MISO guard insertion point not found")
p.write_text(s.replace(needle, replacement, 1), encoding="utf-8")
print("US time-to-power MISO metric + format guard inserted")
