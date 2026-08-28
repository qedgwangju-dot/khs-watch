#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
import re
import urllib.request
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "crypto_liquidity_watch_state.json"
OUT_DIR = ROOT / "out"
PENDING_STATE = OUT_DIR / "crypto_liquidity_watch_pending_state.json"
ALERT_PATH = OUT_DIR / "crypto_liquidity_watch_telegram.txt"
STATUS_PATH = OUT_DIR / "crypto_liquidity_watch_status.md"

TREASURY_BUYBACK_XML = "https://home.treasury.gov/system/files/221/Tentative-Buyback-Schedule.xml"
TREASURY_BUYBACK_PAGE = "https://www.treasurydirect.gov/auctions/announcements-data-results/buy-backs/"
TREASURY_RATES_URL = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?field_tdr_date_value=2026&type=daily_treasury_yield_curve"
FARSIDE_BTC_ETF_URL = "https://farside.co.uk/bitcoin-etf-flow-all-data/"

UA = "Mozilla/5.0 (compatible; khs-watch/1.0; +https://github.com/qedgwangju-dot/khs-watch)"
KST = ZoneInfo("Asia/Seoul")


def fetch(url: str, timeout: int = 35) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def atomic_write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def sha256_bytes(data: bytes) -> str:
    normalized = b"\n".join(line.strip() for line in data.replace(b"\r\n", b"\n").split(b"\n") if line.strip())
    return hashlib.sha256(normalized).hexdigest()


def parse_number(text: str) -> float | None:
    s = (text or "").strip().replace(",", "").replace("$", "")
    if not s or s in {"-", "—", "N/A", "n/a"}:
        return None
    neg = s.startswith("(") and s.endswith(")")
    if neg:
        s = s[1:-1]
    m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
    if not m:
        return None
    value = float(m.group(0))
    return -abs(value) if neg else value


def parse_date(text: str) -> dt.date | None:
    s = " ".join((text or "").split())
    for fmt in ("%m/%d/%Y", "%d %b %Y", "%d %B %Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def treasury_rates() -> dict:
    html = fetch(TREASURY_RATES_URL).decode("utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    rows: list[tuple[dt.date, float, float]] = []
    for tr in soup.find_all("tr"):
        cells = [" ".join(td.get_text(" ", strip=True).split()) for td in tr.find_all(["td", "th"])]
        if len(cells) < 4:
            continue
        d = parse_date(cells[0])
        if not d:
            continue
        y10 = parse_number(cells[-3])
        y30 = parse_number(cells[-1])
        if y10 is None or y30 is None:
            continue
        rows.append((d, y10, y30))
    if not rows:
        raise RuntimeError("Treasury 10Y/30Y rows could not be parsed")
    rows.sort(key=lambda x: x[0])
    latest = rows[-1]
    prev = rows[-2] if len(rows) >= 2 else latest
    prev5 = rows[-6] if len(rows) >= 6 else rows[0]
    return {
        "date": latest[0].isoformat(),
        "10y": latest[1],
        "30y": latest[2],
        "prev_date": prev[0].isoformat(),
        "prev_10y": prev[1],
        "prev_30y": prev[2],
        "daily_10y_bp": round((latest[1] - prev[1]) * 100, 1),
        "daily_30y_bp": round((latest[2] - prev[2]) * 100, 1),
        "prev5_date": prev5[0].isoformat(),
        "prev5_10y": prev5[1],
        "prev5_30y": prev5[2],
        "five_day_10y_bp": round((latest[1] - prev5[1]) * 100, 1),
        "five_day_30y_bp": round((latest[2] - prev5[2]) * 100, 1),
    }


def btc_etf_flow() -> dict:
    html = fetch(FARSIDE_BTC_ETF_URL).decode("utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []
    for tr in soup.find_all("tr"):
        cells = [" ".join(td.get_text(" ", strip=True).split()) for td in tr.find_all(["td", "th"])]
        if len(cells) < 3:
            continue
        d = parse_date(cells[0])
        if not d:
            continue

        fund_cells = cells[1:-1]
        normalized = [x.strip() for x in fund_cells]
        numeric_funds = [parse_number(x) for x in normalized if x not in {"", "-", "—"}]
        reported_count = sum(v is not None for v in numeric_funds)
        missing_count = sum(x in {"", "-", "—"} for x in normalized)
        total = parse_number(cells[-1])
        recomputed_total = round(sum(v for v in numeric_funds if v is not None), 1) if numeric_funds else None

        if reported_count == 0 and missing_count == len(normalized):
            status = "pending"
            total = None
            total_gap = None
            total_validated = False
        else:
            status = "partial" if missing_count > 0 else "complete"
            total_gap = round(total - recomputed_total, 1) if total is not None and recomputed_total is not None else None
            total_validated = total_gap is not None and abs(total_gap) <= 0.6

        rows.append({
            "date": d,
            "total": total,
            "status": status,
            "reported_funds": reported_count,
            "missing_funds": missing_count,
            "recomputed_total": recomputed_total,
            "total_gap": total_gap,
            "total_validated": total_validated,
        })

    if not rows:
        raise RuntimeError("Farside BTC ETF flow rows could not be parsed")

    rows.sort(key=lambda x: x["date"])
    source_latest = rows[-1]
    valid_rows = [
        x for x in rows
        if x["total"] is not None and x["status"] != "pending" and x.get("total_validated")
    ]
    if not valid_rows:
        raise RuntimeError("Farside has no validated BTC ETF flow rows")

    latest_valid = valid_rows[-1]
    prev_valid = valid_rows[-2] if len(valid_rows) >= 2 else latest_valid

    last5 = valid_rows[-5:]
    prev5 = valid_rows[-10:-5] if len(valid_rows) >= 10 else []
    last5_sum = round(sum(x["total"] for x in last5), 1)
    prev5_sum = round(sum(x["total"] for x in prev5), 1) if prev5 else None

    day_change = round(latest_valid["total"] - prev_valid["total"], 1)
    day_change_pct = (
        round(day_change / abs(prev_valid["total"]) * 100, 1)
        if prev_valid["total"] not in (None, 0)
        else None
    )
    five_day_compare_valid = len(last5) == 5 and len(prev5) == 5
    five_day_change = round(last5_sum - prev5_sum, 1) if five_day_compare_valid and prev5_sum is not None else None
    five_day_change_pct = (
        round(five_day_change / abs(prev5_sum) * 100, 1)
        if five_day_compare_valid and prev5_sum not in (None, 0) and last5_sum * prev5_sum > 0
        else None
    )
    five_day_direction = None
    if five_day_compare_valid and prev5_sum is not None:
        if prev5_sum < 0 < last5_sum:
            five_day_direction = "순유출→순유입 전환"
        elif prev5_sum > 0 > last5_sum:
            five_day_direction = "순유입→순유출 전환"
        elif last5_sum > prev5_sum:
            five_day_direction = "순자금흐름 개선"
        elif last5_sum < prev5_sum:
            five_day_direction = "순자금흐름 악화"
        else:
            five_day_direction = "변화 없음"

    return {
        "date": latest_valid["date"].isoformat(),
        "total_usd_m": latest_valid["total"],
        "status": latest_valid["status"],
        "reported_funds": latest_valid["reported_funds"],
        "missing_funds": latest_valid["missing_funds"],
        "prev_date": prev_valid["date"].isoformat(),
        "prev_total_usd_m": prev_valid["total"],
        "day_change_usd_m": day_change,
        "day_change_pct": day_change_pct,
        "source_latest_date": source_latest["date"].isoformat(),
        "source_latest_status": source_latest["status"],
        "pending_date": source_latest["date"].isoformat() if source_latest["status"] == "pending" else None,
        "latest_recomputed_total_usd_m": latest_valid.get("recomputed_total"),
        "latest_total_gap_usd_m": latest_valid.get("total_gap"),
        "latest_total_validated": latest_valid.get("total_validated"),
        "last5_usd_m": last5_sum,
        "last5_dates": [x["date"].isoformat() for x in last5],
        "last5_values_usd_m": [x["total"] for x in last5],
        "prev5_usd_m": prev5_sum,
        "prev5_dates": [x["date"].isoformat() for x in prev5],
        "prev5_values_usd_m": [x["total"] for x in prev5],
        "five_day_compare_valid": five_day_compare_valid,
        "five_day_change_usd_m": five_day_change,
        "five_day_change_pct": five_day_change_pct,
        "five_day_direction": five_day_direction,
    }


def buyback_schedule() -> dict:
    xml = fetch(TREASURY_BUYBACK_XML)
    text = xml.decode("utf-8", errors="replace")
    compact = " ".join(re.sub(r"<[^>]+>", " ", text).split())
    snippets = []
    for pattern in (r".{0,100}10.{0,12}20.{0,160}", r".{0,100}20.{0,12}30.{0,160}"):
        m = re.search(pattern, compact, flags=re.I)
        if m:
            snippets.append(m.group(0).strip())
    return {
        "sha256": sha256_bytes(xml),
        "bytes": len(xml),
        "long_bucket_summary": " | ".join(snippets)[:700],
    }


def signed_millions(value: float) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value:,.1f}백만달러"


def signed_pct(value: float | None) -> str:
    if value is None:
        return "비교 불가"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:,.1f}%"


def market_read(rates: dict, etf: dict) -> str:
    rate_date = rates.get("date")
    etf_date = etf.get("date")
    if not rate_date or not etf_date:
        return "종합판정 보류: 기준일 확인 불가"
    if rate_date != etf_date:
        return f"종합판정 보류: 기준일 불일치(미 국채 {rate_date} / BTC ETF {etf_date})"
    if etf.get("status") != "complete":
        return f"종합판정 보류: BTC ETF {etf_date} 집계 미완료"

    r10 = rates.get("daily_10y_bp", 0.0)
    r30 = rates.get("daily_30y_bp", 0.0)
    flow = etf.get("total_usd_m", 0.0)
    if r10 <= 0 and r30 <= 0 and flow > 0:
        return f"{rate_date} 기준 위험자산에 우호적: 장기금리 하락 + BTC ETF 순유입"
    if r10 >= 0 and r30 >= 0 and flow < 0:
        return f"{rate_date} 기준 위험자산에 불리: 장기금리 상승 + BTC ETF 순유출"
    return f"{rate_date} 기준 혼조: 금리와 ETF 자금흐름이 같은 방향이 아님"


def dated_values(obj: dict) -> dict[str, float]:
    result: dict[str, float] = {}
    for dates_key, values_key in (("prev5_dates", "prev5_values_usd_m"), ("last5_dates", "last5_values_usd_m")):
        for d, value in zip(obj.get(dates_key) or [], obj.get(values_key) or []):
            if d is not None and value is not None:
                result[str(d)] = float(value)
    return result


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ALERT_PATH.unlink(missing_ok=True)

    old = load_state()
    now_kst = dt.datetime.now(KST).isoformat(timespec="seconds")
    errors: list[str] = []

    try:
        buyback = buyback_schedule()
    except Exception as e:
        errors.append(f"buyback: {e}")
        buyback = old.get("buyback") or {}

    try:
        rates = treasury_rates()
    except Exception as e:
        errors.append(f"rates: {e}")
        rates = old.get("rates") or {}

    try:
        etf = btc_etf_flow()
    except Exception as e:
        errors.append(f"btc_etf: {e}")
        etf = old.get("btc_etf") or {}

    new_state = {
        "updated_at_kst": now_kst,
        "buyback": buyback,
        "rates": rates,
        "btc_etf": etf,
        "sources": {
            "treasury_buyback_xml": TREASURY_BUYBACK_XML,
            "treasury_buyback_page": TREASURY_BUYBACK_PAGE,
            "treasury_rates": TREASURY_RATES_URL,
            "farside_btc_etf": FARSIDE_BTC_ETF_URL,
        },
        "errors": errors,
    }
    atomic_write(PENDING_STATE, json.dumps(new_state, ensure_ascii=False, indent=2) + "\n")

    if not old:
        status = [
            "# 크립토 유동성 웹감시",
            "",
            "- 상태: 최초 기준값 저장 예정(텔레그램 미전송)",
            f"- 조회시각(KST): {now_kst}",
            f"- 미 국채 10Y/30Y: {rates.get('10y', 'N/A')}% / {rates.get('30y', 'N/A')}% ({rates.get('date', 'N/A')})",
            f"- BTC 현물 ETF 최신/직전: {signed_millions(etf.get('total_usd_m', 0.0)) if etf else 'N/A'} / {signed_millions(etf.get('prev_total_usd_m', 0.0)) if etf else 'N/A'} ({etf.get('date', 'N/A') if etf else 'N/A'} / {etf.get('prev_date', 'N/A') if etf else 'N/A'})",
            f"- BTC ETF 최근5/이전5: {signed_millions(etf.get('last5_usd_m', 0.0)) if etf else 'N/A'} / {signed_millions(etf.get('prev5_usd_m', 0.0)) if etf and etf.get('prev5_usd_m') is not None else 'N/A'}",
            f"- 오류: {'; '.join(errors) if errors else '없음'}",
        ]
        atomic_write(STATUS_PATH, "\n".join(status) + "\n")
        return

    triggers: list[str] = []

    old_buyback = old.get("buyback") or {}
    if buyback and old_buyback and buyback.get("sha256") != old_buyback.get("sha256"):
        triggers.append("미 재무부 공식 바이백 일정 XML 변경")

    old_rates = old.get("rates") or {}
    if rates and old_rates and rates.get("date") != old_rates.get("date"):
        d10 = (rates.get("10y", 0.0) - old_rates.get("10y", rates.get("10y", 0.0))) * 100
        d30 = (rates.get("30y", 0.0) - old_rates.get("30y", rates.get("30y", 0.0))) * 100
        if max(abs(d10), abs(d30)) >= 10.0:
            triggers.append(f"미 국채 장기금리 큰 변동: 10Y {d10:+.1f}bp / 30Y {d30:+.1f}bp")

    old_etf = old.get("btc_etf") or {}
    if etf and old_etf:
        old_date = old_etf.get("date")
        new_date = etf.get("date")
        pending_date = etf.get("pending_date")
        legacy_pending_zero = (
            pending_date
            and old_date == pending_date
            and float(old_etf.get("total_usd_m", 0.0) or 0.0) == 0.0
            and new_date != old_date
        )

        if new_date != old_date and not legacy_pending_zero:
            qualifier = "잠정 집계" if etf.get("status") == "partial" else "현재 전체 집계"
            triggers.append(f"BTC 현물 ETF 새 일간 자금흐름({qualifier}): {signed_millions(etf.get('total_usd_m', 0.0))}")
        elif new_date == old_date and abs(etf.get("total_usd_m", 0.0) - old_etf.get("total_usd_m", etf.get("total_usd_m", 0.0))) >= 0.1:
            qualifier = "잠정 집계" if etf.get("status") == "partial" else "현재 집계"
            triggers.append(
                f"BTC 현물 ETF 당일 합계 수정({qualifier}): {signed_millions(old_etf.get('total_usd_m', 0.0))} → {signed_millions(etf.get('total_usd_m', 0.0))}"
            )

        old_values = dated_values(old_etf)
        new_values = dated_values(etf)
        revisions = []
        for d in sorted(set(old_values) & set(new_values)):
            old_value = old_values[d]
            new_value = new_values[d]
            if abs(new_value - old_value) >= 0.1:
                revisions.append(f"{d} {signed_millions(old_value)} → {signed_millions(new_value)}")
        if revisions:
            triggers.append("BTC 현물 ETF 과거 원자료 수정: " + " / ".join(revisions))

        if new_date != old_date and old_etf.get("last5_usd_m") is not None and etf.get("last5_usd_m") is not None:
            d_last5 = round(etf.get("last5_usd_m") - old_etf.get("last5_usd_m"), 1)
            d_prev5 = (
                round(etf.get("prev5_usd_m") - old_etf.get("prev5_usd_m"), 1)
                if old_etf.get("prev5_usd_m") is not None and etf.get("prev5_usd_m") is not None
                else None
            )
            movement = (
                f"최근5 {signed_millions(old_etf.get('last5_usd_m', 0.0))} → {signed_millions(etf.get('last5_usd_m', 0.0))} ({signed_millions(d_last5)})"
            )
            if d_prev5 is not None:
                movement += (
                    f" / 이전5 {signed_millions(old_etf.get('prev5_usd_m', 0.0))} → {signed_millions(etf.get('prev5_usd_m', 0.0))} ({signed_millions(d_prev5)})"
                )
            triggers.append("BTC 현물 ETF 5거래일 구간 이동: " + movement)

    if triggers:
        lines = [
            "[크립토 유동성 변화 감지]",
            f"조회시각(KST): {now_kst}",
            "",
            *[f"• {x}" for x in triggers],
            "",
        ]
        if rates:
            lines += [
                f"미 국채 — 미 재무부 공식 수익률곡선 기준일 {rates.get('date', 'N/A')}",
                f"• 10Y {rates.get('10y', 0):.2f}% | 직전 공식일({rates.get('prev_date', 'N/A')}) 대비 {rates.get('daily_10y_bp', 0):+.1f}bp | 5거래일 {rates.get('five_day_10y_bp', 0):+.1f}bp",
                f"• 30Y {rates.get('30y', 0):.2f}% | 직전 공식일({rates.get('prev_date', 'N/A')}) 대비 {rates.get('daily_30y_bp', 0):+.1f}bp | 5거래일 {rates.get('five_day_30y_bp', 0):+.1f}bp",
                "※ 미 재무부 일일 수익률은 장중 실시간 시세가 아니라 약 3:30 PM ET 시장 호가를 바탕으로 산출되는 공식 일일값",
                "",
            ]
        if etf:
            etf_status = "잠정 집계" if etf.get("status") == "partial" else "현재 집계 완료(추후 수정 가능)"
            lines += [
                f"BTC 현물 ETF — Farside 기준 최신 유효일 {etf.get('date')}",
                f"• 최신: {etf.get('date')} {signed_millions(etf.get('total_usd_m', 0.0))} ({etf_status}, 개별 ETF 합계 재검산 {'일치' if etf.get('latest_total_validated') else '불일치'})",
                f"• 직전: {etf.get('prev_date')} {signed_millions(etf.get('prev_total_usd_m', 0.0))}",
                f"• 전일 대비: {signed_millions(etf.get('day_change_usd_m', 0.0))} ({signed_pct(etf.get('day_change_pct'))})",
            ]
            if etf.get("five_day_compare_valid"):
                last5_dates = etf.get("last5_dates") or []
                prev5_dates = etf.get("prev5_dates") or []
                last5_range = f"{last5_dates[0]}~{last5_dates[-1]}" if len(last5_dates) == 5 else "기간 확인 불가"
                prev5_range = f"{prev5_dates[0]}~{prev5_dates[-1]}" if len(prev5_dates) == 5 else "기간 확인 불가"
                direction = etf.get("five_day_direction") or "판정 불가"
                lines += [
                    f"• 최근 5거래일({last5_range}): {signed_millions(etf.get('last5_usd_m', 0.0))}",
                    f"• 이전 5거래일({prev5_range}): {signed_millions(etf.get('prev5_usd_m', 0.0))}",
                    f"• 5거래일 구간 대비: {signed_millions(etf.get('five_day_change_usd_m', 0.0))} | {direction}",
                ]
                if etf.get("five_day_change_pct") is not None:
                    lines += [f"• 5거래일 변화율: {signed_pct(etf.get('five_day_change_pct'))}"]
                elif etf.get("prev5_usd_m", 0.0) * etf.get("last5_usd_m", 0.0) < 0:
                    lines += ["• 5거래일 변화율: 부호 전환 구간이라 % 비교하지 않음"]
            else:
                lines += ["• 5거래일 구간 대비: 검증된 10개 거래일이 확보될 때까지 계산 보류"]
            if etf.get("pending_date"):
                lines += [f"※ {etf.get('pending_date')}: 전 ETF 미보고(-) → 0.0으로 간주하지 않고 미집계 처리"]
            lines += [""]
        if rates and etf:
            lines += [f"판단: {market_read(rates, etf)}"]
        lines += [
            "",
            "공식·데이터 원천:",
            f'• 미 재무부 바이백: <a href="{TREASURY_BUYBACK_PAGE}">원문</a>',
            f'• 미 국채 금리: <a href="{TREASURY_RATES_URL}">원문</a>',
            f'• BTC 현물 ETF: <a href="{FARSIDE_BTC_ETF_URL}">원문</a>',
            "",
            "※ CLARITY Act는 기존 별도 공식 웹감시가 계속 담당합니다.",
        ]
        atomic_write(ALERT_PATH, "\n".join(lines).strip() + "\n")

    status = [
        "# 크립토 유동성 웹감시",
        "",
        f"- 조회시각(KST): {now_kst}",
        f"- 알림 트리거: {len(triggers)}개",
        f"- 바이백 XML 변경: {'예' if (buyback and old_buyback and buyback.get('sha256') != old_buyback.get('sha256')) else '아니오'}",
        f"- 미 국채 10Y/30Y: {rates.get('10y', 'N/A')}% / {rates.get('30y', 'N/A')}% ({rates.get('date', 'N/A')})",
        f"- BTC 현물 ETF: {signed_millions(etf.get('total_usd_m', 0.0)) if etf else 'N/A'} ({etf.get('date', 'N/A') if etf else 'N/A'})",
        f"- 오류: {'; '.join(errors) if errors else '없음'}",
    ]
    atomic_write(STATUS_PATH, "\n".join(status) + "\n")


if __name__ == "__main__":
    main()
