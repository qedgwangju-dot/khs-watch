#!/usr/bin/env python3
"""Confirm whether a yen carry unwind is spreading into high-yield target currencies.

This layer is intentionally a confirmation layer, not a stand-alone macro signal.
It derives JPY-per-target cross rates from Yahoo 5-minute USD pairs:
  MXN/JPY proxy = USD/JPY / USD/MXN
  BRL/JPY proxy = USD/JPY / USD/BRL
  ZAR/JPY proxy = USD/JPY / USD/ZAR
A fall means the target currency is weakening against the yen, consistent with carry
positions being reduced. Broad confirmation requires at least 2 of 3 target currencies
to weaken materially while the yen itself is strengthening quickly.

Operational thresholds are monitoring heuristics, not official BIS thresholds:
- target currency stress: 30m <= -0.35% OR 60m <= -0.50% vs JPY
- yen shock: USD/JPY 15m <= -0.50% OR 30m <= -0.75% OR 60m <= -1.00%

BIS research is the economic basis for the currency basket: MXN was hit hardest in the
August-2024 carry unwind, followed by BRL and ZAR; later BIS work again highlighted
MXN/BRL carry-to-risk versus JPY and leveraged positioning in 2026.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import urllib.parse
from dataclasses import asdict, dataclass
from zoneinfo import ZoneInfo

import yen_carry_fx_shock as fx
from khs_source_fetch import fetch_text, record_source_failure

KST = ZoneInfo("Asia/Seoul")
UTC = dt.timezone.utc
ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "out"
DATA.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)

COMPOSITE_STATE = DATA / "yen_carry_composite_state.json"
CONTEXT_JSON = OUT / "yen_carry_target_currency_context.json"
CONTEXT_MD = OUT / "yen_carry_target_currency_context.md"
ALERT_TITLE = OUT / "yen_carry_composite_alert_title.txt"
ALERT_BODY = OUT / "yen_carry_composite_alert.md"
ALERT_JSON = OUT / "yen_carry_composite_alert.json"
COMPOSITE_PENDING = OUT / "yen_carry_composite_pending_state.json"

USER_AGENT = "Mozilla/5.0 khs-yen-carry-target-currency/1.0"
TARGETS = {
    "MXN": ("MXN=X", "멕시코 페소"),
    "BRL": ("BRL=X", "브라질 헤알"),
    "ZAR": ("ZAR=X", "남아공 랜드"),
}
SOURCE_PAGES = {
    "MXN": "https://finance.yahoo.com/quote/MXN=X/",
    "BRL": "https://finance.yahoo.com/quote/BRL=X/",
    "ZAR": "https://finance.yahoo.com/quote/ZAR=X/",
}
TARGET_30M_STRESS_PCT = -0.35
TARGET_60M_STRESS_PCT = -0.50
YEN_60M_SHOCK_PCT = -1.00


@dataclass(frozen=True)
class CrossMove:
    code: str
    label: str
    latest_jpy_per_target: float
    latest_epoch: float
    change_15m_pct: float
    change_30m_pct: float
    change_60m_pct: float
    stressed: bool


def load_json(path: pathlib.Path, default):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, type(default)) else default
    except Exception:
        return default


def write_json(path: pathlib.Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def chart_url(base: str, symbol: str) -> str:
    params = urllib.parse.urlencode(
        {"interval": "5m", "range": "5d", "includePrePost": "true", "events": "div,splits"}
    )
    return f"{base}/{urllib.parse.quote(symbol, safe='')}?{params}"


def fetch_symbol_points(symbol: str) -> list[tuple[float, float]]:
    series: list[list[tuple[float, float]]] = []
    errors: list[str] = []
    for base in fx.YAHOO_BASES:
        url = chart_url(base, symbol)
        text, error = fetch_text(url, USER_AGENT, timeout=18, attempts=2, accept="application/json")
        if error or not text:
            errors.append(error or "empty response")
            continue
        try:
            series.append(fx.valid_points(json.loads(text)))
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
    if not series:
        raise RuntimeError(" | ".join(errors) or f"{symbol} retrieval failed")
    if len(series) == 1:
        return series[0]
    a, b = series[:2]
    a_ts, a_px = a[-1]
    b_ts, b_px = b[-1]
    gap = abs(a_px - b_px) / max(a_px, b_px) * 100.0
    if gap > 0.05 or abs(a_ts - b_ts) > 600:
        raise RuntimeError(
            f"Yahoo query1/query2 mismatch {symbol}: price_gap={gap:.3f}% time_gap={abs(a_ts-b_ts):.0f}s"
        )
    return a if a_ts >= b_ts else b


def source_failure(name: str, url: str, error: str, now: dt.datetime) -> None:
    record_source_failure(
        lane="yen_carry_target_currency",
        source_name=name,
        source_url=url,
        error=error,
        checked_at=now.astimezone(KST),
    )


def cross_series(
    usdjpy: list[tuple[float, float]], usdtarget: list[tuple[float, float]]
) -> list[tuple[float, float]]:
    """Return JPY per 1 unit of target currency using exact common 5-minute timestamps."""
    target_map = {int(ts): px for ts, px in usdtarget if px > 0}
    out: list[tuple[float, float]] = []
    for ts, jpy_per_usd in usdjpy:
        target_per_usd = target_map.get(int(ts))
        if target_per_usd and jpy_per_usd > 0:
            out.append((float(ts), jpy_per_usd / target_per_usd))
    if len(out) < 20:
        raise RuntimeError(f"insufficient aligned 5m points: {len(out)}")
    return out


def reference_value(points: list[tuple[float, float]], minutes: int) -> float:
    latest_ts = points[-1][0]
    target_ts = latest_ts - minutes * 60
    candidates = [(ts, px) for ts, px in points if ts <= target_ts]
    if not candidates:
        raise RuntimeError(f"no {minutes}m reference")
    ts, px = candidates[-1]
    if target_ts - ts > 15 * 60:
        raise RuntimeError(f"stale {minutes}m reference gap={target_ts-ts:.0f}s")
    return px


def pct_change(new: float, old: float) -> float:
    return (new / old - 1.0) * 100.0


def make_cross_move(code: str, label: str, points: list[tuple[float, float]]) -> CrossMove:
    latest_ts, latest = points[-1]
    ch15 = pct_change(latest, reference_value(points, 15))
    ch30 = pct_change(latest, reference_value(points, 30))
    ch60 = pct_change(latest, reference_value(points, 60))
    stressed = ch30 <= TARGET_30M_STRESS_PCT or ch60 <= TARGET_60M_STRESS_PCT
    return CrossMove(code, label, latest, latest_ts, ch15, ch30, ch60, stressed)


def classify_target_spread(moves: list[CrossMove], usdjpy_15m: float, usdjpy_30m: float, usdjpy_60m: float) -> dict:
    stressed = [m.code for m in moves if m.stressed]
    yen_shock = bool(
        usdjpy_15m <= fx.FAST_WARNING_THRESHOLDS[15]
        or usdjpy_30m <= fx.FAST_WARNING_THRESHOLDS[30]
        or usdjpy_60m <= YEN_60M_SHOCK_PCT
    )
    broad = len(stressed) >= 2
    return {
        "yen_shock": yen_shock,
        "stressed_count": len(stressed),
        "stressed_codes": stressed,
        "broad_target_weakness": broad,
        "active_confirmation": broad and yen_shock,
    }


def emoji(level: int) -> str:
    return {0: "🟢", 1: "🟡", 2: "🟠", 3: "🔴"}.get(max(0, min(3, level)), "🔴")


def append_context(body: str, context: dict) -> str:
    if "캐리 투자통화 확산" in body:
        return body
    moves = context.get("moves") or []
    lines = ["캐리 투자통화 확산"]
    for row in moves:
        state = "급락" if row.get("stressed") else "비확인"
        lines.append(
            f"- {row['code']}/JPY: 15분 {row['change_15m_pct']:+.2f}% / 30분 {row['change_30m_pct']:+.2f}% / 60분 {row['change_60m_pct']:+.2f}% → {state}"
        )
    c = context.get("classification") or {}
    if context.get("incomplete"):
        lines.append(f"- 판정: 자료 일부 지연 — {context.get('available_count', 0)}/3개 통화 확인")
    elif c.get("active_confirmation"):
        lines.append(
            f"- 판정: 🟠 실제 캐리 청산 확산 확인 — {c.get('stressed_count', 0)}/3개 투자통화가 엔화 대비 동반 약세"
        )
    elif c.get("broad_target_weakness"):
        lines.append("- 판정: 투자통화 동반 약세는 있으나 엔화 급등 조건 미충족")
    else:
        lines.append("- 판정: 광범위 캐리 투자통화 청산 미확인")
    lines.append("※ USD 교차가 아니라 엔화 대비 교차환율로 달러 강세 오탐을 줄입니다.")
    lines += [
        "",
        "출처",
        "- USD/JPY: Yahoo query1/query2 5분 데이터 교차확인(USD/MXN·USD/BRL·USD/ZAR 조합, 지연 가능)",
    ]
    return body.rstrip() + "\n\n" + "\n".join(lines) + "\n"


def create_alert(now: dt.datetime, pending: dict, context: dict, reason: str) -> None:
    base_level = int(pending.get("unwind_level") or 0)
    if (context.get("classification") or {}).get("active_confirmation"):
        base_level = max(base_level, 2)
    title = f"{emoji(base_level)} 엔캐리 복합 수급 알림"
    unwind_label = str(pending.get("unwind_label") or "현재 엔캐리 청산 위험 미확인")
    rebuild_label = str(pending.get("rebuild_label") or "엔화 재약세·캐리 재구축 미확인")
    lines = [
        f"조회 시각: {now.astimezone(KST).strftime('%Y-%m-%d %H:%M:%S KST')}",
        "",
        "판정",
        f"- 캐리 청산 위험: {unwind_label}",
        f"- 엔화 재약세·캐리 재구축: {rebuild_label}",
        "※ 두 판정은 서로 다른 질문이며 동시에 높거나 서로 엇갈릴 수 있습니다.",
        "",
        "이번 변화",
        f"- {reason}",
    ]
    body = append_context("\n".join(lines), context)
    ALERT_TITLE.write_text(title + "\n", encoding="utf-8")
    ALERT_BODY.write_text(body.rstrip() + "\n", encoding="utf-8")
    payload = {
        "verdict": {
            "unwind_level": int(pending.get("unwind_level") or 0),
            "unwind_label": unwind_label,
            "rebuild_level": int(pending.get("rebuild_level") or 0),
            "rebuild_label": rebuild_label,
            "evidence": pending.get("evidence") or {},
        },
        "reasons": [reason],
        "errors": [],
        "target_currency_confirmation": context,
        "generated_at_kst": now.astimezone(KST).isoformat(timespec="seconds"),
    }
    write_json(ALERT_JSON, payload)


def process(now: dt.datetime | None = None) -> int:
    now = (now or dt.datetime.now(UTC)).astimezone(UTC)
    composite_previous = load_json(COMPOSITE_STATE, {})
    previous = composite_previous.get("target_currency") or {}
    errors: list[str] = []

    symbol_points: dict[str, list[tuple[float, float]]] = {}
    for code, (symbol, _label) in {"JPY": (fx.SYMBOL, "엔화"), **TARGETS}.items():
        try:
            symbol_points[code] = fetch_symbol_points(symbol)
        except Exception as exc:
            errors.append(f"{code}: {type(exc).__name__}: {exc}")
            page = "https://finance.yahoo.com/quote/JPY=X/" if code == "JPY" else SOURCE_PAGES[code]
            source_failure(f"Yahoo {code}", page, str(exc), now)

    moves: list[CrossMove] = []
    if "JPY" in symbol_points:
        for code, (_symbol, label) in TARGETS.items():
            if code not in symbol_points:
                continue
            try:
                moves.append(make_cross_move(code, label, cross_series(symbol_points["JPY"], symbol_points[code])))
            except Exception as exc:
                errors.append(f"{code}/JPY: {type(exc).__name__}: {exc}")

    available = len(moves)
    incomplete = available < 2 or "JPY" not in symbol_points
    classification = {
        "yen_shock": False,
        "stressed_count": 0,
        "stressed_codes": [],
        "broad_target_weakness": False,
        "active_confirmation": False,
    }
    if not incomplete:
        jpy_points = symbol_points["JPY"]
        latest = jpy_points[-1][1]
        ch15 = pct_change(latest, reference_value(jpy_points, 15))
        ch30 = pct_change(latest, reference_value(jpy_points, 30))
        ch60 = pct_change(latest, reference_value(jpy_points, 60))
        classification = classify_target_spread(moves, ch15, ch30, ch60)
    else:
        ch15 = ch30 = ch60 = 0.0
        if previous.get("initialized"):
            classification["active_confirmation"] = bool(previous.get("active_confirmation"))

    context = {
        "checked_at_kst": now.astimezone(KST).isoformat(timespec="seconds"),
        "available_count": available,
        "incomplete": incomplete,
        "usd_jpy_changes": {"15m_pct": ch15, "30m_pct": ch30, "60m_pct": ch60},
        "moves": [asdict(m) for m in moves],
        "classification": classification,
        "thresholds": {
            "target_30m_pct": TARGET_30M_STRESS_PCT,
            "target_60m_pct": TARGET_60M_STRESS_PCT,
            "yen_15m_pct": fx.FAST_WARNING_THRESHOLDS[15],
            "yen_30m_pct": fx.FAST_WARNING_THRESHOLDS[30],
            "yen_60m_pct": YEN_60M_SHOCK_PCT,
        },
        "errors": errors,
    }
    write_json(CONTEXT_JSON, context)

    md = [
        "# 엔캐리 투자통화 확산 확인",
        f"- 조회시각(KST): {context['checked_at_kst']}",
        f"- 확인 통화: {available}/3",
        f"- 엔화 급등 조건: {'충족' if classification.get('yen_shock') else '미충족'}",
        f"- 투자통화 동반 약세: {classification.get('stressed_count', 0)}/3",
        f"- 청산 확산 확인: {'예' if classification.get('active_confirmation') else '아니오'}",
    ]
    if errors:
        md += ["", "## 자료 확인 지연"] + [f"- {e}" for e in errors]
    CONTEXT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")

    pending = {
        "initialized": True,
        "updated_at_kst": context["checked_at_kst"],
        "active_confirmation": bool(classification.get("active_confirmation")),
        "stressed_count": int(classification.get("stressed_count") or 0),
        "stressed_codes": list(classification.get("stressed_codes") or []),
        "available_count": available,
    }
    composite_pending = load_json(COMPOSITE_PENDING, {})
    if composite_pending:
        composite_pending["target_currency"] = pending
        write_json(COMPOSITE_PENDING, composite_pending)

    reason = None
    if previous.get("initialized") and not incomplete:
        old_active = bool(previous.get("active_confirmation"))
        new_active = bool(pending["active_confirmation"])
        old_count = int(previous.get("stressed_count") or 0)
        new_count = int(pending["stressed_count"])
        if new_active and not old_active:
            reason = f"캐리 투자통화 청산 확산 확인: {','.join(pending['stressed_codes'])} 중 {new_count}/3 동반 약세"
        elif old_active and not new_active:
            reason = "캐리 투자통화 청산 확산 신호 해제"
        elif new_active and new_count == 3 and old_count < 3:
            reason = "캐리 투자통화 청산 확산 심화: MXN·BRL·ZAR 3개 모두 엔화 대비 급락"

    if ALERT_BODY.exists():
        body = ALERT_BODY.read_text(encoding="utf-8")
        ALERT_BODY.write_text(append_context(body, context).rstrip() + "\n", encoding="utf-8")
        payload = load_json(ALERT_JSON, {})
        payload["target_currency_confirmation"] = context
        write_json(ALERT_JSON, payload)
    elif reason:
        composite = load_json(COMPOSITE_PENDING, {})
        if composite:
            create_alert(now, composite, context, reason)

    print(
        json.dumps(
            {
                "active_confirmation": classification.get("active_confirmation"),
                "stressed_count": classification.get("stressed_count"),
                "available_count": available,
                "alert_reason": reason,
                "errors": len(errors),
            },
            ensure_ascii=False,
        )
    )
    return 0


def main() -> int:
    return process()


if __name__ == "__main__":
    raise SystemExit(main())
