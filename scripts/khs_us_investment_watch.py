#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE_PATH = HERE / "khs_us_investment_watch_base.py"

spec = importlib.util.spec_from_file_location("khs_us_investment_watch_base", BASE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"base watcher load failed: {BASE_PATH}")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
core = base.core


def _extend_unique(target: list[str], values: list[str]) -> None:
    for value in values:
        if value not in target:
            target.append(value)


# Encinal의 실제 설비 발주와 가스터빈 병목의 대체전원 경로를 직접 검색한다.
_extend_unique(core.QUERIES, [
    '"대미투자" 가스터빈 두산에너빌리티 when:7d',
    '"Encinal" gas turbine Doosan 1.4GW when:7d',
    '"텍사스" 4.9GW HRSG 비에이치아이 when:7d',
    '"Encinal" HRSG BHI 4.9GW when:7d',
    '두산에너빌리티 가스터빈 생산능력 12기 when:7d',
    '두산에너빌리티 가스터빈 장기 서비스 계약 when:7d',
    '"Babcock & Wilcox" "Base Electron" 1.2GW data center when:14d',
    '"Babcock & Wilcox" Siemens steam turbine 1GW data center when:14d',
    '"natural gas boiler" "steam turbine" AI data center when:14d',
    '"FastPower" data center steam turbine when:30d',
    '"GE Vernova" gas turbine backlog 116GW 125GW when:30d',
    '"Applied Digital" "Base Electron" guarantee when:30d',
    '"1,570 GW" interconnection queue data center when:30d',
])
_extend_unique(core.TRUSTED, [
    "뉴스핌",
    "두산에너빌리티",
    "Babcock & Wilcox",
    "Applied Digital",
    "GE Vernova",
    "Siemens Energy",
    "Lawrence Berkeley National Laboratory",
    "Berkeley Lab",
    "SEC",
])
_extend_unique(core.MATERIAL, [
    "두산에너빌리티",
    "Doosan Enerbility",
    "비에이치아이",
    "BHI",
    "380MW",
    "DGT6-300H",
    "생산능력",
    "장기 서비스",
    "LTPM",
    "LTSA",
    "HRSG 8~10기",
    "4000억",
    "5000억",
    "Babcock & Wilcox",
    "Base Electron",
    "Applied Digital",
    "Siemens Energy",
    "FastPower",
    "natural gas boiler",
    "steam turbine",
    "가스 보일러",
    "천연가스 보일러",
    "증기터빈",
    "1.2GW",
    "2.4 billion",
    "24억달러",
    "20 steam turbines",
    "12 to 15 months",
    "12~15개월",
    "116GW",
    "125GW",
    "1,570 GW",
    "1570GW",
])

_ORIG_TAGS = core._tags
_ORIG_MEANING = core._meaning
_ORIG_TEXAS_BLOCK = core._texas_ai_power_block


def _upgraded_tags(title: str, source: str = "") -> list[str]:
    tags = list(_ORIG_TAGS(title, source))
    low = f"{title} {source}".lower()
    if any(token in low for token in [
        "두산에너빌리티", "doosan enerbility", "비에이치아이", "bhi",
        "가스터빈", "gas turbine", "hrsg", "380mw", "dgt6-300h",
    ]):
        if "가스터빈·HRSG 공급망" not in tags:
            tags.insert(0, "가스터빈·HRSG 공급망")
    if any(token in low for token in ["두산에너빌리티", "doosan enerbility", "dgt6-300h", "380mw"]):
        if "두산에너빌리티 가스터빈 후보" not in tags:
            tags.append("두산에너빌리티 가스터빈 후보")
    if any(token in low for token in ["비에이치아이", "bhi", "hrsg"]):
        if "비에이치아이 HRSG 후보" not in tags:
            tags.append("비에이치아이 HRSG 후보")
    if any(token in low for token in [
        "babcock & wilcox", "base electron", "fastpower", "natural gas boiler",
        "steam turbine", "천연가스 보일러", "가스 보일러", "증기터빈",
    ]):
        if "보일러·증기터빈 대체전원" not in tags:
            tags.insert(0, "보일러·증기터빈 대체전원")
    if any(token in low for token in ["ge vernova", "116gw", "125gw", "gas turbine backlog"]):
        if "가스터빈 슬롯 병목" not in tags:
            tags.insert(0, "가스터빈 슬롯 병목")
    if "applied digital" in low and "base electron" in low:
        if "Base Electron 지분·보증 구조" not in tags:
            tags.append("Base Electron 지분·보증 구조")
    if "1,570 gw" in low or "1570gw" in low:
        if "계통대기열 시점오류 방지" not in tags:
            tags.append("계통대기열 시점오류 방지")
    return tags


def _upgraded_meaning(tags: list[str]) -> str:
    if "보일러·증기터빈 대체전원" in tags:
        return (
            "가스터빈 슬롯이 부족할수록 데이터센터 전력 설계가 천연가스 직화 보일러+증기터빈으로 이동할 수 있습니다. "
            "이 경로는 가스터빈과 HRSG를 생략할 수 있어 두산 증기터빈·보일러에는 새 기회지만 HRSG 업체에는 대체 역풍이 됩니다."
        )
    if "가스터빈 슬롯 병목" in tags:
        return (
            "'2032년 납기' 같은 기사 문구보다 제조사 공식 수주잔고·슬롯 예약·연간 생산능력을 우선 확인합니다. "
            "슬롯이 더 밀리면 보일러+증기터빈, 연료전지, 태양광+저장장치 등 대체전원 채택이 빨라질 수 있습니다."
        )
    if "가스터빈·HRSG 공급망" in tags:
        return (
            "Encinal의 발표 용량보다 실제 가스터빈·스팀터빈·배열회수보일러(HRSG) "
            "제조사 선정, 발주 수량, 생산 슬롯과 납기가 국내 기업 매출 인식 시점을 결정합니다."
        )
    return _ORIG_MEANING(tags)


def _upgraded_texas_block() -> list[str]:
    original = list(_ORIG_TEXAS_BLOCK())
    insert_at = next(
        (i for i, line in enumerate(original) if line == "<b>다음 확인</b>"),
        len(original),
    )
    supply_chain = [
        "<b>🧩 가스터빈·HRSG 공급망 정량 기준선</b>",
        "• <b>1단계 1.4GW</b>를 두산에너빌리티 DGT6-300H S2 <b>380MW급</b>으로 단순환산하면 1,400÷380=3.68 → <b>약 4기</b>입니다. 실제 제조사·모델·배치 수량은 아직 미확정입니다.",
        "• 두산에너빌리티 공식: 미국 기업과 <b>380MW급 가스터빈 7기</b> 추가 공급계약, 미국 누적 <b>12기</b>. 이 7기는 <b>2029년 5월부터 월 1기씩</b> 순차 공급 예정입니다.",
        "• 공급 병목: 보도·증권가 기준 두산 대형 가스터빈 생산능력은 현재 <b>연 8기 → 2028년 연 12기</b> 확대 계획. Encinal이 두산을 선정할 경우 기존 2029년 미국향 공급 슬롯과 겹치는지 반드시 확인합니다.",
        "• 반복매출 기준선: 두산 공식 국내 사례에서 가스터빈 3기 장기 부품조달계약 규모가 <b>약 4,800억원</b>, 통상 계약기간은 <b>10년 이상</b>입니다. Encinal의 장기 유지보수 계약은 아직 미확정이므로 주기기 수주와 분리 추적합니다.",
        "• <b>후속 4.9GW 복합화력</b>: 리딩투자증권 추정으로 HRSG <b>8~10기</b> 발주 가정 시 비에이치아이 잠재 수주 <b>약 4,000억~5,000억원</b>. 이는 <b>증권사 추정이며 확정 수주가 아닙니다.</b>",
        "• 비에이치아이 현재 숫자: 리딩투자증권 기준 2026년 상반기 HRSG 신규 수주 <b>약 5,000억원</b>, 연간 신규 수주 <b>1조원 이상</b> 전망. Encinal 본계약이 붙으면 기존 수주잔고에 추가되는 구조인지 확인합니다.",
        "• <b>확정 당사자 판정</b>: 현재 Encinal 가스터빈·HRSG 제조사는 미확정. 두산에너빌리티·비에이치아이는 각각 기술·레퍼런스 기반 <b>후보 수혜</b>이며 본계약 전 직접 수혜로 승격하지 않습니다.",
        "• <b>공정 병목 후보</b>: 가스터빈 생산 슬롯·주단조/고온부품·발전기·HRSG 제작·현장 설치·시운전. 먼저 볼 지표는 제조사 선정과 납기이며, 2029~2030 슬롯이 밀리면 전원 인가 일정이 먼저 늦어질 수 있습니다.",
        "• <b>승격 조건</b>: 제조사 실명·구매주문(PO)·EPC 범위·가스터빈 실제 기수·HRSG 공급사·납기·장기 유지보수 계약이 공식 확인될 때만 매출 연결 단계로 올립니다.",
        "",
        "<b>♨️ 보일러+증기터빈 대체전원 기준선</b>",
        "• Babcock & Wilcox 공식: Base Electron 1.2GW 프로젝트는 <b>24억달러</b> 설계·조달·시공 계약으로, <b>300MW 천연가스 보일러 4기 + Siemens Energy 증기터빈 발전기</b> 조합입니다. 추가 <b>1.2GW</b> 옵션도 평가 중입니다.",
        "• B&W 2026년 8월 공식: FastPower용 Siemens Energy <b>50MW 증기터빈 20기 = 총 1GW</b>를 선발주했고, 회사는 추가 1GW를 <b>12~15개월</b> 내 확보하는 계획을 제시했습니다.",
        "• 일정 판정: B&W 2026년 3월 투자자료의 1.2GW·4×300MW 구성은 <b>36~40개월</b> 가동 기준입니다. 2026년 1월의 '2028년 말'은 초기 목표였고, 8월 공식자료에서는 노스다코타 Center 인근 부지의 <b>조건부사용허가 신청</b> 단계가 확인돼 허가·착공·전원 인가를 다시 추적합니다.",
        "• 가스터빈 병목은 기사상 '2032년'을 고정값으로 쓰지 않습니다. GE Vernova 2Q26 공식 기준 가스발전 장비 수주잔고+슬롯예약은 <b>116GW</b>, 2026년 말 목표 <b>125GW 이상</b>; 생산능력은 <b>3Q26 20GW → 2028년 24GW → 2030년 30GW</b> 경로를 우선 봅니다.",
        "• 계통대기열 교정: <b>1,570GW·약 11,600건</b>은 2023년 말 미국 <b>발전사업 전체</b> 계통연계 대기열입니다. 태양광·저장장치·풍력이 95%를 차지하므로 2026년 데이터센터 전용 대기물량으로 저장하지 않습니다.",
        "• Base Electron은 Applied Digital의 단순 자회사가 아니라 <b>독립 발전사업자</b>입니다. Applied Digital은 보증 제공 대가로 <b>10% 지분</b>을 받았고, SEC 기준 해당 보증은 <b>2026-05-29 Base Electron 측 3,700만달러 지급 후 종료</b>됐습니다.",
        "• 국내 기업 지도: 두산에너빌리티는 미국에 <b>370MW급 증기터빈·발전기 각 4기</b>를 2029년까지 공급하는 실적이 있어 증기계통 직접 역량이 확인됩니다. 다만 이는 Base Electron 공급 확정이 아니라 기술·수주 레퍼런스입니다.",
        "• <b>HRSG 역풍</b>: 복합화력은 가스터빈→HRSG→증기터빈이지만 직화 보일러+증기터빈은 HRSG를 생략할 수 있습니다. 따라서 비에이치아이·SNT에너지는 복합화력 확대 수혜와 대체전원 확산 역풍을 동시에 추적합니다.",
        "• <b>실패모드</b>: 가스터빈 병목을 피한 뒤 증기터빈·보일러 제작 슬롯, 가스관, 환경허가, 현장 설치 인력이 새 병목으로 이동할 수 있습니다. B&W의 1GW 증기터빈 선발주는 이 병목의 조기지표로 봅니다.",
        "• <b>승격 조건</b>: 국내 업체 실명 공급계약, 보일러·증기터빈 구매주문, 전력구매계약(PPA), 허가·착공, 확정 상업운전일이 붙을 때만 직접 매출 단계로 올립니다.",
        '• 원천: <a href="https://www.babcock.com/home/about/corporate/news/babcock-and-wilcox-receives-full-notice-to-proceed-on-24-billion-power-generation-project-for-base-electron-to-supply-power-to-applied-digital-ai-factory-campuses">B&W 1.2GW·24억달러</a> · <a href="https://www.babcock.com/home/about/corporate/news/babcock-and-wilcox-signs-agreement-with-siemens-energy-to-commence-work-on-20-steam-turbines-for-data-center-power-generation">B&W 증기터빈 1GW</a> · <a href="https://www.gevernova.com/news/press-releases/ge-vernova-reports-second-quarter-2026-financial-results-raises-2026-financial">GE Vernova 2Q26</a> · <a href="https://www.sec.gov/Archives/edgar/data/1144879/000114487926000048/R26.htm">Applied Digital SEC</a>',
        "",
    ]
    return original[:insert_at] + supply_chain + original[insert_at:]


core._tags = _upgraded_tags
core._meaning = _upgraded_meaning
core._texas_ai_power_block = _upgraded_texas_block


def main() -> int:
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
