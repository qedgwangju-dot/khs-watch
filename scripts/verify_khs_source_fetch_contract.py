#!/usr/bin/env python3
"""Verify proxy-first source fetches race routes instead of waiting serially."""

from __future__ import annotations

import os
import time

import khs_source_fetch as source_fetch


def main() -> int:
    original_direct = source_fetch._fetch_direct
    original_proxy = source_fetch._fetch_proxy
    previous_proxy = os.environ.get("KHS_SOURCE_PROXY_URL")
    previous_proxy_first = os.environ.get("KHS_SOURCE_PROXY_FIRST")
    previous_proxy_timeout = os.environ.get("KHS_SOURCE_PROXY_TIMEOUT_SECONDS")
    previous_direct_cap = os.environ.get("KHS_SOURCE_DIRECT_TIMEOUT_CAP_SECONDS")
    try:
        os.environ["KHS_SOURCE_PROXY_URL"] = "https://proxy.example/fetch"
        os.environ["KHS_SOURCE_PROXY_FIRST"] = "true"
        os.environ["KHS_SOURCE_PROXY_TIMEOUT_SECONDS"] = "2"
        os.environ["KHS_SOURCE_DIRECT_TIMEOUT_CAP_SECONDS"] = "1"

        def slow_proxy(*_args, **_kwargs):
            time.sleep(0.35)
            return None, "TimeoutError: proxy stalled"

        def fast_direct(*_args, **_kwargs):
            time.sleep(0.03)
            return "official-source-body", None

        source_fetch._fetch_proxy = slow_proxy
        source_fetch._fetch_direct = fast_direct
        started = time.monotonic()
        text, error = source_fetch.fetch_text("https://www.korea.kr/news", "test-agent", timeout=1, attempts=1)
        elapsed = time.monotonic() - started
        if text != "official-source-body" or error is not None:
            raise AssertionError((text, error))
        if elapsed >= 0.2:
            raise AssertionError(f"proxy/direct routes were not raced: elapsed={elapsed:.3f}s")
    finally:
        source_fetch._fetch_direct = original_direct
        source_fetch._fetch_proxy = original_proxy
        for name, value in (
            ("KHS_SOURCE_PROXY_URL", previous_proxy),
            ("KHS_SOURCE_PROXY_FIRST", previous_proxy_first),
            ("KHS_SOURCE_PROXY_TIMEOUT_SECONDS", previous_proxy_timeout),
            ("KHS_SOURCE_DIRECT_TIMEOUT_CAP_SECONDS", previous_direct_cap),
        ):
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    print("khs_source_fetch_contract=passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
