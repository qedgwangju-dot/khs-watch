#!/usr/bin/env python3
"""Extension layer for the physical-AI Telegram watcher.

Adds high-signal lanes and alert-quality guards without duplicating the base watcher:
1) Microduck / Reachy Mini sales milestones -> implied ROBOTIS actuator demand
2) WONIK Holdings / WONIK Robotics commercialization, policy and customer expansion
3) Cross-publisher event deduplication and repeated-label cleanup
"""
from __future__ import annotations

import hashlib
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import robotis_physical_ai_watch as base

# Broaden discovery while keeping the existing dedup state/output format.
base.QUERIES.extend([
    '(Microduck OR 마이크로덕 OR "Reachy Mini" OR 리치미니) (판매 OR 판매량 OR sold OR sales OR orders OR 주문 OR 15000 OR 15,000 OR 20000 OR 20,000) (ROBOTIS OR 로보티즈 OR DYNAMIXEL OR 액추에이터)',
    '(Microduck OR 마이크로덕) (15000 OR 15,000 OR 1만5000 OR 1.5만 OR 600만달러 OR "6 million")',
    '(원익홀딩스 OR 원익로보틱스 OR "WONIK Robotics" OR "WONIK Holdings") (로봇 OR 휴머노이드 OR humanoid OR 피지컬AI OR "physical AI") (상용화 OR 양산 OR 공급 OR 수주 OR 고객 OR 사업확장 OR 사업 확장 OR 정책 OR 예산 OR 육성)',
    '(원익로보틱스 OR "WONIK Robotics") (Allegro Hand OR 알레그로핸드 OR 알레그로 OR AMMR OR AMR OR 로봇핸드 OR 모바일휴머노이드 OR 모바일 휴머노이드 OR Roboligent OR 로볼리전트)',
    '(원익홀딩스 OR 원익로보틱스) (지능형로봇 OR 지능형 로봇 OR 정부 OR 산업부 OR 과기정통부 OR 정책 OR 예산 OR 규제 OR 실증 OR 조달)',
])

base.TRUSTED.update({
    "아이뉴스24", "iNews24", "The Information",
})
base.OFFICIAL_OR_PRIMARY.update({
    "원익로보틱스", "WONIK Robotics",
})
base.MAX_ALERTS = max(base.MAX_ALERTS, 9)

_orig_topic_group = base.topic_group
_orig_score = base.score
_orig_category = base.category
_orig_tag_for = base.tag_for
_orig_meaning = base.meaning
_orig_risk = base.risk
_orig_verification = base.verification
_orig_clean_title = base.clean_title


def _norm_title(value: str) -> str:
    value = re.sub(r"\s+-\s+[^-]+$", "", value or "")
    value = value.lower()
    value = re.sub(r"\[(?:단독|현장|fn마켓워치|리포트\s*브리핑)[^\]]*\]", " ", value, flags=re.I)
    value = re.sub(r"[^0-9a-z가-힣一-龥]+", " ", value, flags=re.I)
    return re.sub(r"\s+", " ", value).strip()


def key(item: dict) -> str:
    """Source-independent key so an identical syndicated headline is one story."""
    title = _norm_title(item.get("title", ""))
    return hashlib.sha256(title.encode()).hexdigest()


def clean_title(title: str, source: str) -> str:
    """Avoid output such as '로보티즈 로보티즈 ...'."""
    title = _orig_clean_title(title, source)
    for label in ("로보티즈", "원익로보틱스", "배터리", "테슬라옵티머스", "촉각·로봇데이터"):
        title = re.sub(rf"^{re.escape(label)}(?:\s+|\s*[,·:：\-–—]\s*)", "", title, count=1, flags=re.I)
    return title.strip()


def topic_group(text: str) -> str | None:
    if re.search(r"원익홀딩스|원익로보틱스|WONIK Holdings|WONIK Robotics|Allegro Hand|알레그로핸드", text, re.I):
        return "wonik"
    return _orig_topic_group(text)


def score(item: dict) -> int:
    text = f"{item.get('title','')} {item.get('description','')} {item.get('source','')}"
    group = topic_group(text)

    if group == "wonik":
        source = item.get("source") or ""
        s = 7
        if base.NUMERIC.search(text):
            s += 2
        if source in base.OFFICIAL_OR_PRIMARY:
            s += 5
        elif source in base.TRUSTED:
            s += 3
        if re.search(r"상용화|정책|예산|육성|규제|실증|조달|정부|산업부|과기정통부", text, re.I):
            s += 4
        if re.search(r"공급|수주|고객|양산|생산|배치|투입|계약|MOU|협력|사업\s*확장|신제품|출시", text, re.I):
            s += 5
        if re.search(r"Allegro Hand|알레그로|AMMR|AMR|Roboligent|로볼리전트", text, re.I):
            s += 3
        return s

    s = _orig_score(item)
    if group == "robotis" and re.search(r"Microduck|마이크로덕|Reachy Mini|리치미니", text, re.I):
        if re.search(r"판매|판매량|sold|sales|orders|주문|15000|15,000|1만5000|1\.5만", text, re.I):
            s += 5
        if re.search(r"15개|15\s*(?:actuators?|motors?)|22\.5만|225,?000", text, re.I):
            s += 3
    return s


def category(text: str, group: str) -> str:
    if group == "wonik":
        if re.search(r"정책|예산|육성|규제|정부|산업부|과기정통부|조달", text, re.I):
            return "정책·상용화"
        return "원익로보틱스 사업 확장"
    if group == "robotis" and re.search(r"Microduck|마이크로덕|Reachy Mini|리치미니", text, re.I) and re.search(r"판매|판매량|sold|sales|orders|주문", text, re.I):
        return "판매량×액추에이터 수요"
    return _orig_category(text, group)


def tag_for(group: str) -> str:
    if group == "wonik":
        return "원익로보틱스"
    return _orig_tag_for(group)


def meaning(cat: str) -> str:
    if cat == "판매량×액추에이터 수요":
        return "완제품 판매대수에 대당 액추에이터 탑재량을 곱해 ROBOTIS의 잠재 부품 수요를 바로 검산합니다. 예를 들어 Microduck 1.5만대×15개면 22.5만개로, 지난해 ROBOTIS 연간 실제 출하량 약 22만개와 맞먹는 규모입니다."
    if cat == "정책·상용화":
        return "정부 로봇 상용화·실증·예산 확대가 원익로보틱스의 Allegro Hand·AMR·AMMR·모바일 휴머노이드 사업에 실제 고객·조달·양산으로 연결되는지 봅니다."
    if cat == "원익로보틱스 사업 확장":
        return "원익로보틱스가 로봇핸드 중심 연구개발 사업에서 AMR·AMMR·모바일 휴머노이드와 산업 자동화 고객으로 매출 경로를 넓히는 신호인지 확인합니다."
    return _orig_meaning(cat)


def risk(cat: str) -> str:
    if cat == "판매량×액추에이터 수요":
        return "22.5만개는 판매대수×15개로 계산한 내재 수요입니다. ROBOTIS가 22.5만개를 이미 출하·매출 인식했다는 뜻은 아니므로 실제 납품·생산·재고 변화를 따로 확인해야 합니다."
    if cat == "정책·상용화":
        return "정책 수혜 기대와 확정 매출은 다릅니다. 세부 예산 집행, 조달 공고, 고객 실명, 납품 대수와 원익로보틱스 수주 공시가 없으면 주가 테마에 그칠 수 있습니다."
    if cat == "원익로보틱스 사업 확장":
        return "MOU·전시·시제품만으로 양산 매출을 확정할 수 없습니다. 반복 주문, 설치 대수, 가동률과 유지보수 매출을 확인해야 합니다."
    return _orig_risk(cat)


def verification(item: dict, group: str, text: str) -> str:
    if group == "wonik":
        source = item.get("source") or ""
        if source in base.OFFICIAL_OR_PRIMARY:
            return "회사 공식자료"
        if source in base.TRUSTED:
            return "신뢰 매체 보도 · 회사/정부 원문 재확인"
        return "보도 단계 · 회사/정부 원문 재확인 필요"
    if group == "robotis" and re.search(r"Microduck|마이크로덕", text, re.I) and re.search(r"판매|sold|sales|orders", text, re.I):
        return "판매 보도 + 대당 15개 탑재 교차확인 · 실제 ROBOTIS 출하량은 별도"
    return _orig_verification(item, group, text)


def _event_features(text: str) -> set[str]:
    checks = {
        "blockdeal": r"블록딜|block deal|클럽딜",
        "1000eok": r"1000\s*억|1,?000\s*억",
        "solidstate": r"전고체|고체전해질|solid[- ]state|sulfide|황화물",
        "robot_battery": r"휴머노이드.*배터리|배터리.*휴머노이드|로봇.*배터리|배터리.*로봇",
        "2027_mass": r"2027.*양산|2027.*생산|양산.*2027",
        "k1_sale": r"AI\s*사피엔스|AI\s*Sapiens|\bK1\b",
        "nov_sale": r"11월.*판매|판매.*11월|초기.*완판|완판",
        "microduck": r"Microduck|마이크로덕",
        "15000": r"15,?000|1만\s*5000|1\.5만",
        "wonik_policy": r"원익.*(?:정책|상용화)|(?:정책|상용화).*원익",
        "optimus_order": r"Optimus|옵티머스|擎天柱",
        "order": r"발주|주문|order|订单",
    }
    return {name for name, pat in checks.items() if re.search(pat, text, re.I)}


def _entity_features(text: str) -> set[str]:
    checks = {
        "robotis": r"로보티즈|ROBOTIS|DYNAMIXEL|다이나믹셀",
        "ecopro": r"에코프로|EcoPro",
        "wonik": r"원익홀딩스|원익로보틱스|WONIK",
        "tesla": r"Tesla|테슬라|特斯拉",
        "byd": r"BYD|비야디|比亚迪|PaXini|파시니|帕西尼",
    }
    return {name for name, pat in checks.items() if re.search(pat, text, re.I)}


def _same_event(a: dict, b: dict) -> bool:
    if a.get("group") != b.get("group"):
        return False

    ta = _norm_title(a.get("title", ""))
    tb = _norm_title(b.get("title", ""))
    if not ta or not tb:
        return False
    if ta == tb:
        return True
    if SequenceMatcher(None, ta, tb).ratio() >= 0.72:
        return True

    text_a = f"{a.get('title','')} {a.get('description','')}"
    text_b = f"{b.get('title','')} {b.get('description','')}"
    entities = _entity_features(text_a) & _entity_features(text_b)
    events = _event_features(text_a) & _event_features(text_b)
    if entities and len(events) >= 2:
        return True
    return False


def _source_rank(item: dict) -> tuple[int, int, str]:
    source = item.get("source") or ""
    if source in base.OFFICIAL_OR_PRIMARY:
        tier = 3
    elif source in base.TRUSTED:
        tier = 2
    else:
        tier = 1
    return (tier, int(item.get("score", 0)), item.get("published") or "")


def _dedupe_events(candidates: list[dict]) -> list[dict]:
    """Collapse syndicated/rewritten copies of one underlying event.

    When copies exist, prefer official/primary, then trusted media, then the
    highest-scoring/freshest item.
    """
    clusters: list[list[dict]] = []
    for item in candidates:
        for cluster in clusters:
            if _same_event(item, cluster[0]):
                cluster.append(item)
                break
        else:
            clusters.append([item])

    reps = [max(cluster, key=_source_rank) for cluster in clusters]
    reps.sort(key=lambda x: (x.get("score", 0), x.get("published") or ""), reverse=True)
    return reps


def select_diverse(items: list[dict], seen: set[str], force: bool, limit: int) -> list[dict]:
    candidates = items if force else [x for x in items if x["key"] not in seen]
    candidates = _dedupe_events(candidates)
    if not candidates:
        return []

    chosen: list[dict] = []
    used: set[str] = set()
    for group in ["tesla", "battery", "robotis", "wonik", "byd_paxini"]:
        for x in candidates:
            if x.get("group") == group and x["key"] not in used:
                chosen.append(x)
                used.add(x["key"])
                break
        if len(chosen) >= limit:
            return chosen
    for x in candidates:
        if x["key"] in used:
            continue
        chosen.append(x)
        used.add(x["key"])
        if len(chosen) >= limit:
            break
    return chosen


# Monkey-patch extension hooks used by base.main().
base.key = key
base.clean_title = clean_title
base.topic_group = topic_group
base.score = score
base.category = category
base.tag_for = tag_for
base.meaning = meaning
base.risk = risk
base.verification = verification
base.select_diverse = select_diverse

if __name__ == "__main__":
    base.main()
