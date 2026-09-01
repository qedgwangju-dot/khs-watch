from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
DATA = ROOT / "data"
HEARTBEAT = DATA / "bio_watch_heartbeat.json"
ROUTE_FILE = DATA / "bio_telegram_chat_id.enc"


def run(cmd: list[str], timeout: int = 240) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
        env=os.environ.copy(),
    )
    text = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    return proc.returncode, text[-6000:]


def decrypt_chat_id(token: str) -> str:
    if not ROUTE_FILE.exists():
        return ""
    env = os.environ.copy()
    env["BIO_TELEGRAM_BOT_TOKEN"] = token
    proc = subprocess.run(
        [
            "openssl", "enc", "-d", "-aes-256-cbc", "-a", "-A", "-pbkdf2",
            "-pass", "env:BIO_TELEGRAM_BOT_TOKEN",
            "-in", str(ROUTE_FILE),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=30,
        env=env,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def verify_route() -> tuple[str, str, str]:
    token = (os.getenv("BIO_TELEGRAM_BOT_TOKEN") or "").strip()
    expected = (os.getenv("EXPECTED_TELEGRAM_BOT_USERNAME") or "").strip().lstrip("@")
    chat_id = (os.getenv("BIO_TELEGRAM_CHAT_ID") or "").strip()
    source = "secret"
    if not token or not expected:
        raise RuntimeError("BIO Telegram token or expected username missing")
    if not chat_id:
        chat_id = decrypt_chat_id(token)
        source = "encrypted-route"
    if not chat_id:
        raise RuntimeError("BIO Telegram chat route missing")

    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getMe", timeout=25) as response:
        identity = json.loads(response.read().decode("utf-8"))
    actual = str((identity.get("result") or {}).get("username") or "")
    if not identity.get("ok") or actual.lower() != expected.lower():
        raise RuntimeError(f"Wrong Telegram bot: expected @{expected}, got @{actual or 'unknown'}")

    os.environ["BIO_TELEGRAM_CHAT_ID"] = chat_id
    return token, chat_id, source


def send_text(token: str, chat_id: str, text: str) -> int:
    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not result.get("ok"):
        raise RuntimeError(f"Telegram rejected status message: {result}")
    return int((result.get("result") or {}).get("message_id") or 0)


def previous_heartbeat() -> dict:
    try:
        return json.loads(HEARTBEAT.read_text(encoding="utf-8")) if HEARTBEAT.exists() else {}
    except Exception:
        return {}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    now_dt = dt.datetime.now(KST)
    now = now_dt.isoformat(timespec="seconds")
    prev = previous_heartbeat()

    hb: dict = {
        "status": "started",
        "checked_at_kst": now,
        "route_source": "",
        "telegram_route_ok": False,
        "qlex_collector_rc": None,
        "intismeran_collector_rc": None,
        "jemperli_collector_rc": None,
        "enhertu_collector_rc": None,
        "qlex_alert_present": False,
        "intismeran_alert_present": False,
        "jemperli_alert_present": False,
        "enhertu_alert_present": False,
        "qlex_send_outcome": "skipped",
        "intismeran_send_outcome": "skipped",
        "jemperli_send_outcome": "skipped",
        "enhertu_send_outcome": "skipped",
        "qlex_state_persisted": False,
        "intismeran_state_persisted": False,
        "jemperli_state_persisted": False,
        "enhertu_state_persisted": False,
        "intismeran_retry_pending": False,
        "last_health_notice_date": prev.get("last_health_notice_date", ""),
        "errors": [],
    }

    token = ""
    chat_id = ""
    try:
        token, chat_id, route_source = verify_route()
        hb["route_source"] = route_source
        hb["telegram_route_ok"] = True

        for name in (
            "qlex_sc_conversion_alert.md",
            "intismeran_qlex_alert.md",
            "intismeran_structured_send_confirmed.json",
            "jemperli_altb4_alert.md",
            "enhertu_altb4_alert.md",
        ):
            (OUT / name).unlink(missing_ok=True)

        qlex_rc, qlex_log = run([sys.executable, "scripts/qlex_sc_conversion_watch.py", "--mode", "check"])
        hb["qlex_collector_rc"] = qlex_rc
        if qlex_rc != 0:
            hb["errors"].append(f"QLEX collector rc={qlex_rc}: {qlex_log}")

        int_rc, int_log = run([sys.executable, "scripts/intismeran_qlex_watch.py"])
        hb["intismeran_collector_rc"] = int_rc
        if int_rc != 0:
            hb["errors"].append(f"Intismeran collector rc={int_rc}: {int_log}")

        jemp_rc, jemp_log = run([sys.executable, "scripts/jemperli_altb4_watch.py"])
        hb["jemperli_collector_rc"] = jemp_rc
        if jemp_rc != 0:
            hb["errors"].append(f"Jemperli collector rc={jemp_rc}: {jemp_log}")

        enh_rc, enh_log = run([sys.executable, "scripts/enhertu_altb4_watch.py"])
        hb["enhertu_collector_rc"] = enh_rc
        if enh_rc != 0:
            hb["errors"].append(f"Enhertu collector rc={enh_rc}: {enh_log}")

        qlex_alert = OUT / "qlex_sc_conversion_alert.md"
        int_alert = OUT / "intismeran_qlex_alert.md"
        jemp_alert = OUT / "jemperli_altb4_alert.md"
        enh_alert = OUT / "enhertu_altb4_alert.md"
        hb["qlex_alert_present"] = qlex_alert.exists()
        hb["intismeran_alert_present"] = int_alert.exists()
        hb["jemperli_alert_present"] = jemp_alert.exists()
        hb["enhertu_alert_present"] = enh_alert.exists()

        qlex_handled = qlex_rc == 0
        if qlex_rc == 0 and qlex_alert.exists():
            rc, log = run([sys.executable, "scripts/qlex_telegram_send.py", str(qlex_alert.relative_to(ROOT))])
            hb["qlex_send_outcome"] = "success" if rc == 0 else "failure"
            qlex_handled = rc == 0
            if rc != 0:
                hb["errors"].append(f"QLEX sender rc={rc}: {log}")

        qlex_pending = OUT / "qlex_sc_conversion_watch_state_pending.json"
        if qlex_handled and qlex_pending.exists():
            shutil.copy2(qlex_pending, DATA / "qlex_sc_conversion_watch_state.json")
            hb["qlex_state_persisted"] = True

        int_handled = int_rc == 0
        if int_rc == 0 and int_alert.exists():
            rc, log = run([sys.executable, "scripts/intismeran_structured_telegram_send.py", str(int_alert.relative_to(ROOT))])
            hb["intismeran_send_outcome"] = "success" if rc == 0 else "failure"
            confirmed = OUT / "intismeran_structured_send_confirmed.json"
            if rc == 0 and confirmed.exists():
                int_handled = True
            elif rc == 0:
                int_handled = False
                hb["intismeran_retry_pending"] = True
            else:
                int_handled = False
                hb["errors"].append(f"Intismeran sender rc={rc}: {log}")

        int_pending = OUT / "intismeran_qlex_watch_state_pending.json"
        if int_handled and int_pending.exists():
            shutil.copy2(int_pending, DATA / "intismeran_qlex_watch_state.json")
            hb["intismeran_state_persisted"] = True

        jemp_handled = jemp_rc == 0
        if jemp_rc == 0 and jemp_alert.exists():
            rc, log = run([sys.executable, "scripts/qlex_telegram_send.py", str(jemp_alert.relative_to(ROOT))])
            hb["jemperli_send_outcome"] = "success" if rc == 0 else "failure"
            jemp_handled = rc == 0
            if rc != 0:
                hb["errors"].append(f"Jemperli sender rc={rc}: {log}")

        jemp_pending = OUT / "jemperli_altb4_watch_state_pending.json"
        if jemp_handled and jemp_pending.exists():
            shutil.copy2(jemp_pending, DATA / "jemperli_altb4_watch_state.json")
            hb["jemperli_state_persisted"] = True

        enh_handled = enh_rc == 0
        if enh_rc == 0 and enh_alert.exists():
            rc, log = run([sys.executable, "scripts/qlex_telegram_send.py", str(enh_alert.relative_to(ROOT))])
            hb["enhertu_send_outcome"] = "success" if rc == 0 else "failure"
            enh_handled = rc == 0
            if rc != 0:
                hb["errors"].append(f"Enhertu sender rc={rc}: {log}")

        enh_pending = OUT / "enhertu_altb4_watch_state_pending.json"
        if enh_handled and enh_pending.exists():
            shutil.copy2(enh_pending, DATA / "enhertu_altb4_watch_state.json")
            hb["enhertu_state_persisted"] = True

        operational = (
            hb["telegram_route_ok"]
            and qlex_rc == 0
            and int_rc == 0
            and jemp_rc == 0
            and enh_rc == 0
            and hb["qlex_state_persisted"]
            and (hb["intismeran_state_persisted"] or hb["intismeran_retry_pending"])
            and hb["jemperli_state_persisted"]
            and hb["enhertu_state_persisted"]
            and hb["qlex_send_outcome"] != "failure"
            and hb["intismeran_send_outcome"] != "failure"
            and hb["jemperli_send_outcome"] != "failure"
            and hb["enhertu_send_outcome"] != "failure"
        )
        hb["status"] = "ok" if operational else "degraded"

        today = now_dt.date().isoformat()
        if operational and hb.get("last_health_notice_date") != today and now_dt.hour >= 9:
            message_id = send_text(
                token,
                chat_id,
                "[바이오 감시] 정상 작동 확인\n\n"
                f"- 마지막 확인: {now_dt.strftime('%Y-%m-%d %H:%M KST')}\n"
                "- QLEX·Intismeran·Jemperli·Enhertu 감시: 정상\n"
                f"- Telegram 경로: {route_source}\n"
                "- 새 데이터가 없으면 별도 본 알림은 보내지 않습니다.",
            )
            hb["last_health_notice_date"] = today
            hb["health_notice_message_id"] = message_id

    except Exception as exc:
        hb["status"] = "failed"
        hb["errors"].append(f"{type(exc).__name__}: {exc}")
        if token and chat_id:
            try:
                hb["failure_notice_message_id"] = send_text(
                    token,
                    chat_id,
                    "[바이오 감시] 실행 오류\n\n"
                    f"- 시각: {now_dt.strftime('%Y-%m-%d %H:%M KST')}\n"
                    "- QLEX·Intismeran·Jemperli·Enhertu 감시 실행 중 오류가 발생했습니다.\n"
                    "- 다음 15분 실행에서 다시 확인합니다.",
                )
            except Exception:
                pass
    finally:
        HEARTBEAT.write_text(json.dumps(hb, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(hb, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
