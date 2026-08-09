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


def conversion_pct(text: str) -> float | None:
    low = text.lower()
    if not any(k in low for k in CONVERSION_TERMS):
        return None
    for match in re.finditer(r"(\d{1,3}(?:\.\d+)?)\s*%", text):
        context = text[max(0, match.start()-250):min(len(text), match.end()+250)].lower()
        if any(k in context for k in QLEX_TERMS):
            return float(match.group(1))
    return None


def relevant(item: Item) -> bool:
    text = item.full
    low = text.lower()
    if not any(k in low for k in QLEX_TERMS):
        return False
    if not metric_tokens(text):
        return False
    # Accept only numbers tied to QLEX usage/sales or Alteogen economics.
    if any(k in low for k in CONVERSION_TERMS):
        return True
    if qlex_sales_m(text) is not None:
        return True
    if any(k in low for k in ECONOMIC_TERMS):
        return True
    return False


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

    pending = dict(state)
    for item in fresh + silent:
        seen_fp.add(item.fingerprint)
        seen_story.add(item.story_key)
        if metric_tokens(item.full):
            seen_semantic.add(item.semantic_key)
    pending["seen_fingerprints"] = cap(seen_fp)
    pending["seen_story_keys"] = cap(seen_story)
    pending["seen_semantic_keys"] = cap(seen_semantic)
    pending["last_check_kst"] = dt.datetime.now(KST).isoformat(timespec="seconds")

    if not fresh:
        write_pending(pending)
        STATUS.write_text(
            f"changed=false fresh_alerts=0 stale_or_irrelevant={len(silent)} at={pending['last_check_kst']}\n",
            encoding="utf-8",
        )
        return

    # One poll can still contain syndications of the same story. Semantic key prevents duplicate rows.
    chosen: list[Item] = []
    semantic_in_report: set[str] = set()
    for item in fresh:
        if item.semantic_key in semantic_in_report:
            continue
        semantic_in_report.add(item.semantic_key)
        chosen.append(item)
        if len(chosen) >= 6:
            break

    lines = ["[바이오 감시] KEYTRUDA QLEX 새 데이터", ""]
    for number, item in enumerate(chosen, 1):
        text = item.full
        low = text.lower()
        conv = conversion_pct(text)
        sales = qlex_sales_m(text)
        values = metric_tokens(text)
        lines.append(f"{number}) {item.title}")
        source_date = item.published_day or item.published
        lines.append(f"- 출처: {item.source}" + (f" / {source_date}" if source_date else ""))
        if values:
            lines.append("- 신규 숫자 후보: " + ", ".join(values))

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

    lines += [
        "판정",
        "- 총판매액 기준 전환율은 환자 수 기준 점유율과 다릅니다.",
        "- QLEX 전환율의 절대값보다 10.5% 이후 15%→20%→30~40%로 가는 기울기를 중점 추적합니다.",
        "- 동일 기사·동일 숫자는 URL이 바뀌거나 재인용돼도 다시 알리지 않습니다.",
    ]
    ALERT.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    write_pending(pending)
    STATUS.write_text(
        f"changed=true alerts={len(chosen)} stale_or_irrelevant={len(silent)} at={pending['last_check_kst']}\n",
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
