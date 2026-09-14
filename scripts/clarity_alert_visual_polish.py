#!/usr/bin/env python3
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "out"
OUT_HTML = OUT_DIR / "clarity_watch_alert.html"
OUT_CHUNKS = OUT_DIR / "clarity_watch_telegram_chunks.json"

HEADER = "<b>🔔 CLARITY 법안 Watch — 표결·규제·BTC/COIN/Circle 영향</b>"
POLISHED_HEADER = (
    "<b>🔔 CLARITY 법안 Watch</b>\n"
    "<i>표결·규제·BTC/COIN/Circle 영향</i>\n"
    "━━━━━━━━━━━━━━━━━━"
)

AXES = (
    ("돈 버는 능력", "💵"),
    ("할인율", "📉"),
    ("수급", "🌊"),
    ("시간표", "⏱"),
)


def polish_chunk(text):
    text = str(text or "")
    if not text:
        return text

    text = text.replace(HEADER, POLISHED_HEADER)
    text = text.replace("<b>한눈에 보기</b>", "<b>👀 한눈에 보기</b>")

    # Separate each event visually without deleting any substantive text.
    text = re.sub(
        r"(?m)^<b>(\d+)\. ",
        r"━━━━━━━━━━━━━━━━━━\n<b>\1. ",
        text,
    )

    # The overview already has a one-line four-axis snapshot; label it explicitly.
    text = re.sub(
        r"(?m)^  ↳ (.+)$",
        r"  ↳ <b>4축</b> \1",
        text,
    )

    # Make the four investment axes instantly scannable while preserving the explanation.
    for label, emoji in AXES:
        text = re.sub(
            rf"(?m)^• {re.escape(label)}(?=\s|→|↑|↓|△)",
            f"• {emoji} <b>{label}</b>",
            text,
        )

    text = text.replace("검증 근거:", "<b>검증 근거</b>:")
    text = re.sub(r'(?m)^(<a href="[^"]+">원문</a>)$', r'🔗 \1', text)

    text = text.replace(
        "<b>📊 시장 반응·원인 분리</b>",
        "━━━━━━━━━━━━━━━━━━\n📊 <b>시장 반응·원인 분리</b>",
    )
    text = text.replace(
        "<b>핵심 한 줄 요약</b>",
        "🎯 <b>핵심 한 줄 요약</b>",
    )

    # Keep certainty buckets visually distinct. Content itself is untouched.
    text = text.replace("<b>✅ 확인된 사실</b>", "✅ <b>확인된 사실</b>")
    text = text.replace("<b>⚠️ 아직 미확정</b>", "⚠️ <b>아직 미확정</b>")
    text = text.replace("<b>⏱ 다음 확인</b>", "⏱ <b>다음 확인</b>")
    text = text.replace("<b>🔎 근거</b>", "🔎 <b>근거</b>")
    text = text.replace("<b>🧭 무엇이 달라졌나</b>", "🧭 <b>무엇이 달라졌나</b>")
    text = text.replace("<b>📍 현재 판정</b>", "📍 <b>현재 판정</b>")
    text = text.replace("<b>💰 투자 의미</b>", "💰 <b>투자 의미</b>")
    return text


def main():
    if not OUT_CHUNKS.exists():
        print("clarity_visual_polish=false reason=no_chunks")
        return

    chunks = json.loads(OUT_CHUNKS.read_text(encoding="utf-8"))
    polished = [polish_chunk(chunk) for chunk in chunks]
    OUT_CHUNKS.write_text(json.dumps(polished, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUT_HTML.write_text("\n\n".join(polished) + "\n", encoding="utf-8")
    print(f"clarity_visual_polish=true chunks={len(polished)}")


if __name__ == "__main__":
    main()
