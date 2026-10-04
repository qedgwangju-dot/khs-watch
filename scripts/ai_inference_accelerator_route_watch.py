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
from html.parser import HTMLParser
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
OFFICIAL_SNAPSHOT_SCHEMA_VERSION = 2
OFFICIAL_CHANGE_CONFIRM_RUNS = 2
OFFICIAL_CHANGE_CONFIRM_SECONDS = 600

IMMUTABLE_OFFICIAL_REFERENCE_PAGES = {
    "OpenAI·Cerebras 750MW 계약",
    "OpenAI GPT-5.6 Sol Ultrafast 미리보기",
    "Synopsys 2026 Investor Day",
    "Synopsys GPT-Synopsys",
    "Synopsys Autopilot",
}

MUTABLE_SEMANTIC_OFFICIAL_PAGES = {
    "OpenAI Ultrafast 모드",
    "OpenAI GPT-6.1 Sol 모델",
}

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
    '"Synopsys" EDA consumption-based pricing AI agents tapeout output licensing',
    '"Synopsys" FY2027 revenue guidance 11.15 billion investor day',
    '"Synopsys" GPT-Synopsys OpenAI licensing revenue share general availability',
    '"Synopsys" AWS licensing royalty output custom silicon Trainium Graviton',
]

OFFICIAL_PAGES = {
    "OpenAI·Cerebras 750MW 계약": "https://openai.com/index/cerebras-partnership/",
    "OpenAI Ultrafast 모드": "https://developers.openai.com/api/docs/guides/ultrafast-mode",
    "OpenAI GPT-6.1 Sol 모델": "https://developers.openai.com/api/docs/models/gpt-6.1-sol",
    "OpenAI GPT-5.6 Sol Ultrafast 미리보기": "https://openai.com/index/previewing-ultrafast/",
    "Synopsys 2026 Investor Day": "https://investor.synopsys.com/news/news-details/2026/Synopsys-Details-Growth-Strategy-and-Long-term-Financial-Model-at-2026-Investor-Day/",
    "Synopsys GPT-Synopsys": "https://investor.synopsys.com/news/news-details/2026/OpenAI-and-Synopsys-Announce-GPT-Synopsys-Frontier-Intelligence-to-Revolutionize-Chip-Design/default.aspx",
    "Synopsys Autopilot": "https://investor.synopsys.com/news/news-details/2026/Synopsys-Powers-Autonomous-Engineering-with-a-Broad-Portfolio-of-Long-Horizon-Agents-and-Autopilot-Platform/default.aspx",
}

OFFICIAL_SOURCE_HINTS = (
    "openai", "cerebras", "nvidia", "amd", "sec", "investor", "synopsys",
)
TRUSTED_SOURCE_HINTS = (
    "reuters", "bloomberg", "financial times", "the information", "cnbc",
    "techcrunch", "the verge", "ars technica", "semianalysis", "tom's hardware",
    "tomshardware", "serve the home", "servethehome", "venturebeat",
    "barron's", "barrons", "investors business daily", "investopedia",
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


SYNOPSYS_ID = re.compile(r'\bSynopsys\b|시놉시스', re.I)
SYNOPSYS_AI_MONETIZATION = re.compile(r'consumption[-\s]*based|subscription|consumption|usage[-\s]*based|agent|Autopilot|과금|구독|사용량|소비기반', re.I)
SYNOPSYS_GUIDANCE = re.compile(r'FY\s*2027|fiscal\s*2027|2027.{0,20}(?:revenue|매출)|revenue.{0,20}2027', re.I)
SYNOPSYS_1115_BASE = re.compile(r'\$?\s*11\.15\s*billion|\$?\s*11,?150\s*million|111\.5\s*억\s*달러', re.I)
SYNOPSYS_15_BASE = re.compile(r'(?:revenue\s+growth|매출\s*성장).{0,30}(?:~?\s*15\s*%|approximately\s+15\s*%)|15\s*%.{0,30}(?:revenue\s+growth|매출\s*성장)', re.I)
SYNOPSYS_BASELINE_RE = re.compile(r'2026\s+Investor\s+Day|September\s+30,?\s+2026|9월\s*30일|subscription.{0,80}consumption[-\s]*based|consumption[-\s]*based.{0,80}subscription', re.I)
SYNOPSYS_PRICING_DETAIL = re.compile(r'(?:per[-\s]*(?:run|design|tapeout|job|token|compute|hour)|rate\s*card|unit\s*price|price\s*per|tapeout[-\s]*based|output[-\s]*based|royalty\s*rate|사용량\s*단가|건당\s*과금|테이프아웃\s*연동)', re.I)
SYNOPSYS_PRICING_EXEC = re.compile(r'(?:launched|rolled\s+out|available|signed|customer\s+adoption|production|실제\s*도입|상용\s*적용|고객\s*채택|출시|정식\s*도입)', re.I)
SYNOPSYS_GPT = re.compile(r'GPT[-\s]*Synopsys|OpenAI.{0,60}Synopsys|Synopsys.{0,60}OpenAI', re.I)
SYNOPSYS_GPT_MILESTONE = re.compile(r'general\s+availability|generally\s+available|launched|customer\s+deployment|license\s+revenue|revenue\s+share|first\s+customer|정식\s*출시|고객\s*배치|첫\s*고객|사용권\s*매출|수익\s*배분', re.I)
SYNOPSYS_AWS = re.compile(r'Amazon\s+Web\s+Services|\bAWS\b|Amazon', re.I)
SYNOPSYS_AWS_BASE = re.compile(r'(?:over|more\s+than|>)\s*\$?\s*1\s*billion|\$?\s*1\s*billion.{0,60}(?:agreement|deal|license)', re.I)
SYNOPSYS_NEW_HYPERSCALER = re.compile(r'Google|Alphabet|Microsoft|Meta|Oracle|Anthropic|xAI', re.I)
SYNOPSYS_GUIDANCE_CHANGE = re.compile(r'raise|raised|lower|lowered|cut|increase|decrease|revised|updated|상향|하향|삭감|수정|변경', re.I)


def synopsys_stage(text: str) -> str:
    if not SYNOPSYS_ID.search(text):
        return ""
    if SYNOPSYS_GUIDANCE.search(text) and SYNOPSYS_1115_BASE.search(text) and (SYNOPSYS_15_BASE.search(text) or SYNOPSYS_BASELINE_RE.search(text)):
        return "investor_day_baseline"
    if SYNOPSYS_AI_MONETIZATION.search(text) and SYNOPSYS_BASELINE_RE.search(text) and not SYNOPSYS_PRICING_DETAIL.search(text):
        return "monetization_baseline"
    if SYNOPSYS_AWS.search(text) and SYNOPSYS_AWS_BASE.search(text) and not SYNOPSYS_NEW_HYPERSCALER.search(text):
        return "aws_baseline"
    if SYNOPSYS_GPT.search(text) and re.search(r'multi[-\s]*year|strategic\s+partnership|preferred\s+partners?|공동\s*개발|전략적\s*파트너', text, re.I) and not SYNOPSYS_GPT_MILESTONE.search(text):
        return "gpt_baseline"
    if SYNOPSYS_GUIDANCE.search(text) and SYNOPSYS_GUIDANCE_CHANGE.search(text) and re.search(r'\$?\s*\d+(?:\.\d+)?\s*(?:billion|B)|\d+(?:\.\d+)?\s*%', text, re.I):
        return "guidance_change"
    if SYNOPSYS_PRICING_DETAIL.search(text) and SYNOPSYS_PRICING_EXEC.search(text):
        return "pricing_execution"
    if SYNOPSYS_GPT.search(text) and SYNOPSYS_GPT_MILESTONE.search(text):
        return "gpt_milestone"
    if SYNOPSYS_NEW_HYPERSCALER.search(text) and re.search(r'contract|agreement|license|customer|계약|사용권|고객', text, re.I):
        return "new_hyperscaler_contract"
    return "background"

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
    "Synopsys", "GPT-Synopsys", "Autopilot", "EDA", "AWS",
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
    text = f" {item.get('title','')} {item.get('description','')} "
    low = text.lower()

    # Synopsys EDA monetization / AI-chip-design lane.
    stage = synopsys_stage(text)
    if stage:
        if stage in {"investor_day_baseline","monetization_baseline","aws_baseline","gpt_baseline","background"}:
            return False
        if item.get("kind") == "official_page":
            return True
        return source_trusted(item.get("source", ""))

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
    syn = synopsys_stage(text)
    if syn == "guidance_change":
        return "Synopsys FY27 가이던스 변경"
    if syn == "pricing_execution":
        return "Synopsys 소비기반 과금 실제 도입"
    if syn == "gpt_milestone":
        return "GPT-Synopsys 상용화·수익화"
    if syn == "new_hyperscaler_contract":
        return "Synopsys 신규 하이퍼스케일러 계약"
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
    if SYNOPSYS_ID.search(text):
        if SYNOPSYS_GPT.search(text):
            return "Synopsys · OpenAI"
        if SYNOPSYS_AWS.search(text):
            return "Synopsys · AWS"
        return "Synopsys"
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


class _MainTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.main_depth = 0
        self.ignore_depth = 0
        self.saw_main = False
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag == "main":
            self.saw_main = True
            self.main_depth += 1
            return
        if self.main_depth and tag in {"script", "style", "noscript", "svg"}:
            self.ignore_depth += 1

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.main_depth and tag in {"script", "style", "noscript", "svg"} and self.ignore_depth:
            self.ignore_depth -= 1
            return
        if tag == "main" and self.main_depth:
            self.main_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.main_depth and not self.ignore_depth:
            value = " ".join((data or "").split())
            if value:
                self.parts.append(value)


def extract_primary_text(raw_html: str) -> str:
    parser = _MainTextParser()
    try:
        parser.feed(raw_html)
        parser.close()
    except Exception:
        parser.parts = []
    if parser.saw_main and parser.parts:
        return " ".join(parser.parts)
    return strip_html(raw_html)


def _first_float(patterns: tuple[str, ...], text: str) -> float | None:
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.I | re.S)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except Exception:
                continue
    return None


def _first_int(patterns: tuple[str, ...], text: str) -> int | None:
    value = _first_float(patterns, text)
    return int(value) if value is not None else None


def semantic_official_snapshot(name: str, text: str) -> dict:
    normalized = " ".join(text.split())
    low = normalized.lower()

    if name == "OpenAI Ultrafast 모드":
        if "ultrafast mode" not in low or "gpt-6 astra" not in low:
            raise RuntimeError("Ultrafast page semantic markers missing")

        return {
            "kind": "openai_ultrafast",
            "gpt_6_astra_supported": bool(
                re.search(r"(?:broadly\s+available|available).{0,90}gpt-6\s+astra|gpt-6\s+astra.{0,90}(?:available|ultrafast)", normalized, re.I)
            ),
            "gpt_5_6_sol_preview": bool(
                re.search(r"(?:preview\s+access|preview).{0,100}gpt-5\.6\s+sol|gpt-5\.6\s+sol.{0,100}preview", normalized, re.I)
            ),
            "gpt_6_1_sol_mentioned": "gpt-6.1 sol" in low,
            "service_tier_ultrafast": bool(re.search(r"service[_\s-]*tier.{0,40}ultrafast|ultrafast.{0,40}service[_\s-]*tier", normalized, re.I)),
            "max_speed_x": _first_float((
                r"up\s+to\s+([0-9.]+)\s*[x×]\s+faster",
                r"([0-9.]+)\s*[x×]\s+faster",
            ), normalized),
            "tier_1_3_tpm": _first_int((r"Tiers?\s*1\s*[–-]\s*3\s+([0-9,]+)",), normalized),
            "tier_4_tpm": _first_int((r"Tier\s*4\s+([0-9,]+)",), normalized),
            "tier_5_tpm": _first_int((r"Tier\s*5\s+([0-9,]+)",), normalized),
            "us_data_residency": "us data residency" in low,
            "eu_regional_supported": not bool(re.search(r"does\s+not\s+support\s+eu|not\s+support\s+eu", normalized, re.I)),
        }

    if name == "OpenAI GPT-6.1 Sol 모델":
        if "gpt-6.1 sol" not in low:
            raise RuntimeError("GPT-6.1 Sol page semantic markers missing")

        price_match = re.search(
            r"Text\s+tokens.{0,160}?Per\s+1M\s+tokens.{0,160}?"
            r"Input\s+\$?([0-9.]+).{0,100}?"
            r"Cached\s+input\s+\$?([0-9.]+).{0,100}?"
            r"Cache\s+writes\s+\$?([0-9.]+).{0,100}?"
            r"Output\s+\$?([0-9.]+)",
            normalized,
            flags=re.I | re.S,
        )
        if not price_match:
            raise RuntimeError("GPT-6.1 Sol pricing markers missing")

        return {
            "kind": "openai_gpt_6_1_sol",
            "ultrafast_mentioned": "ultrafast" in low,
            "fast_mode_mentioned": "fast mode" in low,
            "input_usd_per_mtok": float(price_match.group(1)),
            "cached_input_usd_per_mtok": float(price_match.group(2)),
            "cache_write_usd_per_mtok": float(price_match.group(3)),
            "output_usd_per_mtok": float(price_match.group(4)),
            "fast_multiplier_x": _first_float((
                r"Fast\s+mode\s+prices?\s+are\s+([0-9.]+)x\s+Standard",
                r"Fast\s+mode.{0,60}?([0-9.]+)x\s+Standard",
            ), normalized),
            "batch_flex_discount_pct": _first_float((
                r"Batch\s+and\s+Flex\s+prices?\s+are\s+([0-9.]+)%\s+lower",
                r"Batch\s+and\s+Flex.{0,80}?([0-9.]+)%\s+lower",
            ), normalized),
            "context_window": _first_int((r"([0-9,]+)\s+context\s+window",), normalized),
            "max_output_tokens": _first_int((r"([0-9,]+)\s+max\s+output\s+tokens",), normalized),
            "us_data_residency": "us" in low and "data residency" in low,
            "eu_data_residency": "eu data residency" in low,
        }

    raise RuntimeError(f"No semantic parser for mutable official page: {name}")


def _semantic_digest(semantic: dict) -> str:
    payload = json.dumps(semantic, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def official_page_snapshots() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for name, url in OFFICIAL_PAGES.items():
        if name in IMMUTABLE_OFFICIAL_REFERENCE_PAGES:
            semantic = {"kind": "immutable_reference", "name": name, "url": url}
            out[name] = {
                "url": url,
                "digest": _semantic_digest(semantic),
                "semantic": semantic,
                "material": "",
                "snapshot_type": "immutable",
            }
            continue

        if name not in MUTABLE_SEMANTIC_OFFICIAL_PAGES:
            continue

        try:
            raw = fetch_bytes(url).decode("utf-8", "ignore")
            primary_text = extract_primary_text(raw)
            semantic = semantic_official_snapshot(name, primary_text)
        except Exception as exc:
            print(f"ai_inference_route_official_page_skip={name}: {type(exc).__name__}: {exc}")
            continue

        out[name] = {
            "url": url,
            "digest": _semantic_digest(semantic),
            "semantic": semantic,
            "material": json.dumps(semantic, ensure_ascii=False, sort_keys=True),
            "snapshot_type": "semantic",
        }
    return out


def _parse_iso_utc(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
    except Exception:
        return None


def semantic_changes(old: dict, new: dict) -> list[tuple[str, object, object]]:
    keys = sorted(set(old) | set(new))
    return [(key, old.get(key), new.get(key)) for key in keys if old.get(key) != new.get(key)]


def official_change_category(name: str, old: dict, new: dict) -> str:
    changes = {key for key, _old, _new in semantic_changes(old, new)}
    if name == "OpenAI Ultrafast 모드":
        return "Ultrafast 출시·지원범위"
    if name == "OpenAI GPT-6.1 Sol 모델":
        if "ultrafast_mentioned" in changes:
            return "Ultrafast 출시·지원범위"
        return "속도·배치·가격 변화"
    return "추론 라우팅 변화"


def _fmt_value(value: object) -> str:
    if isinstance(value, bool):
        return "지원" if value else "미지원"
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:g}"
    if isinstance(value, int):
        return f"{value:,}"
    if value is None:
        return "확인 불가"
    return str(value)


def official_change_summary(name: str, old: dict, new: dict) -> str:
    labels = {
        "gpt_6_astra_supported": "GPT-6 Astra Ultrafast",
        "gpt_5_6_sol_preview": "GPT-5.6 Sol 미리보기",
        "gpt_6_1_sol_mentioned": "GPT-6.1 Sol Ultrafast 문서 언급",
        "service_tier_ultrafast": "Ultrafast 서비스 계층",
        "max_speed_x": "최대 속도 배수",
        "tier_1_3_tpm": "1~3단계 분당 토큰",
        "tier_4_tpm": "4단계 분당 토큰",
        "tier_5_tpm": "5단계 분당 토큰",
        "eu_regional_supported": "EU 지역 처리",
        "ultrafast_mentioned": "GPT-6.1 Sol Ultrafast",
        "fast_mode_mentioned": "GPT-6.1 Sol Fast",
        "input_usd_per_mtok": "입력 100만 토큰 가격",
        "cached_input_usd_per_mtok": "캐시 입력 100만 토큰 가격",
        "cache_write_usd_per_mtok": "캐시 쓰기 100만 토큰 가격",
        "output_usd_per_mtok": "출력 100만 토큰 가격",
        "fast_multiplier_x": "Fast 가격 배수",
        "batch_flex_discount_pct": "Batch·Flex 할인율",
        "context_window": "컨텍스트 창",
        "max_output_tokens": "최대 출력 토큰",
    }
    parts = []
    for key, before, after in semantic_changes(old, new):
        if key in {"kind", "us_data_residency", "eu_data_residency"}:
            continue
        label = labels.get(key, key)
        if key.endswith("_usd_per_mtok") and before is not None and after is not None:
            parts.append(label + " $" + _fmt_value(before) + "→$" + _fmt_value(after))
        elif key in {"max_speed_x", "fast_multiplier_x"}:
            parts.append(label + " " + _fmt_value(before) + "x→" + _fmt_value(after) + "x")
        elif key == "batch_flex_discount_pct":
            parts.append(label + " " + _fmt_value(before) + "%→" + _fmt_value(after) + "%")
        else:
            parts.append(label + " " + _fmt_value(before) + "→" + _fmt_value(after))
    if not parts:
        return f"{name} 공식 핵심 조건 변경"
    return f"{name}: " + " · ".join(parts[:4])


def advance_official_page_state(
    name: str,
    previous: dict | None,
    snapshot: dict,
    now: dt.datetime,
    *,
    rebaseline: bool = False,
) -> tuple[dict, bool, dict | None, dict | None]:
    previous = dict(previous or {})
    digest = str(snapshot.get("digest") or "")
    semantic = dict(snapshot.get("semantic") or {})
    url = str(snapshot.get("url") or "")

    if rebaseline or not previous.get("digest") or not previous.get("semantic"):
        return {
            "digest": digest,
            "semantic": semantic,
            "url": url,
            "updated_at": now.isoformat(),
            "candidate_digest": None,
            "candidate_semantic": None,
            "candidate_count": 0,
            "candidate_first_seen_at": None,
        }, False, None, None

    if name in IMMUTABLE_OFFICIAL_REFERENCE_PAGES:
        previous["url"] = url or previous.get("url")
        previous["candidate_digest"] = None
        previous["candidate_semantic"] = None
        previous["candidate_count"] = 0
        previous["candidate_first_seen_at"] = None
        return previous, False, None, None

    confirmed_digest = str(previous.get("digest") or "")
    confirmed_semantic = dict(previous.get("semantic") or {})
    if digest == confirmed_digest:
        previous["url"] = url or previous.get("url")
        previous["candidate_digest"] = None
        previous["candidate_semantic"] = None
        previous["candidate_count"] = 0
        previous["candidate_first_seen_at"] = None
        return previous, False, None, None

    if str(previous.get("candidate_digest") or "") == digest:
        count = int(previous.get("candidate_count") or 0) + 1
        first_seen = _parse_iso_utc(previous.get("candidate_first_seen_at")) or now
    else:
        count = 1
        first_seen = now

    previous["url"] = url or previous.get("url")
    previous["candidate_digest"] = digest
    previous["candidate_semantic"] = semantic
    previous["candidate_count"] = count
    previous["candidate_first_seen_at"] = first_seen.isoformat()

    age = max(0.0, (now - first_seen).total_seconds())
    if count >= OFFICIAL_CHANGE_CONFIRM_RUNS and age >= OFFICIAL_CHANGE_CONFIRM_SECONDS:
        previous["digest"] = digest
        previous["semantic"] = semantic
        previous["updated_at"] = now.isoformat()
        previous["candidate_digest"] = None
        previous["candidate_semantic"] = None
        previous["candidate_count"] = 0
        previous["candidate_first_seen_at"] = None
        return previous, True, confirmed_semantic, semantic

    return previous, False, None, None

def load_state() -> dict:
    if not STATE_PATH.exists():
        return {
            "initialized": False,
            "seen": {},
            "official_pages": {},
            "official_snapshot_schema_version": 0,
        }
    try:
        obj = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        obj.setdefault("initialized", False)
        obj.setdefault("seen", {})
        obj.setdefault("official_pages", {})
        obj.setdefault("official_snapshot_schema_version", 0)
        return obj
    except Exception:
        return {
            "initialized": False,
            "seen": {},
            "official_pages": {},
            "official_snapshot_schema_version": 0,
        }


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
    if category == "Synopsys FY27 가이던스 변경":
        return "FY27 매출 $11.15B 기준선에서 상향·하향이 발생하면 AI 설계 복잡도와 EDA 소비량이 실제 매출로 전환되는 속도가 바뀐 신호입니다."
    if category == "Synopsys 소비기반 과금 실제 도입":
        return "구독형 EDA에 사용량·소비기반 과금이 실제 고객 단가로 붙으면 AI 에이전트가 5~10배 더 많은 툴 실행을 유발할수록 Synopsys의 고객당 매출이 엔지니어 좌석 수보다 설계 연산량에 더 민감해질 수 있습니다."
    if category == "GPT-Synopsys 상용화·수익화":
        return "OpenAI와의 공동개발이 실제 고객 출시·사용권·수익배분으로 전환되면 EDA 도구 사용량 자체가 새로운 반복매출원이 되는지 확인할 수 있습니다."
    if category == "Synopsys 신규 하이퍼스케일러 계약":
        return "AWS 외 추가 하이퍼스케일러가 Synopsys IP·EDA를 채택하면 맞춤형 AI 칩 증가가 설계자동화와 IP 매출로 직접 연결되는 신호입니다."
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
    has_eda = any(any(SYNOPSYS_ID.search(f"{x.get('title','')} {x.get('description','')}") for x in cluster) for cluster in events)
    watch_name = "AI 반도체 설계·추론 가속기 Watch" if has_eda else "AI 추론 가속기·모델 라우팅 Watch"
    title = f"⚡ <b>{watch_name}</b> · 중요 변화 {len(events)}건"
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
        "<b>다음 확인</b>: Synopsys 소비기반 실제 단가·고객 채택률·FY27 가이던스 변경·GPT-Synopsys 상용출시·추가 하이퍼스케일러 계약 · 모델→가속기 확정 · Ultrafast 정식 출시/지원범위 · tokens/s · batch 크기 · 가격 · Cerebras 750MW 트랜치 가동 · 실제 live MW · 계약 증감·지연",
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
    prior_snapshot_schema = int(state.get("official_snapshot_schema_version") or 0)
    rebaseline_official_pages = prior_snapshot_schema != OFFICIAL_SNAPSHOT_SCHEMA_VERSION
    try:
        snapshots = official_page_snapshots()
        for name, snap in snapshots.items():
            previous = official_pages.get(name)
            page_state, should_alert, old_semantic, new_semantic = advance_official_page_state(
                name,
                previous,
                snap,
                now,
                rebaseline=rebaseline_official_pages,
            )
            official_pages[name] = page_state

            if should_alert and old_semantic is not None and new_semantic is not None:
                category = official_change_category(name, old_semantic, new_semantic)
                summary = official_change_summary(name, old_semantic, new_semantic)
                page_item = normalize({
                    "kind":"official_page",
                    "query":"confirmed semantic official page change",
                    "title":summary,
                    "description":json.dumps(new_semantic, ensure_ascii=False, sort_keys=True),
                    "source":"OpenAI",
                    "url":snap["url"],
                    "published_at":now.isoformat(),
                })
                page_item["category"] = category
                page_item["entity"] = "OpenAI 추론 인프라"
                new_items.append(page_item)
                print(f"ai_inference_route_official_change_confirmed={name} category={category}")

        if rebaseline_official_pages:
            print(
                f"ai_inference_route_official_pages_rebaselined=true "
                f"schema={OFFICIAL_SNAPSHOT_SCHEMA_VERSION}"
            )
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
        "official_snapshot_schema_version": OFFICIAL_SNAPSHOT_SCHEMA_VERSION,
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
        "# AI 반도체 설계·추론 가속기 Watch",
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
