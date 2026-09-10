#!/usr/bin/env python3
"""Add a policy-path / quiet-releveraging layer to the yen-carry composite alert.

This layer separates three questions that should not be conflated:
1) Is BOJ tightening being absorbed gradually while the carry cushion remains?
2) Is the market abruptly repricing the near-term BOJ path even before a policy decision?
3) Is low/stable FX volatility encouraging a crowded yen short to rebuild?

No BOJ OIS probability or economist-consensus number is invented. Until a reliable
machine-readable market source is locked, the script uses only already-verified inputs:
Japan 2Y JGB, the U.S.-Japan 2Y spread, USD/JPY 5-minute moves, realized FX volatility,
and CFTC leveraged-fund yen positioning.

Operational thresholds are monitoring heuristics, not BOJ/BIS official thresholds.
"""
from __future__ import annotations

import json
import pathlib
import re
from datetime import datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "out"

STATE_PATH = DATA / "yen_carry_composite_state.json"
PENDING_PATH = OUT / "yen_carry_composite_pending_state.json"
ALERT_TITLE = OUT / "yen_carry_composite_alert_title.txt"
ALERT_BODY = OUT / "yen_carry_composite_alert.md"
ALERT_JSON = OUT / "yen_carry_composite_alert.json"
CONTEXT_JSON = OUT / "yen_carry_policy_path_context.json"
CONTEXT_MD = OUT / "yen_carry_policy_path_context.md"

JGB2_REPRICING_BP = 10.0
SPREAD_REPRICING_BP = -15.0
WIDE_SPREAD_PCT = 2.00
LOW_VOL_RATIO_MAX = 1.10
ELEVATED_VOL_RATIO = 1.50
CROWDED_NET_SHORT_PCT_OI = 10.0
YEN_SHOCK_15M = -0.50
YEN_SHOCK_30M = -0.75
YEN_SHOCK_60M = -1.00

LEVEL_EMOJI = {0: "🟢", 1: "🟡", 2: "🟠", 3: "🔴"}


def load_json(path: pathlib.Path, default):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, type(default)) else default
    except Exception:
        return default


def write_json(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def classify_context(previous: dict, pending: dict) -> dict:
    pv = previous.get("values") or {}
    cv = pending.get("values") or {}
    ps = previous.get("source_dates") or {}
    cs = pending.get("source_dates") or {}

    jgb2 = num(cv.get("jgb2"))
    prev_jgb2 = num(pv.get("jgb2"))
    spread = num(cv.get("us_jp_2y_spread"))
    prev_spread = num(pv.get("us_jp_2y_spread"))
    vol_ratio = num(cv.get("fx_vol_ratio"))
    net_short = num(cv.get("cftc_net_short"))
    prev_net_short = num(pv.get("cftc_net_short"))
    net_short_pct = num(cv.get("cftc_net_short_pct_oi"))
    ch15 = num(cv.get("usdjpy_15m_pct")) or 0.0
    ch30 = num(cv.get("usdjpy_30m_pct")) or 0.0
    ch60 = num(cv.get("usdjpy_60m_pct")) or 0.0

    new_jgb2 = bool(ps.get("jgb2") and cs.get("jgb2") and ps.get("jgb2") != cs.get("jgb2"))
    new_ust2 = bool(ps.get("ust2") and cs.get("ust2") and ps.get("ust2") != cs.get("ust2"))
    new_cftc = bool(ps.get("cftc") and cs.get("cftc") and ps.get("cftc") != cs.get("cftc"))

    jgb2_change_bp = None if jgb2 is None or prev_jgb2 is None else (jgb2 - prev_jgb2) * 100.0
    spread_change_bp = None if spread is None or prev_spread is None else (spread - prev_spread) * 100.0
    net_short_change = None if net_short is None or prev_net_short is None else net_short - prev_net_short

    yen_shock = ch15 <= YEN_SHOCK_15M or ch30 <= YEN_SHOCK_30M or ch60 <= YEN_SHOCK_60M
    low_or_stable_vol = bool(vol_ratio is not None and vol_ratio <= LOW_VOL_RATIO_MAX)
    elevated_vol = bool(vol_ratio is not None and vol_ratio >= ELEVATED_VOL_RATIO)
    wide_spread = bool(spread is not None and spread > WIDE_SPREAD_PCT)

    jgb2_repricing = bool(new_jgb2 and jgb2_change_bp is not None and jgb2_change_bp >= JGB2_REPRICING_BP)
    spread_repricing = bool((new_jgb2 or new_ust2) and spread_change_bp is not None and spread_change_bp <= SPREAD_REPRICING_BP)
    hawkish_repricing = jgb2_repricing or spread_repricing

    short_build_event = bool(new_cftc and net_short_change is not None and net_short_change > 0)
    crowded_short = bool(net_short_pct is not None and net_short_pct >= CROWDED_NET_SHORT_PCT_OI)
    quiet_crowded_vulnerability = bool(crowded_short and low_or_stable_vol and wide_spread and not yen_shock)
    quiet_releveraging_event = bool(short_build_event and quiet_crowded_vulnerability)

    gradual_absorption = bool(wide_spread and not hawkish_repricing and not yen_shock and not elevated_vol)
    policy_shock_with_yen = bool(hawkish_repricing and yen_shock)

    if policy_shock_with_yen:
        regime = "예상 경로보다 빠른 긴축 재가격·엔화 충격"
    elif quiet_releveraging_event:
        regime = "저변동성 속 레버리지 엔화 숏 재축적"
    elif quiet_crowded_vulnerability:
        regime = "평온하지만 레버리지 취약성 누적"
    elif hawkish_repricing:
        regime = "단기금리 경로 재가격 경계"
    elif gradual_absorption:
        regime = "점진 긴축 흡수·캐리 유지 여지"
    else:
        regime = "혼합·경계"

    risk_floor = 2 if policy_shock_with_yen else 1 if (hawkish_repricing or quiet_crowded_vulnerability) else 0

    return {
        "initialized": True,
        "checked_at_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "regime": regime,
        "risk_floor": risk_floor,
        "new_jgb2": new_jgb2,
        "new_ust2": new_ust2,
        "new_cftc": new_cftc,
        "jgb2_change_bp": jgb2_change_bp,
        "spread_change_bp": spread_change_bp,
        "cftc_net_short_change": net_short_change,
        "cftc_net_short": net_short,
        "cftc_net_short_pct_oi": net_short_pct,
        "fx_vol_ratio": vol_ratio,
        "wide_spread": wide_spread,
        "low_or_stable_vol": low_or_stable_vol,
        "elevated_vol": elevated_vol,
        "yen_shock": yen_shock,
        "hawkish_repricing_proxy": hawkish_repricing,
        "policy_shock_with_yen": policy_shock_with_yen,
        "short_build_event": short_build_event,
        "quiet_crowded_vulnerability": quiet_crowded_vulnerability,
        "quiet_releveraging_event": quiet_releveraging_event,
        "gradual_absorption": gradual_absorption,
        "thresholds": {
            "jgb2_repricing_bp": JGB2_REPRICING_BP,
            "spread_repricing_bp": SPREAD_REPRICING_BP,
            "wide_spread_pct": WIDE_SPREAD_PCT,
            "low_vol_ratio_max": LOW_VOL_RATIO_MAX,
            "crowded_net_short_pct_oi": CROWDED_NET_SHORT_PCT_OI,
            "yen_shock_15m_pct": YEN_SHOCK_15M,
            "yen_shock_30m_pct": YEN_SHOCK_30M,
            "yen_shock_60m_pct": YEN_SHOCK_60M,
        },
        "note": "BOJ OIS/경제전문가 컨센서스는 신뢰 가능한 자동 원천을 잠그기 전까지 점수에 넣지 않음. 일본 2년 JGB와 미·일 2년 금리차를 경로 재가격 프록시로 사용.",
    }


def reasons(previous_policy: dict, current: dict) -> list[str]:
    if not previous_policy.get("initialized"):
        return []
    out: list[str] = []
    if current.get("policy_shock_with_yen") and not previous_policy.get("policy_shock_with_yen"):
        out.append("예상 경로보다 빠른 긴축 재가격 프록시와 엔화 급등이 동시 확인")
    elif current.get("hawkish_repricing_proxy") and not previous_policy.get("hawkish_repricing_proxy"):
        out.append("일본 단기금리·미일 금리차에서 긴축 경로 재가격 급변 감지")
    if current.get("quiet_releveraging_event"):
        out.append("낮은 변동성·넓은 금리차 속 CFTC 레버리지 엔화 순숏 재확대")
    return out


def current_title_level() -> int:
    if not ALERT_TITLE.exists():
        return 0
    title = ALERT_TITLE.read_text(encoding="utf-8").lstrip()
    return {"🟢": 0, "🟡": 1, "🟠": 2, "🔴": 3}.get(title[:1], 0)


def set_title_floor(level: int) -> None:
    if not ALERT_TITLE.exists() or level <= current_title_level():
        return
    text = ALERT_TITLE.read_text(encoding="utf-8").strip()
    text = re.sub(r"^[🟢🟡🟠🔴]\s*", LEVEL_EMOJI[level] + " ", text)
    ALERT_TITLE.write_text(text + "\n", encoding="utf-8")


def replace_unwind_floor(body: str, context: dict) -> str:
    floor = int(context.get("risk_floor") or 0)
    if floor <= 0:
        return body
    current = current_title_level()
    if floor < current:
        return body
    if floor >= 2:
        label = "🟠 긴축 경로 재가격·엔화 충격 동시 확인"
    elif context.get("quiet_crowded_vulnerability"):
        label = "🟡 저변동성 속 레버리지 취약성 누적"
    else:
        label = "🟡 긴축 경로 재가격 구조적 경계"
    return re.sub(r"^- 캐리 청산 위험:.*$", f"- 캐리 청산 위험: {label}", body, flags=re.MULTILINE)


def fmt(value, suffix="", digits=1) -> str:
    return "확인 불가" if value is None else f"{float(value):+.{digits}f}{suffix}"


def context_block(context: dict) -> str:
    cftc_change = context.get("cftc_net_short_change")
    cftc_now = context.get("cftc_net_short")
    cftc_pct = context.get("cftc_net_short_pct_oi")
    cftc_text = "확인 불가"
    if cftc_now is not None:
        cftc_text = f"{int(cftc_now):,}계약"
        if cftc_pct is not None:
            cftc_text += f" ({float(cftc_pct):.1f}% OI)"
        if cftc_change is not None and context.get("new_cftc"):
            cftc_text += f" / 새 보고서 변화 {int(cftc_change):+,}계약"

    vol = context.get("fx_vol_ratio")
    vol_text = "비교기준 부족" if vol is None else f"이전 구간 대비 {float(vol):.2f}배"
    if context.get("low_or_stable_vol"):
        vol_text += " → 낮음·안정"
    elif context.get("elevated_vol"):
        vol_text += " → 상승"

    return "\n".join([
        "긴축 경로·레버리지",
        f"- 일본 2년 JGB 재가격: {fmt(context.get('jgb2_change_bp'), 'bp')} / 미·일 2년 금리차 변화: {fmt(context.get('spread_change_bp'), 'bp')}",
        f"- FX 실현변동성: {vol_text}",
        f"- CFTC 레버리지 엔화 순숏: {cftc_text}",
        f"- 판정: {context.get('regime', '혼합·경계')}",
        "※ 예고된 금리인상 자체와 시장이 예상 경로를 갑자기 앞당기는 재가격을 분리합니다.",
        "※ 낮은 변동성+넓은 금리차+혼잡한 엔화 숏은 현재 청산 증거가 아니라 다음 충격의 취약성으로만 봅니다.",
        "※ BOJ OIS·컨센서스 확률은 신뢰 가능한 자동 원천 확보 전까지 임의 추정하지 않습니다.",
    ])


def ensure_alert(pending: dict, context: dict, why: list[str]) -> None:
    if not why:
        return
    if not ALERT_TITLE.exists():
        level = max(1, int(context.get("risk_floor") or 0))
        ALERT_TITLE.write_text(f"{LEVEL_EMOJI[level]} 엔캐리 복합 수급 알림\n", encoding="utf-8")
        values = pending.get("values") or {}
        unwind_label = pending.get("unwind_label") or "엔캐리 청산 미확인"
        rebuild_label = pending.get("rebuild_label") or "엔화 재약세·캐리 재구축 미확인"
        body = [
            f"조회 시각: {datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S KST')}", "", "판정",
            f"- 캐리 청산 위험: {unwind_label}",
            f"- 엔화 재약세·캐리 재구축: {rebuild_label}", "",
            "이번 변화", *[f"- {x}" for x in why], "", "시장·금리",
            f"- USD/JPY {float(values.get('usdjpy') or 0):.3f} / 15분 {float(values.get('usdjpy_15m_pct') or 0):+.2f}% / 30분 {float(values.get('usdjpy_30m_pct') or 0):+.2f}% / 60분 {float(values.get('usdjpy_60m_pct') or 0):+.2f}%",
            f"- 일본 2년 JGB {float(values.get('jgb2') or 0):.3f}% / 미국 2년 국채 {float(values.get('ust2') or 0):.3f}% / 미·일 2년 금리차 {float(values.get('us_jp_2y_spread') or 0):.3f}%p",
            "", context_block(context), "", "출처",
            "- Japan MOF JGB: https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv",
            "- U.S. Treasury: https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml",
            "- CFTC TFF Futures Only: https://www.cftc.gov/dea/futures/financial_lf.htm",
            "- USD/JPY: Yahoo query1/query2 5분 데이터 교차확인",
        ]
        ALERT_BODY.write_text("\n".join(body).rstrip() + "\n", encoding="utf-8")
        payload = {
            "verdict": {
                "unwind_level": int(pending.get("unwind_level") or 0),
                "unwind_label": unwind_label,
                "rebuild_level": int(pending.get("rebuild_level") or 0),
                "rebuild_label": rebuild_label,
                "evidence": pending.get("evidence") or {},
            },
            "reasons": why,
            "errors": [],
            "policy_path": context,
            "generated_at_kst": datetime.now(KST).isoformat(timespec="seconds"),
        }
        write_json(ALERT_JSON, payload)
        return

    body = ALERT_BODY.read_text(encoding="utf-8") if ALERT_BODY.exists() else ""
    if "긴축 경로·레버리지" not in body:
        body = body.rstrip() + "\n\n" + context_block(context) + "\n"
    body = replace_unwind_floor(body, context)
    ALERT_BODY.write_text(body.rstrip() + "\n", encoding="utf-8")

    payload = load_json(ALERT_JSON, {})
    payload.setdefault("reasons", [])
    for item in why:
        if item not in payload["reasons"]:
            payload["reasons"].append(item)
    payload["policy_path"] = context
    write_json(ALERT_JSON, payload)


def main() -> int:
    pending = load_json(PENDING_PATH, {})
    if not pending:
        print("yen carry policy-path overlay: pending composite state missing")
        return 0
    previous = load_json(STATE_PATH, {})
    context = classify_context(previous, pending)
    previous_policy = previous.get("policy_path") or {}
    why = reasons(previous_policy, context)

    pending["policy_path"] = context
    write_json(PENDING_PATH, pending)
    write_json(CONTEXT_JSON, context)
    CONTEXT_MD.write_text("# 엔캐리 긴축 경로·레버리지\n\n" + context_block(context) + "\n", encoding="utf-8")

    ensure_alert(pending, context, why)
    if ALERT_TITLE.exists():
        set_title_floor(int(context.get("risk_floor") or 0))
        if ALERT_BODY.exists():
            body = ALERT_BODY.read_text(encoding="utf-8")
            if "긴축 경로·레버리지" not in body:
                body = body.rstrip() + "\n\n" + context_block(context) + "\n"
            body = replace_unwind_floor(body, context)
            ALERT_BODY.write_text(body.rstrip() + "\n", encoding="utf-8")
        payload = load_json(ALERT_JSON, {})
        if payload:
            payload["policy_path"] = context
            write_json(ALERT_JSON, payload)

    print(json.dumps({"regime": context["regime"], "risk_floor": context["risk_floor"], "reasons": why}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
