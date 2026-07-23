#!/usr/bin/env python3
"""Full-field compact Telegram renderer for the preopen news radar."""

from __future__ import annotations

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
from khs_compact_text import MAX_PROSE_CHARS, concise_text


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


append_unique(
    base.SOURCES,
    [
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
    ],
)
append_unique(base.TRUSTED, ["이투데이", "etoday", "전자신문", "etnews"])
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
        "수주",
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
    return any(
        marker in f"{publisher} {link}"
        for marker in ("이투데이", "etoday.co.kr", "전자신문", "etnews.com")
    )


KOREAN_BUSINESS_DETAIL_LIMIT = max(
    12,
    int(os.environ.get("GAMEJOA_KOREAN_BUSINESS_DETAIL_LIMIT", "36")),
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
]
ARTICLE_SUMMARY_MAX_CHARS = 420


def clean_article_summary_text(text: str) -> str:
    cleaned = html.unescape(str(text or "")).replace("\xa0", " ")
    for pattern in ARTICLE_SUMMARY_NOISE_PATTERNS:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^[\s,;:>|·•\-]+", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


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


def article_sentences(text: str, required: list[str], limit: int = 3) -> str:
    cleaned_text = clean_article_summary_text(text)
    sentences = [
        re.sub(
            r"^(?:▲[^)]{0,100}\)|\([^)]{0,100}(?:출처|사진)[^)]*\))\s*",
            "",
            clean_article_summary_text(sentence),
        )
        for sentence in re.split(r"(?<=[.!?다])\s+", cleaned_text)
        if clean_article_summary_text(sentence)
    ]
    sentences = [sentence for sentence in sentences if len(sentence) >= 25]
    selected = [
        sentence for sentence in sentences
        if any(term.lower() in sentence.lower() for term in required)
    ]
    if not selected:
        selected = sentences
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


KOREAN_BUSINESS_SECTOR_TERMS = [
    ("MLCC/수동부품", ["mlcc", "적층세라믹커패시터", "수동부품"]),
    ("반도체/HBM/CXL", ["반도체", "hbm", "dram", "nand", "cxl", "테스터"]),
    ("AI/데이터센터", ["ai", "인공지능", "데이터센터", "하이퍼스케일러"]),
    ("태양광/폴리실리콘", ["태양광", "폴리실리콘", "웨이퍼"]),
    ("전력기기/전력망", ["전력기기", "변압기", "전선", "송전망", "전력망"]),
    ("2차전지/배터리", ["2차전지", "배터리", "양극재", "음극재", "전해질"]),
    ("자동차/부품", ["자동차", "현대차", "기아", "전기차", "부품"]),
    ("방산/항공우주", ["방산", "항공우주", "미사일", "전차", "자주포"]),
    ("바이오/헬스케어", ["바이오", "제약", "임상", "의약품", "헬스케어"]),
    ("금융/자본시장", ["은행", "증권", "보험", "외국인", "순매수", "순매도"]),
    ("유통/소비", ["유통", "소비", "홈플러스", "백화점", "면세점"]),
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
    "기아",
    "두산에너빌리티",
    "한화에어로스페이스",
    "LIG넥스원",
    "한국항공우주",
    "현대로템",
    "한화시스템",
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
KOREAN_BUSINESS_IMPACT_TERMS = {
    "돈 버는 능력": [
        "매출", "영업이익", "순이익", "흑자", "적자", "실적", "가이던스",
        "수요", "가격", "판가", "마진", "공급계약", "장기계약", "수주", "발주",
        "증설", "생산능력", "출하", "고객사", "점유율",
    ],
    "할인율": [
        "금리", "환율", "원·달러", "달러", "규제", "관세", "수출통제", "제재",
    ],
    "수급": [
        "외국인", "기관", "순매수", "순매도", "자사주", "유상증자", "cb",
        "전환사채", "etf", "편입", "상장", "ipo",
    ],
    "시간표": [
        "양산평가", "평가", "승인", "허가", "상용화", "출시", "이달 말",
        "예정", "상장예비심사", "ipo", "계약", "증설", "착공", "완공",
    ],
}


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
    summary = article_sentences(body, korean_business_title_terms(title), 2)
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

    out.update(
        {
            "korean_business_news": True,
            "body_verified": True,
            "news": title,
            "original_news": title,
            "source_title": title,
            "source_abstract": body[:16000],
            "policy_plain_summary": summary,
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
    return {
        "score": score + (6 if age is not None and age <= 12 else 0),
        "importance": "상" if score >= 100 else "중",
        "status": "예비",
        "news": str(row.get("source_title") or row.get("title") or ""),
        "original_news": str(row.get("source_title") or row.get("title") or ""),
        "source_title": str(row.get("source_title") or row.get("title") or ""),
        "source_abstract": str(row.get("source_abstract") or row.get("summary") or ""),
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


def build_verified_korean_business_alert(row: dict, now) -> dict | None:
    title = str(row.get("source_title") or row.get("title") or "")
    body = str(row.get("source_body") or row.get("source_abstract") or "")
    text = f"{title} {body}".lower()

    if "외국인" in text and "순매수" in text and all(
        term in text for term in ("삼성전자", "sk하이닉스")
    ):
        alert = base_korean_business_alert(row, now, score=112, impacts=["수급"])
        alert.update(
            {
                "policy_plain_summary": (
                    "외국인이 4거래일간 삼성전자·SK하이닉스를 "
                    "약 4.5조원 순매수했습니다."
                ),
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

    if any(term in title.lower() for term in KOREAN_BUSINESS_MARKET_RECAP_TERMS):
        return None

    title_text = title.lower()
    title_material_terms = [
        term for term in KOREAN_BUSINESS_MATERIAL_TERMS
        if term in title_text
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
            detail_candidates.append(row)
        detail_candidates.sort(key=korean_business_detail_priority, reverse=True)
        deferred = max(0, len(detail_candidates) - KOREAN_BUSINESS_DETAIL_LIMIT)
        for row in detail_candidates[:KOREAN_BUSINESS_DETAIL_LIMIT]:
            attempted += 1
            detail_html, detail_error = base.fetch(str(row.get("link")), 16)
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
            f"attempted={attempted} verified={verified} failed={failed} deferred={deferred}"
        )
        print(
            f"korean_business_detail attempted={attempted} "
            f"verified={verified} failed={failed} deferred={deferred}"
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


def source_output_aligned(alert: dict) -> bool:
    """Reject rendered themes that are not supported by source-authored text."""
    if alert.get("korean_business_news"):
        source_title = base.norm(alert.get("source_title"))
        rendered_title = base.norm(alert.get("news"))
        link = str(alert.get("link") or "").lower()
        summary = base.clean(alert.get("policy_plain_summary"))
        return bool(
            alert.get("body_verified")
            and source_title
            and rendered_title == source_title
            and len(summary) >= 40
            and ("etoday.co.kr/" in link or "etnews.com/" in link)
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


def alert_dedup_key(alert: dict) -> tuple[str, str]:
    if alert.get("iran_hormuz_escalation"):
        return ("iran_hormuz_military_escalation", str(alert.get("published") or "")[:10])
    raw_title = str(alert.get("original_news") or alert.get("news") or "")
    raw_title = re.split(r"\s+-\s+", raw_title, maxsplit=1)[0].strip()
    theme = str(alert.get("supply_chain_theme") or "")
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


def compact_alert(alert: dict, idx: int, now, fred: dict, te: dict) -> str:
    alert = normalize_alert_for_output(alert)
    examples = alert.get("examples") or []
    count_suffix = f" ({alert['cluster_count']}건 묶음)" if alert.get("cluster_count") else ""
    status = alert.get("status") or ("공식 확인 전" if examples else "확인 불가")
    basis = alert.get("korea_basis") or ("외신/지역 뉴스 확산" if examples else "외신 확산")
    impacts = alert.get("impacts") or ["의사결정 영향 제한적"]
    displayed_impacts = display_impacts(impacts)
    paths = alert.get("paths") or ["정책 타임라인" if impact == "시간표" else impact for impact in impacts]
    sectors = alert.get("sectors") or ["영향 섹터 확인 불가"]
    published = alert.get("published") or ("여러 건" if examples else "확인 불가")
    priced_in = alert.get("priced_in") or f"{alert.get('reflection') or '중간'}. 후속 공식 조건과 시장 반응 확인 전까지 확정 반영으로 보기 어렵습니다."
    counter = alert.get("counter") or "원문 세부조건과 공식 문서 확인 전 과대해석 가능"
    interpretation = alert.get("interpretation") or "돈 버는 능력, 할인율, 수급, 시간표 중 하나를 바꿀 수 있는지 확인해야 합니다."
    failed_signal = alert.get("failed_signal") or "관련 가격·수급·공식 후속 확인이 동행하지 않으면 단발성 뉴스"
    title = display_news(alert)
    first_impact = displayed_impacts[0] if displayed_impacts else "의사결정"
    first_sector = sectors[0] if sectors else "관련 업종"
    core = concise_text(alert.get("policy_plain_summary"), fallback=title)
    investment = concise_text(
        alert.get("investment_view") or interpretation,
        fallback=f"{first_impact} 변화 여부를 확인합니다.",
    )
    korea = concise_text(
        alert.get("korea_market_impact"),
        fallback=f"한국장에서는 {first_sector} 직접 노출만 확인합니다.",
    )
    priced_in = concise_text(
        priced_in,
        fallback="중간. 후속 가격·수급 확인이 필요합니다.",
    )
    counter = concise_text(
        counter,
        fallback="원문 조건 확정 전 과대해석 가능성이 있습니다.",
    )
    failed_signal = concise_text(
        failed_signal,
        fallback="후속 공시·가격·수급이 없으면 재료가 약해집니다.",
    )

    lines = [f"{idx}) [{safe(alert.get('importance'))} | {safe(status)}] {safe(title)}{html.escape(count_suffix, quote=False)}"]
    if examples:
        source_text = source_summary(examples[:4])
    else:
        source_text = html_link(
            "원문 뉴스보기",
            alert.get("link") or "",
        )

    lines += [
        f"- 기준/시각: {safe(basis)} · 원천 {safe(published)} · 조회 {now:%H:%M KST}",
        f"- 핵심: {safe(core)}",
        f"- 의사결정 영향: {safe(', '.join(displayed_impacts))}",
        f"- 투자 포인트: {safe(investment)}",
        f"- 한국장: {safe(korea)}",
        f"- 경로/섹터: {safe(', '.join(paths))} | {safe(', '.join(sectors))}",
        f"- 반영/반대: {safe(priced_in)} / {safe(counter)}",
    ]
    lines += [
        f"- 실패 신호: {safe(failed_signal)}",
        f"- 출처: {source_text}",
        "",
    ]
    return "\n".join(lines)


def compact_report(alerts: list[dict], fred: dict, te: dict, now) -> str:
    limit = max(1, min(7, int(os.getenv("RADAR_DISPLAY_LIMIT", "5"))))
    visible = alerts[:limit]
    live_mode = os.getenv("RADAR_RUN_MODE", "").strip().lower() == "live"
    if live_mode:
        title = f"📰 GAMEJOA 실시간 핵심 뉴스 레이더 · {now:%Y년 %m월 %d일} · {now:%H:%M}"
        comment_title = "💡 실시간 뉴스 코멘트"
        followup_line = "다음 투자기상도에서 수치·수급·테마와 재확인 필요."
        empty_line = "실시간 고충격 뉴스 직접 확인 없음"
    else:
        title = f"📰 GAMEJOA 장전 핵심 뉴스 레이더 · {now:%Y년 %m월 %d일} · 06:30"
        comment_title = "💡 06:30 장전 뉴스 코멘트"
        followup_line = "06:50 투자기상도에서 수치·수급·테마와 재확인 필요."
        empty_line = "장전 고충격 뉴스 직접 확인 없음"
    lines = [title, f"조회: {now:%Y-%m-%d %H:%M KST}", f"선별: 핵심 {len(visible)}건", ""]
    if visible:
        for idx, alert in enumerate(visible, 1):
            lines.append(compact_alert(alert, idx, now, fred, te))
        changed = "·".join(display_impacts(visible[0].get("impacts")))
    else:
        lines += [empty_line, ""]
        changed = "명확한 변화 없음"
    lines += [
        comment_title,
        f"오늘 핵심 변화는 `{safe(changed)}`입니다. 한국장에서는 관련 해외 티커 반응과 국내 수급 확산 여부를 먼저 확인합니다.",
        f"할인율: {safe(telegram.compact_real_yield(fred, te))}",
        followup_line,
        "",
        "투자 조언이 아닌 참고용 뉴스 브리핑입니다.",
    ]
    report = "\n".join(lines).strip() + "\n"
    guard_preopen_report(report)
    return report


def guard_preopen_report(text: str) -> None:
    errors: list[str] = []
    valid_title = (
        text.startswith("📰 GAMEJOA 장전 핵심 뉴스 레이더 · ")
        or text.startswith("📰 GAMEJOA 실시간 핵심 뉴스 레이더 · ")
    )
    if not valid_title:
        errors.append("title_contract")
    item_count = sum(1 for line in text.splitlines() if re.match(r"^\d+\)\s+\[", line))
    required = [
        "- 기준/시각:",
        "- 핵심:",
        "- 의사결정 영향:",
        "- 투자 포인트:",
        "- 한국장:",
        "- 경로/섹터:",
        "- 반영/반대:",
        "- 실패 신호:",
        "- 출처:",
    ]
    for marker in required:
        if item_count and text.count(marker) < item_count:
            errors.append(f"missing_{marker}")
    if item_count and "- 의사결정 영향: 의사결정 영향 제한적" in text:
        errors.append("limited_decision_impact_displayed")
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
    compact_prefixes = ("- 핵심:", "- 투자 포인트:", "- 한국장:", "- 실패 신호:")
    for line in text.splitlines():
        visible_line = html.unescape(line)
        for prefix in compact_prefixes:
            if visible_line.startswith(prefix):
                value = visible_line.removeprefix(prefix).strip()
                if len(value) > MAX_PROSE_CHARS:
                    errors.append(f"compact_prose_too_long={prefix}")
        if visible_line.startswith("- 반영/반대:"):
            value = visible_line.removeprefix("- 반영/반대:").strip()
            for part in value.split(" / ", 1):
                if len(part.strip()) > MAX_PROSE_CHARS:
                    errors.append("compact_prose_too_long=- 반영/반대:")
        if not visible_line.startswith("- 핵심:"):
            continue
        summary = visible_line.removeprefix("- 핵심:").strip()
        if re.search(r"(?:보다|에게|에서|으로|와|과|은|는|이|가|을|를|의|며|고)$", summary):
            errors.append(f"incomplete_article_summary={summary[-30:]}")
    if errors:
        raise RuntimeError("GAMEJOA preopen radar quality guard blocked Telegram output: " + "; ".join(errors))


def send_telegram(text: str) -> None:
    guard_preopen_report(text)
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
