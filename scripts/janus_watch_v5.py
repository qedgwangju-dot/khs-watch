#!/usr/bin/env python3
import html
import re
import sys

import janus_watch_v2 as j2
import janus_watch_v4 as j4

# Westinghouse 지분 관련 기사가 한꺼번에 여러 건 잡혀도 동일한 설명 블록을
# 기사마다 반복하지 않고, 하나의 '이슈 묶음'으로 보여준다.
# 정보량은 유지하되 '현재 변화 → 공통 사실 → 기사별 역할 → 병목 → 다음 확인' 순서로 배치한다.

_ORIGINAL_RENDER = j2._render_alert_korean


def _role(title: str) -> str:
    low = (title or "").lower()
    if any(x in low for x in ["특징주", "상승세", "급등", "주가"]):
        return "시장 반응"
    if any(x in low for x in ["사실과 달라", "사실과 다름", "부인", "denies", "not true"]):
        return "부인·검증"
    if any(x in low for x in ["떠맡", "부담", "우려", "논란", "쟁점"]):
        return "쟁점·비판"
    if any(x in low for x in ["급물살", "검토", "협상", "논의", "제안", "인수", "확보"]):
        return "본안·협상"
    return "관련 보도"


def _outlet(source: str) -> str:
    source = j2.base.norm(source)
    aliases = {
        "v.daum.net": "다음",
        "Daum": "다음",
    }
    return aliases.get(source, source or "출처 미상")


def _status(events) -> str:
    # 공식 당사자가 직접 확인한 계약/합의가 잡힌 경우만 '공식 확인'으로 올린다.
    for e in events:
        source = (e.get("source") or "").lower()
        title = (e.get("title") or "").lower()
        official = any(x in source for x in [
            "산업통상부", "정책브리핑", "한국전력", "한수원",
            "westinghouse", "cameco", "brookfield",
        ])
        if official and any(x in title for x in ["계약", "합의", "취득", "투자 확정", "agreement", "acquisition"]):
            return "공식 확인 단계"
    if any(any(x in (e.get("title") or "") for x in ["검토", "급물살", "협상", "논의", "확보"]) for e in events):
        return "새 보도 재등장 — 협의·검토 단계, 공식 확정 전"
    return "관련 보도 확대 — 공식 확정 여부 교차검증 필요"


def _headline(events) -> str:
    titles = " ".join((e.get("title") or "") for e in events)
    if any(x in titles for x in ["급물살", "정부·한전", "지분 확보", "지분 인수"]):
        return "한국의 Westinghouse 지분 인수 논의 재부상"
    return "한국의 Westinghouse 지분 참여 관련 보도 확대"


def _render_wec_cluster(events) -> str:
    lines = [
        "🚨 <b>[원전·Westinghouse 웹감시]</b>",
        "",
        f"<b>{html.escape(_headline(events))}</b>",
        f"<code>지분투자·원전동맹 | 신규 보도 {len(events)}건</code>",
        "",
        "<b>지금 무엇이 달라졌나</b>",
        "• 한국 정부·한국전력이 미국 원전 건설 참여와 함께 Westinghouse 지분 확보 방안을 검토한다는 보도가 다시 확대",
        "• 다만 2026년 8월 25일 산업통상부는 ‘한·미 공동출자 방식의 Westinghouse 지분 인수’ 보도를 공식적으로 사실과 다르다고 설명",
        f"• 현재 판정: <b>{html.escape(_status(events))}</b>",
        "",
        "<b>한눈에 보기</b>",
        "• 핵심 당사자: <b>한국 정부·한국전력 / Westinghouse / Brookfield / Cameco</b>",
        "• 거래조건: <b>지분율 · 인수가격 · 재원 · 경영참여권</b>",
        "• 사업 연결: <b>AP1000 설계 · 기자재 조달 · 시공 · 사업개발</b>",
        "• 별도 협상: <b>지식재산권 · 입찰 지역 제한 완화</b>",
        "",
        "<b>기사별 확인</b>",
    ]

    for event in events[:8]:
        title = j2.base.norm(event.get("title") or "")
        outlet = _outlet(event.get("source") or "")
        role = _role(title)
        url = event.get("url") or ""
        if url:
            title_html = f"<a href=\"{html.escape(url, quote=True)}\">{html.escape(title)}</a>"
        else:
            title_html = html.escape(title)
        lines.append(f"• <b>{html.escape(role)}</b> | {html.escape(outlet)} — {title_html}")

    lines.extend([
        "",
        "<b>핵심 병목</b>",
        "• <b>공식 확인:</b> 8월 25일 산업통상부의 기존 부인 이후 정부·한전·Westinghouse 측 새 공식 발표가 아직 핵심",
        "• <b>가격·지분:</b> Brookfield·Cameco가 실제로 어느 지분을 어떤 가격에 매각할지 미확정",
        "• <b>권한:</b> 지분을 취득해도 AP1000 설계·조달·시공 권한은 자동으로 생기지 않고 별도 계약 필요",
        "• <b>규제:</b> 미국 원전 프로젝트별 CFIUS·NRC 외국인 소유·통제 관련 심사 가능",
        "",
        "<b>왜 중요한가</b>",
        "• 실제 지분 참여와 사업권 확대가 함께 성사되면 한국의 역할이 단순 기자재·시공에서 <b>설계·조달·사업개발</b>까지 넓어질 수 있음",
        "• 반대로 지분만 취득하고 사업권·지식재산권 조건이 그대로라면 투자금 대비 전략적 실익이 크게 낮아질 수 있음",
        "",
        "<b>다음 확인</b>",
        "• <b>공식 발표 → LOI/MOU → 실사 착수 → 지분율·인수가격·재원 → 경영참여권 → CFIUS/NRC → AP1000 사업권</b>",
    ])
    return "\n".join(lines).strip()


def _render_grouped(events, fact_changes):
    wec_events = [e for e in events if e.get("kind") == "westinghouse_stake"]
    other_events = [e for e in events if e.get("kind") != "westinghouse_stake"]
    parts = []

    if wec_events:
        parts.append(_render_wec_cluster(wec_events))

    if other_events or fact_changes:
        other = _ORIGINAL_RENDER(other_events, fact_changes)
        if other:
            parts.append(other)

    return "\n\n──────────\n\n".join(parts).strip()


j2.base.render_alert = _render_grouped

if __name__ == "__main__":
    sys.exit(j2.base.main())
