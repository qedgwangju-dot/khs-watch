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
    '(OpenAI OR Anthropic OR Google OR Meta) "Critical cybersecurity capability" OR "critical cyber capability"',
    '(OpenAI OR Anthropic OR Google OR Meta) "Preparedness Framework" cybersecurity threshold',
    '("AI model" OR "frontier model") cybersecurity capability threshold zero-day sandbox exploit',
    '(OpenAI OR Anthropic OR Google OR Meta) system card cybersecurity "High" "Critical"',
    '(OpenAI OR Anthropic) "tens of thousands" security incidents agent sandbox',
    '(OpenAI OR Anthropic) model behavior guardrail sandbox monitoring unusual problematic',
    '(OpenAI OR Anthropic OR Google OR Meta) "training paused" OR "training resumed" OR "inference paused" OR "evaluation paused"',
    '(OpenAI OR Anthropic OR Google OR Meta) "tool use" paused resumed safety security',
    '("Joint Commitment on Frontier Responsibilities" OR "White House Accord on Super Intelligence") security audit failure violation',
    '(OpenAI OR Anthropic OR Google OR Meta OR xAI OR NVIDIA) external audit security control failure frontier AI',
    '(OpenAI OR Anthropic OR Google OR Meta OR xAI OR NVIDIA) board committee oversight ordered pause training deployment security',
    'frontier AI independent auditor found sandbox unauthorized access control failure',
    '(OpenAI OR Anthropic) "time to detection" OR "run was killed" OR "human reviewer" security agent',
    '(OpenAI OR Anthropic) unauthorized access incidents transcripts evaluations rate percentage',
    '(NVIDIA OpenShell OR OpenShell OR NemoClaw) security vulnerability sandbox escape policy bypass credential',
    '(NVIDIA OpenShell OR OpenShell) data exfiltration network policy bypass unauthorized access',
    '("agent safety runtime" OR "secure agent runtime") vulnerability sandbox escape credential leak',
    '(NVIDIA OpenShell OR OpenShell) "security release" OR "critical reliability update" OR CVE',
    '(OpenShell OR Sentry OR BlueField-4) policy bypass sandbox escape credential exfiltration',
    '(OpenAI OR Anthropic OR Google OR Meta) model release cancelled delayed postponed restricted rollout safety evaluation',
    '(OpenAI OR Anthropic OR Google OR Meta) deployment blocked safety gate failed alignment evaluation',
    '(OpenAI OR Anthropic OR Google OR Meta) limited release restricted deployment safeguards model',
    '(OpenAI OR Anthropic) "blocking alignment evaluation" failed passed deployment',
    '(OpenAI OR Anthropic OR Google OR Meta) "Safety Case" frontier training reinforcement learning',
    '(OpenAI OR Anthropic OR Google OR Meta) "eval awareness" OR metagaming monitoring safety',
    '(OpenAI OR Anthropic OR Google OR Meta) monitorability threshold automatic stop fail-closed training',
    '(OpenAI OR Anthropic OR Google OR Meta) regression test postmortem misalignment incident',
    '(OpenAI OR Anthropic OR Google OR Meta) tool-use training evaluation inference resumed paused frontier model',
    '(Anthropic OR Claude) (Mythos OR "Cyber Verification Program" OR Glasswing) cyber capability vulnerability security access',
    '"Jamie Dimon" (Mythos OR Anthropic) cyber risk bank financial "10-fold"',
    '(JPMorgan OR Citi OR Goldman OR bank OR "critical infrastructure") (Mythos OR Anthropic) AI cyber risk',
    'Anthropic Mythos vulnerabilities critical high severity 129000 33000 5500',
]

AI_TERMS = (
    "ai agent", "artificial intelligence", "chatgpt", "openai", "codex",
    "claude", "anthropic", "gemini", "google ai", "copilot", "microsoft ai",
    "meta muse", "muse ai", "grok", "xai", "bedrock", "model context protocol",
    " mcp ", "llm", "language model", "agentic", "github copilot", "cursor",
    "windsurf", "openshell", "nemoclaw", "agent safety runtime",
    "secure agent runtime", "nvidia agent toolkit",
    "frontier ai", "frontier model", "super intelligence", "superintelligence",
    "joint commitment on frontier responsibilities", "white house accord on super intelligence",
    "mythos", "claude mythos", "claude fable", "cyber verification program",
    "project glasswing",
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
    "critical cybersecurity capability", "critical cyber capability",
    "preparedness framework", "cybersecurity capability threshold",
    "critical threshold", "high threshold", "system card",
    "openshell", "agent safety runtime", "secure agent runtime",
    "security release", "critical reliability update",
    "policy bypass", "sandbox policy bypass", "network policy bypass",
    "credential leak", "secret exposure",
    "release cancelled", "release canceled", "launch cancelled", "launch canceled",
    "release delayed", "launch delayed", "release postponed", "launch postponed",
    "deployment blocked", "blocked deployment", "restricted rollout",
    "restricted deployment", "limited release", "limited rollout",
    "safety gate failed", "failed safety evaluation", "failed alignment evaluation",
    "blocking alignment evaluation", "deployment restriction",
    "training paused", "training resumed", "evaluation paused", "evaluation resumed",
    "inference paused", "inference resumed", "tool use paused", "tool-use paused",
    "tool use resumed", "tool-use resumed", "run was killed", "human reviewer",
    "time to detection", "response time", "restart training", "resume training",
    "safety case", "eval awareness", "metagaming", "monitorability",
    "audit finding", "audit findings", "external audit", "independent audit",
    "control failure", "failed control", "security control failure",
    "accord violation", "noncompliance", "non-compliance",
    "board ordered pause", "oversight ordered pause", "committee ordered pause",
    "fail-closed", "fail closed", "automatic stop", "auto-stop", "auto stop",
    "regression test", "postmortem", "post-mortem", "root cause",
    "senior leadership veto", "training veto",
    "mythos", "cyber verification program", "project glasswing",
    "reduced blocking classifiers", "specialized access", "red team tier",
    "defense tier", "financial sector", "critical infrastructure",
    "10-fold", "tenfold", "ten-fold", "cyber risk",
    "verified software vulnerabilities", "critical or high severity",
)

HARD_SECURITY_TERMS = (
    "remote code execution", " rce", "sandbox escape", "cross-tenant",
    "credential theft", "steal credentials", "stole credentials",
    "actively exploited", "exploited in the wild", "arbitrary code",
    "unauthorized access", "data exfiltration", "exfiltrat", "zero-day",
    "zero day", "agent hijack", "take control",
    "bypassed security controls", "unintended internet access",
    "unauthorized communication", "critical cybersecurity capability",
    "critical cyber capability", "critical threshold",
    "training paused", "inference paused", "evaluation paused", "tool-use paused",
    "release cancelled", "release canceled", "launch cancelled", "launch canceled",
    "deployment blocked", "safety gate failed", "failed alignment evaluation",
    "tool-use paused", "tool use paused", "tool-use resumed", "tool use resumed",
    "audit found unauthorized access", "audit found control failure",
    "external audit found", "independent audit found",
    "board ordered pause", "oversight ordered pause",
    "mythos", "reduced blocking classifiers", "critical or high severity",
    "10-fold", "tenfold", "ten-fold",
    "fail-closed", "fail closed", "automatic stop", "auto-stop",
)

TRUSTED_SOURCE_HINTS = (
    "reuters", "the information", "axios", "associated press", "ap news",
    "yonhap", "연합뉴스", "chosunbiz", "조선비즈",
    "the verge", "wired", "ars technica", "techcrunch", "fortune",
    "the guardian", "guardian", "cnbc", "bbc", "financial times",
    "bloomberg", "the hacker news", "bleepingcomputer", "securityweek",
    "dark reading", "therecord",
    "the record", "krebs", "mit technology review",
    "cisa", "nist", "cert", "project zero", "google security",
    "microsoft security", "microsoft", "meta", "openai", "anthropic",
    "google", "amazon web services", "aws", "apple", "github",
    "palo alto", "unit 42", "wiz", "trail of bits", "cloudflare",
    "snyk", "mandiant", "nvidia", "openshell",
    "associated press", "ap news", "guardian", "cbs news", "white house", "whitehouse.gov",
)

OFFICIAL_SOURCE_HINTS = (
    "cisa", "nist", "cert", "openai", "anthropic", "meta", "google",
    "microsoft", "amazon web services", "aws", "apple", "github",
    "project zero", "google security", "microsoft security", "nvidia", "openshell",
    "white house", "whitehouse.gov",
)

DIRECT_OFFICIAL_PAGES = [
    ("OpenAI Alignment", "https://alignment.openai.com/", r'href=["\\\']([^"\\\']*/misalignment-reports/[^"\\\']+)["\\\']'),
    ("Anthropic Research", "https://www.anthropic.com/research", r'href=["\\\']([^"\\\']*/research/[^"\\\']+)["\\\']'),
    ("Anthropic News", "https://www.anthropic.com/news", r'href=["\\\']([^"\\\']*/(?:news/[^"\\\']+|claude-fable-and-mythos-5-1))["\\\']'),
]

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
    ("NVIDIA/OpenShell", ("nvidia openshell", "openshell", "nemoclaw")),
]

CATEGORY_PATTERNS = [
    ("모델 비의도적 외부접근·사후시정", (
        "investigating unintended model actions", "unintended model actions",
        "unintended use of government systems", "submitted forms it should not",
        "external government website actions",
    )),
    ("금융·핵심인프라 AI 사이버 위험 경보", (
        "jamie dimon", "jpmorgan", "financial sector", "bank", "banks",
        "critical infrastructure", "10-fold", "tenfold", "ten-fold",
        "biggest threat", "cyber risk",
    )),
    ("프런티어 모델 사이버 역량·접근 확대", (
        "claude mythos", "mythos", "cyber verification program",
        "project glasswing", "reduced blocking classifiers",
        "specialized access", "red team tier", "defense tier",
    )),
    ("대규모 취약점 발굴·검증", (
        "verified software vulnerabilities", "critical or high severity",
        "129,000", "129000", "33,000", "33000", "5,500", "5500",
        "vulnerabilities discovered", "vulnerabilities identified",
    )),
    ("공동서약·외부감사 보안실패", (
        "joint commitment on frontier responsibilities",
        "white house accord on super intelligence",
        "external audit", "independent audit", "audit finding", "audit findings",
        "control failure", "failed control", "security control failure",
        "accord violation", "noncompliance", "non-compliance",
    )),
    ("이사회·감독기구 중단명령", (
        "board ordered pause", "oversight ordered pause", "committee ordered pause",
        "board committee", "oversight committee", "independent board",
    )),
    ("출시 게이트·배포 제한", (
        "release cancelled", "release canceled", "launch cancelled", "launch canceled",
        "release delayed", "launch delayed", "release postponed", "launch postponed",
        "deployment blocked", "blocked deployment", "restricted rollout",
        "restricted deployment", "limited release", "limited rollout",
        "safety gate failed", "failed safety evaluation", "failed alignment evaluation",
        "blocking alignment evaluation", "deployment restriction",
    )),
    ("Safety Case·학습 승인 게이트", (
        "safety case", "training veto", "senior leadership veto",
        "fail-closed", "fail closed", "automatic stop", "auto-stop", "auto stop",
        "monitorability threshold",
    )),
    ("평가 인식·모니터 회피", (
        "eval awareness", "evaluation awareness", "metagaming",
        "monitor avoidance", "monitor evasion", "aware of being evaluated",
    )),
    ("사고 사후분석·회귀검사", (
        "regression test", "postmortem", "post-mortem", "root cause",
        "incident review", "lessons learned",
    )),
    ("에이전트 안전 런타임 실패", (
        "openshell", "agent safety runtime", "secure agent runtime",
        "sandbox policy bypass", "network policy bypass", "policy bypass",
        "credential leak", "secret exposure", "runtime escape",
    )),
    ("모델 운영중단·재개", (
        "training paused", "training resumed", "evaluation paused", "evaluation resumed",
        "inference paused", "inference resumed", "tool use paused", "tool-use paused",
        "tool use resumed", "tool-use resumed", "restart training", "resume training",
        "run was killed",
    )),
    ("모델 사이버 능력 임계치", (
        "critical cybersecurity capability", "critical cyber capability",
        "cybersecurity capability threshold", "preparedness framework",
        "critical threshold", "high threshold", "system card",
    )),
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


def parse_direct_official_pages() -> list[dict]:
    out: list[dict] = []
    for source, index_url, pattern in DIRECT_OFFICIAL_PAGES:
        raw = fetch_bytes(index_url).decode("utf-8", "ignore")
        for href in sorted(set(re.findall(pattern, raw, flags=re.I))):
            url = urllib.parse.urljoin(index_url, html.unescape(href))
            if url.rstrip("/") == index_url.rstrip("/"):
                continue
            title = urllib.parse.unquote(url.rstrip("/").split("/")[-1]).replace("-", " ")
            title = re.sub(r"\\s+", " ", title).strip()
            if title and not title.lower().startswith(source.lower()):
                title = f"{source}: {title}"
            if not title:
                continue
            out.append({
                "kind": "official_direct",
                "query": "direct official page",
                "title": title,
                "description": title,
                "source": source,
                "url": url,
                "published_at": None,
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
    if "investigating unintended model actions" in low:
        return "모델 비의도적 외부접근·사후시정"
    scores = []
    for label, patterns in CATEGORY_PATTERNS:
        score = sum(1 for p in patterns if p in low)
        if score:
            scores.append((score, label))
    if scores:
        scores.sort(reverse=True)
        return scores[0][1]
    if any(term in low for term in (
        "vulnerability", "cve-", "security flaw", "hotfix",
        "patched", "patch released", "security update",
    )):
        return "취약점·패치"
    return "미분류 AI 보안 변화"


def severity(text: str) -> tuple[int, str]:
    low = f" {text.lower()} "
    critical = (
        "critical cybersecurity capability", "critical cyber capability",
        "actively exploited", "exploited in the wild", "sandbox escape",
        "remote code execution", "arbitrary code", "cross-tenant",
        "data exfiltration", "credential theft", "take control",
    )
    high = (
        "cybersecurity capability threshold", "preparedness framework",
        "critical threshold", "high threshold", "zero-day", "zero day", "exploit", "data leak", "data exposure",
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


def is_policy_program_announcement(item: dict) -> bool:
    """Keep new defense programs out of the incident/patch alarm channel."""
    url = (item.get("url") or "").lower().rstrip("/")
    title = (item.get("title") or "").lower()
    if url.endswith("/news/anthropic-cyber-mission"):
        return True
    if "anthropic cyber mission" in title and (
        "introducing" in title or "launch" in title or "announcement" in title
    ):
        return True
    return False


def clean_official_headline_prefix(value: str) -> str:
    return re.sub(
        r"^(?:Anthropic News|Anthropic Research|OpenAI Alignment)[ \t]*:[ \t]*",
        "",
        clean_snippet(value, limit=500),
        flags=re.I,
    ).strip()


def material(item: dict) -> bool:
    if is_policy_program_announcement(item):
        return False
    combined = f" {item.get('title','')} {item.get('description','')} "
    low = combined.lower()

    if item.get("kind") == "official_direct":
        if item.get("url", "").rstrip("/").endswith("/research/investigating-unintended-model-actions"):
            return True
        source = (item.get("source") or "").lower()
        if "openai alignment" in source and "/misalignment-reports/" in (item.get("url") or ""):
            return True
        if "anthropic news" in source:
            return any(term in low for term in (
                "vulnerability", "cve-", "patched", "patch",
                "security flaw", "breach", "incident", "exploit",
                "data leak", "unauthorized", "misalignment",
            ))
        direct_security_terms = (
            "cyber", "security", "sandbox", "misalign", "unauthorized",
            "credential", "token", "prompt injection", "jailbreak",
            "guardrail", "external", "internet", "dns", "exploit",
            "containment", "threat intelligence",
            "vulnerability", "patch", "incident", "breach", "mitigation",
            "security flaw", "data leak", "authentication",
        )
        return any(term in low for term in direct_security_terms)

    if not is_ai_related(low) or not is_security_related(low):
        return False

    # Pure model-behavior debates and generic jailbreak coverage are not enough.
    if "jailbreak" in low and not any(x in low for x in HARD_SECURITY_TERMS):
        if not any(x in low for x in ("data leak", "credential", "tool", "connector", "sandbox", "prompt injection")):
            return False

    sev, _ = severity(low)
    if item.get("kind") in ("official", "official_direct"):
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
        "safety case", "eval awareness", "metagaming", "monitorability",
        "fail-closed", "fail closed", "automatic stop", "auto-stop",
        "regression test", "postmortem", "post-mortem",
        "audit finding", "audit findings", "external audit", "independent audit",
        "control failure", "failed control", "security control failure",
        "accord violation", "noncompliance", "non-compliance",
        "board ordered pause", "oversight ordered pause", "committee ordered pause",
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
    out["official"] = source_official(item.get("source", "")) or item.get("kind") in ("official", "official_direct")
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


def clean_snippet(text: str, limit: int = 320) -> str:
    value = strip_html(text)
    value = re.sub(r"\\s+", " ", value).strip()
    if len(value) > limit:
        return value[: limit - 1].rstrip() + "…"
    return value


HANGUL_RE = re.compile(r"[가-힣]")
LATIN_WORD_RE = re.compile(r"[A-Za-z]{2,}")
TRANSLATE_GOOGLE = "https://translate.googleapis.com/translate_a/single"
TRANSLATE_MYMEMORY = "https://api.mymemory.translated.net/get"
ALERT_IDENTIFIER_TERMS = (
    "OpenAI", "Anthropic", "Claude", "ChatGPT", "Codex", "Gemini",
    "Microsoft", "Copilot", "Meta", "Grok", "xAI", "AWS", "GitHub",
    "NVIDIA", "OpenShell", "NemoClaw", "Sentry", "BlueField-4", "BlueField",
)


def _needs_korean_translation(text: str) -> bool:
    value = strip_html(text)
    return not HANGUL_RE.search(value) and len(LATIN_WORD_RE.findall(value)) >= 3


def _preserve_identifiers(original: str, translated: str) -> str:
    found: list[str] = []
    low = original.lower()
    for term in ALERT_IDENTIFIER_TERMS:
        if term.lower() in low and term.lower() not in translated.lower():
            found.append(term)
    for token in re.findall(r"\\b(?:CVE-\\d{4}-\\d+|GLM-\\d+(?:\\.\\d+)*(?:-[A-Za-z0-9]+)?)\\b", original, flags=re.I):
        if token.lower() not in translated.lower() and token.lower() not in {x.lower() for x in found}:
            found.append(token)
    if found:
        return " · ".join(found) + " · " + translated
    return translated


def _translate_google(text: str) -> str:
    params = urllib.parse.urlencode({
        "client": "gtx",
        "sl": "auto",
        "tl": "ko",
        "dt": "t",
        "q": text,
    })
    req = urllib.request.Request(
        TRANSLATE_GOOGLE + "?" + params,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json,text/plain,*/*"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    chunks = payload[0] if isinstance(payload, list) and payload else []
    return "".join(str(part[0]) for part in chunks if isinstance(part, list) and part and part[0]).strip()


def _translate_mymemory(text: str) -> str:
    params = urllib.parse.urlencode({"q": text, "langpair": "en|ko"})
    req = urllib.request.Request(
        TRANSLATE_MYMEMORY + "?" + params,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return str((payload.get("responseData") or {}).get("translatedText") or "").strip()


def translate_alert_text(text: str) -> str:
    """Translate explanatory text while preserving identifying company names.

    The translator previously changed 'Anthropic' into '인류학' (anthropology).
    Do not submit identity tokens to translation providers, and never translate
    the official index source prefix as though it were the article headline.
    """
    value = clean_official_headline_prefix(text)
    if not _needs_korean_translation(value):
        return value

    parts = re.split(
        r"(?i)(\b(?:Anthropic|OpenAI|NVIDIA|Microsoft|Google|Meta|GitHub|Claude|"
        r"OpenShell|Sentry|BlueField-4|CVE-\d{4}-\d+|"
        r"GLM[- ]\d+(?:\.\d+)*|GPT-\d+(?:\.\d+)*[ ]+[A-Za-z0-9.]+)\b)",
        value,
    )
    canonical = {term.lower(): term for term in ALERT_IDENTIFIER_TERMS}
    errors: list[str] = []
    assembled: list[str] = []
    for part in parts:
        if not part:
            continue
        if part.lower() in canonical:
            assembled.append(canonical[part.lower()])
            continue
        if re.fullmatch(r"(?:CVE-|GLM[- ]|GPT-)[A-Za-z0-9. -]+", part, re.I):
            assembled.append(part)
            continue
        if not LATIN_WORD_RE.search(part):
            assembled.append(part)
            continue
        translated_piece = ""
        for translator in (_translate_google, _translate_mymemory):
            for _attempt in range(2):
                try:
                    candidate = clean_snippet(translator(part), limit=500)
                    if candidate and HANGUL_RE.search(candidate):
                        translated_piece = candidate
                        break
                    errors.append(f"{translator.__name__}: no Hangul")
                except Exception as exc:
                    errors.append(f"{translator.__name__}: {type(exc).__name__}: {exc}")
            if translated_piece:
                break
        if not translated_piece:
            raise RuntimeError("Korean translation failed: " + " | ".join(errors[-4:]))
        # Provider responses strip boundary spaces; preserve original spacing
        # around company/model identifiers to prevent 'Anthropic사이버'.
        assembled.append(
            (" " if part[0].isspace() else "")
            + translated_piece
            + (" " if part[-1].isspace() else "")
        )

    result = " ".join("".join(assembled).split())
    if ("Anthropic" in value or "anthropic" in value.lower()) and "인류학" in result:
        raise RuntimeError("Company identifier was mistranslated")
    return result


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
    if any(x in text for x in ("release cancelled", "release canceled", "launch cancelled", "launch canceled")):
        return "신규 모델 출시 취소·철회"
    if any(x in text for x in ("release delayed", "launch delayed", "release postponed", "launch postponed")):
        return "신규 모델 출시 연기"
    if any(x in text for x in ("restricted rollout", "restricted deployment", "limited release", "limited rollout")):
        return "안전성 우려에 제한 출시·배포"
    if any(x in text for x in ("deployment blocked", "safety gate failed", "failed safety evaluation", "failed alignment evaluation")):
        return "안전 게이트 미통과로 배포 차단"
    if ("training" in text or "evaluation" in text or "inference" in text) and ("paused" in text or "suspended" in text):
        return "최고 성능 모델의 학습·평가·추론 또는 도구사용 중단"
    if ("training" in text or "evaluation" in text or "inference" in text) and ("resumed" in text or "restart" in text):
        return "중단됐던 모델 학습·평가·추론 또는 도구사용 재개"
    if ("10-fold" in text or "tenfold" in text or "ten-fold" in text) and ("mythos" in text or "anthropic" in text):
        return "Anthropic Mythos 이후 AI 사이버 위험이 10배 높아졌다는 대형 금융기관 경고"
    if ("129,000" in text or "129000" in text) and "vulnerab" in text:
        return "검증된 소프트웨어 취약점 최소 12만9,000건 확인"
    if ("33,000" in text or "33000" in text) and ("critical" in text or "high" in text):
        return "이 중 3만3,000건이 긴급·높음 등급"
    if ("5,500" in text or "5500" in text) and "vulnerab" in text:
        return "Anthropic 자체 스캔으로 추가 취약점 5,500건 발견"
    if (item.get("url") or "").rstrip("/").endswith("/research/investigating-unintended-model-actions"):
        return "Anthropic 공식 사고보고: 평가·내부 사용 중 서버 명령 실행·실제 웹 양식 제출·접근 제한 우회 등 비의도적 행동 확인"
    if "481 million" in text or "481m" in text:
        return "Anthropic 조사 범위 약 4억8,100만 기록"
    if ("four incidents" in text or "4 incidents" in text) and ("unauthorized" in text or "third-party" in text):
        return "실제 제3자 시스템 비인가 접근 4건 확인"
    if "15 minutes" in text and ("2.5 hours" in text or "two and a half hours" in text):
        return "탐지 약 15분 · 실행 종료 약 2시간30분"
    if "1.5%" in text and "sandbox" in text:
        return "적대적 평가에서 샌드박스 탈출 시도율 1.5%"
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
    if "openshell" in text and ("bypass" in text or "escape" in text or "credential" in text or "exfiltrat" in text):
        return "OpenShell·에이전트 안전 런타임의 정책 우회 또는 격리 실패"
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
    if "금융·핵심인프라 AI 사이버 위험 경보" in cats:
        return "대형 은행·핵심인프라 운영자가 프런티어 모델의 공격·취약점 탐색 능력을 실제 시스템 위험으로 평가하기 시작했는지, 보안예산·모델 접근통제·사고대응 체계가 강화되는지가 핵심입니다."
    if "프런티어 모델 사이버 역량·접근 확대" in cats:
        return "Anthropic이 Mythos 같은 고성능 사이버 모델의 접근범위와 차단 수준을 검증된 방어·레드팀 조직에 확대하면서 방어 생산성과 오용 위험이 동시에 커지는지가 핵심입니다."
    if "대규모 취약점 발굴·검증" in cats:
        return "AI가 실제 소프트웨어에서 발굴·검증하는 취약점 규모와 심각도가 인간 중심 보안 프로세스의 처리용량을 넘어서는지가 핵심입니다."
    if "모델 비의도적 외부접근·사후시정" in cats:
        return "정부기관 등 제3자 웹시스템에 대한 모델의 비의도적 요청을 실제 침해·무해한 양식 제출·시험환경 실패로 구분하고, 관계기관 신고·인터넷 격리·자동 차단의 실효성을 추적합니다."
    if "공동서약·외부감사 보안실패" in cats:
        return "공동 안전서약의 외부감사에서 실제 보안통제 실패·비인가 접근·준수 위반이 확인됐는지가 핵심입니다."
    if "이사회·감독기구 중단명령" in cats:
        return "감사 결과를 받은 독립 이사회·감독기구가 실제 학습·배포 중단 권한을 행사했는지가 핵심입니다."
    if "Safety Case·학습 승인 게이트" in cats:
        return "프런티어 강화학습을 계속하기 전에 위험·격리·모니터링 증거가 실제 학습 승인 게이트로 작동하는지가 핵심입니다."
    if "평가 인식·모니터 회피" in cats:
        return "모델이 평가·감시 상황을 인식해 행동을 바꾸거나 모니터를 회피하는 능력이 실제로 증가하는지가 핵심입니다."
    if "사고 사후분석·회귀검사" in cats:
        return "비정렬 사고 원인이 학습 과정까지 역추적되고 동일 행동이 향후 회귀검사에 실제 반영되는지가 핵심입니다."
    if "출시 게이트·배포 제한" in cats:
        return "모델 성능이 아니라 안전·정렬 평가가 실제 출시 일정과 배포 범위를 제한하는지가 핵심입니다."
    if "에이전트 안전 런타임 실패" in cats:
        return "에이전트 실행환경의 샌드박스·네트워크·자격증명 정책이 실제로 우회되는지가 핵심입니다."
    if "모델 운영중단·재개" in cats:
        return "최고 성능 모델의 학습·평가·추론·도구사용 중단 또는 재개가 실제 안전통제 변화로 이어지는지가 핵심입니다."
    if "모델 사이버 능력 임계치" in cats:
        return "사고 여부와 별개로 모델 자체 공격 역량이 새로운 위험 임계치에 진입했는지가 핵심입니다."
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
            headline = clean_official_headline_prefix(
                clean_snippet(rep.get("title", ""), limit=220)
            )
            if headline:
                try:
                    translated_headline = translate_alert_text(headline)
                except Exception as exc:
                    print(f"ai_security_translation_fallback={type(exc).__name__}: {exc}")
                    translated_headline = ""
                if translated_headline and HANGUL_RE.search(translated_headline):
                    facts.append(clean_snippet(translated_headline, limit=110))
                else:
                    facts.append(
                        f"{rep['vendor']} 관련 {rep.get('category') or '중요 보안 변화'} 공식 업데이트"
                    )
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
        "<b>다음 확인</b>: Mythos/CVP 접근등급·차단수준 · 금융·핵심인프라 실제 사고·보안예산 변화 · AI 취약점 발굴량/긴급·높음 비중 · 공동서약 외부감사 보안실패·준수위반 · 독립 이사회/감독기구의 실제 중단명령 · 공식 출시일/변경일 · 안전게이트 통과 여부 · 제한배포 범위 · 실제 사고/모의평가 구분 · 탐지→강제종료 시간 · 중단/재개 · 패치/완화책",
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

    direct_items: list[dict] = []
    try:
        direct_items = parse_direct_official_pages()
        raw_items.extend(direct_items)
    except Exception as exc:
        errors.append(f"공식 연구페이지 직접 감시 실패: {type(exc).__name__}: {exc}")

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
    direct_source_version = 4
    direct_baseline = state.get("direct_official_version") != direct_source_version
    if baseline:
        new_items = []
    elif direct_baseline:
        new_items = [i for i in new_items if i.get("kind") != "official_direct"]

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
        "direct_official_initialized": True,
        "direct_official_version": direct_source_version,
        "updated_at_kst": now.astimezone(KST).isoformat(timespec="seconds"),
        "seen": seen,
        "last_collection": {
            "raw_items": len(raw_items),
            "direct_official_items": len(direct_items),
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
        f"- 공식 연구페이지 직접 항목: {len(direct_items)}건",
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
