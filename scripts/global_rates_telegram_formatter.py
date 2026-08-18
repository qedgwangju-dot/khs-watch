#!/usr/bin/env python3
"""Build a compact, hierarchy-aware Telegram alert for the global rates / yen-carry watcher.

The formatter deliberately separates:
1) structural boundary: JGB 10Y 3.0% (not an automatic carry-unwind line),
2) leading carry signals: Japan short rates / curve, U.S.-Japan 2Y spread, USD/JPY,
3) confirmation signals: VIX, Nasdaq and Nikkei,
4) historical correction: Aug-2024 unwind was not caused by JGB 10Y at 3%.

It reads outputs produced by global_rates_watch.py and yen_carry_confirmation.py,
then writes a Telegram-ready message only when:
- the primary watcher created a new threshold event, or
- the composite yen-carry risk level changed, or
- FORCE_TEST=1 is supplied by workflow_dispatch.
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
UA = "khs-watch-global-rates-telegram-formatter/1.0"


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
        wc = {norm(x) for x in cands}
        for i, x in enumerate(nh):
            if x in wc:
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
        d = row[di].strip()
        if d and all(x is not None for x in vals):
            good.append((d, vals[0], vals[1], vals[2]))
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


def main() -> int:
    now = datetime.now(KST)
    pending = load_json(OUT / "global_rates_watch_pending_state.json", {})
    previous = load_json(DATA / "global_rates_watch_state.json", {})
    base_alert = load_json(OUT / "global_rates_watch_alert.json", {})
    confirm = load_json(OUT / "yen_carry_confirmation.json", {})
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
        d2, d5, d10 = bp(cur_jgb[1], prev_jgb[1]), bp(cur_jgb[2], prev_jgb[2]), bp(cur_jgb[3], prev_jgb[3])
    except Exception as e:
        jgb_error = f"{type(e).__name__}: {e}"
        jgb_date = str((pending.get("last_source_dates") or {}).get("jgb10") or "")
        jgb2 = fnum(values.get("jgb2"))
        jgb10 = fnum(values.get("jgb10"))
        jgb5 = None
        d2 = d5 = d10 = None

    ust2 = fnum(values.get("ust2"))
    ust10 = fnum(values.get("ust10"))
    ust30 = fnum(values.get("ust30"))
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

    # BOJ OIS is intentionally not fabricated. It stays a manual / future direct-feed slot.
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
    should_send = force_test or primary_event or risk_changed

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
        },
    }
    (OUT / "global_rates_telegram_pending_state.json").write_text(
        json.dumps(pending_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    if not should_send:
        p = OUT / "global_rates_watch_telegram.md"
        if p.exists():
            p.unlink()
        return 0

    events = base_alert.get("events") or []
    event_text = []
    for e in events:
        typ = "진입" if e.get("type") == "trigger" else "해제"
        label = e.get("label") or e.get("metric") or "이벤트"
        val = e.get("value")
        event_text.append(f"- {label}: {typ} ({val})")
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
        "⬜ BOJ OIS 인상확률: 신뢰 가능한 자동 시계열 미연결 — 임의 추정 안 함",
        "",
        "③ 실제 청산 전염 확인",
        f"{mark(vix_spike)} VIX 급등: " + (f"{vix.get('value')} / 1일 {vix_ch:+.2f}%" if vix else "확인 불가"),
        f"{mark(equity_joint)} Nikkei·Nasdaq 동반 급락: " + (
            f"Nikkei {nik_ch:+.2f}% / Nasdaq {nas_ch:+.2f}%" if nik_ch is not None and nas_ch is not None else "확인 불가"
        ),
        "- FX 변동성 직접지수는 아직 미연결. 현재는 USD/JPY 자체 급변과 VIX를 보조 확인.",
        "",
        "④ 정확한 의미",
        "- JGB 10Y 3% = 엔캐리 자동 청산선 아님. 일본 FY2026 예산 금리 가정과 겹치는 재정·심리 경계선.",
        "- 3% 돌파 시 일본채 상대매력↑ → 해외자산 상대매력↓ → 자금 환류·엔화 매수 압력 가능.",
        "- 실제 청산은 BOJ 긴축·일본 단기금리↑ → 미·일 단기금리차↓ → USD/JPY 급락 → 변동성↑ 순서가 핵심.",
        "- 2024년 8월 급락은 JGB 3% 때문이 아니라 BOJ 인상 + 미국 금리 하락 + 엔화 급등 + 레버리지 청산이 겹친 사례.",
        "",
        "⑤ 시장 영향",
        "- 엔화: 청산 확인 시 강세 가속 가능.",
        "- 미국채: 일본 자금 환류가 커지면 장기물 수급 부담. 반대로 미국 경기둔화가 원인이면 금리는 하락할 수 있어 원인 분리 필요.",
        "- Nasdaq·SOX·XBI·KOSDAQ: 실질금리·레버리지 축소가 겹치면 고밸류·듀레이션 자산부터 부담.",
        "- Nikkei: 엔화 급등과 디레버리징이 동시에 나오면 수출주·레버리지 포지션 부담 확대.",
        "",
        "⑥ 현재 한 줄",
        f"{emoji} {risk_label}: 선행 {leading_count}/5, 후행확인 {confirm_count}/2. JGB 3% 하나가 아니라 금리차·엔화·변동성 동시 여부를 우선 봅니다.",
        "",
        "출처",
        f"- 일본 재무성 JGB ({jgb_date}): {JGB_URL}",
        f"- 일본 FY2026 예산 가정: {JAPAN_BUDGET_URL}",
        f"- 미국 재무부 국채 ({data_dates.get('ust10','')}): {UST_URL}",
        f"- Federal Reserve/FRED USD/JPY: {FRED_USDJPY}",
        f"- BIS 2024년 8월 캐리 청산 분석: {BIS_2024}",
    ]
    if jgb_error:
        lines += ["", f"※ JGB 5년 공식값 보강 오류: {jgb_error}"]

    (OUT / "global_rates_watch_telegram.md").write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
