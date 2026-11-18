#!/usr/bin/env python3
"""Foldable smartphone adoption and Apple retail-access watch.

Evidence and state rules:
* Samsung Fold8 +16% = executive-reported customer demand SINCE launch,
  not +16% unit sales and not the Korean weekly +10% reported in September.
* +300% is Google SEARCH interest for Samsung foldables last month, not sales.
* Apple KR/JP notices restrict walk-in purchase for Duo and iPhone 18 Pro Max,
  without cancelling the official October 23 launch.
* IDC/TrendForce are independent 2026 forecast series, not a single actual total.
* Official current Apple policy controls require live Apple-domain retrieval.
* No alarm is produced on an unavailable official site or syndicated repeats.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "apple_foldable_market_access_state.json"
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)
PENDING = OUT / "apple_foldable_market_access_pending_state.json"
STATUS = OUT / "apple_foldable_market_access_status.md"
ALERT = OUT / "apple_foldable_market_access_alert.html"
TELEGRAM = OUT / "apple_duo_supply_watch_telegram.txt"
KST = ZoneInfo("Asia/Seoul")
FORBES = "https://www.forbes.com/sites/davidphelan/2026/10/14/apples-iphone-duo-debut-drives-300-spike-in-samsung-galaxy-z-fold8-searches/"
APPLE_KR = "https://www.apple.com/kr/iphone/"
APPLE_JP = "https://www.apple.com/jp/iphone/?cid=MAR-JP-GOOG-IPHONE"
APPLE_SCHEDULE = "https://www.apple.com/kr/newsroom/2026/10/open-up-to-new-possibilities-with-iphone-duo/"
IDC = "https://www.idc.com/promo/smartphone-market-share/market-share/"
TRENDFORCE = "https://www.trendforce.com/presscenter/news/20260910-13228.html"
BASELINE = {
    "fold8_demand_change_pct": 16.0,
    "fold8_demand_context": "삼성전자 영국·아일랜드 모바일 임원 Forbes 인터뷰·출시 이후·지역별 절대판매대수 미공개",
    "samsung_foldable_google_search_change_pct": 300.0,
    "samsung_search_context": "삼성 폴더블 관련 구글 검색 관심도·최근 한 달·구매전환 미확인",
    "fold8_korea_sales_wow_pct": 10.0,
    "fold8_korea_context": "2026-09-17 국내 통신업계 보도·공개 후 1주·기존 별도 기준선",
    "idc_2026_foldable_m": 22.9,
    "idc_2026_foldable_yoy_pct": 12.6,
    "trendforce_2026_foldable_m": 20.2,
    "trendforce_2026_foldable_yoy_pct": 0.5,
    "official_launch_date": "2026-10-23",
}
SENTIMENT_STUDY_KEY = "quettai_hankyung_20261118_fold8_vs_duo_2026jan_oct"
SENTIMENT_STUDY = {
    "source_kind": "한경·뉴엔AI 퀘타아이 민간 소셜게시물 AI 감성분석·제조사 공식 실판매 아님",
    "published_date": "2026-11-18",
    "observation_period": "2026-01-01..2026-10-31",
    "source_url": "https://www.hankyung.com/article/202611172385g",
    "fold8_positive_pct": 50.2,
    "fold8_negative_pct": 8.3,
    "duo_positive_pct": 21.2,
    "duo_negative_pct": 24.6,
    "fold8_net_sentiment_pp": 41.9,
    "duo_net_sentiment_pp": -3.4,
    "net_sentiment_gap_pp": 45.3,
    "fold8_mention_count_reported": 109825,
    "duo_mention_count_reported": 72070,
    "naver_search_period": "2026-10-13..2026-11-12",
    "fold8_naver_search_count": 103000,
    "duo_naver_search_count": 588800,
    "search_is_sales": False,
    "sample_versus_market": "게시물 감정·검색 관심도. 전체 소비자 선호도·판매대수·기술 세대 증명 아님",
    "independent_directional_source": "https://blog.hashscraper.com/posts/why-was-the-iphone-duo-remembered-for-its-hinge-iphone-duo-vs-galaxy-fold8-through-2-485-social-mentions-in-their-first-week-after-launch?locale=ko",
    "independent_sample_period": "2026-10-22..2026-10-28",
    "independent_classified_posts_fold8": 838,
    "independent_classified_posts_duo": 1047,
    "independent_negative_pct_fold8": 17.5,
    "independent_negative_pct_duo": 51.5,
    "independent_denominator_note": "해시스크래퍼는 뉴스 포함·출시 첫주 표본, 퀘타아이와 비율 합산 금지",
    "fold8_korean_weekly_sales_change_at_least_pct_reported": 20.0,
    "fold8_korean_weekly_sales_period": "2026-10-23..2026-10-29 vs 2026-10-16..2026-10-22",
    "fold8_sales_source": "https://nwww.newsis.com/view/NISX20261103_0003851966",
    "fold8_sales_status": "통신업계 익명 보도·실제 절대 판매 대수·삼성 공식 수치 미공개",
    "apple_display_issue_source": "https://www.reuters.com/business/media-telecom/apple-says-it-will-replace-iphone-duo-units-showing-screen-problems-2026-10-26/",
    "apple_display_issue_status": "애플은 소수 내측화면 문제 인정·교환 안내. 불량률·원인·전량 리콜 미확인",
}


def _verify_sentiment_source_numbers(study: dict) -> None:
    """Sentiment, search traffic, sales and physical reliability stay separate."""
    if round(float(study["fold8_positive_pct"])-float(study["fold8_negative_pct"]),1) != float(study["fold8_net_sentiment_pp"]):
        raise ValueError("Quettai Fold8 sentiment numerator mismatch")
    if round(float(study["duo_positive_pct"])-float(study["duo_negative_pct"]),1) != float(study["duo_net_sentiment_pp"]):
        raise ValueError("Quettai Duo sentiment numerator mismatch")
    if round(float(study["fold8_net_sentiment_pp"])-float(study["duo_net_sentiment_pp"]),1) != float(study["net_sentiment_gap_pp"]):
        raise ValueError("Quettai net sentiment gap mismatch")
    if study.get("search_is_sales") is not False:
        raise ValueError("Search interest is not sales")
    if int(study["fold8_naver_search_count"]) <= 0 or int(study["duo_naver_search_count"]) <= 0:
        raise ValueError("Unverified search denominator")


def _sentiment_baseline_alert(study: dict) -> str:
    _verify_sentiment_source_numbers(study)
    return "\n".join([
        "📱 <b>[폴더블 경쟁·소비자 반응 | 11월 18일 신규 조사 기준선]</b>",
        "━━━━━━━━━━━━━━━━",
        "• 한경·뉴엔AI 퀘타아이 <b>2026년 1~10월 온라인 게시물 감성분석</b> (제조사 공식 판매조사 아님).",
        "• Galaxy Z Fold8: 긍정 <b>50.2%</b> / 부정 <b>8.3%</b> / 순호감 <b>+41.9%p</b>.",
        "• iPhone Duo: 긍정 <b>21.2%</b> / 부정 <b>24.6%</b> / 순호감 <b>-3.4%p</b>.",
        "• 순호감 격차 <b>45.3%p</b>로 갤럭시 우세. 이 비율은 AI가 분류한 언급이며 실제 구매율이 아닙니다.",
        "• 네이버 검색(10/13~11/12): Duo <b>588,800회</b>, Fold8 <b>103,000회</b> → 화제성은 Duo 우세, 구매량 아님.",
        "• 독립 분석(해시스크래퍼, 10/22~28): Duo 부정 <b>51.5%</b>(분류 1,047건), "
        "Fold8 부정 <b>17.5%</b>(분류 838건). 기간·표본·뉴스 포함 기준이 달라 위 조사와 합산 불가.",
        "• 국내 Fold8 10/23~29 주간 판매 <b>직전주 대비 20% 초과</b>는 통신업계 보도이며, 실제 대수·삼성 공식치는 미공개.",
        "• 애플은 Duo 일부 기기의 안쪽 화면 문제를 인정하고 교환을 안내했습니다. "
        "불량률·힌지 원인·차기 모델 개선효과는 아직 확인되지 않았습니다.",
        "• 힌지 기술이 Galaxy Fold4 이하라는 세대별 비교는 공인 동일조건 시험 없이 확정할 수 없습니다.",
        "",
        "<b>[향후 확인할 변화]</b>",
        "• 같은 표본·기간 정의로 반복 측정한 브랜드 호감도 변화",
        "• 실제 판매·교환·반품 건수, 보증 비용과 앱 호환성 개선의 객관적 수치",
        "",
        f'<a href="{study["source_url"]}">원문 · 한경·뉴엔AI 퀘타아이</a>',
        f'<a href="{study["independent_directional_source"]}">별도 표본 · 해시스크래퍼</a>',
        f'<a href="{study["fold8_sales_source"]}">폴드8 주간 판매 보도</a>',
        f'<a href="{study["apple_display_issue_source"]}">Apple 화면 교환 입장 · Reuters</a>',
    ])+"\n"


APPLE_PAGES = {"한국": APPLE_KR, "일본": APPLE_JP}
SEARCHES = [
    ("ko", '"갤럭시 Z 폴드8" 고객 수요 16% 검색량 300%'),
    ("ko", '"아이폰 듀오" "현장 구매" "애플스토어" "일본"'),
    ("ko", '"갤럭시Z폴드8" "아이폰 듀오" 호감도 퀘타아이 제품 평가'),
    ("ko", '"아이폰 듀오" 갤럭시 폴드8 화면 교환 앱 최적화 비교'),
    ("en", '"Galaxy Z Fold8" "customer demand" "searches"'),
    ("en", '"iPhone Duo" walk-in Japan South Korea Apple Store policy'),
]
UA = "Mozilla/5.0 (compatible; khs-apple-foldable-market-access-watch/1.0)"


def _request(url: str, timeout: int = 24) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _plain(raw: str) -> str:
    raw = re.sub(r"(?is)<(?:script|style)[^>]*>.*?</(?:script|style)>", " ", raw)
    raw = re.sub(r"<[^>]*>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(raw)).strip()


def _official_access(raw: str, market: str) -> str:
    text = re.sub(r"[\u200b-\u200f\u2060\ufeff\u00ad]", "", _plain(raw)).lower()
    # Both model names and an explicit prohibition must appear in one short
    # official statement. Missing notices mean unknown, not "allowed".
    if market == "한국":
        blocked = bool(re.search(
            r"iphone\s*duo.{0,110}iphone\s*18\s*pro\s*max.{0,150}"
            r"(?:현장\s*구매를\s*할\s*수\s*없습니다|현장\s*구매\s*불가)",
            text, re.I
        ))
    elif market == "일본":
        blocked = (
            "iphone duo" in text
            and "iphone 18 pro max" in text
            and (
                "予約せずに購入することはできません" in text
                or "予約なしでは購入できません" in text
            )
        )
    else:
        return "unknown"
    if blocked:
        return "reservation_only"
    # Loss of the earlier banner does NOT mean permission to walk in.
    if market == "한국":
        allowed = bool(
            "iphone duo" in text and "iphone 18 pro max" in text
            and re.search(r"(?:예약\s*없이\s*)?현장\s*구매(?:가|를)?\s*가능", text)
        )
    else:
        allowed = (
            "iphone duo" in text and "iphone 18 pro max" in text
            and any(x in text for x in (
                "予約なしで購入できます", "予約なしで購入可能です", "予約なしでご購入いただけます"
            ))
        )
    return "walk_in_available" if allowed else "unknown"


def _metric_quote(text: str, category: str) -> float | None:
    low = _plain(text).lower()
    if category == "fold8":
        # A specific demand claim, not sales, views or marketing search interest.
        if not any(x in low for x in ("fold8", "fold 8", "폴드8")):
            return None
        candidates = [
            r"(?:customer\s+demand|고객\s*수요|consumer\s+demand)"
            r"[^.!?]{0,170}?(?:increas\w*|rose|증가|늘었)[^.!?]{0,30}?(\d{1,3}(?:\.\d+)?)\s*%",
            r"(?:demand|수요)[^.!?]{0,95}?(\d{1,3}(?:\.\d+)?)\s*%\s*(?:increas\w*|rise|증가)"
        ]
    elif category == "search":
        if not any(x in low for x in ("foldable", "폴더블", "fold 8", "fold8", "폴드8")):
            return None
        candidates = [
            r"(\d{1,3}(?:\.\d+)?)\s*%\s*(?:increas\w*|surge|jump|증가)[^.!?]{0,95}?"
            r"(?:google\s+search|구글\s*검색)",
            r"(?:google\s+search|구글\s*검색)[^.!?]{0,130}?"
            r"(?:increas\w*|rose|증가|상승)[^.!?]{0,25}?(\d{1,3}(?:\.\d+)?)\s*%",
            r"(?:google\s+search|구글\s*검색)[^.!?]{0,130}?(\d{1,3}(?:\.\d+)?)\s*%"
        ]
    else:
        return None
    for pat in candidates:
        m = re.search(pat, low, re.I)
        if m:
            value = float(m.group(1))
            return value if 0 <= value <= 1000 else None
    return None


def _publication_date(text: str | None) -> dt.datetime | None:
    if not text:
        return None
    try:
        parsed = parsedate_to_datetime(text)
        return parsed.astimezone(KST) if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc).astimezone(KST)
    except Exception:
        return None


def _rss_url(language: str, q: str) -> str:
    p = {"q": q, "hl": "ko" if language == "ko" else "en-US",
         "gl": "KR" if language == "ko" else "US",
         "ceid": "KR:ko" if language == "ko" else "US:en"}
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(p)


def _fetch_articles(now: dt.datetime) -> tuple[list[dict], list[str]]:
    cutoff = now - dt.timedelta(days=10)
    output: dict[str, dict] = {}
    errors: list[str] = []
    for language, query in SEARCHES:
        try:
            root = ET.fromstring(_request(_rss_url(language, query)))
            for entry in root.findall(".//item"):
                title = _plain(entry.findtext("title") or "")
                description = _plain(entry.findtext("description") or "")
                src_node = entry.find("source")
                source = _plain(src_node.text or "") if src_node is not None else ""
                date = _publication_date(entry.findtext("pubDate"))
                link = (entry.findtext("link") or "").strip()
                if not date or date > now or date < cutoff or not link or not title:
                    continue
                identity = hashlib.sha256((title.lower()+"|"+source.lower()).encode()).hexdigest()[:24]
                output[identity] = {
                    "id": identity, "source": source, "title": title,
                    "description": description, "link": link,
                    "published_at_kst": date.isoformat(timespec="seconds"),
                }
        except Exception as exc:
            errors.append("news:"+type(exc).__name__)
    return list(output.values()), errors


def _fold8_signal(row: dict, baseline: dict) -> dict | None:
    # A media interview with named Samsung spokesperson or direct Samsung
    # newsroom update is required. Other republications never create a signal.
    source = row.get("source", "").lower()
    blob = row.get("title", "")+" "+row.get("description", "")
    low = blob.lower()
    if not any(x in source for x in ("forbes", "samsung", "reuters", "연합뉴스", "yonhap")):
        return None
    if not any(x in low for x in ("samsung", "삼성")) or not any(x in low for x in ("fold8", "fold 8", "폴드8")):
        return None
    if not any(x in low for x in ("richard chang", "리처드 창", "삼성전자 관계자", "samsung executive", "삼성전자 임원", "samsung vice president")):
        return None
    demand = _metric_quote(blob, "fold8")
    searches = _metric_quote(blob, "search")
    old_demand = float(baseline.get("fold8_demand_change_pct", 16))
    old_searches = float(baseline.get("samsung_foldable_google_search_change_pct", 300))
    # Same 16% / 300% republished days later is not a new fact.
    if demand is not None and abs(demand-old_demand) >= 5:
        return {"kind": "demand", "value": demand, "old": old_demand,
                "source": row.get("source"), "link": row.get("link"), "title": row.get("title")}
    if searches is not None and abs(searches-old_searches) >= 100:
        return {"kind": "search", "value": searches, "old": old_searches,
                "source": row.get("source"), "link": row.get("link"), "title": row.get("title")}
    return None


def _load_state() -> dict:
    if not STATE.exists():
        return {"schema_version": 1, "initial_alert_sent": False,
                "metrics": dict(BASELINE), "access": {"한국": "reservation_only", "일본": "reservation_only"},
                "seen_ids": [], "last_alert": None}
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise TypeError("Invalid state")
        return data
    except Exception as exc:
        raise RuntimeError("Foldable market state corrupt; stop before Telegram delivery") from exc


def _merge_market_state(remote: dict, local: dict) -> dict:
    rt, lt = str(remote.get("updated_at_kst") or ""), str(local.get("updated_at_kst") or "")
    newer = local if lt >= rt else remote
    old = remote if newer is local else local
    out = dict(old)
    out.update(newer)
    out["initial_alert_sent"] = bool(remote.get("initial_alert_sent") or local.get("initial_alert_sent"))
    out["sentiment_baseline_sent"] = bool(
        remote.get("sentiment_baseline_sent") or local.get("sentiment_baseline_sent")
    )
    out["sentiment_fact_keys"] = sorted(
        set(remote.get("sentiment_fact_keys") or []) | set(local.get("sentiment_fact_keys") or [])
    )[-100:]
    out["seen_ids"] = sorted(set(remote.get("seen_ids") or []) | set(local.get("seen_ids") or []))[-500:]
    out["access"] = dict(old.get("access") or {})
    out["access"].update(newer.get("access") or {})
    out["metrics"] = dict(old.get("metrics") or {})
    out["metrics"].update(newer.get("metrics") or {})
    if any(isinstance(x.get("last_alert"), dict) for x in (remote, local)):
        out["last_alert"] = max(
            [x["last_alert"] for x in (remote, local) if isinstance(x.get("last_alert"), dict)],
            key=lambda x: str(x.get("at_kst") or ""),
        )
    return out


def _initial_alert(official: dict[str, str]) -> str:
    return "\n".join([
        "📱 <b>[폴더블 시장·애플 매장판매 | 공식 기준선]</b>",
        "━━━━━━━━━━━━━━━━",
        "• 삼성전자 영국·아일랜드 임원: Galaxy Z Fold8 제품군 <b>고객 수요 출시 이후 +16%</b>.",
        "  └ 지역별 실제 판매 대수 또는 전년 대비 성장률로 해석하지 않습니다.",
        "• 삼성 폴더블 구글 검색 관심도 <b>최근 한 달 +300%</b>.",
        "  └ 검색량은 매출·판매량·구매전환률과 다릅니다.",
        "• 별도 국내 판매 기준선: 9월 공개 직후 Fold8 전주 대비 <b>+10%</b> 보도.",
        "• 한국 Apple 공식 안내: <b>iPhone Duo·iPhone 18 Pro Max 예약 없는 현장 구매 제한</b>.",
        "• 일본: Apple 지역 공지·MacRumors가 동일 제한을 보도. 이번 자동실행에서 "
        + ("<b>공식 원문 직접 확인</b>." if official.get("일본") == "reservation_only" else
           "<b>일본 공식 페이지 직접 확인 불가 — 보도·검색색인 확인 단계</b>."),
        "  └ 배송 주문/예약 픽업·신제품 출시일과 구분하며 공급 부족 원인은 미확정입니다.",
        "• Apple 공식 iPhone Duo 출시일: <b>10월 23일</b>로 유지.",
        "",
        "<b>[기관 전망 — 독립된 두 추정]</b>",
        "• IDC 2026 글로벌 폴더블 <b>2,290만 대, +12.6%</b> 전망.",
        "• TrendForce 2026 글로벌 폴더블 <b>2,020만 대, +0.5%</b> 전망.",
        "• 기관별 조사·가정을 섞거나 실제 확정 출하량으로 취급하지 않습니다.",
        "",
        "<b>[앞으로의 새 알림]</b>",
        "• 제조사 경영진의 Fold8 고객 수요 증가율이 5%포인트 이상 재평가",
        "• 삼성 폴더블 검색 관심도 100%포인트 이상 변화(판매 변화로 승격 금지)",
        "• Apple 한국·일본 공식 매장 예약 정책 변경 또는 추가 국가 확대",
        "• 국내 실제 Fold8 판매·iPhone Duo 주문대수·Apple 패널 추가 발주는 별도 모듈에서 검증",
        "",
        f'<a href="{FORBES}">Forbes 삼성 경영진 인터뷰</a>',
        f'<a href="{APPLE_KR}">Apple 한국 공식 정책</a>',
        f'<a href="{APPLE_JP}">Apple 일본 공식 정책</a>',
        f'<a href="{IDC}">IDC 폴더블 전망</a>',
        f'<a href="{TRENDFORCE}">TrendForce 폴더블 전망</a>',
    ])+"\n"


def _append_alert(text: str) -> None:
    existing = TELEGRAM.read_text(encoding="utf-8").strip() if TELEGRAM.exists() else ""
    TELEGRAM.write_text((existing+"\n\n" if existing else "")+text, encoding="utf-8")


def main() -> None:
    now = dt.datetime.now(KST)
    state = _load_state()
    metrics = dict(BASELINE)
    metrics.update(state.get("metrics") or {})
    access = dict(state.get("access") or {})
    errors: list[str] = []
    official: dict[str, str] = {}
    for market, page in APPLE_PAGES.items():
        try:
            raw = _request(page)
            official[market] = _official_access(raw, market)
        except Exception as exc:
            errors.append("apple_"+market+":"+type(exc).__name__)
            official[market] = "unknown"

    rows, rss_errors = _fetch_articles(now)
    errors += rss_errors
    seen = set(state.get("seen_ids") or [])
    alerts: list[str] = []
    pending_baseline = not state.get("initial_alert_sent", False)
    # A transient Japan notice parsing failure cannot hide the separate
    # Samsung demand measurement or Korea's verified Apple retail policy.
    baseline_ready = official.get("한국") == "reservation_only"
    if pending_baseline:
        if baseline_ready:
            alerts.append(_initial_alert(official))
            state["initial_alert_sent"] = True
            access["한국"] = "reservation_only"
            access["일본"] = ("reservation_only" if official.get("일본") == "reservation_only"
                          else "reported_not_live_verified")
        else:
            errors.append("기준선 보류: 한국 Apple 공식 현장판매 공지 직접 조회 불가")
    else:
        for market, value in official.items():
            # Never infer restriction has ended merely because notice is absent.
            if value in ("reservation_only", "walk_in_available") and access.get(market) != value:
                previous = access.get(market)
                access[market] = value
                if value == "walk_in_available":
                    description = "예약 없는 현장 구매 가능하다는 명시적 공식 안내 확인"
                    heading = "애플 매장 현장 구매 허용 확인"
                else:
                    description = "iPhone Duo·iPhone 18 Pro Max 예약 없는 현장 구매 제한 직접 확인"
                    heading = "애플 매장 구매 제한 공식 확인"
                alerts.append(
                    f"📱 <b>[{heading}]</b>\n"
                    f"• {market}: {description}\n"
                    f"• 이전 상태: {html.escape(str(previous or '미확인'))}\n"
                    "• 배송 납기·예약 픽업·완제품 판매량과는 별개입니다.\n"
                    f'<a href="{APPLE_PAGES[market]}">Apple 공식 국가별 공지</a>'
                )

    sent_keys = set(state.get("sentiment_fact_keys") or [])
    sentiment_release = dt.datetime(2026,11,18,6,0,tzinfo=KST)
    if (now >= sentiment_release and state.get("initial_alert_sent")
            and SENTIMENT_STUDY_KEY not in sent_keys):
        _verify_sentiment_source_numbers(SENTIMENT_STUDY)
        alerts.append(_sentiment_baseline_alert(SENTIMENT_STUDY))
        sent_keys.add(SENTIMENT_STUDY_KEY)
        state["sentiment_baseline_sent"] = True
        state["sentiment_study"] = dict(SENTIMENT_STUDY)
    state["sentiment_fact_keys"] = sorted(sent_keys)[-100:]

    for row in rows:
        seen.add(row["id"])
        if pending_baseline:
            continue
        if row["id"] in (state.get("seen_ids") or []):
            continue
        change = _fold8_signal(row, metrics)
        if not change:
            continue
        kind, val = change["kind"], change["value"]
        if kind == "demand":
            metrics["fold8_demand_change_pct"] = val
            text = f"• Galaxy Z Fold8 고객 수요 변화율 {change['old']:g}%→{val:g}% (출시 이후, 실제 판매대수 미공개)"
        else:
            metrics["samsung_foldable_google_search_change_pct"] = val
            text = f"• 삼성 폴더블 구글 검색 관심도 {change['old']:g}%→{val:g}% (최근 한 달, 판매량과 무관)"
        alerts.append(
            "📱 <b>[삼성 폴더블 시장 선행지표 재평가]</b>\n"
            +text+"\n"
            f"• 원문: {html.escape(change['title'] or '')}\n"
            f'<a href="{html.escape(change["link"] or "",quote=True)}">출처 · {html.escape(change["source"] or "")}</a>'
        )
        if len(alerts) >= 3:
            break

    state.update({
        "schema_version": 1,
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "metrics": metrics, "access": access,
        "seen_ids": sorted(seen)[-500:],
        "last_scan_items": len(rows), "last_new_signal_count": len(alerts),
        "last_official": {k: ("확인" if v=="reservation_only" else "확인 불가") for k,v in official.items()},
        "errors": errors[-20:],
        "last_alert": (
            {"at_kst": now.isoformat(timespec="seconds"), "count": len(alerts)}
            if alerts else state.get("last_alert")
        ),
    })
    PENDING.write_text(json.dumps(state, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    if alerts:
        block = "\n\n".join(alerts)
        ALERT.write_text(block+"\n", encoding="utf-8")
        _append_alert(block+"\n")
    else:
        ALERT.unlink(missing_ok=True)
    STATUS.write_text(
        "# 폴더블 시장·매장 판매정책 감시\n"
        f"- 조회(한국): {now.isoformat(timespec='seconds')}\n"
        f"- Apple 공식 정책 확인: {official}\n"
        f"- 기준선 송출상태: {state.get('initial_alert_sent')}\n"
        f"- 뉴스 검색: {len(rows)}건 / 신규 신호: {len(alerts)}건\n"
        f"- 조회 오류: {errors}\n"
        f"- 감성조사 기준선 사실키: {len(state.get('sentiment_fact_keys') or [])}\n", encoding="utf-8",
    )


if __name__ == "__main__":
    main()
