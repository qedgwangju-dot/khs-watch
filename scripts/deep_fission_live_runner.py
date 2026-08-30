#!/usr/bin/env python3
"""Live guard runner for the Deep Fission semantic watcher.

This runner keeps the v3 watcher/state format but adds two runtime guards:
1) Parsons non-nuclear demo completion cannot be true before both the target
   PoC depth is reached and the prototype is deployed underground.
2) Old 18.5 GW customer-pipeline boilerplate repeated in unrelated releases
   is not treated as a fresh customer event.
"""
from __future__ import annotations

import json

import deep_fission_watch_v3 as v3

FALSE_EVENT_IDS = {"customer-pipeline:2026-08-25"}


def repair_persisted_state() -> None:
    state = v3.load_state()
    if not state:
        return

    changed = False
    parsons = dict(state.get("parsons") or {})
    if parsons.get("non_nuclear_demo_complete") and (
        not parsons.get("poc_depth_reached")
        or not parsons.get("prototype_underground_deployed")
    ):
        parsons["non_nuclear_demo_complete"] = False
        state["parsons"] = parsons
        changed = True

    sent = list(state.get("sent_event_ids") or [])
    cleaned = [eid for eid in sent if eid not in FALSE_EVENT_IDS]
    if cleaned != sent:
        state["sent_event_ids"] = cleaned
        changed = True

    if changed:
        v3.STATE.write_text(
            json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )


def install_parsons_guard() -> None:
    original = v3.extract_parsons_state

    def guarded(text: str) -> dict[str, bool]:
        state = original(text)
        if not state.get("poc_depth_reached") or not state.get("prototype_underground_deployed"):
            state["non_nuclear_demo_complete"] = False
        return state

    v3.extract_parsons_state = guarded


def install_press_guard() -> None:
    original = v3.classify_press
    baseline = v3.load_state()
    prior_press = baseline.get("press_urls") or {}
    had_185_pipeline = any(
        "18.5" in v3.norm(str(title)) and "customer pipeline" in v3.norm(str(title))
        for title in prior_press.values()
    )

    def guarded(title: str, text: str, url: str):
        events = original(title, text, url)
        title_low = v3.norm(title)
        body_low = v3.norm(text)

        pipeline_title_signal = any(
            token in title_low
            for token in [
                "customer pipeline",
                "customer",
                "power site",
                "letter of intent",
                "loi",
                "gigawatt",
            ]
        )
        if not pipeline_title_signal:
            events = [item for item in events if not item[0].startswith("customer-pipeline:")]

        if had_185_pipeline and "18.5" in body_low:
            events = [item for item in events if not item[0].startswith("customer-pipeline:")]

        return events

    v3.classify_press = guarded


def main() -> int:
    repair_persisted_state()
    install_parsons_guard()
    install_press_guard()
    return v3.main()


if __name__ == "__main__":
    raise SystemExit(main())
