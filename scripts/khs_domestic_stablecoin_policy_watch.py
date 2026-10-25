#!/usr/bin/env python3
"""KHS domestic stablecoin and digital-asset policy watch.

This lane catches Korean official policy signals on won stablecoins,
digital-asset legislation, payment infrastructure, and deposit-substitution
regulatory risk before they are folded into the policy Telegram alert.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import os
import re
import urllib.parse
from pathlib import Path
from zoneinfo import ZoneInfo

from khs_source_fetch import fetch_text as fetch_text_shared
from khs_source_fetch import record_source_failure


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "out"
DATA_DIR = ROOT / "data"
ALERTS_JSON_PATH = OUT_DIR / "khs_policy_watch_alerts.json"
SEEN_PATH = DATA_DIR / "khs_domestic_stablecoin_policy_seen.json"
KST = ZoneInfo("Asia/Seoul")
MAX_AGE_HOURS = int(os.getenv("KHS_SOURCE_MAX_AGE_HOURS", "72"))
MAX_ALERTS = int(os.getenv("KHS_DOMESTIC_STABLECOIN_MAX_ALERTS", "3"))
MAX_DETAIL_LINKS_PER_SOURCE = int(os.getenv("KHS_DOMESTIC_STABLECOIN_MAX_DETAIL_LINKS_PER_SOURCE", "8"))
UA = os.getenv("SEC_USER_AGENT", "KHS-domestic-stablecoin-policy-watch contact=github-actions")

STABLECOIN_QUERY = urllib.parse.quote("스테이블코인")
DIGITAL_ASSET_QUERY = urllib.parse.quote("디지털자산")
VIRTUAL_ASSET_QUERY = urllib.parse.quote("가상자산")
# Dedicated policy-reported tax stage. These links are evidence, NOT proof of
# an enacted tax postponement. Existing CBDC/stablecoin official lane is unchanged.
CRYPTO_TAX_PRIMARY_REPORT = "https://en.sedaily.com/politics/2026/10/25/presidential-office-decides-to-delay-crypto-tax-again"
CRYPTO_TAX_SECONDARY_REPORT = "https://coinness.com/en/news/1172857"
CRYPTO_TAX_OFFICIAL_GUIDANCE = "https://www.nts.go.kr/nts/cm/cntnts/cntntsView.do?cntntsId=238935"
CRYPTO_TAX_CARF_OECD = "https://www.oecd.org/content/dam/oecd/en/networks/global-forum-tax-transparency/commitments-carf.pdf"
CRYPTO_TAX_BILL_2029 = "https://community.lawmaking.go.kr/gcom/nsmLmSts/out/2220914/detailRP"
CRYPTO_TAX_BILL_CARF = "https://lawwatch.kr/bills/22-2221923"
CRYPTO_TAX_BILL_2030 = "https://lnp.nanet.go.kr/policy/assemblyBodo/detail.do?controlNo=196915"
CRYPTO_TAX_REPORT_TIME = dt.datetime(2026, 10, 25, 12, 2, tzinfo=KST)

SOURCES = [
    (
        "Financial Services Commission stablecoin releases",
        f"https://www.fsc.go.kr/no010101?srchText={STABLECOIN_QUERY}",
    ),
    (
        "Financial Services Commission stablecoin explanations",
        f"https://www.fsc.go.kr/no010102?srchText={STABLECOIN_QUERY}",
    ),
    (
        "Financial Services Commission digital asset releases",
        f"https://www.fsc.go.kr/no010101?srchText={DIGITAL_ASSET_QUERY}",
    ),
    (
        "Korea Policy Briefing stablecoin search",
        f"https://www.korea.kr/news/policyNewsList.do?srchKeyword={STABLECOIN_QUERY}",
    ),
    (
        "Korea Policy Briefing digital asset search",
        f"https://www.korea.kr/news/policyNewsList.do?srchKeyword={DIGITAL_ASSET_QUERY}",
    ),
    (
        "Bank of Korea digital currency policy",
        "https://www.bok.or.kr/portal/submain/submain/cbdc.do?menuNo=201136",
    ),
    (
        "Bank of Korea payment research",
        "https://www.bok.or.kr/portal/bbs/B0000232/list.do?menuNo=200706",
    ),
    (
        "Bank of Korea CBDC and deposit-token blog",
        "https://www.bok.or.kr/portal/bbs/B0000347/list.do?menuNo=201106",
    ),
    (
        "Korea FIU virtual asset notices",
        "https://www.kofiu.go.kr/kor/notification/notice.do",
    ),
]

SOURCE_ALTERNATES = {
    "Korea Policy Briefing stablecoin search": [
        f"https://www.korea.kr/briefing/pressReleaseList.do?srchKeyword={STABLECOIN_QUERY}",
    ],
    "Korea Policy Briefing digital asset search": [
        f"https://www.korea.kr/briefing/pressReleaseList.do?srchKeyword={DIGITAL_ASSET_QUERY}",
    ],
}

ACTOR_TERMS = [
    "금융위원회", "금융위", "금융감독원", "금감원", "한국은행", "한은",
    "국회", "정무위원회", "정부", "당정", "가상자산위원회", "금융당국",
    "금융정보분석원", "FIU", "은행", "은행권", "핀테크", "가상자산거래소",
    "거래소", "전자금융업자", "결제사업자",
]
POLICY_TERMS = [
    "스테이블코인", "원화 스테이블코인", "디지털자산기본법", "디지털자산 기본법",
    "가상자산 2단계", "2단계 입법", "2단계법", "가상자산법", "디지털자산법",
    "디지털자산", "가상자산", "결제토큰", "지급결제", "디지털화폐", "CBDC",
]
EVENT_TERMS = [
    "발행", "발행인", "발행주체", "발행 주체", "유통", "허용", "규율",
    "규제", "법안", "입법", "준비자산", "상환청구권", "예금 대체",
    "은행 중심", "핀테크", "거래소", "상용화", "기술 검증", "테스트",
    "표준", "결제", "인프라", "협의", "확정", "미확정", "정해진 바",
]
HIGH_IMPACT_TERMS = [
    "발행주체", "발행 주체", "은행 중심", "핀테크", "거래소", "예금 대체",
    "준비자산", "상환청구권", "허용", "규제", "법안", "입법", "2단계법",
    "상용화", "표준", "결제 인프라", "확정된 바", "정해진 바",
]
BOK_DIRECT_POLICY_TERMS = [
    "스테이블코인", "원화 스테이블코인", "디지털자산기본법", "디지털자산 기본법",
    "가상자산 2단계", "2단계 입법", "2단계법", "예금 대체",
    "준비자산", "상환청구권", "발행주체", "발행 주체",
]
BOK_DIRECT_EVENT_TERMS = [
    "발행주체", "발행 주체", "은행 중심", "핀테크", "거래소", "예금 대체",
    "준비자산", "상환청구권", "허용", "규제", "법안", "입법",
    "2단계법", "상용화", "확정된 바", "정해진 바",
]
CBDC_TITLE_TERMS = (
    "프로젝트 한강", "예금토큰", "예금 토큰", "CBDC", "중앙은행 디지털화폐",
    "기관용 디지털화폐", "국고금 디지털", "디지털화폐",
)
STABLECOIN_TITLE_TERMS = (
    "스테이블코인", "디지털자산", "가상자산", "지급결제",
    "디지털 금융", "디지털금융", "원화코인",
)
CBDC_EVENT_TERMS = (
    "실거래", "사업", "시행", "참여", "도입", "승인", "발표",
    "사용처", "지급", "발행", "국고금", "정산", "확대", "중단",
    "프로그램", "실증", "검토", "개인정보", "국채",
)
SECTORS = [
    "금융/자본시장/스테이블코인",
    "은행/핀테크/결제",
    "가상자산거래소/디지털자산",
]
POLICY_CHECK = (
    "디지털자산기본법·가상자산 2단계법, 원화 스테이블코인 발행 주체"
    "(은행·핀테크·거래소), 준비자산·상환청구권, 예금 대체 논란, 한국은행·금융당국 규제 강도 확인"
)
RISK_TABLE = (
    "법 진행형: 발행 주체·업권 범위 미확정 / "
    "예금 대체 논란: 한국은행·금융당국 규제 강도 상승 가능 / "
    "기술 검증과 상용화 차이: 실적 연결 시차 큼 / "
    "자금 성격: 코인 가격보다 미래 결제·유통 표준 선점 베팅"
)
STRUCTURE_NOTE = (
    "이 테마는 코인 가격보다 금융 인프라 재편으로 봐야 합니다. "
    "지금 붙는 자금은 당장 실적보다 누가 미래 결제·유통 표준에 앉을 수 있느냐에 먼저 베팅하는 성격이 강합니다."
)
COUNTER = (
    "법안 세부안, 발행 주체, 준비자산 요건, 예금 대체 방지 장치가 확정되지 않았고 "
    "기술 검증이 실제 상용화와 수수료 매출로 이어지기까지 시간이 필요합니다."
)


def now_kst() -> dt.datetime:
    return dt.datetime.now(tz=KST)


def clean_text(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<script\b.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def clip_text(value: object, limit: int) -> str:
    text = clean_text(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def fetch_text(url: str, timeout: int = 10, attempts: int = 1) -> tuple[str | None, str | None]:
    return fetch_text_shared(url, UA, timeout=timeout, attempts=attempts)


def fetch_source_text(source_name: str, source_url: str) -> tuple[str | None, str | None, str]:
    errors: list[str] = []
    for idx, url in enumerate([source_url, *SOURCE_ALTERNATES.get(source_name, [])], start=1):
        text, error = fetch_text(url, timeout=10, attempts=1)
        if error is None:
            return text, None, url
        errors.append(f"source_url={idx} {url} :: {error}")
    return None, " || ".join(errors), source_url


def parse_date(text: str) -> dt.datetime | None:
    match = re.search(r"\b20\d{2}[.-]\d{1,2}[.-]\d{1,2}\b", text)
    if match:
        raw = match.group(0).replace("-", ".")
        try:
            return dt.datetime.strptime(raw, "%Y.%m.%d").replace(tzinfo=KST)
        except ValueError:
            pass
    match = re.search(r"\b(20\d{2})년\s*(\d{1,2})월\s*(\d{1,2})일\b", text)
    if match:
        year, month, day = (int(part) for part in match.groups())
        return dt.datetime(year, month, day, tzinfo=KST)
    return None


def age_hours(published: dt.datetime | None, now: dt.datetime) -> float | None:
    if not published:
        return None
    return (now - published).total_seconds() / 3600


def has_any(text: str, terms: list[str]) -> bool:
    lower = text.lower()
    return any(term.lower() in lower for term in terms)


def matched_terms(text: str, terms: list[str]) -> list[str]:
    lower = text.lower()
    return [term for term in terms if term.lower() in lower]


def is_policy_candidate(text: str, source_name: str) -> bool:
    has_policy = has_any(text, POLICY_TERMS)
    has_event = has_any(text, EVENT_TERMS)
    has_actor = has_any(text, ACTOR_TERMS) or source_name.startswith(
        ("Financial Services Commission", "Korea Policy", "Bank of Korea", "National Assembly")
    )
    if source_name.startswith("Bank of Korea"):
        return has_actor and (
            (has_any(text, BOK_DIRECT_POLICY_TERMS) and has_any(text, BOK_DIRECT_EVENT_TERMS))
            or (
                has_any(text, [
                    "프로젝트 한강", "예금토큰", "예금 토큰", "일반인용 CBDC",
                    "기관용 CBDC", "국고보조금", "국고금 집행", "CBDC",
                ])
                and has_any(text, list(CBDC_EVENT_TERMS))
            )
        )
    return has_policy and has_event and has_actor


def document_title_is_relevant(title: str) -> bool:
    """Require the article heading itself, not a shared navigation/sidebar."""
    normalized = clean_text(title)
    if len(normalized) < 10:
        return False
    lower = normalized.lower()
    if any(word in lower for word in (
        "파일다운로드", "download", "첨부파일", "목록", "더보기",
    )):
        return False
    return (
        has_any(normalized, list(CBDC_TITLE_TERMS))
        or has_any(normalized, list(STABLECOIN_TITLE_TERMS))
    )


def official_document_date(title: str, detail_clean: str) -> dt.datetime | None:
    """Read date near the actual heading; never from unrelated listing context."""
    compact_title = clean_text(title)
    pos = detail_clean.find(compact_title)
    if pos < 0:
        return None
    after_title = detail_clean[pos + len(compact_title): pos + len(compact_title) + 600]
    return parse_date(after_title)


def cbdc_claim_scope(title: str, body: str, source: str) -> dict:
    """Extract published *policy type*, not a speculative issuance amount."""
    haystack = clean_text(f"{title} {body}")
    if not has_any(title, list(CBDC_TITLE_TERMS)):
        return {}
    gov_source = source.startswith((
        "Bank of Korea", "Korea Policy Briefing",
        "Financial Services Commission",
    ))
    if not gov_source:
        return {}
    target_25pct = (
        "2030" in haystack
        and "국고금" in haystack
        and has_any(haystack, ["25%", "4분의 1", "4분의1", "4분의 1을"])
    )
    subsidy = (
        has_any(haystack, ["보조금", "국고금"])
        and has_any(haystack, ["예금토큰", "예금 토큰", "디지털화폐"])
    )
    restricted_spending = subsidy and has_any(
        haystack, ["사용처", "부정수급", "목적성 지급", "지급 조건", "지급조건"]
    )
    retail_no_plan = has_any(
        haystack, [
            "일반인용 cbdc를 도입 또는 발행할 계획이 없",
            "일반인을 대상으로 cbdc를 도입 또는 발행할 계획이 없",
            "범용 cbdc를 검토하지 않",
            "일반인용 cbdc 도입 계획이 없",
            "범용 cbdc 추진하지 않",
        ],
    ) or (
        has_any(haystack, [
            "일반인용 cbdc", "일반인을 대상으로 cbdc", "범용 cbdc",
        ])
        and has_any(haystack, [
            "도입 또는 발행할 계획이 없", "도입 계획이 없",
            "발행 계획이 없", "추진하지 않", "검토하지 않",
        ])
    )
    if retail_no_plan:
        status = "범용 CBDC 도입 계획 없음(한국은행 설명)"
    elif target_25pct:
        status = "2030년 국고금 집행 25% 정책 목표(발행·매출 확정 아님)"
    elif subsidy:
        status = "기관용 디지털화폐·예금토큰 국고금 실증"
    else:
        status = "공식 디지털화폐 정책 문서(상용화 별도 검증)"
    pilot_300eok = subsidy and (
        "300억원" in haystack or "300억 원" in haystack
    )
    return {
        "official_source": True,
        "policy_type": status,
        "2030_treasury_target_25pct": target_25pct,
        "2030_target_is_issued_money": False,
        "182_trillion_is_issuance": False,
        "retail_cbdc_no_plan_statement": retail_no_plan,
        "bank_deposit_token_not_retail_cbdc": True,
        "purpose_restriction_limited_to_program": restricted_spending,
        "300eok_pilot_amount": pilot_300eok,
        "implemented_for_all_citizen_spending": False,
    }


def cbdc_display_title(scope: dict) -> str:
    """Keep institutional money and bank deposits distinct from won stablecoins."""
    if scope.get("retail_cbdc_no_plan_statement"):
        return "한국은행: 일반인용 CBDC 도입 계획 없음 공식 설명"
    if scope.get("2030_treasury_target_25pct"):
        return "국고금 예금토큰 집행: 2030년 25% 정책 목표(발행액 아님)"
    if scope.get("300eok_pilot_amount"):
        return "프로젝트 한강: 전기차 충전 보조금 300억원 예금토큰 실증"
    return "프로젝트 한강: 기관용 CBDC·은행 예금토큰 정책 변화"


def stablecoin_title(text: str) -> str:
    if has_any(text, ["발행주체", "발행 주체", "은행 중심", "핀테크", "거래소"]):
        return "국내 디지털자산 정책: 원화 스테이블코인 발행 주체·업권 범위 체크"
    if has_any(text, ["예금 대체", "준비자산", "상환청구권"]):
        return "국내 디지털자산 정책: 스테이블코인 예금 대체·준비자산 규제 체크"
    if has_any(text, ["상용화", "기술 검증", "테스트", "결제"]):
        return "국내 디지털자산 정책: 스테이블코인 결제 인프라 상용화 체크"
    return "국내 디지털자산 정책: 원화 스테이블코인 법안·결제 표준 체크"


def parse_links(text: str, source_name: str, source_url: str, now: dt.datetime) -> list[dict]:
    link_pattern = re.compile(r"<a\b[^>]*href=[\"'](?P<href>[^\"']+)[\"'][^>]*>(?P<label>.*?)</a>", re.I | re.S)
    deduped: dict[str, dict] = {}
    detail_fetches = 0
    for match in link_pattern.finditer(text):
        if detail_fetches >= MAX_DETAIL_LINKS_PER_SOURCE:
            break
        title = clean_text(match.group("label"))
        if not document_title_is_relevant(title):
            continue
        href = html.unescape(match.group("href"))
        link = urllib.parse.urljoin(source_url, href)
        parsed_link = urllib.parse.urlsplit(link)
        if parsed_link.hostname not in ("www.fsc.go.kr", "fsc.go.kr", "www.korea.kr", "korea.kr", "www.bok.or.kr", "bok.or.kr", "www.kofiu.go.kr", "kofiu.go.kr"):
            continue
        if any(term in parsed_link.path.lower() for term in ("/getfile", "/download", "/filedown")):
            continue
        if parsed_link.path.lower().endswith((".pdf", ".hwp", ".hwpx", ".zip")):
            continue
        context = clean_text(text[max(0, match.start() - 600): match.end() + 1500])
        if not is_policy_candidate(f"{title} {context}", source_name):
            continue

        detail_fetches += 1
        detail_text, detail_error = fetch_text(link, timeout=6, attempts=1)
        if detail_error or not detail_text:
            # A snippet alone cannot establish a dated official policy change.
            continue
        detail_clean = clean_text(detail_text)
        published = official_document_date(title, detail_clean)
        age = age_hours(published, now)
        if age is None or age < -1 or age > MAX_AGE_HOURS:
            continue
        haystack = f"{title} {detail_clean[:9000]}"
        if not is_policy_candidate(haystack, source_name):
            continue
        cbdc_scope = cbdc_claim_scope(title, detail_clean[:8500], source_name)
        if cbdc_scope and any(x in title for x in ("어떻게 다를까", "Q&A", "오해와 진실", "해명")):
            # A repeat explanation of existing policy is not a new stage-changing
            # decision. Continue watching for separately dated formal changes.
            continue
        policy_hits = matched_terms(haystack, POLICY_TERMS + EVENT_TERMS + ACTOR_TERMS)
        high = has_any(haystack, HIGH_IMPACT_TERMS)
        fingerprint = hashlib.sha256(f"{source_name}|{title}|{link}".encode("utf-8")).hexdigest()[:16]
        summary = clip_text(detail_clean, 360)
        deduped[link] = {
            "source": source_name,
            "title": cbdc_display_title(cbdc_scope) if cbdc_scope else stablecoin_title(haystack),
            "original_title": clip_text(title, 120),
            "link": link,
            "summary": summary,
            "published_kst": published.isoformat() if published else "",
            "fingerprint": fingerprint,
            "matched": {
                "korea_cbdc_deposit_token_policy" if cbdc_scope else "korea_stablecoin_policy":
                    policy_hits[:14] or (["기관용 CBDC·예금토큰"] if cbdc_scope else ["스테이블코인 정책"])
            },
            "importance": "상" if high else "중",
            "status": "확정",
            "impacts": ["시간표", "할인율", "수급"],
            "paths": ["정책 타임라인", "규제 강도", "금융 인프라 재편", "표준 선점", "테마 수급"],
            "sectors": SECTORS[:],
            "domestic_stablecoin_policy_watch": True,
            "cbdc_policy_watch": bool(cbdc_scope),
            "cbdc_policy_scope": cbdc_scope,
            "stablecoin_policy_check": POLICY_CHECK,
            "stablecoin_risk_table": (
                "기관용 CBDC·예금토큰·일반인용 CBDC 구별 / 2030년 국고금 25%는 정책목표 / "
                "사용처 제한은 목적성 보조금 실증으로 한정 / 실거래·프라이버시·법적 근거 확인"
                if cbdc_scope else RISK_TABLE
            ),
            "stablecoin_structure_note": STRUCTURE_NOTE,
            "counter": (
                "예금토큰은 은행 발행, 기관용 CBDC는 기관 간 결제에 활용. "
                "2030년 국고금 25%는 목표이지 CBDC 182조원 발행 확정이 아니며, "
                "특정 보조금 사용처 제한을 일반 예금 통제로 확대 해석해서는 안 됩니다."
                if cbdc_scope else COUNTER
            ),
            "reflection": "중간",
        }
    return list(deduped.values())


def crypto_tax_report_candidate(
    primary: str | None,
    secondary: str | None,
    official_guidance: str | None,
    now: dt.datetime,
) -> dict | None:
    """News-reported presidential preference ≠ amendment passed or tax waived."""
    hours = age_hours(CRYPTO_TAX_REPORT_TIME, now)
    if hours is None or hours < -1 or hours > MAX_AGE_HOURS:
        return None

    p = clean_text(primary).lower()
    s = clean_text(secondary).lower()
    # Pin exact 2026-10-25 article; site sidebars alone cannot become a
    # presidential decision. Secondary copy is supplementary, not official.
    primary_ok = bool(
        "2026.10.25" in p
        and "presidential office" in p
        and "crypto tax" in p
        and ("delay" in p or "postpone" in p)
        and "2029" in p
    )
    secondary_ok = bool(
        ("october 25, 2026" in s or "oct. 25" in s or "oct 25" in s)
        and "presidential office" in s
        and "crypto tax" in s
        and ("delay" in s or "postpone" in s)
        and "2029" in s
    )
    if not primary_ok and not secondary_ok:
        return None

    nts = clean_text(official_guidance).lower()
    nts_baseline_confirmed = bool(
        "가상자산" in nts
        and "27.1.1" in nts.replace(" ", "")
        and ("과세" in nts or "분리과세" in nts)
    )
    if primary_ok:
        link, source = CRYPTO_TAX_PRIMARY_REPORT, "서울경제(보도)"
    else:
        link, source = CRYPTO_TAX_SECONDARY_REPORT, "CoinNess(서울경제 보도 재인용)"
    support = "동일 보도 재인용 확인" if primary_ok and secondary_ok else "원문 한 곳만 확인"
    legal_status = (
        "국세청 시행 안내 2027-01-01 유지"
        if nts_baseline_confirmed
        else "국세청 원문 접근 또는 시행일 직접 재확인 실패"
    )
    summary = (
        "2026-10-25 청와대 관계자를 인용한 언론보도: 2027-01-01 예정 가상자산소득 과세를 "
        "추가 유예하는 방향으로 논의. 아직 시행일 변경 법률은 통과·공포되지 않음. "
        "유예 방안은 2029년(김상훈안·박민규 CARF 연동안)과 2030년(김재섭안)으로 다름. "
        f"{legal_status}. {support}. "
        "언론 보도·당정 입장과 국회 의결·법률 공포는 구별."
    )
    return {
        "source": source,
        "title": "가상자산 과세 재유예 방향 보도 · 법률 개정 미확정",
        "title_ko": "가상자산 과세 재유예 방향 보도 · 법률 개정 미확정",
        "original_title": "靑, 가상자산 과세 재유예 결론…청년 여론·美 CARF 고려",
        "link": link,
        "summary": summary,
        "published_kst": CRYPTO_TAX_REPORT_TIME.isoformat(),
        "fingerprint": "crypto-tax:presidential-policy-report:2026-10-25",
        "matched": {
            "korea_crypto_tax_policy": [
                "언론보도: 청와대 관계자 과세 재유예 방향",
                "법률상 현재 예정일 2027-01-01",
                "2029·2030 시행 개정안은 국회 계류",
            ]
        },
        "status": "언론 보도 · 법 개정 전",
        "importance": "상",
        "impacts": ["할인율", "수급", "시간표"],
        "paths": ["국회 입법 단계", "세금/규제 위험", "거래소 투자심리"],
        "sectors": ["가상자산거래소/디지털자산"],
        "domestic_stablecoin_policy_watch": True,
        "crypto_tax_policy_watch": True,
        "crypto_tax_stage": "reported_position_not_enacted",
        "crypto_tax_legal_effective_date": "2027-01-01",
        "crypto_tax_guidance_rechecked": nts_baseline_confirmed,
        "crypto_tax_support_reprint": secondary_ok,
        "crypto_tax_bill_numbers": ["2220914", "2221570", "2221923"],
        "crypto_tax_legal_links": [
            CRYPTO_TAX_OFFICIAL_GUIDANCE,
            CRYPTO_TAX_BILL_2029, CRYPTO_TAX_BILL_CARF, CRYPTO_TAX_BILL_2030,
            CRYPTO_TAX_CARF_OECD,
        ],
        "policy_plain_summary": (
            "청와대 관계자 발언에 대한 재유예 방향 보도이며 법 개정 확정이 아님. "
            "현행 과세 개시 예정일 2027-01-01, 공제 250만원, 국세 20% 및 지방세 포함 22%."
        ),
        "investment_view": "세금 부담이 연기될 기대는 투자심리에 우호적이나 법 통과 전이므로 확정 세제 혜택으로 판단 금지.",
        "counter": "2027년 시행 예정 현행 법률은 유효하며 당정 합의·국회 의결·공포가 아직 필요.",
        "reflection": "미확정",
    }


def crypto_tax_news_candidates(now: dt.datetime) -> list[dict]:
    if not (-1 <= (age_hours(CRYPTO_TAX_REPORT_TIME, now) or -2) <= MAX_AGE_HOURS):
        return []

    verified = {}
    for key, url in (
        ("primary", CRYPTO_TAX_PRIMARY_REPORT),
        ("secondary", CRYPTO_TAX_SECONDARY_REPORT),
        ("nts", CRYPTO_TAX_OFFICIAL_GUIDANCE),
    ):
        body, error = fetch_text(url, timeout=7, attempts=1)
        verified[key] = body if error is None else None
        if error:
            print(f"crypto_tax_source_warning={key} error={error}")
    candidate = crypto_tax_report_candidate(
        verified["primary"], verified["secondary"], verified["nts"], now
    )
    if candidate:
        print(
            "crypto_tax_stage=reported_position_not_enacted "
            f"nts_rechecked={str(candidate['crypto_tax_guidance_rechecked']).lower()} "
            f"reprint_found={str(candidate['crypto_tax_support_reprint']).lower()}"
        )
        return [candidate]
    return []


def load_seen() -> dict:
    if not SEEN_PATH.exists():
        return {"seen": {}, "updated_at_kst": ""}
    try:
        return json.loads(SEEN_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"seen": {}, "updated_at_kst": ""}


def save_seen(seen: dict, now: dt.datetime) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    seen["updated_at_kst"] = now.isoformat(timespec="seconds")
    SEEN_PATH.write_text(json.dumps(seen, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def semantic_key(item: dict) -> str:
    if item.get("crypto_tax_policy_watch"):
        return f"crypto-tax:{item.get('crypto_tax_stage') or 'unknown'}:2026-10-25"
    if item.get("domestic_stablecoin_policy_watch"):
        # Do not deduplicate every different announcement into four fixed template
        # titles. Distinct official documents on different dates remain distinct.
        original = clean_text(item.get("original_title") or item.get("title") or "")
        normalized = re.sub(r"[^0-9A-Za-z가-힣]+", "", original).lower()[:150]
        published = str(item.get("published_kst") or "")[:10]
        group = "cbdc" if item.get("cbdc_policy_watch") else "stablecoin"
        return f"{group}:event:{normalized}:{published}"
    return str(item.get("fingerprint") or item.get("link") or item.get("title") or "")


def semantic_fingerprint(item: dict) -> str:
    return "semantic:" + hashlib.sha256(semantic_key(item).encode("utf-8")).hexdigest()[:16]


def merge_terms(left: dict, right: dict) -> dict:
    merged = {key: list(value) for key, value in (left or {}).items()}
    for key, values in (right or {}).items():
        bucket = merged.setdefault(key, [])
        for value in values:
            if value not in bucket:
                bucket.append(value)
    return merged


def merge_policy_duplicates(items: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for item in items:
        key = semantic_key(item)
        source_fp = str(item.get("fingerprint") or "")
        source_link = {
            "source": item.get("source") or "",
            "link": item.get("link") or "",
            "published_kst": item.get("published_kst") or "",
            "original_title": item.get("original_title") or item.get("title") or "",
        }
        if key not in merged:
            current = dict(item)
            current["fingerprint"] = semantic_fingerprint(item)
            current["source_fingerprints"] = [source_fp] if source_fp else []
            current["source_links"] = [source_link]
            merged[key] = current
            continue

        current = merged[key]
        if source_fp and source_fp not in current.setdefault("source_fingerprints", []):
            current["source_fingerprints"].append(source_fp)
        if not any(link.get("link") == source_link["link"] for link in current.setdefault("source_links", [])):
            current["source_links"].append(source_link)

        sources = []
        for link in current.get("source_links", []):
            source = clean_text(link.get("source") or "")
            if source and source not in sources:
                sources.append(source)
        current["source"] = " / ".join(sources[:3]) if sources else current.get("source")
        current["matched"] = merge_terms(current.get("matched") or {}, item.get("matched") or {})
        if item.get("importance") == "상":
            current["importance"] = "상"
        if not current.get("published_kst") and item.get("published_kst"):
            current["published_kst"] = item.get("published_kst")
    return list(merged.values())


def load_existing_alerts() -> list[dict]:
    if not ALERTS_JSON_PATH.exists():
        return []
    try:
        data = json.loads(ALERTS_JSON_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def write_alerts(alerts: list[dict]) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    ALERTS_JSON_PATH.write_text(json.dumps(alerts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    now = now_kst()
    candidates: list[dict] = []
    for source_name, source_url in SOURCES:
        text, error, effective_url = fetch_source_text(source_name, source_url)
        if error:
            record_source_failure(
                lane="domestic_stablecoin",
                source_name=source_name,
                source_url=source_url,
                error=error,
                checked_at=now,
            )
            print(f"domestic_stablecoin_source_failed source={source_name} error={error}")
            continue
        candidates.extend(parse_links(text or "", source_name, effective_url, now))
    # Reported presidential policy direction is deliberately kept separate
    # from BOK/CBDC official policy and from a law being enacted.
    candidates.extend(crypto_tax_news_candidates(now))
    candidates = merge_policy_duplicates(candidates)

    seen = load_seen()
    seen_map = seen.setdefault("seen", {})
    new_alerts: list[dict] = []
    for item in sorted(candidates, key=lambda x: x.get("importance") != "상"):
        fps = [str(item.get("fingerprint") or "")]
        fps.extend(str(fp) for fp in item.get("source_fingerprints", []) if fp)
        fps = [fp for fp in dict.fromkeys(fps) if fp]
        if any(fp in seen_map for fp in fps):
            continue
        new_alerts.append(item)
        seen_entry = {
            "title": item.get("original_title") or item.get("title"),
            "source": item.get("source"),
            "link": item.get("link"),
            "first_seen_kst": now.isoformat(timespec="seconds"),
            "importance": item.get("importance"),
        }
        for fp in fps:
            seen_map[fp] = seen_entry
        if len(new_alerts) >= MAX_ALERTS:
            break

    if not new_alerts:
        print(
            f"domestic_stablecoin_alerts=0 candidates={len(candidates)} "
            f"official_cbdc_candidates={sum(bool(x.get('cbdc_policy_watch')) for x in candidates)} "
            "known_baseline=2030_national_treasury_25pct_target;retail_cbdc_not_planned"
        )
        return 0

    existing = load_existing_alerts()
    existing_keys = {str(item.get("fingerprint") or item.get("link") or "") for item in existing}
    merged = existing[:]
    for item in new_alerts:
        key = str(item.get("fingerprint") or item.get("link") or "")
        if key not in existing_keys:
            merged.append(item)
            existing_keys.add(key)
    write_alerts(merged)
    save_seen(seen, now)
    print(f"domestic_stablecoin_alerts={len(new_alerts)} candidates={len(candidates)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
