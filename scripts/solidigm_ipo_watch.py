from __future__ import annotations

import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

try:
    from googlenewsdecoder import gnewsdecoder
except Exception:
    gnewsdecoder = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "solidigm_ipo_watch_state.json"
ALERT = ROOT / "out" / "solidigm_ipo_alert.html"
UA = "Mozilla/5.0 (compatible; khs-watch/2.0; +https://github.com/qedgwangju-dot/khs-watch)"
WATCH_VERSION = 4
IPO_ALERT_FORMAT_VERSION = 2
CANONICAL_REUTERS_URL = "https://www.reuters.com/world/sk-hynixs-solidigm-weighs-ipo-that-could-value-the-unit-up-150-billion-sources-2026-09-25/"
SOLIDIGM_DMS_URL = "https://www.solidigm.com/products/document-management-system.html"
OFFICIAL_SK_REPLY = "https://news.skhynix.com/en/fact-11/"
REPORT_YONHAP_URL = "https://www.yna.co.kr/view/AKR20261008022500009"
REPORT_EDAILY_URL = "https://www.edaily.co.kr/News/Read?mediaCodeNo=257&newsId=02407526645610952"
REPORT_INVESTING_URL = "https://www.investing.com/news/stock-market-news/solidigm-selects-lead-banks-for-blockbuster-us-ipo-bloomberg-reports-4937618"
BLOOMBERG_BANK_EVENT_KST = "2026-10-08T07:48:01+09:00"
MANUFACTURING_BASELINE = {
    "stage": "pcn_announced",
    "pcn_number": "0000048112-00",
    "pcn_publish_date": "2026-09-25",
    "pcn_change_title": "Additional Manufacturing Site for all Solidigm Datacenter SSDs",
    "official_pcn_verified": True,
    "affected_scope": "all_solidigm_datacenter_ssds",
    "manufacturing_scope": "ssd_manufacturing_not_nand_wafer_fab",
    "reported_site_country": "Taiwan",
    "reported_manufacturing_model": "ODM",
    "reported_ship_start_month": "2026-12",
    "reported_quality_standard_unchanged": True,
    "quality_issue_status": "not_reported",
    "customer_qualification_stage": "not_reported",
    "reported_existing_odm_partners": ["PTI", "Pegatron"],
    "pti_partnership_officially_supported": True,
    "pegatron_partnership_evidence": "reported",
    "confirmed_direct_server_customers": [],
    "capacity_units_per_month": None,
    "capacity_eb_per_year": None,
    "official_source_url": SOLIDIGM_DMS_URL,
    "reported_source_url": "https://www.ajunews.com/view/20261005160404868",
    "secondary_reported_source_url": "https://en.sedaily.com/finance/2026/10/05/solidigm-to-expand-ssd-production-sites-in-taiwan",
    "pti_official_source_url": "https://www.pti.com.tw/Handlers/ConferenceDownload.ashx?col=briefing&id=1ddf8d0a-0ca9-4271-ad0e-71812b1beadb&lang=en",
    "as_of": "2026-10-05",
    "note": "Solidigm 공식 DMS는 PCN 0000048112-00과 'all Solidigm Datacenter SSDs' 대상 추가 제조거점을 확인. 대만·ODM·12월 출하·Pegatron은 아주경제/서울경제 보도 단계. PTI는 과거 PTI 공식 IR에서 Solidigm 파트너 관계가 확인됨. 신규 거점의 생산능력 수치는 미공개이며 NAND 웨이퍼 팹 증설로 해석하지 않음.",
}

MANUFACTURING_QUERIES = [
    '"Solidigm" "Additional Manufacturing Site" SSD',
    '"Solidigm" Taiwan ODM SSD',
    '"Solidigm" manufacturing site datacenter SSD',
    '"Solidigm" PCN datacenter SSD manufacturing',
    '"솔리다임" 대만 SSD 위탁생산',
    '"솔리다임" SSD 생산거점',
]

QUERIES = [
    '"Solidigm" IPO',
    '"Solidigm" Reuters IPO',
    '"Solidigm" underwriters IPO',
    '"Solidigm" Goldman Sachs Morgan Stanley IPO',
    '"솔리다임" IPO 주관사 골드만삭스 모건스탠리',
    '"솔리다임" "주관사 선정" 블룸버그',
    '"Solidigm" "confidential filing" IPO',
    '"Solidigm" "S-1" IPO',
    '"Solidigm" valuation IPO SK hynix',
    '"Solidigm" pre-IPO SK hynix',
    'site:news.skhynix.com Solidigm IPO',
    'site:solidigm.com Solidigm IPO',
]

TRUSTED = (
    "reuters", "bloomberg", "financial times", "ft.com", "wall street journal", "wsj",
    "cnbc", "business times", "korea times", "investing.com", "seoul economic",
    "서울경제", "seoul economic", "아주경제", "ajunews", "sk hynix", "sk하이닉스", "solidigm", "sec",
    "powertech", "pti", "연합뉴스", "yonhap", "yna.co.kr", "이데일리", "edaily",
)

EVIDENCE_RANK = {"reported": 1, "top_tier_report": 2, "official": 3}

STAGE_RANK = {
    "exploring": 1,
    "bank_bakeoff": 2,
    "underwriters_selected": 3,
    "confidential_filing": 4,
    "public_filing": 5,
    "roadshow": 6,
    "price_range": 7,
    "priced": 8,
    "listed": 9,
}
STAGE_KO = {
    "exploring": "상장 검토",
    "bank_bakeoff": "주관사 선정 경쟁(피치 미팅)",
    "underwriters_selected": "대표주관사·주관단 선정",
    "confidential_filing": "SEC 비공개 예비서류 제출",
    "public_filing": "SEC 공개 상장신고서 제출",
    "roadshow": "수요예측·로드쇼",
    "price_range": "공모가 밴드 제시",
    "priced": "공모가 확정",
    "listed": "상장·거래 개시",
    "postponed": "상장 연기",
    "withdrawn": "상장 철회",
}

def now_kst():
    return datetime.now(ZoneInfo("Asia/Seoul"))

def clean(value):
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def parse_pub(value):
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo("Asia/Seoul"))
    except Exception:
        return None

def rss_url(q, lang):
    enc = urllib.parse.quote(q)
    if lang == "ko":
        return f"https://news.google.com/rss/search?q={enc}&hl=ko&gl=KR&ceid=KR:ko"
    return f"https://news.google.com/rss/search?q={enc}&hl=en-US&gl=US&ceid=US:en"

def decode_google(url):
    if "news.google.com" not in (url or ""):
        return url
    if gnewsdecoder is None:
        return ""
    try:
        result = gnewsdecoder(url, interval=0.2)
        if isinstance(result, dict) and result.get("status"):
            direct = str(result.get("decoded_url") or "").strip()
            if direct.startswith("http") and "news.google.com" not in direct:
                return direct
    except Exception:
        pass
    return ""

def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"watch_version": WATCH_VERSION, "current_state": {}, "seen_urls": []}

def save_state(obj):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def source_rank(source, url):
    text = ((source or "") + " " + (url or "")).lower()
    if "sec.gov" in text or "solidigm.com" in text or "skhynix.com" in text or "sk hynix" in text or "sk하이닉스" in text:
        return 100
    if "reuters" in text or "bloomberg" in text:
        return 95
    if "ft.com" in text or "financial times" in text or "wsj" in text:
        return 90
    if "cnbc" in text or "business times" in text or "korea times" in text:
        return 80
    if "investing.com" in text or "seoul economic" in text or "서울경제" in text:
        return 70
    return 20

def evidence_state(source, url):
    text = ((source or "") + " " + (url or "")).lower()
    if "sec.gov" in text or "solidigm.com" in text or "skhynix.com" in text or "sk hynix" in text or "sk하이닉스" in text:
        return "official"
    if "reuters" in text or "bloomberg" in text:
        return "top_tier_report"
    return "reported"

def read_events():
    rows = {}
    for q in QUERIES:
        for lang in ("en", "ko"):
            try:
                root = ET.fromstring(fetch(rss_url(q, lang)))
            except Exception:
                continue
            for item in root.findall("./channel/item"):
                title = clean(item.findtext("title") or "")
                desc = clean(item.findtext("description") or "")
                link = clean(item.findtext("link") or "")
                source_node = item.find("source")
                source = clean(source_node.text if source_node is not None and source_node.text else "")
                pub = parse_pub(clean(item.findtext("pubDate") or ""))
                text = (title + " " + desc).lower()
                if "solidigm" not in text and "솔리다임" not in text:
                    continue
                if not any(k in text for k in ("ipo", "initial public offering", "상장", "공모", "pre-ipo", "underwriter", "주관사", "s-1", "sec")):
                    continue
                direct = decode_google(link)
                if not direct:
                    continue
                source_host = urllib.parse.urlparse(direct).hostname or ""
                trust_text = (source + " " + source_host).lower()
                if not any(x in trust_text for x in TRUSTED):
                    continue
                key = hashlib.sha256((title + "|" + source).encode()).hexdigest()[:24]
                rows[key] = {
                    "id": key, "title": title, "description": desc, "source": source or "출처 미표시",
                    "published_at_kst": pub.isoformat(timespec="seconds") if pub else "",
                    "direct_link": direct, "rank": source_rank(source, direct),
                }
    # User-supplied Yonhap story was independently checked against the dated
    # EDaily article and an Investing.com Bloomberg republication. They all
    # repeat ONE original Bloomberg report, not multiple original sources.
    # This one-time explicit event expires after ten days; the existing state
    # transition deduplicator prevents repeat Telegram deliveries.
    event = {
        "id": "solidigm_bloomberg_banks_20261008",
        "title": "Bloomberg: Solidigm selected Goldman Sachs and Morgan Stanley to lead IPO",
        "description": (
            "Solidigm selected Goldman Sachs and Morgan Stanley as lead underwriters "
            "for its potential US IPO. JPMorgan Chase, Citigroup and UBS join the syndicate. "
            "The IPO could raise $10 billion and value Solidigm at up to $100 billion. "
            "It could happen as soon as 2027. Pre-IPO financing being considered, "
            "its precise amount unconfirmed; no company IPO decision confirmed."
        ),
        "source": "Bloomberg 보도(이데일리·연합뉴스·Investing.com 재인용)",
        "published_at_kst": BLOOMBERG_BANK_EVENT_KST,
        "direct_link": REPORT_EDAILY_URL,
        "origin_republication": REPORT_YONHAP_URL,
        "crosscheck_republication": REPORT_INVESTING_URL,
        "rank": 96,
        "is_curated_reported_milestone": True,
    }
    if now_kst().date().isoformat() >= "2026-10-08" and now_kst().date().isoformat() <= "2026-10-18":
        rows[event["id"]] = event
    return sorted(rows.values(), key=lambda x: (x.get("published_at_kst") or "", x.get("rank", 0)))


def read_manufacturing_events():
    rows = {}
    for q in MANUFACTURING_QUERIES:
        for lang in ("en", "ko"):
            try:
                root = ET.fromstring(fetch(rss_url(q, lang)))
            except Exception:
                continue
            for item in root.findall("./channel/item"):
                title = clean(item.findtext("title") or "")
                desc = clean(item.findtext("description") or "")
                link = clean(item.findtext("link") or "")
                source_node = item.find("source")
                source = clean(source_node.text if source_node is not None and source_node.text else "")
                pub = parse_pub(clean(item.findtext("pubDate") or ""))
                low = (title + " " + desc).lower()
                if "solidigm" not in low and "솔리다임" not in low:
                    continue
                if not any(k in low for k in (
                    "manufacturing", "factory", "production site", "odm", "pcn",
                    "생산거점", "제조거점", "위탁생산", "생산 기반", "공장",
                )):
                    continue
                if not any(k in low for k in ("ssd", "datacenter", "data center", "데이터센터", "기업용")):
                    continue
                direct = decode_google(link)
                if not direct:
                    continue
                source_host = urllib.parse.urlparse(direct).hostname or ""
                trust_text = (source + " " + source_host).lower()
                if not any(x in trust_text for x in TRUSTED):
                    continue
                key = hashlib.sha256(("manufacturing|" + title + "|" + source).encode()).hexdigest()[:24]
                rows[key] = {
                    "id": key, "title": title, "description": desc, "source": source or "출처 미표시",
                    "published_at_kst": pub.isoformat(timespec="seconds") if pub else "",
                    "direct_link": direct, "rank": source_rank(source, direct),
                }
    return sorted(rows.values(), key=lambda x: (x.get("published_at_kst") or "", x.get("rank", 0)))


def article_text(event):
    url = event.get("direct_link") or ""
    try:
        raw = fetch(url, timeout=16).decode("utf-8", errors="ignore")
        return clean(raw)[:40000]
    except Exception:
        return ""

def usd_amount(text, context_pattern):
    patterns = [
        context_pattern + r"[^$]{0,100}?(?:US\$|\$)\s*([\d.]+)\s*(billion|million|B|M)\b",
        r"(?:US\$|\$)\s*([\d.]+)\s*(billion|million|B|M)\b[^.]{0,120}?" + context_pattern,
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            n = float(m[1])
            return n * (1_000_000_000 if m[2].lower() in ("billion", "b") else 1_000_000)
    return None

def stage_from_text(text):
    low = text.lower()
    solidigm_ipo_context = (
        r"(?:Solidigm[^.]{0,180}?(?:IPO|initial public offering|listing|상장)|"
        r"(?:IPO|initial public offering|listing|상장)[^.]{0,180}?Solidigm)"
    )
    if re.search(solidigm_ipo_context + r"[^.]{0,120}?(?:withdrawn|withdraws|cancelled|canceled|철회|취소)", text, re.I) or re.search(r"(?:withdrawn|withdraws|cancelled|canceled|철회|취소)[^.]{0,120}?" + solidigm_ipo_context, text, re.I):
        return "withdrawn"
    if re.search(solidigm_ipo_context + r"[^.]{0,120}?(?:postponed|delayed|연기|미뤘)", text, re.I) or re.search(r"(?:postponed|delayed|연기|미뤘)[^.]{0,120}?" + solidigm_ipo_context, text, re.I):
        return "postponed"
    if re.search(r"began trading|begins trading|listed on|상장\s*(?:완료|첫날|거래)", text, re.I):
        return "listed"
    if re.search(r"priced (?:its|the) ipo|ipo price|공모가\s*확정", text, re.I):
        return "priced"
    if re.search(r"price range|pricing range|공모가\s*(?:밴드|범위)", text, re.I):
        return "price_range"
    if re.search(r"roadshow|bookbuilding|수요예측|로드쇼", text, re.I):
        return "roadshow"
    if re.search(r"filed[^.]{0,80}?(?:s-1|f-1)|publicly filed|상장신고서\s*제출", text, re.I):
        return "public_filing"
    if re.search(r"confidential(?:ly)?\s+(?:filed|submitted)|draft registration statement|비공개[^.]{0,30}?(?:제출|신고)", text, re.I):
        return "confidential_filing"
    if re.search(
        r"(?:selected|appointed|tapped|picked)[^.]{0,140}?"
        r"(?:banks|underwriters|Goldman Sachs|Morgan Stanley)|"
        r"(?:banks|underwriters)[^.]{0,100}?(?:selected|appointed)|"
        r"(?:대표\s*주관사|주관사)[^.]{0,45}?(?:선정|낙점|확정)|"
        r"(?:선정|낙점)[^.]{0,60}?(?:골드만삭스|모건스탠리)",
        text, re.I,
    ):
        return "underwriters_selected"
    if re.search(r"bake[- ]?off|pitch meetings?|주관사[^.]{0,60}?(?:피치|경쟁|선정 절차)", text, re.I):
        return "bank_bakeoff"
    if re.search(r"weighs? (?:an )?ipo|considering (?:an )?ipo|explor(?:e|ing)[^.]{0,40}?ipo|상장\s*검토|ipo\s*검토", text, re.I):
        return "exploring"
    return ""

def extract_patch(event):
    base = clean(f"{event.get('title','')} {event.get('description','')}")
    page = article_text(event)
    text = (base + " " + page).strip()
    low = text.lower()
    if "solidigm" not in low and "솔리다임" not in low:
        return {}

    patch = {}
    # Only the news summary can promote an IPO stage. General web-page text
    # (menus/related stories) previously caused an incorrect postponement.
    stage = stage_from_text(base)
    if not stage:
        return {}
    patch["stage"] = stage

    y = re.search(r"(?:as early as|earliest|이르면)\s*(20\d{2})", text, re.I)
    if y:
        patch["target_year"] = int(y[1])

    valuation = usd_amount(text, r"(?:valu(?:e|ed|ation)|기업가치)")
    if valuation is not None and valuation >= 10_000_000_000:
        patch["valuation_max_usd"] = valuation

    raise_amt = usd_amount(text, r"(?:raise|raising|proceeds|조달)")
    if raise_amt is not None and 1_000_000_000 <= raise_amt < 100_000_000_000:
        patch["raise_target_usd"] = raise_amt

    pre = usd_amount(text, r"(?:pre[- ]?ipo|프리[- ]?ipo)")
    if pre is not None:
        patch["pre_ipo_raise_usd"] = pre

    if re.search(r"primary shares|new shares|신주", text, re.I):
        patch["primary_secondary_mix"] = "primary_included"
    if re.search(r"secondary shares|existing shares|구주매출|구주", text, re.I):
        patch["primary_secondary_mix"] = "secondary_included" if "primary_secondary_mix" not in patch else "primary_and_secondary"

    stake = re.search(r"(?:post[- ]ipo|after (?:the )?ipo|상장\s*후)[^%]{0,100}?([0-9]+(?:\.[0-9]+)?)\s*%[^.]{0,60}?(?:stake|ownership|지분)", text, re.I)
    if stake:
        patch["parent_post_ipo_stake_pct"] = float(stake[1])

    # Distinguish the two lead banks from participating syndicate banks.
    # Do not mine unrelated website navigation for underwriter names.
    bank_text = base.lower()[:1500]
    bank_aliases = {
        "Goldman Sachs": ("goldman sachs", "골드만삭스"),
        "Morgan Stanley": ("morgan stanley", "모건스탠리"),
        "JPMorgan Chase": ("jpmorgan chase", "jpmorgan", "jp모건", "제이피모건"),
        "Citigroup": ("citigroup", "씨티그룹"),
        "UBS": ("ubs", "유비에스"),
    }
    present = sorted(name for name, aliases in bank_aliases.items()
                     if any(re.search(r"(?<![a-z])" + re.escape(a) + r"(?![a-z])", bank_text) for a in aliases))
    if present and stage in ("underwriters_selected", "confidential_filing", "public_filing", "roadshow", "price_range", "priced"):
        patch["underwriters"] = present
        if "Goldman Sachs" in present and "Morgan Stanley" in present:
            patch["lead_underwriters"] = ["Goldman Sachs", "Morgan Stanley"]
        syndicate = [name for name in ("JPMorgan Chase", "Citigroup", "UBS") if name in present]
        if syndicate:
            patch["other_syndicate_banks"] = syndicate

    use = []
    proceeds_sentences = [
        s for s in re.split(r"(?<=[.!?])\s+|\n+", text)
        if re.search(r"proceeds|use of proceeds|funds? will be used|조달자금|공모자금", s, re.I)
    ]
    proceeds_text = " ".join(proceeds_sentences)
    if re.search(r"u\.s\.?\s+(?:fab|factory|plant|manufacturing)|미국[^.]{0,40}?(?:공장|생산시설)", proceeds_text, re.I):
        use.append("미국 NAND 생산거점")
    if re.search(r"ai[^.]{0,60}?(?:storage|ssd|data center)|기업용\s*ssd|ai\s*스토리지", proceeds_text, re.I):
        use.append("AI·기업용 SSD 성장투자")
    if use:
        patch["use_of_proceeds"] = sorted(set(use))

    # Bloomberg remains ONE anonymously sourced news report, not official.
    attributed_bloomberg = (
        event.get("is_curated_reported_milestone")
        or "bloomberg" in (event.get("source") or "").lower()
        or ("블룸버그" in base and "주관사" in base)
    )
    patch["evidence_state"] = ("top_tier_report" if attributed_bloomberg
                               else evidence_state(event.get("source"), event.get("direct_link")))
    if attributed_bloomberg:
        patch["reported_original"] = "Bloomberg"
        patch["independent_origin_count"] = 1
        patch["ipo_officially_confirmed"] = False
        patch["underwriter_officially_confirmed"] = False
    source_url = event.get("direct_link") or ""
    source_name = event.get("source") or ""
    # Reuters syndication pages can be the accessible evidence copy. Keep Reuters
    # as the canonical attribution/link for this baseline instead of silently
    # downgrading the displayed source to the republisher.
    reuters_syndication = (
        patch["evidence_state"] == "top_tier_report"
        and "reuters.com" not in source_url.lower()
        and (
            "reuters" in (event.get("title") or "").lower()
            or "reuters" in (event.get("description") or "").lower()
            or "reuters" in source_url.lower()
        )
    )
    if reuters_syndication:
        source_url = CANONICAL_REUTERS_URL
        source_name = "Reuters"
    patch["source_url"] = source_url
    patch["source_name"] = source_name
    if event.get("is_curated_reported_milestone"):
        patch["user_original_url"] = REPORT_YONHAP_URL
        patch["crosscheck_url"] = REPORT_INVESTING_URL
    patch["source_published_at_kst"] = event.get("published_at_kst") or ""
    return patch


def _month_from_text(text, published_at=""):
    low = text.lower()
    m = re.search(r"(20\d{2})[-./년]\s*(1[0-2]|0?[1-9])\s*(?:월)?", text)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"
    m = re.search(r"(?:from|starting|beginning|오는|올해\s*)\s*(?:in\s*)?(january|february|march|april|may|june|july|august|september|october|november|december|1[0-2]|[1-9])(?:\s*월)?", low, re.I)
    if not m:
        m = re.search(r"(1[0-2]|[1-9])\s*월(?:부터|에)", text)
    if not m:
        return ""
    names = {
        "january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
        "july":7,"august":8,"september":9,"october":10,"november":11,"december":12,
    }
    token = m.group(1).lower()
    month = names.get(token, int(token) if token.isdigit() else 0)
    if not month:
        return ""
    year = int(published_at[:4]) if re.match(r"^20\d{2}", published_at or "") else now_kst().year
    return f"{year:04d}-{month:02d}"


def manufacturing_patch_from_text(event, text):
    low = text.lower()
    if ("solidigm" not in low and "솔리다임" not in low) or not any(k in low for k in ("ssd", "datacenter", "data center", "데이터센터", "기업용")):
        return {}
    if not any(k in low for k in ("manufacturing", "production site", "odm", "pcn", "생산거점", "제조거점", "위탁생산", "생산 기반")):
        return {}

    patch = {}
    pcn = re.search(r"\b(0000\d{6}-\d{2})\b", text)
    if pcn:
        patch["pcn_number"] = pcn.group(1)

    if re.search(r"additional manufacturing site|제조\s*거점[^.]{0,40}?(?:추가|신규)|생산\s*거점[^.]{0,40}?(?:확대|추가|신규)", text, re.I):
        patch["stage"] = "pcn_announced"

    if re.search(r"all\s+solidigm\s+datacenter\s+ssds", text, re.I):
        patch["affected_scope"] = "all_solidigm_datacenter_ssds"

    if re.search(r"\btaiwan\b|대만", text, re.I):
        patch["reported_site_country"] = "Taiwan"
    if re.search(r"\bodm\b|original\s+design\s+manufactur|위탁\s*생산", text, re.I):
        patch["reported_manufacturing_model"] = "ODM"

    month = _month_from_text(text, event.get("published_at_kst") or "")
    if month and re.search(r"(?:ship|shipment|supply|출하|공급)", text, re.I):
        patch["reported_ship_start_month"] = month

    if re.search(r"(?:same|existing)[^.]{0,50}?(?:quality|terms|standard)|기존[^.]{0,40}?(?:품질|조건|표준)[^.]{0,40}?(?:유지|동일)", text, re.I):
        patch["reported_quality_standard_unchanged"] = True

    # Failure-mode triggers: only explicit statements may move these fields.
    if re.search(r"(?:quality|reliability|qualification)[^.]{0,80}?(?:issue|problem|failure|failed|defect)|품질[^.]{0,60}?(?:이슈|문제|불량|실패)|신뢰성[^.]{0,60}?(?:이슈|문제|실패)|검증[^.]{0,40}?(?:실패|탈락)", text, re.I):
        patch["quality_issue_status"] = "reported"
    if re.search(r"(?:quality|reliability)[^.]{0,80}?(?:issue|problem)[^.]{0,80}?(?:resolved|fixed|cleared)|(?:품질|신뢰성)[^.]{0,60}?(?:이슈|문제)[^.]{0,60}?(?:해결|해소|개선)", text, re.I):
        patch["quality_issue_status"] = "resolved"

    if re.search(r"(?:customer\s*)?(?:qualification|validation)[^.]{0,60}?(?:failed|rejected)|고객[^.]{0,40}?(?:인증|검증)[^.]{0,40}?(?:실패|탈락)", text, re.I):
        patch["customer_qualification_stage"] = "failed"
    elif re.search(r"(?:customer\s*)?(?:qualification|validation)[^.]{0,60}?(?:passed|completed|approved)|고객[^.]{0,40}?(?:인증|검증)[^.]{0,40}?(?:통과|완료|승인)", text, re.I):
        patch["customer_qualification_stage"] = "passed"
    elif re.search(r"(?:customer\s*)?(?:qualification|validation)[^.]{0,60}?(?:ongoing|underway|in progress)|고객[^.]{0,40}?(?:인증|검증)[^.]{0,40}?(?:진행|평가\s*중)", text, re.I):
        patch["customer_qualification_stage"] = "ongoing"

    partners = []
    if re.search(r"\bPTI\b|Powertech\s+Technology|파워텍테크놀로지", text, re.I):
        partners.append("PTI")
    if re.search(r"\bPegatron\b|페가트론", text, re.I):
        partners.append("Pegatron")
    if partners:
        patch["reported_existing_odm_partners"] = sorted(set(partners))

    # Named Taiwan server assemblers are ecosystem targets unless the article
    # explicitly says they are Solidigm's direct SSD customers/contracts.
    customers = []
    for name, pat in (
        ("Foxconn", r"\bFoxconn\b|폭스콘"),
        ("Quanta", r"\bQuanta\b|콴타"),
        ("Wistron", r"\bWistron\b|위스트론"),
        ("Wiwynn", r"\bWiwynn\b|위윈"),
    ):
        if re.search(pat, text, re.I) and re.search(
            rf"(?:Solidigm|솔리다임)[^.]{{0,120}}?(?:direct\s+customer|customer\s+contract|supply\s+contract|직접\s*고객|공급\s*계약)[^.]*?(?:{pat})|"
            rf"(?:{pat})[^.]{{0,120}}?(?:Solidigm|솔리다임)[^.]*?(?:direct\s+customer|customer\s+contract|supply\s+contract|직접\s*고객|공급\s*계약)",
            text, re.I
        ):
            customers.append(name)
    if customers:
        patch["confirmed_direct_server_customers"] = sorted(set(customers))

    # Capacity numbers require an explicit production-capacity denominator.
    cap = re.search(r"(?:production\s+capacity|output\s+capacity|생산능력|생산\s*능력)[^0-9]{0,60}([\d,.]+)\s*(?:units?|drives?|대|개)\s*(?:per\s+month|monthly|월)", text, re.I)
    if cap:
        patch["capacity_units_per_month"] = float(cap.group(1).replace(",", ""))

    if re.search(r"(?:began|started|commenced)[^.]{0,60}?(?:ship|supply)|출하\s*(?:시작|개시)|공급\s*(?:시작|개시)", text, re.I):
        patch["stage"] = "shipping"
    if re.search(r"(?:delayed|postponed)[^.]{0,60}?(?:ship|production)|출하[^.]{0,40}?(?:지연|연기)|생산[^.]{0,40}?(?:지연|연기)", text, re.I):
        patch["stage"] = "delayed"

    patch["manufacturing_scope"] = "ssd_manufacturing_not_nand_wafer_fab"
    patch["reported_source_url"] = event.get("direct_link") or ""
    patch["reported_source_name"] = event.get("source") or ""
    patch["reported_source_published_at_kst"] = event.get("published_at_kst") or ""
    return patch


def extract_manufacturing_patch(event):
    base = clean(f"{event.get('title','')} {event.get('description','')}")
    page = article_text(event)
    return manufacturing_patch_from_text(event, (base + " " + page).strip())


def merge_manufacturing_state(current, patch):
    out = dict(current or {})
    old_stage = out.get("stage", "")
    new_stage = patch.get("stage", "")
    rank = {"pcn_announced":1, "shipping":2, "delayed":2}
    for k, v in patch.items():
        if k == "stage":
            continue
        if k in ("reported_existing_odm_partners", "confirmed_direct_server_customers") and v:
            out[k] = sorted(set(out.get(k) or []) | set(v))
        elif v not in (None, "", []):
            out[k] = v
    if new_stage:
        if new_stage == "delayed":
            out["stage"] = new_stage
        elif old_stage == "delayed" and new_stage != "shipping":
            pass
        elif rank.get(new_stage, 0) >= rank.get(old_stage, 0):
            out["stage"] = new_stage
    return out


def manufacturing_material_changes(old, new):
    reasons = []
    if old.get("stage") != new.get("stage"):
        labels = {"pcn_announced":"추가 제조거점 PCN 공지","shipping":"신규 거점 제품 출하 시작","delayed":"신규 거점 출하·생산 지연"}
        reasons.append(f"제조 단계 {labels.get(old.get('stage'), old.get('stage','미확인'))}→{labels.get(new.get('stage'), new.get('stage','미확인'))}")
    if old.get("pcn_number") != new.get("pcn_number") and new.get("pcn_number"):
        reasons.append(f"제조거점 PCN {old.get('pcn_number') or '미확인'}→{new['pcn_number']}")
    if old.get("reported_site_country") != new.get("reported_site_country") and new.get("reported_site_country"):
        reasons.append(f"제조거점 국가 {old.get('reported_site_country') or '미확인'}→{new['reported_site_country']}")
    if old.get("reported_ship_start_month") != new.get("reported_ship_start_month") and new.get("reported_ship_start_month"):
        reasons.append(f"출하 시작 {old.get('reported_ship_start_month') or '미확인'}→{new['reported_ship_start_month']}")
    oldp, newp = set(old.get("reported_existing_odm_partners") or []), set(new.get("reported_existing_odm_partners") or [])
    added = sorted(newp - oldp)
    if added:
        reasons.append("ODM 파트너 신규 확인: " + ", ".join(added))
    oldc, newc = set(old.get("confirmed_direct_server_customers") or []), set(new.get("confirmed_direct_server_customers") or [])
    addedc = sorted(newc - oldc)
    if addedc:
        reasons.append("직접 서버 고객·공급계약 실명 신규 확인: " + ", ".join(addedc))
    a, b = old.get("capacity_units_per_month"), new.get("capacity_units_per_month")
    if a and b:
        pct = (float(b) / float(a) - 1.0) * 100.0
        if abs(pct) >= 10.0:
            reasons.append(f"신규 거점 생산능력 월 {float(a):,.0f}→{float(b):,.0f}대 ({pct:+.1f}%)")
    elif a is None and b is not None:
        reasons.append(f"신규 거점 생산능력 월 {float(b):,.0f}대 최초 공개")
    if old.get("official_pcn_verified") is not True and new.get("official_pcn_verified") is True:
        reasons.append("Solidigm 공식 PCN 확인")

    a, b = old.get("quality_issue_status"), new.get("quality_issue_status")
    if a != b and b and b != "not_reported":
        labels = {"reported":"품질·신뢰성 이슈 발생", "resolved":"품질·신뢰성 이슈 해소"}
        reasons.append(f"품질 상태 {a or '미확인'}→{labels.get(b,b)}")

    a, b = old.get("customer_qualification_stage"), new.get("customer_qualification_stage")
    if a != b and b and b != "not_reported":
        labels = {"ongoing":"고객 인증·검증 진행", "passed":"고객 인증·검증 통과", "failed":"고객 인증·검증 실패"}
        reasons.append(f"고객 검증 단계 {a or '미확인'}→{labels.get(b,b)}")
    return reasons


def manufacturing_alert_text(old, new, reasons, checked):
    lines = [
        "🚨 <b>Solidigm eSSD 생산거점·ODM 변화</b>",
        "━━━━━━━━━━━━━━━━",
        f"• 현재 단계: <b>{html.escape(new.get('stage') or '확인 불가')}</b>",
        f"• 공식 PCN: <b>{html.escape(new.get('pcn_number') or '확인 불가')}</b> · {html.escape(new.get('pcn_publish_date') or '날짜 미확인')}",
        f"• 적용 범위: <b>{'전체 Solidigm 데이터센터 SSD' if new.get('affected_scope') == 'all_solidigm_datacenter_ssds' else html.escape(str(new.get('affected_scope') or '미확인'))}</b>",
    ]
    if new.get("reported_site_country"):
        lines.append(f"• 제조거점: {html.escape(new['reported_site_country'])} · 모델 {html.escape(new.get('reported_manufacturing_model') or '미확인')}")
    if new.get("reported_ship_start_month"):
        lines.append(f"• 출하 시작 보도: {html.escape(new['reported_ship_start_month'])}")
    if new.get("reported_existing_odm_partners"):
        lines.append("• 기존 ODM 파트너 보도: " + html.escape(", ".join(new["reported_existing_odm_partners"])))
    if new.get("capacity_units_per_month") is None and new.get("capacity_eb_per_year") is None:
        lines.append("• 생산능력: 수량·EB 기준 미공개 — 기사 제목만으로 증설률을 계산하지 않습니다.")
    if new.get("quality_issue_status") not in (None, "not_reported"):
        lines.append("• 품질·신뢰성 상태: " + html.escape(str(new["quality_issue_status"])))
    if new.get("customer_qualification_stage") not in (None, "not_reported"):
        lines.append("• 고객 인증·검증: " + html.escape(str(new["customer_qualification_stage"])))
    if new.get("confirmed_direct_server_customers"):
        lines.append("• 직접 서버 고객 확인: " + html.escape(", ".join(new["confirmed_direct_server_customers"])))
    else:
        lines.append("• 고객 구분: Foxconn·Quanta·Wistron 등은 대만 AI 서버 생태계 설명이며 Solidigm 직접 고객·공급계약으로 승격하지 않습니다.")
    lines.append("• 공정 구분: 대만 SSD 제조·조립 거점 확대이며 NAND 웨이퍼 팹 증설과 분리합니다.")
    lines.append("• 이번 변화: <b>" + html.escape(" · ".join(reasons)) + "</b>")
    lines.append("• 다음 확인: 실제 12월 출하 · 생산능력 수치 · 신규 ODM 실명 · 고객 인증·직접 공급계약 · 품질·수율 이슈 · 일정 지연")
    src = new.get("official_source_url") or SOLIDIGM_DMS_URL
    lines.append("• 공식 근거: Solidigm PCN/DMS · " + href(src))
    if new.get("reported_source_url"):
        lines.append("• 보도 근거: " + html.escape(new.get("reported_source_name") or "보도") + " · " + href(new["reported_source_url"]))
    lines.append("• 조회: " + checked.strftime("%Y-%m-%d %H:%M KST"))
    return "\n".join(lines) + "\n"

def merge_state(current, patch):
    out = dict(current or {})
    old_stage = out.get("stage")
    new_stage = patch.get("stage")
    old_evidence = out.get("evidence_state", "reported")
    new_evidence = patch.get("evidence_state", "reported")
    can_replace_source = EVIDENCE_RANK.get(new_evidence, 0) >= EVIDENCE_RANK.get(old_evidence, 0)

    # A stale or generic company denial cannot downgrade IPO stage, replace
    # newer deal parameters, or masquerade as official IPO approval.
    if (
        new_stage in STAGE_RANK and old_stage in STAGE_RANK
        and STAGE_RANK[new_stage] < STAGE_RANK[old_stage]
    ):
        return out

    for k, v in patch.items():
        if k in ("stage", "evidence_state", "source_url", "source_name", "source_published_at_kst"):
            continue
        if v not in (None, "", []):
            out[k] = v

    if new_stage:
        if new_stage in ("postponed", "withdrawn"):
            if can_replace_source:
                out["stage"] = new_stage
        elif old_stage in ("postponed", "withdrawn") and new_stage not in ("listed",):
            pass
        elif not old_stage or STAGE_RANK.get(new_stage, 0) >= STAGE_RANK.get(old_stage, 0):
            out["stage"] = new_stage

    if can_replace_source:
        out["evidence_state"] = new_evidence
        for k in ("source_url", "source_name", "source_published_at_kst"):
            if patch.get(k):
                out[k] = patch[k]
    return out

def material_changes(old, new):
    reasons = []
    if old.get("stage") != new.get("stage"):
        reasons.append(f"상장 단계 {STAGE_KO.get(old.get('stage'), old.get('stage','미확인'))}→{STAGE_KO.get(new.get('stage'), new.get('stage','미확인'))}")
    for field, label, min_abs in (
        ("valuation_max_usd", "기업가치", 10_000_000_000),
        ("raise_target_usd", "조달 규모", 1_000_000_000),
        ("pre_ipo_raise_usd", "Pre-IPO 조달", 500_000_000),
    ):
        a, b = old.get(field), new.get(field)
        if a and b:
            pct = (float(b) / float(a) - 1) * 100
            if abs(float(b) - float(a)) >= min_abs or abs(pct) >= 10:
                reasons.append(f"{label} {pct:+.1f}%")
        elif a is None and b is not None:
            reasons.append(f"{label} 신규 확인")
    if old.get("target_year") != new.get("target_year") and new.get("target_year"):
        reasons.append(f"목표 시점 {old.get('target_year','미확인')}→{new['target_year']}")
    if old.get("underwriters") != new.get("underwriters") and new.get("underwriters"):
        reasons.append("대표주관사·주관단 명단 보도")
    if old.get("lead_underwriters") != new.get("lead_underwriters") and new.get("lead_underwriters"):
        reasons.append("Goldman Sachs·Morgan Stanley 대표주관사 선정 보도")
    if old.get("other_syndicate_banks") != new.get("other_syndicate_banks") and new.get("other_syndicate_banks"):
        reasons.append("JPMorgan·Citigroup·UBS 주관단 참여 보도")
    if old.get("primary_secondary_mix") != new.get("primary_secondary_mix") and new.get("primary_secondary_mix"):
        reasons.append("신주·구주매출 구조 확인")
    if old.get("parent_post_ipo_stake_pct") != new.get("parent_post_ipo_stake_pct") and new.get("parent_post_ipo_stake_pct") is not None:
        reasons.append("SK하이닉스 상장 후 지분율 확인")
    if old.get("use_of_proceeds") != new.get("use_of_proceeds") and new.get("use_of_proceeds"):
        reasons.append("조달자금 용도 확인")
    if old.get("evidence_state") != "official" and new.get("evidence_state") == "official":
        reasons.append("신뢰보도→회사·SEC 공식 확인")
    return reasons

def krw_large(usd, rate):
    if usd is None or rate is None:
        return "원화 환산 확인 불가"
    eok = int(round(float(usd) * float(rate) / 100_000_000))
    if eok >= 10000:
        jo, rem = divmod(eok, 10000)
        return f"약 {jo:,}조{rem:,}억원" if rem else f"약 {jo:,}조원"
    return f"약 {eok:,}억원"

def usd_display(usd, rate):
    if usd is None:
        return "확인 불가"
    hundred_million = float(usd) / 100_000_000
    if abs(hundred_million - round(hundred_million)) < 1e-9:
        foreign = f"{int(round(hundred_million)):,}억달러"
    else:
        foreign = f"{hundred_million:,.1f}억달러"
    return f"{foreign}({krw_large(usd, rate)})"


def fx_quote():
    try:
        from fx_api import daily_krw
        q = daily_krw()
        return q.rate, q.basis
    except Exception:
        return None, "환율 확인 불가"

def href(url, label="원문"):
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'

def alert_text(old, new, reasons, checked):
    rate, fx_basis = fx_quote()
    evidence_ko = {
        "official": "회사·SEC 공식 확인",
        "top_tier_report": "Reuters·Bloomberg 등 신뢰 보도 단계(회사 미확정)",
        "reported": "신뢰 보도 단계",
    }.get(new.get("evidence_state"), "확인 단계")
    lines = [
        "🚨 <b>Solidigm IPO 상태 변화</b>",
        "━━━━━━━━━━━━━━━━",
        f"• 현재 단계: <b>{html.escape(STAGE_KO.get(new.get('stage'), new.get('stage','확인 불가')))}</b>",
        f"• 확인 수준: <b>{html.escape(evidence_ko)}</b>",
    ]
    if new.get("target_year"):
        lines.append(f"• 목표 시점: <b>이르면 {new['target_year']}년</b>")
    if new.get("valuation_max_usd"):
        lines.append(f"• 거론 기업가치: <b>최대 {usd_display(new['valuation_max_usd'], rate)}</b>")
    if new.get("raise_target_usd"):
        lines.append(f"• 조달 가능 규모: <b>{usd_display(new['raise_target_usd'], rate)}</b>")
    if new.get("pre_ipo_raise_usd"):
        lines.append(f"• 선행 보도상 별도 상장 전 자금조달 검토액: {usd_display(new['pre_ipo_raise_usd'], rate)} (이번 기사에서 재확인된 확정액 아님)")
    if new.get("lead_underwriters"):
        lines.append("• 대표주관사(블룸버그 보도): <b>" + html.escape(", ".join(new["lead_underwriters"])) + "</b>")
    if new.get("other_syndicate_banks"):
        lines.append("• 추가 참여 주관단(보도): " + html.escape(", ".join(new["other_syndicate_banks"])))
    if new.get("underwriters") and not new.get("lead_underwriters"):
        lines.append("• 주관사 명단(보도): " + html.escape(", ".join(new["underwriters"])))
    if new.get("reported_original") == "Bloomberg":
        lines.append("• 출처 계보: Bloomberg 원보도 → 연합뉴스·이데일리·Investing.com 재인용. 별개 독립 확인 3건이 아닙니다.")
    if new.get("ipo_officially_confirmed") is True and new.get("primary_secondary_mix"):
        labels = {"primary_included":"신주 포함","secondary_included":"구주매출 포함","primary_and_secondary":"신주+구주매출"}
        lines.append("• 회사 확정 공모 구조: " + labels.get(new["primary_secondary_mix"], new["primary_secondary_mix"]))
    else:
        lines.append("• 신주·구주 매출 비율 및 자금이 어느 회사에 귀속될지: <b>미확정</b>")
    if new.get("parent_post_ipo_stake_pct") is not None:
        lines.append(f"• SK하이닉스 상장 후 지분율: {new['parent_post_ipo_stake_pct']:.1f}%")
    if new.get("use_of_proceeds"):
        lines.append("• 조달자금 용도: " + html.escape(" · ".join(new["use_of_proceeds"])))
    lines.append("• 이번 변화: <b>" + html.escape(" · ".join(reasons)) + "</b>")
    if new.get("reported_original") == "Bloomberg" and (
        old.get("source_name") == "Reuters" or "알림 표시 보강" in " ".join(reasons)
    ):
        lines.append(
            "• 보도 추정치 비교: Reuters(9월 25일) 조달 "
            + usd_display(15_000_000_000, rate)
            + "·기업가치 " + usd_display(150_000_000_000, rate)
            + " ↔ Bloomberg(10월 8일) 조달 "
            + usd_display(new.get("raise_target_usd"), rate)
            + "·기업가치 " + usd_display(new.get("valuation_max_usd"), rate)
        )
        lines.append("• 확정 공모금액 감액이 아니라 서로 다른 보도상 추정치의 비교입니다.")
    lines.append("• 다음 확인: 대표주관사 선정 · SEC 비공개/공개 신고 · 공모가 밴드 · 신주/구주 비중 · SK하이닉스 잔여지분 · 자금용도")
    if new.get("source_url"):
        lines.append(f"• 근거: {html.escape(new.get('source_name') or '출처')} · {href(new['source_url'])}")
    if new.get("user_original_url"):
        lines.append("• 사용자 원문: 연합뉴스 " + href(new["user_original_url"]))
    lines.append("• SK하이닉스 공식 입장(10월 1일): 구체적인 자금조달 방안 미확정. 기존 주주 경제적 가치·희석 위험 검토 " + href(OFFICIAL_SK_REPLY))
    lines.append("• 확인 대기: SEC 신고, 신주·구주 비율, SK하이닉스 상장 후 지분, 자금 유입처, 이사회 승인.")
    lines.append("• 주의: 이번 주관사·조달액·기업가치·일정은 보도 단계이며 회사나 SEC 확정 사실이 아닙니다.")
    lines.append("• 환율: " + html.escape(fx_basis))
    lines.append("• 조회: " + checked.strftime("%Y-%m-%d %H:%M KST"))
    return "\n".join(lines) + "\n"

def main():
    checked = now_kst()
    state = load_state()

    # --- IPO lane (existing) ---
    current = dict(state.get("current_state") or {})
    candidate = dict(current)
    best_source = None

    cutoff = checked - timedelta(days=10)
    for event in read_events():
        try:
            dt = datetime.fromisoformat(event.get("published_at_kst") or "")
        except Exception:
            continue
        if dt < cutoff or dt > checked + timedelta(minutes=10):
            continue
        patch = extract_patch(event)
        if not patch:
            continue
        before = dict(candidate)
        candidate = merge_state(candidate, patch)
        if candidate != before:
            best_source = event

    ipo_reasons = material_changes(current, candidate)
    ipo_format_refresh = bool(
        candidate.get("stage") == "underwriters_selected"
        and candidate.get("reported_original") == "Bloomberg"
        and int(state.get("ipo_alert_format_version") or 0) < IPO_ALERT_FORMAT_VERSION
    )
    if ipo_format_refresh and not ipo_reasons:
        ipo_reasons = [
            "알림 표시 보강: 대표주관사·참여은행을 분리하고 기존 주주 희석·회사 미확정 상태를 명시 "
            "(기존 주관사 선정 소식의 정확한 재표시, 새로운 IPO 진척 아님)"
        ]

    # --- Manufacturing / Taiwan ODM lane (new, same existing route) ---
    if int(state.get("watch_version") or 0) < WATCH_VERSION or not state.get("manufacturing_state"):
        manufacturing_current = dict(MANUFACTURING_BASELINE)
        manufacturing_current.update(dict(state.get("manufacturing_state") or {}))
    else:
        manufacturing_current = dict(state.get("manufacturing_state") or {})
    manufacturing_candidate = dict(manufacturing_current)
    manufacturing_best_source = None

    for event in read_manufacturing_events():
        try:
            dt = datetime.fromisoformat(event.get("published_at_kst") or "")
        except Exception:
            continue
        if dt < cutoff or dt > checked + timedelta(minutes=10):
            continue
        patch = extract_manufacturing_patch(event)
        if not patch:
            continue
        before = dict(manufacturing_candidate)
        manufacturing_candidate = merge_manufacturing_state(manufacturing_candidate, patch)
        if manufacturing_candidate != before:
            manufacturing_best_source = event

    manufacturing_reasons = manufacturing_material_changes(manufacturing_current, manufacturing_candidate)

    state["watch_version"] = WATCH_VERSION
    if ipo_format_refresh:
        state["ipo_alert_format_version"] = IPO_ALERT_FORMAT_VERSION
    state["last_checked_at_kst"] = checked.isoformat(timespec="seconds")
    state["current_state"] = candidate
    state["manufacturing_state"] = manufacturing_candidate

    if best_source:
        state["last_evidence_url"] = best_source.get("direct_link") or ""
        state["last_evidence_published_at_kst"] = best_source.get("published_at_kst") or ""
    if manufacturing_best_source:
        state["last_manufacturing_evidence_url"] = manufacturing_best_source.get("direct_link") or ""
        state["last_manufacturing_evidence_published_at_kst"] = manufacturing_best_source.get("published_at_kst") or ""

    sections = []
    if ipo_reasons:
        sections.append(alert_text(current, candidate, ipo_reasons, checked).strip())
        state["last_alert_reasons"] = ipo_reasons
        state["last_alert_at_kst"] = checked.isoformat(timespec="seconds")
    if manufacturing_reasons:
        sections.append(manufacturing_alert_text(manufacturing_current, manufacturing_candidate, manufacturing_reasons, checked).strip())
        state["last_manufacturing_alert_reasons"] = manufacturing_reasons
        state["last_manufacturing_alert_at_kst"] = checked.isoformat(timespec="seconds")

    ALERT.parent.mkdir(exist_ok=True)
    if sections:
        ALERT.write_text(("\n\n<<<TELEGRAM_MESSAGE_BREAK>>>\n\n".join(sections)).strip() + "\n", encoding="utf-8")
    else:
        ALERT.unlink(missing_ok=True)

    save_state(state)
    print(
        "solidigm_ipo_watch=true ipo_changes=" + str(len(ipo_reasons))
        + " manufacturing_changes=" + str(len(manufacturing_reasons))
    )


if __name__ == "__main__":
    main()
