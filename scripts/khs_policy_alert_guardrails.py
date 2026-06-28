#!/usr/bin/env python3
"""Post-run quality guardrails for KHS policy watch alerts.

This script runs after the source watcher and before Telegram delivery. It keeps
the detector broad, but makes the delivered alert stricter: sectors must have
direct text evidence, low-impact false positives are removed, and delivered
titles are Koreanized.
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
    ("국내 통신정책/통신3사", [
        "가계통신비", "통신비", "통신요금", "요금제", "5g 요금제", "중간요금제",
        "선택약정", "할인율", "단말기유통법", "단통법", "공시지원금", "전환지원금",
        "과학기술정보통신부", "과기정통부", "방송통신위원회", "방통위",
        "sk텔레콤", "kt", "lg유플러스", "arpu", "가입자당 평균매출",
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

LOW_IMPACT_TITLE_MARKERS = [
    "digital opportunity data collection",
    "modernizing the fcc form 477 data program",
    "delete, delete, delete",
    "television broadcasting services",
    "sunshine act meetings",
    "open commission meeting",
    "open commission meetings",
    "sunshine notice",
]

NATIONAL_EMERGENCY_CONTINUATION = "continuation of the national emergency"


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


def is_domestic_telecom_policy(item: dict) -> bool:
    return bool(item.get("telecom_policy_risk")) or "korea_telecom_policy" in (item.get("matched") or {})


def direct_sectors(item: dict) -> list[str]:
    if is_personnel(item):
        return item.get("sectors") or ["한국 대통령실/고위급 인사"]
    if is_domestic_telecom_policy(item):
        return item.get("sectors") or ["국내 통신정책/통신3사"]

    text = haystack_for(item)
    sectors = [label for label, terms in SECTOR_RULES if has_any(text, terms)]

    if "풍력/해상풍력" in sectors and not has_any(
        text,
        ["offshore wind", "wind energy", "wind lease", "wind leasing", "wind project", "wind area", "wind auction", "wind farm", "wind turbine"],
    ):
        sectors.remove("풍력/해상풍력")

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
    title = str(item.get("title") or "").lower()

    is_boem_marine_mineral = (
        "boem" in source
        and has_any(text, ["mineral leasing", "mineral lease", "marine minerals", "offshore mineral"])
        and not has_any(text, ["offshore wind", "critical mineral", "critical minerals", "lithium", "rare earth", "oil", "gas"])
    )
    if is_boem_marine_mineral:
        item["guardrail_note"] = "BOEM 해양광물 임대 의견수렴은 원문상 풍력·핵심광물·관세 직접 근거가 없어 고충격 알림에서 제외"
        return True

    if "federal register fcc" in source and any(marker in title for marker in LOW_IMPACT_TITLE_MARKERS):
        item["guardrail_note"] = "FCC 행정 데이터 수집·지역 방송·회의 공지는 한국장 고충격 가격 변수로 보기 어려워 제외"
        return True

    if NATIONAL_EMERGENCY_CONTINUATION in title:
        item["guardrail_note"] = "기존 국가비상사태 연례 연장은 신규 제재·관세·수출통제 조치가 아니므로 제외"
        return True

    return False


def mostly_ascii(value: str) -> bool:
    letters = [ch for ch in value if ch.isalpha()]
    if not letters:
        return False
    ascii_letters = [ch for ch in letters if ord(ch) < 128]
    return len(ascii_letters) / max(len(letters), 1) >= 0.75


def korean_title_for(item: dict) -> str:
    original = str(item.get("title") or "").strip()
    source = str(item.get("source") or "").lower()
    text = haystack_for(item)

    if is_domestic_telecom_policy(item):
        return "정부, 통신비 인하·요금제 개편 정책 압박 확인"
    if "export control" in text or "entity list" in text:
        return "미국, 반도체·첨단기술 수출통제 규정 공표"
    if "section 301" in text or "tariff" in text or "customs enforcement" in text:
        return "미국, 관세·통관 집행 관련 규정 공표"
    if "nuclear" in text or "reactor" in text or "uranium" in text:
        return "미국, 원전·핵연료 관련 정책 문서 공표"
    if "ferc" in text or "transmission" in text or "interconnection" in text or "power grid" in text:
        return "FERC, 전력망·전력시장 관련 규정 공표"
    if "fcc" in source or "federal communications commission" in text:
        if "spectrum" in text or "satellite" in text:
            return "FCC, 주파수·위성통신 관련 규정 공표"
        if "broadband" in text:
            return "FCC, 브로드밴드 통신 규정 공표"
        return "FCC, 통신 규제 문서 공표"
    if "fda" in text or "complete response letter" in text or "drug" in text:
        return "FDA, 바이오·의약품 규제 결정 공표"
    if "critical mineral" in text or "lithium" in text or "rare earth" in text:
        return "미국, 핵심광물 공급망 관련 정책 문서 공표"
    if "presidential" in source or "federal register presidential" in source:
        return "미국, 대통령 정책 문서 공표"
    if mostly_ascii(original):
        return "미국, 정책·규제 문서 공표"
    return original


def normalize_title(item: dict) -> None:
    original = str(item.get("title") or "").strip()
    ko_title = korean_title_for(item)
    if original and ko_title != original:
        item.setdefault("original_title", original)
        item["title"] = ko_title


def dedup_key(item: dict) -> str:
    title = str(item.get("title") or "").lower()
    link = str(item.get("link") or "").lower()
    source = str(item.get("source") or "").lower()
    return "|".join([source, re.sub(r"\s+", " ", title).strip(), link.rsplit("/", 1)[0]])


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
            *([f"- 국내 통신정책 체크: {alert.get('telecom_policy_check')}"] if alert.get("telecom_policy_check") else []),
            *([f"- 체크할 리스크: {alert.get('telecom_risk_table')}"] if alert.get("telecom_risk_table") else []),
            "- 반영 가능성: 낮음~중간. 공식 원문/신뢰 소스 확인 후 한국장 확산 여부를 장전 레이더에서 재확인해야 합니다.",
            "- 반대 근거: 원문 세부 조건, 시행일, 예외 조항, 개별 프로젝트 적용 여부 확인이 필요합니다.",
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
    seen: set[str] = set()
    for item in alerts:
        item["sectors"] = direct_sectors(item)
        if is_low_impact_false_positive(item):
            continue
        normalize_title(item)
        key = dedup_key(item)
        if key in seen:
            continue
        seen.add(key)
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
