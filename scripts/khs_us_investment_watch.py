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


# Encinal의 실제 설비 발주가 국내 기자재 매출로 연결되는 경로를 직접 검색한다.
_extend_unique(core.QUERIES, [
    '"대미투자" 가스터빈 두산에너빌리티 when:7d',
    '"Encinal" gas turbine Doosan 1.4GW when:7d',
    '"텍사스" 4.9GW HRSG 비에이치아이 when:7d',
    '"Encinal" HRSG BHI 4.9GW when:7d',
    '두산에너빌리티 가스터빈 생산능력 12기 when:7d',
    '두산에너빌리티 가스터빈 장기 서비스 계약 when:7d',
])
_extend_unique(core.TRUSTED, [
    "뉴스핌",
    "두산에너빌리티",
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
    return tags


def _upgraded_meaning(tags: list[str]) -> str:
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
        '• 원천: <a href="https://www.doosanenerbility.com/kr/business/gas_turbine_product">두산 380MW 제품</a> · <a href="https://www.doosanenerbility.com/kr/about/news_board_view?id=21000800&page=0&pageSize=9">두산 미국 7기 계약</a> · <a href="https://www.doosanenerbility.com/kr/about/news_board_view?id=21000806&page=0&pageSize=9">두산 장기 서비스 4,800억원</a> · <a href="https://www.newspim.com/news/view/20260910000252">비에이치아이 HRSG 추정</a>',
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
