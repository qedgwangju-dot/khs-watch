#!/usr/bin/env python3
"""Post-run quality guardrails for KHS policy watch alerts.

This script runs after the source watcher and before Telegram delivery. It keeps
the detector broad, but makes the delivered alert stricter: sectors must have
direct text evidence and low-impact false positives are removed.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
OUT_DIR = Path("out")
REPORT_PATH = OUT_DIR / "khs_policy_watch.md"
ALERT_PATH = OUT_DIR / "khs_policy_watch_alert.md"
TITLE_PATH = OUT_DIR / "khs_policy_watch_alert_title.txt"
ALERTS_JSON_PATH = OUT_DIR / "khs_policy_watch_alerts.json"


SECTOR_RULES: list[tuple[str, list[str]]] = [
    ("풍력/해상풍력", [
        "offshore wind", "wind energy", "wind lease", "wind leasing", "wind project",
        "wind area", "wind auction", "wind farm", "wind turbine",
    ]),
    ("전력망/데이터센터", [
        "ferc", "electric grid", "power grid", "transmission", "interconnection",
        "large load", "data center", "datacenter",
    ]),
    ("원전/전력기기", [
        "nuclear", "reactor", "uranium", "transformer", "small modular reactor", "smr",
    ]),
    ("반도체/AI", [
        "semiconductor", "semiconductors", "chips", "chip export", "export control",
        "export controls", "entity list", "nvidia", "hbm", "artificial intelligence", "ai",
    ]),
    ("2차전지/핵심광물", [
        "battery", "batteries", "lithium", "critical mineral", "critical minerals",
        "rare earth", "cobalt", "nickel", "graphite", "manganese",
    ]),
    ("방산/지정학", [
        "sanctions", "missile", "defense", "national security", "iran", "russia",
        "china", "taiwan",
    ]),
    ("바이오/FDA", [
        "fda", "clinical", "drug", "complete response letter", "crl",
    ]),
    ("관세/수출주", [
        "tariff", "tariffs", "section 301", "ustr", "customs enforcement",
        "import duty", "export control", "export controls", "entity list",
    ]),
    ("통신/FCC/위성", [
        "fcc", "federal communications commission", "spectrum", "broadband",
        "wireless", "wireline", "satellite", "space bureau", "telecommunications",
    ]),
    ("행정명령/대통령문서", [
        "executive order", "presidential memorandum", "presidential determination",
        "national security memorandum", "presidential permit", "proclamation",
    ]),
    ("해양광물/해양개발", [
        "marine minerals", "mineral leasing", "mineral lease", "offshore mineral",
        "outer continental shelf mineral", "sand", "sediment",
    ]),
]


def term_in_text(text: str, term: str) -> bool:
    term = term.lower()
    if re.fullmatch(r"[a-z0-9]+", term):
        return re.search(rf"\b{re.escape(term)}\b", text) is not None
    return term in text


def has_any(text: str, terms: list[str]) -> bool:
    return any(term_in_text(text, term) for term in terms)


def haystack_for(item: dict) -> str:
    matched_terms = " ".join(
        term
        for terms in (item.get("matched") or {}).values()
        for term in terms
    )
    return " ".join(
        str(part or "")
        for part in (
            item.get("source"),
            item.get("title"),
            item.get("summary"),
            matched_terms,
        )
    ).lower()


def is_personnel(item: dict) -> bool:
    return "korea_presidential_personnel" in (item.get("matched") or {})


def direct_sectors(item: dict) -> list[str]:
    if is_personnel(item):
        return item.get("sectors") or ["한국 대통령실/고위급 인사"]

    text = haystack_for(item)
    sectors = [label for label, terms in SECTOR_RULES if has_any(text, terms)]

    # BOEM/BSEE alone is not a wind signal. Keep marine mineral language separate
    # unless the item explicitly says wind.
    if "풍력/해상풍력" in sectors and not has_any(
        text,
        ["offshore wind", "wind energy", "wind lease", "wind leasing", "wind project", "wind area", "wind auction", "wind farm", "wind turbine"],
    ):
        sectors.remove("풍력/해상풍력")

    # "mineral leasing" is not automatically a battery/critical-minerals signal.
    if "2차전지/핵심광물" in sectors and not has_any(
        text,
        ["battery", "batteries", "lithium", "critical mineral", "critical minerals", "rare earth", "cobalt", "nickel", "graphite", "manganese"],
    ):
        sectors.remove("2차전지/핵심광물")

    return sectors or ["정책/규제 일반"]


def is_low_impact_false_positive(item: dict) -> bool:
    if is_personnel(item):
        return False

    text = haystack_for(item)
    source = str(item.get("source") or "").lower()
    is_boem_marine_mineral = (
        "boem" in source
        and has_any(text, ["mineral leasing", "mineral lease", "marine minerals", "offshore mineral"])
        and not has_any(text, ["offshore wind", "critical mineral", "critical minerals", "lithium", "rare earth", "oil", "gas"])
    )
    if is_boem_marine_mineral:
        item["guardrail_note"] = "BOEM 해양광물 임대 의견수렴은 원문상 풍력·핵심광물·관세 직접 근거가 없어 고충격 알림에서 제외"
        return True

    return False


def render_report(alerts: list[dict], now: dt.datetime) -> str:
    lines = [f"🚨 KHS 정책·규제 고충격 워치 · {now:%Y년 %m월 %d일 %H:%M KST}", ""]
    if not alerts:
        lines.extend([
            "고충격 정책·규제 변경 직접 확인 없음",
            "",
            "💡 워치 판단: 이번 실행에서 돈 버는 능력, 할인율, 수급, 시간표를 새로 바꾼 확정 이벤트는 직접 확인되지 않았습니다.",
            "",
            "투자 조언이 아닌 참고용 정책·규제 알림입니다.",
        ])
        return "\n".join(lines) + "\n"

    for idx, alert in enumerate(alerts, 1):
        matched_terms = sorted({term for terms in (alert.get("matched") or {}).values() for term in terms})
        matched_keys = ", ".join((alert.get("matched") or {}).keys()) or "정책/규제"
        lines.extend([
            f"## {idx}. [{alert.get('importance', '중')}·{alert.get('status', '확정')}] {str(alert.get('title') or '').strip()}",
            f"- 상태 변화: {matched_keys} 신호 확인 ({', '.join(matched_terms[:8])})",
            f"- 원문/출처: [{alert.get('source', 'source')}]({alert.get('link', '')}) · 원천시각 {alert.get('published_kst') or '확인 불가'} · 조회 {now:%H:%M KST}",
            f"- 한국장 영향: {', '.join(alert.get('impacts') or ['의사결정 영향 제한적'])}",
            f"- 영향 경로: {', '.join(alert.get('paths') or ['정책 타임라인'])}",
            f"- 영향 섹터: {', '.join(alert.get('sectors') or ['정책/규제 일반'])}",
            "- 반영 가능성: 낮음~중간. 공식 원문/신뢰 소스 확인 후 한국장 확산 여부를 장전 레이더에서 재확인해야 합니다.",
            "- 반대 근거: 제목·요약 기반 1차 감시라 원문 세부 조건, 시행일, 예외 조항, 개별 프로젝트 적용 여부 확인이 필요합니다.",
            "- 즉시 체크: 원문 전문, 시행일/마감일, 한국 밸류체인 노출, 관련 해외 티커·ETF 반응",
            "",
        ])
    lines.extend([
        "💡 워치 판단: 이번 실행은 시간표·할인율을 바꿀 수 있는 정책/규제 상태 변화 후보를 우선 감지했습니다. 장전 레이더에서 원문 전문과 시장 반응을 재확인해야 합니다.",
        "",
        "투자 조언이 아닌 참고용 정책·규제 알림입니다.",
    ])
    return "\n".join(lines) + "\n"


def clear_alert_outputs(now: dt.datetime) -> None:
    report = render_report([], now)
    REPORT_PATH.write_text(report, encoding="utf-8")
    for path in (ALERT_PATH, TITLE_PATH, ALERTS_JSON_PATH):
        if path.exists():
            path.unlink()


def main() -> int:
    if not ALERTS_JSON_PATH.exists():
        return 0

    now = dt.datetime.now(tz=KST)
    try:
        alerts = json.loads(ALERTS_JSON_PATH.read_text(encoding="utf-8"))
    except Exception:
        return 0

    normalized: list[dict] = []
    for item in alerts:
        item["sectors"] = direct_sectors(item)
        if is_low_impact_false_positive(item):
            continue
        normalized.append(item)

    if not normalized:
        clear_alert_outputs(now)
        print("policy_guardrails=cleared_all_alerts")
        return 0

    ALERTS_JSON_PATH.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not any(is_personnel(item) for item in normalized):
        report = render_report(normalized, now)
        REPORT_PATH.write_text(report, encoding="utf-8")
        ALERT_PATH.write_text(report, encoding="utf-8")
        top = normalized[0]
        TITLE_PATH.write_text(f"KHS 정책 워치: [{top.get('importance', '중')}] {str(top.get('title') or '')[:70]}\n", encoding="utf-8")
    print(f"policy_guardrails=normalized alerts={len(normalized)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
