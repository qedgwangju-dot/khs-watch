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
        elif part == 'scripts/qlex_telegram_send.py':
            patched.append('scripts/qlex_telegram_send_v2.py')
        elif part == 'scripts/intismeran_structured_telegram_send.py':
            patched.append('scripts/intismeran_structured_telegram_send_v2.py')
        else:
            patched.append(part)
    return _original_run(patched, timeout=timeout)


base.run = run


if __name__ == '__main__':
    raise SystemExit(base.main())
