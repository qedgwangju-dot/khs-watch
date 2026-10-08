from __future__ import annotations

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

UA = "Mozilla/5.0 (compatible; khs-watch/3.0; +https://github.com/qedgwangju-dot/khs-watch)"
BOFA_BASELINE_URL = "https://finvaulta.com/research/bank-of-america/rise-of-the-agents-raising-cpu-tam-again-to-210bn-2026-08-12"
AMD_RATIO_URL = "https://www.amd.com/en/blogs/2026/agentic-ai-changes-the-cpu-gpu-equation.html"
AMD_AAI_URL = "https://ir.amd.com/news-events/press-releases/detail/1294/aai-2026-amd-delivers-full-stack-compute-for-the-agentic-ai-era"

BASELINE = {
    "as_of": "2026-08-12",
    "issuer": "Bank of America",
    "source": BOFA_BASELINE_URL,
    "source_kind": "BofA 전망의 2차 리서치 요약",
    "metrics": {
        "server_cpu_tam_2030_usd_bn": 210.6,
        "traditional_iaas_2030_usd_bn": 30.2,
        "compute_head_2030_usd_bn": 90.2,
        "agentic_2030_usd_bn": 90.2,
        "ai_cpu_2030_usd_bn": 180.4,
        "agentic_share_pct": 42.83,
        "ai_cpu_share_pct": 85.66,
        "server_cpu_2025_usd_bn": 35.0,
        "server_cpu_2026_usd_bn": 61.4,
        "server_cpu_cagr_2025_2030_pct": 43.1,
        "server_cpu_cagr_2026_2030_pct": 36.1,
        "ai_cpu_cagr_2026_2030_pct": 43.6,
    },
    "cpu_gpu_ratio": {
        "agentic": "1:1",
        "training": "1:4-8",
        "basic_inference": "1:2",
        "official_support": AMD_RATIO_URL,
    },
    "revision_history": [
        {"date": "2026-05-20", "server_cpu_tam_2030_usd_bn": 125.0, "source_kind": "BofA 보도 재전달"},
        {"date": "2026-06-11", "server_cpu_tam_2030_usd_bn": 170.0, "source_kind": "BofA 리포트 해석 자료"},
        {"date": "2026-08-12", "server_cpu_tam_2030_usd_bn": 210.6, "source_kind": "BofA 전망의 2차 리서치 요약"},
    ],
    "seen_forecast_urls": [BOFA_BASELINE_URL],
    "seen_validation_urls": [AMD_RATIO_URL, AMD_AAI_URL],
    "last_validation_cutoff": "2026-09-25",
}

# Independent institutional forecasts must not overwrite Bank of America's series.
# Values below are locked with their exact source class, not a blended consensus.
CPU_STRUCTURE_TRACK_VERSION = 1
CPU_STRUCTURE_BASELINE = {
    "bnpp_public": {
        "as_of": "2026-10-05",
        "market_2025_usd_bn": 26.0,
        "market_2030_usd_bn": 220.0,
        "source_kind": "BNP Paribas 공개 글에 인용된 AMD 추정치 · BNP 자체 전망과 구분",
        "source_url": "https://cib.bnpparibas/ai-infrastructure-investment-2026/",
    },
    "bnpp_analyst": {
        "as_of": "2026-10-05",
        "market_2030_usd_bn": 245.0,
        "market_2025_user_claim_usd_bn": 30.0,
        "market_2025_official_confirmed": False,
        "amd_target_usd": 960.0,
        "amd_prior_target_usd": 600.0,
        "arm_target_user_claim_usd": 405.0,
        "arm_target_confirmed": False,
        "source_kind": "BNP Paribas Karl Ackerman 애널리스트 의견의 2차 보도 · 보고서 원문 미열람",
        "source_url": "https://finance.yahoo.com/markets/stocks/articles/bnp-paribas-revamps-amd-stock-191959150.html",
        "target_source_url": "https://www.marketscreener.com/news/bnp-paribas-adjusts-pt-on-advanced-micro-devices-to-960-from-600-keeps-outperform-rating-ce785ddbd08af222",
    },
    "digitimes": {
        "as_of": "2026-10-07",
        "per_accelerator_cpu_2027": "nearly_double",
        "cpu_xpu_ratio_2027": 2.3,
        "cpu_xpu_ratio_source_kind": "DIGITIMES 2026-10-05 연구 표제 CPU:XPU=1:2.3 · 영어 후속기사 2027년 언급 · 원문 상세 연도는 구독 제한으로 미열람",
        "cpu_xpu_ratio_source_url": "https://www.digitimes.com.tw/research/report/?cnlid=3&n=1&v=20261005-314",
        "per_accelerator_source_kind": "DIGITIMES 10월 7일 원문 표제 확인 · 구독 제한으로 상세 계산 기준 미열람",
        "per_accelerator_source_url": "https://www.digitimes.com/news/a20261005PD216/cpu-demand-commercial-llm-market.html",
        "shipments_as_of": "2026-07-29",
        "ai_server_cpu_2025_million": 3.793,
        "ai_server_cpu_2026_million": 5.349,
        "ai_server_cpu_2027_million": 9.845,
        "ai_server_cpu_2027_yoy_pct": 84.1,
        "all_server_cpu_2027_million": 48.574,
        "arm_all_server_cpu_2027_million": 15.8,
        "arm_all_server_cpu_2027_share_pct": 32.5,
        "shipments_source_kind": "DIGITIMES 7월 29일 직접 발표 자료 · 예측치, 실제 출하 아님",
        "shipments_source_url": "https://gb-www.digitimes.com.tw/about_us/article.asp?news_key=1150023",
    },
    "amd_system": {
        "as_of": "2026-07-23",
        "helios_venice_cpus": 18,
        "helios_mi455x_gpus": 72,
        "official_design_not_global_ratio": True,
        "source_url": AMD_AAI_URL,
        "customer_validation": "Meta 6세대 EPYC 실험실 검증; OpenAI 2026년 4분기 Helios 가동 시작 전망",
    },
    "seen_source_urls": [],
}
CPU_STRUCTURE_SEARCHES = [
    ("google", 'site:cib.bnpparibas/ai-infrastructure agentic CPU 2030'),
    ("bing", 'site:cib.bnpparibas "data centre CPU" "2030"'),
    ("google", 'site:digitimes.com/news CPU accelerator 2027 agentic'),
    ("bing", 'site:digitimes.com "CPU" "per accelerator" "2027"'),
    ("google", '"BNP Paribas" "AMD" "price target" "CPU"'),
    ("bing", 'site:marketscreener.com "BNP Paribas" "AMD" "price target"'),
    ("google", 'site:gb-www.digitimes.com.tw agentic AI 2027 CPU 出货'),
    ("google", 'site:digitimes.com.tw/research/report CPU XPU agentic'),
    ("google", 'site:digitimes.com.tw/research/report CPU XPU 2027 agentic'),
    ("bing", 'site:digitimes.com.tw AI伺服器CPU XPU'),
]

FORECAST_SEARCHES = [
    ("bing", 'site:finvaulta.com/research/bank-of-america "server CPU TAM" agentic AI'),
    ("google", '"Bank of America" "server CPU TAM" agentic AI 2030'),
    ("bing", '"BofA" "server CPU" "agentic AI" 2030 TAM'),
]

VALIDATION_SEARCHES = [
    ("google", 'site:amd.com "agentic AI" ("order book" OR deploy OR validation OR shipments OR revenue OR capacity) CPU'),
    ("google", 'site:intc.com OR site:intel.com server CPU (shipments OR volume OR ASP OR orders OR capacity) AI'),
    ("google", 'site:dell.com OR site:hpe.com OR site:supermicro.com agentic AI CPU server deploy'),
]

OFFICIAL_VALIDATION_DOMAINS = (
    "amd.com",
    "ir.amd.com",
    "intel.com",
    "intc.com",
    "dell.com",
    "hpe.com",
    "supermicro.com",
)

VALIDATION_TERMS = (
    "order book", "orders", "shipment", "shipments", "volume", "revenue", "capacity",
    "deploy", "deployment", "deployments", "validation", "validating", "long-term agreement",
    "lta", "server cpu", "epyc", "xeon", "cloud",
)


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


def rss_url(kind: str, query: str) -> str:
    q = urllib.parse.quote(query)
    if kind == "google":
        return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    return f"https://www.bing.com/search?format=rss&q={q}"


def read_rss(kind: str, query: str) -> list[dict]:
    root = ET.fromstring(fetch(rss_url(kind, query)))
    out = []
    for item in root.findall("./channel/item"):
        title = clean_text(item.findtext("title") or "")
        link = clean_text(item.findtext("link") or "")
        desc = clean_text(item.findtext("description") or "")
        dt = parse_pubdate(clean_text(item.findtext("pubDate") or ""))
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


def direct_url(item: dict) -> str:
    return decode_google_news(item.get("link") or "") if item.get("kind") == "google" else item.get("link") or ""


def article_text(url: str) -> str:
    if not url:
        return ""
    try:
        return clean_text(fetch(url, timeout=18).decode("utf-8", errors="ignore"))[:30000]
    except Exception:
        return ""


def load_json(path: pathlib.Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def number_near(text: str, labels: tuple[str, ...]) -> float | None:
    low = text.lower()
    patterns = [
        r"\$\s*(\d+(?:\.\d+)?)\s*(?:bn|billion)",
        r"(\d+(?:\.\d+)?)\s*(?:USD\s*)?(?:bn|billion)",
    ]
    for label in labels:
        pos = low.find(label.lower())
        if pos < 0:
            continue

        # First prefer the number AFTER the matching label. This prevents a prior
        # sentence's $210.6bn server-CPU TAM from being misread as the following
        # 'AI CPU TAM 180.4bn' value.
        after = text[pos: min(len(text), pos + 240)]
        forward = []
        for pattern in patterns:
            forward.extend(re.finditer(pattern, after, re.I))
        if forward:
            # Choose the physically nearest number after the label, regardless of
            # whether it is written as "$90bn" or "90 USD billion".
            nearest = min(forward, key=lambda m: m.start())
            return float(nearest.group(1))

        # Only if no forward value exists, allow a very short backward window for
        # constructions such as '$90.2bn for agentic AI nodes'.
        before = text[max(0, pos - 90): pos + len(label)]
        backward = []
        for pattern in patterns:
            backward.extend(re.finditer(pattern, before, re.I))
        if backward:
            nearest = max(backward, key=lambda m: m.end())
            return float(nearest.group(1))
    return None


def parse_forecast(text: str) -> dict:
    low = text.lower()
    if not ("server cpu" in low and ("agentic" in low or "agents" in low)):
        return {}

    metrics: dict[str, float] = {}

    total = number_near(text, ("server cpu tam", "server CPU total addressable market", "server cpu market"))
    if total is None:
        m = re.search(r"(?:server cpu[^.]{0,120}?)(?:\$\s*)?(\d+(?:\.\d+)?)\s*(?:bn|billion)[^.]{0,60}?2030", text, re.I)
        if m:
            total = float(m.group(1))
    if total is not None and 80 <= total <= 500:
        metrics["server_cpu_tam_2030_usd_bn"] = total

    agentic = number_near(text, ("agentic ai nodes", "agentic ai cpu racks", "agentic ai", "standalone processors running ai agents"))
    if agentic is not None and 20 <= agentic <= 300:
        metrics["agentic_2030_usd_bn"] = agentic

    ai_cpu = number_near(text, ("ai cpu tam", "AI CPUs grow", "AI CPU"))
    if ai_cpu is not None and 40 <= ai_cpu <= 400:
        metrics["ai_cpu_2030_usd_bn"] = ai_cpu

    compute = number_near(text, ("compute/head", "head node", "AI cluster and head-node"))
    if compute is not None and 20 <= compute <= 300:
        metrics["compute_head_2030_usd_bn"] = compute

    traditional = number_near(text, ("traditional/iaas", "traditional cloud", "traditional CPUs"))
    if traditional is not None and 5 <= traditional <= 150:
        metrics["traditional_iaas_2030_usd_bn"] = traditional

    cagr = re.search(r"(?:server cpu[^.]{0,160}?)(\d+(?:\.\d+)?)%\s*CAGR", text, re.I)
    if cagr:
        metrics["server_cpu_cagr_2026_2030_pct"] = float(cagr.group(1))

    if "server_cpu_tam_2030_usd_bn" in metrics and "agentic_2030_usd_bn" in metrics:
        metrics["agentic_share_pct"] = metrics["agentic_2030_usd_bn"] / metrics["server_cpu_tam_2030_usd_bn"] * 100
    if "server_cpu_tam_2030_usd_bn" in metrics and "ai_cpu_2030_usd_bn" in metrics:
        metrics["ai_cpu_share_pct"] = metrics["ai_cpu_2030_usd_bn"] / metrics["server_cpu_tam_2030_usd_bn"] * 100
    return metrics


def pct_change(new: float, old: float) -> float:
    if not old:
        return 0.0
    return (new / old - 1) * 100


def material_forecast_changes(old: dict, new: dict) -> list[dict]:
    rules = {
        "server_cpu_tam_2030_usd_bn": ("2030 서버 CPU 시장", "pct", 10.0),
        "agentic_2030_usd_bn": ("에이전트형 AI CPU", "pct", 10.0),
        "ai_cpu_2030_usd_bn": ("2030 AI CPU 전체", "pct", 10.0),
        "agentic_share_pct": ("에이전트형 비중", "pp", 5.0),
        "ai_cpu_share_pct": ("AI CPU 비중", "pp", 5.0),
    }
    out = []
    for key, (label, mode, threshold) in rules.items():
        if key not in old or key not in new:
            continue
        before = float(old[key])
        after = float(new[key])
        delta = (after - before) if mode == "pp" else pct_change(after, before)
        if abs(delta) >= threshold:
            out.append({"key": key, "label": label, "mode": mode, "before": before, "after": after, "delta": delta})
    return out


def ratio_changed(old: str, new: str) -> bool:
    def norm(v: str) -> str:
        return re.sub(r"\s+", "", (v or "").replace("≈", "").replace("~", ""))
    return bool(old and new and norm(old) != norm(new))


def is_official_validation(url: str, text: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if not any(host == d or host.endswith("." + d) for d in OFFICIAL_VALIDATION_DOMAINS):
        return False
    low = text.lower()
    cpu_hit = any(k in low for k in ("cpu", "epyc", "xeon"))
    demand_hit = any(k in low for k in VALIDATION_TERMS)
    return cpu_hit and demand_hit


def extract_ratio(text: str) -> str:
    low = text.lower()
    if "agentic" not in low:
        return ""
    # 과거 1:4~8이 같은 문장에 있어도 에이전트형 목표 구조를 우선한다.
    if (
        "1:1 ratio" in low
        or "toward ~1:1" in low
        or "toward 1:1" in low
        or "moving toward a 1:1" in low
        or "1+ cpu : 1 gpu" in low
        or "1+ cpu:1 gpu" in low
    ):
        return "1:1"
    patterns = [
        r"(?:agentic[^.]{0,180}?)(\d+\+?\s*:\s*\d+(?:\s*[-–]\s*\d+)?)",
        r"(\d+\+?\s*CPU\s*:\s*\d+\s*GPU)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            raw = m.group(1)
            nums = re.findall(r"\d+\+?", raw)
            if len(nums) >= 2:
                return f"{nums[0]}:{nums[1]}"
    return ""


def get_fx() -> tuple[float | None, str]:
    try:
        raw = json.loads(fetch("https://api.frankfurter.app/latest?from=USD&to=KRW", timeout=12).decode("utf-8"))
        rate = float((raw.get("rates") or {}).get("KRW"))
        date = str(raw.get("date") or "")
        if 500 < rate < 3000:
            return rate, date
    except Exception:
        pass
    return None, ""


def won_text(usd_bn: float, rate: float | None) -> str:
    if rate is None:
        return ""
    won_trillion = usd_bn * rate / 1000
    if won_trillion >= 1:
        return f"약 {won_trillion:.1f}조원"
    return f"약 {won_trillion * 10000:.0f}억원"


def fmt_usd(usd_bn: float, rate: float | None) -> str:
    krw = won_text(usd_bn, rate)
    return f"{usd_bn:.1f}억달러" if False else f"{usd_bn:.1f}bn달러" + (f"({krw})" if krw else "")


def bn_label(value: float, rate: float | None) -> str:
    # 한국어 표기는 1bn USD = 10억달러
    usd_hundred_million = value * 10
    krw = won_text(value, rate)
    if abs(usd_hundred_million - round(usd_hundred_million)) < 1e-9:
        usd = f"{int(round(usd_hundred_million)):,}억달러"
    else:
        usd = f"{usd_hundred_million:,.1f}억달러"
    return usd + (f"({krw})" if krw else "")


def cpu_structure_observation(title: str, text: str, url: str) -> tuple[str, dict]:
    """Strict publisher-specific extraction. Never compare different issuers."""
    host = (urlparse(url).hostname or "").lower()
    low = (title + " " + text).lower()
    if host == "cib.bnpparibas" or host.endswith(".cib.bnpparibas"):
        if "cpu" not in low or "agentic" not in low:
            return "", {}
        pattern = (
            r"(?:usd|us\$|\$)\s*(\d{1,3}(?:\.\d+)?)\s*billion\s+in\s+2025"
            r"[^.]{0,180}?"
            r"(?:usd|us\$|\$)\s*(\d{1,3}(?:\.\d+)?)\s*billion\s+in\s+2030"
        )
        m = re.search(pattern, low, re.I)
        if m and 10 <= float(m.group(1)) <= 100 and 100 <= float(m.group(2)) <= 600:
            return "bnpp_public", {
                "market_2025_usd_bn": float(m.group(1)),
                "market_2030_usd_bn": float(m.group(2)),
            }
        return "", {}
    # Secondary analyst reporting is not BNP's public AMD-estimate series.
    trusted = ("marketscreener.com", "investors.com", "247wallst.com", "finance.yahoo.com", "gurufocus.com")
    if any(host == d or host.endswith("." + d) for d in trusted):
        if "bnp paribas" not in low or not any(s in low for s in ("amd", "advanced micro devices")):
            return "", {}
        obs = {}
        # Attribute a target only when AMD itself owns the nearby target phrase.
        # The older broad BNP→AMD→target window could silently pick up an
        # unrelated NVIDIA / Arm price target from the same sentence.
        target_patterns = (
            r"bnp paribas[^.!?]{0,200}?\b(?:amd|advanced micro devices)(?:['’]s)?\s+"
            r"(?:stock\s+)?(?:price\s+target|target|pt)\b[^.!?]{0,45}?\b(?:to|at)\s*\$?\s*(\d{1,2},\d{3}|\d{3,4})\b",
            r"bnp paribas[^.!?]{0,200}?\b(?:price\s+target|target|pt)\s+"
            r"(?:on|for)\s+(?:amd|advanced micro devices)\b(?:\s*\([^)]{0,55}\))?"
            r"[^.!?]{0,20}?\b(?:to|at)\s*\$?\s*(\d{1,2},\d{3}|\d{3,4})\b",
        )
        m = next((found for p in target_patterns if (found := re.search(p, low, re.I))), None)
        if m:
            target = float(m.group(1).replace(",", ""))
            if 100 <= target <= 2000:
                obs["amd_target_usd"] = target
        market = re.search(
            r"bnp paribas[^.!?]{0,180}?(?:agentic\s+cpu\s+market|cpu\s+market)[^.!?]{0,130}?"
            r"(?:\$|usd\s*)?(\d{2,3}(?:\.\d+)?)\s*(?:billion|bn)[^.!?]{0,40}?(?:by\s+)?2030",
            low,
            re.I,
        )
        if market and 100 <= float(market.group(1)) <= 600:
            obs["market_2030_usd_bn"] = float(market.group(1))
        return ("bnpp_analyst", obs) if obs else ("", {})
    if (host == "digitimes.com" or host.endswith(".digitimes.com")
            or host == "digitimes.com.tw" or host.endswith(".digitimes.com.tw")):
        if "cpu" not in low:
            return "", {}
        # Original October 5 Chinese report headline specifies CPU:XPU 1:2.3
        # but does not repeat the year; require 2027 only for shipment values.
        ratio_headline = re.search(r"cpu\s*[:：]\s*xpu", low, re.I)
        if "2027" not in low and not ratio_headline:
            return "", {}
        obs = {}
        # DIGITIMES Research's public headline explicitly specifies 2027
        # CPU:XPU=1:2.3. Preserve the *forecast* as a ratio distinct from
        # CPU shipments, cores/sockets and installed hardware.
        ratio = re.search(
            r"(?<![a-z])cpu\s*[:：]\s*xpu[^0-9]{0,45}?1\s*[:：]\s*(\d+(?:\.\d+)?)",
            low, re.I,
        )
        if ratio:
            accelerator_per_cpu = float(ratio.group(1))
            if 0.7 <= accelerator_per_cpu <= 16:
                obs["cpu_xpu_ratio_2027"] = accelerator_per_cpu
        if "accelerator" in low:
            if re.search(r"(?:nearly|almost)\s+(?:twice|double)|nearly\s+twofold", low):
                obs["per_accelerator_cpu_2027"] = "nearly_double"
            elif re.search(r"(?:threefold|three[- ]?times|triple)\s+(?:as many\s+)?cpus?\s+per\s+accelerator", low):
                obs["per_accelerator_cpu_2027"] = "triple"
            elif re.search(r"(?:half|1\.5)\s+(?:as many\s+)?cpus?\s+per\s+accelerator", low):
                obs["per_accelerator_cpu_2027"] = "one_point_five"
        # Only exact AI-server CPU shipments; total server CPUs use a separate denominator.
        m = re.search(
            r"(?:ai[- ]?server\s+cpu|ai\s+servers?\s+cpu|ai\s*(?:伺服器|服務器|服务器)\s*cpu)[^.!?]{0,190}?"
            r"2027[^.!?]{0,90}?(\d+(?:\.\d+)?)\s*(million|万|萬)",
            low,
            re.I,
        )
        if m:
            amount = float(m.group(1)) * (0.01 if m.group(2) in ("万", "萬") else 1.0)
            if 2 <= amount <= 30:
                obs["ai_server_cpu_2027_million"] = round(amount, 4)
        return ("digitimes", obs) if obs else ("", {})
    return "", {}


def cpu_structure_changes(old: dict, observed: dict, issuer: str) -> list[str]:
    """A forecast is comparable only to its own issuer's prior forecast."""
    changes: list[str] = []
    if issuer == "bnpp_public" and "market_2030_usd_bn" in observed:
        before = float(old.get("market_2030_usd_bn") or 0)
        after = float(observed["market_2030_usd_bn"])
        if before and abs(after / before - 1) >= 0.10:
            changes.append(f"BNP 공개자료의 AMD 인용 CPU 시장 전망: {before:.0f}→{after:.0f}십억달러")
    if issuer == "bnpp_analyst":
        for key, title in (("market_2030_usd_bn", "2030 데이터센터 CPU 시장"),
                           ("amd_target_usd", "AMD 목표주가")):
            if key not in observed:
                continue
            before = float(old.get(key) or 0)
            after = float(observed[key])
            if before and abs(after / before - 1) >= 0.10:
                changes.append(f"BNP 애널리스트 {title} 전망 변경 {((after/before)-1)*100:+.1f}%")
    if issuer == "digitimes":
        if "cpu_xpu_ratio_2027" in observed:
            before_ratio = float(old.get("cpu_xpu_ratio_2027") or 0)
            new_ratio = float(observed["cpu_xpu_ratio_2027"])
            if before_ratio and abs(new_ratio / before_ratio - 1) >= 0.10:
                changes.append(
                    f"DIGITIMES 2027 CPU:XPU 전망 변경: 1:{before_ratio:g}→1:{new_ratio:g}"
                )
        if "per_accelerator_cpu_2027" in observed:
            before = str(old.get("per_accelerator_cpu_2027") or "")
            after = str(observed["per_accelerator_cpu_2027"])
            if before and after != before:
                changes.append(f"DIGITIMES 2027 가속기당 CPU 전망 변경: {before}→{after}")
        if "ai_server_cpu_2027_million" in observed:
            before = float(old.get("ai_server_cpu_2027_million") or 0)
            after = float(observed["ai_server_cpu_2027_million"])
            if before and abs(after / before - 1) >= 0.10:
                changes.append(f"DIGITIMES 2027 AI 서버 CPU 출하 전망 변경 {((after/before)-1)*100:+.1f}%")
    return changes


def discover_cpu_structure(now: datetime, previous: dict) -> list[dict]:
    """Inspect only the original BNP/DIGITIMES domains, not republishers."""
    results: list[dict] = []
    seen: set[str] = set(previous.get("seen_source_urls") or [])
    fetched = 0
    for kind, query in CPU_STRUCTURE_SEARCHES:
        try:
            items = read_rss(kind, query)
        except Exception:
            continue
        for item in items:
            url = direct_url(item)
            if not url or url in seen:
                continue
            host = (urlparse(url).hostname or "").lower()
            trusted = ("marketscreener.com", "investors.com", "247wallst.com", "finance.yahoo.com", "gurufocus.com")
            issuer = (
                "bnpp_public" if host == "cib.bnpparibas" or host.endswith(".cib.bnpparibas")
                else "digitimes" if host == "digitimes.com" or host.endswith(".digitimes.com")
                    or host == "digitimes.com.tw" or host.endswith(".digitimes.com.tw")
                else "bnpp_analyst" if any(host == d or host.endswith("." + d) for d in trusted)
                else ""
            )
            if not issuer:
                continue
            published = str(item.get("published_at_kst") or "")[:10]
            baseline_date = str((previous.get(issuer) or {}).get("as_of") or "")
            # Same-day new URLs are new evidence. URL dedupe and revision
            # comparison prevent replaying the previous numeric baseline.
            if not published or (baseline_date and published < baseline_date):
                continue
            if fetched >= 6:
                continue
            fetched += 1
            body = article_text(url)
            provider, obs = cpu_structure_observation(item.get("title") or "", body or item.get("description") or "", url)
            seen.add(url)
            if provider and obs:
                results.append({"issuer": provider, "metrics": obs, "url": url, "as_of": published})
    previous["seen_source_urls"] = sorted(seen)[-100:]
    return results


def cpu_structure_block(state: dict, fx: float, changes: list[str]) -> str:
    bp = state["bnpp_public"]
    ba = state["bnpp_analyst"]
    di = state["digitimes"]
    am = state["amd_system"]
    fmt = lambda x: html.escape(bn_label(float(x), fx))
    def usd_shares(n: float) -> str:
        return f"\${n:,.0f}(약 {n*fx:,.0f}원)".replace("\\$", "$")
    lines = ["<b>에이전틱 AI·데이터센터 CPU 수요 구조 감시</b>"]
    if changes:
        lines += ["• 신규 변화: " + html.escape("; ".join(changes))]
    else:
        lines += ["• 신규 기준선: 시장 전망과 실제 CPU 공급·양산 검증을 분리"]
    lines += [
        "• BNP 공개자료의 AMD 추정 인용: 2025년 " + fmt(bp["market_2025_usd_bn"])
        + " → 2030년 " + fmt(bp["market_2030_usd_bn"]),
        "• BNP 애널리스트 별도 보도: 2030년 " + fmt(ba["market_2030_usd_bn"])
        + " · 원문 리포트 미열람 / 2025년 " + fmt(ba["market_2025_user_claim_usd_bn"]) + "는 사용자 제공치로 공식 확인 전",
        "• AMD 목표주가: BNP 보도상 " + usd_shares(ba["amd_prior_target_usd"])
        + "→" + usd_shares(ba["amd_target_usd"])
        + " · Arm 목표주가 " + usd_shares(ba["arm_target_user_claim_usd"]) + "는 원문 근거 확인 전이므로 확정 알림에서 제외",
        "• DIGITIMES: 2027년 가속기당 CPU 거의 2배 전망(유료 기사 표제)"
        + (
            f" · 연구 표제 CPU:XPU <b>1:{float(di['cpu_xpu_ratio_2027']):g}</b>"
            f"(가속기당 CPU 약 {1/float(di['cpu_xpu_ratio_2027']):.2f}개, 전망치·상세 기준연도 미열람)"
            if di.get("cpu_xpu_ratio_2027") else ""
        )
        + " · <b>코어 수·소켓 수·실제 출하가 각각 2배라는 의미는 아님</b>",
        "• DIGITIMES 공개 출하 전망: 2027년 AI 서버 CPU "
        + f"{float(di['ai_server_cpu_2027_million'])*100:,.1f}만개(+{float(di['ai_server_cpu_2027_yoy_pct']):.1f}% 전년 대비)"
        + f" / 전체 서버 CPU {float(di['all_server_cpu_2027_million'])*100:,.1f}만개"
        + f" / Arm 계열 전체 서버 CPU {float(di['arm_all_server_cpu_2027_million'])*100:,.0f}만개({float(di['arm_all_server_cpu_2027_share_pct']):.1f}%)",
        "• 실제 설계 검증: AMD Helios 1랙당 Venice CPU "
        + str(am["helios_venice_cpus"]) + "개·MI455X GPU " + str(am["helios_mi455x_gpus"])
        + "개(물리 1:4). 별도 CPU 전용 랙 수요와 혼동 금지",
        "• 후속 확인: CPU 발주·소켓·실출하→DDR5 RDIMM·서버용 FC-BGA/ABF·eSSD 주문 연결"
        + " · 2nm 수율·ABF·전원·냉각 병목 및 가상화 최적화에 따른 수요 미달 점검",
        '• <a href="' + html.escape(bp["source_url"], quote=True) + '">BNP 공식 공개자료</a>'
        + ' · <a href="' + html.escape(ba["source_url"], quote=True) + '">BNP 애널리스트 2차 보도</a>'
        + ' · <a href="' + html.escape(di["per_accelerator_source_url"], quote=True) + '">DIGITIMES 가속기당 전망</a>'
        + ' · <a href="' + html.escape(di["shipments_source_url"], quote=True) + '">DIGITIMES 출하 전망</a>'
        + ' · <a href="' + html.escape(di["cpu_xpu_ratio_source_url"], quote=True) + '">DIGITIMES 연구 1:2.3</a>'
        + ' · <a href="' + html.escape(am["source_url"], quote=True) + '">AMD 실제 설계 자료</a>',
    ]
    return "\n".join(lines) + "\n"


def snapshot_block(state: dict, fx: float | None, fx_date: str, changed: list[dict], ratio_change: tuple[str, str] | None, validation: list[dict], standalone: bool) -> str:
    m = state.get("metrics") or {}

    if not standalone:
        lines = ["<b>CPU·에이전트형 AI</b>"]
        change_bits = []
        for ch in changed[:3]:
            if ch["mode"] == "pp":
                change_bits.append(
                    f"{ch['label']} {ch['before']:.1f}%→{ch['after']:.1f}% ({ch['delta']:+.1f}%p)"
                )
            else:
                change_bits.append(
                    f"{ch['label']} {bn_label(ch['before'], fx)}→{bn_label(ch['after'], fx)} ({ch['delta']:+.1f}%)"
                )
        if ratio_change:
            change_bits.append(f"CPU:GPU {ratio_change[0]}→{ratio_change[1]}")
        if validation:
            change_bits.append("공식 수요검증 " + str(validation[0].get("title") or "확인"))
        if change_bits:
            lines.append("• 변화: " + " / ".join(html.escape(x) for x in change_bits))

        total = float(m.get("server_cpu_tam_2030_usd_bn") or 0)
        agent = float(m.get("agentic_2030_usd_bn") or 0)
        agent_share = float(m.get("agentic_share_pct") or 0)
        base = []
        if total:
            base.append(f"2030 서버 CPU {bn_label(total, fx)}")
        if agent:
            base.append(f"에이전트형 {bn_label(agent, fx)}({agent_share:.1f}%)")
        if base:
            lines.append("• 기준: " + " / ".join(html.escape(x) for x in base))
        lines.append("• 구조: CPU:GPU 챗봇형 1:4~8 → 에이전트형 약 1:1 방향")
        lines.append("• 의미: CPU 주문·출하가 늘면 DDR5 RDIMM·기업용 SSD·FC-BGA/ABF가 동반 수혜")
        lines.append("• 다음: AMD·Intel 주문·출하 / OEM 서버 주문 / CPU:GPU 실제 배치비율")
        if state.get("source"):
            lines.append(f'• <a href="{html.escape(str(state["source"]), quote=True)}">BofA 전망</a> · <a href="{html.escape(AMD_RATIO_URL, quote=True)}">AMD 공식</a>')
        else:
            lines.append(f'• <a href="{html.escape(AMD_RATIO_URL, quote=True)}">AMD 공식 근거</a>')
        return "\n".join(lines).strip() + "\n"

    lines = ["<b>🚨 CPU·에이전트형 AI 구조 변화</b>", "", "<b>변화</b>"]
    if changed:
        for ch in changed[:4]:
            if ch["mode"] == "pp":
                lines.append(
                    f"• {html.escape(ch['label'])}: {ch['before']:.1f}% → {ch['after']:.1f}% "
                    f"({ch['delta']:+.1f}%p)"
                )
            else:
                lines.append(
                    f"• {html.escape(ch['label'])}: {html.escape(bn_label(ch['before'], fx))} "
                    f"→ {html.escape(bn_label(ch['after'], fx))} ({ch['delta']:+.1f}%)"
                )
    if ratio_change:
        lines.append(f"• CPU:GPU 구조: {html.escape(ratio_change[0])} → {html.escape(ratio_change[1])}")
    if validation:
        for item in validation[:2]:
            lines.append(f"• 공식 검증: {html.escape(item.get('title') or '수요 신호')}")

    total = float(m.get("server_cpu_tam_2030_usd_bn") or 0)
    agent = float(m.get("agentic_2030_usd_bn") or 0)
    agent_share = float(m.get("agentic_share_pct") or 0)

    lines += ["", "<b>현재 기준선</b>"]
    baseline_bits = []
    if total:
        baseline_bits.append(f"2030 서버 CPU {bn_label(total, fx)}")
    if agent:
        baseline_bits.append(f"에이전트형 {bn_label(agent, fx)}({agent_share:.1f}%)")
    if baseline_bits:
        lines.append("• " + " / ".join(html.escape(x) for x in baseline_bits))
    lines.append("• CPU:GPU: 챗봇형 1:4~8 → 에이전트형 약 1:1 방향")

    lines += ["", "<b>의미</b>"]
    lines.append(
        "• 에이전트형 AI 확산이 실제 서버 CPU 주문·출하로 이어지면 "
        "DDR5 RDIMM·기업용 SSD·FC-BGA/ABF·네트워크 수요가 함께 커집니다."
    )

    lines += ["", "<b>다음 확인</b>"]
    lines.append("• AMD·Intel CPU 주문·출하 / OEM 서버 주문 / DDR5·eSSD / CPU:GPU 실제 배치비율")

    if state.get("source"):
        lines.append(f'• <a href="{html.escape(str(state["source"]), quote=True)}">BofA 전망 확인 경로</a>')
    lines.append(f'• <a href="{html.escape(AMD_RATIO_URL, quote=True)}">AMD 공식 근거</a>')
    return "\n".join(lines).strip() + "\n"

def discover_forecasts(now: datetime, cutoff: str) -> list[dict]:
    out = []
    seen = set()
    fetch_budget = 6
    fetched = 0
    for kind, query in FORECAST_SEARCHES:
        try:
            items = read_rss(kind, query)
        except Exception:
            continue
        for item in items:
            url = direct_url(item)
            if not url or url in seen:
                continue
            seen.add(url)
            published = item.get("published_at_kst") or ""
            date = published[:10] if published else ""
            if cutoff and date and date <= cutoff:
                continue
            try:
                dt = datetime.fromisoformat(published) if published else None
            except Exception:
                dt = None
            if dt and dt < now - timedelta(days=120):
                continue
            base = clean_text(f"{item.get('title','')} {item.get('description','')}")
            base_low = base.lower()
            if not ("server cpu" in base_low and ("agentic" in base_low or "agents" in base_low)):
                continue
            # This legacy series is BofA-only: never replace BofA with BNP, Citi or DIGITIMES.
            if not ("bofa" in base_low or "bank of america" in base_low):
                continue
            if fetched >= fetch_budget:
                continue
            fetched += 1
            body = article_text(url)
            text = clean_text(f"{base} {body}")
            metrics = parse_forecast(text)
            if not metrics:
                continue
            out.append({**item, "url": url, "metrics": metrics, "text": text})
    out.sort(key=lambda x: x.get("published_at_kst") or "", reverse=True)
    return out


def discover_validation(now: datetime, cutoff: str, seen_urls: set[str]) -> list[dict]:
    out = []
    seen = set(seen_urls)
    fetch_budget = 8
    fetched = 0
    for kind, query in VALIDATION_SEARCHES:
        try:
            items = read_rss(kind, query)
        except Exception:
            continue
        for item in items:
            url = direct_url(item)
            if not url or url in seen:
                continue
            published = item.get("published_at_kst") or ""
            date = published[:10] if published else ""
            # Date-only cutoffs would discard reports published *later today*
            # after the first scan. Revisit a 3-day window, dedupe by URL,
            # and retry on transient feed failure.
            if date:
                try:
                    if datetime.fromisoformat(date).date() < now.date() - timedelta(days=3):
                        continue
                except ValueError:
                    continue
            base = clean_text(f"{item.get('title','')} {item.get('description','')}")
            base_low = base.lower()
            if not any(k in base_low for k in ("cpu", "epyc", "xeon", "agentic")):
                continue
            if not any(k in base_low for k in VALIDATION_TERMS):
                continue
            if fetched >= fetch_budget:
                continue
            fetched += 1
            body = article_text(url)
            text = clean_text(f"{base} {body}")
            if not is_official_validation(url, text):
                continue
            out.append({**item, "url": url, "ratio": extract_ratio(text)})
            seen.add(url)
    out.sort(key=lambda x: x.get("published_at_kst") or "")
    return out


def main() -> None:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    committed = load_json(STATE_PATH)
    pending = load_json(PENDING_PATH)
    previous = committed.get("agentic_cpu_demand") or BASELINE
    latest = json.loads(json.dumps(previous))

    forecast_candidates = discover_forecasts(now, str(previous.get("as_of") or BASELINE["as_of"]))
    forecast_changes: list[dict] = []
    ratio_change: tuple[str, str] | None = None
    seen_forecast = set(previous.get("seen_forecast_urls") or [])

    previous_as_of = str(previous.get("as_of") or BASELINE["as_of"])
    for candidate in forecast_candidates:
        url = candidate.get("url") or ""
        if url in seen_forecast:
            continue
        candidate_date = str(candidate.get("published_at_kst") or "")[:10]
        # 과거 리포트·재인용을 새 전망 하향/상향으로 오인하지 않는다.
        if not candidate_date or candidate_date < previous_as_of:
            continue
        new_metrics = dict(previous.get("metrics") or {})
        new_metrics.update(candidate.get("metrics") or {})
        changes = material_forecast_changes(previous.get("metrics") or {}, new_metrics)
        if changes:
            latest["metrics"] = new_metrics
            latest["source"] = url
            latest["source_kind"] = "BofA 전망 관련 최신 공개자료"
            latest["as_of"] = (candidate.get("published_at_kst") or now.isoformat())[:10]
            forecast_changes = changes
            break

    for c in forecast_candidates:
        if c.get("url"):
            seen_forecast.add(c["url"])
    latest["seen_forecast_urls"] = sorted(seen_forecast)[-120:]

    # CPU:GPU 구조는 새 공식 AMD/Intel/OEM 근거가 나왔을 때만 승격한다.
    ratio_before = str((previous.get("cpu_gpu_ratio") or {}).get("agentic") or "")
    ratio_after = ratio_before

    seen_validation = set(previous.get("seen_validation_urls") or [])
    validation = discover_validation(now, str(previous.get("last_validation_cutoff") or ""), seen_validation)
    for item in validation:
        if item.get("url"):
            seen_validation.add(item["url"])
        candidate_ratio = str(item.get("ratio") or "")
        if candidate_ratio and ratio_changed(ratio_after, candidate_ratio):
            ratio_after = candidate_ratio

    if ratio_changed(ratio_before, ratio_after):
        latest.setdefault("cpu_gpu_ratio", dict(previous.get("cpu_gpu_ratio") or {}))
        latest["cpu_gpu_ratio"]["agentic"] = ratio_after
        ratio_change = (ratio_before, ratio_after)

    latest["seen_validation_urls"] = sorted(seen_validation)[-200:]
    latest["last_validation_cutoff"] = now.date().isoformat()
    latest["last_checked_at_kst"] = now.isoformat(timespec="seconds")

    # Source-separated agentic CPU evidence is stored inside the existing Rubin
    # pending state; a first-install baseline is one-shot and not a fake revision.
    structure_old = previous.get("cpu_structure") or {}
    structure_first_install = int(previous.get("cpu_structure_track_version") or 0) < CPU_STRUCTURE_TRACK_VERSION
    structure_latest = json.loads(json.dumps(CPU_STRUCTURE_BASELINE))
    for provider in ("bnpp_public", "bnpp_analyst", "digitimes", "amd_system"):
        structure_latest[provider].update(structure_old.get(provider) or {})
    structure_latest["seen_source_urls"] = list(structure_old.get("seen_source_urls") or [])
    structure_events: list[str] = []
    for entry in discover_cpu_structure(now, structure_latest):
        provider = entry["issuer"]
        new_metrics = entry["metrics"]
        changes = cpu_structure_changes(structure_latest.get(provider) or {}, new_metrics, provider)
        if not changes:
            continue
        if provider == "bnpp_analyst" and "amd_target_usd" in new_metrics:
            structure_latest[provider]["amd_prior_target_usd"] = structure_latest[provider]["amd_target_usd"]
        structure_latest[provider].update(new_metrics)
        structure_latest[provider]["as_of"] = entry["as_of"]
        structure_latest[provider]["source_url"] = entry["url"]
        structure_events.extend(changes)
    latest["cpu_structure"] = structure_latest
    latest["cpu_structure_track_version"] = CPU_STRUCTURE_TRACK_VERSION

    fx, fx_date = get_fx()
    existing_alert = ALERT_PATH.read_text(encoding="utf-8").strip() if ALERT_PATH.exists() else ""
    cpu_material = bool(forecast_changes or ratio_change or validation or structure_first_install or structure_events)
    if (structure_first_install or structure_events) and fx is None:
        # Fail closed; neither USD figures nor an unacknowledged baseline may leak.
        raise RuntimeError("CPU structure alert requires verified USD/KRW conversion")

    if cpu_material:
        blocks = []
        if forecast_changes or ratio_change or validation:
            blocks.append(snapshot_block(latest, fx, fx_date, forecast_changes, ratio_change, validation, standalone=not bool(existing_alert)))
        if structure_first_install or structure_events:
            blocks.append(cpu_structure_block(structure_latest, fx, structure_events))
        merged = "\n\n".join([part for part in (existing_alert, *blocks) if part]).strip()
        ALERT_PATH.write_text(merged + "\n", encoding="utf-8")
    # 다른 부품 알림이 이미 있어도 CPU 쪽에 새 사건이 없으면 BofA 기준선을 반복 첨부하지 않는다.

    pending["agentic_cpu_demand"] = latest
    write_json(PENDING_PATH, pending)
    print(
        "agentic_cpu_watch=true "
        f"forecast_changes={len(forecast_changes)} ratio_change={str(bool(ratio_change)).lower()} "
        f"validation_signals={len(validation)} structure_initial={str(structure_first_install).lower()} "
        f"structure_changes={len(structure_events)} alert={str(cpu_material or bool(existing_alert)).lower()}"
    )


if __name__ == "__main__":
    main()
