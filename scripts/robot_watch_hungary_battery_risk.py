"""Verified Hungary battery compliance and SNE ex-China market alerts.

Extends the existing physical-AI / ESS-battery route; does not create a
workflow, bot, chat, state file or new delivery identity. Historical events
are baselines except one explicitly dated missed factory-shutdown backfill.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re

HUNGARY = "hungary_battery_environment"
SNE_MARKET = "exchina_ev_battery_market"
BACKFILL = "__verified_hungary_volta_hall101_shutdown_20261104__"
LAST_BACKFILL = dt.date(2026, 11, 18)
DELAYED_SHUTDOWN_KEY = "hungary|volta|2026-11-04|hall101-suspension"
OFFICIAL_GOVERNMENT = re.compile(
    r"kormányhivatal|kormanyhivatal|government office|kormány|kormany\.hu|"
    r"nemzeti jogszabály|government gazette|magyar közlöny|"
    r"országos élőkörnyezet|environmental authority", re.I,
)
OFFICIAL_COMPANY = re.compile(
    r"^(?:Volta Energy Solutions Hungary|Solus Advanced Materials|솔루스첨단소재|"
    r"SK On|SK온|Samsung SDI|삼성SDI)$", re.I,
)
OFFICIAL_SNE = re.compile(r"^(?:SNE\s*Research|SNE\s*리서치|SNE리서치)$", re.I)
TRUSTED_MEDIA = re.compile(r"^(?:Telex|Portfolio|Kemma|24\.hu|Reuters|연합뉴스|전자신문|한국경제)$", re.I)
HUNGARY_PLACE = re.compile(r"헝가리|Hungar|Magyar|Környe|Kornye|쾨르녜|Tatabánya|Iváncsa|Ivancsa|이반차|괴드|\bGöd\b|Debrecen|데브레첸", re.I)
BATTERY_ACTOR = re.compile(r"Volta Energy Solutions|볼타\s*에너지|솔루스첨단소재|Solus|SK\s*On|SK온|Samsung\s*SDI|삼성SDI", re.I)
SNE_ACTOR = re.compile(r"SNE\s*Research|SNE리서치|SNE\s*리서치", re.I)
SNE_EXCHINA = re.compile(r"비\s*중국|非\s*중국|중국\s*제외|excluding\s*China|excl\.?\s*China|ex-China|비중국", re.I)
SNE_USAGE = re.compile(r"전기차|EV\s*battery|battery\s*usage|배터리\s*(?:사용량|시장|점유율)|GWh", re.I)
SNE_PERIOD = re.compile(r"(20\d{2})\s*년?\s*(?:1\s*[~～\-–]\s*(1[012]|[1-9])\s*월|Jan(?:uary)?\s*[-–]\s*(Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?))", re.I)
HALL101 = re.compile(r"\b101(?:번|호|번\s*생산동|-es)?\b|hall\s*101|production\s*(?:hall|building)\s*101|gyártócsarnok(?:ában)?\s*101", re.I)

QUERIES = (
    BACKFILL,
    '(솔루스첨단소재 OR "Volta Energy Solutions Hungary" OR VESH) (헝가리 OR Környe OR 쾨르녜) (101 OR 201 OR 공장) (재가동 OR 중단 OR 유출 OR 누출 OR 오염 OR 허가 OR 환경 OR 생산)',
    'site:kormanyhivatalok.hu "Volta Energy Solutions" (101 OR Környe OR contamination OR production OR pollution OR suspended)',
    '(SK온 OR "SK On" OR "Samsung SDI" OR 삼성SDI) (Iváncsa OR 이반차 OR Göd OR 괴드 OR Hungary OR 헝가리) (환경 과태료 OR 환경 인허가 OR 생산 중단 OR pollution OR fine OR revocation)',
    '(280/2026 OR 412/2026 OR "Országos Élőkörnyezet") (battery OR akkumulátor OR 환경 OR appeal OR fines OR permit)',
    '("SNE Research" OR SNE리서치) (비중국 OR 중국 제외 OR ex-China OR excluding China) (배터리 사용량 OR battery usage OR market share OR 점유율) 2026 2027',
)

def _body(item: dict) -> str:
    return " ".join(str(item.get(field) or "") for field in ("title", "description", "source"))

def _company(text: str) -> str:
    if re.search(r"Volta Energy Solutions|볼타\s*에너지|솔루스첨단소재|Solus", text, re.I):
        return "volta"
    if re.search(r"SK\s*On|SK온", text, re.I):
        return "skon"
    if re.search(r"Samsung\s*SDI|삼성SDI", text, re.I):
        return "sdi"
    return "unspecified"

def _period(text: str) -> str:
    m = SNE_PERIOD.search(text)
    if not m:
        english = re.search(
            r"Jan(?:uary)?\s*[-–]\s*(Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(20\d{2})",
            text, re.I
        )
        if english:
            english_month = {"sep":"09","oct":"10","nov":"11","dec":"12"}[english.group(1).lower()[:3]]
            return f"{english.group(2)}-{english_month}"
        return ""
    year = m.group(1)
    month = m.group(2)
    if not month:
        month = {"sep":"09","oct":"10","nov":"11","dec":"12"}.get((m.group(3) or "").lower()[:3], "")
    return f"{year}-{int(month):02d}" if month else ""

def identity(text: str) -> str:
    if BATTERY_ACTOR.search(text) and HUNGARY_PLACE.search(text) and re.search(
        r"환경|오염|황산구리|구리\s*유출|규제|인허가|과태료|행정\s*처분|"
        r"fines?|pollut|contaminat|suspend|shutdown|resume|reopen|permit|"
        r"gyártócsarnok|környezetvédel|bírság", text, re.I
    ):
        return HUNGARY
    if SNE_ACTOR.search(text) and SNE_EXCHINA.search(text) and SNE_USAGE.search(text):
        return SNE_MARKET
    return ""

def _published(item: dict) -> dt.date | None:
    try:
        return dt.datetime.fromisoformat(str(item.get("published"))).date()
    except (TypeError, ValueError):
        return None

def stage(item: dict, group: str) -> str:
    if item.get("hungary_authority_backfill"):
        return "official_hall101_shutdown_20261104"
    title = str(item.get("title") or "")
    text = _body(item)
    source = str(item.get("source") or "")
    if group == SNE_MARKET:
        period = _period(text)
        if source and OFFICIAL_SNE.search(source) and period and period > "2026-09":
            return "official_monthly_usage_" + period
        return "known_2026_09_baseline"
    if group != HUNGARY:
        return ""
    government = bool(OFFICIAL_GOVERNMENT.search(source))
    company_official = bool(OFFICIAL_COMPANY.search(source))
    released = _published(item)
    if not (government or company_official) or released is None or released <= dt.date(2026, 11, 14):
        return "historic_or_unverified"
    # Only an official actual action in the headline is a new milestone.
    if re.search(r"재가동\s*(?:승인|허용|개시|시작)|reopen(?:ing)?\s*(?:approved|authori[sz]ed)|production\s*resumed|resumed\s*production|újraindítását\s*engedélyezték", title, re.I):
        return "official_production_resumed"
    if re.search(r"과태료\s*(?:부과\s*확정|부과|확정)|벌금\s*(?:부과|확정)|fine\s*(?:imposed|levied|ordered)|bírságot\s*szabott\s*ki", title, re.I) and not re.search(
        r"상한|최대|한도|우려|가능성|risk|cap|maximum|could|may", title, re.I
    ):
        return "official_new_fine"
    if re.search(r"(추가|신규|새로운|new|additional).{0,24}(가동\s*중단|생산\s*중단|공장\s*폐쇄|shutdown|suspension)|"
                 r"(가동\s*중단|생산\s*중단|shutdown|suspension).{0,24}(명령|ordered|추가|new)", title, re.I):
        return "official_new_shutdown"
    if re.search(r"인허가\s*(?:취소|철회)|permit\s*(?:revoked|cancelled)|환경\s*허가\s*취소", title, re.I):
        return "official_permit_revoked"
    return "historic_or_unverified"

def install(base) -> None:
    previous = {name: getattr(base, name) for name in (
        "query_news", "topic_group", "score", "key", "category",
        "meaning", "risk", "verification", "tag_for", "select_diverse",
    )}

    def query(q: str):
        if q == BACKFILL:
            if base.NOW.astimezone(base.KST).date() > LAST_BACKFILL:
                return []
            return [{
                "title": "솔루스첨단소재 헝가리 볼타 전지박 101번 생산동, 11월 4일 가동 중단 명령(기존 사건 지연 확인)",
                "description": (
                    "2026년 11월 6일 코마롬에스테르곰주 정부청의 공식 발표: "
                    "10월 30일 인근 수로 변색 신고, 10월 31일 조사, "
                    "11월 4일 Volta Energy Solutions Hungary의 101번 제조동 모든 전지박 공정 중단 명령. "
                    "원인 제거·수리 및 독립 전문가 검증 없이는 재가동 불가. "
                    "201번 생산동과 SK온·삼성SDI 전체 공장의 중단은 확인된 내용이 아님. "
                    "헝가리 280/2026 정부령의 과태료 상한은 50억포린트(2026-11-14 기준 약 202억원)이며, "
                    "해당 업체에 실제 50억포린트가 부과됐다는 공식 처분은 미확인. "
                    "2027년 1월 1일 새 전국 환경감독기관 설립, 7월 1일 일부 지역 조직 이관 예정은 기존 공포된 일정."
                ),
                "source": "Komárom-Esztergom County Government Office",
                "link": "https://www.kormanyhivatalok.hu/kormanyhivatalok/komarom-esztergom/megye/hirek/hir/szennyezes-miatt-felfuggesztette-egy",
                "published": None,
                "hungary_authority_backfill": True,
            }]
        return previous["query_news"](q)

    def group(text: str):
        return identity(text) or previous["topic_group"](text)

    def score(item: dict):
        g = identity(_body(item))
        if not g and not item.get("hungary_authority_backfill"):
            return previous["score"](item)
        s = stage(item, g)
        if item.get("hungary_authority_backfill"):
            return 48
        if g == SNE_MARKET:
            return 37 if s.startswith("official_monthly_usage_") else 0
        if g == HUNGARY and s.startswith("official_"):
            return 43
        return 0

    def key(item: dict):
        if item.get("hungary_authority_backfill"):
            return hashlib.sha256(DELAYED_SHUTDOWN_KEY.encode()).hexdigest()
        g = identity(_body(item))
        if not g:
            return previous["key"](item)
        s = stage(item, g)
        if g == SNE_MARKET:
            return hashlib.sha256(f"sne|exchina-ev-battery|{_period(_body(item)) or 'baseline'}".encode()).hexdigest()
        company = _company(_body(item))
        published = _published(item)
        month = published.strftime("%Y-%m") if published else "no-date"
        case = re.search(r"\b(?:KE|FE|PE)/\d{3,5}/\d{3,6}[-/]\d{2,4}/20\d{2}\b", _body(item), re.I)
        receipt = case.group(0) if case else month
        return hashlib.sha256(f"hungary|battery|{company}|{s}|{receipt}".encode()).hexdigest()

    def category(text: str, g: str):
        if g == HUNGARY:
            return "헝가리 배터리·전지박 · 실제 환경 제재·공장 가동"
        if g == SNE_MARKET:
            return "중국 제외 전기차 배터리 · 월별 사용량·기업 점유율"
        return previous["category"](text, g)

    def meaning(cat: str):
        if cat == "헝가리 배터리·전지박 · 실제 환경 제재·공장 가동":
            return "정부의 101번 생산동 실제 중단 명령과 50억포린트 법정 과태료 상한은 별개입니다. 재가동 승인·공급 차질·보상·현금흐름을 확인합니다."
        if cat == "중국 제외 전기차 배터리 · 월별 사용량·기업 점유율":
            return "중국 제외 전기차용 실제 배터리 사용량·기업별 점유율을 비교합니다. ESS 출하와 혼동하지 않으며 전월 누적 대비 변화를 확인합니다."
        return previous["meaning"](cat)

    def risk(cat: str):
        if cat == "헝가리 배터리·전지박 · 실제 환경 제재·공장 가동":
            return "101번 동 재가동에는 누출 원인 제거·보수·외부 전문가 검증이 필요합니다. 201번 동은 중단 대상이 아니며, 확정 과태료와 고객 생산 차질도 별도 확인해야 합니다."
        if cat == "중국 제외 전기차 배터리 · 월별 사용량·기업 점유율":
            return "중국계 LFP 저가 경쟁, 유럽 현지 생산·승인, 북미 수요 둔화와 ESS 전환의 물량·가동률·마진 차이를 확인합니다."
        return previous["risk"](cat)

    def verification(item: dict, g: str, text: str):
        if item.get("hungary_authority_backfill"):
            return "헝가리 주정부청 2026-11-06 공식 발표의 기존 11월 4일 중단 명령 · 지연 누락 복구 · 과태료 실제 부과는 미확인"
        if g == HUNGARY:
            return ("정부·회사 직접 발표의 신규 조치(제목·발표일 기반) · 처분 원문·적용 사업장·"
                    "재가동 조건·실제 과태료 확인 필요")
        if g == SNE_MARKET:
            return "SNE리서치 해당 월 원문 · 배터리 사용량과 ESS 출하량, 실적·출하, 확정·전망 구분"
        return previous["verification"](item, g, text)

    def tag(g: str):
        return {HUNGARY: "헝가리 배터리 환경·가동", SNE_MARKET: "비중국 배터리 점유율"}.get(g) or previous["tag_for"](g)

    def select(items: list[dict], seen: set[str], force: bool, limit: int):
        chosen = previous["select_diverse"](items, seen, force, limit)
        eligible = items if force else [x for x in items if x.get("key") not in seen]
        for group_name in (HUNGARY, SNE_MARKET):
            hit = next((x for x in eligible if x.get("group") == group_name and x.get("score", 0) >= 11), None)
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
