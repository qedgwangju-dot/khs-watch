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
import re
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
    parsed = parse_alert_fragment(fragment)
    report = _split_visual_report(parsed["visible_text"])
    header_date = _report_date(report)
    summary_cards = _render_summary_cards(report["summary"])
    sections = _render_report_sections(report["sections"])
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; background: #f1f5fa; }}
body {{
  width: {VIEWPORT_WIDTH}px;
  padding: 0 0 24px;
  color: #17243a;
  font-family: "Noto Sans CJK KR", "Malgun Gothic", "Apple SD Gothic Neo", sans-serif;
}}
main {{
  width: 1200px;
  margin: 0 auto;
  overflow: hidden;
  background: #f1f5fa;
}}
.report-header {{ padding: 32px 44px 24px; color: #fff; background: #142844; }}
.eyebrow {{ color: #b8cbe3; font-size: 16px; font-weight: 700; letter-spacing: .08em; }}
h1 {{ margin: 7px 0 4px; font-size: 38px; line-height: 1.2; font-weight: 800; }}
.report-date {{ color: #cad8e9; font-size: 20px; }}
.header-pills {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 24px; }}
.header-pill {{ padding: 13px 18px; border-radius: 13px; color: #17304d; background: #e5edf7; font-size: 21px; font-weight: 750; }}
.header-pill.warn {{ color: #81450b; background: #ffe5c8; }}
.content {{ padding: 22px 34px 28px; }}
.block-title {{ margin: 0 0 14px; font-size: 25px; font-weight: 800; color: #142844; }}
.summary-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-bottom: 18px; }}
.summary-card {{ min-height: 94px; padding: 15px 18px; border: 1px solid #e5eaf1; border-radius: 15px; background: #fff; box-shadow: 0 3px 10px rgba(25, 45, 70, .045); }}
.summary-label {{ margin-bottom: 6px; color: #59708c; font-size: 17px; font-weight: 700; }}
.summary-value {{ color: #182a43; font-size: 21px; line-height: 1.35; font-weight: 750; overflow-wrap: anywhere; }}
.summary-extra {{ margin-top: 7px; color: #60758c; font-size: 13px; line-height: 1.4; }}
.section-card {{ margin-top: 15px; padding: 19px 20px 16px; border: 1px solid #e3eaf2; border-radius: 17px; background: #fff; box-shadow: 0 3px 10px rgba(25, 45, 70, .045); }}
.section-head {{ display: flex; align-items: center; justify-content: space-between; gap: 14px; margin-bottom: 16px; }}
.section-head h2 {{ margin: 0; color: #142844; font-size: 25px; line-height: 1.28; }}
.section-tag {{ flex: 0 0 auto; padding: 8px 13px; border-radius: 10px; background: #eaf0f7; color: #355271; font-size: 15px; font-weight: 750; }}
.asset-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 11px; }}
.asset-card {{ padding: 15px 15px 13px; border: 1px solid #e6ecf3; border-radius: 14px; background: #fbfcfe; }}
.asset-title {{ margin: 0 0 10px; color: #1b2d45; font-size: 18px; line-height: 1.35; font-weight: 800; }}
.chart-caption {{ margin: 0 0 5px; color: #718198; font-size: 12px; font-weight: 700; }}
.return-chart {{ display: grid; grid-template-columns: 1fr; row-gap: 6px; margin: 6px 0 10px; }}
.return-row {{ display: grid; grid-template-columns: 33px minmax(65px, 1fr) 62px; align-items: center; gap: 6px; font-size: 12px; }}
.return-label {{ color: #5c7087; font-weight: 700; }}
.bar-track {{ position: relative; height: 11px; border-radius: 7px; background: #edf1f6; }}
.bar-track:after {{ position: absolute; top: -3px; bottom: -3px; left: 50%; width: 2px; content: ""; background: #9aaabd; }}
.bar {{ position: absolute; top: 0; height: 11px; border-radius: 7px; }}
.bar.pos {{ left: 50%; background: #25846a; }}
.bar.neg {{ right: 50%; background: #c9515a; }}
.bar-value {{ text-align: right; color: #344860; font-variant-numeric: tabular-nums; font-weight: 750; }}
.pending-chart {{ padding: 12px; border-radius: 10px; background: #f1f4f8; color: #697b90; font-size: 15px; font-weight: 700; }}
.data-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin: 9px 0 12px; }}
.data-card {{ padding: 14px 15px; border-radius: 12px; background: #f5f8fc; }}
.data-label {{ color: #62768e; font-size: 15px; font-weight: 700; }}
.positive {{ color: #14785d; }} .negative {{ color: #b53e4e; }} .neutral {{ color: #3a5e83; }}
.rows {{ display: grid; gap: 7px; margin-top: 10px; }}
.report-row {{ padding: 9px 12px; border-radius: 9px; background: #f7f9fc; color: #3c4f67; font-size: 15px; line-height: 1.42; overflow-wrap: anywhere; }}
.report-row.note {{ background: #eef3f8; color: #5f7084; font-size: 13px; }}
.report-row.emphasis {{ color: #1b2d45; font-weight: 700; }}
.options-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 8px 0 14px; }}
.option-card {{ padding: 14px 16px; border: 1px solid #e5ebf2; border-radius: 12px; background: #f7f9fc; }}
.option-label {{ color: #60758e; font-size: 15px; font-weight: 700; }}
.option-value {{ margin: 4px 0 9px; color: #1b2d45; font-size: 27px; font-weight: 800; font-variant-numeric: tabular-nums; }}
.option-track {{ position: relative; height: 9px; border-radius: 6px; background: #e6edf5; }}
.option-track:after {{ position: absolute; left: 50%; top: -3px; bottom: -3px; width: 2px; content: ""; background: #526c88; }}
.option-dot {{ position: absolute; top: 0; width: 9px; height: 9px; border-radius: 50%; background: #356b9f; }}
.turnover-hero {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 8px 0 13px; }}
.hero-card {{ padding: 16px 18px; border-radius: 13px; background: #f4f7fb; }}
.hero-label {{ color: #667b94; font-size: 14px; font-weight: 700; }}
.hero-value {{ margin-top: 4px; color: #172a43; font-size: 25px; line-height: 1.25; font-weight: 800; font-variant-numeric: tabular-nums; }}
.period-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 11px; margin: 10px 0 12px; }}
.period-card {{ padding: 14px 15px; border: 1px solid #e4eaf2; border-radius: 12px; background: #fff; }}
.period-title {{ color: #62758d; font-size: 14px; font-weight: 750; }}
.period-value {{ margin: 4px 0 8px; font-size: 24px; line-height: 1.2; font-weight: 850; font-variant-numeric: tabular-nums; }}
.period-amount {{ color: #344860; font-size: 13px; line-height: 1.45; font-weight: 650; }}
.period-dates {{ margin-top: 6px; color: #75849a; font-size: 11px; line-height: 1.35; }}
.futures-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }}
.futures-card {{ padding: 14px 16px; border: 1px solid #e5ebf2; border-radius: 12px; background: #f8fafc; }}
.futures-title {{ color: #667b94; font-size: 14px; font-weight: 750; }}
.futures-value {{ margin-top: 5px; color: #1b2d45; font-size: 17px; line-height: 1.42; font-weight: 750; }}
.futures-detail {{ margin-top: 5px; color: #5e7087; font-size: 13px; line-height: 1.42; }}
.breadth-card {{ margin: 9px 0 12px; padding: 15px 17px; border-radius: 12px; background: #f5f8fc; }}
.breadth-title {{ margin-bottom: 5px; color: #647991; font-size: 14px; font-weight: 750; }}
.breadth-values {{ color: #19304c; font-size: 20px; font-weight: 800; }}
.metric-pair {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 10px 0; }}
.metric-pair .data-card {{ min-width: 0; }}
.footer-note {{ margin-top: 17px; padding: 14px 16px; border-radius: 12px; background: #e8eef6; color: #52667f; font-size: 13px; line-height: 1.45; }}
.source-link {{ margin-top: 16px; color: #1c5f99; font-size: 16px; font-weight: 750; }}
</style>
</head>
<body><main>
  <header class="report-header">
    <div class="eyebrow">미국 시장 포지셔닝 · {html.escape(report['edition'] or '일일 요약')}</div>
    <h1>{html.escape(report['title'])}</h1>
    <div class="report-date">{html.escape(header_date or '확정 자료 기준일은 본문 참고')}</div>
    {report['header_pills']}
  </header>
  <div class="content">
    <div class="block-title">한눈에 보기</div>
    {summary_cards}
    {sections}
    <div class="footer-note">수치의 단위·기준일·환산 가정은 각 카드의 주석을 따릅니다. 선물 계약·거래활동·옵션 비율은 실제 현금 유입·유출이나 가격 방향을 단독으로 확정하지 않습니다.</div>
    <div class="source-link">상세 수치 · 계산 · 원문은 Telegram 캡션 링크에서 확인</div>
  </div>
</main></body>
</html>"""


def _split_visual_report(visible_text: str) -> dict:
    lines = [line.strip() for line in visible_text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("US positioning visual report has no visible text")
    title_parts = lines[0].replace("🇺🇸", "").strip().split("|", 1)
    report = {
        "title": title_parts[0].strip(),
        "edition": title_parts[1].strip() if len(title_parts) > 1 else "",
        "summary": [],
        "sections": [],
        "header_pills": [],
    }
    current = None
    in_summary = False
    for line in lines[1:]:
        if line == "한눈에 보기":
            in_summary = True
            current = None
            continue
        match = re.match(r"^([①②③④])\s*(.+)$", line)
        if match:
            in_summary = False
            current = {"marker": match.group(1), "title": match.group(2), "lines": []}
            report["sections"].append(current)
            continue
        if current is not None:
            current["lines"].append(line)
        elif in_summary:
            report["summary"].append(line)
    if not report["sections"]:
        raise ValueError("US positioning image requires its four numbered report sections")
    report["header_pills"] = _render_header_pills(report["sections"])
    return report


def _report_date(report: dict) -> str | None:
    for section in report["sections"]:
        match = re.search(r"20\d{2}-\d{2}-\d{2}", section["title"])
        if match:
            return f"{match.group(0)} · 시장 종가 및 주간 기준은 항목별 표기"
    return None


def _plain_line(line: str) -> str:
    return re.sub(r"^[•→]\s*", "", line).strip()


def _render_header_pills(sections: list[dict]) -> str:
    overview = next((line for line in sections[0]["lines"] if line.startswith(("🔴", "🟡", "🟢", "⚪"))), "")
    if not overview:
        overview = "자료별 확인 상태는 각 항목에 표시"
    status = "확인 대기" if "확인 대기" in overview else "기간별 방향 혼재" if "혼재" in overview else "방향 참고"
    tone = "warn" if "대기" in status or "혼재" in status else ""
    return (
        '<div class="header-pills">'
        f'<div class="header-pill {tone}">{html.escape(status)}</div>'
        f'<div class="header-pill">{html.escape(_plain_line(overview).replace("🔴", "").replace("🟡", "").replace("🟢", "").replace("⚪", "").strip())}</div>'
        "</div>"
    )


def _summary_parts(line: str) -> tuple[str, str]:
    text = _plain_line(line)
    if ":" in text:
        return tuple(part.strip() for part in text.split(":", 1))
    words = text.split(" ", 2)
    return (" ".join(words[:2]), words[2] if len(words) > 2 else text)


def _render_summary_cards(lines: list[str]) -> str:
    cards = []
    highlights = ("반도체(SOX):", "통합 기관:", "통합 헤지펀드성:", "NQ E-mini:")
    for index, line in enumerate(lines):
        if not line.startswith("•") or not any(_plain_line(line).startswith(item) for item in highlights):
            continue
        label, value = _summary_parts(line)
        if not label or not value:
            continue
        extra = ""
        if label == "NQ E-mini" and index + 1 < len(lines) and "백분위" in lines[index + 1]:
            extra = _plain_line(lines[index + 1])
        cards.append(
            '<div class="summary-card">'
            f'<div class="summary-label">{html.escape(label)}</div>'
            f'<div class="summary-value">{html.escape(value)}</div>'
            f'<div class="summary-extra">{html.escape(extra)}</div>'
            "</div>"
        )
    if not cards:
        raise ValueError("US positioning visual report has no summary metrics")
    return '<div class="summary-grid">' + "".join(cards) + "</div>"


def _asset_blocks(lines: list[str]) -> list[dict]:
    labels = ("SOX", "나스닥100", "S&P500")
    blocks = []
    current = None
    for line in lines:
        text = _plain_line(line)
        label = None
        if text.startswith("SOX ") and "현재 추세" not in text:
            label = "SOX"
        elif text.startswith("나스닥100 ") and "추세" not in text:
            label = "나스닥100"
        elif text.startswith("S&P500 종가"):
            label = "S&P500"
        if label is not None:
            if current is None or current["label"] != label:
                current = {"label": label, "lines": []}
                blocks.append(current)
        if current is not None:
            current["lines"].append(line)
    return blocks


def _asset_returns(lines: list[str]) -> list[tuple[str, float]]:
    found = []
    aliases = {"1거래일": "1D", "3거래일": "3D", "5거래일": "5D", "1일": "1D", "3일": "3D", "5일": "5D"}
    for line in lines:
        for label, value in re.findall(r"(?<!\d)(1거래일|3거래일|5거래일|1일|3일|5일)\s*([+-]?\d+(?:\.\d+)?)%", line):
            pair = (aliases[label], float(value))
            if pair[0] not in [item[0] for item in found]:
                found.append(pair)
        for label, value in re.findall(r"(?<!\d)(1개월|3개월)\s*(?:전\s*대비\s*:?\s*)?([+-]?\d+(?:\.\d+)?)%", line):
            pair = ("1M" if label == "1개월" else "3M", float(value))
            if pair[0] not in [item[0] for item in found]:
                found.append(pair)
    order = {"1D": 0, "3D": 1, "5D": 2, "1M": 3, "3M": 4}
    return sorted(found, key=lambda item: order[item[0]])


def _render_return_chart(lines: list[str]) -> str:
    values = _asset_returns(lines)
    if not values:
        pending = next((html.escape(_plain_line(line)) for line in lines[1:] if "확인 대기" in line), "검증된 수익률이 없습니다.")
        return f'<div class="pending-chart">{pending}</div>'
    scale = max(5.0, min(50.0, float(((max(abs(value) for _, value in values) + 4.999) // 5) * 5)))
    rows = []
    for label, value in values:
        width = min(50.0, abs(value) / scale * 50.0)
        sign_class = "pos" if value > 0 else "neg" if value < 0 else "pos"
        color_class = "positive" if value > 0 else "negative" if value < 0 else "neutral"
        rows.append(
            '<div class="return-row">'
            f'<span class="return-label">{label}</span>'
            f'<div class="bar-track"><i class="bar {sign_class}" style="width:{width:.2f}%"></i></div>'
            f'<span class="bar-value {color_class}">{value:+.2f}%</span>'
            "</div>"
        )
    return '<div class="chart-caption">기간별 수익률 · 0% 기준</div><div class="return-chart">' + "".join(rows) + "</div>"


def _render_price_assets(section: dict) -> str:
    blocks = _asset_blocks(section["lines"])
    cards = []
    for block in blocks:
        lines = block["lines"]
        title = _plain_line(lines[0])
        chart = _render_return_chart(lines)
        details = [
            line for line in lines[1:]
            if any(key in _plain_line(line) for key in ("현재 추세", "20일 평균", "60일 평균", "종가고점", "제공처 종가 불일치", "이력·제공처 검산 미완료"))
        ]
        cards.append(
            '<div class="asset-card">'
            f'<div class="asset-title">{html.escape(title)}</div>'
            f'{chart}'
            f'{_render_rows(details, note=True)}'
            "</div>"
        )
    lead = next((line for line in section["lines"] if line.startswith(("🔴", "🟡", "🟢", "⚪"))), "")
    result = f'<div class="section-tag">{html.escape(_plain_line(lead))}</div>' if lead else ""
    if cards:
        result += '<div class="asset-grid">' + "".join(cards) + "</div>"
    notes = [line for line in section["lines"] if _plain_line(line).startswith("※")]
    result += _render_rows(notes, note=True)
    return result


def _render_turnover(section: dict) -> str:
    lines = [_plain_line(line) for line in section["lines"]]
    daily = next((line for line in lines if " 당일 " in line), "")
    change = next((line for line in lines if line.startswith("전일 대비")), "")
    daily_value = daily.split("당일", 1)[1].strip() if "당일" in daily else "공식 총액 확인 대기"
    change_value = change.removeprefix("전일 대비").strip() if change else "공식 비교값 확인 대기"
    result = (
        '<div class="turnover-hero">'
        f'<div class="hero-card"><div class="hero-label">당일 전체 거래대금 · {html.escape(daily.split(" 당일", 1)[0] if " 당일" in daily else "")}</div>'
        f'<div class="hero-value">{html.escape(daily_value)}</div></div>'
        f'<div class="hero-card"><div class="hero-label">전일 대비</div><div class="hero-value">{html.escape(change_value)}</div></div>'
        '</div>'
    )
    date_lines = [line for line in lines if line.startswith("직전") and "→ 최근" in line]
    periods = []
    for line in lines:
        match = re.match(r"(5거래일|1개월|3개월)\s+[↑↓]\s+[^ ]+\s+([+-]\d+(?:\.\d+)?)%:\s*(.*?)\s*→\s*(.*)$", line)
        if not match:
            continue
        label, percentage, before, after = match.groups()
        value = float(percentage)
        period_label = {"5거래일": "5D 일평균", "1개월": "1M 일평균", "3개월": "3M 일평균"}[label]
        result_amounts = f"{before.strip()} → {after.strip()}"
        date_index = len(periods)
        dates = date_lines[date_index].removeprefix("직전").strip() if date_index < len(date_lines) else ""
        periods.append((period_label, value, result_amounts, dates))
    period_cards = []
    for label, value, amounts, dates in periods:
        tone = "positive" if value > 0 else "negative" if value < 0 else "neutral"
        period_cards.append(
            '<div class="period-card">'
            f'<div class="period-title">{html.escape(label)}</div>'
            f'<div class="period-value {tone}">{value:+.2f}%</div>'
            f'<div class="period-amount">{html.escape(amounts)}</div>'
            f'<div class="period-dates">{html.escape(dates)}</div>'
            '</div>'
        )
    if period_cards:
        result += '<div class="chart-caption">기간별 일평균 거래대금 변화</div><div class="period-grid">' + "".join(period_cards) + '</div>'
    notes = [line for line in lines if line.startswith("※")]
    return result + _render_rows(notes, note=True)


def _futures_card(title: str, value: str, detail: str = "") -> str:
    return (
        '<div class="futures-card">'
        f'<div class="futures-title">{html.escape(title)}</div>'
        f'<div class="futures-value">{html.escape(value)}</div>'
        f'<div class="futures-detail">{html.escape(detail)}</div>'
        '</div>'
    )


def _render_futures(section: dict) -> str:
    lines = [_plain_line(line) for line in section["lines"]]
    cards = []
    integrated = next((line for line in lines if line.startswith("나스닥100 통합:")), "")
    if integrated:
        cards.append(_futures_card(
            "통합 포지션 · 계약",
            integrated.split(":", 1)[1].strip(),
            "이 요약에 상품별 구성·승수 근거가 없어 KRW 액면 환산은 확인 불가",
        ))
    current = next((line for line in lines if line.startswith("현재 ") and "계약" in line), "")
    if current:
        amount = next((line for line in lines if line.startswith("※ 참고금액:")), "")
        cards.append(_futures_card("NQ E-mini 현재 포지션", current, amount))
    period_specs = (("1주 전 대비:", "1W 변화"), ("1개월 비교:", "1M 변화"), ("3개월 비교:", "3M 변화"))
    for prefix, label in period_specs:
        for index, line in enumerate(lines):
            if not line.startswith(prefix):
                continue
            notional = lines[index + 1] if index + 1 < len(lines) and "동일가격 환산" in lines[index + 1] else ""
            cards.append(_futures_card(label + " · 계약 변화", line, notional))
            break
    result = '<div class="futures-grid">' + "".join(cards) + '</div>' if cards else ""
    notes = [line for line in lines if line.startswith("※")]
    return result + _render_rows(notes, note=True)


def _render_options(section: dict) -> str:
    lines = [_plain_line(line) for line in section["lines"]]
    ratio_line = next((line for line in lines if "옵션 P/C(" in line), "")
    ratios = re.search(r"주식\s+(\d+(?:\.\d+)?)\s*/\s*지수\s+(\d+(?:\.\d+)?)\s*/\s*전체\s+(\d+(?:\.\d+)?)", ratio_line)
    cards = []
    if ratios:
        for label, value in zip(("주식 P/C", "지수 P/C", "전체 P/C"), ratios.groups()):
            amount = float(value)
            dot = max(0.0, min(100.0, amount / 2.0 * 100.0))
            cards.append(
                '<div class="option-card">'
                f'<div class="option-label">{label}</div>'
                f'<div class="option-value">{amount:.2f}</div>'
                f'<div class="option-track"><i class="option-dot" style="left:calc({dot:.1f}% - 5px)"></i></div>'
                "</div>"
            )
    ratio_markup = '<div class="options-grid">' + "".join(cards) + "</div>" if cards else ""
    breadth = next((line for line in lines if line.startswith("동일가중 RSP")), "")
    volume = next((line for line in lines if "옵션 전체 거래량" in line), "")
    history = [line for line in lines if line.startswith("주식 P/C 과거")]
    extra_cards = []
    if breadth:
        extra_cards.append(("ETF 상대수익률 차이", breadth.split(":", 1)[1].strip()))
    if volume:
        extra_cards.append(("옵션 거래량", volume.split(":", 1)[1].strip()))
    for index, line in enumerate(history, start=1):
        label = "P/C 과거 1개월" if "1개월" in line else "P/C 과거 3개월" if "3개월" in line else f"P/C 이력 {index}"
        extra_cards.append((label, line.split(":", 1)[1].strip()))
    extra_markup = ""
    for title, value in extra_cards:
        extra_markup += (
            '<div class="data-card">'
            f'<div class="data-label">{html.escape(title)}</div>'
            f'<div class="futures-value">{html.escape(value)}</div>'
            '</div>'
        )
    if extra_cards:
        extra_markup = '<div class="data-grid">' + extra_markup + '</div>'
    notes = [line for line in lines if line.startswith("※")]
    return ratio_markup + extra_markup + _render_rows(notes, note=True)


def _render_rows(lines: list[str], note: bool = False) -> str:
    rows = []
    for line in lines:
        text = _plain_line(line)
        if not text:
            continue
        is_note = note or text.startswith("※")
        cls = "note" if is_note else "emphasis" if text.startswith(("→", "⚠")) else ""
        rows.append(f'<div class="report-row {cls}">{html.escape(text)}</div>')
    return '<div class="rows">' + "".join(rows) + "</div>" if rows else ""


def _render_report_sections(sections: list[dict]) -> str:
    rendered = []
    for section in sections:
        marker = section["marker"]
        if marker == "①":
            body = _render_price_assets(section)
        elif marker == "②":
            body = _render_turnover(section)
        elif marker == "③":
            body = _render_futures(section)
        else:
            body = _render_options(section)
        rendered.append(
            '<section class="section-card">'
            '<div class="section-head">'
            f'<h2>{html.escape(marker + " " + section["title"])}</h2>'
            f'<span class="section-tag">{("기간별 비교" if marker == "①" else "검증값" if marker == "②" else "계약 수 · 명목 참고" if marker == "③" else "거래량 비율")}</span>'
            "</div>"
            f'{body}'
            "</section>"
        )
    return "".join(rendered)


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


def _matches_recipient(target: object, chat_id: str) -> bool:
    if not isinstance(target, dict):
        return False
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
    if not isinstance(message, dict):
        message = {}
    target = message.get("chat") or {}
    if not isinstance(target, dict):
        target = {}
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
    message = payload.get("result")
    if not isinstance(message, dict):
        raise ValueError("Telegram response has no message object")
    target = message.get("chat")
    if not isinstance(target, dict):
        raise ValueError("Telegram response has no chat object")
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
