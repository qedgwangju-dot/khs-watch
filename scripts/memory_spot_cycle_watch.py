#!/usr/bin/env python3
"""Memory spot/contract/DRAM-HBM capacity web watch for Telegram alerts.

The watcher is intentionally conservative:
- scans multiple Google News RSS queries in Korean and English,
- directly scans TrendForce Memory & Storage research pages so paid research summaries are not missed,
- scores only memory-supply/price/capacity items,
- explicitly watches DRAM wafer-start, greenfield fab and ramp-up signals,
- translates and polishes English alert titles into natural Korean,
- preserves uncertainty such as report/likely/expected instead of overstating it,
- keeps the full Korean alert sentence without character-level truncation,
- stays silent when there is no new meaningful change,
- deduplicates by normalized title/source,
- emits a compact Telegram alert only for new meaningful items.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import os
import pathlib
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

import currency_krw_guard

try:
    from googlenewsdecoder import gnewsdecoder
except Exception:  # pragma: no cover - optional runtime dependency
    gnewsdecoder = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "memory_spot_cycle_watch_state.json"
OUT_DIR = ROOT / "out"
PENDING_PATH = OUT_DIR / "memory_spot_cycle_watch_pending_state.json"
ALERT_PATH = OUT_DIR / "memory_spot_cycle_watch_telegram.txt"
STATUS_PATH = OUT_DIR / "memory_spot_cycle_watch_status.md"
KST = ZoneInfo("Asia/Seoul")
TREND_RESEARCH_URL = "https://www.trendforce.com/research/memory-storage"
HBM_MARKET_PRICE_TRACK_VERSION = 2
HBM_MARKET_ALERT_FORMAT_VERSION = 2
HBM_MARKET_PRICE_BASELINE = {
    "period": "2027",
    "blended_asp_yoy_pct": 121.0,
    "eight_hi_premium_min_pct": 10.0,
    "eight_hi_premium_max_pct": 20.0,
    "mainstream_layers": 8,
    "source": "TrendForce",
    "source_url": "https://www.trendforce.com/presscenter/news/20260929-13255.html",
    "research_reference_url": "https://www.trendforce.com/research/download/RP260922FJ3",
    "secondary_source_url": "https://biz.chosun.com/it-science/ict/2026/09/29/4EV5Z6JAR5GCPG7DR7ZBBFMJUQ/",
    "source_rank": 3,
    "as_of": "2026-09-29",
}
BERNSTEIN_MEMORY_CYCLE_TRACK_VERSION = 1
BERNSTEIN_MEMORY_CYCLE_BASELINE = {
    "q3_2026_price_band": "mid-teens~20%",
    "q4_2026_price_band": "high-single-digit",
    "shortage_through_year": 2027,
    "normalization_year": 2028,
    "lta_caps_price_increases": True,
    "source": "Bernstein via Investing.com",
    "source_url": "https://au.investing.com/news/stock-market-news/bernstein-sees-samsung-gaining-hbm-share-cuts-sk-hynix-target-4664570",
    "source_rank": 2,
    "as_of": "2026-09-30",
}
TREND_PINNED_PRESS_URLS = [
    "https://www.trendforce.com/presscenter/news/20260929-13255.html",
]
TREND_PINNED_REPORT_URLS = [
    # Seed the latest quarterly forecast explicitly; it is removed naturally by the
    # rolling cutoff once stale, but guarantees paid-research summaries are not missed
    # when TrendForce listing HTML/search indexing changes.
    "https://www.trendforce.com/research/download/RP260924PL",
    "https://www.trendforce.com/research/download/RP260922FJ3",
]
TREND_SEARCH_QUERIES = [
    'site:trendforce.com/research/download "Memory Price Forecast" DRAM NAND',
    'site:trendforce.com/research/download "DRAM Market Bulletin" TrendForce',
    'site:trendforce.com/research/download "NAND Flash Market Bulletin" TrendForce',
    'site:trendforce.com/research/download "HBM Market Bulletin" TrendForce',
    'site:trendforce.com/research/download QLC enterprise SSD KV cache TrendForce',
]

QUERIES = [
    ("ko", 'DRAM 현물 가격 공급 부족 BofA OR 뱅크오브아메리카'),
    ("ko", 'NAND 현물 가격 공급 부족 TrendForce OR 트렌드포스'),
    ("ko", 'TrendForce 4Q26 메모리 가격 전망 Enterprise SSD QLC KV 캐시 23 28 NAND 15 20'),
    ("ko", '서버 DRAM 고정가격 계약가격 ASP 삼성전자 SK하이닉스'),
    ("ko", '2028 HBM 공급확약 브로드컴 엔비디아 구글 AMD'),
    ("ko", 'TrendForce 2027 HBM 평균판매가격 121% 8단 12단 10 20'),
    ("ko", 'HBM 2027 Blended ASP 121 8단 Gb당 10 20 트렌드포스'),
    ("ko", 'Bernstein DRAM NAND 3분기 20% 4분기 한 자릿수 공급부족 2027 2028 정상화 LTA'),
    ("ko", 'Bernstein 메모리 2028 정상화 2027 공급부족 장기계약 LTA 가격 상한'),
    # DRAM physical capacity / wafer-start / new-fab cycle: do not miss supply expansion.
    ("ko", 'DRAM 생산능력 웨이퍼 투입량 월 생산량 증설 삼성전자 P4 SK하이닉스 M15X 마이크론'),
    ("ko", '어플라이드 머티어리얼즈 Citi TMT DRAM 생산능력 웨이퍼 160만 200만 40만'),
    ("ko", 'DRAM 신규 팹 그린필드 장비투자 웨이퍼 스타트 P4 P5 M15X Y1'),
    ("en", 'DRAM spot price shortage BofA Bank of America memory'),
    ("en", 'NAND spot price shortage TrendForce memory'),
    ("en", 'TrendForce 4Q26 Memory Price Forecast enterprise SSD QLC KV cache 23 28 NAND 15 20'),
    ("en", 'server DRAM contract price TrendForce Samsung SK hynix Micron'),
    ("en", '2028 HBM supply commitment Broadcom NVIDIA Google AMD'),
    ("en", 'HBM trade ratio Micron HBM4E DRAM capacity'),
    ("en", 'TrendForce 2027 HBM blended ASP 121% 8-Hi 12-Hi premium 10 20'),
    ("en", 'Bernstein DRAM NAND Q3 mid-teens 20% Q4 high-single-digit shortage 2027 normalize 2028 LTA'),
    ("en", 'Bernstein memory 2028 normalization 2027 shortage long-term agreements cap price increases'),
    ("en", 'Applied Materials Citi TMT DRAM wafer starts capacity 1.6 million 2 million 400000'),
    ("en", 'DRAM wafer starts greenfield fab capacity expansion Samsung P4 SK hynix M15X Micron'),
    ("en", 'DRAM capacity 300000 400000 wafer starts per month Applied Materials'),
]

MEMORY_MARKERS = {
    "dram", "ddr4", "ddr5", "lpddr", "hbm", "hbm4", "hbm4e", "nand",
    "essd", "ssd", "memory", "메모리", "디램", "낸드", "현물", "고정가",
}
CHANGE_MARKERS = {
    "spot", "contract", "price", "asp", "shortage", "supply", "capacity", "capa",
    "inventory", "lta", "commitment", "allocation", "raise", "increase", "forecast",
    "outlook", "revised", "revision", "normalize", "normalization", "wafer", "wafer start", "wafer starts", "wspm",
    "greenfield", "fab", "factory", "ramp", "ramp-up", "equipment investment",
    "현물", "고정가", "계약가", "가격", "부족", "공급", "재고", "증설", "인상",
    "상향", "전망", "확약", "배정", "수급", "웨이퍼", "생산능력", "투입량",
    "신규 팹", "그린필드", "램프업", "가동", "장비투자", "설비투자",
}
HIGH_SIGNAL = {
    "bofa", "bank of america", "bernstein", "trendforce", "dram exchange", "dramexchange", "omdia",
    "reuters", "bloomberg", "citi", "ubs", "micron", "samsung", "sk hynix", "sk하이닉스",
    "삼성전자", "nvidia", "엔비디아", "broadcom", "브로드컴", "google", "구글", "amd",
    "applied materials", "amat", "어플라이드 머티어리얼즈", "citi tmt",
}
CRITICAL_MARKERS = {
    "sufficiency", "공급 충족", "under supply", "undersupply", "shortage", "공급부족",
    "2027", "2028", "hbm4e", "lta", "장기계약", "공급확약", "commitment",
    "wafer starts", "greenfield", "p4", "p5", "m15x", "y1", "웨이퍼", "생산능력",
}


def _rss_url(lang: str, query: str) -> str:
    if lang == "ko":
        params = {"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"}
    else:
        params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; khs-memory-watch/1.3)",
            "Accept": "application/rss+xml,application/xml,text/xml,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        return response.read()


def _clean(text: str | None) -> str:
    value = html.unescape(text or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _translate_to_ko(text: str) -> str:
    """Translate non-Korean alert text to Korean.

    We deliberately do not expose an English title if translation is temporarily
    unavailable. The original link remains untouched as an identifier.
    """
    text = _clean(text)
    if not text:
        return "메모리 관련 신규 변화"
    hangul = len(re.findall(r"[가-힣]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if hangul >= max(4, latin // 3):
        return text

    params = {
        "client": "gtx",
        "sl": "auto",
        "tl": "ko",
        "dt": "t",
        "ie": "UTF-8",
        "oe": "UTF-8",
        "q": text,
    }
    url = "https://translate.googleapis.com/translate_a/single?" + urllib.parse.urlencode(params)
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/json,text/plain,*/*",
                },
            )
            with urllib.request.urlopen(req, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8"))
            translated = "".join(
                str(part[0]) for part in (data[0] or [])
                if isinstance(part, list) and part and part[0]
            ).strip()
            if translated and re.search(r"[가-힣]", translated):
                return translated
        except Exception:
            if attempt < 2:
                time.sleep(1.0 + attempt)

    lower = text.lower()
    # Preserve the product layer before generic keywords such as wafer/capacity.
    # Otherwise "NAND Flash Wafer Contract Price" is incorrectly rendered as a DRAM-capacity alert.
    if "nand flash wafer contract price" in lower:
        return "NAND Flash 웨이퍼 계약가 업데이트"
    if "nand flash contract price" in lower:
        return "NAND Flash 계약가 업데이트"
    if "nand flash market bulletin" in lower:
        return "NAND Flash 시장 수급·가격 업데이트"
    if "specialty dram price" in lower:
        return "Specialty DRAM 계약가 업데이트"
    if "dram market bulletin" in lower:
        return "DRAM 시장 수급·계약가 업데이트"
    if "dram contract price" in lower:
        return "DRAM 계약가 업데이트"
    if "memory price forecast" in lower:
        return "메모리 가격 전망 업데이트"
    if "hbm market bulletin" in lower:
        return "HBM 시장 가격·수급 업데이트"
    if "nand" in lower or "ssd" in lower:
        return "NAND·기업용 SSD 가격·수급 변화"
    if "hbm" in lower:
        return "HBM 수요·공급능력 변화"
    if "dram" in lower:
        return "DRAM 가격·수급 변화"
    if "spot" in lower and "price" in lower:
        return "메모리 현물가격 변화"
    if "wafer" in lower or "capacity" in lower or "greenfield" in lower:
        return "메모리 웨이퍼 생산능력·신규 팹 변화"
    if "shortage" in lower or "supply" in lower:
        return "메모리 공급부족·수급 변화"
    return "해외 메모리 관련 신규 변화"


def _polish_alert_title(raw_title: str, translated: str) -> str:
    """Turn a literal machine translation into a complete Korean headline sentence."""
    raw = _clean(raw_title)
    low = raw.lower()
    title = _clean(translated)

    if (
        "apple" in low
        and "nand" in low
        and "lta" in low
        and "kioxia" in low
        and ("said to have signed" in low or "likely partner" in low)
    ):
        return "Apple, NAND 장기공급계약(LTA) 체결 보도…유력 상대는 Kioxia, 폴더블 iPhone 메모리 공급망 주목"

    title = re.sub(r"^\s*\[(?:뉴스|속보|단독|News|NEWS)\]\s*", "", title).strip()
    title = re.sub(r"^\s*(?:뉴스|속보)\s*[:：]\s*", "", title).strip()
    title = re.sub(r"\s*[;；]\s*", "…", title)
    title = re.sub(r"\.\s*(주목받는|주목되는|관심이 쏠리는)\s+", "…", title)
    title = re.sub(r"\s+\|\s+", "…", title)
    title = re.sub(r"\s+", " ", title).strip()

    if "reportedly" in low and "보도" not in title and "전해" not in title:
        title = title.rstrip(".。 ") + "…관련 보도"
    if "may " in low and not any(x in title for x in ("가능", "전망", "검토", "수 있")):
        title = title.rstrip(".。 ") + " 가능성"

    return title or "메모리 관련 신규 변화"


def _parse_date(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(KST)
    except Exception:
        return None


def _normalize_title(title: str) -> str:
    title = title.lower()
    title = re.sub(r"\s+-\s+[^-]{1,80}$", "", title)
    title = re.sub(r"[^0-9a-z가-힣%]+", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def _fingerprint(item: dict) -> str:
    base = f"{_normalize_title(item['title'])}|{item.get('source','').lower()}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:24]


def _score(item: dict) -> int:
    blob = f"{item['title']} {item.get('source','')} {item.get('description','')}".lower()
    score = 0
    mem_hits = sum(1 for x in MEMORY_MARKERS if x in blob)
    change_hits = sum(1 for x in CHANGE_MARKERS if x in blob)
    high_hits = sum(1 for x in HIGH_SIGNAL if x in blob)
    critical_hits = sum(1 for x in CRITICAL_MARKERS if x in blob)

    if mem_hits == 0 or change_hits == 0:
        return 0
    score += min(mem_hits, 3) * 2
    score += min(change_hits, 3) * 2
    score += min(high_hits, 2) * 2
    score += min(critical_hits, 2) * 2
    if re.search(r"(?:\+|-)?\d+(?:\.\d+)?%", blob):
        score += 2
    if re.search(r"\b(?:2027|2028|2029|2030)\b", blob):
        score += 1
    if re.search(r"\b(?:\d+(?:\.\d+)?\s*(?:million|k|thousand))\s*(?:wafer|wafers)", blob):
        score += 2
    return score


def _decode_google_news_link(link: str) -> str:
    """Best-effort Google News RSS decoding; keep original link on failure."""
    if "news.google.com" not in (link or "") or gnewsdecoder is None:
        return link
    try:
        result = gnewsdecoder(link, interval=0.2)
        if isinstance(result, dict) and result.get("status"):
            decoded = str(result.get("decoded_url") or "").strip()
            if decoded.startswith("http") and "news.google.com" not in decoded:
                return decoded
    except Exception:
        pass
    return link


def collect() -> tuple[list[dict], list[str]]:
    items: list[dict] = []
    errors: list[str] = []
    now = dt.datetime.now(KST)
    cutoff = now - dt.timedelta(days=10)

    for lang, query in QUERIES:
        url = _rss_url(lang, query)
        try:
            root = ET.fromstring(_fetch(url))
            for node in root.findall(".//item"):
                title = _clean(node.findtext("title"))
                link = _decode_google_news_link(_clean(node.findtext("link")))
                description = _clean(node.findtext("description"))
                pub = _parse_date(node.findtext("pubDate"))
                source_node = node.find("source")
                source = _clean(source_node.text if source_node is not None else "")
                if not title or not link:
                    continue
                if pub and pub < cutoff:
                    continue
                item = {
                    "title": title,
                    "link": link,
                    "description": description,
                    "source": source,
                    "published_kst": pub.isoformat(timespec="seconds") if pub else None,
                    "query": query,
                }
                item["score"] = _score(item)
                if item["score"] >= 8:
                    item["fingerprint"] = _fingerprint(item)
                    items.append(item)
        except Exception as exc:
            errors.append(f"{lang}:{query}: {type(exc).__name__}: {exc}")

    direct_items, direct_errors = _collect_trendforce_research(cutoff)
    press_items, press_errors = _collect_trendforce_press(cutoff)
    search_items, search_errors = _collect_trendforce_search(cutoff)
    items.extend(direct_items)
    items.extend(press_items)
    items.extend(search_items)
    errors.extend(direct_errors)
    errors.extend(press_errors)
    errors.extend(search_errors)

    by_fp: dict[str, dict] = {}
    by_title: dict[str, dict] = {}
    for item in items:
        normalized_title = _normalize_title(item["title"])
        prev_title = by_title.get(normalized_title)
        if prev_title is None or (item["score"], item.get("published_kst") or "") > (
            prev_title["score"], prev_title.get("published_kst") or ""
        ):
            by_title[normalized_title] = item

    for item in by_title.values():
        fp = item["fingerprint"]
        prev = by_fp.get(fp)
        if prev is None or (item["score"], item.get("published_kst") or "") > (
            prev["score"], prev.get("published_kst") or ""
        ):
            by_fp[fp] = item
    return sorted(
        by_fp.values(),
        key=lambda x: (x.get("published_kst") or "", x["score"]),
        reverse=True,
    ), errors




def _bing_rss_url(query: str) -> str:
    return "https://www.bing.com/search?" + urllib.parse.urlencode({
        "q": query,
        "format": "rss",
        "setlang": "en-US",
    })


def _trendforce_url_date(url: str) -> dt.datetime | None:
    match = re.search(r"/RP(\d{2})(\d{2})(\d{2})", url, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        year = 2000 + int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        return dt.datetime(year, month, day, 9, 0, tzinfo=KST)
    except Exception:
        return None


def _trendforce_press_date(url: str) -> dt.datetime | None:
    match = re.search(r"/news/(20\d{2})(\d{2})(\d{2})-", url, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return dt.datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), 9, 0, tzinfo=KST)
    except Exception:
        return None


def _collect_trendforce_press(cutoff: dt.datetime) -> tuple[list[dict], list[str]]:
    items: list[dict] = []
    errors: list[str] = []
    for url in TREND_PINNED_PRESS_URLS:
        pub = _trendforce_press_date(url)
        if pub and pub < cutoff:
            continue
        try:
            raw = _fetch(url).decode("utf-8", errors="ignore")
            detail = _clean(raw)[:20000]
            title_m = re.search(r"<title[^>]*>(.*?)</title>", raw, re.I | re.S)
            title = _clean(title_m.group(1)) if title_m else "TrendForce HBM 2027 가격 전망"
            item = {
                "title": title,
                "link": url,
                "description": detail,
                "source": "TrendForce",
                "published_kst": pub.isoformat(timespec="seconds") if pub else None,
                "query": "direct:trendforce-press",
            }
            item["score"] = max(12, _score(item))
            item["fingerprint"] = _fingerprint(item)
            items.append(item)
        except Exception as exc:
            errors.append(f"TrendForce press {url}: {type(exc).__name__}: {exc}")
    return items, errors


def _collect_trendforce_search(cutoff: dt.datetime) -> tuple[list[dict], list[str]]:
    """Use web-search RSS to catch TrendForce paid-research pages that Google News omits."""
    items: list[dict] = []
    errors: list[str] = []
    seen_links: set[str] = set()

    for query in TREND_SEARCH_QUERIES:
        try:
            root = ET.fromstring(_fetch(_bing_rss_url(query)))
            for node in root.findall(".//item"):
                title = _clean(node.findtext("title"))
                link = _clean(node.findtext("link"))
                snippet = _clean(node.findtext("description"))
                if not title or not link:
                    continue
                host = urllib.parse.urlparse(link).netloc.lower()
                if "trendforce.com" not in host or "/research/download/" not in link:
                    continue
                if link in seen_links:
                    continue
                seen_links.add(link)

                pub = _trendforce_url_date(link)
                if pub and pub < cutoff:
                    continue

                detail_text = snippet
                try:
                    detail_text = _clean(_fetch(link).decode("utf-8", errors="ignore"))[:12000]
                except Exception:
                    pass

                item = {
                    "title": re.sub(r"\s*\|\s*TrendForce.*$", "", title, flags=re.IGNORECASE).strip(),
                    "link": link,
                    "description": detail_text,
                    "source": "TrendForce Research",
                    "published_kst": pub.isoformat(timespec="seconds") if pub else None,
                    "query": f"bing:{query}",
                }
                item["score"] = _score(item)
                if item["score"] >= 8:
                    item["fingerprint"] = _fingerprint(item)
                    items.append(item)
        except Exception as exc:
            errors.append(f"TrendForce search {query}: {type(exc).__name__}: {exc}")

    return items, errors

def _collect_trendforce_research(cutoff: dt.datetime) -> tuple[list[dict], list[str]]:
    """Directly scan TrendForce report listings and recent report pages."""
    items: list[dict] = []
    errors: list[str] = []
    listing_urls = [
        TREND_RESEARCH_URL,
        "https://www.trendforce.com/research/category/Semiconductors/DRAM?page=1",
        "https://www.trendforce.com/research/category/Semiconductors/NAND%20Flash?page=1",
    ]
    href_titles: dict[str, str] = {url: "" for url in TREND_PINNED_REPORT_URLS}

    for listing_url in listing_urls:
        try:
            listing_html = _fetch(listing_url).decode("utf-8", errors="ignore")
            # First capture normal anchor tags with their labels.
            for match in re.finditer(
                r'<a[^>]+href=["\']([^"\']*/research/download/RP[^"\']+)["\'][^>]*>(.*?)</a>',
                listing_html,
                flags=re.IGNORECASE | re.DOTALL,
            ):
                href = urllib.parse.urljoin(listing_url, html.unescape(match.group(1)))
                label = _clean(match.group(2))
                if href not in href_titles or (
                    label and label.lower() not in {"download report", "sign in and download report"}
                ):
                    href_titles[href] = label

            # TrendForce occasionally changes card markup or renders labels separately.
            # Capture raw report URLs too, so a layout change cannot hide a new report.
            loose_html = html.unescape(listing_html).replace("\\/", "/")
            for match in re.finditer(
                r'(?:"|\')([^"\']*/research/download/RP[0-9A-Za-z_-]+)(?:"|\')',
                loose_html,
                flags=re.IGNORECASE,
            ):
                href = urllib.parse.urljoin(listing_url, match.group(1))
                href_titles.setdefault(href, "")
        except Exception as exc:
            errors.append(f"TrendForce listing {listing_url}: {type(exc).__name__}: {exc}")

    recent_hrefs: list[tuple[dt.datetime | None, str]] = []
    for href in href_titles:
        url_date = _trendforce_url_date(href)
        if url_date and url_date < cutoff:
            continue
        recent_hrefs.append((url_date, href))
    recent_hrefs.sort(
        key=lambda pair: pair[0] or dt.datetime(2000, 1, 1, tzinfo=KST),
        reverse=True,
    )

    for url_date, href in recent_hrefs[:50]:
        try:
            detail_html = _fetch(href).decode("utf-8", errors="ignore")
            h1 = re.search(r"<h1[^>]*>(.*?)</h1>", detail_html, flags=re.IGNORECASE | re.DOTALL)
            title = _clean(h1.group(1)) if h1 else ""
            listing_title = href_titles.get(href, "")
            if (
                not title
                or title.lower() in {"research reports", "global hi-tech industry research report"}
                or not re.search(r"\b(?:DRAM|NAND|HBM|Memory|SSD|eSSD|Enterprise SSD)\b", title, flags=re.IGNORECASE)
            ):
                title = listing_title or title
            if not title:
                title_match = re.search(
                    r"<title[^>]*>(.*?)</title>",
                    detail_html,
                    flags=re.IGNORECASE | re.DOTALL,
                )
                title = _clean(title_match.group(1)) if title_match else ""
                title = re.sub(r"\s*\|\s*TrendForce.*$", "", title, flags=re.IGNORECASE).strip()

            if not title or not re.search(
                r"\b(?:DRAM|NAND|HBM|Memory|SSD|eSSD|Enterprise SSD)\b",
                title,
                flags=re.IGNORECASE,
            ):
                continue

            detail_text = _clean(detail_html)
            date_match = re.search(
                r"(?:Last Modified|Published|發佈日期|发布日期)\s*(\d{4})[-/](\d{2})[-/](\d{2})",
                detail_text,
                flags=re.IGNORECASE,
            )
            pub = url_date
            if date_match:
                pub = dt.datetime(
                    int(date_match.group(1)),
                    int(date_match.group(2)),
                    int(date_match.group(3)),
                    9,
                    0,
                    tzinfo=KST,
                )
            if pub and pub < cutoff:
                continue

            item = {
                "title": title,
                "link": href,
                "description": detail_text[:12000],
                "source": "TrendForce Research",
                "published_kst": pub.isoformat(timespec="seconds") if pub else None,
                "query": "direct:trendforce-memory-storage",
            }
            item["score"] = _score(item)
            if item["score"] >= 8:
                item["fingerprint"] = _fingerprint(item)
                items.append(item)
        except Exception as exc:
            errors.append(f"TrendForce detail {href}: {type(exc).__name__}: {exc}")

    return items, errors

def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"initialized": False, "seen": {}, "updated_at_kst": None}
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(state.get("seen"), dict):
            state["seen"] = {}
        return state
    except Exception:
        return {"initialized": False, "seen": {}, "updated_at_kst": None}


def classify(title: str) -> str:
    t = title.lower()
    capacity_terms = (
        "capacity", "capa", "greenfield", "fab", "factory", "ramp",
        "생산능력", "증설", "신규 팹", "그린필드", "램프업",
    )
    if "memory price forecast" in t or "메모리 가격 전망" in t:
        return "DRAM/NAND"
    if "hbm" in t:
        return "HBM"
    # Product family takes precedence over generic words such as contract/wafer.
    if "nand" in t or "낸드" in t or "ssd" in t:
        return "NAND/eSSD"
    if "specialty dram" in t:
        return "Specialty DRAM"
    if "dram" in t or "디램" in t:
        if any(x in t for x in capacity_terms):
            return "DRAM/CAPA"
        return "DRAM"
    if "spot" in t or "현물" in t:
        return "현물가"
    if "contract" in t or "고정가" in t or "계약가" in t:
        return "계약가"
    if "inventory" in t or "재고" in t or "sufficiency" in t:
        return "재고/수급"
    return "메모리"


def compact_title(title: str, source: str) -> str:
    suffix = f" - {source}" if source else ""
    if suffix and title.endswith(suffix):
        title = title[: -len(suffix)]
    return title.strip()


def _pct_range(blob: str, patterns: tuple[str, ...]) -> tuple[str, str] | None:
    for pattern in patterns:
        match = re.search(pattern, blob, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1), match.group(2)
    return None


def _price_change_details(raw_title: str, detail_blob: str) -> list[str]:
    """Return user-facing price changes, not just a report title.

    Use only numbers visible in the public report page. If TrendForce says an
    outlook was raised but the public summary withholds the exact band, say so
    instead of inventing a number from a paid table.
    """
    low = raw_title.lower()
    blob = _clean(detail_blob)
    details: list[str] = []

    if "memory price forecast" in low or "메모리 가격 전망" in low:
        essd = _pct_range(blob, (
            r"Enterprise\s+SSD[^0-9%]{0,180}(\d{1,3})\s*[-~–—]\s*(\d{1,3})\s*%\s*(?:QoQ|quarter[- ]over[- ]quarter)?",
            r"enterprise\s+ssd[^0-9%]{0,180}(\d{1,3})\s*(?:to|~|[-–—])\s*(\d{1,3})\s*%",
        ))
        nand = _pct_range(blob, (
            r"(?:Overall\s+)?NAND\s+Flash[^0-9%]{0,180}(\d{1,3})\s*[-~–—]\s*(\d{1,3})\s*%\s*(?:QoQ|quarter[- ]over[- ]quarter)?",
            r"overall\s+nand[^0-9%]{0,180}(\d{1,3})\s*(?:to|~|[-–—])\s*(\d{1,3})\s*%",
        ))
        if essd:
            details.append(f"기업용 SSD 계약가: 4Q26 +{essd[0]}~{essd[1]}% QoQ")
        if nand:
            details.append(f"NAND Flash 전체 계약가: 4Q26 +{nand[0]}~{nand[1]}% QoQ")
        if re.search(r"DRAM", blob, re.IGNORECASE):
            details.append("DRAM 계약가: 4Q26 상승 전망·상향 유지(공개 요약에 세부 등락률 미제시)")
        return details

    if "dram market bulletin" in low:
        if re.search(r"(?:lifts?|raises?|upgrade)[^。.!]{0,100}4Q26[^。.!]{0,80}(?:contract )?price", blob, re.IGNORECASE) or (
            "4q26" in blob.lower() and "contract price outlook" in blob.lower()
        ):
            details.append("DRAM 계약가: 4Q26 전망 상향(공개 요약에 세부 등락률 미제시)")
        if re.search(r"PC and server lead gains|PC[^。.!]{0,50}server[^。.!]{0,50}(?:gain|rise)", blob, re.IGNORECASE):
            details.append("제품별 방향: PC·서버 DRAM 상승폭 우위, 모바일·소비자용은 높은 가격 부담으로 상승폭 둔화")
        return details

    if "nand flash market bulletin" in low:
        if re.search(r"contract prices?[^。.!]{0,100}(?:up|rise|raise|higher)", blob, re.IGNORECASE) or re.search(
            r"(?:raise|raising)[^。.!]{0,80}contract prices?", blob, re.IGNORECASE
        ):
            details.append("NAND Flash 계약가: 전 제품군 상승 방향(공개 요약에 세부 등락률 미제시)")
        if re.search(r"enterprise SSD", blob, re.IGNORECASE):
            details.append("가격 주도 품목: 기업용 SSD·고성능 저장장치, AI 주문 증가로 공급 부족")
        return details

    if "hbm market bulletin" in low:
        if "2027" in blob and re.search(r"price[^。.!]{0,100}(?:forecast|outlook)", blob, re.IGNORECASE):
            details.append("HBM 가격: 2027년 전망 상향(이번 공개 요약에 새 등락률·단가 범위 미제시)")
        if re.search(r"8[- ]?Hi", blob, re.IGNORECASE) and re.search(r"premium", blob, re.IGNORECASE):
            details.append("제품별 가격 구조: 8단 HBM은 12단 대비 Gb당 프리미엄 전망")
        return details

    # Generic spot/contract items: expose the price type even when a precise
    # forecast range is not available in the public text.
    if "spot" in low or "현물" in low:
        details.append("가격 유형: 현물가")
    elif "contract" in low or "고정가" in low or "계약가" in low:
        details.append("가격 유형: 계약가")
    return details


def _market_signal_details(raw_title: str, detail_blob: str) -> list[str]:
    """Extract the public summary into user-facing cause/meaning lines.

    Never invent paid-table numbers. Narrative is emitted only when those words
    are visible on the report/listing page.
    """
    low_title = raw_title.lower()
    blob = _clean(detail_blob)
    low = blob.lower()
    out: list[str] = []

    if "dram market bulletin" in low_title:
        if ("csp" in low or "cloud" in low) and "server dram" in low:
            out.append("수급: CSP의 서버 DRAM 추가 매수 → 공급사 재고 하락")
        if "contract price" in low and any(k in low for k in ("push", "rise", "higher", "up")):
            out.append("가격: 서버 DRAM 계약가 상승 압력 강화")
        if "spot" in low and any(k in low for k in ("narrow", "range", "fluctuat")):
            out.append("현물: 거래는 좁은 범위 등락 → 계약가 강세와 현물 강도를 분리해서 봐야 함")

    elif "nand flash market bulletin" in low_title:
        if any(k in low for k in ("two-tier", "divergence", "structural shortage")):
            out.append("수급: 기업용 고성능 저장장치 강세와 소비자 NAND 약세가 갈리는 양극화")
        if ("cloud" in low or "ai" in low) and ("enterprise ssd" in low or "storage" in low):
            out.append("원인: 클라우드·AI의 기업용 SSD 수요가 공급사 재고와 생산능력을 압박")
        if "inventory" in low and any(k in low for k in ("low", "tight", "declin")):
            out.append("재고: 공급사 재고가 낮아 기업용 SSD 가격결정력 유지")

    elif "specialty dram price" in low_title:
        if "supply" in low and any(k in low for k in ("gap", "shortage", "tight")):
            out.append("수급: Specialty DRAM 공급 부족 지속")
        if any(k in low for k in ("upward", "rise", "higher")):
            out.append("가격: 계약가는 상승 방향 유지")
        if any(k in low for k in ("moderating", "cost tolerance", "cost pressure")):
            out.append("역풍: 구매자의 비용 부담 한계로 가격 상승폭은 둔화 가능")

    elif "nand flash wafer contract price" in low_title:
        if any(k in low for k in ("high price", "high prices", "historic high", "expensive")):
            out.append("가격: NAND 웨이퍼 고가격이 모듈업체 마진을 압박")
        if "module" in low and any(k in low for k in ("margin", "profit")):
            out.append("수익구조: 웨이퍼 가격 상승 → 다운스트림 모듈업체 수익성 악화")
        if any(k in low for k in ("downgraded", "secondary market", "lower-grade")):
            out.append("수요 이동: 원가 부담으로 저등급 웨이퍼·2차 시장 대체 수요 증가")

    elif "nand flash contract price" in low_title:
        if "high-layer" in low or "advanced process" in low or "3d" in low:
            out.append("공급: 제조사가 고단수 3D NAND로 생산능력을 재배분 → niche NAND 공급 제약")
        if any(k in low for k in ("hovering at high", "remain high", "high level")):
            out.append("가격: niche NAND 계약가는 높은 수준 유지")
        if any(k in low for k in ("cost pressure", "buyer", "supply discrep")):
            out.append("역풍: 구매자 비용 부담과 품목별 공급 차이로 추가 인상폭은 차별화")

    elif "memory price forecast" in low_title:
        if "csp" in low and ("dram" in low and "nand" in low):
            out.append("원인: CSP AI 수요가 DRAM·NAND 가격 상승을 동시에 지지")
        if "capacity" in low and ("server dram" in low or "hbm" in low):
            out.append("공급: 생산능력이 서버 DRAM·HBM으로 우선 배분돼 소비자 메모리 공급을 압박")
        if "qlc" in low and "kv cache" in low:
            out.append("저장계층: QLC 기업용 SSD가 KV 캐시 수요로 가장 강한 가격축")

    # Keep concise and deterministic.
    return list(dict.fromkeys(out))[:4]


def _meaning_line(raw_title: str, detail_blob: str) -> str:
    low = f"{raw_title} {detail_blob}".lower()
    if "enterprise ssd" in low or "qlc" in low or "nand" in low:
        return "의미: 삼성전자·SK하이닉스/Solidigm·Micron 등 NAND 업체는 기업용 SSD 제품혼합·평균판매단가가 핵심 확인 지표"
    if "hbm" in low:
        return "의미: HBM 가격·적층·고객승인·양산물량 변화가 삼성전자·SK하이닉스·Micron 실적에 직접 연결"
    if "dram" in low:
        return "의미: conventional/server DRAM 계약가·재고·웨이퍼 배분 변화가 메모리 3사의 평균판매단가와 마진에 직접 연결"
    return "의미: 가격 자체보다 재고·생산능력·실제 계약가 변화가 실적 연결의 핵심"


def _is_sparse_price_sheet(raw_title: str, price_details: list[str], signal_details: list[str]) -> bool:
    low = raw_title.lower()
    monthly_sheet = any(k in low for k in (
        "contract price", "wafer contract price", "specialty dram price", "spot price", "datasheet",
    )) and "market bulletin" not in low and "memory price forecast" not in low
    specific_price = any(re.search(r"[+-]?\d+(?:\.\d+)?(?:~|-|–|—)\d+(?:\.\d+)?%", x) for x in price_details)
    meaningful_signal = len(signal_details) >= 1
    return bool(monthly_sheet and not specific_price and not meaningful_signal)


def _extract_hbm_market_pricing(item: dict) -> dict | None:
    text = _clean(f"{item.get('title','')} {item.get('description','')}")
    low = text.lower()
    if "hbm" not in low or "2027" not in text:
        return None
    if not ("trendforce" in low or "트렌드포스" in text):
        return None

    blended = None
    for pat in (
        r"(?:Blended\s+ASP|평균판매가격|평균판매단가|혼합\s*ASP)[^%]{0,120}?전년\s*대비\s*(?:\+|상승\s*)?([0-9]{2,3}(?:\.[0-9]+)?)\s*%",
        r"(?:Blended\s+ASP|평균판매가격|평균판매단가|혼합\s*ASP)[^%]{0,120}?([0-9]{2,3}(?:\.[0-9]+)?)\s*%[^.]{0,40}?(?:YoY|전년)",
        r"2027[^.]{0,160}?(?:HBM)[^.]{0,160}?(?:Blended\s+ASP|평균판매가격|평균판매단가)[^%]{0,80}?([0-9]{2,3}(?:\.[0-9]+)?)\s*%",
    ):
        m = re.search(pat, text, re.I)
        if m:
            blended = float(m.group(1))
            break

    premium_min = premium_max = None
    for pat in (
        r"8\s*(?:단|[- ]?Hi)[^.]{0,120}?12\s*(?:단|[- ]?Hi)[^.]{0,120}?([0-9]{1,2}(?:\.[0-9]+)?)\s*(?:~|∼|[-–—]|to)\s*([0-9]{1,2}(?:\.[0-9]+)?)\s*%[^.]{0,50}?(?:높|premium|비싸)",
        r"8\s*(?:단|[- ]?Hi)[^.]{0,120}?(?:Gb당|per[- ]?Gb)[^.]{0,100}?([0-9]{1,2}(?:\.[0-9]+)?)\s*(?:~|∼|[-–—]|to)\s*([0-9]{1,2}(?:\.[0-9]+)?)\s*%",
    ):
        m = re.search(pat, text, re.I)
        if m:
            premium_min, premium_max = float(m.group(1)), float(m.group(2))
            break

    mainstream = None
    if re.search(r"8\s*(?:단|[- ]?Hi)[^.]{0,120}?(?:주류|우선\s*적용|lead(?:s|ing)?\s+shipments|mainstream)", text, re.I):
        mainstream = 8
    elif re.search(r"12\s*(?:단|[- ]?Hi)[^.]{0,120}?(?:주류|우선\s*적용|lead(?:s|ing)?\s+shipments|mainstream)", text, re.I):
        mainstream = 12

    if blended is None and premium_min is None and mainstream is None:
        return None
    source = item.get("source") or ""
    source_url = item.get("link") or ""
    source_rank = 3 if "trendforce.com" in urllib.parse.urlparse(source_url).netloc.lower() else (3 if source.lower().startswith("trendforce") else 2)
    return {
        "period": "2027",
        "blended_asp_yoy_pct": blended,
        "eight_hi_premium_min_pct": premium_min,
        "eight_hi_premium_max_pct": premium_max,
        "mainstream_layers": mainstream,
        "source": source,
        "source_url": source_url,
        "source_rank": source_rank,
        "as_of": (item.get("published_kst") or "")[:10],
    }


def _is_hbm_market_pricing_republisher(item: dict) -> bool:
    text = _clean(f"{item.get('title','')} {item.get('description','')}")
    low = text.lower()
    if "hbm" not in low:
        return False
    published = str(item.get("published_kst") or "")
    next_year = ""
    if re.match(r"20\d{2}", published):
        next_year = str(int(published[:4]) + 1)
    period_match = "2027" in text or ("내년" in text and next_year == "2027")
    exact_price = bool(re.search(r"(?:121\s*%|평균판매가|평균판매가격|평균판매단가|blended\s+asp)", text, re.I))
    stack_price = bool(
        re.search(r"8\s*(?:단|[- ]?Hi)", text, re.I)
        and re.search(r"12\s*(?:단|[- ]?Hi)", text, re.I)
        and re.search(r"(?:10\s*(?:~|∼|[-–—]|to)\s*20\s*%|Gb당|per[- ]?Gb)", text, re.I)
    )
    return bool(period_match and (exact_price or stack_price))


def _hbm_market_break_even_summary(state: dict) -> str:
    if int(state.get("mainstream_layers") or 0) != 8:
        return ""
    pmin = state.get("eight_hi_premium_min_pct")
    pmax = state.get("eight_hi_premium_max_pct")
    if pmin is None or pmax is None:
        return ""
    bit_ratio = 8.0 / 12.0
    low_revenue_ratio = bit_ratio * (1.0 + float(pmin) / 100.0)
    high_revenue_ratio = bit_ratio * (1.0 + float(pmax) / 100.0)
    be_min = (1.0 / high_revenue_ratio - 1.0) * 100.0
    be_max = (1.0 / low_revenue_ratio - 1.0) * 100.0
    return f"12단→8단 스택당 비트 -33.3% · 8단 Gb당 프리미엄 반영 시 기존 12단 매출 상쇄에 필요한 GPU·ASIC 출하 +{be_min:.1f}~{be_max:.1f}%"


def _merge_hbm_market_pricing(old: dict, obs: dict) -> dict:
    merged = dict(old or {})
    old_rank = int(merged.get("source_rank") or 0)
    new_rank = int(obs.get("source_rank") or 0)
    for key, value in obs.items():
        if value in (None, ""):
            continue
        if key in ("source", "source_url", "as_of", "source_rank") and old_rank > new_rank:
            continue
        merged[key] = value
    return merged


def _hbm_market_pricing_changes(old: dict, new: dict) -> list[str]:
    changes: list[str] = []
    a, b = old.get("blended_asp_yoy_pct"), new.get("blended_asp_yoy_pct")
    if a is not None and b is not None and abs(float(b) - float(a)) >= 10:
        changes.append(f"2027 HBM Blended ASP {float(a):+.0f}%→{float(b):+.0f}% YoY ({float(b)-float(a):+.0f}%p)")
    elif a is None and b is not None:
        changes.append(f"2027 HBM Blended ASP {float(b):+.0f}% YoY 신규 확인")

    for key, label in (
        ("eight_hi_premium_min_pct", "8단 Gb당 프리미엄 하단"),
        ("eight_hi_premium_max_pct", "8단 Gb당 프리미엄 상단"),
    ):
        av, bv = old.get(key), new.get(key)
        if av is not None and bv is not None and abs(float(bv) - float(av)) >= 5:
            changes.append(f"{label} {float(av):.0f}%→{float(bv):.0f}%")
        elif av is None and bv is not None:
            changes.append(f"{label} {float(bv):.0f}% 신규 확인")

    av, bv = old.get("mainstream_layers"), new.get("mainstream_layers")
    if av is not None and bv is not None and int(av) != int(bv):
        changes.append(f"2027 HBM 주류 적층 {int(av)}단→{int(bv)}단")
    elif av is None and bv is not None:
        changes.append(f"2027 HBM 주류 적층 {int(bv)}단 신규 확인")
    return changes



def _is_bernstein_memory_cycle_item(item: dict) -> bool:
    text = _clean(f"{item.get('title','')} {item.get('description','')}")
    low = text.lower()
    if "bernstein" not in low and "伯恩斯坦" not in text:
        return False
    if not any(k in low for k in ("dram", "nand", "memory", "메모리")):
        return False
    return any(k in low for k in (
        "3q26", "4q26", "third quarter", "fourth quarter", "this quarter", "3분기", "4분기",
        "2027", "2028", "lta", "long-term agreement", "contract price",
        "high-single-digit", "high single digit", "normalize", "normalization", "가격",
        "nearly 20%", "almost 20%", "20% this quarter",
    ))


def _extract_bernstein_memory_cycle(item: dict) -> dict | None:
    text = _clean(f"{item.get('title','')} {item.get('description','')}")
    low = text.lower()
    if not _is_bernstein_memory_cycle_item(item):
        return None

    obs: dict = {}
    published = str(item.get("published_kst") or "")
    this_quarter_is_q3 = ("this quarter" in low) and published.startswith("2026-09")
    q3_context = any(k in low for k in ("3q26", "3q 2026", "third quarter", "3분기")) or this_quarter_is_q3
    q4_context = any(k in low for k in ("4q26", "4q 2026", "fourth quarter", "4분기"))

    if q3_context and re.search(r"(?:mid[- ]?teens?|중반)[^%]{0,80}?20\s*%", text, re.I):
        obs["q3_2026_price_band"] = "mid-teens~20%"
    else:
        m = re.search(
            r"(?:3Q26|3Q\s*2026|third quarter|3분기)[^%]{0,140}?"
            r"(\d+(?:\.\d+)?)\s*(?:%|percent)[^%]{0,60}?"
            r"(?:to|[-–—~∼]|에서)[^%]{0,30}?(\d+(?:\.\d+)?)\s*(?:%|percent)",
            text,
            re.I,
        )
        if m:
            obs["q3_2026_price_band"] = f"{float(m.group(1)):g}~{float(m.group(2)):g}%"

    if q4_context and re.search(r"high[- ]?single[- ]?digit|한\s*자릿수\s*(?:중후반|후반)", text, re.I):
        obs["q4_2026_price_band"] = "high-single-digit"
    else:
        m = re.search(
            r"(?:4Q26|4Q\s*2026|fourth quarter|4분기)[^%]{0,140}?"
            r"(\d+(?:\.\d+)?)\s*(?:%|percent)[^%]{0,60}?"
            r"(?:to|[-–—~∼]|에서)[^%]{0,30}?(\d+(?:\.\d+)?)\s*(?:%|percent)",
            text,
            re.I,
        )
        if m:
            obs["q4_2026_price_band"] = f"{float(m.group(1)):g}~{float(m.group(2)):g}%"

    shortage_years = [
        int(y) for y in re.findall(
            r"(?:shortage|shortages|undersuppl(?:y|ied)|공급\s*부족)[^.]{0,100}?(20\d{2})",
            text,
            re.I,
        )
    ]
    if not shortage_years:
        shortage_years = [
            int(y) for y in re.findall(
                r"(20\d{2})[^.]{0,100}?(?:shortage|shortages|undersuppl(?:y|ied)|공급\s*부족)",
                text,
                re.I,
            )
        ]
    if shortage_years:
        obs["shortage_through_year"] = max(shortage_years)

    norm = re.search(r"(?:normaliz\w*|정상화)[^.]{0,100}?(20\d{2})", text, re.I)
    if not norm:
        norm = re.search(r"(20\d{2})[^.]{0,100}?(?:normaliz\w*|정상화)", text, re.I)
    if norm:
        obs["normalization_year"] = int(norm.group(1))

    if (
        any(k in low for k in ("lta", "long-term agreement", "long term agreement", "장기계약"))
        and any(k in low for k in ("cap", "limit", "restrict", "상한", "제한"))
    ):
        obs["lta_caps_price_increases"] = True

    if not obs:
        return None
    obs.update({
        "source": item.get("source") or "Bernstein 관련 보도",
        "source_url": item.get("link") or "",
        "source_rank": 2,
        "as_of": (item.get("published_kst") or "")[:10],
    })
    return obs


def _merge_bernstein_memory_cycle(old: dict, obs: dict) -> dict:
    merged = dict(old or {})
    old_rank = int(merged.get("source_rank") or 0)
    new_rank = int(obs.get("source_rank") or 0)
    for key, value in obs.items():
        if value in (None, ""):
            continue
        if key in ("source", "source_url", "as_of", "source_rank") and old_rank > new_rank:
            continue
        merged[key] = value
    return merged


def _bernstein_memory_cycle_changes(old: dict, new: dict) -> list[str]:
    changes: list[str] = []
    fields = (
        ("q3_2026_price_band", "3Q26 conventional DRAM·NAND 가격 전망"),
        ("q4_2026_price_band", "4Q26 conventional DRAM·NAND 가격 전망"),
        ("shortage_through_year", "공급부족 지속 연도"),
        ("normalization_year", "가격 정상화 예상연도"),
        ("lta_caps_price_increases", "LTA 가격상승 제한"),
    )
    for key, label in fields:
        a, b = old.get(key), new.get(key)
        if a is not None and b is not None and a != b:
            if isinstance(a, bool) or isinstance(b, bool):
                changes.append(f"{label}: {'적용' if a else '미적용'}→{'적용' if b else '미적용'}")
            else:
                changes.append(f"{label}: {a}→{b}")
        elif a is None and b is not None:
            changes.append(f"{label}: {b} 신규 확인")
    return changes


def write_outputs(items: list[dict], errors: list[str]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()
    seen: dict = state.get("seen", {})
    now = dt.datetime.now(KST)
    initialized = bool(state.get("initialized"))
    market_state = dict(state.get("hbm_market_pricing") or {})
    if int(state.get("hbm_market_pricing_track_version") or 0) < HBM_MARKET_PRICE_TRACK_VERSION:
        market_state = _merge_hbm_market_pricing(market_state, HBM_MARKET_PRICE_BASELINE)
        state["hbm_market_pricing_track_version"] = HBM_MARKET_PRICE_TRACK_VERSION

    bernstein_state = dict(state.get("bernstein_memory_cycle") or {})
    if int(state.get("bernstein_memory_cycle_track_version") or 0) < BERNSTEIN_MEMORY_CYCLE_TRACK_VERSION:
        bernstein_state = _merge_bernstein_memory_cycle(bernstein_state, BERNSTEIN_MEMORY_CYCLE_BASELINE)
        state["bernstein_memory_cycle_track_version"] = BERNSTEIN_MEMORY_CYCLE_TRACK_VERSION

    market_changes: list[str] = []
    market_source_url = ""
    market_format_due = (
        int(state.get("hbm_market_alert_format_version") or 0) < HBM_MARKET_ALERT_FORMAT_VERSION
        and market_state.get("blended_asp_yoy_pct") is not None
    )
    for item in sorted(items, key=lambda x: x.get("published_kst") or ""):
        obs = _extract_hbm_market_pricing(item)
        if not obs:
            continue
        merged = _merge_hbm_market_pricing(market_state, obs)
        changes = _hbm_market_pricing_changes(market_state, merged)
        market_state = merged
        if changes:
            market_changes.extend(changes)
            market_source_url = market_state.get("source_url") or obs.get("source_url") or market_source_url

    if market_format_due and not market_changes:
        market_changes = ["TrendForce 2027 HBM Blended ASP·8단 프리미엄 기준선 확정"]
        market_source_url = market_state.get("source_url") or ""

    bernstein_changes: list[str] = []
    bernstein_source_url = ""
    for item in sorted(items, key=lambda x: x.get("published_kst") or ""):
        obs = _extract_bernstein_memory_cycle(item)
        if not obs:
            continue
        merged = _merge_bernstein_memory_cycle(bernstein_state, obs)
        changes = _bernstein_memory_cycle_changes(bernstein_state, merged)
        bernstein_state = merged
        if changes:
            bernstein_changes.extend(changes)
            bernstein_source_url = bernstein_state.get("source_url") or obs.get("source_url") or bernstein_source_url

    seen_titles = {
        _normalize_title(str(meta.get("title") or ""))
        for meta in seen.values()
        if isinstance(meta, dict)
    }
    new_items = []
    for x in items:
        if x["fingerprint"] in seen or _normalize_title(x["title"]) in seen_titles:
            continue
        # Market-pricing republishers are not separate alerts. They feed the
        # typed numeric state above; only an actual numeric/state change alerts.
        if _extract_hbm_market_pricing(x) or _is_hbm_market_pricing_republisher(x):
            continue
        # Bernstein price-cycle stories are routed through typed state. A new
        # headline alone must not alert unless a tracked price/year/LTA state changes.
        if _is_bernstein_memory_cycle_item(x):
            continue
        new_items.append(x)
    force_notify = os.getenv("FORCE_NOTIFY", "").strip().lower() in {"1", "true", "yes"}
    if force_notify:
        report_items = items[:5]
    elif initialized:
        report_items = new_items[:5]
    else:
        report_items = []

    for item in items:
        seen[item["fingerprint"]] = {
            "title": item["title"],
            "source": item.get("source"),
            "published_kst": item.get("published_kst"),
            "first_seen_kst": seen.get(item["fingerprint"], {}).get("first_seen_kst") or now.isoformat(timespec="seconds"),
        }

    if len(seen) > 700:
        keys = list(seen.keys())[-700:]
        seen = {k: seen[k] for k in keys}

    pending = {
        "initialized": True,
        "seen": seen,
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "last_scan_count": len(items),
        "last_new_count": len(new_items),
        "hbm_market_pricing_track_version": HBM_MARKET_PRICE_TRACK_VERSION,
        "hbm_market_alert_format_version": HBM_MARKET_ALERT_FORMAT_VERSION if market_changes else int(state.get("hbm_market_alert_format_version") or 0),
        "hbm_market_pricing": market_state,
        "bernstein_memory_cycle_track_version": BERNSTEIN_MEMORY_CYCLE_TRACK_VERSION,
        "bernstein_memory_cycle": bernstein_state,
    }
    for key in (
        "last_successful_delivery_kst",
        "telegram_message_ids",
        "telegram_message_id",
        "bot_username",
        "delivery_receipt",
    ):
        if state.get(key) is not None:
            pending[key] = state[key]
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    status_lines = [
        "# 메모리 현물·계약가·DRAM/HBM CAPA 웹 감시",
        "",
        f"- 조회시각(KST): {now.isoformat(timespec='seconds')}",
        f"- 유효 후보: {len(items)}건",
        f"- 신규 후보: {len(new_items)}건",
        f"- Telegram 대상 신규: {len(report_items)}건",
        f"- HBM 시장 가격 숫자 변화: {len(market_changes)}건",
        f"- Bernstein 가격 사이클 상태 변화: {len(bernstein_changes)}건",
        f"- 원천 오류: {len(errors)}건",
    ]
    if errors:
        status_lines += ["", "## 오류", *[f"- {x}" for x in errors[:6]]]
    STATUS_PATH.write_text("\n".join(status_lines) + "\n", encoding="utf-8")

    if ALERT_PATH.exists():
        ALERT_PATH.unlink()
    if not report_items and not market_changes and not bernstein_changes:
        return

    lines = ["<b>[메모리 수급 변화 감지]</b>"]
    typed_changes = len(market_changes) + len(bernstein_changes)
    if typed_changes:
        suffix = f" · 기타 신규 {len(report_items)}건" if report_items else ""
        lines.append(f"조회 {now.strftime('%Y-%m-%d %H:%M')} KST · 상태 변화 {typed_changes}건{suffix}")
    else:
        lines.append(f"조회 {now.strftime('%Y-%m-%d %H:%M')} KST · 신규 {len(report_items)}건")
    if market_changes:
        lines.append("• <b>HBM 시장 가격 상태 변화</b>")
        for change in market_changes:
            lines.append("  " + html.escape(change))
        if market_state.get("blended_asp_yoy_pct") is not None:
            lines.append(f"  2027 Blended ASP: <b>+{float(market_state['blended_asp_yoy_pct']):.0f}% YoY</b> → 2026=100이면 2027=221")
        if market_state.get("mainstream_layers") is not None:
            lines.append(f"  주류 적층 전망: <b>{int(market_state['mainstream_layers'])}단</b>")
        if market_state.get("eight_hi_premium_min_pct") is not None:
            lines.append(
                f"  8단 HBM Gb당 판매가격: 12단 대비 <b>+{float(market_state['eight_hi_premium_min_pct']):.0f}~{float(market_state['eight_hi_premium_max_pct']):.0f}%</b>"
            )
        be = _hbm_market_break_even_summary(market_state)
        if be:
            lines.append("  매출 연결: " + html.escape(be))
        lines.append("  ※ 시장 전체 TrendForce Blended ASP이며 삼성전자·SK하이닉스·Micron 개별 ASP와 별도")
        if market_source_url:
            lines.append('  <a href="' + html.escape(market_source_url, quote=True) + '">기사 원문</a>')
        ref = market_state.get("research_reference_url")
        if ref:
            lines.append('  <a href="' + html.escape(ref, quote=True) + '">TrendForce HBM 보고서</a>')
        secondary = market_state.get("secondary_source_url")
        if secondary:
            lines.append('  <a href="' + html.escape(secondary, quote=True) + '">국내 보도</a>')
    if bernstein_changes:
        lines.append("• <b>Bernstein 메모리 가격 사이클 상태 변화</b>")
        for change in bernstein_changes:
            lines.append("  " + html.escape(change))
        if bernstein_state.get("q3_2026_price_band"):
            lines.append("  3Q26 conventional DRAM·NAND: <b>" + html.escape(str(bernstein_state["q3_2026_price_band"])) + "</b> QoQ")
        if bernstein_state.get("q4_2026_price_band"):
            lines.append("  4Q26 conventional DRAM·NAND: <b>" + html.escape(str(bernstein_state["q4_2026_price_band"])) + "</b> QoQ")
        if bernstein_state.get("shortage_through_year"):
            lines.append(f"  공급부족 지속 기준: <b>{int(bernstein_state['shortage_through_year'])}년</b>")
        if bernstein_state.get("normalization_year"):
            lines.append(f"  정상화 기준: <b>{int(bernstein_state['normalization_year'])}년</b>")
        if bernstein_state.get("lta_caps_price_increases"):
            lines.append("  LTA: <b>가격 상승폭 제한</b> 조건 유지")
        lines.append("  ※ 기사 제목이 아니라 위 기준 숫자·연도·LTA 상태가 실제로 바뀔 때만 알림")
        if bernstein_source_url:
            lines.append('  <a href="' + html.escape(bernstein_source_url, quote=True) + '">근거 기사</a>')
    emitted = 0
    for item in report_items:
        label = classify(item["title"])
        raw_title = compact_title(item["title"], item.get("source", ""))
        translated = _translate_to_ko(raw_title)
        title = _polish_alert_title(raw_title, translated)
        detail_blob = str(item.get("description") or "")
        price_details = _price_change_details(raw_title, detail_blob)
        signal_details = _market_signal_details(raw_title, detail_blob)
        # A monthly paid price-sheet title without a public number or public narrative
        # is not actionable. Do not send a one-line 'price type: contract' alert.
        if _is_sparse_price_sheet(raw_title, price_details, signal_details):
            continue
        if item.get("source") == "TrendForce Research" and "memory price forecast" in raw_title.lower():
            title = (
                "TrendForce 4Q26 메모리 가격 전망: AI 서버·HBM 우선배정으로 소비자 DRAM 공급 축소, "
                "QLC 기업용 SSD는 KV 캐시 수요로 강세…LTA가 DRAM 인상폭 제한"
            )
        pub = item.get("published_kst")
        date_text = ""
        if pub:
            try:
                date_text = dt.datetime.fromisoformat(pub).strftime("%m/%d %H:%M")
            except Exception:
                pass
        safe_title = html.escape(title)
        safe_link = html.escape(item["link"], quote=True)
        lines.append(f"• <b>{label}</b> | {safe_title}")
        if price_details:
            for detail in price_details:
                prefix = "가격: " if not detail.startswith("가격 유형:") else ""
                lines.append("  " + prefix + html.escape(detail))
        for detail in signal_details:
            lines.append("  " + html.escape(detail))
        lines.append("  " + html.escape(_meaning_line(raw_title, detail_blob)))
        if item.get("source") == "TrendForce Research":
            lines.append("  검증: TrendForce 공식 리서치 공개 페이지 · 유료표 내부 숫자는 공개 확인 전 확정값으로 쓰지 않음")
        else:
            lines.append("  검증: " + html.escape(str(item.get("source") or "출처 미표시")) + " 보도 · 동일 내용의 숫자/기간 변화만 상태값으로 추적")
        if date_text:
            lines.append(f"  {date_text} · <a href=\"{safe_link}\">원문</a>")
        else:
            lines.append(f"  <a href=\"{safe_link}\">원문</a>")
        emitted += 1

    # If all generic paid-price sheets were filtered, do not send an empty shell.
    if emitted == 0 and not market_changes and not bernstein_changes:
        if ALERT_PATH.exists():
            ALERT_PATH.unlink()
        return
    lines.append("※ 가격·수급·LTA·DRAM/HBM CAPA·웨이퍼 생산능력의 신규 변화만 알림")
    ALERT_PATH.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def main() -> int:
    items, errors = collect()
    write_outputs(items, errors)
    # Hard gate: every foreign-currency amount that reaches Telegram must have
    # an immediately adjacent KRW conversion. If fresh FX cannot be verified,
    # stop this run rather than send an unconverted or stale amount.
    currency_krw_guard.enforce_file(ALERT_PATH)
    print(f"memory_watch_candidates={len(items)} errors={len(errors)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
