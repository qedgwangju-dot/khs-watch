#!/usr/bin/env python3
from __future__ import annotations

import re
import sys

import janus_watch_v2 as j2
import janus_watch_v11 as j11

# v12 핵심
# 사용자가 보내는 개별 기사/URL은 '그 기사 자체를 계속 감시하라'는 뜻이 아니다.
# 해당 기사는 감시 범위·키워드·당사자·실패모드·숫자검산 규칙을 확장하는 사례다.
# 실제 알림은 새 기사 개수가 아니라 이슈의 물질적 상태변화가 확인될 때만 보낸다.

_WEC_MATERIAL = [
    "공식 발표", "공식 확인", "공식 부인", "사실과 다르", "부인",
    "합의", "계약", "loi", "mou", "양해각서", "실사", "due diligence",
    "협상 개시", "협상 착수", "본협상", "우선협상", "term sheet", "텀시트",
    "취득", "매각", "지분율", "인수가격", "매각가격", "출자액", "투자금",
    "경영권", "이사회", "의결권", "voting rights",
    "cfius", "nrc", "승인", "인가",
    "사업권", "설계권", "조달권", "시공권", "입찰 제한", "지식재산권",
]

_WEC_COMMENTARY = [
    "고차방정식", "열쇠", "주식인가", "사업인가", "전망", "분석", "진단",
    "수혜", "들썩", "특징주", "상승세", "주목", "기대", "논란", "평가",
]

_GENERIC_COMMENTARY = [
    "[분석", "분석]", "전망", "수혜주", "관련주", "특징주", "들썩", "급등",
    "상승세", "주목", "기대감", "테마", "진단", "칼럼", "오피니언",
]

_GENERIC_MATERIAL = [
    "공식 발표", "확정", "합의", "계약", "수주", "발주", "선정", "승인", "허가", "인가",
    "신청", "착공", "준공", "상업운전", "임계", "실증", "증설", "공장",
    "예산", "대출", "지원금", "보조금", "출자", "매각", "취득", "실사",
    "loi", "mou", "ppa", "오프테이크", "전력구매", "부지", "전원 인가",
    "mw", "gw", "억달러", "조원", "억원", "%",
]

_HIGH_SIGNAL_KINDS = {
    "official", "official_detail", "vendor_detail", "smr_law_static", "smr_decree_static",
    "doe_ap1000_track", "fermi_ap1000_track", "nuclear_contract_terms", "doosan_nuclear_capacity",
    "smr_budget", "smr_special_zone", "smr_public_private_company", "smr_fuel_supply", "ismr_licensing",
    "smr_offtake_contract", "gt_capacity_cycle", "gt_backlog_slot", "gt_price_leadtime",
    "gt_supply_bottleneck", "doosan_gt_order", "doosan_gt_service", "gt_datacenter_demand", "gt_project_bundle",
}


def _is_material_westinghouse(event: dict) -> bool:
    title = (event.get("title") or "").lower()
    source = (event.get("source") or "").lower()

    # 당사자 공식자료는 그 자체가 상태변화 후보이므로 통과.
    if any(x in source for x in [
        "산업통상부", "정책브리핑", "한국전력", "한수원", "khnp", "kepco",
        "westinghouse", "cameco", "brookfield",
    ]):
        return True

    # 단순 해설/평가 기사라면 실제 단계변화 단어가 없는 한 차단.
    if any(x in title for x in _WEC_COMMENTARY):
        strong = [
            "공식", "합의", "계약", "loi", "mou", "실사", "취득", "매각",
            "지분율", "인수가격", "출자액", "투자금", "cfius", "nrc", "승인",
        ]
        if not any(x in title for x in strong):
            return False

    if any(x in title for x in _WEC_MATERIAL):
        return True

    # 가격·지분율 등 새 거래조건이 제목에 직접 나타나는 경우.
    if re.search(r"(?:\$|달러|원|억원|조원|%|퍼센트).*?\d|\d[\d,.]*\s*(?:억달러|달러|억원|조원|%)", title):
        return True

    return False


def _is_material_generic(event: dict) -> bool:
    title = (event.get("title") or "").lower()
    kind = event.get("kind") or ""

    if kind in _HIGH_SIGNAL_KINDS:
        return True

    # 단순 시장반응·분석·전망은 프로젝트 상태나 숫자가 바뀔 때만 알림.
    if any(x in title for x in _GENERIC_COMMENTARY):
        return any(x in title for x in _GENERIC_MATERIAL)

    return True


def _filter_material(events: list[dict]) -> list[dict]:
    kept = []
    for event in events:
        if event.get("kind") == "westinghouse_stake":
            if _is_material_westinghouse(event):
                kept.append(event)
        elif _is_material_generic(event):
            kept.append(event)
    return kept


_PREV_RENDER = j2.base.render_alert


def _render_v12(events, fact_changes):
    material = _filter_material(events)
    if not material and not fact_changes:
        return ""
    return _PREV_RENDER(material, fact_changes)


j2.base.render_alert = _render_v12


def _self_test_v12():
    # 방금처럼 '새 분석기사 2건'만 늘었지만 거래조건/공식단계가 안 바뀐 경우는 차단.
    assert not _is_material_westinghouse({
        "kind": "westinghouse_stake",
        "source": "인베스트조선",
        "title": "웨스팅하우스가 원전 족쇄를 풀 열쇠?…韓·美·주주 이해관계 얽힌 고차방정식",
    })
    assert not _is_material_westinghouse({
        "kind": "westinghouse_stake",
        "source": "네이트",
        "title": "미국 제안 '지분'…웨스팅하우스 주식인가 원전 사업인가",
    })
    # 실제 상태변화는 통과.
    assert _is_material_westinghouse({
        "kind": "westinghouse_stake",
        "source": "연합뉴스",
        "title": "한국전력, 웨스팅하우스 지분 인수 실사 착수…지분율 10% 협상",
    })
    assert _is_material_westinghouse({
        "kind": "westinghouse_stake",
        "source": "산업통상부",
        "title": "웨스팅하우스 투자 관련 공식 설명",
    })


if __name__ == "__main__":
    if "--mode" in sys.argv and "self-test" in sys.argv:
        _self_test_v12()
    sys.exit(j2.base.main())
