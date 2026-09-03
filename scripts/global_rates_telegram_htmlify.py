#!/usr/bin/env python3
"""Enrich the global-rates alert, improve visual hierarchy, then render safe Telegram HTML links."""
from __future__ import annotations

import csv
import html
import io
import pathlib
import re
import urllib.parse
import urllib.request
from datetime import date, datetime
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPORT = ROOT / "out" / "global_rates_watch_telegram.md"
SOURCE_RE = re.compile(r"^(?P<prefix>-\s+.+?):\s+(?P<url>https?://\S+)\s*$")
OLD_SECTION_RE = re.compile(r"^(?:①|②(?:-\d+)?|③|④|⑤|⑥|⑦)\s")
DISPLAY_SECTION_RE = re.compile(r"^(?:①|②|③|④|⑤|⑥|⑦|⑧)\s")
KST = ZoneInfo("Asia/Seoul")
UA = "khs-watch-global-rates-transition/1.1"

BOJ_MPM_URL = "https://www.boj.or.jp/en/mopo/mpmsche_minu/index.htm"
BOJ_JGB_PLAN_URL = "https://www.boj.or.jp/en/mopo/mpmdeci/mpr_2026/k260616d.pdf"
JAPAN_BOP_URL = "https://www.mof.go.jp/english/policy/international_policy/reference/balance_of_payments/index.htm"
FRED_USDKRW_URL = "https://fred.stlouisfed.org/series/DEXKOUS"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"

# Officially announced dates. If these are exhausted, the alert points back to the official page
# instead of inventing a future date.
BOJ_MEETINGS_2026 = [
    (date(2026, 9, 17), date(2026, 9, 18)),
    (date(2026, 10, 29), date(2026, 10, 30)),
    (date(2026, 12, 17), date(2026, 12, 18)),
]
BOP_RELEASES = [
    (date(2026, 9, 8), "7월분"),
    (date(2026, 10, 8), "8월분"),
    (date(2026, 11, 10), "9월분"),
    (date(2026, 12, 8), "10월분"),
    (date(2027, 1, 12), "11월분"),
]


def next_boj_meeting(today: date) -> str:
    for start, end in BOJ_MEETINGS_2026:
        if today <= end:
            return f"{start.month}/{start.day}~{end.day}"
    return "공식 일정 페이지 재확인"


def next_bop_release(today: date) -> str:
    for day, subject in BOP_RELEASES:
        if today <= day:
            return f"{day.month}/{day.day} 08:50({subject})"
    return "공식 발표일 재확인"


def fetch_fred_rows(series_id: str, max_rows: int = 40) -> dict[str, float]:
    params = urllib.parse.urlencode({"id": series_id})
    req = urllib.request.Request(
        f"{FRED_CSV}?{params}",
        headers={"User-Agent": UA, "Cache-Control": "no-cache"},
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        text = response.read().decode("utf-8-sig", errors="replace")
    rows: list[tuple[str, float]] = []
    for row in csv.DictReader(io.StringIO(text)):
        day = (row.get("DATE") or row.get("observation_date") or "").strip()
        raw = (row.get(series_id) or "").strip()
        if not day or not raw or raw == ".":
            continue
        try:
            rows.append((day, float(raw)))
        except ValueError:
            continue
    return dict(rows[-max_rows:])


def krw_per_100_yen() -> tuple[str, float, float, float] | None:
    """Use the latest common FRED H.10 date, never two mismatched observation dates."""
    try:
        krw = fetch_fred_rows("DEXKOUS")
        jpy = fetch_fred_rows("DEXJPUS")
        common = sorted(set(krw) & set(jpy))
        if not common:
            return None
        day = common[-1]
        usdkrw = krw[day]
        usdjpy = jpy[day]
        if usdjpy <= 0:
            return None
        return day, usdkrw, usdjpy, 100.0 * usdkrw / usdjpy
    except Exception:
        return None


def transition_section(text: str, now: datetime | None = None) -> tuple[list[str], list[str]]:
    now = now or datetime.now(KST)
    today = now.date()
    match = re.search(r"^판정:\s*(.+)$", text, flags=re.MULTILINE)
    risk_label = match.group(1).strip() if match else ""
    detailed = risk_label != "관찰"

    fx = krw_per_100_yen()
    if fx:
        day, usdkrw, usdjpy, krw100 = fx
        fx_line = (
            f"- 100엔당 원화: {krw100:,.1f}원 = 100×USD/KRW {usdkrw:,.2f}÷USD/JPY {usdjpy:.3f} "
            f"(FRED 동일 기준일 {day})."
        )
    else:
        fx_line = "- 100엔당 원화: USD/KRW와 USD/JPY를 반드시 분리 확인 — 서로 다른 기준일 수치를 섞어 환산하지 않음."

    next_mpm = next_boj_meeting(today)
    next_bop = next_bop_release(today)

    if detailed:
        section = [
            "⑦ 흐름 전환 조건·다음 확인",
            f"- BOJ: 다음 회의 {next_mpm}. 정책금리와 추가 인상 속도를 확인. 7월 회의는 1.0% 유지 8대1, 반대 1명은 1.25% 인상을 제안.",
            "- JGB 매입: 2027년 1~3월까지 분기마다 월 매입액을 약 0.2조엔씩 감액, 2027년 4월부터 월 약 2조엔. 장기금리 급등 시 매입 확대 등 기민 대응 발동 여부를 별도 확인.",
            f"- 자금 흐름: 주간 해외증권투자를 단기 수급에 우선 사용. 월간 직접투자는 순유출 규모가 꺾이는지 보는 구조적 확인용이며 다음 국제수지 발표는 {next_bop}.",
            fx_line,
            "- 전환 판정: 일본 단기금리 상승 + 미·일 2년 금리차 축소 + USD/JPY 하락 지속 + 일본의 해외자산 매수·직접투자 순유출 둔화가 함께 확인될 때 ‘엔화 재약세·캐리 재구축’ 압력이 약해진 것으로 단계 하향.",
            "- 단일 임계치 금지: JGB 10년 3%나 USD/JPY 특정 숫자 하나만으로 종료·청산을 판정하지 않음.",
        ]
    else:
        section = [
            "⑦ 흐름 전환 조건·다음 확인",
            f"- 다음 확인: BOJ {next_mpm} · JGB 매입 감액/기민 대응 · 주간 해외증권 수급 · 월간 직접투자 순유출 {next_bop}.",
            "- 전환 판정: 일본 단기금리 상승 + 미·일 2년 금리차 축소 + USD/JPY 하락 지속 + 일본 해외자산 매수·직접투자 순유출 둔화가 함께 확인될 때 캐리 재구축 압력 약화로 판단.",
            fx_line,
        ]

    sources = [
        f"- BOJ 금융정책결정회의 일정: {BOJ_MPM_URL}",
        f"- BOJ JGB 매입 감액·기민 대응 계획: {BOJ_JGB_PLAN_URL}",
        f"- Japan MOF 국제수지·직접투자 일정: {JAPAN_BOP_URL}",
        f"- Federal Reserve/FRED USD/KRW: {FRED_USDKRW_URL}",
    ]
    return section, sources


def enrich_transition_context(text: str, now: datetime | None = None) -> str:
    if "⑦ 흐름 전환 조건·다음 확인" in text:
        return text

    section, sources = transition_section(text, now=now)
    lines = text.splitlines()
    try:
        source_idx = next(i for i, line in enumerate(lines) if line.strip() == "출처")
    except StopIteration:
        source_idx = len(lines)

    before = lines[:source_idx]
    after = lines[source_idx:]
    if before and before[-1].strip():
        before.append("")
    before.extend(section)
    before.append("")

    if after:
        existing = set(after)
        after.extend(source for source in sources if source not in existing)
    else:
        after = ["출처", *sources]

    return "\n".join(before + after).strip() + "\n"


def _pop_section(lines: list[str], heading: str) -> list[str]:
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == heading)
    except StopIteration:
        return []
    end = start + 1
    while end < len(lines):
        stripped = lines[end].strip()
        if stripped == "출처" or OLD_SECTION_RE.match(stripped):
            break
        end += 1
    block = lines[start:end]
    del lines[start:end]
    return block


def _key_metrics(lines: list[str]) -> str | None:
    joined = "\n".join(lines)
    jgb = re.search(r"JGB 10Y 3\.0% 경계:\s*([0-9.]+%)", joined)
    yen = re.search(r"엔화 급등:.*?USD/JPY\s*([0-9.]+).*?(?:기준변화|1일)\s*([+-][0-9.]+%)", joined)
    spread = re.search(r"미·일 2Y 금리차 축소:\s*([0-9.]+%p)", joined)
    parts: list[str] = []
    if jgb:
        parts.append(f"JGB10 {jgb.group(1)}")
    if yen:
        parts.append(f"USD/JPY {yen.group(1)} ({yen.group(2)})")
    if spread:
        parts.append(f"미·일2Y {spread.group(1)}")
    return "핵심 숫자 │ " + " · ".join(parts) if parts else None


def _compact_blank_lines(lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        if not line.strip() and (not out or not out[-1].strip()):
            continue
        out.append(line)
    while out and not out[-1].strip():
        out.pop()
    return out


def _format_bullet(line: str) -> str:
    if not line.startswith("- "):
        return line
    body = line[2:]
    label_map = {
        "JGB 입찰:": "JGB 입찰 │",
        "GPIF:": "GPIF │",
        "GPIF 제로섬:": "GPIF 제로섬 │",
        "BOJ 채권시장 서베이:": "BOJ 시장기능 │",
        "외환개입:": "외환개입 │",
        "개입 효율 다음 검산:": "개입효율 다음 검산 │",
        "원화 환산 기준:": "원화 환산 기준 │",
        "JGB 상승 원인:": "JGB 상승 원인 │",
        "글로벌 동조 검산:": "글로벌 동조 │",
        "환율 검산:": "환율 검산 │",
        "3% 입찰 흡수력:": "3% 입찰 흡수력 │",
        "일본 거주자 해외 주식+중장기채:": "해외 주식+중장기채 │",
        "해외 중장기채만:": "해외 중장기채 │",
        "원화 환산:": "원화 환산 │",
        "정확한 의미:": "판정 원칙 │",
        "조기경보:": "조기경보 │",
        "BOJ:": "BOJ │",
        "JGB 매입:": "JGB 매입 │",
        "자금 흐름:": "자금 흐름 │",
        "100엔당 원화:": "100엔당 원화 │",
        "전환 판정:": "전환 판정 │",
        "단일 임계치 금지:": "단일 임계치 금지 │",
        "다음 확인:": "다음 확인 │",
    }
    for prefix, replacement in label_map.items():
        if body.startswith(prefix):
            return "• " + replacement + body[len(prefix):].lstrip()
    return "• " + body


def improve_readability(text: str) -> str:
    """Reorder and style the alert without dropping factual lines.

    The generated alert used to put the ②-2 regime block after the current-summary
    section because that block was appended late. This function moves it beside the
    other structural block, promotes the existing current-summary line to the top,
    and preserves all other non-duplicate content.
    """
    lines = text.splitlines()
    try:
        source_idx = next(i for i, line in enumerate(lines) if line.strip() == "출처")
    except StopIteration:
        source_idx = len(lines)

    body = lines[:source_idx]
    sources = lines[source_idx:]

    current_block = _pop_section(body, "⑥ 현재 한 줄")
    regime_block = _pop_section(body, "②-2 JGB 3% 체제·실제 자금이동")

    if regime_block:
        try:
            insert_at = next(i for i, line in enumerate(body) if line.strip() == "③ 실제 청산 전염 확인")
        except StopIteration:
            insert_at = len(body)
        body[insert_at:insert_at] = [*regime_block, ""]

    heading_map = {
        "① 무엇이 바뀌었나": "① 지금 바뀐 것",
        "② 선행 신호": "② 선행 신호",
        "②-1 실제 자금 수요·시장 기능": "③ 실제 자금 수요·시장 기능",
        "②-2 JGB 3% 체제·실제 자금이동": "④ JGB 3% 원인·실제 자금이동",
        "③ 실제 청산 전염 확인": "⑤ 실제 청산 전염",
        "④ 정확한 의미": "⑥ 왜 이런 판정인가",
        "⑤ 시장 영향": "⑦ 시장 영향",
        "⑦ 흐름 전환 조건·다음 확인": "⑧ 다음 확인·단계 전환 조건",
    }

    formatted: list[str] = []
    in_sources = False
    for line in body:
        stripped = line.strip()
        if stripped == "데이터 최신성 검증":
            formatted.append("최신성")
            continue
        if stripped in heading_map:
            formatted.append(heading_map[stripped])
            continue
        if line.startswith("판정:"):
            formatted.append("판정 │" + line.split(":", 1)[1])
            continue
        if line.startswith("조회:"):
            formatted.append("조회 │" + line.split(":", 1)[1])
            continue
        formatted.append(_format_bullet(line))

    summary_lines = [line for line in current_block[1:] if line.strip()] if current_block else []
    metric_line = _key_metrics(formatted)
    if summary_lines or metric_line:
        try:
            first_section = next(i for i, line in enumerate(formatted) if line.startswith("① "))
        except StopIteration:
            first_section = min(3, len(formatted))
        summary = ["한눈에 보기", *summary_lines]
        if metric_line:
            summary.append(metric_line)
        summary.append("")
        formatted[first_section:first_section] = summary

    formatted = _compact_blank_lines(formatted)
    if sources:
        formatted += ["", *sources]
    return "\n".join(formatted).strip() + "\n"


def htmlify(text: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    in_sources = False
    seen_source_urls: set[str] = set()

    for line in lines:
        stripped = line.strip()
        if stripped == "출처":
            in_sources = True
            out.append("<b>출처</b>")
            continue

        if in_sources:
            match = SOURCE_RE.match(line)
            if match:
                raw_url = match.group("url")
                if raw_url in seen_source_urls:
                    continue
                seen_source_urls.add(raw_url)
                prefix = html.escape(match.group("prefix"), quote=False)
                url = html.escape(raw_url, quote=True)
                out.append(f'{prefix} · <a href="{url}">원문</a>')
                continue

        escaped = html.escape(line, quote=False)
        if stripped.startswith("[글로벌 금리·엔캐리 경보]"):
            out.append(f"<b>{escaped}</b>")
        elif stripped in {"한눈에 보기", "최신성"} or DISPLAY_SECTION_RE.match(stripped):
            out.append(f"<b>{escaped}</b>")
        elif line.startswith(("판정 │", "조회 │", "핵심 숫자 │")) and "│" in line:
            label, value = line.split("│", 1)
            out.append(f"<b>{html.escape(label.strip(), quote=False)}</b> │{html.escape(value, quote=False)}")
        else:
            out.append(escaped)

    return "\n".join(out).strip() + "\n"


def main() -> int:
    if not REPORT.exists():
        return 0
    raw = REPORT.read_text(encoding="utf-8")
    enriched = enrich_transition_context(raw)
    readable = improve_readability(enriched)
    REPORT.write_text(htmlify(readable), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
