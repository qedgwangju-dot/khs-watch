from __future__ import annotations

import intismeran_structured_telegram_send as base
from bio_korean_guard_strict_v2 import ensure_korean_text

_original_send_message = base.send_message


def send_message(text: str):
    return _original_send_message(ensure_korean_text(text))


base.send_message = send_message


if __name__ == '__main__':
    raise SystemExit(base.main())
