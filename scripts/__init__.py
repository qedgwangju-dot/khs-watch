"""Scoped runtime hooks for KHS scripts.

The policy Telegram readability patch is activated only inside the final
Telegram delivery process, where POLICY_TELEGRAM_* is exported by the workflow.
Other script executions keep their existing behavior.
"""

from __future__ import annotations

import os


_is_policy_telegram_delivery = bool(
    os.getenv("POLICY_TELEGRAM_BOT_TOKEN")
    or os.getenv("POLICY_TELEGRAM_CHAT_ID")
    or os.getenv("TELEGRAM_DRY_RUN", "").lower() == "true"
)

if _is_policy_telegram_delivery:
    try:
        from . import khs_policy_telegram_formatter as _formatter
        from .khs_policy_readability_patch import install as _install_readability

        _install_readability(_formatter)
    except Exception as _exc:  # Keep alert delivery alive if readability-only logic fails.
        print(f"policy_readability_patch_error={type(_exc).__name__}: {_exc}")
