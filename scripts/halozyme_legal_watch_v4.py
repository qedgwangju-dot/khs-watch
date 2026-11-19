from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import html
import json
import datetime as dt
import urllib.request
from zoneinfo import ZoneInfo
import os
import re
import time
import urllib.parse

import halozyme_legal_watch_v3 as v3

base = v3.base
_original_get_case = base.get_case
_original_rss = base.rss

ALTEOGEN_IR_LIST_URL = "https://alteogen.com/kr/sub/ir/information.php?bid=2"
ALTEOGEN_IR_CURRENT_URL = "https://alteogen.com/kr/sub/ir/information.php?bid=2&idx=374&mode=view&page=1"
OFFICIAL_IR_HTTP_TIMEOUT = 7
OFFICIAL_IR_HTTP_ATTEMPTS = 2
OFFICIAL_IR_RETRY_BACKOFF_SECONDS = 0.5
OFFICIAL_IR_WORKERS = 4
OFFICIAL_IR_MAX_ARTICLES = 12


def _official_ir_fetch(url: str) -> str:
    last_exc: Exception | None = None
    for attempt in range(1, OFFICIAL_IR_HTTP_ATTEMPTS + 1):
        try:
            return base.fetch(url, timeout=OFFICIAL_IR_HTTP_TIMEOUT)
        except Exception as exc:
            last_exc = exc
            if attempt < OFFICIAL_IR_HTTP_ATTEMPTS:
                time.sleep(OFFICIAL_IR_RETRY_BACKOFF_SECONDS * attempt)
    assert last_exc is not None
    raise last_exc
CURRENT_PORTFOLIO_SCORECARD = {
    "url": ALTEOGEN_IR_CURRENT_URL,
    "title": "알테오젠 파트너 MSD, 할로자임 MDASE 여섯 번째·일곱 번째 특허 무효화 판정",
    "score": {
        "total": 14,
        "won": 7,
        "pending": 7,
        "oral_date": "2026-07-23",
        "patents": ["12,049,652", "12,104,185"],
    },
}

# 동일 사건당 4개 변형 검색을 직렬 반복하던 구조를 제거한다.
# 각 알려진 PGR·IPR은 정확 사건번호 검색 1개로 전수 추적하고,
# 최종결정·국장 재검토·재심·항소·민사소송·한국어 보도는 별도 광역 검색축으로 유지한다.
base.SEARCHES = [
    '"Halozyme" "Merck" PTAB PGR',
    '"Halozyme" "Merck" "Final Written Decision"',
    '"Halozyme" "Merck" "Director Review" PTAB',
    '"Halozyme" "Merck" rehearing PTAB',
    '"Halozyme" "Merck" "Federal Circuit" patent',
    '"Halozyme" "Merck" MDASE patent',
    '"Halozyme" "Merck" modified PH20 patent',
    '"2:25-cv-03179" Halozyme Merck',
    '할로자임 MSD 특허 무효 PGR',
    '할로자임 MDASE 특허 PTAB',
    '알테오젠 할로자임 특허 분쟁 MSD',
    'Halozyme MSD 특허심판원 무효',
    '"알테오젠 파트너 MSD" 할로자임 PH20 특허 특허성 없음',
    '"할로자임 PH20" MSD 특허성 없음',
    '"Halozyme" "Merck" Munich preliminary injunction overturned',
]
for case in base.KNOWN_CASES:
    base.SEARCHES.append(f'"{case}" Halozyme Merck')
for case in ("PGR2025-00042", "PGR2025-00050", "PGR2025-00053"):
    base.SEARCHES.append(f'"{case}" "Final Written Decision" Halozyme')
# Keep the established 40-query budget; the existing PH20 and Korean axes
# already cover the other variants of this technical subject.
base.SEARCHES.append('"Halozyme" "Merck" "written description" "challenged claims" PTAB')

base.SEARCHES.extend([
    '"C/09/695432" Halozyme Merck Keytruda SC',
    '"EP 2 797 622" Halozyme Merck Keytruda SC appeal',
    '"EP 3 130 347" Halozyme Merck Keytruda SC UK',
])


_CURRENT_BATCH_SOURCE = "http://the-biz.co.kr/news/articleView.html?idxno=728392"
ALTEOGEN_IR_INDEX = "https://www.alteogen.com/kr/sub/ir/information.php?bid=2"

# 2026-10-03 사용자 제공 PTAB 결정문 첫 페이지를 기준으로 사건번호·특허번호·결정일·
# "Final Written Decision Determining All Challenged Claims Unpatentable" 문구를 직접 대조했다.
# 사건 자체는 USPTO 공개 P-TACTS 사건 페이지로 연결하고, 검색색인 지연과 무관하게
# 이번 두 최종결정은 한 번만 백필하여 즉시 알림·상태·타임라인에 반영한다.
PTACTS_CASE_URLS = {
    "PGR2025-00042": "https://ptacts.uspto.gov/ptacts/public-informations/petitions/1557626",
    "PGR2025-00046": "https://ptacts.uspto.gov/ptacts/public-informations/petitions/1557766",
    "PGR2025-00052": "https://ptacts.uspto.gov/ptacts/public-informations/petitions/1557959",
}

VERIFIED_CURRENT_DECISIONS = [
    {
        "engine": "USPTO/PTAB 공식 결정문",
        "title": "PGR2025-00052 Final Written Decision — all challenged claims unpatentable",
        "url": PTACTS_CASE_URLS["PGR2025-00052"],
        "description": (
            "PGR2025-00052 Patent 12,264,345 B1 Paper 89 Date October 1, 2026. "
            "JUDGMENT Final Written Decision Determining All Challenged Claims Unpatentable "
            "35 U.S.C. § 328(a). Halozyme Merck."
        ),
        "published": "Thu, 01 Oct 2026 00:00:00 GMT",
    },
    {
        "engine": "USPTO/PTAB 공식 결정문",
        "title": "PGR2025-00046 Final Written Decision — all challenged claims unpatentable",
        "url": PTACTS_CASE_URLS["PGR2025-00046"],
        "description": (
            "PGR2025-00046 Patent 12,091,692 B2 Paper 96 Date October 2, 2026. "
            "JUDGMENT Final Written Decision Determining All Challenged Claims Unpatentable "
            "35 U.S.C. § 328(a). Halozyme Merck."
        ),
        "published": "Fri, 02 Oct 2026 00:00:00 GMT",
    },
]

PTAB_VERIFIED_PORTFOLIO_SCORECARD = {
    "url": PTACTS_CASE_URLS["PGR2025-00052"],
    "source_urls": [PTACTS_CASE_URLS["PGR2025-00052"], PTACTS_CASE_URLS["PGR2025-00046"]],
    "source_kind": "ptab_verified_rollup",
    "title": "PTAB 신규 최종서면결정 2건 반영 — 누적 9/14",
    "score": {
        "total": 14,
        "won": 9,
        "pending": 5,
        "oral_date": "2026-07-23",
        "patents": ["12,264,345", "12,091,692"],
    },
}

DUTCH_VRO_CASE = "NL-VRO-C09-695432"
GERMAN_EP622_CASE = "DE-EP622-KEYTRUDA"
HALOZYME_GERMAN_REVERSAL_URL = (
    "https://ir.halozyme.com/news/news-details/2026/"
    "Halozyme-Provides-Update-on-German-Preliminary-Injunction-Hearing/default.aspx"
)
PGR_LAST_TWO_NEWS_URL = "https://www.thebionews.net/news/articleView.html?idxno=30460"
PGR_LAST_TWO_CORROBORATION_URL = (
    "https://www4.edaily.co.kr/News/Read?mediaCodeNo=257&newsId=02368166645647360"
)
PGR_LAST_TWO_FINAL_CASES = {
    "PGR2025-00050": "12,077,791",
    "PGR2025-00053": "12,195,773",
}
PGR_LAST_TWO_SCORE = {"total": 14, "won": 14, "pending": 0}
UK_EP347_CASE = "UK-EP347-KEYTRUDA"
DUTCH_VRO_PATENT = "EP 2,797,622"
HALOZYME_DUTCH_INJUNCTION_URL = (
    "https://ir.halozyme.com/news/news-details/2026/"
    "Halozyme-Wins-Injunction-Stopping-Manufacture-and-Sale-of-Mercks-Keytruda-SC-in-Multiple-European-Markets/default.aspx"
)
REUTERS_DUTCH_INJUNCTION_URL = (
    "https://www.reuters.com/legal/litigation/"
    "halozyme-wins-court-order-block-mercks-injected-keytruda-select-european-markets-2026-10-07/"
)
DUTCH_JULY_RULING_URL = (
    "https://www.uitspraken.nl/uitspraak/rechtbank-den-haag/civiel-recht/"
    "intellectueel-eigendomsrecht/kort-geding/ecli-nl-rbdha-2026-18266"
)
MERCK_2Q26_DISCLOSURES_URL = (
    "https://www.merck.com/wp-content/uploads/sites/124/2026/08/2Q26-Merck-Other-Financial-Disclosures.pdf"
)
MERCK_2Q26_10Q_URL = "https://www.merck.com/wp-content/uploads/sites/124/2026/08/MRK-06.30.2026-10Q-FINAL.pdf"
UK_EP347_COURT_URL = "https://www.bailii.org/ew/cases/EWHC/Patents/2026/1838.html"

VERIFIED_EUROPE_DECISIONS = [
    {
        "engine": "Halozyme 공식 IR + Reuters 교차확인",
        "title": "Dutch court finds EP622 valid and Keytruda SC infringing; injunction in eight European markets",
        "url": HALOZYME_DUTCH_INJUNCTION_URL,
        "description": (
            "Halozyme Merck MSD Keytruda SC C/09/695432 Dutch Netherlands The Hague EP 2 797 622 EP622. "
            "October 7 2026 specialized Dutch patent court found Merck infringing Halozyme MDASE EP622, "
            "rejected invalidity arguments and granted injunction stopping manufacture, having manufactured, "
            "offering, placing on the market, using, importing or stocking Keytruda SC in Belgium Denmark France "
            "Ireland Italy Sweden Switzerland Netherlands; also forbids MSD BV facilitating affiliates through "
            "the European Marketing Authorization."
        ),
        "published": "Wed, 07 Oct 2026 00:00:00 GMT",
    },
]

# The 2026-10-15 Paper 100 cover pages were supplied by the user and matched
# by docket/patent to public USPTO records and the dated secondary report.
# Do not claim the complete official PDF body was accessed by this collector.
OCT15_PTACTS_CASES = {
    "PGR2025-00024": "https://ptacts.uspto.gov/ptacts/public-informations/petitions/1557268",
    "PGR2025-00030": "https://ptacts.uspto.gov/ptacts/public-informations/petitions/1557365",
}
OCT15_VERIFIED_DECISIONS = [
    {
        "engine": "PTAB Paper 100 표지 + 사건기록·보도 교차확인",
        "title": f"{case} Halozyme Merck Final Written Decision Determining All Challenged Claims Unpatentable",
        "url": OCT15_PTACTS_CASES[case],
        "description": (
            f"Halozyme Merck {case} Patent {patent} Paper 100 October 15 2026 "
            "JUDGMENT Final Written Decision Determining All Challenged Claims Unpatentable "
            "35 U.S.C. 328(a)."
        ),
        "published": "Thu, 15 Oct 2026 12:00:00 GMT",
    }
    for case, patent in (
        ("PGR2025-00024", "12,060,590"),
        ("PGR2025-00030", "12,054,758"),
    )
]

# 2026-11-09 Paper 95 first page supplied by the user (131-page document).
# This is NOT a claim to have downloaded or read the complete USPTO decision.
# Official USPTO records independently tie this case to patent 12,037,618.
NOV9_USER_DOCUMENTED_FWD = [{
    "engine": "사용자 제공 PTAB Paper 95 표지 + USPTO 사건번호·특허번호 교차확인",
    "title": "PGR2025-00042 Halozyme Merck Final Written Decision Determining All Challenged Claims Unpatentable",
    "url": PTACTS_CASE_URLS["PGR2025-00042"],
    "description": (
        "Halozyme Merck PGR2025-00042 Patent 12,037,618 B2 "
        "Paper 95 dated November 9, 2026. "
        "JUDGMENT Final Written Decision Determining All Challenged Claims Unpatentable "
        "35 U.S.C. 328(a). User supplied page 1 of 131; full official PDF not independently retrieved."
    ),
    "published": "Mon, 09 Nov 2026 00:00:00 GMT",
}]
PTAB_NOV9_PORTFOLIO_SCORECARD = {
    "url": PTACTS_CASE_URLS["PGR2025-00042"],
    "source_urls": [PTACTS_CASE_URLS["PGR2025-00042"]],
    "source_kind": "ptab_user_cover_rollup_20261109",
    "title": "PTAB 11월 9일 Paper 95 반영 — 11/14 → 12/14",
    "score": {
        "total": 14,
        "won": 12,
        "pending": 2,
        "oral_date": "2026-07-23",
        "patents": ["12,037,618"],
    },
}


# 2026-11-10 16:27 KST ChosunBiz follow-up after the 2026-11-09
# Paper 95 alert. The user supplied the article URL; its full text was
# independently available through search indexing. This is an editorial
# report, NOT a direct reading of all 131 pages of the official FWD.
NOV10_PGR42_TECHNICAL_ANALYSIS = [{
    "engine": "조선비즈 2026-11-10 기사 검색색인 + PTAB 사건·이전 심판 개시 결정 대조",
    "title": (
        "PGR2025-00042 Halozyme Merck Final Written Decision technical rationale: "
        "30 challenged claims, PH20 residue 309, written description, obviousness"
    ),
    "url": "https://biz.chosun.com/science-chosun/bio/2026/11/10/EBGMPDET6ZD57JCLBVLAN7PTYI/",
    "description": (
        "PGR2025-00042 Patent 12,037,618, Paper 95 Final Written Decision. "
        "Of 40 originally challenged claims, Halozyme disclaimed 10 claims "
        "(3, 4, 6, 34-40); the remaining 30 claims (1, 2, 5, 7-33) were "
        "all determined unpatentable. PH20 amino-acid position 309 variant "
        "with at least 91% sequence identity and multiple additional substitutions. "
        "Written description lacked sufficient support and experimental data "
        "for the immense scope of multiply mutated enzymes. The obviousness "
        "ground was not accepted; the outcome rests on written description "
        "and sufficiency grounds. Related cases concerned positions 307 and 317. "
        "This is new explanatory detail, NOT a second final decision."
    ),
    "published": "Tue, 10 Nov 2026 07:27:00 GMT",
}]

# Dated, already-grounded case events survive transient Bing/Google failures.
base.VERIFIED_BACKFILL_ITEMS = (
    list(VERIFIED_CURRENT_DECISIONS)
    + list(VERIFIED_EUROPE_DECISIONS)
    + list(OCT15_VERIFIED_DECISIONS)
    + list(NOV9_USER_DOCUMENTED_FWD)
    + list(NOV10_PGR42_TECHNICAL_ANALYSIS)
)
PTAB_OCT15_PORTFOLIO_SCORECARD = {
    "url": OCT15_PTACTS_CASES["PGR2025-00024"],
    "source_urls": list(OCT15_PTACTS_CASES.values()),
    "source_kind": "ptab_verified_rollup_20261015",
    "title": "PTAB 10월 15일 최종서면결정 2건 반영 — 누적 11/14",
    "score": {
        "total": 14,
        "won": 11,
        "pending": 3,
        "oral_date": "2026-07-23",
        "patents": ["12,060,590", "12,054,758"],
    },
}


def _strip_tags(value: str) -> str:
    import html as _html
    value = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", value)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", _html.unescape(value)).strip()


def _alteogen_official_portfolio_items() -> list[dict]:
    try:
        page = _official_ir_fetch(ALTEOGEN_IR_INDEX)
    except Exception:
        return []

    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()
    for match in re.finditer(r'(?is)<a\b[^>]*href=["\']([^"\']*information\.php\?[^"\']*idx=\d+[^"\']*)["\'][^>]*>(.*?)</a>', page):
        href = match.group(1).replace("&amp;", "&")
        title = _strip_tags(match.group(2))
        url = urllib.parse.urljoin(ALTEOGEN_IR_INDEX, href)
        if url in seen:
            continue
        seen.add(url)
        low_title = title.lower()
        if not any(k in low_title for k in ("할로자임", "halozyme", "mdase", "특허")):
            continue
        candidates.append((title, url))
        if len(candidates) >= OFFICIAL_IR_MAX_ARTICLES:
            break

    if not candidates:
        return []

    def load(candidate: tuple[str, str]) -> dict | None:
        title, url = candidate
        try:
            article = _strip_tags(_official_ir_fetch(url))
        except Exception:
            article = title
        low = article.lower()
        if not ("pgr" in low and ("할로자임" in low or "halozyme" in low or "mdase" in low)):
            return None
        return {
            "engine": "알테오젠 공식 IR",
            "title": title or "알테오젠 Halozyme 특허분쟁 누적 현황",
            "url": url,
            "description": article[:12000],
            "published": "",
        }

    out: list[dict] = []
    workers = max(1, min(OFFICIAL_IR_WORKERS, len(candidates)))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="alteogen-ir") as pool:
        futures = [pool.submit(load, candidate) for candidate in candidates]
        for future in as_completed(futures):
            try:
                item = future.result()
            except Exception:
                item = None
            if item:
                out.append(item)
    return out


_official_portfolio_cache: list[dict] | None = None


def rss(query: str, engine: str) -> list[dict]:
    out = _original_rss(query, engine)
    if engine == "Bing 웹" and query == base.SEARCHES[0]:
        out.extend([
            {
                "engine": "현재 사건 교차검증",
                "title": "PGR2025-00033 Halozyme Merck Final Written Decision all challenged claims unpatentable",
                "url": _CURRENT_BATCH_SOURCE,
                "description": "PGR2025-00033 12,049,652 PH20 특허 심판 대상 청구항 특허성 없음",
                "published": "Fri, 25 Sep 2026 12:00:00 GMT",
            },
            {
                "engine": "현재 사건 교차검증",
                "title": "PGR2025-00039 Halozyme Merck Final Written Decision all challenged claims unpatentable",
                "url": _CURRENT_BATCH_SOURCE + "#pgr2025-00039",
                "description": "PGR2025-00039 12,104,185 PH20 특허 심판 대상 청구항 특허성 없음",
                "published": "Fri, 25 Sep 2026 12:00:00 GMT",
            },
        ])
        out.extend(VERIFIED_CURRENT_DECISIONS)
        out.extend(VERIFIED_EUROPE_DECISIONS)
    global _official_portfolio_cache
    if engine == "Bing 웹" and query == base.SEARCHES[0]:
        if _official_portfolio_cache is None:
            _official_portfolio_cache = _alteogen_official_portfolio_items()
        out.extend(_official_portfolio_cache)
    return out


base.rss = rss

FINAL_UNPATENTABLE_TERMS = (
    "all challenged claims unpatentable",
    "determining all challenged claims unpatentable",
    "held all challenged claims unpatentable",
    "found all challenged claims unpatentable",
    "all challenged claims invalid",
    "청구항 전부 무효",
    "심판 대상 청구항 전부 무효",
    "전부 무효",
    "특허성 없음",
    "특허 받을 수 없음",
)

CURRENT_CONFIRMED_UNPATENTABLE = {
    "PGR2025-00042",
    "PGR2025-00033",
    "PGR2025-00039",
    "PGR2025-00046",
    "PGR2025-00052",
    "PGR2025-00024",
    "PGR2025-00030",
}

CASE_TIMELINES = {
    "PGR2025-00042": (
        ("2025-04-15", "PGR 청구"),
        ("2025-11-13", "심판 개시"),
        ("2026-11-09", "최종서면결정"),
    ),
    "PGR2025-00024": (
        ("2025-02-21", "PGR 청구"),
        ("2025-10-16", "심판 개시"),
        ("2026-07-23", "공동 구술심리"),
        ("2026-10-15", "최종서면결정"),
    ),
    "PGR2025-00030": (
        ("2025-02-04", "PGR 청구"),
        ("2025-10-16", "심판 개시"),
        ("2026-07-23", "공동 구술심리"),
        ("2026-10-15", "최종서면결정"),
    ),
    "PGR2025-00033": (
        ("2025-03-07", "PGR 청구"),
        ("2025-10-01", "심판 개시"),
        ("2026-07-23", "공동 구술심리"),
        ("2026-09-25", "최종서면결정"),
    ),
    "PGR2025-00039": (
        ("2025-03-28", "PGR 청구"),
        ("2025-10-01", "심판 개시"),
        ("2026-07-23", "공동 구술심리"),
        ("2026-09-25", "최종서면결정"),
    ),
    "PGR2025-00046": (
        ("2025-04-29", "PGR 청구"),
        ("2025-10-10", "심판 개시"),
        ("2026-07-23", "공동 구술심리"),
        ("2026-10-02", "최종서면결정"),
    ),
    "PGR2025-00052": (
        ("2025-06-27", "PGR 청구"),
        ("2025-10-16", "심판 개시"),
        ("2026-07-23", "공동 구술심리"),
        ("2026-10-01", "최종서면결정"),
    ),
    DUTCH_VRO_CASE: (
        ("2026-07-03", "별도 가처분 기각 — EP622 유효성·침해 본안 판단 아님"),
        ("2026-07-31", "VRO 본안 구술심리"),
        ("2026-10-07", "VRO 본안 — EP622 유효·Keytruda SC 침해·8개 유럽시장 금지명령"),
    ),
    GERMAN_EP622_CASE: (
        ("2025-12-04", "독일 Keytruda SC 판매금지 가처분"),
        ("2026-11-19", "독일 가처분 항소심 예정"),
    ),
    UK_EP347_CASE: (
        ("2026-07-20", "영국 EP347 절차판단 EWHC 1838"),
        ("2026-11-23", "영국 법원 7월 결정의 심리 가능 기간 시작(이전 일정, 실제 개시 아님)"),
        ("2026-11-30", "MSD 11월 4일 미국 공시 기준 영국 EP347 본안 심리 시작 예정"),
    ),
}


TIMELINE_EVENT_LABELS = {
    "institution": "심판 개시",
    "final_unpatentable": "최종서면결정",
    "final_decision": "최종서면결정",
    "director_review": "국장 재검토",
    "rehearing": "PTAB 재심",
    "appeal": "연방순회항소법원 항소",
    "termination": "종결·합의",
    "disclaimer": "청구항 포기",
    "nl_injunction": "VRO 본안 — EP622 유효·Keytruda SC 침해·8개 유럽시장 금지명령",
    "nl_appeal": "네덜란드 항소 제기",
    "nl_stay": "네덜란드 집행정지 절차 변화",
    "nl_stay_request": "네덜란드 집행정지 신청",
    "nl_stay_decision": "네덜란드 집행정지 인용·기각 판단",
    "nl_appeal_decision": "네덜란드 항소심 결정",
    "de_appeal_decision": "독일 가처분 항소심 결정",
    "uk_judgment": "영국 EP347 본안 판단",
}

_successful_timeline_events: list[dict] = []
_pending_timeline_event: dict | None = None


def _event_date(item: dict) -> str:
    # A dated judicial event must never be silently replaced with a later article date.
    # Event-date metadata takes precedence; older feeds without it retain legacy parsing.
    explicit = str(item.get("event_date") or item.get("decision_date") or "").strip()
    if explicit:
        try:
            return dt.date.fromisoformat(explicit).isoformat()
        except ValueError:
            return ""  # Invalid judicial date is not permission to infer one.
    published = str(item.get("published") or "").strip()
    if published:
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(published).date().isoformat()
        except Exception:
            pass
    blob = " ".join(str(item.get(key) or "") for key in ("title", "description"))
    m = re.search(r"\b(20\d{2})[-./년 ](\d{1,2})[-./월 ](\d{1,2})(?:일)?\b", blob)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return ""


def _timeline_event(case: str, kind: str, item: dict) -> dict | None:
    if not (case.startswith(("PGR", "IPR")) or case in CASE_TIMELINES):
        return None
    label = TIMELINE_EVENT_LABELS.get(kind)
    if not label:
        return None
    return {
        "case": case,
        "date": _event_date(item),
        "kind": kind,
        "label": label,
    }


def _persisted_timeline_rows(case: str) -> list[dict]:
    try:
        state = json.loads(base.STATE.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows = (state.get("case_event_timelines") or {}).get(case) or []
    out: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        copy = dict(row)
        if case == DUTCH_VRO_CASE and copy.get("label") == "VRO 본안 — EP622 유효·침해·8개 유럽시장 금지명령":
            copy["label"] = TIMELINE_EVENT_LABELS["nl_injunction"]
        if case in OCT15_PTACTS_CASES and str(copy.get("label") or "").startswith("Paper 100 최종서면결정"):
            copy["label"] = "최종서면결정"
        if case == "PGR2025-00042" and str(copy.get("label") or "").startswith("Paper 95 최종서면결정"):
            copy["label"] = "최종서면결정"
        out.append(copy)
    return out


def _merged_case_timelines(state: dict) -> dict:
    timelines = dict(state.get("case_event_timelines") or {})

    # 과거 버전의 표현 차이로 같은 날짜·같은 사건이 두 줄이 되는 것을 정리한다.
    old_nl_label = "VRO 본안 — EP622 유효·침해·8개 유럽시장 금지명령"
    canonical_nl_label = TIMELINE_EVENT_LABELS["nl_injunction"]
    for case, rows in list(timelines.items()):
        cleaned: list[dict] = []
        seen_rows: set[tuple[str, str]] = set()
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            date = str(row.get("date") or "")
            label = str(row.get("label") or "")
            if case == DUTCH_VRO_CASE and label == old_nl_label:
                label = canonical_nl_label
            if case in OCT15_PTACTS_CASES and label.startswith("Paper 100 최종서면결정"):
                label = "최종서면결정"
            if case == "PGR2025-00042" and label.startswith("Paper 95 최종서면결정"):
                label = "최종서면결정"
            key = (date, label)
            if key in seen_rows:
                continue
            seen_rows.add(key)
            cleaned.append({**row, "date": date, "label": label})
        timelines[case] = cleaned

    def add(case: str, date: str, label: str, kind: str = "") -> None:
        rows = [row for row in (timelines.get(case) or []) if isinstance(row, dict)]
        key = (date, label)
        if key not in {(str(row.get("date") or ""), str(row.get("label") or "")) for row in rows}:
            rows.append({"date": date, "kind": kind, "label": label})
        rows.sort(key=lambda row: (str(row.get("date") or "9999-99-99"), str(row.get("label") or "")))
        timelines[case] = rows[-30:]

    for case, rows in CASE_TIMELINES.items():
        for date, label in rows:
            add(case, date, label)

    for event in _successful_timeline_events:
        add(
            str(event.get("case") or ""),
            str(event.get("date") or ""),
            str(event.get("label") or ""),
            str(event.get("kind") or ""),
        )
    return timelines

FINAL_DECISION_TERMS = (
    "final written decision",
    "status final written decision",
    "최종서면결정",
    "최종 서면 결정",
    "최종 결정",
)


CURRENT_POST_FWD_TIMELINE_CASES = {
    "PGR2025-00042",
    "PGR2025-00033",
    "PGR2025-00039",
    "PGR2025-00046",
    "PGR2025-00052",
}



def decision_rationale_material(text: str, case: str) -> bool:
    """Require multiple independent technical/legal facts, not a restated FWD headline."""
    if not case.startswith(("PGR", "IPR")):
        return False
    low = text.lower()
    if not any(term in low for term in ("final written decision", "최종서면결정", "특허성 부정")):
        return False
    evidence = (
        bool(re.search(r"\b\d+\s+(?:challenged\s+)?claims?\b|청구항\s*\d+\s*개", low)),
        bool(re.search(r"(?:amino[- ]acid|residue|position)\s*\d{2,4}|아미노산\s*\d{2,4}\s*번", low)),
        any(term in low for term in ("written description", "명세서", "실험 근거", "enablement")),
        any(term in low for term in ("obviousness", "자명성", "not accepted", "받아들이지 않았다")),
        any(term in low for term in ("disclaimed", "claims withdrawn", "청구항 포기")),
    )
    return sum(evidence) >= 3


def decision_rationale_preview(item: dict) -> list[str]:
    """Only show facts present in the source item; never invent a claim count."""
    body = " ".join(str(item.get(k) or "") for k in ("title", "description"))
    low = body.lower()
    facts: list[str] = []
    numbers = re.search(r"(\d+)\s+(?:challenged\s+)?claims?\b", low)
    if numbers:
        facts.append(f"심판 대상 청구항 {int(numbers.group(1))}개 관련 상세 분석")
    position = re.search(r"(?:amino[- ]acid\s+)?(?:residue|position)\s*(\d{2,4})", low)
    if position:
        facts.append(f"PH20 아미노산 {position.group(1)}번 변형")
    if "written description" in low or "명세서" in low:
        facts.append("명세서 뒷받침 범위에 대한 법적 쟁점")
    if "obviousness" in low or "자명성" in low:
        facts.append("기존 기술로부터의 자명성 판단과 다른 무효 사유를 구분")
    if "disclaimed" in low or "청구항 포기" in low:
        facts.append("심판 전 자발적 청구항 포기 여부")
    return facts[:5]

def classify(text: str, case: str) -> str:
    low = text.lower()
    if case.startswith("HALOZYME-PGR-PORTFOLIO-"):
        return "portfolio_update"
    if case == base.DISTRICT_CASE:
        return "district_order"

    if case == DUTCH_VRO_CASE:
        # 항소 검토 발언과 실제 항소장 제출, 항소심 선고는 서로 다른 사건이다.
        if any(term in low for term in (
            "appeal court ruled", "court of appeal ruled", "appeals court held",
            "appeal judgment issued", "appeal decision published",
            "gerechtshof heeft geoordeeld", "항소심 선고", "항소심 판결",
        )):
            return "nl_appeal_decision"
        # 신청서 접수와 법원의 집행정지 인용·기각은 각각 다른 타임라인 이벤트다.
        if any(term in low for term in (
            "court granted a stay", "court denied a stay", "stay order issued",
            "schorsing toegewezen", "schorsing afgewezen",
            "집행정지 인용", "집행정지 기각", "집행정지 결정",
        )):
            return "nl_stay_decision"
        if any(term in low for term in (
            "motion for stay filed", "filed a request to suspend",
            "requested a stay of injunction", "schorsing verzocht", "집행정지 신청",
        )):
            return "nl_stay_request"
        if any(term in low for term in (
            "notice of appeal filed", "filed an appeal", "has filed an appeal",
            "has appealed", "appeal was lodged", "hoger beroep ingesteld",
            "항소장을 제출", "항소를 제기",
        )):
            return "nl_appeal"
        has_infringement = any(term in low for term in ("found merck to be infringing", "found merck infringing", "infringes", "infringement"))
        has_injunction = any(term in low for term in ("granted injunction", "injunction stopping", "ordered merck", "refrain from manufacturing", "halt", "block merck"))
        has_validity = any(term in low for term in ("rejected merck's arguments that ep622 patent is invalid", "rejected invalidity arguments", "recognized the validity", "ep622 is valid", "patent is valid"))
        if has_infringement and has_injunction and has_validity:
            return "nl_injunction"
        return ""

    if case == GERMAN_EP622_CASE:
        reversed_injunction = (
            any(term in low for term in (
                "overturned", "reversed", "lifted", "set aside", "vacated",
                "취소", "뒤집", "해제", "번복",
            ))
            and any(term in low for term in (
                "preliminary injunction", "distribution ban", "sale ban",
                "가처분", "판매금지", "판매 금지",
            ))
            and any(term in low for term in (
                "higher regional court", "appeals court", "appeal court",
                "oberlandesgericht", "고등법원", "항소심",
            ))
        )
        if reversed_injunction or any(term in low for term in (
            "appeal court ruled", "appeals court held", "appeal judgment issued",
            "appeal decision published", "oberlandesgericht ruled", "oberlandesgericht decided",
            "항소심 선고", "항소심 판결",
        )):
            return "de_appeal_decision"
        return ""

    if case == UK_EP347_CASE:
        # 영국 7월 EWHC 1838은 증거공개 절차판결이므로 본안결정과 구분한다.
        court_result = (
            "trial judgment issued", "trial judgment handed down",
            "court held ep347 valid", "court held ep347 invalid",
            "court found ep347 infringed", "patents court ruled on ep347 validity",
            "ep347 본안 판결", "ep347 무효 판결", "ep347 침해 인정",
        )
        if any(term in low for term in ("ep347", "ep 347", "ep 3 130 347", "ep3130347")) and any(term in low for term in court_result):
            return "uk_judgment"
        return ""

    # 최종서면결정 이후의 재검토·재심·항소 서류는 본문에 기존 FWD 문구를
    # 반복 인용하는 경우가 많다. 최신 판세 사건은 후속 절차를 FWD보다
    # 먼저 판정해 타임라인 변화가 기존 최종결정으로 오분류되어 누락되지 않게 한다.
    if case in CURRENT_POST_FWD_TIMELINE_CASES:
        for key, terms in (
            ("director_review", ("director review", "director-review", "국장 재검토")),
            ("rehearing", ("request for rehearing", "rehearing", "재심")),
            ("appeal", ("notice of appeal", "federal circuit", "court of appeals", "연방순회항소법원", "항소")),
        ):
            if any(term in low for term in terms):
                return key

    # Nov 18 final decisions are one legal milestone each; don't split their
    # initial claim-by-claim reporting into duplicate "rationale" alerts.
    if case in PGR_LAST_TWO_FINAL_CASES and any(term in low for term in (
        "all challenged claims unpatentable",
        "determining all challenged claims unpatentable",
        "심판 대상 청구항 전부의 특허성을 부정",
        "심판 대상 청구항 전부 특허성 부정",
    )):
        return "final_unpatentable"

    # An explanatory follow-up can carry NEW claim counts and reasoning while
    # the case's final-decision status stays unchanged. Use its own event key.
    if decision_rationale_material(text, case):
        return "decision_rationale"

    if any(term in low for term in FINAL_UNPATENTABLE_TERMS):
        return "final_unpatentable"

    if any(term in low for term in FINAL_DECISION_TERMS):
        if case in CURRENT_CONFIRMED_UNPATENTABLE:
            return "final_unpatentable"
        return "final_decision"

    # 최종결정 외 절차는 기존 분류 규칙을 유지한다.
    for key, terms in base.EVENTS:
        if key in ("district_order", "final_unpatentable"):
            continue
        if any(t.lower() in low for t in terms):
            return key
    return ""


def timeline_line(case: str, kind: str, item: dict) -> str:
    if case.startswith(("PGR", "IPR")) or case in CASE_TIMELINES:
        rows: list[tuple[str, str]] = list(CASE_TIMELINES.get(case) or ())
        for row in _persisted_timeline_rows(case):
            rows.append((str(row.get("date") or ""), str(row.get("label") or "")))
        for event in _successful_timeline_events:
            if event.get("case") == case:
                rows.append((str(event.get("date") or ""), str(event.get("label") or "")))
        current = _timeline_event(case, kind, item)
        if current:
            rows.append((str(current.get("date") or ""), str(current.get("label") or "")))

        # Keep the underlying historical state intact, but do not show a
        # scheduled hearing as still pending on a day with a confirmed ruling.
        if case == GERMAN_EP622_CASE:
            completed_dates = {
                date for date, label in rows
                if "가처분 항소심" in label and "취소" in label
            }
            rows = [
                (date, label) for date, label in rows
                if not ("예정" in label and date in completed_dates)
            ]

        unique: dict[tuple[str, str], tuple[str, str]] = {}
        for date, label in rows:
            if label:
                unique.setdefault((date, label), (date, label))
        ordered = sorted(unique.values(), key=lambda row: (row[0] or "9999-99-99", row[1]))
        if ordered:
            return " → ".join(
                f"{date} {label}" if date else f"날짜 확인 필요 · {label}"
                for date, label in ordered
            )

    published = str(item.get("published") or "").strip()
    event_label = {
        "district_order": "연방법원 절차 변화",
    }.get(kind, TIMELINE_EVENT_LABELS.get(kind, "새 절차 변화"))
    if published:
        try:
            from email.utils import parsedate_to_datetime
            stamp = parsedate_to_datetime(published)
            return f"{stamp.date().isoformat()} {event_label}"
        except Exception:
            pass
    return f"날짜 확인 필요 · {event_label}"


def _korean_date_label(date_text: str) -> str:
    m = re.fullmatch(r"(20\d{2})-(\d{2})-(\d{2})", date_text.strip())
    if not m:
        return html.escape(date_text)
    return f"{int(m.group(1))}년 {int(m.group(2))}월 {int(m.group(3))}일"


def timeline_html(case: str, kind: str, item: dict) -> str:
    rows: list[str] = []
    for segment in timeline_line(case, kind, item).split(" → "):
        segment = segment.strip()
        m = re.match(r"^(20\d{2}-\d{2}-\d{2})\s+(.+)$", segment)
        if m:
            rows.append(
                f"• <b>{_korean_date_label(m.group(1))}</b> {html.escape(m.group(2))}"
            )
        else:
            rows.append(f"• {html.escape(segment)}")
    # An explicitly verified event date and the publication date are different
    # clocks. Disclose both when they differ, without guessing release hours.
    explicit = str(item.get("event_date") or item.get("decision_date") or "").strip()
    published = str(item.get("published") or "").strip()
    if explicit and published:
        try:
            from email.utils import parsedate_to_datetime
            publication_day = parsedate_to_datetime(published).date().isoformat()
        except (TypeError, ValueError, IndexError):
            publication_day = ""
        if publication_day and publication_day != explicit:
            rows.append(
                f"• <b>{_korean_date_label(publication_day)}</b> 자료 게시일 "
                f"(사건 발생일과 구분)"
            )
    return "\n".join(rows)


_original_alert = base.alert


def alert(case: str, patent: str, kind: str, item: dict) -> str:
    global _pending_timeline_event
    _pending_timeline_event = None
    if kind == "portfolio_update":
        m = re.search(r"(\d+)OF(\d+)$", case)
        decided = int(m.group(1)) if m else 0
        total = int(m.group(2)) if m else 0
        remaining = max(0, total - decided)
        url = html.escape(item["url"], quote=True)
        return (
            "<b>[바이오 감시] Halozyme 특허분쟁 누적 판세 업데이트</b>\n\n"
            f"<b>MSD PGR {total}건 중 {decided}건에서 심판 대상 청구항 특허성 부정</b>\n\n"
            "- <b>타임라인:</b>\n"
            "• <b>2026년 7월 23일</b> 잔여 사건 포함 구술심리\n"
            "• <b>2026년 9월 25일</b> PGR2025-00033·00039 최종서면결정\n"
            "• <b>2026년 9월 28일</b> 알테오젠 공식 IR 누적 판세 확인\n"
            f"- <b>현재 판세:</b> 최종결정 {decided}건 특허성 부정 · 잔여 {remaining}건 최종결정 대기\n"
            "- <b>알테오젠:</b> 단일 사건 승패가 아니라 Halozyme MDASE 특허군 전체의 방어력이 약해지는 흐름을 보여주는 후속 업데이트입니다. ALT-B4 자체 특허 유효성 판정은 아닙니다.\n"
            "- <b>다음 확인:</b> 잔여 PGR 최종서면결정 → 국장 재검토·재심 → 연방순회항소법원 항소 → 뉴저지·유럽 소송\n"
            "- <b>원문 확인:</b> 알테오젠 공식 IR 본문 직접 확인\n"
            f'- <a href="{url}">원문 뉴스보기</a>'
        )

    _pending_timeline_event = _timeline_event(case, kind, item)

    if kind == "decision_rationale":
        _pending_timeline_event = None  # Not a second court decision/date.
        url = html.escape(item["url"], quote=True)
        if case == "PGR2025-00042":
            return (
                "<b>[바이오 감시] Halozyme PGR2025-00042 판결 근거 추가 확인</b>\n\n"
                "<b>2026년 11월 10일 16:27 공개된 심층 보도</b>\n"
                "- <b>새로 확인된 청구항 범위:</b> MSD는 처음 40개 청구항에 이의를 제기했고, "
                "할로자임이 3·4·6·34~40번 10개를 포기했습니다. 남은 "
                "<b>1·2·5·7~33번, 총 30개</b> 전부 특허성이 부정됐습니다.\n"
                "- <b>기술 쟁점:</b> 인간 히알루로니다제 PH20의 <b>309번 아미노산</b>을 "
                "변형하면서 원형과 <b>91% 이상 서열 유사성</b>을 지닌 변이체까지 "
                "특허 범위를 넓게 주장했습니다.\n"
                "- <b>부정 판단의 직접 원인:</b> 명세서에는 단일 변형 실험 결과가 있었지만 "
                "여러 위치를 동시에 변형한 광범위한 효소 활성까지 뒷받침할 설명·실험이 "
                "충분하지 않았다는 것이 기사에서 설명한 핵심입니다.\n"
                "- <b>자명성과 구분:</b> 기존 기술로부터 쉽게 생각해 낼 수 있다는 "
                "MSD의 자명성 주장은 받아들여지지 않았으며, 명세서의 뒷받침 부족과 "
                "그 주장 범위가 서로 다른 문제입니다.\n"
                "- <b>선행 결정과 비교:</b> PH20 307번·317번 관련 특허에 이어 "
                "309번에서도 과도하게 넓은 변이체 청구 범위가 쟁점이 됐습니다.\n"
                "- <b>누적 상태:</b> PGR <b>12/14건</b>에서 심판 대상 청구항 특허성 부정, "
                "잔여 <b>PGR2025-00050·00053</b>은 결정 대기 중입니다. "
                "11월 19일 전후는 예상 시점이지 확정 결과가 아닙니다.\n"
                "- <b>법적·지역별 제한:</b> 11월 9일 최종서면결정을 다시 내린 사건이 아니며, "
                "미국 특허의 취소 확정이나 유럽 EP622 금지명령 해제가 아닙니다.\n"
                "- <b>근거·검증:</b> 이 기술적 설명은 조선비즈 11월 10일 기사 "
                "(원문 검색색인 열람)와 기존 PTAB 사건 및 이전 심판 개시 기록을 대조한 "
                "2차 자료입니다. Paper 95 최종결정 131쪽 전문을 직접 대조하지는 못했습니다.\n"
                f'- <a href="{url}">조선비즈 상세 분석 원문</a>\n'
                f'- <a href="{html.escape(PTACTS_CASE_URLS["PGR2025-00042"], quote=True)}">'
                "USPTO P-TACTS 원사건 기록</a>"
            )
        preview = decision_rationale_preview(item)
        details = "\n".join("- " + html.escape(fact) for fact in preview)
        return (
            "<b>[바이오 감시] Halozyme PTAB 결정의 기술적 근거 추가 확인</b>\n\n"
            f"- <b>사건:</b> {html.escape(case)} · 미국 특허 {html.escape(patent or '확인 필요')}\n"
            f"{details}\n"
            "- <b>단계:</b> 기존 최종결정에 대한 후속 설명이지 새로운 최종결정·항소 판결은 아닙니다.\n"
            "- <b>근거 수준:</b> 검색으로 확인된 보도 설명이며, 기술·법적 세부사항은 "
            "원문 결정과 대조하기 전까지 확정 판정으로 확대하지 않습니다.\n"
            f'- <a href="{url}">분석 자료 원문 보기</a>'
        )

    if case == "PGR2025-00042" and kind == "final_unpatentable":
        url = html.escape(item["url"], quote=True)
        return (
            "<b>[바이오 감시] MSD·Halozyme 미국 특허심판 신규 승소 — PGR2025-00042</b>\n\n"
            "<b>2026년 11월 9일 · 미국 특허 12,037,618호 · Paper 95</b>\n"
            "- <b>결정:</b> PTAB는 심판 대상 청구항 전부에 특허성이 없다는 최종서면결정을 내렸습니다.\n"
            "- <b>누적 변화:</b> MSD가 제기해 심리가 개시된 PGR 14건 중 "
            "11건 → <b>12건</b>에서 심판 대상 청구항의 특허성이 부정됐으며, "
            "잔여 최종결정은 <b>2건(PGR2025-00050·00053)</b>입니다.\n"
            "- <b>타임라인:</b>\n"
            "• <b>2025년 4월 15일</b> MSD, PGR2025-00042 청구\n"
            "• <b>2025년 11월 13일</b> PTAB 본안 심리 개시\n"
            "• <b>2026년 11월 9일</b> Paper 95 최종서면결정\n"
            "- <b>법적 구분:</b> 심판 대상 청구항에 대한 최종서면결정이지, "
            "미국 특허의 법적 취소 확정이나 항소 종료를 뜻하지 않습니다.\n"
            "- <b>알테오젠 의미:</b> Halozyme MDASE 특허분쟁의 미국 측 방어력은 추가 약화되는 방향입니다. "
            "다만 알테오젠 ALT-B4 자체 특허 유효성 판단은 아니고, 유럽 EP622 금지명령도 그대로 별개입니다.\n"
            "- <b>다음 확인:</b> PGR2025-00050·00053 최종결정, Halozyme 국장 재검토·재심, "
            "미 연방순회항소법원 항소, 뉴저지·유럽 소송을 구분해 추적합니다.\n"
            "- <b>원문 확인 수준:</b> 사용자 제공 PTAB Paper 95 표지(131쪽 중 첫 쪽)와 "
            "USPTO 사건·특허번호를 대조했습니다. Paper 95 본문 전체의 공식 직접 열람은 미완료입니다.\n"
            f'- <a href="{url}">USPTO P-TACTS 사건기록</a>'
        )

    if case in OCT15_PTACTS_CASES and kind == "final_unpatentable":
        patent = base.KNOWN_CASES[case]
        count = 26 if case == "PGR2025-00024" else 27
        url = html.escape(item["url"], quote=True)
        return (
            "<b>[바이오 감시] Halozyme 미국 MDASE PGR 최종서면결정</b>\n\n"
            f"<b>{case} · 미국 특허 {html.escape(patent)}</b>\n"
            f"- <b>타임라인:</b>\n{timeline_html(case, kind, item)}\n"
            f"- <b>결과:</b> 2026년 10월 15일 Paper 100, 심판 대상 청구항 {count}개 전부 특허성 부정.\n"
            "- <b>구분:</b> 미국 PTAB 최종서면결정이며 재검토·항소 가능성이 있습니다. 특허 전체의 확정 취소가 아닙니다.\n"
            "- <b>알테오젠 의미:</b> 미국 MDASE 특허 장벽을 약화시키는 방향이지만 유럽 EP622 금지명령을 자동 해소하지는 않습니다.\n"
            "- <b>다음 확인:</b> 30일 내 국장 재검토·PTAB 재심 신청 여부 → 이후 연방순회항소법원 항소.\n"
            "- <b>출처:</b> 사용자 제공 PTAB 결정문 표지 및 사건번호·특허번호 교차확인\n"
            f'- <a href="{url}">USPTO P-TACTS 사건 확인</a>'
        )

    if case == DUTCH_VRO_CASE and kind == "nl_injunction":
        source_url = html.escape(item["url"], quote=True)
        reuters_url = html.escape(REUTERS_DUTCH_INJUNCTION_URL, quote=True)
        merck_sales_url = html.escape(MERCK_2Q26_DISCLOSURES_URL, quote=True)
        july_url = html.escape(DUTCH_JULY_RULING_URL, quote=True)
        return (
            "<b>[바이오 감시] Halozyme 유럽 특허분쟁 — 판단 하향</b>\n\n"
            "<b>네덜란드 VRO 본안: EP622 유효 + Keytruda SC 침해 인정, 8개 유럽시장 금지명령</b>\n\n"
            f"- <b>사건:</b> C/09/695432 · MDASE {html.escape(DUTCH_VRO_PATENT)}\n"
            f"- <b>타임라인:</b>\n{timeline_html(case, kind, item)}\n"
            "- <b>금지 범위:</b> 벨기에·덴마크·프랑스·아일랜드·이탈리아·스웨덴·스위스·네덜란드에서 제조·위탁제조·판매제안·판매·사용·수입·재고보유를 금지하고, MSD B.V.가 유럽 판매허가를 이용해 계열사 침해를 돕는 것도 금지했습니다.\n"
            "- <b>제외 대상:</b> Keytruda 정맥주사(IV)는 이번 SC 금지명령 대상이 아닙니다.\n"
            "- <b>상대방 입장:</b> Merck는 이번 판결에 동의하지 않는다고 밝혔으며, 법적 대응 검토와 실제 항소장 제출을 구분합니다.\n"
            "- <b>특허 층:</b> 이번 특허는 ENHANZE 핵심특허가 아니라 별도 MDASE EP622이며, 네덜란드 법원 공개자료 기준 2032년 12월 27일까지 존속합니다.\n"
            "- <b>현재 숫자:</b> Merck 공식 2Q26 Keytruda Qlex 매출은 글로벌 US$463M, 미국 US$395M, 미국 외 US$68M입니다. 공개 지역분류상 이번 8개국 직접 판매 노출은 미국 외 US$68M의 일부입니다.\n"
            "- <b>알테오젠 의미:</b> 현재 매출의 즉시 훼손보다 유럽 확장·판매 마일스톤·향후 로열티의 시간표와 법률 할인율 훼손이 더 중요합니다.\n"
            "- <b>반대축:</b> 미국 PTAB에서는 현재 확인 기준 MSD가 14건 중 9건에서 심판대상 청구항 특허성 부정 결정을 확보했습니다. 유럽 패소를 미국 패소로 동일시하면 안 됩니다.\n"
            "- <b>다른 ALT-B4 파트너:</b> GSK·Biogen·Novartis 제품이 자동으로 EP622 침해가 되는 것은 아닙니다. 제품별 제형·PH20 변형·청구항 매핑을 별도로 확인합니다.\n"
            "- <b>다음 확인:</b> 네덜란드 판결문 전체·ECLI 공개 → 항소·집행정지 여부 → <b>2026년 11월 19일</b> 독일 가처분 항소심 → <b>2026년 11월 23일</b> 영국 법원 7월 기록의 심리 가능 기간 시작(이전 일정) → <b>2026년 11월 30일</b> MSD 최신 공시 기준 영국 EP347 심리 시작 예정(실제 개시 확인 전)\n"
            "- <b>원문 상태:</b> 현재 VRO 본안의 유효성·침해·8개국 금지명령은 Halozyme 공식 발표와 Reuters로 교차확인했습니다. 공개 검색에서 본안 판결문 전체 ECLI는 아직 직접 확보하지 못해 구체적 이행기한·벌금·집행정지 효과는 확정하지 않습니다.\n"
            f'- <a href="{source_url}">Halozyme 공식 발표</a>\n'
            f'- <a href="{reuters_url}">Reuters 보도</a>\n'
            f'- <a href="{merck_sales_url}">Merck 2Q26 공식 매출자료</a>\n'
            f'- <a href="{july_url}">7월 네덜란드 가처분 판결</a>'
        )

    if case in {DUTCH_VRO_CASE, GERMAN_EP622_CASE, UK_EP347_CASE}:
        source_url = html.escape(item["url"], quote=True)
        title_map = {
            "nl_appeal": "네덜란드 EP622 항소 제기",
            "nl_stay": "네덜란드 EP622 집행정지 절차 변화",
            "nl_stay_request": "네덜란드 EP622 집행정지 신청",
            "nl_stay_decision": "네덜란드 EP622 집행정지 법원 결정",
            "nl_appeal_decision": "네덜란드 EP622 항소심 결정",
            "de_appeal_decision": "독일 EP622 가처분 항소심 결정",
            "uk_judgment": "영국 EP347 본안 판단",
        }
        if kind in title_map:
            return (
                "<b>[바이오 감시] Halozyme 유럽 특허분쟁 후속</b>\n\n"
                f"<b>{html.escape(title_map[kind])}</b>\n\n"
                f"- <b>타임라인:</b>\n{timeline_html(case, kind, item)}\n"
                "- <b>의미:</b> Keytruda SC의 유럽 자유실시 가능성과 알테오젠의 유럽 판매 마일스톤·향후 로열티 시간표를 다시 평가해야 하는 후속 절차입니다.\n"
                "- <b>주의:</b> 유럽 개별국 결과를 미국 PTAB·뉴저지 소송 또는 다른 ALT-B4 파트너 제품에 자동 확대하지 않습니다.\n"
                f'- <a href="{source_url}">원문 뉴스보기</a>'
            )

    if kind != "final_decision":
        message = _original_alert(case, patent, kind, item)
        timeline = timeline_html(case, kind, item)
        lines = message.splitlines()
        for idx, line in enumerate(lines):
            if "<b>사건:</b>" in line:
                lines.insert(idx + 1, f"- <b>타임라인:</b>\n{timeline}")
                break
        if kind == "final_unpatentable":
            for idx, line in enumerate(lines):
                if "<b>다음 확인:</b>" in line:
                    lines.insert(
                        idx,
                        "- <b>절차 시계:</b> 최종서면결정 후 30일 내 USPTO 국장 재검토 또는 PTAB 재심 중 하나를 요청할 수 있습니다. 기본 항소기간은 63일이며, 적법한 재검토·재심이 있으면 항소 시계가 재설정됩니다.",
                    )
                    break
        return "\n".join(lines)

    title = f"PTAB 최종서면결정 공개 — {case}, Halozyme 특허 {patent or '관련 특허'}"
    src = "USPTO/PTAB·법원 공식자료" if base.official(item["url"]) else "2차 자료 — 공식 결정문 결과 교차확인 대상"
    url = html.escape(item["url"], quote=True)
    return (
        "<b>[바이오 감시] Halozyme 특허분쟁</b>\n\n"
        f"<b>{html.escape(title)}</b>\n\n"
        f"- <b>사건:</b> {html.escape(case)}"
        + (f" · 미국 특허 {html.escape(patent)}" if patent else "")
        + "\n"
        f"- <b>타임라인:</b>\n{timeline_html(case, kind, item)}\n"
        "- <b>결정:</b> PTAB 최종서면결정이 공개됐습니다. 청구항별 특허성 판단은 원문 결과를 추가 교차확인합니다.\n"
        "- <b>알테오젠:</b> Halozyme 변형 PH20 특허 장벽과 MSD·알테오젠의 미국 피하주사 사업 리스크에 직접 연결되는 사건입니다.\n"
        "- <b>다음 확인:</b> 청구항별 특허성 결과 → 국장 재검토·재심 → 연방순회항소법원 항소\n"
        f"- <b>원문 확인:</b> {src}\n"
        f'- <a href="{url}">원문 뉴스보기</a>'
    )


def get_case(text: str) -> tuple[str, str]:
    case, patent = _original_get_case(text)
    if case:
        return case, patent

    low = text.lower()
    normalized = re.sub(r"[,\s]", "", low)
    # Halozyme's Nov 19 official release describes the German appeal outcome
    # without spelling out EP622. Require jurisdiction + drug + final action.
    if (
        ("keytruda" in low or "키트루다" in low)
        and ("halozyme" in low or "할로자임" in low)
        and ("merck" in low or "msd" in low or "머크" in low)
        and any(x in low for x in ("germany", "german", "munich", "독일", "뮌헨"))
        and any(x in low for x in ("preliminary injunction", "가처분", "판매금지", "판매 금지"))
        and any(x in low for x in ("overturned", "reversed", "vacated", "lifted", "취소", "뒤집", "해제"))
    ):
        return GERMAN_EP622_CASE, DUTCH_VRO_PATENT
    if "c/09/695432" in low or (
        ("ep622" in normalized or "ep2797622" in normalized)
        and "keytruda" in low
        and any(term in low for term in ("netherlands", "dutch", "the hague", "den haag", "네덜란드"))
    ):
        return DUTCH_VRO_CASE, DUTCH_VRO_PATENT
    if (
        ("ep622" in normalized or "ep2797622" in normalized)
        and "keytruda" in low
        and any(term in low for term in ("germany", "german", "deutschland", "독일"))
    ):
        return GERMAN_EP622_CASE, DUTCH_VRO_PATENT
    if (
        ("ep347" in normalized or "ep3130347" in normalized)
        and "keytruda" in low
        and any(term in low for term in ("united kingdom", "uk", "england", "britain", "영국"))
    ):
        return UK_EP347_CASE, "EP 3,130,347"

    # 번호가 없는 '2건' 기사를 임의로 PGR2025-00033에 귀속시키지 않는다.
    # 기왕의 판정은 VERIFIED_CURRENT_DECISIONS와 공식 IR로 별도 확인한다.
    return "", ""


base.classify = classify
base.alert = alert
base.get_case = get_case

_original_event_already_sent = base.event_already_sent


def stage_aware_event_already_sent(
    key: str, url: str, kind: str, seen_events: set[str], seen_urls: set[str]
) -> bool:
    # An ambiguous Telegram receipt must never authorize a blind resend.
    try:
        legal_state = json.loads(base.STATE.read_text(encoding="utf-8"))
        uncertain = legal_state.get("halozyme_delivery_uncertain") or {}
        if key in set(uncertain.get("event_keys") or []):
            return True
    except (ValueError, OSError, TypeError, AttributeError):
        pass
    # An institution or older filing can share the case URL with a new FWD.
    # Still suppress repeated FWD notices by the exact case+stage event key.
    if kind in {"final_unpatentable", "decision_rationale"}:
        return key in seen_events
    return _original_event_already_sent(key, url, kind, seen_events, seen_urls)


base.event_already_sent = stage_aware_event_already_sent



def _plain_text(page: str) -> str:
    value = re.sub(r"(?is)<script.*?</script>|<style.*?</style>|<noscript.*?</noscript>", " ", page)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def parse_portfolio_scorecard(text: str) -> dict | None:
    low = text.lower()
    if "halozyme" not in low and "할로자임" not in text:
        return None
    if "pgr" not in low:
        return None

    total = won = pending = None
    m = re.search(r"PGR\s*(\d+)\s*건\s*가운데\s*(\d+)\s*건", text, re.I)
    if m:
        total, won = int(m.group(1)), int(m.group(2))
    m2 = re.search(r"나머지\s*(\d+)\s*건", text)
    if m2:
        pending = int(m2.group(1))
    if total is None or won is None:
        return None
    if pending is None:
        pending = max(0, total - won)

    oral = ""
    mh = re.search(r"(?:지난\s*)?(\d{1,2})월\s*(\d{1,2})일\s*구술심리", text)
    if mh:
        oral = f"2026-{int(mh.group(1)):02d}-{int(mh.group(2)):02d}"

    patents = []
    for patent in re.findall(r"\b12[,\d]{7,}\b", text):
        cleaned = patent.replace(",", "")
        if len(cleaned) == 8:
            formatted = f"{cleaned[:2]},{cleaned[2:5]},{cleaned[5:]}"
            if formatted not in patents:
                patents.append(formatted)

    return {
        "total": total,
        "won": won,
        "pending": pending,
        "oral_date": oral,
        "patents": patents[:6],
    }


def _portfolio_ir_urls() -> list[str]:
    urls = [ALTEOGEN_IR_CURRENT_URL]
    try:
        page = base.fetch(ALTEOGEN_IR_LIST_URL, timeout=7)
        for href, label in re.findall(r'href=["\']([^"\']*information\.php\?[^"\']*idx=\d+[^"\']*)["\'][^>]*>(.*?)</a>', page, re.I | re.S):
            title = _plain_text(label)
            if not any(k in title.lower() for k in ("halozyme", "mdase", "pgr", "ipr")) and "할로자임" not in title:
                continue
            url = urllib.parse.urljoin(ALTEOGEN_IR_LIST_URL, html.unescape(href))
            if url not in urls:
                urls.append(url)
    except Exception:
        pass
    return urls[:12]


def portfolio_scorecard_key(score: dict) -> str:
    # 동일 11/14 판세를 다른 기사·IR에서 재확인하더라도 중복 송출하지 않는다.
    # 심리일 표기의 누락·변경은 승패 건수 변화가 아니다.
    return base.digest(
        f"portfolio-v2|{score['total']}|{score['won']}|{score['pending']}"
    )


def _legacy_portfolio_scorecard_keys(score: dict) -> set[str]:
    # 기존 송출 완료 키를 유지하며, 새 기준 도입으로 7/14·9/14·11/14
    # 과거 알림을 다시 보내는 일을 방지한다.
    dates = {str(score.get("oral_date") or ""), "", "2026-07-23"}
    return {
        base.digest(
            f"portfolio|{score['total']}|{score['won']}|{score['pending']}|{oral}"
        )
        for oral in dates
    }


def portfolio_updates() -> list[dict]:
    # 현재 공식 IR에서 확인된 7/14 판세는 검색색인·HTML 파싱 실패와 무관하게
    # 한 번은 반드시 이벤트로 소비하도록 검증된 기준선을 포함한다.
    updates: list[dict] = [
        CURRENT_PORTFOLIO_SCORECARD,
        PTAB_VERIFIED_PORTFOLIO_SCORECARD,
        PTAB_OCT15_PORTFOLIO_SCORECARD,
        PTAB_NOV9_PORTFOLIO_SCORECARD,
    ]
    global _official_portfolio_cache
    if _official_portfolio_cache is None:
        _official_portfolio_cache = _alteogen_official_portfolio_items()
    for official_item in _official_portfolio_cache:
        text = str(official_item.get("description") or "")
        score = parse_portfolio_scorecard(text)
        if not score:
            continue
        updates.append({
            "url": base.clean_url(str(official_item.get("url") or "")),
            "title": str(official_item.get("title") or "알테오젠 공식 IR Halozyme PGR 판세 업데이트"),
            "score": score,
        })
    unique = {}
    for item in updates:
        s = item["score"]
        key = portfolio_scorecard_key(s)
        unique.setdefault(key, item)
    return list(unique.values())


def portfolio_alert(item: dict) -> str:
    s = item["score"]
    ratio = (s["won"] / s["total"] * 100.0) if s["total"] else 0.0
    oral = f" · {s['oral_date']} 공동 구술심리" if s.get("oral_date") else ""
    patents = " · ".join(s.get("patents") or [])
    patent_line = f"\n- <b>이번 확인 특허:</b> {html.escape(patents)}" if patents else ""
    source_kind = str(item.get("source_kind") or "alteogen_ir")

    if source_kind == "ptab_user_cover_rollup_20261109":
        url = html.escape(item["url"], quote=True)
        return (
            "<b>[바이오 감시] Halozyme MDASE 미국 PGR 누적 판세 갱신</b>\n\n"
            f"<b>최종서면결정에서 심판 대상 청구항 특허성 부정: 11/14 → {s['won']}/{s['total']}건</b>\n"
            f"- <b>최종결정 대기:</b> {s['pending']}건(PGR2025-00050·00053)\n"
            "- <b>신규 결정:</b> <b>2026년 11월 9일</b> PGR2025-00042, 미국 특허 "
            "12,037,618호, Paper 95, 심판 대상 청구항 전부 특허성 부정.\n"
            "- <b>구분:</b> 12건의 PGR 최종서면결정에서 특허성이 부정됐다는 뜻이며 "
            "법적 취소·항소 종결이 완료된 특허가 12건이라는 뜻이 아닙니다.\n"
            "- <b>미국·유럽 차이:</b> 미국 PTAB 판단은 별개 유럽 EP622 유효·침해 판결과 "
            "판매금지명령을 자동으로 뒤집지 않습니다.\n"
            "- <b>근거 수준:</b> 11/14는 이전 확인치, 이번 한 건은 사용자 제공 Paper 95 표지와 "
            "USPTO 사건번호·특허번호 교차확인에 근거합니다. 공식 전체 결정문 직접 열람은 미완료입니다.\n"
            f'- <a href="{url}">USPTO 사건기록 확인</a>'
        )

    if source_kind == "ptab_verified_rollup_20261015":
        urls = list(item.get("source_urls") or [])
        links = "\n".join(
            f'- <a href="{html.escape(url, quote=True)}">USPTO P-TACTS 사건기록 {i}</a>'
            for i, url in enumerate(urls, 1)
        )
        return (
            "<b>[바이오 감시] Halozyme MDASE 미국 PGR 누적 판세 변화</b>\n\n"
            f"<b>PTAB 최종서면결정 기준 9/14 → {s['won']}/{s['total']}건 (잔여 {s['pending']}건)</b>\n"
            "- <b>타임라인:</b>\n"
            "• <b>2026년 9월 28일</b> 알테오젠 공식 IR 7/14 확인\n"
            "• <b>2026년 10월 1일</b> PGR2025-00052 최종서면결정\n"
            "• <b>2026년 10월 2일</b> PGR2025-00046 최종서면결정, 누적 9/14\n"
            "• <b>2026년 10월 15일</b> PGR2025-00024·00030 Paper 100 최종서면결정, 누적 11/14\n"
            "- <b>이번 2건:</b> US 12,060,590 심판 대상 26개 청구항, US 12,054,758 심판 대상 27개 청구항에서 전부 특허성 부정(합계 53개).\n"
            "- <b>정확한 법적 성격:</b> PGR 심판 대상 청구항의 PTAB 최종서면결정으로, 확정 취소·특허 소멸이나 항소 종료를 의미하지 않습니다.\n"
            "- <b>잔여 사건:</b> PGR2025-00042·00050·00053. 11월 19일까지 모두 MSD 승소한다는 전망은 확정 사실이 아닙니다.\n"
            "- <b>국가별 차이:</b> 미국 PTAB 결과와 네덜란드 EP622 유효·침해 인정 및 유럽 8개국 금지명령은 별개입니다.\n"
            "- <b>다음 확인:</b> 3개 잔여 최종서면결정 → 국장 재검토·재심 → 연방순회항소법원 항소·결과.\n"
            "- <b>확인 근거:</b> 사용자 제공 PTAB Paper 100 표지(2026-10-15), USPTO 사건번호·특허번호 대조, 관련 보도. 전체 결정문 본문 직접 열람 여부는 별도입니다.\n"
            + links
        )

    if source_kind == "ptab_verified_rollup":
        source_urls = list(item.get("source_urls") or [])
        source_links = "\n".join(
            f'- <a href="{html.escape(url, quote=True)}">USPTO/PTAB 사건 원문 {idx}</a>'
            for idx, url in enumerate(source_urls, 1)
        )
        return (
            "<b>[바이오 감시] Halozyme 특허분쟁 판세 업데이트</b>\n\n"
            f"<b>PTAB 신규 최종서면결정 2건 반영 — 누적 {s['won']}/{s['total']}건</b>\n\n"
            "- <b>타임라인:</b>\n"
            "• <b>2026년 7월 23일</b> 관련 10개 PGR 공동 구술심리\n"
            "• <b>2026년 9월 25일</b> PGR2025-00033·00039 최종서면결정\n"
            "• <b>2026년 9월 28일</b> 알테오젠 공식 IR 7/14 확인\n"
            "• <b>2026년 10월 1일</b> PGR2025-00052 최종서면결정\n"
            "• <b>2026년 10월 2일</b> PGR2025-00046 최종서면결정\n"
            f"- <b>누적 판세:</b> PTAB 확인 기준 {s['won']}/{s['total']}건 · {ratio:.0f}% · 잔여 {s['pending']}건{oral}"
            + patent_line
            + "\n- <b>결정:</b> PGR2025-00052와 PGR2025-00046 모두 PTAB가 심판 대상 청구항 전부를 특허 받을 수 없다고 최종 판단했습니다.\n"
            "- <b>정확한 성격:</b> 알테오젠이 9/14를 새 공식 IR로 발표했다는 뜻이 아니라, 9월 28일 공식 7/14 기준에 이후 PTAB 최종결정 2건을 더한 현재 확인치입니다.\n"
            "- <b>알테오젠:</b> ALT-B4 자체 특허 유효성 판정은 아니지만, Halozyme MDASE 특허 포트폴리오 방어력이 추가로 약해지는 방향입니다.\n"
            "- <b>절차 시계:</b> 각 최종서면결정 후 30일 내 USPTO 국장 재검토 또는 PTAB 재심 중 하나 → 기본 63일 내 연방순회항소법원 항소. 재검토·재심이 있으면 항소 시계는 재설정됩니다.\n"
            "- <b>다음 확인:</b> 잔여 5건 최종서면결정 → 국장 재검토·재심 → 연방순회항소법원 항소 → 뉴저지·유럽 소송\n"
            "- <b>원문 확인:</b> 사용자 제공 PTAB 결정문 첫 페이지 직접 대조 + USPTO/P-TACTS 사건 식별 교차확인\n"
            + source_links
        )

    return (
        "<b>[바이오 감시] Halozyme 특허분쟁 판세 업데이트</b>\n\n"
        f"<b>MSD, 심리 개시 PGR {s['total']}건 중 {s['won']}건에서 특허성 부정</b>\n\n"
        f"- <b>누적 판세:</b> {s['won']}/{s['total']}건 · {ratio:.0f}%\n"
        f"- <b>잔여:</b> {s['pending']}건 최종결정 대기{oral}"
        + patent_line
        + "\n- <b>의미:</b> 개별 특허 결과를 넘어 Halozyme MDASE 특허 포트폴리오 전체에서 MSD 우위가 누적되고 있다는 공식 IR 업데이트입니다.\n"
        "- <b>알테오젠:</b> ALT-B4 자체 특허 유효성 판정은 아니지만, KEYTRUDA QLEX 미국 사업에 반영되던 Halozyme 특허분쟁 불확실성을 낮추는 방향입니다.\n"
        "- <b>아직 남음:</b> 잔여 PGR 최종결정 · 국장 재검토·재심 · 연방순회항소 · 뉴저지·유럽 소송\n"
        f"- <b>다음 확인:</b> {s['won']}/{s['total']} → 다음 누적 판세 변화와 후속 절차\n"
        "- <b>원문 확인:</b> 알테오젠 공식 IR 본문 직접 열람\n"
        f'- <a href="{html.escape(item["url"], quote=True)}">원문 뉴스보기</a>'
    )


def send_portfolio_updates() -> list[int]:
    try:
        state = json.loads(base.STATE.read_text(encoding="utf-8"))
    except Exception:
        state = {}
    seen = set(state.get("seen_portfolio_updates") or [])
    token = (os.getenv("BIO_TELEGRAM_BOT_TOKEN") or "").strip()
    chat = base.resolve_chat_id(token) if token else ""
    sent = []
    if not token or not chat:
        return sent

    for item in portfolio_updates():
        s = item["score"]
        key = portfolio_scorecard_key(s)
        uncertain = state.get("halozyme_delivery_uncertain") or {}
        if uncertain.get("event_id") == "pgr14" and key == portfolio_scorecard_key(PGR_LAST_TWO_SCORE):
            continue
        if key in seen or seen.intersection(_legacy_portfolio_scorecard_keys(s)):
            seen.add(key)
            continue
        mid = base.send(token, chat, portfolio_alert(item))
        sent.append(mid)
        seen.add(key)

    state["seen_portfolio_updates"] = sorted(seen)[-500:]
    if sent:
        state["last_portfolio_message_ids"] = sent
    base.STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return sent

# Separate lead warning: this is not a PTAB decision or proof of 14/14.
# Only one notice is eligible around the two outstanding 2025-11-19 institutions.
PGR_FINAL_WINDOW_LEAD_KEY = base.digest(
    "pgr2025-00050|pgr2025-00053|2026-11-19-et|predecision-lead-v1"
)


def _send_verified_pgr_lead(token: str, chat: str, message: str) -> int:
    """Use the existing bio Telegram route, and check the actual send receipt."""
    from qlex_telegram_send import correct_destination

    payload = urllib.parse.urlencode({
        "chat_id": chat,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage", data=payload, method="POST"
    )
    # Do not blindly retry an ambiguous POST: it may already have reached Telegram.
    with urllib.request.urlopen(req, timeout=25) as response:
        receipt = json.loads(response.read().decode("utf-8"))
    result = receipt.get("result") or {}
    message_id = int(result.get("message_id") or 0)
    if not receipt.get("ok") or message_id <= 0 or not correct_destination(chat, result):
        raise RuntimeError("PGR lead warning Telegram receipt or destination mismatch")
    return message_id


def maybe_send_pgr_deadline_lead_notice(now_et: dt.datetime | None = None) -> list[int]:
    """Warn of expected timing once, without relaxing final-decision proof gates."""
    eastern = ZoneInfo("America/New_York")
    now = (now_et or dt.datetime.now(eastern)).astimezone(eastern)
    if not (dt.date(2026, 11, 18) <= now.date() <= dt.date(2026, 11, 20)):
        return []
    try:
        state = json.loads(base.STATE.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        # Never reset a missing/corrupted baseline just to send a lead notice.
        return []
    if not state.get("initialized"):
        return []
    score_keys = set(state.get("seen_portfolio_updates") or [])
    if portfolio_scorecard_key(PTAB_NOV9_PORTFOLIO_SCORECARD["score"]) not in score_keys:
        return []
    if portfolio_scorecard_key({"total": 14, "won": 14, "pending": 0}) in score_keys:
        return []

    events = set(state.get("seen_events") or [])
    remaining = ("PGR2025-00050", "PGR2025-00053")
    if any(
        base.digest(f"{case}|{stage}") in events
        for case in remaining
        for stage in ("final_decision", "final_unpatentable")
    ):
        return []
    if (
        PGR_FINAL_WINDOW_LEAD_KEY in set(state.get("seen_lead_warning_keys") or [])
        or state.get("pgr_deadline_lead_uncertain")
    ):
        return []

    token = (os.getenv("BIO_TELEGRAM_BOT_TOKEN") or "").strip()
    chat = base.resolve_chat_id(token) if token else ""
    if not token or not chat:
        return []

    message = (
        "<b>[바이오 감시] Halozyme PGR 선행경보 — 최종결정 미확인</b>\n\n"
        "<b>미국 11월 19일 전후, MDASE 특허 마지막 PGR 2건의 최종판단 예상</b>\n"
        "- <b>현재 확인:</b> 14건 중 12건은 심판 대상 청구항의 특허성이 부정됐고, "
        "나머지 2건은 아직 PTAB 최종 결정문 확인 전입니다.\n"
        "- <b>대기 사건:</b> PGR2025-00050(US 12,077,791), "
        "PGR2025-00053(US 12,195,773).\n"
        "- <b>예상 시점:</b> 2025년 11월 19일 심판 개시 후 통상 1년 기준인 "
        "2026년 11월 19일(미국 동부) 전후. 결정일은 연장될 수 있습니다.\n"
        "- <b>확정경보:</b> 각 사건의 최종서면결정·청구항별 결과를 "
        "공식 기록과 대조한 후 별도 발송합니다. 14전 14승은 아직 확정하지 않습니다.\n"
        "- <b>구분:</b> PTAB 미국 판단은 특허 소멸·항소 종결이나 "
        "유럽의 별도 판결을 뜻하지 않습니다.\n"
        '- <a href="https://ptacts.uspto.gov/ptacts/public-informations/petitions/1557844">'
        "PGR2025-00050 미국 특허심판원 사건기록</a>"
    )
    try:
        message_id = _send_verified_pgr_lead(token, chat, message)
    except Exception as exc:
        # POST receipt absent: quarantine this notice, never blindly retransmit.
        state["pgr_deadline_lead_uncertain"] = {
            "key": PGR_FINAL_WINDOW_LEAD_KEY,
            "cause_type": type(exc).__name__,
            "recorded_at_kst": dt.datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds"),
        }
        base.STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise RuntimeError("PGR lead warning receipt not verified; automatic resend blocked") from exc

    state["seen_lead_warning_keys"] = sorted(
        set(state.get("seen_lead_warning_keys") or []) | {PGR_FINAL_WINDOW_LEAD_KEY}
    )
    state["last_pgr_lead_notice_receipt"] = {
        "message_id": message_id,
        "destination_verified": True,
        "sent_at_kst": dt.datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds"),
    }
    base.STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"pgr_predecision_lead_sent=true message_id={message_id} destination_verified=true")
    return [message_id]



# Dated event recovery limited to the two November 2026 material changes.
# PGR sources: the 2026-11-18 PTAB decision cover images published by TheBioNews
# plus separate coverage by Edaily and ChosunBiz, and USPTO case identification.
# The complete PTAB decision PDFs have NOT been accessed by this workflow.
# German source: Halozyme's own November 19 official public release.
# Neither the existence of this fixture nor generic RSS success means the
# original official PTAB documents were fetched in the current runtime.
def _verified_material_report(event_id: str) -> str:
    if event_id == "pgr14":
        return (
            "<b>[바이오 감시] MSD·Halozyme 미국 PGR 최종결정 — 14건 모두 MSD에 유리</b>\n\n"
            "<b>2026년 11월 18일 PTAB 최종서면결정 2건 추가: 12/14 → 14/14</b>\n"
            "- <b>확정 타임라인(미국 현지 날짜):</b>\n"
            "• <b>2025년 11월 19일</b> 두 사건 심판 개시 — 아직 최종결정 아님\n"
            "• <b>2026년 11월 9일</b> 이전 결정까지 MSD 우위 12/14 확인\n"
            "• <b>2026년 11월 18일</b> 두 최종서면결정으로 14/14 도달\n"
            "- <b>보도일:</b> 2026년 11월 19일 한국 기사 게시. PTAB 결정일과 구분합니다.\n"
            "- <b>후속 확인:</b> 재검토·재심 신청 여부 → 실제 결정 → 항소 제기·결과. "
            "절차 일정은 공식 접수 후 별도 확정합니다.\n"
            "- <b>신규 사건 1:</b> PGR2025-00050 · US 12,077,791 · 심판 대상 청구항 "
            "1~3·6~10(8개) 전부 특허성 부정.\n"
            "- <b>신규 사건 2:</b> PGR2025-00053 · US 12,195,773 · 심판 대상 청구항 "
            "1~3·5~15(14개) 전부 특허성 부정.\n"
            "- <b>범위:</b> 합계 22개 심판 대상 청구항 판단. 기존 포기 청구항 "
            "(791호 4·5, 773호 4)은 최종심결로 무효화한 청구항과 구분합니다.\n"
            "- <b>알테오젠 영향:</b> KEYTRUDA QLEX에 적용된 ALT-B4의 미국 MDASE "
            "특허분쟁 부담이 완화되는 방향입니다. 매출·로열티 증가액은 이 판정만으로 확정되지 않습니다.\n"
            "- <b>법적 범위:</b> PTAB 최종서면결정은 미국 특허권 취소·항소 종료가 "
            "법적으로 모두 완료됐다는 뜻이 아닙니다. 뉴저지 침해소송·유럽 특허소송은 별개입니다.\n"
            "- <b>근거 수준:</b> 11월 18일 결정 표지 이미지·사건번호/특허번호와 "
            "독립 보도를 대조했습니다. 미국 특허청 최종결정문 전문은 직접 열람하지 못했습니다.\n"
            '- <a href="https://ptacts.uspto.gov/ptacts/public-informations/petitions/1557844">'
            '미국 특허청 PGR2025-00050 사건기록</a>\n'
            f'- <a href="{html.escape(PGR_LAST_TWO_NEWS_URL, quote=True)}">11월 19일 최초 확인 보도</a>\n'
            f'- <a href="{html.escape(PGR_LAST_TWO_CORROBORATION_URL, quote=True)}">독립 교차확인 보도</a>'
        )
    if event_id == "de_reversal":
        return (
            "<b>[바이오 감시] MSD·Halozyme 독일 법원 판결 — 기존 가처분 취소</b>\n\n"
            "<b>2026년 11월 19일 뮌헨 고등법원: Keytruda SC 독일 "
            "판매금지 가처분을 항소심에서 뒤집음</b>\n"
            "- <b>확정 타임라인(독일 현지 날짜):</b>\n"
            "• <b>2025년 12월 4일</b> 뮌헨 지방법원 판매·유통금지 가처분\n"
            "• <b>2026년 11월 19일</b> 뮌헨 고등법원 항소심에서 해당 가처분 취소\n"
            "- <b>공식 발표일:</b> 2026년 11월 19일 할로자임 보도자료. 실제 법원 결정과 별도 구분합니다.\n"
            "- <b>후속 예정:</b> 독일 본안 침해소송은 할로자임 제기 계획 단계로, "
            "실제 제출·심리·선고 날짜는 확인되지 않았습니다.\n"
            "- <b>기존 → 신규:</b> 2025년 12월 독일 판매·유통금지 가처분 "
            "→ 2026년 11월 19일 항소심에서 그 가처분 취소.\n"
            "- <b>공식 확인:</b> 패소 당사자인 Halozyme이 판결 결과를 직접 발표했습니다.\n"
            "- <b>법적 제한:</b> 이번 결정은 독일 가처분에 관한 것이며 "
            "EP622 특허 자체의 무효 확정이나 모든 본안소송 종결이 아닙니다.\n"
            "- <b>반대 위험:</b> Halozyme은 독일에서 금지명령을 구하는 "
            "정식 침해소송을 제기하겠다고 밝혔습니다. 네덜란드 법원의 "
            "별도 유럽 8개국 금지명령도 이번 결정으로 자동 취소되지 않습니다.\n"
            "- <b>알테오젠 영향:</b> 독일 시장 출시 제약이 완화될 수 있으나 "
            "실제 판매 재개·공급·로열티는 별도 확인이 필요합니다.\n"
            f'- <a href="{html.escape(HALOZYME_GERMAN_REVERSAL_URL, quote=True)}">'
            'Halozyme 공식 보도자료</a>'
        )
    raise ValueError("Unknown Halozyme material event")


def send_missing_verified_material(now_kst: dt.datetime | None = None) -> list[int]:
    """Backfill exactly the two verified facts, on the existing chat and keys."""
    now = (now_kst or dt.datetime.now(ZoneInfo("Asia/Seoul"))).astimezone(ZoneInfo("Asia/Seoul"))
    try:
        state = json.loads(base.STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []  # An invalid checkpoint is not permission to replay old events.
    if not state.get("initialized"):
        return []

    final_case_keys = {
        base.digest(f"{case}|{stage}")
        for case in PGR_LAST_TWO_FINAL_CASES
        for stage in ("final_unpatentable", "final_decision")
    }
    score_key = portfolio_scorecard_key(PGR_LAST_TWO_SCORE)
    german_key = base.digest(f"{GERMAN_EP622_CASE}|de_appeal_decision")
    seen = set(state.get("seen_events") or [])
    seen_scores = set(state.get("seen_portfolio_updates") or [])
    delivered: list[int] = []

    for event_id, cutoff in (
        ("pgr14", dt.datetime(2026, 11, 19, 12, 25, tzinfo=ZoneInfo("Asia/Seoul"))),
        ("de_reversal", dt.datetime(2026, 11, 19, 23, 20, tzinfo=ZoneInfo("Asia/Seoul"))),
    ):
        if now < cutoff:
            continue
        # The cumulative PGR update is enough; no individual-case duplicate
        # messages for the two decisions already described in the one alert.
        if event_id == "pgr14" and score_key in seen_scores:
            continue
        if event_id == "de_reversal" and german_key in seen:
            continue
        marker = state.get("halozyme_delivery_uncertain") or {}
        if marker.get("event_id") == event_id:
            continue
        token = (os.getenv("BIO_TELEGRAM_BOT_TOKEN") or "").strip()
        chat = base.resolve_chat_id(token) if token else ""
        if not token or not chat:
            raise RuntimeError("Halozyme event recovery route unavailable")

        message = _verified_material_report(event_id)
        try:
            receipt = _send_verified_pgr_lead(token, chat, message)
        except Exception as exc:
            # The POST may have been accepted even when the receipt is missing.
            # Persist uncertainty BEFORE allowing a later check/retry.
            state["halozyme_delivery_uncertain"] = {
                "event_id": event_id,
                "event_keys": sorted(final_case_keys if event_id == "pgr14" else {german_key}),
                "message_sha": base.digest(message),
                "recorded_at_kst": now.isoformat(timespec="seconds"),
                "cause_type": type(exc).__name__,
                "retransmission_allowed": False,
            }
            base.STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            raise RuntimeError(f"Halozyme {event_id} receipt unconfirmed; automatic resend disabled") from exc

        if event_id == "pgr14":
            seen.update(final_case_keys)
            seen_scores.add(score_key)
            state["seen_portfolio_updates"] = sorted(seen_scores)[-500:]
            state["last_portfolio_message_ids"] = [receipt]
        else:
            seen.add(german_key)
            _successful_timeline_events.append({
                "case": GERMAN_EP622_CASE,
                "date": "2026-11-19",
                "kind": "de_appeal_decision",
                "label": "독일 가처분 항소심 — 2025년 판매금지명령 취소",
            })

        state["seen_events"] = sorted(seen)[-5000:]
        state.setdefault("halozyme_verified_delivery_receipts", [])
        state["halozyme_verified_delivery_receipts"] = (
            list(state["halozyme_verified_delivery_receipts"])[-19:]
            + [{
                "event_id": event_id,
                "message_id": receipt,
                "destination_verified": True,
                "source_level": "news_and_ptab_case_metadata" if event_id == "pgr14" else "issuer_official",
                "sent_at_kst": now.isoformat(timespec="seconds"),
            }]
        )
        base.STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _sent_ids.append(receipt)
        delivered.append(receipt)
        print(f"halozyme_material_alert_confirmed event={event_id} message_id={receipt} destination_verified=true")
    return delivered


_sent_ids: list[int] = []
_original_send = base.send


def tracked_send(token: str, chat: str, text: str) -> int:
    global _pending_timeline_event
    try:
        mid = _original_send(token, chat, text)
    except Exception:
        _pending_timeline_event = None
        raise
    _sent_ids.append(mid)
    if _pending_timeline_event:
        _successful_timeline_events.append(dict(_pending_timeline_event))
        _pending_timeline_event = None
    return mid


base.send = tracked_send


def main() -> int:
    # 이미 과거에 최종 무효 알림이 끝난 사건은 "최종서면결정 공개"로
    # 다시 중복 송출되지 않도록 동일 단계 키를 기준선에 추가한다.
    try:
        state0 = json.loads(base.STATE.read_text(encoding="utf-8"))
    except Exception:
        state0 = {}
    seen0 = set(state0.get("seen_events") or [])
    for case in ("PGR2025-00003", "PGR2025-00004", "PGR2025-00006", "PGR2025-00009", "PGR2025-00017"):
        seen0.add(base.digest(f"{case}|final_decision"))
    state0["seen_events"] = sorted(seen0)[-5000:]
    base.STATE.write_text(json.dumps(state0, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    material_failure = ""
    try:
        send_missing_verified_material()
    except Exception as exc:
        material_failure = f"{type(exc).__name__}: {exc}"
        print(f"halozyme_material_alert_error={material_failure}")
    rc = base.main()
    portfolio_sent = send_portfolio_updates()
    _sent_ids.extend(mid for mid in portfolio_sent if mid not in _sent_ids)
    lead_sent = maybe_send_pgr_deadline_lead_notice()
    _sent_ids.extend(mid for mid in lead_sent if mid not in _sent_ids)
    try:
        state = json.loads(base.STATE.read_text(encoding="utf-8"))
    except Exception:
        state = {}
    state["legal_v4_initialized"] = True
    state["search_mode"] = "개별 사건번호 + 미국/한국 뉴스 + Bing 웹 + 판결기술근거 (공식 PTAB 개별 문서 미연동)"
    state["ptab_direct_document_coverage"] = {
        "status": "not_verified",
        "reason": "USPTO ODP trial document API requires account/API key; no direct docket fetch in this workflow",
        "backfilled_case": "PGR2025-00042",
        "evidence": "user-supplied Paper 95 first page and independent USPTO case/patent identification",
        "pending_fwd_cases": (
            [] if portfolio_scorecard_key(PGR_LAST_TWO_SCORE)
            in set(state.get("seen_portfolio_updates") or [])
            else ["PGR2025-00050", "PGR2025-00053"]
        ),
        "late_2026_fwd_source_level": "independent_news_plus_official_docket_identity; final_pdfs_not_directly_fetched",
    }
    state["last_sent_message_ids"] = _sent_ids
    state["final_decision_classification_version"] = 2
    state["case_event_timelines"] = _merged_case_timelines(state)
    base.STATE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    errors = list(state.get("errors_last_run") or [])
    critical_names = ("RecursionError", "NameError", "UnboundLocalError", "TypeError", "SyntaxError", "AttributeError")
    critical = [err for err in errors if any(name in err for name in critical_names)]
    print(json.dumps({
        "halozyme_legal_v4": "ok" if not critical else "failed",
        "sent_message_ids": _sent_ids,
        "portfolio_sent_message_ids": portfolio_sent,
        "errors": errors[-10:],
        "critical_errors": critical,
    }, ensure_ascii=False))
    if critical or material_failure:
        return 2
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
