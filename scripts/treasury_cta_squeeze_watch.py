#!/usr/bin/env python3
"""Monitor the Treasury CTA short-squeeze hypothesis.

Purpose:
- Distinguish a real systematic short squeeze from a simple bond rebound.
- Track the chain requested by the user:
  Goldman-quoted CTA DV01 -> CFTC positioning -> CME Treasury futures price/OI
  -> 1σ/2σ trend proxy -> repo/basis pressure -> 10Y 4.3% approach.

Important:
- Goldman CTA DV01 is not a public official feed. It is monitored only when quoted
  by public sources and is labelled as secondary-source information.
- CFTC, Treasury and New York Fed data are official.
- Cash/futures "basis" is not inferred directly without CTD/conversion-factor data.
  Repo + leveraged-fund positioning + dealer/futures OI are used only as a pressure proxy.
"""
from __future__ import annotations

import email.utils
import html
import json
import math
import re
import statistics
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "out"
STATE = DATA / "treasury_cta_squeeze_state.json"
NEXT_STATE = DATA / "treasury_cta_squeeze_state_next.json"
ALERT = OUT / "treasury_cta_squeeze_alert.html"
TITLE = OUT / "treasury_cta_squeeze_title.txt"
DETAIL = OUT / "treasury_cta_squeeze_detail.json"
STATUS = OUT / "treasury_cta_squeeze_status.md"

FORMAT_REVISION = 1

CFTC_TFF = "https://www.cftc.gov/dea/futures/financial_lf.htm"
TREASURY_YIELD_XML = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value=2026"
NYFED_SOFR_API = "https://markets.newyorkfed.org/api/rates/secured/sofr/last/1.json"
NYFED_BGCR_API = "https://markets.newyorkfed.org/api/rates/secured/bgcr/last/1.json"
NYFED_TGCR_API = "https://markets.newyorkfed.org/api/rates/secured/tgcr/last/1.json"
NYFED_PRIMARY_DEALER = "https://www.newyorkfed.org/markets/counterparties/primary-dealers-statistics"
FRED_FX = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXKOUS"

CME_SLATE = "https://www.cmegroup.com/CmeWS/mvc/ProductSlate/V2/List?pageNumber=1&sortAsc=false&sortField=rank&searchString={symbol}&pageSize=10"
CME_QUOTES = "https://www.cmegroup.com/CmeWS/mvc/Quotes/Future/{product_id}/G"
CME_PAGES = {
    "ZN": "https://www.cmegroup.com/markets/interest-rates/us-treasury/10-year-us-treasury-note.quotes.html",
    "ZB": "https://www.cmegroup.com/markets/interest-rates/us-treasury/us-treasury-bond.quotes.html",
    "UB": "https://www.cmegroup.com/markets/interest-rates/us-treasury/ultra-t-bond.quotes.html",
}

CTA_QUERIES = (
    'Goldman CTA Treasury DV01 155 million 2 standard deviation Bessent',
    'CTA Treasury short squeeze 4.3 Bessent Goldman',
    'trend-following bond shorts DV01 Goldman Treasury',
)

TRUSTED_OR_EXPLICIT_SECONDARY = (
    "Reuters", "Bloomberg", "CNBC", "Financial Times", "The Wall Street Journal",
    "Wall Street Journal", "MarketWatch", "Barron's", "Yahoo", "华尔街见闻",
    "WallstreetCN", "Futu", "Futunn",
)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 khs-watch/cta-squeeze",
        "Accept": "*/*",
    })
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", errors="replace")


def fetch_json(url: str):
    return json.loads(fetch(url))


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def latest_fx() -> tuple[float, str]:
    rows = [line.split(",") for line in fetch(FRED_FX).splitlines()[1:] if "," in line]
    for row in reversed(rows):
        if len(row) >= 2 and row[1] not in ("", "."):
            return float(row[1]), row[0]
    raise RuntimeError("FRED DEXKOUS 최신 환율 확인 실패")


def krw(usd: float, fx: float) -> str:
    value = usd * fx
    if value >= 1_000_000_000_000:
        return f"약 {value/1_000_000_000_000:,.2f}조원"
    if value >= 100_000_000:
        return f"약 {value/100_000_000:,.0f}억원"
    if value >= 10_000:
        return f"약 {value/10_000:,.0f}만원"
    return f"약 {value:,.0f}원"


def strip_tags(value: str) -> str:
    value = re.sub(r"(?i)<br\s*/?>", "\n", value)
    value = re.sub(r"(?i)</(?:p|div|tr|li|pre|table|h\d)>", "\n", value)
    value = re.sub(r"<[^>]+>", " ", value)
    return html.unescape(value).replace("\r", "")


def parse_pub_epoch(value: str) -> float:
    try:
        dt = email.utils.parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return 0.0


def cta_news() -> dict | None:
    found = []
    for q in CTA_QUERIES:
        url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(q + " when:3d") + "&hl=en-US&gl=US&ceid=US:en"
        try:
            root = ET.fromstring(fetch(url))
        except Exception:
            continue
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            desc = strip_tags(item.findtext("description") or "").strip()
            link = (item.findtext("link") or "").strip()
            source = (item.findtext("source") or "").strip()
            pub = (item.findtext("pubDate") or "").strip()
            blob = f"{title} {desc}".lower()
            if not ("cta" in blob and ("dv01" in blob or "4.3" in blob or "standard deviation" in blob)):
                continue
            if source and not any(x.lower() in source.lower() for x in TRUSTED_OR_EXPLICIT_SECONDARY):
                continue
            found.append({"title": title, "description": desc, "link": link, "source": source, "pubDate": pub})
    if not found:
        return None
    found.sort(key=lambda x: parse_pub_epoch(x.get("pubDate", "")), reverse=True)
    return found[0]


def cftc_snapshot() -> dict:
    raw = fetch(CFTC_TFF)
    text = strip_tags(raw)
    date_match = re.search(r"Positions\s+as\s+of\s+([A-Za-z]+\s+\d{1,2},\s+2026)", text, re.I)
    report_date = date_match.group(1) if date_match else "확인 불가"

    markets = {
        "2Y": r"UST\s+2Y\s+NOTE",
        "5Y": r"UST\s+5Y\s+NOTE",
        "10Y": r"UST\s+10Y\s+NOTE",
        "ULTRA10Y": r"ULTRA\s+UST\s+10Y",
        "BOND": r"(?:UST|U\.S\.\s+TREASURY)\s+BOND",
        "ULTRABOND": r"ULTRA\s+UST\s+BOND",
    }
    result = {"report_date": report_date, "markets": {}}
    for key, pat in markets.items():
        m = re.search(pat + r".*?Open Interest is\s+([0-9,]+).*?Positions\s*\n\s*([^\n]+)", text, flags=re.I | re.S)
        if not m:
            continue
        nums = [int(x.replace(",", "")) for x in re.findall(r"-?[0-9][0-9,]*", m.group(2))]
        if len(nums) < 14:
            continue
        oi = int(m.group(1).replace(",", ""))
        lev_long, lev_short, lev_spread = nums[6], nums[7], nums[8]
        result["markets"][key] = {
            "open_interest": oi,
            "leveraged_long": lev_long,
            "leveraged_short": lev_short,
            "leveraged_spreading": lev_spread,
            "leveraged_net": lev_long - lev_short,
            "short_share_oi_pct": lev_short / oi * 100 if oi else None,
        }
    return result


def treasury_10y_snapshot() -> dict:
    raw = fetch(TREASURY_YIELD_XML)
    values = []
    for entry in re.findall(r"<entry>(.*?)</entry>", raw, flags=re.S | re.I):
        dm = re.search(r"<d:NEW_DATE[^>]*>([^<]+)</d:NEW_DATE>", entry, re.I)
        ym = re.search(r"<d:BC_10YEAR[^>]*>([^<]+)</d:BC_10YEAR>", entry, re.I)
        if not dm or not ym:
            continue
        try:
            values.append((dm.group(1)[:10], float(ym.group(1))))
        except Exception:
            pass
    if not values:
        raise RuntimeError("Treasury 10Y XML 파싱 실패")
    values.sort(key=lambda x: x[0])
    latest_date, latest = values[-1]
    window = [v for _, v in values[-20:]]
    mean20 = statistics.mean(window)
    sd20 = statistics.pstdev(window) if len(window) > 1 else 0.0
    z20 = (latest - mean20) / sd20 if sd20 > 0 else 0.0
    return {
        "date": latest_date,
        "yield": latest,
        "mean20": mean20,
        "sd20": sd20,
        "z20": z20,
        "distance_to_4_3_bp": (latest - 4.30) * 100,
    }


def threshold_bucket(y: float) -> str:
    if y <= 4.30:
        return "4.30% 이하"
    if y <= 4.35:
        return "4.35% 이하"
    if y <= 4.40:
        return "4.40% 이하"
    if y <= 4.50:
        return "4.50% 이하"
    return "4.50% 초과"


def nyfed_rate(url: str) -> dict | None:
    try:
        data = fetch_json(url)
    except Exception:
        return None
    records = []
    if isinstance(data, dict):
        for key in ("refRates", "rates", "data"):
            if isinstance(data.get(key), list):
                records = data[key]
                break
    if not records and isinstance(data, list):
        records = data
    if not records:
        return None
    row = records[0]
    if not isinstance(row, dict):
        return None
    rate = row.get("percentRate") or row.get("rate") or row.get("Rate")
    date = row.get("effectiveDate") or row.get("date") or row.get("businessDate")
    volume = row.get("volumeInBillions") or row.get("volume")
    try:
        rate = float(rate)
    except Exception:
        return None
    return {"date": str(date or ""), "rate": rate, "volume_bn": volume}


def repo_snapshot() -> dict:
    return {
        "SOFR": nyfed_rate(NYFED_SOFR_API),
        "BGCR": nyfed_rate(NYFED_BGCR_API),
        "TGCR": nyfed_rate(NYFED_TGCR_API),
    }


def parse_treasury_price(value) -> float | None:
    if value is None:
        return None
    s = str(value).strip().replace("A", "").replace("B", "")
    if not s or s in ("-", "--"):
        return None
    sign = -1 if s.startswith("-") else 1
    s = s.lstrip("+-")
    if "'" in s or "-" in s:
        sep = "'" if "'" in s else "-"
        try:
            whole, frac = s.split(sep, 1)
            frac = frac.replace("+", "4")
            digits = re.sub(r"\D", "", frac)
            thirtyseconds = int(digits[:2]) if len(digits) >= 2 else int(digits or 0)
            eighths = int(digits[2]) if len(digits) >= 3 else 0
            return sign * (float(whole) + thirtyseconds / 32 + eighths / 256)
        except Exception:
            return None
    try:
        return sign * float(s.replace(",", ""))
    except Exception:
        return None


def as_int(value) -> int | None:
    try:
        return int(float(str(value).replace(",", "")))
    except Exception:
        return None


def cme_front(symbol: str) -> dict | None:
    try:
        slate = fetch_json(CME_SLATE.format(symbol=urllib.parse.quote(symbol)))
        products = slate.get("products", []) if isinstance(slate, dict) else []
        product = None
        for p in products:
            if str(p.get("globex") or p.get("globexCode") or "").upper() == symbol:
                product = p
                break
        if product is None and products:
            product = products[0]
        product_id = product.get("id") if isinstance(product, dict) else None
        if product_id is None:
            return None
        q = fetch_json(CME_QUOTES.format(product_id=product_id))
        quotes = q.get("quotes", []) if isinstance(q, dict) else []
        candidates = []
        for row in quotes:
            if not isinstance(row, dict):
                continue
            oi = as_int(row.get("openInterest")) or 0
            vol = as_int(row.get("volume")) or 0
            last = parse_treasury_price(row.get("last") or row.get("lastPrice"))
            if last is None:
                continue
            candidates.append((oi, vol, row, last))
        if not candidates:
            return None
        candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
        oi, vol, row, last = candidates[0]
        change = parse_treasury_price(row.get("change"))
        prior = parse_treasury_price(row.get("priorSettle") or row.get("previousSettlement"))
        pct = None
        if prior and prior != 0:
            pct = (last / prior - 1) * 100
        elif change is not None and last - change:
            pct = change / (last - change) * 100
        return {
            "symbol": symbol,
            "month": row.get("expirationMonth") or row.get("month") or row.get("contractMonth") or "",
            "last": last,
            "change": change,
            "pct_change": pct,
            "open_interest": oi,
            "volume": vol,
            "source": CME_PAGES.get(symbol),
        }
    except Exception:
        return None


def cme_snapshot() -> dict:
    return {s: cme_front(s) for s in ("ZN", "ZB", "UB")}


def squeeze_evidence(current: dict, previous: dict) -> list[str]:
    signals = []
    prev_cme = previous.get("cme", {}) if isinstance(previous, dict) else {}
    for symbol, row in current.get("cme", {}).items():
        if not row:
            continue
        prev = prev_cme.get(symbol) or {}
        pct = row.get("pct_change")
        oi = row.get("open_interest")
        prev_oi = prev.get("open_interest")
        if pct is not None and pct > 0.20 and oi and prev_oi and oi < prev_oi:
            signals.append(f"{symbol} 가격↑({pct:+.2f}%) + 미결제약정↓({prev_oi:,}→{oi:,}) = 숏커버 확인 신호")
    return signals


def cftc_lines(cftc: dict, previous: dict) -> list[str]:
    lines = []
    prev_markets = (previous.get("cftc") or {}).get("markets", {}) if isinstance(previous, dict) else {}
    order = ("2Y", "5Y", "10Y", "BOND", "ULTRABOND")
    for key in order:
        row = cftc.get("markets", {}).get(key)
        if not row:
            continue
        net = row["leveraged_net"]
        direction = "순숏" if net < 0 else "순롱"
        text = f"• {key}: Leveraged Funds {direction} {abs(net):,}계약 · 숏/OI {row['short_share_oi_pct']:.1f}%"
        prev = prev_markets.get(key)
        if prev and prev.get("leveraged_net") is not None:
            delta = net - prev["leveraged_net"]
            if delta:
                text += f" · 직전 대비 순포지션 {delta:+,}계약"
        lines.append(text)
    return lines


def format_alert(snapshot: dict, previous: dict, fx: float, fx_date: str, reasons: list[str]) -> tuple[str, str]:
    y = snapshot["yield10"]
    cftc = snapshot["cftc"]
    repo = snapshot["repo"]
    media = snapshot.get("cta_media")
    cme = snapshot.get("cme", {})
    evidence = squeeze_evidence(snapshot, previous)

    if y["z20"] <= -2:
        sigma = "🔴 20일 기준 -2σ 이하: 채권가격 급등에 대응하는 강한 금리하락 프록시"
    elif y["z20"] <= -1:
        sigma = "🟠 20일 기준 -1σ 이하: CTA 추세 전환 후보 구간"
    else:
        sigma = "⚪ 20일 기준 -1σ 미도달: 공개 금리 프록시상 강제 환매 확인 전"

    repo_bits = []
    for key in ("SOFR", "BGCR", "TGCR"):
        row = repo.get(key)
        if row:
            repo_bits.append(f"{key} {row['rate']:.2f}%")
    repo_text = " · ".join(repo_bits) if repo_bits else "NY Fed repo 값 확인 불가"

    cme_lines = []
    for symbol in ("ZN", "ZB", "UB"):
        row = cme.get(symbol)
        if not row:
            cme_lines.append(f"• {symbol}: CME 지연가격/OI 자동 파싱 확인 불가 — CFTC·공식 금리로 보조 판정")
            continue
        pct = row.get("pct_change")
        pct_text = f"{pct:+.2f}%" if pct is not None else "변화율 확인 불가"
        cme_lines.append(f"• {symbol} {row.get('month','')}: 가격 {row['last']:.5f} ({pct_text}) · OI {row['open_interest']:,}")

    media_line = "• Goldman CTA DV01: 공개 공식 피드 없음 — 신뢰/명시적 2차 출처의 신규 인용만 감시"
    if media:
        blob = f"{media.get('title','')} {media.get('description','')}"
        dv = re.search(r"\$?\s*([0-9]+(?:\.[0-9]+)?)\s*million\s*(?:of\s*)?(?:bond\s*)?DV01", blob, re.I)
        if dv:
            usd = float(dv.group(1)) * 1_000_000
            media_line = f"• Goldman 인용 CTA DV01: 약 ${float(dv.group(1)):.0f}m DV01(1bp당 {krw(usd, fx)}) — <b>2차 출처 인용, Goldman 원문 직접확인 전</b>"
        else:
            media_line = f"• CTA/Goldman 신규 2차 인용: {html.escape(media.get('title',''))}"

    title = "🇺🇸 미 국채 CTA 숏 스퀴즈 감시 — 4.3% 시나리오가 실제로 작동하는지 판정"
    body = "\n".join([
        "<b>🎯 핵심 판단</b>",
        "‘베센트가 10년물을 4.3%로 만든다’는 공식 정책이 아니라 <b>재무부 수급 충격이 CTA 숏커버를 점화할 수 있다는 시장 가설</b>입니다. 따라서 말이 아니라 포지션·선물·자금조달·금리의 동시 움직임으로 확인합니다.",
        "",
        "<b>1️⃣ Goldman CTA DV01 — 스퀴즈의 연료</b>",
        media_line,
        "• +2σ 채권가격 상승 시 대규모 환매 추정치가 새로 인용되면 별도 변화로 감지합니다.",
        "",
        f"<b>2️⃣ CFTC 공식 포지션 — {cftc.get('report_date','확인 불가')}</b>",
        *(cftc_lines(cftc, previous) or ["• CFTC TFF 파싱 확인 불가"]),
        "※ Leveraged Funds 숏 전체를 CTA 방향성 숏으로 동일시하지 않습니다. 베이시스 거래가 섞일 수 있습니다.",
        "",
        "<b>3️⃣ TY/US/WN 대응 CME 선물 — 가격 + 미결제약정</b>",
        "※ CME Globex 표기는 ZN(10년), ZB(T-Bond), UB(Ultra Bond)로 추적합니다.",
        *cme_lines,
        *( [f"• ✅ {x}" for x in evidence] if evidence else ["• 아직 ‘가격↑ + OI↓’ 동시 신호 미확인 → 기계적 숏커버 확정 전"] ),
        "",
        "<b>4️⃣ 1σ·2σ 추세 전환 프록시</b>",
        f"• 미 재무부 공식 10년물: {y['yield']:.3f}% · 20일 평균 {y['mean20']:.3f}% · z={y['z20']:+.2f}σ",
        f"• {sigma}",
        "※ Goldman CTA의 독자 모델과 동일한 신호가 아니며, 공개 공식 데이터로 보는 보조 프록시입니다.",
        "",
        "<b>5️⃣ Repo·Basis 압력</b>",
        f"• NY Fed 공식: {repo_text}",
        "• 실제 cash-futures basis는 CTD·전환계수·repo specialness가 필요하므로 임의 계산하지 않습니다.",
        "• 대신 CFTC Leveraged Funds 숏 + CME OI + SOFR/BGCR/TGCR을 묶어 <b>베이시스/펀딩 압력 프록시</b>로 판정합니다.",
        "",
        "<b>6️⃣ 10년물 4.3% 접근</b>",
        f"• 현재 공식 10년물 {y['yield']:.3f}% → 4.30%까지 {y['distance_to_4_3_bp']:+.1f}bp",
        f"• 현재 구간: <b>{threshold_bucket(y['yield'])}</b>",
        "• 4.50 → 4.40 → 4.35 → 4.30%를 단계별 경보선으로 사용. 4.30%는 공식 목표가 아니라 시장 시나리오입니다.",
        "",
        "<b>🔍 스퀴즈 확인 조건</b>",
        "① CTA/DV01 숏 축소 보도 + ② CFTC 순숏 감소 + ③ ZN/ZB/UB 가격↑·OI↓ + ④ -1σ/-2σ 진입 + ⑤ repo 스트레스 비악화 + ⑥ 10Y 4.3% 접근이 <b>같은 방향으로 겹칠 때</b> ‘실제 숏 스퀴즈 강화’로 판정합니다.",
        "",
        "<b>⚠️ 실패모드</b>",
        "• 금리는 내려도 OI가 줄지 않음 → 신규 롱 유입일 수 있어 CTA 환매 증거 약함",
        "• CFTC 숏이 유지되는데 10Y만 하락 → 단순 매크로 랠리 가능성",
        "• SOFR/BGCR/TGCR 급등·딜러 펀딩 악화 → 베이시스 포지션 청산이 질서 없는 디레버리징으로 바뀔 수 있음",
        "• CTA 숏이 대부분 소진되면 기계적 매수 연료가 사라져 재정·인플레이션이 다시 금리를 지배할 수 있음",
        "",
        "<b>📌 이번 알림 발생 이유</b>",
        " · ".join(reasons) if reasons else "초기 기준선 생성",
        "",
        "<b>한 줄 결론</b>",
        "<b>4.3%라는 숫자보다 ‘CTA DV01↓ → CFTC 숏↓ → ZN/ZB/UB 가격↑·OI↓ → -1σ/-2σ → repo 안정 → 10Y 하락’의 연쇄가 실제로 발생하는지가 핵심</b>이며, 한 축만 움직이면 숏 스퀴즈로 단정하지 않습니다.",
        "",
        f"환율 기준: FRED DEXKOUS {fx_date}, 1달러={fx:,.2f}원",
        f'<a href="{CFTC_TFF}">CFTC 포지션</a> · <a href="{TREASURY_YIELD_XML}">미 재무부 금리</a> · <a href="{NYFED_SOFR_API}">NY Fed SOFR</a> · <a href="{CME_PAGES["ZN"]}">CME ZN</a> · <a href="{CME_PAGES["ZB"]}">CME ZB</a> · <a href="{CME_PAGES["UB"]}">CME UB</a> · <a href="{NYFED_PRIMARY_DEALER}">Primary Dealer 통계</a>'
    ])
    return title, body


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    for p in (ALERT, TITLE, DETAIL):
        try:
            p.unlink()
        except FileNotFoundError:
            pass

    state = load_state()
    fx, fx_date = latest_fx()
    snapshot = {
        "checked_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "cta_media": cta_news(),
        "cftc": cftc_snapshot(),
        "cme": cme_snapshot(),
        "yield10": treasury_10y_snapshot(),
        "repo": repo_snapshot(),
        "format_revision": FORMAT_REVISION,
    }

    reasons = []
    media_id = None
    if snapshot["cta_media"]:
        media_id = snapshot["cta_media"].get("link") or snapshot["cta_media"].get("title")
        if media_id and media_id != state.get("media_id"):
            reasons.append("CTA/Goldman 신규 인용")

    cftc_date = snapshot["cftc"].get("report_date")
    if state.get("cftc_date") and cftc_date != state.get("cftc_date"):
        reasons.append("CFTC 주간 포지션 갱신")

    bucket = threshold_bucket(snapshot["yield10"]["yield"])
    if state.get("yield_bucket") and bucket != state.get("yield_bucket"):
        reasons.append(f"10년물 경보구간 변화: {state.get('yield_bucket')} → {bucket}")

    prev_snapshot = state.get("snapshot") or {}
    evidence = squeeze_evidence(snapshot, prev_snapshot)
    if evidence:
        reasons.append("CME 가격↑ + 미결제약정↓ 숏커버 신호")

    z = snapshot["yield10"]["z20"]
    prev_z = ((prev_snapshot.get("yield10") or {}).get("z20")) if prev_snapshot else None
    if prev_z is not None:
        if prev_z > -1 >= z:
            reasons.append("10년물 -1σ 진입")
        if prev_z > -2 >= z:
            reasons.append("10년물 -2σ 진입")

    force = int(state.get("format_revision", 0) or 0) < FORMAT_REVISION
    should_alert = bool(reasons or force or not state)

    next_state = {
        "last_checked_kst": snapshot["checked_kst"],
        "media_id": media_id,
        "cftc_date": cftc_date,
        "yield_bucket": bucket,
        "snapshot": snapshot,
        "format_revision": FORMAT_REVISION,
    }

    if should_alert:
        title, body = format_alert(snapshot, prev_snapshot, fx, fx_date, reasons)
        if len(title) + 2 + len(body) > 4096:
            raise RuntimeError(f"Telegram message too long: {len(title)+2+len(body)}")
        TITLE.write_text(title + "\n", encoding="utf-8")
        ALERT.write_text(body + "\n", encoding="utf-8")
        DETAIL.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    NEXT_STATE.write_text(json.dumps(next_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    STATUS.write_text(
        "# 미 국채 CTA 숏 스퀴즈 감시\n\n"
        f"- 조회시각: {snapshot['checked_kst']}\n"
        f"- CFTC 기준일: {cftc_date}\n"
        f"- 10년물: {snapshot['yield10']['yield']:.3f}% / {bucket}\n"
        f"- 20일 z: {snapshot['yield10']['z20']:+.2f}σ\n"
        f"- 신규 경보 사유: {', '.join(reasons) if reasons else '없음'}\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
