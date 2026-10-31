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
import statistics
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
BTC_CONFIRM_OBSERVATIONS = 2
BTC_CONFIRM_MIN_SECONDS = 180

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
    """Read Farside daily rows without comparing provisional prints to completed periods."""
    soup = BeautifulSoup(fetch(url).decode("utf-8", errors="replace"), "html.parser")
    rows = []
    today = dt.datetime.now(KST).date()
    for tr in soup.find_all("tr"):
        cells = [clean(x.get_text(" ", strip=True)) for x in tr.find_all(["td", "th"])]
        if len(cells) < 3:
            continue
        day = parse_date(cells[0])
        if not day or day > today:
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
        rows.append({
            "date": day,
            "total": total,
            "status": "complete" if missing == 0 else "partial",
            "reported": reported,
            "missing": missing,
        })

    if len(rows) < 6:
        raise RuntimeError("현재·직전 5영업일 ETF 집계행이 6개 미만")
    rows.sort(key=lambda x: x["date"])
    # The source sometimes publishes a partial current row. Its rolling five-day
    # sum must never be labeled as the previous FULL five-day period.
    latest = rows[-1]
    last5 = rows[-5:]
    prev5 = rows[-6:-1]
    last5_complete = len(last5) == 5 and all(x["status"] == "complete" for x in last5)
    prev5_complete = len(prev5) == 5 and all(x["status"] == "complete" for x in prev5)
    return {
        "date": latest["date"].isoformat(),
        "daily_usd_m": latest["total"],
        "status": latest["status"],
        "reported_funds": latest["reported"],
        "missing_funds": latest["missing"],
        "five_day_usd_m": round(sum(x["total"] for x in last5), 1),
        "five_day_dates": [x["date"].isoformat() for x in last5],
        "five_day_complete": last5_complete,
        "previous_five_day_usd_m": round(sum(x["total"] for x in prev5), 1) if prev5_complete else None,
        "previous_five_day_dates": [x["date"].isoformat() for x in prev5],
        "previous_five_day_complete": prev5_complete,
        "source_url": url,
    }


def coingecko_prices() -> dict:
    raw = fetch_json(COINGECKO)
    return {
        "BTC": {
            "price": float(raw["bitcoin"]["usd"]),
            "change24": float(raw["bitcoin"].get("usd_24h_change") or 0.0),
            "volume24": float(raw["bitcoin"].get("usd_24h_vol") or 0.0),
        },
        "ETH": {
            "price": float(raw["ethereum"]["usd"]),
            "change24": float(raw["ethereum"].get("usd_24h_change") or 0.0),
            "volume24": float(raw["ethereum"].get("usd_24h_vol") or 0.0),
        },
        "SOL": {
            "price": float(raw["solana"]["usd"]),
            "change24": float(raw["solana"].get("usd_24h_change") or 0.0),
            "volume24": float(raw["solana"].get("usd_24h_vol") or 0.0),
        },
    }


def gate_spot_prices() -> dict:
    result = {}
    for coin in ("BTC", "ETH", "SOL"):
        pair = f"{coin}_USDT"
        rows = fetch_json(
            "https://api.gateio.ws/api/v4/spot/tickers?"
            + urllib.parse.urlencode({"currency_pair": pair})
        )
        if not isinstance(rows, list) or not rows:
            raise RuntimeError(f"Gate.io spot ticker empty: ${pair}")
        row = rows[0]
        result[coin] = {
            "price": float(row["last"]),
            "change24": float(row.get("change_percentage") or 0.0),
            "volume24": float(row.get("quote_volume") or 0.0),
        }
    return result


def coinbase_prices() -> dict:
    result = {}
    for coin in ("BTC", "ETH", "SOL"):
        raw = fetch_json(
            "https://api.coinbase.com/v2/exchange-rates?"
            + urllib.parse.urlencode({"currency": coin})
        )
        rates = ((raw.get("data") or {}).get("rates") or {})
        if "USD" not in rates:
            raise RuntimeError(f"Coinbase USD rate missing: ${coin}")
        result[coin] = {"price": float(rates["USD"])}
    return result


def combine_spot_prices(source_map: dict[str, dict]) -> dict:
    combined = {}
    all_verified = True
    source_names = sorted(source_map)
    for coin in ("BTC", "ETH", "SOL"):
        quotes = []
        details = {}
        for source, values in source_map.items():
            row = values.get(coin) or {}
            price = row.get("price")
            if price is None:
                continue
            value = float(price)
            if value <= 0:
                continue
            quotes.append(value)
            details[source] = value

        if not quotes:
            all_verified = False
            continue

        consensus = float(statistics.median(quotes))
        dispersion_pct = (
            (max(quotes) - min(quotes)) / consensus * 100.0
            if len(quotes) >= 2 and consensus > 0
            else None
        )
        verified = len(quotes) >= 2 and dispersion_pct is not None and dispersion_pct <= 0.75
        all_verified = all_verified and verified

        change24 = None
        volume24 = None
        for preferred in ("CoinGecko", "Gate.io Spot"):
            row = (source_map.get(preferred) or {}).get(coin) or {}
            if row.get("change24") is not None and change24 is None:
                change24 = float(row["change24"])
            if row.get("volume24") is not None and volume24 is None:
                volume24 = float(row["volume24"])

        combined[coin] = {
            "usd": consensus,
            "change24": change24,
            "volume24": volume24,
            "verified": verified,
            "source_count": len(quotes),
            "sources": details,
            "dispersion_pct": dispersion_pct,
        }

    return {
        "prices": combined,
        "price_verified": all_verified and len(combined) == 3,
        "price_sources": source_names,
    }


def crypto_snapshot() -> tuple[dict, list[str]]:
    result = {}
    errors = []
    price_sources = {}
    for source_name, loader in (
        ("CoinGecko", coingecko_prices),
        ("Coinbase", coinbase_prices),
        ("Gate.io Spot", gate_spot_prices),
    ):
        try:
            price_sources[source_name] = loader()
        except Exception as exc:
            errors.append(f"{source_name}: {exc}")

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
                "index_price": float(info.get("index_price") or 0.0),
                "mark_price": float(info.get("mark_price") or 0.0),
                "last_price": float(info.get("last_price") or 0.0),
                "open_interest": float(stat.get("open_interest") or info.get("position_size") or 0.0),
                "open_interest_value": float(stat.get("open_interest_usd") or 0.0),
                "turnover24h": float(info.get("trade_size") or 0.0),
                "source": "Gate.io Futures API",
            }
        except Exception as exc:
            errors.append(f"Gate.io {contract}: {exc}")
    result["derivatives"] = deriv

    combined = combine_spot_prices(price_sources)
    result.update(combined)
    result["price_trigger_ready"] = bool(
        ((combined.get("prices") or {}).get("BTC") or {}).get("verified")
    )

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
            kept.pop("stale_due_to_error", None)
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


def btc_threshold_zone(crypto: dict) -> str | None:
    btc = ((crypto.get("prices") or {}).get("BTC") or {})
    if not bool(btc.get("verified")) or not bool(crypto.get("price_trigger_ready")):
        return None
    sources = btc.get("sources") or {}
    values = [float(v) for v in sources.values() if v is not None and float(v) > 0]
    if len(values) < 2:
        return None
    if all(v > BTC_LINE for v in values):
        return "above"
    if all(v < BTC_LINE for v in values):
        return "below"
    return "mixed"


def _parse_state_dt(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=KST)
        return parsed.astimezone(KST)
    except Exception:
        return None


def advance_btc_threshold_state(
    old_state: dict | None,
    crypto: dict,
    now: dt.datetime,
) -> tuple[dict, dict | None]:
    """Require a true spot quorum and persistence before confirming an 85k regime change."""
    old_state = old_state or {}
    btc = ((crypto.get("prices") or {}).get("BTC") or {})
    price = btc.get("usd")
    verified = bool(btc.get("verified")) and bool(crypto.get("price_trigger_ready"))

    state = {
        "confirmed_side": old_state.get("confirmed_side"),
        "last_confirmed_at": old_state.get("last_confirmed_at"),
        "last_confirmed_price": old_state.get("last_confirmed_price"),
        "candidate_side": old_state.get("candidate_side"),
        "candidate_count": int(old_state.get("candidate_count") or 0),
        "candidate_first_seen": old_state.get("candidate_first_seen"),
        "candidate_first_price": old_state.get("candidate_first_price"),
    }

    def clear_candidate() -> None:
        state["candidate_side"] = None
        state["candidate_count"] = 0
        state["candidate_first_seen"] = None
        state["candidate_first_price"] = None

    if not verified or price is None:
        clear_candidate()
        return state, None

    price = float(price)
    zone = btc_threshold_zone(crypto)
    confirmed = state.get("confirmed_side")

    if confirmed not in {"above", "below"}:
        if zone not in {"above", "below"}:
            clear_candidate()
            return state, None
        confirmed = zone
        state["confirmed_side"] = confirmed
        state["last_confirmed_at"] = now.isoformat(timespec="seconds")
        state["last_confirmed_price"] = price
        clear_candidate()
        return state, None

    if zone == "mixed" or zone is None:
        clear_candidate()
        return state, None

    if zone == confirmed:
        clear_candidate()
        return state, None

    if state.get("candidate_side") == zone:
        first_seen = _parse_state_dt(state.get("candidate_first_seen")) or now
        first_price = float(state.get("candidate_first_price") or price)
        count = int(state.get("candidate_count") or 0) + 1
    else:
        first_seen = now
        first_price = price
        count = 1

    state["candidate_side"] = zone
    state["candidate_count"] = count
    state["candidate_first_seen"] = first_seen.isoformat(timespec="seconds")
    state["candidate_first_price"] = first_price

    elapsed = max(0.0, (now - first_seen).total_seconds())
    if count < BTC_CONFIRM_OBSERVATIONS or elapsed < BTC_CONFIRM_MIN_SECONDS:
        return state, None

    event = {
        "from_side": confirmed,
        "to_side": zone,
        "first_price": first_price,
        "confirmed_price": price,
        "observations": count,
        "elapsed_seconds": elapsed,
    }
    state["confirmed_side"] = zone
    state["last_confirmed_at"] = now.isoformat(timespec="seconds")
    state["last_confirmed_price"] = price
    clear_candidate()
    return state, event


def build_signals(old: dict, new: dict, news_items: list[dict], btc_threshold_event: dict | None = None) -> list[tuple]:
    signals = []

    old_crypto, new_crypto = old.get("crypto") or {}, new.get("crypto") or {}
    if btc_threshold_event:
        direction = "상향 돌파" if btc_threshold_event.get("to_side") == "above" else "하향 이탈"
        first_price = float(btc_threshold_event.get("first_price") or 0.0)
        confirmed_price = float(btc_threshold_event.get("confirmed_price") or 0.0)
        observations = int(btc_threshold_event.get("observations") or 0)
        elapsed_min = float(btc_threshold_event.get("elapsed_seconds") or 0.0) / 60.0
        signals.append((
            "암호화폐",
            f"BTC가 85,000달러 기준선을 {direction} — 지속 확인",
            f"1차 ${first_price:,.0f} → 확인 ${confirmed_price:,.0f} · 현물원천 전부 같은 방향 · 연속 {observations}회 · {elapsed_min:.1f}분 지속",
            "한 번의 기준선 터치가 아니라 복수 현물 원천과 시간 지속성이 확인된 가격 레짐 변화",
            "BTC·ETH ETF 5영업일 흐름과 펀딩·미결제약정이 같은 방향으로 확인되는지",
            None,
        ))

    for key, label in (("btc_etf", "BTC"), ("eth_etf", "ETH")):
        before, after = old_crypto.get(key) or {}, new_crypto.get(key) or {}
        new5 = after.get("five_day_usd_m")
        previous_full5 = after.get("previous_five_day_usd_m")
        daily = after.get("daily_usd_m")
        if new5 is None or daily is None or previous_full5 is None:
            continue
        if not bool(after.get("trigger_ready")):
            continue
        before_daily = before.get("daily_usd_m")
        changed = (
            after.get("date") != before.get("date")
            or after.get("status") != before.get("status")
            or before_daily is None
            or abs(float(daily) - float(before_daily)) >= 10
        )
        flip = float(previous_full5) * float(new5) < 0 and (
            abs(float(new5)) >= 100 or abs(float(daily)) >= 300
        )
        big_day = abs(float(daily)) >= 500
        if not changed or not (flip or big_day):
            continue

        complete5 = bool(after.get("five_day_complete"))
        stage = "확정" if complete5 else "잠정·추가 집계 중"
        signal_direction = "순유출" if float(new5) < 0 else "순유입"
        if flip:
            prior_direction = "순유입" if float(previous_full5) > 0 else "순유출"
            headline = f"{label} ETF 최근 5거래일 {prior_direction}에서 {signal_direction}로 전환"
        else:
            direction_day = "순유출" if float(daily) < 0 else "순유입"
            headline = f"{label} ETF 당일 큰 규모의 {direction_day}"

        prev_dates = after.get("previous_five_day_dates") or []
        curr_dates = after.get("five_day_dates") or []
        prev_period = f"{prev_dates[0]}~{prev_dates[-1]}" if len(prev_dates) == 5 else "직전 완료 기간"
        curr_period = f"{curr_dates[0]}~{curr_dates[-1]}" if len(curr_dates) == 5 else "최근 기간"
        details = (
            f"이전 5거래일({prev_period}) {float(previous_full5):+,.1f}백만달러 "
            f"→ 최근 5거래일({curr_period}) {float(new5):+,.1f}백만달러; "
            f"최신 거래일 {float(daily):+,.1f}백만달러 ({stage})"
        )
        signals.append((
            "암호화폐",
            headline,
            details,
            "ETF 자금흐름 변화로 단기 매수·매도 압력의 방향을 재평가",
            "가격·ETF 5거래일 방향이 함께 유지되는지, 반대 흐름으로 돌아서는지",
            after.get("source_url"),
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


def _read_official_fx(target: str | None) -> dict | None:
    """Use an existing date-matched BOK ECOS observation; never invent FX."""
    if not target:
        return None
    try:
        file = ROOT / "data" / "korea_market_stress_watch_state.json"
        state = json.loads(file.read_text(encoding="utf-8"))
        row = (((state.get("snapshot") or {}).get("usdkrw") or {}).get("ecos_official") or {})
        day = dt.date.fromisoformat(str(row.get("date") or ""))
        needed = dt.date.fromisoformat(target)
        rate = float(row.get("value") or 0.0)
        if (
            row.get("stat_code") == "731Y001"
            and row.get("item_code") == "0000001"
            and 0 <= (needed - day).days <= 4
            and 800.0 <= rate <= 2500.0
        ):
            return {"rate": rate, "date": day.isoformat(), "source": "한국은행 ECOS"}
    except Exception:
        return None
    return None


def _money_usd_m(value: float | None, fx: dict | None = None) -> str:
    if value is None:
        return "확인 불가"
    amount = float(value)
    sign = "-" if amount < 0 else "+" if amount > 0 else ""
    ten_thousands = int(round(abs(amount) * 100))
    hundred_million, ten_thousand = divmod(ten_thousands, 10_000)
    if hundred_million:
        display = f"{hundred_million:,}억"
        if ten_thousand:
            display += f"{ten_thousand:,}만"
    else:
        display = f"{ten_thousand:,}만"
    usd_text = f"{sign}{display}달러"
    if fx and fx.get("rate"):
        eok = int(round(abs(amount) * float(fx["rate"]) / 100.0))
        krw_sign = "-" if amount < 0 else "+" if amount > 0 else ""
        return usd_text + f"(약 {krw_sign}{eok:,}억원)"
    return usd_text


def _fresh_enough(date_str: str | None, now: dt.datetime, max_days: int = 4) -> bool:
    if not date_str:
        return False
    try:
        age = (now.date() - dt.date.fromisoformat(date_str)).days
        return 0 <= age <= max_days
    except Exception:
        return False


def _crypto_direction(snapshot: dict, now: dt.datetime) -> dict:
    """Plain-language pressure assessment, not a price forecast or buy/sell instruction."""
    crypto = snapshot.get("crypto") or {}
    prices = crypto.get("prices") or {}
    btc = prices.get("BTC") or {}
    etf = crypto.get("btc_etf") or {}
    valid_price = bool(btc.get("verified")) and bool(crypto.get("price_trigger_ready"))
    valid_flow = (
        _fresh_enough(etf.get("date"), now)
        and bool(etf.get("five_day_complete"))
        and etf.get("five_day_usd_m") is not None
    )
    if not valid_price or not valid_flow:
        return {
            "direction": "판단 보류",
            "reason": "현물가격 또는 확정 5거래일 ETF 자금흐름 확인이 불충분",
            "next": "현물가격 교차검증과 5거래일 ETF 집계 완료를 먼저 확인",
        }
    price = float(btc["usd"])
    five = float(etf["five_day_usd_m"])
    if price < BTC_LINE and five < 0:
        return {
            "direction": "단기 하락 압력 우세",
            "reason": "BTC가 서한의 적정가보다 낮고 최근 5거래일 ETF에도 자금이 순유출",
            "next": "약세 완화 신호: 5거래일 ETF 순유입 전환과 BTC 8만5,000달러 회복 여부를 함께 확인",
        }
    if price < BTC_LINE and five >= 0:
        return {
            "direction": "혼조 — 가격은 약하지만 ETF 자금은 유입",
            "reason": "서한의 적정가 아래이지만 현물 ETF는 아직 자금 유입",
            "next": "ETF 순유입이 유지되며 가격이 회복하는지, 반대로 ETF까지 순유출로 바뀌는지 확인",
        }
    if price >= BTC_LINE and five > 0:
        return {
            "direction": "단기 회복 신호 우세",
            "reason": "BTC가 서한 적정가 위이고 최근 5거래일 ETF도 순유입",
            "next": "자금 유입과 가격 회복이 추가 거래일에도 이어지는지 확인",
        }
    return {
        "direction": "혼조 — 가격은 회복했지만 ETF는 순유출",
        "reason": "가격과 현물자금 흐름이 일치하지 않아 상승 지속성 확인 부족",
        "next": "ETF 5거래일 순유입 복귀 여부와 가격 유지 여부를 함께 확인",
    }


def build_alert(signals: list[tuple], now: dt.datetime, snapshot: dict) -> str:
    """Put the current direction and next reversal condition before raw statistics."""
    axes = {s[0] for s in signals}
    market_axes = axes - {"감시원천 이상", "감시원천 복구"}
    health_only = bool(axes) and not market_axes
    crypto_event = "암호화폐" in axes
    rate_event = "나스닥 할인율" in axes
    nvidia_event = "NVIDIA 수요의 질" in axes
    memory_event = any(x in axes for x in ("DRAM", "HBM", "NAND"))
    korea_event = "한국 주주환원" in axes

    crypto = snapshot.get("crypto") or {}
    prices = crypto.get("prices") or {}
    btc = prices.get("BTC") or {}
    btc_flow = crypto.get("btc_etf") or {}
    eth_flow = crypto.get("eth_etf") or {}
    fx = _read_official_fx(btc_flow.get("date"))
    overview = _crypto_direction(snapshot, now)

    lines = ["<b>워뇨띠 90일 서한 · 중요한 변화</b>", "━━━━━━━━━━━━━━━━"]
    if health_only:
        lines.extend([
            "<b>[현재 상태] 감시 자료 이상 또는 복구</b>",
            "• 시장이 급등·급락했다는 뜻이 아니라 자료 확인 상태가 달라졌다는 기술 알림입니다.",
            "• 해당 자료가 정상화되기 전에는 해당 축의 새로운 투자 판단을 보류합니다.",
        ])
    else:
        lines.append("<b>[지금 방향 — 먼저 읽기]</b>")
        if crypto_event:
            lines.append(f"• 암호화폐 단기(수일~1주): <b>{html.escape(overview['direction'])}</b>")
            lines.append(f"• 이유: {html.escape(overview['reason'])}")
            lines.append("• 중기(수주~3개월): 아직 확정할 수 없음. 하루 ETF 유출만으로 장기 하락을 단정하지 않습니다.")
            lines.append("• 나스닥·코스피: 이번 암호화폐 신호만으로 두 지수의 방향이 정해지는 것은 아닙니다.")
        if rate_event:
            nom = ((snapshot.get("rates") or {}).get("nominal10y") or {}).get("value")
            real = ((snapshot.get("rates") or {}).get("real10y") or {}).get("value")
            rate_signal = next((x for x in signals if x[0] == "나스닥 할인율"), None)
            direction = "상승" if rate_signal and "상승" in rate_signal[1] else "하락" if rate_signal and "하락" in rate_signal[1] else "혼조"
            effect = "나스닥 성장주에 단기 부담" if direction == "상승" else "나스닥 성장주에 단기 우호적" if direction == "하락" else "나스닥 영향 혼재"
            lines.append(f"• 금리: {effect} — 미국 10년 명목 {nom if nom is not None else '미확인'}%, 실질 {real if real is not None else '미확인'}%")
        if nvidia_event:
            lines.append("• NVIDIA: 고객금융·매출채권·보증 노출의 질을 재점검할 사건이며, 회계부정 또는 나스닥 하락 확정은 아닙니다.")
        if memory_event:
            lines.append("• 메모리: DRAM·HBM·NAND 중 바뀐 항목만 아래에 표시합니다. 메모리 전체의 동반 하락·상승으로 단정하지 않습니다.")
        if korea_event:
            lines.append("• 코스피: 주주환원 기대에 영향을 줄 가능성이 있으나 실제 집행과 회사 공식 공시를 따로 확인해야 합니다.")

    lines.extend(["", "<b>[이번에 실제 바뀐 내용]</b>"])
    for i, (axis, headline, detail, meaning, next_check, url) in enumerate(signals[:12], 1):
        lines.append(f"{i}. <b>{html.escape(axis)} · {html.escape(headline)}</b>")
        lines.append(f"   {html.escape(detail)}")
        if not health_only and axis != "암호화폐":
            lines.append(f"   의미: {html.escape(meaning)}")
        if url:
            lines.append(f"   {link(url)}")

    if crypto_event:
        lines.extend(["", "<b>[지금 숫자로 확인]</b>"])
        if btc.get("usd") is not None:
            btc_value = float(btc["usd"])
            lines.append(
                f"• BTC {btc_value:,.0f}달러 ({fmt_pct(btc.get('change24'))} / 24시간), "
                f"서한의 적정가 85,000달러 대비 {((btc_value / BTC_LINE) - 1) * 100:+.1f}%"
            )
        if (prices.get("ETH") or {}).get("usd") is not None and (prices.get("SOL") or {}).get("usd") is not None:
            eth = prices["ETH"]
            sol = prices["SOL"]
            lines.append(
                f"• ETH {float(eth['usd']):,.0f}달러 ({fmt_pct(eth.get('change24'))}), "
                f"SOL {float(sol['usd']):,.2f}달러 ({fmt_pct(sol.get('change24'))})"
            )
        for label, flow in (("BTC", btc_flow), ("ETH", eth_flow)):
            if flow.get("daily_usd_m") is None:
                continue
            status = "확정" if flow.get("five_day_complete") else "잠정"
            lines.append(
                f"• {label} ETF {flow.get('date')}: 당일 {_money_usd_m(flow.get('daily_usd_m'), fx)} "
                f"/ 최근 5거래일 {_money_usd_m(flow.get('five_day_usd_m'), fx)} ({status})"
            )
        if fx:
            lines.append(f"• 원화 환산: {fx['date']} 한국은행 매매기준율 1달러={fx['rate']:,.2f}원")
        lines.append("• 주의: 85,000달러는 서한 작성자의 추정 적정가이며 확정된 기술적 지지선이 아닙니다.")
        if btc_flow.get("five_day_complete") and eth_flow.get("five_day_complete"):
            if (btc_flow.get("five_day_usd_m") or 0) < 0 and (eth_flow.get("five_day_usd_m") or 0) < 0:
                lines.append("• BTC와 ETH ETF가 함께 순유출이어서 암호화폐 전반의 자금 이탈 위험도 커진 상태입니다.")
    if nvidia_event:
        nv = snapshot.get("nvidia_sec") or {}
        if nv.get("parsed_ok"):
            lines.extend([
                "",
                "<b>[NVIDIA 공식 공시 확인]</b>",
                f"• 매출채권 {fmt_usd((nv.get('accounts_receivable_m') or 0) * 1_000_000)}, 분기 매출 {fmt_usd((nv.get('revenue_q_m') or 0) * 1_000_000)}",
                f"• 공급·생산능력 약정 {nv.get('supply_commitments_b')}십억달러, AI 클라우드 약정 {nv.get('ai_cloud_commitments_b')}십억달러",
            ])

    if not health_only:
        lines.extend(["", "<b>[무엇이 바뀌면 판단을 수정하나]</b>"])
        if crypto_event:
            lines.append("• " + html.escape(overview["next"]))
            lines.append("• 추가 악화 신호: ETF 5거래일 순유출 지속과 BTC 가격 약세가 동시에 이어질 때")
        if rate_event:
            lines.append("• 금리 상승·하락의 지속성과 빅테크 예상이익·AI 설비투자 전망의 동반 변화를 확인")
        if memory_event:
            lines.append("• 반도체 계약가격·고객 검증·재고·실제 신규 설비 가동 시점을 재확인")
        if nvidia_event:
            lines.append("• 다음 공식 분기보고서의 매출채권·영업현금흐름·고객 보증 증감을 확인")
        if korea_event:
            lines.append("• 삼성전자·SK하이닉스의 실제 배당·자사주 매입·소각 집행 공시 확인")
    lines.append(f"\n<b>조회</b>: {now.strftime('%Y-%m-%d %H:%M:%S KST')}")
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
    # identical on two consecutive successful checks before it can trigger an alert.
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
    news_items, seen, news_errors = high_signal_news(set(old.get("news_seen") or []))
    errors.extend(news_errors)

    btc_threshold_state, btc_threshold_event = advance_btc_threshold_state(
        old.get("btc_threshold_state") or {},
        crypto,
        now,
    )

    def fresh_date(value: str | None, max_age_days: int = 4) -> bool:
        if not value:
            return False
        try:
            day = dt.date.fromisoformat(value)
        except Exception:
            return False
        age = (now.date() - day).days
        return 0 <= age <= max_age_days

    deriv_health = True
    deriv = crypto.get("derivatives") or {}
    for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
        item = deriv.get(symbol) or {}
        if (
            float(item.get("index_price") or 0.0) <= 0
            or float(item.get("open_interest_value") or 0.0) <= 0
            or item.get("funding") is None
        ):
            deriv_health = False

    health = {
        "crypto_prices": bool(crypto.get("price_verified")),
        "crypto_derivatives": deriv_health and len(crypto.get("derivatives") or {}) == 3,
        "btc_etf": fresh_date((crypto.get("btc_etf") or {}).get("date")),
        "eth_etf": fresh_date((crypto.get("eth_etf") or {}).get("date")),
        "rates": (
            fresh_date((rates.get("nominal10y") or {}).get("date"))
            and fresh_date((rates.get("real10y") or {}).get("date"))
        ),
        "nvidia_10q": bool(nvidia_sec.get("parsed_ok")) and not bool(nvidia_sec.get("stale_due_to_error")),
        "news_search": len(news_errors) == 0,
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
        "btc_threshold_state": btc_threshold_state,
        "health": health,
        "health_error_streaks": health_streaks,
    }
    write_json(PENDING, new_state)

    signals = []
    if old.get("initialized"):
        signals = build_signals(old, new_state, news_items, btc_threshold_event)

        old_health_streaks = old.get("health_error_streaks") or {}
        labels = {
            "crypto_prices": "암호화폐 현물가격",
            "crypto_derivatives": "암호화폐 선물 펀딩·미결제약정",
            "btc_etf": "BTC 현물 ETF 자금흐름",
            "eth_etf": "ETH 현물 ETF 자금흐름",
            "rates": "미국 10년 명목·실질금리",
            "nvidia_10q": "NVIDIA 공식 10-Q",
            "news_search": "빅테크·메모리·주주환원 뉴스 교차검색",
        }
        for key, streak in health_streaks.items():
            old_streak = int(old_health_streaks.get(key) or 0)
            if streak == 2 and old_streak < 2:
                signals.append((
                    "감시원천 이상",
                    f"{labels.get(key, key)} 원천이 2회 연속 조회 실패",
                    "해당 축은 복구 전까지 투자판정 알림을 보류",
                    "데이터 공백을 시장 변화로 오인하지 않도록 기술 경보만 송출",
                    "다음 15분 실행 또는 독립 감시자 재호출에서 원천 복구 여부",
                    None,
                ))
            elif streak == 0 and old_streak >= 2:
                recovery_detail = "복수 원천 교차검증 정상" if key == "crypto_prices" else "원천 조회 정상"
                signals.append((
                    "감시원천 복구",
                    f"{labels.get(key, key)} 원천이 복구됨",
                    recovery_detail,
                    "기술 장애가 해소되어 해당 축의 투자판정 재개",
                    "다음 실행에서도 연속 정상 여부 확인",
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
        (
            "- BTC 85,000달러 확인상태: "
            f"확정={btc_threshold_state.get('confirmed_side') or '미정'}, "
            f"후보={btc_threshold_state.get('candidate_side') or '없음'}, "
            f"연속확인={btc_threshold_state.get('candidate_count') or 0}회"
        ),
        "- 원천 건강도: " + ", ".join(f"{k}={'정상' if v else '실패'}" for k, v in health.items()),
    ]
    if errors:
        status += ["", "## 부분 조회 오류"] + [f"- {x}" for x in errors[:20]]
    STATUS.write_text("\n".join(status) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
