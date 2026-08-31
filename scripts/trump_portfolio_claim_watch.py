#!/usr/bin/env python3
"""Monitor web-indexed Trump portfolio claims and send verified Telegram alerts.

This is intentionally separate from the official OGE filing monitor. It catches
secondary/social claims such as exact portfolio-weight graphics, then labels
what is and is not supported by OGE disclosures.
"""

import datetime as dt
import hashlib
import html
import json
import os
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

STATE_PATH = pathlib.Path("data/trump_portfolio_claim_watch_state.json")
EXPECTED_BOT_USERNAME = "khs887988798879_bot"

# Official references used for verification context.
OGE_ANNUAL_PAGE = "https://www2.oge.gov/web/oge.nsf/Resources/Now%2BAvailable%3A%2BThe%2BPresident%E2%80%99s%2Band%2BVice%2BPresident%E2%80%99s%2Bcertified%2Bannual%2Bfinancial%2Bdisclosure%2Breports"
OGE_JUNE_TRADES = "https://extapps2.oge.gov/201/Presiden.nsf/PAS+Index/2BF91F890F718ACB85258E5B002DE16B/$FILE/Donald-J-Trump-08.12.2026-278T.pdf"

# Current viral claim that motivated this watcher. Seeded so the first run sends
# one verification alert even if an RSS index is temporarily delayed.
SEED_CLAIMS = [
    {
        "id": "milkroad-trump-ai-portfolio-2026-08-28",
        "title": "Trump's updated portfolio is basically a bet that America wins the AI race.",
        "source": "Milk Road Stocks",
        "published": "2026-08-28",
        "url": "https://www.investmentwatchblog.com/trumps-updated-portfolio-is-basically-a-bet-that-america-wins-the-ai-race/",
        "kind": "viral_exact_weights",
    }
]

QUERIES = [
    '"Trump\'s updated portfolio"',
    'Trump portfolio Nvidia Tesla Apple',
    '"Milk Road Stocks" Trump portfolio',
    '트럼프 포트폴리오 엔비디아 테슬라 애플',
    'Trump portfolio allocation NVDA TSLA AAPL',
]


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 KHS Trump Portfolio Claim Watch"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _rss_urls(query):
    q = urllib.parse.quote_plus(query)
    return [
        f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en",
        f"https://www.bing.com/news/search?q={q}&format=rss",
    ]


def _strip_tags(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def discover_claims():
    out = {x["id"]: dict(x) for x in SEED_CLAIMS}
    for query in QUERIES:
        for rss_url in _rss_urls(query):
            try:
                root = ET.fromstring(_get(rss_url))
            except Exception as e:
                print(f"WARN RSS fetch/parse failed: {rss_url}: {e}")
                continue
            for item in root.findall(".//item"):
                title = _strip_tags(item.findtext("title"))
                link = (item.findtext("link") or "").strip()
                desc = _strip_tags(item.findtext("description"))
                pub = _strip_tags(item.findtext("pubDate"))
                hay = f"{title} {desc}".lower()
                if not link:
                    continue
                if "trump" not in hay and "트럼프" not in hay:
                    continue
                if not any(k in hay for k in ["portfolio", "포트폴리오", "holding", "allocation", "nvda", "nvidia"]):
                    continue
                cid = hashlib.sha256(link.encode("utf-8")).hexdigest()[:24]
                out[cid] = {
                    "id": cid,
                    "title": title or "트럼프 포트폴리오 관련 주장",
                    "source": "웹 검색",
                    "published": pub or "",
                    "url": link,
                    "kind": "web_claim",
                }
    return list(out.values())


def telegram_api(token, method, params=None):
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(params or {}).encode("utf-8") if params is not None else None
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=25) as r:
        payload = json.load(r)
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {payload}")
    return payload["result"]


def verify_bot(token):
    me = telegram_api(token, "getMe")
    username = me.get("username", "")
    if username.lower() != EXPECTED_BOT_USERNAME.lower():
        raise RuntimeError(f"Telegram bot mismatch: expected @{EXPECTED_BOT_USERNAME}, got @{username or 'unknown'}")
    return username


def _link(label, url):
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'


def build_seed_message(c):
    # Image weights: 10+9+8.5+7.5+7+6.5+6+5.5+5+5+5+4.5+4+3.5+3+4 = 94%.
    lines = [
        "🔎 [트럼프 포트폴리오 바이럴 주장 검증]",
        f"출처: {c['source']} | 게시: {c['published']}",
        "",
        "▶ 주장",
        "• NVDA 10.0%, TSLA 9.0%, Apple 8.5%가 트럼프의 최신 포트폴리오 상위 비중이라는 인포그래픽이 확산 중",
        "• 전체적으로 미국의 AI 경쟁 승리에 베팅한 포트폴리오라는 해석",
        "",
        "▶ 공식자료 대조 판정: 정확한 비중은 공식 확인 불가",
        "• OGE 연례 재산공개는 자산가치를 정확한 단일값이 아니라 법정 금액 범위로 신고합니다.",
        "• 278-T는 거래별 금액 범위를 공개하는 문서이지 전체 포트폴리오 비중표가 아닙니다.",
        "• 따라서 NVDA 10.0%·TSLA 9.0%·Apple 8.5%를 OGE 공식 비중으로 인용하면 안 됩니다.",
        "",
        "▶ 이미지 자체 검산",
        "• 표시된 모든 비중을 합치면 94.0%로 100%가 되지 않아 6.0%가 비어 있습니다.",
        "• Apple 티커도 공식 AAPL이 아니라 APPL로 오기돼 있습니다.",
        "• 이 두 가지 때문에 공식 포트폴리오 표가 아니라 2차 제작 인포그래픽으로 봐야 합니다.",
        "",
        "▶ 실제로 확인되는 방향",
        "• 트럼프 관련 OGE 신고에는 Nvidia·Apple·Palantir 등 기술주 거래가 실제 존재합니다.",
        "• 그러나 2026년 거래는 기술주뿐 아니라 금융·산업재·채권·ETF 등 수천 건에 걸쳐 있어 'AI 14종목 집중 포트폴리오'로 단순화하기 어렵습니다.",
        "",
        "▶ 알림 기준",
        "• 앞으로 이런 포트폴리오 비중표·소셜 주장도 별도 감시합니다.",
        "• 공식 OGE에서 확인되면 '확정', 계산 가정이 필요하면 '추정', 근거가 맞지 않으면 '비공식 주장'으로 분리해 보냅니다.",
        "",
        f"{_link('원문', c['url'])}  |  {_link('OGE 공식 연례보고서', OGE_ANNUAL_PAGE)}  |  {_link('OGE 거래신고', OGE_JUNE_TRADES)}",
    ]
    return "\n".join(lines)


def build_generic_message(c):
    lines = [
        "🔎 [트럼프 포트폴리오 주장 새 변화]",
        f"출처: {c.get('source') or '웹'}",
        f"제목: {c.get('title') or '트럼프 포트폴리오 관련 주장'}",
        "",
        "판정: 비공식 2차 주장 — 공식 OGE 교차검증 필요",
        "• OGE는 연례 자산가치를 범위로, 278-T 거래금액도 범위로 공개하므로 소셜미디어의 정확한 포트폴리오 비중은 자동으로 공식값으로 승격하지 않습니다.",
        "• 새로운 종목·비중·매수·매도 주장이 확인되면 공식 OGE 신고와 대조해 후속 알림합니다.",
        "",
        f"{_link('원문', c['url'])}  |  {_link('OGE 공식자료', OGE_ANNUAL_PAGE)}",
    ]
    return "\n".join(lines)


def load_state():
    if not STATE_PATH.exists():
        return {"version": 1, "seen": [], "updated_at": None}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "seen": [], "updated_at": None}


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    token = os.environ.get("THIRTEENF_TELEGRAM_BOT_TOKEN") or os.environ.get("KHS_POLICY_TELEGRAM_BOT_TOKEN") or ""
    chat_id = os.environ.get("THIRTEENF_TELEGRAM_CHAT_ID") or os.environ.get("KHS_POLICY_TELEGRAM_CHAT_ID") or ""
    if not token or not chat_id:
        raise RuntimeError("Telegram secrets missing")
    verify_bot(token)

    state = load_state()
    seen = set(state.get("seen", []))
    claims = discover_claims()
    new = [x for x in claims if x["id"] not in seen]
    if not new:
        print("No new Trump portfolio web claim; no Telegram message.")
        save_state(state)
        return

    # Prevent broad RSS spam: always send the seeded current claim; for web claims,
    # only send the newest few in one run.
    seeded = [x for x in new if x.get("kind") == "viral_exact_weights"]
    generic = [x for x in new if x.get("kind") != "viral_exact_weights"][:3]
    for c in seeded + generic:
        msg = build_seed_message(c) if c.get("kind") == "viral_exact_weights" else build_generic_message(c)
        telegram_api(
            token,
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": msg,
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            },
        )
        seen.add(c["id"])

    # Mark all discovered results seen after first scan to avoid old-search backfill spam.
    if state.get("updated_at") is None:
        for c in claims:
            seen.add(c["id"])
    state["seen"] = sorted(seen)
    save_state(state)


if __name__ == "__main__":
    main()
