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
        "penalized Amidi LLC $200,000 for an investment of $92,478 in Noematrix, China robotics AI."
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
        # Even HTTP 200 is not an authentic release if it is a challenge page.
        source_fetch._fetch_proxy_direct_race = lambda *_args, **_kwargs: (
            "<html>Access Denied</html>", None
        )
        challenge_recovery, challenge_error = source_fetch.fetch_text(
            original_url, "test-agent", timeout=1, attempts=1
        )
        assert challenge_recovery == official_html and challenge_error is None
        source_fetch._fetch_proxy_direct_race = lambda *_args, **_kwargs: (
            None, "simulated 403 and timeout"
        )
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

    # Render-to-Telegram contract: the recovered OISP case must survive the
    # shared formatter and one-link validator, not merely pass source parsing.
    import datetime as dt
    import khs_policy_runtime_patch as runtime_patch
    runtime_patch.main()  # Same official parser patch run by the watch job.
    import khs_trusted_policy_news_watch as trusted
    from khs_policy_telegram_formatter import (
        format_policy_message, validate_final_policy_message,
        prepare_telegram_messages,
    )
    oisp_rule = next(
        rule for rule in trusted.STORY_RULES
        if rule.key == "us_treasury_outbound_ai_robotics_enforcement"
    )
    official_item = {
        "title": "Treasury Announces Enforcement Penalty for Violation of Outbound Program",
        "description": (
            "U.S. Treasury issued its first penalty under the Outbound Investment Security Program "
            "after Amidi LLC failed to notify Treasury of its $92,478 investment in "
            "Chinese robotics AI firm Noematrix and was fined $200,000."
        ),
        "link": original_url,
        "source": "U.S. Department of the Treasury",
        "published_kst": "2026-10-07T12:00:00+09:00",
        "official_direct_verified": True,
        "priority": 0,
    }
    assert trusted.alert_confirmation_status(oisp_rule, [official_item])[0] == "공식 확인"
    # Exercise the *real* official-direct parser and its date/stage fallback
    # before testing the message formatter; mocked RSS feeds stay empty.
    from unittest.mock import patch
    def policy_feed(url, *args, **kwargs):
        if url == original_url:
            return official_html
        return "<rss><channel></channel></rss>"
    with patch.object(trusted, "fetch_text", policy_feed):
        collected = trusted.collect_rule_items(
            oisp_rule, dt.datetime(2026, 10, 10, 7, 25, tzinfo=trusted.KST)
        )
    assert len(collected) == 1, f"verified Treasury source not collected: {collected}"
    assert collected[0].get("official_direct_verified") is True
    assert trusted.semantic_policy_event_key(collected[0]) == (
        "us-treasury-oisp-amidi-noematrix-notification-penalty-2026-10-07"
    )
    report = trusted.render_alert_bundle(
        [{"rule": oisp_rule, "items": [official_item]}],
        dt.datetime(2026, 10, 10, 7, 25, tzinfo=trusted.KST),
    )
    title = "신뢰외신 정책 워치: [상·공식 확인] 미 재무부, 중국 로봇·체화형 AI 투자 미신고 첫 과징금"
    title, report = format_policy_message(title, report)
    errors = validate_final_policy_message(title, report)
    assert not errors, f"rendered Treasury policy alert blocked by quality guard: {errors}"
    assert prepare_telegram_messages(title, report), "no Telegram message parts created"

    print("khs_source_fetch_contract=passed treasury_official_backup=passed treasury_message_format=passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
