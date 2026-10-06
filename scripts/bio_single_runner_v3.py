from __future__ import annotations

import bio_single_runner as base

_original_run = base.run


def run(cmd: list[str], timeout: int = 240):
    patched: list[str] = []
    for part in cmd:
        if part == 'scripts/enhertu_altb4_watch.py':
            patched.append('scripts/enhertu_altb4_watch_v2.py')
        elif part == 'scripts/jemperli_altb4_watch.py':
            patched.append('scripts/jemperli_altb4_watch_v2.py')
        elif part == 'scripts/qlex_wac_ir_watch.py':
            patched.append('scripts/qlex_wac_ir_watch_v2.py')
        elif part == 'scripts/qlex_telegram_send.py':
            patched.append('scripts/qlex_telegram_send_v2.py')
        elif part == 'scripts/intismeran_structured_telegram_send.py':
            patched.append('scripts/intismeran_structured_telegram_send_v2.py')
        else:
            patched.append(part)
    effective_timeout = timeout
    if 'scripts/halozyme_legal_watch_v4.py' in patched:
        effective_timeout = max(timeout, 300)
    return _original_run(patched, timeout=effective_timeout)


base.run = run


if __name__ == '__main__':
    raise SystemExit(base.main())
