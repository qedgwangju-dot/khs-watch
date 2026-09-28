from __future__ import annotations

import copy
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

try:
    from googlenewsdecoder import gnewsdecoder
except Exception:
    gnewsdecoder = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "ai_inference_structure_watch_state.json"
PENDING_PATH = ROOT / "out" / "ai_inference_structure_pending_state.json"
ALERT_PATH = ROOT / "out" / "ai_inference_structure_alert.html"
RUBIN_STATE_PATH = ROOT / "data" / "rubin_hbm_watch_state.json"
UA = "Mozilla/5.0 (compatible; khs-watch/inference-structure)"

BASELINE = {
    "as_of": "2026-09-28",
    "cpu_ratio": {
        "AMD": {"cpu_per_gpu": 1.0, "source": "https://www.amd.com/en/blogs/2026/agentic-ai-changes-the-cpu-gpu-equation.html"},
        "Intel": {"cpu_per_gpu": 1.0, "source": "https://www.intel.com/content/www/us/en/newsroom/news/artificial-intelligence/computex-2026-an-intelligent-world-built-on-silicon.html"},
        "Dell": {"cpu_per_gpu": 1.0, "source": "https://www.amd.com/en/corporate/events/advancing-ai/sessions-catalog/dell-technologies--balancing-cpu-and-gpu-for-the-agentic-ai-era.html"},
    },
    "neocloud": {
        "CoreWeave": {
            "active_power_gw": 1.5,
            "contracted_power_gw": 4.2,
            "annualized_revenue_per_mw_usd_m": 40.0,
        },
        "Nebius": {
            "contracted_power_gw": 3.5,
            "contracted_power_guidance_gw": 4.0,
            "microsoft_servicing": True,
        },
    },
    "upstream_snapshot": {},
    "seen_urls": [
        "https://www.amd.com/en/blogs/2026/agentic-ai-changes-the-cpu-gpu-equation.html",
        "https://www.intel.com/content/www/us/en/newsroom/news/artificial-intelligence/computex-2026-an-intelligent-world-built-on-silicon.html",
        "https://www.amd.com/en/corporate/events/advancing-ai/sessions-catalog/dell-technologies--balancing-cpu-and-gpu-for-the-agentic-ai-era.html",
        "https://www.sem.samsung.com/global/newsroom/news/view.do?id=10462",
        "https://investors.coreweave.com/news/news-details/2026/CoreWeave-Reports-Strong-Second-Quarter-2026-Results/default.aspx",
        "https://investors.coreweave.com/news/news-details/2026/CoreWeave-Continues-to-Contract-New-Compute-Capacity-at-Higher-Prices/default.aspx",
        "https://nebius.com/newsroom/nebius-reports-first-quarter-2026-financial-results",
        "https://nebius.com/newsroom/nebius-raises-775-million-in-first-secured-debt-financing-to-accelerate-global-buildout",
    ],
    "last_checked_at_kst": "2026-09-28T12:10:00+09:00",
    "candidate_count": 0,
    "event_count": 0,
}

SEARCHES = [
    'site:amd.com OR site:intel.com OR site:arm.com OR site:nvidia.com OR site:dell.com OR site:hpe.com "agentic AI" CPU GPU ratio',
    'site:investors.coreweave.com CoreWeave active power contracted power megawatt annualized revenue 2026',
    'site:nebius.com OR site:assets.nebius.com Nebius active power connected power contracted power servicing capacity tranche 2026',
    '(site:att.com OR site:verizon.com OR site:t-mobile.com OR site:microsoft.com OR site:aws.amazon.com OR site:cloud.google.com OR site:oracle.com) edge regional inference AI contract MW deployed',
]

OFFICIAL_DOMAINS = (
    "amd.com", "intel.com", "arm.com", "nvidia.com", "dell.com", "hpe.com",
    "investors.coreweave.com", "coreweave.com", "nebius.com", "assets.nebius.com",
    "att.com", "verizon.com", "t-mobile.com", "microsoft.com", "aws.amazon.com",
    "cloud.google.com", "googlecloudpresscorner.com", "oracle.com",
)

def fetch(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()

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
    return "https://news.google.com/rss/search?q=" + urllib.parse.quote(query) + "&hl=en-US&gl=US&ceid=US:en"

def read_rss(query: str) -> list[dict]:
    root = ET.fromstring(fetch(google_news_url(query)))
    rows = []
    for item in root.findall("./channel/item"):
        title = clean_text(item.findtext("title") or "")
        link = clean_text(item.findtext("link") or "")
        desc = clean_text(item.findtext("description") or "")
        dt = parse_pubdate(clean_text(item.findtext("pubDate") or ""))
        if title and link:
            rows.append({
                "title": title,
                "link": link,
                "description": desc,
                "published_at_kst": dt.isoformat(timespec="seconds") if dt else "",
            })
    return rows

def decode_google_news(link: str) -> str:
    if "news.google.com" not in (link or ""):
        return link
    if gnewsdecoder is None:
        return ""
    try:
        result = gnewsdecoder(link, interval=0.15)
        if isinstance(result, dict) and result.get("status"):
            decoded = str(result.get("decoded_url") or "").strip()
            if decoded.startswith("http") and "news.google.com" not in decoded:
                return decoded
    except Exception:
        pass
    return ""

def article_text(url: str) -> str:
    try:
        return clean_text(fetch(url, timeout=18).decode("utf-8", errors="ignore"))[:50000]
    except Exception:
        return ""

def host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()

def is_official(url: str) -> bool:
    host = host_of(url)
    return any(host == d or host.endswith("." + d) for d in OFFICIAL_DOMAINS)

def load_json(path: pathlib.Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def write_json(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def company_for(url: str, text: str = "") -> str:
    host = host_of(url)
    low = text.lower()
    if "coreweave.com" in host:
        return "CoreWeave"
    if "nebius.com" in host:
        return "Nebius"
    if "intel.com" in host:
        return "Intel"
    if "dell.com" in host or "dell technologies" in low:
        return "Dell"
    if "amd.com" in host:
        return "AMD"
    if "arm.com" in host:
        return "Arm"
    if "nvidia.com" in host:
        return "NVIDIA"
    if "hpe.com" in host:
        return "HPE"
    return host.split(".")[-2] if "." in host else host

def _to_gw(value: float, unit: str) -> float:
    return value / 1000.0 if unit.lower().startswith("m") else value

def metric_near(text: str, label_pattern: str) -> float | None:
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if not re.search(label_pattern, sentence, re.I):
            continue
        m = re.search(r"(\d+(?:\.\d+)?)\s*(GW|gigawatts?|MW|megawatts?)\b", sentence, re.I)
        if m:
            return _to_gw(float(m.group(1)), m.group(2))
    return None

def parse_cpu_ratio(text: str, url: str) -> dict:
    low = text.lower()
    if not is_official(url) or "cpu" not in low or "gpu" not in low or not any(k in low for k in ("agentic", "agent", "agents")):
        return {}
    ratios = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        s = sentence.lower()
        if "cpu" not in s or "gpu" not in s or not any(k in s for k in ("agentic", "agent", "agents")):
            continue
        for m in re.finditer(r"(\d+(?:\.\d+)?)(?:\+)?\s*(?:cpu)?\s*(?::|to)\s*(\d+(?:\.\d+)?)\s*(?:gpu)?", sentence, re.I):
            den = float(m.group(2))
            if den:
                ratios.append(float(m.group(1)) / den)
    if not ratios:
        return {}
    return {"kind": "cpu_ratio", "company": company_for(url, text), "cpu_per_gpu": max(ratios)}

def parse_coreweave(text: str, url: str) -> dict:
    if company_for(url, text) != "CoreWeave":
        return {}
    metrics = {}
    active = metric_near(text, r"\bactive power\b")
    contracted = metric_near(text, r"\b(?:total )?contracted power\b")
    if active is not None:
        metrics["active_power_gw"] = active
    if contracted is not None:
        metrics["contracted_power_gw"] = contracted
    m = re.search(r"(?:pricing|annualized revenue)[^.]{0,160}?\$\s*(\d+(?:\.\d+)?)\s*million\s+per\s+megawatt", text, re.I)
    if m:
        metrics["annualized_revenue_per_mw_usd_m"] = float(m.group(1))
    negative = bool(re.search(r"\b(cancelled|canceled|contract cancellation|has terminated|terminated the|termination announced|delayed by|delay of|postponed|power shortfall)\b", text, re.I))
    return {"kind": "neocloud", "company": "CoreWeave", "metrics": metrics, "negative": negative} if metrics or negative else {}

def parse_nebius(text: str, url: str) -> dict:
    if company_for(url, text) != "Nebius":
        return {}
    metrics = {}
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        low = sentence.lower()
        if "contracted power" in low:
            m = re.search(r"(\d+(?:\.\d+)?)\s*(GW|gigawatts?|MW|megawatts?)\b", sentence, re.I)
            if m:
                value = _to_gw(float(m.group(1)), m.group(2))
                if any(k in low for k in ("guidance", "target", "year-end", "expect")):
                    metrics["contracted_power_guidance_gw"] = value
                else:
                    metrics["contracted_power_gw"] = value
        if "connected power" in low:
            m = re.search(r"(\d+(?:\.\d+)?)\s*(GW|gigawatts?|MW|megawatts?)\b", sentence, re.I)
            if m and not any(k in low for k in ("target", "expect", "year-end")):
                metrics["connected_power_gw"] = _to_gw(float(m.group(1)), m.group(2))
        if "active power" in low:
            m = re.search(r"(\d+(?:\.\d+)?)\s*(GW|gigawatts?|MW|megawatts?)\b", sentence, re.I)
            if m:
                metrics["active_power_gw"] = _to_gw(float(m.group(1)), m.group(2))
    servicing = bool(re.search(r"\b(servicing phase|servicing stage|delivered the latest planned capacity tranche|capacity commitments.*delivered)\b", text, re.I))
    microsoft = "microsoft" in text.lower()
    negative = bool(re.search(r"\b(cancelled|canceled|contract cancellation|has terminated|terminated the|missed delivery|delayed by|delay of|postponed)\b", text, re.I))
    if servicing and microsoft:
        metrics["microsoft_servicing"] = True
    return {"kind": "neocloud", "company": "Nebius", "metrics": metrics, "negative": negative} if metrics or negative else {}

def parse_edge_actual(text: str, url: str, title: str) -> dict:
    if not is_official(url):
        return {}
    title_low = (title or "").lower()
    if any(k in title_low for k in ("acquire", "acquisition", "merger", "to buy", "investment in")):
        return {}

    sentences = re.split(r"(?<=[.!?])\s+", text)
    edge_terms = ("edge", "regional", "metro", "telco", "distributed")
    inference_terms = ("inference", "agentic ai", "ai inference")
    action_terms = (
        "signed", "contract", "purchase order", "deployed", "deployment",
        "operational", "in service", "commercially available", "service launch",
        "launched", "production deployment",
    )

    for i, sentence in enumerate(sentences):
        window = " ".join(sentences[i:i + 2])
        low = window.lower()
        if not any(k in low for k in edge_terms):
            continue
        if not any(k in low for k in inference_terms):
            continue
        if not any(k in low for k in action_terms):
            continue

        scale_match = re.search(
            r"\b\d+(?:\.\d+)?\s*(?:MW|GW|megawatts?|gigawatts?)\b",
            window,
            re.I,
        )
        money_match = re.search(
            r"(?:\$|USD)\s*\d[\d,.]*(?:\s*(?:million|billion|M|B))?",
            window,
            re.I,
        )
        if not (scale_match or money_match):
            continue

        return {
            "kind": "edge_actual",
            "company": company_for(url, text),
            "title": title,
            "scale": scale_match.group(0) if scale_match else "",
            "money": money_match.group(0) if money_match else "",
        }
    return {}

def compare_neocloud(previous: dict, update: dict) -> list[dict]:
    company = update["company"]
    old = ((previous.get("neocloud") or {}).get(company) or {})
    events = []
    thresholds = {
        "active_power_gw": (0.10, "활성 전력"),
        "connected_power_gw": (0.10, "전원 연결 전력"),
        "contracted_power_gw": (0.20, "계약 전력"),
    }
    for key, (absolute, label) in thresholds.items():
        if key not in update["metrics"]:
            continue
        before = old.get(key)
        after = float(update["metrics"][key])
        if before is None:
            events.append({"kind": "neocloud_metric", "company": company, "label": label, "before": None, "after": after, "unit": "GW"})
            continue
        before = float(before)
        pct = abs(after / before - 1.0) if before else 1.0
        if abs(after - before) >= absolute or pct >= 0.10:
            events.append({"kind": "neocloud_metric", "company": company, "label": label, "before": before, "after": after, "unit": "GW"})
    if "annualized_revenue_per_mw_usd_m" in update["metrics"]:
        before = old.get("annualized_revenue_per_mw_usd_m")
        after = float(update["metrics"]["annualized_revenue_per_mw_usd_m"])
        if before is None or (before and abs(after / float(before) - 1.0) >= 0.10):
            events.append({"kind": "neocloud_metric", "company": company, "label": "MW당 연환산 매출", "before": before, "after": after, "unit": "USDm/MW"})
    if update["metrics"].get("microsoft_servicing") and not old.get("microsoft_servicing"):
        events.append({"kind": "servicing", "company": company, "label": "Microsoft 계약이 실제 서비스 단계로 전환"})
    if update.get("negative"):
        events.append({"kind": "negative", "company": company, "label": "계약·전력·납기 하향 신호"})
    return events

def upstream_snapshot() -> dict:
    root = load_json(RUBIN_STATE_PATH)
    agent = root.get("agentic_cpu_demand") or {}
    samsung = root.get("samsung_electromechanics_cpu_realization") or {}
    abf = root.get("abf_cpu_monetization") or {}
    am = agent.get("metrics") or {}
    sm = samsung.get("metrics") or {}
    sf = samsung.get("facts") or {}
    ao = abf.get("official") or {}
    af = abf.get("facts") or {}
    return {
        "agentic_ratio": (agent.get("cpu_gpu_ratio") or {}).get("agentic"),
        "server_cpu_tam_2030_usd_bn": am.get("server_cpu_tam_2030_usd_bn"),
        "samsung_q3_revenue_forecast_krw_100m": sm.get("q3_revenue_forecast_krw_100m"),
        "samsung_q3_operating_profit_forecast_krw_100m": sm.get("q3_operating_profit_forecast_krw_100m"),
        "samsung_cpu_abf_share_floor_pct": sm.get("cpu_abf_share_floor_pct"),
        "samsung_server_cpu_fcbga_mass_production": sf.get("server_cpu_fcbga_mass_production"),
        "samsung_q3_actual_revenue_krw_100m": sf.get("q3_actual_revenue_krw_100m"),
        "samsung_q3_actual_operating_profit_krw_100m": sf.get("q3_actual_operating_profit_krw_100m"),
        "samsung_venice_large_scale_deployment_confirmed": sf.get("meta_venice_large_scale_deployment_confirmed") or sf.get("venice_demand_validation_advanced"),
        "ibiden_sap_capacity_multiple": ao.get("ibiden_sap_capacity_fy2027_multiple_min"),
        "ibiden_capex_jpy_bn": ao.get("ibiden_capex_fy2026_2028_jpy_bn"),
        "ibiden_asic_share_pct": ao.get("ibiden_asic_share_fy2026_floor_pct"),
        "ibiden_pricing_stance": ao.get("ibiden_pricing_stance"),
        "ibiden_abf_price_increase": af.get("official_abf_price_increase_confirmed"),
        "ibiden_nvidia_cpu_substrate_confirmed": af.get("official_nvidia_cpu_substrate_confirmed"),
    }

def upstream_events(before: dict, after: dict) -> list[dict]:
    if not before:
        return []
    events = []
    if before.get("agentic_ratio") != after.get("agentic_ratio") and after.get("agentic_ratio"):
        events.append({"kind": "upstream", "label": "에이전트형 CPU:GPU 비율", "before": before.get("agentic_ratio"), "after": after.get("agentic_ratio")})
    numeric = {
        "server_cpu_tam_2030_usd_bn": ("서버 CPU 2030 시장 전망", 0.10, "pct"),
        "samsung_q3_revenue_forecast_krw_100m": ("삼성전기 3Q 매출 전망", 0.05, "pct"),
        "samsung_q3_operating_profit_forecast_krw_100m": ("삼성전기 3Q 영업이익 전망", 0.10, "pct"),
        "samsung_cpu_abf_share_floor_pct": ("삼성전기 CPU향 ABF 비중", 5.0, "pp"),
        "ibiden_sap_capacity_multiple": ("IBIDEN SAP 생산능력", 0.10, "pct"),
        "ibiden_capex_jpy_bn": ("IBIDEN 전자사업 설비투자", 0.10, "pct"),
        "ibiden_asic_share_pct": ("IBIDEN ASIC 매출 비중", 5.0, "pp"),
    }
    for key, (label, threshold, mode) in numeric.items():
        b, a = before.get(key), after.get(key)
        if b in (None, 0) or a in (None, 0):
            continue
        b, a = float(b), float(a)
        delta = (a / b - 1.0) if mode == "pct" else (a - b)
        if abs(delta) >= threshold:
            events.append({"kind": "upstream", "label": label, "before": b, "after": a})
    for key, label in {
        "samsung_server_cpu_fcbga_mass_production": "삼성전기 서버 CPU FCBGA 양산",
        "samsung_venice_large_scale_deployment_confirmed": "6세대 EPYC 실제 대규모 배치",
        "ibiden_abf_price_increase": "IBIDEN ABF 가격 인상",
        "ibiden_nvidia_cpu_substrate_confirmed": "IBIDEN NVIDIA CPU 기판 공급",
    }.items():
        if before.get(key) != after.get(key) and after.get(key) is not None:
            events.append({"kind": "upstream", "label": label, "before": before.get(key), "after": after.get(key)})
    if before.get("ibiden_pricing_stance") != after.get("ibiden_pricing_stance") and after.get("ibiden_pricing_stance"):
        events.append({"kind": "upstream", "label": "IBIDEN 가격 정책", "before": before.get("ibiden_pricing_stance"), "after": after.get("ibiden_pricing_stance")})
    for key, label in {
        "samsung_q3_actual_revenue_krw_100m": "삼성전기 3Q 실제 매출",
        "samsung_q3_actual_operating_profit_krw_100m": "삼성전기 3Q 실제 영업이익",
    }.items():
        if before.get(key) != after.get(key) and after.get(key) not in (None, 0):
            events.append({"kind": "upstream", "label": label, "before": before.get(key), "after": after.get(key)})
    return events

def newer_than(published: str, cutoff: str) -> bool:
    try:
        return datetime.fromisoformat(published) > datetime.fromisoformat(cutoff)
    except Exception:
        return False

def discover(previous: dict) -> list[dict]:
    seen = set(previous.get("seen_urls") or [])
    cutoff = str(previous.get("last_checked_at_kst") or "")
    rows, local = [], set()
    fetched = 0
    for query in SEARCHES:
        try:
            items = read_rss(query)
        except Exception:
            continue
        for item in items:
            url = decode_google_news(item.get("link") or "")
            if not url or url in seen or url in local or not is_official(url):
                continue
            local.add(url)
            published = item.get("published_at_kst") or ""
            if cutoff and not newer_than(published, cutoff):
                continue
            if fetched >= 22:
                continue
            fetched += 1
            text = clean_text(item.get("title", "") + " " + item.get("description", "") + " " + article_text(url))
            parsed = (
                parse_coreweave(text, url)
                or parse_nebius(text, url)
                or parse_cpu_ratio(text, url)
                or parse_edge_actual(text, url, item.get("title") or "")
            )
            if parsed:
                rows.append({**item, "url": url, "parsed": parsed})
    rows.sort(key=lambda x: x.get("published_at_kst") or "")
    return rows

def event_line(event: dict) -> str:
    kind = event.get("kind")
    if kind == "cpu_ratio":
        return f"• <b>{html.escape(event['company'])} CPU:GPU 구조:</b> CPU/GPU {float(event['before']):.2f} → {float(event['after']):.2f}"
    if kind == "neocloud_metric":
        before = "신규" if event.get("before") is None else f"{float(event['before']):.2f}"
        if event.get("unit") == "USDm/MW":
            return f"• <b>{html.escape(event['company'])} {html.escape(event['label'])}:</b> {before} → {float(event['after']):.1f}백만달러"
        return f"• <b>{html.escape(event['company'])} {html.escape(event['label'])}:</b> {before} → {float(event['after']):.2f}GW"
    if kind in ("servicing", "negative"):
        return f"• <b>{html.escape(event['company'])}:</b> {html.escape(event['label'])}"
    if kind == "edge_actual":
        detail = " / ".join(x for x in (str(event.get("scale") or ""), str(event.get("money") or "")) if x)
        suffix = f" ({html.escape(detail)})" if detail else ""
        return f"• <b>에지·지역 추론 상용화:</b> {html.escape(event['company'])} — {html.escape(event['title'])}{suffix}"
    if kind == "upstream":
        return f"• <b>{html.escape(event['label'])}:</b> {html.escape(str(event.get('before')))} → {html.escape(str(event.get('after')))}"
    return "• 구조 변화 감지"

def build_alert(events: list[dict], latest: dict, sources: list[str]) -> str:
    cw = (latest.get("neocloud") or {}).get("CoreWeave") or {}
    kinds = {str(e.get("kind") or "") for e in events}
    labels = " ".join(str(e.get("label") or "") for e in events)

    lines = [
        "<b>🚨 AI 추론 수익화 변화</b>",
        "",
        "<b>변화</b>",
        *[event_line(e) for e in events],
        "",
        "<b>의미</b>",
        "• Agentic AI → CPU 비중 상승 → FCBGA·지역 인프라 → 실제 MW·매출로 이어지는지 확인하는 신호입니다.",
    ]

    current = []
    if "cpu_ratio" in kinds or "CPU" in labels or "서버 CPU" in labels:
        current.append("• CPU:GPU 기준선: AMD·Intel 에이전트형 AI 약 1:1 방향")
    if "upstream" in kinds and any(k in labels for k in ("FCBGA", "ABF", "삼성전기", "IBIDEN")):
        current.append("• 삼성전기 2Q26 패키지솔루션 7,716억원")
    if "neocloud_metric" in kinds or "servicing" in kinds or "negative" in kinds:
        current.append(
            f"• CoreWeave: 활성 {float(cw.get('active_power_gw') or 0):.2f}GW / "
            f"계약 {float(cw.get('contracted_power_gw') or 0):.2f}GW / "
            f"MW당 연환산 매출 {float(cw.get('annualized_revenue_per_mw_usd_m') or 0):.1f}백만달러"
        )
    if current:
        lines += ["", "<b>현재 숫자</b>", *current]

    checks = []
    if "cpu_ratio" in kinds or "CPU" in labels:
        checks.append("CPU 주문·출하")
    if "upstream" in kinds:
        checks.append("FCBGA 가동률·고객 승인")
    if "neocloud_metric" in kinds or "servicing" in kinds or "negative" in kinds:
        checks.append("계약 GW→활성 GW·MW당 매출")
    if "edge_actual" in kinds:
        checks.append("실제 가동 MW·상용 매출")
    if not checks:
        checks.append("실제 주문·양산·MW·매출")
    lines += ["", "<b>다음 확인</b>", "• " + " / ".join(dict.fromkeys(checks))]

    unique_sources = list(dict.fromkeys(sources))
    if unique_sources:
        lines += ["", "<b>원문</b>"]
        for url in unique_sources:
            lines.append(f'• <a href="{html.escape(url, quote=True)}">근거 원문</a>')

    return "\n".join(lines).strip() + "\n"

def main() -> None:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    previous = load_json(STATE_PATH) or copy.deepcopy(BASELINE)
    latest = copy.deepcopy(previous)
    updates = discover(previous)
    events = []
    source_urls = []

    latest.setdefault("cpu_ratio", copy.deepcopy(BASELINE["cpu_ratio"]))
    latest.setdefault("neocloud", copy.deepcopy(BASELINE["neocloud"]))
    seen = set(latest.get("seen_urls") or [])

    for item in updates:
        parsed = item["parsed"]
        url = item["url"]
        source_urls.append(url)
        seen.add(url)
        if parsed["kind"] == "cpu_ratio":
            company = parsed["company"]
            old = (latest["cpu_ratio"].get(company) or {}).get("cpu_per_gpu")
            after = float(parsed["cpu_per_gpu"])
            if old is None or (float(old) and abs(after / float(old) - 1.0) >= 0.25):
                events.append({"kind": "cpu_ratio", "company": company, "before": float(old or 0), "after": after})
            latest["cpu_ratio"][company] = {"cpu_per_gpu": after, "source": url}
        elif parsed["kind"] == "neocloud":
            events.extend(compare_neocloud(latest, parsed))
            latest["neocloud"].setdefault(parsed["company"], {}).update(parsed["metrics"])
        elif parsed["kind"] == "edge_actual":
            events.append(parsed)

    snap = upstream_snapshot()
    events.extend(upstream_events(previous.get("upstream_snapshot") or {}, snap))
    latest["upstream_snapshot"] = snap
    latest["seen_urls"] = sorted(seen)[-250:]
    latest["last_checked_at_kst"] = now.isoformat(timespec="seconds")
    latest["candidate_count"] = len(updates)
    latest["event_count"] = len(events)
    write_json(PENDING_PATH, latest)

    if events:
        ALERT_PATH.parent.mkdir(parents=True, exist_ok=True)
        ALERT_PATH.write_text(build_alert(events, latest, source_urls), encoding="utf-8")

    print(
        "ai_inference_structure_watch=true "
        f"candidates={len(updates)} events={len(events)} notify={str(bool(events)).lower()}"
    )

if __name__ == "__main__":
    main()
