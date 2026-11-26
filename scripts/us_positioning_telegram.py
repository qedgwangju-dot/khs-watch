#!/usr/bin/env python3
"""Image rendering and Telegram photo delivery for the US positioning watcher only.

The report HTML remains the source of truth. This module renders that exact
Telegram-safe fragment to PNG, uploads it with sendPhoto, and records an
unconfirmed delivery guard before any network send so ambiguous outcomes are
never automatically resent.
"""
from __future__ import annotations

import argparse
import hashlib
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


MAX_REPORT_CHARS = 3600
MAX_CAPTION_CHARS = 1024
MAX_PHOTO_BYTES = 9_500_000
MAX_DIMENSION_SUM = 10_000
MAX_ASPECT_RATIO = 20
VIEWPORT_WIDTH = 1280
CONTENT_MAX_HEIGHT = 8_600
SAFE_GUARD_STATUSES = {"confirmed", "retry_safe"}


class _TelegramFragmentParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.text_parts = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "b":
            if attrs:
                raise ValueError("Telegram alert has unexpected <b> attributes")
        elif tag == "a":
            if set(attrs) != {"href"}:
                raise ValueError("Telegram alert link must contain only href")
            href = attrs["href"]
            parsed = urlsplit(href)
            if parsed.scheme != "https" or parsed.hostname != "github.com":
                raise ValueError("Telegram alert link is outside the trusted GitHub host")
            self.links.append(href)
        else:
            raise ValueError(f"Telegram alert contains unsupported HTML tag: {tag}")
        self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        raise ValueError(f"Telegram alert contains unexpected self-closing tag: {tag}")

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            raise ValueError(f"Telegram alert has unbalanced HTML tag: {tag}")
        self.stack.pop()

    def handle_data(self, data):
        self.text_parts.append(data)

    def handle_comment(self, data):
        raise ValueError("Telegram alert contains an unexpected HTML comment")


def parse_alert_fragment(fragment: str) -> dict:
    if not isinstance(fragment, str) or not fragment.strip():
        raise ValueError("US positioning alert is empty")
    if len(fragment.strip()) > MAX_REPORT_CHARS:
        raise ValueError("US positioning alert exceeds the image report budget")
    parser = _TelegramFragmentParser()
    parser.feed(fragment)
    parser.close()
    if parser.stack:
        raise ValueError("US positioning alert contains unclosed HTML tags")
    visible_text = "".join(parser.text_parts)
    title = next((line.strip() for line in visible_text.splitlines() if line.strip()), "")
    if not title:
        raise ValueError("US positioning alert has no visible title")
    return {"visible_text": visible_text, "title": title, "links": parser.links}


def _trusted_detail_url(parsed: dict) -> str | None:
    for href in reversed(parsed["links"]):
        parts = urlsplit(href)
        if parts.path.startswith("/qedgwangju-dot/khs-watch/actions/runs/") or (
            parts.path.startswith("/qedgwangju-dot/khs-watch/actions/")
        ):
            return href
    return None


def build_caption(fragment: str) -> str:
    parsed = parse_alert_fragment(fragment)
    title = html.escape(parsed["title"])
    caption = f"<b>{title}</b>\n전체 보고는 이미지에서 확인하세요."
    detail_url = _trusted_detail_url(parsed)
    if detail_url:
        caption += f'\n<a href="{html.escape(detail_url, quote=True)}">상세 계산·원문</a>'
    caption_visible = _TelegramFragmentParser()
    caption_visible.feed(caption)
    caption_visible.close()
    if len("".join(caption_visible.text_parts)) > MAX_CAPTION_CHARS:
        raise ValueError("Telegram photo caption exceeds the 1024-character limit")
    return caption


def png_dimensions(data: bytes) -> tuple[int, int]:
    signature = b"\x89PNG\r\n\x1a\n"
    if not isinstance(data, bytes) or len(data) < 45 or data[:8] != signature:
        raise ValueError("Image output is not a valid PNG")
    position = 8
    dimensions = None
    saw_idat = False
    saw_iend = False
    while position + 12 <= len(data):
        size = struct.unpack(">I", data[position:position + 4])[0]
        kind = data[position + 4:position + 8]
        end = position + 12 + size
        if end > len(data):
            raise ValueError("PNG contains a truncated chunk")
        payload = data[position + 8:position + 8 + size]
        expected_crc = struct.unpack(">I", data[position + 8 + size:end])[0]
        actual_crc = zlib.crc32(kind + payload) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise ValueError("PNG chunk checksum failed")
        if dimensions is None:
            if kind != b"IHDR" or size != 13:
                raise ValueError("PNG is missing its required IHDR header")
            dimensions = struct.unpack(">II", payload[:8])
        elif kind == b"IHDR":
            raise ValueError("PNG contains duplicate IHDR headers")
        if kind == b"IDAT":
            saw_idat = True
        if kind == b"IEND":
            if size != 0:
                raise ValueError("PNG IEND chunk is malformed")
            saw_iend = True
            position = end
            break
        position = end
    if dimensions is None or not saw_idat or not saw_iend or position != len(data):
        raise ValueError("PNG is incomplete or contains trailing bytes")
    return dimensions


def validate_photo_bytes(data: bytes) -> dict:
    width, height = png_dimensions(data)
    if width <= 0 or height <= 0:
        raise ValueError("Image dimensions are empty")
    if width + height > MAX_DIMENSION_SUM:
        raise ValueError(f"Telegram photo dimensions exceed {MAX_DIMENSION_SUM}px combined")
    if max(width / height, height / width) > MAX_ASPECT_RATIO:
        raise ValueError(f"Telegram photo aspect ratio exceeds {MAX_ASPECT_RATIO}:1")
    if len(data) > MAX_PHOTO_BYTES:
        raise ValueError(f"Telegram photo exceeds safe upload budget ({MAX_PHOTO_BYTES} bytes)")
    return {"width": width, "height": height, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _chrome_path(chromium):
    candidates = (
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    )
    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate
    bundled = Path(chromium.executable_path)
    if bundled.is_file():
        return str(bundled)
    raise RuntimeError("system or Playwright Chromium executable not found")


def _require_korean_font():
    if not sys.platform.startswith("linux"):
        return
    fc_match = shutil.which("fc-match")
    if not fc_match:
        raise RuntimeError("fontconfig is required to verify Korean report font")
    match = subprocess.run(
        [fc_match, "-f", "%{family}", "Noto Sans CJK KR"],
        check=True, capture_output=True, text=True, timeout=10,
    ).stdout.lower()
    if "noto sans cjk" not in match and "noto serif cjk" not in match:
        raise RuntimeError("Noto CJK Korean font is unavailable; refusing to create tofu text")


def render_alert_document(fragment: str) -> str:
    parse_alert_fragment(fragment)
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; background: #edf2f8; }}
body {{
  width: {VIEWPORT_WIDTH}px;
  padding: 34px 0;
  color: #172033;
  font-family: "Noto Sans CJK KR", "Malgun Gothic", "Apple SD Gothic Neo", sans-serif;
}}
main {{
  width: 1160px;
  margin: 0 auto;
  padding: 52px 58px;
  border: 1px solid #dbe3ee;
  border-radius: 22px;
  background: #ffffff;
  box-shadow: 0 12px 36px rgba(26, 45, 71, .10);
  font-size: 25px;
  line-height: 1.56;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: keep-all;
}}
b {{ color: #0d2745; font-weight: 750; }}
a {{ color: #125e9a; text-decoration: underline; overflow-wrap: anywhere; }}
</style>
</head>
<body><main>{fragment}</main></body>
</html>"""


def render_alert_png(alert_path: Path, image_path: Path) -> dict:
    fragment = alert_path.read_text(encoding="utf-8").strip()
    parse_alert_fragment(fragment)
    _require_korean_font()
    from playwright.sync_api import sync_playwright

    document = render_alert_document(fragment)
    image_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=_chrome_path(playwright.chromium),
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = browser.new_page(
            viewport={"width": VIEWPORT_WIDTH, "height": 1024},
            device_scale_factor=1,
            locale="ko-KR",
            color_scheme="light",
        )
        page.set_content(document, wait_until="load")
        page.evaluate("() => document.fonts.ready")
        page.wait_for_timeout(150)
        metrics = page.locator("body").evaluate(
            "(el) => ({width: Math.ceil(el.scrollWidth), height: Math.ceil(el.scrollHeight)})"
        )
        if metrics["height"] > CONTENT_MAX_HEIGHT:
            browser.close()
            raise ValueError(
                f"US positioning image would be too tall ({metrics['height']}px); no Telegram send"
            )
        data = page.screenshot(full_page=True, type="png", animations="disabled")
        browser.close()
    photo = validate_photo_bytes(data)
    if photo["width"] != metrics["width"] or photo["height"] != metrics["height"]:
        raise ValueError("PNG dimensions differ from the checked browser layout")
    image_path.write_bytes(data)
    return {**photo, "alert_text_sha256": hashlib.sha256(
        parse_alert_fragment(fragment)["visible_text"].encode("utf-8")
    ).hexdigest()}


def guard_status(guard: dict | None) -> str:
    if not guard:
        return "clear"
    return str(guard.get("status") or "unknown")


def guard_blocks_send(guard: dict | None) -> bool:
    return bool(guard) and guard_status(guard) not in SAFE_GUARD_STATUSES


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Unable to read delivery state: {path.name}") from None


def write_json_atomic(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", dir=path.parent,
        prefix=path.name + ".", suffix=".tmp", delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    temp_path.replace(path)


def prepare_attempt(alert_path: Path, image_path: Path, guard_path: Path, attempt_path: Path,
                    run_id: str, head_sha: str, bot_username: str, chat_id: str) -> dict:
    prior = read_json(guard_path, {})
    if guard_blocks_send(prior):
        raise RuntimeError(
            "Prior Telegram delivery is unconfirmed; manual reconciliation is required before any resend"
        )
    fragment = alert_path.read_text(encoding="utf-8").strip()
    parsed = parse_alert_fragment(fragment)
    photo = validate_photo_bytes(image_path.read_bytes())
    caption = build_caption(fragment)
    alert_digest = hashlib.sha256(parsed["visible_text"].encode("utf-8")).hexdigest()
    caption_digest = hashlib.sha256(caption.encode("utf-8")).hexdigest()
    recipient_digest = hashlib.sha256(chat_id.encode("utf-8")).hexdigest()
    attempt_core = {
        "run_id": str(run_id),
        "head_sha": str(head_sha),
        "alert_sha256": alert_digest,
        "image_sha256": photo["sha256"],
        "caption_sha256": caption_digest,
        "recipient_sha256": recipient_digest,
    }
    attempt_id = hashlib.sha256(
        json.dumps(attempt_core, sort_keys=True).encode("utf-8")
    ).hexdigest()
    candidate = {
        "schema_version": 1,
        "status": "unconfirmed",
        "attempt_id": attempt_id,
        "attempt_count": int(prior.get("attempt_count") or 0) + 1,
        "attempted_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_id": str(run_id),
        "head_sha": str(head_sha),
        "delivery_method": "sendPhoto",
        "bot_username": str(bot_username).strip().lstrip("@"),
        "recipient_sha256": recipient_digest,
        "alert_text_sha256": alert_digest,
        "caption_sha256": caption_digest,
        "image_sha256": photo["sha256"],
        "image_width": photo["width"],
        "image_height": photo["height"],
        "image_bytes": photo["bytes"],
    }
    write_json_atomic(attempt_path, candidate)
    return candidate


def attempt_matches_files(guard: dict, alert_path: Path, image_path: Path) -> bool:
    try:
        fragment = alert_path.read_text(encoding="utf-8").strip()
        parsed = parse_alert_fragment(fragment)
        photo = validate_photo_bytes(image_path.read_bytes())
    except Exception:
        return False
    alert_digest = hashlib.sha256(parsed["visible_text"].encode("utf-8")).hexdigest()
    caption_digest = hashlib.sha256(build_caption(fragment).encode("utf-8")).hexdigest()
    return (
        guard.get("status") == "unconfirmed"
        and guard.get("delivery_method") == "sendPhoto"
        and guard.get("alert_text_sha256") == alert_digest
        and guard.get("caption_sha256") == caption_digest
        and guard.get("image_sha256") == photo["sha256"]
        and guard.get("image_width") == photo["width"]
        and guard.get("image_height") == photo["height"]
    )


def _write_rejection(path: Path, attempt_id: str, kind: str, error_code=None):
    write_json_atomic(path, {
        "status": "retry_safe",
        "attempt_id": attempt_id,
        "rejection_kind": kind,
        "error_code": error_code if type(error_code) is int else None,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
    })


def _multipart(fields: dict[str, str], photo: bytes) -> tuple[bytes, str]:
    boundary = "----us-positioning-" + hashlib.sha256(os.urandom(24)).hexdigest()[:32]
    pieces = []
    for key, value in fields.items():
        pieces.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{key}"\r\n\r\n'
            f"{value}\r\n".encode("utf-8")
        )
    pieces.append(
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="photo"; filename="us_positioning_alert.png"\r\n'
        "Content-Type: image/png\r\n\r\n".encode("utf-8")
        + photo + b"\r\n"
    )
    pieces.append(f"--{boundary}--\r\n".encode("ascii"))
    return b"".join(pieces), boundary


def _matches_recipient(target: dict, chat_id: str) -> bool:
    returned_id = target.get("id")
    if type(returned_id) is not int:
        return False
    value = str(chat_id).strip()
    if value.lstrip("-").isdigit():
        return str(returned_id) == value
    if value.startswith("@"):
        return str(target.get("username") or "").lower() == value[1:].lower()
    return False


def send_photo(alert_path: Path, image_path: Path, guard_path: Path, receipt_path: Path,
               rejection_path: Path, unconfirmed_path: Path, token: str,
               chat_id: str, expected_bot: str) -> dict:
    token = str(token).strip()
    chat_id = str(chat_id).strip()
    expected_bot = str(expected_bot).strip().lstrip("@")
    if not token or not chat_id or not expected_bot:
        raise RuntimeError("Telegram photo route configuration is incomplete")
    guard = read_json(guard_path)
    if not guard or not attempt_matches_files(guard, alert_path, image_path):
        raise RuntimeError("Telegram photo attempt does not match the persisted guard")
    if guard.get("recipient_sha256") != hashlib.sha256(chat_id.encode("utf-8")).hexdigest():
        raise RuntimeError("Telegram configured recipient does not match the persisted photo attempt")
    if guard.get("bot_username", "").lower() != expected_bot.lower():
        raise RuntimeError("Telegram configured bot does not match the persisted photo attempt")
    fragment = alert_path.read_text(encoding="utf-8").strip()
    photo = image_path.read_bytes()
    photo_meta = validate_photo_bytes(photo)
    caption = build_caption(fragment)
    attempt_id = guard["attempt_id"]

    for path in (receipt_path, rejection_path, unconfirmed_path):
        path.unlink(missing_ok=True)

    try:
        with urlopen(f"https://api.telegram.org/bot{token}/getMe", timeout=25) as response:
            identity = json.loads(response.read().decode("utf-8"))
    except Exception:
        _write_rejection(rejection_path, attempt_id, "preflight_failed_no_photo_request")
        raise RuntimeError("Telegram bot preflight failed before any photo upload; safe retry recorded") from None
    actual_bot = str((identity.get("result") or {}).get("username") or "")
    if not identity.get("ok") or actual_bot.lower() != expected_bot.lower():
        _write_rejection(rejection_path, attempt_id, "bot_identity_mismatch_no_photo_request")
        raise RuntimeError("Telegram bot identity mismatch before any photo upload; safe retry recorded")

    fields = {
        "chat_id": chat_id,
        "caption": caption,
        "parse_mode": "HTML",
        "show_caption_above_media": "true",
    }
    body, boundary = _multipart(fields, photo)
    request = Request(
        f"https://api.telegram.org/bot{token}/sendPhoto",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=60) as response:
            response_status = response.status
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            payload = None
        if isinstance(payload, dict) and payload.get("ok") is False:
            _write_rejection(rejection_path, attempt_id, "telegram_api_rejected", payload.get("error_code"))
            raise RuntimeError("Telegram explicitly rejected the photo; safe retry recorded") from None
        write_json_atomic(unconfirmed_path, {
            "status": "unconfirmed",
            "attempt_id": attempt_id,
            "http_status": int(exc.code),
            "reason": "HTTP response did not contain an explicit Telegram rejection",
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        })
        raise RuntimeError("Telegram photo result is ambiguous; automatic resend is blocked") from None
    except Exception:
        write_json_atomic(unconfirmed_path, {
            "status": "unconfirmed",
            "attempt_id": attempt_id,
            "reason": "No authoritative Telegram response received",
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        })
        raise RuntimeError("Telegram photo result is ambiguous; automatic resend is blocked") from None

    if isinstance(payload, dict) and payload.get("ok") is False:
        _write_rejection(rejection_path, attempt_id, "telegram_api_rejected", payload.get("error_code"))
        raise RuntimeError("Telegram explicitly rejected the photo; safe retry recorded")
    message = (payload.get("result") or {}) if isinstance(payload, dict) else {}
    target = message.get("chat") or {}
    message_id = message.get("message_id")
    photos = message.get("photo")
    recipient_matches = _matches_recipient(target, chat_id)
    valid_receipt = (
        response_status == 200
        and payload.get("ok") is True
        and type(message_id) is int and message_id > 0
        and recipient_matches
        and isinstance(photos, list) and bool(photos)
    )
    if not valid_receipt:
        write_json_atomic(unconfirmed_path, {
            "status": "unconfirmed",
            "attempt_id": attempt_id,
            "api_ok": payload.get("ok") if isinstance(payload, dict) else None,
            "message_id": message_id if type(message_id) is int else None,
            "chat_id_match": recipient_matches,
            "photo_sizes_returned": len(photos) if isinstance(photos, list) else 0,
            "http_status": response_status,
            "reason": "Telegram response did not satisfy the photo delivery receipt checks",
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        })
        raise RuntimeError("Telegram photo receipt is incomplete or mismatched; automatic resend is blocked")

    try:
        receipt = build_send_photo_receipt(
            payload, response_status, chat_id, photo_meta, guard, actual_bot
        )
    except Exception:
        write_json_atomic(unconfirmed_path, {
            "status": "unconfirmed",
            "attempt_id": attempt_id,
            "api_ok": payload.get("ok") if isinstance(payload, dict) else None,
            "message_id": message_id if type(message_id) is int else None,
            "chat_id_match": recipient_matches,
            "photo_sizes_returned": len(photos) if isinstance(photos, list) else 0,
            "http_status": response_status,
            "reason": "Telegram response did not satisfy the photo delivery receipt checks",
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        })
        raise RuntimeError("Telegram photo receipt is incomplete or mismatched; automatic resend is blocked") from None
    write_json_atomic(receipt_path, receipt)
    return receipt


def build_send_photo_receipt(payload: dict, response_status: int, chat_id: str,
                              photo_meta: dict, guard: dict, actual_bot: str) -> dict:
    if not isinstance(payload, dict) or payload.get("ok") is not True or response_status != 200:
        raise ValueError("Telegram did not confirm the photo")
    message = payload.get("result") or {}
    target = message.get("chat") or {}
    message_id = message.get("message_id")
    photos = message.get("photo")
    if type(message_id) is not int or message_id <= 0:
        raise ValueError("Telegram response has no valid message id")
    if not _matches_recipient(target, chat_id):
        raise ValueError("Telegram response chat does not match the configured recipient")
    if not isinstance(photos, list) or not photos or any(not isinstance(item, dict) for item in photos):
        raise ValueError("Telegram response has no photo sizes")
    largest = max(
        photos,
        key=lambda item: int(item.get("width") or 0) * int(item.get("height") or 0),
    )
    if type(largest.get("width")) is not int or type(largest.get("height")) is not int:
        raise ValueError("Telegram response has invalid photo dimensions")
    if largest["width"] <= 0 or largest["height"] <= 0:
        raise ValueError("Telegram response has empty photo dimensions")
    return {
        "status": "confirmed",
        "delivery_method": "sendPhoto",
        "attempt_id": guard["attempt_id"],
        "bot_username": actual_bot,
        "message_id": message_id,
        "message_count": 1,
        "chat_id_match": True,
        "photo_sizes_returned": len(photos),
        "telegram_photo_width": largest.get("width"),
        "telegram_photo_height": largest.get("height"),
        "image_width": photo_meta["width"],
        "image_height": photo_meta["height"],
        "image_bytes": photo_meta["bytes"],
        "image_sha256": photo_meta["sha256"],
        "alert_text_sha256": guard["alert_text_sha256"],
        "caption_sha256": guard["caption_sha256"],
        "confirmed_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def confirm_guard(guard_path: Path, receipt_path: Path):
    guard = read_json(guard_path)
    receipt = read_json(receipt_path)
    if not guard or not receipt or guard.get("status") != "unconfirmed":
        raise RuntimeError("Cannot confirm delivery without a matching pending attempt")
    if receipt.get("status") != "confirmed" or receipt.get("delivery_method") != "sendPhoto":
        raise RuntimeError("Only a confirmed Telegram sendPhoto receipt can complete the guard")
    if receipt.get("attempt_id") != guard.get("attempt_id"):
        raise RuntimeError("Telegram receipt attempt id does not match the persisted guard")
    if receipt.get("chat_id_match") is not True:
        raise RuntimeError("Telegram recipient was not confirmed")
    for field in (
        "image_sha256", "alert_text_sha256", "caption_sha256",
        "image_width", "image_height", "image_bytes",
    ):
        if receipt.get(field) != guard.get(field):
            raise RuntimeError(f"Telegram receipt {field} does not match the persisted attempt")
    if type(receipt.get("message_id")) is not int or receipt["message_id"] <= 0:
        raise RuntimeError("Telegram receipt has no valid message id")
    if type(receipt.get("photo_sizes_returned")) is not int or receipt["photo_sizes_returned"] < 1:
        raise RuntimeError("Telegram receipt has no returned photo size")
    guard.update({
        "status": "confirmed",
        "confirmed_at_utc": receipt["confirmed_at_utc"],
        "telegram_message_id": receipt["message_id"],
        "photo_sizes_returned": receipt["photo_sizes_returned"],
    })
    write_json_atomic(guard_path, guard)
    return guard


def mark_retry_safe(guard_path: Path, rejection_path: Path):
    guard = read_json(guard_path)
    rejection = read_json(rejection_path)
    if not guard or guard.get("status") != "unconfirmed" or not rejection:
        raise RuntimeError("Cannot clear delivery guard without a recorded safe rejection")
    allowed_rejections = {
        "telegram_api_rejected",
        "preflight_failed_no_photo_request",
        "bot_identity_mismatch_no_photo_request",
    }
    if (
        rejection.get("status") != "retry_safe"
        or rejection.get("attempt_id") != guard.get("attempt_id")
        or rejection.get("rejection_kind") not in allowed_rejections
    ):
        raise RuntimeError("Telegram rejection does not match the current delivery attempt")
    guard.update({
        "status": "retry_safe",
        "retry_safe_at_utc": rejection["recorded_at_utc"],
        "last_rejection_kind": rejection["rejection_kind"],
        "last_rejection_error_code": rejection.get("error_code"),
    })
    write_json_atomic(guard_path, guard)
    return guard


def guard_status_markdown(guard: dict | None) -> str:
    if not guard:
        return "# US Positioning Telegram Image\n\n- delivery_guard: clear\n"
    status = guard_status(guard)
    if status == "unconfirmed":
        return (
            "# US Positioning Telegram Image\n\n"
            "- delivery_guard: unconfirmed\n"
            f"- prior_attempt_id: {guard.get('attempt_id', 'unknown')}\n"
            f"- prior_run_id: {guard.get('run_id', 'unknown')}\n"
            f"- started_at_utc: {guard.get('attempted_at_utc', 'unknown')}\n"
            "- action: automatic sends are blocked until Telegram chat history is checked and the guard is reconciled\n"
        )
    return f"# US Positioning Telegram Image\n\n- delivery_guard: {status}\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    render = sub.add_parser("render")
    render.add_argument("--alert", type=Path, required=True)
    render.add_argument("--image", type=Path, required=True)

    check = sub.add_parser("check-guard")
    check.add_argument("--guard", type=Path, required=True)
    check.add_argument("--status", type=Path, required=True)

    attempt = sub.add_parser("prepare-attempt")
    attempt.add_argument("--alert", type=Path, required=True)
    attempt.add_argument("--image", type=Path, required=True)
    attempt.add_argument("--guard", type=Path, required=True)
    attempt.add_argument("--output", type=Path, required=True)
    attempt.add_argument("--run-id", required=True)
    attempt.add_argument("--head-sha", required=True)

    send = sub.add_parser("send-photo")
    send.add_argument("--alert", type=Path, required=True)
    send.add_argument("--image", type=Path, required=True)
    send.add_argument("--guard", type=Path, required=True)
    send.add_argument("--receipt", type=Path, required=True)
    send.add_argument("--rejection", type=Path, required=True)
    send.add_argument("--unconfirmed", type=Path, required=True)

    confirm = sub.add_parser("confirm-guard")
    confirm.add_argument("--guard", type=Path, required=True)
    confirm.add_argument("--receipt", type=Path, required=True)

    reject = sub.add_parser("mark-retry-safe")
    reject.add_argument("--guard", type=Path, required=True)
    reject.add_argument("--rejection", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.command == "render":
        result = render_alert_png(args.alert, args.image)
        print(
            f"telegram_photo_ready=true path={args.image.as_posix()} "
            f"dimensions={result['width']}x{result['height']} bytes={result['bytes']} "
            f"sha256={result['sha256']} alert_text_sha256={result['alert_text_sha256']}"
        )
    elif args.command == "check-guard":
        guard = read_json(args.guard, {})
        blocked = guard_blocks_send(guard)
        args.status.parent.mkdir(parents=True, exist_ok=True)
        args.status.write_text(guard_status_markdown(guard), encoding="utf-8")
        output = os.getenv("GITHUB_OUTPUT")
        if output:
            with open(output, "a", encoding="utf-8") as handle:
                handle.write(f"blocked={str(blocked).lower()}\n")
        summary = os.getenv("GITHUB_STEP_SUMMARY")
        if summary and blocked:
            with open(summary, "a", encoding="utf-8") as handle:
                handle.write(guard_status_markdown(guard))
        print(f"us_positioning_delivery_guard_blocked={str(blocked).lower()} status={guard_status(guard)}")
        if blocked:
            print("US positioning send skipped: prior Telegram photo delivery needs manual reconciliation")
    elif args.command == "prepare-attempt":
        result = prepare_attempt(
            args.alert, args.image, args.guard, args.output, args.run_id,
            args.head_sha, os.getenv("EXPECTED_TELEGRAM_BOT_USERNAME", ""),
            os.getenv("TELEGRAM_CHAT_ID", ""),
        )
        print(
            f"telegram_photo_attempt_prepared=true attempt_id={result['attempt_id']} "
            f"image_sha256={result['image_sha256']} dimensions={result['image_width']}x{result['image_height']}"
        )
    elif args.command == "send-photo":
        result = send_photo(
            args.alert, args.image, args.guard, args.receipt, args.rejection,
            args.unconfirmed, os.getenv("TELEGRAM_BOT_TOKEN", ""),
            os.getenv("TELEGRAM_CHAT_ID", ""), os.getenv("EXPECTED_TELEGRAM_BOT_USERNAME", ""),
        )
        print(
            f"telegram_delivery_confirmed=true method=sendPhoto "
            f"bot=@{result['bot_username']} messages=1 id={result['message_id']} "
            f"image_sha256={result['image_sha256']} dimensions={result['image_width']}x{result['image_height']}"
        )
    elif args.command == "confirm-guard":
        result = confirm_guard(args.guard, args.receipt)
        print(f"telegram_delivery_guard=confirmed attempt_id={result['attempt_id']}")
    elif args.command == "mark-retry-safe":
        result = mark_retry_safe(args.guard, args.rejection)
        print(
            f"telegram_delivery_guard=retry_safe attempt_id={result['attempt_id']} "
            f"reason={result['last_rejection_kind']}"
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"us_positioning_telegram_error={type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
