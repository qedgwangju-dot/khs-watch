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
    from khs_article_detail import extract_article_detail
except ImportError:  # pragma: no cover - supports module-style local tests.
    from scripts.khs_policy_alert_explainer import ensure_explained
    from scripts.khs_article_detail import extract_article_detail
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
AI_FORCE_ALERT_PATH = OUT_DIR / "khs_ai_force_policy_alert.md"
AI_FORCE_TITLE_PATH = OUT_DIR / "khs_ai_force_policy_title.txt"

OFFICIAL_DIRECT_STORIES = {
    "us_congress_chinese_optical_transceiver_restriction": (
        (
            "https://www.mccormick.senate.gov/news/press-releases/senators-mccormick-gallego-cornyn-fetterman-introduce-bill-to-keep-chinese-transceivers-out-of-u-s-national-security-systems/",
            "SENATORS MCCORMICK, GALLEGO, CORNYN, FETTERMAN INTRODUCE BILL TO KEEP CHINESE TRANSCEIVERS OUT OF U.S. NATIONAL SECURITY SYSTEMS",
            "U.S. Senate (Sen. Dave McCormick)",
        ),
    ),
    "us_dow_project_meridian_future_warfare": (
        (
            "https://www.mitre.org/news-insights/publication/project-meridian",
            "Project Meridian",
            "MITRE",
        ),
        (
            "https://www.army.mil/article/295897/hegseth_delivers_state_of_the_force_address_outlines_series_of_new_initiatives",
            "Hegseth delivers 'State of the Force' address, outlines series of new initiatives",
            "U.S. Army",
        ),
    ),
    "us_dow_autonomous_warfare_execution": (
        (
            "https://www.army.mil/article/295897/hegseth_delivers_state_of_the_force_address_outlines_series_of_new_initiatives",
            "Hegseth delivers 'State of the Force' address, outlines series of new initiatives",
            "U.S. Army",
        ),
        (
            "https://www.army.mil/article/295913/army_announces_futures_and_autonomous_systems_command",
            "Army announces Futures and Autonomous Systems Command",
            "U.S. Army",
        ),
    ),
}

OFFICIAL_API_STORIES = {
    "us_fcc_upper_c_band_auction115": (
        (
            "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bterm%5D=Auction+115+Upper+C-Band&order=newest&per_page=20",
            "2026-15725",
            "미 연방관보 FCC",
        ),
    ),
}

# FCC final Commission items are exposed as plain-text attachments even when
# the public document landing page is not reliably indexed by Google News.
# Fetching the official text directly keeps these three tracks first-party and replay-safe.
OFFICIAL_TEXT_STORIES = {
    "us_fcc_space_nepa_reform": (
        (
            "https://docs.fcc.gov/public/attachments/FCC-26-64A1.txt",
            "https://docs.fcc.gov/public/attachments/FCC-26-64A1.pdf",
            "FCC 26-64",
            "Federal Communications Commission",
        ),
    ),
    "us_fcc_satellite_spectrum_abundance": (
        (
            "https://docs.fcc.gov/public/attachments/FCC-26-65A1.txt",
            "https://docs.fcc.gov/public/attachments/FCC-26-65A1.pdf",
            "FCC 26-65",
            "Federal Communications Commission",
        ),
    ),
    "us_fcc_satellite_spectrum_followon_fnprm": (
        (
            "https://docs.fcc.gov/public/attachments/FCC-26-65A1.txt",
            "https://docs.fcc.gov/public/attachments/FCC-26-65A1.pdf",
            "FCC 26-65",
            "Federal Communications Commission",
        ),
    ),
    "us_fcc_foreign_energy_inverter_ban": (
        (
            "https://docs.fcc.gov/public/attachments/DA-26-786A1.txt",
            "https://docs.fcc.gov/public/attachments/DA-26-786A1.pdf",
            "DA 26-786",
            "Federal Communications Commission",
        ),
        (
            "https://docs.fcc.gov/public/attachments/DA-26-870A1.txt",
            "https://docs.fcc.gov/public/attachments/DA-26-870A1.pdf",
            "DA 26-870",
            "Federal Communications Commission",
        ),
        (
            "https://docs.fcc.gov/public/attachments/DA-26-957A1.txt",
            "https://docs.fcc.gov/public/attachments/DA-26-957A1.pdf",
            "DA 26-957",
            "Federal Communications Commission",
        ),
        (
            "https://docs.fcc.gov/public/attachments/DA-26-996A1.txt",
            "https://docs.fcc.gov/public/attachments/DA-26-996A1.pdf",
            "DA 26-996",
            "Federal Communications Commission",
        ),
    ),
}

ANALYST_DIRECT_STORIES = {
    "us_fcc_chinese_optical_transceiver_ban": (
        (
            "https://money.udn.com/money/story/5612/9791710",
            "https://money.udn.com/money/story/5612/9791710",
            "美訂光通訊新規 台鏈利多 聯亞、華星光等迎轉單",
            "經濟日報",
            "2026-10-03T02:43:54+08:00",
        ),
        (
            "https://money.udn.com/money/story/5612/9790549",
            "https://money.udn.com/money/story/5612/9790549",
            "FCC 光模組限制即將出爐？台、美供應鏈皆有望受惠",
            "經濟日報",
            "2026-10-02T13:14:04+08:00",
        ),
    ),
}

DIRECT_STORY_URLS = {
    "us_fcc_chinese_optical_transceiver_ban": (
        (
            "https://www.devdiscourse.com/article/politics/3959328-exclusive-trump-administration-drafting-ban-on-chinese-data-center-devices-sources-say",
            "https://www.reuters.com/world/trump-administration-drafting-ban-chinese-data-center-devices-sources-say-2026-08-04/",
        ),
    ),
}
TITLE_PATH = OUT_DIR / "khs_trusted_policy_news_title.txt"
ALERTS_JSON_PATH = OUT_DIR / "khs_trusted_policy_news_alerts.json"

MAX_AGE_HOURS = int(os.getenv("KHS_TRUSTED_NEWS_MAX_AGE_HOURS", "72"))
RULE_MAX_AGE_HOURS = {
    # One-time recovery lane for the already-official Auction 115 schedule plus
    # the later FCC Chair $100B multi-auction context that was missed on Telegram.
    "us_fcc_upper_c_band_auction115": 24 * 75,
    # These FCC items were released before their dedicated rules produced a
    # confirmed Telegram delivery. Keep a bounded recovery window so the missed
    # official stages can be sent once, then semantic seen-state prevents repeats.
    "us_fcc_space_nepa_reform": 24 * 14,
    "us_fcc_satellite_spectrum_abundance": 24 * 14,
    "us_fcc_satellite_spectrum_followon_fnprm": 24 * 14,
    # The robot/inverter Covered List baseline was adopted on 2026-07-28.
    # Keep a bounded recovery window for source verification, while the
    # semantic event key below prevents article republication dates from
    # becoming false "new official stage" alerts.
    "us_fcc_foreign_energy_inverter_ban": 24 * 90,
    # Backfill only the verified launch/current execution stages once; after
    # that semantic event keys prevent republications from becoming new alerts.
    "us_dow_project_meridian_future_warfare": 24 * 7,
    "us_dow_autonomous_warfare_execution": 24 * 7,
}

def max_age_hours_for_rule(rule: "StoryRule") -> int:
    return RULE_MAX_AGE_HOURS.get(rule.key, MAX_AGE_HOURS)

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
    "federal communications commission",
    "fcc",
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
    "federal communications commission": 0,
    "fcc": 0,
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
    "mitre": 0,
    "u.s. army": 0,
    "us army": 0,
    "politico": 8,
}

TRUSTED_WIRE_RELAY_SOURCES = {
    "aol.com",
    "devdiscourse",
    "devdiscourse.com",
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
        key="us_dow_project_meridian_future_warfare",
        title="미 국방부 Project Meridian 미래전 연구·권고 변화",
        google_queries=(
            "\"Project Meridian\" Musk Luckey Gingrich MITRE future warfare",
            "\"Project Meridian\" report recommendations January 28 2027",
            "\"Project Meridian\" Department of War MITRE",
            "\"Project Meridian\" procurement testing fielding contract award",
        ),
        required_groups=(
            ("project meridian",),
            ("future warfare", "future of warfare", "battlefields of the future", "warfare"),
            ("musk", "luckey", "gingrich", "mitre", "emil michael", "chief technology officer", "technology"),
            (
                "commission", "commissioned", "co-direct", "co-director", "participant", "participants",
                "report", "recommendation", "recommendations", "actionable solutions",
                "developing", "testing", "fielding", "submitted", "released",
            ),
        ),
        core=(
            "미 국방부가 Project Meridian을 통해 미래 전장을 연구하고 필요한 무기·기술과 실행 가능한 개발·시험·전력화 과제를 "
            "도출하도록 했습니다. Elon Musk·Palmer Luckey·Newt Gingrich가 공동주도하고 MITRE가 독립 연구를 이끕니다."
        ),
        impact="미 국방 기술 우선순위, AI·자율·로봇·지향성에너지·바이오, 방산기술 생태계 | 시간표·수급·돈 버는 능력",
        point=(
            "핵심은 인물 참여 자체가 아니라 120일 연구 결과가 실제 예산·조달·시험·전력화 우선순위로 연결되는지입니다. "
            "공개 보고서와 기밀 부록의 권고가 후속 프로그램으로 전환될 때 투자 영향이 커집니다."
        ),
        counter=(
            "Project Meridian은 현재 연구·자문 프로젝트입니다. 공동주도자나 참가자 선정만으로 SpaceX·Anduril 등 특정 회사의 "
            "국방 계약·수주가 확정됐다고 해석하면 안 됩니다."
        ),
        sectors="AI/자율·로봇, 우주·통신, 지향성에너지, 바이오·국방기술, 신속획득",
        impacts=("시간표", "수급", "돈 버는 능력"),
        paths=("기술 우선순위", "예산", "조달", "시험·전력화"),
        follow_up=(
            "2027년 1월 28일 이전 최종 연구결과 제출 여부, 공개 보고서·기밀 부록, 참가자 변화, "
            "권고가 예산·BAA·OTA·RFP·계약·시험·전력화로 전환되는지를 추적합니다."
        ),
        trusted_sources=("MITRE", "U.S. Army", "US Army", "U.S. Department of Defense", "U.S. Department of War", "Department of War"),
    ),
    StoryRule(
        key="us_dow_autonomous_warfare_execution",
        title="미 국방부 자율전투 지휘체계·조달 실행 변화",
        google_queries=(
            "\"Autonomous Warfare Command\" Project Agincourt four-star acquisition fielding",
            "\"AUTOWARCOM\" procurement budget contract fielding",
            "\"Futures and Autonomous Systems Command\" FASCOM Army acquisition",
            "\"Portfolio Acquisition Executive for Autonomy\" Army",
        ),
        required_groups=(
            ("autowarcom", "autonomous warfare command", "futures and autonomous systems command", "fascom", "project agincourt"),
            ("autonomous", "autonomy", "robotic", "robotics", "unmanned", "drone"),
            (
                "establish", "establishment", "stand up", "operational", "acquisition", "procurement",
                "fielding", "budget", "contract", "award", "portfolio acquisition executive",
                "acquisition executive", "project agincourt",
            ),
            ("four-star", "joint force", "project agincourt", "fascom", "futures and autonomous systems command", "portfolio acquisition executive"),
        ),
        core=(
            "9월 30일 미 국방부의 4성급 Autonomous Warfare Command 구상 뒤, 미 육군이 10월 2일 "
            "Futures and Autonomous Systems Command(FASCOM) 창설과 자율체계 조달·전력화 지시를 발표했습니다."
        ),
        impact="드론·무인체계·자율전투차량·센서·통신·엣지컴퓨팅·자율 소프트웨어 | 돈 버는 능력·수급·시간표",
        point=(
            "Project Meridian이 미래 기술을 고르는 연구축이라면 AUTOWARCOM·FASCOM·Project Agincourt는 실제 조직·획득·전력화 축입니다. "
            "예산과 조달 공고가 붙는 순간 특정 공급사 매출로 연결될 가능성이 더 높습니다."
        ),
        counter=(
            "조직 창설 지시와 예산 요청은 확정 계약이 아닙니다. 의회 예산, 조달 공고, 시험평가, 상호운용성·사이버·전자전 검증을 거쳐야 하며, "
            "2026년 4월 SOUTHCOM Autonomous Warfare Command는 이번 국방부 전체 4성급 AUTOWARCOM과 별도입니다."
        ),
        sectors="드론/무인기, 로봇·자율전투차량, 센서·C2·통신, 엣지컴퓨팅·AI, 대드론",
        impacts=("돈 버는 능력", "수급", "시간표"),
        paths=("조직 창설", "예산", "신속획득", "조달·계약", "시험·전력화"),
        follow_up=(
            "AUTOWARCOM 실제 창설·지휘관 임명, Project Agincourt 신속획득 구조, FASCOM·자율성 조달책임자, "
            "FY2028 전력화 일정, 의회 예산 확정, RFI·BAA·OTA·RFP·계약·대량구매를 추적합니다."
        ),
        trusted_sources=("U.S. Army", "US Army", "U.S. Department of Defense", "U.S. Department of War", "Department of War"),
    ),
    StoryRule(
        key="us_fcc_foreign_energy_inverter_ban",
        title="미 FCC, 외국산 전력 인버터·첨단 로봇 Covered List 편입",
        google_queries=(
            "\"DA 26-786\" FCC robots inverters Covered List",
            "\"foreign-produced advanced robotic devices\" FCC Covered List",
            "\"foreign-produced power inverters\" FCC Covered List",
            "\"DA 26-870\" FCC power inverters",
            "\"DA 26-996\" FCC advanced robotic devices conditional approval",
        ),
        required_groups=(
            (
                "inverter", "inverters", "power inverter", "power inverters",
                "robot", "robotic", "advanced robotic devices", "robotic devices",
            ),
            ("covered list", "equipment authorization", "conditional approval", "exemption"),
            (
                "foreign-produced", "foreign produced", "foreign country",
                "conditional approval", "modification", "modified",
            ),
        ),
        core=(
            "FCC는 2026년 7월 28일 DA 26-786으로 외국산 전력 인버터와 외국산 첨단 로봇을 Covered List에 추가했습니다. "
            "Covered List 대상 신규 장비는 FCC 장비인증을 받을 수 없으며, 전력 인버터는 DoW 또는 DHS, 첨단 로봇은 DoW의 "
            "조건부 승인을 받은 특정 장비·등급이 예외가 될 수 있습니다."
        ),
        impact="첨단 로봇·로봇청소기 등 이동형 연결 로봇, 전력 인버터·전력변환장치, 미국 수입·판매 인증 | 돈 버는 능력·수급·시간표",
        point=(
            "핵심은 기사 게시일이 아니라 FCC의 실제 정책 단계입니다. 최초 편입일은 2026년 7월 28일이며, "
            "2026년 8월 20일에는 전력 인버터 정의·예외가 수정됐고 이후 조건부 승인 공지가 별도 단계로 이어집니다."
        ),
        counter=(
            "모든 소비자 로봇이 자동으로 포함되는 것은 아닙니다. FCC의 '첨단 로봇' 정의를 충족해야 하며, "
            "기존 승인 장비·허용된 소프트웨어/펌웨어 변경·조건부 승인 장비는 별도 예외를 확인해야 합니다."
        ),
        sectors="첨단 로봇/피지컬 AI, 태양광 인버터/전력변환장치, 미국 장비인증/공급망",
        impacts=("돈 버는 능력", "수급", "시간표"),
        paths=("정책 타임라인", "장비인증", "공급망", "조건부 승인"),
        follow_up=(
            "새 알림은 FCC 공식 문서번호·Released 날짜가 바뀌는 경우에만 단계 변화로 처리합니다. "
            "DA 26-786(7월 28일) 재인용·재게시를 9월 30일 신규 정책으로 다시 알리지 않고, "
            "전력 인버터 정의 수정·조건부 승인·Covered List 추가 수정처럼 실제 공식 단계가 바뀔 때만 보냅니다."
        ),
    ),
    StoryRule(
        key="us_fcc_chinese_optical_transceiver_ban",
        title="미 FCC, 중국산 데이터센터 광트랜시버 규제 단계 변화",
        google_queries=(
            "Reuters Trump administration drafting ban Chinese data center devices optical transceivers FCC",
            '"drafting ban on Chinese data center devices" Reuters',
            '"Chinese optical transceivers" FCC data centers ban',
            "FCC Chinese fiber optic transceivers import ban Reuters",
            '"3.2T" FCC optical transceiver Covered List Morgan Stanley',
            '"65%" BOM optical transceiver FCC 3.2T',
            '"800G" "1.6T" "3.2T" optical transceiver FCC',
            '"Marvell" Lumentum Coherent FCC optical transceiver 3.2T',
            '"FCC" "optical transceiver" "Covered List" 3.2T',
        ),
        required_groups=(
            (
                "optical transceiver", "optical transceivers", "fiber optic transceiver",
                "fiber-optic transceiver", "optical module", "optical modules",
                "광트랜시버", "광모듈", "光收发器", "光模组",
            ),
            ("fcc", "federal communications commission"),
            ("china", "chinese", "중국", "中國", "中国产", "中國製"),
            (
                "ban", "bar", "prohibit", "import", "imports", "drafting", "restriction", "restrictions",
                "covered list", "equipment authorization", "3.2t", "65%", "65 percent",
                "phase in", "phased", "미국산", "미국 함량", "美国产", "美國含量",
            ),
        ),
        core=(
            "현재 공개 FCC 문서에서는 중국산 데이터센터 광트랜시버를 겨냥한 최종 규칙이 확인되지 않았습니다. "
            "Reuters는 2026년 8월 4일 신규 중국산 광트랜시버 수입제한 초안을 보도했고, "
            "Morgan Stanley의 10월 1일 보고서는 3.2T부터 제한하고 미국산 부품의 BOM 가치가 65% 이상이면 "
            "예외가 가능할 수 있다는 정책 시나리오를 제시했습니다."
        ),
        impact="광트랜시버/광통신, DSP·레이저·InP 광원 공급망, AI 데이터센터 네트워크 | 매출·마진·현금흐름·수급·시간표",
        point=(
            "3.2T·65% 시나리오가 공식화되면 800G·1.6T 기존 세대의 단기 공급 충격보다 "
            "3.2T에서 Marvell 계열 DSP와 Lumentum·Coherent 계열 레이저처럼 고가 핵심부품의 원산지·가치비중이 더 중요해집니다."
        ),
        counter=(
            "3.2T 적용, 65% BOM 기준, 이르면 10월 발표, 2028년 출하 확대·2029년 광범위 배포는 "
            "현재 FCC 확정 문구가 아니라 Morgan Stanley 분석과 업계 전망입니다. FCC가 범위를 바꾸거나 연기·철회할 수도 있습니다."
        ),
        sectors="광트랜시버/광통신, DSP, 레이저·InP 광원, AI 데이터센터 네트워크, 중국 대체·우방국 공급망",
        impacts=("매출·마진·현금흐름", "수급", "시간표"),
        paths=("정책 타임라인", "세대 전환", "BOM 가치비중", "공급망", "고객 인증"),
        follow_up=(
            "신규 알림은 ① FCC 공식 문서번호·Covered List 편입 ② 800G·1.6T·3.2T 중 실제 적용 세대 "
            "③ 65% 기준의 분모·원산지·미국/우방국 인정범위 ④ 중국 조립 허용 여부 ⑤ 발효일·기존모델 유예 "
            "⑥ 조건부 승인·면제 ⑦ Marvell DSP·Lumentum/Coherent 레이저·InP 기판 공급과 하이퍼스케일러 인증 변화가 "
            "실제로 확인될 때 단계 변화로 보냅니다."
        ),
        trusted_sources=("經濟日報", "Economic Daily News"),
    ),
    StoryRule(
        key="us_congress_chinese_optical_transceiver_restriction",
        title="미 의회, 중국산 광트랜시버 정부 민감 시스템 사용 제한 법안 발의",
        google_queries=(
            '"US lawmakers aim to keep China\'s datacenter tech out of sensitive government systems" Reuters',
            '"Securing National Security Systems from Chinese Optical Transceivers Act"',
            '"McCormick" "Gallego" "Cornyn" "Fetterman" optical transceivers Reuters',
            '"InnoLight" "Eoptolink" federal government optical transceivers bill Reuters',
            '"Chinese transceivers" lawmakers "national security systems" Reuters',
        ),
        required_groups=(
            ("china", "chinese", "innolight", "eoptolink"),
            ("lawmakers", "senators", "legislation", "bill", "act", "congress", "federal government"),
            ("data center", "datacenter", "government systems", "national security systems", "sensitive government systems", "transceiver"),
            ("keep", "bar", "prohibit", "restrict", "restriction", "sensitive", "national security"),
        ),
        core=(
            "미 상원의원들이 중국산 광트랜시버를 연방정부의 민감한 국가안보 시스템에서 배제하는 "
            "초당적 법안을 발의했습니다. InnoLight·Eoptolink와 자회사·계열사가 우선 대상이고, "
            "이들 업체의 펌웨어·소프트웨어·부품이 들어간 적용 대상 광트랜시버까지 포함됩니다. "
            "법안이 통과되면 5년 전환기간 뒤 조달 제한이 적용되며 현재는 발의 단계입니다."
        ),
        impact="광통신/광트랜시버, AI 데이터센터 네트워크, 미국 연방조달, 중국 대체 공급망 | 돈 버는 능력·수급·시간표",
        point=(
            "기존 FCC의 수입규제 검토보다 한 단계 구체화된 입법 신호입니다. InnoLight의 Section 1260H 지정 뒤 "
            "연방조달 제한으로 규제 연속선이 확장됐고, Commerce에는 미국·동맹국 생산능력 평가와 신뢰 공급망 강화 전략 수립을 요구합니다."
        ),
        counter=(
            "적용 범위는 현재 법안 문구상 연방정부의 민감한 국가안보 시스템이며 미국의 모든 상업용·하이퍼스케일러 "
            "데이터센터를 즉시 금지하는 조치는 아닙니다. 대체 공급원이 없으면 제한적·갱신 가능한 면제가 가능하고 각 면제는 의회 보고 대상입니다."
        ),
        sectors="광트랜시버/광통신, AI 데이터센터 네트워크, 미국 연방조달, 중국 대체 공급망",
        impacts=("돈 버는 능력", "수급", "시간표"),
        paths=("입법 타임라인", "연방조달", "공급망", "생산능력"),
        follow_up=(
            "위원회 심사·상하원 통과·대통령 서명, War·Commerce의 추가 지정기업, 면제 건수·갱신·의회 보고를 추적합니다. "
            "Commerce의 미국·동맹국 생산능력 평가와 공급망 전략, Coherent·Lumentum·Applied Optoelectronics 등 대체 공급사의 증설·납기도 확인합니다."
        ),
        trusted_sources=("Dave McCormick", "Senator Dave McCormick", "U.S. Senate"),
    ),
    StoryRule(
        key="us_fcc_upper_c_band_auction115",
        title="미 FCC, Upper C-band Auction 115 2027 경매 일정·대역 확정",
        google_queries=(
            '"Auction 115" "Upper C-Band" FCC April 27 2027',
            '"upcoming spectrum auctions" "$100 billion" Brendan Carr Reuters',
            '"Upper C-Band" 160 megahertz 3248 licenses FCC Reuters',
            '"Auction of Flexible-Use Licenses" "Auction 115"',
        ),
        required_groups=(
            ("auction 115", "upper c-band", "upper c band"),
            ("fcc", "federal communications commission", "federal register"),
            ("2027", "april 27", "3.98", "3980", "160 megahertz", "160 mhz"),
        ),
        core=(
            "FCC는 Auction 115에서 3.98~4.14GHz Upper C-band 160MHz를 20MHz×8블록으로 나눠 "
            "미 본토 406개 PEA에 총 3,248개 면허를 공급하고, 입찰 개시를 2027년 4월 27일로 잠정 예정했습니다."
        ),
        impact="미국 통신장비·5G/차세대 무선망, 기지국 안테나·필터·중계기·프론트홀 | 돈 버는 능력·수급·시간표",
        point=(
            "Brendan Carr FCC 위원장이 향후 수년간 여러 주파수 경매의 누적 수입이 1,000억달러를 넘을 수 있다고 밝혔습니다. "
            "이는 Auction 115 단일 경매액이 아니라 후속 경매까지 합친 전망이며, 실제 장비매출은 통신사 낙찰 후 CAPEX·발주로 연결돼야 합니다."
        ),
        counter=(
            "Auction 115 경매는 2027년에 열리지만 FCC 전환 일정상 상위 75개 PEA의 신규 지상 무선 서비스는 "
            "2030년 12월 31일부터 가능하고, 나머지 지역은 2031년 7월 1일이 기준입니다. "
            "따라서 2027년 경매 직후 전국 장비매출이 즉시 발생한다고 보면 안 됩니다."
        ),
        sectors="통신장비/5G·6G, 기지국 안테나·필터, DAS·중계기, 프론트홀·광전송",
        impacts=("돈 버는 능력", "수급", "시간표"),
        paths=("주파수 경매", "통신사 CAPEX", "장비 발주", "망 구축 시간표"),
        follow_up=(
            "최종 입찰절차·최저입찰가, 적격 입찰자, AT&T·Verizon·T-Mobile·신규 사업자 낙찰, 통신사 CAPEX 상향, "
            "삼성전자·Ericsson·Nokia 수주, KMW·에이스테크·쏠리드·에치에프알 실제 주문을 순서대로 추적합니다."
        ),
        trusted_sources=("미 연방관보 FCC",),
    ),
    StoryRule(
        key="us_fcc_space_nepa_reform",
        title="미 FCC, 우주 기반 운영의 NEPA 환경심사 범위 축소",
        google_queries=(
            '"Modernizing the Commission’s National Environmental Policy Act Rules" FCC space-based operations September 30 2026',
            '"space-based operations" "major Federal action" FCC NEPA satellite',
            '"FCC" "NEPA" satellite launch deployment operation space stations 2026',
            '"actions associated with space-based operations" FCC NEPA September 30 2026',
            '"not major Federal actions" FCC satellite earth stations space-based operations',
        ),
        required_groups=(
            ("fcc", "federal communications commission"),
            ("nepa", "national environmental policy act"),
            ("space-based operations", "space station", "space stations", "satellite", "satellites"),
            ("major federal action", "major federal actions", "mfa", "environmental review", "environmental assessment"),
        ),
        core=(
            "FCC는 안테나 구조물 등록이 필요하지 않은 범위의 스펙트럼 인가·위성 지상국 배치와 "
            "발사·배치·우주국 운용 등 우주 기반 운영 관련 FCC 조치를 NEPA상 '주요 연방행위(MFA)'로 보지 않기로 했습니다."
        ),
        impact="위성통신·LEO/NGSO 위성군, 지상국·게이트웨이, 우주 인프라 | 시간표·할인율·돈 버는 능력",
        point=(
            "핵심은 '위성군 프로젝트가 모든 환경규제에서 면제'가 아니라 FCC가 행사하는 스펙트럼 인가·우주 기반 운영 관련 "
            "NEPA 심사 트리거의 범위가 줄어드는 것입니다. 허가 절차 불확실성이 낮아지면 위성 배치·지상국 구축 시간표가 빨라질 수 있습니다."
        ),
        counter=(
            "FAA의 발사·통제된 재진입 인허가와 환경심사, 안테나 구조물 등록이 필요한 지상시설, 궤도잔해·주파수 간섭·안전 규정까지 사라지는 것은 아닙니다. "
            "따라서 FCC NEPA 개정은 '모든 환경규제 면제'나 위성군 자동 승인으로 해석하면 안 됩니다."
        ),
        sectors="위성통신/LEO·NGSO, 지상국·게이트웨이, 우주 인프라·발사서비스",
        impacts=("시간표", "할인율", "돈 버는 능력"),
        paths=("인허가", "규제비용", "위성 배치", "지상국 구축"),
        follow_up=(
            "Federal Register 게재·효력발생일, 소송·집행정지 여부, FCC 위성·지상국 허가 처리기간, "
            "SpaceX·Amazon Leo/Project Kuiper·AST SpaceMobile 등 사업자의 실제 신규 허가·배치 증가를 추적합니다."
        ),
        trusted_sources=("Federal Communications Commission", "FCC"),
    ),
    StoryRule(
        key="us_fcc_satellite_spectrum_abundance",
        title="미 FCC, 위성통신용 1,050MHz 주파수 추가 개방",
        google_queries=(
            '"Satellite Spectrum Abundance" FCC 12.7 42 GHz September 30 2026',
            '"1,050 megahertz" satellite FCC 12.7 42',
            '"more than 1,000 megahertz" satellite broadband FCC 42 GHz 12.7 GHz',
            '"12.7-13.25 GHz" "42-42.5 GHz" FCC fixed-satellite service September 30 2026',
            '"1,050 megahertz" FCC satellite broadband September 30 2026',
        ),
        required_groups=(
            ("fcc", "federal communications commission"),
            ("satellite spectrum abundance", "satellite broadband", "fixed-satellite service", "fss"),
            ("12.7", "12.7-13.25", "42 ghz", "42-42.5"),
            ("1,050", "1050", "1,000 megahertz", "1000 megahertz", "more than 1,000"),
        ),
        core=(
            "FCC는 12.7~13.25GHz 550MHz에서 위성 고정통신서비스(FSS) 상·하향 운용을 확대하고, "
            "42~42.5GHz 500MHz에서는 개별 허가된 위성 게이트웨이·피더링크 지구국으로의 FSS 하향 운용을 허용해 총 1,050MHz를 추가 개방했습니다."
        ),
        impact="위성광대역·항공/해상 연결·게이트웨이·feeder link·ESIM | 돈 버는 능력·수급·시간표",
        point=(
            "추가 주파수는 소비자 단말 downlink, 항공·해상 이동형 지구국, 게이트웨이·feeder link 용량 확대에 연결될 수 있어 "
            "위성망의 가입자·트래픽 증가를 기존 주파수 혼잡 없이 수용할 여지를 늘립니다."
        ),
        counter=(
            "1,050MHz는 단일 사업자에게 독점 배정된 용량이 아니며, 실제 매출은 사업자별 면허·주파수 조정·단말/지상국 투자·위성 발사로 이어져야 합니다. "
            "12.7GHz·42GHz의 기존 지상 서비스와 간섭 보호 조건도 남습니다."
        ),
        sectors="위성광대역, 항공·해상 위성통신, 게이트웨이·지상국, 위성 안테나·RF 부품",
        impacts=("돈 버는 능력", "수급", "시간표"),
        paths=("주파수", "위성 용량", "지상국 CAPEX", "가입자·트래픽"),
        follow_up=(
            "최종 규칙의 Federal Register 게재·효력발생일, SpaceX·Amazon Leo/Project Kuiper·기타 NGSO 사업자의 실제 대역 사용 신청, "
            "지상국·ESIM·게이트웨이 발주를 추적합니다. 별도 후속 트랙으로 Ku/Ka 1,450MHz와 D-band 138.25GHz 추가 확대 FNPRM의 최종 규칙 전환도 감시합니다."
        ),
        trusted_sources=("Federal Communications Commission", "FCC"),
    ),
    StoryRule(
        key="us_fcc_satellite_spectrum_followon_fnprm",
        title="미 FCC, Ku/Ka·D-band 위성 주파수 추가 확대 절차",
        google_queries=(
            '"1,450 megahertz" FCC satellite Ku Ka D-band',
            '"138.25 gigahertz" FCC satellite D-band',
            '"Spectrum Abundance FNPRM" 1450 megahertz 138.25 gigahertz',
            '"satellite communications" "1,450 megahertz" "138.25 gigahertz"',
        ),
        required_groups=(
            ("fcc", "federal communications commission"),
            ("satellite", "satellite communications", "fixed-satellite service", "fss"),
            ("1,450", "1450", "138.25"),
            ("further notice", "fnprm", "seek comment", "comment", "proposed", "proposal", "final rule", "report and order", "adopted", "finalized"),
        ),
        core=(
            "FCC는 이미 개방한 1,050MHz와 별도로 Ku·Ka 대역 1,450MHz와 D-band 138.25GHz를 "
            "위성통신에 더 집중적으로 쓰는 방안을 추가 의견수렴(FNPRM) 단계에서 검토하고 있습니다."
        ),
        impact="위성광대역·위성 간 링크·게이트웨이·RF/안테나·고주파 부품 | 시간표·돈 버는 능력",
        point=(
            "이 물량은 아직 최종 개방이 아니라 후속 규칙제정 절차입니다. 최종 채택되면 현재 1,050MHz보다 훨씬 큰 추가 용량이 열려 "
            "차세대 위성망의 게이트웨이·단말·고주파 RF 장비 투자 규모를 다시 키울 수 있습니다."
        ),
        counter=(
            "FNPRM은 의견수렴 단계이므로 1,450MHz·138.25GHz 전부가 그대로 최종 할당된다고 가정하면 안 됩니다. "
            "기존 사용자 보호·간섭 조건·기술규칙과 실제 최종 대역폭이 바뀔 수 있습니다."
        ),
        sectors="위성광대역, 위성 간 링크, 게이트웨이·지상국, RF 프론트엔드·안테나",
        impacts=("시간표", "돈 버는 능력"),
        paths=("규칙제정", "주파수", "지상국 CAPEX", "위성 네트워크 용량"),
        follow_up=(
            "Federal Register 의견수렴 기한, 주요 사업자 의견서, 최종 Report and Order 채택 여부, 실제 사용 신청·게이트웨이 발주를 추적합니다."
        ),
        trusted_sources=("Federal Communications Commission", "FCC"),
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
        key="us_china_ai_safety_talks",
        title="미·중, AI 안전 통지체계 협의: 정상회담 후속 확인",
        google_queries=(
            "Reuters Bessent He Lifeng AI safety notifications talks",
            "Reuters US China artificial intelligence safety notification mechanism Bessent He",
            "site:reuters.com Bessent China AI safety notification He Lifeng",
        ),
        required_groups=(
            ("bessent", "treasury secretary", "u.s. treasury"),
            ("he lifeng", "chinese vice premier", "vice premier"),
            ("ai", "artificial intelligence"),
            ("safety", "notification", "notifications", "national security", "talks", "mechanism"),
        ),
        core="미·중 장관급 협의에서 AI 안전 통지체계가 의제로 올라간 사안입니다.",
        impact="반도체/AI, 클라우드/보안 AI, 미중 기술규제 | 시간표·수급·돈 버는 능력",
        point="양국이 실제 통지체계나 공동 안전원칙을 채택하면 모델 배포·사이버안보·첨단칩 통제의 정책 경로가 달라질 수 있습니다.",
        counter="현재는 미국 측 제안과 협의 단계로, 중국의 수용·구체 범위·법적 구속력은 확정되지 않았습니다.",
        sectors="반도체/AI, 클라우드/보안 AI, 미중 기술규제",
        impacts=("시간표", "수급", "돈 버는 능력"),
        paths=("미중 AI 협의", "정책 타임라인", "수출통제", "국가안보"),
        follow_up="2026년 9월 24일 정상회담에서 AI 안전 통지체계가 채택되는지, 적용 대상·통지 요건·수출통제와의 관계가 구체화되는지 확인합니다.",
    ),
    StoryRule(
        key="trump_direct_policy_remarks_watch",
        title="트럼프 대통령 직접 발언, 시장 영향 정책 신호",
        google_queries=(
            "site:reuters.com Trump AI force AI czar adviser White House",
            "\"AI force\" \"AI czar\" Trump Reuters",
            "\"new AI adviser\" Trump Reuters",
            "Trump AI force executive order budget procurement Reuters",
            "Trump AI czar appointment White House Reuters",
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
            ("says", "said", "remarks", "comments", "announces", "backs", "orders", "warns", "threatens", "signals", "vows", "signs", "creates", "establishes", "appoints", "names", "말했다", "밝혔다", "발언", "언급", "임명", "창설"),
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
        try:
            parsed = dt.datetime.fromisoformat(value)
        except (TypeError, ValueError):
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
            r"\b(?:president\s+)?trump\s+(?:says|said|remarks|comments|announces|backs|orders|warns|threatens|signals|vows|signs|creates|establishes|appoints|names)\b",
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

    # Some FCC Commission items are available first as official plain-text
    # attachments. Read those exact documents before falling back to news RSS.
    for fetch_url, canonical_url, document_number, source_label in OFFICIAL_TEXT_STORIES.get(rule.key, ()):
        try:
            raw = fetch_text(fetch_url, timeout=12)
        except Exception as exc:
            print(f"trusted_policy_news=official_text_failed key={rule.key} error={type(exc).__name__}: {exc}")
            continue
        raw_plain = clean_text(raw)
        normalized_doc = re.sub(r"[^a-z0-9]", "", document_number.lower())
        normalized_raw = re.sub(r"[^a-z0-9]", "", raw_plain.lower())
        released_match = re.search(
            r"\bReleased:\s*(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
            r"(\d{1,2}),\s+(20\d{2})\b",
            raw_plain,
            flags=re.I,
        )
        published = None
        if released_match:
            try:
                published = dt.datetime.strptime(
                    released_match.group(0).split(":", 1)[1].strip(),
                    "%B %d, %Y",
                ).replace(tzinfo=KST)
            except ValueError:
                published = None
        title = rule.title
        haystack = f"{title} {source_label} {document_number} {raw_plain}"
        if (
            normalized_doc not in normalized_raw
            or not published
            or (now - published).total_seconds() / 3600 > max_age_hours_for_rule(rule)
            or not has_required_terms(haystack, rule)
        ):
            print(
                f"trusted_policy_news=official_text_rejected key={rule.key} "
                f"document={document_number!r} published={published!r}"
            )
            continue
        seen_links.add(canonical_url)
        items.append({
            "title": title,
            "description": raw_plain[:50000],
            "link": canonical_url,
            "source": source_label,
            "published_kst": published.isoformat(timespec="seconds"),
            "priority": 0,
        })
        print(
            f"trusted_policy_news=official_text_verified key={rule.key} "
            f"document={document_number!r}"
        )

    # Federal Register JSON metadata is used for official notices whose HTML
    # layout is not reliably parsed by the generic article-body extractor.
    for fetch_url, document_number, source_label in OFFICIAL_API_STORIES.get(rule.key, ()):
        try:
            payload = json.loads(fetch_text(fetch_url))
        except Exception as exc:
            print(f"trusted_policy_news=official_api_failed key={rule.key} error={type(exc).__name__}: {exc}")
            continue
        matched_row = next(
            (
                row for row in (payload.get("results") or [])
                if str(row.get("document_number") or "") == document_number
            ),
            None,
        )
        if not matched_row:
            print(f"trusted_policy_news=official_api_missing key={rule.key} document={document_number}")
            continue
        title = clean_text(str(matched_row.get("title") or ""))
        description = clean_text(str(matched_row.get("abstract") or matched_row.get("excerpt") or ""))
        link = clean_text(str(matched_row.get("html_url") or matched_row.get("pdf_url") or fetch_url))
        published = parse_pub_date(str(matched_row.get("publication_date") or ""))
        haystack = f"{title} {source_label} {description}"
        if (
            not title
            or not published
            or (now - published).total_seconds() / 3600 > max_age_hours_for_rule(rule)
            or not has_required_terms(haystack, rule)
        ):
            print(
                f"trusted_policy_news=official_api_rejected key={rule.key} "
                f"title={title!r} published={published!r}"
            )
            continue
        seen_links.add(link)
        items.append({
            "title": title,
            "description": description,
            "link": link,
            "source": source_label,
            "published_kst": published.isoformat(timespec="seconds"),
            "priority": 0,
        })
        print(f"trusted_policy_news=official_api_verified key={rule.key} document={document_number} title={title!r}")

    # Official first-party pages are fetched directly so a material policy step
    # cannot be missed just because a wire headline uses different agency words.
    for fetch_url, expected_title, source_label in OFFICIAL_DIRECT_STORIES.get(rule.key, ()):
        try:
            raw = fetch_text(fetch_url)
            detail = extract_article_detail(raw, expected_title)
        except Exception as exc:
            print(f"trusted_policy_news=official_direct_failed key={rule.key} error={type(exc).__name__}: {exc}")
            continue
        title = clean_text(detail.get("title"))
        description = clean_text(f"{detail.get('abstract') or ''} {detail.get('body') or ''}")
        published = parse_pub_date(detail.get("published_kst"))
        verified = bool(detail.get("body_verified"))

        # Some Senate press-release pages do not expose article metadata in the
        # generic parser even though the full first-party page is available.
        # Fall back only when the exact expected title and the rule's required
        # terms are present in the fetched official HTML.
        if not verified:
            raw_plain = clean_text(raw)
            expected_plain = clean_text(expected_title)
            if expected_plain and expected_plain.lower() in raw_plain.lower():
                title = expected_plain
                description = raw_plain[:50000]
                date_match = re.search(
                    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
                    r"(\d{1,2}),\s+(20\d{2})\b",
                    raw_plain,
                    flags=re.I,
                )
                if date_match:
                    try:
                        published = dt.datetime.strptime(date_match.group(0), "%B %d, %Y").replace(tzinfo=KST)
                    except ValueError:
                        published = None
                verified = True

            elif (
                rule.key == "us_fcc_upper_c_band_auction115"
                and "auction 115" in raw_plain.lower()
                and "upper c-band" in raw_plain.lower()
                and "april 27, 2027" in raw_plain.lower()
                and ("3.98" in raw_plain or "3980" in raw_plain)
            ):
                title = expected_plain
                description = raw_plain[:50000]
                published = dt.datetime(2026, 8, 3, tzinfo=KST)
                verified = True

        haystack = f"{title} {source_label} {description}"
        if (
            not verified
            or not published
            or (now - published).total_seconds() / 3600 > max_age_hours_for_rule(rule)
            or not has_required_terms(haystack, rule)
        ):
            print(
                f"trusted_policy_news=official_direct_rejected key={rule.key} "
                f"verified={verified!r} published={published!r}"
            )
            continue
        seen_links.add(fetch_url)
        items.append({
            "title": title,
            "description": description,
            "link": fetch_url,
            "source": source_label,
            "published_kst": published.isoformat(timespec="seconds"),
            "priority": 0,
        })
        print(f"trusted_policy_news=official_direct_verified key={rule.key} title={title!r}")
    # Direct analyst/reporting pages are tracked separately from first-party FCC
    # material.  They may trigger a research-stage alert, but never upgrade the
    # event to "공식 확인" unless a genuine FCC/Federal Register source is present.
    for fetch_url, canonical_url, expected_title, source_label, fallback_published in ANALYST_DIRECT_STORIES.get(rule.key, ()):
        try:
            raw = fetch_text(fetch_url, timeout=12)
            detail = extract_article_detail(raw, expected_title)
        except Exception as exc:
            print(f"trusted_policy_news=analyst_direct_failed key={rule.key} source={source_label!r} error={type(exc).__name__}: {exc}")
            continue
        title = clean_text(detail.get("title")) or expected_title
        description = clean_text(f"{detail.get('abstract') or ''} {detail.get('body') or ''}")
        published = parse_pub_date(detail.get("published_kst")) or parse_pub_date(fallback_published)
        verified = bool(detail.get("body_verified"))
        raw_plain = clean_text(raw)
        # Source-specific fallback: UDN pages can vary their article container.
        # Require the report identity plus all distinctive policy terms before
        # treating the direct page as body-verified.
        if (
            not verified
            and "money.udn.com" in fetch_url
            and ("Morgan Stanley" in raw_plain or "摩根士丹利" in raw_plain or "大摩" in raw_plain)
            and "FCC" in raw_plain
            and "3.2T" in raw_plain
            and ("65%" in raw_plain or "65％" in raw_plain)
        ):
            description = raw_plain[:50000]
            verified = True
        haystack = f"{title} {source_label} {description}"
        if (
            not verified
            or not published
            or (now - published).total_seconds() / 3600 > max_age_hours_for_rule(rule)
            or not has_required_terms(haystack, rule)
        ):
            print(
                f"trusted_policy_news=analyst_direct_rejected key={rule.key} source={source_label!r} "
                f"verified={verified!r} published={published!r}"
            )
            continue
        seen_links.add(canonical_url)
        items.append({
            "title": title,
            "description": description,
            "link": canonical_url,
            "source": source_label,
            "published_kst": published.isoformat(timespec="seconds"),
            "priority": 8,
        })
        print(
            f"trusted_policy_news=analyst_direct_verified key={rule.key} source={source_label!r} "
            f"title={title!r}"
        )

    for fetch_url, canonical_url in DIRECT_STORY_URLS.get(rule.key, ()):
        try:
            raw = fetch_text(fetch_url)
            expected_title = (
                "EXCLUSIVE-Trump administration drafting ban on Chinese data center devices, sources say"
                if rule.key == "us_fcc_chinese_optical_transceiver_ban"
                else rule.title
            )
            detail = extract_article_detail(raw, expected_title)
        except Exception as exc:
            print(f"trusted_policy_news=direct_failed key={rule.key} error={type(exc).__name__}: {exc}")
            continue
        title = clean_text(detail.get("title"))
        description = clean_text(f"{detail.get('abstract') or ''} {detail.get('body') or ''}")
        published = parse_pub_date(detail.get("published_kst"))
        haystack = f"{title} Devdiscourse Reuters {description}"
        if is_space_pv_pia_base_rehash_text(haystack):
            print(f"trusted_policy_news=historical_space_pv_rehash key={rule.key} title={title!r}")
            continue
        if is_polysilicon_11052_base_rehash_text(haystack):
            print(f"trusted_policy_news=historical_polysilicon_rehash key={rule.key} title={title!r}")
            continue
        if (
            not detail.get("body_verified")
            or not published
            or (now - published).total_seconds() / 3600 > MAX_AGE_HOURS
            or not has_required_terms(haystack, rule)
        ):
            print(f"trusted_policy_news=direct_rejected key={rule.key} verified={detail.get('body_verified')!r}")
            continue
        seen_links.add(canonical_url)
        items.append({
            "title": title,
            "description": description,
            "link": canonical_url,
            "source": "Devdiscourse (Reuters 보도 인용)",
            "published_kst": published.isoformat(timespec="seconds"),
            "priority": SOURCE_PRIORITY.get("reuters", 0),
        })
        print(f"trusted_policy_news=direct_verified key={rule.key} title={title!r}")
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
            if is_space_pv_pia_base_rehash_text(haystack):
                continue
            if is_polysilicon_11052_base_rehash_text(haystack):
                continue
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


SPACE_PV_PIA_BASE_TERMS = (
    "space photovoltaics research and development partnership intermediary agreement",
    "space photovoltaics (pv) research and development partnership intermediary agreement",
    "space-based energy generation",
    "solar panels in space applications",
)
SPACE_PV_STAGE_CHANGE_TERMS = (
    "awardee", "awardees", "recipient", "recipients",
    "selected for award", "selected projects", "announces selections", "announced selections",
    "has selected", "have selected", "selected the following", "awarded to",
    "selection notifications issued", "selection notifications sent", "selection notifications released",
    "awards announced",
)


def is_space_pv_pia_base_rehash_text(value: str) -> bool:
    text = clean_text(value).lower()
    if not any(term in text for term in SPACE_PV_PIA_BASE_TERMS):
        return False
    return not any(term in text for term in SPACE_PV_STAGE_CHANGE_TERMS)


def is_polysilicon_11052_base_rehash_text(value: str) -> bool:
    text = clean_text(value).lower()
    if not ("polysilicon" in text and "11052" in text):
        return False
    base_terms = (
        "minimum import price", "minimum import prices", "mip program",
        "15% ad valorem", "15 percent ad valorem",
        "adjusting imports of polysilicon", "onshoring",
    )
    if not any(term in text for term in base_terms):
        return False
    stage_change_terms = (
        "amend", "amended", "amendment", "modify", "modified", "revision", "revised",
        "waiver", "exemption", "temporary final rule", "stockpil", "import prohibition",
        "new rule", "new guidance", "changes to", "changed",
    )
    return not any(term in text for term in stage_change_terms)


def semantic_policy_event_key(item: dict) -> str:
    title_text = clean_text(str(item.get("title") or "")).lower()
    text = clean_text(
        " ".join(
            str(item.get(key) or "")
            for key in ("title", "description", "link", "source")
        )
    ).lower()
    if (
        "jay clayton" in text
        and "ai czar" in text
        and any(term in title_text for term in ("names", "named", "appoints", "appointed"))
        and not any(term in title_text for term in ("expected to", "will name", "will appoint"))
    ):
        return "us-trump-ai-czar-jay-clayton-appointed-2026-10-03"

    if "project meridian" in text:
        stage = "commissioned"
        report_release_terms = (
            "final report released", "final report published", "final report submitted",
            "findings released", "findings published", "findings submitted",
            "recommendations released", "recommendations published", "recommendations submitted",
            "public report released", "public report published", "public report submitted",
        )
        if any(term in text for term in report_release_terms):
            stage = "report"
        elif any(term in title_text for term in ("new participant", "joins project meridian", "adds participant", "expands roster", "membership update")):
            stage = "participants-" + hashlib.sha1(title_text.encode("utf-8")).hexdigest()[:10]
        elif (
            any(term in text for term in ("contract award", "contract awarded", "procurement award", "ota award", "baa award", "rfp issued"))
            and any(term in text for term in ("developing", "testing", "fielding", "procurement", "acquisition"))
        ):
            stage = "implementation-" + hashlib.sha1(title_text.encode("utf-8")).hexdigest()[:10]
        return f"us-dow-project-meridian-{stage}"

    if "futures and autonomous systems command" in text or re.search(r"\bfascom\b", text):
        return "us-dow-autonomous-warfare-army-fascom-2026-10-02"

    if ("autowarcom" in text or "autonomous warfare command" in text) and not (
        "southcom autonomous warfare command" in text
        or "u.s. southern command" in text
        or "us southern command" in text
    ):
        stage = "announced"
        if any(term in title_text for term in ("activated", "operational", "stands up", "stood up", "stand-up", "command established")):
            stage = "activated"
        elif any(term in text for term in ("appropriation", "appropriations", "funding approved", "budget enacted", "budget passed")):
            stage = "funding"
        elif any(term in text for term in ("contract award", "contract awarded", "ota award", "baa award", "procurement award", "rfp issued")):
            stage = "procurement-" + hashlib.sha1(title_text.encode("utf-8")).hexdigest()[:10]
        return f"us-dow-autonomous-warfare-{stage}"

    fcc_optical_transceiver = (
        (
            "optical transceiver" in text
            or "optical transceivers" in text
            or "fiber optic transceiver" in text
            or "fiber-optic transceiver" in text
            or "optical module" in text
            or "optical modules" in text
            or "광트랜시버" in text
            or "광모듈" in text
            or "光收发器" in text
            or "光模组" in text
        )
        and (
            "fcc" in text
            or "federal communications commission" in text
            or "fcc.gov" in text
            or "docs.fcc.gov" in text
        )
        and any(term in text for term in ("china", "chinese", "중국", "中國", "中国产", "中國製"))
    )
    if fcc_optical_transceiver:
        final_terms = (
            "added to the covered list", "adds to the covered list", "addition to the covered list",
            "final rule", "report and order", "adopted", "finalized",
            "covered list에 추가", "covered list 편입", "최종 규칙", "최종규칙", "채택",
        )
        effective_terms = (
            "takes effect", "effective date", "effective on", "becomes effective",
            "발효", "시행일", "효력 발생",
        )
        proposal_terms = (
            "notice of proposed rulemaking", "nprm", "proposed rule", "proposal",
            "draft order", "seeking comment", "request for comment", "의견수렴", "규칙안", "제안",
        )
        exemption_terms = (
            "conditional approval", "waiver", "exemption", "exception",
            "조건부 승인", "면제", "예외",
        )
        research_terms = (
            "morgan stanley", "3.2t", "65%", "65 percent",
            "800g", "1.6t", "2028", "2029",
        )
        if any(term in title_text for term in final_terms) or (
            "covered list" in text
            and any(term in title_text for term in ("adds", "added", "addition", "final", "adopts", "adopted"))
        ):
            stage = "covered-list-final"
        elif any(term in title_text for term in effective_terms):
            stage = "effective"
        elif any(term in title_text for term in proposal_terms):
            stage = "proposal"
        elif any(term in title_text for term in exemption_terms):
            stage = "exemption"
        elif any(term in text for term in research_terms):
            stage = "3p2t-65pct-research-2026-10-01"
        else:
            stage = "draft"
        return f"us-fcc-optical-transceiver-{stage}"

    optical_bill = (
        "securing national security systems from chinese optical transceivers act" in text
        or (
            "innolight" in text
            and "eoptolink" in text
            and "national security systems" in text
        )
        or (
            "광트랜시버" in text
            and "국가안보" in text
            and ("중국" in text or "中" in text)
        )
    )
    if optical_bill:
        stage = "introduced"
        if any(term in title_text for term in ("signed into law", "president signs", "enacted", "법률 서명", "대통령 서명", "법제화")):
            stage = "signed"
        elif any(term in title_text for term in ("house passes", "passed the house", "하원 통과", "하원 가결")):
            stage = "house-passed"
        elif any(term in title_text for term in ("senate passes", "passed the senate", "상원 통과", "상원 가결")):
            stage = "senate-passed"
        elif (
            any(term in title_text for term in ("committee", "위원회"))
            and any(term in title_text for term in ("advances", "approves", "reports", "markup", "통과", "가결", "심사"))
        ):
            stage = "committee"
        elif any(term in title_text for term in ("waiver", "waivers", "면제")):
            stage = "waiver"
        elif (
            any(term in title_text for term in ("commerce", "상무부"))
            and any(term in title_text for term in ("production capacity", "supply chain strategy", "assessment", "report", "생산능력", "공급망 전략", "평가", "보고서"))
        ):
            stage = "commerce-assessment"
        elif any(term in title_text for term in ("additional companies", "additional vendors", "designates", "designation", "추가 지정", "추가 기업")):
            stage = "additional-designation"
        return f"us-congress-chinese-optical-transceiver-{stage}"
    # FCC follow-up notices quote the July 28 baseline internally, so identify
    # the document carried by the current URL/headline before scanning body
    # references. Otherwise DA 26-957/996 would collapse back into DA 26-786.
    item_link = clean_text(str(item.get("link") or "")).lower()
    if (
        ("da-26-996" in item_link or "da 26-996" in title_text)
        and ("advanced robotic devices" in text or "robotic devices" in text)
    ):
        return "us-fcc-robot-conditional-approval-2026-09-18"
    if (
        ("da-26-957" in item_link or "da 26-957" in title_text)
        and ("advanced robotic devices" in text or "robotic devices" in text)
    ):
        return "us-fcc-robot-conditional-approval-2026-09-09"
    if (
        ("da-26-870" in item_link or "da 26-870" in title_text)
        and ("power inverter" in text or "power inverters" in text)
    ):
        return "us-fcc-inverter-definition-modification-2026-08-20"
    if (
        ("da-26-786" in item_link or "da 26-786" in title_text)
        and ("power inverter" in text or "advanced robotic devices" in text)
    ):
        return "us-fcc-robot-inverter-covered-list-2026-07-28"

    # Headline/text fallbacks for trustworthy republications that lack the FCC
    # document URL. Specific later stages stay ahead of the baseline fallback.
    if (
        "modification of power inverters entry on the covered list" in text
        and ("power inverter" in text or "power inverters" in text)
    ):
        return "us-fcc-inverter-definition-modification-2026-08-20"
    if (
        "conditional approval and exemption of certain routers and advanced robotic devices" in text
        and ("advanced robotic devices" in text or "robotic devices" in text)
    ):
        return "us-fcc-robot-conditional-approval-2026-09-09"
    if (
        "conditional approval and exemption of certain advanced robotic devices" in text
        and ("advanced robotic devices" in text or "robotic devices" in text)
    ):
        return "us-fcc-robot-conditional-approval-2026-09-18"
    fcc_robot_inverter = (
        (
            "addition of foreign-produced power inverters and advanced robotic devices" in text
            or (
                "foreign-produced advanced robotic devices" in text
                and "foreign-produced power inverters" in text
                and "covered list" in text
            )
        )
        and ("fcc" in text or "federal communications commission" in text or "docs.fcc.gov" in text)
    )
    if fcc_robot_inverter:
        return "us-fcc-robot-inverter-covered-list-2026-07-28"
    if "nepa" in text and ("space-based operations" in text or "space station" in text or "satellite" in text):
        stage = "adopted"
        if any(term in title_text for term in ("effective", "takes effect", "효력", "발효")):
            stage = "effective"
        elif any(term in title_text for term in ("court", "lawsuit", "challenge", "stay", "소송", "집행정지")):
            stage = "litigation"
        elif any(term in title_text for term in ("propose", "proposes", "proposed", "proposal", "notice of proposed", "제안", "초안")):
            stage = "proposal"
        return f"us-fcc-space-nepa-{stage}"
    # Distinguish the follow-on Ku/Ka/D-band proceeding from the already-adopted
    # 12.7/42 GHz order.  Use the headline for the split so a broad FCC article
    # that merely mentions both packages does not collapse the two event tracks.
    if (
        ("1,450" in title_text or "1450" in title_text or "138.25" in title_text)
        and ("satellite" in text or "fss" in text)
    ):
        stage = "proposal"
        if any(term in title_text for term in ("final rule", "report and order", "adopted", "finalized", "최종", "채택")):
            stage = "final"
        elif any(term in title_text for term in ("comment deadline", "reply comment", "의견수렴", "댓글 기한")):
            stage = "comment"
        return f"us-fcc-satellite-spectrum-followon-{stage}"
    if (
        ("satellite spectrum abundance" in text or ("12.7" in text and "42" in text))
        and ("1,050" in text or "1050" in text or "1,000 megahertz" in text or "1000 megahertz" in text or "more than 1,000" in text)
    ):
        stage = "adopted"
        if any(term in title_text for term in ("effective", "takes effect", "효력", "발효")):
            stage = "effective"
        elif any(term in title_text for term in ("application", "license", "market access", "신청", "면허")):
            stage = "operator-application"
        elif any(term in title_text for term in ("further notice", "fnprm", "comment", "추가 의견", "의견수렴")):
            stage = "further-notice"
        return f"us-fcc-satellite-spectrum-abundance-{stage}"
    if (
        "auction 115" in text
        and ("upper c-band" in text or "upper c band" in text)
    ):
        title_low = clean_text(str(item.get("title") or "")).lower()
        stage = "scheduled"
        if any(term in title_low for term in ("results", "winning bidders", "auction closes", "낙찰 결과", "낙찰자", "경매 종료")):
            stage = "results"
        elif any(term in title_low for term in ("bidding begins", "bidding opens", "auction begins", "입찰 개시", "경매 개시")):
            stage = "bidding-open"
        elif any(term in title_low for term in ("qualified bidders", "accepted applicants", "적격 입찰자", "참가자 확정")):
            stage = "qualified-bidders"
        elif any(term in title_low for term in ("final procedures", "final bidding procedures", "최종 입찰 절차", "최종 경매 절차")):
            stage = "final-procedures"
        elif any(term in title_low for term in ("minimum opening bid", "upfront payment", "최저 입찰가", "선납금")):
            stage = "pricing-terms"
        return f"us-fcc-upper-c-band-auction115-{stage}"
    if "polysilicon" in text and "11052" in text:
        if (
            "measures to restrict stockpiling" in text
            or (
                "stockpil" in text
                and (
                    "temporary final rule" in text
                    or "import prohibition" in text
                    or "new importer" in text
                    or "waiver" in text
                )
            )
        ):
            return "polysilicon-11052-stockpiling-tfr"
        if any(
            term in text
            for term in (
                "minimum import price", "minimum import prices", "mip program",
                "15% ad valorem", "15 percent ad valorem",
                "adjusting imports of polysilicon", "onshoring",
            )
        ):
            return "polysilicon-11052-base"
    if any(term in text for term in SPACE_PV_PIA_BASE_TERMS):
        if any(term in text for term in SPACE_PV_STAGE_CHANGE_TERMS):
            return "doe-space-pv-pia-selections"
        return "doe-space-pv-pia-2026-08-31"
    return ""


def semantic_policy_title(item: dict) -> str:
    key = semantic_policy_event_key(item)
    if key == "us-trump-ai-czar-jay-clayton-appointed-2026-10-03":
        return "트럼프, Jay Clayton 신임 AI 차르 임명"
    if key == "us-dow-project-meridian-commissioned":
        return "미 국방부 Project Meridian 출범: 미래전 기술 우선순위 연구"
    if key == "us-dow-project-meridian-report":
        return "미 국방부 Project Meridian 최종 보고서·권고 공개"
    if key.startswith("us-dow-project-meridian-participants-"):
        return "미 국방부 Project Meridian 참가자 구성 변화"
    if key.startswith("us-dow-project-meridian-implementation-"):
        return "Project Meridian 권고, 실제 개발·조달 단계로 전환"
    if key == "us-dow-autonomous-warfare-army-fascom-2026-10-02":
        return "미 육군 FASCOM 창설 지시: 자율무기 조달·전력화 실행"
    if key == "us-dow-autonomous-warfare-announced":
        return "미 국방부 4성급 AUTOWARCOM 창설 구상"
    if key == "us-dow-autonomous-warfare-activated":
        return "미 국방부 AUTOWARCOM 실제 창설·가동"
    if key == "us-dow-autonomous-warfare-funding":
        return "미 국방부 자율전투 예산·재원 확정 단계"
    if key.startswith("us-dow-autonomous-warfare-procurement-"):
        return "미 국방부 자율전투 조달·계약 실행 단계"
    if key == "us-fcc-optical-transceiver-draft":
        return "미 FCC, 중국산 데이터센터 광트랜시버 수입제한 초안"
    if key == "us-fcc-optical-transceiver-3p2t-65pct-research-2026-10-01":
        return "FCC 광트랜시버 규제 경로 업데이트: 3.2T·65% BOM은 Morgan Stanley 시나리오"
    if key == "us-fcc-optical-transceiver-proposal":
        return "미 FCC, 중국산 데이터센터 광트랜시버 규칙안·의견수렴"
    if key == "us-fcc-optical-transceiver-covered-list-final":
        return "미 FCC, 중국산 데이터센터 광트랜시버 Covered List 최종 범위 확정"
    if key == "us-fcc-optical-transceiver-effective":
        return "미 FCC, 중국산 데이터센터 광트랜시버 규제 발효"
    if key == "us-fcc-optical-transceiver-exemption":
        return "미 FCC, 광트랜시버 규제 조건부 승인·면제 변화"
    if key == "us-fcc-robot-inverter-covered-list-2026-07-28":
        return "미 FCC, 외국산 전력 인버터·첨단 로봇 Covered List 편입"
    if key == "us-fcc-inverter-definition-modification-2026-08-20":
        return "미 FCC, 외국산 전력 인버터 Covered List 정의·예외 수정"
    if key == "us-fcc-robot-conditional-approval-2026-09-09":
        return "미 FCC, 일부 첨단 로봇 조건부 승인·Covered List 예외"
    if key == "us-fcc-robot-conditional-approval-2026-09-18":
        return "미 FCC, 추가 첨단 로봇 조건부 승인·Covered List 예외"
    if key == "polysilicon-11052-stockpiling-tfr":
        return "미 상무부, 폴리실리콘 사재기 차단 규칙 시행"
    if key == "polysilicon-11052-base":
        return "미국, 폴리실리콘 Section 232 최저수입가격·관세 조치"
    if key == "doe-space-pv-pia-selections":
        return "미 에너지부, 우주태양광 R&D 선정 결과 발표"
    if key == "doe-space-pv-pia-2026-08-31":
        return "미 에너지부, 우주태양광 R&D 지원사업 공고"
    return ""


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
    """Deduplicate the same policy event even when publisher/title/timestamp changes."""
    semantic_key = semantic_policy_event_key(items[0]) if items else ""
    if semantic_key:
        raw = f"{FORMAT_VERSION}:semantic-policy-event-v1:{semantic_key}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
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
    if rule.key in {
        "us_dow_project_meridian_future_warfare",
        "us_dow_autonomous_warfare_execution",
    }:
        grouped: dict[str, list[dict]] = {}
        for item in items:
            key = semantic_policy_event_key(item) or story_identity(item)
            grouped.setdefault(key, []).append(item)
        return list(grouped.values())
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
    if (
        "iran" in low
        and any(term in low for term in ("hold off", "held off", "pause", "delay"))
        and any(term in low for term in ("attack", "strike"))
        and any(term in low for term in ("deal", "agreement"))
    ):
        return {
            **common,
            "revision": "trump-iran-attack-holdoff-deal-ko-v1",
            "title": "트럼프, 신속한 합의 기대하며 이란 추가 공격 보류",
            "core": "트럼프는 신속한 합의를 기대해 이란 추가 공격을 보류했습니다. 조건부 유예입니다.",
            "investment": "추가 공격 유예는 중동 위험프리미엄을 낮출 수 있지만 합의가 지연되면 재공격 위험이 남습니다.",
            "korea": "정유·화학 원가, 해운·항공 운임, 방산과 원/달러 반응을 함께 확인합니다.",
            "impacts": "매출·마진·현금흐름, 밸류에이션/할인율, 수급, 시간표",
            "paths": "지정학 리스크, 유가·운임, 환율, 정책 타임라인",
            "sectors": "정유/화학, 해운, 항공/운송, 방산/지정학",
            "failure": "신속한 합의나 공식 협상 일정이 확인되지 않고 추가 공격이 재개되면 완화 재료가 소멸합니다.",
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
    if any(term in low for term in ("ai adviser", "ai advisor", "ai czar", "ai force")):
        future_language = any(
            term in low
            for term in (
                "will appoint", "will name", "will create", "plans to", "plan to",
                "without providing details", "intends to",
            )
        )
        appointment_language = any(
            term in low
            for term in ("appoints", "appointed", "names", "named")
        ) and not future_language
        formalization_language = any(
            term in low
            for term in ("executive order", "signs", "creates", "establishes", "launches")
        ) and not future_language

        if appointment_language:
            ai_title = "트럼프, 신임 AI 차르 임명: AI 정책 지휘체계 구체화"
            ai_core = "트럼프가 신임 AI 차르 인선을 확정했습니다."
            ai_stage = "인선 확정 단계 — 소속기관·법적 권한·예산·조달권은 후속 공식문서로 확인해야 합니다."
            ai_actual = "AI 정책 총괄 인선이 발표 단계에서 실제 인선 단계로 넘어간 변화입니다."
            ai_timeline = "2026년 9월 19일 AI Force·신임 AI 차르 구상 발표 → 신임 AI 차르 인선 확정 → 조직·권한·예산 문서 확인 단계"
        elif formalization_language:
            ai_title = "트럼프, AI Force 공식화 후속: 조직·권한 문서 확인 단계"
            ai_core = "AI Force 구상이 공식 정책문서 단계로 진전됐습니다."
            ai_stage = "공식화 단계 — 문서에 적힌 소속·권한·예산·조달 범위를 원문 기준으로 확인해야 합니다."
            ai_actual = "단순 구상 발표를 넘어 AI Force의 실제 정부 조직·집행체계가 만들어지는지 확인하는 단계입니다."
            ai_timeline = "2026년 9월 19일 구상 발표 → 후속 공식 정책문서 → 조직·권한·예산·조달 집행 확인"
        else:
            ai_title = "트럼프, AI Force 창설·신임 AI 차르 임명 예고"
            ai_core = "트럼프가 AI Force 창설과 신임 AI 차르 임명을 예고했습니다."
            ai_stage = "대통령 발표 단계 — 공식 행정명령·조직도·예산·임명자는 아직 공개되지 않았습니다."
            ai_actual = "미국 정부의 AI 정책을 총괄할 새 AI 차르를 두고 AI Force를 만들겠다는 구상입니다."
            ai_timeline = "2026년 9월 19일 발표 → 2026년 9월 20일 베선트·허리펑 AI 안보·무역 회담 → 2026년 9월 24일 트럼프·시진핑 정상회담 일정"

        return {
            **common,
            "revision": "trump-ai-force-czar-ko-v3",
            "event_date": "2026년 9월 19일" if not appointment_language and not formalization_language else "",
            "title": ai_title,
            "core": ai_core,
            "stage": ai_stage,
            "actual": ai_actual,
            "timeline": ai_timeline,
            "why": "사람→조직→권한→예산→정부 AI 조달로 이어질 수 있는 새로운 AI 정책 지휘체계 신호입니다.",
            "next": "신임 AI 차르 실명·권한, AI Force 소속·법적 근거, 행정명령·대통령각서, 예산·인원·정부 AI 조달, 미중 AI 협의 결과",
            "investment": "현재 신규 확정 매출은 없으며, 예산·조달이 붙을 때 GPU·클라우드·보안 AI·데이터센터 전력 인프라로 실제 수요가 연결될 수 있습니다.",
            "korea": "한국장에서는 삼성전자·SK하이닉스 HBM과 AI 서버·전력 인프라 중 미국 정부 조달·하이퍼스케일러 CAPEX에 실제 연결되는 노출만 확인합니다.",
            "impacts": "매출·마진·현금흐름, 수급, 시간표",
            "paths": "정책 지휘체계, 정부 AI 조달, AI 인프라 CAPEX, 미중 기술경쟁",
            "sectors": "반도체/AI, 클라우드/보안 AI, 데이터센터 전력 인프라",
            "failure": "행정명령·대통령각서, 인선, 예산·조달 공고 중 하나도 뒤따르지 않으면 조직명 제안 수준에서 끝납니다.",
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
            "core": "트럼프의 우크라이나·러시아 발언으로 제재·휴전 시간표가 다시 변수로 부각됐습니다.",
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
    semantic_key = semantic_policy_event_key(items[0])
    if rule.key == "us_fcc_chinese_optical_transceiver_ban":
        if semantic_key == "us-fcc-optical-transceiver-3p2t-65pct-research-2026-10-01":
            return {
                "revision": "us-fcc-optical-transceiver-3p2t-65pct-research-ko-v1",
                "event_date": "2026년 10월 1일",
                "title": "FCC 광트랜시버 규제 경로 업데이트: 3.2T·65% BOM은 Morgan Stanley 시나리오",
                "core": "Morgan Stanley는 워싱턴 정책 미팅을 근거로 FCC의 중국산 광트랜시버 제한이 3.2T 세대부터 적용될 가능성과 미국산 부품 가치 65% 이상 예외 가능성을 제시했습니다.",
                "stage": "증권사 정책경로 추정 단계 — FCC 공식 규칙·Covered List 편입 확정이 아닙니다.",
                "actual": "공개 FCC 확정문서에서는 아직 중국산 데이터센터 광트랜시버를 특정해 3.2T 또는 65% BOM 기준을 채택한 문구가 확인되지 않았습니다.",
                "timeline": "2026년 8월 4일 Reuters 수입제한 초안 보도 → 9월 장비인증 규칙 개정에서 광트랜시버 직접 대상 미확인 → 10월 1일 Morgan Stanley 3.2T·65% 시나리오 → FCC 공식 문서 대기",
                "why": "정책이 현행 800G·1.6T를 즉시 막기보다 차세대 3.2T의 고부가 DSP·레이저 가치비중을 미국·우방국 쪽으로 유도할 가능성을 시사합니다.",
                "next": "FCC 문서번호·Covered List, 실제 적용 세대, 65% 산식과 원산지 인정범위, 중국 조립 허용 여부, 발효일·기존모델 유예, 조건부 승인·면제",
                "investment": "공식화될 경우 모듈 조립 점유율 이동보다 DSP·레이저의 가격결정력과 인증된 공급능력이 더 중요해질 수 있습니다. 현재는 확정 수주·매출이 아니라 정책 시나리오입니다.",
                "korea": "국내 기업은 3.2T 광모듈·레이저·광부품의 미국 하이퍼스케일러 인증과 실제 미국향 수주가 확인될 때만 직접 수혜로 분류합니다.",
                "headwind": "FCC가 규칙을 연기·철회하거나 65% 예외를 채택하지 않을 수 있고, InP 기판·레이저 공급능력과 고객 인증이 새 병목이 될 수 있습니다.",
                "scope_note": "3.2T·65%·이르면 10월·2028~2029 확산 일정은 FCC 확정치가 아니라 Morgan Stanley 분석·업계 전망으로 유지합니다.",
                "impacts": "매출·마진·현금흐름, 수급, 시간표",
                "paths": "정책 타임라인, 3.2T 세대전환, BOM 가치비중, DSP·레이저 공급망, 고객 인증",
                "sectors": "광트랜시버/광통신, DSP, 레이저·InP 광원, AI 데이터센터 네트워크",
                "priced_in": "중간. 광통신 종목 주가가 먼저 반응했지만 FCC 최종 규칙과 기업별 주문은 미확정입니다.",
                "counter": "9월 공개 FCC 장비인증 규칙에서 광트랜시버가 직접 대상이 아니었던 만큼 3.2T·65% 경로가 최종안과 다를 가능성이 남아 있습니다.",
                "failure": "FCC 공식 문서에서 3.2T·65%·적용일이 확인되지 않거나 2027~2028년 고객 인증·부품 수급이 따라오지 않으면 정책 기대가 실적보다 앞선 상태입니다.",
            }
        stage_map = {
            "us-fcc-optical-transceiver-draft": ("수입제한 초안 보도 단계", "미 FCC, 중국산 데이터센터 광트랜시버 수입제한 초안"),
            "us-fcc-optical-transceiver-proposal": ("FCC 규칙안·의견수렴 단계", "미 FCC, 중국산 데이터센터 광트랜시버 규칙안·의견수렴"),
            "us-fcc-optical-transceiver-covered-list-final": ("FCC Covered List·최종 규칙 확정 단계", "미 FCC, 중국산 데이터센터 광트랜시버 Covered List 최종 범위 확정"),
            "us-fcc-optical-transceiver-effective": ("규제 발효·집행 단계", "미 FCC, 중국산 데이터센터 광트랜시버 규제 발효"),
            "us-fcc-optical-transceiver-exemption": ("조건부 승인·면제 변화 단계", "미 FCC, 광트랜시버 규제 조건부 승인·면제 변화"),
        }
        stage, title_ko = stage_map.get(
            semantic_key,
            ("정책 경로 확인 단계", "미 FCC, 중국산 데이터센터 광트랜시버 규제 단계 변화"),
        )
        return {
            "revision": f"{semantic_key or 'us-fcc-optical-transceiver'}-ko-v1",
            "event_date": "",
            "title": title_ko,
            "core": "FCC의 중국산 데이터센터 광트랜시버 규제 범위·장비인증·Covered List 단계가 변했는지 확인하는 이벤트입니다.",
            "stage": stage,
            "actual": "적용 세대·BOM 기준·생산국·조립국·대상 업체·기존모델 유예·조건부 승인·면제는 해당 FCC 원문에 실제 적힌 항목만 확정값으로 사용합니다.",
            "timeline": "Reuters 초안 보도 → FCC 규칙안/의견수렴 → Covered List·최종 규칙 → 발효·장비인증 집행 → 면제·조건부 승인 후속",
            "why": "규제의 실제 경제효과는 중국 조립 여부보다 어느 세대·어느 부품가치·어느 인증단계까지 제한하는지에 따라 달라집니다.",
            "next": "3.2T·800G·1.6T 적용 여부, 65% 산식, 미국/우방국 인정범위, 발효일, 기존모델 유예, hyperscaler 인증·조달 변경",
            "investment": "확정 규칙이 3.2T·핵심부품 중심이면 DSP·레이저 공급자의 가격결정력이 상대적으로 커질 수 있고, 전면금지이면 모듈 대체 공급사의 생산능력이 더 중요해집니다.",
            "korea": "한국 기업은 미국향 실제 고객·제품세대·수주·양산·인증이 확인될 때만 직접 실적 영향으로 연결합니다.",
            "headwind": "대체 생산능력 부족, InP 기판·레이저 공급, 고객 인증, 규칙 지연·철회·예외 확대가 가장 현실적인 변동요인입니다.",
            "scope_note": "Morgan Stanley의 3.2T·65% 시나리오와 FCC 공식 확정문구를 절대 혼합하지 않습니다.",
            "impacts": "매출·마진·현금흐름, 수급, 시간표",
            "paths": "장비인증, Covered List, 세대전환, BOM 가치비중, 공급망",
            "sectors": "광트랜시버/광통신, DSP, 레이저·InP 광원, AI 데이터센터 네트워크",
            "priced_in": "공식 단계와 기업별 수주 확인 수준에 따라 달라집니다.",
            "counter": "FCC가 광트랜시버를 최종 대상에서 제외하거나 규제 범위를 좁힐 수 있습니다.",
            "failure": "공식 문서·발효일·고객 조달변화가 뒤따르지 않으면 관련주 반응은 정책 기대에 그칠 수 있습니다.",
        }
    if rule.key == "us_dow_project_meridian_future_warfare":
        if semantic_key == "us-dow-project-meridian-report":
            return {
                "revision": "us-dow-project-meridian-report-ko-v1",
                "event_date": "",
                "title": "미 국방부 Project Meridian 최종 보고서·권고 공개",
                "core": "Project Meridian의 미래전 연구 결과와 권고가 공개·제출된 단계입니다.",
                "stage": "보고서 공개·제출 단계 — 예산·조달·계약 반영은 별도 확인이 필요합니다.",
                "actual": "공개 보고서와 기밀 부록이 미래전의 핵심 능력 격차와 개발·시험·전력화 우선순위를 제시하는 단계입니다.",
                "timeline": "2026년 9월 30일 Project Meridian 출범 → 120일 연구 → 2027년 1월 28일 이전 결과 제출 목표 → 예산·조달 반영 여부 확인",
                "why": "연구 단계의 아이디어가 어떤 기술·프로그램을 우선 개발할지 공식 권고로 좁혀지는 첫 전환점입니다.",
                "next": "예산안, Program Executive Office, BAA·OTA·RFI·RFP, 시험평가·전력화 일정, 실제 계약·수주",
                "investment": "특정 기업 수혜는 권고만으로 확정하지 않고 후속 예산·조달·계약이 확인될 때만 매출로 연결합니다.",
                "korea": "한국 기업은 미 국방부 공급망·FMS·미국 현지 조달 또는 미국 주계약자 공급계약이 확인될 때만 직접 수혜로 분류합니다.",
                "headwind": "권고가 예산에 반영되지 않거나 의회 승인·획득절차·시험평가에서 지연되면 실적 전환이 늦어집니다.",
                "scope_note": "보고서 권고와 계약은 별개이며, 참가자 소속 기업의 수주를 자동 의미하지 않습니다.",
                "impacts": "매출·마진·현금흐름, 수급, 시간표",
                "paths": "기술 우선순위, 예산, 조달, 시험·전력화",
                "sectors": "AI/자율·로봇, 우주·통신, 지향성에너지, 바이오·국방기술",
                "priced_in": "보고서 내용과 후속 예산·조달 강도에 따라 달라집니다.",
                "counter": "공개 권고가 장기 연구 의제로만 남고 예산·조달로 이어지지 않을 수 있습니다.",
                "failure": "3~6개월 내 예산·조달 문서나 시험·계약 후속이 없으면 테마 기대가 실적 기대보다 앞선 상태입니다.",
            }
        if semantic_key.startswith("us-dow-project-meridian-participants-"):
            return {
                "revision": "us-dow-project-meridian-participants-ko-v1",
                "event_date": "",
                "title": "미 국방부 Project Meridian 참가자 구성 변화",
                "core": "Project Meridian의 공동주도·참가자 구성이 새로 바뀐 단계입니다.",
                "stage": "자문단 구성 변화 — 계약·수주 변화가 아닙니다.",
                "actual": "MITRE가 공개한 현 구성은 프로젝트 진행 과정에서 계속 바뀔 수 있으며, 새 인물 추가는 전문영역 우선순위를 보여주는 보조 신호입니다.",
                "timeline": "2026년 9월 30일 출범 → 2026년 10월 2일 MITRE 구성 공개 → 이후 참가자 업데이트",
                "why": "어떤 기술·산업 전문가가 추가되는지는 연구 초점 변화를 보여줄 수 있지만 매출 신호는 아닙니다.",
                "next": "최종 보고서, 공식 기술 우선순위, 예산·조달·계약 전환 여부",
                "investment": "참가자 소속기업을 수혜주로 자동 연결하지 않습니다.",
                "korea": "국내 기업 직접 영향은 공식 조달·공급망 편입이 확인될 때만 반영합니다.",
                "headwind": "이해상충 논란과 자문·조달 분리, 의회·획득 절차가 실제 사업화 속도를 제한할 수 있습니다.",
                "scope_note": "인물 참여는 기업 계약이 아닙니다.",
                "impacts": "수급, 시간표",
                "paths": "자문단, 기술 우선순위, 정책 시간표",
                "sectors": "AI/자율·로봇, 우주·통신, 방산기술",
                "priced_in": "낮음. 인물 변화만으로 실적이 바뀌지는 않습니다.",
                "counter": "참가자 확대가 프로젝트 권고나 예산을 실제로 바꾸지 않을 수 있습니다.",
                "failure": "후속 보고서·예산·조달 변화가 없으면 인물 뉴스로 끝납니다.",
            }
        if semantic_key.startswith("us-dow-project-meridian-implementation-"):
            return {
                "revision": "us-dow-project-meridian-implementation-ko-v1",
                "event_date": "",
                "title": "Project Meridian 권고, 실제 개발·조달 단계로 전환",
                "core": "Project Meridian과 연결된 기술 우선순위가 실제 개발·시험·조달 문서로 전환된 단계입니다.",
                "stage": "실행 전환 단계 — 개별 계약과 수주 금액을 별도 확인합니다.",
                "actual": "BAA·OTA·RFI·RFP·계약·시험평가 문서처럼 돈과 일정이 붙는 후속 단계입니다.",
                "timeline": "연구·자문 → 권고 → 예산·획득 문서 → 시험·계약 → 전력화",
                "why": "이 단계부터 특정 기술·공급사에 실제 매출 경로가 생길 수 있습니다.",
                "next": "계약 당사자, 계약금액, 납기, 시험평가, 양산·전력화 일정",
                "investment": "확정 계약만 직접 매출로 분류하고 제안·실증은 고객 검증 단계로 낮춰 봅니다.",
                "korea": "한국 기업은 미국 조달 직접계약·미국 주계약자 공급계약·FMS 연결이 확인될 때만 직접 수혜로 봅니다.",
                "headwind": "예산 미확정, 경쟁입찰, 시험 실패, 사이버·전자전·안전 인증이 병목입니다.",
                "scope_note": "Project Meridian 명칭이 언급됐다는 이유만으로 모든 후속 방산 계약을 연결하지 않습니다.",
                "impacts": "매출·마진·현금흐름, 수급, 시간표",
                "paths": "예산, 조달, 계약, 시험·전력화",
                "sectors": "AI/자율·로봇, 우주·통신, 방산기술",
                "priced_in": "후속 계약 강도에 따라 낮음~중간.",
                "counter": "실제 계약·시험대상이 제한적이면 산업 전체 수혜로 확장하기 어렵습니다.",
                "failure": "계약·시험·전력화 일정이 후속 문서로 이어지지 않으면 연구 테마에 머뭅니다.",
            }
        return {
            "revision": "us-dow-project-meridian-commissioned-ko-v1",
            "event_date": "2026년 9월 30일",
            "title": "미 국방부 Project Meridian 출범: 머스크·Palmer Luckey·Newt Gingrich 공동주도",
            "core": "미 국방부가 Project Meridian을 출범시켜 미래전 기술 우선순위를 연구합니다.",
            "stage": "공식 연구·자문 착수 단계 — 국방 계약·수주 확정이 아닙니다.",
            "actual": "미 국방부 CTO Emil Michael의 지휘 아래 미래 전장·필요 무기·기술을 연구하고 실행 가능한 개발·시험·전력화 과제를 제안합니다. MITRE 공개 명단은 현재 구성이고 향후 바뀔 수 있습니다.",
            "timeline": "2026년 9월 30일 국방부 발표·연구 착수 → 2026년 10월 2일 MITRE 구성 공개 → 120일 내 결과 제출 → 2027년 1월 28일 이전 최종 연구결과 목표",
            "why": "미래전 기술 우선순위를 민간 기술리더와 FFRDC가 함께 좁히는 공식 연구축이 생겼다는 점이 중요합니다. 다만 돈이 움직이는 시점은 후속 예산·조달부터입니다.",
            "next": "최종 보고서·기밀 부록, 기술 우선순위, 참가자 변화, 예산·BAA·OTA·RFI·RFP·계약, 시험·전력화 일정",
            "investment": "Musk·Luckey 참여는 SpaceX·Anduril의 자동 수주를 뜻하지 않습니다. 실제 투자 재료는 권고가 특정 프로그램·예산·계약으로 전환되는지입니다.",
            "korea": "현재 한국 상장사의 Project Meridian 직접 계약은 확인되지 않았습니다. 미 조달·FMS·미국 주계약자 공급망 편입이 확인될 때 실적 연결을 판단합니다.",
            "headwind": "이해상충 논란, 의회 예산, 획득절차, 시험·안전·사이버·전자전 검증이 실제 사업화 속도를 늦출 수 있습니다.",
            "scope_note": "미 육군 공식 설명은 Project Meridian을 새 전략·정책을 만드는 사업이 아니라 미래 도메인·역량을 식별하는 미래전 연구로 규정합니다.",
            "impacts": "수급, 시간표, 향후 매출·마진·현금흐름",
            "paths": "기술 우선순위, 예산, 조달, 시험·전력화",
            "sectors": "AI/자율·로봇, 우주·통신, 지향성에너지, 바이오·국방기술",
            "priced_in": "중간. 인물 참여는 공개됐지만 실제 권고·예산·계약은 아직 없습니다.",
            "counter": "120일 연구가 장기 비전 제시에 그치고 실제 예산·조달 우선순위를 바꾸지 않을 수 있습니다.",
            "failure": "2027년 1분기 이후에도 구체 프로그램·예산·조달·시험 일정이 없으면 직접 실적 재료보다 정책 테마에 머뭅니다.",
        }
    if rule.key == "us_dow_autonomous_warfare_execution":
        if semantic_key == "us-dow-autonomous-warfare-army-fascom-2026-10-02":
            return {
                "revision": "us-dow-autonomous-warfare-fascom-ko-v1",
                "event_date": "2026년 10월 2일",
                "title": "미 육군 FASCOM 창설 지시: 자율무기 조달·전력화 실행 단계",
                "core": "미 육군이 FASCOM 창설과 자율체계 획득·전력화를 지시했습니다.",
                "stage": "미 육군 공식 시행 지시 — Project Meridian의 연구축보다 직접적인 조달·전력화 실행축입니다.",
                "actual": "육군은 항공·기갑·화력·군수·공병·훈련 등 최소 6개 편성영역에 자율능력을 통합하고, Autonomy 담당 Portfolio Acquisition Executive를 두며 FY2028까지 자율 화력·전투차량·수상 보급·돌파·정찰감시표적획득 등의 획득·전력화를 우선하도록 했습니다.",
                "timeline": "2026년 4월 21일 SOUTHCOM SAWC(별도 지역사령부) → 9월 30일 국방부 4성급 AUTOWARCOM·Project Agincourt 발표 → 10월 2일 미 육군 FASCOM 지시 → FY2028 우선 획득·전력화",
                "why": "자문·연구가 아니라 실제 조직·획득책임자·전력화 대상과 기한이 붙은 후속 단계여서 돈이 조달로 이동할 가능성이 더 높습니다.",
                "next": "FASCOM 실제 가동, Autonomy 조달책임자 임명, 예산 확정, RFI·BAA·OTA·RFP, 시험평가, 계약·대량구매, 부대 배치",
                "investment": "드론·무인차량·센서·C2·통신·엣지컴퓨팅·자율소프트웨어는 조달 공고와 계약이 확인될 때 직접 매출로 전환됩니다.",
                "korea": "한국 방산사는 미국 조달 자격·현지 파트너·FMS 또는 미국 주계약자 공급계약이 확인돼야 직접 수혜로 분류합니다.",
                "headwind": "의회 예산, 상호운용성, 전자전·통신교란, 사이버보안, 안전·책임, 대량생산 수율·원가가 병목입니다.",
                "scope_note": "2026년 4월 SOUTHCOM Autonomous Warfare Command와 9월 30일 발표된 국방부 전체 4성급 AUTOWARCOM을 같은 조직으로 합치지 않습니다.",
                "impacts": "매출·마진·현금흐름, 수급, 시간표",
                "paths": "조직 창설, 예산, 신속획득, 조달·계약, 시험·전력화",
                "sectors": "드론/무인기, 로봇·자율전투차량, 센서·C2·통신, 엣지컴퓨팅·AI, 대드론",
                "priced_in": "낮음~중간. 조직 방향은 공개됐지만 공급사·계약금액·대량구매는 아직 대부분 미확정입니다.",
                "counter": "조직 창설만으로 조달예산이 자동 집행되는 것은 아니며 서비스별 기존 프로그램과 역할 조정이 남습니다.",
                "failure": "6~12개월 내 예산·조달 공고·시험평가·계약이 따라오지 않으면 조직개편 기대가 실적보다 앞선 상태입니다.",
            }
        if semantic_key == "us-dow-autonomous-warfare-activated":
            stage = "실제 창설·가동 단계"
            title_ko = "미 국방부 AUTOWARCOM 실제 창설·가동"
        elif semantic_key == "us-dow-autonomous-warfare-funding":
            stage = "예산·재원 확정 단계"
            title_ko = "미 국방부 자율전투 예산·재원 확정"
        elif semantic_key.startswith("us-dow-autonomous-warfare-procurement-"):
            stage = "조달·계약 실행 단계"
            title_ko = "미 국방부 자율전투 조달·계약 실행"
        else:
            stage = "4성급 지휘체계 창설 발표 단계"
            title_ko = "미 국방부 4성급 AUTOWARCOM 창설 구상"
        return {
            "revision": "us-dow-autonomous-warfare-execution-ko-v1",
            "event_date": "",
            "title": title_ko,
            "core": "미 국방부가 4성급 AUTOWARCOM 창설과 자율전투 신속획득을 추진합니다.",
            "stage": stage,
            "actual": "핵심은 자율·로봇 체계를 빠르게 획득·시험·배치하는 조직과 획득 권한을 묶는 것입니다.",
            "timeline": "9월 30일 AUTOWARCOM·Project Agincourt 발표 → 육군·각 군 조직·획득 후속 → 예산·조달·시험 → 실제 부대 전력화",
            "why": "Project Meridian보다 직접적으로 예산·획득·계약·전력화로 이어지는 실행축입니다.",
            "next": "지휘관·조직 확정, 의회 예산, 조달 공고, 계약 당사자·금액, 시험평가, 배치 수량·일정",
            "investment": "공급사 실적은 발표가 아니라 계약·납품·시험통과·대량배치로 확인합니다.",
            "korea": "한국 기업은 미국 조달·FMS·현지 생산·미국 주계약자 공급망 연결이 확인될 때만 직접 수혜로 봅니다.",
            "headwind": "예산, 규제·책임, 사이버·전자전, 통신·항법 교란, 대량생산·유지보수 비용이 실패 경로입니다.",
            "scope_note": "SOUTHCOM의 4월 지역 자율전투 사령부와 국방부 전체 4성급 AUTOWARCOM은 별개로 추적합니다.",
            "impacts": "매출·마진·현금흐름, 수급, 시간표",
            "paths": "조직 창설, 예산, 조달, 시험·전력화",
            "sectors": "드론/무인기, 로봇·자율체계, 센서·C2·통신, 엣지AI, 대드론",
            "priced_in": "실제 예산·계약 단계에 따라 달라집니다.",
            "counter": "조직·정책 발표만으로 특정 기업 수주를 단정할 수 없습니다.",
            "failure": "예산·조달·시험·대량배치가 지연되면 관련 기업의 매출 전환도 늦어집니다.",
        }
    if semantic_key == "us-fcc-robot-inverter-covered-list-2026-07-28":
        return {
            "revision": "us-fcc-robot-inverter-covered-list-ko-v1",
            "event_date": "2026년 7월 28일",
            "title": "미 FCC, 외국산 전력 인버터·첨단 로봇 Covered List 편입",
            "core": "FCC가 외국산 전력 인버터와 외국산 첨단 로봇을 Covered List에 추가했습니다.",
            "stage": "2026년 7월 28일 최초 편입 단계입니다. 기사 게시일·재게시일을 새 정책 날짜로 사용하지 않습니다.",
            "actual": "Covered List 대상 신규 장비는 FCC 장비인증 제한을 받으며, 전력 인버터는 DoW 또는 DHS, 첨단 로봇은 DoW의 조건부 승인에 따라 예외가 가능합니다.",
            "timeline": "2026년 7월 28일 DA 26-786 최초 편입 → 8월 20일 DA 26-870 인버터 정의 수정 → 9월 9일 DA 26-957 일부 장비 조건부 승인 → 9월 18일 DA 26-996 추가 첨단 로봇 조건부 승인",
            "why": "정책의 기준일과 후속 예외·수정 단계를 분리해야 재게시 기사 때문에 같은 사건을 신규 변화로 잘못 알리는 것을 막을 수 있습니다.",
            "next": "Covered List 추가 수정, 조건부 승인·철회, 장비인증 규칙 변경처럼 FCC 공식 문서번호와 Released 날짜가 실제로 바뀌는 경우만 신규 단계로 알립니다.",
            "investment": "미국향 신규 외국산 로봇·전력변환장치의 인증·판매 경로에 영향을 주지만 개별 제품이 정의에 해당하는지와 예외 승인이 있는지는 별도 확인해야 합니다.",
            "korea": "국내 기업은 미국향 해당 완제품의 생산국·FCC 장비인증·조건부 승인 여부가 확인될 때만 직접 실적 영향으로 연결합니다.",
            "impacts": "매출·마진·현금흐름, 수급, 시간표",
            "paths": "FCC 장비인증, Covered List, 조건부 승인, 공급망",
            "sectors": "첨단 로봇/피지컬 AI, 전력 인버터/전력변환장치, 미국 장비인증",
            "priced_in": "기존 정책. 7월 28일 최초 편입 자체는 재알림하지 않습니다.",
            "counter": "모든 소비자 로봇이 자동 포함되는 것은 아니며 FCC의 첨단 로봇 정의와 예외를 제품별로 확인해야 합니다.",
            "failure": "기사 게시일을 정책일로 오인하거나 조건부 승인 예외를 누락하면 규제 강도를 과대평가하게 됩니다.",
        }
    if semantic_key == "us-fcc-inverter-definition-modification-2026-08-20":
        return {
            "revision": "us-fcc-inverter-modification-ko-v1",
            "event_date": "2026년 8월 20일",
            "title": "미 FCC, 외국산 전력 인버터 Covered List 정의·예외 수정",
            "core": "FCC가 DA 26-870으로 전력 인버터 Covered List 항목의 정의와 예외 범위를 수정했습니다.",
            "stage": "7월 28일 최초 편입 이후의 공식 수정 단계입니다.",
            "actual": "최초 편입 자체의 재게시가 아니라 전력 인버터 적용범위가 공식 문서로 조정된 후속 변화입니다.",
            "timeline": "7월 28일 DA 26-786 최초 편입 → 8월 20일 DA 26-870 수정",
            "why": "적용범위·예외가 달라지는 후속 문서이므로 별도 신규 단계로 취급합니다.",
            "next": "추가 정의 수정, 조건부 승인, FCC 장비인증 집행 변화를 확인합니다.",
            "investment": "실제 대상 제품 범위가 좁아지거나 넓어지는지가 미국향 인버터 공급 가능성을 바꿉니다.",
            "korea": "미국향 인버터 완제품·전력변환장치의 생산국과 예외 적용 여부를 제품별로 확인해야 합니다.",
            "impacts": "매출·마진·현금흐름, 시간표",
            "paths": "Covered List, 장비인증, 예외 범위",
            "sectors": "전력 인버터/전력변환장치, 미국 장비인증",
            "priced_in": "공식 후속 단계.",
            "counter": "정의 수정이 모든 기존 인증 장비의 즉시 판매중단을 뜻하지는 않습니다.",
            "failure": "수정 전 문구를 계속 적용하면 대상 제품과 규제강도를 잘못 판단할 수 있습니다.",
        }
    if semantic_key in {"us-fcc-robot-conditional-approval-2026-09-09", "us-fcc-robot-conditional-approval-2026-09-18"}:
        event_date = "2026년 9월 9일" if semantic_key.endswith("09-09") else "2026년 9월 18일"
        doc = "DA 26-957" if semantic_key.endswith("09-09") else "DA 26-996"
        return {
            "revision": f"{semantic_key}-ko-v1",
            "event_date": event_date,
            "title": "미 FCC, 일부 첨단 로봇 조건부 승인·Covered List 예외",
            "core": f"FCC가 {doc}으로 특정 첨단 로봇에 대한 조건부 승인·Covered List 예외를 공식 공지했습니다.",
            "stage": f"{event_date} 조건부 승인 후속 단계입니다.",
            "actual": "7월 28일 전체 외국산 첨단 로봇 범주 편입 뒤 특정 장비가 조건부 승인으로 예외 처리된 변화입니다.",
            "timeline": f"7월 28일 최초 편입 → {event_date} {doc} 조건부 승인 공지",
            "why": "규제가 일률적 전면금지가 아니라 조건부 승인 절차를 통해 제품별 예외가 실제 발생한다는 점을 보여줍니다.",
            "next": "추가 승인·철회·승인조건 변경과 Covered List 갱신을 추적합니다.",
            "investment": "개별 제조사의 미국 판매 가능성은 조건부 승인 여부에 따라 달라지므로 제품 단위 확인이 필요합니다.",
            "korea": "한국 로봇 기업도 미국향 완제품이 Covered List 정의에 해당하면 생산국·승인상태를 제품별로 확인해야 합니다.",
            "impacts": "매출·마진·현금흐름, 시간표",
            "paths": "조건부 승인, Covered List, 장비인증",
            "sectors": "첨단 로봇/피지컬 AI, 미국 장비인증",
            "priced_in": "공식 후속 단계.",
            "counter": "조건부 승인은 일부 특정 장비에 대한 예외이며 모든 외국산 로봇 규제가 해제된 것은 아닙니다.",
            "failure": "예외 승인 대상을 전체 시장으로 일반화하면 규제영향을 과소평가할 수 있습니다.",
        }
    if semantic_key == "polysilicon-11052-stockpiling-tfr":
        return {
            "revision": "polysilicon-11052-stockpiling-ko-v1",
            "event_date": "2026년 9월 22일",
            "title": "미 상무부, 폴리실리콘 사재기 차단 규칙 시행",
            "core": "미 상무부 BIS가 Proclamation 11052의 12월 4일 시행 전 폴리실리콘·파생제품 재고 사재기를 막는 임시 최종규칙을 시행했습니다.",
            "stage": "시행 중 — 2026년 9월 22일부터 12월 3일까지 적용되는 별도 집행 단계입니다.",
            "actual": "기존 수입자의 비정상 재고 축적을 감시하고 신규 수입자 물량을 제한하며 필요시 수입금지와 면제 절차를 적용하는 규칙입니다.",
            "timeline": "8월 6일 Proclamation 11052 발표 → 9월 22일 사재기 차단 규칙 발효 → 12월 4일 최저수입가격·관세 조치 시행",
            "why": "8월 6일 정책의 재보도가 아니라 시행 전 우회 재고축적을 차단하는 새 집행 규칙이라는 점이 핵심입니다.",
            "next": "BIS 수입금지·면제 결정, CBP 집행 변화, 12월 4일 본 조치 시행",
            "investment": "직접 기업 매출보다 미국향 폴리실리콘·잉곳·웨이퍼·셀·모듈 수입가격과 공급시점에 영향을 주는 통상 집행 변수입니다.",
            "korea": "한국 기업은 미국향 태양광 공급망 노출과 실제 수입·판매 계약이 확인되는 경우에만 실적 영향으로 연결합니다.",
            "impacts": "매출·마진·현금흐름, 수급, 시간표",
            "paths": "Section 232, 수입규제, 재고, 정책 타임라인",
            "sectors": "태양광/폴리실리콘, 관세/수출주",
            "priced_in": "중간. 8월 기본 조치는 알려졌지만 9월 22일 사재기 차단 집행 규칙은 별도 신규 단계입니다.",
            "counter": "개별 기업의 실제 수입금지나 매출 영향은 아직 별도 확인이 필요합니다.",
            "failure": "BIS·CBP의 실제 집행 변화와 수입량·가격 변화가 없으면 기업 실적 영향은 제한됩니다.",
        }
    if semantic_key == "polysilicon-11052-base":
        return {
            "revision": "polysilicon-11052-base-ko-v1",
            "event_date": "2026년 8월 6일",
            "title": "미국, 폴리실리콘 Section 232 최저수입가격·관세 조치",
            "core": "Proclamation 11052는 폴리실리콘과 파생 태양광 제품에 최저수입가격과 추가 관세를 도입하는 8월 6일 발표 정책입니다.",
            "stage": "기존 발표 재확인 단계 — 새 기사 URL만으로 신규 변화로 보지 않습니다.",
            "actual": "12월 4일 시행 예정인 기존 정책의 기본 조치입니다.",
            "timeline": "8월 6일 발표 → 12월 4일 시행",
            "why": "새 기사나 재인용 보도는 신규 정책 변화가 아니라 기존 Proclamation의 재노출일 수 있습니다.",
            "next": "세부 집행규칙, 면제·수입금지, CBP 집행 변화처럼 실제 조건이 바뀌는 경우만 신규 알림",
            "investment": "기존 발표 자체는 중복 알림하지 않고 실제 집행조건 변화만 추적합니다.",
            "korea": "미국향 태양광 공급망 노출 기업의 실제 계약·가격 변화가 확인될 때만 실적 연결합니다.",
            "impacts": "매출·마진·현금흐름, 시간표",
            "paths": "Section 232, 관세, 정책 타임라인",
            "sectors": "태양광/폴리실리콘, 관세/수출주",
            "priced_in": "높음. 8월 6일 공개된 기본 정책입니다.",
            "counter": "새 URL·새 해설기사만으로 정책이 바뀌었다고 볼 수 없습니다.",
            "failure": "기존 조건과 달라진 공식 집행 문구가 없으면 신규 알림에서 제외합니다.",
        }
    if rule.key == "us_china_ai_safety_talks":
        return {
            "revision": "us-china-ai-safety-talks-ko-v1",
            "event_date": "2026년 9월 20일",
            "title": "미·중, AI 안전 통지체계 협의: 정상회담 후속 확인",
            "core": "베선트·허리펑 회담에서 AI 안전 통지체계 제안이 논의됐습니다.",
            "stage": "장관급 협의 완료 단계 — 미국 측 제안은 확인됐지만 중국의 수용과 구체 제도는 아직 미확정입니다.",
            "actual": "미 재무장관 스콧 베선트가 허리펑 중국 부총리와의 회담에서 AI 안전 관련 상호 통지 메커니즘을 제안했습니다.",
            "timeline": "2026년 9월 19일 AI Force·신임 AI 차르 구상 발표 → 2026년 9월 20일 베선트·허리펑 AI·무역 회담 → 2026년 9월 24일 트럼프·시진핑 정상회담 일정",
            "why": "미국의 국내 AI 지휘체계 구상과 미·중 AI 안전 협의가 같은 주간에 연결되며, 규제·국가안보 정책축이 실제 협상 의제로 이동한 변화입니다.",
            "next": "9월 24일 정상회담 결과, AI 안전 통지체계 채택 여부, 적용 대상·통지 요건, 사이버안보·AI 무기화 범위, BIS 수출통제와의 관계",
            "investment": "직접 매출은 아직 없지만, 후속 합의가 첨단칩·클라우드·모델 배포 규칙으로 이어질 경우 AI 공급망의 판매 가능 시장과 규제비용이 바뀔 수 있습니다.",
            "korea": "한국장에서는 삼성전자·SK하이닉스 HBM과 반도체 장비·소재 중 실제 BIS 규정·라이선스 변경으로 연결되는 경우만 실적 변수로 봅니다.",
            "impacts": "매출·마진·현금흐름, 수급, 시간표",
            "paths": "미중 AI 협의, 정책 타임라인, 수출통제, 국가안보",
            "sectors": "반도체/AI, 클라우드/보안 AI, 미중 기술규제",
            "priced_in": "낮음~중간. 장관급 제안은 새 정보지만 최종 합의와 규정 반영 전에는 정책 기대 단계입니다.",
            "counter": "중국의 명확한 수용이나 공동문서가 아직 없고, 안전 협의가 첨단칩 규제 완화로 직결된다는 근거도 없습니다.",
            "failure": "정상회담 공동문구, 후속 실무협의, BIS·백악관 규정 변화가 없으면 외교 협의 수준에서 끝납니다.",
        }
    if rule.key == "us_fcc_upper_c_band_auction115":
        return {
            "revision": "us-fcc-upper-c-band-auction115-ko-v1",
            "event_date": "2026년 8월 3일",
            "title": "미 FCC, Upper C-band Auction 115 확정: 2027년 4월 27일 입찰 예정",
            "core": "FCC가 3.98~4.14GHz 160MHz를 20MHz×8블록, 총 3,248개 면허로 경매하는 Auction 115 일정을 공식화했습니다.",
            "stage": "경매 준비 단계 — 입찰 개시는 2027년 4월 27일 잠정 예정이며 실제 장비 발주는 낙찰·CAPEX 이후입니다.",
            "actual": (
                "미 본토 406개 PEA에 3,248개 면허를 공급합니다. Brendan Carr FCC 위원장의 1,000억달러 발언은 "
                "Auction 115 단일 금액이 아니라 향후 수년간 여러 주파수 경매의 누적 수입 전망입니다."
            ),
            "timeline": (
                "2026년 8월 3일 Auction 115 절차 공고 → 2026년 9월 17일 Carr 1,000억달러+ 다중경매 전망 → "
                "2027년 4월 27일 입찰 개시 예정 → 2030년 12월 31일 상위 75개 PEA 서비스 개시 가능 → "
                "2031년 7월 1일 나머지 지역 서비스 개시 기준"
            ),
            "why": (
                "주파수 확보가 통신사 CAPEX·기지국 증설의 선행조건이라는 점은 긍정적이지만, 2027년 경매와 실제 전국 서비스 개시 사이에 "
                "3~4년의 전환·항공고도계·위성사업자 정리 시차가 있다는 점이 핵심입니다."
            ),
            "next": (
                "최종 입찰절차·최저입찰가 → 적격 입찰자 → 낙찰자·낙찰액 → AT&T·Verizon·T-Mobile CAPEX → "
                "삼성전자·Ericsson·Nokia 장비수주 → 국내 부품사 실제 주문"
            ),
            "investment": (
                "국내 통신장비주는 경매액이 아니라 미국 통신사 CAPEX와 글로벌 장비사 발주가 실적 촉발 요인입니다. "
                "낙찰 이후 기지국·안테나·필터·DAS·프론트홀 발주가 확인될 때 실적 재평가가 강해집니다."
            ),
            "korea": (
                "직접 후보는 KMW·에이스테크·쏠리드·에치에프알입니다. 다만 FCC 경매 자체는 이들 기업의 수주가 아니며, "
                "삼성전자·Ericsson·Nokia 및 미국 통신사향 고객 승인·발주가 확인돼야 확정 매출로 구분합니다."
            ),
            "korea_candidates": (
                "직접 장비 후보: KMW·에이스테크 / 미국 매출 기반: 쏠리드 / 프론트홀·무선망 후보: 에치에프알 "
                "— 현재 Auction 115 관련 확정 수주 아님"
            ),
            "headwind": (
                "최대 역풍은 시간표입니다. 상위 75개 PEA도 신규 지상 무선서비스 개시는 2030년 12월 31일부터 가능하며 "
                "나머지 지역은 2031년 7월 1일 기준이라 2027년 경매 직후 전국 장비수요가 한꺼번에 발생하지 않습니다."
            ),
            "scope_note": (
                "1,000억달러는 Auction 115 한 번의 경매액이 아니라 FCC가 계획한 향후 여러 경매의 누적 가능 수입입니다."
            ),
            "backfill_note": "기존 공식 공고가 Telegram까지 전달되지 않아 이번에 누락 복구로 1회 전송합니다.",
            "secondary_source": (
                "Reuters | https://www.reuters.com/business/media-telecom/"
                "us-official-says-upcoming-spectrum-auctions-could-generate-more-than-100-billion-2026-09-17/"
            ),
            "impacts": "매출·마진·현금흐름, 수급, 시간표",
            "paths": "주파수 경매, 통신사 CAPEX, 장비 발주, 망 구축 시간표",
            "sectors": "통신장비/5G·6G, 안테나·필터, DAS·중계기, 프론트홀",
            "priced_in": "중간. 경매 일정과 1,000억달러 전망은 알려졌지만 낙찰자·통신사 CAPEX·장비 발주는 아직 미확정입니다.",
            "counter": (
                "경매 규모가 커도 사업자가 주파수 확보 뒤 CAPEX를 늦추거나 기존 장비 재활용 비중을 높이면 국내 장비사 매출 증가는 제한될 수 있습니다."
            ),
            "failure": (
                "낙찰 후 6~12개월 내 통신사 CAPEX 상향·삼성전자/Ericsson/Nokia 수주·국내 부품사 고객승인이 나오지 않으면 "
                "테마성 기대가 실적으로 이어지지 않습니다."
            ),
        }
    if rule.key == "us_congress_chinese_optical_transceiver_restriction":
        return {
            "revision": "us-congress-chinese-optical-transceiver-ko-v2",
            "event_date": "2026년 9월 25일",
            "title": "미 의회, 중국산 광트랜시버 국가안보 시스템 조달 제한 법안 발의",
            "core": "InnoLight·Eoptolink 계열 광트랜시버를 연방 국가안보 시스템 조달에서 제한하는 초당적 법안이 발의됐습니다.",
            "stage": "상원 법안 발의 단계 — 아직 미국 전체 상업용 데이터센터 수입금지나 시행 확정은 아닙니다.",
            "actual": (
                "InnoLight·Eoptolink와 자회사·계열사뿐 아니라 해당 업체의 펌웨어·소프트웨어·부품이 들어간 적용 대상 "
                "광트랜시버까지 포함하고, 시행 전 5년 전환기간을 둡니다."
            ),
            "timeline": (
                "2026년 6월 InnoLight Section 1260H 중국 군사기업 명단 추가 → "
                "2026년 9월 25일 초당적 조달 제한 법안 발의 → "
                "위원회 심사·상하원 통과·대통령 서명 여부 확인"
            ),
            "why": (
                "단순 FCC 검토가 아니라 군사기업 지정 이후 연방조달 제한으로 규제 연속선이 구체화됐고, "
                "Commerce가 미국·동맹국 생산능력과 신뢰 공급망 전략을 평가하도록 요구받는 점이 중요합니다."
            ),
            "next": (
                "War·Commerce 추가 지정기업, Commerce 생산능력 평가, 미국·동맹 증설, "
                "대체 공급원 부재 시 갱신형 면제 건수·의회 보고, 연방 조달 변경"
            ),
            "investment": (
                "단기 민간 데이터센터 물량이 즉시 이동하는 사건은 아니지만, 5년 조달 전환기간 동안 비중국 광모듈 공급사의 "
                "증설·고객 인증·장기계약을 앞당길 수 있는 수요 신호입니다."
            ),
            "korea": (
                "국내 보도상 후보는 오이솔루션·빛과전자(구 라이트론) 광트랜시버, 쏠리드 광통신장비, "
                "LS전선·대한전선 광케이블입니다. 미국 정부 지정·연방조달 수주가 확인된 기업은 아직 없어 기대감 단계로만 구분합니다."
            ),
            "korea_candidates": (
                "직접 제품 후보: 오이솔루션·빛과전자(구 라이트론) / 인접: 쏠리드 / 간접 인프라: LS전선·대한전선 "
                "— 미국 정부 지정·연방조달 수주 미확정"
            ),
            "headwind": (
                "Reuters 기준 Coherent·Lumentum이 대체품을 공급하지만 중국 업체 물량을 단기간 전면 대체할 생산능력은 부족합니다. "
                "공급 부족이 심하면 면제 확대·AI 인프라 구축 지연이 먼저 나타날 수 있습니다."
            ),
            "scope_note": (
                "법안은 연방정부 국가안보 시스템 조달 제한이며 미국 전체 민간 데이터센터의 즉시 수입금지가 아닙니다. "
                "공식 원문은 5년 전환기간을 두며, '5년 내 기존 부품 전면 교체 의무'로 단정하지 않습니다."
            ),
            "impacts": "매출·마진·현금흐름, 수급, 시간표",
            "paths": "연방조달, 공급망, 생산능력, 정책 타임라인",
            "sectors": "광트랜시버/광통신, AI 데이터센터 네트워크, 중국 대체 공급망",
            "priced_in": "중간. 발의 사실은 알려졌지만 실제 규제 강도는 통과 여부·추가 지정·면제 규모·대체 생산능력이 결정합니다.",
            "counter": (
                "적용 범위는 연방정부 국가안보 시스템입니다. 대체 공급원이 없으면 제한적·갱신 가능한 면제가 가능하고 "
                "각 면제는 의회에 보고되므로 면제 규모가 크면 실질 규제효과가 약해질 수 있습니다."
            ),
            "failure": (
                "법안이 위원회에서 진전되지 않거나, 광범위한 면제가 반복되거나, 미국·동맹 생산능력 확대가 지연되면 "
                "비중국 공급사의 실제 수주 전환은 늦어집니다."
            ),
        }
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


def is_ai_force_alert(alert: dict) -> bool:
    rule = alert.get("rule")
    items = alert.get("items") or []
    if not rule or not items:
        return False
    profile = item_story_profile(rule, items)
    return bool(
        rule.key == "us_china_ai_safety_talks"
        or (
            profile
            and str(profile.get("revision") or "").startswith("trump-ai-force-czar-")
        )
    )


def dedupe_alerts_for_display(alerts: list[dict]) -> list[dict]:
    """Keep only the newest alert for each rendered decision headline."""
    output: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for alert in alerts:
        rule = alert.get("rule")
        items = alert.get("items") or []
        if not rule or not items:
            continue
        key = (
            str(getattr(rule, "key", "") or ""),
            story_display_title(rule, items).strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(alert)
    return output


def alert_latest_kst(alert: dict) -> str:
    items = alert.get("items") or []
    return max((str(item.get("published_kst", "")) for item in items), default="")


def source_bits(items: list[dict], limit: int = 1) -> str:
    bits: list[str] = []
    for item in items[:limit]:
        published = parse_kst_iso(str(item.get("published_kst") or ""))
        published_label = (
            f"{published.year}년 {published.month}월 {published.day}일 {published:%H:%M} KST"
            if published
            else "확인 불가"
        )
        bits.append(
            f"[{item['source']}]({item['link']}) · 원천시각 {published_label}"
        )
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
    profile = item_story_profile(rule, items)
    if profile and profile.get("stage"):
        published = parse_kst_iso(str(items[0].get("published_kst") or "")) if items else None
        published_label = (
            f"{published.year}년 {published.month}월 {published.day}일"
            if published
            else "확인 불가"
        )
        event_date = str(profile.get("event_date") or "").strip() or published_label
        timeline_parts = [
            part.strip()
            for part in str(profile.get("timeline") or "").split(" → ")
            if part.strip()
        ]
        timeline_lines = ["- 타임라인:"]
        timeline_lines.extend(f"  • {part}" for part in timeline_parts)
        return [
            f"- 발표일: {event_date}",
            f"- 현재 단계: {profile.get('stage')}",
            f"- 핵심: {core}",
            f"- 실제 내용: {profile.get('actual')}",
            *timeline_lines,
            f"- 왜 중요한가: {profile.get('why')}",
            *([f"- 국내 관련 기업: {profile.get('korea_candidates')}"] if profile.get("korea_candidates") else []),
            *([f"- 숨은 역풍: {profile.get('headwind')}"] if profile.get("headwind") else []),
            *([f"- 범위 주의: {profile.get('scope_note')}"] if profile.get("scope_note") else []),
            *([f"- 알림 상태: {profile.get('backfill_note')}"] if profile.get("backfill_note") else []),
            *([f"- 보조 출처: {profile.get('secondary_source')}"] if profile.get("secondary_source") else []),
            f"- 다음 확인: {profile.get('next')}",
        ]
    return [f"- 핵심: {core}"]


def alert_confirmation_status(rule: StoryRule, items: list[dict]) -> tuple[str, str]:
    """Return a conservative status, upgrading only first-party verified events."""
    if (
        rule.key in {
            "us_dow_project_meridian_future_warfare",
            "us_dow_autonomous_warfare_execution",
        }
        and any(
            "army.mil" in str(item.get("link") or "").lower()
            or "mitre.org" in str(item.get("link") or "").lower()
            or str(item.get("source") or "").strip().lower() in {"u.s. army", "us army", "mitre"}
            for item in items
        )
    ):
        return "공식 확인", "미 육군·MITRE 1차 자료 확인 완료"
    if (
        rule.key in {
            "us_fcc_space_nepa_reform",
            "us_fcc_satellite_spectrum_abundance",
            "us_fcc_satellite_spectrum_followon_fnprm",
        }
        and any(
            "fcc.gov" in str(item.get("link") or "").lower()
            or "federal communications commission" in str(item.get("source") or "").lower()
            or str(item.get("source") or "").strip().lower() == "fcc"
            for item in items
        )
    ):
        return "공식 확인", "미 FCC 공식자료 확인 완료"
    if (
        rule.key == "us_fcc_chinese_optical_transceiver_ban"
        and any(
            "fcc.gov" in str(item.get("link") or "").lower()
            or "docs.fcc.gov" in str(item.get("link") or "").lower()
            or "federalregister.gov" in str(item.get("link") or "").lower()
            or "federal communications commission" in str(item.get("source") or "").lower()
            or str(item.get("source") or "").strip().lower() == "fcc"
            for item in items
        )
    ):
        return "공식 확인", "미 FCC·연방관보 공식자료 확인 완료"
    if (
        rule.key == "us_fcc_upper_c_band_auction115"
        and any(
            "federalregister.gov" in str(item.get("link") or "").lower()
            or "u.s. federal register" in str(item.get("source") or "").lower()
            or "미 연방관보 fcc" in str(item.get("source") or "").lower()
            for item in items
        )
    ):
        return "공식 확인", "미 연방관보 FCC Auction 115 원문 확인 완료"
    if (
        rule.key == "us_congress_chinese_optical_transceiver_restriction"
        and any(
            "mccormick.senate.gov" in str(item.get("link") or "").lower()
            or "u.s. senate" in str(item.get("source") or "").lower()
            for item in items
        )
    ):
        return "공식 확인", "미 상원의원 공식 보도자료 확인 완료"
    return "공식 확인 전", "공식 원문/후속 문서 확인 전"


def render_alert_section(rule: StoryRule, items: list[dict], now: dt.datetime, index: int, source_limit: int = 1) -> list[str]:
    display_title = story_display_title(rule, items)
    sources = source_bits(items, source_limit)
    source_names = ", ".join(dict.fromkeys(str(item["source"]) for item in items[:3]))
    matched = {rule.key: ["EU", "Korea", "policy"] if rule.key.startswith("eu_korea_") else ["trusted policy news"]}
    if rule.key == "us_japan_korea_smr_moc_state_watch":
        matched["state_smr_moc_policy"] = ["moc", "smr", "samsung c&t", "bwrx-300"]
    status_label, status_detail = alert_confirmation_status(rule, items)
    explain_item = {
        "title": rule.title,
        "source": source_names,
        "summary": f"{rule.core} {rule.point}",
        "status": status_label,
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
        f"{index}. [상·{status_label}] {display_title}",
        f"- 확인 상태: {status_detail}. 확인 소스: {source_names or '확인 불가'}.",
        *compact_explanation_lines(rule, items, explain_item),
        f"- 출처: {sources} · 조회 {now:%H:%M KST}",
        "",
    ]


def render_auction115_compact_body(now: dt.datetime) -> str:
    fcc_url = (
        "https://www.federalregister.gov/documents/2026/08/03/2026-15725/"
        "auction-of-flexible-use-licenses-in-the-upper-c-band-for-next-generation-wireless-services-scheduled"
    )
    reuters_url = (
        "https://www.reuters.com/business/media-telecom/"
        "us-official-says-upcoming-spectrum-auctions-could-generate-more-than-100-billion-2026-09-17/"
    )
    return "\n".join([
        f"{now:%Y년 %m월 %d일 %H:%M KST} · FCC 공식 확인",
        "- 핵심: 2027년 4월 27일 · 3.98~4.14GHz · 160MHz · 3,248개 면허",
        "- 1,000억달러: Auction 115 단일액 아님 · 향후 여러 경매 누적 전망",
        "- 국내: KMW·에이스테크 / 쏠리드 / 에치에프알 — Auction 115 확정 수주 아님",
        "- 역풍: 상위 75개 PEA 2030년 12월 31일, 기타 2031년 7월 1일 → 장비매출 시차",
        f'- 다음: 낙찰자 → 통신사 CAPEX → 삼성전자·Ericsson·Nokia 수주 → 국내 주문 · <a href="{reuters_url}">Reuters</a>',
        f'- 출처: <a href="{fcc_url}">FCC 원문</a>',
    ]) + "\n"


def _self_test_fcc_optical_transceiver_event_model() -> None:
    research = {
        "title": "Potential FCC Rules on Optical Transceivers More Likely to Come in at 3.2T",
        "description": (
            "Morgan Stanley says FCC restrictions would likely start at 3.2T modules made in China; "
            "800G and 1.6T would be left alone and a 65% U.S.-value BOM threshold is under discussion."
        ),
        "link": "https://money.udn.com/example",
        "source": "經濟日報",
        "published_kst": "2026-10-02T13:14:04+09:00",
    }
    assert semantic_policy_event_key(research) == "us-fcc-optical-transceiver-3p2t-65pct-research-2026-10-01"
    rules = {rule.key: rule for rule in STORY_RULES}
    assert alert_confirmation_status(
        rules["us_fcc_chinese_optical_transceiver_ban"], [research]
    )[0] == "공식 확인 전"
    research_profile = item_story_profile(
        rules["us_fcc_chinese_optical_transceiver_ban"], [research]
    )
    assert research_profile and "FCC 공식 규칙" in str(research_profile.get("stage"))

    draft = {
        "title": "Trump administration drafting ban on Chinese data center optical transceivers",
        "description": "The FCC is drafting a ban on new Chinese optical transceiver models used in data centers.",
        "link": "https://www.reuters.com/example",
        "source": "Reuters",
        "published_kst": "2026-08-04T12:00:00+09:00",
    }
    assert semantic_policy_event_key(draft) == "us-fcc-optical-transceiver-draft"

    official = {
        "title": "FCC Adds Chinese Optical Transceivers to the Covered List",
        "description": (
            "The Federal Communications Commission adopts a final rule covering 3.2T optical transceivers made in China "
            "and specifies equipment authorization conditions."
        ),
        "link": "https://www.fcc.gov/document/example",
        "source": "Federal Communications Commission",
        "published_kst": "2026-10-20T12:00:00+09:00",
    }
    assert semantic_policy_event_key(official) == "us-fcc-optical-transceiver-covered-list-final"
    assert alert_confirmation_status(
        rules["us_fcc_chinese_optical_transceiver_ban"], [official]
    )[0] == "공식 확인"


def _self_test_defense_future_warfare_event_model() -> None:
    meridian = {
        "title": "Project Meridian",
        "description": "Project Meridian will study the battlefields of the future. Elon Musk, Palmer Luckey and Newt Gingrich are co-directors. MITRE leads the independent effort.",
        "link": "https://www.mitre.org/news-insights/publication/project-meridian",
        "source": "MITRE",
        "published_kst": "2026-10-02T12:00:00+09:00",
    }
    assert semantic_policy_event_key(meridian) == "us-dow-project-meridian-commissioned"

    report = {
        **meridian,
        "title": "Project Meridian final report released",
        "description": "Project Meridian final report released with findings and recommendations submitted to the Secretary.",
        "published_kst": "2027-01-28T12:00:00+09:00",
    }
    assert semantic_policy_event_key(report) == "us-dow-project-meridian-report"

    fascom = {
        "title": "Army announces Futures and Autonomous Systems Command",
        "description": "The Army establishes FASCOM, a Portfolio Acquisition Executive for Autonomy, and prioritizes acquisition and fielding across the joint force.",
        "link": "https://www.army.mil/article/295913/army_announces_futures_and_autonomous_systems_command",
        "source": "U.S. Army",
        "published_kst": "2026-10-02T12:00:00+09:00",
    }
    assert semantic_policy_event_key(fascom) == "us-dow-autonomous-warfare-army-fascom-2026-10-02"

    clayton = {
        "title": "Trump names intelligence chief Jay Clayton as AI czar, to head task force, WSJ reports",
        "description": "Trump named Jay Clayton as AI czar.",
        "link": "https://www.reuters.com/world/us/jay-clayton-lead-trumps-ai-task-force-deliver-report-120-days-wsj-reports-2026-10-03/",
        "source": "Reuters",
        "published_kst": "2026-10-03T12:00:00+09:00",
    }
    assert semantic_policy_event_key(clayton) == "us-trump-ai-czar-jay-clayton-appointed-2026-10-03"
    expected_clayton = {
        **clayton,
        "title": "Trump expected to name Jay Clayton as AI czar",
    }
    assert semantic_policy_event_key(expected_clayton) != "us-trump-ai-czar-jay-clayton-appointed-2026-10-03"

    southcom = {
        "title": "SOUTHCOM Establishes Autonomous Warfare Command",
        "description": "U.S. Southern Command established a regional autonomous warfare command.",
        "link": "https://www.southcom.mil/example",
        "source": "U.S. Southern Command",
        "published_kst": "2026-04-21T12:00:00+09:00",
    }
    assert semantic_policy_event_key(southcom) == ""

    rules = {rule.key: rule for rule in STORY_RULES}
    assert alert_confirmation_status(
        rules["us_dow_project_meridian_future_warfare"], [meridian]
    )[0] == "공식 확인"
    assert alert_confirmation_status(
        rules["us_dow_autonomous_warfare_execution"], [fascom]
    )[0] == "공식 확인"

    meridian_profile = item_story_profile(
        rules["us_dow_project_meridian_future_warfare"], [meridian]
    )
    assert meridian_profile and "계약·수주 확정이 아닙니다" in str(meridian_profile.get("stage"))
    fascom_profile = item_story_profile(
        rules["us_dow_autonomous_warfare_execution"], [fascom]
    )
    assert fascom_profile and "6개" in str(fascom_profile.get("actual"))


def render_alert(rule: StoryRule, items: list[dict], now: dt.datetime) -> str:
    if rule.key == "us_fcc_upper_c_band_auction115":
        return render_auction115_compact_body(now)
    status_label, _ = alert_confirmation_status(rule, items)
    header = "공식 확인 정책 뉴스 1건 확인" if status_label == "공식 확인" else "공식 문서 확인 전 정책 뉴스 1건 확인"
    lines = [
        f"{now:%Y년 %m월 %d일 %H:%M KST}",
        header,
        "",
        *render_alert_section(rule, items, now, index=1, source_limit=3),
        "투자 조언이 아닌 참고용 정책·규제 알림입니다.",
    ]
    return "\n".join(lines) + "\n"


def render_alert_bundle(alerts: list[dict], now: dt.datetime, limit: int = 3) -> str:
    selected = alerts[:limit]
    if (
        len(selected) == 1
        and selected[0].get("rule")
        and selected[0]["rule"].key == "us_fcc_upper_c_band_auction115"
    ):
        return render_auction115_compact_body(now)
    statuses = [alert_confirmation_status(alert["rule"], alert["items"])[0] for alert in selected]
    if selected and all(status == "공식 확인" for status in statuses):
        header = f"공식 확인 정책 뉴스 {len(selected)}건 확인"
    elif "공식 확인" in statuses:
        header = f"공식 확인·확인 전 혼합 정책 뉴스 {len(selected)}건 확인"
    else:
        header = f"공식 문서 확인 전 정책 뉴스 {len(selected)}건 확인"
    lines = [
        f"{now:%Y년 %m월 %d일 %H:%M KST}",
        header,
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
        for path in (
            ALERT_PATH,
            TITLE_PATH,
            ALERTS_JSON_PATH,
            AI_FORCE_ALERT_PATH,
            AI_FORCE_TITLE_PATH,
        ):
            if path.exists():
                path.unlink()
        print("trusted_policy_news_alerts=0")
        return 0

    alerts.sort(key=alert_latest_kst, reverse=True)
    ai_force_alerts = dedupe_alerts_for_display(
        [alert for alert in alerts if is_ai_force_alert(alert)]
    )
    general_alerts = dedupe_alerts_for_display(
        [alert for alert in alerts if not is_ai_force_alert(alert)]
    )

    if general_alerts:
        selected_alerts = general_alerts[:3]
        top = selected_alerts[0]
        extra_count = max(0, len(selected_alerts) - 1)
        title_suffix = f" 외 {extra_count}건" if extra_count else ""
        report = render_alert_bundle(selected_alerts, now)
        ALERT_PATH.write_text(report, encoding="utf-8")
        top_status, _ = alert_confirmation_status(top["rule"], top["items"])
        if len(selected_alerts) == 1 and top["rule"].key == "us_fcc_upper_c_band_auction115":
            telegram_title = "FCC Auction 115 | 2027.04.27 경매 예정"
        else:
            telegram_title = f"신뢰외신 정책 워치: [상·{top_status}] {story_display_title(top['rule'], top['items'])}{title_suffix}"
        TITLE_PATH.write_text(telegram_title + "\n", encoding="utf-8")
        ALERTS_JSON_PATH.write_text(
            json.dumps(
                [
                    {
                        "key": alert["rule"].key,
                        "title": alert["rule"].title,
                        "status": alert_confirmation_status(alert["rule"], alert["items"])[0],
                        "items": alert["items"],
                        "fingerprint": alert["fingerprint"],
                    }
                    for alert in general_alerts
                ],
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    else:
        for path in (ALERT_PATH, TITLE_PATH, ALERTS_JSON_PATH):
            if path.exists():
                path.unlink()

    if ai_force_alerts:
        selected_ai_force = ai_force_alerts[:1]
        ai_top = selected_ai_force[0]
        AI_FORCE_ALERT_PATH.write_text(
            render_alert_bundle(selected_ai_force, now, limit=1),
            encoding="utf-8",
        )
        AI_FORCE_TITLE_PATH.write_text(
            f"🚨 미국 AI 정책지휘체계 중요 변화: {story_display_title(ai_top['rule'], ai_top['items'])}\n",
            encoding="utf-8",
        )
    else:
        for path in (AI_FORCE_ALERT_PATH, AI_FORCE_TITLE_PATH):
            if path.exists():
                path.unlink()

    for alert in alerts:
        seen_entry = {
            "key": alert["rule"].key,
            "title": alert["rule"].title,
            "first_seen_kst": now.isoformat(timespec="seconds"),
            "status": alert_confirmation_status(alert["rule"], alert["items"])[0],
            "sources": [item["source"] for item in alert["items"][:3]],
        }
        seen[alert["fingerprint"]] = seen_entry
        seen[alert["legacy_fingerprint"]] = seen_entry
    seen_payload["updated_at_kst"] = now.isoformat(timespec="seconds")
    SEEN_PATH.write_text(json.dumps(seen_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(
        f"trusted_policy_news_alerts={len(alerts)} "
        f"general={len(general_alerts)} ai_force={len(ai_force_alerts)}"
    )
    return 0


if __name__ == "__main__":
    _self_test_fcc_optical_transceiver_event_model()
    raise SystemExit(main())
