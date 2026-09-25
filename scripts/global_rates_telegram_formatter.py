#!/usr/bin/env python3
"""Build a compact, hierarchy-aware Telegram alert for global rates / yen carry.

The report separates:
1) rate/FX leading signals,
2) actual JGB demand and large-allocator flows,
3) daily confirmation in volatility/equities,
4) policy/transition checkpoints.

A JGB auction or GPIF move may cause the report to be sent, but one structural signal
alone never upgrades the carry-unwind risk label. That label remains based on rates,
FX and market contagion.
"""
from __future__ import annotations

import csv
import io
import json
import os
import pathlib
import re
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

from global_rates_freshness_guard import calculate_final_risk, classify_live_fx

KST = ZoneInfo("Asia/Seoul")
ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
DATA = ROOT / "data"
OUT.mkdir(parents=True, exist_ok=True)
DATA.mkdir(parents=True, exist_ok=True)

JGB_URL = "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv"
JAPAN_BUDGET_URL = "https://www.mof.go.jp/policy/budget/topics/outlook/sy2026a.htm"
UST_URL = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve"
FRED_USDJPY = "https://fred.stlouisfed.org/series/DEXJPUS"
BIS_2024 = "https://www.bis.org/publ/bisbull90.htm"
STATE_PATH = DATA / "global_rates_telegram_state.json"
UA = "khs-watch-global-rates-telegram-formatter/1.2"


def load_json(path: pathlib.Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def norm(v: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (v or "").lower())


def fnum(v):
    try:
        return float(v)
    except Exception:
        return None


def fetch_jgb_latest_two():
    req = urllib.request.Request(JGB_URL, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=30) as r:
        text = r.read().decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    hi = None
    for i, row in enumerate(rows[:12]):
        if any(norm(x) == "date" for x in row):
            hi = i
            break
    if hi is None:
        raise RuntimeError("MOF JGB header not found")
    header = [x.strip() for x in rows[hi]]
    nh = [norm(x) for x in header]

    def col(cands):
        wanted = {norm(x) for x in cands}
        for i, x in enumerate(nh):
            if x in wanted:
                return i
        raise RuntimeError(f"JGB column missing: {cands}; header={header}")

    di = col(["Date"])
    i2 = col(["2", "2Y", "2 year", "2-year"])
    i5 = col(["5", "5Y", "5 year", "5-year"])
    i10 = col(["10", "10Y", "10 year", "10-year"])
    good = []
    for row in rows[hi + 1:]:
        if len(row) <= max(di, i2, i5, i10):
            continue
        vals = [fnum(row[i2]), fnum(row[i5]), fnum(row[i10])]
        day = row[di].strip()
        if day and all(x is not None for x in vals):
            good.append((day, vals[0], vals[1], vals[2]))
    if len(good) < 2:
        raise RuntimeError("MOF JGB needs at least two complete rows")
    return good[-2], good[-1]


def bp(new, old):
    return (new - old) * 100.0


def mark(v: bool) -> str:
    return "✅" if v else "⬜"


def fmt_change(v, suffix=""):
    if v is None:
        return "확인 불가"
    return f"{v:+.2f}{suffix}"


def format_yen_trillion(value_yen) -> str:
    value = fnum(value_yen)
    return "확인 불가" if value is None else f"{value / 1e12:,.2f}조엔"


def format_krw(value_krw) -> str:
    value = fnum(value_krw)
    if value is None:
        return "원화 환산 확인 불가"
    return f"약 {value / 1e12:,.1f}조원"


def structural_lines(structural: dict) -> list[str]:
    auction = structural.get("auction") or {}
    gpif = structural.get("gpif") or {}
    lines = ["③ 실제 자금·전염"]

    if auction:
        accepted_yen = fnum(auction.get("accepted_billion_yen"))
        accepted_yen = None if accepted_yen is None else accepted_yen * 1e9
        lines.append(
            "• JGB 입찰 │ "
            f"{str(auction.get('tenor','')).replace('-Year','년')} {auction.get('grade','확인 불가')} · "
            f"응찰 {fnum(auction.get('bid_to_cover')):.2f}배 · 꼬리 {fnum(auction.get('tail_bp')):.1f}bp · "
            f"낙찰 {format_yen_trillion(accepted_yen)}({format_krw(auction.get('accepted_krw'))})"
        )
    else:
        lines.append("• JGB 입찰 │ 최근 공식 결과 확인 불가")

    if gpif:
        actual = gpif.get("actual_pct") or {}
        target = gpif.get("target_pct") or {}
        domestic = fnum(actual.get("domestic_bonds"))
        target_domestic = fnum(target.get("domestic_bonds"))
        if None not in (domestic, target_domestic):
            lines.append(
                f"• GPIF │ 국내채권 {domestic:.2f}% / 목표 {target_domestic:.0f}% · "
                f"{gpif.get('zero_sum_summary','변화 확인 대기')}"
            )
    return lines

def structural_source_lines(structural: dict) -> list[str]:
    lines: list[str] = []
    auction = structural.get("auction") or {}
    gpif = structural.get("gpif") or {}
    if auction.get("url"):
        lines.append(f"- JGB 입찰: {auction['url']}")
    if gpif.get("url"):
        lines.append(f"- GPIF: {gpif['url']}")
    return lines

def current_carry_direction(
    *,
    usd_day: float | None,
    yen_surge: bool,
    spread_narrow: bool,
    us_rates_down: bool,
    jgb10_3: bool,
    curve_up: bool,
    vix_spike: bool,
    equity_joint: bool,
    risk_level: int,
) -> tuple[str, str]:
    """Separate the market's current direction from the structural risk level."""
    contagion = vix_spike or equity_joint

    if risk_level >= 3 and yen_surge and contagion:
        return (
            "🔴 엔캐리 청산 진행",
            "엔화 급등 + 금리/금리차 부담 + 위험자산 전염이 동시 확인",
        )
    if yen_surge and (spread_narrow or us_rates_down or jgb10_3 or curve_up):
        return (
            "🟠 엔캐리 청산 압력 우세",
            "엔화 급등에 금리·금리차 부담이 겹침",
        )

    if usd_day is not None and usd_day < 0:
        if spread_narrow or us_rates_down:
            return (
                "↘ 엔캐리 청산 쪽으로 기울기",
                "엔화 강세 + 미·일 금리차 축소/미국2Y 하락 신호",
            )
        if jgb10_3 or curve_up:
            return (
                "↔ 혼조 — 구조적 청산 부담↑",
                "엔화는 강세지만 금리차 급축소·위험자산 전염은 아직 미확인",
            )
        return (
            "↔ 엔화 강세, 청산 확인은 아직",
            "엔화 강세 단독이며 금리차·전염 신호가 부족",
        )

    if usd_day is not None and usd_day > 0:
        if jgb10_3 or curve_up:
            return (
                "↗ 캐리 유지 우세 / 구조 부담↑",
                "엔화 약세 + 금리차 급축소·전염 없음, 다만 JGB 상승은 청산 부담",
            )
        return (
            "🟢 캐리 유지·재구축 우세",
            "엔화 약세 + 금리차 급축소·위험자산 전염 없음",
        )

    if contagion:
        return (
            "↔ 방향 혼조 — 위험자산 스트레스",
            "주식·변동성 스트레스는 있으나 엔화 방향 확인 부족",
        )
    return (
        "↔ 방향 확인 대기",
        "엔화·금리차·위험자산에서 우세 방향이 아직 없음",
    )

def main() -> int:
    now = datetime.now(KST)
    pending = load_json(OUT / "global_rates_watch_pending_state.json", {})
    previous = load_json(DATA / "global_rates_watch_state.json", {})
    base_alert = load_json(OUT / "global_rates_watch_alert.json", {})
    confirm = load_json(OUT / "yen_carry_confirmation.json", {})
    structural = load_json(OUT / "global_rates_structural.json", {})
    structural_event = load_json(OUT / "global_rates_structural_event.json", {})
    telegram_state = load_json(STATE_PATH, {"risk_level": 0, "risk_label": "관찰"})
    force_test = os.getenv("FORCE_TEST", "0").strip() == "1"

    values = pending.get("last_values") or {}
    prev_values = previous.get("last_values") or {}
    if not values:
        return 0

    jgb_error = None
    try:
        prev_jgb, cur_jgb = fetch_jgb_latest_two()
        jgb_date = cur_jgb[0]
        jgb2, jgb5, jgb10 = cur_jgb[1], cur_jgb[2], cur_jgb[3]
        d2 = bp(cur_jgb[1], prev_jgb[1])
        d5 = bp(cur_jgb[2], prev_jgb[2])
        d10 = bp(cur_jgb[3], prev_jgb[3])
    except Exception as e:
        jgb_error = f"{type(e).__name__}: {e}"
        jgb_date = str((pending.get("last_source_dates") or {}).get("jgb10") or "")
        jgb2 = fnum(values.get("jgb2"))
        jgb10 = fnum(values.get("jgb10"))
        jgb5 = None
        d2 = d5 = d10 = None

    ust2 = fnum(values.get("ust2"))
    prev_ust2 = fnum(prev_values.get("ust2"))
    ust2_change_bp = None if ust2 is None or prev_ust2 is None else bp(ust2, prev_ust2)
    spread = fnum(values.get("us_jp_2y_spread"))
    prev_spread = fnum(prev_values.get("us_jp_2y_spread"))
    spread_change_bp = None if spread is None or prev_spread is None else bp(spread, prev_spread)
    usdjpy = fnum(values.get("usdjpy"))
    usd_day = fnum(values.get("usdjpy_daily_change_pct"))

    cdata = confirm.get("data") or {}
    sig = confirm.get("signals") or {}
    vix = cdata.get("VIXCLS") or {}
    nasdaq = cdata.get("NASDAQCOM") or {}
    nikkei = cdata.get("NIKKEI225") or {}

    jgb10_3 = bool(jgb10 is not None and jgb10 >= 3.0)
    curve_up = bool(d2 is not None and d5 is not None and d10 is not None and d2 > 0 and d5 > 0 and d10 > 0)
    spread_narrow = bool((spread is not None and spread <= 2.0) or (spread_change_bp is not None and spread_change_bp <= -10.0))
    us_rates_down = bool(ust2_change_bp is not None and ust2_change_bp <= -10.0)
    fx_state = classify_live_fx(usdjpy, usd_day)
    yen_strong_level = bool(fx_state["strong_level"])
    yen_surge = bool(fx_state["surge"])
    vix_spike = bool(sig.get("vix_spike_20pct"))
    equity_joint = bool(confirm.get("equity_joint_weakness"))

    risk_signals = {
        "jgb10_3": jgb10_3,
        "jgb_curve_up": curve_up,
        "us_jp_2y_spread_narrow": spread_narrow,
        "us_2y_down": us_rates_down,
        "yen_surge": yen_surge,
        "vix_spike": vix_spike,
        "nikkei_nasdaq_joint_weakness": equity_joint,
    }
    risk_level, risk_label, emoji, leading_count, confirm_count = calculate_final_risk(risk_signals)
    direction_label, direction_reason = current_carry_direction(
        usd_day=usd_day,
        yen_surge=yen_surge,
        spread_narrow=spread_narrow,
        us_rates_down=us_rates_down,
        jgb10_3=jgb10_3,
        curve_up=curve_up,
        vix_spike=vix_spike,
        equity_joint=equity_joint,
        risk_level=risk_level,
    )

    old_level = int(telegram_state.get("risk_level") or 0)
    primary_event = bool(base_alert.get("events"))
    risk_changed = risk_level != old_level
    structural_changed = bool(structural_event.get("events"))
    should_send = force_test or primary_event or risk_changed or structural_changed

    pending_state = {
        "risk_level": risk_level,
        "risk_label": risk_label,
        "market_direction": direction_label,
        "market_direction_reason": direction_reason,
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "signals": {
            "jgb10_3": jgb10_3,
            "jgb_curve_up": curve_up,
            "us_jp_2y_spread_narrow": spread_narrow,
            "us_2y_down": us_rates_down,
            "yen_strong_level": yen_strong_level,
            "yen_surge": yen_surge,
            "vix_spike": vix_spike,
            "nikkei_nasdaq_joint_weakness": equity_joint,
            "structural_event": structural_changed,
        },
    }
    (OUT / "global_rates_telegram_pending_state.json").write_text(
        json.dumps(pending_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    if not should_send:
        report = OUT / "global_rates_watch_telegram.md"
        if report.exists():
            report.unlink()
        return 0

    event_text = []
    for event in base_alert.get("events") or []:
        typ = "진입" if event.get("type") == "trigger" else "해제"
        label = event.get("label") or event.get("metric") or "이벤트"
        event_text.append(f"- {label}: {typ} ({event.get('value')})")
    for event in structural_event.get("events") or []:
        event_text.append(f"- 구조 신호: {event.get('summary','새 구조 변화')}")
    if force_test and not event_text:
        event_text.append("- 수동 테스트: 전송 경로·현재 판정 확인")
    if risk_changed:
        event_text.append(f"- 위험단계 변화: {telegram_state.get('risk_label','관찰')} → {risk_label}")

    data_dates = pending.get("last_source_dates") or {}
    vix_ch = fnum(vix.get("change_pct"))
    nas_ch = fnum(nasdaq.get("change_pct"))
    nik_ch = fnum(nikkei.get("change_pct"))

    vix_text = (
        f"{vix.get('value')} ({vix_ch:+.2f}%, {vix.get('date')})"
        if vix and vix_ch is not None else "확인 불가"
    )
    nik_text = f"{nik_ch:+.2f}%({nikkei.get('date')})" if nik_ch is not None else "확인 불가"
    nas_text = f"{nas_ch:+.2f}%({nasdaq.get('date')})" if nas_ch is not None else "확인 불가"

    lines = [
        f"[글로벌 금리·엔캐리] {emoji} {risk_label}",
        f"현재 방향 │ {direction_label}",
        f"방향 근거 │ {direction_reason}",
        f"조회 │ {now.strftime('%Y-%m-%d %H:%M:%S')} KST",
        "",
        "① 이번 변화",
        *event_text,
        "",
        "② 핵심 신호",
        f"{mark(jgb10_3)} JGB10 │ " + (f"{jgb10:.3f}% · 3% 경계" if jgb10 is not None else "확인 불가"),
        f"{mark(curve_up)} JGB 곡선 │ " + (
            f"2Y {jgb2:.3f}({d2:+.1f}bp) · 5Y {jgb5:.3f}({d5:+.1f}bp) · 10Y {jgb10:.3f}({d10:+.1f}bp)"
            if None not in (jgb2, jgb5, jgb10, d2, d5, d10) else "확인 불가"
        ),
        f"{mark(spread_narrow)} 미·일2Y │ " + (f"{spread:.3f}%p · 변화 {fmt_change(spread_change_bp,'bp')}" if spread is not None else "계산 보류"),
        f"{mark(yen_surge)} 엔화 급등: " + (f"USD/JPY {usdjpy:.3f} / {usd_day:+.2f}% / {fx_state['direction']}" if usdjpy is not None and usd_day is not None else "확인 불가"),
        f"{mark(us_rates_down)} 미국2Y │ " + (f"{ust2:.3f}% · {fmt_change(ust2_change_bp,'bp')}" if ust2 is not None else "확인 불가"),
        "",
        *structural_lines(structural),
        f"• 후행시장 │ VIX {vix_text} · Nikkei {nik_text} · Nasdaq {nas_text}",
        f"• 전염 확인 │ {confirm_count}/2 · {'동반 청산 신호 있음' if confirm_count else '동반 청산 신호 없음'}",
        "",
        "④ 판정",
        f"• 현재 방향 │ {direction_label}",
        f"• 위험단계 │ {emoji} {risk_label} · 선행 {leading_count}/5 · 후행 {confirm_count}/2",
        "• JGB 3%만으로 청산 확정하지 않음. 미·일 단기금리차 축소 + USD/JPY 급락 + VIX/주식 전염이 겹칠 때 단계 상향.",
        "",
        "⑤ 다음 확인",
        "• BOJ 정책·JGB 입찰·일본 재무성 주간 해외증권투자",
        "• 특히 USD/JPY 급락, 미·일2Y 급축소, VIX 급등, Nikkei·Nasdaq 동반 약세 여부",
        "",
        "출처",
        f"- 일본 재무성 JGB ({jgb_date}): {JGB_URL}",
        f"- 미국 재무부 국채 ({data_dates.get('ust10','')}): {UST_URL}",
        *structural_source_lines(structural),
    ]

    if jgb_error:
        lines += ["", f"※ JGB 5년 공식값 보강 오류: {jgb_error}"]
    structural_errors = structural.get("errors") or []
    if structural_errors:
        lines += ["", "※ 구조 신호 부분완료: " + " | ".join(structural_errors[:3])]

    (OUT / "global_rates_watch_telegram.md").write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
