#!/usr/bin/env python3
import html
import re

import treasury_credit_flow_watch_readable as readable

app = readable.app
_original_raw_send = readable._original_send


def _yield_value(text, tenor):
    m = re.search(rf"^• {re.escape(tenor)}: ([0-9]+(?:\.[0-9]+)?)%", text, re.M)
    return float(m.group(1)) if m else None


def _market_stress(y10, y30):
    if y10 is None:
        head = "판정 대기"
        reason = "10년물 공식값을 확인하지 못해 5% 옵션·헤지 구간 판정 보류"
    elif y10 >= 5.20:
        head = "적색 — 10년물 5.20% 이상"
        reason = "9/10 Bloomberg 보도 대형 옵션 거래의 5.20% 수익 확대 구간까지 진입 → 옵션·컨벡시티 헤지가 국채 매도세를 증폭할 위험이 큼"
    elif y10 >= 5.10:
        head = "강한 경계 — 10년물 5.10% 이상"
        reason = "9/10 Bloomberg 보도 대형 옵션 거래의 손익분기점 부근/상회 → 추가 금리상승 헤지와 마켓메이커 컨벡시티 대응이 매도 압력을 키울 수 있음"
    elif y10 >= 5.00:
        head = "경계 — 10년물 5% 돌파"
        reason = "심리적 5%선 돌파 → 금리상승 헤지 수요와 기술적 매도가 서로 증폭되는지 확인할 구간"
    elif y10 >= 4.90:
        gap = (5.00 - y10) * 100
        head = f"접근 경계 — 10년물 5%까지 {gap:.0f}bp"
        reason = "5% 심리선에 근접 → 옵션·컨벡시티 헤지가 본격화되기 전 선제 경계 구간"
    else:
        gap = (5.00 - y10) * 100
        head = f"정상 — 10년물 5%까지 {gap:.0f}bp"
        reason = "5% 기술적 스트레스 구간과 아직 거리가 있어 옵션 헤지발 증폭 위험은 상대적으로 낮음"

    if y30 is not None and y30 >= 5.35:
        reason += " | 30년물도 5.35% 이상이면 뒷단 재정·기간프리미엄 스트레스까지 동시 확인"
    elif y30 is not None and y30 >= 5.30:
        reason += f" | 30년물 {y30:.2f}%로 5.35% 스트레스선에 근접"
    return head, reason


def _insert_market_stress(text):
    y10 = _yield_value(text, "10년")
    y30 = _yield_value(text, "30년")
    head, reason = _market_stress(y10, y30)
    block = f"시장 기술압력: {head}\n→ {reason}"

    # 한눈에 보기에서 자료 기준일 직전에 삽입해 방향 → 기술압력 → 기준일 순서로 읽히게 한다.
    marker = "\n자료 기준일:"
    if marker in text:
        text = text.replace(marker, "\n\n" + block + marker, 1)
    else:
        text += "\n\n" + block
    return text


def _format_html(chunk):
    out = []
    bold_prefixes = (
        "전체 방향:", "국채 자금:", "회사채 자금:", "신용 위험:",
        "성장-차입비용:", "기업이익:", "위험 전환 경보:",
        "금리:", "커브:", "2년-10년:", "10년-30년:",
        "오늘의 주도축:", "시장 기술압력:", "자료 기준일:",
        "전체 자금 방향:", "ETF 자금 방향:", "신용자금 방향:",
        "• 현재 형태:", "• 오늘의 주도축:", "• 신용 위험:",
    )
    for line in chunk.splitlines():
        escaped = html.escape(line, quote=False)
        bold = line in ("[한눈에 보기]", "[오늘의 결론]") or line.startswith(bold_prefixes)
        out.append(f"<b>{escaped}</b>" if bold else escaped)
    return "\n".join(out)


def send_marketstress(raw_text):
    text = readable.improve_overview(raw_text)
    text = _insert_market_stress(text)
    (app.base.OUT / "treasury_etf_flow_telegram.txt").write_text(text + "\n", encoding="utf-8")
    (app.base.OUT / "treasury_etf_flow_status.md").write_text("```\n" + text + "\n```\n", encoding="utf-8")
    app.fmt_html = _format_html
    return _original_raw_send(text)


app.send_exact = send_marketstress


if __name__ == "__main__":
    app.main()
