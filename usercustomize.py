"""Runtime-only customization for the policy Telegram delivery step.

Python imports usercustomize automatically when user-site customization is enabled.
This patch is deliberately inactive unless the policy Telegram send step exports
its delivery environment variables, so repository validation and watch logic are
left unchanged.
"""

from __future__ import annotations

import os


WESTINGHOUSE_DISCLAIMER = "투자 조언이 아닌 참고용 원전·Westinghouse 정책 알림입니다."


def _clean_prestructured_westinghouse_body(body: str) -> str:
    """Keep the watcher's intentional section order; only remove legacy boilerplate."""
    lines = [line for line in str(body or "").splitlines() if line.strip() != WESTINGHOUSE_DISCLAIMER]
    return "\n".join(lines).strip() + "\n"


def _install_policy_telegram_readability_patch() -> None:
    delivery_step = any(
        bool(os.getenv(name))
        for name in ("POLICY_TELEGRAM_BOT_TOKEN", "KHS_POLICY_TELEGRAM_BOT_TOKEN")
    ) or os.getenv("TELEGRAM_DRY_RUN", "").lower() == "true"
    if not delivery_step:
        return

    try:
        from scripts import khs_policy_telegram_formatter as formatter
        from scripts.khs_nuclear_alert_readability import restructure_nuclear_message
    except Exception as exc:
        print(f"policy_nuclear_readability_patch=failed error={type(exc).__name__}:{exc}")
        return

    original = formatter.format_policy_message
    if getattr(original, "_khs_nuclear_readability_wrapped", False):
        return

    def wrapped_format_policy_message(title, body, *, rates=None, now=None):
        new_title, new_body = original(title, body, rates=rates, now=now)

        # Westinghouse watch output is already decision-first and sectioned by its
        # source watcher. Re-bucketing it here caused headings and their content to
        # be separated (e.g. 숫자/기업·매출 연결/세부), so preserve that order.
        if "원전·Westinghouse 웹감시" in new_title or "[원전·Westinghouse 웹감시]" in new_body:
            return new_title, _clean_prestructured_westinghouse_body(new_body)

        return restructure_nuclear_message(new_title, new_body)

    wrapped_format_policy_message._khs_nuclear_readability_wrapped = True
    formatter.format_policy_message = wrapped_format_policy_message
    print("policy_nuclear_readability_patch=installed")


_install_policy_telegram_readability_patch()
