#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import re
import sys
from urllib.parse import urlsplit

SOURCE_PREFIX = "• 원문: "
TAG_RE = re.compile(r"^\[(신규병목|계약|개발|증권사|발사슬롯)\]")
ASCII_WORD_RE = re.compile(r"\b[A-Za-z][A-Za-z'-]*\b")
HANGUL_RE = re.compile(r"[가-힣]")
SOURCE_TOKEN_RE = re.compile(r"__SOURCE_URL_\d{4}__")


def clean_model_output(text: str) -> str:
    value = text.strip()
    fence = chr(96) * 3
    if value.startswith(fence) and value.endswith(fence):
        lines = value.splitlines()
        if lines and lines[0].startswith(fence):
            lines = lines[1:]
        if lines and lines[-1].strip() == fence:
            lines = lines[:-1]
        value = "\n".join(lines).strip()
    return value


def extract_source_urls(text: str) -> list[str]:
    urls: list[str] = []
    for line in text.splitlines():
        if line.startswith(SOURCE_PREFIX):
            url = line[len(SOURCE_PREFIX):].strip()
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(f"invalid source URL in report: {url!r}")
            urls.append(url)
    return urls


def prepare_for_translation(original: str) -> tuple[str, list[str]]:
    urls = extract_source_urls(original)
    prepared = original
    for index, url in enumerate(urls, start=1):
        prepared = prepared.replace(
            SOURCE_PREFIX + url,
            SOURCE_PREFIX + f"__SOURCE_URL_{index:04d}__",
            1,
        )
    return prepared, urls


def restore_source_urls(translated: str, urls: list[str]) -> str:
    restored = translated
    for index, url in enumerate(urls, start=1):
        token = f"__SOURCE_URL_{index:04d}__"
        if token not in restored:
            raise ValueError(f"source URL placeholder missing after translation: {token}")
        restored = restored.replace(token, url, 1)
    if SOURCE_TOKEN_RE.search(restored):
        raise ValueError("unexpected source URL placeholder remains")
    return restored


def tags(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if TAG_RE.match(line.strip())]


def validate_korean_translation(original: str, translated: str) -> None:
    if not translated.strip():
        raise ValueError("translation output is empty")

    if not translated.startswith("🚀 우주 발사 병목 웹감시"):
        raise ValueError("translated report header changed")

    original_urls = extract_source_urls(original)
    translated_urls = extract_source_urls(translated)
    if original_urls != translated_urls:
        raise ValueError("source URLs were changed, removed, or reordered during translation")

    original_tags = tags(original)
    translated_tags = tags(translated)
    if original_tags != translated_tags:
        raise ValueError("category tags or category names were changed during translation")

    for line in translated.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(SOURCE_PREFIX):
            continue
        if "출처:" in stripped:
            continue
        words = ASCII_WORD_RE.findall(stripped)
        if len(words) >= 4 and not HANGUL_RE.search(stripped):
            raise ValueError(f"untranslated English prose remains: {stripped!r}")

    lines = translated.splitlines()
    for index, line in enumerate(lines):
        if not TAG_RE.match(line.strip()):
            continue
        for candidate in lines[index + 1 :]:
            candidate = candidate.strip()
            if not candidate:
                continue
            if candidate.startswith("• "):
                title = candidate[2:].strip()
                if len(ASCII_WORD_RE.findall(title)) >= 4 and not HANGUL_RE.search(title):
                    raise ValueError(f"article title was not translated to Korean: {title!r}")
                break

    if chr(96) * 3 in translated:
        raise ValueError("markdown code fence found in translated report")


def main() -> int:
    if len(sys.argv) == 4 and sys.argv[1] == "--prepare":
        original_path = pathlib.Path(sys.argv[2])
        output_path = pathlib.Path(sys.argv[3])
        original = original_path.read_text(encoding="utf-8")
        prepared, _ = prepare_for_translation(original)
        output_path.write_text(prepared.rstrip() + "\n", encoding="utf-8")
        print("space_launch_translation_prepared=true")
        return 0

    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        original = (
            "🚀 우주 발사 병목 웹감시\n"
            "기준: 2026-10-07 18:23 KST\n\n"
            "[계약] Rocket Lab Electron·Neutron 발사 공급\n"
            "• How Investors May Respond To Rocket Lab Winning A Record Contract\n"
            "• 검증: 공식자료 | 출처: Rocket Lab\n"
            "• 원문: https://example.com/a?x=1&y=2\n"
        )
        translated = (
            "🚀 우주 발사 병목 웹감시\n"
            "기준: 2026-10-07 18:23 KST\n\n"
            "[계약] Rocket Lab Electron·Neutron 발사 공급\n"
            "• Rocket Lab의 기록적인 계약 체결에 투자자들이 어떻게 반응할 수 있는가\n"
            "• 검증: 공식자료 | 출처: Rocket Lab\n"
            "• 원문: __SOURCE_URL_0001__\n"
        )
        prepared, urls = prepare_for_translation(original)
        assert "__SOURCE_URL_0001__" in prepared
        restored = restore_source_urls(translated, urls)
        validate_korean_translation(original, restored)
        print("space_launch_korean_translation_self_test=ok")
        return 0

    if len(sys.argv) != 4:
        print(
            "usage: validate_space_launch_korean.py ORIGINAL TRANSLATED DESTINATION | --prepare ORIGINAL OUTPUT | --self-test",
            file=sys.stderr,
        )
        return 2

    original_path = pathlib.Path(sys.argv[1])
    translated_path = pathlib.Path(sys.argv[2])
    destination_path = pathlib.Path(sys.argv[3])

    original = original_path.read_text(encoding="utf-8")
    translated = clean_model_output(translated_path.read_text(encoding="utf-8"))
    urls = extract_source_urls(original)
    if SOURCE_TOKEN_RE.search(translated):
        translated = restore_source_urls(translated, urls)
    validate_korean_translation(original, translated)

    destination_path.write_text(translated.rstrip() + "\n", encoding="utf-8")
    print("space_launch_korean_translation_validated=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
