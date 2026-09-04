#!/usr/bin/env python3
import argparse

import war_peace_reconstruction_watch_clean as clean

watch = clean.watch
runner = clean.runner

# Reuters의 /pf/api는 GitHub hosted runner에서 차단될 수 있다.
# robots.txt가 공개하는 Reuters 공식 News Sitemap을 직접 5분마다 읽어 원문 색인 지연을 줄인다.
DIRECT_REUTERS_SITEMAPS = [
    "reuters-sitemap:0",
    "reuters-sitemap:100",
    "reuters-sitemap:200",
    "reuters-sitemap:300",
]

# Google News는 보강 경로다. 1시간 창만 쓰지 않고 6/12/24시간 창을 병행해 색인 지연도 회수한다.
UKRAINE_FAST_QUERIES = [
    'site:reuters.com (Putin OR Zelenskiy OR Zelensky OR Ukraine OR Russia) ("peace deal" OR "peace agreement" OR "chance of peace" OR "constructive peace" OR "new dynamic") when:6h',
    'site:reuters.com (Zelenskiy OR Zelensky OR Ukraine) ("US negotiators" OR "U.S. negotiators" OR "US delegation" OR "U.S. delegation" OR Witkoff OR Kushner) (Moscow OR Kyiv OR Kiev OR visit) when:12h',
    'site:reuters.com (Ukraine OR Russia OR Putin OR Zelenskiy OR Zelensky) peace when:24h',
    'site:reuters.com "Putin cites chance of peace deal" when:24h',
    'site:reuters.com "Zelenskiy says Ukraine expects meeting with US negotiators" when:24h',
    'site:voakorea.com (푸틴 OR 젤렌스키 OR 우크라이나 OR 러시아) (평화협정 OR 평화협상 OR 미국협상단 OR 미국대표단) when:24h',
]

IRAN_BACKFILL_QUERIES = [
    'site:reuters.com (Iran OR Hormuz OR Trump) ("end the war" OR "peace deal" OR ceasefire OR negotiations OR advisers) when:12h',
    'site:wsj.com Iran Trump ("end the war" OR "declare the war over" OR advisers OR midterms) when:24h',
]

# 전쟁·종전 발언이 실제 자산가격으로 번지는 2차 파급도 별도 포착한다.
# 곡물·에너지·귀금속·해운 가격 반응은 '시장 파급'으로 분리해 텔레그램에 노출한다.
MARKET_IMPACT_QUERIES = [
    'site:barchart.com (Putin OR Russia OR Ukraine) (wheat OR grain OR corn OR soybeans) (peace OR deal OR comments OR talks) when:12h',
    'site:reuters.com (Putin OR Russia OR Ukraine) (wheat OR grain OR oil OR gas OR gold) (peace OR deal OR talks OR ceasefire) when:12h',
    'site:barchart.com (Iran OR Hormuz OR Tehran) (crude OR oil OR gold OR natural gas) (strike OR blockade OR ceasefire OR peace) when:12h',
    'site:reuters.com (Iran OR Hormuz OR Tehran) (oil OR tanker OR shipping OR insurance OR gold) (strike OR blockade OR ceasefire OR peace) when:12h',
]

watch.QUERIES = (
    DIRECT_REUTERS_SITEMAPS
    + UKRAINE_FAST_QUERIES
    + IRAN_BACKFILL_QUERIES
    + MARKET_IMPACT_QUERIES
    + list(watch.QUERIES)
)
watch.TRUSTED = tuple(list(watch.TRUSTED) + ["Voice of America", "VOA", "VOA Korea", "Barchart"])
watch.PEACE = list(watch.PEACE) + [
    "chance of peace", "new dynamic", "u.s. delegation", "us delegation",
    "u.s. envoys", "us envoys", "u.s. negotiators", "us negotiators", "negotiators",
    "broker a deal", "broker a possible solution",
    "평화 협정 가능", "평화협정 가능", "미국 협상단", "미국 대표단", "미국 협상대표",
]

_prev_google_news = watch.google_news
_MARKET_QUERIES = set(MARKET_IMPACT_QUERIES)


def _market_signal(row):
    text = (row.get("title_original", "") + " " + row.get("description", "")).lower()
    signals = []
    if "wheat" in text or "밀" in text:
        signals.append("전쟁·종전 발언이 밀 가격에 직접 반영 — 흑해 공급 기대와 곡물 선물 반응 확인")
    elif any(k in text for k in ("corn", "soybean", "grain", "옥수수", "대두", "곡물")):
        signals.append("전쟁·종전 발언이 곡물 가격에 직접 반영 — 흑해 공급·수출 경로 변화 확인")
    elif any(k in text for k in ("oil", "crude", "brent", "wti", "원유", "유가")):
        signals.append("전쟁·종전 변화가 원유 가격에 직접 반영 — 공급차질 위험프리미엄 변화 확인")
    elif any(k in text for k in ("shipping", "tanker", "insurance", "해운", "탱커", "보험")):
        signals.append("전쟁·봉쇄 변화가 해운·탱커·보험 비용에 직접 반영되는지 확인")
    elif any(k in text for k in ("gold", "금 가격", "금값")):
        signals.append("전쟁 위험 변화가 안전자산 수요와 금 가격에 직접 반영되는지 확인")
    else:
        signals.append("전쟁·종전 변화가 실물·금융시장 가격에 직접 반영된 2차 파급 신호")
    return signals


def _reuters_news_sitemap(offset):
    base = "https://www.reuters.com/arc/outboundfeeds/news-sitemap/?outputType=xml"
    if offset:
        base += f"&from={offset}"
    try:
        root = watch.ET.fromstring(watch.req(base, 20))
    except Exception as e:
        return [], f"Reuters news sitemap {offset}: {type(e).__name__}"

    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9", "news": "http://www.google.com/schemas/sitemap-news/0.9"}
    rows = []
    for node in root.findall("sm:url", ns):
        loc = watch.clean(node.findtext("sm:loc", default="", namespaces=ns))
        title = watch.clean(node.findtext("news:news/news:title", default="", namespaces=ns))
        pub = watch.clean(node.findtext("news:news/news:publication_date", default="", namespaces=ns))
        if not loc or not title:
            continue
        row = {
            "title": title,
            "title_original": title,
            "link": loc,
            "published": pub,
            "source": "Reuters",
            "description": "",
        }
        text = title.lower()
        signals = []
        forced_tags = []
        if "putin" in text and any(k in text for k in ("peace deal", "peace agreement", "chance of peace")):
            signals.append("푸틴, 우크라이나 전쟁 종식을 위한 평화 협정 타결 가능성 언급")
            forced_tags.extend(["종전·협상", "시간표"])
        if "zelenski" in text and any(k in text for k in ("negotiators", "delegation", "envoys")):
            signals.append("젤렌스키, 미국 협상단이 우크라이나와 러시아 양국을 곧 방문할 예정이라고 밝혀")
            forced_tags.extend(["종전·협상", "시간표"])
        if any(k in text for k in ("wheat", "grain", "corn", "soybean", "oil", "crude", "brent", "gold", "shipping", "tanker", "insurance")) and any(k in text for k in ("putin", "ukraine", "russia", "iran", "hormuz", "tehran")):
            signals.extend(_market_signal(row))
            forced_tags.append("시장파급")
        if signals:
            row["signals_ko"] = list(dict.fromkeys(signals))
            row["forced_tags"] = list(dict.fromkeys(forced_tags))
            row["deep_signal"] = True
        rows.append(row)
    return rows, None


def google_news_with_reuters_sitemap(query):
    prefix = "reuters-sitemap:"
    if query.startswith(prefix):
        return _reuters_news_sitemap(int(query[len(prefix):] or 0))
    rows, err = _prev_google_news(query)
    if query in _MARKET_QUERIES:
        for row in rows:
            text = (row.get("title_original", "") + " " + row.get("description", "")).lower()
            if not any(k in text for k in ("putin", "ukraine", "russia", "iran", "hormuz", "tehran", "푸틴", "우크라이나", "러시아", "이란", "호르무즈")):
                continue
            row["signals_ko"] = list(dict.fromkeys(list(row.get("signals_ko", [])) + _market_signal(row)))
            tags = list(row.get("forced_tags", [])) + ["시장파급"]
            if any(k in text for k in ("peace", "deal", "talks", "ceasefire", "평화", "종전", "휴전")):
                tags.append("종전·협상")
            if any(k in text for k in ("strike", "attack", "blockade", "missile", "공습", "공격", "봉쇄")):
                tags.append("확전")
            row["forced_tags"] = list(dict.fromkeys(tags))
            row["deep_signal"] = True
    return rows, err


watch.google_news = google_news_with_reuters_sitemap

_prev_score = watch.score_item


def priority_score_item(x, now):
    score, tags = _prev_score(x, now)
    text = (x.get("title_original", "") + " " + x.get("description", "")).lower()
    if any(k in text for k in ("ukraine", "russia", "putin", "zelenskiy", "zelensky", "우크라이나", "러시아", "푸틴", "젤렌스키")):
        if any(k in text for k in ("peace deal", "peace agreement", "chance of peace", "constructive peace", "u.s. delegation", "us delegation", "u.s. envoys", "us envoys", "u.s. negotiators", "us negotiators", "negotiators", "평화협정", "평화 협정", "미국 협상단", "미국 대표단")):
            score += 10
            tags = sorted(set(tags + ["종전·협상", "시간표"]))
    if "시장파급" in x.get("forced_tags", []) or "시장파급" in tags:
        score += 7
        tags = sorted(set(tags + ["시장파급"]))
    return score, tags


watch.score_item = priority_score_item


# Yahoo chartPreviousClose는 range=5d에서 '전일 종가'가 아니라 조회 구간 직전 값이 들어갈 수 있어
# WTI/Brent/DXY 일간 등락률이 며칠 누적치로 잘못 표시됐다. 1일 차트의 previousClose를 우선 사용한다.
def corrected_market_snapshot():
    symbols = {"NQ=F": "나스닥100 선물", "CL=F": "WTI", "BZ=F": "Brent", "DX-Y.NYB": "달러지수"}
    rows = []
    for sym, name in symbols.items():
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{watch.urllib.parse.quote(sym)}?range=1d&interval=5m"
            data = watch.json.loads(watch.req(url, 15).decode())
            r = data["chart"]["result"][0]
            meta = r["meta"]
            px = float(meta.get("regularMarketPrice") or 0)
            prev = float(meta.get("previousClose") or meta.get("chartPreviousClose") or 0)
            if px and prev:
                pct = (px / prev - 1) * 100
                arrow = "▲" if pct > 0 else "▼" if pct < 0 else "－"
                rows.append({
                    "name": name,
                    "price": px,
                    "pct": pct,
                    "arrow": arrow,
                    "basis": "전일 종가 대비",
                    "source": "Yahoo Finance",
                })
        except Exception:
            pass
    return rows


watch.market_snapshot = corrected_market_snapshot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--finalize", action="store_true")
    ap.add_argument("--telegram-test", action="store_true")
    args = ap.parse_args()
    if args.finalize:
        watch.finalize()
        return
    if args.telegram_test:
        clean.write_clean_test()
    else:
        watch.run(test=False)
    runner.verify_alert(test_mode=False)


if __name__ == "__main__":
    main()
