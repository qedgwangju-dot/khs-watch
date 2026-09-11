#!/usr/bin/env python3
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALERT = ROOT / "out" / "khs_us_investment_alert.html"


def main() -> int:
    if not ALERT.exists():
        print("altpower_finalize=none")
        return 0

    text = ALERT.read_text(encoding="utf-8")
    low = text.lower()
    relevant = any(
        token in low
        for token in [
            "encinal", "엔시날", "가스터빈", "gas turbine", "hrsg",
            "스팀터빈", "증기터빈", "steam turbine", "보일러", "babcock",
            "base electron", "텍사스 ai 전력", "data center",
        ]
    )
    if not relevant:
        print("altpower_finalize=not_relevant")
        return 0
    if "♨️ 가스터빈 병목·대체전원 기준선" in text:
        print("altpower_finalize=already_present")
        return 0

    block = [
        "",
        "<b>♨️ 가스터빈 병목·대체전원 기준선</b>",
        "• <b>가스터빈 병목 검증</b>: 기사 제목의 '2032년 납기'를 고정 사실로 저장하지 않습니다. GE Vernova 2Q26 공식 기준 가스발전 장비 수주잔고+슬롯예약은 <b>116GW</b>, 2026년 말 목표 <b>125GW 이상</b>; 생산능력은 <b>3Q26 20GW → 2028년 24GW → 2030년 30GW</b>를 우선 추적합니다.",
        "• <b>대체전원 실증</b>: Babcock & Wilcox–Base Electron은 <b>1.2GW·24억달러</b> 설계·조달·시공 계약을 체결했고, 구성은 <b>300MW 천연가스 보일러 4기 + Siemens Energy 증기터빈 발전기</b>입니다. 추가 <b>1.2GW</b> 옵션도 평가 중입니다.",
        "• <b>증기터빈 선점</b>: B&W는 Siemens Energy <b>50MW급 20기 = 총 1GW</b>를 FastPower용으로 선발주했습니다. B&W 2Q26 공식 설명은 추가 1GW를 <b>12~15개월</b> 내 확보하는 계획입니다.",
        "• <b>일정 교정</b>: B&W 3월 투자자료의 1.2GW·4×300MW 구성은 <b>36~40개월</b> 가동 기준입니다. 1월의 '2028년 말'은 초기 목표였고, 8월에는 노스다코타 Center 인근 부지의 <b>조건부사용허가 신청</b> 단계가 확인돼 허가·착공·전원 인가를 우선 봅니다.",
        "• <b>계통대기열 교정</b>: <b>1,570GW·약 11,600건</b>은 2023년 말 미국 발전사업 전체 계통연계 대기열입니다. 태양광·저장장치·풍력이 95%를 차지하므로 2026년 데이터센터 전용 대기물량으로 저장하지 않습니다.",
        "• <b>Base Electron 관계</b>: Base Electron은 독립 발전사업자입니다. Applied Digital은 보증 제공 대가로 <b>10% 지분</b>을 받았고, SEC 기준 해당 보증은 <b>2026-05-29 Base Electron 측 3,700만달러 지급 후 종료</b>됐습니다. 'Applied Digital 자회사'로 단순 표기하지 않습니다.",
        "• <b>국내 기업 지도</b>: 두산에너빌리티는 미국에 <b>370MW급 증기터빈·발전기 각 4기</b>를 2029년까지 공급하는 북미 레퍼런스가 있습니다. 다만 이는 Base Electron 공급 확정이 아니라 증기계통 직접 역량 증거입니다.",
        "• <b>HRSG 역풍</b>: 복합화력은 가스터빈→HRSG→증기터빈이지만 직화 보일러+증기터빈은 HRSG를 생략할 수 있습니다. 따라서 비에이치아이·SNT에너지는 복합화력 확대 수혜와 대체전원 확산 역풍을 동시에 추적합니다.",
        "• <b>실패모드</b>: 가스터빈 병목이 증기터빈·보일러 제작 슬롯, 가스관, 환경허가, 현장 설치 인력 병목으로 이동할 수 있습니다. B&W의 1GW 증기터빈 선발주를 조기 경보 지표로 봅니다.",
        "• <b>승격 조건</b>: 국내 업체 실명 공급계약·구매주문(PO)·전력구매계약(PPA)·허가·착공·확정 전원 인가 시점이 붙을 때만 직접 매출 단계로 올립니다.",
        "",
        '<b>대체전원 원천</b> · <a href="https://www.babcock.com/home/about/corporate/news/babcock-and-wilcox-receives-full-notice-to-proceed-on-24-billion-power-generation-project-for-base-electron-to-supply-power-to-applied-digital-ai-factory-campuses">B&W 1.2GW·24억달러</a> · <a href="https://www.babcock.com/home/about/corporate/news/babcock-and-wilcox-signs-agreement-with-siemens-energy-to-commence-work-on-20-steam-turbines-for-data-center-power-generation">B&W 증기터빈 1GW</a> · <a href="https://www.gevernova.com/news/press-releases/ge-vernova-reports-second-quarter-2026-financial-results-raises-2026-financial">GE Vernova 2Q26</a>',
        '<b>구조·일정 원천</b> · <a href="https://www.sec.gov/Archives/edgar/data/1630805/000163080526000066/bwiroverview-august2026x.htm">B&W 8월 투자자료</a> · <a href="https://www.sec.gov/Archives/edgar/data/1144879/000114487926000048/R26.htm">Applied Digital SEC</a> · <a href="https://energyanalysis.lbl.gov/publications/queued-2024-edition-characteristics">Berkeley Lab 계통대기열</a> · <a href="https://www.doosanenerbility.com/kr/about/news_board_view?id=21000808&page=0&pageSize=9">두산 증기터빈 4기</a>',
    ]

    ALERT.write_text(text.rstrip() + "\n" + "\n".join(block) + "\n", encoding="utf-8")
    print("altpower_finalize=appended")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
