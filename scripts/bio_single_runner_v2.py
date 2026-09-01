from __future__ import annotations

import bio_single_runner as base

_original_run = base.run


def run(cmd: list[str], timeout: int = 240):
    patched = [
        "scripts/enhertu_altb4_watch_v2.py" if part == "scripts/enhertu_altb4_watch.py" else part
        for part in cmd
    ]
    return _original_run(patched, timeout=timeout)


base.run = run


if __name__ == "__main__":
    raise SystemExit(base.main())
