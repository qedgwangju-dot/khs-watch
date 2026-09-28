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
STATE = ROOT / "data" / "tsmc_leading_node_watch_state.json"
ALERT = ROOT / "out" / "tsmc_leading_node_alert.html"
STATUS = ROOT / "out" / "tsmc_leading_node_status.json"
UA = "Mozilla/5.0 (compatible; khs-watch/2.0; +https://github.com/qedgwangju-dot/khs-watch)"
WATCH_VERSION = 1

UDN_BASELINE = "https://money.udn.com/money/story/5612/9780512"
FOCUS_2NM = "https://focustaiwan.tw/sci-tech/202604280010"
TSMC_ANNUAL = "https://investor.tsmc.com/static/annualReports/2025/english/index.html"
TSMC_4Q25_TRANSCRIPT = "https://investor.tsmc.com/english/encrypt/files/encrypt_file/reports/2026-01/51d09df96cd89ac19d65af39032b038dc2896a24/TSMC%204Q25%20Transcript.pdf"

SEARCHES = [
    ('"TSMC" 2nm capacity wafers month N2', "en"),
    ('"TSMC" 3nm capacity wafers month N3', "en"),
    ('"TSMC" N2P A16 A14 production', "en"),
    ('"TSMC" 2nm Apple NVIDIA AMD Qualcomm MediaTek capacity', "en"),
    ('台積電 2奈米 月產能 擴產 12萬', "zh"),
    ('台積電 3奈米 月產能 18萬 20萬', "zh"),
    ('台積電 2奈米 蘋果 輝達 超微 高通 聯發科 追加', "zh"),
]

TRUSTED = (
    "tsmc.com", "investor.tsmc.com", "reuters", "bloomberg", "cna.com.tw", "中央社",
    "money.udn.com", "udn.com", "經濟日報", "trendforce", "digitimes",
    "focustaiwan.tw",
)
EVIDENCE_RANK = {"reported": 1, "supply_chain_report": 2, "top_tier_report": 3, "official": 4}
HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
SOURCE_KO = {
    "經濟日報": "경제일보",
    "中央社": "대만 중앙통신사(CNA)",
    "聯合報": "연합보",
}
CAPACITY_ABS_TRIGGER = 10000
CAPACITY_PCT_TRIGGER = 10.0
PRICE_PCT_TRIGGER = 5.0
RESERVATION_PP_TRIGGER = 10.0

AI_HBM_CUSTOMERS = {"NVIDIA", "AMD", "Broadcom"}
CUSTOMER_ALIASES = {
    "Apple": ("apple", "蘋果", "苹果"),
    "NVIDIA": ("nvidia", "輝達", "辉达"),
    "AMD": ("amd", "超微"),
    "Qualcomm": ("qualcomm", "高通"),
    "MediaTek": ("mediatek", "聯發科", "联发科"),
    "Broadcom": ("broadcom", "博通"),
}


def now_kst():
    return datetime.now(ZoneInfo("Asia/Seoul"))


def clean(value):
    value = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    return re.sub(r"\s+", " ", value).strip()


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,*/*"})
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


def rss_url(query, lang):
    enc = urllib.parse.quote(query)
    if lang == "zh":
        return f"https://news.google.com/rss/search?q={enc}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    return f"https://news.google.com/rss/search?q={enc}&hl=en-US&gl=US&ceid=US:en"


def decode_google(url):
    if "news.google.com" not in (url or ""):
        return url
    if gnewsdecoder is None:
        return ""
    try:
        result = gnewsdecoder(url, interval=0.15)
        if isinstance(result, dict) and result.get("status"):
            direct = str(result.get("decoded_url") or "").strip()
            if direct.startswith("http") and "news.google.com" not in direct:
                return direct
    except Exception:
        pass
    return ""


def evidence_state(source, url):
    text = ((source or "") + " " + (url or "")).lower()
    if "tsmc.com" in text or "investor.tsmc.com" in text:
        return "official"
    if any(x in text for x in ("reuters", "bloomberg", "cna.com.tw", "中央社", "focustaiwan.tw")):
        return "top_tier_report"
    if any(x in text for x in ("money.udn.com", "udn.com", "經濟日報", "trendforce", "digitimes")):
        return "supply_chain_report"
    return "reported"


def source_name_ko(name, url=""):
    raw = clean(name)
    for original, translated in SOURCE_KO.items():
        if original in raw:
            return translated
    if HAN_RE.search(raw):
        return urllib.parse.urlparse(url or "").hostname or "출처"
    return raw or (urllib.parse.urlparse(url or "").hostname or "출처")


def korean_guard(text):
    if HAN_RE.search(text):
        raise ValueError("번역되지 않은 한자·중문이 TSMC 선단공정 Telegram 알림에 남아 있어 전송을 차단했습니다")
    return text


def read_events():
    rows = {}
    for query, lang in SEARCHES:
        try:
            root = ET.fromstring(fetch(rss_url(query, lang)))
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
            if not any(k in low for k in ("tsmc", "台積電", "台积电")):
                continue
            if not any(k in low for k in ("2nm", "2 nm", "2奈米", "n2", "3nm", "3 nm", "3奈米", "n3", "n2p", "a16", "a14")):
                continue
            direct = decode_google(link)
            if not direct:
                continue
            host = (urllib.parse.urlparse(direct).hostname or "").lower()
            trust = (source + " " + host).lower()
            if not any(x in trust for x in TRUSTED):
                continue
            key = hashlib.sha256((title + "|" + source).encode()).hexdigest()[:24]
            rows[key] = {
                "id": key, "title": title, "description": desc, "source": source or host,
                "published_at_kst": pub.isoformat(timespec="seconds") if pub else "",
                "direct_link": direct, "evidence_state": evidence_state(source, direct),
            }
    return sorted(rows.values(), key=lambda x: x.get("published_at_kst") or "")


def article_text(event):
    try:
        return clean(fetch(event.get("direct_link") or "", timeout=16).decode("utf-8", errors="ignore"))[:60000]
    except Exception:
        return ""


def _pub_year(event):
    try:
        return datetime.fromisoformat(event.get("published_at_kst") or "").year
    except Exception:
        return now_kst().year


def _wafers(raw):
    raw = raw.replace(",", "")
    return int(round(float(raw)))


def _capacity_numbers(fragment):
    out = []
    for m in re.finditer(r"([0-9]+(?:\.[0-9]+)?)\s*(?:萬|万)\s*(?:片|張|张)?", fragment, re.I):
        out.append(int(round(float(m.group(1)) * 10000)))
    for m in re.finditer(r"(\d{1,3}(?:,\d{3})+|\d{4,6})\s*(?:wafers?|wspm|片|張|张)\b", fragment, re.I):
        value = _wafers(m.group(1))
        if 1000 <= value <= 1000000:
            out.append(value)
    return out


def _period(fragment, pub_year):
    low = fragment.lower()
    m = re.search(r"\b(20\d{2})\s*(?:년)?\s*(?:q|Q)?\s*([1-4])\s*(?:분기|q)?", fragment)
    if m:
        return f"{m.group(1)}Q{m.group(2)}"
    m = re.search(r"\b([1-4])Q\s*(20\d{2})\b", fragment, re.I)
    if m:
        return f"{m.group(2)}Q{m.group(1)}"
    if any(k in fragment for k in ("第四季", "第4季")) or "4q" in low:
        y = re.search(r"(20\d{2})", fragment)
        return f"{y.group(1) if y else pub_year}Q4"
    if any(k in fragment for k in ("今年底", "年底", "年末")) or "year-end" in low or "end of the year" in low:
        y = re.search(r"(20\d{2})", fragment)
        return f"{y.group(1) if y else pub_year}YE"
    y = re.search(r"\b(20\d{2})\b", fragment)
    return y.group(1) if y else ""


def _capacity_targets(text, event):
    pub_year = _pub_year(event)
    out = {}
    sentences = re.split(r"[。.!?\n]+", text)
    for sentence in sentences:
        slow = sentence.lower()
        node = ""
        if any(x in slow for x in ("2nm", "2 nm", "n2")) or "2奈米" in sentence:
            node = "N2"
        elif any(x in slow for x in ("3nm", "3 nm", "n3")) or "3奈米" in sentence:
            node = "N3"
        if not node:
            continue
        clauses = re.split(r"[，,；;]", sentence)
        for clause in clauses:
            if not any(k in clause.lower() for k in ("capacity", "wspm", "wafer")) and not any(k in clause for k in ("月產能", "月产能", "產能", "产能")):
                continue
            nums = _capacity_numbers(clause)
            if not nums:
                continue
            period = _period(clause, pub_year) or _period(sentence, pub_year)
            if not period:
                continue
            score = 0
            if any(k in clause for k in ("原本", "原先", "先前")) or any(k in clause.lower() for k in ("previously", "originally", "prior estimate")):
                score -= 4
            if any(k in clause for k in ("衝刺", "上看", "達", "达到", "目標", "目标")) or any(k in clause.lower() for k in ("target", "reach", "ramp", "expected")):
                score += 3
            key = f"{node}|{period}"
            row = {
                "value": nums[-1] if len(nums) == 1 else None,
                "min": min(nums) if len(nums) > 1 else None,
                "max": max(nums) if len(nums) > 1 else None,
                "score": score,
                "evidence_state": event.get("evidence_state") or "reported",
                "source_url": event.get("direct_link") or "",
                "source_name": event.get("source") or "",
            }
            old = out.get(key)
            if old is None or row["score"] >= old.get("score", -99):
                out[key] = row
    for row in out.values():
        row.pop("score", None)
    return out


def _customers(text):
    low = text.lower()
    found = []
    for name, aliases in CUSTOMER_ALIASES.items():
        if any(a.lower() in low for a in aliases):
            found.append(name)
    return sorted(set(found))


def _reservation(text, event):
    low = text.lower()
    if not any(k in low for k in ("additional", "increase", "booking", "reservation", "order", "追加", "增幅", "加單", "加单", "追單", "追单", "預訂", "预订")):
        return None
    m = re.search(r"([0-9]{1,3}(?:\.[0-9]+)?)\s*%\s*(?:至|到|~|[-–—]|to)\s*([0-9]{1,3}(?:\.[0-9]+)?)\s*%", text, re.I)
    if not m:
        return None
    customers = _customers(text)
    if not customers:
        return None
    return {
        "min_pct": float(m.group(1)), "max_pct": float(m.group(2)),
        "customers": customers,
        "ai_hbm_customers": sorted(set(customers) & AI_HBM_CUSTOMERS),
        "evidence_state": event.get("evidence_state") or "reported",
        "source_url": event.get("direct_link") or "",
        "source_name": event.get("source") or "",
    }


def _wafer_prices(text, event):
    out = {}
    for node, aliases in (("N2", ("2nm", "2 nm", "2奈米", "n2")), ("N3", ("3nm", "3 nm", "3奈米", "n3"))):
        for sentence in re.split(r"[。.!?\n]+", text):
            low = sentence.lower()
            if not any(a.lower() in low for a in aliases):
                continue
            m = re.search(r"(?:US\$|\$)\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:per\s+wafer|/wafer|每片)?", sentence, re.I)
            if not m:
                continue
            value = float(m.group(1).replace(",", ""))
            if 1000 <= value <= 100000:
                out[node] = {
                    "value_usd": value,
                    "evidence_state": event.get("evidence_state") or "reported",
                    "source_url": event.get("direct_link") or "",
                    "source_name": event.get("source") or "",
                }
    return out


def _scalar_metrics(text, event):
    out = {}
    low = text.lower()
    if re.search(r"(?:5|five)\s*(?:座|fabs?)[^.]{0,120}(?:2nm|2\s*nm|2奈米)", text, re.I) or re.search(r"(?:2nm|2\s*nm|2奈米)[^.]{0,120}(?:5|five)\s*(?:座|fabs?)", text, re.I):
        out["n2_fabs_2026"] = 5
    m = re.search(r"(?:first year|第一年)[^%]{0,140}?([0-9]{1,3}(?:\.[0-9]+)?)\s*%[^.]{0,80}?(?:3nm|3奈米|3纳米)", text, re.I)
    if m:
        out["n2_first_year_vs_n3_pct"] = float(m.group(1))
    m = re.search(r"(?:2026)[^%]{0,80}(?:2028)[^%]{0,100}?([0-9]{1,3}(?:\.[0-9]+)?)\s*%[^.]{0,50}?(?:CAGR|compound|複合|复合)", text, re.I)
    if not m:
        m = re.search(r"(?:CAGR|compound|複合|复合)[^%]{0,100}?([0-9]{1,3}(?:\.[0-9]+)?)\s*%[^.]{0,100}?(?:2nm|2奈米|N2)", text, re.I)
    if m:
        out["n2_cagr_2026_2028_pct"] = float(m.group(1))
    if out:
        out["_evidence_state"] = event.get("evidence_state") or "reported"
        out["_source_url"] = event.get("direct_link") or ""
        out["_source_name"] = event.get("source") or ""
    return out


def _margin_dilution(text, event):
    low = text.lower()
    if not ("n2" in low or "2-nanometer" in low or "2nm" in low or "2奈米" in text):
        return None
    m = re.search(r"([0-9](?:\.[0-9]+)?)\s*%\s*(?:to|~|[-–—]|至)\s*([0-9](?:\.[0-9]+)?)\s*%[^.]{0,90}?(?:dilution|희석|稀釋|稀释)", text, re.I)
    if not m:
        return None
    return {
        "min_pp": float(m.group(1)), "max_pp": float(m.group(2)),
        "evidence_state": event.get("evidence_state") or "reported",
        "source_url": event.get("direct_link") or "",
    }


def _timelines(text, event):
    out = {}
    low = text.lower()
    for product in ("N2P", "A16", "A14"):
        if product.lower() not in low:
            continue
        if re.search(r"(?:second half|2H|하반기|下半年)[^0-9]{0,30}(2026)", text, re.I) or re.search(r"(2026)[^.]{0,80}(?:second half|2H|하반기|下半年)", text, re.I):
            out[product] = {"milestone": "양산", "period": "2026H2", "evidence_state": event.get("evidence_state") or "reported", "source_url": event.get("direct_link") or ""}
        else:
            y = re.search(r"(20\d{2})", text)
            if y and re.search(r"mass production|volume production|양산|量產|量产", text, re.I):
                out[product] = {"milestone": "양산", "period": y.group(1), "evidence_state": event.get("evidence_state") or "reported", "source_url": event.get("direct_link") or ""}
    return out


def extract_patch(event):
    base = clean(f"{event.get('title','')} {event.get('description','')}")
    page = article_text(event)
    text = (base + " " + page).strip()
    low = text.lower()
    if not any(k in low for k in ("tsmc", "台積電", "台积电")):
        return {}
    patch = {
        "last_evidence_state": event.get("evidence_state") or "reported",
        "last_source_url": event.get("direct_link") or "",
        "last_source_name": event.get("source") or "",
        "last_source_published_at_kst": event.get("published_at_kst") or "",
    }
    caps = _capacity_targets(text, event)
    if caps:
        patch["capacity_targets"] = caps
    reservation = _reservation(text, event)
    if reservation:
        patch["customer_reservation"] = reservation
    prices = _wafer_prices(text, event)
    if prices:
        patch["wafer_prices"] = prices
    scalars = _scalar_metrics(text, event)
    if scalars:
        patch["scalar_metrics"] = scalars
    margin = _margin_dilution(text, event)
    if margin:
        patch["n2_gross_margin_dilution"] = margin
    timelines = _timelines(text, event)
    if timelines:
        patch["process_timeline"] = timelines
    return patch


def _ev(row):
    return EVIDENCE_RANK.get((row or {}).get("evidence_state", "reported"), 0)


def merge_state(current, patch):
    out = json.loads(json.dumps(current or {}, ensure_ascii=False))
    for field in ("capacity_targets", "wafer_prices", "process_timeline"):
        target = dict(out.get(field) or {})
        for key, row in (patch.get(field) or {}).items():
            old = target.get(key) or {}
            if not old or _ev(row) >= _ev(old):
                target[key] = row
        if target:
            out[field] = target

    reservation = patch.get("customer_reservation")
    if reservation:
        old = out.get("customer_reservation") or {}
        if not old or _ev(reservation) >= _ev(old):
            out["customer_reservation"] = reservation

    margin = patch.get("n2_gross_margin_dilution")
    if margin:
        old = out.get("n2_gross_margin_dilution") or {}
        if not old or _ev(margin) >= _ev(old):
            out["n2_gross_margin_dilution"] = margin

    metrics = patch.get("scalar_metrics") or {}
    if metrics:
        new_ev = metrics.get("_evidence_state", "reported")
        old_ev = out.get("scalar_evidence_state", "reported")
        if EVIDENCE_RANK.get(new_ev, 0) >= EVIDENCE_RANK.get(old_ev, 0):
            for key in ("n2_fabs_2026", "n2_first_year_vs_n3_pct", "n2_cagr_2026_2028_pct"):
                if metrics.get(key) is not None:
                    out[key] = metrics[key]
            out["scalar_evidence_state"] = new_ev
            out["scalar_source_url"] = metrics.get("_source_url") or out.get("scalar_source_url", "")

    new_ev = patch.get("last_evidence_state", "reported")
    old_ev = out.get("last_evidence_state", "reported")
    if EVIDENCE_RANK.get(new_ev, 0) >= EVIDENCE_RANK.get(old_ev, 0):
        for key in ("last_evidence_state", "last_source_url", "last_source_name", "last_source_published_at_kst"):
            if patch.get(key):
                out[key] = patch[key]
    return out


def _capacity_mid(row):
    if not row:
        return None
    if row.get("value") is not None:
        return float(row["value"])
    if row.get("min") is not None and row.get("max") is not None:
        return (float(row["min"]) + float(row["max"])) / 2
    return None


def material_changes(old, new):
    reasons = []
    old_caps, new_caps = old.get("capacity_targets") or {}, new.get("capacity_targets") or {}
    for key, row in new_caps.items():
        before = old_caps.get(key)
        cur = _capacity_mid(row)
        prev = _capacity_mid(before)
        if prev is None and cur is not None:
            reasons.append(f"{key} 월 생산능력 {cur:,.0f}장 신규 확인")
            continue
        if prev is None or cur is None:
            continue
        delta = cur - prev
        pct = delta / prev * 100 if prev else 0
        evidence_upgrade = _ev(before) < _ev(row)
        if abs(delta) >= CAPACITY_ABS_TRIGGER or abs(pct) >= CAPACITY_PCT_TRIGGER:
            reasons.append(f"{key} 월 생산능력 {prev:,.0f}→{cur:,.0f}장 ({pct:+.1f}%)")
        elif evidence_upgrade and abs(delta) < 1:
            reasons.append(f"{key} 생산능력 보도→상위 근거 확인")

    old_r, new_r = old.get("customer_reservation") or {}, new.get("customer_reservation") or {}
    if new_r:
        old_min, old_max = old_r.get("min_pct"), old_r.get("max_pct")
        new_min, new_max = new_r.get("min_pct"), new_r.get("max_pct")
        if old_min is not None and new_min is not None:
            if abs(float(new_min)-float(old_min)) >= RESERVATION_PP_TRIGGER or abs(float(new_max)-float(old_max)) >= RESERVATION_PP_TRIGGER:
                reasons.append(f"고객 추가 예약률 {old_min:g}~{old_max:g}%→{new_min:g}~{new_max:g}%")
        elif new_min is not None:
            reasons.append(f"고객 추가 예약률 {new_min:g}~{new_max:g}% 신규 확인")
        added = sorted(set(new_r.get("customers") or []) - set(old_r.get("customers") or []))
        if added and float(new_r.get("min_pct") or 0) >= RESERVATION_PP_TRIGGER:
            reasons.append("추가 예약 고객 확대: " + "·".join(added))

    for key, label in (
        ("n2_fabs_2026", "2026년 2나노 가동 팹"),
        ("n2_first_year_vs_n3_pct", "2나노 첫해 생산량의 3나노 대비"),
        ("n2_cagr_2026_2028_pct", "2나노 2026~2028 생산능력 CAGR"),
    ):
        if new.get(key) is not None and old.get(key) is not None and float(new[key]) != float(old[key]):
            reasons.append(f"{label} {old[key]:g}→{new[key]:g}")
        elif new.get(key) is not None and old.get(key) is None:
            reasons.append(f"{label} {new[key]:g} 신규 확인")

    old_prices, new_prices = old.get("wafer_prices") or {}, new.get("wafer_prices") or {}
    for node, row in new_prices.items():
        before = old_prices.get(node)
        if before and before.get("value_usd") and row.get("value_usd"):
            pct = (float(row["value_usd"]) / float(before["value_usd"]) - 1) * 100
            if abs(pct) >= PRICE_PCT_TRIGGER:
                reasons.append(f"{node} 웨이퍼 가격 {pct:+.1f}%")
        elif row.get("value_usd"):
            reasons.append(f"{node} 웨이퍼 가격 신규 확인")

    old_t, new_t = old.get("process_timeline") or {}, new.get("process_timeline") or {}
    for product, row in new_t.items():
        before = old_t.get(product)
        if before and (before.get("period"), before.get("milestone")) != (row.get("period"), row.get("milestone")):
            reasons.append(f"{product} 일정 {before.get('period','미확인')}→{row.get('period','미확인')} {row.get('milestone','')}")
        elif not before:
            reasons.append(f"{product} {row.get('milestone','일정')} {row.get('period','미확인')} 신규 확인")

    old_m, new_m = old.get("n2_gross_margin_dilution") or {}, new.get("n2_gross_margin_dilution") or {}
    if new_m and old_m:
        if (old_m.get("min_pp"), old_m.get("max_pp")) != (new_m.get("min_pp"), new_m.get("max_pp")):
            reasons.append(f"N2 매출총이익률 희석 {old_m.get('min_pp')}~{old_m.get('max_pp')}%p→{new_m.get('min_pp')}~{new_m.get('max_pp')}%p")
    elif new_m:
        reasons.append(f"N2 매출총이익률 희석 {new_m.get('min_pp')}~{new_m.get('max_pp')}%p 신규 확인")
    return reasons


def _fmt_cap(row):
    if not row:
        return "미확인"
    if row.get("value") is not None:
        return f"{int(row['value']):,}장/월"
    if row.get("min") is not None and row.get("max") is not None:
        return f"{int(row['min']):,}~{int(row['max']):,}장/월"
    return "미확인"


def alert_text(new, reasons, checked):
    caps = new.get("capacity_targets") or {}
    r = new.get("customer_reservation") or {}
    lines = [
        "🚨 <b>TSMC 선단공정 생산능력 상태 변화</b>",
        "━━━━━━━━━━━━━━━━",
        "• 이번 변화: <b>" + html.escape(" · ".join(reasons)) + "</b>",
        "• 2나노 2026년말: <b>" + html.escape(_fmt_cap(caps.get("N2|2026YE"))) + "</b>",
        "• 3나노 2026년 4분기: <b>" + html.escape(_fmt_cap(caps.get("N3|2026Q4"))) + "</b>",
        "• 3나노 2027년: <b>" + html.escape(_fmt_cap(caps.get("N3|2027"))) + "</b>",
    ]
    if r:
        lines.append(f"• 고객 추가 예약: <b>{r.get('min_pct',0):g}~{r.get('max_pct',0):g}%</b> · " + html.escape(" · ".join(r.get("customers") or [])))
    if new.get("n2_fabs_2026") is not None:
        lines.append(f"• 2026년 2나노 가동 팹: {int(new['n2_fabs_2026'])}개")
    if new.get("n2_first_year_vs_n3_pct") is not None:
        lines.append(f"• 2나노 첫해 생산량: 3나노 첫해 대비 +{float(new['n2_first_year_vs_n3_pct']):g}%")
    if new.get("n2_cagr_2026_2028_pct") is not None:
        lines.append(f"• 2나노 생산능력: 2026~2028 CAGR {float(new['n2_cagr_2026_2028_pct']):g}%")
    margin = new.get("n2_gross_margin_dilution") or {}
    if margin:
        lines.append(f"• 초기 수익성 역풍: 2026년 N2 램프의 매출총이익률 희석 {margin.get('min_pp'):g}~{margin.get('max_pp'):g}%p")
    lines.append("• 다음 확인: 월 생산능력 1만 장 또는 10% 이상 변경 · 고객 예약 10%p 이상 변경 · 장비 반입/양산 일정 · 웨이퍼 가격 5% 이상 변경 · 수율·가동률·마진")
    lines.append("• 중복 방지: 같은 생산능력·같은 고객 예약 수치의 재배포는 다시 알리지 않습니다.")
    if new.get("last_source_url"):
        safe = urllib.parse.quote(new["last_source_url"], safe=":/?&=%#@+;,-._~")
        lines.append("• 근거: " + html.escape(source_name_ko(new.get("last_source_name"), new.get("last_source_url"))) + f' · <a href="{html.escape(safe, quote=True)}">원문</a>')
    lines.append("• 조회: " + checked.strftime("%Y-%m-%d %H:%M KST"))
    return korean_guard("\n".join(lines) + "\n")


def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"watch_version": WATCH_VERSION, "current_state": {}}


def save_state(value):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def hbm_snapshot(state=None):
    state = state or load_state()
    cur = state.get("current_state") or {}
    caps = cur.get("capacity_targets") or {}
    r = cur.get("customer_reservation") or {}
    def mid(key):
        row = caps.get(key) or {}
        return int(round(_capacity_mid(row))) if _capacity_mid(row) is not None else None
    return {
        "n2_2026ye_wpm": mid("N2|2026YE"),
        "n3_2026q4_wpm": mid("N3|2026Q4"),
        "reservation_min_pct": r.get("min_pct"),
        "reservation_max_pct": r.get("max_pct"),
        "reservation_customers": r.get("customers") or [],
        "ai_hbm_customers": r.get("ai_hbm_customers") or [],
        "n2_fabs_2026": cur.get("n2_fabs_2026"),
        "source_url": cur.get("last_source_url") or "",
        "source_name": source_name_ko(cur.get("last_source_name"), cur.get("last_source_url")),
    }


def main():
    checked = now_kst()
    state = load_state()
    current = dict(state.get("current_state") or {})
    candidate = dict(current)
    latest = None
    cutoff = checked - timedelta(days=21)
    events = read_events()
    for event in events:
        try:
            dt = datetime.fromisoformat(event.get("published_at_kst") or "")
        except Exception:
            continue
        if dt < cutoff or dt > checked + timedelta(minutes=10):
            continue
        patch = extract_patch(event)
        if not patch:
            continue
        before = candidate
        candidate = merge_state(candidate, patch)
        if candidate != before:
            latest = event

    reasons = material_changes(current, candidate)
    state["watch_version"] = WATCH_VERSION
    state["last_checked_at_kst"] = checked.isoformat(timespec="seconds")
    state["current_state"] = candidate
    if latest:
        state["last_evidence_url"] = latest.get("direct_link") or ""
        state["last_evidence_published_at_kst"] = latest.get("published_at_kst") or ""
    ALERT.parent.mkdir(exist_ok=True)
    if reasons:
        ALERT.write_text(alert_text(candidate, reasons, checked), encoding="utf-8")
        state["last_alert_reasons"] = reasons
        state["last_alert_at_kst"] = checked.isoformat(timespec="seconds")
    else:
        ALERT.unlink(missing_ok=True)
    save_state(state)
    STATUS.write_text(json.dumps({
        "checked_at_kst": checked.isoformat(timespec="seconds"),
        "events_scanned": len(events),
        "changes": reasons,
        "hbm_snapshot": hbm_snapshot(state),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("tsmc_leading_node_watch=true changes=" + str(len(reasons)))


if __name__ == "__main__":
    main()
