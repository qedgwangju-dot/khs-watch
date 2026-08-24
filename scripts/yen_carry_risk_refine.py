#!/usr/bin/env python3
"""Refine the yen-carry Telegram risk label using a hierarchy grounded in carry mechanics.

Principles:
- The title colour represents *current unwind / market-stress risk*, not carry rebuilding.
- Carry rebuilding is shown separately because it is a different question.
- Weekly CFTC positioning and policy/intervention context are vulnerability/catalyst inputs,
  not proof that an unwind is active.
- A JGB 10Y 3% print is a structural/fiscal boundary, never an automatic unwind trigger.
- Red requires an active yen-strength shock plus funding/spread pressure and volatility or
  cross-asset deleveraging confirmation.
- User-facing Telegram alerts must not expose raw Python/network exception strings. Retrieval
  failures are summarized in Korean while raw errors remain in the JSON/artifacts for audit.

Inputs:
  out/yen_carry_composite_alert.json
  out/yen_carry_composite_alert_title.txt
  out/yen_carry_composite_alert.md
  out/yen_carry_confirmation.json   (optional but recommended)

The script rewrites the alert title/body and adds refined_risk to alert JSON.
"""
from __future__ import annotations

import json
import pathlib
import re

OUT = pathlib.Path("out")
JSON_PATH = OUT / "yen_carry_composite_alert.json"
TITLE_PATH = OUT / "yen_carry_composite_alert_title.txt"
BODY_PATH = OUT / "yen_carry_composite_alert.md"
CONFIRM_PATH = OUT / "yen_carry_confirmation.json"

EMOJI = {0: "🟢", 1: "🟡", 2: "🟠", 3: "🔴"}
RISK_LABEL = {
    0: "현재 엔캐리 청산 위험 미확인",
    1: "구조적 취약성·경계",
    2: "엔캐리 청산 경계 강화",
    3: "실제 엔캐리 청산·디레버리징 위험 높음",
}


def load(path: pathlib.Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def b(d: dict, key: str) -> bool:
    return bool(d.get(key))


def refine(payload: dict, confirm: dict) -> dict:
    verdict = payload.get("verdict") or {}
    evidence = verdict.get("evidence") or {}
    signals = confirm.get("signals") or {}

    # Core carry-unwind mechanics.
    short_rate_up = b(evidence, "unwind::일본 단기금리 상승")
    spread_narrow = b(evidence, "unwind::미·일 2년 금리차 축소")
    yen_fast = b(evidence, "unwind::USD/JPY 급락·엔화 급등")
    fx_vol = b(evidence, "unwind::FX 실현변동성 상승")

    # Vulnerability/catalyst inputs. These cannot by themselves prove an active unwind.
    leveraged_short = b(evidence, "unwind::레버리지 펀드 엔화 순숏")
    policy_catalyst = b(evidence, "unwind::최근 공식 공동개입·추가개입 경고")

    # Daily confirmation layer: deliberately slower and used only as confirmation.
    yen_daily = b(signals, "yen_strength_daily_2pct")
    vix_spike = b(signals, "vix_spike_20pct")
    nasdaq_down = b(signals, "nasdaq_down_2pct")
    nikkei_down = b(signals, "nikkei_down_2pct")
    equity_joint = bool(confirm.get("equity_joint_weakness")) or (nasdaq_down and nikkei_down)

    yen_shock = yen_fast or yen_daily
    funding_pressure = short_rate_up or spread_narrow
    market_confirmation = fx_vol or vix_spike or equity_joint

    # 3 = disorderly/active unwind risk. Require the funding currency to strengthen,
    # funding economics to worsen, and volatility/cross-asset confirmation.
    if yen_shock and funding_pressure and market_confirmation and leveraged_short:
        level = 3
    # 2 = active warning. Yen must already be strengthening sharply and at least one
    # policy/funding/volatility catalyst must corroborate it. Alternatively, simultaneous
    # funding pressure + volatility + crowded shorts is enough for an orange pre-unwind warning.
    elif yen_shock and (funding_pressure or fx_vol or policy_catalyst):
        level = 2
    elif funding_pressure and fx_vol and leveraged_short:
        level = 2
    # 1 = structural vulnerability only. Crowded shorts plus a catalyst, or funding
    # economics worsening without an actual yen shock, stays yellow.
    elif (leveraged_short and (short_rate_up or spread_narrow or policy_catalyst)) or funding_pressure:
        level = 1
    else:
        level = 0

    rebuild_level = int(verdict.get("rebuild_level") or 0)
    rebuild_label = str(verdict.get("rebuild_label") or "엔화 재약세·캐리 재구축 미확인")

    return {
        "level": level,
        "label": RISK_LABEL[level],
        "emoji": EMOJI[level],
        "rebuild_level": rebuild_level,
        "rebuild_label": rebuild_label,
        "rebuild_emoji": EMOJI.get(max(0, min(3, rebuild_level)), "🔴"),
        "signals": {
            "yen_shock": yen_shock,
            "funding_pressure": funding_pressure,
            "fx_volatility": fx_vol,
            "vix_spike": vix_spike,
            "equity_joint_weakness": equity_joint,
            "leveraged_yen_short": leveraged_short,
            "policy_catalyst": policy_catalyst,
            "short_rate_up": short_rate_up,
            "spread_narrow": spread_narrow,
        },
        "method": (
            "현재 청산 위험과 캐리 재구축을 분리. CFTC·정책은 취약성/촉매로만 사용하고, "
            "주황·빨강은 엔화 강세 충격과 미·일 금리차/일본 단기금리, 변동성·위험자산 전염의 동시 확인을 요구."
        ),
    }


def concise_failure(raw: str) -> tuple[str, str]:
    """Return a compact user-facing source name and reason without losing the audit trail."""
    text = str(raw or "")
    lower = text.lower()

    if text.startswith("Japan MOF 해외증권투자:"):
        source = "일본 재무성 해외증권투자"
    elif text.startswith("CFTC:"):
        source = "CFTC 레버리지 포지션"
    elif text.startswith("Japan MOF 공동개입:"):
        source = "일본 재무성 공동개입 자료"
    else:
        source = "보조자료"

    reasons = []
    if "timeout" in lower:
        reasons.append("응답 시간초과")
    if "403" in lower or "forbidden" in lower:
        reasons.append("대체 경로 접속 차단")
    if "connection reset" in lower or "errno 104" in lower:
        reasons.append("연결 재설정")
    if "parse" in lower or "decode" in lower or "json" in lower:
        reasons.append("자료 형식 확인 필요")

    # Deduplicate while preserving order.
    reasons = list(dict.fromkeys(reasons))
    if not reasons:
        reasons = ["원문 재조회 실패"]

    return source, "·".join(reasons)


def clean_failure_section(body: str, errors: list[str]) -> str:
    if not errors:
        return body

    notices = []
    for raw in errors:
        source, reason = concise_failure(raw)
        notices.append(f"- {source} — 일시적 확인 지연({reason}) / 다음 실행에서 자동 재시도")

    # Keep user-facing status concise. Raw exception text remains in alert JSON/artifacts.
    clean_block = (
        "자료 확인 상태\n"
        + "\n".join(notices)
        + "\n※ 확인이 지연된 항목은 이번 위험도 판정의 확정 근거에서 제외했습니다."
    )

    # Replace the raw '확인 실패' block, if present.
    body = re.sub(
        r"\n\n확인 실패\n(?:- .*?(?:\n|$))+",
        "\n\n" + clean_block + "\n",
        body,
        flags=re.MULTILINE,
    )

    # If the upstream body did not contain a raw failure block, append a clean status block.
    if "자료 확인 상태" not in body:
        body = body.rstrip() + "\n\n" + clean_block

    # Improve the inline data row so it does not look like the statistic itself is missing.
    if any(str(e).startswith("Japan MOF 해외증권투자:") for e in errors):
        body = body.replace(
            "- 일본 재무성 해외증권투자: 확인 불가",
            "- 일본 재무성 해외증권투자: 이번 실행 확인 지연(원문 재조회 실패)",
        )
    if any(str(e).startswith("CFTC:") for e in errors):
        body = body.replace(
            "- CFTC 레버리지 펀드: 확인 불가",
            "- CFTC 레버리지 펀드: 이번 실행 확인 지연(원문 재조회 실패)",
        )
    if any(str(e).startswith("Japan MOF 공동개입:") for e in errors):
        body = body.replace(
            "- 정책개입 신뢰도: 공식 원문 재확인 실패",
            "- 정책개입 자료: 이번 실행 확인 지연(공식 원문 재조회 실패)",
        )

    return body


def rewrite_body(body: str, refined: dict, errors: list[str]) -> str:
    unwind_line = f"- 캐리 청산 위험: {refined['emoji']} {refined['label']}"
    rebuild_line = f"- 엔화 재약세·캐리 재구축: {refined['rebuild_emoji']} {refined['rebuild_label']}"

    body = re.sub(r"^- 캐리 청산 위험:.*$", unwind_line, body, flags=re.MULTILINE)
    body = re.sub(r"^- 엔화 재약세·캐리 재구축:.*$", rebuild_line, body, flags=re.MULTILINE)

    marker = "※ 제목 색상은 ‘현재 엔캐리 청산·시장 스트레스 위험’만 표시하며, 재구축 압력은 별도 색으로 표시합니다."
    if marker not in body:
        anchor = "※ 두 판정은 서로 다른 질문이며 동시에 높거나 서로 엇갈릴 수 있습니다."
        body = body.replace(anchor, anchor + "\n" + marker)

    return clean_failure_section(body, errors)


def main() -> int:
    if not JSON_PATH.exists() or not TITLE_PATH.exists() or not BODY_PATH.exists():
        return 0

    payload = load(JSON_PATH, {})
    if not payload:
        return 0
    confirm = load(CONFIRM_PATH, {})
    refined = refine(payload, confirm)
    payload["refined_risk"] = refined
    JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    title = TITLE_PATH.read_text(encoding="utf-8").strip()
    title = re.sub(r"^[🟢🟡🟠🔴]\s*", refined["emoji"] + " ", title)
    TITLE_PATH.write_text(title + "\n", encoding="utf-8")

    body = BODY_PATH.read_text(encoding="utf-8")
    errors = payload.get("errors") or []
    BODY_PATH.write_text(rewrite_body(body, refined, errors).rstrip() + "\n", encoding="utf-8")

    print(json.dumps(refined, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
