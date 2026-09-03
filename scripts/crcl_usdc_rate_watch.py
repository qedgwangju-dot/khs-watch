#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from scripts.crypto_alert_krw import get_usdkrw, format_krw_from_usd_m

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "crcl_usdc_rate_watch_state.json"
OUT_DIR = ROOT / "out"
PENDING_STATE = OUT_DIR / "crcl_usdc_rate_watch_pending_state.json"
ALERT_PATH = OUT_DIR / "crcl_usdc_rate_watch_telegram.txt"
STATUS_PATH = OUT_DIR / "crcl_usdc_rate_watch_status.md"

CIRCLE_USDC_URL = "https://www.circle.com/usdc"
BLACKROCK_USDXX_URL = "https://www.blackrock.com/cash/en-us/products/329365/circle-reserve-fund"
NYFED_SOFR_URL = "https://www.newyorkfed.org/markets/reference-rates/sofr"
TREASURY_CURVE_URL = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView"
PROSHARES_TBX_URL = "https://www.proshares.com/our-etfs/leveraged-and-inverse/tbx"
SEC_CRCL_Q2_URL = "https://www.sec.gov/Archives/edgar/data/1876042/000187604226000248/crcl-20260630.htm"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

UA = "Mozilla/5.0 (compatible; khs-watch/1.0; +https://github.com/qedgwangju-dot/khs-watch)"
KST = ZoneInfo("Asia/Seoul")
ET = ZoneInfo("America/New_York")


def fetch(url: str, timeout: int = 35) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def atomic_write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def parse_float(value: str) -> float | None:
    s = (value or "").strip().replace(",", "").replace("$", "").replace("%", "")
    m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else None


def circle_usdc() -> dict:
    text = " ".join(BeautifulSoup(fetch(CIRCLE_USDC_URL), "html.parser").get_text(" ", strip=True).split())
    patterns = [
        r"\$\s*([\d.]+)\s*B\s*USDC\s+in\s+circulation\s+as\s+of\s+(\d{1,2}\s+[A-Za-z]+\s+20\d{2})",
        r"USDC\s+in\s+circulation.*?\$\s*([\d.]+)\s*B.*?as\s+of\s+(\d{1,2}\s+[A-Za-z]+\s+20\d{2})",
    ]
    m = next((re.search(p, text, re.I) for p in patterns if re.search(p, text, re.I)), None)
    if not m:
        raise RuntimeError("Circle USDC circulation/date could not be parsed")
    amount_b = float(m.group(1))
    d = dt.datetime.strptime(m.group(2), "%d %B %Y").date()
    return {"date": d.isoformat(), "circulation_usd_b": amount_b, "precision": "0.1B official webpage display"}


def blackrock_usdxx() -> dict:
    text = " ".join(BeautifulSoup(fetch(BLACKROCK_USDXX_URL), "html.parser").get_text(" ", strip=True).split())
    m = re.search(r"7\s*Day\s*SEC\s*Yield\s*as\s*of\s*(\d{1,2}-[A-Za-z]{3}-20\d{2})\s*([\d.]+)%", text, re.I)
    if not m:
        raise RuntimeError("BlackRock USDXX 7-Day SEC yield could not be parsed")
    d = dt.datetime.strptime(m.group(1), "%d-%b-%Y").date()
    y = float(m.group(2))

    size = None
    size_date = None
    sm = re.search(r"Size\s+of\s+Fund\s*\(Millions\)\s*as\s*of\s*(\d{1,2}-[A-Za-z]{3}-20\d{2})\s*\$\s*([\d,]+(?:\.\d+)?)", text, re.I)
    if sm:
        size_date = dt.datetime.strptime(sm.group(1), "%d-%b-%Y").date().isoformat()
        size = float(sm.group(2).replace(",", ""))
    return {"date": d.isoformat(), "sec_yield_7d": y, "fund_size_usd_m": size, "fund_size_date": size_date}


def infer_mmdd_year(mmdd: str) -> dt.date:
    month, day = map(int, mmdd.split("/"))
    today = dt.datetime.now(ET).date()
    year = today.year
    candidate = dt.date(year, month, day)
    if candidate > today + dt.timedelta(days=7):
        candidate = dt.date(year - 1, month, day)
    return candidate


def nyfed_sofr() -> dict:
    soup = BeautifulSoup(fetch(NYFED_SOFR_URL), "html.parser")
    rows: list[tuple[dt.date, float]] = []
    for tr in soup.find_all("tr"):
        cells = [" ".join(x.get_text(" ", strip=True).split()) for x in tr.find_all(["td", "th"])]
        if len(cells) < 2 or not re.fullmatch(r"\d{1,2}/\d{1,2}", cells[0]):
            continue
        rate = parse_float(cells[1])
        if rate is None:
            continue
        rows.append((infer_mmdd_year(cells[0]), rate))
    if not rows:
        raise RuntimeError("NY Fed SOFR rows could not be parsed")
    rows.sort(key=lambda x: x[0])
    latest = rows[-1]
    prev = rows[-2] if len(rows) >= 2 else latest
    return {
        "date": latest[0].isoformat(), "rate": latest[1],
        "prev_date": prev[0].isoformat(), "prev_rate": prev[1],
        "daily_bp": round((latest[1] - prev[1]) * 100, 1),
    }


def treasury_curve() -> dict:
    year = dt.datetime.now(ET).year
    url = TREASURY_CURVE_URL + "?" + urllib.parse.urlencode({"type": "daily_treasury_yield_curve", "field_tdr_date_value": year})
    soup = BeautifulSoup(fetch(url), "html.parser")
    header = None
    data: list[tuple[dt.date, list[str]]] = []
    for tr in soup.find_all("tr"):
        cells = [" ".join(x.get_text(" ", strip=True).split()) for x in tr.find_all(["td", "th"])]
        if not cells:
            continue
        if header is None and any("Date" == x for x in cells):
            header = cells
            continue
        try:
            d = dt.datetime.strptime(cells[0], "%m/%d/%Y").date()
        except Exception:
            continue
        data.append((d, cells))
    if not header or not data:
        raise RuntimeError("Treasury curve table could not be parsed")

    norm = [re.sub(r"\s+", " ", x.lower()).strip() for x in header]
    def find_col(candidates: list[str]) -> int:
        for c in candidates:
            if c in norm:
                return norm.index(c)
        for i, h in enumerate(norm):
            if any(c in h for c in candidates):
                return i
        raise RuntimeError(f"Treasury column missing: {candidates}")

    i3 = find_col(["3 mo", "3-month", "3 month"])
    i10 = find_col(["10-year", "10 yr", "10 year"])
    data.sort(key=lambda x: x[0])
    latest_d, latest_c = data[-1]
    prev_d, prev_c = data[-2] if len(data) >= 2 else data[-1]
    y3, y10 = parse_float(latest_c[i3]), parse_float(latest_c[i10])
    p3, p10 = parse_float(prev_c[i3]), parse_float(prev_c[i10])
    if None in (y3, y10, p3, p10):
        raise RuntimeError("Treasury 3M/10Y values missing")
    return {
        "date": latest_d.isoformat(), "three_month": y3, "ten_year": y10,
        "prev_date": prev_d.isoformat(), "prev_three_month": p3, "prev_ten_year": p10,
        "daily_3m_bp": round((y3 - p3) * 100, 1), "daily_10y_bp": round((y10 - p10) * 100, 1),
        "url": url,
    }


def yahoo_daily(symbol: str) -> dict:
    end = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)
    start = end - dt.timedelta(days=20)
    params = urllib.parse.urlencode({
        "period1": int(start.timestamp()), "period2": int(end.timestamp()),
        "interval": "1d", "events": "history", "includeAdjustedClose": "true",
    })
    data = json.loads(fetch(YAHOO_CHART.format(symbol=urllib.parse.quote(symbol)) + "?" + params).decode("utf-8"))
    result = (((data.get("chart") or {}).get("result") or [None])[0])
    if not result:
        raise RuntimeError(f"Yahoo {symbol} chart missing")
    timestamps = result.get("timestamp") or []
    closes = (((result.get("indicators") or {}).get("quote") or [{}])[0]).get("close") or []
    rows: list[tuple[dt.date, float]] = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        d = dt.datetime.fromtimestamp(ts, ET).date()
        rows.append((d, float(close)))
    rows.sort(key=lambda x: x[0])
    if not rows:
        raise RuntimeError(f"Yahoo {symbol} has no closes")
    latest = rows[-1]
    prev = rows[-2] if len(rows) >= 2 else latest
    pct = (latest[1] / prev[1] - 1.0) * 100 if prev[1] else 0.0
    return {"date": latest[0].isoformat(), "close": latest[1], "prev_date": prev[0].isoformat(), "prev_close": prev[1], "daily_pct": round(pct, 2)}


def fmt_money_b(b: float, fx: float) -> str:
    return f"{b:,.1f}십억달러 ({format_krw_from_usd_m(b * 1000.0, fx)})"


def fmt_money_m(m: float | None, fx: float) -> str:
    if m is None:
        return "확인 불가"
    return f"{m:,.1f}백만달러 ({format_krw_from_usd_m(m, fx)})"


def fmt_delta(value: float | None, unit: str = "") -> str:
    if value is None:
        return "비교 불가"
    return f"{value:+,.2f}{unit}"


def bp(a: float, b: float) -> float:
    return round((a - b) * 100, 1)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ALERT_PATH.unlink(missing_ok=True)
    old = load_state()
    now = dt.datetime.now(KST).isoformat(timespec="seconds")
    errors: list[str] = []

    def safe(name: str, fn, fallback: dict | None = None):
        try:
            return fn()
        except Exception as e:
            errors.append(f"{name}: {e}")
            return fallback or {}

    circle = safe("circle", circle_usdc, old.get("circle"))
    usdxx = safe("usdxx", blackrock_usdxx, old.get("usdxx"))
    sofr = safe("sofr", nyfed_sofr, old.get("sofr"))
    treasury = safe("treasury", treasury_curve, old.get("treasury"))
    crcl = safe("crcl", lambda: yahoo_daily("CRCL"), old.get("crcl"))
    tbx = safe("tbx", lambda: yahoo_daily("TBX"), old.get("tbx"))

    if not circle or not usdxx or not treasury:
        raise RuntimeError("핵심 공식 원천(Circle/BlackRock/Treasury) 중 하나 이상 확인 실패")

    # Use the most recent date among key monetary figures for KRW translation.
    fx_date = dt.date.fromisoformat(max(circle.get("date"), usdxx.get("date"), treasury.get("date")))
    try:
        fx = get_usdkrw(fx_date)
    except Exception as e:
        errors.append(f"fx: {e}")
        fx = old.get("fx") or {}
    if not fx:
        raise RuntimeError("USD/KRW 확인 실패")
    fx_rate = float(fx["rate"])

    new_state = {
        "updated_at_kst": now,
        "circle": circle, "usdxx": usdxx, "sofr": sofr, "treasury": treasury,
        "crcl": crcl, "tbx": tbx, "fx": fx, "errors": errors,
    }
    atomic_write(PENDING_STATE, json.dumps(new_state, ensure_ascii=False, indent=2) + "\n")

    changes: list[str] = []
    initial = not old
    if initial:
        changes.append("감시 시작 기준값 생성")
    else:
        oc = old.get("circle") or {}
        ou = old.get("usdxx") or {}
        os = old.get("sofr") or {}
        ot = old.get("treasury") or {}
        op = old.get("crcl") or {}

        if circle.get("date") != oc.get("date") or circle.get("circulation_usd_b") != oc.get("circulation_usd_b"):
            delta_b = circle.get("circulation_usd_b", 0) - oc.get("circulation_usd_b", circle.get("circulation_usd_b", 0))
            changes.append(f"Circle USDC 공식 유통량 갱신: {delta_b:+.1f}십억달러")
        if usdxx.get("date") != ou.get("date") and abs(usdxx.get("sec_yield_7d", 0) - ou.get("sec_yield_7d", usdxx.get("sec_yield_7d", 0))) >= 0.01:
            changes.append(f"Circle Reserve Fund 7일 SEC 수익률 변화: {bp(usdxx['sec_yield_7d'], ou['sec_yield_7d']):+.1f}bp")
        if sofr and os and sofr.get("date") != os.get("date") and abs(sofr.get("rate", 0) - os.get("rate", sofr.get("rate", 0))) >= 0.01:
            changes.append(f"SOFR 변화: {bp(sofr['rate'], os['rate']):+.1f}bp")
        if treasury.get("date") != ot.get("date"):
            d3 = bp(treasury["three_month"], ot.get("three_month", treasury["three_month"]))
            d10 = bp(treasury["ten_year"], ot.get("ten_year", treasury["ten_year"]))
            if max(abs(d3), abs(d10)) >= 2.0:
                changes.append(f"미 국채 금리 변화: 3M {d3:+.1f}bp / 10Y {d10:+.1f}bp")
        # One consolidated daily snapshot when a new CRCL close appears.
        if crcl and op and crcl.get("date") != op.get("date"):
            changes.append(f"CRCL 새 종가: {crcl.get('daily_pct', 0):+.2f}%")

    if changes:
        oc = old.get("circle") or circle
        ou = old.get("usdxx") or usdxx
        os = old.get("sofr") or sofr
        ot = old.get("treasury") or treasury

        circle_delta = circle["circulation_usd_b"] - oc.get("circulation_usd_b", circle["circulation_usd_b"])
        circle_pct = (circle_delta / oc["circulation_usd_b"] * 100) if oc.get("circulation_usd_b") else 0.0
        usdxx_bp = bp(usdxx["sec_yield_7d"], ou.get("sec_yield_7d", usdxx["sec_yield_7d"]))
        sofr_bp = bp(sofr["rate"], os.get("rate", sofr["rate"])) if sofr else 0.0
        t3_bp = bp(treasury["three_month"], ot.get("three_month", treasury["three_month"]))
        t10_bp = bp(treasury["ten_year"], ot.get("ten_year", treasury["ten_year"]))

        # Earnings direction uses the actual short-rate proxies, not TBX.
        if circle_delta > 0 and (usdxx_bp > 0 or t3_bp > 0 or sofr_bp > 0):
            earnings_view = "우호적 — USDC 물량과 단기금리 중 둘 다 개선"
        elif circle_delta < 0 and (usdxx_bp < 0 or t3_bp < 0 or sofr_bp < 0):
            earnings_view = "불리 — USDC 물량과 단기금리 중 둘 다 악화"
        elif circle_delta == 0 and max(abs(usdxx_bp), abs(t3_bp), abs(sofr_bp)) < 0.5:
            earnings_view = "중립 — 핵심 실적 변수 변화 제한"
        else:
            earnings_view = "혼조 — USDC 물량과 단기금리 방향이 엇갈림"

        if t10_bp > 0:
            discount_view = "불리 — 10년물 상승으로 주식 할인율 부담 확대"
        elif t10_bp < 0:
            discount_view = "우호적 — 10년물 하락으로 할인율 부담 완화"
        else:
            discount_view = "중립 — 10년물 변화 제한"

        lines = [
            "<b>CRCL 금리·USDC 펀더멘털 변화</b>",
            f"<code>조회 {html.escape(now)}</code>",
            "",
            "<b>핵심 변화</b>",
        ]
        lines += [f"• {html.escape(x)}" for x in changes]
        lines += [
            "",
            "<b>돈 버는 능력 — 실제 핵심</b>",
            f"• <b>USDC 유통량</b> {fmt_money_b(circle['circulation_usd_b'], fx_rate)} · Circle {circle['date']}",
            f"  직전 대비 {circle_delta:+.1f}십억달러 ({circle_pct:+.2f}%) · Circle 공식 공개는 0.1십억달러 단위",
            f"• <b>Circle Reserve Fund 7일 SEC 수익률</b> {usdxx['sec_yield_7d']:.2f}% · {usdxx['date']} | 직전 저장값 대비 {usdxx_bp:+.1f}bp",
        ]
        if usdxx.get("fund_size_usd_m") is not None:
            lines += [f"• 펀드 규모 {fmt_money_m(usdxx['fund_size_usd_m'], fx_rate)} · {usdxx.get('fund_size_date') or usdxx['date']}"]
        if sofr:
            lines += [f"• <b>SOFR</b> {sofr['rate']:.2f}% · {sofr['date']} | 직전 저장값 대비 {sofr_bp:+.1f}bp"]
        lines += [
            f"• <b>미 국채 3개월</b> {treasury['three_month']:.2f}% · {treasury['date']} | 직전 저장값 대비 {t3_bp:+.1f}bp",
            "",
            "<b>할인율 — TBX는 여기서만 보조</b>",
            f"• <b>미 국채 10년</b> {treasury['ten_year']:.2f}% · {treasury['date']} | 직전 저장값 대비 {t10_bp:+.1f}bp",
        ]
        if crcl:
            lines += [f"• <b>CRCL</b> ${crcl['close']:.2f} · {crcl['date']} | 일간 {crcl['daily_pct']:+.2f}%"]
        if tbx:
            lines += [f"• <b>TBX</b> ${tbx['close']:.2f} · {tbx['date']} | 일간 {tbx['daily_pct']:+.2f}% · 7~10년 미 국채 가격 일간 -1배 보조지표"]

        lines += [
            "",
            "<blockquote><b>판단</b>",
            f"실적 축: {html.escape(earnings_view)}",
            f"할인율 축: {html.escape(discount_view)}",
            "CRCL의 직접 실적 변수는 TBX가 아니라 <b>USDC 유통량 × 단기금리(USDXX·SOFR·3개월 국채)</b>입니다.</blockquote>",
            "",
            "<b>고정 기준</b>",
            "• 2026년 2분기 Circle 준비금 수익은 전체 매출의 95.2%",
            "• 2026년 6월 말 USDC 준비금 약 84%가 Circle Reserve Fund에 편입",
            "• TBX는 7~10년 미 국채 가격의 일간 -1배 상품이라 장기 할인율 방향 확인용이며, 준비금 수익의 직접 기준금리가 아님",
            "",
            f"<b>원화 환산</b> · 1달러={fx_rate:,.2f}원 · 기준일 {html.escape(str(fx.get('date')))} · {html.escape(str(fx.get('source')))}",
            "",
            "<b>원문</b>",
            f'• Circle USDC: <a href="{CIRCLE_USDC_URL}">원문</a>',
            f'• Circle Reserve Fund(BlackRock): <a href="{BLACKROCK_USDXX_URL}">원문</a>',
            f'• SOFR(New York Fed): <a href="{NYFED_SOFR_URL}">원문</a>',
            f'• 미 국채 금리: <a href="{treasury.get("url") or TREASURY_CURVE_URL}">원문</a>',
            f'• TBX(ProShares): <a href="{PROSHARES_TBX_URL}">원문</a>',
            f'• Circle 2Q26 10-Q(SEC): <a href="{SEC_CRCL_Q2_URL}">원문</a>',
            "",
            "※ Circle USDC 공식 웹페이지 유통량은 0.1십억달러 단위 표시라 세부 온체인 수치와 소폭 차이가 날 수 있습니다.",
        ]
        atomic_write(ALERT_PATH, "\n".join(lines).strip() + "\n")

    status = [
        "# CRCL 금리·USDC 펀더멘털 감시",
        "",
        f"- 조회시각(KST): {now}",
        f"- 알림 트리거: {len(changes)}개",
        f"- Circle USDC: {circle.get('circulation_usd_b')}B ({circle.get('date')})",
        f"- USDXX 7-day SEC yield: {usdxx.get('sec_yield_7d')}% ({usdxx.get('date')})",
        f"- SOFR: {sofr.get('rate') if sofr else 'N/A'}% ({sofr.get('date') if sofr else 'N/A'})",
        f"- Treasury 3M/10Y: {treasury.get('three_month')}% / {treasury.get('ten_year')}% ({treasury.get('date')})",
        f"- CRCL: {crcl.get('close') if crcl else 'N/A'} ({crcl.get('date') if crcl else 'N/A'})",
        f"- TBX: {tbx.get('close') if tbx else 'N/A'} ({tbx.get('date') if tbx else 'N/A'})",
        f"- 오류: {'; '.join(errors) if errors else '없음'}",
    ]
    atomic_write(STATUS_PATH, "\n".join(status) + "\n")


if __name__ == "__main__":
    main()
