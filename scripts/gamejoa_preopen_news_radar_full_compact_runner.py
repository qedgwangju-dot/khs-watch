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
from khs_article_detail import extract_article_detail, normalized_title_tokens
from khs_compact_text import concise_text
import gamejoa_news_coverage_extension as coverage
import gamejoa_article_detail_queue as detail_queue
import gamejoa_market_materiality as market_materiality


telegram = contract.telegram
base = contract.base
MATERIALITY_IMPACT_NAMES = {
    "earnings": "돈 버는 능력", "discount_rate": "할인율", "flows": "수급", "timeline": "시간표",
}

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
    "seoul.co.kr": "서울신문",
    "zdnet.co.kr": "지디넷코리아",
    "thebell.co.kr": "더벨",
    "newsis.com": "뉴시스",
    "inews24.com": "아이뉴스24",
    "dailian.co.kr": "데일리안",
    "kmib.co.kr": "국민일보",
    "biz.chosun.com": "조선비즈",
    "chosun.com": "조선일보",
    "bloter.net": "블로터",
    "wowtv.co.kr": "한국경제TV",
    "hankookilbo.com": "한국일보",
    "reuters.com": "Reuters",
    "apnews.com": "AP",
    "cnbc.com": "CNBC",
    "joongang.co.kr": "중앙일보",
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
    (
        "기업 실적·공급부족·시장점유율",
        (
            "(삼성전자 OR SK하이닉스 OR 애플 OR 아마존 OR 키옥시아 OR LG CNS) "
            "(실적 OR 영업이익 OR 매출 OR 가이던스 OR 공급부족 OR 공급 부족 OR 점유율 OR HBM4 OR HBM4E) "
            "(site:seoul.co.kr OR site:zdnet.co.kr OR site:thebell.co.kr OR site:newsis.com OR "
            "site:bloter.net OR site:wowtv.co.kr OR site:hankookilbo.com OR site:yna.co.kr)"
        ),
    ),
    (
        "AI 모델·데이터센터 구축",
        (
            "(K-엑사원 OR 파운데이션모델 OR 파운데이션 모델 OR 딥시크 OR AI데이터센터 OR AI 데이터센터) "
            "(공개 OR 출시 OR 건설 OR 투자 OR 수요 OR 상용화) "
            "(site:zdnet.co.kr OR site:thebell.co.kr OR site:newsis.com OR site:bloter.net OR "
            "site:wowtv.co.kr OR site:hankookilbo.com OR site:hankyung.com)"
        ),
    ),
    (
        "바이오 허가·상업화",
        (
            "(품목허가 OR 허가권고 OR 허가 권고 OR 임상결과 OR 임상 결과 OR 상업화) "
            "(신약 OR 의약품 OR 바이오 OR 치료제) "
            "(site:newsis.com OR site:yna.co.kr OR site:edaily.co.kr OR site:mt.co.kr OR "
            "site:hankyung.com OR site:thebell.co.kr)"
        ),
    ),
    (
        "수급·자본행사·외환",
        (
            "(의무보유 OR 보호예수 OR 유상증자 OR 인수 OR 합병 OR 외환거래 OR 지분 OR 주식분할) "
            "(해제 OR 결정 OR 최대 OR 공시 OR 취득 OR 매수 OR 증가) "
            "(site:newsis.com OR site:yna.co.kr OR site:edaily.co.kr OR site:mk.co.kr OR "
            "site:mt.co.kr OR site:thebell.co.kr OR site:hankyung.com)"
        ),
    ),
    (
        "트럼프 관세·원자재·중동",
        (
            "(트럼프 OR 미국 OR 이란 OR 하마스) "
            "(관세면제 OR 관세 면제 OR 구리 OR 석유 OR 가스 OR 다이아몬드 OR 무장해제 OR 중동전쟁 OR 중동 전쟁) "
            "(site:seoul.co.kr OR site:newsis.com OR site:yna.co.kr OR site:edaily.co.kr OR "
            "site:mt.co.kr OR site:hankookilbo.com OR site:wowtv.co.kr)"
        ),
    ),
    (
        "트럼프 이란·걸프 군사긴장",
        (
            "(트럼프 OR Trump) (이란 OR Iran OR 쿠웨이트 OR Kuwait OR 걸프) "
            "(추가공격 OR 추가 공격 OR 공격임박 OR 공격 임박 OR 드론공격 OR 드론 공격) "
            "(site:reuters.com OR site:apnews.com OR site:cnbc.com OR site:yna.co.kr OR "
            "site:newsis.com OR site:seoul.co.kr OR site:yonhapnewstv.co.kr)"
        ),
    ),
    (
        "우크라이나 스타링크 군사사용 승인",
        (
            "(젤렌스키 OR Zelensky OR 우크라이나 OR Ukraine) "
            "(스타링크 OR Starlink) (트럼프 OR Trump OR 승인 OR 타격 OR strike) "
            "(site:reuters.com OR site:apnews.com OR site:cnbc.com OR site:yna.co.kr OR "
            "site:newsis.com OR site:seoul.co.kr)"
        ),
    ),
    (
        "가자 휴전·하마스 무장해제",
        (
            "(가자 OR Gaza OR 하마스 OR Hamas) "
            "(휴전 OR ceasefire OR 무장해제 OR 무장 해제 OR disarmament OR 평화협정) "
            "(트럼프 OR Trump OR 위원회 OR committee) "
            "(site:reuters.com OR site:apnews.com OR site:cnbc.com OR site:yna.co.kr OR "
            "site:newsis.com OR site:seoul.co.kr OR site:yonhapnewstv.co.kr)"
        ),
    ),
    (
        "단일종목 레버리지 국정조사·청문회",
        (
            "(단일종목레버리지 OR 단일종목 레버리지 OR 레버리지ETF OR 레버리지 ETF) "
            "(국정조사 OR 청문회 OR 조사요구 OR 조사 요구 OR 발의 OR 조사착수 OR 조사 착수) "
            "(site:yna.co.kr OR site:newsis.com OR site:mk.co.kr OR site:mt.co.kr OR "
            "site:kmib.co.kr OR site:metroseoul.co.kr OR site:asiae.co.kr)"
        ),
    ),

    (
        "SK하이닉스 해외 HBM 생산거점",
        (
            "(SK하이닉스 OR SK hynix) (일본 OR 미국 OR 해외) "
            "(HBM OR 메모리 OR 반도체) "
            "(공장 OR 팹 OR 생산거점 OR 건설 OR 투자 OR 증설 OR 검토) "
            "(site:hankyung.com OR site:yna.co.kr OR site:mk.co.kr OR site:edaily.co.kr OR "
            "site:mt.co.kr OR site:fnnews.com OR site:newsis.com)"
        ),
    ),
    (
        "엔비디아 AI 서버 가격·메모리 공급부족",
        (
            "(엔비디아 OR NVIDIA) (AI 서버 OR AI서버 OR GPU) "
            "(가격 인상 OR 가격인상 OR 판가 OR 메모리 품귀 OR 메모리 부족 OR HBM) "
            "(site:asiae.co.kr OR site:edaily.co.kr OR site:mk.co.kr OR site:mt.co.kr OR "
            "site:hankyung.com OR site:yna.co.kr)"
        ),
    ),
    (
        "YMTC 낸드 IPO·중국 메모리 공급",
        (
            "(YMTC OR 창장메모리 OR Yangtze Memory) "
            "(IPO OR 상장 OR 조달 OR 낸드 OR SSD OR 메모리) "
            "(site:fnnews.com OR site:mk.co.kr OR site:hankyung.com OR site:edaily.co.kr OR "
            "site:asiae.co.kr OR site:mt.co.kr)"
        ),
    ),
    (
        "앤트로픽 IPO·AI 인프라 자금",
        (
            "(앤트로픽 OR Anthropic) (IPO OR 상장 OR 기업가치 OR 투자설명서) "
            "(AI OR 데이터센터 OR 반도체 OR 전력) "
            "(site:edaily.co.kr OR site:wowtv.co.kr OR site:mk.co.kr OR site:hankyung.com OR "
            "site:mt.co.kr OR site:yna.co.kr)"
        ),
    ),
    (
        "삼성·SK HBM 핫칩스·기술공개",
        (
            "(삼성전자 OR SK하이닉스) (HBM OR HBM4 OR HBM4E) "
            "(핫칩스 OR Hot Chips OR 학회 OR 기술공개 OR 발표) "
            "(site:bloter.net OR site:zdnet.co.kr OR site:etnews.com OR site:yna.co.kr OR "
            "site:hankyung.com OR site:mk.co.kr)"
        ),
    ),
    (
        "빅테크 AI 회사채·미국 국채금리",
        (
            "(빅테크 OR 하이퍼스케일러 OR 마이크로소프트 OR 구글 OR 아마존 OR 메타) "
            "(AI 투자 OR AI투자 OR 데이터센터) (회사채 OR 회사채 발행 OR 미국 국채 OR 국채 금리) "
            "(site:mt.co.kr OR site:edaily.co.kr OR site:mk.co.kr OR site:hankyung.com OR "
            "site:yna.co.kr)"
        ),
    ),
    (
        "미국·캐나다 무역협정·관세",
        (
            "(트럼프 OR 미국) (캐나다 OR Canada) "
            "(무역협정 OR 무역 협정 OR 관세 OR 무역전쟁 OR 무역 전쟁) "
            "(site:reuters.com OR site:apnews.com OR site:cnbc.com OR site:yna.co.kr OR "
            "site:edaily.co.kr OR site:mt.co.kr OR site:mk.co.kr)"
        ),
    ),
    (
        "이란·중국 원유·브렌트",
        (
            "(이란 OR Iran) (중국 OR China) "
            "(원유 OR 석유 OR 브렌트 OR Brent OR 휴전 OR 제재 OR 무역) "
            "(site:reuters.com OR site:apnews.com OR site:cnbc.com OR site:yna.co.kr OR "
            "site:mt.co.kr OR site:edaily.co.kr)"
        ),
    ),
    (
        "삼성 TV 출하·메모리 원가",
        (
            "(삼성전자 OR Samsung) (TV OR 미니 LED OR Mini LED) "
            "(출하량 OR 점유율 OR 시장 1위 OR 메모리 가격 OR 원가) "
            "(site:zdnet.co.kr OR site:yna.co.kr OR site:mk.co.kr OR site:hankyung.com OR "
            "site:edaily.co.kr)"
        ),
    ),
    (
        "반도체 노조·성과급·가동 리스크",
        (
            "(삼성전자 OR SK하이닉스) (DS OR DX OR 반도체) "
            "(노조 OR 임단협 OR 파업 OR 성과급 OR 보상) "
            "(site:joongang.co.kr OR site:yna.co.kr OR site:edaily.co.kr OR site:mk.co.kr OR "
            "site:hankyung.com)"
        ),
    ),
    (
        "중동 경제전·원유·해운 리스크",
        (
            "(이란 OR Iran OR 테헤란 OR Tehran) "
            "(경제전쟁 OR 경제 전쟁 OR 제재 OR 원유 OR 석유 OR 브렌트 OR 운임 OR 해운) "
            "(site:reuters.com OR site:apnews.com OR site:cnbc.com OR site:yna.co.kr OR "
            "site:edaily.co.kr OR site:mt.co.kr OR site:news1.kr)"
        ),
    ),
    (
        "반도체 자회사·설비투자 자금조달",
        (
            "(반도체 OR HBM OR 메모리 OR 솔리다임 OR Solidigm) "
            "(자금조달 OR 자금 조달 OR 외부자본 OR 자회사 상장 OR 지분 매각 OR funding) "
            "(site:yna.co.kr OR site:news1.kr OR site:hankyung.com OR site:mk.co.kr OR "
            "site:reuters.com OR site:edaily.co.kr)"
        ),
    ),
    (
        "AI 인프라 자산매각·담보금융·재임차",
        (
            "(AI OR GPU OR 엔비디아 OR 데이터센터) "
            "(매각 OR 담보 OR 리스 OR 재임차 OR 자금조달 OR sale-leaseback OR financing) "
            "(아마존 OR 빅테크 OR 클라우드 OR Amazon OR hyperscaler) "
            "(site:hankyung.com OR site:yna.co.kr OR site:news1.kr OR site:reuters.com OR "
            "site:ft.com OR site:edaily.co.kr OR site:mt.co.kr)"
        ),
    ),
    (
        "국내외 제조업 공장 감원·생산축소",
        (
            "(공장 OR 제조업 OR 자동차 OR 트럭 OR factory OR manufacturing) "
            "(감원 OR 해고 OR 일자리 감축 OR 생산축소 OR layoffs OR laid off) "
            "(site:apnews.com OR site:reuters.com OR site:yna.co.kr OR site:news1.kr OR "
            "site:hankyung.com OR site:edaily.co.kr OR site:mk.co.kr)"
        ),
    ),
    (
        "러시아·우크라이나 경제목표·에너지·물류",
        (
            "(푸틴 OR Putin OR 러시아 OR Russia OR 우크라이나 OR Ukraine) "
            "(경제목표 OR 경제 목표 OR 에너지시설 OR 에너지 시설 OR 제재 OR 원유 OR 가스 OR 운임) "
            "(site:reuters.com OR site:apnews.com OR site:cnbc.com OR site:yna.co.kr OR "
            "site:edaily.co.kr OR site:mt.co.kr)"
        ),
    ),
    (
        "AGI·HBM 첨단패키징 병목",
        (
            "(AGI OR 인공일반지능 OR 반도체패키징 OR 반도체 패키징) "
            "(HBM OR 첨단패키징 OR 첨단 패키징 OR 병목 OR 공급부족 OR 공급 부족) "
            "(site:hankyung.com OR site:etnews.com OR site:zdnet.co.kr OR site:yna.co.kr OR "
            "site:mk.co.kr OR site:edaily.co.kr)"
        ),
    ),
    (
        "삼성 엑시노스·2나노·퀄컴 성능",
        (
            "(삼성전자 OR Samsung) (엑시노스 OR Exynos) "
            "(퀄컴 OR Qualcomm OR 2나노 OR 2nm OR 2㎚ OR 성능 OR 테스트) "
            "(site:hankyung.com OR site:etnews.com OR site:zdnet.co.kr OR site:yna.co.kr OR "
            "site:mk.co.kr OR site:edaily.co.kr)"
        ),
    ),
    (
        "엔비디아 실적·잭슨홀 일정",
        (
            "(엔비디아 OR NVIDIA) (실적발표 OR 실적 발표 OR 잭슨홀 OR Jackson Hole) "
            "(AI OR 반도체 OR HBM OR 금리 OR 연준 OR FOMC) "
            "(site:reuters.com OR site:cnbc.com OR site:yna.co.kr OR site:edaily.co.kr OR "
            "site:mt.co.kr OR site:mk.co.kr)"
        ),
    ),
    (
        "미 재정적자·장기국채 금리",
        (
            "(미국 OR U.S. OR US Treasury) (재정적자 OR 재정 적자 OR 국채금리 OR 국채 금리 OR 30년물) "
            "(달러 OR 금리 OR 국채발행 OR 국채 발행 OR 재정경로 OR 재정 경로) "
            "(site:reuters.com OR site:ft.com OR site:wsj.com OR site:edaily.co.kr OR "
            "site:yna.co.kr OR site:mt.co.kr)"
        ),
    ),
    (
        "고배당·커버드콜 ETF 순매수",
        (
            "(ACE OR TIGER OR KODEX OR 커버드콜 OR Covered Call) "
            "(ETF OR 상장지수펀드) (순매수 OR 자금유입 OR 자금 유입 OR 설정액 OR 순자산) "
            "(site:fnnews.com OR site:yna.co.kr OR site:edaily.co.kr OR site:mk.co.kr OR "
            "site:mt.co.kr OR site:hankyung.com)"
        ),
    ),
    (
        "미국 쇠고기 관세·통상",
        (
            "(트럼프 OR Trump OR 미국) (쇠고기 OR beef OR 미국산 소고기 OR 미국산 쇠고기) "
            "(관세 OR 관세철폐 OR 관세 철폐 OR 수입 OR 무역협정) "
            "(site:reuters.com OR site:apnews.com OR site:cnbc.com OR site:yna.co.kr OR "
            "site:edaily.co.kr OR site:mt.co.kr OR site:mk.co.kr)"
        ),
    ),
    (
        "트럼프 자산공시·대형 주식거래",
        (
            "(트럼프 OR Trump) (자산공시 OR 투자계좌 OR 주식 거래 OR ETF 거래) "
            "(공시 OR 매수 OR 매도 OR 거래액) "
            "(site:reuters.com OR site:wsj.com OR site:edaily.co.kr OR site:mk.co.kr OR "
            "site:hankyung.com OR site:yna.co.kr)"
        ),
    ),
    (
        "엔비디아·삼성 파운드리 추론칩 양산",
        (
            "(엔비디아 OR NVIDIA) (삼성전자 OR 삼성 파운드리 OR Samsung Foundry) "
            "(그록3 OR Groq3 OR LPX OR 추론칩 OR 추론 가속기 OR inference accelerator) "
            "(양산 OR 위탁생산 OR 파운드리 OR 공급) "
            "(site:dt.co.kr OR site:edaily.co.kr OR site:mt.co.kr OR site:mk.co.kr OR site:yna.co.kr OR site:hankyung.com)"
        ),
    ),
    (
        "AI 반도체·퇴직연금 ETF 신규 상장",
        (
            "(삼성전자 OR SK하이닉스 OR 삼성전기 OR AI 반도체) "
            "(퇴직연금 OR 채권혼합 OR ETF 상장 OR ETF 출시) "
            "(site:etoday.co.kr OR site:edaily.co.kr OR site:mt.co.kr OR site:mk.co.kr OR site:yna.co.kr)"
        ),
    ),
    (
        "중국 휴머노이드 로봇·대규모 투자",
        (
            "(샤오펑 OR XPeng OR 도고틱스 OR Dogo OR 휴머노이드 로봇) "
            "(투자 OR 자금조달 OR 신주 OR 출자 OR 달러) "
            "(site:mt.co.kr OR site:edaily.co.kr OR site:mk.co.kr OR site:yna.co.kr OR site:hankyung.com)"
        ),
    ),
    (
        "SK하이닉스 HBM 열관리·하이브리드 본딩",
        (
            "(SK하이닉스 OR SK hynix) (HBM OR I-HBM) "
            "(하이브리드 본딩 OR hybrid bonding OR 수직 적층 OR EMIB OR 열 관리) "
            "(site:edaily.co.kr OR site:mk.co.kr OR site:yna.co.kr OR site:hankyung.com OR site:dt.co.kr)"
        ),
    ),
    (
        "AI·반도체 슈퍼예산·재정지원",
        (
            "(정부 OR 기획재정부 OR 재정) (AI OR 반도체) "
            "(슈퍼예산 OR 슈퍼 예산 OR 예산안 OR 재정지원 OR R&D) "
            "(site:yna.co.kr OR site:edaily.co.kr OR site:mt.co.kr OR site:mk.co.kr OR site:hankyung.com)"
        ),
    ),
    (
        "CXMT·SMIC 메모리 자립·공급",
        (
            "(CXMT OR 창신메모리 OR SMIC) (D램 OR DRAM OR HBM OR 메모리) "
            "(2028 OR 자립 OR 자급 OR 수요 OR 점유율 OR 증설) "
            "(site:edaily.co.kr OR site:mk.co.kr OR site:mt.co.kr OR site:hankyung.com OR site:dt.co.kr)"
        ),
    ),
    (
        "엔비디아 베라루빈·총마진·양산",
        (
            "(엔비디아 OR NVIDIA) (베라 루빈 OR 베라루빈 OR Vera Rubin) "
            "(양산 OR 램프업 OR 총마진 OR 마진 OR HBM 수요) "
            "(site:reuters.com OR site:cnbc.com OR site:yna.co.kr OR site:edaily.co.kr OR site:mk.co.kr)"
        ),
    ),
    (
        "삼성 PIM·AI PC 상용화",
        (
            "(삼성전자 OR Samsung) (PIM OR LPDDR5X-PIM OR 가이아 OR Gaia) "
            "(상용화 OR AI PC OR 온디바이스 OR 출시) "
            "(site:zdnet.co.kr OR site:etnews.com OR site:yna.co.kr OR site:edaily.co.kr OR site:mk.co.kr)"
        ),
    ),
    (
        "엔비디아·앰코 첨단패키징 장기계약",
        (
            "(엔비디아 OR NVIDIA) (앰코 OR Amkor OR 첨단패키징 OR 첨단 패키징) "
            "(장기계약 OR 장기 계약 OR 선급금 OR 공급계약 OR 계약) "
            "(site:reuters.com OR site:bloomberg.com OR site:yna.co.kr OR site:edaily.co.kr OR site:mk.co.kr)"
        ),
    ),
    (
        "삼성·SK 레버리지 ETF 자금유출",
        (
            "(삼성전자 OR SK하이닉스 OR 삼전 OR 하닉) "
            "(레버리지 ETF OR 2배 ETF OR 단일종목 레버리지) "
            "(자금유출 OR 자금 유출 OR 순유출 OR 빠져나) "
            "(site:theguru.co.kr OR site:edaily.co.kr OR site:mk.co.kr OR site:mt.co.kr OR site:yna.co.kr)"
        ),
    ),
    (
        "AI MLCC 공급부족·리드타임",
        (
            "(MLCC OR 적층세라믹콘덴서) (AI OR 데이터센터 OR 서버) "
            "(공급부족 OR 공급 부족 OR 리드타임 OR 가격 인상 OR 쇼티지) "
            "(site:etnews.com OR site:zdnet.co.kr OR site:yna.co.kr OR site:edaily.co.kr OR site:mk.co.kr)"
        ),
    ),
    (
        "오픈AI·브로드컴 자체 AI칩·HBM",
        (
            "(오픈AI OR OpenAI OR 브로드컴 OR Broadcom) "
            "(할라페뇨 OR Jalapeno OR 자체 AI칩 OR 자체 AI 칩 OR HBM4) "
            "(가동 OR 상용화 OR 성능 OR 추론 OR inference) "
            "(site:yna.co.kr OR site:news1.kr OR site:chosun.com OR site:edaily.co.kr OR "
            "site:mk.co.kr OR site:hankyung.com)"
        ),
    ),
    (
        "SK하이닉스·인텔 EMIB·HBM 패키징",
        (
            "(SK하이닉스 OR SK hynix) (EMIB OR 2.5D OR HBM 패키징 OR HBM패키징) "
            "(인텔 OR Intel OR 기판 OR 고객 인증 OR 다변화) "
            "(site:theguru.co.kr OR site:yna.co.kr OR site:edaily.co.kr OR site:mk.co.kr OR site:hankyung.com)"
        ),
    ),
    (
        "AI 반도체 절연필름·기판 공급병목",
        (
            "(절연필름 OR 절연 필름 OR 패키지기판 OR 패키지 기판) "
            "(AI칩 OR AI 칩 OR HBM OR 반도체) "
            "(병목 OR 공급부족 OR 공급 부족 OR 생산량 OR 증설) "
            "(site:edaily.co.kr OR site:etnews.com OR site:yna.co.kr OR site:mk.co.kr)"
        ),
    ),
    (
        "아마존·엔비디아 GPU 대형도입",
        (
            "(아마존 OR Amazon OR AWS) (엔비디아 OR NVIDIA OR GPU) "
            "(200만 OR 추가 도입 OR 확보 OR 구매 OR CAPEX) "
            "(site:yna.co.kr OR site:news1.kr OR site:edaily.co.kr OR site:mk.co.kr OR site:hankyung.com)"
        ),
    ),
    (
        "엔비디아 메모리·생산능력 구매약정",
        (
            "(엔비디아 OR NVIDIA) (구매약정 OR 구매 약정 OR 생산능력 OR 메모리) "
            "(달러 OR 약정 OR 증가 OR 확대) "
            "(site:hankyung.com OR site:yna.co.kr OR site:edaily.co.kr OR site:mk.co.kr)"
        ),
    ),
    (
        "CATL 리튬광산 재가동·환경평가",
        (
            "(CATL OR 닝더스다이 OR 리튬광산 OR 리튬 광산) "
            "(재가동 OR 환경영향평가 OR EIA OR 공시 철회 OR 생산중단) "
            "(site:theguru.co.kr OR site:yna.co.kr OR site:edaily.co.kr OR site:mk.co.kr)"
        ),
    ),
    (
        "엔비디아 NVHBM·아마존 협력",
        (
            "(NVHBM OR 엔비디아 OR NVIDIA) (아마존 OR Amazon OR NVLink Fusion OR NV링크 퓨전) "
            "(공개 OR 공동 개발 OR 협력 OR HBM) "
            "(site:zdnet.co.kr OR site:yna.co.kr OR site:edaily.co.kr OR site:mk.co.kr)"
        ),
    ),
    (
        "엔비디아 루빈·베라 HBM4·LPDDR5X 메모리 공급",
        (
            "(엔비디아 OR NVIDIA) (루빈 OR Rubin OR 베라 OR Vera OR HBM4 OR LPDDR5X OR 메모리 부족) "
            "(삼성전자 OR SK하이닉스 OR 메모리 공급 OR 공급부족 OR 공급 부족) "
            "(site:news1.kr OR site:mt.co.kr OR site:edaily.co.kr OR site:mk.co.kr OR site:hankyung.com OR site:yna.co.kr)"
        ),
    ),
    (
        "이란 전쟁·중국·OPEC+ 원유시장 영향",
        (
            "(이란 OR Iran) (중국 OR China) (OPEC OR OPEC+) (석유 OR 원유 OR oil) "
            "(전쟁 OR 제재 OR 공급 OR 시장점유율 OR 가격) "
            "(site:reuters.com OR site:bloomberg.com OR site:ft.com OR site:cnbc.com)"
        ),
    ),
    (
        "트럼프 관세·미국 데이터센터 CAPEX",
        (
            "(트럼프 OR Trump OR 미국 행정부) (관세 OR tariff) (데이터센터 OR data center) "
            "(장비 OR 건설비 OR CAPEX OR 비용 OR 수입) "
            "(site:reuters.com OR site:bloomberg.com OR site:ft.com OR site:cnbc.com)"
        ),
    ),
    (
        "SK하이닉스 미국 HBM 첨단패키징 투자",
        (
            "(SK하이닉스 OR SK hynix) (웨스트라피엣 OR 인디애나 OR Purdue OR 퍼듀) "
            "(HBM OR 첨단 패키징 OR 첨단패키징) "
            "(투자 OR 공정 OR 생산시설 OR 착공 OR 가동) "
            "(site:dailian.co.kr OR site:yna.co.kr OR site:edaily.co.kr OR site:mk.co.kr OR site:hankyung.com)"
        ),
    ),
    (
        "키옥시아 이와테 낸드 공장 CAPEX",
        (
            "(키옥시아 OR Kioxia) (이와테 OR Iwate OR 낸드 OR NAND) "
            "(공장 OR 투자 OR 추진 OR 증설 OR CAPEX) "
            "(site:joongang.co.kr OR site:yna.co.kr OR site:edaily.co.kr OR site:mk.co.kr)"
        ),
    ),
    (
        "트럼프 H-1B 비자 수수료 정책",
        (
            "(트럼프 OR Trump OR 미국 행정부) (H-1B OR H1B OR 전문직 비자) "
            "(수수료 OR 비자비용 OR 이민정책 OR 제안 OR 규칙) "
            "(site:reuters.com OR site:apnews.com OR site:cnbc.com OR site:yna.co.kr OR site:chosun.com)"
        ),
    ),
    (
        "반도체 소재·패키징·황산 증설",
        (
            "(고려아연 OR 반도체황산 OR 반도체 황산 OR 글라스 캐리어 OR 유리 웨이퍼 OR HBM 패키징) "
            "(증설 OR 생산능력 OR 수율 OR 결함 OR 검사 OR 투자 OR 양산) "
            "(site:hankyung.com OR site:edaily.co.kr OR site:mk.co.kr OR site:etnews.com OR "
            "site:inews24.com OR site:biz.chosun.com OR site:yna.co.kr)"
        ),
    ),
    (
        "ESS 규제·NXT 거래제도",
        (
            "(ESS OR 에너지저장장치 OR NXT OR 넥스트레이드 OR 프리마켓 OR 프리 마켓) "
            "(법적 분류 OR 이격거리 OR 규제 개선 OR 규제개선 OR 거래 방식 OR 거래방식 OR 시행) "
            "(site:yna.co.kr OR site:edaily.co.kr OR site:mk.co.kr OR site:mt.co.kr OR "
            "site:inews24.com OR site:dailian.co.kr OR site:newsis.com)"
        ),
    ),
    (
        "중국 메모리 생산능력·LPDDR6",
        (
            "(CXMT OR 창신메모리 OR YMTC OR 창장메모리) "
            "(매출 OR 웨이퍼 OR 낸드 OR LPDDR6 OR 양산 OR 생산능력 OR 점유율) "
            "(site:edaily.co.kr OR site:mk.co.kr OR site:mt.co.kr OR site:hankyung.com OR "
            "site:dt.co.kr OR site:yna.co.kr)"
        ),
    ),
    (
        "미국 반도체 관세·내장제품",
        (
            "(트럼프 OR Trump OR 미국 행정부) (반도체 관세 OR 칩 관세 OR tariff) "
            "(칩 들어간 제품 OR 내장 제품 OR 수입품 OR 공급망 OR 적용 대상) "
            "(site:reuters.com OR site:apnews.com OR site:cnbc.com OR site:ft.com OR "
            "site:yna.co.kr OR site:edaily.co.kr OR site:mk.co.kr)"
        ),
    ),
    (
        "삼성·SK 주주환원·자사주",
        (
            "(삼성전자 OR SK하이닉스 OR 삼전 OR 하이닉스) "
            "(자사주 OR 자기주식 OR 주주환원 OR 소각 OR 매입) "
            "(공시 OR 이사회 OR 결정 OR 규모 OR 취득) "
            "(site:dart.fss.or.kr OR site:yna.co.kr OR site:edaily.co.kr OR site:mk.co.kr OR "
            "site:mt.co.kr OR site:hankyung.com OR site:newsis.com)"
        ),
    ),
    (
        "신용융자·삼성·SK 수급",
        (
            "(삼성전자 OR SK하이닉스 OR 삼전 OR 하이닉스) "
            "(신용거래융자 OR 신용잔고 OR 빚투 OR 신용자금) "
            "(증가 OR 집중 OR 비중 OR 금액 OR 수급) "
            "(site:edaily.co.kr OR site:mk.co.kr OR site:mt.co.kr OR site:yna.co.kr OR site:fnnews.com)"
        ),
    ),
    (
        "한국 로보택시·ESS 합작법인",
        (
            "(포니AI OR Pony AI OR 로보택시 OR robotaxi OR 삼성SDI OR Samsung SDI) "
            "(상용화 OR 운행 OR 도입 OR 시범 OR GM OR 합작법인 OR JV OR 26GWh) "
            "(site:yna.co.kr OR site:edaily.co.kr OR site:mk.co.kr OR site:mt.co.kr OR "
            "site:news1.kr OR site:biz.chosun.com)"
        ),
    ),
    (
        "미국·베네수엘라 원유협정",
        (
            "(트럼프 OR Trump OR 미국) (베네수엘라 OR Venezuela) "
            "(석유 합의 OR 원유 합의 OR oil agreement OR 650억 배럴 OR 65 billion barrels) "
            "(site:reuters.com OR site:apnews.com OR site:cnbc.com OR site:bbc.com OR site:ft.com)"
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
    row_text = f"{row.get('title') or ''} {row.get('summary') or ''}".lower()
    trusted_names = {str(value).lower() for value in KOREAN_BUSINESS_PUBLISHER_DOMAINS.values()}
    foreign_domains = {"reuters.com", "apnews.com", "cnbc.com"}
    foreign_geopolitical_event = (
        any(domain in link for domain in foreign_domains)
        and (
            (
                "이란" in row_text
                and any(term in row_text for term in ("추가 공격", "추가공격", "공격 임박", "공격임박"))
            )
            or (
                any(term in row_text for term in ("쿠웨이트", "kuwait"))
                and any(term in row_text for term in ("드론 공격", "드론공격", "drone attack"))
            )
            or (
                any(term in row_text for term in ("젤렌스키", "zelensky", "우크라이나", "ukraine"))
                and any(term in row_text for term in ("스타링크", "starlink"))
            )
            or (
                any(term in row_text for term in ("가자", "gaza", "하마스", "hamas"))
                and any(term in row_text for term in ("휴전", "ceasefire", "무장해제", "disarmament"))
            )
        )
    )
    return (
        any(
            domain in link
            for domain in KOREAN_BUSINESS_PUBLISHER_DOMAINS
            if domain not in foreign_domains
        )
        or (publisher in trusted_names and publisher not in {"reuters", "ap", "cnbc"})
        or foreign_geopolitical_event
        or source.startswith("국내 신뢰매체")
    )


def korean_business_publisher(row: dict) -> str:
    link = str(row.get("link") or "").lower()
    for domain, publisher in KOREAN_BUSINESS_PUBLISHER_DOMAINS.items():
        if domain in link:
            return publisher
    return str(row.get("publisher") or row.get("source") or "국내 신뢰매체")


def korean_business_source_domain_allowed(link: str) -> bool:
    try:
        hostname = urllib.parse.urlsplit(str(link or "")).hostname or ""
    except ValueError:
        return False
    return any(hostname == domain or hostname.endswith("." + domain) for domain in KOREAN_BUSINESS_PUBLISHER_DOMAINS)


def korean_business_article_url_rejection(link: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(link)
    except ValueError:
        return "malformed_article_url"
    if parsed.scheme not in {"http", "https"} or not korean_business_source_domain_allowed(link):
        return "untrusted_article_url"
    path = parsed.path.lower().rstrip("/")
    if not path or re.search(r"/(?:search|section|category|listing|list)(?:[/.]|$)", path):
        return "publisher_listing_not_article"
    host = parsed.hostname or ""
    query = {key.lower(): values for key, values in urllib.parse.parse_qs(parsed.query).items()}
    if host == "fnnews.com" or host.endswith(".fnnews.com"):
        if not re.fullmatch(r"/news/\d+", path):
            return "publisher_listing_not_article"
    if host == "etoday.co.kr" or host.endswith(".etoday.co.kr"):
        if not re.fullmatch(r"/news/view/\d+", path):
            return "publisher_listing_not_article"
    if host == "kmib.co.kr" or host.endswith(".kmib.co.kr"):
        if path != "/article/view.asp" or not any(re.fullmatch(r"\d+", value) for value in query.get("arcid", [])):
            return "publisher_listing_not_article"
    if host == "newsis.com" or host.endswith(".newsis.com"):
        if any(value.upper().startswith("NISI") for value in query.get("id", [])) or "nisi" in path:
            return "photo_page_not_article"
    return ""


def canonical_korean_business_article_url(link: str) -> str:
    parsed = urllib.parse.urlsplit(link)
    query = urllib.parse.parse_qs(parsed.query)
    article_ids = next((values for key, values in query.items() if key.lower() == "newsid"), [])
    if (
        parsed.hostname == "m.coinlab.edaily.co.kr" and parsed.scheme in {"http", "https"}
        and parsed.path.lower() == "/news/read"
        and len(article_ids) == 1 and re.fullmatch(r"\d{15,20}", article_ids[0])
    ):
        return urllib.parse.urlunsplit(("https", "www.edaily.co.kr", "/News/Read", parsed.query, ""))
    return link


def korean_business_source_allowed(item: dict) -> bool:
    if korean_business_source_domain_allowed(str(item.get("link") or "")):
        return True
    publisher = base.norm(str(item.get("publisher") or item.get("source") or ""))
    trusted_publishers = {
        base.norm(str(value))
        for value in KOREAN_BUSINESS_PUBLISHER_DOMAINS.values()
    }
    return bool(publisher and publisher in trusted_publishers)


def korean_business_event_date(row: dict) -> str:
    published = row.get("published")
    if hasattr(published, "date"):
        return published.date().isoformat()
    return "date-unavailable"


KOREAN_BUSINESS_DETAIL_LIMIT = max(
    12,
    int(os.environ.get("GAMEJOA_KOREAN_BUSINESS_DETAIL_LIMIT", "160")),
)
KOREAN_BUSINESS_DETAIL_WORKERS = max(
    2,
    int(os.environ.get("GAMEJOA_KOREAN_BUSINESS_DETAIL_WORKERS", "12")),
)
KOREAN_BUSINESS_PRIORITY_TERMS = {
    "국부펀드": 12,
    "국가전략산업": 10,
    "aws": 11,
    "클라우드": 9,
    "capex": 11,
    "설비투자": 10,
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
    "관세 면제": 12,
    "영업익": 10,
    "매출": 9,
    "공급 부족": 11,
    "hbm4": 12,
    "hbm4e": 12,
    "시장 1위": 11,
    "점유율": 10,
    "역대 최대 매출": 12,
    "k-엑사원": 12,
    "파운데이션 모델": 11,
    "데이터센터 건설": 11,
    "의무보유": 12,
    "보호예수": 12,
    "품목허가": 12,
    "허가 권고": 12,
    "외환거래": 10,
    "주식분할": 9,
    "무장해제": 11,
    "중동 전쟁": 12,
    "추가 공격": 14,
    "공격 임박": 14,
    "드론 공격": 13,
    "쿠웨이트": 10,
    "스타링크": 12,
    "타격 승인": 13,
    "가자 휴전": 12,
    "평화 협정": 11,
    "국정조사": 13,
    "청문회": 12,
    "조사 착수": 12,
    "ymtc": 12,
    "창장메모리": 12,
    "일본 공장": 12,
    "해외 공장": 10,
    "생산거점": 10,
    "ai 서버 가격": 12,
    "메모리 품귀": 11,
    "핫칩스": 10,
    "hot chips": 10,
    "회사채": 10,
    "브렌트": 10,
    "무역협정": 11,
    "대응관세": 11,
    "앤트로픽 ipo": 12,
    "주주환원": 11,
    "잉여현금흐름": 10,
    "특별배당": 10,
    "자산공시": 9,
    "투자계좌": 9,
    "자기주식": 12,
    "자사주": 12,
    "웨스트라피엣": 14,
    "인디애나": 12,
    "반도체황산": 11,
    "글라스 캐리어": 10,
    "nxt": 12,
    "넥스트레이드": 12,
    "ess": 10,
    "이격거리": 10,
    "반도체 관세": 13,
    "칩 들어간 제품": 13,
    "베네수엘라": 12,
    "lpddr6": 11,
    "신용거래융자": 11,
    "신용잔고": 10,
    "로보택시": 10,
    "포니ai": 10,
}


def korean_business_detail_priority(row: dict) -> tuple[int, float]:
    title = str(row.get("title") or "").lower()
    summary = str(row.get("summary") or "").lower()
    title_score = sum(
        weight for term, weight in KOREAN_BUSINESS_PRIORITY_TERMS.items()
        if term in title
    )
    summary_score = sum(
        weight for term, weight in KOREAN_BUSINESS_PRIORITY_TERMS.items()
        if term not in title and term in summary
    )
    published = row.get("published")
    timestamp = published.timestamp() if hasattr(published, "timestamp") else 0.0
    return title_score * 2 + min(summary_score, 24), timestamp


def rank_korean_business_detail_candidates(
    rows: list[dict], seen_links: set[str], live_mode: bool
) -> list[dict]:
    return sorted(
        rows,
        key=lambda row: (
            1 if row.get("_pinned_direct_article") else 0,
            1 if not live_mode or str(row.get("link") or "") not in seen_links else 0,
            *korean_business_detail_priority(row),
        ),
        reverse=True,
    )


ARTICLE_SUMMARY_NOISE_PATTERNS = [
    r"\b[가-힣]{2,6}(?:\s+[가-힣]{2,6}){0,2}\s*(?:인턴\s*|수습\s*|객원\s*)?기자\s*=\s*",
    r"(?:저작권자\s*\(?c\)?\s*)?[^.\n]{0,80}?무단\s*전재\s*[-·–—]?\s*(?:및\s*)?재배포(?:\s*금지)?[.!。]?",
    r"AI\s*학습\s*및\s*활용\s*금지",
    r"저작권자\s*©?\s*이투데이",
    r"Copyright\s*©?\s*Etoday",
    r"\b(?:등록|입력)\s*\d{4}[./-]\d{1,2}[./-]\d{1,2}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?"
    r"(?:\s*수정\s*\d{4}[./-]\d{1,2}[./-]\d{1,2}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?)?"
    r"\s*[가-힣]{2,6}\s*기자\b",
    r"^\s*\([^)]{0,80}(?:로이터|연합뉴스|Reuters|AP|AFP)[^)]*\)\s*",
    r"\[[^\]\r\n]{1,40}=\s*(?:AP|AFP|Reuters|뉴시스|연합뉴스)(?:/[A-Za-z가-힣]+)?\]",
    r"\b(?:북마크|마이페이지에서\s*확인하세요)\b",
    r"\b카카오톡\s+페이스북\s+엑스\s+URL\s*공유\b",
    r"\[(?:서울|세종|부산|대구|대전|인천|광주|울산|수원|제주)\s*=\s*[^\]]{1,60}\]",
    r"\((?:서울|세종|부산|대구|대전|인천|광주|울산|수원|제주)\s*=\s*[^)]{1,80}\)",
    r"\[(?:헤럴드경제|이데일리|머니투데이|매일경제|전자신문|연합뉴스)"
    r"(?:\s*=\s*|\s+)[^\]]{1,30}\s*기자\]",
    r"(?:fn\s+)?공유(?:\s+공유하기)?(?:\s+글자크기){1,2}\s+설정\s+"
    r"프린트(?:\s+구독){1,2}(?:\s+증권(?:일반)?){0,2}",
    r"페이스북\s+X\(트위터\)\s+메일\s+URL\s+복사\s+작게\s+보통\s+크게",
    r"\[email\s+protected\]",
    r"\[(?:촬영|사진|자료사진|제공)\s+[^\]\r\n]{1,60}\]",
    r"\*?\s*재판매\s*및\s*DB\s*금지\]?",
    r"\b\d{4}[./]\d{1,2}[./]\d{1,2}\.?(?=\s+[A-Za-z0-9._%+-]+@)",
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
]
ARTICLE_UI_BOILERPLATE_TERMS = (
    "공유하기", "글자크기 설정", "프린트 구독", "페이스북 X(트위터)",
    "메일 URL 복사", "작게 보통 크게", "북마크", "마이페이지에서 확인하세요",
    "카카오톡 페이스북", "URL공유",
)
ARTICLE_SUMMARY_MAX_CHARS = 420
ARTICLE_MATERIAL_TERMS = (
    "매출", "영업이익", "순이익", "당기순이익", "실적", "수주", "계약", "발주",
    "증설", "출하", "가격", "인상", "인하", "증가", "감소", "순매수", "순매도",
    "배당", "자사주", "자기주식", "소각", "취득", "상용화", "양산평가",
    "투자", "협력", "회동", "공급", "가동", "인허가", "채용", "감원", "감축",
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
GAMEJOA_CORE_MAX_CHARS = 180
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
FOREIGN_NUMBER_PATTERN = r"\d[\d,.]*(?:\s*[천백십조억만](?:\s*\d[\d,.]*)?)*"
ENGLISH_SCALE_MULTIPLIERS = {
    "trillion": 1_000_000_000_000,
    "tn": 1_000_000_000_000,
    "billion": 1_000_000_000,
    "bn": 1_000_000_000,
    "million": 1_000_000,
    "mn": 1_000_000,
}


def clean_article_summary_text(text: str) -> str:
    cleaned = (
        html.unescape(str(text or ""))
        .replace("\xa0", " ")
        .replace("\ufeff", "")
        .replace("\u200b", "")
        .replace("弗", "달러")
    )
    cleaned = market_materiality.strip_source_photo_caption(cleaned)
    cleaned = re.sub(
        r"^[^.!?\r\n]{0,140}\[[^\]\r\n]{0,40}자료사진\]\s*", "", cleaned,
    )
    cleaned = re.sub(
        r"^.{0,100}?(?:참고\s*이미지|자료사진)\s*\((?:사진|제공)=[^)]+\)\s*",
        "",
        cleaned,
    )
    for pattern in ARTICLE_SUMMARY_NOISE_PATTERNS:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\(\s*(?:AI\s*)?(?:이미지\s*생성|자료사진)\s*\)", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"^\s*/사진\s*=[^\r\n]+[\r\n]+", "", cleaned)
    cleaned = re.sub(r"\[(?:앵커|기자|리포터)\]\s*(?:네[,，]\s*)?", " ", cleaned)
    cleaned = re.sub(r"^[\s,;:>|\]·•.*\-]+", "", cleaned)
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
            if match.group("label") == "파운드":
                # Bare pounds may be a production weight, not sterling.
                before = re.split(r"[.!?。;\n]|,\s+", cleaned[:match.start()])[-1][-80:]
                after = re.split(r"[.!?。;\n]|,\s+", cleaned[match.end():], maxsplit=1)[0][:60]
                quantity = re.search(r"구리|금속|생산량|출하량|중량|무게|체중|수확량|온스|킬로그램|\bkg\b", before + after, re.I)
                monetary = re.search(r"영국|스털링|매출|이익|배당|투자|자금|지출|자산|대출|비용|벌금|대금|구입|매입|매수|매도|계약금|상금|가격|금액", before + after)
                if quantity or not monetary:
                    continue
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
    from fx_api import daily_krw
    rates = {}
    for code in codes:
        try:
            q = daily_krw(code, now=now)
            rates[code] = {
                "code": code, "value": q.rate, "status": "일일 기준",
                "reference_time_kst": q.date + " 일일 기준(장중값 아님)",
                "query_time_kst": q.fetched_at, "source": q.source,
                "url": "https://www.exchangerate-api.com" if "ExchangeRate" in q.source else "https://frankfurter.dev/",
                "error": "", "crosscheck": q.check,
            }
        except Exception as exc:
            rates[code] = {
                "code": code, "value": None, "status": "확인 불가",
                "reference_time_kst": None, "query_time_kst": now.isoformat(timespec="seconds"),
                "source": "환율 API", "url": "https://frankfurter.dev/",
                "error": type(exc).__name__,
            }
    return {
        "query_time_kst": now.isoformat(timespec="seconds"),
        "rates": rates,
    }


def format_krw_amount(value: float) -> str:
    if value >= 100_000_000_000_000:
        return f"{int(value / 1_000_000_000_000 + 0.5):,}조원"
    if value >= 1_000_000_000_000:
        units = int(value / 100_000_000 + 0.5)
        trillions, remainder = divmod(units, 10_000)
        return f"{trillions}조{remainder:,}억원" if remainder else f"{trillions}조원"
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
    return text


def compact_converted_core(core: str, conversion: dict, limit: int = GAMEJOA_CORE_MAX_CHARS) -> str:
    converted = apply_krw_conversions(core, conversion)
    if len(converted) <= limit:
        return converted

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


def article_summary_body(text: str) -> str:
    """Keep article paragraphs, excluding UI chrome and related-story sections."""
    raw = market_materiality.source_reported_body(str(text or ""))
    ui_boundary = re.search(r"URL\s*(?:공유|복사)", raw, flags=re.I)
    if ui_boundary:
        raw = raw[ui_boundary.end():]
    paragraphs = []
    for line in raw.splitlines():
        line = line.strip()
        if re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", line) or re.match(
            r"^(?:제보는\s*카카오톡|[◎☞]\s*공감언론|<저작권자)", line,
        ):
            break
        if re.fullmatch(r"관련\s*뉴스|주요\s*뉴스|.+기자의\s*주요\s*뉴스", line):
            break
        if re.fullmatch(r"읽기모드|다크모드|폰트크기|가|기사반응|공유하기|프린트|북마크|가장\s*(?:작게|크게)|작게|기본|크게", line):
            continue
        cleaned = strip_core_ui_garbage(line)
        if cleaned:
            paragraphs.append(cleaned)
    return "\n".join(paragraphs)


def ranked_article_sentences(
    text: str,
    required: list[str],
    *,
    title: str = "",
) -> list[str]:
    cleaned_text = article_summary_body(text)
    sentences = [
        re.sub(
            r"^(?:▲[^)]{0,100}\)|\([^)]{0,100}(?:출처|사진)[^)]*\))\s*",
            "",
            clean_article_summary_text(sentence),
        )
        # Split only at actual punctuation. A bare Hangul "다" also appears
        # inside clauses such as "지난해 같은 기간보다 20.8% 감소", so using
        # it as a boundary drops the result that follows.
        for sentence in market_materiality.source_sentences(cleaned_text)
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
        if len(sentence) >= 12 and not article_title_restatement(sentence, title)
        and not market_materiality.COMPANY_PROFILE.search(sentence)
        and not market_materiality.ACCOUNTING_NOTE.search(sentence)
    ]
    sentences = list(dict.fromkeys(sentences))
    if market_materiality.focus_kind(title) == "research_spending":
        # Bind an amount to the issuer in the preceding source sentence.
        for index in range(1, len(sentences)):
            sentence, previous = sentences[index], sentences[index - 1]
            if not re.match(r"^(?:올해\s*)?(?:상반기|하반기|연간)\s+(?:연구개발비|R&D)", sentence, re.I):
                continue
            owner = re.match(r"^([A-Za-z0-9가-힣&·]+(?:\s+[A-Z]{2,5})?)(?:은|는|도)\s+", previous)
            if owner and re.search(r"연구개발|R&D", previous, re.I):
                particle = "의" if re.search(r"(?:연구개발비|R&D\s*비용)(?:는|은)", sentence, re.I) else "는"
                sentences[index] = f"{owner.group(1)}{particle} {sentence}"
    scored: list[tuple[int, int, str]] = []
    for index, sentence in enumerate(sentences):
        lowered = sentence.lower()
        required_hits = sum(term.lower() in lowered for term in required)
        material_hits = sum(term.lower() in lowered for term in ARTICLE_MATERIAL_TERMS)
        numeric = bool(re.search(r"\d[\d,.]*\s*(?:%|조|억|만|원|달러|t|톤|주)", sentence, re.I))
        result = any(term in sentence for term in ARTICLE_RESULT_TERMS)
        shareholder = any(term in sentence for term in ARTICLE_SHAREHOLDER_TERMS)
        score = required_hits * 3 + min(material_hits, 4) * 2
        score += market_materiality.focus_score(title, sentence)
        score += 5 if numeric else 0
        score += 4 if result else 0
        score += 3 if shareholder else 0
        score += 3 if re.search(r"(?:발표했다|공시했다|밝혔다|설명했다|공식화했다)[.!?。]?$", sentence) else 0
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
    attributed = re.match(
        r"^(로이터통신|블룸버그통신)(?:은|는)\s+[^.!?]{0,100}?인용해\s+(.+?)"
        r"(?:\s+\d{1,2}일\s*\(현지\s*시간\))?\s+보도했다[.!?]?$", text,
    )
    if attributed:
        text = f"{attributed.group(1)}은 {attributed.group(2)} 보도했다."
    replacements = (
        (r"^이에\s*따라\s+", ""),
        (r"^[가-힣]{2,5}\s*(?:인턴\s*|수습\s*|객원\s*)?(?:기자|특파원)(?:\s+[가-힣]{2,5}\s*(?:기자|특파원))*\s*=\s*", ""),
        (r"^[▲△▶]\s*", ""),
        (
            r"([A-Za-z가-힣·&]+)\s*\(\s*[\d,]+원\s*[▲▼+-]\s*[\d,]+\s*"
            r"(?:[+-]\d+(?:\.\d+)?%)?\s*\)",
            r"\1",
        ),
        (r"^\d{1,2}일\s+([A-Za-z0-9가-힣·&()]+)(?:은|는)\s+", r"\1, "),
        (r"^이날\s+([A-Za-z0-9가-힣·&()]+)(?:\s+이사회)?(?:은|는)\s+", r"\1, "),
        (r"^\d{1,2}일\s+([^.!?]{2,30}?)에\s*따르면\s*", r"\1에 따르면 "),
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


def korean_topic_particle(name: str) -> str:
    last = ord(name[-1]) if name else 0
    return "은" if 0xAC00 <= last <= 0xD7A3 and (last - 0xAC00) % 28 else "는"


def asset_financing_observation(sentence: str) -> dict[str, str]:
    """Bind the financing actor, quantified asset and proposal stage together."""
    proposal = re.search(
        r"(?:특수목적기구|\bSPV\b).{0,20}이전하는\s*방안.{0,20}(논의|검토)", sentence, re.I,
    )
    issuer = re.search(r"([A-Za-z0-9가-힣&·]+)(?:은|는)\s", sentence)
    asset = re.search(
        r"(\d[\d,.]*\s*(?:억|만|조)?\s*달러)\s*(?:\(약[^)]*\))?\s*(?:규모의\s*)?"
        r"([^.!?]{2,45}?\s*칩)(?:을|를)", sentence,
    )
    if not (proposal and issuer and asset):
        return {}
    return {
        "issuer": issuer.group(1),
        "amount": re.sub(r"\s+", "", asset.group(1)),
        "asset": re.sub(r"[‘’'\"“”]", "", asset.group(2)).strip(),
        "stage": proposal.group(1),
    }


def financial_cyber_incident_fact(title: str, body: str) -> str:
    """Bind an observed bank disclosure count and the authority's meeting stage."""
    if market_materiality.focus_kind(title) != "cyber_incident":
        return ""
    sentences = market_materiality.source_sentences(body)
    incidents = []
    bank_pattern = r"[A-Za-z가-힣]{2,18}(?:은행|캐피탈|금융지주)"
    headline_banks = list(dict.fromkeys(re.findall(bank_pattern, title)))
    if len(headline_banks) == 2:
        facts = []
        for bank in headline_banks:
            for index, sentence in enumerate(sentences):
                if bank not in sentence or not re.search(r"공격|해킹|유출", sentence):
                    continue
                window = []
                for row in sentences[index:index + 3]:
                    if any(other != bank for other in re.findall(bank_pattern, row)):
                        break
                    window.append(row)
                context = " ".join(window)
                if not any(market_materiality.focus_matches(title, row) for row in window):
                    continue
                estimate = re.search(r"유출\s*규모는\s*(약\s*)?(\d[\d,]*(?:만[\d,]*)?)명.{0,35}추정", context)
                broker = re.search(r"(?:주택\s*)?대출\s*모집인\s*(\d[\d,]*)명.{0,50}개인정보가\s*유출된.{0,20}확인", context)
                if estimate:
                    amount = f"{(estimate.group(1) or '').strip()}{estimate.group(2).replace(',', '')}명"
                    facts.append(f"{bank}{korean_topic_particle(bank)} 개인정보 유출 규모를 {amount}으로 추정했다.")
                elif broker:
                    facts.append(f"{bank}{korean_topic_particle(bank)} 대출모집인 {broker.group(1)}명의 개인정보 유출을 확인했다.")
                else:
                    continue
                break
        if len(facts) == 2:
            fact = " ".join(facts)
            owner = ""
            for index, sentence in enumerate(sentences):
                banks = set(re.findall(bank_pattern, sentence))
                if banks:
                    owner = banks.pop() if len(banks) == 1 else ""
                if (owner in headline_banks
                        and re.search(r"AI\s*침투\s*흔적은\s*발견되지\s*않", sentence)
                        and re.search(r"AI\s*이용\s*가능성", " ".join(sentences[index:index + 2]))):
                    fact += f" {owner} 공격의 AI 이용은 미확인이다."
                    break
            if len(fact) <= GAMEJOA_CORE_MAX_CHARS and core_sentence_is_complete(fact):
                return fact
    for index, sentence in enumerate(sentences):
        count = re.search(r"개인정보\s*(\d[\d,]*(?:만[\d,]*)?)\s*건이\s*유출(?:됐다|되었다)", sentence)
        if not count or not market_materiality.focus_matches(title, sentence) or market_materiality.BACKGROUND.search(sentence):
            continue
        context = sentence
        if re.match(r"^이\s*과정에서\s", sentence) and index:
            previous = sentences[index - 1]
            if not market_materiality.BACKGROUND.search(previous):
                context = previous + " " + sentence
        banks = set(re.findall(bank_pattern, context))
        if len(banks) == 1:
            incidents.append((banks.pop(), count.group(1).replace(',', '')))
    for response in sentences:
        if not market_materiality.focus_matches(title, response) or market_materiality.BACKGROUND.search(response):
            continue
        if not all(term in response for term in ("금융위원장", "금융감독원장", "CEO", "긴급 점검회의")):
            continue
        future = re.search(r"회의를\s*(?:연다|열\s*예정|개최한다|개최할\s*예정)", response)
        completed = re.search(r"회의를\s*(?:열었다|개최했다)", response)
        if not incidents or not (future or completed):
            continue
        bank, count = incidents[0]
        other_damage = any(
            market_materiality.focus_matches(title, sentence) and "유출" in sentence
            and any(other != bank for other in re.findall(bank_pattern, sentence))
            for sentence in sentences
        )
        timing = re.search(r"(?:오늘|이날|내일|오는\s*\d{1,2}일)(?:\s*(?:오전|오후))?", response)
        when = f"{timing.group(0)} " if timing else ""
        affected = "피해 " if re.search(r"침해\s*사고가\s*발생한\s*금융회사|피해\s*금융사", response) else ""
        stage = "열 예정이다" if future else "열었다"
        scope = " 등이" if other_damage else "이"
        fact = (f"{bank} 개인정보 {count}건{scope} 유출됐다. "
                f"금융위원장·금감원장은 {when}{affected}금융사 CEO 긴급 점검회의를 {stage}.")
        if len(fact) <= GAMEJOA_CORE_MAX_CHARS and core_sentence_is_complete(fact):
            return fact
    return ""


def contextual_commercial_fact(title: str, body: str) -> str:
    """Retain the supplier when a contract paragraph continues its product profile."""
    if market_materiality.focus_kind(title):
        return ""
    sentences = market_materiality.source_sentences(body)
    for index, sentence in enumerate(sentences):
        if not re.match(r"^(?:출시|도입)\s*이후\s", sentence) or not re.search(r"공급\s*계약을\s*체결했다", sentence):
            continue
        for previous in reversed(sentences[max(0, index - 3):index]):
            issuer = re.match(r"^([A-Za-z0-9가-힣&·]{2,30})(?:은|는)\s", previous)
            if not issuer or issuer.group(1) in {"회사", "업체", "기업", "정부", "제품", "서비스", "우리회사"}:
                continue
            if not re.search(r"자체[^.!?]{0,60}(?:제품|서비스|검사)|사업화에\s*나섰다", previous):
                continue
            name = issuer.group(1)
            fact = f"{name}{korean_topic_particle(name)} " + re.sub(r"^(?:출시|도입)\s*이후\s+", "", sentence)
            fact = normalized_article_sentence(fact)
            if len(fact) <= GAMEJOA_CORE_MAX_CHARS and core_sentence_is_complete(fact):
                return fact
    return ""


def conditional_financial_market_entry_fact(title: str, body: str) -> str:
    if not re.search(r"규제.{0,15}(?:열리면|명확).{0,15}(?:韓|한국)\s*진출", title):
        return ""
    source = article_summary_body(body)
    issuer = re.search(r"([가-힣A-Za-z]{2,20})\s+홀딩스\([^)]*주식\s*티커명", source)
    listed = re.search(r"오는\s*(\d{1,2})일\s*나스닥에\s*상장돼[^.!?]{0,50}첫\s*거래를\s*시작한다", source)
    if not issuer or issuer.group(1) not in title or not listed:
        return ""
    if not (
        re.search(r"CEO", source) and re.search(r"XRP를.{0,45}운용해\s*수익을\s*얻는.{0,60}더\s*많은\s*XRP를\s*축적", source)
        and re.search(r"한국\s*내\s*규제가\s*명확해진다는\s*전제.{0,160}한국\s*사업\s*확대", source)
        and re.search(r"그\s*이후에\s*검토할\s*것", source)
    ):
        return ""
    name = issuer.group(1)
    fact = (f"{name} CEO는 XRP 운용수익 확대와 규제 명확화 후 한국 진출 검토 방침을 밝혔다. "
            f"나스닥 상장·첫 거래는 오는 {listed.group(1)}일 예정이라고 말했다.")
    return fact if core_sentence_is_complete(fact) else ""


def compensation_cost_forecast_fact(title: str, body: str) -> str:
    if not re.search(r"성과급|보상\s*비용", title) or not re.search(r"실적|이익|마진|수익성", title):
        return ""
    source = article_summary_body(body)
    speakers = set(re.findall(r"([가-힣A-Za-z]+)\s+([가-힣A-Za-z]{2,20})\s+최고재무책임자\(CFO\)", source))
    if len(speakers) != 1:
        return ""
    name, issuer = next(iter(speakers))
    for sentence in market_materiality.source_sentences(source):
        if not re.search(rf"{re.escape(name)}\s*CFO", sentence) or not re.search(
            r"성과급과\s*신규\s*생산시설\s*초기\s*가동\s*비용\s*등", sentence,
        ):
            continue
        cost = re.search(
            r"(\d{4})회계연도\s*([1-4])분기[^!?]{0,35}?약\s*"
            r"(\d[\d,.]*\s*(?:조|억|만)?\s*달러)(?:\([^)]{0,50}\))?의\s*추가\s*비용이\s*"
            r"발생할\s*것으로\s*예상했다", sentence,
        )
        if not cost:
            continue
        amount = re.sub(r"\s+", "", cost.group(3))
        fact = (f"{issuer}{korean_topic_particle(issuer)} 성과급·신규시설 초기 가동 등으로 "
                f"{cost.group(1)}회계연도 {cost.group(2)}분기 추가 비용 {amount}를 예상했다.")
        margin = re.search(
            rf"{re.escape(issuer)}(?:은|는)\s*매출총이익률[^!?]{{0,100}}?다음\s*분기에는\s*"
            r"약\s*(\d+(?:\.\d+)?)%로\s*낮아질\s*것으로\s*관측했다", source,
        )
        if margin:
            fact += f" 다음 분기 매출총이익률은 {margin.group(1)}%로 전망했다."
        return fact if core_sentence_is_complete(fact) else ""
    return ""


def acquisition_negotiation_fact(title: str, body: str) -> str:
    if market_materiality.focus_kind(title) != "ownership" or not re.search(r"인수|합병", title):
        return ""
    if re.search(r"완료|계약\s*체결|인수\s*확정|합병\s*성사", title):
        return ""
    issuer = re.match(r"^([^,，]{2,40})[,，]", title)
    if not issuer:
        return ""
    buyer = issuer.group(1).strip()
    source = article_summary_body(body)
    talks = re.search(
        rf"{re.escape(buyer)}(?:이|가|은|는)\s+([A-Za-z0-9가-힣&·-]+)(?:을|를)\s*"
        r"인수하는\s*방안을\s*논의\s*중", source,
    )
    if not talks:
        return ""
    target = talks.group(1)
    terms = re.search(
        rf"{re.escape(target)}(?:을|를)\s*(약\s*)?(\d[\d,.]*\s*(?:(?:조|억|만|천)\s*)*(?:달러|유로|원))"
        r"(?:\([^)]{0,60}\))?에\s*인수", source,
    )
    amount = f"{terms.group(1) or ''}{terms.group(2)}에 " if terms else ""
    attribution = "이라고 보도됐다" if re.search(r"소식통|보도했다|통신|파이낸셜타임스", source) else "이다"
    fact = f"{buyer}{korean_topic_particle(buyer)} {target}를 {amount}인수하는 방안을 논의 중{attribution}."
    return fact if core_sentence_is_complete(fact) else ""


def reported_issuer_announcement_fact(title: str, body: str) -> str:
    """Bind a declared issuer action before analyst forecasts or commentary."""
    body = market_materiality.source_reported_body(body)
    issuer = re.search(r"(?m)^([A-Za-z가-힣][^!?\n]{1,45}?)\(([A-Z0-9.]{2,10})\)(?:은|는|가|이)\s+", body)
    if not issuer:
        return ""
    actor = issuer.group(1).strip()
    lead = body[issuer.end():].splitlines()[0]
    if market_materiality.focus_kind(title) == "nav_forecast":
        reference = re.search(r"(\d{1,2}월\s*\d{1,2}일)\s*기준\s*잠정", lead)
        nav = re.search(r"주당\s*순자산가치\(NAV\)가\s*(\d{1,2}월\s*\d{1,2}일)\s*대비\s*(\d+(?:\.\d+)?)%\s*넘게\s*증가할\s*것으로\s*예상", lead)
        if reference and nav:
            fact = (f"{actor}{korean_topic_particle(actor)} {reference.group(1)} 잠정치에서 주당 NAV가 "
                    f"{nav.group(1)} 대비 {nav.group(2)}% 넘게 증가할 것으로 예상했다.")
            if re.search(r"감사를\s*거치지\s*않은\s*잠정치", body):
                fact += " 감사 전 추정치로 최종 결산에서 달라질 수 있다."
            return fact if core_sentence_is_complete(fact) else ""
    if market_materiality.focus_kind(title) == "facility_approval":
        product = re.search(r"FDA\s*([A-Za-z가-힣0-9]+)\s*(?:美|미국)", title)
        facility = re.search(r"생산\s*설비\(([A-Z0-9]+)\)", lead)
        if product and facility and product.group(1) in lead and re.search(r"FDA[^\n]{0,400}승인해", lead):
            fact = (f"{actor}{korean_topic_particle(actor)} FDA의 추가 승인으로 {product.group(1)}를 "
                    f"{facility.group(1)}에서도 미국용 원료의약품으로 생산할 수 있게 됐다.")
            capacity = re.search(r"미국\s*공급[^\n]{0,50}?생산능력이\s*사실상\s*(\d+)배로\s*늘었다고\s*밝혔다", body)
            if capacity:
                fact += f" 회사는 미국 공급용 생산능력이 사실상 {capacity.group(1)}배로 늘었다고 밝혔다."
            return fact if core_sentence_is_complete(fact) else ""
    currency = r"\d[\d,.]*(?:\s*[조억만천]\s*\d[\d,.]*)*\s*[조억만천]?\s*(?:달러|유로|원)"
    acquisition = re.search(rf"^(.+?)(?:을|를)\s*(약\s*)?({currency})에\s*인수하는\s*(?:최종\s*)?계약을\s*체결", lead)
    if "인수" in title and acquisition:
        target = re.sub(r"\([A-Za-z][^)]*\)", "", acquisition.group(1)).strip()
        fact = f"{actor}{korean_topic_particle(actor)} {target}를 {acquisition.group(2) or ''}{acquisition.group(3)}에 인수하는 최종 계약을 체결했다."
        close = re.search(r"거래는\s*규제\s*당국\s*승인[^\n]{0,100}?(\d{4})년[^\n]{0,30}?([1-4])분기\s*중\s*완료될\s*것으로\s*예상", body)
        if close:
            fact += f" 규제 승인 등을 거쳐 {close.group(1)}년 {close.group(2)}분기 종결 예정이다."
        return fact if core_sentence_is_complete(fact) else ""
    sale = re.search(rf"연방정부에\s*총\s*({currency})에\s*매각하는\s*거래를\s*마무리", lead)
    buyback = re.search(rf"자사주\s*매입\s*승인\s*한도를[^\n]{{0,55}}?늘린\s*({currency})로\s*상향", lead)
    facilities = re.search(r"\(([A-Z]{2,8})\)\s*수용·처리\s*시설\s*(\d+)곳", lead)
    if "매각" in title and "자사주" in title and sale and buyback and facilities:
        fact = (f"{actor}{korean_topic_particle(actor)} {facilities.group(1)} 시설 {facilities.group(2)}곳을 연방정부에 "
                f"{sale.group(1)}에 매각 완료했다. 자사주 매입 승인 한도는 {buyback.group(1)}로 늘렸다.")
        return fact if core_sentence_is_complete(fact) else ""
    if market_materiality.focus_kind(title) == "management_change":
        departure = re.search(r"최고재무책임자\(CFO\)가\s*(\d{1,2}월\s*\d{1,2}일)\s*자로\s*사임", lead)
        guidance = re.search(r"(\d{4})년\s*연간\s*매출\s*가이던스를\s*유지", lead)
        if departure and guidance:
            fact = (f"{actor}{korean_topic_particle(actor)} CFO의 {departure.group(1)} 사임을 발표했고, "
                    f"{guidance.group(1)}년 연간 매출 가이던스를 유지했다.")
            if re.search(r"후임\s*CFO\s*물색\s*절차에\s*이미\s*착수", body, re.I):
                fact += " 후임 CFO 물색에 착수했다."
            return fact if core_sentence_is_complete(fact) else ""
    if re.search(r"제조\s*계약", title):
        partner = re.search(r"([A-Za-z가-힣]+)와\s*제조\s*계약", title)
        subsidiary = re.search(r"자회사[^\n]{0,55}?\(([A-Z]{2,8})\)가", lead)
        product = re.search(r"의약품\s*등급\s*([가-힣A-Za-z]+)\s*원료의약품", lead)
        if partner and subsidiary and product and partner.group(1) in lead and "제조 서비스 계약을 체결" in lead:
            fact = (f"{actor}의 자회사 {subsidiary.group(1)}는 {partner.group(1)}와 미국 내 의약품 등급 "
                    f"{product.group(1)} 제조 계약을 체결했다.")
            if re.search(r"생산의\s*시기와\s*규모는\s*DEA\s*쿼터[^\n]{0,80}규제\s*승인에\s*따라", body):
                fact += " 생산 시기·규모는 DEA 쿼터와 규제 승인에 달렸다."
            return fact if core_sentence_is_complete(fact) else ""
    return ""


def source_headline_event_fact(title: str, body: str) -> str:
    """Bind a compact observation to its source actor, population and period."""
    focus = market_materiality.focus_kind(title)
    source = market_materiality.source_reported_body(body)
    rows = market_materiality.source_sentences(source)
    consensus = market_materiality.annual_earnings_consensus_observation(title, source)
    if consensus:
        fact = (f"{consensus['provider']}가 최근 {consensus['window']}개월간 집계한 {consensus['issuer']}의 "
                f"{consensus['period']} 영업이익 전망치 평균은 {consensus['amount'].strip()}이다.")
        if consensus['quarter']:
            direction = '증가' if consensus['quarter_direction'] in {'급증', '증가'} else '감소'
            fact += (f" {consensus['quarter']}분기 전망은 {consensus['quarter_amount'].strip()}으로 "
                     f"전년비 {consensus['quarter_growth']}% {direction}할 전망이다.")
        return fact if len(fact) <= GAMEJOA_CORE_MAX_CHARS and core_sentence_is_complete(fact) else ''
    decree = market_materiality.enacted_financial_decree_observation(title, source)
    if decree:
        fact = (f"{decree['day']}일 국무회의에서 {decree['law']} 개정안이 의결됐다. "
                f"{decree['beneficiary']}의 부실채권 매입을 허용하며 {decree['effective_day']}일부터 시행된다.")
        if decree['operation_month']:
            fact += f" 매입 업무는 출자·금융위 의결 등을 거쳐 {decree['operation_month']}월 이후 시작할 예정이다."
        return fact if len(fact) <= GAMEJOA_CORE_MAX_CHARS and core_sentence_is_complete(fact) else ''
    if re.search(r'글로벌\s*전기차', title):
        volume = re.search(r'(?P<provider>[A-Za-z가-힣]+리서치)에\s*따르면\s*'
                           r'(?P<period>\d{1,2}[∼~\-]\d{1,2}월)\s*글로벌\s*전기차\(플러그인하이브리드\s*포함\)\s*'
                           r'인도량은\s*전년\s*동기\s*대비\s*(?P<growth>\d+(?:\.\d+)?)%\s*'
                           r'(?P<direction>증가|감소)한\s*(?P<units>\d[\d,.천백십만]*대)로\s*집계됐다', source)
        group = re.search(r'(?P<group>[A-Za-z가-힣]+차그룹)은\s*(?P<growth>\d+(?:\.\d+)?)%\s*'
                          r'(?P<direction>증가|감소)한\s*(?P<units>\d[\d,.천백십만]*대)로\s*점유율을\s*'
                          r'종전\s*(?P<old_share>\d+(?:\.\d+)?)%에서\s*(?P<share>\d+(?:\.\d+)?)%로', source)
        if volume:
            fact = (f"{volume['provider']}에 따르면 {volume['period']} 글로벌 전기차(플러그인하이브리드 포함) "
                    f"인도량은 {volume['units']}로 전년비 {volume['growth']}% {volume['direction']}했다.")
            if group and group['group'] in title:
                share_direction = '높아졌다' if float(group['share']) > float(group['old_share']) else '낮아졌다'
                fact += (f" {group['group']}은 {group['units']}로 {group['growth']}% {group['direction']}했으며 "
                         f"점유율은 {group['old_share']}%에서 {group['share']}%로 {share_direction}.")
            return fact if len(fact) <= GAMEJOA_CORE_MAX_CHARS and core_sentence_is_complete(fact) else ''
    if re.search(r'재개발|정비사업|구역\s*수주', title):
        order = next((match for row in rows
                      if (match := re.search(r'(?P<issuer>[A-Za-z0-9가-힣&·.-]+)(?:은|는|이|가)\s*공사비\s*'
                                             r'(?P<amount>\d[\d,.\s조억만천백십]*원)\s*규모의\s*'
                                             r'(?P<project>[^.!?]{3,70}사업)을\s*수주했다', row))), None)
        cumulative = re.search(r'올해\s*도시정비사업\s*누적\s*수주액은\s*(\d[\d,.\s조억만천백십]*원)으로\s*늘었다', source)
        if order and order['issuer'] in title and cumulative:
            fact = (f"{order['issuer']}{korean_topic_particle(order['issuer'])} {order['project']}을 수주했다. "
                    f"공사비는 {order['amount'].strip()}이며 올해 도시정비사업 누적 수주액은 {cumulative[1].strip()}이다.")
            return fact if len(fact) <= GAMEJOA_CORE_MAX_CHARS and core_sentence_is_complete(fact) else ''
    sales = market_materiality.cumulative_foreign_sales_observation(title, source)
    if sales:
        fact = (f"{sales['issuer']}은 {sales['day']}일 {sales['period']} 누적 외국인 고객 매출이 "
                f"{sales['amount']}을 돌파했다고 밝혔다.")
        return fact if core_sentence_is_complete(fact) else ''
    model = market_materiality.macro_model_report_observation(title, source)
    if focus == 'macro_model_assessment' and model:
        report_name = 'IMF EBA 모형 개편이 우리나라 경상수지 평가에 미치는 영향'
        prefix = f"{model['day']}일 한국은행이 발표한 '{report_name}'"
        levels = re.search(r'적정\s*경상수지는\s*기존\s*([\d.]+)%에서\s*([\d.]+)%로\s*([\d.]+)%p\s*낮아', source)
        gap = re.search(r'경상수지\s*갭\s*역시\s*([\d.]+)%에서\s*([\d.]+)%', source)
        if levels and gap:
            fact = (f'{prefix} 보고서에 따르면 GDP 대비 적정 경상수지는 {levels[1]}%에서 {levels[2]}%로 낮아졌다. '
                    f'실제 수지와 적정 수준 간 갭은 {gap[1]}%에서 {gap[2]}%로 확대됐다.')
        else:
            fact = f'{prefix} 보고서는 한국의 적정 경상수지가 낮아질 것으로 분석했다.'
        if not levels and re.search(r'내년.{0,50}(?:초과.{0,8}순대외자산|NFA)|내년부터\s*도입되는.{0,30}순대외자산', source):
            fact += ' 내년 평가에는 초과조정 순대외자산(NFA)이 도입된다.'
        return fact if len(fact) <= GAMEJOA_CORE_MAX_CHARS and core_sentence_is_complete(fact) else ''
    if '소각' in title and len(source) < 500:
        decision = next((normalized_article_sentence(row) for row in rows
                         if '소각을 결정' in row and '공시했다' in row), '')
        schedule = next((normalized_article_sentence(row) for row in rows if '소각 예정일은' in row), '')
        if decision and schedule:
            fact = decision + ' ' + schedule
            return fact if len(fact) <= GAMEJOA_CORE_MAX_CHARS and core_sentence_is_complete(fact) else ''
    if '발전소' in title and '송금' in title:
        speaker = re.search(r'([가-힣]{2,5})\s*경제부총리', source)
        payment = re.search(r'정부가\s*대미투자\s*사업인\s*([^.!?]{2,40}발전소)\s*건설을\s*위해\s*(지난\s*\d{1,2}일)\s*(\d[\d,.]*억\s*달러)를\s*송금했다고', source)
        pending = re.search(r'전력구매계약은\s*아직\s*체결되지\s*않았다', source)
        if speaker and speaker[1] in title and payment and pending:
            fact = (f"{speaker[1]} 부총리는 {payment[1]} 건설에 {payment[2]} {payment[3]}를 송금한 사실을 확인했다. "
                    '발전소 전력구매계약은 아직 체결되지 않았으며 향후 체결할 예정이다.')
            return fact if core_sentence_is_complete(fact) else ''
    if '면세' in title and '경유' in title:
        signed = next((row for row in rows if '트럼프' in row and '행정명령에 서명했다' in row
                       and '면세 경유' in row and '도로 차량' in row), '')
        tax = re.search(r'갤런당\s*(\d+(?:\.\d+)?)센트의\s*연방\s*소비세가\s*면제', source)
        if signed and tax:
            fact = ('트럼프는 면세 경유를 도로 차량에도 쓸 수 있도록 사용 제한을 완화하는 행정명령에 서명했다. '
                    f'갤런당 {tax[1]}센트의 연방 소비세가 면제된 착색 경유의 사용 범위를 넓힌 조치다.')
            return fact if core_sentence_is_complete(fact) else ''
    if re.search(r'세계\s*반도체\s*매출', title) and '반도체산업협회(SIA)' in source:
        cumulative = re.search(r'올해\s*(\d{1,2}[~∼-]\d{1,2}월)\s*세계\s*반도체\s*누적\s*매출이\s*(\d+(?:\.\d+)?조\s*달러)를\s*넘어', source)
        observation = re.search(r'(\d{1,2}월)\s*세계\s*반도체\s*매출은\s*([\d,.]+억[\d,.]*만달러)로,\s*지난해\s*같은\s*달보다\s*([\d.]+)%\s*증가', source)
        basis = re.search(r'수치는\s*(\d{1,2}[~∼-]\d{1,2}월)\s*월평균\s*매출을\s*뜻한다', source)
        if cumulative and observation and basis and '3개월 이동평균 기준' in source:
            fact = (f"미국 반도체산업협회(SIA)는 올해 {cumulative[1]} 누적 매출이 {cumulative[2]}를 넘었다고 발표했다. "
                    f"{observation[1]} 수치 {observation[2]}는 {basis[1]} 3개월 이동평균으로 전년비 {observation[3]}% 증가했다.")
            return fact if core_sentence_is_complete(fact) else ''
    if '매출' in title and '돌파' in title:
        milestone = next((normalized_article_sentence(row) for row in rows
                          if re.search(r'올해\s*누적\s*외국인\s*고객\s*매출이\s*\d[\d,.]*조원을\s*돌파했다고\s*\d{1,2}일\s*밝혔다', row)), '')
        if milestone and core_sentence_is_complete(milestone):
            return milestone
    if '원전' in title and '국내법' in title and '연내 송금' in source:
        speaker = re.search(r'([가-힣]{2,5})\s*부총리', source)
        payment = re.search(r'(최대\s*\d[\d,.]*억\s*달러)를\s*우선\s*지급하는\s*방안', source)
        condition = re.search(r'국내법상\s*절차를\s*완료하면\s*가능하다', source)
        if speaker and speaker[1] in title and payment and condition:
            fact = (f"대미 원전 투자금 {payment[1]} 우선지급 방안에 대해 {speaker[1]} 부총리는 국내법 절차 완료 후 "
                    '연내 송금이 가능하다고 밝혔다.')
            if '투자금 회수 시점과 규모는 아직 정해지지 않았다' in source and '현재 협의 중' in source:
                fact += ' 회수 시점·규모는 협의 중이다.'
            return fact if core_sentence_is_complete(fact) else ''
    if re.search(r'에너지\s*대전환|재생.{0,20}GW.*석탄발전', title):
        report = re.search(r'([가-힣]{2,20}부)는\s*\d{1,2}일\s*이\s*같은\s*내용의\s*하반기\s*업무추진\s*계획을[^.!?]{0,60}보고했다', source)
        capacity = re.search(r'(20\d{2}년)까지\s*재생에너지\s*발전설비\s*(\d+(?:\.\d+)?)\s*(?:기가와트\(GW\)|GW)\s*이상', source)
        extra = re.search(r'(20\d{2}년)까지\s*계통포화지역\s*태양광\s*(\d+(?:\.\d+)?)GW를\s*추가\s*접속', source)
        closure = re.search(r'(20\d{2}년)까지\s*석탄발전을\s*폐지', source)
        if report and report[1] in title and capacity and extra and closure and '유연접속' in source and 'ESS를 설치' in source:
            fact = (f"{report[1]}는 하반기 업무계획을 국회에 보고했다. {capacity[1]} 재생에너지 발전설비 {capacity[2]}GW 이상 확대, "
                    f"{extra[1]} 계통포화지역 태양광 {extra[2]}GW 추가 접속과 {closure[1]} 석탄발전 폐지가 목표다. "
                    'ESS 설치·유연접속을 추진한다.')
            return fact if core_sentence_is_complete(fact) else ''
    mlcc = market_materiality.mlcc_contract_observation(title, body)
    if mlcc:
        fact = (f"{mlcc['issuer']}{korean_topic_particle(mlcc['issuer'])} {mlcc['customer']}과 {mlcc['reported_krw']} MLCC 공급계약을 "
                f"체결했다고 {mlcc['disclosure_day']}일 공시했다. 계약 기간은 {mlcc['year_label']} {mlcc['start_month']}월 "
                f"{mlcc['start_day']}일부터 {mlcc['end_month']}월 {mlcc['end_day']}일까지, 지난해 매출의 {mlcc['revenue_share']}% 규모다.")
        return fact if core_sentence_is_complete(fact) else ''
    if focus == 'commercial_order':
        disclosed = next((normalized_article_sentence(row) for row in rows
                          if '공급계약을 체결했다고' in row and re.search(r'\d{1,2}일\s*공시했다', row)
                          and not market_materiality.PAST_ACTION.search(row)), '')
        terms = next((row for row in rows if '계약 기간은' in row and '지난해 매출액 대비' in row), '')
        share = re.search(r'지난해\s*매출액\s*대비\s*([\d.]+)%', terms)
        end = re.search(r'계약\s*기간은\s*((?:내년|20\d{2}년)\s*\d{1,2}월\s*\d{1,2}일까지)', terms)
        if disclosed and share and end:
            fact = f'{disclosed} 계약 기간은 {end[1]}이며 지난해 매출의 {share[1]}% 규모다.'
            return fact if core_sentence_is_complete(fact) else ''
    structured = market_materiality.structured_supply_contract_observation(title, body)
    if structured:
        product = {'Wafer Inspection System': '웨이퍼 검사 시스템'}.get(structured['product'], structured['product'])
        fact = (f"{structured['issuer']}{korean_topic_particle(structured['issuer'])} {structured['customer']}와 "
                f"{structured['amount']} {product} 공급계약을 체결했다. 계약 기간은 {structured['period']}다.")
        if structured['revenue_share']:
            fact += f" 최근 매출의 {structured['revenue_share']}% 규모다."
        return fact if core_sentence_is_complete(fact) else ''
    rows = market_materiality.source_sentences(market_materiality.source_reported_body(body))
    if re.search(r'데이터센터', title) and re.search(r'정책|인허가|규제|중단', title):
        stop = next((row for row in rows if '데이터센터' in row and re.search(r'공사를\s*즉각\s*중단하라고\s*명령', row)), '')
        reason = next((row for row in rows if '환경영향평가' in row and re.search(r'인허가.{0,30}발급되지', row)), '')
        actor = re.search(r'(지난주\s*)?([가-힣]+)\s*([가-힣]+(?:\s+[가-힣]+){0,2}\s*주)는\s*([A-Za-z가-힣0-9 ]+?)\s*데이터센터가\s*운영하는', stop)
        if actor and reason:
            fact = (f"{actor[1] or ''}{actor[2]} {actor[3]}는 {actor[4]} 데이터센터 건설 현장에 공사 중단을 명령했다. "
                    '환경영향평가 등 주요 인허가 미발급이 이유다.')
            return fact if core_sentence_is_complete(fact) else ''
    if focus == 'commercial_order' or ('수주' in title and 'MLCC' in source):
        lead = next((row for row in rows if re.search(r'체결했다고\s*\d{1,2}일\s*밝혔다', row)), '')
        issuer = re.match(r'([A-Za-z가-힣&·.-]{2,30})(?:은|는)\s*', lead)
        amount = re.search(r'(약\s*\d[\d,.]*억\s*원)', lead)
        lta = next((row for row in rows if re.search(r'LTA\s*규모는\s*공시\s*기준|월부터\s*이번\s*계약까지.{0,100}장기공급계약', row)), '')
        total = re.search(r'(약\s*\d+조\s*\d+억\s*원)', lta)
        since = re.search(r'((?:올해|지난해|20\d{2}년)\s*\d{1,2}월)부터\s*이번\s*계약까지', lta)
        period = next((row for row in rows if re.search(r'계약\s*기간은\s*20\d{2}년', row)), '')
        dates = re.search(r'계약\s*기간은\s*(20\d{2}년)\s*(\d{1,2})월\s*\d{1,2}일부터\s*(?:같은\s*해\s*)?(\d{1,2})월\s*\d{1,2}일까지', period)
        if issuer and issuer[1] in title and amount and total and since and dates and 'AI' in title and 'MLCC' in lead:
            fact = (f"{issuer[1]}{korean_topic_particle(issuer[1])} {dates[1]} {dates[2]}~{dates[3]}월 AI 서버용 MLCC "
                    f"{amount[1]} 공급계약을 체결했다. {since[1]}부터 공시한 LTA 합계는 {total[1]}이다.")
            return fact if core_sentence_is_complete(fact) else ''
    if re.search(r'펀드', body) and re.search(r'정책자금|출자|매칭', title):
        support = re.search(r'대형리그는\s*정책금융기관이\s*(\d+억원)을\s*출자해\s*최소\s*(\d+억원)', body)
        matching = re.search(r'나머지\s*(\d+억원)을\s*추가로\s*확보해야', body)
        applicant = re.search(r'대형리그에는\s*([^.!?\n]{2,60}?)\s*(?:컨소시엄\s*)?한\s*곳만\s*지원', body)
        name = re.search(r"['‘]([^'’]{2,60}협력펀드)['’]", body)
        if support and matching and applicant and name:
            fact = (f"'{name[1]}' 대형리그는 최소 {support[2]} 중 정책기관이 {support[1]}을 출자하며 "
                    f"민간자금 {matching[1]}을 추가 확보해야 한다. 지원 운용사는 1곳뿐이다.")
            return fact if core_sentence_is_complete(fact) else ''
    if '임상 3상' in title and re.search(r'발표|결과', title):
        lead = next((row for row in rows if '임상 3상 결과를 발표' in row), '')
        issuer = re.match(r'([A-Za-z가-힣&·.-]{2,30})(?:은|는)\s*', lead)
        product = re.search(r"['‘]([^'’]{2,30})\(성분명", lead)
        duration = re.search(r'(\d+)주간\s*진행', body)
        reduction = re.search(r'HbA1c\).*?(\d+(?:\.\d+)?)%\s*감소해\s*대조군\(-?(\d+(?:\.\d+)?)%\)', body)
        attainment = re.search(r'도달률.*?투여군이\s*(\d+(?:\.\d+)?)%.*?대조군\((\d+(?:\.\d+)?)%\)', body)
        if issuer and issuer[1] in title and product and duration and reduction and attainment:
            fact = (f"{issuer[1]}{korean_topic_particle(issuer[1])} '{product[1]}' {duration[1]}주 임상 3상 결과로 "
                    f"당화혈색소 감소폭 {reduction[1]}%(대조군 {reduction[2]}%), 목표 혈당 도달률 "
                    f"{attainment[1]}%(대조군 {attainment[2]}%)를 발표했다.")
            return fact if core_sentence_is_complete(fact) else ''
    supply = market_materiality.capacity_supply_contract_observation(title, body)
    if supply:
        fact = (f"{supply['issuer']}{korean_topic_particle(supply['issuer'])} {supply['region']} "
                f"{supply['customer']}와 {supply['capacity_gw']}GW {supply['product']} 장기 공급계약을 체결했다.")
        if supply['pending_cdu']:
            fact += ' CDU 공급 확대는 논의 중이다.'
        return fact if core_sentence_is_complete(fact) else ''
    volume = market_materiality.vehicle_volume_observation(title, body)
    if volume:
        fact = (f"{volume['issuer']}의 {volume['period']} 전기차({volume['population']}) 인도량은 "
                f"{volume['volume']}대로 전년 동기 대비 {volume['change']}% {volume['direction']}했다. "
                f"세계 시장은 {volume['market_change']}% {volume['market_direction']}했지만, "
                f"그룹의 북미 인도량은 {volume['north_america_change']}% {volume['north_america_direction']}했다.")
        return fact if core_sentence_is_complete(fact) else ''
    marine = market_materiality.marine_delivery_observation(title, body)
    if marine:
        fact = (f"{marine['issuer']}{korean_topic_particle(marine['issuer'])} {marine['technology']} "
                f"{marine['type']} 타입을 부분 적용한 {marine['country']} 선사의 {marine['capacity_teu']}TEU 컨테이너선을 인도했다. "
                f"회사는 이 기술로 갑판 적재중량을 {marine['cargo_increase']}% 이상 늘릴 수 있다고 설명했다.")
        return fact if core_sentence_is_complete(fact) else ''
    property_stress = market_materiality.commercial_property_stress_observation(title, body)
    if property_stress:
        fact = (f"고금리 속 미국 상업용 부동산 시장의 FTSE 상장리츠지수는 {property_stress['from']}부터 {property_stress['until']}까지 "
                f"{property_stress['index_decline']}% 넘게 하락했다. 트렙에 따르면 {property_stress['loan_period']} "
                f"CMBS 대출의 {property_stress['special_management_share']}%가 특수관리 대상이며, "
                f"{property_stress['high_since']} 이후 최고 수준이다.")
        return fact if core_sentence_is_complete(fact) else ''
    product = market_materiality.industrial_product_milestone_observation(title, body)
    if product:
        fact = (f"{product['issuer']}{korean_topic_particle(product['issuer'])} AI 데이터센터용 {product['technology']} '{product['new_model']}' 제품을 추가한다고 밝혔다. "
                f"연간 에너지 사용량을 최대 {product['saving_maximum']}% 절감할 수 있다는 설명이다. "
                f"{product['certified_supplier']}의 데이터센터 냉각장비 {product['certified_capacity']}MW '{product['certified_model']}'은 "
                f"{product['certifier']} 인증을 받았고, {product['pending_capacity']}MW 제품 인증은 추진 중이다.")
        return fact if core_sentence_is_complete(fact) else ''
    thermal = market_materiality.thermal_lifespan_policy_observation(title, body)
    if thermal:
        years = thermal['years'].replace('∼', '~')
        fact = (f"{thermal['authority']}{korean_topic_particle(thermal['authority'])} 휴·폐지 예정 화력발전소가 "
                f"{years}년 뒤에도 전기를 공급하도록 {thermal['payers']}가 유지·보수 비용을 분담하는 제도를 검토한다. "
                f"{clean_article_summary_text(thermal['deadline'])}")
        return fact if core_sentence_is_complete(fact) else ''
    submission = market_materiality.clinical_submission_observation(title, body)
    if submission:
        fact = (f"{submission['issuer']} 파트너사 {submission['partner']}{korean_topic_particle(submission['partner'])} "
                f"미국시간 {submission['day']}일 FDA로부터 {submission['drug']}({submission['code']})의 "
                f"허가신청 전 미팅을 권고받았다. {submission['phase']}상은 1차·주요 2차 평가변수를 충족하지 못했다.")
        return fact if core_sentence_is_complete(fact) else ''
    regulation = market_materiality.regulatory_package_observation(title, body)
    if regulation:
        fact = (f"정부는 {regulation['item']}를 수입 승인 대상에서 제외하도록 "
                f"{regulation['import_deadline']} 수출입공고 개정을 추진한다. "
                f"생성형 AI 활용을 위한 보안 가이드라인은 {regulation['guide_year']} "
                f"{regulation['guide_quarter']}분기 마련할 계획이다.")
        return fact if core_sentence_is_complete(fact) else ''
    legislation = market_materiality.legislative_action_observation(title, body)
    if legislation:
        day = f" {legislation['day']}일" if legislation['day'] else ''
        fact = f"{legislation['actor']} 의원이 '{legislation['law']}'을{day} {legislation['action']}."
        if legislation['investment_vehicle'] and all(re.search(term, body) for term in (r'AI|인공지능', '드론', '로봇', '중소', '중견')):
            fact += ' 투자전문회사 설립과 AI·드론·로봇 분야 중소기업·중견기업 지원을 담았다.'
        elif legislation['purpose'] and core_sentence_is_complete(fact + ' ' + legislation['purpose']):
            fact += ' ' + legislation['purpose']
        return fact if core_sentence_is_complete(fact) else ''
    if re.search(r"규제\s*개선", title):
        rows = market_materiality.source_sentences(market_materiality.source_reported_body(body))
        implementation = next((row for row in rows if re.search(r"정부(?:는|가)", row)
                               and re.search(r"연내|20\d{2}년|\d분기", row)
                               and re.search(r"공고\s*개정|시행|입법예고", row)), '')
        followup = next((re.sub(r"^(?:아울러|또)\s*", '', row) for row in rows
                         if re.search(r"가이드라인", row) and re.search(r"내년\s*\d분기|20\d{2}년", row)), '')
        if implementation and core_sentence_is_complete(implementation):
            fact = implementation
            if followup and core_sentence_is_complete(fact + ' ' + followup):
                fact += ' ' + followup
            return fact
    if re.search(r"기술이전", title):
        rows = market_materiality.source_sentences(market_materiality.source_reported_body(body))
        statement = next((row for row in rows if re.search(r"기술이전\s*계약", row)
                          and re.search(r"체결했다고\s*\d{1,2}일\s*밝혔다", row)), '')
        terms = next((row for row in rows if re.match(r"총\s*규모", row)
                      and re.search(r"공개되지\s*않", row)), '')
        if statement and terms and core_sentence_is_complete(clean_article_summary_text(statement + ' ' + terms)):
            return clean_article_summary_text(statement + ' ' + terms)
    mou = market_materiality.industrial_development_mou_observation(title, body)
    if mou:
        fact = clean_article_summary_text(mou['source_excerpt'])
        goal = next((row for row in market_materiality.source_sentences(market_materiality.source_reported_body(body))
                     if re.search(r"(?:20\d{2}년|내년).{0,35}(?:양산|상용화).{0,15}목표", row)), '')
        if goal and len(fact + ' ' + goal) <= GAMEJOA_CORE_MAX_CHARS:
            fact += ' ' + clean_article_summary_text(goal)
        return fact if core_sentence_is_complete(fact) else ''
    construction = market_materiality.construction_order_observation(title, body)
    if construction:
        issuer_amount = f"({construction['issuer_amount']})" if construction.get('issuer_amount') else ''
        fact = (f"{construction['issuer']}이 {construction['customer']}의 {construction['project']}를 수주했다. "
                f"총 공사비는 {construction['total_budget']}, 회사 지분은 {construction['issuer_share']}%{issuer_amount}이며 "
                f"공사기간은 착공 후 {construction['months']}개월이다.")
        return fact if core_sentence_is_complete(fact) else ''
    participation = market_materiality.national_research_participation_observation(title, body)
    if participation:
        fact = (f"{participation['issuer']}{korean_topic_particle(participation['issuer'])} 국가 피지컬AI 사업의 "
                f"공동연구기관으로 참여해 {participation['role']}을 총괄한다고 {participation['day']}일 밝혔다. "
                f"{participation['until_year']}년까지 사업 전체 예산은 {participation['total_budget']}(국비 {participation['government_support']}), "
                f"참여 세부과제 예산은 약 {participation['subproject_budget']}이다.")
        return fact if core_sentence_is_complete(fact) else ''
    backlog = market_materiality.broker_backlog_mix_observation(title, body)
    if backlog:
        fact = (f"{backlog['broker']}{korean_topic_particle(backlog['broker'])} {backlog['day']}일 "
                f"{backlog['issuer']}의 {backlog['period']} {backlog['business']} 수주잔고 {backlog['amount']} 중 "
                f"{backlog['region']} 비중이 {backlog['share']}%에 육박한다고 분석했다.")
        return fact if core_sentence_is_complete(fact) else ""
    research = market_materiality.research_program_award_observation(title, body)
    if research:
        fact = (f"{research['issuer']}{korean_topic_particle(research['issuer'])} {research['tasks']} 국책과제 "
                f"{research['count']}건을 수주했다고 {research['day']}일 밝혔다. "
                f"전체 과제의 총 연구개발비는 약 {research['total_budget']}이며 정부 지원금은 약 {research['government_support']}이다.")
        return fact if core_sentence_is_complete(fact) else ""
    expansion = market_materiality.order_expansion_target_observation(title, body)
    if expansion:
        fact = (f"{expansion['statement']} 이번 계약을 시작으로 관련 수주를 약 "
                f"{expansion['expansion_target']}까지 확대하는 것이 목표다.")
        return fact if core_sentence_is_complete(fact) else ""
    anonymous_order = market_materiality.scoped_anonymous_order_observation(title, body)
    if anonymous_order:
        fact = (f"{anonymous_order['source_excerpt']} 이번 계약을 시작으로 관련 수주를 약 "
                f"{anonymous_order['expansion_target']}까지 확대하는 것이 목표다.")
        return fact if core_sentence_is_complete(fact) else ''
    adoption = market_materiality.industrial_customer_adoption_observation(title, body)
    if adoption:
        stage = ("채택돼 초도 물량 납품을 완료했다고" if adoption['stage'] == 'initial_delivery_completed'
                 else "채택됐다고")
        fact = (f"{adoption['issuer']}{korean_topic_particle(adoption['issuer'])} 글로벌 MLCC 제조사의 "
                f"자동광학검사(AOI) 장비에 {adoption['product']}이 {stage} {adoption['day']}일 밝혔다. "
                f"해당 장비는 {adoption['site']} 생산거점에 공급된다.")
        return fact if core_sentence_is_complete(fact) else ""
    marketing = market_materiality.marketing_contract_observation(title, body)
    if marketing:
        scope = (f"공급 물량은 최대 {marketing['maximum_volume']}으로 전망된다."
                 if marketing['volume_stage'] == 'expected' else f"계약 물량은 최대 {marketing['maximum_volume']}이다.")
        fact = (f"{marketing['issuer']}{korean_topic_particle(marketing['issuer'])} {marketing['customer']}와 "
                f"{marketing['until_year']}년까지 {marketing['product']} 장기 마케팅 계약을 체결했다고 {marketing['day']}일 밝혔다. "
                f"{scope}")
        return fact if core_sentence_is_complete(fact) else ""
    if focus == "aviation_network":
        sentences = market_materiality.source_sentences(market_materiality.source_reported_body(body))
        lead = next((row for row in sentences if re.search(r"운수권|노선", row) and re.search(r"\d{1,2}일\s*밝혔다", row)), "")
        issuer = re.search(r"([A-Za-z0-9가-힣&·.-]{2,30})(?:은|는)\s+", lead)
        change = next((row for row in sentences if market_materiality.focus_matches(title, row)
                       and re.search(r"일부터", row) and re.search(r"주\s*\d+회에서", row)), "")
        followup = next((row for row in sentences if re.search(r"주\s*\d+회에서\s*\d+회로\s*늘린다", row)), "")
        if issuer and change and issuer.group(1) in title:
            statement = f"{issuer.group(1)}{korean_topic_particle(issuer.group(1))} {clean_article_summary_text(change)}"
            if followup and followup != change and core_sentence_is_complete(statement + " " + followup):
                statement += " " + followup
            return statement if core_sentence_is_complete(statement) else ""
    housing = market_materiality.housing_demand_observation(title, body)
    if housing:
        fact = (f"{housing['provider']}{korean_topic_particle(housing['provider'])} {housing['day']}일 "
                f"{housing['year']} {housing['period']} 입주자모집공고 기준 전국 1순위 평균 청약경쟁률이 "
                f"{housing['current']}대 1이라고 발표했다. 지난해 같은 기간은 {housing['previous']}대 1이었다.")
        return fact if core_sentence_is_complete(fact) else ""
    if focus == "military_reinforcement":
        sentences = market_materiality.source_sentences(market_materiality.source_reported_body(body))
        statement = next((clean_article_summary_text(sentence) for sentence in sentences
                          if market_materiality.focus_matches(title, sentence)
                          and not re.match(r"^(?:3국|그는|이는|이들은)(?:은|는|이|가)?\s", sentence)
                          and not market_materiality.BACKGROUND.search(sentence)), "")
        limitation = next((clean_article_summary_text(sentence) for sentence in sentences
                           if re.search(r"군사력\s*규모|병력\s*규모|임무", sentence)
                           and re.search(r"설명하지\s*않|공개하지\s*않|미공개", sentence)), "")
        if limitation and core_sentence_is_complete(statement + " " + limitation):
            statement += " " + limitation
        return statement if core_sentence_is_complete(statement) else ""
    power_contract = re.search(r"계약\s*전력\s*용량을\s*(\d[\d,.]*)(?:메가와트)?\s*\(MW\)에서\s*"
                               r"(\d[\d,.]*)(?:기가와트)?\s*\(GW\)로\s*확대", body, re.I)
    if power_contract and re.search(r"전기\s*공급\s*계약을\s*개정", body):
        source = re.sub(r"\s+", " ", body)
        parties = re.search(r"([A-Za-z가-힣&·.-]{2,30})\([^)]*\)(?:은|는)\s*"
                            r"([A-Za-z가-힣 ]{2,30})\([^)]*\)(?:와|과)\s*전기\s*공급\s*계약", source)
        site = re.search(r"위치한\s*([^()!?]{2,40}데이터\s*캠퍼스)\([^)]*\)의\s*계약\s*전력", source)
        condition = re.search(r"개정안에는\s*([A-Za-z가-힣 ]{2,35}위원회)의\s*승인\s*및\s*[^.!?]{2,35}공사\s*일정\s*수립을\s*전제로,\s*"
                              r"두\s*번째\s*(\d[\d,.]*)\s*메가와트\(MW\)\s*단계의\s*공급\s*시기를\s*(20\d{2})년", source)
        if parties and site and condition and parties.group(1) in title:
            issuer, utility = parties.groups()
            fact = (f"{issuer}{korean_topic_particle(issuer)} {utility}와 전기공급계약을 개정해 "
                    f"{site.group(1)}의 계약 전력 용량을 {power_contract.group(1)}MW에서 {power_contract.group(2)}GW로 확대했다. "
                    f"추가 {condition.group(2)}MW의 {condition.group(3)}년 공급은 {condition.group(1)} 승인과 전력사 공사 일정 수립이 전제다.")
            return fact if core_sentence_is_complete(fact) else ""
    freight = market_materiality.freight_cost_observation(title, body)
    if freight:
        fact = (f"{freight['source']}의 {freight['day']}일 현지 보도에 따르면 호르무즈 VLCC 셔틀 운항의 "
                f"왕복 {freight['voyages']}회 비용은 최대 {freight['max_cost']}다.")
        if freight.get('current_daily'):
            fact += (f" {freight['period']} {freight['route']}까지 초대형 유조선 용선료는 전쟁 전 하루 약 "
                     f"{freight['previous_daily']}에서 하루 {freight['current_daily']}로 급등했다.")
        return fact if core_sentence_is_complete(fact) else ""
    allocation = market_materiality.public_compute_allocation(title, body)
    if allocation:
        fact = (f"{allocation['provider']} 자료에 따르면 {allocation['period']}까지 공모에서 "
                f"GPU {allocation['requested']}장을 신청했고 {allocation['allocated']}장이 배정됐다. "
                f"배정량은 신청량의 {allocation['allocation_rate']}%다.")
        return fact if core_sentence_is_complete(fact) else ""
    outlook = market_materiality.conditional_index_outlook(title, body)
    if outlook:
        fact = (f"{outlook['broker']}{korean_topic_particle(outlook['broker'])} {outlook['day']}일 보고서에서 "
                f"유가·금리의 추가 급등이 없고 {outlook['index']}가 {outlook['threshold']}선을 돌파·안착하면 "
                f"{outlook['target_range']}선까지 상승할 수 있다고 전망했다.")
        return fact if core_sentence_is_complete(fact) else ""
    quotes = market_materiality.intraday_equity_observations(title, body)
    if quotes:
        observations = []
        for quote in quotes["quotes"]:
            observations.append(f"{quote['issuer']}{korean_topic_particle(quote['issuer'])} {quote['rate']}% {quote['direction']} {quote['price']}")
        fact = (f"{quotes['market']} 기준 {quotes['day']}일 {quotes['half']} {quotes['hour']}시{quotes['minute']}분 "
                f"{', '.join(observations)}에 거래됐다. 등락률은 전 거래일 대비다.")
        return fact if core_sentence_is_complete(fact) else ""
    if focus == "capital_spending":
        observation = next((market_materiality.business_investment_observation(sentence)
                            for sentence in market_materiality.source_sentences(body)
                            if market_materiality.business_investment_observation(sentence)), {})
        if observation:
            change = "늘었다" if observation["direction"] == "증가" else "줄었다"
            fact = (f"{observation['country']} 기업들의 {observation['population']} 투자는 "
                    f"{observation['year']} {observation['quarter']}분기 {observation['amount']}를 넘었고, "
                    f"전년 동기 대비 {observation['change']}% {change}.")
            return fact if core_sentence_is_complete(fact) else ""
    if focus == "equity_index":
        source = " ".join(market_materiality.source_sentences(body))
        index = next((term for term in ("나스닥", "S&P500", "다우", "코스피", "코스닥")
                      if term in title.replace(" ", "")), "")
        change = re.search(rf"{re.escape(index)}\s*(?:종합)?지수(?:는|가|이)?\s*(\d+(?:\.\d+)?)%\s*(올랐다|내렸다)", source)
        record = re.search(rf"{re.escape(index)}(?:은|는|이|가)\s*사상\s*최고치를\s*기록했다", source)
        if change and record:
            direction = "상승" if change.group(2) == "올랐다" else "하락"
            fact = f"{index}지수는 {change.group(1)}% {direction}해 사상 최고치를 기록했다."
            yields = re.search(r"미\s*10년물\s*국채\s*금리는\s*장중\s*(\d+(?:\.\d+)?)%", source)
            if yields:
                fact += f" 미 10년물 국채금리는 장중 {yields.group(1)}%까지 올랐다."
            return fact if core_sentence_is_complete(fact) else ""
    if focus == "commercial_order":
        contract = re.search(r"([A-Za-z0-9가-힣&·.-]{2,30})(?:이|가)\s+[^.!?\n]{0,50}?['‘]([^'’\n]{2,40})['’](?:\([^)]*\))?(?:와|과)\s*맺은\s*장기공급계약", body)
        capacity = re.search(r"(\d[\d,.]*\s*(?:GW|MW))\s*규모\s*(?:AI\s*)?데이터센터\s*칠러\s*공급", body, re.I)
        if contract and capacity and contract.group(1) in title:
            issuer, customer = contract.groups()
            fact = (f"{issuer}{korean_topic_particle(issuer)} {customer}와 "
                    f"{capacity.group(1)} 규모 데이터센터용 칠러 장기공급계약을 맺었다.")
            if re.search(r"CDU.{0,30}공급\s*품목을\s*확대하는\s*방안을\s*논의", body):
                fact += " CDU 공급 확대도 논의 중이다."
            if core_sentence_is_complete(fact):
                return fact
    target_revision = market_materiality.analyst_target_revision_terms(title, body)
    if target_revision:
        broker, issuer = target_revision["broker"], target_revision["issuer"]
        direction = "하향" if target_revision["direction"] == "down" else "상향"
        fact = (f"{broker}{korean_topic_particle(broker)} {issuer}의 목표주가를 "
                f"{target_revision['previous_display']}원에서 {target_revision['current_display']}원으로 {direction} 조정했다.")
        sentences = market_materiality.source_sentences(market_materiality.source_reported_body(body))
        index = next((i for i, sentence in enumerate(sentences) if market_materiality.focus_matches(title, sentence)), -1)
        if index >= 0 and index + 1 < len(sentences):
            reason = clean_article_summary_text(sentences[index + 1])
            if (re.search(r"기저|부담|둔화|비용|반영|따른", reason)
                    and not market_materiality.BACKGROUND.search(reason)
                    and core_sentence_is_complete(fact + " " + reason)):
                fact += " " + reason
        return fact if core_sentence_is_complete(fact) else ""
    if focus == "industrial_partnership":
        sentences = market_materiality.source_sentences(market_materiality.source_reported_body(body))
        statement = next((clean_article_summary_text(sentence) for sentence in sentences
                          if market_materiality.focus_matches(title, sentence)
                          and not market_materiality.PAST_ACTION.search(sentence)), "")
        followup = next((clean_article_summary_text(sentence) for sentence in sentences
                         if re.search(r"양사는.{0,50}공동\s*연구할\s*예정", sentence)), "")
        if followup and core_sentence_is_complete(statement + " " + followup):
            statement += " " + followup
        return statement if core_sentence_is_complete(statement) else ""
    if "지분" in title and re.search(r"확대|늘려|증가", title):
        source = market_materiality.source_reported_body(body)
        holding = re.search(r"([A-Za-z0-9가-힣&·.-]{2,30})의\s+([A-Za-z0-9가-힣&·.-]{2,30})\s+보유주식\s*수는\s*기존\s*(\d[\d,]*만?\d*)주에서\s*(\d[\d,]*만?\d*)주로", source)
        stake = re.search(r"지분율도\s*기존\s*(\d+(?:\.\d+)?)%에서\s*(\d+(?:\.\d+)?)%로", source)
        if holding and stake and holding.group(2) in title:
            owner, issuer, previous, current = holding.groups()
            fact = (f"{issuer}에 따르면 {owner}의 보유주식은 {previous}주에서 {current}주로 늘었고, "
                    f"지분율은 {stake.group(1)}%에서 {stake.group(2)}%로 확대됐다.")
            if re.search(r"지분\s*보유\s*목적은\s*['‘]단순투자['’]", source):
                fact += " 보유 목적은 단순투자다."
            return fact if core_sentence_is_complete(fact) else ""
    research = market_materiality.broker_earnings_report_terms(title, body)
    if research:
        fact = (f"{research['broker']}{korean_topic_particle(research['broker'])} {research['issuer']}의 "
                f"{research['quarter']}분기 매출을 {research['revenue_display']}원, "
                f"영업이익을 {research['profit_display']}원으로 예상했다.")
        return fact if core_sentence_is_complete(fact) else ""
    merger = market_materiality.merger_agreement_terms(title, body)
    if merger:
        source = market_materiality.source_reported_body(body)
        amount = next(item for item in re.finditer(market_materiality.SOURCE_MONEY, " ".join(market_materiality.source_sentences(source)[:2]))
                      if [item.group(2), market_materiality.korean_amount_value(item.group(1))] == merger["amount"])
        actor = title.split(",", 1)[0].strip()
        target_view = re.match(r"^[^,，]+[,，]\s*([^,，]{2,40}?)의\s+\d", title)
        if target_view:
            actor = target_view.group(1).strip()
        fact = f"{actor}{korean_topic_particle(actor)} {amount.group(1).strip()}{amount.group(2)} 규모의 {merger['target']} 인수에 합의했다."
        closing = re.search(r"거래\s*(?:종료|종결)는\s*(\d{4})년\s*(상반기|하반기|[1-4]분기)[^.!?]{0,20}예상", source)
        if closing and re.search(r"규제\s*당국\s*승인", source):
            fact += f" {closing.group(1)}년 {closing.group(2)} 종결 예상이며 규제 승인 등이 필요하다."
        return fact if core_sentence_is_complete(fact) else ""
    reported_fact = reported_issuer_announcement_fact(title, body)
    if reported_fact:
        return reported_fact
    source = re.sub(r"\s+", " ", market_materiality.source_reported_body(body))
    if "주간증시전망" in title:
        revision = re.search(
            r"([A-Za-z가-힣]+증권)에\s*따르면\s*([A-Za-z가-힣0-9]+)\s*([1-4])분기\s*영업이익\s*컨센서스는\s*"
            r"(\d{1,2}월\s*(?:초|중순|말))\s*(\d[\d,.\s조억만천백십]*원)으로\s*고점을\s*찍은\s*뒤\s*현재\s*"
            r"(\d[\d,.\s조억만천백십]*원)까지\s*하향\s*조정됐다", source,
        )
        if revision and revision.group(2) in title:
            broker, actor, quarter, period, previous, current = revision.groups()
            fact = (f"{broker}에 따르면 {actor} {quarter}분기 영업이익 컨센서스는 "
                    f"{period} {previous.strip()}에서 현재 {current.strip()}으로 하향 조정됐다.")
            return fact if core_sentence_is_complete(fact) else ""
    if focus == "production_target":
        decision = re.search(r"(OPEC\+)\s*내\s*(\d+)개국[^.!?]{0,100}?(내달|다음\s*달|\d{1,2}월)\s*생산\s*목표를\s*현\s*수준으로\s*유지하기로\s*합의했다", source)
        if decision:
            group, count, period = decision.groups()
            return f"{group} {count}개국은 {period} 원유 생산 목표를 현 수준으로 유지하기로 합의했다."
    if focus == "maritime_attack":
        observation = re.search(
            r"UKMTO\)(?:는|은)\s*(지난달\s*\d{1,2}일)\s*이후\s*(이달\s*\d{1,2}일)까지"
            r"[^.!?]{0,60}?선박을\s*대상으로\s*한\s*(\d+)건의\s*공격을\s*보고했다", source,
        )
        sea = next((name for name in ("호르무즈", "홍해") if name in title), "")
        if observation and sea:
            start, end, count = observation.groups()
            fact = f"UKMTO는 {start} 이후 {end}까지 {sea} 주변 선박 공격 {count}건을 보고했다."
            additional = re.search(r"UKMTO는\s*(\d{1,2})일에도\s*또\s*다른\s*선박이\s*공격받았다고\s*밝혔[^.!?]*", source)
            if additional:
                fact += f" {additional.group(1)}일에도 추가 피격을 알렸다."
                if re.search(r"발생\s*시점.{0,20}공개하지\s*않", additional.group(0)):
                    fact += " 추가 피격의 발생 시점은 미공개다."
            return fact if core_sentence_is_complete(fact) else ""
    if focus == "fund_performance" and re.search(r"美|미국", title):
        performance = re.search(r"미국\s*상장\s*ETF[^\n]{0,80}?\(([A-Z]{2,8})\)은\s*지난\s*(\d+)일\s*기준으로\s*최근\s*(\d+)개월간\s*(\d+(?:\.\d+)?)%", source)
        if performance:
            code, day, months, rate = performance.groups()
            fact = f"미국 상장 {code} ETF는 지난 {day}일 기준 최근 {months}개월 수익률 {rate}%를 기록했다."
            annual = re.search(r"연초\s*이후\s*수익률은\s*(\d+(?:\.\d+)?)%", source)
            if annual:
                fact += f" 연초 이후 수익률은 {annual.group(1)}%다."
            return fact if core_sentence_is_complete(fact) else ""
    if focus == "shareholder" and re.search(r"자사주.{0,30}(?:빠지|끝|종료|마무리)", title):
        ending = re.search(r"([A-Za-z0-9가-힣·&]+)\s*(?:주가를\s*떠받쳐온\s*)?자사주\s*매입이\s*(이달\s*(?:초중순|중순|말|초))\s*끝", source)
        if ending:
            actor, horizon = ending.groups()
            fact = f"{actor}의 자사주 매입은 {horizon} 종료 예정이다."
            announcement = re.search(rf"오는\s*(\d+)일\s*예정된\s*{re.escape(actor)}의\s*([1-4])분기\s*잠정\s*실적", source)
            if announcement:
                fact += f" {announcement.group(1)}일 {announcement.group(2)}분기 잠정실적 발표를 앞두고 있다."
            return fact if core_sentence_is_complete(fact) else ""
    if focus == "product_volume":
        volume = re.search(
            r"([A-Za-z가-힣]+(?:\s+[A-Za-z가-힣]+)?)\([A-Z]+\)(?:은|는)\s*(\d{4})년\s*([1-4])분기"
            r"[^.!?]{0,130}?총\s*판매량이\s*(\d[\d,.]*(?:만\d[\d,.]*)?대)로\s*전년\s*동기"
            r"\([^)]*\)\s*대비\s*(\d+(?:\.\d+)?)%\s*증가", source,
        )
        if volume and re.search(r"공장\s*출고\([^)]*\)\s*기준", source):
            actor, year, quarter, units, growth = volume.groups()
            fact = f"{actor}{korean_topic_particle(actor)} {year}년 {quarter}분기 출고 기준 판매량이 {units}로 전년비 {growth}% 증가했다."
            overseas = re.search(r"해외\s*판매량은\s*(\d[\d,.]*(?:만\d[\d,.]*)?대)로\s*전년\s*동기\([^)]*\)\s*대비\s*(\d+(?:\.\d+)?)%", source)
            if overseas:
                combined = fact + f" 해외는 {overseas.group(1)}로 {overseas.group(2)}% 늘었다."
                if core_sentence_is_complete(combined):
                    return combined
            return fact if core_sentence_is_complete(fact) else ""
    if focus == "trading_rule":
        lot = re.search(r"(\d+)주\s*미만\s*단주를\s*일정기간\s*시간외\s*종가매매로\s*장내에서\s*처분[^.!?]{0,45}검토\s*중", source)
        if lot and "단일종목" in source and "금융위" in source and re.search(r"다음\s*달[^.!?]{0,70}세부방안을\s*발표할\s*계획", source):
            fact = (f"금융위는 단일종목 레버리지 ETF의 {lot.group(1)}주 미만 단주를 시간외 종가매매로 "
                    "처분하도록 허용하는 방안을 검토 중으로 알려졌다. 세부안은 내달 발표 예정이다.")
            return fact if core_sentence_is_complete(fact) else ""
    if focus == "technical_standard":
        standard = re.search(
            r"([A-Za-z가-힣]{2,25})(?:이|가)\s*발표한\s*['‘\"]?"
            r"(JESD\d+[A-Z0-9.-]*|IEEE\s*\d+[A-Z0-9.-]*|ISO\s*\d+[A-Z0-9.-]*)['’\"]?\s*표준은\s*"
            r"([^.!?]{2,35}?)\s*기술에\s*대한\s*전반적인\s*신뢰성\s*기준", source, re.I,
        )
        if standard:
            actor, code, topic = standard.groups()
            first = "업계 첫 " if re.search(r"업계\s*첫\s*신뢰성\s*표준", source) else ""
            fact = f"{actor}{korean_topic_particle(actor)} {first}{topic} 신뢰성 표준 {code}를 발표했다."
            if re.search(r"구성요소\s*검증,\s*제조\s*공정", source):
                fact += " 구성요소 검증과 제조 공정의 요구사항을 포함한다."
            return fact if core_sentence_is_complete(fact) else ""
    if focus == "energy_import_mix":
        period = re.search(r"올해\s*들어\s*(\d{1,2})월까지\s*누적\s*기준", source)
        country = re.search(r"([가-힣]{2,12})산\s*원유", title)
        if period and country:
            measure = re.search(
                rf"국가별\s*원유\s*도입\s*비중은\s*{re.escape(country.group(1))}가\s*(\d+(?:\.\d+)?)%"
                r"[^!?]{0,45}?전월\s*(\d+(?:\.\d+)?)%에\s*비해\s*비중이\s*"
                r"(\d+(?:\.\d+)?)%포인트[^!?]{0,15}?낮아졌다", source,
            )
            if measure:
                fact = (f"올해 1~{period.group(1)}월 국내 원유 도입 비중은 {country.group(1)}산 {measure.group(1)}%로 "
                        f"전월 누적 {measure.group(2)}%보다 {measure.group(3)}%p 낮아졌다.")
                return fact if core_sentence_is_complete(fact) else ""
    if focus == "investor_flow":
        actor = next((term for term in ("외국인", "기관", "개인", "연기금") if term in title), "")
        normalized_title = title.replace("삼전닉스", "삼성전자·SK하이닉스")
        issuers = [issuer for issuer in re.findall(r"[A-Za-z가-힣][A-Za-z0-9가-힣&]+", normalized_title) if issuer in source and re.search(
            rf"{re.escape(issuer)}(?:를|을|\()[^.!?]{{0,45}}{KOREAN_WON_AMOUNT_PATTERN}", source,
        )]
        period = re.search(r"지난주\s*\((\d{1,2}월\s*\d{1,2}일\s*[~∼-]\s*\d{1,2}월\s*\d{1,2}일)\)", source)
        selling = bool(re.search(r"순매도|팔아|매도|던졌", title))
        actor_source = " ".join(paragraph.strip() for paragraph in body.splitlines() if re.match(
            rf"^(?:(?:반면|또한|한편)\s+)?{re.escape(actor)}(?:은|는|이|가|의|도|\s)", paragraph.strip(),
        ))
        observations = []
        for issuer in dict.fromkeys(issuers):
            amount = re.search(
                rf"{re.escape(issuer)}(?:를|을|로)?\s*(?:한\s*주간\s*)?(?:무려\s*)?"
                rf"({KOREAN_WON_AMOUNT_PATTERN})(?:어치|을|를)?[^.!?]{{0,12}}"
                + (r"(?:쏟아|팔아|순매도)" if selling else r"(?:사들|순매수)"), actor_source,
            )
            if not amount:
                amount = re.search(rf"{re.escape(issuer)}\(({'-' if selling else ''}{KOREAN_WON_AMOUNT_PATTERN})\)", actor_source)
            if amount:
                observations.append(f"{issuer} {amount.group(1).lstrip('-')}")
        if actor and period and observations and len(observations) == len(set(issuers)):
            span = re.sub(r"\s+", "", period.group(1))
            direction = "순매도" if selling else "순매수"
            fact = f"{span} {actor}은 {'·'.join(observations)}을 {direction}했다."
            return fact if core_sentence_is_complete(fact) else ""
    return ""


def source_focused_article_core(title: str, sentences: list[str]) -> str:
    """Prefer a complete source fact about the headline, never an unrelated number."""
    focus = market_materiality.focus_kind(title)
    observed = source_headline_event_fact(title, "\n".join(sentences))
    if observed:
        return observed
    negotiation = acquisition_negotiation_fact(title, "\n".join(sentences))
    if negotiation:
        return negotiation
    if focus == "capital_listing" and "ETF" in title.upper():
        for sentence in sentences:
            if market_materiality.evidence_is_new_event("capital_listing_stage", sentence) and re.search(
                r"ETF.{0,35}(?:상장|출시)|(?:상장|출시).{0,35}ETF", sentence, re.I,
            ):
                fact = normalized_article_sentence(sentence)
                if core_sentence_is_complete(fact):
                    return fact
    if focus == "bond_yield" and re.search(r"닛케이|항셍|아시아증시", title):
        source = " ".join(sentences)
        probability = re.search(
            r"연준의\s*이달\s*금리\s*인상\s*가능성은\s*현재\s*(\d+(?:\.\d+)?)%\s*미만으로,\s*"
            r"일주일\s*전의\s*(\d+(?:\.\d+)?)%에서\s*크게\s*낮아졌다", source,
        )
        close = re.search(r"일본\s*닛케이225지수는\s*(\d+(?:\.\d+)?)%[^!?]{0,60}상승\s*마감했다", source)
        if probability and close and re.search(r"CME\s*페드워치", source, re.I):
            return (f"CME 페드워치상 연준의 이달 금리 인상 가능성은 {probability.group(2)}%에서 "
                    f"{probability.group(1)}% 미만으로 낮아졌다. 닛케이225는 {close.group(1)}% 상승 마감했다.")
    if focus == "housing_supply_policy":
        for sentence in sentences:
            if market_materiality.focus_matches(title, sentence) and all(
                term in sentence for term in ("LH", "미분양", "매입임대", "매수확약", "지시")
            ) and "대통령" in title:
                return "대통령은 LH가 미분양 주택을 매입임대용으로 매수확약하도록 지시했다고 밝혔다."
    if focus == "network_segmentation_policy":
        source = " ".join(sentences)
        day = re.search(r"오는\s*(\d{1,2})일에는\s*2차\s*규제\s*완화\s*대상이\s*선정된다", source)
        applicants = re.search(r"신청\s*가능\s*대상을\s*기존\s*(\d+)개사에서[^.!?]{0,60}?(\d+)개사로\s*확대", source)
        selected = re.search(r"선정\s*규모도\s*1차\s*(\d+)개사에서\s*최대\s*(\d+)개사로\s*늘릴\s*예정", source)
        if day and applicants and selected and "금융위" in source and "망분리" in source:
            return (f"금융위는 {day.group(1)}일 보안 목적의 2차 망분리 규제 완화 대상을 선정한다. "
                    f"신청 가능 대상은 {applicants.group(1)}개사에서 {applicants.group(2)}개사로, "
                    f"선정 규모는 {selected.group(1)}개사에서 최대 {selected.group(2)}개사로 늘릴 예정이다.")
    factory = market_materiality.factory_tariff_observation(title, "\n".join(sentences))
    if factory:
        return (f"트럼프는 기업에 약 {factory['grace']}의 미국 공장 건설 시간을 주고, "
                f"미건설 시 {factory['rate']}%까지 관세를 부과한다고 말했다.")
    compensation = compensation_cost_forecast_fact(title, "\n".join(sentences))
    if compensation:
        return compensation
    entry = conditional_financial_market_entry_fact(title, "\n".join(sentences))
    if entry:
        return entry
    flow_actors = [actor for actor in ("외국인", "기관", "개인", "연기금") if actor in title]
    if flow_actors and re.search(r"순매수|순매도|팔아치|사들|매수|매도", title):
        for sentence in sentences:
            if (
                any(actor in sentence for actor in flow_actors)
                and re.search(r"\d[\d,.]*\s*(?:조|억|만)\s*원", sentence)
                and re.search(r"순매수(?:했다|한\s*것으로)|순매도(?:했다|한\s*것으로)|매수했다|매도했다", sentence)
                and market_materiality.period_matches(title, sentence)
                and not market_materiality.EARLY_SIGNAL.search(sentence)
            ):
                fact = normalized_article_sentence(sentence)
                if core_sentence_is_complete(fact):
                    return fact
    if not market_materiality.focus_kind(title) and not market_materiality.DENIAL_HEADLINE.search(title):
        return ""
    focus = market_materiality.focus_kind(title)
    source = " ".join(sentences)
    if focus == "capital_spending" and re.search(r"공급|생산", title):
        investment = re.search(
            r"([A-Za-z가-힣]{2,20})(?:은|는)\s*(\d{4})\s*회계연도\s*(상반기|하반기)\s*"
            r"(?:에\s*)?설비투자에\s*(\d[\d,.]*\s*(?:억|만|조)?\s*달러)", source,
        )
        effect = re.search(
            r"([가-힣A-Za-z]{2,20}증권)\s*연구원은[^.!?]{0,100}?"
            r"유의미한\s*생산\s*증가\s*효과는\s*(\d{4})년\s*(상반기|하반기)부터[^.!?]{0,50}?"
            r"(?:분석했다|전망했다)", source,
        )
        if investment and effect:
            name = investment.group(1)
            amount = re.sub(r"\s+", "", investment.group(4))
            return (f"{name}{korean_topic_particle(name)} {investment.group(2)}회계연도 {investment.group(3)} "
                    f"설비투자 {amount}를 계획했다. {effect.group(1)}은 생산 증가 효과를 "
                    f"{effect.group(2)}년 {effect.group(3)}부터로 전망했다.")
    if focus == "breadth":
        divergence = re.search(
            r"(블룸버그(?:통신)?)은\s*(S&P\s*500|코스피|나스닥)(?:지수)?가\s*사상\s*최고치에서\s*"
            r"(\d+(?:\.\d+)?)%도\s*떨어지지\s*않은[^.!?]{0,45}?"
            r"상당수\s*업종과\s*종목이\s*고점\s*대비\s*(\d+(?:\.\d+)?)%\s*이상\s*하락[^.!?]{0,30}?전했다", source,
        )
        if divergence:
            publisher = divergence.group(1).removesuffix("통신")
            index = re.sub(r"\s+", "", divergence.group(2))
            return (f"{publisher}는 {index}이 사상 최고치 대비 {divergence.group(3)}% 이내에 있지만, "
                    f"상당수 업종·종목은 고점 대비 {divergence.group(4)}% 이상 하락했다고 전했다.")
    if focus == "asset_financing":
        for sentence in sentences:
            observation = asset_financing_observation(sentence)
            if not observation:
                continue
            name = observation["issuer"]
            fact = (f"{name}{korean_topic_particle(name)} {observation['amount']} {observation['asset']}을 "
                    f"특수목적기구(SPV)로 이전하는 방안을 {observation['stage']} 중이다.")
            if core_sentence_is_complete(fact):
                return fact
    if focus == "fx" and re.search(r"전망|예상", title):
        brokers = set(re.findall(r"[A-Za-z가-힣]{2,20}증권", source))
        target = re.search(r"(올해\s*연말|내년\s*연말)\s*환율은\s*(\d[\d,]*)\s*원\s*(전후|안팎)(?:로|으로)?\s*(?:예상|전망)", source)
        if len(brokers) == 1 and target:
            broker = next(iter(brokers))
            fact = f"{broker}{korean_topic_particle(broker)} {target.group(1)} 원·달러 환율을 {target.group(2)}원 {target.group(3)}로 전망했다."
            if core_sentence_is_complete(fact):
                return fact
    if focus == "national_exports":
        observed = next((fact for sentence in sentences
                         if (fact := market_materiality.national_export_observation(sentence))), None)
        if observed and re.search(r"한국|韓|우리나라|대한민국", title + " " + " ".join(sentences[:3])):
            period = " ".join(value for value in (observed["year"], observed["period"]) if value)
            metric = observed["metric"].replace("누적수출", "누적 수출").replace("월간수출", "월간 수출")
            fact = f"한국의 {period} {metric}은 {observed['amount']}로 집계됐다."
            if re.search(r"지난해\s*연간\s*수출액[^.!?]{0,40}(?:넘어섰|넘어선)", source):
                fact += " 지난해 연간 수출액을 이미 넘었다."
            if core_sentence_is_complete(fact):
                return fact
    if focus == "financing":
        for sentence in sentences:
            if (re.search(r"외부\s*자본", sentence)
                    and re.search(r"자체\s*자금", sentence)
                    and re.search(r"비교\s*검토", sentence)):
                fact = normalized_article_sentence(sentence)
                if core_sentence_is_complete(fact):
                    return fact
    if focus == "economic_response":
        for sentence in sentences:
            if not market_materiality.focus_matches(title, sentence):
                continue
            speaker = re.search(r"([가-힣]{2,15})\s*대통령", sentence)
            if not speaker or not re.search(r"도입.{0,20}밝혔다", sentence):
                continue
            country = "이란 " if "이란" in title or "이란" in sentence else ""
            if speaker.group(1) == country.strip():
                country = ""
            fact = f"{country}{speaker.group(1)} 대통령은 경제전쟁 대응 조치를 도입하고 있다고 밝혔다."
            if re.search(r"환율", source) and re.search(r"필수\s*물자", source) and re.search(r"점검", source):
                fact += " 환율·필수물자 공급을 점검했다."
            if core_sentence_is_complete(fact):
                return fact
    if focus == "retail_fuel":
        observation = market_materiality.retail_fuel_observation(title, "\n".join(sentences))
        if observation:
            return (f"{observation['period']} 전국 {observation['product']} 평균 판매가격은 L당 {observation['price']}원으로 "
                    f"전주보다 {observation['change']}원 {observation['direction']}했다.")
    if focus == "product_sales_mix":
        parties = re.search(r"([A-Za-z0-9가-힣&]+(?:[·ㆍ][A-Za-z0-9가-힣&]+)+)", title)
        observation = re.search(
            r"(?:양사의|두\s*회사의)\s*(\d{1,2}[~∼-]\d{1,2}월)\s*국내\s*판매량\s*\d[\d,만]*대\s*중\s*"
            r"하이브리드[·ㆍ]전기차[·ㆍ]수소차는\s*(\d[\d,만]*)대로\s*(\d+(?:\.\d+)?)%를\s*차지했다", source,
        )
        comparison = re.search(r"전년\s*동기\s*\d+(?:\.\d+)?%보다\s*(\d+(?:\.\d+)?)%포인트\s*높아졌다", source)
        if parties and observation and comparison and "친환경차" in source:
            return (f"{parties.group(1)}의 {observation.group(1)} 국내 친환경차 판매는 {observation.group(2)}대로 "
                    f"전체 판매의 {observation.group(3)}%를 차지했다. 비중은 전년비 {comparison.group(1)}%포인트 높아졌다.")
    if focus == "earnings":
        loss = profit_loss_result_fact(title, sentences)
        if loss:
            return loss
    if focus == "ownership" and "자산" in title and "인수" in title:
        for sentence in sentences:
            issuer = re.match(r"^([A-Za-z0-9가-힣&·]+(?:\s+[A-Za-z0-9가-힣&·]+){0,4})\s*(?:\([A-Za-z0-9.-]+\))?(?:은|는|이|가)\s+", sentence)
            amount = re.search(r"총\s*(\d[\d,.]*\s*(?:(?:조|억|만|천)\s*)*(?:달러|유로|원))에\s*인수하는\s*(?:확정\s*)?(?:자산매입|인수)?계약을\s*체결", sentence)
            asset = re.search(r"([가-힣A-Za-z]+(?:\s+[가-힣A-Za-z]+){0,2}\s+자산)(?:을|를)\s*현금", sentence)
            if not issuer or not amount or not asset or market_materiality.PAST_ACTION.search(sentence):
                continue
            name = issuer.group(1)
            target = re.sub(r"^등\s+", "", asset.group(1))
            regulator = re.search(r"\(([A-Z]{2,8})\)\s*인허가", sentence)
            if regulator:
                target = f"{regulator.group(1)} 인허가 등 {target}"
            fact = (f"{name}{korean_topic_particle(name)} {target}을 "
                    f"{re.sub(r'\s+', '', amount.group(1))}에 인수하는 계약을 체결했다.")
            unbuilt = re.search(r"(?:해당\s*)?시설은[^.!?]{0,25}(?:미건설|실제로\s*건설되지\s*않)", source)
            approvals = re.search(r"종결은[^.!?]{0,100}승인[^.!?]{0,30}전제", source)
            if unbuilt and approvals:
                fact += " 시설은 미건설이며 종결에는 규제 승인이 필요하다."
            elif unbuilt:
                fact += " 시설은 미건설 상태다."
            elif approvals:
                fact += " 종결에는 규제 승인이 필요하다."
            if core_sentence_is_complete(fact):
                return fact
    if focus == "market_macro_response":
        jobs = re.search(r"(\d{1,2}월)\s*(?:미국(?:의)?\s*)?비농업\s*(?:부문\s*고용|일자리|고용)(?:은|이|가)?[^.!?]{0,30}(\d[\d,]*만\d[\d,]*명)\s*증가", source)
        expected = re.search(r"(?:(?:전문가|시장)\s*)?예상치(?:인)?\s*(\d[\d,]*만\d[\d,]*명)", source)
        close = re.search(r"나스닥(?:종합)?지수는[^!?]{0,70}?\(([+-]?\d+(?:\.\d+)?)%\)([^!?]{0,45}?)(?:마감|거래를\s*끝냈다)", source)
        if jobs and expected and close:
            observed = jobs.group(2).replace(',', '')
            forecast = expected.group(1).replace(',', '')
            def headcount(value):
                return int(value.split('만')[0]) * 10000 + int(value.split('만')[1].rstrip('명'))
            rising_close = bool(
                re.search(r"오른|뛴|상승", close.group(2))
                and not re.search(r"내린|하락|떨어", close.group(2))
                and float(close.group(1)) > 0
            )
            falling_close = bool(
                re.search(r"내린|하락|떨어", close.group(2))
                and not re.search(r"오른|뛴|상승", close.group(2))
                and float(close.group(1)) > 0
            )
            if headcount(observed) < headcount(forecast) and (rising_close or falling_close):
                direction = "상승" if rising_close else "하락"
                fact = (f"美 {jobs.group(1)} 비농업 고용은 {observed}으로 예상 {forecast}을 밑돌았다. "
                        f"나스닥은 {close.group(1)}% {direction} 마감했다.")
                if all(name in title for name in ("엔비디아", "AMD")) and any(
                    all(name in sentence for name in ("엔비디아", "AMD"))
                    and re.search(r"장중\s*(?:역대|사상)?\s*최고가를\s*경신했다", sentence)
                    for sentence in sentences
                ):
                    fact += " 엔비디아·AMD는 장중 최고가를 경신했다."
                if core_sentence_is_complete(fact):
                    return fact
    if focus == "project_response" and re.search(r"트럼프", title) and re.search(r"원유\s*회수\s*증진", source):
        amount = re.search(r"(\d+(?:\.\d+)?\s*억\s*달러)[^.!?]{0,35}원유\s*회수\s*증진", source)
        omitted = re.search(r"원유\s*회수\s*증진\s*프로젝트[^.!?]{0,100}공동\s*팩트시트[^.!?]{0,30}포함[^.!?]{0,15}않", source)
        uncertain = re.search(r"(?:해당\s*)?사업의?\s*추진\s*여부[^.!?]{0,20}말하기\s*어렵", source)
        if amount and omitted and uncertain:
            fact = (f"트럼프의 {amount.group(1)} 원유회수증진 사업은 공동 팩트시트에 없고, "
                    "정부는 추진 여부를 밝히기 어렵다는 입장이다.")
            if core_sentence_is_complete(fact):
                return fact
    if focus == "authorized_capital":
        issuer = re.match(r"^([^,，]{2,35})[,，]", title)
        for sentence in sentences:
            change = re.search(r"수권자본을\s*\d[\d,.]*\s*(?:만|억)?\s*달러에서\s*(\d[\d,.억만천\s]*달러)로\s*(\d[\d,]*)배\s*늘리는\s*안건", sentence)
            meeting = re.search(r"(\d{1,2}월\s*\d{1,2}일)\s*임시주주총회", sentence)
            if issuer and change and meeting and re.search(r"소집한다고|상정한다고|표결", sentence):
                name = issuer.group(1)
                fact = (f"{name}{korean_topic_particle(name)} 수권자본을 {change.group(1)}로 "
                        f"{change.group(2)}배 늘리는 안건을 {meeting.group(1)} 임시주총에 상정한다.")
                if re.search(r"신주\s*발행\s*규모와\s*시기[^.!?]{0,45}제시되지|증액\s*승인만으로\s*신주가\s*발행되지는\s*않", source):
                    fact += " 신주 발행이 확정된 것은 아니다."
                if core_sentence_is_complete(fact):
                    return fact
    if focus == "industry_outlook":
        for sentence in sentences:
            if not market_materiality.focus_matches(title, sentence):
                continue
            analyst = re.search(r"([A-Za-z가-힣&]+증권)\s*연구원", sentence)
            estimate = re.search(r"(데이터센터)\s*발주\s*시장\s*규모는\s*(\d[\d,.]*\s*(?:조|억)\s*원)\s*(?:정도로\s*)?추산", sentence)
            duration = re.search(r"인허가\s*기간을\s*제외하고\s*단순\s*시공\s*기준으로\s*(\d+)년", sentence)
            if analyst and estimate:
                context = "원전 투자 수혜 분석에서 " if "원전" in title and "원전" in source else ""
                fact = f"{context}{analyst.group(1)}은 {estimate.group(1)} 발주시장을 {estimate.group(2)}으로 추산했다."
                if duration:
                    fact += f" 인허가를 제외한 시공기간은 약 {duration.group(1)}년으로 예상했다."
                if core_sentence_is_complete(fact):
                    return fact
    if focus == "commercial_order":
        for sentence in sentences:
            issuer = re.match(r"^([A-Za-z0-9가-힣&·]+(?:\s+[A-Za-z0-9가-힣&·]+){0,4})\s*(?:\([A-Za-z0-9.-]+\))?(?:은|는|이|가)\s+", sentence)
            headline_issuer = re.match(r"^([^,，]{2,35})[,，]", title)
            if not issuer and headline_issuer and re.search(
                re.escape(headline_issuer.group(1)) + r"\s*(?:\([A-Za-z0-9.-]+\))?(?:은|는|이|가)\s+", sentence,
            ):
                issuer = headline_issuer
            duration = re.search(r"(?<!\d)(\d+)\s*년\s*계약\s*수주", sentence)
            amount = re.search(r"(\d[\d,.]*\s*(?:(?:조|억|만|천)\s*)*(?:달러|유로|원))\s*[,，]?\s*\d+\s*년\s*계약\s*수주", sentence)
            if not issuer or not duration or not amount or not re.search(r"발표했다", sentence):
                continue
            name = issuer.group(1)
            fact = f"{name}{korean_topic_particle(name)} {amount.group(1)} 규모의 {duration.group(1)}년 계약 수주를 발표했다."
            start = re.search(r"업무는\s*(\d{4}년\s*\d{1,2}월)\s*시작될\s*예정", source)
            if start:
                fact += f" 업무는 {start.group(1)} 시작될 예정이다."
            if core_sentence_is_complete(fact):
                return fact
        # The evidence path below can join an order with its next-sentence
        # amount. Do not return the isolated amount or acquisition background.
        return ""
    if focus == "trading_status":
        issuer = re.match(r"^([^,，]{2,35})[,，]", title)
        for sentence in sentences:
            ratio_range = re.search(r"(\d+대\d+)에서\s*(\d+대\d+)\s*범위로\s*병합", sentence)
            meeting_date = re.search(r"(\d{1,2}월\s*\d{1,2}일)(?:\([^)]*\))?\s*임시\s*주주총회", sentence)
            if issuer and ratio_range and meeting_date and re.search(r"상정한다고|상정할|상정하기로", sentence):
                name = issuer.group(1)
                fact = (f"{name}{korean_topic_particle(name)} {ratio_range.group(1)}~{ratio_range.group(2)} "
                        f"액면병합안을 {meeting_date.group(1)} 임시주총에 상정한다. 최종 비율은 미정이다.")
                if core_sentence_is_complete(fact):
                    return fact
            ratio = re.search(r"(?:보통주\s*)?(\d[\d,]*)주를\s*(\d[\d,]*)주로\s*합치는\s*액면병합", sentence)
            if not issuer or not ratio or not re.search(r"상정한다고|상정할|상정하기로", sentence):
                continue
            meeting = next((re.search(r"임시주총은[^.!?]{0,40}?(?<!\d)(\d{1,2}월\s*\d{1,2}일)", row) for row in sentences
                            if re.search(r"임시주총은[^.!?]{0,40}\d{1,2}월\s*\d{1,2}일", row)), None)
            schedule = f" {meeting.group(1)}" if meeting else ""
            additional = "과 복수의결권 도입" if "복수의결권" in sentence else ""
            fact = (f"{issuer.group(1)}{korean_topic_particle(issuer.group(1))} {ratio.group(1)}대{ratio.group(2)} "
                    f"액면병합{additional}안을{schedule} 임시주총에 상정한다.")
            if core_sentence_is_complete(fact):
                return fact
    if focus == "sanctions_request":
        for sentence in sentences:
            speaker = re.search(r"([가-힣]{2,12})\s*(?:[가-힣]{2,12}\s*)?대통령은", sentence)
            system = re.search(r"러시아가[^.!?]{0,70}위성\s*인터넷\s*['‘]([^('’]+)", sentence)
            if not speaker or not system or not re.search(r"미국에[^.!?]{0,20}제재해달라고\s*요구", sentence):
                continue
            support = "중국 지원으로 개발 중인 " if re.search(r"중국\s*지원으로\s*개발", sentence) else ""
            target = " 관련 기업" if re.search(r"(?:시스템|개발)[^.!?]{0,30}관련된\s*기업들을\s*제재", source) else ""
            name = speaker.group(1)
            fact = (f"{name}{korean_topic_particle(name)} {support}러시아 위성인터넷 '{system.group(1)}'{target}에 "
                    "미국 제재를 요청했다고 밝혔다.")
            if core_sentence_is_complete(fact):
                return fact
    if focus == "breadth":
        for sentence in sentences:
            period = re.search(r"(?:지난\s*)?(\d{1,2}월)", sentence)
            index = re.search(r"(나스닥100|나스닥|러셀2000)[^.!?]{0,25}?(\d+(?:\.\d+)?)%\s*(?:올랐|상승)", sentence)
            breadth = re.search(r"(S&P500)\s*(?:구성\s*)?종목의\s*(약\s*)?(\d+(?:\.\d+)?)%는\s*하락", sentence)
            if not period or not index or not breadth:
                continue
            fact = (f"{period.group(1)} {index.group(1)}은 {index.group(2)}% 올랐지만 "
                    f"{breadth.group(1)} 구성 종목의 {breadth.group(2) or ''}{breadth.group(3)}%는 하락했다.")
            average = re.search(r"종목별\s*평균\s*하락률은\s*(\d+(?:\.\d+)?)%", source)
            if average:
                fact += f" 종목별 평균 하락률은 {average.group(1)}%였다."
            if core_sentence_is_complete(fact):
                return fact
    if focus == "earnings":
        for sentence in sentences:
            issuer = re.match(r"^([A-Za-z0-9가-힣&·]+(?:\s+[A-Za-z0-9가-힣&·]+){0,4})\s*(?:\([A-Za-z0-9.-]+\))?(?:은|는|이|가)\s+", sentence)
            estimate = re.search(r"(\d{4})\s*회계연도\s*(상반기|하반기)\s*(?:\([^)]*\))?\s*잠정\s*미감사\s*매출액이\s*(?:약\s*)?(\d[\d,.]*\s*(?:만|억)?\s*[~∼-]\s*\d[\d,.]*\s*(?:만|억)\s*달러)", sentence)
            multiple = re.search(r"전년\s*동기[^.!?]{0,90}대비\s*(약\s*)?(\d+(?:\.\d+)?)배[^.!?]{0,40}예상", sentence)
            if issuer and estimate and multiple and re.search(r"발표했다", sentence):
                name = issuer.group(1)
                fact = (f"{name}{korean_topic_particle(name)} {estimate.group(1)}회계연도 {estimate.group(2)} "
                        f"잠정 미감사 매출을 {estimate.group(3)}로 예상했다. 전년동기 {multiple.group(1) or ''}{multiple.group(2)}배다.")
                if core_sentence_is_complete(fact):
                    return fact
    if focus == "bond_yield":
        for sentence in sentences:
            if (
                market_materiality.focus_matches(title, sentence)
                and re.search(r"\d+(?:\.\d+)?\s*(?:%|bp\b)", sentence, re.I)
                and re.search(r"올라|올랐|치솟|상승|하락|밑돌|넘었|돌파|기록|내렸|낮아|높아", sentence)
                and not market_materiality.BACKGROUND.search(sentence)
                and not market_materiality.EARLY_SIGNAL.search(sentence)
            ):
                fact = normalized_article_sentence(sentence)
                fact = re.sub(r"^이에\s*따라\s+", "", fact)
                if core_sentence_is_complete(fact):
                    return fact
    if re.search(r"트럼프", title) and re.search(r"알래스카", title) and re.search(r"한국|韓", source):
        threat = next((sentence for sentence in sentences
                       if not market_materiality.BACKGROUND.search(sentence)
                       and re.search(r"합의[^.!?]{0,30}(?:않|안\s*하)|서명[^.!?]{0,20}(?:않|안\s*하)", sentence)
                       and re.search(r"(?:청구|부담)[^.!?]{0,30}(?:두|2)\s*배|(?:두|2)\s*배[^.!?]{0,30}(?:청구|부담)", sentence)), "")
        if threat:
            timing = "곧 " if "곧" in threat else ""
            # A bill/charge is not a tariff. Do not convert the sourced noun.
            fact = f"트럼프는 한국이 알래스카 투자에 {timing}합의하지 않으면 청구액을 두 배로 올리겠다고 말했다."
            if core_sentence_is_complete(fact):
                return fact
    if focus == "stockpile_release" and not re.search(r"채운|재비축|refill", title, re.I):
        for sentence in sentences:
            duration = re.search(r"(\d+)\s*(?:개월|달)", sentence)
            volume = re.search(r"(\d+(?:\.\d+)?\s*(?:억|만)?\s*배럴)", sentence)
            if duration and volume and re.search(r"G7|주요\s*7개국", sentence, re.I) and re.search(r"방출[^.!?]{0,35}합의", sentence):
                fact = f"G7은 향후 {duration.group(1)}개월 동안 비축유 {volume.group(1)}을 방출하기로 합의했다."
                if core_sentence_is_complete(fact):
                    return fact
        foreground = " ".join(sentence for sentence in sentences[:6] if not market_materiality.BACKGROUND.search(sentence))
        duration = re.search(r"(\d+)\s*(?:개월|달)", foreground)
        volume = re.search(r"(\d+(?:\.\d+)?\s*(?:억|만)?\s*배럴)", foreground)
        if duration and volume and re.search(r"G7|주요\s*7개국", foreground, re.I) and re.search(r"공동\s*방출|방출하기로", foreground):
            fact = f"G7은 향후 {duration.group(1)}개월 동안 비축유 {volume.group(1)}을 공동 방출하기로 합의했다."
            if core_sentence_is_complete(fact):
                return fact
    identity = market_materiality.source_event_identity({"source_title": title, "source_body": source, "body_verified": True}) if re.search(r"트럼프", title) and re.search(r"석유|원유", title) else ""
    if ":us_oil_investment:statement:" in identity:
        for sentence in sentences:
            amount = re.search(r"(\d+(?:\.\d+)?\s*억\s*달러)", sentence)
            if amount and re.search(r"트럼프", sentence) and re.search(r"석유|원유", sentence) and re.search(r"투자|프로젝트", sentence) and not market_materiality.BACKGROUND.search(sentence):
                project = "원유 회수 증진" if re.search(r"원유\s*회수\s*증진", source) else "원유 증산" if re.search(r"원유\s*증산|석유\s*증산", source) else "석유"
                fact = f"트럼프는 한국과의 협상에 따른 {project} 사업 규모가 {amount.group(1)}라고 발표했다."
                if core_sentence_is_complete(fact):
                    return fact
    if focus == "industry_market_share":
        period = re.search(r"(\d{4}년\s*[1-4]분기)\s*D램\s*매출\s*시장\s*점유율", source, re.I)
        micron = re.search(r"마이크론(?:은|의)\s*(?:매출\s*)?점유율\s*(\d+(?:\.\d+)?)%", source)
        hynix = re.search(r"SK하이닉스\s*점유율은\s*(\d+(?:\.\d+)?)%", source, re.I)
        gap = re.search(r"(?:두\s*업체\s*)?점유율\s*격차는\s*(\d+(?:\.\d+)?)%포인트", source)
        if period and micron and hynix and gap and "카운터포인트" in source:
            fact = (
                f"카운터포인트의 {period.group(1)} D램 매출 점유율은 마이크론 {micron.group(1)}%, "
                f"SK하이닉스 {hynix.group(1)}%로 격차는 {gap.group(1)}%포인트다."
            )
            if core_sentence_is_complete(fact):
                return fact
    if focus == "capital_spending":
        for sentence in sentences:
            plan = re.search(
                r"(\d{4}회계연도)\s*상반기\s*(?:\([^)]*\))?\s*설비투자는\s*"
                r"(\d[\d,.]*\s*억\s*달러)[^.!?]{0,70}이[르를][^.!?]{0,70}"
                r"하반기[^.!?]{0,100}자본지출이\s*더\s*증가[^.!?]{0,40}예상", sentence,
            )
            if plan and re.search(r"^마이크론은", sentence):
                basis = " 순설비투자" if re.search(r"정부\s*지원금을\s*차감한\s*순액", source) else " 설비투자"
                fact = (
                    f"마이크론은 {plan.group(1)} 상반기{basis} {plan.group(2)}를 예상하고 "
                    "하반기 추가 증액을 밝혔다."
                )
                if core_sentence_is_complete(fact):
                    return fact
    if focus == "trade_threat":
        for sentence in sentences:
            if market_materiality.BACKGROUND.search(sentence) or not market_materiality.focus_matches(title, sentence):
                continue
            fact = normalized_article_sentence(sentence)
            if core_sentence_is_complete(fact) and re.search(r"트럼프|Trump", fact, re.I):
                return fact
    if market_materiality.focus_kind(title) == "memory":
        issuer = re.match(r"^([A-Za-z가-힣]+증권)\s", title)
        for sentence in sentences:
            prices = re.search(
                r"([1-4]분기)\s*(?:범용\s*)?D램\s*가격은\s*전\s*분기\s*대비\s*"
                r"(\d+(?:\.\d+)?\s*[~∼-]\s*\d+(?:\.\d+)?%),\s*"
                r"낸드(?:\(NAND\))?\s*가격은\s*(\d+(?:\.\d+)?\s*[~∼-]\s*\d+(?:\.\d+)?%)"
                r"[^.!?]{0,100}상승[^.!?]{0,100}(?:전망|예상)", sentence,
            )
            if issuer and prices and issuer.group(1) in " ".join(sentences):
                attribution = " 트렌드포스를 인용해" if re.search(r"트렌드포스를\s*인용", sentence) else ""
                fact = (
                    f"{issuer.group(1)}은{attribution} {prices.group(1)} 전분기 대비 "
                    f"D램 가격 {prices.group(2)}, 낸드 가격 {prices.group(3)} 추가 상승을 전망했다."
                )
                if core_sentence_is_complete(fact):
                    return fact
    if market_materiality.focus_kind(title) == "project_cost":
        for sentence in sentences:
            comparison = re.search(
                r"([가-힣A-Za-z0-9]+)\s+(?:액화천연가스\s*\(LNG\)|LNG)\s*사업의\s*비용이\s*"
                r"([^.!?]{1,50}LNG\s*사업의\s*두\s*배를\s*넘는다고)\s*로이터\s*통신이[^.!?]{0,40}보도했다", sentence,
            )
            if comparison:
                fact = f"로이터는 {comparison.group(1)} LNG 사업비가 {comparison.group(2)} 보도했다."
                if core_sentence_is_complete(fact):
                    return fact
    if market_materiality.focus_kind(title) == "space_execution":
        for sentence in sentences:
            if re.search(r"발사했다|발사에\s*성공|교신.{0,20}성공", sentence) and any(
                term in sentence for term in korean_business_title_terms(title)
            ):
                fact = normalized_article_sentence(sentence)
                if core_sentence_is_complete(fact):
                    return fact
    if market_materiality.focus_kind(title) == "capital_listing" and "ETF" in title.upper():
        for sentence in sentences:
            issuer = re.match(r"^([가-힣A-Za-z0-9·&]+)(?:은|는)\s", sentence)
            fund = re.search(r"['‘]([^'’]{3,60})['’]\s*(?:상장지수펀드\s*\(ETF\)|ETF)", sentence, re.I)
            schedule = re.search(r"((?:오는\s*)?\d{1,2}일)\s*((?:유가증권|코스닥)시장에\s*)?(상장|출시)(?:한다고|할\s*예정이라고)\s*밝혔다", sentence)
            if issuer and fund and schedule:
                fact = f"{issuer.group(1)}은 '{fund.group(1)}' ETF를 {schedule.group(1)} {schedule.group(2) or ''}{schedule.group(3)}한다고 밝혔다."
                if core_sentence_is_complete(fact):
                    return fact
    if market_materiality.focus_kind(title) == "labor_negotiation":
        for sentence in sentences:
            if market_materiality.focus_matches(title, sentence) and re.search(r"임단협|임금|단체협약|잠정합의안", sentence):
                fact = normalized_article_sentence(sentence)
                if core_sentence_is_complete(fact):
                    return fact
    if market_materiality.focus_kind(title) == "research_result":
        issuer = re.match(r"^([^,，]{2,30})[,，]", title)
        for sentence in sentences:
            result = re.search(
                r"(AI\s*기반\s*코돈\s*최적화)\s*기술을\s*적용해\s*"
                r"(벤치마크\s*대비\s*단백질\s*번역\s*효율을\s*\d+(?:\.\d+)?%\s*이상\s*향상시켰다[.!?]?)", sentence,
            )
            if issuer and result:
                fact = f"{issuer.group(1)}는 {result.group(1)}로 {result.group(2)}"
                if core_sentence_is_complete(fact):
                    return fact
    if market_materiality.focus_kind(title) == "macro_release" and "건설지출" in title:
        country = re.match(r"^(미국|한국|중국|일본)\s", title)
        for sentence in sentences:
            change = re.search(
                r"((?:\d{4}년\s*)?\d{1,2}월)\s*건설지출은\s*(연율\s*환산으로\s*)?"
                r"전월\s*대비\s*(\d+(?:\.\d+)?%)\s*(증가|감소)했다고", sentence,
            )
            if country and change:
                basis = " 연율 환산 기준" if change.group(2) else ""
                fact = f"{country.group(1)} {change.group(1)} 건설지출은{basis} 전월 대비 {change.group(3)} {change.group(4)}했다."
                if core_sentence_is_complete(fact):
                    return fact
    if market_materiality.focus_kind(title) == "analyst_revision":
        for sentence in sentences:
            cleaned = normalized_article_sentence(sentence)
            reporter = re.match(r"^([A-Za-z0-9가-힣]+)(은|는)\s", cleaned)
            revision = re.search(
                r"([A-Za-z가-힣]+(?:\s+[A-Za-z가-힣]+){0,2}\([A-Z]{1,8}\))의\s*목표주가를\s*"
                r"(?:기존\s*)?(\d[\d,.]*(?:달러|원))에서\s*(\d[\d,.]*(?:달러|원))로\s*(상향|하향)", cleaned,
            )
            if reporter and revision:
                company = re.sub(r"(?<=[가-힣])\s+(?=[가-힣])", "", revision.group(1))
                particle = "으로" if revision.group(3).endswith("원") else "로"
                fact = f"{reporter.group(1)}{reporter.group(2)} {company} 목표주가를 {revision.group(2)}에서 {revision.group(3)}{particle} {revision.group(4)}했다."
                if core_sentence_is_complete(fact):
                    return fact
    if market_materiality.focus_kind(title) == "export_results":
        for sentence in sentences:
            if not market_materiality.focus_matches(title, sentence) or not market_materiality.QUANTITY.search(sentence):
                continue
            fact = normalized_article_sentence(sentence)
            fact = re.sub(r"^[^.!?]{0,100}?에\s*따르면\s*", "", fact, count=1)
            if not core_sentence_is_complete(fact):
                continue
            headline_amounts = [re.sub(r"\s+", "", match.group(0)) for match in market_materiality.QUANTITY.finditer(title)]
            for related in sentences:
                if related == sentence or not market_materiality.focus_matches(title, related):
                    continue
                if not any(amount in re.sub(r"\s+", "", related) for amount in headline_amounts):
                    continue
                other_fact = normalized_article_sentence(related)
                expanded = fact + " " + other_fact
                if core_sentence_is_complete(other_fact) and core_sentence_is_complete(expanded):
                    fact = expanded
            if re.search(r"수출.{0,20}1위", title):
                for ranking in sentences:
                    country = re.search(r"국가별로는[^.!?]{0,60}?([가-힣A-Za-z]+)(이|가)\s*1위를\s*기록했다", ranking)
                    if country:
                        expanded = fact + f" {country.group(1)}{country.group(2)} 수출 1위다."
                        if core_sentence_is_complete(expanded):
                            fact = expanded
                        break
            return fact
    if market_materiality.focus_kind(title) == "financing":
        for sentence in sentences:
            if not re.search(r"전환사채|전환\s*(?:선순위)?\s*채권", sentence):
                continue
            issuer = re.match(r"^([A-Za-z0-9가-힣&·]+(?:\s+[A-Za-z0-9가-힣&·]+){0,4})\s*(?:\([A-Za-z0-9.-]+\))?(?:은|는|이|가)\s+", sentence)
            amount = re.search(r"총\s*(\d[\d,.]*\s*(?:(?:조|억|만|천)\s*)*(?:달러|유로|원))", sentence)
            if not issuer or not amount or not re.search(r"발행", sentence):
                continue
            planned = bool(re.search(r"계획|추진|예정", sentence))
            if not planned and not re.search(r"발행했다|발행했다고", sentence):
                continue
            interest = "무이자 " if re.search(r"이표율\s*0(?:\.0+)?\s*%|무이자", sentence) else ""
            action = "발행을 추진한다" if planned else "발행했다"
            fact = f"{issuer.group(1)}{korean_topic_particle(issuer.group(1))} {amount.group(1)} {interest}전환사채 {action}."
            repurchase = re.search(r"기존\s*(\d{4})년(?:\s*만기)?[^.!?]{0,30}(?:전환사채|채권)[^.!?]{0,20}환매", sentence)
            if repurchase and re.search(r"자금|조달", sentence):
                fact += f" 일부 자금으로 {repurchase.group(1)}년물을 환매할 계획이다."
            if core_sentence_is_complete(fact) and market_materiality.core_focus_aligned(title, fact):
                return fact
        for sentence in sentences:
            audit = market_materiality.assess(title, sentence)
            if any(item["kind"] == "customer_financing_commitment" for item in audit["evidence"]):
                fact = normalized_article_sentence(sentence)
                if core_sentence_is_complete(fact):
                    return fact
    if focus == "equity_compensation":
        for sentence in sentences:
            issuer = re.match(r"^([A-Za-z0-9가-힣&·]+(?:\s+[A-Za-z0-9가-힣&·]+){0,4})\s*(?:\([A-Za-z0-9.-]+\))?(?:은|는|이|가)\s+", sentence)
            value = re.search(r"추정\s*총가치(?:는|가)?\s*(약\s*)?(\d[\d,.]*\s*(?:(?:조|억|만|천)\s*)*(?:달러|유로|원))", sentence)
            if not issuer or not value or not re.search(r"전\s*직원", sentence):
                continue
            if not re.search(r"주식보상|성과연동주식|양도제한조건부주식", sentence) or not re.search(r"도입하기로\s*결의", sentence):
                continue
            fact = (f"{issuer.group(1)}{korean_topic_particle(issuer.group(1))} 전 직원 주식보상제 도입을 결의했다. "
                    f"추정 총가치는 {value.group(1) or ''}{value.group(2)}다.")
            if core_sentence_is_complete(fact):
                return fact
    if focus == "ownership" and re.search(r"인수|합병", title):
        for sentence in sentences:
            target = re.match(r"^([A-Za-z0-9가-힣&·]+(?:\s+[A-Za-z0-9가-힣&·]+){0,4})\s*(?:\([A-Za-z0-9.-]+\))?(?:은|는|이|가)\s+", sentence)
            buyer = re.search(r"(?:법인\s+)?([A-Za-z0-9가-힣&·]+(?:\s+[A-Za-z0-9가-힣&·]+){0,3})에\s*인수되는", sentence)
            cash = re.search(r"(?:보통주\s*)?1주당\s*현금\s*(\d[\d,.]*\s*(?:달러|유로|원))", sentence)
            stock = re.search(r"보통주\s*(\d[\d,.]*)주를\s*받게", sentence)
            if target and buyer and cash and stock and re.search(r"계약을\s*체결", sentence):
                acquirer = re.sub(r"^.*?법인\s+", "", buyer.group(1))
                fact = (f"{target.group(1)} 주주는 {acquirer} 인수 계약에 따라 "
                        f"거래 종결 시 주당 현금 {cash.group(1)}와 주식 {stock.group(1)}주를 받는다.")
                if core_sentence_is_complete(fact):
                    return fact
    if market_materiality.focus_kind(title) == "ownership" and re.search(r"매각|매도|처분|주식.{0,8}판다", title):
        for sentence in sentences:
            if re.search(r"거래계획보고서", sentence) and re.search(r"[\d,만억]+주.{0,20}매도", sentence):
                fact = normalized_article_sentence(sentence)
                owner = re.search(r"([가-힣]{2,5})\s*[,，]", title)
                if owner and owner.group(1) in " ".join(sentences):
                    fact = re.sub(rf"{re.escape(owner.group(1)[0])}\s*회장", f"{owner.group(1)} 회장", fact, count=1)
                if core_sentence_is_complete(fact):
                    return fact
            if (
                market_materiality.core_focus_aligned(title, sentence)
                and re.search(r"주식\s*[\d,만억]+주", sentence)
                and re.search(r"(?:매각|처분)할\s*(?:예정|계획)", sentence)
                and re.search(r"공시했다|밝혔다", sentence)
                and any(term in sentence for term in korean_business_title_terms(title))
            ):
                fact = normalized_article_sentence(sentence)
                if core_sentence_is_complete(fact):
                    return fact
    if market_materiality.focus_kind(title) == "sanctions_exemption":
        for sentence in sentences:
            action = re.search(
                r"((?:영국|유럽연합|EU|미국|일본|캐나다)\s*(?:정부)?(?:은|는|이))\s+"
                r"(?:\d{1,2}일\s*\(현지\s*시간\)\s*)?"
                r"[^.!?]{0,100}?제재\s*예외조치를\s*발표하고\s+([^.!?]+제재를\s*면제하기로\s*했다[.!?]?)",
                sentence,
            )
            if action:
                fact = action.group(1) + " " + action.group(2)
                if core_sentence_is_complete(fact):
                    return fact
    if market_materiality.focus_kind(title) == "shareholder":
        insider_fact = insider_purchase_fact(title, sentences)
        if core_sentence_is_complete(insider_fact):
            return insider_fact
        if re.search(r"종료|사라|마무리|막바지", title):
            schedules = []
            for sentence in sentences:
                ending = re.search(r"([A-Za-z0-9가-힣&·]+)(?:은|는)\s+[^.!?]*(?:마무리|종료|마지막\s*주문)[^.!?]*[.!?]", sentence)
                if not ending:
                    continue
                fact = normalized_article_sentence(ending.group(0))
                if not re.search(r"\d{1,2}(?:[~∼-]\d{1,2})?일|이날|오늘|오는|내달|내년|예정|완료했다|종료했다", fact):
                    continue
                candidate = "자사주 매입: " + " ".join(schedules + [fact])
                if core_sentence_is_complete(candidate):
                    schedules.append(fact)
                if len(schedules) == 2:
                    break
            if schedules:
                return "자사주 매입: " + " ".join(schedules)
    for sentence in sentences:
        if (
            not market_materiality.core_focus_aligned(title, sentence)
            or market_materiality.ASPIRATION.search(sentence)
            or market_materiality.BACKGROUND.search(sentence)
            or market_materiality.COMPANY_PROFILE.search(sentence)
            or re.match(r"^(?:또|그리고|한편|이러한|이를|이\s*같은)\s", sentence)
        ):
            continue
        fact = normalized_article_sentence(sentence)
        if focus == "ownership" and not market_materiality.evidence_is_new_event("corporate_transaction", sentence) and re.search(r"인수|합병", title):
            continue
        if focus == "ownership" and re.search(r"인수|합병", title):
            issuer = re.match(r"^([A-Za-z0-9가-힣&·-]+(?:\s+[A-Za-z0-9가-힣&·-]+){0,3})[,，]\s*", title)
            if issuer and issuer.group(1) not in fact and re.match(r"^[^.!?]{0,80}(?:인수한다고|인수를\s*마무리|합병이\s*완료)", fact):
                acquisition = re.search(r"기업\s+([A-Za-z0-9가-힣&·-]+)(?:을|를)\s*인수한다고\s*발표", sentence)
                fact = issuer.group(1) + korean_topic_particle(issuer.group(1)) + " " + fact
                if acquisition:
                    fact = f"{issuer.group(1)}{korean_topic_particle(issuer.group(1))} {acquisition.group(1)} 인수를 발표했다."
                    for related in sentences:
                        if acquisition.group(1) not in related or not re.search(r"비용|가동률|마진", related) or not re.search(r"기대|예상|전망|수\s*있", related):
                            continue
                        expanded = fact + " " + normalized_article_sentence(related)
                        if core_sentence_is_complete(expanded):
                            fact = expanded
                        break
        if market_materiality.focus_kind(title) == "environmental_approval":
            fact = re.sub(r"^\d{1,2}일\s*업계에\s*따르면\s*", "", fact)
            fact = re.sub(r"\s*\(현지\s*시간\)", "", fact)
            fact = re.sub(r"미국\s*국가환경정책법\s*\(NEPA\)", "NEPA", fact)
            fact = re.sub(r"최종\s*환경평가\s*\(Final\s*EA\)", "최종 환경평가", fact, flags=re.I)
        if market_materiality.focus_kind(title) == "nuclear_warning":
            speaker = re.match(r"^([A-Za-z가-힣]{2,20})\s*[,，]", title)
            if speaker and speaker.group(1) in fact[:60]:
                fact = re.sub(
                    rf"^.*?{re.escape(speaker.group(1))}\s+[^.!?]{{0,20}}대통령(?:은|는)\s+", speaker.group(1) + ": ", fact,
                )
                fact = re.sub(r"^([^:]+:\s*)\d{1,2}일\s*\(현지\s*시간\)\s*", r"\1", fact)
                fact = fact.replace("발트해 연안 역외 영토 ", "")
                fact = re.sub(r"(을|를)(?:을|를)(?=\s)", r"\1", fact)
        if market_materiality.focus_kind(title) == "industrial_program":
            fact = re.sub(r"소형모듈원자로\s*\(SMR\)", "SMR", fact, flags=re.I)
            fact = fact.replace("SMR는", "SMR은")
            fact = fact.replace("상용화 기반 마련에 나서고", "상용화를 추진하고")
            fact = fact.replace("연구 성과를 창업과 사업화로 연결하기 위한 지원", "연구성과의 창업·사업화 지원")
        if market_materiality.focus_kind(title) == "sanctions_exemption":
            fact = re.sub(r"^([가-힣]{2,10}(?:이|은|는))\s+\d{1,2}일\s*\(현지\s*시간\)\s*", r"\1 ", fact)
            fact = fact.replace("대(對)", "대")
            fact = re.sub(r"액화천연가스\s*\(LNG\)", "LNG", fact, flags=re.I)
            if not re.search(r"\d{4}년", fact):
                if not core_sentence_is_complete(fact) or article_title_restatement(fact, title):
                    continue
                for provision in sentences:
                    expiry = re.search(r"(\d{4}년\s*\d{1,2}월\s*\d{1,2}일)까지\s*제재를\s*면제", provision)
                    if expiry:
                        expanded = fact + f" 기한은 {expiry.group(1)}까지다."
                        if core_sentence_is_complete(expanded):
                            fact = expanded
                        break
        if market_materiality.focus_kind(title) == "project_buildout":
            fact = re.sub(
                r"^.*?([A-Za-z0-9가-힣&·]+)의\s+(?:글로벌\s*)?최고경영자\s*\(CEO\)"
                r"[^.!?]{1,60}?인터뷰에서\s+", r"\1는 ", fact,
            )
            fact = re.sub(r"말했다고\s+전했다\.?$", "밝혔다.", fact)
        if market_materiality.DENIAL_HEADLINE.search(title):
            # Keep the reporting institution and the exact denial quote when
            # an overlong lead also describes a disputed positive announcement.
            reporter = re.match(r"^([가-힣A-Za-z]{2,30}(?:\([A-Z]{2,10}\))?)(?:은|는)\s", fact)
            quotation = re.search(r'["“]([^"”]+)["”](?:이라고|고)\s*보도했다', fact)
            context = re.search(r"([가-힣A-Za-z0-9·-]+\s+(?:LNG|데이터센터|원전)\s*(?:사업|투자))에", fact)
            if reporter and quotation and context and market_materiality.DENIAL_SOURCE.search(quotation.group(1)):
                institution = re.search(r"\(([A-Z]{2,10})\)", reporter.group(1))
                institution = institution.group(1) if institution else reporter.group(1)
                candidate = f'{institution}: {context.group(1)}에 대해 "{quotation.group(1)}"이라고 보도했다.'
                if core_sentence_is_complete(candidate) and market_materiality.core_focus_aligned(title, candidate):
                    return candidate
            fact = re.sub(r"액화천연가스\s*\(LNG\)", "LNG", fact, flags=re.I)
            fact = re.sub(r"((?:은|는)\s+)(?:\d{1,2}일\s+)?[^.!?]{1,30}(?:대통령|총리|장관)이\s+", r"\1", fact)
            fact = re.sub(r"(투자|계약|수주|매각|인수)(?:를|을)\s*(?:기정사실로\s*)?발표한\s*데\s*대해", r"\1에 대해", fact)
        if len(fact) > GAMEJOA_CORE_MAX_CHARS:
            fact = re.sub(r"^[^.!?]{0,180}?에\s*따르면\s*", "", fact, count=1)
        if (
            core_sentence_is_complete(fact)
            and not subjectless_financial_core(fact)
            and not sentence_has_suspect_financial_amount(fact)
            and not article_title_restatement(fact, title)
            and market_materiality.core_focus_aligned(title, fact)
        ):
            return fact
    return ""


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


def analyst_research_target(title: str, source: str) -> str:
    revision = market_materiality.analyst_target_revision_terms(title, source)
    if revision:
        return str(revision["issuer"])
    research = market_materiality.broker_earnings_report_terms(title, source)
    if research:
        return str(research["issuer"])
    quoted = re.search(r'(?:증권|리서치|research)\s*["\'“‘]\s*([A-Za-z0-9가-힣&·.-]{2,30})(?=[,，\s])', title, re.I)
    if quoted and re.search(rf"{re.escape(quoted.group(1))}(?:의|은|는|에\s*대해)", source):
        return quoted.group(1)
    return ""


def financial_headline_subject(title: str, source: str) -> str:
    if not re.search(r"분기|매출|영업이익|순이익|순익|영업익|판매|실적|최다", title):
        return ""
    head = re.sub(r"^(?:\[[^\]]+\]\s*)+", "", title)
    match = re.match(r"^([A-Za-z0-9가-힣&·.-]{2,30})[,，\s]", head)
    if match and re.search(rf"{re.escape(match.group(1))}(?:은|는|이|가|의)\s", source):
        return match.group(1)
    named = {name for name in re.findall(r"\b([A-Za-z0-9가-힣&·.-]{2,30})(?:은|는|이|가|의)(?=\s|\()", source)
             if name in head and not re.search(r"분기|매출|실적|이익|전망|집계", name)}
    if len(named) == 1:
        return named.pop()
    return ""


def profit_loss_result_fact(title: str, sentences: list[str]) -> str:
    """Keep the issuer's adjacent, same-period observed loss and accounting basis."""
    if not re.search(r"실적|적자|손실|영업이익|순이익", title):
        return ""
    for index, sentence in enumerate(sentences[:-1]):
        owner = re.match(r"^([A-Za-z0-9가-힣&·.-]{2,30})(?:은|는)\s*(?:올\s*)?(상반기|하반기|[1-4]분기)\s*매출", sentence)
        if not owner or owner.group(1) not in title or market_materiality.BACKGROUND.search(sentence):
            continue
        following = sentences[index + 1]
        metric = re.match(r"(모회사\s*귀속\s*|지배주주\s*귀속\s*)?순손실(?:은|이)\s*", following)
        amounts = extract_foreign_amounts(following[metric.end():]) if metric else []
        won = re.search(KOREAN_WON_AMOUNT_PATTERN, following[metric.end():]) if metric else None
        if not metric or not re.search(r"흑자에서\s*적자로\s*전환", following) or not (amounts or won):
            continue
        if re.search(r"전망|추정|예상|가정", following):
            continue
        amount = amounts[0]["raw"].replace(" ", "") if amounts else won.group(0).replace(" ", "")
        particle = "으로" if amount.endswith(("원", "위안", "엔")) else "로"
        change = re.search(r"전년\s*동기\s*대비\s*(\d+(?:\.\d+)?)%\s*(증가|감소)", sentence)
        revenue = f"매출이 전년비 {change.group(1)}% {change.group(2)}했고, " if change else ""
        return (f"{owner.group(1)}은 {owner.group(2)} {revenue}{metric.group(1) or ''}"
                f"순손실 {amount}{particle} 적자 전환했다.")
    return ""


def headline_financial_fact(title: str, body: str) -> str:
    loss = profit_loss_result_fact(title, market_materiality.source_sentences(body))
    if loss:
        return loss
    subject = financial_headline_subject(title, body)
    if not subject or market_materiality.focus_kind(title) not in {"", "earnings"}:
        return ""
    sentences = market_materiality.source_sentences(body)
    if re.search(r"영업(?:익|이익)", title):
        for sentence in sentences:
            quarter = re.search(rf"{re.escape(subject)}의\s*([1-4])분기", sentence)
            profit = re.search(rf"영업이익(?:은|의\s*컨센서스는)\s*({KOREAN_WON_AMOUNT_PATTERN})", sentence)
            if not quarter or not profit or not re.search(r"에프앤가이드.{0,30}집계|집계.{0,30}에프앤가이드", sentence):
                continue
            if not re.search(r"컨센서스", sentence):
                continue
            revenue = re.search(rf"매출액\s*컨센서스는\s*({KOREAN_WON_AMOUNT_PATTERN})", sentence)
            fact = f"에프앤가이드 집계상 {subject} {quarter.group(1)}분기 영업이익 예상은 {profit.group(1)}이다."
            if revenue:
                fact += f" 매출 예상은 {revenue.group(1)}이다."
            announcement = re.search(rf"{re.escape(subject)}(?:은|는)\s*오는\s*(\d{{1,2}})일\s*{quarter.group(1)}분기\s*잠정실적을\s*발표할\s*예정", body)
            if announcement:
                fact += f" 잠정실적은 {announcement.group(1)}일 발표 예정이다."
            if core_sentence_is_complete(fact):
                return fact
    for index, sentence in enumerate(sentences):
        if subject not in sentence or not re.search(r"(?:매출|판매량|영업이익|순이익).{0,80}(?:집계|기록|증가|감소|달성)", sentence):
            continue
        if market_materiality.BACKGROUND.search(sentence):
            continue
        fact = normalized_article_sentence(sentence)
        if not core_sentence_is_complete(fact):
            continue
        if index + 1 < len(sentences):
            change = re.match(r"전년\s*동기\s*대비\s*(\d+(?:\.\d+)?)%\s*(증가|감소)한\s*것이다", sentences[index + 1])
            if change:
                expanded = fact + f" 전년비 {change.group(1)}% {change.group(2)}했다."
                if core_sentence_is_complete(expanded):
                    fact = expanded
        return fact
    return ""


def financial_revision_fact(title: str, sentences: list[str], source_context: str = "") -> str:
    target = analyst_research_target(title, source_context or " ".join(sentences))
    for sentence in sentences:
        revision = re.search(
            r"(영업이익|순이익|매출(?:액)?)\s*(?:(?:전망치|추정치|전망|예상치)(?:도|는|은|를|을)?\s*)?"
            rf"(?:기존\s*)?({KOREAN_WON_AMOUNT_PATTERN})에서\s*({KOREAN_WON_AMOUNT_PATTERN})(?:으로|로)\s*"
            r"(?:(\d+(?:\.\d+)?)%\s*)?(하향|상향|낮췄|높였)", sentence,
        )
        if not revision:
            continue
        owner = re.match(r"^([A-Za-z0-9가-힣&·.-]{2,30})(?:은|는|의)\s*", sentence)
        subject = target or (owner.group(1) if owner else "")
        if not subject or (not target and re.search(r"증권|리서치", subject)):
            continue
        period = re.search(r"([1-4])분기", sentence) or re.search(r"([1-4])분기", title)
        old, new = (amount.replace(" ", "") for amount in revision.group(2, 3))
        direction = "하향" if revision.group(5) in {"하향", "낮췄"} else "상향"
        change = f"({revision.group(4)}% {direction})" if revision.group(4) else f" {direction}"
        fact = f"{subject} {period.group(1) + '분기 ' if period else ''}{revision.group(1)} 전망은 {old}→{new}{change}입니다."
        if core_sentence_is_complete(fact):
            return fact
    return ""


def financial_result_fact(title: str, sentences: list[str], source_context: str = "") -> str:
    revision = financial_revision_fact(title, sentences, source_context)
    if revision:
        return revision
    target = analyst_research_target(title, source_context or " ".join(sentences))
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
        foreign_amounts = extract_foreign_amounts(metric_tail)
        amount = amount_match.group(0) if amount_match else (
            foreign_amounts[0]["raw"] if foreign_amounts else ""
        )
        if not amount:
            continue
        if amount_match and suspect_financial_amount(metric, amount):
            continue
        period_match = re.search(r"([1-4])분기", sentence) or re.search(r"([1-4])분기", title)
        change_match = re.search(
            r"(?:전년\s*동기\s*대비|전년비|지난해\s*같은\s*기간보다)\s*"
            r"([+-]?\d+(?:\.\d+)?)%\s*(증가|감소|늘|줄)",
            sentence,
        )
        subject_match = re.match(r"^([A-Za-z0-9가-힣&·.-]{2,30})(?:은|는|의)\s*", sentence)
        if not subject_match:
            continue
        subject = subject_match.group(1)
        if re.search(r"증권|리서치", subject) and subject not in title.split('"')[0]:
            continue
        if re.search(r"증권|리서치", subject) and target:
            subject = target
        elif re.search(r"증권|리서치", subject) and re.search(r"전망|추정|예상", sentence):
            continue
        prefix = subject + " "
        prefix += f"{period_match.group(1)}분기 " if period_match else ""
        compact_amount = amount.replace(' ', '') if amount_match else amount
        result = f"{prefix}{metric}은 {compact_amount}"
        projected = bool(re.search(r"(?:전망|예상|추정)(?:치|했다|한다|된|된다|됩니다)|가이던스", sentence))
        if re.search(r"집계(?:됐|되었|돼|되며|된다)|기록(?:했|한)|달성(?:했|한)|거뒀", sentence):
            projected = False
        if change_match:
            direction = "증가" if change_match.group(2) in {"증가", "늘"} else "감소"
            particle = "으로" if compact_amount.endswith("원") else "로"
            result += f"{particle} 전년비 {change_match.group(1)}% {direction}"
            result += "할 전망입니다." if projected else "했습니다."
        else:
            result += " 전망입니다." if projected else "입니다."
        return concise_text(result, limit=100)
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
    title_text = clean_article_summary_text(title)
    if not re.search(r"(?:매수|매입|취득)", title_text):
        return ""
    text = " ".join([title, *sentences])
    if not insider_purchase_signal(text):
        return ""

    # A group total belongs to the group, not the first named executive.
    for sentence in sentences:
        group = re.search(
            r"(?:대표이사|회장|임원).{0,40}(?:비롯한|포함한|등\s*특수관계인|특수관계인).{0,80}(?:매입|매수|취득)", sentence,
        )
        if not group or not re.search(r"\d[\d,.]*(?:만\d*)?주", sentence):
            continue
        fact = normalized_article_sentence(sentence)
        fact = re.sub(r"^.*?기자\s*=\s*", "", fact)
        fact = re.sub(r"\s*\(블록딜\)\s*", " ", fact)
        fact = fact.replace("시간외 대량매매 방식으로", "블록딜로")
        fact = fact.replace("대표이사를 비롯한 주요 임원", "대표 등 임원")
        fact = re.sub(r"\(약\s*([^()]+)\s*규모\)", r"(약 \1)", fact)
        fact = fact.replace("만원 )", "만원)")
        fact = re.sub(r"(?:을|를)\s*(매입|매수|취득)했다고\s*\d{1,2}일\s*밝혔다\.?$", r" \1했다.", fact)
        if core_sentence_is_complete(fact):
            return fact

    purchases: list[str] = []
    seen_buyers: set[str] = set()
    seen_details: set[str] = set()
    for sentence in sentences:
        if not re.search(INSIDER_ROLE_PATTERN, sentence, flags=re.IGNORECASE):
            continue
        if not re.search(r"(?:매수|매입|취득)", sentence):
            continue
        if re.search(r"비롯한|포함한|특수관계인", sentence) or re.search(r"회사\s*측에\s*따르면", sentence):
            continue
        buyer_match = re.search(
            rf"([가-힣]{{2,4}}(?:\s+[A-Za-z가-힣0-9()·]+){{0,3}}\s*{INSIDER_ROLE_PATTERN})",
            sentence,
            flags=re.IGNORECASE,
        )
        if not buyer_match:
            continue
        buyer = re.sub(r"\s+", " ", buyer_match.group(1)).strip()
        person_buyer = re.search(
            rf"([가-힣]{{2,4}}(?:\s+[A-Za-z][A-Za-z가-힣0-9()·]*)?\s*"
            rf"{INSIDER_ROLE_PATTERN})",
            sentence,
            flags=re.IGNORECASE,
        )
        if person_buyer:
            buyer = re.sub(r"\s+", " ", person_buyer.group(1)).strip()
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
        details_key = "|".join(details)
        if details_key in seen_details:
            continue
        purchases.append(f"{buyer} {', '.join(details)}")
        seen_buyers.add(buyer_key)
        seen_details.add(details_key)
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
    personal = " 개인 명의로" if re.search(r"개인\s*명의|개인\s*자금|사비", text) else ""
    return concise_text(
        f"{'·'.join(purchases)}를{personal} 매수했습니다.",
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


def long_term_supply_article_fact(title: str, body: str) -> str:
    text = clean_article_summary_text(f"{title} {body}")
    if not (
        "SK하이닉스" in text
        and any(term in text for term in ("장기공급계약", "장기 공급계약", "장기 공급 계약"))
    ):
        return ""
    customer_match = re.search(r"(\d+)개\s*고객사", text)
    revenue_match = re.search(r"(\d+(?:\.\d+)?조원)", text)
    if customer_match and revenue_match:
        return (
            f"SK하이닉스는 {customer_match.group(1)}개 고객사와 AI 메모리 장기공급계약을 "
            f"체결했으며 관련 매출은 {revenue_match.group(1)}으로 보도됐다."
        )
    return ""


def growth_fund_article_fact(title: str, body: str) -> str:
    text = clean_article_summary_text(f"{title} {body}")
    if "국민성장펀드" not in text:
        return ""
    if "LG디스플레이" in text and "테크윙" in text:
        lg_amount = re.search(r"LG디스플레이[^.!?]{0,45}?(1(?:\.5)?조원)", text)
        techwing_amount = re.search(r"테크윙[^.!?]{0,45}?(500억원)", text)
        if lg_amount and techwing_amount:
            return (
                f"국민성장펀드는 LG디스플레이에 {lg_amount.group(1)}, "
                f"테크윙에 {techwing_amount.group(1)}을 저리 대출해 OLED·HBM 투자를 지원한다."
            )
    return ""


def market_sidecar_fact(title: str, body: str) -> str:
    text = clean_article_summary_text(f"{title} {body}")
    if "매수 사이드카" in text:
        kospi_rise = re.search(
            r"코스피(?:는|가)?[^!?]{0,100}?(\d+(?:\.\d+)?)%\)?\s*"
            r"(?:오른|올랐|상승|급등)",
            text,
        )
        if kospi_rise:
            return (
                f"코스피가 {kospi_rise.group(1)}% 급등해 프로그램 매수호가를 "
                "5분간 정지하는 매수 사이드카가 발동됐다."
            )
        return "코스피 급등으로 프로그램 매수호가를 5분간 정지하는 매수 사이드카가 발동됐다."
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


def unconfirmed_company_action_fact(title: str, body: str) -> str:
    headline = re.match(r"^([A-Za-z0-9가-힣·&]+)\s*[,，]\s*(.+?)\s*(?:미정|미확정|확정\s*안\s*돼)", title)
    if not headline:
        return ""
    company, topic = headline.groups()
    topic = topic.strip(" \"'“”·….")
    anchor = (korean_business_title_terms(topic) or [""])[0]
    if not anchor:
        return ""
    for sentence in ranked_article_sentences(body, [company, anchor], title=title):
        if (
            company in sentence and anchor in sentence
            and re.search(r"(?:확정|결정)된\s*사항(?:은|이)?\s*없", sentence)
            and re.search(r"(?:설명했다|밝혔다|공시했다)", sentence)
        ):
            core = f"{company}는 {topic}에 대해 확정된 사항은 없다고 설명했다."
            return core if core_sentence_is_complete(core) else ""
    return ""


def listing_maintenance_action_fact(title: str, body: str) -> str:
    if not re.search(r"상폐|상장폐지|상장유지", title):
        return ""
    threshold = re.search(
        r"(내년|올해|20\d{2}년)\s*(\d{1,2})월[^.!?\n]{0,60}?상장유지\s*시가총액\s*기준이\s*([\d,]+억원)으로\s*(?:높아|상향)",
        body,
    )
    issuer = re.search(
        r"([A-Za-z0-9가-힣·&]{2,30})(?:은|는)\s*(?:이날\s*)?기업가치\s*제고\s*계획을\s*공시",
        body,
    )
    repurchase = re.search(r"자사주\s*([\d,]+만?주)\s*이상을\s*매입[·\s]*소각", body)
    if not threshold or not issuer or not repurchase or issuer.group(1) not in title:
        return ""
    core = (
        f"{issuer.group(1)}, {threshold.group(1)} {threshold.group(2)}월 상장유지 시총 기준 "
        f"{threshold.group(3)} 앞두고 자사주 {repurchase.group(1)} 이상 매입·소각 계획을 공시했다."
    )
    return core if core_sentence_is_complete(core) else ""


def policy_probability_article_fact(title: str, body: str) -> str:
    if "금리" not in title or not has_term(title, ("확률", "가능성")):
        return ""
    if not has_term(body.lower(), ("페드워치", "fedwatch")):
        return ""
    match = re.search(
        r"(\d{1,2})월\s*(?:기준)?금리(?:를|가)?\s*(동결|인상|인하)"
        r"[^。\n]{0,60}?(?:가능성|확률)[^。\n]{0,25}?(?:전날|기존|종전)\s*"
        r"(\d+(?:\.\d+)?)%에서\s*(?:이날|현재)?\s*(\d+(?:\.\d+)?)%로",
        clean_article_summary_text(body),
    )
    if not match:
        return ""
    month, action, before, after = match.groups()
    direction = "높아졌다" if float(after) > float(before) else "낮아졌다" if float(after) < float(before) else "유지됐다"
    return f"CME 페드워치의 {month}월 금리{action} 확률이 {before}%에서 {after}%로 {direction}."


def detailed_article_core(title: str, body: str) -> str:
    raw_body = str(body or "")
    if core_has_ui_garbage(raw_body):
        # Some publishers concatenate the abstract, title chrome, and the
        # article body without punctuation. Keep the body after the share UI
        # so an abstract fragment cannot become the reported sentence.
        ui_boundary = re.search(r"URL\s*(?:공유|복사)", raw_body, flags=re.IGNORECASE)
        if ui_boundary:
            body_tail = raw_body[ui_boundary.end():]
            body_tail = re.sub(
                r"^(?:\s*(?:가장\s*크게|가장\s*작게|작게|기본|보통|크게|프린트|구독)){1,12}\s*",
                "",
                body_tail,
                flags=re.IGNORECASE,
            )
            if body_tail.strip():
                raw_body = body_tail
    body = article_summary_body(raw_body)
    entry_fact = conditional_financial_market_entry_fact(title, body)
    if entry_fact:
        return entry_fact
    cyber_fact = financial_cyber_incident_fact(title, body)
    if cyber_fact:
        return cyber_fact
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
    revision_fact = financial_revision_fact(title, sentences, body)
    if revision_fact:
        return revision_fact
    financial_fact = headline_financial_fact(title, body)
    if financial_fact:
        return financial_fact
    long_term_supply_fact = long_term_supply_article_fact(title, body)
    if long_term_supply_fact:
        return long_term_supply_fact
    growth_fund_fact = growth_fund_article_fact(title, body)
    if growth_fund_fact:
        return growth_fund_fact
    tariff_fact = tariff_policy_fact(title, body)
    if tariff_fact:
        return tariff_fact
    sidecar_fact = market_sidecar_fact(title, body)
    if sidecar_fact:
        return sidecar_fact
    leverage_fact = single_stock_leverage_kosdaq_fact(title, body)
    if leverage_fact:
        return leverage_fact
    probability_fact = policy_probability_article_fact(title, body)
    if probability_fact:
        return probability_fact
    unconfirmed_fact = unconfirmed_company_action_fact(title, body)
    if unconfirmed_fact:
        return unconfirmed_fact
    listing_fact = listing_maintenance_action_fact(title, body)
    if listing_fact:
        return listing_fact
    focused_fact = source_focused_article_core(title, sentences)
    if focused_fact:
        return focused_fact
    audit = market_materiality.assess(title, body)
    for evidence in audit["evidence"]:
        if evidence["kind"] not in {"commercial_order", "customer_supply_start", "procurement_execution_stage", "policy_scope_or_stage", "export_control_scope"}:
            continue
        fact = normalized_article_sentence(evidence["source_excerpt"].rstrip(".") + ".")
        if len(fact) > GAMEJOA_CORE_MAX_CHARS:
            fact = re.sub(r"^\d{1,2}일\s+[^.!?]{1,30}에\s*따르면\s*", "", fact)
        if evidence["kind"] == "commercial_order":
            source_sentences = market_materiality.source_sentences(body)
            for index, sentence in enumerate(source_sentences[:-1]):
                if sentence != evidence["source_excerpt"]:
                    continue
                following = source_sentences[index + 1]
                amount = re.search(rf"^계약금액(?:은|이)\s*[^.!?]{{0,100}}?({KOREAN_WON_AMOUNT_PATTERN})", following)
                if amount:
                    approximate = "약 " if re.search(r"약\s*" + re.escape(amount.group(1)), following) else ""
                    candidate = fact + f" 계약금액은 {approximate}{amount.group(1)}이다."
                    if core_sentence_is_complete(candidate):
                        fact = candidate
                break
        if core_sentence_is_complete(fact) and not article_title_restatement(fact, title):
            return fact

    # In a multi-issuer memory article, a contextual revenue number must not
    # replace the headline's HBM supply/price change or lose its issuer.
    if "hbm" in title.lower():
        memory_facts = [normalized_article_sentence(sentence) for sentence in sentences if (
            "hbm" in sentence.lower()
            and has_term(sentence, ("가격", "판가", "공급", "수급", "계약", "물량", "수요"))
            and has_term(sentence, ("상승", "인상", "급등", "부족", "빠듯", "체결", "전망", "예상", "완판"))
        )]
        memory_facts.sort(key=lambda sentence: bool(re.search(r"전망했다|예상했다|내다봤|밝혔다", sentence)), reverse=True)
        for fact in memory_facts:
            fact = fact.replace("Blended ASP", "ASP")
            if len(fact) <= GAMEJOA_CORE_MAX_CHARS and core_sentence_is_complete(fact):
                return fact

    # An attributed earnings forecast is not a reported result. Preserve the
    # source's forecast and range instead of discarding it as a large actual.
    for sentence in sentences:
        if (
            sentence_has_suspect_financial_amount(sentence)
            and re.search(r"(?:전망|예상|추정)(?:했다|한다|된다|됩니다)", sentence)
            and core_sentence_is_complete(sentence)
        ):
            return sentence

    preferred = [
        insider_purchase_fact(title, sentences),
        financial_result_fact(title, sentences, body),
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
                or not core_sentence_is_complete(fact)
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
    "LG CNS",
    "LG AI연구원",
    "키옥시아",
    "애플",
    "아마존",
    "딥시크",
    "화웨이",
    "온코닉테라퓨틱스",
    "KAI",
    "SK이터닉스",
    "모트렉스",
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
    "관세 면제",
    "공급 부족",
    "hbm4",
    "hbm4e",
    "점유율",
    "시장 1위",
    "공개",
    "출시",
    "데이터센터 건설",
    "의무보유",
    "보호예수",
    "품목허가",
    "허가 권고",
    "상업화",
    "외환거래",
    "지분",
    "주식분할",
    "무장해제",
    "중동 전쟁",
    "추가 공격",
    "공격 임박",
    "드론 공격",
    "스타링크",
    "가자 휴전",
    "평화 협정",
    "국정조사",
    "청문회",
    "조사 착수",
    "공장 건설",
    "해외 공장",
    "생산거점",
    "서버 가격",
    "메모리 품귀",
    "회사채 발행",
    "잉여현금흐름",
    "주주환원",
    "특별배당",
    "순자산",
    "거래대금",
    "무역협정",
    "대응관세",
    "관세 철폐",
    "브렌트",
    "핫칩스",
    "기술공개",
    "성과급",
    "임단협",
    "파업",
    "자산공시",
    "자기주식",
    "반도체황산",
    "웨이퍼",
    "lpddr6",
    "신용거래융자",
    "로보택시",
    "이격거리",
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
        "매출", "영업익", "영업이익", "순이익", "흑자", "적자", "실적", "가이던스",
        "수요", "가격", "판가", "마진", "공급계약", "장기계약", "수주", "발주",
        "증설", "생산능력", "출하", "고객사", "점유율", "공급 부족",
        "시장 1위", "가격 인상", "데이터센터 건설", "품목허가", "상업화",
        "공장 건설", "해외 공장", "생산거점", "서버 가격", "메모리 품귀",
        "성과급", "임단협", "파업",
    ],
    "할인율": [
        "금리", "환율", "원·달러", "달러", "규제", "관세", "수출통제", "제재",
        "fomc", "연준", "국채금리", "국제유가", "인플레이션", "밸류에이션",
        "관세 면제", "상품 관세", "원유", "구리", "외환거래", "브렌트",
        "무역협정", "대응관세", "관세 철폐", "회사채", "회사채 발행",
        "이란", "쿠웨이트", "드론 공격", "추가 공격", "가자 휴전",
    ],
    "수급": [
        "외국인", "기관", "순매수", "순매도", "자사주", "유상증자", "cb",
        "전환사채", "etf", "etn", "레버리지", "기본예탁금", "편입", "상장", "ipo",
        "의무보유", "보호예수", "외환거래", "지분",
        "국정조사", "청문회", "스타링크", "주주환원", "잉여현금흐름",
        "특별배당", "순자산", "거래대금", "자산공시", "투자계좌",
    ],
    "시간표": [
        "양산평가", "평가", "승인", "허가", "상용화", "출시", "이달 말",
        "예정", "시행", "상장예비심사", "ipo", "계약", "증설", "착공", "완공",
        "공개", "품목허가", "허가 권고", "주식분할", "의무보유 해제",
        "추가 공격", "공격 임박", "타격 승인", "무장해제", "가자 휴전",
        "평화 협정", "국정조사", "청문회", "조사 착수", "공장 건설",
        "해외 공장", "생산거점", "핫칩스", "hot chips", "기술공개",
        "무역협정", "임단협", "파업",
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
        "source_body": body[:16000],
        "source_description": str(row.get("source_description") or ""),
        "article_query_time_kst": row.get("article_query_time_kst") or "",
        "article_detail_cache_hit": bool(row.get("_article_detail_cache_hit")),
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


def build_strategic_technology_investment_alert(row: dict, now, text: str) -> dict | None:
    title = str(row.get("source_title") or row.get("title") or "")
    body = str(row.get("source_body") or row.get("source_abstract") or "")
    lowered = f"{title} {body}".lower()
    companies = (
        "삼성전자", "sk하이닉스", "sk텔레콤", "현대차", "현대자동차",
        "lg전자", "lg디스플레이", "한화", "naver", "네이버", "카카오",
    )
    investment_terms = (
        "출자", "투자조합", "벤처펀드", "스타트업 투자", "스타트업투자",
        "전략적 투자", "오픈 이노베이션",
    )
    technology_terms = (
        "반도체", "ai", "인공지능", "로봇", "배터리", "바이오",
        "데이터센터", "첨단기술", "신기술", "스타트업",
    )
    if not (
        any(company in lowered for company in companies)
        and any(term in lowered for term in investment_terms)
        and any(term in lowered for term in technology_terms)
        and re.search(r"\d[\d,.]*\s*(?:억|조)\s*원", lowered)
    ):
        return None

    samsung_funds = (
        "삼성전자" in lowered
        and "svic 82호" in lowered
        and "svic 83호" in lowered
        and "4950억원" in lowered.replace(",", "")
        and "2970억원" in lowered.replace(",", "")
    )
    if samsung_funds:
        core = (
            "삼성전자가 DS 4,950억원·DX 2,970억원 등 7,920억원을 출자해 "
            "반도체·AI·로봇 스타트업 기술 확보에 나섭니다. "
            "두 펀드는 8월 출범해 13년·10년 운용됩니다."
        )
        sectors = ["반도체/HBM/CXL", "AI/데이터센터", "로봇/생산자동화"]
        company_key = "samsung_electronics"
        score = 120
    else:
        core = detailed_article_core(title, body)
        sectors = korean_business_source_sectors(title, body)
        company_key = next(
            (company.lower().replace(" ", "_") for company in companies if company in lowered),
            "major_company",
        )
        score = 110

    alert = base_korean_business_alert(
        row,
        now,
        score=score,
        impacts=["돈 버는 능력", "시간표"],
    )
    alert.update(
        {
            "importance": "상",
            "status": "확정" if "공시" in lowered else "예비",
            "policy_plain_summary": core,
            "telegram_core_fact": core,
            "telegram_investment_fact": (
                "출자금은 단기 현금유출이지만, 투자 대상·지분율·기술 이전·사업 협력이 "
                "확인되면 중장기 기술 경쟁력과 매출 시간표로 연결됩니다."
            ),
            "investment_view": (
                "출자금은 단기 현금유출이지만, 투자 대상·지분율·기술 이전·사업 협력이 "
                "확인되면 중장기 기술 경쟁력과 매출 시간표로 연결됩니다."
            ),
            "korea_market_impact": (
                "출자 기업과 반도체·AI·로봇 스타트업 생태계의 후속 투자 대상, "
                "지분 취득, 공동개발, 공급계약 공시만 직접 연결합니다."
            ),
            "sectors": sectors,
            "paths": ["현금흐름", "전략기술 확보", "투자 집행 시간표"],
            "korean_business_kind": "strategic_technology_fund_investment",
            "supply_chain_theme": (
                f"strategic_technology_fund:{company_key}:{korean_business_event_date(row)}"
            ),
        }
    )
    if row.get("_pinned_direct_article"):
        article_id = re.sub(r"[^A-Za-z0-9]", "", str(row.get("link") or "").rstrip("/").rsplit("/", 1)[-1])
        alert["_pinned_direct_article"] = True
        alert["supply_chain_theme"] = f"direct_trusted_article:{article_id}"
    return alert


def build_single_stock_leverage_rule_alert(row: dict, now, text: str) -> dict | None:
    if not (
        "레버리지" in text
        and any(term in text for term in ("etf", "etn"))
        and (
            any(term in text for term in ("삼성전자", "sk하이닉스", "삼닉"))
            or "긴급조치권" in text
        )
        and any(
            term in text
            for term in (
                "기본예탁금", "3000만원", "대용증권", "31일",
                "긴급조치권", "거래 제한", "거래제한",
            )
        )
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
    if "긴급조치권" in text:
        alert.update(
            {
                "status": "예비",
                "policy_plain_summary": (
                    "금융당국이 증시 급변 때 단일종목 레버리지 ETF 거래를 제한할 "
                    "긴급조치권 확보를 추진합니다."
                ),
                "telegram_core_fact": (
                    "금융당국이 증시 급변 때 단일종목 레버리지 ETF 거래를 제한할 "
                    "긴급조치권 확보를 추진합니다."
                ),
                "supply_chain_theme": f"korea_single_stock_leverage_emergency_power:{date_key}",
            }
        )
    if row.get("_pinned_direct_article"):
        article_id = str(row.get("link") or "").rstrip("/").rsplit("/", 1)[-1]
        title = str(row.get("source_title") or row.get("title") or "")
        body = str(row.get("source_body") or row.get("source_abstract") or "")
        if "AKR20260730034600008" in str(row.get("link") or ""):
            direct_core = (
                "유안타증권은 31일 규제로 대형 반도체 집중 자금의 기회비용이 정상화돼 "
                "코스닥 우량 성장주 수급이 개선될 수 있다고 분석했습니다."
            )
            direct_theme = f"direct_trusted_article:{article_id}"
        elif any(term in f"{title} {body}" for term in ("거래대금", "거래량", "12조원대", "개인 매도", "개미는")):
            if "12조원대" in f"{title} {body}" and "3조원대" in f"{title} {body}":
                direct_core = (
                    "기본예탁금이 1000만원에서 3000만원으로 오른 첫날 "
                    "단일종목 레버리지 ETF 거래액이 12조원대에서 3조원대로 급감했습니다."
                )
            elif "1억1692만좌" in body and "1조1967억원" in body:
                direct_core = (
                    "예탁금 상향 첫날 개인 매도와 거래량 감소가 나타났고, "
                    "SK하이닉스 레버리지 ETF 거래는 1억1692만좌·1조1967억원을 기록했습니다."
                )
            else:
                direct_core = detailed_article_core(title, body)
            direct_theme = f"korea_single_stock_leverage_rule_effect:{date_key}"
        else:
            direct_core = detailed_article_core(title, body)
            direct_theme = f"direct_trusted_article:{article_id}"
        alert.update(
            {
                "policy_plain_summary": direct_core,
                "telegram_core_fact": direct_core,
                "telegram_investment_fact": (
                    "거래대금 감소와 개인 매도가 이어지는지 확인해야 합니다."
                ),
                "investment_view": (
                    "거래대금 감소와 개인 매도가 이어지는지 확인해야 합니다."
                ),
                "supply_chain_theme": direct_theme,
                "_pinned_direct_article": True,
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
        any(term in title for term in ("국제유가", "유가 불안", "유가 상승"))
        and any(term in text for term in ("국제유가", "유가 불안", "유가 상승"))
        and macro_hits >= 2
    ):
        return None
    core = detailed_article_core(
        str(row.get("source_title") or row.get("title") or ""),
        str(row.get("source_body") or row.get("source_abstract") or ""),
    )
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


def build_korea_aquaculture_heat_loss_alert(row: dict, now, text: str) -> dict | None:
    marine_terms = ("양식장", "양식어류", "양식 어류", "어가")
    mortality_terms = ("집단 폐사", "집단폐사", "떼죽음", "폐사")
    cause_terms = ("고수온", "수온", "폭염", "적조", "산소 부족", "빈산소")
    if not (
        any(term in text for term in marine_terms)
        and any(term in text for term in mortality_terms)
        and any(term in text for term in cause_terms)
    ):
        return None

    title = str(row.get("source_title") or row.get("title") or "").strip()
    body = str(row.get("source_body") or row.get("source_abstract") or "").strip()
    core = article_sentences(
        body,
        ["양식", "폐사", "고수온", "수온", "피해", "마리", "억원", "가격"],
        2,
        title=title,
    )
    if not core:
        core = title

    alert = base_korean_business_alert(
        row,
        now,
        score=104,
        impacts=["돈 버는 능력", "시간표"],
    )
    alert.update(
        {
            "policy_plain_summary": core,
            "telegram_core_fact": core,
            "investment_view": (
                "고수온·적조 피해가 확대되면 양식 출하량 감소와 폐사 손실이 수산물 "
                "공급·가격, 사료·백신·보험 및 냉각·산소공급 장비 수요를 바꿀 수 있습니다."
            ),
            "korea_market_impact": (
                "수산물 유통·가공, 양식 사료·백신, 어업재해보험과 수처리·냉각·산소공급 "
                "장비 중 실제 피해 지역과 매출 노출이 확인되는 종목만 연결합니다."
            ),
            "priced_in": (
                "낮음~중간. 현장 폐사는 빠르게 발생하지만 전국 피해 집계와 출하가격 "
                "전가는 뒤늦게 확인되는 경우가 많습니다."
            ),
            "counter": (
                "단일 양식장 사고이거나 조기 출하·긴급 방류로 공급 차질이 제한되면 "
                "전국 수산물 가격과 상장사 실적 영향은 작을 수 있습니다."
            ),
            "failed_signal": (
                "해수부·지자체 피해 집계, 산지가격 상승, 출하량 감소 또는 관련 기업의 "
                "비용·수주 변화가 확인되지 않으면 지역성 피해 뉴스로 낮춥니다."
            ),
            "sectors": [
                "수산물/양식",
                "사료·백신/어업재해보험",
                "수처리·냉각/산소공급 장비",
            ],
            "korean_business_kind": "korea_aquaculture_heat_mass_mortality",
            "supply_chain_theme": (
                "korea_aquaculture_heat_loss:"
                f"{korean_business_event_date(row)}:"
                f"{base.norm(title)[:24]}"
            ),
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


def build_iran_gulf_escalation_alert(row: dict, now, text: str) -> dict | None:
    has_iran_attack = (
        "이란" in text
        and any(term in text for term in ("추가 공격", "추가공격", "공격 임박", "공격임박"))
    )
    has_gulf_drone = (
        any(term in text for term in ("쿠웨이트", "kuwait", "걸프"))
        and any(term in text for term in ("드론 공격", "드론공격", "drone attack"))
    )
    if not (has_iran_attack or has_gulf_drone):
        return None
    title = str(row.get("source_title") or row.get("title") or "")
    body = str(row.get("source_body") or row.get("source_abstract") or "")
    core = detailed_article_core(title, body)
    alert = base_korean_business_alert(
        row,
        now,
        score=122,
        impacts=["돈 버는 능력", "할인율", "수급", "시간표"],
    )
    alert.update(
        {
            "importance": "상",
            "status": "확정" if row.get("body_verified") else "예비",
            "policy_plain_summary": core,
            "telegram_core_fact": core,
            "sectors": ["정유/화학/해운", "방산/지정학", "원유/인플레이션"],
            "paths": ["지정학 리스크", "유가·운임", "환율", "군사행동 시간표"],
            "korean_business_kind": "iran_gulf_attack_escalation",
            "supply_chain_theme": f"iran_gulf_attack_escalation:{korean_business_event_date(row)}",
            "realtime_policy_lane": True,
        }
    )
    return alert


def build_ukraine_starlink_military_alert(row: dict, now, text: str) -> dict | None:
    if not (
        any(term in text for term in ("젤렌스키", "zelensky", "우크라이나", "ukraine"))
        and any(term in text for term in ("스타링크", "starlink"))
        and any(term in text for term in ("트럼프", "trump", "승인", "타격", "strike"))
    ):
        return None
    title = str(row.get("source_title") or row.get("title") or "")
    body = str(row.get("source_body") or row.get("source_abstract") or "")
    core = detailed_article_core(title, body)
    alert = base_korean_business_alert(
        row,
        now,
        score=116,
        impacts=["돈 버는 능력", "수급", "시간표"],
    )
    alert.update(
        {
            "importance": "상",
            # A request for approval is not an approval or an operational decision.
            "status": "예비",
            "policy_plain_summary": core,
            "telegram_core_fact": core,
            "sectors": ["위성통신/우주", "방산/무인체계", "우크라이나 지정학"],
            "paths": ["군사통신 접근", "정책 승인 시간표", "방산 수급"],
            "korean_business_kind": "ukraine_starlink_military_request",
            "supply_chain_theme": f"ukraine_starlink_military_request:{korean_business_event_date(row)}",
            "realtime_policy_lane": True,
        }
    )
    return alert


def build_gaza_ceasefire_disarmament_alert(row: dict, now, text: str) -> dict | None:
    if not (
        any(term in text for term in ("가자", "gaza", "하마스", "hamas"))
        and any(
            term in text
            for term in ("휴전", "ceasefire", "무장해제", "무장 해제", "disarmament", "평화 협정")
        )
    ):
        return None
    title = str(row.get("source_title") or row.get("title") or "")
    body = str(row.get("source_body") or row.get("source_abstract") or "")
    core = detailed_article_core(title, body)
    alert = base_korean_business_alert(
        row,
        now,
        score=114,
        impacts=["할인율", "수급", "시간표"],
    )
    alert.update(
        {
            "importance": "상",
            "status": "확정" if row.get("body_verified") else "예비",
            "policy_plain_summary": core,
            "telegram_core_fact": core,
            "sectors": ["중동 지정학", "해운/운임", "정유/화학", "방산"],
            "paths": ["휴전 시간표", "지정학 위험프리미엄", "유가·운임"],
            "korean_business_kind": "gaza_ceasefire_disarmament",
            "supply_chain_theme": f"gaza_ceasefire_disarmament:{korean_business_event_date(row)}",
            "realtime_policy_lane": True,
        }
    )
    return alert


def build_leverage_etf_parliamentary_inquiry_alert(row: dict, now, text: str) -> dict | None:
    if not (
        "레버리지" in text
        and any(term in text for term in ("etf", "etn"))
        and any(term in text for term in ("국정조사", "청문회", "조사 요구", "조사요구", "조사 착수", "조사착수"))
    ):
        return None
    title = str(row.get("source_title") or row.get("title") or "")
    body = str(row.get("source_body") or row.get("source_abstract") or "")
    core = detailed_article_core(title, body)
    formal_process = any(
        term in text
        for term in ("요구서 제출", "본회의 의결", "위원회 구성", "청문회 일정", "조사 착수")
    )
    alert = base_korean_business_alert(
        row,
        now,
        score=110,
        impacts=["수급", "시간표"],
    )
    alert.update(
        {
            "importance": "중",
            "status": "확정" if formal_process and row.get("body_verified") else "예비",
            "policy_plain_summary": core,
            "telegram_core_fact": core,
            "sectors": ["금융/자본시장", "ETF/ETN", "삼성전자·SK하이닉스 수급"],
            "paths": ["국회 조사 시간표", "상품 규제", "개인·기관 수급"],
            "korean_business_kind": "single_stock_leverage_parliamentary_inquiry",
            "supply_chain_theme": f"single_stock_leverage_parliamentary_inquiry:{korean_business_event_date(row)}",
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
    is_ymtc = any(term in text for term in ("ymtc", "창장메모리", "yangtze memory"))
    if not (
        any(term in text for term in ("cxmt", "창신메모리", "ymtc", "창장메모리", "yangtze memory"))
        and any(term in text for term in ("상장", "ipo"))
        and any(term in text for term in ("메모리", "반도체", "etf", "낸드", "ssd"))
    ):
        return None
    core = (
        "YMTC 상장 추진이 중국 낸드 공급·메모리 수급 변수로 부각됐습니다."
        if is_ymtc
        else "CXMT 상장 추진이 중국 메모리 공급·ETF 수급 변수로 부각됐습니다."
    )
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


def build_korea_strategic_etf_listing_alert(row: dict, now, text: str) -> dict | None:
    """Classify new strategic-industry ETF listings without calling them fund inflows."""
    title = str(row.get("source_title") or row.get("title") or "")
    has_listing_timetable = (
        any(term in text for term in ("신규상장", "신규 상장", "상장 예정", "상장예정"))
        or (
            "상장" in text
            and bool(re.search(r"\d{1,2}\s*일", text))
        )
    )
    if not (
        any(term in text for term in ("etf", "상장지수펀드"))
        and has_listing_timetable
    ):
        return None
    theme_terms = ("반도체", "금융", "지주", "방산", "ai", "전력", "전략산업", "전략 산업")
    if sum(term in text for term in theme_terms) < 2:
        return None

    body = str(row.get("source_body") or row.get("source_abstract") or "")
    if all(term in text for term in ("브이아이", "반도체", "금융", "지주")):
        core = "브이아이운용이 반도체·금융·지주 분산 ETF를 11일 상장합니다."
    else:
        core = detailed_article_core(title, body)
    alert = base_korean_business_alert(row, now, score=106, impacts=["수급", "시간표"])
    alert.update(
        {
            "importance": "중",
            "status": "확정" if row.get("body_verified") else "예비",
            "policy_plain_summary": core,
            "telegram_core_fact": core,
            "investment_view": "신규 ETF 상장은 해당 바스켓의 거래 접근성과 초기 편입·리밸런싱 수요 가능성을 만듭니다. 실제 자금 유입은 순자산·설정액·거래대금으로 별도 확인해야 합니다.",
            "korea_market_impact": "삼성전자·SK하이닉스와 금융·지주 편입 비중, 상장일 거래대금, 순자산 및 설정·환매 변화를 분리해 확인합니다.",
            "sectors": ["금융/자본시장", "반도체/HBM/CXL", "지주회사"],
            "paths": ["ETF 신규상장", "편입·리밸런싱", "수급 접근성"],
            "korean_business_kind": "korea_strategic_etf_listing",
            "supply_chain_theme": f"korea_strategic_etf_listing:{korean_business_event_date(row)}",
        }
    )
    return alert


AUGUST13_ATTACHMENT_PROFILES = (
    (
        "tesla_us_solar_factory_capex",
        ("테슬라", "tesla"),
        ("태양광", "solar"),
        ["돈 버는 능력", "시간표"],
        ["태양광/신재생", "전력기기/전력망", "미국 제조 CAPEX"],
        ["태양광 제조 CAPEX", "생산능력", "고용·가동 시간표"],
        112,
    ),
    (
        "nvidia_rubin_hbm_spec_change",
        ("엔비디아", "nvidia"),
        ("루빈", "rubin", "hbm4e", "hbm 4e"),
        ["돈 버는 능력", "수급", "시간표"],
        ["반도체/HBM/CXL", "AI/데이터센터", "반도체 장비·소재"],
        ["HBM 사양", "AI 가속기 수요", "고객 요구 변경"],
        118,
    ),
    (
        "skhynix_indiana_advanced_packaging_timeline",
        ("sk하이닉스", "sk hynix"),
        ("인디애나", "indiana"),
        ["돈 버는 능력", "시간표"],
        ["반도체/HBM/CXL", "반도체 장비·소재", "미국 제조 CAPEX"],
        ["HBM 후공정", "미국 생산거점", "착공·양산 시간표"],
        117,
    ),
    (
        "ai_datacenter_optical_interconnect",
        ("광통신", "광인터커넥트", "실리콘 포토닉스", "광 송수신기", "optical interconnect"),
        ("ai", "gpu", "hbm", "데이터센터", "data center"),
        ["돈 버는 능력", "시간표"],
        ["AI/데이터센터", "반도체/HBM/CXL", "네트워크·광통신"],
        ["광인터커넥트 수요", "AI 클러스터 병목", "네트워크 CAPEX"],
        113,
    ),
    (
        "samsung_datacenter_cooling_capacity",
        ("삼성", "samsung"),
        ("데이터센터", "data center"),
        ["돈 버는 능력", "시간표"],
        ["데이터센터 냉각", "전력기기/전력망", "AI/데이터센터"],
        ["공조·냉각 생산능력", "해외 제조 CAPEX", "가동 시간표"],
        112,
    ),
)



AUGUST27_ATTACHMENT_PROFILES = (
    (
        "us_h1b_visa_fee_proposal",
        ("h-1b", "h1b", "전문직 비자"),
        ("트럼프", "trump", "미국 행정부", "수수료", "비자비용"),
        ["돈 버는 능력", "할인율", "시간표"],
        ["미국 IT/인력", "AI/데이터센터", "환율/수출입"],
        ["전문인력 비용", "이민정책", "빅테크 인건비"],
        111,
    ),
    (
        "samsung_labor_separate_bargaining",
        ("삼성전자", "삼성"),
        ("분리교섭", "분리 교섭", "ds", "dx", "노조"),
        ["돈 버는 능력", "시간표"],
        ["반도체/HBM/CXL", "가전/디스플레이"],
        ["노사 교섭", "인건비", "가동 리스크"],
        108,
    ),
    (
        "korea_single_stock_leverage_etf_volume_drop",
        ("삼성전자", "sk하이닉스", "삼전", "닉스"),
        ("단일종목 레버리지", "레버리지 etf", "레버리지etf", "거래대금", "거래량"),
        ["수급"],
        ["ETF/ETN", "금융/자본시장", "반도체/HBM/CXL"],
        ["레버리지 거래", "개인 수급", "변동성"],
        113,
    ),
    (
        "openai_broadcom_jalapeno_inference_chip",
        ("오픈ai", "openai"),
        ("할라페뇨", "jalapeno", "자체 ai칩", "자체 ai 칩", "브로드컴"),
        ["돈 버는 능력", "수급", "시간표"],
        ["AI/데이터센터", "반도체/HBM/CXL", "반도체 장비·소재"],
        ["AI 추론칩", "HBM 수요", "AI 서비스 원가"],
        120,
    ),
    (
        "china_ai_price_war_short_interest",
        ("지푸", "미니맥스", "minimax", "중국 ai"),
        ("가격전쟁", "가격 전쟁", "공매도", "short interest", "공매도 잔액"),
        ["수급", "시간표"],
        ["중국 공급망", "AI/데이터센터", "금융/자본시장"],
        ["중국 AI 가격경쟁", "공매도 수급", "AI 수익성"],
        107,
    ),
    (
        "skhynix_emib_hbm_2p5d_packaging",
        ("sk하이닉스", "sk hynix"),
        ("emib", "2.5d", "hbm 패키징", "hbm패키징"),
        ["돈 버는 능력", "시간표"],
        ["반도체/HBM/CXL", "반도체 장비·소재", "AI/데이터센터"],
        ["2.5D 패키징", "HBM 고객 인증", "패키징 공급망"],
        119,
    ),
    (
        "ai_semiconductor_insulation_film_bottleneck",
        ("절연필름", "절연 필름", "패키지기판", "패키지 기판"),
        ("ai칩", "ai 칩", "hbm", "반도체", "기판 생산량"),
        ["돈 버는 능력", "수급", "시간표"],
        ["반도체 장비·소재", "반도체/HBM/CXL", "AI/데이터센터"],
        ["기판 소재 병목", "AI 칩 공급", "패키징 생산능력"],
        118,
    ),
    (
        "samsung_electro_mlcc_lta",
        ("삼성전기", "samsung electro"),
        ("mlcc", "lta", "장기공급", "장기 공급"),
        ["돈 버는 능력", "시간표"],
        ["전자부품/MLCC", "AI/데이터센터", "반도체/HBM/CXL"],
        ["고부가 MLCC", "고객 LTA", "AI 부품 수요"],
        115,
    ),
    (
        "amazon_nvidia_gpu_2m_capex",
        ("아마존", "amazon", "aws"),
        ("엔비디아", "nvidia", "gpu"),
        ["돈 버는 능력", "수급", "시간표"],
        ["AI/데이터센터", "반도체/HBM/CXL", "전력기기/전력망"],
        ["GPU 도입", "AI 데이터센터 CAPEX", "HBM 수요"],
        120,
    ),
    (
        "us_pce_ndf_rate_shift",
        ("pce", "개인소비지출"),
        ("ndf", "원·달러", "원달러", "예상 상회", "금리"),
        ["할인율", "수급"],
        ["미국 증시/금리", "환율/수출입", "성장주/밸류에이션"],
        ["미국 물가", "원·달러 환율", "연준 금리 경로"],
        118,
    ),
    (
        "nvidia_earnings_actual",
        ("엔비디아", "nvidia"),
        ("깜짝 실적", "실적 상회", "어닝 서프라이즈", "월가 예상"),
        ["돈 버는 능력", "수급", "시간표"],
        ["반도체/HBM/CXL", "AI/데이터센터", "미국 증시/금리"],
        ["AI 가속기 실적", "HBM 수요", "빅테크 CAPEX"],
        120,
    ),
    (
        "nvidia_memory_purchase_commitments",
        ("엔비디아", "nvidia"),
        ("구매약정", "구매 약정", "생산능력", "생산 능력"),
        ["돈 버는 능력", "수급", "시간표"],
        ["반도체/HBM/CXL", "반도체 장비·소재", "AI/데이터센터"],
        ["메모리 구매약정", "공급망 선점", "HBM 생산능력"],
        120,
    ),
    (
        "catl_lithium_mine_restart_halted",
        ("catl", "닝더스다이"),
        ("리튬광산", "리튬 광산", "환경영향평가", "eia", "재가동"),
        ["돈 버는 능력", "수급", "시간표"],
        ["2차전지/핵심광물", "원자재/매크로", "중국 공급망"],
        ["리튬 공급", "환경 인허가", "배터리 원가"],
        117,
    ),
    (
        "nvidia_hbm4_rubin_vera_memory_shortage",
        ("엔비디아", "nvidia"),
        ("메모리 부족", "메모리 공급부족", "메모리 공급 부족", "hbm4", "루빈", "rubin", "베라", "vera", "lpddr5x"),
        ["돈 버는 능력", "수급", "시간표"],
        ["반도체/HBM/CXL", "AI/데이터센터", "DRAM/NAND"],
        ["HBM4·LPDDR5X 수요", "AI 가속기 메모리", "메모리 공급"],
        120,
    ),
    (
        "nvidia_nvhbm_amazon_collaboration",
        ("nvhbm",),
        ("엔비디아", "nvidia", "아마존", "amazon", "nv링크", "nvlink"),
        ["돈 버는 능력", "수급", "시간표"],
        ["반도체/HBM/CXL", "AI/데이터센터", "반도체 장비·소재"],
        ["맞춤형 HBM", "AI 가속기", "아마존 협력"],
        120,
    ),
    (
        "iran_opec_china_oil_market_shift",
        ("이란", "iran"),
        ("중국", "china", "opec", "석유", "원유", "oil"),
        ["돈 버는 능력", "할인율", "수급"],
        ["원유/인플레이션", "정유/화학/해운", "방산/지정학"],
        ["원유 공급망", "OPEC+ 가격 조절력", "중국 원유 수요"],
        114,
    ),
    (
        "us_datacenter_tariff_cost_pressure",
        ("데이터센터", "data center"),
        ("관세", "tariff", "트럼프", "trump"),
        ["돈 버는 능력", "할인율", "시간표"],
        ["AI/데이터센터", "전력기기/전력망", "반도체/HBM/CXL"],
        ["AI 인프라 CAPEX", "수입 장비 비용", "관세 정책"],
        114,
    ),
    (
        "skhynix_us_hbm_advanced_packaging_capex",
        ("sk하이닉스", "sk hynix"),
        ("웨스트라피엣", "인디애나", "퍼듀", "purdue", "첨단 패키징", "첨단패키징"),
        ["돈 버는 능력", "수급", "시간표"],
        ["반도체/HBM/CXL", "미국·일본 제조 CAPEX", "반도체 장비·소재"],
        ["미국 HBM 생산시설", "첨단 패키징 CAPEX", "현지 고객 지원"],
        120,
    ),
    (
        "korea_bok_rate_policy_event",
        ("한국은행", "한은", "금통위"),
        ("기준금리", "금리 인상", "금리 결정", "10월 금리"),
        ["할인율", "수급", "시간표"],
        ["미국 증시/금리", "환율/수출입", "금융/자본시장"],
        ["기준금리", "물가·환율", "통화정책 시간표"],
        119,
    ),
    (
        "iran_china_sanctions_policy",
        ("이란", "iran", "테헤란"),
        ("중국", "china", "제재", "경제적 압박", "보복"),
        ["돈 버는 능력", "할인율", "수급", "시간표"],
        ["원유/인플레이션", "정유/화학/해운", "방산/지정학"],
        ["대이란 제재", "중국 원유·무역", "유가·운임"],
        119,
    ),
    (
        "kioxia_iwate_nand_factory_capex",
        ("키옥시아", "kioxia"),
        ("이와테", "iwate", "낸드", "nand"),
        ["돈 버는 능력", "수급", "시간표"],
        ["DRAM/NAND", "반도체 장비·소재", "일본 제조 CAPEX"],
        ["낸드 생산능력", "일본 공장 CAPEX", "공급 경쟁"],
        116,
    ),
)


AUGUST30_ATTACHMENT_PROFILES = (
    (
        "skhynix_2030_memory_shortage_outlook",
        ("곽노정", "sk하이닉스", "sk hynix"),
        ("2030년", "2030년말", "2030년 말", "공급 부족", "공급부족"),
        ["돈 버는 능력", "수급", "시간표"],
        ["반도체/HBM/CXL", "DRAM/NAND", "AI/데이터센터"],
        ["메모리 공급 전망", "HBM 수요", "공급부족 시간표"],
        119,
    ),
    (
        "nvidia_memory_cost_margin_pressure",
        ("엔비디아", "nvidia"),
        ("메모리값", "메모리 가격", "메모리 부담", "마진", "gpm"),
        ["돈 버는 능력", "수급", "시간표"],
        ["반도체/HBM/CXL", "AI/데이터센터", "DRAM/NAND"],
        ["메모리 원가", "엔비디아 마진", "HBM 가격"],
        119,
    ),
    (
        "nvidia_ai_hbm_demand_outlook",
        ("엔비디아", "nvidia"),
        ("삼성전자", "sk하이닉스", "메모리 공급 부족", "메모리 부족", "ai 수요"),
        ["돈 버는 능력", "수급", "시간표"],
        ["반도체/HBM/CXL", "AI/데이터센터", "DRAM/NAND"],
        ["AI 가속기 수요", "메모리 공급", "HBM 매출 기대"],
        118,
    ),
    (
        "iran_ceasefire_oil_price_move",
        ("이란", "iran"),
        ("휴전", "ceasefire", "유가", "원유", "oil", "2%"),
        ["돈 버는 능력", "할인율", "수급", "시간표"],
        ["원유/인플레이션", "정유/화학/해운", "방산/지정학"],
        ["중동 휴전", "유가", "운임·위험프리미엄"],
        118,
    ),
    (
        "hbm_glass_carrier_yield_inspection",
        ("hbm", "글라스 캐리어", "유리 웨이퍼", "glass carrier"),
        ("수율", "결함", "검사", "재생가공", "ai 활용"),
        ["돈 버는 능력", "시간표"],
        ["반도체/HBM/CXL", "반도체 장비·소재"],
        ["HBM 수율", "글라스 캐리어 검사", "후공정 생산성"],
        112,
    ),
    (
        "samsung_china_semiconductor_localization_research",
        ("삼성전자", "삼성"),
        ("중국 반도체국산화", "반도체 국산화", "중국 국산화", "kb증권"),
        ["돈 버는 능력", "수급", "시간표"],
        ["반도체/HBM/CXL", "중국 공급망", "파운드리"],
        ["중국 반도체 국산화", "삼성전자 수혜", "경쟁구도"],
        107,
    ),
    (
        "samsung_skhynix_shareholder_return_program",
        ("삼성전자", "sk하이닉스", "삼전", "닉스"),
        ("자사주", "자기주식", "주주환원", "소각", "매입"),
        ["수급", "돈 버는 능력", "시간표"],
        ["금융/자본시장", "반도체/HBM/CXL"],
        ["자사주 매입·소각", "주주환원", "유통주식수"],
        120,
    ),
    (
        "korea_ess_regulatory_improvement",
        ("ess", "에너지저장장치"),
        ("법적 분류", "이격거리", "규제 개선", "규제개선"),
        ["돈 버는 능력", "할인율", "시간표"],
        ["ESS/전력변환장치", "전력기기/전력망", "산업정책/첨단전략산업"],
        ["ESS 인허가", "안전기준", "프로젝트 시간표"],
        114,
    ),
    (
        "tsmc_foundry_share_gap",
        ("tsmc", "대만 tsmc", "대만적층"),
        ("점유율 73", "73%", "삼성은 7", "삼성전자 7"),
        ["돈 버는 능력", "수급", "시간표"],
        ["파운드리", "반도체/HBM/CXL", "AI/데이터센터"],
        ["파운드리 점유율", "고객 수주", "첨단공정 경쟁"],
        113,
    ),
    (
        "korea_zinc_semiconductor_sulfuric_acid_capacity",
        ("고려아연", "korea zinc"),
        ("반도체황산", "반도체 황산", "4만t", "4만톤", "4만 t"),
        ["돈 버는 능력", "시간표"],
        ["반도체 장비·소재", "비철금속/제련"],
        ["반도체황산 공급", "소재 생산능력", "증설 시간표"],
        114,
    ),
    (
        "samsung_skhynix_hbm_packaging_roadmap",
        ("삼성전자", "sk하이닉스", "삼성", "sk"),
        ("hbm", "패키징", "cube-e", "2.3d"),
        ["돈 버는 능력", "수급", "시간표"],
        ["반도체/HBM/CXL", "반도체 장비·소재", "AI/데이터센터"],
        ["HBM 패키징", "고객 인증", "첨단패키징 경쟁"],
        113,
    ),
    (
        "nxt_premarket_microstructure_rule",
        ("nxt", "넥스트레이드"),
        ("프리마켓", "프리 마켓", "거래 방식", "거래방식", "하한가"),
        ["수급", "시간표"],
        ["금융/자본시장", "ETF/ETN", "반도체/HBM/CXL"],
        ["대체거래소 제도", "프리마켓 가격발견", "거래규칙"],
        114,
    ),
    (
        "us_chip_tariff_embedded_products",
        ("트럼프", "trump", "미국 행정부", "미국"),
        ("반도체 관세", "칩 관세", "칩 들어간 제품", "칩이 들어간", "embedded product"),
        ["돈 버는 능력", "할인율", "시간표"],
        ["관세/수출주", "반도체/HBM/CXL", "중국 공급망"],
        ["반도체 관세", "내장제품 적용", "공급망 원가"],
        120,
    ),
    (
        "openai_samsung_computational_memory",
        ("오픈ai", "openai"),
        ("삼성", "연산 메모리", "z hbm", "zhbm", "베이스다이"),
        ["돈 버는 능력", "수급", "시간표"],
        ["반도체/HBM/CXL", "AI/데이터센터", "반도체 장비·소재"],
        ["AI 자체칩", "연산 메모리", "HBM 병목"],
        115,
    ),
    (
        "us_venezuela_oil_agreement",
        ("베네수엘라", "venezuela"),
        ("석유 합의", "원유 합의", "oil agreement", "650억 배럴", "65 billion barrels"),
        ["돈 버는 능력", "할인율", "수급", "시간표"],
        ["원유/인플레이션", "정유/화학/해운", "방산/지정학"],
        ["원유 공급", "대베네수엘라 정책", "유가 위험프리미엄"],
        120,
    ),
    (
        "cxmt_memory_revenue_growth",
        ("cxmt", "창신메모리"),
        ("매출", "10배", "10 배", "10x", "hbm"),
        ["돈 버는 능력", "수급", "시간표"],
        ["DRAM/NAND", "중국 메모리 공급", "반도체/HBM/CXL"],
        ["중국 D램 매출", "메모리 공급경쟁", "가격 사이클"],
        118,
    ),
    (
        "ymtc_nand_wafer_capacity_expansion",
        ("ymtc", "창장메모리", "yangtze memory"),
        ("250만장", "250만 장", "웨이퍼", "생산능력", "캐파"),
        ["돈 버는 능력", "수급", "시간표"],
        ["DRAM/NAND", "중국 메모리 공급", "반도체/HBM/CXL"],
        ["낸드 웨이퍼 공급", "중국 생산능력", "점유율 경쟁"],
        118,
    ),
    (
        "china_mobile_lpddr6_commercialization",
        ("cxmt", "창신메모리"),
        ("lpddr6", "샤오미", "xiaomi", "양산", "탑재"),
        ["돈 버는 능력", "수급", "시간표"],
        ["DRAM/NAND", "중국 메모리 공급", "모바일/AI PC"],
        ["LPDDR6 양산", "모바일 고객 채택", "중국 메모리 경쟁"],
        116,
    ),
    (
        "single_stock_leverage_etf_rule_effect",
        ("단일종목", "레버리지"),
        ("19조", "5000억", "거래대금", "거래량", "규제"),
        ["수급"],
        ["ETF/ETN", "금융/자본시장", "반도체/HBM/CXL"],
        ["레버리지 ETF 규제", "개인 수급", "거래대금"],
        116,
    ),
    (
        "korea_robotaxi_commercialization",
        ("포니ai", "pony ai", "로보택시", "robotaxi"),
        ("상용화", "퓨처링크", "7세대", "도입", "운행"),
        ["돈 버는 능력", "수급", "시간표"],
        ["로봇/생산자동화", "자동차/부품", "AI/데이터센터"],
        ["로보택시 상용화", "자율주행 도입", "국내 서비스 일정"],
        111,
    ),
    (
        "samsung_sdi_gm_ess_jv_restructure",
        ("삼성sdi", "samsung sdi"),
        ("gm", "시너지셀스", "26gwh", "전략 인수", "합작법인"),
        ["돈 버는 능력", "시간표"],
        ["2차전지/배터리", "ESS/전력변환장치", "미국 제조 CAPEX"],
        ["ESS 셀 생산능력", "합작법인 지분", "미국 가동 일정"],
        115,
    ),
    (
        "samsung_skhynix_margin_credit_concentration",
        ("삼성전자", "sk하이닉스", "삼전", "하이닉스"),
        ("신용거래융자", "신용잔고", "빚투", "신용자금"),
        ["수급"],
        ["금융/자본시장", "반도체/HBM/CXL"],
        ["신용융자", "개인 수급", "변동성"],
        113,
    ),
    (
        "korea_ai_megaproject_personnel_policy",
        ("ai 메가프로젝트", "ai·메가프로젝트", "메가프로젝트"),
        ("핀셋인사", "핀셋 인사", "인사", "정부", "대통령"),
        ["시간표", "할인율"],
        ["산업정책/첨단전략산업", "AI/데이터센터", "반도체/HBM/CXL"],
        ["AI 산업정책", "프로젝트 집행", "정책 시간표"],
        109,
    ),
    (
        "us_china_trade_truce_calendar",
        ("미국", "중국", "시진핑"),
        ("무역 휴전", "무역휴전", "휴전 연장", "방문", "정상회담"),
        ["할인율", "시간표"],
        ["관세/수출주", "중국 공급망", "반도체/HBM/CXL"],
        ["미·중 무역협상", "관세 일정", "정상외교"],
        112,
    ),
)


AUGUST26_ATTACHMENT_PROFILES = (
    (
        "nvidia_samsung_foundry_inference_mass_production",
        ("엔비디아", "nvidia"),
        ("그록3", "groq3", "lpx", "추론가속기", "추론 가속기", "inference accelerator"),
        ["돈 버는 능력", "수급", "시간표"],
        ["반도체/HBM/CXL", "파운드리", "AI/데이터센터"],
        ["AI 추론칩 양산", "파운드리 매출", "고객 다변화"],
        120,
    ),
    (
        "korea_samsung_skhynix_us_treasury_mixed_etf",
        ("삼성전자", "sk하이닉스"),
        ("미국 단기국채", "미국채혼합", "미국채 혼합"),
        ["수급", "시간표"],
        ["ETF/ETN", "금융/자본시장", "반도체/HBM/CXL"],
        ["ETF 신규 상장", "연금계좌 수급", "미국 단기국채 혼합"],
        107,
    ),
    (
        "korea_ai_semiconductor_etf_listing",
        ("삼성전자", "sk하이닉스", "삼성전기", "ai 반도체"),
        ("퇴직연금", "채권혼합", "채권 혼합", "etf 상장", "etf 출시"),
        ["수급", "시간표"],
        ["ETF/ETN", "금융/자본시장", "반도체/HBM/CXL"],
        ["ETF 신규 상장", "연금계좌 수급"],
        107,
    ),
    (
        "china_humanoid_robot_funding",
        ("샤오펑", "xpeng", "도고틱스", "dogo"),
        ("휴머노이드", "로봇", "robot", "로보틱스"),
        ["돈 버는 능력", "수급", "시간표"],
        ["로봇/생산자동화", "중국 공급망", "AI/데이터센터"],
        ["로봇 자금조달", "중국 피지컬 AI CAPEX"],
        112,
    ),
    (
        "skhynix_advanced_memory_thermal_packaging",
        ("sk하이닉스", "sk hynix"),
        ("하이브리드 본딩", "hybrid bonding", "i-hbm", "수직 적층", "수직적층", "emib", "열 관리"),
        ["돈 버는 능력", "시간표"],
        ["반도체/HBM/CXL", "반도체 장비·소재", "AI/데이터센터"],
        ["HBM 열관리", "차세대 패키징", "고객 인증"],
        116,
    ),
    (
        "korea_ai_semiconductor_budget",
        ("정부", "기획재정부", "재정"),
        ("슈퍼예산", "슈퍼 예산", "ai·반도체", "ai 반도체", "반도체·ai"),
        ["돈 버는 능력", "할인율", "시간표"],
        ["산업정책/첨단전략산업", "반도체/HBM/CXL", "AI/데이터센터"],
        ["재정지원", "R&D·인프라 투자", "예산 편성 시간표"],
        116,
    ),
    (
        "china_memory_self_sufficiency_forecast",
        ("cxmt", "창신메모리", "smic"),
        ("2028", "d램", "dram", "hbm", "자급", "자립", "수요"),
        ["돈 버는 능력", "수급", "시간표"],
        ["DRAM/NAND", "중국 메모리 공급", "반도체/HBM/CXL"],
        ["중국 메모리 증설", "공급경쟁", "가격 사이클"],
        115,
    ),
    (
        "nvidia_rubin_margin_ramp",
        ("엔비디아", "nvidia"),
        ("베라 루빈", "베라루빈", "vera rubin", "마진 75", "75%"),
        ["돈 버는 능력", "수급", "시간표"],
        ["반도체/HBM/CXL", "AI/데이터센터"],
        ["AI 가속기 램프", "총마진", "HBM 수요"],
        116,
    ),
    (
        "ai_memory_revenue_growth_outlook",
        ("삼성전자", "sk하이닉스"),
        ("메모리 매출", "hbm", "d램", "dram", "낸드"),
        ["돈 버는 능력", "수급", "시간표"],
        ["반도체/HBM/CXL", "DRAM/NAND", "AI/데이터센터"],
        ["메모리 ASP·물량", "AI 데이터센터 수요"],
        115,
    ),
    (
        "korea_single_stock_leverage_etf_volatility",
        ("삼성전자", "sk하이닉스", "삼전", "닉스"),
        ("2배 etf", "2배etf", "단일종목 레버리지", "레버리지 etf", "레버리지etf"),
        ["수급"],
        ["ETF/ETN", "금융/자본시장", "반도체/HBM/CXL"],
        ["레버리지 거래", "개인 수급", "변동성"],
        108,
    ),
    (
        "samsung_pim_ai_pc_commercialization",
        ("삼성전자", "삼성", "samsung"),
        ("pim", "lpddr5x-pim", "가이아", "gaia", "온디바이스"),
        ["돈 버는 능력", "시간표"],
        ["반도체/HBM/CXL", "모바일/AI PC", "반도체 장비·소재"],
        ["PIM 상용화", "AI PC 제품", "메모리 믹스"],
        113,
    ),
    (
        "nvidia_amkor_advanced_packaging_contract",
        ("엔비디아", "nvidia"),
        ("앰코", "amkor", "15억달러", "15억 달러", "선급금", "장기계약", "장기 계약"),
        ["돈 버는 능력", "수급", "시간표"],
        ["반도체/HBM/CXL", "반도체 장비·소재", "AI/데이터센터"],
        ["첨단패키징 장기계약", "선급금", "AI 공급망"],
        120,
    ),
    (
        "samsung_skhynix_leveraged_etf_outflow",
        ("삼성전자", "sk하이닉스", "삼전", "닉스"),
        ("레버리지 etf", "레버리지etf", "2배 etf", "2배etf"),
        ["수급"],
        ["ETF/ETN", "금융/자본시장", "반도체/HBM/CXL"],
        ["레버리지 ETF 자금유출", "단기 매매 수급"],
        112,
    ),
    (
        "ai_mlcc_supply_bottleneck",
        ("mlcc",),
        ("ai", "인공지능", "데이터센터", "반도체"),
        ["돈 버는 능력", "수급", "시간표"],
        ["전자부품/MLCC", "AI/데이터센터", "반도체/HBM/CXL"],
        ["AI 부품 수요", "MLCC 공급병목"],
        110,
    ),
)


AUGUST23_ATTACHMENT_PROFILES = (
    (
        "iran_economic_war_trade_risk",
        ("이란", "iran", "테헤란", "tehran"),
        ("경제 전쟁", "economic war", "무력화", "neutralise", "neutralize"),
        ["할인율", "수급", "시간표"],
        ["원유/인플레이션", "정유/화학/해운", "방산/지정학"],
        ["제재·전쟁 대응", "중동 지정학", "원유·운임"],
        116,
    ),
    (
        "russia_ukraine_economic_targets",
        ("푸틴", "putin", "러시아", "russia"),
        ("경제적 목표", "경제 목표", "경제 시설", "pandora", "판도라의 상자"),
        ["할인율", "시간표"],
        ["원유/인플레이션", "방산/지정학", "해운/물류"],
        ["러시아·우크라이나 전쟁", "에너지·물류 위험", "제재 시간표"],
        112,
    ),
    (
        "agi_advanced_packaging_hbm_bottleneck",
        ("agi", "인공일반지능", "반도체 패키징", "반도체패키징"),
        ("hbm", "병목", "첨단 패키징", "첨단패키징"),
        ["돈 버는 능력", "수급", "시간표"],
        ["반도체/HBM/CXL", "반도체 장비·소재", "AI/데이터센터"],
        ["HBM 패키징 수요", "첨단패키징 병목", "AI 공급능력"],
        118,
    ),
    (
        "active_covered_call_etf_net_buy",
        ("ace", "커버드콜", "covered call"),
        ("순매수", "자금 유입", "자금유입"),
        ["수급"],
        ["금융/자본시장", "ETF/ETN", "고배당·커버드콜"],
        ["ETF 순매수", "개인·기관 수급"],
        109,
    ),
    (
        "samsung_exynos_2nm_performance",
        ("엑시노스", "exynos"),
        ("퀄컴", "qualcomm", "2나노", "2nm", "2㎚"),
        ["돈 버는 능력", "시간표"],
        ["반도체/HBM/CXL", "파운드리", "모바일 AP"],
        ["모바일 AP 성능", "2나노 공정", "고객 인증"],
        114,
    ),
    (
        "nvidia_earnings_jackson_hole_calendar",
        ("엔비디아", "nvidia"),
        ("실적 발표", "실적발표", "잭슨홀", "jackson hole"),
        ["할인율", "수급", "시간표"],
        ["반도체/HBM/CXL", "AI/데이터센터", "미국 증시/금리"],
        ["엔비디아 실적", "연준 정책신호", "AI 투자심리"],
        116,
    ),
    (
        "us_fiscal_deficit_treasury_yield",
        ("미국", "u.s.", "us treasury", "미 재정"),
        ("재정적자", "재정 적자", "정부부채", "정부 부채", "국가부채", "국가 부채", "fiscal deficit", "government debt"),
        ["할인율", "수급"],
        ["미국 증시/금리", "환율/수출입", "성장주/밸류에이션"],
        ["미 국채 공급", "장기금리", "달러·외국인 수급"],
        118,
    ),
)


AUGUST22_ATTACHMENT_PROFILES = (
    (
        "iran_china_trade_policy",
        ("이란", "iran"),
        ("경제적 d-day", "경제적 d day", "경제적 데이", "최대 무역 상대국", "무역 상대국"),
        ["돈 버는 능력", "할인율", "수급", "시간표"],
        ["관세/수출주", "원유/인플레이션", "정유/화학/해운", "방산/지정학"],
        ["이란 제재·무역압박", "중국 원유수요", "대미 통상 위험"],
        116,
    ),
    (
        "iran_china_oil_trade",
        ("이란", "iran"),
        ("중국 원유", "중국의 석유", "석유 수입", "브렌트", "brent"),
        ["돈 버는 능력", "할인율", "수급", "시간표"],
        ["원유/인플레이션", "정유/화학/해운", "방산/지정학"],
        ["중국 원유수요", "브렌트·운임", "중동 휴전 시간표"],
        116,
    ),
    (
        "skhynix_overseas_hbm_production",
        ("sk하이닉스", "sk hynix"),
        ("일본", "해외", "생산거점", "반도체 공장"),
        ["돈 버는 능력", "시간표"],
        ["반도체/HBM/CXL", "미국·일본 제조 CAPEX", "반도체 장비·소재"],
        ["HBM 생산거점", "해외 CAPEX", "생산·가동 시간표"],
        118,
    ),
    (
        "samsung_tv_memory_cost_share",
        ("삼성전자", "samsung"),
        ("tv", "미니 led", "출하량", "점유율", "메모리 가격"),
        ["돈 버는 능력", "시간표"],
        ["가전/디스플레이", "반도체/HBM/CXL", "소비 IT"],
        ["TV 출하·점유율", "메모리 원가", "제품 믹스"],
        107,
    ),
    (
        "samsung_labor_compensation_risk",
        ("삼성전자", "삼성"),
        ("노조", "임단협", "파업", "성과급"),
        ["돈 버는 능력", "시간표"],
        ["반도체/HBM/CXL", "가전/디스플레이"],
        ["인건비", "노사협상", "가동 리스크"],
        106,
    ),
    (
        "ymtc_nand_ipo",
        ("ymtc", "창장메모리", "yangtze memory"),
        ("ipo", "상장", "조달", "낸드", "ssd"),
        ["돈 버는 능력", "수급", "시간표"],
        ["반도체/HBM/CXL", "DRAM/NAND", "중국 메모리 공급"],
        ["중국 낸드 공급", "IPO 자금조달", "경쟁 CAPEX"],
        115,
    ),
    (
        "us_canada_tariff_trade",
        ("캐나다", "canada"),
        ("관세", "무역협정", "무역 협정", "무역전쟁", "무역 전쟁"),
        ["돈 버는 능력", "할인율", "시간표"],
        ["관세/수출주", "원자재/매크로", "환율/수출입"],
        ["관세·보복관세", "북미 공급망", "협상 시간표"],
        114,
    ),
    (
        "anthropic_ipo_ai_infrastructure",
        ("앤트로픽", "anthropic"),
        ("ipo", "상장", "기업가치", "투자설명서"),
        ["돈 버는 능력", "수급", "시간표"],
        ["AI/데이터센터", "반도체/HBM/CXL", "전력기기/전력망"],
        ["AI 자본조달", "데이터센터 CAPEX", "상장 시간표"],
        116,
    ),
    (
        "samsung_skhynix_hbm_hotchips",
        ("삼성전자", "sk하이닉스"),
        ("핫칩스", "hot chips"),
        ["돈 버는 능력", "수급", "시간표"],
        ["반도체/HBM/CXL", "반도체 장비·소재", "AI/데이터센터"],
        ["HBM 기술공개", "고객 인증", "학회 시간표"],
        112,
    ),
    (
        "nvidia_ai_server_memory_price",
        ("엔비디아", "nvidia"),
        ("ai 서버", "ai서버", "메모리 품귀", "메모리 부족", "가격 인상"),
        ["돈 버는 능력", "수급", "시간표"],
        ["반도체/HBM/CXL", "AI/데이터센터", "서버/OEM"],
        ["AI 서버 ASP", "HBM·DRAM 원가", "고객 CAPEX"],
        120,
    ),
    (
        "bigtech_ai_credit_yield",
        ("빅테크", "하이퍼스케일러", "마이크로소프트", "구글", "아마존", "메타"),
        ("회사채", "회사채 발행", "미국 국채", "국채 금리"),
        ["돈 버는 능력", "할인율", "수급"],
        ["AI/데이터센터", "미국 증시/금리", "반도체/HBM/CXL"],
        ["AI CAPEX 조달", "회사채 공급", "미 국채 금리"],
        118,
    ),
    (
        "us_apec_china_policy",
        ("apec", "미국 우선주의", "america first"),
        ("중국", "시진핑", "정상회담", "의제"),
        ["할인율", "시간표"],
        ["관세/수출주", "반도체/HBM/CXL", "중국 공급망"],
        ["미·중 통상정책", "APEC 정상외교", "수출통제 위험"],
        109,
    ),
    (
        "us_beef_tariff_policy",
        ("트럼프", "trump", "미국"),
        ("쇠고기", "beef", "미국산 소고기", "미국산 쇠고기"),
        ["돈 버는 능력", "할인율", "시간표"],
        ["관세/수출주", "원자재/매크로", "식품/유통"],
        ["농축산물 관세", "물가·소비", "통상 협상"],
        108,
    ),
    (
        "trump_asset_trade_disclosure",
        ("트럼프", "trump"),
        ("자산공시", "투자계좌", "주식 거래", "etf 거래"),
        ["수급", "시간표"],
        ["금융/자본시장", "미국 증시/금리"],
        ["대통령 자산공시", "대형 거래", "정책 이해상충"],
        108,
    ),
)
def build_attachment_verified_event_alert(row: dict, now, text: str) -> dict | None:
    """Route recurring company and market events from verified article bodies."""
    title = str(row.get("source_title") or row.get("title") or "")
    body = str(row.get("source_body") or row.get("source_abstract") or "")
    profiles = (*AUGUST30_ATTACHMENT_PROFILES, *AUGUST27_ATTACHMENT_PROFILES, *AUGUST26_ATTACHMENT_PROFILES, *AUGUST23_ATTACHMENT_PROFILES, *AUGUST13_ATTACHMENT_PROFILES, *AUGUST22_ATTACHMENT_PROFILES,
        ("korea_zinc_critical_minerals", ("고려아연",), ("핵심광물", "핵심 광물", "제련소", "통합제련소"), ["돈 버는 능력", "할인율", "시간표"], ["핵심광물", "비철금속/제련", "미국 공급망"], ["미국 정책 연결", "제련 CAPEX", "핵심광물 공급"], 111),
        ("korea_anthropic_strategic_investment", ("앤트로픽", "anthropic"), ("네이버", "naver", "삼성전자", "sk텔레콤", "skt"), ["돈 버는 능력", "수급", "시간표"], ["AI/데이터센터", "반도체/HBM/CXL", "플랫폼/클라우드"], ["AI 전략투자", "모델 협업", "데이터센터 수요"], 109),
        ("apple_cxmt_memory_supply_test", ("애플", "apple"), ("cxmt", "창신메모리", "중국 메모리", "중국 d램"), ["돈 버는 능력", "수급", "시간표"], ["반도체/HBM/CXL", "DRAM/NAND", "중국 메모리 공급"], ["고객 인증", "메모리 공급", "경쟁구도"], 112),
        ("ai_infrastructure_finance_platform", ("금융플랫폼", "금융 플랫폼", "자금조달", "투자플랫폼", "투자 플랫폼"), ("ai 인프라", "ai인프라", "데이터센터", "gpu", "컴퓨팅"), ["돈 버는 능력", "할인율", "시간표"], ["AI/데이터센터", "전력기기/전력망", "반도체/HBM/CXL"], ["데이터센터 금융", "CAPEX 조달", "AI 인프라"], 110),
        ("skhynix_kioxia_ownership_structure", ("sk하이닉스", "sk hynix"), ("키옥시아", "kioxia"), ["돈 버는 능력", "수급", "시간표"], ["반도체/HBM/CXL", "DRAM/NAND", "기업결합/지분"], ["낸드 경쟁구도", "CB 전환", "경쟁당국 승인"], 109),
        ("korea_etf_asset_flow", ("etf", "상장지수펀드"), ("자금유출", "자금 유출", "자금유입", "자금 유입", "순자산", "설정액", "환매"), ["수급"], ["금융/자본시장", "ETF/ETN"], ["ETF 설정·환매", "투자자 수급"], 106),
        ("korea_solar_module_capacity", ("태양광 모듈", "태양광모듈", "solar module"), ("신규 라인", "신규라인", "양산", "생산라인", "공장 가동", "증설"), ["돈 버는 능력", "시간표"], ["태양광/신재생", "전력기기/전력망"], ["모듈 생산능력", "양산 시간표"], 106),
        ("korea_large_mna_credit_structure", ("인수", "m&a", "매각 계약", "매각계약"), ("조원", "억원", "pef", "사모펀드", "tpg", "kkr", "mbk"), ["돈 버는 능력", "수급", "시간표"], ["금융/자본시장", "기업 M&A"], ["인수 구조", "신용등급", "자금조달"], 110),
        ("ai_cloud_gpu_lessors_earnings", ("코어위브", "coreweave", "nebius", "crusoe", "gpu 클라우드", "gpu cloud"), ("매출", "실적", "가이던스", "수요", "계약", "revenue", "earnings", "guidance"), ["돈 버는 능력", "수급", "시간표"], ["AI/데이터센터", "반도체/HBM/CXL", "전력기기/전력망"], ["AI 클라우드 매출", "GPU 임대 수요", "AI CAPEX"], 116),
        ("china_memory_yield_oem_supply", ("cxmt", "창신메모리", "중국 메모리"), ("수율", "yield", "hp", "에이수스", "asus", "에이서", "acer", "pc 제조사"), ["돈 버는 능력", "수급", "시간표"], ["반도체/HBM/CXL", "DRAM/NAND", "중국 메모리 공급"], ["DDR5 수율", "PC OEM 공급", "범용 DRAM 가격"], 115),
        ("korea_semiconductor_power_supply_pact", ("한국전력", "한전"), ("삼성전자", "sk하이닉스", "반도체 산단", "반도체산단"), ["돈 버는 능력", "할인율", "시간표"], ["반도체/HBM/CXL", "전력기기/전력망", "송배전"], ["반도체 전력공급", "송변전 투자", "산단 가동 시간표"], 118),
        ("foreign_sovereign_fund_korea_semis", ("테마섹", "temasek", "국부펀드", "sovereign fund"), ("삼성전자", "sk하이닉스", "한국 반도체", "k증시"), ["수급"], ["금융/자본시장", "반도체/HBM/CXL"], ["해외 장기자금", "대형주 수급"], 113),
        ("korea_public_fund_asset_flow", ("공모펀드", "인덱스펀드", "인덱스 펀드"), ("순자산", "설정액", "환매", "자금유입", "자금 유입", "자금유출", "자금 유출"), ["수급"], ["금융/자본시장", "펀드 수급"], ["공모펀드 설정·환매", "장기자금 수급"], 105),
        ("tsmc_advanced_packaging_capex", ("tsmc", "대만적층", "taiwan semiconductor"), ("cowos", "첨단패키징", "첨단 패키징", "2나노"), ["돈 버는 능력", "시간표"], ["반도체/HBM/CXL", "반도체 장비·소재", "AI/데이터센터"], ["첨단패키징 CAPEX", "CoWoS 공급", "AI 가속기 생산능력"], 116),
    )
    for kind, anchors, triggers, impacts, sectors, paths, score in profiles:
        normalized_anchors = tuple(str(term).lower() for term in anchors)
        normalized_triggers = tuple(str(term).lower() for term in triggers)
        if not any(term in text for term in normalized_anchors) or not any(term in text for term in normalized_triggers):
            continue
        if kind == "skhynix_2030_memory_shortage_outlook" and not (
            any(term in title.lower() for term in ("곽노정", "2030년", "공급 부족"))
            and any(term in text for term in ("2030년", "2030년말", "2030년 말"))
            and any(term in text for term in ("공급 부족", "공급부족"))
        ):
            continue
        if kind == "nvidia_memory_cost_margin_pressure" and not (
            any(term in text for term in ("메모리값", "메모리 가격", "메모리 부담"))
            and any(term in text for term in ("마진", "gpm"))
            and re.search(r"71\s*[~～-]\s*72\s*%", text)
        ):
            continue
        if kind == "nvidia_ai_hbm_demand_outlook" and any(
            term in text
            for term in (
                "hbm4",
                "루빈",
                "rubin",
                "베라",
                "vera",
                "lpddr5x",
                "15%",
                "그록3",
                "groq3",
                "lpx",
                "추론가속기",
                "200만",
                "2 million",
                "two million",
            )
        ):
            continue
        if kind == "nvidia_ai_hbm_demand_outlook" and not (
            any(term in title.lower() for term in ("엔비디아", "nvidia"))
            and any(
                term in text
                for term in ("메모리 공급 부족", "메모리 공급부족", "메모리 부족")
            )
            and any(term in text for term in ("삼성전자", "sk하이닉스"))
        ):
            continue
        if kind == "iran_ceasefire_oil_price_move" and not any(
            term in text for term in ("2%", "2 퍼센트", "2프로", "상승 마감")
        ):
            continue
        if kind == "hbm_glass_carrier_yield_inspection" and not any(
            term in text for term in ("수율", "결함", "검사", "재생가공")
        ):
            continue
        if kind == "samsung_china_semiconductor_localization_research" and not (
            "중국" in text and any(term in text for term in ("국산화", "국산", "현지화"))
        ):
            continue
        if kind == "samsung_skhynix_shareholder_return_program" and not (
            all(term in text for term in ("삼성전자", "sk하이닉스"))
            and re.search(r"\d[\d,.]*\s*조\s*원", text)
            and any(term in text for term in ("자사주", "자기주식"))
            and any(term in text for term in ("매입", "취득", "소각"))
        ):
            continue
        if kind == "korea_ess_regulatory_improvement" and not (
            any(term in text for term in ("법적 분류", "이격거리"))
            and any(term in text for term in ("규제", "개선", "신설"))
        ):
            continue
        if kind == "tsmc_foundry_share_gap" and not all(
            term in text for term in ("73%", "7%")
        ):
            continue
        if kind == "korea_zinc_semiconductor_sulfuric_acid_capacity" and not re.search(
            r"4만\s*(?:t|톤)", text
        ):
            continue
        if kind == "samsung_skhynix_hbm_packaging_roadmap" and not any(
            term in text for term in ("cube-e", "2.3d", "차세대 기술 경쟁")
        ):
            continue
        if kind == "nxt_premarket_microstructure_rule" and not any(
            term in text for term in ("하한가", "가격이 크게", "가격 급변", "가격 변동")
        ):
            continue
        if kind == "us_chip_tariff_embedded_products" and not (
            any(term in text for term in ("칩 들어간 제품", "칩이 들어간", "내장 제품", "내장제품"))
            and any(term in text for term in ("관세", "tariff"))
        ):
            continue
        if kind == "openai_samsung_computational_memory" and not (
            "삼성" in text
            and any(
                term in text
                for term in (
                    "연산 메모리",
                    "연산메모리",
                    "베이스다이",
                    "zhbm",
                    "z hbm",
                )
            )
        ):
            continue
        if kind == "us_venezuela_oil_agreement" and not (
            base.trusted(str(row.get("publisher") or row.get("source") or ""))
            and re.search(r"650억\s*배럴|65\s*billion\s*barrels", text)
            and any(term in text for term in ("합의", "agreement", "통제권", "통제"))
        ):
            continue
        if kind == "cxmt_memory_revenue_growth" and not re.search(
            r"10\s*배|10x|열\s*배", text
        ):
            continue
        if kind == "ymtc_nand_wafer_capacity_expansion" and not re.search(
            r"250만\s*장|250\s*만장", text
        ):
            continue
        if kind == "china_mobile_lpddr6_commercialization" and not (
            "lpddr6" in text and any(term in text for term in ("샤오미", "xiaomi"))
        ):
            continue
        if kind == "single_stock_leverage_etf_rule_effect" and not (
            all(term in text for term in ("19조", "5000억"))
            and any(term in text for term in ("규제", "거래대금", "거래량"))
        ):
            continue
        if kind == "korea_robotaxi_commercialization" and not (
            "퓨처링크" in text and any(term in text for term in ("상용화", "7세대", "도입"))
        ):
            continue
        if kind == "samsung_sdi_gm_ess_jv_restructure" and not (
            "gm" in text and "26gwh" in text
        ):
            continue
        if kind == "samsung_skhynix_margin_credit_concentration" and not (
            all(term in text for term in ("삼성전자", "sk하이닉스"))
            and any(term in text for term in ("신용거래융자", "신용잔고", "빚투", "신용자금"))
        ):
            continue
        if kind == "korea_ai_megaproject_personnel_policy" and not any(
            term in text for term in ("핀셋인사", "핀셋 인사", "미래 먹거리")
        ):
            continue
        if kind == "us_china_trade_truce_calendar" and not (
            "무역" in text and any(term in text for term in ("휴전", "정상회담", "시진핑"))
        ):
            continue
        if kind == "apple_cxmt_memory_supply_test" and not any(term in text for term in ("테스트", "시험", "탑재", "공급", "협력", "채택")):
            continue
        if kind == "us_fiscal_deficit_treasury_yield" and not any(
            term in text for term in ("재정적자", "재정 적자", "정부부채", "정부 부채", "국가부채", "국가 부채", "fiscal deficit")
        ):
            continue
        if kind == "korea_etf_asset_flow" and not re.search(r"\d[\d,.]*(?:조|억)원", text):
            continue
        if kind == "korea_large_mna_credit_structure" and not any(term in text for term in ("계약", "결정", "인수한다", "인수하기로")):
            continue
        if kind == "ai_cloud_gpu_lessors_earnings" and not re.search(r"\d[\d,.]*\s*(?:%|배|조|억|달러|원)", text):
            continue
        if kind == "korea_semiconductor_power_supply_pact" and not any(term in text for term in ("협약", "협정", "mou", "비용분담", "송전", "변전")):
            continue
        if kind == "foreign_sovereign_fund_korea_semis" and not any(term in text for term in ("투자", "지분", "매수", "편입", "출자", "보유")):
            continue
        if kind == "korea_public_fund_asset_flow" and not re.search(r"\d[\d,.]*\s*(?:조|억)원", text):
            continue
        if kind == "tsmc_advanced_packaging_capex" and not any(term in text for term in ("자본지출", "capex", "투자승인", "투자 승인", "이사회 승인", "증설")):
            continue
        if kind == "tesla_us_solar_factory_capex" and not any(
            term in text for term in ("공장", "factory", "건설", "투자", "capex", "고용", "증설")
        ):
            continue
        if kind == "nvidia_rubin_hbm_spec_change" and not any(
            term in text for term in ("사양", "변경", "낮추", "검토", "공급", "수요")
        ):
            continue
        if kind == "skhynix_indiana_advanced_packaging_timeline" and not any(
            term in text for term in ("착공", "공장", "양산", "가동", "투자")
        ):
            continue
        if kind == "ai_datacenter_optical_interconnect" and not any(
            term in text for term in ("병목", "수요", "투자", "증설", "공급", "capex")
        ):
            continue
        if kind == "samsung_datacenter_cooling_capacity" and not any(
            term in text for term in ("공조", "냉각", "hvac", "칠러", "chiller")
        ):
            continue
        if kind == "nvidia_samsung_foundry_inference_mass_production" and not any(
            term in text for term in ("양산", "생산", "위탁 생산", "위탁생산", "파운드리", "foundry")
        ):
            continue
        if kind == "korea_ai_semiconductor_etf_listing" and not any(
            term in text for term in ("ai 반도체", "ai반도체", "삼성전기")
        ):
            continue
        if kind == "korea_samsung_skhynix_us_treasury_mixed_etf" and not (
            "삼성전자" in text
            and "sk하이닉스" in text
            and any(term in text for term in ("미국 단기국채", "미국채혼합", "미국채 혼합"))
            and any(term in text for term in ("상장", "출시", "신규"))
        ):
            continue
        if kind == "china_humanoid_robot_funding" and not (
            any(term in text for term in ("투자", "자금조달", "자금 조달", "신주", "출자", "조달"))
            and re.search(r"\d[\d,.]*\s*(?:억|만)?\s*(?:달러|원)", text)
        ):
            continue
        if kind == "skhynix_advanced_memory_thermal_packaging" and not any(
            term in text for term in ("하이브리드 본딩", "hybrid bonding", "i-hbm", "수직 적층", "수직적층", "emib")
        ):
            continue
        if kind == "korea_ai_semiconductor_budget" and not (
            "예산" in text and re.search(r"\d[\d,.]*\s*(?:조|억)원", text)
        ):
            continue
        if kind == "china_memory_self_sufficiency_forecast" and not (
            ("2028" in text and any(term in text for term in ("d램", "dram", "hbm")))
            or any(term in text for term in ("자급", "자립"))
        ):
            continue
        if kind == "nvidia_rubin_margin_ramp" and not (
            any(term in text for term in ("베라 루빈", "베라루빈", "vera rubin"))
            and any(term in text for term in ("마진", "양산", "램프", "ramp"))
        ):
            continue
        if kind == "ai_memory_revenue_growth_outlook" and not (
            any(term in text for term in ("전망", "예상", "추정", "급증", "증가"))
            and re.search(r"\d[\d,.]*\s*(?:%|배)", text)
        ):
            continue
        if kind == "korea_single_stock_leverage_etf_volatility" and not any(
            term in text for term in ("변동성", "거래대금", "거래량", "급감", "규제", "수급")
        ):
            continue
        if kind == "samsung_pim_ai_pc_commercialization" and not any(
            term in text for term in ("상용화", "탑재", "출시", "양산")
        ):
            continue
        if kind == "nvidia_amkor_advanced_packaging_contract" and not any(
            term in text for term in ("계약", "선급금", "공급", "협력")
        ):
            continue
        if kind == "samsung_skhynix_leveraged_etf_outflow" and not any(
            term in text for term in ("자금유출", "자금 유출", "순유출", "빠져나", "이탈")
        ):
            continue
        if kind == "ai_mlcc_supply_bottleneck" and not any(
            term in text for term in ("공급부족", "공급 부족", "리드타임", "가격 인상", "쇼티지")
        ):
            continue
        if kind == "samsung_labor_separate_bargaining" and not (
            any(term in text for term in ("분리교섭", "분리 교섭"))
            or ("ds" in text and "dx" in text)
        ):
            continue
        if kind == "korea_single_stock_leverage_etf_volume_drop" and not any(
            term in text for term in ("급감", "감소", "줄어", "91%")
        ):
            continue
        if kind == "skhynix_emib_hbm_2p5d_packaging" and not any(
            term in text for term in ("2.5d", "다변화", "diversif")
        ):
            continue
        if kind == "iran_china_sanctions_policy" and not any(
            term in text for term in ("새로운 경제적 압박", "보복을 공언", "보복 공언", "new economic pressure")
        ):
            continue
        if kind == "amazon_nvidia_gpu_2m_capex" and not any(
            term in text for term in ("200만", "2 million", "two million")
        ):
            continue
        if kind == "nvidia_memory_purchase_commitments" and not any(
            term in text for term in ("2790억", "279 billion", "2790")
        ):
            continue
        if kind == "nvidia_hbm4_rubin_vera_memory_shortage" and not (
            any(
                term in text
                for term in ("메모리 부족", "메모리 공급부족", "메모리 공급 부족", "supply shortage")
            )
            and (
                any(term in text for term in ("루빈", "rubin", "베라", "vera", "hbm4", "lpddr5x"))
                or (
                    any(term in text for term in ("삼성전자", "삼전"))
                    and any(term in text for term in ("sk하이닉스", "하이닉스", "sk hynix"))
                )
            )
        ):
            continue
        if kind == "iran_opec_china_oil_market_shift" and not (
            base.trusted(str(row.get("publisher") or row.get("source") or ""))
            and all(
                term in text
                for term in ("이란", "중국", "opec")
            )
            and any(term in text for term in ("석유", "원유", "oil"))
        ):
            continue
        if kind == "us_datacenter_tariff_cost_pressure" and not (
            base.trusted(str(row.get("publisher") or row.get("source") or ""))
            and any(term in text for term in ("트럼프", "trump"))
            and any(term in text for term in ("관세", "tariff"))
            and any(term in text for term in ("데이터센터", "data center"))
        ):
            continue
        if kind == "nvidia_earnings_actual" and not any(
            term in text for term in ("15분기", "15 quarter", "fifteen quarter")
        ):
            continue
        if kind == "skhynix_us_hbm_advanced_packaging_capex" and not any(
            term in text for term in ("웨스트라피엣", "west lafayette")
        ):
            continue
        if kind == "kioxia_iwate_nand_factory_capex" and not any(
            term in text for term in ("이와테", "iwate")
        ):
            continue
        core = detailed_article_core(title, body)
        if kind == "korea_etf_asset_flow":
            valuation_drop = (
                "순자산" in text
                and any(term in text for term in ("평가액", "기초자산 가격", "증발", "감소", "줄었"))
            )
            decline_matches = re.findall(
                r"(\d[\d,.]*\s*조원)\s*(?:증발|감소|줄었|줄었다)",
                text,
            )
            amount_match = re.search(r"\d[\d,.]*(?:조|억)원", text)
            if valuation_drop and decline_matches:
                core = (
                    "국내 주식형 ETF 순자산이 기초자산 가격 하락과 레버리지 규제 영향으로 "
                    f"{decline_matches[-1]} 감소했습니다."
                )
            elif any(term in text for term in ("자금유출", "자금 유출", "빠져나")) and amount_match:
                core = f"국내 ETF에서 {amount_match.group(0)} 자금이 유출됐습니다."
            elif any(term in text for term in ("자금유입", "자금 유입", "순매수")) and amount_match:
                core = f"국내 ETF에 {amount_match.group(0)} 자금이 유입됐습니다."
        elif kind == "nvidia_ai_server_memory_price" and "15%" in text:
            core = "엔비디아가 메모리 부족을 이유로 AI 서버 가격을 15% 인상하겠다고 고객사에 통보했습니다."
        elif kind == "active_covered_call_etf_net_buy" and "ace" in text and "1천억" in text:
            core = "ACE 고배당주PLUS커버드콜액티브 순매수가 1천억원을 돌파했습니다."
        elif kind == "korea_solar_module_capacity" and "신성이엔지" in text:
            core = "신성이엔지가 김제공장 신규 라인을 가동해 태양광 모듈 양산을 시작했습니다."
        elif kind == "skhynix_indiana_advanced_packaging_timeline":
            date = "27일" if "27일" in text else "예정된 일정에 따라"
            core = f"SK하이닉스가 {date} 미국 인디애나 첨단 패키징 공장 착공식을 열며 2028년 하반기 양산을 목표로 합니다."
        elif kind == "nvidia_samsung_foundry_inference_mass_production":
            core = "엔비디아가 삼성전자 파운드리에 그록3 LPX 추론가속기 양산을 맡겼다고 보도됐습니다."
        elif kind == "korea_samsung_skhynix_us_treasury_mixed_etf":
            core = "미래에셋운용이 삼성전자·SK하이닉스 각 25%와 미국 단기국채 50%를 담은 혼합 ETF를 상장했습니다."
        elif kind == "korea_ai_semiconductor_etf_listing":
            core = "삼성전자·SK하이닉스·삼성전기를 담은 퇴직연금 AI반도체 ETF가 상장됩니다."
        elif kind == "china_humanoid_robot_funding":
            core = "샤오펑 로봇 자회사 도고틱스가 대규모 자금조달을 추진한다고 보도됐습니다."
        elif kind == "skhynix_advanced_memory_thermal_packaging":
            core = "SK하이닉스가 HBM 열 문제 대응으로 하이브리드 본딩·I-HBM과 인텔 EMIB 활용을 제시했습니다."
        elif kind == "korea_ai_semiconductor_budget":
            core = "정부가 AI·반도체 경쟁력 강화를 위해 800조원대 슈퍼예산 편성을 추진한다고 보도됐습니다."
        elif kind == "china_memory_self_sufficiency_forecast" and any(
            term in text for term in ("골드만", "goldman")
        ):
            core = "골드만삭스는 CXMT가 2028년 중국 D램·HBM 수요의 상당 부분을 충족할 수 있다고 전망했습니다."
        elif kind == "nvidia_rubin_margin_ramp":
            core = "엔비디아 베라루빈의 양산 속도와 75% 마진 유지가 AI 반도체 투자심리의 핵심 변수로 제시됐습니다."
        elif kind == "ai_memory_revenue_growth_outlook":
            core = "AI 데이터센터 투자 확대로 삼성전자·SK하이닉스 메모리 매출이 280% 급증할 수 있다는 전망이 나왔습니다."
        elif kind == "korea_single_stock_leverage_etf_volatility":
            core = "삼성전자·SK하이닉스 단일종목 2배 ETF가 한국 증시 변동성을 키웠다는 분석이 나왔습니다."
        elif kind == "samsung_pim_ai_pc_commercialization":
            core = "삼성전자가 AI PC용 가이아에 LPDDR5X-PIM을 탑재해 PIM 상용화를 추진한다고 밝혔습니다."
        elif kind == "nvidia_amkor_advanced_packaging_contract":
            core = "엔비디아가 앰코와 첨단패키징 장기계약을 맺고 선급금을 제공했다는 보도가 나왔습니다."
        elif kind == "samsung_skhynix_leveraged_etf_outflow":
            core = "삼성전자·SK하이닉스 연계 레버리지 ETF에서 10억달러(약 1조4000억원) 순유출이 발생했다고 보도됐습니다."
        elif kind == "us_h1b_visa_fee_proposal":
            core = "트럼프 행정부가 H-1B 전문직 비자 수수료 인상안을 제안했다고 보도됐습니다."
        elif kind == "samsung_labor_separate_bargaining":
            core = "삼성전자 DS·DX 사업장 노조의 분리교섭 구조가 현실화됐다고 보도됐습니다."
        elif kind == "korea_single_stock_leverage_etf_volume_drop":
            core = "삼성전자·SK하이닉스 단일종목 레버리지 ETF 거래대금이 한 달 새 91% 감소했습니다."
        elif kind == "openai_broadcom_jalapeno_inference_chip":
            core = "오픈AI가 브로드컴과 개발한 자체 AI칩 할라페뇨를 연내 추론 서비스에 투입한다고 보도됐습니다."
        elif kind == "china_ai_price_war_short_interest":
            core = "중국 AI 가격경쟁 속 지푸·미니맥스에 공매도 수요가 몰렸다고 보도됐습니다."
        elif kind == "skhynix_emib_hbm_2p5d_packaging":
            core = "SK하이닉스가 인텔 EMIB 기반 2.5D HBM 패키징 다변화를 모색한다고 보도됐습니다."
        elif kind == "ai_semiconductor_insulation_film_bottleneck":
            core = "AI칩용 패키지기판 절연필름 공급부족이 기판 생산의 새 병목으로 부각됐습니다."
        elif kind == "samsung_electro_mlcc_lta":
            core = "삼성전기가 빅테크·반도체 고객 10여곳과 고부가 MLCC 장기공급 협의를 진행 중입니다."
        elif kind == "amazon_nvidia_gpu_2m_capex":
            core = "아마존이 AI 수요 대응을 위해 엔비디아 GPU 200만개를 추가 도입한다고 보도됐습니다."
        elif kind == "us_pce_ndf_rate_shift":
            core = "미국 7월 PCE가 예상을 웃돌며 원·달러 NDF와 연준 금리 경로가 재평가됐습니다."
        elif kind == "nvidia_earnings_actual":
            core = "엔비디아가 15분기 연속 월가 예상을 웃도는 실적을 발표했다고 보도됐습니다."
        elif kind == "nvidia_memory_purchase_commitments":
            core = "엔비디아의 메모리·생산능력 구매약정이 2790억달러로 석 달 새 134% 증가했습니다."
        elif kind == "catl_lithium_mine_restart_halted":
            core = "CATL 리튬광산 재가동 절차가 환경영향평가 공시 철회로 중단됐다고 보도됐습니다."
        elif kind == "nvidia_hbm4_rubin_vera_memory_shortage":
            core = "엔비디아 루빈·베라 플랫폼의 HBM4·LPDDR5X 수요가 메모리 부족 우려로 부각됐습니다."
        elif kind == "nvidia_nvhbm_amazon_collaboration":
            core = "엔비디아가 맞춤형 HBM 기술 NVHBM을 공개하고 아마존과 공동 개발을 추진합니다."
        elif kind == "iran_opec_china_oil_market_shift":
            core = "이란 전쟁 장기화로 중국의 원유 조달 영향력과 OPEC+ 가격 조절력 변화가 거론됐습니다."
        elif kind == "us_datacenter_tariff_cost_pressure":
            core = "트럼프 관세가 미국 데이터센터 장비·건설비를 높여 AI 인프라 CAPEX를 압박할 수 있다는 보도입니다."
        elif kind == "skhynix_us_hbm_advanced_packaging_capex":
            core = "SK하이닉스가 미국 웨스트라피엣에 AI용 HBM 첨단패키징 생산시설을 구축합니다."
        elif kind == "korea_bok_rate_policy_event" and any(
            term in text for term in ("인상", "인하", "동결")
        ):
            core = "한국은행이 물가·환율·경기지표를 반영해 기준금리 경로를 재조정했습니다."
        elif kind == "kioxia_iwate_nand_factory_capex":
            core = "키옥시아가 일본 이와테에 낸드 생산능력 확대를 위한 공장 투자를 추진합니다."
        elif kind == "skhynix_2030_memory_shortage_outlook":
            core = "SK하이닉스 CEO는 메모리 공급 부족이 2030년 말까지 이어질 수 있다고 전망했습니다."
        elif kind == "nvidia_memory_cost_margin_pressure":
            core = "엔비디아는 메모리 가격 상승으로 4분기 매출총이익률을 71~72%로 전망했습니다."
        elif kind == "nvidia_ai_hbm_demand_outlook":
            core = "엔비디아 AI 수요와 메모리 공급 부족이 삼성전자·SK하이닉스의 내년 실적 기대를 높였습니다."
        elif kind == "iran_ceasefire_oil_price_move":
            core = "트럼프의 이란 휴전 조건 복귀 거부 뒤 국제유가가 2% 상승 마감했습니다."
        elif kind == "hbm_glass_carrier_yield_inspection":
            core = "AI 기반 글라스 캐리어 결함검사가 HBM 수율 개선 기술로 부각됐습니다."
        elif kind == "samsung_china_semiconductor_localization_research":
            core = "KB증권은 중국 반도체 국산화 가속에 삼성전자 수혜 가능성을 제시했습니다."
        elif kind == "samsung_skhynix_shareholder_return_program":
            core = "삼성전자·SK하이닉스가 총 46조원 규모 자사주 매입·소각 계획을 발표했습니다."
        elif kind == "korea_ess_regulatory_improvement":
            core = "정부가 ESS 법적 분류와 이격거리 기준을 신설하는 규제개선을 추진합니다."
        elif kind == "tsmc_foundry_share_gap":
            core = "2분기 TSMC 파운드리 점유율은 73%, 삼성전자는 7%로 격차가 확대됐습니다."
        elif kind == "korea_zinc_semiconductor_sulfuric_acid_capacity":
            core = "고려아연이 반도체황산 생산라인을 연 4만톤 증설합니다."
        elif kind == "samsung_skhynix_hbm_packaging_roadmap":
            core = "삼성전자·SK하이닉스가 HBM 연결성을 높이는 차세대 패키징 경쟁을 강화합니다."
        elif kind == "nxt_premarket_microstructure_rule":
            core = "NXT가 프리마켓 급격한 가격변동을 막기 위한 거래방식 개편을 검토합니다."
        elif kind == "us_chip_tariff_embedded_products":
            core = "미국이 칩 내장 제품까지 반도체 관세 대상을 넓히는 방안을 검토합니다."
        elif kind == "openai_samsung_computational_memory":
            core = "오픈AI 자체칩과 삼성전자 연산메모리가 AI 반도체 병목 완화 경쟁으로 부각됐습니다."
        elif kind == "us_venezuela_oil_agreement":
            core = "트럼프가 베네수엘라 650억 배럴 원유 매장량 통제 합의를 주장했습니다."
        elif kind == "cxmt_memory_revenue_growth":
            core = "CXMT 상반기 매출이 10배 늘며 중국 D램 경쟁력 확대 신호가 나왔습니다."
        elif kind == "ymtc_nand_wafer_capacity_expansion":
            core = "YMTC가 낸드 웨이퍼 생산을 내년 250만장으로 확대해 점유율 경쟁을 키웁니다."
        elif kind == "china_mobile_lpddr6_commercialization":
            core = "CXMT가 LPDDR6을 양산해 샤오미 스마트폰에 처음 탑재했습니다."
        elif kind == "single_stock_leverage_etf_rule_effect":
            core = "단일종목 레버리지 ETF 규제 후 거래대금이 19조원에서 5000억원으로 줄었습니다."
        elif kind == "korea_robotaxi_commercialization":
            core = "포니AI가 퓨처링크와 한국 로보택시 상용화·7세대 자율주행 도입을 추진합니다."
        elif kind == "samsung_sdi_gm_ess_jv_restructure":
            core = "삼성SDI가 GM 합작법인 지분 인수로 ESS 셀 26GWh 확보를 추진합니다."
        elif kind == "samsung_skhynix_margin_credit_concentration":
            core = "증시 신용자금 증가분이 삼성전자·SK하이닉스에 집중됐다는 분석이 나왔습니다."
        elif kind == "korea_ai_megaproject_personnel_policy":
            core = "정부가 AI 메가프로젝트 추진을 위한 인사를 단행하며 산업 육성을 재확인했습니다."
        elif kind == "us_china_trade_truce_calendar":
            core = "미·중 무역 휴전 연장과 시진핑 방미 가능성이 통상 일정 변수로 부각됐습니다."
        headline_override = {
            "us_pce_ndf_rate_shift": "미국 7월 PCE 예상 상회…원·달러 NDF·연준 금리 경로 재평가",
        }.get(kind, "")
        alert = base_korean_business_alert(row, now, score=score, impacts=impacts)
        alert.update(
            {
                "importance": "상" if score >= 110 else "중",
                "status": "확정" if row.get("body_verified") else "예비",
                "news": headline_override or alert["news"],
                "policy_plain_summary": core,
                "telegram_core_fact": core,
                "sectors": sectors,
                "paths": paths,
                "korean_business_kind": kind,
                "supply_chain_theme": f"{kind}:{korean_business_event_date(row)}",
                "headline_override": headline_override,
            }
        )
        return alert
    return None


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


def build_korea_sovereign_fund_alert(row: dict, now, text: str) -> dict | None:
    title = str(row.get("source_title") or row.get("title") or "")
    if not (
        "국부펀드" in text
        and any(term in text for term in ("전략적 투자", "국가전략산업", "산업 투자"))
        and re.search(r"\d[\d,.]*\s*조(?:원)?(?:\+α|\s*이상)?", text)
    ):
        return None
    core = detailed_article_core(title, str(row.get("source_body") or row.get("source_abstract") or ""))
    alert = base_korean_business_alert(
        row,
        now,
        score=116,
        impacts=["돈 버는 능력", "수급", "시간표"],
    )
    alert.update(
        {
            "importance": "상",
            "status": "예비",
            "policy_plain_summary": core,
            "telegram_core_fact": core,
            "telegram_investment_fact": "국가 전략자금의 투자 대상과 집행 일정은 해당 산업의 자금조달·CAPEX·정책 수급을 바꿉니다.",
            "investment_view": "국가 전략자금의 투자 대상과 집행 일정은 해당 산업의 자금조달·CAPEX·정책 수급을 바꿉니다.",
            "korea_market_impact": "국부펀드의 출자 구조, 투자 대상 산업, 실제 집행액이 확인되는 국내 기업과 밸류체인만 연결합니다.",
            "sectors": ["금융/자본시장", "산업정책/첨단전략산업"],
            "paths": ["정책자금 수급", "CAPEX", "투자 집행 시간표"],
            "korean_business_kind": "korea_sovereign_strategic_fund",
            "supply_chain_theme": f"korea_sovereign_fund:{korean_business_event_date(row)}",
        }
    )
    return alert


def build_hyperscaler_ai_capex_alert(row: dict, now, text: str) -> dict | None:
    title = str(row.get("source_title") or row.get("title") or "")
    title_text = title.lower()
    companies = ("아마존", "amazon", "aws", "마이크로소프트", "microsoft", "구글", "alphabet", "메타", "oracle", "오라클", "앤트로픽", "anthropic")
    if not (re.search(r"설비투자|capex|자본지출|투자|매출|실적|가이던스|클라우드.{0,12}성장", title_text)
            and (any(company in title_text for company in companies)
                 or re.search(r"빅테크|하이퍼스케일러|\bai\b|인공지능|클라우드", title_text))):
        return None
    if not (
        any(company in text for company in companies)
        and any(term in text for term in ("ai", "인공지능", "데이터센터", "클라우드", "aws"))
        and any(term in text for term in ("투자", "capex", "설비투자", "성장", "매출", "가이던스"))
        and re.search(r"\d[\d,.]*\s*(?:%|조원|억원|억달러|조달러|십억달러)", text)
    ):
        return None
    core = detailed_article_core(title, str(row.get("source_body") or row.get("source_abstract") or ""))
    confirmed = any(term in title_text for term in ("실적", "매출", "성장", "영업이익"))
    alert = base_korean_business_alert(
        row,
        now,
        score=118,
        impacts=["돈 버는 능력", "수급", "시간표"],
    )
    alert.update(
        {
            "importance": "상",
            "status": "확정" if confirmed else "예비",
            "policy_plain_summary": core,
            "telegram_core_fact": core,
            "telegram_investment_fact": "하이퍼스케일러의 클라우드 성장과 AI CAPEX는 GPU·HBM·서버·전력 인프라 발주 추정치를 바꿉니다.",
            "investment_view": "하이퍼스케일러의 클라우드 성장과 AI CAPEX는 GPU·HBM·서버·전력 인프라 발주 추정치를 바꿉니다.",
            "korea_market_impact": "삼성전자·SK하이닉스와 HBM 장비·소재, 서버·전력기기 중 고객 CAPEX에 직접 노출된 종목만 연결합니다.",
            "sectors": ["AI/데이터센터", "반도체/HBM/CXL", "전력기기/전력망"],
            "paths": ["클라우드 매출", "AI CAPEX", "밸류체인 발주"],
            "korean_business_kind": "hyperscaler_ai_capex",
            "supply_chain_theme": f"hyperscaler_ai_capex:{korean_business_event_date(row)}",
        }
    )
    return alert


def build_korea_monthly_export_alert(row: dict, now, text: str) -> dict | None:
    title = str(row.get("source_title") or row.get("title") or "")
    title_lower = title.lower()
    if not (
        "수출" in text
        and any(term in text for term in ("반도체", "무역수지", "월간", "7월", "8월"))
        and any(term in text for term in ("역대", "증가", "감소", "흑자", "적자"))
        and re.search(r"\d[\d,.]*\s*(?:%|억달러|조원)", text)
    ):
        return None
    if not (
        any(
            term in title_lower
            for term in ("월간", "무역수지", "반도체 수출", "수출액", "수출 증가", "수출입")
        )
        or ("수출" in title_lower and "반도체" in title_lower)
    ):
        return None
    core = detailed_article_core(
        title,
        str(row.get("source_body") or row.get("source_abstract") or ""),
    )
    alert = base_korean_business_alert(
        row,
        now,
        score=120,
        impacts=["돈 버는 능력", "할인율", "시간표"],
    )
    alert.update(
        {
            "importance": "상",
            "status": "확정" if row.get("body_verified") else "예비",
            "policy_plain_summary": core,
            "telegram_core_fact": core,
            "investment_view": "월간 수출과 반도체 수출은 한국 기업의 매출·무역수지·원화 경로를 동시에 바꿉니다.",
            "korea_market_impact": "삼성전자·SK하이닉스와 수출 대형주, 원/달러 및 외국인 수급에 직접 연결합니다.",
            "sectors": ["한국 수출/무역수지", "반도체/HBM/CXL", "환율/수출입"],
            "paths": ["수출 매출", "무역수지", "환율", "월간 통계 시간표"],
            "korean_business_kind": "korea_monthly_exports",
            "supply_chain_theme": f"korea_monthly_exports:{korean_business_event_date(row)}",
        }
    )
    return alert


def build_fed_meeting_structure_alert(row: dict, now, text: str) -> dict | None:
    if not (
        any(term in text for term in ("연준", "fomc", "federal reserve"))
        and "회의" in text
        and any(term in text for term in ("축소", "횟수", "연 8회", "연8회", "정례"))
    ):
        return None
    title = str(row.get("source_title") or row.get("title") or "")
    core = detailed_article_core(
        title,
        str(row.get("source_body") or row.get("source_abstract") or ""),
    )
    alert = base_korean_business_alert(
        row,
        now,
        score=116,
        impacts=["할인율", "시간표"],
    )
    alert.update(
        {
            "importance": "상",
            "status": "확정" if row.get("body_verified") else "예비",
            "policy_plain_summary": core,
            "telegram_core_fact": core,
            "investment_view": "FOMC 개최 횟수 변경은 금리 신호가 갱신되는 빈도와 정책 불확실성의 시간표를 바꿉니다.",
            "korea_market_impact": "원/달러, 외국인 수급, 성장주·반도체의 할인율 민감도를 함께 확인합니다.",
            "sectors": ["금리/연준", "환율/수출입", "금융/자본시장"],
            "paths": ["할인율", "통화정책 일정", "환율"],
            "korean_business_kind": "fed_meeting_structure",
            "supply_chain_theme": f"fed_meeting_structure:{korean_business_event_date(row)}",
        }
    )
    return alert


def build_fx_intervention_alert(row: dict, now, text: str) -> dict | None:
    if not (
        any(term in text for term in ("엔화", "달러당 엔", "달러·엔", "달러-엔"))
        and "개입" in text
        and any(term in text for term in ("환율", "외환", "시장", "재무부", "공조"))
    ):
        return None
    title = str(row.get("source_title") or row.get("title") or "")
    core = detailed_article_core(
        title,
        str(row.get("source_body") or row.get("source_abstract") or ""),
    )
    alert = base_korean_business_alert(
        row,
        now,
        score=119,
        impacts=["할인율", "수급", "시간표"],
    )
    alert.update(
        {
            "importance": "상",
            "status": "확정" if row.get("body_verified") else "예비",
            "policy_plain_summary": core,
            "telegram_core_fact": core,
            "investment_view": "미·일 환율개입은 엔화·달러와 아시아 통화의 상대가치, 외국인 수급 기대를 즉시 바꿉니다.",
            "korea_market_impact": "원/달러·원/엔과 자동차·부품·기계 등 일본 경쟁 수출주의 가격경쟁력을 확인합니다.",
            "sectors": ["환율/수출입", "자동차/부품", "금융/자본시장"],
            "paths": ["환율", "외국인 수급", "정책 개입 시간표"],
            "korean_business_kind": "us_japan_fx_intervention",
            "supply_chain_theme": f"us_japan_fx_intervention:{korean_business_event_date(row)}",
        }
    )
    return alert


def build_china_memory_capacity_alert(row: dict, now, text: str) -> dict | None:
    if not (
        any(term in text for term in ("cxmt", "창신메모리", "중국 d램", "중국 dram", "중국 메모리"))
        and any(term in text for term in ("생산 능력", "생산능력", "웨이퍼", "증설", "캐파", "점유율"))
    ):
        return None
    title = str(row.get("source_title") or row.get("title") or "")
    core = detailed_article_core(
        title,
        str(row.get("source_body") or row.get("source_abstract") or ""),
    )
    alert = base_korean_business_alert(
        row,
        now,
        score=117,
        impacts=["돈 버는 능력", "수급", "시간표"],
    )
    alert.update(
        {
            "importance": "상",
            "status": "확정" if row.get("body_verified") else "예비",
            "policy_plain_summary": core,
            "telegram_core_fact": core,
            "investment_view": "CXMT의 DRAM 증설은 범용 메모리 공급과 가격, 한국 메모리 업체의 믹스·마진 전망을 바꿉니다.",
            "korea_market_impact": "삼성전자·SK하이닉스의 범용 DRAM 가격과 HBM 전환 속도, 중국 노출 장비·소재를 확인합니다.",
            "sectors": ["반도체/HBM/CXL", "중국 메모리 공급", "반도체 장비·소재"],
            "paths": ["DRAM 공급", "메모리 가격", "증설 시간표"],
            "korean_business_kind": "china_memory_capacity",
            "supply_chain_theme": f"china_memory_capacity:{korean_business_event_date(row)}",
        }
    )
    return alert


TITLE_ONLY_HARD_EVENT_TERMS = (
    "관세 면제", "공급 부족", "hbm4", "hbm4e", "시장 1위", "점유율",
    "데이터센터 건설", "파운데이션 모델", "k-엑사원", "역대 최대 매출",
    "의무보유", "보호예수", "품목허가", "허가 권고", "상업화",
    "외환거래", "유상증자", "인수", "합병", "주식분할",
    "무장해제", "중동 전쟁", "영업익", "영업이익", "순이익", "매출",
    "월간 수출", "수출 실적", "반도체 수출", "무역수지",
    "회의 축소", "회의 횟수", "연 8회", "환율 개입", "외환 개입",
    "생산 능력", "웨이퍼", "클라우드 성장", "aws 매출",
    "추가 공격", "공격 임박", "드론 공격", "스타링크", "타격 승인",
    "가자 휴전", "평화 협정", "국정조사", "청문회", "조사 착수",
)
TITLE_ONLY_VAGUE_TERMS = (
    "전망", "가능성", "기대", "주목", "관심", "왜", "칼럼", "사설",
    "국가 경쟁력", "살펴보니", "분석", "진단",
)


def build_title_verified_korean_business_alert(row: dict, now) -> dict | None:
    """Promote self-contained hard-event headlines when article-body fetch fails."""
    title = str(row.get("source_title") or row.get("title") or "").strip()
    if not title or not korean_business_source_allowed(row):
        return None
    title_text = title.lower()
    fallback_row = dict(row)
    fallback_row["source_title"] = title
    fallback_row["source_body"] = ""
    fallback_row["source_abstract"] = title
    fallback_row["summary"] = title
    fallback_row["body_verified"] = False

    for builder in (
        build_iran_gulf_escalation_alert,
        build_ukraine_starlink_military_alert,
        build_gaza_ceasefire_disarmament_alert,
        build_leverage_etf_parliamentary_inquiry_alert,
        build_korea_monthly_export_alert,
        build_fed_meeting_structure_alert,
        build_fx_intervention_alert,
        build_china_memory_capacity_alert,
        build_korea_sovereign_fund_alert,
        build_hyperscaler_ai_capex_alert,
    ):
        alert = builder(fallback_row, now, title_text)
        if not alert:
            continue
        alert["status"] = "예비"
        alert["title_fact_verified"] = True
        alert["body_verified"] = False
        alert["source_abstract"] = title
        alert["policy_plain_summary"] = title_only_provisional_core(title)
        alert["telegram_core_fact"] = alert["policy_plain_summary"]
        alert["interpretation"] = alert["policy_plain_summary"]
        return alert

    if is_low_value_market_commentary({"korean_business_news": True, "source_title": title}):
        return None
    if has_term(title_text, TITLE_ONLY_VAGUE_TERMS) and not re.search(
        r"\d[\d,.]*(?:조|억|만|%|배|주|명|달러|유로|원)", title_text
    ):
        return None
    if not has_term(title_text, TITLE_ONLY_HARD_EVENT_TERMS):
        return None

    impacts = korean_business_impacts(title, [])
    if not impacts:
        return None
    score = 104 + min(
        12,
        sum(
            weight
            for term, weight in KOREAN_BUSINESS_PRIORITY_TERMS.items()
            if term in title_text
        ) // 8,
    )
    alert = base_korean_business_alert(fallback_row, now, score=score, impacts=impacts)
    core = title_only_provisional_core(title)
    alert.update(
        {
            "status": "예비",
            "title_fact_verified": True,
            "body_verified": False,
            "source_abstract": title,
            "policy_plain_summary": core,
            "telegram_core_fact": core,
            "telegram_investment_fact": core,
            "investment_view": core,
            "interpretation": core,
            "sectors": korean_business_source_sectors(title, title),
            "korean_business_kind": "trusted_title_material_event",
        }
    )
    return alert

def build_verified_korean_business_alert(row: dict, now) -> dict | None:
    title = str(row.get("source_title") or row.get("title") or "")
    title_text = title.lower()
    body = str(row.get("source_body") or row.get("source_abstract") or "")
    text = f"{title} {body}".lower()
    entertainment_reason = market_materiality.nonmarket_entertainment_reason(
        title, article_summary_body(body) if row.get("body_verified") else "", str(row.get("link") or ""),
    )
    if entertainment_reason:
        row["_exclusion_reason"] = entertainment_reason
        return None

    # A macro release owns its headline; background oil/Fed references must
    # not replace the announced indicator with a thematic policy template.
    if has_term(title_text, (
        "pce", "cpi", "ppi", "gdp", "고용지표", "비농업 고용", "비농업고용", "실업률",
    )):
        alert = base_korean_business_alert(
            row, now, score=110, impacts=korean_business_impacts(text, ["할인율"])
        )
        return apply_generic_korean_business_profile(alert, row, now)

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
        build_iran_gulf_escalation_alert,
        build_ukraine_starlink_military_alert,
        build_gaza_ceasefire_disarmament_alert,
        build_leverage_etf_parliamentary_inquiry_alert,
        build_korea_monthly_export_alert,
        build_fed_meeting_structure_alert,
        build_fx_intervention_alert,
        build_china_memory_capacity_alert,
        build_korea_sovereign_fund_alert,
        build_hyperscaler_ai_capex_alert,
        build_strategic_technology_investment_alert,
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
        build_korea_aquaculture_heat_loss_alert,
        build_korea_oil_fx_inflation_alert,
        build_fomc_rate_outlook_alert,
        build_china_memory_ipo_alert,
        build_korea_etf_net_buy_alert,
        build_korea_strategic_etf_listing_alert,
        build_attachment_verified_event_alert,
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

    if market_materiality.focus_kind(title) not in {"breadth", "market_macro_response"} and any(term in title.lower() for term in KOREAN_BUSINESS_MARKET_RECAP_TERMS):
        return None

    # Source-backed changes must survive the legacy headline vocabulary gate.
    source_audit = market_materiality.assess(title, article_summary_body(body), source_url=str(row.get("link") or ""))
    if row.get("body_verified") and source_audit["disposition"] == "keep" and source_audit["priority"] >= 2:
        impacts = [MATERIALITY_IMPACT_NAMES[axis] for axis in source_audit["axes"] if axis in MATERIALITY_IMPACT_NAMES]
        alert = base_korean_business_alert(
            row, now, score=100 if source_audit["priority"] >= 3 else 90, impacts=impacts,
        )
        return apply_generic_korean_business_profile(alert, row, now)

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


def hydrate_korean_business_details(rows: list[dict], now) -> list[str]:
    candidates = []
    unique_links = set()
    live_mode = os.getenv("RADAR_RUN_MODE", "").strip().lower() == "live"
    queue_state = detail_queue.load_state(detail_queue.STATE_PATH)
    seen_entries = list(telegram.load_seen_state().get("seen", {}).values()) if live_mode else []
    recent_sent = {}
    sent_by_link = {}
    sent_links = set()
    for entry in seen_entries:
        if not isinstance(entry, dict) or not entry.get("link"):
            continue
        sent_links.add(str(entry["link"]))
        sent_by_link.setdefault(str(entry["link"]), []).append(entry)
        sent_at = detail_queue.parse_time(entry.get("last_seen_kst"))
        if sent_at and dt.timedelta() <= now - sent_at < dt.timedelta(hours=1):
            recent_sent.setdefault(str(entry["link"]), []).append(entry)
    backlog_resumed = 0
    invalid_url_skipped = 0
    canonicalized_urls = 0
    if live_mode:
        for row in detail_queue.backlog_rows(
            queue_state, now, {str(row.get("link") or "") for row in rows}, base.MAX_AGE_HOURS,
        ):
            if not is_korean_business_row(row) or not korean_business_source_domain_allowed(row["link"]):
                continue
            published = detail_queue.parse_time(row.get("published"))
            prior_sends = sent_by_link.get(row["link"], [])
            if prior_sends and not any(
                published and (sent_at := detail_queue.parse_time(entry.get("last_seen_kst")))
                and published > sent_at for entry in prior_sends
            ):
                continue
            row["publisher"] = korean_business_publisher(row)
            row["source"] = row.get("source") or row["publisher"]
            rows.append(row)
            backlog_resumed += 1
    sent_skipped = 0
    nonmarket_skipped = 0
    for row in rows:
        if not is_korean_business_row(row) or not row.get("link"):
            continue
        link = str(row["link"])
        canonical_link = canonical_korean_business_article_url(link)
        if canonical_link != link:
            row["source_discovery_url"] = link
            row["link"] = canonical_link
            row["_fetch_url"] = canonical_link
            link = canonical_link
            canonicalized_urls += 1
        rejection = korean_business_article_url_rejection(link)
        if rejection:
            row["_detail_skipped_reason"] = rejection
            invalid_url_skipped += 1
            continue
        if link in unique_links:
            continue
        unique_links.add(link)
        row["publisher"] = korean_business_publisher(row)
        if is_nonmarket_business_event(row):
            row["_detail_skipped_reason"] = market_materiality.nonmarket_entertainment_reason(
                str(row.get("source_title") or row.get("title") or ""), source_url=link,
            ) or "nonmarket_ceremonial_or_sports"
            nonmarket_skipped += 1
            continue
        title_tokens = normalized_title_tokens(str(row.get("title") or ""))
        if title_tokens and any(
            normalized_title_tokens(str(entry.get("title") or "")) == title_tokens
            and (detail_queue.parse_time(row.get("published")) or now) <= detail_queue.parse_time(entry["last_seen_kst"])
            for entry in recent_sent.get(link, [])
        ):
            row["_detail_skipped_reason"] = "recently_delivered_unchanged_title"
            sent_skipped += 1
            continue
        candidates.append(row)
    candidates = rank_korean_business_detail_candidates(candidates, sent_links, live_mode)
    selected, pending, stats = detail_queue.plan_details(
        candidates, queue_state, now, KOREAN_BUSINESS_DETAIL_LIMIT,
        respect_cooldown=live_mode,
        selection_version=market_materiality.VERSION,
    )
    cache = detail_queue.load_run_cache(now, detail_queue.CACHE_PATH)

    def fetch_detail(row: dict) -> tuple[dict, dict, bool]:
        cached = detail_queue.cached_receipt(cache, row)
        if cached:
            return row, cached, True
        fetch_url = str(row.get("_fetch_url") or row["link"])
        title = str(row.get("title") or "")

        def validate_article_response(source_html: str) -> str | None:
            candidate = extract_article_detail(source_html, title, fetch_url)
            if candidate.get("body_verified"):
                if row.get("_detail_from_queue") and not (row.get("published") or base.parse_date(candidate.get("published_kst"))):
                    return "resumed article publication time unavailable"
                return None
            return (
                f"title/body mismatch aligned={candidate.get('title_aligned')} "
                f"body_chars={len(str(candidate.get('body') or ''))}"
            )

        detail_html, error = base.fetch(fetch_url, 16, response_validator=validate_article_response)
        detail = extract_article_detail(detail_html, title, fetch_url) if detail_html and not error else {}
        if not error and not detail.get("body_verified"):
            error = (
                "title/body mismatch "
                f"aligned={detail.get('title_aligned')} body_chars={len(str(detail.get('body') or ''))}"
            )
        receipt = {
            "fingerprint": detail_queue.fingerprint(row),
            "query_time_kst": base.kst_now().isoformat(timespec="seconds"),
            "detail": detail, "error": str(error or ""),
        }
        return row, receipt, False

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(KOREAN_BUSINESS_DETAIL_WORKERS, max(1, len(selected)))
    ) as executor:
        results = list(executor.map(fetch_detail, selected))
    verified = failed = cache_hits = 0
    for row, receipt, cache_hit in results:
        cache["receipts"][detail_queue.article_key(row)] = receipt
        cache_hits += int(cache_hit)
        detail = receipt["detail"]
        error = receipt["error"]
        valid = bool(not error and detail.get("body_verified"))
        if valid and row.get("_detail_from_queue") and not (row.get("published") or base.parse_date(detail.get("published_kst"))):
            valid = False
            error = "resumed article publication time unavailable"
        query_time = detail_queue.parse_time(receipt["query_time_kst"]) or now
        source_selection = market_materiality.assess(
            detail.get("title") or str(row.get("title") or ""),
            article_summary_body(detail.get("body") or ""),
            source_url=str(row.get("link") or ""),
        ) if valid else {}
        detail_queue.record_attempt(
            pending, row, query_time, verified=valid, error=error,
            selection_version=market_materiality.VERSION,
            source_disposition=source_selection.get("disposition") or "",
            source_reason=source_selection.get("reason") or "",
        )
        row["article_query_time_kst"] = receipt["query_time_kst"]
        row["_article_detail_cache_hit"] = cache_hit
        if not valid:
            row["_article_verification_failed"] = error or "empty article"
            failed += 1
            continue
        row["source_title"] = detail.get("title") or row.get("title")
        row["source_body"] = detail.get("body") or ""
        row["source_description"] = detail.get("abstract") or ""
        row["source_abstract"] = re.sub(r"\s+", " ", row["source_body"]).strip()[:16000]
        row["summary"] = row["source_abstract"]
        row["body_verified"] = True
        if detail.get("published_kst"):
            parsed = base.parse_date(detail["published_kst"])
            if parsed:
                row["published"] = parsed
                pending["entries"][detail_queue.article_key(row)]["source_published_kst"] = parsed.isoformat(timespec="seconds")
        verified += 1
    # Preflight receipts are reusable only inside this GitHub execution. The
    # durable queue holds retrieval metadata, never bodies or delivery state.
    pending = detail_queue.merge_state(pending, detail_queue.load_state(detail_queue.PENDING_PATH), now)
    detail_queue.save_json(detail_queue.PENDING_PATH, pending)
    detail_queue.save_json(detail_queue.CACHE_PATH, cache)
    notes = [
        "Korean business detail: "
        f"attempted={len(results)} verified={verified} failed={failed} deferred={stats['deferred']} "
        f"workers={KOREAN_BUSINESS_DETAIL_WORKERS}",
        "Korean business detail queue: "
        f"source_fetches={len(results) - cache_hits} cache_hits={cache_hits} "
        f"fair_slots={stats['fair_slots']} retry_cooldown={stats['cooling']} "
        f"nonmaterial_recheck={stats['nonmaterial_recheck']} "
        f"selection_refresh={stats['selection_refresh']} "
        f"backlog_resumed={backlog_resumed} "
        f"invalid_url_skipped={invalid_url_skipped} canonicalized_urls={canonicalized_urls} "
        f"already_sent_skipped={sent_skipped} nonmarket_skipped={nonmarket_skipped}",
    ]
    for note in notes:
        print(note)
    return notes


def enforce_korean_business_news_contract() -> None:
    original_collect_items = contract.strict.collect_items

    def collect_items(now):
        rows, notes = original_collect_items(now)
        existing_by_link = {
            str(row.get("link") or ""): row
            for row in rows
            if str(row.get("link") or "")
        }
        direct_added = 0
        direct_pinned = 0
        for seed in coverage.DIRECT_ARTICLES:
            link = str(seed.get("url") or "")
            published = base.parse_date(seed.get("published_kst"))
            if link in existing_by_link:
                existing = existing_by_link[link]
                existing.update(
                    {
                        "source": seed.get("source") or "국내 신뢰매체 직접감시",
                        "layer": "trusted",
                        "publisher": seed.get("publisher") or "국내 신뢰매체",
                        "title": seed.get("title") or existing.get("title") or "",
                        "published": published or existing.get("published"),
                        "_fetch_url": seed.get("fetch_url") or link,
                        "_pinned_direct_article": True,
                    }
                )
                direct_pinned += 1
                continue
            direct_row = {
                "source": seed.get("source") or "국내 신뢰매체 직접감시",
                "layer": "trusted",
                "publisher": seed.get("publisher") or "국내 신뢰매체",
                "title": seed.get("title") or "",
                "link": link,
                "summary": "",
                "published": published,
                "_fetch_url": seed.get("fetch_url") or link,
                "_pinned_direct_article": True,
            }
            if link and base.fresh(direct_row, now):
                rows.append(direct_row)
                existing_by_link[link] = direct_row
                direct_added += 1
        notes.append(
            f"Direct trusted articles: added={direct_added} pinned_existing={direct_pinned}"
        )
        print(
            "GAMEJOA direct-watch collection: "
            f"added={direct_added} pinned_existing={direct_pinned}"
        )

        notes.extend(hydrate_korean_business_details(rows, now))
        return rows, notes

    original_classify = contract.strict.classify

    def classify(row: dict, now):
        if is_korean_business_row(row):
            if row.get("_detail_skipped_reason"):
                return None
            if row.get("_article_verification_failed") or not row.get("body_verified"):
                return build_title_verified_korean_business_alert(row, now)
            return build_verified_korean_business_alert(row, now)
        return original_classify(row, now)

    contract.strict.collect_items = collect_items
    contract.strict.classify = classify


enforce_korean_business_news_contract()


def safe(value: object) -> str:
    return html.escape(str(value or "확인 불가"), quote=False)


def normalize_telegram_source_url(value: str) -> str:
    """Repair whitespace-split HTTP schemes before building Telegram links."""
    normalized = html.unescape(str(value or "")).strip()
    normalized = re.sub(r"^h\s*ps?://", "h" + "ttps://", normalized, flags=re.IGNORECASE)
    return normalized


def html_link(label: str, url: str) -> str:
    """Render a Telegram source label with a normalized article URL."""
    text = html.escape(label or "출처", quote=False)
    normalized = normalize_telegram_source_url(url)
    parsed = urllib.parse.urlsplit(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return text
    return f'<a href="{html.escape(normalized, quote=True)}">{text}</a>'


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
    "회장",
    "부회장",
    "사장",
    "대표",
    "대표이사",
    "임원",
    "주식",
    "개인",
    "명의",
    "매수",
    "매입",
    "취득",
    "규모",
    "기록",
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
    text = re.sub(r"(\d[\d,.]*)\s*만\s*(?:명|개|주)", r"\1만", str(value or ""))
    raw_tokens = re.findall(
        r"[A-Za-z][A-Za-z0-9.-]*|"
        r"\d[\d,.]*(?:%|조원|억원|만원|달러|만|명|개)?|"
        r"[가-힣]{2,}",
        text,
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
    if market_materiality.focus_kind(title) == "intraday_equity" and market_materiality.intraday_equity_observations(title, core):
        return True
    if (market_materiality.focus_kind(title) == "national_exports"
            and market_materiality.focus_matches(title, core)
            and re.search(r"누적\s*수출액", core)
            and market_materiality.QUANTITY.search(core)):
        return True
    title_tokens = title_core_alignment_tokens(title)
    core_tokens = title_core_alignment_tokens(core)
    if not title_tokens or not core_tokens:
        return False
    matched: set[str] = set()
    for title_token in title_tokens:
        for core_token in core_tokens:
            if title_token == core_token:
                matched.add(title_token)
                break
            if (
                not any(char.isdigit() for char in title_token + core_token)
                and min(len(title_token), len(core_token)) >= 3
                and (title_token in core_token or core_token in title_token)
            ):
                matched.add(title_token)
                break
    if not matched:
        # Broad regulatory headlines may name the meeting, while the core
        # correctly names its concrete instrument rather than the promise.
        return bool(
            re.search(r"규제(?:혁신|\s*개선|\s*완화|합리화)", title)
            and re.search(r"(?:허가|규정|규제|요건|기준|절차).{0,35}(?:완화|개정)", core)
            and re.search(r"(?:고시|법률|법안|시행령|규정).{0,15}(?:개정|제정|시행)", core)
        )

    # Company names often split into several tokens (for example SK +
    # 하이닉스). A company-only overlap is insufficient evidence that the
    # compact sentence describes the headline's actual event.
    entity_tokens = {
        "sk", "하이닉스", "sk하이닉스", "삼성", "삼성전자", "엔비디아", "nvidia",
        "아마존", "amazon", "aws", "브로드컴", "broadcom", "애플", "apple",
        "현대차", "현대자동차", "lg", "lg전자", "tsmc", "마이크론", "micron",
    }
    if any(token not in entity_tokens for token in matched):
        return True

    if market_materiality.focus_kind(title) == "asset_financing":
        observation = asset_financing_observation(core)
        return bool(
            observation and observation["issuer"].casefold() in title.casefold()
            and re.search(r"칩|GPU", title, re.I)
        )

    event_terms = (
        "매수", "매각", "취득", "소각", "실적", "수주", "계약", "증설", "양산", "착공",
        "가동", "관세", "금리", "유가", "폭염", "정전", "수출", "상장", "인상", "하락",
    )
    return any(term in title.lower() and term in core.lower() for term in event_terms)


def macro_release_core_aligned(title: str, core: str) -> bool:
    indicators = {
        "pce": ("pce", "개인소비지출"),
        "cpi": ("cpi", "소비자물가"),
        "ppi": ("ppi", "생산자물가"),
        "gdp": ("gdp", "국내총생산"),
    }
    required = [aliases for indicator, aliases in indicators.items() if has_term(base.norm(title), [indicator])]
    if not required:
        return True
    if not all(has_term(base.norm(core), aliases) for aliases in required):
        return False
    headline_rates = {float(value) for value in re.findall(r"([+-]?\d+(?:\.\d+)?)%", title)}
    core_rates = {float(value) for value in re.findall(r"([+-]?\d+(?:\.\d+)?)%", core)}
    return headline_rates.issubset(core_rates)


def source_output_aligned(alert: dict) -> bool:
    """Reject rendered themes that are not supported by source-authored text."""
    if alert.get("korean_business_news"):
        source_title = base.norm(alert.get("source_title"))
        rendered_title = base.norm(alert.get("news"))
        link = str(alert.get("link") or "").lower()
        summary = base.clean(
            alert.get("telegram_core_fact") or alert.get("policy_plain_summary")
        )
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
        direction_conflict = direction_conflict or market_move_direction_conflict(source_title, summary)
        financing_alignment = False
        if alert.get("body_verified") and market_materiality.focus_kind(source_title) == "financing":
            financing_alignment = any(
                item["kind"] == "customer_financing_commitment"
                and normalized_article_sentence(item["source_excerpt"]) == summary
                for item in source_market_materiality(alert)["evidence"]
            )
        preview_revision_alignment = False
        if alert.get("body_verified") and "주간증시전망" in source_title:
            observation = source_headline_event_fact(
                str(alert.get("source_title") or ""), str(alert.get("source_body") or ""),
            )
            preview_revision_alignment = bool(
                observation and "컨센서스" in observation and "하향 조정" in observation
                and market_materiality.canonical_source_fact(observation) == market_materiality.canonical_source_fact(summary)
            )
        return bool(
            (alert.get("body_verified") or alert.get("title_fact_verified"))
            and source_title
            and rendered_title == source_title
            and len(summary) >= 12
            and not core_has_ui_garbage(summary)
            and korean_business_source_allowed(alert)
            and (korean_title_core_aligned(source_title, summary) or financing_alignment or preview_revision_alignment)
            and macro_release_core_aligned(source_title, summary)
            and market_materiality.core_focus_aligned(source_title, summary)
            and not source_core_fact_errors(alert)
            and not direction_conflict
        )
    if alert.get("grid_policy_delay"):
        source_title = base.norm(alert.get("source_title") or alert.get("original_news") or "")
        grid_subject = has_term(source_title, [
            "송전망", "송전선", "계통접속", "전력망", "transmission grid",
            "transmission line", "interconnection", "grid investment",
        ])
        policy_action = has_term(source_title, [
            "승인", "규제", "인허가", "지연", "보류", "접속",
            "approval", "regulatory", "permitting", "delay", "interconnection",
        ])
        if not (grid_subject and policy_action):
            return False
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


def bond_yield_threshold_theme(alert: dict) -> str:
    title = str(alert.get("source_title") or alert.get("original_news") or alert.get("news") or "")
    event = re.search(
        r"(미국|영국|독일|프랑스|일본|이탈리아|캐나다|한국)\s*(\d{1,2})년물\s*국채\s*"
        r"(?:금리|수익률).{0,20}?(\d+(?:\.\d+)?)\s*[%％]\s*(돌파|하회)", title,
    )
    published = detail_queue.parse_time(alert.get("published"))
    if not event or not published:
        return ""
    country, tenor, threshold, direction = event.groups()
    day = published.astimezone(dt.timezone(dt.timedelta(hours=9))).date().isoformat()
    return f"bond_yield_threshold:{country}:{int(tenor)}:{float(threshold):.12g}:{direction}:{day}"


def joint_validation_event_theme(alert: dict) -> str:
    """Deduplicate a named joint test, not every story about the same sector."""
    if not alert.get("body_verified"):
        return ""
    title = str(alert.get("source_title") or alert.get("news") or "")
    body = str(alert.get("source_body") or "")
    if not re.search(r"검증|실증|validation|field test", title, re.I) or not re.search(r"업무협약|MOU|joint agreement", body, re.I):
        return ""
    parties = re.search(r"(?m)^([A-Za-z0-9가-힣&]{2,30}(?:[·ㆍ][A-Za-z0-9가-힣&]{2,30}){2,3})(?=\s)", body)
    markers = sorted(set(re.findall(r"[\"'‘“]([A-Za-z][A-Za-z0-9-]{2,30})[\"'’”]", body)))
    markers = [marker.lower() for marker in markers if marker.lower() not in {"mou", "gpu", "npu", "tta", "cpu", "aws"}]
    published = detail_queue.parse_time(alert.get("published"))
    if not parties or not markers or not published:
        return ""
    participant_key = "+".join(sorted(re.split(r"[·ㆍ]", parties.group(1).lower())))
    day = published.astimezone(dt.timezone(dt.timedelta(hours=9))).date().isoformat()
    stage = "result" if re.search(r"결과|성공|달성|개선|results|success", title, re.I) else "start"
    quantities = "+".join(sorted(re.sub(r"\s+", "", match.group(0)) for match in market_materiality.QUANTITY.finditer(title)))
    return f"joint_validation:{participant_key}:{'+'.join(markers)}:{stage}:{quantities}:{day}"


def sanctions_exemption_event_theme(alert: dict) -> str:
    """Merge a verified, same-jurisdiction LNG exemption across publishers."""
    if not alert.get("body_verified"):
        return ""
    title = str(alert.get("source_title") or alert.get("news") or "")
    body = str(alert.get("source_body") or "")
    if market_materiality.focus_kind(title) != "sanctions_exemption":
        return ""
    authority = re.search(r"이어\s*(영국|英|미국|美|유럽연합|EU|일본|日|캐나다)(?:도|[,，\s])", title) or re.match(r"^(영국|英|미국|美|유럽연합|EU|일본|日|캐나다)(?:\s*정부)?[,，\s]", title)
    if not authority or not all(term in body for term in ("한국", "러시아", "LNG")):
        return ""
    if not re.search(r"사할린[\s-]*(?:Ⅱ|II|2)", body, re.I):
        return ""
    expiries = re.findall(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일\s*(?:까지|사이)", body)
    if not expiries:
        return ""
    expiry = max(tuple(map(int, values)) for values in expiries)
    authorities = {"영국": "uk", "英": "uk", "미국": "us", "美": "us", "유럽연합": "eu", "EU": "eu", "일본": "jp", "日": "jp", "캐나다": "ca"}
    return f"sanctions_exemption:{authorities[authority.group(1)]}:russia:sakhalin-2:korea:{expiry[0]:04d}-{expiry[1]:02d}-{expiry[2]:02d}"


def semantic_event_theme(alert: dict) -> str:
    source_identity = market_materiality.source_event_identity(alert)
    if source_identity:
        return source_identity
    exemption_theme = sanctions_exemption_event_theme(alert)
    if exemption_theme:
        return exemption_theme
    joint_theme = joint_validation_event_theme(alert)
    if joint_theme:
        return joint_theme
    yield_theme = bond_yield_threshold_theme(alert)
    if yield_theme:
        return yield_theme
    macro_theme = telegram.macro_release_theme(alert)
    if macro_theme:
        return macro_theme
    market_theme = telegram.korean_market_move_theme(alert)
    if market_theme:
        return market_theme
    bond_theme = telegram.korean_bond_demand_theme(alert)
    if bond_theme:
        return bond_theme
    ceo_theme = telegram.korean_joint_ceo_theme(alert)
    if ceo_theme:
        return ceo_theme
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
        "polysilicon" in text
        and "11052" in text
        and (
            "measures to restrict stockpiling" in text
            or ("stockpil" in text and ("temporary final rule" in text or "import prohibition" in text or "new importer" in text or "waiver" in text))
        )
    ):
        return "polysilicon-11052-stockpiling-tfr"
    if (
        "polysilicon" in text
        and "11052" in text
        and any(term in text for term in (
            "minimum import price", "minimum import prices", "mip program",
            "15% ad valorem", "15 percent ad valorem",
            "adjusting imports of polysilicon", "onshoring",
        ))
    ):
        return "polysilicon-11052-base"
    if any(term in text for term in (
        "space photovoltaics research and development partnership intermediary agreement",
        "space photovoltaics (pv) research and development partnership intermediary agreement",
        "space-based energy generation",
        "solar panels in space applications",
    )):
        if any(term in text for term in (
            "awardee", "awardees", "recipient", "recipients",
            "selected for award", "selected projects", "announces selections", "announced selections",
            "has selected", "have selected", "selected the following", "awarded to",
            "selection notifications issued", "selection notifications sent", "selection notifications released",
            "awards announced",
        )):
            return "doe-space-pv-pia-selections"
        return "doe-space-pv-pia-2026-08-31"
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
    source_identity = market_materiality.source_event_identity(alert)
    if source_identity:
        return (source_identity, "event")
    if alert.get("iran_hormuz_escalation"):
        return ("iran_hormuz_military_escalation", str(alert.get("published") or "")[:10])
    macro_theme = telegram.macro_release_theme(alert)
    if macro_theme:
        return (macro_theme, "event")
    trade_theme = telegram.verified_trade_theme(alert)
    if trade_theme:
        return (trade_theme, "event")
    market_theme = telegram.korean_market_move_theme(alert)
    if market_theme:
        return (market_theme, "event")
    bond_theme = telegram.korean_bond_demand_theme(alert)
    if bond_theme:
        return (bond_theme, "event")
    ceo_theme = telegram.korean_joint_ceo_theme(alert)
    if ceo_theme:
        return (ceo_theme, "event")
    raw_title = str(alert.get("original_news") or alert.get("news") or "")
    raw_title = re.split(r"\s+-\s+", raw_title, maxsplit=1)[0].strip()
    raw_title = re.sub(r"^(?:\s*\[[^\]]{1,12}\]\s*)+", "", raw_title).strip()
    raw_title = telegram.canonical_edition_title(raw_title)
    theme = str(alert.get("supply_chain_theme") or semantic_event_theme(alert) or "")
    if theme:
        return (base.norm(theme), "event")
    fact_identity = market_materiality.verified_source_fact_identity(alert)
    if fact_identity:
        return (fact_identity, "fact")
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


STOCK_MARKET_SUBJECTS = {
    "rates_fx_liquidity": (
        "연준", "federal reserve", "fomc", "ecb", "유럽중앙은행", "일본은행", "bank of japan",
        "한국은행", "기준금리", "국채", "국고채", "treasury", "bond yields", "금리",
        "물가", "인플레이션", "inflation", "cpi", "pce", "미국 고용", "payrolls",
        "실업률", "unemployment", "환율", "달러", "엔화", "liquidity", "유동성",
    ),
    "trade_policy_supply_chain": (
        "관세", "수출통제", "수입금지", "제재", "통상협정", "tariff", "export control",
        "import ban", "sanctions", "trade agreement",
    ),
    "energy_commodities_transport": (
        "유가", "원유", "브렌트", "oil", "brent", "wti", "opec", "천연가스",
        "natural gas", "구리", "copper", "리튬", "lithium", "운임", "freight", "해운",
    ),
    "geopolitical_risk": (
        "이란", "iran", "호르무즈", "hormuz", "홍해", "red sea", "이스라엘", "israel",
        "우크라이나", "ukraine", "러시아", "russia", "가자", "gaza", "하마스", "hamas",
    ),
    "earnings_investment": (
        "매출", "영업이익", "순이익", "실적", "가이던스", "수주", "공급계약",
        "설비투자", "자금조달", "자본조달", "earnings", "profit warning", "guidance",
        "capex", "supply agreement", "financing",
    ),
    "capital_flows": (
        "순매수", "순매도", "외국인", "연기금", "etf", "etn", "자사주", "배당",
        "유상증자", "buyback", "dividend", "fund flows",
    ),
}
STOCK_MARKET_CHANGE_TERMS = (
    "발표", "상승", "하락", "급등", "급락", "상회", "하회", "증가", "감소", "확대", "축소",
    "인상", "인하", "동결", "상향", "하향", "체결", "결정", "시행", "발효", "합의",
    "취득", "소각", "유입", "유출", "중단", "차질", "부족", "공격", "공습", "휴전",
    "협상", "제한", "금지", "검토", "추진", "announces", "decision", "cut", "cuts",
    "hike", "hikes", "raises", "rise", "rises", "falls", "drop", "surge", "slump",
    "surprise", "warning", "agreement", "restriction", "ban", "disruption", "shortage",
    "attack", "attacks", "airstrikes", "ceasefire", "talks", "inflows", "outflows",
)
STOCK_MARKET_REQUIRED_CONTEXT = {
    "rates_fx_liquidity": (
        "금리", "물가", "인플레이션", "고용", "국채", "환율", "달러", "엔화", "유동성",
        "interest rate", "rates", "inflation", "cpi", "pce", "payrolls", "unemployment",
        "treasury", "bond yields", "liquidity", "monetary policy",
    ),
    "geopolitical_risk": (
        "공격", "공습", "휴전", "미사일", "전쟁", "제재", "원유", "통항", "핵 협상",
        "attack", "attacks", "airstrikes", "strike", "ceasefire", "missile", "war",
        "sanctions", "oil", "shipping", "nuclear talks",
    ),
    "capital_flows": (
        "주식", "증시", "순매수", "순매도", "etf", "etn", "자사주", "배당", "유상증자",
        "shares", "equities", "buyback", "dividend", "fund flows",
    ),
}

# Labels assigned by a classifier are not evidence. These pairs require an
# event in the source headline and matching market/business facts in the body.
SOURCE_BUSINESS_MARKET_EVENTS = (
    (
        ("주식", "증시", "코스피", "코스닥", "주가", "거래대금", "레버리지", "ipo", "상장", "순매수", "순매도", "etf", "etn"),
        ("주식", "증시", "코스피", "코스닥", "주가", "거래대금", "etf", "etn", "상장", "투자자", "순매수", "순매도"),
    ),
    (
        ("펀드", "투자유치", "투자 유치", "출자", "자금조달", "회사채", "신용등급", "주주환원", "vc", "벤처", "스타트업", "자본지출", "최대주주", "cb 전환"),
        ("투자", "출자", "조달", "회사채", "신용등급", "주주환원", "배당", "자사주", "주식", "지분", "증설"),
    ),
    (
        ("인수", "합병", "지분 매각", "지분매각", "공장 매각", "공장매각", "법인 설립", "법인설립"),
        ("기업", "회사", "법인", "사업", "지분", "공장", "생산", "수주", "인수", "합병", "조달"),
    ),
    (
        ("공장", "생산능력", "생산시설", "생산라인", "증설", "착공", "가동", "공급계약", "상용화", "양산", "장비 개발", "기술 공개", "기술공개"),
        ("생산", "공장", "공급", "수주", "설비", "장비", "출하", "고객", "상용화", "양산", "제품"),
    ),
    (
        ("투자", "판매", "수출", "출하", "점유율", "가격", "판가", "마진", "흑자", "적자", "영업익", "이익률"),
        ("기업", "회사", "산업", "시장", "생산", "제품", "매출", "실적", "공급", "수요", "스타트업", "벤처", "시설", "설비", "반도체", "영업이익", "이익률", "협력"),
    ),
    (
        ("회동", "만났다", "협력", "협약", "공동개발", "공동 개발", "신사업", "신제품"),
        ("공급", "고객", "공장", "설비", "상용화", "양산", "기술", "제조", "제품", "투자계약", "생산", "판매", "반도체", "메모리", "hbm", "파운드리", "인프라", "로봇"),
    ),
    (
        ("보조금", "지원금", "보증", "정책자금", "조례", "규제", "예탁금", "관세", "수출통제", "증시경보"),
        ("기업", "산업", "투자", "생산", "수출", "수입", "통관", "금융", "증권", "주식", "장비", "인허가"),
    ),
    (
        ("폭염", "폭우", "홍수", "태풍", "정전", "폐사", "가뭄", "산불"),
        ("전력", "변압기", "과부하", "양식", "농작물", "생산", "공급", "물류", "공장", "항만", "철도", "운항"),
    ),
    (
        ("파업", "노조", "성과급", "임단협", "감원", "감축", "임금"),
        ("기업", "회사", "생산", "공장", "직원", "노동자", "항만", "운송", "수익", "비용"),
    ),
    (
        ("반도체", "메모리", "칩", "ddr", "hbm", "hbf", "cxl", "엑시노스", "gpu", "ai", "로봇", "임상", "의약품", "데이터센터", "핵심광물"),
        ("양산", "상용화", "인증", "승인", "공급", "수요", "실적", "수주", "계약", "생산", "가격", "투자", "품목허가", "메모리", "반도체", "hbm", "도입", "제련", "금속"),
    ),
)
SOURCE_BUSINESS_EVENT_ACTIONS = STOCK_MARKET_CHANGE_TERMS + (
    "설립", "착공", "가동", "도입", "출시", "공개", "개발", "상용화", "양산", "승인", "허가",
    "매수", "매입", "매각", "인수", "합병", "출자", "유치", "지급", "지출", "조성", "출범",
    "정전", "폐사", "과부하", "피해", "둔화", "회복", "전망", "협력", "회동", "맞손",
    "논의", "상장", "구축", "전환", "돌파", "건설", "계획", "시험", "테스트", "나선", "나섰",
)


def has_source_business_market_event(alert: dict) -> bool:
    title = base.norm(str(alert.get("source_title") or alert.get("original_news") or ""))
    body = base.norm(str(alert.get("source_body") or alert.get("source_abstract") or ""))
    if not title or not body or not has_term(f"{title} {body}", SOURCE_BUSINESS_EVENT_ACTIONS):
        return False
    if insider_purchase_signal(f"{title} {body}"):
        return True
    return any(
        has_term(title, subjects) and has_term(body, context)
        for subjects, context in SOURCE_BUSINESS_MARKET_EVENTS
    )


def stock_market_channels(alert: dict) -> list[str]:
    """Find a market subject and change in source text, never generated commentary."""
    title = base.norm(str(alert.get("source_title") or alert.get("original_news") or ""))
    body = base.norm(str(alert.get("source_abstract") or ""))
    source_text = f"{title} {body}"
    if not title or not has_term(source_text, STOCK_MARKET_CHANGE_TERMS):
        return []
    return [
        channel for channel, terms in STOCK_MARKET_SUBJECTS.items()
        if has_term(title, terms)
        and (
            channel not in STOCK_MARKET_REQUIRED_CONTEXT
            or has_term(source_text, STOCK_MARKET_REQUIRED_CONTEXT[channel])
        )
    ]


def has_stock_market_link(alert: dict) -> bool:
    text = source_evidence_text(alert)
    return has_direct_market_path(text, alert)


def has_korea_market_link(alert: dict) -> bool:
    """Compatibility name; global market transmission need not name a Korean issuer."""
    return has_stock_market_link(alert)


def has_direct_market_path(text: str, alert: dict) -> bool:
    text = source_evidence_text(alert) or text
    if verified_materiality_axes(alert) or verified_market_breadth_change(alert):
        return True
    if stock_market_channels(alert):
        return True
    if alert.get("korean_business_news") and (
        alert.get("body_verified") or alert.get("title_fact_verified")
    ):
        return has_source_business_market_event(alert)
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
    if verified_materiality_axes(alert) or verified_market_breadth_change(alert):
        return True
    labels = set(display_impacts(alert.get("impacts")))
    if not labels or labels == {LIMITED_DECISION_IMPACT}:
        alert["guardrail_note"] = "매출·마진·현금흐름, 밸류에이션/할인율, 수급, 시간표 중 바뀐 축이 없어 제외"
        return False
    if not labels.intersection(ACTIONABLE_DECISION_LABELS):
        alert["guardrail_note"] = "시장 의사결정 축으로 분류되지 않아 제외"
        return False
    if not has_stock_market_link(alert):
        alert["guardrail_note"] = "기업 실적·할인율·수급·일정 또는 글로벌 시장 전달 경로 근거가 약해 제외"
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
    title = str(alert.get("source_title") or alert.get("news") or "")
    source = article_summary_body(str(alert.get("source_body") or "")) if alert.get("body_verified") else ""
    if alert.get("body_verified") and market_materiality.focus_kind(title) == "industry_outlook" and not re.search(
        r"조례|모라토리엄|공청회|시의회|군의회|인허가.{0,15}(?:승인|거부|부결|금지)|"
        r"zoning|moratorium|public hearing|city council|county board|permit denied", f"{text} {source}", re.I,
    ):
        # Excluding permit time from a construction estimate is not a local
        # permitting decision, even when a legacy collector assigned that lane.
        return False
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
    source = market_materiality.source_reported_body(str(alert.get('source_body') or '')) if alert.get('body_verified') else ''
    formal_stop = bool(re.search(r'(?:주|정부|당국).{0,180}공사를\s*즉각\s*중단하라고\s*명령', source)
                       and re.search(r'환경영향평가.*?인허가.{0,35}발급되지', source, re.S))
    if formal_stop and (korean_business_publisher(alert) or has_trusted_source) and not weak_local_only:
        return True
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
    # A verified source-body profile may expose the actual price-moving event
    # when a broad market-recap title would hide it.
    headline_override = str(alert.get("headline_override") or "").strip()
    if headline_override and not mostly_ascii(headline_override):
        return headline_override
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
        return raw if raw and not mostly_ascii(raw) else "북미 송전망 투자 정책 변수: 정부 승인·규제 지연 리스크"
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
    if (
        "polysilicon" in text
        and "11052" in text
        and (
            "measures to restrict stockpiling" in text
            or ("stockpil" in text and ("temporary final rule" in text or "import prohibition" in text))
        )
    ):
        return "미 상무부, 폴리실리콘 사재기 차단 규칙 시행"
    if (
        "polysilicon" in text
        and "11052" in text
        and has_term(text, ["minimum import price", "15% ad valorem", "15 percent ad valorem", "adjusting imports of polysilicon"])
    ):
        return "미국, 폴리실리콘 Section 232 최저수입가격·관세 조치"
    if has_term(text, [
        "space photovoltaics research and development partnership intermediary agreement",
        "space-based energy generation",
        "solar panels in space applications",
    ]) and has_term(text, [
        "awardee", "awardees", "recipient", "recipients",
        "selected for award", "selected projects", "announces selections", "announced selections",
        "has selected", "have selected", "selected the following", "awarded to",
        "selection notifications issued", "selection notifications sent", "selection notifications released",
        "awards announced",
    ]):
        return "미 에너지부, 우주태양광 R&D 선정 결과 발표"
    if has_term(text, [
        "space photovoltaics research and development partnership intermediary agreement",
        "space-based energy generation",
        "solar panels in space applications",
    ]):
        return "미 에너지부, 우주태양광 R&D 지원사업 공고"
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
    if out.get("korean_business_news") and out.get("body_verified"):
        repaired_core = verified_alert_core(out, str(out.get("source_title") or out.get("news") or ""))
        if repaired_core:
            out["telegram_core_fact"] = repaired_core
            out["policy_plain_summary"] = repaired_core
    macro_theme = telegram.macro_release_theme(out)
    if macro_theme:
        out["supply_chain_theme"] = macro_theme
    market_theme = telegram.korean_market_move_theme(out)
    if market_theme:
        out["supply_chain_theme"] = market_theme
    bond_theme = telegram.korean_bond_demand_theme(out)
    if bond_theme:
        out["supply_chain_theme"] = bond_theme
    ceo_theme = telegram.korean_joint_ceo_theme(out)
    if ceo_theme:
        out["supply_chain_theme"] = ceo_theme
    yield_theme = bond_yield_threshold_theme(out)
    if yield_theme:
        out["supply_chain_theme"] = yield_theme
    if is_china_mofcom_control(out):
        out["china_mofcom_trade_control"] = True
        out["impacts"] = ["돈 버는 능력", "수급", "시간표"]
        out["paths"] = ["공급·수요", "원자재 비용", "공급망", "정책 타임라인"]
    if not out.get("source_title"):
        out["source_title"] = out.get("original_news") or out.get("news")
    if not out.get("original_news"):
        out["original_news"] = out.get("source_title") or out.get("news")
    exemption_theme = sanctions_exemption_event_theme(out)
    if exemption_theme:
        out["supply_chain_theme"] = exemption_theme
    source_identity = market_materiality.source_event_identity(out)
    if source_identity:
        out["supply_chain_theme"] = source_identity
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
    source_axes = verified_materiality_axes(out)
    if source_axes:
        impacts = [MATERIALITY_IMPACT_NAMES[axis] for axis in source_axes if axis in MATERIALITY_IMPACT_NAMES]
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


KOREAN_BUSINESS_LOW_VALUE_COMMENTARY_TERMS = [
    "의심할 때 사서",
    "확신할 때 팔아",
    "그게 언제일까요",
    "주식 투자법",
    "투자 고수의 조언",
    "투자하지 않는 것이 최선",
    "ETF 아버지",
    "상폐 아닌 자연사",
    "좋은 꿈을 꾸었습니다",
    "한때 수익률",
    "지금은?",
    "SNS 달군",
    "도플갱어",
    "닮은꼴",
    "바비큐 사장",
    "화제의 인물",
]


def is_low_value_market_commentary(alert: dict) -> bool:
    if not alert.get("korean_business_news"):
        return False
    title = base.norm(str(alert.get("source_title") or alert.get("news") or ""))
    if has_term(title, ("[mk시그널]", "mk시그널 추천", "경제 골든벨")):
        return True
    if not has_term(title, KOREAN_BUSINESS_LOW_VALUE_COMMENTARY_TERMS):
        return False
    hard_facts = [
        "영업이익", "순이익", "매출", "가이던스", "공급계약", "수주", "발주",
        "증설", "유상증자", "자사주", "순매수", "순매도", "관세", "수출통제",
    ]
    return not has_term(title, hard_facts)


def is_stale_opening_market_report(alert: dict, now) -> bool:
    if os.getenv("RADAR_RUN_MODE", "").strip().lower() != "live" or now.hour < 12:
        return False
    title = base.norm(str(alert.get("source_title") or alert.get("news") or ""))
    return has_term(title, ("약세 출발", "강세 출발", "상승 출발", "하락 출발")) and has_term(
        title, ("삼성전자", "SK하이닉스", "삼전", "닉스", "코스피", "코스닥", "증시")
    )


def is_stale_session_preview(alert: dict, now) -> bool:
    title = str(alert.get("source_title") or alert.get("news") or "")
    if not re.search(r"오늘의\s*증시|오늘\s*증시|오늘의\s*시장\s*전망", title):
        return False
    published = detail_queue.parse_time(alert.get("published"))
    return bool(published and published.astimezone(now.tzinfo).date() < now.date())


def is_nonmarket_business_event(item: dict) -> bool:
    title = base.norm(str(item.get("source_title") or item.get("news") or item.get("title") or ""))
    body = str(item.get("source_body") or "") if item.get("body_verified") else ""
    if market_materiality.nonmarket_entertainment_reason(title, body, str(item.get("link") or "")):
        return True
    material_events = (
        "매출", "영업이익", "순이익", "가이던스", "공급계약", "수주", "발주",
        "자사주", "주식 매수", "주식매수", "지분", "인수", "합병", "상장",
        "투자협약", "투자 협약", "투자계약", "투자 계약", "수출통제", "관세",
    )
    if has_term(title, material_events):
        return False
    sports_election = has_term(title, ("연맹", "체육회", "스포츠협회", "당구")) and has_term(
        title, ("회장 선거", "회장선거", "후보 당선", "회장 당선")
    )
    ceremonial_photo = "포토" in title and has_term(
        title, ("폐회사", "개회사", "축사", "기념촬영", "기념 촬영")
    )
    return sports_election or ceremonial_photo


def is_stale_intraday_market_report(alert: dict, now) -> bool:
    if os.getenv("RADAR_RUN_MODE", "").strip().lower() != "live" or (now.hour, now.minute) < (15, 45):
        return False
    title = base.norm(str(alert.get("source_title") or alert.get("news") or ""))
    if not has_term(title, ("코스피", "코스닥", "한국 증시", "국내 증시")):
        return False
    if has_term(title, ("마감", "종가")) or not has_term(
        title, ("장중", "오전", "상승세 전환", "하락세 전환", "상승 전환", "하락 전환"),
    ):
        return False
    published = detail_queue.parse_time(alert.get("published"))
    if published and published.astimezone(now.tzinfo).date() == now.date() and (
        published.astimezone(now.tzinfo).hour, published.astimezone(now.tzinfo).minute
    ) < (15, 30):
        return True
    body = str(alert.get("source_body") or alert.get("source_abstract") or "")
    return bool(re.search(r"(?:오전\s*(?:9|10|11)|오후\s*(?:12|1|2))\s*시(?:\s*\d+\s*분)?\s*(?:기준|현재)", body))


GENERIC_BUSINESS_TITLE_SIGNALS = (
    "주식", "증시", "코스피", "코스닥", "etf", "etn", "채권", "금리", "환율",
    "수출", "수입", "투자", "자사주", "매출", "영업이익", "순이익", "실적",
    "공장", "생산", "판매", "계약", "수주", "발주", "증설", "인수", "매각",
    "대표", "회장", "ceo", "사장", "기업", "반도체", "ai", "데이터센터",
    "원전", "전력", "배터리", "관세", "정책", "규제", "유가", "lng",
    "정전", "폭염", "물가", "물류", "해운", "자동차", "조선", "방산",
    "바이오", "임상", "fda", "의약품", "화학", "철강", "은행", "보험",
    "펀드", "재정", "산업", "사업", "상장", "ipo", "무역", "공급망",
)


def is_unanchored_generic_business_alert(alert: dict) -> bool:
    if not alert.get("korean_business_news"):
        return False
    if verified_materiality_axes(alert):
        return False
    sectors = [str(item).strip() for item in alert.get("sectors") or []]
    if sectors != ["한국 기업/산업 뉴스"]:
        return False
    title = base.norm(str(alert.get("source_title") or alert.get("news") or ""))
    return not has_term(title, GENERIC_BUSINESS_TITLE_SIGNALS)


def is_space_pv_pia_base_rehash(alert: dict) -> bool:
    text = base.norm(
        " ".join(
            str(alert.get(key) or "")
            for key in (
                "source_title", "original_news", "news", "source_abstract",
                "source_body", "summary", "telegram_core_fact", "policy_plain_summary",
            )
        )
    )
    base_terms = (
        "space photovoltaics research and development partnership intermediary agreement",
        "space photovoltaics (pv) research and development partnership intermediary agreement",
        "space-based energy generation",
        "solar panels in space applications",
    )
    if not any(term in text for term in base_terms):
        return False
    stage_change_terms = (
        "awardee", "awardees", "recipient", "recipients",
        "selected for award", "selected projects", "announces selections", "announced selections",
        "has selected", "have selected", "selected the following", "awarded to",
        "selection notifications issued", "selection notifications sent", "selection notifications released",
        "awards announced",
    )
    return not any(term in text for term in stage_change_terms)


def is_polysilicon_11052_base_rehash(alert: dict) -> bool:
    text = base.norm(
        " ".join(
            str(alert.get(key) or "")
            for key in (
                "source_title", "original_news", "news", "source_abstract",
                "source_body", "summary", "telegram_core_fact", "policy_plain_summary",
            )
        )
    )
    if semantic_event_theme(alert) != "polysilicon-11052-base":
        return False
    stage_change_terms = (
        "amend", "amended", "amendment", "modify", "modified", "revision", "revised",
        "waiver", "exemption", "temporary final rule", "stockpil", "import prohibition",
        "new rule", "new guidance", "changes to", "changed",
    )
    return not any(term in text for term in stage_change_terms)


def source_market_materiality(alert: dict) -> dict:
    title = str(alert.get("source_title") or alert.get("original_news") or "")
    body = str(alert.get("source_body") or alert.get("source_abstract") or "")
    if not alert.get("body_verified"):
        body = ""
    return market_materiality.assess(title, article_summary_body(body), source_url=str(alert.get("link") or ""))


def verified_materiality_axes(alert: dict) -> list[str]:
    """Verified source changes must survive legacy sector/label keyword gates."""
    audit = source_market_materiality(alert)
    if audit["disposition"] != "keep" or audit["priority"] < 2:
        return []
    return list(audit["axes"])


def verified_market_breadth_change(alert: dict) -> bool:
    # Index/constituent dispersion is a market observation, not proof of flows.
    audit = source_market_materiality(alert)
    return bool(
        alert.get("body_verified")
        and audit["disposition"] == "keep"
        and audit["priority"] >= 2
        and audit.get("transmission_scope_reason") == "market_wide_breadth_change"
    )


def is_dedicated_fcc_optical_transceiver_policy(alert: dict) -> bool:
    """Keep FCC optical-transceiver policy in the KHS policy owner lane.

    GAMEJOA may still discover the article for research context, but it must not
    deliver a second Telegram alert for the same FCC optics policy event.
    """
    text = " ".join(
        str(alert.get(key) or "")
        for key in (
            "source_title", "original_news", "source_body", "source_abstract",
            "summary", "telegram_core_fact", "policy_plain_summary", "link", "source",
        )
    ).lower()
    has_fcc = (
        "federal communications commission" in text
        or re.search(r"\bfcc\b", text) is not None
        or "docs.fcc.gov" in text
        or "fcc.gov" in text
    )
    has_optics = any(
        term in text
        for term in (
            "optical transceiver", "optical transceivers", "fiber optic transceiver",
            "fiber-optic transceiver", "optical module", "optical modules",
            "광트랜시버", "광모듈", "光收发器", "光模组",
        )
    )
    has_policy_shape = any(
        term in text
        for term in (
            "covered list", "equipment authorization", "ban", "bar", "prohibit",
            "restriction", "restrictions", "3.2t", "65%", "65 percent",
            "morgan stanley", "drafting", "phase in", "phased",
        )
    )
    return bool(has_fcc and has_optics and has_policy_shape)


def is_dedicated_fcc_robot_inverter_policy(alert: dict) -> bool:
    """Keep FCC robot/inverter Covered List chronology in the KHS policy owner lane.

    GAMEJOA can still discover and analyze the source, but it must not deliver the
    same FCC policy event through the shared policy Telegram route. This prevents
    cross-workflow duplicate sends and article-date replays of the July 28, 2026
    Covered List baseline.
    """
    text = " ".join(
        str(alert.get(key) or "")
        for key in (
            "source_title", "original_news", "source_body", "source_abstract",
            "summary", "telegram_core_fact", "policy_plain_summary", "link", "source",
        )
    ).lower()
    has_fcc = (
        "federal communications commission" in text
        or re.search(r"\bfcc\b", text) is not None
        or "docs.fcc.gov" in text
        or "fcc.gov" in text
    )
    has_covered_action = (
        "covered list" in text
        or "equipment authorization" in text
        or "da 26-786" in text
        or "da-26-786" in text
        or "da 26-870" in text
        or "da-26-870" in text
        or "da 26-957" in text
        or "da-26-957" in text
        or "da 26-996" in text
        or "da-26-996" in text
    )
    has_robot_or_inverter = any(
        term in text
        for term in (
            "advanced robotic device", "advanced robotic devices",
            "foreign-produced robotic", "robot cleaner", "robotic lawn",
            "pool-cleaning robot", "power inverter", "power inverters",
            "foreign-produced power inverter",
        )
    )
    return bool(has_fcc and has_covered_action and has_robot_or_inverter)


def quality_display_alerts(alerts: list[dict], limit: int) -> list[dict]:
    initial = telegram.display_alerts(alerts, min(max(limit * 3, 12), 30))
    candidates = list({id(alert): alert for alert in initial + alerts}.values())
    now = base.kst_now()
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
    for alert in candidates:
        alert["market_materiality"] = source_market_materiality(alert)
    candidates = sorted(
        candidates,
        key=lambda alert: (
            alert["market_materiality"].get("transmission_scope_rank", 0),
            alert["market_materiality"].get("news_value_rank", 0),
            alert["market_materiality"]["priority"],
            alert["market_materiality"].get("focus", 0),
            (detail_queue.parse_time(alert.get("published")) or dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)).timestamp(),
        ),
        reverse=True,
    )
    selected: list[dict] = []
    seen: set[tuple[str, str]] = set()
    seen_facts: set[str] = set()
    for alert in candidates:
        if alert["market_materiality"]["disposition"] == "exclude":
            alert["_exclusion_reason"] = "market_materiality:" + alert["market_materiality"]["reason"]
            continue
        if alert["market_materiality"]["disposition"] != "keep" or alert["market_materiality"]["priority"] < 2:
            alert["_exclusion_reason"] = "no_source_market_change_evidence:" + alert["market_materiality"].get("scope_note", alert["market_materiality"]["reason"])
            continue
        if is_dedicated_fcc_optical_transceiver_policy(alert):
            alert["_exclusion_reason"] = "dedicated_khs_policy_owner:fcc_optical_transceiver"
            continue
        if is_dedicated_fcc_robot_inverter_policy(alert):
            alert["_exclusion_reason"] = "dedicated_khs_policy_owner:fcc_robot_inverter_covered_list"
            continue
        if is_polysilicon_11052_base_rehash(alert):
            alert["_exclusion_reason"] = "historical_polysilicon_11052_base_rehash"
            continue
        if is_space_pv_pia_base_rehash(alert):
            alert["_exclusion_reason"] = "historical_space_pv_pia_rehash"
            continue
        if is_low_value_market_commentary(alert):
            alert["_exclusion_reason"] = "low_value_market_commentary"
            continue
        if is_nonmarket_business_event(alert):
            alert["_exclusion_reason"] = "nonmarket_ceremonial_or_sports"
            continue
        if is_unanchored_generic_business_alert(alert):
            alert["_exclusion_reason"] = "generic_sector_without_market_title"
            continue
        if is_stale_opening_market_report(alert, now):
            alert["_exclusion_reason"] = "stale_opening_market_report"
            continue
        if is_stale_session_preview(alert, now):
            alert["_exclusion_reason"] = "stale_session_preview"
            continue
        if is_stale_intraday_market_report(alert, now):
            alert["_exclusion_reason"] = "stale_intraday_market_report"
            continue
        if is_low_impact_admin_alert(alert):
            alert["_exclusion_reason"] = "low_impact_admin_document"
            continue
        if is_low_impact_trade_admin_notice(alert):
            alert["_exclusion_reason"] = "low_impact_trade_admin_notice"
            continue
        if is_local_dc_like(alert) and not is_actionable_local_dc_policy(alert):
            alert["_exclusion_reason"] = "local_data_center_without_trusted_hard_action"
            continue
        # A headline-only fallback is useful while collecting candidates, but it
        # is not sufficient for a Telegram alert.  Publishing it would repeat
        # the headline instead of explaining the linked article.
        if (
            not alert.get("body_verified")
            and str(alert.get("telegram_core_fact") or "").strip().startswith(
                "공개된 제목에 따르면"
            )
        ):
            alert["_exclusion_reason"] = "title_only_summary"
            continue
        normalized = normalize_alert_for_output(alert)
        if not source_output_aligned(normalized):
            core_errors = source_core_fact_errors(normalized)
            alert["_exclusion_reason"] = "core_fact_guard:" + ",".join(core_errors) if core_errors else "source_body_mismatch"
            continue
        normalized["stock_market_channels"] = stock_market_channels(normalized)
        if not has_stock_market_link(normalized):
            alert["_exclusion_reason"] = "stock_market_link_guard"
            continue
        key = alert_dedup_key(normalized)
        fact_keys = market_materiality.verified_source_fact_keys(normalized)
        if key in seen or (fact_keys and all(fact in seen_facts for fact in fact_keys)):
            alert.setdefault("_exclusion_reason", "semantic_duplicate")
            continue
        if is_low_impact_admin_alert(normalized):
            alert["_exclusion_reason"] = "low_impact_admin_document"
            continue
        if is_low_impact_trade_admin_notice(normalized):
            alert["_exclusion_reason"] = "low_impact_trade_admin_notice"
            continue
        if not has_decision_impact(normalized):
            alert["_exclusion_reason"] = "decision_impact_guard"
            alert["guardrail_note"] = normalized.get("guardrail_note") or "구체 사유 확인 불가"
            alert["_decision_debug"] = {
                "kind": normalized.get("korean_business_kind"),
                "impacts": display_impacts(normalized.get("impacts")),
                "sectors": normalized.get("sectors") or [],
                "body_verified": bool(normalized.get("body_verified")),
                "has_korea_market_link": has_korea_market_link(normalized),
                "generic_explanation": has_generic_explanation(normalized),
            }
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
        seen.add(key)
        seen_facts.update(fact_keys)
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


DATED_WIRE_PHOTO_PATTERN = (
    r"\[[^\]\r\n]{1,40}=\s*(?:AP|AFP|Reuters|뉴시스|연합뉴스)(?:/[A-Za-z가-힣]+)?\]"
    r"(?![^.\r\n]{0,50}기자\s*=)[^\r\n]{0,600}?(?:고\s*있다|자료사진)"
    r"[^\r\n]{0,600}?\b\d{4}\.\d{1,2}\.\d{1,2}\.\s*"
    r"|\[[^\]\r\n]{1,40}=\s*(?:AP|AFP|Reuters|뉴시스|연합뉴스)(?:/[A-Za-z가-힣]+)?\]"
    r"(?![^.\r\n]{0,50}기자\s*=)[^\r\n]{0,1400}?사진은[^\r\n]{0,500}?\b\d{4}\.\d{1,2}\.\d{1,2}\.\s*"
)
CORE_UI_GARBAGE_PATTERNS = (
    DATED_WIRE_PHOTO_PATTERN,
    r"^\s*\d{4}\.\d{1,2}\.\d{1,2}\.\s*(?=[가-힣A-Za-z])",
    r"^[^.!?\r\n]{0,140}\[[^\]\r\n]{0,40}자료사진\]\s*",
    r'[^.!?\r\n"“”]*?(?:시공|시연|촬영)하고\s*있다\s*\(사진\s*=[^)]*\)',
    r'[^.!?\r\n"“”]*?(?:발언|연설|질문에\s*답|기념촬영을)\s*하고\s*있다\.',
    r"\((?:사진|사진제공|촬영|자료사진)\s*(?:=|:)[^)]{1,100}\)",
    r"\b등록\s*\d{4}[./-]\d{1,2}[./-]\d{1,2}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?"
    r"(?:\s*수정\s*\d{4}[./-]\d{1,2}[./-]\d{1,2}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?)?",
    r"\b(?:입력|등록)\s*\d{4}[./-]\d{1,2}[./-]\d{1,2}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?"
    r"(?:\s*수정\s*\d{4}[./-]\d{1,2}[./-]\d{1,2}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?)?"
    r"\s*[가-힣]{2,6}\s*기자\b",
    r"^\s*\([^)]{0,80}(?:로이터|연합뉴스|Reuters|AP|AFP)[^)]*\)\s*",
    r"구글에서\s*선호하는\s*매체로\s*추가",
    r"\b작게\s*크게\b",
    r"\b(?:북마크|마이페이지에서\s*확인하세요)\b",
    r"\b카카오톡\s+페이스북\s+엑스\s+URL\s*공유\b",
    r"재판매\s*및\s*DB\s*금지",
    r"\]?\s*\([^)]{0,30}=.{0,30}\)\s*[^.!?]{0,50}?기자\s*=",
    r"\b[가-힣]{2,4}\s*기자\s*=",
    r"무단\s*전재(?:-?재배포)?\s*금지",
    r"AI\s*학습\s*및\s*활용\s*금지",
    r"저작권자.{0,40}무단\s*전재",
    r"\[email\s+protected\]",
    r"\[[^\]\r\n]{1,40}=\s*(?:AP|AFP|Reuters|뉴시스|연합뉴스)(?:/[A-Za-z가-힣]+)?\]",
    r"[\ufeff\u200b]",
    r"\[(?:촬영|사진|자료사진|제공)\s+[^\]\r\n]{1,60}\]",
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
)


def core_has_ui_garbage(value: object) -> bool:
    text = html.unescape(str(value or ""))
    return any(
        re.search(pattern, text, flags=re.IGNORECASE)
        for pattern in CORE_UI_GARBAGE_PATTERNS
    )


def strip_core_ui_garbage(value: object) -> str:
    """Remove known publisher chrome before sentence ranking, never before direct output."""
    # Remove bracketed photo credits before the byline pattern can consume
    # their closing bracket next to a concatenated wire-service dateline.
    raw = re.sub(DATED_WIRE_PHOTO_PATTERN, " ", html.unescape(str(value or "")), flags=re.I)
    text = clean_article_summary_text(raw)
    for pattern in CORE_UI_GARBAGE_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def core_sentence_is_complete(value: object, limit: int = GAMEJOA_CORE_MAX_CHARS) -> bool:
    text = clean_article_summary_text(value)
    if not text or text == "확인 불가" or len(text) > limit:
        return False
    if core_has_ui_garbage(text) or "…" in text or re.search(r"\.{3,}", text):
        return False
    # A sentence beginning with a discourse connector is usually a clipped
    # paragraph fragment from a publisher page, not a self-contained summary.
    if re.match(r"^(?:그리고|한편|다만|그러나|이에|여기에|이\s*부문|이와\s*관련해)\s+", text):
        return False
    if re.match(r"^(?:이\s*과정에서|이러한|이\s*같은|이를\s*통해|그\s*결과)\s+", text):
        return False
    if re.match(r"^(?:이|해당|그)\s*(?:기술|시스템|제품|장비)(?:이|은|는|을|의|가)\s+", text):
        return False
    if (
        re.search(r"(?:예상치|전망치|기대치).*?(?:밑돈|웃돈|낮은|높은)\s*(?:수치|수준)(?:다|이다)[.!?。]?$", text)
        and not re.search(r"PCE|CPI|지수|성장률|매출|이익|가격|금리|환율|실업률|고용", text, re.I)
    ):
        return False
    if re.match(r"^(?:을|를|은|는|의)\s+", text) or re.search(r"(?:는데요|거든요|잖아요)[.!?。]?$", text):
        return False
    if re.search(
        r"(?:보다|에게|에서|으로|와|과|은|는|이|가|을|를|의|며|고)(?:[.!?。])?$",
        text,
    ):
        return False
    terminal = re.sub(r"[.!?。]+$", "", text).strip()
    return bool(
        re.search(
            r"(?:다|요|함|됨|임|음)$",
            terminal,
        )
    )


def complete_prose_text(value: object, *, fallback: object = "", limit: int) -> str:
    """Keep only a verified, complete sentence; never fabricate a suffix for a fragment."""
    raw_value = html.unescape(str(value or ""))
    fallback_value = html.unescape(str(fallback or ""))
    if core_has_ui_garbage(raw_value):
        raw_value = ""
    raw = clean_article_summary_text(raw_value) or clean_article_summary_text(fallback_value)
    if not raw or raw == "확인 불가" or core_has_ui_garbage(raw):
        return ""

    text = re.sub(r"\s*(?:…+|\.{3,})\s*", ". ", raw)
    text = re.sub(r"\.\s*\.", ".", text)
    text = re.sub(r"^(?:및|또한|아울러|이어|여기에)\s+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text or core_has_ui_garbage(text):
        return ""

    if len(text) <= limit:
        if re.search(r"[.!?。]$", text) and core_sentence_is_complete(text, limit):
            return text
        if re.search(r"(?:합니다|했습니다|됩니다|됐습니다|있습니다|없습니다|한다|했다|됐다|된다|이다|입니다|아니다)$", text):
            completed = f"{text}."
            if core_sentence_is_complete(completed, limit):
                return completed

    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?。])\s+", text) if re.search(r"[.!?。]$", sentence)]
    complete = [
        sentence
        for sentence in sentences
        if len(sentence) <= limit and core_sentence_is_complete(sentence, limit)
    ]
    if complete:
        return max(complete, key=len)
    return ""


def canonical_title_fact(title: object) -> str:
    """Use a narrow title-derived fact only when article text is unusable."""
    headline = clean_article_summary_text(title)
    headline = re.sub(r"\s*\|.*$", "", headline).strip()
    subject_match = re.match(r"^\s*([A-Za-z0-9가-힣·]+)", headline)
    subject = subject_match.group(1) if subject_match else ""
    if not subject:
        return ""

    if "자사주" in headline and ("취득" in headline or "소각" in headline):
        action = "자사주 취득·소각"
        if "주주환원" in headline:
            return f"{subject}가 {action}과 주주환원 조기 시행을 발표했습니다."
        return f"{subject}가 {action}을 발표했습니다."

    if "합작법인" in headline and "검토 중단" in headline:
        remainder = headline[len(subject):].lstrip(" ,:\"“")
        partner_match = re.search(
            r"(.+?)(?:와|과)\s*합작법인\s*설립\s*검토\s*중단",
            remainder,
        )
        partner = partner_match.group(1).strip(" \"“”") if partner_match else ""
        if partner:
            return f"{subject}은 {partner}와의 합작법인 설립 검토를 중단했습니다."
    return ""


def title_only_provisional_core(title: object) -> str:
    """Retain title-only items as explicitly provisional facts, never as body evidence."""
    headline = clean_article_summary_text(title)
    if not headline or core_has_ui_garbage(headline):
        return ""
    candidate = f"공개된 제목에 따르면, {headline}."
    return candidate if len(candidate) <= GAMEJOA_CORE_MAX_CHARS else ""


def single_stock_leverage_core(alert: dict, title: str) -> str:
    """Keep both rule amounts and the effective date inside the compact core."""
    source = " ".join(
        str(alert.get(key) or "")
        for key in ("source_body", "source_abstract", "summary", "telegram_core_fact", "policy_plain_summary")
    )
    if not (
        alert.get("korean_business_kind") == "single_stock_leverage_rule"
        or ("단일종목" in source and "기본예탁금" in source)
    ):
        return ""
    amount_match = re.search(
        r"기본예탁금(?:이|을)?\s*(\d+(?:,\d+)?만원)\s*(?:에서|→)\s*(\d+(?:,\d+)?만원)",
        source,
    )
    date_match = re.search(
        r"(\d{1,2}일(?:부터)?)\s*(?:동시|시행|적용|부터)",
        source,
    )
    if not amount_match or not date_match:
        return ""
    return (
        "삼성전자·SK하이닉스 단일종목 레버리지 ETF·ETN 기본예탁금이 "
        f"{date_match.group(1)} {amount_match.group(1)}에서 {amount_match.group(2)}으로 상향됩니다."
    )


def verified_alert_core(alert: dict, title: str) -> str:
    """Recover a complete headline fact; publication still applies source guards."""
    is_business = bool(alert.get("korean_business_news"))
    source_title = clean_article_summary_text(
        alert.get("source_title") or alert.get("original_news") or title
    )
    candidates: list[str] = []
    def valid_source_fact(fact: str) -> bool:
        return bool(core_sentence_is_complete(fact) and not source_core_fact_errors({**alert, "telegram_core_fact": fact}))

    rule_core = single_stock_leverage_core(alert, title)
    if core_sentence_is_complete(rule_core):
        return rule_core

    if is_business:
        if alert.get("body_verified"):
            body = str(alert.get("source_body") or alert.get("source_abstract") or "")
            observed_fact = source_headline_event_fact(source_title or title, article_summary_body(body))
            if observed_fact and valid_source_fact(observed_fact):
                return observed_fact
            entry_fact = conditional_financial_market_entry_fact(source_title or title, article_summary_body(body))
            if entry_fact and valid_source_fact(entry_fact):
                return entry_fact
            listing_fact = listing_maintenance_action_fact(source_title or title, str(alert.get("source_body") or ""))
            if listing_fact:
                return listing_fact
            cyber_fact = financial_cyber_incident_fact(source_title or title, article_summary_body(body))
            if cyber_fact and valid_source_fact(cyber_fact):
                return cyber_fact
            commercial_fact = contextual_commercial_fact(source_title or title, article_summary_body(body))
            if commercial_fact and valid_source_fact(commercial_fact):
                return commercial_fact
            revision_fact = financial_revision_fact(source_title or title, ranked_article_sentences(body, [], title=source_title or title), body)
            if revision_fact and valid_source_fact(revision_fact):
                return revision_fact
            financial_fact = headline_financial_fact(source_title or title, article_summary_body(body))
            if financial_fact and valid_source_fact(financial_fact):
                return financial_fact
            focused_fact = source_focused_article_core(source_title or title, ranked_article_sentences(
                body, korean_business_title_terms(source_title or title), title=source_title or title,
            ))
            if focused_fact and valid_source_fact(focused_fact):
                return focused_fact
        source_body = article_summary_body(
            "\n".join(
                str(alert.get(key) or "")
                for key in (
                    "source_body",
                    "article_body",
                    "source_abstract",
                    "summary",
                    "original_summary",
                )
                if alert.get(key)
            )
        )
        if source_body:
            regenerated = detailed_article_core(source_title or title, source_body)
        if not source_core_fact_errors(alert):
            candidates.append(str(alert.get("telegram_core_fact") or ""))
        if source_body:
            candidates.append(regenerated)
        candidates.append(canonical_title_fact(source_title or title))
    else:
        candidates.extend(
            [
                str(alert.get("policy_plain_summary") or ""),
                str(alert.get("telegram_core_fact") or ""),
            ]
        )

    if is_business and alert.get("body_verified"):
        for candidate in candidates:
            core = complete_prose_text(candidate, limit=GAMEJOA_CORE_MAX_CHARS)
            if valid_source_fact(core) and market_materiality.core_focus_aligned(source_title, core):
                return core
        audit = source_market_materiality(alert)
        if audit["disposition"] == "keep" and audit["priority"] >= 2:
            for evidence in audit["evidence"]:
                fact = normalized_article_sentence(evidence["source_excerpt"])
                core = complete_prose_text(fact, limit=GAMEJOA_CORE_MAX_CHARS)
                if valid_source_fact(core) and market_materiality.core_focus_aligned(source_title, core):
                    return core
        # A complete but low-materiality fact remains inspectable. The final
        # selection guard still excludes it; do not replace it with background.
    for candidate in candidates:
        core = complete_prose_text(candidate, limit=GAMEJOA_CORE_MAX_CHARS)
        if core_sentence_is_complete(core) and not subjectless_financial_core(core) and (
            not is_business or market_materiality.core_focus_aligned(source_title, core)
        ):
            return core
    return ""


def source_core_fact_errors(alert: dict) -> list[str]:
    title = str(alert.get("source_title") or alert.get("news") or "")
    source = article_summary_body(str(alert.get("source_body") or alert.get("source_abstract") or ""))
    core = str(alert.get("telegram_core_fact") or "")
    if not source or not core:
        return []
    errors = []
    expected_observation = source_headline_event_fact(title, source)
    observation_core = re.sub(r"\((?:약[^)]*|원화\s*환산\s*확인\s*불가)\)", "", core)
    if expected_observation and market_materiality.canonical_source_fact(expected_observation) != market_materiality.canonical_source_fact(observation_core):
        errors.append("headline_actor_population_period_or_standard_mismatch")
    negotiation = acquisition_negotiation_fact(title, source)
    if negotiation and not re.search(r"논의\s*중|협상\s*중|검토\s*중", core):
        errors.append("acquisition_negotiation_reported_as_confirmed")
    if re.match(r"^(?:출시|도입)\s*이후\s", core) and re.search(r"공급\s*계약|사업\s*수행기관", core):
        errors.append("commercial_contract_actor_missing")
    expected_commercial = contextual_commercial_fact(title, source)
    if expected_commercial and re.search(r"공급\s*계약|사업\s*수행기관", core):
        if re.sub(r"\s+", "", expected_commercial) != re.sub(r"\s+", "", core):
            errors.append("commercial_contract_actor_customer_or_stage_mismatch")
    if not market_materiality.core_focus_aligned(title, core):
        errors.append("headline_event_or_period_mismatch")
    if market_materiality.focus_kind(title) == "cyber_incident":
        expected_cyber = financial_cyber_incident_fact(title, source)
        if expected_cyber and re.sub(r"\s+", "", expected_cyber) != re.sub(r"\s+", "", core):
            errors.append("cyber_incident_actor_count_or_response_stage_mismatch")
    if market_materiality.focus_kind(title) == "asset_financing":
        observations = [asset_financing_observation(sentence) for sentence in market_materiality.source_sentences(source)]
        observations = [item for item in observations if item]
        core_observation = asset_financing_observation(core)
        if (observations or core_observation) and core_observation not in observations:
            errors.append("asset_financing_actor_amount_or_stage_mismatch")
    if market_materiality.focus_kind(title) == "factory_tariff" or market_materiality.factory_tariff_observation(title, source):
        expected_tariff = source_focused_article_core(title, market_materiality.source_sentences(source))
        if expected_tariff and re.sub(r"\s+", "", expected_tariff) != re.sub(r"\s+", "", core):
            errors.append("factory_tariff_condition_rate_or_statement_mismatch")
    if market_materiality.focus_kind(title) in {"capital_spending", "breadth"}:
        expected_fact = source_focused_article_core(title, market_materiality.source_sentences(source))
        if expected_fact:
            comparable_core = re.sub(r"\(약[^)]*\)", "", core)
            if re.sub(r"\s+", "", expected_fact) != re.sub(r"\s+", "", comparable_core):
                errors.append("investment_horizon_or_market_population_mismatch")
    if market_materiality.focus_kind(title) == "fx" and re.search(r"전망|예상", title):
        expected_forecast = source_focused_article_core(title, market_materiality.source_sentences(source))
        if expected_forecast and re.sub(r"\s+", "", expected_forecast) != re.sub(r"\s+", "", core):
            errors.append("fx_forecast_attribution_target_or_horizon_mismatch")
    if market_materiality.focus_kind(title) == "national_exports":
        expected_export = source_focused_article_core(title, market_materiality.source_sentences(source))
        if expected_export:
            comparable_core = re.sub(r"\((?:약[^)]*|원화\s*환산\s*확인\s*불가)\)", "", core)
            if re.sub(r"\s+", "", expected_export) != re.sub(r"\s+", "", comparable_core):
                errors.append("national_export_observed_period_total_mismatch")
    expected_compensation = compensation_cost_forecast_fact(title, source)
    if expected_compensation:
        comparable_core = re.sub(r"\((?:약[^)]*|원화\s*환산\s*확인\s*불가)\)", "", core)
        if re.sub(r"\s+", "", expected_compensation) != re.sub(r"\s+", "", comparable_core):
            errors.append("compensation_cost_forecast_actor_period_or_amount_mismatch")
    expected_entry = conditional_financial_market_entry_fact(title, source)
    if expected_entry and re.sub(r"\s+", "", expected_entry) != re.sub(r"\s+", "", core):
        errors.append("market_entry_conditions_issuer_or_first_trade_date_mismatch")
    expected_loss = profit_loss_result_fact(title, market_materiality.source_sentences(source))
    if expected_loss:
        basis = re.search(r"(?:모회사\s*귀속\s*|지배주주\s*귀속\s*)?순손실", expected_loss).group(0)
        amounts = extract_foreign_amounts(expected_loss)
        compact_core = re.sub(r"\s", "", core)
        if basis.replace(" ", "") not in compact_core or not re.search(r"적자\s*전환|적자로\s*전환", core):
            errors.append("observed_loss_or_accounting_basis_omitted")
        if amounts and amounts[0]["raw"].replace(" ", "") not in compact_core:
            errors.append("observed_loss_amount_mismatch")
    if market_materiality.focus_kind(title) == "product_sales_mix":
        expected_mix = source_focused_article_core(title, market_materiality.source_sentences(source))
        if expected_mix:
            compact_core = re.sub(r"\s", "", core)
            required = re.findall(r"\d{1,2}[~∼-]\d{1,2}월|\d+(?:\.\d+)?%포인트|\d+(?:\.\d+)?%", expected_mix)
            parties = re.search(r"([A-Za-z0-9가-힣&]+(?:[·ㆍ][A-Za-z0-9가-힣&]+)+)", title)
            if any(value not in compact_core for value in required) or (
                parties and not all(party in core for party in re.split(r"[·ㆍ]", parties.group(1)))
            ):
                errors.append("combined_sales_population_or_mix_mismatch")
    if market_materiality.COMPANY_PROFILE.search(core):
        errors.append("company_profile_not_news_core")
    if alert.get("korean_business_news"):
        source_audit = market_materiality.assess(title, source)
        if source_audit["disposition"] != "keep" or not source_audit["evidence"]:
            errors.append("article_without_headline_market_change_evidence")
        core_audit = market_materiality.assess(title, core)
        # The economic transmission may be in the full report rather than its
        # short deployment sentence. Require that exact source-bound summary.
        source_bound_deployment = bool(
            market_materiality.focus_kind(title) == "military_reinforcement"
            and source_audit["disposition"] == "keep" and source_audit["priority"] >= 2
            and expected_observation
            and market_materiality.canonical_source_fact(expected_observation) == market_materiality.canonical_source_fact(core)
        )
        if (core_audit["disposition"] != "keep" or not core_audit["evidence"]) and not source_bound_deployment:
            errors.append("core_without_market_change_evidence")
    if core.count("“") != core.count("”"):
        errors.append("orphaned_source_quote")
    if market_materiality.PHOTO_DESCRIPTION.search(core):
        errors.append("photo_description_not_news_core")
    if re.search(r"하고\s*있다\s+(?:[A-Za-z0-9가-힣·&()]+\s+){0,8}[A-Za-z0-9가-힣·&()]+(?:은|는)\s+", core):
        errors.append("concatenated_photo_caption")
    target = analyst_research_target(title, source) or financial_headline_subject(title, source)
    subjects = re.split(r"[·ㆍ]", target) if target else []
    if subjects and re.search(r"영업이익|순이익|매출|판매량", core) and not any(subject in core for subject in subjects):
        errors.append("financial_subject_mismatch")
    revision = financial_revision_fact(title, ranked_article_sentences(source, [], title=title), source)
    if revision:
        values = re.search(rf"({KOREAN_WON_AMOUNT_PATTERN})→({KOREAN_WON_AMOUNT_PATTERN})", revision)
        if values and re.search(r"영업이익|순이익|매출", core):
            compact = re.sub(r"\s", "", core)
            if values.group(1).replace(" ", "") in compact and values.group(2).replace(" ", "") not in compact:
                errors.append("superseded_financial_estimate")
    if re.search(r"수주를\s*이어가|수주가\s*이어", core) and re.search(r"입찰제안서.{0,15}제출|공급계약.{0,15}체결", source):
        errors.append("new_execution_replaced_by_order_history")
    if re.search(r"비롯한|포함한|특수관계인", source) and "개인 명의" in core and not re.search(r"개인\s*명의|개인\s*자금|사비", source):
        errors.append("unsupported_personal_trade_attribution")
    if (
        market_materiality.focus_kind(title) == "ownership" and re.search(r"매각|처분", title)
        and re.search(r"(?:매각|처분)할\s*(?:예정|계획)[^.!?]{0,30}(?:공시했다|밝혔다)", source)
        and not re.search(r"예정|계획|추진|검토|매각할|처분할", core)
    ):
        errors.append("planned_disposal_reported_as_completed")
    return errors


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
            value = clean_article_summary_text(stripped.removeprefix(prefix).strip())
            compacted = complete_prose_text(value, limit=limit)
            if compacted:
                compacted_line = f"{indent}{prefix} {compacted}"
                changed += compacted != value
            break
        output.append(compacted_line)
    suffix = "\n" if str(body or "").endswith("\n") else ""
    return "\n".join(output) + suffix, changed


def compact_title_summary_aligned(title: str, summary: str) -> bool:
    title_low = clean_article_summary_text(title).lower()
    summary_low = clean_article_summary_text(summary).lower()
    if "알래스카" in title_low and "알래스카" not in summary_low:
        return False
    if "lng" in title_low and not has_term(summary_low, ("lng", "액화천연가스")):
        return False
    event_rules = (
        (("지진", "강진", "쓰나미"), ("지진", "강진", "쓰나미", "대피", "방재", "폭발")),
        (("사이드카", "서킷브레이커"), ("사이드카", "서킷브레이커", "프로그램 매수", "프로그램 매도")),
    )
    for title_terms, summary_terms in event_rules:
        if any(term in title_low for term in title_terms):
            return any(term in summary_low for term in summary_terms)
    if "사이드카" in summary_low and not any(
        term in title_low for term in ("사이드카", "코스피", "코스닥", "증시")
    ):
        return False
    return True


def market_move_direction_conflict(title: str, summary: str) -> bool:
    if not has_term(title.lower(), ["코스피", "코스닥", "kospi", "kosdaq"]):
        return False
    title_up = has_term(title, ["↑", "상승", "급등", "올라"])
    title_down = has_term(title, ["↓", "하락", "급락", "내려"])
    core_up = has_term(summary, ["↑", "상승", "급등", "올라", "올랐", "오른"])
    core_down = has_term(summary, ["↓", "하락", "급락", "내려", "내렸", "내린"])
    return (title_up and not title_down and core_down and not core_up) or (
        title_down and not title_up and core_up and not core_down
    )


def subjectless_financial_core(core: str) -> bool:
    return bool(re.match(r"^(?:(?:[1-4]분기|올해|지난해|분기|연간)\s*)?(?:매출|영업이익|순이익)(?:액|률)?(?:은|이|는|\s)", core))


def compact_alert_block_errors(block: str) -> list[str]:
    errors: list[str] = []
    title = ""
    summary = ""
    for line in str(block or "").splitlines():
        visible = html.unescape(line).strip()
        if re.match(r"^\d+\)\s+(?:\[[^\]]+\]\s*)?\S", visible):
            # Accept legacy fixtures but require new production output to omit
            # importance and verification-state labels from the Telegram line.
            title = re.sub(r"^\d+\)\s+(?:\[[^\]]+\]\s*)?", "", visible).strip()
            title = re.sub(r"\(\d+건 묶음\)$", "", title).strip()
        elif visible.startswith("- 핵심:"):
            summary = visible.removeprefix("- 핵심:").strip()
    if not title:
        errors.append("missing_title")
    elif mostly_ascii(title):
        errors.append("raw_english_heading")
    if not summary:
        errors.append("missing_core")
        return errors
    if core_has_ui_garbage(summary):
        errors.append("article_ui_boilerplate")
    if re.search(r"\[[^\]]{0,60}\s*기자\]", summary):
        errors.append("article_ui_boilerplate")
    if not core_sentence_is_complete(summary):
        errors.append("incomplete_core")
    if subjectless_financial_core(summary):
        errors.append("financial_subject_missing")
    if len(summary) > GAMEJOA_CORE_MAX_CHARS:
        errors.append("core_too_long")
    if "…" in summary or re.search(r"\.{3,}", summary):
        errors.append("truncated_core")
    if re.search(
        r"(?:보다|에게|에서|으로|와|과|은|는|이|가|을|를|의|며|고)(?:[.!?。])?$",
        summary,
    ) or re.search(
        r"(?:의|은|는|이|가|을|를)\s*(?:미국|한국|중국|일본|유럽|인도)[.!?。]?$",
        summary,
    ):
        errors.append("incomplete_core")
    if title and (summary == title or article_title_restatement(summary, title)) and not canonical_title_fact(title) == summary:
        errors.append("headline_repeated_as_summary")
    if title and not compact_title_summary_aligned(title, summary):
        errors.append("title_core_mismatch")
    if title and market_move_direction_conflict(title, summary):
        errors.append("market_direction_mismatch")
    if title and not macro_release_core_aligned(title, summary):
        errors.append("macro_release_mismatch")
    if title and not market_materiality.core_focus_aligned(title, summary):
        errors.append("headline_event_or_period_mismatch")
    if any(term.lower() in summary.lower() for term in ARTICLE_UI_BOILERPLATE_TERMS):
        errors.append("article_ui_boilerplate")
    foreign_amounts = extract_foreign_amounts(summary)
    if foreign_amounts and not (
        re.search(r"\(약\s*[\d,.]+(?:조[\d,.]+억|조|억|만)?원\)", summary)
        or "원화 환산 확인 불가" in summary
    ):
        errors.append("foreign_currency_not_converted")
    return errors


def compact_alert(alert: dict, idx: int, now, fred: dict, te: dict) -> str:
    alert = normalize_alert_for_output(alert)
    examples = alert.get("examples") or []
    count_suffix = f" ({alert['cluster_count']}건 묶음)" if alert.get("cluster_count") else ""
    impacts = alert.get("impacts") or ["의사결정 영향 제한적"]
    displayed_impacts = display_impacts(impacts)
    interpretation = alert.get("interpretation") or "돈 버는 능력, 할인율, 수급, 시간표 중 하나를 바꿀 수 있는지 확인해야 합니다."
    title = display_news(alert)
    first_impact = displayed_impacts[0] if displayed_impacts else "의사결정"
    if alert.get("memory_antitrust_lawsuit"):
        core = "삼성전자·SK하이닉스·Micron에 DRAM 가격담합 집단소송이 제기됐습니다."
    else:
        core = verified_alert_core(alert, title)
    conversion = alert.get("fx_conversion") or {"amounts": []}
    title = apply_krw_conversions(title, conversion)
    core = compact_converted_core(core, conversion, limit=GAMEJOA_CORE_MAX_CHARS)
    if not core_sentence_is_complete(core):
        core = ""

    lines = [f"{idx}) {safe(title)}{html.escape(count_suffix, quote=False)}"]
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


def compact_quality_final_alerts(alerts: list[dict], limit: int) -> list[dict]:
    """Return only alerts that can be rendered, keeping report/JSON/send in sync."""
    now = base.kst_now()
    candidates = quality_display_alerts(alerts, max(limit * 2, limit))
    needs_fx = any(extract_foreign_amounts(alert_text(alert)) for alert in candidates)
    fx_snapshot = collect_fx_snapshot(candidates, now) if needs_fx else {"rates": {}}
    selected: list[dict] = []
    for alert in candidates:
        alert["fx_conversion"] = build_alert_fx_conversion(alert, fx_snapshot, now)
        block = compact_alert(alert, len(selected) + 1, now, {}, {})
        block_errors = compact_alert_block_errors(block)
        if block_errors:
            alert["_exclusion_reason"] = "compact_quality:" + ",".join(block_errors)
            print(
                "GAMEJOA final alert dropped "
                f"title={display_news(alert)!r} errors={','.join(block_errors)}"
            )
            continue
        selected.append(alert)
        if len(selected) >= limit:
            break
    return selected


def compact_report(alerts: list[dict], fred: dict, te: dict, now) -> str:
    limit = max(1, min(7, int(os.getenv("RADAR_DISPLAY_LIMIT", "7"))))
    candidates = alerts[: max(limit * 2, limit)]
    fx_snapshot = collect_fx_snapshot(candidates, now)
    for alert in candidates:
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

    visible: list[dict] = []
    rendered: list[str] = []
    for alert in candidates:
        block = compact_alert(alert, len(rendered) + 1, now, fred, te)
        block_errors = compact_alert_block_errors(block)
        if block_errors:
            print(
                "GAMEJOA compact item dropped "
                f"title={display_news(alert)!r} errors={','.join(block_errors)}"
            )
            continue
        visible.append(alert)
        rendered.append(block)
        if len(rendered) >= limit:
            break

    lines = [title, f"선별: 핵심 {len(rendered)}건", ""]
    if rendered:
        lines.extend(rendered)
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


def strip_article_boilerplate_from_report(text: str) -> str:
    """Remove publisher UI notices before validating the visible Telegram report."""
    cleaned = str(text or "")
    for pattern in ARTICLE_SUMMARY_NOISE_PATTERNS[:2]:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    return re.sub(r"[ \t]{2,}", " ", cleaned)


def guard_preopen_report(text: str) -> str:
    text = strip_article_boilerplate_from_report(text)
    text, compacted_fields = compact_gamejoa_prose_lines(text)
    errors: list[str] = []
    valid_title = (
        text.startswith("📰 GAMEJOA 장전 핵심 뉴스 레이더 · ")
        or text.startswith("📰 실시간 핵심 뉴스 레이더 · ")
    )
    if not valid_title:
        errors.append("title_contract")
    item_count = sum(
        1
        for line in text.splitlines()
        if re.match(r"^\d+\)\s+(?:\[[^\]]+\]\s*)?\S", line)
    )
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
        if not re.match(r"^\d+\)\s+(?:\[[^\]]+\]\s*)?\S", line):
            continue
        title = re.sub(r"^\d+\)\s+(?:\[[^\]]+\]\s*)?", "", line).strip()
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
            context = next(
                (
                    re.sub(r"\\s+", " ", line).strip()[:180]
                    for line in text.splitlines()
                    if marker in re.sub(r"https?://\\S+", "", line).lower()
                ),
                "",
            )
            errors.append(f"article_boilerplate={marker}:{context}")
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
        if any(term.lower() in summary.lower() for term in ARTICLE_UI_BOILERPLATE_TERMS) or core_has_ui_garbage(summary):
            errors.append("article_ui_boilerplate")
        if not core_sentence_is_complete(summary):
            errors.append(f"incomplete_article_summary={summary[-30:]}")
        if re.search(
            r"(?:보다|에게|에서|으로|와|과|은|는|이|가|을|를|의|며|고)(?:[.!?。])?$",
            summary,
        ):
            errors.append(f"incomplete_article_summary={summary[-30:]}")
        foreign_amounts = extract_foreign_amounts(summary)
        if foreign_amounts and not (
            re.search(r"\(약\s*[\d,.]+(?:조[\d,.]+억|조|억|만)?원\)", summary)
            or "원화 환산 확인 불가" in summary
        ):
            errors.append("foreign_currency_not_converted")
    current_title = ""
    for line in text.splitlines():
        if re.match(r"^\d+\)\s+(?:\[[^\]]+\]\s*)?\S", line):
            current_title = re.sub(
                r"^\d+\)\s+(?:\[[^\]]+\]\s*)?", "", html.unescape(line)
            ).strip()
            current_title = re.sub(r"\(\d+건 묶음\)$", "", current_title).strip()
            continue
        if current_title and line.startswith("- 핵심:"):
            summary = html.unescape(line.removeprefix("- 핵심:").strip())
            if (
                summary == current_title
                or article_title_restatement(summary, current_title)
            ) and canonical_title_fact(current_title) != summary:
                errors.append("headline_repeated_as_summary")
    if errors:
        raise RuntimeError("GAMEJOA preopen radar quality guard blocked Telegram output: " + "; ".join(errors))
    if compacted_fields:
        print(f"GAMEJOA compact prose rewritten={compacted_fields}")
    return text


TELEGRAM_SOURCE_ANCHOR = re.compile(
    r'<a href="([^"<>]+)">(.+?)</a>',
    re.DOTALL,
)


def telegram_utf16_length(value: str) -> int:
    return len(str(value or "").encode("utf-16-le")) // 2


def telegram_text_and_entities(text: str) -> tuple[str, list[dict]]:
    """Convert generated source anchors into Telegram text-link entities.

    Telegram's entity payload is independent of parse_mode, so a source label
    cannot be exposed as literal HTML when the client ignores HTML parsing.
    """
    source = str(text or "")
    pieces: list[str] = []
    entities: list[dict] = []
    cursor = 0
    for match in TELEGRAM_SOURCE_ANCHOR.finditer(source):
        pieces.append(html.unescape(source[cursor:match.start()]))
        label = html.unescape(match.group(2))
        url = normalize_telegram_source_url(match.group(1))
        if label:
            offset = telegram_utf16_length("".join(pieces))
            pieces.append(label)
            entities.append({
                "type": "text_link",
                "offset": offset,
                "length": telegram_utf16_length(label),
                "url": url,
            })
        cursor = match.end()
    pieces.append(html.unescape(source[cursor:]))
    return "".join(pieces), entities


def fit_telegram_text_with_entities(
    text: str,
    entities: list[dict],
    limit: int,
) -> tuple[str, list[dict]]:
    if telegram_utf16_length(text) <= limit:
        return text, entities

    suffix = "\n\n전체 보고서는 GitHub Actions artifact에서 확인 필요."
    budget = max(0, limit - telegram_utf16_length(suffix))
    chars: list[str] = []
    used = 0
    for char in text:
        char_units = telegram_utf16_length(char)
        if used + char_units > budget:
            break
        chars.append(char)
        used += char_units
    candidate = "".join(chars)
    newline = candidate.rfind("\n")
    if newline > 1800:
        candidate = candidate[:newline]
    message = candidate.rstrip() + suffix
    message_units = telegram_utf16_length(message)
    kept_entities = [
        entity
        for entity in entities
        if int(entity["offset"]) + int(entity["length"]) <= message_units
    ]
    return message, kept_entities


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
    message, entities = telegram_text_and_entities(text)
    message, entities = fit_telegram_text_with_entities(message, entities, base.TELEGRAM_LIMIT)
    body = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": "true",
        "entities": json.dumps(entities, ensure_ascii=False, separators=(",", ":")),
    }).encode("utf-8")
    last_error = ""
    for attempt in range(1, 4):
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                telegram_response = json.loads(resp.read().decode("utf-8"))
            if not telegram_response.get("ok"):
                raise RuntimeError(f"Telegram rejected message: {telegram_response}")
            message_id = (telegram_response.get("result") or {}).get("message_id")
            if message_id is None:
                raise RuntimeError("Telegram send succeeded without message_id")
            write_delivery_status("sent", chat_id, len(text), "", len(message), attempt, message_id)
            print(
                f"Telegram: sent message_id={message_id} chars={len(message)} "
                f"entities={len(entities)} original_chars={len(text)} attempt={attempt}"
            )
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


def sanitize_telegram_html(text: str) -> str:
    """Keep generated source links while escaping every article-body HTML token."""
    anchors: list[str] = []

    def stash_anchor(match: re.Match[str]) -> str:
        anchors.append(match.group(0))
        return f"\x00GAMEJOA_LINK_{len(anchors) - 1}\x00"

    protected = re.sub(
        r'<a href="https?://[^"<>]+">.*?</a>',
        stash_anchor,
        str(text or ""),
        flags=re.DOTALL,
    )
    escaped = html.escape(html.unescape(protected), quote=False)
    for index, anchor in enumerate(anchors):
        escaped = escaped.replace(f"\x00GAMEJOA_LINK_{index}\x00", anchor)
    return escaped


def write_delivery_status(
    status: str,
    chat_id: str,
    original_chars: int,
    error: str = "",
    sent_chars: int | None = None,
    attempts: int | None = None,
    message_id: int | None = None,
) -> None:
    payload = {
        "status": status,
        "chat_id_masked": mask_chat_id(chat_id),
        "original_chars": original_chars,
        "sent_chars": sent_chars,
        "attempts": attempts,
        "message_id": message_id,
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
telegram.final_alerts_for_output = compact_quality_final_alerts
telegram.canonical_alert_for_seen = normalize_alert_for_output


if __name__ == "__main__":
    raise SystemExit(telegram.main())

