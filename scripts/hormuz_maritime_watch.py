from __future__ import annotations

import datetime as dt
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
STATE_VERSION = 3
BASELINE_WARNING = 124
UA = "Mozilla/5.0 KHS-Hormuz-Maritime-Watch/3.0"
TIMEOUT = 12
MAX_BODY = 7_000_000

SEED_URLS = {
    "124-26": "https://www.ukmto.org/-/media/ukmto/products/20260831-ukmto_warning_124-26.pdf?rev=15628245e24f4431b04b8badc4036ed7",
}

NEWS_QUERIES = (
    '"Strait of Hormuz" tanker when:7d',
    'UKMTO tanker Hormuz when:7d',
    'Khasab tanker projectile when:7d',
)
TRUSTED = {
    "Reuters", "Associated Press", "AP News", "U.S. Central Command", "CENTCOM",
    "The Maritime Executive", "Lloyd’s List", "Lloyd's List", "TradeWinds", "Oman News Agency",
}
GEO = ("hormuz", "khasab", "fujairah", "oman", "gulf of oman", "arabian gulf", "larak")
VESSEL = ("tanker", "vessel", "ship", "vlcc", "merchant")
RISK = (
    "projectile", "attack", "struck", "hit", "explosion", "mine", "missile", "drone",
    "seized", "boarding", "stopped", "blockade", "closure", "closed", "security incident",
)


def now() -> dt.datetime:
    return dt.datetime.now(KST)


def fetch(url: str, accept: str = "*/*") -> tuple[bytes, str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        body = r.read(MAX_BODY + 1)
        if len(body) > MAX_BODY:
            raise RuntimeError("response too large")
        return body, str(r.headers.get("Content-Type") or "").lower(), r.geturl()


def clean(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<script\b[^>]*>.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style\b[^>]*>.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def low(value: str) -> str:
    return clean(value).lower()


def relevant(value: str) -> bool:
    text = low(value)
    return any(x in text for x in GEO) and any(x in text for x in VESSEL) and any(x in text for x in RISK)


def warn_no(value: str) -> str | None:
    for pat in (
        r"\b(?:warning|ukmto)\s*[-:#]?\s*(\d{2,3})\s*[-_/]\s*26\b",
        r"\bukmto\s+#?(\d{2,3})\b",
    ):
        m = re.search(pat, value, flags=re.I)
        if m:
            return f"{int(m.group(1)):03d}-26"
    return None


def warn_int(value: str | None) -> int:
    m = re.match(r"^(\d{2,3})-26$", value or "")
    return int(m.group(1)) if m else 0


def digest(value: str) -> str:
    return hashlib.sha256(low(value).encode()).hexdigest()[:16]


def pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        return clean(" ".join((p.extract_text() or "") for p in reader.pages[:8]))
    except Exception:
        return ""


def fetch_source(url: str) -> tuple[str, str]:
    body, ctype, final_url = fetch(url)
    if body.startswith(b"%PDF") or "pdf" in ctype or final_url.lower().split("?")[0].endswith(".pdf"):
        return pdf_text(body), final_url
    return clean(body.decode("utf-8", errors="replace")), final_url


def candidate_urls(number: int) -> list[str]:
    yy = str(now().year)[-2:]
    urls: list[str] = []
    # Most UKMTO warning files use the issue date in the path. Today/yesterday is enough for a 15-minute watcher.
    for delta in (0, 1):
        stamp = (now().date() - dt.timedelta(days=delta)).strftime("%Y%m%d")
        urls.extend((
            f"https://www.ukmto.org/-/media/ukmto/products/{stamp}-ukmto_warning_{number:03d}-{yy}.pdf",
            f"https://www.ukmto.org/-/media/ukmto/products/{stamp}-ukmto_warning_attack_{number:03d}_{yy}.pdf",
            f"https://www.ukmto.org/-/media/ukmto/products/{stamp}-ukmto_warning_suspicious_activity_{number:03d}_{yy}.pdf",
        ))
    return urls


def official_scan(highest: int) -> tuple[list[dict], int, list[str]]:
    rows: dict[str, dict] = {}
    errors: list[str] = []
    max_seen = highest

    # Always re-read the most recent verified warning so an official update to the same warning can be detected.
    for expected, url in SEED_URLS.items():
        try:
            text, final_url = fetch_source(url)
            no = warn_no(text)
            if no == expected and "ukmto" in low(text):
                key = f"ukmto:{no}:{digest(text)}"
                rows[key] = {"key": key, "warning": no, "url": final_url, "text": text, "relevant": relevant(text), "lane": "seed-direct"}
        except Exception as e:
            errors.append(f"seed {expected}: {type(e).__name__}: {e}")

    # Probe a small forward window. This is fast enough for every 15 minutes and catches skipped/advisory numbers.
    start = max(BASELINE_WARNING + 1, highest + 1)
    for number in range(start, start + 6):
        for url in candidate_urls(number):
            try:
                text, final_url = fetch_source(url)
            except Exception as e:
                if getattr(e, "code", None) in (403, 404):
                    continue
                continue
            no = warn_no(text)
            if no and warn_int(no) == number and "ukmto" in low(text):
                key = f"ukmto:{no}:{digest(text)}"
                rows[key] = {"key": key, "warning": no, "url": final_url, "text": text, "relevant": relevant(text), "lane": "sequential-direct"}
                max_seen = max(max_seen, number)
                break
    return list(rows.values()), max_seen, errors


def gnews(query: str) -> list[dict]:
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    body, _, _ = fetch(url, "application/rss+xml,application/xml,text/xml,*/*")
    root = ET.fromstring(body)
    out = []
    for item in root.findall(".//item"):
        source = ""
        for child in list(item):
            if child.tag.endswith("source"):
                source = clean(child.text or "")
                break
        out.append({
            "title": clean(item.findtext("title") or ""),
            "url": (item.findtext("link") or "").strip(),
            "description": clean(item.findtext("description") or ""),
            "published": clean(item.findtext("pubDate") or ""),
            "source": source,
        })
    return out


def news_scan() -> tuple[list[dict], list[str], list[dict]]:
    selected: dict[str, dict] = {}
    samples: list[dict] = []
    errors: list[str] = []
    for query in NEWS_QUERIES:
        try:
            items = gnews(query)
            samples.extend(items[:3])
            for item in items:
                text = item["title"] + " " + item["description"]
                if item["source"] not in TRUSTED or not relevant(text):
                    continue
                key = hashlib.sha256((item["source"] + "|" + item["title"] + "|" + item["url"]).encode()).hexdigest()[:18]
                selected[key] = {**item, "key": key, "warning": warn_no(text)}
        except Exception as e:
            errors.append(f"news {query!r}: {type(e).__name__}: {e}")
    return list(selected.values()), errors, samples[:12]


def load_state() -> dict:
    default = {"version": STATE_VERSION, "initialized": False, "official": {}, "news": {}, "highest_warning_seen": BASELINE_WARNING}
    if not STATE_PATH.exists():
        return default
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if int(state.get("version") or 0) < STATE_VERSION:
            return default
        state.setdefault("official", {})
        state.setdefault("news", {})
        state.setdefault("highest_warning_seen", BASELINE_WARNING)
        state.setdefault("initialized", False)
        return state
    except Exception:
        return default


def evidence(text: str) -> list[str]:
    text = clean(text)
    out: list[str] = []
    m = re.search(r"(\d+(?:\.\d+)?\s*NM\s+[^.]{3,100})", text, flags=re.I)
    if m:
        out.append("위치: " + m.group(1).strip())
    elif "Strait of Hormuz" in text:
        out.append("위치: Strait of Hormuz")
    m = re.search(r"((?:tanker|vessel|ship|VLCC)[^.]{0,220}(?:struck|hit|attack(?:ed)?|projectile|mine|fire|explosion)[^.]{0,220})", text, flags=re.I)
    if m:
        sentence = clean(m.group(1))[:380]
        sentence = re.sub(r"\b(?:unknown|unidentified) projectiles?\b", "미상 발사체", sentence, flags=re.I)
        out.append("사건: " + sentence)
    t = text.lower()
    if "crew are reported safe" in t or "crew are safe" in t or "all crew are reported safe" in t:
        out.append("인명: UKMTO 원문상 crew safe")
    if "no environmental impact" in t or "no reported environmental impact" in t:
        out.append("환경: 보고된 오염 없음")
    return out[:4]


def related(item: dict, news: list[dict]) -> list[dict]:
    no = item.get("warning")
    ot = low(item.get("text", ""))
    out = []
    for n in news:
        nt = low(n.get("title", "") + " " + n.get("description", ""))
        if no and n.get("warning") == no:
            out.append(n)
            continue
        common = sum(1 for token in ("hormuz", "khasab", "tanker", "projectile", "struck", "attack", "mine") if token in ot and token in nt)
        if common >= 4:
            out.append(n)
    rank = {"Reuters": 0, "Associated Press": 1, "AP News": 1, "U.S. Central Command": 2, "CENTCOM": 2}
    return sorted(out, key=lambda x: rank.get(x.get("source", ""), 9))[:3]


def alert_text(item: dict, news: list[dict], update: bool) -> str:
    lines = [
        "[호르무즈 해상보안 업데이트]" if update else "[호르무즈 해상보안 신규 경보]",
        f"UKMTO: {item.get('warning')}",
        f"확인시각: {now().strftime('%Y-%m-%d %H:%M KST')}",
    ]
    lines.extend(evidence(item.get("text", "")))
    lines.append("무기/공격주체: UKMTO가 특정하지 않은 내용은 추정하지 않음")
    lines.append("원문: " + item.get("url", ""))
    cross = related(item, news)
    if any(n.get("warning") == item.get("warning") and item.get("warning") for n in cross):
        lines.append("교차검증: 경보번호까지 일치하는 신뢰 보도 확인")
    elif cross:
        lines.append("교차검증: 관련 신뢰 보도 확인. 동일 사건 여부가 확정되지 않은 내용은 별도 취급")
    else:
        lines.append("교차검증: UKMTO 공식 원문 우선 확인. Reuters/AP 후속 보도는 아직 검색되지 않음")
    for n in cross:
        lines.append(f"- {n.get('source')}: {n.get('title')} | {n.get('url')}")
    lines.append("표기 원칙: unknown/unidentified projectile = 미상 발사체. 포탄·미사일·드론으로 임의 단정하지 않음.")
    return "\n".join(lines) + "\n"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()
    initialized = bool(state.get("initialized"))
    highest = max(BASELINE_WARNING, int(state.get("highest_warning_seen") or BASELINE_WARNING))

    official, max_seen, official_errors = official_scan(highest)
    news, news_errors, news_samples = news_scan()
    old_official = state.get("official") or {}
    old_news = state.get("news") or {}

    new_rows = []
    for item in official:
        if item["key"] in old_official:
            continue
        same_warning = any(v.get("warning") == item.get("warning") for v in old_official.values())
        if initialized and item.get("relevant"):
            new_rows.append((item, same_warning))

    pending = {
        "version": STATE_VERSION,
        "initialized": True,
        "official": dict(old_official),
        "news": dict(old_news),
        "highest_warning_seen": max_seen,
        "last_checked_kst": now().isoformat(timespec="seconds"),
    }
    for item in official:
        pending["official"][item["key"]] = {
            "warning": item.get("warning"), "url": item.get("url"), "relevant": item.get("relevant"),
            "first_seen_kst": old_official.get(item["key"], {}).get("first_seen_kst") or now().isoformat(timespec="seconds"),
        }
    for item in news:
        pending["news"][item["key"]] = {
            "source": item.get("source"), "title": item.get("title"), "url": item.get("url"),
            "first_seen_kst": old_news.get(item["key"], {}).get("first_seen_kst") or now().isoformat(timespec="seconds"),
        }
    OUT_PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if new_rows:
        OUT_ALERT.write_text("\n\n".join(alert_text(item, news, update) for item, update in new_rows), encoding="utf-8")
    elif OUT_ALERT.exists():
        OUT_ALERT.unlink()

    errors = official_errors + news_errors
    status = [
        "# Hormuz maritime watch",
        f"- checked: {now().strftime('%Y-%m-%d %H:%M:%S KST')}",
        f"- state_version: {STATE_VERSION}",
        f"- initialized_before_run: {initialized}",
        f"- highest_warning_seen: {max_seen}",
        f"- official_items_detected: {len(official)}",
        f"- official_relevant_items: {sum(1 for x in official if x.get('relevant'))}",
        f"- trusted_news_items: {len(news)}",
        f"- new_official_alerts: {len(new_rows)}",
        "- trigger: UKMTO official evidence only; news is cross-check/context only.",
        "- fidelity: unknown/unidentified projectile remains 미상 발사체 unless an official source identifies it.",
    ]
    if errors:
        status.append("- partial errors:")
        status.extend("  - " + x[:500] for x in errors[:8])
    OUT_STATUS.write_text("\n".join(status) + "\n", encoding="utf-8")
    OUT_DEBUG.write_text(json.dumps({"official": official, "news": news, "errors": errors, "news_samples": news_samples}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"hormuz_watch_v3 initialized={initialized} highest={max_seen} official={len(official)} relevant={sum(1 for x in official if x.get('relevant'))} news={len(news)} new={len(new_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
