#!/usr/bin/env python3
"""Route KHS policy-watch alerts into separate delivery lanes."""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from zoneinfo import ZoneInfo

from khs_policy_alert_explainer import ensure_explained, explanation_lines

KST = ZoneInfo("Asia/Seoul")
OUT_DIR = Path("out")

POLICY_REPORT_PATH = OUT_DIR / "khs_policy_watch.md"
POLICY_ALERT_PATH = OUT_DIR / "khs_policy_watch_alert.md"
POLICY_TITLE_PATH = OUT_DIR / "khs_policy_watch_alert_title.txt"
POLICY_ALERTS_JSON_PATH = OUT_DIR / "khs_policy_watch_alerts.json"

KOREA_PERSONNEL_ALERTS_JSON_PATH = OUT_DIR / "khs_korea_presidential_personnel_alerts.json"

MATCHED_KEY_LABELS = {
    "court_order": "법원 명령/판결",
    "final_rule": "최종 규칙",
    "permit_restart": "인허가·임대 재개",
    "sanctions_tariffs_export": "제재·관세·수출통제",
    "agency_order": "기관 명령/규칙",
    "fcc_decision_notice": "규칙 제안·회의 공지",
    "presidential_action": "대통령 정책문서",
    "korea_presidential_personnel": "대통령실 고위급 인사",
    "company_filing": "기업 공시",
    "fda_decision": "FDA 결정",
}

TERM_LABELS = {
    "final rule": "최종규칙",
    "interim final rule": "임시최종규칙",
    "effective date": "시행일",
    "implementation": "시행",
    "commission meeting": "공개위원회 회의",
    "open meeting": "공개회의",
    "sunshine notice": "회의 공고",
    "proposed rule": "규칙 제안",
    "request for information": "정보요청",
    "rfi": "정보요청",
    "rulemaking": "규칙 제정 절차",
    "notice of proposed rulemaking": "규칙 제안 공고",
    "nprm": "규칙 제안 공고",
    "fnprm": "추가 규칙 제안 공고",
    "further notice of proposed rulemaking": "추가 규칙 제안 공고",
    "order": "명령",
    "broadband": "브로드밴드",
    "satellite": "위성",
    "spectrum": "주파수",
    "permit": "인허가",
    "tariff": "관세",
    "tariffs": "관세",
    "section 301": "무역법 301조",
    "customs enforcement": "통관 집행",
    "export controls": "수출통제",
    "entity list": "수출통제 명단",
    "executive order": "행정명령",
    "presidential memorandum": "대통령각서",
    "continuation of the national emergency": "국가비상사태 연장",
}

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

SOURCE_LABELS = {
    "federal register fcc": "미 연방관보 FCC",
    "federal register presidential documents": "미 연방관보 대통령문서",
    "federal register tariffs": "미 연방관보 관세",
    "federal register chips export": "미 연방관보 반도체·수출통제",
    "federal register energy": "미 연방관보 에너지",
    "federal register transformers": "미 연방관보 변압기",
    "commerce news": "미 상무부",
    "bis news": "미 BIS",
    "ustr press releases": "미 USTR",
    "ofac recent actions": "미 OFAC",
    "ferc news": "미 FERC",
    "doe news": "미 에너지부",
    "sec press releases": "미 SEC",
    "ftc press releases": "미 FTC",
    "fda press announcements": "미 FDA",
    "boem news": "미 BOEM",
}


def is_personnel(item: dict) -> bool:
    return "korea_presidential_personnel" in (item.get("matched") or {})


def is_whitehouse(item: dict) -> bool:
    source = str(item.get("source") or "").lower()
    link = str(item.get("link") or "").lower()
    return source.startswith("white house") or "whitehouse.gov" in link


def mostly_ascii(value: str) -> bool:
    letters = [ch for ch in value if ch.isalpha()]
    if not letters:
        return False
    ascii_letters = [ch for ch in letters if ord(ch) < 128]
    return len(ascii_letters) / max(len(letters), 1) >= 0.75


def alert_text(alert: dict) -> str:
    return " ".join([
        str(alert.get("source") or ""),
        str(alert.get("title") or ""),
        str(alert.get("summary") or ""),
        " ".join(term for terms in (alert.get("matched") or {}).values() for term in terms),
    ]).lower()


def is_fcc_resilient_networks_policy(alert: dict) -> bool:
    text = alert_text(alert)
    source = str(alert.get("source") or "").lower()
    return ("fcc" in source or "federal communications commission" in text) and any(term in text for term in FCC_RESILIENT_NETWORKS_TERMS)


def safe_title(alert: dict) -> str:
    title = str(alert.get("title") or "").strip()
    if not title:
        return "미국 정책·규제 문서 공표"
    if is_fcc_resilient_networks_policy(alert):
        return "FCC, 재난 시 통신망 장애보고 시스템(DIRS) 현대화 최종규칙 공표"
    if mostly_ascii(title):
        source = str(alert.get("source") or "").lower()
        text = alert_text(alert)
        if "fcc" in source or "federal communications commission" in text:
            return "FCC, 통신 규제 문서 공표"
        if "distribution transformer" in text or "electrical core steel" in text or "grain-oriented electrical steel" in text or "goes" in text or "amorphous" in text:
            return "미국, 변압기 효율규제 재검토"
        if "tariff" in text or "section 301" in text or "customs" in text:
            return "미국, 관세·통상 규정 공표"
        if "export control" in text or "entity list" in text:
            return "미국, 수출통제 규정 공표"
        if "nuclear" in text or "reactor" in text:
            return "미국, 원전 정책 문서 공표"
        if "fda" in text:
            return "FDA, 바이오·의약품 규제 결정 공표"
        return "미국 정책·규제 문서 공표"
    return title


def display_source(source: object) -> str:
    raw = str(source or "source").strip()
    return SOURCE_LABELS.get(raw.lower(), raw)


def enrich_missing_context(alert: dict) -> dict:
    if is_fcc_resilient_networks_policy(alert):
        alert = dict(alert)
        alert["importance"] = "중"
        alert["impacts"] = alert.get("impacts") or ["시간표", "의사결정 영향 제한적"]
        alert["paths"] = alert.get("paths") or ["정책 타임라인", "규제 준수"]
        alert["sectors"] = ["미국 통신망 복구/장애보고"]
        alert.setdefault(
            "policy_plain_summary",
            "FCC가 재난·정전·허리케인 등 통신장애 때 사업자가 DIRS에 보고하는 절차를 현대화한 최종규칙입니다. 통신망 투자 확대나 주파수 경매가 아니라 재난 대응 보고·행정 부담 조정 성격입니다.",
        )
        alert.setdefault(
            "investment_view",
            "매출을 직접 늘리는 정책은 아닙니다. 미국 통신사·장비사의 단기 CAPEX, 한국 통신3사 실적, 국내 네트워크 장비 수주로 바로 연결되는 근거는 제한적입니다.",
        )
        alert.setdefault(
            "korea_market_impact",
            "한국장에서는 통신장비·위성·통신주 테마 반응이 붙어도 직접 가격 변수는 약합니다. 재난통신 장비 조달, 911·공공안전망 투자, 보안장비 의무화가 뒤따를 때만 재평가 후보입니다.",
        )
        alert.setdefault("priced_in", "낮음. 선반영 여부보다 영향 자체가 제한적입니다.")
        alert.setdefault(
            "counter",
            "최종규칙이라도 핵심은 보고 절차 정비입니다. 신규 예산·장비 발주·주파수 정책·보조금이 확인되지 않으면 실적 연결은 약합니다.",
        )
        alert.setdefault(
            "failure_signal",
            "미국 통신사 CAPEX 가이던스, 장비 발주, 공공안전망 예산, 국내 장비사 수주 공시가 없으면 테마성 반응에서 끝납니다.",
        )
        return alert

    alert = dict(alert)
    impacts = alert.get("impacts") or ["의사결정 영향 제한적"]
    sectors = alert.get("sectors") or ["정책/규제 일반"]
    alert.setdefault("policy_plain_summary", f"공식 정책·규제 문서에서 {', '.join(impacts)} 관련 상태 변화 후보가 확인됐습니다.")
    alert.setdefault("investment_view", "실제 투자 재료가 되려면 매출·마진·할인율·수급·정책 시간표 중 무엇이 바뀌는지 후속 원문과 시장 반응으로 확인해야 합니다.")
    alert.setdefault("korea_market_impact", f"한국장 체크 대상은 {', '.join(sectors)}입니다. 원문에 직접 근거가 없는 업종 확장은 제외합니다.")
    alert.setdefault("priced_in", "낮음~중간. 공식 원문 확인 후 한국장 확산 여부를 장전 레이더에서 재확인해야 합니다.")
    alert.setdefault("failure_signal", "시행일, 예산, 계약, 수급 반응, 관련 기업 공시가 뒤따르지 않으면 단발성 정책 뉴스로 끝납니다.")
    return ensure_explained(alert)


def display_matched_keys(matched: dict) -> str:
    if not matched:
        return "정책·규제"
    labels = [MATCHED_KEY_LABELS.get(str(key), str(key)) for key in matched.keys()]
    return ", ".join(dict.fromkeys(labels))


def display_terms(terms: list[str]) -> str:
    labels = [TERM_LABELS.get(str(term).lower(), str(term)) for term in terms]
    return ", ".join(dict.fromkeys(labels))


def no_general_report(now: dt.datetime) -> str:
    return "\n".join([
        f"🚨 KHS 정책·규제 고충격 워치 · {now:%Y년 %m월 %d일 %H:%M KST}",
        "",
        "고충격 일반 정책·규제 변경 직접 확인 없음",
        "",
        "💡 워치 판단: 이번 실행에서 일반 정책·규제 라인으로 따로 송출할 고충격 이벤트는 직접 확인되지 않았습니다.",
        "",
        "투자 조언이 아닌 참고용 정책·규제 알림입니다.",
    ]) + "\n"


def render_policy_report(alerts: list[dict], now: dt.datetime) -> str:
    if not alerts:
        return no_general_report(now)

    lines = [f"🚨 KHS 정책·규제 고충격 워치 · {now:%Y년 %m월 %d일 %H:%M KST}", ""]
    for idx, alert in enumerate(alerts, 1):
        alert = enrich_missing_context(alert)
        matched = alert.get("matched") or {}
        matched_terms = sorted({term for terms in matched.values() for term in terms})
        matched_keys = display_matched_keys(matched)
        matched_terms_text = display_terms(matched_terms[:8])
        source_label = display_source(alert.get("source"))
        title = safe_title(alert)
        lines.extend([
            f"## {idx}. [{alert.get('importance', '중')}·{alert.get('status', '확정')}] {title}",
            f"- 상태 변화: {matched_keys} 신호 확인 ({matched_terms_text})",
            f"- 원문/출처: [{source_label}]({alert.get('link', '')}) · 원천시각 {alert.get('published_kst') or '확인 불가'} · 조회 {now:%H:%M KST}",
            *explanation_lines(alert),
            "- 즉시 체크: 원문 전문, 시행일/마감일, 한국 밸류체인 노출, 관련 해외 티커·ETF 반응",
            "",
        ])
    lines.extend([
        "💡 워치 판단: 이번 실행은 일반 정책·규제 라인으로 송출할 이벤트만 분리했습니다. 전용 감시 대상은 별도 워치에서 따로 송출됩니다.",
        "",
        "투자 조언이 아닌 참고용 정책·규제 알림입니다.",
    ])
    return "\n".join(lines) + "\n"


def remove_outputs(paths: list[Path]) -> None:
    for path in paths:
        if path.exists():
            path.unlink()


def write_policy_outputs(alerts: list[dict], now: dt.datetime) -> None:
    POLICY_REPORT_PATH.write_text(render_policy_report(alerts, now), encoding="utf-8")
    if not alerts:
        remove_outputs([POLICY_ALERT_PATH, POLICY_TITLE_PATH, POLICY_ALERTS_JSON_PATH])
        return

    POLICY_ALERT_PATH.write_text(render_policy_report(alerts, now), encoding="utf-8")
    POLICY_ALERTS_JSON_PATH.write_text(json.dumps(alerts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    top = alerts[0]
    POLICY_TITLE_PATH.write_text(
        f"KHS 정책 워치: [{top.get('importance', '중')}] {safe_title(top)[:70]}\n",
        encoding="utf-8",
    )


def main() -> int:
    now = dt.datetime.now(tz=KST)
    if not POLICY_ALERTS_JSON_PATH.exists():
        if KOREA_PERSONNEL_ALERTS_JSON_PATH.exists():
            KOREA_PERSONNEL_ALERTS_JSON_PATH.unlink()
        return 0

    try:
        alerts = json.loads(POLICY_ALERTS_JSON_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"policy_router=skip json_error={exc}")
        return 0

    policy_alerts: list[dict] = []
    personnel_alerts: list[dict] = []
    whitehouse_count = 0
    for item in alerts:
        if is_whitehouse(item):
            whitehouse_count += 1
        elif is_personnel(item):
            personnel_alerts.append(item)
        else:
            policy_alerts.append(item)

    write_policy_outputs(policy_alerts, now)
    if personnel_alerts:
        KOREA_PERSONNEL_ALERTS_JSON_PATH.write_text(
            json.dumps(personnel_alerts, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    else:
        remove_outputs([KOREA_PERSONNEL_ALERTS_JSON_PATH])

    print(
        "policy_router=split "
        f"policy={len(policy_alerts)} korea_personnel={len(personnel_alerts)} "
        f"whitehouse_routed_out={whitehouse_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
