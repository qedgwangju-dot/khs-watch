from __future__ import annotations

import re

import jobs_wage_watch_full_report_v6 as v6

DIVIDER = "━━━━━━━━━━━━━━━━━━━━"


def _clean(value: str) -> str:
    """Remove Markdown-only marks because Telegram is sent as plain text."""
    return value.replace("**", "").replace("#", "").strip()


def _first_match(pattern: str, text: str):
    return re.search(pattern, text, flags=re.MULTILINE)


def _overview(report: str) -> list[str]:
    """Build a compact scan-first block without deleting any detailed section."""
    bullets: list[str] = []

    regime = _first_match(r"노동시장 국면:\s*\*\*(.+?)\*\*", report)
    if not regime:
        regime = _first_match(r"노동시장 국면:\s*([^\n]+)", report)
    if regime:
        bullets.append(f"• 국면 | {_clean(regime.group(1))}")

    lines = report.splitlines()
    for idx, line in enumerate(lines):
        label = line.strip()
        if not re.match(r"^[①②③]\s+", label):
            continue
        detail = ""
        if idx + 1 < len(lines) and "기준기간:" in lines[idx + 1]:
            detail = lines[idx + 1].strip().lstrip("- ").strip()
            detail = detail.replace("기준기간:", "기준 ").replace("발표:", "발표 ")
        item = f"• 새 발표 | {_clean(label)}"
        if detail:
            item += f" · {_clean(detail)}"
        bullets.append(item)

    claims = _first_match(
        r"Initial\s+([0-9,]+)건\s*\|\s*4주 평균\s+([0-9,]+)건\s*\|\s*Continuing\s+([0-9,]+)건",
        report,
    )
    if claims:
        bullets.append(
            f"• 실업수당 | 신규 {claims.group(1)}건 · 4주 평균 {claims.group(2)}건 · 계속 {claims.group(3)}건"
        )

    bls = _first_match(
        r"BLS 기준월\s+([0-9]{4}-[0-9]{2}):\s*NFP\s*([+\-]?[0-9,]+)\s*\|\s*민간\s*([+\-]?[0-9,]+)\s*\|\s*정부\s*([+\-]?[0-9,]+)",
        report,
    )
    if bls:
        bullets.append(
            f"• 고용 | {bls.group(1)} NFP {bls.group(2)}명 · 민간 {bls.group(3)}명 · 정부 {bls.group(4)}명"
        )

    cps = _first_match(r"CPS:\s*실업률\s*([^|\n]+)\|\s*참가율\s*([^|\n]+)\|\s*EPOP\s*([^|\n]+)", report)
    if cps:
        bullets.append(
            f"• 가계조사 | 실업률 {cps.group(1).strip()} · 참가율 {cps.group(2).strip()} · 고용률 {cps.group(3).strip()}"
        )

    wage = _first_match(r"AHE MoM\s*([^/|\n]+)\s*/\s*YoY\s*([^|\n]+)", report)
    if wage:
        text = f"BLS 임금 MoM {wage.group(1).strip()} · YoY {wage.group(2).strip()}"
        adp = _first_match(
            r"ADP:\s*고용\s*([+\-]?[0-9,]+),\s*Stayer\s*([^,|\n]+),\s*Changer\s*([^,|\n]+)",
            report,
        )
        if adp:
            text += f" · ADP Stayer {adp.group(2).strip()} / Changer {adp.group(3).strip()}"
        bullets.append(f"• 임금 | {text}")

    market = _first_match(r"^- 판정:\s*([^\n]+)", report)
    if market:
        bullets.append(f"• 시장 | {_clean(market.group(1))}")

    timing = _first_match(r"^- 시간표:\s*\*\*[^*]+\*\*\s*—\s*([^\n]+)", report)
    if timing:
        schedule = timing.group(1).split(". 다음 공식 데이터", 1)[0].strip()
        bullets.append(f"• 다음 확인 | {_clean(schedule)}")

    # Keep the scan-first block at 5~8 lines when enough verified fields exist.
    return bullets[:8]


def _group_market_items(body: str) -> list[str]:
    items = [item.strip() for item in body.split(" | ") if item.strip()]
    groups = [
        ("달러·환율", ("DXY", "UUP", "USD/JPY", "EUR/USD", "USD/KRW")),
        ("채권·변동성", ("TLT", "VIX")),
        ("주식", ("S&P 500", "NASDAQ", "SOXX", "KOSPI", "KOSDAQ")),
        ("기타 위험자산·크레딧", ("Gold", "Bitcoin", "HYG", "JNK")),
    ]
    out = ["• 발표 직후 시장 반응"]
    used: set[int] = set()
    for label, prefixes in groups:
        selected = []
        for i, item in enumerate(items):
            if any(item.startswith(prefix + " ") for prefix in prefixes):
                selected.append(item)
                used.add(i)
        if selected:
            out.append(f"  {label} | " + " · ".join(selected))
    rest = [item for i, item in enumerate(items) if i not in used]
    if rest:
        out.append("  기타 | " + " · ".join(rest))
    return out


def _reflow_line(line: str) -> list[str]:
    stripped = line.strip()

    if stripped.startswith("- 발표 직후 Yahoo Finance 5분봉:"):
        body = stripped.split(":", 1)[1].strip()
        return _group_market_items(body)

    if stripped.startswith("- 금리 즉시 프록시:"):
        body = stripped.split(":", 1)[1].strip().replace(" | ", " · ")
        return ["• 금리 즉시 반응 | " + body]

    if stripped.startswith("- FRED 최신 일별 공식 비교값"):
        body = stripped.split(":", 1)[1].strip()
        items = [item.strip() for item in body.split(" | ") if item.strip()]
        nominal = [x for x in items if x.startswith(("UST 2Y", "UST 5Y", "UST 10Y"))]
        real = [x for x in items if x.startswith(("10Y real yield", "10Y BEI"))]
        other = [x for x in items if x not in nominal and x not in real]
        out = ["• FRED 최신 일별 공식 비교값 | 발표 직후값 아님·시차 가능"]
        if nominal:
            out.append("  명목금리 | " + " · ".join(nominal))
        if real:
            out.append("  실질·기대인플레이션 | " + " · ".join(real))
        if other:
            out.append("  기타 | " + " · ".join(other))
        return out

    if stripped.startswith("- 업종:"):
        body = stripped.split(":", 1)[1].strip()
        items = [item.strip() for item in body.split(" | ") if item.strip()]
        midpoint = (len(items) + 1) // 2
        out = ["• 업종별 고용"]
        if items[:midpoint]:
            out.append("  " + " · ".join(items[:midpoint]))
        if items[midpoint:]:
            out.append("  " + " · ".join(items[midpoint:]))
        return out

    if stripped.startswith("- 최신 공식 비교값 — Weekly Claims:") and " | ADP:" in stripped:
        left, right = stripped[2:].split(" | ADP:", 1)
        return ["• " + left, "• ADP 최신 공식 비교값:" + right]

    if stripped.startswith("- "):
        return ["• " + stripped[2:]]

    return [stripped]


def _format_report(report: str) -> str:
    lines = report.splitlines()
    body_start = None
    for i, line in enumerate(lines):
        if re.match(r"^##\s+1\)", line.strip()):
            body_start = i
            break
    if body_start is None:
        body_start = len(lines)

    header = [_clean(line) for line in lines[:body_start] if _clean(line)]
    overview = _overview(report)

    out: list[str] = []
    if header:
        out.append(header[0])
        for line in header[1:]:
            out.append(line)
    else:
        out.append("Jobs Wage Watch")

    if overview:
        out.extend(["", "한눈에 보기"])
        out.extend(overview)

    for raw in lines[body_start:]:
        stripped = raw.strip()
        if not stripped:
            if out and out[-1] != "":
                out.append("")
            continue

        heading = re.match(r"^#{1,6}\s*(.+)$", stripped)
        if heading:
            title = _clean(heading.group(1))
            if re.match(r"^\d+\)", title) or title == "다음 공식 발표별 시나리오":
                if out and out[-1] != "":
                    out.append("")
                out.extend([DIVIDER, title])
            else:
                if out and out[-1] != "":
                    out.append("")
                out.append(title)
            continue

        for item in _reflow_line(raw):
            out.append(_clean(item))

    # Collapse excessive blank lines but keep paragraph separation.
    compact: list[str] = []
    for line in out:
        if line == "" and compact and compact[-1] == "":
            continue
        compact.append(line)

    result = "\n".join(compact).strip() + "\n"
    # Final hard guarantee requested by the user: no visible Markdown hashes.
    result = result.replace("#", "").replace("**", "")
    return result


def build_report(new_releases):
    return _format_report(v6.build_report(new_releases))
