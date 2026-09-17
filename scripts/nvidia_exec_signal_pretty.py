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
            "📈 <b>수량</b> 2027년 NVIDIA 전체 칩 판매량 <b>약 2배</b> 전망",
            "🏢 <b>공식 기준</b> FY28 매출 성장 전망 <b>약 +70%</b>",
            "→ <b>핵심: 전체 칩 2배 ≠ AI GPU·HBM 2배</b>",
        ]
    if has_safety:
        lines += [
            "🛡️ <b>안전</b> 준비되지 않은 제품은 <b>출시 보류 후 추가 개발</b>",
            "→ Reuters가 <b>같은 스코틀랜드 회의 현장</b> 발언으로 확인",
            "→ 원칙적 발언이며 <b>Blackwell·Rubin 실제 지연 신호는 아직 아님</b>",
        ]

    lines += [
        "",
        "<b>[투자 연결]</b>",
        "• 병목: <b>HBM·서버 DRAM·파운드리·첨단패키징·전력</b>",
        "• 제품믹스: GPU 외 <b>CPU·스위치·광 네트워킹·노트북·Jetson</b> 포함",
        "• 따라서 전체 칩 수량 2배를 <b>HBM 수요 2배로 직접 환산 금지</b>",
        "• 병목 완화 → 현재 못 받는 주문이 <b>추가 매출</b>로 전환될 여지",
        "",
        "<b>[출처·맥락]</b>",
        "• 판매 2배: <b>9월 17일 스코틀랜드 찰스 3세 AI 정상회의 전 취재진 발언</b>",
        "• 안전: Reuters가 같은 회의 현장에서 <b>‘준비되지 않았으면 보류’</b> 발언 확인",
        "• 같은 행사 맥락이지만 <b>수량 전망</b>과 <b>안전 원칙</b>은 분리해서 판단",
        "",
        "<b>[다음 알림]</b>",
        "• FY28 매출 성장률 <b>+70% 상향·하향</b>",
        "• GPU·CPU·네트워킹 등 <b>제품별 출하량·판매량 목표</b> 신규 제시",
        "• 전체 칩 2배 중 <b>AI GPU 비중</b> 공개",
        "• 수요 2배 대비 <b>실제 공급 가능 비율</b> 변화",
        "• HBM·DRAM·CoWoS·파운드리·전력 <b>병목 순위 구체화</b>",
        "• Blackwell·Rubin이 <b>안전·신뢰성 때문에 실제 연기·출시 보류</b>",
        "• AI 규제·안전 기준이 <b>제품 출시·데이터센터 도입 일정</b>에 직접 영향",
    ]

    details = [
        "<b>상세 판단 기준</b>",
        "• FY27 2분기 실적발표에서 NVIDIA는 고객 수요 전망상 다음 해 성장 잠재력이 약 2배라고 설명했습니다.",
        "• 회사의 FY28 공식 매출 성장 전망은 약 +70%였고, 그 차이는 수요 부족이 아니라 공급 제약 때문이라고 설명했습니다.",
        "• 9월 17일 Huang의 ‘칩 판매 2배’는 스코틀랜드 찰스 3세 AI 정상회의 전 취재진에게 직접 밝힌 수량 전망입니다.",
        "• 다만 NVIDIA가 총 칩 판매대수를 공개하지 않고, GPU 외 CPU·스위치·광 네트워킹·노트북·Jetson 등을 함께 판매하므로 AI GPU 2배와 동일하지 않습니다.",
        "• FY27 2분기 공식 실적발표에서는 고객 수요가 다음 해 약 2배 성장 가능성을 보였지만 공급 제약 때문에 FY28 매출은 약 +70% 성장으로 전망했습니다.",
        "• 따라서 HBM·서버 DRAM·파운드리·첨단패키징·전력 공급능력이 실제 매출 전환 속도를 결정합니다.",
        "• Reuters도 같은 스코틀랜드 회의에서 Huang이 준비되지 않은 제품은 보류해야 한다고 말했다고 확인했지만, 이는 Blackwell·Rubin 실제 일정 연기를 뜻하지는 않습니다.",
    ]
    lines += ["", "<blockquote expandable>" + "\n".join(details) + "</blockquote>"]

    refs = [x for x in (query_line, official_line, scotland_line, demand_source, safety_source) if x]
    if refs:
        lines += ["", "<b>[근거]</b>"] + refs

    ALERT.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
