#!/usr/bin/env python3
from __future__ import annotations

import html
import re

import korea_market_stress_watch_v13_core as core

watch = core.watch

NEWS_CAPEX_PREFIX = "• 하이퍼스케일러 AI 설비투자 ±10% 이상 수치 포함 신규자료: "
NEWS_WAVE_PREFIX = "• BofA Global Wave 방향 전환 관련 신규 공개자료: "

COMPANIES = (
    ("Microsoft", "Microsoft"),
    ("Alphabet", "Alphabet"),
    ("Google", "Google"),
    ("Amazon", "Amazon"),
    ("Meta", "Meta"),
    ("NVIDIA", "NVIDIA"),
    ("Nvidia", "NVIDIA"),
    ("Oracle", "Oracle"),
)


def _company(title: str) -> str:
    for needle, label in COMPANIES:
        if needle.lower() in title.lower():
            m = re.search(rf"{re.escape(needle)}\s*\(([A-Z]{{1,6}})\)", title, re.I)
            return f"{label}({m.group(1).upper()})" if m else label
    m = re.search(r"\(([A-Z]{1,6})\)", title)
    return f"해당 기업({m.group(1)})" if m else "해당 기업"


def _money_to_ko(raw: str) -> str:
    m = re.fullmatch(r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*([MB])", raw.strip(), re.I)
    if not m:
        return raw
    value = float(m.group(1))
    dollars = value * (1_000_000 if m.group(2).upper() == "M" else 1_000_000_000)
    eok = dollars / 100_000_000
    whole = int(eok)
    man = int(round((eok - whole) * 10_000))
    return f"{whole:,}억{man:,}만달러" if man else f"{whole:,}억달러"


def _translate_title(title: str, kind: str) -> str:
    title = html.unescape(title).strip()
    lower = title.lower()
    company = _company(title)
    pieces: list[str] = []

    if any(k in lower for k in ("crash", "crashing", "plunge", "slump", "slides", "falls", "falling")):
        pieces.append("주가 급락")
    elif any(k in lower for k in ("surge", "surges", "jumps", "rally", "rises", "rose")):
        pieces.append("주가 강세")

    if "earnings" in lower:
        pieces.append("실적 발표 영향")

    m = re.search(r"EPS\s+(?:missed|misses)\s+([0-9]+(?:\.[0-9]+)?)%", title, re.I)
    if m:
        pieces.append(f"주당순이익(EPS) 예상치 {m.group(1)}% 하회")
    m = re.search(r"EPS\s+(?:beat|beats)\s+([0-9]+(?:\.[0-9]+)?)%", title, re.I)
    if m:
        pieces.append(f"주당순이익(EPS) 예상치 {m.group(1)}% 상회")

    m = re.search(r"FCF\s+(?:Hit|Hits|at|to)\s*(\$\s*[0-9]+(?:\.[0-9]+)?\s*[MB])", title, re.I)
    if m:
        pieces.append(f"잉여현금흐름(FCF) {_money_to_ko(m.group(1))}")

    if "capex raised again" in lower:
        pieces.append("설비투자 가이던스 재차 상향")
    elif "capex raised" in lower or "raises capex" in lower or "raised capex" in lower:
        pieces.append("설비투자 가이던스 상향")
    elif "capex" in lower or "capital expenditure" in lower or "capital spending" in lower:
        pieces.append("설비투자 변화")

    if kind == "wave":
        if any(k in lower for k in ("trough", "troughed", "rise", "rising", "rose", "improve", "improved", "positive signal")):
            pieces.append("경기·이익 수정 방향 개선 신호")
        if any(k in lower for k in ("peak", "peaked", "fall", "falling", "fell", "deteriorate", "deteriorated", "negative signal")):
            pieces.append("경기·이익 수정 방향 악화 신호")

    pcts = []
    for p in re.findall(r"(?<!\d)(-?[0-9]+(?:\.[0-9]+)?)\s*%", title):
        if p not in pcts:
            pcts.append(p)
    if pcts and not any(p + "%" in " ".join(pieces) for p in pcts):
        pieces.append("주요 변화율 " + ", ".join(p + "%" for p in pcts[:3]))

    if pieces:
        return company + ": " + " · ".join(dict.fromkeys(pieces))
    if kind == "capex":
        return f"{company}: AI 인프라·설비투자 관련 신규 공개자료 — ±10% 이상 변화 수치 확인"
    return "BofA Global Wave 방향 전환 관련 신규 공개자료 확인"


def _koreanize_alert_news() -> None:
    if not watch.ALERT_PATH.exists():
        return
    lines = watch.ALERT_PATH.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    changed = False
    for line in lines:
        new_line = line
        if line.startswith(NEWS_CAPEX_PREFIX):
            new_line = NEWS_CAPEX_PREFIX + html.escape(_translate_title(line[len(NEWS_CAPEX_PREFIX):], "capex"))
        elif line.startswith(NEWS_WAVE_PREFIX):
            new_line = NEWS_WAVE_PREFIX + html.escape(_translate_title(line[len(NEWS_WAVE_PREFIX):], "wave"))
        if new_line != line:
            changed = True
        out.append(new_line)
    if changed:
        watch.ALERT_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> int:
    rc = core.main()
    _koreanize_alert_news()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
