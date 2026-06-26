#!/usr/bin/env python3
"""KHS White House agriculture / food-security policy watch."""

from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "out"
DATA_DIR = ROOT / "data"
SEEN_PATH = DATA_DIR / "khs_whitehouse_agriculture_seen.json"
ALERT_PATH = OUT_DIR / "khs_whitehouse_agriculture_alert.md"
TITLE_PATH = OUT_DIR / "khs_whitehouse_agriculture_title.txt"
ALERTS_JSON_PATH = OUT_DIR / "khs_whitehouse_agriculture_alerts.json"

MAX_AGE_HOURS = int(os.getenv("KHS_WHITEHOUSE_AGRI_MAX_AGE_HOURS", "72"))
FORMAT_VERSION = "whitehouse-agri-v1"

SOURCES = [
    ("백악관 행정명령", "https://www.whitehouse.gov/presidential-actions/executive-orders/", "/presidential-actions/"),
    ("백악관 팩트시트", "https://www.whitehouse.gov/fact-sheets/", "/fact-sheets/"),
]

LINK_PATTERN = re.compile(r"<a\b[^>]*href=[\"'](?P<href>[^\"']+)[\"'][^>]*>(?P<label>.*?)</a>", re.I | re.S)
DATE_PATTERN = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+20\d{2}\b",
    re.I,
)
ARTICLE_PATH_PATTERN = re.compile(r"/20\d{2}/\d{2}/[^/]+$", re.I)


def now_kst() -> dt.datetime:
    return dt.datetime.now(tz=KST)


def clean(value: str | None) -> str:
    value = re.sub(r"<script\b.*?</script>", " ", value or "", flags=re.I | re.S)
    value = re.sub(r"<style\b.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def fetch(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "KHS-whitehouse-agriculture-watch contact=github-actions"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode(resp.headers.get_content_charset() or "utf-8", errors="replace")


def parse_date(text: str) -> dt.datetime | None:
    match = DATE_PATTERN.search(text or "")
    if not match:
        return None
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return dt.datetime.strptime(match.group(0), fmt).replace(tzinfo=KST)
        except ValueError:
            pass
    return None


def is_article_link(link: str, source_url: str, required_path: str) -> bool:
    low = link.lower().rstrip("/")
    path = urllib.parse.urlparse(link).path.lower().rstrip("/")
    if low == source_url.lower().rstrip("/"):
        return False
    if "whitehouse.gov" not in low or required_path not in low:
        return False
    if "nominations-appointments" in path:
        return False
    return bool(ARTICLE_PATH_PATTERN.search(path))


def links_from(source_url: str, required_path: str) -> list[tuple[str, str]]:
    try:
        page = fetch(source_url)
    except Exception as exc:
        print(f"whitehouse_agri=source_failed url={source_url} error={type(exc).__name__}: {exc}")
        return []
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for match in LINK_PATTERN.finditer(page):
        title = clean(match.group("label"))
        link = urllib.parse.urljoin(source_url, html.unescape(match.group("href")))
        if link in seen or not is_article_link(link, source_url, required_path):
            continue
        seen.add(link)
        found.append((title, link))
        if len(found) >= 30:
            break
    return found


def read_article(title_hint: str, link: str) -> tuple[str, str, dt.datetime | None]:
    try:
        raw = fetch(link)
    except Exception as exc:
        print(f"whitehouse_agri=article_failed url={link} error={type(exc).__name__}: {exc}")
        return title_hint, "", None
    text = clean(raw)
    title = title_hint
    h1 = re.search(r"<h1[^>]*>(?P<title>.*?)</h1>", raw, re.I | re.S)
    if h1:
        title = clean(h1.group("title")) or title
    return title, text, parse_date(text)


def is_agriculture_policy(title: str, body: str, link: str) -> bool:
    haystack = f"{title} {body} {link}".lower()
    has_core = "regenerative agriculture" in haystack or "farm resilience" in haystack
    has_policy_actor = any(term in haystack for term in ("usda", "department of agriculture", "epa", "environmental protection agency", "hhs"))
    has_market_path = any(term in haystack for term in ("precision agriculture", "farm modernization", "crop protection", "pesticide", "food supply security", "regenerative pilot program"))
    return has_core and has_policy_actor and has_market_path


def load_seen() -> dict:
    if not SEEN_PATH.exists():
        return {"seen": {}, "updated_at_kst": ""}
    try:
        return json.loads(SEEN_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"seen": {}, "updated_at_kst": ""}


def fingerprint(link: str) -> str:
    raw = f"{FORMAT_VERSION}:{link}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def collect(now: dt.datetime) -> list[dict]:
    items: list[dict] = []
    seen_links: set[str] = set()
    for source_name, source_url, required_path in SOURCES:
        for title_hint, link in links_from(source_url, required_path):
            if link in seen_links:
                continue
            title, body, published = read_article(title_hint, link)
            if not published:
                continue
            published = published.astimezone(KST).replace(hour=0, minute=0, second=0, microsecond=0)
            if (now - published).total_seconds() / 3600 > MAX_AGE_HOURS:
                continue
            if not is_agriculture_policy(title, body, link):
                continue
            seen_links.add(link)
            items.append({
                "source": source_name,
                "title": title,
                "link": link,
                "published": published.isoformat(),
                "fingerprint": fingerprint(link),
            })
    return items


def render(items: list[dict], now: dt.datetime) -> str:
    sources = " / ".join(
        f"[{item['source']}]({item['link']}) · 원천시각 {item['published']}"
        for item in items[:3]
    )
    lines = [
        f"🚨 KHS 백악관 농업·식량안보 고충격 정책 워치 · {now:%Y년 %m월 %d일 %H:%M KST}",
        "백악관 농업·식량안보 정책 문서 1건 확인",
        "",
        "## 1. [상·확정] 백악관, 재생농업·농장 회복력 강화 행정명령 발표",
        "- 핵심: USDA·HHS·EPA 축으로 정밀농업, 재생농업, 농장 현대화, 식품공급망 안정, 작물보호 대체기술 평가를 정책 시간표로 공식화.",
        "- 영향: 농업/스마트팜, 농기계, 비료·농약/작물보호, 식품공급망 | 시간표·수급·마진",
        "- 투자 포인트: EPA 등록·라벨링 검토, USDA 재생농업 파일럿 확대, 공공·민간 파트너십이 농업 투입재와 정밀농업 테마 수급을 자극할 수 있음.",
        "- 반대 근거: 확정 매출이나 즉시 조달 공고는 아니며, 예산 배정·세부 프로그램·품목별 규제 변화 확인 전까지 직접 실적 연결은 제한적.",
        f"- 원문: {sources} · 조회 {now:%H:%M KST}",
        "",
        "💡 판단: 오늘 바뀐 것은 확정 매출보다 정책 시간표·테마 수급입니다. USDA/EPA 후속 공고, 농약·비료·정밀농업 밸류체인 반응 확인 필요.",
        "",
        "투자 조언이 아닌 참고용 정책·규제 알림입니다.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    now = now_kst()
    OUT_DIR.mkdir(exist_ok=True)
    DATA_DIR.mkdir(exist_ok=True)
    seen_payload = load_seen()
    seen = seen_payload.setdefault("seen", {})

    items = [item for item in collect(now) if item["fingerprint"] not in seen]
    if not items:
        for path in (ALERT_PATH, TITLE_PATH, ALERTS_JSON_PATH):
            if path.exists():
                path.unlink()
        print("whitehouse_agriculture_alerts=0")
        return 0

    report = render(items, now)
    ALERT_PATH.write_text(report, encoding="utf-8")
    TITLE_PATH.write_text("KHS 백악관 농업 정책 워치: [상] 재생농업·농장 회복력 강화 행정명령\n", encoding="utf-8")
    ALERTS_JSON_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for item in items:
        seen[item["fingerprint"]] = {
            "title": "백악관, 재생농업·농장 회복력 강화 행정명령 발표",
            "source": item["source"],
            "link": item["link"],
            "first_seen_kst": now.isoformat(timespec="seconds"),
            "importance": "상",
            "format": FORMAT_VERSION,
        }
    seen_payload["updated_at_kst"] = now.isoformat(timespec="seconds")
    SEEN_PATH.write_text(json.dumps(seen_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"whitehouse_agriculture_alerts={len(items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())