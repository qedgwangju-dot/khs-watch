#!/usr/bin/env python3
"""Build a compact, scan-first Telegram body for the yen-carry composite alert.

The detailed alert remains archived separately. This formatter keeps only:
1) current verdict,
2) what changed,
3) a small set of decision-critical numbers,
4) one short interpretation block,
5) next escalation conditions,
6) a few primary-source links.

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


def compact_jgb10(item: str | None) -> str | None:
    if not item:
        return None
    m = re.search(r"JGB[^0-9]*10년[^0-9]*([0-9.]+)%", item)
    if not m:
        m = re.search(r"10년[^0-9]*([0-9.]+)%", item)
    if m:
        level = float(m.group(1))
        suffix = " → 3% 구조적 경계" if level >= 3.0 else ""
        return f"JGB 10년 {level:.3f}%{suffix}"
    return item


def compact_flow(item: str | None) -> str | None:
    if not item:
        return None
    # Keep the latest 2-week and prior 2-week comparison; drop explanatory tail.
    m = re.search(r"최근 2주\s*([+\-]?[0-9.]+)조엔\s*/\s*직전 2주\s*([+\-]?[0-9.]+)조엔", item)
    if m:
        latest = float(m.group(1))
        prior = float(m.group(2))
        state = "순매수" if latest > 0 else "순매도" if latest < 0 else "중립"
        return f"해외중장기채 2주 {latest:+.2f}조엔 (직전 {prior:+.2f}) → {state}"
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
    if net > 0:
        pos = f"엔화 순롱 +{net:,}계약"
    elif net < 0:
        pos = f"엔화 순숏 {abs(net):,}계약"
    else:
        pos = "엔화 순포지션 0계약"
    suffix = f" ({date})" if date else ""
    return f"CFTC 레버리지: {pos} · Long {long_pos:,} / Short {short_pos:,}{suffix}"


def normalize_verdict(item: str) -> str:
    return (
        item.replace("캐리 청산 위험:", "청산 위험:")
        .replace("엔화 재약세·캐리 재구축:", "캐리 재구축:")
        .replace("엔캐리 청산 ", "")
        .replace("엔화 재약세·캐리 재구축 압력 ", "")
    )


def market_meaning(payload: dict, sections: dict[str, list[str]]) -> list[str]:
    verdict = payload.get("verdict") or {}
    refined = payload.get("refined_risk") or {}
    unwind = int(refined.get("level", verdict.get("unwind_level", 0)) or 0)
    rebuild = int(refined.get("rebuild_level", verdict.get("rebuild_level", 0)) or 0)

    out: list[str] = []
    if unwind <= 1 and rebuild >= 2:
        out.append("지금은 ‘청산’보다 캐리 유지·재구축 쪽이 우세.")
    elif unwind >= 2:
        out.append("현재는 엔캐리 청산 경계가 우세해 위험자산 수급 확인이 필요.")
    else:
        out.append("현재 엔캐리 강제청산 증거는 제한적.")

    jgb = first_matching(sections.get("구조적 경계·자금환류", []), "JGB", "10년")
    if jgb and "3%" in jgb:
        out.append("JGB 10년 3%는 구조적 경계이지 자동 청산선·입찰 붕괴 신호는 아님.")

    if rebuild >= 2:
        out.append("엔화 재약세가 더 커지면 구두개입·실개입·BOJ 추가 긴축 위험이 다시 올라감.")
    return out[:3]


def main() -> int:
    if not BODY.exists():
        return 0

    original = BODY.read_text(encoding="utf-8")
    if not original.strip():
        return 0

    DETAIL.write_text(original.rstrip() + "\n", encoding="utf-8")
    payload = load_json(PAYLOAD)
    preamble, sections = split_sections(original)

    verdict_items = bullets(sections.get("판정", []))
    verdict_items = [normalize_verdict(x) for x in verdict_items if x.startswith(("캐리 청산 위험:", "엔화 재약세·캐리 재구축:"))][:2]

    change_items = bullets(sections.get("이번 변화", []))[:3]

    key_numbers: list[str] = []
    usd = first_matching(sections.get("주식시장 영향", []), "현재 USD/JPY")
    if not usd:
        usd = first_matching(sections.get("시장·금리", []), "USD/JPY")
    if usd:
        key_numbers.append(usd.replace("현재 USD/JPY:", "USD/JPY"))

    jgb = compact_jgb10(first_matching(sections.get("구조적 경계·자금환류", []), "JGB", "10년"))
    if jgb:
        key_numbers.append(jgb)

    flow = compact_flow(first_matching(sections.get("구조적 경계·자금환류", []), "해외중장기채"))
    if flow:
        key_numbers.append(flow)

    rate = first_matching(sections.get("긴축 경로·레버리지", []), "일본 2년 JGB 재가격", "미·일 2년 금리차 변화")
    if rate:
        key_numbers.append(rate)

    vol = first_matching(sections.get("긴축 경로·레버리지", []), "FX 실현변동성")
    if vol:
        # Remove explanatory tail if present.
        key_numbers.append(vol.split("→", 1)[0].strip())

    cftc = cftc_line(payload)
    if cftc:
        key_numbers.append(cftc)

    # Keep the message compact even when many overlays are active.
    key_numbers = key_numbers[:6]

    meaning = market_meaning(payload, sections)

    next_alert = [
        "미·일 2년 금리차 급축소 + JGB 2년 급등",
        "USD/JPY 급락·FX 변동성 급등",
        "해외중장기채가 다시 4주·12주 누적 순매도로 전환",
        "엔화 강세와 Nasdaq·Nikkei 급락이 동시에 발생",
    ]

    # Keep only the sources needed to validate the compact decision tree.
    source_lines = [f"- {label}: {url}" for label, url in SOURCE_LINES]

    checked = next((x.strip() for x in preamble if x.strip().startswith("조회 시각:")), "")
    if not checked:
        checked = f"조회 시각: {dt.datetime.now(KST).strftime('%Y-%m-%d %H:%M KST')}"

    lines: list[str] = [
        "판정",
        *[f"• {x}" for x in verdict_items],
        "",
        "이번 변화",
        *([f"• {x}" for x in change_items] if change_items else ["• 새 단계 변화 없음"]),
        "",
        "핵심 숫자",
        *[f"• {x}" for x in key_numbers],
        "",
        "의미",
        *[f"• {x}" for x in meaning],
        "",
        "다음 경보",
        *[f"• {x}" for x in next_alert],
        "",
        "출처",
        *source_lines,
        "",
        checked,
    ]

    BODY.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    print("yen_carry_telegram_compact=rewritten")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
