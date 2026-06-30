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

from khs_policy_alert_explainer import ensure_explained, explanation_lines

KST = ZoneInfo("Asia/Seoul")
OUT_DIR = Path("out")
REPORT_PATH = OUT_DIR / "khs_policy_watch.md"
ALERT_PATH = OUT_DIR / "khs_policy_watch_alert.md"
TITLE_PATH = OUT_DIR / "khs_policy_watch_alert_title.txt"
ALERTS_JSON_PATH = OUT_DIR / "khs_policy_watch_alerts.json"
KOREA_PERSONNEL_ALERTS_JSON_PATH = OUT_DIR / "khs_korea_presidential_personnel_alerts.json"


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
    ("금융/자본시장/스테이블코인", [
        "스테이블코인", "원화 스테이블코인", "디지털자산기본법", "디지털자산 기본법",
        "가상자산 2단계", "2단계 입법", "2단계법", "가상자산법", "디지털자산법",
        "준비자산", "상환청구권", "예금 대체", "한국은행", "금융위원회", "금융당국",
    ]),
    ("은행/핀테크/결제", [
        "은행", "은행권", "핀테크", "전자금융업자", "결제사업자", "지급결제",
        "결제 인프라", "결제 표준", "발행 주체", "발행주체",
    ]),
    ("가상자산거래소/디지털자산", [
        "가상자산거래소", "거래소", "디지털자산", "가상자산", "결제토큰",
        "디지털자산법", "가상자산법",
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

FCC_RESILIENT_NETWORKS_TERMS = [
    "resilient networks",
    "disruptions to communications",
    "disaster information reporting system",
    "dirs",
    "outage reporting",
    "network outage reporting",
    "communications disruption",
    "disaster reporting",
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


def is_whitehouse(item: dict) -> bool:
    source = str(item.get("source") or "").lower()
    link = str(item.get("link") or "").lower()
    return source.startswith("white house") or "whitehouse.gov" in link


def is_domestic_telecom_policy(item: dict) -> bool:
    return bool(item.get("telecom_policy_risk")) or "korea_telecom_policy" in (item.get("matched") or {})


def is_domestic_stablecoin_policy(item: dict) -> bool:
    return bool(item.get("domestic_stablecoin_policy_watch")) or "korea_stablecoin_policy" in (item.get("matched") or {})


def is_fcc_resilient_networks_policy(item: dict) -> bool:
    source = str(item.get("source") or "").lower()
    if "fcc" not in source and "federal communications commission" not in haystack_for(item):
        return False
    return has_any(haystack_for(item), FCC_RESILIENT_NETWORKS_TERMS)


def direct_sectors(item: dict) -> list[str]:
    if is_personnel(item):
        return item.get("sectors") or ["한국 대통령실/고위급 인사"]
    if is_domestic_telecom_policy(item):
        return item.get("sectors") or ["국내 통신정책/통신3사"]
    if is_domestic_stablecoin_policy(item):
        return item.get("sectors") or [
            "금융/자본시장/스테이블코인",
            "은행/핀테크/결제",
            "가상자산거래소/디지털자산",
        ]
    if is_fcc_resilient_networks_policy(item):
        return ["미국 통신망 복구/장애보고"]

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
    if is_domestic_stablecoin_policy(item):
        return "국내 디지털자산 정책: 원화 스테이블코인 법안·결제 표준 체크"
    if is_fcc_resilient_networks_policy(item):
        return "FCC, 재난 시 통신망 장애보고 시스템(DIRS) 현대화 최종규칙 공표"
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
            *explanation_lines(alert),
            *([f"- 국내 통신정책 체크: {alert.get('telecom_policy_check')}"] if alert.get("telecom_policy_check") else []),
            *([f"- 체크할 리스크: {alert.get('telecom_risk_table')}"] if alert.get("telecom_risk_table") else []),
            *([f"- 구조 변화: {alert.get('telecom_structure_note')}"] if alert.get("telecom_structure_note") else []),
            *([f"- 국내 스테이블코인 정책 체크: {alert.get('stablecoin_policy_check')}"] if alert.get("stablecoin_policy_check") else []),
            *([f"- 체크할 리스크: {alert.get('stablecoin_risk_table')}"] if alert.get("stablecoin_risk_table") else []),
            *([f"- 구조 변화: {alert.get('stablecoin_structure_note')}"] if alert.get("stablecoin_structure_note") else []),
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


def write_general_outputs(alerts: list[dict], now: dt.datetime) -> None:
    if not alerts:
        clear_alert_outputs(now)
        return
    report = render_report(alerts, now)
    REPORT_PATH.write_text(report, encoding="utf-8")
    ALERT_PATH.write_text(report, encoding="utf-8")
    ALERTS_JSON_PATH.write_text(json.dumps(alerts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    top = alerts[0]
    TITLE_PATH.write_text(f"KHS 정책 워치: [{top.get('importance', '중')}] {str(top.get('title') or '')[:70]}\n", encoding="utf-8")


def main() -> int:
    if not ALERTS_JSON_PATH.exists():
        return 0

    now = dt.datetime.now(tz=KST)
    try:
        alerts = json.loads(ALERTS_JSON_PATH.read_text(encoding="utf-8"))
    except Exception:
        return 0

    general_alerts: list[dict] = []
    personnel_alerts: list[dict] = []
    routed_whitehouse_count = 0
    seen: set[str] = set()
    for item in alerts:
        if is_whitehouse(item):
            routed_whitehouse_count += 1
            continue
        item["sectors"] = direct_sectors(item)
        if is_low_impact_false_positive(item):
            continue
        normalize_title(item)
        ensure_explained(item)
        key = dedup_key(item)
        if key in seen:
            continue
        seen.add(key)
        if is_personnel(item):
            personnel_alerts.append(item)
        else:
            general_alerts.append(item)

    write_general_outputs(general_alerts, now)
    if personnel_alerts:
        KOREA_PERSONNEL_ALERTS_JSON_PATH.write_text(
            json.dumps(personnel_alerts, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    elif KOREA_PERSONNEL_ALERTS_JSON_PATH.exists():
        KOREA_PERSONNEL_ALERTS_JSON_PATH.unlink()

    total_alerts = len(general_alerts) + len(personnel_alerts)
    if total_alerts == 0:
        print(f"policy_guardrails=cleared_all_alerts routed_whitehouse={routed_whitehouse_count}")
        return 0

    print(
        "policy_guardrails=split "
        f"general={len(general_alerts)} personnel={len(personnel_alerts)} "
        f"routed_whitehouse={routed_whitehouse_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
