from __future__ import annotations

import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

try:
    from googlenewsdecoder import gnewsdecoder
except Exception:  # pragma: no cover
    gnewsdecoder = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "rubin_hbm_watch_state.json"
PENDING_PATH = ROOT / "out" / "rubin_hbm_pending_state.json"
ALERT_PATH = ROOT / "out" / "rubin_hbm_alert.md"

UA = "Mozilla/5.0 (compatible; khs-watch/2.0; +https://github.com/qedgwangju-dot/khs-watch)"
BASELINE_DATE = "2026-09-15"
BASELINE = {
    "as_of": BASELINE_DATE,
    "source": "TrendForce 공식 X 사용자 제공 캡처",
    "components": {
        "GPU": {"status": "Balanced", "current": "20-30", "balanced": "20-30"},
        "DRAM": {"status": "Very Tight", "current": "20", "balanced": "8"},
        "NAND(eSSD)": {"status": "Tight", "current": "16", "balanced": "8"},
        "HDD": {"status": "Very Tight", "current": "50", "balanced": "16"},
        "ABF": {"status": "Very Tight", "current": "48-56", "balanced": "12"},
        "MLCC": {"status": "Tight", "current": "30", "balanced": "12"},
    },
    "seen_urls": [],
}

SEARCHES = [
    (
        "google_news",
        'TrendForce ("lead time" OR "lead times") (ABF OR MLCC OR HDD OR DRAM OR NAND OR GPU) "AI infrastructure"',
    ),
    (
        "bing_web",
        'site:x.com/trendforce "lead time" "AI infrastructure" ABF MLCC',
    ),
    (
        "bing_web",
        'site:trendforce.com TrendForce "lead time" ABF DRAM NAND HDD MLCC GPU',
    ),
    (
        "bing_web",
        '"current vs balanced lead times" TrendForce',
    ),
]

ALIASES = {
    "GPU": ("GPU",),
    "DRAM": ("DRAM",),
    "NAND(eSSD)": ("NAND", "eSSD", "enterprise SSD"),
    "HDD": ("HDD", "hard disk"),
    "ABF": ("ABF", "ABF substrate", "ABF substrates"),
    "MLCC": ("MLCC", "MLCCs"),
}

STATUS_KO = {
    "Very Tight": "심각한 부족",
    "Tight": "공급 제약",
    "Balanced": "수급 균형",
}


def fetch(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<(script|style|svg|noscript)[^>]*>.*?</\1>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def parse_pubdate(value: str) -> datetime | None:
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo("Asia/Seoul"))
    except Exception:
        return None


def google_news_url(query: str) -> str:
    q = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def bing_rss_url(query: str) -> str:
    q = urllib.parse.quote(query)
    return f"https://www.bing.com/search?format=rss&q={q}"


def read_rss(kind: str, query: str) -> list[dict]:
    url = google_news_url(query) if kind == "google_news" else bing_rss_url(query)
    root = ET.fromstring(fetch(url))
    out: list[dict] = []
    for item in root.findall("./channel/item"):
        title = clean_text(item.findtext("title") or "")
        link = clean_text(item.findtext("link") or "")
        desc = clean_text(item.findtext("description") or "")
        pub = clean_text(item.findtext("pubDate") or "")
        dt = parse_pubdate(pub)
        if title and link:
            out.append({
                "kind": kind,
                "title": title,
                "link": link,
                "description": desc,
                "published_at_kst": dt.isoformat(timespec="seconds") if dt else "",
            })
    return out


def decode_google_news(link: str) -> str:
    if "news.google.com" not in (link or ""):
        return link
    if gnewsdecoder is None:
        return ""
    try:
        result = gnewsdecoder(link, interval=0.2)
        if isinstance(result, dict) and result.get("status"):
            decoded = str(result.get("decoded_url") or "").strip()
            if decoded.startswith("http") and "news.google.com" not in decoded:
                return decoded
    except Exception:
        pass
    return ""


def candidate_url(item: dict) -> str:
    if item.get("kind") == "google_news":
        return decode_google_news(item.get("link") or "")
    return item.get("link") or ""


def is_trendforce_source(url: str, text: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    low = text.lower()
    return (
        "trendforce.com" in host
        or (host.endswith("x.com") and "/trendforce" in url.lower())
        or "trendforce" in low
    )


def is_relevant(text: str) -> bool:
    low = text.lower()
    component_hits = sum(1 for aliases in ALIASES.values() if any(a.lower() in low for a in aliases))
    lead_hit = any(k in low for k in ("lead time", "lead times", "balanced lead", "current lead", "리드타임", "납기"))
    weekly_phrase = "six ai infrastructure components" in low or "current vs balanced" in low
    return lead_hit and (component_hits >= 2 or weekly_phrase)


def article_text(url: str) -> str:
    if not url:
        return ""
    host = (urlparse(url).hostname or "").lower()
    # X 본문은 서버 측 직접 열람이 자주 차단되므로 검색 색인 문구를 보존하고 실패를 허용한다.
    if host.endswith("x.com"):
        return ""
    try:
        raw = fetch(url, timeout=18).decode("utf-8", errors="ignore")
        return clean_text(raw)[:24000]
    except Exception:
        return ""


def week_tokens(chunk: str) -> list[str]:
    vals: list[str] = []
    # 48–56 weeks, 20-30W, 20 weeks 등을 모두 지원한다.
    for m in re.finditer(r"(?<!\d)(\d{1,2})(?:\s*[-–—~]\s*(\d{1,2}))?\s*(?:weeks?|w)\b", chunk, re.I):
        a, b = m.group(1), m.group(2)
        token = f"{a}-{b}" if b else a
        if token not in vals:
            vals.append(token)
    return vals


def status_from(chunk: str) -> str:
    low = chunk.lower()
    if "very tight" in low or "severe shortage" in low:
        return "Very Tight"
    if re.search(r"\btight\b", low) or "constrained supply" in low:
        return "Tight"
    if "balanced" in low:
        return "Balanced"
    return ""


def extract_components(text: str) -> dict:
    result: dict[str, dict] = {}
    normalized = text.replace("48–56", "48-56")
    for name, aliases in ALIASES.items():
        best_chunk = ""
        for alias in aliases:
            for m in re.finditer(re.escape(alias), normalized, re.I):
                start = max(0, m.start() - 40)
                end = min(len(normalized), m.end() + 220)
                chunk = normalized[start:end]
                if len(week_tokens(chunk)) > len(week_tokens(best_chunk)):
                    best_chunk = chunk
        if not best_chunk:
            continue
        weeks = week_tokens(best_chunk)
        if not weeks:
            continue
        entry = {"status": status_from(best_chunk), "current": weeks[0], "balanced": ""}
        if len(weeks) >= 2:
            entry["balanced"] = weeks[1]
        result[name] = entry
    return result


def canonical_component(entry: dict) -> tuple[str, str, str]:
    return (
        str(entry.get("status") or ""),
        str(entry.get("current") or ""),
        str(entry.get("balanced") or ""),
    )


def changed_components(old: dict, new: dict) -> list[str]:
    changed = []
    for name, new_entry in new.items():
        old_entry = old.get(name) or {}
        if canonical_component(old_entry) != canonical_component(new_entry):
            changed.append(name)
    return changed


def ratio_value(current: str, balanced: str) -> float | None:
    def midpoint(value: str) -> float | None:
        nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", value or "")]
        if not nums:
            return None
        return sum(nums) / len(nums)

    c = midpoint(current)
    b = midpoint(balanced)
    if c is None or b in (None, 0):
        return None
    return c / b


def source_score(url: str, components: dict, text: str) -> int:
    host = (urlparse(url).hostname or "").lower()
    score = len(components) * 10
    if "trendforce.com" in host:
        score += 40
    if host.endswith("x.com") and "/trendforce" in url.lower():
        score += 35
    if "current vs balanced" in text.lower():
        score += 20
    return score


def load_json(path: pathlib.Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: pathlib.Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fmt_entry(entry: dict) -> str:
    status = str(entry.get("status") or "")
    current = str(entry.get("current") or "확인 불가")
    balanced = str(entry.get("balanced") or "확인 불가")
    status_ko = STATUS_KO.get(status, status or "상태 미확인")
    return f"{current}주 / 균형 {balanced}주 / {status_ko}"


def build_alert(old: dict, new: dict, changed: list[str], source_url: str, published: str, signal_only: bool) -> str:
    lines = [
        "<b>🚨 AI 인프라 부품 납기 변화</b>",
        "",
        "<b>무엇이 달라졌나</b>",
    ]
    if signal_only:
        lines.append("• TrendForce의 새 AI 인프라 리드타임 업데이트를 감지했습니다.")
        lines.append("• 검색 색인에서 표 전체 수치가 확보되지 않아 숫자는 임의 추정하지 않습니다.")
    else:
        for name in changed:
            before = fmt_entry(old.get(name) or {})
            after = fmt_entry(new.get(name) or {})
            lines.append(f"• {html.escape(name)}: {html.escape(before)} → {html.escape(after)}")

    complete = new or old
    ranked = []
    for name, entry in complete.items():
        ratio = ratio_value(str(entry.get("current") or ""), str(entry.get("balanced") or ""))
        if ratio is not None:
            ranked.append((ratio, name, entry))
    ranked.sort(reverse=True)

    lines += ["", "<b>현재 판정</b>"]
    if ranked:
        ratio, name, entry = ranked[0]
        lines.append(f"• 가장 강한 병목: {html.escape(name)} — {html.escape(fmt_entry(entry))}, 균형 대비 약 {ratio:.1f}배")
    else:
        lines.append("• 새 업데이트 자체는 확인했지만 표 수치 자동 추출은 불완전합니다.")

    lines += [
        "",
        "<b>투자 의미</b>",
        "• GPU 자체보다 ABF 패키지기판·DRAM·기업용 SSD·HDD·MLCC의 납기 변화가 AI 서버 실제 출하 시점을 좌우하는지 확인합니다.",
        "• 납기 단축은 증설 효과일 수도 있고 수요 둔화일 수도 있으므로, 가격·신규수주·주문출하비율과 함께 판정합니다.",
    ]
    if published:
        lines.append(f"• 공개시각: {html.escape(published)}")
    if source_url:
        safe_url = html.escape(source_url, quote=True)
        lines.append(f'• <a href="{safe_url}">원문</a>')
    return "\n".join(lines).strip() + "\n"


def main() -> None:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    state = load_json(STATE_PATH)
    pending = load_json(PENDING_PATH)
    previous = state.get("ai_component_leadtime") or BASELINE
    previous_components = previous.get("components") or BASELINE["components"]
    seen_urls = set(previous.get("seen_urls") or [])

    candidates: list[dict] = []
    errors: list[str] = []
    cutoff = now - timedelta(days=21)

    for kind, query in SEARCHES:
        try:
            items = read_rss(kind, query)
        except Exception as exc:
            errors.append(f"{kind}: {type(exc).__name__}: {exc}")
            continue
        for item in items:
            direct = candidate_url(item)
            if not direct:
                continue
            base_text = f"{item.get('title','')} {item.get('description','')}"
            if not is_trendforce_source(direct, base_text):
                continue
            dt = None
            if item.get("published_at_kst"):
                try:
                    dt = datetime.fromisoformat(item["published_at_kst"])
                except Exception:
                    pass
            if dt is not None and dt < cutoff:
                continue
            body = article_text(direct)
            full_text = clean_text(f"{base_text} {body}")
            if not is_relevant(full_text):
                continue
            components = extract_components(full_text)
            candidates.append({
                **item,
                "direct_url": direct,
                "full_text": full_text,
                "components": components,
                "score": source_score(direct, components, full_text),
            })

    candidates.sort(key=lambda x: (x.get("score", 0), x.get("published_at_kst") or ""), reverse=True)
    best = candidates[0] if candidates else None

    latest_components = dict(previous_components)
    latest_source = previous.get("source") or BASELINE["source"]
    latest_as_of = previous.get("as_of") or BASELINE_DATE
    notify_text = ""
    new_seen = set(seen_urls)

    if best:
        url = best.get("direct_url") or ""
        published = best.get("published_at_kst") or ""
        if url:
            new_seen.add(url)
        extracted = best.get("components") or {}
        # 부분 표가 잡혀도 이전 스냅샷의 미확인 품목을 지우지 않고 덮어쓴다.
        merged = dict(previous_components)
        for name, entry in extracted.items():
            old_entry = dict(merged.get(name) or {})
            for key in ("status", "current", "balanced"):
                if entry.get(key):
                    old_entry[key] = entry[key]
            merged[name] = old_entry

        changed = changed_components(previous_components, merged)
        published_date = published[:10] if published else ""
        is_after_baseline = bool(published_date and published_date > BASELINE_DATE)
        is_new_url = bool(url and url not in seen_urls)
        exact_weekly_signal = (
            "current vs balanced" in (best.get("full_text") or "").lower()
            or "six ai infrastructure components" in (best.get("full_text") or "").lower()
        )

        if changed:
            notify_text = build_alert(previous_components, merged, changed, url, published, signal_only=False)
            latest_components = merged
            latest_source = url or latest_source
            latest_as_of = published_date or now.date().isoformat()
        elif is_new_url and is_after_baseline and exact_weekly_signal:
            # 표가 이미지로만 있어 자동 숫자 추출이 안 되더라도 새 주간 업데이트 자체는 알린다.
            notify_text = build_alert(previous_components, merged, [], url, published, signal_only=True)
            latest_source = url or latest_source
            latest_as_of = published_date or now.date().isoformat()

    pending["ai_component_leadtime"] = {
        "as_of": latest_as_of,
        "source": latest_source,
        "components": latest_components,
        "seen_urls": sorted(new_seen)[-120:],
        "last_checked_at_kst": now.isoformat(timespec="seconds"),
        "candidate_count": len(candidates),
        "errors": errors[-10:],
    }
    write_json(PENDING_PATH, pending)

    if notify_text:
        existing = ""
        if ALERT_PATH.exists():
            existing = ALERT_PATH.read_text(encoding="utf-8").strip()
        merged_alert = (existing + "\n\n" + notify_text.strip()).strip() if existing else notify_text.strip()
        ALERT_PATH.write_text(merged_alert + "\n", encoding="utf-8")

    print(
        "ai_component_leadtime_watch=true "
        f"candidates={len(candidates)} notify={str(bool(notify_text)).lower()} "
        f"source={best.get('direct_url') if best else 'none'}"
    )


if __name__ == "__main__":
    main()
