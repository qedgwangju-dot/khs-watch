#!/usr/bin/env python3
import hashlib
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALERT_PATH = ROOT / "out" / "honam_semiconductor_alert.json"
STATE_PATH = ROOT / "data" / "honam_semiconductor_watch_state.json"
PENDING_PATH = ROOT / "out" / "honam_semiconductor_pending_state.json"

STATE_TERMS = [
    "확정", "승인", "선정", "지정", "착수", "계약", "낙찰", "보완", "반려", "지연", "연기",
    "중단", "재검토", "검토 착수", "검토", "우려", "위험", "부족", "갈등", "변경", "확대", "축소",
    "증설", "예타 면제", "예비타당성조사 면제", "발표", "보고서", "실사", "착공", "준공", "양산",
    "공급", "수요", "법적 근거", "목적 외 사용", "사용료", "대안", "협의", "로드맵", "계획"
]

STRONG_TERMS = [
    "확정", "승인", "선정", "지정", "착수", "계약", "낙찰", "보완", "반려", "지연", "연기",
    "중단", "재검토", "검토 착수", "우려", "위험", "부족", "갈등", "변경", "확대", "축소",
    "증설", "예타 면제", "예비타당성조사 면제", "실사", "착공", "준공", "양산", "법적 근거",
    "목적 외 사용"
]

ENTITY_TERMS = [
    "환경영향평가", "장록습지", "람사르", "산정지구", "광주공항", "광주 군공항", "함평", "무안",
    "무안공항", "삼성전자", "SK하이닉스", "동복댐", "주암댐", "장흥댐", "보성강댐", "나주댐",
    "영산강", "섬진강", "하수재이용수", "전력", "용수", "변전소", "송전", "주거", "정주",
    "팹", "클러스터", "국가산단", "국가산업단지", "소부장", "배후기지", "군공항"
]

OFFICIAL_HINTS = ["공식자료", "정부", "국회", "국토교통부", "산업통상자원부", "기후", "LH", "한국전력", "한국수자원공사"]

PROPOSAL_ONLY_TERMS = ["5분 자유발언", "의원이 제안", "의원, ", "의원은", "정책 제안", "필요성 강조"]
PROPOSAL_ADOPTION_TERMS = ["채택", "의결", "조례", "예산 반영", "수립 착수", "tf 구성", "시행", "확정"]

# 이미 공식·신뢰자료로 공개된 사건군의 최소 기준선.
# 같은 계획을 새 기사로 다시 설명한 것만으로는 이 수준을 넘지 못한다.
KNOWN_FAMILY_ACTION_LEVELS = {
    "honam_settlement_governance": 2,   # 9/27: 10/7 반도체도시과·정주팀 신설 계획 공개
    "honam_settlement_healthcare": 1,   # 9/29: 의료 포함 정주여건을 초기부터 함께 추진 지시
}

ACTION_EXECUTION_PATTERNS = [
    r"출범했다", r"출범식", r"착수했다", r"공사에 착수", r"첫 삽",
    r"체결했다", r"협약을 체결", r"계약을 체결", r"낙찰됐다", r"선정됐다",
    r"지정했다", r"지정됐다", r"해제했다", r"해제됐다", r"발주했다",
    r"시행했다", r"시행됐다", r"공급을 시작", r"공급 개시", r"운영을 시작",
    r"가동을 시작", r"양산을 시작", r"양산 개시", r"준공했다", r"완료했다",
]
ACTION_COMMITTED_TERMS = [
    "신설", "구성", "수립 착수", "예산 반영", "승인", "최종 지정", "지정 고시",
    "협약 체결", "계약 체결", "낙찰", "선정", "확정", "일정 변경", "연기 확정",
    "축소 확정", "확대 확정", "증설 확정", "해제",
]
ACTION_RISK_TERMS = ["반려", "중단", "지연", "부족", "갈등", "위험", "우려", "재입찰", "무산"]
ACTION_PLAN_TERMS = ["계획", "검토", "추진", "예정", "방침", "시급", "필요", "밑그림", "제안", "로드맵"]


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _item_text(item):
    return " ".join([
        _norm(item.get("title")),
        _norm(item.get("description")),
        _norm(item.get("body_excerpt")),
        _norm(item.get("headline")),
        _norm(item.get("detail")),
        _norm(item.get("reason")),
        _norm(item.get("impact")),
        _norm(item.get("source_status")),
    ]).strip()


def _executive_visit_signal(item):
    """Classify the SK chairman's site visit from the lead, not old background."""
    lead = " ".join([
        _norm(item.get("title")),
        _norm(item.get("description")),
        _norm(item.get("headline")),
    ]).lower()
    heading = " ".join([_norm(item.get("title")), _norm(item.get("headline"))]).lower()
    # 본문에서 과거 최태원 발언을 인용한 다른 경영진 방문 기사는 제외한다.
    if not any(term in heading for term in ("최태원", "sk그룹 회장", "sk 회장", "최 회장")):
        return 0
    if not any(x in lead for x in ("광주 군공항", "광주공항", "군공항", "호남")):
        return 0
    if not any(x in lead for x in ("반도체", "sk하이닉스", "팹", "fab")):
        return 0
    if not any(x in lead for x in ("방문", "찾", "부지", "현장", "실사")):
        return 0

    phase = str(item.get("event_phase") or "").lower()
    if phase == "scheduled":
        return 1
    if phase == "completed":
        return 3

    completed_verbs = (
        "방문했다", "방문을 마쳤", "방문 완료", "현장을 찾았다",
        "직접 찾았다", "현장을 둘러봤", "현장 점검했다",
        "실사를 마쳤", "현장 방문 마쳤",
    )
    if any(x in heading for x in completed_verbs):
        return 3
    # 기사 설명의 '지난달 사장단이 방문했다'는 과거 배경이다.
    # 회장 본인의 완료 동사가 같은 문장에 있을 때만 완료로 승격한다.
    for sentence in re.split(r"(?<=[.!?])\s+|(?<=다\.)\s+", _norm(item.get("description")).lower()):
        if any(actor in sentence for actor in ("최태원", "최 회장")) and any(verb in sentence for verb in completed_verbs):
            return 3
    # '방문한다', '찾는다', '예정'을 완료로 취급하지 않는다.
    return 1


def _extract_numbers(text):
    vals = re.findall(r"\d[\d,.]*\s*(?:명|가구|세대|년|월|일|억|조|만평|평|㎡|km|㎞|mw|gw|%|톤/일|만\s*톤/일|만톤/일|t/일)?", text, flags=re.I)
    out = []
    for v in vals:
        v = re.sub(r"\s+", "", v.lower())
        if v and v not in out:
            out.append(v)
    return out[:8]


def _event_key(item):
    text = _item_text(item).lower()
    stages = sorted(item.get("stages") or ([item.get("stage")] if item.get("stage") else []))
    entities = sorted({t.lower() for t in ENTITY_TERMS if t.lower() in text})
    states = sorted({t.lower() for t in STATE_TERMS if t.lower() in text})
    numbers = _extract_numbers(text)
    basis = "|".join(stages) + "||" + "|".join(entities) + "||" + "|".join(states) + "||" + "|".join(numbers)
    if not basis.strip("|"):
        basis = text[:240]
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:28]


def _is_material_event(item):
    if _executive_visit_signal(item):
        return True
    text = _item_text(item)
    low = text.lower()
    strong = any(t.lower() in low for t in STRONG_TERMS)
    numbers = bool(_extract_numbers(text))
    official = any(t.lower() in low for t in OFFICIAL_HINTS) or item.get("source_status") == "공식자료"
    contextual = any(t.lower() in low for t in ["계획", "수요", "공급", "보고서", "발표", "협의", "로드맵"])
    return strong or official or (numbers and contextual)



# 2026-09-22 기자간담회까지 이미 공개된 호남 반도체 실행 로드맵.
# 기사 발행일이나 제목이 달라져도 아래 기존 상태를 재서술한 것만으로는 새 알림을 만들지 않는다.
KNOWN_ROADMAP_MARKERS = [
    "250만평", "63만평", "2027년 상반기", "2027년 하반기", "2028년 12월",
    "3.1gw", "6.3gw", "23km", "23㎞", "15만", "35만", "65만", "106만",
    "2030년 6월", "입주 협약", "입주협약", "팹 4기", "4기 기준", "2만3천명",
]

# 계획 재서술이 아니라 실제 단계가 바뀐 경우만 기존 로드맵 차단을 해제한다.
EXECUTION_UPGRADE_TERMS = [
    "협약 체결", "협약을 체결", "협약식 개최", "투자 확정", "투자계약",
    "최종 지정", "지정 고시", "착공식", "첫 삽", "공사 시작", "공사에 착수",
    "전원 인가", "공급 개시", "공급 시작", "준공 완료", "양산 개시", "양산 시작",
    "일정 변경", "일정이 변경", "연기 확정", "앞당기기로", "취소", "무산",
    "축소 확정", "확대 확정", "증설 확정",
]


def _is_known_baseline_only(item):
    # 회장의 신규 현장방문은 과거 팹 로드맵 수치를 함께 언급해도 별개 사건이다.
    if _executive_visit_signal(item):
        return False
    text = _item_text(item)
    low = text.lower()

    # 실제 체결·착공·공급개시·일정변경처럼 실행 상태가 변했으면 반드시 통과시킨다.
    if any(term.lower() in low for term in EXECUTION_UPGRADE_TERMS):
        return False

    # 9/22에 공개된 수치·일정을 여러 개 다시 묶어 쓴 후속기사는 같은 로드맵의 재서술이다.
    marker_hits = {marker.lower() for marker in KNOWN_ROADMAP_MARKERS if marker.lower() in low}
    if "반도체" in low and len(marker_hits) >= 2:
        return True

    # 250만평 + 삼성/SK 입주협약 '추진·계획' 조합도 이미 공개된 상태다.
    if "250만평" in low and ("입주 협약" in low or "입주협약" in low) and (
        "삼성" in low or "sk하이닉스" in low or "하이닉스" in low
    ):
        return True

    # 2030년 6월 첫 양산 목표의 단순 재인용도 차단한다.
    if re.search(r"2030(?:년)?(?:\s*6월)?[^\n]{0,50}양산|양산[^\n]{0,50}2030(?:년)?(?:\s*6월)?", text, re.I):
        return True

    return False


def _is_proposal_only(item):
    text = _item_text(item).lower()
    proposal = any(t.lower() in text for t in PROPOSAL_ONLY_TERMS) or ("의원" in text and "제안" in text)
    adopted = any(t.lower() in text for t in PROPOSAL_ADOPTION_TERMS)
    return proposal and not adopted


def _action_level(item):
    executive_signal = _executive_visit_signal(item)
    if executive_signal:
        return executive_signal
    text = _item_text(item).lower()
    if any(re.search(pattern, text, flags=re.I) for pattern in ACTION_EXECUTION_PATTERNS):
        return 3
    if any(term.lower() in text for term in ACTION_COMMITTED_TERMS):
        return 2
    # 공식 보고서나 보도에서 확인된 지연·부족·우려도 시간표/실패모드의 실제 상태 신호다.
    if any(term.lower() in text for term in ACTION_RISK_TERMS):
        return 2
    if any(term.lower() in text for term in ACTION_PLAN_TERMS):
        return 1
    return 0


def _event_family(item):
    # 검증된 사건 접수의 고유 식별자는 기사 URL이 아닌 사업·당사자·방문일이다.
    family = _norm(item.get("event_family"))
    if family.startswith("honam_sk_chair_site_visit_") and _executive_visit_signal(item):
        return family
    if _executive_visit_signal(item):
        # 이번 10/9 방문: '예정' 기사와 다음 날 실제 방문 기사를 한 사건으로 연결.
        return "honam_sk_chair_site_visit_20261009"
    text = _item_text(item).lower()
    if "반도체" in text and ("반도체도시과" in text or "반도체도시정주팀" in text):
        return "honam_settlement_governance"
    if "반도체" in text and ("의료" in text or "병원" in text or "응급" in text) and "정주" in text:
        return "honam_settlement_healthcare"
    # 9/29 메가프로젝트 점검회의와 후속 보도를 하나의 사건군으로 묶는다.
    if "반도체" in text and (
        ("메가프로젝트" in text and ("정주" in text or "군공항" in text))
        or ("계통관리변전소" in text and "10월 1" in text)
        or ("2028년 중순" in text and ("재검토" in text or "당길" in text))
    ):
        return "honam_megaproject_20260929"
    # 같은 기자차담회/로드맵을 제목만 바꿔 쓴 보도는 한 사건으로 묶는다.
    if "반도체" in text and "2030" in text and "양산" in text and any(
        marker in text for marker in ["2027", "2028", "3.1gw", "6.3gw", "15만", "35만", "65만", "106만", "63만평", "208만"]
    ):
        return "honam_execution_roadmap"
    if "입법조사처" in text and "용수" in text and any(marker in text for marker in ["우려", "안정성", "댐", "가뭄"]):
        return "honam_water_supply_risk"
    return ""

def _verification_level(items):
    if any(i.get("_kind") == "official" or i.get("source_status") == "공식자료" for i in items):
        return 3
    independent = {
        (_norm(i.get("source")) or _norm(i.get("url"))).lower()
        for i in items
        if _norm(i.get("source")) or _norm(i.get("url"))
    }
    if len(independent) >= 2:
        return 2
    return 1


def _verification_status(level):
    return {
        3: "공식자료 확인",
        2: "복수 보도 교차확인",
        1: "단일 보도·공식 미확정",
    }.get(int(level or 0), "확인 필요")


def _summarize_event(items):
    if any(_executive_visit_signal(i) for i in items):
        completed = any(_executive_visit_signal(i) >= 3 for i in items)
        if completed:
            return "최태원 SK그룹 회장, 광주 군공항 팹 예정지 현장 방문 완료 보도"
        return "최태원 SK그룹 회장, 10월 9일 광주 군공항 팹 예정지 방문 예정"
    text = " ".join(_item_text(i) for i in items)
    low = text.lower()
    points = []
    if "2028년 중순" in low and ("재검토" in low or "당길" in low):
        points.append("광주 군공항 임시이전 완료시기(2028년 중순)를 더 앞당기도록 재검토 지시")
    if "계통관리변전소" in low and "10월 1" in low:
        points.append("호남권 계통관리변전소 지정 10월 1일 해제")
    if "정주" in low and ("묶어서" in low or "하나의 계획" in low or "동시 진행" in low):
        points.append("산업단지와 정주여건을 사업 초기부터 함께 추진")
    if points:
        return " / ".join(points[:3])
    for item in items:
        title = _norm(item.get("title")) or _norm(item.get("headline"))
        if title:
            return title
    return "호남 반도체 관련 상태 변화"


def _merge_group(items):
    ordered = sorted(
        items,
        key=lambda i: (
            -_action_level(i),
            0 if (i.get("_kind") == "official" or i.get("source_status") == "공식자료") else 1,
            _norm(i.get("published")),
        ),
    )
    first = dict(ordered[0])
    evidence = []
    seen = set()
    merged_stages = []
    merged_labels = []
    for it in ordered:
        for stage in it.get("stages", []) or ([it.get("stage")] if it.get("stage") else []):
            if stage and stage not in merged_stages:
                merged_stages.append(stage)
        for label in it.get("stage_labels", []):
            if label and label not in merged_labels:
                merged_labels.append(label)
        url = _norm(it.get("url"))
        source = _norm(it.get("source")) or _norm(it.get("source_status")) or "근거자료"
        key = (source, url)
        if key in seen:
            continue
        seen.add(key)
        evidence.append({"source": source, "url": url, "published": _norm(it.get("published"))})
    level = _verification_level(ordered)
    evidence.sort(key=lambda ev: (1 if "news.google.com" in str(ev.get("url") or "") else 0))
    first["evidence_count"] = len(evidence)
    first["evidence_sources"] = evidence[:5]
    first["verification_level"] = level
    first["verification_status"] = _verification_status(level)
    first["source_status"] = _verification_status(level)
    first["stages"] = merged_stages
    first["stage_labels"] = merged_labels
    # 방문 장소에서 전력·용수를 논의할 예정이라는 내용은
    # 전력 공급량·용수 확보 상태 자체가 바뀌었다는 뜻이 아니다.
    executive_visit = any(_executive_visit_signal(i) for i in ordered)
    if executive_visit:
        first["stages"] = ["6_산단투자_기업일정"]
        first["stage_labels"] = ["⑥ 산단·기업투자·팹 일정"]
        completed = any(_executive_visit_signal(i) >= 3 for i in ordered)
        first["impact"] = (
            "SK그룹 회장 광주 군공항 현장 방문 완료 확인"
            if completed else "SK그룹 회장 현장 방문 예정·투자계약은 별도 확인"
        )
        first["reason"] = (
            "기존 SK하이닉스 사장단 검토 이후 회장 현장방문 단계로 진전. "
            "군공항 부지·전력·용수·인허가 실제 협의 결과는 후속 확인"
        )
    summary = _summarize_event(ordered)
    if summary:
        first["title"] = summary
        first["headline"] = summary
    if len(evidence) > 1:
        first["source"] = " · ".join([e["source"] for e in evidence[:3]]) + (f" 외 {len(evidence)-3}곳" if len(evidence) > 3 else "")
    return first


def main():
    if not ALERT_PATH.exists():
        print("event_filter: no alert candidate")
        return

    alert = json.loads(ALERT_PATH.read_text(encoding="utf-8"))
    state = json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {}
    pending = json.loads(PENDING_PATH.read_text(encoding="utf-8")) if PENDING_PATH.exists() else dict(state)
    seen_event_keys = set(state.get("seen_event_keys", []))
    seen_event_levels = {str(k): int(v) for k, v in (state.get("event_status_levels") or {}).items()}
    seen_action_levels = {str(k): int(v) for k, v in (state.get("event_action_levels") or {}).items()}

    candidates = []
    for item in alert.get("official_changes", []):
        obj = dict(item)
        obj["_kind"] = "official"
        if _is_material_event(obj):
            candidates.append(obj)
    for item in alert.get("new_items", []):
        obj = dict(item)
        obj["_kind"] = "news"
        # 새 기사 자체가 아니라 실제 주제·상태 변화만 통과시킨다.
        # 기존 로드맵 재서술과 채택되지 않은 단순 제안은 알림 후보에서 제외한다.
        if _is_material_event(obj) and not _is_known_baseline_only(obj) and not _is_proposal_only(obj):
            candidates.append(obj)

    groups = {}
    all_event_keys = []
    for item in candidates:
        family = _event_family(item)
        key = hashlib.sha256(("family|" + family).encode("utf-8")).hexdigest()[:28] if family else _event_key(item)
        item["event_key"] = key
        item["event_family"] = family
        all_event_keys.append(key)
        groups.setdefault(key, []).append(item)

    new_groups = {}
    current_levels = dict(seen_event_levels)
    current_action_levels = dict(seen_action_levels)
    for key, items in groups.items():
        level = _verification_level(items)
        action_level = max((_action_level(item) for item in items), default=0)
        family = next((str(item.get("event_family") or "") for item in items if item.get("event_family")), "")
        baseline_action = int(KNOWN_FAMILY_ACTION_LEVELS.get(family, 0))
        previous_level = int(seen_event_levels.get(key, 0))
        previous_action = max(int(seen_action_levels.get(key, 0)), baseline_action)

        current_levels[key] = max(level, previous_level)
        current_action_levels[key] = max(action_level, previous_action)

        is_new_key = key not in seen_event_keys
        action_upgrade = action_level > previous_action
        verification_upgrade = (
            previous_action > baseline_action
            and action_level >= previous_action
            and level > previous_level
        )
        genuinely_new = is_new_key and action_level > baseline_action

        # 새 기사/새 도메인만으로는 알리지 않는다.
        # 기존 기준선보다 행동·공식상태가 올라가거나, 이미 올라간 사건의 검증등급이 상승할 때만 재알림한다.
        if action_upgrade or verification_upgrade or genuinely_new:
            new_groups[key] = items

    final_news, final_official = [], []
    for key, items in new_groups.items():
        merged = _merge_group(items)
        merged["event_key"] = key
        merged["verification_upgrade"] = int(seen_event_levels.get(key, 0)) > 0
        if any(i.get("_kind") == "official" or i.get("source_status") == "공식자료" for i in items):
            merged.pop("_kind", None)
            final_official.append(merged)
        else:
            merged.pop("_kind", None)
            final_news.append(merged)

    pending["seen_event_keys"] = list(dict.fromkeys(all_event_keys + list(seen_event_keys)))[:3000]
    pending["event_status_levels"] = current_levels
    pending["event_action_levels"] = current_action_levels
    pending["alert_basis"] = "topic_event_official_state_change"
    pending["article_role"] = "evidence_and_crosscheck_only"
    pending["baseline_guard"] = "canonical_url_title_dedupe_plus_family_action_level_state_machine"
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if not final_news and not final_official:
        ALERT_PATH.unlink(missing_ok=True)
        print(f"event_filter: suppressed={len(candidates)} reason=no_new_event_state")
        return

    alert["new_items"] = final_news
    alert["official_changes"] = final_official
    alert["new_count"] = len(final_news) + len(final_official)
    alert["alert_basis"] = "주제·사건·공식 상태 변화"
    alert["article_role"] = "감지 근거·교차검증"
    ALERT_PATH.write_text(json.dumps(alert, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"event_filter: new_events={alert['new_count']} evidence_candidates={len(candidates)}")


if __name__ == "__main__":
    main()
