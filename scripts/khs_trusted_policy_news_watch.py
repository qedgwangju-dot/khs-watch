#!/usr/bin/env python3
"""KHS trusted policy-news watch.

This lane is intentionally separate from the official-source policy watcher.
It catches high-impact policy news reported by trusted outlets before an
agency posts a formal release, and labels every alert as "공식 확인 전".
"""

from __future__ import annotations

import datetime as dt
import email.utils
import hashlib
import html
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from khs_policy_alert_explainer import ensure_explained, explanation_lines

KST = ZoneInfo("Asia/Seoul")
UTC = dt.timezone.utc
ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "out"
DATA_DIR = ROOT / "data"
SEEN_PATH = DATA_DIR / "khs_trusted_policy_news_seen.json"
ALERT_PATH = OUT_DIR / "khs_trusted_policy_news_alert.md"
TITLE_PATH = OUT_DIR / "khs_trusted_policy_news_title.txt"
ALERTS_JSON_PATH = OUT_DIR / "khs_trusted_policy_news_alerts.json"

MAX_AGE_HOURS = int(os.getenv("KHS_TRUSTED_NEWS_MAX_AGE_HOURS", "72"))
FORMAT_VERSION = "trusted-policy-news-v1"

TRUSTED_SOURCES = {
    "european commission",
    "european council",
    "european parliament",
    "official journal of the european union",
    "politico",
    "reuters",
    "bloomberg",
    "the wall street journal",
    "wall street journal",
    "financial times",
    "cnbc",
    "marketwatch",
    "ap news",
    "associated press",
    "yonhap news agency",
    "yonhap news",
    "연합뉴스",
    "the korea economic daily",
    "korea economic daily",
    "한국경제",
    "한국경제신문",
    "매일경제",
    "서울신문",
    "서울경제신문",
    "서울경제",
}

SOURCE_PRIORITY = {
    "european commission": 0,
    "official journal of the european union": 0,
    "european council": 1,
    "european parliament": 1,
    "reuters": 1,
    "bloomberg": 2,
    "the wall street journal": 3,
    "wall street journal": 3,
    "financial times": 4,
    "cnbc": 5,
    "marketwatch": 6,
    "ap news": 7,
    "associated press": 7,
    "politico": 8,
    "yonhap news agency": 9,
    "yonhap news": 9,
    "연합뉴스": 9,
    "the korea economic daily": 10,
    "korea economic daily": 10,
    "한국경제": 10,
    "한국경제신문": 10,
    "매일경제": 11,
    "서울신문": 11,
    "서울경제신문": 11,
    "서울경제": 11,
}

TRUSTED_WIRE_RELAY_SOURCES = {
    "aol.com",
    "investing.com",
    "kfgo",
    "kfgo am",
    "kfgo-am",
}


@dataclass(frozen=True)
class StoryRule:
    key: str
    title: str
    google_queries: tuple[str, ...]
    required_groups: tuple[tuple[str, ...], ...]
    core: str
    impact: str
    point: str
    counter: str
    sectors: str
    impacts: tuple[str, ...]
    paths: tuple[str, ...]
    follow_up: str


STORY_RULES = (
    StoryRule(
        key="us_fcc_foreign_energy_inverter_ban",
        title="미국 FCC, 외국산 에너지 인버터 수입금지 검토 보도",
        google_queries=(
            "Reuters FCC foreign energy inverters ban solar national security",
            "Bloomberg FCC foreign inverters import ban solar stocks",
            "Trump administration ban foreign energy inverters Reuters FCC",
            "US working ban Chinese energy inverters FCC Reuters",
            "\"foreign energy inverters\" \"FCC\" Reuters",
        ),
        required_groups=(
            ("inverter", "inverters"),
            ("ban", "barred", "imports", "import", "targeting", "foreign", "chinese", "national security"),
            ("foreign", "chinese", "china"),
            ("solar", "energy", "renewable", "grid"),
        ),
        core="Reuters·Bloomberg 계열 보도 기준, 미국 FCC가 국가안보 우려를 이유로 외국산 또는 중국산 에너지 인버터 신규 수입 제한·금지 조치를 검토 중이라는 예비 정책 신호입니다.",
        impact="태양광 인버터·전력변환장치, 미국 태양광 밸류체인, 전력망 보안, 중국 대체 공급망 | 돈 버는 능력·수급·시간표",
        point="인버터는 태양광 발전을 전력망에 연결하는 핵심 장비라 수입 금지가 공식화되면 미국 내 인버터/전력변환장치 업체의 가격결정력과 주문 기대, 중국산 부품 의존 리스크가 동시에 바뀔 수 있습니다.",
        counter="아직 FCC 공식 규칙·수입금지 대상·적용일·기존 모델 예외가 확정되지 않은 보도 단계입니다. 미국 업체 주가 반응이 먼저 나온 만큼 단기 과열일 수 있습니다.",
        sectors="태양광 인버터/전력변환장치, 전력기기/전력망 보안, 신재생에너지, 중국 대체 공급망",
        impacts=("돈 버는 능력", "수급", "시간표"),
        paths=("정책 타임라인", "공급망", "밸류체인", "수급"),
        follow_up="핵심은 FCC가 실제 규칙안을 내고 적용 대상을 중국산 인버터 전체, 신규 모델, 특정 통신 모듈 내장 장비 중 어디까지로 확정하느냐입니다. 한국장에서는 인버터 직접 종목보다 전력변환장치, ESS/전력기기, 태양광 부품, 전력망 보안 밸류체인으로 연결되는지 확인해야 합니다.",
    ),
    StoryRule(
        key="us_china_robotics_import_review",
        title="미 상무부, 중국산 로봇 수입 조사·추가 조치 가능성",
        google_queries=(
            "Politico Commerce Chinese robots imports investigation robotics subsidies",
            "Commerce Department Chinese robots import investigation robotics tariffs",
            "US Commerce Secretary Chinese robots review possible action Reuters Politico",
        ),
        required_groups=(
            ("commerce", "lutnick"),
            ("robot", "robotics"),
            ("china", "chinese"),
            ("import", "imports", "imported", "tariff", "tariffs", "action", "review", "investigation"),
        ),
        core="Politico 소식통 보도와 Reuters 재전파 기준, 미 상무부가 중국산 로봇 수입을 검토하고 추가 조치 가능성을 시사한 것으로 보도됨.",
        impact="로봇/스마트팩토리, 감속기/FA, 관세/중국 대체 공급망 | 시간표·수급·마진",
        point="관세·수입제한·미국 내 제조지원으로 번지면 한국 로봇/자동화 테마 수급과 중국 대체 밸류체인 기대를 자극할 수 있음.",
        counter="공식 상무부 발표 전이고 익명 소식통 기반 보도라 품목, 관세율, 시행일, 대출 조건, 대상 기업은 미확정.",
        sectors="로봇/스마트팩토리, 감속기/FA, 산업자동화, 관세/수출주, 중국 대체 공급망",
        impacts=("시간표", "수급", "돈 버는 능력"),
        paths=("정책 타임라인", "수급", "중국 대체 공급망"),
        follow_up="오늘 바뀐 것은 확정 매출이 아니라 정책 시간표·테마 수급입니다. 공식 상무부 발표, 관세/수입제한 품목, OSC 대출 조건을 후속 확인해야 합니다.",
    ),
    StoryRule(
        key="eu_korea_steel_safeguard_relief",
        title="EU, 한국산 철강 규제 완화 신호",
        google_queries=(
            "Reuters EU South Korea steel safeguard quota 19.7 46 regulation",
            "Bloomberg European Union South Korea steel quota 19.7 46 safeguard",
            "European Commission Korea steel safeguard quota 19.7 46",
            "\"한국산 철강\" \"46%\" \"19.7%\" EU 철강 규제 완화",
            "\"EU\" \"한국산 철강\" \"세이프가드\" \"19.7%\"",
        ),
        required_groups=(
            ("eu", "european union", "european commission", "유럽연합", "유럽", "eu집행위"),
            ("korea", "south korea", "korean", "한국", "한국산"),
            ("steel", "철강"),
            ("19.7", "19.7%", "46", "46%", "safeguard", "quota", "tariff", "regulation", "규제", "세이프가드", "쿼터", "관세", "완화"),
        ),
        core="EU가 한국산 철강에 적용되는 수입규제·세이프가드·쿼터 조건을 완화한다는 신뢰 보도/공식 신호가 확인된 사안.",
        impact="철강/강관/자동차강판, EU향 수출주, 관세·쿼터 정책 | 돈 버는 능력·수급·시간표",
        point="규제율·쿼터 부담이 낮아지면 EU향 철강 수출 물량, 가격경쟁력, 마진, 밸류체인 수급 기대가 동시에 바뀔 수 있음.",
        counter="보도 단계에서는 품목 범위, 적용 기간, 국가별 쿼터, 실제 관세율·세이프가드 문구, EU 관보 확정 여부가 미확인일 수 있음.",
        sectors="철강/강관, EU향 수출주, 자동차강판/조선후판, 관세·쿼터 정책",
        impacts=("돈 버는 능력", "수급", "시간표"),
        paths=("이익", "무역규제", "정책 타임라인", "수급"),
        follow_up="핵심은 규제 완화가 실제 EU 관보·집행위 문서와 품목별 쿼터로 확정되는지입니다. 포스코홀딩스·현대제철·세아제강 등 철강/강관 수출주와 EU향 노출 종목의 가격·수급 반응을 재확인해야 합니다.",
    ),
    StoryRule(
        key="eu_korea_trade_regulation_watch",
        title="EU, 한국 영향 무역규제·관세·쿼터 정책 신호",
        google_queries=(
            "Reuters European Union South Korea tariff quota safeguard anti-dumping regulation",
            "Bloomberg EU South Korea trade regulation tariff quota customs duty",
            "European Commission South Korea trade regulation tariff quota safeguard",
            "\"EU\" \"South Korea\" tariff quota safeguard anti-dumping",
            "\"유럽연합\" \"한국\" 관세 쿼터 세이프가드 반덤핑 규제",
        ),
        required_groups=(
            ("eu", "european union", "european commission", "유럽연합", "유럽", "eu집행위"),
            ("korea", "south korea", "korean", "한국", "한국산"),
            ("tariff", "quota", "safeguard", "anti-dumping", "duty", "customs", "regulation", "import", "export", "관세", "쿼터", "세이프가드", "반덤핑", "규제", "수입", "수출", "완화", "강화"),
        ),
        core="EU발 무역규제·관세·쿼터·반덤핑 정책이 한국 수출 품목의 가격경쟁력과 물량 조건을 바꿀 수 있는 신뢰 보도/공식 신호입니다.",
        impact="EU향 수출주, 철강/화학/배터리/자동차/조선, 관세·쿼터 정책 | 돈 버는 능력·수급·시간표",
        point="품목·세율·쿼터·시행일이 공식화되면 한국 수출기업의 마진, 주문 이전, 밸류체인 수급 기대가 동시에 바뀔 수 있습니다.",
        counter="EU 공식 문서 전에는 품목 범위, 국가별 쿼터, 적용 기간, 예외 조항이 달라질 수 있어 확정 매출로 볼 수 없습니다.",
        sectors="EU 무역규제/관세, 철강/화학/배터리/자동차/조선, 한국 수출주",
        impacts=("돈 버는 능력", "수급", "시간표"),
        paths=("이익", "무역규제", "정책 타임라인", "수급"),
        follow_up="철강에 한정하지 말고 EU 관보·집행위·의회·이사회 문서에서 한국 품목의 세율, 쿼터, 시행일, 예외 조항을 확인해야 합니다.",
    ),
    StoryRule(
        key="eu_korea_green_industry_watch",
        title="EU, 한국 영향 탄소·배터리·친환경 산업 규제 신호",
        google_queries=(
            "Reuters EU South Korea CBAM battery regulation critical raw materials due diligence",
            "Bloomberg European Union Korea carbon border battery regulation supply chain",
            "European Commission Korea CBAM battery regulation critical raw materials due diligence",
            "\"EU\" \"Korea\" CBAM battery regulation critical raw materials",
            "\"유럽연합\" \"한국\" 탄소국경 배터리규정 핵심원자재 공급망실사",
        ),
        required_groups=(
            ("eu", "european union", "european commission", "유럽연합", "유럽", "eu집행위"),
            ("korea", "south korea", "korean", "한국", "한국산"),
            ("cbam", "carbon border", "battery regulation", "critical raw materials", "due diligence", "reach", "recycling", "emissions", "탄소국경", "배터리규정", "핵심원자재", "공급망실사", "재활용", "배출", "환경규제"),
        ),
        core="EU의 탄소국경조정, 배터리규정, 핵심원자재·공급망 실사 정책이 한국 제조사의 원가·인증·수출 시간표를 바꿀 수 있는 신뢰 보도/공식 신호입니다.",
        impact="배터리/2차전지, 철강/화학, 자동차/부품, 탄소국경·공급망 정책 | 돈 버는 능력·할인율·시간표",
        point="인증·재활용·탄소비용·원산지 요건이 강화되면 한국 기업의 유럽 매출 마진과 CAPEX, 고객사 공급망 편입 조건이 바뀝니다.",
        counter="시행 유예, 세부 위임규정, 국가별 적용 방식이 남아 있으면 단기 실적 영향은 제한될 수 있습니다.",
        sectors="배터리/2차전지, 철강/화학, 자동차/부품, 탄소국경/공급망",
        impacts=("돈 버는 능력", "할인율", "시간표"),
        paths=("원가", "공급망", "정책 타임라인", "규제 리스크"),
        follow_up="EU 환경·산업 규제는 품목별 인증, 탄소비용, 원산지·재활용 요건이 숫자로 나오는 순간 한국 기업의 마진 가정이 바뀝니다.",
    ),
    StoryRule(
        key="eu_korea_digital_security_watch",
        title="EU, 한국 영향 디지털·AI·플랫폼·사이버 규제 신호",
        google_queries=(
            "Reuters EU South Korea AI Act Digital Markets Act cybersecurity data privacy cloud",
            "Bloomberg European Union Korea AI Act platform regulation cybersecurity data",
            "European Commission Korea AI Act DSA DMA cybersecurity cloud regulation",
            "\"EU\" \"Korea\" \"AI Act\" cybersecurity cloud data platform",
            "\"유럽연합\" \"한국\" AI법 플랫폼 사이버보안 개인정보 클라우드",
        ),
        required_groups=(
            ("eu", "european union", "european commission", "유럽연합", "유럽", "eu집행위"),
            ("korea", "south korea", "korean", "한국", "한국산"),
            ("ai act", "digital markets act", "digital services act", "cybersecurity", "data", "privacy", "cloud", "platform", "dma", "dsa", "인공지능법", "ai법", "플랫폼", "사이버보안", "개인정보", "클라우드", "데이터"),
        ),
        core="EU 디지털·AI·플랫폼·사이버 규제가 한국 플랫폼, 클라우드, 전자·보안 기업의 유럽 사업 조건과 준수비용을 바꿀 수 있는 신뢰 보도/공식 신호입니다.",
        impact="플랫폼/인터넷, AI/클라우드, 사이버보안, 전자/반도체 | 시간표·할인율·돈 버는 능력",
        point="규제 대상, 준수기한, 과징금·인증 의무가 구체화되면 유럽 매출 노출 기업의 비용, 제품 출시 일정, 밸류에이션 할인율이 바뀝니다.",
        counter="EU 규정이더라도 한국 기업의 유럽 매출 비중과 직접 적용 여부가 낮으면 한국장 가격 변수는 약할 수 있습니다.",
        sectors="플랫폼/인터넷, AI/클라우드, 사이버보안, 반도체/전자",
        impacts=("시간표", "할인율", "돈 버는 능력"),
        paths=("규제 준수", "정책 타임라인", "원가", "밸류체인"),
        follow_up="디지털 규제는 실제 적용 대상 기업, 과징금·인증 의무, 시행기한이 확인될 때만 고충격 재료로 남겨야 합니다.",
    ),
    StoryRule(
        key="eu_korea_sanctions_export_watch",
        title="EU, 한국 영향 제재·수출통제·공급망 정책 신호",
        google_queries=(
            "Reuters EU South Korea sanctions export controls Russia China supply chain semiconductor",
            "Bloomberg European Union Korea sanctions export control critical technology supply chain",
            "European Commission Korea sanctions export control Russia China critical technology",
            "\"EU\" \"Korea\" sanctions export controls semiconductor supply chain",
            "\"유럽연합\" \"한국\" 제재 수출통제 공급망 반도체 러시아 중국",
        ),
        required_groups=(
            ("eu", "european union", "european commission", "유럽연합", "유럽", "eu집행위"),
            ("korea", "south korea", "korean", "한국", "한국산"),
            ("sanction", "sanctions", "export control", "restricted", "dual-use", "russia", "china", "supply chain", "critical technology", "semiconductor", "제재", "수출통제", "이중용도", "러시아", "중국", "공급망", "첨단기술", "반도체"),
        ),
        core="EU 제재·수출통제·공급망 정책이 한국 기업의 판매 가능 국가, 우회수요, 소재·장비 조달 조건을 바꿀 수 있는 신뢰 보도/공식 신호입니다.",
        impact="반도체/장비, 방산/조선, 에너지/원자재, 공급망 | 돈 버는 능력·수급·시간표",
        point="대상 국가·품목·기업이 확정되면 한국 밸류체인의 매출처 제한, 대체수요, 재고·물류 비용, 수주 시간표가 바뀝니다.",
        counter="제재 패키지 초안이나 정치 발언 단계에서는 최종 품목, 예외 라이선스, 동맹국 적용 방식이 달라질 수 있습니다.",
        sectors="반도체/장비, 방산/조선, 에너지/원자재, 공급망",
        impacts=("돈 버는 능력", "수급", "시간표"),
        paths=("수출통제", "공급망", "정책 타임라인", "수급"),
        follow_up="제재·수출통제는 최종 관보, 대상 품목·기업, 예외 라이선스, 한국 기업의 직접 노출을 확인해야 고충격으로 인정합니다.",
    ),
)


def now_kst() -> dt.datetime:
    return dt.datetime.now(tz=KST)


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def fetch_text(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "KHS-trusted-policy-news-watch contact=github-actions",
            "Accept": "application/rss+xml, text/xml, text/html;q=0.8, */*;q=0.5",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode(resp.headers.get_content_charset() or "utf-8", errors="replace")


def google_news_rss_url(query: str) -> str:
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    )


def parse_pub_date(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(KST)


def source_name(item: ET.Element) -> str:
    source = item.find("source")
    if source is not None:
        return clean_text(source.text)
    title = clean_text(item.findtext("title"))
    if " - " in title:
        return title.rsplit(" - ", 1)[-1].strip()
    return ""


def source_key(name: str) -> str:
    return clean_text(name).lower()


def is_trusted_source(name: str) -> bool:
    key = source_key(name)
    return key in TRUSTED_SOURCES


def trusted_wire_source(text: str) -> str:
    low = text.lower()
    if "reuters" in low:
        return "Reuters"
    if "bloomberg" in low:
        return "Bloomberg"
    return ""


def is_trusted_wire_relay(publisher: str, text: str) -> bool:
    key = source_key(publisher)
    return key in TRUSTED_WIRE_RELAY_SOURCES and bool(trusted_wire_source(text))


def has_required_terms(text: str, rule: StoryRule) -> bool:
    low = text.lower()
    return all(any(term.lower() in low for term in group) for group in rule.required_groups)


def load_seen() -> dict:
    if not SEEN_PATH.exists():
        return {"seen": {}, "updated_at_kst": ""}
    try:
        return json.loads(SEEN_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"seen": {}, "updated_at_kst": ""}


def collect_rule_items(rule: StoryRule, now: dt.datetime) -> list[dict]:
    items: list[dict] = []
    seen_links: set[str] = set()
    for query in rule.google_queries:
        try:
            raw = fetch_text(google_news_rss_url(query))
        except Exception as exc:
            print(f"trusted_policy_news=query_failed key={rule.key} error={type(exc).__name__}: {exc}")
            continue
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            print(f"trusted_policy_news=parse_failed key={rule.key} error={exc}")
            continue
        for item in root.findall("./channel/item"):
            title = clean_text(item.findtext("title"))
            link = clean_text(item.findtext("link"))
            publisher = source_name(item)
            published = parse_pub_date(item.findtext("pubDate"))
            description = clean_text(item.findtext("description"))
            haystack = " ".join([title, publisher, description])
            wire_source = trusted_wire_source(haystack)
            if not title or not link or not published:
                continue
            if link in seen_links:
                continue
            if not is_trusted_source(publisher) and not is_trusted_wire_relay(publisher, haystack):
                continue
            if (now - published).total_seconds() / 3600 > MAX_AGE_HOURS:
                continue
            if not has_required_terms(haystack, rule):
                continue
            seen_links.add(link)
            display_source = publisher
            priority_key = source_key(publisher)
            if wire_source and not is_trusted_source(publisher):
                display_source = f"{publisher} ({wire_source} 보도 인용)"
                priority_key = source_key(wire_source)
            items.append(
                {
                    "title": title,
                    "link": link,
                    "source": display_source,
                    "published_kst": published.isoformat(timespec="seconds"),
                    "priority": SOURCE_PRIORITY.get(priority_key, 99),
                }
            )
    return sorted(items, key=lambda item: (item["priority"], item["published_kst"]))


def fingerprint(rule: StoryRule, items: list[dict]) -> str:
    first_day = ""
    if items:
        first_day = str(items[0].get("published_kst", ""))[:10]
    raw = f"{FORMAT_VERSION}:{rule.key}:{first_day}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def render_alert(rule: StoryRule, items: list[dict], now: dt.datetime) -> str:
    source_bits = []
    for item in items[:3]:
        source_bits.append(
            f"[{item['source']}]({item['link']}) · 원천시각 {item['published_kst']}"
        )
    sources = " / ".join(source_bits) if source_bits else "확인 불가"
    source_names = ", ".join(dict.fromkeys(str(item["source"]) for item in items[:3]))
    explain_item = {
        "title": rule.title,
        "source": source_names,
        "summary": f"{rule.core} {rule.point}",
        "status": "공식 확인 전",
        "policy_plain_summary": rule.core,
        "investment_view": rule.point,
        "counter": rule.counter,
        "sectors": rule.sectors,
        "impacts": list(rule.impacts),
        "paths": list(rule.paths),
        "eu_korea_policy_watch": rule.key.startswith("eu_korea_"),
        "eu_policy_category": rule.key if rule.key.startswith("eu_korea_") else "",
        "eu_korea_steel_policy_watch": rule.key == "eu_korea_steel_safeguard_relief",
        "trusted_policy_rule_key": rule.key,
        "matched": {rule.key: ["EU", "Korea", "policy"] if rule.key.startswith("eu_korea_") else ["trusted policy news"]},
    }
    ensure_explained(explain_item)

    lines = [
        f"🚨 KHS 신뢰외신 정책·규제 고충격 워치 · {now:%Y년 %m월 %d일 %H:%M KST}",
        "공식 발표 전 정책 뉴스 1건 확인",
        "",
        f"## 1. [상·공식 확인 전] {rule.title}",
        f"- 확인 상태: 공식 원문/후속 문서 확인 전. 신뢰 소스 확인: {source_names or '확인 불가'}.",
        *explanation_lines(explain_item),
        f"- 출처: {sources} · 조회 {now:%H:%M KST}",
        "",
        f"💡 판단: {rule.follow_up}",
        "",
        "투자 조언이 아닌 참고용 정책·규제 알림입니다.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    now = now_kst()
    OUT_DIR.mkdir(exist_ok=True)
    DATA_DIR.mkdir(exist_ok=True)
    seen_payload = load_seen()
    seen = seen_payload.setdefault("seen", {})

    alerts: list[dict] = []
    for rule in STORY_RULES:
        items = collect_rule_items(rule, now)
        if not items:
            continue
        fp = fingerprint(rule, items)
        if fp in seen:
            continue
        alerts.append({"rule": rule, "items": items, "fingerprint": fp})

    if not alerts:
        for path in (ALERT_PATH, TITLE_PATH, ALERTS_JSON_PATH):
            if path.exists():
                path.unlink()
        print("trusted_policy_news_alerts=0")
        return 0

    top = alerts[0]
    report = render_alert(top["rule"], top["items"], now)
    ALERT_PATH.write_text(report, encoding="utf-8")
    TITLE_PATH.write_text(f"KHS 신뢰외신 정책 워치: [상·공식 확인 전] {top['rule'].title}\n", encoding="utf-8")
    ALERTS_JSON_PATH.write_text(
        json.dumps(
            [
                {
                    "key": alert["rule"].key,
                    "title": alert["rule"].title,
                    "status": "공식 확인 전",
                    "items": alert["items"],
                    "fingerprint": alert["fingerprint"],
                }
                for alert in alerts
            ],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    for alert in alerts:
        seen[alert["fingerprint"]] = {
            "key": alert["rule"].key,
            "title": alert["rule"].title,
            "first_seen_kst": now.isoformat(timespec="seconds"),
            "status": "공식 확인 전",
            "sources": [item["source"] for item in alert["items"][:3]],
        }
    seen_payload["updated_at_kst"] = now.isoformat(timespec="seconds")
    SEEN_PATH.write_text(json.dumps(seen_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"trusted_policy_news_alerts={len(alerts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
