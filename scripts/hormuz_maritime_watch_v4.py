from __future__ import annotations

import datetime as dt
import email.utils
import hashlib
import html
import io
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from zoneinfo import ZoneInfo

from pypdf import PdfReader

STATE_PATH = Path("data/hormuz_maritime_watch_state.json")
OUT_DIR = Path("out")
OUT_ALERT = OUT_DIR / "hormuz_maritime_watch_telegram.txt"
OUT_STATUS = OUT_DIR / "hormuz_maritime_watch_status.md"
OUT_PENDING = OUT_DIR / "hormuz_maritime_watch_pending_state.json"
OUT_DEBUG = OUT_DIR / "hormuz_maritime_watch_debug.json"
KST = ZoneInfo("Asia/Seoul")
UTC = dt.timezone.utc
STATE_VERSION = 4
BASELINE_WARNING = 124
UA = "Mozilla/5.0 KHS-Hormuz-Maritime-Watch/4.0"
TIMEOUT = 10
MAX_BODY = 7_000_000
MAX_NEWS_AGE_HOURS = 72
CLUSTER_WINDOW_HOURS = 8

UKMTO_WARNINGS_PAGE = "https://www.ukmto.org/ukmto-products/warnings"
SEED_URLS = {
    "124-26": "https://www.ukmto.org/-/media/ukmto/products/20260831-ukmto_warning_124-26.pdf?rev=15628245e24f4431b04b8badc4036ed7",
}
NEWS_QUERIES = (
    '"UKMTO" "Strait of Hormuz" tanker when:3d',
    '"UK maritime agency" tanker Hormuz when:3d',
    '"unknown projectile" tanker Khasab when:3d',
    '"3 projectiles" tanker Khasab when:3d',
    'tanker struck "Strait of Hormuz" when:3d',
    'tanker attack Hormuz UKMTO when:3d',
)

PRIMARY_SOURCES = {"Reuters", "Associated Press", "AP News"}
STRONG_SOURCES = PRIMARY_SOURCES | {
    "Radio Free Europe/Radio Liberty", "RFE/RL", "Anadolu Ajansı", "Anadolu Agency",
}
SPECIALIST_SOURCES = {
    "The Maritime Executive", "Lloyd’s List", "Lloyd's List", "TradeWinds", "Seavanta",
    "Gulf News", "Arab News", "Oman News Agency", "U.S. Central Command", "CENTCOM",
}
TRUSTED_SOURCES = STRONG_SOURCES | SPECIALIST_SOURCES

GEO_TERMS = ("hormuz", "khasab", "fujairah", "oman", "gulf of oman", "arabian gulf", "larak")
VESSEL_TERMS = ("tanker", "vessel", "ship", "vlcc", "merchant")
SECURITY_TERMS = (
    "projectile", "attack", "struck", "hit", "explosion", "fire", "mine", "missile", "drone",
    "seized", "seizure", "boarding", "stopped", "blocked", "blockade", "closure", "security incident",
)


def now_kst() -> dt.datetime:
    return dt.datetime.now(KST)


def fetch(url: str, accept: str = "*/*") -> tuple[bytes, str, str]:
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        body = response.read(MAX_BODY + 1)
        if len(body) > MAX_BODY:
            raise RuntimeError("response too large")
        return body, str(response.headers.get("Content-Type") or "").lower(), response.geturl()


def clean(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<script\b[^>]*>.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style\b[^>]*>.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def lowered(value: str) -> str:
    return clean(value).lower()


def relevant(value: str) -> bool:
    text = lowered(value)
    return any(term in text for term in GEO_TERMS) and any(term in text for term in VESSEL_TERMS) and any(term in text for term in SECURITY_TERMS)


def warning_no(value: str) -> str | None:
    for pattern in (
        r"\b(?:warning|ukmto)\s*[-:#]?\s*(\d{2,3})\s*[-_/]\s*26\b",
        r"\bukmto\s+#?(\d{2,3})\b",
    ):
        match = re.search(pattern, value, flags=re.I)
        if match:
            return f"{int(match.group(1)):03d}-26"
    return None


def warning_int(value: str | None) -> int:
    match = re.match(r"^(\d{2,3})-26$", value or "")
    return int(match.group(1)) if match else 0


def digest(value: str) -> str:
    return hashlib.sha256(lowered(value).encode("utf-8")).hexdigest()[:18]


def pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        return clean(" ".join((page.extract_text() or "") for page in reader.pages[:8]))
    except Exception:
        return ""


def fetch_source(url: str) -> tuple[str, str]:
    body, ctype, final_url = fetch(url)
    if body.startswith(b"%PDF") or "pdf" in ctype or final_url.lower().split("?")[0].endswith(".pdf"):
        return pdf_text(body), final_url
    return clean(body.decode("utf-8", errors="replace")), final_url


def candidate_urls(number: int) -> list[str]:
    yy = str(now_kst().year)[-2:]
    urls: list[str] = []
    for delta in (0, 1):
        stamp = (now_kst().date() - dt.timedelta(days=delta)).strftime("%Y%m%d")
        urls.extend((
            f"https://www.ukmto.org/-/media/ukmto/products/{stamp}-ukmto_warning_{number:03d}-{yy}.pdf",
            f"https://www.ukmto.org/-/media/ukmto/products/{stamp}-ukmto_warning_attack_{number:03d}_{yy}.pdf",
        ))
    return urls


def official_scan(highest: int) -> tuple[list[dict], int, list[str], bool]:
    rows: dict[str, dict] = {}
    errors: list[str] = []
    max_seen = highest
    page_ok = False
    try:
        page_text, _ = fetch_source(UKMTO_WARNINGS_PAGE)
        page_ok = "UKMTO" in page_text and "Warnings" in page_text
    except Exception as exc:
        errors.append(f"UKMTO warnings page: {type(exc).__name__}: {exc}")

    for expected, url in SEED_URLS.items():
        try:
            text, final_url = fetch_source(url)
            no = warning_no(text)
            if no == expected and "ukmto" in lowered(text):
                key = f"ukmto:{no}:{digest(text)}"
                rows[key] = {"key": key, "warning": no, "url": final_url, "text": text, "relevant": relevant(text), "lane": "official-direct"}
        except Exception:
            pass

    start = max(BASELINE_WARNING + 1, highest + 1)
    for number in range(start, start + 4):
        for url in candidate_urls(number):
            try:
                text, final_url = fetch_source(url)
            except Exception:
                continue
            no = warning_no(text)
            if no and warning_int(no) == number and "ukmto" in lowered(text):
                key = f"ukmto:{no}:{digest(text)}"
                rows[key] = {"key": key, "warning": no, "url": final_url, "text": text, "relevant": relevant(text), "lane": "official-direct"}
                max_seen = max(max_seen, number)
                break
    return list(rows.values()), max_seen, errors, page_ok


def google_news(query: str) -> list[dict]:
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    body, _, _ = fetch(url, "application/rss+xml,application/xml,text/xml,*/*")
    root = ET.fromstring(body)
    rows = []
    for item in root.findall(".//item"):
        source = ""
        for child in list(item):
            if child.tag.endswith("source"):
                source = clean(child.text or "")
                break
        published_raw = clean(item.findtext("pubDate") or "")
        try:
            published = email.utils.parsedate_to_datetime(published_raw)
            if published.tzinfo is None:
                published = published.replace(tzinfo=UTC)
            published = published.astimezone(UTC)
        except Exception:
            continue
        rows.append({
            "title": clean(item.findtext("title") or ""),
            "url": (item.findtext("link") or "").strip(),
            "description": clean(item.findtext("description") or ""),
            "source": source,
            "published_utc": published.isoformat().replace("+00:00", "Z"),
            "published_epoch": published.timestamp(),
        })
    return rows


def classify_event(value: str) -> str | None:
    text = lowered(value)
    if any(term in text for term in ("projectile", "struck", " hit ", "missile", "drone", "attack")):
        return "strike"
    if "mine" in text:
        return "mine"
    if any(term in text for term in ("seized", "seizure", "boarding")):
        return "seizure"
    if any(term in text for term in ("explosion", "fire")):
        return "explosion"
    if any(term in text for term in ("stopped", "blocked", "blockade", "closure")):
        return "restriction"
    return None


def projectile_count(value: str) -> int | None:
    text = lowered(value)
    match = re.search(r"\b(\d+)\s+(?:unknown\s+|unidentified\s+)?projectiles?\b", text)
    if match:
        return int(match.group(1))
    if re.search(r"\b(?:unknown|unidentified) projectile\b", text) and "projectiles" not in text:
        return 1
    return None


def location_bucket(value: str) -> str:
    text = lowered(value)
    if "khasab" in text:
        return "khasab"
    if "fujairah" in text:
        return "fujairah"
    if "gulf of oman" in text:
        return "gulf-of-oman"
    if "hormuz" in text:
        return "hormuz"
    if "oman" in text:
        return "oman"
    return "regional"


def news_scan() -> tuple[list[dict], list[str], list[dict]]:
    cutoff = dt.datetime.now(UTC).timestamp() - MAX_NEWS_AGE_HOURS * 3600
    selected: dict[str, dict] = {}
    samples: list[dict] = []
    errors: list[str] = []
    for query in NEWS_QUERIES:
        try:
            items = google_news(query)
            samples.extend(items[:2])
            for item in items:
                if item["published_epoch"] < cutoff or item["source"] not in TRUSTED_SOURCES:
                    continue
                text = item["title"] + " " + item["description"]
                if not relevant(text):
                    continue
                kind = classify_event(text)
                if not kind:
                    continue
                key = hashlib.sha256((item["source"] + "|" + item["title"] + "|" + item["url"]).encode("utf-8")).hexdigest()[:20]
                selected[key] = {
                    **item,
                    "key": key,
                    "warning": warning_no(text),
                    "event_kind": kind,
                    "projectile_count": projectile_count(text),
                    "location": location_bucket(text),
                    "mentions_authority": any(term in lowered(text) for term in ("ukmto", "uk maritime agency", "uk maritime", "centcom", "u.s. central command")),
                }
        except Exception as exc:
            errors.append(f"news {query!r}: {type(exc).__name__}: {exc}")
    return list(selected.values()), errors, samples[:15]


def source_confidence(items: list[dict]) -> bool:
    sources = {item.get("source") for item in items if item.get("source")}
    strong = sources & STRONG_SOURCES
    primary = sources & PRIMARY_SOURCES
    specialists = sources & SPECIALIST_SOURCES
    authority_mention = any(item.get("mentions_authority") for item in items)
    if not authority_mention:
        return False
    if len(sources) >= 2 and primary and (len(strong) >= 2 or specialists):
        return True
    if len(strong) >= 2:
        return True
    return len(sources) >= 3 and bool(strong or primary)


def compatible(a: dict, b: dict) -> bool:
    if a.get("event_kind") != b.get("event_kind"):
        return False
    if a.get("location") != b.get("location"):
        if {a.get("location"), b.get("location")} != {"khasab", "hormuz"}:
            return False
    count_a, count_b = a.get("projectile_count"), b.get("projectile_count")
    if count_a is not None and count_b is not None and count_a != count_b:
        return False
    warning_a, warning_b = a.get("warning"), b.get("warning")
    if warning_a and warning_b and warning_a != warning_b:
        return False
    return True


def build_confirmed_clusters(news: list[dict]) -> list[dict]:
    ordered = sorted(news, key=lambda row: row.get("published_epoch", 0))
    clusters: dict[str, dict] = {}
    window = CLUSTER_WINDOW_HOURS * 3600
    for anchor in ordered:
        rows = [row for row in ordered if 0 <= row.get("published_epoch", 0) - anchor.get("published_epoch", 0) <= window and compatible(anchor, row)]
        unique_by_source: dict[str, dict] = {}
        for row in rows:
            unique_by_source.setdefault(row.get("source", ""), row)
        rows = list(unique_by_source.values())
        if not source_confidence(rows):
            continue
        warnings = [row.get("warning") for row in rows if row.get("warning")]
        warning = max(warnings, key=warning_int) if warnings else None
        counts = [row.get("projectile_count") for row in rows if row.get("projectile_count") is not None]
        count = max(set(counts), key=counts.count) if counts else None
        location = "khasab" if any(row.get("location") == "khasab" for row in rows) else anchor.get("location")
        day = dt.datetime.fromtimestamp(anchor["published_epoch"], UTC).strftime("%Y-%m-%d")
        event_key = f"warning:{warning}" if warning else f"news:{day}:{anchor.get('event_kind')}:{location}:{count if count is not None else 'x'}"
        candidate = {
            "event_key": event_key,
            "warning": warning,
            "event_kind": anchor.get("event_kind"),
            "location": location,
            "projectile_count": count,
            "first_epoch": min(row["published_epoch"] for row in rows),
            "last_epoch": max(row["published_epoch"] for row in rows),
            "sources": sorted(rows, key=lambda row: (0 if row.get("source") in PRIMARY_SOURCES else 1, -row.get("published_epoch", 0))),
        }
        old = clusters.get(event_key)
        if old is None or len(candidate["sources"]) > len(old["sources"]):
            clusters[event_key] = candidate
    return list(clusters.values())


def load_state() -> tuple[dict, bool]:
    default = {
        "version": STATE_VERSION, "initialized": False, "official": {}, "news": {}, "confirmed_events": {},
        "highest_warning_seen": BASELINE_WARNING, "last_checked_kst": None,
    }
    if not STATE_PATH.exists():
        return default, True
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return default, True
    migrating = int(state.get("version") or 0) < STATE_VERSION
    state.setdefault("official", {})
    state.setdefault("news", {})
    state.setdefault("confirmed_events", {})
    state.setdefault("highest_warning_seen", BASELINE_WARNING)
    state.setdefault("initialized", False)
    state.setdefault("last_checked_kst", None)
    return state, migrating


def official_evidence(text: str) -> list[str]:
    text = clean(text)
    rows: list[str] = []
    match = re.search(r"(\d+(?:\.\d+)?\s*NM\s+[^.]{3,110})", text, flags=re.I)
    if match:
        rows.append("위치: " + match.group(1).strip())
    elif "Strait of Hormuz" in text:
        rows.append("위치: Strait of Hormuz")
    match = re.search(r"((?:tanker|vessel|ship|VLCC)[^.]{0,230}(?:struck|hit|attack(?:ed)?|projectile|mine|fire|explosion)[^.]{0,230})", text, flags=re.I)
    if match:
        sentence = clean(match.group(1))[:390]
        sentence = re.sub(r"\b(?:unknown|unidentified) projectiles?\b", "미상 발사체", sentence, flags=re.I)
        rows.append("사건: " + sentence)
    low_text = text.lower()
    if "crew are reported safe" in low_text or "crew are safe" in low_text:
        rows.append("인명: UKMTO 원문상 crew safe")
    if "no environmental impact" in low_text or "no reported environmental impact" in low_text:
        rows.append("환경: 보고된 오염 없음")
    return rows[:4]


def build_official_alert(item: dict, news: list[dict], update: bool) -> str:
    lines = [
        "[호르무즈 해상보안 공식 업데이트]" if update else "[호르무즈 해상보안 공식 신규 경보]",
        f"UKMTO: {item.get('warning')}",
        f"확인시각: {now_kst().strftime('%Y-%m-%d %H:%M KST')}",
    ]
    lines.extend(official_evidence(item.get("text", "")))
    lines.append("무기/공격주체: UKMTO가 특정하지 않은 내용은 추정하지 않음")
    lines.append("원문: " + item.get("url", ""))
    related = [row for row in news if row.get("warning") == item.get("warning")][:3]
    if related:
        lines.append("교차검증:")
        for row in related:
            lines.append(f"- {row.get('source')}: {row.get('title')} | {row.get('url')}")
    lines.append("표기 원칙: unknown/unidentified projectile = 미상 발사체. 포탄·미사일·드론으로 임의 단정하지 않음.")
    return "\n".join(lines) + "\n"


def build_cluster_alert(cluster: dict) -> str:
    kind_labels = {
        "strike": "유조선/상선 피격·공격", "mine": "기뢰 관련 사건", "seizure": "나포·승선 사건",
        "explosion": "폭발·화재 사건", "restriction": "강제정지·통항 제한",
    }
    sources = cluster.get("sources", [])
    lines = [
        "[호르무즈 해상보안 교차검증 경보]",
        f"사건: {kind_labels.get(cluster.get('event_kind'), cluster.get('event_kind'))}",
        f"위치: {cluster.get('location')}",
        f"확인시각: {now_kst().strftime('%Y-%m-%d %H:%M KST')}",
    ]
    if cluster.get("warning"):
        lines.append(f"UKMTO 경보번호 보도상 확인: {cluster.get('warning')}")
    if cluster.get("projectile_count") is not None:
        lines.append(f"발사체 수: {cluster.get('projectile_count')}발(복수 독립 보도 일치 범위)")
    lines.append(f"검증 수준: 독립 신뢰출처 {len(sources)}곳 교차 일치")
    lines.append("직접 UKMTO PDF가 GitHub 러너에서 동적/접근 구조로 미탐지될 때만 사용하는 보조 확정 경로")
    for row in sources[:4]:
        lines.append(f"- {row.get('source')} · {row.get('published_utc')} · {row.get('title')} | {row.get('url')}")
    lines.append("주의: unknown/unidentified projectile는 '미상 발사체'로 유지하며 공격주체·미사일/포탄/드론은 공식 확인 전 단정하지 않음.")
    return "\n".join(lines) + "\n"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    state, migrating = load_state()
    initialized = bool(state.get("initialized"))
    highest = max(BASELINE_WARNING, int(state.get("highest_warning_seen") or BASELINE_WARNING))

    official, max_seen, official_errors, official_page_ok = official_scan(highest)
    news, news_errors, news_samples = news_scan()
    clusters = build_confirmed_clusters(news)

    old_official = dict(state.get("official") or {})
    old_news = dict(state.get("news") or {})
    old_events = dict(state.get("confirmed_events") or {})

    alerts: list[str] = []
    for item in official:
        if item["key"] in old_official or not item.get("relevant"):
            continue
        same_warning_seen = any(row.get("warning") == item.get("warning") for row in old_official.values())
        if initialized and not migrating:
            alerts.append(build_official_alert(item, news, same_warning_seen))

    for cluster in clusters:
        if cluster["event_key"] in old_events:
            continue
        if initialized and not migrating:
            alerts.append(build_cluster_alert(cluster))

    pending = {
        "version": STATE_VERSION, "initialized": True, "official": old_official, "news": old_news,
        "confirmed_events": old_events, "highest_warning_seen": max_seen,
        "last_checked_kst": now_kst().isoformat(timespec="seconds"),
    }
    for item in official:
        pending["official"][item["key"]] = {
            "warning": item.get("warning"), "url": item.get("url"), "relevant": item.get("relevant"),
            "first_seen_kst": old_official.get(item["key"], {}).get("first_seen_kst") or now_kst().isoformat(timespec="seconds"),
        }
    for item in news:
        pending["news"][item["key"]] = {
            "source": item.get("source"), "title": item.get("title"), "url": item.get("url"),
            "published_utc": item.get("published_utc"),
            "first_seen_kst": old_news.get(item["key"], {}).get("first_seen_kst") or now_kst().isoformat(timespec="seconds"),
        }
    for cluster in clusters:
        pending["confirmed_events"][cluster["event_key"]] = {
            "warning": cluster.get("warning"), "event_kind": cluster.get("event_kind"), "location": cluster.get("location"),
            "projectile_count": cluster.get("projectile_count"), "sources": [row.get("source") for row in cluster.get("sources", [])],
            "first_seen_kst": old_events.get(cluster["event_key"], {}).get("first_seen_kst") or now_kst().isoformat(timespec="seconds"),
        }
    for field, limit in (("official", 300), ("news", 800), ("confirmed_events", 300)):
        if len(pending[field]) > limit:
            pending[field] = dict(list(pending[field].items())[-limit:])
    OUT_PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if alerts:
        OUT_ALERT.write_text("\n\n".join(alerts).strip() + "\n", encoding="utf-8")
    elif OUT_ALERT.exists():
        OUT_ALERT.unlink()

    errors = official_errors + news_errors
    status = [
        "# Hormuz maritime watch",
        f"- checked: {now_kst().strftime('%Y-%m-%d %H:%M:%S KST')}",
        f"- state_version: {STATE_VERSION}",
        f"- migration_baseline: {migrating}",
        f"- ukmto_warnings_page_reachable: {official_page_ok}",
        f"- direct_official_items: {len(official)}",
        f"- trusted_news_items: {len(news)}",
        f"- cross_verified_clusters: {len(clusters)}",
        f"- new_alerts: {len(alerts)}",
        "- trigger A: 직접 UKMTO 원문 탐지.",
        "- trigger B: UKMTO/해사당국 언급 + 독립 신뢰출처 2곳 이상(또는 강한 출처 조합)의 8시간 내 사건 일치.",
        "- fidelity: unknown/unidentified projectile remains 미상 발사체; attacker and weapon type are not inferred.",
    ]
    if errors:
        status.append("- partial errors:")
        status.extend("  - " + error[:500] for error in errors[:8])
    OUT_STATUS.write_text("\n".join(status) + "\n", encoding="utf-8")
    OUT_DEBUG.write_text(json.dumps({"official": official, "news": news, "clusters": clusters, "errors": errors, "news_samples": news_samples}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"hormuz_watch_v4 migrating={migrating} page_ok={official_page_ok} direct={len(official)} news={len(news)} clusters={len(clusters)} alerts={len(alerts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
