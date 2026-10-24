#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

OUT = Path("out")
STATE = Path("data/us_data_center_cancellation_risk_state.json")
ALERT = OUT / "us_data_center_cancellation_risk_alert.txt"
PENDING = OUT / "us_data_center_cancellation_risk_pending_state.json"
STATUS = OUT / "us_data_center_cancellation_risk_status.md"

DCK_RIPPLE = "https://www.datacenterknowledge.com/energy-power-supply/the-ripple-effect-of-data-center-project-cancellations-and-delays"
CAPGEMINI = "https://www.capgemini.com/insights/research-library/data-centers-and-electricity-demand/"
FERC_LARGE_LOAD = "https://www.ferc.gov/news-events/news/ferc-launches-aggressive-targeted-action-speed-large-load-integration"
FERC_ROSNER = "https://www.ferc.gov/news-events/news/commissioner-rosners-remarks-large-load-show-cause-orders-e-7-e-12-june-18-2026"
FERC_PJM_COST = "https://www.ferc.gov/news-events/news/commissioner-changs-concurrence-transmission-security-agreement-between-peco"
FT_OCT18_URL = "https://www.ft.com/content/9ea5a37d-15c9-4d5b-94d6-719048c9cd3c"
FT_OFFICIAL_POST = "https://bsky.app/profile/financialtimes.com/post/3my4rbhlidz2h"
NSCALE_REUTERS = "https://www.reuters.com/business/media-telecom/microsoft-pulls-out-uk-data-center-deal-with-nscale-telegraph-reports-2026-10-18/"
NSCALE_OFFICIAL_2025 = "https://www.nscale.com/press-releases/nscale-uk-ai-infrastructure-announcement"
NSCALE_MSFT_OTHER_REGIONS = "https://www.nscale.com/press-releases/nscale-microsoft-2025"
NSCALE_EVENT_DAY_UTC = dt.datetime(2026, 10, 18, 10, 1, tzinfo=dt.timezone.utc)
NSCALE_EVENT_MAX_AGE_HOURS = 72
NSCALE_ANCHOR_KEY = "nscale-microsoft-loughton-reported-termination-2026-10-18"

OPENAI_STARGATE_OFFICIAL = "https://openai.com/index/announcing-the-stargate-project/"
FT_OCT18_ANNOUNCED_UTC = dt.datetime(2026, 10, 18, 4, 26, 58, tzinfo=dt.timezone.utc)
FT_CURRENT_STORY_MAX_AGE_HOURS = 72
FINANCING_NEWS_MAX_AGE_HOURS = 48

# Verified reference points. The restudy duration is an industry-experience range
# quoted by Data Center Knowledge, not a statutory nationwide deadline.
BASELINE = {
    "phantom_load_pct": 19.0,
    "restudy_min_months": 6,
    "restudy_one_year_plus": True,
    "pjm_2024_dc_transmission_projects": 130,
    "pjm_2024_dc_transmission_usd_b": 4.3,
    "cost_recovery_agreement": True,
    "escalating_readiness_requirements": True,
}

TRUSTED_DOMAINS = (
    "ferc.gov", "federalregister.gov", "pjm.com", "capgemini.com",
    "datacenterknowledge.com", "reuters.com", "utilitydive.com", "rtoinsider.com",
    "datacenterdynamics.com", "publicpower.org", "bisnow.com",
    "ft.com", "wsj.com", "axios.com", "bloomberg.com",
    "morningstar.com", "sec.gov", "finra.org", "spglobal.com", "fitchratings.com", "moodys.com",
)

NEWS_QUERIES = (
    'data center project cancellation delay interconnection restudy stranded cost utility',
    'data center cost recovery agreement FERC large load readiness financial security site control',
    'data center phantom load forecast utility cancellation transmission substation',
    'data center restudy interconnection capacity reassignment queue delay',
    'hyperscale data center withdraw cancel delay transmission utility project',
    'data center developer credit debt financing bond yields project construction delays',
    'data center finance IPO delayed loan funding financial close power permit 2026',
    'AI infrastructure financing debt project delays data centers US 2026',
    'data center lease amendment delivery penalties cost overrun tenant termination lender 2026',
    'data center refinancing credit spread covenant default investor bond yields 2026',
    '"Microsoft" "Nscale" "Loughton" data centre contract termination grid Reuters Telegraph',
    '"Nscale" "Loughton" "Microsoft" power connection withdrawal customer alternative 2026',
    # Independent AI credit lane: issuer debt, project liens, and actual lender exposure.
    '"CoreWeave" unsecured notes bonds yield credit spread 2026',
    '"CoreWeave" "Applied Digital" secured bonds yield spread',
    '"APLD ComputeCo" secured bonds trading yield',
    '"Applied Digital" Ellendale bond downgrade spread',
    '"CoreWeave" global bank exposure losses lending credit risks',
    '"AI data center" bond refinancing collateral lender contagion',
)

HEADERS = {"User-Agent": "khs-watch/1.0 (+https://github.com/qedgwangju-dot/khs-watch)"}
FORMAT_VERSION = 1
NEWS_ALERT_MAX_AGE_DAYS = 7
SEEN_ID_LIMIT = 5000


def fetch(url: str, timeout: int = 25):
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def sig(*parts: str) -> str:
    return hashlib.sha256("\n".join(str(x) for x in parts).encode("utf-8")).hexdigest()[:20]


def h(text) -> str:
    return html.escape(str(text), quote=True)


def a(label: str, url: str) -> str:
    return f'<a href="{h(url)}">{h(label)}</a>'


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def domain_of(url: str) -> str:
    return urllib.parse.urlparse(url or "").netloc.lower().replace("www.", "")


def trusted(domain: str) -> bool:
    return any(domain == d or domain.endswith("." + d) for d in TRUSTED_DOMAINS)


def has_korean(text: str) -> bool:
    return bool(re.search(r"[가-힣]", text or ""))


def fx_rate(old=None):
    sources = [
        ("https://open.er-api.com/v6/latest/USD", lambda d: d["rates"]["KRW"], "ER-API"),
        ("https://api.frankfurter.app/latest?from=USD&to=KRW", lambda d: d["rates"]["KRW"], "Frankfurter"),
    ]
    for url, parser, name in sources:
        try:
            v = float(parser(fetch(url, 15).json()))
            if 500 < v < 3000:
                return v, name
        except Exception:
            pass
    if old:
        return float(old), "직전 저장값"
    return None, "조회 실패"


def krw_from_usd(usd: float, fx: float) -> str:
    eok = round(usd * fx / 100_000_000)
    jo, rem = divmod(eok, 10000)
    if jo and rem:
        return f"약 {jo:,}조 {rem:,}억원"
    if jo:
        return f"약 {jo:,}조원"
    return f"약 {rem:,}억원"


def dollar_values(text: str) -> list[float]:
    low = (text or "").lower().replace(",", "")
    vals = []
    pats = (
        (r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*(?:trillion|tn|tr)\b", 1e12),
        (r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*(?:billion|bn|b)\b", 1e9),
        (r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*(?:million|mn|m)\b", 1e6),
    )
    for pat, mult in pats:
        for m in re.finditer(pat, low, re.I):
            try:
                vals.append(float(m.group(1)) * mult)
            except Exception:
                pass
    return vals


def money_suffix(text: str, fx: float) -> str:
    vals = dollar_values(text)
    if not vals:
        return ""
    return " · " + ", ".join(krw_from_usd(v, fx) for v in vals[:2])


def extract_scale_mw(text: str) -> float:
    low = (text or "").lower().replace(",", "")
    vals = []
    vals += [float(x) for x in re.findall(r"(?<![a-z0-9])([0-9]+(?:\.[0-9]+)?)\s*mw\b", low)]
    vals += [float(x) * 1000 for x in re.findall(r"(?<![a-z0-9])([0-9]+(?:\.[0-9]+)?)\s*gw\b", low)]
    return max(vals + [0.0])


def extract_percent(text: str) -> float:
    vals = []
    for x in re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*%", text or ""):
        try:
            vals.append(float(x))
        except Exception:
            pass
    return max(vals + [0.0])


def translate_google(text: str) -> str | None:
    if not text or has_korean(text):
        return text
    try:
        url = "https://translate.googleapis.com/translate_a/single?" + urllib.parse.urlencode({
            "client": "gtx", "sl": "auto", "tl": "ko", "dt": "t", "q": text,
        })
        data = fetch(url, 15).json()
        out = "".join(seg[0] for seg in (data[0] or []) if isinstance(seg, list) and seg and isinstance(seg[0], str))
        out = normalize(out)
        return out if has_korean(out) else None
    except Exception:
        return None


def source_label(source: str, url: str = "") -> str:
    s = f"{source} {domain_of(url)}".lower()
    mapping = (
        ("ferc", "FERC"), ("federal register", "미국 연방관보"), ("pjm", "PJM"),
        ("capgemini", "Capgemini"), ("datacenterknowledge", "Data Center Knowledge"),
        ("reuters", "Reuters"), ("utilitydive", "Utility Dive"),
        ("financial times", "Financial Times"), ("ft.com", "Financial Times"),
        ("wall street journal", "Wall Street Journal"), ("axios", "Axios"),
        ("bloomberg", "Bloomberg"),
        ("rtoinsider", "RTO Insider"), ("datacenterdynamics", "Data Center Dynamics"),
        ("publicpower", "Public Power"), ("bisnow", "Bisnow"),
    )
    for key, label in mapping:
        if key in s:
            return label
    return normalize(source)[:40] or domain_of(url)[:40]



def ai_credit_signal(title: str) -> str | None:
    """Do not call bank research opinions realized bank losses or coupons market yields."""
    low = normalize(html.unescape(title)).lower()
    ai = any(k in low for k in (
        "coreweave", "applied digital", "apld computeco", "ellendale",
        "ai data center", "ai data centre", "ai infrastructure", "neocloud",
    ))
    debt = any(k in low for k in (
        "bond", "notes", "debt", "credit", "lender", "loan", "yield", "spread",
        "financing", "refinancing", "default", "collateral",
    ))
    if not (ai and debt):
        return None
    change = any(k in low for k in (
        "yield", "spread", "selloff", "sell-off", "slump", "rising", "falls",
        "surge", "jump", "widen", "narrow", "downgrad", "upgrad", "default",
        "distress", "refinanc", "financing", "loss", "exposure", "borrow",
        "lending", "credit risk", "funding", "notes offering",
    ))
    if not change:
        return None
    if any(k in low for k in ("bank", "lender", "private credit")) and any(
        k in low for k in ("exposure", "loss", "credit risk", "contagion", "default")
    ):
        return "은행 대출·익스포저 보도(실제 손실 여부 별도 확인)"
    if "coreweave" in low and any(k in low for k in ("applied digital", "apld computeco", "ellendale")):
        return "발행사 회사채 대 시설 담보채 차별화"
    if "coreweave" in low:
        return "CoreWeave 발행사 신용"
    if any(k in low for k in ("applied digital", "apld computeco", "ellendale")):
        return "Applied Digital 프로젝트 금융"
    return "AI 인프라 금융시장"


def ai_credit_gap_single_headline(title: str) -> int | None:
    """Only compute an unadjusted headline comparison when both yields are explicit."""
    low = normalize(title).lower()
    cr = re.search(r"coreweave.{0,105}?\byields?\s*(?:of|at|near|around|roughly|about)?\s*(\d{1,2}(?:\.\d+)?)\s*%", low)
    ap = re.search(r"(?:applied digital|apld computeco).{0,105}?\byields?\s*(?:of|at|near|around|roughly|about)?\s*(\d{1,2}(?:\.\d+)?)\s*%", low)
    if not (cr and ap):
        return None
    a, b = float(cr.group(1)), float(ap.group(1))
    return round((a - b) * 100) if 0 < a < 40 and 0 < b < 40 else None


def classify(text: str) -> str:
    low = (text or "").lower().replace("data-center", "data center").replace("data-centre", "data centre")
    if all(x in low for x in ("microsoft", "nscale")) and any(x in low for x in ("loughton", "essex")) and any(
        x in low for x in ("pulls out", "pulled out", "pull out", "withdraw", "terminat", "cancel", "scrap", "axes")
    ):
        # Contract withdrawal reporting is not a cancelled data-center project,
        # not an official Microsoft termination announcement.
        return "고객 이용계약 철회 보도"
    if ai_credit_signal(low):
        return "AI 채권·담보채 신용변화"
    # Financial pipeline risk is distinct from an actual cancelled project.
    if any(k in low for k in ("data center", "data centre", "datacenter", "ai infrastructure")) and any(
        k in low for k in (
            "financial", "financing", "funding", "credit", "bond", "borrowing",
            "debt", "liquidity", "ipo", "investor", "fundraise", "fray",
            "funding crunch", "construction loan", "cost overrun",
            "lease termination", "tenant walk away", "financial close",
        )
    ):
        return "자금조달·계획 실현 위험"
    if any(k in low for k in ("cost recovery agreement", "transmission security agreement", "financial security", "site control", "readiness requirement")):
        return "비용보호·준비도 규칙"
    if any(k in low for k in ("phantom load", "speculative load", "duplicate request", "double counting", "load forecast")):
        return "Phantom load·수요전망"
    if any(k in low for k in ("restudy", "re-study", "reassign", "reassignment", "fresh study", "new study")):
        return "재심사·접속승계"
    if any(k in low for k in ("stranded", "rate base", "cost allocation", "sunk cost", "deposit", "clawback")):
        return "매몰·송전비용"
    if any(k in low for k in ("cancel", "cancelled", "canceled", "withdraw", "walk away", "abandon", "delay", "postpone", "suspend")):
        return "프로젝트 취소·지연"
    return "기타"


def is_meaningful(title: str, source: str, domain: str) -> bool:
    low = f"{title} {source}".lower().replace("data-center", "data center").replace("data-centre", "data centre")
    theme = classify(low)
    if theme == "AI 채권·담보채 신용변화":
        return trusted(domain)
    if theme == "고객 이용계약 철회 보도":
        # A named customer exit at 50MW is material even below the generic
        # US project cancellation screen of 250MW.
        return trusted(domain) and all(x in low for x in ("microsoft", "nscale")) and any(
            x in low for x in ("loughton", "essex")
        )
    if theme == "기타":
        return False

    # Do not infer a data center development setback from generic AI financing.
    if theme == "자금조달·계획 실현 위험":
        context = any(k in low for k in ("data center", "data centre", "datacenter", "ai infrastructure"))
        adverse = any(k in low for k in (
            "fray", "delay", "postpone", "withdraw", "cancel", "default", "distress",
            "bond sell", "sell-off", "selloff", "downgrad", "worsen", "slump",
            "cost overrun", "risk", "concern", "financing crunch", "funding gap",
            "funding shortfall", "under pressure", "rising yield", "debt burden",
            "repayment", "credit squeeze", "walk away", "termination",
            "financing fail", "credit spread", "lease amendment",
        ))
        # A financing facility closing is progress, not an adverse-risk alert.
        return context and trusted(domain) and adverse

    official = domain.endswith("ferc.gov") or domain.endswith("federalregister.gov") or domain.endswith("pjm.com")
    if official and theme in {"비용보호·준비도 규칙", "Phantom load·수요전망", "매몰·송전비용", "재심사·접속승계"}:
        return True

    dc_context = any(k in low for k in ("data center", "data centre", "hyperscale", "large load", "ai campus", "ai factory"))
    if not dc_context:
        return False

    if theme == "프로젝트 취소·지연":
        scale = extract_scale_mw(low)
        money = max(dollar_values(low) + [0.0])
        # Prefer large projects; trusted specialist outlets may omit MW in the headline.
        return scale >= 250 or money >= 100e6 or domain in {
            "datacenterknowledge.com", "reuters.com", "utilitydive.com", "rtoinsider.com", "bisnow.com"
        }
    if theme == "재심사·접속승계":
        return True
    if theme == "매몰·송전비용":
        money = max(dollar_values(low) + [0.0])
        return money >= 100e6 or any(k in low for k in ("stranded", "rate base", "cost allocation"))
    if theme == "Phantom load·수요전망":
        return extract_percent(low) >= 10 or extract_scale_mw(low) >= 1000 or "phantom load" in low
    if theme == "비용보호·준비도 규칙":
        return True
    return False


def translate_title(text: str, theme: str, source: str) -> str:
    clean = normalize(html.unescape(text))
    # Strip common source suffix from Google News title.
    clean = re.sub(r"\s+-\s+[^-]{2,80}$", "", clean).strip()
    if has_korean(clean):
        return clean
    out = translate_google(clean)
    if out:
        replacements = {
            "데이터 센터": "데이터센터",
            "대규모 부하": "대형부하",
            "재 연구": "재심사",
            "재연구": "재심사",
            "좌초 비용": "매몰비용",
            "그리드": "전력망",
        }
        for old, new in replacements.items():
            out = out.replace(old, new)
        return out
    labels = {
        "프로젝트 취소·지연": "대형 데이터센터 프로젝트 취소·지연 관련 신규 자료",
        "재심사·접속승계": "데이터센터 계통연계 재심사·접속승계 관련 신규 자료",
        "매몰·송전비용": "데이터센터 매몰비용·송전비용 관련 신규 자료",
        "Phantom load·수요전망": "데이터센터 Phantom load·수요전망 관련 신규 자료",
        "비용보호·준비도 규칙": "대형부하 비용보호·준비도 규칙 관련 신규 자료",
        "자금조달·계획 실현 위험": "데이터센터 자금조달·사업 실현 위험 관련 신규 자료",
        "AI 채권·담보채 신용변화": "AI 발행사 회사채·프로젝트 담보채 신용위험 관련 신규 자료",
    }
    return f"{source} · {labels.get(theme, '데이터센터 취소·지연 위험 관련 신규 자료')}"


def anchored_ft_oct18_event(now: dt.datetime | None = None) -> dict | None:
    """One-time, time-bounded first-party FT headline previously independently verified.

    The original FT article is paywalled: quoted project counts and the viability
    share below must remain attributed estimates, not independently verified facts.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    age = (now - FT_OCT18_ANNOUNCED_UTC).total_seconds() / 3600
    if age < 0 or age > FT_CURRENT_STORY_MAX_AGE_HOURS:
        return None
    return {
        "id": sig("ft-oct18-ai-infrastructure-finance", FT_OCT18_URL),
        "title": "America's $10tn AI infrastructure boom is starting to fray",
        "url": FT_OCT18_URL,
        "source": "Financial Times",
        "theme": "자금조달·계획 실현 위험",
        "published": FT_OCT18_ANNOUNCED_UTC.strftime("%a, %d %b %Y %H:%M:%S GMT"),
        "scale_mw": 0.0,
        "verified_first_party_headline": True,
    }


def anchored_nscale_loughton_event(now: dt.datetime | None = None) -> dict | None:
    """First verified news event; Telegraph allegation reported by Reuters.
    Nscale's Sep-2025 own release independently confirms site size and prior plan,
    NOT the Oct-2026 withdrawal. No firm-party statement is implied.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    hours = (now - NSCALE_EVENT_DAY_UTC).total_seconds() / 3600
    if hours < 0 or hours > NSCALE_EVENT_MAX_AGE_HOURS:
        return None
    return {
        "id": sig(NSCALE_ANCHOR_KEY, NSCALE_REUTERS),
        "title": "Microsoft pulls out of UK data-center deal with Nscale in Loughton, Telegraph reports",
        "url": NSCALE_REUTERS,
        "source": "Reuters (The Telegraph 원보도 인용)",
        "theme": "고객 이용계약 철회 보도",
        "published": NSCALE_EVENT_DAY_UTC.strftime("%a, %d %b %Y %H:%M:%S GMT"),
        "scale_mw": 50.0,
        "nscale_loughton_media_anchor": True,
        "official_contract_termination_confirmed": False,
        "reported_power_delay_not_causal_proof": True,
    }


def nscale_is_same_initial_retelling(title: str, published: dt.datetime) -> bool:
    """Collapse same day's wire rewrites without suppressing later confirmations."""
    low = normalize(title).lower()
    if published.date() > dt.date(2026, 10, 19):
        return False
    if re.search(r"confirms?|official statement|signed replacement|court filing|reversal", low):
        return False
    return (
        "microsoft" in low and "nscale" in low
        and any(x in low for x in ("loughton", "essex", "uk data"))
        and any(x in low for x in ("withdraw", "pulls out", "pulled out", "cancel", "scrap", "axes"))
    )


def regression_checks() -> None:
    assert classify("Microsoft pulls out of UK data-center deal with Nscale in Loughton") == "고객 이용계약 철회 보도"
    assert classify("CoreWeave senior unsecured bonds yield 16% after sell-off") == "AI 채권·담보채 신용변화"
    assert ai_credit_signal("JPMorgan upgrades CoreWeave stock to buy") is None
    assert ai_credit_gap_single_headline("CoreWeave 2030 bonds yield 15%, Applied Digital 2030 secured bonds yield 8%") == 700
    assert ai_credit_gap_single_headline("CoreWeave issues 9.75% notes and Applied Digital issues 9.25% secured notes") is None
    assert is_meaningful(
        "Microsoft pulls out of UK data-center deal with Nscale in Loughton",
        "Reuters", "reuters.com"
    )
    assert not is_meaningful("Microsoft outlines UK data center expansion", "Reuters", "reuters.com")
    assert anchored_nscale_loughton_event(NSCALE_EVENT_DAY_UTC) is not None
    assert anchored_nscale_loughton_event(NSCALE_EVENT_DAY_UTC + dt.timedelta(hours=73)) is None
    assert nscale_is_same_initial_retelling(
        "Microsoft pulls out of UK data-center deal with Nscale in Loughton",
        NSCALE_EVENT_DAY_UTC
    )
    assert not nscale_is_same_initial_retelling(
        "Microsoft formally confirms the Nscale Loughton contract termination",
        NSCALE_EVENT_DAY_UTC
    )
    headline = "America's $10tn AI infrastructure boom is starting to fray"
    assert classify(headline) == "자금조달·계획 실현 위험"
    assert is_meaningful(headline, "Financial Times", "ft.com")
    assert not is_meaningful("AI boom continues", "Financial Times", "ft.com")
    assert not is_meaningful(
        "Data center secures $2bn construction financing and begins work",
        "Reuters", "reuters.com")
    assert is_meaningful(
        "Data center lease amendment adds $359m cost overruns and debt burden",
        "Reuters", "reuters.com")
    assert dollar_values("$10tn") == [10e12]
    assert dollar_values("$500bn") == [500e9]
    now = FT_OCT18_ANNOUNCED_UTC
    assert anchored_ft_oct18_event(now) is not None
    assert anchored_ft_oct18_event(now + dt.timedelta(hours=73)) is None
    assert extract_scale_mw("279 GWh energy storage") == 0.0
    assert extract_scale_mw("500 MWh BESS") == 0.0
    assert extract_scale_mw("2.5 GW data center") == 2500.0
    assert extract_scale_mw("250 MW data center") == 250.0


def collect_news() -> list[dict]:
    out = []
    for query in NEWS_QUERIES:
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({
            "q": query, "hl": "en-US", "gl": "US", "ceid": "US:en",
        })
        try:
            root = ET.fromstring(fetch(url, 25).content)
        except Exception:
            continue
        for item in root.findall("./channel/item")[:25]:
            title = normalize(item.findtext("title") or "")
            link = normalize(item.findtext("link") or "")
            pub = normalize(item.findtext("pubDate") or "")
            if not pub:
                continue
            try:
                published = parsedate_to_datetime(pub)
                if published.tzinfo is None:
                    published = published.replace(tzinfo=dt.timezone.utc)
                if published.astimezone(dt.timezone.utc) < dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=NEWS_ALERT_MAX_AGE_DAYS):
                    continue
            except Exception:
                continue
            source_el = item.find("source")
            source = normalize(source_el.text if source_el is not None else "")
            source_url = normalize(source_el.attrib.get("url", "") if source_el is not None else "")
            domain = domain_of(source_url)
            if not trusted(domain):
                continue
            if not is_meaningful(title, source, domain):
                continue
            theme = classify(f"{title} {source}")
            if theme in {"자금조달·계획 실현 위험", "AI 채권·담보채 신용변화"}:
                if published.astimezone(dt.timezone.utc) < (
                    dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=FINANCING_NEWS_MAX_AGE_HOURS)
                ):
                    continue
            if nscale_is_same_initial_retelling(title, published.astimezone(dt.timezone.utc)):
                # The Reuters anchor below assigns one stable cross-source key.
                continue
            # The verified anchor below already covers the same FT story.
            if "ft.com" in domain and "10tn" in title.lower() and "ai infrastructure" in title.lower():
                continue
            stable_id = (
                sig("financing-news", source_label(source, source_url).lower(), normalize(title).lower())
                if theme == "자금조달·계획 실현 위험"
                else sig(title, link)
            )
            out.append({
                "id": stable_id,
                "title": title,
                "url": link,
                "source": source_label(source, source_url),
                "theme": theme,
                "published": pub,
                "scale_mw": extract_scale_mw(title),
            })
    verified_ft = anchored_ft_oct18_event()
    if verified_ft:
        out.append(verified_ft)
    verified_nscale = anchored_nscale_loughton_event()
    if verified_nscale:
        out.append(verified_nscale)
    return list({x["id"]: x for x in out}.values())


def source_priority(item: dict) -> tuple[int, int, str]:
    src = item.get("source", "")
    official = 0 if src in {"FERC", "미국 연방관보", "PJM", "Capgemini"} else 1
    theme_order = {
        "고객 이용계약 철회 보도": -2,
        "자금조달·계획 실현 위험": -1,
        "AI 채권·담보채 신용변화": -2,
        "프로젝트 취소·지연": 0,
        "재심사·접속승계": 1,
        "매몰·송전비용": 2,
        "비용보호·준비도 규칙": 3,
        "Phantom load·수요전망": 4,
    }
    return official, theme_order.get(item.get("theme"), 9), item.get("title", "")


regression_checks()

OUT.mkdir(exist_ok=True)
for p in (ALERT, PENDING, STATUS):
    if p.exists():
        p.unlink()

old = load_json(STATE)
fx, fx_source = fx_rate(old.get("last_fx_krw_per_usd"))
if fx is None:
    raise SystemExit("KRW exchange rate unavailable; refusing to send monetary alerts without KRW conversion")
fx_checked = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

items = collect_news()
items.sort(key=source_priority)
old_seen = list(old.get("seen_ids", []))
old_ids = set(old_seen)
credit_items = [x for x in items if x["theme"] == "AI 채권·담보채 신용변화"]
credit_initialized = bool(old.get("ai_credit_initialized", False))
credit_seen_prev = list(old.get("ai_credit_seen_ids", []))
credit_seen_old = set(credit_seen_prev)
# First deployment silently baselines all recent credit headlines; no historical resend.
credit_new = [x for x in credit_items if x["id"] not in credit_seen_old] if credit_initialized else []
regular_new = [x for x in items if x["theme"] != "AI 채권·담보채 신용변화" and x["id"] not in old_ids]
new_items = regular_new + credit_new
credit_seen = list(dict.fromkeys(credit_seen_prev + [x["id"] for x in credit_items]))[-SEEN_ID_LIMIT:]
baseline_run = not old.get("initialized")
format_upgrade = int(old.get("format_version", 0) or 0) < FORMAT_VERSION
should_alert = baseline_run or format_upgrade or bool(new_items)

seen = list(dict.fromkeys(old_seen + [x["id"] for x in items]))[-SEEN_ID_LIMIT:]
pending = {
    "initialized": True,
    "format_version": FORMAT_VERSION,
    "baseline": BASELINE,
    "seen_ids": seen,
    "last_fx_krw_per_usd": fx,
    "fx_source": fx_source,
    "fx_checked_utc": fx_checked,
    "updated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    "ai_credit_initialized": True,
    "ai_credit_seen_ids": credit_seen,
    "ai_credit_last_new_count": len(credit_new),
    "ai_credit_quote_source": "신뢰 매체 헤드라인. TRACE 개별채권 실시간 시세 미연결",
    "nscale_loughton": {
        "event_key": NSCALE_ANCHOR_KEY,
        "site": "Loughton, Essex, UK",
        "former_anchor_customer": "Microsoft",
        "operator": "Nscale",
        "site_initial_mw": 50,
        "site_expandable_mw": 90,
        "planned_nvidia_gb300_gpu_count": 23040,
        "original_supply_target": "2027-Q1",
        "first_media_report": "The Telegraph",
        "reuters_followup_reported": sig(NSCALE_ANCHOR_KEY, NSCALE_REUTERS) in seen,
        "microsoft_formal_cancellation_statement": False,
        "reported_grid_availability": "2030년대, 언론보도 기준·전력회사 공식 원문 미확인",
        "withdrawal_reason_confirmed": False,
        "site_cancellation_confirmed": False,
        "other_microsoft_contracts_terminated": False,
        "contract_value_disclosed": False,
        "news_link": NSCALE_REUTERS,
        "historical_official_link": NSCALE_OFFICIAL_2025,
    },
}
PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

if should_alert:
    nscale_new = any(item.get("nscale_loughton_media_anchor") for item in new_items)
    if baseline_run:
        headline = "✅ 데이터센터 취소·지연·계통비용 위험 감시 시작"
    elif nscale_new:
        headline = "⚠️ Microsoft–Nscale 영국 데이터센터 이용계약 철회 보도"
    elif credit_new and not regular_new:
        headline = "AI 회사채·시설 담보채 신용위험 변화"
    else:
        headline = "⚠️ 미국 데이터센터 취소·지연·계통비용 변화"

    msg = [f"<b>{h(headline)}</b>", ""]

    if baseline_run:
        pjm_cost_krw = krw_from_usd(BASELINE["pjm_2024_dc_transmission_usd_b"] * 1e9, fx)
        threshold_krw = krw_from_usd(100e6, fx)
        msg += ["<b>🧭 한눈에</b>"]
        msg.append("• 핵심 위험 │ 데이터센터가 취소돼도 전력망 비용과 재심사 시간이 그대로 남을 수 있음")
        msg.append("• 판단 기준 │ 취소 건수보다 매몰비용·재심사·비용부담 주체·후속 프로젝트 전환시간을 우선")

        msg += ["", "<b>⚠️ 기준 위험판</b>"]
        msg.append(f"• Phantom load │ 전력요청의 약 <b>{BASELINE['phantom_load_pct']:.0f}%</b>가 실제 부하로 이어지지 않을 수 있음")
        msg.append("• 재심사 │ 산업 경험상 <b>6개월~1년 이상</b> 걸릴 수 있음 · 전국 공통 법정기간은 아님")
        msg.append(
            f"• PJM 2024 데이터센터 송전사업 │ <b>{BASELINE['pjm_2024_dc_transmission_projects']}건 · "
            f"43억달러 = {h(pjm_cost_krw)}</b>"
        )
        msg.append("• FERC │ Cost Recovery Agreement + 단계별 준비도 요건으로 소비자 비용전가·중복신청 방지 추진")

        msg += ["", "<b>🔔 알림 조건</b>"]
        msg.append("• 250MW 이상 대형 프로젝트 취소·대규모 지연·축소")
        msg.append("• 후속 프로젝트가 기존 접속을 승계하지 못하고 재심사에 들어간 사실이 확인될 때")
        msg.append(f"• 매몰·송전·변전 비용이 <b>1억달러 = {h(threshold_krw)}</b> 이상 확인될 때")
        msg.append("• FERC·RTO·주 규제기관의 Cost Recovery Agreement·준비도·site control·금융보증 규칙 변경")
        msg.append("• Phantom load 제거로 공식 수요전망이 10% 이상 또는 1GW 이상 하향될 때")
    else:
        msg += ["<b>🧭 한눈에</b>"]
        if new_items:
            first = new_items[0]
            src = first.get("source", "")
            title_ko = translate_title(first.get("title", ""), first.get("theme", "기타"), src)
            msg.append(f"• 이번 핵심 변화 │ {a(title_ko, first.get('url',''))}")
        msg.append("• 판단 기준 │ 취소 → stranded cost → restudy → 추가 CAPEX·금융비용 → IRR 악화 경로 확인")

    if nscale_new:
        msg += ["", "<b>⚠️ 영국 로턴: 계약 철회 보도·전원 인가 병목</b>"]
        msg.append("• <b>보도 상태</b> │ The Telegraph 최초 보도, Reuters 10월 18일 후속 보도. Microsoft 공식 철회사유 미공개")
        msg.append("• <b>2025년 Nscale 당사자 발표</b> │ 로턴 초기 50MW→최대 90MW, NVIDIA GB300 23,040개, 2027년 1분기 공급 목표")
        msg.append("• <b>핵심 변화</b> │ Microsoft의 로턴 시설 이용계약 철회 보도. 로턴 데이터센터 사업 전체 취소·Nscale 다른 고객계약 취소 아님")
        msg.append("• <b>전력 위험</b> │ 2030년대 전력 공급 가능하다는 언론보도. 실제 철회사유 및 전력회사 공식 확정 문서는 별도 확인 필요")
        msg.append("• <b>재무 영향</b> │ 임차인 매출·사업금융 가정 약화 가능. 해당 계약금액·위약금·확정 손실액 미공개(금액 추정 금지)")
        msg.append("• <b>시간표</b> │ 2027년 1분기 공급 목표 대 2030년대 전력 가능성: 실현되면 최소 약 3년 지연")
        msg.append("• <b>실패 경로</b> │ 전력망 접속 지연→GPU 납품·설치 지연→고객 계약 변경→차입·현금회수 부담")
        msg.append("• <b>다음 확인</b> │ 당사자 계약 공시/공식 설명, 계통접속 예정일, 대체전원 계약, 신규 핵심 고객, 프로젝트 금융조건")
        msg.append(f"• {a('Reuters 10월 18일 원문', NSCALE_REUTERS)} · {a('Nscale 2025년 원발표', NSCALE_OFFICIAL_2025)}")
        msg.append(f"• {a('Nscale-Microsoft 타지역 계약 원발표', NSCALE_MSFT_OTHER_REGIONS)}")
    if any(item.get("verified_first_party_headline") for item in new_items):
        msg += ["", "<b>📌 FT 10월 18일 미국 AI 인프라 금융·착공 위험</b>"]
        msg.append(
            f"• FT의 10조달러({h(krw_from_usd(10e12, fx))})는"
            " 2025~2032년 미국 AI 인프라 누적 지출 전망(Columbia·Brookings 연구 인용)."
            " 이미 집행·확정 투자한 금액이나 취소금액이 아님"
        )
        msg.append(
            "• FT가 인용한 RegLayer 집계: 2026년 대형 프로젝트 지연·철회·차단 최소 47건."
            " RegLayer의 개별 프로젝트 전체 원자료는 별도 확인 필요"
        )
        msg.append(
            "• FT가 전한 Bernstein 약 35%: 계획의 실현 신뢰도 추정."
            " 실제 완공률·취소율이나 10조달러에 곱할 비율이 아님"
        )
        msg.append(
            f"• OpenAI 스타게이트 <b>5,000억달러({h(krw_from_usd(500e9, fx))})</b>는"
            " 2025년 최초 투자 구상. 실제 지출·계약·가동 물량과 분리"
        )
        msg.append("• 경고 경로: 금리·금융조달 → 전력 접속·인허가 → 착공 → 장비 주문 → 전원 인가")
        msg.append("• 재확인: 대출 금융종결·신규수주·전력서비스 계약·착공·공식 가동 MW")
        msg.append(
            f"• 근거 등급: {a('FT 원보도', FT_OCT18_URL)}는 제목을 FT 공식 게시물로 확인."
            f" {a('FT 공식 게시', FT_OFFICIAL_POST)} ·"
            f" {a('OpenAI 원발표', OPENAI_STARGATE_OFFICIAL)} ·"
            f" {a('Brookings 2025~2032 전망', 'https://www.brookings.edu/articles/the-10-trillion-question-financing-the-ai-buildout/')}."
            " 세부 47건·35%는 FT 인용 추정으로 독립 원자료 미확보"
        )

    if new_items:
        msg += ["", "<b>🆕 핵심 신규 변화</b>"]
        chosen = []
        used_theme = set()
        for item in new_items:
            theme = item.get("theme")
            if theme in used_theme:
                continue
            chosen.append(item)
            used_theme.add(theme)
            if len(chosen) >= 5:
                break
        if len(chosen) < 5:
            for item in new_items:
                if item in chosen:
                    continue
                chosen.append(item)
                if len(chosen) >= 5:
                    break
        for idx, item in enumerate(chosen, 1):
            src = item.get("source", "")
            theme = item.get("theme", "기타")
            title_ko = (
                "FT 미국 AI 인프라 10조달러 계획의 금융·착공 위험 확대"
                if item.get("verified_first_party_headline")
                else "Microsoft, 영국 로턴 Nscale 데이터센터 이용계약 철회 보도(Reuters·The Telegraph)"
                if item.get("nscale_loughton_media_anchor")
                else translate_title(item.get("title", ""), theme, src)
            )
            suffix = money_suffix(item.get("title", ""), fx)
            msg.append(f"{idx}. {a(title_ko, item.get('url',''))}{h(suffix)}")
            msg.append(f"   {h(theme)} · {h(src)}")
        if len(new_items) > len(chosen):
            msg.append(f"• 나머지 {len(new_items)-len(chosen)}건은 중복·추적 상태에 저장해 다음 변화 판정에 반영")


    if credit_new:
        msg += ["", "<b>AI 회사채·시설 담보채 차별화 확인</b>"]
        for item in credit_new[:5]:
            kind = ai_credit_signal(item["title"])
            gap = ai_credit_gap_single_headline(item["title"])
            msg.append(f"• {h(kind or '신용위험 변화')} · {h(item['source'])} · 보도 제목 기준")
            if gap is not None:
                msg.append(
                    f"  같은 보도 내 두 수익률의 단순 차이 <b>{gap:+,}bp</b> "
                    "(채권 만기·발행주체·담보·선순위 차이 미보정)"
                )
        msg.append("• CoreWeave 발행사 무담보채와 APLD ComputeCo 데이터센터 담보채는 채무자·담보가 다름")
        msg.append("• 15%와 8%는 WSJ 10월 19일 당시 관측치이며 현재 시세나 고정 경보 임계값이 아님")
        msg.append("• 개별 채권의 동시 TRACE 시세가 없으면 현재 금리차를 임의 계산하지 않음")
        msg.append("• 은행 위험은 대출 익스포저 추정과 실제 손실·충당금을 구분")
        msg.append(f"• {a('CoreWeave SEC 채무', 'https://www.sec.gov/Archives/edgar/data/1769628/000176962826000366/crwv-20260630.htm')} · {a('APLD SEC 담보채', 'https://www.sec.gov/Archives/edgar/data/1144879/000114487926000059/apld-20260831.htm')}")

    msg += ["", "<b>📊 투자 판단</b>"]
    msg.append("• 실행률 │ 신청 MW보다 보증금·부지·전력계약·송전착공·실제 데이터센터 착공·전원 인가 MW를 우선")
    msg.append("• 비용 │ 개발사 매몰비용과 유틸리티 송전·변전 투자비를 분리해 확인")
    msg.append("• 후속사업자 │ 같은 부지라도 부하규모·접속점·가동시점이 달라지면 재심사 가능성을 확인")
    msg.append("• 조기경보 │ 대형 취소→restudy 증가→COD 지연→금융비용 상승이 연속으로 나타나는지 추적")

    msg += ["", "<b>💱 환율</b>"]
    msg.append(f"• <b>1달러 = {fx:,.2f}원</b> │ {h(fx_source)} │ {h(fx_checked)} UTC")
    msg.append("• 외화 금액은 확인되는 즉시 같은 줄에 원화 환산")

    msg += ["", "<b>🔗 기준 원문</b>"]
    msg.append(f"• {a('Data Center Knowledge · 취소·지연 파급효과', DCK_RIPPLE)}")
    msg.append(f"• {a('Capgemini · Phantom load 19% 기준', CAPGEMINI)}")
    msg.append(f"• {a('FERC · 대형부하 Cost Recovery·준비도 개편', FERC_LARGE_LOAD)}")
    msg.append(f"• {a('FERC · Cost Recovery Agreement 설명', FERC_ROSNER)}")

    ALERT.write_text("\n".join(msg).strip() + "\n", encoding="utf-8")

STATUS.write_text(
    "# 미국 데이터센터 취소·지연·계통비용 위험 감시\n\n"
    f"- Phantom load 기준: **{BASELINE['phantom_load_pct']}%**\n"
    f"- 재심사 기준: **{BASELINE['restudy_min_months']}개월~1년 이상(산업 경험치)**\n"
    f"- PJM 2024 DC 송전사업: **{BASELINE['pjm_2024_dc_transmission_projects']}건 / ${BASELINE['pjm_2024_dc_transmission_usd_b']}B**\n"
    f"- 신규 의미자료: **{len(new_items)}건**\n"
    f"- Reuters–Nscale 로턴 철회 보도: **{'신규' if any(x.get('nscale_loughton_media_anchor') for x in new_items) else '중복 제외/해당 없음'}**\n"
    f"- AI 발행사·담보채 신용경보: **감시 활성** · 신규 **{len(credit_new)}건** · TRACE 개별 실시간 시세 **미연결**\n"
    f"- 알림: **{'예' if should_alert else '아니오'}**\n",
    encoding="utf-8",
)
print(
    f"cancellation_risk baseline={BASELINE['phantom_load_pct']}% "
    f"new={len(new_items)} credit_new={len(credit_new)} credit_baselined={not credit_initialized} alert={should_alert}"
)
