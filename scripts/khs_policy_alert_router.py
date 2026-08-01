#!/usr/bin/env python3
"""Route KHS policy-watch alerts into separate delivery lanes."""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from khs_policy_alert_explainer import ensure_explained, explanation_lines
except ImportError:  # pragma: no cover - supports module-style local tests.
    from scripts.khs_policy_alert_explainer import ensure_explained, explanation_lines
try:
    from khs_compact_text import concise_text
except ImportError:  # pragma: no cover - supports module-style local tests.
    from scripts.khs_compact_text import concise_text

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
    "energy_security_policy": "에너지부 전력·원전·대출/제한 정책",
    "state_smr_moc_policy": "국무부 SMR 국제협력 MOC",
    "presidential_action": "대통령 정책문서",
    "agriculture_supply_policy": "농업·비료·식량 공급정책",
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
    "covered list": "FCC 보안장비 목록",
    "equipment authorization": "장비 인증",
    "national security": "국가안보",
    "foreign adversary": "외국 적대국",
    "secure equipment": "보안 장비",
    "communications supply chain": "통신 공급망",
    "inverter": "인버터",
    "energy inverter": "에너지 인버터",
    "loan guarantee": "대출보증",
    "conditional commitment": "조건부 지원 약정",
    "funding opportunity": "자금지원 공고",
    "efficiency standard": "효율규제",
    "critical materials": "핵심소재",
    "nuclear fuel": "핵연료",
    "state department": "미 국무부",
    "department of state": "미 국무부",
    "office of the spokesperson": "국무부 대변인실",
    "memorandum of cooperation": "협력각서",
    "moc": "협력각서",
    "trilateral": "3국 협력",
    "small modular reactor": "소형모듈원전",
    "small modular reactors": "소형모듈원전",
    "smr": "SMR",
    "bwrx-300": "BWRX-300",
    "first program": "FIRST 프로그램",
    "samsung c&t": "삼성물산",
    "ge vernova": "GE Vernova",
    "hitachi": "Hitachi",
    "sge": "SGE",
    "indo-pacific": "인도·태평양",
    "smr regional training hub": "SMR 지역훈련허브",
    "fertilizer": "비료",
    "phosphate": "인산비료",
    "phosphate fertilizer": "인산비료",
    "duty-free importation": "무관세 수입",
    "temporary duty-free": "임시 무관세",
    "agriculture": "농업",
    "farm resilience": "농업 회복력",
    "regenerative agriculture": "재생농업",
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
    "china mofcom announcements": "중국 상무부 공식 공고",
    "federal register fcc": "미 연방관보 FCC",
    "federal register presidential documents": "미 연방관보 대통령문서",
    "federal register tariffs": "미 연방관보 관세",
    "federal register chips export": "미 연방관보 반도체·수출통제",
    "federal register energy": "미 연방관보 에너지",
    "federal register commerce national security": "미 연방관보 상무부·국가안보",
    "federal register doe ferc nrc power": "미 연방관보 에너지·전력·원전",
    "federal register doe restrictions loans": "미 연방관보 DOE 대출·제한·효율규제",
    "federal register agriculture supply": "미 연방관보 농업·비료",
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
    "white house executive orders": "백악관 행정명령",
    "white house executive order": "백악관 행정명령",
    "white house presidential memoranda": "백악관 대통령각서",
    "white house presidential memorandum": "백악관 대통령각서",
    "white house proclamations": "백악관 포고문",
    "white house fact sheets": "백악관 팩트시트",
    "white house fact sheet": "백악관 팩트시트",
    "white house remarks": "백악관 트럼프 발언",
    "white house briefings statements": "백악관 브리핑·성명",
    "state department office spokesperson": "미 국무부 대변인실",
    "state department press releases": "미 국무부 보도자료",
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
        str(alert.get("original_title") or ""),
        str(alert.get("link") or ""),
        str(alert.get("summary") or ""),
        " ".join(term for terms in (alert.get("matched") or {}).values() for term in terms),
    ]).lower()


def is_fcc_resilient_networks_policy(alert: dict) -> bool:
    text = alert_text(alert)
    source = str(alert.get("source") or "").lower()
    return ("fcc" in source or "federal communications commission" in text) and any(term in text for term in FCC_RESILIENT_NETWORKS_TERMS)


def is_fcc_submarine_cable_policy(alert: dict) -> bool:
    text = alert_text(alert)
    source = str(alert.get("source") or "").lower()
    return (
        ("fcc" in source or "federal communications commission" in text or "federalregister.gov" in text)
        and any(
            term in text
            for term in (
                "submarine cable",
                "submarine-cable",
                "cable landing",
                "landing license",
                "undersea cable",
                "해저케이블",
                "해저 통신케이블",
                "랜딩 라이선스",
            )
        )
    )


def is_fcc_upper_c_band_auction(alert: dict) -> bool:
    text = alert_text(alert)
    return (
        ("fcc" in text or "federalregister.gov" in text)
        and "upper c-band" in text
        and any(term in text for term in ("auction", "competitive bidding", "flexible use licenses"))
    )


def is_fcc_foreign_equipment_proposal(alert: dict) -> bool:
    text = alert_text(alert)
    return (
        ("fcc" in text or "federalregister.gov" in text)
        and any(term in text for term in ("foreign-produced", "foreign produced"))
        and any(term in text for term in ("prohibiting", "prohibit", "importation", "marketing"))
        and any(term in text for term in ("seeking comment", "request for comment", "comment"))
    )
def is_china_mofcom_trade_control(alert: dict) -> bool:
    text = alert_text(alert)
    source = str(alert.get("source") or "").lower()
    has_authority = (
        "china mofcom" in source
        or "mofcom" in text
        or "china ministry of commerce" in text
        or "chinese ministry of commerce" in text
        or "中国商务部" in text
        or "商务部" in text
    )
    has_action = any(
        term in text
        for term in (
            "export ban", "export suspension", "suspend exports", "suspended exports",
            "export restriction", "export control", "export licensing", "dual-use items",
            "tariff", "anti-dumping", "antidumping", "countervailing",
            "出口管制", "暂停出口", "停止出口", "禁止出口", "出口禁令", "出口许可",
            "两用物项", "关税", "反倾销", "反补贴", "管控名单", "禁令",
        )
    ) or ("出口" in text and any(term in text for term in ("管制", "暂停", "停止", "禁止", "许可", "禁令"))) or (
        any(term in text for term in ("export", "exports"))
        and any(term in text for term in ("suspend", "suspends", "suspended", "ban", "bans", "banned"))
    )
    return has_authority and has_action


def china_mofcom_product(text: str) -> str:
    products = (
        (("helium", "氦"), "헬륨"),
        (("rare earth", "rare-earth", "稀土"), "희토류"),
        (("gallium", "镓"), "갈륨"),
        (("germanium", "锗"), "게르마늄"),
        (("graphite", "石墨"), "흑연"),
        (("antimony", "锑"), "안티몬"),
        (("tungsten", "钨"), "텅스텐"),
        (("indium", "铟"), "인듐"),
        (("battery", "cathode", "anode", "lfp", "电池"), "배터리 소재·기술"),
        (("semiconductor", "chip", "半导体"), "반도체 품목"),
        (("steel", "钢铁"), "철강"),
        (("dual-use", "两用物项"), "이중용도 품목"),
    )
    for terms, label in products:
        if any(term in text for term in terms):
            return label
    return "전략 품목"


def china_mofcom_action(text: str) -> str:
    if any(term in text for term in ("暂停出口", "停止出口", "export suspension", "suspend exports", "suspended exports")) or (
        "出口" in text and any(term in text for term in ("暂停", "停止"))
    ) or (
        any(term in text for term in ("export", "exports"))
        and any(term in text for term in ("suspend", "suspends", "suspended"))
    ):
        return "수출 일시 중단"
    if any(term in text for term in ("禁止出口", "出口禁令", "export ban", "banned exports")) or (
        any(term in text for term in ("export", "exports"))
        and any(term in text for term in ("ban", "bans", "banned"))
    ):
        return "수출 금지"
    if any(term in text for term in ("反倾销", "anti-dumping", "antidumping")):
        return "반덤핑 조치"
    if any(term in text for term in ("反补贴", "countervailing")):
        return "상계관세 조치"
    if any(term in text for term in ("关税", "tariff", "tariffs")):
        return "관세 조치"
    if any(term in text for term in ("出口许可", "export licensing")):
        return "수출 허가제"
    return "수출통제"


def china_mofcom_title(alert: dict) -> str:
    text = alert_text(alert)
    return f"중국 상무부, {china_mofcom_product(text)} {china_mofcom_action(text)} 발표"


def safe_title(alert: dict) -> str:
    title_ko = str(alert.get("title_ko") or "").strip()
    if title_ko:
        return title_ko
    ensure_explained(alert)
    title_ko = str(alert.get("title_ko") or "").strip()
    if title_ko:
        return title_ko
    title = str(alert.get("title") or "").strip()
    if not title:
        return "미국 정책·규제 문서 공표"
    if is_fcc_resilient_networks_policy(alert):
        return "FCC, 재난 시 통신망 장애보고 시스템(DIRS) 현대화 최종규칙 공표"
    if is_fcc_submarine_cable_policy(alert):
        return "FCC, 해저케이블 랜딩 라이선스 국가안보 심사 규칙 재검토"
    if is_fcc_upper_c_band_auction(alert):
        return "FCC, 상단 C대역 차세대 무선통신 주파수 경매 일정 공표"
    if is_fcc_foreign_equipment_proposal(alert):
        return "FCC, 외국산 군용급 무인기·핵심부품 수입·판매 금지안 의견수렴"
    if is_china_mofcom_trade_control(alert):
        return china_mofcom_title(alert)
    if mostly_ascii(title):
        source = str(alert.get("source") or "").lower()
        text = alert_text(alert)
        if "petition for reconsideration" in text:
            return "FCC, 규칙 재심 청원 접수 공지"
        if "covered communications equipment" in text or (
            "covered list" in text
            and ("prohibit" in text or "importation" in text or "marketing" in text)
        ):
            return "FCC, 보안 위험 통신장비 수입·판매 제한 절차 공표"
        if "fcc" in source or "federal communications commission" in text:
            return "FCC, 통신 규제 문서 공표"
        if (
            "distribution transformer" in text
            or "electrical core steel" in text
            or "grain-oriented electrical steel" in text
            or "goes" in text
            or "amorphous" in text
        ):
            return "미국, 변압기 효율규제 재검토"
        if "tariff" in text or "section 301" in text or "customs" in text:
            return "미국, 관세·통상 규정 공표"
        if "export control" in text or "entity list" in text:
            return "미국, 수출통제 규정 공표"
        if "memorandum of cooperation" in text and (
            "small modular reactor" in text or "smr" in text
        ):
            return "미·일·한, 제3국 SMR 배치 협력 MOC 체결"
        if "nuclear" in text or "reactor" in text:
            return "미국, 원전 정책 문서 공표"
        if "fda" in text:
            return "FDA, 바이오·의약품 규제 결정 공표"
        if (
            "historic defense investment" in text
            or ("nato allies" in text and "defense industrial base" in text)
            or "arsenal of freedom" in text
        ):
            return "백악관, NATO 방위투자 확대·미국 방산 생산 강화 발표"
        if "white house" in source or "whitehouse.gov" in text:
            if "fact sheet" in text:
                return "백악관, 정책 팩트시트 발표"
            if "remarks" in text or "president trump" in text or "donald j. trump" in text:
                return "트럼프 대통령 발언, 정책 영향 후보"
            if "statement" in text or "briefing" in text:
                return "백악관, 정책 성명·브리핑 발표"
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

    if is_fcc_submarine_cable_policy(alert):
        alert = dict(alert)
        alert["importance"] = "중"
        alert["impacts"] = ["시간표", "할인율"]
        alert["paths"] = ["정책 타임라인", "국가안보 심사", "규제 리스크"]
        alert["sectors"] = ["해저케이블/국제통신망", "통신보안", "통신/FCC"]
        alert["korea_value_chain"] = ["해저 통신케이블", "국제망 보안", "통신장비", "통신사 해외망"]
        alert["title_ko"] = "FCC, 해저케이블 랜딩 라이선스 국가안보 심사 규칙 재검토"
        alert["policy_plain_summary"] = "FCC가 해저 통신케이블 랜딩 라이선스 규칙과 절차를 국가안보 환경 변화에 맞춰 재검토하는 공식 규제 문서입니다."
        alert["investment_view"] = "핵심은 태양광·전력장비 수입금지가 아니라 국제 통신망 인허가와 보안 심사 시간표입니다. 신규 케이블 허가, 외국 지분·운영자 심사, 데이터센터 연결망 규제가 구체화될 때만 투자 재료가 됩니다."
        alert["korea_market_impact"] = "한국장에서는 해저 통신케이블, 국제망 보안, 통신장비, 통신사 해외망 노출만 제한적으로 확인합니다. 원문 근거 없이 …2537 tokens truncated…가 재료로 약합니다."
        return
    if is_china_mofcom_trade_control(alert):
        product = china_mofcom_product(text)
        action = china_mofcom_action(text)
        alert["importance"] = "상"
        alert["title_ko"] = china_mofcom_title(alert)
        alert["policy_plain_summary"] = f"중국 상무부가 {product} 관련 {action}을 발표한 사안입니다. 적용 품목·국가·시행일과 예외 허가가 실제 공급 감소 폭을 결정합니다."
        alert["investment_view"] = f"{product}의 중국발 공급이 줄면 현물가격, 조달기간, 재고비용이 올라 수입업체 마진과 생산계획이 바뀔 수 있습니다. 단순 허가제인지 전면 금지인지 구분해야 합니다."
        if product == "헬륨":
            alert["korea_market_impact"] = "한국장에서는 반도체·HBM 공정, 디스플레이, 광섬유, MRI, 산업가스 밸류체인의 재고와 조달가격을 확인합니다. 중국산 의존도와 대체 조달 계약이 확인된 기업만 연결합니다."
            sectors = ["반도체/HBM 공정가스", "디스플레이/광섬유", "산업가스", "의료기기/MRI"]
        elif product in {"희토류", "갈륨", "게르마늄", "흑연", "안티몬", "텅스텐", "인듐"}:
            alert["korea_market_impact"] = "한국장에서는 반도체·2차전지·자석·방산·전력전자 소재 중 해당 중국산 원료 의존도와 비중국 대체 공급망이 확인된 기업만 선별합니다."
            sectors = ["핵심광물/소재", "반도체", "2차전지", "방산/전력전자"]
        else:
            alert["korea_market_impact"] = "한국장에서는 원문에 직접 적시된 품목의 중국산 의존도, 재고일수, 대체 공급선, 한국 기업의 수출입 노출이 확인된 업종만 연결합니다."
            sectors = ["중국 수출통제/핵심소재", "공급망", "관세/수출주"]
        alert["impacts"] = ["매출·마진·현금흐름", "수급", "시간표"]
        alert["paths"] = ["공급·수요", "원자재 비용", "공급망", "정책 타임라인"]
        alert["sectors"] = sectors
        alert["korea_value_chain"] = sectors
        alert["priced_in"] = "낮음~중간. 속보 직후 관련 원자재와 테마주는 먼저 움직일 수 있지만 실제 이익 영향은 품목 범위와 시행기간 확인 뒤 결정됩니다."
        alert["counter"] = "수출 허가 예외, 특정 국가·기업 한정, 기존 계약 유예, 중국 외 공급 확대가 있으면 공급 충격이 예상보다 작을 수 있습니다."
        alert["failure_signal"] = "공식 원문에서 품목·대상국·시행일이 확인되지 않거나 현물가격·리드타임·국내 조달비용이 움직이지 않으면 테마성 반응으로 끝납니다."
        return
    if is_fcc_submarine_cable_policy(alert):
        alert["importance"] = "중"
        alert["title_ko"] = "FCC, 해저케이블 랜딩 라이선스 국가안보 심사 규칙 재검토"
        alert["policy_plain_summary"] = "FCC가 해저 통신케이블 랜딩 라이선스 규칙과 절차를 국가안보 환경 변화에 맞춰 재검토하는 공식 규제 문서입니다."
        alert["investment_view"] = "핵심은 태양광·전력장비 수입금지가 아니라 국제 통신망 인허가와 보안 심사 시간표입니다. 신규 케이블 허가, 외국 지분·운영자 심사, 데이터센터 연결망 규제가 구체화될 때만 투자 재료가 됩니다."
        alert["korea_market_impact"] = "한국장에서는 해저 통신케이블, 국제망 보안, 통신장비, 통신사 해외망 노출만 제한적으로 확인합니다. 원문 근거 없이 태양광·전력변환 테마로 확장하지 않습니다."
        alert["impacts"] = ["시간표", "할인율"]
        alert["paths"] = ["정책 타임라인", "국가안보 심사", "규제 리스크"]
        alert["sectors"] = ["해저케이블/국제통신망", "통신보안", "통신/FCC"]
        alert["korea_value_chain"] = ["해저 통신케이블", "국제망 보안", "통신장비", "통신사 해외망"]
        alert["priced_in"] = "낮음~중간. FCC 국가안보 문서라 테마 반응은 가능하지만, 한국 기업의 직접 수주·인허가 노출이 확인되기 전에는 가격 변수로 약합니다."
        alert["counter"] = "규칙·절차 재검토 단계일 수 있어 특정 케이블 프로젝트의 승인·거절, 예산, 조달, 한국 기업 수혜가 확정된 것은 아닙니다."
        alert["failure_signal"] = "구체 라이선스 변경, 신규 심사 기준, 케이블 사업자 영향, 한국 기업 수주·공급망 노출이 확인되지 않으면 관찰 재료로만 처리합니다."
        return
    if is_fcc_upper_c_band_auction(alert):
        alert["importance"] = "상"
        alert["title_ko"] = "FCC, 상단 C대역 차세대 무선통신 주파수 경매 일정 공표"
        alert["policy_plain_summary"] = "FCC가 상단 C대역 100MHz 이상 면허의 차세대 무선통신 경매 일정을 공표했습니다."
        alert["investment_view"] = "중대역 주파수 공급은 미국 통신사의 5G·차세대망 CAPEX와 네트워크 장비 발주 시간표를 바꿀 수 있습니다."
        alert["korea_market_impact"] = "한국장에서는 미국향 통신장비·안테나·RF 부품과 통신사 CAPEX 노출이 확인되는 기업만 봅니다."
        alert["impacts"] = ["매출·마진·현금흐름", "시간표", "수급"]
        alert["paths"] = ["주파수 경매", "통신사 CAPEX", "장비 발주", "정책 타임라인"]
        alert["sectors"] = ["통신장비", "안테나/RF", "5G·차세대 무선통신"]
        alert["korea_value_chain"] = alert["sectors"]
        alert["priced_in"] = "낮음~중간. 경매 일정은 공식화됐지만 실제 장비 매출은 낙찰자와 구축계획 확인 뒤 반영됩니다."
        alert["counter"] = "주파수 경매가 통신사 CAPEX 총액 증가가 아니라 기존 투자 재배분에 그칠 수 있습니다."
        alert["failure_signal"] = "낙찰 결과, 통신사 CAPEX 상향, 장비 발주가 뒤따르지 않으면 직접 실적 재료는 약합니다."
        return
    if is_fcc_foreign_equipment_proposal(alert):
        alert["importance"] = "상"
        alert["status"] = "예비"
        alert["title_ko"] = "FCC, 외국산 군용급 무인기·핵심부품 수입·판매 금지안 의견수렴"
        alert["policy_plain_summary"] = "FCC가 외국산 군용 무인기(UAS)·핵심부품의 수입·판매 금지안에 대해 의견을 받습니다."
        alert["investment_view"] = "금지 대상과 시행일이 확정되면 미국 내 무인기·통신모듈·핵심부품 대체 조달과 방산 공급망 주문이 바뀔 수 있습니다."
        alert["korea_market_impact"] = "한국장에서는 무인기 플랫폼·통신모듈·탐지레이더·대드론 체계의 미국향 공급망 노출이 확인되는 기업만 봅니다."
        alert["impacts"] = ["매출·마진·현금흐름", "수급", "시간표"]
        alert["paths"] = ["수입 제한", "공급망 대체", "장비 조달", "정책 타임라인"]
        alert["sectors"] = ["무인기/UAS", "대드론", "탐지레이더", "방산 전자장비", "중국 대체 공급망"]
        alert["korea_value_chain"] = alert["sectors"]
        alert["priced_in"] = "낮음~중간. 현재는 의견수렴 단계여서 최종 금지 범위와 시행일이 남았습니다."
        alert["counter"] = "군용급 범위가 좁거나 기존 승인 제품·동맹국 부품이 예외면 대체 수요가 작을 수 있습니다."
        alert["failure_signal"] = "최종규칙, 군용급 UAS 범위, 대상 업체·부품, 시행일, 한국 기업 대체 수주가 없으면 테마성 반응에 그칩니다."
        return
    if "covered communications equipment" in text or ("covered list" in text and ("prohibit" in text or "importation" in text or "marketing" in text)):
        alert["title_ko"] = "FCC, 보안 위험 통신장비 수입·판매 제한 절차 공표"
        alert["policy_plain_summary"] = "FCC가 Covered List에 오른 보안 위험 통신장비의 미국 내 수입·판매 제한 절차를 공표한 사안입니다."
        alert["investment_view"] = "적용 장비와 공급사가 확정되면 중국산 통신장비 배제, 대체 공급망, 미국향 장비 수주 기대가 움직일 수 있습니다."
        alert["korea_market_impact"] = "한국장에서는 통신장비, 네트워크 장비, 보안장비 중 미국향 매출·대체 공급망 노출이 확인되는 종목만 선별 확인합니다."
        alert["sectors"] = ["무인기/UAS", "대드론", "탐지레이더", "방산 전자장비", "중국 대체 공급망"]
        alert["korea_value_chain"] = ["통신장비", "네트워크 장비", "보안장비", "미국향 장비 공급망"]
        alert["priced_in"] = "낮음~중간. 보안장비 규제 테마는 빠르게 반응하지만 적용 대상·시행일 확인 전 직접 실적 연결은 제한적입니다."
        alert["counter"] = "기존 승인 장비의 처리 절차일 수 있고, 한국 기업의 대체 수주나 공급망 노출이 없으면 과대해석입니다."
        alert["failure_signal"] = "적용 장비, 금지 범위, 시행일, 한국 기업의 미국향 수주·공급망 노출이 확인되지 않으면 테마성 반응으로 끝납니다."


def normalize_semantic_text(value: object) -> str:
    text = re.sub(r"https?://\S+", " ", str(value or "").lower())
    text = re.sub(r"[\W_]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def importance_rank(value: object) -> int:
    return {"상": 3, "중": 2, "하": 1}.get(str(value or ""), 0)


def merge_unique_list(left: object, right: object) -> list:
    merged: list = []
    for value in list(left or []) + list(right or []):
        if value and value not in merged:
            merged.append(value)
    return merged


def source_entries(alert: dict) -> list[dict]:
    entries = list(alert.get("source_links") or [])
    if alert.get("source") or alert.get("link"):
        entries.insert(0, {
            "source": alert.get("source") or "",
            "link": alert.get("link") or "",
            "published_kst": alert.get("published_kst") or "",
            "original_title": alert.get("original_title") or alert.get("title") or "",
        })
    deduped: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        source = str(entry.get("source") or "").strip()
        link = str(entry.get("link") or "").strip()
        key = (source, link)
        if key in seen:
            continue
        seen.add(key)
        deduped.append({**entry, "source": source, "link": link})
    return deduped


def merge_matched(left: dict, right: dict) -> dict:
    merged = {key: list(value or []) for key, value in (left or {}).items()}
    for key, values in (right or {}).items():
        bucket = merged.setdefault(key, [])
        for value in values or []:
            if value not in bucket:
                bucket.append(value)
    return merged


def source_family_from_text(value: str) -> str:
    raw = str(value or "").lower()
    normalized = normalize_semantic_text(raw)
    if "whitehouse gov" in normalized or "white house" in raw:
        return "whitehouse"
    if "state gov" in normalized or "department of state" in raw or "state department" in raw:
        return "state_department"
    if "boem gov" in normalized or re.search(r"\bboem\b", raw):
        return "boem"
    if "bsee gov" in normalized or re.search(r"\bbsee\b", raw):
        return "bsee"
    if "federal register fcc" in raw or "federal communications commission" in raw or re.search(r"\bfcc\b", raw):
        return "fcc"
    if "energy gov" in normalized or "department of energy" in raw or re.search(r"\bdoe\b", raw):
        return "doe"
    if "ferc gov" in normalized or re.search(r"\bferc\b", raw):
        return "ferc"
    if "commerce gov" in normalized or "bureau of industry and security" in raw or re.search(r"\bbis\b", raw):
        return "commerce_bis"
    if "ustr gov" in normalized or re.search(r"\bustr\b", raw):
        return "ustr"
    if "federalregister gov" in normalized or "federal register" in raw:
        return "federal_register_other"
    if "korea kr" in normalized or "bok or kr" in normalized or "fsc go kr" in normalized or "fss or kr" in normalized:
        return "korea_official"
    compact = normalize_semantic_text(raw)
    return compact[:80] or "unknown_source"


def alert_source_family(alert: dict) -> str:
    values = [
        alert.get("source"),
        alert.get("link"),
        alert.get("title"),
        alert.get("original_title"),
        alert.get("summary"),
    ]
    for entry in source_entries(alert):
        values.extend([
            entry.get("source"),
            entry.get("link"),
            entry.get("original_title"),
        ])
    return source_family_from_text(" ".join(str(value or "") for value in values))


def semantic_alert_key(alert: dict) -> str:
    probe = enrich_missing_context(dict(alert))
    apply_router_overrides(probe)
    whitehouse_story_key = str(probe.get("whitehouse_story_key") or "").strip()
    if whitehouse_story_key:
        return "whitehouse|" + normalize_semantic_text(whitehouse_story_key)
    title = safe_title(probe)
    sectors = "|".join(str(value) for value in probe.get("sectors") or [])
    impacts = "|".join(str(value) for value in probe.get("impacts") or [])
    matched_keys = "|".join(sorted((probe.get("matched") or {}).keys()))
    source_family = alert_source_family(probe)
    if probe.get("domestic_stablecoin_policy_watch"):
        return "stablecoin|" + normalize_semantic_text(title or probe.get("title"))
    return "|".join([
        normalize_semantic_text(source_family),
        normalize_semantic_text(title or probe.get("title")),
        normalize_semantic_text(sectors),
        normalize_semantic_text(impacts),
        normalize_semantic_text(matched_keys),
    ])


def merge_duplicate_alert(current: dict, incoming: dict) -> dict:
    current = dict(current)
    existing_entries = source_entries(current)
    existing_keys = {(entry.get("source"), entry.get("link")) for entry in existing_entries}
    extra_entries = [
        entry for entry in source_entries(incoming)
        if (entry.get("source"), entry.get("link")) not in existing_keys
    ]
    current["source_links"] = existing_entries + extra_entries
    sources = []
    for entry in current["source_links"]:
        source = str(entry.get("source") or "").strip()
        if source and source not in sources:
            sources.append(source)
    if sources:
        current["source"] = " / ".join(sources[:3])
    if not current.get("link") and incoming.get("link"):
        current["link"] = incoming.get("link")
    current["matched"] = merge_matched(current.get("matched") or {}, incoming.get("matched") or {})
    for key in ("impacts", "paths", "sectors", "korea_value_chain"):
        current[key] = merge_unique_list(current.get(key), incoming.get(key))
    if importance_rank(incoming.get("importance")) > importance_rank(current.get("importance")):
        current["importance"] = incoming.get("importance")
    for key in ("published_kst", "status", "policy_plain_summary", "investment_view", "korea_market_impact", "priced_in", "counter", "failure_signal"):
        if not current.get(key) and incoming.get(key):
            current[key] = incoming.get(key)
    return current


def dedupe_alerts(alerts: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    order: list[str] = []
    for alert in alerts:
        key = semantic_alert_key(alert)
        if not key.strip("| "):
            key = normalize_semantic_text(f"{alert.get('source')} {alert.get('title')} {alert.get('link')}")
        if key not in merged:
            merged[key] = dict(alert)
            order.append(key)
            continue
        merged[key] = merge_duplicate_alert(merged[key], alert)
    return [merged[key] for key in order]


def source_markdown(alert: dict) -> str:
    parts: list[str] = []
    for entry in source_entries(alert)[:3]:
        label = display_source(entry.get("source"))
        link = str(entry.get("link") or "").strip()
        parts.append(f"[{label}]({link})" if link else label)
    if not parts:
        label = display_source(alert.get("source"))
        link = str(alert.get("link") or "").strip()
        return f"[{label}]({link})" if link else label
    return " / ".join(parts)


def render_policy_report(alerts: list[dict], now: dt.datetime) -> str:
    if not alerts:
        return no_general_report(now)

    lines = [f"🚨 KHS 정책·규제 고충격 워치 · {now:%Y년 %m월 %d일 %H:%M KST}", ""]
    for idx, alert in enumerate(alerts, 1):
        alert = enrich_missing_context(alert)
        apply_router_overrides(alert)
        title = safe_title(alert)
        lines.extend([
            f"## {idx}. [{alert.get('importance', '중')}·{alert.get('status', '확정')}] {title}",
            *compact_explanation_lines(alert),
            f"- 출처: [원문 보기]({alert.get('link', '')}) · {display_source(alert.get('source'))} · 조회 {now:%H:%M KST}",
            "",
        ])
    return "\n".join(lines).rstrip() + "\n"


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
        if is_personnel(item):
            personnel_alerts.append(item)
        else:
            policy_alerts.append(item)

    raw_policy_count = len(policy_alerts)
    policy_alerts = dedupe_alerts(policy_alerts)
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
        f"policy={len(policy_alerts)} raw_policy={raw_policy_count} "
        f"korea_personnel={len(personnel_alerts)} "
        f"whitehouse_checked={whitehouse_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

