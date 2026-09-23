#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import pathlib
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

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
SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK0001045810.json"
SEC_COMPANYFACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK0001045810.json"

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
        fund_values = [parse_number(x) for x in cells[1:-1] if x not in {"", "-", "—"}]
        total = parse_number(cells[-1])
        if not fund_values or total is None:
            continue
        recomputed = round(sum(x for x in fund_values if x is not None), 1)
        if abs(recomputed - total) > 1.0:
            continue
        rows.append((day, total))
    if len(rows) < 5:
        raise RuntimeError("검증 가능한 ETF 행이 5개 미만")
    rows.sort(key=lambda x: x[0])
    last5 = rows[-5:]
    return {
        "date": rows[-1][0].isoformat(),
        "daily_usd_m": rows[-1][1],
        "five_day_usd_m": round(sum(x[1] for x in last5), 1),
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
    for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
        try:
            premium = fetch_json(f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={symbol}")
            oi = fetch_json(f"https://fapi.binance.com/fapi/v1/openInterest?symbol={symbol}")
            deriv[symbol] = {
                "funding": float(premium.get("lastFundingRate") or 0.0),
                "open_interest": float(oi.get("openInterest") or 0.0),
            }
        except Exception as exc:
            errors.append(f"Binance {symbol}: {exc}")
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


def latest_point_fact(usgaap: dict, tag: str) -> dict | None:
    entries = usgaap.get(tag, {}).get("units", {}).get("USD", [])
    values = [x for x in entries if x.get("form") in {"10-Q", "10-K"} and x.get("end") and x.get("val") is not None]
    if not values:
        return None
    values.sort(key=lambda x: (x.get("end", ""), x.get("filed", "")))
    latest = values[-1]
    target = dt.date.fromisoformat(latest["end"]) - dt.timedelta(days=365)
    prior = None
    for row in values:
        try:
            d = dt.date.fromisoformat(row["end"])
        except Exception:
            continue
        if abs((d - target).days) <= 45:
            prior = row
    yoy = None
    if prior and float(prior["val"]) != 0:
        yoy = (float(latest["val"]) / float(prior["val"]) - 1.0) * 100.0
    return {"end": latest["end"], "value": float(latest["val"]), "yoy": yoy}


def latest_quarter_fact(usgaap: dict, tags: tuple[str, ...]) -> dict | None:
    candidates = []
    for tag in tags:
        for row in usgaap.get(tag, {}).get("units", {}).get("USD", []):
            frame = str(row.get("frame") or "")
            if row.get("form") == "10-Q" and re.fullmatch(r"CY\d{4}Q[1-4]", frame) and row.get("val") is not None:
                candidates.append((frame, tag, row))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    frame, tag, latest = candidates[-1]
    year = int(frame[2:6])
    prior_frame = f"CY{year-1}{frame[-2:]}"
    prior = next((row for f, t, row in reversed(candidates) if f == prior_frame and t == tag), None)
    yoy = None
    if prior and float(prior["val"]) != 0:
        yoy = (float(latest["val"]) / float(prior["val"]) - 1.0) * 100.0
    return {"frame": frame, "value": float(latest["val"]), "yoy": yoy}


def nvidia_sec_snapshot() -> tuple[dict, list[str]]:
    out, errors = {}, []
    try:
        submissions = fetch_json(SEC_SUBMISSIONS)
        recent = submissions.get("filings", {}).get("recent", {})
        for form, accession, document, filed in zip(
            recent.get("form") or [],
            recent.get("accessionNumber") or [],
            recent.get("primaryDocument") or [],
            recent.get("filingDate") or [],
        ):
            if form in {"10-Q", "10-K"}:
                out["latest_filing"] = {
                    "form": form,
                    "accession": accession,
                    "filed": filed,
                    "url": "https://www.sec.gov/Archives/edgar/data/1045810/" + accession.replace("-", "") + "/" + document,
                }
                break
    except Exception as exc:
        errors.append(f"SEC submissions: {exc}")

    try:
        facts = fetch_json(SEC_COMPANYFACTS)
        usgaap = facts.get("facts", {}).get("us-gaap", {})
        out["accounts_receivable"] = latest_point_fact(usgaap, "AccountsReceivableNetCurrent")
        out["revenue"] = latest_quarter_fact(usgaap, ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"))
        out["net_income"] = latest_quarter_fact(usgaap, ("NetIncomeLoss", "ProfitLoss"))
    except Exception as exc:
        errors.append(f"SEC companyfacts: {exc}")
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
            results.append({"title": title, "link": decode_google_news(news_link), "source": source, "description": description, "published": published})
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
                    "officialish": any(x in blob for x in OFFICIALISH),
                })
                candidates.append(item)

    groups = {}
    for item in candidates:
        groups.setdefault((item["category"], item["company"], item["direction"]), []).append(item)

    selected = []
    for items in groups.values():
        sources = {x["source"].lower() for x in items if x.get("source")}
        new_items = [x for x in items if x["key"] not in old_seen]
        if not new_items:
            continue
        if not (any(x.get("officialish") for x in items) or len(sources) >= 2):
            continue
        new_items.sort(key=lambda x: x.get("published") or "", reverse=True)
        best = new_items[0]
        best["cross_sources"] = sorted({x["source"] for x in items if x.get("source")})[:4]
        selected.append(best)

    selected.sort(key=lambda x: x.get("published") or "", reverse=True)
    return selected[:8], all_seen, errors


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
        daily = after.get("daily_usd_m")
        if a is not None and b is not None:
            if (a * b < 0 and abs(b) >= 250) or (daily is not None and abs(daily) >= 500):
                direction = "순유입" if b > 0 else "순유출"
                signals.append(("암호화폐", f"{label} 현물 ETF 자금흐름이 {direction} 쪽으로 의미 있게 이동", f"5영업일 {a:+,.1f} → {b:+,.1f}백만달러, 최신 일간 {daily:+,.1f}백만달러", "가격 변화가 실제 현물 자금과 동행하는지 보는 핵심 확인 지표", f"{label} 가격·거래대금·파생 미결제약정 동행 여부", None))

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
    for key, label in (("nominal10y", "미국 10년 명목금리"), ("real10y", "미국 10년 실질금리")):
        before, after = old_rates.get(key) or {}, new_rates.get(key) or {}
        if before.get("date") and after.get("date") and before["date"] != after["date"]:
            bp = (float(after["value"]) - float(before["value"])) * 100.0
            if abs(bp) >= 20:
                signals.append(("나스닥 할인율", f"{label} 하루 변동 {bp:+.1f}bp", f"{before['date']} {before['value']:.2f}% → {after['date']} {after['value']:.2f}%", "실질금리 급등은 고평가 성장주의 할인율 역풍, 급락은 반대로 재평가 여지", "Fed·물가·고용과 Nasdaq-100 선행이익 추정 변화", None))

    old_nv, new_nv = old.get("nvidia_sec") or {}, new.get("nvidia_sec") or {}
    old_acc = (old_nv.get("latest_filing") or {}).get("accession")
    new_filing = new_nv.get("latest_filing") or {}
    if old_acc and new_filing.get("accession") and old_acc != new_filing["accession"]:
        ar = new_nv.get("accounts_receivable") or {}
        revenue = new_nv.get("revenue") or {}
        detail = f"매출채권 {fmt_usd(ar.get('value'))} ({fmt_pct(ar.get('yoy'))} YoY), 분기 매출 {fmt_usd(revenue.get('value'))} ({fmt_pct(revenue.get('yoy'))} YoY)"
        signals.append(("NVIDIA 수요의 질", f"NVIDIA 신규 {new_filing.get('form')} 제출", detail, "고객금융·매출채권·구매약정·현금회수의 질을 공식 공시로 재검증하는 게이트", "영업현금흐름·보증·클라우드 용량구매·공급능력 약정 문구", new_filing.get("url")))

    ar, revenue = new_nv.get("accounts_receivable") or {}, new_nv.get("revenue") or {}
    if ar.get("yoy") is not None and revenue.get("yoy") is not None:
        gap = float(ar["yoy"]) - float(revenue["yoy"])
        old_ar, old_revenue = old_nv.get("accounts_receivable") or {}, old_nv.get("revenue") or {}
        old_gap = None
        if old_ar.get("yoy") is not None and old_revenue.get("yoy") is not None:
            old_gap = float(old_ar["yoy"]) - float(old_revenue["yoy"])
        if gap >= 15 and (old_gap is None or old_gap < 15):
            signals.append(("NVIDIA 수요의 질", "NVIDIA 매출채권 증가율이 분기 매출 증가율을 15%p 이상 상회", f"매출채권 {ar['yoy']:+.1f}% YoY vs 분기 매출 {revenue['yoy']:+.1f}% YoY, 격차 {gap:+.1f}%p", "현금회수 속도와 고객금융 의존도 점검 강도를 높여야 하는 신호", "영업현금흐름/순이익·DSO·고객별 매출 집중도", None))

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
            lines.append(f"• {label}: {flow.get('date')} 일간 {flow.get('daily_usd_m',0):+,.1f}백만달러 · 5영업일 {flow.get('five_day_usd_m',0):+,.1f}백만달러")
    rates = snapshot.get("rates") or {}
    if rates.get("nominal10y"):
        lines.append(f"• 미국 10년 명목금리 {rates['nominal10y']['value']:.2f}% ({rates['nominal10y']['date']})")
    if rates.get("real10y"):
        lines.append(f"• 미국 10년 실질금리 {rates['real10y']['value']:.2f}% ({rates['real10y']['date']})")
    nv = snapshot.get("nvidia_sec") or {}
    if nv.get("accounts_receivable"):
        ar = nv["accounts_receivable"]
        lines.append(f"• NVIDIA 매출채권 {fmt_usd(ar.get('value'))} · YoY {fmt_pct(ar.get('yoy'))}")
    if nv.get("revenue"):
        revenue = nv["revenue"]
        lines.append(f"• NVIDIA 분기 매출 {fmt_usd(revenue.get('value'))} · YoY {fmt_pct(revenue.get('yoy'))}")

    lines += [
        "",
        "<b>[현재 판정]</b>",
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
    rates, part = rates_snapshot()
    errors.extend(part)
    nvidia_sec, part = nvidia_sec_snapshot()
    errors.extend(part)
    news_items, seen, part = high_signal_news(set(old.get("news_seen") or []))
    errors.extend(part)

    new_state = {
        "initialized": True,
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "crypto": crypto,
        "rates": rates,
        "nvidia_sec": nvidia_sec,
        "news_seen": sorted(seen)[-5000:],
    }
    write_json(PENDING, new_state)

    signals = []
    if old.get("initialized"):
        signals = build_signals(old, new_state, news_items)
        if signals:
            ALERT.write_text(build_alert(signals, now, new_state), encoding="utf-8")

    status = [
        "# 워뇨띠 90일 서한 변곡 웹감시",
        f"- 조회: {now.strftime('%Y-%m-%d %H:%M:%S KST')}",
        f"- 이전 기준선 존재: {'예' if old.get('initialized') else '아니오 — 이번 실행은 기준선만 저장'}",
        f"- 신규 고신호: {len(signals)}건",
        f"- 교차검증 뉴스 후보: {len(news_items)}건",
        f"- 부분 조회 오류: {len(errors)}건",
    ]
    if errors:
        status += ["", "## 부분 조회 오류"] + [f"- {x}" for x in errors[:20]]
    STATUS.write_text("\n".join(status) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
