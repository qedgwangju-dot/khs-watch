#!/usr/bin/env python3
"""Trump OGE Telegram entrypoint with verified wording and compact clickable source link."""

import datetime as dt
import html
import hashlib
import json
import os
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
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
    """Escape report text and render long source URLs as compact clickable labels."""
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        patterns = [
            (r"OGE 원문:\s*(https?://\S+)", "원문"),
            (r"원문:\s*(https?://\S+)", "원문"),
            (r"Reuters 보도:\s*(https?://\S+)", "Reuters 원문"),
            (r"조선일보:\s*(https?://\S+)", "조선일보 원문"),
            (r"OGE 공개목록:\s*(https?://\S+)", "OGE 공개목록"),
        ]
        rendered = False
        for pattern, label in patterns:
            m = re.fullmatch(pattern, stripped)
            if m:
                href = html.escape(m.group(1), quote=True)
                indent = "   " if line.startswith("   ") else ""
                out.append(f'{indent}<a href="{href}">{label}</a>')
                rendered = True
                break
        if not rendered:
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

# OGE 공개목록 반영이 늦거나 URL 형식이 달라져도 새 거래를 놓치지 않도록
# 신뢰보도 기반의 보조 감시를 함께 운용한다. 공식 PDF가 나중에 잡히면
# 거래월(period) 기준으로 중복 송출을 차단한다.
OGE_PUBLIC_LIST = "https://extapps2.oge.gov/201/Presiden.nsf/PAS%20Filings%20by%20Date?OpenView&Start=1&Count=250"
SPACE_X_REUTERS_URL = "https://www.investing.com/news/stock-market-news/trump-bought-and-sold-shares-in-musks-spacex-in-july-financial-disclosure-shows-4911482"
SPACE_X_CHOSUN_URL = "https://chosun.com/economy/money/2026/09/23/FPWCCWW23BCHVOE3FYO32HHBQM"

FALLBACK_SEED = {
    "id": "oge-fallback-spacex-2026-07",
    "period": "2026-07",
    "title": "트럼프, 7월 SpaceX 주식 최대 5만달러 매수·최대 1만5천달러 매도",
    "source": "Reuters·국내보도 교차확인",
    "url": SPACE_X_REUTERS_URL,
}

FALLBACK_QUERIES = [
    '"Trump" "financial disclosure" bought sold shares',
    '"Trump" "Office of Government Ethics" stock trades',
    '"Trump" "278-T" transaction',
    '트럼프 재산공개 주식 매수 매도 정부윤리청',
    '트럼프 OGE 거래 신고 주식',
]

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def _news_get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "KHS Trump OGE fallback/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _rss_urls(query):
    q = urllib.parse.quote_plus(query)
    return [
        f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en",
        f"https://www.bing.com/news/search?q={q}&format=rss",
    ]


def _strip_tags(text):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


FALLBACK_RECENCY_HOURS = 72

KNOWN_FALLBACK_TITLE_KO = {
    "Trump's Latest Financial Disclosure Shows Significant Sales Of Netflix":
        "트럼프 최신 재산공개, Netflix 증권 대규모 매도 확인",
    "Latest Trump Financial Disclosure Reveals Dubiously Timed Stock Sales":
        "트럼프 최신 재산공개에서 주식 매도 시점 관련 논란 제기",
    "Trump's financial disclosure reveals 18 Coupang stock trades since late last year":
        "트럼프 재산공개, 지난해 말 이후 Coupang 주식 18건 거래 확인",
    "Donald Trump’s Financial Disclosure Shows Thousands Of Stock Trades In Three Months":
        "트럼프 재산공개, 3개월간 수천 건의 주식 거래 확인",
    "New Trump OGE Filings Reveal Hundreds of Additional April and May Stock Trades, Expanding Earlier Disclosure":
        "트럼프 OGE 추가 신고, 4~5월 수백 건의 추가 주식 거래 공개",
    "Trump Files New Financial Disclosure Showing Massive Bond Trades and Corporate Debt Activity | MSFT Stock News":
        "트럼프 신규 재산공개, 대규모 채권·회사채 거래 공개",
    "Trump bought shares in Elon Musk's SpaceX in June, financial disclosure shows":
        "트럼프 재산공개, 6월 Elon Musk의 SpaceX 주식 매수 확인",
}


def _pub_dt(pub):
    try:
        d = parsedate_to_datetime(pub or "")
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(dt.timezone.utc)
    except Exception:
        return None


def _is_recent_pub(pub, hours=FALLBACK_RECENCY_HOURS):
    d = _pub_dt(pub)
    if d is None:
        return False
    now = dt.datetime.now(dt.timezone.utc)
    age = now - d
    return dt.timedelta(0) <= age <= dt.timedelta(hours=hours)


def _translate_title_ko(title):
    title = (title or "").strip()
    if not title:
        return "트럼프 OGE 거래 관련 보도"
    core = title.rsplit(" - ", 1)[0].strip() if " - " in title else title
    if core in KNOWN_FALLBACK_TITLE_KO:
        return KNOWN_FALLBACK_TITLE_KO[core]
    if re.search(r"[가-힣]", title):
        return title
    low = title.lower()
    if "spacex" in low:
        return "트럼프 재산공개에서 SpaceX 주식 거래가 확인됐다는 보도"
    if "coupang" in low:
        return "트럼프 재산공개에서 Coupang 주식 거래가 확인됐다는 보도"
    if "netflix" in low:
        return "트럼프 재산공개에서 Netflix 증권 거래가 확인됐다는 보도"
    if "bond" in low or "debt" in low:
        return "트럼프 재산공개에서 채권·회사채 거래가 확인됐다는 보도"
    if "thousands" in low and "trade" in low:
        return "트럼프 재산공개에서 수천 건의 증권 거래가 확인됐다는 보도"
    return "트럼프 OGE 신규 거래 관련 보도"


def _source_name(item):
    return _strip_tags(item.findtext("source")) or "웹 검색"


def _period_from_text(text, published=""):
    low = (text or "").lower()
    year_match = re.search(r"\b(20\d{2})\b", f"{text} {published}")
    year = int(year_match.group(1)) if year_match else dt.datetime.now(dt.timezone.utc).year
    for name, month in _MONTHS.items():
        if re.search(rf"\b{name}\b", low):
            return f"{year:04d}-{month:02d}"
    for month in range(1, 13):
        if f"{month}월" in text:
            return f"{year:04d}-{month:02d}"
    return ""


def _periods_from_transactions(txs):
    out = set()
    for x in txs:
        m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(20\d{2})", x.get("date") or "")
        if m:
            out.add(f"{int(m.group(3)):04d}-{int(m.group(1)):02d}")
    return out


def _discover_fallback_news():
    out = {FALLBACK_SEED["id"]: dict(FALLBACK_SEED)}
    for query in FALLBACK_QUERIES:
        for rss_url in _rss_urls(query):
            try:
                root = ET.fromstring(_news_get(rss_url))
            except Exception as e:
                print(f"WARN OGE fallback RSS failed: {rss_url}: {e}")
                continue
            for item in root.findall(".//item"):
                title = _strip_tags(item.findtext("title"))
                desc = _strip_tags(item.findtext("description"))
                link = (item.findtext("link") or "").strip()
                pub = _strip_tags(item.findtext("pubDate"))
                if not _is_recent_pub(pub):
                    continue
                hay = f"{title} {desc}".lower()
                if not link or ("trump" not in hay and "트럼프" not in hay):
                    continue
                if not any(k in hay for k in [
                    "financial disclosure", "government ethics", "oge", "278-t",
                    "재산공개", "정부윤리청", "거래 신고",
                ]):
                    continue
                if not any(k in hay for k in [
                    "bought", "sold", "purchase", "sale", "shares", "stock",
                    "매수", "매도", "주식", "거래",
                ]):
                    continue
                period = _period_from_text(f"{title} {desc}", pub)
                eid = "oge-news:" + hashlib.sha256(
                    re.sub(r"[^0-9a-z가-힣]+", " ", title.lower()).strip().encode("utf-8")
                ).hexdigest()[:24]
                out[eid] = {
                    "id": eid,
                    "period": period,
                    "title": title or "트럼프 OGE 신규 거래 보도",
                    "source": _source_name(item),
                    "url": link,
                    "published": pub,
                }
    return list(out.values())



FALLBACK_ASSET_KEYS = [
    "spacex", "nvidia", "apple", "microsoft", "meta", "tesla", "palantir",
    "coinbase", "berkshire", "visa", "mastercard", "cintas", "rtx", "northrop",
    "amazon", "alphabet", "google", "home depot", "fidelity",
]


def _fallback_event_key(event):
    title = (event.get("title") or "").lower()
    period = event.get("period") or "unknown"
    assets = sorted({k.replace(" ", "-") for k in FALLBACK_ASSET_KEYS if k in title})
    if event.get("id") == FALLBACK_SEED["id"]:
        return "oge-event:2026-07:spacex"
    if assets:
        return "oge-event:" + period + ":" + ",".join(assets)
    normalized = re.sub(r"[^0-9a-z가-힣]+", " ", title).strip()
    return "oge-event:" + hashlib.sha256((period + "|" + normalized).encode("utf-8")).hexdigest()[:24]


def _fallback_message(event, rate, basis):
    if event.get("id") == FALLBACK_SEED["id"]:
        return "\n".join([
            "📊 [트럼프 OGE 신규 거래 — 2026년 7월]",
            "판정: OGE 공시 기반 보도 교차확인 · 공식 PDF 직접주소 자동 탐색 보강 중",
            f"원화 환산 기준: 1달러={rate:,.2f}원 ({basis})",
            "",
            "▶ 한눈에 보기",
            f"• 7월 10일 SpaceX 매수: 1만5,001~5만달러 ({watch.krw_range(15_001, 50_000, rate)})",
            f"• 7월 17일 SpaceX 매도: 1,001~1만5,000달러 ({watch.krw_range(1_001, 15_000, rate)})",
            "• 신고서 서명일: 2026년 9월 8일 · OGE 게시: 9월 22일",
            "• 7월 전체 거래: 1,000건 이상",
            "",
            "▶ 이전 거래와 연결",
            f"• 6월 23일에도 SpaceX 1만5,001~5만달러 매수 ({watch.krw_range(15_001, 50_000, rate)})",
            "• 연방 재산공개는 정확한 거래액이 아니라 법정 범위로 신고하므로 실제 매수·매도 금액은 확정할 수 없습니다.",
            "",
            "▶ 출처",
            f"Reuters 보도: {SPACE_X_REUTERS_URL}",
            f"조선일보: {SPACE_X_CHOSUN_URL}",
            f"OGE 공개목록: {OGE_PUBLIC_LIST}",
        ])

    return "\n".join([
        "📊 [트럼프 OGE 신규 거래 보도 감지]",
        f"출처: {event.get('source') or '웹 검색'}",
        f"제목: {_translate_title_ko(event.get('title') or '')}",
        f"거래 기준월: {event.get('period') or '자동 판정 불가'}",
        "",
        "• OGE 공개목록의 직접 PDF URL 탐색과 병행하는 보조 감시입니다.",
        "• 공식 PDF가 직접 잡히기 전에는 기사 숫자를 OGE 원문 직접 추출치로 승격하지 않습니다.",
        f"원문: {event.get('url')}",
        f"OGE 공개목록: {OGE_PUBLIC_LIST}",
    ])


def main_with_fallback():
    token = os.environ.get("THIRTEENF_TELEGRAM_BOT_TOKEN") or os.environ.get("KHS_POLICY_TELEGRAM_BOT_TOKEN") or ""
    chat_id = os.environ.get("THIRTEENF_TELEGRAM_CHAT_ID") or os.environ.get("KHS_POLICY_TELEGRAM_CHAT_ID") or ""
    if not token or not chat_id:
        raise RuntimeError("Telegram secrets missing")
    watch.verify_bot(token)

    state = watch.load_state()
    seen_urls = set(state.get("seen", []))
    # seen_urls: exact OGE filing URLs already sent.
    # seen_news: exact fallback news events already sent.
    # seen_periods is informational only; it must never suppress a different filing in the same month.
    seen_periods = set(state.get("seen_periods", []))
    seen_news = set(state.get("seen_news_events", []))
    seen_news_event_keys = set(state.get("seen_news_event_keys", []))

    if watch.filing_key(watch.SEED_CURRENT_URL) in seen_urls:
        seen_periods.add("2026-06")

    rate, basis = watch.fx_rate()

    urls = watch.discover_trump_278t_urls()
    for url in [u for u in urls if watch.filing_key(u) not in seen_urls]:
        key = watch.filing_key(url)
        txs = []
        periods = set()
        if urllib.parse.unquote(url).lower() == urllib.parse.unquote(watch.SEED_CURRENT_URL).lower():
            periods = {"2026-06"}
            msg = watch.curated_seed_message(url, rate, basis)
        else:
            try:
                text = watch.pdf_text(url)
                txs = watch.extract_transactions(text)
                periods = _periods_from_transactions(txs)
            except Exception as e:
                print(f"WARN PDF parse failed {url}: {e}")
                txs = []
            msg = watch.generic_message(url, txs, rate, basis)

        watch.send_message(token, chat_id, msg)
        seen_urls.add(key)
        seen_periods.update(periods)

    fallback_events = _discover_fallback_news()

    # Migrate already-seen raw article IDs into stable event fingerprints.
    for event in fallback_events:
        if (event.get("id") or "") in seen_news:
            seen_news_event_keys.add(_fallback_event_key(event))

    pending_fallback = []
    for event in fallback_events:
        eid = event.get("id") or ""
        ekey = _fallback_event_key(event)
        if ekey in seen_news_event_keys:
            seen_news.add(eid)
            continue
        pending_fallback.append(event)

    curated = [e for e in pending_fallback if e.get("id") == FALLBACK_SEED["id"]]
    generic = [e for e in pending_fallback if e.get("id") != FALLBACK_SEED["id"]]

    for event in curated:
        watch.send_message(token, chat_id, _fallback_message(event, rate, basis))
        seen_news.add(event.get("id") or "")
        seen_news_event_keys.add(_fallback_event_key(event))
        if event.get("period"):
            seen_periods.add(event["period"])

    # Fresh supporting articles are bundled into one digest instead of one Telegram message per URL.
    unique_generic = []
    used_keys = set()
    for event in generic:
        ekey = _fallback_event_key(event)
        if ekey in used_keys:
            seen_news.add(event.get("id") or "")
            continue
        used_keys.add(ekey)
        unique_generic.append(event)

    if unique_generic:
        lines = [
            "📰 [트럼프 OGE 신규 거래 관련 보도 묶음]",
            f"새 관련 사건: {min(len(unique_generic), 5)}건",
            "",
            "▶ 한눈에 보기",
            "• 최근 72시간 안에 새로 나온 OGE·재산공개 관련 보도만 묶었습니다.",
            "• 과거 기사 재노출은 제외하며, 공식 OGE PDF 직접 감시는 별도로 계속됩니다.",
            "",
            "▶ 관련 보도",
        ]
        for i, event in enumerate(unique_generic[:5], 1):
            lines += [
                f"{i}. {event.get('source') or '웹 검색'}",
                f"   {_translate_title_ko(event.get('title') or '')}",
                f"   원문: {event.get('url')}",
            ]
        lines += ["", f"OGE 공개목록: {OGE_PUBLIC_LIST}"]
        watch.send_message(token, chat_id, "\n".join(lines))

        for event in generic:
            seen_news.add(event.get("id") or "")
            seen_news_event_keys.add(_fallback_event_key(event))
            if event.get("period"):
                seen_periods.add(event["period"])

    state["seen"] = sorted(seen_urls)
    state["seen_periods"] = sorted(seen_periods)
    state["seen_news_events"] = sorted(seen_news)
    state["seen_news_event_keys"] = sorted(seen_news_event_keys)
    watch.save_state(state)


if __name__ == "__main__":
    main_with_fallback()
