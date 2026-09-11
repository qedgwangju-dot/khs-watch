"""Runtime-only customization for the policy Telegram delivery step.

Python imports usercustomize automatically when user-site customization is enabled.
This patch is deliberately inactive unless the policy Telegram send step exports
its delivery environment variables, so repository validation and watch logic are
left unchanged.
"""

from __future__ import annotations

import os


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
        return restructure_nuclear_message(new_title, new_body)

    wrapped_format_policy_message._khs_nuclear_readability_wrapped = True
    formatter.format_policy_message = wrapped_format_policy_message
    print("policy_nuclear_readability_patch=installed")


_install_policy_telegram_readability_patch()
