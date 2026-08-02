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

try:
    from khs_policy_alert_explainer import ensure_explained
except ImportError:  # pragma: no cover - supports module-style local tests.
    from scripts.khs_policy_alert_explainer import ensure_explained
try:
    from khs_compact_text import concise_text
except ImportError:  # pragma: no cover - supports module-style local tests.
    from scripts.khs_compact_text import concise_text

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
    "u.s. department of state",
    "us department of state",
    "united states department of state",
    "state department",
    "department of state",
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
    "world health organization",
    "world health organization (who)",
    "who",
    "world meteorological organization",
    "world meteorological organization (wmo)",
    "wmo",
}

SOURCE_PRIORITY = {
    "european commission": 0,
    "official journal of the european union": 0,
    "u.s. department of state": 0,
    "us department of state": 0,
    "united states department of state": 0,
    "state department": 0,
    "department of state": 0,
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
    "world health organization": 0,
    "world health organization (who)": 0,
    "who": 0,
    "world meteorological organization": 0,
    "world meteorological organization (wmo)": 0,
    "wmo": 0,
    "politico": 8,
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
    trusted_sources: tuple[str, ...] = ()


STORY_RULES = (
    StoryRule(
        key="china_mofcom_export_controls_tariffs",
        title="중국 상무부, 전략 품목 수출금지·관세 정책 변화",
        google_queries=(
            "Reuters China Ministry of Commerce export ban suspension tariff helium",
            "Bloomberg China MOFCOM export controls tariff rare earth helium gallium",
            "China commerce ministry temporarily bans exports helium Reuters",
            "Reuters China export licensing dual-use items graphite germanium antimony tungsten",
            "Bloomberg China anti-dumping countervailing tariff semiconductor battery materials",
        ),
        required_groups=(
            ("china", "chinese", "mofcom", "ministry of commerce", "商务部"),
            (
                "export ban", "export bans", "suspend exports", "suspended exports",
                "suspend", "suspends", "suspended", "ban", "bans", "banned",
                "export control", "export controls", "export restriction", "export licensing",
                "tariff", "tariffs", "anti-dumping", "antidumping", "countervailing",
                "出口管制", "暂停出口", "停止出口", "禁止出口", "关税", "反倾销", "反补贴",
            ),
        ),
        core="중국 상무부가 전략 품목의 수출 금지·일시 중단·허가제 또는 관세·반덤핑 조치를 발표하거나 준비한다는 신뢰외신 정책 신호입니다.",
        impact="중국 수출통제/핵심소재, 반도체·디스플레이·산업가스, 2차전지·방산 공급망 | 매출·마진·현금흐름·수급·시간표",
        point="적용 품목과 국가가 확정되면 중국산 원료 의존 업체의 조달가격·재고·생산계획과 비중국 대체 공급자의 주문 기대가 동시에 바뀔 수 있습니다.",
        counter="보도 단계이거나 수출 허가 예외·기존 계약 유예·대상국 제한이 있으면 실제 공급 충격은 작을 수 있습니다.",
        sectors="중국 수출통제/핵심소재, 반도체/HBM 공정가스, 디스플레이, 산업가스, 2차전지, 방산/전력전자",
        impacts=("매출·마진·현금흐름", "수급", "시간표"),
        paths=("공급·수요", "원자재 비용", "공급망", "정책 타임라인"),
        follow_up="중국 상무부 공식 공고에서 품목·HS코드·대상국·시행일·예외 허가를 확인하고, 현물가격·리드타임·한국 기업의 중국산 조달 비중이 실제로 변하는지 재확인합니다.",
    ),
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
        key="us_fcc_security_import_restriction",
        title="미국 FCC, 국가안보형 장비 수입제한·금지 정책 보도",
        google_queries=(
            "Reuters FCC national security import ban foreign equipment",
            "Bloomberg FCC national security import restriction equipment",
            "FCC foreign equipment ban national security Reuters Bloomberg",
            "FCC covered list import ban national security Reuters",
            "FCC energy inverter satellite telecom module equipment ban national security",
        ),
        required_groups=(
            ("fcc", "federal communications commission"),
            ("national security", "security", "covered list", "ban", "barred", "restrict", "restriction", "prohibit", "import", "imports"),
            ("equipment", "device", "devices", "module", "modules", "inverter", "inverters", "satellite", "telecom", "communications", "grid", "energy", "drone", "router", "camera", "connected vehicle"),
        ),
        core="Reuters·Bloomberg 등 신뢰외신 기준, 미국 FCC가 국가안보를 이유로 외국산 장비의 수입·인증·판매를 제한할 수 있다는 예비 정책 신호입니다.",
        impact="전력망/통신장비/위성/보안장비/전력변환장치, 중국 대체 공급망 | 돈 버는 능력·수급·시간표",
        point="FCC 장비 제한은 단순 통신 규제가 아니라 특정 외국산 장비를 미국 시장에서 배제하는 수급 재편 재료가 될 수 있습니다. 적용 장비가 전력망·에너지·통신모듈·위성·보안장비로 넓어지면 국내 밸류체인도 재평가될 수 있습니다.",
        counter="신뢰외신 보도 단계에서는 FCC 공식 규칙안, 적용 장비, 기존 인증 장비 예외, 시행일이 확정되지 않았습니다. 특정 기업 매출로 연결하려면 미국향 공급망 노출과 수주 근거가 필요합니다.",
        sectors="전력망/통신장비/위성/보안장비/전력변환장치, 중국 대체 공급망",
        impacts=("돈 버는 능력", "수급", "시간표"),
        paths=("정책 타임라인", "공급망", "밸류체인", "수급"),
        follow_up="FCC 보도는 회의 공지·보고양식이면 제외하고, 국가안보·수입금지·장비인증·Covered List·외국산 장비 배제 중 하나가 직접 붙을 때만 고충격 후보로 봐야 합니다. 공식 규칙안, 적용 장비, 한국 기업의 미국향 공급망 노출을 즉시 확인해야 합니다.",
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
        core="EU의 탄소국경조정, 배터리규정, 핵심원자재·공급망 실사 정책이 한국 제조사의 원가·인증·수출 시간표를 바꿀 수 있는 신뢰 보도/공식…16880 tokens truncated…   }
    if any(
        term in low
        for term in (
            "cut interest rates",
            "cut rates",
            "lower interest rates",
            "lower rates",
            "rate cut",
            "rates should be lower",
            "may cut interest rates",
        )
    ):
        chair = "연준 의장이 " if any(term in low for term in ("fed chair", "chair may", "chairman")) else ""
        return {
            **common,
            "revision": "trump-rate-cut-ko-v1",
            "title": "트럼프, 연준 금리 인하 필요성 강조",
            "core": f"트럼프는 {chair}금리 인하에 나서야 한다고 말했습니다.",
            "investment": "정책 압박이 국채금리와 달러를 움직이면 성장주 할인율과 원/달러가 반응할 수 있습니다.",
            "korea": "원/달러, 외국인 수급과 고밸류 성장주만 확인합니다.",
            "impacts": "밸류에이션/할인율, 수급",
            "paths": "금리, 환율, 외국인 수급",
            "sectors": "금리·환율 민감주, 성장주",
            "failure": "연준 반응과 미국채 금리·DXY 변화가 없으면 발언성 재료로 끝납니다.",
        }
    if any(term in low for term in ("rate hike", "raise interest rates", "higher interest rates")):
        return {
            **common,
            "revision": "trump-rate-hike-ko-v1",
            "title": "트럼프, 연준 금리 인상 가능성 언급",
            "core": "트럼프는 연준의 금리 인상 가능성에 관한 입장을 밝혔습니다.",
            "investment": "금리 인상 기대는 국채금리와 달러, 성장주 할인율을 높일 수 있습니다.",
            "korea": "원/달러, 외국인 수급과 고밸류 성장주만 확인합니다.",
            "impacts": "밸류에이션/할인율, 수급",
            "paths": "금리, 환율, 외국인 수급",
            "sectors": "금리·환율 민감주, 성장주",
            "failure": "연준 반응과 미국채 금리·DXY 변화가 없으면 발언성 재료로 끝납니다.",
        }
    if "south korea" in low or "usfk" in low or "burden sharing" in low:
        return {
            **common,
            "title": "트럼프, 한국·주한미군·방위비 관련 발언: 지정학·방산 변수",
            "core": "트럼프가 한국, 주한미군 또는 방위비와 관련한 정책 방향을 언급한 보도입니다.",
            "investment": "실제 협상 요구나 주둔 조정은 지정학 위험프리미엄과 방산 수요 기대를 바꿀 수 있습니다.",
            "korea": "K-방산과 지정학 민감주를 보되, 구체 협상안·예산·주둔 계획 전에는 실적 연결을 단정하지 않습니다.",
            "impacts": "밸류에이션/할인율, 수급, 시간표",
            "paths": "지정학 리스크, 방산 수요, 정책 타임라인",
            "sectors": "방산/지정학",
            "failure": "한미 공동발표, 방위비 협상안, 주둔·조달 계획이 없으면 정치 발언으로 약화됩니다.",
        }
    if "nato" in low or "allies" in low:
        return {
            **common,
            "title": "트럼프, NATO·방위비 관련 발언: 방산 수요·동맹 리스크",
            "core": "트럼프의 NATO·동맹국 방위비 관련 발언으로 방산 조달과 동맹 정책의 불확실성이 부각된 보도입니다.",
            "investment": "방위비 확대가 예산·조달로 이어질 때만 방산 매출과 수주 가시성이 실제로 바뀝니다.",
            "korea": "K-방산은 미국·유럽 조달, 폴란드 등 수출계약의 후속 예산·서명 여부를 중심으로 확인합니다.",
            "impacts": "매출·마진·현금흐름, 수급, 시간표",
            "paths": "방산 수요, 정책 타임라인, 계약 가시성",
            "sectors": "방산/지정학",
            "failure": "예산·조달 공고·계약 서명이 없으면 방산 테마 수급으로 끝납니다.",
        }
    if any(term in low for term in ("ukraine", "russia", "putin", "zelenskiy")):
        return {
            **common,
            "title": "트럼프, 우크라이나·러시아 관련 발언: 제재·전쟁 시간표 변수",
            "core": "트럼프의 우크라이나·러시아 관련 발언으로 제재, 휴전, 에너지·방산 리스크의 시간표가 흔들릴 수 있다는 보도입니다.",
            "investment": "제재·휴전의 실제 진전 여부는 에너지·원자재 가격과 방산 수요 기대를 바꿀 수 있습니다.",
            "korea": "방산·에너지·해운만 직접 확인하며, 공식 협상문·제재 변경 전에는 테마 확장을 제한합니다.",
            "impacts": "밸류에이션/할인율, 수급, 시간표",
            "paths": "지정학 리스크, 제재, 정책 타임라인",
            "sectors": "방산/지정학, 에너지/해운",
            "failure": "공식 협상·제재 문서와 원자재·방산 반응이 없으면 발언성 재료로 약화됩니다.",
        }
    return None


def korean_trump_story_title(title: str) -> str:
    profile = trump_story_profile(title)
    return str((profile or {}).get("title") or "트럼프 직접 발언: 세부 내용 확인 필요")


def item_story_profile(rule: StoryRule, items: list[dict]) -> dict[str, object] | None:
    if not items:
        return None
    title = str(items[0].get("title", ""))
    if rule.key == "trump_direct_policy_remarks_watch":
        return trump_story_profile(title)
    if rule.key == "global_extreme_heat_mortality_watch":
        return heat_mortality_story_profile(title)
    if rule.key == "iran_hormuz_military_escalation":
        return iran_hormuz_story_profile(title)
    return None


def story_display_title(rule: StoryRule, items: list[dict]) -> str:
    profile = item_story_profile(rule, items)
    if profile:
        return str(profile["title"])
    return rule.title


def story_summary_lines(rule: StoryRule, items: list[dict], limit: int = 3) -> list[str]:
    if rule.key != "trump_direct_policy_remarks_watch":
        return []
    lines: list[str] = []
    for idx, item in enumerate(items[:limit], start=1):
        lines.append(
            f"- 주요 보도 {idx}: {korean_trump_story_title(str(item.get('title', '')))} "
            f"({item.get('source', '확인 불가')}, {item.get('published_kst', '시각 확인 불가')})"
        )
    return lines


def alert_latest_kst(alert: dict) -> str:
    items = alert.get("items") or []
    return max((str(item.get("published_kst", "")) for item in items), default="")


def source_bits(items: list[dict], limit: int = 1) -> str:
    bits = [
        f"[{item['source']}]({item['link']}) · 원천시각 {item['published_kst']}"
        for item in items[:limit]
    ]
    return " / ".join(bits) if bits else "확인 불가"


def short_text(value: object, limit: int = 120) -> str:
    text = clean_text(str(value or ""))
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def split_display_values(value: object) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [clean_text(str(part)) for part in value if clean_text(str(part))]
    text = clean_text(str(value or ""))
    if not text:
        return []
    return [part.strip() for part in re.split(r"[,|]", text) if part.strip()]


def join_short_values(value: object, max_items: int = 3, fallback: str = "확인 필요") -> str:
    values = split_display_values(value)
    if not values:
        return fallback
    return ", ".join(values[:max_items])


def compact_core(rule: StoryRule, items: list[dict]) -> str:
    profile = item_story_profile(rule, items)
    if profile:
        return str(profile["core"])
    return short_text(rule.core, 125)


def compact_investment_view(rule: StoryRule, items: list[dict]) -> str:
    profile = item_story_profile(rule, items)
    if profile:
        return str(profile["investment"])
    return short_text(rule.point, 125)


def compact_korea_market_view(rule: StoryRule, items: list[dict]) -> str:
    profile = item_story_profile(rule, items)
    if profile:
        return str(profile["korea"])
    return short_text(f"{join_short_values(rule.sectors, max_items=3)} 중심으로 공식 원문과 한국 기업 직접 노출만 확인합니다.", 125)


def compact_priced_in(rule: StoryRule, items: list[dict]) -> str:
    profile = item_story_profile(rule, items)
    if profile:
        return str(profile["priced_in"])
    if rule.key == "iran_hormuz_military_escalation":
        return "낮음~중간. 신규 상선 피격과 재공격은 휴전 붕괴 확률을 다시 높이는 새 정보입니다."
    if rule.key == "trump_direct_policy_remarks_watch":
        return "낮음~중간. 발언은 빠르게 반영되지만 공식 문서 전에는 되돌림도 빠릅니다."
    return "낮음~중간. 공식 문서·시행일·적용 대상 확인 전까지는 예비 재료입니다."


def compact_failure_signal(rule: StoryRule, items: list[dict]) -> str:
    profile = item_story_profile(rule, items)
    if profile:
        return str(profile["failure"])
    if rule.key == "iran_hormuz_military_escalation":
        return "미 국방부·CENTCOM 후속, 통항 감소, 유가·운임·환율 반응이 없으면 단발성 충돌로 약화됩니다."
    if rule.key == "trump_direct_policy_remarks_watch":
        return "백악관/부처 후속, 유가·환율·운임·방산 티커 반응이 없으면 단발성 발언으로 제외합니다."
    return "공식 원문, 시행일, 적용 대상, 한국 기업 직접 노출이 확인되지 않으면 제외합니다."


def compact_counter(rule: StoryRule, items: list[dict]) -> str:
    profile = item_story_profile(rule, items)
    if profile:
        return str(profile["counter"])
    if rule.key == "iran_hormuz_military_escalation":
        return "단발성 보복 뒤 추가 공격이 멈추고 상선 통항이 유지되면 유가·운임 충격은 빠르게 되돌릴 수 있습니다."
    return "공식 문서·시행일·적용 범위가 아직 없다는 점입니다."


def is_trump_iran_item(rule: StoryRule, items: list[dict]) -> bool:
    if rule.key != "trump_direct_policy_remarks_watch" or not items:
        return False
    title = clean_story_title(str(items[0].get("title", ""))).lower()
    return "iran" in title or "이란" in title


def compact_impacts(rule: StoryRule, items: list[dict]) -> str:
    profile = item_story_profile(rule, items)
    if profile:
        return str(profile["impacts"])
    mapped = ["매출·마진·현금흐름" if value == "돈 버는 능력" else value for value in split_display_values(rule.impacts)]
    return join_short_values(mapped, max_items=4, fallback="의사결정 영향 제한적")


def compact_paths(rule: StoryRule, items: list[dict]) -> str:
    profile = item_story_profile(rule, items)
    if profile:
        return str(profile["paths"])
    return join_short_values(rule.paths, max_items=4, fallback="정책 타임라인")


def compact_sectors(rule: StoryRule, items: list[dict]) -> str:
    profile = item_story_profile(rule, items)
    if profile:
        return str(profile["sectors"])
    return join_short_values(rule.sectors, max_items=3, fallback="정책/규제 일반")


def compact_policy_core(value: object, fallback: object = "", limit: int = 50) -> str:
    text = re.sub(r"\s+", " ", str(value or fallback or "확인 불가")).strip()
    if len(text) <= limit:
        return text
    for match in re.finditer(r".+?[.!?](?=\s|$)", text):
        sentence = match.group(0).strip()
        if 8 <= len(sentence) <= limit:
            return sentence
    room = max(8, limit - 4)
    head = text[: room + 1]
    boundary = max(
        head.rfind(" "),
        head.rfind(","),
        head.rfind("·"),
        head.rfind(";"),
        head.rfind(":"),
    )
    if boundary < int(room * 0.6):
        boundary = room
    return head[:boundary].rstrip(" ,·;:.") + "입니다."


def compact_explanation_lines(rule: StoryRule, items: list[dict], explain_item: dict) -> list[str]:
    ensure_explained(explain_item)
    title = story_display_title(rule, items)
    core = compact_policy_core(compact_core(rule, items), fallback=title)
    return [f"- 핵심: {core}"]


def render_alert_section(rule: StoryRule, items: list[dict], now: dt.datetime, index: int, source_limit: int = 1) -> list[str]:
    display_title = story_display_title(rule, items)
    sources = source_bits(items, source_limit)
    source_names = ", ".join(dict.fromkeys(str(item["source"]) for item in items[:3]))
    matched = {rule.key: ["EU", "Korea", "policy"] if rule.key.startswith("eu_korea_") else ["trusted policy news"]}
    if rule.key == "us_japan_korea_smr_moc_state_watch":
        matched["state_smr_moc_policy"] = ["moc", "smr", "samsung c&t", "bwrx-300"]
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
        "matched": matched,
    }
    ensure_explained(explain_item)

    return [
        f"{index}. [상·공식 확인 전] {display_title}",
        f"- 확인 상태: 공식 원문/후속 문서 확인 전. 신뢰 소스 확인: {source_names or '확인 불가'}.",
        *compact_explanation_lines(rule, items, explain_item),
        f"- 출처: {sources} · 조회 {now:%H:%M KST}",
        "",
    ]


def render_alert(rule: StoryRule, items: list[dict], now: dt.datetime) -> str:
    lines = [
        f"{now:%Y년 %m월 %d일 %H:%M KST}",
        "공식 발표 전 정책 뉴스 1건 확인",
        "",
        *render_alert_section(rule, items, now, index=1, source_limit=3),
        "투자 조언이 아닌 참고용 정책·규제 알림입니다.",
    ]
    return "\n".join(lines) + "\n"


def render_alert_bundle(alerts: list[dict], now: dt.datetime, limit: int = 3) -> str:
    selected = alerts[:limit]
    lines = [
        f"{now:%Y년 %m월 %d일 %H:%M KST}",
        f"공식 발표 전 정책 뉴스 {len(selected)}건 확인",
        "",
    ]
    for idx, alert in enumerate(selected, start=1):
        lines.extend(render_alert_section(alert["rule"], alert["items"], now, index=idx, source_limit=1))
    lines.append("투자 조언이 아닌 참고용 정책·규제 알림입니다.")
    return "\n".join(lines) + "\n"


def main() -> int:
    now = now_kst()
    OUT_DIR.mkdir(exist_ok=True)
    DATA_DIR.mkdir(exist_ok=True)
    seen_payload = load_seen()
    seen = seen_payload.setdefault("seen", {})

    alerts: list[dict] = []
    for rule in STORY_RULES:
        if rule.key.startswith("_disabled_"):
            continue
        items = collect_rule_items(rule, now)
        for alert_items in alert_item_groups(rule, items):
            alert_items = unseen_items_for_rule(rule, alert_items, seen)
            if not alert_items:
                continue
            fp = story_event_fingerprint(rule, alert_items)
            if fp in seen:
                continue
            alerts.append(
                {
                    "rule": rule,
                    "items": alert_items,
                    "fingerprint": fp,
                    "legacy_fingerprint": fingerprint(rule, alert_items),
                }
            )

    if not alerts:
        for path in (ALERT_PATH, TITLE_PATH, ALERTS_JSON_PATH):
            if path.exists():
                path.unlink()
        print("trusted_policy_news_alerts=0")
        return 0

    alerts.sort(key=alert_latest_kst, reverse=True)
    selected_alerts = alerts[:3]
    top = selected_alerts[0]
    extra_count = max(0, len(selected_alerts) - 1)
    title_suffix = f" 외 {extra_count}건" if extra_count else ""
    report = render_alert_bundle(selected_alerts, now)
    ALERT_PATH.write_text(report, encoding="utf-8")
    TITLE_PATH.write_text(
        f"신뢰외신 정책 워치: [상·공식 확인 전] {story_display_title(top['rule'], top['items'])}{title_suffix}\n",
        encoding="utf-8",
    )
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
        seen_entry = {
            "key": alert["rule"].key,
            "title": alert["rule"].title,
            "first_seen_kst": now.isoformat(timespec="seconds"),
            "status": "공식 확인 전",
            "sources": [item["source"] for item in alert["items"][:3]],
        }
        seen[alert["fingerprint"]] = seen_entry
        seen[alert["legacy_fingerprint"]] = seen_entry
    seen_payload["updated_at_kst"] = now.isoformat(timespec="seconds")
    SEEN_PATH.write_text(json.dumps(seen_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"trusted_policy_news_alerts={len(alerts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
