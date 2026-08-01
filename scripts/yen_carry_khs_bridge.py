#!/usr/bin/env python3
"""Compatibility stub.

Yen-carry alerts are delivered by the dedicated scheduled workflow. Keeping this
entry point prevents the legacy KHS hook from failing while avoiding duplicate
Telegram messages.
"""

from __future__ import annotations


def main() -> int:
    print("yen_carry_bridge=disabled_dedicated_workflow")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
