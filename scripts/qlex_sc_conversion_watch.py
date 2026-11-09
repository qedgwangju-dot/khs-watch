from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
UTC = dt.timezone.utc
STATE = Path("data/qlex_sc_conversion_watch_state.json")
OUT = Path("out")
PENDING = OUT / "qlex_sc_conversion_watch_state_pending.json"
ALERT = OUT / "qlex_sc_conversion_alert.md"
STATUS = OUT / "qlex_sc_conversion_status.md"
UA = "Mozilla/5.0 (compatible; QlexSCConversionWatch/2.0)"

DEDUPE_VERSION = 2
NEWS_MAX_AGE_DAYS = 7
BASE_CONVERSION = 10.5
BASE_QLEX_SALES_M = 463.0

QUERIES = [
    '"KEYTRUDA QLEX" conversion',
    '"KEYTRUDA QLEX" adoption',
    '"KEYTRUDA QLEX" uptake',
    '"KEYTRUDA QLEX" "gross sales"',
    '"KEYTRUDA QLEX" "Symphony Health"',
    '"KEYTRUDA SC" UBS Symphony',
    '"KEYTRUDA QLEX" sales Merck',
    '"KEYTRUDA QLEX" milestone Alteogen',
    '"키트루다 큐렉스" 전환율',
    '"키트루다 큐렉스" 매출',
    '"Keytruda Qlex" CMS drug price negotiation',
    '알테오젠 키트루다 CMS 약가협상 규정',
]

QLEX_TERMS = (
    "keytruda qlex", "keytruda sc", "키트루다 큐렉스", "키트루다 sc",
    "키트루다 피하", "qlex",
)
CONVERSION_TERMS = (
    "conversion", "adoption", "uptake", "gross sales", "gross-sales", "prescription",
    "전환율", "전환", "채택률", "점유율", "처방",
)
ECONOMIC_TERMS = ("milestone", "royalty", "마일스톤", "로열티")
CMS_2029_FINAL_RULE_ID = "CMS|4215-F|FINAL|HYALURONIDASE_FIXED_COMBINATION|2029|2026-11-05"
CMS_2029_FINAL_RULE_URL = "https://www.cms.gov/newsroom/fact-sheets/medicare-drug-price-negotiation-program-medicare-prescription-drug-benefit-program-final-rule-cms"
CMS_2029_RULE_DATE = dt.date(2026, 11, 5)

# 유럽위원회 2026-10-21 최종 승인: 2026-06-24 시스플라틴 부적격자 승인의
# 단순 재보도가 아닌, 적격 여부 제한을 제거한 새 적응증 확대 사건.
# Merck 공식 원문과 2026-09-17 EMA CHMP 권고를 교차 검증한 기준선이다.
EU_MIBC_REGULATORY_EVENT_ID = "EC|KEYTRUDA_SC+PADCEV|MIBC|CISPLATIN_ALL|2026-10-21"
EU_MIBC_RELEASE_UTC = dt.datetime(2026, 10, 21, 10, 45, tzinfo=UTC)
EU_MIBC_MERCK_URL = (
    "https://www.merck.com/news/"
    "european-commission-approves-keytruda-pembrolizumab-plus-padcev-enfortumab-vedotin-ejfv-"
    "as-perioperative-treatment-for-adults-with-resectable-muscle-invasive-bladder-cancer-mibc/"
)
EU_MIBC_EMA_URL = "https://www.ema.europa.eu/en/medicines/human/variation/keytruda-1"
EU_MIBC_EUROPE_INJUNCTION_URL = (
    "https://ir.halozyme.com/news/news-details/2026/"
    "Halozyme-Wins-Injunction-Stopping-Manufacture-and-Sale-of-Mercks-Keytruda-SC-in-"
    "Multiple-European-Markets/default.aspx"
)



def cms_final_rule_signal(state: dict) -> tuple[bool, str]:
    """Verify the exact CMS policy event before the initial and only alert.

    News headlines never certify a final regulation. A failed official fetch
    leaves the event unacknowledged for the next scheduled check.
    """
    if CMS_2029_FINAL_RULE_ID in set(state.get("seen_regulatory_events") or []):
        return False, "previously_delivered"
    if dt.datetime.now(KST).date() < CMS_2029_RULE_DATE:
        return False, "before_official_date"
    try:
        body = strip_html(fetch(CMS_2029_FINAL_RULE_URL, timeout=20)).lower()
    except Exception as exc:
        return False, "official_fetch_failed:" + type(exc).__name__
    required = (
        "cms-4215-f", "nov", "2026", "2029", "hyaluronidase",
        "active ingredient", "same", "new formulation",
    )
    if not all(term in body for term in required):
        return False, "official_content_unverified"
    if not re.search(r"(?:nov|november)\s*0?5,\s*2026", body):
        return False, "official_publication_date_unverified"
    return True, "official_final_verified"


def cms_final_rule_lines() -> list[str]:
    return [
        "[바이오 감시] 중요 규제 확정 — 알테오젠·키트루다SC 미국 약가협상",
        "",
        "**2026년 11월 5일** 미국 메디케어·메디케이드서비스센터(CMS)가 약가협상 최종 규정(CMS-4215-F)을 발표했습니다.",
        "",
        "■ **무엇이 달라졌나:** 동일한 의약품 허가권자가 기존 주성분에 히알루로니다제 등을 추가해 투여 경로를 바꾼 일부 복합제형은 원래 제형과 묶어 약가협상 대상 여부를 판단합니다.",
        "■ **사업 영향:** 키트루다 정맥주사와 알테오젠 ALT-B4가 적용된 키트루다SC의 약가협상 대상 선정 시점을 별도로 늦출 수 있다는 기대가 약해졌습니다. 실제로 가격이 인하되면 MSD의 판매실적과 알테오젠의 판매 연동 마일스톤·로열티에도 영향을 줄 수 있습니다.",
        "■ **확정 단계 구분:** 이번에 확정된 것은 대상 선정 기준입니다. 키트루다SC가 이미 협상 대상에 선정됐거나 판매가격·알테오젠 로열티가 특정 비율만큼 인하됐다는 뜻은 아닙니다.",
        "■ **회사 입장:** 알테오젠은 환자 편의성과 별도 제품 특허에 따른 피하주사 전환 수요가 유지된다고 설명했습니다. 이는 회사 평가이며 약가협상 영향 확정치가 아닙니다.",
        "■ **시장 반응:** **2026년 11월 9일** 오전 10시 25분 알테오젠은 전 거래일 대비 20.95% 하락했으며, 장중 최대 하락폭은 23.94%로 보도됐습니다. 장중 수치로 종가는 아닙니다.",
        "",
        "**핵심 일정**",
        "• **2026년 6월 16일** 관련 규칙 제안",
        "• **2026년 11월 5일** 최종 규정 공표",
        "• **2026년 12월 5일** 규정 시행",
        "• **2027년 2월 1일까지** 2029년 가격 적용 대상 선정 예정",
        "• **2029년** 해당 주기에 선정된 의약품의 협상 가격 적용 시작",
        "",
        "■ **다음 확인:** CMS 실제 선정 목록, 키트루다 정맥·피하주사 묶음 판단, 최종 순판매가격, MSD 판매실적, 알테오젠 마일스톤·로열티, 유럽 특허분쟁 진행을 각각 구분해 추적합니다.",
        "- 미국 CMS 공식 최종 규정: " + CMS_2029_FINAL_RULE_URL,
        "- 관련 시장 보도: https://www.mt.co.kr/stock/2026/11/09/2026110910384710612",
        "- 알테오젠 공식 투자정보: https://alteogen.com/kr/sub/ir/information.php",
    ]

def eu_mibc_approval_due(state: dict, now_utc: dt.datetime | None = None) -> bool:
    now = now_utc if now_utc is not None else dt.datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("유럽 허가 알림 시각은 시간대가 있어야 합니다")
    return (
        now.astimezone(UTC) >= EU_MIBC_RELEASE_UTC
        and EU_MIBC_REGULATORY_EVENT_ID not in set(state.get("seen_regulatory_events") or [])
    )


def eu_mibc_regulatory_lines() -> list[str]:
    # Telegram 송신기는 **날짜**를 HTML 굵게 표시로 변환한다.
    # 당국의 적응증 승인과 법원의 별도 특허금지명령, 실제 판매·급여를 혼동하지 않는다.
    return [
        "[바이오 감시] KEYTRUDA SC 유럽 방광암 적응증 확대 승인",
        "",
        "**유럽위원회, Keytruda+Padcev 병용 수술 전후 치료의 시스플라틴 적격 제한 해제**",
        "",
        "- **변화:** 6월에는 시스플라틴 화학요법 부적격 환자만 허가됐지만, 10월에는 적격 여부에 관계없이 절제 가능한 근육 침습성 방광암(MIBC) 성인으로 확대됐습니다.",
        "- **제형:** Keytruda 정맥주사와 Keytruda SC(미국명 Keytruda Qlex, 알테오젠 ALT-B4 기반)를 포함합니다. Padcev는 항체약물접합체입니다.",
        "- **허가 범위:** 유럽연합 27개 회원국과 아이슬란드·리히텐슈타인·노르웨이. 각국 급여·실제 판매 개시는 별도입니다.",
        "- **3상 근거:** KEYNOTE-B15/EV-304에서 무사건생존 관련 사건 위험 47% 감소(위험비 0.53), 사망 위험 35% 감소(위험비 0.65), 병리학적 완전관해율 55.8% 대 32.5%. 이 임상은 정맥주사 Keytruda+Padcev 비교이며 Keytruda SC만의 직접 비교시험으로 해석하지 않습니다.",
        "",
        "- **타임라인:**",
        "• **2026년 6월 24일** 시스플라틴 부적격 환자 대상 유럽 병용요법 승인",
        "• **2026년 9월 17일** 유럽의약품청 적격 제한 삭제 긍정 의견",
        "• **2026년 10월 7일** 별도 EP622 특허분쟁으로 유럽 8개국 Keytruda SC 금지명령",
        "• **2026년 10월 21일** 적격 여부 제한 없는 유럽위원회 확대 승인",
        "",
        "- **법적 역풍:** 허가 확대는 기존 EP622 특허 금지명령의 집행정지·취소가 아닙니다. 네덜란드·벨기에·덴마크·프랑스·아일랜드·이탈리아·스웨덴·스위스의 Keytruda SC 제조·판매 등 제한은 별도 법원 절차로 추적합니다.",
        "- **매출 연결:** 적응증 확대 → 국가별 급여 → 특허 자유실시·출하 → 실제 판매 → 알테오젠 판매 마일스톤·로열티 순서입니다. 이번 허가만으로 원화 매출이나 마일스톤 확정액을 만들지 않습니다.",
        "- **확정 당사자:** Merck/MSD(Keytruda SC), 화이자·아스텔라스(Padcev 공동개발·사업), 알테오젠(ALT-B4 공급·사용권), Halozyme(별도 MDASE 특허분쟁).",
        "- **다음 확인:** 국가별 출시·급여·특허 집행정지 및 항소, 유럽 Keytruda SC 판매와 알테오젠 수익인식.",
        f"- 원문: {EU_MIBC_MERCK_URL}",
        f"- 원문: {EU_MIBC_EMA_URL}",
        f"- 원문: {EU_MIBC_EUROPE_INJUNCTION_URL}",
    ]


@dataclass
class Item:
    source: str
    title: str
    url: str
    published: str = ""
    text: str = ""

    @property
    def full(self) -> str:
        return f"{self.title} {self.text}".strip()

    @property
    def canonical_url(self) -> str:
        return canonicalize_url(self.url)

    @property
    def title_key(self) -> str:
        return normalize_title(self.title)

    @property
    def published_day(self) -> str:
        stamp = parse_published(self.published)
        return stamp.date().isoformat() if stamp else ""

    @property
    def fingerprint(self) -> str:
        raw = f"{self.canonical_url}|{self.title_key}|{self.published_day}"
        return digest(raw)

    @property
    def story_key(self) -> str:
        # Stable even when Bing changes redirect query parameters.
        raw = f"{self.title_key}|{self.published_day}"
        return digest(raw)

    @property
    def semantic_key(self) -> str:
        # Suppresses the same story/numbers even if it is re-syndicated with another URL/date.
        nums = "|".join(metric_tokens(self.full))
        return digest(f"{self.title_key}|{nums}")


class Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[tuple[str, str]] = []
        self.href: str | None = None
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self.href = dict(attrs).get("href")
            self.parts = []

    def handle_data(self, data):
        if self.href is not None:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.href is not None:
            title = re.sub(r"\s+", " ", " ".join(self.parts)).strip()
            self.rows.append((self.href, title))
            self.href = None
            self.parts = []


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def normalize_title(value: str) -> str:
    value = html.unescape(value).lower()
    value = re.sub(r"\s+-\s+(?:reuters|msn|yahoo.*|bloomberg.*)$", "", value, flags=re.I)
    value = re.sub(r"[^0-9a-z가-힣]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def canonicalize_url(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(html.unescape(url))
        host = parsed.netloc.lower()
        if host.endswith("bing.com") and parsed.path.endswith("/news/apiclick.aspx"):
            target = urllib.parse.parse_qs(parsed.query).get("url", [""])[0]
            if target.startswith(("http://", "https://")):
                return canonicalize_url(target)
        query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)
        query = [
            (k, v) for k, v in query
            if not k.lower().startswith("utm_")
            and k.lower() not in {"ref", "referrer", "source", "ocid", "cmpid", "cid"}
        ]
        return urllib.parse.urlunparse((
            parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), "",
            urllib.parse.urlencode(query, doseq=True), ""
        ))
    except Exception:
        return url


def parse_published(value: str) -> dt.datetime | None:
    if not value:
        return None
    try:
        stamp = parsedate_to_datetime(value)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=UTC)
        return stamp.astimezone(UTC)
    except Exception:
        return None


def is_recent_news(item: Item) -> bool:
    if item.source not in ("Google News", "Bing News"):
        return True
    stamp = parse_published(item.published)
    if stamp is None:
        return True
    age = dt.datetime.now(UTC) - stamp
    return age <= dt.timedelta(days=NEWS_MAX_AGE_DAYS) and age >= dt.timedelta(days=-1)


def fetch(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9,ko;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = response.read()
        enc = response.headers.get_content_charset() or "utf-8"
    return data.decode(enc, errors="replace")


def strip_html(value: str) -> str:
    value = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", value)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def rss(query: str, engine: str) -> list[Item]:
    if engine == "Google News":
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({
            "q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"
        })
    else:
        url = "https://www.bing.com/news/search?" + urllib.parse.urlencode({"q": query, "format": "rss"})
    root = ET.fromstring(fetch(url))
    out: list[Item] = []
    for node in root.findall(".//item")[:30]:
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        pub = (node.findtext("pubDate") or "").strip()
        desc = strip_html(node.findtext("description") or "")
        if link:
            out.append(Item(engine, title, link, pub, desc))
    return out


def official_links(base: str, source: str) -> list[Item]:
    parser = Links()
    parser.feed(fetch(base))
    out: list[Item] = []
    seen: set[str] = set()
    for href, title in parser.rows:
        if not href:
            continue
        url = urllib.parse.urljoin(base, html.unescape(href))
        low = f"{url} {title}".lower()
        if source == "Merck 공식":
            ok = "/news/" in url and any(k in low for k in ("keytruda", "financial-results", "earnings", "quarter"))
        else:
            ok = "idx=" in url and any(k in low for k in ("키트루다", "qlex", "msd", "머크", "피하", "sc"))
        canonical = canonicalize_url(url)
        if ok and canonical not in seen:
            seen.add(canonical)
            out.append(Item(source, title or url, canonical))
    return out[:50]


def enrich(item: Item) -> Item:
    if item.source in ("Google News", "Bing News"):
        return item
    try:
        item.text = strip_html(fetch(item.url))[:35000]
    except Exception:
        pass
    return item


def metric_tokens(text: str) -> list[str]:
    values: list[str] = []
    patterns = (
        r"\b\d{1,3}(?:\.\d+)?\s*%",
        r"\$\s*\d+(?:\.\d+)?\s*(?:m|mn|million|bn|billion)\b",
        r"\b\d+(?:\.\d+)?\s*(?:억|조)원",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.I):
            value = re.sub(r"\s+", " ", match.group(0)).strip().lower()
            if value not in values:
                values.append(value)
    return values[:12]


def qlex_sales_m(text: str) -> float | None:
    patterns = (
        r"keytruda qlex[^$]{0,180}\$\s*([0-9]+(?:\.[0-9]+)?)\s*(?:m|mn|million)\b",
        r"qlex[^$]{0,120}\$\s*([0-9]+(?:\.[0-9]+)?)\s*(?:m|mn|million)\b",
        r"keytruda qlex[^0-9]{0,180}([0-9]+(?:\.[0-9]+)?)\s*million",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return float(match.group(1))
    return None


# An article's stock-price change must never become a drug conversion percentage.
_PRICE_CONTEXT_RE = re.compile(
    r"주가|주식|주당|시가총액|급락|폭락|하락|상승|코스닥|코스피|"
    r"\bstock\b|\bshare price\b|\bshares\b|\bslump\b|\bplunge\b|\bdecline\b",
    re.I,
)
_CONVERSION_LABEL = (
    r"(?:conversion(?:\s+rate)?|adoption(?:\s+rate)?|uptake(?:\s+rate)?|"
    r"penetration(?:\s+rate)?|전환율|채택률|처방\s*비중|"
    r"매출\s*비중|판매\s*비중|시장\s*점유율)"
)
_PCT = r"(\d{1,3}(?:\.\d+)?)\s*%"


def conversion_pct(text: str) -> float | None:
    if not any(k in text.lower() for k in QLEX_TERMS):
        return None
    patterns = (
        rf"{_CONVERSION_LABEL}[^\n.!?]{{0,65}}?{_PCT}",
        rf"{_PCT}[^\n.!?]{{0,65}}?{_CONVERSION_LABEL}",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.I):
            if _PRICE_CONTEXT_RE.search(match.group(0)):
                continue
            value = float(match.group(1))
            if 0 <= value <= 100:
                return value
    return None


def economic_metric(text: str) -> bool:
    """Only monetary/royalty-rate figures close to QLEX economics qualify."""
    labels = r"(?:royalt(?:y|ies)|milestones?|로열티|마일스톤)"
    amount = (
        r"(?:\$\s*\d+(?:\.\d+)?\s*(?:m|mn|million|bn|billion)\b|"
        r"\d+(?:\.\d+)?\s*(?:억|조)\s*(?:원|달러)|"
        r"\d+(?:\.\d+)?\s*%)"
    )
    for pattern in (rf"{labels}[^\n.!?]{{0,55}}?{amount}", rf"{amount}[^\n.!?]{{0,55}}?{labels}"):
        for match in re.finditer(pattern, text, re.I):
            # The percentage may precede "royalty" but belong to a stock
            # plunge in the headline; check the number's preceding context too.
            nearby = text[max(0, match.start() - 100):match.end() + 30]
            if not _PRICE_CONTEXT_RE.search(nearby):
                return True
    return False


def relevant(item: Item) -> bool:
    text = item.full
    if not any(k in text.lower() for k in QLEX_TERMS):
        return False
    return conversion_pct(text) is not None or qlex_sales_m(text) is not None or economic_metric(text)


def usdkrw() -> tuple[float | None, str]:
    try:
        payload = json.loads(fetch("https://api.frankfurter.app/latest?from=USD&to=KRW"))
        return float(payload["rates"]["KRW"]), str(payload.get("date") or "")
    except Exception:
        return None, ""


def krw(usd_m: float) -> str:
    rate, day = usdkrw()
    if rate is None:
        return "원화 환산 확인 불가"
    won = usd_m * 1_000_000 * rate
    if won >= 1_000_000_000_000:
        result = f"약 {won/1_000_000_000_000:.2f}조원"
    else:
        result = f"약 {won/100_000_000:.0f}억원"
    return f"{result} (USD/KRW {rate:,.2f}, {day}, ECB-derived)"


def load_state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "dedupe_version": DEDUPE_VERSION,
        "seen_fingerprints": [],
        "seen_story_keys": [],
        "seen_semantic_keys": [],
        "last_conversion": BASE_CONVERSION,
        "last_qlex_sales_m": BASE_QLEX_SALES_M,
        "initialized_at_kst": None,
    }


def write_pending(state: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    PENDING.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def collect() -> list[Item]:
    items: list[Item] = []
    errors: list[str] = []
    official = [
        ("https://www.merck.com/media/news/", "Merck 공식"),
        ("https://www.alteogen.com/kr/sub/ir/news.php?bid=1", "Alteogen 공식"),
        ("https://www.alteogen.com/kr/sub/ir/information.php?bid=2", "Alteogen 공식"),
    ]
    for url, source in official:
        try:
            items.extend(official_links(url, source))
        except Exception as exc:
            errors.append(f"{source}: {exc}")
    for query in QUERIES:
        for engine in ("Google News", "Bing News"):
            try:
                items.extend(rss(query, engine))
            except Exception as exc:
                errors.append(f"{engine} {query}: {exc}")

    unique: dict[str, Item] = {}
    for item in items:
        # Canonical URL + title/date dedupes multiple query results in the same poll.
        key = item.story_key or item.fingerprint
        unique.setdefault(key, item)
    if errors:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "qlex_sc_conversion_errors.log").write_text("\n".join(errors) + "\n", encoding="utf-8")
    return list(unique.values())


def cap(values: set[str], limit: int = 5000) -> list[str]:
    return sorted(values)[-limit:]


def migrate_state(items: list[Item], state: dict) -> None:
    now = dt.datetime.now(KST).isoformat(timespec="seconds")
    state = dict(state)
    state["dedupe_version"] = DEDUPE_VERSION
    state["seen_fingerprints"] = cap({item.fingerprint for item in items})
    state["seen_story_keys"] = cap({item.story_key for item in items})
    state["seen_semantic_keys"] = cap({item.semantic_key for item in items if metric_tokens(item.full)})
    state["last_conversion"] = state.get("last_conversion", BASE_CONVERSION)
    state["last_qlex_sales_m"] = state.get("last_qlex_sales_m", BASE_QLEX_SALES_M)
    state["initialized_at_kst"] = state.get("initialized_at_kst") or now
    state["last_check_kst"] = now
    write_pending(state)
    STATUS.write_text(
        f"migration=true dedupe_version={DEDUPE_VERSION} seeded_items={len(items)} alert=false at={now}\n",
        encoding="utf-8",
    )


def check(items: list[Item], state: dict) -> None:
    if int(state.get("dedupe_version", 0) or 0) != DEDUPE_VERSION:
        migrate_state(items, state)
        return

    seen_fp = set(state.get("seen_fingerprints", []))
    seen_story = set(state.get("seen_story_keys", []))
    seen_semantic = set(state.get("seen_semantic_keys", []))
    regulatory_due = eu_mibc_approval_due(state)
    cms_rule_due, cms_policy_status = cms_final_rule_signal(state)

    fresh: list[Item] = []
    silent: list[Item] = []
    for item in items:
        if item.fingerprint in seen_fp or item.story_key in seen_story or item.semantic_key in seen_semantic:
            continue
        if not is_recent_news(item):
            silent.append(item)
            continue
        item = enrich(item)
        if relevant(item):
            fresh.append(item)
        else:
            silent.append(item)

    # Limit delivery to six distinct stories, but never mark overflow as delivered.
    # Unrelated articles can be suppressed; eligible overflow stays pending until
    # a later real Telegram send confirms its state.
    chosen: list[Item] = []
    semantic_in_report: set[str] = set()
    for item in fresh:
        if item.semantic_key in semantic_in_report:
            continue
        semantic_in_report.add(item.semantic_key)
        chosen.append(item)
        if len(chosen) >= 6:
            break

    processed = silent + [item for item in fresh if item.semantic_key in semantic_in_report]
    pending = dict(state)
    for item in processed:
        seen_fp.add(item.fingerprint)
        seen_story.add(item.story_key)
        if metric_tokens(item.full):
            seen_semantic.add(item.semantic_key)
    pending["seen_fingerprints"] = cap(seen_fp)
    pending["seen_story_keys"] = cap(seen_story)
    pending["seen_semantic_keys"] = cap(seen_semantic)
    pending["last_check_kst"] = dt.datetime.now(KST).isoformat(timespec="seconds")
    pending["cms_policy_status"] = cms_policy_status

    if not fresh and not regulatory_due and not cms_rule_due:
        write_pending(pending)
        STATUS.write_text(
            f"changed=false fresh_alerts=0 cms_policy_status={cms_policy_status} "
            f"stale_or_irrelevant={len(silent)} at={pending['last_check_kst']}\n",
            encoding="utf-8",
        )
        return

    lines = cms_final_rule_lines() if cms_rule_due else []
    if regulatory_due:
        lines += (["", ""] if lines else []) + eu_mibc_regulatory_lines()
    if not lines:
        lines = ["[바이오 감시] KEYTRUDA QLEX 새 데이터", ""]
    if cms_rule_due:
        seen = set(pending.get("seen_regulatory_events") or [])
        seen.add(CMS_2029_FINAL_RULE_ID)
        pending["seen_regulatory_events"] = sorted(seen)[-200:]
        pending["last_cms_policy_source_url"] = CMS_2029_FINAL_RULE_URL
        pending["last_cms_policy_event_date"] = CMS_2029_RULE_DATE.isoformat()
    if regulatory_due:
        existing = set(pending.get("seen_regulatory_events") or [])
        existing.add(EU_MIBC_REGULATORY_EVENT_ID)
        pending["seen_regulatory_events"] = sorted(existing)[-200:]
        pending["last_regulatory_source_url"] = EU_MIBC_MERCK_URL
        pending["last_regulatory_release_kst"] = "2026-10-21T19:45:00+09:00"
        if chosen:
            lines += ["", "**같은 실행에서 확인된 QLEX 신규 수치**", ""]
    for number, item in enumerate(chosen, 1):
        text = item.full
        low = text.lower()
        conv = conversion_pct(text)
        sales = qlex_sales_m(text)
        values = metric_tokens(text)
        lines.append(f"{number}) {item.title}")
        source_date = item.published_day or item.published
        lines.append(f"- 출처: {item.source}" + (f" / {source_date}" if source_date else ""))
        if values and not _PRICE_CONTEXT_RE.search(item.title):
            lines.append("- 신규 숫자 후보(원문 정의 확인 필요): " + ", ".join(values))

        if conv is not None:
            old = float(pending.get("last_conversion", BASE_CONVERSION))
            if "gross sales" in low or "gross-sales" in low or "총판매액" in low:
                lines.append(
                    f"- 쉽게: 미국 IV+SC 총판매액을 100으로 볼 때 QLEX/SC가 {conv:.1f}을 차지한다는 뜻입니다. "
                    f"환자 100명 중 {conv:.1f}명이라는 뜻은 아닙니다."
                )
                lines.append(f"- 동일한 총판매액 기준 직전 {old:.1f}% 대비 {conv-old:+.1f}%p")
                pending["last_conversion"] = conv
            else:
                lines.append(
                    f"- 쉽게: QLEX 전환·채택 수치 {conv:.1f}%입니다. 환자 수·처방 건수·매출 중 어느 기준인지 원문 정의를 구분합니다."
                )

        if sales is not None:
            old_sales = float(pending.get("last_qlex_sales_m", BASE_QLEX_SALES_M))
            lines.append(f"- QLEX 매출 ${sales:.1f}m = {krw(sales)}")
            if old_sales > 0:
                lines.append(f"- 직전 공식 기준 ${old_sales:.1f}m 대비 {(sales/old_sales-1)*100:+.1f}%")
            lines.append(
                "- 이는 Merck 제품매출이며 Alteogen 매출 자체는 아닙니다. ALT-B4 판매 마일스톤·향후 로열티·상업 공급의 기반이 커지는 방향입니다."
            )
            if item.source == "Merck 공식":
                pending["last_qlex_sales_m"] = sales

        if "opdivo" in low or "tecentriq" in low:
            lines.append("- 경쟁 비교: Opdivo SC·Tecentriq SC는 QLEX와 동일 출시 후 개월(M+N) 기준으로 비교합니다.")
        if any(k in low for k in ECONOMIC_TERMS):
            lines.append("- Alteogen 실적: 판매 마일스톤은 일회성, 로열티·ALT-B4 공급은 반복성으로 분리합니다.")
        if item.source in ("Google News", "Bing News"):
            lines.append("- 시장/2차 자료: 공식자료로 교차확인 전에는 확정치로 승격하지 않습니다. 유료 원자료는 공개 인용값만 사용합니다.")
        lines.append(f"- 원문: {item.canonical_url}")
        lines.append("")

    if chosen:
        lines += [
            "판정",
            "- 총판매액 기준 전환율은 환자 수 기준 점유율과 다릅니다.",
            "- QLEX 전환율의 절대값보다 10.5% 이후 15%→20%→30~40%로 가는 기울기를 중점 추적합니다.",
            "- 동일 기사·동일 숫자는 URL이 바뀌거나 재인용돼도 다시 알리지 않습니다.",
        ]
    ALERT.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    write_pending(pending)
    STATUS.write_text(
        f"changed=true alerts={len(chosen)} regulatory_approval={'true' if regulatory_due else 'false'} "
        f"cms_final_rule={'true' if cms_rule_due else 'false'} cms_policy_status={cms_policy_status} "
        f"stale_or_irrelevant={len(silent)} at={pending['last_check_kst']}\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("baseline", "check"), default="check")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    for path in (ALERT, STATUS):
        if path.exists():
            path.unlink()
    state = load_state()
    items = collect()
    if args.mode == "baseline":
        migrate_state(items, state)
    else:
        check(items, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
