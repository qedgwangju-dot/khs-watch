#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import pathlib
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HANGUL_RE = re.compile(r"[가-힣]")
ASCII_WORD_RE = re.compile(r"\b[A-Za-z][A-Za-z'-]*\b")
SOURCE_PREFIX = "• 원문: "

IDENTIFIERS = (
    "Morgan Stanley",
    "Yahoo Finance",
    "Hyundai Rotem",
    "Open Cosmos",
    "Rocket Lab",
    "Adam Jonas",
    "Synspective",
    "DIGITIMES",
    "SpaceNews",
    "Starlink",
    "Starship",
    "Electron",
    "Neutron",
    "SpaceX",
    "CNBC",
    "Reuters",
    "FAA",
    "RKLB",
    "ZBO",
)

RETRYABLE_HTTP = {429, 500, 502, 503, 504}


def request_json(url: str, timeout: int = 20, attempts: int = 3) -> dict | list:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; khs-space-launch-translate/1.0)",
                "Accept": "application/json,text/plain,*/*",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
            return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in RETRYABLE_HTTP or attempt >= attempts:
                raise
            retry_after = exc.headers.get("Retry-After")
            try:
                delay = int(retry_after) if retry_after else 2 ** (attempt - 1)
            except ValueError:
                delay = 2 ** (attempt - 1)
            time.sleep(max(1, min(delay, 10)))
        except (urllib.error.URLError, socket.timeout, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt >= attempts:
                raise
            time.sleep(min(2 ** (attempt - 1), 8))
    if last_error:
        raise last_error
    raise RuntimeError("translation request failed without an exception")


def protect_identifiers(text: str) -> tuple[str, dict[str, str]]:
    protected = text
    mapping: dict[str, str] = {}

    dynamic = set(IDENTIFIERS)
    dynamic.update(re.findall(r"\$?[A-Z][A-Z0-9.-]{1,9}\b", text))

    for index, identifier in enumerate(sorted(dynamic, key=len, reverse=True), start=1):
        if identifier not in protected:
            continue
        token = f"ZXQID{index:04d}QXZ"
        protected = protected.replace(identifier, token)
        mapping[token] = identifier

    return protected, mapping


def restore_identifiers(text: str, mapping: dict[str, str]) -> str:
    restored = text
    for token, identifier in mapping.items():
        restored = re.sub(re.escape(token), identifier, restored, flags=re.I)
    return restored


def google_translate(text: str) -> str:
    params = urllib.parse.urlencode(
        {
            "client": "gtx",
            "sl": "en",
            "tl": "ko",
            "dt": "t",
            "q": text,
        }
    )
    data = request_json("https://translate.googleapis.com/translate_a/single?" + params)
    if not isinstance(data, list) or not data or not isinstance(data[0], list):
        raise RuntimeError("unexpected Google translation response")
    parts: list[str] = []
    for row in data[0]:
        if isinstance(row, list) and row and isinstance(row[0], str):
            parts.append(row[0])
    translated = "".join(parts).strip()
    if not translated:
        raise RuntimeError("empty Google translation")
    return translated


def mymemory_translate(text: str) -> str:
    params = urllib.parse.urlencode({"q": text, "langpair": "en|ko"})
    data = request_json("https://api.mymemory.translated.net/get?" + params)
    if not isinstance(data, dict):
        raise RuntimeError("unexpected MyMemory response")
    response_data = data.get("responseData")
    if not isinstance(response_data, dict):
        raise RuntimeError("missing MyMemory responseData")
    translated = html.unescape(str(response_data.get("translatedText") or "")).strip()
    if not translated:
        raise RuntimeError("empty MyMemory translation")
    return translated


def translate_english_text(text: str) -> str:
    protected, mapping = protect_identifiers(text)
    errors: list[str] = []

    for provider in (google_translate, mymemory_translate):
        try:
            translated = provider(protected)
            translated = restore_identifiers(translated, mapping)
            if translated and (HANGUL_RE.search(translated) or len(ASCII_WORD_RE.findall(text)) < 4):
                return translated
            errors.append(f"{provider.__name__}: no Korean text in result")
        except Exception as exc:
            errors.append(f"{provider.__name__}: {type(exc).__name__}: {exc}")

    raise RuntimeError("all translation providers failed: " + " | ".join(errors))


def needs_translation(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith(SOURCE_PREFIX):
        return False
    if "출처:" in stripped:
        return False
    if HANGUL_RE.search(stripped):
        return False
    return len(ASCII_WORD_RE.findall(stripped)) >= 4


def translate_report(text: str, translate_fn=translate_english_text) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        if not needs_translation(line):
            lines.append(line)
            continue

        prefix = ""
        body = line
        if line.startswith("• "):
            prefix = "• "
            body = line[2:]

        translated = translate_fn(body).strip()
        if not HANGUL_RE.search(translated):
            raise RuntimeError(f"translation did not produce Korean text: {body!r}")
        lines.append(prefix + translated)

    return "\n".join(lines).rstrip() + "\n"


def self_test() -> int:
    sample = (
        "🚀 우주 발사 병목 웹감시\n"
        "기준: 2026-10-07 18:23 KST\n\n"
        "[계약] Rocket Lab Electron·Neutron 발사 공급\n"
        "• How Investors May Respond To Rocket Lab Winning Synspective's Record 20-Launch Electron Contract - Yahoo Finance\n"
        "• 검증: 복수 신뢰보도 교차확인 | 출처: Yahoo Finance | 2026-10-04 13:14 KST\n"
        "• 원문: https://example.com/a?x=1&y=2\n"
    )

    def fake_translate(value: str) -> str:
        assert "Rocket Lab" in value
        return "Rocket Lab의 Synspective 기록적인 Electron 20회 발사 계약에 투자자들이 어떻게 반응할 수 있는가 - Yahoo Finance"

    output = translate_report(sample, fake_translate)
    assert "투자자들이 어떻게 반응할 수 있는가" in output
    assert "https://example.com/a?x=1&y=2" in output
    assert "출처: Yahoo Finance" in output
    print("space_launch_local_translation_self_test=ok")
    return 0


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        return self_test()

    if len(sys.argv) != 3:
        print("usage: space_launch_translate_local.py INPUT OUTPUT | --self-test", file=sys.stderr)
        return 2

    input_path = pathlib.Path(sys.argv[1])
    output_path = pathlib.Path(sys.argv[2])
    text = input_path.read_text(encoding="utf-8")
    translated = translate_report(text)
    output_path.write_text(translated, encoding="utf-8")
    print("space_launch_local_translation_completed=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
