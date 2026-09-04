#!/usr/bin/env python3
"""Resolve Google News wrapper URLs to publisher links for SK hynix eSSD alerts.

The main watcher intentionally suppresses Google News RSS wrapper URLs. This
post-processor decodes those wrappers to the publisher's original article URL
and inserts a clickable ``원문`` link into the Telegram HTML only when a valid
non-Google direct URL is resolved.
"""

from __future__ import annotations

import argparse
import html
import json
import pathlib
import urllib.parse

from googlenewsdecoder import gnewsdecoder

ROOT = pathlib.Path(__file__).resolve().parents[1]
PENDING_PATH = ROOT / "out" / "skhynix_china_essd_reg_watch_pending_state.json"
ALERT_PATH = ROOT / "out" / "skhynix_china_essd_reg_watch_telegram.html"


def is_google_news(url: str) -> bool:
    try:
        host = (urllib.parse.urlparse((url or "").strip()).hostname or "").lower()
    except Exception:
        return False
    return host == "news.google.com" or host.endswith(".news.google.com")


def valid_direct_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse((url or "").strip())
        host = (parsed.hostname or "").lower()
    except Exception:
        return False
    return (
        parsed.scheme in {"http", "https"}
        and bool(host)
        and host != "news.google.com"
        and not host.endswith(".news.google.com")
    )


def resolve_direct_url(url: str) -> str:
    value = (url or "").strip()
    if not value:
        return ""
    if valid_direct_url(value):
        return value
    if not is_google_news(value):
        return ""
    try:
        result = gnewsdecoder(value, interval=0.5)
    except Exception as exc:
        print(f"direct_link_decode_error={type(exc).__name__}: {exc}")
        return ""
    if not isinstance(result, dict) or not result.get("status"):
        print(f"direct_link_decode_failed={result}")
        return ""
    decoded = str(result.get("decoded_url") or "").strip()
    if valid_direct_url(decoded):
        return decoded
    print(f"direct_link_invalid_decoded_url={decoded!r}")
    return ""


def inject_links(alert_text: str, events: list[dict]) -> tuple[str, int]:
    lines = alert_text.splitlines()
    inserted = 0

    # Alert order matches latest_high_signal order; Telegram output is capped at six events.
    for idx, event in enumerate(events[:6], 1):
        direct = resolve_direct_url(str(event.get("direct_link") or event.get("link") or ""))
        event["direct_link"] = direct or None
        if not direct:
            continue

        header_prefix = f"<b>{idx}. "
        start = next((i for i, line in enumerate(lines) if line.startswith(header_prefix)), None)
        if start is None:
            continue

        # Do not duplicate an existing source link.
        end = len(lines)
        for j in range(start + 1, len(lines)):
            if lines[j].startswith("<b>"):
                end = j
                break
        if any(">원문</a>" in line for line in lines[start:end]):
            continue

        meaning_idx = next(
            (j for j in range(start + 1, end) if lines[j].startswith("• 의미:")),
            None,
        )
        if meaning_idx is None:
            continue

        link_line = f'• <a href="{html.escape(direct, quote=True)}">원문</a>'
        lines.insert(meaning_idx + 1, link_line)
        inserted += 1

    return "\n".join(lines) + ("\n" if alert_text.endswith("\n") else ""), inserted


def process_alert() -> int:
    if not ALERT_PATH.exists() or not PENDING_PATH.exists():
        print("direct_link_fix_skipped=no_alert_or_pending_state")
        return 0

    pending = json.loads(PENDING_PATH.read_text(encoding="utf-8"))
    events = list(pending.get("latest_high_signal") or [])
    if not events:
        print("direct_link_fix_skipped=no_high_signal")
        return 0

    original = ALERT_PATH.read_text(encoding="utf-8")
    updated, inserted = inject_links(original, events)
    ALERT_PATH.write_text(updated, encoding="utf-8")
    PENDING_PATH.write_text(
        json.dumps(pending, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"direct_links_inserted={inserted}")
    return inserted


def probe_state(path: pathlib.Path) -> int:
    state = json.loads(path.read_text(encoding="utf-8"))
    events = list(state.get("latest_high_signal") or [])
    if not events:
        print("direct_link_probe=no_latest_high_signal")
        return 0
    url = str(events[0].get("link") or "")
    direct = resolve_direct_url(url)
    if not direct:
        raise RuntimeError("Could not resolve the latest Google News wrapper to a direct publisher URL")
    print(f"direct_link_probe=ok url={direct}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe-state", type=pathlib.Path)
    args = parser.parse_args()
    if args.probe_state:
        return probe_state(args.probe_state)
    process_alert()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
