#!/usr/bin/env python3
from __future__ import annotations

import html
import re

import korea_market_stress_watch_v13 as v13

watch = v13.watch

NEWS_PREFIXES = (
    "• 하이퍼스케일러 AI 설비투자 ±10% 이상 수치 포함 신규자료: ",
    "• BofA Global Wave 방향 전환 관련 신규 공개자료: ",
)

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
            ticker = re.search(rf"{re.escape(needle)}\s*\(([A-Z]{{1,6}})\)", title, re.I)
            return f"{label}({ticker.group(1).upper()})" if ticker else label
    ticker = re.search(r"\(([A-Z]{1,6})\)", title)
    return f"해당 기업({ticker.group(1)})" if ticker else "해당 기업"


def _money_to_ko(raw: str) -> str:
    m = re.fullmatch(r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*([MB])", raw.strip(), re.I)
    if not m:
        return raw
    value = float(m.group(1))
    unit = m.group(2).upper()
    dollars = value * (1_000_000 if unit == "M" else 1_000_000_000)
    eok = dollars / 100_000_000
    if eok >= 10_000:
        jo = int(eok // 10_000)
        rem = int(round(eok - jo * 10_000))
        return f"{jo}조{rem:,}억달러" if rem else f"{jo}조달러"
    if eok >= 1:
        whole = int(eok)
        man = int(round((eok - whole) * 10_000))
        return f"{whole:,}억{man:,}만달러" if man else f"{whole:,}억달러"
    return f"{dollars:,.0f}달러"


def _translate_finance_title(title: str, *, kind: str) -> str:
    title = html.unescape(title).strip()
    lower = title.lower()
    company = _company(title)

    # 실적/설비투자 제목에서 반복적으로 등장하는 핵심 표현을 한국어로 구조화한다.
    pieces: list[str] = []
    if any(k in lower for k in ("crash", "crashing", "plunge", "plunges", "slump", "slides", "falls", "falling")):
        pieces.append("주가 급락")
    elif any(k in lower for k in ("surge", "surges", "jumps", "jumped", "rally", "rallies", "rises", "rose")):
        pieces.append("주가 강세")

    if "after earnings" in lower or "earnings" in lower:
        pieces.append("실적 발표 영향")

    eps = re.search(r"EPS\s+(?:missed|misses)\s+([0-9]+(?:\.[0-9]+)?)%", title, re.I)
    if eps:
        pieces.append(f"주당순이익(EPS) 예상치 {eps.group(1)}% 하회")
    elif re.search(r"EPS\s+(?:beat|beats)\s+([0-9]+(?:\.[0-9]+)?)%", title, re.I):
        beat = re.search(r"EPS\s+(?:beat|beats)\s+([0-9]+(?:\.[0-9]+)?)%", title, re.I)
        pieces.append(f"주당순이익(EPS) 예상치 {beat.group(1)}% 상회")

    fcf = re.search(r"FCF\s+(?:Hit|Hits|at|to)\s*(\$\s*[0-9]+(?:\.[0-9]+)?\s*[MB])", title, re.I)
    if fcf:
        pieces.append(f"잉여현금흐름(FCF) {_money_to_ko(fcf.group(1))}")

    if "capex raised again" in lower:
        pieces.append("설비투자 가이던스 재차 상향")
    elif "capex raised" in lower or "raises capex" in lower or "raised capex" in lower:
        pieces.append("설비투자 가이던스 상향")
    elif "capex" in lower or "capital expenditure" in lower or "capital spending" in lower:
        pieces.append("설비투자 변화")

    if "free cash flow" in lower and not any("잉여현금흐름" in p for p in pieces):
        pieces.append("잉여현금흐름 변화")
    if "revenue" in lower:
        pieces.append("매출 변화")

    # BofA Global Wave는 방향 자체가 핵심이므로 상승/하락·개선/악화를 한국어로 명시한다.
    if kind == "globalwave":
        if any(k in lower for k in ("trough", "troughed", "rise", "rising", "rose", "improve", "improved", "positive signal")):
            pieces.append("경기·이익 수정 방향 개선 신호")
        if any(k in lower for k in ("peak", "peaked", "fall", "falling", "fell", "deteriorate", "deteriorated", "negative signal")):
            pieces.append("경기·이익 수정 방향 악화 신호")

    # 제목 안의 큰 변화율을 보조 정보로 보존한다.
    pcts = []
    for p in re.findall(r"(?<!\d)(-?[0-9]+(?:\.[0-9]+)?)\s*%", title):
        if p not in pcts:
            pcts.append(p)
    if pcts and not any(p + "%" in " ".join(pieces) for p in pcts):
        pieces.append("주요 변화율 " + ", ".join(p + "%" for p in pcts[:3]))

    if pieces:
        return company + ": " + " · ".join(dict.fromkeys(pieces))

    # 번역 규칙에 없는 영문 제목도 영어 원문을 그대로 내보내지 않는다.
    if kind == "capex":
        return f"{company}: AI 인프라·설비투자 관련 신규 공개자료 — ±10% 이상 변화 수치 확인"
    return "BofA Global Wave 방향 전환 관련 신규 공개자료 확인"


def _koreanize_alert_news() -> None:
    if not watch.ALERT_PATH.exists():
        return
    lines = watch.ALERT_PATH.read_text(encoding="utf-8").splitlines()
    changed = False
    out: list[str] = []
    for line in lines:
        replaced = line
        if line.startswith(NEWS_PREFIXES[0]):
            title = line[len(NEWS_PREFIXES[0]):]
            replaced = NEWS_PREFIXES[0] + html.escape(_translate_finance_title(title, kind="capex"))
        elif line.startswith(NEWS_PREFIXES[1]):
            title = line[len(NEWS_PREFIXES[1]):]
            replaced = NEWS_PREFIXES[1] + html.escape(_translate_finance_title(title, kind="globalwave"))
        if replaced != line:
            changed = True
        out.append(replaced)
    if changed:
        watch.ALERT_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> int:
    rc = v13.main()
    _koreanize_alert_news()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
