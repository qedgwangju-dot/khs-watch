#!/usr/bin/env python3
"""Semiconductor supply-chain source overlay for the GAMEJOA preopen radar."""

from __future__ import annotations

import datetime as dt
import re

import gamejoa_preopen_news_radar_memory_antitrust_runner as current


runner = current.runner
base = current.base
contract = current.contract
telegram = current.telegram


def append_unique(seq: list, values: list) -> None:
    for value in values:
        if value not in seq:
            seq.append(value)


append_unique(base.SOURCES, [
    ("TrendForce semiconductor RSS", "https://www.trendforce.com/feed/Semiconductors.html", "official"),
    ("ServeTheHome RSS", "https://www.servethehome.com/feed/", "trusted"),
])

append_unique(base.QUERIES, [
    (
        "TrendForce HBM4 계약가",
        "site:trendforce.com HBM4 contract price hikes 2027 supply negotiations pricing power TrendForce",
    ),
    (
        "TrendForce 노트북/PC 수요",
        "site:trendforce.com/presscenter/news Apple MacBook notebook shipments 13.6 memory cost consumer demand TrendForce",
    ),
    (
        "TrendForce 수동부품/MLCC",
        "site:trendforce.com/news YAGEO Nichicon MLCC aluminum electrolytic capacitor price hike X6S AI ASIC TrendForce",
    ),
    (
        "반도체 소재가스/CO2",
        "high-purity CO2 Samsung SK Hynix advanced semiconductor packaging HBM 3D NAND The Elec TrendForce Wccftech",
    ),
    (
        "Intel 18A/애플 듀얼파운드리",
        "Intel 18A wafer-to-wafer yield 12000 15000 wafers Apple A20 iPhone 18 Intel foundry Tom's Hardware Wccftech",
    ),
    (
        "HBM 대체 메모리/LPDDR5X",
        "AMD Versal Premium Gen 2 LPDDR5X HBM shortage memory on package ServeTheHome",
    ),
    (
        "PC/노트북 부품 원가",
        "global PC notebook shipments memory SSD price surge DRAM NAND demand TrendForce Tom's Hardware",
    ),
])

append_unique(base.TRUSTED, [
    "trendforce",
    "tom's hardware",
    "tomshardware",
    "servethehome",
    "digitimes",
    "the elec",
])

append_unique(base.TERMS, [
    "18a",
    "18a-p",
    "a20",
    "aluminum electrolytic capacitor",
    "capacitor",
    "capacitors",
    "co2",
    "consumer demand",
    "contract price hikes",
    "contract price surge",
    "foundry",
    "high-purity co2",
    "hbm4",
    "hbm suppliers",
    "iphone 18",
    "lpddr5x",
    "macbook",
    "mlcc",
    "notebook shipments",
    "passive component",
    "pc shipments",
    "pricing power",
    "price hikes",
    "supply negotiations",
    "ssd price",
    "versal",
    "wafer-to-wafer",
    "yageo",
])

for idx, (label, keys) in enumerate(base.SECTORS):
    if label == "반도체/AI":
        merged = list(keys)
        append_unique(merged, [
            "18a",
            "18a-p",
            "co2",
            "contract price surge",
            "foundry",
            "high-purity co2",
            "hbm4",
            "hbm suppliers",
            "lpddr5x",
            "mlcc",
            "passive component",
            "versal",
            "wafer-to-wafer",
        ])
        base.SECTORS[idx] = (label, merged)
        break

SUPPLY_FLAG = "semiconductor_supply_chain_watch"
TRENDFORCE_RESEARCH_URL = "https://www.trendforce.com/research/category/selected_topics/tri_semiconductors"
TRENDFORCE_RESEARCH_MAX_AGE_DAYS = int(base.os.getenv("RADAR_TRENDFORCE_RESEARCH_MAX_AGE_DAYS", "3"))


def has_any(text: str, terms: list[str]) -> bool:
    return any(base.has(text, term) for term in terms)


def source_text(row: dict) -> str:
    return base.norm(f"{row.get('publisher')} {row.get('link')}")


def parse_trendforce_research_items(text: str, now) -> list[dict]:
    body = base.clean(text)
    rows: list[dict] = []
    if not has_any(base.norm(body), ["hbm4", "2027 hbm", "contract price hikes", "pricing power"]):
        return rows

    title_match = re.search(
        r"(New HBM Market Outlook[:：]\s*HBM Suppliers Seize Pricing Power as AI Demand Fuels Explosive Contract Price Surge)",
        body,
        re.I,
    )
    date_match = re.search(
        r"New HBM Market Outlook[:：].{0,220}?(\d{4}/\d{2}/\d{2})",
        body,
        re.I,
    )
    summary_match = re.search(
        r"(As 2027 HBM4 supply negotiations launch in 2Q26, TrendForce expects suppliers to push through substantial contract price hikes,"
        r".{0,360}?manufacturing costs\.)",
        body,
        re.I,
    )
    link_match = re.search(r'href=["\']([^"\']*RP260527UC[^"\']*)["\']', text, re.I)

    source_date = None
    if date_match:
        try:
            parsed = dt.datetime.strptime(date_match.group(1), "%Y/%m/%d")
            source_date = parsed.replace(tzinfo=base.KST)
        except ValueError:
            source_date = None

    if not source_date:
        return rows
    age_days = (now - source_date).total_seconds() / 86400
    if age_days > TRENDFORCE_RESEARCH_MAX_AGE_DAYS:
        return rows

    link = "https://www.trendforce.com/research/download/RP260527UC"
    if link_match:
        candidate = link_match.group(1)
        link = candidate if candidate.startswith("http") else f"https://www.trendforce.com{candidate}"

    title = title_match.group(1) if title_match else "New HBM Market Outlook: HBM Suppliers Seize Pricing Power as AI Demand Fuels Explosive Contract Price Surge"
    summary = summary_match.group(1) if summary_match else (
        "As 2027 HBM4 supply negotiations launch in 2Q26, TrendForce expects suppliers to push through "
        "substantial contract price hikes, reflecting acute supply-demand imbalance and rising next-generation manufacturing costs."
    )
    rows.append({
        "source": "TrendForce semiconductor research",
        "layer": "official",
        "publisher": "TrendForce",
        "title": title,
        "link": link,
        "summary": summary,
        "published": source_date,
        "source_published": source_date,
    })
    return rows


def install_fast_collect_items() -> None:
    def collect_items(now):
        rows, notes = base.collect_items(now)
        existing_links = {row.get("link") for row in rows if row.get("link")}
        research_text, research_err = base.fetch(TRENDFORCE_RESEARCH_URL)
        if research_err:
            notes.append(f"TrendForce semiconductor research: 확인 불가 ({research_err})")
        else:
            research_rows = [
                row for row in parse_trendforce_research_items(research_text or "", now)
                if row.get("link") not in existing_links
            ]
            rows.extend(research_rows)
            existing_links.update(row.get("link") for row in research_rows if row.get("link"))
            notes.append(f"TrendForce semiconductor research: {len(research_rows)}건")

        query = getattr(current, "MEMORY_ANTITRUST_QUERY", None)
        is_memory_antitrust_row = getattr(current, "is_memory_antitrust_row", None)
        if not query or not is_memory_antitrust_row:
            return rows, notes
        text, err = base.fetch(base.news_search_url(query[1]))
        if err:
            notes.append(f"Trusted news {query[0]}: 확인 불가 ({err})")
            return rows, notes
        parsed = [
            row for row in base.parse_rss(text or "", f"Trusted news {query[0]}", "trusted")
            if base.fresh(row, now) and is_memory_antitrust_row(row) and row.get("link") not in existing_links
        ]
        notes.append(f"Trusted news {query[0]}: {len(parsed)}건")
        rows.extend(parsed)
        return rows, notes

    contract.strict.collect_items = collect_items


def supply_theme(row: dict) -> str | None:
    text = base.source_content_text(row)
    src = source_text(row)
    if "trendforce" in src and has_any(text, ["hbm4", "hbm suppliers", "2027 hbm"]) and has_any(text, ["contract price", "contract price hikes", "contract price surge", "price hikes", "pricing power", "supply negotiations"]):
        return "hbm4_contract_price"
    if "trendforce" in src and has_any(text, ["macbook", "notebook shipments", "13.6"]):
        return "notebook_demand"
    if "trendforce" in src and has_any(text, ["ai server demand", "memory prices", "3q26", "dram", "nand"]) and has_any(text, ["support", "moderate", "consumer demand", "high base"]):
        return "memory_price_cycle"
    if has_any(text, ["mlcc", "passive component", "capacitor", "capacitors", "yageo", "nichicon"]) and has_any(text, ["price", "hike", "increase", "shortage", "lead time", "x6s"]):
        return "passive_components"
    if has_any(text, ["high-purity co2", "co2 shortage", "carbon dioxide"]) and has_any(text, ["samsung", "sk hynix", "semiconductor", "advanced packaging", "hbm", "3d nand"]):
        return "co2_materials"
    if has_any(text, ["intel 18a", "18a-p", "wafer-to-wafer", "bluefin", "a20", "iphone 18"]) and has_any(text, ["yield", "foundry", "apple", "wafers", "process"]):
        return "intel_18a"
    if has_any(text, ["versal premium", "lpddr5x", "memory on package"]) and has_any(text, ["amd", "hbm", "shortage", "adaptive soc"]):
        return "hbm_substitution"
    if has_any(text, ["pc shipments", "notebook shipments", "ssd price", "memory price"]) and has_any(text, ["decline", "drop", "surge", "demand", "shipments"]):
        return "pc_cost_demand"
    if has_any(text, ["sk hynix", "samsung", "micron"]) and has_any(text, ["antitrust", "class-action", "class action", "price fixing", "collusion", "lawsuit", "dram"]):
        return "memory_antitrust"
    if has_any(text, ["sk hynix", "cheongju", "yongin", "south korean operations"]) and has_any(text, ["invest", "investment", "nand", "dram", "semiconductor cluster"]):
        return "korea_memory_capex"
    return None


THEME = {
    "hbm4_contract_price": {
        "news": "TrendForce, 2027년 HBM4 계약가 대폭 인상 전망",
        "status": "확정",
        "importance": "상",
        "score": 122,
        "impacts": ["매출·마진·현금흐름", "수급", "시간표"],
        "paths": ["이익", "공급·수요", "계약 가시성", "밸류체인"],
        "sectors": ["HBM4/DRAM 가격", "SK하이닉스·삼성전자·Micron", "HBM 장비·소재·패키징"],
        "summary": "TrendForce 리서치 기준 2027년 HBM4 공급 협상이 2026년 2분기에 시작됐고, 공급 부족과 차세대 제조비 상승을 반영해 공급사가 큰 폭의 계약가 인상을 추진할 수 있다는 전망입니다.",
        "view": "HBM4 ASP와 공급자 가격결정력은 SK하이닉스·삼성전자·Micron의 2027년 HBM 매출, 마진, 장비·소재 발주 기대를 동시에 건드립니다.",
        "korea": "한국장에서는 SK하이닉스 HBM4 선점, 삼성전자 HBM4 고객 인증, 한미반도체 등 HBM 패키징·검사·소재 밸류체인, Micron/NVDA/AVGO 반응을 같이 확인합니다.",
        "priced": "중간. HBM 슈퍼사이클은 이미 상당 부분 주가에 반영됐지만, 2027년 HBM4 계약가가 기존 기대보다 크게 올라가면 내년 이후 EPS 추정이 다시 바뀔 수 있습니다.",
        "counter": "TrendForce 리서치 전망과 협상 신호이지 실제 장기공급계약 서명이나 확정 ASP 공시는 아닙니다. NVIDIA·ASIC 고객 배정, 수율, 베이스다이, 경쟁사 인증 상황에 따라 실제 가격 인상 폭은 달라질 수 있습니다.",
        "failure": "SK하이닉스·삼성전자·Micron의 HBM4 공급계약, 고객 인증, 2027년 물량·ASP, DRAM 웨이퍼 배분, HBM 장비 발주가 후속 확인되지 않으면 기대감 재료로 약해집니다.",
    },
    "notebook_demand": {
        "news": "TrendForce, 맥북 가격 인상 여파로 2026년 노트북 수요 둔화 전망",
        "status": "확정",
        "importance": "상",
        "score": 108,
        "impacts": ["매출·마진·현금흐름", "시간표"],
        "paths": ["공급·수요", "이익", "밸류체인"],
        "sectors": ["노트북/PC 밸류체인", "디스플레이/패널", "메모리/부품"],
        "summary": "TrendForce가 맥북 전 라인업 가격 인상, 부품 원가 부담, 소비자 가격 저항을 근거로 2026년 글로벌 노트북 출하 둔화를 제시한 사안입니다.",
        "view": "PC 수요 둔화는 패널, 메모리, SSD, PMIC, 부품 업체의 물량 가정과 마진을 동시에 흔듭니다.",
        "korea": "한국장에서는 삼성전자·SK하이닉스의 PC DRAM/NAND 믹스, 디스플레이·부품주의 출하량 전망, 소비 IT 밸류체인 수급을 확인합니다.",
        "priced": "중간. AI 서버/HBM 강세는 이미 반영돼도 소비 IT 둔화가 별도로 가격에 반영되는지는 확인이 필요합니다.",
        "counter": "애플 자체 출하는 상대적으로 견조할 수 있고, AI 서버 수요가 메모리 가격을 지지하면 한국 메모리주의 하방은 제한될 수 있습니다.",
        "failure": "PC DRAM/NAND 가격, 패널 출하, 주요 PC 업체 가이던스가 악화되지 않으면 소비 IT 둔화 재료는 약해집니다.",
    },
    "passive_components": {
        "news": "TrendForce, MLCC·알루미늄 콘덴서 가격 인상/쇼티지 신호",
        "status": "예비",
        "importance": "상",
        "score": 110,
        "impacts": ["매출·마진·현금흐름", "수급", "시간표"],
        "paths": ["이익", "공급·수요", "밸류체인"],
        "sectors": ["수동부품/MLCC/콘덴서", "AI 서버 부품", "전자부품 밸류체인"],
        "summary": "AI ASIC·서버 보드 고사양화로 X6S MLCC와 알루미늄 전해 콘덴서 수요가 늘고, YAGEO·Nichicon 등 가격 인상 신호가 확인되는 구간입니다.",
        "view": "수동부품 가격 인상은 부품사의 마진에는 호재지만, 서버·전장·소비전자 조립사의 BOM 비용에는 부담입니다.",
        "korea": "한국장에서는 MLCC/콘덴서 직접 노출, AI 서버 부품, 전장 부품, 삼성전기류 수동부품 밸류체인과 세트업체 원가 부담을 나눠 봅니다.",
        "priced": "낮음~중간. HBM과 전력기기보다 덜 주목받아 단기 수급이 붙을 여지가 있지만 일부 대만 업체는 먼저 반응했을 수 있습니다.",
        "counter": "TrendForce News가 인용보도 기반인 경우 확정 계약·공급부족 수치·국내 기업 직접 노출 확인 전에는 과대해석 위험이 있습니다.",
        "failure": "리드타임, 실제 판가, 국내 업체 수주·ASP, 대만 수동부품주 반응이 동행하지 않으면 테마성으로 약해집니다.",
    },
    "memory_price_cycle": {
        "news": "TrendForce, AI 서버가 메모리 가격 지지하나 소비 수요 둔화 체크",
        "status": "확정",
        "importance": "상",
        "score": 108,
        "impacts": ["매출·마진·현금흐름", "수급", "시간표"],
        "paths": ["이익", "공급·수요", "밸류체인"],
        "sectors": ["DRAM/NAND 가격 사이클", "AI 서버/HBM", "소비 IT 수요"],
        "summary": "TrendForce가 AI 서버 수요는 메모리 가격을 지지하지만 소비 수요 둔화와 높은 기저로 상승폭이 둔화될 수 있다고 본 사안입니다.",
        "view": "메모리 주가는 판가 상승만큼 물량·믹스·재고가 중요합니다. AI 서버 강세와 소비 IT 약세 중 어느 쪽이 이익 추정에 더 큰지 봐야 합니다.",
        "korea": "한국장에서는 삼성전자·SK하이닉스의 HBM/서버 DRAM 믹스, PC·모바일 DRAM/NAND 가격, 재고와 고객사 주문을 같이 확인합니다.",
        "priced": "중간. HBM 강세는 상당 부분 반영됐지만 소비 메모리 가격 둔화가 확인되면 해석이 바뀔 수 있습니다.",
        "counter": "AI 서버 수요가 예상보다 강하거나 공급 제약이 지속되면 소비 수요 둔화가 전체 메모리 업황을 꺾지 못할 수 있습니다.",
        "failure": "DRAM/NAND 계약가, HBM 리드타임, MU/삼성전자/SK하이닉스 반응이 동행하지 않으면 단발성 리서치로 약화됩니다.",
    },
    "co2_materials": {
        "news": "반도체용 고순도 CO₂ 재고 부족: 삼성전자·SK하이닉스 소재 리스크",
        "status": "예비",
        "importance": "상",
        "score": 112,
        "impacts": ["매출·마진·현금흐름", "수급", "시간표"],
        "paths": ["공급·수요", "원가", "밸류체인", "지정학 리스크"],
        "sectors": ["반도체 소재가스/고순도 CO2", "HBM/첨단패키징", "삼성전자/SK하이닉스 밸류체인"],
        "summary": "고순도 CO₂는 첨단 반도체 세정 공정에 쓰이는 소재이고, 재고가 한 달 미만으로 낮아졌다는 보도는 HBM·3D NAND 생산 원가와 일정 리스크를 건드립니다.",
        "view": "아직 생산 차질 확정은 아니지만 장기화되면 소재 조달비와 첨단 패키징 단가, 메모리 공급 타이트닝 기대를 바꿀 수 있습니다.",
        "korea": "한국장에서는 삼성전자·SK하이닉스, 반도체 특수가스·소재, 정유·석화 부산물 공급망, HBM/패키징 관련주를 분리 확인합니다.",
        "priced": "낮음. 소재 병목은 공식 생산 차질 전까지 시장이 늦게 반영하는 경우가 많습니다.",
        "counter": "TrendForce/Wccftech가 The Elec 등 보도 인용에 의존하고 있고, 현재 생산 차질은 확인되지 않았습니다.",
        "failure": "재고가 정상화되거나 삼성전자·SK하이닉스 생산·가격·조달 공시/후속 보도가 없으면 단기 소재 테마로 끝납니다.",
    },
    "intel_18a": {
        "news": "Intel 18A 수율 개선·애플 듀얼 파운드리 가능성 체크",
        "status": "공식 확인 전",
        "importance": "중",
        "score": 94,
        "impacts": ["밸류에이션/할인율", "수급", "시간표"],
        "paths": ["밸류체인", "수급", "정책 타임라인"],
        "sectors": ["Intel Foundry/18A", "파운드리/첨단공정", "반도체 장비·소재"],
        "summary": "Intel 18A 웨이퍼 간 수율 변동성 개선 보도와 애플 A20/아이폰 18 듀얼 파운드리 루머가 동시에 도는 구간입니다.",
        "view": "Intel Foundry 신뢰도 회복은 TSMC 독점 프리미엄, 첨단공정 장비·소재 기대, INTC 밸류에이션에 영향을 줄 수 있습니다.",
        "korea": "한국장 직접 실적보다 삼성전자 파운드리 상대평가, 반도체 장비·소재 수급, TSMC·Intel·ASML 반응을 먼저 확인합니다.",
        "priced": "중간. Intel 턴어라운드 기대는 선반영되기 쉽고, 애플 수주는 루머 단계라 변동성이 큽니다.",
        "counter": "Tom's Hardware도 비공식 리서치 인용이고 Wccftech 애플 A20 건은 루머 기반입니다. 애플·Intel 공식 계약이나 양산 수율 수치가 없으면 확정 재료가 아닙니다.",
        "failure": "Intel 공식 수율·고객 발표, Apple 공급망 교차확인, INTC/TSM/ASML 반응이 없으면 루머성 재료로 낮춰야 합니다.",
    },
    "hbm_substitution": {
        "news": "AMD Versal, HBM 대신 LPDDR5X 채택: HBM 병목 대체 설계 신호",
        "status": "예비",
        "importance": "중",
        "score": 92,
        "impacts": ["매출·마진·현금흐름", "수급", "시간표"],
        "paths": ["공급·수요", "밸류체인", "계약 가시성"],
        "sectors": ["HBM/메모리 병목", "AMD/Xilinx FPGA", "LPDDR5X/패키징"],
        "summary": "ServeTheHome 보도 기준 AMD Versal Premium Gen 2 Memory on Package가 HBM 대신 LPDDR5X를 쓰는 방향은 HBM 부족 환경에서 대체 메모리 설계가 확산되는 신호입니다.",
        "view": "HBM의 절대 수요가 꺾였다는 뜻이 아니라, 일부 FPGA/적응형 SoC에서 원가·공급 안정성을 위해 LPDDR5X로 우회하는 설계 선택입니다.",
        "korea": "한국장에서는 HBM 과열 해석보다 LPDDR5X, 패키징, 기판, 메모리 믹스, AMD 공급망 노출을 확인합니다.",
        "priced": "중간. HBM 쇼티지는 이미 많이 반영됐고, 이 뉴스는 대체 설계의 범위가 넓어질 때 추가 의미가 커집니다.",
        "counter": "Versal은 범용 AI GPU가 아니라 FPGA/적응형 SoC 영역이라 HBM 시장 전체를 바로 뒤집는 재료는 아닙니다.",
        "failure": "AMD 공식 제품 로드맵, 고객 채택, LPDDR5X 공급계약, HBM 가격·리드타임 변화가 없으면 제한적입니다.",
    },
    "pc_cost_demand": {
        "news": "메모리·SSD 가격 부담에 PC/노트북 출하 둔화 체크",
        "status": "예비",
        "importance": "중",
        "score": 90,
        "impacts": ["매출·마진·현금흐름", "수급"],
        "paths": ["이익", "공급·수요", "밸류체인"],
        "sectors": ["PC/노트북 수요", "DRAM/NAND", "SSD/부품"],
        "summary": "메모리와 SSD 가격 상승이 PC·노트북 수요를 압박한다는 보도는 소비 IT 밸류체인의 출하량과 원가 가정을 흔드는 재료입니다.",
        "view": "메모리 업체에는 판가 상승 호재와 수요 둔화 부담이 동시에 존재하므로, 가격 상승이 물량 감소를 압도하는지 봐야 합니다.",
        "korea": "한국장에서는 삼성전자·SK하이닉스의 PC DRAM/NAND 가격, 세트 수요, SSD 채널 재고, 패널·부품주를 함께 확인합니다.",
        "priced": "중간. 메모리 가격 상승은 주가에 일부 반영됐지만 PC 수요 둔화가 커지면 해석이 바뀔 수 있습니다.",
        "counter": "AI 서버/HBM 수요가 전체 메모리 사이클을 지지하면 PC 약세만으로 주도주 추세가 꺾이지 않을 수 있습니다.",
        "failure": "PC OEM 가이던스, DRAM/NAND 계약가, SSD 채널 가격, 삼성전자·SK하이닉스 주가가 동행하지 않으면 약화됩니다.",
    },
    "memory_antitrust": {
        "news": "메모리 반독점 소송: DRAM 가격담합 주장과 규제 리스크 체크",
        "status": "공식 확인 전",
        "importance": "중",
        "score": 92,
        "impacts": ["밸류에이션/할인율", "수급", "시간표"],
        "paths": ["규제 리스크", "밸류체인", "수급"],
        "sectors": ["DRAM/메모리", "삼성전자/SK하이닉스", "규제·소송 리스크"],
        "summary": "삼성전자·SK하이닉스·Micron 관련 DRAM 가격담합 집단소송 보도는 당장 실적보다 규제·소송 할인율과 투자심리를 건드립니다.",
        "view": "소송은 초기 단계에서는 주가 재료가 과장되기 쉽지만, 규제기관 조사나 대형 합의 가능성으로 번지면 할인율 재료가 됩니다.",
        "korea": "한국장에서는 삼성전자·SK하이닉스의 메모리 가격 사이클과 별도로 소송 단계, 관할 법원, 청구 근거, DOJ/FTC 확산 여부를 확인합니다.",
        "priced": "중간. 과거 유사 소송이 기각된 사례가 있어 시장이 크게 반영하지 않을 수 있습니다.",
        "counter": "원고 측 주장 단계라 사실관계가 확정되지 않았고, 규제기관 공식 조사와 별개입니다.",
        "failure": "법원 사건번호·소장·후속 절차, 규제기관 조사, 주요 외신 확산이 없으면 주가 영향은 제한됩니다.",
    },
    "korea_memory_capex": {
        "news": "SK하이닉스 국내 NAND·DRAM 투자 확대: 청주·용인 일정 체크",
        "status": "예비",
        "importance": "상",
        "score": 106,
        "impacts": ["매출·마진·현금흐름", "수급", "시간표"],
        "paths": ["CAPEX", "밸류체인", "공급·수요", "정책 타임라인"],
        "sectors": ["반도체 CAPEX", "장비·소재·부품", "SK하이닉스 밸류체인"],
        "summary": "SK하이닉스의 국내 NAND·DRAM 투자와 용인 클러스터 일정 보도는 장비·소재·부품 발주 시간표와 메모리 공급능력 가정을 건드립니다.",
        "view": "대형 CAPEX는 장비·소재주 수주 기대에는 호재지만, 메모리 공급 증가가 중장기 가격 사이클에 어떤 영향을 주는지도 같이 봐야 합니다.",
        "korea": "한국장에서는 SK하이닉스, 반도체 장비·소재·부품, 인프라/전력, 용인 클러스터 인허가와 발주 공시를 확인합니다.",
        "priced": "중간. 장기 투자 계획은 알려진 부분이 많아 실제 발주·착공·장비 반입 일정이 새로워야 가격 재료가 됩니다.",
        "counter": "언론 보도만으로 개별 장비사 매출 인식이 확정되는 것은 아니며, 투자 집행 시점이 늦어질 수 있습니다.",
        "failure": "DART/회사 발표, 장비 발주, 착공·인허가 일정, 전력·용수 인프라 진전이 없으면 장기 테마로 후퇴합니다.",
    },
}


def build_supply_alert(row: dict, now, theme: str) -> dict:
    info = THEME[theme]
    age = base.age_hours(row, now)
    score = int(info["score"]) + (8 if age is not None and age <= 24 else 0)
    status = info["status"]
    src = source_text(row)
    if "wccftech" in src and theme in {"intel_18a", "co2_materials"}:
        status = "공식 확인 전" if theme == "intel_18a" else "예비"
    published_dt = row.get("source_published") or row.get("published")
    return {
        "score": score,
        "importance": "상" if score >= 100 else info["importance"],
        "status": status,
        "news": info["news"],
        "original_news": base.clean(row.get("title")),
        "publisher": row.get("publisher") or row.get("source"),
        "source": row.get("source"),
        "link": row.get("link") or "",
        "published": published_dt.isoformat(timespec="minutes") if published_dt else "확인 불가",
        "impacts": list(info["impacts"]),
        "paths": list(info["paths"]),
        "sectors": list(info["sectors"]),
        "matched": [theme],
        "reflection": "낮음" if age is not None and age <= 24 else "중간",
        "counter": info["counter"],
        "interpretation": info["view"],
        "failed_signal": info["failure"],
        "korea_basis": "신뢰 리서치/전문매체 확산",
        "policy_plain_summary": info["summary"],
        "investment_view": info["view"],
        "korea_market_impact": info["korea"],
        "priced_in": info["priced"],
        "supply_chain_theme": theme,
        SUPPLY_FLAG: True,
    }


def enforce_semiconductor_supply_chain_watch() -> None:
    original_classify = contract.strict.classify

    def classify(row: dict, now):
        theme = supply_theme(row)
        alert = original_classify(row, now)
        src = source_text(row)
        specialist_feed = any(term in src for term in [
            "trendforce semiconductor rss",
            "tom's hardware all rss",
            "servethehome rss",
        ])
        if specialist_feed and not theme and alert and not alert.get("k_defense_watch") and not alert.get("korea_nuclear_siting_policy_watch"):
            return None
        if not theme:
            return alert
        supply_alert = build_supply_alert(row, now, theme)
        if not alert:
            return supply_alert
        alert.update({
            key: value
            for key, value in supply_alert.items()
            if key not in {"score", "importance"}
        })
        alert["score"] = max(int(alert.get("score", 0)), int(supply_alert["score"]))
        alert["importance"] = "상" if int(alert["score"]) >= 100 else supply_alert["importance"]
        return alert

    contract.strict.classify = classify


def patch_supply_output_helpers() -> None:
    original_korean_title = runner.korean_title
    original_curated_sectors = runner.curated_sectors
    original_related_text = runner.related_text
    original_has_direct_market_path = runner.has_direct_market_path

    def theme_from_alert(alert: dict) -> str | None:
        if alert.get("supply_chain_theme"):
            return str(alert.get("supply_chain_theme"))
        text = runner.alert_text(alert)
        dummy_row = {
            "title": text,
            "summary": "",
            "publisher": alert.get("publisher") or alert.get("source"),
            "source": alert.get("source"),
            "link": alert.get("link"),
        }
        return supply_theme(dummy_row)

    def korean_title(alert: dict) -> str:
        theme = theme_from_alert(alert)
        if alert.get(SUPPLY_FLAG) or theme:
            return str(THEME.get(theme or "", {}).get("news") or alert.get("news") or "")
        return original_korean_title(alert)

    def curated_sectors(alert: dict) -> list[str]:
        theme = theme_from_alert(alert)
        if alert.get(SUPPLY_FLAG) or theme:
            return list(THEME.get(theme or "", {}).get("sectors") or alert.get("sectors") or [])
        return original_curated_sectors(alert)

    def related_text(alert: dict, fred: dict, te: dict) -> str:
        theme = theme_from_alert(alert)
        if alert.get(SUPPLY_FLAG) or theme:
            extras = {
                "hbm4_contract_price": ["SK하이닉스", "삼성전자", "Micron", "NVDA", "AVGO", "HBM4 ASP", "DRAM 웨이퍼 배분", "TrendForce"],
                "notebook_demand": ["AAPL", "HPQ", "DELL", "Lenovo", "삼성전자", "SK하이닉스", "DRAM/NAND 가격"],
                "memory_price_cycle": ["삼성전자", "SK하이닉스", "MU", "DRAM/NAND 계약가", "HBM 리드타임", "TrendForce"],
                "passive_components": ["YAGEO", "Nichicon", "MLCC 리드타임", "삼성전기", "AI 서버 BOM"],
                "co2_materials": ["삼성전자", "SK하이닉스", "The Elec", "고순도 CO2 가격", "HBM/3D NAND"],
                "intel_18a": ["INTC", "TSM", "ASML", "AAPL", "Intel Foundry", "18A/18A-P"],
                "hbm_substitution": ["AMD", "SK하이닉스", "삼성전자", "Micron", "LPDDR5X", "HBM 리드타임"],
                "pc_cost_demand": ["삼성전자", "SK하이닉스", "MU", "WDC", "STX", "PC DRAM/NAND"],
                "memory_antitrust": ["삼성전자", "SK하이닉스", "Micron", "DRAM 가격", "소송/규제 리스크"],
                "korea_memory_capex": ["SK하이닉스", "반도체 장비", "소재·부품", "용인 클러스터", "DART"],
            }.get(theme, [])
            base_text = original_related_text(alert, fred, te)
            base_parts = [] if base_text == "확인 가능한 직접 지표 없음" else [part.strip() for part in base_text.split(",") if part.strip()]
            return ", ".join(dict.fromkeys(base_parts + extras)) or "확인 가능한 직접 지표 없음"
        return original_related_text(alert, fred, te)

    def has_direct_market_path(text: str, alert: dict) -> bool:
        if alert.get(SUPPLY_FLAG):
            return True
        return original_has_direct_market_path(text, alert)

    runner.korean_title = korean_title
    runner.curated_sectors = curated_sectors
    runner.related_text = related_text
    runner.has_direct_market_path = has_direct_market_path


install_fast_collect_items()
enforce_semiconductor_supply_chain_watch()
patch_supply_output_helpers()


if __name__ == "__main__":
    raise SystemExit(telegram.main())
