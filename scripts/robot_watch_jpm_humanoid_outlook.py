"""Source-graded J.P. Morgan 2026-11-12 humanoid outlook within the existing ROBOTIS watch.

Reuters-reported forecast is not a ROBOTIS customer order, supply agreement
or validated OEM qualification. Reprints of the original report share one key.
No new workflow, Telegram destination, recurring state file or forced send.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re

GROUP = "jpm_humanoid_component_outlook"
BACKFILL = "__reuters_jpm_robotis_humanoid_20261112_once__"
BACKFILL_END = dt.date(2026, 11, 20)
EVENT_ID = "jpmorgan|2026-11-12|us-humanoid-forecast|robotis-among-component-favorites"
EVENT_KEY = hashlib.sha256(EVENT_ID.encode("utf-8")).hexdigest()
REUTERS_URL = "https://www.reuters.com/business/us-humanoid-robot-production-could-hit-400000-by-2030-deployment-ramps-jp-morgan-2026-11-12/"
BANK = re.compile(r"J\.?\s*P\.?\s*Morgan|JPMorgan|JP모건|제이피모건", re.I)
ROBOTIS = re.compile(r"로보티즈|ROBOTIS", re.I)
HUMANOID = re.compile(r"휴머노이드|humanoid", re.I)
REVISED = re.compile(r"전망.{0,22}(상향|하향|수정)|(?:상향|하향|수정).{0,22}전망|revis(?:es|ed|ion)|raise[sd]? forecast|cut[s]? forecast|lifts? forecast|lowers? forecast", re.I)
PRIMARY = re.compile(r"^(?:Reuters|로이터|J\.?\s*P\.?\s*Morgan|JPMorgan)$", re.I)
QUERIES = (
    BACKFILL,
    '("J.P. Morgan" OR JPMorgan OR JP모건) (ROBOTIS OR 로보티즈) (humanoid OR 휴머노이드) (2030 OR 2035 OR actuator OR 액추에이터)',
    '(Timken OR "Leader Drive" OR Orbbec OR Cognex) ("J.P. Morgan" OR JP모건) (ROBOTIS OR 로보티즈) (humanoid OR 휴머노이드)',
)


def _body(item: dict) -> str:
    return " ".join(str(item.get(k) or "") for k in ("title", "description", "source"))


def identity(text: str) -> str:
    return GROUP if BANK.search(text) and ROBOTIS.search(text) and HUMANOID.search(text) else ""


def _date(item: dict) -> dt.date | None:
    try:
        return dt.datetime.fromisoformat(str(item.get("published"))).date()
    except (TypeError, ValueError):
        return None


def stage(item: dict, group: str) -> str:
    if item.get("jpm_robotis_backfill"):
        return "reuters_report_20261112"
    if group != GROUP:
        return ""
    released = _date(item)
    source = str(item.get("source") or "").strip()
    headline = str(item.get("title") or "")
    if (released and released > dt.date(2026, 11, 15)
            and PRIMARY.fullmatch(source) and REVISED.search(headline)
            and re.search(r"2030|2035", _body(item))):
        return "new_forecast_revision"
    return "known_research_or_reprint"


def install(base) -> None:
    prior = {name: getattr(base, name) for name in (
        "query_news", "topic_group", "score", "key", "category",
        "meaning", "risk", "verification", "tag_for", "select_diverse",
    )}

    def query(q: str):
        if q == BACKFILL:
            if base.NOW.astimezone(base.KST).date() > BACKFILL_END:
                return []
            return [{
                "title": "JP모건 11월 12일 미국 휴머노이드 전망: 로보티즈 5개 유망 부품사 포함(기존 보고서 지연 확인)",
                "description": (
                    "로이터 2026-11-12 보도 기준. 미국 연간 생산량 2030년 30만~40만대, "
                    "2035년 약 150만대 전망. 2035년 액추에이터·모터·비전 핵심 부품시장 "
                    "300억달러(11월 13일 기준 약 40조1,010억원) 예상. "
                    "로보티즈, 팀켄, 코그넥스, 리더드라이브, 오르벡을 유망 부품기업으로 제시. "
                    "다교대 운용 고객 연간 10만달러(약 1억3,367만원) 절감 추산. "
                    "손·액추에이터·AI·생산능력이 핵심 병목. "
                    "이는 증권사 산업 전망이며 로보티즈의 신규 OEM 수주·납품·양산 확인이 아님. "
                    "JP모건 보고서 전문은 직접 확보하지 못했으며 로이터 직접 취재 보도 기준."
                ),
                "source": "Reuters",
                "link": REUTERS_URL,
                "published": None,
                "jpm_robotis_backfill": True,
            }]
        return prior["query_news"](q)

    def group(text: str):
        return identity(text) or prior["topic_group"](text)

    def score(item: dict):
        g = identity(_body(item))
        if not g and not item.get("jpm_robotis_backfill"):
            return prior["score"](item)
        s = stage(item, g)
        if s == "reuters_report_20261112":
            return 48
        if s == "new_forecast_revision":
            return 37
        return 0

    def key(item: dict):
        g = identity(_body(item))
        if not g and not item.get("jpm_robotis_backfill"):
            return prior["key"](item)
        s = stage(item, g)
        if s == "new_forecast_revision":
            date = _date(item)
            title = re.sub(r"\s+", " ", str(item.get("title") or "")).strip().casefold()
            return hashlib.sha256(f"jpm|humanoid|revision|{date}|{title}".encode()).hexdigest()
        return EVENT_KEY

    category_label = "JP모건 · 미국 휴머노이드 생산 전망·로보티즈 부품사 평가"
    def category(text: str, group_name: str):
        return category_label if group_name == GROUP else prior["category"](text, group_name)

    def meaning(cat: str):
        if cat == category_label:
            return ("2030년 미국 생산 30만~40만대, 2035년 약 150만대는 증권사 전망입니다. "
                    "로보티즈가 유망 액추에이터 공급사로 거론됐지만 실제 OEM 고객·공급계약·출하·매출은 별도 확인해야 합니다.")
        return prior["meaning"](cat)

    def risk(cat: str):
        if cat == category_label:
            return ("부품 선정은 실제 납품사 선정이 아닙니다. 로봇 손·제어 AI·생산능력·가격 경쟁력과 "
                    "미국 관세 변수 때문에 예상 대수가 계약·양산·매출로 실현되지 않을 수 있습니다.")
        return prior["risk"](cat)

    def verify(item: dict, group_name: str, text: str):
        if group_name == GROUP:
            if item.get("jpm_robotis_backfill"):
                return ("2026-11-12 로이터 보도 재확인·알림 누락 복구; "
                        "JP모건 보고서 전문 미열람; 실제 공급계약·고객사 실명·매출 확정 아님")
            return ("로이터 또는 JP모건 직접자료의 새로운 전망 수정 보도; "
                    "전망과 실제 고객 수주·양산 계약은 반드시 분리")
        return prior["verification"](item, group_name, text)

    def tag(group_name: str):
        return "JP모건·로보티즈 전망" if group_name == GROUP else prior["tag_for"](group_name)

    def select(items: list[dict], seen: set[str], force: bool, limit: int):
        chosen = prior["select_diverse"](items, seen, force, limit)
        eligible = items if force else [x for x in items if x.get("key") not in seen]
        hit = next((x for x in eligible if x.get("group") == GROUP and x.get("score", 0) >= 11), None)
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
    base.verification = verify
    base.tag_for = tag
    base.select_diverse = select
    for q in QUERIES:
        if q not in base.QUERIES:
            base.QUERIES.append(q)
