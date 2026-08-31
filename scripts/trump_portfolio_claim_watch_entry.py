#!/usr/bin/env python3
"""Readable Korean wrapper for Trump portfolio claim Telegram alerts."""

import datetime as dt
import html
import json
import re
import urllib.parse
import urllib.request

import trump_portfolio_claim_watch as watch


KNOWN_TITLE_KO = {
    "Nvidia, Tesla, Apple: Trump promoted companies after buying their stocks, says report":
        "엔비디아·테슬라·애플: 트럼프, 해당 종목 매수 후 기업들을 홍보했다는 보도",
    "Trump trades millions in Nvidia, Apple, Microsoft while promoting companies":
        "트럼프, 기업들을 홍보하는 동안 엔비디아·애플·마이크로소프트 주식을 수백만달러 규모로 거래",
    "Trump revamps portfolio, adding Nvidia and other AI names":
        "트럼프, 엔비디아 등 AI 관련주를 추가하며 포트폴리오 재편",
    "Trump's updated portfolio is basically a bet that America wins the AI race.":
        "트럼프의 업데이트된 포트폴리오는 미국이 AI 경쟁에서 승리할 것이라는 베팅에 가깝다",
}


def _needs_korean_translation(text: str) -> bool:
    text = text or ""
    return bool(re.search(r"[A-Za-z]", text)) and not bool(re.search(r"[가-힣]", text))


def _google_translate_ko(text: str) -> str:
    q = urllib.parse.urlencode(
        {"client": "gtx", "sl": "auto", "tl": "ko", "dt": "t", "q": text}
    )
    url = "https://translate.googleapis.com/translate_a/single?" + q
    req = urllib.request.Request(url, headers={"User-Agent": "KHS-Trump-Portfolio-Watch/1.0"})
    with urllib.request.urlopen(req, timeout=12) as r:
        data = json.load(r)
    parts = []
    for row in data[0] if data and data[0] else []:
        if isinstance(row, list) and row and row[0]:
            parts.append(str(row[0]))
    return "".join(parts).strip()


def translate_title_ko(title: str) -> str:
    title = (title or "").strip()
    if not title:
        return "트럼프 포트폴리오 관련 주장"
    if title in KNOWN_TITLE_KO:
        return KNOWN_TITLE_KO[title]
    if not _needs_korean_translation(title):
        return title
    try:
        translated = _google_translate_ko(title)
        if translated and re.search(r"[가-힣]", translated):
            return translated
    except Exception as e:
        print(f"WARN title translation failed: {e}")
    return "한국어 번역 실패 — 원제는 원문 링크에서 확인"


def _split_source_title(c):
    """Google News often appends ' - Publisher' to the title. Keep publisher as identifier."""
    source = (c.get("source") or "웹 검색").strip()
    title = (c.get("title") or "").strip()
    if source == "웹 검색" and " - " in title:
        maybe_title, maybe_source = title.rsplit(" - ", 1)
        if maybe_title.strip() and maybe_source.strip():
            title, source = maybe_title.strip(), maybe_source.strip()
    return source, title


def _e(text):
    return html.escape(str(text or ""))


def _link(label, url):
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'


def build_seed_message_readable(c):
    return "\n".join(
        [
            "🔎 <b>트럼프 포트폴리오 바이럴 주장 검증</b>",
            "<b>판정  🟠 정확한 비중은 공식 확인 불가</b>",
            f"출처: {_e(c.get('source') or 'Milk Road Stocks')} · 게시: {_e(c.get('published') or '')}",
            "",
            "<b>한눈에 보기</b>",
            "• 주장: <b>NVDA 10.0% · TSLA 9.0% · Apple 8.5%</b>가 최신 상위 비중",
            "• 공식 확인: Nvidia·Apple·Palantir 등 기술주 거래 자체는 OGE 신고에 존재",
            "• 공식 미확인: 위 숫자를 전체 포트폴리오의 정확한 비중으로 계산할 근거",
            "• 이미지 오류: <b>표시 비중 합계 94.0%</b> · Apple 티커 <b>APPL → AAPL</b>",
            "",
            "✅ <b>공식자료 대조</b>",
            "• OGE 연례 재산공개는 자산가치를 정확한 단일값이 아니라 법정 금액 범위로 신고합니다.",
            "• OGE Form 278-T는 거래별 금액 범위를 공개하는 문서이지 전체 포트폴리오 비중표가 아닙니다.",
            "• 따라서 NVDA 10.0%·TSLA 9.0%·Apple 8.5%를 OGE 공식 비중으로 인용하면 안 됩니다.",
            "",
            "⚠️ <b>이미지 자체 검산</b>",
            "• 표시된 비중을 모두 더하면 94.0%로 100%가 되지 않아 6.0%가 비어 있습니다.",
            "• Apple 티커도 공식 AAPL이 아니라 APPL로 오기돼 있습니다.",
            "• 따라서 공식 포트폴리오 표가 아니라 2차 제작 인포그래픽으로 봐야 합니다.",
            "",
            "📌 <b>실제로 확인되는 방향</b>",
            "• 트럼프 관련 OGE 신고에는 Nvidia·Apple·Palantir 등 기술주 거래가 실제 존재합니다.",
            "• 그러나 2026년 거래는 금융·산업재·채권·ETF 등에도 걸쳐 있어 ‘AI 14종목 집중 포트폴리오’로 단순화하기 어렵습니다.",
            "",
            "🔎 <b>앞으로의 알림 기준</b>",
            "• 공식 OGE 확인 → <b>확정</b>",
            "• 계산 가정 필요 → <b>추정</b>",
            "• 공식 근거 불충분 → <b>비공식 주장</b>",
            "",
            f"{_link('원문', c['url'])}  |  {_link('OGE 공식 연례보고서', watch.OGE_ANNUAL_PAGE)}  |  {_link('OGE 거래신고', watch.OGE_JUNE_TRADES)}",
        ]
    )


def build_generic_digest(claims):
    lines = [
        "📰 <b>트럼프 포트폴리오 관련 보도 묶음</b>",
        "<b>판정  🟠 비공식 2차 보도 — OGE 교차검증 필요</b>",
        f"새 관련 보도: <b>{len(claims)}건</b>",
        "",
        "<b>한눈에 보기</b>",
        "• 공통 주제: 트럼프 투자계좌의 Nvidia·Apple·Tesla·Microsoft 등 기술주/AI 관련 거래",
        "• 공식 확인 가능한 것: 개별 종목의 매수·매도와 신고 금액 범위",
        "• 공식 확인 불가: 소셜·기사에서 제시하는 정확한 전체 포트폴리오 비중",
        "",
        "🗞 <b>관련 보도</b>",
    ]

    for i, c in enumerate(claims, 1):
        source, raw_title = _split_source_title(c)
        title_ko = translate_title_ko(raw_title)
        lines += [
            f"<b>{i}. {_e(source)}</b>",
            f"   {_e(title_ko)}",
            f"   {_link('원문', c['url'])}",
        ]

    lines += [
        "",
        "✅ <b>검증 기준</b>",
        "• OGE 연례보고서는 자산가치를 법정 금액 범위로 공개합니다.",
        "• OGE Form 278-T도 거래금액을 범위로 공개하므로 기사에 나온 정확한 비중은 자동으로 공식값으로 인정하지 않습니다.",
        "• 같은 종목이 같은 기간에 매수·매도 모두 나타날 수 있어 ‘보유’와 ‘순매수’를 구분합니다.",
        "",
        "📌 <b>알림 해석</b>",
        "• 기사 제목은 한국어로 번역해 표시하고, 매체명·기업명·티커는 식별성을 위해 유지합니다.",
        "• 동일 주제의 복수 기사는 따로 연속 송출하지 않고 한 묶음으로 보여줍니다.",
        "",
        _link("OGE 공식자료", watch.OGE_ANNUAL_PAGE),
    ]
    return "\n".join(lines)


# Override the single seeded-claim format with the new visual hierarchy.
watch.build_seed_message = build_seed_message_readable


def main_readable():
    token = watch.os.environ.get("THIRTEENF_TELEGRAM_BOT_TOKEN") or watch.os.environ.get("KHS_POLICY_TELEGRAM_BOT_TOKEN") or ""
    chat_id = watch.os.environ.get("THIRTEENF_TELEGRAM_CHAT_ID") or watch.os.environ.get("KHS_POLICY_TELEGRAM_CHAT_ID") or ""
    if not token or not chat_id:
        raise RuntimeError("Telegram secrets missing")
    watch.verify_bot(token)

    state = watch.load_state()
    seen = set(state.get("seen", []))
    claims = watch.discover_claims()
    new = [x for x in claims if x["id"] not in seen]
    if not new:
        print("No new Trump portfolio web claim; no Telegram message.")
        watch.save_state(state)
        return

    seeded = [x for x in new if x.get("kind") == "viral_exact_weights"]
    generic = [x for x in new if x.get("kind") != "viral_exact_weights"][:5]

    for c in seeded:
        watch.telegram_api(
            token,
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": build_seed_message_readable(c),
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            },
        )
        seen.add(c["id"])

    if generic:
        watch.telegram_api(
            token,
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": build_generic_digest(generic),
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            },
        )
        for c in generic:
            seen.add(c["id"])

    # On the first scan, mark old indexed results seen to avoid historical backfill spam.
    if state.get("updated_at") is None:
        for c in claims:
            seen.add(c["id"])
    state["seen"] = sorted(seen)
    watch.save_state(state)


if __name__ == "__main__":
    main_readable()
