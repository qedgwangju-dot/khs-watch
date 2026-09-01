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
UA = "khs-watch-global-rates-telegram-formatter/1.1"


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
    survey = structural.get("boj_survey") or {}
    intervention = structural.get("intervention") or {}
    fx = structural.get("fx") or {}
    lines = ["②-1 실제 자금 수요·시장 기능"]

    if auction:
        accepted_yen = fnum(auction.get("accepted_billion_yen"))
        accepted_yen = None if accepted_yen is None else accepted_yen * 1e9
        lines.append(
            "- JGB 입찰: "
            f"{str(auction.get('tenor','')).replace('-Year','년')} {auction.get('grade','확인 불가')} / "
            f"응찰배율 {fnum(auction.get('bid_to_cover')):.2f}배 / "
            f"꼬리 {fnum(auction.get('tail_bp')):.1f}bp / "
            f"낙찰 {format_yen_trillion(accepted_yen)}({format_krw(auction.get('accepted_krw'))})."
        )
    else:
        lines.append("- JGB 입찰: 최근 공식 결과 확인 불가.")

    if gpif:
        actual = gpif.get("actual_pct") or {}
        target = gpif.get("target_pct") or {}
        tol = gpif.get("tolerance_pp") or {}
        domestic = fnum(actual.get("domestic_bonds"))
        target_domestic = fnum(target.get("domestic_bonds"))
        tolerance = fnum(tol.get("domestic_bonds"))
        if None not in (domestic, target_domestic, tolerance):
            low, high = target_domestic - tolerance, target_domestic + tolerance
            lines.append(
                f"- GPIF: 국내채권 실제 {domestic:.2f}% / 목표 {target_domestic:.0f}% / 허용 {low:.0f}~{high:.0f}%. "
                f"1%p = {fnum(gpif.get('one_pct_point_trillion_yen')):.2f}조엔({format_krw(gpif.get('one_pct_point_krw'))})."
            )
        lines.append(f"- GPIF 제로섬: {gpif.get('zero_sum_summary','첫 기준선 저장 — 다음 공식 분기와 비교')}.")
    else:
        lines.append("- GPIF: 공식 자산배분 확인 불가 — 추정값 사용 안 함.")

    if survey:
        lines.append(
            f"- BOJ 채권시장 서베이: {survey.get('label','확인 불가')} / 공개일 {survey.get('posted_date','확인 불가')}. "
            "시장 기능도·장기금리 전망은 공식 원문 수치가 확인될 때만 해석."
        )
    else:
        lines.append("- BOJ 채권시장 서베이: 최신 공식 발표 확인 불가.")

    if intervention:
        amount = intervention.get("amount_yen")
        if amount is not None:
            lines.append(
                f"- 외환개입: 최신 월간 총액 {format_yen_trillion(amount)}({format_krw(intervention.get('amount_krw'))}). "
                "실시일별 금액이 없는 월간 총액으로 1조엔당 개입효율을 계산하지 않음."
            )
        if intervention.get("next_daily_detail_release"):
            lines.append(f"- 개입 효율 다음 검산: {intervention['next_daily_detail_release']} 공식 일별자료 공개 후 24시간·5거래일 잔존효과 계산.")

    if fx:
        lines.append(
            f"- 원화 환산 기준: FRED 동일 기준일 {fx.get('date')} / USD/KRW {fnum(fx.get('usdkrw')):,.2f} / "
            f"USD/JPY {fnum(fx.get('usdjpy')):.3f} / 1엔={fnum(fx.get('yenkrw')):.4f}원."
        )
    return lines


def structural_source_lines(structural: dict) -> list[str]:
    lines: list[str] = []
    auction = structural.get("auction") or {}
    gpif = structural.get("gpif") or {}
    survey = structural.get("boj_survey") or {}
    intervention = structural.get("intervention") or {}
    if auction.get("url"):
        lines.append(f"- 일본 재무성 JGB 입찰 결과: {auction['url']}")
    if gpif.get("url"):
        lines.append(f"- GPIF 최신 자산배분: {gpif['url']}")
    if gpif.get("target_pct"):
        lines.append("- GPIF 기본 포트폴리오: https://www.gpif.go.jp/gpif/portfolio.html")
    if survey.get("url"):
        lines.append(f"- BOJ 채권시장 서베이: {survey['url']}")
    if intervention.get("url"):
        lines.append(f"- 일본 재무성 외환시장 개입 실적: {intervention['url']}")
    if intervention.get("overview_url"):
        lines.append(f"- 일본 재무성 외환개입 공개 일정: {intervention['overview_url']}")
    return lines


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
    yen_surge = bool((usdjpy is not None and usdjpy <= 155.0) or (usd_day is not None and usd_day <= -2.0))
    vix_spike = bool(sig.get("vix_spike_20pct"))
    equity_joint = bool(confirm.get("equity_joint_weakness"))
    leading_count = sum([jgb10_3, curve_up, spread_narrow, us_rates_down, yen_surge])
    confirm_count = sum([vix_spike, equity_joint])

    if yen_surge and spread_narrow and (vix_spike or equity_joint):
        risk_level, risk_label, emoji = 3, "실제 엔캐리 청산 위험 높음", "🔴"
    elif (yen_surge and (spread_narrow or curve_up)) or (jgb10_3 and curve_up and spread_narrow):
        risk_level, risk_label, emoji = 2, "엔캐리 청산 경계 강화", "🟠"
    elif leading_count >= 2 or (jgb10_3 and (vix_spike or equity_joint)):
        risk_level, risk_label, emoji = 1, "구조적 경계 상승", "🟡"
    else:
        risk_level, risk_label, emoji = 0, "관찰", "🟢"

    old_level = int(telegram_state.get("risk_level") or 0)
    primary_event = bool(base_alert.get("events"))
    risk_changed = risk_level != old_level
    structural_changed = bool(structural_event.get("events"))
    should_send = force_test or primary_event or risk_changed or structural_changed

    pending_state = {
        "risk_level": risk_level,
        "risk_label": risk_label,
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "signals": {
            "jgb10_3": jgb10_3,
            "jgb_curve_up": curve_up,
            "us_jp_2y_spread_narrow": spread_narrow,
            "us_2y_down": us_rates_down,
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

    lines = [
        f"[글로벌 금리·엔캐리 경보] {emoji}",
        f"판정: {risk_label}",
        f"조회: {now.strftime('%Y-%m-%d %H:%M:%S')} KST",
        "",
        "① 무엇이 바뀌었나",
        *event_text,
        "",
        "② 선행 신호",
        f"{mark(jgb10_3)} JGB 10Y 3.0% 경계: " + (f"{jgb10:.3f}%" if jgb10 is not None else "확인 불가"),
        f"{mark(curve_up)} 일본 금리곡선 동반 상승: " + (
            f"2Y {jgb2:.3f}%({d2:+.1f}bp) / 5Y {jgb5:.3f}%({d5:+.1f}bp) / 10Y {jgb10:.3f}%({d10:+.1f}bp)"
            if None not in (jgb2, jgb5, jgb10, d2, d5, d10) else "5년 포함 일부 확인 불가"
        ),
        f"{mark(spread_narrow)} 미·일 2Y 금리차 축소: " + (f"{spread:.3f}%p / 변화 {fmt_change(spread_change_bp,'bp')}" if spread is not None else "확인 불가"),
        f"{mark(us_rates_down)} 미국 2Y 하락 가속: " + (f"{ust2:.3f}% / 변화 {fmt_change(ust2_change_bp,'bp')}" if ust2 is not None else "확인 불가"),
        f"{mark(yen_surge)} 엔화 급등: " + (f"USD/JPY {usdjpy:.3f} / 1일 {usd_day:+.2f}%" if usdjpy is not None and usd_day is not None else "확인 불가"),
        "⬜ BOJ 시장 내재 인상확률: 신뢰 가능한 공개 자동 시계열 미연결. 주요매체가 숫자를 명시한 경우에만 ‘보도값’으로 별도 사용 — 임의 추정 안 함.",
        "",
        *structural_lines(structural),
        "",
        "③ 실제 청산 전염 확인",
        f"{mark(vix_spike)} VIX 급등: " + (f"{vix.get('value')} / 1일 {vix_ch:+.2f}% / 기준일 {vix.get('date')}" if vix else "확인 불가"),
        f"{mark(equity_joint)} Nikkei·Nasdaq 동반 급락: " + (
            f"Nikkei {nik_ch:+.2f}%({nikkei.get('date')}) / Nasdaq {nas_ch:+.2f}%({nasdaq.get('date')})"
            if nik_ch is not None and nas_ch is not None else "확인 불가"
        ),
        "- VIX·Nikkei·Nasdaq은 FRED 일간 후행 확인값. 장중 실시간 값으로 오인하지 않음.",
        "- FX 변동성 직접지수는 아직 미연결. 현재는 USD/JPY 자체 급변과 VIX를 보조 확인.",
        "",
        "④ 정확한 의미",
        "- JGB 10Y 3% = 엔캐리 자동 청산선 아님. 일본 FY2026 예산 금리 가정과 겹치는 재정·심리 경계선.",
        "- JGB 금리가 올라가도 입찰 수요가 강하면 ‘시장 스트레스’로 자동 승격하지 않음. 응찰배율·꼬리까지 같이 확인.",
        "- GPIF 국내채권 확대는 반대편 자산이 무엇인지 확인해야 환율·미국채·주식 수급 방향을 판단할 수 있음.",
        "- 실제 청산은 BOJ 긴축·일본 단기금리↑ → 미·일 2년 금리차↓ → USD/JPY 급락 → 변동성·주식 전염 순서가 핵심.",
        "- 2024년 8월 급락은 JGB 3% 때문이 아니라 BOJ 인상 + 미국 금리 하락 + 엔화 급등 + 레버리지 청산이 겹친 사례.",
        "",
        "⑤ 시장 영향",
        "- 엔화: 청산 확인 시 강세 가속 가능. GPIF 해외자산 축소가 동반되면 환류 신호 강화.",
        "- 미국채: GPIF가 국내채권을 늘리면서 외국채권을 줄이는 경우에만 직접 수급 부담을 강하게 판정.",
        "- Nasdaq·SOX·XBI·KOSDAQ: 실질금리·레버리지 축소가 겹치면 고밸류·듀레이션 자산 부담.",
        "- Nikkei: 엔화 급등과 디레버리징이 동시에 나오면 수출주·레버리지 포지션 부담 확대.",
        "",
        "⑥ 현재 한 줄",
        f"{emoji} {risk_label}: 선행 {leading_count}/5, 후행확인 {confirm_count}/2. 구조 신호는 실제 자금행동 확인용이며 단독으로 엔캐리 청산을 확정하지 않습니다.",
        "",
        "출처",
        f"- 일본 재무성 JGB ({jgb_date}): {JGB_URL}",
        f"- 일본 FY2026 예산 가정: {JAPAN_BUDGET_URL}",
        f"- 미국 재무부 국채 ({data_dates.get('ust10','')}): {UST_URL}",
        f"- Federal Reserve/FRED USD/JPY: {FRED_USDJPY}",
        f"- BIS 2024년 8월 캐리 청산 분석: {BIS_2024}",
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
