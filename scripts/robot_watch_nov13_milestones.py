"""Source-graded Nov 13 robotics milestones in the existing alert route.

Does not change Telegram destinations, cadence, historical dedup keys or
contract standards. Short-lived backfills are not new recurring sources.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re

MERGER = "spacex_tesla_combination"
DKT = "dkt_auto_oled_expansion"
COST = "robot_cost_economics"
MERGER_BACKFILL = "__20261112_reuters_spacex_tesla_progress__"
DKT_BACKFILL = "__20261113_user_dkt_auto_oled_report__"

QUERIES = (
    MERGER_BACKFILL,
    DKT_BACKFILL,
    '(SpaceX OR 스페이스X) (Tesla OR 테슬라) (merger OR 합병 OR special committee OR 특별위원회 OR exchange ratio OR 교환비율 OR approval OR 승인)',
    '(디케이티 OR DKT) (북미 OR North American) (차량용 OLED OR Auto OLED OR 자동차 OLED) (양산 OR 신규 고객 OR 추가 수주 OR 공급 계약)',
    '(Anthropic OR 앤트로픽) (robot cost OR robot exposure OR 로봇 비용 OR 경제성 OR cost competitive) (revised OR revised study OR 70% OR 0.3% OR update OR 보고서)',
)

OFFICIAL_MERGER = {"Tesla", "Tesla Investor Relations", "SpaceX", "SpaceX Investor Relations", "테슬라 공식", "SpaceX IR"}
OFFICIAL_DKT = {"디케이티", "DKT", "디케이티 공식", "DKT IR"}
OFFICIAL_COST = {"Anthropic", "Anthropic Research", "앤트로픽", "앤트로픽 연구"}

CATEGORIES = {
    MERGER: "SpaceX·테슬라 기업결합 · 보도와 공시 단계 구분",
    DKT: "디케이티 · 북미 차량용 OLED 신규 공급 확대",
    COST: "앤트로픽 · 로봇 경제성 및 실제 노동 대체 조건",
}

def identity(text: str) -> str:
    if re.search(r"Space\s*X|스페이스\s*X", text, re.I) and re.search(r"Tesla|테슬라", text, re.I) and re.search(r"합병|기업결합|combination|merger|특별위원회|special committee|교환비율|exchange ratio", text, re.I):
        return MERGER
    if re.search(r"디케이티|\bDKT\b", text, re.I) and re.search(r"OLED|유기발광", text, re.I) and re.search(r"차량|완성차|전기차|automotiv|auto OLED", text, re.I) and re.search(r"북미|North America|북미 최대", text, re.I):
        return DKT
    if re.search(r"Anthropic|앤트로픽", text, re.I) and re.search(r"robot|로봇", text, re.I) and re.search(r"비용|가격|경제성|직업|노동|일자리|cost|job|work|exposure", text, re.I):
        return COST
    return ""

def _body(item: dict) -> str:
    return " ".join(str(item.get(k) or "") for k in ("title", "description"))

def stage(item: dict, group: str) -> str:
    title = str(item.get("title") or "")
    body = _body(item)
    src = str(item.get("source") or "").strip()
    if group == MERGER:
        if src in OFFICIAL_MERGER:
            if re.search(r"(합병|기업결합|merger|combination).{0,65}(완료|종결|closing completed|closed)", title, re.I):
                return "official_close"
            if re.search(r"(합병|기업결합|merger|combination).{0,80}(주주총회 승인|주주 승인|shareholder approval|shareholder vote approved)|shareholders? approved", title, re.I):
                return "official_approval"
            if re.search(r"(합병|기업결합|merger|combination).{0,80}(철회|중단|무산|terminated|abandoned)", title, re.I):
                return "official_termination"
            if re.search(r"(합병|기업결합|merger|combination).{0,80}(본계약 체결|최종 계약 체결|definitive agreement signed|binding agreement signed)", title, re.I):
                return "official_signed"
        if re.search(r"합병|merger|combination", title, re.I) and (
            re.search(r"협상.{0,12}진전|합병.{0,18}협상.{0,18}진전|talks? progress|advanced merger talks|merger talks advance", title, re.I)
            or (re.search(r"2026.{0,3}12월|12월|December|2027년 초|early 2027", title, re.I)
                and re.search(r"협상 진전|talks progressing|negotiations advancing", body, re.I))
        ):
            return "reported_progress_20261112"
        return "baseline_committee"
    if group == DKT:
        if src in OFFICIAL_DKT:
            if re.search(r"(차량용|완성차|OLED).{0,65}(정식 공급계약 체결|구매계약 체결|binding supply contract signed)", title, re.I):
                return "official_auto_oled_contract"
            if re.search(r"(차량용|완성차|OLED).{0,65}(첫 출하 완료|초도 출하 완료|first shipment completed)", title, re.I):
                return "official_auto_oled_shipment"
        has_new = re.search(r"신규\s*(고객|완성차)|새\s*고객|추가\s*(수주|확보|따내)|물량\s*더\s*커|앞좌석|뒷좌석|front and rear", body, re.I)
        headline_actual = re.search(r"(본격\s*양산|양산\s*(시작|개시)|양산.{0,10}물량|양산…|mass production started)", title, re.I)
        if has_new and headline_actual and not re.search(r"양산\s*(예정|전망|계획|기대)", title, re.I):
            return "reported_sop_expansion_20261113"
        return "prior_guidance"
    if group == COST:
        if src in OFFICIAL_COST and re.search(r"(revised|updated|new follow-up|수정|후속\s*조사|재추정)", title, re.I):
            try:
                pub = dt.datetime.fromisoformat(item.get("published") or "")
            except (TypeError, ValueError):
                pub = None
            if pub and pub.date() > dt.date(2026, 11, 12):
                return "official_revised_estimate"
        return "sep30_baseline"
    return ""

def install(base) -> None:
    previous = {name: getattr(base, name) for name in (
        "query_news", "topic_group", "score", "key", "category",
        "meaning", "risk", "verification", "tag_for", "select_diverse",
    )}

    def query(q: str):
        # Recover only current, dated items for a few days; no stale replay.
        if q in {MERGER_BACKFILL, DKT_BACKFILL}:
            if base.NOW.astimezone(base.KST).date() > dt.date(2026, 11, 16):
                return []
            if q == MERGER_BACKFILL:
                return [{
                    "title": "SpaceX Tesla merger talks progress, Bloomberg News reports",
                    "description": ("2026-11-12 Reuters citing Bloomberg: negotiations advancing; "
                                    "December announcement possible or early 2027 delay. "
                                    "Special committees disclosed in Oct 2026; no signed merger terms."),
                    "link": "https://www.reuters.com/legal/transactional/spacex-tesla-merger-talks-progress-bloomberg-news-reports-2026-11-12/",
                    "source": "Reuters", "published": "2026-11-12T20:22:00+00:00",
                    "nov13_verified_backfill": True,
                }]
            return [{
                "title": "디케이티, 북미 최대 전기차 OLED 본격 양산…물량 더 커졌다",
                "description": ("제공 메모 기준, 2026-11-13 더스탁 기사 원문 직접 열람 실패·독립 확인 전. "
                                "북미 전기차 앞좌석·뒷좌석 OLED 모듈 추가 수주, 신규 북미 완성차 고객 확보 보도. "
                                "고객 실명, 신규 계약금액, 실제 출하 수량 미공개. "
                                "2026~2028년 기존 3,300억원 수주잔고와 중복 합산 금지."),
                "link": "https://www.the-stock.kr/news/articleView.html?idxno=33795",
                "source": "사용자 제공 메모", "published": None,
                "nov13_user_memo_backfill": True,
            }]
        return previous["query_news"](q)

    def group(text: str):
        return identity(text) or previous["topic_group"](text)

    def score(item: dict):
        g = identity(_body(item))
        if not g:
            return previous["score"](item)
        s = stage(item, g)
        if s.startswith("reported_"):
            source = str(item.get("source") or "")
            title = str(item.get("title") or "")
            if g == MERGER and not (source in {"Reuters", "Bloomberg", "Investing.com", "연합뉴스", "로이터", "블룸버그"} or re.search(r"Reuters|Bloomberg|로이터|블룸버그", title, re.I)):
                return 0
            if g == DKT and not (source in {"더스탁", "THE STOCK", "The Stock", "사용자 제공 메모", "하나증권", "한국투자증권", "이데일리"} or item.get("nov13_user_memo_backfill")):
                return 0
        return (52 if s.startswith("official_") else 36) if s.startswith(("official_", "reported_")) else 0

    def key(item: dict):
        g = identity(_body(item))
        if not g:
            return previous["key"](item)
        return hashlib.sha256(f"robot-nov13|{g}|{stage(item, g)}".encode("utf-8")).hexdigest()

    def category(text: str, g: str):
        return CATEGORIES[g] if g in CATEGORIES else previous["category"](text, g)

    def meaning(cat: str):
        if cat == CATEGORIES[MERGER]:
            return "특별위원회 구성은 기존 확정 사실이고 12월 발표는 언론 전망입니다. 실제 합병계약·교환비율·주주승인을 별도로 확인해야 합니다."
        if cat == CATEGORIES[DKT]:
            return "북미 자동차 OLED용 모듈 양산·추가 고객 확보 보도입니다. 기존 2026~2028년 수주잔고와 신규 수주를 중복 합산하지 않고 실제 출하·매출을 확인합니다."
        if cat == CATEGORIES[COST]:
            return "2026-09-30 앤트로픽 연구의 0.3% 경제성·70% 비용 하락 조건은 기존 기준선입니다. 새 추정치만 변화로 알립니다."
        return previous["meaning"](cat)

    def risk(cat: str):
        if cat == CATEGORIES[MERGER]:
            return "합병 구조·자금조달·규제·중국 사업·미국 방산 계약·주식 희석이 불확실합니다. 두 회사의 공식 계약서와 감독기관 판단이 먼저입니다."
        if cat == CATEGORIES[DKT]:
            return "완성차 고객 실명·최종 공급계약 금액·차량 생산량·검수·매출 인식이 미확인입니다. 기존 3,300억원 차량용 OLED 수주잔고를 추가 3,300억원으로 오인하지 않습니다."
        if cat == CATEGORIES[COST]:
            return "일자리의 기술적 노출과 경제적 대체는 다릅니다. 로봇 가격·고장·인력 감독·안전·가동률·실제 작업당 비용을 추적합니다."
        return previous["risk"](cat)

    def verification(item: dict, g: str, text: str):
        if g == MERGER:
            if stage(item, g).startswith("official_"):
                return "회사 명의 공식 발표 주장 · 계약 문서와 공시 원문 추가 대조"
            return "블룸버그 취재·로이터 재보도 단계; 2026-10-20 양사 특별위원회는 공식 확인, 합병 계약 미확정"
        if g == DKT:
            if item.get("nov13_user_memo_backfill"):
                return "사용자 제공 2026-11-13 더스탁 메모 기준; 기사 직접 열람 실패·신규 양산/수주 독립 확인 전"
            if stage(item, g).startswith("official_"):
                return "디케이티 명의 공식 발표 주장 · 실제 매출·고객·수량 별도 확인"
            return "더스탁·증권사 보도 단계 · 고객 실명·계약·양산 물량의 회사 공시 독립 확인 전"
        if g == COST:
            return "앤트로픽 2026-09-30 원문 연구 · 새 수정 수치는 공식 후속 발표와 대조"
        return previous["verification"](item, g, text)

    def tag(g: str):
        return {MERGER: "SpaceX·테슬라 합병", DKT: "디케이티 차량용 OLED", COST: "로봇 경제성"}.get(g) or previous["tag_for"](g)

    def select(items: list[dict], seen: set[str], force: bool, limit: int):
        chosen = previous["select_diverse"](items, seen, force, limit)
        pool = items if force else [x for x in items if x.get("key") not in seen]
        for group_name in (MERGER, DKT, COST):
            hit = next((x for x in pool if x.get("group") == group_name and x.get("score", 0) >= 11), None)
            if hit and not any(x.get("key") == hit.get("key") for x in chosen):
                chosen = [hit, *chosen][:limit]
        return chosen

    base.query_news = query
    base.topic_group = group
    base.score = score
    base.key = key
    base.category = category
    base.meaning = meaning
    base.risk = risk
    base.verification = verification
    base.tag_for = tag
    base.select_diverse = select
    for q in QUERIES:
        if q not in base.QUERIES:
            base.QUERIES.append(q)
