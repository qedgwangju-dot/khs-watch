#!/usr/bin/env python3
"""Shared source fetching helpers for KHS policy-watch lanes."""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import queue
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path


OUT_DIR = Path("out")
FAILURES_PATH = OUT_DIR / "khs_source_failures.json"
DEFAULT_ACCEPT = "text/html,application/xhtml+xml,*/*"
TRUE_VALUES = {"1", "true", "yes", "y", "on"}


def fetch_text(
    url: str,
    user_agent: str,
    *,
    timeout: int = 20,
    attempts: int = 2,
    accept: str = DEFAULT_ACCEPT,
) -> tuple[str | None, str | None]:
    errors: list[str] = []
    proxy_base = os.getenv("KHS_SOURCE_PROXY_URL", "").strip()
    proxy_first = os.getenv("KHS_SOURCE_PROXY_FIRST", "").strip().lower() in TRUE_VALUES
    proxy_timeout = _env_int("KHS_SOURCE_PROXY_TIMEOUT_SECONDS", 12)
    direct_fallback_cap = _env_int("KHS_SOURCE_DIRECT_TIMEOUT_CAP_SECONDS", 8)

    if proxy_base and proxy_first:
        return _fetch_proxy_direct_race(
            proxy_base,
            url,
            user_agent,
            accept,
            proxy_timeout=proxy_timeout,
            direct_timeout=min(timeout, direct_fallback_cap),
        )

    for attempt in range(1, attempts + 1):
        current_timeout = timeout if attempt == 1 else min(max(timeout * 2, timeout + 10), 45)
        if proxy_first and proxy_base:
            current_timeout = min(current_timeout, direct_fallback_cap)
        text, error = _fetch_direct(url, user_agent, accept, current_timeout)
        if error is None:
            return text, None
        errors.append(f"direct attempt={attempt}/{attempts} timeout={current_timeout}s {error}")
        if attempt < attempts:
            time.sleep(1.5 * attempt)

    if proxy_base and not proxy_first:
        proxy_text, proxy_error = _fetch_proxy(proxy_base, url, user_agent, accept, proxy_timeout)
        if proxy_error is None:
            return proxy_text, None
        errors.append(f"proxy timeout={proxy_timeout}s {proxy_error}")
    else:
        if not proxy_base:
            errors.append("proxy not configured")

    return None, " | ".join(errors)


def record_source_failure(
    *,
    lane: str,
    source_name: str,
    source_url: str,
    error: str,
    checked_at: dt.datetime,
) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    failures = _load_failures()
    key = f"{lane}|{source_name}|{source_url}"
    failures = [item for item in failures if item.get("key") != key]
    failures.append(
        {
            "key": key,
            "lane": lane,
            "source": source_name,
            "url": source_url,
            "error": html.unescape(str(error))[:900],
            "checked_at_kst": checked_at.isoformat(timespec="seconds"),
            "proxy_configured": bool(os.getenv("KHS_SOURCE_PROXY_URL", "").strip()),
        }
    )
    FAILURES_PATH.write_text(json.dumps(failures, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _fetch_direct(url: str, user_agent: str, accept: str, timeout: int) -> tuple[str | None, str | None]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": user_agent, "Accept": accept},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace"), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _fetch_proxy(
    proxy_base: str,
    target_url: str,
    user_agent: str,
    accept: str,
    timeout: int,
) -> tuple[str | None, str | None]:
    proxy_url = _build_proxy_url(proxy_base, target_url)
    return _fetch_direct(proxy_url, user_agent, accept, timeout)


def _fetch_proxy_direct_race(
    proxy_base: str,
    target_url: str,
    user_agent: str,
    accept: str,
    *,
    proxy_timeout: int,
    direct_timeout: int,
) -> tuple[str | None, str | None]:
    """Return the first successful route without serially paying both timeouts."""

    results: queue.Queue[tuple[str, int, str | None, str | None]] = queue.Queue()

    def run_route(label: str, route_timeout: int) -> None:
        if label == "proxy":
            text, error = _fetch_proxy(proxy_base, target_url, user_agent, accept, route_timeout)
        else:
            text, error = _fetch_direct(target_url, user_agent, accept, route_timeout)
        results.put((label, route_timeout, text, error))

    for label, route_timeout in (("proxy", proxy_timeout), ("direct", direct_timeout)):
        threading.Thread(target=run_route, args=(label, route_timeout), daemon=True).start()

    deadline = time.monotonic() + max(proxy_timeout, direct_timeout) + 1
    errors: list[str] = []
    for _ in range(2):
        remaining = max(0.01, deadline - time.monotonic())
        try:
            label, route_timeout, text, error = results.get(timeout=remaining)
        except queue.Empty:
            errors.append(f"route race exceeded {max(proxy_timeout, direct_timeout)}s")
            break
        if error is None:
            return text, None
        errors.append(f"{label} race timeout={route_timeout}s {error}")

    return None, " | ".join(errors)


def _build_proxy_url(proxy_base: str, target_url: str) -> str:
    sep = "&" if "?" in proxy_base else "?"
    return f"{proxy_base}{sep}url={urllib.parse.quote(target_url, safe='')}"


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return max(1, value)


def _load_failures() -> list[dict]:
    if not FAILURES_PATH.exists():
        return []
    try:
        data = json.loads(FAILURES_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []
