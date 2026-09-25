#!/usr/bin/env python3
"""Build a scan-first Telegram body for the yen-carry composite alert.

The detailed alert remains archived separately. The Telegram body must answer, in
this order:
1) Which way is the carry regime moving right now?
2) Is that good or bad for risk assets?
3) What changed?
4) Which 4-6 numbers prove the direction?
5) What would reverse the call?

It never changes trigger logic or risk scores.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
OUT = pathlib.Path("out")
BODY = OUT / "yen_carry_composite_alert.md"
DETAIL = OUT / "yen_carry_composite_alert_detail.md"
PAYLOAD = OUT / "yen_carry_composite_alert.json"
TITLE = OUT / "yen_carry_composite_alert_title.txt"

HEADINGS = {
    "판정",
    "이번 변화",
    "시장·금리",
    "포지션·자금",
    "정책",
    "정확한 의미",
    "구조적 경계·자금환류",
    "JGB 입찰 수요",
    "실질금리·정책 정상화",
    "긴축 경로·레버리지",
    "출처",
    "미·일 정책공조·시장 영향",
    "주식시장 영향",
    "자료 확인 상태",
}

SOURCE_LINES = (
    ("Japan MOF JGB", "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv"),
    ("Japan MOF 해외증권투자", "https://www.mof.go.jp/policy/international_policy/reference/itn_transactions_in_securities/week.csv"),
    ("CFTC TFF Futures Only", "https://publicreporting.cftc.gov/resource/gpe5-46if.json"),
    ("Bank of Japan policy guideline", "https://www.boj.or.jp/en/"),
)


def load_json(path: pathlib.Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def split_sections(text: str) -> tuple[list[str], dict[str, list[str]]]:
    preamble: list[str] = []
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if line in HEADINGS:
            current = line
            sections.setdefault(current, [])
            continue
        if current is None:
            preamble.append(raw.rstrip())
        else:
            sections[current].append(raw.rstrip())
    return preamble, sections


def bullets(lines: list[str]) -> list[str]:
    out: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("※"):
            continue
        if line.startswith(("-", "•")):
            item = line[1:].strip()
            if item:
                out.append(item)
    return out


def first_matching(lines: list[str], *needles: str) -> str | None:
    for item in bullets(lines):
        if any(needle in item for needle in needles):
            return item
    return None


def levels(payload: dict) -> tuple[int, int]:
    verdict = payload.get("verdict") or {}
    refined = payload.get("refined_risk") or {}
    unwind = int(refined.get("level", verdict.get("unwind_level", 0)) or 0)
    rebuild = int(refined.get("rebuild_level", verdict.get("rebuild_level", 0)) or 0)
    return unwind, rebuild


def direction_call(payload: dict) -> tuple[str, str, str]:
    """Return title direction, current direction and risk-asset implication."""
    unwind, rebuild = levels(payload)
    risk_emoji = {0: "🟢", 1: "🟡", 2: "🟠", 3: "🔴"}.get(min(unwind, 3), "🟡")

    if unwind >= 2 and rebuild >= 2:
        direction = "↔ 청산·재구축 신호 충돌"
        title_dir = "↔ 방향 충돌"
        impact = "🟠 위험자산 변동성 확대 주의"
    elif unwind >= 2:
        direction = "↘ 엔화 강세·캐리 청산 압력 우세"
        title_dir = "↘ 청산 압력 우세"
        impact = "🔴 위험자산 수급 부담"
    elif rebuild >= 2:
        direction = "↗ 엔화 약세·캐리 재구축 우세"
        title_dir = "↗ 재구축 우세"
        impact = "🟢 위험자산 수급 단기 우호"
    elif rebuild > unwind:
        direction = "↗ 캐리 유지 쪽으로 기울기"
        title_dir = "↗ 캐리 유지"
        impact = "🟡 위험자산 수급 소폭 우호"
    elif unwind > rebuild:
        direction = "↘ 캐리 청산 쪽으로 기울기"
        title_dir = "↘ 청산 경계"
        impact = "🟠 위험자산 수급 주의"
    else:
        direction = "↔ 중립·방향 확인 대기"
        title_dir = "↔ 중립"
        impact = "⚪ 위험자산 영향 중립"

    return f"{risk_emoji} 엔캐리 | {title_dir}", direction, impact


def unwind_risk_line(payload: dict, sections: dict[str, list[str]]) -> str:
    items = bullets(sections.get("판정", []))
    raw = next((x for x in items if x.startswith("캐리 청산 위험:")), "")
    if raw:
        return raw.replace("캐리 청산 위험:", "").strip()
    unwind, _ = levels(payload)
    return {
        0: "🟢 강제청산 증거 낮음",
        1: "🟡 구조적 취약성·경계",
        2: "🟠 청산 압력 강화",
        3: "🔴 실제 청산·전염 위험",
    }.get(min(unwind, 3), "🟡 확인 필요")


def compact_jgb10(item: str | None) -> str | None:
    if not item:
        return None
    m = re.search(r"JGB[^0-9]*10년[^0-9]*([0-9.]+)%", item)
    if not m:
        m = re.search(r"10년[^0-9]*([0-9.]+)%", item)
    if m:
        level = float(m.group(1))
        if level >= 3.0:
            return f"JGB 10년 {level:.3f}% → 🟡 구조적 경계, 자동 청산선 아님"
        return f"JGB 10년 {level:.3f}%"
    return item


def compact_flow(item: str | None) -> str | None:
    if not item:
        return None
    m = re.search(r"최근 2주\s*([+\-]?[0-9.]+)조엔\s*/\s*직전 2주\s*([+\-]?[0-9.]+)조엔", item)
    if m:
        latest = float(m.group(1))
        prior = float(m.group(2))
        if latest > 0:
            meaning = "순매수·본국회귀 압력 약함"
        elif latest < 0:
            meaning = "순매도·본국회귀 압력"
        else:
            meaning = "중립"
        return f"해외중장기채 2주 {latest:+.2f}조엔 (직전 {prior:+.2f}) → {meaning}"
    return item


def compact_rate(item: str | None) -> str | None:
    if not item:
        return None
    jgb = re.search(r"일본 2년 JGB 재가격:\s*([+\-]?[0-9.]+)bp", item)
    spread = re.search(r"미·일 2년 금리차 변화:\s*([+\-]?[0-9.]+)bp", item)
    if not spread:
        return item
    spread_bp = float(spread.group(1))
    jgb_bp = float(jgb.group(1)) if jgb else None
    if spread_bp >= 1.0:
        meaning = "확대 → 캐리 유지·재구축 쪽"
    elif spread_bp <= -1.0:
        meaning = "축소 → 캐리 청산 압력"
    else:
        meaning = "보합 → 중립"
    tail = f" / JGB2 {jgb_bp:+.1f}bp" if jgb_bp is not None else ""
    return f"미·일 2년 금리차 {spread_bp:+.1f}bp {meaning}{tail}"


def compact_vol(item: str | None) -> str | None:
    if not item:
        return None
    if "낮음·안정" in item:
        return "FX 변동성 낮음·안정 → 강제청산 신호 약함"
    if "상승" in item or "높" in item:
        return "FX 변동성 상승 → 청산 위험 점검"
    return item


def cftc_line(payload: dict) -> str | None:
    cftc = payload.get("cftc") or {}
    try:
        long_pos = int(cftc.get("leveraged_long"))
        short_pos = int(cftc.get("leveraged_short"))
    except (TypeError, ValueError):
        return None
    net = long_pos - short_pos
    date = str(cftc.get("report_date") or "")
    suffix = f" ({date})" if date else ""
    if net > 0:
        return f"CFTC 레버리지: 엔화 순롱 +{net:,}계약 → 혼잡한 엔숏 아님{suffix}"
    if net < 0:
        return f"CFTC 레버리지: 엔화 순숏 {abs(net):,}계약 → 숏청산 취약성{suffix}"
    return f"CFTC 레버리지: 엔화 순포지션 0계약{suffix}"


def usd_line(sections: dict[str, list[str]]) -> str | None:
    usd = first_matching(sections.get("주식시장 영향", []), "현재 USD/JPY")
    if not usd:
        usd = first_matching(sections.get("시장·금리", []), "USD/JPY")
    if not usd:
        return None
    return usd.replace("현재 USD/JPY:", "USD/JPY").replace("현재 USD/JPY", "USD/JPY")


def reverse_conditions(payload: dict) -> list[str]:
    unwind, rebuild = levels(payload)
    if rebuild >= 2 and unwind <= 1:
        return [
            "USD/JPY 급락 + FX 변동성 급등 → 재구축 종료·청산 경계",
            "미·일 2년 금리차 급축소 + JGB 2년 급등 → 청산 압력 강화",
            "해외중장기채 4주·12주 순매도 + Nasdaq·Nikkei 동반 급락 → 실제 전염",
        ]
    if unwind >= 2:
        return [
            "USD/JPY 반등 + FX 변동성 안정 → 청산 압력 완화",
            "미·일 2년 금리차 재확대 → 캐리 유지 여지 회복",
            "Nasdaq·Nikkei 안정 + 해외중장기채 순매수 → 전염 약화",
        ]
    return [
        "USD/JPY 급변과 FX 변동성 확대",
        "미·일 2년 금리차의 10bp 이상 급격한 축소·확대",
        "해외중장기채 4주·12주 방향 전환 + 위험자산 동반 반응",
    ]


def main() -> int:
    if not BODY.exists():
        return 0

    original = BODY.read_text(encoding="utf-8")
    if not original.strip():
        return 0

    DETAIL.write_text(original.rstrip() + "\n", encoding="utf-8")
    payload = load_json(PAYLOAD)
    preamble, sections = split_sections(original)

    title, direction, risk_asset = direction_call(payload)
    TITLE.write_text(title + "\n", encoding="utf-8")
    unwind_text = unwind_risk_line(payload, sections)

    change_items = bullets(sections.get("이번 변화", []))[:2]

    key_reasons: list[str] = []
    usd = usd_line(sections)
    if usd:
        key_reasons.append(usd)

    rate = compact_rate(first_matching(
        sections.get("긴축 경로·레버리지", []),
        "일본 2년 JGB 재가격",
        "미·일 2년 금리차 변화",
    ))
    if rate:
        key_reasons.append(rate)

    flow = compact_flow(first_matching(
        sections.get("구조적 경계·자금환류", []),
        "해외중장기채",
    ))
    if flow:
        key_reasons.append(flow)

    vol = compact_vol(first_matching(
        sections.get("긴축 경로·레버리지", []),
        "FX 실현변동성",
    ))
    if vol:
        key_reasons.append(vol)

    cftc = cftc_line(payload)
    if cftc:
        key_reasons.append(cftc)

    jgb = compact_jgb10(first_matching(
        sections.get("구조적 경계·자금환류", []),
        "JGB",
        "10년",
    ))
    if jgb:
        key_reasons.append(jgb)

    key_reasons = key_reasons[:6]
    next_alert = reverse_conditions(payload)
    source_lines = [f"- {label}: {url}" for label, url in SOURCE_LINES]

    checked = next((x.strip() for x in preamble if x.strip().startswith("조회 시각:")), "")
    if not checked:
        checked = f"조회 시각: {dt.datetime.now(KST).strftime('%Y-%m-%d %H:%M KST')}"

    lines: list[str] = [
        "판정",
        f"▶ 현재 방향 │ {direction}",
        f"▶ 청산 위험 │ {unwind_text}",
        f"▶ 시장 영향 │ {risk_asset}",
        "",
        "이번 변화",
        *([f"• {x}" for x in change_items] if change_items else ["• 새 단계 변화 없음"]),
        "",
        "핵심 근거",
        *[f"• {x}" for x in key_reasons],
        "",
        "반전 조건",
        *[f"• {x}" for x in next_alert],
        "",
        "출처",
        *source_lines,
        "",
        checked,
    ]

    BODY.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    print("yen_carry_telegram_compact=direction_first")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
