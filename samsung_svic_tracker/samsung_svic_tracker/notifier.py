from __future__ import annotations

import json
import os
import urllib.request


def _telegram_text(payload: dict) -> str:
    if payload.get("type") == "collector_error":
        return (
            "⚠️ [SVIC 82·83 수집 오류]\n"
            f"출처: {payload.get('source', '확인 불가')}\n"
            f"연속 실패: {payload.get('consecutive_failures', 3)}회\n"
            f"오류: {payload.get('error', '확인 불가')}"
        )
    sources = payload.get("sources") or []
    source_lines = "\n".join(str(url) for url in sources)
    return (
        "🔎 [SVIC 82·83 신규 공식자료]\n"
        f"기업: {payload.get('company', '확인 필요')}\n"
        f"구분: {payload.get('event', '확인 필요')}\n"
        f"내용: {payload.get('summary', '확인 필요')}\n"
        f"공식 근거:\n{source_lines or '확인 필요'}"
    )


def _telegram_get_me(token: str) -> str:
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getMe", timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError("Telegram getMe failed")
    return str((data.get("result") or {}).get("username") or "")


def notify(payload: dict) -> None:
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.getenv("SVIC_TELEGRAM_CHAT_ID")
    if telegram_token and telegram_chat_id:
        expected = (os.getenv("SVIC_EXPECTED_TELEGRAM_BOT_USERNAME") or "khs8879_bot").strip().lstrip("@")
        actual = _telegram_get_me(telegram_token)
        if actual.lower() != expected.lower():
            raise RuntimeError(f"Wrong Telegram bot: expected @{expected}, got @{actual or 'unknown'}")

        telegram_url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
        telegram_payload = {
            "chat_id": telegram_chat_id,
            "text": _telegram_text(payload),
            "disable_web_page_preview": True,
        }
        request = urllib.request.Request(
            telegram_url,
            data=json.dumps(telegram_payload, ensure_ascii=False).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status >= 300:
                raise RuntimeError(f"Telegram returned HTTP {response.status}")
        return
    url = os.getenv("ALERT_WEBHOOK_URL")
    if not url:
        print(json.dumps(payload, ensure_ascii=False))
        return
    request = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status >= 300:
            raise RuntimeError(f"webhook returned HTTP {response.status}")
