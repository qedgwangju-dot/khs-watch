from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALERT = ROOT / "out" / "nvidia_exec_signal_alert.html"


def first_line(text: str, prefix: str) -> str:
    for line in text.splitlines():
        if line.startswith(prefix):
            return line
    return ""


def _strip_prefix(line: str, prefix: str) -> str:
    return line[len(prefix):].strip() if line.startswith(prefix) else line.strip()


def main() -> None:
    if not ALERT.exists():
        return

    raw = ALERT.read_text(encoding="utf-8").strip()
    has_demand = "2027년에 올해보다 약 2배 많은 칩을 판매할 것으로 예상" in raw
    has_safety = "같은 스코틀랜드 회의 현장에서 Huang은 AI 안전" in raw
    has_capital = "• <b>자본환원</b>: NVIDIA 이사회가 자사주 매입 승인 규모를 대폭 확대했습니다." in raw

    query_line = first_line(raw, "<b>조회</b>:")
    official_line = first_line(raw, "<b>공식 기준</b>:")
    scotland_line = first_line(raw, "<b>스코틀랜드 회의</b>:")
    demand_source = first_line(raw, "<b>수요·판매 전망 출처</b>:")
    safety_source = first_line(raw, "<b>안전 발언 출처</b>:")
    capital_source = first_line(raw, "<b>자본환원 출처</b>:")
    capital_official = first_line(raw, "<b>직전 공식 자사주 기준</b>:")
    capital_add = first_line(raw, "• 추가 승인:")
    capital_remaining = first_line(raw, "• 총 잔여 승인한도:")
    capital_horizon = first_line(raw, "• 실행 계획:")
    capital_baseline = first_line(raw, "• 직전 공식 기준(")

    kinds = sum((has_capital, has_demand, has_safety))
    if kinds == 1 and has_capital:
        title = "🚨 <b>NVIDIA 자본환원</b>"
    elif kinds == 1 and has_demand:
        title = "🚨 <b>NVIDIA 수요 변화</b>"
    elif kinds == 1 and has_safety:
        title = "🚨 <b>NVIDIA 안전·출시 신호</b>"
    else:
        title = "🚨 <b>NVIDIA 주요 변화</b>"

    lines: list[str] = [title, "━━━━━━━━━━━━━━━━", "<b>[핵심]</b>"]

    if has_capital:
        for x in (capital_add, capital_remaining):
            if x:
                lines.append(x)
        if capital_horizon:
            lines.append("• 실행: " + _strip_prefix(capital_horizon, "• 실행 계획:"))
        if capital_baseline:
            lines.append("• 직전 공식: " + _strip_prefix(capital_baseline, "• 직전 공식 기준(2026-07-26):"))
    if has_demand:
        lines += [
            "• 2027년 NVIDIA 전체 칩 판매량: <b>약 2배</b> 전망",
            "• FY28 공식 매출 성장 전망: <b>약 +70%</b>",
        ]
    if has_safety:
        lines.append("• 준비되지 않은 제품은 <b>출시 보류 후 추가 개발</b> 원칙")

    lines += ["", "<b>[해석]</b>"]
    if has_capital:
        lines += [
            "• <b>승인한도 ≠ 실제 매입액</b> — 실제 집행 속도가 핵심",
            "• 주당가치 효과: <b>실제 매입액·평균매입가·주식보상 희석·잉여현금흐름</b> 확인",
        ]
    if has_demand:
        lines += [
            "• <b>전체 칩 2배 ≠ AI GPU·HBM 2배</b>",
            "• 실제 매출 전환은 HBM·DRAM·파운드리·첨단패키징·전력 병목에 좌우",
        ]
    if has_safety:
        lines.append("• 원칙적 발언이며 <b>Blackwell·Rubin 실제 일정 지연 신호는 아직 아님</b>")

    lines += ["", "<b>[다음 확인]</b>"]
    if has_capital:
        lines += [
            "• 10-Q·10-K: <b>실제 매입액·매입주식수·평균매입가</b>",
            "• 추가 승인·잔여한도·배당정책 변경",
        ]
    if has_demand:
        lines += [
            "• 제품별 출하량·AI GPU 비중·공급 가능 비율",
            "• HBM·CoWoS·파운드리·전력 병목 순위",
        ]
    if has_safety:
        lines.append("• Blackwell·Rubin 실제 연기·출시 보류 여부")

    refs: list[str] = []
    if has_capital:
        refs += [x for x in (capital_source, capital_official) if x]
    if has_demand:
        refs += [x for x in (official_line, demand_source) if x]
    if has_safety:
        refs += [x for x in (scotland_line, safety_source) if x]
    if query_line:
        refs.append(query_line)

    if refs:
        lines += ["", "<b>[근거]</b>"]
        for ref in refs:
            lines.append(ref)

    ALERT.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
