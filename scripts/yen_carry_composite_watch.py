#!/usr/bin/env python3
"""Multi-factor yen-carry monitor.

This lane deliberately answers two separate questions:
1) Is a leveraged yen-carry unwind becoming more likely / active?
2) Is yen weakness / carry rebuilding pressure re-emerging?

It never treats one level such as JGB 10Y 3% as an automatic unwind trigger.
Fast USD/JPY data are Yahoo 5-minute observations and may be delayed. Structural
inputs use official Japan MOF, U.S. Treasury and CFTC data.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import io
import json
import math
import pathlib
import statistics
import urllib.parse
from dataclasses import asdict, dataclass
from zoneinfo import ZoneInfo

import global_rates_watch as rates
import yen_carry_fx_shock as fx
from khs_source_fetch import fetch_text, record_source_failure

KST = ZoneInfo("Asia/Seoul")
UTC = dt.timezone.utc
ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "out"
DATA.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)

STATE_PATH = DATA / "yen_carry_composite_state.json"
PENDING_PATH = OUT / "yen_carry_composite_pending_state.json"
ALERT_TITLE_PATH = OUT / "yen_carry_composite_alert_title.txt"
ALERT_BODY_PATH = OUT / "yen_carry_composite_alert.md"
ALERT_JSON_PATH = OUT / "yen_carry_composite_alert.json"
CONFIRM_PATH = OUT / "yen_carry_composite_telegram_confirmed.json"
STATUS_PATH = OUT / "yen_carry_composite_watch.md"

MOF_WEEK_CSV = "https://www.mof.go.jp/policy/international_policy/reference/itn_transactions_in_securities/week.csv"
CFTC_TFF_API = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"
MOF_INTERVENTION_STATEMENT = "https://www.mof.go.jp/english/public_relations/statement/others/20260803073000.html"
USER_AGENT = "Mozilla/5.0 khs-yen-carry-composite/1.0"

# Existing fast-yen thresholds are reused unchanged. Rebuild uses their symmetric mirror.
YEN_WEAK_FAST_15M = 0.50
YEN_WEAK_FAST_30M = 0.75
# Operational volatility flag: current 12h 5-minute return sigma / prior-block median.
FX_VOL_ELEVATED_RATIO = 1.50
# Same short-spread boundary already used by the official-rates yen-carry watcher.
SPREAD_NARROW_LEVEL = 2.00
SPREAD_CHANGE_BP = 10.0
JGB2_CHANGE_BP = 5.0
POLICY_RECENCY_DAYS = 30


@dataclass(frozen=True)
class CftcPosition:
    report_date: str
    open_interest: int
    leveraged_long: int
    leveraged_short: int
    net: int
    net_short: int
    net_short_pct_oi: float
    previous_report_date: str
    previous_net_short: int
    short_covering: bool


@dataclass(frozen=True)
class MofOutwardFlow:
    latest_week: str
    previous_week: str
    latest_two_week_trillion_yen: float
    previous_two_week_trillion_yen: float
    outward_buying: bool
    outward_accelerating: bool


@dataclass(frozen=True)
class FxVol:
    current_12h_5m_sigma_bps: float
    baseline_12h_5m_sigma_bps: float | None
    ratio: float | None
    elevated: bool


@dataclass(frozen=True)
class CompositeVerdict:
    unwind_level: int
    unwind_label: str
    rebuild_level: int
    rebuild_label: str
    divergence_short_covering_but_yen_weak: bool
    evidence: dict[str, bool]


def number(value) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace("*", "").replace("△", "-").replace("−", "-")
    try:
        out = float(text)
    except ValueError:
        return None
    return out if math.isfinite(out) else None


def load_json(path: pathlib.Path, default):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, type(default)) else default
    except Exception:
        return default


def source_failure(name: str, url: str, error: str, now: dt.datetime) -> None:
    record_source_failure(
        lane="yen_carry_composite",
        source_name=name,
        source_url=url,
        error=error,
        checked_at=now.astimezone(KST),
    )


def parse_mof_week_csv(text: str) -> MofOutwardFlow:
    """Parse MOF weekly history. Column 7 is outward equity+LT-debt subtotal net.

    Since Jan-2014, positive outward net means residents were net purchasers.
    Units are 100 million yen; divide by 10,000 for trillion yen.
    """
    rows: list[tuple[str, float]] = []
    for row in csv.reader(io.StringIO(text.lstrip("\ufeff"))):
        if len(row) < 12:
            continue
        label = (row[0] or "").strip()
        subtotal = number(row[7])
        if not label or subtotal is None:
            continue
        if not any(ch.isdigit() for ch in label):
            continue
        rows.append((label, subtotal))
    if len(rows) < 4:
        raise RuntimeError(f"MOF weekly CSV needs >=4 data rows, got {len(rows)}")
    latest4 = rows[-4:]
    prior2 = latest4[:2]
    latest2 = latest4[2:]
    prior_sum = sum(v for _, v in prior2) / 10000.0
    latest_sum = sum(v for _, v in latest2) / 10000.0
    return MofOutwardFlow(
        latest_week=latest2[-1][0],
        previous_week=latest2[-2][0],
        latest_two_week_trillion_yen=latest_sum,
        previous_two_week_trillion_yen=prior_sum,
        outward_buying=latest_sum > 0,
        outward_accelerating=latest_sum > 0 and latest_sum > prior_sum,
    )


def fetch_mof_outward(now: dt.datetime) -> MofOutwardFlow:
    text, error = fetch_text(MOF_WEEK_CSV, USER_AGENT, timeout=20, attempts=2, accept="text/csv,text/plain,*/*")
    if error or not text:
        raise RuntimeError(error or "empty MOF weekly CSV")
    return parse_mof_week_csv(text)


def cftc_query_url() -> str:
    select = ",".join(
        [
            "report_date_as_yyyy_mm_dd",
            "open_interest_all",
            "lev_money_positions_long_all",
            "lev_money_positions_short_all",
        ]
    )
    where = "contract_market_name='JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE'"
    params = urllib.parse.urlencode(
        {"$select": select, "$where": where, "$order": "report_date_as_yyyy_mm_dd DESC", "$limit": "2"}
    )
    return f"{CFTC_TFF_API}?{params}"


def parse_cftc_json(text: str) -> CftcPosition:
    rows = json.loads(text)
    if not isinstance(rows, list) or len(rows) < 2:
        raise RuntimeError("CFTC TFF query returned fewer than two JPY rows")

    def row_values(row: dict) -> tuple[str, int, int, int, int, int]:
        date = str(row.get("report_date_as_yyyy_mm_dd") or "")[:10]
        oi = int(float(row["open_interest_all"]))
        long = int(float(row["lev_money_positions_long_all"]))
        short = int(float(row["lev_money_positions_short_all"]))
        net = long - short
        net_short = max(short - long, 0)
        return date, oi, long, short, net, net_short

    cur = row_values(rows[0])
    prev = row_values(rows[1])
    return CftcPosition(
        report_date=cur[0],
        open_interest=cur[1],
        leveraged_long=cur[2],
        leveraged_short=cur[3],
        net=cur[4],
        net_short=cur[5],
        net_short_pct_oi=(cur[5] / cur[1] * 100.0) if cur[1] else 0.0,
        previous_report_date=prev[0],
        previous_net_short=prev[5],
        short_covering=cur[5] < prev[5],
    )


def fetch_cftc(now: dt.datetime) -> CftcPosition:
    url = cftc_query_url()
    text, error = fetch_text(url, USER_AGENT, timeout=20, attempts=2, accept="application/json,*/*")
    if error or not text:
        raise RuntimeError(error or "empty CFTC response")
    return parse_cftc_json(text)


def fx_chart_url(base: str) -> str:
    params = urllib.parse.urlencode({"interval": "5m", "range": "5d", "includePrePost": "true", "events": "div,splits"})
    return f"{base}/{urllib.parse.quote(fx.SYMBOL, safe='')}?{params}"


def fetch_fx_points() -> list[tuple[float, float]]:
    series: list[list[tuple[float, float]]] = []
    errors: list[str] = []
    for base in fx.YAHOO_BASES:
        url = fx_chart_url(base)
        text, error = fetch_text(url, USER_AGENT, timeout=18, attempts=2, accept="application/json")
        if error or not text:
            errors.append(error or "empty response")
            continue
        try:
            series.append(fx.valid_points(json.loads(text)))
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
    if not series:
        raise RuntimeError(" | ".join(errors) or "USD/JPY 5d retrieval failed")
    if len(series) == 1:
        return series[0]
    a, b = series[:2]
    a_ts, a_px = a[-1]
    b_ts, b_px = b[-1]
    gap = abs(a_px - b_px) / max(a_px, b_px) * 100.0
    if gap > 0.03 or abs(a_ts - b_ts) > 600:
        raise RuntimeError(f"Yahoo query1/query2 5d mismatch: price_gap={gap:.3f}% time_gap={abs(a_ts-b_ts):.0f}s")
    return a if a_ts >= b_ts else b


def sigma_bps(points: list[tuple[float, float]], start: float, end: float) -> float | None:
    chosen = [(ts, px) for ts, px in points if start <= ts <= end]
    returns: list[float] = []
    for (ts0, p0), (ts1, p1) in zip(chosen, chosen[1:]):
        # Ignore weekend/data gaps; this is five-minute realized volatility, not gap risk.
        if ts1 - ts0 > 15 * 60 or p0 <= 0 or p1 <= 0:
            continue
        returns.append(math.log(p1 / p0) * 10000.0)
    return statistics.pstdev(returns) if len(returns) >= 12 else None


def realized_fx_vol(points: list[tuple[float, float]]) -> FxVol:
    latest_ts = points[-1][0]
    block = 12 * 3600
    current = sigma_bps(points, latest_ts - block, latest_ts)
    if current is None:
        raise RuntimeError("USD/JPY 12h realized volatility unavailable")
    previous: list[float] = []
    for index in range(1, 5):
        end = latest_ts - index * block
        value = sigma_bps(points, end - block, end)
        if value is not None:
            previous.append(value)
    baseline = statistics.median(previous) if previous else None
    ratio = (current / baseline) if baseline and baseline > 0 else None
    return FxVol(
        current_12h_5m_sigma_bps=current,
        baseline_12h_5m_sigma_bps=baseline,
        ratio=ratio,
        elevated=bool(ratio is not None and ratio >= FX_VOL_ELEVATED_RATIO),
    )


def fetch_policy_context(now: dt.datetime) -> dict:
    text, error = fetch_text(MOF_INTERVENTION_STATEMENT, USER_AGENT, timeout=18, attempts=2)
    if error or not text:
        raise RuntimeError(error or "empty MOF intervention statement")
    plain = html.unescape(text).lower()
    joint = "purchased the japanese yen in coordination with the u.s. department of the treasury" in plain
    further = "will not hesitate to conduct further joint intervention" in plain
    action_date = dt.date(2026, 7, 31)
    age_days = (now.astimezone(KST).date() - action_date).days
    return {
        "official_joint_intervention": joint,
        "further_joint_intervention_signal": further,
        "action_date": action_date.isoformat(),
        "age_days": age_days,
        "recent": joint and 0 <= age_days <= POLICY_RECENCY_DAYS,
    }


def classify(
    *,
    move: fx.FxMove,
    fx_vol: FxVol,
    jgb2: float,
    spread: float,
    previous_jgb2: float | None,
    previous_spread: float | None,
    cftc: CftcPosition | None,
    mof: MofOutwardFlow | None,
    policy: dict | None,
) -> CompositeVerdict:
    jgb2_change_bp = None if previous_jgb2 is None else (jgb2 - previous_jgb2) * 100.0
    spread_change_bp = None if previous_spread is None else (spread - previous_spread) * 100.0

    short_rate_up = bool(jgb2_change_bp is not None and jgb2_change_bp >= JGB2_CHANGE_BP)
    spread_narrow = bool(spread <= SPREAD_NARROW_LEVEL or (spread_change_bp is not None and spread_change_bp <= -SPREAD_CHANGE_BP))
    spread_wide = bool(spread > SPREAD_NARROW_LEVEL and not spread_narrow)
    spread_widening = bool(spread_change_bp is not None and spread_change_bp >= SPREAD_CHANGE_BP)

    yen_strength_fast = bool(
        move.change_15m_pct <= fx.FAST_WARNING_THRESHOLDS[15]
        or move.change_30m_pct <= fx.FAST_WARNING_THRESHOLDS[30]
        or (
            move.sustained_duration_minutes >= fx.SUSTAINED_MIN_DURATION_MINUTES
            and move.sustained_drawdown_pct <= fx.SUSTAINED_WARNING_DRAWDOWN_PCT
            and move.sustained_rebound_pct <= fx.SUSTAINED_MAX_REBOUND_PCT
        )
    )
    yen_weak_fast = bool(move.change_15m_pct >= YEN_WEAK_FAST_15M or move.change_30m_pct >= YEN_WEAK_FAST_30M)
    yen_weak_direction = bool(move.change_30m_pct > 0 or move.change_60m_pct > 0)

    leveraged_net_short = bool(cftc is not None and cftc.net_short > 0)
    short_covering = bool(cftc is not None and cftc.short_covering)
    outward_buying = bool(mof is not None and mof.outward_buying)
    outward_accelerating = bool(mof is not None and mof.outward_accelerating)
    policy_recent = bool(policy and policy.get("recent") and policy.get("further_joint_intervention_signal"))

    unwind_evidence = {
        "일본 단기금리 상승": short_rate_up,
        "미·일 2년 금리차 축소": spread_narrow,
        "USD/JPY 급락·엔화 급등": yen_strength_fast,
        "FX 실현변동성 상승": fx_vol.elevated,
        "레버리지 펀드 엔화 순숏": leveraged_net_short,
        "최근 공식 공동개입·추가개입 경고": policy_recent,
    }
    if yen_strength_fast and (spread_narrow or short_rate_up) and (fx_vol.elevated or policy_recent) and leveraged_net_short:
        unwind_level, unwind_label = 3, "엔캐리 청산 위험 높음"
    elif yen_strength_fast and (spread_narrow or short_rate_up or policy_recent):
        unwind_level, unwind_label = 2, "엔캐리 청산 경계 강화"
    elif sum(bool(v) for v in unwind_evidence.values()) >= 3 and (spread_narrow or short_rate_up):
        unwind_level, unwind_label = 1, "엔캐리 청산 구조적 경계"
    else:
        unwind_level, unwind_label = 0, "엔캐리 청산 미확인"

    divergence = bool(short_covering and yen_weak_direction)
    rebuild_evidence = {
        "USD/JPY 상승·엔화 재약세": yen_weak_fast,
        "USD/JPY 완만한 상승 방향": yen_weak_direction,
        "미·일 2년 금리차 여전히 넓음": spread_wide,
        "미·일 2년 금리차 재확대": spread_widening,
        "일본 거주자 해외주식·장기채 순매수": outward_buying,
        "최근 2주 해외매수 가속": outward_accelerating,
        "레버리지 엔화 숏 축소에도 USD/JPY 상승": divergence,
        "FX 변동성 비상승": not fx_vol.elevated,
    }
    if yen_weak_fast and outward_buying and spread_wide and not fx_vol.elevated:
        rebuild_level, rebuild_label = 3, "엔화 재약세·캐리 재구축 압력 높음"
    elif outward_buying and spread_wide and (yen_weak_direction or divergence or outward_accelerating):
        rebuild_level, rebuild_label = 2, "엔화 재약세·캐리 재구축 압력 강화"
    elif sum(bool(v) for v in rebuild_evidence.values()) >= 4 and (outward_buying or yen_weak_direction):
        rebuild_level, rebuild_label = 1, "엔화 재약세·캐리 재구축 경계"
    else:
        rebuild_level, rebuild_label = 0, "엔화 재약세·캐리 재구축 미확인"

    evidence = {"unwind::" + k: v for k, v in unwind_evidence.items()}
    evidence.update({"rebuild::" + k: v for k, v in rebuild_evidence.items()})
    return CompositeVerdict(unwind_level, unwind_label, rebuild_level, rebuild_label, divergence, evidence)


def make_state(
    verdict: CompositeVerdict,
    *,
    now: dt.datetime,
    jgb2,
    ust2,
    spread,
    move,
    fx_vol,
    cftc,
    mof,
    policy,
) -> dict:
    return {
        "initialized": True,
        "updated_at_kst": now.astimezone(KST).isoformat(timespec="seconds"),
        "unwind_level": verdict.unwind_level,
        "unwind_label": verdict.unwind_label,
        "rebuild_level": verdict.rebuild_level,
        "rebuild_label": verdict.rebuild_label,
        "divergence_short_covering_but_yen_weak": verdict.divergence_short_covering_but_yen_weak,
        "source_dates": {
            "jgb2": jgb2.date,
            "ust2": ust2.date,
            "cftc": cftc.report_date if cftc else None,
            "mof_week": mof.latest_week if mof else None,
            "policy_action": (policy or {}).get("action_date"),
        },
        "values": {
            "jgb2": jgb2.value,
            "ust2": ust2.value,
            "us_jp_2y_spread": spread,
            "usdjpy": move.latest_price,
            "usdjpy_15m_pct": move.change_15m_pct,
            "usdjpy_30m_pct": move.change_30m_pct,
            "usdjpy_60m_pct": move.change_60m_pct,
            "usdjpy_12h_drawdown_pct": move.sustained_drawdown_pct,
            "fx_12h_5m_sigma_bps": fx_vol.current_12h_5m_sigma_bps,
            "fx_vol_ratio": fx_vol.ratio,
            "cftc_net_short": cftc.net_short if cftc else None,
            "cftc_net_short_pct_oi": cftc.net_short_pct_oi if cftc else None,
            "mof_latest_2w_outward_trillion_yen": mof.latest_two_week_trillion_yen if mof else None,
            "mof_prior_2w_outward_trillion_yen": mof.previous_two_week_trillion_yen if mof else None,
        },
        "evidence": verdict.evidence,
    }


def source_changed(previous: dict, pending: dict, key: str) -> bool:
    old = (previous.get("source_dates") or {}).get(key)
    new = (pending.get("source_dates") or {}).get(key)
    return bool(old and new and old != new)


def should_alert(previous: dict, pending: dict, verdict: CompositeVerdict) -> tuple[bool, list[str]]:
    if not previous.get("initialized"):
        return False, ["최초 기준값 저장"]
    reasons: list[str] = []
    if int(previous.get("unwind_level") or 0) != verdict.unwind_level:
        reasons.append(f"청산 위험 단계 변화: {previous.get('unwind_label','미확인')} → {verdict.unwind_label}")
    if int(previous.get("rebuild_level") or 0) != verdict.rebuild_level:
        reasons.append(f"재구축 단계 변화: {previous.get('rebuild_label','미확인')} → {verdict.rebuild_label}")
    old_div = bool(previous.get("divergence_short_covering_but_yen_weak"))
    if verdict.divergence_short_covering_but_yen_weak and not old_div:
        reasons.append("레버리지 엔화 숏 축소에도 USD/JPY 상승이라는 괴리 새로 확인")
    if source_changed(previous, pending, "cftc") and (verdict.unwind_level > 0 or verdict.rebuild_level > 0):
        reasons.append("새 CFTC 레버리지 포지션 발표")
    if source_changed(previous, pending, "mof_week") and (verdict.unwind_level > 0 or verdict.rebuild_level > 0):
        reasons.append("새 일본 재무성 해외증권투자 발표")
    return bool(reasons), reasons


def fmt_bool(value: bool) -> str:
    return "✅" if value else "⬜"


def build_message(
    *,
    now: dt.datetime,
    verdict: CompositeVerdict,
    reasons: list[str],
    jgb2,
    ust2,
    spread: float,
    move: fx.FxMove,
    fx_vol: FxVol,
    cftc: CftcPosition | None,
    mof: MofOutwardFlow | None,
    policy: dict | None,
    errors: list[str],
) -> tuple[str, str, dict]:
    top = max(verdict.unwind_level, verdict.rebuild_level)
    title = ("🔴" if top >= 3 else "🟠" if top >= 2 else "🟡") + " 엔캐리 복합 수급 알림"
    lines = [
        f"조회 시각: {now.astimezone(KST).strftime('%Y-%m-%d %H:%M:%S KST')}",
        "",
        "판정",
        f"- 캐리 청산 위험: {verdict.unwind_label}",
        f"- 엔화 재약세·캐리 재구축: {verdict.rebuild_label}",
        "※ 두 판정은 서로 다른 질문이며 동시에 높거나 서로 엇갈릴 수 있습니다.",
        "",
        "이번 변화",
        *[f"- {reason}" for reason in reasons],
        "",
        "시장·금리",
        f"- USD/JPY {move.latest_price:.3f} / 15분 {move.change_15m_pct:+.2f}% / 30분 {move.change_30m_pct:+.2f}% / 60분 {move.change_60m_pct:+.2f}%",
        f"- 최근 12시간 고점 대비 {move.sustained_drawdown_pct:+.2f}% / 반등 {move.sustained_rebound_pct:+.2f}%",
        f"- FX 실현변동성: 5분 수익률 σ {fx_vol.current_12h_5m_sigma_bps:.1f}bp" + (f" / 이전 구간 대비 {fx_vol.ratio:.2f}배" if fx_vol.ratio is not None else " / 비교기준 부족"),
        f"- 일본 2년 JGB(단기금리 프록시) {jgb2.value:.3f}% ({jgb2.date})",
        f"- 미국 2년 국채 {ust2.value:.3f}% ({ust2.date}) / 미·일 2년 금리차 {spread:.3f}%p",
        "",
        "포지션·자금",
    ]
    if cftc:
        direction = "숏 축소" if cftc.short_covering else "숏 확대/유지"
        lines.append(
            f"- CFTC 레버리지 펀드: 엔화 순숏 {cftc.net_short:,}계약 ({cftc.net_short_pct_oi:.1f}% OI), 전주 {cftc.previous_net_short:,}계약 → {direction} ({cftc.report_date})"
        )
    else:
        lines.append("- CFTC 레버리지 펀드: 확인 불가")
    if mof:
        lines.append(
            f"- 일본 거주자 해외주식+장기채: 최근 2주 {mof.latest_two_week_trillion_yen:+.2f}조엔 / 직전 2주 {mof.previous_two_week_trillion_yen:+.2f}조엔 (순매수 +)"
        )
    else:
        lines.append("- 일본 재무성 해외증권투자: 확인 불가")

    lines += ["", "정책"]
    if policy:
        lines.append(
            f"- 미·일 공동 엔화매수 개입: {'공식 확인' if policy.get('official_joint_intervention') else '미확인'} / 추가 공동개입 불사 문구: {'있음' if policy.get('further_joint_intervention_signal') else '없음'} (행동일 {policy.get('action_date')})"
        )
    else:
        lines.append("- 정책개입 신뢰도: 공식 원문 재확인 실패")

    lines += [
        "",
        "정확한 의미",
        "- JGB 10년 3% 같은 단일 숫자로 엔캐리 청산을 단정하지 않습니다.",
        "- 레버리지 엔화 숏이 줄어도 일본의 해외자산 매수와 넓은 금리차가 남으면 USD/JPY는 다시 상승(엔화 약세)할 수 있습니다.",
        "- 따라서 ‘캐리 청산이 있었는가’와 ‘엔화 강세가 지속되는가’를 별도로 판정합니다.",
        "- 일본 2년 JGB는 실제 오버나이트 조달금리가 아니라 자동화 가능한 단기금리 프록시입니다.",
        "- FX 실현변동성은 Yahoo 5분 가격으로 계산한 통계치이며 옵션 내재변동성이 아닙니다.",
        "",
        "출처",
        f"- Japan MOF JGB: {rates.JGB_URL}",
        f"- U.S. Treasury: {rates.UST_XML_BASE}",
        f"- CFTC TFF Futures Only: {CFTC_TFF_API}",
        f"- Japan MOF 해외증권투자: {MOF_WEEK_CSV}",
        f"- Japan MOF 공동개입 공식발표: {MOF_INTERVENTION_STATEMENT}",
        "- USD/JPY: Yahoo query1/query2 5분 데이터 교차확인(동일 공급자, 지연 가능)",
    ]
    if errors:
        lines += ["", "확인 실패"] + [f"- {item}" for item in errors]
    payload = {
        "verdict": asdict(verdict),
        "reasons": reasons,
        "jgb2": asdict(jgb2),
        "ust2": asdict(ust2),
        "spread": spread,
        "fx": asdict(move),
        "fx_vol": asdict(fx_vol),
        "cftc": asdict(cftc) if cftc else None,
        "mof_outward": asdict(mof) if mof else None,
        "policy": policy,
        "errors": errors,
    }
    return title, "\n".join(lines).strip(), payload


def write_json(path: pathlib.Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def clear_alert_files() -> None:
    for path in (ALERT_TITLE_PATH, ALERT_BODY_PATH, ALERT_JSON_PATH, CONFIRM_PATH):
        if path.exists():
            path.unlink()


def process(now: dt.datetime | None = None) -> int:
    now = (now or dt.datetime.now(UTC)).astimezone(UTC)
    clear_alert_files()
    errors: list[str] = []

    try:
        jgb2, _jgb10 = rates.fetch_jgb()
        ust = rates.fetch_ust_curve()
        ust2 = ust["ust2"]
    except Exception as exc:
        STATUS_PATH.write_text(f"# 엔캐리 복합 수급 감시\n- 상태: 금리 필수자료 실패 — {type(exc).__name__}: {exc}\n", encoding="utf-8")
        return 2

    try:
        move = fx.fetch_move()
        points = fetch_fx_points()
        fx_vol = realized_fx_vol(points)
    except Exception as exc:
        STATUS_PATH.write_text(f"# 엔캐리 복합 수급 감시\n- 상태: USD/JPY 필수자료 실패 — {type(exc).__name__}: {exc}\n", encoding="utf-8")
        return 2

    cftc = None
    try:
        cftc = fetch_cftc(now)
    except Exception as exc:
        errors.append(f"CFTC: {type(exc).__name__}: {exc}")
        source_failure("CFTC TFF", CFTC_TFF_API, str(exc), now)

    mof = None
    try:
        mof = fetch_mof_outward(now)
    except Exception as exc:
        errors.append(f"Japan MOF 해외증권투자: {type(exc).__name__}: {exc}")
        source_failure("Japan MOF ITS weekly", MOF_WEEK_CSV, str(exc), now)

    policy = None
    try:
        policy = fetch_policy_context(now)
    except Exception as exc:
        errors.append(f"Japan MOF 공동개입: {type(exc).__name__}: {exc}")
        source_failure("Japan MOF intervention statement", MOF_INTERVENTION_STATEMENT, str(exc), now)

    # We require at least one structural flow/position source in addition to rates and FX.
    if cftc is None and mof is None:
        STATUS_PATH.write_text("# 엔캐리 복합 수급 감시\n- 상태: 부분완료 — CFTC와 일본 해외증권투자 모두 실패, 알림 생성 안 함\n", encoding="utf-8")
        return 2

    spread = ust2.value - jgb2.value
    previous = load_json(STATE_PATH, {})
    prev_values = previous.get("values") or {}
    verdict = classify(
        move=move,
        fx_vol=fx_vol,
        jgb2=jgb2.value,
        spread=spread,
        previous_jgb2=number(prev_values.get("jgb2")),
        previous_spread=number(prev_values.get("us_jp_2y_spread")),
        cftc=cftc,
        mof=mof,
        policy=policy,
    )
    pending = make_state(
        verdict,
        now=now,
        jgb2=jgb2,
        ust2=ust2,
        spread=spread,
        move=move,
        fx_vol=fx_vol,
        cftc=cftc,
        mof=mof,
        policy=policy,
    )
    write_json(PENDING_PATH, pending)
    alert, reasons = should_alert(previous, pending, verdict)

    status = [
        "# 엔캐리 복합 수급 감시",
        f"- 조회시각(KST): {now.astimezone(KST).isoformat(timespec='seconds')}",
        f"- 청산 위험: {verdict.unwind_label}",
        f"- 재약세·재구축: {verdict.rebuild_label}",
        f"- USD/JPY: {move.latest_price:.3f} / 15m {move.change_15m_pct:+.2f}% / 30m {move.change_30m_pct:+.2f}%",
        f"- 미·일 2Y 금리차: {spread:.3f}%p",
        f"- CFTC: {cftc.report_date if cftc else '확인 불가'}",
        f"- MOF 해외증권투자: {mof.latest_week if mof else '확인 불가'}",
        f"- 데이터 오류: {len(errors)}건",
        f"- 신규 알림: {'예' if alert else '아니오'}",
    ]
    if errors:
        status += ["", "## 부분 실패"] + [f"- {e}" for e in errors]
    STATUS_PATH.write_text("\n".join(status) + "\n", encoding="utf-8")

    if alert:
        title, body, payload = build_message(
            now=now,
            verdict=verdict,
            reasons=reasons,
            jgb2=jgb2,
            ust2=ust2,
            spread=spread,
            move=move,
            fx_vol=fx_vol,
            cftc=cftc,
            mof=mof,
            policy=policy,
            errors=errors,
        )
        ALERT_TITLE_PATH.write_text(title + "\n", encoding="utf-8")
        ALERT_BODY_PATH.write_text(body + "\n", encoding="utf-8")
        payload["generated_at_kst"] = now.astimezone(KST).isoformat(timespec="seconds")
        write_json(ALERT_JSON_PATH, payload)

    print(json.dumps({"alerted": alert, "unwind_level": verdict.unwind_level, "rebuild_level": verdict.rebuild_level, "errors": len(errors)}, ensure_ascii=False))
    return 0


def finalize() -> int:
    if not PENDING_PATH.exists():
        print("yen carry composite pending state missing")
        return 1
    if ALERT_BODY_PATH.exists():
        confirmation = load_json(CONFIRM_PATH, {})
        if confirmation.get("status") != "confirmed" or confirmation.get("lane") != "yen_carry_composite":
            print("yen carry composite Telegram confirmation missing; state not advanced")
            return 1
    pending = load_json(PENDING_PATH, {})
    if not pending:
        return 1
    write_json(STATE_PATH, pending)
    print(f"Finalized yen carry composite state: {STATE_PATH}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    return finalize() if args.finalize else process()


if __name__ == "__main__":
    raise SystemExit(main())
