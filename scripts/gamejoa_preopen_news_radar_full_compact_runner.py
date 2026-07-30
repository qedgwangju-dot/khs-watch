#!/usr/bin/env python3
"""Full-field compact Telegram renderer for the preopen news radar."""

from __future__ import annotations

import concurrent.futures
import datetime as dt
import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import gamejoa_preopen_news_radar_contract_runner as contract
from khs_article_detail import extract_article_detail
from khs_compact_text import concise_text
import gamejoa_news_coverage_extension as coverage


telegram = contract.telegram
base = contract.base

BIOTECH_SECTOR = "바이오/FDA"
BIOTECH_QUERY = (
    "바이오 주도주 복귀 체크",
    "biotech FDA approval PDUFA complete response letter CRL drug launch commercial sales profit guidance royalty milestone upfront licensing technology transfer pharma pipeline priority big pharma Reuters Bloomberg CNBC MarketWatch",
)
BIOTECH_TERMS = [
    "biotech", "biopharma", "pharma", "fda", "pdufa", "approval", "complete response letter",
    "crl", "clinical trial", "phase 3", "priority review", "nda", "bla", "drug launch",
    "commercial sales", "royalty", "milestone", "upfront", "license agreement", "licensing",
    "technology transfer", "out-license", "collaboration", "pipeline priority", "big pharma",
    "revenue", "profit", "earnings", "guidance", "rate cut", "real yield", "discount rate",
    "treasury", "tips", "xbi", "ibb", "기술이전", "마일스톤", "선급금", "임상", "승인",
    "매출", "영업이익", "빅파마", "파이프라인",
]
BIOTECH_DOMAIN_TERMS = [
    "biotech", "biopharma", "pharma", "fda", "pdufa", "complete response letter", "crl",
    "clinical trial", "phase 3", "priority review", "adcom", "nda", "bla", "drug launch",
    "pipeline priority", "big pharma", "xbi", "ibb", "바이오", "제약", "신약", "임상",
    "빅파마", "파이프라인",
]
BIOTECH_TRANSFER_TERMS = [
    "technology transfer", "license agreement", "licensing", "out-license", "collaboration",
    "milestone", "upfront", "기술이전", "마일스톤", "선급금",
]
BIOTECH_SALES_TERMS = [
    "commercial sales", "drug launch", "revenue", "profit", "earnings", "guidance", "royalty",
    "upfront", "milestone", "매출", "영업이익", "마일스톤", "선급금",
]
BIOTECH_FDA_TERMS = [
    "fda", "pdufa", "approval", "complete response letter", "crl", "priority review",
    "adcom", "nda", "bla", "phase 3", "임상", "승인",
]
BIOTECH_PHARMA_PRIORITY_TERMS = [
    "pipeline priority", "big pharma", "pfizer", "merck", "roche", "novartis", "lilly",
    "astrazeneca", "bristol myers", "bms", "johnson & johnson", "j&j", "sanofi", "gsk",
    "abbvie", "takeda", "빅파마", "파이프라인",
]
BIOTECH_DISCOUNT_TERMS = [
    "rate cut", "real yield", "discount rate", "treasury", "tips", "fed", "금리", "실질금리",
]
ROBOTICS_SECTOR = "로봇/생산자동화"
ROBOTICS_QUERY = (
    "삼성 로봇 실행 단계 체크",
    "Samsung Future Robotics reorganization Rainbow Robotics RB5-850 collaborative robot cobot Samsung production line factory automation deployment procurement order capex Reuters Bloomberg Samsung Electronics IR DART",
)
ROBOTICS_TERMS = [
    "samsung", "samsung electronics", "future robotics", "robotics task force", "robot organization",
    "reorganization", "restructuring", "rainbow robotics", "rb5-850", "collaborative robot",
    "cobot", "production line", "factory automation", "pilot", "test", "deployment", "adoption",
    "procurement", "purchase order", "supply contract", "order", "capex", "삼성전자", "미래로봇추진단",
    "조직개편", "조직 정비", "레인보우로보틱스", "협동로봇", "생산라인", "자동화", "테스트",
    "양산", "도입", "발주", "공급계약", "수주",
]
ROBOTICS_DOMAIN_TERMS = [
    "future robotics", "robotics task force", "rainbow robotics", "rb5-850", "collaborative robot",
    "cobot", "robot organization", "factory automation", "미래로봇추진단", "레인보우로보틱스",
    "협동로봇", "로봇", "생산라인 자동화",
]
ROBOTICS_SAMSUNG_TERMS = ["samsung", "samsung electronics", "삼성전자", "삼성"]
ROBOTICS_EXECUTION_TERMS = [
    "deployment", "adoption", "procurement", "purchase order", "supply contract", "order",
    "capex", "production line", "factory automation", "commercial", "양산", "도입", "발주",
    "공급계약", "수주", "생산라인", "자동화", "매출",
]
ROBOTICS_ORG_TERMS = [
    "future robotics", "reorganization", "restructuring", "robot organization", "task force",
    "미래로봇추진단", "조직개편", "조직 정비", "재정비",
]
ROBOTICS_TEST_TERMS = ["rb5-850", "pilot", "test", "testing", "trial", "테스트", "시범", "실증"]


def append_unique(seq: list, values: list) -> None:
    for value in values:
        if value not in seq:
            seq.append(value)


def korean_news_search_url(query: str) -> str:
    return "https://www.bing.com/news/search?" + urllib.parse.urlencode(
        {
            "q": query,
            "format": "rss",
            "setlang": "ko-KR",
            "cc": "KR",
        }
    )


KOREAN_BUSINESS_PUBLISHER_DOMAINS = {
    "edaily.co.kr": "이데일리",
    "mk.co.kr": "매일경제",
    "mt.co.kr": "머니투데이",
    "biz.heraldcorp.com": "헤럴드경제",
    "yna.co.kr": "연합뉴스",
    "yonhapnewstv.co.kr": "연합뉴스TV",
    "hankyung.com": "한국경제",
    "sedaily.com": "서울경제",
    "etoday.co.kr": "이투데이",
    "etnews.com": "전자신문",
    "fnnews.com": "파이낸셜뉴스",
    "asiae.co.kr": "아시아경제",
    "news1.kr": "뉴스1",
    "dt.co.kr": "디지털타임스",
}
KOREAN_BUSINESS_SEARCH_SOURCES = [
    (
        "국내 신뢰매체 AI·반도체 협력",
        (
            "(엔비디아 OR 삼성전자 OR SK하이닉스 OR 현대차 OR 브로드컴 OR 앤트로픽) "
            "(AI OR 반도체 OR HBM OR 로봇) "
            "(협력 OR 회동 OR 계약 OR 공급 OR 투자 OR 증설 OR 수주) "
            "(site:edaily.co.kr OR site:mk.co.kr OR site:mt.co.kr OR "
            "site:biz.heraldcorp.com OR site:yna.co.kr OR site:hankyung.com)"
        ),
    ),
    (
        "국내 신뢰매체 미국 증시·반도체",
        (
            "(나스닥 OR 필라델피아반도체 OR 필라델피아 반도체 OR SMH OR FOMC OR 연준 OR 유가) "
            "(급락 OR 급등 OR 하락 OR 상승 OR 금리 OR 실적) "
            "(site:edaily.co.kr OR site:mt.co.kr OR site:mk.co.kr OR site:hankyung.com)"
        ),
    ),
    (
        "국내 신뢰매체 자본시장 정책",
        (
            "(금융위원회 OR 금융감독원 OR 한국거래소 OR ETF OR ETN OR 레버리지 OR 기본예탁금) "
            "(시행 OR 규제 OR 상향 OR 제한 OR 편입 OR 공매도) "
            "(site:mk.co.kr OR site:edaily.co.kr OR site:mt.co.kr OR "
            "site:yna.co.kr OR site:hankyung.com)"
        ),
    ),
    (
        "국내 신뢰매체 산업수요·CAPEX",
        (
            "(데이터센터 OR 반도체공장 OR 반도체 공장 OR 철강 OR 전력망 OR 변압기 OR 원전 OR 방산) "
            "(수요 OR 투자 OR 증설 OR 수주 OR 계약 OR 실적 OR 발주) "
            "(site:biz.heraldcorp.com OR site:edaily.co.kr OR site:mk.co.kr OR "
            "site:mt.co.kr OR site:yna.co.kr OR site:hankyung.com)"
        ),
    ),
    (
        "이데일리 기업·AI",
        (
            "site:edaily.co.kr (엔비디아 OR 삼성전자 OR SK하이닉스 OR 현대차 OR AI OR 반도체) "
            "(협력 OR 회동 OR 계약 OR 공급 OR 투자 OR 증설 OR 수주)"
        ),
    ),
    (
        "이데일리 미국 증시",
        (
            "site:edaily.co.kr (나스닥 OR 필라델피아반도체 OR 필라델피아 반도체 OR "
            "SMH OR FOMC OR 연준 OR 유가) (급락 OR 급등 OR 하락 OR 상승)"
        ),
    ),
    (
        "매일경제 자본시장",
        (
            "site:mk.co.kr (금융위원회 OR 금융감독원 OR 한국거래소 OR ETF OR ETN OR "
            "레버리지 OR 기본예탁금 OR 외국인) (시행 OR 규제 OR 상향 OR 제한 OR 순매수)"
        ),
    ),
    (
        "머니투데이 글로벌시장",
        (
            "site:mt.co.kr (뉴욕마감 OR 나스닥 OR 필라델피아반도체 OR 필라델피아 반도체 OR "
            "FOMC OR 연준 OR 유가 OR 엔비디아 OR 마이크론)"
        ),
    ),
    (
        "헤럴드경제 산업수요",
        (
            "site:biz.heraldcorp.com (데이터센터 OR 반도체공장 OR 반도체 공장 OR 철강 OR "
            "전력망 OR 변압기 OR 원전 OR 방산 OR AI) "
            "(수요 OR 투자 OR 증설 OR 수주 OR 계약 OR 실적)"
        ),
    ),
    (
        "현대차·엔비디아 AI 협력",
        (
            "site:edaily.co.kr (정의선 OR 현대차) 엔비디아 "
            "(회동 OR 협력 OR 로봇 OR 자율주행 OR 제조AI)"
        ),
    ),
    (
        "AI 인프라 철강 수요",
        (
            "site:biz.heraldcorp.com (데이터센터 OR 반도체공장 OR 반도체 공장) "
            "(철강 OR 형강 OR 후판) 수요"
        ),
    ),
    (
        "국내 AI 계약·최고경영자 회동",
        (
            "(이재용 OR 정의선 OR SK하이닉스 OR SK텔레콤 OR 네이버) "
            "(샘올트먼 OR 샘 올트먼 OR 오픈AI OR 엔비디아 OR 젠슨황 OR 젠슨 황 "
            "OR 마이크로소프트 OR 앤트로픽) "
            "(HBM OR 파운드리 OR 메모리 OR AI팩토리 OR AI 팩토리 OR 데이터센터 OR 로봇) "
            "(계약 OR 공급 OR 회동 OR 협의 OR 도입 OR 구축) "
            "(site:yna.co.kr OR site:mk.co.kr OR site:hankyung.com OR "
            "site:edaily.co.kr OR site:dt.co.kr OR site:fnnews.com)"
        ),
    ),
    (
        "글로벌 VC·K스타트업 자본",
        (
            "(a16z OR 벤처캐피털 OR 실리콘밸리 OR VC) "
            "(K스타트업 OR 한국스타트업 OR 한국 스타트업 OR 한국투자) "
            "(투자 OR 펀드 OR 운용자산 OR 협력) "
            "(site:hankyung.com OR site:mk.co.kr OR site:fnnews.com OR site:asiae.co.kr)"
        ),
    ),
    (
        "중동·유가·물가·환율",
        (
            "(이란 OR 호르무즈 OR 후티 OR 사우디 OR 중동) "
            "(공습 OR 휴전 OR 충돌 OR 유가 OR 운임 OR 물가 OR 환율 OR 금리) "
            "(site:yna.co.kr OR site:yonhapnewstv.co.kr OR site:news1.kr OR "
            "site:mt.co.kr OR site:edaily.co.kr OR site:dt.co.kr)"
        ),
    ),
    (
        "빅테크 AI CAPEX·감원",
        (
            "(빅테크 OR 기술기업 OR 마이크로소프트 OR 구글 OR 아마존 OR 메타) "
            "(AI투자 OR AI 투자 OR CAPEX OR 데이터센터) "
            "(감원 OR 일자리 OR 인력감축 OR 투자) "
            "(site:etoday.co.kr OR site:mk.co.kr OR site:mt.co.kr OR site:hankyung.com)"
        ),
    ),
    (
        "중국 메모리·IPO·ETF",
        (
            "(CXMT OR 창신메모리 OR SMIC OR 중국반도체 OR 중국 반도체) "
            "(상장 OR IPO OR ETF OR 증설 OR 메모리가격 OR 메모리 가격) "
            "(site:asiae.co.kr OR site:hankyung.com OR site:mk.co.kr OR site:mt.co.kr)"
        ),
    ),
    (
        "국내 ETF 실수요·레버리지 규제",
        (
            "(ETF OR ETN) (개인 OR 외국인 OR 기관 OR 단일종목) "
            "(순매수 OR 순매도 OR 기본예탁금 OR 레버리지 OR 시행) "
            "(site:etoday.co.kr OR site:mk.co.kr OR site:mt.co.kr OR "
            "site:edaily.co.kr OR site:asiae.co.kr)"
        ),
    ),
]

coverage.apply_source_extensions(
    KOREAN_BUSINESS_PUBLISHER_DOMAINS,
    KOREAN_BUSINESS_SEARCH_SOURCES,
    base.TRUSTED,
)

append_unique(
    base.SOURCES,
    [
        *coverage.DIRECT_RSS_SOURCES,
        (
            "이투데이 전체뉴스",
            "https://rss.etoday.co.kr/eto/etoday_news_all.xml",
            "trusted",
        ),
        (
            "이투데이 마켓",
            "https://rss.etoday.co.kr/eto/market_news.xml",
            "trusted",
        ),
        (
            "이투데이 산업",
            "https://rss.etoday.co.kr/eto/industry_news.xml",
            "trusted",
        ),
        (
            "전자신문 오늘의 뉴스",
            "https://rss.etnews.com/Section901.xml",
            "trusted",
        ),
        (
            "전자신문 속보",
            "https://rss.etnews.com/Section902.xml",
            "trusted",
        ),
        (
            "전자신문 전자산업",
            "https://rss.etnews.com/06.xml",
            "trusted",
        ),
        *[
            (name, korean_news_search_url(query), "trusted")
            for name, query in KOREAN_BUSINESS_SEARCH_SOURCES
        ],
    ],
)
append_unique(
    base.TRUSTED,
    [
        "이투데이",
        "etoday",
        "전자신문",
        "etnews",
        "이데일리",
        "edaily",
        "매일경제",
        "mk.co.kr",
        "머니투데이",
        "mt.co.kr",
        "헤럴드경제",
        "heraldcorp",
        "연합뉴스",
        "yna.co.kr",
        "한국경제",
        "hankyung",
        "서울경제",
        "sedaily",
        "연합뉴스TV",
        "yonhapnewstv",
        "파이낸셜뉴스",
        "fnnews",
        "아시아경제",
        "asiae",
        "뉴스1",
        "news1",
        "디지털타임스",
        "dt.co.kr",
    ],
)
append_unique(
    base.TERMS,
    [
        "외국인",
        "순매수",
        "순매도",
        "삼성전자",
        "sk하이닉스",
        "하이닉스",
        "hbm",
        "cxl",
        "테스터",
        "양산평가",
        "상용화",
        "공급계약",
        "장기 공급",
        "장기공급",
        "수주",
        "감원",
        "기본예탁금",
        "ai 팩토리",
        "a16z",
        "cxmt",
        "샘 올트먼",
    ],
)
for sector_index, (sector_label, sector_terms) in enumerate(base.SECTORS):
    if sector_label == "반도체/AI":
        merged_terms = list(sector_terms)
        append_unique(
            merged_terms,
            [
                "삼성전자",
                "sk하이닉스",
                "하이닉스",
                "hbm",
                "cxl",
                "테스터",
                "양산평가",
                "엑시콘",
            ],
        )
        base.SECTORS[sector_index] = (sector_label, merged_terms)
        break


def enforce_semiconductor_cycle_contract() -> None:
    append_unique(base.QUERIES, [
        ("반도체 가격 사이클", "semiconductor selloff memory price DRAM NAND customer inventory capex valuation guidance Micron Samsung SK Hynix Reuters Bloomberg MarketWatch CNBC"),
        ("반도체 정책 드라이브", "semiconductor R&D tax credit tax deduction chip subsidy investment credit materials equipment components Korea Samsung SK Hynix 소부장 세액공제 Reuters Bloomberg 한국 정부"),
        ("메가프로젝트 일정 - 미국 항만 파업", "US East Coast port strike ILA USMX contract expires October port labor negotiations freight rates shipping megaproject project schedule equipment delivery Reuters Bloomberg CNBC MarketWatch"),
        ("중국 부양 벌크선", "China stimulus iron ore coal dry bulk freight Baltic Dry Index bulk carrier rates Reuters Bloomberg CNBC MarketWatch"),
        ("북미 송전망 정책 변수", "North America transmission grid investment approval regulatory permitting interconnection FERC DOE utility transmission line delay data center power grid Reuters Bloomberg CNBC MarketWatch"),
    ])
    append_unique(base.TERMS, [
        "customer inventory", "dram", "inventory", "memory price", "nand", "oversupply",
        "pricing", "selloff", "stock drop", "valuation",
        "chip subsidy", "component", "equipment", "investment credit", "materials", "r&d",
        "rd tax credit", "semiconductor tax credit", "subsidy", "tax credit", "tax deduction",
        "세액공제", "소부장",
        "baltic dry", "baltic dry index", "bdi", "bulk carrier", "coal", "dockworker",
        "dry bulk", "east coast port", "freight rate", "gulf coast port", "ila", "iron ore",
        "port labor", "port strike", "shipping rate", "stimulus", "strike", "usmx",
        "capex schedule", "delivery schedule", "equipment delivery", "mega project",
        "megaproject", "project delay", "project schedule",
        "grid approval", "grid delay", "grid investment", "interconnection", "north america grid",
        "permitting", "public utility commission", "regulatory approval", "transmission grid",
        "transmission investment", "transmission line", "utility capex", "utility commission",
    ])
    for idx, (label, keys) in enumerate(base.SECTORS):
        if label == "반도체/AI":
            merged = list(keys)
            append_unique(merged, ["dram", "nand", "memory", "inventory", "valuation", "tax credit", "tax deduction", "subsidy", "materials", "equipment", "component", "세액공제", "소부장"])
            base.SECTORS[idx] = (label, merged)
            break
    for idx, (label, keys) in enumerate(base.SECTORS):
        if label == "데이터센터/전력망/전력기기":
            merged = list(keys)
            append_unique(merged, ["transmission grid", "transmission line", "interconnection", "permitting", "regulatory approval", "utility commission", "grid investment", "grid delay"])
            base.SECTORS[idx] = (label, merged)
            break
    if not any(label == "해운/항만/물류" for label, _ in base.SECTORS):
        base.SECTORS.append((
            "해운/항만/물류",
            ["port strike", "port labor", "dockworker", "ila", "usmx", "east coast port", "gulf coast port", "freight rate", "shipping rate"],
        ))
    if not any(label == "메가프로젝트 일정/물류" for label, _ in base.SECTORS):
        base.SECTORS.append((
            "메가프로젝트 일정/물류",
            [
                "capex schedule", "construction delay", "delivery schedule", "equipment delivery",
                "mega project", "megaproject", "port strike", "project delay", "project schedule",
            ],
        ))
    if not any(label == "중국 경기부양/벌크선" for label, _ in base.SECTORS):
        base.SECTORS.append((
            "중국 경기부양/벌크선",
            ["china", "stimulus", "iron ore", "coal", "dry bulk", "bulk carrier", "baltic dry", "baltic dry index", "bdi"],
        ))

    original_classify = contract.strict.classify

    def classify(row: dict, now):
        text = base.source_content_text(row)
        alert = original_classify(row, now)
        port_terms = ["port strike", "port labor", "dockworker", "ila", "usmx", "east coast port", "gulf coast port", "contract expires", "freight rate", "shipping rate"]
        china_bulk_terms = ["china", "stimulus", "iron ore", "coal", "dry bulk", "bulk carrier", "baltic dry", "baltic dry index", "bdi"]
        grid_policy_terms = ["transmission grid", "transmission line", "grid investment", "grid approval", "grid delay", "regulatory approval", "permitting", "interconnection", "public utility commission", "utility commission", "utility capex", "ferc", "doe"]
        is_port_strike = any(base.has(text, term) for term in port_terms) and any(base.has(text, term) for term in ["port", "ila", "usmx", "dockworker"])
        is_china_bulk = base.has(text, "china") and base.has(text, "stimulus") and any(base.has(text, term) for term in ["iron ore", "coal", "dry bulk", "bulk c…47589 tokens truncated…DXY", "방산 ETF/티커"]
    if "해운/항만/물류" in alert.get("sectors", []):
        extra += ["SCFI", "Drewry WCI", "BDI", "컨테이너 운임", "벌크선 운임"]
    if "메가프로젝트 일정/물류" in alert.get("sectors", []):
        extra += ["대형 CAPEX 일정", "기자재 납기", "EPC/전력기기 수주 인식", "SCFI", "Drewry WCI"]
    if "중국 경기부양/벌크선" in alert.get("sectors", []):
        extra += ["Iron Ore", "Coal", "BDI", "벌크선 운임", "중국 인프라/부동산 지표"]
    if alert.get("grid_policy_delay"):
        extra += ["FERC", "DOE", "주 공공서비스위원회", "유틸리티 CAPEX", "전력기기/전선/변압기"]
    if alert.get("biotech_leadership_filter"):
        extra += ["FDA", "PDUFA", "XBI", "IBB", "DFII10", "10Y TIPS"]
    if alert.get("robotics_execution_filter"):
        extra += ["Samsung Electronics", "Rainbow Robotics", "RB5-850", "협동로봇"]
    if "전력망 보안/FCC 장비규제" in alert.get("sectors", []):
        extra += ["FSLR", "ENPH", "SEDG", "VRT", "ETN", "GEV", "FCC Covered List"]
    if "EU/한국 정책 영향" in alert.get("sectors", []):
        extra += ["EU 집행위/관보", "철강·배터리·반도체·조선 수출주", "EUR/KRW"]
    if "DOE 전력망/원전/에너지지원" in alert.get("sectors", []):
        extra += ["DOE", "FERC", "NRC", "AP1000", "Westinghouse", "VRT", "ETN", "GEV", "Uranium"]
    try:
        base_text = base.related(alert, fred, te)
        base_parts = [] if base_text == "확인 가능한 직접 티커 없음" else [part.strip() for part in base_text.split(",") if part.strip()]
        return ", ".join(dict.fromkeys(base_parts + extra)) or "확인 가능한 직접 지표 없음"
    except Exception:
        out = []
        if "데이터센터/전력망/전력기기" in alert.get("sectors", []):
            out += ["VRT", "ETN", "GEV", "CEG", "SMH"]
        if "반도체/AI" in alert.get("sectors", []):
            out += ["NVDA", "MU", "AVGO", "AMD", "TSM", "ASML"]
        if "전력망 보안/FCC 장비규제" in alert.get("sectors", []):
            out += ["FSLR", "ENPH", "SEDG", "VRT", "ETN", "GEV", "FCC Covered List"]
        if "EU/한국 정책 영향" in alert.get("sectors", []):
            out += ["EU 집행위/관보", "철강·배터리·반도체·조선 수출주", "EUR/KRW"]
        if "DOE 전력망/원전/에너지지원" in alert.get("sectors", []):
            out += ["DOE", "FERC", "NRC", "AP1000", "Westinghouse", "VRT", "ETN", "GEV", "Uranium"]
        if alert.get("biotech_leadership_filter"):
            out += ["FDA", "PDUFA", "XBI", "IBB", "DFII10", "10Y TIPS"]
        if alert.get("robotics_execution_filter"):
            out += ["Samsung Electronics", "Rainbow Robotics", "RB5-850", "협동로봇"]
        out += extra
        if "할인율" in alert.get("impacts", []):
            out += [
                f"DFII10 {fred.get('value') if fred.get('value') is not None else '확인 불가'}",
                f"TE TIPS {te.get('value') if te.get('value') is not None else '확인 불가'}",
                "IWM/SPY",
            ]
        return ", ".join(dict.fromkeys(out)) or "확인 가능한 직접 지표 없음"


def semiconductor_cycle_check(alert: dict) -> str | None:
    if not alert.get("semiconductor_selloff"):
        return None
    return "메모리 가격·고객사 재고·CAPEX·밸류에이션 부담 동시 악화 여부"


def semiconductor_policy_check(alert: dict) -> str | None:
    if not alert.get("policy_drive"):
        return None
    return "R&D 세액공제 대상·시행 시점·소부장 발주/수주 연결성"


def port_strike_check(alert: dict) -> str | None:
    if not alert.get("port_strike_risk"):
        return None
    return "ILA/USMX 계약 만료·협상 결렬 여부·동부/걸프 항만 차질·기자재 납기/대형 CAPEX 일정"


def china_bulk_check(alert: dict) -> str | None:
    if not alert.get("china_stimulus_bulk"):
        return None
    return "중국 부양책 실물 강도·철광석/석탄 물동량·BDI/벌크선 운임 동행"


def grid_policy_check(alert: dict) -> str | None:
    if not alert.get("grid_policy_delay"):
        return None
    return "정부 승인·규제/인허가·계통접속 일정·유틸리티 CAPEX 집행 속도"


def biotech_leadership_check(alert: dict) -> str | None:
    if not alert.get("biotech_leadership_filter"):
        return None
    return alert.get("biotech_check") or "실제 매출/이익·빅파마 우선순위·FDA 일정·금리/할인율 동시 확인"


def robotics_execution_check(alert: dict) -> str | None:
    if not alert.get("robotics_execution_filter"):
        return None
    return alert.get("robotics_check") or "삼성 조직개편 방향·RB5-850 테스트·발주/CAPEX/매출 인식 연결 확인"


def display_news(alert: dict) -> str:
    return korean_title(alert)


def complete_prose_text(value: object, *, fallback: object = "", limit: int) -> str:
    text = clean_article_summary_text(value) or clean_article_summary_text(fallback) or "확인 불가"
    text = text.rstrip("…").rstrip()
    if len(text) <= limit:
        return text
    head = text[: limit + 1]
    sentence_ends = [
        match.end()
        for match in re.finditer(r"(?:[.!?]|다)(?=\s|$)", head)
        if match.end() >= int(limit * 0.55)
    ]
    if sentence_ends:
        return head[: sentence_ends[-1]].rstrip()
    boundary = max(
        head.rfind(",", int(limit * 0.55), limit),
        head.rfind("·", int(limit * 0.55), limit),
        head.rfind(";", int(limit * 0.55), limit),
        head.rfind(" ", int(limit * 0.7), limit),
    )
    if boundary < int(limit * 0.55):
        boundary = limit - 4
    return head[:boundary].rstrip(" ,·;:") + "입니다."


def compact_gamejoa_prose_lines(body: str) -> tuple[str, int]:
    limits = {
        "- 핵심:": GAMEJOA_CORE_MAX_CHARS,
    }
    output: list[str] = []
    changed = 0
    for raw_line in str(body or "").splitlines():
        stripped = raw_line.strip()
        indent = raw_line[: len(raw_line) - len(raw_line.lstrip())]
        compacted_line = raw_line
        for prefix, limit in limits.items():
            if not stripped.startswith(prefix):
                continue
            value = stripped.removeprefix(prefix).strip()
            compacted = complete_prose_text(value, limit=limit)
            compacted_line = f"{indent}{prefix} {compacted}"
            changed += compacted != value
            break
        output.append(compacted_line)
    suffix = "\n" if str(body or "").endswith("\n") else ""
    return "\n".join(output) + suffix, changed


def compact_alert(alert: dict, idx: int, now, fred: dict, te: dict) -> str:
    alert = normalize_alert_for_output(alert)
    examples = alert.get("examples") or []
    count_suffix = f" ({alert['cluster_count']}건 묶음)" if alert.get("cluster_count") else ""
    status = alert.get("status") or ("공식 확인 전" if examples else "확인 불가")
    impacts = alert.get("impacts") or ["의사결정 영향 제한적"]
    displayed_impacts = display_impacts(impacts)
    interpretation = alert.get("interpretation") or "돈 버는 능력, 할인율, 수급, 시간표 중 하나를 바꿀 수 있는지 확인해야 합니다."
    title = display_news(alert)
    first_impact = displayed_impacts[0] if displayed_impacts else "의사결정"
    article_core = (
        alert.get("telegram_core_fact")
        if alert.get("korean_business_news")
        else ""
    )
    if alert.get("memory_antitrust_lawsuit"):
        core = "\uc0bc\uc131\uc804\uc790\u00b7SK\ud558\uc774\ub2c9\uc2a4\u00b7Micron\uc5d0 DRAM \uac00\uaca9\ub2f4\ud569 \uc9d1\ub2e8\uc18c\uc1a1\uc774 \uc81c\uae30\ub410\uc2b5\ub2c8\ub2e4."
    else:
        core = complete_prose_text(
            article_core or alert.get("policy_plain_summary"),
            fallback=title,
            limit=GAMEJOA_CORE_MAX_CHARS,
        )
    conversion = alert.get("fx_conversion") or {"amounts": []}
    core = compact_converted_core(core, conversion, limit=GAMEJOA_CORE_MAX_CHARS)

    lines = [f"{idx}) [{safe(alert.get('importance'))} | {safe(status)}] {safe(title)}{html.escape(count_suffix, quote=False)}"]
    if examples:
        source_text = source_summary(examples[:4])
    else:
        source_text = html_link(
            "원문 뉴스보기",
            alert.get("link") or "",
        )
    fx_source = fx_provenance_text(conversion)
    if fx_source:
        source_text = f"{source_text} · 환율: {fx_source}"

    lines += [
        f"- 핵심: {safe(core)}",
        f"- 출처: {source_text}",
        "",
    ]
    return "\n".join(lines)


def compact_report(alerts: list[dict], fred: dict, te: dict, now) -> str:
    limit = max(1, min(7, int(os.getenv("RADAR_DISPLAY_LIMIT", "7"))))
    visible = alerts[:limit]
    fx_snapshot = collect_fx_snapshot(visible, now)
    for alert in visible:
        alert["fx_conversion"] = build_alert_fx_conversion(alert, fx_snapshot, now)
    live_mode = os.getenv("RADAR_RUN_MODE", "").strip().lower() == "live"
    if live_mode:
        title = f"📰 실시간 핵심 뉴스 레이더 · {now:%Y년 %m월 %d일} · {now:%H:%M}"
        empty_line = "실시간 고충격 뉴스 직접 확인 없음"
    else:
        title = f"📰 GAMEJOA 장전 핵심 뉴스 레이더 · {now:%Y년 %m월 %d일} · 06:30"
        comment_title = "💡 06:30 장전 뉴스 코멘트"
        followup_line = "06:50 투자기상도에서 수치·수급·테마와 재확인 필요."
        empty_line = "장전 고충격 뉴스 직접 확인 없음"
    lines = [title, f"선별: 핵심 {len(visible)}건", ""]
    if visible:
        for idx, alert in enumerate(visible, 1):
            lines.append(compact_alert(alert, idx, now, fred, te))
        changed = "·".join(display_impacts(visible[0].get("impacts")))
    else:
        lines += [empty_line, ""]
        changed = "명확한 변화 없음"
    if not live_mode:
        lines += [
            comment_title,
            f"오늘 핵심 변화는 `{safe(changed)}`입니다.",
            f"할인율: {safe(telegram.compact_real_yield(fred, te))}",
            followup_line,
        ]
    report = "\n".join(lines).strip() + "\n"
    return guard_preopen_report(report)


def guard_preopen_report(text: str) -> str:
    text, compacted_fields = compact_gamejoa_prose_lines(text)
    errors: list[str] = []
    valid_title = (
        text.startswith("📰 GAMEJOA 장전 핵심 뉴스 레이더 · ")
        or text.startswith("📰 실시간 핵심 뉴스 레이더 · ")
    )
    if not valid_title:
        errors.append("title_contract")
    item_count = sum(1 for line in text.splitlines() if re.match(r"^\d+\)\s+\[", line))
    required = [
        "- 핵심:",
        "- 출처:",
    ]
    for marker in required:
        if item_count and text.count(marker) < item_count:
            errors.append(f"missing_{marker}")
    forbidden_markers = (
        "- 기준/시각:",
        "- 경로/섹터:",
        "- 투자 포인트:",
        "- 의사결정 영향:",
        "- 한국장:",
        "- 반영/반대:",
        "- 실패 신호:",
    )
    for marker in forbidden_markers:
        if item_count and marker in text:
            errors.append(f"forbidden_compact_marker={marker}")
    if text.startswith("📰 실시간 핵심 뉴스 레이더 · ") and "💡 실시간 뉴스 코멘트" in text:
        errors.append("forbidden_live_commentary")
    for marker in ("외화 환산:", "≈"):
        if marker in text:
            errors.append(f"forbidden_currency_format={marker}")
    for phrase in GENERIC_EXPLANATION_PHRASES:
        if item_count and phrase in text:
            errors.append("generic_policy_explanation_displayed")
    for line in text.splitlines():
        if not re.match(r"^\d+\)\s+\[", line):
            continue
        title = re.sub(r"^\d+\)\s+\[[^\]]+\]\s*", "", line).strip()
        title = re.sub(r"\(\d+건 묶음\)$", "", title).strip()
        if mostly_ascii(title):
            errors.append(f"raw_english_heading={title[:80]}")
    low = re.sub(r"https?://\S+", "", text).lower()
    for marker in [
        "this document is also available in the following formats",
        "normalized attributes and metadata",
        "original full text xml",
        "government publishing office metadata",
        "developer tools pages",
    ]:
        if marker in low:
            errors.append(f"federal_register_boilerplate={marker}")
    for marker in ["무단 전재", "재배포 금지", "ai 학습 및 활용 금지"]:
        if marker in low:
            errors.append(f"article_boilerplate={marker}")
    for line in text.splitlines():
        visible_line = html.unescape(line)
        if not visible_line.startswith("- 핵심:"):
            continue
        prefix = "- 핵심:"
        summary = visible_line.removeprefix(prefix).strip()
        limit = GAMEJOA_CORE_MAX_CHARS
        if len(summary) > limit:
            errors.append(f"compact_field_too_long={prefix}{len(summary)}")
        if "…" in summary or re.search(r"\.{3,}", summary):
            errors.append(f"truncated_compact_field={prefix}")
        if re.search(r"(?:보다|에게|에서|으로|와|과|은|는|이|가|을|를|의|며|고)$", summary):
            errors.append(f"incomplete_article_summary={summary[-30:]}")
        foreign_amounts = extract_foreign_amounts(summary)
        if foreign_amounts and not (
            re.search(r"\(약\s*[\d,.]+(?:조|억|만)?원\)", summary)
            or "원화 환산 확인 불가" in summary
        ):
            errors.append("foreign_currency_not_converted")
    current_title = ""
    for line in text.splitlines():
        if re.match(r"^\d+\)\s+\[", line):
            current_title = re.sub(r"^\d+\)\s+\[[^\]]+\]\s*", "", html.unescape(line)).strip()
            current_title = re.sub(r"\(\d+건 묶음\)$", "", current_title).strip()
            continue
        if current_title and line.startswith("- 핵심:"):
            summary = html.unescape(line.removeprefix("- 핵심:").strip())
            if summary == current_title or article_title_restatement(summary, current_title):
                errors.append("headline_repeated_as_summary")
    if errors:
        raise RuntimeError("GAMEJOA preopen radar quality guard blocked Telegram output: " + "; ".join(errors))
    if compacted_fields:
        print(f"GAMEJOA compact prose rewritten={compacted_fields}")
    return text


def send_telegram(text: str) -> None:
    text = guard_preopen_report(text)
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if is_empty_radar_report(text) and not should_send_empty_radar():
        write_delivery_status("skipped_empty", chat_id, len(text), "No high-impact radar item selected")
        print(f"Telegram: skipped empty radar original_chars={len(text)}")
        return
    if not preopen_send_window_open():
        write_delivery_status("skipped_off_window", chat_id, len(text), "Outside GAMEJOA preopen Telegram send window")
        print(f"Telegram: skipped outside preopen send window original_chars={len(text)}")
        return
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token or not chat_id:
        write_delivery_status("blocked", chat_id, len(text), "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing")
        raise RuntimeError("Telegram delivery blocked: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing")
    message = fit_telegram_html(text, base.TELEGRAM_LIMIT)
    body = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": "true",
        "parse_mode": "HTML",
    }).encode("utf-8")
    last_error = ""
    for attempt in range(1, 4):
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                resp.read()
            write_delivery_status("sent", chat_id, len(text), "", len(message), attempt)
            print(f"Telegram: sent chars={len(message)} original_chars={len(text)} attempt={attempt}")
            return
        except urllib.error.HTTPError as exc:
            error_text = exc.read().decode("utf-8", "replace")[:500]
            last_error = f"Telegram HTTP {exc.code}: {error_text}"
            if attempt < 3 and (exc.code == 429 or exc.code >= 500):
                retry_after = exc.headers.get("retry-after")
                delay = int(retry_after) if retry_after and retry_after.isdigit() else attempt
                time.sleep(delay)
                continue
            break
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < 3:
                time.sleep(attempt)
                continue
            break
    write_delivery_status("failed", chat_id, len(text), last_error, len(message), 3)
    raise RuntimeError(f"Telegram delivery failed: {last_error}")


def is_empty_radar_report(text: str) -> bool:
    return "선별: 핵심 0건" in text


def should_send_empty_radar() -> bool:
    return os.getenv("SEND_EMPTY_RADAR", "").lower() in {"1", "true", "yes", "y"}


def parse_hhmm(value: str, fallback: tuple[int, int]) -> int:
    match = re.match(r"^\s*(\d{1,2}):(\d{2})\s*$", value or "")
    if not match:
        return fallback[0] * 60 + fallback[1]
    hour, minute = int(match.group(1)), int(match.group(2))
    return max(0, min(23, hour)) * 60 + max(0, min(59, minute))


def preopen_send_window_open() -> bool:
    if os.getenv("RADAR_RUN_MODE", "").strip().lower() == "live":
        return True
    if os.getenv("ALLOW_OFF_WINDOW_TELEGRAM", "").lower() in {"1", "true", "yes", "y"}:
        return True
    now = base.kst_now()
    current = now.hour * 60 + now.minute
    start = parse_hhmm(os.getenv("PREOPEN_SEND_WINDOW_START_KST", "05:30"), (5, 30))
    end = parse_hhmm(os.getenv("PREOPEN_SEND_WINDOW_END_KST", "07:30"), (7, 30))
    if start <= end:
        return start <= current <= end
    return current >= start or current <= end


def fit_telegram_html(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    suffix = "\n\n전체 보고서는 GitHub Actions artifact에서 확인 필요."
    candidate = text[: max(0, limit - len(suffix))]
    newline = candidate.rfind("\n")
    if newline > 1800:
        candidate = candidate[:newline]
    if candidate.count("<a ") > candidate.count("</a>"):
        candidate = candidate[: candidate.rfind("<a ")].rstrip()
    return (candidate.rstrip() + suffix)[:limit]


def write_delivery_status(
    status: str,
    chat_id: str,
    original_chars: int,
    error: str = "",
    sent_chars: int | None = None,
    attempts: int | None = None,
) -> None:
    payload = {
        "status": status,
        "chat_id_masked": mask_chat_id(chat_id),
        "original_chars": original_chars,
        "sent_chars": sent_chars,
        "attempts": attempts,
        "error": error,
    }
    base.OUT.mkdir(exist_ok=True)
    (base.OUT / "gamejoa_preopen_news_radar_delivery.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def mask_chat_id(value: str) -> str:
    if not value:
        return ""
    return "*" * max(0, len(value) - 4) + value[-4:]


telegram.compact_report = compact_report
telegram.send_telegram = send_telegram
telegram.final_alerts_for_output = quality_display_alerts
telegram.canonical_alert_for_seen = normalize_alert_for_output


if __name__ == "__main__":
    raise SystemExit(telegram.main())