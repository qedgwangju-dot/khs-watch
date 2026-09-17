from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALERT = ROOT / "out" / "nvidia_exec_signal_alert.html"


def first_line(text: str, prefix: str) -> str:
    for line in text.splitlines():
        if line.startswith(prefix):
            return line
    return ""


def main() -> None:
    if not ALERT.exists():
        return

    raw = ALERT.read_text(encoding="utf-8").strip()
    has_demand = "2027년 NVIDIA 칩 판매량" in raw or "판매 2배" in raw or "수요 2배" in raw
    has_safety = "제품의 기능·성능·안전에 확신이 없으면" in raw or "안전하지 않으면 출시" in raw

    query_line = first_line(raw, "<b>조회</b>:")
    official_line = first_line(raw, "<b>공식 기준</b>:")
    scotland_line = first_line(raw, "<b>스코틀랜드 회의</b>:")
    demand_source = first_line(raw, "<b>수요·판매 전망 출처</b>:")
    safety_source = first_line(raw, "<b>안전 발언 출처</b>:")

    lines: list[str] = [
        "🚨 <b>NVIDIA 경영진 신호</b>",
        "━━━━━━━━━━━━━━━━",
        "<b>[한눈에 보기]</b>",
    ]

    if has_demand:
        lines += [
            "📈 <b>수요</b> 2027년 칩 판매량 <b>약 2배</b> 가능성",
            "🏢 <b>공식 기준</b> FY28 매출 성장 전망 <b>약 +70%</b>",
            "→ <b>핵심: 수요보다 공급능력이 매출 상단을 제한</b>",
        ]
    if has_safety:
        lines += [
            "🛡️ <b>안전</b> 기능·성능·안전에 확신이 없으면 <b>출시 보류 후 수정</b>",
            "→ 원칙적 발언이며 <b>Blackwell·Rubin 실제 지연 신호는 아직 아님</b>",
        ]

    lines += [
        "",
        "<b>[투자 연결]</b>",
        "• 병목: <b>HBM·서버 DRAM·파운드리·첨단패키징·전력</b>",
        "• 병목 완화 → 현재 못 받는 주문이 <b>추가 매출</b>로 전환될 여지",
        "• 실제 악화 판정 → <b>Blackwell·Rubin 일정 변경·고객 승인 지연</b>이 확인될 때",
        "",
        "<b>[출처·맥락 구분]</b>",
        "• 스코틀랜드: Jensen Huang의 <b>Dumfries House AI 회의 참석</b> 확인",
        "• 안전 발언: <b>9월 15일 Salesforce Dreamforce</b>에서 나온 구체적 원칙",
        "• 따라서 두 사건을 <b>같은 장소의 한 발언처럼 합치지 않음</b>",
        "",
        "<b>[다음 알림]</b>",
        "• FY28 매출 성장률 <b>+70% 상향·하향</b>",
        "• GPU·AI 가속기 <b>출하량·판매량 목표</b> 신규 제시",
        "• 수요 2배 대비 <b>실제 공급 가능 비율</b> 변화",
        "• HBM·DRAM·CoWoS·파운드리·전력 <b>병목 순위 구체화</b>",
        "• Blackwell·Rubin이 <b>안전·신뢰성 때문에 실제 연기·출시 보류</b>",
        "• AI 규제·안전 기준이 <b>제품 출시·데이터센터 도입 일정</b>에 직접 영향",
    ]

    details = [
        "<b>상세 판단 기준</b>",
        "• FY27 2분기 실적발표에서 NVIDIA는 고객 수요 전망상 다음 해 성장 잠재력이 약 2배라고 설명했습니다.",
        "• 회사의 FY28 공식 매출 성장 전망은 약 +70%였고, 그 차이는 수요 부족이 아니라 공급 제약 때문이라고 설명했습니다.",
        "• 따라서 ‘칩 판매 2배’는 수요 강도의 상단 신호이지 공식 매출 +100% 가이던스가 아닙니다.",
        "• HBM·서버 DRAM·파운드리·첨단패키징·전력 공급능력이 늘어야 미충족 수요가 실제 매출로 전환됩니다.",
        "• 안전 원칙만으로 제품 지연으로 판정하지 않고, 실제 제품 일정 변경·고객 승인 지연이 확인될 때 시간표 악화로 판정합니다.",
    ]
    lines += ["", "<blockquote expandable>" + "\n".join(details) + "</blockquote>"]

    refs = [x for x in (query_line, official_line, scotland_line, demand_source, safety_source) if x]
    if refs:
        lines += ["", "<b>[근거]</b>"] + refs

    ALERT.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
