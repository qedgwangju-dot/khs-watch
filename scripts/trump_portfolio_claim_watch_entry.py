#!/usr/bin/env python3
"""Readable Korean wrapper for Trump portfolio claim Telegram alerts."""

import datetime as dt
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
                hay = f"{title} {desc}".lower()
                if not link:
                    continue
                if "trump" not in hay and "트럼프" not in hay:
                    continue
                policy_keys = [
                    "congress", "의회", "trading ban", "stock trading", "insider trading",
                    "out-traded", "28,700", "28700", "22,200", "22200",
                ]
                if not any(k in hay for k in policy_keys):
                    continue
                cid = hashlib.sha256(link.encode("utf-8")).hexdigest()[:24]
                out[cid] = {
                    "id": cid,
                    "title": title or "트럼프 증권거래·의회 거래제한 관련 보도",
                    "source": "웹 검색",
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


def build_congress_trade_policy_digest(claims):
    lines = [
        "📊 <b>트럼프 증권거래량 vs 미 의회 — 새 분석</b>",
        "<b>판정  🟡 Bloomberg 집계 보도 + 공식 법안 교차확인</b>",
        "",
        "<b>한눈에 보기</b>",
        "• Bloomberg가 공개 신고를 분석한 결과, 트럼프 또는 자산관리인의 증권 거래는 두 번째 취임 후 2026년 6월 말까지 약 <b>28,700건</b>",
        "• 같은 기간 미 상·하원 의원 전체가 신고한 유사 거래는 약 <b>22,200건</b>",
        "• 차이: 약 <b>6,500건</b> · 트럼프 측 집계가 의회 전체보다 약 <b>29%</b> 많음",
        "• 중요: 28,700건과 22,200건은 <b>Bloomberg의 공개 신고 집계</b>이며 하나의 정부 공식 총계 표에서 나온 숫자는 아닙니다.",
        "",
        "🏛 <b>법안 상태</b>",
        "• 법안: <b>H.R. 7008 Stop Insider Trading Act</b>",
        "• 2026년 7월 22일 하원 통과: <b>232대 198</b>",
        "• 2026년 8월 6일 상원 일정표에 올라간 상태",
        "• 적용 대상: <b>연방 의원·배우자·부양 자녀</b>",
        "• 현행 하원 통과안의 적용 대상 정의에는 <b>대통령이 포함되지 않습니다.</b>",
        "",
        "💼 <b>최근 OGE 거래와 연결</b>",
        "• 6월 신고에는 <b>1,051건</b>의 거래가 포함됐습니다.",
        "• 단일 최대 공개 범위 거래: 6월 22일 <b>VIG 500만~2,500만달러 매도</b>",
        "• 6월 18일 BRK.B·CTAS·V·MA를 각각 <b>100만~500만달러 매수</b>",
        "• Palantir(PLTR)은 같은 달 <b>매수와 매도가 모두 확인</b>돼 단순 ‘대량 순매수’로 표현하면 부정확합니다.",
        "",
        "⚖️ <b>해석 주의</b>",
        "• 거래신고는 거래 사실과 금액 범위를 보여주지만 <b>누가 개별 주문을 결정했는지</b>까지 증명하지 않습니다.",
        "• 백악관은 투자계좌가 독립적으로 관리되는 모델 포트폴리오라고 설명해 왔습니다.",
        "• 거래일과 정책·시장 이벤트가 겹친다는 사실만으로 내부정보 이용이나 동기를 단정하지 않습니다.",
        "",
        "🗞 <b>관련 보도</b>",
    ]

    for i, c in enumerate(claims[:5], 1):
        source, raw_title = _split_source_title(c)
        title_ko = translate_title_ko(raw_title)
        lines += [
            f"<b>{i}. {_e(source)}</b>",
            f"   {_e(title_ko)}",
            f"   {_link('원문', c['url'])}",
        ]

    lines += [
        "",
        f"{_link('H.R. 7008 공식 법안', GOVINFO_HR7008)}  |  {_link('하원 위원회 설명', HOUSE_HR7008)}  |  {_link('OGE 6월 거래신고', watch.OGE_JUNE_TRADES)}",
    ]
    return "\n".join(lines)


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
    policy = [x for x in new if x.get("kind") == "congress_trade_policy"][:5]
    generic = [x for x in new if x.get("kind") not in {"viral_exact_weights", "congress_trade_policy"}][:5]

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

    if policy:
        watch.telegram_api(
            token,
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": build_congress_trade_policy_digest(policy),
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            },
        )
        for c in policy:
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

    if state.get("updated_at") is None:
        for c in claims:
            seen.add(c["id"])
    state["seen"] = sorted(seen)
    watch.save_state(state)


if __name__ == "__main__":
    main_readable()
