#!/usr/bin/env python3
"""Expose partial source coverage without dropping independently verified alerts."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLARITY_NOTICE = (
    "⚠️ <b>공식 출처 일부 미확인</b>\n"
    "일부 공식 출처 조회가 실패했습니다. 앞서 안내한 변화만 확인했으며, "
    "전체 출처에 다른 새 변화가 없다는 뜻은 아닙니다."
)


def read_state(path):
    state = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        raise ValueError("Source health artifact must be an object")
    return state


def validate_clarity_pending(state):
    if state.get("initialized") is not True or type(state.get("source_version")) is not int:
        raise ValueError("CLARITY pending baseline is invalid")
    keys = state.get("seen_event_keys")
    errors = state.get("source_errors")
    if not isinstance(keys, list) or any(not isinstance(key, str) for key in keys):
        raise ValueError("CLARITY pending dedupe checkpoint is invalid")
    if not isinstance(errors, list) or any(not isinstance(error, str) for error in errors):
        raise ValueError("CLARITY pending source errors are invalid")
    if type(state.get("collection_complete")) is not bool or state["collection_complete"] != (not errors):
        raise ValueError("CLARITY pending completeness is invalid or contradictory")


def append_clarity_notice(out):
    chunks_path = out / "clarity_watch_telegram_chunks.json"
    if not chunks_path.exists():
        return False  # Never create a Telegram message just for source failure.
    state = read_state(out / "clarity_watch_pending_state.json")
    validate_clarity_pending(state)
    if state.get("collection_complete") is True:
        return False
    chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    if not isinstance(chunks, list) or not chunks or any(not isinstance(c, str) or not c for c in chunks):
        raise ValueError("CLARITY chunks must be a nonempty string list")
    if CLARITY_NOTICE not in chunks:
        chunks.append(CLARITY_NOTICE)  # Separate chunk preserves the existing size bounds.
        chunks_path.write_text(json.dumps(chunks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        preview = out / "clarity_watch_alert.html"
        if preview.exists():
            preview.write_text(preview.read_text(encoding="utf-8") + "\n\n" + CLARITY_NOTICE, encoding="utf-8")
    return True


def require_complete(out, lane):
    filename, field = {
        "clarity": ("clarity_watch_pending_state.json", "collection_complete"),
        "maplight": ("optogenetics_translation_watch_pending_state.json", "maplight_health_ok"),
    }[lane]
    state = read_state(out / filename)
    if lane == "clarity":
        validate_clarity_pending(state)
    if state.get(field) is not True:
        raise RuntimeError(f"{lane} source coverage incomplete; inspect source error artifacts")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("clarity-notice", "clarity-check", "maplight-check"))
    args = parser.parse_args()
    out = ROOT / "out"
    if args.action == "clarity-notice":
        append_clarity_notice(out)
    else:
        require_complete(out, args.action.split("-")[0])


if __name__ == "__main__":
    main()
