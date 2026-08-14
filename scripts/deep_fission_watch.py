#!/usr/bin/env python3
"""Compatibility entrypoint for the semantic Deep Fission v3 watcher."""
from __future__ import annotations

import json
import pathlib
import shutil

import deep_fission_watch_v3 as v3

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "out"
OLD_STATE = DATA / "deep_fission_watch_state.json"
OLD_PENDING = OUT / "deep_fission_watch_state_pending.json"
OLD_ALERT = OUT / "deep_fission_alert.md"
OLD_STATUS = OUT / "deep_fission_status.md"
OLD_ERRORS = OUT / "deep_fission_errors.log"


def prepare_state() -> None:
    """Carry the semantic v3 state through filenames used by the existing workflow."""
    v3.STATE.unlink(missing_ok=True)
    if not OLD_STATE.exists():
        return
    try:
        state = json.loads(OLD_STATE.read_text(encoding="utf-8"))
    except Exception:
        return
    if state.get("version") == 3:
        v3.STATE.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(OLD_STATE, v3.STATE)


def publish_compat_artifacts() -> None:
    if v3.PENDING.exists():
        shutil.copyfile(v3.PENDING, OLD_PENDING)

    if v3.ALERT.exists() and v3.ALERT.read_text(encoding="utf-8").strip():
        text = v3.ALERT.read_text(encoding="utf-8")
        text = text.replace("- 링크:", "- 원문:")
        OLD_ALERT.write_text(text, encoding="utf-8")
    else:
        OLD_ALERT.unlink(missing_ok=True)

    if v3.STATUS.exists():
        shutil.copyfile(v3.STATUS, OLD_STATUS)
    if v3.ERRORS.exists():
        shutil.copyfile(v3.ERRORS, OLD_ERRORS)
    else:
        OLD_ERRORS.unlink(missing_ok=True)


def main() -> int:
    prepare_state()
    rc = v3.main()
    publish_compat_artifacts()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
