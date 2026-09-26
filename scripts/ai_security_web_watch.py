#!/usr/bin/env python3
"""Broad AI security web watcher for Telegram alerts.

The watcher is deliberately event-driven:
- Search the live web via Google News RSS with multiple AI-security queries.
- Add CISA KEV as an official exploitation backstop.
- Keep only material AI-product / agent / tool / connector / sandbox events.
- Baseline silently on first run; alert only on genuinely new developments.
- Persist state only after the workflow confirms the Telegram outcome.

No LLM is used inside the workflow. The alert therefore separates facts visible
in source titles/snippets from interpretation and preserves the source links.
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
from collections import defaultdict
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
UTC = dt.timezone.utc
ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "out"
DATA.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)

STATE_PATH = DATA / "ai_security_web_watch_state.json"
PENDING_PATH = OUT / "ai_security_web_watch_pending_state.json"
ALERT_TITLE = OUT / "ai_security_web_watch_alert_title.txt"
ALERT_BODY = OUT / "ai_security_web_watch_alert.md"
STATUS_PATH = OUT / "ai_security_web_watch_status.md"
CONFIRMED_PATH = OUT / "ai_security_web_watch_telegram_confirmed.json"

GOOGLE_NEWS = "https://news.google.com/rss/search"
CISA_KEV = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
USER_AGENT = "Mozilla/5.0 khs-ai-security-web-watch/1.0"
MAX_AGE_HOURS = 96
SEEN_RETENTION_DAYS = 35
MAX_ALERT_ITEMS = 6

NEWS_QUERIES = [
    '"AI agent" security vulnerability exploit "data leak" "prompt injection"',
    '"Meta Muse" security vulnerability exploit privacy patch',
    '(OpenAI OR ChatGPT OR Codex) security vulnerability exploit "data leak"',
    '(Anthropic OR Claude) security vulnerability exploit "prompt injection"',
    '(Gemini OR "Google AI") security vulnerability exploit "data leak"',
    '(Copilot OR "Microsoft AI") security vulnerability exploit agent',
    '("Model Context Protocol" OR MCP) security vulnerability exploit',
    '(Grok OR xAI OR Bedrock) AI security vulnerability exploit',
    '("AI agent" OR agentic) "sandbox escape" OR "unauthorized access" OR credential',
    'LLM "supply chain" vulnerability exploit security',
    '("AI agent" OR agentic OR LLM) misalignment "third party" OR "third-party" OR "agent spam"',
    '("AI agent" OR agentic) "bypassed security controls" OR "unintended internet access" OR "unauthorized communication"',
    '(OpenAI OR Anthropic OR Google OR Meta) agent misalignment external service unintended behavior',
    '"rogue agent" AI OpenAI Anthropic Google Meta security',
    '"rogue agents" ChatGPT user images third party',
    '"AI agent" "third-party" impact security controls',
    '"AI agent" "undesirable behavior" OR "unintended behavior"',
    'OpenAI "Hugging Face" agent incident misalignment',
]

AI_TERMS = (
    "ai agent", "artificial intelligence", "chatgpt", "openai", "codex",
    "claude", "anthropic", "gemini", "google ai", "copilot", "microsoft ai",
    "meta muse", "muse ai", "grok", "xai", "bedrock", "model context protocol",
    " mcp ", "llm", "language model", "agentic", "github copilot", "cursor",
    "windsurf",
)

SECURITY_TERMS = (
    "vulnerability", "security flaw", "exploit", "zero-day", "zero day",
    "data leak", "data exposure", "privacy flaw", "prompt injection",
    "sandbox", "remote code execution", " rce", "authentication bypass",
    "authorization bypass", "credential", "unauthorized access", "hijack",
    "malicious", "hotfix", "patched", "patches", "security warning",
    "risk warning", "cross-tenant", "exfiltrat", "supply chain", "cve-",
    "arbitrary code", "take control", "stole data", "leaked data",
    "misalignment", "misaligned", "agent spam", "bypassed security controls",
    "bypass security controls", "improper activity", "undesirable behavior",
    "unintended internet access", "unauthorized communication",
    "third-party impact", "third party impact", "outside intended scope",
    "rogue agent", "rogue agents", "rogue activity", "leaked images",
    "improper activity", "unintended behavior", "unexpected behavior",
    "broke containment", "security controls", "third-party", "third party",
)

HARD_SECURITY_TERMS = (
    "remote code execution", " rce", "sandbox escape", "cross-tenant",
    "credential theft", "steal credentials", "stole credentials",
    "actively exploited", "exploited in the wild", "arbitrary code",
    "unauthorized access", "data exfiltration", "exfiltrat", "zero-day",
    "zero day", "agent hijack", "take control",
    "bypassed security controls", "unintended internet access",
    "unauthorized communication",
)

TRUSTED_SOURCE_HINTS = (
    "reuters", "the information", "associated press", "ap news",
    "the verge", "wired", "ars technica", "techcrunch", "fortune",
    "the guardian", "guardian", "cnbc", "bbc", "financial times",
    "bloomberg", "the hacker news", "bleepingcomputer", "securityweek",
    "dark reading", "therecord",
    "the record", "krebs", "mit technology review",
    "cisa", "nist", "cert", "project zero", "google security",
    "microsoft security", "microsoft", "meta", "openai", "anthropic",
    "google", "amazon web services", "aws", "apple", "github",
    "palo alto", "unit 42", "wiz", "trail of bits", "cloudflare",
    "snyk", "mandiant",
)

OFFICIAL_SOURCE_HINTS = (
    "cisa", "nist", "cert", "openai", "anthropic", "meta", "google",
    "microsoft", "amazon web services", "aws", "apple", "github",
    "project zero", "google security", "microsoft security",
)

VENDOR_PATTERNS = [
    ("Meta", ("meta muse", "muse ai", " meta ")),
    ("OpenAI", ("openai", "chatgpt", "codex")),
    ("Anthropic", ("anthropic", "claude")),
    ("Google", ("gemini", "google ai", "google deepmind")),
    ("Microsoft", ("copilot", "microsoft ai", "azure ai")),
    ("xAI", (" xai", "grok")),
    ("Amazon/AWS", ("bedrock", "amazon web services", "aws ai")),
    ("GitHub", ("github copilot", "github")),
    ("AI 개발도구", ("cursor", "windsurf")),
    ("MCP 생태계", ("model context protocol", " mcp ")),
]

CATEGORY_PATTERNS = [
    ("가상환경·샌드박스", (
        "sandbox escape", "sandbox", "virtual machine", "secure vm", "vm escape",
        "remote code execution", "arbitrary code", "code execution",
    )),
    ("데이터·개인정보", (
        "data leak", "data exposure", "privacy", "sensitive data", "email",
        "files", "cross-tenant", "exfiltrat", "leaked data", "stole data",
    )),
    ("프롬프트 주입·도구권한", (
        "prompt injection", "indirect prompt", "tool abuse", "connector",
        "plugin", "agent hijack", "model context protocol", " mcp ",
        "unauthorized action", "take control",
    )),
    ("인증·자격증명", (
        "authentication bypass", "authorization bypass", "credential",
        "api key", "oauth", "token theft", "secret",
    )),
    ("공급망", (
        "supply chain", "dependency", "package", "poisoned model",
        "model tampering", "malicious model",
    )),
    ("에이전트 비정렬·제3자 영향", (
        "misalignment", "misaligned", "agent spam", "undesirable behavior",
        "improper activity", "bypassed security controls",
        "unintended internet access", "unauthorized communication",
        "third-party impact", "third party impact", "outside intended scope",
    )),
]

STOPWORDS = {
    "the", "a", "an", "of", "to", "for", "and", "or", "in", "on", "with",
    "from", "by", "at", "as", "is", "are", "was", "were", "that", "this",
    "ai", "security", "new", "says", "after", "over", "could", "can",
    "its", "their", "your", "users", "user",
}


def fetch_bytes(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml,application/xml,application/json,text/html,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def strip_html(value: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", value or ""))
    return " ".join(text.replace("\xa0", " ").split())


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
    params = {
        "q": query,
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    }
    return GOOGLE_NEWS + "?" + urllib.parse.urlencode(params)


def parse_google_news(query: str, now: dt.datetime) -> list[dict]:
    data = fetch_bytes(google_news_url(query))
    root = ET.fromstring(data)
    items = []
    for node in root.findall(".//item"):
        title = strip_html(node.findtext("title") or "")
        link = (node.findtext("link") or "").strip()
        desc = strip_html(node.findtext("description") or "")
        source_node = node.find("source")
        source = strip_html(source_node.text if source_node is not None and source_node.text else "")
        published = parse_pubdate(node.findtext("pubDate"))
        if not title or not link:
            continue
        if published and now - published > dt.timedelta(hours=MAX_AGE_HOURS):
            continue
        items.append({
            "kind": "news",
            "query": query,
            "title": title,
            "description": desc,
            "source": source or "Google News 수집원",
            "url": link,
            "published_at": published.isoformat() if published else None,
        })
    return items


def parse_cisa_kev(now: dt.datetime) -> list[dict]:
    payload = json.loads(fetch_bytes(CISA_KEV).decode("utf-8"))
    out = []
    cutoff = now.date() - dt.timedelta(days=7)
    for row in payload.get("vulnerabilities") or []:
        added_text = str(row.get("dateAdded") or "")
        try:
            added = dt.date.fromisoformat(added_text)
        except Exception:
            continue
        if added < cutoff:
            continue
        title = " ".join([
            str(row.get("vendorProject") or ""),
            str(row.get("product") or ""),
            str(row.get("vulnerabilityName") or ""),
        ]).strip()
        desc = " ".join([
            str(row.get("shortDescription") or ""),
            str(row.get("requiredAction") or ""),
            str(row.get("cveID") or ""),
        ]).strip()
        combined = f" {title} {desc} ".lower()
        if not is_ai_related(combined):
            continue
        out.append({
            "kind": "official",
            "query": "CISA KEV",
            "title": title,
            "description": desc,
            "source": "CISA",
            "url": CISA_KEV,
            "published_at": dt.datetime.combine(added, dt.time(12, 0), tzinfo=UTC).isoformat(),
        })
    return out


def is_ai_related(text: str) -> bool:
    low = f" {text.lower()} "
    return any(term in low for term in AI_TERMS)


def is_security_related(text: str) -> bool:
    low = f" {text.lower()} "
    return any(term in low for term in SECURITY_TERMS)


def source_trusted(source: str) -> bool:
    low = source.lower()
    return any(hint in low for hint in TRUSTED_SOURCE_HINTS)


def source_official(source: str) -> bool:
    low = source.lower()
    return any(hint in low for hint in OFFICIAL_SOURCE_HINTS)


def detect_vendor(text: str) -> str:
    low = f" {text.lower()} "
    for vendor, patterns in VENDOR_PATTERNS:
        if any(p in low for p in patterns):
            return vendor
    return "AI 생태계"


def detect_category(text: str) -> str:
    low = f" {text.lower()} "
    scores = []
    for label, patterns in CATEGORY_PATTERNS:
        score = sum(1 for p in patterns if p in low)
        if score:
            scores.append((score, label))
    if scores:
        scores.sort(reverse=True)
        return scores[0][1]
    return "취약점·패치"


def severity(text: str) -> tuple[int, str]:
    low = f" {text.lower()} "
    critical = (
        "actively exploited", "exploited in the wild", "sandbox escape",
        "remote code execution", "arbitrary code", "cross-tenant",
        "data exfiltration", "credential theft", "take control",
    )
    high = (
        "zero-day", "zero day", "exploit", "data leak", "data exposure",
        "unauthorized access", "prompt injection", "agent hijack",
        "security flaw", "vulnerability", "hotfix", "bypassed security controls",
        "unintended internet access", "unauthorized communication", "misaligned",
        "misalignment", "agent spam", "rogue agent", "rogue agents",
        "rogue activity", "leaked images", "improper activity",
        "undesirable behavior", "unintended behavior", "broke containment",
    )
    if any(x in low for x in critical):
        return 3, "긴급"
    if any(x in low for x in high):
        return 2, "높음"
    return 1, "주의"


def material(item: dict) -> bool:
    combined = f" {item.get('title','')} {item.get('description','')} "
    low = combined.lower()
    if not is_ai_related(low) or not is_security_related(low):
        return False

    # Pure model-behavior debates and generic jailbreak coverage are not enough.
    if "jailbreak" in low and not any(x in low for x in HARD_SECURITY_TERMS):
        if not any(x in low for x in ("data leak", "credential", "tool", "connector", "sandbox", "prompt injection")):
            return False

    sev, _ = severity(low)
    if item.get("kind") == "official":
        return True
    if not source_trusted(item.get("source", "")):
        return False
    if sev >= 2:
        return True

    # Medium-severity items are kept only when they mention a concrete patch,
    # warning, privacy exposure, or tool/permission boundary.
    return any(x in low for x in (
        "patched", "patches", "hotfix", "security warning", "risk warning",
        "privacy", "connector", "plugin", "tool", "secure vm", "virtual machine",
        "misalignment", "misaligned", "agent spam", "bypassed security controls",
        "unintended internet access", "unauthorized communication",
        "third-party impact", "third party impact", "undesirable behavior",
        "improper activity", "rogue agent", "rogue agents", "rogue activity",
        "leaked images", "unintended behavior", "broke containment",
    ))


def fingerprint(item: dict) -> str:
    raw = "|".join([
        item.get("url", ""),
        item.get("title", ""),
        item.get("source", ""),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def token_set(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9][a-z0-9+._-]{2,}", text.lower())
    return {w for w in words if w not in STOPWORDS and not w.isdigit()}


def similarity(a: str, b: str) -> float:
    aa, bb = token_set(a), token_set(b)
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / len(aa | bb)


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"initialized": False, "seen": {}}
    try:
        value = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            value.setdefault("initialized", False)
            value.setdefault("seen", {})
            return value
    except Exception:
        pass
    return {"initialized": False, "seen": {}}


def save_json(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def normalize_item(item: dict) -> dict:
    combined = f"{item.get('title','')} {item.get('description','')}"
    sev_num, sev_label = severity(combined)
    out = dict(item)
    out["fingerprint"] = fingerprint(item)
    out["vendor"] = detect_vendor(combined)
    out["category"] = detect_category(combined)
    out["severity"] = sev_num
    out["severity_label"] = sev_label
    out["official"] = source_official(item.get("source", "")) or item.get("kind") == "official"
    return out


def previously_similar(item: dict, seen: dict, now: dt.datetime) -> bool:
    pub = item.get("published_at")
    for entry in seen.values():
        if entry.get("vendor") != item.get("vendor") or entry.get("category") != item.get("category"):
            continue
        old_time = entry.get("published_at") or entry.get("first_seen_at")
        try:
            old_dt = dt.datetime.fromisoformat(str(old_time).replace("Z", "+00:00")).astimezone(UTC)
        except Exception:
            old_dt = now - dt.timedelta(days=1)
        if abs((now - old_dt).total_seconds()) > 7 * 86400:
            continue
        if similarity(item.get("title", ""), entry.get("title", "")) >= 0.50:
            return True
    return False


def event_token_set(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9][a-z0-9+._-]{2,}", text.lower())
    normalized = set()
    replacements = {
        "agents": "agent", "users": "user", "images": "image",
        "leaked": "leak", "leaks": "leak", "leaking": "leak",
        "activities": "activity", "impacts": "impact",
        "vulnerabilities": "vulnerability", "patches": "patch",
    }
    drop = STOPWORDS | {
        "openai", "anthropic", "google", "meta", "microsoft", "amazon",
        "agent", "agents", "security", "latest", "exclusive", "reportedly",
        "report", "reports", "says", "said",
    }
    for word in words:
        word = replacements.get(word, word)
        if word not in drop and not word.isdigit():
            normalized.add(word)
    return normalized


def same_event(a: dict, b: dict) -> bool:
    if a.get("vendor") != b.get("vendor"):
        return False
    aa = event_token_set(f"{a.get('title','')} {a.get('description','')}")
    bb = event_token_set(f"{b.get('title','')} {b.get('description','')}")
    if not aa or not bb:
        return False
    overlap = aa & bb
    score = len(overlap) / len(aa | bb)
    if score >= 0.20:
        return True
    strong = {"leak", "image", "activity", "misalignment", "rogue", "medicare",
              "sandbox", "credential", "prompt", "injection", "hugging", "face"}
    return len(overlap & strong) >= 2


def cluster_alert_events(items: list[dict]) -> list[list[dict]]:
    ordered = sorted(
        items,
        key=lambda x: (x.get("severity", 0), bool(x.get("official")), x.get("published_at") or ""),
        reverse=True,
    )
    clusters: list[list[dict]] = []
    for item in ordered:
        placed = False
        for cluster in clusters:
            if any(same_event(item, existing) for existing in cluster):
                cluster.append(item)
                placed = True
                break
        if not placed:
            clusters.append([item])
    return clusters[:MAX_ALERT_ITEMS]


def source_label(source: str) -> str:
    low = source.lower()
    mapping = (
        ("reuters", "Reuters"),
        ("fortune", "Fortune"),
        ("guardian", "Guardian"),
        ("the verge", "The Verge"),
        ("wired", "WIRED"),
        ("ars technica", "Ars Technica"),
        ("techcrunch", "TechCrunch"),
        ("bleepingcomputer", "BleepingComputer"),
        ("securityweek", "SecurityWeek"),
        ("cisa", "CISA"),
        ("openai", "OpenAI"),
        ("anthropic", "Anthropic"),
        ("microsoft", "Microsoft"),
        ("google", "Google"),
        ("meta", "Meta"),
        ("github", "GitHub"),
    )
    for needle, label in mapping:
        if needle in low:
            return label
    value = re.sub(r"^www\.", "", source.strip())
    return value[:26] or "원문"


def incident_fact(item: dict) -> str | None:
    text = f" {item.get('title','')} {item.get('description','')} ".lower()
    if "53" in text and "image" in text:
        return "ChatGPT 사용자 이미지 53건 외부 업로드"
    if ("1m" in text or "million" in text) and ("link" in text or "url" in text):
        return "단축 URL 약 100만 개 활용 정황"
    if "medicare" in text:
        return "호주 Medicare 시스템 비인가 접근"
    if "hugging face" in text and ("misalign" in text or "rogue" in text or "incident" in text):
        return "Hugging Face 사고 관련 에이전트 비정렬 활동"
    if "user data leak" in text or ("data leak" in text and "user" in text):
        return "사용자 데이터 유출 사례 확인"
    if "sandbox escape" in text:
        return "가상환경·샌드박스 격리 우회"
    if "remote code execution" in text or " rce" in text:
        return "원격 코드 실행 가능성"
    if "prompt injection" in text:
        return "프롬프트 주입을 통한 도구·권한 오용 위험"
    if "credential" in text and ("steal" in text or "theft" in text or "leak" in text):
        return "자격증명 탈취·노출 위험"
    if "bypassed security controls" in text or "bypass security controls" in text:
        return "보안 통제 우회 행동 확인"
    if "misalignment" in text or "misaligned" in text or "rogue agent" in text:
        return "비정렬 에이전트의 의도하지 않은 외부 행동 확인"
    return None


def event_heading(cluster: list[dict]) -> str:
    rep = cluster[0]
    categories = []
    for item in cluster:
        cat = item.get("category") or "중요 보안 변화"
        if cat not in categories:
            categories.append(cat)
    cat_text = " · ".join(categories[:2])
    return f"{rep['vendor']} · {cat_text}"


def event_impact(cluster: list[dict]) -> str:
    cats = " ".join(item.get("category", "") for item in cluster)
    if "데이터·개인정보" in cats:
        return "사용자 데이터와 외부 시스템 접근 범위 확대 여부가 핵심입니다."
    if "에이전트 비정렬" in cats:
        return "목표 달성을 위해 보안통제를 우회하는 자율 행동이 핵심 위험입니다."
    if "가상환경·샌드박스" in cats:
        return "격리 실패가 실제 외부 시스템 접근으로 이어지는지 확인이 필요합니다."
    if "프롬프트 주입·도구권한" in cats:
        return "에이전트가 연결된 도구·계정 권한을 오용할 가능성이 핵심입니다."
    if "인증·자격증명" in cats:
        return "계정·토큰·API 키의 권한 확대로 이어지는지 확인이 필요합니다."
    return "실제 악용·영향 범위·패치 여부가 다음 핵심 확인 지점입니다."


def build_alert(events: list[list[dict]], now: dt.datetime) -> tuple[str, str]:
    highest = max(item["severity"] for cluster in events for item in cluster)
    icon = {3: "🚨", 2: "⚠️", 1: "🔎"}[highest]
    title = f"{icon} <b>AI 보안 웹감시</b> · 신규 중요 변화 {len(events)}건"

    lines = [f"<i>{now.astimezone(KST).strftime('%m/%d %H:%M KST')}</i>"]
    for idx, cluster in enumerate(events, 1):
        rep = cluster[0]
        severity_label = rep["severity_label"]
        lines += ["", f"<b>{idx}. [{html.escape(severity_label)}] {html.escape(event_heading(cluster))}</b>"]

        facts: list[str] = []
        for item in cluster:
            fact = incident_fact(item)
            if fact and fact not in facts:
                facts.append(fact)
        if not facts:
            headline = clean_snippet(rep.get("title", ""), limit=110)
            if headline:
                facts.append(headline)
        for fact in facts[:3]:
            lines.append(f"• {html.escape(fact)}")

        unique_sources = []
        official = False
        for item in cluster:
            label = source_label(item.get("source", ""))
            if label not in [x[0] for x in unique_sources]:
                unique_sources.append((label, item.get("url", "")))
            official = official or bool(item.get("official"))

        if official:
            evidence = "공식 원천 포함"
        elif len(unique_sources) >= 2:
            evidence = f"복수 출처 {len(unique_sources)}곳"
        else:
            evidence = "신뢰보도 1건·추가 확인 필요"

        lines.append(f"• <b>판정</b>: {html.escape(event_impact(cluster))}")
        lines.append(f"• <b>확인</b>: {html.escape(evidence)}")

        links = []
        for label, url in unique_sources[:4]:
            if url:
                links.append(
                    f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'
                )
        if links:
            lines.append("🔗 " + " · ".join(links))

    lines += [
        "",
        "<b>다음 확인</b>: 실제 악용 · 영향 범위 · 추가 피해 · 패치/완화책",
    ]
    return title, "\n".join(lines)


def prune_seen(seen: dict, now: dt.datetime) -> dict:
    cutoff = now - dt.timedelta(days=SEEN_RETENTION_DAYS)
    kept = {}
    for key, value in seen.items():
        stamp = value.get("first_seen_at") or value.get("published_at")
        try:
            when = dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).astimezone(UTC)
        except Exception:
            when = now
        if when >= cutoff:
            kept[key] = value
    return kept


def main() -> int:
    for path in (ALERT_TITLE, ALERT_BODY, CONFIRMED_PATH):
        path.unlink(missing_ok=True)

    now = dt.datetime.now(UTC)
    state = load_state()
    errors: list[str] = []
    raw_items: list[dict] = []

    for query in NEWS_QUERIES:
        try:
            raw_items.extend(parse_google_news(query, now))
        except Exception as exc:
            errors.append(f"Google News RSS 실패: {query[:55]}… / {type(exc).__name__}: {exc}")

    try:
        raw_items.extend(parse_cisa_kev(now))
    except Exception as exc:
        errors.append(f"CISA KEV 실패: {type(exc).__name__}: {exc}")

    dedup: dict[str, dict] = {}
    for raw in raw_items:
        item = normalize_item(raw)
        if material(item):
            dedup[item["fingerprint"]] = item

    current = sorted(
        dedup.values(),
        key=lambda x: (x.get("severity", 0), x.get("published_at") or ""),
        reverse=True,
    )

    seen = prune_seen(dict(state.get("seen") or {}), now)
    new_items: list[dict] = []
    for item in current:
        fp = item["fingerprint"]
        if fp in seen:
            continue
        if previously_similar(item, seen, now):
            continue
        new_items.append(item)

    # Silent baseline on the first successful collection to prevent retroactive spam.
    baseline = not bool(state.get("initialized"))
    if baseline:
        new_items = []

    # Add all material current items to the pending seen set. This state is only
    # committed by the workflow after a successful/no-alert outcome.
    first_seen = now.isoformat()
    for item in current:
        fp = item["fingerprint"]
        seen.setdefault(fp, {
            "title": item["title"],
            "source": item["source"],
            "url": item["url"],
            "vendor": item["vendor"],
            "category": item["category"],
            "severity": item["severity"],
            "published_at": item.get("published_at"),
            "first_seen_at": first_seen,
        })

    pending = {
        "initialized": True,
        "updated_at_kst": now.astimezone(KST).isoformat(timespec="seconds"),
        "seen": seen,
        "last_collection": {
            "raw_items": len(raw_items),
            "material_items": len(current),
            "new_material_items": len(new_items),
            "errors": errors,
        },
    }
    save_json(PENDING_PATH, pending)

    alert_events = cluster_alert_events(new_items)

    if alert_events:
        title, body = build_alert(alert_events, now)
        ALERT_TITLE.write_text(title + "\n", encoding="utf-8")
        ALERT_BODY.write_text(body.rstrip() + "\n", encoding="utf-8")

    status = [
        "# AI 보안 웹감시",
        "",
        f"- 조회시각: {now.astimezone(KST).strftime('%Y-%m-%d %H:%M:%S KST')}",
        f"- 최초 기준선 생성: {'예' if baseline else '아니오'}",
        f"- 웹 수집 원문: {len(raw_items)}건",
        f"- 중요 필터 통과: {len(current)}건",
        f"- 신규 중요 기사: {len(new_items)}건",
        f"- 신규 중요 사건: {len(alert_events)}건",
        f"- 수집 오류: {len(errors)}건",
    ]
    if errors:
        status += ["", "## 수집 오류"] + [f"- {e}" for e in errors[:10]]
    STATUS_PATH.write_text("\n".join(status) + "\n", encoding="utf-8")

    print(
        f"ai_security_baseline={str(baseline).lower()} "
        f"material={len(current)} new_articles={len(new_items)} new_events={len(alert_events)} errors={len(errors)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
