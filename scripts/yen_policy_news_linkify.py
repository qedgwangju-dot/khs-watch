#!/usr/bin/env python3
"""Render clickable source links in yen-policy Telegram alerts."""

from __future__ import annotations

import datetime as dt
import html
import json
import pathlib
from zoneinfo import ZoneInfo

import yen_policy_news_alert as news

KST = ZoneInfo("Asia/Seoul")
ALERT_JSON_PATH = pathlib.Path("out/yen_policy_news_alert.json")
ALERT_BODY_PATH = pathlib.Path("out/yen_policy_news_alert.md")


def parse_published(value: str) -> dt.datetime | None:
    try:
        parsed = dt.datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=KST)
    return parsed.astimezone(dt.timezone.utc)


def source_links_for_item(alert_item: dict, current: dt.datetime) -> list[dict]:
    groups = [str(group) for group in (alert_item.get("corroborating_groups") or []) if group]
    primary_group = str(alert_item.get("source_group") or "").strip()
    primary_link = str(alert_item.get("link") or "").strip()
    if not groups and primary_group:
        groups = [primary_group]

    links: dict[str, str] = {}
    if primary_group and primary_link:
        links[primary_group] = primary_link

    topic = str(alert_item.get("topic") or "")
    published = parse_published(str(alert_item.get("published_at_kst") or ""))
    if topic and groups and published is not None:
        try:
            items, _errors = news.collect_items(current)
            classified = [result for item in items if (result := news.classify(item)) is not None]
            candidates = [
                result
                for result in classified
                if result.topic == topic
                and result.source_group in groups
                and abs((result.item.published - published).total_seconds()) <= 6 * 3600
            ]
            candidates.sort(key=lambda result: result.item.published, reverse=True)
            for result in candidates:
                links.setdefault(result.source_group, result.item.link)
        except Exception:
            # The primary article link is already stored in the alert JSON. A failed
            # refresh must not block the alert or remove that primary link.
            pass

    return [{"source_group": group, "link": links.get(group, "")} for group in groups]


def format_crosscheck_html(sources: list[dict]) -> str:
    parts: list[str] = []
    for source in sources:
        group = html.escape(str(source.get("source_group") or "미확인"), quote=False)
        link = str(source.get("link") or "").strip()
        if link:
            safe_link = html.escape(link, quote=True)
            parts.append(f'{group} · <a href="{safe_link}">원문</a>')
        else:
            parts.append(group)
    return "교차확인: " + " | ".join(parts)


def linkify(
    alert_json_path: pathlib.Path = ALERT_JSON_PATH,
    body_path: pathlib.Path = ALERT_BODY_PATH,
    current: dt.datetime | None = None,
) -> bool:
    if not alert_json_path.exists() or not body_path.exists():
        return False

    current = (current or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    payload = json.loads(alert_json_path.read_text(encoding="utf-8"))
    alert_items = list(payload.get("items") or [])
    source_sets = [source_links_for_item(item, current) for item in alert_items]

    raw_lines = body_path.read_text(encoding="utf-8").splitlines()
    rendered: list[str] = []
    cross_index = 0
    for line in raw_lines:
        if line.startswith("교차확인:") and cross_index < len(source_sets):
            rendered.append(format_crosscheck_html(source_sets[cross_index]))
            cross_index += 1
        else:
            rendered.append(html.escape(line, quote=False))

    for item, sources in zip(alert_items, source_sets):
        item["corroborating_sources"] = sources
    payload["telegram_parse_mode"] = "HTML"

    body_path.write_text("\n".join(rendered).rstrip() + "\n", encoding="utf-8")
    alert_json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return True


def main() -> int:
    changed = linkify()
    print(json.dumps({"linkified": changed}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
