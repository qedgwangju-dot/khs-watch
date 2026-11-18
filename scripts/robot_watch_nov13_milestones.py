"""Source-graded Nov 13 robotics milestones in the existing alert route.

Does not change Telegram destinations, cadence, historical dedup keys or
contract standards. Short-lived backfills are not new recurring sources.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import unicodedata
import urllib.parse

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


def _fact_text(value: str) -> str:
    """Normalise typography, not the meaning or date of a research finding."""
    value = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\s+", " ", value).strip(" .;:")


def _cost_document_url(item: dict) -> str:
    # A publisher's RSS source_url usually identifies its homepage. It is
    # deliberately not evidence of an individual report or a report version.
    if str(item.get("source") or "").strip() not in OFFICIAL_COST:
        return ""
    for field in ("canonical_url", "original_url", "link"):
        try:
            parts = urllib.parse.urlsplit(str(item.get(field) or ""))
            port = parts.port
        except ValueError:
            continue
        host = (parts.hostname or "").lower().removeprefix("www.")
        path = parts.path.rstrip("/")
        if (parts.scheme != "https" or port not in {None, 443} or parts.username or parts.password
                or not (host == "anthropic.com" or host.endswith(".anthropic.com"))
                or len([p for p in path.split("/") if p]) < 2
                or path.split("/")[1] not in {"research", "news", "engineering"}
                or re.search(r"(?:rss|feed|index)(?:\.xml|\.html)?$", path, re.I)):
            continue
        query = urllib.parse.urlencode(sorted(
            (k, v) for k, v in urllib.parse.parse_qsl(parts.query)
            if not k.lower().startswith("utm_")
            and k.lower() not in {"gclid", "fbclid", "ref", "source"}
        ))
        return urllib.parse.urlunsplit(("https", host, path, query, ""))
    return ""


def _labelled_fact(text: str, names: str) -> str:
    match = re.search(rf"(?:{names})\s*[:=]\s*([^;|\n]+)", text, re.I)
    return _fact_text(match.group(1)) if match else ""


def cost_revision(item: dict) -> tuple[dict, list[str]]:
    """Require an identifiable official document and attributable new values.

    This is an RSS discovery gate, not full-text verification. Ambiguous prose,
    unlabeled old/new percentages and generic 'new figures' titles stay pending.
    Publication time is never a revision identifier: a reprint can change it.
    """
    text = unicodedata.normalize("NFKC", "\n".join(
        str(item.get(k) or "") for k in ("title", "description")
    ))
    facts = {"document": _cost_document_url(item)}
    facts["scope"] = _labelled_fact(
        text, r"analysis\s+scope|study\s+population|sample\s+scope|분석\s*대상|조사\s*대상"
    )
    if not facts["scope"]:
        scope = re.search(
            r"(?:U\.?S\.?|United States|global|worldwide|미국|전\s*세계|한국|유럽)"
            r"[^;|.\n]{0,45}(?:occupations?|jobs?|tasks?|workers?|직업|일자리|업무|노동자)",
            text, re.I,
        )
        facts["scope"] = _fact_text(scope.group()) if scope else ""
    facts["period"] = _labelled_fact(
        text, r"analysis\s+period|study\s+period|reference\s+period|data\s+period|분석\s*기간|기준\s*기간|자료\s*기간"
    )
    facts["version"] = _labelled_fact(text, r"report\s+version|revision|version|보고서\s*버전|개정판|버전")
    report_date = re.search(
        r"(?:report\s+date|revised\s+on|updated\s+on|발표일|개정일|수정일|보고서\s*날짜)"
        r"\s*[:=]?\s*(20\d{2})[-./](\d{1,2})[-./](\d{1,2})", text, re.I,
    )
    facts["report_date"] = ""
    if report_date:
        try:
            facts["report_date"] = dt.date(*(int(v) for v in report_date.groups())).isoformat()
        except ValueError:
            pass
    metric_patterns = {
        "경제적 대체 비중": r"cost[-\s]*competitive\s*(?:share|exposure)|economic(?:ally)?\s*(?:competitive\s*)?(?:share|exposure)|경제(?:적)?\s*대체\s*비중|경제성\s*확보\s*비중",
        "기술적 노출 비중": r"technical\s*exposure|technically\s*exposed\s*share|기술적\s*노출\s*비중",
        "비용 하락 조건": r"cost\s*(?:reduction|decline|drop)\s*(?:threshold|required)|비용\s*하락\s*조건|필요\s*비용\s*감소율",
    }
    metrics = {}
    ambiguous = False
    for name, pattern in metric_patterns.items():
        values = {
            format(float(m.group(1)), ".12g") + "%"
            for m in re.finditer(
                rf"(?:{pattern})\s*(?:is\s*|now\s*|[:=]\s*)?(\d+(?:\.\d+)?)\s*%", text, re.I,
            )
        }
        if len(values) > 1:
            ambiguous = True
        elif values:
            metrics[name] = next(iter(values))
    facts["metrics"] = metrics
    missing = []
    for field, label in (("document", "개별 공식 문서 URL"), ("scope", "분석 대상"),
                         ("period", "자료 기준기간"), ("metrics", "라벨이 있는 수정 수치")):
        if not facts[field]:
            missing.append(label)
    if facts["period"] and not re.search(r"(?<!\d)20\d{2}(?!\d)", facts["period"]):
        missing.append("연도를 포함한 절대 자료 기준기간")
    if any(not 0 <= float(value.rstrip("%")) <= 100 for value in metrics.values()):
        missing.append("백분율 지표의 유효 범위")
    if ambiguous:
        missing.append("같은 지표의 과거값·수정값 구분")
    if facts["report_date"] and facts["report_date"] <= "2026-11-12":
        missing.append("기존 기준선 이후의 실제 개정일")
    return facts, missing


# Qualify the matched milestone itself. A later closing target must not erase
# an already signed contract, and an actual termination is a material event.
_UNCONFIRMED_PREFIX = re.compile(
    r"\b(?:no|not|never|without|pending|awaiting|awaits|cannot|won['’]t|can['’]t|"
    r"(?:is|are|was|were|has|have|had|will|would|could|can|should)n['’]t|"
    r"(?:will|would|could|may|might|should|must)|"
    r"(?:expected|planned|scheduled|intended|targeted|set)\s+to|"
    r"(?:plans?|intends?|aims?|hopes?|expects?)\s+to)"
    r"(?:\s+(?:yet|be|been|being|have|already|actually|officially|finally))*\s*$|"
    r"(?:미|불|안\s*|못\s*|아직\s*|미처\s*)$",
    re.I,
)
_UNCONFIRMED_SUFFIX = re.compile(
    r"^\s*(?:[,:'’\"“”‘’]\s*)*(?:"
    r"(?:is\s+|are\s+|was\s+|were\s+|has\s+been\s+|have\s+been\s+)?"
    r"(?:not\b|never\b|pending\b|awaited\b|required\b|unconfirmed\b|denied\b|"
    r"planned\b|scheduled\b|expected\b|targeted\b|anticipated\b|"
    r"(?:claim|report)s?\s+(?:(?:is|are|was|were)\s+)?denied\b)|"
    r"(?:은|는|이|가|을|를)?\s*(?:"
    r"(?:하|되|받)(?:지\s*(?:않|못)|지는\s*(?:않|못))|"
    r"(?:한|된)\s*바\s*없|하지\s*않|되지\s*않|"
    r"아니|없|아직|미완료|미체결|미승인|미확인|"
    r"예정|계획|목표|전망|검토|추진|대기|필요|조건부|가능성|불확실|"
    r"부인|불발|연기|지연|보류|결렬|설\s*부인|"
    r"하기로|되기로|할\s|될\s|할$|될$))",
    re.I,
)


def _confirmed_headline(title: str, pattern: str) -> bool:
    """Keep existing positive matches, excluding attached denial/future claims."""
    for match in re.finditer(pattern, title, re.I):
        action = "action" if match.groupdict().get("action") else "standalone"
        start, end = match.span(action)
        before = title[:start].rstrip(" \t\"'“”‘’")
        after = title[end:]
        if _UNCONFIRMED_PREFIX.search(before) or _UNCONFIRMED_SUFFIX.search(after):
            continue
        return True
    return False


def stage(item: dict, group: str) -> str:
    title = str(item.get("title") or "")
    body = _body(item)
    src = str(item.get("source") or "").strip()
    if group == MERGER:
        if src in OFFICIAL_MERGER:
            if _confirmed_headline(title, r"(합병|기업결합|merger|combination).{0,65}(?P<action>완료|종결|closing completed|closed)"):
                return "official_close"
            if _confirmed_headline(title, r"(합병|기업결합|merger|combination).{0,80}(?P<action>주주총회 승인|주주 승인|shareholder approval|shareholder vote approved)|(?P<standalone>shareholders? approved)"):
                return "official_approval"
            if _confirmed_headline(title, r"(합병|기업결합|merger|combination).{0,80}(?P<action>철회|중단|무산|terminated|abandoned)"):
                return "official_termination"
            if _confirmed_headline(title, r"(합병|기업결합|merger|combination).{0,80}(?P<action>본계약 체결|최종 계약 체결|definitive agreement signed|binding agreement signed)"):
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
            if _confirmed_headline(title, r"(차량용|완성차|OLED).{0,65}(?P<action>정식 공급계약 체결|구매계약 체결|binding supply contract signed)"):
                return "official_auto_oled_contract"
            if _confirmed_headline(title, r"(차량용|완성차|OLED).{0,65}(?P<action>첫 출하 완료|초도 출하 완료|first shipment completed)"):
                return "official_auto_oled_shipment"
        has_new = re.search(r"신규\s*(고객|완성차)|새\s*고객|추가\s*(수주|확보|따내)|물량\s*더\s*커|앞좌석|뒷좌석|front and rear", body, re.I)
        headline_actual = re.search(r"(본격\s*양산|양산\s*(시작|개시)|양산.{0,10}물량|양산…|mass production started)", title, re.I)
        if has_new and headline_actual and not re.search(r"양산\s*(예정|전망|계획|기대)", title, re.I):
            return "reported_sop_expansion_20261113"
        return "prior_guidance"
    if group == COST:
        if src in OFFICIAL_COST and _confirmed_headline(title, r"(?P<action>revised|updated|new follow-up|수정|후속\s*조사|재추정)"):
            try:
                pub = dt.datetime.fromisoformat(item.get("published") or "")
            except (TypeError, ValueError):
                pub = None
            if pub and pub.date() > dt.date(2026, 11, 12):
                _, missing = cost_revision(item)
                return "revision_verification_pending" if missing else "official_revised_estimate"
            return "revision_verification_pending"
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
        s = stage(item, g)
        if g == COST and s == "official_revised_estimate":
            facts, _ = cost_revision(item)
            fingerprint = json.dumps(facts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            return hashlib.sha256(f"robot-nov13|{g}|{s}|{fingerprint}".encode("utf-8")).hexdigest()
        # All historical baseline/merger/DKT keys are deliberately unchanged.
        return hashlib.sha256(f"robot-nov13|{g}|{s}".encode("utf-8")).hexdigest()

    def category(text: str, g: str):
        return CATEGORIES[g] if g in CATEGORIES else previous["category"](text, g)

    def meaning(cat: str):
        if cat == CATEGORIES[MERGER]:
            return "특별위원회 구성은 기존 확정 사실이고 12월 발표는 언론 전망입니다. 실제 합병계약·교환비율·주주승인을 별도로 확인해야 합니다."
        if cat == CATEGORIES[DKT]:
            return "북미 자동차 OLED용 모듈 양산·추가 고객 확보 보도입니다. 기존 2026~2028년 수주잔고와 신규 수주를 중복 합산하지 않고 실제 출하·매출을 확인합니다."
        if cat == CATEGORIES[COST]:
            return "공식 후속 문서의 수정 수치·분석 대상·자료 기준기간을 구분합니다. 과거 연구 수치를 이번 개정의 현재값으로 재사용하지 않으며 경제적 대체와 기술적 노출을 별도로 확인합니다."
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
            s = stage(item, g)
            if s == "official_revised_estimate":
                facts, _ = cost_revision(item)
                metrics = ", ".join(f"{label} {value}" for label, value in sorted(facts["metrics"].items()))
                revision = ", ".join(filter(None, (
                    "문서 개정일 " + facts["report_date"] if facts["report_date"] else "",
                    "문서 버전 " + facts["version"] if facts["version"] else "",
                ))) or "문서 개정일·버전 미표기"
                return (f"앤트로픽 공식 도메인 개별 문서의 제목·요약 검색색인 · 원문 추가 검증; "
                        f"수정 수치 {metrics}; 분석 대상 {facts['scope']}; 자료 기준기간 {facts['period']}; {revision}")
            if s == "revision_verification_pending":
                _, missing = cost_revision(item)
                return "공식 후속 제목 검증 대기 · " + ", ".join(missing or ["실제 개정 시점"]) + " 미식별; 새 수치 확정 전"
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

