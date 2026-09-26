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
            (r"BBC 원문:\s*(https?://\S+)", "BBC 원문"),
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

MSTR_SEED = {
    "id": "oge-detail-mstr-2026-07",
    "period": "2026-07",
    "title": "President Trump Discloses He Owns Strategy Stock",
    "source": "Bitcoin Treasuries",
    "published": "2026-09-23",
    "url": "https://ingress-prod.bitcointreasuries.net/news/president-trump-discloses-he-owns-strategy-stock",
}

BBC_AI_SEED = {
    "id": "oge-detail-bbc-big-tech-ai-2026-07",
    "period": "2026-07",
    "title": "Trump reveals millions of dollars' worth of share deals in big tech and AI",
    "source": "BBC 비즈니스",
    "published": "2026-09-23",
    "url": "https://www.bbc.co.uk/news/articles/c6p3kxpp8lezo?at_medium=RSS&at_campaign=rss",
}

BBC_AI_CORRECTION_SEED = {
    "id": "oge-detail-bbc-big-tech-ai-2026-07-corrected-v2",
    "period": "2026-07",
    "title": "Trump reveals millions of dollars' worth of share deals in big tech and AI",
    "source": "BBC 비즈니스",
    "published": "2026-09-23",
    "url": "https://www.bbc.co.uk/news/articles/c6p3kxpp8lezo?at_medium=RSS&at_campaign=rss",
}

FALLBACK_QUERIES = [
    '"Trump" "financial disclosure" bought sold shares',
    '"Trump" "Office of Government Ethics" stock trades',
    '"Trump" "278-T" transaction',
    '트럼프 재산공개 주식 매수 매도 정부윤리청',
    '트럼프 OGE 거래 신고 주식',
    'Trump Strategy MSTR financial disclosure July 2026',
    'Trump MicroStrategy MSTR OGE July stock',
    '"Trump reveals millions of dollars worth of share deals in big tech and AI"',
    'BBC Trump Microsoft Nvidia SpaceX financial disclosure July 2026',
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
        f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko",
    ]


def _strip_tags(text):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


FALLBACK_RECENCY_HOURS = 72

KNOWN_FALLBACK_TITLE_KO = {
    "Trump's Latest Financial Disclosure Shows Significant Sales Of Netflix":
        "트럼프 최신 재산공개, 넷플릭스 증권 대규모 매도 확인",
    "Latest Trump Financial Disclosure Reveals Dubiously Timed Stock Sales":
        "트럼프 최신 재산공개에서 주식 매도 시점 관련 논란 제기",
    "Trump's financial disclosure reveals 18 Coupang stock trades since late last year":
        "트럼프 재산공개, 지난해 말 이후 쿠팡 주식 18건 거래 확인",
    "Donald Trump’s Financial Disclosure Shows Thousands Of Stock Trades In Three Months":
        "트럼프 재산공개, 3개월간 수천 건의 주식 거래 확인",
    "New Trump OGE Filings Reveal Hundreds of Additional April and May Stock Trades, Expanding Earlier Disclosure":
        "트럼프 OGE 추가 신고, 4~5월 수백 건의 추가 주식 거래 공개",
    "Trump Files New Financial Disclosure Showing Massive Bond Trades and Corporate Debt Activity | MSFT Stock News":
        "트럼프 신규 재산공개, 대규모 채권·회사채 거래 공개",
    "Trump bought shares in Elon Musk's SpaceX in June, financial disclosure shows":
        "트럼프 재산공개, 6월 일론 머스크의 SpaceX 주식 매수 확인",
    "Donald Trump's Latest Financial Filing Includes SpaceX Surprise — Report":
        "트럼프 최신 재산공개, 7월 SpaceX 주식 매수·매도 확인",
    "Donald Trump's latest financial filing includes SpaceX surprise — report":
        "트럼프 최신 재산공개, 7월 SpaceX 주식 매수·매도 확인",
    "Trump July disclosure: 1,156 trades, Microsoft and Amazon among largest sales":
        "트럼프 7월 재산공개: 1,156건 거래, Microsoft·Amazon이 최대 매도 종목",
    "Trump reveals millions of dollars' worth of share deals in big tech and AI":
        "트럼프 7월 재산공개, 빅테크·AI 주식 거래 내역 공개",
    "President Trump Discloses He Owns Strategy Stock":
        "트럼프 계좌, 7월 Strategy(MSTR) 주식 추가 매수 확인",
    "Trump Accounts Bought MicroStrategy Stock Before an 83% Rally":
        "트럼프 계좌, 7월 Strategy(MSTR) 주식 재매수 확인",
    "Trump's latest financial disclosure shows he purchased shares of Strategy precisely at its annual low.":
        "트럼프 최신 재산공개, 7월 Strategy(MSTR) 주식 매수 확인",
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


def _machine_translate_title_ko(text):
    """Best-effort translation fallback. Never let a raw English title reach Telegram."""
    q = urllib.parse.urlencode({
        "client": "gtx",
        "sl": "auto",
        "tl": "ko",
        "dt": "t",
        "q": text,
    })
    url = "https://translate.googleapis.com/translate_a/single?" + q
    req = urllib.request.Request(url, headers={"User-Agent": "KHS Trump OGE translate/1.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.load(r)
    parts = []
    for row in data[0] if data and data[0] else []:
        if isinstance(row, list) and row and row[0]:
            parts.append(str(row[0]))
    translated = "".join(parts).strip()
    if translated and re.search(r"[가-힣]", translated):
        return translated
    return ""


def _translate_title_ko(title):
    title = (title or "").strip()
    if not title:
        return "트럼프 OGE 거래 관련 보도"
    core = title.rsplit(" - ", 1)[0].strip() if " - " in title else title
    if core in KNOWN_FALLBACK_TITLE_KO:
        return KNOWN_FALLBACK_TITLE_KO[core]
    if re.search(r"[가-힣]", core):
        return core

    try:
        translated = _machine_translate_title_ko(core)
        if translated:
            return translated
    except Exception as e:
        print(f"WARN OGE title translation failed: {e}")

    low = core.lower()
    if any(k in low for k in ["strategy", "microstrategy", "mstr"]):
        return "트럼프 재산공개에서 Strategy(MSTR) 주식 거래가 확인됐다는 보도"
    if "spacex" in low:
        return "트럼프 재산공개에서 SpaceX 주식 거래가 확인됐다는 보도"
    if "coupang" in low:
        return "트럼프 재산공개에서 쿠팡 주식 거래가 확인됐다는 보도"
    if "netflix" in low:
        return "트럼프 재산공개에서 넷플릭스 증권 거래가 확인됐다는 보도"
    if "bond" in low or "debt" in low:
        return "트럼프 재산공개에서 채권·회사채 거래가 확인됐다는 보도"
    if "thousands" in low and "trade" in low:
        return "트럼프 재산공개에서 수천 건의 증권 거래가 확인됐다는 보도"
    return "트럼프 OGE 신규 거래 관련 보도"


SOURCE_DOMAIN_LABELS = {
    "aol.com": "AOL (Reuters 재배포)",
    "reuters.com": "Reuters",
    "chosun.com": "조선일보",
    "yna.co.kr": "연합뉴스",
    "newrepublic.com": "The New Republic",
    "deadline.com": "Deadline",
    "seekingalpha.com": "Seeking Alpha",
    "bitcointreasuries.net": "Bitcoin Treasuries",
    "finance.yahoo.com": "Yahoo Finance",
    "coindesk.com": "CoinDesk",
    "metatrader.com": "MetaTrader",
    "bbc.co.uk": "BBC 비즈니스",
    "zdnet.co.kr": "ZDNet Korea",
    "msn.com": "MSN",
}


def _publisher_from_link(link):
    try:
        parsed = urllib.parse.urlparse(link or "")
        host = (parsed.hostname or "").lower().removeprefix("www.")
        qs = urllib.parse.parse_qs(parsed.query)
        if "bing.com" in host and qs.get("url"):
            inner = urllib.parse.unquote(qs["url"][0])
            host = (urllib.parse.urlparse(inner).hostname or "").lower().removeprefix("www.")
        for domain, label in SOURCE_DOMAIN_LABELS.items():
            if host == domain or host.endswith("." + domain):
                return label
    except Exception:
        pass
    return ""


def _source_name(item, link=""):
    raw = _strip_tags(item.findtext("source")) or ""
    if raw and raw.lower() not in {"web search", "웹 검색"}:
        return raw
    return _publisher_from_link(link) or "웹 검색"


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
    out = {
        FALLBACK_SEED["id"]: dict(FALLBACK_SEED),
        MSTR_SEED["id"]: dict(MSTR_SEED),
        BBC_AI_SEED["id"]: dict(BBC_AI_SEED),
        BBC_AI_CORRECTION_SEED["id"]: dict(BBC_AI_CORRECTION_SEED),
    }
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
                    "source": _source_name(item, link),
                    "url": link,
                    "published": pub,
                }
    return list(out.values())



FALLBACK_ASSET_KEYS = [
    "spacex", "nvidia", "apple", "microsoft", "meta", "tesla", "palantir",
    "coinbase", "berkshire", "visa", "mastercard", "cintas", "rtx", "northrop",
    "amazon", "alphabet", "google", "home depot", "fidelity",
    "strategy", "microstrategy", "mstr",
]


def _detail_kind(event):
    title = (event.get("title") or "").lower()
    if (
        ("1,156" in title or "1156" in title)
        and "microsoft" in title
        and "amazon" in title
    ):
        return "july-summary-1156-msft-amzn"
    if any(k in title for k in ["strategy", "microstrategy", "mstr", "스트래티지", "마이크로스트래티지"]):
        if any(k in title for k in ["trump", "트럼프", "financial disclosure", "ethics filing", "account", "재산공개", "정부윤리청"]):
            return "july-mstr-trades"
    if event.get("id") == BBC_AI_CORRECTION_SEED["id"]:
        return "july-bbc-big-tech-ai-corrected-v2"
    if event.get("id") == BBC_AI_SEED["id"] or (
        "big tech" in title and "ai" in title and "trump" in title
    ):
        return "july-bbc-big-tech-ai"
    return ""


def _fallback_event_key(event):
    title = (event.get("title") or "").lower()
    period = event.get("period") or "unknown"
    assets = sorted({k.replace(" ", "-") for k in FALLBACK_ASSET_KEYS if k in title})
    if event.get("id") == FALLBACK_SEED["id"]:
        return "oge-event:2026-07:spacex"

    # Reuters/AOL syndications of the Sep. 22 disclosure sometimes omit "July"
    # from the headline, which previously produced an "unknown:spacex" duplicate.
    if "spacex" in title and any(
        marker in title
        for marker in [
            "latest financial filing",
            "financial disclosure shows",
            "bought and sold shares",
            "spacex surprise",
        ]
    ):
        pub = _pub_dt(event.get("published") or "")
        if pub and pub.date() >= dt.date(2026, 9, 22) and pub.date() <= dt.date(2026, 9, 24):
            return "oge-event:2026-07:spacex"

    detail = _detail_kind(event)
    if detail:
        # Known July disclosure details keep one stable key even when a republisher
        # omits "July" from its headline/RSS description.
        fixed_period = {
            "july-mstr-trades": "2026-07",
            "july-summary-1156-msft-amzn": "2026-07",
            "july-bbc-big-tech-ai": "2026-07",
            "july-bbc-big-tech-ai-corrected-v2": "2026-07",
        }.get(detail, period or "unknown")
        return "oge-detail:" + fixed_period + ":" + detail
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
        has_existing_period_detail = any(
            (e.get("period") or "") in seen_periods for e in unique_generic
        )
        july_summary = next(
            (e for e in unique_generic if _detail_kind(e) == "july-summary-1156-msft-amzn"),
            None,
        )
        mstr_detail = next(
            (e for e in unique_generic if _detail_kind(e) == "july-mstr-trades"),
            None,
        )
        bbc_ai_correction = next(
            (e for e in unique_generic if _detail_kind(e) == "july-bbc-big-tech-ai-corrected-v2"),
            None,
        )
        bbc_ai_detail = next(
            (e for e in unique_generic if _detail_kind(e) == "july-bbc-big-tech-ai"),
            None,
        )

        if bbc_ai_correction:
            lines = [
                "🤖 [트럼프 OGE 7월 신고 — 빅테크·AI 거래 정정본]",
                "판정: 기존 7월 OGE 신고의 추가 분석 · 새 신고 아님",
                f"원화 환산 기준: 1달러={rate:,.2f}원 ({basis})",
                "",
                "▶ 한눈에 보기",
                f"• Microsoft 매도 합산: 650만~3,100만달러 ({watch.krw_range(6_500_000, 31_000_000, rate)})",
                f"• Microsoft 매수 합산: 16만5,000~40만달러 ({watch.krw_range(165_000, 400_000, rate)})",
                "• Nvidia·Palantir: 7월 신고에서 매수와 매도가 모두 확인",
                "• SpaceX·Tesla: 7월 신고에서 매수와 매도가 모두 확인",
                "",
                "▶ 추가 교차확인",
                f"• SpaceX 7월 10일 매수: 1만5,001~5만달러 ({watch.krw_range(15_001, 50_000, rate)})",
                f"• SpaceX 7월 17일 매도: 1,001~1만5,000달러 ({watch.krw_range(1_001, 15_000, rate)})",
                "• SpaceX 금액은 Reuters의 동일 OGE 신고 분석으로 교차확인",
                "",
                "▶ 해석 주의",
                "• BBC는 동일한 7월 OGE 신고를 빅테크·AI 종목 중심으로 재구성한 후속 보도입니다.",
                "• Nvidia·Palantir·Tesla의 개별 거래금액은 BBC 본문에서 직접 제시되지 않아 임의 계산하지 않습니다.",
                "• 백악관은 해당 주식·채권 포트폴리오가 제3자에 의해 독립적으로 운용된다는 입장입니다.",
                "• ‘개별 종목 시장 영향 제한적’은 공식 신고 사실이 아니라 별도 시장 해석이므로 확정 사실과 분리합니다.",
                "",
                "▶ 출처",
                f"BBC 원문: {BBC_AI_CORRECTION_SEED['url']}",
                f"Reuters 보도: {SPACE_X_REUTERS_URL}",
                f"OGE 공개목록: {OGE_PUBLIC_LIST}",
            ]
        elif bbc_ai_detail:
            lines = [
                "🤖 [트럼프 OGE 7월 신고 — 빅테크·AI 거래 추가 분석]",
                "판정: 기존 7월 OGE 신고의 추가 세부사항 · 새 신고 아님",
                f"원화 환산 기준: 1달러={rate:,.2f}원 ({basis})",
                "",
                "▶ 한눈에 보기",
                f"• Microsoft 매도 합산: 650만~3,100만달러 ({watch.krw_range(6_500_000, 31_000_000, rate)})",
                f"• Microsoft 매수 합산: 16만5,000~40만달러 ({watch.krw_range(165_000, 400_000, rate)})",
                "• Nvidia·Palantir: 7월 신고에서 매수와 매도가 모두 확인",
                "• SpaceX·Tesla: 7월 신고에서 매수·매도 거래가 함께 확인",
                "",
                "▶ 해석",
                "• BBC는 동일한 7월 OGE 신고를 빅테크·AI 종목 중심으로 재구성한 후속 보도입니다.",
                "• 따라서 새로운 OGE 신고가 아니라 기존 7월 신고의 추가 분석으로 분류합니다.",
                "• ‘개별 종목 시장 영향 제한적’은 기사에서 확인되는 공식 수치가 아니라 별도 시장 해석으로 구분합니다.",
                "",
                "▶ 관련 보도",
            ]
        elif mstr_detail:
            lines = [
                "₿ [트럼프 OGE 7월 신고 — Strategy(MSTR) 추가 거래]",
                "판정: 기존 7월 OGE 신고의 추가 세부사항 · 새 신고 아님",
                f"원화 환산 기준: 1달러={rate:,.2f}원 ({basis})",
                "",
                "▶ 한눈에 보기",
                f"• 7월 8일 Strategy(MSTR) 매도: 1,001~1만5,000달러 ({watch.krw_range(1_001, 15_000, rate)})",
                f"• 7월 24일 Strategy(MSTR) 매수: 1,001~1만5,000달러 ({watch.krw_range(1_001, 15_000, rate)})",
                f"• 7월 27일 Strategy(MSTR) 추가 매수: 5만1~10만달러 ({watch.krw_range(50_001, 100_000, rate)})",
                f"• 두 매수 합산 공개범위: 5만1,002~11만5,000달러 ({watch.krw_range(51_002, 115_000, rate)})",
                "",
                "▶ 해석",
                "• 최대 11만5,000달러는 실제 매수금액이 아니라 두 신고구간의 상한을 더한 값입니다.",
                "• Strategy는 비트코인을 주된 재무준비자산으로 보유하는 상장사이므로 MSTR 매수는 비트코인 간접 노출 확대에 해당합니다.",
                "• 트럼프 본인이 직접 주문했다는 뜻은 아니며, 공개된 거래계좌의 수익자 기준 신고입니다.",
                "",
                "▶ 관련 보도",
            ]
        elif july_summary:
            lines = [
                "📊 [트럼프 OGE 7월 신고 — 추가 세부사항]",
                "판정: 기존 7월 OGE 신고의 추가 분석 · 새 신고 아님",
                f"원화 환산 기준: 1달러={rate:,.2f}원 ({basis})",
                "",
                "▶ 한눈에 보기",
                "• 7월 증권 거래: 1,156건",
                f"• 거래 총액 범위: 7,900만~2억7,000만달러 ({watch.krw_range(79_000_000, 270_000_000, rate)})",
                f"• 매수 하한: 4,360만달러 이상 ({_krw_at_least(43_600_000, rate)})",
                f"• 매도 하한: 3,560만달러 이상 ({_krw_at_least(35_600_000, rate)})",
                "",
                "▶ 주요 거래",
                f"• 7월 20일 Microsoft 매도: 500만~2,500만달러 ({watch.krw_range(5_000_000, 25_000_000, rate)})",
                f"• 7월 20일 Amazon 매도: 500만~2,500만달러 ({watch.krw_range(5_000_000, 25_000_000, rate)})",
                f"• 7월 20일 Oracle 매도: 100만~500만달러 ({watch.krw_range(1_000_000, 5_000_000, rate)})",
                f"• 7월 20일 Nvidia 매수: 50만1~100만달러 ({watch.krw_range(500_001, 1_000_000, rate)})",
                f"• 7월 23일 Microsoft 재매수: 10만1~25만달러 ({watch.krw_range(100_001, 250_000, rate)})",
                f"• 7월 23일 Amazon 재매수: 1,001~1만5,000달러 ({watch.krw_range(1_001, 15_000, rate)})",
                "",
                "▶ 의미",
                "• 앞서 알린 7월 SpaceX 거래와 같은 7월 OGE 신고를 더 넓게 분석한 후속 보도입니다.",
                "• 따라서 ‘새 관련 사건’이 아니라 ‘기존 신고의 추가 세부사항’으로 분류합니다.",
                "",
                "▶ 관련 보도",
            ]
        else:
            heading = (
                "📰 [트럼프 OGE 기존 신고 — 추가 보도 묶음]"
                if has_existing_period_detail
                else "📰 [트럼프 OGE 신규 거래 관련 보도 묶음]"
            )
            count_label = "추가 보도" if has_existing_period_detail else "새 관련 사건"
            lines = [
                heading,
                f"{count_label}: {min(len(unique_generic), 5)}건",
                "",
                "▶ 한눈에 보기",
                "• 최근 72시간 안에 새로 나온 OGE·재산공개 관련 보도만 묶었습니다.",
                "• 과거 기사 재노출은 제외하며, 공식 OGE PDF 직접 감시는 별도로 계속됩니다.",
                "",
                "▶ 관련 보도",
            ]
        if bbc_ai_correction:
            display_events = []
        elif bbc_ai_detail:
            display_events = [bbc_ai_detail]
        elif mstr_detail:
            display_events = [mstr_detail]
        elif july_summary:
            display_events = [july_summary]
        else:
            display_events = unique_generic[:5]
        for i, event in enumerate(display_events, 1):
            lines += [
                f"{i}. {event.get('source') or '웹 검색'}",
                f"   {_translate_title_ko(event.get('title') or '')}",
                f"   원문: {event.get('url')}",
            ]
        if not bbc_ai_correction:
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
