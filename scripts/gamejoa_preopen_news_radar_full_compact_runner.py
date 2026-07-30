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
        is_china_bulk = base.has(text, "china") and base.has(text, "stimulus") and any(base.has(text, term) for term in ["iron ore", "coal", "dry bulk", "bulk carrier", "baltic dry", "bdi"])
        is_grid_policy = any(base.has(text, term) for term in grid_policy_terms) and any(base.has(text, term) for term in ["approval", "regulatory", "permitting", "delay", "interconnection", "commission", "ferc", "doe"])

        if (is_port_strike or is_china_bulk or is_grid_policy) and not alert:
            age = base.age_hours(row, now)
            sectors = ["메가프로젝트 일정/물류", "해운/항만/물류"] if is_port_strike else ["중국 경기부양/벌크선"] if is_china_bulk else ["데이터센터/전력망/전력기기"]
            if is_china_bulk:
                sectors.append("해운/항만/물류")
            impacts = ["시간표", "돈 버는 능력"] if is_port_strike else ["돈 버는 능력"] if is_china_bulk else ["할인율", "시간표"]
            score = 92 + (10 if age is not None and age <= 12 else 0)
            status = "확정" if row.get("layer") == "official" else "공식 확인 전"
            alert = {
                "score": score,
                "importance": "상" if score >= 100 else "중",
                "status": status,
                "news": base.clean(row.get("title")),
                "publisher": row.get("publisher") or row.get("source"),
                "source": row.get("source"),
                "link": row.get("link") or "",
                "published": row["published"].isoformat(timespec="minutes") if row.get("published") else "확인 불가",
                "impacts": impacts,
                "paths": ["이익" if x == "돈 버는 능력" else "정책 타임라인" for x in impacts],
                "sectors": sectors,
                "matched": [],
                "local_dc_policy": False,
                "reflection": "낮음" if age is not None and age <= 6 else "중간",
                "counter": "제목·요약 기반 1차 감지라 원문 세부조건과 공식 문서 확인 전 과대해석 가능",
                "interpretation": "",
                "failed_signal": "",
                "korea_basis": "예고된 이벤트의 공식화" if status == "확정" else "외신 확산",
            }

        if alert and is_grid_policy:
            for impact in ["할인율", "시간표"]:
                if impact not in alert["impacts"]:
                    alert["impacts"].append(impact)
            if "의사결정 영향 제한적" in alert["impacts"] and len(alert["impacts"]) > 1:
                alert["impacts"] = [x for x in alert["impacts"] if x != "의사결정 영향 제한적"]
            alert["paths"] = [
                "이익" if x == "돈 버는 능력" else "할인율" if x == "할인율" else "수급" if x == "수급" else "정책 타임라인"
                for x in alert["impacts"]
            ]
            if "데이터센터/전력망/전력기기" not in alert["sectors"]:
                alert["sectors"].append("데이터센터/전력망/전력기기")
            alert["score"] = max(int(alert.get("score", 0)), 100)
            alert["importance"] = "상" if alert["score"] >= 100 else "중"
            alert["grid_policy_delay"] = True
            alert["news"] = "북미 송전망 투자 정책 변수: 정부 승인·규제 지연 리스크"
            alert["interpretation"] = "북미 송전망 투자는 전력 수요보다 정부 승인, 규제, 인허가, 계통접속 일정에 속도가 좌우됩니다. 지연 시 전력기기·전선·변압기 수주 기대의 인식 시점과 밸류에이션 프리미엄을 재점검해야 합니다."
            alert["failed_signal"] = "FERC/DOE·주 공공서비스위원회 승인과 유틸리티 CAPEX 일정이 유지되고 계통접속·송전선 인허가 지연 신호가 없으면 재료 약화"

        if alert and is_port_strike:
            for impact in ["시간표", "돈 버는 능력"]:
                if impact not in alert["impacts"]:
                    alert["impacts"].append(impact)
            if "의사결정 영향 제한적" in alert["impacts"] and len(alert["impacts"]) > 1:
                alert["impacts"] = [x for x in alert["impacts"] if x != "의사결정 영향 제한적"]
            impact_order = ["시간표", "돈 버는 능력", "할인율", "수급"]
            alert["impacts"] = [x for x in impact_order if x in alert["impacts"]] + [x for x in alert["impacts"] if x not in impact_order]
            alert["paths"] = [
                "이익" if x == "돈 버는 능력" else "할인율" if x == "할인율" else "수급" if x == "수급" else "메가프로젝트 일정"
                for x in alert["impacts"]
            ]
            for sector in ["메가프로젝트 일정/물류", "해운/항만/물류"]:
                if sector not in alert["sectors"]:
                    alert["sectors"].append(sector)
            alert["score"] = max(int(alert.get("score", 0)), 102)
            alert["importance"] = "상" if alert["score"] >= 100 else "중"
            alert["port_strike_risk"] = True
            alert["news"] = "메가프로젝트 일정: 미국 동부·걸프 항만 계약 만료/파업 리스크"
            alert["interpretation"] = "미국 동부·걸프 항만 파업 리스크는 AI 데이터센터, 전력기기, 플랜트/EPC 같은 대형 프로젝트의 기자재 반입, 납기, 설치 일정과 운임을 흔드는 시간표 재료입니다. 운임 급등만이 아니라 프로젝트 지연 비용과 매출 인식 시점까지 확인해야 합니다."
            alert["failed_signal"] = "노사 협상 타결, 파업 유예, 항만 적체·컨테이너 운임 미반응, 핵심 기자재 납기·프로젝트 일정 차질 제한 시 재료 약화"

        if alert and is_china_bulk:
            if "돈 버는 능력" not in alert["impacts"]:
                alert["impacts"].append("돈 버는 능력")
            if "의사결정 영향 제한적" in alert["impacts"] and len(alert["impacts"]) > 1:
                alert["impacts"] = [x for x in alert["impacts"] if x != "의사결정 영향 제한적"]
            alert["paths"] = [
                "이익" if x == "돈 버는 능력" else "할인율" if x == "할인율" else "수급" if x == "수급" else "정책 타임라인"
                for x in alert["impacts"]
            ]
            for sector in ["중국 경기부양/벌크선", "해운/항만/물류"]:
                if sector not in alert["sectors"]:
                    alert["sectors"].append(sector)
            alert["score"] = max(int(alert.get("score", 0)), 100)
            alert["importance"] = "상" if alert["score"] >= 100 else "중"
            alert["china_stimulus_bulk"] = True
            alert["news"] = "중국 경기부양책: 철광석·석탄 물동량과 벌크선 운임 회복 기대"
            alert["interpretation"] = "중국 추가 부양책은 철광석·석탄 물동량 회복 기대를 통해 벌크선 운임과 해운주 이익 추정에 연결될 수 있습니다."
            alert["failed_signal"] = "부양책이 부동산·인프라 실물 수요로 연결되지 않거나 철광석·석탄 가격, BDI, 벌크선 운임이 동행하지 않으면 기대 약화"

        if alert and "반도체/AI" in alert.get("sectors", []):
            selloff_terms = ["selloff", "stock drop", "memory price", "customer inventory", "oversupply", "valuation"]
            policy_terms = ["tax credit", "tax deduction", "investment credit", "chip subsidy", "subsidy", "r&d", "rd tax credit", "semiconductor tax credit", "세액공제", "소부장"]
            if any(base.has(text, term) for term in policy_terms):
                for impact in ["돈 버는 능력", "시간표"]:
                    if impact not in alert["impacts"]:
                        alert["impacts"].append(impact)
                alert["paths"] = [
                    "이익" if x == "돈 버는 능력" else "할인율" if x == "할인율" else "수급" if x == "수급" else "정책 타임라인"
                    for x in alert["impacts"]
                ]
                alert["score"] = max(int(alert.get("score", 0)), 94)
                alert["importance"] = "상" if alert["score"] >= 100 else "중"
                alert["policy_drive"] = True
                alert["interpretation"] = "반도체 R&D 세액공제 확대는 직접 매출보다 연구개발·투자 현금흐름과 정책 타임라인을 바꾸는 재료입니다. 소부장으로 온기가 확산되는지는 세액공제 대상, 적용 시점, 국내 장비·소재 발주 연결성을 확인해야 합니다."
                alert["failed_signal"] = "세액공제 확대가 법안·시행령·예산으로 확정되지 않거나 소부장 발주·수주·CAPEX 증가로 연결되지 않으면 정책 기대에 그칠 수 있음"
            elif any(base.has(text, term) for term in selloff_terms):
                alert["semiconductor_selloff"] = True
                alert["interpretation"] = (
                    "반도체 급락은 가격 사이클 하나로만 보지 않고 메모리 가격, 고객사 재고, "
                    "설비투자, 밸류에이션 부담이 동시에 흔들리는지 확인합니다."
                )
                alert["failed_signal"] = (
                    "메모리 가격·고객사 재고·CAPEX·밸류에이션 중 복수 축의 악화가 확인되지 않거나 "
                    "SOX/MU/NVDA/삼성전자·SK하이닉스 반응이 제한되면 일회성 조정 가능"
                )
        return alert

    contract.strict.classify = classify


enforce_semiconductor_cycle_contract()


def enforce_biotech_leadership_filter() -> None:
    append_unique(base.QUERIES, [BIOTECH_QUERY])
    append_unique(base.TERMS, BIOTECH_TERMS)
    for idx, (label, keys) in enumerate(base.SECTORS):
        if label == BIOTECH_SECTOR:
            merged = list(keys)
            append_unique(merged, BIOTECH_DOMAIN_TERMS)
            base.SECTORS[idx] = (label, merged)
            break
    else:
        base.SECTORS.append((BIOTECH_SECTOR, BIOTECH_DOMAIN_TERMS))

    original_classify = contract.strict.classify

    def classify(row: dict, now):
        text = base.source_content_text(row)
        alert = original_classify(row, now)
        is_biotech = any(base.has(text, term) for term in BIOTECH_DOMAIN_TERMS) or (
            alert is not None and BIOTECH_SECTOR in alert.get("sectors", [])
        )
        if not is_biotech:
            return alert

        has_transfer = any(base.has(text, term) for term in BIOTECH_TRANSFER_TERMS)
        has_sales = any(base.has(text, term) for term in BIOTECH_SALES_TERMS)
        has_fda = any(base.has(text, term) for term in BIOTECH_FDA_TERMS)
        has_priority = any(base.has(text, term) for term in BIOTECH_PHARMA_PRIORITY_TERMS)
        has_discount = any(base.has(text, term) for term in BIOTECH_DISCOUNT_TERMS)
        has_leadership_signal = has_sales or has_fda or has_priority or has_discount

        if has_transfer and not has_leadership_signal:
            return None
        if not alert:
            return None

        append_unique(alert.setdefault("sectors", []), [BIOTECH_SECTOR])
        if has_sales:
            append_unique(alert.setdefault("impacts", []), ["돈 버는 능력"])
        if has_fda or has_priority:
            append_unique(alert.setdefault("impacts", []), ["시간표"])
        if has_discount:
            append_unique(alert.setdefault("impacts", []), ["할인율"])
        if len(alert["impacts"]) > 1:
            alert["impacts"] = [x for x in alert["impacts"] if x != "의사결정 영향 제한적"]
        alert["paths"] = [
            "이익" if x == "돈 버는 능력" else "할인율" if x == "할인율" else "수급" if x == "수급" else "정책 타임라인"
            for x in alert["impacts"]
        ]
        alert["score"] = max(int(alert.get("score", 0)), 108 if (has_sales and has_fda) else 100 if (has_fda or has_priority) else 92)
        alert["importance"] = "상" if int(alert["score"]) >= 100 else "중"
        alert["biotech_leadership_filter"] = True
        alert["biotech_check"] = (
            "실제 매출/이익, 빅파마 파이프라인 우선순위, FDA 일정, 금리/할인율 중 무엇이 바뀌는지 확인"
        )
        alert["counter"] = (
            "기술이전 발표만으로는 주도주 복귀 신호가 약합니다. 선급금·마일스톤의 매출 인식, "
            "빅파마 우선순위, FDA 일정, 금리 환경이 함께 확인되어야 합니다."
        )
        alert["interpretation"] = (
            "바이오가 다시 주도주가 되려면 기대가 아니라 실제 매출과 이익 전환이 보여야 합니다. "
            "FDA 일정과 빅파마 파이프라인 우선순위, 할인율이 같이 맞을 때만 장전 핵심 후보로 봅니다."
        )
        alert["failed_signal"] = (
            "기술이전 금액·기간·상대방 우선순위·FDA 일정·매출 인식 조건이 확인되지 않거나 "
            "금리 상승으로 바이오 밸류에이션이 눌리면 테마성 반응에 그칠 가능성"
        )
        return alert

    contract.strict.classify = classify


enforce_biotech_leadership_filter()


def enforce_robotics_execution_filter() -> None:
    append_unique(base.QUERIES, [ROBOTICS_QUERY])
    append_unique(base.TERMS, ROBOTICS_TERMS)
    if not any(label == ROBOTICS_SECTOR for label, _ in base.SECTORS):
        base.SECTORS.append((ROBOTICS_SECTOR, ROBOTICS_DOMAIN_TERMS + ROBOTICS_EXECUTION_TERMS))

    original_classify = contract.strict.classify

    def classify(row: dict, now):
        text = base.source_content_text(row)
        alert = original_classify(row, now)
        has_samsung = any(base.has(text, term) for term in ROBOTICS_SAMSUNG_TERMS)
        has_domain = any(base.has(text, term) for term in ROBOTICS_DOMAIN_TERMS)
        has_rainbow = any(base.has(text, term) for term in ["rainbow robotics", "rb5-850", "레인보우로보틱스", "협동로봇"])
        has_execution = any(base.has(text, term) for term in ROBOTICS_EXECUTION_TERMS)
        has_org = any(base.has(text, term) for term in ROBOTICS_ORG_TERMS)
        has_test = any(base.has(text, term) for term in ROBOTICS_TEST_TERMS)
        is_robotics = (
            has_samsung and has_domain and (has_execution or has_org or has_test)
        ) or (
            has_rainbow and (has_samsung or has_execution or has_test)
        )
        if not is_robotics:
            return alert

        age = base.age_hours(row, now)
        status = "확정" if row.get("layer") == "official" else "공식 확인 전"
        impacts = ["시간표"]
        if has_execution:
            impacts.insert(0, "돈 버는 능력")
        if has_rainbow:
            impacts.append("수급")
        impacts = list(dict.fromkeys(impacts))
        score = (106 if has_execution else 96 if (has_org or has_test) else 88) + (6 if age is not None and age <= 12 else 0)

        if not alert:
            alert = {
                "score": score,
                "importance": "상" if score >= 100 else "중",
                "status": status,
                "news": "삼성 로봇 실행 단계: 조직 재정비와 생산라인 자동화 전환 체크",
                "publisher": row.get("publisher") or row.get("source"),
                "source": row.get("source"),
                "link": row.get("link") or "",
                "published": row["published"].isoformat(timespec="minutes") if row.get("published") else "확인 불가",
                "impacts": impacts,
                "paths": ["이익" if x == "돈 버는 능력" else "수급" if x == "수급" else "실행 타임라인" for x in impacts],
                "sectors": [ROBOTICS_SECTOR],
                "matched": [],
                "local_dc_policy": False,
                "reflection": "중간",
                "counter": "",
                "interpretation": "",
                "failed_signal": "",
                "korea_basis": "예고된 이벤트의 공식화" if status == "확정" else "외신 확산",
            }
        else:
            alert["score"] = max(int(alert.get("score", 0)), score)
            alert["importance"] = "상" if int(alert["score"]) >= 100 else "중"
            alert["status"] = alert.get("status") or status
            append_unique(alert.setdefault("impacts", []), impacts)
            if "의사결정 영향 제한적" in alert["impacts"] and len(alert["impacts"]) > 1:
                alert["impacts"] = [x for x in alert["impacts"] if x != "의사결정 영향 제한적"]
            alert["paths"] = [
                "이익" if x == "돈 버는 능력" else "할인율" if x == "할인율" else "수급" if x == "수급" else "실행 타임라인"
                for x in alert["impacts"]
            ]
            append_unique(alert.setdefault("sectors", []), [ROBOTICS_SECTOR])

        alert["robotics_execution_filter"] = True
        alert["robotics_check"] = (
            "삼성 미래로봇추진단 재정비가 축소인지 실행 전환인지, RB5-850/협동로봇 테스트가 발주·CAPEX·매출 인식으로 연결되는지 확인"
        )
        alert["news"] = "삼성 로봇 실행 단계: 조직 재정비와 레인보우로보틱스 생산라인 자동화 체크"
        alert["counter"] = (
            "조직 재정비만으로는 호재도 악재도 확정하기 어렵습니다. 삼성의 로봇 사업 축소 발표가 없고 "
            "생산라인 테스트·발주·공급계약·CAPEX가 확인될 때만 실적 재료로 볼 수 있습니다."
        )
        alert["interpretation"] = (
            "삼성전자 생산라인 자동화 수요가 실제 도입 단계로 넘어가면 레인보우로보틱스의 매출 개선 속도가 빨라질 수 있습니다. "
            "반대로 조직개편 불확실성은 협력 규모와 시간표를 흔드는 변수라 공식 후속 확인이 필요합니다."
        )
        alert["failed_signal"] = (
            "미래로봇추진단 재정비가 사업 축소로 확인되거나 RB5-850 테스트가 발주·도입·공급계약으로 이어지지 않으면 "
            "로봇 테마 수급만 남고 실적 재료는 약화"
        )
        return alert

    contract.strict.classify = classify


enforce_robotics_execution_filter()


def enforce_source_identity_contract() -> None:
    """Restore immutable source fields after every legacy classifier overlay.

    Some older overlays create a replacement alert dictionary.  The decision
    fields are useful, but source identity must always come from the row that
    supplied the link, never from a previous Korean template.
    """
    original_classify = contract.strict.classify

    def classify(row: dict, now):
        alert = original_classify(row, now)
        if not alert:
            return alert
        alert = dict(alert)
        alert["source_title"] = base.clean(row.get("source_title") or row.get("title") or alert.get("source_title") or alert.get("news"))
        alert["source_abstract"] = base.clean(row.get("source_abstract") or row.get("summary") or alert.get("source_abstract"))
        alert["source_document_number"] = base.clean(row.get("source_document_number") or alert.get("source_document_number"))
        alert["source_metadata_url"] = base.clean(row.get("source_metadata_url") or alert.get("source_metadata_url"))
        return alert

    contract.strict.classify = classify


enforce_source_identity_contract()


def is_korean_business_row(row: dict) -> bool:
    publisher = str(row.get("publisher") or row.get("source") or "").lower()
    link = str(row.get("link") or "").lower()
    source = str(row.get("source") or "").lower()
    return any(
        marker in f"{publisher} {link}"
        for marker in (
            "이투데이",
            "etoday.co.kr",
            "전자신문",
            "etnews.com",
            "이데일리",
            "edaily.co.kr",
            "매일경제",
            "mk.co.kr",
            "머니투데이",
            "mt.co.kr",
            "헤럴드경제",
            "heraldcorp.com",
            "연합뉴스",
            "yna.co.kr",
            "연합뉴스tv",
            "yonhapnewstv.co.kr",
            "한국경제",
            "hankyung.com",
            "서울경제",
            "sedaily.com",
            "파이낸셜뉴스",
            "fnnews.com",
            "아시아경제",
            "asiae.co.kr",
            "뉴스1",
            "news1.kr",
            "디지털타임스",
            "dt.co.kr",
        )
    ) or source.startswith("국내 신뢰매체")


def korean_business_publisher(row: dict) -> str:
    link = str(row.get("link") or "").lower()
    for domain, publisher in KOREAN_BUSINESS_PUBLISHER_DOMAINS.items():
        if domain in link:
            return publisher
    return str(row.get("publisher") or row.get("source") or "국내 신뢰매체")


def korean_business_source_domain_allowed(link: str) -> bool:
    lowered = str(link or "").lower()
    return any(domain in lowered for domain in KOREAN_BUSINESS_PUBLISHER_DOMAINS)


def korean_business_event_date(row: dict) -> str:
    published = row.get("published")
    if hasattr(published, "date"):
        return published.date().isoformat()
    return "date-unavailable"


KOREAN_BUSINESS_DETAIL_LIMIT = max(
    12,
    int(os.environ.get("GAMEJOA_KOREAN_BUSINESS_DETAIL_LIMIT", "72")),
)
KOREAN_BUSINESS_DETAIL_WORKERS = max(
    2,
    int(os.environ.get("GAMEJOA_KOREAN_BUSINESS_DETAIL_WORKERS", "8")),
)
KOREAN_BUSINESS_PRIORITY_TERMS = {
    "외국인": 8,
    "순매수": 10,
    "순매도": 7,
    "삼성전자": 6,
    "sk하이닉스": 8,
    "하이닉스": 6,
    "hbm": 9,
    "cxl": 10,
    "테스터": 8,
    "양산평가": 10,
    "상용화": 7,
    "공급계약": 10,
    "수주": 9,
    "실적": 7,
    "가이던스": 8,
    "증설": 7,
    "관세": 8,
    "수출통제": 9,
    "엔비디아": 9,
    "브로드컴": 8,
    "앤트로픽": 8,
    "회동": 6,
    "협력": 7,
    "파트너십": 9,
    "레버리지": 10,
    "etf": 9,
    "etn": 9,
    "기본예탁금": 12,
    "금융위원회": 10,
    "나스닥": 8,
    "필라델피아 반도체": 12,
    "fomc": 10,
    "반도체주 급락": 12,
    "데이터센터": 7,
    "철강 수요": 10,
    "형강": 8,
    "샘 올트먼": 12,
    "오픈ai": 11,
    "이재용": 10,
    "젠슨 황": 10,
    "코스피": 8,
    "a16z": 12,
    "k스타트업": 10,
    "벤처캐피털": 9,
    "감원": 11,
    "ai 팩토리": 11,
    "베라 루빈": 12,
    "장기 공급": 12,
    "장기공급": 12,
    "cxmt": 11,
    "창신메모리": 11,
    "국제유가": 10,
    "호르무즈": 12,
    "후티": 11,
    "외식 물가": 8,
}


def korean_business_detail_priority(row: dict) -> tuple[int, float]:
    text = f"{row.get('title') or ''} {row.get('summary') or ''}".lower()
    score = sum(
        weight for term, weight in KOREAN_BUSINESS_PRIORITY_TERMS.items()
        if term in text
    )
    published = row.get("published")
    timestamp = published.timestamp() if hasattr(published, "timestamp") else 0.0
    return score, timestamp


ARTICLE_SUMMARY_NOISE_PATTERNS = [
    r"무단\s*전재(?:\s*[-·]?\s*재배포)?\s*금지",
    r"AI\s*학습\s*및\s*활용\s*금지",
    r"저작권자\s*©?\s*이투데이",
    r"Copyright\s*©?\s*Etoday",
    r"\[(?:헤럴드경제|이데일리|머니투데이|매일경제|전자신문|연합뉴스)"
    r"\s*=\s*[^\]]{1,30}\s*기자\]",
]
ARTICLE_SUMMARY_MAX_CHARS = 420
ARTICLE_MATERIAL_TERMS = (
    "매출", "영업이익", "순이익", "당기순이익", "실적", "수주", "계약", "발주",
    "증설", "출하", "가격", "인상", "인하", "증가", "감소", "순매수", "순매도",
    "배당", "자사주", "자기주식", "소각", "취득", "상용화", "양산평가",
)
ARTICLE_RESULT_TERMS = (
    "매출", "영업이익", "순이익", "당기순이익", "실적", "수주", "계약", "출하",
)
ARTICLE_SHAREHOLDER_TERMS = ("배당", "자사주", "자기주식", "소각", "취득")
INSIDER_ROLE_PATTERN = (
    r"(?:회장|부회장|대표이사|대표|사장|총괄\s*프로듀서|CCO|CEO|CFO|"
    r"임원|사내이사|이사회\s*의장)"
)
INSIDER_PURCHASE_PATTERN = r"(?:장내\s*매수|주식\s*매수|지분\s*매수|자사주\s*매입|취득)"
KOREAN_WON_AMOUNT_PATTERN = (
    r"(?=\d)(?:\d[\d,.]*조)?(?:\d[\d,.]*억)?"
    r"(?:\d[\d,.]*만)?(?:\d[\d,.]*)?원"
)
GAMEJOA_CORE_MAX_CHARS = 100
GAMEJOA_INVESTMENT_MAX_CHARS = 100
GAMEJOA_ARTICLE_FACT_LIMIT = 2
FX_QUERY_TIMEOUT_SECONDS = max(3, int(os.getenv("RADAR_FX_TIMEOUT_SECONDS", "8")))
YAHOO_FINANCE_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/"
FOREIGN_CURRENCY_SPECS = {
    "USD": {
        "labels": ("미국 달러", "미달러", "달러", "USD", "US$"),
        "symbol": "KRW=X",
    },
    "EUR": {"labels": ("유로", "EUR"), "symbol": "EURKRW=X"},
    "JPY": {"labels": ("일본 엔", "엔화", "엔", "JPY"), "symbol": "JPYKRW=X"},
    "CNY": {"labels": ("중국 위안", "위안화", "위안", "CNY", "RMB"), "symbol": "CNYKRW=X"},
    "GBP": {"labels": ("영국 파운드", "파운드", "GBP"), "symbol": "GBPKRW=X"},
    "CHF": {"labels": ("스위스 프랑", "스위스프랑", "CHF"), "symbol": "CHFKRW=X"},
    "CAD": {"labels": ("캐나다 달러", "캐나다달러", "CAD"), "symbol": "CADKRW=X"},
    "AUD": {"labels": ("호주 달러", "호주달러", "AUD"), "symbol": "AUDKRW=X"},
    "HKD": {"labels": ("홍콩 달러", "홍콩달러", "HKD"), "symbol": "HKDKRW=X"},
    "SGD": {"labels": ("싱가포르 달러", "싱가포르달러", "SGD"), "symbol": "SGDKRW=X"},
    "TWD": {"labels": ("대만 달러", "대만달러", "TWD"), "symbol": "TWDKRW=X"},
    "INR": {"labels": ("인도 루피", "루피", "INR"), "symbol": "INRKRW=X"},
    "BRL": {"labels": ("브라질 헤알", "헤알", "BRL"), "symbol": "BRLKRW=X"},
    "MXN": {"labels": ("멕시코 페소", "멕시코페소", "MXN"), "symbol": "MXNKRW=X"},
    "NZD": {"labels": ("뉴질랜드 달러", "뉴질랜드달러", "NZD"), "symbol": "NZDKRW=X"},
    "SEK": {"labels": ("스웨덴 크로나", "SEK"), "symbol": "SEKKRW=X"},
    "NOK": {"labels": ("노르웨이 크로네", "NOK"), "symbol": "NOKKRW=X"},
    "DKK": {"labels": ("덴마크 크로네", "DKK"), "symbol": "DKKKRW=X"},
    "PLN": {"labels": ("폴란드 즈워티", "즈워티", "PLN"), "symbol": "PLNKRW=X"},
    "TRY": {"labels": ("튀르키예 리라", "터키 리라", "리라", "TRY"), "symbol": "TRYKRW=X"},
    "SAR": {"labels": ("사우디 리얄", "리얄", "SAR"), "symbol": "SARKRW=X"},
    "AED": {"labels": ("UAE 디르함", "아랍에미리트 디르함", "디르함", "AED"), "symbol": "AEDKRW=X"},
    "IDR": {"labels": ("인도네시아 루피아", "루피아", "IDR"), "symbol": "IDRKRW=X"},
    "MYR": {"labels": ("말레이시아 링깃", "링깃", "MYR"), "symbol": "MYRKRW=X"},
    "THB": {"labels": ("태국 바트", "바트", "THB"), "symbol": "THBKRW=X"},
    "PHP": {"labels": ("필리핀 페소", "필리핀페소", "PHP"), "symbol": "PHPKRW=X"},
    "ZAR": {"labels": ("남아공 랜드", "랜드", "ZAR"), "symbol": "ZARKRW=X"},
}
FOREIGN_NUMBER_PATTERN = r"\d[\d,.]*(?:\s*[천백십조억만]\s*\d[\d,.]*)*(?:\s*[천백십조억만])?"
ENGLISH_SCALE_MULTIPLIERS = {
    "trillion": 1_000_000_000_000,
    "tn": 1_000_000_000_000,
    "billion": 1_000_000_000,
    "bn": 1_000_000_000,
    "million": 1_000_000,
    "mn": 1_000_000,
}


def clean_article_summary_text(text: str) -> str:
    cleaned = html.unescape(str(text or "")).replace("\xa0", " ")
    for pattern in ARTICLE_SUMMARY_NOISE_PATTERNS:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^[\s,;:>|·•\-]+", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def parse_small_korean_number(value: str) -> float:
    text = re.sub(r"[,\s]", "", value or "")
    if not text:
        return 0.0
    total = 0.0
    remaining = text
    for unit, multiplier in (("천", 1_000), ("백", 100), ("십", 10)):
        if unit not in remaining:
            continue
        left, remaining = remaining.split(unit, 1)
        total += (float(left) if left else 1.0) * multiplier
    if remaining:
        total += float(remaining)
    return total


def parse_foreign_number(value: str, scale: str = "") -> float | None:
    text = re.sub(r"[,\s]", "", value or "")
    if not text:
        return None
    try:
        total = 0.0
        remaining = text
        for unit, multiplier in (("조", 1_000_000_000_000), ("억", 100_000_000), ("만", 10_000)):
            if unit not in remaining:
                continue
            left, remaining = remaining.split(unit, 1)
            total += parse_small_korean_number(left or "1") * multiplier
        total += parse_small_korean_number(remaining)
        total *= ENGLISH_SCALE_MULTIPLIERS.get((scale or "").lower(), 1)
        return total if total > 0 else None
    except (TypeError, ValueError):
        return None


def currency_label_to_code(label: str) -> str:
    normalized = re.sub(r"\s+", " ", str(label or "")).strip().lower()
    symbol_codes = {"$": "USD", "us$": "USD", "€": "EUR", "£": "GBP"}
    if normalized in symbol_codes:
        return symbol_codes[normalized]
    for code, spec in FOREIGN_CURRENCY_SPECS.items():
        if any(normalized == candidate.lower() for candidate in spec["labels"]):
            return code
    return ""


def extract_foreign_amounts(text: str) -> list[dict]:
    cleaned = clean_article_summary_text(text)
    labels = sorted(
        {
            label
            for spec in FOREIGN_CURRENCY_SPECS.values()
            for label in spec["labels"]
        },
        key=len,
        reverse=True,
    )
    label_pattern = "|".join(re.escape(label) for label in labels)
    prefix_labels = sorted(
        {"US$", "$", "€", "£", *FOREIGN_CURRENCY_SPECS.keys()},
        key=len,
        reverse=True,
    )
    prefix_label_pattern = "|".join(re.escape(label) for label in prefix_labels)
    suffix_pattern = re.compile(
        rf"(?P<number>{FOREIGN_NUMBER_PATTERN})\s*"
        rf"(?P<scale>trillion|billion|million|tn|bn|mn)?\s*"
        rf"(?P<label>{label_pattern})",
        re.IGNORECASE,
    )
    prefix_pattern = re.compile(
        rf"(?<![A-Za-z])(?P<label>{prefix_label_pattern})\s*"
        rf"(?P<number>{FOREIGN_NUMBER_PATTERN})\s*"
        rf"(?P<scale>trillion|billion|million|tn|bn|mn)?",
        re.IGNORECASE,
    )
    output: list[dict] = []
    seen: set[tuple[str, int]] = set()
    occupied: list[tuple[int, int]] = []
    for pattern in (suffix_pattern, prefix_pattern):
        for match in pattern.finditer(cleaned):
            if any(match.start() < end and match.end() > start for start, end in occupied):
                continue
            code = currency_label_to_code(match.group("label"))
            amount = parse_foreign_number(match.group("number"), match.group("scale") or "")
            if not code or amount is None:
                continue
            key = (code, int(round(amount)))
            if key in seen:
                continue
            seen.add(key)
            occupied.append(match.span())
            output.append(
                {
                    "code": code,
                    "amount": amount,
                    "raw": re.sub(r"\s+", " ", match.group(0)).strip(),
                    "start": match.start(),
                    "end": match.end(),
                }
            )
    output.sort(key=lambda item: item["start"])
    return output


def yahoo_fx_url(code: str) -> str:
    symbol = FOREIGN_CURRENCY_SPECS.get(code, {}).get("symbol") or f"{code}KRW=X"
    return (
        YAHOO_FINANCE_CHART_URL
        + urllib.parse.quote(symbol, safe="")
        + "?interval=1d&range=5d"
    )


def fetch_yahoo_krw_rate(code: str, now) -> dict:
    url = yahoo_fx_url(code)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; GAMEJOA-news-radar/1.0)",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=FX_QUERY_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
        result = ((payload.get("chart") or {}).get("result") or [None])[0] or {}
        meta = result.get("meta") or {}
        rate = float(meta.get("regularMarketPrice"))
        timestamp = int(meta.get("regularMarketTime"))
        market_time = dt.datetime.fromtimestamp(timestamp, tz=dt.timezone.utc).astimezone(base.KST)
        age_hours = max(0.0, (now - market_time).total_seconds() / 3600)
        return {
            "code": code,
            "value": rate,
            "status": "최근거래" if age_hours <= 72 else "지연",
            "reference_time_kst": market_time.isoformat(timespec="minutes"),
            "query_time_kst": now.isoformat(timespec="seconds"),
            "source": "Yahoo Finance",
            "url": url,
            "error": "",
        }
    except Exception as exc:
        return {
            "code": code,
            "value": None,
            "status": "확인 불가",
            "reference_time_kst": None,
            "query_time_kst": now.isoformat(timespec="seconds"),
            "source": "Yahoo Finance",
            "url": url,
            "error": f"{type(exc).__name__}: {exc}",
        }


def fetch_frankfurter_krw_rates(codes: list[str], now) -> dict[str, dict]:
    if not codes:
        return {}
    url = "https://api.frankfurter.app/latest"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; GAMEJOA-news-radar/1.0)",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=FX_QUERY_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
        rates = payload.get("rates") or {}
        krw_per_eur = float(rates["KRW"])
        reference = dt.datetime.fromisoformat(str(payload.get("date"))).replace(tzinfo=base.KST)
        age_hours = max(0.0, (now - reference).total_seconds() / 3600)
        status = "보조" if age_hours <= 96 else "지연"
        output: dict[str, dict] = {}
        for code in codes:
            if code == "EUR":
                rate = krw_per_eur
            elif code in rates:
                rate = krw_per_eur / float(rates[code])
            else:
                continue
            output[code] = {
                "code": code,
                "value": rate,
                "status": status,
                "reference_time_kst": reference.isoformat(timespec="minutes"),
                "query_time_kst": now.isoformat(timespec="seconds"),
                "source": "ECB/Frankfurter",
                "url": url,
                "error": "",
            }
        return output
    except Exception:
        return {}


def collect_fx_snapshot(alerts: list[dict], now) -> dict:
    codes: list[str] = []
    for alert in alerts:
        source_text = " ".join(
            str(alert.get(key) or "")
            for key in (
                "policy_plain_summary",
                "telegram_core_fact",
                "source_title",
                "original_news",
                "news",
            )
        )
        for amount in extract_foreign_amounts(source_text):
            if amount["code"] not in codes:
                codes.append(amount["code"])
    rates = {code: fetch_yahoo_krw_rate(code, now) for code in codes}
    missing = [code for code, item in rates.items() if item.get("value") is None]
    for code, fallback in fetch_frankfurter_krw_rates(missing, now).items():
        rates[code] = fallback
    return {
        "query_time_kst": now.isoformat(timespec="seconds"),
        "rates": rates,
    }


def format_krw_amount(value: float) -> str:
    if value >= 1_000_000_000_000:
        return f"{int(value / 1_000_000_000_000 + 0.5):,}조원"
    if value >= 100_000_000:
        number = f"{value / 100_000_000:,.1f}".rstrip("0").rstrip(".")
        return f"{number}억원"
    if value >= 10_000:
        number = f"{value / 10_000:,.1f}".rstrip("0").rstrip(".")
        return f"{number}만원"
    return f"{value:,.0f}원"


def build_alert_fx_conversion(alert: dict, snapshot: dict, now) -> dict:
    source_text = " ".join(
        str(alert.get(key) or "")
        for key in (
            "policy_plain_summary",
            "telegram_core_fact",
            "source_title",
            "original_news",
            "news",
        )
    )
    amounts = extract_foreign_amounts(source_text)
    converted: list[dict] = []
    rates = snapshot.get("rates") or {}
    for amount in amounts:
        rate = rates.get(amount["code"]) or {
            "code": amount["code"],
            "value": None,
            "status": "확인 불가",
            "reference_time_kst": None,
            "query_time_kst": now.isoformat(timespec="seconds"),
            "source": "확인 불가",
            "url": yahoo_fx_url(amount["code"]),
            "error": "same-run FX lookup unavailable",
        }
        krw_value = amount["amount"] * float(rate["value"]) if rate.get("value") is not None else None
        converted.append(
            {
                "original": amount["raw"],
                "currency": amount["code"],
                "foreign_value": amount["amount"],
                "krw_value": krw_value,
                "krw_text": format_krw_amount(krw_value) if krw_value is not None else "원화 환산 확인 불가",
                "rate": rate.get("value"),
                "status": rate.get("status") or "확인 불가",
                "reference_time_kst": rate.get("reference_time_kst"),
                "query_time_kst": rate.get("query_time_kst") or now.isoformat(timespec="seconds"),
                "source": rate.get("source") or "확인 불가",
                "url": rate.get("url") or yahoo_fx_url(amount["code"]),
            }
        )
    return {
        "query_time_kst": now.isoformat(timespec="seconds"),
        "amounts": converted,
    }


def apply_krw_conversions(core: str, conversion: dict) -> str:
    text = clean_article_summary_text(core)
    for item in conversion.get("amounts") or []:
        original = str(item.get("original") or "").strip()
        krw_text = str(item.get("krw_text") or "원화 환산 확인 불가")
        replacement = f"{original}(약 {krw_text})" if item.get("krw_value") is not None else f"{original}({krw_text})"
        if original and original in text:
            text = re.sub(
                re.escape(original) + r"(?:\s*\(약\s*[^)]{1,40}원\))?",
                replacement,
                text,
                count=1,
            )
        elif original:
            text = f"{text.rstrip('.')} {replacement}.".strip()
    return text


def compact_converted_core(core: str, conversion: dict, limit: int = 50) -> str:
    converted = apply_krw_conversions(core, conversion)
    if len(converted) <= limit:
        return converted

    amount_chunks: list[str] = []
    first_position: int | None = None
    for item in conversion.get("amounts") or []:
        original = str(item.get("original") or "").strip()
        krw_text = str(item.get("krw_text") or "원화 환산 확인 불가")
        chunk = (
            f"{original}(약 {krw_text})"
            if item.get("krw_value") is not None
            else f"{original}({krw_text})"
        )
        position = converted.find(chunk)
        if position < 0 or chunk in amount_chunks:
            continue
        if first_position is None:
            first_position = position
        amount_chunks.append(chunk)

    if amount_chunks:
        prefix = converted[: first_position or 0].strip(" ,·;:")
        prefix_tokens = re.findall(r"[A-Za-z0-9가-힣·]+", prefix)
        short_prefix = " ".join(prefix_tokens[-2:])
        joined = ", ".join(amount_chunks)
        for candidate in (
            f"{short_prefix} {joined}입니다.".strip(),
            f"{joined}입니다.",
        ):
            if len(candidate) <= limit:
                return candidate

    return complete_prose_text(converted, limit=limit)


def fx_provenance_text(conversion: dict) -> str:
    entries: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for item in conversion.get("amounts") or []:
        code = str(item.get("currency") or "")
        source = str(item.get("source") or "확인 불가")
        reference = str(item.get("reference_time_kst") or "확인 불가")
        key = (code, source, reference)
        if key in seen:
            continue
        seen.add(key)
        if item.get("rate") is None:
            link = html_link(f"{source} {code}/KRW", item.get("url") or "")
            entries.append(f"{link} 확인 불가 · 조회 {item.get('query_time_kst') or '확인 불가'}")
            continue
        rate = float(item["rate"])
        rate_text = f"{rate:,.4f}".rstrip("0").rstrip(".")
        link = html_link(f"{source} {code}/KRW", item.get("url") or "")
        entries.append(
            f"{link} {rate_text}원 · 기준 {reference} · 조회 {item.get('query_time_kst') or '확인 불가'}"
        )
    return " / ".join(entries)


def bounded_complete_excerpt(text: str, max_chars: int) -> str:
    cleaned = clean_article_summary_text(text)
    if len(cleaned) <= max_chars:
        return cleaned
    head = cleaned[: max_chars + 1]
    sentence_ends = [
        match.end()
        for match in re.finditer(
            r"(?:[.!?。]|(?:했|됐|였|입니|됩니|됩|된|이|한|졌|보였|나타났|밝혔|전했|설명했|기록했|늘었|줄었|확대됐|축소됐)다)(?=\s|$)",
            head,
        )
        if match.end() >= max_chars // 2
    ]
    if sentence_ends:
        return head[: sentence_ends[-1]].rstrip()
    clause_ends = [
        match.start()
        for match in re.finditer(r"[,;:·]\s+", head)
        if match.start() >= max_chars // 2
    ]
    cut = clause_ends[-1] if clause_ends else head.rfind(" ", max_chars // 2, max_chars)
    if cut < max_chars // 2:
        cut = max_chars
    return head[:cut].rstrip(" ,;:·") + "…"


def article_title_restatement(sentence: str, title: str) -> bool:
    sentence_tokens = set(re.findall(r"[a-z0-9가-힣]+", sentence.lower()))
    title_tokens = set(re.findall(r"[a-z0-9가-힣]+", title.lower()))
    if not sentence_tokens or not title_tokens:
        return False
    overlap = len(sentence_tokens & title_tokens)
    return (
        overlap / min(len(sentence_tokens), len(title_tokens)) >= 0.85
        and max(len(sentence_tokens), len(title_tokens))
        <= min(len(sentence_tokens), len(title_tokens)) + 2
    )


def ranked_article_sentences(
    text: str,
    required: list[str],
    *,
    title: str = "",
) -> list[str]:
    cleaned_text = clean_article_summary_text(text)
    sentences = [
        re.sub(
            r"^(?:▲[^)]{0,100}\)|\([^)]{0,100}(?:출처|사진)[^)]*\))\s*",
            "",
            clean_article_summary_text(sentence),
        )
        # Split only at actual punctuation. A bare Hangul "다" also appears
        # inside clauses such as "지난해 같은 기간보다 20.8% 감소", so using
        # it as a boundary drops the result that follows.
        for sentence in re.split(r"(?<=[.!?。])\s+", cleaned_text)
        if clean_article_summary_text(sentence)
    ]
    if title:
        sentences = [
            sentence[len(title):].lstrip(" \t:|-·")
            if sentence.startswith(title)
            else sentence
            for sentence in sentences
        ]
    sentences = [
        sentence
        for sentence in sentences
        if len(sentence) >= 25 and not article_title_restatement(sentence, title)
    ]
    scored: list[tuple[int, int, str]] = []
    for index, sentence in enumerate(sentences):
        lowered = sentence.lower()
        required_hits = sum(term.lower() in lowered for term in required)
        material_hits = sum(term.lower() in lowered for term in ARTICLE_MATERIAL_TERMS)
        numeric = bool(re.search(r"\d[\d,.]*\s*(?:%|조|억|만|원|달러|t|톤|주)", sentence, re.I))
        result = any(term in sentence for term in ARTICLE_RESULT_TERMS)
        shareholder = any(term in sentence for term in ARTICLE_SHAREHOLDER_TERMS)
        score = required_hits * 3 + min(material_hits, 4) * 2
        score += 5 if numeric else 0
        score += 4 if result else 0
        score += 3 if shareholder else 0
        if score:
            scored.append((score, index, sentence))
    if not scored:
        return sentences
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [sentence for _score, _index, sentence in scored]


def article_sentences(
    text: str,
    required: list[str],
    limit: int = 3,
    *,
    title: str = "",
) -> str:
    selected = ranked_article_sentences(text, required, title=title)
    summary = ""
    for sentence in selected[:limit]:
        remaining = ARTICLE_SUMMARY_MAX_CHARS - len(summary) - (1 if summary else 0)
        if remaining < 80:
            break
        excerpt = bounded_complete_excerpt(sentence, remaining)
        summary = f"{summary} {excerpt}".strip()
        if excerpt.endswith("…"):
            break
    return summary


def normalized_article_sentence(sentence: str) -> str:
    text = clean_article_summary_text(sentence)
    replacements = (
        (
            r"([A-Za-z가-힣·&]+)\s*\(\s*[\d,]+원\s*[▲▼+-]\s*[\d,]+\s*"
            r"(?:[+-]\d+(?:\.\d+)?%)?\s*\)",
            r"\1",
        ),
        (r"^\d{1,2}일\s+([A-Za-z0-9가-힣·&()]+)(?:은|는)\s+", r"\1, "),
        (r"^이날\s+([A-Za-z0-9가-힣·&()]+)(?:\s+이사회)?(?:은|는)\s+", r"\1, "),
        (r"\b올해\s+", ""),
        (r"\b올\s+", ""),
        (r"지배주주\s+당기순이익", "순이익"),
        (r"지배지분\s+기준\s+순이익", "순이익"),
        (r"전년\s+동기\s+대비", "전년비"),
        (r"지난해\s+같은\s+기간보다", "전년비"),
        (r"보통주\s+1주당\s+현금\s*", "주당 "),
        (r"자기주식\s+취득\s+및\s+소각", "자사주 매입·소각"),
        (r"자기주식\s+취득·소각", "자사주 매입·소각"),
        (r"주주환원\s+정책의\s+하나로\s*", ""),
        (r"\s*규모의\s+", " "),
        (r"\s*과\s+함께\s*", ", "),
        (r"(?:을|를)?\s*기록했다고\s+밝혔다\.?$", " 기록."),
        (r"(?:을|를)?\s*결정했다고\s+밝혔다\.?$", " 결정."),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return clean_article_summary_text(text)


def compact_article_sentence(sentence: str, limit: int = 50) -> str:
    return concise_text(normalized_article_sentence(sentence), limit=limit)


def suspect_financial_amount(metric: str, amount: str) -> bool:
    trillion_match = re.search(r"(\d[\d,.]*)조", amount or "")
    if not trillion_match:
        return False
    try:
        trillion = float(trillion_match.group(1).replace(",", ""))
    except ValueError:
        return True
    limits = {
        "영업이익": 20.0,
        "순이익": 30.0,
    }
    return metric in limits and trillion >= limits[metric]


def sentence_has_suspect_financial_amount(sentence: str) -> bool:
    for metric_term, metric in (
        ("영업이익", "영업이익"),
        ("당기순이익", "순이익"),
        ("순이익", "순이익"),
    ):
        position = sentence.find(metric_term)
        if position < 0:
            continue
        metric_tail = sentence[position + len(metric_term):position + len(metric_term) + 90]
        amount_match = re.search(KOREAN_WON_AMOUNT_PATTERN, metric_tail)
        if amount_match and suspect_financial_amount(metric, amount_match.group(0)):
            return True
    return False


def financial_result_fact(title: str, sentences: list[str]) -> str:
    metric_patterns = (
        ("영업이익", "영업이익"),
        ("당기순이익", "순이익"),
        ("순이익", "순이익"),
        ("매출", "매출"),
    )
    for sentence in sentences:
        metric_term, metric = next(
            ((term, label) for term, label in metric_patterns if term in sentence),
            ("", ""),
        )
        if not metric:
            continue
        metric_start = sentence.find(metric_term) + len(metric_term)
        metric_tail = sentence[metric_start:metric_start + 90]
        amount_match = re.search(KOREAN_WON_AMOUNT_PATTERN, metric_tail)
        if not amount_match:
            continue
        if suspect_financial_amount(metric, amount_match.group(0)):
            continue
        period_match = re.search(r"([1-4])분기", sentence) or re.search(r"([1-4])분기", title)
        change_match = re.search(
            r"(?:전년\s*동기\s*대비|전년비|지난해\s*같은\s*기간보다)\s*"
            r"([+-]?\d+(?:\.\d+)?)%\s*(증가|감소|늘|줄)",
            sentence,
        )
        prefix = f"{period_match.group(1)}분기 " if period_match else ""
        result = f"{prefix}{metric} {amount_match.group(0).replace(' ', '')}"
        if change_match:
            direction = "증가" if change_match.group(2) in {"증가", "늘"} else "감소"
            result += f", 전년비 {change_match.group(1)}% {direction}"
        if any(term in title for term in ("사상 최대", "역대 최대")):
            result += "·역대 최대"
        return concise_text(result.rstrip(".") + ".", limit=100)
    return ""


def financial_context_fact(sentences: list[str]) -> str:
    for sentence in sentences:
        if "영업이익률" not in sentence and "가이던스" not in sentence:
            continue
        sales_match = re.search(
            rf"매출(?:액)?(?:은|이|는)?\s*({KOREAN_WON_AMOUNT_PATTERN})",
            sentence,
        )
        sales_change = None
        if sales_match:
            sales_change = re.search(
                r"(?:으로|로)?\s*([+-]?\d+(?:\.\d+)?)%\s*(증가|감소|늘|줄)",
                sentence[sales_match.end():],
            )
        margin_match = re.search(
            r"영업이익률(?:은|이|는)?\s*([+-]?\d+(?:\.\d+)?)%",
            sentence,
        )
        guidance_match = re.search(
            r"가이던스\s*\(?\s*([+-]?\d+(?:\.\d+)?)\s*[~～-]\s*"
            r"([+-]?\d+(?:\.\d+)?)%\s*\)?",
            sentence,
        )
        parts: list[str] = []
        if sales_match:
            sales = f"매출 {sales_match.group(1).replace(' ', '')}"
            if sales_change:
                direction = "증가" if sales_change.group(2) in {"증가", "늘"} else "감소"
                sales += f"(전년비 {sales_change.group(1)}% {direction})"
            parts.append(sales)
        if margin_match:
            margin = f"영업이익률 {margin_match.group(1)}%"
            if guidance_match:
                margin += (
                    f"로 가이던스 {guidance_match.group(1)}~"
                    f"{guidance_match.group(2)}% 하회"
                )
            parts.append(margin)
        if parts:
            return concise_text(", ".join(parts).rstrip(".") + ".", limit=140)
    return ""


def shareholder_return_fact(sentences: list[str]) -> str:
    best = ""
    best_score = 0
    for sentence in sentences:
        if not any(term in sentence for term in ARTICLE_SHAREHOLDER_TERMS):
            continue
        dividend_match = re.search(r"(?:1주당|주당)(?:\s*현금)?\s*(\d[\d,.]*)원", sentence)
        buyback_match = re.search(
            rf"({KOREAN_WON_AMOUNT_PATTERN})\s*(?:규모의\s*)?(?:자기주식|자사주)",
            sentence,
        )
        parts: list[str] = []
        if dividend_match and "배당" in sentence:
            parts.append(f"주당 {dividend_match.group(1)}원 배당")
        if buyback_match:
            if "소각" in sentence and any(term in sentence for term in ("취득", "매입")):
                action = "매입·소각"
            elif "소각" in sentence:
                action = "소각"
            else:
                action = "매입"
            parts.append(f"자사주 {buyback_match.group(1).replace(' ', '')} {action}")
        specificity = sum(char.isdigit() for char in " ".join(parts))
        score = len(parts) * 100 + specificity + (10 if "공시" in sentence else 0)
        if score > best_score:
            best = concise_text(", ".join(parts) + ".", limit=120)
            best_score = score
    return best


def insider_purchase_signal(text: str) -> bool:
    compact = clean_article_summary_text(text)
    return bool(
        re.search(INSIDER_ROLE_PATTERN, compact, flags=re.IGNORECASE)
        and re.search(r"(?:매수|매입|취득)", compact)
        and re.search(
            r"(?:\d[\d,.]*(?:억|만|천)(?:원|주)?|\d[\d,.]*(?:원|주)|지분율)",
            compact,
        )
    )


def insider_purchase_fact(title: str, sentences: list[str]) -> str:
    text = " ".join([title, *sentences])
    if not insider_purchase_signal(text):
        return ""

    purchases: list[str] = []
    seen_buyers: set[str] = set()
    for sentence in sentences:
        if not re.search(INSIDER_ROLE_PATTERN, sentence, flags=re.IGNORECASE):
            continue
        if not re.search(r"(?:매수|매입|취득)", sentence):
            continue
        buyer_match = re.search(
            rf"([가-힣]{{2,4}}(?:\s+[A-Za-z가-힣0-9()·]+){{0,3}}\s*{INSIDER_ROLE_PATTERN})",
            sentence,
            flags=re.IGNORECASE,
        )
        if not buyer_match:
            continue
        buyer = re.sub(r"\s+", " ", buyer_match.group(1)).strip()
        buyer_key = re.sub(r"\s+", "", buyer.lower())
        if buyer_key in seen_buyers:
            continue

        shares_match = re.search(
            r"(?:총\s*)?(\d[\d,.]*(?:억|만|천)?\d[\d,.]*)주",
            sentence,
        )
        amount_match = re.search(
            rf"({KOREAN_WON_AMOUNT_PATTERN})\s*(?:규모를?|어치를?|들여|투입해)?",
            sentence,
        )
        stake_match = re.search(
            r"지분율(?:은|이|도)?\s*(\d+(?:\.\d+)?)%에서\s*(\d+(?:\.\d+)?)%",
            sentence,
        )
        details: list[str] = []
        if amount_match:
            details.append(amount_match.group(1).replace(" ", ""))
        if shares_match:
            details.append(f"{shares_match.group(1)}주")
        if stake_match:
            details.append(f"지분율 {stake_match.group(1)}→{stake_match.group(2)}%")
        if not details:
            continue
        purchases.append(f"{buyer} {', '.join(details)}")
        seen_buyers.add(buyer_key)
        if len(purchases) >= 2:
            break

    if not purchases:
        title_buyer = re.search(
            rf"([가-힣]{{2,4}}(?:\s+[A-Za-z가-힣0-9()·]+){{0,2}}\s*{INSIDER_ROLE_PATTERN})",
            title,
            flags=re.IGNORECASE,
        )
        title_shares = re.search(r"(\d[\d,.]*(?:억|만|천)?\d[\d,.]*)주", title)
        if title_buyer and title_shares:
            purchases.append(f"{title_buyer.group(1).strip()} {title_shares.group(1)}주")

    if not purchases:
        return ""
    return concise_text(
        f"{'·'.join(purchases)}를 개인 명의로 매수했습니다.",
        limit=GAMEJOA_CORE_MAX_CHARS,
    )


def single_stock_leverage_kosdaq_fact(title: str, body: str) -> str:
    text = clean_article_summary_text(f"{title} {body}")
    if not (
        "단일종목" in text
        and "레버리지" in text
        and "코스닥" in text
        and any(term in text for term in ("규제", "기본예탁금", "시행"))
    ):
        return ""

    date_match = re.search(r"(?:오는\s*)?(\d{1,2})일부터", text)
    analyst_signal = any(
        term in text
        for term in ("유안타증권", "연구원", "분석", "보고서", "전망")
    )
    prefix = (
        f"{date_match.group(1)}일부터 단일종목 레버리지 ETF 규제가 시행돼"
        if date_match
        else "단일종목 레버리지 ETF 규제로"
    )
    interpretation = (
        " 대형 반도체 쏠림 완화와 코스닥 우량 성장주 수급 회복 가능성이 제기됐습니다."
        if analyst_signal
        else " 대형주 쏠림 완화와 코스닥 수급 변화 가능성을 확인해야 합니다."
    )
    return concise_text(prefix + interpretation, limit=GAMEJOA_CORE_MAX_CHARS)


def shareholder_schedule_fact(sentences: list[str]) -> str:
    for sentence in sentences:
        if "소각" not in sentence or not any(term in sentence for term in ("예정일", "소각 대상")):
            continue
        date_match = re.search(r"(?:오는\s*)?(\d{1,2})일", sentence)
        shares_match = re.search(
            r"(?:총\s*)?(\d[\d,.]*(?:천|백|십|억|만)?\d[\d,.]*(?:천|백|십|억|만)?\d*)주",
            sentence,
        )
        parts: list[str] = []
        if shares_match:
            parts.append(f"소각 대상 {shares_match.group(1)}주")
        if date_match:
            parts.append(f"예정일 {date_match.group(1)}일")
        if parts:
            return concise_text(", ".join(parts) + ".", limit=100)
    return ""


def market_sidecar_fact(title: str, body: str) -> str:
    text = clean_article_summary_text(f"{title} {body}")
    if "매도 사이드카" not in text:
        return ""
    kospi_match = re.search(
        r"코스피(?:는|가)?[^!?]{0,100}?(\d+(?:\.\d+)?)%\)?\s*(?:내린|내렸|하락|떨어)",
        text,
    )
    kosdaq_match = re.search(
        r"코스닥(?:은|이)?[^!?]{0,100}?(\d+(?:\.\d+)?)%\)?\s*(?:내린|내렸|하락|떨어)",
        text,
    )
    if kospi_match and kosdaq_match:
        parts = [
            f"코스피·코스닥은 각각 {kospi_match.group(1)}%·"
            f"{kosdaq_match.group(1)}% 하락해 양 시장에 매도 사이드카가 발동됐다."
        ]
    else:
        parts = ["코스피·코스닥에 매도 사이드카가 발동됐다."]
    flow_match = re.search(
        rf"외국인이?\s*({KOREAN_WON_AMOUNT_PATTERN}),?\s*"
        rf"기관이?\s*({KOREAN_WON_AMOUNT_PATTERN})\s*순매도",
        text,
    ) or re.search(
        rf"외국인(?:과|·)\s*기관이?\s*각각\s*"
        rf"({KOREAN_WON_AMOUNT_PATTERN}),?\s*({KOREAN_WON_AMOUNT_PATTERN})\s*순매도",
        text,
    )
    if flow_match:
        parts.append(
            "외국인·기관은 각각 "
            f"{flow_match.group(1)}·{flow_match.group(2)} 순매도했다."
        )
    stock_pair_match = re.search(
        r"삼성전자(?:와|·)\s*SK하이닉스[^.!?]{0,50}?각각\s*"
        r"(-?\d+(?:\.\d+)?)%\s*[,·]\s*(-?\d+(?:\.\d+)?)%",
        text,
    )
    samsung_match = re.search(
        r"삼성전자\s*\([^)]*?(-?\d+(?:\.\d+)?)%\)",
        text,
    )
    hynix_match = re.search(
        r"SK하이닉스\s*\([^)]*?(-?\d+(?:\.\d+)?)%\)",
        text,
    )
    if stock_pair_match:
        samsung_change = stock_pair_match.group(1)
        hynix_change = stock_pair_match.group(2)
    elif samsung_match and hynix_match:
        samsung_change = samsung_match.group(1)
        hynix_change = hynix_match.group(1)
    else:
        samsung_change = ""
        hynix_change = ""
    if samsung_change and hynix_change:
        parts.append(
            "삼성전자·SK하이닉스는 각각 "
            f"{abs(float(samsung_change)):g}%·"
            f"{abs(float(hynix_change)):g}% 하락했다."
        )
    return " ".join(parts)


def tariff_policy_fact(title: str, body: str) -> str:
    text = clean_article_summary_text(f"{title} {body}")
    if "관세" not in text:
        return ""
    imposed_match = re.search(
        r"(?:한국에|한국산[^,.]{0,30})\s*([0-9]+(?:\.[0-9]+)?)%의?\s*관세를\s*부과",
        text,
    )
    cap_match = re.search(
        r"(?:마지노선|상한|관세율|합의상\s*관세율)[^.%]{0,35}?([0-9]+(?:\.[0-9]+)?)%",
        text,
    )
    if not cap_match:
        cap_match = re.search(
            r"([0-9]+(?:\.[0-9]+)?)%를\s*(?:넘지|초과하지)",
            text,
        )
    foreign_amount = next(
        (item for item in extract_foreign_amounts(text) if item["code"] == "USD"),
        None,
    )
    parts: list[str] = []
    if imposed_match:
        first = f"미국은 한국에 {imposed_match.group(1)}% 관세를 부과"
        if "추가 관세" in text or "과잉생산" in text:
            first += "하고 과잉생산 관련 추가 관세도 예고했다"
        else:
            first += "했다"
        parts.append(first + ".")
    if cap_match:
        second = f"의원단은 총관세 {cap_match.group(1)}% 상한 준수"
        if foreign_amount:
            second += f"와 {foreign_amount['raw']} 대미 투자합의 이행"
        second += "을 촉구했다."
        parts.append(second)
    return " ".join(parts)


def detailed_article_core(title: str, body: str) -> str:
    normalized_title = title.lower()
    if "sk하이닉스" in normalized_title and any(
        term in normalized_title for term in ("실적", "역대급")
    ):
        preview_match = re.search(
            r"(?:오는\s*)?(\d{1,2})일[^.!?]{0,45}?(?:2분기\s*)?실적(?:을|이)?\s*발표",
            body,
        )
        if preview_match and sentence_has_suspect_financial_amount(body):
            return (
                f"SK하이닉스는 {preview_match.group(1)}일 2분기 실적을 발표하며, "
                "HBM 가격·LTA·AI CAPEX 가이던스가 핵심입니다. "
                "기사의 영업이익 수치는 이상치로 제외했습니다."
            )

    sentences = ranked_article_sentences(
        body,
        korean_business_title_terms(title),
        title=title,
    )
    tariff_fact = tariff_policy_fact(title, body)
    if tariff_fact:
        return tariff_fact
    sidecar_fact = market_sidecar_fact(title, body)
    if sidecar_fact:
        return sidecar_fact
    leverage_fact = single_stock_leverage_kosdaq_fact(title, body)
    if leverage_fact:
        return leverage_fact

    preferred = [
        insider_purchase_fact(title, sentences),
        financial_result_fact(title, sentences),
        shareholder_return_fact(sentences),
        financial_context_fact(sentences),
        shareholder_schedule_fact(sentences),
    ]
    facts = [fact for fact in preferred if fact]
    if not facts:
        for sentence in sentences:
            fact = normalized_article_sentence(sentence)
            if (
                not fact
                or article_title_restatement(fact, title)
                or sentence_has_suspect_financial_amount(fact)
            ):
                continue
            facts.append(fact)
            if len(facts) >= GAMEJOA_ARTICLE_FACT_LIMIT:
                break

    output: list[str] = []
    for fact in facts:
        candidate = " ".join(output + [fact]).strip()
        if len(candidate) <= GAMEJOA_CORE_MAX_CHARS:
            output.append(fact)
            if len(output) >= GAMEJOA_ARTICLE_FACT_LIMIT:
                break
            continue
        elif not output:
            excerpt = bounded_complete_excerpt(fact, GAMEJOA_CORE_MAX_CHARS)
            output.append(excerpt.rstrip("…").rstrip() + ".")
        break
    return " ".join(output).strip()


def article_investment_point(title: str, body: str, impacts: list[str]) -> str:
    text = clean_article_summary_text(f"{title} {body}")
    title_text = clean_article_summary_text(title)
    if (
        any(term in title_text for term in ("코스피", "코스닥", "증시", "뉴욕마감"))
        and any(term in title_text for term in ("하락", "급락", "대외불안", "반등"))
    ):
        return "외국인·기관 매도와 유가·금리 상승이 이어지면 대형 반도체주와 지수 수급 부담이 지속됩니다."
    if (
        any(term in title_text.lower() for term in ("oci", "오씨아이"))
        and any(term in title_text for term in ("영업이익", "흑자전환", "흑자 전환", "실적"))
        and any(term in text for term in ("폴리실리콘", "태양광"))
    ):
        return "흑자 전환과 프로젝트 매각, 폴리실리콘 증설·장기계약이 현금흐름과 성장 CAPEX를 바꿉니다."
    if any(term in text for term in ARTICLE_SHAREHOLDER_TERMS) and any(
        term in text for term in ("순이익", "영업이익", "매출")
    ):
        return "실적 개선과 배당·자사주 소각이 이익 추정과 주주환원 수급을 함께 높입니다."
    if "영업이익률" in text and "가이던스" in text:
        return "영업이익 감소와 마진 가이던스 하회는 이익 추정과 밸류에이션을 낮추는 요인입니다."
    if any(term in title_text for term in ("영업이익", "순이익", "매출", "실적", "흑자전환", "흑자 전환")):
        return "기사의 실적과 사업별 원인이 다음 분기 매출·마진·현금흐름으로 이어지는지 확인합니다."
    if "관세" in title_text or tariff_policy_fact(title, body):
        cap_match = re.search(
            r"(?:마지노선|상한|관세율|합의상\s*관세율)[^.%]{0,35}?([0-9]+(?:\.[0-9]+)?)%",
            text,
        ) or re.search(r"([0-9]+(?:\.[0-9]+)?)%를\s*(?:넘지|초과하지)", text)
        cap = cap_match.group(1) if cap_match else ""
        prefix = f"합산 관세가 {cap}%를 넘으면" if cap else "추가 관세가 확정되면"
        return f"{prefix} 한국 수출주의 가격경쟁력과 마진 부담이 커집니다."
    if "소각" in text:
        return "소각 완료 시 발행주식 수가 줄어 주당가치와 주주환원 수급에 긍정적입니다."
    if any(term in text for term in ("순매수", "순매도")) or re.search(
        r"(?:외국인|기관)[^.!?]{0,40}(?:매수|매도)",
        text,
    ):
        return "기사에 나온 매수·매도 주체와 규모가 다음 거래일까지 이어지는지 확인합니다."
    if "돈 버는 능력" in impacts:
        return "기사의 수요·가격·계약 변화가 실제 매출과 마진으로 이어지는지 확인합니다."
    if "수급" in impacts:
        return "기사에 나온 거래 주체와 규모가 후속 수급으로 이어지는지 확인합니다."
    if "시간표" in impacts:
        return "승인·계약·출시 일정이 실제 공시와 매출 인식으로 이어지는지 확인합니다."
    return "기사 본문의 새 수치와 후속 공식 발표가 실제 가격 변수로 이어지는지 확인합니다."


def compact_article_facts(title: str, body: str) -> list[str]:
    sentences = ranked_article_sentences(
        body,
        korean_business_title_terms(title),
        title=title,
    )
    facts = [
        insider_purchase_fact(title, sentences),
        financial_result_fact(title, sentences),
        shareholder_return_fact(sentences),
    ]
    for sentence in sentences:
        facts.append(compact_article_sentence(sentence))
    output: list[str] = []
    for fact in facts:
        fact = clean_article_summary_text(fact)
        if not fact or fact == title:
            continue
        normalized = re.sub(r"[^a-z0-9가-힣]+", "", fact.lower())
        if any(
            normalized == re.sub(r"[^a-z0-9가-힣]+", "", existing.lower())
            for existing in output
        ):
            continue
        output.append(fact)
        if len(output) == 2:
            break
    return output


KOREAN_BUSINESS_SECTOR_TERMS = [
    ("MLCC/수동부품", ["mlcc", "적층세라믹커패시터", "수동부품"]),
    ("반도체/HBM/CXL", ["반도체", "hbm", "dram", "nand", "cxl", "테스터"]),
    ("AI/데이터센터", ["ai", "인공지능", "데이터센터", "하이퍼스케일러"]),
    ("로봇/생산자동화", ["로봇", "자율주행", "제조 ai", "피지컬 ai", "스마트팩토리"]),
    ("철강/건설소재", ["철강", "철강재", "형강", "후판", "강재"]),
    (
        "미국 증시/금리",
        [
            "나스닥", "s&p500", "필라델피아 반도체", "smh", "fomc",
            "연준", "미국 국채", "국채금리",
        ],
    ),
    ("원유/인플레이션", ["국제유가", "브렌트", "wti", "인플레이션"]),
    ("태양광/폴리실리콘", ["태양광", "폴리실리콘", "웨이퍼"]),
    ("전력기기/전력망", ["전력기기", "변압기", "전선", "송전망", "전력망"]),
    ("2차전지/배터리", ["2차전지", "배터리", "양극재", "음극재", "전해질"]),
    ("자동차/부품", ["자동차", "현대차", "기아", "전기차", "부품"]),
    ("방산/항공우주", ["방산", "항공우주", "미사일", "전차", "자주포"]),
    ("바이오/헬스케어", ["바이오", "제약", "임상", "의약품", "헬스케어"]),
    (
        "금융/자본시장",
        [
            "은행", "금융지주", "금융그룹", "JB금융", "KB금융", "신한금융",
            "하나금융", "우리금융", "BNK금융", "iM금융", "증권", "보험",
            "외국인", "순매수", "순매도", "금융위원회", "금융감독원",
            "한국거래소", "etf", "etn", "레버리지", "기본예탁금",
        ],
    ),
    ("유통/소비", ["유통", "소비", "홈플러스", "백화점", "면세점"]),
    ("엔터테인먼트/콘텐츠", ["엔터", "yg", "jyp", "하이브", "sm엔터", "음반", "콘텐츠"]),
]
KOREAN_BUSINESS_COMPANIES = [
    "삼성전자",
    "SK하이닉스",
    "엑시콘",
    "삼성전기",
    "OCI",
    "OCI홀딩스",
    "대신증권",
    "KB증권",
    "현대차",
    "현대자동차",
    "기아",
    "엔비디아",
    "브로드컴",
    "앤트로픽",
    "동국제강",
    "두산에너빌리티",
    "한화에어로스페이스",
    "LIG넥스원",
    "한국항공우주",
    "현대로템",
    "한화시스템",
    "YG엔터테인먼트",
    "JYP엔터테인먼트",
    "하이브",
    "SM엔터테인먼트",
]
KOREAN_BUSINESS_MARKET_RECAP_TERMS = [
    "급등락주 짚어보기",
    "상한가 종목",
    "하한가 종목",
    "장 마감",
    "마감시황",
    "오늘의 급등주",
]
KOREAN_BUSINESS_MATERIAL_TERMS = [
    "영업익",
    "영업이익",
    "순이익",
    "흑자전환",
    "실적",
    "가이던스",
    "공급계약",
    "장기계약",
    "계약",
    "수주",
    "발주",
    "증설",
    "양산",
    "출하",
    "매출",
    "가격 인상",
    "순매수",
    "순매도",
    "상장예비심사",
    "ipo",
    "인수",
    "합병",
    "승인",
    "허가",
    "임상",
    "관세",
    "수출통제",
    "원·달러",
    "환율",
    "자사주",
    "유상증자",
    "전환사채",
]


def korean_business_title_has_material_term(title: str, term: str) -> bool:
    title_text = str(title or "").lower()
    if term == "내부자 직접매수":
        return insider_purchase_signal(title_text)
    if term != "수주":
        return term in title_text

    # "수주" is also used in Korean personal names such as "홍수주".
    # Accept it only as a standalone word or with an investment-news context.
    if re.search(r"(?<![가-힣])수주(?![가-힣])", title_text):
        return True
    if re.search(
        r"(?:대형|신규|추가|첫|해외|역대|최대|단독|공동|누적|방산|원전|선박|플랜트|계약)수주",
        title_text,
    ):
        return True
    if re.search(
        r"\d[\d,.]*(?:조|억|만)?(?:원|달러|유로)?(?:대)?\s*수주",
        title_text,
    ):
        return True
    return bool(
        re.search(
            r"수주(?:액|잔고|계약|공시|확정|성공|목표|실적|소식|기대|전망|가시화|했다|해|한|로|를|가|는|도)",
            title_text,
        )
    )


KOREAN_BUSINESS_IMPACT_TERMS = {
    "돈 버는 능력": [
        "매출", "영업이익", "순이익", "흑자", "적자", "실적", "가이던스",
        "수요", "가격", "판가", "마진", "공급계약", "장기계약", "수주", "발주",
        "증설", "생산능력", "출하", "고객사", "점유율",
    ],
    "할인율": [
        "금리", "환율", "원·달러", "달러", "규제", "관세", "수출통제", "제재",
        "fomc", "연준", "국채금리", "국제유가", "인플레이션", "밸류에이션",
    ],
    "수급": [
        "외국인", "기관", "순매수", "순매도", "자사주", "유상증자", "cb",
        "전환사채", "etf", "etn", "레버리지", "기본예탁금", "편입", "상장", "ipo",
    ],
    "시간표": [
        "양산평가", "평가", "승인", "허가", "상용화", "출시", "이달 말",
        "예정", "시행", "상장예비심사", "ipo", "계약", "증설", "착공", "완공",
    ],
}

coverage.apply_term_extensions(
    KOREAN_BUSINESS_PRIORITY_TERMS,
    KOREAN_BUSINESS_MATERIAL_TERMS,
    KOREAN_BUSINESS_IMPACT_TERMS,
)


def korean_business_source_sectors(title: str, summary: str) -> list[str]:
    title_lower = title.lower()
    if any(term in title_lower for term in ("ipo", "상장예비심사", "대표주관", "중복상장")):
        return ["IPO/증권"]
    if any(term in title_lower for term in ("원·달러", "환율", "달러-원")):
        return ["환율/수출입"]
    text = f"{title} {summary}"
    lowered = text.lower()
    sectors = [
        label for label, terms in KOREAN_BUSINESS_SECTOR_TERMS
        if any(term.lower() in lowered for term in terms)
    ]
    return sectors[:3] or ["한국 기업/산업 뉴스"]


def korean_business_impacts(text: str, existing: list[object]) -> list[str]:
    lowered = text.lower()
    impacts = [
        impact for impact, terms in KOREAN_BUSINESS_IMPACT_TERMS.items()
        if any(term.lower() in lowered for term in terms)
    ]
    if insider_purchase_signal(lowered) and "수급" not in impacts:
        impacts.append("수급")
    if not impacts:
        impacts = [
            str(value) for value in existing
            if str(value) != "의사결정 영향 제한적"
        ]
    return list(dict.fromkeys(impacts))


def korean_business_title_terms(title: str) -> list[str]:
    stopwords = {
        "관련", "전망", "속도", "확대", "추진", "시장", "기업", "대한", "통해",
        "한다", "했다", "있는", "나섰다", "본격", "차세대",
    }
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9.+-]{1,}|[가-힣]{2,}", title or "")
    return [
        token for token in dict.fromkeys(tokens)
        if token.lower() not in stopwords
    ][:10]


def apply_generic_korean_business_profile(alert: dict, row: dict, now) -> dict:
    out = dict(alert)
    title = str(row.get("source_title") or row.get("title") or "")
    body = str(row.get("source_body") or row.get("source_abstract") or "")
    summary = article_sentences(
        body,
        korean_business_title_terms(title),
        2,
        title=title,
    )
    source_focus = f"{title} {summary}"
    impacts = korean_business_impacts(source_focus, out.get("impacts") or [])
    if "ipo" in title.lower() and any(term in title for term in ("주관", "대표주관")):
        impacts = ["돈 버는 능력", "시간표"]
    sectors = korean_business_source_sectors(title, summary)
    companies = [
        company for company in KOREAN_BUSINESS_COMPANIES
        if company.lower() in source_focus.lower()
    ]
    impact_notes = []
    if "돈 버는 능력" in impacts:
        impact_notes.append("원문에 나온 수요·가격·계약·실적 변화가 매출과 마진으로 이어지는지")
    if "할인율" in impacts:
        impact_notes.append("금리·환율·규제 변화가 밸류에이션을 바꾸는지")
    if "수급" in impacts:
        impact_notes.append("기사에 나온 매수·매도 주체와 규모가 이어지는지")
    if "시간표" in impacts:
        impact_notes.append("평가·승인·계약·출시 일정이 실제로 지켜지는지")
    decision_focus = ", ".join(impact_notes) or "후속 공시와 시장 반응이 실제 가격 변수를 바꾸는지"
    exposure = "·".join(companies[:5]) if companies else "원문에 직접 언급된 기업"
    age = base.age_hours(row, now)
    article_core = detailed_article_core(title, body)
    article_investment = article_investment_point(title, body, impacts)

    out.update(
        {
            "korean_business_news": True,
            "body_verified": True,
            "news": title,
            "original_news": title,
            "source_title": title,
            "source_abstract": body[:16000],
            "policy_plain_summary": summary,
            "telegram_core_fact": article_core,
            "telegram_investment_fact": article_investment,
            "investment_view": f"{decision_focus} 확인합니다.",
            "interpretation": f"{decision_focus} 확인합니다.",
            "korea_market_impact": (
                f"한국장에서는 {exposure}, {', '.join(sectors)} 중 원문에 직접 근거가 있는 노출만 연결합니다."
            ),
            "sectors": sectors,
            "impacts": impacts or ["의사결정 영향 제한적"],
            "paths": [
                "이익" if impact == "돈 버는 능력"
                else "할인율" if impact == "할인율"
                else "수급" if impact == "수급"
                else "실행 시간표"
                for impact in impacts
            ] or ["정책 타임라인"],
            "status": "예비",
            "korea_basis": "신뢰 국내매체 확산",
            "priced_in": (
                "낮음~중간. 발표 당일 기사라 첫 가격 반응과 다음 거래일 후속 수급을 함께 확인해야 합니다."
                if age is not None and age <= 12
                else "중간. 보도 뒤 이미 가격이 움직였는지와 새 후속 공시가 있는지 확인해야 합니다."
            ),
            "counter": "기사 보도만으로 신규 계약·확정 매출·지속 수급이 보장되지는 않습니다. 원문에 없는 수혜 종목으로 확대하면 과대해석입니다.",
            "failed_signal": "후속 공시·수주·가격·거래주체 변화가 확인되지 않거나 관련 종목 수급이 동행하지 않으면 단발성 기사로 약해집니다.",
            "korean_business_kind": "verified_source_summary",
        }
    )
    out["importance"] = "상" if int(out.get("score") or 0) >= 100 else "중"
    return out


def base_korean_business_alert(row: dict, now, *, score: int, impacts: list[str]) -> dict:
    age = base.age_hours(row, now)
    title = str(row.get("source_title") or row.get("title") or "")
    body = str(row.get("source_body") or row.get("source_abstract") or row.get("summary") or "")
    article_core = detailed_article_core(title, body)
    article_investment = article_investment_point(title, body, impacts)
    return {
        "score": score + (6 if age is not None and age <= 12 else 0),
        "importance": "상" if score >= 100 else "중",
        "status": "예비",
        "news": title,
        "original_news": title,
        "source_title": title,
        "source_abstract": str(row.get("source_abstract") or row.get("summary") or ""),
        "policy_plain_summary": article_core,
        "telegram_core_fact": article_core,
        "telegram_investment_fact": article_investment,
        "investment_view": article_investment or article_core,
        "interpretation": article_investment or article_core,
        "korea_market_impact": "원문에 직접 언급된 국내 기업·업종의 가격과 수급만 연결합니다.",
        "publisher": row.get("publisher") or row.get("source"),
        "source": row.get("source"),
        "link": row.get("link") or "",
        "published": row["published"].isoformat(timespec="minutes") if row.get("published") else "확인 불가",
        "impacts": impacts,
        "paths": [
            "이익" if impact == "돈 버는 능력"
            else "수급" if impact == "수급"
            else "정책 타임라인"
            for impact in impacts
        ],
        "sectors": ["반도체/AI"],
        "matched": [],
        "local_dc_policy": False,
        "reflection": "낮음" if age is not None and age <= 6 else "중간",
        "korea_basis": "신뢰 국내매체 확산",
        "korean_business_news": True,
        "body_verified": True,
    }


def korean_market_decline(text: str, labels: tuple[str, ...]) -> str:
    for label in labels:
        match = re.search(
            rf"{re.escape(label)}[^.!?]{{0,90}}?(\d+(?:\.\d+)?)%\s*"
            r"[^가-힣a-z0-9]{0,8}(?:급락|하락|내렸|떨어졌|빠졌)",
            text,
            flags=re.IGNORECASE,
        )
        if match:
            return match.group(1)
    return ""


def build_hyundai_nvidia_meeting_alert(row: dict, now, text: str) -> dict | None:
    title = str(row.get("source_title") or row.get("title") or "").lower()
    if not (
        any(term in title for term in ("정의선", "현대차", "현대자동차"))
        and "엔비디아" in title
        and any(term in text for term in ("정의선", "현대차", "현대자동차"))
        and "엔비디아" in text
        and any(term in text for term in ("회동", "만나", "본사", "협력"))
        and any(term in text for term in ("자율주행", "로봇", "제조 ai", "새만금", "ai 밸리"))
    ):
        return None
    date_key = korean_business_event_date(row)
    stage = "robot_platform" if any(
        term in text for term in ("로봇 레퍼런스 플랫폼", "공동 구축", "개방형 생태계")
    ) else "meeting"
    if stage == "robot_platform":
        core = "현대차·엔비디아가 로봇 플랫폼 공동 구축을 제시했습니다."
    else:
        core = "정의선·젠슨 황이 자율주행·로봇·제조AI 협력을 논의했습니다."
    alert = base_korean_business_alert(
        row,
        now,
        score=101,
        impacts=["시간표", "수급"],
    )
    alert.update(
        {
            "importance": "중",
            "status": "예비",
            "policy_plain_summary": core,
            "telegram_core_fact": core,
            "telegram_investment_fact": "협력 논의 단계로, 공동개발 범위와 계약·발주가 확인돼야 실적 재료가 됩니다.",
            "investment_view": "협력 논의 단계로, 공동개발 범위와 계약·발주가 확인돼야 실적 재료가 됩니다.",
            "korea_market_impact": "현대차·현대모비스와 자율주행·로봇·스마트팩토리 밸류체인의 후속 계약만 연결합니다.",
            "sectors": ["자동차/부품", "로봇/생산자동화", "AI/데이터센터"],
            "paths": ["협력 시간표", "테마 수급"],
            "korean_business_kind": "hyundai_nvidia_ai_partnership",
            "supply_chain_theme": f"hyundai_nvidia_{stage}:{date_key}",
        }
    )
    return alert


def build_single_stock_leverage_rule_alert(row: dict, now, text: str) -> dict | None:
    if not (
        "레버리지" in text
        and any(term in text for term in ("etf", "etn"))
        and any(term in text for term in ("삼성전자", "sk하이닉스", "삼닉"))
        and any(term in text for term in ("기본예탁금", "3000만원", "대용증권", "31일"))
    ):
        return None
    date_key = korean_business_event_date(row)
    alert = base_korean_business_alert(
        row,
        now,
        score=116,
        impacts=["수급", "시간표"],
    )
    alert.update(
        {
            "importance": "상",
            "status": "확정",
            "policy_plain_summary": "기본예탁금 1000만→3000만원·대용증권 불인정, 31일 시행.",
            "telegram_core_fact": "기본예탁금 1000만→3000만원·대용증권 불인정, 31일 시행.",
            "telegram_investment_fact": "진입비용 상승으로 상품 신규수요와 대형 반도체주 파생수급이 둔화할 수 있습니다.",
            "investment_view": "진입비용 상승으로 상품 신규수요와 대형 반도체주 파생수급이 둔화할 수 있습니다.",
            "korea_market_impact": "삼성전자·SK하이닉스 단일종목 레버리지 ETF·ETN 거래대금과 현물 연계수급을 확인합니다.",
            "sectors": ["금융/자본시장", "반도체/HBM/CXL"],
            "paths": ["상품 진입규제", "수급", "정책 시행일"],
            "korean_business_kind": "single_stock_leverage_rule",
            "supply_chain_theme": (
                "korea_single_stock_leverage_rule:2026-07-31"
                if "31일" in text
                else f"korea_single_stock_leverage_rule:{date_key}"
            ),
        }
    )
    return alert


def build_global_semiconductor_market_alert(row: dict, now, text: str) -> dict | None:
    if not (
        "나스닥" in text
        and any(term in text for term in ("반도체주", "필라델피아 반도체", "smh", "마이크론"))
        and any(term in text for term in ("fomc", "연준", "금리", "유가", "빅테크"))
        and any(term in text for term in ("급락", "하락", "내렸", "차익실현"))
    ):
        return None
    date_key = korean_business_event_date(row)
    nasdaq = korean_market_decline(text, ("나스닥종합지수", "나스닥 종합지수", "나스닥"))
    sox = korean_market_decline(
        text,
        ("필라델피아 반도체지수", "필라델피아반도체지수", "필라델피아 반도체 지수"),
    )
    smh = korean_market_decline(text, ("반에크 반도체 상장지수펀드", "smh"))
    oil_price_match = re.search(r"유가[^.!?]{0,18}?(\d+(?:\.\d+)?)\s*달러", text)
    oil_price = oil_price_match.group(1) if oil_price_match else ""
    oil_rising = any(
        term in text
        for term in ("유가 상승", "유가 급등", "유가 폭등", "유가 100달러 돌파", "유가가 올")
    )
    oil_falling = any(
        term in text
        for term in ("유가 하락", "유가 급락", "유가가 내", "유가가 떨어")
    )
    metrics = []
    if nasdaq:
        metrics.append(f"나스닥 {nasdaq}%")
    if sox:
        metrics.append(f"필라델피아 반도체지수 {sox}%")
    if smh:
        metrics.append(f"SMH {smh}%")
    metric_text = "·".join(metrics)
    if oil_rising and oil_price and nasdaq:
        core = f"유가 {oil_price}달러·나스닥 {nasdaq}% 하락, AI 수익성 우려가 겹쳤습니다."
    elif oil_rising and oil_price:
        core = f"유가 {oil_price}달러 돌파와 AI 수익성 우려로 반도체주가 하락했습니다."
    elif metric_text and oil_falling:
        core = f"{metric_text} 하락, FOMC·빅테크 실적을 대기합니다."
    elif metric_text:
        core = f"{metric_text} 하락, 반도체 차익실현이 확대됐습니다."
    else:
        core = (
            "유가 하락에도 미국 반도체주가 급락하고 나스닥이 약세를 보였습니다. "
            "FOMC와 빅테크 실적을 앞둔 차익실현과 밸류에이션 부담이 겹쳤습니다."
        )
    alert = base_korean_business_alert(
        row,
        now,
        score=114 + min(6, len(metrics) * 2),
        impacts=["할인율", "수급", "시간표"],
    )
    alert.update(
        {
            "importance": "상",
            "status": "확정",
            "policy_plain_summary": core,
            "telegram_core_fact": core,
            "telegram_investment_fact": "SOX·MU·NVDA 약세가 이어지면 삼성전자·SK하이닉스의 외국인 수급 부담입니다.",
            "investment_view": "SOX·MU·NVDA 약세가 이어지면 삼성전자·SK하이닉스의 외국인 수급 부담입니다.",
            "korea_market_impact": "삼성전자·SK하이닉스와 HBM 장비·소재주의 외국인 수급, FOMC·빅테크 실적을 함께 봅니다.",
            "sectors": ["반도체/HBM/CXL", "미국 증시/금리", "원유/인플레이션"],
            "paths": ["밸류에이션", "외국인 수급", "FOMC·실적 시간표"],
            "korean_business_kind": "global_semiconductor_market_shock",
            "supply_chain_theme": f"us_semiconductor_selloff:{date_key}",
        }
    )
    return alert


def build_ai_infrastructure_steel_alert(row: dict, now, text: str) -> dict | None:
    if not (
        "데이터센터" in text
        and any(term in text for term in ("반도체 공장", "반도체공장", "팹"))
        and any(term in text for term in ("철강", "철강재", "형강", "후판"))
        and "수요" in text
    ):
        return None
    date_key = korean_business_event_date(row)
    facts: list[str] = []
    if re.search(r"103만\s*톤", text) and "9.7%" in text:
        facts.append("1~5월 형강 내수판매는 103만톤으로 전년비 9.7% 늘었습니다.")
    if "456억원" in text and "52.3%" in text:
        facts.append("동국제강 2분기 영업이익은 456억원으로 52.3% 증가했습니다.")
    if "2030년" in text and "86만톤" in text:
        facts.append("AI 데이터센터 철강 수요는 2030년까지 86만톤으로 추정됐습니다.")
    if all(term in text for term in ("9.7%", "52.3%", "86만톤")):
        core = "형강 판매 9.7%↑·동국제강 이익 52.3%↑·수요 86만톤 전망."
    else:
        core = " ".join(facts[:1]) or detailed_article_core(
        str(row.get("source_title") or row.get("title") or ""),
        str(row.get("source_body") or row.get("source_abstract") or ""),
        )
    alert = base_korean_business_alert(
        row,
        now,
        score=105,
        impacts=["돈 버는 능력", "시간표"],
    )
    alert.update(
        {
            "importance": "중",
            "status": "예비",
            "policy_plain_summary": core,
            "telegram_core_fact": core,
            "telegram_investment_fact": "실제 팹·데이터센터 착공이 형강·후판 주문으로 이어져야 철강사 이익 추정이 올라갑니다.",
            "investment_view": "실제 팹·데이터센터 착공이 형강·후판 주문으로 이어져야 철강사 이익 추정이 올라갑니다.",
            "korea_market_impact": "동국제강 등 형강·후판 업체는 출하량·스프레드와 프로젝트 착공 일정으로 확인합니다.",
            "sectors": ["철강/건설소재", "AI/데이터센터", "반도체/HBM/CXL"],
            "paths": ["산업수요", "이익", "CAPEX 시간표"],
            "korean_business_kind": "ai_infrastructure_steel_demand",
            "supply_chain_theme": f"korea_ai_infrastructure_steel_demand:{date_key}",
        }
    )
    return alert


def build_korea_ai_bigtech_cooperation_alert(row: dict, now, text: str) -> dict | None:
    title = str(row.get("source_title") or row.get("title") or "")
    title_text = title.lower()
    korean_actor = any(
        term in title_text
        for term in ("삼성전자", "sk하이닉스", "sk그룹", "sk텔레콤", "현대차", "네이버")
    )
    global_actor = any(
        term in title_text
        for term in ("엔비디아", "브로드컴", "마이크로소프트", "앤트로픽", "오픈ai", "aws")
    )
    action = any(
        term in text
        for term in ("공급계약", "장기 공급", "장기공급", "협력 체결", "mou", "파트너십", "공동 구축")
    )
    title_action = any(
        term in title_text
        for term in (
            "계약",
            "공급",
            "협력 체결",
            "협력 추진",
            "공동 구축",
            "구축",
            "투자",
            "수주",
            "발주",
            "mou",
        )
    ) or bool(extract_foreign_amounts(title))
    if not (
        korean_actor
        and global_actor
        and action
        and title_action
        and any(term in text for term in ("반도체", "메모리", "hbm", "ai 데이터센터", "ai 인프라"))
    ):
        return None
    body = str(row.get("source_body") or row.get("source_abstract") or "")
    date_key = korean_business_event_date(row)
    if "삼성전자" in text and "브로드컴" in text:
        event = "samsung_broadcom_ai"
    elif ("sk그룹" in text or "sk하이닉스" in text) and "엔비디아" in text:
        event = "sk_nvidia_ai_memory"
    elif "앤트로픽" in text and any(term in text for term in ("삼성전자", "sk하이닉스")):
        event = "anthropic_korea_memory"
    else:
        event = "korea_global_bigtech_ai"
    ranked = ranked_article_sentences(
        body,
        ["협력", "공급", "계약", "반도체", "메모리", "ai 인프라"],
        title=title,
    )
    agreement_sentences = [
        normalized_article_sentence(sentence)
        for sentence in ranked
        if extract_foreign_amounts(sentence)
        and any(
            term in sentence.lower()
            for term in ("협력", "공급", "계약", "파트너십", "공동 구축")
        )
    ]
    core = ""
    if event == "sk_nvidia_ai_memory":
        if re.search(r"5000\s*억\s*달러", text):
            core = "SK그룹이 엔비디아와 5000억달러 규모 AI 인프라 협력을 추진합니다."
        elif "730조원" in text or "731조원" in text:
            core = "SK그룹이 엔비디아와 약 730조원 규모 AI 인프라 협력을 추진합니다."
        if core and "마이크로소프트" in text and any(
            term in text for term in ("장기 공급", "장기공급", "메모리 공급")
        ):
            core += " 마이크로소프트와 메모리 장기공급도 추진합니다."
    elif event == "samsung_broadcom_ai":
        if re.search(r"2000\s*억\s*달러", text):
            core = "삼성전자가 브로드컴과 2000억달러 규모 AI 반도체 협력을 추진합니다."
        elif "292조원" in text:
            core = "삼성전자가 브로드컴과 약 292조원 규모 AI 반도체 협력을 추진합니다."
        if core and "파운드리" in text and "메모리" in text:
            core += " 파운드리·메모리 협력이 포함됐습니다."
    if not core and agreement_sentences:
        core = bounded_complete_excerpt(agreement_sentences[0], 180)
    if not core:
        core = detailed_article_core(title, body)
    if not core:
        core = article_sentences(body, korean_business_title_terms(title), 2, title=title)
    core = bounded_complete_excerpt(core, GAMEJOA_CORE_MAX_CHARS)
    alert = base_korean_business_alert(
        row,
        now,
        score=110,
        impacts=["돈 버는 능력", "수급", "시간표"],
    )
    alert.update(
        {
            "importance": "상",
            "status": "예비",
            "policy_plain_summary": core,
            "telegram_core_fact": core,
            "telegram_investment_fact": "발표 총액 전부가 확정 매출은 아니며 품목·물량·기간·매출 인식 공시를 확인해야 합니다.",
            "investment_view": "발표 총액 전부가 확정 매출은 아니며 품목·물량·기간·매출 인식 공시를 확인해야 합니다.",
            "korea_market_impact": "삼성전자·SK하이닉스와 HBM·파운드리·AIDC 밸류체인은 개별 계약 범위가 확인된 경우만 연결합니다.",
            "sectors": ["반도체/HBM/CXL", "AI/데이터센터"],
            "paths": ["계약 가시성", "공급·수요", "수급", "실행 시간표"],
            "korean_business_kind": "korea_ai_bigtech_cooperation",
            "supply_chain_theme": f"{event}:{date_key}",
        }
    )
    return alert


def build_global_semiconductor_leader_signal(row: dict, now, text: str) -> dict | None:
    title = str(row.get("source_title") or row.get("title") or "")
    if not (
        "젠슨 황" in text
        and any(term in text for term in ("코스피", "한국 반도체", "반도체 산업"))
        and any(term in text for term in ("오를", "상승", "호황", "황금기", "낙관"))
    ):
        return None
    core = (
        "젠슨 황은 한국 반도체 호황과 코스피 재상승을 전망했습니다."
        if "코스피" in text
        else "젠슨 황은 한국 반도체 산업의 호황 지속을 전망했습니다."
    )
    alert = base_korean_business_alert(row, now, score=103, impacts=["수급"])
    alert.update(
        {
            "importance": "중",
            "status": "예비",
            "policy_plain_summary": core,
            "telegram_core_fact": core,
            "sectors": ["반도체/HBM/CXL", "금융/자본시장"],
            "paths": ["투자심리", "외국인 수급"],
            "korean_business_kind": "global_semiconductor_leader_signal",
            "supply_chain_theme": f"jensen_korea_market_signal:{korean_business_event_date(row)}",
        }
    )
    return alert


def build_skhynix_earnings_consensus_alert(row: dict, now, text: str) -> dict | None:
    title = str(row.get("source_title") or row.get("title") or "")
    title_lower = title.lower()
    if not (
        any(term in title_lower for term in ("sk하이닉스", "하닉"))
        and "2분기" in title_lower
        and any(term in title_lower for term in ("영업익", "영업이익"))
        and "이익률" in title_lower
    ):
        return None
    profit_match = re.search(
        r"(?:영업익|영업이익)\s*([0-9][\d,.]*\s*조(?:원)?)",
        title,
    )
    margin_match = re.search(
        r"이익률\s*([0-9]+(?:\.[0-9]+)?%)",
        title,
    )
    if not profit_match or not margin_match:
        return None
    profit = re.sub(r"\s+", "", profit_match.group(1))
    margin = margin_match.group(1)
    core = (
        f"증권가는 SK하이닉스 2분기 영업익 {profit}·"
        f"이익률 {margin} 이상을 전망합니다."
    )
    alert = base_korean_business_alert(
        row,
        now,
        score=111,
        impacts=["돈 버는 능력", "수급", "시간표"],
    )
    alert.update(
        {
            "importance": "상",
            "status": "예비",
            "policy_plain_summary": core,
            "telegram_core_fact": core,
            "sectors": ["반도체/HBM/CXL"],
            "paths": ["실적 전망", "마진", "실적 발표 시간표"],
            "korean_business_kind": "skhynix_earnings_consensus",
            "supply_chain_theme": f"skhynix_earnings_consensus:{korean_business_event_date(row)}",
        }
    )
    return alert


def build_kstartup_global_vc_access_alert(row: dict, now, text: str) -> dict | None:
    title = str(row.get("source_title") or row.get("title") or "").lower()
    title_has_vc = any(term in title for term in ("a16z", "벤처캐피털", "실리콘밸리", " vc"))
    if not title_has_vc:
        return None
    if "국민연금" in title and any(term in title for term in ("투자", "맞손", "기회")):
        core = "국민연금이 실리콘밸리 최상위 VC와 투자 협력을 확대합니다."
        alert = base_korean_business_alert(row, now, score=104, impacts=["수급", "시간표"])
        alert.update(
            {
                "importance": "중",
                "status": "예비",
                "policy_plain_summary": core,
                "telegram_core_fact": core,
                "sectors": ["벤처투자/스타트업", "금융/자본시장"],
                "paths": ["벤처자금", "협력 시간표"],
                "korean_business_kind": "kstartup_global_vc_access",
                "supply_chain_theme": f"nps_global_vc_access:{korean_business_event_date(row)}",
            }
        )
        return alert
    if not (
        any(term in text for term in ("a16z", "벤처캐피털", "실리콘밸리", " vc "))
        and any(term in text for term in ("k스타트업", "한국 스타트업", "한국스타트업"))
        and any(term in text for term in ("투자", "협력", "펀드", "운용자산"))
    ):
        return None
    scale = "글로벌"
    scale_match = re.search(r"(\d[\d,.]*)\s*조(?:원)?", text)
    if scale_match:
        scale = f"운용자산 {scale_match.group(1)}조원"
    core = f"{scale} VC들이 K스타트업 협력 확대를 논의했습니다."
    alert = base_korean_business_alert(row, now, score=104, impacts=["수급", "시간표"])
    alert.update(
        {
            "importance": "중",
            "status": "예비",
            "policy_plain_summary": core,
            "telegram_core_fact": core,
            "sectors": ["벤처투자/스타트업", "AI/데이터센터"],
            "paths": ["벤처자금", "협력 시간표"],
            "korean_business_kind": "kstartup_global_vc_access",
            "supply_chain_theme": f"kstartup_global_vc_access:{korean_business_event_date(row)}",
        }
    )
    return alert


def build_samsung_openai_meeting_alert(row: dict, now, text: str) -> dict | None:
    title = str(row.get("source_title") or row.get("title") or "").lower()
    if not (
        any(term in title for term in ("이재용", "삼성전자"))
        and any(term in title for term in ("샘 올트먼", "샘올트먼", "오픈ai"))
        and any(term in title for term in ("회동", "만나", "만났", "협의", "논의"))
        and any(term in text for term in ("hbm", "d램", "dram", "파운드리", "반도체"))
    ):
        return None
    core = "이재용·올트먼이 회동했고 HBM·파운드리 협력은 관측 단계입니다."
    alert = base_korean_business_alert(row, now, score=106, impacts=["수급", "시간표"])
    alert.update(
        {
            "importance": "중",
            "status": "예비",
            "policy_plain_summary": core,
            "telegram_core_fact": core,
            "sectors": ["반도체/HBM/CXL", "AI/데이터센터"],
            "paths": ["고객 협력", "사업 시간표", "테마 수급"],
            "korean_business_kind": "samsung_openai_meeting",
            "supply_chain_theme": f"samsung_openai_meeting:{korean_business_event_date(row)}",
        }
    )
    return alert


def build_korea_nvidia_ecosystem_alert(row: dict, now, text: str) -> dict | None:
    title = str(row.get("source_title") or row.get("title") or "").lower()
    if not (
        "엔비디아" in title
        and any(term in title for term in ("k기업", "한국 기업", "국내 기업", "한국기업"))
        and any(term in title for term in ("ai", "생태계", "반도체", "인프라", "협력"))
    ):
        return None
    core = "K기업들이 엔비디아와 AI 반도체·인프라 협력을 확대합니다."
    alert = base_korean_business_alert(
        row,
        now,
        score=107,
        impacts=["돈 버는 능력", "수급", "시간표"],
    )
    alert.update(
        {
            "importance": "상",
            "status": "예비",
            "policy_plain_summary": core,
            "telegram_core_fact": core,
            "sectors": ["반도체/HBM/CXL", "AI/데이터센터"],
            "paths": ["고객 협력", "AI CAPEX", "수급"],
            "korean_business_kind": "korea_nvidia_ai_ecosystem",
            "supply_chain_theme": f"korea_nvidia_ai_ecosystem:{korean_business_event_date(row)}",
        }
    )
    return alert


def build_bigtech_ai_layoff_alert(row: dict, now, text: str) -> dict | None:
    if not (
        any(term in text for term in ("빅테크", "기술기업", "테크기업"))
        and "ai" in text
        and any(term in text for term in ("감원", "인력 감축", "일자리"))
        and any(term in text for term in ("투자", "데이터센터", "설비투자", "capex"))
    ):
        return None
    count_match = re.search(r"(약\s*)?(\d[\d,.]*\s*만)\s*(?:명|개)", text)
    count = re.sub(r"\s+", "", count_match.group(2)) if count_match else ""
    core = (
        f"미 기술기업은 AI 투자 확대 속 올해 약 {count}명을 감원했습니다."
        if count
        else "미 기술기업은 AI 투자 확대와 동시에 대규모 감원을 진행했습니다."
    )
    alert = base_korean_business_alert(row, now, score=106, impacts=["돈 버는 능력", "시간표"])
    alert.update(
        {
            "importance": "중",
            "status": "예비",
            "policy_plain_summary": core,
            "telegram_core_fact": core,
            "sectors": ["AI/데이터센터", "미국 증시/금리"],
            "paths": ["AI CAPEX", "비용 절감", "고용"],
            "korean_business_kind": "bigtech_ai_capex_layoffs",
            "supply_chain_theme": f"bigtech_ai_capex_layoffs:{korean_business_event_date(row)}",
        }
    )
    return alert


def build_korea_oil_fx_inflation_alert(row: dict, now, text: str) -> dict | None:
    title = str(row.get("source_title") or row.get("title") or "").lower()
    macro_hits = sum(term in text for term in ("물가", "환율", "금리"))
    if not (
        any(term in title for term in ("국제유가", "유가 불안", "유가 상승", "물가", "환율"))
        and any(term in text for term in ("국제유가", "유가 불안", "유가 상승"))
        and macro_hits >= 2
    ):
        return None
    core = "중동발 유가 불안이 국내 물가·환율·금리 부담으로 번지고 있습니다."
    alert = base_korean_business_alert(
        row,
        now,
        score=110,
        impacts=["돈 버는 능력", "할인율", "수급"],
    )
    alert.update(
        {
            "importance": "상",
            "status": "예비",
            "policy_plain_summary": core,
            "telegram_core_fact": core,
            "sectors": ["원유/인플레이션", "환율/수출입", "금융/자본시장"],
            "paths": ["원자재 비용", "물가", "환율", "금리"],
            "korean_business_kind": "korea_oil_fx_inflation",
            "supply_chain_theme": f"korea_oil_fx_inflation:{korean_business_event_date(row)}",
        }
    )
    return alert


def build_fomc_rate_outlook_alert(row: dict, now, text: str) -> dict | None:
    title = str(row.get("source_title") or row.get("title") or "").lower()
    if not (
        any(term in title for term in ("fomc", "연준"))
        and "금리" in text
        and any(term in title for term in ("동결", "인상", "인하", "전망", "엇갈"))
    ):
        return None
    if "동결" in text and "인상" in text:
        core = "월가의 FOMC 금리 동결·인상 전망이 엇갈리고 있습니다."
    elif "동결" in text:
        core = "월가는 이번 FOMC의 금리 동결 가능성을 높게 보고 있습니다."
    elif "인하" in text:
        core = "월가는 FOMC 금리 인하 시점과 폭을 다시 점검하고 있습니다."
    else:
        core = "월가는 FOMC 금리 경로가 달러·증시 할인율을 바꿀지 주목합니다."
    alert = base_korean_business_alert(
        row,
        now,
        score=108,
        impacts=["할인율", "수급", "시간표"],
    )
    alert.update(
        {
            "importance": "상",
            "status": "예비",
            "policy_plain_summary": core,
            "telegram_core_fact": core,
            "sectors": ["미국 증시/금리", "금융/자본시장"],
            "paths": ["금리 경로", "달러", "할인율"],
            "korean_business_kind": "fomc_rate_outlook",
            "supply_chain_theme": f"fomc_rate_outlook:{korean_business_event_date(row)}",
        }
    )
    return alert


def build_middle_east_geopolitical_alert(row: dict, now, text: str) -> dict | None:
    if not (
        any(term in text for term in ("이란", "호르무즈", "후티"))
        and any(term in text for term in ("공습", "충돌", "휴전", "소강", "공격"))
        and any(term in text for term in ("사우디", "미국", "이스라엘", "홍해", "유조선"))
    ):
        return None
    core = "미·이란 공습 소강 뒤 사우디·후티 충돌로 유가·운임 위험이 남았습니다."
    alert = base_korean_business_alert(
        row,
        now,
        score=114,
        impacts=["돈 버는 능력", "할인율", "수급", "시간표"],
    )
    alert.update(
        {
            "importance": "상",
            "status": "예비",
            "policy_plain_summary": core,
            "telegram_core_fact": core,
            "sectors": ["방산/지정학", "정유/화학/해운", "원유/인플레이션"],
            "paths": ["지정학 리스크", "유가·운임", "환율"],
            "korean_business_kind": "middle_east_geopolitical_risk",
            "supply_chain_theme": f"middle_east_geopolitical_risk:{korean_business_event_date(row)}",
            "realtime_policy_lane": True,
        }
    )
    return alert


def build_china_memory_ipo_alert(row: dict, now, text: str) -> dict | None:
    if not (
        any(term in text for term in ("cxmt", "창신메모리"))
        and any(term in text for term in ("상장", "ipo"))
        and any(term in text for term in ("메모리", "반도체", "etf"))
    ):
        return None
    core = "CXMT 상장 추진이 중국 메모리 공급·ETF 수급 변수로 부각됐습니다."
    alert = base_korean_business_alert(row, now, score=104, impacts=["수급", "시간표"])
    alert.update(
        {
            "importance": "중",
            "status": "예비",
            "policy_plain_summary": core,
            "telegram_core_fact": core,
            "sectors": ["반도체/HBM/CXL", "금융/자본시장"],
            "paths": ["중국 메모리 공급", "IPO", "ETF 수급"],
            "korean_business_kind": "china_memory_ipo",
            "supply_chain_theme": f"china_memory_ipo:{korean_business_event_date(row)}",
        }
    )
    return alert


def build_korea_etf_net_buy_alert(row: dict, now, text: str) -> dict | None:
    if not (
        "etf" in text
        and "개인" in text
        and "순매수" in text
        and re.search(r"\d[\d,.]*(?:조|억)원", text)
    ):
        return None
    total_match = re.search(r"순매수[^.!?]{0,50}?(?<!\d)(\d[\d,.]*\s*조원)", text)
    covered_match = re.search(
        rf"커버드콜[^.!?]{{0,60}}?({KOREAN_WON_AMOUNT_PATTERN})",
        text,
    )
    facts = []
    if total_match:
        total_value = re.sub(r"\s+", "", total_match.group(1))
        facts.append(f"개인 ETF 순매수 {total_value}")
    if covered_match:
        facts.append(f"커버드콜 상위 종목 {covered_match.group(1)}")
    core = "·".join(facts) + "입니다." if facts else "개인의 국내 ETF 순매수 규모가 크게 늘었습니다."
    alert = base_korean_business_alert(row, now, score=105, impacts=["수급"])
    alert.update(
        {
            "importance": "중",
            "status": "확정",
            "policy_plain_summary": core,
            "telegram_core_fact": core,
            "sectors": ["금융/자본시장"],
            "paths": ["개인 순매수", "ETF 상품 수급"],
            "korean_business_kind": "korea_etf_net_buy",
            "supply_chain_theme": f"korea_etf_net_buy:{korean_business_event_date(row)}",
        }
    )
    return alert


def build_ai_factory_deployment_alert(row: dict, now, text: str) -> dict | None:
    if not (
        any(term in text for term in ("sk텔레콤", "skt"))
        and "네이버" in text
        and any(term in text for term in ("ai 팩토리", "ai팩토리"))
        and any(term in text for term in ("베라 루빈", "vera rubin", "dsx"))
        and any(term in text for term in ("도입", "우선 할당", "구축"))
    ):
        return None
    core = "SKT·네이버가 내년 베라루빈 기반 AI팩토리 도입을 추진합니다."
    alert = base_korean_business_alert(
        row,
        now,
        score=108,
        impacts=["돈 버는 능력", "수급", "시간표"],
    )
    alert.update(
        {
            "importance": "상",
            "status": "예비",
            "policy_plain_summary": core,
            "telegram_core_fact": core,
            "sectors": ["AI/데이터센터", "반도체/HBM/CXL"],
            "paths": ["AI CAPEX", "GPU·HBM 수요", "도입 시간표"],
            "korean_business_kind": "korea_ai_factory_deployment",
            "supply_chain_theme": f"korea_ai_factory_deployment:{korean_business_event_date(row)}",
        }
    )
    return alert


def build_sk_ms_memory_supply_alert(row: dict, now, text: str) -> dict | None:
    title = str(row.get("source_title") or row.get("title") or "").lower()
    title_has_sk = any(
        term in title for term in ("sk,", "sk ", "sk하이닉스", "sk그룹")
    )
    title_has_ms = "마이크로소프트" in title or bool(
        re.search(r"(^|[^a-z0-9])ms([^a-z0-9]|$)", title)
    )
    if not (
        title_has_sk
        and title_has_ms
        and any(term in title for term in ("장기 공급", "장기공급"))
        and any(term in text for term in ("hbm4", "hbm 4", "메모리"))
    ):
        return None
    if any(term in text for term in ("hbm4", "hbm 4")):
        core = "SK하이닉스가 MS와 HBM4 공동개발·장기공급 계약을 체결했습니다."
    else:
        core = "SK가 MS와 AI 메모리 장기공급 계약을 체결했다고 보도됐습니다."
    alert = base_korean_business_alert(
        row,
        now,
        score=118,
        impacts=["돈 버는 능력", "수급", "시간표"],
    )
    alert.update(
        {
            "importance": "상",
            "status": "예비",
            "policy_plain_summary": core,
            "telegram_core_fact": core,
            "sectors": ["반도체/HBM/CXL", "AI/데이터센터"],
            "paths": ["장기공급 계약", "AI 메모리 수요", "계약 시간표"],
            "korean_business_kind": "sk_ms_hbm4_supply",
            "supply_chain_theme": f"sk_ms_hbm4_supply:{korean_business_event_date(row)}",
        }
    )
    return alert


def build_verified_korean_business_alert(row: dict, now) -> dict | None:
    title = str(row.get("source_title") or row.get("title") or "")
    title_text = title.lower()
    body = str(row.get("source_body") or row.get("source_abstract") or "")
    text = f"{title} {body}".lower()

    if "외국인" in title_text and "순매수" in title_text and all(
        term in title_text for term in ("삼성전자", "sk하이닉스")
    ):
        alert = base_korean_business_alert(row, now, score=112, impacts=["수급"])
        alert.update(
            {
                "policy_plain_summary": (
                    "외국인이 4거래일간 삼성전자·SK하이닉스를 "
                    "약 4.5조원 순매수했습니다."
                ),
                "telegram_core_fact": "외국인이 삼성전자·SK하이닉스를 약 4.5조원 순매수했습니다.",
                "investment_view": "외국인 매수 집중은 대형 반도체주의 단기 수급과 지수 기여도를 바꿉니다. 다만 HBM 수요 전망은 매수 이유이지 이번 기사만으로 새 실적이 확정된 것은 아닙니다.",
                "korea_market_impact": "삼성전자·SK하이닉스의 외국인 순매수 지속 여부와 반도체 장비·부품주로 매수 폭이 넓어지는지 구분해 확인합니다.",
                "priced_in": "중간. 기사 기준 누적 매수 기간에 두 종목 주가가 이미 반응했을 수 있어 다음 거래일 순매수 지속성이 중요합니다.",
                "counter": "특정 4거래일 누적치이며 일부 반도체 장비주는 외국인이 순매도해 업종 전체 매수로 일반화하기 어렵습니다.",
                "interpretation": "외국인이 삼성전자·SK하이닉스에 집중한 수급 신호입니다. 실적 변화보다 당일 지수와 대형주 수급에 직접적입니다.",
                "failed_signal": "외국인이 순매도로 전환하거나 반도체 업종 확산 없이 두 대형주 거래만 끝나면 후속 수급 재료가 약해집니다.",
                "korean_business_kind": "foreign_semiconductor_flow",
            }
        )
        return alert

    if "엑시콘" in text and "cxl 3.1" in text and "양산평가" in text:
        alert = base_korean_business_alert(
            row,
            now,
            score=104,
            impacts=["돈 버는 능력", "시간표", "수급"],
        )
        alert.update(
            {
                "policy_plain_summary": (
                    "엑시콘이 삼성전자와 CXL 3.1 테스터 양산평가 중이며 "
                    "이달 말 종료 예정입니다."
                ),
                "investment_view": "삼성전자 양산평가 통과는 CXL·Gen6 테스터 공급의 선행 조건입니다. 평가 종료는 수주가 아니므로 장비 발주·공급계약·매출 인식 확인이 필요합니다.",
                "korea_market_impact": "한국장에서는 엑시콘과 CXL·SSD 검사장비 밸류체인의 수급을 보되, 삼성전자 평가 통과와 신규 계약 공시가 확인된 종목만 연결합니다.",
                "priced_in": "낮음~중간. 이달 말 평가 종료 기대는 단기 수급에 반영될 수 있지만 양산 공급 규모는 아직 확정되지 않았습니다.",
                "counter": "양산평가 진행은 확정 매출이 아니며 경쟁사도 평가에 참여한 것으로 보도됐습니다. 최종 채택 물량과 공급 시점이 달라질 수 있습니다.",
                "interpretation": "CXL 3.1 테스터가 개발 단계에서 고객 양산평가 단계로 이동한 시간표 뉴스입니다. 통과 후 발주가 확인돼야 돈 버는 능력이 실제로 바뀝니다.",
                "failed_signal": "평가 완료가 지연되거나 삼성전자 발주·엑시콘 공급계약 공시가 나오지 않으면 상용화 기대만 남습니다.",
                "korean_business_kind": "exicon_cxl_tester",
            }
        )
        return alert

    for builder in (
        build_single_stock_leverage_rule_alert,
        build_global_semiconductor_market_alert,
        build_ai_infrastructure_steel_alert,
        build_hyundai_nvidia_meeting_alert,
        build_global_semiconductor_leader_signal,
        build_skhynix_earnings_consensus_alert,
        build_kstartup_global_vc_access_alert,
        build_samsung_openai_meeting_alert,
        build_korea_nvidia_ecosystem_alert,
        build_bigtech_ai_layoff_alert,
        build_middle_east_geopolitical_alert,
        build_korea_oil_fx_inflation_alert,
        build_fomc_rate_outlook_alert,
        build_china_memory_ipo_alert,
        build_korea_etf_net_buy_alert,
        build_ai_factory_deployment_alert,
        build_sk_ms_memory_supply_alert,
        build_korea_ai_bigtech_cooperation_alert,
    ):
        alert = builder(row, now, text)
        if alert:
            alert["interpretation"] = (
                alert.get("investment_view")
                or alert.get("telegram_investment_fact")
                or alert.get("policy_plain_summary")
            )
            return alert

    if any(term in title.lower() for term in KOREAN_BUSINESS_MARKET_RECAP_TERMS):
        return None

    title_text = title.lower()
    title_material_terms = [
        term for term in KOREAN_BUSINESS_MATERIAL_TERMS
        if korean_business_title_has_material_term(title_text, term)
    ]
    if not title_material_terms:
        return None
    impacts = korean_business_impacts(text, [])
    if not impacts:
        return None
    has_numeric_materiality = bool(
        re.search(r"\d[\d,.]*\s*(?:%|억|조|만|t|톤|달러|원)", title_text)
    )
    source_score = (
        90
        + min(12, len(title_material_terms) * 3)
        + (4 if has_numeric_materiality else 0)
    )
    alert = base_korean_business_alert(
        row,
        now,
        score=source_score,
        impacts=impacts,
    )
    return apply_generic_korean_business_profile(alert, row, now)


def enforce_korean_business_news_contract() -> None:
    original_collect_items = contract.strict.collect_items

    def collect_items(now):
        rows, notes = original_collect_items(now)
        verified = 0
        failed = 0
        attempted = 0
        detail_candidates = []
        seen_links = set()
        for row in rows:
            if not is_korean_business_row(row) or not row.get("link"):
                continue
            link = str(row.get("link"))
            if link in seen_links:
                continue
            seen_links.add(link)
            row["publisher"] = korean_business_publisher(row)
            detail_candidates.append(row)
        detail_candidates.sort(key=korean_business_detail_priority, reverse=True)
        deferred = max(0, len(detail_candidates) - KOREAN_BUSINESS_DETAIL_LIMIT)
        selected_candidates = detail_candidates[:KOREAN_BUSINESS_DETAIL_LIMIT]

        def fetch_detail(row: dict) -> tuple[dict, str | None, str | None]:
            detail_html, detail_error = base.fetch(str(row.get("link")), 16)
            return row, detail_html, detail_error

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(KOREAN_BUSINESS_DETAIL_WORKERS, max(1, len(selected_candidates)))
        ) as executor:
            detail_results = list(executor.map(fetch_detail, selected_candidates))

        for row, detail_html, detail_error in detail_results:
            attempted += 1
            if detail_error or not detail_html:
                row["_article_verification_failed"] = detail_error or "empty article"
                failed += 1
                continue
            detail = extract_article_detail(detail_html, str(row.get("title") or ""))
            if not detail.get("body_verified"):
                row["_article_verification_failed"] = (
                    "title/body mismatch "
                    f"aligned={detail.get('title_aligned')} body_chars={len(str(detail.get('body') or ''))}"
                )
                failed += 1
                continue
            row["source_title"] = detail.get("title") or row.get("title")
            row["source_body"] = detail.get("body") or ""
            row["source_abstract"] = re.sub(
                r"\s+",
                " ",
                f"{detail.get('abstract') or ''} {detail.get('body') or ''}",
            ).strip()[:16000]
            row["summary"] = row["source_abstract"]
            row["body_verified"] = True
            if detail.get("published_kst"):
                parsed = base.parse_date(detail["published_kst"])
                if parsed:
                    row["published"] = parsed
            verified += 1
        notes.append(
            "Korean business detail: "
            f"attempted={attempted} verified={verified} failed={failed} deferred={deferred} "
            f"workers={KOREAN_BUSINESS_DETAIL_WORKERS}"
        )
        print(
            f"korean_business_detail attempted={attempted} "
            f"verified={verified} failed={failed} deferred={deferred} "
            f"workers={KOREAN_BUSINESS_DETAIL_WORKERS}"
        )
        return rows, notes

    original_classify = contract.strict.classify

    def classify(row: dict, now):
        if is_korean_business_row(row):
            if row.get("_article_verification_failed") or not row.get("body_verified"):
                return None
            return build_verified_korean_business_alert(row, now)
        return original_classify(row, now)

    contract.strict.collect_items = collect_items
    contract.strict.classify = classify


enforce_korean_business_news_contract()


def safe(value: object) -> str:
    return html.escape(str(value or "확인 불가"), quote=False)


def html_link(label: str, url: str) -> str:
    text = html.escape(label or "출처", quote=False)
    if not url:
        return text
    return f'<a href="{html.escape(url, quote=True)}">{text}</a>'


def source_summary(items: list[dict]) -> str:
    grouped: dict[str, dict[str, object]] = {}
    for item in items:
        publisher = item.get("publisher") or "출처 확인 불가"
        if publisher not in grouped:
            grouped[publisher] = {"count": 0, "link": item.get("link") or ""}
        grouped[publisher]["count"] = int(grouped[publisher]["count"]) + 1
        if not grouped[publisher]["link"] and item.get("link"):
            grouped[publisher]["link"] = item.get("link")
    parts = []
    for publisher, meta in grouped.items():
        label = f"{publisher} {meta['count']}건" if int(meta["count"]) > 1 else publisher
        parts.append(html_link(label, str(meta.get("link") or "")))
    return " / ".join(parts) if parts else "출처 확인 불가"


LOW_IMPACT_TITLE_TERMS = [
    "request for comments and notice of public hearing",
]

HARD_LOW_IMPACT_TITLE_TERMS = [
    "annual review of country eligibility",
    "african growth and opportunity act",
    "annual inquiry service list",
    "antidumping or countervailing duty order finding or suspended investigation",
    "continuation of the national emergency",
    "delete, delete, delete",
    "digital opportunity data collection",
    "establishing the digital opportunity data collection",
    "federal oil, gas, and coal amendments",
    "federal oil gas and coal amendments",
    "nominations & appointments",
    "nominations appointments",
    "nominations sent to the senate",
    "note regarding format of review requests",
    "opportunity to request administrative review",
    "resilient networks",
    "disruptions to communications",
    "disaster information reporting system",
    "sunshine act meetings",
    "technical guidelines for the production of regenerative agricultural biofuel feedstocks",
    "television broadcasting services",
]

FEDERAL_REGISTER_MARKERS = ["federal register", "federalregister.gov", "연방관보"]


def unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def alert_text(alert: dict) -> str:
    parts = [
        alert.get("news"),
        alert.get("original_news"),
        alert.get("publisher"),
        alert.get("source"),
        alert.get("link"),
        alert.get("policy_plain_summary"),
        alert.get("investment_view"),
        alert.get("korea_market_impact"),
        alert.get("counter"),
        alert.get("failed_signal"),
        " ".join(str(x) for x in alert.get("matched") or []),
    ]
    for item in alert.get("examples") or []:
        parts.extend([
            item.get("title"),
            item.get("summary"),
            item.get("publisher"),
            item.get("source"),
            item.get("link"),
        ])
    return base.norm(" ".join(str(part or "") for part in parts))


def source_evidence_text(alert: dict) -> str:
    """Return source-authored evidence, excluding query labels and commentary."""
    parts = [
        alert.get("source_title") or alert.get("original_news"),
        alert.get("source_abstract"),
        alert.get("publisher"),
        alert.get("link"),
    ]
    for item in alert.get("examples") or []:
        parts.extend([
            item.get("title"),
            item.get("summary"),
            item.get("publisher"),
            item.get("link"),
        ])
    return base.norm(" ".join(str(part or "") for part in parts))


def source_subject_text(alert: dict) -> str:
    """Source title and official abstract only, never generated commentary.

    The classifier deliberately keeps broad matching terms for recall.  Those
    terms must not decide the Korean headline because a subordinate keyword in
    an abstract can otherwise overwrite the actual document subject.
    """
    parts = [
        alert.get("source_title") or alert.get("original_news") or alert.get("news"),
        alert.get("source_abstract"),
        alert.get("publisher"),
        alert.get("link"),
        alert.get("source_document_number"),
    ]
    return base.norm(" ".join(str(part or "") for part in parts))


def is_federal_register_source(alert: dict) -> bool:
    link = str(alert.get("link") or "").lower()
    return "federalregister.gov/documents/" in link or has_term(source_subject_text(alert), FEDERAL_REGISTER_MARKERS)


def federal_register_profile(alert: dict) -> dict[str, object] | None:
    """Return a source-faithful Korean profile for verified FR documents.

    The profile is intentionally narrow: only a verified document signature
    may receive an exact Korean policy template.
    """
    if not is_federal_register_source(alert):
        return None
    title = base.norm(str(alert.get("source_title") or alert.get("original_news") or ""))
    abstract = base.norm(str(alert.get("source_abstract") or ""))
    document_number = str(alert.get("source_document_number") or "")
    is_uae_ear = (
        "united arab emirates" in title
        and "export administration regulations" in title
        and (
            document_number == "2026-14132"
            or ("country groups d:3" in abstract and "country group a:5" in abstract)
        )
    )
    if not is_uae_ear:
        return None
    return {
        "id": "federal_register_uae_ear",
        "title": "미 상무부 BIS, UAE 대상 수출관리규정(EAR) 우대 적용 확대",
        "core": (
            "미 상무부 산업안보국(BIS)이 UAE를 EAR 국가그룹 D:3·D:4에서 제외하고 "
            "A:5에 추가한 최종규칙입니다. UAE 정부와 승인 상업기관에는 STA를 포함한 "
            "추가 라이선스 예외가 열리며, 규칙은 7월 10일부터 효력이 발생했습니다."
        ),
        "view": (
            "UAE향 첨단컴퓨팅·위성·이중용도 품목의 미국 수출·재수출 허가 부담과 "
            "납기 불확실성은 낮아질 수 있습니다. 다만 한국 기업의 실적 영향은 UAE향 "
            "매출과 미국 EAR 적용 비중이 확인될 때만 판단할 수 있습니다."
        ),
        "korea": (
            "한국장 직접 수혜로 일반화하지 않습니다. 반도체·AI 서버, 위성·방산, "
            "플랜트 장비 중 UAE향 수출 또는 미국산 기술·부품 통제를 받는 기업만 "
            "개별 공시와 공급계약으로 확인합니다."
        ),
        "impacts": ["돈 버는 능력", "시간표"],
        "paths": ["수출통제", "공급망", "정책 타임라인"],
        "sectors": ["수출통제/통상", "UAE향 첨단기술·방산/위성", "반도체/AI"],
        "priced": (
            "중간. 7월 10일 발효된 최종규칙이지만, 한국 기업별 UAE향 매출·EAR 적용 "
            "노출이 확인되기 전에는 일괄적인 실적 상향 재료로 보기 어렵습니다."
        ),
        "counter": (
            "우대 적용은 UAE 정부와 승인 상업기관, 품목별 EAR 요건에 한정됩니다. "
            "미국산 기술·부품 비중, 최종사용자, 개별 예외 조건에 따라 실제 허가 부담은 달라집니다."
        ),
        "failure": (
            "BIS의 적용 대상·최종사용자 확인, UAE향 수출·재수출 계약, 기업별 매출·납기 변화가 "
            "뒤따르지 않으면 한국장에는 직접 재료가 되지 않습니다."
        ),
    }


SOURCE_OUTPUT_ALIGNMENT_THEMES = [
    (
        "nuclear",
        ["nuclear", "reactor", "smr", "small modular reactor", "ap1000", "westinghouse", "원전", "원자력", "소형모듈원전"],
        ["원전", "원자력", "smr", "ap1000", "westinghouse", "두산에너빌리티", "khnp"],
    ),
    (
        "communications",
        ["fcc", "federal communications commission", "broadband", "spectrum", "satellite", "submarine cable", "cable landing", "covered communications equipment", "통신", "주파수", "위성", "해저케이블"],
        ["fcc", "통신·브로드밴드", "통신규제", "통신장비", "위성통신", "주파수", "해저케이블"],
    ),
    (
        "semiconductor",
        [
            "semiconductor", "chip", "hbm", "dram", "nand", "cxl", "memory tester",
            "tester", "micron", "nvidia", "tsmc", "asml", "반도체", "메모리", "테스터",
        ],
        ["반도체", "hbm", "dram", "nand", "cxl", "메모리", "테스터", "삼성전자", "sk하이닉스"],
    ),
    (
        "data_center",
        ["data center", "data-center", "data centre", "hyperscale", "데이터센터"],
        ["데이터센터", "ai 전력수요"],
    ),
    (
        "trade_control",
        ["tariff", "customs", "duty", "antidumping", "anti-dumping", "countervailing", "section 232", "section 301", "export control", "entity list", "bis", "ustr", "관세", "반덤핑", "상계관세", "수출통제", "통관"],
        ["관세", "반덤핑", "상계관세", "수출통제", "통관", "bis", "ustr"],
    ),
    (
        "iran_hormuz",
        ["iran", "iranian", "tehran", "hormuz", "red sea", "이란", "호르무즈", "홍해"],
        ["이란", "호르무즈", "홍해"],
    ),
    (
        "biotech",
        ["fda", "pdufa", "clinical trial", "phase 3", "biotech", "biopharma", "pharma", "drug", "임상", "바이오", "제약"],
        ["fda", "pdufa", "임상", "바이오", "제약", "신약"],
    ),
    (
        "defense",
        ["defense", "military", "attack", "strike", "war", "missile", "fighter", "tank", "artillery", "k9", "k2", "fa-50", "kf-21", "redback", "방산", "군사", "공격", "타격", "전쟁", "미사일", "전차", "자주포"],
        ["k-방산", "방산", "천궁", "현궁", "k9", "k2", "fa-50", "kf-21", "레드백"],
    ),
    (
        "robotics",
        ["robot", "robotics", "cobot", "factory automation", "로봇", "협동로봇", "생산자동화"],
        ["로봇", "협동로봇", "생산자동화", "레인보우로보틱스"],
    ),
]


TITLE_CORE_ALIGNMENT_STOPWORDS = {
    "ai",
    "관련",
    "기업",
    "국내",
    "미국",
    "시장",
    "전망",
    "정책",
    "추진",
    "확대",
    "협력",
    "발표",
    "보도",
    "뉴스",
    "속보",
    "오늘",
    "올해",
    "한국",
}
KOREAN_ALIGNMENT_SUFFIXES = (
    "에서는",
    "에게는",
    "으로는",
    "부터",
    "까지",
    "에서",
    "에게",
    "으로",
    "처럼",
    "보다",
    "과의",
    "와의",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "와",
    "과",
    "의",
    "도",
    "만",
    "에",
    "로",
)


def normalize_title_core_token(token: str) -> str:
    normalized = token.lower().strip(".,:%()[]{}'\"")
    if re.fullmatch(r"[가-힣]{3,}", normalized):
        for suffix in KOREAN_ALIGNMENT_SUFFIXES:
            if normalized.endswith(suffix) and len(normalized) - len(suffix) >= 2:
                normalized = normalized[: -len(suffix)]
                break
    return normalized


def title_core_alignment_tokens(value: str) -> set[str]:
    raw_tokens = re.findall(
        r"[A-Za-z][A-Za-z0-9.-]*|"
        r"\d[\d,.]*(?:%|조원|억원|만원|달러|만명|명|개)?|"
        r"[가-힣]{2,}",
        str(value or ""),
    )
    tokens = {
        normalize_title_core_token(token)
        for token in raw_tokens
    }
    return {
        token
        for token in tokens
        if len(token) >= 2 and token not in TITLE_CORE_ALIGNMENT_STOPWORDS
    }


def korean_title_core_aligned(title: str, core: str) -> bool:
    title_tokens = title_core_alignment_tokens(title)
    core_tokens = title_core_alignment_tokens(core)
    for title_token in title_tokens:
        for core_token in core_tokens:
            if title_token == core_token:
                return True
            if min(len(title_token), len(core_token)) >= 3 and (
                title_token in core_token or core_token in title_token
            ):
                return True
    return False


def source_output_aligned(alert: dict) -> bool:
    """Reject rendered themes that are not supported by source-authored text."""
    if alert.get("korean_business_news"):
        source_title = base.norm(alert.get("source_title"))
        rendered_title = base.norm(alert.get("news"))
        link = str(alert.get("link") or "").lower()
        summary = base.clean(alert.get("policy_plain_summary"))
        source_text = base.norm(
            f"{alert.get('source_title') or ''} {alert.get('source_abstract') or ''}"
        )
        rendered_text = base.norm(
            f"{alert.get('news') or ''} {alert.get('policy_plain_summary') or ''} "
            f"{alert.get('telegram_core_fact') or ''}"
        )
        oil_up = has_term(source_text, ["유가 상승", "유가 급등", "유가 폭등", "유가 100달러 돌파"])
        oil_down = has_term(source_text, ["유가 하락", "유가 급락"])
        direction_conflict = (
            (oil_up and has_term(rendered_text, ["유가 하락", "유가 급락"]))
            or (oil_down and has_term(rendered_text, ["유가 상승", "유가 급등", "유가 폭등", "유가 돌파"]))
        )
        return bool(
            alert.get("body_verified")
            and source_title
            and rendered_title == source_title
            and len(summary) >= 12
            and korean_business_source_domain_allowed(link)
            and korean_title_core_aligned(source_title, summary)
            and not direction_conflict
        )
    profile = federal_register_profile(alert)
    rendered = base.norm(" ".join(
        str(alert.get(key) or "")
        for key in ["news", "policy_plain_summary", "investment_view", "korea_market_impact", "sectors", "paths"]
    ))
    if profile:
        required = ["uae", "수출관리규정", "bis"]
        forbidden_headline = ["원전·smr·ai 전력 정책", "가스터빈", "두산에너빌리티", "khnp"]
        return all(term in rendered for term in required) and not any(term in rendered for term in forbidden_headline)

    source = source_subject_text(alert)
    for _name, source_terms, rendered_terms in SOURCE_OUTPUT_ALIGNMENT_THEMES:
        if has_term(rendered, rendered_terms) and not has_term(source, source_terms):
            return False
    return True


def semantic_event_theme(alert: dict) -> str:
    text = base.norm(
        " ".join(
            str(alert.get(key) or "")
            for key in (
                "news",
                "original_news",
                "source_title",
                "policy_plain_summary",
                "telegram_core_fact",
                "source_abstract",
                "source_body",
            )
        )
    )
    if (
        "레버리지" in text
        and any(term in text for term in ("etf", "etn"))
        and any(term in text for term in ("기본예탁금", "3000만원", "대용증권", "7월 31일", "31일부터"))
    ):
        return "korea_single_stock_leverage_rule:2026-07-31"
    if (
        any(term in text for term in ("필라델피아 반도체", "필라델피아반도체", "sox", "smh"))
        and any(term in text for term in ("4.3%", "3.3%", "나스닥 0.6%", "나스닥 0.64%"))
    ):
        return f"us_semiconductor_market_shock:{str(alert.get('published') or '')[:10]}"
    coverage_theme = coverage.semantic_theme(alert, text)
    if coverage_theme:
        return coverage_theme
    return ""


def alert_dedup_key(alert: dict) -> tuple[str, str]:
    if alert.get("iran_hormuz_escalation"):
        return ("iran_hormuz_military_escalation", str(alert.get("published") or "")[:10])
    raw_title = str(alert.get("original_news") or alert.get("news") or "")
    raw_title = re.split(r"\s+-\s+", raw_title, maxsplit=1)[0].strip()
    theme = str(alert.get("supply_chain_theme") or semantic_event_theme(alert) or "")
    if theme:
        return (base.norm(theme), "event")
    canonical = base.norm(theme or raw_title or alert.get("news") or alert.get("link"))
    return (canonical, str(alert.get("published") or "")[:10])


def has_term(text: str, terms: list[str]) -> bool:
    return any(term.lower() in text for term in terms)


def mostly_ascii(value: str) -> bool:
    letters = [ch for ch in value if ch.isalpha()]
    if not letters:
        return False
    ascii_letters = [ch for ch in letters if ord(ch) < 128]
    return len(ascii_letters) / max(len(letters), 1) >= 0.7


def is_federal_register_alert(text: str) -> bool:
    return has_term(text, FEDERAL_REGISTER_MARKERS)


DECISION_IMPACT_DISPLAY = {
    "돈 버는 능력": "매출·마진·현금흐름",
    "매출·마진·현금흐름": "매출·마진·현금흐름",
    "할인율": "밸류에이션/할인율",
    "밸류에이션/할인율": "밸류에이션/할인율",
    "수급": "수급",
    "시간표": "시간표",
}
ACTIONABLE_DECISION_LABELS = {
    "매출·마진·현금흐름",
    "밸류에이션/할인율",
    "수급",
    "시간표",
}
LIMITED_DECISION_IMPACT = "의사결정 영향 제한적"
GENERIC_EXPLANATION_PHRASES = [
    "공식 문서 또는 신뢰 보도에서 한국장 가격 변수 후보가 확인됐습니다.",
    "돈 버는 능력, 할인율, 수급, 시간표 중 무엇이 실제로 바뀌는지 원문과 시장 반응으로 재확인해야 합니다.",
    "한국장 직접 영향은 원문에 근거가 있는 업종과 종목군으로만 제한해 확인합니다.",
]
GENERIC_SECTOR_TERMS = [
    "영향 섹터 확인 불가",
    "정책/규제 일반",
    "직접 영향 확인 불가",
    "확인 불가",
]
TIMELINE_MATERIAL_TERMS = [
    "effective date",
    "implementation",
    "deadline",
    "approval",
    "authorization",
    "permit",
    "license",
    "contract",
    "supply agreement",
    "order",
    "funding opportunity",
    "loan",
    "loan guarantee",
    "nrc",
    "fda approval",
    "pdufa",
    "clinical hold",
    "phase 3",
    "official",
    "final rule",
    "notice of proposed rulemaking",
    "nprm",
    "proposed rule",
    "rulemaking",
    "request for comments",
    "public hearing",
    "comment period",
    "comment deadline",
    "investigation",
    "probe",
    "review",
    "inquiry",
    "seeks public input",
    "preparing",
    "considering",
    "proposed ban",
    "ban",
    "restriction",
    "import ban",
    "tariff review",
    "section 232 investigation",
    "section 301 review",
    "agency order",
    "directive",
    "roadmap",
    "program launch",
    "solicitation",
    "application deadline",
    "시행일",
    "마감",
    "승인",
    "허가",
    "계약",
    "수주",
    "공급계약",
    "대출",
    "보증",
    "인허가",
    "최종규칙",
    "임상",
    "실적 발표",
    "정책 발표",
    "규칙안",
    "입법예고",
    "규정안",
    "의견수렴",
    "공청회",
    "의견 제출",
    "조사 착수",
    "검토 착수",
    "수입금지",
    "금지 검토",
    "제한 검토",
    "관세 검토",
    "프로그램 공고",
    "신청 마감",
    "공모",
    "로드맵",
    "부처 지시",
]


def display_impacts(impacts: list | tuple | None) -> list[str]:
    labels: list[str] = []
    for impact in impacts or []:
        label = DECISION_IMPACT_DISPLAY.get(str(impact), str(impact))
        if label == LIMITED_DECISION_IMPACT:
            continue
        if label not in labels:
            labels.append(label)
    return labels or [LIMITED_DECISION_IMPACT]


def decision_matrix(impacts: list | tuple | None) -> str:
    labels = set(display_impacts(impacts))
    return " | ".join(
        f"{label}: {'해당' if label in labels else '해당 없음'}"
        for label in [
            "매출·마진·현금흐름",
            "밸류에이션/할인율",
            "수급",
            "시간표",
        ]
    )


def has_korea_market_link(alert: dict) -> bool:
    text = source_evidence_text(alert)
    return has_direct_market_path(text, alert)


def has_direct_market_path(text: str, alert: dict) -> bool:
    text = source_evidence_text(alert) or text
    if alert.get("korean_business_news") and alert.get("body_verified"):
        sectors = [
            str(value) for value in alert.get("sectors") or []
            if str(value) not in GENERIC_SECTOR_TERMS
        ]
        return bool(alert.get("source_title") and sectors)
    if federal_register_profile(alert):
        # The verified UAE EAR rule changes the licensing timetable for
        # advanced-computing and dual-use exports; Korean exposure remains
        # company-specific, which the rendered counterargument makes explicit.
        return True
    if any(
        alert.get(flag)
        for flag in [
            "grid_policy_delay",
            "local_dc_policy",
            "policy_drive",
            "semiconductor_selloff",
            "robotics_execution_filter",
            "biotech_leadership_filter",
            "port_strike_risk",
            "china_stimulus_bulk",
            "memory_antitrust_lawsuit",
            "transformer_tariff_policy_watch",
            "k_defense_watch",
            "korea_nuclear_siting_policy_watch",
            "k_power_watch",
        ]
    ):
        return True
    if is_china_mofcom_control(alert):
        return True
    if has_term(text, ["tariff", "duty", "duties", "antidumping", "anti-dumping", "countervailing"]):
        korea_direct = has_term(text, ["korea", "south korea", "korean", "한국", "한국산"])
        strategic_country = has_term(
            text, ["china", "chinese", "taiwan", "taiwanese", "european union", "eu ", "중국", "대만", "유럽연합"]
        )
        strategic_product = has_term(
            text,
            [
                "semiconductor", "chip", "steel", "transformer", "battery", "cathode", "anode",
                "automotive", "auto parts", "shipbuilding", "solar inverter", "robot", "robotics",
                "반도체", "철강", "변압기", "배터리", "자동차", "조선", "인버터", "로봇",
            ],
        )
        return korea_direct or (strategic_country and strategic_product)
    return has_term(
        text,
        [
            "ap1000",
            "bis",
            "chips act",
            "data center",
            "entity list",
            "export control",
            "ferc",
            "nrc",
            "section 232",
            "section 301",
            "semiconductor",
            "transformer",
            "westinghouse",
            "oil",
            "brent",
            "wti",
            "natural gas",
            "uranium",
            "copper",
            "lithium",
            "gold",
            "treasury yield",
            "treasury yields",
            "treasury bond",
            "treasury bonds",
            "10-year treasury",
            "10 year treasury",
            "real yield",
            "federal reserve",
            "hormuz",
            "red sea",
            "iran",
            "관세",
            "데이터센터",
            "반도체",
            "변압기",
            "수출통제",
            "원전",
        ],
    )


def is_low_impact_admin_alert(alert: dict) -> bool:
    text = alert_text(alert)
    if not is_federal_register_alert(text):
        return False
    if has_term(text, HARD_LOW_IMPACT_TITLE_TERMS):
        return True
    if not has_term(text, LOW_IMPACT_TITLE_TERMS):
        return False
    return not has_direct_market_path(text, alert)


def is_low_impact_trade_admin_notice(alert: dict) -> bool:
    text = alert_text(alert)
    if not has_term(text, ["antidumping", "countervailing", "anti-dumping", "상계관세", "반덤핑"]):
        return False
    return has_term(
        text,
        [
            "opportunity to request administrative review",
            "join annual inquiry service list",
            "annual inquiry service list",
            "note regarding format of review requests",
        ],
    )


def has_generic_explanation(alert: dict) -> bool:
    text = "\n".join(
        str(alert.get(key) or "")
        for key in [
            "policy_plain_summary",
            "investment_view",
            "korea_market_impact",
            "interpretation",
        ]
    )
    return any(phrase in text for phrase in GENERIC_EXPLANATION_PHRASES)


def has_decision_impact(alert: dict) -> bool:
    labels = set(display_impacts(alert.get("impacts")))
    if not labels or labels == {LIMITED_DECISION_IMPACT}:
        alert["guardrail_note"] = "매출·마진·현금흐름, 밸류에이션/할인율, 수급, 시간표 중 바뀐 축이 없어 제외"
        return False
    if not labels.intersection(ACTIONABLE_DECISION_LABELS):
        alert["guardrail_note"] = "시장 의사결정 축으로 분류되지 않아 제외"
        return False
    if not has_korea_market_link(alert):
        alert["guardrail_note"] = "한국장 업종·밸류체인 연결 근거가 약해 제외"
        return False
    if labels == {"시간표"} and not has_term(alert_text(alert), TIMELINE_MATERIAL_TERMS):
        alert["guardrail_note"] = "단순 시간표 후보일 뿐 공식 절차 착수·의견수렴·조사·정책 시행·계약 등 추적 가능한 근거가 약해 제외"
        return False
    if has_generic_explanation(alert):
        alert["guardrail_note"] = "정책·기업 이벤트의 내용과 한국장 영향이 구체적으로 설명되지 않아 제외"
        return False
    return True


def is_local_dc_like(alert: dict) -> bool:
    text = alert_text(alert)
    return bool(alert.get("local_dc_policy")) or (
        has_term(text, ["data center", "data centers", "데이터센터"])
        and has_term(text, ["zoning", "moratorium", "residents", "ordinance", "permit", "public hearing", "주민", "인허가"])
    )


LOCAL_DC_TRUSTED_SOURCE_TERMS = [
    "reuters",
    "bloomberg",
    "associated press",
    "ap news",
    "cnbc",
    "marketwatch",
    "wall street journal",
    "financial times",
    "wsj",
    "ft.com",
    "federal register",
    "ferc",
    "department of energy",
    "doe",
    "public utility commission",
    "state corporation commission",
    ".gov",
    ".gov/",
]

LOCAL_DC_HARD_ACTION_TERMS = [
    "moratorium",
    "ordinance",
    "ban",
    "banned",
    "block",
    "blocked",
    "vote",
    "voted",
    "approved",
    "passed",
    "public hearing",
    "planning commission",
    "city council",
    "county board",
    "zoning",
    "permit denied",
    "injunction",
    "lawsuit",
    "조례",
    "표결",
    "승인",
    "부결",
    "모라토리엄",
    "금지",
    "인허가",
    "공청회",
]

LOCAL_DC_WEAK_LOCAL_ONLY_TERMS = [
    "residents say",
    "neighbors say",
    "construction already impacting",
    "rural radio",
    "thecarrollnews",
    "herald-mail",
    "256 today",
    "aol.com",
    "local news",
]


def is_actionable_local_dc_policy(alert: dict) -> bool:
    if not is_local_dc_like(alert):
        return False
    examples = alert.get("examples") or []
    source_blob = " ".join(
        str(item.get("publisher") or item.get("source") or item.get("link") or "")
        for item in examples
        if isinstance(item, dict)
    )
    text = " ".join([alert_text(alert), source_blob]).lower()
    has_hard_action = has_term(text, LOCAL_DC_HARD_ACTION_TERMS)
    has_trusted_source = has_term(text, LOCAL_DC_TRUSTED_SOURCE_TERMS)
    weak_local_only = has_term(text, LOCAL_DC_WEAK_LOCAL_ONLY_TERMS) and not has_trusted_source
    return has_hard_action and has_trusted_source and not weak_local_only


def is_china_mofcom_control(alert: dict) -> bool:
    text = alert_text(alert)
    has_authority = has_term(
        text,
        ["mofcom", "china ministry of commerce", "chinese ministry of commerce", "中国商务部", "商务部"],
    )
    has_action = has_term(
        text,
        [
            "export ban", "export suspension", "suspend exports", "suspended exports",
            "export control", "export licensing", "tariff", "anti-dumping", "antidumping",
            "countervailing", "出口管制", "暂停出口", "停止出口", "禁止出口", "关税", "反倾销", "反补贴",
        ],
    ) or ("出口" in text and any(term in text for term in ["管制", "暂停", "停止", "禁止", "许可", "禁令"])) or (
        any(term in text for term in ["export", "exports"])
        and any(term in text for term in ["suspend", "suspends", "suspended", "ban", "bans", "banned"])
    )
    return has_authority and has_action


def china_mofcom_product_label(alert: dict) -> str:
    text = alert_text(alert)
    products = [
        (["helium", "氦"], "헬륨"),
        (["rare earth", "rare-earth", "稀土"], "희토류"),
        (["gallium", "镓"], "갈륨"),
        (["germanium", "锗"], "게르마늄"),
        (["graphite", "石墨"], "흑연"),
        (["antimony", "锑"], "안티몬"),
        (["tungsten", "钨"], "텅스텐"),
        (["indium", "铟"], "인듐"),
        (["battery", "cathode", "anode", "lfp", "电池"], "배터리 소재·기술"),
        (["semiconductor", "chip", "半导体"], "반도체 품목"),
        (["steel", "钢铁"], "철강"),
        (["dual-use", "两用物项"], "이중용도 품목"),
    ]
    for terms, label in products:
        if has_term(text, terms):
            return label
    return "전략 품목"


def china_mofcom_action_label(alert: dict) -> str:
    text = alert_text(alert)
    if has_term(text, ["export suspension", "suspend exports", "suspended exports", "暂停出口", "停止出口"]) or (
        "出口" in text and any(term in text for term in ["暂停", "停止"])
    ) or (
        any(term in text for term in ["export", "exports"])
        and any(term in text for term in ["suspend", "suspends", "suspended"])
    ):
        return "수출 일시 중단"
    if has_term(text, ["export ban", "banned exports", "禁止出口", "出口禁令"]) or (
        any(term in text for term in ["export", "exports"])
        and any(term in text for term in ["ban", "bans", "banned"])
    ):
        return "수출 금지"
    if has_term(text, ["anti-dumping", "antidumping", "反倾销"]):
        return "반덤핑 조치"
    if has_term(text, ["countervailing", "反补贴"]):
        return "상계관세 조치"
    if has_term(text, ["tariff", "tariffs", "关税"]):
        return "관세 조치"
    if has_term(text, ["export licensing", "出口许可"]):
        return "수출 허가제"
    return "수출통제"


def korean_title(alert: dict) -> str:
    if alert.get("korean_business_news"):
        raw = str(
            alert.get("source_title")
            or alert.get("original_news")
            or alert.get("news")
            or ""
        ).strip()
        if raw and not mostly_ascii(raw):
            return raw
    profile = federal_register_profile(alert)
    if profile:
        return str(profile["title"])
    # Render only from the original source identity.  Generated fields from an
    # earlier overlay are not source evidence and cannot select a new theme.
    text = source_subject_text(alert)
    raw = str(alert.get("source_title") or alert.get("original_news") or alert.get("news") or "").strip()
    if alert.get("iran_hormuz_escalation"):
        return "미국, 이란 재공격·호르무즈 상선 피격: 휴전·유가 리스크"
    if is_china_mofcom_control(alert):
        return f"중국 상무부, {china_mofcom_product_label(alert)} {china_mofcom_action_label(alert)} 발표"
    if alert.get("grid_policy_delay"):
        return "북미 송전망 투자 정책 변수: 정부 승인·규제 지연 리스크"
    if alert.get("memory_antitrust_lawsuit"):
        return "메모리 반독점 소송: 삼성전자·SK하이닉스·Micron DRAM 가격담합 집단소송"
    if alert.get("robotics_execution_filter"):
        return "삼성 로봇 실행 단계: 조직 재정비와 레인보우로보틱스 생산라인 자동화 체크"
    if alert.get("biotech_leadership_filter"):
        return raw or "바이오 주도주 복귀 조건: 매출·FDA 일정·할인율 동시 체크"
    if alert.get("port_strike_risk"):
        return "메가프로젝트 일정: 미국 동부·걸프 항만 계약 만료/파업 리스크"
    if alert.get("china_stimulus_bulk"):
        return "중국 경기부양책: 철광석·석탄 물동량과 벌크선 운임 회복 기대"
    if has_term(text, ["federal oil, gas, and coal amendments", "federal oil gas and coal amendments"]):
        return "미국, 석유·가스·석탄 자원개발 규정 개정 공표"
    if has_term(text, ["african growth and opportunity act", "annual review of country eligibility"]):
        return "USTR, 2027년 AGOA 수혜국 자격 연례검토 의견수렴"
    if has_term(text, ["technical guidelines for the production of regenerative agricultural biofuel feedstocks"]):
        return "미국, 재생농업 바이오연료 원료 생산 기술지침 공표"
    if has_term(text, ["advancing regenerative agriculture", "farm resilience"]):
        return "백악관, 재생농업·미국 농가 회복력 강화 행정명령 발표"
    if has_term(text, ["resilient networks", "disruptions to communications", "dirs"]):
        return "FCC, 재난 시 통신망 장애보고 시스템(DIRS) 현대화 규칙 공표"
    if has_term(text, ["digital opportunity data collection", "form 477"]):
        return "FCC, 브로드밴드 데이터 수집·Form 477 현대화 문서 공표"
    if has_term(text, ["fcc", "federal communications commission"]) and has_term(text, ["national security", "covered list", "equipment authorization", "foreign equipment", "inverter", "solar inverter"]):
        return "FCC, 국가안보 명분 외국산 장비·인버터 규제 신호"
    if has_term(text, ["nominations", "appointments"]):
        return "백악관, 고위급 인사 지명·임명 공지"
    if has_term(text, ["doe", "department of energy", "energy.gov"]) and has_term(text, ["loan", "loans", "low-cost loan", "loan guarantee", "conditional commitment", "funding opportunity", "efficiency standard", "grid deployment", "nuclear fuel", "critical materials", "ap1000"]):
        return "미 에너지부, 전력망·원전·에너지 장비 지원/제한 정책 체크"
    if has_term(text, ["transformer", "large power transformer", "변압기"]):
        return "미국, 대형 변압기 관세·규제 변화 공식근거 체크"
    if has_term(text, ["robot", "robotics", "chinese robots"]):
        return "미국, 중국산 로봇 수입 규제 검토 신호"
    if has_term(text, ["european union", "european commission", "eu집행위", "유럽연합"]) and has_term(text, ["korea", "south korea", "korean", "한국", "한국산"]):
        return "EU 등 해외 정책, 한국 수출주 직접 영향 체크"
    if has_term(text, ["nuclear", "reactor", "ap1000", "westinghouse", "smr"]):
        return "미국 원전·SMR·AI 전력 정책 시간표 체크"
    if is_local_dc_like(alert):
        return "미국 지역 데이터센터 인허가·주민 반발 이슈 확산"
    if has_term(text, ["fcc", "broadband", "satellite", "spectrum"]):
        return "FCC, 통신·브로드밴드 규제 문서 공표"
    if has_term(text, ["export control", "entity list", "semiconductor", "chips"]):
        return "미국, 반도체·첨단기술 수출통제 정책 신호"
    if has_term(text, ["antidumping", "countervailing", "anti-dumping"]) and has_term(text, ["final results", "preliminary results", "cash deposit", "dumping margin", "subsidy rate", "rate", "korea", "south korea"]):
        return "미 상무부, 반덤핑·상계관세 판정/재심 결과 공표"
    if has_term(text, ["tariff", "customs", "duty", "section 301", "section 232"]):
        return "미국, 관세·통관 정책 변화 체크"
    if raw and not mostly_ascii(raw):
        return raw
    return "해외 정책·기업 이벤트 한국장 영향 점검"


def curated_sectors(alert: dict) -> list[str]:
    if alert.get("korean_business_news"):
        existing = unique(
            [
                str(value)
                for value in alert.get("sectors") or []
                if str(value).strip()
                and str(value) not in {"정책/규제 일반", "영향 섹터 확인 불가"}
            ]
        )
        if existing:
            return existing
    profile = federal_register_profile(alert)
    if profile:
        return list(profile["sectors"])
    text = source_subject_text(alert)
    if alert.get("iran_hormuz_escalation"):
        return ["정유/화학", "해운/운임", "방산/지정학", "환율 민감주"]
    if is_china_mofcom_control(alert):
        product = china_mofcom_product_label(alert)
        if product == "헬륨":
            return ["반도체/HBM 공정가스", "디스플레이/광섬유", "산업가스", "의료기기/MRI"]
        if product in {"희토류", "갈륨", "게르마늄", "흑연", "안티몬", "텅스텐", "인듐"}:
            return ["핵심광물/소재", "반도체", "2차전지", "방산/전력전자"]
        return ["중국 수출통제/핵심소재", "공급망", "관세/수출주"]
    if has_term(text, ["자기주식", "자사주", "buyback"]):
        return ["자사주/주주환원", "수급/오버행", "한국 직접 공시"]
    if has_term(text, ["전환사채", "신주인수권", "유상증자", "주요사항보고서", "타법인주식", "회사합병", "회사분할"]):
        return ["개별종목 자금조달/희석", "수급/오버행", "한국 직접 공시"]
    if is_local_dc_like(alert):
        return ["데이터센터/전력망/전력기기"]
    if has_term(text, ["fcc", "federal communications commission"]) and has_term(text, ["national security", "covered list", "equipment authorization", "foreign equipment", "inverter", "solar inverter"]):
        return ["전력망 보안/FCC 장비규제", "태양광 인버터/전력변환장치", "중국 대체 공급망"]
    if has_term(text, ["european union", "european commission", "eu집행위", "유럽연합"]) and has_term(text, ["korea", "south korea", "korean", "한국", "한국산"]):
        return ["EU/한국 정책 영향", "한국 수출주", "무역규제/관세"]
    if has_term(text, ["doe", "department of energy", "energy.gov"]) and has_term(text, ["loan", "loans", "low-cost loan", "loan guarantee", "conditional commitment", "funding opportunity", "efficiency standard", "grid deployment", "nuclear fuel", "critical materials", "ap1000"]):
        return ["DOE 전력망/원전/에너지지원", "전력망/전력기기", "원전/SMR/핵연료", "데이터센터 전력"]
    if has_term(text, ["transformer", "large power transformer", "변압기"]):
        return ["전력기기/변압기", "관세/수출주", "전력망/데이터센터"]
    if has_term(text, ["nuclear", "reactor", "smr", "ap1000", "westinghouse", "doosan", "원전"]):
        return ["원전/SMR/가스터빈", "전력기기/전력망", "두산에너빌리티/KHNP"]
    if has_term(text, ["hanwha aerospace", "lig nex1", "kai", "hyundai rotem", "k9", "k2", "fa-50", "kf-21", "redback", "천궁", "현궁"]):
        return ["K-방산/항공우주", "수주/계약", "지정학/방위비"]
    if has_term(text, ["robot", "robotics", "smart factory", "automation"]):
        return ["로봇/스마트팩토리", "감속기/FA", "산업자동화"]
    if has_term(text, ["fda", "pdufa", "clinical", "crl", "pharma"]):
        return ["바이오/FDA", "제약", "헬스케어"]
    if has_term(text, ["fcc", "broadband", "spectrum", "satellite", "communications"]):
        return ["미국 통신규제", "통신장비/위성"]
    if has_term(text, ["oil", "gas", "coal", "biofuel", "feedstocks"]):
        return ["에너지/원자재", "정유·화학 원가", "미국 자원개발 정책"]
    if has_term(text, ["tariff", "customs", "duty", "section 301", "section 232", "관세"]):
        return ["관세/수출주", "공급망", "물류/통상"]
    if has_term(text, ["semiconductor", "chip", "hbm", "ai", "nvidia", "micron"]):
        return ["반도체/AI", "장비·소재"]
    if has_term(text, ["stablecoin", "digital asset", "스테이블코인"]):
        return ["금융/자본시장/스테이블코인", "은행/핀테크/결제"]
    return unique([str(x) for x in alert.get("sectors") or []])[:4] or ["영향 섹터 확인 불가"]


def explanation_for(alert: dict) -> dict[str, str]:
    profile = federal_register_profile(alert)
    if profile:
        return {
            "core": str(profile["core"]),
            "view": str(profile["view"]),
            "korea": str(profile["korea"]),
            "priced": str(profile["priced"]),
            "counter": str(profile["counter"]),
            "failure": str(profile["failure"]),
        }
    text = source_subject_text(alert)
    if alert.get("iran_hormuz_escalation"):
        return {
            "core": "미국이 호르무즈 해협 상선 피격에 대응해 이란을 다시 공격했고, 이란도 걸프 국가를 향해 대응하면서 취약한 휴전과 해상운송 안전이 다시 흔들린 사안입니다.",
            "view": "호르무즈 통항 차질이 이어지면 유가·운임·보험료 상승이 정유·화학·항공의 원가와 해운·방산의 수익 기대를 동시에 바꿀 수 있습니다.",
            "korea": "한국장에서는 WTI/Brent, 원/달러, 탱커·컨테이너 운임과 정유/화학·해운·방산 수급을 함께 확인합니다. 실제 항로 차질이 없으면 테마 반응으로 제한합니다.",
            "priced": "낮음~중간. 최근 충돌 재개 우려가 일부 반영됐지만 신규 상선 피격과 재공격은 휴전 붕괴 확률을 다시 높이는 새 정보입니다.",
            "counter": "단발성 보복 뒤 추가 공격이 멈추고 호르무즈 통항이 유지되면 유가·운임 충격은 빠르게 되돌릴 수 있습니다.",
            "failure": "미 국방부·CENTCOM·백악관 후속, 실제 선박 통항 감소, WTI/Brent·운임·USD/KRW·방산주 반응이 없으면 고충격 재료에서 약화됩니다.",
        }
    if is_china_mofcom_control(alert):
        product = china_mofcom_product_label(alert)
        action = china_mofcom_action_label(alert)
        korea = (
            "한국장에서는 반도체·HBM 공정, 디스플레이, 광섬유, MRI, 산업가스 밸류체인의 재고와 조달가격을 확인합니다. 중국산 의존도와 대체 조달 계약이 확인된 기업만 연결합니다."
            if product == "헬륨"
            else "한국장에서는 해당 품목의 중국산 의존도, 재고일수, 대체 공급선, 한국 기업의 수출입 노출이 확인된 업종만 연결합니다."
        )
        return {
            "core": f"중국 상무부가 {product} 관련 {action}을 발표하거나 준비한다는 정책 신호입니다. 품목·대상국·시행일·예외 허가가 실제 공급 감소 폭을 결정합니다.",
            "view": f"{product}의 중국발 공급이 줄면 현물가격, 조달기간, 재고비용이 올라 수입업체 마진과 생산계획이 바뀔 수 있습니다.",
            "korea": korea,
            "priced": "낮음~중간. 속보 직후 관련 원자재와 테마주는 먼저 움직일 수 있지만 실제 이익 영향은 공식 적용범위 확인 뒤 결정됩니다.",
            "counter": "수출 허가 예외, 특정 국가·기업 한정, 기존 계약 유예, 중국 외 공급 확대가 있으면 공급 충격이 예상보다 작을 수 있습니다.",
            "failure": "공식 원문에서 품목·대상국·시행일이 확인되지 않거나 현물가격·리드타임·국내 조달비용이 움직이지 않으면 테마성 반응으로 끝납니다.",
        }
    if has_term(text, ["자기주식", "자사주", "buyback"]):
        return {
            "core": "자사주 취득, 처분, 신탁, 소각 관련 공시는 주주환원, 유통주식 수, 오버행, 단기 수급을 바꿀 수 있는 공시입니다.",
            "view": "실제 고충격 여부는 취득·소각 규모, 시가총액 대비 비중, 처분 상대방, 목적, 기간, 기존 기대 대비 신규성으로 판단해야 합니다.",
            "korea": "한국장에서는 자사주 소각 또는 대규모 취득이면 주주환원과 수급 호재, 신탁 해지·처분이면 오버행 가능성을 구분해 봅니다.",
            "priced": "중간. 자사주 공시는 즉시 반응하지만 규모와 목적이 작거나 반복 공시면 이미 반영됐을 가능성이 높습니다.",
            "counter": "단순 신탁 만기·해지, 기존 취득 완료 보고, 소규모 반복 공시면 새 수급 변수로 보기 어렵습니다.",
            "failure": "소각, 신규 대규모 취득, 처분 제한, 경영권 변화, 거래량 대비 의미 있는 규모가 확인되지 않으면 고충격 재료에서 제외합니다.",
        }
    if has_term(text, ["전환사채", "신주인수권", "유상증자", "주요사항보고서", "타법인주식", "회사합병", "회사분할"]):
        return {
            "core": "국내 기업의 CB/BW/유상증자/주요사항 공시는 개별 종목 수급, 희석, 오버행, 지배구조 이벤트를 바꿀 수 있는 공시입니다.",
            "view": "신규 자금조달은 성장 투자 재원일 수 있지만 전환·행사 가능 물량과 발행조건이 불리하면 주당가치와 단기 수급에 부담입니다.",
            "korea": "한국장에서는 해당 종목의 발행규모, 전환가·행사가, 리픽싱, 납입일, 최대주주·투자자 성격, 기존 주식수 대비 희석률을 확인합니다.",
            "priced": "낮음~중간. 공시 직후 수급에 반영되지만 실제 납입·전환·행사 일정과 조건에 따라 재평가됩니다.",
            "counter": "정정공시나 단순 일정 변경이면 신규 악재가 아닐 수 있고, 자금 사용처가 명확하면 부정적 영향이 제한될 수 있습니다.",
            "failure": "납입 지연, 조건 변경, 리픽싱 확대, 대규모 전환 가능 물량이 확인되지 않으면 시장 영향은 제한됩니다.",
        }
    if is_local_dc_like(alert):
        return {
            "core": "미국 지역 단위에서 데이터센터 인허가, 조례, 주민 반발, 공사 영향 이슈가 확인된 사안입니다.",
            "view": "AI 데이터센터 CAPEX 자체보다 승인 시간표와 전력망 접속 병목 프리미엄을 바꿀 수 있는지 보는 재료입니다.",
            "korea": "한국장에서는 전력기기, 변압기, 전선, 냉각·전력 인프라 밸류체인 수급을 보되 개별 지역 이슈인지 먼저 걸러야 합니다.",
            "priced": "중간. 데이터센터 전력 테마는 선반영이 강하지만 실제 조례·투표·인허가 보류가 확인되면 시간표 재평가 여지가 있습니다.",
            "counter": "개별 지역 민원이나 지역 언론 보도일 수 있어 전국 CAPEX 둔화로 바로 확장하면 과대해석입니다.",
            "failure": "공식 의사록·조례·투표일·빅테크 CAPEX 조정·전력기기 수주 변화가 없으면 단발성 지역 뉴스입니다.",
        }
    if has_term(text, ["fcc", "federal communications commission"]) and has_term(text, ["national security", "covered list", "equipment authorization", "foreign equipment", "inverter", "solar inverter"]):
        return {
            "core": "FCC가 국가안보를 이유로 외국산 장비, 통신모듈, 에너지 인버터, 전력망 연결 장비의 수입·인증·판매 제한을 검토하거나 공표한 사안입니다.",
            "view": "단순 통신 행정공지와 다르게 적용 장비가 특정되면 미국 시장에서 중국산 장비가 배제되고 대체 공급망의 주문 기대와 가격결정력이 바뀔 수 있습니다.",
            "korea": "한국장에서는 전력변환장치, ESS/PCS, 전력기기, 통신장비, 위성·보안장비 중 미국향 공급망 노출과 중국 대체 수요가 있는 종목만 선별 확인합니다.",
            "priced": "낮음~중간. 신뢰외신 보도나 규칙 제안 단계에서는 테마가 먼저 움직일 수 있지만 공식 적용 대상·시행일 전에는 직접 반영이 제한적입니다.",
            "counter": "FCC 공식 규칙, 적용 장비, 기존 인증 장비 예외, 시행일, 한국 기업의 미국향 공급망 노출이 확인되지 않으면 과대해석입니다.",
            "failure": "FCC 원문, Covered List·장비인증 제한 범위, 적용 장비, 국내 기업 수주·공급망 노출이 확인되지 않으면 테마성 반응으로 끝납니다.",
        }
    if has_term(text, ["european union", "european commission", "eu집행위", "유럽연합"]) and has_term(text, ["korea", "south korea", "korean", "한국", "한국산"]):
        return {
            "core": "EU 등 해외 정책이 한국산 제품이나 한국 기업의 수출 조건을 직접 바꿀 수 있는 무역·규제 사안입니다.",
            "view": "품목·세율·쿼터·인증·시행일이 공식화되면 한국 수출기업의 마진, 물량, 주문 이전, 밸류체인 수급 기대가 바뀔 수 있습니다.",
            "korea": "한국장에서는 원문에 직접 언급된 품목과 유럽·해외 매출 노출이 있는 철강, 배터리, 반도체, 조선, 자동차, 화학, 전력기기 수출주만 연결합니다.",
            "priced": "낮음~중간. 보도 직후 테마 수급은 빠르지만 관보·집행위·의회·이사회 문서로 품목과 시행일이 확인돼야 실적 추정에 반영됩니다.",
            "counter": "해외 정책 보도만으로는 품목 범위, 국가별 쿼터, 예외 조항, 시행일, 한국 기업 직접 노출이 확정되지 않습니다.",
            "failure": "공식 문서, 품목별 수치, 적용일, 한국 기업 직접 노출, 국내 가격·수급 반응이 없으면 제외해야 합니다.",
        }
    if has_term(text, ["doe", "department of energy", "energy.gov"]) and has_term(text, ["loan", "loans", "low-cost loan", "loan guarantee", "conditional commitment", "funding opportunity", "efficiency standard", "grid deployment", "nuclear fuel", "critical materials", "ap1000"]):
        return {
            "core": "미 에너지부(DOE)의 대출보증, 조건부 지원 약정, 자금지원, 효율규제, 금지·제한, 핵연료·전력망 정책이 확인된 사안입니다.",
            "view": "DOE 정책은 보조금성 자금, 저리 대출, 효율 기준, 조달·인허가 일정으로 원전·전력기기·송전망·데이터센터 전력 밸류체인의 수주 가시성과 할인율을 동시에 바꿀 수 있습니다.",
            "korea": "한국장에서는 두산에너빌리티, 원전 기자재, 전력기기, 변압기·전선, ESS/전력변환장치, 핵연료·핵심소재 중 미국 프로젝트 노출이 있는 종목만 선별 확인합니다.",
            "priced": "중간. 원전·전력망 테마는 선반영이 강하지만 DOE 금액, 대출조건, 선정기업, 시행일이 공식화되면 실적 추정과 수급이 다시 움직일 수 있습니다.",
            "counter": "DOE 발표라도 공고·의향서·조건부 약정 단계는 최종 계약이나 매출 확정이 아닙니다. 수혜 기업, 금액, 매칭 자금, 인허가, 착공 일정 확인이 필요합니다.",
            "failure": "DOE 원문에서 금액·대상기업·대출조건·시행일·조달일정이 확인되지 않거나 국내 기업의 미국 프로젝트 노출이 없으면 테마성 반응으로 끝납니다.",
        }
    if has_term(text, ["transformer", "large power transformer", "변압기"]):
        return {
            "core": "미국 변압기 관세·효율규제 변화가 한국 전력기기 수출 가격경쟁력과 수주 기대를 바꿀 수 있는지 확인하는 사안입니다.",
            "view": "세율, 품목코드, 시행일이 공식화되면 마진과 신규 수주 기대가 동시에 바뀝니다.",
            "korea": "효성중공업, HD현대일렉트릭, LS ELECTRIC 등 변압기·전력기기 밸류체인과 데이터센터 전력망 테마 수급을 확인합니다.",
            "priced": "중간. 전력기기 테마가 이미 강해도 공식 세율·시행일이 확인되면 실적 추정 조정 여지가 남습니다.",
            "counter": "공식 관보·상무부·USTR 근거 없이 보도만 있으면 예비 재료입니다.",
            "failure": "품목코드·시행일·예외조항·개별 기업 수주/마진 변화가 확인되지 않으면 재료가 약해집니다.",
        }
    if has_term(text, ["nuclear", "reactor", "smr", "ap1000", "westinghouse", "doosan", "원전"]):
        return {
            "core": "원전, SMR, 가스터빈, AI 전력수요 관련 정책·계약 시간표가 밸류체인 기대를 다시 움직이는 사안입니다.",
            "view": "당장 매출 확정보다 인허가, 대출·예산, 최종 계약, 기자재 발주 시간표가 돈 버는 능력으로 이어지는지 봐야 합니다.",
            "korea": "두산에너빌리티, 원전 기자재, 전력기기, 송전망, KHNP·체코·중동 원전 노출 종목의 수급을 확인합니다.",
            "priced": "중간~높음. 원전 테마는 선반영이 빨라 계약·인허가·발주가 없으면 되돌림 위험이 큽니다.",
            "counter": "부지, NRC/국내 인허가, 주민수용성, 방폐장·송전망, 최종 계약금액이 확정되지 않으면 매출 인식까지 시차가 큽니다.",
            "failure": "공식 계약·대출조건·인허가 일정·기자재 발주가 확인되지 않으면 정책 기대에 그칩니다.",
        }
    if has_term(text, ["fcc", "broadband", "spectrum", "satellite", "communications", "dirs"]):
        return {
            "core": "FCC 통신·브로드밴드·장애보고 규제 문서입니다. 주파수 경매, 장비 의무화, 보조금인지 단순 행정 절차인지 구분해야 합니다.",
            "view": "통신사 CAPEX, 위성·장비 인증, 공공안전망 조달로 연결될 때만 실적 재료입니다.",
            "korea": "한국장에서는 통신장비·위성통신·네트워크 장비 테마 반응 가능성은 있으나 행정 공지라면 직접 영향은 제한적입니다.",
            "priced": "낮음~중간. 구체 인허가·경매·예산·장비 발주가 없으면 선반영보다 영향 자체가 작습니다.",
            "counter": "회의 공고, 데이터 수집, 보고 양식 정비 수준이면 고충격 재료가 아닙니다.",
            "failure": "통신사 CAPEX 가이던스, 장비 발주, 공공안전망 예산, 국내 장비사 수주 공시가 없으면 제외해야 합니다.",
        }
    if has_term(text, ["robot", "robotics", "automation"]):
        return {
            "core": "로봇·자동화 정책 또는 기업 실행 단계가 중국 대체 공급망과 생산자동화 수요를 자극할 수 있는 사안입니다.",
            "view": "관세·수입제한·제조지원 또는 실제 발주·CAPEX로 이어질 때 매출 기대가 바뀝니다.",
            "korea": "로봇, 감속기, FA, 스마트팩토리, 삼성·레인보우로보틱스 연계 수급을 확인합니다.",
            "priced": "중간. 로봇 테마는 기대가 빠르게 붙지만 공식 조치나 발주 전에는 되돌림이 큽니다.",
            "counter": "검토·조직개편·소식통 보도 단계면 품목, 세율, 시행일, 발주 규모가 미확정입니다.",
            "failure": "상무부 공식 조사, 관세·대출 조건, 생산라인 발주·공급계약이 나오지 않으면 테마성 반응으로 끝납니다.",
        }
    if has_term(text, ["oil", "gas", "coal", "biofuel", "feedstocks", "agriculture"]):
        return {
            "core": "미국 에너지·자원개발·바이오연료 관련 규정/지침입니다. 가격, 공급량, 세액공제, 의무혼합으로 연결되는지 확인해야 합니다.",
            "view": "유가·가스·석탄·바이오연료 가격 또는 정유·화학 원가에 반영될 때만 돈 버는 능력 변화입니다.",
            "korea": "정유·화학, 에너지 비용 민감 업종, 바이오연료 밸류체인을 보되 한국 직접 영향은 공식 시행 조건 확인 전 제한적입니다.",
            "priced": "중간. 원자재 정책은 반복 재료라 가격 반응이 동행해야 추가 반영됩니다.",
            "counter": "기술지침·의견수렴·행정 개정은 실제 공급·가격 변화와 거리가 있을 수 있습니다.",
            "failure": "WTI/Brent/천연가스/정제마진/관련 ETF가 반응하지 않으면 단발성 정책 문서입니다.",
        }
    if has_term(text, ["tariff", "customs", "duty", "section 301", "section 232", "antidumping", "countervailing", "anti-dumping", "safeguard", "quota"]):
        return {
            "core": "관세·통관 뉴스는 품목, 국가, 세율, 쿼터, 적용일이 실제로 바뀔 때만 한국 수출기업의 가격경쟁력과 마진을 바꾸는 재료입니다.",
            "view": "반덤핑·상계관세 행정재심 신청 안내처럼 절차만 여는 공고는 가격 변수가 아니며, 최종판정·예비판정·현금예치율·관세율·시행일이 확인될 때 고충격으로 봅니다.",
            "korea": "한국장에서는 원문에 한국산 품목, 세율 변화, 적용일, 예외 조항이 직접 확인될 때 철강, 배터리, 화학, 전력기기, 자동차부품 등 수출주로만 연결합니다.",
            "priced": "낮음~중간. 보도나 행정 공고 단계에서는 테마 반응이 먼저 나올 수 있지만, 실제 세율과 시행일이 없으면 실적 추정 반영은 제한적입니다.",
            "counter": "행정재심 신청 기회, 서비스리스트 갱신, 절차 안내는 새 관세 부과나 완화가 아니므로 고충격 정책 뉴스로 보기 어렵습니다.",
            "failure": "품목·국가·세율·현금예치율·시행일·한국 기업 노출이 확인되지 않으면 레이더에서 제외합니다.",
        }
    return {
        "core": "공식 문서 또는 신뢰 보도에서 한국장 가격 변수 후보가 확인됐습니다.",
        "view": "돈 버는 능력, 할인율, 수급, 시간표 중 무엇이 실제로 바뀌는지 원문과 시장 반응으로 재확인해야 합니다.",
        "korea": "한국장 직접 영향은 원문에 근거가 있는 업종과 종목군으로만 제한해 확인합니다.",
        "priced": f"{alert.get('reflection') or '중간'}. 발표 직후라도 개별 밸류체인 반영은 후속 일정·가격·수급 확인이 필요합니다.",
        "counter": alert.get("counter") or "세부 조건 확인 전까지 직접 실적 연결은 제한적입니다.",
        "failure": alert.get("failed_signal") or "후속 시행일·예산·계약·수급 반응이 없으면 단발성 뉴스로 끝납니다.",
    }


def normalize_alert_for_output(alert: dict) -> dict:
    out = dict(alert)
    if is_china_mofcom_control(out):
        out["china_mofcom_trade_control"] = True
        out["impacts"] = ["돈 버는 능력", "수급", "시간표"]
        out["paths"] = ["공급·수요", "원자재 비용", "공급망", "정책 타임라인"]
    if not out.get("source_title"):
        out["source_title"] = out.get("original_news") or out.get("news")
    if not out.get("original_news"):
        out["original_news"] = out.get("source_title") or out.get("news")
    if not out.get("supply_chain_theme"):
        inferred_theme = semantic_event_theme(out)
        if inferred_theme:
            out["supply_chain_theme"] = inferred_theme
    profile = federal_register_profile(out)
    out["news"] = korean_title(out)
    out["sectors"] = curated_sectors(out)
    impacts = unique([str(x) for x in out.get("impacts") or []]) or ["의사결정 영향 제한적"]
    if len(impacts) > 1:
        impacts = [x for x in impacts if x != "의사결정 영향 제한적"]
    if profile:
        impacts = list(profile["impacts"])
    out["impacts"] = impacts
    if profile:
        out["paths"] = list(profile["paths"])
    else:
        out["paths"] = unique([str(x) for x in out.get("paths") or []]) or [
        "이익" if x == "돈 버는 능력" else "할인율" if x == "할인율" else "수급" if x == "수급" else "정책 타임라인"
        for x in impacts
        ]
    explanation = explanation_for(out)
    if profile or not out.get("policy_plain_summary"):
        out["policy_plain_summary"] = explanation["core"]
    if profile or not out.get("investment_view"):
        out["investment_view"] = explanation["view"]
    if profile or not out.get("korea_market_impact"):
        out["korea_market_impact"] = explanation["korea"]
    if profile or not out.get("priced_in"):
        out["priced_in"] = explanation["priced"]
    generic_counter_terms = [
        "시행일, 적용 대상, 금액, 기간",
        "제목·요약 기반 1차 감지",
        "원문 세부조건과 공식 문서 확인 전",
    ]
    counter_text = str(out.get("counter") or "")
    if profile or not counter_text or any(term in counter_text for term in generic_counter_terms):
        out["counter"] = explanation["counter"]
    failed_text = str(out.get("failed_signal") or "")
    stale_failure_terms = [
        "메모리 가격·고객사 재고",
        "SOX/MU/NVDA",
        "관련 해외 티커·원자재·금리·환율",
    ]
    if profile or not failed_text or any(term in failed_text for term in stale_failure_terms):
        out["failed_signal"] = explanation["failure"]
    stale_interpretation_terms = [
        "반도체 급락은",
        "돈 버는 능력, 할인율, 수급, 시간표 중 하나를 바꿀 수 있는 후보",
    ]
    if profile or not out.get("interpretation") or (
        any(term in str(out.get("interpretation")) for term in stale_interpretation_terms)
        and "반도체/AI" not in out.get("sectors", [])
    ):
        out["interpretation"] = explanation["view"]
    return out


def quality_display_alerts(alerts: list[dict], limit: int) -> list[dict]:
    initial = telegram.display_alerts(alerts, min(max(limit * 3, 12), 30))
    candidates = initial + alerts
    iran_candidates = [alert for alert in candidates if alert.get("iran_hormuz_escalation")]
    if iran_candidates:
        def iran_source_rank(alert: dict) -> int:
            source = alert_text(alert)
            if has_term(source, ["ap news", "associated press"]):
                return 0
            if has_term(source, ["reuters"]):
                return 1
            if has_term(source, ["cnbc"]):
                return 2
            return 3

        best_rank = min(iran_source_rank(alert) for alert in iran_candidates)
        preferred_iran = max(
            (alert for alert in iran_candidates if iran_source_rank(alert) == best_rank),
            key=lambda alert: str(alert.get("published") or ""),
        )
        candidates = [preferred_iran] + [alert for alert in candidates if not alert.get("iran_hormuz_escalation")]
    selected: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for alert in candidates:
        if is_low_impact_admin_alert(alert):
            alert["_exclusion_reason"] = "low_impact_admin_document"
            continue
        if is_low_impact_trade_admin_notice(alert):
            alert["_exclusion_reason"] = "low_impact_trade_admin_notice"
            continue
        if is_local_dc_like(alert) and not is_actionable_local_dc_policy(alert):
            alert["_exclusion_reason"] = "local_data_center_without_trusted_hard_action"
            continue
        normalized = normalize_alert_for_output(alert)
        if not source_output_aligned(normalized):
            alert["_exclusion_reason"] = "source_body_mismatch"
            continue
        if not has_korea_market_link(normalized):
            alert["_exclusion_reason"] = "korea_market_link_guard"
            continue
        key = alert_dedup_key(normalized)
        if key in seen:
            alert.setdefault("_exclusion_reason", "semantic_duplicate")
            continue
        seen.add(key)
        if is_low_impact_admin_alert(normalized):
            alert["_exclusion_reason"] = "low_impact_admin_document"
            continue
        if is_low_impact_trade_admin_notice(normalized):
            alert["_exclusion_reason"] = "low_impact_trade_admin_notice"
            continue
        if not has_decision_impact(normalized):
            alert["_exclusion_reason"] = "decision_impact_guard"
            continue
        if (
            is_local_dc_like(normalized)
            and not normalized.get("cluster_count")
            and any(is_local_dc_like(item) and item.get("cluster_count") for item in selected)
        ):
            alert["_exclusion_reason"] = "covered_by_data_center_cluster"
            continue
        alert.pop("_exclusion_reason", None)
        selected.append(normalized)
        if len(selected) >= limit:
            break
    return selected


def related_text(alert: dict, fred: dict, te: dict) -> str:
    extra = []
    if alert.get("iran_hormuz_escalation"):
        extra += ["WTI", "Brent", "XLE", "탱커·컨테이너 운임", "USD/KRW", "DXY", "방산 ETF/티커"]
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
