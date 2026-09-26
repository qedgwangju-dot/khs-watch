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


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _extract_numbers(text):
    vals = re.findall(r"\d[\d,.]*\s*(?:명|가구|세대|년|월|일|억|조|만평|평|㎡|km|㎞|mw|gw|%|톤/일|만\s*톤/일|만톤/일|t/일)?", text, flags=re.I)
    out = []
    for v in vals:
        v = re.sub(r"\s+", "", v.lower())
        if v and v not in out:
            out.append(v)
    return out[:8]


def _event_key(item):
    text = " ".join([
        _norm(item.get("title")), _norm(item.get("headline")), _norm(item.get("detail")),
        _norm(item.get("reason")), _norm(item.get("impact"))
    ]).lower()
    stages = sorted(item.get("stages") or ([item.get("stage")] if item.get("stage") else []))
    entities = sorted({t.lower() for t in ENTITY_TERMS if t.lower() in text})
    states = sorted({t.lower() for t in STATE_TERMS if t.lower() in text})
    numbers = _extract_numbers(text)
    basis = "|".join(stages) + "||" + "|".join(entities) + "||" + "|".join(states) + "||" + "|".join(numbers)
    if not basis.strip("|"):
        basis = text[:240]
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:28]


def _is_material_event(item):
    text = " ".join([
        _norm(item.get("title")), _norm(item.get("headline")), _norm(item.get("detail")),
        _norm(item.get("reason")), _norm(item.get("impact")), _norm(item.get("source_status"))
    ])
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
    text = " ".join([
        _norm(item.get("title")), _norm(item.get("description")), _norm(item.get("headline")),
        _norm(item.get("detail")), _norm(item.get("reason")), _norm(item.get("impact"))
    ])
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
    text = " ".join([
        _norm(item.get("title")), _norm(item.get("description")), _norm(item.get("headline")),
        _norm(item.get("detail"))
    ]).lower()
    proposal = any(t.lower() in text for t in PROPOSAL_ONLY_TERMS) or ("의원" in text and "제안" in text)
    adopted = any(t.lower() in text for t in PROPOSAL_ADOPTION_TERMS)
    return proposal and not adopted


def _event_family(item):
    text = " ".join([
        _norm(item.get("title")), _norm(item.get("description")), _norm(item.get("headline")),
        _norm(item.get("detail"))
    ]).lower()
    # 같은 기자차담회/로드맵을 제목만 바꿔 쓴 보도는 한 사건으로 묶는다.
    if "반도체" in text and "2030" in text and "양산" in text and any(
        marker in text for marker in ["2027", "2028", "3.1gw", "6.3gw", "15만", "35만", "65만", "106만", "63만평", "208만"]
    ):
        return "honam_execution_roadmap"
    if "입법조사처" in text and "용수" in text and any(marker in text for marker in ["우려", "안정성", "댐", "가뭄"]):
        return "honam_water_supply_risk"
    return ""


def _merge_group(items):
    first = dict(items[0])
    evidence = []
    seen = set()
    for it in items:
        url = _norm(it.get("url"))
        source = _norm(it.get("source")) or _norm(it.get("source_status")) or "근거자료"
        key = (source, url)
        if key in seen:
            continue
        seen.add(key)
        evidence.append({"source": source, "url": url, "published": _norm(it.get("published"))})
    first["evidence_count"] = len(evidence)
    first["evidence_sources"] = evidence[:4]
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
        all_event_keys.append(key)
        groups.setdefault(key, []).append(item)

    new_groups = {k: v for k, v in groups.items() if k not in seen_event_keys}
    final_news, final_official = [], []
    for key, items in new_groups.items():
        merged = _merge_group(items)
        merged["event_key"] = key
        if any(i.get("_kind") == "official" for i in items):
            merged.pop("_kind", None)
            final_official.append(merged)
        else:
            merged.pop("_kind", None)
            final_news.append(merged)

    pending["seen_event_keys"] = list(dict.fromkeys(all_event_keys + list(seen_event_keys)))[:3000]
    pending["alert_basis"] = "topic_event_official_state_change"
    pending["article_role"] = "evidence_and_crosscheck_only"
    pending["baseline_guard"] = "suppress_20260922_roadmap_rehash_unless_execution_or_status_changes"
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
