"""Verified Telegram receipts for the existing KOSPI/KOSDAQ alert route.

The route probe only calls getMe/getChat. Sending keeps the configured route,
records the returned destination and rendered text, and never retries an
ambiguous send automatically. No token or unmasked recipient ID is exported.
"""
from __future__ import annotations

import argparse
import contextlib
import contextvars
import datetime as dt
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

_context = contextvars.ContextVar("market_alert_context", default={})
_lock = threading.RLock()
_routes: dict[str, dict] = {}
_receipts: dict[int, dict] = {}


class DeliveryUncertain(RuntimeError):
    """A POST may have succeeded; inspect its durable evidence before retrying."""


def digest(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


class _Plain(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, value):
        self.parts.append(value)


def rendered_text(text: str) -> str:
    parser = _Plain()
    parser.feed(text)
    parser.close()
    return "".join(parser.parts)


@contextlib.contextmanager
def delivery_context(**values):
    token = _context.set(values)
    try:
        yield
    finally:
        _context.reset(token)


def _root() -> Path:
    return Path(os.getenv("MARKET_ALERT_DELIVERY_DIR", "out/market_alert_delivery"))


def _stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _code_sha() -> str:
    explicit = os.getenv("MARKET_ALERT_CODE_SHA", "").strip()
    if explicit:
        return explicit
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True, timeout=5
        ).strip()
    except Exception:
        return "unverified"


def _append(record: dict) -> None:
    root = _root()
    root.mkdir(parents=True, exist_ok=True)
    with (root / "journal.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _states() -> dict:
    path = _root() / "journal.jsonl"
    if not path.exists():
        return {}
    states = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                row = json.loads(line)
                states[row["delivery_key"]] = row
            except (ValueError, KeyError):
                raise DeliveryUncertain("Market alert delivery journal is incomplete; automatic resend blocked") from None
    return states


def _read_api(token: str, method: str, data: dict | None = None) -> tuple[dict, bytes]:
    # Only idempotent read methods use transport retries.
    assert method in {"getMe", "getChat"}
    for attempt in range(3):
        try:
            request = urllib.request.Request(
                f"https://api.telegram.org/bot{token}/{method}",
                data=urllib.parse.urlencode(data).encode() if data else None,
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read()
            result = json.loads(raw)
            if not result.get("ok") or not isinstance(result.get("result"), dict):
                raise RuntimeError(f"Telegram {method} rejected the route lookup")
            return result["result"], raw
        except RuntimeError:
            raise
        except Exception:
            if attempt == 2:
                raise RuntimeError(f"Telegram {method} read failed; no message sent") from None
            time.sleep(1 + attempt)
    raise AssertionError("unreachable")


def verify_route(*, refresh: bool = False) -> dict:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    primary = os.getenv("TELEGRAM_CHAT_ID_PRIMARY", "").strip()
    fallback = os.getenv("TELEGRAM_CHAT_ID_FALLBACK", "").strip()
    chat = primary or fallback
    expected = os.getenv("EXPECTED_TELEGRAM_BOT_USERNAME", "").strip().lstrip("@")
    if not token or not chat:
        raise RuntimeError("Telegram token/chat id missing")
    cache_key = digest(token + "|" + chat + "|" + expected)
    with _lock:
        if not refresh and cache_key in _routes:
            return _routes[cache_key]
        bot, bot_raw = _read_api(token, "getMe")
        username = str(bot.get("username") or "")
        if not username or not bot.get("id") or (expected and username.lower() != expected.lower()):
            raise RuntimeError(f"Wrong Telegram bot: expected @{expected}, got @{username or 'unknown'}")
        target, target_raw = _read_api(token, "getChat", {"chat_id": chat})
        actual_id = str(target.get("id") or "")
        matches = (chat.lstrip("@").lower() == str(target.get("username") or "").lower()
                   if chat.startswith("@") else chat == actual_id)
        if not matches or not actual_id or target.get("type") not in {"private", "group", "supergroup", "channel"}:
            raise RuntimeError("Telegram getChat destination does not match the configured route")
        label = os.getenv("MARKET_ALERT_EXPECTED_CHAT_LABEL", "").strip()
        public = {"bot_username": username, "recipient_sha256": digest(actual_id),
                  "configured_recipient_sha256": digest(chat),
                  "chat_type": target["type"], "route_selection": "primary" if primary else "fallback",
                  "message_auto_delete_time_sec": target.get("message_auto_delete_time"),
                  "chat_is_forum": target.get("is_forum"),
                  "chat_title_sha256": digest(str(target.get("title") or "")),
                  "expected_label_matches_title": ("".join(label.split()) == "".join(str(target.get("title") or "").split())) if label else None,
                  "getMe_response_sha256": digest(bot_raw), "getChat_response_sha256": digest(target_raw),
                  "verified_at_utc": _stamp(), "code_sha": _code_sha(),
                  "run_id": os.getenv("GITHUB_RUN_ID", "local"), "read_only": True}
        route = {"token": token, "configured_chat": chat, "chat_id": actual_id,
                 "bot_id": bot["id"], "public": public}
        _routes[cache_key] = route
        root = _root()
        root.mkdir(parents=True, exist_ok=True)
        (root / "route.json").write_text(json.dumps(public, ensure_ascii=False, indent=2), encoding="utf-8")
        print("market_alert_route_verified=" + json.dumps(public, ensure_ascii=False), flush=True)
        return route


def receipt_for(message_id: int) -> dict | None:
    return _receipts.get(message_id)


def send_message(text: str) -> int:
    with _lock:
        route = verify_route()
        public = route["public"]
        context = dict(_context.get())
        request_hash = digest(text)
        identity = {k: context.get(k) for k in ("market", "stage", "actor", "event_start_ts", "expansion_from")}
        if not context:
            identity = {"request_body_sha256": request_hash}
        key = digest(json.dumps([public["bot_username"], public["recipient_sha256"], identity], sort_keys=True))
        states = _states()
        previous = states.get(key)
        if previous and previous.get("status") in {"in_flight", "uncertain"}:
            raise DeliveryUncertain("Unresolved Telegram send exists for this market event; automatic resend blocked")
        if previous and previous.get("status") == "confirmed":
            _receipts[int(previous["message_id"])] = previous
            print(f"market_alert_delivery_reused=true stage={context.get('stage')} message_id={previous['message_id']}", flush=True)
            return int(previous["message_id"])
        plain = rendered_text(text)
        if not 0 < len(plain) <= 4096:
            raise RuntimeError("Market alert text exceeds Telegram's rendered text limit")
        base = {"delivery_key": key, **public, "read_only": False, "context": context,
                "request_body_sha256": request_hash, "request_html": text,
                "expected_rendered_text_sha256": digest(plain), "started_at_utc": _stamp()}
        payload = urllib.parse.urlencode({"chat_id": route["configured_chat"], "text": text,
                                         "parse_mode": "HTML", "disable_web_page_preview": "true"}).encode()
        for attempt in range(4):
            _append({**base, "status": "in_flight", "attempt": attempt + 1})
            try:
                request = urllib.request.Request(f"https://api.telegram.org/bot{route['token']}/sendMessage", data=payload, method="POST")
                with urllib.request.urlopen(request, timeout=30) as response:
                    raw = response.read()
                result = json.loads(raw)
            except urllib.error.HTTPError as error:
                if 400 <= error.code < 500:
                    _append({**base, "status": "rejected", "http_status": error.code})
                    if error.code == 429 and attempt < 3:
                        time.sleep(2 * (attempt + 1))
                        continue
                    raise RuntimeError(f"Telegram HTTP {error.code}; message not approved") from None
                _append({**base, "status": "uncertain", "http_status": error.code})
                raise DeliveryUncertain("Telegram send response uncertain; automatic resend blocked") from None
            except Exception as error:
                _append({**base, "status": "uncertain", "error_type": type(error).__name__})
                raise DeliveryUncertain("Telegram send response uncertain; automatic resend blocked") from None
            if not result.get("ok"):
                _append({**base, "status": "rejected", "error_code": result.get("error_code")})
                if result.get("error_code") == 429 and attempt < 3:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise RuntimeError("Telegram rejected market alert; no approved receipt")
            message = result.get("result") or {}
            mid = message.get("message_id")
            actual_chat = str((message.get("chat") or {}).get("id") or "")
            sender = message.get("from") or {}
            verified = (isinstance(mid, int) and not isinstance(mid, bool) and mid > 0
                        and actual_chat == route["chat_id"] and message.get("text") == plain
                        and isinstance(message.get("date"), int)
                        and (not sender or sender.get("id") == route["bot_id"]))
            receipt = {**base, "status": "confirmed" if verified else "uncertain",
                       "message_id": mid, "returned_recipient_sha256": digest(actual_chat),
                       "telegram_date_utc": dt.datetime.fromtimestamp(message["date"], dt.timezone.utc).isoformat() if isinstance(message.get("date"), int) else None,
                       "telegram_rendered_text": message.get("text"),
                       "telegram_rendered_text_sha256": digest(str(message.get("text") or "")),
                       "response_sha256": digest(raw), "confirmed_at_utc": _stamp(),
                       "returned_message_thread_id": message.get("message_thread_id"),
                       "returned_chat_type": (message.get("chat") or {}).get("type")}
            _append(receipt)
            if not verified:
                raise DeliveryUncertain("Telegram returned destination/text/receipt fields mismatch; automatic resend blocked")
            _receipts[mid] = receipt
            print(f"telegram_delivery_confirmed=true bot=@{public['bot_username']} message_id={mid} "
                  f"market={context.get('market', 'unclassified')} stage={context.get('stage', 'unclassified')} "
                  f"recipient_sha256={public['recipient_sha256']} body_sha256={request_hash} "
                  f"telegram_date_utc={receipt['telegram_date_utc']}", flush=True)
            return mid
        raise RuntimeError("Telegram rate limit did not clear")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-route", action="store_true", required=True)
    parser.parse_args()
    verify_route(refresh=True)
