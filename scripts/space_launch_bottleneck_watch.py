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
)


def request_bytes(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


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
    if category.key == "launch_slots":
        if "open cosmos" in text:
            return "open_cosmos"
        if "faa" in text:
            return "faa"
        return "slot_shortage"
    return category.key


def corroborated(category: Category, item: dict, peers: Iterable[dict]) -> bool:
    if source_is_official(item):
        return True
    if not source_is_trusted(item):
        return False
    sig = event_signature(category, item)
    source = (item.get("source") or "").strip().lower()
    for peer in peers:
        if peer is item or not source_is_trusted(peer):
            continue
        peer_source = (peer.get("source") or "").strip().lower()
        if not peer_source or peer_source == source:
            continue
        if event_signature(category, peer) != sig:
            continue
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
    for number, unit in matches[:3]:
        value = float(number)
        u = unit.lower()
        if u in {"b", "bn", "billion"}:
            usd = value * 1_000_000_000
        elif u in {"m", "mn", "million"}:
            usd = value * 1_000_000
        else:
            usd = value
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
    except Exception:
        return {"version": 1, "seen": {}, "created_at": NOW.isoformat(), "recovered": True}


def save_pending_state(state: dict) -> None:
    PENDING_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = NOW.isoformat()
    seen = state.get("seen", {})
    if len(seen) > 2500:
        ordered = sorted(seen.items(), key=lambda kv: kv[1], reverse=True)[:2000]
        state["seen"] = dict(ordered)
    PENDING_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def render_item(category: Category, item: dict, rate: float | None) -> str:
    pub = dt.datetime.fromisoformat(item["published"]) if item.get("published") else None
    when = pub.astimezone(KST).strftime("%Y-%m-%d %H:%M KST") if pub else "게시시각 확인 불가"
    official = source_is_official(item)
    verification = "공식자료" if official else "복수 신뢰보도 교차확인"
    numbers = extract_numbers(item_text(item))
    krw = usd_to_krw_note(item_text(item), rate)
    lines = [
        f"{category.tag} {category.name}",
        f"• {item['title']}",
        f"• 검증: {verification} | 출처: {item.get('source') or '출처 미표기'} | {when}",
        f"• 핵심 숫자: {numbers}",
    ]
    if krw:
        lines.append(f"• 원화 환산(USD/KRW {rate:,.2f}): {krw}")
    lines.extend(
        [
            f"• 투자 의미: {category.meaning}",
            f"• 실패 경로: {category.failure}",
            f"• 먼저 볼 지표: {category.indicator}",
            f"• 원문: {item['link']}",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    force_notify = str(os.getenv("FORCE_NOTIFY", "")).lower() in {"1", "true", "yes", "on"}
    bootstrap = not STATE_PATH.exists()
    state = load_state()
    seen: dict[str, str] = state.setdefault("seen", {})
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
            if pub and NOW - pub > dt.timedelta(days=14):
                continue
            item["_score"] = score
            item["_id"] = item_id(category.key, item)
            item["_verified"] = corroborated(category, item, peers)
            if item["_verified"]:
                candidates.append(item)

        candidates.sort(key=lambda x: (x.get("_score", 0), x.get("published") or ""), reverse=True)

        if force_notify or bootstrap:
            if candidates:
                selected.append((category, candidates[0]))
        else:
            for item in candidates:
                if item["_id"] not in seen:
                    selected.append((category, item))
                    break

        for item in peers:
            iid = item_id(category.key, item)
            if source_is_trusted(item) and signal_score(category, item) >= 0:
                seen[iid] = NOW.isoformat()

    rate = fetch_usdkrw()
    ALERT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if selected or bootstrap or force_notify:
        header = [
            "🚀 우주 발사 병목 웹감시",
            f"기준: {NOW.astimezone(KST).strftime('%Y-%m-%d %H:%M KST')}",
        ]
        if bootstrap:
            header.append("상태: 신규 감시 시작 — 현재 확인 가능한 최신 고신호 항목을 기준선으로 등록합니다.")
        elif force_notify:
            header.append("상태: 수동 강제 알림 — 카테고리별 최신 고신호 항목을 재전송합니다.")
        blocks = ["\n".join(header)]
        for category, item in selected:
            blocks.append(render_item(category, item, rate))
        if not selected:
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
        f"- Telegram 알림 항목: {len(selected)}",
        f"- USD/KRW: {rate:,.2f}" if rate else "- USD/KRW: 조회 실패",
        "",
        "## 카테고리별 검색 결과",
    ]
    for category in CATEGORIES:
        status_lines.append(f"- {category.name}: {len(all_by_category[category.key])}개 검색")
    if fetch_errors:
        status_lines.extend(["", "## 조회 오류"])
        status_lines.extend(f"- {x}" for x in fetch_errors[:20])
    STATUS_PATH.write_text("\n".join(status_lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
