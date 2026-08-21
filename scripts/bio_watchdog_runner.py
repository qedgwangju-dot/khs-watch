from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import sys
import urllib.request
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
DATA = ROOT / "data"
HEARTBEAT = DATA / "bio_watchdog_heartbeat.json"


def run(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=180,
    )
    output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    return proc.returncode, output[-4000:]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(KST).isoformat(timespec="seconds")
    hb: dict = {
        "checked_at_kst": now,
        "status": "started",
        "telegram_route_ok": False,
        "qlex_collector_rc": None,
        "intismeran_collector_rc": None,
        "qlex_alert_present": False,
        "intismeran_alert_present": False,
        "qlex_sender_rc": None,
        "intismeran_sender_rc": None,
        "qlex_state_persisted": False,
        "intismeran_state_persisted": False,
        "errors": [],
    }

    try:
        token = (os.getenv("BIO_TELEGRAM_BOT_TOKEN") or "").strip()
        chat_id = (os.getenv("BIO_TELEGRAM_CHAT_ID") or "").strip()
        expected = (os.getenv("EXPECTED_TELEGRAM_BOT_USERNAME") or "").strip().lstrip("@")
        if not token or not chat_id or not expected:
            raise RuntimeError("BIO Telegram token/chat_id/expected username missing")
        with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getMe", timeout=25) as response:
            identity = json.loads(response.read().decode("utf-8"))
        actual = str((identity.get("result") or {}).get("username") or "")
        if not identity.get("ok") or actual.lower() != expected.lower():
            raise RuntimeError(f"Wrong bio Telegram bot: expected @{expected}, got @{actual or 'unknown'}")
        hb["telegram_route_ok"] = True
        hb["bot_username"] = actual

        for name in ("qlex_sc_conversion_alert.md", "intismeran_qlex_alert.md"):
            path = OUT / name
            if path.exists():
                path.unlink()

        qlex_rc, qlex_log = run([sys.executable, "scripts/qlex_sc_conversion_watch.py", "--mode", "check"])
        hb["qlex_collector_rc"] = qlex_rc
        if qlex_rc != 0:
            hb["errors"].append(f"qlex collector rc={qlex_rc}: {qlex_log}")

        int_rc, int_log = run([sys.executable, "scripts/intismeran_qlex_watch.py"])
        hb["intismeran_collector_rc"] = int_rc
        if int_rc != 0:
            hb["errors"].append(f"intismeran collector rc={int_rc}: {int_log}")

        qlex_alert = OUT / "qlex_sc_conversion_alert.md"
        int_alert = OUT / "intismeran_qlex_alert.md"
        hb["qlex_alert_present"] = qlex_alert.exists()
        hb["intismeran_alert_present"] = int_alert.exists()

        qlex_delivery_ok = qlex_rc == 0
        if qlex_rc == 0 and qlex_alert.exists():
            rc, log = run([sys.executable, "scripts/qlex_telegram_send.py", str(qlex_alert.relative_to(ROOT))])
            hb["qlex_sender_rc"] = rc
            qlex_delivery_ok = rc == 0
            if rc != 0:
                hb["errors"].append(f"qlex sender rc={rc}: {log}")

        int_delivery_ok = int_rc == 0
        if int_rc == 0 and int_alert.exists():
            rc, log = run([sys.executable, "scripts/intismeran_structured_telegram_send.py", str(int_alert.relative_to(ROOT))])
            hb["intismeran_sender_rc"] = rc
            int_delivery_ok = rc == 0
            if rc != 0:
                hb["errors"].append(f"intismeran sender rc={rc}: {log}")

        qlex_pending = OUT / "qlex_sc_conversion_watch_state_pending.json"
        if qlex_delivery_ok and qlex_pending.exists():
            shutil.copy2(qlex_pending, DATA / "qlex_sc_conversion_watch_state.json")
            hb["qlex_state_persisted"] = True

        int_pending = OUT / "intismeran_qlex_watch_state_pending.json"
        if int_delivery_ok and int_pending.exists():
            shutil.copy2(int_pending, DATA / "intismeran_qlex_watch_state.json")
            hb["intismeran_state_persisted"] = True

        hb["status"] = "ok" if (
            hb["telegram_route_ok"]
            and qlex_rc == 0
            and int_rc == 0
            and qlex_delivery_ok
            and int_delivery_ok
            and hb["qlex_state_persisted"]
            and hb["intismeran_state_persisted"]
        ) else "degraded"
    except Exception as exc:
        hb["status"] = "failed"
        hb["errors"].append(f"{type(exc).__name__}: {exc}")
    finally:
        HEARTBEAT.write_text(json.dumps(hb, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(hb, ensure_ascii=False))

    # Do not break the independent global-rates monitor; heartbeat records bio failure explicitly.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
