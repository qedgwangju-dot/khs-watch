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
except Exception:
    gnewsdecoder = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "rubin_socamm_capacity_watch_state.json"
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)

UA = "Mozilla/5.0 (compatible; khs-watch/2.0; +https://github.com/qedgwangju-dot/khs-watch)"
FRESH_HOURS = 96
VERA_CPUS_PER_NVL72 = 36
GB300_CPU_MEMORY_TB = 17.3

NVIDIA_URLS = [
    "https://www.nvidia.com/ko-kr/data-center/vera-rubin-nvl72/",
    "https://www.nvidia.com/en-au/data-center/vera-rubin-nvl72/",
]

QUERIES = [
    '"Vera" SOCAMM2 (768GB OR 1.5TB OR 1536GB OR 96GB OR 192GB OR 28TB OR 54TB)',
    '"Vera CPU" (SOCAMM2 OR LPDDR5X) (shipment OR shipping OR configuration OR order OR production OR supply)',
    '"Vera Rubin" (SOCAMM2 OR LPDDR5X) (capacity OR memory OR 768GB OR 1.5TB OR 28TB OR 54TB)',
    '(Dell OR HPE OR Lenovo OR Supermicro OR GIGABYTE OR QCT OR Wiwynn) "Vera CPU" (memory OR SOCAMM2 OR LPDDR5X)',
    '(Samsung OR "SK hynix" OR Micron) SOCAMM2 (Vera OR Rubin) (mass production OR shipment OR supply OR order OR sample)',
]

TRUSTED_HINTS = (
    "trendforce", "reuters", "bloomberg", "digitimes", "tom's hardware",
    "toms hardware", "the elec", "thelec", "semianalysis", "financial times",
    "wall street journal", "wsj", "cnbc", "yonhap", "연합뉴스",
)
OFFICIAL_HOST_HINTS = (
    "nvidia.com", "dell.com", "hpe.com", "lenovo.com", "supermicro.com",
    "gigabyte.com", "qct.io", "quantatw.com", "wiwynn.com", "samsung.com",
    "news.skhynix.com", "skhynix.com", "micron.com",
)
OEM_NAMES = ("dell", "hpe", "lenovo", "supermicro", "gigabyte", "qct", "wiwynn")
SUPPLIER_NAMES = ("samsung", "삼성", "sk hynix", "sk하이닉스", "micron")
ACTION_TERMS = (
    "shipment", "shipping", "ship", "order", "production", "mass production",
    "supply", "configuration", "launch", "sample", "adopt", "spec", "datasheet",
    "halve", "halved", "cut", "reduce", "reduced", "increase", "increased",
    "actual", "출하", "주문", "양산", "공급", "구성", "출시", "샘플", "채택",
    "사양", "절반", "축소", "감소", "상향", "하향", "실제",
)


def fetch(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<(script|style|svg|noscript)[^>]*>.*?</\\1>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\\s+", " ", value).strip()


def parse_pubdate(value: str) -> datetime | None:
    try:
        d = parsedate_to_datetime(value)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(ZoneInfo("Asia/Seoul"))
    except Exception:
        return None


def rss_url(query: str, lang: str) -> str:
    q = urllib.parse.quote(query)
    if lang == "ko":
        return f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


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


def event_id(title: str, link: str) -> str:
    return hashlib.sha256(f"{title}|{link}".encode("utf-8")).hexdigest()[:24]


def normalize_num_token(value: str) -> str:
    return value.lower().replace(" ", "").replace(",", "")


def extract_capacity(text: str) -> dict:
    low = text.lower().replace(",", "")
    module_values = set()
    cpu_values = set()
    rack_values = set()
    slots = set()

    if re.search(r"\\b96\\s*gb\\b", low):
        module_values.add(96)
    if re.search(r"\\b192\\s*gb\\b", low):
        module_values.add(192)

    if re.search(r"\\b768\\s*gb\\b", low):
        cpu_values.add(768)
    if re.search(r"\\b(?:1\\.5|1,?536)\\s*(?:tb|gb)\\b", low):
        if re.search(r"1\\.5\\s*tb", low):
            cpu_values.add(1536)
        if re.search(r"1536\\s*gb", low):
            cpu_values.add(1536)

    for m in re.finditer(r"\\b(27(?:\\.\\d+)?|28(?:\\.\\d+)?|54(?:\\.\\d+)?|55(?:\\.\\d+)?)\\s*tb\\b", low):
        rack_values.add(float(m.group(1)))

    for m in re.finditer(r"\\b([48])\\s*(?:socamm2?|socamm|modules?|slots?|모듈|슬롯)", low):
        slots.add(int(m.group(1)))
    for m in re.finditer(r"(?:socamm2?|socamm|modules?|slots?|모듈|슬롯)\\s*(?:x|×|:)??\\s*([48])\\b", low):
        slots.add(int(m.group(1)))

    # Only infer the standard 8-module arithmetic when the text itself supplies module + CPU/rack capacity.
    if 96 in module_values and (768 in cpu_values or any(27 <= x <= 29 for x in rack_values)):
        slots.add(8)
        cpu_values.add(768)
        rack_values.add(round(96 * 8 * VERA_CPUS_PER_NVL72 / 1024, 3))
    if 192 in module_values and (1536 in cpu_values or any(53 <= x <= 55 for x in rack_values)):
        slots.add(8)
        cpu_values.add(1536)
        rack_values.add(round(192 * 8 * VERA_CPUS_PER_NVL72 / 1024, 3))

    return {
        "module_gb": sorted(module_values),
        "cpu_gb": sorted(cpu_values),
        "rack_tb": sorted(rack_values),
        "slots": sorted(slots),
    }


def capacity_signature(cap: dict) -> str:
    return json.dumps(cap, sort_keys=True, ensure_ascii=False)


def source_tier(source: str, direct_link: str) -> str:
    host = (urlparse(direct_link).hostname or "").lower()
    src = (source or "").lower()
    if any(h in host for h in OFFICIAL_HOST_HINTS):
        return "공식자료"
    if any(h in src or h in host for h in TRUSTED_HINTS):
        return "신뢰 보도"
    return "일반 보도"


def fetch_official_nvidia() -> tuple[dict | None, list[str]]:
    errors = []
    for url in NVIDIA_URLS:
        try:
            body = fetch(url).decode("utf-8", errors="ignore")
            text = clean_text(body)
            low = text.lower()
            if "vera" not in low or "rubin" not in low:
                raise RuntimeError("Vera Rubin 본문 식별 실패")
            cap = extract_capacity(text)
            # NVIDIA table currently exposes up to 54 TB rack / 1.5 TB per Vera CPU.
            if "54 tb" in low and not any(53 <= x <= 55 for x in cap["rack_tb"]):
                cap["rack_tb"].append(54.0)
            if "1.5 tb" in low and 1536 not in cap["cpu_gb"]:
                cap["cpu_gb"].append(1536)
            cap["rack_tb"] = sorted(set(cap["rack_tb"]))
            cap["cpu_gb"] = sorted(set(cap["cpu_gb"]))
            return {
                "url": url,
                "capacity": cap,
                "signature": capacity_signature(cap),
                "label": "NVIDIA 공식 최대 사양",
            }, errors
        except Exception as e:
            errors.append(f"NVIDIA 공식 페이지 조회 실패 {url}: {type(e).__name__}: {e}")
    return None, errors


def read_news(now: datetime) -> tuple[list[dict], list[str]]:
    items = []
    errors = []
    cutoff = now - timedelta(days=10)
    seen = set()
    for query in QUERIES:
        for lang in ("en", "ko"):
            try:
                root = ET.fromstring(fetch(rss_url(query, lang)))
                for item in root.findall("./channel/item"):
                    title = clean_text(item.findtext("title") or "")
                    desc = clean_text(item.findtext("description") or "")
                    link = clean_text(item.findtext("link") or "")
                    pub = clean_text(item.findtext("pubDate") or "")
                    source_node = item.find("source")
                    source = clean_text(source_node.text if source_node is not None and source_node.text else "")
                    d = parse_pubdate(pub)
                    if d and d < cutoff:
                        continue
                    text = f"{title} {desc}"
                    low = text.lower()
                    if "vera" not in low or not any(k in low for k in ("socamm", "lpddr5x")):
                        continue
                    cap = extract_capacity(text)
                    if not (cap["module_gb"] or cap["cpu_gb"] or cap["rack_tb"]):
                        continue
                    if not any(k in low for k in ACTION_TERMS) and not any(k in low for k in OEM_NAMES + SUPPLIER_NAMES):
                        continue
                    eid = event_id(title, link)
                    if eid in seen:
                        continue
                    seen.add(eid)
                    direct = decode_google_news_url(link)
                    if not direct:
                        continue
                    items.append({
                        "id": eid,
                        "title": title,
                        "description": desc,
                        "source": source or "출처 미표시",
                        "published_at_kst": d.isoformat(timespec="seconds") if d else "",
                        "direct_link": direct,
                        "capacity": cap,
                        "signature": capacity_signature(cap),
                        "tier": source_tier(source, direct),
                        "text": text,
                    })
            except Exception as e:
                errors.append(f"뉴스 조회 실패 {lang}: {type(e).__name__}: {e}")
    return items, errors


def is_fresh(item: dict, now: datetime) -> bool:
    raw = item.get("published_at_kst") or ""
    if not raw:
        return False
    try:
        d = datetime.fromisoformat(raw)
    except Exception:
        return False
    return now - timedelta(hours=FRESH_HOURS) <= d <= now + timedelta(minutes=10)


def verified_news(items: list[dict], seen_ids: set[str], now: datetime) -> list[dict]:
    fresh = [x for x in items if x["id"] not in seen_ids and is_fresh(x, now)]
    grouped: dict[str, list[dict]] = {}
    for x in fresh:
        grouped.setdefault(x["signature"], []).append(x)

    out = []
    for sig, group in grouped.items():
        source_names = {x["source"].lower() for x in group if x.get("source")}
        good = [x for x in group if x["tier"] in ("공식자료", "신뢰 보도")]
        if good:
            chosen = sorted(good, key=lambda x: (x["tier"] == "공식자료", x.get("published_at_kst") or ""), reverse=True)[0]
            chosen["verification"] = chosen["tier"]
            out.append(chosen)
        elif len(source_names) >= 2:
            chosen = sorted(group, key=lambda x: x.get("published_at_kst") or "", reverse=True)[0]
            chosen["verification"] = f"일반 보도 {len(source_names)}곳 교차확인"
            out.append(chosen)
    return out


def fmt_cap(cap: dict) -> list[str]:
    lines = []
    if cap.get("module_gb"):
        lines.append("모듈당 " + "/".join(f"{x}GB" for x in cap["module_gb"]))
    if cap.get("slots"):
        lines.append("CPU당 " + "/".join(str(x) for x in cap["slots"]) + "개 모듈")
    if cap.get("cpu_gb"):
        vals = []
        for x in cap["cpu_gb"]:
            vals.append(f"{x}GB" if x < 1024 else f"{x/1024:.1f}TB")
        lines.append("CPU당 " + "/".join(vals))
    if cap.get("rack_tb"):
        lines.append("NVL72 랙당 " + "/".join(f"{x:g}TB" for x in cap["rack_tb"]))
    return lines


def classify_change(cap: dict) -> str:
    has_768 = 768 in cap.get("cpu_gb", []) or any(27 <= x <= 29 for x in cap.get("rack_tb", []))
    has_1536 = 1536 in cap.get("cpu_gb", []) or any(53 <= x <= 55 for x in cap.get("rack_tb", []))
    if has_768 and has_1536:
        return "768GB와 1.5TB급 구성이 함께 언급됨 — 다중 SKU 병행 가능성 확인 필요"
    if has_768:
        return "약 768GB/CPU·약 28TB/랙 구성 신호"
    if has_1536:
        return "최대 1.5TB/CPU·54TB/랙 구성 유지·회복 신호"
    return "SOCAMM2 용량·구성 변화 신호"


def investment_math(cap: dict) -> list[str]:
    lines = []
    rack = None
    if cap.get("rack_tb"):
        rack = max(cap["rack_tb"])
    elif 768 in cap.get("cpu_gb", []):
        rack = 768 * VERA_CPUS_PER_NVL72 / 1024
    elif 1536 in cap.get("cpu_gb", []):
        rack = 1536 * VERA_CPUS_PER_NVL72 / 1024
    if rack:
        vs_gb300 = (rack / GB300_CPU_MEMORY_TB - 1) * 100
        vs_54 = (rack / 54.0 - 1) * 100
        lines.append(f"GB300 CPU 메모리 약 {GB300_CPU_MEMORY_TB:g}TB 대비 비트량 {vs_gb300:+.1f}%")
        lines.append(f"기존 54TB 가정 대비 SOCAMM 비트량 {vs_54:+.1f}%")
    return lines


def build_alert(now: datetime, official_change: dict | None, events: list[dict]) -> str:
    blocks = [
        "<b>Vera Rubin SOCAMM 용량 변화 감시</b>",
        "",
        f"조회시각: {now.strftime('%Y-%m-%d %H:%M:%S KST')}",
    ]

    if official_change:
        cap = official_change["capacity"]
        blocks += [
            "",
            "<b>무엇이 달라졌나</b>",
            f"• NVIDIA 공식 최대 사양 변화: {html.escape(' / '.join(fmt_cap(cap)))}",
            f"• 현재 판정: {html.escape(classify_change(cap))}",
        ]
        for x in investment_math(cap):
            blocks.append(f"• {html.escape(x)}")
        blocks += [
            "• 확정 수준: NVIDIA 공식자료",
            f'• <a href="{html.escape(official_change["url"], quote=True)}">원문</a>',
        ]

    for e in events:
        cap = e["capacity"]
        blocks += [
            "",
            "<b>신규 실제 구성·공급 신호</b>",
            f"• {html.escape(classify_change(cap))}",
            f"• 확인 숫자: {html.escape(' / '.join(fmt_cap(cap)))}",
        ]
        for x in investment_math(cap):
            blocks.append(f"• {html.escape(x)}")

        low = e["text"].lower()
        if any(k in low for k in OEM_NAMES):
            blocks.append("• 매출 연결 경로: 서버 OEM 실제 구성·출하 SKU → Vera CPU 탑재량 → SOCAMM2 모듈 장수·비트 수요")
        elif any(k in low for k in SUPPLIER_NAMES):
            blocks.append("• 매출 연결 경로: 메모리 공급사 SOCAMM2 양산·출하 → Vera CPU 탑재 → LPDDR5X 비트 수요")
        else:
            blocks.append("• 매출 연결 경로: Vera CPU 구성 변화 → SOCAMM2 모듈 장수·LPDDR5X 비트 수요")

        blocks += [
            f"• 확정 수준: {html.escape(e.get('verification') or e.get('tier') or '확인 중')}",
            "• 투자 의미: 삼성전자·SK하이닉스·Micron은 비트량에 민감하고, 모듈 기판 업체는 CPU당 모듈 장수와 Vera CPU 출하량을 함께 봐야 합니다.",
            f'• <a href="{html.escape(e["direct_link"], quote=True)}">원문</a>',
        ]

    blocks += [
        "",
        "<b>현재 기준선</b>",
        "• NVIDIA 공식 페이지: NVL72당 Vera CPU 36개, CPU 메모리 최대 54TB, Vera CPU당 최대 1.5TB LPDDR5X.",
        "• 단순히 공식 페이지의 54TB 문구가 유지되는 것만으로는 알리지 않습니다.",
        "• 실제 출하 SKU, OEM 주문 구성, 공급사 양산·출하, 768GB↔1.5TB 변화처럼 새로운 숫자가 확인될 때만 발송합니다.",
    ]
    return "\n".join(blocks).strip() + "\n"


def load_state() -> tuple[dict, bool]:
    if not DATA.exists():
        return {}, True
    try:
        return json.loads(DATA.read_text(encoding="utf-8")), False
    except Exception:
        return {}, True


def write_json(path: pathlib.Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    state, first_run = load_state()
    seen_ids = set(state.get("seen_ids") or [])
    prev_official_sig = state.get("official_signature") or ""

    official, official_errors = fetch_official_nvidia()
    news, news_errors = read_news(now)
    events = verified_news(news, seen_ids, now)

    official_change = None
    current_official_sig = prev_official_sig
    if official:
        current_official_sig = official["signature"]
        if prev_official_sig and current_official_sig != prev_official_sig:
            official_change = official

    all_ids = seen_ids | {x["id"] for x in news}
    pending = {
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "official_signature": current_official_sig,
        "official_capacity": official.get("capacity") if official else state.get("official_capacity"),
        "official_url": official.get("url") if official else state.get("official_url"),
        "seen_ids": sorted(all_ids)[-1500:],
        "fresh_hours": FRESH_HOURS,
        "errors": (official_errors + news_errors)[-30:],
        "new_verified_events": len(events),
    }
    write_json(OUT / "rubin_socamm_capacity_pending_state.json", pending)

    if first_run:
        (OUT / "rubin_socamm_capacity_rebaseline.txt").write_text(
            f"Initial SOCAMM capacity baseline at {now.isoformat(timespec='seconds')}; no Telegram alert sent.\n",
            encoding="utf-8",
        )
    elif official_change or events:
        (OUT / "rubin_socamm_capacity_alert.html").write_text(
            build_alert(now, official_change, events[:6]), encoding="utf-8"
        )

    status = [
        "# Vera Rubin SOCAMM Capacity Watch",
        f"- checked_at_kst: {now.isoformat(timespec='seconds')}",
        f"- first_run_baseline: {str(first_run).lower()}",
        f"- official_spec_read: {str(bool(official)).lower()}",
        f"- official_changed: {str(bool(official_change)).lower()}",
        f"- news_candidates: {len(news)}",
        f"- verified_new_events: {len(events)}",
        f"- errors: {len(official_errors) + len(news_errors)}",
    ]
    for err in (official_errors + news_errors)[:12]:
        status.append(f"  - {err}")
    (OUT / "rubin_socamm_capacity_status.md").write_text("\n".join(status) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
