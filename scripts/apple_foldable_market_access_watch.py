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
APPLE_PAGES = {"한국": APPLE_KR, "일본": APPLE_JP}
SEARCHES = [
    ("ko", '"갤럭시 Z 폴드8" 고객 수요 16% 검색량 300%'),
    ("ko", '"아이폰 듀오" "현장 구매" "애플스토어" "일본"'),
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
    return "unknown"


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
            if value == "reservation_only" and access.get(market) != "reservation_only":
                access[market] = value
                alerts.append(
                    "📱 <b>[Apple 매장 구매 제한 공식 재확인]</b>"\n"
                    f"• {market} Apple 공식 안내: iPhone Duo·iPhone 18 Pro Max 예약 없는 현장 구매 제한\n"
                    "• 온라인 주문·매장 픽업 예약은 별도이며 10월 23일 공식 출시는 유지\n"
                    f'<a href="{APPLE_PAGES[market]}">Apple 공식 국가별 공지</a>'
                )

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
        f"- 조회 오류: {errors}\n", encoding="utf-8",
    )


if __name__ == "__main__":
    main()
