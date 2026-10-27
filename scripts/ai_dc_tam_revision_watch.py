#!/usr/bin/env python3
from __future__ import annotations

import email.utils
import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

try:
    from googlenewsdecoder import gnewsdecoder
except Exception:
    gnewsdecoder = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "ai_dc_tam_revision_state.json"
OUT = ROOT / "out"
ALERT = OUT / "ai_dc_tam_revision_alert.txt"
PENDING = OUT / "ai_dc_tam_revision_pending_state.json"
STATUS = OUT / "ai_dc_tam_revision_status.md"

KST = ZoneInfo("Asia/Seoul")
UA = "Mozilla/5.0 khs-ai-dc-tam-watch/1.0"
GOOGLE_NEWS = "https://news.google.com/rss/search"

BASELINE = {
    "source": "BofA Global Research 2차 공개보도 기준",
    "as_of": "2026-10-01",
    "ai_dc_system_tam_2030_usd_t": 2.2,
    "ai_dc_system_tam_prior_usd_t": 1.8,
    "ai_dc_cagr_pct": 40.0,
    "server_cpu_tam_2030_usd_b": 210.6,
    "server_cpu_tam_2026_usd_b": 61.4,
    "cloud_capex_2026_usd_t": 1.0,
    "cloud_capex_2027_usd_t": 1.4,
    "cloud_capex_2030_low_usd_t": 2.0,
    "cloud_capex_2030_high_usd_t": 3.0,
    "training_cpu_per_gpu": 0.25,
    "agentic_cpu_per_gpu": 1.0,
}

# Global data-center spending and whole-facility cost are NOT the existing BofA AI systems TAM.
BOFA_GLOBAL_ID = "bofa-global-dc-spending-20261023-reuters-cost-per-mw"
BOFA_GLOBAL_REUTERS = "https://www.reuters.com/business/data-center-spending-more-than-double-21-trillion-by-2028-2026-10-23/"
BOFA_GLOBAL_TECHTIMES = "https://www.techtimes.com/articles/329486/20261026/bank-america-data-center-market-will-top-2-trillion-2028-ai-driven-build.htm"
BOFA_GLOBAL_SYNDICATED = "https://www.channelnewsasia.com/business/data-center-spending-more-double-21-trillion-2028-bofa-says-6487191"
BOFA_GLOBAL_REFERENCE = {
    "research_note_date": "2026-10-23",
    "global_spending_2026_usd_t": 1.0,
    "global_spending_2028_usd_t": 2.1,
    "global_market_2030_usd_t": 2.93,
    "global_market_2022_usd_b": 275.0,
    "market_2025_2030_cagr_pct": 37.0,
    "standard_dc_total_usd_m_per_mw": 49.0,
    "ai_dc_total_usd_m_per_mw": 57.0,
    "standard_dc_it_cost_pct": 78.0,
    "standard_dc_server_usd_m_per_mw": 31.4,
    "standard_dc_network_usd_m_per_mw": 4.8,
    "component_range_usd_m_per_mw": [0.1, 1.1],
    "geography": "전 세계",
    "source_grade": "Reuters 10월 23일 및 TechTimes 10월 26일 공개보도. BofA 원보고서 미확보",
    "scope_warning": "종전 BofA 2030 AI 데이터센터 시스템시장 2.2조달러와 전체 시장 2.93조달러는 동일 분모 미확인",
    "sources": [BOFA_GLOBAL_REUTERS, BOFA_GLOBAL_TECHTIMES, BOFA_GLOBAL_SYNDICATED],
}

# 13 October 2026 JPMorgan Hardware & Networking research, independently repeated
# by multiple secondary outlets. The paywalled original is NOT verified.
JPM_REFERENCE = {
    "as_of": "2026-10-13",
    "source_grade": "JP모건 증권사 추정 · 리포트 원문 직접 미확인 · 2차 보도 2곳 이상 교차",
    "top4_growth_2026_pct": 85.0, "top4_prior_2026_pct": 80.0,
    "top4_growth_2027_pct": 70.0, "top4_prior_2027_pct": 50.0,
    "top4_increment_2026_b_floor": 270.0,
    "top4_increment_2027_b_floor": 400.0,
    "na_planned_2026q2_gw_floor": 200.0,
    "na_installed_2025_gw": 54.0,
    "na_installed_2026_gw": 82.0,
    "na_installed_2027_gw": 125.0,
    "all_provider_capex_2026_b_approx": 800.0,
    "all_provider_capex_2027_b_approx": 1500.0,
    "tier2_capex_2026_b_floor": 200.0,
    "tier2_capex_2027_b_floor": 370.0,
    "top4_dc_capex_ocf_2026_pct": 80.0,
    "top4_dc_capex_ocf_2027_pct": 111.0,
}
JPM_BASELINE_EVENT = "jpm-cloud-dc-2026-10-13-85-70-54-82-125"
JPM_NETWORKING_EVENT = "jpm-cloud-dc-networking-2026-10-13-nine-suppliers"
JPM_NETWORKING_TICKERS = ("LITE", "COHR", "FN", "GLW", "APH", "CRDO", "ANET", "CIEN", "CLS")
JPM_CORNING_META_URL = "https://www.corning.com/emea/en/about-us/news-events/news-releases/2026/01/corning-and-meta-announce-multiyear-up-to-6-billion-agreement-to-accelerate-us-data-center-buildout.html"
JPM_CELESTICA_Q2_URL = "https://corporate.celestica.com/node/17621/html"
JPM_CIENA_VI_URL = "https://investor.ciena.com/news/news-details/2026/Vodafone-Idea-Deploys-Cienas-WaveLogic-6-Extreme-to-Deliver-High-Capacity-Connectivity-03-31-2026/default.aspx"
JPM_SECONDARY_SOURCES = (
    "https://www.macrostream.ai/articles/6ace3ff6f30e248c424121dd",
    "https://streetsignal.substack.com/p/streetsignal-morning-call-10132026",
)
JPM_FINANCE_OFFICIAL = "https://www.jpmorgan.com/insights/banking/capital-markets/financing-ai-infrastructure-data-centers"

# Article address supplied by the user; its contents are NOT a verified primary
# source until confirmed by the publisher's own feed with numeric evidence.
SEMIA_2027_ARTICLE = "https://newsletter.semianalysis.com/p/datacenters-2027-the-year-of-acceleration"
SEMIA_2027_RSS = "https://newsletter.semianalysis.com/feed"
SEMIA_2027_ID = "semianalysis-2027-acceleration-primary-evidence-20261019"
SEMIA_LEASE_CORRECTION_ID = "semianalysis-2027-lease-conflict-clarification-20261019"
SEMIA_DAYONE_SOLUTION_URL = "https://dayonedc.com/our-solutions"
SEMIA_DAYONE_2026_FINANCING_URL = "https://dayonedc.com/headliners/dayone-upsizes-malaysia-financing-to-us7-2-billion-total-billings-surpass-1gw-and-bookings-reach-2-3gw"
SEMIA_2027_USER_EXCERPT = {
    "2027_new_capacity_headline_gw": 50,
    "under_construction_gw": 60,
    "advanced_2027_construction_gw_floor": 24,
    "advanced_campuses": 40,
    "older_semianalysis_2027_gw": 43,
    "altimeter_2027_gw_opinion": 25,
    "claimed_ytd_lease_commitments_usd_t": 1.3,
    "hypothetical_cost_per_gw_usd_b": 50,
    "comparator_2027_capex_usd_t": 1.5,
    "geography": "원문 원자료 확인 전 미확정",
    "power_basis": "총전력/IT전력/전원인가 여부 원문 확인 전 미확정",
    "provenance": "사용자 제공 기사 발췌; 원문 수치 독립 검증 전",
}
JPM_NEWS_QUERIES = (
    'JPMorgan top four cloud data center capex growth forecast revised 2026 2027',
    'J.P. Morgan hardware networking four CSP data center capex growth 2027',
)

QUERIES = (
    'BofA AI data center systems market 2030',
    'Bank of America data center systems TAM AI 2030',
    'BofA server CPU 2030 agentic AI',
    'BofA cloud capex 2027 AI infrastructure',
    'BofA global data center spending 2028 2.1 trillion 2030 2.93 trillion',
    'Bank of America data center 49 million MW 57 million neocloud servers networking',
    'Vivek Arya AI data center systems 2030',
)

SEED_URLS = (
    ("Yahoo Finance", "https://ca.finance.yahoo.com/news/ai-spending-will-fuel-wins-for-micron-nvidia-intel-and-other-chip-stocks-bofa-analyst-193925832.html"),
    ("Investing.com", "https://www.investing.com/news/stock-market-news/bofa-lifts-server-cpu-tam-to-210bn-on-the-rise-of-ai-agents-4857499?ampMode=1"),
    ("Finvaulta", "https://finvaulta.com/research/bank-of-america/rise-of-the-agents-raising-cpu-tam-again-to-210bn-2026-08-12"),
    ("StreetSignal", "https://streetsignal.substack.com/p/streetsignal-morning-call-9302026-09e"),
)

TRUSTED = (
    "Investing.com", "Yahoo Finance", "Reuters", "Bloomberg", "CNBC",
    "Financial Times", "Barron's", "MarketWatch",
)


def fetch(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value or ""))).strip()


def gnews_url(query: str) -> str:
    return GOOGLE_NEWS + "?" + urllib.parse.urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})


def decode_news(url: str) -> str:
    if "news.google.com" not in url:
        return url
    if gnewsdecoder is None:
        return ""
    try:
        result = gnewsdecoder(url, interval=0.1)
        if isinstance(result, dict) and result.get("status"):
            decoded = str(result.get("decoded_url") or "").strip()
            if decoded.startswith("http"):
                return decoded
    except Exception:
        pass
    return ""


def parse_date(value: str):
    try:
        dt = email.utils.parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def trusted_source(source: str) -> bool:
    low = source.lower()
    return any(x.lower() in low for x in TRUSTED)


def article_text(url: str) -> str:
    if not url:
        return ""
    try:
        return clean(fetch(url, 18).decode("utf-8", errors="ignore"))[:45000]
    except Exception:
        return ""


def collect(now: datetime) -> list[dict]:
    out = []
    cutoff = now - timedelta(days=90)
    for query in QUERIES:
        try:
            root = ET.fromstring(fetch(gnews_url(query), 20))
        except Exception:
            continue
        for item in root.findall("./channel/item")[:30]:
            title = clean(item.findtext("title") or "")
            desc = clean(item.findtext("description") or "")
            link = clean(item.findtext("link") or "")
            source_node = item.find("source")
            source = clean(source_node.text if source_node is not None else "")
            pub = parse_date(clean(item.findtext("pubDate") or ""))
            if pub and pub < cutoff:
                continue
            if not trusted_source(source):
                continue
            direct = decode_news(link)
            body = article_text(direct)
            blob = clean(f"{title} {desc} {body}")
            low = blob.lower()
            if "bofa" not in low and "bank of america" not in low and "vivek arya" not in low:
                continue
            if "data center" not in low and "server cpu" not in low and "cloud capex" not in low:
                continue
            ident = hashlib.sha256((direct or link or title).encode("utf-8")).hexdigest()[:24]
            out.append({
                "id": ident,
                "title": title,
                "source": source,
                "url": direct or link,
                "published_at": pub.isoformat() if pub else "",
                "text": blob,
            })
    for source, url in SEED_URLS:
        try:
            blob = article_text(url)
            if not blob:
                continue
            low = blob.lower()
            if "bofa" not in low and "bank of america" not in low and "vivek arya" not in low:
                continue
            ident = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
            out.append({
                "id": ident,
                "title": clean(blob[:220]),
                "source": source,
                "url": url,
                "published_at": "",
                "text": blob,
            })
        except Exception:
            pass

    uniq = {}
    for row in out:
        uniq[row["id"]] = row
    return list(uniq.values())


def num(s: str) -> float | None:
    try:
        return float(str(s).replace(",", ""))
    except Exception:
        return None


def extract_metrics(text: str) -> dict:
    low = text.lower()
    out = {}
    if "bofa" not in low and "bank of america" not in low and "vivek arya" not in low:
        return out

    patterns = [
        ("ai_dc_system_tam_2030_usd_t", [
            r"(?:2030[^.]{0,120}?)?\$?([0-9]+(?:\.[0-9]+)?)\s*(?:trillion|tn|t)[^.]{0,120}?(?:data center systems|ai data center systems|data-center systems)",
            r"(?:data center systems|ai data center systems|data-center systems)[^.]{0,120}?\$?([0-9]+(?:\.[0-9]+)?)\s*(?:trillion|tn|t)[^.]{0,80}?2030",
        ], 0.5, 5.0),
        ("server_cpu_tam_2030_usd_b", [
            r"(?:server cpu|cpu)[^.]{0,120}?(?:2030[^.]{0,80}?)?\$?([0-9]{2,4}(?:\.[0-9]+)?)\s*(?:billion|bn)",
            r"\$?([0-9]{2,4}(?:\.[0-9]+)?)\s*(?:billion|bn)[^.]{0,120}?(?:server cpu|cpu)[^.]{0,80}?2030",
        ], 50, 600),
        ("cloud_capex_2026_usd_t", [
            r"2026[^.]{0,100}?(?:capex|capital spending)[^.]{0,80}?\$?([0-9]+(?:\.[0-9]+)?)\s*(?:trillion|tn|t)",
            r"(?:capex|capital spending)[^.]{0,80}?2026[^.]{0,80}?\$?([0-9]+(?:\.[0-9]+)?)\s*(?:trillion|tn|t)",
        ], 0.3, 3.0),
        ("cloud_capex_2027_usd_t", [
            r"2027[^.]{0,100}?(?:capex|capital spending)[^.]{0,80}?\$?([0-9]+(?:\.[0-9]+)?)\s*(?:trillion|tn|t)",
            r"(?:capex|capital spending)[^.]{0,80}?2027[^.]{0,80}?\$?([0-9]+(?:\.[0-9]+)?)\s*(?:trillion|tn|t)",
        ], 0.3, 4.0),
    ]
    for key, pats, lo, hi in patterns:
        for pat in pats:
            m = re.search(pat, text, re.I)
            if not m:
                continue
            v = num(m.group(1))
            if v is not None and lo <= v <= hi:
                out[key] = v
                break

    # CAGR is only the AI data-center *systems* series, not the total worldwide
    # market-wide CAGR from the separate Oct-23 BofA note.
    for m in re.finditer(r"(?:annual pace|cagr|annual growth)[^.]{0,50}?([0-9]{1,2}(?:\.[0-9]+)?)%", text, re.I):
        window = low[max(0, m.start()-160):min(len(low), m.end()+80)]
        if not any(x in window for x in ("data center systems", "data-center systems", "ai infrastructure systems")):
            continue
        v = num(m.group(1))
        if v and 10 <= v <= 80:
            out["ai_dc_cagr_pct"] = v
            break

    if re.search(r"(?:1\s*:\s*4|one cpu for every four gpus|four gpus.*one cpu)", text, re.I):
        out["training_cpu_per_gpu"] = 0.25
    if re.search(r"(?:1\s*:\s*1|one-to-one|1-to-1)", text, re.I) and ("agent" in low or "agentic" in low):
        out["agentic_cpu_per_gpu"] = 1.0
    return out


def bofa_global_due(prev: dict, fx: dict, first: bool) -> bool:
    return bool(not first and fx.get("usdkrw") and prev.get("delivered_id") != BOFA_GLOBAL_ID)


def bofa_global_checks() -> None:
    assert BOFA_GLOBAL_REFERENCE["global_spending_2028_usd_t"] == 2.1
    assert abs(49 * .78 - 38.22) < 1e-9
    assert abs(31.4 + 4.8 + 2.02 + 10.78 - 49) < 1e-9
    assert bofa_global_due({}, {"usdkrw": 1325}, False)
    assert not bofa_global_due({"delivered_id": BOFA_GLOBAL_ID}, {"usdkrw":1325}, False)
    assert not bofa_global_due({}, {}, False)
    assert not bofa_global_due({}, {"usdkrw":1325}, True)
    assert "ai_dc_system_tam_2030_usd_t" not in extract_metrics(
        "BofA global data center spending $2.93 trillion by 2030")
    assert extract_metrics("BofA projects $2.2 trillion data center systems by 2030").get(
        "ai_dc_system_tam_2030_usd_t") == 2.2
    assert "ai_dc_cagr_pct" not in extract_metrics("BofA global data center market CAGR 37% by 2030")
    assert extract_metrics("BofA AI data center systems CAGR 40% by 2030").get(
        "ai_dc_cagr_pct") == 40.0


def bofa_global_alert(fx: dict) -> str:
    rate = float(fx["usdkrw"])
    m = lambda v: krw_from_usd_b(v / 1000, rate)
    lines = [
        "BofA 데이터센터 글로벌 지출·1MW 비용 별도 보강 (2026년 10월 23일 전망)",
        "",
        "■ 핵심 수치",
        f"• 2026년 세계 지출 1조달러({krw_from_usd_t(1,rate)}) →"
        f" 2028년 2조1,000억달러({krw_from_usd_t(2.1,rate)})."
        " 110% 증가 전망이며 확정 발주·가동물량 아님.",
        f"• 2030년 세계 시장 2조9,300억달러({krw_from_usd_t(2.93,rate)}),"
        " 2025~2030년 예상 연평균 성장률 37%.",
        f"• 일반 데이터센터 1MW 전체 구축비 4,900만달러({m(49)}),"
        f" AI 특화형 5,700만달러({m(57)}). AI형 프리미엄 약 16.3%.",
        "",
        "■ 일반형 1MW 비용 분해 (서버·네트워크는 전체 총사업비 비중)",
        f"• 서버 3,140만달러({m(31.4)}) · 64.1%.",
        f"• 네트워크 480만달러({m(4.8)}) · 9.8%.",
        f"• 기타 IT 자체 역산 202만달러({m(2.02)}) · 4.1%.",
        f"• 비IT 물리시설 자체 역산 1,078만달러({m(10.78)}) · 22.0%.",
        "• IT 전체 78%; 비IT는 건설·전력기기·냉각·설비·안전·소방 등."
        " 품목별 배분비율 미공개. 부품별 10만~110만달러/MW는 개별 품목 구간.",
        "",
        "■ 단위 물량 × 단가 감도 (미확정 지출 시나리오)",
        f"• 일반형 100MW 49억달러({krw_from_usd_b(4.9,rate)}),"
        f" 1GW 490억달러({krw_from_usd_b(49,rate)}).",
        f"• AI형 100MW 57억달러({krw_from_usd_b(5.7,rate)}),"
        f" 1GW 570억달러({krw_from_usd_b(57,rate)}).",
        "• 연간 지출액에 교체·확장 장비 등이 포함될 수 있어 지출÷MW단가로"
        " 신규 가동 GW를 산정하면 안 됨. IT 전력/총전력도 구분 필요.",
        "",
        "■ 기존 BofA 시스템 시장과 완전히 별도",
        f"• 기존 2030년 AI 데이터센터 시스템시장 2조2,000억달러"
        f"({krw_from_usd_t(2.2,rate)})는 유지. 이번 2조9,300억달러는 글로벌 전체 시장.",
        "• BofA 원본 유료 보고서를 확보하지 못해 세부 포함범위는 확인 불가."
        " 이번 수치를 기존 시스템시장 전망의 상향 조정으로 저장하지 않음.",
        "",
        "■ 실제 수익화·실패 경로",
        "• 칩·HBM·서버·기업용 SSD·통신이 큰 지출처."
        " 전력변환·개폐기·변압기·발전기·냉각도 준공에 필수.",
        "• 계획 MW → 금융종결 → 변전소·송전선 → 전원 인가"
        " → 장비 검수 → 임대·운영 매출; 계획과 인식 매출 구분.",
        "• 역풍: 접속 지연, 발열·냉각 안정성, 소방·보험·고객 승인."
        " 6~24개월 구간에서 전원 인가 MW·신규수주·검수 기간을 조기 확인.",
        "• 초기장비·설계·조달·시공과 장기 유지보수·교체부품·원격관제"
        " 반복매출을 구분하며 BofA 전망을 개별기업 확정 수주로 간주하지 않음.",
        "",
        "■ 환율과 확인 수준",
        f"• 1달러={rate:,.2f}원 · {fx.get('basis','확인 불가')}",
        "• Reuters 10월 23일 보도, TechTimes 10월 26일 기사 교차 확인."
        " BofA 리서치 보고서 원문은 미열람, 증권사 추정의 신뢰보도 단계.",
        "원문: "+BOFA_GLOBAL_REUTERS,
        "원문: "+BOFA_GLOBAL_TECHTIMES,
        "원문: "+BOFA_GLOBAL_SYNDICATED,
    ]
    rendered = "\n".join(lines)+"\n"
    mandatory=("2조1,000억달러","2조9,300억달러","4,900만달러",
               "5,700만달러","3,140만달러","480만달러","78%","22.0%",
               BOFA_GLOBAL_REUTERS,BOFA_GLOBAL_TECHTIMES)
    if any(t not in rendered for t in mandatory):
        raise RuntimeError("BofA 새 알림 숫자·출처 누락")
    if max(map(len,lines))>3000:
        raise RuntimeError("BofA 새 알림 단일 줄 길이 초과")
    return rendered


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def pct(new: float, old: float) -> float:
    return (new / old - 1) * 100 if old else 0.0


def fetch_fx() -> dict:
    from fx_api import daily_krw, historical_krw
    try:
        q = daily_krw()
        quality = "교차검증 일일 기준환율"
    except Exception as exc:
        target = datetime.now(timezone.utc).astimezone(KST).date()
        q = historical_krw("USD", target)
        quality = f"ECB 일일 기준환율 · 보조 검증 실패 대체 ({type(exc).__name__})"
    return {
        "usdkrw": float(q.rate),
        "basis": q.basis,
        "source": q.source,
        "quality": quality,
    }


def krw_from_usd_t(value_t: float, fx: float) -> str:
    won = value_t * 1_000_000_000_000 * fx
    eok = int(round(won / 100_000_000))
    jo, rem = divmod(eok, 10000)
    return f"약 {jo:,}조{rem:,}억원" if rem else f"약 {jo:,}조원"


def krw_from_usd_b(value_b: float, fx: float) -> str:
    won = value_b * 1_000_000_000 * fx
    eok = int(round(won / 100_000_000))
    jo, rem = divmod(eok, 10000)
    return f"약 {jo:,}조{rem:,}억원" if jo and rem else (f"약 {jo:,}조원" if jo else f"약 {eok:,}억원")


def material_changes(old: dict, new: dict) -> list[dict]:
    rules = {
        "ai_dc_system_tam_2030_usd_t": ("2030 AI 데이터센터 시스템 시장", "pct", 5.0),
        "ai_dc_cagr_pct": ("AI 데이터센터 시스템 성장률", "pp", 3.0),
        "server_cpu_tam_2030_usd_b": ("2030 서버 CPU 시장", "pct", 10.0),
        "cloud_capex_2026_usd_t": ("2026 클라우드 설비투자", "pct", 10.0),
        "cloud_capex_2027_usd_t": ("2027 클라우드 설비투자", "pct", 10.0),
        "agentic_cpu_per_gpu": ("에이전틱 AI CPU/GPU 비율", "abs", 0.25),
    }
    out = []
    for key, (label, mode, threshold) in rules.items():
        if key not in old or key not in new:
            continue
        before, after = float(old[key]), float(new[key])
        delta = after - before if mode in {"pp", "abs"} else pct(after, before)
        if abs(delta) >= threshold:
            out.append({"key": key, "label": label, "before": before, "after": after, "delta": delta, "mode": mode})
    return out



def jpm_parse_future_growth(text: str) -> dict:
    """Conservative top-four growth extraction. Excludes 2nd-tier and cash-flow percentages."""
    low = clean(text).lower()
    if not any(t in low for t in ("jpmorgan", "j.p. morgan", "jp morgan")):
        return {}
    if not any(t in low for t in ("data center", "data centre", "cloud dc")):
        return {}
    if not ("capex" in low or "capital expenditure" in low):
        return {}
    if not any(t in low for t in ("top four", "top 4", "four csp", "four hyperscaler")):
        return {}
    out = {}
    for year in (2026, 2027):
        # Anchor to the same year and require an explicit target-rate wording.
        for match in re.finditer(r"\b" + str(year) + r"\b", low):
            tail = low[match.end():match.end()+135]
            tail = re.split(r"\b202[5-9]\b", tail, maxsplit=1)[0]
            surrounding = low[max(0, match.start()-100):match.start()] + tail
            if not any(t in surrounding for t in ("growth", "yoy", "raised", "revised")):
                continue
            if "cash flow" in tail[:75] or "tier 2" in tail[:35]:
                continue
            patterns = (
                r"\b(?:revised|raised|increased|upgraded)\b.{0,50}?\bto\s*\+?(\d{2,3})\s*%",
                r"\b(?:forecast|growth|yoy)\b.{0,50}?\bto\s*\+?(\d{2,3})\s*%",
                r"\b(?:growth|yoy)\s*(?:rate\s*)?(?:of|at|:)?\s*\+?(\d{2,3})\s*%",
                r"\+?(\d{2,3})\s*%\s*(?:growth|yoy)",
            )
            for pattern in patterns:
                mm = re.search(pattern, tail, re.I)
                if mm and 15 <= int(mm.group(1)) <= 120:
                    out[year] = float(mm.group(1))
                    break
            if year in out:
                break
    return out



def jpm_needs_baseline(previous: dict) -> bool:
    """A successful previously committed Telegram delivery suppresses replay."""
    return not bool(previous.get("last_sent_event_id"))


def jpm_networking_needs_alert(previous: dict) -> bool:
    """Only the old, already-delivered capex study can receive this once-only addendum."""
    return (
        previous.get("last_sent_event_id") == JPM_BASELINE_EVENT
        and previous.get("networking_alert_id") != JPM_NETWORKING_EVENT
    )


def jpm_guard() -> None:
    j = JPM_REFERENCE
    assert j["na_installed_2026_gw"] - j["na_installed_2025_gw"] == 28
    assert j["na_installed_2027_gw"] - j["na_installed_2026_gw"] == 43
    # The two percentage figures use different investment universes.
    assert (j["all_provider_capex_2027_b_approx"] /
            j["all_provider_capex_2026_b_approx"] - 1) * 100 == 87.5
    assert j["top4_growth_2027_pct"] == 70
    assert jpm_parse_future_growth(
        "JPMorgan top four CSP data center capex 2027 growth forecast raised from 70% to 80%"
    ) == {2027: 80.0}
    assert jpm_parse_future_growth(
        "JPMorgan tier 2 neocloud data center capex 2027 growth forecast raised to 85%"
    ) == {}
    assert jpm_needs_baseline({}) is True
    assert jpm_needs_baseline({"last_sent_event_id": JPM_BASELINE_EVENT}) is False
    assert jpm_networking_needs_alert({}) is False
    assert jpm_networking_needs_alert({"last_sent_event_id": JPM_BASELINE_EVENT}) is True
    assert jpm_networking_needs_alert({
        "last_sent_event_id": JPM_BASELINE_EVENT,
        "networking_alert_id": JPM_NETWORKING_EVENT,
    }) is False
    assert len(JPM_NETWORKING_TICKERS) == len(set(JPM_NETWORKING_TICKERS)) == 9
    assert "LITE" in JPM_NETWORKING_TICKERS and "CLS" in JPM_NETWORKING_TICKERS



def jpm_watch_revisions(now: datetime, current: dict) -> tuple[dict, list[dict]]:
    """Only corroborated fresh revisions may supersede the saved JPM estimate."""
    cutoff = max(now - timedelta(days=7), datetime(2026, 10, 13, tzinfo=timezone.utc))
    buckets = {}
    seen = set()
    for query in JPM_NEWS_QUERIES:
        try:
            root = ET.fromstring(fetch(gnews_url(query), 16))
        except Exception:
            continue
        for item in root.findall("./channel/item")[:20]:
            source_node = item.find("source")
            source = clean(source_node.text if source_node is not None else "")
            pub = parse_date(clean(item.findtext("pubDate") or ""))
            if pub is None or pub < cutoff or pub > now + timedelta(hours=2):
                continue
            if not trusted_source(source) and "j.p. morgan" not in source.lower():
                continue
            title = clean(item.findtext("title") or "")
            description = clean(item.findtext("description") or "")
            link = clean(item.findtext("link") or "")
            dedup = source.lower() + "|" + title.lower()
            if dedup in seen:
                continue
            seen.add(dedup)
            rates = jpm_parse_future_growth(title + " " + description)
            for year, value in rates.items():
                key = f"top4_growth_{year}_pct"
                if abs(value - float(current.get(key) or 0)) < 5:
                    continue
                buckets.setdefault((key, value), {})[source.lower()] = {
                    "source": source, "title": title, "url": decode_news(link) or link,
                    "published": pub.isoformat(),
                }
    candidates = [(key, value, list(by_source.values()))
                  for (key, value), by_source in buckets.items() if len(by_source) >= 2]
    if not candidates:
        return {}, []
    candidates.sort(key=lambda c: max(z["published"] for z in c[2]), reverse=True)
    key, value, supporting = candidates[0]
    return {key: value}, supporting


def jpm_alert_text(metrics: dict, fx: dict, revised: dict | None,
                   evidence: list[dict]) -> str:
    m = metrics
    rate = float(fx["usdkrw"])
    is_revision = bool(revised)
    title = ("JP모건 데이터센터 설비투자 전망 변경" if is_revision
             else "JP모건 10월 13일 데이터센터 설비투자 전망 감시 기준선 등록")
    text = [
        title, "",
        "■ 상위 4개 CSP 데이터센터 설비투자 증가율(증권사 전망)",
        f"• 2026년 기존 {m['top4_prior_2026_pct']:g}% → {m['top4_growth_2026_pct']:g}%",
        f"• 2027년 기존 {m['top4_prior_2027_pct']:g}% → {m['top4_growth_2027_pct']:g}%",
        f"• 2026년 추가 투자 2,700억달러 이상({krw_from_usd_b(m['top4_increment_2026_b_floor'], rate)} 이상)",
        f"• 2027년 추가 투자 4,000억달러 이상({krw_from_usd_b(m['top4_increment_2027_b_floor'], rate)} 이상)",
        "",
        "■ 북미 데이터센터 전력설비 계획·설치 추정",
        f"• 2026년 2분기 말 계획 {m['na_planned_2026q2_gw_floor']:g}GW 초과: 전원 인가 확정이 아님",
        f"• 설치 2025년 {m['na_installed_2025_gw']:g}GW → 2026년 {m['na_installed_2026_gw']:g}GW"
        f" → 2027년 {m['na_installed_2027_gw']:g}GW (각각 증권사 추정)",
        "• 연간 증가 +28GW(2026년), +43GW(2027년). 실제 가동·송전접속 MW는 별도 검증",
        "",
        "■ 더 넓은 사업자군 전체 금액: 상위 4개 성장률과 분모가 다름",
        f"• 2026년 약 8,000억달러({krw_from_usd_b(m['all_provider_capex_2026_b_approx'], rate)})",
        f"• 2027년 약 1조5,000억달러({krw_from_usd_b(m['all_provider_capex_2027_b_approx'], rate)})",
        "• 위 전체 금액의 단순 증가율은 약 +87.5%이며 상위 4개 사업자 +70%와 혼합 금지",
        "• 전력 계획→계통 계약→인허가→착공→전원 인가→장비 검수→매출 인식 순서 확인",
        "",
        "■ 투자 회수와 자금조달 역풍",
        f"• 상위 4개 사업자의 데이터센터 투자/영업현금흐름: 2026년 {m['top4_dc_capex_ocf_2026_pct']:g}%"
        f" → 2027년 {m['top4_dc_capex_ocf_2027_pct']:g}% (2차 보도 전망)",
        "• 전망치·연구기관별 투자 범위가 달라 직접 합산하거나 확정 수주로 간주하지 않음",
        f"• 검증 수준: {m['source_grade']}",
        f"• 환율: 1달러={rate:,.2f}원, {fx.get('basis','확인 불가')} · {fx.get('source','확인 불가')}",
    ]
    if is_revision:
        text.insert(3, "• 신규 교차검증 변화: " + ", ".join(
            f"{key.split('_')[2]}년 성장률 {value:g}%" for key, value in revised.items()))
        text.append("• 신규 전망은 서로 다른 신뢰보도 2곳 이상 같은 수치일 때만 알림·기준 갱신")
        for row in evidence[:2]:
            if row["url"].startswith("http") and "news.google.com" not in row["url"]:
                text.append("원문: " + row["url"])
    else:
        text.append("• 10월 13일 발표 내용의 신규 감시 등록이며 10월 18일 새 발표 아님")
        for url in JPM_SECONDARY_SOURCES:
            text.append("원문: " + url)
        text.append("원문: " + JPM_FINANCE_OFFICIAL)
    return "\n".join(text) + "\n"



def jpm_networking_alert_text(fx: dict) -> str:
    rate = float(fx["usdkrw"])
    return "\n".join([
        "JP모건 AI 데이터센터 네트워킹 병목·공급사 추가 관점",
        "※ 기존 2026~2027 설비투자 증가율 숫자의 새 발표가 아닙니다.",
        "",
        "■ 무엇이 달라졌나",
        "• 전체 데이터센터 투자 확대의 수혜가 GPU 외에 광연결·스위치·고속 케이블로 확산될 가능성.",
        "• 네트워킹은 GPU 간 데이터 이동 지연·대역폭·전력 손실을 좌우하므로 실제 설치 물량을 확인.",
        "• JP모건의 공급사 긍정적 관점 ≠ 고객별 독점공급·계약·확정매출.",
        "",
        "■ 이번 JP모건 자료에 나온 9개 후보(종목코드)",
        "• 광원·광부품: 루멘텀 LITE, 코히런트 COHR, 파브리넷 FN",
        "• 광섬유·고속 연결: 코닝 GLW, 암페놀 APH, 크레도 CRDO",
        "• 네트워크 스위치·광전송·제조: 아리스타 ANET, 시에나 CIEN, 셀레스티카 CLS",
        "• 공시상 각 기업의 고객 실명·매출비중은 따로 검증. 단순 투자의견은 별도 신규 사건으로 취급하지 않음.",
        "",
        "■ 확인된 사업 연결 — 증권사 추정과 구분",
        f"• 코닝–Meta: 다년 광섬유·케이블 공급계약 최대 60억달러({krw_from_usd_b(6,rate)}). 상한액이지 기인식 매출 아님.",
        f"• 셀레스티카: 2026년 2분기 고성능 플랫폼(HPS) 매출 약 19억달러({krw_from_usd_b(1.9,rate)})."
        " 실제 발생한 사업부 매출로, 전액이 단일 데이터센터 계약은 아님.",
        "• 시에나: WaveLogic 6 Extreme 데이터센터 간 광연결 실제 구축 사례(Vodafone Idea)."
        " 미국 상위 4개 CSP 직접 계약 증빙은 아님.",
        "",
        "■ 이후 신규 알림 조건",
        "• 9개 업체의 실제 신규수주·출하·고객 검증·생산능력·평균판매단가·영업현금흐름 의미 변화",
        "• 숨은 역풍: 광결합 손실·발열·고온 신뢰성·인증시간·수율·소재 병목·고객 투자 지연",
        "• 기존 광통신 감시에 빠진 APH·CIEN·CLS 검색을 추가. 과거 기사 재발송 방지.",
        "",
        f"• 환율: 1달러={rate:,.2f}원 · {fx.get('basis','확인 불가')} · {fx.get('source','확인 불가')}",
        "• JP모건 증권 리포트 원문 직접 미열람. 2차 공개 보도·개별 공식자료 기반.",
        "원문: https://www.macrostream.ai/articles/6ace3ff6f30e248c424121dd",
        "원문: " + JPM_CORNING_META_URL,
        "원문: " + JPM_CELESTICA_Q2_URL,
        "원문: " + JPM_CIENA_VI_URL,
        ""
    ])



def semia_numeric_anchors(text: str) -> list[str]:
    """Extract only explicit GW/leasing figures, never treat GWh as GW."""
    t = clean(text).lower().replace(",", "")
    expected = (
        ("50gw", r"(?<!\w)50\s*(?:gw|gigawatts?)\b"),
        ("60gw", r"(?<!\w)60\s*(?:gw|gigawatts?)\b"),
        ("24gw", r"(?<!\w)24\s*(?:gw|gigawatts?)\b"),
        ("1.3tn_leases", r"(?:\$\s*1\.3\s*(?:trillion|tn|t)\b|"
                          r"1\.3\s*(?:trillion|tn)\s*dollars?)"
                          r".{0,90}(?:lease|leasing|contracts?)"),
    )
    return [key for key, pattern in expected if re.search(pattern, t, re.I | re.S)]



def semia_lease_evidence(text: str) -> dict:
    """Extract mutually inconsistent *publisher* year-to-date lease descriptions.

    No amount may enter confirmed financial totals when at least two versions
    conflict, even if the subtitle says 1.3T. A lease TCV is not construction
    CAPEX or recognized revenue.
    """
    text = clean(text).lower()
    flags = {
        "headline_1_3_t": bool(re.search(
            r"(?:1[.]3\s*(?:t|tn|trillion)).{0,95}(?:lease|contracts?)", text, re.I)),
        "body_under_1_t": bool(re.search(
            r"slightly\s+under\s*(?:usd\s*|\$\s*)?1\s*(?:t\b|tn\b|trillion\b)", text, re.I)),
        "body_over_1_t": bool(re.search(
            r"over\s+a\s+trillion\s*(?:usd|dollars?)?|"
            r"over\s+(?:usd\s*|\$\s*)?1\s*(?:t\b|tn\b|trillion\b)", text, re.I)),
        "term_15_20_years": bool(re.search(r"15\s*[-–—]\s*20\s*(?:year|yr)", text, re.I)),
        "tcv_30_50_b_per_gw": bool(re.search(
            r"(?:\$\s*|usd\s*)?30\s*[-–—]\s*50\s*(?:b\b|bn\b|billion\b)"
            r".{0,35}(?:per|/)\s*gw", text, re.I)),
        "developer_prefund_5_10_pct": bool(re.search(
            r"5\s*[-–—]\s*10\s*%.{0,90}(?:project capital|without a customer)", text, re.I)),
        "dayone_9_months": bool(re.search(
            r"dayone.{0,430}?(?:~|about|around|roughly|approximately)?\s*9\s*months?", text,
            re.I | re.S)),
    }
    flags["body_conflict"] = bool(flags["body_under_1_t"] and flags["body_over_1_t"])
    flags["exact_lease_ytd_usable"] = False
    return flags


def semia_lease_correction_due(old: dict, source: dict, fx: dict, first: bool) -> bool:
    return bool(
        not first and fx.get("usdkrw")
        and old.get("delivered_id") == SEMIA_2027_ID
        and old.get("lease_clarification_id") != SEMIA_LEASE_CORRECTION_ID
        and source.get("verified")
        and source.get("lease_evidence", {}).get("body_conflict")
    )


def semia_lease_correction_alert(source: dict, fx: dict) -> str:
    rate = float(fx["usdkrw"])
    return "\n".join([
        "[수치 보강·정정] SemiAnalysis 2027 데이터센터 임대계약·건설 단계",
        "",
        "■ 앞서 송출된 SemiAnalysis 전망의 임대금액 정밀 검증",
        "• 원문 표제: 올해 누적 임대계약 1조3,000억달러 주장.",
        "• 같은 원문 본문: 구속력 있는 임대계약 '1조달러 약간 미만',"
        " 다른 문단: 체결된 임대계약 '1조달러 초과'로 표현.",
        "• 계약 범위·집계 마감·정의가 일치하는지 설명이 없으므로"
        " 올해 임대계약 확정 총액은 '확인 불가'로 잠급니다.",
        "• 원문 제목의 숫자만으로 2027 신규 GW, 실제 투자·매출액을 역산하지 않습니다.",
        "",
        "■ 앞으로 중요하게 보는 계약 경제성",
        f"• 대형 선임대: 보통 15~20년, 1GW당 총계약가치"
        f" 300억달러({krw_from_usd_b(30,rate)})~"
        f"500억달러({krw_from_usd_b(50,rate)}).",
        "• 단순 계약기간 나눗셈: 연간 1GW당 15억~33억3,333만달러."
        " 계약 총액·실제 입금·건설비·영업매출은 다른 지표.",
        "• 임차인 확정 전 개발사의 선투입 자금은 통상 사업비의 5~10%라는 연구기관 설명."
        " 전력·인허가·완공 보증·대출 조건은 별도 확인.",
        "• 건설 속도: SemiAnalysis의 DayOne 약 9개월 사례."
        " DayOne 공식 자료는 말레이시아 NTP 부지 약 8.5개월 실적."
        " 모든 사업장에 적용 불가.",
        "",
        "■ 실제 사업과의 대조",
        f"• DayOne 공식 발표: 장기 고객계약으로 수익 발생 IT전력 1GW,"
        f" 고객 계약물량 2.3GW, 추가 예약 1.1GW, 금융조달"
        f" 72억달러({krw_from_usd_b(7.2,rate)})."
        " 같은 모집단으로 합산하지 않습니다.",
        "• 2027 신규 용량 50GW, 건설 중 60GW, 후반 공정 24GW는"
        " 전망·전체 공정·그 부분집합을 구분합니다.",
        "",
        f"• 환율: 1달러={rate:,.2f}원 · {fx.get('basis','확인 불가')}",
        "• 향후 알림: 신규 원출처 수치가 실제 일치하고, 새 계약·금융종결·전원 인가 등"
        " 별도 사건이 확인될 때만. 동일 기사 재송출 금지.",
        "원문: " + source["url"],
        "원문: " + SEMIA_DAYONE_SOLUTION_URL,
        "원문: " + SEMIA_DAYONE_2026_FINANCING_URL,
        ""
    ])


def semia_primary_probe(now: datetime) -> dict:
    """Gate publication on an actual SemiAnalysis publisher RSS item and 2 numbers.

    No fallback to third-party articles, Google snippets, user quotation or
    model priors. On source failure, leave the last delivered event unchanged.
    """
    result = {"status": "공식 기사 확인 대기", "publisher_confirmed": False,
              "verified": False, "numeric_anchors": [], "published": "",
              "url": "", "errors": []}
    try:
        root = ET.fromstring(fetch(SEMIA_2027_RSS, 14))
    except Exception as exc:
        result["status"] = "발행처 RSS 조회 실패·원문 확인 대기"
        result["errors"].append(type(exc).__name__)
        return result
    for item in root.findall("./channel/item")[:35]:
        title = clean(item.findtext("title") or "")
        link = (item.findtext("link") or "").strip()
        host = (urllib.parse.urlparse(link).hostname or "").lower()
        if host not in {"newsletter.semianalysis.com", "semianalysis.com"}:
            continue
        low_title = title.lower()
        matched = (
            "datacenters-2027-the-year-of-acceleration" in link.lower()
            or (("datacenters 2027" in low_title or "data centers 2027" in low_title)
                and "acceleration" in low_title)
        )
        if not matched:
            continue
        publication = parse_date(item.findtext("pubDate") or "")
        if publication is None:
            result["status"] = "발행처 기사 제목 확인·게시시각 미확인"
            continue
        if publication > now + timedelta(hours=2):
            result["status"] = "발행처 시각 미래값·검증 보류"
            continue
        if now - publication > timedelta(days=14):
            result["status"] = "과거 기사 재발견·신규 알림 금지"
            continue
        result["publisher_confirmed"] = True
        result["published"] = publication.isoformat()
        result["url"] = link
        content = item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded") or ""
        excerpt = item.findtext("description") or ""
        verified_text = " ".join((title, content, excerpt))
        result["numeric_anchors"] = semia_numeric_anchors(verified_text)
        result["lease_evidence"] = semia_lease_evidence(verified_text)
        if len(result["numeric_anchors"]) >= 2:
            result["verified"] = True
            result["status"] = "발행처 RSS·핵심 숫자 2개 이상 직접 확인"
        else:
            result["status"] = "발행처 기사 확인·핵심 수치 본문 접근 제한"
        return result
    return result


def semia_alert_due(old: dict, source: dict, fx: dict, first: bool) -> bool:
    return (
        not first
        and bool(fx.get("usdkrw"))
        and bool(source.get("verified"))
        and len(source.get("numeric_anchors") or []) >= 2
        and old.get("delivered_id") != SEMIA_2027_ID
    )


def semia_regression_checks() -> None:
    # Two MW/GW concepts and all-in capex use DIFFERENT quantities.
    t = "50GW capacity additions; 60 GW under construction; 24 gigawatts late stage."
    assert semia_numeric_anchors(t) == ["50gw", "60gw", "24gw"]
    assert semia_numeric_anchors("50GWh batteries 60MWh storage") == []
    assert SEMIA_2027_USER_EXCERPT["advanced_2027_construction_gw_floor"] <= SEMIA_2027_USER_EXCERPT["under_construction_gw"]
    assert SEMIA_2027_USER_EXCERPT["2027_new_capacity_headline_gw"] * SEMIA_2027_USER_EXCERPT["hypothetical_cost_per_gw_usd_b"] == 2500
    assert SEMIA_2027_USER_EXCERPT["comparator_2027_capex_usd_t"] * 1000 != 2500
    valid = {"verified": True, "numeric_anchors": ["50gw", "60gw"]}
    fx = {"usdkrw": 1300}
    assert semia_alert_due({}, valid, fx, False)
    assert not semia_alert_due({"delivered_id": SEMIA_2027_ID}, valid, fx, False)
    assert not semia_alert_due({}, {"verified": False, "numeric_anchors": []}, fx, False)
    assert not semia_alert_due({}, {"verified": True, "numeric_anchors": ["50gw"]}, fx, False)
    assert not semia_alert_due({}, valid, fx, True)
    assert not semia_alert_due({}, valid, {}, False)
    assert semia_numeric_anchors("60 GWh battery + 24 MWh ESS") == []
    assert SEMIA_2027_USER_EXCERPT["advanced_campuses"] == 40
    assert (SEMIA_2027_USER_EXCERPT["advanced_2027_construction_gw_floor"] /
            SEMIA_2027_USER_EXCERPT["under_construction_gw"]) == 0.4
    example = ("Year-to-date, slightly under USD 1T of binding / non-cancellable"
               " datacenter leases have been signed. Just in 2026 year-to-date,"
               " we've identified over a trillion USD of lease value signed and closed."
               " 15-20 year contract, with a TCV of $30-50B per GW."
               " Developers spend 5-10% of project capital without a customer.")
    proof = semia_lease_evidence(example)
    assert proof["body_conflict"] and not proof["exact_lease_ytd_usable"]
    assert proof["term_15_20_years"]
    assert proof["tcv_30_50_b_per_gw"]
    assert proof["developer_prefund_5_10_pct"]
    assert not semia_lease_evidence("We signed $1.3T of leases")["body_conflict"]
    assert not semia_lease_evidence("We leased 60GWh storage at 15-20 years")["body_conflict"]
    correction_source = {"verified": True, "lease_evidence": proof}
    acknowledged = {"delivered_id": SEMIA_2027_ID}
    assert semia_lease_correction_due(acknowledged, correction_source, fx, False)
    assert not semia_lease_correction_due(
        {**acknowledged, "lease_clarification_id": SEMIA_LEASE_CORRECTION_ID},
        correction_source, fx, False)
    assert not semia_lease_correction_due(acknowledged, {"verified": False,
        "lease_evidence": proof}, fx, False)
    assert not semia_lease_correction_due(acknowledged, correction_source, {}, False)


def semia_verified_alert_text(source: dict, fx: dict) -> str:
    """Primary publisher verified some headline numbers; others remain user excerpt."""
    b = SEMIA_2027_USER_EXCERPT
    rate = float(fx["usdkrw"])
    checked = ", ".join(source["numeric_anchors"])
    total_usd_b = b["2027_new_capacity_headline_gw"] * b["hypothetical_cost_per_gw_usd_b"]
    return "\n".join([
        "SemiAnalysis 2027 데이터센터 건설 가속 전망 — 발행처 확인",
        "",
        "■ 발행처와 숫자 검증 범위",
        f"• 발행처 RSS 확인: {source['published']} · 직접 확인한 수치표현: {checked}",
        "• 나머지 세부 숫자는 사용자 제공 발췌. 유료 원자료·개별 현장 명단 전체는 미열람.",
        f"• 헤드라인 신규 용량 약 {b['2027_new_capacity_headline_gw']}GW(주장),"
        f" 건설 중 {b['under_construction_gw']}GW(주장),"
        f" 후반 공정 {b['advanced_2027_construction_gw_floor']}GW 이상(주장).",
        "• 건설 후반 24GW는 건설 중 60GW의 부분집합. 더하거나 완공·전원 인가로 간주하지 않음.",
        "• 동일 용량의 지역(미국/북미/세계), 전력 기준(IT/총전력), 집계일이"
        " 완전히 대조되기 전에는 Epoch·JP모건·Goldman GW와 합산하지 않음.",
        "",
        "■ 투자액·임대계약 구분",
        f"• 1GW당 500억달러({krw_from_usd_b(50, rate)}) 시나리오"
        f" × 50GW = 2조5,000억달러({krw_from_usd_b(total_usd_b, rate)}).",
        "• 이는 총 구축비 감도분석이지 2027년 한 해의 실제 설비투자·신규 발주액이 아님.",
        f"• 연초 이후 임대계약 1조3,000억달러({krw_from_usd_b(1300, rate)}) 주장:"
        " 기간별 미래 지급의무이며 즉시 매출·현금 지급과 구분.",
        f"• 별도 2027년 투자전망 약 1조5,000억달러({krw_from_usd_b(1500, rate)})와"
        " 집계범위·현금 집행연도가 달라 단순 차감·동일시 금지.",
        "",
        "■ 건설과 반도체 병목을 별도로 확인",
        "• 사업별 계약·부지 → 실제 착공 → 후반 전기·냉각 공사 → 전원 인가 → 서버 반입·검수 순으로 추적.",
        "• 2027~2028년 HBM·DRAM·첨단 로직·CoWoS 수율과 공급량이 추가 병목으로"
        " 이동할 수 있음. 메모리·로직 양산 물량과 건설 GW를 나란히 감시.",
        "• 위험: 계약 취소·대출비용·전력접속 지연, 변압기 납기, 현장 인력, 냉각 인수시험, HBM 휨·검사시간.",
        "",
        "■ 근거·환율",
        f"• 1달러={rate:,.2f}원 · {fx.get('basis','확인 불가')} · {fx.get('source','확인 불가')}",
        "• SemiAnalysis 자체 예측이며 공식 완공실적·구속력 있는 모든 계약의 전수 확인은 아님.",
        "원문: " + source["url"],
        "원문: https://newsletter.semianalysis.com/p/to-boldly-go-the-case-for-space-datacenters",
        ""
    ])


def fmt(key: str, value: float, fx: float | None = None) -> str:
    if key.endswith("_usd_t"):
        base = f"{value:.2f}조달러"
        return f"{base} ({krw_from_usd_t(value, fx)})" if fx else base
    if key.endswith("_usd_b"):
        base = f"{value:,.1f}억달러" if value < 100 else f"{value:,.0f}억달러"
        return f"{base} ({krw_from_usd_b(value, fx)})" if fx else base
    if key.endswith("_pct"):
        return f"{value:.1f}%"
    if "cpu_per_gpu" in key:
        return f"GPU 1개당 CPU {value:.2f}개"
    return f"{value:g}"


def build_alert(metrics: dict, changes: list[dict], evidence: list[dict], fx: dict) -> str:
    rate = float(fx["usdkrw"])
    lines = [
        "🚨 AI 데이터센터 시장규모·클라우드 설비투자 전망 변경",
        "",
        "▶ 핵심",
    ]
    for ch in changes[:6]:
        unit = "%p" if ch["mode"] == "pp" else ("개" if ch["mode"] == "abs" else "%")
        lines.append(f"• {ch['label']}: {fmt(ch['key'], ch['before'], rate)} → {fmt(ch['key'], ch['after'], rate)} ({ch['delta']:+.1f}{unit})")

    lines += [
        "",
        "■ 현재 기준",
        f"• 2030 AI 데이터센터 시스템 시장: {fmt('ai_dc_system_tam_2030_usd_t', metrics['ai_dc_system_tam_2030_usd_t'], rate)}",
        f"• 2030 서버 CPU 시장: {fmt('server_cpu_tam_2030_usd_b', metrics['server_cpu_tam_2030_usd_b'], rate)}",
        f"• 2026 클라우드 설비투자: {fmt('cloud_capex_2026_usd_t', metrics['cloud_capex_2026_usd_t'], rate)}",
        f"• 2027 클라우드 설비투자: {fmt('cloud_capex_2027_usd_t', metrics['cloud_capex_2027_usd_t'], rate)}",
        f"• 에이전틱 AI: GPU 1개당 CPU {metrics['agentic_cpu_per_gpu']:.2f}개 기준",
        "",
        "■ 의미",
        "• 이 알림은 데이터센터 건설 GW가 아니라 GPU·CPU·메모리·네트워크에 실제로 들어갈 시스템 지출 전망이 상향·하향되는지를 추적합니다.",
        "• 전력 병목 감시와 분리해 수요 측 전망 자체가 꺾이는지 먼저 확인합니다.",
        "• BofA 리포트 원문이 공개되지 않는 경우 신뢰 보도에 나온 수치를 증권사 추정으로만 표시합니다.",
        "",
        "■ 원화 환산 기준",
        f"• 1달러 = {rate:,.2f}원",
        f"• 기준: {fx.get('basis','확인 불가')}",
        f"• 출처: {fx.get('source','확인 불가')} · {fx.get('quality','')}",
    ]
    if evidence:
        source_ko = {
            "Yahoo Finance": "야후 파이낸스",
            "Investing.com": "인베스팅닷컴",
            "Finvaulta": "핀볼타",
            "StreetSignal": "스트리트시그널",
            "Reuters": "로이터",
            "Bloomberg": "블룸버그",
            "CNBC": "CNBC",
            "Financial Times": "파이낸셜타임스",
            "Barron's": "배런스",
            "MarketWatch": "마켓워치",
        }
        lines += ["", "■ 확인 자료"]
        for row in evidence[:4]:
            lines.append(f"• {source_ko.get(row['source'], '신뢰 자료')}: 전망 변경 근거 확인")
            if row.get("url"):
                lines.append(f"원문: {row['url']}")
    return "\n".join(lines) + "\n"


def main() -> int:
    OUT.mkdir(exist_ok=True)
    for p in (ALERT, PENDING, STATUS):
        p.unlink(missing_ok=True)

    now = datetime.now(timezone.utc)
    jpm_guard()
    semia_regression_checks()
    bofa_global_checks()
    old = load_state()
    first = not bool(old)
    old_bofa_global = dict(old.get('bofa_global_spending') or {})
    baseline_metrics = {k: v for k, v in BASELINE.items() if k not in {"source", "as_of"}}
    metrics = dict(old.get("metrics") or baseline_metrics)
    for k, v in baseline_metrics.items():
        metrics.setdefault(k, v)
    reference_metrics = dict(old.get("reference_metrics") or baseline_metrics)
    for k, v in baseline_metrics.items():
        reference_metrics.setdefault(k, v)

    try:
        fx = fetch_fx()
    except Exception as exc:
        fx = {}
        print(f"ai_dc_tam_fx_error={type(exc).__name__}: {exc}")

    bofa_new_due = bofa_global_due(old_bofa_global, fx, first)
    bofa_global_next = dict(old_bofa_global)
    bofa_global_next["reference"] = BOFA_GLOBAL_REFERENCE
    if bofa_new_due:
        bofa_global_next["delivered_id"] = BOFA_GLOBAL_ID
        bofa_global_next["delivered_at_kst"] = now.astimezone(KST).isoformat(timespec="seconds")
    rows = collect(now)
    seen_ordered = list(old.get("seen_ids") or [])
    seen = set(seen_ordered)
    new_rows = [r for r in rows if r["id"] not in seen]

    # 본문 접근이 일시 실패해도 다음 실행에서 다시 숫자를 추출할 수 있도록
    # 신규 기사뿐 아니라 현재 조회 가능한 신뢰자료 전체를 매번 재검증한다.
    candidates = []
    for row in rows:
        parsed = extract_metrics(row["text"])
        if parsed:
            candidates.append((row, parsed))

    proposed = dict(metrics)
    evidence = []
    # 동일 숫자가 서로 다른 신뢰자료 2곳 이상에서 확인될 때만 기준을 갱신한다.
    # 과거 정적 기준과 새 전망이 동수면 게시시각이 더 최근인 전망을 우선한다.
    keys = set()
    for _, parsed in candidates:
        keys.update(parsed)

    def published_score(row: dict) -> float:
        raw = str(row.get("published_at") or "")
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
        except Exception:
            return 0.0

    for key in keys:
        buckets = {}
        for row, parsed in candidates:
            if key not in parsed:
                continue
            v = round(float(parsed[key]), 4)
            buckets.setdefault(v, []).append(row)
        qualified = [(value, support) for value, support in buckets.items()
                     if len({str(row.get("source") or "").strip().lower() for row in support}) >= 2]
        if not qualified:
            continue
        value, support = max(
            qualified,
            key=lambda item: (max((published_score(r) for r in item[1]), default=0.0), len(item[1])),
        )
        proposed[key] = value
        evidence.extend(support)

    changes = material_changes(reference_metrics, proposed)
    notify = bool(changes)
    # A blocked message must not acknowledge or consume its new baseline.
    can_deliver = not first and bool(fx.get("usdkrw"))
    next_reference = dict(proposed) if notify and can_deliver else dict(reference_metrics)

    jpm_old = dict(old.get("jpm_capex") or {})
    jpm_metrics = dict(jpm_old.get("metrics") or JPM_REFERENCE)
    for key, val in JPM_REFERENCE.items():
        jpm_metrics.setdefault(key, val)
    jpm_initial = jpm_needs_baseline(jpm_old)
    jpm_revision, jpm_support = ({}, []) if jpm_initial else jpm_watch_revisions(now, jpm_metrics)
    jpm_event_id = (JPM_BASELINE_EVENT if jpm_initial else
                    hashlib.sha256(json.dumps(jpm_revision, sort_keys=True).encode("utf-8")).hexdigest()[:24]
                    if jpm_revision else "")
    jpm_alert = bool(jpm_event_id) and can_deliver
    # Separate, one-time networking *analysis* addendum to the already delivered
    # capex event. Do not re-send JPM_REFERENCE 85%/70% as fresh news.
    jpm_networking_due = jpm_networking_needs_alert(jpm_old)
    jpm_networking_alert = jpm_networking_due and can_deliver
    jpm_next = dict(jpm_old)
    if jpm_networking_alert:
        jpm_next["networking_alert_id"] = JPM_NETWORKING_EVENT
        jpm_next["networking_alert_at_kst"] = now.astimezone(KST).isoformat(timespec="seconds")
    if jpm_alert:
        jpm_metrics.update(jpm_revision)
        jpm_next["metrics"] = jpm_metrics
        jpm_next["last_sent_event_id"] = jpm_event_id
        jpm_next["last_sent_at_kst"] = now.astimezone(KST).isoformat(timespec="seconds")
    else:
        jpm_next.setdefault("metrics", jpm_metrics)

    semi_old = dict(old.get("semianalysis_2027") or {})
    semi_live = semia_primary_probe(now)
    semi_notify = semia_alert_due(semi_old, semi_live, fx, first)
    semi_lease_correction = semia_lease_correction_due(semi_old, semi_live, fx, first)
    semi_next = dict(semi_old)
    # Only source-confirmed definitions, never assign a conflicting aggregate as a fact.
    semi_next["lease_contract_terms"] = {
        "typical_contract_years": [15, 20],
        "tcv_usd_b_per_gw": [30, 50],
        "developer_prefund_percent": [5, 10],
        "modular_build_months_example": 9,
        "dayone_official_ntp_build_months": 8.5,
        "contract_total_usd_t_confirmed": None,
        "lease_ytd_source_conflict": "표제 1.3조달러·본문 1조달러 미만·다른 본문 1조달러 초과",
        "contract_tcv_not_annual_capex": True,
        "source_grade": "SemiAnalysis 발행처 + DayOne 회사 발표; 금융 현금집행 별도 검증",
    }
    semi_next["lease_evidence"] = semi_live.get("lease_evidence") or {}
    if semi_lease_correction:
        semi_next["lease_clarification_id"] = SEMIA_LEASE_CORRECTION_ID
        semi_next["lease_clarification_at_kst"] = now.astimezone(KST).isoformat(timespec="seconds")
    semi_next["user_excerpt"] = SEMIA_2027_USER_EXCERPT
    semi_next["primary_status"] = semi_live["status"]
    semi_next["primary_numeric_anchors"] = semi_live["numeric_anchors"]
    semi_next["last_primary_checked_kst"] = now.astimezone(KST).isoformat(timespec="seconds")
    semi_next["primary_errors"] = semi_live.get("errors") or []
    if semi_live.get("publisher_confirmed"):
        semi_next["publisher_release"] = semi_live["published"]
        semi_next["publisher_article_url"] = semi_live["url"]
    if semi_notify:
        semi_next["delivered_id"] = SEMIA_2027_ID
        semi_next["delivered_at_kst"] = now.astimezone(KST).isoformat(timespec="seconds")

    pending = {
        "initialized": True,
        "metrics": proposed,
        "reference_metrics": next_reference,
        "baseline_source": BASELINE["source"],
        "updated_at_kst": now.astimezone(KST).isoformat(timespec="seconds"),
        "seen_ids": list(dict.fromkeys(seen_ordered + [r["id"] for r in rows]))[-1000:],
        "jpm_capex": jpm_next,
        "bofa_global_spending": bofa_global_next,
        "semianalysis_2027": semi_next,
        "fx": fx,
        "last_collection": {
            "trusted_rows": len(rows),
            "new_rows": len(new_rows),
            "candidate_metric_rows": len(candidates),
            "material_changes": len(changes),
        },
    }
    PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    alerts = []
    if notify and not first:
        if not can_deliver:
            print("ai_dc_tam_alert_blocked_no_krw=true")
        else:
            alerts.append(build_alert(proposed, changes, list({r["id"]: r for r in evidence}.values()), fx))
    if jpm_alert:
        alerts.append(jpm_alert_text(jpm_metrics, fx, jpm_revision, jpm_support))
    if jpm_networking_alert:
        alerts.append(jpm_networking_alert_text(fx))
    if semi_notify:
        alerts.append(semia_verified_alert_text(semi_live, fx))
    if semi_lease_correction:
        alerts.append(semia_lease_correction_alert(semi_live, fx))
    if bofa_new_due:
        alerts.append(bofa_global_alert(fx))
    if alerts:
        ALERT.write_text("\n\n".join(alerts), encoding="utf-8")

    STATUS.write_text(
        "# AI 데이터센터 TAM·설비투자 전망 감시\n\n"
        f"- 최초 기준선: **{'예' if first else '아니오'}**\n"
        f"- 신뢰자료 수집: **{len(rows)}건**\n"
        f"- 신규 자료: **{len(new_rows)}건**\n"
        f"- BofA 글로벌 투자액·단위 구축비 별도 1회 알림: **{'예' if bofa_new_due else '중복 제외'}**\n"
        f"- 숫자 후보: **{len(candidates)}건**\n"
        f"- 중요 전망 변경: **{len(changes)}건**\n"
        f"- JP모건 현재 성장률 2026/2027: **{jpm_metrics['top4_growth_2026_pct']:g}% / {jpm_metrics['top4_growth_2027_pct']:g}%**\n"
        f"- JP모건 기준·전망 알림: **{'예' if jpm_alert else '아니오'}**\n"
        f"- JP모건 네트워킹 별도 관점: **{'예' if jpm_networking_alert else '아니오'}**\n"
        f"- SemiAnalysis 2027 원천 상태: **{semi_live['status']}**\n"
        f"- SemiAnalysis 핵심 수치 확인: **{len(semi_live['numeric_anchors'])}개**\n"
        f"- SemiAnalysis 신규 알림: **{'예' if semi_notify else '아니오'}**\n"
        f"- SemiAnalysis 임대계약 원문 충돌 확인: **{'예' if semi_live.get('lease_evidence', {}).get('body_conflict') else '아니오·재검증 필요'}**\n"
        f"- SemiAnalysis 임대금액 1회 정정: **{'예' if semi_lease_correction else '아니오'}**\n"
        f"- 알림: **{'예' if alerts else '아니오'}**\n",
        encoding="utf-8",
    )
    print(f"ai_dc_tam_watch first={first} rows={len(rows)} candidates={len(candidates)} changes={len(changes)} jpm_initial={jpm_initial} jpm_changes={len(jpm_revision)} jpm_alert={jpm_alert} jpm_net_alert={jpm_networking_alert} semia_source={semi_live['status']} semia_anchors={len(semi_live['numeric_anchors'])} semia_alert={semi_notify} semi_lease_conflict={semi_live.get('lease_evidence', {}).get('body_conflict')} semi_lease_correction={semi_lease_correction} alert={bool(alerts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
