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
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
STATE = Path("data/qlex_sc_conversion_watch_state.json")
OUT = Path("out")
PENDING = OUT / "qlex_sc_conversion_watch_state_pending.json"
ALERT = OUT / "qlex_sc_conversion_alert.md"
SETUP = OUT / "qlex_sc_conversion_setup.md"
STATUS = OUT / "qlex_sc_conversion_status.md"
UA = "Mozilla/5.0 (compatible; QlexSCConversionWatch/1.0)"

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

PRODUCT_TERMS = (
    "keytruda qlex", "keytruda sc", "키트루다 큐렉스", "키트루다 sc",
    "berahyaluronidase", "alt-b4",
)
SIGNAL_TERMS = (
    "conversion", "adoption", "uptake", "share", "gross sales", "sales", "revenue",
    "symphony", "ubs", "bloomberg", "milestone", "royalty", "prescription", "trx",
    "전환율", "전환", "점유", "매출", "판매", "처방", "마일스톤", "로열티",
)


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
    def key(self) -> str:
        raw = f"{self.source}|{self.url}|{self.title}|{self.published}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


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
        if source == "Merck official":
            ok = "/news/" in url and any(k in low for k in ("keytruda", "financial-results", "earnings", "quarter"))
        else:
            ok = "idx=" in url and any(k in low for k in ("키트루다", "qlex", "alt-b4", "msd", "머크", "sc", "피하"))
        if ok and url not in seen:
            seen.add(url)
            out.append(Item(source, title or url, url))
    return out[:50]


def enrich(item: Item) -> Item:
    if item.source in ("Google News", "Bing News"):
        return item
    try:
        item.text = strip_html(fetch(item.url))[:35000]
    except Exception:
        pass
    return item


def relevant(text: str) -> bool:
    low = text.lower()
    if not any(k in low for k in PRODUCT_TERMS):
        return False
    if not any(k in low for k in SIGNAL_TERMS):
        return False
    return bool(
        re.search(r"\b\d{1,3}(?:\.\d+)?\s*%", text)
        or re.search(r"\$\s*\d+(?:\.\d+)?\s*(?:m|mn|million|bn|billion)\b", low)
        or re.search(r"\b\d+(?:\.\d+)?\s*(?:억|조)원", text)
    )


def metric_tokens(text: str) -> list[str]:
    values: list[str] = []
    for pattern in (
        r"\b\d{1,3}(?:\.\d+)?\s*%",
        r"\$\s*\d+(?:\.\d+)?\s*(?:m|mn|million|bn|billion)\b",
        r"\b\d+(?:\.\d+)?\s*(?:억|조)원",
    ):
        for match in re.finditer(pattern, text, re.I):
            value = re.sub(r"\s+", " ", match.group(0)).strip()
            if value not in values:
                values.append(value)
    return values[:12]


def conversion_pct(text: str) -> float | None:
    low = text.lower()
    if not any(k in low for k in ("conversion", "adoption", "uptake", "전환율", "전환", "점유")):
        return None
    for match in re.finditer(r"(\d{1,3}(?:\.\d+)?)\s*%", text):
        context = text[max(0, match.start()-250):min(len(text), match.end()+250)].lower()
        if any(k in context for k in ("keytruda", "qlex", "키트루다")):
            return float(match.group(1))
    return None


def qlex_sales_m(text: str) -> float | None:
    patterns = (
        r"keytruda qlex[^$]{0,180}\$\s*([0-9]+(?:\.[0-9]+)?)\s*(?:m|mn|million)\b",
        r"keytruda qlex[^0-9]{0,180}([0-9]+(?:\.[0-9]+)?)\s*million",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return float(match.group(1))
    return None


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
        "seen": [],
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
        ("https://www.merck.com/media/news/", "Merck official"),
        ("https://www.alteogen.com/kr/sub/ir/news.php?bid=1", "Alteogen official"),
        ("https://www.alteogen.com/kr/sub/ir/information.php?bid=2", "Alteogen official"),
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
        unique.setdefault(item.url or f"{item.source}|{item.title}", item)
    if errors:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "qlex_sc_conversion_errors.log").write_text("\n".join(errors) + "\n", encoding="utf-8")
    return list(unique.values())


def baseline(items: list[Item], state: dict) -> None:
    now = dt.datetime.now(KST).isoformat(timespec="seconds")
    state["seen"] = sorted(set(state.get("seen", [])) | {item.key for item in items})[-4000:]
    state["last_conversion"] = BASE_CONVERSION
    state["last_qlex_sales_m"] = BASE_QLEX_SALES_M
    state["initialized_at_kst"] = now
    state["last_check_kst"] = now
    write_pending(state)
    SETUP.write_text(
        "[바이오 감시] KEYTRUDA QLEX SC 전환 감시 설정\n\n"
        "- Merck 공식: QLEX 분기 매출, 미국 SC adoption/conversion, 처방·볼륨 신규 수치\n"
        "- Alteogen 공식: QLEX 판매 마일스톤, 로열티, ALT-B4 상업 공급 신규 공시\n"
        "- 시장 데이터: UBS/Symphony Health/Bloomberg 및 공개 인용자료의 미국 PD-(L)1 월간 SC 전환율\n"
        "- 비교: QLEX vs Opdivo SC vs Tecentriq SC, 반드시 동일 출시 후 개월(M+N) 기준\n"
        "- 현재 기준선: 미국 gross-sales QLEX SC 전환율 10.5%, 2026 Q2 QLEX 매출 $463m\n"
        "- gross-sales 전환율은 환자수 점유율과 다르게 해석\n"
        "- 같은 발표·같은 기준기간·같은 숫자의 재인용은 중복 알림하지 않음\n"
        "- 새 데이터가 없으면 무통지\n\n"
        f"기준선 생성: {now}\n",
        encoding="utf-8",
    )
    STATUS.write_text(f"baseline=true items={len(items)} at={now}\n", encoding="utf-8")


def check(items: list[Item], state: dict) -> None:
    seen = set(state.get("seen", []))
    fresh = [item for item in items if item.key not in seen]
    alerts: list[Item] = []
    silent: list[Item] = []
    for item in fresh:
        item = enrich(item)
        (alerts if relevant(item.full) else silent).append(item)

    pending = dict(state)
    pending["seen"] = sorted(seen | {item.key for item in silent} | {item.key for item in alerts})[-4000:]
    pending["last_check_kst"] = dt.datetime.now(KST).isoformat(timespec="seconds")

    if not alerts:
        write_pending(pending)
        STATUS.write_text(f"changed=false fresh={len(fresh)} at={pending['last_check_kst']}\n", encoding="utf-8")
        return

    chosen: list[Item] = []
    title_seen: set[str] = set()
    for item in alerts:
        title_key = re.sub(r"\W+", "", item.title.lower())[:180]
        if title_key in title_seen:
            continue
        title_seen.add(title_key)
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
        lines.append(f"- 출처: {item.source}" + (f" / {item.published}" if item.published else ""))
        if values:
            lines.append("- 신규 숫자 후보: " + ", ".join(values))

        if conv is not None:
            old = float(pending.get("last_conversion", BASE_CONVERSION))
            if "gross sales" in low or "gross-sales" in low:
                lines.append(f"- 쉽게: 미국 IV+SC 총판매액을 100으로 볼 때 QLEX/SC가 {conv:.1f}을 차지한다는 의미입니다. 환자 100명 중 {conv:.1f}명이라는 뜻은 아닙니다.")
                lines.append(f"- 동일 gross-sales 기준 직전 {old:.1f}% 대비 {conv-old:+.1f}%p")
                pending["last_conversion"] = conv
            else:
                lines.append(f"- 쉽게: QLEX 전환/채택 수치 {conv:.1f}%입니다. 환자수·처방건수·매출 중 어느 기준인지 원문 정의를 구분합니다.")

        if sales is not None:
            old_sales = float(pending.get("last_qlex_sales_m", BASE_QLEX_SALES_M))
            lines.append(f"- QLEX 매출 ${sales:.1f}m = {krw(sales)}")
            if old_sales > 0:
                lines.append(f"- 직전 공식 기준 ${old_sales:.1f}m 대비 {(sales/old_sales-1)*100:+.1f}%")
            lines.append("- 이것은 Merck 제품매출이며 Alteogen 매출 자체는 아닙니다. 다만 ALT-B4 판매 마일스톤·향후 로열티·상업 공급의 기반이 커지는 방향입니다.")
            if item.source == "Merck official":
                pending["last_qlex_sales_m"] = sales

        if "opdivo" in low or "tecentriq" in low:
            lines.append("- 경쟁 비교: Opdivo SC·Tecentriq SC는 QLEX와 동일 출시 후 개월(M+N) 기준으로만 속도를 비교합니다.")
        if any(k in low for k in ("milestone", "마일스톤", "royalty", "로열티")):
            lines.append("- Alteogen 실적: 판매 마일스톤은 일회성, 로열티·ALT-B4 공급은 반복성으로 분리합니다.")
        if item.source not in ("Merck official", "Alteogen official"):
            lines.append("- 시장/2차 자료: 공식자료로 확인되기 전까지 확정치로 승격하지 않습니다. UBS/Symphony 원자료가 비공개면 공개 인용값만 표시하고 임의 추정하지 않습니다.")
        lines.append(f"- 원문: {item.url}")
        lines.append("")

    lines += [
        "판정",
        "- gross-sales 전환율 ≠ 환자수 점유율.",
        "- QLEX 전환율의 절대값보다 10.5% 이후 15%→20%→30~40%로 가는 기울기를 중점 추적합니다.",
        "- 같은 기준월·분기·동일 숫자의 재인용은 중복 알림하지 않습니다.",
    ]
    ALERT.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    write_pending(pending)
    STATUS.write_text(f"changed=true fresh={len(fresh)} alerts={len(chosen)} at={pending['last_check_kst']}\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("baseline", "check"), default="check")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    state = load_state()
    items = collect()
    if args.mode == "baseline" or not state.get("initialized_at_kst"):
        baseline(items, state)
    else:
        check(items, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
