"""Scoped runtime hooks for KHS scripts.

Policy Telegram runtime patches are activated only inside the final Telegram
delivery process. Other script executions keep their existing behavior.
"""

from __future__ import annotations

import os


_policy_bot_token = (
    os.getenv("POLICY_TELEGRAM_BOT_TOKEN")
    or os.getenv("KHS_POLICY_TELEGRAM_BOT_TOKEN")
    or ""
).strip()
_policy_chat_id = (
    os.getenv("POLICY_TELEGRAM_CHAT_ID")
    or os.getenv("KHS_POLICY_TELEGRAM_CHAT_ID")
    or ""
).strip()

_is_policy_telegram_delivery = bool(
    _policy_bot_token
    or _policy_chat_id
    or os.getenv("TELEGRAM_DRY_RUN", "").lower() == "true"
)

if _is_policy_telegram_delivery:
    # The dedicated Westinghouse bot token is kept unchanged. If its dedicated
    # chat-id secret is absent, use the already verified policy private chat.
    # The fallback is process-local and affects only the final delivery process.
    if (
        not (os.getenv("KHS887900_CHAT_ID") or "").strip()
        and (os.getenv("KHS887900_BOT_TOKEN") or "").strip()
        and _policy_chat_id
    ):
        os.environ["KHS887900_CHAT_ID"] = _policy_chat_id
        print("policy_westinghouse_chat_route=fallback_policy_chat")

    try:
        from . import khs_policy_telegram_formatter as _formatter
        from .khs_policy_readability_patch import install as _install_readability

        _install_readability(_formatter)
    except Exception as _exc:  # Keep alert delivery alive if readability-only logic fails.
        print(f"policy_readability_patch_error={type(_exc).__name__}: {_exc}")
