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
MS_FINANCE_URL = "https://www.morganstanley.com/insights/podcasts/thoughts-on-the-market/credit-markets-ai-boom-financing-carolyn-campbell"
JLL_COLO_URL = "https://www.jll.com/en-us/newsroom/data-center-demand-exceeds-expectations-in-h1-2026"
CBRE_COLO_URL = "https://www.cbre.com/insights/books/north-america-data-center-trends-h1-2026"
MS_FINANCE_EVENT = "ms-data-center-financing-colocation-20261016-context-addendum"
MS_FINANCE_REFERENCE = {
    "as_of": "2026-10-16",
    "bond_yield_start_2026_below_pct": 5.0,
    "bond_yield_oct_16_approx_pct": 7.0,
    "issuance_difficulty_borrowing_rate_near_pct": 8.0,
    "dc_abs_2026_ytd_usd_b": 15.0,
    "dc_cmbs_2026_ytd_usd_b": 7.0,
    "future_dc_abs_cmbs_issuance_usd_b_range": [120.0, 150.0],
    "us_power_current_gw_estimate": 60.0,
    "us_power_2028_gw_forecast": 150.0,
    "us_power_2028_shortfall_pct": [30.0, 40.0],
    "us_power_2028_shortfall_scenario_gw": [90.0, 105.0],
    "jll_north_america_h1_2026_vacancy_pct": 1.0,
    "cbre_primary_market_h1_2026_vacancy_pct": 1.4,
    "cbre_primary_3_to_10mw_asking_rent_h1_growth_pct": 8.3,
    "primary_sources": [MS_FINANCE_URL, JLL_COLO_URL, CBRE_COLO_URL],
    "source_status": "2026-10-25 검증한 과거 발행처 원자료 기준; 실시간 채권시세 미연결",
}

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
    "morganstanley.com", "jll.com", "cbre.com",
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
    # Historical sources are baselines, not reannounced as a live market move.
    'Morgan Stanley data center ABS CMBS bonds borrowing costs finance outlook',
    'CBRE JLL North America data center colocation vacancy rental rates growth',
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
NEWS_SCAN_HEALTH = {"ai_credit_rss_ok": 0, "ai_credit_rss_failed": 0}
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


def ms_finance_addendum_due(old: dict, first: bool) -> bool:
    return not first and old.get("ms_finance_addendum_id") != MS_FINANCE_EVENT


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
        k in low for k in ("exposure", "loss", "risk", "contagion", "default")
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
    if any(t in low for t in ("data center", "data centre", "datacenter", "colocation")) and any(
        t in low for t in ("vacancy", "asking rent", "rental rate")
    ):
        return "코로케이션 공실률·임대료 변화"
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
    if theme == "코로케이션 공실률·임대료 변화":
        directional = any(t in low for t in (
            "rose", "rise", "rising", "fell", "fall", "declin", "drop",
            "surge", "jump", "record low", "record-low", "record high"
        ))
        return trusted(domain) and directional and bool(re.search(r"\b\d+(?:\.\d+)?\s*%", low))
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
        "코로케이션 공실률·임대료 변화": "데이터센터 공실률·임대료의 실질 변화",
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
    assert ms_finance_addendum_due({"initialized": True}, False)
    assert not ms_finance_addendum_due({"ms_finance_addendum_id": MS_FINANCE_EVENT}, False)
    assert not ms_finance_addendum_due({}, True)
    assert MS_FINANCE_REFERENCE["us_power_2028_gw_forecast"] * 0.6 == 90
    assert MS_FINANCE_REFERENCE["us_power_2028_gw_forecast"] * 0.7 == 105
    assert classify("CBRE data center vacancy fell to 1.4%") == "코로케이션 공실률·임대료 변화"
    assert is_meaningful("CBRE data center vacancy fell to 1.4%", "CBRE", "cbre.com")
    assert not is_meaningful("CBRE data center trend overview", "CBRE", "cbre.com")
    assert classify("Microsoft pulls out of UK data-center deal with Nscale in Loughton") == "고객 이용계약 철회 보도"
    assert classify("CoreWeave senior unsecured bonds yield 16% after sell-off") == "AI 채권·담보채 신용변화"
    assert ai_credit_signal("JPMorgan upgrades CoreWeave stock to buy") is None
    assert ai_credit_signal("CoreWeave debt selloff poses limited risk to global banks") == "은행 대출·익스포저 보도(실제 손실 여부 별도 확인)"
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
        is_credit_query = query in NEWS_QUERIES[-6:]
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({
            "q": query, "hl": "en-US", "gl": "US", "ceid": "US:en",
        })
        try:
            root = ET.fromstring(fetch(url, 25).content)
            if is_credit_query:
                NEWS_SCAN_HEALTH["ai_credit_rss_ok"] += 1
        except Exception:
            if is_credit_query:
                NEWS_SCAN_HEALTH["ai_credit_rss_failed"] += 1
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
                if theme in {"자금조달·계획 실현 위험", "AI 채권·담보채 신용변화"}
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
        "코로케이션 공실률·임대료 변화": 0,
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
credit_source_ok = NEWS_SCAN_HEALTH["ai_credit_rss_ok"] > 0
credit_seen_prev = list(old.get("ai_credit_seen_ids", []))
credit_seen_old = set(credit_seen_prev)
# First deployment silently baselines all recent credit headlines; no historical resend.
credit_new = [x for x in credit_items if x["id"] not in credit_seen_old] if credit_initialized and credit_source_ok else []
regular_new = [x for x in items if x["theme"] != "AI 채권·담보채 신용변화" and x["id"] not in old_ids]
new_items = regular_new + credit_new
credit_seen = list(dict.fromkeys(credit_seen_prev + [x["id"] for x in credit_items]))[-SEEN_ID_LIMIT:] if credit_source_ok else credit_seen_prev
baseline_run = not old.get("initialized")
format_upgrade = int(old.get("format_version", 0) or 0) < FORMAT_VERSION
ms_finance_due = ms_finance_addendum_due(old, baseline_run)
should_alert = baseline_run or format_upgrade or bool(new_items) or ms_finance_due

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
    "ai_credit_initialized": bool(credit_initialized or credit_source_ok),
    "ai_credit_rss_success_count": NEWS_SCAN_HEALTH["ai_credit_rss_ok"],
    "ai_credit_rss_failure_count": NEWS_SCAN_HEALTH["ai_credit_rss_failed"],
    "ai_credit_seen_ids": credit_seen,
    "ai_credit_last_new_count": len(credit_new),
    "ai_credit_quote_source": "신뢰 매체 헤드라인. TRACE 개별채권 실시간 시세 미연결",
    "ai_credit_baseline_confirmed_at_utc": old.get("ai_credit_baseline_confirmed_at_utc"),
    "ms_finance_reference": MS_FINANCE_REFERENCE,
    "ms_finance_addendum_id": MS_FINANCE_EVENT if ms_finance_due else old.get("ms_finance_addendum_id"),
    "ms_finance_addendum_at_utc": (
        dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        if ms_finance_due else old.get("ms_finance_addendum_at_utc")
    ),
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
if old.get("ai_credit_baseline_confirmed_at_utc") and pending.get("ai_credit_baseline_confirmed_at_utc") != old["ai_credit_baseline_confirmed_at_utc"]:
    raise RuntimeError("AI credit verified baseline timestamp would be lost")
PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

if should_alert:
    nscale_new = any(item.get("nscale_loughton_media_anchor") for item in new_items)
    if baseline_run:
        headline = "✅ 데이터센터 취소·지연·계통비용 위험 감시 시작"
    elif nscale_new:
        headline = "⚠️ Microsoft–Nscale 영국 데이터센터 이용계약 철회 보도"
    elif credit_new and not regular_new:
        headline = "AI 회사채·시설 담보채 신용위험 변화"
    elif ms_finance_due and not new_items:
        headline = "Morgan Stanley 데이터센터 금융·코로케이션 관점 보강"
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
        if ms_finance_due:
            msg.append("• <b>금융</b> │ 우량 데이터센터 채권 금리 5% 미만 → 약 <b>7%</b>; 8% 접근 시 조달 부담 확대")
            msg.append("• <b>전력</b> │ 미국 약 <b>60GW → 2028년 150GW</b> 전망. 공급 제약 시 <b>90~105GW</b>")
            msg.append("• <b>임대</b> │ 공실률 JLL 1.0% / CBRE 1.4%(표본 다름), CBRE 3~10MW 호가 +8.3%")
        if new_items:
            first = new_items[0]
            src = first.get("source", "")
            title_ko = translate_title(first.get("title", ""), first.get("theme", "기타"), src)
            msg.append(f"• <b>이번 추가 변화</b> │ {a(title_ko, first.get('url',''))}")
        msg.append("• <b>판단 기준</b> │ 계약 철회 → 매몰비용 → 전력 접속 재심사 → 추가 설비투자·금융비용 → 내부수익률 하락")

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
        msg += ["", f"<b>🆕 신규 확인 자료 │ 총 {len(new_items)}건</b>"]
        msg.append("• 신뢰 출처에서 확인한 신규 자료를 생략하지 않고 모두 표시합니다.")
        shown_ids = []
        for idx, item in enumerate(new_items, 1):
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
            msg.append(f"{idx}. <b>{h(theme)}</b>")
            msg.append(f"   {a(title_ko, item.get('url', ''))}{h(suffix)}")
            msg.append(f"   출처: {h(src)}")
            shown_ids.append(item["id"])
        if shown_ids != [item["id"] for item in new_items]:
            raise RuntimeError("신규 기사 목록 표시 누락·순서 변경 감지")

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

    if ms_finance_due:
        msg += ["", "<b>① 차입금리·이자부담 | 10월 16일 기준</b>"]
        msg.append("• <b>우량 데이터센터 채권 수익률</b>")
        msg.append("  2026년 연초 <b>5% 미만</b> → 10월 16일 <b>약 7%</b>.")
        msg.append("• <b>8% 위험구간</b> │ 차입비용이 8%에 접근하면 증권화 발행이 어려워진다는 Morgan Stanley 전략가 판단.")
        msg.append("  10월 16일 분석이며 실시간 현재 금리·자동 돌파판정이 아님.")
        msg.append("• <b>차입금리 +2%포인트 재조달 감도</b>")
        msg.append(
            f"  차입 10억달러({h(krw_from_usd(1e9, fx))}) × 2%p"
            f" = 추가 연이자 2,000만달러({h(krw_from_usd(20e6, fx))})."
        )
        msg.append("  이미 발행한 고정금리 부채 전체가 즉시 재가격되지는 않음.")

        msg += ["", "<b>② 금융시장 발행 규모 · 미래 전망 분리</b>"]
        msg.append("• <b>2026년 10월 16일 기준 발행</b>")
        msg.append(f"  데이터센터 자산유동화증권(ABS) 약 150억달러({h(krw_from_usd(15e9, fx))}).")
        msg.append(f"  상업용 부동산 저당증권(CMBS) 약 70억달러({h(krw_from_usd(7e9, fx))}).")
        msg.append("• <b>향후 수년간 증권화 발행 전망</b>")
        msg.append(
            f"  1,200억달러({h(krw_from_usd(120e9, fx))})"
            f"~1,500억달러({h(krw_from_usd(150e9, fx))})."
        )
        msg.append("• <b>중복·회계 구분</b> │ 발행액은 신규 건설비·인식 매출이 아님.")
        msg.append("  JLL의 전체 AI 회사채 통계와 집계범위가 다르므로 합산 금지.")

        msg += ["", "<b>③ 실제 전력 확보 · 전망과 가동 구분</b>"]
        msg.append("• <b>미국 전력용량 전망</b> │ 현재 약 <b>60GW</b> → 2028년 <b>150GW</b>.")
        msg.append("• <b>공급 제약</b> │ 전망보다 30~40% 부족할 경우 <b>90~105GW</b> 시나리오.")
        msg.append("  계획·건설 중·전원 인가·실제 가동 용량은 다른 숫자.")

        msg += ["", "<b>④ 코로케이션 · 빠른 임대료 재가격 여부</b>"]
        msg.append("• <b>2026년 상반기 북미 공실률</b>")
        msg.append("  JLL 전체 <b>1.0%</b> / CBRE 주요 도매시장 <b>1.4%</b>.")
        msg.append("  조사범위·표본이 달라 두 수치 차이를 공실률 변동으로 해석 금지.")
        msg.append("• <b>CBRE 3~10MW 임대료 호가</b> │ 상반기 <b>+8.3%</b>.")
        msg.append("  호가·실제 신규 임대계약 단가·기존 장기고정 임대매출은 구분.")
        msg.append("• <b>반복매출 가능성</b> │ 다수 업종 임차인·상대적으로 짧은 임대기간은 재가격에 유리.")
        msg.append("  실제 계약·전력 확보·갱신 단가·현금 회수가 확인돼야 실적 개선으로 판단.")

        msg += ["", "<b>⑤ 실패 경로 · 후속 확인</b>"]
        msg.append("• <b>금융 실패</b> │ 차입금리 상승 → 준공 후 차입금 대체 지연 → 현금흐름 악화 → 후속 착공 지연.")
        msg.append("• <b>전력 실패</b> │ 변전소·송전선·전원 인가 지연. 금융 위험과 별개로 감시.")
        msg.append("• <b>추적 대상</b> │ 새 회사채·담보채 금리 및 신용 변화, 금융종결, 공실률, 갱신 임대료.")
        msg.append("  TRACE 실시간 금리 조회와 8% 돌파 자동 경보는 미구축.")

        msg += ["", "<b>🔗 Morgan Stanley 관점의 공식 출처</b>"]
        msg.append(f"• {a('Morgan Stanley · 금융·전력 전망', MS_FINANCE_URL)}")
        msg.append(f"• {a('JLL · 북미 2026년 상반기 조사', JLL_COLO_URL)}")
        msg.append(f"• {a('CBRE · 북미 주요시장 2026년 상반기', CBRE_COLO_URL)}")

    msg += ["", "<b>📊 실제 투자 판단</b>"]
    msg.append("• <b>실행률</b> │ 전력 신청 MW보다 보증금·부지·전력계약·송전 착공·현장 착공·전원 인가 MW를 우선")
    msg.append("• <b>비용</b> │ 개발사 매몰비용과 전력회사의 송전·변전 투자비 분리")
    msg.append("• <b>후속 사업자</b> │ 부하 규모·접속점·가동일이 달라지면 재심사 가능성 확인")
    msg.append("• <b>조기 경보</b> │ 대형 계약 취소 → 접속 재심사 증가 → 전원 인가 지연 → 차입비용 상승")

    msg += ["", "<b>💱 환율</b>"]
    msg.append(f"• <b>1달러 = {fx:,.2f}원</b> │ {h(fx_source)} │ {h(fx_checked)} UTC")
    msg.append("• 외화 금액은 확인되는 즉시 같은 줄에 원화 환산")

    msg += ["", "<b>🔗 기준 원문</b>"]
    msg.append(f"• {a('Data Center Knowledge · 취소·지연 파급효과', DCK_RIPPLE)}")
    msg.append(f"• {a('Capgemini · Phantom load 19% 기준', CAPGEMINI)}")
    msg.append(f"• {a('FERC · 대형부하 Cost Recovery·준비도 개편', FERC_LARGE_LOAD)}")
    msg.append(f"• {a('FERC · Cost Recovery Agreement 설명', FERC_ROSNER)}")

    if ms_finance_due:
        complete = "\n".join(msg)
        required = (
            "5% 미만", "7%", "8%", "2%포인트", "2,000만달러",
            "150억달러", "70억달러", "1,200억달러", "1,500억달러",
            "60GW", "150GW", "30~40%", "90~105GW",
            "1.0%", "1.4%", "+8.3%", "TRACE",
            MS_FINANCE_URL, JLL_COLO_URL, CBRE_COLO_URL,
            DCK_RIPPLE, CAPGEMINI, FERC_LARGE_LOAD, FERC_ROSNER,
        )
        missing = [term for term in required if term not in complete]
        if missing:
            raise RuntimeError(f"금융·코로케이션 알림 원문 수치·출처 누락: {missing}")
    if new_items:
        full_report = "\n".join(msg)
        missing_urls = [
            item.get("url")
            for item in new_items
            if item.get("url") and h(item["url"]) not in full_report
        ]
        if missing_urls:
            raise RuntimeError(f"신규 기사 링크 누락으로 Telegram 송출 차단: {len(missing_urls)}건")
    ALERT.write_text("\n".join(msg).strip() + "\n", encoding="utf-8")

STATUS.write_text(
    "# 미국 데이터센터 취소·지연·계통비용 위험 감시\n\n"
    f"- Phantom load 기준: **{BASELINE['phantom_load_pct']}%**\n"
    f"- 재심사 기준: **{BASELINE['restudy_min_months']}개월~1년 이상(산업 경험치)**\n"
    f"- PJM 2024 DC 송전사업: **{BASELINE['pjm_2024_dc_transmission_projects']}건 / ${BASELINE['pjm_2024_dc_transmission_usd_b']}B**\n"
    f"- 신규 의미자료: **{len(new_items)}건**\n"
    f"- Reuters–Nscale 로턴 철회 보도: **{'신규' if any(x.get('nscale_loughton_media_anchor') for x in new_items) else '중복 제외/해당 없음'}**\n"
    f"- AI 신용경보: **{'감시 활성' if credit_initialized or credit_source_ok else '원천 장애·기준선 보류'}** · 신규 **{len(credit_new)}건** · RSS 응답 **{NEWS_SCAN_HEALTH['ai_credit_rss_ok']}/6** · TRACE 실시간 시세 **미연결**\n"
    f"- 코로케이션 공실률·임대료 신규 보도: **{sum(1 for x in new_items if x.get('theme') == '코로케이션 공실률·임대료 변화')}건** · 자료별 표본 구분\n"
    f"- Morgan Stanley 금융 관점 1회 보강: **{'예' if ms_finance_due else '중복 제외'}** · 실시간 채권시세 미연결\n"
    f"- 알림: **{'예' if should_alert else '아니오'}**\n",
    encoding="utf-8",
)
print(
    f"cancellation_risk baseline={BASELINE['phantom_load_pct']}% "
    f"new={len(new_items)} credit_new={len(credit_new)} credit_feeds_ok={NEWS_SCAN_HEALTH['ai_credit_rss_ok']} credit_baselined={not credit_initialized} ms_finance_addendum={ms_finance_due} alert={should_alert}"
)


# US_KOREA_INBOUND_DIVERSION_V1
# Existing US data-center cancellation/finance watcher, Telegram destination,
# pending-state file and schedule only. No second workflow or bot.
INBOUND_DIVERSION_ID = "us-tx-approval-delay-korea-investment-diversion-source-graded-20261108"
INBOUND_TEXAS_GOV = "https://gov.texas.gov/news/post/governor-abbott-directs-tceq-to-halt-data-center-permits"
INBOUND_TEXAS_TRIBUNE = "https://www.texastribune.org/2026/11/04/data-center-texas-pause-gina-hinojosa-governor-policies/"
INBOUND_TEXAS_ERCOT = "https://www.ercot.com/about/legal/data-center-impact-rfi"
INBOUND_MOTIR = "https://english.motir.go.kr/eng/article/EATCLdfa319ada/2779/view?bbsCdN=2&pageIndex=1"
INBOUND_KOTRA_SIGNED_REPORT = "https://biz.heraldcorp.com/article/10926277"
INBOUND_HANA = "https://www.hanaw.com/main/research/research/list.cmd?cid=1&pid=3"
INBOUND_KHAN = "https://www.khan.co.kr/article/202611081638001"
INBOUND_NH_REPOST = "https://tele.wiki/t/post/455884571"
INBOUND_SKT_AWS = "https://news.sktelecom.com/en/1948"
INBOUND_SKT_ROADMAP = "https://news.sktelecom.com/en/3155"
INBOUND_MSIT_ULSAN = "https://msit.go.kr/eng/bbs/view.do?bbsSeqNo=42&mId=4&nttSeqNo=1130&sCode=eng"
INBOUND_CBRE_KOREA = "https://www.cbre.com/insights/reports/korea-data-center-investment"
INBOUND_US_KOREA_SNAPSHOT = {
    "as_of": "2026-11-08",
    "texas_permit_pause_since": "2026-09-21, 기존 주지사 행정조치·감사 기한부",
    "texas_governor_elect": "2026-11-03 당선, 2027-01 취임 후 추가 승인 중단 공약·아직 시행 전",
    "hana_research_date": "2026-11-06 발행처 목록 검색 색인",
    "hana_2030_incremental_base_gw": [3.0, 4.2],
    "hana_2030_incremental_bull_gw": [5.1, 7.0],
    "hana_4_to_5gw_epc_krw_trillion": [30, 40],
    "hana_report_pdf_confirmed": False,
    "nh_analyst_original_report_confirmed": False,
    "kotra_kdcc_mou_date": "2026-11-04",
    "kotra_kdcc_mou_stage": "투자유치 협력 양해각서·실제 외국인 투자계약 아님",
    "sk_aws_ulsan_existing_contract_year": 2025,
    "sk_aws_ulsan_target_mw_2027_11": 41,
    "sk_aws_ulsan_target_mw_2029_02": 103,
    "post_us_election_relocation_to_korea_confirmed": False,
    "korea_power_and_land_constraints": "CBRE 2026-07 수도권 전력·부지 부족, 비수도권도 실제 접속확약 별도 확인",
    "primary_sources": [INBOUND_TEXAS_GOV, INBOUND_TEXAS_ERCOT,
                        INBOUND_MOTIR, INBOUND_SKT_AWS, INBOUND_MSIT_ULSAN],
    "reported_sources": [INBOUND_TEXAS_TRIBUNE, INBOUND_KHAN,
                         INBOUND_HANA, INBOUND_NH_REPOST,
                         INBOUND_KOTRA_SIGNED_REPORT, INBOUND_CBRE_KOREA],
}
INBOUND_OFFICIAL_NEWS_QUERIES = (
    '"South Korea" "AI data center" "signed" "AWS" 2026',
    '"Korea" "hyperscale data center" "investment agreement" 2026',
    'Texas data center permits moratorium governor official decision',
    'ERCOT data center audit report grid approval final ruling',
)
INBOUND_OFFICIAL_DOMAINS = (
    "sktelecom.com", "sk.com", "aws.amazon.com", "amazon.com",
    "microsoft.com", "google.com", "motir.go.kr", "msit.go.kr",
    "kotra.or.kr", "navercloudcorp.com", "lgcns.com",
    "gov.texas.gov", "ercot.com", "governor.ohio.gov", "georgia.gov",
)


def inbound_official_stage(title: str) -> str | None:
    """Only first-party, Korean-site project milestones; not relocation opinions."""
    t = normalize(html.unescape(title)).lower().replace("data-center", "data center")
    is_dc = any(x in t for x in ("data center", "data centre", "datacenter", "데이터센터", "aidc"))
    is_korea = any(x in t for x in ("korea", "ulsan", "seoul", "gwangju",
                                  "한국", "울산", "광주", "전남", "부산"))
    if not (is_dc and is_korea):
        return None
    if any(x in t for x in ("mou", "memorandum of understanding", "양해각서")):
        return "투자유치 양해각서(구속력·실제 집행 미확인)"
    if any(x in t for x in ("energized", "commenced operations", "commercial operations",
                            "operational", "상업운전", "가동 개시")):
        return "가동·전원 인가 공식 발표"
    if any(x in t for x in ("financial close", "financing closed", "금융종결")):
        return "프로젝트 금융종결 공식 발표"
    if any(x in t for x in ("broke ground", "groundbreaking", "construction begins",
                            "construction started", "착공")):
        return "착공 공식 발표"
    if any(x in t for x in ("signed contract", "signed agreement", "long-term lease signed",
                            "binding agreement", "공급계약 체결", "임대계약 체결")):
        return "계약 체결 공식 발표(구체적 구속력 별도 확인)"
    return None


def inbound_us_policy_stage(title: str) -> str | None:
    """A formal US state or grid regulator action, not election promises."""
    t = normalize(html.unescape(title)).lower().replace("data-center", "data center")
    if not any(word in t for word in ("data center", "data centre", "datacenter")):
        return None
    if not any(word in t for word in ("texas", "ercot", "ohio", "georgia")):
        return None
    # Opinion-only and political campaign coverage are not enacted rules.
    if any(word in t for word in (
        "candidate", "governor-elect", "pledges", "promises", "could", "may",
        "proposes", "proposal", "planned", "plan to", "would",
    )):
        return None
    enforceable = any(word in t for word in (
        "signed into law", "issues executive order", "orders permit freeze",
        "halts data center permits", "suspends approvals",
        "approves new rule", "adopts final rules", "audit results released",
        "final audit report", "reopens approvals", "lifts moratorium",
    ))
    return "미국 주정부·전력당국 공식 인허가·감사 결정" if enforceable else None


def inbound_primary_check() -> dict:
    """Current first-party access; news headlines may not substitute for documents."""
    def check(url: str, alternatives: tuple[tuple[str, ...], ...]) -> bool:
        try:
            raw = html.unescape(re.sub(r"<[^>]+>", " ", fetch(url, 12).text)).lower()
            normalized = normalize(raw)
            return all(any(token in normalized for token in group) for group in alternatives)
        except Exception:
            return False
    return {
        "texas_governor": check(INBOUND_TEXAS_GOV,
                                (("data center", "data centers"), ("tceq",), ("ercot",))),
        "texas_independent": check(INBOUND_TEXAS_TRIBUNE,
                                   (("data center",), ("hinojosa",), ("moratorium",))),
        "korea_government": check(INBOUND_MOTIR,
                                  (("data center", "data centers", "데이터센터"),
                                   ("invest korea", "kotra", "코트라"))),
        "korea_signed_earlier": check(INBOUND_SKT_AWS,
                                      (("aws",), ("ulsan",), ("2027",))),
    }


def inbound_is_due(prior: dict, first: bool, source: dict) -> bool:
    return bool(
        not first and prior.get("last_context_id") != INBOUND_DIVERSION_ID
        and (source.get("texas_governor") or source.get("texas_independent"))
        and (source.get("korea_government") or source.get("korea_signed_earlier"))
    )


def inbound_collect_official_announcements() -> tuple[list[dict], int]:
    """Publisher-domain gated Korean investment milestones, only after this watch began."""
    found: dict[str, dict] = {}
    successes = 0
    threshold = dt.datetime(2026, 11, 8, tzinfo=dt.timezone.utc)
    for query in INBOUND_OFFICIAL_NEWS_QUERIES:
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({
            "q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"
        })
        try:
            root = ET.fromstring(fetch(url, 12).content)
            successes += 1
        except Exception:
            continue
        for item in root.findall("./channel/item")[:25]:
            title = normalize(item.findtext("title") or "")
            link = normalize(item.findtext("link") or "")
            published_raw = item.findtext("pubDate") or ""
            origin = item.find("source")
            origin_domain = domain_of(origin.attrib.get("url", "") if origin is not None else "")
            if not any(origin_domain == d or origin_domain.endswith("." + d)
                       for d in INBOUND_OFFICIAL_DOMAINS):
                continue
            try:
                when = parsedate_to_datetime(published_raw)
                if when.tzinfo is None:
                    when = when.replace(tzinfo=dt.timezone.utc)
                when = when.astimezone(dt.timezone.utc)
                if when < threshold or when > dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=2):
                    continue
            except Exception:
                continue
            stage = inbound_official_stage(title) or inbound_us_policy_stage(title)
            if not stage:
                continue
            # Same publisher+headline = one milestone even across syndication URLs.
            key = sig("korean-inbound-official", origin_domain, normalize(title).lower())
            found[key] = {
                "key": key, "title": title, "url": link,
                "publisher": origin_domain, "stage": stage,
                "published": when.isoformat()
            }
    return list(found.values()), successes


def inbound_regression_checks() -> None:
    assert inbound_official_stage("Korea data center investment may rise") is None
    assert inbound_official_stage("Korea data center investor signs MOU") == "투자유치 양해각서(구속력·실제 집행 미확인)"
    assert inbound_official_stage("AWS South Korea AI data center signed contract") == "계약 체결 공식 발표(구체적 구속력 별도 확인)"
    assert inbound_official_stage("Texas data center moratorium extended") is None
    assert inbound_official_stage("Japan data center agreed investments") is None
    assert inbound_us_policy_stage("Texas governor-elect pledges data center moratorium") is None
    assert inbound_us_policy_stage("Texas data center construction could be delayed") is None
    assert inbound_us_policy_stage("Texas governor orders permit freeze on data center approvals") == "미국 주정부·전력당국 공식 인허가·감사 결정"
    assert inbound_us_policy_stage("ERCOT data center final audit report released in Texas") == "미국 주정부·전력당국 공식 인허가·감사 결정"
    assert not inbound_is_due({"last_context_id": INBOUND_DIVERSION_ID}, False,
                              {"texas_governor": True, "korea_government": True})
    assert not inbound_is_due({}, True, {"texas_governor": True, "korea_government": True})
    assert not inbound_is_due({}, False, {"texas_governor": True, "korea_government": False})
    assert inbound_is_due({}, False, {"texas_governor": True, "korea_signed_earlier": True})
    assert INBOUND_US_KOREA_SNAPSHOT["hana_2030_incremental_base_gw"][1] < INBOUND_US_KOREA_SNAPSHOT["hana_2030_incremental_bull_gw"][0]
    assert not INBOUND_US_KOREA_SNAPSHOT["post_us_election_relocation_to_korea_confirmed"]


def inbound_report(probe: dict, official_events: list[dict]) -> str:
    lines = [
        "<b>미국 데이터센터 규제 → 한국·일본 투자유치 가능성 | 11월 8일 보강</b>",
        "",
        "<b>■ 핵심: 정책 변화와 실제 계약을 분리</b>",
        "• <b>텍사스 기존 규제</b> │ 2026-09-21 애벗 주지사가 감사 완료 전 신규 데이터센터 환경 인허가 중단을 지시.",
        "• <b>선거 후 변화</b> │ 11월 3일 주지사 당선인은 2027년 1월 취임 후 신규 승인 중단 확대를 공약."
        " 주 전체 영구 건설중단·연방 전국 규제로 확정된 것은 아님.",
        "• <b>해외 이전</b> │ 하나·NH투자증권은 한국·일본의 해외투자 유치 기회를 전망."
        " 미국의 투자취소가 한국의 실계약·외국인투자로 자동 전환된 것은 아님.",
        "",
        "<b>■ 국내 투자 전망: 회사 실적·확정 수주 아님</b>",
        "• <b>하나증권 11월 6일 발행처 검색 색인</b> │ 2030 국내 AI 데이터센터 추가 유효수요"
        " 기본 3.0~4.2GW, 해외 공급 지연 수혜를 반영한 낙관 5.1~7.0GW.",
        "• <b>공사비 수주 시장 추정</b> │ 공급 4~5GW일 경우 약 30조~40조원."
        " 총사업비·개별 건설사 확정 계약액과 구분.",
        "• <b>NH투자증권</b> │ 일본·한국 수혜, 해저광케이블·전력·인허가 경쟁력 전망."
        " 원 연구보고서 본문 직접 확인 전(신문 인용·중개 게시글).",
        "",
        "<b>■ 실제 국내 투자·유치 실행 단계</b>",
        "• <b>KOTRA·한국데이터센터연합회</b> │ 11월 4일 외국인투자 유치 업무협약 체결 보도."
        " 산업통상부는 행사에서 체결 계획을 발표. 양해각서는 개별 빅테크 투자계약 아님.",
        "• <b>SK그룹·AWS 울산</b> │ 2025년 체결한 15년 협력사업."
        " 과기정통부 기존 일정은 2027년 11월 41MW 부분 가동→2029년 2월 103MW 전체 가동.",
        " 2026년 미국 선거로 새로 한국에 옮긴 계약이라고 볼 근거 없음.",
        "• <b>SK텔레콤 장기 확장 목표</b> │ 국내 5GW를 2029년부터 단계적으로 추진,"
        " 장기 목표 15GW. 전체 확정 수주·전원 인가 용량이 아님.",
        "",
        "<b>■ 가장 중요한 실패경로·다음 알림 조건</b>",
        "• <b>실행 선행지표</b> │ 신규 미국 빅테크 실명 계약→확정 MW·투자액→부지·전력접속 확약"
        "→금융종결→착공→전원 인가→고객 가동.",
        "• <b>한국 측 역풍</b> │ CBRE 2026년 7월 수도권 전력·부지 부족."
        " 비수도권도 송변전·용수·냉각·지역 전기요금·허가·민원 비용을 확인해야 함.",
        "• <b>미국 측 조기경보</b> │ 텍사스 ERCOT 감사 결과 공개·차기 주정부의 실제 명령·"
        "지역 인허가 재개 또는 중단. 공약과 효력 발생을 구분.",
        "• <b>후속 신규 알림</b> │ 한국의 해외 빅테크 실제 계약·금융종결·착공·전원 인가"
        " 및 미국 규제의 신규 공식 결정만 별도 사건으로 판정.",
    ]
    if official_events:
        lines += ["", "<b>■ 신규 공식 발표 (원문 제목·단계)</b>"]
        for row in official_events:
            lines.append(f"• {h(row['stage'])} │ {a(row['title'], row['url'])}"
                         f" · {h(row['publisher'])} · {h(row['published'][:10])}")
    lines += [
        "", "<b>■ 확인한 근거·출처 단계</b>",
        f"• {a('텍사스 주정부 인허가 지시', INBOUND_TEXAS_GOV)} · {a('ERCOT 감사 일정', INBOUND_TEXAS_ERCOT)}",
        f"• {a('텍사스 차기 주지사 공약 보도', INBOUND_TEXAS_TRIBUNE)}",
        f"• {a('산업통상부 11월 외국인투자 행사 발표', INBOUND_MOTIR)}",
        f"• {a('KOTRA·KDCC 업무협약 체결 보도', INBOUND_KOTRA_SIGNED_REPORT)}",
        f"• {a('경향신문 11월 8일 원기사', INBOUND_KHAN)}",
        f"• {a('하나증권 공개 보고서 목록', INBOUND_HANA)} · {a('NH 메모 재게시', INBOUND_NH_REPOST)}",
        f"• {a('SK·AWS 공식 계약 발표', INBOUND_SKT_AWS)} · {a('과기정통부 울산 일정', INBOUND_MSIT_ULSAN)}",
        f"• {a('CBRE 한국 전력·부지 보고서', INBOUND_CBRE_KOREA)}",
        f"• 실시간 확인: 텍사스 공식={probe['texas_governor']} / 독립 보도={probe['texas_independent']}"
        f" / 한국 정부={probe['korea_government']} / SK·AWS 공식={probe['korea_signed_earlier']}",
    ]
    result = "\n".join(lines).strip()
    must = ("3.0~4.2GW", "5.1~7.0GW", "30조~40조원", "41MW", "103MW",
            "2027년", "2029년", "양해각서", "확정", "전원 인가",
            INBOUND_TEXAS_GOV, INBOUND_MOTIR, INBOUND_HANA, INBOUND_SKT_AWS)
    missing = [token for token in must if token not in result]
    if missing or result.count("<b>") != result.count("</b>") or result.count("<a href=") != result.count("</a>"):
        raise RuntimeError(f"해외 데이터센터 국내 유치 알림 누락·HTML 오류: {missing}")
    if any(len(line) > 2300 for line in result.splitlines()):
        raise RuntimeError("해외 유치 알림 긴 행 검증 실패")
    return result + "\n"


def run_inbound_diversion_extension() -> None:
    inbound_regression_checks()
    previous = dict(old.get("us_korea_investment_watch") or {})
    context_needed = previous.get("last_context_id") != INBOUND_DIVERSION_ID
    probe = inbound_primary_check() if context_needed else {}
    first = not old.get("initialized")
    perspective_due = inbound_is_due(previous, first, probe)
    official_rows, scan_ok = inbound_collect_official_announcements()
    previous_seen = list(previous.get("seen_official_event_ids") or [])
    new_events = [row for row in official_rows if row["key"] not in set(previous_seen)]
    if not perspective_due and not new_events:
        if STATUS.exists():
            with STATUS.open("a", encoding="utf-8") as fd:
                fd.write(
                    "- 미국→한국 투자유치 감시: 새 실계약 0건 · "
                    f"기준 보강={'공식 확인 대기' if context_needed else '기존 반영'}"
                    f" · 검색원천={scan_ok}/{len(INBOUND_OFFICIAL_NEWS_QUERIES)}\n"
                )
        print(f"korea_inbound_alert=false context_due={perspective_due} official_news_new=0")
        return
    if fx_source == "직전 저장값":
        # Keep dedupe state unchanged; do not mask live API failures with old FX.
        print("korea_inbound_alert=hold_fx_stale")
        return
    if not perspective_due and context_needed and not new_events:
        return

    # If an official new milestone exists but the introductory context lacks live
    # evidence, deliver ONLY the sourced milestone, not a reconstructed policy claim.
    if perspective_due:
        report = inbound_report(probe, new_events)
    else:
        lines = [
            "<b>미국 주정부 규제·한국 해외 빅테크 데이터센터 실제 단계 변화</b>",
            "• 전망·관심 표명과 계약·실제 전원 인가를 구분한 신규 공식 발표",
        ]
        for row in new_events:
            lines.append(f"• {h(row['stage'])} │ {a(row['title'], row['url'])}"
                         f" · {h(row['publisher'])} · {h(row['published'][:10])}")
        report = "\n".join(lines).strip() + "\n"
    pending = load_json(PENDING)
    next_stage = dict(previous)
    if perspective_due:
        next_stage["last_context_id"] = INBOUND_DIVERSION_ID
        next_stage["context_sent_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        next_stage["source_snapshot"] = INBOUND_US_KOREA_SNAPSHOT
        next_stage["live_primary_checks"] = probe
    next_stage["seen_official_event_ids"] = list(dict.fromkeys(
        previous_seen + [row["key"] for row in new_events]
    ))[-500:]
    next_stage["last_event_count"] = len(new_events)
    pending["us_korea_investment_watch"] = next_stage
    old_alert = ALERT.read_text(encoding="utf-8").strip() if ALERT.exists() else ""
    ALERT.write_text((old_alert + "\n\n" if old_alert else "") + report, encoding="utf-8")
    PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if STATUS.exists():
        with STATUS.open("a", encoding="utf-8") as fd:
            fd.write(f"- 미국→한국 투자유치 신규 공식자료: {len(new_events)}건"
                     f" · 신규 관점 보강={perspective_due}"
                     f" · 검색원천={scan_ok}/{len(INBOUND_OFFICIAL_NEWS_QUERIES)}\n")
    print(f"korea_inbound_alert=prepared context_due={perspective_due} new_official_milestones={len(new_events)}")


run_inbound_diversion_extension()


# BAAJA_POLICY_TRACKING_V1
# Federal BAAJA S.5653 via H.R.2347 is distinct from H.R.9340 (100 MW).
# Preserve ALL existing risk/financing/Korea alerts, state IDs, schedule and bot.
BAAJA_PROCEDURAL_ID = "baaja-20261109-hr2347-motion-to-proceed-cloture-73-25"
BAAJA_SENATE_WRAP = "https://www.democrats.senate.gov/2026/11/09/wrap-up-for-monday-november-9-2026"
BAAJA_EPW_NOV9 = "https://www.epw.senate.gov/public/index.cfm/press-releases-republican?ID=CCD27C16-CBA8-4E56-BFAE-C30D16E0AE61"
BAAJA_ENR_NOV7 = "https://www.energy.senate.gov/press/rep/lee-capito-heinrich-and-whitehouse-release-substitute-amendment-to-bipartisan-american-affordability-and-jobs-act-of-2026/"
BAAJA_BPC_NOV8 = "https://bipartisanpolicy.org/explainer/explaining-the-affordability-in-the-bipartisan-american-affordability-and-jobs-act/"
BAAJA_GPO_SEP30 = "https://www.govinfo.gov/content/pkg/BILLS-119s5653is/html/BILLS-119s5653is.htm"
BAAJA_RHODIUM_NOV2 = "https://rhg.com/research/baaja-us-energy-system-impacts/"
BAAJA_HOUSE_RPA_VOTE = "https://clerk.house.gov/evs/2026/roll312"
BAAJA_MCKINSEY = "https://www.mckinsey.com/capabilities/strategy-and-corporate-finance/our-insights/the-capex-crucible-what-finance-teams-can-learn-from-data-center-builds"
BAAJA_SANDERS_POST = "https://x.com/SenSanders/status/2118131101562454038"
BAAJA_PUBLIC_STATUS = "2026-11-09 Senate cloture on MOTION TO PROCEED 73-25; NOT final passage"
BAAJA_POLICY_REFERENCE = {
    "date": "2026-11-09",
    "bill_original": "S.5653, introduced 2026-09-30",
    "senate_vehicle": "H.R.2347 (motion to proceed), NOT H.R.9340",
    "substitute_amendment_released": "2026-11-07",
    "senate_motion_to_proceed_cloture_yes": 73,
    "senate_motion_to_proceed_cloture_no": 25,
    "stage": "심의 개시 관련 절차표결 통과, 상원 본안 최종 가결 전",
    "BAAJA_new_computational_load_mw_threshold": 20,
    "BAAJA_full_incremental_costs": "발전·저장·송전·배전 증분비용, 조기 사업철회 비용보호",
    "RPA_HR9340_house_threshold_mw": 100,
    "RPA_HR9340_house_vote": [417, 3],
    "RPA_HR9340_senate_cloture_sept30": [57, 43],
    "rhodium_model_initial_bill_nov2_power_price_increase_pct": [88, 102],
    "rhodium_model_1gw_annualized_capex_plus_opex_increase_pct": [10, 11],
    "rhodium_based_on_pre_nov7_substitute": True,
    "mckinsey_global_dc_construction_through_2030_usd_t_range": [1.7, 1.9],
    "mckinsey_1p8tn_as_enactment_unlocked_capex_verified": False,
    "sanders_moratorium_post_date": "2026-11-04",
    "nationwide_moratorium_implemented": False,
    "ferc_final_implementation": False,
    "scope": "절차 표결 != 최종 통과 != 시행; 주택 전기요금과 기업 부담의 실제 효과는 별도 규칙·시나리오",
    "primary_sources": [BAAJA_SENATE_WRAP, BAAJA_EPW_NOV9, BAAJA_ENR_NOV7,
                        BAAJA_GPO_SEP30, BAAJA_HOUSE_RPA_VOTE],
    "research_sources": [BAAJA_BPC_NOV8, BAAJA_RHODIUM_NOV2, BAAJA_MCKINSEY],
}

# Read official pages rather than equating third-party headlines with enactment.
def baaja_primary_source_checks() -> dict:
    def page(url: str, required: tuple[tuple[str, ...], ...]) -> bool:
        try:
            from bs4 import BeautifulSoup
            clean = normalize(BeautifulSoup(fetch(url, 14).text, "html.parser").get_text(" ")).lower()
            return all(any(phrase in clean for phrase in group) for group in required)
        except Exception:
            return False
    return {
        "senate_vote": page(BAAJA_SENATE_WRAP,
                            (("motion to invoke cloture",), ("h.r.2347", "h.r. 2347"),
                             ("73-25", "73 - 25"))),
        "senate_sponsor": page(BAAJA_EPW_NOV9,
                               (("bipartisan american affordability",),
                                ("73-25", "73 - 25"))),
        "cost_threshold": page(BAAJA_BPC_NOV8,
                               (("20 megawatts", "20 mw"),
                                ("incremental",), ("data center", "data centers"))),
        "govinfo_bill": page(BAAJA_GPO_SEP30,
                             (("sec. 2107",), ("20 megawatts",),
                              ("incremental cost",))),
        "rhodium_model": page(BAAJA_RHODIUM_NOV2,
                              (("88-102%", "88–102%"), ("10-11%", "10–11%"),
                               ("annualized capital and operating",))),
    }


def baaja_procedural_due(previous: dict, first: bool, checks: dict, fresh_fx: bool) -> bool:
    """Require a Senate first-party procedural record plus independent text review."""
    return bool(not first and fresh_fx
                and previous.get("procedural_id") != BAAJA_PROCEDURAL_ID
                and (checks.get("senate_vote") or checks.get("senate_sponsor"))
                and (checks.get("cost_threshold") or checks.get("govinfo_bill")))


def baaja_later_stage(title: str) -> str | None:
    """False positive protection: words 'advance' and 'cloture' are not passage."""
    t = normalize(html.unescape(title)).lower().replace("h.r. 2347", "h.r.2347")
    if not any(x in t for x in (
        "baaja", "bipartisan american affordability and jobs act", "h.r.2347",
        "s.5653", "s. 5653",
    )):
        return None
    if any(x in t for x in (
        "cloture", "motion to proceed", "procedural", "advances", "advance",
        "committee", "urges", "seeks to", "could", "might",
        "calls for", "support for", "opposes", "amendment to",
    )):
        return None
    if re.search(r"\b(?:president|white house)\b.{0,50}\b(?:signs|signed)\b", t) and "law" in t:
        return "대통령 서명·법률 제정 공식 발표"
    if re.search(r"\bsenate\b.{0,40}\b(?:passes|passed|approves|approved)\b", t) or re.search(
        r"\b(?:passes|passed)\b.{0,40}\bsenate\b", t
    ):
        return "상원 본안 최종 의결 공식 발표"
    if re.search(r"\bhouse\b.{0,40}\b(?:passes|passed|approves|approved)\b", t) or re.search(
        r"\b(?:passes|passed)\b.{0,40}\bhouse\b", t
    ):
        return "하원 본안 최종 의결 공식 발표"
    if "ferc" in t and any(w in t for w in (
        "final rule", "final rules", "final regulation", "adopts implementing",
    )):
        return "FERC 시행 세부규칙 최종 발표"
    return None


BAAJA_OFFICIAL_INDEXES = (
    ("https://www.epw.senate.gov/public/index.cfm/press-releases-republican", "epw.senate.gov"),
    ("https://www.energy.senate.gov/press/rep", "energy.senate.gov"),
    ("https://energycommerce.house.gov/posts", "energycommerce.house.gov"),
    ("https://www.whitehouse.gov/briefings-statements/", "whitehouse.gov"),
    ("https://www.ferc.gov/news-events/news/decisions-notices", "ferc.gov"),
)


def baaja_collect_future_official() -> tuple[list[dict], dict]:
    """A same-publisher announcement; not the news feed's interpretation."""
    from bs4 import BeautifulSoup
    now = dt.datetime.now(dt.timezone.utc)
    result = {}
    health = {}
    for index, domain in BAAJA_OFFICIAL_INDEXES:
        health[domain] = False
        try:
            soup = BeautifulSoup(fetch(index, 10).text, "html.parser")
            health[domain] = True
            for tag in soup.find_all("a", href=True)[:300]:
                title = normalize(tag.get_text(" "))
                stage = baaja_later_stage(title)
                if not stage:
                    continue
                url = urllib.parse.urljoin(index, tag.get("href") or "")
                actual = domain_of(url)
                if actual != domain and not actual.endswith("." + domain):
                    continue
                try:
                    detail = normalize(BeautifulSoup(fetch(url, 10).text,
                                                      "html.parser").get_text(" ")).lower()
                    # Explicitly demand a recent publication date and BAAJA named bill.
                    # Never classify a general Senate rollcall or H.R.9340 as this act.
                    name_ok = any(t in detail for t in (
                        "bipartisan american affordability and jobs act",
                        "baaja", "s. 5653", "s.5653"
                    ))
                    date_ok = bool(re.search(
                        r"november\s+(?:1[0-9]|2[0-9]|30),?\s+2026|2026[-/]11[-/](?:1[0-9]|2[0-9]|30)",
                        detail
                    ))
                    if not (name_ok and date_ok):
                        continue
                except Exception:
                    continue
                fingerprint = sig("baaja-stage", stage, normalize(title).lower())
                result[fingerprint] = {
                    "id": fingerprint, "stage": stage, "title": title[:260],
                    "source": domain, "url": url,
                }
        except Exception:
            continue
    return list(result.values()), health


def baaja_policy_regression_checks() -> None:
    assert baaja_later_stage("Senate advances BAAJA 73-25 procedural cloture") is None
    assert baaja_later_stage("BAAJA passes key Senate procedural hurdle") is None
    assert baaja_later_stage("Senate passes H.R.9340 Ratepayer Protection Act") is None
    assert baaja_later_stage("Senate passes BAAJA final legislation") == "상원 본안 최종 의결 공식 발표"
    assert baaja_later_stage("House passes Bipartisan American Affordability and Jobs Act") == "하원 본안 최종 의결 공식 발표"
    assert baaja_later_stage("President signs BAAJA into law") == "대통령 서명·법률 제정 공식 발표"
    assert baaja_later_stage("BAAJA Senate managers amendment released") is None
    checks = {"senate_vote": True, "senate_sponsor": False,
              "cost_threshold": True, "rhodium_model": True}
    assert baaja_procedural_due({}, False, checks, True)
    assert not baaja_procedural_due({"procedural_id": BAAJA_PROCEDURAL_ID},
                                    False, checks, True)
    assert not baaja_procedural_due({}, True, checks, True)
    assert not baaja_procedural_due({}, False, {**checks, "cost_threshold": False}, True)
    assert baaja_procedural_due({}, False, {**checks, "cost_threshold": False,
                                           "govinfo_bill": True, "rhodium_model": False}, True)
    assert baaja_procedural_due({}, False, {**checks, "rhodium_model": False}, True)
    assert not baaja_procedural_due({}, False, checks, False)
    b = BAAJA_POLICY_REFERENCE
    assert b["BAAJA_new_computational_load_mw_threshold"] == 20
    assert b["RPA_HR9340_house_threshold_mw"] == 100
    assert b["rhodium_model_1gw_annualized_capex_plus_opex_increase_pct"] == [10, 11]
    assert not b["mckinsey_1p8tn_as_enactment_unlocked_capex_verified"]


def baaja_procedural_alert(fx: float, checks: dict) -> str:
    lines = [
        "<b>미국 BAAJA 데이터센터 인허가·비용부담 법안: 11월 9일 절차표결</b>",
        "",
        "<b>■ 핵심 변화 · 정확한 의회 단계</b>",
        "• <b>11월 9일 상원 73대25</b> │ H.R.2347에 대한 심의 개시 동의안의 토론종결(cloture) 표결 통과.",
        "  <b>BAAJA 본안 최종 가결 아님.</b> 상원 본안·하원·대통령 서명·FERC 시행 절차는 별도.",
        "• <b>S.5653</b> │ 9월30일 발의, 11월7일 대체수정안 발표."
        " 캐피토·화이트하우스·리·하인릭 4명 초당적 공동 발의.",
        "• <b>20MW 이상</b> │ BAAJA 2107조 신규 데이터센터는 발전·저장·송전·배전 등"
        " 수요 때문에 추가 발생한 증분비용 전액을 부담하도록 하는 제안.",
        "  단일 부지뿐 아니라 동일 소유·통제 아래 여러 부지의 부하를 합산할 수 있으며,"
        " 단계별 증설의 전체 준공 예상 부하도 20MW 판정에 포함.",
        "  고객이 조기 철수해도 나머지 전력소비자에게 비용이 전가되지 않도록 하는 조건.",
        "",
        "<b>■ 별도 법안과 반드시 구분</b>",
        "• <b>H.R.9340 전력 소비자 보호법</b> │ 신규 대형 부하 <b>100MW 이상</b>."
        " 9월16일 하원 417대3 통과, 9월30일 상원 심의 개시 토론종결 57대43로 실패.",
        "  주 전기요금 규제기관이 비용회수 기준을 검토하도록 하는 제도이며 BAAJA 20MW 의무와 별개.",
        "• <b>정치적 발언</b> │ 샌더스 전국 데이터센터 일시중단 촉구 X 게시일 11월4일."
        " 전국 중단 법령은 시행되지 않았고 이번 인허가 법안과 별도 입법 흐름.",
        "• <b>화이트하우스</b> │ 공동 발의 민주당 상원의원 Sheldon Whitehouse,"
        " 백악관(White House) 기관과 동명이지만 서로 다른 당사자."
        " 하원 민주당 지도부는 환경·원주민 권리 보호에 대해 유보.",
        "",
        "<b>■ 실제 비용 영향: 연구 시나리오와 법 적용 분리</b>",
        "• <b>로디움그룹 11월2일 모델</b> │ 완전 시행 시 데이터센터가 납부하는"
        " 전력망 연결 소매 전력가격 <b>+88~102%</b> 추정.",
        f"  검증 단계: {'이번 실행 원문 직접 재확인' if checks.get('rhodium_model') else '이번 실행 원문 접근 미확인·11월2일 발표 기준선'}.",
        "• <b>1GW 데이터센터 전체 연간 환산 비용</b> │ 설비투자와 운영비 합산"
        " <b>+10~11%</b> 추정. 운영비만 10% 증가 또는 이미 확정된 인상이 아님.",
        "• <b>연구 가정</b> │ 9월30일 초기 BAAJA 문안을 바탕으로 한 모델;"
        " 11월7일 대체 수정안·개별 요금제·전력믹스 반영 효과는 별도 검증.",
        f"• <b>맥킨지 1조8,000억달러({krw_from_usd(1.8e12, fx)})</b>는"
        " BAAJA 가결로 즉시 해제되는 사업비가 아님.",
        " 2030년까지 전 세계 데이터센터 건설비 약 1조7,000억~1조9,000억달러라는"
        " 별도 투자 수요 전망의 중간 규모와 혼동 금지.",
        "",
        "<b>■ 전력망·수익구조와 다음 조기경보</b>",
        "• 인허가·송전망 증설이 빨라지더라도 FERC 규칙제정, 주 규제기관의"
        " 비용배분 승인, 전력망 실제 착공·전원 인가가 남음.",
        "• 설비·허가 시차의 수혜 가능 기업은 송변전, 시공, 발전, 냉각 업체."
        " 확정 수주·금융종결·납품 매출과 산업 수요 전망 분리.",
        "• 추적 단계: 상원 최종표결 → 하원 본안 처리 → 대통령 서명 →"
        " FERC 시행규칙 → 전력요금·접속계약 변경 → 실제 전원 인가 MW.",
        "• 최대 역풍: 전력망 조달비 100% 부담으로 미확정 프로젝트 금융성 악화,"
        " 지역별 소송·원주민 보호 쟁점으로 하원 통과 지연.",
        "",
        "<b>■ 공식 원문 · 연구 근거</b>",
        f"• {a('11월9일 미 상원 표결 공식 기록', BAAJA_SENATE_WRAP)}",
        f"• {a('11월9일 상원 EPW 공식 발표', BAAJA_EPW_NOV9)}",
        f"• {a('11월7일 상원 대체수정안 발표', BAAJA_ENR_NOV7)}",
        f"• {a('S.5653 9월30일 발의 법안 원문', BAAJA_GPO_SEP30)}",
        f"• {a('20MW 규정: Bipartisan Policy Center', BAAJA_BPC_NOV8)}",
        f"• {a('로디움그룹 +88~102%·+10~11% 모델', BAAJA_RHODIUM_NOV2)}",
        f"• {a('H.R.9340 하원 417대3 공식 기록', BAAJA_HOUSE_RPA_VOTE)}",
        f"• {a('맥킨지 글로벌 건설비 추정', BAAJA_MCKINSEY)}",
        f"• 환율: 1달러={fx:,.2f}원 · {h(fx_source)} · {h(fx_checked)} UTC",
        f"• 실행 당시 근거 재조회: 상원기록={checks.get('senate_vote')},"
        f" EPW={checks.get('senate_sponsor')}, BPC20MW={checks.get('cost_threshold')},"
        f" GPO20MW={checks.get('govinfo_bill')}, 로디움={checks.get('rhodium_model')}",
    ]
    complete = "\n".join(lines).strip()
    mandatory = ("73대25", "본안 최종 가결 아님", "20MW", "100MW", "417대3",
                 "57대43", "+88~102%", "+10~11%", "1GW", "하원",
                 BAAJA_SENATE_WRAP, BAAJA_EPW_NOV9, BAAJA_BPC_NOV8,
                 BAAJA_RHODIUM_NOV2)
    missing = [x for x in mandatory if x not in complete]
    if missing:
        raise RuntimeError(f"BAAJA 법안 단계·원문 수치 송출 전 누락: {missing}")
    if complete.count("<b>") != complete.count("</b>") or complete.count("<a href=") != complete.count("</a>"):
        raise RuntimeError("BAAJA Telegram HTML 태그 불일치")
    if any(len(line) > 2300 for line in lines):
        raise RuntimeError("BAAJA Telegram 한 줄 길이 제한 초과")
    return complete + "\n"


def baaja_run_existing_risk_watch() -> None:
    baaja_policy_regression_checks()
    previous = dict(old.get("baaja_permitting_policy") or {})
    initial_needed = previous.get("procedural_id") != BAAJA_PROCEDURAL_ID
    source_checks = baaja_primary_source_checks() if initial_needed else {}
    due = baaja_procedural_due(previous, not old.get("initialized"), source_checks,
                               fx is not None and fx_source != "직전 저장값")
    later_events, feed_health = baaja_collect_future_official()
    previous_seen = list(previous.get("official_later_event_ids") or [])
    new_events = [x for x in later_events if x["id"] not in set(previous_seen)]
    if not due and not new_events:
        if STATUS.exists():
            with STATUS.open("a", encoding="utf-8") as fd:
                fd.write("- BAAJA 정책: 신규 실질 법안단계 없음"
                         f" · 11월9일 공식 재조회={source_checks}"
                         f" · 향후 의회 원천={feed_health}\n")
        print(f"baaja_policy_no_new_stage=true sources={source_checks} later={feed_health}")
        return
    if fx is None or fx_source == "직전 저장값":
        # Never invent a current KRW rate or consume an unsent stage.
        print("baaja_policy_hold_stale_fx=true")
        return
    chunks = []
    if due:
        chunks.append(baaja_procedural_alert(fx, source_checks).strip())
    if new_events:
        msgs = [
            "<b>미국 BAAJA 정식 입법·시행 단계 변화 (공식기관 자료)</b>",
            "• <b>절차표결·최종 가결·법률 제정·실제 시행을 서로 구분</b>",
        ]
        for event in new_events:
            msgs.append(f"• {h(event['stage'])} │ {a(event['title'], event['url'])}"
                        f" · {h(event['source'])}")
        msgs.append("• 실제 시행·기업 비용 전가·전원 인가 일자는 공식 시행규칙·"
                    "관할 전력시장·주정부 자료 확인 전 확정하지 않음.")
        chunks.append("\n".join(msgs))
    report = "\n\n".join(chunks).strip()
    if not report:
        return
    pending = load_json(PENDING)
    state = dict(previous)
    if due:
        state["procedural_id"] = BAAJA_PROCEDURAL_ID
        state["procedural_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        state["reference"] = BAAJA_POLICY_REFERENCE
        state["source_checks"] = source_checks
        state["latest_stage"] = "절차표결 통과, 상원 본안 가결 전"
    if new_events:
        # Index order is not legislative order. Never downgrade "signed" to "passed"
        # just because an older announcement appears later in the source list.
        ranking = {
            "절차표결 통과, 상원 본안 가결 전": 1,
            "상원 본안 최종 의결 공식 발표": 2,
            "하원 본안 최종 의결 공식 발표": 3,
            "대통령 서명·법률 제정 공식 발표": 4,
            "FERC 시행 세부규칙 최종 발표": 5,
        }
        stage_choices = [state.get("latest_stage") or ""] + [x["stage"] for x in new_events]
        state["latest_stage"] = max(stage_choices, key=lambda x: ranking.get(x, 0))
    state["official_later_event_ids"] = list(dict.fromkeys(
        previous_seen + [x["id"] for x in new_events]
    ))[-200:]
    state["last_new_event_count"] = len(new_events)
    pending["baaja_permitting_policy"] = state
    original_alert = ALERT.read_text(encoding="utf-8").strip() if ALERT.exists() else ""
    ALERT.write_text((original_alert + "\n\n" if original_alert else "") + report + "\n",
                     encoding="utf-8")
    PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
    if STATUS.exists():
        with STATUS.open("a", encoding="utf-8") as fd:
            fd.write(f"- BAAJA 신규 보강={due} · 이후 공식 단계={len(new_events)}"
                     f" · 공식 원천 확인={source_checks} · 색인={feed_health}\n")
    print(f"baaja_policy_prepared_initial={due} new_official_stages={len(new_events)}")
    

baaja_run_existing_risk_watch()
