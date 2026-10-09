# Follow-up candidate processing trigger: EU diesel reserve policy
# China refined fuel export suspension/resumption watch
#!/usr/bin/env python3
"""이란·호르무즈 지정학 완화와 시장 확인 조건을 감시한다.

외부 패키지 없이 GitHub Actions에서 실행한다. 뉴스는 Google News RSS에서
신뢰 매체의 제목을 교차 확인하고, 시장 값은 Yahoo Finance 차트 엔드포인트를
사용한다. Telegram 전송은 워크플로가 담당하며 이 스크립트는 전송용 파일과
확정 후 반영할 상태 파일을 만든다.
"""

from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import hashlib
import html
import json
import math
import os
import pathlib
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
UTC = dt.timezone.utc
OUT_DIR = pathlib.Path("out")
STATE_PATH = pathlib.Path("data/iran_hormuz_market_turn_state.json")
TITLE_PATH = OUT_DIR / "iran_hormuz_market_turn_title.txt"
BODY_PATH = OUT_DIR / "iran_hormuz_market_turn_alert.md"
ALERT_JSON_PATH = OUT_DIR / "iran_hormuz_market_turn_alert.json"
SUMMARY_PATH = OUT_DIR / "iran_hormuz_market_turn_watch.md"
PENDING_STATE_PATH = OUT_DIR / "iran_hormuz_market_turn_pending_state.json"
TELEGRAM_CONFIRMED_PATH = OUT_DIR / "iran_hormuz_market_turn_telegram_confirmed.json"

YAHOO_BASES = (
    "https://query1.finance.yahoo.com/v8/finance/chart",
    "https://query2.finance.yahoo.com/v8/finance/chart",
)
CHINA_REUTERS_20261009_URL = "https://live.euronext.com/en/financial-news/china-resume-october-fuel-exports-after-holiday-pause-sources-say"
HORMUZ_7DAY_XINHUA_URL = "https://english.news.cn/20261009/b23dc5dd06f242e991ad5dfe3eed727c/c.html"
MMA_OIL_ISAIAS_OCT7_URL = "https://www.bsee.gov/newsroom/latest-news/statements-and-releases/press-releases/mma-monitors-gulf-response-isaias"
MMA_OIL_ISAIAS_OCT8_URL = "https://www.bsee.gov/newsroom/latest-news/statements-and-releases/press-releases/mma-monitors-gulf-response-isaias2"
EIA_REFINING_WEEKLY_URL = "https://www.eia.gov/dnav/pet/pet_pri_spt_s1_w.htm"
EIA_REFINING_SOURCE = "미국 에너지정보청(EIA)"
# Only distinct weekly observations and material changes can trigger a message.
EIA_REFINING_MIN_ABS_WEEKLY_MOVE_USD = 5.0
EIA_REFINING_MIN_LEVEL_USD = 40.0

KPLER_STS_URL = (
    "https://www.kpler.com/blog/"
    "saudi-export-rerouting-amid-gulf-of-oman-sts-bottlenecks-amplify-vlcc-intensity-of-meg-flows"
)
KPLER_PREWAR_EXPORT_URL = (
    "https://www.kpler.com/blog/"
    "explainer-how-mideast-gulf-crude-exports-returned-to-pre-war-levels"
)
EU_DIESEL_RESERVE_URL = (
    "https://www.euronews.com/2026/10/01/"
    "releasing-strategic-reserves-is-a-possibility-eu-energy-chief-tells-euronews-as-diesel-squ"
)
MIDEAST_EXPORT_SNAPSHOT_URLS = (
    "https://www.reuters.com/business/energy/"
    "mideast-oil-exports-rebound-september-saudi-arabia-boosts-shipments-2026-09-28/",
    "https://in.marketscreener.com/news/"
    "mideast-oil-exports-rebound-in-september-as-saudi-arabia-boosts-shipments-ce785addd888f724",
)
SAUDI_NOVEMBER_OSP_URLS = (
    "https://boereport.com/2026/10/04/saudi-arabia-unexpectedly-cuts-oil-prices-to-asia/amp/",
    "https://www.argaam.com/en/article/articledetail/id/1941273",
)
MIDEAST_PRODUCT_GAP_URLS = (
    "https://getnews.co.kr/news/articleView.html?idxno=882308",
    "https://www.moneycontrol.com/news/business/"
    "mideast-crude-oil-flows-hit-98-of-pre-war-level-jpmorgan-says-14041480.html",
    "https://www.businesstimes.com.sg/companies-markets/energy-commodities/"
    "jpmorgan-and-goldman-see-middle-east-oil-flows-near-pre-war-levels/",
)

NEWS_QUERIES = (
    'Iran ceasefire agreement OR Iran truce agreement OR "US Iran ceasefire" when:3d',
    'US ends attacks Iran OR US halts strikes Iran OR US ceases military operations Iran when:3d',
    '"Strait of Hormuz reopens" OR "shipping resumes" Hormuz OR "traffic returns to normal" Hormuz when:3d',
    '"Gulf oil exports" recover OR "Middle East oil exports" rebound OR "Saudi crude shipments" September when:3d',
    '"Middle East oil exports" "highest level since" Iran war Kpler when:3d',
    '"Middle East crude exports" Kpler September highest since war when:3d',
    '"16.328 million barrels per day" Middle East exports Kpler when:3d',
    '"Hormuz" "9.719 million bpd" Kpler September when:3d',
    '"Saudi Arabia ramps up Gulf oil exports" OR "Aramco to boost Gulf exports" when:7d',
    '"Saudi Arabia unexpectedly cuts oil prices to Asia" Aramco OSP when:7d',
    '"Arab Light" OSP Asia Oman Dubai Saudi Aramco when:7d',
    '"Saudi Aramco sets" crude OSP Asia when:7d',
    '사우디 아람코 아시아 원유 공식판매가격 OSP when:7d',
    '"Gulf of Oman" STS record OR "ship-to-ship" Oman Saudi crude when:7d',
    'Kpler "Gulf of Oman" STS bottlenecks VLCC when:7d',
    'Kpler "pre-war levels" Middle East Gulf crude excluding Iran when:7d',
    '"40% bypass Hormuz" Kpler crude when:7d',
    '"16.5 mbd" "excluding Iran" Kpler when:7d',
    '"Hormuz" "9.9 mbd" Kpler when:7d',
    '"Hormuz oil shipments" six-month high OR "record oil" Hormuz when:7d',
    '"East-West Pipeline" 3.5 million barrels per day Saudi when:3d',
    '"East-West Pipeline" pumping 3.5 million bpd Yanbu when:3d',
    '"East-West Pipeline" 4 million bpd Yanbu Saudi when:3d',
    '"East-West Pipeline" 80% capacity Saudi when:3d',
    '"East-West Pipeline" 6 million barrels Saudi when:3d',
    '"Saudi Arabia Hikes Oil Flow on Key Pipeline to Over 80% Capacity" when:3d',
    '"Yanbu" crude loadings resume East-West Pipeline when:3d',
    '"Middle East crude exports" September Kpler Reuters when:3d',
    '"Hormuz" "80% of prewar" oil flows Kpler when:3d',
    '"Middle East crude" 98% pre-war JPMorgan when:3d',
    '"17.5 million barrels" JPMorgan Middle East oil when:3d',
    '"product flows" 58% diesel gasoline JPMorgan Middle East when:3d',
    'JP모건 중동 원유 수출 98% 정제유 58% when:3d',
    '"diesel export ban" Trump White House when:3d',
    '"diesel export restrictions" voluntary US when:3d',
    '"diesel export ban" considering Trump when:3d',
    '"still considering diesel export ban" Trump Reuters when:3d',
    '미국 디젤 수출 금지 검토 백악관 when:3d',
    '"strategic reserves" diesel EU energy chief Jorgensen when:3d',
    '"50 million barrels" diesel EU reserves France when:3d',
    '"Europe weighs" diesel stocks release when:3d',
    'EU 경유 전략비축유 방출 검토 요르겐센 when:3d',
    '"G7 agrees to release" 100mn barrels diesel crude when:1d',
    '"100 million barrels" G7 diesel crude Financial Times when:1d',
    '"Europe agrees to release diesel reserves immediately" Trump when:1d',
    '"Trump" Europe diesel reserves immediately AP when:1d',
    'G7 디젤 원유 1억배럴 방출 트럼프 즉시 방출 when:1d',
    '"Chinese refiners suspend" fuel exports PetroChina when:3d',
    '"China" fuel exports resume PetroChina October 7 when:7d',
    '"China to resume October fuel exports" "four trade sources" when:3d',
    '"China" "3.7 million metric tons" fuel exports when:3d',
    '"China" "fuel shipments loaded" October 2026 when:3d',
    '"Araghchi" "seven-day plan" US views Hormuz when:3d',
    '아라그치 호르무즈 7일 이내 재개방 미국 의견 검토 when:3d',
    'Isaias oil production shut in MMA Gulf of Mexico when:3d',
    '"China" refined product exports suspended Beijing green light when:7d',
    '"China" gasoline jet fuel cargoes cancelled PetroChina when:7d',
    '중국 정유사 정제품 수출 중단 페트로차이나 when:7d',
    '"Gulf crude" India 1.52 million bpd Kpler September when:7d',
    '"Saudi Arabia resumes oil exports" Yanbu East-West Pipeline when:3d',
    '"East-West pipeline starts exports" Saudi Yanbu when:3d',
    '"overseas shipments have now resumed" Saudi East-West Pipeline when:3d',
)

TRUSTED_SOURCE_ALIASES = (
    "reuters",
    "associated press",
    "ap news",
    "bloomberg",
    "bbc",
    "financial times",
    "the wall street journal",
    "wall street journal",
    "the new york times",
    "new york times",
    "cnn",
    "nbc news",
    "abc news",
    "cbs news",
    "the guardian",
    "al jazeera",
    "france 24",
    "afp",
    "the white house",
    "white house",
    "u.s. department of state",
    "us department of state",
    "u.s. department of defense",
    "us department of defense",
    "u.s. central command",
    "us central command",
    "centcom",
    "international maritime organization",
    "ukmto",
    "iranian foreign ministry",
    "iran ministry of foreign affairs",
    "연합뉴스",
    "로이터",
    "ap통신",
    "블룸버그",
    "bbc 코리아",
    "business times",
    "moneycontrol",
    "livemint",
    "mint",
    "news1",
    "newsis",
    "뉴시스",
    "euronews",
    "xinhua",
    "anadolu agency",
    "tasnim",
    "irna",
    "boe report",
    "argaam",
    "marketscreener",
    "s&p global",
    "platts",
    "kpler",
    "vortexa",
    "saudi ministry of energy",
    "ministry of energy saudi arabia",
    "saudi aramco",
    "aramco",
)

NEGATIVE_OR_TENTATIVE_PHRASES = (
    "ceasefire hopes",
    "truce hopes",
    "peace hopes",
    "hopes for",
    "in hope of",
    "could agree",
    "may agree",
    "might agree",
    "possible agreement",
    "proposed ceasefire",
    "ceasefire proposal",
    "calls for ceasefire",
    "seeks ceasefire",
    "talks continue",
    "talks resume",
    "negotiations continue",
    "considering",
    "reportedly considering",
    "hold off",
    "held off",
    "pause attacks",
    "pause strikes",
    "temporarily halt",
    "temporary halt",
    "for now",
    "not yet",
    "no agreement",
    "deal elusive",
    "휴전 기대",
    "합의 기대",
    "협상 재개",
    "협상 중",
    "공격 보류",
    "일시 중단",
    "검토 중",
    "가능성",
)

EVENT_LABELS = {
    "ceasefire": "미국·이란의 최종 휴전·합의",
    "us_attack_end": "미국의 대이란 공격 중단 공식화",
    "hormuz_normalization": "호르무즈 해협의 실질적 통행 정상화",
    "oil_flow_recovery": "중동 원유 수출·호르무즈 물류 회복",
    "sts_reroute_expansion": "걸프오브오만 STS 우회 물류 급증·병목",
    "ex_iran_crude_prewar_recovery": "이란 제외 걸프 원유 수출 전쟁 전 100% 회복",
    "saudi_asia_osp_change": "사우디 아시아 원유 공식판매가격(OSP) 변화",
    "eia_refining_crack_watch": "미국 공식 현물 정제마진·가격 병목 변화",
    "east_west_pipeline_recovery": "사우디 East-West Pipeline 실물 회복",
    "regional_export_recovery": "중동 원유 수출 회복 단계 상향",
    "crude_product_divergence": "중동 원유 98% 회복·정제품 병목",
    "us_diesel_export_policy": "미국 디젤 수출정책 단계 변화",
    "eu_diesel_reserve_policy": "EU 경유 전략비축유 방출 단계 변화",
    "g7_reserve_release_agreement": "G7 경유·원유 전략비축유 방출 합의",
    "china_fuel_export_policy": "중국 정제품 수출정책 단계 변화",
    "hormuz_7day_diplomacy": "호르무즈 7일 이내 재개방 제안·미국 의견 검토",
    "us_gulf_isaias_shutin": "미국 허리케인 해상 원유 생산중단 변화",
    "india_gulf_import_recovery": "인도 걸프산 원유 유입 회복",
}
DATA_PROVIDER_ALIASES = ("kpler", "vortexa", "jodi")


@dataclass(frozen=True)
class NewsItem:
    title: str
    source: str
    link: str
    published_utc: str
    published_epoch: float
    event_kind: str


@dataclass(frozen=True)
class SymbolSpec:
    symbol: str
    label: str
    unit: str


@dataclass(frozen=True)
class Quote:
    symbol: str
    label: str
    unit: str
    price: float
    previous_close: float
    change: float
    change_pct: float
    timestamp_utc: str
    timestamp_epoch: float


SYMBOLS = {
    "us2y": SymbolSpec("^UST2Y", "미국 2년물 국채금리", "%"),
    "dxy": SymbolSpec("DX-Y.NYB", "달러인덱스", ""),
    "wti": SymbolSpec("CL=F", "WTI", "달러/배럴"),
    "brent": SymbolSpec("BZ=F", "Brent", "달러/배럴"),
    "usdkrw": SymbolSpec("KRW=X", "원·달러", "원/달러"),
}


def now_utc() -> dt.datetime:
    return dt.datetime.now(UTC)


def normalize_text(value: str) -> str:
    value = html.unescape(value or "")
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r"\s+", " ", value).strip().lower()
    return value


def _source_name_ko(source: str) -> str:
    low = normalize_text(source)
    mappings = (
        ("jpmorgan via bloomberg", "JP모건·블룸버그"),
        ("bnn bloomberg", "BNN 블룸버그"),
        ("bloomberg", "블룸버그"),
        ("reuters", "로이터"),
        ("xinhua", "신화통신"),
        ("anadolu agency", "아나돌루통신"),
        ("mma", "미 해양광물관리청"),
        ("financial times", "파이낸셜타임스"),
        ("associated press", "AP"),
        ("ap news", "AP"),
        ("business times", "비즈니스타임스"),
        ("livemint", "라이브민트"),
        ("moneycontrol", "머니컨트롤"),
        ("euronews", "유로뉴스"),
        ("boe report", "BOE Report"),
        ("argaam", "아르가암"),
        ("newsis", "뉴시스"),
        ("뉴시스", "뉴시스"),
        ("news1", "뉴스1"),
        ("marketscreener", "마켓스크리너"),
    )
    for key, label in mappings:
        if key in low:
            return label
    return source


def _news_title_ko(row: NewsItem) -> str:
    title = html.unescape(str(row.title or "")).strip()
    if not title:
        return EVENT_LABELS.get(row.event_kind, "관련 보도")
    if re.search(r"[가-힣]", title) and not re.search(r"[A-Za-z]{5,}", title):
        return title

    low = normalize_text(title)
    kind = row.event_kind

    if kind == "china_fuel_export_policy":
        stage = _china_fuel_export_stage(title)
        if stage == "planned_resume":
            return "중국, 10월 정제품 수출 재개 예정…Reuters 관계자 보도·실제 선적 미확인"
        if stage == "approval_reported":
            return "중국 10월 수출 승인 물량 보도…실제 선적 미확인"
        if stage == "physical_resumed":
            return "중국 정제품 실제 출항·선적 재개 확인"
        if stage == "resumption_reported":
            return "중국 정제품 수출 재개 보도…실제 출항 확인 필요"
        if stage == "cargo_cancelled":
            return "중국 정유사, 10월 정제품 수출 중단…PetroChina 일부 휘발유·항공유 화물 취소"
        if stage == "resumed":
            return "중국, 정제품 수출 재개·허용"
        if stage == "extended":
            return "중국, 정제품 수출 중단·제한 연장"
        if stage == "restricted":
            return "중국, 정제품 수출 제한"
        return "중국 정유사, 10월 정제품 수출 중단"

    if kind == "hormuz_7day_diplomacy":
        return "이란 외무장관, 호르무즈 7일 이내 개방 제안의 미국 답변 검토"
    if kind == "us_gulf_isaias_shutin":
        return "미국 해양광물관리청, 허리케인 Isaias 해상 원유생산 중단 집계"
    if kind == "g7_reserve_release_agreement":
        stage = _g7_reserve_stage(title)
        labels = {
            "release_started": "G7·IEA, 경유·원유 전략비축유 실제 방출 시작",
            "agreed_100m": "G7, 경유·원유 전략비축유 1억 배럴 방출 합의",
            "immediate_diesel": "트럼프, 유럽이 비축 경유를 즉시 방출하기로 합의했다고 발표",
            "proposal_100m": "유럽·IEA, 경유 5,000만 배럴+원유 5,000만 배럴 방출안 논의",
        }
        return labels.get(stage, "G7 경유·원유 전략비축유 방출 합의 보도")

    if kind == "eu_diesel_reserve_policy":
        stage = _eu_diesel_reserve_stage(title)
        labels = {
            "released": "EU 회원국, 경유 전략비축유 실제 방출",
            "approved": "EU 회원국, 경유 전략비축유 방출 승인",
            "proposal_50m": "유럽, 경유 전략비축유 5,000만 배럴 방출안 논의",
            "considering": "EU 에너지 책임자, 경유 전략비축유 방출 검토",
            "coordinating": "EU·IEA, 경유 전략비축유 공동대응 협의",
            "rejected": "EU, 경유 전략비축유 추가 방출안 보류·거부",
        }
        return labels.get(stage, "EU 경유 전략비축유 방출정책 변화")

    if kind == "us_diesel_export_policy":
        stage = _diesel_policy_stage(title)
        labels = {
            "effective": "미국, 디젤 수출 금지·제한 시행",
            "announced": "미국, 디젤 수출금지 발표",
            "supports": "미국 대통령, 디젤 수출금지 방안 지지·요구",
            "considering": "백악관, 미국 디젤 수출금지 여부 검토",
            "voluntary": "미국 정부, 정유사 자발적 디젤 수출 제한 논의",
            "denied": "백악관, 미국 디젤 수출금지 검토 보도 부인",
            "withdrawn": "미국, 디젤 수출금지 계획 철회",
        }
        return labels.get(stage, "미국 디젤 수출정책 변화")

    if kind == "eia_refining_crack_watch":
        return "미국 에너지정보청, WTI·휘발유·경유 현물가격으로 계산한 정제마진 변화"

    if kind == "crude_product_divergence":
        return "JP모건, 중동 원유 흐름은 전쟁 전 수준에 근접했지만 정제품 회복은 지연"

    if kind == "regional_export_recovery":
        return "중동 원유 수출, 전쟁 이후 최고 수준으로 회복"

    if kind == "oil_flow_recovery":
        if "prices settle down" in low or "prices fall" in low or "prices decline" in low:
            return "중동 원유 수출 회복 조짐에 국제유가 하락"
        return "중동 원유 수출·호르무즈 물류 회복"

    if kind == "sts_reroute_expansion":
        return "오만만 선박 간 이송 급증·VLCC 병목 심화"

    if kind == "ex_iran_crude_prewar_recovery":
        return "Kpler, 이란 제외 걸프 원유 수출 16.5 Mbd로 전쟁 전 수준 회복"

    if kind == "saudi_asia_osp_change":
        return "Saudi Aramco, 11월 아시아 Arab Light 공식판매가격을 Oman/Dubai 대비 배럴당 5달러 할인으로 인하"

    if kind == "east_west_pipeline_recovery":
        if "80% capacity" in low or "over 80% capacity" in low or "above 80% capacity" in low:
            return "사우디 East-West Pipeline, 최대 수송능력의 80% 이상으로 회복"
        if any(term in low for term in ("yanbu", "loadings resume", "exports resume", "resumes oil exports")):
            return "사우디 East-West Pipeline 복구 후 Yanbu 원유 선적 재개"
        return "사우디 East-West Pipeline 유량 회복"

    if kind == "india_gulf_import_recovery":
        return "인도, 걸프산 원유 수입 회복"

    if kind == "ceasefire":
        return "미국·이란 최종 휴전 합의"
    if kind == "us_attack_end":
        return "미국, 대이란 공격 중단 공식화"
    if kind == "hormuz_normalization":
        return "호르무즈 해협 실질 통행 정상화"

    return EVENT_LABELS.get(kind, "관련 보도")


def finite_number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def fetch_bytes(url: str, timeout: int = 20, attempts: int = 3) -> bytes:
    headers = {
        "Accept": "application/rss+xml, application/xml, text/xml, application/json;q=0.9, */*;q=0.8",
        "User-Agent": "Mozilla/5.0 iran-hormuz-market-turn-alert/1.0",
    }
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(0.5 * (2**attempt))
    raise RuntimeError(f"요청 실패: {url} · {last_error}")


def fetch_json(url: str) -> dict:
    try:
        return json.loads(fetch_bytes(url).decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"JSON 해석 실패: {url} · {exc}") from exc


def source_is_trusted(source: str) -> bool:
    low = normalize_text(source)
    return any(alias in low for alias in TRUSTED_SOURCE_ALIASES)


def classify_event(title: str) -> str | None:
    low = normalize_text(title)
    if not low:
        return None

    diesel_policy_context = any(
        term in low
        for term in (
            "diesel export ban", "diesel-export ban", "diesel export restriction",
            "diesel-export restriction", "diesel export cap", "diesel-export cap",
            "디젤 수출 금지", "디젤 수출 제한", "경유 수출 금지", "경유 수출 제한",
        )
    )
    us_policy_actor = any(
        term in low
        for term in (
            "white house", "trump", "u.s.", "united states", "energy secretary",
            "백악관", "트럼프", "미국", "에너지장관",
        )
    )
    if diesel_policy_context and us_policy_actor:
        return "us_diesel_export_policy"

    g7_release_agreement = (
        (
            any(term in low for term in ("g7", "group of seven", "주요 7개국"))
            and any(term in low for term in ("diesel", "crude", "oil", "경유", "원유"))
            and any(term in low for term in ("release", "agrees", "agreed", "방출", "합의"))
            and any(term in low for term in ("100 million", "100mn", "1억", "50 million", "5,000만"))
        )
        or (
            any(term in low for term in ("europe agrees", "european countries have agreed", "유럽이", "유럽 국가"))
            and any(term in low for term in ("diesel reserves", "diesel oil reserves", "비축 경유", "경유 비축"))
            and any(term in low for term in ("immediately", "immediate", "즉시", "방출"))
        )
    )
    if g7_release_agreement:
        return "g7_reserve_release_agreement"

    eu_reserve_context = (
        any(term in low for term in ("eu", "europe", "european", "jorgensen", "jørgensen", "유럽연합", "유럽", "요르겐센"))
        and any(term in low for term in ("diesel", "gasoil", "경유", "디젤"))
        and any(term in low for term in ("strategic reserve", "strategic diesel reserve", "strategic fuel reserve", "strategic stock", "emergency stock", "emergency reserve", "reserve release", "stock release", "비축유", "전략비축", "비축"))
        and any(term in low for term in ("release", "releasing", "consider", "considering", "discuss", "weigh", "proposal", "방출", "검토", "논의", "협의"))
    )
    if eu_reserve_context:
        return "eu_diesel_reserve_policy"

    china_context = any(term in low for term in ("china", "chinese", "beijing", "petrochina", "sinopec", "zhejiang petrochemical", "중국", "베이징", "페트로차이나", "시노펙"))
    china_product_export_context = any(term in low for term in (
        "fuel exports", "oil product exports", "refined product exports",
        "gasoline exports", "diesel exports", "jet fuel exports",
        "product shipments", "fuel shipments",
        "정제품 수출", "석유제품 수출", "경유 수출", "휘발유 수출", "항공유 수출",
    ))
    china_policy_change = any(term in low for term in (
        "set to resume", "to resume", "will resume", "expected to resume", "resumption", "재개 예정",
        "suspend", "suspended", "suspension", "halt", "halts", "halted",
        "cancel", "cancels", "cancelled", "canceled", "no green light",
        "restrict", "restriction", "curb", "curbs",
        "resume", "resumes", "resumed", "reopen", "restart", "allow", "permits", "permitting",
        "중단", "보류", "취소", "제한", "재개", "허용", "승인",
    ))
    if china_context and china_product_export_context and china_policy_change:
        return "china_fuel_export_policy"

    if (
        any(v in low for v in ("araghchi","아라그치"))
        and any(v in low for v in ("7-day","seven-day","7일"))
        and any(v in low for v in ("hormuz","호르무즈"))
        and any(v in low for v in ("review","proposal","response","views","검토","제안","답변"))
    ):
        return "hormuz_7day_diplomacy"

    jpmorgan_recovery_context = (
        ("jpmorgan" in low or "jp모건" in low or "jp 모건" in low)
        and any(term in low for term in ("middle east", "mideast", "중동"))
        and any(term in low for term in ("98% of pre-war", "98% of prewar", "98% 복구", "98% 회복", "17.5 million"))
    )
    product_gap_context = (
        any(term in low for term in ("product flows", "refined product", "diesel and gasoline", "정제유", "정제품"))
        and any(term in low for term in ("58%", "3 million", "3.0 mbd"))
    )
    if jpmorgan_recovery_context or product_gap_context:
        return "crude_product_divergence"

    if any(phrase in low for phrase in NEGATIVE_OR_TENTATIVE_PHRASES):
        return None

    has_iran = "iran" in low or "이란" in low
    has_us = any(term in low for term in ("u.s.", "us ", "united states", "america", "미국"))

    ceasefire_phrases = (
        "agree to ceasefire",
        "agreed to ceasefire",
        "ceasefire agreed",
        "cease-fire agreed",
        "ceasefire agreement",
        "cease-fire agreement",
        "truce agreed",
        "truce agreement",
        "final agreement signed",
        "final deal signed",
        "peace deal signed",
        "ceasefire takes effect",
        "cease-fire takes effect",
        "최종 휴전 합의",
        "휴전 합의 체결",
        "휴전에 합의",
        "평화협정 체결",
        "최종 합의 체결",
    )
    if has_iran and any(phrase in low for phrase in ceasefire_phrases):
        return "ceasefire"

    attack_end_phrases = (
        "ends attacks on iran",
        "ends strikes on iran",
        "halts attacks on iran",
        "halts strikes on iran",
        "stops attacks on iran",
        "stops strikes on iran",
        "ceases attacks on iran",
        "ceases military operations against iran",
        "military operations against iran have ended",
        "officially ends iran strikes",
        "대이란 공격 종료",
        "이란 공격 공식 중단",
        "이란 공습 공식 종료",
        "대이란 군사작전 종료",
    )
    if has_iran and has_us and any(phrase in low for phrase in attack_end_phrases):
        return "us_attack_end"

    saudi_osp_context = (
        any(term in low for term in ("saudi", "aramco", "사우디", "아람코"))
        and any(term in low for term in ("official selling price", "osp", "oil prices to asia", "crude prices to asia", "공식판매가격", "아시아 원유 가격"))
        and any(term in low for term in ("cut", "cuts", "raise", "raises", "set", "sets", "slash", "slashed", "인하", "인상", "책정"))
    )
    if saudi_osp_context:
        return "saudi_asia_osp_change"

    ex_iran_prewar_context = (
        any(term in low for term in ("excluding iran", "outside iran", "이란 제외"))
        and any(term in low for term in ("middle east gulf", "mideast gulf", "gulf crude", "걸프 원유"))
        and any(term in low for term in ("pre-war level", "prewar level", "pre-war levels", "전쟁 전 수준", "전쟁 이전 수준"))
        and any(term in low for term in ("16.5", "100%"))
    )
    if ex_iran_prewar_context:
        return "ex_iran_crude_prewar_recovery"

    regional_export_phrases = (
        "middle east crude exports", "mideast oil exports", "middle east oil exports",
        "highest since the war", "highest since the iran war", "highest since february",
        "80% of prewar", "80% of pre-war", "prewar oil flow", "pre-war oil flow",
        "중동 원유 수출", "전쟁 이전 대비", "전쟁 전 대비",
    )
    if any(term in low for term in regional_export_phrases):
        has_volume = re.search(
            r"\b(?:[1-9]|1[0-9]|2[0-9])(?:\.[0-9]+)?\s*(?:million\s+(?:barrels\s+per\s+day|bpd)|mbd)\b",
            low,
            flags=re.I,
        ) is not None
        has_recovery_context = any(term in low for term in (
            "highest since", "rebound", "recover", "recovered", "prewar", "pre-war",
            "전쟁 이전", "전쟁 전", "전쟁 후 최고", "snapshot"
        ))
        if has_volume and has_recovery_context:
            return "regional_export_recovery"

    india_import_phrases = (
        "gulf crude imports to india", "gulf arrivals", "gulf oil supplies to india",
        "india imports from middle east", "india's middle east imports", "인도 걸프산", "인도 중동산",
    )
    if any(term in low for term in india_import_phrases) and any(
        term in low for term in ("1.52", "recover", "recovered", "surge", "rise", "회복", "증가")
    ):
        return "india_gulf_import_recovery"

    if (
        any(term in low for term in ("saudi", "saudi arabia", "aramco", "사우디", "아람코"))
        and any(term in low for term in ("pipeline", "송유관"))
        and any(term in low for term in ("80% capacity", "over 80% capacity", "above 80% capacity", "80% 이상", "80% 넘"))
    ):
        return "east_west_pipeline_recovery"

    pipeline_export_resume_phrases = (
        "resumes oil exports",
        "resume oil exports",
        "starts exports after repairs",
        "starts exports",
        "export shipments resume",
        "shipments have now resumed",
        "overseas shipments have now resumed",
        "crude loadings resume",
        "loadings resume",
        "yanbu exports resume",
        "yanbu oil exports resume",
        "수출 재개",
        "선적 재개",
    )
    if (
        any(term in low for term in ("east-west pipeline", "east west pipeline", "yanbu", "petroline", "동서 송유관"))
        and any(term in low for term in pipeline_export_resume_phrases)
    ):
        return "east_west_pipeline_recovery"

    pipeline_recovery_phrases = (
        "east-west pipeline",
        "east west pipeline",
        "petroline",
        "yanbu pipeline",
        "동서 송유관",
        "east–west pipeline",
    )
    pipeline_rate_terms = (
        "million barrels per day", "million bpd", "mbd", "barrels per day",
        "pumping", "flow", "flows", "transport", "throughput", "수송", "송유",
    )
    pipeline_recovery_terms = (
        "restart", "restarted", "resumes", "resumed", "recovery", "hits", "reaches",
        "rises to", "back to", "building up", "increase", "재가동", "회복", "증가",
    )
    if (
        any(term in low for term in pipeline_recovery_phrases)
        and any(term in low for term in pipeline_rate_terms)
        and any(term in low for term in pipeline_recovery_terms)
    ):
        return "east_west_pipeline_recovery"

    flow_recovery_phrases = (
        "ramps up gulf oil exports",
        "boost gulf exports",
        "oil shipments hit six-month high",
        "oil shipments hit a six-month high",
        "highest during the iran war",
        "highest since the iran war",
        "exports recover",
        "exports recovered",
        "export recovery",
        "oil flows rise",
        "oil flows through the strait",
        "middle east exports",
        "gulf oil exports",
        "saudi crude shipments",
        "사우디 원유 수출 회복",
        "걸프 원유 수출 회복",
        "호르무즈 원유 통과 증가",
    )
    if any(phrase in low for phrase in flow_recovery_phrases) and any(
        term in low for term in ("oil", "crude", "barrel", "export", "shipment", "원유", "석유", "수출")
    ):
        return "oil_flow_recovery"

    sts_phrases = (
        "ship-to-ship",
        "ship to ship",
        "sts bottleneck",
        "sts volumes",
        "sts activity",
        "sts transfers",
        "lightering",
        "shuttle trades",
        "gulf of oman",
        "sohar",
        "오만만",
        "선박 간 이송",
    )
    sts_change = (
        "record", "surge", "surged", "rises", "rose", "capacity", "bottleneck",
        "rerouting", "reroute", "boost", "increase", "급증", "기록", "병목", "우회",
    )
    if any(term in low for term in sts_phrases) and any(term in low for term in sts_change):
        return "sts_reroute_expansion"

    hormuz_phrases = (
        "strait of hormuz reopens",
        "hormuz strait reopens",
        "shipping resumes through the strait of hormuz",
        "shipping resumes in the strait of hormuz",
        "traffic returns to normal in the strait of hormuz",
        "hormuz traffic returns to normal",
        "normal transit resumes through hormuz",
        "full passage restored through hormuz",
        "navigation restored in hormuz",
        "호르무즈 해협 통항 정상화",
        "호르무즈 해협 운항 재개",
        "호르무즈 해협 선박 통행 정상화",
        "호르무즈 해협 재개방",
    )
    if ("hormuz" in low or "호르무즈" in low) and any(phrase in low for phrase in hormuz_phrases):
        return "hormuz_normalization"
    return None


def parse_rss(payload: bytes, current: dt.datetime, max_age_hours: int) -> list[NewsItem]:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise RuntimeError(f"RSS 해석 실패: {exc}") from exc

    cutoff = current.timestamp() - max_age_hours * 3600
    results: list[NewsItem] = []
    for node in root.findall(".//item"):
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        source_node = node.find("source")
        source = (source_node.text if source_node is not None and source_node.text else "").strip()
        if not source and " - " in title:
            source = title.rsplit(" - ", 1)[-1].strip()
        published_raw = (node.findtext("pubDate") or "").strip()
        try:
            published = email.utils.parsedate_to_datetime(published_raw)
            if published.tzinfo is None:
                published = published.replace(tzinfo=UTC)
            published = published.astimezone(UTC)
        except (TypeError, ValueError, OverflowError):
            continue
        if published.timestamp() < cutoff or published.timestamp() > current.timestamp() + 600:
            continue
        event_kind = classify_event(title)
        if not event_kind or not source_is_trusted(source):
            continue
        results.append(
            NewsItem(
                title=title,
                source=source,
                link=link,
                published_utc=published.isoformat().replace("+00:00", "Z"),
                published_epoch=published.timestamp(),
                event_kind=event_kind,
            )
        )
    return results


def google_news_url(query: str) -> str:
    params = urllib.parse.urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    return f"https://news.google.com/rss/search?{params}"


def _visible_text(raw_html: str) -> str:
    text = re.sub(r"(?is)<script\b.*?</script>|<style\b.*?</style>", " ", raw_html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def parse_eu_diesel_reserve_snapshot(raw_html: str, current: dt.datetime) -> NewsItem:
    text = _visible_text(raw_html)
    low = normalize_text(text)
    required = (
        any(term in low for term in ("energy commissioner", "dan jørgensen", "dan jorgensen"))
        and "diesel" in low
        and any(term in low for term in ("strategic reserves", "emergency oil-reserve", "emergency stocks", "strategic stocks"))
        and any(term in low for term in ("possibility", "discuss", "release", "releasing"))
    )
    if not required:
        raise RuntimeError("EU diesel reserve interview markers not found")
    title = "EU energy chief considers release of strategic diesel reserves"
    return NewsItem(
        title=title,
        source="Euronews",
        link=EU_DIESEL_RESERVE_URL,
        published_utc=current.isoformat().replace("+00:00", "Z"),
        published_epoch=current.timestamp(),
        event_kind="eu_diesel_reserve_policy",
    )


def parse_saudi_osp_snapshot(
    raw_html: str,
    current: dt.datetime,
    source_url: str,
    source_name: str,
) -> NewsItem:
    text = _visible_text(raw_html)

    month_match = re.search(
        r"(November|December|January|February|March|April|May|June|July|August|September|October)\s+(?:Arab\s+Light|crude|oil)",
        text,
        flags=re.I,
    )
    if not month_match:
        month_match = re.search(
            r"(November|December|January|February|March|April|May|June|July|August|September|October)\s+(?:delivery|loadings?)",
            text,
            flags=re.I,
        )
    delivery_month = month_match.group(1).title() if month_match else "November"

    # Prefer the Reuters-style prose because it contains both current and monthly changes.
    light = re.search(
        r"Arab\s+Light.*?(?:OSP|official\s+selling\s+price).*?Asia.*?"
        r"(?:at\s+)?\$?([0-9.]+)\s+a\s+barrel\s+below.*?"
        r"(?:down|cut)\s+\$?([0-9.]+)\s+from\s+the\s+previous\s+month",
        text,
        flags=re.I | re.S,
    )
    if not light:
        light = re.search(
            r"Arab\s+Light.*?(?:Asia|East\s+Asia).*?\$?([0-9.]+)\s+(?:a\s+barrel\s+)?below",
            text,
            flags=re.I | re.S,
        )

    # Exact current differentials also appear in the OSP tables.
    table_values = re.search(
        r"(?:NOVEMBER|November).*?(?:SUPER\s+LIGHT|Super\s+Light).*?(-?[0-9.]+).*?"
        r"(?:EXTRA\s+LIGHT|Extra\s+Light).*?(-?[0-9.]+).*?"
        r"(?:LIGHT|Light).*?(-?[0-9.]+).*?"
        r"(?:MEDIUM|Average|Medium).*?(-?[0-9.]+).*?"
        r"(?:HEAVY|Heavy).*?(-?[0-9.]+)",
        text,
        flags=re.I | re.S,
    )

    if table_values:
        super_light = float(table_values.group(1))
        extra_light = float(table_values.group(2))
        asia_light = float(table_values.group(3))
        asia_medium = float(table_values.group(4))
        asia_heavy = float(table_values.group(5))
    else:
        super_light = -3.35 if "-3.35" in text else None
        extra_light = -4.50 if "-4.50" in text else None
        asia_light = -5.00 if ("$5" in text and ("below" in text.lower() or "-5.00" in text)) else None
        asia_medium = -6.00 if "-6.00" in text else None
        asia_heavy = -7.35 if "-7.35" in text else None

    if light and len(light.groups()) >= 2:
        asia_light = -abs(float(light.group(1)))
        light_delta = -abs(float(light.group(2)))
    else:
        light_delta = -3.0 if ("down $3" in text.lower() or "drop from the previous month" in text.lower() or "down us$3" in text.lower()) else None

    heavy_cut = re.search(
        r"(?:Arab\s+Medium\s+and\s+Arab\s+Heavy|heavier\s+grades).*?(?:cut|cuts|reduced).*?\$?([0-9.]+)\s+a\s+barrel",
        text,
        flags=re.I | re.S,
    )
    heavy_delta = -abs(float(heavy_cut.group(1))) if heavy_cut else (-5.0 if "change" in text.lower() and "-5.00" in text else None)

    eu_raise = re.search(
        r"(?:raised|raise).*?(?:northwest|north-west)\s+Europe.*?\$?([0-9.]+)\s+a\s+barrel"
        r"|(?:northwest|north-west)\s+Europe.*?(?:raised|raise).*?\$?([0-9.]+)\s+a\s+barrel",
        text,
        flags=re.I | re.S,
    )
    europe_delta = None
    if eu_raise:
        raw_europe_delta = eu_raise.group(1) or eu_raise.group(2)
        europe_delta = abs(float(raw_europe_delta)) if raw_europe_delta is not None else None
    elif "northwest europe" in text.lower() and "0.85" in text:
        europe_delta = 3.0
    us_unchanged = "unchanged" in text.lower() and ("united states" in text.lower() or "u.s." in text.lower() or "north america" in text.lower())

    if asia_light is None:
        raise RuntimeError("Saudi Asia Arab Light OSP not found")

    widest = "june 2020" in text.lower()
    title = (
        f"Saudi OSP {delivery_month} Asia: Super Light {super_light if super_light is not None else 0:.2f}; "
        f"Extra Light {extra_light if extra_light is not None else 0:.2f}; "
        f"Arab Light {asia_light:.2f}"
        + (f" MoM {light_delta:.2f}" if light_delta is not None else "")
        + f"; Arab Medium {asia_medium if asia_medium is not None else 0:.2f}"
        + (f" MoM {heavy_delta:.2f}" if heavy_delta is not None else "")
        + f"; Arab Heavy {asia_heavy if asia_heavy is not None else 0:.2f}"
        + (f" MoM {heavy_delta:.2f}" if heavy_delta is not None else "")
        + (f"; NW Europe MoM +{europe_delta:.2f}" if europe_delta is not None else "")
        + ("; US unchanged" if us_unchanged else "")
        + ("; widest Asia Light discount since June 2020" if widest else "")
    )

    return NewsItem(
        title=title,
        source=source_name,
        link=source_url,
        published_utc=current.isoformat().replace("+00:00", "Z"),
        published_epoch=current.timestamp(),
        event_kind="saudi_asia_osp_change",
    )


def fetch_saudi_osp_snapshots(current: dt.datetime) -> list[NewsItem]:
    items: list[NewsItem] = []
    errors: list[str] = []
    source_names = ("Reuters via BOE Report", "Saudi Aramco via Argaam")
    for url, source_name in zip(SAUDI_NOVEMBER_OSP_URLS, source_names):
        try:
            raw = fetch_bytes(url, timeout=25, attempts=2).decode("utf-8", errors="replace")
            items.append(parse_saudi_osp_snapshot(raw, current, url, source_name))
        except Exception as exc:
            errors.append(f"{source_name}: {type(exc).__name__}: {exc}")
    if not items:
        raise RuntimeError(" | ".join(errors))
    return items


def _extract_saudi_osp_metrics(news_rows: list[NewsItem]) -> dict[str, float | str | None]:
    text = " ".join(str(row.title or "") for row in news_rows)

    def val(pattern: str) -> float | None:
        m = re.search(pattern, text, flags=re.I)
        return float(m.group(1)) if m else None

    month_match = re.search(r"Saudi\s+OSP\s+([A-Za-z]+)\s+Asia", text, flags=re.I)
    delivery_month = month_match.group(1).title() if month_match else None
    return {
        "delivery_month": delivery_month,
        "asia_super_light": val(r"Super\s+Light\s+(-?[0-9.]+)"),
        "asia_extra_light": val(r"Extra\s+Light\s+(-?[0-9.]+)"),
        "asia_light": val(r"Arab\s+Light\s+(-?[0-9.]+)"),
        "asia_light_delta": val(r"Arab\s+Light\s+-?[0-9.]+\s+MoM\s+(-?[0-9.]+)"),
        "asia_medium": val(r"Arab\s+Medium\s+(-?[0-9.]+)"),
        "asia_medium_delta": val(r"Arab\s+Medium\s+-?[0-9.]+\s+MoM\s+(-?[0-9.]+)"),
        "asia_heavy": val(r"Arab\s+Heavy\s+(-?[0-9.]+)"),
        "asia_heavy_delta": val(r"Arab\s+Heavy\s+-?[0-9.]+\s+MoM\s+(-?[0-9.]+)"),
        "europe_delta": val(r"NW\s+Europe\s+MoM\s+\+?([0-9.]+)"),
        "us_unchanged": 1.0 if "US unchanged" in text else 0.0,
        "widest_since_2020": 1.0 if "widest Asia Light discount since June 2020" in text else 0.0,
    }


def parse_kpler_prewar_export_snapshot(raw_html: str, current: dt.datetime) -> NewsItem:
    text = _visible_text(raw_html)

    current_match = re.search(
        r"At\s+least\s+([0-9.]+)\s*mbd\s+left\s+the\s+region\s+between\s+1\s+and\s+28\s+September",
        text,
        flags=re.I,
    )
    prewar_match = re.search(
        r"matching\s+the\s+pre-war\s+average\s+excluding\s+Iran",
        text,
        flags=re.I,
    )
    bypass_match = re.search(
        r"([0-9.]+)%\s+of\s+the\s+region['’]s\s+crude\s+now\s+leaves\s+without\s+crossing\s+Hormuz",
        text,
        flags=re.I,
    )
    prewar_bypass_match = re.search(
        r"against\s+([0-9.]+)%\s+before\s+the\s+war",
        text,
        flags=re.I,
    )
    hormuz_match = re.search(
        r"([0-9.]+)%\s+physically\s+crossed\s+Hormuz,\s*([0-9.]+)\s*mbd",
        text,
        flags=re.I,
    )
    sts_match = re.search(
        r"more\s+than\s+([0-9.]+)%\s+of\s+the\s+crude\s+crossing\s+the\s+strait\s+changed\s+tankers",
        text,
        flags=re.I,
    )

    if not (current_match and prewar_match and bypass_match and prewar_bypass_match and hormuz_match):
        raise RuntimeError("Kpler pre-war export snapshot metrics not found")

    current_mbd = float(current_match.group(1))
    bypass_pct = float(bypass_match.group(1))
    prewar_bypass_pct = float(prewar_bypass_match.group(1))
    hormuz_pct = float(hormuz_match.group(1))
    hormuz_mbd = float(hormuz_match.group(2))
    sts_pct = float(sts_match.group(1)) if sts_match else None

    title = (
        f"Kpler Gulf crude excluding Iran {current_mbd:.1f} Mbd, 100% pre-war average; "
        f"Hormuz {hormuz_mbd:.1f} Mbd {hormuz_pct:.0f}%; "
        f"bypass {bypass_pct:.0f}% vs pre-war {prewar_bypass_pct:.0f}%"
        + (f"; STS over {sts_pct:.0f}%" if sts_pct is not None else "")
    )
    return NewsItem(
        title=title,
        source="Kpler",
        link=KPLER_PREWAR_EXPORT_URL,
        published_utc=current.isoformat().replace("+00:00", "Z"),
        published_epoch=current.timestamp(),
        event_kind="ex_iran_crude_prewar_recovery",
    )


def _extract_ex_iran_prewar_metrics(news_rows: list[NewsItem]) -> dict[str, float | None]:
    text = " ".join(normalize_text(row.title) for row in news_rows)

    def grab(pattern: str) -> float | None:
        m = re.search(pattern, text, flags=re.I)
        return float(m.group(1)) if m else None

    current_mbd = grab(r"excluding\s+iran\s+([0-9]+(?:\.[0-9]+)?)\s+mbd")
    recovery_pct = grab(r"([0-9]+(?:\.[0-9]+)?)%\s+pre-war")
    hormuz_mbd = grab(r"hormuz\s+([0-9]+(?:\.[0-9]+)?)\s+mbd")
    hormuz_pct = grab(r"hormuz\s+[0-9]+(?:\.[0-9]+)?\s+mbd\s+([0-9]+(?:\.[0-9]+)?)%")
    bypass_pct = grab(r"bypass\s+([0-9]+(?:\.[0-9]+)?)%")
    prewar_bypass_pct = grab(r"pre-war\s+([0-9]+(?:\.[0-9]+)?)%")
    sts_pct = grab(r"sts\s+over\s+([0-9]+(?:\.[0-9]+)?)%")

    return {
        "current_mbd": current_mbd,
        "recovery_pct": recovery_pct,
        "hormuz_mbd": hormuz_mbd,
        "hormuz_pct": hormuz_pct,
        "bypass_pct": bypass_pct,
        "prewar_bypass_pct": prewar_bypass_pct,
        "sts_pct": sts_pct,
    }


def _eia_weekly_table_values(
    text: str,
    start_label: str,
    end_label: str,
    expected_count: int,
) -> list[float]:
    a = text.find(start_label)
    if a < 0:
        raise RuntimeError(f"EIA 주간표에서 품목 행을 찾지 못함: {start_label}")
    b = text.find(end_label, a + len(start_label))
    if b < 0:
        raise RuntimeError(f"EIA 주간표에서 행 경계를 찾지 못함: {end_label}")
    segment = text[a + len(start_label):b]
    raw = re.findall(r"(?<![0-9])([0-9]{1,4}\.[0-9]{2,3})(?![0-9])", segment)
    if len(raw) != expected_count:
        raise RuntimeError(f"EIA 주간표 기간·값 개수 불일치: {start_label} {len(raw)} vs {expected_count}")
    vals = [float(v) for v in raw]
    if not all(math.isfinite(v) for v in vals):
        raise RuntimeError(f"EIA 주간표에 비정상 숫자 존재: {start_label}")
    return vals


def _eia_refining_spread(wti_barrel: float, gas_gallon: float, diesel_gallon: float) -> float:
    if not (15 <= wti_barrel <= 350 and 0.25 <= gas_gallon <= 20 and 0.25 <= diesel_gallon <= 20):
        raise ValueError("EIA 가격 범위가 비정상: 원유/휘발유/경유 단위 확인 필요")
    # (2 gasoline barrels + 1 diesel barrel - 3 crude barrels) / 3 crude barrels;
    # gasoline and diesel are $/gallon and WTI is $/barrel (42 gallons per barrel).
    return ((2 * gas_gallon + diesel_gallon) * 42.0 / 3.0) - wti_barrel


def parse_eia_weekly_refining_snapshot(raw_html: str, current: dt.datetime) -> NewsItem:
    """Official EIA weekly NYH conventional gasoline, NYH ULSD, WTI spot proxy.

    Not the same as Bloomberg's futures-based WTI 3-2-1, and not realized profit.
    All inputs must come from the same EIA date columns.
    """
    visible = _visible_text(raw_html)
    if not all(marker in visible for marker in (
        "Spot Prices", "WTI - Cushing, Oklahoma",
        "Conventional Gasoline", "Ultra-Low-Sulfur No. 2 Diesel Fuel",
    )):
        raise RuntimeError("EIA 공식 현물표 헤더·품목 확인 실패")

    dates_part = visible.split("WTI - Cushing, Oklahoma", 1)[0]
    stamp_strings = re.findall(r"(?<!\d)(\d{2}/\d{2}/\d{2})(?!\d)", dates_part)
    if len(stamp_strings) < 2 or len(stamp_strings) > 10:
        raise RuntimeError("EIA 주간표 기준일 2개 이상 확인 불가")
    dates = [dt.datetime.strptime(d, "%m/%d/%y").replace(tzinfo=UTC) for d in stamp_strings]
    if any(dates[i] >= dates[i + 1] for i in range(len(dates) - 1)):
        raise RuntimeError("EIA 주간표 기준일 중복·역순")
    now_date = current.astimezone(UTC).date()
    last_date = dates[-1].date()
    if last_date > now_date + dt.timedelta(days=1):
        raise RuntimeError("EIA 주간표 기준일이 미래")
    age_days = (now_date - last_date).days
    if age_days > 14:
        raise RuntimeError(f"EIA 주간 현물값 {age_days}일 경과 · 오래된 수치 발송 금지")

    n = len(dates)
    wti = _eia_weekly_table_values(visible, "WTI - Cushing, Oklahoma", "Brent - Europe", n)
    conventional = visible.split("Conventional Gasoline", 1)[1].split("RBOB Regular Gasoline", 1)[0]
    gas = _eia_weekly_table_values(conventional, "New York Harbor, Regular", "U.S. Gulf Coast, Regular", n)
    distillate = visible.split("Ultra-Low-Sulfur No. 2 Diesel Fuel", 1)[1].split("Kerosene-Type Jet Fuel", 1)[0]
    diesel = _eia_weekly_table_values(distillate, "New York Harbor", "U.S. Gulf Coast", n)

    last_spread = _eia_refining_spread(wti[-1], gas[-1], diesel[-1])
    prev_spread = _eia_refining_spread(wti[-2], gas[-2], diesel[-2])
    move = last_spread - prev_spread
    if max(last_spread, prev_spread) < EIA_REFINING_MIN_LEVEL_USD:
        raise RuntimeError("EIA 정제마진 고마진 구간이 아니어서 알림 제외")
    if abs(move) < EIA_REFINING_MIN_ABS_WEEKLY_MOVE_USD:
        raise RuntimeError(f"EIA 정제마진 주간 변동 {move:+.2f}달러 · 의미 있는 변화 기준 미충족")
    if not (math.isfinite(last_spread) and math.isfinite(prev_spread) and math.isfinite(move)):
        raise RuntimeError("EIA 정제마진 계산 결과 비정상")

    title = (
        f"EIA weekly refining proxy {last_date.isoformat()}; "
        f"latest {last_spread:.2f} USD/bbl; previous {prev_spread:.2f} USD/bbl; "
        f"delta {move:+.2f} USD/bbl; WTI {wti[-1]:.2f} USD/bbl; "
        f"NYH regular gasoline {gas[-1]:.3f} USD/gal; "
        f"NYH ULSD {diesel[-1]:.3f} USD/gal"
    )
    return NewsItem(
        title=title,
        source=EIA_REFINING_SOURCE,
        link=EIA_REFINING_WEEKLY_URL,
        published_utc=current.isoformat().replace("+00:00", "Z"),
        published_epoch=current.timestamp(),
        event_kind="eia_refining_crack_watch",
    )


def _extract_eia_refining_metrics(rows: list[NewsItem]) -> dict[str, float | str] | None:
    for row in rows:
        if row.event_kind != "eia_refining_crack_watch" or row.source != EIA_REFINING_SOURCE or row.link != EIA_REFINING_WEEKLY_URL:
            continue
        pattern = (
            r"EIA weekly refining proxy (\d{4}-\d{2}-\d{2}); "
            r"latest ([+-]?\d+\.\d{2}) USD/bbl; previous ([+-]?\d+\.\d{2}) USD/bbl; "
            r"delta ([+-]\d+\.\d{2}) USD/bbl; WTI (\d+\.\d{2}) USD/bbl; "
            r"NYH regular gasoline (\d+\.\d{3}) USD/gal; NYH ULSD (\d+\.\d{3}) USD/gal"
        )
        m = re.fullmatch(pattern, row.title)
        if not m:
            continue
        latest, previous, delta = float(m.group(2)), float(m.group(3)), float(m.group(4))
        if not all(math.isfinite(v) for v in (latest, previous, delta)):
            continue
        if abs((latest - previous) - delta) > 0.025:
            continue
        return {
            "week": m.group(1),
            "latest": latest, "previous": previous, "move": delta,
            "wti": float(m.group(5)), "gas": float(m.group(6)), "diesel": float(m.group(7)),
        }
    return None


def _build_eia_refining_alert_body(
    news_rows: list[NewsItem], oil: Quote | None, current: dt.datetime, fx: Quote | None
) -> str:
    m = _extract_eia_refining_metrics(news_rows)
    if m is None:
        raise RuntimeError("EIA 공식 지표 숫자 불일치 · Telegram 전송 차단")
    latest, previous, move = float(m["latest"]), float(m["previous"]), float(m["move"])
    direction = "확대" if move > 0 else "축소"
    lines = [
        current.astimezone(KST).strftime("%Y년 %m월 %d일 %H:%M KST"),
        "",
        "[현재 숫자]",
        f"주간 기준      {m['week']} · EIA 현물 3-2-1 유사 지표",
        f"정제마진      {latest:.2f}달러/배럴 · 전주 {previous:.2f}달러 · {move:+.2f}달러 {direction}",
        f"입력 가격     WTI {float(m['wti']):.2f}달러/배럴 · 휘발유 {float(m['gas']):.3f}달러/갤런 · 경유 {float(m['diesel']):.3f}달러/갤런",
    ]
    if fx is not None:
        lines.append(f"원화 환산     약 {latest * fx.price:,.0f}원/배럴 · 원·달러 {fx.price:,.2f}원")
    lines.extend([
        "",
        "[핵심]",
        "원유 가격과 정제품 가격의 차이를 분리해 추적합니다. 정제마진은 곧바로 영업이익이 아닙니다.",
        (
            "→ 가격차 확대는 정유사의 잠재적인 가공수익에 우호적이지만 운임·에너지·가동률·재고평가를 확인해야 합니다."
            if move > 0 else
            "→ 아직 고마진이더라도 주간 차이 축소는 정유사의 추가 이익 증가세가 둔화될 조기 경보입니다."
        ),
        "",
        "[한국 전이]",
        "정유          S-OIL·SK에너지·GS칼텍스·HD현대오일뱅크: 아시아 실제 정제마진·원가 확인",
        "역방향        항공·운송: 항공유·경유 가격 상승 시 비용 부담",
        "",
        "[다음 체크]",
        "미국          EIA 다음 주 현물가격·정유 가동률·휘발유/중간유분 재고",
        "해외          싱가포르 경유·항공유 정제마진 · 중국 수출 재개 · 중동 정제시설 복구",
        "정책          G7 비축유 실제 방출량 · 미국 디젤 수출 제한 여부",
        "",
        "[근거]",
        f"{EIA_REFINING_SOURCE} · 기준 {m['week']} · 공식 현물가격 주간표",
        f"원문: {EIA_REFINING_WEEKLY_URL}",
        "",
        "[주의]",
        "공식 WTI·뉴욕항 일반휘발유·초저유황경유의 동일 주간 현물가격으로 재계산한 유사 3-2-1입니다.",
        "Bloomberg 선물 3-2-1·Shell 회사별 정제마진과 다른 지표이며, 영업비·수율·재고손익을 차감하지 않았습니다.",
        "6주 내역만으로 '52주 신고가'나 '사상 최고'를 단정하지 않습니다.",
    ])
    return "\n".join(lines).strip() + "\n"


def parse_kpler_sts_snapshot(raw_html: str, current: dt.datetime) -> NewsItem:
    text = _visible_text(raw_html)
    record = re.search(
        r"September\s+(\d{1,2})\s+to\s+date\s+currently\s+tracking\s+at\s+a\s+record\s+([0-9.]+)\s*Mbd",
        text,
        flags=re.I,
    )
    since_war = re.search(
        r"average\s+of\s+([0-9.]+)\s*Mbd\s+since\s+the\s+US-Iran\s+war",
        text,
        flags=re.I,
    )
    baseline = re.search(
        r"from\s+just\s+([0-9.]+)\s*Mbd\s+in\s+2025",
        text,
        flags=re.I,
    )
    vlcc = re.search(
        r"3\s*Mbd\s+of\s+Saudi\s+crude.*?between\s+(\d+)\s+and\s+(\d+)\s+additional\s+VLCCs",
        text,
        flags=re.I,
    )
    if not record or not since_war or not baseline:
        raise RuntimeError("Kpler STS snapshot metrics not found")
    day = int(record.group(1))
    record_mbd = float(record.group(2))
    since_war_mbd = float(since_war.group(1))
    baseline_mbd = float(baseline.group(1))
    year = current.astimezone(KST).year
    source_date = dt.date(year, 9, day)
    if source_date > current.astimezone(KST).date() + dt.timedelta(days=1):
        raise RuntimeError(f"Kpler STS source date in future: {source_date}")
    vlcc_text = f"; Saudi 3 Mbd requires {vlcc.group(1)}-{vlcc.group(2)} additional VLCCs" if vlcc else ""
    title = (
        f"Kpler Gulf of Oman STS record {record_mbd:.1f} Mbd as of {source_date.isoformat()}; "
        f"since-war average {since_war_mbd:.1f} Mbd; 2025 average {baseline_mbd:.2f} Mbd"
        f"{vlcc_text}"
    )
    return NewsItem(
        title=title,
        source="Kpler",
        link=KPLER_STS_URL,
        published_utc=current.isoformat().replace("+00:00", "Z"),
        published_epoch=current.timestamp(),
        event_kind="sts_reroute_expansion",
    )


def parse_mideast_export_snapshot(raw_html: str, current: dt.datetime, source_url: str) -> NewsItem:
    text = _visible_text(raw_html)

    current_patterns = (
        r"rebounded\s+in\s+September\s+to\s+([0-9.]+)\s+million\s+barrels\s+per\s+day",
        r"rebounded\s+in\s+September\s+to\s+([0-9.]+)\s+million\s+bpd",
        r"Middle\s+East\s+crude\s+exports.*?([0-9.]+)\s+million\s+(?:barrels\s+per\s+day|bpd)",
    )
    hormuz_patterns = (
        r"Strait\s+of\s+Hormuz.*?(?:about|approximately)?\s*([0-9.]+)\s+million\s+bpd",
        r"exports\s+via\s+the\s+Strait\s+of\s+Hormuz.*?([0-9.]+)\s+million\s+bpd",
    )
    feb_patterns = (
        r"from\s+([0-9.]+)\s+million\s+bpd\s+in\s+February",
        r"below\s+the\s+([0-9.]+)\s+million\s+bpd.*?February",
        r"([0-9.]+)\s+million\s+bpd\s+in\s+February",
    )
    saudi_patterns = (
        r"Saudi\s+Arabia.*?ship\s+about\s+([0-9.]+)\s+million\s+bpd",
        r"Saudi\s+Arabia.*?exports.*?([0-9.]+)\s+million\s+bpd",
    )
    ras_patterns = (
        r"Ras\s+Tanura.*?about\s+([0-9.]+)\s+million\s+bpd",
        r"Ras\s+Tanura.*?([0-9.]+)\s+million\s+bpd",
    )

    def first_number(patterns: tuple[str, ...]) -> float | None:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.I | re.S)
            if match:
                return float(match.group(1))
        return None

    current_mbd = first_number(current_patterns)
    hormuz_mbd = first_number(hormuz_patterns)
    feb_mbd = first_number(feb_patterns)
    saudi_mbd = first_number(saudi_patterns)
    ras_mbd = first_number(ras_patterns)

    if current_mbd is None or hormuz_mbd is None or feb_mbd is None:
        raise RuntimeError(
            f"regional export snapshot metrics missing current={current_mbd} "
            f"hormuz={hormuz_mbd} feb={feb_mbd}"
        )
    if not (5.0 <= current_mbd <= 25.0 and 2.0 <= hormuz_mbd <= 20.0 and 10.0 <= feb_mbd <= 30.0):
        raise RuntimeError(
            f"regional export snapshot out of range current={current_mbd} "
            f"hormuz={hormuz_mbd} feb={feb_mbd}"
        )
    if current_mbd > feb_mbd * 1.25:
        raise RuntimeError(
            f"regional export snapshot implausible current={current_mbd} feb={feb_mbd}"
        )

    gap_mbd = feb_mbd - current_mbd
    recovery_pct = current_mbd / feb_mbd * 100.0 if feb_mbd else 0.0
    extras = []
    if saudi_mbd is not None:
        extras.append(f"Saudi {saudi_mbd:.3f} Mbd")
    if ras_mbd is not None:
        extras.append(f"RasTanura {ras_mbd:.3f} Mbd")
    extra_text = "; " + "; ".join(extras) if extras else ""

    title = (
        f"Middle East crude exports snapshot {current_mbd:.3f} Mbd; "
        f"Hormuz {hormuz_mbd:.3f} Mbd; February {feb_mbd:.3f} Mbd; "
        f"gap {gap_mbd:.3f} Mbd; recovery {recovery_pct:.1f}%"
        f"{extra_text}; preliminary Kpler data may revise"
    )
    return NewsItem(
        title=title,
        source="Reuters/Kpler",
        link=source_url,
        published_utc=current.isoformat().replace("+00:00", "Z"),
        published_epoch=current.timestamp(),
        event_kind="regional_export_recovery",
    )


def fetch_mideast_export_snapshot(current: dt.datetime) -> NewsItem:
    errors: list[str] = []
    for url in MIDEAST_EXPORT_SNAPSHOT_URLS:
        try:
            raw = fetch_bytes(url, timeout=25, attempts=2).decode("utf-8", errors="replace")
            return parse_mideast_export_snapshot(raw, current, url)
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {exc}")
    raise RuntimeError(" | ".join(errors))


def fetch_news(current: dt.datetime) -> tuple[list[NewsItem], list[str]]:
    max_age_hours = int(os.getenv("IRAN_HORMUZ_MAX_NEWS_AGE_HOURS", "72"))
    items: list[NewsItem] = []
    errors: list[str] = []
    for query in NEWS_QUERIES:
        try:
            items.extend(parse_rss(fetch_bytes(google_news_url(query)), current, max_age_hours))
        except Exception as exc:
            errors.append(str(exc))

    try:
        eia_html = fetch_bytes(EIA_REFINING_WEEKLY_URL, timeout=22, attempts=2).decode("utf-8", errors="replace")
        items.append(parse_eia_weekly_refining_snapshot(eia_html, current))
    except Exception as exc:
        errors.append(f"EIA refinery 3-2-1 official: {type(exc).__name__}: {exc}")

    direct_sources=(
        ("중국 Reuters 거래 관계자 보도", lambda: parse_china_reuters_resumption(
            fetch_bytes(CHINA_REUTERS_20261009_URL,timeout=16,attempts=2).decode("utf-8","replace"),current)),
        ("호르무즈 신화통신·타스님 인용 보도", lambda: parse_hormuz_xinhua_review(
            fetch_bytes(HORMUZ_7DAY_XINHUA_URL,timeout=16,attempts=2).decode("utf-8","replace"),current)),
        ("허리케인 공식 MMA 중단율", lambda: fetch_mma_isaias_snapshot(current)),
    )
    for desc, loader in direct_sources:
        try:
            items.append(loader())
        except Exception as exc:
            errors.append(f"{desc}: {type(exc).__name__}: {exc}")

    try:
        items.extend(fetch_saudi_osp_snapshots(current))
    except Exception as exc:
        errors.append(f"Saudi OSP direct: {type(exc).__name__}: {exc}")

    try:
        eu_html = fetch_bytes(EU_DIESEL_RESERVE_URL).decode("utf-8", errors="replace")
        items.append(parse_eu_diesel_reserve_snapshot(eu_html, current))
    except Exception as exc:
        errors.append(f"Euronews EU diesel reserve direct: {type(exc).__name__}: {exc}")

    try:
        kpler_prewar_html = fetch_bytes(KPLER_PREWAR_EXPORT_URL).decode("utf-8", errors="replace")
        items.append(parse_kpler_prewar_export_snapshot(kpler_prewar_html, current))
    except Exception as exc:
        errors.append(f"Kpler pre-war export direct: {type(exc).__name__}: {exc}")

    try:
        kpler_html = fetch_bytes(KPLER_STS_URL).decode("utf-8", errors="replace")
        items.append(parse_kpler_sts_snapshot(kpler_html, current))
    except Exception as exc:
        errors.append(f"Kpler STS direct: {type(exc).__name__}: {exc}")

    try:
        items.append(fetch_mideast_export_snapshot(current))
    except Exception as exc:
        errors.append(f"Reuters/Kpler regional direct: {type(exc).__name__}: {exc}")

    try:
        items.append(fetch_jpmorgan_product_gap_snapshot(current))
    except Exception as exc:
        errors.append(f"JPMorgan crude/product direct: {type(exc).__name__}: {exc}")

    unique: dict[tuple[str, str, str], NewsItem] = {}
    for item in items:
        key = (normalize_text(item.source), normalize_text(item.title), item.event_kind)
        unique[key] = item
    return sorted(unique.values(), key=lambda item: item.published_epoch, reverse=True), errors


def confirm_events(items: list[NewsItem], minimum_sources: int = 2) -> list[tuple[str, list[NewsItem]]]:
    by_kind: dict[tuple[str,str], list[NewsItem]] = {}
    for item in items:
        if item.event_kind == "china_fuel_export_policy":
            stage=_china_fuel_export_stage(item.title)
        elif item.event_kind == "hormuz_7day_diplomacy":
            stage=_hormuz_7day_stage(item.title)
        else:
            stage="all"
        by_kind.setdefault((item.event_kind,stage),[]).append(item)

    candidates: list[tuple[float, str, list[NewsItem]]] = []
    for (kind,stage), rows in by_kind.items():
        source_rows: dict[str, NewsItem] = {}
        for row in sorted(rows, key=lambda item: item.published_epoch, reverse=True):
            publisher=normalize_text(row.source)
            if kind in ("china_fuel_export_policy","hormuz_7day_diplomacy"):
                if ("reuters" in publisher or "reuters" in normalize_text(row.title)
                    or "marketscreener" in publisher or "euronext" in publisher):
                    publisher="reuters"
                elif "anadolu" in publisher or "aa.com.tr" in row.link:
                    publisher="anadolu"
                elif "xinhua" in publisher:
                    publisher="xinhua"
            source_rows.setdefault(publisher, row)
        selected = list(source_rows.values())

        has_primary_data = kind in ("oil_flow_recovery", "sts_reroute_expansion") and any(
            any(alias in normalize_text(row.source) for alias in DATA_PROVIDER_ALIASES)
            for row in selected
        )
        regional_primary = kind in (
            "regional_export_recovery",
            "india_gulf_import_recovery",
            "ex_iran_crude_prewar_recovery",
        ) and any(
            "kpler" in normalize_text(row.source)
            for row in selected
        )
        broker_snapshot = kind == "crude_product_divergence" and any(
            "jpmorgan via bloomberg" in normalize_text(row.source)
            for row in selected
        )
        eu_primary_interview = kind == "eu_diesel_reserve_policy" and any(
            "euronews" in normalize_text(row.source)
            for row in selected
        )
        pipeline_cross_checked = kind == "east_west_pipeline_recovery" and len(selected) >= minimum_sources
        osp_cross_checked = kind == "saudi_asia_osp_change" and len(selected) >= minimum_sources
        china_report=kind=="china_fuel_export_policy" and stage=="planned_resume" and any(
            ("reuters" in normalize_text(row.source) or row.link==CHINA_REUTERS_20261009_URL)
            and "four trade" in normalize_text(row.title) for row in selected
        )
        hormuz_primary=kind=="hormuz_7day_diplomacy" and stage=="reviewing_us_views" and any(
            row.source=="Xinhua" and row.link==HORMUZ_7DAY_XINHUA_URL
            for row in selected
        )
        mma_primary=kind=="us_gulf_isaias_shutin" and _extract_mma_isaias_data(selected) is not None
        eia_primary = kind == "eia_refining_crack_watch" and any(
            row.source == EIA_REFINING_SOURCE
            and row.link == EIA_REFINING_WEEKLY_URL
            and _extract_eia_refining_metrics([row]) is not None
            for row in selected
        )
        pipeline_bloomberg_material = kind == "east_west_pipeline_recovery" and any(
            "bloomberg" in normalize_text(row.source)
            and ("80% capacity" in normalize_text(row.title) or "6 million" in normalize_text(row.title))
            for row in selected
        )

        if len(selected) >= minimum_sources or has_primary_data or regional_primary or broker_snapshot or eu_primary_interview or pipeline_cross_checked or pipeline_bloomberg_material or osp_cross_checked or eia_primary or china_report or hormuz_primary or mma_primary:
            candidates.append((max(row.published_epoch for row in selected), kind, selected))

    candidates.sort(key=lambda value: value[0], reverse=True)
    return [
        (kind, sorted(selected, key=lambda item: item.published_epoch, reverse=True)[:3])
        for _, kind, selected in candidates
    ]


def confirm_event(items: list[NewsItem], minimum_sources: int = 2) -> tuple[str, list[NewsItem]] | None:
    events = confirm_events(items, minimum_sources)
    return events[0] if events else None


def last_finite_point(timestamps: list, closes: list) -> tuple[float, float] | None:
    for timestamp, close in reversed(list(zip(timestamps, closes))):
        ts_value = finite_number(timestamp)
        close_value = finite_number(close)
        if ts_value is not None and close_value is not None:
            return ts_value, close_value
    return None


def parse_yahoo_payload(payload: dict, spec: SymbolSpec) -> Quote:
    chart = payload.get("chart") or {}
    results = chart.get("result") or []
    if not results:
        error = chart.get("error") or {}
        raise RuntimeError(f"{spec.symbol} 데이터 없음: {error.get('description', 'unknown')}")
    result = results[0]
    meta = result.get("meta") or {}
    timestamps = result.get("timestamp") or []
    quote_rows = (result.get("indicators") or {}).get("quote") or []
    closes = quote_rows[0].get("close", []) if quote_rows else []
    last_point = last_finite_point(timestamps, closes)

    price = finite_number(meta.get("regularMarketPrice"))
    if price is None and last_point:
        price = last_point[1]
    previous_close = (
        finite_number(meta.get("regularMarketPreviousClose"))
        or finite_number(meta.get("previousClose"))
    )
    timestamp = finite_number(meta.get("regularMarketTime"))
    if timestamp is None and last_point:
        timestamp = last_point[0]
    if price is None or previous_close is None or previous_close == 0 or timestamp is None:
        raise RuntimeError(f"{spec.symbol} 핵심 값 누락")

    observed = dt.datetime.fromtimestamp(timestamp, tz=UTC)
    change = price - previous_close
    return Quote(
        symbol=spec.symbol,
        label=spec.label,
        unit=spec.unit,
        price=price,
        previous_close=previous_close,
        change=change,
        change_pct=(change / previous_close) * 100,
        timestamp_utc=observed.isoformat().replace("+00:00", "Z"),
        timestamp_epoch=timestamp,
    )


def fetch_quote(spec: SymbolSpec) -> Quote:
    params = urllib.parse.urlencode(
        {
            "interval": os.getenv("IRAN_HORMUZ_YAHOO_INTERVAL", "5m"),
            "range": os.getenv("IRAN_HORMUZ_YAHOO_RANGE", "5d"),
            "includePrePost": "true",
            "events": "div,splits",
        }
    )
    parsed: list[Quote] = []
    errors: list[str] = []
    for base in YAHOO_BASES:
        url = f"{base}/{urllib.parse.quote(spec.symbol, safe='')}?{params}"
        try:
            parsed.append(parse_yahoo_payload(fetch_json(url), spec))
        except Exception as exc:
            errors.append(str(exc))

    if len(parsed) != 2:
        raise RuntimeError(
            f"{spec.symbol} 2개 Yahoo 엔드포인트 교차검증 실패: {' | '.join(errors)}"
        )

    first, second = parsed
    price_gap = abs(first.price - second.price) / max(abs(first.price), abs(second.price), 1e-9)
    prev_gap = abs(first.previous_close - second.previous_close) / max(
        abs(first.previous_close), abs(second.previous_close), 1e-9
    )
    time_gap = abs(first.timestamp_epoch - second.timestamp_epoch)
    if price_gap > 0.002 or prev_gap > 0.002 or time_gap > 300:
        raise RuntimeError(
            f"{spec.symbol} Yahoo 불일치 "
            f"price={price_gap:.3%} prev={prev_gap:.3%} time={time_gap:.0f}s"
        )
    return first


def age_minutes(quote: Quote, current: dt.datetime) -> float:
    return max(0.0, (current.timestamp() - quote.timestamp_epoch) / 60.0)


def quote_is_fresh(quote: Quote, current: dt.datetime, max_age_minutes: int) -> bool:
    return age_minutes(quote, current) <= max_age_minutes


def market_confirms(us2y: Quote, dxy: Quote) -> bool:
    return us2y.price < us2y.previous_close and dxy.price < dxy.previous_close


def load_state(path: pathlib.Path = STATE_PATH) -> dict:
    if not path.exists():
        return {"last_alert_at_kst": None, "last_event_kind": None, "last_event_id": None}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {"last_alert_at_kst": None, "last_event_kind": None, "last_event_id": None}


def event_id(kind: str, rows: list[NewsItem]) -> str:
    combined = " ".join(normalize_text(row.title) for row in rows)

    if kind == "eia_refining_crack_watch":
        metrics = _extract_eia_refining_metrics(rows)
        if not metrics:
            raise ValueError("EIA 정제마진 수치가 없어 중복키를 만들 수 없습니다")
        obs = str(metrics["week"])
        latest = float(metrics["latest"])
        previous = float(metrics["previous"])
        # Same observation and same material $5/bbl band -> same alert even if a feed is republished.
        bucket = math.floor(latest / 5.0)
        direction = "up" if latest > previous else "down" if latest < previous else "flat"
        basis = f"{kind}|week_{obs}|bucket_{bucket}|{direction}"
        return f"{kind}:{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:16]}"

    if kind == "us_diesel_export_policy":
        stage = _diesel_policy_stage(combined)
        basis = f"{kind}|{stage}"
        return f"{kind}:{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:16]}"

    if kind == "g7_reserve_release_agreement":
        stage = _g7_reserve_stage(combined)
        basis = f"{kind}|{stage}"
        return f"{kind}:{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:16]}"

    if kind == "eu_diesel_reserve_policy":
        stage = _eu_diesel_reserve_stage(combined)
        basis = f"{kind}|{stage}"
        return f"{kind}:{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:16]}"

    if kind == "china_fuel_export_policy":
        stage = _china_fuel_export_stage(rows)
        q = _china_resumption_volume(rows)
        volume = f"{q:.1f}" if stage == "planned_resume" and q is not None else "na"
        basis = f"{kind}|2026-10|{stage}|quantity_{volume}"
        return f"{kind}:{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:16]}"

    if kind == "hormuz_7day_diplomacy":
        stage = _hormuz_7day_stage(rows)
        basis = f"{kind}|2026-10|{stage}"
        return f"{kind}:{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:16]}"

    if kind == "us_gulf_isaias_shutin":
        m = _extract_mma_isaias_data(rows)
        if m is None:
            raise ValueError("MMA 검증 숫자 없이 사건 식별 불가")
        band = int(float(m["oil_pct"]) // 5) * 5
        basis = f"{kind}|{m['date']}|pct_{band}"
        return f"{kind}:{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:16]}"

    if kind == "saudi_asia_osp_change":
        metrics = _extract_saudi_osp_metrics(rows)
        month = str(metrics.get("delivery_month") or "unknown")
        light = float(metrics.get("asia_light") or 0.0)
        light_delta = float(metrics.get("asia_light_delta") or 0.0)
        medium = float(metrics.get("asia_medium") or 0.0)
        heavy = float(metrics.get("asia_heavy") or 0.0)
        basis = (
            f"{kind}|{month}|light_{light:.2f}|delta_{light_delta:.2f}|"
            f"medium_{medium:.2f}|heavy_{heavy:.2f}"
        )
        return f"{kind}:{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:16]}"

    if kind == "ex_iran_crude_prewar_recovery":
        metrics = _extract_ex_iran_prewar_metrics(rows)
        crude = float(metrics.get("current_mbd") or 0.0)
        bypass = float(metrics.get("bypass_pct") or 0.0)
        hormuz = float(metrics.get("hormuz_mbd") or 0.0)
        sts = float(metrics.get("sts_pct") or 0.0)
        crude_band = round(crude * 2.0) / 2.0 if crude else 0.0
        bypass_band = int(bypass // 5 * 5) if bypass else 0
        hormuz_band = round(hormuz * 2.0) / 2.0 if hormuz else 0.0
        sts_band = int(sts // 10 * 10) if sts else 0
        basis = (
            f"{kind}|crude_{crude_band:.1f}|bypass_{bypass_band}|"
            f"hormuz_{hormuz_band:.1f}|sts_{sts_band}"
        )
        return f"{kind}:{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:16]}"

    if kind == "crude_product_divergence":
        metrics = _extract_crude_product_gap_metrics(rows)
        crude_pct = float(metrics.get("crude_pct") or 0.0)
        product_pct = float(metrics.get("product_pct") or 0.0)
        crude_band = int(crude_pct // 5 * 5) if crude_pct else 0
        product_band = int(product_pct // 5 * 5) if product_pct else 0
        basis = f"{kind}|crude_{crude_band}|products_{product_band}"
        return f"{kind}:{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:16]}"

    if kind == "regional_export_recovery":
        values = [
            float(value)
            for value in re.findall(
                r"\b([0-9]+(?:\.[0-9]+)?)\s*(?:million\s+(?:barrels\s+per\s+day|bpd)|mbd)\b",
                combined,
                flags=re.I,
            )
        ]
        max_value = max(values) if values else 0.0
        volume_band = round(max_value * 4.0) / 4.0 if max_value > 0 else 0.0
        prewar = "prewar80" if (
            "80% of prewar" in combined or "80% of pre-war" in combined or "80% 회복" in combined
        ) else "no80"
        basis = f"{kind}|mbd_{volume_band:.2f}|{prewar}"
        return f"{kind}:{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:16]}"

    if kind == "india_gulf_import_recovery":
        values = [
            float(value)
            for value in re.findall(
                r"\b([0-9]+(?:\.[0-9]+)?)\s*(?:mb/d|mbd|million\s+bpd|million\s+barrels\s+per\s+day)\b",
                combined,
                flags=re.I,
            )
        ]
        max_value = max(values) if values else 0.0
        volume_band = int(max_value * 4) / 4.0 if max_value > 0 else 0.0
        basis = f"{kind}|mbd_{volume_band:.2f}"
        return f"{kind}:{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:16]}"

    if kind == "east_west_pipeline_recovery":
        exports_resumed = any(
            phrase in combined
            for phrase in (
                "resumes oil exports", "resume oil exports", "starts exports after repairs",
                "starts exports", "export shipments resume", "shipments have now resumed",
                "overseas shipments have now resumed", "crude loadings resume",
                "loadings resume", "yanbu exports resume", "수출 재개", "선적 재개",
            )
        )
        rates = [
            float(value)
            for value in re.findall(
                r"\b([0-9]+(?:\.[0-9]+)?)\s*(?:million\s+(?:barrels\s+per\s+day|bpd)|mbd)\b",
                combined,
                flags=re.I,
            )
        ]
        pct_values = [
            float(value)
            for value in re.findall(r"\b([0-9]+(?:\.[0-9]+)?)\s*%\s*(?:of\s+)?capacity\b", combined, flags=re.I)
        ]
        rate = max(rates) if rates else 0.0
        pct = max(pct_values) if pct_values else 0.0
        if pct >= 95.0:
            band = "capacity_95"
        elif pct >= 90.0:
            band = "capacity_90"
        elif pct >= 80.0:
            band = "capacity_80"
        elif rate >= 5.5:
            band = "5_5plus"
        elif rate >= 5.0:
            band = "5_0"
        elif rate >= 4.0:
            band = "4plus"
        elif exports_resumed:
            band = "export_resume"
        elif rate >= 3.5:
            band = "3_5"
        elif rate >= 3.0:
            band = "3_0"
        else:
            band = "restart"
        yanbu = "yanbu" if "yanbu" in combined else "no_yanbu"
        basis = f"{kind}|{band}|{yanbu}"
        return f"{kind}:{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:16]}"

    if kind in ("oil_flow_recovery", "sts_reroute_expansion"):
        markers = []
        marker_terms = (
            ("saudi_export_ramp", ("saudi", "aramco", "ras tanura")),
            ("hormuz_flow_high", ("hormuz", "six-month high", "record oil")),
            ("sts_record", ("ship-to-ship", "ship to ship", "sts", "gulf of oman")),
            ("sohar_reroute", ("sohar", "oman")),
            ("yanbu_restart", ("yanbu", "east-west pipeline", "east west pipeline")),
            ("vlcc_bottleneck", ("vlcc", "bottleneck", "capacity")),
        )

        def marker_match(term: str) -> bool:
            if term.isalnum() and len(term) <= 4:
                return re.search(rf"\b{re.escape(term)}\b", combined) is not None
            return term in combined

        for name, terms in marker_terms:
            if any(marker_match(term) for term in terms):
                markers.append(name)

        volumes = [
            float(value)
            for value in re.findall(r"\b([0-9]+(?:\.[0-9]+)?)\s*mbd\b", combined, flags=re.I)
        ]
        if volumes:
            max_volume = max(volumes)
            markers.append(
                f"sts_mbd_{int(max_volume)}" if kind == "sts_reroute_expansion"
                else f"flow_mbd_{int(max_volume)}"
            )
        if not markers:
            markers = [kind]
        basis = f"{kind}|{'|'.join(sorted(set(markers)))}"
        return f"{kind}:{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:16]}"

    day = dt.datetime.fromtimestamp(
        max(row.published_epoch for row in rows), tz=UTC
    ).astimezone(KST).date().isoformat()
    sources = ",".join(sorted(normalize_text(row.source) for row in rows))
    digest = hashlib.sha256(f"{kind}|{day}|{sources}".encode("utf-8")).hexdigest()[:16]
    return f"{kind}:{day}:{digest}"


def _parse_kst_timestamp(raw: object) -> dt.datetime | None:
    if not raw:
        return None
    try:
        value = dt.datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=KST)
    return value.astimezone(KST)


def event_recently_alerted(
    state: dict,
    current_event_id: str,
    current: dt.datetime,
    hours: int = 336,
) -> bool:
    alerted = state.get("alerted_events")
    if isinstance(alerted, dict):
        previous = _parse_kst_timestamp(alerted.get(current_event_id))
        if previous is not None:
            return (current.astimezone(KST) - previous).total_seconds() < hours * 3600

    if state.get("last_event_id") == current_event_id:
        previous = _parse_kst_timestamp(state.get("last_alert_at_kst"))
        if previous is None:
            return True
        return (current.astimezone(KST) - previous).total_seconds() < hours * 3600
    return False


def build_pending_state(
    state: dict,
    current_event_id: str,
    kind: str,
    current: dt.datetime,
    market: dict,
) -> dict:
    alerted = dict(state.get("alerted_events") or {})
    now_kst = current.astimezone(KST)
    cutoff = now_kst - dt.timedelta(days=45)
    cleaned: dict[str, str] = {}
    for key, raw in alerted.items():
        stamp = _parse_kst_timestamp(raw)
        if stamp is not None and stamp >= cutoff:
            cleaned[str(key)] = stamp.isoformat(timespec="seconds")
    cleaned[current_event_id] = now_kst.isoformat(timespec="seconds")
    return {
        "last_alert_at_kst": now_kst.isoformat(timespec="seconds"),
        "last_event_kind": kind,
        "last_event_id": current_event_id,
        "alerted_events": cleaned,
        "last_market": market,
    }


def select_unalerted_event(
    state: dict,
    candidates: list[tuple[str, list[NewsItem]]],
    current: dt.datetime,
) -> tuple[tuple[str, list[NewsItem], str] | None, list[str]]:
    duplicate_labels: list[str] = []
    for candidate_kind, candidate_rows in candidates:
        candidate_id = event_id(candidate_kind, candidate_rows)
        if event_recently_alerted(state, candidate_id, current):
            duplicate_labels.append(EVENT_LABELS.get(candidate_kind, candidate_kind))
            continue
        return (candidate_kind, candidate_rows, candidate_id), duplicate_labels
    return None, duplicate_labels


def clean_outputs() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in (
        TITLE_PATH,
        BODY_PATH,
        ALERT_JSON_PATH,
        PENDING_STATE_PATH,
        TELEGRAM_CONFIRMED_PATH,
    ):
        path.unlink(missing_ok=True)


def fmt_signed(value: float, digits: int = 2, suffix: str = "") -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.{digits}f}{suffix}"


def fmt_quote_line(quote: Quote) -> str:
    if quote.symbol == "^UST2Y":
        bp = quote.change * 100
        direction = "하락" if quote.change < 0 else "상승" if quote.change > 0 else "보합"
        return (
            f"- {quote.label}: {quote.price:.3f}% (전 거래일 {quote.previous_close:.3f}%, "
            f"{fmt_signed(bp, 1, 'bp')}, {direction})"
        )
    if quote.symbol == "DX-Y.NYB":
        direction = "하락" if quote.change < 0 else "상승" if quote.change > 0 else "보합"
        return (
            f"- {quote.label}: {quote.price:.2f} (전 거래일 {quote.previous_close:.2f}, "
            f"{fmt_signed(quote.change_pct, 2, '%')}, {direction})"
        )
    if quote.symbol == "KRW=X":
        won = "원화 약세" if quote.change > 0 else "원화 강세" if quote.change < 0 else "보합"
        return (
            f"- {quote.label}: {quote.price:,.2f}원 "
            f"(전 거래일 {quote.previous_close:,.2f}원, "
            f"{fmt_signed(quote.change_pct, 2, '%')}, {won})"
        )
    direction = "하락" if quote.change < 0 else "상승" if quote.change > 0 else "보합"
    return (
        f"- {quote.label}: ${quote.price:.2f}/배럴 (전 거래일 ${quote.previous_close:.2f}, "
        f"{fmt_signed(quote.change_pct, 2, '%')}, {direction})"
    )


def _extract_kpler_sts_metrics(news_rows: list[NewsItem]) -> dict[str, object] | None:
    for row in news_rows:
        if "kpler" not in normalize_text(row.source):
            continue
        title = str(row.title or "")
        match = re.search(
            r"STS record\s+([0-9.]+)\s+Mbd\s+as of\s+(\d{4}-\d{2}-\d{2});\s*"
            r"since-war average\s+([0-9.]+)\s+Mbd;\s*"
            r"2025 average\s+([0-9.]+)\s+Mbd"
            r"(?:;\s*Saudi\s+([0-9.]+)\s+Mbd\s+requires\s+(\d+)-(\d+)\s+additional VLCCs)?",
            title,
            flags=re.I,
        )
        if not match:
            continue
        current = float(match.group(1))
        since_war = float(match.group(3))
        baseline_2025 = float(match.group(4))
        return {
            "current_mbd": current,
            "source_date": match.group(2),
            "since_war_mbd": since_war,
            "baseline_2025_mbd": baseline_2025,
            "vs_war_avg": current / since_war if since_war else None,
            "vs_2025_avg": current / baseline_2025 if baseline_2025 else None,
            "saudi_increment_mbd": float(match.group(5)) if match.group(5) else None,
            "vlcc_low": int(match.group(6)) if match.group(6) else None,
            "vlcc_high": int(match.group(7)) if match.group(7) else None,
            "link": row.link,
        }
    return None


def _extract_pipeline_rate(news_rows: list[NewsItem]) -> tuple[float | None, bool]:
    rates: list[float] = []
    yanbu = False
    for row in news_rows:
        title = str(row.title or "")
        low = normalize_text(title)
        if "yanbu" in low:
            yanbu = True
        for value in re.findall(
            r"\b([0-9]+(?:\.[0-9]+)?)\s*(?:million\s+(?:barrels\s+per\s+day|bpd)|mbd)\b",
            low,
            flags=re.I,
        ):
            try:
                rate = float(value)
            except ValueError:
                continue
            if 0.5 <= rate <= 10.0:
                rates.append(rate)
    return (max(rates) if rates else None, yanbu)


def _extract_pipeline_capacity_pct(news_rows: list[NewsItem]) -> float | None:
    text = " ".join(normalize_text(row.title) for row in news_rows)
    values = [
        float(v)
        for v in re.findall(r"\b([0-9]+(?:\.[0-9]+)?)\s*%\s*(?:of\s+)?capacity\b", text, flags=re.I)
    ]
    if not values:
        values = [
            float(v)
            for v in re.findall(r"(?:over|above|more than)\s+([0-9]+(?:\.[0-9]+)?)\s*%\s+capacity", text, flags=re.I)
        ]
    return max(values) if values else None


def _pipeline_exports_resumed(news_rows: list[NewsItem]) -> bool:
    phrases = (
        "resumes oil exports", "resume oil exports", "starts exports after repairs",
        "starts exports", "export shipments resume", "shipments have now resumed",
        "overseas shipments have now resumed", "crude loadings resume",
        "loadings resume", "yanbu exports resume", "수출 재개", "선적 재개",
    )
    text = " ".join(normalize_text(row.title) for row in news_rows)
    return any(phrase in text for phrase in phrases)


def parse_jpmorgan_product_gap_snapshot(
    raw_html: str,
    current: dt.datetime,
    source_url: str,
) -> NewsItem:
    text = _visible_text(raw_html)
    crude = re.search(
        r"(?:shipments\s+of\s+crude\s+oil.*?|crude\s+(?:oil\s+)?(?:flows|shipments).*?)"
        r"([0-9]+(?:\.[0-9]+)?)\s+million\s+barrels\s+(?:a|per)\s+day.*?"
        r"([0-9]+(?:\.[0-9]+)?)\s*%\s+of\s+pre-war",
        text, flags=re.I,
    )
    products = re.search(
        r"(?:flows|shipments)\s+of\s+(?:oil\s+)?products.*?"
        r"([0-9]+(?:\.[0-9]+)?)\s+million\s+barrels\s+(?:a|per)\s+day.*?"
        r"([0-9]+(?:\.[0-9]+)?)\s*%",
        text, flags=re.I,
    )
    if not products:
        products = re.search(
            r"products\s+such\s+as\s+diesel\s+and\s+(?:gasoline|petrol).*?"
            r"([0-9]+(?:\.[0-9]+)?)\s+million\s+barrels\s+(?:a|per)\s+day.*?"
            r"([0-9]+(?:\.[0-9]+)?)\s*%",
            text, flags=re.I,
        )
    overall = re.search(r"overall\s+figure\s+was\s+([0-9]+(?:\.[0-9]+)?)\s*%\s+of\s+2025", text, flags=re.I)
    hormuz = re.search(
        r"(?:Hormuz|Strait\s+of\s+Hormuz).*?(?:nearly|about|almost)?\s*"
        r"([0-9]+(?:\.[0-9]+)?)\s+million\s+barrels\s+(?:a|per)\s+day",
        text, flags=re.I,
    )
    if not crude or not products:
        raise RuntimeError("JPMorgan crude/product gap metrics not found")
    crude_mbd = float(crude.group(1))
    crude_pct = float(crude.group(2))
    product_mbd = float(products.group(1))
    product_pct = float(products.group(2))
    overall_pct = float(overall.group(1)) if overall else None
    hormuz_mbd = float(hormuz.group(1)) if hormuz else None
    extra = []
    if overall_pct is not None:
        extra.append(f"overall {overall_pct:.0f}% of 2025")
    if hormuz_mbd is not None:
        extra.append(f"Hormuz {hormuz_mbd:.1f} Mbd")
    suffix = "; " + "; ".join(extra) if extra else ""
    title = (
        f"JPMorgan Middle East crude/product snapshot crude {crude_mbd:.1f} Mbd "
        f"{crude_pct:.0f}% pre-war; products {product_mbd:.1f} Mbd "
        f"{product_pct:.0f}% pre-war{suffix}"
    )
    return NewsItem(
        title=title,
        source="JPMorgan via Bloomberg",
        link=source_url,
        published_utc=current.isoformat().replace("+00:00", "Z"),
        published_epoch=current.timestamp(),
        event_kind="crude_product_divergence",
    )


def fetch_jpmorgan_product_gap_snapshot(current: dt.datetime) -> NewsItem:
    errors: list[str] = []
    for url in MIDEAST_PRODUCT_GAP_URLS:
        try:
            raw = fetch_bytes(url, timeout=25, attempts=2).decode("utf-8", errors="replace")
            return parse_jpmorgan_product_gap_snapshot(raw, current, url)
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {exc}")
    raise RuntimeError(" | ".join(errors))


def _extract_crude_product_gap_metrics(news_rows: list[NewsItem]) -> dict[str, float | None]:
    text = " ".join(normalize_text(row.title) for row in news_rows)

    crude_pair = re.search(
        r"\bcrude\s+([0-9]+(?:\.[0-9]+)?)\s+mbd\s+([0-9]+(?:\.[0-9]+)?)%\s+pre-war",
        text,
        flags=re.I,
    )
    product_pair = re.search(
        r"\bproducts\s+([0-9]+(?:\.[0-9]+)?)\s+mbd\s+([0-9]+(?:\.[0-9]+)?)%\s+pre-war",
        text,
        flags=re.I,
    )

    def grab(pattern: str) -> float | None:
        match = re.search(pattern, text, flags=re.I)
        return float(match.group(1)) if match else None

    crude_mbd = float(crude_pair.group(1)) if crude_pair else grab(r"\bcrude\s+([0-9]+(?:\.[0-9]+)?)\s+mbd")
    crude_pct = float(crude_pair.group(2)) if crude_pair else grab(r"([0-9]+(?:\.[0-9]+)?)%\s+(?:of\s+)?pre-war")
    product_mbd = float(product_pair.group(1)) if product_pair else grab(r"\bproducts\s+([0-9]+(?:\.[0-9]+)?)\s+mbd")
    product_pct = float(product_pair.group(2)) if product_pair else None
    overall_pct = grab(r"\boverall\s+([0-9]+(?:\.[0-9]+)?)%\s+of\s+2025")
    hormuz_mbd = grab(r"\bhormuz\s+([0-9]+(?:\.[0-9]+)?)\s+mbd")
    return {
        "crude_mbd": crude_mbd, "crude_pct": crude_pct,
        "product_mbd": product_mbd, "product_pct": product_pct,
        "overall_pct": overall_pct, "hormuz_mbd": hormuz_mbd,
        "gap_pp": crude_pct - product_pct if crude_pct is not None and product_pct is not None else None,
    }


def _diesel_policy_stage(text_or_rows: str | list[NewsItem]) -> str:
    text = normalize_text(text_or_rows) if isinstance(text_or_rows, str) else " ".join(normalize_text(row.title) for row in text_or_rows)
    if any(term in text for term in ("takes effect", "effective immediately", "ban effective", "금지 시행", "시행")):
        return "effective"
    if any(term in text for term in ("denies", "denied", "rules out", "not considering", "부인", "검토하지")):
        return "denied"
    if any(term in text for term in ("withdraw", "drops plan", "abandons", "철회", "백지화")):
        return "withdrawn"
    if any(term in text for term in ("announces ban", "announced ban", "imposes ban", "90-day ban", "금지 발표", "금지 결정")):
        return "announced"
    if any(term in text for term in ("voluntary restriction", "voluntary cap", "voluntary limit", "자발적 제한", "자율 제한")):
        return "voluntary"
    if any(term in text for term in ("supports diesel export ban", "backs the idea", "called for", "지지", "요구")):
        return "supports"
    if any(term in text for term in ("considering", "weighs", "weighing", "review", "검토", "논의")):
        return "considering"
    return "policy_change"


def _build_crude_product_gap_alert_body(
    news_rows: list[NewsItem], oil: Quote | None, current: dt.datetime, fx: Quote | None,
) -> str:
    m = _extract_crude_product_gap_metrics(news_rows)
    lines = [current.astimezone(KST).strftime("%Y년 %m월 %d일 %H:%M KST"), "", "[한눈에]"]
    if m.get("crude_mbd") is not None and m.get("crude_pct") is not None:
        lines.append(f"원유          {m['crude_mbd']:.1f} Mbd · 전쟁 전의 {m['crude_pct']:.0f}%")
    if m.get("product_mbd") is not None and m.get("product_pct") is not None:
        lines.append(f"정제품        {m['product_mbd']:.1f} Mbd · 전쟁 전의 {m['product_pct']:.0f}%")
    if m.get("gap_pp") is not None:
        lines.append(f"회복 격차     {m['gap_pp']:.0f}%p · 원유 정상화 ≠ 연료시장 정상화")
    if m.get("hormuz_mbd") is not None:
        lines.append(f"호르무즈      약 {m['hormuz_mbd']:.1f} Mbd")
    if m.get("overall_pct") is not None:
        lines.append(f"전체 흐름     2025년의 {m['overall_pct']:.0f}%")
    market=[]
    if oil is not None:
        direction="↓" if oil.change<0 else "↑" if oil.change>0 else "→"
        market.append(f"Brent USD {oil.price:.2f} {oil.change_pct:+.2f}% {direction}")
    if fx is not None:
        won="약세" if fx.change>0 else "강세" if fx.change<0 else "보합"
        market.append(f"원·달러 {fx.price:,.2f}원 {fx.change_pct:+.2f}% · 원화 {won}")
    if market:
        lines.append("시장          "+" | ".join(market))
    lines.extend([
        "", "[핵심 의미]",
        "원유 자체의 부족은 크게 완화됐지만 경유·휘발유 등 정제품 회복은 훨씬 느립니다.",
        "→ 병목이 원유 물량에서 정제시설·정제품·운송·보험으로 이동하는지 확인해야 합니다.",
        "", "[한국 전이]",
        "정유          정제품 부족이 지속되면 디젤·항공유 정제마진이 원유보다 강할 수 있음",
        "항공·운송     Brent가 내려도 실제 연료비가 같은 속도로 내려가지 않을 수 있음",
        "물가·금리     정제품 가격·원·달러가 높으면 수입물가 완화가 지연될 수 있음",
        "", "[다음 체크]",
        "정제품        58% → 70% → 85% → 95% 회복 여부",
        "실물          호르무즈 약 13 Mbd 유지 · East-West Pipeline 추가 복구",
        "시장          디젤·항공유 정제마진 · VLCC 운임 · Brent · 원·달러",
        "정책          미국 디젤 수출 제한·금지 단계 변화",
        "", "[근거]",
    ])
    for row in news_rows[:3]:
        published=dt.datetime.fromtimestamp(row.published_epoch,tz=UTC).astimezone(KST)
        lines.append(f"{_source_name_ko(row.source)} · {published:%m-%d %H:%M KST}")
        if row.link:
            lines.append(f"원문: {row.link}")
    lines.extend(["", "[주의]", "JP모건 추정치와 Kpler 선박추적치는 집계 범위·다크 플로우 포함 여부가 달라 직접 치환하지 않습니다."])
    return "\n".join(lines).strip()+"\n"


def _build_us_diesel_policy_alert_body(
    news_rows: list[NewsItem], oil: Quote | None, current: dt.datetime, fx: Quote | None,
) -> str:
    stage=_diesel_policy_stage(news_rows)
    labels={"effective":"수출 금지·제한 시행","announced":"수출 금지 발표","supports":"대통령 지지·요구","considering":"정부 검토","voluntary":"정유사 자발적 제한 논의","denied":"전면 금지 보도 부인","withdrawn":"계획 철회","policy_change":"정책 단계 변화"}
    lines=[current.astimezone(KST).strftime("%Y년 %m월 %d일 %H:%M KST"),"","[한눈에]",f"미국 정책     {labels.get(stage,stage)}"]
    if oil is not None:
        direction="↓" if oil.change<0 else "↑" if oil.change>0 else "→"
        lines.append(f"Brent         USD {oil.price:.2f} · {oil.change_pct:+.2f}% {direction}")
    if fx is not None:
        won="약세" if fx.change>0 else "강세" if fx.change<0 else "보합"
        lines.append(f"원·달러       {fx.price:,.2f}원 · {fx.change_pct:+.2f}% · 원화 {won}")
    lines.extend([
        "", "[핵심 의미]",
        "이 사안은 원유 공급이 아니라 글로벌 경유 공급을 직접 바꾸는 정책 변수입니다.",
        "→ 미국 수출이 줄면 해외 디젤 공급은 타이트해질 수 있지만 미국 내 저장이 차면 정유 가동률이 낮아지는 역효과도 가능합니다.",
        "", "[한국 전이]",
        "정유          아시아 디젤 수출 스프레드 확대 가능성 확인",
        "항공·운송     글로벌 경유·항공유 가격 상승 시 비용 부담 확인",
        "물가·금리     정제품 가격 상승이 수입물가·운송비로 전이되는지 확인",
        "", "[다음 체크]",
        "정책          백악관·미 에너지부(DOE) 공식문구 · 금지/자발제한/철회 · 기간·물량",
        "미국          중간유분 수출·재고 · 정유 가동률",
        "세계          디젤·항공유 가격 · 유럽·중남미 대체조달 · 중국 수출",
        "", "[근거]",
    ])
    for row in news_rows[:3]:
        published=dt.datetime.fromtimestamp(row.published_epoch,tz=UTC).astimezone(KST)
        lines.append(f"{_source_name_ko(row.source)} · {published:%m-%d %H:%M KST} · {_news_title_ko(row)}")
        if row.link:
            lines.append(f"원문: {row.link}")
    lines.extend(["","[주의]","검토·지지·자발 제한·금지 발표·실제 시행을 서로 다른 단계로 관리합니다."])
    return "\n".join(lines).strip()+"\n"


def _g7_reserve_stage(text_or_rows: str | list[NewsItem]) -> str:
    text = normalize_text(text_or_rows) if isinstance(text_or_rows, str) else " ".join(normalize_text(row.title) for row in text_or_rows)
    if any(term in text for term in ("release started", "releases begin", "stocks released", "actual release", "방출 시작", "실제 방출")):
        return "release_started"
    if (
        any(term in text for term in ("g7 agrees", "g7 agreed", "agrees to release", "agreed to release", "합의"))
        and any(term in text for term in ("100 million", "100mn", "1억"))
    ):
        return "agreed_100m"
    if (
        any(term in text for term in ("europe agrees", "european countries have agreed", "유럽"))
        and any(term in text for term in ("diesel", "경유"))
        and any(term in text for term in ("immediately", "immediate", "즉시"))
    ):
        return "immediate_diesel"
    if (
        any(term in text for term in ("50 million", "5,000만"))
        and any(term in text for term in ("diesel", "경유"))
        and any(term in text for term in ("crude", "원유"))
    ):
        return "proposal_100m"
    return "agreement_reported"


def _build_g7_reserve_release_alert_body(
    news_rows: list[NewsItem], oil: Quote | None, current: dt.datetime, fx: Quote | None,
) -> str:
    stage = _g7_reserve_stage(news_rows)
    labels = {
        "release_started": "실제 방출 시작",
        "agreed_100m": "경유·원유 합계 1억 배럴 방출 합의 보도",
        "immediate_diesel": "유럽 비축 경유 즉시 방출 합의 발표",
        "proposal_100m": "경유 5,000만+원유 5,000만 배럴 방출안",
        "agreement_reported": "G7 전략비축유 방출 합의 보도",
    }
    lines = [
        current.astimezone(KST).strftime("%Y년 %m월 %d일 %H:%M KST"),
        "",
        "[한눈에]",
        f"G7 상태       {labels.get(stage, stage)}",
        "구성          경유 5,000만 배럴 + IEA 원유 5,000만 배럴 제안이 합의 보도로 단계 상승",
        "시점          FT: 경유 상당 물량 첫 20일 내 · AP: 트럼프 '즉시 방출' 발표",
    ]
    if oil is not None:
        direction = "↓" if oil.change < 0 else "↑" if oil.change > 0 else "→"
        lines.append(f"Brent         USD {oil.price:.2f} · {oil.change_pct:+.2f}% {direction}")
    if fx is not None:
        won = "약세" if fx.change > 0 else "강세" if fx.change < 0 else "보합"
        lines.append(f"원·달러       {fx.price:,.2f}원 · {fx.change_pct:+.2f}% · 원화 {won}")

    lines.extend([
        "",
        "[핵심]",
        "EU의 '검토' 단계에서 G7 차원의 '합의 보도' 단계로 올라왔습니다.",
        "→ 단기 경유·원유 가격과 정제마진에는 하방 압력, 항공·운송·물가에는 완화 방향입니다.",
        "→ 다만 1억 배럴 전체가 경유라는 뜻은 아닙니다. 로이터가 전한 기존 안은 경유 5,000만+원유 5,000만 배럴입니다.",
        "",
        "[다음 확인]",
        "공식          G7·IEA 최종 성명 · 회원국별 배정 물량 · 실제 방출 시작일",
        "경유          첫 20일 실제 방출량 · 유럽 경유 선물·재고",
        "원유          IEA 5,000만 배럴 집행 여부 · Brent 반응",
        "미국          디젤 수출금지 철회·유예 보장 여부",
        "",
        "[근거]",
    ])
    for row in news_rows[:3]:
        published = dt.datetime.fromtimestamp(row.published_epoch, tz=UTC).astimezone(KST)
        lines.append(f"{_source_name_ko(row.source)} · {published:%m-%d %H:%M KST} · {_news_title_ko(row)}")
        if row.link:
            lines.append(f"원문: {row.link}")
    lines.extend([
        "",
        "[주의]",
        "FT는 G7의 1억 배럴 합의를 보도했고, AP는 트럼프의 유럽 경유 '즉시 방출' 발표를 전했습니다.",
        "현재 확인한 공개 G7·IEA 공식문서에는 세부 배정표가 아직 보이지 않아, 실제 집행 물량·시점은 별도 확인합니다.",
    ])
    return "\n".join(lines).strip() + "\n"


def _eu_diesel_reserve_stage(text_or_rows: str | list[NewsItem]) -> str:
    text = normalize_text(text_or_rows) if isinstance(text_or_rows, str) else " ".join(normalize_text(row.title) for row in text_or_rows)
    if any(term in text for term in ("released", "release begins", "stocks released", "방출 시작", "실제 방출")):
        return "released"
    if any(term in text for term in ("approved", "agreed to release", "approve release", "방출 승인", "방출 결정")):
        return "approved"
    if "50 million" in text or "50mn" in text or "5,000만" in text:
        return "proposal_50m"
    if any(term in text for term in ("reject", "rejected", "rules out", "보류", "거부")):
        return "rejected"
    if any(term in text for term in ("coordinate", "coordinated", "coordinating", "iea", "공동대응", "협의")):
        return "coordinating"
    if any(term in text for term in ("consider", "considering", "weigh", "weighing", "discuss", "검토", "논의")):
        return "considering"
    return "policy_change"


def _build_eu_diesel_reserve_alert_body(
    news_rows: list[NewsItem], oil: Quote | None, current: dt.datetime, fx: Quote | None,
) -> str:
    stage = _eu_diesel_reserve_stage(news_rows)
    labels = {
        "released": "전략비축 경유 실제 방출",
        "approved": "전략비축 경유 방출 승인",
        "proposal_50m": "경유 5,000만 배럴 방출안 논의",
        "considering": "경유 전략비축유 방출 검토",
        "coordinating": "EU·IEA 공동 방출 협의",
        "rejected": "추가 방출 보류·거부",
        "policy_change": "전략비축유 정책 변화",
    }
    lines = [
        current.astimezone(KST).strftime("%Y년 %m월 %d일 %H:%M KST"),
        "",
        "[한눈에]",
        f"EU 정책       {labels.get(stage, stage)}",
    ]
    if oil is not None:
        direction = "↓" if oil.change < 0 else "↑" if oil.change > 0 else "→"
        lines.append(f"Brent         USD {oil.price:.2f} · {oil.change_pct:+.2f}% {direction}")
    if fx is not None:
        won = "약세" if fx.change > 0 else "강세" if fx.change < 0 else "보합"
        lines.append(f"원·달러       {fx.price:,.2f}원 · {fx.change_pct:+.2f}% · 원화 {won}")

    lines.extend([
        "",
        "[핵심]",
        "글로벌 경유 공급부족에 대응해 EU가 비축유를 시장에 풀 가능성이 커지는 단계입니다.",
        "→ 실제 방출 시 단기 경유 가격·정제마진을 낮추는 방향이지만, 비축분은 유한해 구조적 공급부족을 해결하지는 못합니다.",
        "",
        "[다음 확인]",
        "정책          EU 회원국 승인 · IEA 공동방출 규모 · 실제 방출 시작일",
        "물량          5,000만 배럴 제안 · 미국 요구 1억2,000만 배럴과의 차이",
        "시장          유럽 경유·미국 ULSD · 아시아 경유 정제마진 · Brent",
        "연결          미국 디젤 수출제한 · 중국 수출중단 · 중동 정제품 회복률",
        "",
        "[근거]",
    ])
    for row in news_rows[:3]:
        published = dt.datetime.fromtimestamp(row.published_epoch, tz=UTC).astimezone(KST)
        lines.append(f"{_source_name_ko(row.source)} · {published:%m-%d %H:%M KST} · {_news_title_ko(row)}")
        if row.link:
            lines.append(f"원문: {row.link}")
    lines.extend([
        "",
        "[주의]",
        "EU 차원의 조율과 실제 방출 결정은 다릅니다. 최종 결정은 회원국별로 이뤄집니다.",
    ])
    return "\n".join(lines).strip() + "\n"


def _china_fuel_export_stage(text_or_rows: str | list[NewsItem]) -> str:
    text = normalize_text(text_or_rows if isinstance(text_or_rows, str) else (
        text_or_rows[0].title if text_or_rows else ""
    ))
    planned = bool(re.search(
        r"\b(?:set to|expected to|plans? to|will|due to|to)\s+(?:re-?)?(?:resume|restart)\b",
        text, re.I
    )) or any(v in text for v in (
        "resumption expected", "재개 예정", "재개할 예정", "재개 전망", "재개 계획"
    ))
    if planned:
        return "planned_resume"
    if any(v in text for v in (
        "cargoes departed", "tankers departed", "vessel departed",
        "shipments loaded", "customs clearance confirms", "verified exports resumed",
        "선박 출항 확인", "실제 선적 재개", "선적 완료", "통관 완료"
    )):
        return "physical_resumed"
    if any(v in text for v in (
        "approved export quota", "exports approved", "approved october exports",
        "authorized exports", "수출 물량 승인", "수출 허가 보도"
    )):
        return "approval_reported"
    if any(v in text for v in (
        "resumed exports", "exports resume", "exports resumed", "resume fuel exports",
        "resumes refined fuel", "refined fuel exports resume", "수출 재개", "재개 발표"
    )):
        return "resumption_reported"
    if any(v in text for v in ("extend", "extended", "until further notice", "연장", "무기한")):
        return "extended"
    if any(v in text for v in ("cancel", "cancels", "cancelled", "canceled", "취소")):
        return "cargo_cancelled"
    if any(v in text for v in ("suspend", "suspended", "suspension", "halt", "halted", "no green light", "중단", "보류")):
        return "suspended"
    if any(v in text for v in ("restrict", "restriction", "curb", "curbs", "제한")):
        return "restricted"
    return "policy_change"


def _china_resumption_volume(rows: list[NewsItem]) -> float | None:
    for row in rows:
        match = re.search(r"approved\s+([0-9]+(?:\.[0-9]+)?)\s+million\s+metric\s+tons", normalize_text(row.title))
        if match and 0 < float(match.group(1)) <= 20:
            return float(match.group(1))
    return None


def _hormuz_7day_stage(text_or_rows: str | list[NewsItem]) -> str:
    text = normalize_text(text_or_rows if isinstance(text_or_rows, str) else (text_or_rows[0].title if text_or_rows else ""))
    if any(v in text for v in ("signed agreement", "proposal accepted", "합의 서명", "제안 수용 공식")):
        return "agreement_reported"
    if any(v in text for v in ("response delivered", "iran replies", "iran responded", "공식 답변 전달", "회신 전달")):
        return "iran_response_reported"
    if any(v in text for v in ("reviewing", "review", "evaluating", "검토", "검토 중")):
        return "reviewing_us_views"
    return "proposal_reported"


def _extract_mma_isaias_data(rows: list[NewsItem]) -> dict[str, float | int | str] | None:
    pattern = (
        r"MMA Isaias date=(\d{4}-\d{2}-\d{2}); oil_bpd=(\d+); "
        r"oil_pct=(\d+\.\d{2}); gas_pct=(\d+\.\d{2}); "
        r"platforms=(\d+); previous_bpd=(\d+); previous_pct=(\d+\.\d{2})"
    )
    for row in rows:
        if row.event_kind!="us_gulf_isaias_shutin" or row.source!="MMA" or row.link!=MMA_OIL_ISAIAS_OCT8_URL:
            continue
        m=re.fullmatch(pattern,row.title)
        if not m:
            continue
        vals={
            "date":m.group(1),"oil_bpd":int(m.group(2)),
            "oil_pct":float(m.group(3)),"gas_pct":float(m.group(4)),
            "platforms":int(m.group(5)),"previous_bpd":int(m.group(6)),
            "previous_pct":float(m.group(7))
        }
        if not(0<=vals["oil_pct"]<=100 and 0<=vals["previous_pct"]<=100
           and 0<vals["oil_bpd"]<5_000_000 and 0<vals["previous_bpd"]<5_000_000):
            return None
        return vals
    return None


def _parse_mma_isaias_report(raw_html: str, date: str) -> dict[str, float | int]:
    text=_visible_text(raw_html)
    report_day=dt.date.fromisoformat(date)
    date_label=f"{report_day:%B} {report_day.day}, {report_day.year}"
    if "Isaias" not in text or date_label not in text or "Marine Minerals Administration" not in text:
        raise RuntimeError("MMA 공식 보고서 명칭·날짜 불일치")
    p=re.search(r"approximately\s+(\d+\.\d+)%\s+of\s+the\s+current\s+(?:daily\s+)?oil\s+production",text,re.I)
    g=re.search(r"(\d+\.\d+)%\s+of\s+the\s+current\s+(?:daily\s+)?natural\s+gas\s+production",text,re.I)
    q=re.search(r"Oil,\s*BOPD\*{0,3}\s*Shut-in\s+([\d,]+)",text,re.I)
    f=re.search(r"evacuated\s+from\s+a\s+total\s+of\s+([\d,]+)\s+production\s+platforms",text,re.I)
    if not all((p,g,q,f)):
        raise RuntimeError("MMA 중단율·물량·대피시설 값 부족")
    vals={"oil_pct":float(p.group(1)),"gas_pct":float(g.group(1)),
          "oil_bpd":int(q.group(1).replace(",","")),
          "platforms":int(f.group(1).replace(",",""))}
    if not (0<=vals["oil_pct"]<=100 and 0<=vals["gas_pct"]<=100
         and 0<vals["oil_bpd"]<5_000_000 and 0<=vals["platforms"]<=371):
        raise RuntimeError("MMA 숫자 범위 오류")
    return vals


def fetch_mma_isaias_snapshot(current: dt.datetime) -> NewsItem:
    observed=dt.datetime(2026,10,8,16,tzinfo=UTC)
    if not (observed <= current and (current-observed).total_seconds()<=48*3600):
        raise RuntimeError("MMA 허리케인 중단율 공식 자료 신선도 종료")
    old=_parse_mma_isaias_report(fetch_bytes(MMA_OIL_ISAIAS_OCT7_URL,timeout=18,attempts=2).decode("utf-8","replace"),"2026-10-07")
    latest=_parse_mma_isaias_report(fetch_bytes(MMA_OIL_ISAIAS_OCT8_URL,timeout=18,attempts=2).decode("utf-8","replace"),"2026-10-08")
    title=(
        f"MMA Isaias date=2026-10-08; oil_bpd={latest['oil_bpd']}; "
        f"oil_pct={latest['oil_pct']:.2f}; gas_pct={latest['gas_pct']:.2f}; "
        f"platforms={latest['platforms']}; previous_bpd={old['oil_bpd']}; "
        f"previous_pct={old['oil_pct']:.2f}"
    )
    return NewsItem(title,"MMA",MMA_OIL_ISAIAS_OCT8_URL,
                    observed.isoformat().replace("+00:00","Z"),
                    observed.timestamp(),"us_gulf_isaias_shutin")


def parse_china_reuters_resumption(raw_html: str, current: dt.datetime) -> NewsItem:
    observed=dt.datetime(2026,10,9,3,27,tzinfo=UTC)
    if not(observed<=current and (current-observed).total_seconds()<=36*3600):
        raise RuntimeError("중국 Reuters 수출 재개 보도의 유효기간 경과")
    text=normalize_text(_visible_text(raw_html))
    if not all(v in text for v in ("china","october","fuel exports")) or not (
        ("set to resume" in text or "to resume" in text)
        and ("four traders" in text or "four trade sources" in text)
    ):
        raise RuntimeError("중국 Reuters 기사 식별·재개 예정 상태 검증 실패")
    m=re.search(r"([0-9]+(?:\.[0-9]+)?)\s+million\s+(?:metric\s+)?tons",text)
    if not m or not(0<float(m.group(1))<20):
        raise RuntimeError("중국 정제품 수출 허가 관련 보도 물량 직접 확인 실패")
    title=f"China to resume October fuel exports after holiday pause; four trade sources say; approved {float(m.group(1)):.1f} million metric tons"
    return NewsItem(title,"Reuters",CHINA_REUTERS_20261009_URL,
                    observed.isoformat().replace("+00:00","Z"),observed.timestamp(),
                    "china_fuel_export_policy")


def parse_hormuz_xinhua_review(raw_html: str,current: dt.datetime) -> NewsItem:
    observed=dt.datetime(2026,10,9,1,11,tzinfo=UTC)
    if not(observed<=current and (current-observed).total_seconds()<=36*3600):
        raise RuntimeError("7일 이내 호르무즈 협상 보도 신선도 종료")
    text=normalize_text(_visible_text(raw_html))
    if not all(v in text for v in ("araghchi","seven-day plan","reviewing","hormuz")):
        raise RuntimeError("신화통신 원문 아라그치 발언 미검증")
    return NewsItem(
        "Iran Araghchi reviewing US views on seven-day plan to reopen Strait of Hormuz within seven days",
        "Xinhua",HORMUZ_7DAY_XINHUA_URL,
        observed.isoformat().replace("+00:00","Z"),observed.timestamp(),
        "hormuz_7day_diplomacy"
    )

def _build_hormuz_7day_alert_body(
    news_rows: list[NewsItem], oil: Quote | None, current: dt.datetime, fx: Quote | None
) -> str:
    stage=_hormuz_7day_stage(news_rows)
    state={
        "reviewing_us_views":"이란, 미국 측 답변 검토 중",
        "proposal_reported":"조건부 7일 이내 재개방안 전달",
        "iran_response_reported":"이란 측 회신 전달 보도",
        "agreement_reported":"합의 보도·실제 통항 미확인",
    }
    lines=[
        current.astimezone(KST).strftime("%Y년 %m월 %d일 %H:%M KST"),
        "", "[한눈에]",f"협상 상태     {state.get(stage,stage)}",
        "의미          조건 수용 시 7일 이내 호르무즈 재개방 제안",
        "실물          해협 실제 통항 정상화·안전은 아직 별도 확인",
    ]
    if oil is not None:
        arrow="↑" if oil.change>0 else "↓" if oil.change<0 else "→"
        lines.append(f"Brent         USD {oil.price:.2f} · {oil.change_pct:+.2f}% {arrow}")
    lines.extend([
        "", "[핵심]",
        "아라그치 이란 외무장관은 미국 의견을 검토하고 수일 내 회신할 예정이라고 밝혔습니다.",
        "→ '7일 이내 조건부 재개방'이지 '7일 동안 개방 확정'이 아닙니다.",
        "", "[다음 확인]",
        "외교          미국·이란 최종 답변 · 서명·발효 일자",
        "물류          호르무즈 실제 통과 원유·선박 수·보험·안전",
        "시장          원유가격 · 정제품 · VLCC 운임",
        "", "[근거]",
    ])
    for row in news_rows[:2]:
        d=dt.datetime.fromtimestamp(row.published_epoch,tz=UTC).astimezone(KST)
        lines.append(f"{_source_name_ko(row.source)} · {d:%m-%d %H:%M KST} · {_news_title_ko(row)}")
        if row.link: lines.append(f"원문: {row.link}")
    return "\n".join(lines).strip()+"\n"


def _build_us_gulf_isaias_alert_body(
    news_rows: list[NewsItem], oil: Quote | None, current: dt.datetime, fx: Quote | None
) -> str:
    m=_extract_mma_isaias_data(news_rows)
    if m is None: raise RuntimeError("MMA 공식 중단자료 불일치 · 발송 차단")
    current_bpd=int(m["oil_bpd"])
    previous_bpd=int(m["previous_bpd"])
    lines=[
        current.astimezone(KST).strftime("%Y년 %m월 %d일 %H:%M KST"),
        "", "[현재 숫자]",
        f"원유 중단     {current_bpd:,}배럴/일 · 해상 생산의 {float(m['oil_pct']):.2f}%",
        f"전날          {previous_bpd:,}배럴/일 · {float(m['previous_pct']):.2f}%",
        f"증가분        {current_bpd-previous_bpd:+,}배럴/일 · {float(m['oil_pct'])-float(m['previous_pct']):+.2f}%p",
        f"추가          가스 {float(m['gas_pct']):.2f}% 중단 · 생산시설 {int(m['platforms'])}개 대피",
    ]
    if oil is not None and fx is not None:
        exposure=current_bpd*oil.price*fx.price
        lines.append(f"가격환산      하루 중단 물량×유가 약 {exposure/1e8:,.0f}억원 · 실제 매출 손실 아님")
    lines.extend([
        "", "[핵심]",
        "안전을 위한 임시 가동 중단으로, 실제 설비 파손이나 영구 공급 감소와는 다릅니다.",
        "→ 중동 호르무즈 물류 위험과 미국 멕시코만 생산 위험은 별도 공급 병목입니다.",
        "", "[다음 확인]",
        "미국          MMA 후속 중단율 · 피해 시설 · 재가동 시점",
        "중동          실제 호르무즈 통항량 · 재개방 협상",
        "제품          정유시설 가동·항만 수출·경유 가격",
        "", "[근거]",
        "미국 해양광물관리청(MMA) · 10월 8일 오전 11시(미국 중부시간) 기준",
        f"원문: {MMA_OIL_ISAIAS_OCT8_URL}",
        "", "[주의]",
        "사업자 신고 기반 일별 중단 추정치이며 후속 복구 숫자를 확인해야 합니다.",
    ])
    return "\n".join(lines).strip()+"\n"


def _build_china_fuel_export_policy_alert_body(
    news_rows: list[NewsItem], oil: Quote | None, current: dt.datetime, fx: Quote | None,
) -> str:
    stage = _china_fuel_export_stage(news_rows)
    labels = {
        "planned_resume": "재개 예정 · 실제 출항 미확인",
        "approval_reported": "승인 물량 보도 · 실제 출항 미확인",
        "physical_resumed": "선적·출항 재개 확인",
        "resumption_reported": "재개 보도 · 실제 선적 확인 필요",
        "resumed": "수출 재개·허용",
        "extended": "수출 중단·제한 연장",
        "cargo_cancelled": "기존 10월 선적 취소",
        "suspended": "홍콩·마카오 외 수출 중단",
        "restricted": "정제품 수출 제한",
        "policy_change": "정제품 수출정책 변화",
    }
    lines = [
        current.astimezone(KST).strftime("%Y년 %m월 %d일 %H:%M KST"),
        "",
        "[한눈에]",
        f"중국 정책     {labels.get(stage, stage)}",
    ]
    quota = _china_resumption_volume(news_rows)
    if stage == "planned_resume" and quota is not None:
        lines.append(f"10월 승인 보도  휘발유·경유·항공유 합산 약 {quota*100:.0f}만 톤 · 관계자 전언")
        lines.append("9월 비교       400만 톤 초과 예상 · 10월 승인 보도량이 더 적음")
    if oil is not None:
        direction = "↓" if oil.change < 0 else "↑" if oil.change > 0 else "→"
        lines.append(f"Brent         USD {oil.price:.2f} · {oil.change_pct:+.2f}% {direction}")
    if fx is not None:
        won = "약세" if fx.change > 0 else "강세" if fx.change < 0 else "보합"
        lines.append(f"원·달러       {fx.price:,.2f}원 · {fx.change_pct:+.2f}% · 원화 {won}")

    if stage in ("planned_resume","approval_reported","physical_resumed","resumption_reported"):
        lines.extend([
            "", "[핵심 의미]",
            "수출 재개 움직임은 아시아 제품 공급 압박을 낮출 수 있지만 실제 출항·도착 물량이 확인돼야 합니다.",
            "→ 허가·재개 예정·화물 출항은 별도 단계입니다.",
            "", "[한국 전이]",
            "정유          디젤·항공유 정제마진 조정 가능성",
            "항공·운송     실제 연료비 완화 여부 확인",
            "물가          정제품 가격·환율 전이 시차 확인",
            "", "[다음 확인]",
            "중국          월별 승인 공고 · 실제 통관·선적·도착량",
            "시장          싱가포르 경유 정제마진 · VLCC 운임",
            "역풍          호르무즈 물류 차질·미국 허리케인 해상 생산 중단",
        ])
    else:
        lines.extend([
        "",
        "[핵심 의미]",
        "원유가 회복돼도 중국이 경유·휘발유·항공유 수출을 막으면 글로벌 정제품 공급은 다시 타이트해질 수 있습니다.",
        "→ 이번 병목은 원유 부족이 아니라 정제·제품 수출정책 쪽에서 생기는 공급 충격입니다.",
        "",
        "[한국 전이]",
        "정유          아시아 디젤·항공유 정제마진 상승 시 한국 정유사의 수출 스프레드에 우호적",
        "항공·운송     연료비 하락 지연 또는 재상승 위험",
        "물가·금리     정제품 가격 상승이 수입물가·운송비로 전이되는지 확인",
        "",
        "[다음 체크]",
        "중국          10월 7일 연휴 종료 뒤 수출 허용 여부 · PetroChina 취소 물량 재계약 여부",
        "제품          디젤·항공유·휘발유 수출량 · 중국 내 재고 · 정유 가동률",
        "아시아        싱가포르 경유 정제마진 · 10~11월 스프레드 · 한국 정유사 수출마진",
        "동시 변수     러시아 디젤 수출금지 · 미국 디젤 수출제한 검토 · 중동 정제품 회복률",
        ])
    lines.extend(["", "[근거]"])
    for row in news_rows[:3]:
        published = dt.datetime.fromtimestamp(row.published_epoch, tz=UTC).astimezone(KST)
        lines.append(f"{_source_name_ko(row.source)} · {published:%m-%d %H:%M KST} · {_news_title_ko(row)}")
        if row.link:
            lines.append(f"원문: {row.link}")
    lines.extend([
        "",
        "[주의]",
        ("Reuters 관계자 전언에 따른 재개 예정이며 승인 보도량은 실제 선적·도착량이 아닙니다."
         if stage in ("planned_resume","approval_reported","resumption_reported")
         else "현재 공개 보도는 관계자 전언 기반입니다. 중국 정부의 공개 명령문이 확인되기 전에는 공식 전면 금지로 표현하지 않습니다. 실제 선적·도착도 별도로 확인합니다."),
    ])
    return "\n".join(lines).strip() + "\n"


def _extract_regional_export_metrics(news_rows: list[NewsItem]) -> dict[str, float | None]:
    text = " ".join(normalize_text(row.title) for row in news_rows)

    snapshot = re.search(
        r"middle east crude exports snapshot\s+([0-9.]+)\s+mbd;\s*"
        r"hormuz\s+([0-9.]+)\s+mbd;\s*"
        r"february\s+([0-9.]+)\s+mbd;\s*"
        r"gap\s+([0-9.]+)\s+mbd;\s*recovery\s+([0-9.]+)%",
        text,
        flags=re.I,
    )
    if snapshot:
        return {
            "current_mbd": float(snapshot.group(1)),
            "hormuz_mbd": float(snapshot.group(2)),
            "feb_mbd": float(snapshot.group(3)),
            "gap_mbd": float(snapshot.group(4)),
            "recovery_pct": float(snapshot.group(5)),
        }

    def find_value(pattern: str):
        match = re.search(pattern, text, flags=re.I)
        return float(match.group(1)) if match else None

    current = find_value(
        r"(?:middle east|mideast).*?([0-9]+(?:\.[0-9]+)?)\s*"
        r"(?:million\s+bpd|million\s+barrels\s+per\s+day|mbd)"
    )
    feb = find_value(
        r"(?:february|prewar|pre-war).*?([0-9]+(?:\.[0-9]+)?)\s*"
        r"(?:million\s+bpd|million\s+barrels\s+per\s+day|mbd)"
    )
    hormuz = find_value(
        r"hormuz.*?([0-9]+(?:\.[0-9]+)?)\s*"
        r"(?:million\s+bpd|million\s+barrels\s+per\s+day|mbd)"
    )
    gap = feb - current if feb is not None and current is not None else None
    recovery = current / feb * 100.0 if feb and current is not None else None
    return {
        "current_mbd": current,
        "feb_mbd": feb,
        "hormuz_mbd": hormuz,
        "gap_mbd": gap,
        "recovery_pct": recovery,
    }


def _extract_india_gulf_metrics(news_rows: list[NewsItem]) -> dict[str, float | None]:
    text = " ".join(normalize_text(row.title) for row in news_rows)
    nums = [float(v) for v in re.findall(r"\b([0-9]+(?:\.[0-9]+)?)\s*(?:mb/d|mbd|million\s+bpd)", text)]
    current = max(nums) if nums else None
    return {"current_mbd": current}



def _build_east_west_pipeline_alert_body(
    news_rows: list[NewsItem], oil: Quote | None, current: dt.datetime, fx: Quote | None,
) -> str:
    rate, yanbu = _extract_pipeline_rate(news_rows)
    capacity_pct = _extract_pipeline_capacity_pct(news_rows)
    exports_resumed = _pipeline_exports_resumed(news_rows)

    lines = [
        current.astimezone(KST).strftime("%Y년 %m월 %d일 %H:%M KST"),
        "",
        "[한눈에]",
    ]
    if capacity_pct is not None:
        implied = 7.0 * capacity_pct / 100.0
        lines.append(f"East-West     최대 수송능력의 {capacity_pct:.0f}% 이상 · 최소 {implied:.1f} Mbd 수준")
    elif rate is not None:
        lines.append(f"East-West     {rate:.1f} Mbd · 7 Mbd 명목능력의 약 {rate / 7.0 * 100:.0f}%")
        lines.append(f"vs 4Mbd      약 {rate / 4.0 * 100:.0f}% 회복")
    else:
        lines.append("East-West     재가동·유량 회복 확인")
    if exports_resumed:
        lines.append("Yanbu 수출     재개 확인")
    elif yanbu:
        lines.append("Yanbu         기사 내 직접 언급 · 선적 재개 여부 추가 확인")
    else:
        lines.append("Yanbu 수출     실제 선적 별도 확인 필요")

    market = []
    if oil is not None:
        direction = "↓" if oil.change < 0 else "↑" if oil.change > 0 else "→"
        market.append(f"Brent USD {oil.price:.2f} {oil.change_pct:+.2f}% {direction}")
    if fx is not None:
        won = "약세" if fx.change > 0 else "강세" if fx.change < 0 else "보합"
        market.append(f"원·달러 {fx.price:,.2f}원 {fx.change_pct:+.2f}% · 원화 {won}")
    if market:
        lines.append("시장          " + " | ".join(market))

    lines.extend([
        "",
        "[핵심]",
        "사우디의 호르무즈 우회 공급축이 빠르게 정상화되면서 홍해를 통한 수출 여력이 크게 늘고 있습니다.",
        (
            "→ Yanbu 해외 선적 재개가 확인돼 송유관 회복이 실제 수출로 연결되기 시작했습니다."
            if exports_resumed
            else "→ 다만 송유관 내부 유량과 Yanbu 실제 선적은 다릅니다. 선적 재개 확인 전 수출 정상화로 단정하지 않습니다."
        ),
        "→ 7 Mbd 명목능력의 80%는 5.6 Mbd입니다. 80% 초과라면 최소 이 수준을 넘어선 것으로 볼 수 있습니다.",
        "",
        "[다음 확인]",
        "유량          80% → 90% → 95% · 실제 Mbd",
        "수출          Yanbu 선적량 · 홍해 수출 가능 물량 · 사우디 국내 정유 투입량",
        "위험          송유관 재공격 · Bab el-Mandeb 통항 · 보험·VLCC 운임",
        "",
        "[근거]",
    ])
    for row in news_rows[:3]:
        published = dt.datetime.fromtimestamp(row.published_epoch, tz=UTC).astimezone(KST)
        lines.append(f"{_source_name_ko(row.source)} · {published:%m-%d %H:%M KST} · {_news_title_ko(row)}")
        if row.link:
            lines.append(f"원문: {row.link}")
    lines.extend([
        "",
        "[주의]",
        "명목 최대능력 7 Mbd와 실제 지속가능 처리량은 다를 수 있으므로, 가동률·실제 선적량을 함께 확인합니다.",
    ])
    return "\n".join(lines).strip() + "\n"


def _build_saudi_osp_alert_body(
    news_rows: list[NewsItem], oil: Quote | None, current: dt.datetime, fx: Quote | None,
) -> str:
    m = _extract_saudi_osp_metrics(news_rows)
    month = str(m.get("delivery_month") or "해당 월")
    light = m.get("asia_light")
    light_delta = m.get("asia_light_delta")
    medium = m.get("asia_medium")
    medium_delta = m.get("asia_medium_delta")
    heavy = m.get("asia_heavy")
    heavy_delta = m.get("asia_heavy_delta")
    europe_delta = m.get("europe_delta")
    widest = bool(m.get("widest_since_2020"))

    lines = [
        current.astimezone(KST).strftime("%Y년 %m월 %d일 %H:%M KST"),
        "",
        "[한눈에]",
    ]
    if light is not None:
        line = f"{month} Arab Light  Oman/Dubai 평균 대비 {float(light):+.2f}달러/배럴"
        if light_delta is not None:
            line += f" · 전월 대비 {float(light_delta):+.2f}달러"
        lines.append(line)
    if medium is not None and heavy is not None:
        medium_text = f"{float(medium):+.2f}"
        heavy_text = f"{float(heavy):+.2f}"
        if medium_delta is not None and heavy_delta is not None:
            lines.append(
                f"중·중질유      Arab Medium {medium_text} · Arab Heavy {heavy_text}달러/배럴 "
                f"· 둘 다 전월 대비 {float(medium_delta):+.0f}달러"
            )
        else:
            lines.append(f"중·중질유      Arab Medium {medium_text} · Arab Heavy {heavy_text}달러/배럴")
    if europe_delta is not None:
        lines.append(f"지역 차별화    서북유럽 전월 대비 +{float(europe_delta):.0f}달러 · 미국 동결")
    if widest:
        lines.append("역사 비교      Arab Light 아시아 할인폭 2020년 6월 이후 최대")

    if fx is not None and light is not None:
        krw_diff = abs(float(light)) * fx.price
        lines.append(f"원화 환산      Arab Light 할인폭 약 {krw_diff:,.0f}원/배럴")
    if oil is not None:
        direction = "↓" if oil.change < 0 else "↑" if oil.change > 0 else "→"
        lines.append(f"Brent         USD {oil.price:.2f} · {oil.change_pct:+.2f}% {direction}")

    lines.extend([
        "",
        "[핵심]",
        "아시아에만 큰 폭으로 가격 차등을 낮춘 것은 물량 회복 국면에서 시장점유율을 방어하고 높은 운송비를 일부 상쇄하려는 신호로 해석할 수 있습니다.",
        "→ 다만 '-5달러'는 원유의 절대가격이 아니라 Oman/Dubai 기준 대비 공식판매가격 차등입니다.",
        "→ 유럽은 인상·미국은 동결이라 글로벌 수요 붕괴 신호로 단순 해석하면 안 됩니다.",
        "",
        "[한국 전이]",
        "정유          사우디 장기계약 원유의 기준 차등 하락은 아시아 정유사 원료비에 우호적",
        "운임          높은 VLCC·보험 비용이 실제 도착원가 절감폭을 깎을 수 있음",
        "제품          실제 이익은 경유·항공유 정제마진과 제품 수출가격까지 함께 확인",
        "",
        "[다음 확인]",
        "사우디        다음 월 Arab Light·Medium·Heavy OSP와 월간 변화",
        "아시아        Oman/Dubai 현물차익 · Saudi term nomination · VLCC 운임",
        "지역차        아시아 인하가 유럽·미국으로 확산되는지 여부",
        "실물          호르무즈 통과량 · East-West Pipeline · 오만만 선박 간 이송",
        "",
        "[근거]",
    ])
    for row in news_rows[:3]:
        published = dt.datetime.fromtimestamp(row.published_epoch, tz=UTC).astimezone(KST)
        lines.append(f"{_source_name_ko(row.source)} · {published:%m-%d %H:%M KST} · {_news_title_ko(row)}")
        if row.link:
            lines.append(f"원문: {row.link}")
    lines.extend([
        "",
        "[주의]",
        "OSP는 장기계약 원유의 벤치마크 대비 가격 차등입니다. 사우디 원유 자체를 배럴당 5달러에 판매한다는 뜻이 아닙니다.",
        "이번 11월 수치는 Reuters 보도와 Aramco 성명을 전달한 Argaam 자료를 교차 확인했습니다.",
    ])
    return "\n".join(lines).strip() + "\n"


def _build_ex_iran_prewar_alert_body(
    news_rows: list[NewsItem], oil: Quote | None, current: dt.datetime, fx: Quote | None,
) -> str:
    m = _extract_ex_iran_prewar_metrics(news_rows)
    crude = float(m.get("current_mbd") or 0.0)
    hormuz = float(m.get("hormuz_mbd") or 0.0)
    hormuz_pct = float(m.get("hormuz_pct") or 0.0)
    bypass = float(m.get("bypass_pct") or 0.0)
    prewar_bypass = float(m.get("prewar_bypass_pct") or 0.0)
    sts = m.get("sts_pct")

    prewar_hormuz_mbd = crude * (1.0 - prewar_bypass / 100.0) if crude and prewar_bypass else None
    current_bypass_mbd = crude * bypass / 100.0 if crude and bypass else None
    prewar_bypass_mbd = crude * prewar_bypass / 100.0 if crude and prewar_bypass else None
    hormuz_gap_mbd = prewar_hormuz_mbd - hormuz if prewar_hormuz_mbd is not None and hormuz else None
    bypass_gain_mbd = current_bypass_mbd - prewar_bypass_mbd if current_bypass_mbd is not None and prewar_bypass_mbd is not None else None

    lines = [
        current.astimezone(KST).strftime("%Y년 %m월 %d일 %H:%M KST"),
        "",
        "[한눈에]",
        f"이란 제외 원유  {crude:.1f} Mbd · 전쟁 전 평균의 100%",
        f"호르무즈      {hormuz:.1f} Mbd · 전체의 {hormuz_pct:.0f}%",
        f"우회          {bypass:.0f}% · 전쟁 전 {prewar_bypass:.0f}%",
    ]
    if sts is not None:
        lines.append(f"선박 간 이송  호르무즈 통과 원유의 70% 초과")
    if hormuz_gap_mbd is not None and bypass_gain_mbd is not None:
        lines.append(
            f"구조 변화     호르무즈 약 {hormuz_gap_mbd:.1f} Mbd 감소 ↔ 우회 약 {bypass_gain_mbd:.1f} Mbd 증가"
        )

    market = []
    if oil is not None:
        direction = "↓" if oil.change < 0 else "↑" if oil.change > 0 else "→"
        market.append(f"Brent USD {oil.price:.2f} {oil.change_pct:+.2f}% {direction}")
    if fx is not None:
        won = "약세" if fx.change > 0 else "강세" if fx.change < 0 else "보합"
        market.append(f"원·달러 {fx.price:,.2f}원 {fx.change_pct:+.2f}% · 원화 {won}")
    if market:
        lines.append("시장          " + " | ".join(market))

    lines.extend([
        "",
        "[핵심]",
        "원유 총량은 이란 제외 기준 전쟁 전 수준까지 회복했지만 운송 경로는 아직 정상화되지 않았습니다.",
        "→ 원유 공급 정상화와 호르무즈·운임·보험 정상화를 같은 의미로 보면 안 됩니다.",
        "",
        "[다음 확인]",
        "총량          이란 제외 16.5 Mbd 유지·상향 여부",
        "호르무즈      60% → 70% → 전쟁 전 83% 회복 여부",
        "우회          40% → 30% → 전쟁 전 17% 정상화 여부",
        "물류          선박 간 이송 비중 · VLCC 회전주기 · 보험료",
        "이란          약 1.7 Mbd 전쟁 전 수출분 복귀 여부",
        "",
        "[근거]",
    ])
    for row in news_rows[:2]:
        published = dt.datetime.fromtimestamp(row.published_epoch, tz=UTC).astimezone(KST)
        lines.append(f"{_source_name_ko(row.source)} · {published:%m-%d %H:%M KST} · {_news_title_ko(row)}")
        if row.link:
            lines.append(f"원문: {row.link}")
    lines.extend([
        "",
        "[주의]",
        "이 수치는 이란을 제외한 걸프 원유 기준이며, Reuters의 2월 단일월 19.513 Mbd 비교와 분모가 다릅니다.",
    ])
    return "\n".join(lines).strip() + "\n"


def _build_sts_compact_alert_body(
    news_rows: list[NewsItem],
    oil: Quote | None,
    current: dt.datetime,
    fx: Quote | None,
    metrics: dict[str, object],
) -> str:
    lines = [
        current.astimezone(KST).strftime("%Y년 %m월 %d일 %H:%M KST"),
        "",
        "[한눈에]",
        "원유 공급     회복 ↑",
        "물류 효율     병목 심화 ↓",
        (
            f"GoO STS       {float(metrics['current_mbd']):.1f} Mbd · "
            f"전쟁 후 평균 {float(metrics['since_war_mbd']):.1f} · "
            f"2025 평균 {float(metrics['baseline_2025_mbd']):.2f}"
        ),
    ]
    if metrics.get("vs_war_avg") is not None and metrics.get("vs_2025_avg") is not None:
        lines.append(
            f"현재 강도     전쟁 후 평균의 {float(metrics['vs_war_avg']):.1f}배 · "
            f"2025 평균의 {float(metrics['vs_2025_avg']):.0f}배"
        )
    if metrics.get("vlcc_low") is not None:
        lines.append(
            f"VLCC 수요     Saudi +{float(metrics['saudi_increment_mbd']):.0f} Mbd 처리 시 "
            f"+{int(metrics['vlcc_low'])}~{int(metrics['vlcc_high'])}척"
        )

    market_bits: list[str] = []
    if oil is not None:
        direction = "↓" if oil.change < 0 else "↑" if oil.change > 0 else "→"
        market_bits.append(f"Brent USD {oil.price:.2f} · {oil.change_pct:+.2f}% {direction}")
    if fx is not None:
        won = "약세" if fx.change > 0 else "강세" if fx.change < 0 else "보합"
        market_bits.append(f"원·달러 {fx.price:,.2f}원 · {fx.change_pct:+.2f}% · 원화 {won}")
    if market_bits:
        lines.append("시장          " + " | ".join(market_bits))

    lines.extend([
        "",
        "[핵심 의미]",
        "원유는 회복 중이지만 정상 항로 복귀가 아니라 GoO STS 우회입니다.",
        "→ 유가 하방 가능 / VLCC 운임·물류비 상방 가능 · 수출 회복 ≠ 물류 정상화",
        "",
        "[한국 전이]",
    ])
    if oil is not None and fx is not None:
        if oil.change < 0 and fx.change <= 0:
            lines.append("현재          유가 ↓ + 원화 강세/안정 → 수입물가·에너지 원가·금리 부담 완화")
        elif oil.change < 0 and fx.change > 0:
            lines.append("현재          유가 ↓ + 원화 약세 → 수입원가 완화 효과 일부 상쇄")
        elif oil.change > 0 and fx.change > 0:
            lines.append("현재          유가 ↑ + 원화 약세 → 수입물가·금리·기업 원가 부담 확대")
        else:
            lines.append("현재          유가·환율 신호 엇갈림 → 업종별 실적 영향 차별화")
    elif oil is not None:
        lines.append("현재          유가 방향 확인 · 원·달러 검증값 부재로 국내 전이 숫자 판정 보류")
    else:
        lines.append("현재          유가·원·달러 동시 검증 부재 · 국내 전이는 정성 판단만 유지")

    if fx is not None and fx.change < 0:
        lines.append("실적          원화 강세는 달러 매출 환산에 부담 · 유가 하락은 항공·전력/가스·운송·석유화학 원가에 완화")
    elif fx is not None and fx.change > 0:
        lines.append("실적          원화 약세는 달러 매출 환산에 우호적 · 원가 민감 업종은 수입비용 부담 확인")
    else:
        lines.append("실적          달러 매출 수출기업과 항공·전력/가스·운송·석유화학 원가 민감 업종을 분리 확인")
    lines.append("다음          원·달러 → 수입물가/CPI → 국고채 금리 → 3분기 실적 가이던스")

    lines.extend([
        "",
        "[병목]",
        "핵심          Fujairah·Sohar 처리능력 · STS 슬롯/예인선/파일럿/검사 · VLCC 회전율",
        "확대 시       서인도 → 말레이시아로 이송거리 확대 · Kpler 최대 58척 시나리오",
        "",
        "[다음 체크]",
        "실물          호르무즈 통과량 · Saudi Gulf/Red Sea 선적 · GoO STS 7일 평균",
        "우회/시장     East-West 3.0→3.5→4.0 Mbd · Yanbu 선적 · VLCC 운임 · Brent · 원·달러",
        "한국          수입물가/CPI · 국고채 금리 · 3분기 기업 실적 가이던스",
        "",
        "[근거]",
    ])

    for row in news_rows[:2]:
        published = dt.datetime.fromtimestamp(row.published_epoch, tz=UTC).astimezone(KST)
        if "kpler" in normalize_text(row.source):
            lines.append(
                f"Kpler · 기준 {metrics['source_date']} · STS {float(metrics['current_mbd']):.1f} Mbd"
            )
        else:
            lines.append(f"{_source_name_ko(row.source)} · {published:%m-%d %H:%M KST}")
        if row.link:
            lines.append(f"원문: {row.link}")

    lines.extend([
        "",
        "[주의]",
        "STS는 같은 배럴이 여러 번 이송될 수 있어 호르무즈 통과량·중동 전체 수출량과 합산하지 않습니다.",
        "정책 발언 처리: 실물 물량·통항 데이터 없이 '정상화'로 판정하지 않습니다.",
    ])
    return "\n".join(lines).strip() + "\n"


def _build_oil_flow_compact_alert_body(
    news_rows: list[NewsItem],
    oil: Quote | None,
    current: dt.datetime,
    fx: Quote | None,
) -> str:
    lines = [
        current.astimezone(KST).strftime("%Y년 %m월 %d일 %H:%M KST"),
        "",
        "[한눈에]",
        "실물          중동 원유 수출 회복 · 호르무즈 정상화는 아직 아님",
    ]

    market_bits: list[str] = []
    if oil is not None:
        direction = "↓" if oil.change < 0 else "↑" if oil.change > 0 else "→"
        market_bits.append(f"Brent USD {oil.price:.2f} · {oil.change_pct:+.2f}% {direction}")
    if fx is not None:
        won = "약세" if fx.change > 0 else "강세" if fx.change < 0 else "보합"
        market_bits.append(f"원·달러 {fx.price:,.2f}원 · {fx.change_pct:+.2f}% · 원화 {won}")
    if market_bits:
        lines.append("시장          " + " | ".join(market_bits))

    lines.extend(["", "[핵심]"])
    if oil is not None and fx is not None and oil.change > 0 and fx.change > 0:
        lines.append("원유 물량은 회복 중이지만 현재 시장가격은 반대로 상승 중입니다.")
        lines.append("→ 유가 ↑ + 원화 약세 → 한국 수입물가·에너지 원가·금리 부담 확대")
    elif oil is not None and fx is not None and oil.change < 0 and fx.change <= 0:
        lines.append("원유 회복과 시장가격 하락이 같은 방향입니다.")
        lines.append("→ 유가 ↓ + 원화 강세/안정 → 한국 수입원가·물가 부담 완화")
    elif oil is not None and fx is not None:
        lines.append("원유 회복과 유가·환율 신호가 엇갈립니다.")
        lines.append("→ 국내 영향은 원·달러와 정제품 가격까지 함께 확인")
    else:
        lines.append("원유는 다시 나오지만 정상 항로·운임까지 정상화된 것은 아닙니다.")

    lines.extend([
        "",
        "[다음 확인]",
        "실물          호르무즈 통과량 · 사우디 걸프/홍해 선적 · Yanbu·East-West Pipeline",
        "물류          오만만 선박 간 이송(STS) · VLCC 운임/가용선복 · 보험",
        "한국          원·달러 · 수입물가/CPI · 국고채 금리 · 기업 실적",
        "",
        "[근거]",
    ])
    for row in news_rows[:2]:
        published = dt.datetime.fromtimestamp(row.published_epoch, tz=UTC).astimezone(KST)
        lines.append(f"{_source_name_ko(row.source)} · {published:%m-%d %H:%M KST}")
        if row.link:
            lines.append(f"원문: {row.link}")

    lines.extend([
        "",
        "[주의]",
        "수출 회복과 호르무즈·정제품·운임 정상화는 서로 다른 단계로 봅니다.",
    ])
    return "\n".join(lines).strip() + "\n"


def build_physical_flow_alert_body(
    kind: str,
    news_rows: list[NewsItem],
    oil: Quote | None,
    current: dt.datetime,
    fx: Quote | None = None,
) -> str:
    metrics = _extract_kpler_sts_metrics(news_rows)
    if kind == "eia_refining_crack_watch":
        return _build_eia_refining_alert_body(news_rows, oil, current, fx)
    if kind == "crude_product_divergence":
        return _build_crude_product_gap_alert_body(news_rows, oil, current, fx)
    if kind == "g7_reserve_release_agreement":
        return _build_g7_reserve_release_alert_body(news_rows, oil, current, fx)
    if kind == "eu_diesel_reserve_policy":
        return _build_eu_diesel_reserve_alert_body(news_rows, oil, current, fx)
    if kind == "us_diesel_export_policy":
        return _build_us_diesel_policy_alert_body(news_rows, oil, current, fx)
    if kind == "china_fuel_export_policy":
        return _build_china_fuel_export_policy_alert_body(news_rows, oil, current, fx)
    if kind == "hormuz_7day_diplomacy":
        return _build_hormuz_7day_alert_body(news_rows, oil, current, fx)
    if kind == "us_gulf_isaias_shutin":
        return _build_us_gulf_isaias_alert_body(news_rows, oil, current, fx)
    if kind == "saudi_asia_osp_change":
        return _build_saudi_osp_alert_body(news_rows, oil, current, fx)
    if kind == "ex_iran_crude_prewar_recovery":
        return _build_ex_iran_prewar_alert_body(news_rows, oil, current, fx)
    if kind == "oil_flow_recovery":
        return _build_oil_flow_compact_alert_body(news_rows, oil, current, fx)
    if kind == "east_west_pipeline_recovery":
        return _build_east_west_pipeline_alert_body(news_rows, oil, current, fx)
    if kind == "sts_reroute_expansion" and metrics:
        return _build_sts_compact_alert_body(news_rows, oil, current, fx, metrics)

    lines = [
        current.astimezone(KST).strftime("%Y년 %m월 %d일 %H:%M KST"),
        "",
        "[한눈에]",
    ]

    pipeline_rate, pipeline_yanbu = _extract_pipeline_rate(news_rows)
    pipeline_exports_resumed = _pipeline_exports_resumed(news_rows)
    regional = _extract_regional_export_metrics(news_rows)
    india_gulf = _extract_india_gulf_metrics(news_rows)

    if kind == "regional_export_recovery":
        current_mbd = regional.get("current_mbd")
        feb_mbd = regional.get("feb_mbd")
        hormuz_mbd = regional.get("hormuz_mbd")
        gap_mbd = regional.get("gap_mbd")
        recovery_pct = regional.get("recovery_pct")
        lines.append("중동 수출     전쟁 후 최고 수준")
        if current_mbd is not None:
            lines.append(f"핵심 수치     {current_mbd:.3f} Mbd · Reuters/Kpler")
        if hormuz_mbd is not None:
            lines.append(f"호르무즈      {hormuz_mbd:.3f} Mbd")
        if feb_mbd is not None and gap_mbd is not None:
            lines.append(f"비교          2월 {feb_mbd:.3f} Mbd보다 {gap_mbd:.3f} Mbd 낮음")
        if recovery_pct is not None:
            lines.append(f"회복률        2월 대비 {recovery_pct:.1f}%")
        lines.append("해석          잠정 선박추적치는 확인이 붙으며 수정될 수 있음")
    elif kind == "india_gulf_import_recovery":
        lines.append("인도 유입     걸프산 1.52 Mbd")
        lines.append("비교          6월 1.03 → 8월 1.18 → 9월 1.52 Mbd")
        lines.append("해석          아시아 실수요처까지 물량 회복이 연결되는지 확인")
    elif kind == "east_west_pipeline_recovery":
        if pipeline_rate is not None:
            lines.append(f"East-West     {pipeline_rate:.1f} Mbd")
            lines.append(f"vs 4Mbd      약 {pipeline_rate / 4.0 * 100:.0f}% 회복")
            lines.append(f"vs 7Mbd      명목 용량의 약 {pipeline_rate / 7.0 * 100:.0f}%")
        else:
            lines.append("East-West     재가동·유량 회복 확인")
        if pipeline_exports_resumed:
            lines.append("Yanbu 수출     재개 확인")
        elif pipeline_yanbu:
            lines.append("Yanbu         기사 내 직접 언급 · 선적 재개 여부 추가 확인")
        else:
            lines.append("Yanbu 수출     실제 선적 별도 확인 필요")
    elif kind == "sts_reroute_expansion" and metrics:
        lines.append("원유 공급     회복 ↑")
        lines.append("물류 효율     병목 심화 ↓")
        lines.append(
            f"GoO STS       {float(metrics['current_mbd']):.1f} Mbd · "
            f"전쟁 후 평균 {float(metrics['since_war_mbd']):.1f} · "
            f"2025 평균 {float(metrics['baseline_2025_mbd']):.2f}"
        )
        if metrics.get("vs_war_avg") is not None and metrics.get("vs_2025_avg") is not None:
            lines.append(
                f"현재 강도     전쟁 후 평균의 {float(metrics['vs_war_avg']):.1f}배 · "
                f"2025 평균의 {float(metrics['vs_2025_avg']):.0f}배"
            )
        if metrics.get("vlcc_low") is not None:
            lines.append(
                f"VLCC 수요     Saudi +{float(metrics['saudi_increment_mbd']):.0f} Mbd 처리 시 "
                f"+{int(metrics['vlcc_low'])}~{int(metrics['vlcc_high'])}척"
            )
        lines.append(f"기준일        {metrics['source_date']} · Kpler")
    else:
        lines.append(f"변화          {EVENT_LABELS[kind]}")

    if oil is not None:
        direction = "↓" if oil.change < 0 else "↑" if oil.change > 0 else "→"
        lines.append(
            f"Brent         USD {oil.price:.2f}/배럴 · {oil.change_pct:+.2f}% {direction}"
        )
    if fx is not None:
        won = "약세" if fx.change > 0 else "강세" if fx.change < 0 else "보합"
        lines.append(
            f"원·달러       {fx.price:,.2f}원 · {fx.change_pct:+.2f}% · 원화 {won}"
        )

    lines.extend(["", "[핵심 의미]"])
    if kind == "regional_export_recovery":
        current_mbd = regional.get("current_mbd")
        feb_mbd = regional.get("feb_mbd")
        gap_mbd = regional.get("gap_mbd")
        recovery_pct = regional.get("recovery_pct")
        lines.append("중동 주요 산유국의 원유 수출이 전쟁 이후 최고 수준으로 올라왔습니다.")
        if current_mbd is not None and feb_mbd is not None and gap_mbd is not None:
            lines.append(
                f"→ 최신 Reuters/Kpler 잠정치 {current_mbd:.3f} Mbd · "
                f"2월 {feb_mbd:.3f} Mbd보다 {gap_mbd:.3f} Mbd 낮습니다."
            )
        if recovery_pct is not None:
            lines.append(
                f"→ 현재 회복률은 2월 대비 {recovery_pct:.1f}%입니다. "
                "최근 14일 선박 데이터는 확인이 붙으며 상향 수정될 수 있습니다."
            )
        lines.append("→ 따라서 고정 숫자를 재사용하지 않고 매 실행 최신 잠정치를 다시 읽습니다.")
    elif kind == "india_gulf_import_recovery":
        lines.extend([
            "걸프산 원유가 인도 같은 최종 수요처까지 다시 도착하는 흐름이 강해지고 있습니다.",
            "→ 6월 1.03 → 8월 1.18 → 9월 1.52 Mbd로 회복했습니다.",
            "→ 다만 2025 평균 2.24 Mbd보다 낮아 완전 정상화는 아닙니다.",
        ])
    elif kind == "east_west_pipeline_recovery":
        lines.extend([
            "East-West Pipeline 유량 회복은 호르무즈를 우회하는 Red Sea 공급축이 되살아나는 신호입니다.",
            "→ 3.5Mbd가 확인되면 Reuters가 언급한 전쟁 전후 우회 운송 약 4Mbd의 약 88% 수준입니다.",
            (
                "→ Yanbu 해외 선적 재개가 확인돼 송유관 회복이 실제 수출로 연결되기 시작했습니다."
                if pipeline_exports_resumed
                else "→ 다만 송유관 내부 유량과 Yanbu 실제 선적은 다릅니다. 선적 재개 확인 전 수출 정상화로 단정하지 않습니다."
            ),
        ])
    elif kind == "oil_flow_recovery":
        lines.extend([
            "원유는 다시 시장에 나오고 있습니다.",
            "다만 호르무즈가 전쟁 이전처럼 정상화됐다는 뜻은 아닙니다.",
            "→ 공급량 회복은 유가 하방, 우회 물류 지속은 운임 상방 요인입니다.",
        ])
    else:
        lines.extend([
            "원유는 다시 나오지만 정상 항로 회복이 아니라 GoO STS 우회로 빼내는 중입니다.",
            "→ 유가에는 하방 압력, VLCC 운임·물류비에는 상방 압력이 동시에 생길 수 있습니다.",
            "→ '수출 회복'과 '물류 정상화'를 같은 의미로 보면 안 됩니다.",
        ])

    lines.extend(["", "[한국 전이]"])
    if oil is not None and fx is not None:
        if oil.change < 0 and fx.change <= 0:
            lines.append("유가 ↓ + 원화 강세/안정 → 수입물가·에너지 원가·금리 부담 완화 방향")
        elif oil.change < 0 and fx.change > 0:
            lines.append("유가 ↓ 하지만 원화 약세 → 국내 수입원가 완화 속도는 느려질 수 있음")
        elif oil.change > 0 and fx.change > 0:
            lines.append("유가 ↑ + 원화 약세 → 수입물가·금리·기업 원가 부담이 동시에 커지는 조합")
        else:
            lines.append("유가·환율 신호가 엇갈림 → 국내 실적 영향은 업종별로 갈릴 가능성")
    elif oil is not None:
        lines.append("유가 방향은 확인됐지만 원·달러 검증값이 없어 국내 환율 전이는 숫자 판정 보류")
    else:
        lines.append("유가·원·달러 동시 검증이 없어 국내 전이는 정성 판단만 유지")

    lines.extend([
        "실적 시즌    달러 매출 비중이 큰 수출기업은 원화 약세가 원화 환산 매출에 우호적일 수 있음",
        "원가 민감    항공·전력/가스·운송·석유화학 등은 유가·달러 동반 상승 시 비용 부담 확대",
        "금리 경로    고유가·원화 약세가 수입물가를 끌어올리면 한국은행의 완화 여지가 줄 수 있음",
        "다음 확인    원·달러 → 수입물가/CPI → 국고채 금리 → 3분기 실적 가이던스",
    ])

    lines.extend(["", "[병목]"])
    if kind == "regional_export_recovery":
        lines.extend([
            "1) 호르무즈 실제 통과량이 회복세를 유지하는지",
            "2) Ras Tanura·Yanbu 양쪽 선적이 동시에 유지되는지",
            "3) GoO STS 비용과 VLCC 운임이 낮아지는지",
            "4) 이란·후티 공격 재개로 우회망이 다시 흔들리는지",
        ])
    elif kind == "india_gulf_import_recovery":
        lines.extend([
            "1) 인도 도착 기준 1.52 Mbd가 월말까지 유지되는지",
            "2) Iraq·UAE·Kuwait·Saudi 물량 회복이 지속되는지",
            "3) STS·운임·보험 비용이 구매단가를 다시 끌어올리는지",
            "4) 러시아산 감소를 걸프산이 얼마나 대체하는지",
        ])
    elif kind == "east_west_pipeline_recovery":
        lines.extend([
            "1) 손상 펌핑스테이션 우회·복구 안정성",
            "2) Yanbu 저장탱크 재충전",
            "3) Yanbu 실제 탱커 선적 재개",
            "4) Red Sea·Bab el-Mandeb 통항 위험",
        ])
    elif kind == "sts_reroute_expansion":
        lines.extend([
            "1) Fujairah·Sohar 육상 지원능력 한계",
            "2) STS 작업 슬롯·예인선·파일럿·검사 처리능력",
            "3) VLCC 회전율 저하",
            "4) 한계 초과 시 서인도 → 말레이시아로 이송거리 확대",
            "Kpler 시나리오: 말레이시아까지 밀리면 최대 58척 수준의 VLCC가 필요할 수 있음",
        ])
    else:
        lines.extend([
            "1) 호르무즈 실제 통과량",
            "2) Ras Tanura 선적 지속 여부",
            "3) Yanbu·East-West Pipeline 복구 속도",
            "4) 보험·VLCC 운임",
        ])

    lines.extend(["", "[다음 체크]"])
    lines.extend([
        "호르무즈 실제 통과량",
        "Saudi Gulf / Red Sea 선적량",
        "GoO STS 7일 평균과 신규 최고치",
        "East-West Pipeline 유량 3.0 → 3.5 → 4.0 Mbd",
        "Yanbu 실제 선적 재개",
        "Fujairah·Sohar 병목",
        "VLCC 운임·가용선복",
        "Brent",
        "원·달러",
        "한국 수입물가·CPI·국고채 금리",
        "3분기 기업 실적 가이던스",
    ])

    lines.extend(["", "[근거]"])
    for row in news_rows[:3]:
        published = dt.datetime.fromtimestamp(row.published_epoch, tz=UTC).astimezone(KST)
        if "kpler" in normalize_text(row.source) and metrics:
            lines.append(
                f"Kpler · STS {float(metrics['current_mbd']):.1f} Mbd 기록 · "
                f"전쟁 후 평균 {float(metrics['since_war_mbd']):.1f} · "
                f"2025 평균 {float(metrics['baseline_2025_mbd']):.2f}"
            )
        else:
            lines.append(f"{_source_name_ko(row.source)} · {published:%m-%d %H:%M KST} · {_news_title_ko(row)}")
        if row.link:
            lines.append(f"원문: {row.link}")

    lines.extend(["", "[주의]"])
    lines.append("STS는 같은 배럴이 여러 번 이송될 수 있어 호르무즈 통과량·중동 전체 수출량과 합산하지 않습니다.")
    lines.append("정책 발언 처리: 대통령·정부 발언은 참고만 하고, 실물 물량·통항 데이터 없이 '정상화'로 판정하지 않습니다.")

    return "\n".join(lines).strip() + "\n"



def build_alert_body(
    kind: str,
    news_rows: list[NewsItem],
    us2y: Quote,
    dxy: Quote,
    oil: Quote | None,
    current: dt.datetime,
) -> str:
    lines = [
        current.astimezone(KST).strftime("%Y년 %m월 %d일 %H:%M KST"),
        "",
        f"확정 사건: {EVENT_LABELS[kind]}",
        "교차 확인:",
    ]
    for row in news_rows[:3]:
        published = dt.datetime.fromtimestamp(row.published_epoch, tz=UTC).astimezone(KST)
        lines.append(f"- {_source_name_ko(row.source)} · {published:%m-%d %H:%M KST} · {_news_title_ko(row)}")
    lines.extend(
        [
            "",
            "시장 확인:",
            fmt_quote_line(us2y),
            fmt_quote_line(dxy),
        ]
    )
    if oil is not None:
        lines.append(fmt_quote_line(oil))
    lines.extend(
        [
            "",
            "주식시장 의미:",
            "- 돈 버는 능력: 유가·운임 완화 시 항공·화학·운송 원가에는 우호적이고 정유·방산 위험프리미엄에는 역풍입니다.",
            "- 할인율: 미국 2년물과 달러가 함께 내려 성장주·고베타 자산의 할인율 부담이 낮아지는 방향입니다.",
            "- 수급: 지정학적 위험회피 포지션의 되돌림과 외국인 위험자산 재유입 가능성이 커집니다.",
            "- 시간표: 합의 이행, 공격 재개 여부, 선박 통행량의 지속성을 추가 확인해야 합니다.",
            "",
            "실패 경로: 합의 파기·공격 재개·통항 재차 차질 또는 2년물·달러 반등이 나타나면 완화 신호가 되돌려질 수 있습니다.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def write_summary(lines: list[str]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def create_test_alert(current: dt.datetime) -> None:
    TITLE_PATH.write_text("이란·호르무즈 시장 전환 Telegram 연결 시험\n", encoding="utf-8")
    BODY_PATH.write_text(
        current.astimezone(KST).strftime("%Y년 %m월 %d일 %H:%M KST")
        + "\n\n@hs8879887988798879_bot 연결 시험입니다. 실제 조건 알림이 아닙니다.\n",
        encoding="utf-8",
    )
    ALERT_JSON_PATH.write_text(
        json.dumps({"test_mode": True, "created_at_kst": current.astimezone(KST).isoformat()}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    write_summary(["# 이란·호르무즈 시장 전환 감시", "Telegram 연결 시험 메시지를 생성했습니다."])


def run_monitor(current: dt.datetime) -> int:
    clean_outputs()
    if os.getenv("TELEGRAM_TEST", "false").lower() == "true":
        create_test_alert(current)
        return 0

    state = load_state()
    news_items, news_errors = fetch_news(current)
    confirmed_candidates = confirm_events(news_items)
    if not confirmed_candidates:
        lines = [
            "# 이란·호르무즈 시장 전환 감시",
            current.astimezone(KST).strftime("확인 시각: %Y-%m-%d %H:%M KST"),
            f"신뢰 매체 후보 기사: {len(news_items)}건",
            "결과: 동일 사건을 확인한 신뢰 자료 2곳이 없어 알리지 않음",
        ]
        if news_errors:
            lines.append(f"조회 오류: {len(news_errors)}개 피드")
        write_summary(lines)
        return 0

    selected, duplicate_labels = select_unalerted_event(
        state, confirmed_candidates, current
    )

    if selected is None:
        write_summary(
            [
                "# 이란·호르무즈 시장 전환 감시",
                current.astimezone(KST).strftime("확인 시각: %Y-%m-%d %H:%M KST"),
                "결과: 확인된 사건은 모두 최근에 이미 알린 동일 단계여서 중복 발송하지 않음",
                *[f"- 중복: {label}" for label in duplicate_labels],
            ]
        )
        return 0

    kind, news_rows, current_event_id = selected

    market_errors: list[str] = []
    quotes: dict[str, Quote] = {}
    for key in ("us2y", "dxy", "wti", "brent", "usdkrw"):
        try:
            quotes[key] = fetch_quote(SYMBOLS[key])
        except Exception as exc:
            market_errors.append(f"{key}: {exc}")

    max_age_minutes = int(os.getenv("IRAN_HORMUZ_MARKET_MAX_AGE_MINUTES", "240"))

    physical_kinds = {
        "oil_flow_recovery",
        "sts_reroute_expansion",
        "ex_iran_crude_prewar_recovery",
        "saudi_asia_osp_change",
        "east_west_pipeline_recovery",
        "regional_export_recovery",
        "crude_product_divergence",
        "eia_refining_crack_watch",
        "g7_reserve_release_agreement",
        "eu_diesel_reserve_policy",
        "us_diesel_export_policy",
        "china_fuel_export_policy",
        "hormuz_7day_diplomacy",
        "us_gulf_isaias_shutin",
        "india_gulf_import_recovery",
    }
    if kind in physical_kinds:
        oil = None
        for key in ("brent", "wti"):
            candidate = quotes.get(key)
            if candidate is not None and quote_is_fresh(candidate, current, max_age_minutes):
                oil = candidate
                break
        fx = quotes.get("usdkrw")
        if fx is not None and not quote_is_fresh(fx, current, max_age_minutes):
            fx = None
        body = build_physical_flow_alert_body(kind, news_rows, oil, current, fx)
        if kind == "eia_refining_crack_watch":
            title = "미국 정제마진·정유사 이익 병목 변화"
        elif kind == "crude_product_divergence":
            title = "중동 원유 회복·정제품 병목 변화"
        elif kind == "g7_reserve_release_agreement":
            title = "G7 경유·원유 전략비축유 방출 합의"
        elif kind == "eu_diesel_reserve_policy":
            title = "EU 경유 전략비축유 방출 변화"
        elif kind == "us_diesel_export_policy":
            title = "미국 디젤 수출정책 변화"
        elif kind == "china_fuel_export_policy":
            title = "중국 정제품 수출정책 변화"
        elif kind == "hormuz_7day_diplomacy":
            title = "호르무즈 7일 이내 재개방 제안·미국 의견 검토"
        elif kind == "us_gulf_isaias_shutin":
            title = "미국 허리케인 원유생산 임시 중단 변화"
        elif kind == "oil_flow_recovery":
            title = "중동 원유 흐름 변화"
        elif kind == "ex_iran_crude_prewar_recovery":
            title = "걸프 원유 전쟁 전 수준 회복·우회 구조 변화"
        elif kind == "saudi_asia_osp_change":
            title = "사우디 아시아 원유 공식판매가격(OSP) 변화"
        elif kind == "east_west_pipeline_recovery":
            title = "사우디 East-West Pipeline 회복"
        else:
            title = "중동 원유 흐름 회복·우회 물류 변화"
        alert = {
            "test_mode": False,
            "created_at_kst": current.astimezone(KST).isoformat(timespec="seconds"),
            "event_kind": kind,
            "event_label": EVENT_LABELS[kind],
            "event_id": current_event_id,
            "news": [asdict(row) for row in news_rows],
            "market": {
                "oil": asdict(oil) if oil else None,
                "usdkrw": asdict(fx) if fx else None,
            },
        }
        pending_state = build_pending_state(
            state, current_event_id, kind, current, alert["market"]
        )
        TITLE_PATH.write_text(title + "\n", encoding="utf-8")
        BODY_PATH.write_text(body, encoding="utf-8")
        ALERT_JSON_PATH.write_text(json.dumps(alert, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        PENDING_STATE_PATH.write_text(json.dumps(pending_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_summary([
            "# 이란·호르무즈 시장 전환 감시",
            current.astimezone(KST).strftime("확인 시각: %Y-%m-%d %H:%M KST"),
            f"사건: {EVENT_LABELS[kind]}",
            "결과: 실물 원유 흐름 별도 Telegram 조건 충족",
        ])
        return 0

    us2y = quotes.get("us2y")
    dxy = quotes.get("dxy")
    if us2y is None or dxy is None:
        write_summary(
            [
                "# 이란·호르무즈 시장 전환 감시",
                current.astimezone(KST).strftime("확인 시각: %Y-%m-%d %H:%M KST"),
                f"사건: {EVENT_LABELS[kind]}",
                "결과: 미국 2년물 또는 달러인덱스 값을 확보하지 못해 알리지 않음",
                *market_errors,
            ]
        )
        return 0

    stale = [
        quote.label
        for quote in (us2y, dxy)
        if not quote_is_fresh(quote, current, max_age_minutes)
    ]
    if stale:
        write_summary(
            [
                "# 이란·호르무즈 시장 전환 감시",
                current.astimezone(KST).strftime("확인 시각: %Y-%m-%d %H:%M KST"),
                f"사건: {EVENT_LABELS[kind]}",
                f"결과: 시장 데이터가 오래됨({', '.join(stale)}) · 알리지 않음",
            ]
        )
        return 0

    if not market_confirms(us2y, dxy):
        write_summary(
            [
                "# 이란·호르무즈 시장 전환 감시",
                current.astimezone(KST).strftime("확인 시각: %Y-%m-%d %H:%M KST"),
                f"사건: {EVENT_LABELS[kind]}",
                fmt_quote_line(us2y),
                fmt_quote_line(dxy),
                "결과: 미국 2년물과 달러인덱스가 모두 전 거래일보다 낮지 않아 알리지 않음",
            ]
        )
        return 0

    oil = None
    for key in ("wti", "brent"):
        candidate = quotes.get(key)
        if candidate is not None and quote_is_fresh(candidate, current, max_age_minutes):
            oil = candidate
            break

    body = build_alert_body(kind, news_rows, us2y, dxy, oil, current)
    title = "이란·호르무즈 시장 전환 확인"
    alert = {
        "test_mode": False,
        "created_at_kst": current.astimezone(KST).isoformat(timespec="seconds"),
        "event_kind": kind,
        "event_label": EVENT_LABELS[kind],
        "event_id": current_event_id,
        "news": [asdict(row) for row in news_rows],
        "market": {
            "us2y": asdict(us2y),
            "dxy": asdict(dxy),
            "oil": asdict(oil) if oil else None,
        },
    }
    pending_state = build_pending_state(
        state, current_event_id, kind, current, alert["market"]
    )
    TITLE_PATH.write_text(title + "\n", encoding="utf-8")
    BODY_PATH.write_text(body, encoding="utf-8")
    ALERT_JSON_PATH.write_text(json.dumps(alert, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    PENDING_STATE_PATH.write_text(json.dumps(pending_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_summary(
        [
            "# 이란·호르무즈 시장 전환 감시",
            current.astimezone(KST).strftime("확인 시각: %Y-%m-%d %H:%M KST"),
            f"사건: {EVENT_LABELS[kind]}",
            fmt_quote_line(us2y),
            fmt_quote_line(dxy),
            "결과: Telegram 전송 조건 충족",
        ]
    )
    return 0


def finalize_state() -> int:
    if not PENDING_STATE_PATH.exists():
        return 0
    if not TELEGRAM_CONFIRMED_PATH.exists():
        print("Telegram 전송 확인 파일이 없어 상태를 반영하지 않습니다.")
        return 0
    try:
        confirmed = json.loads(TELEGRAM_CONFIRMED_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print("Telegram 전송 확인 파일 해석 실패")
        return 0
    if confirmed.get("status") != "confirmed":
        print("Telegram 전송이 확정되지 않아 상태를 반영하지 않습니다.")
        return 0
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(PENDING_STATE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"state_finalized=true message_id={confirmed.get('message_id')}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    if args.finalize:
        return finalize_state()
    return run_monitor(now_utc())


if __name__ == "__main__":
    raise SystemExit(main())
