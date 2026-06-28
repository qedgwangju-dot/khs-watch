#!/usr/bin/env python3
"""Full-field compact Telegram renderer for the preopen news radar."""

from __future__ import annotations

import html
import os
import urllib.parse
import urllib.request

import gamejoa_preopen_news_radar_contract_runner as contract


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
    "Samsung Future Robotics reorganization Rainbow Robotics RB5-850 collaborative robot cobot Samsung production line factory automation deployment procurement order capex DART Reuters Bloomberg Yonhap",
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
        text = base.norm(f"{row.get('title')} {row.get('summary')} {row.get('publisher')} {row.get('source')}")
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
        text = base.norm(f"{row.get('title')} {row.get('summary')} {row.get('publisher')} {row.get('source')}")
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
        text = base.norm(f"{row.get('title')} {row.get('summary')} {row.get('publisher')} {row.get('source')}")
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


def related_text(alert: dict, fred: dict, te: dict) -> str:
    extra = []
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
        extra += ["Samsung Electronics", "Rainbow Robotics", "RB5-850", "협동로봇", "DART"]
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
        if alert.get("biotech_leadership_filter"):
            out += ["FDA", "PDUFA", "XBI", "IBB", "DFII10", "10Y TIPS"]
        if alert.get("robotics_execution_filter"):
            out += ["Samsung Electronics", "Rainbow Robotics", "RB5-850", "협동로봇", "DART"]
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
    if alert.get("grid_policy_delay"):
        return "북미 송전망 투자 정책 변수: 정부 승인·규제 지연 리스크"
    if alert.get("robotics_execution_filter"):
        return "삼성 로봇 실행 단계: 조직 재정비와 레인보우로보틱스 생산라인 자동화 체크"
    if alert.get("port_strike_risk"):
        return "메가프로젝트 일정: 미국 동부·걸프 항만 계약 만료/파업 리스크"
    if alert.get("china_stimulus_bulk"):
        return "중국 경기부양책: 철광석·석탄 물동량과 벌크선 운임 회복 기대"
    return alert.get("news") or "뉴스 제목 확인 불가"


def compact_alert(alert: dict, idx: int, now, fred: dict, te: dict) -> str:
    examples = alert.get("examples") or []
    count_suffix = f" ({alert['cluster_count']}건 묶음)" if alert.get("cluster_count") else ""
    status = alert.get("status") or ("공식 확인 전" if examples else "확인 불가")
    basis = alert.get("korea_basis") or ("외신/지역 뉴스 확산" if examples else "외신 확산")
    impacts = alert.get("impacts") or ["의사결정 영향 제한적"]
    paths = alert.get("paths") or ["정책 타임라인" if impact == "시간표" else impact for impact in impacts]
    sectors = alert.get("sectors") or ["영향 섹터 확인 불가"]
    published = alert.get("published") or ("여러 건" if examples else "확인 불가")
    reflection = alert.get("reflection") or "중간"
    counter = alert.get("counter") or "원문 세부조건과 공식 문서 확인 전 과대해석 가능"
    interpretation = alert.get("interpretation") or "돈 버는 능력, 할인율, 수급, 시간표 중 하나를 바꿀 수 있는지 확인해야 합니다."
    failed_signal = alert.get("failed_signal") or "관련 가격·수급·공식 후속 확인이 동행하지 않으면 단발성 뉴스"

    lines = [f"{idx}) [{safe(alert.get('importance'))} | {safe(status)}] {safe(display_news(alert))}{html.escape(count_suffix, quote=False)}"]
    if examples:
        lines.append("- 확인: " + safe(" / ".join(item["title"] for item in examples[:4])))
        source_text = source_summary(examples[:4])
    else:
        source_text = html_link(alert.get("publisher") or alert.get("source") or "출처 확인 불가", alert.get("link") or "")

    lines += [
        f"- 기준/타임라인: {safe(basis)} | 원천 {safe(published)} · 확산 {now:%H:%M KST}",
        f"- 영향/경로: {safe('·'.join(impacts))} | {safe('·'.join(paths))}",
        f"- 섹터/지표: {safe(', '.join(sectors))} | {safe(related_text(alert, fred, te))}",
        f"- 반영/반대: {safe(reflection)} | {safe(counter)}",
        f"- 해석: {safe(interpretation)}",
    ]
    semi_check = semiconductor_cycle_check(alert)
    policy_check = semiconductor_policy_check(alert)
    port_check = port_strike_check(alert)
    bulk_check = china_bulk_check(alert)
    grid_check = grid_policy_check(alert)
    biotech_check = biotech_leadership_check(alert)
    robotics_check = robotics_execution_check(alert)
    if policy_check:
        lines.append(f"- 반도체 정책 체크: {safe(policy_check)}")
    elif semi_check:
        lines.append(f"- 반도체 급락 체크: {safe(semi_check)}")
    if port_check:
        lines.append(f"- 메가프로젝트 일정 체크: {safe(port_check)}")
    if bulk_check:
        lines.append(f"- 중국 부양·벌크선 체크: {safe(bulk_check)}")
    if grid_check:
        lines.append(f"- 송전망 정책 체크: {safe(grid_check)}")
    if biotech_check:
        lines.append(f"- 바이오 주도주 체크: {safe(biotech_check)}")
    if robotics_check:
        lines.append(f"- 삼성 로봇 체크: {safe(robotics_check)}")
    lines += [
        f"- 실패 신호: {safe(failed_signal)}",
        f"- 출처: {source_text} · 조회 {now:%H:%M KST}",
        "",
    ]
    return "\n".join(lines)


def compact_report(alerts: list[dict], fred: dict, te: dict, now) -> str:
    limit = max(1, min(7, int(os.getenv("RADAR_DISPLAY_LIMIT", "5"))))
    visible = telegram.display_alerts(alerts, limit)
    title = f"장전 핵심 뉴스 레이더 · {now:%Y년 %m월 %d일} · 06:30"
    lines = [title, f"조회: {now:%Y-%m-%d %H:%M KST}", f"선별: 핵심 {len(visible)}건", ""]
    if visible:
        for idx, alert in enumerate(visible, 1):
            lines.append(compact_alert(alert, idx, now, fred, te))
        changed = "·".join(visible[0].get("impacts") or ["명확한 변화 없음"])
    else:
        lines += ["장전 고충격 뉴스 직접 확인 없음", ""]
        changed = "명확한 변화 없음"
    lines += [
        "💡 06:30 장전 뉴스 코멘트",
        f"오늘 핵심 변화는 `{safe(changed)}`입니다. 한국장에서는 관련 해외 티커 반응과 국내 수급 확산 여부를 먼저 확인합니다.",
        f"할인율: {safe(telegram.compact_real_yield(fred, te))}",
        "06:50 투자기상도에서 수치·수급·테마와 재확인 필요.",
        "",
        "투자 조언이 아닌 참고용 뉴스 브리핑입니다.",
    ]
    return "\n".join(lines).strip() + "\n"


def send_telegram(text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("Telegram: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing")
        return
    body = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text[:base.TELEGRAM_LIMIT],
        "disable_web_page_preview": "true",
        "parse_mode": "HTML",
    }).encode("utf-8")
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body, method="POST")
    with urllib.request.urlopen(req, timeout=25) as resp:
        resp.read()
    print("Telegram: sent")


telegram.compact_report = compact_report
telegram.send_telegram = send_telegram


if __name__ == "__main__":
    raise SystemExit(telegram.main())
