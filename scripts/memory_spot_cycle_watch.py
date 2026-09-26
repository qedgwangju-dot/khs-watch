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

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "memory_spot_cycle_watch_state.json"
OUT_DIR = ROOT / "out"
PENDING_PATH = OUT_DIR / "memory_spot_cycle_watch_pending_state.json"
ALERT_PATH = OUT_DIR / "memory_spot_cycle_watch_telegram.txt"
STATUS_PATH = OUT_DIR / "memory_spot_cycle_watch_status.md"
KST = ZoneInfo("Asia/Seoul")
TREND_RESEARCH_URL = "https://www.trendforce.com/research/memory-storage"
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
    ("ko", '서버 DRAM 고정가격 계약가격 ASP 삼성전자 SK하이닉스'),
    ("ko", '2028 HBM 공급확약 브로드컴 엔비디아 구글 AMD'),
    # DRAM physical capacity / wafer-start / new-fab cycle: do not miss supply expansion.
    ("ko", 'DRAM 생산능력 웨이퍼 투입량 월 생산량 증설 삼성전자 P4 SK하이닉스 M15X 마이크론'),
    ("ko", '어플라이드 머티어리얼즈 Citi TMT DRAM 생산능력 웨이퍼 160만 200만 40만'),
    ("ko", 'DRAM 신규 팹 그린필드 장비투자 웨이퍼 스타트 P4 P5 M15X Y1'),
    ("en", 'DRAM spot price shortage BofA Bank of America memory'),
    ("en", 'NAND spot price shortage TrendForce memory'),
    ("en", 'server DRAM contract price TrendForce Samsung SK hynix Micron'),
    ("en", '2028 HBM supply commitment Broadcom NVIDIA Google AMD'),
    ("en", 'HBM trade ratio Micron HBM4E DRAM capacity'),
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
    "outlook", "revised", "revision", "wafer", "wafer start", "wafer starts", "wspm",
    "greenfield", "fab", "factory", "ramp", "ramp-up", "equipment investment",
    "현물", "고정가", "계약가", "가격", "부족", "공급", "재고", "증설", "인상",
    "상향", "전망", "확약", "배정", "수급", "웨이퍼", "생산능력", "투입량",
    "신규 팹", "그린필드", "램프업", "가동", "장비투자", "설비투자",
}
HIGH_SIGNAL = {
    "bofa", "bank of america", "trendforce", "dram exchange", "dramexchange", "omdia",
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
    if "spot" in lower and "price" in lower:
        return "메모리 현물가격 관련 신규 상승·수급 변화 기사 감지"
    if "wafer" in lower or "capacity" in lower or "greenfield" in lower:
        return "DRAM 웨이퍼 생산능력·신규 팹 증설 관련 신규 변화 기사 감지"
    if "shortage" in lower or "supply" in lower:
        return "메모리 공급부족·수급 관련 신규 변화 기사 감지"
    if "hbm" in lower:
        return "HBM 수요·공급능력 관련 신규 변화 기사 감지"
    if "dram" in lower:
        return "DRAM 가격·수급 관련 신규 변화 기사 감지"
    if "nand" in lower or "ssd" in lower:
        return "NAND·SSD 가격·수급 관련 신규 변화 기사 감지"
    return "해외 메모리 관련 신규 변화 기사 감지"


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
                link = _clean(node.findtext("link"))
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
    search_items, search_errors = _collect_trendforce_search(cutoff)
    items.extend(direct_items)
    items.extend(search_items)
    errors.extend(direct_errors)
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
    href_titles: dict[str, str] = {}

    for listing_url in listing_urls:
        try:
            listing_html = _fetch(listing_url).decode("utf-8", errors="ignore")
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
        "capacity", "capa", "wafer", "greenfield", "fab", "factory", "ramp",
        "생산능력", "웨이퍼", "증설", "신규 팹", "그린필드", "램프업",
    )
    if "memory price forecast" in t or "메모리 가격 전망" in t:
        return "DRAM/NAND"
    if "hbm" in t:
        return "HBM/CAPA"
    if "dram" in t or "디램" in t:
        if any(x in t for x in capacity_terms):
            return "DRAM/CAPA"
    if "spot" in t or "현물" in t:
        return "현물가"
    if "contract" in t or "고정가" in t or "계약가" in t:
        return "계약가"
    if "nand" in t or "낸드" in t or "ssd" in t:
        return "NAND/eSSD"
    if "inventory" in t or "재고" in t or "sufficiency" in t:
        return "재고/수급"
    return "DRAM"


def compact_title(title: str, source: str) -> str:
    suffix = f" - {source}" if source else ""
    if suffix and title.endswith(suffix):
        title = title[: -len(suffix)]
    return title.strip()


def write_outputs(items: list[dict], errors: list[str]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()
    seen: dict = state.get("seen", {})
    now = dt.datetime.now(KST)
    initialized = bool(state.get("initialized"))

    seen_titles = {
        _normalize_title(str(meta.get("title") or ""))
        for meta in seen.values()
        if isinstance(meta, dict)
    }
    new_items = [
        x for x in items
        if x["fingerprint"] not in seen
        and _normalize_title(x["title"]) not in seen_titles
    ]
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
    }
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    status_lines = [
        "# 메모리 현물·계약가·DRAM/HBM CAPA 웹 감시",
        "",
        f"- 조회시각(KST): {now.isoformat(timespec='seconds')}",
        f"- 유효 후보: {len(items)}건",
        f"- 신규 후보: {len(new_items)}건",
        f"- Telegram 대상 신규: {len(report_items)}건",
        f"- 원천 오류: {len(errors)}건",
    ]
    if errors:
        status_lines += ["", "## 오류", *[f"- {x}" for x in errors[:6]]]
    STATUS_PATH.write_text("\n".join(status_lines) + "\n", encoding="utf-8")

    if ALERT_PATH.exists():
        ALERT_PATH.unlink()
    if not report_items:
        return

    lines = [
        "<b>[메모리 수급 변화 감지]</b>",
        f"조회 {now.strftime('%Y-%m-%d %H:%M')} KST · 신규 {len(report_items)}건",
    ]
    for item in report_items:
        label = classify(item["title"])
        raw_title = compact_title(item["title"], item.get("source", ""))
        translated = _translate_to_ko(raw_title)
        title = _polish_alert_title(raw_title, translated)
        detail_blob = str(item.get("description") or "")
        if item.get("source") == "TrendForce Research" and "memory price forecast" in raw_title.lower():
            essd = re.search(
                r"Enterprise SSD[^0-9]{0,120}(\d{1,2})\s*[-~–—]\s*(\d{1,2})\s*%",
                detail_blob,
                re.IGNORECASE,
            )
            nand = re.search(
                r"(?:Overall\s+)?NAND Flash[^0-9]{0,120}(\d{1,2})\s*[-~–—]\s*(\d{1,2})\s*%",
                detail_blob,
                re.IGNORECASE,
            )
            if essd and nand:
                title = (
                    f"TrendForce 4Q26: Enterprise SSD +{essd.group(1)}~{essd.group(2)}% QoQ, "
                    f"NAND 전체 +{nand.group(1)}~{nand.group(2)}%…서버 DRAM·HBM 우선배정으로 소비자 DRAM 공급 축소, LTA가 DRAM 인상폭 제한"
                )
            elif "4q26" in raw_title.lower():
                title = (
                    "TrendForce 4Q26 메모리 가격 전망: AI 서버·HBM 우선배정으로 소비자 DRAM 공급 축소, "
                    "QLC Enterprise SSD는 KV Cache 수요로 강세…LTA가 DRAM 인상폭 제한"
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
        if date_text:
            lines.append(f"  {date_text} · <a href=\"{safe_link}\">원문</a>")
        else:
            lines.append(f"  <a href=\"{safe_link}\">원문</a>")
    lines.append("※ 가격·수급·LTA·DRAM/HBM CAPA·웨이퍼 생산능력의 신규 변화만 알림")
    ALERT_PATH.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def main() -> int:
    items, errors = collect()
    write_outputs(items, errors)
    print(f"memory_watch_candidates={len(items)} errors={len(errors)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
