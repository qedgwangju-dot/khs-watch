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
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

try:
    from googlenewsdecoder import gnewsdecoder
except Exception:  # pragma: no cover - dependency failure is handled explicitly
    gnewsdecoder = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "rubin_hbm_watch_state.json"
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)

UA = "Mozilla/5.0 (compatible; khs-watch/2.0; +https://github.com/qedgwangju-dot/khs-watch)"
FX_URL = "https://api.frankfurter.dev/v2/rate/USD/KRW"

OFFICIAL_RUBIN_GB = 288
RUMORED_ULTRA_GB = 192
BREAKEVEN_GPU_GROWTH = OFFICIAL_RUBIN_GB / RUMORED_ULTRA_GB - 1
BASE_NVLINK_GPU = 72
ULTRA_NVLINK_GPU = 576
BASE_SYSTEM_GB = BASE_NVLINK_GPU * OFFICIAL_RUBIN_GB
ULTRA_SYSTEM_GB = ULTRA_NVLINK_GPU * RUMORED_ULTRA_GB
SYSTEM_HBM_GROWTH = ULTRA_SYSTEM_GB / BASE_SYSTEM_GB - 1
SEND_FRESHNESS_HOURS = 72

QUERIES = [
    (
        "rubin_spec",
        '"Rubin Ultra" (HBM OR HBM4 OR HBM4E OR 192GB OR 288GB OR 1TB OR 8-Hi OR 12-Hi)',
    ),
    (
        "hbm4e_validation",
        'HBM4E (qualification OR validation OR sample OR mass production OR production) (Samsung OR "SK hynix" OR Micron)',
    ),
    (
        "rubin_shipments",
        '"Rubin Ultra" (NVL576 OR shipment OR production OR deployment OR order OR ramp OR customer)',
    ),
    (
        "hbm_2027_contract",
        '2027 HBM (contract OR price OR pricing OR LTA OR supply OR allocation OR volume) (Samsung OR "SK hynix" OR Micron OR NVIDIA)',
    ),
    (
        "memory_migration",
        '(Rubin OR "Rubin Ultra" OR HBM) (DDR5 OR SOCAMM2 OR eSSD OR "enterprise SSD" OR "KV cache" OR offload OR pooling)',
    ),
]

CATEGORY_KO = {
    "rubin_spec": "Rubin Ultra 최종 HBM 사양",
    "hbm4e_validation": "HBM4E 고객 검증·양산",
    "rubin_shipments": "Rubin Ultra·NVL576 실제 출하",
    "hbm_2027_contract": "2027 HBM 계약가격·물량",
    "memory_migration": "DDR5·SOCAMM2·기업용 eSSD 이동",
}

OFFICIAL_SOURCE_HINTS = (
    "nvidia", "samsung newsroom", "삼성전자 뉴스룸", "sk hynix", "sk하이닉스 뉴스룸",
    "micron technology", "micron newsroom",
)
TRUSTED_SOURCE_HINTS = (
    "trendforce", "reuters", "bloomberg", "the information", "semianalysis", "digitimes",
    "tom's hardware", "toms hardware", "financial times", "wall street journal", "wsj", "cnbc",
    "thelec", "the elec", "연합뉴스", "yonhap",
)
LOW_VALUE_SOURCE_HINTS = (
    "finance.biggo", "aol", "24/7 wall st", "247wallst", "cryptobriefing",
)


def fetch(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def rss_url(query: str, lang: str) -> str:
    q = urllib.parse.quote(query)
    if lang == "ko":
        return f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def parse_pubdate(value: str) -> datetime | None:
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo("Asia/Seoul"))
    except Exception:
        return None


def relevant(category: str, text: str) -> bool:
    low = text.lower()
    if category == "rubin_spec":
        return "rubin ultra" in low and any(k in low for k in ("hbm", "192gb", "288gb", "768gb", "1tb", "8-hi", "8hi", "12-hi", "12hi"))
    if category == "hbm4e_validation":
        return "hbm4e" in low and any(k in low for k in ("samsung", "sk hynix", "sk하이닉스", "micron")) and any(k in low for k in ("qualification", "validation", "sample", "mass production", "production", "양산", "검증", "샘플"))
    if category == "rubin_shipments":
        return ("rubin ultra" in low or "nvl576" in low) and any(k in low for k in ("shipment", "ship", "production", "deployment", "order", "ramp", "customer", "출하", "양산", "도입", "주문"))
    if category == "hbm_2027_contract":
        return "2027" in low and "hbm" in low and any(k in low for k in ("contract", "price", "pricing", "lta", "supply", "allocation", "volume", "계약", "가격", "공급", "물량"))
    if category == "memory_migration":
        return any(k in low for k in ("rubin", "hbm")) and any(k in low for k in ("ddr5", "socamm2", "essd", "enterprise ssd", "kv cache", "offload", "pooling", "오프로드", "풀링"))
    return False


def source_quality(source: str) -> str:
    low = (source or "").lower().strip()
    if any(k in low for k in OFFICIAL_SOURCE_HINTS):
        return "공식·회사자료"
    if any(k in low for k in TRUSTED_SOURCE_HINTS):
        return "신뢰 리서치·보도"
    return "일반 보도"


def quality_rank(value: str) -> int:
    if value.startswith("공식"):
        return 4
    if "Reuters" in value or value.startswith("신뢰"):
        return 3
    if value.startswith("교차검증"):
        return 2
    return 1


def normalized_title(title: str) -> str:
    value = clean_text(title).lower()
    if " - " in value:
        value = value.rsplit(" - ", 1)[0]
    value = re.sub(r"[^a-z0-9가-힣]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def event_id(category: str, title: str, link: str) -> str:
    raw = f"{category}|{title}|{link}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def is_fresh_for_send(event: dict, now: datetime) -> bool:
    raw = event.get("published_at_kst") or ""
    if not raw:
        return False
    try:
        dt = datetime.fromisoformat(raw)
    except Exception:
        return False
    return now - timedelta(hours=SEND_FRESHNESS_HOURS) <= dt <= now + timedelta(minutes=10)


def read_feed(category: str, query: str, lang: str) -> tuple[list[dict], list[str]]:
    errors: list[str] = []
    out: list[dict] = []
    url = rss_url(query, lang)
    try:
        root = ET.fromstring(fetch(url))
        for item in root.findall("./channel/item"):
            title = clean_text(item.findtext("title") or "")
            link = clean_text(item.findtext("link") or "")
            desc = clean_text(item.findtext("description") or "")
            pub = clean_text(item.findtext("pubDate") or "")
            source_node = item.find("source")
            source = clean_text(source_node.text if source_node is not None and source_node.text else "")
            text = f"{title} {desc}"
            if not title or not link or not relevant(category, text):
                continue
            dt = parse_pubdate(pub)
            out.append({
                "id": event_id(category, title, link),
                "category": category,
                "title": title,
                "link": link,
                "source": source or "출처 미표시",
                "published_at_kst": dt.isoformat(timespec="seconds") if dt else "",
                "description": desc[:900],
                "quality": source_quality(source),
                "lang": lang,
            })
    except Exception as e:
        errors.append(f"{category}/{lang}: {type(e).__name__}: {e}")
    return out, errors


def decode_google_news_url(link: str) -> str:
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


def meta_content(raw_html: str, key: str) -> str:
    patterns = [
        rf'<meta[^>]+(?:property|name)=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']+)["\']',
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{re.escape(key)}["\']',
    ]
    for pattern in patterns:
        m = re.search(pattern, raw_html, re.I)
        if m:
            return clean_text(m.group(1))
    return ""


def article_text_from_html(raw_html: str) -> str:
    value = re.sub(r"<(script|style|svg|noscript)[^>]*>.*?</\1>", " ", raw_html, flags=re.I | re.S)
    value = re.sub(r"<!--.*?-->", " ", value, flags=re.S)
    value = clean_text(value)
    return value[:16000]


def enrich_event(event: dict) -> dict:
    e = dict(event)
    direct = decode_google_news_url(e.get("link") or "")
    e["direct_link"] = direct
    e["link_verified"] = bool(direct)
    e["article_title"] = e.get("title") or ""
    e["article_description"] = e.get("description") or ""
    e["article_text"] = ""
    e["origin_source"] = e.get("source") or "출처 미표시"

    if not direct:
        return e

    try:
        raw = fetch(direct, timeout=18).decode("utf-8", errors="ignore")
        og_title = meta_content(raw, "og:title") or meta_content(raw, "twitter:title")
        desc = meta_content(raw, "og:description") or meta_content(raw, "description")
        body = article_text_from_html(raw)
        if og_title:
            e["article_title"] = og_title
        if desc:
            e["article_description"] = desc
        e["article_text"] = body

        source_low = (e.get("source") or "").lower()
        direct_host = (urlparse(direct).hostname or "").lower()
        body_low = body.lower()
        if "reuters" in body_low and "reuters" not in source_low:
            republisher = e.get("source") or direct_host
            e["origin_source"] = f"Reuters (재전재: {republisher})"
            e["quality"] = "신뢰 리서치·보도"
        elif "thelec" in direct_host:
            e["origin_source"] = "THE ELEC"
            e["quality"] = "신뢰 리서치·보도"
        elif "news.skhynix.com" in direct_host or "skhynix.com" in direct_host:
            e["origin_source"] = "SK하이닉스 공식자료"
            e["quality"] = "공식·회사자료"
    except Exception as ex:
        e["enrich_error"] = f"{type(ex).__name__}: {ex}"
    return e


def compact_fact_text(event: dict) -> str:
    return " ".join(
        x for x in (
            event.get("title") or "",
            event.get("description") or "",
            event.get("article_title") or "",
            event.get("article_description") or "",
            event.get("article_text") or "",
        ) if x
    )


def pct_tokens(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"[+-]?\d+(?:\.\d+)?%", text)))


def money_tokens(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"\$\s*\d+(?:\.\d+)?\s*(?:billion|million|B|M)\b", text, re.I)))


def make_fact(event: dict) -> dict | None:
    e = dict(event)
    text = compact_fact_text(e)
    low = text.lower()
    cat = e.get("category") or ""
    bullets: list[str] = []
    headline = ""
    verdict = ""
    fact_key = ""

    # SK hynix Indiana HBM4E: classify it correctly as a packaging/production-base event,
    # not as customer qualification.
    if cat == "hbm4e_validation" and "hbm4e" in low and "indiana" in low and "2029" in low and ("sk hynix" in low or "sk hynix" in low.replace("-", " ")):
        fact_key = "skhynix_indiana_hbm4e_2029"
        headline = "SK하이닉스, 인디애나 HBM4E 첨단 패키징 양산을 2029년 3분기에 시작 계획"
        bullets.append("• 확인된 사실: 미국 인디애나 거점에서 차세대 HBM4E의 첨단 패키징·양산을 2029년 3분기부터 시작할 계획입니다.")
        if "cleanroom" in low and "2028" in low:
            bullets.append("• 일정: 클린룸은 2028년 하반기 가동을 목표로 합니다.")
        if "hundreds of thousands" in low and "wafer" in low:
            bullets.append("• 생산 규모: 장기적으로 연간 수십만 장 수준의 웨이퍼를 처리하는 생산능력을 목표로 제시했습니다.")
        if ("$4 billion" in low or "$4b" in low or "4 billion" in low) and "indiana" in low:
            bullets.append("• 투자: 인디애나 프로젝트는 40억달러 이상 규모입니다.")
        if "shortage" in low and "2030" in low:
            bullets.append("• 수요 신호: 곽노정 CEO는 메모리 공급 부족이 2030년 말까지 이어질 것으로 전망했습니다.")
        bullets.append("• 구분: 이 소식은 2027년 HBM4E 고객 인증 완료 뉴스가 아니라, 2029년 미국 후공정·첨단패키징 생산기지 일정입니다.")
        verdict = "🟢 중장기 HBM 공급 확대와 수요 강도를 확인하는 긍정 신호. 다만 단기 고객 인증 완료 신호로 해석하면 안 됩니다."

    elif cat == "hbm4e_validation" and "hbm4e" in low:
        company = ""
        if "sk hynix" in low or "sk하이닉스" in low:
            company = "SK하이닉스"
        elif "samsung" in low or "삼성전자" in low:
            company = "삼성전자"
        elif "micron" in low:
            company = "Micron"
        if not company:
            return None

        if any(k in low for k in ("qualification completed", "qualified", "validation completed", "certification completed", "인증 완료", "검증 완료")):
            fact_key = f"{company}_hbm4e_customer_validation"
            headline = f"{company}, HBM4E 고객 검증 완료 신호"
            bullets.append("• 확인된 사실: 기사에서 HBM4E 고객 검증·인증 완료를 명시했습니다.")
            verdict = "🟢 가장 중요한 강세 조건 중 하나인 고객 인증 완료에 해당합니다. 실제 양산 개시일과 계약물량을 다음으로 확인해야 합니다."
        elif any(k in low for k in ("mass production", "volume production", "양산")):
            year = next(iter(re.findall(r"20\d{2}", text)), "")
            q = ""
            if any(k in low for k in ("third quarter", "q3", "3분기")):
                q = " 3분기"
            elif any(k in low for k in ("second half", "h2", "하반기")):
                q = " 하반기"
            fact_key = f"{company}_hbm4e_mass_production_{year}_{q.strip()}"
            headline = f"{company}, HBM4E 양산 일정 구체화{(' — ' + year + q) if year else ''}"
            bullets.append(f"• 확인된 사실: HBM4E 양산 일정이 {year + q if year else '기사에서 구체화'}됐습니다.")
            verdict = "🟢 양산 일정 구체화는 긍정적이지만, 고객 인증 완료·실제 출하와는 별도로 확인합니다."
        elif any(k in low for k in ("sample", "samples", "샘플")):
            year = next(iter(re.findall(r"20\d{2}", text)), "")
            fact_key = f"{company}_hbm4e_sample_{year}"
            headline = f"{company}, HBM4E 샘플 공급 일정 확인"
            bullets.append("• 확인된 사실: HBM4E 샘플 공급·출하 단계에 관한 일정이 확인됐습니다.")
            verdict = "🟡 샘플 출하는 개발 진척 신호지만 고객 인증 완료나 매출 인식과 동일하지 않습니다."
        else:
            return None

    elif cat == "rubin_spec" and "rubin ultra" in low:
        capacities = [x for x in ("192GB", "288GB", "768GB", "1TB") if x.lower() in low]
        if not capacities:
            return None
        cap = "/".join(capacities)
        fact_key = "rubin_ultra_spec_" + "_".join(x.lower() for x in capacities)
        headline = f"Rubin Ultra HBM 사양 변화 감지 — {cap}"
        bullets.append(f"• 확인된 사양 후보: {cap}")
        if "8-hi" in low or "8hi" in low:
            bullets.append("• 적층 후보: 8단 HBM 구성이 언급됐습니다.")
        if "12-hi" in low or "12hi" in low:
            bullets.append("• 적층 후보: 12단 HBM 구성이 언급됐습니다.")
        bw = re.findall(r"\d+(?:\.\d+)?\s*TB/s", text, re.I)
        if bw:
            bullets.append(f"• 대역폭: {', '.join(dict.fromkeys(bw))}")
        if "192gb" in low:
            bullets.append(f"• 숫자: 288GB→192GB면 GPU당 HBM은 -33.3%, 총 비트 수요 상쇄에는 GPU 출하 +{BREAKEVEN_GPU_GROWTH*100:.0f}%가 필요합니다.")
            verdict = "🟡 192GB만으로 수요 붕괴 판정 금지. 최종 사양·대역폭·GPU 총출하를 함께 확인해야 합니다."
        else:
            verdict = "🟡 공급망 사양 정보입니다. NVIDIA 공식 확정 여부를 별도로 확인합니다."

    elif cat == "rubin_shipments" and ("rubin ultra" in low or "nvl576" in low):
        if not any(k in low for k in ("shipment", "ship", "deployment", "order", "production", "ramp", "출하", "도입", "주문", "양산")):
            return None
        fact_key = "rubin_ultra_nvl576_shipments_" + "_".join(re.findall(r"20\d{2}", text)[:1])
        headline = "Rubin Ultra·NVL576 출하·도입 변화 확인"
        bullets.append("• 확인된 사실: Rubin Ultra 또는 NVL576의 출하·도입·양산 일정 변화가 기사에서 명시됐습니다.")
        numbers = re.findall(r"\b\d{2,6}\s*(?:GPU|GPUs|대)\b", text, re.I)
        if numbers:
            bullets.append(f"• 물량 단서: {', '.join(dict.fromkeys(numbers))}")
        bullets.append(f"• 상쇄선: GPU당 HBM이 288GB→192GB로 줄면 전체 HBM 비트를 유지하려면 GPU 출하가 최소 +{BREAKEVEN_GPU_GROWTH*100:.0f}% 늘어야 합니다.")
        verdict = "🟢 실제 출하·고객 도입 확대면 HBM 총수요 판단에 직접 반영합니다. 단순 로드맵 재언급은 제외합니다."

    elif cat == "hbm_2027_contract" and "2027" in low and "hbm" in low:
        pcts = pct_tokens(text)
        has_price = any(k in low for k in ("price", "pricing", "asp", "가격", "판가"))
        has_volume = any(k in low for k in ("volume", "allocation", "supply", "contract", "lta", "물량", "공급", "계약"))
        if not (has_price or has_volume) or not pcts:
            return None
        fact_key = "hbm_2027_contract_" + "_".join(p.replace("%", "pct") for p in pcts[:3])
        headline = f"2027 HBM 계약가격·물량 변화 — {' / '.join(pcts[:3])}"
        if has_price:
            bullets.append(f"• 가격: 기사에서 2027년 HBM 가격·평균판매단가 관련 수치 {' / '.join(pcts[:3])}가 제시됐습니다.")
        if has_volume:
            bullets.append("• 물량: 계약물량·공급배정이 유지 또는 증가하는지 반드시 가격과 함께 판정합니다.")
        verdict = "🟢 가격 상승과 계약물량 유지·증가가 동시에 확인되면 강한 호재. 가격만 오르고 물량이 줄면 별도 계산합니다."

    elif cat == "memory_migration":
        if "hbm3e" in low and "ddr5" in low and ("3x" in low or "3 x" in low or "three times" in low or "3배" in low):
            fact_key = "hbm3e_wafer_capacity_3x_ddr5"
            headline = "Micron: HBM3E가 DDR5보다 웨이퍼 생산능력을 약 3배 더 소모"
            bullets.append("• 확인된 사실: HBM3E는 같은 비트 생산 기준으로 DDR5보다 웨이퍼 생산능력을 약 3배 더 소모한다는 설명입니다.")
            bullets.append("• 의미: HBM 세대가 올라갈수록 웨이퍼 투입 부담이 커져, 공급 확대 속도가 비트 수요 증가를 따라가기 어려울 수 있습니다.")
            verdict = "🟢 HBM 공급 제약과 가격결정력을 뒷받침하는 신호. 다만 DDR5·SOCAMM2·eSSD 수요 이동과는 별개의 공급효율 이슈입니다."
        elif "socamm2" in low and any(k in low for k in ("mass production", "shipment", "supply", "order", "양산", "출하", "공급", "주문")):
            fact_key = "socamm2_demand_supply_" + "_".join(re.findall(r"20\d{2}", text)[:1])
            headline = "SOCAMM2 공급·주문 변화 확인"
            bullets.append("• 확인된 사실: SOCAMM2의 양산·출하·공급 또는 주문 변화가 기사에서 명시됐습니다.")
            verdict = "🟢 HBM 밖으로 내려가는 대용량 메모리 계층 수요가 실제 주문으로 연결되는지 확인하는 긍정 신호입니다."
        elif any(k in low for k in ("enterprise ssd", "essd")) and any(k in low for k in ("demand", "order", "shipment", "supply", "수요", "주문", "출하", "공급")):
            fact_key = "enterprise_ssd_ai_demand_" + "_".join(re.findall(r"20\d{2}", text)[:1])
            headline = "기업용 eSSD AI 수요·주문 변화 확인"
            bullets.append("• 확인된 사실: 기업용 eSSD의 AI 관련 수요·주문·출하 변화가 기사에서 명시됐습니다.")
            verdict = "🟢 HBM 용량 보완 계층으로 기업용 SSD 수요가 실제 증가하는지 확인하는 신호입니다."
        else:
            return None
    else:
        return None

    e["fact_key"] = fact_key
    e["headline_ko"] = headline
    e["fact_bullets"] = bullets
    e["verdict"] = verdict
    return e


def fact_signature_from_raw(event: dict) -> str:
    text = f"{event.get('title','')} {event.get('description','')}".lower()
    cat = event.get("category") or ""
    if "hbm4e" in text and "indiana" in text and "2029" in text and "sk hynix" in text:
        return "skhynix_indiana_hbm4e_2029"
    if "hbm3e" in text and "ddr5" in text and ("3x" in text or "three times" in text or "3배" in text):
        return "hbm3e_wafer_capacity_3x_ddr5"
    if cat == "rubin_spec" and "rubin ultra" in text:
        caps = [x for x in ("192gb", "288gb", "768gb", "1tb") if x in text]
        if caps:
            return "rubin_ultra_spec_" + "_".join(caps)
    if cat == "hbm_2027_contract" and "2027" in text:
        pcts = re.findall(r"[+-]?\d+(?:\.\d+)?%", text)
        if pcts:
            return "hbm_2027_contract_" + "_".join(p.replace("%", "pct") for p in pcts[:3])
    return ""


def verification_for(event: dict, raw_events: list[dict]) -> str:
    quality = event.get("quality") or ""
    origin = event.get("origin_source") or ""
    if quality.startswith("공식"):
        return "공식자료 확인"
    if "Reuters" in origin:
        return "Reuters 원문/재전재 확인"
    if quality.startswith("신뢰"):
        return "신뢰 보도 확인"

    key = event.get("fact_key") or ""
    if not key:
        return ""
    sources = set()
    for raw in raw_events:
        if fact_signature_from_raw(raw) == key:
            sources.add((raw.get("source") or "").lower())
    sources.discard("")
    if len(sources) >= 2:
        return f"교차검증 {len(sources)}곳"
    return ""


def choose_verified_events(fresh_unseen: list[dict], raw_events: list[dict], seen_fact_keys: set[str]) -> tuple[list[dict], list[str]]:
    errors: list[str] = []
    candidates: list[dict] = []
    for raw in fresh_unseen:
        source_low = (raw.get("source") or "").lower()
        if any(k in source_low for k in LOW_VALUE_SOURCE_HINTS):
            # 저품질 집계 사이트는 단독 발송 금지. 같은 사실의 더 나은 출처가 있으면 그쪽을 사용한다.
            continue
        enriched = enrich_event(raw)
        if not enriched.get("link_verified"):
            errors.append(f"원문 URL 확인 실패: {raw.get('source')} | {raw.get('title')}")
            continue
        fact = make_fact(enriched)
        if not fact:
            errors.append(f"핵심 사실 자동추출 실패로 발송 제외: {raw.get('source')} | {raw.get('title')}")
            continue
        if fact.get("fact_key") in seen_fact_keys:
            continue
        verification = verification_for(fact, raw_events)
        if not verification:
            errors.append(f"교차검증 부족으로 발송 제외: {raw.get('source')} | {raw.get('title')}")
            continue
        fact["verification"] = verification
        candidates.append(fact)

    # 같은 사실이 여러 매체에 재전재된 경우 가장 좋은 출처 한 건만 남긴다.
    chosen: dict[str, dict] = {}
    for e in candidates:
        key = e.get("fact_key") or normalized_title(e.get("headline_ko") or e.get("title") or "")
        old = chosen.get(key)
        if old is None:
            chosen[key] = e
            continue
        if quality_rank(e.get("quality") or "") > quality_rank(old.get("quality") or ""):
            chosen[key] = e
        elif quality_rank(e.get("quality") or "") == quality_rank(old.get("quality") or "") and (e.get("published_at_kst") or "") > (old.get("published_at_kst") or ""):
            chosen[key] = e
    return sorted(chosen.values(), key=lambda x: x.get("published_at_kst") or ""), errors


def fetch_fx() -> dict:
    result = {"rate": None, "date": "", "error": ""}
    try:
        obj = json.loads(fetch(FX_URL).decode("utf-8"))
        result["rate"] = float(obj.get("rate"))
        result["date"] = str(obj.get("date") or "")
    except Exception as e:
        result["error"] = f"USD/KRW 조회 실패: {type(e).__name__}: {e}"
    return result


def load_state() -> tuple[dict, bool]:
    if not DATA.exists():
        return {}, True
    try:
        return json.loads(DATA.read_text(encoding="utf-8")), False
    except Exception:
        return {}, True


def write_json(path: pathlib.Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fmt_krw_usd(value: float, rate: float | None) -> str:
    if rate is None:
        return "원화 환산 불가"
    won = value * rate
    return f"약 {won:,.0f}원"


def krw_large_usd(value: float, rate: float | None) -> str:
    if rate is None:
        return "원화 환산 불가"
    won = value * rate
    eok = int(round(won / 100_000_000))
    if eok >= 10000:
        jo, rem = divmod(eok, 10000)
        return f"약 {jo:,}조{rem:,}억원" if rem else f"약 {jo:,}조원"
    return f"약 {eok:,}억원"


def extract_price_notes(text: str, rate: float | None) -> list[str]:
    notes: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*/\s*(GB|Gb)", text, re.I):
        usd = float(m.group(1))
        unit = m.group(2)
        key = f"{usd}/{unit}"
        if key not in seen:
            seen.add(key)
            notes.append(f"• 가격 환산: ${usd:g}/{unit} = {fmt_krw_usd(usd, rate)}/{unit}")
    for m in re.finditer(r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*(billion|million|B|M)\b", text, re.I):
        suffix = m.group(2).lower()
        val = float(m.group(1)) * (1_000_000_000 if suffix in ("b", "billion") else 1_000_000)
        key = f"{val}usd"
        if key not in seen:
            seen.add(key)
            notes.append(f"• 금액 환산: {m.group(0)} = {krw_large_usd(val, rate)}")
    return notes


def build_alert(now: datetime, events: list[dict], fx: dict) -> str:
    rate = fx.get("rate")
    lines = [
        "🚨 Rubin/HBM 구조 변화 감시",
        "",
        f"조회시각: {now.strftime('%Y-%m-%d %H:%M:%S KST')}",
        f"신규 핵심 변화: {len(events)}건",
        f"기준선: 일반 Rubin 288GB HBM4 / 디스펙 상쇄선 GPU 출하 +{BREAKEVEN_GPU_GROWTH*100:.0f}%",
    ]
    if rate is not None:
        lines.append(f"원화 환산: 1달러={rate:,.2f}원 / 기준일 {fx.get('date') or '미표시'}")

    grouped: dict[str, list[dict]] = {}
    for e in events:
        grouped.setdefault(e["category"], []).append(e)

    n = 1
    for category in ("rubin_spec", "hbm4e_validation", "rubin_shipments", "hbm_2027_contract", "memory_migration"):
        group = grouped.get(category) or []
        if not group:
            continue
        lines += ["", f"■ {CATEGORY_KO[category]}"]
        for e in group[:5]:
            full_text = compact_fact_text(e)
            lines += [
                f"{n}. {e['headline_ko']}",
                f"- 출처: {e.get('origin_source') or e.get('source')} / {e.get('verification')}",
                f"- 공개시각: {e.get('published_at_kst') or '확인 불가'}",
            ]
            lines.extend(e.get("fact_bullets") or [])
            lines += extract_price_notes(full_text, rate)
            lines.append(f"• 판정: {e.get('verdict')}")
            lines.append(f"- 원문: {e.get('direct_link')}")
            n += 1

    lines += [
        "",
        "■ 자동 판정 원칙",
        "• 원문 URL을 직접 확인하지 못한 기사는 발송하지 않습니다.",
        "• 일반 매체 단독 보도는 발송하지 않고 공식자료·Reuters·신뢰 매체 또는 2곳 이상 교차검증이 있어야 발송합니다.",
        "• 기사 제목만 전달하지 않고, 원문에서 확인된 핵심 사실·일정·물량·금액·판정을 함께 적습니다.",
        "• 192GB 확정만으로 HBM 수요 붕괴로 판정하지 않습니다.",
        f"• GPU당 288→192GB(-33.3%)일 때 GPU 출하가 +{BREAKEVEN_GPU_GROWTH*100:.0f}% 이상이면 총 HBM 비트 수요는 상쇄 가능합니다.",
    ]
    return "\n".join(lines).strip() + "\n"


def main() -> None:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    history_cutoff = now - timedelta(days=14)
    state, first_run = load_state()
    seen_before = set(state.get("seen_ids") or [])
    seen_fact_keys = set(state.get("seen_fact_keys") or [])

    raw_events_by_id: dict[str, dict] = {}
    errors: list[str] = []
    for category, query in QUERIES:
        for lang in ("en", "ko"):
            events, errs = read_feed(category, query, lang)
            errors.extend(errs)
            for e in events:
                try:
                    dt = datetime.fromisoformat(e["published_at_kst"])
                    if dt < history_cutoff:
                        continue
                except Exception:
                    pass
                raw_events_by_id[e["id"]] = e

    raw_events = sorted(raw_events_by_id.values(), key=lambda x: x.get("published_at_kst") or "")
    current_ids = {e["id"] for e in raw_events}
    unseen_raw = [e for e in raw_events if e["id"] not in seen_before]
    fresh_unseen = [e for e in unseen_raw if is_fresh_for_send(e, now)]

    verified_events, verify_errors = choose_verified_events(fresh_unseen, raw_events, seen_fact_keys)
    errors.extend(verify_errors)

    fx = fetch_fx()
    if fx.get("error"):
        errors.append(fx["error"])

    send_events = [] if first_run else verified_events
    send_events = send_events[-12:]
    new_fact_keys = {e.get("fact_key") for e in verified_events if e.get("fact_key")}

    # 첫 실행은 최근 기사들의 인식 가능한 사실키도 기준선에 저장해 재전재 폭탄을 막는다.
    if first_run:
        for raw in raw_events:
            key = fact_signature_from_raw(raw)
            if key:
                new_fact_keys.add(key)

    pending = {
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "seen_ids": sorted((seen_before | current_ids))[-1200:],
        "seen_fact_keys": sorted(seen_fact_keys | new_fact_keys)[-500:],
        "last_unseen_raw_count": len(unseen_raw),
        "last_verified_event_count": len(verified_events),
        "last_send_event_count": len(send_events),
        "freshness_hours": SEND_FRESHNESS_HOURS,
        "usdkrw": fx,
        "errors": errors,
    }
    write_json(OUT / "rubin_hbm_pending_state.json", pending)

    if first_run:
        (OUT / "rubin_hbm_rebaseline.txt").write_text(
            f"Initial verified baseline at {now.isoformat(timespec='seconds')}; {len(raw_events)} recent items stored; no Telegram alert sent.\n",
            encoding="utf-8",
        )

    if send_events:
        (OUT / "rubin_hbm_alert.md").write_text(build_alert(now, send_events, fx), encoding="utf-8")

    status = [
        "# Rubin HBM Watch",
        f"- checked_at_kst: {now.isoformat(timespec='seconds')}",
        f"- first_run_baseline: {str(first_run).lower()}",
        f"- recent_raw_events: {len(raw_events)}",
        f"- unseen_raw_events: {len(unseen_raw)}",
        f"- verified_events: {len(verified_events)}",
        f"- send_events: {len(send_events)}",
        f"- freshness_hours: {SEND_FRESHNESS_HOURS}",
        f"- break_even_gpu_growth: {BREAKEVEN_GPU_GROWTH*100:.1f}%",
        f"- source_errors_or_suppressed: {len(errors)}",
    ]
    for e in errors[:12]:
        status.append(f"  - {e}")
    (OUT / "rubin_hbm_status.md").write_text("\n".join(status) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
