#!/usr/bin/env python3
import html
import re

import treasury_credit_flow_watch_ishares as app


_original_send = app.send_exact


def _match(pattern, text, default="확인 대기"):
    m = re.search(pattern, text, re.M)
    return m.group(1).strip() if m else default


def _direction_pair(label, text):
    m = re.search(rf"^{re.escape(label)}: ([^\n]+)\n→ ([^\n]+)", text, re.M)
    if not m:
        return "확인 대기", "세부 자료 확인 대기"
    return m.group(1).strip(), m.group(2).strip()


def _etf_flow(ticker, text):
    m = re.search(
        rf"^{ticker} \([^\n]+\) — [^\n]+\n"
        rf"• 가격: [^\n]+\n"
        rf"• 일간 자금: ([^\n]+)",
        text,
        re.M,
    )
    return m.group(1).strip() if m else "확인 대기"


def _etf_oas(ticker, text):
    m = re.search(
        rf"^{ticker} \([^\n]+\) — [^\n]+\n"
        rf"• 가격: [^\n]+\n"
        rf"• 일간 자금: [^\n]+\n"
        rf"• 최근 5회: [^\n]+\n"
        rf"• 포트폴리오 OAS: ([^\n]+)",
        text,
        re.M,
    )
    return m.group(1).strip() if m else "확인 대기"


def _rate_line(label, text):
    return _match(rf"^• {re.escape(label)}: ([^\n]+)", text)


def _plain_driver(text):
    driver = _match(r"^• 오늘의 주도축: ([^\n]+)", text)
    return driver


def improve_overview(text):
    overall, overall_reason = _direction_pair("전체 자금 방향", text)
    treasury, treasury_reason = _direction_pair("ETF 자금 방향", text)
    credit, credit_reason = _direction_pair("신용자금 방향", text)
    regime, regime_easy = _direction_pair("금리 구조", text)

    shy = _etf_flow("SHY", text)
    ief = _etf_flow("IEF", text)
    tlt = _etf_flow("TLT", text)
    lqd = _etf_flow("LQD", text)
    hyg = _etf_flow("HYG", text)
    lqd_oas = _etf_oas("LQD", text)
    hyg_oas = _etf_oas("HYG", text)

    r2 = _rate_line("2년", text)
    r10 = _rate_line("10년", text)
    r30 = _rate_line("30년", text)
    s210 = _rate_line("2년-10년 금리차", text)
    s1030 = _rate_line("10년-30년 금리차", text)
    back = _match(r"^• 뒷단 해석: ([^\n]+)", text)
    driver = _plain_driver(text)

    overview = [
        "[한눈에 보기]",
        f"전체 방향: {overall}",
        f"→ {overall_reason}",
        "",
        f"국채 자금: SHY {shy} | IEF {ief} | TLT {tlt}",
        f"→ {treasury}: {treasury_reason}",
        "",
        f"회사채 자금: LQD {lqd} | HYG {hyg}",
        f"→ {credit}: {credit_reason}",
        "",
        f"신용 위험: LQD OAS {lqd_oas} | HYG OAS {hyg_oas}",
        "→ 자금유출과 OAS 확대가 함께 나오면 실제 신용위험 악화, OAS가 안정적이면 선제적 위험축소로 판독",
        "",
        f"금리: 2년 {r2} | 10년 {r10} | 30년 {r30}",
        f"커브: {regime} = {regime_easy}",
        f"2년-10년: {s210}",
        f"10년-30년: {s1030}",
        f"→ {back}",
        f"오늘의 주도축: {driver}",
    ]

    new_block = "\n".join(overview)
    pattern = r"\[한눈에 보기\]\n.*?\n\[미 국채 ETF\]"
    if not re.search(pattern, text, re.S):
        return text
    return re.sub(pattern, new_block + "\n\n[미 국채 ETF]", text, count=1, flags=re.S)


def fmt_html(chunk):
    out = []
    bold_prefixes = (
        "전체 방향:",
        "국채 자금:",
        "회사채 자금:",
        "신용 위험:",
        "금리:",
        "커브:",
        "2년-10년:",
        "10년-30년:",
        "오늘의 주도축:",
        "전체 자금 방향:",
        "ETF 자금 방향:",
        "신용자금 방향:",
        "• 현재 형태:",
        "• 오늘의 주도축:",
        "• 신용 위험:",
    )
    for line in chunk.splitlines():
        escaped = html.escape(line, quote=False)
        bold = line in ("[한눈에 보기]", "[오늘의 결론]") or line.startswith(bold_prefixes)
        out.append(f"<b>{escaped}</b>" if bold else escaped)
    return "\n".join(out)


def send_readable(text):
    readable = improve_overview(text)
    (app.base.OUT / "treasury_etf_flow_telegram.txt").write_text(readable + "\n", encoding="utf-8")
    (app.base.OUT / "treasury_etf_flow_status.md").write_text("```\n" + readable + "\n```\n", encoding="utf-8")
    return _original_send(readable)


app.fmt_html = fmt_html
app.send_exact = send_readable


if __name__ == "__main__":
    app.main()
