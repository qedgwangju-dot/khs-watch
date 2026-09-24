#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import html
import io
import json
import pathlib
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from pypdf import PdfReader

try:
    from googlenewsdecoder import gnewsdecoder
except Exception:
    gnewsdecoder = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "wonyotti_90d_thesis_watch_state.json"
OUT = ROOT / "out"
PENDING = OUT / "wonyotti_90d_thesis_pending_state.json"
ALERT = OUT / "wonyotti_90d_thesis_alert.html"
STATUS = OUT / "wonyotti_90d_thesis_status.md"

KST = ZoneInfo("Asia/Seoul")
UA = "Mozilla/5.0 (compatible; khs-watch/1.0; +https://github.com/qedgwangju-dot/khs-watch)"
BTC_LINE = 85000.0

COINGECKO = (
    "https://api.coingecko.com/api/v3/simple/price"
    "?ids=bitcoin,ethereum,solana&vs_currencies=usd&include_24hr_change=true&include_24hr_vol=true"
)
FARSIDE_BTC = "https://farside.co.uk/bitcoin-etf-flow-all-data/"
FARSIDE_ETH = "https://farside.co.uk/ethereum-etf-flow-all-data/"
TREASURY_NOMINAL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "TextView?field_tdr_date_value=2026&type=daily_treasury_yield_curve"
)
TREASURY_REAL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "TextView?field_tdr_date_value=2026&type=daily_treasury_real_yield_curve"
)
NVIDIA_HOME = "https://investor.nvidia.com/home/default.aspx"
NVIDIA_CURRENT_10Q_FALLBACK = "https://investor.nvidia.com/files/doc_financials/2027/NVDA-2027-Q2-10Q-Final-including-exhibits.pdf"

NEWS_QUERIES = {
    "빅테크 AI 설비투자": [
        '"Microsoft" AI capex guidance data center Reuters OR Bloomberg',
        '"Meta" AI capex guidance data center Reuters OR Bloomberg',
        '"Amazon" AI capex guidance data center Reuters OR Bloomberg',
        '"Alphabet" AI capex guidance data center Reuters OR Bloomberg',
    ],
    "DRAM": [
        'DRAM 2027 shortage supply contract price TrendForce OR Reuters OR Bloomberg',
        'DRAM wafer starts capacity Samsung SK hynix Micron 2027',
    ],
    "HBM": [
        'HBM HBM4 2027 supply price shortage NVIDIA Broadcom TrendForce Reuters Bloomberg',
        'HBM4 qualification capacity Samsung SK hynix Micron 2027',
    ],
    "NAND": [
        'NAND 2027 oversupply easing shortage contract price TrendForce Reuters Bloomberg',
        'NAND capacity 2027 Samsung Kioxia SK hynix Micron',
    ],
    "한국 주주환원": [
        '삼성전자 주주환원 배당 자사주 소각 2026 2027',
        'SK하이닉스 자사주 매입 소각 FCF 주주환원 2026 2027',
    ],
}

TRUSTED = (
    "reuters", "bloomberg", "financial times", "ft.com", "wall street journal", "wsj",
    "cnbc", "associated press", "ap news", "yonhap", "연합뉴스", "trendforce",
    "dramexchange", "nvidia", "samsung", "sk hynix", "sk하이닉스", "micron",
    "microsoft", "meta", "amazon", "alphabet", "google",
)
OFFICIALISH = (
    "nvidia", "samsung", "sk hynix", "sk하이닉스", "micron", "microsoft",
    "meta", "amazon", "alphabet", "google", "investor relations", "newsroom",
)
CHANGE_WORDS = (
    "raise", "raised", "cut", "lower", "increase", "decrease", "guidance", "capex",
    "shortage", "tight", "deficit", "oversupply", "surplus", "easing", "normalize",
    "price", "contract", "capacity", "wafer", "qualification", "delay", "buyback",
    "repurchase", "cancel", "reduce", "expand", "상향", "하향", "증액", "축소",
    "설비투자", "공급부족", "타이트", "과잉", "완화", "가격", "계약가",
    "생산능력", "웨이퍼", "인증", "지연", "앞당", "자사주", "소각", "배당", "주주환원",
)


def fetch(url: str, timeout: int = 30, accept: str = "*/*") -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def fetch_json(url: str, timeout: int = 30):
    return json.loads(fetch(url, timeout, "application/json").decode("utf-8"))


def clean(value: str | None) -> str:
    text = html.unescape(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_number(text: str) -> float | None:
    s = (text or "").replace(",", "").replace("$", "").strip()
    if not s or s in {"-", "—", "N/A", "n/a"}:
        return None
    negative = s.startswith("(") and s.endswith(")")
    if negative:
        s = s[1:-1]
    match = re.search(r"[-+]?\d+(?:\.\d+)?", s)
    if not match:
        return None
    value = float(match.group(0))
    return -abs(value) if negative else value


def parse_date(text: str) -> dt.date | None:
    value = " ".join((text or "").split())
    for fmt in ("%m/%d/%Y", "%d %b %Y", "%d %B %Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"initialized": False, "news_seen": []}


def write_json(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fmt_pct(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "확인 불가"
    return f"{value:+.{digits}f}%"


def fmt_usd(value: float | None) -> str:
    if value is None:
        return "확인 불가"
    if abs(value) >= 1_000_000_000:
        return f"${value/1_000_000_000:,.2f}B"
    if abs(value) >= 1_000_000:
        return f"${value/1_000_000:,.1f}M"
    return f"${value:,.0f}"


def translate_to_korean(text: str) -> str | None:
    text = clean(text)
    if not text:
        return None
    hangul = len(re.findall(r"[가-힣]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if hangul >= max(4, latin // 3):
        return text
    params = {
        "client": "gtx", "sl": "auto", "tl": "ko", "dt": "t",
        "ie": "UTF-8", "oe": "UTF-8", "q": text,
    }
    url = "https://translate.googleapis.com/translate_a/single?" + urllib.parse.urlencode(params)
    for attempt in range(2):
        try:
            data = fetch_json(url, 20)
            translated = "".join(
                str(part[0]) for part in (data[0] or [])
                if isinstance(part, list) and part and part[0]
            ).strip()
            if translated and re.search(r"[가-힣]", translated):
                return translated
        except Exception:
            if attempt == 0:
                time.sleep(1)
    return None


def decode_google_news(url: str) -> str:
    if not url or gnewsdecoder is None or "news.google.com" not in url:
        return url
    try:
        result = gnewsdecoder(url, interval=0.2)
        if isinstance(result, dict) and result.get("status") and result.get("decoded_url"):
            return str(result["decoded_url"])
    except Exception:
        pass
    return url


def farside_flow(url: str) -> dict:
    soup = BeautifulSoup(fetch(url).decode("utf-8", errors="replace"), "html.parser")
    rows = []
    for tr in soup.find_all("tr"):
        cells = [clean(x.get_text(" ", strip=True)) for x in tr.find_all(["td", "th"])]
        if len(cells) < 3:
            continue
        day = parse_date(cells[0])
        if not day:
            continue

        raw_funds = cells[1:-1]
        numeric = [parse_number(x) for x in raw_funds if x not in {"", "-", "—"}]
        reported = sum(v is not None for v in numeric)
        missing = sum(x in {"", "-", "—"} for x in raw_funds)
        total = parse_number(cells[-1])
        if reported == 0 or total is None:
            continue
        recomputed = round(sum(x for x in numeric if x is not None), 1)
        if abs(recomputed - total) > 1.0:
            continue
        status = "complete" if missing == 0 else "partial"
        rows.append({
            "date": day,
            "total": total,
            "status": status,
            "reported": reported,
            "missing": missing,
        })

    if len(rows) < 5:
        raise RuntimeError("검증 가능한 ETF 행이 5개 미만")
    rows.sort(key=lambda x: x["date"])
    latest = rows[-1]
    last5 = rows[-5:]
    return {
        "date": latest["date"].isoformat(),
        "daily_usd_m": latest["total"],
        "status": latest["status"],
        "reported_funds": latest["reported"],
        "missing_funds": latest["missing"],
        "five_day_usd_m": round(sum(x["total"] for x in last5), 1),
        "five_day_dates": [x["date"].isoformat() for x in last5],
    }


def crypto_snapshot() -> tuple[dict, list[str]]:
    result = {}
    errors = []
    try:
        raw = fetch_json(COINGECKO)
        result["prices"] = {
            "BTC": {"usd": float(raw["bitcoin"]["usd"]), "change24": float(raw["bitcoin"].get("usd_24h_change") or 0.0), "volume24": float(raw["bitcoin"].get("usd_24h_vol") or 0.0)},
            "ETH": {"usd": float(raw["ethereum"]["usd"]), "change24": float(raw["ethereum"].get("usd_24h_change") or 0.0), "volume24": float(raw["ethereum"].get("usd_24h_vol") or 0.0)},
            "SOL": {"usd": float(raw["solana"]["usd"]), "change24": float(raw["solana"].get("usd_24h_change") or 0.0), "volume24": float(raw["solana"].get("usd_24h_vol") or 0.0)},
        }
    except Exception as exc:
        errors.append(f"CoinGecko: {exc}")

    deriv = {}
    for coin in ("BTC", "ETH", "SOL"):
        contract = f"{coin}_USDT"
        try:
            info = fetch_json(f"https://api.gateio.ws/api/v4/futures/usdt/contracts/{contract}")
            stats = fetch_json(
                "https://api.gateio.ws/api/v4/futures/usdt/contract_stats?"
                + urllib.parse.urlencode({"contract": contract, "interval": "5m", "limit": 1})
            )
            stat = stats[-1] if isinstance(stats, list) and stats else {}
            deriv[f"{coin}USDT"] = {
                "funding": float(info.get("funding_rate") or 0.0),
                "open_interest": float(stat.get("open_interest") or info.get("position_size") or 0.0),
                "open_interest_value": float(stat.get("open_interest_usd") or 0.0),
                "turnover24h": float(info.get("trade_size") or 0.0),
                "source": "Gate.io Futures API",
            }
        except Exception as exc:
            errors.append(f"Gate.io {contract}: {exc}")
    result["derivatives"] = deriv

    for key, url in (("btc_etf", FARSIDE_BTC), ("eth_etf", FARSIDE_ETH)):
        try:
            result[key] = farside_flow(url)
        except Exception as exc:
            errors.append(f"{key}: {exc}")
    return result, errors


def treasury_10y(url: str) -> dict:
    soup = BeautifulSoup(fetch(url).decode("utf-8", errors="replace"), "html.parser")
    table = soup.find("table")
    if table is None:
        raise RuntimeError("Treasury 표 없음")
    rows = table.find_all("tr")
    headers = [clean(x.get_text(" ", strip=True)).lower() for x in rows[0].find_all(["th", "td"])]
    index = None
    for i, header in enumerate(headers):
        if "10-year" in header or ("10" in header and ("year" in header or "yr" in header)):
            index = i
            break
    if index is None:
        raise RuntimeError("10년물 열 탐색 실패")
    parsed = []
    for row in rows[1:]:
        cells = [clean(x.get_text(" ", strip=True)) for x in row.find_all(["td", "th"])]
        if not cells or index >= len(cells):
            continue
        day = parse_date(cells[0])
        value = parse_number(cells[index])
        if day and value is not None:
            parsed.append((day, value))
    if not parsed:
        raise RuntimeError("10년물 행 파싱 실패")
    parsed.sort()
    return {"date": parsed[-1][0].isoformat(), "value": parsed[-1][1]}


def rates_snapshot() -> tuple[dict, list[str]]:
    out, errors = {}, []
    for key, url in (("nominal10y", TREASURY_NOMINAL), ("real10y", TREASURY_REAL)):
        try:
            out[key] = treasury_10y(url)
        except Exception as exc:
            errors.append(f"{key}: {exc}")
    return out, errors


def discover_nvidia_10q() -> str:
    html_text = fetch(NVIDIA_HOME, 30, "text/html").decode("utf-8", errors="replace")
    soup = BeautifulSoup(html_text, "html.parser")
    candidates = []
    for anchor in soup.find_all("a", href=True):
        label = clean(anchor.get_text(" ", strip=True))
        href = urljoin(NVIDIA_HOME, anchor.get("href") or "")
        if re.search(r"\b10-Q\b", label, re.I) and href:
            candidates.append(href)
    if candidates:
        pdfs = [x for x in candidates if ".pdf" in x.lower()]
        return (pdfs or candidates)[0]
    return NVIDIA_CURRENT_10Q_FALLBACK


def _first_pair_millions(text: str, label_pattern: str) -> tuple[float | None, float | None]:
    match = re.search(
        label_pattern + r"\s+\$?\s*([\d,]+)\s+\$?\s*([\d,]+)",
        text,
        flags=re.I,
    )
    if not match:
        return None, None
    return float(match.group(1).replace(",", "")), float(match.group(2).replace(",", ""))


def _quarter_four_values(text: str, label_pattern: str) -> tuple[float | None, float | None]:
    match = re.search(
        label_pattern
        + r"\s+\$?\s*([\d,]+)\s+\$?\s*([\d,]+)\s+\$?\s*([\d,]+)\s+\$?\s*([\d,]+)",
        text,
        flags=re.I,
    )
    if not match:
        return None, None
    return float(match.group(1).replace(",", "")), float(match.group(2).replace(",", ""))


def _billion(text: str, pattern: str) -> float | None:
    match = re.search(pattern, text, flags=re.I | re.S)
    return float(match.group(1)) if match else None


def nvidia_ir_snapshot(old_nv: dict | None = None) -> tuple[dict, list[str]]:
    old_nv = old_nv or {}
    errors = []
    out = {}
    try:
        q10_url = discover_nvidia_10q()
        out["q10_url"] = q10_url
        if q10_url == old_nv.get("q10_url") and old_nv.get("parsed_ok") and int(old_nv.get("parser_version") or 0) >= 3:
            kept = dict(old_nv)
            kept["checked_at_kst"] = dt.datetime.now(KST).isoformat(timespec="seconds")
            return kept, errors

        pdf = fetch(q10_url, 45, "application/pdf")
        reader = PdfReader(io.BytesIO(pdf))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        compact = re.sub(r"[ \t]+", " ", text)

        ar, ar_prev = _first_pair_millions(compact, r"Accounts receivable, net")
        revenue, revenue_prev = _quarter_four_values(compact, r"Revenue")
        net_income, net_income_prev = _quarter_four_values(compact, r"Net income")

        out.update({
            "parsed_ok": True,
            "parser_version": 3,
            "q10_sha256": hashlib.sha256(pdf).hexdigest(),
            "accounts_receivable_m": ar,
            "accounts_receivable_prev_m": ar_prev,
            "revenue_q_m": revenue,
            "revenue_q_prev_m": revenue_prev,
            "net_income_q_m": net_income,
            "net_income_q_prev_m": net_income_prev,
            "supply_commitments_b": _billion(
                compact,
                r"supply commitments[^.]{0,500}?to\s+\$?\s*([\d.]+)\s+billion",
            ),
            "ai_cloud_commitments_b": _billion(
                compact,
                r"commitments[^.]{0,250}typically six years[^.]{0,250}totaled\s+\$?\s*([\d.]+)\s+billion",
            ),
            "ai_cloud_guarantee_b": _billion(
                compact,
                r"maximum gross exposure under all agreements is\s+\$?\s*([\d.]+)\s+billion",
            ),
            "sb_energy_guarantee_b": _billion(
                compact,
                r"SB Energy.*?(?:capped at a total of|capped at)\s+\$?\s*([\d.]+)\s+billion",
            ),
            "equity_investments_b": _billion(
                compact,
                r"equity investments of\s+\$?\s*([\d.]+)\s+billion",
            ),
            "equity_commitments_b": _billion(
                compact,
                r"equity investment commitments of\s+\$?\s*([\d.]+)\s+billion",
            ),
            "customer_finance_language": bool(
                re.search(r"extended payment terms|financial guarantees|credit support|AI cloud", compact, flags=re.I)
            ),
            "checked_at_kst": dt.datetime.now(KST).isoformat(timespec="seconds"),
        })

        if ar is None or revenue is None:
            errors.append("NVIDIA 10-Q 핵심 재무표 파싱 일부 실패")
    except Exception as exc:
        errors.append(f"NVIDIA IR 10-Q: {exc}")
        if old_nv:
            out = dict(old_nv)
            out["stale_due_to_error"] = True
            out["checked_at_kst"] = dt.datetime.now(KST).isoformat(timespec="seconds")
    return out, errors


def google_news(query: str) -> list[dict]:
    params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    root = ET.fromstring(fetch("https://news.google.com/rss/search?" + urllib.parse.urlencode(params)))
    results = []
    for item in root.findall(".//item"):
        title = clean(item.findtext("title"))
        news_link = clean(item.findtext("link"))
        source_node = item.find("source")
        source = clean(source_node.text if source_node is not None else "")
        description = clean(item.findtext("description"))
        published = ""
        try:
            value = parsedate_to_datetime(item.findtext("pubDate") or "")
            if value.tzinfo is None:
                value = value.replace(tzinfo=dt.timezone.utc)
            published = value.astimezone(KST).isoformat(timespec="seconds")
        except Exception:
            pass
        if title and news_link:
            results.append({"title": title, "link": news_link, "source": source, "description": description, "published": published})
    return results


def company_bucket(text: str) -> str:
    lower = text.lower()
    for needle, value in (
        ("microsoft", "Microsoft"), ("meta", "Meta"), ("amazon", "Amazon"),
        ("alphabet", "Alphabet"), ("google", "Alphabet"), ("nvidia", "NVIDIA"),
        ("samsung", "삼성전자"), ("삼성전자", "삼성전자"),
        ("sk hynix", "SK하이닉스"), ("sk하이닉스", "SK하이닉스"),
        ("micron", "Micron"), ("kioxia", "Kioxia"),
    ):
        if needle in lower:
            return value
    return "산업"


def direction_bucket(category: str, text: str) -> str:
    lower = text.lower()
    if any(x in lower for x in ("cut", "lower", "reduce", "delay", "push out", "하향", "축소", "지연")):
        return "약화"
    if category in {"DRAM", "HBM", "NAND"}:
        if any(x in lower for x in ("oversupply", "surplus", "easing", "normalize", "과잉", "완화")):
            return "공급완화"
        if any(x in lower for x in ("shortage", "tight", "deficit", "공급부족", "타이트")):
            return "공급긴축"
    if any(x in lower for x in ("raise", "increase", "expand", "pull in", "상향", "증액", "확대", "앞당")):
        return "강화"
    if any(x in lower for x in ("buyback", "repurchase", "소각", "배당", "주주환원")):
        return "주주환원"
    return "변화"


def news_key(category: str, item: dict) -> str:
    norm = re.sub(r"[^0-9A-Za-z가-힣]+", " ", item["title"].lower())
    norm = re.sub(r"\s+", " ", norm).strip()
    return hashlib.sha256(f"{category}|{norm}|{item.get('source','').lower()}".encode()).hexdigest()[:24]


def _event_tokens(title: str) -> set[str]:
    text = re.sub(r"\s+-\s+[^-]{1,80}$", "", title.lower())
    tokens = re.findall(r"[a-z0-9가-힣]+", text)
    stop = {
        "the", "a", "an", "of", "for", "to", "in", "on", "and", "or", "with",
        "says", "said", "report", "reports", "news", "stock", "shares",
        "전망", "관련", "보도", "기사", "업계", "시장",
    }
    return {x for x in tokens if len(x) >= 2 and x not in stop}


def _same_event(a: dict, b: dict) -> bool:
    if a["category"] != b["category"] or a["company"] != b["company"]:
        return False
    if a["direction"] != b["direction"]:
        return False
    ta, tb = _event_tokens(a["title"]), _event_tokens(b["title"])
    if not ta or not tb:
        return False
    overlap = len(ta & tb) / max(1, len(ta | tb))
    nums_a = set(re.findall(r"\b\d+(?:\.\d+)?%?\b", a["title"]))
    nums_b = set(re.findall(r"\b\d+(?:\.\d+)?%?\b", b["title"]))
    number_match = bool(nums_a & nums_b)
    return overlap >= 0.30 or (overlap >= 0.20 and number_match)


def high_signal_news(old_seen: set[str]) -> tuple[list[dict], set[str], list[str]]:
    now = dt.datetime.now(KST)
    cutoff = now - dt.timedelta(hours=72)
    all_seen = set(old_seen)
    candidates, errors = [], []
    for category, queries in NEWS_QUERIES.items():
        for query in queries:
            try:
                rows = google_news(query)
            except Exception as exc:
                errors.append(f"{category}: {exc}")
                continue
            for item in rows:
                try:
                    published = dt.datetime.fromisoformat(item["published"]) if item["published"] else None
                except Exception:
                    published = None
                if published and published < cutoff:
                    continue
                blob = f"{item['title']} {item['description']} {item['source']}".lower()
                if not any(x in blob for x in CHANGE_WORDS):
                    continue
                if not any(x in blob for x in TRUSTED):
                    continue
                key = news_key(category, item)
                all_seen.add(key)
                item.update({
                    "category": category,
                    "key": key,
                    "company": company_bucket(blob),
                    "direction": direction_bucket(category, blob),
                    "officialish": any(x in item["source"].lower() for x in OFFICIALISH),
                })
                candidates.append(item)

    selected = []
    for item in candidates:
        if item["key"] in old_seen:
            continue
        corroborators = [
            other for other in candidates
            if other["key"] != item["key"]
            and other.get("source", "").lower() != item.get("source", "").lower()
            and _same_event(item, other)
        ]
        sources = {item.get("source", "")}
        sources.update(x.get("source", "") for x in corroborators if x.get("source"))
        official_count = int(bool(item.get("officialish"))) + sum(int(bool(x.get("officialish"))) for x in corroborators)
        trusted_count = len({x.lower() for x in sources if x})
        # Variable investment information is emitted only after same-event corroboration.
        if trusted_count < 2:
            continue
        if official_count == 0 and not any(
            any(t in (x.get("source") or "").lower() for t in ("reuters", "bloomberg", "trendforce", "yonhap", "연합뉴스"))
            for x in [item] + corroborators
        ):
            continue
        item["cross_sources"] = sorted(sources)[:4]
        selected.append(item)

    # Same event can appear several times. Keep one highest-quality/newest representative.
    deduped = []
    for item in sorted(selected, key=lambda x: x.get("published") or "", reverse=True):
        if any(_same_event(item, kept) for kept in deduped):
            continue
        item["link"] = decode_google_news(item.get("link") or "")
        deduped.append(item)
    return deduped[:8], all_seen, errors


def build_signals(old: dict, new: dict, news_items: list[dict]) -> list[tuple]:
    signals = []

    old_crypto, new_crypto = old.get("crypto") or {}, new.get("crypto") or {}
    old_btc = (((old_crypto.get("prices") or {}).get("BTC") or {}).get("usd"))
    new_btc = (((new_crypto.get("prices") or {}).get("BTC") or {}).get("usd"))
    if old_btc and new_btc and (old_btc - BTC_LINE) * (new_btc - BTC_LINE) <= 0 and old_btc != new_btc:
        direction = "상향 돌파" if new_btc > BTC_LINE else "하향 이탈"
        signals.append(("암호화폐", f"BTC가 85,000달러 기준선을 {direction}", f"${old_btc:,.0f} → ${new_btc:,.0f}", "가격 기준선 변화가 실제 주목도 유입·이탈로 이어지는지 ETF와 파생 흐름 확인", "BTC·ETH ETF 5영업일 흐름과 펀딩·미결제약정", None))

    for key, label in (("btc_etf", "BTC"), ("eth_etf", "ETH")):
        before, after = old_crypto.get(key) or {}, new_crypto.get(key) or {}
        a, b = before.get("five_day_usd_m"), after.get("five_day_usd_m")
        before_daily, daily = before.get("daily_usd_m"), after.get("daily_usd_m")
        if a is not None and b is not None:
            trigger_ready = bool(after.get("trigger_ready"))
            changed = (
                after.get("date") != before.get("date")
                or after.get("status") != before.get("status")
                or before_daily is None
                or daily is None
                or abs(float(daily) - float(before_daily)) > 0.6
                or abs(float(b) - float(a)) > 0.6
            )
            sign_flip = a * b < 0 and abs(b) >= 250
            large_day = daily is not None and abs(float(daily)) >= 500
            if trigger_ready and changed and (sign_flip or large_day):
                if sign_flip:
                    direction = "순유출→순유입" if b > 0 else "순유입→순유출"
                    headline = f"{label} 현물 ETF 5영업일 자금흐름이 {direction} 전환"
                else:
                    direction = "순유입" if float(daily) > 0 else "순유출"
                    headline = f"{label} 현물 ETF 당일 대규모 {direction} 확인"
                status_label = "확정" if after.get("status") == "complete" else "부분집계·2회 안정확인"
                signals.append((
                    "암호화폐",
                    headline,
                    f"5영업일 {a:+,.1f} → {b:+,.1f}백만달러, 최신 일간 {float(daily):+,.1f}백만달러 ({status_label})",
                    "가격 변화가 실제 현물 자금과 동행하는지 보는 핵심 확인 지표",
                    f"{label} 가격·거래대금·파생 미결제약정 동행 여부",
                    None,
                ))

    old_deriv, new_deriv = old_crypto.get("derivatives") or {}, new_crypto.get("derivatives") or {}
    for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
        before, after = old_deriv.get(symbol) or {}, new_deriv.get(symbol) or {}
        if before.get("open_interest") and after.get("open_interest") and after.get("funding") is not None:
            oi_change = (float(after["open_interest"]) / float(before["open_interest"]) - 1.0) * 100.0
            coin = symbol.replace("USDT", "")
            price_change = (((new_crypto.get("prices") or {}).get(coin) or {}).get("change24"))
            if abs(oi_change) >= 12 and (abs(float(after["funding"])) >= 0.0005 or (price_change is not None and abs(price_change) >= 4)):
                signals.append(("암호화폐", f"{coin} 파생 레버리지 변화 확대", f"미결제약정 {oi_change:+.1f}%, 펀딩 {float(after['funding'])*100:+.4f}%, 24시간 가격 {fmt_pct(price_change)}", "현물 주목도 회복인지 레버리지 추격인지 구분해야 하는 구간", "현물 거래대금·ETF 자금흐름 동행 여부", None))

    old_rates, new_rates = old.get("rates") or {}, new.get("rates") or {}
    old_nom, new_nom = old_rates.get("nominal10y") or {}, new_rates.get("nominal10y") or {}
    old_real, new_real = old_rates.get("real10y") or {}, new_rates.get("real10y") or {}
    if (
        old_nom.get("date") and new_nom.get("date")
        and old_real.get("date") and new_real.get("date")
        and old_nom["date"] != new_nom["date"]
        and old_real["date"] != new_real["date"]
    ):
        nominal_bp = (float(new_nom["value"]) - float(old_nom["value"])) * 100.0
        real_bp = (float(new_real["value"]) - float(old_real["value"])) * 100.0
        material = (
            abs(nominal_bp) >= 15
            or abs(real_bp) >= 10
            or (nominal_bp * real_bp > 0 and abs(nominal_bp) >= 10 and abs(real_bp) >= 10)
        )
        if material:
            direction = "상승" if nominal_bp > 0 and real_bp > 0 else "하락" if nominal_bp < 0 and real_bp < 0 else "혼조"
            signals.append((
                "나스닥 할인율",
                f"미국 10년 명목·실질금리 동반 {direction}",
                f"명목 {old_nom['value']:.2f}% → {new_nom['value']:.2f}% ({nominal_bp:+.1f}bp), 실질 {old_real['value']:.2f}% → {new_real['value']:.2f}% ({real_bp:+.1f}bp)",
                "실질금리 상승은 미래이익 현재가치를 낮추는 할인율 역풍이고, 하락은 반대로 성장주 재평가 여지",
                "Fed·물가·고용과 빅테크 실적·AI 설비투자 가이던스",
                None,
            ))

    old_nv, new_nv = old.get("nvidia_sec") or {}, new.get("nvidia_sec") or {}
    old_q10 = old_nv.get("q10_url")
    new_q10 = new_nv.get("q10_url")
    if old_q10 and new_q10 and old_q10 != new_q10 and new_nv.get("parsed_ok"):
        def chg(a, b):
            if a is None or b in (None, 0):
                return None
            return (float(a) / float(b) - 1.0) * 100.0

        ar_yoy = chg(new_nv.get("accounts_receivable_m"), new_nv.get("accounts_receivable_prev_m"))
        rev_yoy = chg(new_nv.get("revenue_q_m"), new_nv.get("revenue_q_prev_m"))
        pieces = [
            f"매출채권 {fmt_usd((new_nv.get('accounts_receivable_m') or 0)*1_000_000)} ({fmt_pct(ar_yoy)} YoY)",
            f"분기 매출 {fmt_usd((new_nv.get('revenue_q_m') or 0)*1_000_000)} ({fmt_pct(rev_yoy)} YoY)",
        ]
        for key, label in (
            ("supply_commitments_b", "공급·생산능력 약정"),
            ("ai_cloud_commitments_b", "AI cloud 약정"),
            ("ai_cloud_guarantee_b", "AI cloud 보증"),
            ("sb_energy_guarantee_b", "SB Energy 보증"),
        ):
            value = new_nv.get(key)
            if value is not None:
                pieces.append(f"{label} {value:,.1f}십억달러")
        signals.append((
            "NVIDIA 수요의 질",
            "NVIDIA 신규 10-Q 감지 — 고객금융·매출채권·현금회수 구조 재검증",
            " · ".join(pieces),
            "서한의 NVIDIA 고객지원 우려를 회계 부정이 아니라 수요의 질·현금회수·보증 노출로 공식 재검증",
            "영업현금흐름·매출채권 증가율 vs 매출 증가율·AI cloud 약정·보증 변화",
            new_q10,
        ))

    if old_nv.get("parsed_ok") and new_nv.get("parsed_ok") and old_q10 == new_q10:
        old_ar = old_nv.get("accounts_receivable_m")
        new_ar = new_nv.get("accounts_receivable_m")
        if old_ar and new_ar and old_ar != new_ar:
            signals.append((
                "NVIDIA 수요의 질",
                "동일 10-Q 기준 NVIDIA 매출채권 숫자 재파싱 변화 감지",
                f"{old_ar:,.0f} → {new_ar:,.0f}백만달러",
                "원문 파싱 또는 원문 수정 가능성이 있어 즉시 검산 필요",
                "NVIDIA Investor Relations 10-Q PDF와 SEC 원문 대조",
                new_q10,
            ))

    for item in news_items:
        translated = translate_to_korean(item["title"])
        if not translated:
            continue
        category = item["category"]
        direction = item["direction"]
        if category in {"DRAM", "HBM", "NAND"}:
            if direction == "공급긴축":
                meaning = f"{category} 공급 타이트 지속 가설 강화"
            elif direction == "공급완화":
                meaning = f"{category} 공급 완화 시점이 앞당겨질 가능성"
            else:
                meaning = f"{category} 가격·공급·생산능력 기준선 재검증 필요"
        elif category == "빅테크 AI 설비투자":
            meaning = "AI 설비투자와 가속기 수요의 중기 경로를 바꿀 수 있는 신호"
        else:
            meaning = "삼성전자·SK하이닉스 실제 주주환원 규모와 집행 속도 재검증 필요"
        sources = ", ".join(item.get("cross_sources") or [item.get("source", "")])
        signals.append((category, translated, f"{item['company']} · {direction} · 교차 출처 {sources}", meaning, "공식 공시·실적자료·기업설명자료의 수치와 일정", item.get("link")))

    unique, seen = [], set()
    for signal in signals:
        fingerprint = (signal[0], re.sub(r"\W+", "", signal[1].lower())[:120])
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        unique.append(signal)
    return unique[:12]


def link(url: str | None) -> str:
    if not url:
        return ""
    return f'<a href="{html.escape(url, quote=True)}">원문</a>'


def build_alert(signals: list[tuple], now: dt.datetime, snapshot: dict) -> str:
    lines = [
        "🚨 <b>워뇨띠 90일 서한 변곡 웹감시</b>",
        "━━━━━━━━━━━━━━━━",
        "<b>[무엇이 달라졌나]</b>",
    ]
    for i, (axis, headline, detail, meaning, next_check, url) in enumerate(signals, 1):
        lines.append(f"{i}. <b>{html.escape(axis)}</b> · {html.escape(headline)}")
        lines.append(f"   • 기존 대비 새 숫자/신호: {html.escape(detail)}")
        lines.append(f"   • 서한 가설 영향: {html.escape(meaning)}")
        lines.append(f"   • 다음 확인: {html.escape(next_check)}")
        if url:
            lines.append(f"   • {link(url)}")

    lines += ["", "<b>[현재 숫자]</b>"]
    crypto = snapshot.get("crypto") or {}
    prices = crypto.get("prices") or {}
    if prices.get("BTC"):
        btc, eth, sol = prices["BTC"], prices.get("ETH") or {}, prices.get("SOL") or {}
        lines.append(f"• BTC ${btc['usd']:,.0f} ({fmt_pct(btc.get('change24'))}) · ETH ${eth.get('usd',0):,.0f} ({fmt_pct(eth.get('change24'))}) · SOL ${sol.get('usd',0):,.2f} ({fmt_pct(sol.get('change24'))})")
    for key, label in (("btc_etf", "BTC ETF"), ("eth_etf", "ETH ETF")):
        flow = crypto.get(key) or {}
        if flow:
            status_label = "확정" if flow.get("status") == "complete" else f"부분집계 {flow.get('reported_funds',0)}개/미보고 {flow.get('missing_funds',0)}개"
            lines.append(f"• {label}: {flow.get('date')} 일간 {flow.get('daily_usd_m',0):+,.1f}백만달러 · 5영업일 {flow.get('five_day_usd_m',0):+,.1f}백만달러 · {status_label}")
    deriv = crypto.get("derivatives") or {}
    deriv_parts = []
    for symbol, label in (("BTCUSDT", "BTC"), ("ETHUSDT", "ETH"), ("SOLUSDT", "SOL")):
        item = deriv.get(symbol) or {}
        if item:
            oi_value = float(item.get("open_interest_value") or 0.0)
            funding_pct = float(item.get("funding") or 0.0) * 100.0
            deriv_parts.append(f"{label} 펀딩 {funding_pct:+.4f}% · 미결제약정 {fmt_usd(oi_value)}")
    if deriv_parts:
        lines.append("• 파생: " + " / ".join(deriv_parts))
    rates = snapshot.get("rates") or {}
    if rates.get("nominal10y"):
        lines.append(f"• 미국 10년 명목금리 {rates['nominal10y']['value']:.2f}% ({rates['nominal10y']['date']})")
    if rates.get("real10y"):
        lines.append(f"• 미국 10년 실질금리 {rates['real10y']['value']:.2f}% ({rates['real10y']['date']})")
    nv = snapshot.get("nvidia_sec") or {}
    if nv.get("parsed_ok"):
        ar = nv.get("accounts_receivable_m")
        ar_prev = nv.get("accounts_receivable_prev_m")
        rev = nv.get("revenue_q_m")
        rev_prev = nv.get("revenue_q_prev_m")
        ar_yoy = ((float(ar) / float(ar_prev) - 1.0) * 100.0) if ar is not None and ar_prev not in (None, 0) else None
        rev_yoy = ((float(rev) / float(rev_prev) - 1.0) * 100.0) if rev is not None and rev_prev not in (None, 0) else None
        lines.append(f"• NVIDIA 10-Q: 매출채권 {fmt_usd((ar or 0)*1_000_000)} ({fmt_pct(ar_yoy)} YoY) · 분기 매출 {fmt_usd((rev or 0)*1_000_000)} ({fmt_pct(rev_yoy)} YoY)")
        commitments = []
        for key, label in (
            ("supply_commitments_b", "공급·생산능력 약정"),
            ("ai_cloud_commitments_b", "AI cloud 약정"),
            ("ai_cloud_guarantee_b", "AI cloud 보증"),
            ("sb_energy_guarantee_b", "SB Energy 보증상한"),
        ):
            value = nv.get(key)
            if value is not None:
                commitments.append(f"{label} {float(value):,.1f}십억달러")
        if commitments:
            lines.append("• NVIDIA 약정·보증: " + " · ".join(commitments))

    lines += ["", "<b>[현재 판정]</b>"]
    btc_price = ((prices.get("BTC") or {}).get("usd"))
    btc_flow = (crypto.get("btc_etf") or {}).get("five_day_usd_m")
    if btc_price is not None and btc_flow is not None:
        if float(btc_price) < BTC_LINE and float(btc_flow) > 0:
            lines.append("• BTC는 85,000달러 아래지만 5영업일 ETF는 순유입 → 가격 약세와 현물자금이 엇갈려 ‘주목도 이탈’ 확정 신호는 아직 아님.")
        elif float(btc_price) < BTC_LINE and float(btc_flow) < 0:
            lines.append("• BTC 85,000달러 하회 + 5영업일 ETF 순유출 → 서한의 ‘주목도 이탈’ 위험이 함께 강화.")
        elif float(btc_price) >= BTC_LINE and float(btc_flow) > 0:
            lines.append("• BTC 85,000달러 상회 + 5영업일 ETF 순유입 → 단기 상승·주목도 논리가 함께 유지.")
    lines += [
        "• 단순 가격 등락은 보내지 않고 가격·자금흐름·할인율·공식 공시·공급사슬 변화가 서한의 전제를 바꿀 때만 알립니다.",
        "• 메모리는 DRAM·HBM·NAND를 분리 판정합니다.",
        "• NVIDIA는 회계 부정으로 단정하지 않고 고객금융·매출채권·현금회수·수요의 질 위험으로 구분합니다.",
        "",
        f"<b>조회</b>: {now.strftime('%Y-%m-%d %H:%M:%S KST')}",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ALERT.unlink(missing_ok=True)
    old = load_state()
    now = dt.datetime.now(KST)
    errors = []

    crypto, part = crypto_snapshot()
    errors.extend(part)

    # Farside can update a partially reported day intraday. A partial print must be
    # identical on two consecutive 30-minute checks before it can trigger an alert.
    old_crypto = old.get("crypto") or {}
    for flow_key in ("btc_etf", "eth_etf"):
        current = crypto.get(flow_key) or {}
        previous = old_crypto.get(flow_key) or {}
        same = (
            current.get("date")
            and current.get("date") == previous.get("date")
            and current.get("daily_usd_m") is not None
            and previous.get("daily_usd_m") is not None
            and abs(float(current["daily_usd_m"]) - float(previous["daily_usd_m"])) <= 0.6
        )
        stable_obs = int(previous.get("stable_obs") or 0) + 1 if same else 1
        current["stable_obs"] = stable_obs
        current["trigger_ready"] = current.get("status") == "complete" or stable_obs >= 2
    rates, part = rates_snapshot()
    errors.extend(part)
    nvidia_sec, part = nvidia_ir_snapshot(old.get("nvidia_sec") or {})
    errors.extend(part)
    news_items, seen, part = high_signal_news(set(old.get("news_seen") or []))
    errors.extend(part)

    health = {
        "crypto_prices": bool((crypto.get("prices") or {}).get("BTC")),
        "crypto_derivatives": len(crypto.get("derivatives") or {}) == 3,
        "btc_etf": bool((crypto.get("btc_etf") or {}).get("date")),
        "eth_etf": bool((crypto.get("eth_etf") or {}).get("date")),
        "rates": bool((rates.get("nominal10y") or {}).get("date")) and bool((rates.get("real10y") or {}).get("date")),
        "nvidia_10q": bool(nvidia_sec.get("parsed_ok")),
    }
    old_streaks = old.get("health_error_streaks") or {}
    health_streaks = {
        key: 0 if ok else int(old_streaks.get(key) or 0) + 1
        for key, ok in health.items()
    }

    new_state = {
        "initialized": True,
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "crypto": crypto,
        "rates": rates,
        "nvidia_sec": nvidia_sec,
        "news_seen": sorted(seen)[-5000:],
        "health": health,
        "health_error_streaks": health_streaks,
    }
    write_json(PENDING, new_state)

    signals = []
    if old.get("initialized"):
        signals = build_signals(old, new_state, news_items)

        old_health_streaks = old.get("health_error_streaks") or {}
        for key, streak in health_streaks.items():
            if streak == 2 and int(old_health_streaks.get(key) or 0) < 2:
                labels = {
                    "crypto_prices": "암호화폐 현물가격",
                    "crypto_derivatives": "암호화폐 선물 펀딩·미결제약정",
                    "btc_etf": "BTC 현물 ETF 자금흐름",
                    "eth_etf": "ETH 현물 ETF 자금흐름",
                    "rates": "미국 10년 명목·실질금리",
                    "nvidia_10q": "NVIDIA 공식 10-Q",
                }
                signals.append((
                    "감시원천 이상",
                    f"{labels.get(key, key)} 원천이 2회 연속 조회 실패",
                    "해당 축은 복구 전까지 투자판정 알림을 보류",
                    "데이터 공백을 시장 변화로 오인하지 않도록 기술 경보만 송출",
                    "다음 30분 실행에서 원천 복구 여부",
                    None,
                ))

        if signals:
            ALERT.write_text(build_alert(signals, now, new_state), encoding="utf-8")

    status = [
        "# 워뇨띠 90일 서한 변곡 웹감시",
        f"- 조회: {now.strftime('%Y-%m-%d %H:%M:%S KST')}",
        f"- 이전 기준선 존재: {'예' if old.get('initialized') else '아니오 — 이번 실행은 기준선만 저장'}",
        f"- 신규 고신호: {len(signals)}건",
        f"- 교차검증 뉴스 후보: {len(news_items)}건",
        f"- 부분 조회 오류: {len(errors)}건",
        "- 원천 건강도: " + ", ".join(f"{k}={'정상' if v else '실패'}" for k, v in health.items()),
    ]
    if errors:
        status += ["", "## 부분 조회 오류"] + [f"- {x}" for x in errors[:20]]
    STATUS.write_text("\n".join(status) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
