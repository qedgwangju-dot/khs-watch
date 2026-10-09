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

    # Regression: a blocked Treasury original may be recovered only from the
    # Treasury-owned USTREAS bulletin with exact case facts; no third-party text.
    original_direct = source_fetch._fetch_direct
    original_race = source_fetch._fetch_proxy_direct_race
    old_proxy = os.environ.get("KHS_SOURCE_PROXY_URL")
    old_proxy_first = os.environ.get("KHS_SOURCE_PROXY_FIRST")
    official_html = (
        "<html>U.S. Department of the Treasury "
        "Treasury Announces Enforcement Penalty for Violation of Outbound Program "
        "October 7, 2026. The Outbound Investment Security Program (OISP) "
        "penalized Amidi LLC $200,000 for an investment of $92,478 in Noematrix."
        "</html>"
    )
    original_url = "https://home.treasury.gov/news/press-releases/sb0652"
    bulletin_url = "https://content.govdelivery.com/accounts/USTREAS/bulletins/42e501d"
    try:
        os.environ["KHS_SOURCE_PROXY_URL"] = "https://proxy.example/fetch"
        os.environ["KHS_SOURCE_PROXY_FIRST"] = "true"
        source_fetch._fetch_proxy_direct_race = lambda *_args, **_kwargs: (
            None, "simulated 403 and timeout"
        )

        def bulletin_direct(url, *_args, **_kwargs):
            if url == bulletin_url:
                return official_html, None
            return None, "simulated 403"

        source_fetch._fetch_direct = bulletin_direct
        recovered, error = source_fetch.fetch_text(original_url, "test-agent", timeout=1, attempts=1)
        assert recovered == official_html and error is None, (recovered, error)
        unrelated, other_error = source_fetch.fetch_text(
            "https://home.treasury.gov/news/press-releases/sb9999",
            "test-agent", timeout=1, attempts=1
        )
        assert unrelated is None and "simulated" in (other_error or "")
        source_fetch._fetch_direct = lambda *_args, **_kwargs: (
            official_html.replace("92,478", "92,000"), None
        )
        rejected, rejection = source_fetch.fetch_text(original_url, "test-agent", timeout=1, attempts=1)
        assert rejected is None and "required case facts missing" in (rejection or "")
    finally:
        source_fetch._fetch_direct = original_direct
        source_fetch._fetch_proxy_direct_race = original_race
        for name, value in (
            ("KHS_SOURCE_PROXY_URL", old_proxy),
            ("KHS_SOURCE_PROXY_FIRST", old_proxy_first),
        ):
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    print("khs_source_fetch_contract=passed treasury_official_backup=passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
