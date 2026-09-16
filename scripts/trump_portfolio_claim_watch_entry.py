#!/usr/bin/env python3
"""Readable Korean Trump portfolio claim alerts with event-level dedupe."""

import hashlib
import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

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
    "Trump out-traded all members of Congress combined - report":
        "트럼프 측 증권 거래 건수, 미 의회 전체 합산치 상회 — 보도",
    "Trump Made More Stock Trades Than Congress Combined While Pushing a Trading Ban":
        "트럼프 측 증권 거래 건수, 의회 전체보다 많아…의원 주식거래 제한 법안과 대비",
    "Trump Made More Trades Than All of Congress":
        "트럼프 측 증권 거래 건수, 미 의회 전체 합산치 상회",
    "Trump Clocks More Stock Trades Than Entire Congress Combined":
        "트럼프 측 증권 거래 건수, 미 의회 전체 합산치 상회",
}

POLICY_SEED = {
    "id": "trump-vs-congress-trades-2026-09-15",
    "title": "Trump out-traded all members of Congress combined - report",
    "source": "Bloomberg 분석 인용 보도",
    "published": "2026-09-15",
    "url": "https://www.tradingview.com/news/seekingalpha%3A0af0473d8094b%3A0-trump-out-traded-all-members-of-congress-combined-report/",
    "kind": "congress_trade_policy",
}

POLICY_QUERIES = [
    '"Trump out-traded" Congress',
    'Trump 28700 trades 22200 Congress',
    'Trump stock trades Congress trading ban',
    'Trump "Stop Insider Trading Act" trades',
    '트럼프 거래 의회 전체 주식거래 금지',
]

GOVINFO_HR7008 = "https://www.govinfo.gov/app/details/BILLS-119hr7008eh"
HOUSE_HR7008 = "https://cha.house.gov/press-releases?id=1961B99D-475D-4240-864B-A42F219CF63C"

# These events were already delivered before event-level fingerprints were introduced.
LEGACY_SEEN_EVENT_KEYS = {
    "event:trump-vs-congress-trades-2026-09-15",
    "event:milkroad-trump-ai-portfolio-2026-08-28",
}
LEGACY_SEEN_HEADLINES = {
    "빅테크에다 버크셔·비자 추가로 담았다… 트럼프의 주식 포트폴리오 재편",
}

SOURCE_DOMAIN_MAP = {
    "bloomberg.com": "Bloomberg",
    "seekingalpha.com": "Seeking Alpha",
    "yahoo.com": "Yahoo",
    "msn.com": "MSN",
    "weekly.donga.com": "주간동아",
    "indianexpress.com": "The Indian Express",
    "usatoday.com": "USA Today",
    "investing.com": "Investing.com",
    "mediaite.com": "Mediaite",
    "newser.com": "Newser",
    "substack.com": "Substack",
}

GENERIC_SUFFIXES = {
    "report", "analysis", "update", "updates", "live", "news", "breaking", "exclusive"
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


def _topic_fallback_title_ko(title: str) -> str:
    low = (title or "").lower()
    if "scarborough" in low:
        return "조 스카보로, 트럼프 측 증권 거래량이 의회 전체를 웃돈다는 보도에 반응"
    if "28,700" in low or "28700" in low:
        return "17개월간 약 2만8,700건: 트럼프 관련 계좌의 증권 거래량이 의회 전체를 상회했다는 보도"
    if "congress" in low and any(k in low for k in ["trade", "trading", "outpaced", "out-traded"]):
        return "트럼프 측 증권 거래 건수가 미 의회 전체 합산치를 웃돌았다는 보도"
    if "nvidia" in low and "apple" in low and "microsoft" in low:
        return "트럼프 투자계좌의 엔비디아·애플·마이크로소프트 거래 관련 보도"
    if "nvidia" in low and "tesla" in low and "apple" in low:
        return "트럼프 투자계좌의 엔비디아·테슬라·애플 거래 관련 보도"
    if "portfolio" in low:
        return "트럼프 포트폴리오 재편 관련 보도"
    if "stock" in low or "securit" in low or "trade" in low:
        return "트럼프 증권 거래 관련 보도"
    return "트럼프 포트폴리오 관련 보도"


def translate_title_ko(title: str) -> str:
    title = (title or "").strip()
    if not title:
        return "트럼프 포트폴리오 관련 보도"
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
    # Never pass English through or show a bare 'translation failed' line in Telegram.
    return _topic_fallback_title_ko(title)


def _publisher_from_url(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(url or "")
        host = (parsed.hostname or "").lower().removeprefix("www.")
        qs = urllib.parse.parse_qs(parsed.query)
        # Bing RSS redirect keeps the real article URL in its `url` query parameter.
        if "bing.com" in host and qs.get("url"):
            inner = urllib.parse.unquote(qs["url"][0])
            host = (urllib.parse.urlparse(inner).hostname or "").lower().removeprefix("www.")
        for domain, label in SOURCE_DOMAIN_MAP.items():
            if host == domain or host.endswith("." + domain):
                return label
    except Exception:
        pass
    return ""


def _split_source_title(c):
    source = (c.get("source") or "웹 검색").strip()
    title = (c.get("title") or "").strip()

    if source == "웹 검색":
        derived = _publisher_from_url(c.get("url") or "")
        if derived:
            source = derived

    # Google News often appends ' - Publisher'. Do not mistake '- report' for a publisher.
    if source == "웹 검색" and " - " in title:
        maybe_title, maybe_source = title.rsplit(" - ", 1)
        suffix = maybe_source.strip()
        if (
            maybe_title.strip()
            and suffix
            and suffix.lower() not in GENERIC_SUFFIXES
            and ("." in suffix or " " in suffix or "|" in suffix or len(suffix) >= 6)
        ):
            title, source = maybe_title.strip(), suffix

    # If the feed already gave a publisher, remove only that exact suffix from the title.
    if source != "웹 검색" and title.lower().endswith((" - " + source).lower()):
        title = title[: -(len(source) + 3)].strip()
    return source, title


def _e(text):
    return html.escape(str(text or ""))


def _link(label, url):
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'


def _discover_policy_claims():
    out = {POLICY_SEED["id"]: dict(POLICY_SEED)}
    for query in POLICY_QUERIES:
        for rss_url in watch._rss_urls(query):
            try:
                root = ET.fromstring(watch._get(rss_url))
            except Exception as e:
                print(f"WARN policy RSS fetch/parse failed: {rss_url}: {e}")
                continue
            for item in root.findall(".//item"):
                title = watch._strip_tags(item.findtext("title"))
                link = (item.findtext("link") or "").strip()
                desc = watch._strip_tags(item.findtext("description"))
                pub = watch._strip_tags(item.findtext("pubDate"))
                feed_source = watch._strip_tags(item.findtext("source")) or "웹 검색"
                hay = f"{title} {desc}".lower()
                if not link:
                    continue
                if "trump" not in hay and "트럼프" not in hay:
                    continue
                policy_keys = [
                    "congress", "의회", "trading ban", "stock trading", "insider trading",
                    "out-traded", "outpaced", "28,700", "28700", "22,200", "22200",
                ]
                if not any(k in hay for k in policy_keys):
                    continue
                cid = hashlib.sha256(link.encode("utf-8")).hexdigest()[:24]
                out[cid] = {
                    "id": cid,
                    "title": title or "트럼프 증권거래·의회 거래제한 관련 보도",
                    "source": feed_source,
                    "published": pub or "",
                    "url": link,
                    "kind": "congress_trade_policy",
                }
    return list(out.values())


_original_discover_claims = watch.discover_claims


def discover_claims_extended():
    out = {x["id"]: x for x in _original_discover_claims()}
    for x in _discover_policy_claims():
        out[x["id"]] = x
    return list(out.values())


watch.discover_claims = discover_claims_extended


def _normalize_headline(title: str) -> str:
    title = (title or "").lower()
    # Remove a publisher suffix only when it looks like a publisher, not '- report'.
    if " - " in title:
        left, suffix = title.rsplit(" - ", 1)
        if suffix.strip() not in GENERIC_SUFFIXES and len(suffix.strip()) >= 6:
            title = left
    title = re.sub(r"https?://\S+", " ", title)
    title = re.sub(r"[^0-9a-z가-힣]+", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def _is_material_new_bill_action(title: str) -> bool:
    low = (title or "").lower()
    return any(
        k in low
        for k in [
            "senate passes", "senate passed", "상원 통과", "signed into law", "법률 서명",
            "veto", "거부권", "amended", "수정안 통과", "committee advances", "위원회 통과",
        ]
    )


def event_key(c) -> str:
    kind = c.get("kind") or ""
    if kind == "viral_exact_weights":
        return "event:milkroad-trump-ai-portfolio-2026-08-28"
    if kind == "congress_trade_policy" and not _is_material_new_bill_action(c.get("title") or ""):
        # All syndications of the 28,700-vs-22,200 Bloomberg analysis are one event.
        return "event:trump-vs-congress-trades-2026-09-15"
    normalized = _normalize_headline(c.get("title") or "")
    if not normalized:
        normalized = c.get("url") or c.get("id") or "unknown"
    return "headline:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]


def _legacy_seen_event_keys(state, claims):
    seen_ids = set(state.get("seen", []))
    keys = set(state.get("seen_events", []))
    # Seed known already-delivered events from the pre-migration state.
    if seen_ids:
        keys.update(LEGACY_SEEN_EVENT_KEYS)
        for title in LEGACY_SEEN_HEADLINES:
            keys.add("headline:" + hashlib.sha256(_normalize_headline(title).encode("utf-8")).hexdigest()[:24])
    # Migrate any currently discoverable old raw URL IDs into stable event fingerprints.
    for c in claims:
        if c.get("id") in seen_ids:
            keys.add(event_key(c))
    return keys


def _dedupe_display_claims(claims, limit=5):
    out = []
    seen = set()
    for c in claims:
        source, raw_title = _split_source_title(c)
        key = (source.lower(), _normalize_headline(raw_title))
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
        if len(out) >= limit:
            break
    return out


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
            "",
            "📌 <b>실제로 확인되는 방향</b>",
            "• 트럼프 관련 OGE 신고에는 Nvidia·Apple·Palantir 등 기술주 거래가 실제 존재합니다.",
            "• 그러나 2026년 거래는 금융·산업재·채권·ETF 등에도 걸쳐 있어 ‘AI 14종목 집중 포트폴리오’로 단순화하기 어렵습니다.",
            "",
            f"{_link('원문', c['url'])}  |  {_link('OGE 공식 연례보고서', watch.OGE_ANNUAL_PAGE)}  |  {_link('OGE 거래신고', watch.OGE_JUNE_TRADES)}",
        ]
    )


def build_congress_trade_policy_digest(claims):
    claims = _dedupe_display_claims(claims, limit=5)
    lines = [
        "📊 <b>트럼프 증권거래량 vs 미 의회 — 새 분석</b>",
        "<b>판정  🟡 Bloomberg 집계 보도 + 공식 법안 교차확인</b>",
        "",
        "<b>한눈에 보기</b>",
        "• 트럼프 또는 자산관리인: 약 <b>28,700건</b> · 미 의회 전체: 약 <b>22,200건</b>",
        "• 차이: 약 <b>6,500건</b> · 트럼프 측 집계가 약 <b>29%</b> 많음",
        "• 두 숫자는 <b>Bloomberg의 공개 신고 분석치</b>이며 정부 단일 공식 총계가 아닙니다.",
        "",
        "🏛 <b>법안 상태</b>",
        "• <b>H.R. 7008 Stop Insider Trading Act</b> — 7월 22일 하원 <b>232대198</b> 통과",
        "• 8월 6일 상원 일정표 등재 · 적용 대상은 <b>연방 의원·배우자·부양 자녀</b>",
        "• 현행 하원 통과안의 적용 대상 정의에는 <b>대통령이 포함되지 않습니다.</b>",
        "",
        "💼 <b>최근 OGE 거래</b>",
        "• 6월 신고: <b>1,051건</b>",
        "• 최대 공개 범위: 6월 22일 <b>VIG 500만~2,500만달러 매도</b>",
        "• 6월 18일 BRK.B·CTAS·V·MA 각각 <b>100만~500만달러 매수</b>",
        "• PLTR은 같은 달 매수·매도가 모두 확인돼 단순 순매수로 보면 안 됩니다.",
        "",
        "⚖️ <b>해석 주의</b>",
        "• 신고서는 거래 사실과 금액 범위를 보여주지만 누가 개별 주문을 결정했는지까지 증명하지 않습니다.",
        "• 거래일과 정책·시장 이벤트의 시점 일치만으로 내부정보 이용이나 동기를 단정하지 않습니다.",
        "",
        "🗞 <b>관련 보도</b>",
    ]
    for i, c in enumerate(claims, 1):
        source, raw_title = _split_source_title(c)
        lines += [
            f"<b>{i}. {_e(source)}</b>",
            f"   {_e(translate_title_ko(raw_title))}",
            f"   {_link('원문', c['url'])}",
        ]
    lines += [
        "",
        f"{_link('H.R. 7008 공식 법안', GOVINFO_HR7008)}  |  {_link('하원 위원회 설명', HOUSE_HR7008)}  |  {_link('OGE 6월 거래신고', watch.OGE_JUNE_TRADES)}",
    ]
    return "\n".join(lines)


def build_generic_digest(claims):
    claims = _dedupe_display_claims(claims, limit=5)
    lines = [
        "📰 <b>트럼프 포트폴리오 관련 보도 묶음</b>",
        "<b>판정  🟠 비공식 2차 보도 — OGE 교차검증 필요</b>",
        f"새 독립 주제: <b>{len(claims)}건</b>",
        "",
        "<b>한눈에 보기</b>",
        "• 공식 확인 가능한 것: 개별 종목의 매수·매도와 신고 금액 범위",
        "• 공식 확인 불가: 기사·소셜에서 계산한 정확한 전체 포트폴리오 비중",
        "",
        "🗞 <b>관련 보도</b>",
    ]
    for i, c in enumerate(claims, 1):
        source, raw_title = _split_source_title(c)
        lines += [
            f"<b>{i}. {_e(source)}</b>",
            f"   {_e(translate_title_ko(raw_title))}",
            f"   {_link('원문', c['url'])}",
        ]
    lines += [
        "",
        "✅ <b>검증 기준</b>",
        "• 동일 기사 URL이 바뀌거나 다른 뉴스 집계 링크로 다시 잡혀도 같은 제목·사건이면 재알림하지 않습니다.",
        "• 같은 종목이 같은 기간에 매수·매도 모두 나타날 수 있어 ‘보유’와 ‘순매수’를 구분합니다.",
        "",
        _link("OGE 공식자료", watch.OGE_ANNUAL_PAGE),
    ]
    return "\n".join(lines)


watch.build_seed_message = build_seed_message_readable


def main_readable():
    token = watch.os.environ.get("THIRTEENF_TELEGRAM_BOT_TOKEN") or watch.os.environ.get("KHS_POLICY_TELEGRAM_BOT_TOKEN") or ""
    chat_id = watch.os.environ.get("THIRTEENF_TELEGRAM_CHAT_ID") or watch.os.environ.get("KHS_POLICY_TELEGRAM_CHAT_ID") or ""
    if not token or not chat_id:
        raise RuntimeError("Telegram secrets missing")
    watch.verify_bot(token)

    state = watch.load_state()
    seen_ids = set(state.get("seen", []))
    claims = watch.discover_claims()
    seen_events = _legacy_seen_event_keys(state, claims)

    groups = {}
    for c in claims:
        key = event_key(c)
        if c.get("id") in seen_ids or key in seen_events:
            continue
        groups.setdefault(key, []).append(c)

    if not groups:
        # Persist migrated event fingerprints even when nothing new is sent.
        state["seen_events"] = sorted(seen_events)
        watch.save_state(state)
        print("No new Trump portfolio event; duplicate URLs/headlines suppressed.")
        return

    # Seeded viral claim: one alert per event.
    for key, group in list(groups.items()):
        if group[0].get("kind") != "viral_exact_weights":
            continue
        c = group[0]
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
        seen_events.add(key)
        for x in group:
            seen_ids.add(x["id"])

    # Policy event: bundle all reports about the same underlying event into one message.
    for key, group in list(groups.items()):
        if group[0].get("kind") != "congress_trade_policy" or key in seen_events:
            continue
        watch.telegram_api(
            token,
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": build_congress_trade_policy_digest(group),
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            },
        )
        seen_events.add(key)
        for x in group:
            seen_ids.add(x["id"])

    # Generic claims: one representative per stable headline event, bundled together.
    generic_reps = []
    generic_keys = []
    for key, group in groups.items():
        if key in seen_events or group[0].get("kind") in {"viral_exact_weights", "congress_trade_policy"}:
            continue
        generic_reps.append(group[0])
        generic_keys.append(key)
        if len(generic_reps) >= 5:
            break

    if generic_reps:
        watch.telegram_api(
            token,
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": build_generic_digest(generic_reps),
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            },
        )
        for key in generic_keys:
            seen_events.add(key)
            for x in groups.get(key, []):
                seen_ids.add(x["id"])

    # First-run backfill safety and state persistence.
    if state.get("updated_at") is None:
        for c in claims:
            seen_ids.add(c["id"])
            seen_events.add(event_key(c))
    state["seen"] = sorted(seen_ids)
    state["seen_events"] = sorted(seen_events)
    watch.save_state(state)


if __name__ == "__main__":
    main_readable()
