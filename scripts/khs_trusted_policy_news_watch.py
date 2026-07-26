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
    StoryRule(
        key="global_extreme_heat_mortality_watch",
        title="신뢰외신, 폭염 사망·기후 재난의 전력·식량 영향 보도",
        google_queries=(
            "Reuters heatwave deaths power demand grid food crops insurance",
            "AP News extreme heat deaths electricity demand agriculture food prices",
            "Reuters record heat deaths emergency power grid drought crops",
            "World Health Organization heatwave deaths emergency electricity food",
            "World Meteorological Organization extreme heat deaths power demand drought",
        ),
        required_groups=(
            ("heatwave", "heat wave", "extreme heat", "record heat", "high temperatures", "hot weather", "폭염", "극한 고온"),
            ("death", "deaths", "dead", "died", "killed", "fatalities", "death toll", "사망", "사망자", "사망자 수"),
        ),
        core="신뢰외신 또는 WHO·WMO가 폭염 사망과 광역 기후 재난을 보도한 사안입니다. 전력수요, 식량·물가, 보험손해, 산업가동 중 어느 경로가 실제로 동행하는지 확인해야 합니다.",
        impact="전력수요·LNG, 농산물·음식료 원가, 손해보험, 물류·산업가동 | 매출·마진·현금흐름·할인율·시간표",
        point="사망 규모가 큰 폭염은 단순 날씨 뉴스가 아니라 냉방 전력피크, 가뭄·농산물 수급, 보험손해, 노동·물류 차질로 전이될 수 있습니다.",
        counter="사망자 집계는 지연·추정치일 수 있고, 지역 재난이 전력·식량·보험 지표로 전이되지 않으면 한국장 직접 영향은 제한적입니다.",
        sectors="전력·LNG, 전력기기, 음식료·농산물 원가, 손해보험, 물류·산업재",
        impacts=("매출·마진·현금흐름", "밸류에이션/할인율", "시간표"),
        paths=("기후 재난", "전력수요", "원자재 비용", "보험손해", "공급·수요"),
        follow_up="사망자 공식 집계, 기상 경보 범위, 전력피크·LNG·농산물·보험손해·항만/물류 지표가 같은 방향으로 확인될 때만 가격 재료로 유지합니다.",
    ),
    StoryRule(
        key="us_trusted_policy_shock_broad",
        title="신뢰외신, 미국 고충격 정책 후보 보도",
        google_queries=(
            "Reuters Bloomberg US policy ban tariff export control investigation subsidy loan nuclear data center power grid robotics semiconductor fertilizer agriculture",
            "Reuters Bloomberg Trump administration national security import restriction equipment energy inverter robot drone satellite",
            "Reuters Bloomberg Commerce BIS USTR FCC DOE FERC NRC USDA policy ban investigation subsidy loan supply chain",
            "Politico Reuters Commerce Chinese imports robots drones equipment national security tariffs",
            "Bloomberg Reuters DOE FERC NRC USDA nuclear reactors data centers power grid low cost loans fertilizer agriculture",
        ),
        required_groups=(
            ("commerce", "bis", "ustr", "fcc", "federal communications commission", "doe", "ferc", "nrc", "white house", "treasury", "ofac", "trump administration"),
            ("ban", "barred", "restrict", "restriction", "tariff", "tariffs", "export control", "sanction", "investigation", "review", "subsidy", "loan", "loans", "low-cost", "rule", "national security"),
            ("semiconductor", "ai chip", "robot", "robotics", "drone", "inverter", "solar", "grid", "power", "data center", "nuclear", "reactor", "transformer", "battery", "critical minerals", "steel", "shipbuilding", "satellite", "defense", "uranium", "fertilizer", "phosphate", "agriculture", "biofuel", "food supply"),
        ),
        core="Reuters·Bloomberg 등 신뢰외신에서 미국 정부·규제기관의 수입제한, 관세, 수출통제, 보조금, 대출, 인허가, 산업비용 정책 후보가 보도된 사안입니다.",
        impact="반도체/AI, 전력망/데이터센터, 원전/전력기기, 로봇/자동화, 비료/농업 원가, 방산/공급망 | 돈 버는 능력·수급·시간표",
        point="정책 대상 품목과 시행일이 공식화되면 한국 밸류체인의 매출처, 원가, 수주 시간표, 중국 대체 수요가 바뀔 수 있습니다.",
        counter="신뢰외신 보도 단계에서는 공식 문서, 품목코드, 시행일, 예외 조항, 실제 예산·대출 조건이 확정되지 않았습니다.",
        sectors="반도체/AI, 전력망/데이터센터, 원전/전력기기, 로봇/자동화, 비료/농업 원가, 방산/공급망",
        impacts=("돈 버는 능력", "수급", "시간표"),
        paths=("정책 타임라인", "공급망", "밸류체인", "수급"),
        follow_up="이 넓은 안전망은 특정 테마 룰이 없는 새 정책축을 놓치지 않기 위한 것입니다. 송출 후에는 공식 원문, 품목·세율·시행일, 한국 기업 직접 노출을 확인해야 합니다.",
    ),
    StoryRule(
        key="us_japan_korea_smr_moc_state_watch",
        title="미·일·한, 제3국 SMR 배치 협력 MOC 체결",
        google_queries=(
            "site:state.gov \"Republic of Korea\" \"Small Modular Reactor\" \"Memorandum of Cooperation\" \"Samsung C&T\"",
            "\"United States\" \"Japan\" \"Republic of Korea\" \"Small Modular Reactor\" \"Memorandum of Cooperation\" \"Samsung C&T\"",
            "\"GE Vernova\" Hitachi \"Samsung C&T\" SGE BWRX-300 SMR Europe",
            "\"FIRST Program\" \"SMR Regional Training Hub\" \"Republic of Korea\"",
            "Reuters Bloomberg \"South Korea\" Japan US small modular reactor memorandum cooperation Samsung C&T",
        ),
        required_groups=(
            ("small modular reactor", "small modular reactors", "smr", "bwrx-300"),
            ("memorandum of cooperation", "moc", "signed", "cooperation"),
            ("republic of korea", "south korea", "korea"),
            ("japan", "japanese", "trilateral"),
            ("samsung c&t", "ge vernova", "hitachi", "first program", "regional training hub", "indo-pacific", "europe"),
        ),
        core="미 국무부 또는 신뢰 소스 기준 미·일·한이 제3국 SMR 배치를 가속하기 위한 3국 협력각서(MOC)를 체결했다는 신호입니다. 원문에는 FIRST 프로그램 1,000만 달러 이상 지원, GE Vernova·Hitachi·Samsung C&T·SGE의 BWRX-300 유럽 배치 이니셔티브가 함께 언급됩니다.",
        impact="원전/SMR, 삼성물산/건설·EPC, 원전 기자재/전력기기, BWRX-300 밸류체인 | 시간표·수급·돈 버는 능력·할인율",
        point="MOC는 확정 수주가 아니라 제3국 SMR 사업의 정책 시간표와 파이낸싱 신뢰도, 민간 밸류체인 기대를 높이는 재료입니다. 삼성물산이 원문에 직접 언급되면 한국장에서는 원전 EPC와 기자재 밸류체인 기대가 먼저 움직일 수 있습니다.",
        counter="확정 매출 확인 불가. 협력각서(MOC)는 EPC 계약, 공급계약, 확정 매출이 아닙니다. FIRST 자금도 기술지원·훈련허브 성격이라 실제 건설 CAPEX와 다르며, 국가·부지·라이선스·계약 범위가 확인돼야 실적 재료가 됩니다.",
        sectors="원전/SMR, 삼성물산/건설·EPC, 원전 기자재/전력기기, BWRX-300 밸류체인",
        impacts=("시간표", "수급", "돈 버는 능력", "할인율"),
        paths=("정책 타임라인", "계약 가시성", "원전 밸류체인", "프로젝트 파이낸싱", "수급"),
        follow_up="이 뉴스는 MOC 단계라 확정 수주로 계산하지 않습니다. 후속으로 삼성물산·GE Vernova·Hitachi·SGE 공시, BWRX-300 프로젝트 국가·부지·EPC 범위, 인허가·금융 일정, 한국 기자재 공급망 노출을 확인해야 합니다.",
        trusted_sources=(
            "Aju Press",
            "American Nuclear Society -- ANS",
            "American Nuclear Society",
            "World Nuclear News",
            "POWER Magazine",
            "SMR Insider",
            "The Express Tribune",
            "U.S. Embassy & Consulates in China",
            "U.S. Mission to the European Union",
        ),
    ),
    StoryRule(
        key="us_doe_energy_security_policy",
        title="미 에너지부, 전력망·원전·에너지 장비 지원/제한 정책 보도",
        google_queries=(
            "Reuters Bloomberg DOE loan guarantee nuclear reactors data centers power grid energy security",
            "Reuters Bloomberg Department of Energy conditional commitment loan guarantee nuclear grid transformer",
            "Reuters Bloomberg DOE funding opportunity grid deployment transformer critical materials nuclear fuel",
            "Reuters Bloomberg DOE ban restriction efficiency standard energy equipment transformer inverter",
            "Bloomberg Reuters Department of Energy low cost loans AP1000 reactors data centers",
        ),
        required_groups=(
            ("doe", "department of energy", "energy department"),
            ("loan", "loans", "loan guarantee", "conditional commitment", "funding", "grant", "award", "selected", "ban", "restriction", "efficiency standard", "low-cost"),
            ("grid", "power", "transmission", "data center", "nuclear", "reactor", "ap1000", "transformer", "uranium", "nuclear fuel", "critical materials", "inverter"),
        ),
        core="미 에너지부(DOE)의 대출보증, 조건부 지원 약정, 자금지원, 효율규제, 금지·제한 정책이 전력망·원전·에너지 장비 밸류체인에 영향을 줄 수 있다는 신뢰외신 보도입니다.",
        impact="전력망/전력기기, 원전/SMR/핵연료, 데이터센터 전력, 핵심소재/에너지 공급망 | 돈 버는 능력·수급·시간표·할인율",
        point="DOE의 자금지원·대출·규제는 프로젝트 착공과 장비 발주 시간표, 원전/전력기기 수주 가시성, 데이터센터 전력 병목 프리미엄을 동시에 바꿀 수 있습니다.",
        counter="신뢰외신 보도 단계에서는 최종 DOE 원문, 선정 기업, 금액, 대출 조건, 인허가·착공 일정, 한국 기업 공급망 노출이 확정되지 않았습니다.",
        sectors="전력망/전력기기, 원전/SMR/핵연료, 데이터센터 전력, 핵심소재/에너지 공급망",
        impacts=("돈 버는 능력", "수급", "시간표", "할인율"),
        paths=("정책 타임라인", "전력망 투자", "원전/핵연료", "대출·보조금", "공급망"),
        follow_up="DOE 보도는 금액·대출조건·선정기업·시행일·조달일정이 원문에서 확인될 때 고충격으로 남깁니다. 국내 기업은 미국 프로젝트 노출이 없으면 테마 반응으로 제한합니다.",
    ),
    StoryRule(
        key="iran_hormuz_military_escalation",
        title="미국, 이란 재공격·호르무즈 상선 피격: 휴전·유가 리스크",
        google_queries=(
            "site:apnews.com Iran Hormuz attack ship strike ceasefire",
            "Iran Hormuz attack ship airstrikes AP News",
            "U.S. strikes Iran ship Strait of Hormuz ceasefire AP Reuters CNBC",
            "Iran retaliates Gulf states Hormuz vessel attack AP News",
        ),
        required_groups=(
            ("iran", "iranian", "tehran", "이란"),
            ("hormuz", "strait of hormuz", "ship", "vessel", "tanker", "gulf"),
            ("attack", "attacks", "attacked", "strike", "strikes", "airstrike", "airstrikes", "retaliation", "ceasefire", "missile", "drone", "closed"),
        ),
        core="AP·Reuters·CNBC 등 신뢰외신에서 호르무즈 상선 피격과 미국의 이란 재공격, 이란의 역내 대응으로 휴전과 해상운송 안전이 다시 흔들린 사안입니다.",
        impact="정유/화학, 해운/운임, 방산/지정학, 환율 민감주 | 돈 버는 능력·할인율·수급·시간표",
        point="호르무즈 통항 차질은 유가·운임·보험료와 원/달러를 통해 한국 수입 원가를 높이고, 해운·방산 수급을 자극할 수 있습니다.",
        counter="단발성 보복 뒤 추가 공격이 멈추고 상선 통항이 유지되면 유가·운임 충격은 빠르게 되돌릴 수 있습니다.",
        sectors="정유/화학, 해운/운임, 방산/지정학, 환율 민감주",
        impacts=("돈 버는 능력", "할인율", "수급", "시간표"),
        paths=("지정학 리스크", "유가·운임", "원자재 비용", "환율", "정책 타임라인"),
        follow_up="미 국방부·CENTCOM·백악관 후속, 실제 선박 통항 감소, WTI/Brent·운임·USD/KRW·방산주 반응을 확인합니다.",
    ),
    StoryRule(
        key="trump_direct_policy_remarks_watch",
        title="트럼프 대통령 직접 발언, 시장 영향 정책 신호",
        google_queries=(
            "site:reuters.com Trump says tariffs chips AI semiconductor China",
            "site:reuters.com Trump says Iran Israel Hormuz oil",
            "site:reuters.com Trump Iran wants talks negotiations",
            "site:reuters.com Trump says Iran wants deal contacted",
            "site:reuters.com Trump Iran reached out seeking new agreement",
            "site:bloomberg.com Trump Iran reached out seeking new agreement",
            "site:reuters.com Trump says NATO defense spending Ukraine Russia",
            "site:reuters.com Trump says South Korea troops burden sharing defense",
            "site:reuters.com Trump says Fed rates dollar tariffs oil",
            "site:apnews.com Trump NATO Iran Ukraine defense spending tariffs",
            "site:apnews.com Trump Iran wants negotiations talks deal",
            "site:apnews.com Trump says China tariffs chips oil Fed",
            "site:cnbc.com Trump tariffs Fed dollar oil chips nuclear data centers",
            "site:cnbc.com Trump Iran wants negotiations talks deal",
            "site:marketwatch.com Trump tariffs Fed dollar oil Iran chips",
            "Trump says Iran wants negotiations Reuters",
            "Trump says Iran wants to negotiate Reuters",
            "Trump contacted by Iran wants negotiations Reuters",
            "\"Trump says Iran reached out seeking a new agreement\"",
            "\"Iran reached out seeking a new agreement\" Trump",
            "\"TRUMP SAYS IRAN REACHED OUT SEEKING A NEW AGREEMENT\"",
            "Trump says tariff semiconductor China Taiwan Korea dollar Fed oil nuclear data center Reuters",
            "President Trump remarks tariffs export controls sanctions defense burden sharing South Korea Reuters",
            "Trump says Iran Israel war strike ceasefire oil Hormuz Middle East Reuters",
            "Trump warns Iran Israel Strait of Hormuz oil tanker shipping Reuters",
            "Trump comments Red Sea Houthi Iran missile strike Brent WTI Reuters",
            "Trump says Russia Ukraine NATO defense spending sanctions oil gas Reuters",
            "Trump says North Korea South Korea US troops burden sharing defense Reuters",
        ),
        required_groups=(
            ("trump", "president trump", "donald trump", "donald j. trump", "트럼프"),
            ("says", "said", "remarks", "comments", "announces", "backs", "orders", "warns", "threatens", "signals", "vows", "말했다", "밝혔다", "발언", "언급"),
            (
                "tariff", "tariffs", "export control", "sanctions", "fed", "rate", "dollar", "oil",
                "china", "taiwan", "korea", "south korea", "defense", "burden sharing", "usfk",
                "semiconductor", "chip", "ai", "data center", "power grid", "nuclear", "reactor",
                "iran", "israel", "middle east", "hormuz", "strait of hormuz", "red sea", "houthi",
                "missile", "strike", "ceasefire", "war", "war powers", "brent", "wti", "tanker",
                "shipping", "lng", "natural gas", "russia", "ukraine", "nato", "north korea",
                "steel", "copper", "transformer", "pharma", "drug price", "autos", "ev",
                "iran wants", "negotiate", "negotiations", "talks", "contacted by iran",
                "reached out", "new agreement", "seeking a new agreement", "reached out seeking",
                "이란", "협상", "연락", "유가", "호르무즈", "관세", "방위비", "나토", "우크라이나", "러시아", "달러", "금리", "반도체",
            ),
        ),
        core="Reuters·Bloomberg·CNBC 등 신뢰외신에서 트럼프 대통령의 직접 발언이 관세, 수출통제, 금리·달러, 유가·에너지, 이란·이스라엘·중동 전쟁위험, 방위비, 반도체·AI 인프라 정책 기대를 움직인 사안입니다.",
        impact="관세/수출주, 반도체/AI, 전력망/원전, 방산/지정학, 정유·화학·해운, 환율·금리 민감주 | 돈 버는 능력·할인율·수급·시간표",
        point="트럼프 직접 발언은 공식 문서 전이라도 정책 확률과 시장 할인율을 먼저 움직일 수 있습니다. 특히 이란·이스라엘·호르무즈·홍해 관련 전쟁 발언은 유가, 운임, 방산 수요, 정유·화학 원가, 환율 리스크를 즉시 건드립니다.",
        counter="발언은 행정명령·관보·부처 공고가 아니므로 실제 정책 범위가 축소되거나 일정이 밀릴 수 있습니다. 단순 정치 발언이면 하루짜리 수급으로 끝날 수 있습니다.",
        sectors="관세/수출주, 반도체/AI, 전력망/원전, 방산/지정학, 정유·화학·해운, 환율·금리 민감주",
        impacts=("돈 버는 능력", "할인율", "수급", "시간표"),
        paths=("정책 타임라인", "할인율", "공급망", "지정학 리스크", "원자재 비용", "수급"),
        follow_up="트럼프 발언은 모두 감시하되, 송출 후에는 백악관 원문, 부처 후속 문서, 품목·국가·시행일, 유가·환율·운임·방산 티커 반응, 한국 기업 직접 노출을 재확인해야 합니다. 단순 선거성 발언은 실패 신호로 처리합니다.",
    ),
    StoryRule(
        key="global_korea_policy_shock_broad",
        title="신뢰외신, 한국 직접 영향 해외 정책 후보 보도",
        google_queries=(
            "Reuters Bloomberg South Korea tariff quota safeguard export control regulation steel battery semiconductor shipbuilding fertilizer agriculture",
            "Reuters Bloomberg Korea policy impact EU China Japan Taiwan Middle East sanctions tariff export controls supply chain fertilizer food",
            "\"South Korea\" \"tariff\" \"quota\" \"export control\" Reuters Bloomberg",
            "\"Korean\" steel battery semiconductor shipbuilding fertilizer regulation tariff quota Reuters Bloomberg",
            "\"한국산\" 관세 쿼터 규제 완화 강화 EU 미국 중국 일본 수출통제 비료 농업",
        ),
        required_groups=(
            ("korea", "south korea", "korean", "한국", "한국산"),
            ("tariff", "quota", "safeguard", "anti-dumping", "export control", "sanction", "regulation", "ban", "restriction", "customs", "duty", "관세", "쿼터", "세이프가드", "반덤핑", "수출통제", "제재", "규제"),
            ("steel", "battery", "semiconductor", "shipbuilding", "auto", "chemical", "solar", "transformer", "defense", "critical minerals", "fertilizer", "agriculture", "food", "철강", "배터리", "반도체", "조선", "자동차", "화학", "변압기", "방산", "비료", "농업", "식량"),
        ),
        core="미국·EU·중국·일본 등 해외 정책이 한국산 제품이나 한국 기업의 수출 조건을 직접 바꿀 수 있다는 신뢰 보도/공식 신호입니다.",
        impact="한국 수출주, 철강/배터리/반도체/조선/자동차/화학/전력기기/비료·음식료 원가 | 돈 버는 능력·수급·시간표",
        point="한국산 품목의 관세, 쿼터, 수출통제, 제재, 인증·규제 조건이 바뀌면 마진, 물량, 주문 이전, 테마 수급이 함께 움직일 수 있습니다.",
        counter="해외 정책 보도만으로는 품목 범위, 국가별 쿼터, 예외 조항, 시행일, 한국 기업 직접 노출이 확정되지 않습니다.",
        sectors="한국 수출주, 철강/배터리/반도체/조선/자동차/화학/전력기기/비료·음식료 원가",
        impacts=("돈 버는 능력", "수급", "시간표"),
        paths=("무역규제", "정책 타임라인", "공급망", "수급"),
        follow_up="한국산 또는 한국 기업 직접 노출이 원문에 있어야 고충격으로 남깁니다. 단순 해외 일반 규제는 공식 문서와 국내 밸류체인 연결이 없으면 제외합니다.",
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


def fetch_text(url: str, timeout: int = 8) -> str:
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
    if key in TRUSTED_SOURCES:
        return True
    return "department of state" in key or "state department" in key or "state.gov" in key


def is_rule_trusted_source(name: str, rule: StoryRule) -> bool:
    key = source_key(name)
    return any(key == source_key(source) for source in rule.trusted_sources)


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


def is_direct_trump_statement_title(title: str) -> bool:
    """Reject third-party reporting that merely contains the words Trump and says."""
    low = clean_story_title(title).lower()
    return bool(
        re.search(
            r"\b(?:president\s+)?trump\s+(?:says|said|remarks|comments|announces|backs|orders|warns|threatens|signals|vows)\b",
            low,
        )
        or re.search(r"\btrump\s+on\b", low)
    )


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
            rule_source_ok = is_rule_trusted_source(publisher, rule)
            haystack_parts = [title, publisher, description]
            if rule_source_ok and rule.key == "us_japan_korea_smr_moc_state_watch":
                haystack_parts.append(query)
            haystack = " ".join(haystack_parts)
            wire_source = trusted_wire_source(haystack)
            if not title or not link or not published:
                continue
            if link in seen_links:
                continue
            if not is_trusted_source(publisher) and not rule_source_ok and not is_trusted_wire_relay(publisher, haystack):
                continue
            if (now - published).total_seconds() / 3600 > MAX_AGE_HOURS:
                continue
            if not has_required_terms(haystack, rule):
                continue
            # A direct Trump quote is sendable only when its English headline maps
            # to a concrete Korean policy event. Do not fall back to a broad
            # "market-moving remark" template for an otherwise ambiguous story.
            if rule.key == "trump_direct_policy_remarks_watch":
                if not is_direct_trump_statement_title(title) or not trump_story_profile(title):
                    continue
            # Weather-disaster alerts must be source-specific.  A death count
            # in a generic climate commentary is not enough to justify a
            # market alert; the wire headline itself needs a large-scale or
            # price-transmission signal that the Korean rendering can carry.
            if rule.key == "global_extreme_heat_mortality_watch":
                if not is_heat_mortality_high_impact_title(title) or not heat_mortality_story_profile(title):
                    continue
            if rule.key == "iran_hormuz_military_escalation":
                if not iran_hormuz_story_profile(title):
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
                    "description": description,
                    "link": link,
                    "source": display_source,
                    "published_kst": published.isoformat(timespec="seconds"),
                    "priority": SOURCE_PRIORITY.get(priority_key, 99),
                }
            )
    items.sort(key=lambda item: item["published_kst"], reverse=True)
    items.sort(key=lambda item: item["priority"])
    return items


def legacy_daily_fingerprint(rule: StoryRule, items: list[dict]) -> str:
    first_day = ""
    if items:
        first_day = str(items[0].get("published_kst", ""))[:10]
    raw = f"{FORMAT_VERSION}:{rule.key}:{first_day}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def clean_story_title(title: str) -> str:
    title = clean_text(title)
    title = re.sub(
        r"\s+-\s+(Reuters|Bloomberg|AP News|Associated Press|CNBC|MarketWatch|The Wall Street Journal|Financial Times)\s*$",
        "",
        title,
        flags=re.I,
    )
    return title


def story_identity(item: dict) -> str:
    title = re.sub(r"\s+", " ", clean_story_title(str(item.get("title") or "")).lower()).strip()
    source = source_key(str(item.get("source") or ""))
    published = str(item.get("published_kst") or "")[:16]
    return f"{source}|{published}|{title}"


def fingerprint(rule: StoryRule, items: list[dict]) -> str:
    top_identity = story_identity(items[0]) if items else ""
    raw = f"{FORMAT_VERSION}:story-v2:{rule.key}:{top_identity}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def story_event_fingerprint(rule: StoryRule, items: list[dict]) -> str:
    """Deduplicate the same wire headline when only its update timestamp moves."""
    if not items:
        identity = ""
    else:
        title = re.sub(r"\s+", " ", clean_story_title(str(items[0].get("title") or "")).lower()).strip()
        identity = f"{rule.key}|{title}"
    profile = trump_story_profile(str(items[0].get("title") or "")) if items else None
    revision = str((profile or {}).get("revision") or "story-event-v1")
    raw = f"{FORMAT_VERSION}:{revision}:{identity}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


IRAN_HORMUZ_REPEAT_COOLDOWN = dt.timedelta(hours=6)


def is_recent_iran_hormuz_escalation(rule: StoryRule, items: list[dict], seen: dict) -> bool:
    """Avoid repeats and old-wire backfills across AP/CNBC escalation coverage."""
    if rule.key != "iran_hormuz_military_escalation" or not items:
        return False
    reference_times = [parse_kst_iso(str(item.get("published_kst") or "")) for item in items]
    reference = max((value for value in reference_times if value), default=None)
    if not reference:
        return False
    prior_alerts: list[dt.datetime] = []
    for entry in seen.values():
        if not isinstance(entry, dict) or entry.get("key") != rule.key:
            continue
        first_seen = parse_kst_iso(str(entry.get("first_seen_kst") or ""))
        if first_seen:
            prior_alerts.append(first_seen)
    if not prior_alerts:
        return False
    latest_alert = max(prior_alerts)
    # A wire article published before the latest delivered escalation alert was
    # already represented by the previous broad grouping.  Never replay it just
    # because the renderer gained a more precise title later.
    if reference <= latest_alert:
        return True
    return reference - latest_alert < IRAN_HORMUZ_REPEAT_COOLDOWN


def parse_kst_iso(value: str) -> dt.datetime | None:
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=KST)
    return parsed.astimezone(KST)


def unseen_items_for_rule(rule: StoryRule, items: list[dict], seen: dict) -> list[dict]:
    if not items:
        return []
    if is_recent_iran_hormuz_escalation(rule, items, seen):
        return []
    current_fp = fingerprint(rule, items)
    event_fp = story_event_fingerprint(rule, items)
    profile = trump_story_profile(str(items[0].get("title") or "")) if rule.key == "trump_direct_policy_remarks_watch" else None
    is_corrective_render = bool((profile or {}).get("revision"))
    if event_fp in seen:
        return []
    # Preserve previous time-stamped fingerprints during migration. The one
    # exception is a corrected Korean rendering, which is allowed once.
    if current_fp in seen and not is_corrective_render:
        return []
    legacy_fp = legacy_daily_fingerprint(rule, items)
    legacy_entry = seen.get(legacy_fp)
    if not legacy_entry:
        return items
    first_seen = parse_kst_iso(str(legacy_entry.get("first_seen_kst") or ""))
    if not first_seen:
        return items
    fresh_items = [
        item for item in items
        if (parse_kst_iso(str(item.get("published_kst") or "")) or dt.datetime.min.replace(tzinfo=KST)) > first_seen
    ]
    return fresh_items


def alert_item_groups(rule: StoryRule, items: list[dict]) -> list[list[dict]]:
    """Keep article-specific profiles in their own alert and source chain."""
    if rule.key in {
        "trump_direct_policy_remarks_watch",
        "global_extreme_heat_mortality_watch",
        "iran_hormuz_military_escalation",
    }:
        return [[item] for item in items]
    return [items] if items else []


HEAT_LOCATION_LABELS = (
    ("south korea", "한국"),
    ("korea", "한국"),
    ("japan", "일본"),
    ("china", "중국"),
    ("india", "인도"),
    ("pakistan", "파키스탄"),
    ("bangladesh", "방글라데시"),
    ("vietnam", "베트남"),
    ("thailand", "태국"),
    ("philippines", "필리핀"),
    ("indonesia", "인도네시아"),
    ("australia", "호주"),
    ("united states", "미국"),
    ("u.s.", "미국"),
    ("usa", "미국"),
    ("mexico", "멕시코"),
    ("canada", "캐나다"),
    ("brazil", "브라질"),
    ("argentina", "아르헨티나"),
    ("spain", "스페인"),
    ("portugal", "포르투갈"),
    ("france", "프랑스"),
    ("italy", "이탈리아"),
    ("germany", "독일"),
    ("greece", "그리스"),
    ("turkey", "튀르키예"),
    ("uk", "영국"),
    ("britain", "영국"),
    ("europe", "유럽"),
    ("middle east", "중동"),
    ("global", "세계"),
    ("world", "세계"),
)

HEAT_SYSTEMIC_TERMS = (
    "record", "emergency", "state of emergency", "nationwide", "widespread", "across",
    "power", "electricity", "grid", "energy", "blackout", "outage", "demand",
    "crop", "agriculture", "food", "drought", "water", "insurance", "insured",
    "factory", "industrial", "transport", "rail", "airport", "port", "shipping",
)


def iran_hormuz_story_profile(title: str) -> dict[str, object] | None:
    """Render one escalation headline without mixing it with another wire story."""
    cleaned = clean_story_title(title)
    low = cleaned.lower()
    has_iran = "iran" in low or "iranian" in low or "tehran" in low
    has_action = any(term in low for term in ("attack", "attacks", "strike", "strikes", "targets", "retaliates", "hits", "standoff", "vessel", "tanker"))
    has_shipping_or_gulf = any(term in low for term in ("hormuz", "vessel", "tanker", "gulf", "uae", "bahrain"))
    if not (has_iran and has_action and has_shipping_or_gulf):
        return None
    if "civilian vessel" in low:
        title_ko = "호르무즈 민간선 피격 뒤 미군 이란 타격 보도: 유가·운임 리스크"
        core = "신뢰외신은 호르무즈 민간 선박 피격 뒤 미군이 이란을 타격했다고 보도했습니다. 핵심은 실제 통항 감소와 추가 보복 여부입니다."
    elif any(term in low for term in ("tanker", "uae", "bahrain")):
        title_ko = "미국·이란 공방과 호르무즈 유조선 위협 보도: 유가·운임 리스크"
        core = "신뢰외신은 미국의 이란 공격과 이란의 UAE 유조선·바레인 관련 대응을 보도했습니다. 호르무즈 통항과 유조선 안전이 직접 변수입니다."
    elif "gulf states" in low or "military assets" in low:
        title_ko = "미국의 이란 군사자산 타격·걸프국 긴장 보도: 유가·운임 리스크"
        core = "신뢰외신은 미국의 이란 군사자산 타격과 테헤란의 걸프국 대응을 보도했습니다. 확전이 유조선·에너지 인프라로 번지는지 확인해야 합니다."
    else:
        title_ko = "미국, 이란 추가 타격·호르무즈 긴장 고조 보도: 유가·운임 리스크"
        core = "신뢰외신은 미국의 이란 추가 타격과 호르무즈를 둘러싼 긴장 고조를 보도했습니다. 실제 상선 통항과 에너지 인프라 피해가 가격 변수입니다."
    return {
        "title": title_ko,
        "core": core,
        "investment": "통항 차질이나 유조선 피격이 이어지면 Brent·전쟁보험료·운임·원/달러가 먼저 반응하고, 정유·화학 원가와 해운·방산 수급이 뒤따를 수 있습니다.",
        "korea": "한국장에서는 정유·화학의 원가, 해운·항공의 운임·연료비, 방산과 환율 민감주만 확인합니다. 실제 통항 감소 전에는 테마 확장을 제한합니다.",
        "impacts": "매출·마진·현금흐름, 밸류에이션/할인율, 수급, 시간표",
        "paths": "지정학 리스크, 유가·운임, 원자재 비용, 환율",
        "sectors": "정유/화학, 해운, 항공/운송, 방산/지정학",
        "priced_in": "중간. 기존 중동 긴장은 반영됐지만, 유조선 위협·통항 차질이 새로 확인되면 단기 재평가가 가능합니다.",
        "counter": "공격·보복이 더 확산되지 않고 상선 통항이 유지되면 유가·운임 충격은 빠르게 되돌릴 수 있습니다.",
        "failure": "CENTCOM·해운사·보험사 후속, AIS 통항 감소, Brent·운임·원/달러 반응이 없으면 단발성 속보로 약화됩니다.",
    }


def heat_death_count(title: str) -> int | None:
    """Extract a count only when it is grammatically tied to deaths."""
    low = clean_story_title(title).lower()
    patterns = (
        r"(?:death toll|toll|deaths?|fatalities)\s+(?:rises?|reach(?:es)?|hits?|stands? at|of|to)?\s*(?:over|more than|at least|nearly|about)?\s*(\d[\d,]*)",
        r"(?:kills?|killed|claims?)\s+(?:over|more than|at least|nearly|about)?\s*(\d[\d,]*)",
        r"(?:over|more than|at least|nearly|about)?\s*(\d[\d,]*)\s+(?:people\s+)?(?:dead|deaths?|died|killed|fatalities)",
    )
    for pattern in patterns:
        match = re.search(pattern, low)
        if match:
            try:
                return int(match.group(1).replace(",", ""))
            except ValueError:
                return None
    return None


def is_heat_mortality_high_impact_title(title: str) -> bool:
    """Reject local or unspecific weather stories before rendering an alert."""
    low = clean_story_title(title).lower()
    is_heat = any(term in low for term in ("heatwave", "heat wave", "extreme heat", "record heat", "high temperatures", "hot weather"))
    is_mortality = any(term in low for term in ("death", "dead", "died", "kills", "killed", "claims", "fatalities", "death toll"))
    if not (is_heat and is_mortality):
        return False
    count = heat_death_count(title)
    return bool(any(term in low for term in HEAT_SYSTEMIC_TERMS) or (count is not None and count >= 25) or "dozens" in low or "hundreds" in low)


def heat_location_label(text: str) -> str:
    low = text.lower()
    for marker, label in HEAT_LOCATION_LABELS:
        if re.search(rf"(?<![a-z]){re.escape(marker)}(?![a-z])", low):
            return label
    return "해외"


def heat_mortality_story_profile(title: str) -> dict[str, object] | None:
    """Build a Korean summary solely from facts visible in one wire headline."""
    if not is_heat_mortality_high_impact_title(title):
        return None
    cleaned = clean_story_title(title)
    low = cleaned.lower()
    location = heat_location_label(low)
    count = heat_death_count(cleaned)
    count_text = f" {count:,}명" if count is not None else ""
    channels: list[str] = []
    if any(term in low for term in ("power", "electricity", "grid", "blackout", "outage", "demand", "energy")):
        channels.append("전력수요·전력망")
    if any(term in low for term in ("crop", "agriculture", "food", "drought", "water")):
        channels.append("식량·농산물")
    if any(term in low for term in ("insurance", "insured")):
        channels.append("보험손해")
    if any(term in low for term in ("factory", "industrial", "transport", "rail", "airport", "port", "shipping")):
        channels.append("물류·산업가동")
    channel_text = "·".join(channels[:2]) if channels else "기후 재난 확산"
    has_earnings_path = bool(channels)
    impacts = "매출·마진·현금흐름, 밸류에이션/할인율, 시간표" if has_earnings_path else "밸류에이션/할인율, 시간표"
    paths = ", ".join(channels[:3]) if channels else "기후 재난, 정책·보건 대응 시간표"
    sectors = "전력·LNG, 전력기기, 음식료·농산물 원가, 손해보험" if has_earnings_path else "전력·LNG, 음식료·농산물 원가, 손해보험"
    return {
        "title": f"{location}, 폭염 사망{count_text} 보도: {channel_text} 리스크 확인",
        "core": f"신뢰외신·국제기구가 {location} 폭염과 사망{count_text} 발생을 보도했습니다. 이 기사에서 직접 확인된 전이 경로는 {channel_text}입니다.",
        "investment": (
            f"{channel_text} 경로가 실제 수치로 확인되면 전력피크·에너지 비용·농산물 원가·보험손해 추정이 바뀔 수 있습니다."
            if has_earnings_path else
            "사망 보도만으로 즉시 실적을 단정하지 않습니다. 전력피크, 농산물 가격, 보험손해가 동행할 때만 이익 추정으로 연결합니다."
        ),
        "korea": "한국장 직접 영향은 제한적입니다. 냉방 전력수요, LNG·석탄, 농산물·음식료 원가, 손해보험 지표가 동행하는 종목군만 선별 확인합니다.",
        "impacts": impacts,
        "paths": paths,
        "sectors": sectors,
        "priced_in": "낮음~중간. 지역 재난 뉴스는 빠르게 반영되지만, 에너지·식량·보험 지표 전이 전에는 지속성이 낮습니다.",
        "counter": "사망자 수는 당국의 잠정 집계일 수 있고, 지역적 사건이면 글로벌 원가·수요 변수로 확대 해석하기 어렵습니다.",
        "failure": "공식 사망 집계·기상경보와 전력피크·LNG·농산물·보험손해 중 하나도 동행하지 않으면 지역 재난 뉴스로 분리합니다.",
    }


def trump_story_profile(title: str) -> dict[str, object] | None:
    """Return a source-faithful Korean profile for supported Trump headlines."""
    cleaned = clean_story_title(title)
    low = cleaned.lower()
    common = {
        "priced_in": "낮음~중간. 대통령 발언은 즉시 반영될 수 있지만, 공식 문서나 실제 지표가 없으면 되돌림도 빠릅니다.",
        "counter": "대통령 발언만으로는 시행 주체, 적용 범위, 실제 이행 여부가 확정되지 않았습니다.",
    }
    if "hormuz" in low and "open" in low and any(term in low for term in ("commercial", "traffic", "shipping", "tanker")):
        return {
            **common,
            "revision": "trump-hormuz-open-ko-v2",
            "title": "트럼프, 호르무즈 해협 상업 통항 가능 발언: 유가·운임 리스크 완화 신호",
            "core": "Reuters는 트럼프가 호르무즈 해협이 상업 통항에 열려 있다고 말했다고 보도했습니다. 핵심은 발언이 아니라 실제 선박 통항 재개입니다.",
            "investment": "통항이 정상화되면 원유 공급 차질 우려, 해상 보험료, 우회 운항 비용이 낮아질 수 있습니다.",
            "korea": "항공·운송·화학은 비용 완화 가능성, 해운은 운임 정상화 압력입니다. 정유는 재고평가와 정제마진이 엇갈려 방향을 단정하지 않습니다.",
            "impacts": "매출·마진·현금흐름, 밸류에이션/할인율, 시간표",
            "paths": "유가·운임, 원자재 비용, 지정학 리스크, 정책 타임라인",
            "sectors": "항공/운송, 화학, 해운, 정유",
            "failure": "실제 AIS 통항, 전쟁보험료, Brent·운임이 정상화되지 않으면 발언성 재료로 끝납니다.",
        }
    if (
        "iran" in low
        and "russia" in low
        and "china" in low
        and "trust" in low
        and any(term in low for term in ("enable", "support", "back"))
    ):
        return {
            **common,
            "revision": "trump-russia-china-iran-support-ko-v1",
            "title": "트럼프, 러시아·중국이 이란 지원하지 않을 것으로 신뢰",
            "core": "트럼프는 러·중 지도자가 이란 지원을 막을 것으로 믿는다고 밝혔습니다.",
            "investment": "러·중의 실제 군사·경제 지원 여부가 대이란 제재와 중동 확전 위험을 바꿀 수 있습니다.",
            "korea": "정유·화학·해운·방산은 러·중의 후속 발표와 유가·운임 반응만 확인합니다.",
            "impacts": "밸류에이션/할인율, 수급, 시간표",
            "paths": "지정학 리스크, 제재, 유가·운임",
            "sectors": "정유/화학, 해운, 방산/지정학",
            "failure": "러·중 후속 발표와 제재·유가·운임 변화가 없으면 발언성 재료로 끝납니다.",
        }
    if (
        "iran" in low
        and "houthi" in low
        and "red sea" in low
        and any(term in low for term in ("punish", "punishment", "vow"))
    ):
        oil_suffix = "했고 유가는 100달러를 넘었습니다." if re.search(r"(?:\$|usd\s*)?100", low) else "했습니다."
        return {
            **common,
            "revision": "trump-iran-houthi-red-sea-ko-v1",
            "title": "트럼프, 후티 홍해 공격 관련 이란 응징 경고",
            "core": f"트럼프는 후티 공격 배후 이란을 경고{oil_suffix}",
            "investment": "홍해 공격과 대이란 보복이 이어지면 유가·운임·전쟁보험료가 오를 수 있습니다.",
            "korea": "정유·화학 원가, 해운·항공 운임, 방산과 원/달러 반응만 확인합니다.",
            "impacts": "매출·마진·현금흐름, 밸류에이션/할인율, 수급, 시간표",
            "paths": "지정학 리스크, 유가·운임, 환율",
            "sectors": "정유/화학, 해운, 항공/운송, 방산/지정학",
            "failure": "추가 공격·보복과 유가·운임 반응이 없으면 단발성 경고로 끝납니다.",
        }
    if (
        ("iran" in low or "이란" in low)
        and "reached out" in low
        and any(term in low for term in ("new agreement", "new deal", "새 합의"))
    ):
        return {
            **common,
            "revision": "trump-iran-new-agreement-ko-v1",
            "title": "트럼프, 이란의 새 합의 요청 연락 공개: 협상 재개 가능성",
            "core": "트럼프는 이란이 새 합의를 원해 미국에 연락했다고 밝혔고, 협상 조건은 미정입니다.",
            "investment": "협상 진전은 유가·운임·원/달러 위험프리미엄을 낮출 수 있습니다.",
            "korea": "정유·화학 원가, 해운, 항공·운송, 방산·환율 민감주만 선별 확인합니다.",
            "impacts": "매출·마진·현금흐름, 밸류에이션/할인율, 시간표",
            "paths": "지정학 리스크, 유가·운임, 환율, 정책 타임라인",
            "sectors": "정유/화학, 해운, 항공/운송, 방산/지정학",
            "failure": "공식 협상 일정, 통항 정상화, 유가·운임·환율 반응이 없으면 단발성 발언으로 약화됩니다.",
        }
    if ("iran" in low or "이란" in low) and any(term in low for term in ("negot", "talk", "deal", "contact", "reached out", "agreement", "협상", "연락")):
        return {
            **common,
            "title": "트럼프, 이란 협상 재개 발언: 중동 위험프리미엄 완화 가능성",
            "core": "트럼프가 이란과의 협상·접촉 가능성을 언급한 보도입니다. 협상 재개가 실제 합의나 통항 정상화로 이어지는지가 핵심입니다.",
            "investment": "협상 진전은 유가·운임·원/달러 위험프리미엄을 낮출 수 있지만, 공식 합의 전에는 변동성이 큽니다.",
            "korea": "정유·화학 원가, 해운, 항공·운송, 방산·환율 민감주만 선별 확인합니다.",
            "impacts": "매출·마진·현금흐름, 밸류에이션/할인율, 시간표",
            "paths": "지정학 리스크, 유가·운임, 환율, 정책 타임라인",
            "sectors": "정유/화학, 해운, 항공/운송, 방산/지정학",
            "failure": "공식 협상 일정, 통항 정상화, 유가·운임·환율 반응이 없으면 단발성 발언으로 약화됩니다.",
        }
    if "iran" in low and any(term in low for term in ("over", "end", "conflict", "strike", "attack", "war", "ceasefire")):
        return {
            **common,
            "title": "트럼프, 이란 충돌·휴전 관련 발언: 유가·운임 재상승 리스크",
            "core": "트럼프의 이란 충돌·휴전 관련 발언으로 중동 긴장과 호르무즈 통항 위험이 다시 가격 변수로 부각된 보도입니다.",
            "investment": "긴장 고조는 유가, 전쟁보험료, 해운 운임과 방산 수요를 밀어 올리고 원/달러 위험프리미엄을 높일 수 있습니다.",
            "korea": "정유·화학 원가, 해운, 방산, 환율 민감주를 보되 실제 선박 피격·통항 감소가 없으면 테마성 반응으로 제한합니다.",
            "impacts": "매출·마진·현금흐름, 밸류에이션/할인율, 수급, 시간표",
            "paths": "지정학 리스크, 유가·운임, 환율, 정책 타임라인",
            "sectors": "정유/화학, 해운, 방산/지정학, 환율 민감주",
            "failure": "국방부·CENTCOM 후속, 통항 감소, 유가·운임·환율 반응이 없으면 단발성 충돌로 약화됩니다.",
        }
    if "tariff" in low or "tariffs" in low:
        return {
            **common,
            "title": "트럼프, 관세 관련 발언: 수출주·공급망 정책 리스크",
            "core": "트럼프의 관세 관련 발언으로 대상 국가·품목·시행일에 대한 정책 불확실성이 커진 보도입니다.",
            "investment": "관세가 실제화되면 가격경쟁력, 마진, 공급망 재편과 수출 주문이 바뀔 수 있습니다.",
            "korea": "대미 수출 비중과 품목 노출이 확인되는 자동차·철강·가전·배터리·반도체만 선별 확인합니다.",
            "impacts": "매출·마진·현금흐름, 수급, 시간표",
            "paths": "무역규제, 공급망, 정책 타임라인",
            "sectors": "관세 민감 수출주, 물류/공급망",
            "failure": "대상국·품목·세율·시행일과 한국 기업 노출이 확인되지 않으면 발언성 재료로 끝납니다.",
        }
    if (
        "semiconductor" in low
        or re.search(r"\bchips?\b", low)
        or re.search(r"\bai\b", low)
        or "artificial intelligence" in low
        or "data center" in low
    ):
        return {
            **common,
            "title": "트럼프, 반도체·AI 관련 발언: 수출통제·AI 투자 정책 신호",
            "core": "트럼프가 반도체·AI·데이터센터 관련 정책 방향을 언급한 보도입니다. 실제 수출통제·보조금·전력 인허가 문서가 뒤따르는지가 중요합니다.",
            "investment": "고객사 CAPEX, AI 인프라 발주, 수출통제 범위가 바뀌면 반도체 매출과 밸류체인 주문 기대가 달라집니다.",
            "korea": "삼성전자·SK하이닉스와 HBM·장비·소재, 데이터센터 전력 인프라 중 직접 노출이 확인되는 종목만 봅니다.",
            "impacts": "매출·마진·현금흐름, 수급, 시간표",
            "paths": "수출통제, 공급망, CAPEX, 정책 타임라인",
            "sectors": "반도체/AI, 데이터센터 전력 인프라",
            "failure": "부처 공고, 적용 품목, 고객 CAPEX·수주 반응이 없으면 기대감 재료로 약화됩니다.",
        }
    if (
        "strong dollar" in low
        and any(term in low for term in ("weaker", "weak dollar"))
    ):
        return {
            **common,
            "revision": "trump-strong-weaker-dollar-ko-v1",
            "title": "트럼프, 강달러 선호에도 약달러 수익 효과 강조",
            "core": "트럼프는 강달러를 선호하지만 약달러가 수익에 유리하다고 말했습니다.",
            "investment": "미국채 금리와 달러가 움직이면 성장주 할인율, 원/달러, 외국인 수급이 먼저 반응할 수 있습니다.",
            "korea": "원/달러, 외국인 현물·선물 수급, 반도체·수출주와 고밸류 성장주를 함께 확인합니다.",
            "impacts": "밸류에이션/할인율, 수급",
            "paths": "금리, 환율, 외국인 수급",
            "sectors": "금리·환율 민감주, 수출주, 성장주",
            "failure": "미국채 금리·DXY·원/달러·외국인 수급이 동행하지 않으면 발언성 변동으로 끝납니다.",
        }
    if "value of the dollar" in low and any(term in low for term in ("great", "good", "strong")):
        return {
            **common,
            "revision": "trump-dollar-value-ko-v1",
            "title": "트럼프, 달러 가치 긍정 평가",
            "core": "트럼프는 달러 가치를 긍정적으로 평가했다고 밝혔습니다.",
            "investment": "달러 방향은 원/달러와 외국인 수급, 수출주 환산 실적에 영향을 줄 수 있습니다.",
            "korea": "원/달러, 외국인 현물·선물 수급과 수출주만 확인합니다.",
            "impacts": "밸류에이션/할인율, 수급",
            "paths": "환율, 외국인 수급",
            "sectors": "환율 민감주, 수출주",
            "failure": "DXY·원/달러·외국인 수급이 동행하지 않으면 발언성 변동으로 끝납니다.",
        }
    high_rate_match = re.search(
        r"(?:interest\s+)?rate(?:s|\s+is|\s+are)?\s+(?:is\s+|are\s+)?(?:at\s+least\s+)?"
        r"(\d+(?:\.\d+)?)\s+(?:percentage\s+)?points?\s+too\s+high",
        low,
    )
    if high_rate_match:
        points = high_rate_match.group(1)
        return {
            **common,
            "revision": "trump-rates-too-high-ko-v1",
            "title": f"트럼프, 미국 금리 {points}%p 이상 과도하다고 주장",
            "core": f"트럼프는 미국 금리가 최소 {points}%p 높다며 인하를 요구했습니다.",
            "investment": "정책 압박이 국채금리와 달러를 움직이면 성장주 할인율과 원/달러가 반응할 수 있습니다.",
            "korea": "원/달러, 외국인 수급과 고밸류 성장주만 확인합니다.",
            "impacts": "밸류에이션/할인율, 수급",
            "paths": "금리, 환율, 외국인 수급",
            "sectors": "금리·환율 민감주, 성장주",
            "failure": "연준 반응과 미국채 금리·DXY 변화가 없으면 발언성 재료로 끝납니다.",
        }
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
        f"🚨 신뢰외신 정책·규제 고충격 워치 · {now:%Y년 %m월 %d일 %H:%M KST}",
        "공식 발표 전 정책 뉴스 1건 확인",
        "",
        *render_alert_section(rule, items, now, index=1, source_limit=3),
        "투자 조언이 아닌 참고용 정책·규제 알림입니다.",
    ]
    return "\n".join(lines) + "\n"


def render_alert_bundle(alerts: list[dict], now: dt.datetime, limit: int = 3) -> str:
    selected = alerts[:limit]
    lines = [
        f"🚨 신뢰외신 정책·규제 고충격 워치 · {now:%Y년 %m월 %d일 %H:%M KST}",
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
