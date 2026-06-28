#!/usr/bin/env python3
"""KHS transformer tariff policy watch.

This lane catches high-impact transformer and grid-equipment tariff signals.
It monitors both official U.S. policy sources and fresh Korean market-media
amplification when the story is tied to an official Section 232 basis.
"""

from __future__ import annotations

import datetime as dt
import email.utils
import hashlib
import html
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "out"
DATA_DIR = ROOT / "data"
ALERTS_JSON_PATH = OUT_DIR / "khs_policy_watch_alerts.json"
SEEN_PATH = DATA_DIR / "khs_transformer_tariff_policy_seen.json"
KST = ZoneInfo("Asia/Seoul")
MAX_AGE_HOURS = int(os.getenv("KHS_SOURCE_MAX_AGE_HOURS", "72"))
MAX_ALERTS = int(os.getenv("KHS_TRANSFORMER_TARIFF_MAX_ALERTS", "3"))
UA = os.getenv("SEC_USER_AGENT", "KHS-transformer-tariff-policy-watch contact=github-actions")

OFFICIAL_BASIS = [
    (
        "White House fact sheet - steel/aluminum/copper tariffs",
        "https://www.whitehouse.gov/fact-sheets/2026/04/fact-sheet-president-donald-j-trump-strengthens-tariffs-on-steel-aluminum-and-copper-imports/",
    ),
    (
        "Federal Register - Section 232 steel/aluminum/copper proclamation",
        "https://www.federalregister.gov/documents/2026/04/09/2026-06960/strengthening-actions-taken-to-adjust-imports-of-aluminum-steel-and-copper-into-the-united-states",
    ),
]

SOURCES = [
    (
        "Federal Register transformer tariff",
        "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bterm%5D="
        + urllib.parse.quote("transformer section 232 tariff electrical grid equipment steel derivative")
        + "&order=newest&per_page=20",
        "federal_register_json",
    ),
    (
        "Federal Register electrical equipment tariff",
        "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bterm%5D="
        + urllib.parse.quote("electrical equipment tariff steel aluminum derivative section 232")
        + "&order=newest&per_page=20",
        "federal_register_json",
    ),
    (
        "Korean transformer tariff news",
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote('"대형 변압기" 관세 25% 15% 미국 효성 포스코')
        + "&hl=ko&gl=KR&ceid=KR:ko",
        "rss",
    ),
    (
        "Korean power-equipment tariff news",
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote("변압기 전력기기 관세 인하 미국 15% 25%")
        + "&hl=ko&gl=KR&ceid=KR:ko",
        "rss",
    ),
    (
        "Daum/The Guru transformer tariff follow-up",
        "https://v.daum.net/v/20260628072105404",
        "html",
    ),
]

TRANSFORMER_TERMS = [
    "transformer", "transformers", "large power transformer", "power transformer",
    "distribution transformer", "electrical transformer", "electrical equipment",
    "electrical grid equipment", "grid equipment", "electric power transmission",
    "grain-oriented electrical steel", "grain oriented electrical steel", "electrical steel",
    "GOES", "대형 변압기", "변압기", "전력기기", "전력 기자재", "전력망 장비", "전기강판",
]
TARIFF_TERMS = [
    "tariff", "tariffs", "duty", "duties", "section 232", "232조", "관세", "상호관세",
    "철강", "알루미늄", "파생상품", "derivative", "derivatives",
]
RATE_TERMS = [
    "25%", "25 percent", "15%", "15 percent", "인하", "lower", "lowered", "reduce",
    "reduced", "reduction", "cut", "조정",
]
KOREA_VALUE_TERMS = [
    "한국", "korea", "효성", "hyosung", "포스코", "posco", "hd현대일렉트릭",
    "hyundai electric", "ls electric", "일진전기", "대한전선",
]
MARKET_NEWS_PUBLISHERS = [
    "연합뉴스", "yna", "한국경제", "매일경제", "서울경제", "전자신문", "더구루", "the guru", "daum",
]

SECTORS = ["전력기기/변압기", "관세/수출주", "전력망/데이터센터"]
POLICY_CHECK = (
    "미국 Section 232/철강·알루미늄 파생상품 적용에서 대형 변압기·전력망 장비 관세율 "
    "25%→15% 적용 여부, 품목코드, 시행일, 예외·원산지 요건, 기존 계약 가격 조정 가능성 확인"
)
RISK_TABLE = (
    "관세율 인하: 한국 변압기 가격경쟁력·수주마진 개선 가능 / "
    "품목코드·원산지·예외 미확정: 직접 수혜 제한 / "
    "공급능력·납기 병목: 수주 기대 과열 가능 / "
    "4월 공식 문서 재해석이면 6월 보도 신규성은 낮을 수 있음"
)
STRUCTURE_NOTE = (
    "핵심은 관세율 숫자 자체보다 미국 전력망·AI 데이터센터 투자에서 한국 전력기기 업체의 "
    "가격경쟁력, 수주 가능성, 매출 인식 시간이 바뀌는지입니다."
)
COUNTER = (
    "품목코드, 실제 적용세율, 시행일, 원산지 요건, 기존 계약 가격 조정 여부가 확인되지 않으면 "
    "수혜가 제한될 수 있습니다. 4월 공식 문서의 재해석이면 새 정책 발표가 아니라 국내 재확산 재료입니다."
)


def now_kst() -> dt.datetime:
    return dt.datetime.now(tz=KST)


def clean_text(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<script\b.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_text(url: str, timeout: int = 10) -> tuple[str | None, str | None]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept": "text/html,application/json,application/rss+xml,*/*"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace"), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def parse_kst_date(value: object) -> dt.datetime | None:
    raw = clean_text(value)
    if not raw:
        return None
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed.astimezone(KST) if parsed.tzinfo else parsed.replace(tzinfo=KST)
    except ValueError:
        pass
    try:
        parsed = email.utils.parsedate_to_datetime(raw)
        return parsed.astimezone(KST) if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc).astimezone(KST)
    except (TypeError, ValueError):
        pass
    match = re.search(r"(20\d{2})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})[.\-/일]?\s+(\d{1,2}):(\d{2})", raw)
    if match:
        year, month, day, hour, minute = (int(part) for part in match.groups())
        return dt.datetime(year, month, day, hour, minute, tzinfo=KST)
    match = re.search(r"(20\d{2})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})", raw)
    if match:
        year, month, day = (int(part) for part in match.groups())
        return dt.datetime(year, month, day, tzinfo=KST)
    return None


def age_hours(published: dt.datetime | None, now: dt.datetime) -> float | None:
    if not published:
        return None
    return (now - published).total_seconds() / 3600


def has_any(text: str, terms: list[str]) -> bool:
    lower = text.lower()
    return any(term.lower() in lower for term in terms)


def matched_terms(text: str, terms: list[str]) -> list[str]:
    lower = text.lower()
    return [term for term in terms if term.lower() in lower]


def looks_like_transformer_tariff(text: str) -> bool:
    return (
        has_any(text, TRANSFORMER_TERMS)
        and has_any(text, TARIFF_TERMS)
        and has_any(text, RATE_TERMS)
        and (has_any(text, KOREA_VALUE_TERMS) or has_any(text, ["section 232", "232조", "federal register", "white house"]))
    )


def market_source_allowed(publisher: str, text: str) -> bool:
    if has_any(publisher, MARKET_NEWS_PUBLISHERS):
        return True
    return has_any(text, ["코트라", "kotra", "무역협회", "kita", "산업통상자원부", "motir"])


def build_alert(*, source: str, title: str, link: str, summary: str, published: dt.datetime | None, status: str, matched: list[str]) -> dict:
    fingerprint = hashlib.sha256(f"transformer-tariff|{title}|{link}".encode("utf-8")).hexdigest()[:16]
    return {
        "source": source,
        "title": "미국, 대형 변압기 관세 25%→15% 인하 보도·공식근거 체크",
        "original_title": title,
        "link": link,
        "summary": summary[:900],
        "published_kst": published.isoformat(timespec="seconds") if published else "",
        "fingerprint": fingerprint,
        "matched": {"transformer_tariff_policy": matched[:14] or ["변압기 관세 정책"]},
        "importance": "상",
        "status": status,
        "impacts": ["돈 버는 능력", "할인율", "수급", "시간표"],
        "paths": ["이익", "정책 타임라인", "밸류체인", "수급", "계약 가시성"],
        "sectors": SECTORS[:],
        "transformer_tariff_policy_watch": True,
        "transformer_tariff_check": POLICY_CHECK,
        "transformer_tariff_risk_table": RISK_TABLE,
        "transformer_tariff_structure_note": STRUCTURE_NOTE,
        "official_basis": [{"source": label, "link": url} for label, url in OFFICIAL_BASIS],
        "counter": COUNTER,
        "reflection": "중간",
    }


def parse_federal_register_json(text: str, source_name: str, now: dt.datetime) -> list[dict]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    alerts: list[dict] = []
    for item in payload.get("results") or []:
        title = clean_text(item.get("title"))
        summary = clean_text(item.get("abstract") or item.get("excerpts") or "")
        link = str(item.get("html_url") or item.get("url") or "")
        published = parse_kst_date(item.get("publication_date"))
        haystack = f"{title} {summary} {link} {source_name}"
        if not looks_like_transformer_tariff(haystack):
            continue
        age = age_hours(published, now)
        if age is None or age < -1 or age > MAX_AGE_HOURS:
            continue
        hits = matched_terms(haystack, TRANSFORMER_TERMS + TARIFF_TERMS + RATE_TERMS + KOREA_VALUE_TERMS)
        alerts.append(build_alert(source=source_name, title=title, link=link, summary=summary, published=published, status="확정", matched=hits))
    return alerts


def parse_rss(text: str, source_name: str, now: dt.datetime) -> list[dict]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    alerts: list[dict] = []
    for item in root.findall(".//item"):
        title = clean_text(item.findtext("title"))
        summary = clean_text(item.findtext("description"))
        link = clean_text(item.findtext("link"))
        published = parse_kst_date(item.findtext("pubDate"))
        source_node = item.find("source")
        publisher = clean_text(source_node.text if source_node is not None else source_name)
        haystack = f"{title} {summary} {publisher} {source_name}"
        if not looks_like_transformer_tariff(haystack):
            continue
        if not market_source_allowed(publisher, haystack):
            continue
        age = age_hours(published, now)
        if age is None or age < -1 or age > MAX_AGE_HOURS:
            continue
        hits = matched_terms(haystack, TRANSFORMER_TERMS + TARIFF_TERMS + RATE_TERMS + KOREA_VALUE_TERMS)
        alerts.append(build_alert(source=publisher or source_name, title=title, link=link, summary=summary, published=published, status="예비", matched=hits))
    return alerts


def parse_html(text: str, source_name: str, source_url: str, now: dt.datetime) -> list[dict]:
    title_match = re.search(r"<meta[^>]+property=[\"']og:title[\"'][^>]+content=[\"']([^\"']+)[\"']", text, re.I)
    title = clean_text(title_match.group(1) if title_match else "")
    if not title:
        title_match = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
        title = clean_text(title_match.group(1) if title_match else source_name)
    summary_match = re.search(r"<meta[^>]+property=[\"']og:description[\"'][^>]+content=[\"']([^\"']+)[\"']", text, re.I)
    summary = clean_text(summary_match.group(1) if summary_match else text[:5000])
    haystack = f"{title} {summary} {clean_text(text[:12000])} {source_name}"
    if not looks_like_transformer_tariff(haystack):
        return []
    published = parse_kst_date(haystack)
    age = age_hours(published, now)
    if age is None or age < -1 or age > MAX_AGE_HOURS:
        return []
    hits = matched_terms(haystack, TRANSFORMER_TERMS + TARIFF_TERMS + RATE_TERMS + KOREA_VALUE_TERMS)
    return [build_alert(source=source_name, title=title, link=source_url, summary=summary, published=published, status="예비", matched=hits)]


def load_seen() -> dict:
    if not SEEN_PATH.exists():
        return {"seen": {}, "updated_at_kst": ""}
    try:
        return json.loads(SEEN_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"seen": {}, "updated_at_kst": ""}


def save_seen(seen: dict, now: dt.datetime) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    seen["updated_at_kst"] = now.isoformat(timespec="seconds")
    SEEN_PATH.write_text(json.dumps(seen, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_existing_alerts() -> list[dict]:
    if not ALERTS_JSON_PATH.exists():
        return []
    try:
        data = json.loads(ALERTS_JSON_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def write_alerts(alerts: list[dict]) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    ALERTS_JSON_PATH.write_text(json.dumps(alerts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    now = now_kst()
    candidates: list[dict] = []
    for source_name, source_url, source_type in SOURCES:
        text, error = fetch_text(source_url)
        if error:
            print(f"transformer_tariff_source_failed source={source_name} error={error}")
            continue
        if source_type == "federal_register_json":
            candidates.extend(parse_federal_register_json(text or "", source_name, now))
        elif source_type == "rss":
            candidates.extend(parse_rss(text or "", source_name, now))
        else:
            candidates.extend(parse_html(text or "", source_name, source_url, now))

    seen = load_seen()
    seen_map = seen.setdefault("seen", {})
    new_alerts: list[dict] = []
    for item in candidates:
        fp = item["fingerprint"]
        if fp in seen_map:
            continue
        new_alerts.append(item)
        seen_map[fp] = {
            "title": item.get("original_title") or item.get("title"),
            "source": item.get("source"),
            "link": item.get("link"),
            "first_seen_kst": now.isoformat(timespec="seconds"),
            "importance": item.get("importance"),
            "status": item.get("status"),
        }
        if len(new_alerts) >= MAX_ALERTS:
            break

    if not new_alerts:
        print(f"transformer_tariff_alerts=0 candidates={len(candidates)}")
        return 0

    existing = load_existing_alerts()
    existing_keys = {str(item.get("fingerprint") or item.get("link") or "") for item in existing}
    merged = existing[:]
    for item in new_alerts:
        key = str(item.get("fingerprint") or item.get("link") or "")
        if key not in existing_keys:
            merged.append(item)
            existing_keys.add(key)
    write_alerts(merged)
    save_seen(seen, now)
    print(f"transformer_tariff_alerts={len(new_alerts)} candidates={len(candidates)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
