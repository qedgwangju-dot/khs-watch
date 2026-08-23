#!/usr/bin/env python3
"""Enrich the global-rates alert, then render safe Telegram HTML links."""
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
KST = ZoneInfo("Asia/Seoul")
UA = "khs-watch-global-rates-transition/1.0"

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
            f"- 자금 흐름: 주간 해외증권투자를 단기 수급에 우선 사용하고, 월간 직접투자는 구조적 확인용. 다음 국제수지 발표 {next_bop}.",
            fx_line,
            "- 전환 판정: 일본 단기금리 상승 + 미·일 2년 금리차 축소 + USD/JPY 하락 지속 + 일본의 해외자산 매수 둔화가 함께 확인될 때 ‘엔화 재약세·캐리 재구축’ 압력이 약해진 것으로 단계 하향.",
            "- 단일 임계치 금지: JGB 10년 3%나 USD/JPY 특정 숫자 하나만으로 종료·청산을 판정하지 않음.",
        ]
    else:
        section = [
            "⑦ 흐름 전환 조건·다음 확인",
            f"- 다음 확인: BOJ {next_mpm} · JGB 매입 감액/기민 대응 · 주간 해외증권 수급 · 월간 직접투자 {next_bop}.",
            "- 전환 판정: 일본 단기금리 상승 + 미·일 2년 금리차 축소 + USD/JPY 하락 지속 + 일본 해외자산 매수 둔화가 함께 확인될 때 캐리 재구축 압력 약화로 판단.",
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


def htmlify(text: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    in_sources = False

    for line in lines:
        if line.strip() == "출처":
            in_sources = True
            out.append("<b>출처</b>")
            continue

        if in_sources:
            match = SOURCE_RE.match(line)
            if match:
                prefix = html.escape(match.group("prefix"), quote=False)
                url = html.escape(match.group("url"), quote=True)
                out.append(f'{prefix} · <a href="{url}">원문</a>')
                continue

        out.append(html.escape(line, quote=False))

    return "\n".join(out).strip() + "\n"


def main() -> int:
    if not REPORT.exists():
        return 0
    raw = REPORT.read_text(encoding="utf-8")
    REPORT.write_text(htmlify(enrich_transition_context(raw)), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
