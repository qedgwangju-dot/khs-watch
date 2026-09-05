#!/usr/bin/env python3
"""Structural demand layer for the global-rates / yen-carry Telegram watch.

The existing watcher measures rates, FX and market contagion. This module adds the
missing question: who is actually buying/selling, and is the JGB market absorbing
supply normally?

Official sources:
- Japan MOF JGB auction results
- GPIF latest asset allocation and policy portfolio
- BOJ Bond Market Survey release page
- Japan MOF FX-intervention statistics / release timetable
- FRED H.10 USD/KRW and USD/JPY for same-date KRW conversion

It never treats one auction, one yield, or one allocation move as automatic proof of
a yen-carry unwind. State persistence is left to the GitHub Actions workflow.
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import io
import json
import pathlib
import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
DATA = ROOT / "data"
OUT.mkdir(parents=True, exist_ok=True)
DATA.mkdir(parents=True, exist_ok=True)
STATE_PATH = DATA / "global_rates_structural_state.json"

MOF_AUCTION_EN = "https://www.mof.go.jp/english/policy/jgbs/auction/calendar/eresul/eresul{day}.htm"
GPIF_LATEST = "https://www.gpif.go.jp/operation/the-latest-results.html"
GPIF_PORTFOLIO = "https://www.gpif.go.jp/gpif/portfolio.html"
BOJ_BOND = "https://www.boj.or.jp/paym/bond/"
BOJ_BOND_TS = "https://www.boj.or.jp/paym/bond/timeseries.xlsx"
MOF_FEIO_OVERVIEW = "https://www.mof.go.jp/policy/international_policy/reference/feio/index.html"
MOF_FEIO_MONTHLY = "https://www.mof.go.jp/policy/international_policy/reference/feio/data/monthly/index.html"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
UA = "khs-watch-global-rates-structural/1.1"

ASSET_JP = {
    "domestic_bonds": "国内債券",
    "foreign_bonds": "外国債券",
    "domestic_equities": "国内株式",
    "foreign_equities": "外国株式",
}
ASSET_KO = {
    "domestic_bonds": "국내채권",
    "foreign_bonds": "외국채권",
    "domestic_equities": "국내주식",
    "foreign_equities": "외국주식",
}


def get_text(url: str, timeout: int = 25) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Cache-Control": "no-cache", "Accept": "text/html,*/*"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def load_json(path: pathlib.Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def clean_text(value: str) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", " ", value or ""))
    return re.sub(r"\s+", " ", value).strip()


def fnum(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "").replace("%", "").strip())
    except Exception:
        return None


class TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self.row: list[str] | None = None
        self.cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag == "tr":
            self.row = []
        elif tag in {"td", "th"} and self.row is not None:
            self.cell = []

    def handle_data(self, data: str) -> None:
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self.cell is not None and self.row is not None:
            self.row.append(re.sub(r"\s+", " ", " ".join(self.cell)).strip())
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if self.row:
                self.rows.append(self.row)
            self.row = None


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self.href: str | None = None
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() == "a":
            self.href = dict(attrs).get("href")
            self.parts = []

    def handle_data(self, data: str) -> None:
        if self.href is not None:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self.href is not None:
            self.links.append((re.sub(r"\s+", " ", " ".join(self.parts)).strip(), self.href))
            self.href = None
            self.parts = []


def parse_auction_result(page: str, url: str) -> dict[str, Any] | None:
    parser = TableParser()
    parser.feed(page)
    for row in parser.rows:
        if len(row) < 13:
            continue
        tenor = row[0].strip()
        if not re.fullmatch(r"(?:2|5|10|20|30|40)-Year", tenor):
            continue
        bids = fnum(row[6])
        accepted = fnum(row[7])
        low_yield = fnum(row[9])
        avg_yield = fnum(row[12])
        if None in (bids, accepted, low_yield, avg_yield) or not accepted:
            continue
        bid_to_cover = float(bids) / float(accepted)
        tail_bp = (float(low_yield) - float(avg_yield)) * 100.0
        result = {
            "tenor": tenor,
            "auction_date": row[2].strip(),
            "coupon_pct": fnum(row[5]),
            "competitive_bids_billion_yen": bids,
            "accepted_billion_yen": accepted,
            "bid_to_cover": bid_to_cover,
            "lowest_accepted_yield_pct": low_yield,
            "average_yield_pct": avg_yield,
            "tail_bp": tail_bp,
            "url": url,
        }
        result["grade"] = auction_grade(result)
        return result
    return None


def auction_grade(auction: dict[str, Any]) -> str:
    btc = float(auction["bid_to_cover"])
    tail = float(auction["tail_bp"])
    if btc <= 2.50 or tail >= 5.0:
        return "수요 매우 약함"
    if btc <= 2.80 or tail >= 3.0:
        return "수요 약함"
    if btc >= 3.50 and tail <= 1.0:
        return "수요 강함"
    return "중립"


def fetch_recent_auction(now: dt.datetime) -> dict[str, Any] | None:
    # Results are normally posted on the auction day. Looking back four calendar
    # days covers weekends without pretending that a non-auction day had a result.
    for offset in range(0, 5):
        day = now.date() - dt.timedelta(days=offset)
        url = MOF_AUCTION_EN.format(day=day.strftime("%Y%m%d"))
        try:
            parsed = parse_auction_result(get_text(url), url)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                continue
            raise
        if parsed:
            return parsed
    return None


def parse_gpif_latest(page: str) -> dict[str, Any]:
    text = clean_text(page)
    actual: dict[str, float] = {}
    amounts_oku: dict[str, float] = {}
    for key, jp_name in ASSET_JP.items():
        match = re.search(rf"{jp_name}\s*([0-9,]+)\s*([0-9.]+)%", text)
        if not match:
            raise RuntimeError(f"GPIF allocation not found: {jp_name}")
        amounts_oku[key] = float(match.group(1).replace(",", ""))
        actual[key] = float(match.group(2))
    total_match = re.search(r"合計\s*([0-9,]+)\s*100\.00%", text)
    if not total_match:
        raise RuntimeError("GPIF total assets not found")
    total_oku = float(total_match.group(1).replace(",", ""))
    return {
        "actual_pct": actual,
        "amounts_oku_yen": amounts_oku,
        "total_oku_yen": total_oku,
        "one_pct_point_trillion_yen": total_oku / 1_000_000.0,
        "url": GPIF_LATEST,
    }


def parse_gpif_policy(page: str) -> dict[str, Any]:
    text = clean_text(page)
    # Order on the official table: domestic bonds, foreign bonds, domestic equities,
    # foreign equities. Keep the parser strict so a page redesign fails visibly.
    target_match = re.search(
        r"資産構成割合\s*([0-9.]+)%\s*([0-9.]+)%\s*([0-9.]+)%\s*([0-9.]+)%",
        text,
    )
    tolerance_match = re.search(
        r"乖離許容幅.*?各資産\s*[±＋+]?([0-9.]+)[%％]\s*[±＋+]?([0-9.]+)[%％]\s*[±＋+]?([0-9.]+)[%％]\s*[±＋+]?([0-9.]+)[%％]",
        text,
    )
    if not target_match or not tolerance_match:
        raise RuntimeError("GPIF target/tolerance table not found")
    keys = list(ASSET_JP)
    return {
        "target_pct": {key: float(value) for key, value in zip(keys, target_match.groups())},
        "tolerance_pp": {key: float(value) for key, value in zip(keys, tolerance_match.groups())},
        "url": GPIF_PORTFOLIO,
    }


def parse_boj_survey(page: str) -> dict[str, Any] | None:
    text = clean_text(page)
    match = re.search(r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日.*?(20\d{2})年\s*(\d{1,2})月調査", text)
    if not match:
        return None
    posted = dt.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    survey_year = int(match.group(4))
    survey_month = int(match.group(5))
    label = f"{survey_year}年{survey_month}月調査"
    links = LinkParser()
    links.feed(page)
    result_url = BOJ_BOND
    for anchor, href in links.links:
        if label in anchor:
            result_url = urllib.parse.urljoin(BOJ_BOND, href)
            break
    return {
        "label": label,
        "posted_date": posted.isoformat(),
        "survey_year": survey_year,
        "survey_month": survey_month,
        "url": result_url,
        "timeseries_url": BOJ_BOND_TS,
    }


def parse_yen_amount(text: str) -> float | None:
    compact = str(text).replace(",", "")
    trillion = re.search(r"([0-9]+(?:\.[0-9]+)?)兆", compact)
    oku = re.search(r"([0-9]+(?:\.[0-9]+)?)億", compact)
    if trillion or oku:
        amount = 0.0
        if trillion:
            amount += float(trillion.group(1)) * 1_000_000_000_000.0
        if oku:
            amount += float(oku.group(1)) * 100_000_000.0
        return amount
    yen = re.search(r"([0-9]+(?:\.[0-9]+)?)円", compact)
    return float(yen.group(1)) if yen else None


def fetch_intervention_context() -> dict[str, Any] | None:
    # The overview is authoritative about monthly vs daily/quarterly disclosure.
    overview_text = clean_text(get_text(MOF_FEIO_OVERVIEW))
    overview_links = LinkParser()
    overview_links.feed(get_text(MOF_FEIO_OVERVIEW))

    monthly_page = get_text(MOF_FEIO_MONTHLY)
    links = LinkParser()
    links.feed(monthly_page)
    candidates: list[tuple[str, str]] = []
    for anchor, href in links.links:
        if "令和8年" in anchor and re.search(r"月\d+日", anchor):
            candidates.append((anchor, urllib.parse.urljoin(MOF_FEIO_MONTHLY, href)))
    if not candidates:
        return {
            "url": MOF_FEIO_OVERVIEW,
            "amount_yen": None,
            "efficiency_rule": "월간 총액만으로 개입 효율 계산 금지 — 일별 공식자료에서만 계산",
        }

    period, detail_url = candidates[0]
    detail = clean_text(get_text(detail_url))
    amount_match = re.search(r"(?:操作額|介入額)[^0-9]*([0-9兆億,]+円)", detail)
    if not amount_match:
        amount_match = re.search(r"([0-9]+兆[0-9,]+億円)", detail)
    amount_yen = parse_yen_amount(amount_match.group(1)) if amount_match else None

    next_daily = None
    schedule = re.search(
        r"令和8年11月2日[-～〜]9日\s*日次ベース（令和8年7月[～〜]令和8年9月）",
        overview_text,
    )
    if schedule:
        next_daily = "2026-11-02~11-09 (2026년 7~9월 일별 상세)"
    return {
        "period": period,
        "amount_yen": amount_yen,
        "url": detail_url,
        "overview_url": MOF_FEIO_OVERVIEW,
        "next_daily_detail_release": next_daily,
        "efficiency_rule": "월간 총액은 실시일별 금액을 알 수 없어 1조엔당 USD/JPY 효과를 계산하지 않음. 분기 일별자료 공개 후 계산.",
    }


def fetch_fred_rows(series_id: str, keep: int = 90) -> dict[str, float]:
    url = FRED_CSV + "?" + urllib.parse.urlencode({"id": series_id})
    text = get_text(url)
    rows: list[tuple[str, float]] = []
    for row in csv.DictReader(io.StringIO(text)):
        day = (row.get("DATE") or row.get("observation_date") or "").strip()
        value = fnum(row.get(series_id))
        if day and value is not None:
            rows.append((day, value))
    return dict(rows[-keep:])


def latest_common_fx() -> dict[str, Any] | None:
    try:
        krw = fetch_fred_rows("DEXKOUS")
        jpy = fetch_fred_rows("DEXJPUS")
        common = sorted(set(krw) & set(jpy))
        if not common:
            return None
        day = common[-1]
        usdkrw = krw[day]
        usdjpy = jpy[day]
        from fx_api import _validate, UTC
        import datetime as fx_dt
        now = fx_dt.datetime.now(UTC)
        usdkrw, day = _validate(usdkrw, day, now)
        usdjpy, _ = _validate(usdjpy, day, now)
        return {"date": day, "usdkrw": usdkrw, "usdjpy": usdjpy, "yenkrw": usdkrw / usdjpy}
    except Exception:
        return None


def yen_to_krw(amount_yen: float | None, fx: dict[str, Any] | None) -> float | None:
    if amount_yen is None or fx is None:
        return None
    return amount_yen * float(fx["yenkrw"])


def gpif_zero_sum_summary(previous: dict[str, float], current: dict[str, float]) -> str:
    changes = {key: current.get(key, 0.0) - previous.get(key, 0.0) for key in ASSET_JP}
    increases = sorted(((value, ASSET_KO[key]) for key, value in changes.items() if value > 0), reverse=True)
    decreases = sorted(((value, ASSET_KO[key]) for key, value in changes.items() if value < 0))
    if not increases and not decreases:
        return "비중 변화 없음"
    inc = ", ".join(f"{name} +{value:.2f}%p" for value, name in increases) or "증가 자산 없음"
    dec = ", ".join(f"{name} {value:.2f}%p" for value, name in decreases) or "감소 자산 없음"
    return f"증가: {inc} / 감소: {dec}"


def main() -> int:
    now = dt.datetime.now(KST)
    previous = load_json(STATE_PATH, {})
    errors: list[str] = []
    events: list[dict[str, Any]] = []
    fx = latest_common_fx()

    auction = None
    try:
        auction = fetch_recent_auction(now)
    except Exception as exc:
        errors.append(f"JGB auction: {type(exc).__name__}: {exc}")

    gpif = None
    try:
        gpif = parse_gpif_latest(get_text(GPIF_LATEST))
        gpif.update(parse_gpif_policy(get_text(GPIF_PORTFOLIO)))
        gpif["total_krw"] = yen_to_krw(gpif["total_oku_yen"] * 1e8, fx)
        gpif["one_pct_point_krw"] = yen_to_krw(gpif["one_pct_point_trillion_yen"] * 1e12, fx)
    except Exception as exc:
        errors.append(f"GPIF: {type(exc).__name__}: {exc}")

    survey = None
    try:
        survey = parse_boj_survey(get_text(BOJ_BOND))
    except Exception as exc:
        errors.append(f"BOJ bond survey: {type(exc).__name__}: {exc}")

    intervention = None
    try:
        intervention = fetch_intervention_context()
        if intervention:
            intervention["amount_krw"] = yen_to_krw(intervention.get("amount_yen"), fx)
    except Exception as exc:
        errors.append(f"MOF intervention: {type(exc).__name__}: {exc}")

    previous_auctions = dict(previous.get("auctions") or {})
    next_auctions = dict(previous_auctions)
    signals = {
        "jgb_auction_weak": False,
        "gpif_domestic_bond_shift": False,
        "gpif_policy_changed": False,
        "boj_survey_new": False,
    }

    if auction:
        tenor = str(auction["tenor"])
        old = previous_auctions.get(tenor) or {}
        new_date = auction["auction_date"] != old.get("auction_date")
        grade = auction["grade"]
        signals["jgb_auction_weak"] = grade in {"수요 약함", "수요 매우 약함"}
        auction["accepted_krw"] = yen_to_krw(float(auction["accepted_billion_yen"]) * 1e9, fx)
        if new_date:
            if grade in {"수요 약함", "수요 매우 약함"}:
                events.append({
                    "type": "jgb_auction_weak",
                    "severity": 2 if grade == "수요 매우 약함" else 1,
                    "summary": f"JGB {tenor.replace('-Year','년')} 입찰 {grade}: 응찰배율 {auction['bid_to_cover']:.2f}배 / 꼬리 {auction['tail_bp']:.1f}bp",
                })
            elif grade == "수요 강함" and old.get("grade") in {"수요 약함", "수요 매우 약함"}:
                events.append({
                    "type": "jgb_auction_recovery",
                    "severity": 1,
                    "summary": f"JGB {tenor.replace('-Year','년')} 입찰 수요 회복: 응찰배율 {auction['bid_to_cover']:.2f}배 / 꼬리 {auction['tail_bp']:.1f}bp",
                })
        next_auctions[tenor] = auction

    if gpif:
        old_gpif = previous.get("gpif") or {}
        old_actual = old_gpif.get("actual_pct") or {}
        old_target = old_gpif.get("target_pct") or {}
        old_tolerance = old_gpif.get("tolerance_pp") or {}
        if old_actual:
            domestic_delta = gpif["actual_pct"]["domestic_bonds"] - float(old_actual.get("domestic_bonds", gpif["actual_pct"]["domestic_bonds"]))
            gpif["domestic_bonds_delta_pp"] = domestic_delta
            gpif["zero_sum_summary"] = gpif_zero_sum_summary(old_actual, gpif["actual_pct"])
            if abs(domestic_delta) >= 1.0:
                signals["gpif_domestic_bond_shift"] = True
                events.append({
                    "type": "gpif_allocation_shift",
                    "severity": 1,
                    "summary": f"GPIF 국내채권 실제 비중 {domestic_delta:+.2f}%p 이동 — {gpif['zero_sum_summary']}",
                })
        else:
            gpif["domestic_bonds_delta_pp"] = None
            gpif["zero_sum_summary"] = "첫 기준선 저장 — 다음 공식 분기와 제로섬 비교"
        if old_target and (gpif["target_pct"] != old_target or gpif["tolerance_pp"] != old_tolerance):
            signals["gpif_policy_changed"] = True
            events.append({
                "type": "gpif_policy_change",
                "severity": 3,
                "summary": "GPIF 기본 포트폴리오 목표비중 또는 허용범위 변경",
            })

    if survey:
        old_survey = previous.get("boj_survey") or {}
        changed = survey.get("label") != old_survey.get("label")
        posted_today = survey.get("posted_date") == now.date().isoformat()
        if changed and (old_survey or posted_today):
            signals["boj_survey_new"] = True
            events.append({
                "type": "boj_bond_survey_new",
                "severity": 1,
                "summary": f"BOJ 채권시장 서베이 새 발표: {survey['label']} — 시장 기능도·장기금리 전망 원문 확인",
            })

    result = {
        "checked_at_kst": now.isoformat(timespec="seconds"),
        "auction": auction,
        "gpif": gpif,
        "boj_survey": survey,
        "intervention": intervention,
        "fx": fx,
        "signals": signals,
        "errors": errors,
        "rules": {
            "auction": "JGB 금리 수준과 별도로 응찰배율·입찰 꼬리로 실제 수요를 확인",
            "gpif": "국내채권 확대만 보지 않고 총합 100%에서 줄어드는 반대편 자산을 함께 확인",
            "intervention": "월간 총액만 공개된 단계에서는 1조엔당 개입효율을 계산하지 않고 분기 일별자료에서만 계산",
            "ois": "신뢰 가능한 공개 자동 시계열이 없으면 임의 추정하지 않음. 주요매체가 시장 내재확률을 숫자로 명시할 때만 출처를 붙인 보도값으로 사용",
        },
    }
    pending = {
        "updated_at_kst": result["checked_at_kst"],
        "auctions": next_auctions,
        "gpif": gpif or previous.get("gpif"),
        "boj_survey": survey or previous.get("boj_survey"),
        "intervention": intervention or previous.get("intervention"),
    }
    write_json(OUT / "global_rates_structural.json", result)
    write_json(OUT / "global_rates_structural_pending_state.json", pending)

    event_path = OUT / "global_rates_structural_event.json"
    if events:
        write_json(event_path, {"checked_at_kst": result["checked_at_kst"], "events": events})
    elif event_path.exists():
        event_path.unlink()

    print(json.dumps({"events": len(events), "signals": signals, "errors": errors}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
