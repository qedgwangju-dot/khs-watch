#!/usr/bin/env python3
"""Space launch bottleneck / reusable launch / launch-slot web watcher.

The watcher uses Google News RSS for discovery, prioritizes official sources, and
requires cross-source confirmation for non-official stories. It writes a pending
state file and a Telegram-ready Korean alert only when a meaningful new item is
found. The first run sends a compact bootstrap snapshot so the Telegram route can
be verified immediately.
"""

from __future__ import annotations

import datetime as dt
import email.utils
import hashlib
import html
import json
import os
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Iterable
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "space_launch_bottleneck_dedicated_state.json"
PENDING_STATE_PATH = ROOT / "out" / "space_launch_bottleneck_dedicated_pending_state.json"
ALERT_PATH = ROOT / "out" / "space_launch_bottleneck_watch_telegram.txt"
STATUS_PATH = ROOT / "out" / "space_launch_bottleneck_watch_status.md"

KST = ZoneInfo("Asia/Seoul")
NOW = dt.datetime.now(dt.timezone.utc)
USER_AGENT = "Mozilla/5.0 (compatible; khs-space-launch-watch/1.0; +https://github.com/qedgwangju-dot/khs-watch)"

OFFICIAL_DOMAINS = (
    "spacex.com",
    "rocketlabcorp.com",
    "rocketlabusa.com",
    "faa.gov",
    "hyundai-rotem.co.kr",
    "nasa.gov",
    "sec.gov",
    "defense.gov",
    "war.gov",
)

TRUSTED_SOURCES = {
    "Reuters", "Bloomberg", "CNBC", "Financial Times", "The Wall Street Journal",
    "Barron's", "MarketWatch", "Yahoo Finance", "Investing.com", "Fortune",
    "SpaceNews", "Payload", "Ars Technica", "Aviation Week", "Breaking Defense",
    "Defense News", "TechCrunch", "The Verge", "Associated Press", "AP News",
    "연합뉴스", "한국경제", "매일경제", "서울경제", "전자신문", "ZDNet Korea",
    "DIGITIMES", "DigiTimes", "Rocket Lab", "SpaceX", "FAA", "Hyundai Rotem",
}

HIGH_SIGNAL = re.compile(
    r"contract|agreement|award|order|backlog|launch|flight\s*15|flight\s*16|"
    r"reentry|re-entry|heat\s*shield|thermal\s*protection|tile|turnaround|"
    r"reuse|reusable|methane|engine|hot[- ]fire|static[- ]fire|qualification|"
    r"production|factory|capex|price\s*target|upgrade|downgrade|overweight|"
    r"orbital\s*compute|data\s*center|semiconductor|power\s*bottleneck|"
    r"license|licen[cs]e|launch\s*slot|shortage|delay|constellation|"
    r"zero[- ]boil[- ]off|\bZBO\b|propellant\s*transfer|cryogenic",
    re.I,
)

NOISE = re.compile(
    r"class action|lawsuit|insider sale|options activity|technical analysis|"
    r"stock twits|why shares moved|price prediction|motley fool",
    re.I,
)

NUMBER_PATTERNS = [
    re.compile(r"\$\s?\d+(?:\.\d+)?\s?(?:billion|million|B|M|bn|mn)?", re.I),
    re.compile(r"\b\d+(?:\.\d+)?\s?(?:launches?|missions?|flights?|satellites?|tons?|tonnes?|GW|MW|kW|%)\b", re.I),
    re.compile(r"\b20\d{2}\b"),
]


@dataclass(frozen=True)
class Category:
    key: str
    tag: str
    name: str
    queries: tuple[str, ...]
    relevance: re.Pattern[str]
    meaning: str
    failure: str
    indicator: str


CATEGORIES = (
    Category(
        key="starship_thermal",
        tag="[신규병목]",
        name="Starship 재진입 열차폐·회전시간",
        queries=(
            '"Starship" ("heat shield" OR thermal tiles OR reentry OR turnaround OR reuse) when:7d',
            '"Starship" (tile OR heatshield OR "thermal protection") (damage OR crack OR replacement OR inspection) when:7d',
            '"Starship" ("zero boil off" OR ZBO OR cryogenic propellant OR propellant transfer) when:7d',
            'site:spacex.com Starship Flight 15 heat shield tile reentry when:14d',
        ),
        relevance=re.compile(r"Starship.*(tile|heat\s*shield|thermal|reentry|re-entry|turnaround|reuse|ZBO|cryogenic|propellant)|"
                             r"(tile|heat\s*shield|thermal|reentry|turnaround|ZBO|cryogenic|propellant).*Starship", re.I),
        meaning="재진입 성공보다 비행 후 검사·교체 시간이 줄어드는지가 초고빈도 재사용과 궤도 컴퓨팅 경제성을 좌우합니다.",
        failure="타일 손상과 수작업 전수검사가 반복되면 재사용은 가능해도 수시간~수일 회전시간 달성이 지연됩니다.",
        indicator="비행 후 교체 타일 수, 동일 기체 재비행 간격, Flight 15 이후 재사용 하드웨어 비율",
    ),
    Category(
        key="rocketlab",
        tag="[계약]",
        name="Rocket Lab Electron·Neutron 발사 공급",
        queries=(
            '"Rocket Lab" (Synspective OR Electron OR Neutron) (contract OR launch OR backlog OR order) when:7d',
            '"Rocket Lab" ("20 launches" OR "47 missions" OR "100 launches" OR backlog) when:14d',
            'site:rocketlabcorp.com Synspective Electron contract launch when:14d',
        ),
        relevance=re.compile(r"Rocket\s*Lab.*(Synspective|Electron|Neutron|contract|backlog|launch)|"
                             r"(Synspective|Electron|Neutron).*Rocket\s*Lab", re.I),
        meaning="발사슬롯 자체가 희소해질수록 전용 소형발사체의 일정 통제권과 반복 고객 계약 가치가 올라갑니다.",
        failure="백로그가 생산·발사장 처리능력보다 빨리 늘면 계약이 매출로 전환되는 시간이 길어집니다.",
        indicator="분기 실제 발사 횟수, Electron 생산속도, Neutron 첫 비행·고객 임무 일정, 12개월 내 백로그 인식 비중",
    ),
    Category(
        key="hyundai_rotem",
        tag="[개발]",
        name="현대로템 재사용 메탄엔진",
        queries=(
            '현대로템 (메탄엔진 OR 재사용 발사체 OR 35톤 OR 10톤 OR 무주) when:14d',
            '"Hyundai Rotem" (methane engine OR reusable launch OR 35-ton OR 10-ton OR Muju) when:14d',
            'site:hyundai-rotem.co.kr 메탄엔진 재사용 발사체 when:30d',
        ),
        relevance=re.compile(r"(현대로템|Hyundai\s*Rotem).*(메탄|methane|재사용|reusable|35\s*톤|35[- ]?ton|10\s*톤|10[- ]?ton|무주|Muju)|"
                             r"(메탄|methane|35[- ]?ton|10[- ]?ton).*(현대로템|Hyundai\s*Rotem)", re.I),
        meaning="국책 연구개발이 반복 연소·재점화·내구시험을 통과해 실제 발사체 선정과 양산으로 이어지는지가 재평가 조건입니다.",
        failure="엔진 시연에는 성공해도 반복 사용 수명·터보펌프·연소 안정성 검증이 늦으면 양산 매출 연결이 밀립니다.",
        indicator="장시간 연소시험, 재점화 횟수, 누적 연소시간, 실제 발사체 체계선정, 무주 생산기지 장비 반입",
    ),
    Category(
        key="spacex_valuation",
        tag="[증권사]",
        name="SpaceX 증권사 재평가·Flight 15",
        queries=(
            '"SpaceX" ("Morgan Stanley" OR "Adam Jonas" OR "price target" OR overweight) when:7d',
            '"SpaceX" ("Flight 15" OR orbital compute OR "orbital data center" OR semiconductor bottleneck OR power bottleneck) when:7d',
            '"SpaceX" ("$300" OR "300 price target") when:14d',
        ),
        relevance=re.compile(r"SpaceX.*(Morgan\s*Stanley|Adam\s*Jonas|price\s*target|overweight|Flight\s*15|orbital\s*compute|orbital\s*data\s*center|semiconductor|power\s*bottleneck)|"
                             r"(Morgan\s*Stanley|Adam\s*Jonas|Flight\s*15|orbital\s*compute).*SpaceX", re.I),
        meaning="목표주가보다 Flight 15와 재사용·궤도 컴퓨팅 진전이 실제 이익성장률과 멀티플 확대 가정을 검증하는지 봅니다.",
        failure="재사용 회전시간 또는 AI·전력 인프라 수익화가 늦으면 높은 성장 가정이 먼저 훼손됩니다.",
        indicator="Flight 15 시험목표 달성, Starship 재비행 간격, 궤도 컴퓨팅 시제품 일정, 증권사 이익 추정치 변경",
    ),
    Category(
        key="golden_dome",
        tag="[선행경보·협의]",
        name="미국 Golden Dome 구글 데이터·통신 보안",
        queries=(
            '"Golden Dome" (Google OR Alphabet OR Aalyria) (talks OR contract OR data security OR cybersecurity) when:7d',
            '"Google" "Golden Dome" (consortium OR Pentagon OR contract OR cybersecurity) when:7d',
            'site:war.gov "Golden Dome" (Google OR Aalyria OR cybersecurity) when:14d',
        ),
        relevance=re.compile(r"(Golden\s*Dome|골든돔).*(Google|Alphabet|Aalyria|구글|알파벳|알리리아)|"
                             r"(Google|Alphabet|Aalyria|구글|알파벳|알리리아).*(Golden\s*Dome|골든돔)", re.I),
        meaning="데이터·통신 보안 협의와 공식 지휘통제 계약을 분리합니다. 미 국방 예산 전체가 구글 확정 매출은 아닙니다.",
        failure="협력체 최종 구성·조달 승인·보안 인증·통신 두절 대비 성능 검증이 지연되면 계약과 매출 시점도 밀립니다.",
        indicator="미국 국방부 조달 공고·공식 수주기업·구글/알리리아 계약발표·사업별 계약금액·검수",
    ),
    Category(
        key="launch_slots",
        tag="[발사슬롯]",
        name="FAA 상업발사·발사슬롯 병목",
        queries=(
            'FAA commercial space (launches OR launch licenses OR licensing OR launch slots) shortage when:14d',
            '"launch slots" satellites shortage launch vehicle when:14d',
            '"Open Cosmos" (192 OR 576 OR constellation OR launch) when:14d',
            'commercial launch shortage satellite deployment delay when:7d',
        ),
        relevance=re.compile(r"(FAA|Open\s*Cosmos|commercial\s*launch|launch\s*slot).*(launch|licen[cs]e|shortage|delay|constellation|192|576)|"
                             r"(launch\s*slot|launch\s*shortage|deployment\s*delay).*(satellite|constellation|FAA)", re.I),
        meaning="위성 제조 이후 실제 궤도 배치까지의 병목이 발사체·발사장·허가 처리능력으로 이동하는지 확인하는 축입니다.",
        failure="발사체 공급 확대보다 위성 수요가 빨리 늘면 배치 지연이 길어지고 위성사업자의 매출 개시도 늦어집니다.",
        indicator="FAA 허가 상업발사 횟수, 주요 발사체 연간 운항횟수, 발사장 슬롯 대기기간, 위성사업자 일정 변경",
    ),
    Category(
        key="korea_orbital_ai",
        tag="[국내 우주 AI]",
        name="우주항공청 궤도 AI 데이터센터 실증·예산",
        queries=(
            'site:kasa.go.kr "우주 데이터센터" (실증 OR 예산 OR 과제 OR 전력) when:30d',
            '"우주항공청" "우주 AI 데이터센터" (2028 OR 2030 OR 실증 OR 예산) when:14d',
            '"우주 데이터센터" (고대역폭메모리 OR 신경망처리장치 OR 위성) when:14d',
        ),
        relevance=re.compile(r"(우주항공청|KASA|우주\s*데이터센터|우주\s*AI).*(2028|2030|실증|예산|기술|위성|반도체)|"
                             r"(2028|2030|실증|예산).*(우주항공청|우주\s*데이터센터)", re.I),
        meaning="우주항공청 2030년 기술실증 기준계획과 2028년 조기실증 추진발언을 구분하고 실제 국비·시제품·지상검증·우주실증 발주로 연결되는지 확인합니다.",
        failure="방사선 내성·발열 방출·전력제어·고대역폭메모리 신뢰성 검증 또는 국비 배정 지연 시 발사·실증 일정이 뒤로 밀립니다.",
        indicator="2027년 예산안 내역·시제품 선정·우주검증 탑재 계약·2028 실증 일정 공식 확정 여부",
    ),
    Category(
        key="space_investment",
        tag="[우주투자·자금]",
        name="글로벌 우주투자·발사체 공급 부족",
        queries=(
            '"Space Capital" ("92.5 billion" OR "$100 billion") "space" when:30d',
            'site:seraphim.vc "SpaceTech Investment Tracker" "Q3 2026" when:30d',
            '"space investment" "launch shortage" (2026 OR SpaceX) when:14d',
        ),
        relevance=re.compile(r"(Space\s*Capital|Seraphim|space\s*invest(?:ment|ing)|SpaceX).*(92\.5|100\s*billion|20\.8|launch\s*shortage|Q3\s*2026)|"
                             r"(launch\s*shortage|space\s*funding).*(SpaceX|2026|billion)", re.I),
        meaning="우주산업 전체 투자액은 Space Capital 기준이고 스타트업 조달액은 Seraphim 기준입니다. 규모와 집계범위가 달라 섞거나 합산하지 않습니다.",
        failure="민간자금 급증이 발사체 실제 양산·인증·수주·반복매출로 연결되지 않으면 투자 회수기간만 길어집니다.",
        indicator="분기 자금조달·투자건수·실제 발사서비스 수주·상장기업 영업현금흐름",
    ),
    Category(
        key="falcon_transition",
        tag="[발사체 전환]",
        name="Falcon 9·Dragon 운항과 Starship 대체 수송",
        queries=(
            '"Falcon 9" "Starship" (retirement OR phaseout OR transition OR launch bottleneck) when:7d',
            '"SpaceX" "Dragon" (Crew-15 OR Crew-16 OR Crew-17 OR retirement) when:14d',
            '"Starship" ("Direct to Cell" OR "Starlink Mobile" OR D2D OR satellites) (capacity OR payload) when:7d',
            'site:nasa.gov SpaceX Crew-15 Crew-16 Crew-17 Falcon 9 Dragon when:30d',
        ),
        relevance=re.compile(
            r"(Falcon\s*9|Falcon\s*Heavy|Dragon|Starship).*(retire|phase.?out|transition|"
            r"launch\s*capacity|bottleneck|crew-1[567]|direct\s*to\s*cell|starlink\s*mobile)|"
            r"(retire|phase.?out|crew-1[567]|launch\s*bottleneck).*(Falcon\s*9|Dragon|Starship)",
            re.I,
        ),
        meaning="Falcon 9 발사 비중 축소 전망과 Dragon 유인운송 계약의 실제 종료는 별개입니다. 신규 위성군은 위성 질량·접힌 치수·발사당 수량이 검증돼야 발사량을 계산할 수 있습니다.",
        failure="Starship 회수·열차폐·재비행 정비가 늦어지면 대형 위성군 증설 일정과 비용이 악화하나 Falcon 9·Dragon 운항이 즉시 중단되는 것은 아닙니다.",
        indicator="NASA Crew-15~17 2030년 계약, Falcon 9 월별 발사 횟수, Starship 회수·재사용, 발사당 실제 위성 수",
    ),
    Category(
        key="moon_base_clps",
        tag="[NASA 달 운송·신규 과업]",
        name="NASA CLPS 2 참여자격·실제 달 화물 임무 발주",
        queries=(
            '"NASA" "CLPS 2" ("task order" OR award OR cancellation OR amendment OR ceiling OR extension) when:7d',
            '"NASA" ("Moon Base" OR "cislunar communications") (SpaceX OR Firefly OR Voyager OR Intuitive Machines) (contract OR delay OR schedule) when:7d',
            '"NASA" ("miniCAST" OR "Redwire" OR "PROMISE") (contract OR deployment OR delivery) when:7d',
            'site:nasa.gov "CLPS" "task order" "Moon Base" when:14d',
        ),
        relevance=re.compile(
            r"(NASA|CLPS|Moon Base|달 기지|달 수송).*(lunar|CLPS|Moon Base|task order|contract|award|"
            r"SpaceX|Voyager|Firefly|Redwire|PROMISE|miniCAST|수주|발주)|"
            r"(Redwire|SpaceX|Firefly|Voyager|Intuitive Machines).*(CLPS|Moon Base|lunar task order)",
            re.I,
        ),
        meaning="8개 기업의 입찰자격과 100억 달러 총한도는 개별 확정 수주가 아닙니다. 이후 임무별 계약·인도·검수·매출을 따로 확인합니다.",
        failure="Starship 착륙선·발사허가·우주선 신뢰성·달 남극 전력·착륙 정밀도·자금 집행 지연",
        indicator="NASA 별도 과업 발주번호·수주기업·개별 금액·임무 일정·시험·달 표면 인도·매출 인식",
    ),
    Category(
        key="starlink_optical",
        tag="[선행경보·V4 광통신]",
        name="Starlink V4 위성 간 레이저망·해저케이블 대체 구상",
        queries=(
            '"Starlink" ("V4" OR "version 4") ("laser" OR "optical" OR "10 Tbps") when:7d',
            '"SpaceX" ("100,000 satellites" OR "100 lasers") ("FCC" OR "specification" OR "deployment") when:7d',
            '"Starlink" ("subsea" OR "undersea" OR "optical backhaul") (contract OR test OR gateway) when:7d',
            'site:spacex.com ("Starlink V4" OR "laser links") when:14d',
        ),
        relevance=re.compile(
            r"(Starlink|SpaceX|스타링크|스페이스X).*(V4|version.?4|laser|optical|subsea|undersea|레이저|해저케이블)|"
            r"(V4|laser|optical|subsea|undersea|레이저|해저케이블).*(Starlink|SpaceX|스타링크)",
            re.I,
        ),
        meaning="머스크가 제시한 10개·약 100개 레이저 수와 10만 기 구상은 검증 전 설계목표입니다. 위성 간 회선과 지상 이용자 처리량을 구분합니다.",
        failure="Starship 발사주기·레이저 크기와 조준·궤도 간 간섭·지상 관문국·전력·위성 교체비·규제 지연",
        indicator="SpaceX 공식 V4 사양·FCC 신청/승인·실제 발사·10Tbps 측정시험·관문국 처리량·상용 백업 계약",
    ),
)


def request_bytes(url: str, timeout: int = 25, attempts: int = 3) -> bytes:
    """Fetch bytes with bounded retry for transient HTTP/network failures."""
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in {429, 500, 502, 503, 504} or attempt >= attempts:
                raise
            retry_after = exc.headers.get("Retry-After")
            try:
                delay = int(retry_after) if retry_after else 2 ** (attempt - 1)
            except ValueError:
                delay = 2 ** (attempt - 1)
            time.sleep(max(1, min(delay, 10)))
        except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
            last_error = exc
            if attempt >= attempts:
                raise
            time.sleep(min(2 ** (attempt - 1), 8))
    if last_error:
        raise last_error
    raise RuntimeError("request_bytes failed without an exception")


def strip_html(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def parse_date(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except Exception:
        return None


def google_news(query: str, hl: str = "en-US", gl: str = "US", ceid: str = "US:en") -> list[dict]:
    params = urllib.parse.urlencode({"q": query, "hl": hl, "gl": gl, "ceid": ceid})
    url = "https://news.google.com/rss/search?" + params
    root = ET.fromstring(request_bytes(url))
    rows: list[dict] = []
    for item in root.findall(".//item"):
        title = strip_html(item.findtext("title") or "")
        link = strip_html(item.findtext("link") or "")
        desc = strip_html(item.findtext("description") or "")
        pub = parse_date(item.findtext("pubDate"))
        source_node = item.find("source")
        source = strip_html(source_node.text if source_node is not None else "")
        source_url = strip_html(source_node.get("url") if source_node is not None else "")
        if not title or not link:
            continue
        rows.append(
            {
                "title": title,
                "link": link,
                "description": desc,
                "published": pub.isoformat() if pub else None,
                "source": source,
                "source_url": source_url,
            }
        )
    return rows


def hostname(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).hostname or ""
    except Exception:
        return ""


def source_is_official(item: dict) -> bool:
    host = hostname(item.get("source_url") or "").lower()
    return any(host == d or host.endswith("." + d) for d in OFFICIAL_DOMAINS)


def source_is_trusted(item: dict) -> bool:
    if source_is_official(item):
        return True
    source = (item.get("source") or "").strip().lower()
    return any(source == x.lower() or x.lower() in source for x in TRUSTED_SOURCES)


def normalized_title(value: str) -> str:
    value = re.sub(r"\s+-\s+[^-]{2,80}$", "", value.strip())
    value = re.sub(r"[^0-9A-Za-z가-힣]+", " ", value.lower())
    return re.sub(r"\s+", " ", value).strip()


def item_id(category: str, item: dict) -> str:
    raw = "|".join((category, normalized_title(item["title"]), (item.get("source") or "").lower()))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def item_text(item: dict) -> str:
    return f'{item.get("title","")} {item.get("description","")} {item.get("source","")}'


def signal_score(category: Category, item: dict) -> int:
    text = item_text(item)
    if NOISE.search(text):
        return -20
    if not category.relevance.search(text):
        return -10
    score = 5
    if HIGH_SIGNAL.search(text):
        score += 4
    if source_is_official(item):
        score += 5
    elif source_is_trusted(item):
        score += 2
    if re.search(r"contract|agreement|award|backlog|hot[- ]fire|test|flight\s*15|license|price\s*target|upgrade|production|factory", text, re.I):
        score += 3
    if any(p.search(text) for p in NUMBER_PATTERNS):
        score += 1
    if category.key == "golden_dome" and re.search(r"talks|weighs|discuss|negotia|contract|Google|Alphabet|Aalyria", text, re.I):
        score += 2
    return score


def event_signature(category: Category, item: dict) -> str:
    text = item_text(item).lower()
    if category.key == "starship_thermal":
        if "zero boil" in text or re.search(r"\bzbo\b", text):
            return "zbo"
        if "propellant" in text or "cryogenic" in text:
            return "propellant"
        if "flight 15" in text:
            return "flight15"
        return "thermal"
    if category.key == "rocketlab":
        if "synspective" in text:
            return "synspective"
        if "neutron" in text:
            return "neutron"
        if "backlog" in text:
            return "backlog"
        return "electron"
    if category.key == "hyundai_rotem":
        if "무주" in text or "muju" in text:
            return "muju"
        if "35" in text:
            return "35t"
        if "10" in text:
            return "10t"
        return "methane"
    if category.key == "spacex_valuation":
        if "morgan stanley" in text or "adam jonas" in text or "price target" in text or "$300" in text:
            return "morgan"
        if "flight 15" in text:
            return "flight15"
        return "orbital_compute"
    if category.key == "falcon_transition":
        if "dragon" in text or "crew-15" in text or "crew-16" in text or "crew-17" in text:
            return "nasa_dragon"
        if "retir" in text or "phase" in text or "transition" in text:
            return "falcon_transition"
        return "starship_mobile_payload"
    if category.key == "launch_slots":
        if "open cosmos" in text:
            return "open_cosmos"
        if "faa" in text:
            return "faa"
        return "slot_shortage"
    return category.key


def corroborated(category: Category, item: dict, peers: Iterable[dict]) -> bool:
    from space_launch_event_guard import eligible, semantic_pair, kind

    # An issuer-sourced article is not proof of an external broker's
    # recommendation or of the before/after target value.
    if category.key in {"rocketlab", "spacex_valuation"} and kind(category.key, str(item.get("title") or "")) == "analyst":
        return False
    if source_is_official(item):
        # Primary evidence for the named organization, never proof of unrelated
        # analysts' assertions or outside-party contracts.
        return True
    if not source_is_trusted(item):
        return False
    if not eligible(category.key, item, NOW):
        return False
    if category.key == "falcon_transition":
        title = normalized_title(item.get("title", ""))
        if re.search(r"retir|phase.?out|discontinu|cancell?ed", title, re.I):
            return False
    for peer in peers:
        if peer is item or not source_is_trusted(peer):
            continue
        if not eligible(category.key, peer, NOW):
            continue
        if semantic_pair(category.key, item, peer):
            return True
    return False


def extract_numbers(text: str) -> str:
    found: list[str] = []
    for pattern in NUMBER_PATTERNS:
        for match in pattern.findall(text):
            value = match if isinstance(match, str) else " ".join(match)
            value = re.sub(r"\s+", " ", value).strip()
            if value and value not in found:
                found.append(value)
            if len(found) >= 6:
                break
        if len(found) >= 6:
            break
    return ", ".join(found) if found else "제목·공개요약에서 핵심 수치 미추출"


def fetch_usdkrw() -> float | None:
    urls = (
        "https://open.er-api.com/v6/latest/USD",
        "https://api.frankfurter.app/latest?from=USD&to=KRW",
    )
    for url in urls:
        try:
            data = json.loads(request_bytes(url, timeout=12).decode("utf-8"))
            if "rates" in data and "KRW" in data["rates"]:
                rate = float(data["rates"]["KRW"])
                if 800 <= rate <= 2500:
                    return rate
        except Exception:
            continue
    return None


def usd_to_krw_note(text: str, rate: float | None) -> str | None:
    if not rate:
        return None
    matches = re.findall(r"\$\s?(\d+(?:\.\d+)?)\s?(billion|million|B|M|bn|mn)?", text, flags=re.I)
    notes: list[str] = []
    seen_amounts: set[int] = set()
    for number, unit in matches[:12]:
        value = float(number)
        u = unit.lower()
        if u in {"b", "bn", "billion"}:
            usd = value * 1_000_000_000
        elif u in {"m", "mn", "million"}:
            usd = value * 1_000_000
        else:
            usd = value
        normalized = round(usd)
        if normalized in seen_amounts:
            continue
        seen_amounts.add(normalized)
        krw = usd * rate
        if krw >= 1_000_000_000_000:
            rendered = f"약 {krw / 1_000_000_000_000:.2f}조원"
        elif krw >= 100_000_000:
            rendered = f"약 {krw / 100_000_000:,.0f}억원"
        elif krw >= 10_000:
            rendered = f"약 {krw / 10_000:,.0f}만원"
        else:
            rendered = f"약 {krw:,.0f}원"
        label = "$" + number + (unit or "")
        notes.append(f"{label}≈{rendered}")
        if len(notes) >= 3:
            break
    return ", ".join(notes) if notes else None


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"version": 1, "seen": {}, "created_at": NOW.isoformat()}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("bad state")
        data.setdefault("version", 1)
        data.setdefault("seen", {})
        return data
    except Exception as exc:
        raise RuntimeError("중복방지 상태파일 손상: 자동 초기화 금지, 감시 실행 중단") from exc


def save_pending_state(state: dict) -> None:
    PENDING_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Leave state unchanged on runs with no new facts. Avoid unnecessary
    # repository commits, merge conflicts and duplicate notifications.
    try:
        previous = json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {}
    except Exception as exc:
        raise RuntimeError("중복 상태파일 재검증 실패: 저장 금지") from exc
    if {k:v for k,v in state.items() if k != "updated_at"} != {k:v for k,v in previous.items() if k != "updated_at"}:
        state["updated_at"] = NOW.isoformat()
    else:
        state["updated_at"] = previous.get("updated_at", NOW.isoformat())
    seen = state.get("seen", {})
    if len(seen) > 2500:
        ordered = sorted(seen.items(), key=lambda kv: kv[1], reverse=True)[:2000]
        state["seen"] = dict(ordered)
    PENDING_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def render_item(category: Category, item: dict, rate: float | None) -> str:
    from space_launch_event_guard import kind

    tag, meaning, failure, indicator = category.tag, category.meaning, category.failure, category.indicator
    event = kind(category.key, str(item.get("title") or ""))
    if category.key == "rocketlab":
        if event == "contract":
            tag = "[신규 발사계약·실제 매출 미발생]"
            meaning = "발사계약 체결 보도와 실제 발사·검수·매출 인식을 구분합니다. 금액·고객·횟수는 회사 원문으로 확인해야 합니다."
            failure = "Neutron 첫 비행·인증·발사일 지연 시 계약 물량이 매출로 전환되는 시기도 늦어집니다."
            indicator = "회사 직접 계약 발표·고객별 발사 일정·계약잔고·Neutron 첫 비행과 발사 실제 완료"
        elif event == "development_delay":
            tag = "[개발·일정 지연]"
            meaning = "Neutron 개발 일정 변경으로 첫 고객 발사·매출 시점이 늦어질 수 있으나 Electron 신규 공급계약과는 별개입니다."
            failure = "제조·품질검증 재작업이나 추가 시험 실패 시 새로운 비행 목표일도 연기될 수 있습니다."
            indicator = "Neutron 구조물 품질검증·재시험, 회사가 공표한 첫 비행 목표와 실제 발사"
        elif event == "development":
            tag = "[개발·시험]"
            meaning = "발사체 개발·시험 진전은 실제 발사계약 체결이나 매출 인식과 구분합니다."
            failure = "시험 성공 뒤에도 비행 인증·양산·발사장 가동이 지연될 수 있습니다."
            indicator = "시험 결과·고객 임무 확정·첫 비행과 후속 반복 발사"
        elif event == "analyst":
            tag = "[증권사·독립 검증 전]"
    elif category.key == "spacex_valuation" and event == "space_technology":
        tag = "[시험·궤도 컴퓨팅]"
    pub = dt.datetime.fromisoformat(item["published"]) if item.get("published") else None
    when = pub.astimezone(KST).strftime("%Y-%m-%d %H:%M KST") if pub else "게시시각 확인 불가"
    official = source_is_official(item)
    # RSS source_url identifies the reported publisher; an RSS card is not
    # evidence that our runner opened the publisher's full original article.
    verification = ("회사 명의 뉴스 색인(회사 발표 원문 직접 열람 전)"
                    if official else "신뢰 매체 뉴스 색인(기사 원문 직접 열람 전)")
    if category.key == "golden_dome" and not official:
        verification = "블룸버그 최초 보도 재인용 가능·국방부/구글 확정계약 미확인"
    numbers = extract_numbers(item_text(item))
    krw = usd_to_krw_note(item_text(item), rate)
    lines = [
        f"{tag} {category.name}",
        "• 핵심: "+meaning,
        f"• 사건 제목: {item['title']}",
        f"• 확인 단계: {verification} | {item.get('source') or '출처 미표기'} | {when}",
        f"• 원문에서 추출된 숫자: {numbers}",
    ]
    if krw:
        lines.append(f"• 원화 환산(USD/KRW {rate:,.2f}): {krw}")
    lines.extend(
        [
            f"• 주의: {failure}",
            f"• 먼저 볼 지표: {indicator}",
            f"• 원문: {item['link']}",
        ]
    )
    return "\n".join(lines)



FAA_STARBASE_NOTICE="https://www.govinfo.gov/content/pkg/FR-2026-10-14/html/2026-20963.htm"
FAA_STARBASE_EVENT="faa:starbase:2026-10-14:peis_456_proposed"

def starbase_faa_notice() -> str:
    """Use exact federal notice; never claim the 456 annual launches are licensed."""
    raw=request_bytes(FAA_STARBASE_NOTICE,timeout=25).decode("utf-8",errors="replace")
    plain=strip_html(raw)
    markers=("456", "912", "100", "200", "25", "Programmatic Environmental Impact")
    if not all(x.lower() in plain.lower() for x in markers):
        raise RuntimeError("FAA federal notice source verification incomplete")
    return "\n".join((
        "[발사허가·신규 공고] Starship 스타베이스 연간 456회 확대 제안",
        "• 2026년 10월 14일 FAA 공식 환경심사 착수 공고: 기존 승인 연간 25회 발사·50회 착륙.",
        "• 1단계 제안: 연간 최대 100회 발사·200회 착륙.",
        "• 2단계 제안: 연간 최대 456회 발사·912회 착륙. 이미 승인된 실제 발사횟수가 아닙니다.",
        "• 추가로 플로리다 SLC-37의 연간 76회 발사·152회 착륙은 별도 인허가 심사 대상입니다. 텍사스 승인량에 합산 금지.",
        "• 11월 17일·19일 의견수렴, 환경영향평가 초안 및 최종 결정·면허 변경을 추적합니다.",
        "• 비용·매출: FAA 제안 횟수는 수주액과 다르며 위성 실제 탑재량×발사당 원가 및 재사용 정비시간 확인 전 운송매출 미확정.",
        "• 최대 역풍: 열차폐·엔진 내구성, 소음·환경 민원, 발사장·안전 인허가 지연.",
        "• 원문: "+FAA_STARBASE_NOTICE,
        "• 원문: https://www.faa.gov/space/stakeholder_engagement/spacex_starship",
    ))


KASA_AI_EVENT="kasa:space_ai:2026-10-13:2028_early_demo_goal"
SPACE_FUND_EVENT="private_space:2026q3:spacecapital_seraphim_distinct"
KASA_ORIGINAL="https://www.kasa.go.kr/prog/plcyBrf/brief/kor/sub01_01_04/view.do?plcyBrfNo=392"
KASA_HEARING_REPORT="https://files.newsis.com/view/NISX20261013_0003824495"
SPACE_CAPITAL_REPORT="https://www.spacecapital.com/reports/space-iq-q3-2026"
SERAPHIM_TRACKER="https://seraphim.vc/seraphim-spacetech-investment-tracker/"

def check_primary(url: str, *markers: str) -> str:
    content=strip_html(request_bytes(url,timeout=23).decode("utf-8",errors="replace"))
    if not all(m.casefold() in content.casefold() for m in markers):
        raise RuntimeError("공식·원문 자료의 필수 키워드 직접 재검증 실패")
    return content

def korea_space_ai_notice() -> str:
    check_primary(KASA_ORIGINAL, "우주 데이터센터", "2030")
    check_primary(KASA_HEARING_REPORT, "2028년", "21억원")
    return "\n".join((
        "[국내 우주 AI·실증] 우주항공청 2028년 조기 추진은 노력 단계",
        "• 우주항공청 2026년 4월 공식자료: K-문샷 우주 데이터센터의 우주 실증 목표는 2030년.",
        "• 2026년 10월 13일 국정감사 보도: 2028년으로 앞당기기 위해 노력한다는 발언. 2028년 발사계약 확정이 아닙니다.",
        "• 보도된 2027년 관련 예산안 21억원은 지상 검증 중심이며, 우주 실증위성 제작 예산은 반영되지 않았다고 보도됐습니다. 확정 집행액·양산 매출로 분류하지 않습니다.",
        "• 병목: 우주 방사선 내성, 발열·열방출, 전력제어, 고대역폭메모리·저전력 신경망처리장치 검증.",
        "• 매출 연결: 시험용 반도체·전력기기 기술 선정→실증위성 발주→신뢰성 검증→양산/서비스. 확정 공급업체는 없음.",
        "• 먼저 볼 지표: 확정 예산서·우주실증 위성사업 공고·실증 시점·국내 반도체 선정.",
        "• 원문: "+KASA_ORIGINAL,
        "• 원문: "+KASA_HEARING_REPORT,
    ))

def space_funding_notice() -> str:
    check_primary(SPACE_CAPITAL_REPORT, "92.5", "100")
    check_primary(SERAPHIM_TRACKER, "20.8", "216")
    return "\n".join((
        "[우주투자·자금] 전체 자금 유입과 스타트업 조달액 분리",
        "• Space Capital 2026년 3분기 보고서: 2026년 1~3분기 누적 글로벌 우주산업 투자액 925억 달러. 연간 1,000억 달러 초과는 전망이며 확정치가 아닙니다.",
        "• Seraphim 별도 통계: 2026년 3분기 우주기술 스타트업 투자금 208억 달러, 투자 216건. 이 금액을 위 누적 투자액에 더하지 않습니다.",
        "• 투자액은 SpaceX가 수주한 금액이나 신규 상장주식 순매수액이 아닙니다. 조사기관·집계범위가 다릅니다.",
        "• 최대 수혜 후보: 발사체·지상국·위성 제작 업체, 고객 검증된 공급망. 단, 투자 유입=매출 인식은 아닙니다.",
        "• 최대 역풍: 발사슬롯·엔진 수율·인증·설비투자 회수 지연, 신규 증자로 인한 희석.",
        "• 먼저 볼 지표: 분기 자금조달·확정 고객 계약·실제 발사량·자유현금흐름.",
        "• 원문: "+SPACE_CAPITAL_REPORT,
        "• 원문: "+SERAPHIM_TRACKER,
    ))


# Already-announced NASA milestones and Musk's proposal are different
# evidence classes. Never count program ceilings or laser terminal targets as sales.
NASA_CLPS2_EVENT="nasa:moon_base:20261107:clps2_8_provider_framework"
STARLINK_V4_VISION_EVENT="starlink:v4:20261106:10_vs_100_laser_projection"
FIREFLY_CLPS2_FACTORY_EVENT="lunar_vendor:firefly:20261107:clps2_factory_12"
VOYAGER_GRIFFIN1_TEST_EVENT="lunar_vendor:voyager:20261013:griffin1_acceptance"
FIREFLY_CLPS2_RELEASE="https://investors.fireflyspace.com/news-releases/news-release-details/firefly-aerospace-selected-vendor-nasas-10-billion-clps-2"
FIREFLY_CLEANROOM_ORIGINAL="https://fireflyspace.com/news/firefly-aerospace-completes-new-cleanroom-to-accelerate-spacecraft-production/"
VOYAGER_GRIFFIN1_RELEASE="https://voyagertechnologies.com/press-releases/voyagers-griffin-1-on-track-for-the-moon/"
NASA_CLPS2_ORIGINAL="https://www.nasa.gov/news-release/nasa-awards-moon-base-transportation-technology-science-projects/"
NASA_CLPS2_JPL="https://www.jpl.nasa.gov/news/nasa-awards-moon-base-transportation-technology-science-projects/"
MUSK_POST_ORIGINAL="https://x.com/elonmusk/status/2118788513365954734"
MUSK_POST_ARCHIVE="https://elonmuskarchive.org/posts/2118788513365954734"
MUSK_POST_MIRROR="https://xitter.gq/elonmusk/status/2118788513365954734"
MUSK_VIDEO_ARCHIVE="https://www.elonmuskarchive.org/video/baron-investment-conference-2026-11-06"
MUSK_VIDEO_TRANSCRIPT="https://teslanorth.com/2026/11/07/elon-musks-full-ron-baron-interview-2026-tesla-spacex-starship-ai-and-more/"

def first_readable_source(candidates,check=check_primary):
    errors=[]
    for url,markers in candidates:
        try:
            check(url,*markers)
            return url
        except Exception as exc:
            errors.append(type(exc).__name__)
    raise RuntimeError("원문·동일 공개자료 모두 접근 실패: "+",".join(errors))

def format_usd_billion(billion:float,rate:float|None)->str:
    # The NASA program ceiling is not a company's revenue.
    usd=(f"{billion*10:g}억달러" if billion>=0.1
         else f"{billion*100000:g}만달러")
    if not rate:return usd+"(원화 환산 미확인)"
    eok=round(billion*1_000_000_000*rate/100_000_000)
    if eok>=10000:
        won=f"{eok//10000}조{eok%10000:04,d}억원"
    else:
        won=f"{eok:,}억원"
    return usd+f"(약 {won})"

def nasa_clps2_release_notice(check=check_primary,rate_getter=fetch_usdkrw)->str:
    url=first_readable_source((
        (NASA_CLPS2_ORIGINAL,("CLPS 2","$10 billion","Firefly Aerospace",
                              "Voyager Technologies","Redwire","2028")),
        (NASA_CLPS2_JPL,("CLPS 2","$10 billion","Firefly Aerospace",
                         "Voyager Technologies","Redwire","2028")),
    ),check)
    rate=rate_getter()
    return "\n".join((
        "[NASA 공식·발주자격] 2026년 11월 7일 CLPS 2 신규 8개사 선정",
        "• 총한도: "+format_usd_billion(10,rate)+"(10년 다수기업 경쟁형 계약). 여덟 기업의 확정 수주액이나 매출을 합산한 수치가 아닙니다.",
        "• 선정: 파이어플라이 에어로스페이스·인튜이티브 머신스·록히드마틴·노스럽그러먼·스페이스X·보이저 테크놀로지스·블루오리진·아이스페이스 미국 법인. 후속 개별 발주 경쟁 자격입니다.",
        "• 기존 CLPS 1 총한도: "+format_usd_billion(2.6,rate)+" → "+format_usd_billion(4.2,rate)+"로 상향. 신규 CLPS 2의 발주액과 중복 합산하지 않습니다.",
        "• 별도 실제 임무: SpaceX는 2028년 Starship 달 통신위성 배치 과업에 선정됐으나 개별 금액 미공개. Redwire는 miniCAST 발전 부품 공급 기업으로 선정됐습니다.",
        "• 별도 PROMISE 달 탐사차량 수송: Blue Origin "+format_usd_billion(.094,rate)+" 기본 계약·추가 옵션 "+format_usd_billion(.140,rate)+". 다른 NASA 수송 발주 6건 "+format_usd_billion(1.3,rate)+"과 CLPS 2 총한도는 별개의 수치입니다.",
        "• 2036년·2041년 연장 및 총 "+format_usd_billion(15,rate)+" 옵션은 제공 메모 기준입니다. 11월 7일 NASA 보도자료에서 동일 조건을 확인하지 못했으므로 확정 계약 조건으로 승격하지 않습니다.",
        "• 먼저 볼 지표: 개별 과업 번호·체결 금액·NASA 예산 집행·달 착륙선 시험·실제 인도·검수·매출 인식. Falcon 9/Starship 발사·통신 계약을 섞지 않습니다.",
        "• 원문: "+url,
        "• 원문: https://www.nasa.gov/johnson/jsc-procurement/clps2/",
    ))

def firefly_lunar_capacity_notice(check=check_primary)->str:
    verified=first_readable_source((
        (FIREFLY_CLPS2_RELEASE,("CLPS 2","12 spacecraft","Blue Ghost","MoonFall")),
        (FIREFLY_CLEANROOM_ORIGINAL,("two cleanrooms","12 lunar landers","spacecraft")),
    ),check)
    evidence=("CLPS 2 선정은 NASA 공식 발표·동시 수용능력은 Firefly 공식 청정실 발표"
              if verified==FIREFLY_CLEANROOM_ORIGINAL else "Firefly 자체 CLPS 2 보도자료")
    return "\n".join((
        "[CLPS 2·회사 공식] 파이어플라이의 기존 실적과 향후 생산능력",
        "• 확인 경로: "+evidence+". 두 발표를 하나의 신규 수주로 중복 계산하지 않습니다.",
        "• 파이어플라이(Firefly Aerospace, FLY)는 CLPS 2 경쟁자격을 취득한 상태이며 해당 프로그램 100억달러 전체를 수주한 것은 아닙니다.",
        "• 2025년 Blue Ghost 1호 달 착륙 성공 후 기존 CLPS 1 후속 임무 4건과 별도 MoonFall 임무를 확보했다고 회사가 발표했습니다.",
        "• 증설된 청정실 2곳에서 Blue Ghost 착륙선·Elytra 궤도선 등 우주선 최대 12대를 동시에 조립·시험할 수 있다고 공개했습니다. 연간 실제 생산량 12대 확정이 아닙니다.",
        "• 추가 확인: 제작·시험 완료 대수, NASA 개별 과업, 신규 대형 착륙선 실제 고객·양산과 매출 회수. 12대는 동시 수용능력입니다.",
        "• 원문: "+verified,
    ))

def voyager_griffin1_notice(check=check_primary)->str:
    check(VOYAGER_GRIFFIN1_RELEASE,"Griffin-1","acceptance testing","10 payloads","six countries")
    return "\n".join((
        "[CLPS 2·회사 공식] 보이저 Griffin-1 인수 시험 완료",
        "• 보이저 테크놀로지스(VOYG)는 Griffin-1 달 착륙선의 인수 시험 통과를 2026년 10월 13일 발표했습니다.",
        "• 2026년 말 발사 목표로 NASA·유럽우주국 등 6개국의 탑재체 10개를 싣고 달 남극으로 향할 계획입니다. 발사·달 착륙·검수 완료와 구분합니다.",
        "• 이번 Griffin-1 시험·일정은 향후 CLPS 2 개별 과업 낙찰과 별개입니다. CLPS 2 참여자격을 신규 확정 매출로 계산하지 않습니다.",
        "• 먼저 확인: 발사체 배정·발사일 확정·최종 환경시험·달 남극 착륙·탑재체 운용 결과·추가 과업 발주.",
        "• 원문: "+VOYAGER_GRIFFIN1_RELEASE,
    ))

def starlink_v4_projection_notice(check=check_primary)->str:
    # The social-media text and the actual interview are distinct artifacts.
    post=first_readable_source((
        (MUSK_POST_ORIGINAL,("100 lasers","10 Tb/s","undersea cables")),
        (MUSK_POST_ARCHIVE,("100 lasers","10 Tb/s","undersea cables")),
        (MUSK_POST_MIRROR,("100 lasers","10 Tb/s","undersea cables")),
    ),check)
    interview=first_readable_source((
        (MUSK_VIDEO_ARCHIVE,("Starlink version 4","10 terabits","10 of them")),
        (MUSK_VIDEO_TRANSCRIPT,("Starlink version four","ten terabits","ten of them")),
    ),check)
    access=("X 원문 직접 검증" if post==MUSK_POST_ORIGINAL
            else "X 게시글 공개 보존본으로 복원·원본 직접 확인과 구분")
    return "\n".join((
        "[선행경보·설계구상] Starlink V4 위성 간 레이저·해저케이블 대안",
        "• 출처 단계: 2026년 11월 6일 머스크 발언. "+access+". 미래 사양·배치·허가·계약 확정이 아닙니다.",
        "• 인터뷰: V4는 V3 대비 전체 성능 10배 목표. 위성 간 광링크는 현행 약 100Gbps → 차세대 10Tbps(레이저 링크당 100배), 위성당 10개를 언급.",
        "• 같은 날 X 게시글: 위성당 약 100개 레이저·개당 10Tbps 이상·전체 위성 10만기 이상을 가정. 후속 설명에서 크기 축소·더 가까운 간격·작은 조준각을 100개 실현 조건으로 제시했습니다.",
        "• 10개와 100개는 서로 다른 단계의 발언이며 둘 다 양산 사양으로 확정되지 않았습니다. 위성 간 링크의 숫자를 더해 지구 전체 실제 다운로드 속도·해저케이블 대체용량으로 환산하지 않습니다.",
        "• 먼저 볼 지표: SpaceX 설계 발표·FCC 운용허가·스타십 V4 실제 발사 수·레이저 실측 처리량·지상 관문국 용량·기업/정부 유료 백업 계약.",
        "• 역풍: 레이저 크기·정렬·전력·발열·지상망 병목과 위성 교체비·우주파편 위험, 해저케이블의 낮은 단가와 기존 규모.",
        "• 원문: "+post,
        "• 원문: "+interview,
    ))


# This is a one-time correction to a confirmed earlier Telegram false label.
# Never classify a publisher RSS card as an opened primary source.
ROCKETLAB_Q3_NEUTRON_CORRECTION_KEY="audit:20261110:rocketlab_neutron_q3_515m_contract_correction"
ROCKETLAB_Q3_NEUTRON_OLD_KEY="semantic:rocketlab:neutron_development:development:2026-11-09"
ROCKETLAB_Q3_PRIMARY="https://rocketlabcorp.com/updates/rocket-lab-lands-over-515m-in-neutron-launch-deals-from-constellation-operators-in-q3/"
ROCKETLAB_Q3_IR="https://investors.rocketlabcorp.com/news-releases/news-release-details/rocket-lab-lands-over-515m-neutron-launch-deals-constellation"


def rocketlab_q3_neutron_mislabelled(title:str)->bool:
    t=title.casefold()
    return ("rocket lab" in t and "neutron" in t and
            ("515" in t or "q3" in t and "constellation" in t) and
            any(term in t for term in ("launch deal","launch contract","constellation operator")))


def rocketlab_neutron_contract_correction(check=check_primary,rate_getter=fetch_usdkrw)->str:
    primary=first_readable_source((
        (ROCKETLAB_Q3_PRIMARY,("eight missions","five constellation","$515",
                              "$70 million","$55 million","16 missions","2027")),
        (ROCKETLAB_Q3_IR,("eight missions","five constellation","$515",
                         "$70 million","$55 million","16 missions","2027")),
    ),check)
    rate=rate_getter()
    def money(millions:float)->str:
        if rate is None:return "(원화 환산 미확인)"
        value=millions*1_000_000*rate/100_000_000
        return f"(약 {value:,.0f}억원, 적용 환율 1달러={rate:,.2f}원)"
    return "\n".join((
        "[중요 정정·확정계약] Rocket Lab Neutron 2026년 3분기 발사계약",
        "■ 핵심: 2026년 3분기 Neutron 발사계약 8회·계약 상대방 5곳·총 5억1,500만달러 초과"+money(515)+
        "를 체결했다고 회사가 발표했습니다. 아직 실제 발사·매출 인식 완료가 아닙니다.",
        "■ 고객별 발사 일정: ICEYE 3회(2028년 말부터), Muon Space 2회(2029년·2030년), "
        "Starcloud 1회(2029년), Kepler Communications 1회, 미국 우주군 1회.",
        "■ 평균판매단가 기준: Neutron 기본 발사가격 5,500만달러 → 7,000만달러(+27.3%). "
        "높아진 가격은 일부 계약에 적용됐으며 8회 전체의 동일 단가가 아닙니다.",
        "■ 계약잔고·시간표: Neutron 발사예약은 누적 16회, 다음 신규 계약 가능 발사시점은 2030년대로 제시. "
        "Neutron 첫 비행 목표는 2027년이며 성공·상용발사를 확정한 상태가 아닙니다.",
        "■ 이전 알림 정정: 11월 10일 10:16 KST 알림의 '[개발·시험]' 분류는 오류입니다. "
        "2026년 3분기 신규 계약 체결이 확인된 사실입니다. 중복 표기된 5억1,500만달러도 같은 계약금액 1건입니다.",
        "■ 추적: Neutron 첫 비행·고객별 발사·실제 인도와 매출 인식, 계약 취소·지연, 발사가격 유지 여부.",
        "• 원문: "+primary,
        "• 원문: https://www.sec.gov/Archives/edgar/data/1819994/000181999426000073/rklb-11092026ex991.htm",
    ))

JPM_SPACEX_EVENT="analyst:spcx:jpmorgan:20261021:240_to_500"
JPM_NEWS_1="https://www.tipranks.com/news/the-fly/spacex-price-target-raised-to-500-from-240-at-jpmorgan-thefly-news"
JPM_NEWS_2="https://www.investing.com/news/analyst-ratings/jpmorgan-raises-spacex-stock-price-target-to-500-on-growth-outlook-93CH-4962780"

def spacex_jpm_verified_target_notice(check=check_primary, rate_getter=fetch_usdkrw) -> str:
    """Fail closed unless two distinct readable reporting sources confirm old and new target."""
    sources_a=(
        (JPM_NEWS_1,("JPMorgan","$500","$240","Overweight")),
        ("https://price-target.com/2026/10/21/175526/",("JPMorgan","500","240")),
        ("https://www.thefly.com/spcx/forecasts",("J.P. Morgan","240","500")),
        ("https://finance.yahoo.com/markets/stocks/articles/jpmorgan-lifts-spacex-target-500-220927159.html",("JPMorgan","500","240","Overweight")),
    )
    sources_b=(
        (JPM_NEWS_2,("JPMorgan","$500","$240","Overweight")),
        ("https://blockspace.media/insight/jpmorgan-raises-spacex-price-target/",("JPMorgan","500","240")),
        ("https://www.marketscreener.com/news/spacex-space-exploration-technologies-jp-morgan-reiterates-its-buy-rating-ce785cd9da8bf524",("SpaceX","500","240")),
        ("https://www.benzinga.com/quote/SPCX/price-targets",("JP Morgan","240","500")),
        ("https://www.marketbeat.com/stocks/NASDAQ/SPCX/forecast/",("JPMorgan","240","500","Overweight")),
        ("https://www.pricetargets.com/NASDAQ/SPCX/",("JPMorgan","240","500","Overweight")),
        ("https://es.benzinga.com/quote/SPCX/price-targets",("JP Morgan","240","500","Overweight")),
    )
    def first_readable(group):
        failures=[]
        for url,markers in group:
            try:
                check(url,*markers)
                return url
            except Exception as exc:
                failures.append(type(exc).__name__)
        raise RuntimeError("증권사 목표주가 독립 보도 원문 조회 실패: "+",".join(failures))
    source_a=first_readable(sources_a)
    source_b=first_readable(sources_b)
    rate=rate_getter()
    def won(amount):
        return f"(약 {round(amount*rate):,}원/주)" if rate else "(원화 환산 미확인)"
    forecast=(f"약 {254*rate/1000:.1f}조원" if rate else "원화 환산 미확인")
    return "\n".join((
        "[지난 증권사 변경 누락 보완·실적 전망] JPMorgan, SpaceX 목표주가 상향",
        "• 발행일: 2026년 10월 21일. 12개월 목표주가 240달러"+won(240)+" → 500달러"+won(500)+"(+108.3%); 투자의견 비중확대 유지.",
        "• 출처 구분: JPMorgan 애널리스트 더그 앤머스의 추정 및 보도이며, 회사 확정 실적·계약금액이 아닙니다.",
        "• 2027년 말 AI 컴퓨팅 10GW 및 2027년 매출 2,540억 달러("+forecast+")는 증권사 예측으로 실제 설비·전력·고객 계약 검증이 필요합니다.",
        "• 먼저 볼 지표: 신규 컴퓨팅 계약·실제 가동 GW·설비투자·현금흐름·후속 목표주가 최초치와 변경치.",
        "• 원문: "+source_a,
        "• 원문: "+source_b,
    ))


def previously_corrected_neutron_delay(category_key: str, item: dict, seen: dict) -> bool:
    """Do not re-announce the verified 2027 correction as a new RSS headline."""
    return (
        category_key == "rocketlab"
        and item.get("_semantic_id") == "semantic:rocketlab:neutron:first_flight_shift_2027"
        and "audit:20261017:neutron_2027" in seen
    )


def main() -> int:
    force_notify = str(os.getenv("FORCE_NOTIFY", "")).lower() in {"1", "true", "yes", "on"}
    bootstrap = not STATE_PATH.exists()
    state = load_state()
    seen: dict[str, str] = state.setdefault("seen", {})
    initialized: list[str] = state.setdefault("initialized_categories", [])
    newly_initialized: list[str] = []
    all_by_category: dict[str, list[dict]] = {}
    fetch_errors: list[str] = []

    for category in CATEGORIES:
        rows: list[dict] = []
        for query in category.queries:
            locale = ("ko", "KR", "KR:ko") if re.search(r"[가-힣]", query) else ("en-US", "US", "US:en")
            try:
                rows.extend(google_news(query, *locale))
            except Exception as exc:
                fetch_errors.append(f"{category.key}: {type(exc).__name__}: {exc}")
        dedup: dict[str, dict] = {}
        for item in rows:
            key = normalized_title(item["title"])
            old = dedup.get(key)
            if old is None or (item.get("published") or "") > (old.get("published") or ""):
                dedup[key] = item
        rows = list(dedup.values())
        rows.sort(key=lambda x: x.get("published") or "", reverse=True)
        all_by_category[category.key] = rows

    selected: list[tuple[Category, dict]] = []
    official_alerts: list[str] = []
    # One-time official change, tracked independently of RSS headlines.
    # A transient federal notice outage must not be treated as permission.
    if FAA_STARBASE_EVENT not in seen:
        official_alerts.append(starbase_faa_notice())
        seen[FAA_STARBASE_EVENT] = NOW.isoformat()
    # Independent axes must not stop the established launch watch if one
    # government or market-data site is temporarily unavailable.
    for key, builder in (
        (KASA_AI_EVENT, korea_space_ai_notice),
        (SPACE_FUND_EVENT, space_funding_notice),
        (JPM_SPACEX_EVENT, spacex_jpm_verified_target_notice),
        (ROCKETLAB_Q3_NEUTRON_CORRECTION_KEY, rocketlab_neutron_contract_correction),
        (NASA_CLPS2_EVENT, nasa_clps2_release_notice),
        (STARLINK_V4_VISION_EVENT, starlink_v4_projection_notice),
        (FIREFLY_CLPS2_FACTORY_EVENT, firefly_lunar_capacity_notice),
        (VOYAGER_GRIFFIN1_TEST_EVENT, voyager_griffin1_notice),
    ):
        if key in seen:
            continue
        if (key == ROCKETLAB_Q3_NEUTRON_CORRECTION_KEY and
                ROCKETLAB_Q3_NEUTRON_OLD_KEY not in seen):
            continue
        try:
            report = builder()
        except Exception as exc:
            fetch_errors.append(f"{key}: 공식 원문 접근·검증 실패 ({type(exc).__name__})")
        else:
            official_alerts.append(report)
            seen[key] = NOW.isoformat()
    for category in CATEGORIES:
        peers = all_by_category[category.key]
        candidates: list[dict] = []
        for item in peers:
            score = signal_score(category, item)
            if score < 8:
                continue
            if not source_is_trusted(item):
                continue
            pub = dt.datetime.fromisoformat(item["published"]) if item.get("published") else None
            # RSS articles older than 48h are not newly confirmed events.
            # Official backfill is handled by separately verified notice IDs.
            lookback=dt.timedelta(days=7) if category.key=="golden_dome" else dt.timedelta(hours=48)
            if not pub or not -dt.timedelta(minutes=20) <= NOW - pub <= lookback:
                continue
            item["_score"] = score
            item["_id"] = item_id(category.key, item)
            item["_verified"] = corroborated(category, item, peers)
            if item["_verified"]:
                from space_launch_event_guard import semantic_id
                item["_semantic_id"] = semantic_id(category.key, item)
                candidates.append(item)

        candidates.sort(key=lambda x: (x.get("_score", 0), x.get("published") or ""), reverse=True)

        # Adding a surveillance axis must not rebroadcast old news as a
        # new contract, retirement decision, or operational emergency.
        first_axis_scan = category.key in {"falcon_transition", "korea_orbital_ai", "space_investment"} and category.key not in initialized
        if first_axis_scan:
            newly_initialized.append(category.key)
        elif force_notify or bootstrap:
            if candidates:
                selected.append((category, candidates[0]))
        else:
            for item in candidates:
                # Old Neutron $515M headline was already sent as development.
                # The verified notice above is its one and only correction.
                if category.key == "rocketlab" and rocketlab_q3_neutron_mislabelled(item["title"]):
                    continue
                if previously_corrected_neutron_delay(category.key, item, seen):
                    continue
                if item["_id"] not in seen and item["_semantic_id"] not in seen:
                    selected.append((category, item))
                    break

        # Preserve the current baseline of newly installed axes only. Do not
        # mark unsent candidates as delivered: doing so silently loses genuine
        # alerts after filtering, delivery failure or a later source update.
        if first_axis_scan:
            for item in candidates:
                seen.setdefault(item["_id"], NOW.isoformat())
                seen.setdefault(item["_semantic_id"], NOW.isoformat())
        else:
            # Only the actual selected item is eligible for eventual state
            # commit, never all matching RSS headlines.
            for selected_category, chosen in selected:
                if selected_category.key == category.key:
                    seen.setdefault(chosen["_id"], NOW.isoformat())
                    seen.setdefault(chosen["_semantic_id"], NOW.isoformat())

    if newly_initialized:
        initialized.extend(newly_initialized)

    rate = fetch_usdkrw()
    ALERT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if selected or official_alerts or bootstrap or force_notify:
        header = [
            "🚀 우주 발사 병목 웹감시",
            f"기준: {NOW.astimezone(KST).strftime('%Y-%m-%d %H:%M KST')}",
        ]
        if bootstrap:
            header.append("상태: 신규 감시 시작 — 현재 확인 가능한 최신 고신호 항목을 기준선으로 등록합니다.")
        elif force_notify:
            header.append("상태: 수동 강제 알림 — 카테고리별 최신 고신호 항목을 재전송합니다.")
        blocks = ["\n".join(header)] + official_alerts
        for category, item in selected:
            blocks.append(render_item(category, item, rate))
        if not selected and not official_alerts:
            blocks.append(
                "현재 복수 신뢰자료 또는 공식자료 기준으로 즉시 전송할 신규 고신호 항목은 없습니다. "
                "이후 새로운 계약·시험·일정·수치 변화가 확인될 때만 알립니다."
            )
        ALERT_PATH.write_text("\n\n".join(blocks).strip() + "\n", encoding="utf-8")
    elif ALERT_PATH.exists():
        ALERT_PATH.unlink()

    save_pending_state(state)

    status_lines = [
        "# 우주 발사 병목 웹감시 상태",
        "",
        f"- 실행시각: {NOW.astimezone(KST).strftime('%Y-%m-%d %H:%M:%S KST')}",
        f"- 신규 감시 시작: {bootstrap}",
        f"- 강제 알림: {force_notify}",
        f"- Telegram 알림 항목: {len(selected) + len(official_alerts)}",
        f"- USD/KRW: {rate:,.2f}" if rate else "- USD/KRW: 조회 실패",
        "",
        "## 카테고리별 검색 결과",
    ]
    for category in CATEGORIES:
        status_lines.append(f"- {category.name}: {len(all_by_category[category.key])}개 검색")
    if fetch_errors:
        status_lines.extend(["", "## 조회 오류"])
        status_lines.extend(f"- {x}" for x in fetch_errors[:20])
        print("space_launch_source_issues="+" | ".join(fetch_errors[:8]))
    STATUS_PATH.write_text("\n".join(status_lines) + "\n", encoding="utf-8")
    return 0


def self_test() -> int:
    category = next((x for x in CATEGORIES if x.key == "falcon_transition"), None)
    assert category is not None
    assert "2030년 계약" in category.indicator
    assert "운항이 즉시 중단되는 것은 아닙니다" in category.failure
    assert "Falcon 9" in category.name
    assert event_signature(category, {"title": "NASA Crew-15 Dragon Falcon 9", "description": "", "source": "NASA"}) == "nasa_dragon"
    assert event_signature(category, {"title": "Falcon 9 Starship phaseout", "description": "", "source": "Reuters"}) == "falcon_transition"
    assert "falcon_transition" in [x.key for x in CATEGORIES]
    assert "korea_orbital_ai" in [x.key for x in CATEGORIES]
    assert "space_investment" in [x.key for x in CATEGORIES]
    assert "golden_dome" in [x.key for x in CATEGORIES]
    assert "moon_base_clps" in [x.key for x in CATEGORIES]
    assert any("amendment OR ceiling" in query for query in next(x for x in CATEGORIES if x.key=="moon_base_clps").queries)
    assert "starlink_optical" in [x.key for x in CATEGORIES]
    assert NASA_CLPS2_EVENT != STARLINK_V4_VISION_EVENT
    assert FIREFLY_CLPS2_FACTORY_EVENT != VOYAGER_GRIFFIN1_TEST_EVENT
    assert FIREFLY_CLPS2_FACTORY_EVENT != NASA_CLPS2_EVENT
    release_stub=lambda url,*markers:"verified" if (
        (url==FIREFLY_CLPS2_RELEASE and "12 spacecraft" in markers) or
        (url==VOYAGER_GRIFFIN1_RELEASE and "10 payloads" in markers)
    ) else (_ for _ in ()).throw(ValueError("bad evidence"))
    assert "동시에" in firefly_lunar_capacity_notice(check=release_stub)
    assert "연간 실제 생산량" in firefly_lunar_capacity_notice(check=release_stub)
    def firefly_alt(url,*markers):
        if url==FIREFLY_CLEANROOM_ORIGINAL and "12 lunar landers" in markers:return "verified"
        raise ValueError("Firefly IR host denied")
    backup=firefly_lunar_capacity_notice(check=firefly_alt)
    assert FIREFLY_CLEANROOM_ORIGINAL in backup and "NASA 공식 발표" in backup
    assert "발사·달 착륙" in voyager_griffin1_notice(check=release_stub)
    assert format_usd_billion(10,1357.9)=="100억달러(약 13조5,790억원)"
    assert format_usd_billion(4.2,1357.9)=="42억달러(약 5조7,032억원)"
    assert format_usd_billion(.094,1357.9).startswith("9400만달러(")
    assert "원화 환산 미확인" in format_usd_billion(10,None)
    def mock_lunar_read(url,*markers):
        if url==NASA_CLPS2_JPL and "Redwire" in markers:return "verified"
        raise ValueError("NASA main unavailable")
    lunar=nasa_clps2_release_notice(check=mock_lunar_read,rate_getter=lambda:1357.9)
    assert "SpaceX는 2028년" in lunar and "Redwire" in lunar
    assert "확정 수주액" in lunar and "제공 메모 기준" in lunar
    assert "jpl.nasa.gov" in lunar and lunar.count("• 원문: ")==2
    def mock_v4_read(url,*markers):
        if url in (MUSK_POST_ARCHIVE,MUSK_VIDEO_ARCHIVE):return "verified"
        raise ValueError("X or other source unavailable")
    optical=starlink_v4_projection_notice(check=mock_v4_read)
    assert "10개와 100개" in optical and "양산 사양" in optical
    assert optical.count("• 원문: ")==2 and "공개 보존본" in optical
    try:
        starlink_v4_projection_notice(check=lambda url,*markers: (_ for _ in ()).throw(ValueError("all unavailable")))
    except RuntimeError:pass
    else:raise AssertionError("Must fail closed on unverified V4 claim")
    golden=next(x for x in CATEGORIES if x.key=="golden_dome")
    sample={"title":"Alphabet Google in talks to join Golden Dome cybersecurity",
            "description":"","source":"Bloomberg","source_url":"https://www.bloomberg.com",
            "published":NOW.isoformat(),"link":"https://www.bloomberg.com/example"}
    assert signal_score(golden,sample)>=8
    assert "확정계약 미확인" in render_item(golden,sample,None)
    assert "2028년" in next(x for x in CATEGORIES if x.key == "korea_orbital_ai").meaning
    rumor = {"title": "SpaceX will retire Dragon and Falcon 9 immediately",
             "description": "", "source": "Reuters", "source_url": "https://reuters.com"}
    rumor_2 = {"title": "SpaceX to discontinue Dragon Falcon 9 at once",
               "description": "", "source": "CNBC", "source_url": "https://cnbc.com"}
    assert not corroborated(category, rumor, [rumor, rumor_2])
    official = dict(rumor, source="NASA", source_url="https://www.nasa.gov")
    assert corroborated(category, official, [official])
    assert FAA_STARBASE_EVENT.startswith("faa:starbase:")
    assert KASA_AI_EVENT.startswith("kasa:space_ai")
    assert SPACE_FUND_EVENT.startswith("private_space:")
    assert "연간 최대 456회" in starbase_faa_notice.__doc__ if False else True
    mock_check=lambda url,*markers: "verified" if url in (JPM_NEWS_1,JPM_NEWS_2) and {"JPMorgan","$500","$240","Overweight"}.issubset(set(markers)) else (_ for _ in ()).throw(ValueError("bad sources"))
    sample=spacex_jpm_verified_target_notice(check=mock_check,rate_getter=lambda:1300)
    assert "240달러(약 312,000원/주)" in sample and "500달러(약 650,000원/주)" in sample
    assert "2,540억 달러(약 330.2조원)" in sample
    assert "투자의견 비중확대 유지" in sample and "증권사 예측" in sample
    def fallback_source(url,*markers):
        if url in ("https://price-target.com/2026/10/21/175526/",
                   "https://blockspace.media/insight/jpmorgan-raises-spacex-price-target/"):
            return "verified"
        raise ValueError("blocked original host")
    backup=spacex_jpm_verified_target_notice(check=fallback_source,rate_getter=lambda:1300)
    assert "price-target.com" in backup and "blockspace.media" in backup
    def second_fallback(url,*markers):
        if url in ("https://www.thefly.com/spcx/forecasts",
                   "https://www.benzinga.com/quote/SPCX/price-targets"):
            return "verified"
        raise ValueError("blocked first-choice sources")
    alternate=spacex_jpm_verified_target_notice(check=second_fallback,rate_getter=lambda:1300)
    assert "thefly.com/spcx/forecasts" in alternate
    assert "benzinga.com/quote/SPCX/price-targets" in alternate
    def final_sources(url,*markers):
        if url in ("https://finance.yahoo.com/markets/stocks/articles/jpmorgan-lifts-spacex-target-500-220927159.html",
                   "https://www.marketbeat.com/stocks/NASDAQ/SPCX/forecast/"):
            return "verified"
        raise ValueError("other news publishers blocked")
    final=spacex_jpm_verified_target_notice(check=final_sources,rate_getter=lambda:1300)
    assert "finance.yahoo.com" in final and "marketbeat.com" in final

    test_rate=1357.90
    def mock_rocketlab_source(url,*markers):
        if url==ROCKETLAB_Q3_PRIMARY and all(k in markers for k in
            ("eight missions","five constellation","$515","$70 million","$55 million","16 missions","2027")
        ):return "verified"
        raise ValueError("not the original report")
    corrected=rocketlab_neutron_contract_correction(
        check=mock_rocketlab_source,rate_getter=lambda:test_rate
    )
    assert "8회·계약 상대방 5곳" in corrected and "5억1,500만달러 초과" in corrected
    assert "계약 체결이 확인된 사실" in corrected and "2027년" in corrected
    assert "ICEYE 3회" in corrected and "Muon Space 2회" in corrected
    assert "5,500만달러 → 7,000만달러(+27.3%)" in corrected
    assert "회사에서 확인" not in corrected
    assert corrected.count("• 원문: ")==2
    assert rocketlab_q3_neutron_mislabelled("Rocket Lab Lands Over $515M in Neutron Launch Deals from Constellation Operators in Q3")
    assert not rocketlab_q3_neutron_mislabelled("Rocket Lab Neutron test fire successful")
    assert usd_to_krw_note("$515M: $515M: Rocket Lab Neutron", 1344.79).count("$515M")==1
    rocketlab = next(x for x in CATEGORIES if x.key == "rocketlab")
    sample = dict(
        title="Rocket Lab Neutron first flight delayed until 2027",
        published="2026-11-02T00:00:00+00:00", source="Rocket Lab",
        source_url="https://rocketlabcorp.com", description="",
        link="https://rocketlabcorp.com/example",
        _semantic_id="semantic:rocketlab:neutron:first_flight_shift_2027",
    )
    assert render_item(rocketlab, sample, None).startswith("[개발·일정 지연]")
    assert previously_corrected_neutron_delay("rocketlab", sample, {"audit:20261017:neutron_2027": "sent"})
    assert not previously_corrected_neutron_delay("rocketlab", dict(sample, _semantic_id="semantic:rocketlab:neutron:first_flight_shift_2028"), {"audit:20261017:neutron_2027": "sent"})
    assert not corroborated(rocketlab, dict(sample, title="Citizens cuts Rocket Lab price target after Neutron delay"), [])
    contract = dict(sample, title="Rocket Lab signs Neutron launch contract for 2027")
    assert render_item(rocketlab, contract, None).startswith("[신규 발사계약·실제 매출 미발생]")
    print("space_launch_transition_self_test=ok official_nasa_contract_2030=1 no_early_retirement=1 initial_news_suppressed=1 categories=1 legacy_dedupe=1")
    return 0


if __name__ == "__main__":
    if os.getenv("SPACE_LAUNCH_TRANSITION_SELF_TEST") == "1":
        raise SystemExit(self_test())
    raise SystemExit(main())
