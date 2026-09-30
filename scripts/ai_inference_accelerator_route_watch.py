#!/usr/bin/env python3
"""Low-frequency OpenAI inference accelerator / model-routing watcher.

Alerts only on material changes that can alter the Cerebras/NVIDIA inference thesis:
- model -> accelerator mapping becomes explicit or changes
- Ultrafast launch/support changes
- tokens/s, batch size, or service-tier pricing changes
- OpenAI/Cerebras 750MW tranches come online or are delayed/cut
- contract/capacity changes between OpenAI and accelerator vendors

The first run establishes a silent baseline. State is committed only after the
workflow confirms Telegram delivery (or confirms that no alert was generated).
"""
from __future__ import annotations

import datetime as dt
import email.utils
import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
UTC = dt.timezone.utc
ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "out"
DATA.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)

STATE_PATH = DATA / "ai_inference_accelerator_route_watch_state.json"
PENDING_PATH = OUT / "ai_inference_accelerator_route_watch_pending_state.json"
ALERT_TITLE = OUT / "ai_inference_accelerator_route_watch_alert_title.txt"
ALERT_BODY = OUT / "ai_inference_accelerator_route_watch_alert.html"
STATUS_PATH = OUT / "ai_inference_accelerator_route_watch_status.md"
CONFIRMED_PATH = OUT / "ai_inference_accelerator_route_watch_telegram_confirmed.json"

GOOGLE_NEWS = "https://news.google.com/rss/search"
USER_AGENT = "Mozilla/5.0 khs-ai-inference-accelerator-route-watch/1.0"
MAX_AGE_HOURS = 120
SEEN_RETENTION_DAYS = 45
MAX_ALERT_EVENTS = 5

NEWS_QUERIES = [
    '"OpenAI" Cerebras NVIDIA Ultrafast inference GPU accelerator',
    '"GPT-6.1 Sol" Ultrafast NVIDIA Cerebras GPU',
    '"GPT-6 Astra" Ultrafast Cerebras NVIDIA GPU',
    '"OpenAI" "750MW" Cerebras tranche capacity online',
    '"OpenAI" Cerebras contract capacity delay cancellation 750MW',
    '"OpenAI" inference routing accelerator NVIDIA Cerebras AMD ASIC',
    '"OpenAI" tokens per second Ultrafast batch size GPU Cerebras',
    '"Cerebras" OpenAI model support GPT-6.1 Astra Ultrafast',
    '"OpenAI" service_tier ultrafast pricing speed',
    '"OpenAI" low batch NVIDIA GPU inference latency',
]

OFFICIAL_PAGES = {
    "OpenAI·Cerebras 750MW 계약": "https://openai.com/index/cerebras-partnership/",
    "OpenAI Ultrafast 모드": "https://developers.openai.com/api/docs/guides/ultrafast-mode",
    "OpenAI GPT-6.1 Sol 모델": "https://developers.openai.com/api/docs/models/gpt-6.1-sol",
    "OpenAI GPT-5.6 Sol Ultrafast 미리보기": "https://openai.com/index/previewing-ultrafast/",
}

OFFICIAL_SOURCE_HINTS = (
    "openai", "cerebras", "nvidia", "amd", "sec", "investor",
)
TRUSTED_SOURCE_HINTS = (
    "reuters", "bloomberg", "financial times", "the information", "cnbc",
    "techcrunch", "the verge", "ars technica", "semianalysis", "tom's hardware",
    "tomshardware", "serve the home", "servethehome", "venturebeat",
)

MODEL_TERMS = (
    "gpt-6.1 sol", "gpt 6.1 sol", "gpt-6 astra", "gpt 6 astra",
    "gpt-5.6 sol", "gpt 5.6 sol", "ultrafast",
)
ACCELERATOR_TERMS = (
    "cerebras", "nvidia", "gpu", "wafer scale", "wse", "amd", "asic",
    "accelerator", "inference hardware", "inference stack",
)
CONCRETE_TERMS = (
    "ultrafast", "service_tier", "service tier", "available", "availability",
    "preview", "launch", "launched", "support", "supported", "runs on",
    "powered by", "nvidia gpu", "cerebras", "750mw", "750 mw", "tranche",
    "come online", "comes online", "online capacity", "capacity", "mw",
    "tokens per second", "tokens/s", "tok/s", "batch", "batch size",
    "price", "pricing", "cost", "contract", "agreement", "deal",
    "delay", "delayed", "cancel", "cancelled", "canceled", "cut",
    "reduced", "expanded", "increase", "decrease", "routing", "route",
    "deployment", "deployed", "production",
)

CATEGORY_PATTERNS = [
    ("모델→가속기 배치 확정", (
        "runs on", "powered by", "nvidia gpu", "cerebras", "inference hardware",
        "accelerator", "routing", "route", "backend", "back-end",
    )),
    ("Ultrafast 출시·지원범위", (
        "ultrafast", "service_tier", "service tier", "available", "availability",
        "preview", "support", "supported", "launch", "launched",
    )),
    ("속도·배치·가격 변화", (
        "tokens per second", "tokens/s", "tok/s", "batch", "batch size",
        "price", "pricing", "cost", "latency", "throughput",
    )),
    ("Cerebras 750MW 가동·트랜치", (
        "750mw", "750 mw", "tranche", "come online", "comes online",
        "online capacity", "live capacity", "megawatt", " mw",
    )),
    ("계약·용량 변경", (
        "contract", "agreement", "deal", "capacity", "delay", "delayed",
        "cancel", "cancelled", "canceled", "cut", "reduced", "expanded",
        "increase", "decrease",
    )),
]

HANGUL_RE = re.compile(r"[가-힣]")
LATIN_WORD_RE = re.compile(r"[A-Za-z]{2,}")
TRANSLATE_GOOGLE = "https://translate.googleapis.com/translate_a/single"
TRANSLATE_MYMEMORY = "https://api.mymemory.translated.net/get"
IDENTIFIERS = (
    "OpenAI", "Cerebras", "NVIDIA", "AMD", "GPT-6.1 Sol", "GPT-6 Astra",
    "GPT-5.6 Sol", "Ultrafast", "GPU", "WSE", "ASIC",
)


def fetch_bytes(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml,application/xml,text/html,application/json,*/*"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def strip_html(value: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", value or "")).replace("\xa0", " ").split())


def parse_pubdate(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except Exception:
        return None


def google_news_url(query: str) -> str:
    return GOOGLE_NEWS + "?" + urllib.parse.urlencode({
        "q": query,
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    })


def parse_google_news(query: str, now: dt.datetime) -> list[dict]:
    root = ET.fromstring(fetch_bytes(google_news_url(query)))
    out = []
    for node in root.findall(".//item"):
        title = strip_html(node.findtext("title") or "")
        desc = strip_html(node.findtext("description") or "")
        link = (node.findtext("link") or "").strip()
        source_node = node.find("source")
        source = strip_html(source_node.text if source_node is not None and source_node.text else "")
        published = parse_pubdate(node.findtext("pubDate"))
        if not title or not link:
            continue
        if published and now - published > dt.timedelta(hours=MAX_AGE_HOURS):
            continue
        out.append({
            "kind": "news",
            "query": query,
            "title": title,
            "description": desc,
            "source": source or "Google News",
            "url": link,
            "published_at": published.isoformat() if published else None,
        })
    return out


def source_official(source: str) -> bool:
    low = source.lower()
    return any(x in low for x in OFFICIAL_SOURCE_HINTS)


def source_trusted(source: str) -> bool:
    low = source.lower()
    return source_official(source) or any(x in low for x in TRUSTED_SOURCE_HINTS)


def material(item: dict) -> bool:
    low = f" {item.get('title','')} {item.get('description','')} ".lower()
    if not ("openai" in low or "gpt-" in low or "gpt " in low):
        return False
    if not any(x in low for x in ACCELERATOR_TERMS):
        return False
    if not any(x in low for x in CONCRETE_TERMS):
        return False
    if item.get("kind") == "official_page":
        return True
    return source_trusted(item.get("source", ""))


def detect_category(text: str) -> str:
    low = text.lower()
    scored = []
    for label, patterns in CATEGORY_PATTERNS:
        score = sum(1 for p in patterns if p in low)
        if score:
            scored.append((score, label))
    if not scored:
        return "추론 라우팅 변화"
    scored.sort(reverse=True)
    return scored[0][1]


def detect_entity(text: str) -> str:
    low = text.lower()
    if "cerebras" in low and "nvidia" in low:
        return "OpenAI · Cerebras/NVIDIA"
    if "cerebras" in low:
        return "OpenAI · Cerebras"
    if "nvidia" in low or "gpu" in low:
        return "OpenAI · NVIDIA"
    if "amd" in low:
        return "OpenAI · AMD"
    return "OpenAI 추론 인프라"


def fingerprint(item: dict) -> str:
    raw = "|".join([item.get("url",""), item.get("title",""), item.get("source","")])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def token_set(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9][a-z0-9+._-]{2,}", text.lower())
    stop = {"the","and","for","with","from","that","this","openai","ai","new","says","said"}
    return {w for w in words if w not in stop and not w.isdigit()}


def similarity(a: str, b: str) -> float:
    aa, bb = token_set(a), token_set(b)
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / len(aa | bb)


def normalize(item: dict) -> dict:
    text = f"{item.get('title','')} {item.get('description','')}"
    out = dict(item)
    out["fingerprint"] = fingerprint(item)
    out["category"] = detect_category(text)
    out["entity"] = detect_entity(text)
    out["official"] = source_official(item.get("source","")) or item.get("kind") == "official_page"
    return out


def official_page_snapshots() -> dict[str, dict]:
    out = {}
    keyword = re.compile(
        r"(?i)(?:GPT-6\.1 Sol|GPT-6 Astra|GPT-5\.6 Sol|Ultrafast|Cerebras|NVIDIA|750\s*MW|tranche|"
        r"tokens? per second|tokens?/s|service[_ -]?tier|batch(?: size)?|pricing|price|capacity|inference stack)"
    )
    for name, url in OFFICIAL_PAGES.items():
        try:
            raw = fetch_bytes(url).decode("utf-8", "ignore")
        except Exception as exc:
            # OpenAI/Cerebras pages can sometimes block automated fetches.
            # Keep monitoring the remaining official pages and news sources.
            print(f"ai_inference_route_official_page_skip={name}: {type(exc).__name__}: {exc}")
            continue
        text = strip_html(raw)
        pieces = []
        for m in keyword.finditer(text):
            start = max(0, m.start() - 140)
            end = min(len(text), m.end() + 240)
            piece = re.sub(r"\s+", " ", text[start:end]).strip()
            if piece not in pieces:
                pieces.append(piece)
        material_text = "\n".join(pieces[:80]) if pieces else text[:8000]
        out[name] = {
            "url": url,
            "digest": hashlib.sha256(material_text.encode("utf-8")).hexdigest(),
            "material": material_text[:2200],
        }
    return out

def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"initialized": False, "seen": {}, "official_pages": {}}
    try:
        obj = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        obj.setdefault("initialized", False)
        obj.setdefault("seen", {})
        obj.setdefault("official_pages", {})
        return obj
    except Exception:
        return {"initialized": False, "seen": {}, "official_pages": {}}


def save_json(path: pathlib.Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def prune_seen(seen: dict, now: dt.datetime) -> dict:
    cutoff = now - dt.timedelta(days=SEEN_RETENTION_DAYS)
    out = {}
    for key, row in seen.items():
        stamp = row.get("first_seen_at") or row.get("published_at")
        try:
            when = dt.datetime.fromisoformat(str(stamp).replace("Z","+00:00")).astimezone(UTC)
        except Exception:
            when = now
        if when >= cutoff:
            out[key] = row
    return out


def previously_similar(item: dict, seen: dict) -> bool:
    for row in seen.values():
        if row.get("category") != item.get("category"):
            continue
        if similarity(item.get("title",""), row.get("title","")) >= 0.48:
            return True
    return False


def cluster_events(items: list[dict]) -> list[list[dict]]:
    clusters: list[list[dict]] = []
    for item in sorted(items, key=lambda x: (bool(x.get("official")), x.get("published_at") or ""), reverse=True):
        placed = False
        for cluster in clusters:
            rep = cluster[0]
            if rep.get("category") == item.get("category") and similarity(rep.get("title",""), item.get("title","")) >= 0.18:
                cluster.append(item)
                placed = True
                break
        if not placed:
            clusters.append([item])
    return clusters[:MAX_ALERT_EVENTS]


def _needs_korean_translation(text: str) -> bool:
    value = strip_html(text)
    return not HANGUL_RE.search(value) and len(LATIN_WORD_RE.findall(value)) >= 3


def _preserve_identifiers(original: str, translated: str) -> str:
    found = []
    low = original.lower()
    for term in IDENTIFIERS:
        if term.lower() in low and term.lower() not in translated.lower():
            found.append(term)
    if found:
        return " · ".join(found) + " · " + translated
    return translated


def _translate_google(text: str) -> str:
    params = urllib.parse.urlencode({"client":"gtx","sl":"auto","tl":"ko","dt":"t","q":text})
    req = urllib.request.Request(
        TRANSLATE_GOOGLE + "?" + params,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json,text/plain,*/*"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    chunks = payload[0] if isinstance(payload, list) and payload else []
    return "".join(str(x[0]) for x in chunks if isinstance(x, list) and x and x[0]).strip()


def _translate_mymemory(text: str) -> str:
    params = urllib.parse.urlencode({"q":text,"langpair":"en|ko"})
    req = urllib.request.Request(
        TRANSLATE_MYMEMORY + "?" + params,
        headers={"User-Agent": USER_AGENT, "Accept":"application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return str((payload.get("responseData") or {}).get("translatedText") or "").strip()


def translate_alert_text(text: str) -> str:
    value = " ".join(strip_html(text).split())
    if not _needs_korean_translation(value):
        return value
    errors = []
    for fn in (_translate_google, _translate_mymemory):
        for _attempt in range(2):
            try:
                out = " ".join(strip_html(fn(value)).split())
                if out and HANGUL_RE.search(out):
                    return _preserve_identifiers(value, out)
                errors.append(f"{fn.__name__}: no Hangul")
            except Exception as exc:
                errors.append(f"{fn.__name__}: {type(exc).__name__}: {exc}")
    raise RuntimeError("Korean translation failed: " + " | ".join(errors[-4:]))


def source_label(source: str) -> str:
    low = source.lower()
    mapping = (
        ("openai","OpenAI"), ("cerebras","Cerebras"), ("nvidia","NVIDIA"),
        ("semianalysis","SemiAnalysis"), ("reuters","Reuters"),
        ("bloomberg","Bloomberg"), ("financial times","Financial Times"),
        ("the information","The Information"), ("cnbc","CNBC"),
        ("techcrunch","TechCrunch"), ("the verge","The Verge"),
    )
    for key, label in mapping:
        if key in low:
            return label
    return re.sub(r"^www\.","",source)[:26] or "원문"


def concise_fact(item: dict) -> str:
    title = re.sub(r"\s+-\s+[^-]{1,45}$", "", item.get("title","")).strip()
    try:
        title = translate_alert_text(title)
    except Exception as exc:
        print(f"ai_inference_route_translation_fallback={type(exc).__name__}: {exc}")
        title = f"{item.get('entity') or 'OpenAI 추론 인프라'} 관련 {item.get('category') or '중요 변화'} 공식 업데이트"
    return title[:155].rstrip() + ("…" if len(title) > 155 else "")


def impact(category: str) -> str:
    if category == "모델→가속기 배치 확정":
        return "같은 OpenAI 모델이 어느 가속기에서 실제 서비스되는지가 확정되면 Cerebras와 NVIDIA의 실질 점유 영역이 바뀝니다."
    if category == "Ultrafast 출시·지원범위":
        return "Ultrafast 지원 모델이 늘거나 바뀌면 초저지연 추론의 실제 공급자가 누구인지 확인할 수 있습니다."
    if category == "속도·배치·가격 변화":
        return "토큰 속도·배치 크기·가격의 조합이 바뀌면 NVIDIA 저배치 GPU와 Cerebras의 경제성 비교가 달라집니다."
    if category == "Cerebras 750MW 가동·트랜치":
        return "계약 750MW보다 실제 가동·검수된 MW가 Cerebras의 매출 인식과 OpenAI 내 채택 강도를 더 직접적으로 보여줍니다."
    if category == "계약·용량 변경":
        return "계약금액·용량·일정의 증액·감액·지연은 Cerebras의 남은 계약매출과 OpenAI의 멀티가속기 전략을 직접 바꿉니다."
    return "OpenAI가 워크로드별로 어떤 가속기를 선택하는지 확인하는 변화입니다."


def build_alert(events: list[list[dict]], now: dt.datetime) -> tuple[str,str]:
    title = f"⚡ <b>AI 추론 가속기·모델 라우팅 Watch</b> · 중요 변화 {len(events)}건"
    lines = [f"<i>{now.astimezone(KST).strftime('%m/%d %H:%M KST')}</i>"]
    for idx, cluster in enumerate(events, 1):
        rep = cluster[0]
        lines += [
            "",
            f"<b>{idx}. {html.escape(rep['entity'])} · {html.escape(rep['category'])}</b>",
            f"• {html.escape(concise_fact(rep))}",
            f"• <b>의미</b>: {html.escape(impact(rep['category']))}",
        ]
        sources = []
        official = False
        for item in cluster:
            label = source_label(item.get("source",""))
            if label not in [x[0] for x in sources]:
                sources.append((label,item.get("url","")))
            official = official or bool(item.get("official"))
        level = "공식 원천 포함" if official else (f"복수 신뢰출처 {len(sources)}곳" if len(sources) >= 2 else "신뢰자료 1건·추가 확인 필요")
        lines.append(f"• <b>확인</b>: {html.escape(level)}")
        links = [f'<a href="{html.escape(url,quote=True)}">{html.escape(label)}</a>' for label,url in sources[:4] if url]
        if links:
            lines.append("🔗 " + " · ".join(links))
    lines += [
        "",
        "<b>다음 확인</b>: 모델→가속기 확정 · Ultrafast 정식 출시/지원범위 · tokens/s · batch 크기 · 가격 · Cerebras 750MW 트랜치 가동 · 실제 live MW · 계약 증감·지연",
    ]
    return title, "\n".join(lines)


def main() -> int:
    for p in (ALERT_TITLE, ALERT_BODY, CONFIRMED_PATH):
        p.unlink(missing_ok=True)

    now = dt.datetime.now(UTC)
    state = load_state()
    errors: list[str] = []
    raw: list[dict] = []

    for query in NEWS_QUERIES:
        try:
            raw.extend(parse_google_news(query, now))
        except Exception as exc:
            errors.append(f"Google News 실패: {query[:55]} / {type(exc).__name__}: {exc}")

    normalized = {}
    for row in raw:
        item = normalize(row)
        if material(item):
            normalized[item["fingerprint"]] = item
    current = list(normalized.values())

    seen = prune_seen(dict(state.get("seen") or {}), now)
    new_items = [
        item for item in current
        if item["fingerprint"] not in seen and not previously_similar(item, seen)
    ]

    official_pages = dict(state.get("official_pages") or {})
    try:
        snapshots = official_page_snapshots()
        for name, snap in snapshots.items():
            previous = official_pages.get(name)
            if previous and previous.get("digest") != snap["digest"]:
                page_item = normalize({
                    "kind":"official_page",
                    "query":"official page change",
                    "title":f"{name} 공식 페이지 핵심 내용 변경",
                    "description":snap.get("material",""),
                    "source":"OpenAI",
                    "url":snap["url"],
                    "published_at":now.isoformat(),
                })
                new_items.append(page_item)
            official_pages[name] = {
                "digest":snap["digest"],
                "url":snap["url"],
                "updated_at":now.isoformat(),
            }
    except Exception as exc:
        errors.append(f"공식 페이지 감시 실패: {type(exc).__name__}: {exc}")

    baseline = not bool(state.get("initialized"))
    if baseline:
        new_items = []

    first_seen = now.isoformat()
    for item in current:
        seen.setdefault(item["fingerprint"], {
            "title":item["title"], "source":item["source"], "url":item["url"],
            "category":item["category"], "entity":item["entity"],
            "published_at":item.get("published_at"), "first_seen_at":first_seen,
        })

    events = cluster_events(new_items)
    pending = {
        "initialized": True,
        "updated_at_kst": now.astimezone(KST).isoformat(timespec="seconds"),
        "seen": seen,
        "official_pages": official_pages,
        "last_collection": {
            "raw_items":len(raw),
            "material_items":len(current),
            "new_articles":len(new_items),
            "new_events":len(events),
            "errors":errors,
        },
    }
    save_json(PENDING_PATH, pending)

    if events:
        title, body = build_alert(events, now)
        ALERT_TITLE.write_text(title + "\n", encoding="utf-8")
        ALERT_BODY.write_text(body.rstrip() + "\n", encoding="utf-8")

    status = [
        "# AI 추론 가속기·모델 라우팅 Watch",
        "",
        f"- 조회시각: {now.astimezone(KST).strftime('%Y-%m-%d %H:%M:%S KST')}",
        f"- 최초 기준선: {'예' if baseline else '아니오'}",
        f"- 웹 수집: {len(raw)}건",
        f"- 중요 필터 통과: {len(current)}건",
        f"- 신규 중요 사건: {len(events)}건",
        f"- 공식 페이지 기준선: {len(official_pages)}개",
        f"- 오류: {len(errors)}건",
    ]
    if errors:
        status += ["", "## 오류"] + [f"- {x}" for x in errors[:10]]
    STATUS_PATH.write_text("\n".join(status) + "\n", encoding="utf-8")
    print(
        f"ai_inference_route_baseline={str(baseline).lower()} "
        f"material={len(current)} new_articles={len(new_items)} "
        f"new_events={len(events)} errors={len(errors)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
