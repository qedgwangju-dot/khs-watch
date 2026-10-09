#!/usr/bin/env python3
import html
import re

import treasury_credit_flow_watch_readable as readable

app = readable.app
_original_raw_send = readable._original_send


def _yield_value(text, tenor):
    m = re.search(rf"^• {re.escape(tenor)}: ([0-9]+(?:\.[0-9]+)?)%", text, re.M)
    return float(m.group(1)) if m else None


def _market_stress(y10, y30, move10_bp=None, move30_bp=None):
    """Report stress *level* independently of the latest rate direction."""
    if y10 is None:
        head = "판정 대기"
        reason = "미국 10년물 공식 금리가 없어 수준 경보를 판정하지 않음"
    elif y10 >= 5.20:
        head = "적색 — 10년물 5.20% 이상(수준 경보)"
        reason = (
            "과거 9/10 Bloomberg에서 보도된 5.20% 관련 옵션 거래의 기술적 관찰 구간. "
            "현재 잔존 계약·미결제약정·헤지 매도 규모는 미확인 → 새로운 옵션발 매도세로 단정하지 않음"
        )
    elif y10 >= 5.10:
        head = "강한 경계 — 10년물 5.10% 이상(수준 경보)"
        reason = "장기금리 절대 수준이 높아 할인율 부담. 과거 옵션의 현재 헤지 영향은 별도 확인 필요"
    elif y10 >= 5.00:
        head = "경계 — 10년물 5.00% 이상(수준 경보)"
        reason = "10년물 5% 이상인 상태. 신규 상향 돌파인지 여부는 직전 수익률과 비교해야 함"
    elif y10 >= 4.90:
        head = f"접근 경계 — 10년물 5.00%까지 {(5.00 - y10) * 100:.0f}bp"
        reason = "5%에 근접한 금리 수준. 방향은 별도 판정"
    else:
        head = f"5% 미만 — 10년물 5.00%까지 {(5.00 - y10) * 100:.0f}bp"
        reason = "기존 5% 기술 경계선 아래. 위험이 사라졌다는 뜻은 아님"

    if move10_bp is not None:
        direction = "하락" if move10_bp < 0 else "상승" if move10_bp > 0 else "보합"
        reason += f" | 이번 거래일 10년물 {move10_bp:+.0f}bp {direction}"
    if y30 is not None and y30 >= 5.35:
        reason += f" | 30년물 {y30:.2f}%로 절대 수준 부담 지속"
    elif y30 is not None and y30 >= 5.30:
        reason += f" | 30년물 {y30:.2f}%로 5.35% 수준에 근접"
    if move30_bp is not None:
        direction = "하락" if move30_bp < 0 else "상승" if move30_bp > 0 else "보합"
        reason += f" · 당일 30년물 {move30_bp:+.0f}bp {direction}"
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
