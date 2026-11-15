#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import email.utils
import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "korea_ai_semiconductor_policy_watch_state.json"
OUT = ROOT / "out"
OUT.mkdir(parents=True, exist_ok=True)
ALERT = OUT / "korea_ai_semiconductor_policy_watch_alert.html"
PENDING = OUT / "korea_ai_semiconductor_policy_watch_pending_state.json"
STATUS = OUT / "korea_ai_semiconductor_policy_watch_status.md"

KST = ZoneInfo("Asia/Seoul")
UA = "Mozilla/5.0 (compatible; KHSAISemiconductorPolicyWatch/1.0; +https://github.com/qedgwangju-dot/khs-watch)"

AIDC_RND_VERSION = 1
# The 2026-11-12 conference plan is a baseline, not a new government award.
AIDC_PRIOR_PLAN = "aidc-network|integrated|2027|plan"
COMPANIES = (
    "리벨리온", "rebellions", "퓨리오사ai", "퓨리오사 ai", "furiosa", "딥엑스", "deepx",
    "모빌린트", "mobilint", "하이퍼엑셀", "hyperaccel",
)
CORE_TERMS = (
    "국산 ai 반도체", "국산 ai반도체", "국산 npu", "ai 반도체", "ai반도체", "npu",
) + COMPANIES

ACTION_TERMS = (
    "보조금", "지원금", "세제", "세액공제", "조달", "공공구매", "시범구매", "구매",
    "초기수요", "초기 수요", "지원사업", "사업공고", "공모", "선정", "협약", "예산",
    "출자", "투자", "정책금융", "수출금융", "무역보험", "보증", "해외실증", "해외 실증",
    "해외진출", "해외 진출", "수출", "공급계약", "공급 계약", "수주", "계약", "납품",
    "실증", "poc", "데이터센터", "국부펀드", "사우디", "아랍에미리트", "uae", "중동",
    "정상외교", "경제사절단", "정부지원", "정부 지원", "혁신제품", "수의계약",
)
NOISE_TERMS = (
    "특징주", "관련주", "상한가", "급등", "주가", "테마주", "목표주가", "증권사",
    "단순 부각", "수혜주",
)

OFFICIAL_MARKERS = (
    "과학기술정보통신부", "산업통상자원부", "금융위원회", "조달청", "기획재정부",
    "정보통신산업진흥원", "nipa", "한국수출입은행", "해외경제연구소", "수출입은행",
    "한국무역보험공사", "무역보험공사", "k-sure", "kotra", "대한무역투자진흥공사",
    "정책브리핑", "대통령실", "산업은행", "한국산업은행", "국회도서관", "국가전략포털", "정보통신기획평가원", "iitp", "국회예산정책처", "nabo", "범부처통합연구지원시스템", "iris",
)
TRUSTED_NEWS_MARKERS = (
    "연합뉴스", "뉴시스", "전자신문", "지디넷코리아", "zdnet", "디지털데일리",
    "디일렉", "thelec", "서울경제", "한국경제", "매일경제", "머니투데이", "이데일리",
    "조선비즈", "아시아경제", "파이낸셜뉴스", "뉴스핌", "블로터", "아이뉴스24",
    "이투데이", "아주경제", "비즈워치", "서울경제tv", "더벨", "뉴스1", "news1",
)

QUERY_SPECS = [
    ("정책·초기수요", '"국산 AI 반도체" (보조금 OR 세액공제 OR 세제 OR 조달 OR 공공구매 OR 시범구매 OR 초기수요 OR 지원사업) when:60d'),
    ("정책·초기수요", '"국산 NPU" (조달 OR 구매 OR 보조금 OR 세액공제 OR 지원사업 OR 공공기관 OR 혁신제품) when:60d'),
    ("해외지원", '(리벨리온 OR 퓨리오사AI OR 딥엑스 OR 모빌린트 OR 하이퍼엑셀) (수출금융 OR 무역보험 OR 해외실증 OR 해외진출 OR 수출계약 OR 공급계약) when:60d'),
    ("중동", '(리벨리온 OR 퓨리오사AI OR 딥엑스 OR 모빌린트 OR 하이퍼엑셀) (사우디 OR UAE OR 아랍에미리트 OR 중동) (계약 OR 실증 OR 데이터센터 OR 국부펀드 OR 정부) when:60d'),
    ("공식-과기정통부", 'site:msit.go.kr ("AI 반도체" OR "NPU") (지원 OR 조달 OR 실증 OR 해외) when:90d'),
    ("공식-정책브리핑", 'site:korea.kr ("AI 반도체" OR "NPU") (지원 OR 조달 OR 실증 OR 해외) when:90d'),
    ("공식-금융위", 'site:fsc.go.kr ("AI 반도체" OR 리벨리온 OR 퓨리오사AI) (투자 OR 지원 OR 펀드 OR 금융) when:120d'),
    ("공식-조달청", 'site:pps.go.kr ("AI 반도체" OR "NPU") (혁신제품 OR 시범구매 OR 조달 OR 구매) when:120d'),
    ("공식-NIPA", 'site:nipa.kr ("AI 반도체" OR "NPU") (해외실증 OR 지원사업 OR 공모 OR 선정) when:120d'),
    ("공식-수은", '(site:koreaexim.go.kr OR site:keri.koreaexim.go.kr) ("AI 반도체" OR "NPU") when:180d'),
    ("공식-국가전략포털", 'site:nsp.nanet.go.kr ("AI반도체" OR "AI 반도체" OR "NPU") (한국수출입은행 OR 정부 OR 정책 OR 지원) when:180d'),
    ("공식-KOTRA", 'site:kotra.or.kr ("AI 반도체" OR "NPU") (중동 OR 사우디 OR UAE OR 해외진출) when:180d'),
    ("공식-무보", 'site:ksure.or.kr ("AI 반도체" OR "NPU") (수출 OR 보증 OR 금융 OR 중동) when:180d'),
    ("AIDC-국산광통신", '("AIDC" OR "AI 데이터센터") (국산화 OR 광통신 OR 광회선스위칭 OR 광스위칭 OR 광반도체 OR 도파관 OR "AI 기지국") (예산 OR 연구개발 OR 과제 OR 실증 OR 선정 OR 공고) when:60d'),
    ("AIDC-광부품", '(CPO OR NPO OR OCS OR MEMS OR "L-COS" OR 광트랜시버 OR 인화인듐) (IITP OR 과기정통부 OR 국산화 OR "공공 파운드리") (연구개발 OR 사업 OR 과제 OR 예산 OR 선정 OR 공고 OR 양산) when:90d'),
    ("AIDC-공식-과기", 'site:msit.go.kr (AIDC OR "AI데이터센터") (광통신 OR 광반도체 OR 광회선 OR 네트워크 OR 국산 OR 과제) when:120d'),
    ("AIDC-공식-IITP", 'site:iitp.kr (AIDC OR 광집적회로 OR 광반도체 OR 광회선스위칭) (2027 OR 공고 OR 과제 OR 연구개발) when:120d'),
    ("AIDC-공식-조달", 'site:pps.go.kr (AIDC OR 광회선스위칭 OR 광반도체 OR 광트랜시버) (입찰 OR 낙찰 OR 공고 OR 조달) when:180d'),
    ("AIDC-공식-NABO", 'site:nabo.go.kr (AIDC OR "K-AIDC") ("소부장" OR 광통신 OR 예산안) 2027 when:120d'),
    ("AIDC-공식-IRIS", 'site:iris.go.kr (AIDC OR 광반도체 OR 광회선스위칭 OR 광트랜시버 OR 광집적회로) (공모 OR 신규과제 OR 공고 OR 선정 OR R&D) when:180d'),
]


def now_kst() -> dt.datetime:
    return dt.datetime.now(KST)


def norm(value: str | None) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", " ", value or ""))
    return re.sub(r"\s+", " ", value).strip()


def esc(value: str | None) -> str:
    return html.escape(str(value or ""), quote=True)


def fetch_text(url: str, timeout: int = 30) -> tuple[str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
        final_url = resp.geturl()
        charset = resp.headers.get_content_charset() or "utf-8"
    return data.decode(charset, errors="replace"), final_url


def parse_pubdate(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(KST)
    except Exception:
        return None


def normalize_title(value: str) -> str:
    text = norm(value).lower()
    text = re.sub(r"\s+-\s+[^-]{2,60}$", "", text)
    text = re.sub(r"[^0-9a-z가-힣]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def canonical_url(value: str) -> str:
    value = norm(value)
    try:
        p = urllib.parse.urlsplit(value)
        query = "" if p.netloc.lower() == "news.google.com" else p.query
        return urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), query, ""))
    except Exception:
        return value


def resolve_original_url(value: str) -> str:
    if "news.google.com/" not in value:
        return value
    try:
        _, final = fetch_text(value, timeout=12)
        if final and "news.google.com/" not in final:
            return final
    except Exception:
        pass
    return value


def source_quality(source: str, lane: str, source_url: str = "") -> str:
    # A search on an official domain is NOT evidence that the publisher is official.
    name = norm(source).lower()
    host = (urllib.parse.urlsplit(source_url).hostname or "").lower()
    primary_hosts = ("msit.go.kr", "iitp.kr", "korea.kr", "nabo.go.kr", "iris.go.kr",
                     "nipa.kr", "pps.go.kr", "nrf.re.kr", "kotra.or.kr", "ksure.or.kr")
    if any(host == h or host.endswith("." + h) for h in primary_hosts) or any(x.lower() in name for x in OFFICIAL_MARKERS):
        return "공식"
    if any(x.lower() in name for x in TRUSTED_NEWS_MARKERS):
        return "신뢰보도"
    return "기타보도"


def aidc_milestone(title: str, summary: str = "") -> tuple[str, int, str, str] | None:
    """AIDC optical R&D plan, budget, RFP, award and production are separate."""
    head = norm(title)
    text = f"{head} {norm(summary)}"
    if not re.search(r"AIDC|AI\s*데이터센터|인공지능\s*데이터센터|광회선\s*스위칭|"
                     r"광스위칭|\bOCS\b|\bCPO\b|\bNPO\b|\bInP\b|인화인듐|광반도체|"
                     r"광트랜시버|도파관|AI\s*기지국", head, re.I):
        return None
    if not re.search(r"네트워크|광통신|광회선|광스위칭|광반도체|광트랜시버|"
                     r"광원|\bCPO\b|\bNPO\b|\bOCS\b|인화인듐|\bInP\b|도파관|AI\s*기지국", text, re.I):
        return None
    # Vendor announcements about domestic CPO alone are not government R&D events.
    if not re.search(r"정부|과기정통부|과학기술정보통신부|정보통신기획평가원|"
                     r"\bIITP\b|국회|공공\s*파운드리|국책|국가연구개발|정부\s*R&D", text, re.I):
        return None
    if not re.search(r"정부|과기정통부|정보통신기획평가원|국회|공공\s*파운드리|"
                     r"예산안|사업\s*공고|과제\s*공모|국가연구개발|정부\s*지원|국산화\s*추진", head, re.I):
        return None
    if not re.search(r"예산|사업|지원|과제|공모|공고|연구개발|R&D|국산화|개발|"
                     r"선정|협약|조달|구축|생산|검증|실증|착수|시제품|양산", text, re.I):
        return None
    if re.search(r"공공\s*파운드리|인화인듐|\bInP\b|광반도체", head, re.I):
        axis, label = "inp-foundry", "InP 광반도체 공공 파운드리"
    elif re.search(r"광회선\s*스위칭|광스위칭|\bOCS\b|\bMEMS\b|L-COS", head, re.I):
        axis, label = "ocs", "OCS·MEMS·L-COS 광스위칭"
    elif re.search(r"\bCPO\b|\bNPO\b|광트랜시버|광원\s*국산", head, re.I):
        axis, label = "cpo-npo", "CPO·NPO·광트랜시버·광원"
    elif re.search(r"도파관|구리\s*케이블|고주파", head, re.I):
        axis, label = "waveguide", "랙 내부 구리·플라스틱 도파관"
    elif re.search(r"AI\s*기지국|분산\s*추론", head, re.I):
        axis, label = "ai-base-station", "AI 기지국·분산 추론"
    else:
        axis, label = "integrated", "AIDC 네트워크 국산화·기술개발"
    if re.search(r"국회.{0,35}(본회의|예산안|예산).{0,25}(최종\s*의결|통과|확정)|"
                 r"예산안.{0,20}국회.{0,20}(의결|통과)", head, re.I):
        phase, level, status = "budget-approved", 4, "국회 의결 보도·공식 확인 필요"
    elif re.search(r"실제\s*출하|첫\s*공급|양산\s*개시|생산\s*라인\s*가동|"
                   r"파운드리\s*준공|시제품\s*검증\s*완료", head, re.I):
        phase, level, status = "production", 5, "가동·검증·출하 주장·원문 확인 필요"
    elif re.search(r"협약\s*체결|사업자\s*선정\s*완료|수행기관\s*최종\s*선정|"
                   r"주관기관\s*선정|낙찰\s*결과|공급계약\s*체결", head, re.I):
        phase, level, status = "award", 4, "선정·협약 보도·원문 확인 필요"
    elif re.search(r"신규\s*과제\s*공고|연구개발\s*공모|사업\s*공고|"
                   r"과제\s*공모|제안요청서|입찰\s*공고|모집\s*공고", head, re.I) \
            and not re.search(r"(공고|공모).{0,10}(예정|계획|검토)", head, re.I):
        phase, level, status = "call", 3, "과제 공고·공모(선정·매출 전)"
    elif re.search(r"삭감|증액|감액|예산\s*조정|일정\s*연기|사업\s*보류|사업\s*취소", head, re.I):
        phase, level, status = "change", 3, "예산·일정 변경 보도·확정 단계 확인 필요"
    else:
        phase, level, status = "plan", 2, "정부 기획·예산안(선정·수주 아님)"
    year = "2028" if "2028" in text else "2027"
    amounts = re.findall(r"\d[\d,]*(?:\.\d+)?\s*(?:조\s*원|억\s*원|억원)", head)
    suffix = "-" + "-".join(re.sub(r"\s+", "", a) for a in amounts[:2]) if phase == "change" and amounts else ""
    key = f"aidc-network|{axis}|{year}|{phase}{suffix}"
    return (label, level, key, status)


def is_relevant(title: str, summary: str) -> bool:
    text = f"{norm(title)} {norm(summary)}".lower()
    if any(term in text for term in NOISE_TERMS):
        return False
    return bool(aidc_milestone(title, summary)) or (any(term in text for term in CORE_TERMS) and any(term in text for term in ACTION_TERMS))


def classify(text: str, quality: str) -> tuple[str, int]:
    t = norm(text).lower()

    # Highest-priority: money or purchase commitment is actually fixed.
    if any(x in t for x in ("수주", "공급계약", "공급 계약", "구매계약", "구매 계약", "발주", "낙찰", "납품")):
        return "실제 수주·구매", 5
    if any(x in t for x in ("수출금융 승인", "보증 승인", "금융지원 확정", "투자 승인", "직접투자", "출자 승인")):
        return "정책금융 확정", 5
    if any(x in t for x in ("세액공제", "보조금", "지원금")) and any(x in t for x in ("신설", "확정", "시행", "의결", "공고")):
        return "세제·보조금 확정", 5
    if any(x in t for x in ("예산", "사업비")) and any(x in t for x in ("확정", "의결", "공고", "편성", "배정")):
        return "예산·사업 확정", 5

    if any(x in t for x in ("선정", "협약체결", "협약 체결", "시범구매", "수의계약", "혁신제품")):
        return "조달·선정·협약", 4
    if any(x in t for x in ("해외실증", "해외 실증", "현지실증", "현지 실증", "poc", "실증")) and any(
        x in t for x in ("사우디", "uae", "아랍에미리트", "중동", "해외")
    ):
        return "해외 실증", 4
    if any(x in t for x in ("정상외교", "경제사절단", "정부 간", "정부간", "국부펀드")):
        return "정부·중동 사업화 지원", 4

    if any(x in t for x in ("지원사업", "사업공고", "공모", "조달", "공공구매", "초기수요", "초기 수요")):
        return "초기수요 정책", 3
    if any(x in t for x in ("수출금융", "무역보험", "보증", "해외진출", "해외 진출")):
        return "해외진출 지원", 3
    if quality == "공식" and any(x in t for x in ("보고서", "연구소", "제안", "필요")) and any(
        x in t for x in ("보조금", "세액공제", "초기수요", "초기 수요", "해외진출", "해외 진출", "공공구매")
    ):
        return "정책 선행신호", 2

    return "정책·산업 변화", 1


def entity_key(text: str) -> str:
    t = norm(text).lower()
    aliases = [
        ("리벨리온", ("리벨리온", "rebellions")),
        ("퓨리오사AI", ("퓨리오사ai", "퓨리오사 ai", "furiosa")),
        ("딥엑스", ("딥엑스", "deepx")),
        ("모빌린트", ("모빌린트", "mobilint")),
        ("하이퍼엑셀", ("하이퍼엑셀", "hyperaccel")),
    ]
    found = [name for name, xs in aliases if any(x in t for x in xs)]
    return "+".join(found) if found else "국산AI반도체산업"


def topic_key(text: str) -> str:
    t = norm(text).lower()
    for key, terms in [
        ("혁신제품", ("혁신제품", "시범구매", "수의계약")),
        ("해외실증", ("해외실증", "해외 실증", "현지실증", "현지 실증")),
        ("세제보조", ("세액공제", "보조금", "지원금")),
        ("정책금융", ("수출금융", "무역보험", "보증", "직접투자", "출자")),
        ("중동", ("사우디", "uae", "아랍에미리트", "중동", "국부펀드")),
        ("공공수요", ("공공구매", "초기수요", "초기 수요", "조달")),
        ("지원사업", ("지원사업", "사업공고", "공모", "선정")),
    ]:
        if any(x in t for x in terms):
            return key
    return "일반"


def event_signature(item: dict) -> str:
    if item.get("aidc_event_key"):
        return item["aidc_event_key"]
    category, _ = classify(f"{item['title']} {item.get('summary','')}", item["quality"])
    return f"{entity_key(item['title'] + ' ' + item.get('summary',''))}|{category}|{topic_key(item['title'] + ' ' + item.get('summary',''))}"


def amount_tokens(text: str) -> list[str]:
    found = re.findall(
        r"(?:약\s*)?\d+(?:[,.]\d+)*(?:조\s*원|억원|만억원|천억원|백억원|억\s*달러|만\s*달러|달러|억원\s*내외)",
        norm(text),
    )
    out = []
    for value in found:
        value = re.sub(r"\s+", "", value)
        if value not in out:
            out.append(value)
    return out[:5]


def key_for(item: dict) -> str:
    raw = f"{normalize_title(item['title'])}|{canonical_url(item['url'])}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def collect_google_news() -> tuple[list[dict], dict]:
    items = []
    health = {"attempted": 0, "successful": 0, "failed": 0, "aidc_attempted": 0, "aidc_successful": 0, "aidc_failed": 0, "errors": []}
    for lane, query in QUERY_SPECS:
        aidc_lane = lane.startswith("AIDC-")
        health["attempted"] += 1
        if aidc_lane:
            health["aidc_attempted"] += 1
        url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(query) + "&hl=ko&gl=KR&ceid=KR:ko"
        try:
            xml_text, _ = fetch_text(url)
            root = ET.fromstring(xml_text)
            health["successful"] += 1
            if aidc_lane:
                health["aidc_successful"] += 1
        except Exception as exc:
            health["failed"] += 1
            if aidc_lane:
                health["aidc_failed"] += 1
            health["errors"].append(f"{lane}: {type(exc).__name__}")
            continue
        for node in root.findall(".//item"):
            title = norm(node.findtext("title") or "")
            link = norm(node.findtext("link") or "")
            summary = norm(node.findtext("description") or "")
            source_node = node.find("source")
            source = norm(source_node.text if source_node is not None else "Google News")
            if not title or not link or not is_relevant(title, summary):
                continue
            pub = parse_pubdate(node.findtext("pubDate"))
            source_url = norm(source_node.attrib.get("url", "") if source_node is not None else "")
            quality = source_quality(source, lane, source_url)
            aidc = aidc_milestone(title, summary)
            category, stage = (aidc[0], aidc[1]) if aidc else classify(f"{title} {summary}", quality)
            # Low-signal items are only kept when they come from official sources.
            if stage <= 1 and quality != "공식":
                continue
            items.append(
                {
                    "title": title,
                    "url": link,
                    "summary": summary,
                    "source": source,
                    "lane": lane,
                    "quality": quality,
                    "category": category,
                    "stage": stage,
                    "aidc_event_key": aidc[2] if aidc else None,
                    "aidc_stage_label": aidc[3] if aidc else None,
                    "published_kst": pub.isoformat(timespec="minutes") if pub else None,
                }
            )
    if health["successful"] == 0:
        raise RuntimeError("All policy news queries failed; state must not advance")
    return items, health


def load_state() -> dict:
    if not STATE.exists():
        return {"initialized": False, "seen": {}}
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"initialized": False, "seen": {}}
    state.setdefault("seen", {})
    return state


def entry_time(entry: dict) -> dt.datetime | None:
    raw = str(entry.get("first_seen_kst") or "")
    try:
        value = dt.datetime.fromisoformat(raw)
        if value.tzinfo is None:
            value = value.replace(tzinfo=KST)
        return value
    except Exception:
        return None


def duplicate_reason(item: dict, seen: dict, now: dt.datetime) -> str | None:
    url = canonical_url(item["url"])
    title = normalize_title(item["title"])
    sig = event_signature(item)
    for prior in seen.values():
        if url and canonical_url(prior.get("url", "")) == url:
            return "same_url"
        if title and normalize_title(prior.get("title", "")) == title:
            return "same_title"

    # Same underlying stage/event from another publisher: suppress for 7 days.
    cutoff = now - dt.timedelta(days=7)
    for prior in seen.values():
        if not prior.get("alerted"):
            continue
        when = entry_time(prior)
        if not when or when < cutoff:
            continue
        if prior.get("event_signature") == sig:
            return f"same_event:{sig}"
    return None


def main() -> None:
    for path in (ALERT, PENDING, STATUS):
        if path.exists():
            path.unlink()

    now = now_kst()
    state = load_state()
    seen = dict(state.get("seen") or {})

    candidates, source_health = collect_google_news()
    # Freeze the AIDC lane until EVERY independently monitored source query succeeds.
    # A partial upstream outage must not advance its own last-healthy checkpoint.
    aidc_healthy = (source_health["aidc_attempted"] > 0 and source_health["aidc_successful"] == source_health["aidc_attempted"])
    if not aidc_healthy:
        candidates = [item for item in candidates if not item.get("aidc_event_key")]
    deduped = {}
    for item in candidates:
        key = key_for(item)
        current = deduped.get(key)
        if current is None or item["stage"] > current["stage"] or item["quality"] == "공식":
            deduped[key] = item

    ordered = sorted(
        deduped.items(),
        key=lambda kv: (kv[1].get("published_kst") or "", kv[1]["stage"]),
    )

    if not state.get("initialized"):
        for key, item in ordered:
            seen[key] = {
                "title": item["title"],
                "url": item["url"],
                "event_signature": event_signature(item),
                "stage": item["stage"],
                "category": item["category"],
                "first_seen_kst": now.isoformat(timespec="seconds"),
                "baseline": True,
            }
        pending = {
            "initialized": True,
            "bootstrap_kst": now.isoformat(timespec="seconds"),
            "last_checked_kst": now.isoformat(timespec="seconds"),
            "seen": seen,
        }
        PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        STATUS.write_text(
            f"# 국산 AI반도체 정책·초기수요·해외수주 감시\n\n"
            f"- 상태: 초기 기준선 생성\n"
            f"- 기준선 후보: {len(ordered)}개\n"
            f"- 신규 알림: 0개\n"
            f"- 조회시각: {now:%Y-%m-%d %H:%M:%S} KST\n",
            encoding="utf-8",
        )
        return

    try:
        last_checked = dt.datetime.fromisoformat(str(state.get("last_checked_kst") or ""))
        if last_checked.tzinfo is None:
            last_checked = last_checked.replace(tzinfo=KST)
    except Exception:
        last_checked = now - dt.timedelta(days=2)

    fresh = []
    fresh_aidc_keys = set()
    suppressed_duplicate = 0
    suppressed_stale = 0

    for key, item in ordered:
        if key in seen:
            continue
        aidc_key = item.get("aidc_event_key")
        if aidc_key == AIDC_PRIOR_PLAN:
            # Known 2026-11-12 planning speech and the reported 180억원 are old.
            seen[key] = {"title": item["title"], "url": item["url"], "event_signature": aidc_key,
                         "stage": item["stage"], "category": item["category"],
                         "first_seen_kst": now.isoformat(timespec="seconds"), "baseline": True}
            continue
        if aidc_key and aidc_key in fresh_aidc_keys:
            suppressed_duplicate += 1
            continue

        reason = duplicate_reason(item, seen, now)
        if reason:
            suppressed_duplicate += 1
            seen[key] = {
                "title": item["title"],
                "url": item["url"],
                "event_signature": event_signature(item),
                "stage": item["stage"],
                "category": item["category"],
                "first_seen_kst": now.isoformat(timespec="seconds"),
                "suppressed_duplicate": reason,
            }
            continue

        pub = None
        if item.get("published_kst"):
            try:
                pub = dt.datetime.fromisoformat(item["published_kst"])
            except Exception:
                pass
        aidc_checked = last_checked
        if aidc_key:
            try:
                aidc_checked = dt.datetime.fromisoformat(str(state.get("aidc_network_last_healthy_kst") or state.get("last_checked_kst") or ""))
            except Exception:
                pass
        if pub and pub < aidc_checked - dt.timedelta(hours=30):
            suppressed_stale += 1
            seen[key] = {
                "title": item["title"],
                "url": item["url"],
                "event_signature": event_signature(item),
                "stage": item["stage"],
                "category": item["category"],
                "first_seen_kst": now.isoformat(timespec="seconds"),
                "suppressed_stale": True,
            }
            continue

        # Telegram should prioritize verified policy/business changes, not theme/news noise.
        if item["quality"] == "기타보도":
            seen[key] = {
                "title": item["title"],
                "url": item["url"],
                "event_signature": event_signature(item),
                "stage": item["stage"],
                "category": item["category"],
                "first_seen_kst": now.isoformat(timespec="seconds"),
                "suppressed_low_quality": True,
            }
            continue
        # Stage 2 policy research is useful only from official/public research sources.
        if item["stage"] == 2 and item["quality"] != "공식" and not (aidc_key and item["quality"] == "신뢰보도"):
            continue
        if aidc_key:
            fresh_aidc_keys.add(aidc_key)
        fresh.append((key, item))

    if fresh:
        fresh.sort(key=lambda kv: (kv[1]["stage"], kv[1].get("published_kst") or ""), reverse=True)
        lines = [
            "<b>국산 AI반도체 정책·초기수요·해외수주</b>",
            "",
            f"조회시각: {now:%Y-%m-%d %H:%M} KST",
            f"신규 핵심 변화: {len(fresh)}건",
            "",
        ]

        for idx, (key, item) in enumerate(fresh[:6], start=1):
            direct = resolve_original_url(item["url"])
            amounts = amount_tokens(f"{item['title']} {item.get('summary','')}")
            priority = "최우선" if item["stage"] >= 5 else "중요" if item["stage"] >= 3 else "선행신호"
            lines.extend(
                [
                    f"<b>{idx}. [{esc(priority)} · {esc(item['category'])}] {esc(item['title'])}</b>",
                    f"• 상태: {esc(item['quality'])} · 단계 {item['stage']}/5",
                    f"• 대상: {esc(entity_key(item['title'] + ' ' + item.get('summary','')))}",
                ]
            )
            if amounts:
                lines.append("• 금액: " + esc(" · ".join(amounts)))
            if item.get("aidc_event_key"):
                lines.append("• 정책 단계: " + esc(item.get("aidc_stage_label")))
                lines.append("• 추적: 계획→국회 예산 의결→과제 공고→수행기업 선정·협약→시제품·양산·매출")
                if item["stage"] <= 2:
                    lines.append("• 예산 구분: 뉴스1 보도상 2027년 네트워크 180억원 계획은 과기정통부 상위 AIDC R&D 정부안 1,155억원과 중복 합산 금지")
            if item.get("published_kst"):
                lines.append(f"• 공개: {esc(item['published_kst'])}")
            lines.append(f"• 출처: {esc(item['source'])}")
            lines.append(f'<a href="{esc(direct)}">원문</a>')
            lines.append("")

            seen[key] = {
                "title": item["title"],
                "url": item["url"],
                "direct_url": direct,
                "event_signature": event_signature(item),
                "stage": item["stage"],
                "category": item["category"],
                "first_seen_kst": now.isoformat(timespec="seconds"),
                "alerted": True,
            }

        if len(fresh) > 6:
            lines.append(f"※ 한 번에 6건만 송출. 추가 {len(fresh)-6}건은 다음 실행에서 재평가합니다.")

        ALERT.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

    if len(seen) > 1200:
        seen = dict(list(seen.items())[-1200:])

    pending = {
        **{k: v for k, v in state.items() if k != "seen"},
        "initialized": True,
        "last_checked_kst": now.isoformat(timespec="seconds"),
        "aidc_network_watch_version": AIDC_RND_VERSION,
        "aidc_network_last_healthy_kst": now.isoformat(timespec="seconds") if aidc_healthy else state.get("aidc_network_last_healthy_kst"),
        "seen": seen,
    }
    PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    STATUS.write_text(
        f"# 국산 AI반도체 정책·초기수요·해외수주 감시\n\n"
        f"- 상태: {'정상 조회' if source_health['failed'] == 0 else '부분 조회 실패·원천 확인 필요'}\n"
        f"- 후보 항목: {len(ordered)}개\n"
        f"- 신규 알림: {len(fresh)}개\n"
        f"- 중복 억제: {suppressed_duplicate}개\n"
        f"- 오래된 재노출 억제: {suppressed_stale}개\n"
        f"- 누적 상태: {len(seen)}개\n"
        f"- 전체 검색: {source_health['successful']}/{source_health['attempted']} 성공 · 오류 {source_health['failed']}\n"
        f"- AIDC 광통신·OCS·InP 검색: {source_health['aidc_successful']}/{source_health['aidc_attempted']} 성공 · 오류 {source_health['aidc_failed']}\n"
        f"- AIDC 검색 오류: {', '.join([e for e in source_health['errors'] if e.startswith('AIDC-')][:5]) if source_health['aidc_failed'] else '없음'}\n"
        "- 금액 구분: 뉴스1 보도 180억원(좁은 네트워크 계획)과 과기정통부 상위 1,155억원(정부안) 중복 합산 금지\n"
        f"- 조회시각: {now:%Y-%m-%d %H:%M:%S} KST\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
