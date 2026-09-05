from __future__ import annotations

import qlex_telegram_send as base
from bio_korean_guard_strict_v2 import ensure_korean_text

_original_normalize = base.normalize_alert_language


def normalize_alert_language(text: str) -> str:
    return ensure_korean_text(_original_normalize(text))


base.normalize_alert_language = normalize_alert_language


if __name__ == '__main__':
    raise SystemExit(base.main())
