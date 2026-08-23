#!/usr/bin/env python3
"""Trump OGE Telegram entrypoint with verified wording and compact clickable source link."""

import datetime as dt
import html
import re
from email.utils import parsedate_to_datetime

import trump_oge_portfolio_watch as watch


_original_fx_rate = watch.fx_rate
_original_curated_seed_message = watch.curated_seed_message
_original_generic_message = watch.generic_message


def _krw_at_least(usd_amount: float, rate: float) -> str:
    won = usd_amount * rate
    if won >= 1_000_000_000_000:
        return f"약 {won / 1_000_000_000_000:,.2f}조원 이상"
    return f"약 {won / 100_000_000:,.1f}억원 이상"


def fx_rate_korean_basis():
    """Keep the live FX rate, but show its timestamp in concise Korea time."""
    rate, basis = _original_fx_rate()
    try:
        parsed = parsedate_to_datetime(basis)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        kst = parsed.astimezone(dt.timezone(dt.timedelta(hours=9)))
        basis = kst.strftime("%Y-%m-%d %H:%M KST")
    except Exception:
        pass
    return rate, basis


watch.fx_rate = fx_rate_korean_basis


def _polish_common(text: str) -> str:
    text = text.replace(
        "OGE Form 278-T(정기 거래 신고)",
        "OGE Form 278-T(정기 거래 보고서)",
    )
    text = text.replace(
        "• 백악관/트럼프 측은 자산이 제3자 운용계좌·신탁 구조로 관리돼 대통령이 개별 거래를 지시하지 않는다는 입장입니다.",
        "• 백악관은 투자계좌가 독립적으로 관리되며 대통령과 가족이 해당 계좌를 통제하지 않는다고 설명했습니다.",
    )
    text = text.replace(
        "• 팔란티어(PLTR), RTX(RTX), 노스럽그러먼(NOC), 코인베이스(COIN), 미국 국채·기술주·원자재 ETF, 지방채 등에서 다수 매수·매도",
        "• 팔란티어(PLTR), RTX(RTX), 노스럽그러먼(NOC), 코인베이스(COIN), 미국 국채·기술주·원자재 ETF, 지방채 관련 거래가 확인됐습니다.",
    )
    return text


def curated_seed_message(url, rate, basis):
    text = _polish_common(_original_curated_seed_message(url, rate, basis))
    header = "공시 종류: OGE Form 278-T(정기 거래 보고서)"
    if header in text and "공개일: 2026-08-22" not in text:
        text = text.replace(header, header + "\n공개일: 2026-08-22")

    marker = "• 주의: 위 금액은 6월 거래액 범위 합계이며 전체 보유자산 규모가 아닙니다."
    if marker in text and "매수 총액 하한" not in text:
        extra = "\n".join(
            [
                f"• 매수 총액 하한: 4,900만달러 이상 ({_krw_at_least(49_000_000, rate)})",
                f"• 매도 총액 하한: 2,850만달러 이상 ({_krw_at_least(28_500_000, rate)})",
                marker,
            ]
        )
        text = text.replace(marker, extra)
    return text


def generic_message(url, txs, rate, basis):
    return _polish_common(_original_generic_message(url, txs, rate, basis))


watch.curated_seed_message = curated_seed_message
watch.generic_message = generic_message


def _telegram_html(text: str) -> str:
    """Escape all report text and render only the final OGE source as a compact '원문' link."""
    out = []
    for line in text.splitlines():
        m = re.fullmatch(r"OGE 원문:\s*(https?://\S+)", line.strip())
        if m:
            href = html.escape(m.group(1), quote=True)
            out.append(f'<a href="{href}">원문</a>')
        else:
            out.append(html.escape(line))
    return "\n".join(out)


def send_message_html(token, chat_id, text):
    chunks = []
    current = ""
    for line in text.splitlines(True):
        if len(current) + len(line) > 3600 and current:
            chunks.append(current.rstrip())
            current = line
        else:
            current += line
    if current.strip():
        chunks.append(current.rstrip())

    for chunk in chunks:
        watch.telegram_api(
            token,
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": _telegram_html(chunk),
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            },
        )


watch.send_message = send_message_html


if __name__ == "__main__":
    watch.main()
