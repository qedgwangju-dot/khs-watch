#!/usr/bin/env python3
"""Parse the latest Japan MOF weekly securities flow PDF.

The fixed official `week.pdf` contains a narrative with the latest and previous-week
resident/outward figures. We parse that authoritative release. PDF text extraction
uses the runner's `pdftotext` when available and falls back to pypdf if installed.
MOF's post-2014 convention is preserved: acquisition excess = positive, disposition
excess = negative.
"""
from __future__ import annotations

import datetime as dt
import io
import re
import subprocess
import tempfile
from typing import Any

MOF_WEEK_PDF = "https://www.mof.go.jp/policy/international_policy/reference/itn_transactions_in_securities/week.pdf"


def extract_pdf_text(raw: bytes) -> str:
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
            tmp.write(raw)
            tmp.flush()
            proc = subprocess.run(
                ["pdftotext", "-layout", tmp.name, "-"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=20,
                check=False,
            )
        if proc.returncode == 0 and proc.stdout:
            return proc.stdout.decode("utf-8", errors="replace")
    except (FileNotFoundError, subprocess.SubprocessError):
        pass

    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:
        raise RuntimeError(f"MOF weekly PDF text extraction failed: {type(exc).__name__}: {exc}") from exc


def fnum_jpy_100m(raw: str, direction: str) -> float:
    text = (raw or "").replace(" ", "").replace(",", "")
    negative_mark = text.startswith(("▲", "△", "-", "−"))
    text = text.lstrip("▲△-−")
    cho = re.search(r"([0-9]+(?:\.[0-9]+)?)兆", text)
    oku = re.search(r"([0-9]+(?:\.[0-9]+)?)億", text)
    value = 0.0
    if cho:
        value += float(cho.group(1)) * 10_000.0
    if oku:
        value += float(oku.group(1))
    if not cho and not oku:
        number = re.search(r"([0-9]+(?:\.[0-9]+)?)", text)
        if not number:
            raise ValueError(f"yen amount not found: {raw}")
        value = float(number.group(1))
    direction_negative = "処分超" in direction or "売り越し" in direction
    return -abs(value) if negative_mark or direction_negative else abs(value)


def extract_category(section: str, category_pattern: str) -> tuple[float, float]:
    pattern = re.compile(
        rf"(?:{category_pattern}).{{0,180}}?([▲△\-−]?[0-9兆億,\.]+円)\s*の\s*(取得超|処分超)"
        rf".{{0,240}}?前週\s*([▲△\-−]?[0-9兆億,\.]+円)\s*の\s*(取得超|処分超)",
        re.S,
    )
    match = pattern.search(section)
    if not match:
        raise RuntimeError(f"MOF weekly PDF category parse failed: {category_pattern}")
    latest = fnum_jpy_100m(match.group(1), match.group(2))
    previous = fnum_jpy_100m(match.group(3), match.group(4))
    return latest, previous


def period_label(text: str) -> tuple[str, str]:
    match = re.search(
        r"令和\s*8\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*[～〜~\-]\s*(?:(\d{1,2})\s*月\s*)?(\d{1,2})\s*日\s*の対外",
        text,
    )
    if not match:
        return "最新週", "前週"
    start_month, start_day, end_month, end_day = match.groups()
    end_month = end_month or start_month
    try:
        start = dt.date(2026, int(start_month), int(start_day))
        end = dt.date(2026, int(end_month), int(end_day))
        prev_end = start - dt.timedelta(days=1)
        prev_start = prev_end - dt.timedelta(days=6)
        return f"{start.month}/{start.day}~{end.month}/{end.day}", f"{prev_start.month}/{prev_start.day}~{prev_end.month}/{prev_end.day}"
    except Exception:
        return "최신주", "전주"


def fetch_weekly_outward_flows(get_bytes) -> list[dict[str, Any]]:
    raw = get_bytes(MOF_WEEK_PDF)
    text = extract_pdf_text(raw)
    compact = re.sub(r"[\t\r ]+", " ", text)
    start = compact.find("１．対外証券投資")
    if start < 0:
        start = compact.find("1．対外証券投資")
    end = compact.find("２．対内証券投資", start + 1) if start >= 0 else -1
    if end < 0 and start >= 0:
        end = compact.find("2．対内証券投資", start + 1)
    if start < 0 or end < 0:
        raise RuntimeError("MOF weekly PDF outward narrative section not found")
    section = compact[start:end]

    eq_latest, eq_prev = extract_category(section, r"株式\s*[・･]\s*投資ファンド持分")
    lt_latest, lt_prev = extract_category(section, r"中長期債投資")
    latest_period, prev_period = period_label(compact)
    return [
        {
            "period": prev_period,
            "equity_net_100m_yen": eq_prev,
            "long_term_net_100m_yen": lt_prev,
            "equity_long_subtotal_100m_yen": eq_prev + lt_prev,
            "short_term_net_100m_yen": None,
            "total_net_100m_yen": None,
        },
        {
            "period": latest_period,
            "equity_net_100m_yen": eq_latest,
            "long_term_net_100m_yen": lt_latest,
            "equity_long_subtotal_100m_yen": eq_latest + lt_latest,
            "short_term_net_100m_yen": None,
            "total_net_100m_yen": None,
        },
    ]
