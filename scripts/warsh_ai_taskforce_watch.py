#!/usr/bin/env python3
import hashlib
import html
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

URL = "https://www.federalreserve.gov/monetarypolicy/productivity-and-jobs-task-force.htm"
STATE_PATH = Path("data/warsh_ai_taskforce_watch_state.json")
UA = "Mozilla/5.0 (compatible; khs-watch/1.0; +https://github.com/qedgwangju-dot/khs-watch)"
TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
EXPECTED_BOT = (os.getenv("EXPECTED_BOT_USERNAME") or "khs8879887988798879_bot").strip().lstrip("@")
FORCE_NOTIFY = os.getenv("FORCE_NOTIFY", "0") == "1"

KEYWORDS = [
    "artificial intelligence", "general-purpose technologies", "productivity", "jobs",
    "employment", "inflation", "task force", "findings", "recommendations", "report",
    "productive capacity", "economic impact", "policy judgments"
]


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", errors="replace")


def clean_text(raw: str) -> str:
    raw = re.sub(r"(?is)<script.*?>.*?</script>|<style.*?>.*?</style>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h[1-6]>", "\n", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    text = html.unescape(raw).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def meaningful_text(text: str) -> str:
    lines = []
    for s in re.split(r"\n+|(?<=[.!?])\s+", text):
        s = re.sub(r"\s+", " ", s).strip()
        low = s.lower()
        if 20 <= len(s) <= 600 and any(k in low for k in KEYWORDS):
            lines.append(s)
    return "\n".join(dict.fromkeys(lines))


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get_bot_username() -> str:
    if not TOKEN:
        raise RuntimeError("Telegram token missing")
    with urllib.request.urlopen(f"https://api.telegram.org/bot{TOKEN}/getMe", timeout=20) as r:
        data = json.loads(r.read().decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError("Telegram getMe failed")
    return str((data.get("result") or {}).get("username") or "")


def send(text: str):
    if not TOKEN or not CHAT_ID:
        raise RuntimeError("Telegram token/chat id missing")
    username = get_bot_username()
    if username.lower() != EXPECTED_BOT.lower():
        raise RuntimeError(f"Wrong Telegram bot: expected @{EXPECTED_BOT}, got @{username}")
    payload = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text[:4090], "disable_web_page_preview": "true"}).encode("utf-8")
    req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data=payload, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        result = json.loads(r.read().decode("utf-8"))
    if not result.get("ok"):
        raise RuntimeError(f"Telegram send failed: {result}")


def load_state():
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    text = clean_text(fetch(URL))
    core = meaningful_text(text)
    fp = fingerprint(core)
    old = load_state()
    first_run = not bool(old.get("fingerprint"))
    changed = old.get("fingerprint") not in (None, fp)

    if FORCE_NOTIFY or changed:
        lines = core.splitlines()[:10]
        msg = [
            "[Fed AI 생산성·고용 태스크포스 변화 감지]",
            "Warsh가 AI를 'new variable / potentially a new factor of production'으로 규정한 후속 공식 업데이트입니다.",
            "",
            *[f"• {x}" for x in lines],
            "",
            "판정: AI가 잠재성장률·생산성·고용·중립금리/통화정책 판단에 실제 반영되는 단계로 넘어가는지 확인",
            f"원문: {URL}",
        ]
        send("\n".join(msg))

    save_state({"fingerprint": fp})
    print(json.dumps({"first_run": first_run, "changed": changed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
