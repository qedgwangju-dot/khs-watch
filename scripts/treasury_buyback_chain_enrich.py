#!/usr/bin/env python3
"""Append the existing Treasury buyback policy alert with execution and CTA reaction context.

This is a post-processing layer only. It does not own event detection and does not
create a separate alert lane. The official policy watcher still decides whether an
alert exists. This layer only adds the chain requested by the user:
policy/operation cap -> actual accepted amount -> long-yield reaction -> CTA squeeze
confirmation -> failure conditions.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import treasury_buyback_execution_watch as execution

ROOT = Path(__file__).resolve().parents[1]
ALERT = ROOT / "out" / "treasury_buyback_policy_alert.html"
DETAIL = ROOT / "out" / "treasury_buyback_policy_detail.json"
CTA_STATE = ROOT / "data" / "treasury_cta_squeeze_state.json"
KST = ZoneInfo("Asia/Seoul")
HEADING = "<b>발표→집행→금리·CTA 확인</b>"
CTA_FRESH_HOURS = 6.0


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def num(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "").replace("$", ""))
    except Exception:
        return None


def fmt_usd_bn(value: float | None) -> str:
    return "확인 불가" if value is None else f"${value / 1e9:,.3f}B"


def fmt_pct(value: float | None) -> str:
    return "확인 불가" if value is None else f"{value:.1f}%"


def latest_execution() -> dict:
    row = execution.latest_long_end_result()
    maximum = num(row.get("max_par_amt_redeemed"))
    offered = num(row.get("total_par_amt_offered"))
    accepted = num(row.get("total_par_amt_accepted"))
    cap_use = accepted / maximum * 100 if maximum and accepted is not None else None
    accept_offer = accepted / offered * 100 if offered and accepted is not None else None
    fx, fx_date = execution.latest_fx()
    return {
        "operation_date": str(row.get("operation_date") or ""),
        "bucket": str(row.get("maturity_bucket") or "장기물"),
        "maximum": maximum,
        "offered": offered,
        "accepted": accepted,
        "cap_use_pct": cap_use,
        "accept_offer_pct": accept_offer,
        "maximum_krw": execution.fmt_krw_from_usd(maximum, fx) if maximum is not None else "확인 불가",
        "accepted_krw": execution.fmt_krw_from_usd(accepted, fx) if accepted is not None else "확인 불가",
        "fx": fx,
        "fx_date": fx_date,
        "source": execution.BUYBACK_RESULTS_PAGE,
    }


def _cta_age_hours(raw: str) -> float | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=KST)
        return max(0.0, (datetime.now(KST) - parsed.astimezone(KST)).total_seconds() / 3600.0)
    except Exception:
        return None


def cta_context() -> dict:
    state = load_json(CTA_STATE)
    snapshot = state.get("snapshot") or {}
    yield10 = snapshot.get("yield10") or {}
    cme = snapshot.get("cme") or {}
    gate = state.get("last_gate") or {}
    last_checked = str(state.get("last_checked_kst") or "")
    age_hours = _cta_age_hours(last_checked)
    stale = age_hours is None or age_hours > CTA_FRESH_HOURS

    price_rows = []
    for symbol in ("ZN", "ZB", "UB"):
        row = cme.get(symbol) or {}
        pct = num(row.get("pct_change"))
        if pct is not None:
            price_rows.append((symbol, pct))

    rising = [symbol for symbol, pct in price_rows if pct > 0]
    falling = [symbol for symbol, pct in price_rows if pct < 0]
    composite = bool(gate.get("composite_confirmed"))
    short_bias = bool(state.get("short_bias_active"))

    if composite:
        underlying_verdict = "CTA 숏커버 복합 확인"
    elif short_bias and rising:
        underlying_verdict = "CTA 숏 포지션은 남아 있고 국채선물 반등이 일부 확인 — 청산 후보, 아직 확정 아님"
    elif short_bias and falling:
        underlying_verdict = "CTA 숏 편향은 남아 있으나 국채선물이 하락 — 숏커버 확인 안 됨"
    elif short_bias:
        underlying_verdict = "CTA 숏 편향은 남아 있으나 가격 확인 부족 — 숏커버 확정 전"
    else:
        underlying_verdict = "CTA 숏 편향 자체가 약화 — 숏커버 촉매 민감도 낮음"

    if stale:
        age_text = "시각 확인 불가" if age_hours is None else f"{age_hours:.1f}시간 전"
        verdict = f"CTA 상태가 오래됨({age_text}) — 현재 반응 확정에 사용하지 않음; 최근 상태: {underlying_verdict}"
    else:
        verdict = underlying_verdict

    return {
        "last_checked_kst": last_checked or "확인 불가",
        "age_hours": age_hours,
        "stale": stale,
        "yield10_date": str(yield10.get("date") or "확인 불가"),
        "yield10": num(yield10.get("yield")),
        "yield10_z20": num(yield10.get("z20")),
        "short_bias_active": short_bias,
        "composite_confirmed": composite and not stale,
        "futures_price_same_scope_oi": bool(gate.get("futures_price_same_scope_oi")),
        "futures": {symbol: pct for symbol, pct in price_rows},
        "verdict": verdict,
        "underlying_verdict": underlying_verdict,
    }


def causal_context(detail: dict) -> dict:
    snapshot = detail.get("bessent_causal_snapshot") or detail.get("causal_snapshot") or {}
    values = snapshot.get("common_values") or {}
    changes = snapshot.get("common_changes") or {}
    return {
        "date": str(snapshot.get("common_date") or "확인 불가"),
        "nom10": num(values.get("nom10")),
        "nom10_bp": num(changes.get("nom_bp")),
        "real10_bp": num(changes.get("real_bp")),
        "bei10_bp": num(changes.get("bei_bp")),
        "verdict": str(snapshot.get("verdict") or detail.get("bessent_causal_verdict") or "확인 불가"),
    }


def failure_lines(exe: dict, causal: dict, cta: dict) -> list[str]:
    failures: list[str] = []
    cap_use = exe.get("cap_use_pct")
    nom_bp = causal.get("nom10_bp")

    if cap_use is not None and cap_use < 80:
        failures.append(f"실제 집행이 운영 상한의 {cap_use:.1f}%에 그침")
    if nom_bp is not None and nom_bp > 0:
        failures.append(f"10년 명목금리가 공통 비교일 기준 {nom_bp:+.1f}bp 상승")
    if cta.get("stale"):
        failures.append("CTA 상태가 6시간 신선도 기준을 넘겨 현재 반응 확인 불가")
    elif not cta.get("composite_confirmed"):
        failures.append("CTA 숏커버 복합 확인이 아직 없음")
    if not failures:
        failures.append("현재 핵심 실패 조건은 충족되지 않음")
    return failures[:3]


def build_block(exe: dict, causal: dict, cta: dict) -> str:
    max_text = fmt_usd_bn(exe.get("maximum"))
    accepted_text = fmt_usd_bn(exe.get("accepted"))
    cap_use = fmt_pct(exe.get("cap_use_pct"))
    nom10 = causal.get("nom10")
    nom10_bp = causal.get("nom10_bp")
    y10 = "확인 불가" if nom10 is None else f"{nom10:.2f}%"
    ychg = "" if nom10_bp is None else f" ({nom10_bp:+.1f}bp)"

    futures = cta.get("futures") or {}
    futures_text = " · ".join(
        f"{symbol} {pct:+.2f}%" for symbol, pct in futures.items()
    ) or "가격 확인 불가"

    failures = " / ".join(failure_lines(exe, causal, cta))
    return "\n".join(
        [
            "",
            HEADING,
            f"• ① 운영 상한: {max_text}({exe.get('maximum_krw')}) · {exe.get('bucket')} · {exe.get('operation_date')}",
            f"• ② 실제 집행: {accepted_text}({exe.get('accepted_krw')}) · 상한 사용 {cap_use}",
            f"• ③ 금리 반응: 10년 명목금리 {y10}{ychg} · {causal.get('verdict')}",
            f"• ④ CTA 반응: {cta.get('verdict')} · 상태 {cta.get('last_checked_kst')} · {futures_text}",
            f"• 실패 조건: {failures}",
            "• 해석: 바이백은 발표 규모만 보지 않고 실제 매입액이 상한을 얼마나 채웠는지, 그 뒤 장기금리가 내려갔는지, 마지막으로 CTA 숏커버가 확인됐는지 순서대로 판정합니다.",
        ]
    )


def compact_block(exe: dict, causal: dict, cta: dict) -> str:
    nom_bp = causal.get("nom10_bp")
    ychg = "확인 불가" if nom_bp is None else f"{nom_bp:+.1f}bp"
    return "\n".join(
        [
            "",
            HEADING,
            f"• 상한 {fmt_usd_bn(exe.get('maximum'))} → 실제 {fmt_usd_bn(exe.get('accepted'))} · 상한 사용 {fmt_pct(exe.get('cap_use_pct'))}",
            f"• 10년물 {ychg} · CTA: {cta.get('verdict')}",
            f"• 실패 조건: {' / '.join(failure_lines(exe, causal, cta))}",
        ]
    )


def main() -> int:
    if not ALERT.exists():
        print("treasury_buyback_chain_enrich=skipped_no_policy_alert")
        return 0

    text = ALERT.read_text(encoding="utf-8").rstrip()
    if HEADING in text:
        print("treasury_buyback_chain_enrich=already_present")
        return 0

    detail = load_json(DETAIL)
    exe = latest_execution()
    causal = causal_context(detail)
    cta = cta_context()

    block = build_block(exe, causal, cta)
    if len(text) + len(block) > 3950:
        block = compact_block(exe, causal, cta)
    if len(text) + len(block) > 4000:
        raise RuntimeError(
            f"Treasury policy alert too long after chain enrichment: {len(text) + len(block)}"
        )

    ALERT.write_text(text + block + "\n", encoding="utf-8")
    detail["buyback_execution_chain"] = {
        "enriched_at_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "execution": exe,
        "causal": causal,
        "cta": cta,
        "failure_conditions": failure_lines(exe, causal, cta),
    }
    DETAIL.write_text(
        json.dumps(detail, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("treasury_buyback_chain_enrich=added")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
