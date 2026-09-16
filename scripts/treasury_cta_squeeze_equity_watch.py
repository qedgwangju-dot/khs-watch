#!/usr/bin/env python3
"""Readable equity interpretation plus scheduled Treasury CTA reports.

Delivery policy:
- preserve the audited composite squeeze gate for event-driven alerts
- always send one Monday weekly status report
- always send one FOMC decision-eve report on the Korean evening before the
  2:00 p.m. ET decision reaches Korea
- preserve scheduled-delivery state only after Telegram delivery succeeds
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import treasury_cta_squeeze_audited_watch as audited

watcher = audited.watcher
# Keep revision 9 so a readability-only edit does not itself force an alert.
watcher.FORMAT_REVISION = max(int(getattr(watcher, "FORMAT_REVISION", 0)), 9)
_base_format = audited.format_alert
_base_main = watcher.main

NY = ZoneInfo("America/New_York")
KST = ZoneInfo("Asia/Seoul")

# Federal Reserve published meeting-end dates.
FOMC_END_DATES = {
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
    "2027-01-27", "2027-03-17", "2027-04-28", "2027-06-09",
    "2027-07-28", "2027-09-15", "2027-10-28", "2027-12-08",
}
FOMC_SEP_END_DATES = {
    "2026-03-18", "2026-06-17", "2026-09-16", "2026-12-09",
    "2027-03-17", "2027-06-09", "2027-09-15", "2027-12-08",
}

TREASURY_URL = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve"
CFTC_URL = "https://www.cftc.gov/dea/futures/financial_lf.htm"
NYFED_URL = "https://markets.newyorkfed.org/api/rates/secured/sofr/last/1.json"
FED_FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
CTA_SECONDARY_URL = "https://a.foresightnews.pro/article/detail/99813"


def _equity_impact(snapshot: dict, previous: dict, reasons: list[str]) -> tuple[str, str]:
    y = snapshot.get("yield10") or {}
    yld = float(y.get("yield") or 0.0)
    z = float(y.get("z20") or 0.0)
    evidence = watcher.squeeze_evidence(snapshot, previous)
    repo_ok, _ = audited._repo_not_worse(snapshot, previous)
    prices_up = audited._price_up_count(snapshot)
    short_bias = any("CFTC 숏 축소" in r or "CFTC 주간 숏 축소" in r for r in reasons)
    if evidence and z <= -1.0 and repo_ok:
        return "🟢 성장주 우호 강화", "금리 하락이 포지션 청산과 함께 확인"
    if (short_bias or prices_up >= 2) and repo_ok:
        return "🟡 중립~약한 우호", f"숏 압력 완화 가능성은 있지만 10Y {yld:.3f}%·z={z:+.2f}σ로 추세전환 미확인"
    return "⚪ 중립", f"10Y {yld:.3f}%에서 할인율 완화 신호 미확인"


def _compact_duplicates(body: str) -> str:
    drops = (
        "• Goldman CTA DV01: 공개 공식 피드 없음 — 신뢰/명시적 2차 출처의 신규 인용만 감시\n",
        "• +2σ 채권가격 상승 시 대규모 환매 추정치가 새로 인용되면 별도 변화로 감지합니다.\n",
        "※ CME가 클라우드 러너를 차단하면 Yahoo 지연가격 + CFTC 공식 주간 OI로 교차검증. 주간 OI를 실시간 OI처럼 표시하지 않음\n",
    )
    for line in drops:
        body = body.replace(line, "")
    body = re.sub(
        r"\n<b>🔕 중복 제거 규칙</b>\n• 신규 기사 한 건, CFTC 주간 갱신 한 건, 10년물 구간 변화 한 건만으로는 텔레그램을 보내지 않습니다\.\n• <b>동일 범위 OI 감소 \+ 선물가격 상승 \+ \(CFTC 숏 축소 또는 -1σ 이하\) \+ repo 비악화</b>가 겹칠 때만 실제 스퀴즈로 격상합니다\.",
        "\n• 🔕 단독 기사·CFTC 갱신·10Y 구간 변화만으로는 재발송하지 않음.",
        body,
    )
    return body


def _checked_date(snapshot: dict) -> date:
    raw = str(snapshot.get("checked_kst") or "")
    try:
        return datetime.fromisoformat(raw).astimezone(KST).date()
    except Exception:
        return datetime.now(KST).date()


def _fomc_times(end_day: date) -> tuple[datetime, datetime]:
    decision_et = datetime.combine(end_day, time(14, 0), tzinfo=NY)
    press_et = datetime.combine(end_day, time(14, 30), tzinfo=NY)
    return decision_et.astimezone(KST), press_et.astimezone(KST)


def _easy_read_block(snapshot: dict, previous: dict, reasons: list[str]) -> str:
    y = snapshot.get("yield10") or {}
    yld = float(y.get("yield") or 0.0)
    z = float(y.get("z20") or 0.0)
    evidence = watcher.squeeze_evidence(snapshot, previous)
    repo_ok, _ = audited._repo_not_worse(snapshot, previous)
    prices_up = audited._price_up_count(snapshot)
    direction, _ = audited._direction_label(snapshot, previous, reasons)
    return (
        "<b>👀 지금 쉽게 보면</b>\n"
        f"• <b>{direction}</b> — 10년물 {yld:.3f}% · z={z:+.2f}σ\n"
        f"• 선물 {prices_up}/3 상승 · 동일범위 OI 감소 {'확인' if evidence else '미확인'} · repo {'안정' if repo_ok else '주의'}\n"
        "• 숏이 많다는 사실만으로는 부족합니다. 가격↑+OI↓가 같이 붙어야 실제 숏커버 증거가 강해집니다.\n\n"
    )


def format_alert(snapshot, previous, fx, fx_date, reasons):
    title, body = _base_format(snapshot, previous, fx, fx_date, reasons)
    body = _compact_duplicates(body)
    body = _easy_read_block(snapshot, previous, reasons) + body

    impact, path = _equity_impact(snapshot, previous, reasons)
    block = (
        "<b>🧭 주식시장 해석</b>\n"
        f"• <b>{impact}</b> — {path}.\n"
        "• repo·신용 스트레스형 금리 하락은 위험자산 호재로 보지 않습니다.\n\n"
    )
    marker = "<b>한 줄 결론</b>"
    if "🧭 주식시장 해석" not in body:
        body = body.replace(marker, block + marker, 1) if marker in body else body + "\n\n" + block.rstrip()
    return title, body


def _fmt_pct(value) -> str:
    try:
        return f"{float(value):+.2f}%"
    except Exception:
        return "확인 불가"


def _fmt_net(value) -> str:
    try:
        return f"{int(value):+,}계약"
    except Exception:
        return "확인 불가"


def _scheduled_report(snapshot: dict, previous: dict, reasons: list[str]) -> tuple[str, str]:
    y = snapshot.get("yield10") or {}
    yld = float(y.get("yield") or 0.0)
    z = float(y.get("z20") or 0.0)
    distance = max(0.0, (yld - 4.30) * 100)
    direction, _ = audited._direction_label(snapshot, previous, reasons)
    impact, path = _equity_impact(snapshot, previous, reasons)
    evidence = watcher.squeeze_evidence(snapshot, previous)
    repo_ok, repo_worse = audited._repo_not_worse(snapshot, previous)

    cftc = (snapshot.get("cftc") or {}).get("markets", {})
    cftc_date = (snapshot.get("cftc") or {}).get("report_date", "확인 불가")
    cme = snapshot.get("cme") or {}
    repo = snapshot.get("repo") or {}

    if any("FOMC 전날 점검" in r for r in reasons):
        title = "🚨 미 국채 CTA · FOMC 전날 점검"
    else:
        title = "📅 미 국채 CTA · 월요일 주간 점검"

    lines = [
        "<b>👀 지금 쉽게 보면</b>",
        f"• 판정: <b>{direction}</b>",
        f"• 10년물: <b>{yld:.3f}%</b> · 20일 z={z:+.2f}σ · 4.30%까지 {distance:.1f}bp",
        f"• 선물: ZN {_fmt_pct((cme.get('ZN') or {}).get('pct_change'))} · ZB {_fmt_pct((cme.get('ZB') or {}).get('pct_change'))} · UB {_fmt_pct((cme.get('UB') or {}).get('pct_change'))}",
        f"• 가격↑+동일범위 OI↓: {'확인' if evidence else '미확인'} · repo: {'안정' if repo_ok else '주의 ' + ', '.join(repo_worse)}",
        "",
        "<b>📍 포지션은 얼마나 쌓였나</b>",
        f"• CFTC {cftc_date}: 2Y {_fmt_net((cftc.get('2Y') or {}).get('leveraged_net'))} · 5Y {_fmt_net((cftc.get('5Y') or {}).get('leveraged_net'))}",
        f"• 10Y {_fmt_net((cftc.get('10Y') or {}).get('leveraged_net'))} · Bond {_fmt_net((cftc.get('BOND') or {}).get('leveraged_net'))} · Ultra {_fmt_net((cftc.get('ULTRABOND') or {}).get('leveraged_net'))}",
        f"• SOFR {(repo.get('SOFR') or {}).get('rate', '확인 불가')}% · BGCR {(repo.get('BGCR') or {}).get('rate', '확인 불가')}% · TGCR {(repo.get('TGCR') or {}).get('rate', '확인 불가')}%",
    ]

    if any("FOMC 전날 점검" in r for r in reasons):
        d = _checked_date(snapshot)
        start = d - timedelta(days=1)
        decision_kst, press_kst = _fomc_times(d)
        sep = " · 점도표·경제전망 동반" if d.isoformat() in FOMC_SEP_END_DATES else ""
        lines.extend([
            "",
            "<b>⚡ 내일 FOMC가 왜 중요한가</b>",
            f"• 미국 {start:%m/%d}~{d:%m/%d} 회의{sep}",
            f"• 결정문 한국시간 <b>{decision_kst:%m/%d %H:%M}</b> · 기자회견 {press_kst:%H:%M}",
            "• FOMC가 금리 방향의 촉매는 될 수 있지만, 장기금리가 내려간다는 이유만으로 CTA 스퀴즈라고 보지는 않습니다.",
            "• 발표 직후 10Y·ZN/ZB/UB가 먼저 움직이고, OI·CFTC는 후행 확인합니다.",
        ])

    if any("월요일 정기점검" in r for r in reasons):
        lines.extend([
            "",
            "<b>📅 이번 주에 볼 것</b>",
            "• 4.50→4.40→4.35→4.30% 하향과 -1σ/-2σ 진입을 단계별 확인합니다.",
            "• 월요일에는 신호가 없어도 1회 보고하고, 주중에는 복합 조건이 강화될 때만 추가 발송합니다.",
        ])

    lines.extend([
        "",
        "<b>🧭 주식시장 해석</b>",
        f"• <b>{impact}</b> — {path}.",
        "• 금리↓+선물↑+OI↓가 겹치면 성장주·반도체 할인율에는 우호적입니다.",
        "• 반대로 repo·신용 스트레스 때문에 금리가 내려가면 주식 호재로 보지 않습니다.",
        "",
        "<b>🚦 다음 확인 신호</b>",
        "• 10Y -1σ 진입 또는 4.50% 하향 + 선물 상승 + 동일범위 OI 감소",
        "• 이후 CFTC 순숏 추가 축소까지 붙으면 ‘실제 숏 스퀴즈 강화’로 격상",
        "",
        "<b>⚠️ 실패모드</b>",
        "• 금리만 내려가고 OI가 줄지 않으면 단순 매크로 랠리일 수 있음",
        "• repo가 악화되면 질서 있는 숏커버가 아니라 강제 디레버리징일 수 있음",
        "",
        f'<a href="{FED_FOMC_URL}">Fed FOMC 일정</a> · <a href="{CFTC_URL}">CFTC 포지션</a> · <a href="{TREASURY_URL}">미 재무부 금리</a> · <a href="{NYFED_URL}">NY Fed repo</a> · <a href="{CTA_SECONDARY_URL}">CTA 2차 출처</a>',
    ])
    return title, "\n".join(lines)


def _scheduled_due(current_state: dict, next_state: dict) -> tuple[bool, bool, str, str]:
    snapshot = next_state.get("snapshot") or {}
    d = _checked_date(snapshot)
    iso = d.isocalendar()
    week_key = f"{iso.year}-W{iso.week:02d}"
    date_key = d.isoformat()
    monday_due = d.weekday() == 0 and current_state.get("last_weekly_report_key") != week_key
    fomc_due = date_key in FOMC_END_DATES and current_state.get("last_fomc_eve_report") != date_key
    return monday_due, fomc_due, week_key, date_key


def scheduled_main() -> int:
    current_state = watcher.load_state()
    rc = _base_main()
    if rc != 0 or not watcher.NEXT_STATE.exists():
        return rc

    next_state = json.loads(watcher.NEXT_STATE.read_text(encoding="utf-8"))
    monday_due, fomc_due, week_key, date_key = _scheduled_due(current_state, next_state)
    if not (monday_due or fomc_due):
        return rc

    reasons: list[str] = []
    if watcher.DETAIL.exists():
        try:
            detail_existing = json.loads(watcher.DETAIL.read_text(encoding="utf-8"))
            reasons.extend(detail_existing.get("alert_reasons") or [])
        except Exception:
            pass
    if monday_due:
        reasons.append("월요일 정기점검")
    if fomc_due:
        reasons.append("FOMC 전날 점검")
    reasons = list(dict.fromkeys(reasons))

    snapshot = next_state.get("snapshot") or {}
    previous = current_state.get("snapshot") or {}
    title, body = _scheduled_report(snapshot, previous, reasons)
    if len(title) + 2 + len(body) > 4096:
        raise RuntimeError(f"Telegram scheduled report too long: {len(title)+2+len(body)}")

    watcher.TITLE.write_text(title + "\n", encoding="utf-8")
    watcher.ALERT.write_text(body + "\n", encoding="utf-8")
    watcher.DETAIL.write_text(
        json.dumps(
            {
                **snapshot,
                "dedupe_gate": next_state.get("last_gate") or {},
                "alert_reasons": reasons,
                "scheduled_delivery": {"monday_weekly": monday_due, "fomc_eve": fomc_due},
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    if monday_due:
        next_state["last_weekly_report_key"] = week_key
    if fomc_due:
        next_state["last_fomc_eve_report"] = date_key
    watcher.NEXT_STATE.write_text(json.dumps(next_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with watcher.STATUS.open("a", encoding="utf-8") as f:
        if monday_due:
            f.write("- 예약 발송: 월요일 주간 점검\n")
        if fomc_due:
            f.write("- 예약 발송: FOMC 전날 점검\n")
    return rc


audited.format_alert = format_alert
watcher.main = scheduled_main

if __name__ == "__main__":
    raise SystemExit(watcher.main())
