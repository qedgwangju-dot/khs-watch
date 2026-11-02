#!/usr/bin/env python3
import argparse
import datetime as dt
import hashlib
import html
import json
import os
import pathlib
import re
from collections import defaultdict
from email.utils import parsedate_to_datetime
from urllib.parse import quote, urlparse

import xml.etree.ElementTree as ET
import requests

KST = dt.timezone(dt.timedelta(hours=9))
ROOT = pathlib.Path(__file__).resolve().parents[1] if "scripts" in pathlib.Path(__file__).parts else pathlib.Path.cwd()
STATE_PATH = ROOT / "data" / "gwangju_airport_watch_state.json"
PENDING_STATE_PATH = ROOT / "out" / "gwangju_airport_watch_state_pending.json"
ALERT_PATH = ROOT / "out" / "gwangju_airport_alert.md"
STATUS_PATH = ROOT / "out" / "gwangju_airport_status.md"
ERROR_PATH = ROOT / "out" / "gwangju_airport_errors.log"

BASELINE = (
    "2026-08-28 국방부 이전부지 선정위원회가 전남 무안군 망운면 일대를 "
    "광주 군 공항 이전후보지로 선정. 최종 이전부지는 아직 미확정."
)
DEFAULT_CUTOFF = "2026-08-28T21:53:24+09:00"
USER_AGENT = os.getenv("GWANGJU_AIRPORT_WATCH_USER_AGENT", "KHS-Gwangju-Airport-Watch/2.0")
TIMEOUT = 25

QUERIES = [
    '"광주 군공항" 무안',
    '"광주 군 공항" 망운면',
    '"광주 군공항" 주민투표',
    '"광주 군공항" 유치 신청',
    '"광주 군공항" 이전부지 선정',
    '"광주 군공항" 지원계획 1조',
    '"광주 군공항" 이전사업 지원위원회',
    '"광주 군공항" 제1전투비행단 예천 서산 중원',
    '"광주 군공항" 반도체 클러스터 착공',
    '"광주 군공항" 지연 철회 소송',
    'site:korea.kr "광주 군 공항"',
    'site:mnd.go.kr "광주 군 공항"',
    '"광주 군공항" "미군시설" "포괄협정"',
    '"광주 군공항" "2027년" "임시배치" "예산"',
    '"광주 군공항" "주한미군" "대체시설" "비용분담"',
    '"광주 군공항" "공여구역" "반환" "국회 비준"',
    '"광주 군공항" "미군시설" "보강공사" "중단"',
    'site:korea.kr/briefing "광주 군공항" "포괄 협정"',
    'site:mnd.go.kr "COB" "광주" "미군"',
    'site:jeonnam.go.kr "광주 군 공항"',
    'site:muan.go.kr "광주 군공항"',
]

CATEGORY_RULES = {
    "지원계획·예산": ["지원계획", "1조", "지원위원회", "지원사업", "예산", "국비", "지원방안", "재원"],
    "주민투표": ["주민투표", "투표율", "찬성", "반대", "투표 결과"],
    "무안군 유치신청": ["유치 신청", "유치신청", "무안군수", "신청서"],
    "최종 이전부지": ["최종 이전부지", "이전부지 선정", "최종 선정", "이전부지로 선정"],
    "지연·철회·법적절차": ["지연", "연기", "철회", "취소", "가처분", "소송", "행정심판", "재검토", "무산"],
    "제1전투비행단 임시배치": ["제1전투비행단", "임시 배치", "임시배치", "예천", "서산", "중원기지", "기능 이전"],
    "미군시설·한미 포괄협정": ["미군시설", "미군 시설", "주한미군", "포괄협정", "포괄 협정", "COB", "공동운영기지", "공여구역"],
    "미군시설 이전예산": ["미군 시설 임시배치 예산", "미군시설 이전 예산", "미군시설 임시배치 예산", "정부안 미반영", "미군 시설 이전비"],
    "미군시설 보강공사": ["미군시설 공사", "미군 시설 보강공사", "급유시설", "엔지니어저장시설", "보강공사"],
    "반도체 클러스터·기존부지": ["반도체 클러스터", "반도체 산단", "국가산단", "산업단지", "착공", "부지 인도", "전력", "용수"],
}

ACTION_TERMS = [
    "확정", "선정", "의결", "발표", "공고", "구성", "출범", "개최", "실시", "결과",
    "찬성", "반대", "신청", "제출", "착공", "준공", "계약", "반영", "증액", "감액",
    "지연", "연기", "철회", "취소", "소송", "가처분", "재검토", "배치", "이전", "승인",
    "협의", "논의", "수립", "마련", "비준", "미반영", "포괄협정", "보강공사", "공여구역",
]

EVENT_ACTION_GROUPS = {
    "협의": ["협의", "논의", "회의", "간담회", "면담"],
    "계획수립": ["수립", "마련", "초안", "계획", "구체화"],
    "지원재원": ["지원", "예산", "국비", "지방비", "재원", "분담", "조달", "증액", "감액"],
    "주민투표": ["주민투표", "투표율", "투표", "찬성", "반대"],
    "유치신청": ["유치신청", "유치 신청", "신청서", "신청"],
    "최종선정": ["최종선정", "최종 선정", "최종 이전부지", "이전부지로 선정"],
    "법적절차": ["소송", "가처분", "행정심판", "재검토", "철회", "취소", "무산"],
    "일정변경": ["지연", "연기", "앞당겨", "당겨", "변경"],
    "착공준공": ["착공", "준공", "공사", "부지 인도"],
    "배치": ["배치", "임시배치", "기능 이전", "예천", "서산", "중원기지"],
}

OFFICIAL_DOMAIN_SUFFIXES = (
    "korea.kr", "mnd.go.kr", "molit.go.kr", "opm.go.kr", "gwangju.go.kr", "jeonnam.go.kr", "muan.go.kr",
)
OFFICIAL_NAME_TOKENS = ["국방부", "정책브리핑", "국토교통부", "국무조정실", "광주광역시", "전라남도", "무안군"]

TRUSTED_DOMAIN_SUFFIXES = (
    "yna.co.kr", "newsis.com", "news1.kr", "kbs.co.kr", "imbc.com", "sbs.co.kr", "hankyung.com",
    "mk.co.kr", "sedaily.com", "mt.co.kr", "etnews.com", "chosun.com", "joongang.co.kr", "donga.com",
    "asiae.co.kr", "fnnews.com", "newspim.com", "ohmynews.com", "ikbc.co.kr",
)
TRUSTED_NAME_TOKENS = [
    "연합뉴스", "뉴시스", "뉴스1", "KBS", "MBC", "SBS", "한국경제", "매일경제", "서울경제",
    "머니투데이", "전자신문", "아시아경제", "파이낸셜뉴스", "뉴스핌", "오마이뉴스", "KBC광주방송",
]

PUBLISHER_ALIASES = {
    "yna.co.kr": "연합뉴스", "연합뉴스": "연합뉴스",
    "newsis.com": "뉴시스", "뉴시스": "뉴시스",
    "news1.kr": "뉴스1", "뉴스1": "뉴스1",
    "ohmynews.com": "오마이뉴스", "오마이뉴스": "오마이뉴스",
    "ikbc.co.kr": "KBC광주방송", "KBC광주방송": "KBC광주방송",
    "kbs.co.kr": "KBS", "kbs": "KBS",
    "imbc.com": "MBC", "mbc": "MBC",
    "sbs.co.kr": "SBS", "sbs": "SBS",
    "hankyung.com": "한국경제", "한국경제": "한국경제",
    "mk.co.kr": "매일경제", "매일경제": "매일경제",
    "sedaily.com": "서울경제", "서울경제": "서울경제",
    "mt.co.kr": "머니투데이", "머니투데이": "머니투데이",
    "etnews.com": "전자신문", "전자신문": "전자신문",
    "chosun.com": "조선일보", "조선일보": "조선일보",
    "joongang.co.kr": "중앙일보", "중앙일보": "중앙일보",
    "donga.com": "동아일보", "동아일보": "동아일보",
    "asiae.co.kr": "아시아경제", "아시아경제": "아시아경제",
    "fnnews.com": "파이낸셜뉴스", "파이낸셜뉴스": "파이낸셜뉴스",
    "newspim.com": "뉴스핌", "뉴스핌": "뉴스핌",
}

GENERIC_EVENT_WORDS = {
    "광주", "군공항", "군", "공항", "이전", "무안", "무안군", "전남", "전남광주", "전남광주시",
    "관련", "대한", "등", "및", "일대", "후보지", "이전후보지", "사업", "지역",
}


def now_kst():
    return dt.datetime.now(dt.timezone.utc).astimezone(KST)


def parse_iso(value):
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=KST)
        return parsed
    except Exception:
        return None


def normalize_text(text):
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_title(title):
    title = normalize_text(title)
    title = re.sub(r"\s+-\s+[^-]{1,30}$", "", title).strip()
    return title


def title_signature(title):
    title = normalize_title(title).lower()
    return re.sub(r"[^0-9a-z가-힣]+", "", title)


def item_id(item):
    basis = "|".join([item.get("title", ""), item.get("source", ""), item.get("link", "")])
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:24]


def domain_from_url(url):
    try:
        return (urlparse(url).hostname or "").lower().removeprefix("www.")
    except Exception:
        return ""


def publisher_key(source, source_url="", link=""):
    source_norm = normalize_text(source).lower()
    domains = [domain_from_url(source_url), domain_from_url(link)]
    for domain in domains:
        if not domain:
            continue
        for alias, canonical in PUBLISHER_ALIASES.items():
            if "." in alias and (domain == alias or domain.endswith("." + alias)):
                return canonical
    for alias, canonical in PUBLISHER_ALIASES.items():
        if "." not in alias and alias.lower() in source_norm:
            return canonical
    if source_norm.endswith(".com") or source_norm.endswith(".co.kr") or source_norm.endswith(".kr"):
        for alias, canonical in PUBLISHER_ALIASES.items():
            if "." in alias and alias in source_norm:
                return canonical
    return normalize_text(source) or "미상"


def source_rank(source, source_url, link):
    source = source or ""
    domain = domain_from_url(source_url) or domain_from_url(link)
    if any(domain == suffix or domain.endswith("." + suffix) for suffix in OFFICIAL_DOMAIN_SUFFIXES) or any(tok in source for tok in OFFICIAL_NAME_TOKENS):
        return "공식"
    if any(domain == suffix or domain.endswith("." + suffix) for suffix in TRUSTED_DOMAIN_SUFFIXES) or any(tok in source for tok in TRUSTED_NAME_TOKENS):
        return "신뢰언론"
    return "기타"


def classify(text):
    return [category for category, words in CATEGORY_RULES.items() if any(word in text for word in words)]


def relevant(text):
    compact = text.replace(" ", "")
    return ("광주" in text and "군공항" in compact) or ("무안" in text and "군공항" in compact) or ("망운면" in text and "공항" in text)


def decisive(text):
    return any(term in text for term in ACTION_TERMS)


def action_groups(text):
    compact = text.replace(" ", "")
    groups = set()
    for group, words in EVENT_ACTION_GROUPS.items():
        if any(word.replace(" ", "") in compact for word in words):
            groups.add(group)
    return groups


def title_tokens(title):
    words = re.findall(r"[0-9A-Za-z가-힣]+", normalize_title(title).lower())
    return {w for w in words if len(w) >= 2 and w not in GENERIC_EVENT_WORDS}


def same_event(a, b):
    if not set(a.get("categories") or []) & set(b.get("categories") or []):
        return False
    if title_signature(a.get("title", "")) == title_signature(b.get("title", "")):
        return True

    a_groups = action_groups(" ".join([a.get("title", ""), a.get("description", "")]))
    b_groups = action_groups(" ".join([b.get("title", ""), b.get("description", "")]))
    if not (a_groups & b_groups):
        return False

    at, bt = title_tokens(a.get("title", "")), title_tokens(b.get("title", ""))
    if not at or not bt:
        return False
    common = at & bt
    union = at | bt
    jaccard = len(common) / max(1, len(union))
    return len(common) >= 2 and jaccard >= 0.34


def preferred_item(current, challenger):
    rank_score = {"공식": 3, "신뢰언론": 2, "기타": 1}

    def score(item):
        source = item.get("source", "")
        source_is_domain = "." in source and " " not in source
        return (
            rank_score.get(item.get("rank"), 0),
            0 if source_is_domain else 1,
            -len(item.get("link", "")),
            item.get("published") or "",
        )

    return challenger if score(challenger) > score(current) else current


def fetch_rss(url, provider, query):
    headers = {"User-Agent": USER_AGENT, "Accept": "application/rss+xml,application/xml,text/xml,*/*"}
    response = requests.get(url, headers=headers, timeout=TIMEOUT)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    items = []
    for node in root.findall(".//item"):
        source_node = node.find("source")
        source = normalize_text(source_node.text if source_node is not None and source_node.text else "")
        source_url = source_node.attrib.get("url", "") if source_node is not None else ""
        title = normalize_title(node.findtext("title") or "")
        link = (node.findtext("link") or "").strip()
        description = normalize_text(node.findtext("description") or "")
        raw_time = node.findtext("pubDate") or node.findtext("date") or ""
        try:
            published = parsedate_to_datetime(raw_time) if raw_time else None
            if published is not None and published.tzinfo is None:
                published = published.replace(tzinfo=dt.timezone.utc)
        except Exception:
            published = None
        item = {
            "title": title,
            "link": link,
            "description": description,
            "source": source or provider,
            "source_url": source_url,
            "provider": provider,
            "query": query,
            "published": published.isoformat() if published else None,
        }
        item["publisher"] = publisher_key(item["source"], source_url, link)
        item["rank"] = source_rank(item["source"], source_url, link)
        item["id"] = item_id(item)
        items.append(item)
    return items



# Verified from the 2026-11-02 Ministry of National Defense spokesperson briefing.
# This first intake is ONE incident with three separate factual axes; it does
# not claim a signed COB agreement, secured budget or halted construction.
COB_OFFICIAL_BRIEFING_URL = "https://www.korea.kr/briefing/policyBriefingView.do?newsId=156787549"
COB_BRIEFING_EVENT_KEY = "gwangju_us_facilities_briefing_20261102"
COB_SOURCE_DATE = None  # Only official briefing date, not clock time, is confirmed.
US_FACILITY_WORDS = ("미군", "주한미군", "미군시설", "미군 시설", "공여구역", "COB", "포괄협정", "포괄 협정")
US_BASELINE_WORDS = ("포괄협정", "포괄 협정", "COB", "2027년", "미군시설", "미군 시설", "공여구역", "보강공사")


def is_us_facility_story(item):
    title = normalize_text(item.get("title", ""))
    description = normalize_text(item.get("description", ""))
    compact = (title + " " + description).replace(" ", "").lower()
    return ("광주" in compact and "군공항" in compact and
            any(word.replace(" ", "").lower() in compact for word in US_FACILITY_WORDS))


def is_us_baseline_reprint(item):
    """Block known 2026-11-02 follow-up coverage, not fresh delays."""
    if not is_us_facility_story(item):
        return False
    title = normalize_text(item.get("title", "")).replace(" ", "")
    if any(t in title for t in (
        "협상결렬", "협정파기", "비준부결", "시설이전지연",
        "대체시설미확보", "대체부지변경", "일정연기확정",
    )):
        return False
    if ("포괄협정" in title or "COB" in title) and any(
        t in title for t in ("추진", "협의중", "연내", "협의완료목표",
                          "문안협의", "큰틀합의", "거의다돼")
    ):
        return True
    if ("미군" in title or "임시배치" in title) and ("예산" in title or "이전비" in title):
        if any(t in title for t in ("정부안에빠져", "정부안미반영", "예산미반영",
                                   "예산누락", "국회협의", "예산협의중")):
            return True
    if ("미군" in title or "공여구역" in title) and ("보강공사" in title or "시설공사" in title):
        if any(t in title for t in ("중단협의", "중단도논의", "공정률0.2", "중단논의")):
            return True
    return False


def us_milestone(item):
    """Classify only a *new completed action* stated in the headline.

    Background mentions of other years, negotiation goals or mere requests
    must never promote a historic development into a fresh alert.
    """
    if not is_us_facility_story(item):
        return ""
    title = normalize_text(item.get("title", "")).replace(" ", "")
    if not title:
        return ""
    if any(t in title for t in ("목표", "예정", "전망", "추진", "협의중", "검토중", "요청", "계획", "논의중", "합의임박")):
        return ""
    if "포괄협정" in title or "COB" in title:
        if any(t in title for t in ("국회비준동의안가결", "국회비준완료", "비준동의안통과")):
            return "cob_ratified"
        if any(t in title for t in ("포괄협정서명", "포괄협정체결", "협정서명완료", "협정체결완료")):
            return "cob_signed"
        if any(t in title for t in ("문안협의완료", "협정문안최종합의", "문안최종합의")):
            return "cob_text_agreed"
    if ("미군" in title or "임시배치" in title) and ("예산" in title or "이전비" in title):
        if any(t in title for t in ("미반영", "빠져", "미확보", "불발")):
            return ""  # 2027 government draft omission already verified 2026-11-02
        if any(t in title for t in ("예산안최종확정", "예산최종확정", "예산확보완료", "예산안가결")):
            return "2027_budget_enacted"
        if any(t in title for t in ("추경반영확정", "국회증액확정", "예산반영확정", "예산편성확정")):
            return "2027_budget_revised"
    if ("미군" in title or "공여" in title or "광주군공항" in title):
        if any(t in title for t in ("공여구역반환완료", "미군공여지반환완료")):
            return "returned_land"
        if any(t in title for t in ("미군시설이전완료", "미군시설임시배치완료")):
            return "relocation_completed"
        if any(t in title for t in ("대체시설부지확정", "미군대체시설계약체결", "대체시설착공")):
            return "replacement_facility"
        if any(t in title for t in ("보강공사중단확정", "보강공사중단합의", "보강공사중단결정")):
            return "existing_works_halted"
        if any(t in title for t in ("보강공사재개확정", "보강공사재개")):
            return "existing_works_resumed"
    return ""


def verified_briefing_item(state):
    """One-time, source-labeled briefing event; never replay after confirmed send."""
    if COB_BRIEFING_EVENT_KEY in (state.get("sent_event_keys") or []):
        return None
    return {
        "id": COB_BRIEFING_EVENT_KEY,
        "event_key": COB_BRIEFING_EVENT_KEY,
        "title": "광주 미군시설 이전: 포괄협정 협의·2027년 정부안 예산 미반영",
        "link": COB_OFFICIAL_BRIEFING_URL,
        "description": "2026-11-02 국방부 정례브리핑의 미군시설 이전 진행 단계",
        "source": "대한민국 정책브리핑·국방부",
        "source_url": COB_OFFICIAL_BRIEFING_URL,
        "publisher": "국방부",
        "rank": "공식",
        "published": COB_SOURCE_DATE,
        "source_date_display": "2026-11-02 (발표일 확인·시각 미공개)",
        "categories": ["미군시설·한미 포괄협정", "미군시설 이전예산", "미군시설 보강공사"],
        "verification": "국방부 2026-11-02 정례브리핑 + 구체적인 사업비·목표는 출처별 별도 표시",
        "summary_lines": [
            "[협의 중] 광주 미군시설 이전은 한미 포괄협정에 포함하는 방안을 협의 중. 협정 체결·국회 비준 전.",
            "[정부안 미반영] 2027년 미군시설 임시배치 예산은 정부안에 없음. 최종 예산 확정 0원이란 뜻은 아님.",
            "[중단 미확정] 기존 보강공사 공정률은 0.2%. 중단 여부도 한미 협의 중.",
        ],
        "detail_sections": [
            {
                "title": "한미 포괄협정 (협의 단계)",
                "bullets": [
                    "국방부 공식: 광주 미군시설 임시배치를 기존 공동운영기지(COB) 이전 포괄협정에 포함하는 방안을 미측과 협의 중.",
                    "연합뉴스 보도: 연내 협정 문안 협의 완료가 정부 목표. 문안 완료·서명·국회 비준은 아직 확정되지 않음.",
                ],
            },
            {
                "title": "2027년 미군시설 이전예산 (정부안 단계)",
                "bullets": [
                    "국방부 공식: 미군시설 임시배치 예산은 현재 2027년 정부안 미반영.",
                    "국회 심의 과정에서 협의 필요. 정부안 미반영과 국회 최종 예산 0원 확정은 다름.",
                ],
            },
            {
                "title": "기존 미군시설 보강공사 (중단 협의 단계)",
                "bullets": [
                    "연합뉴스 보도 기준 세부사업비: 항공유 급유시설 586억원 + 엔지니어저장시설 36억원 + 철제물탱크 13억원 = 635억원.",
                    "국방부 공식: 공정률 0.2%. 공사 중단 등을 미측과 협의 중이며 중단 완료가 아님.",
                    "635억원은 기존 세부사업비 합계이며, 실제 집행액이나 신규 이전예산으로 볼 수 없음.",
                ],
            },
            {
                "title": "반도체 국가산단에 미치는 영향 (목표 단계)",
                "bullets": [
                    "정부의 광주 군공항 기능 임시배치 목표는 2028년 중순이며, 시점 단축도 검토 대상.",
                    "미군시설 이전·공여구역 반환·부지 인도·반도체 팹 착공은 아직 각각 별도 확인이 필요함.",
                ],
            },
            {
                "title": "다음 확인 관문 (확정 전)",
                "bullets": [
                    "미군시설: 대체시설·비용분담 협의 → 협정 문안 완료·서명 → 국회 비준 동의 → 예산 확보 → 시설 이전·공여구역 반환.",
                    "군공항 최종 이전부지: 이전주변지역 지원계획 → 주민투표 → 무안군 유치신청 → 최종 이전부지 선정.",
                ],
            },
        ],
        "additional_sources": [
            {
                "publisher": "연합뉴스",
                "date": "2026-11-02 13:35 KST",
                "link": "https://www.yna.co.kr/view/AKR20261102090100504",
            },
            {
                "publisher": "청와대 브리핑",
                "date": "2026-09-29 (2028년 중순 목표)",
                "link": "https://www.korea.kr/briefing/presidentView.do?newsId=148972779",
            },
        ],
    }

def select_us_milestone_alerts(items, state):
    """Build verified change alerts while retaining cross-run evidence.

    One newspaper's article is pending, not silently marked delivered. A
    later distinct publisher can corroborate it even after source dedup.
    """
    cache = dict(state.get("us_pending_evidence") or {})
    sent_keys = set(state.get("sent_event_keys") or [])
    now = now_kst()
    fresh = {}
    for family, record in cache.items():
        try:
            first = parse_iso(record.get("first_seen") or "")
            if not first or now - first.astimezone(KST) > dt.timedelta(days=10):
                continue
        except (ValueError, TypeError):
            continue
        if family in sent_keys:
            continue
        fresh[family] = record
    cache = fresh
    for item in items:
        family = us_milestone(item)
        if not family or family in sent_keys:
            continue
        # User has requested event-stage monitoring, not old article replay.
        published = parse_iso(item.get("published"))
        if published and (now - published.astimezone(KST)).total_seconds() > 7 * 86400:
            continue
        record = cache.setdefault(family, {"first_seen": now.isoformat(), "items": []})
        arr = record["items"]
        publisher = item.get("publisher") or publisher_key(item.get("source", ""), item.get("source_url", ""), item.get("link", ""))
        if not any((x.get("publisher"), x.get("link")) == (publisher, item.get("link")) for x in arr):
            arr.append(dict(item))
            if len(arr) > 14:
                del arr[:-14]

    selected = []
    for family, record in list(cache.items()):
        arr = [x for x in record.get("items", []) if us_milestone(x) == family]
        publishers = {x.get("publisher") for x in arr if x.get("publisher") and x.get("rank") in ("공식", "신뢰언론")}
        official = [x for x in arr if (
            domain_from_url(x.get("source_url", "")) in OFFICIAL_DOMAIN_SUFFIXES
            or domain_from_url(x.get("link", "")) in OFFICIAL_DOMAIN_SUFFIXES
        )]
        if len(publishers) < 2 and not official:
            continue
        preferred = sorted(arr, key=lambda x: (x.get("rank") == "공식", x.get("published") or ""), reverse=True)[0]
        event = dict(preferred)
        event["event_key"] = "gwangju_us_" + family
        event["verification"] = "공식자료" if official else f"독립 언론 {len(publishers)}곳 교차확인"
        event["categories"] = ["미군시설·한미 포괄협정", "미군시설 이전예산", "미군시설 보강공사"] if family == "cob_ratified" else event.get("categories", [])
        event["detail_lines"] = [
            f"실제 변경 단계: {family} (계획·발언이 아니라 실행 완료 문구와 출처 대조)",
            "이전 정부안의 예산 미반영 및 협정 협의 중 상태와 구분",
        ]
        selected.append(event)
        cache.pop(family, None)
    return selected, cache


def collect_items():
    all_items, errors = [], []
    for query in QUERIES:
        encoded = quote(query)
        feeds = [
            ("Google 뉴스", f"https://news.google.com/rss/search?q={encoded}&hl=ko&gl=KR&ceid=KR:ko"),
            ("Bing 뉴스", f"https://www.bing.com/news/search?q={encoded}&format=rss&setlang=ko-kr"),
        ]
        for provider, url in feeds:
            try:
                all_items.extend(fetch_rss(url, provider, query))
            except Exception as exc:
                errors.append(f"{provider} | {query} | {type(exc).__name__}: {exc}")

    by_publisher_title = {}
    for item in all_items:
        key = (item["publisher"], title_signature(item["title"]))
        current = by_publisher_title.get(key)
        by_publisher_title[key] = item if current is None else preferred_item(current, item)

    by_title = {}
    for item in by_publisher_title.values():
        key = title_signature(item["title"])
        current = by_title.get(key)
        by_title[key] = item if current is None else preferred_item(current, item)

    return list(by_title.values()), errors


def load_state():
    if STATE_PATH.exists():
        try:
            state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(state, dict):
                return state
        except Exception:
            pass
    return {
        "version": 1,
        "baseline": BASELINE,
        "cutoff_kst": DEFAULT_CUTOFF,
        "seen_ids": [],
        "last_scan_kst": None,
    }


def cluster_events(items):
    clusters = []
    for item in sorted(items, key=lambda x: x.get("published") or ""):
        placed = False
        for cluster in clusters:
            if any(same_event(item, existing) for existing in cluster):
                cluster.append(item)
                placed = True
                break
        if not placed:
            clusters.append([item])
    return clusters


def select_alerts(items, state):
    cutoff = parse_iso(state.get("cutoff_kst") or DEFAULT_CUTOFF) or parse_iso(DEFAULT_CUTOFF)
    seen = set(state.get("seen_ids") or [])
    candidates = []

    for item in items:
        if item["id"] in seen:
            continue
        published = parse_iso(item.get("published"))
        if published and cutoff and published.astimezone(KST) <= cutoff.astimezone(KST):
            continue
        text = " ".join([item.get("title", ""), item.get("description", "")])
        if not relevant(text):
            continue
        # US-facility milestones have their own status/dedupe/verification
        # pipeline so newspaper reprints cannot duplicate the original.
        if us_milestone(item) or is_us_baseline_reprint(item):
            continue
        categories = classify(text)
        if not categories or not decisive(text):
            continue
        item = dict(item)
        item["categories"] = categories
        candidates.append(item)

    selected = []

    official_clusters = cluster_events([i for i in candidates if i["rank"] == "공식"])
    for cluster in official_clusters:
        rep = cluster[0]
        for item in cluster[1:]:
            rep = preferred_item(rep, item)
        rep = dict(rep)
        rep["verification"] = "공식자료"
        selected.append(rep)

    trusted_clusters = cluster_events([i for i in candidates if i["rank"] == "신뢰언론"])
    for cluster in trusted_clusters:
        publishers = {i["publisher"] for i in cluster}
        if len(publishers) < 2:
            continue
        rep = cluster[0]
        for item in cluster[1:]:
            rep = preferred_item(rep, item)
        rep = dict(rep)
        rep["verification"] = f"신뢰언론 {len(publishers)}곳 교차"
        rep["corroborated_publishers"] = sorted(publishers)
        selected.append(rep)

    compact = []
    for item in sorted(selected, key=lambda x: x.get("published") or ""):
        duplicate_idx = None
        for idx, existing in enumerate(compact):
            if same_event(item, existing):
                duplicate_idx = idx
                break
        if duplicate_idx is None:
            compact.append(item)
        elif item.get("verification") == "공식자료" and compact[duplicate_idx].get("verification") != "공식자료":
            compact[duplicate_idx] = item

    return compact, candidates


def format_time(value):
    parsed = parse_iso(value)
    if not parsed:
        return "시각 미표기"
    return parsed.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")


def build_alert(selected):
    """Readable, lossless alert text; every selected event appears."""
    ts = now_kst().strftime("%Y-%m-%d %H:%M KST")
    lines = [
        f"[광주 군공항 이전 감시] 신규 변화 {len(selected)}건",
        f"조회: {ts}",
        "",
    ]
    for idx, item in enumerate(selected, 1):
        verification = item.get("verification") or ("공식자료" if item.get("rank") == "공식" else "교차검증")
        lines.extend([
            f"■ {idx}. {item.get('title') or '제목 미확인'}",
            f"확인 단계: {verification}",
        ])
        for summary in item.get("summary_lines") or []:
            lines.append(f"• {summary}")
        for section in item.get("detail_sections") or []:
            lines.extend(["", f"【{section.get('title') or '세부 내용'}】"])
            for detail in section.get("bullets") or []:
                lines.append(f"• {detail}")
        for detail in item.get("detail_lines") or []:
            lines.append(f"• {detail}")
        if item.get("categories") and not item.get("detail_sections"):
            lines.append("분야: " + " · ".join(item["categories"]))
        link = item.get("link") or ""
        if link:
            lines.extend(["", f"- 출처원문: {item.get('publisher') or '발행기관 미확인'} | {item.get('source_date_display') or format_time(item.get('published'))} | {link}"])
        for extra in item.get("additional_sources") or []:
            if extra.get("link"):
                lines.append(f"- 출처원문: {extra.get('publisher') or '추가 근거'} | {extra.get('date') or '발표일 미확인'} | {extra['link']}")
        lines.append("")

    lines.extend([
        "【기존 기준선 · 신규 사실과 구분】",
        BASELINE,
        "다음 핵심 절차: 지원계획 구체화 → 주민투표 → 무안군 유치신청 → 최종 이전부지 선정.",
    ])
    return "\n".join(lines).strip() + "\n"


def render_telegram_html(text):
    """HTML-escape untrusted text and turn verified source URLs into links."""
    rendered = []
    for line in text.splitlines():
        match = re.fullmatch(
            r"\s*-\s*출처원문:\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(https?://\S+)\s*",
            line,
        )
        if match:
            source, when, url = match.groups()
            rendered.append(
                f"출처: {html.escape(source.strip())} · "
                f"{html.escape(when.strip())} · "
                f'<a href="{html.escape(url.strip(), quote=True)}">원문 보기</a>'
            )
            continue
        if line.startswith("■ ") or (line.startswith("【") and line.endswith("】")) or line.startswith("[광주 군공항 이전 감시]"):
            rendered.append(f"<b>{html.escape(line)}</b>")
        else:
            rendered.append(html.escape(line))
    return "\n".join(rendered)


def telegram_html_chunks(text, limit=3700):
    """Split at original lines only, never drop an event or cut a source URL."""
    if not text.strip():
        return []
    if limit < 400:
        raise ValueError("Telegram chunk limit too small")
    budget = limit - 90  # reserve room for 1/N headings
    groups, group = [], []
    for line in text.rstrip("\n").split("\n"):
        candidate = group + [line]
        if len(render_telegram_html("\n".join(candidate))) <= budget:
            group = candidate
            continue
        if not group:
            raise ValueError("Single alert line exceeds Telegram safe length; never truncate")
        groups.append(group)
        group = [line]
        if len(render_telegram_html(line)) > budget:
            raise ValueError("Single alert line exceeds Telegram safe length; never truncate")
    if group:
        groups.append(group)
    chunks = []
    for index, lines in enumerate(groups, 1):
        prefix = f"【광주 군공항 이전 알림 {index}/{len(groups)}】\n" if len(groups) > 1 else ""
        part = prefix + render_telegram_html("\n".join(lines))
        if len(part) > limit:
            raise ValueError("Telegram chunk unexpectedly exceeds safe length")
        chunks.append(part)
    return chunks

def write_status(total, candidates, selected, errors):
    ts = now_kst().strftime("%Y-%m-%d %H:%M:%S KST")
    lines = [
        "# 광주 군공항 이전 감시 상태",
        f"- 조회: {ts}",
        f"- 중복 제거 후 수집 항목: {total}건",
        f"- 의미 변화 후보: {len(candidates)}건",
        f"- 알림 확정: {len(selected)}건",
        f"- 수집 오류: {len(errors)}건",
        f"- 기준선: {BASELINE}",
        "- 교차검증 규칙: 동일 발행사 별칭/미러/동일 제목은 독립 출처로 세지 않음; 같은 사건끼리만 독립 발행사 수를 계산.",
    ]
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ERROR_PATH.write_text("\n".join(errors) + ("\n" if errors else ""), encoding="utf-8")


def build_pending_state(items, state, selected=None, us_cache=None):
    seen = list(dict.fromkeys((state.get("seen_ids") or []) + [(i.get("id") or item_id(i)) for i in items]))[-2500:]
    updated = dict(state)  # preserve existing settings and historic event state
    updated.update({
        "version": 3,
        "baseline": BASELINE,
        "cutoff_kst": state.get("cutoff_kst") or DEFAULT_CUTOFF,
        "seen_ids": seen,
        "last_scan_kst": now_kst().isoformat(),
    })
    sent = list(dict.fromkeys(state.get("sent_event_keys") or []))
    for event in selected or []:
        if event.get("event_key") and event["event_key"] not in sent:
            sent.append(event["event_key"])
    updated["sent_event_keys"] = sent[-1000:]
    updated["us_pending_evidence"] = us_cache if us_cache is not None else dict(state.get("us_pending_evidence") or {})
    return updated


def self_test():
    sample = {
        "title": "국방부, 광주 군공항 최종 이전부지 선정 결과 발표",
        "description": "무안군 주민투표 결과를 반영해 최종 선정",
    }
    text = sample["title"] + " " + sample["description"]
    assert relevant(text)
    cats = classify(text)
    assert "최종 이전부지" in cats and "주민투표" in cats
    assert decisive(text)
    assert normalize_title("테스트 - 연합뉴스") == "테스트"
    assert publisher_key("뉴시스", "https://www.newsis.com") == "뉴시스"
    assert publisher_key("newsis.com", "https://www.newsis.com") == "뉴시스"

    a = {
        "title": "전남광주시, 무안군과 '군공항 이전' 지원계획 등 협의",
        "description": "지원계획 협의",
        "categories": ["지원계획·예산"],
    }
    b = {
        "title": "전남광주시, 무안군과 '군공항 이전' 지원계획 등 협의",
        "description": "지원계획 협의",
        "categories": ["지원계획·예산"],
    }
    assert same_event(a, b)

    c = {
        "title": "광주 군공항 이전 무안지역 지원계획 마련 1조 조달 관건",
        "description": "9월 말 초안 마련",
        "categories": ["지원계획·예산"],
    }
    assert not same_event(a, c)
    baseline_news = {
        "title": "광주 군공항 미군시설 이전 포괄협정 추진…연내 문안 협의 완료 목표",
        "description": "광주 군공항 미군시설 대체시설과 예산 논의",
        "source": "KBC광주방송", "publisher": "KBC광주방송",
        "link": "https://example.com/current", "categories": ["미군시설·한미 포괄협정"],
        "published": now_kst().isoformat(), "rank": "신뢰언론",
    }
    assert is_us_facility_story(baseline_news)
    assert not us_milestone(baseline_news)
    budget = dict(baseline_news, title="광주 군공항 미군시설 이전 예산 2027년 정부안 미반영")
    assert not us_milestone(budget)
    assert is_us_baseline_reprint(baseline_news)
    assert is_us_baseline_reprint(budget)
    bad_news = dict(baseline_news, title="광주 군공항 미군시설 이전 포괄협정 협상 결렬")
    assert not is_us_baseline_reprint(bad_news)
    assert not us_milestone(bad_news)
    signed = dict(baseline_news, title="광주 군공항 미군시설 포괄협정 체결 완료")
    assert us_milestone(signed) == "cob_signed"
    signed_target = dict(signed, title=signed["title"] + " 목표")
    assert not us_milestone(signed_target)
    allocated = dict(baseline_news, title="광주 군공항 미군시설 이전 예산 국회 증액 확정")
    assert us_milestone(allocated) == "2027_budget_revised"
    work = dict(baseline_news, title="광주 군공항 미군시설 보강공사 중단 합의")
    assert us_milestone(work) == "existing_works_halted"
    item = verified_briefing_item({"sent_event_keys": []})
    assert item is not None
    notice = build_alert([item])
    for required in ("586억원", "36억원", "13억원", "635억원", "0.2%",
                     "2027년", "2028년 중순", "정부안 미반영", "협의 중",
                     "공여구역 반환", "국회 비준", "원문 보기"):
        if required == "원문 보기":
            assert required in render_telegram_html(notice)
        else:
            assert required in notice, required
    assert item["link"] == COB_OFFICIAL_BRIEFING_URL
    assert verified_briefing_item({"sent_event_keys": [COB_BRIEFING_EVENT_KEY]}) is None
    assert '&lt;script&gt;' in render_telegram_html('<script>')
    assert '<a href="' in render_telegram_html(notice)
    synthetic = [
        {"title": f"서로 다른 사건 고유번호 {i}", "categories": ["지원계획·예산"],
         "publisher": "국방부", "rank": "공식",
         "link": f"https://example.com/source/{i}"} for i in range(11)
    ]
    full = build_alert(synthetic)
    assert "■ 11. 서로 다른 사건 고유번호 10" in full
    chunks = telegram_html_chunks(full, limit=600)
    assert len(chunks) > 1 and all(len(part) <= 600 for part in chunks)
    assert all(f"고유번호 {i}" in "\n".join(chunks) for i in range(11))
    assert all(f"source/{i}" in "\n".join(chunks) for i in range(11))
    try:
        telegram_html_chunks("x" * 700, limit=600)
        raise AssertionError("Oversized single line was silently accepted")
    except ValueError:
        pass
    no_repeat = {"sent_event_keys": [COB_BRIEFING_EVENT_KEY], "us_pending_evidence": {}}
    assert not select_us_milestone_alerts([baseline_news], no_repeat)[0]
    event1, cache = select_us_milestone_alerts([signed], no_repeat)
    assert not event1 and "cob_signed" in cache
    signed_2 = dict(signed, publisher="연합뉴스", source="연합뉴스", link="https://example.com/yna")
    event2, cache2 = select_us_milestone_alerts([signed_2], dict(no_repeat, us_pending_evidence=cache))
    assert len(event2) == 1 and event2[0]["event_key"] == "gwangju_us_cob_signed"
    assert "cob_signed" not in cache2
    state_after = build_pending_state([signed], no_repeat, event2, cache2)
    assert "gwangju_us_cob_signed" in state_after["sent_event_keys"]
    assert verified_briefing_item(state_after) is None
    print("self_test=ok checks=baseline+distinct_milestones+cross_run_corroboration+delivery_gate")


def run_check():
    for path in (ALERT_PATH, STATUS_PATH, ERROR_PATH, PENDING_STATE_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()

    state = load_state()
    items, errors = collect_items()
    selected, candidates = select_alerts(items, state)
    us_selected, us_cache = select_us_milestone_alerts(items, state)
    intake = verified_briefing_item(state)
    if intake is not None:
        us_selected.insert(0, intake)
    # Structured military milestones are separate from generic newspaper
    # headlines.  Event keys persist only after Telegram confirms delivery.
    selected = us_selected + selected

    if selected:
        ALERT_PATH.write_text(build_alert(selected), encoding="utf-8")

    pending = build_pending_state(items, state, selected, us_cache)
    PENDING_STATE_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_status(len(items), candidates, selected, errors)
    print(f"collected={len(items)} candidates={len(candidates)} alerts={len(selected)} errors={len(errors)}")
    print(f"gwangju_us_milestones={len(us_selected)} pending_evidence={len(us_cache)} last_scan={pending['last_scan_kst']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["check", "self-test"], default="check")
    args = parser.parse_args()
    if args.mode == "self-test":
        self_test()
    else:
        run_check()


if __name__ == "__main__":
    main()
