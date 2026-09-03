#!/usr/bin/env python3
"""Japan -> U.S. Treasury spillover monitor.

This lane watches the transmission channels that are easy to conflate:
1) Japanese residents' foreign long-term debt flows (MOF weekly, not equity+bond subtotal),
2) JGB auction demand from 2Y through 40Y,
3) foreign-official/FIMA repo usage in Fed H.4.1,
4) a conservative Treasury basis/repo-stress proxy using SOFR-IORB and 10Y/30Y yields.

It deliberately does NOT treat Japan's TIC holdings, hedge-fund gross Treasury exposure,
or MMF AUM as directly comparable pools of final-duration demand.
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import io
import json
import pathlib
import re
import urllib.parse
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from khs_source_fetch import fetch_text, record_source_failure
from krw_fx import format_krw, latest_jpy_krw

KST = ZoneInfo("Asia/Seoul")
ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "out"
DATA.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)

STATE_PATH = DATA / "japan_treasury_spillover_state.json"
PENDING_PATH = OUT / "japan_treasury_spillover_pending.json"
ALERT_PATH = OUT / "japan_treasury_spillover_alert.html"
TITLE_PATH = OUT / "japan_treasury_spillover_title.txt"
STATUS_PATH = OUT / "japan_treasury_spillover_status.md"

UA = "Mozilla/5.0 khs-japan-treasury-spillover/1.0"
MOF_WEEK = "https://www.mof.go.jp/policy/international_policy/reference/itn_transactions_in_securities/week.csv"
MOF_JGB_YIELDS = "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv"
MOF_JGB_NEWS = "https://www.mof.go.jp/english/public_relations/whats_new/2026jgbs.html"
FED_H41 = "https://www.federalreserve.gov/releases/h41/current/"
FED_FIMA = "https://www.federalreserve.gov/monetarypolicy/fima-repo-facility-faqs.htm"
FED_HF = "https://www.federalreserve.gov/econres/notes/feds-notes/decomposing-hedge-funds-u-s-treasury-exposures-20260622.html"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv"
TENORS = (2, 10, 20, 30, 40)

LT_DEBT_WEEKLY_SELL_TRILLION_YEN = -0.50
LT_DEBT_TWO_WEEK_SELL_TRILLION_YEN = -1.00
JGB_BTC_WEAK = 3.0
JGB_BTC_DROP_PCT = -15.0
JGB_TAIL_BP = 2.5
JGB_TAIL_WIDEN_BP = 1.0
FIMA_HIGH_BN_USD = 1.0
REPO_SPREAD_BP = 10.0
REPO_SPREAD_JUMP_BP = 5.0
UST_LONG_YIELD_JUMP_BP = 8.0
JGB2_UP_BP = 5.0
YEN_STRENGTH_PCT = -1.0


def num(value) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace("%", "").replace("−", "-").replace("△", "-")
    text = re.sub(r"\s+", "", text)
    if text in {"", ".", "-", "+"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def load_state() -> dict:
    try:
        value = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def source(name: str, url: str, now: dt.datetime, *, accept: str = "text/html,application/xhtml+xml,*/*") -> str:
    text, error = fetch_text(url, UA, timeout=20, attempts=2, accept=accept)
    if error or not text:
        record_source_failure(
            lane="japan_treasury_spillover",
            source_name=name,
            source_url=url,
            error=error or "empty response",
            checked_at=now,
        )
        raise RuntimeError(error or f"{name}: empty response")
    return text


def normalize_week(label: str) -> str:
    parts = [int(x) for x in re.findall(r"\d+", label)]
    if len(parts) >= 5 and parts[0] >= 2000:
        return f"{parts[0]:04d}-{parts[1]:02d}-{parts[2]:02d}~{parts[3]:02d}-{parts[4]:02d}"
    return re.sub(r"\s+", " ", label.strip())


@dataclass(frozen=True)
class MofFlow:
    latest_week: str
    previous_week: str
    latest_lt_debt_trillion_yen: float
    previous_lt_debt_trillion_yen: float
    two_week_lt_debt_trillion_yen: float
    latest_equity_plus_lt_trillion_yen: float


def parse_mof_week_csv(text: str) -> MofFlow:
    rows: list[tuple[str, float, float]] = []
    for row in csv.reader(io.StringIO(text.lstrip("\ufeff"))):
        if len(row) < 12 or not any(ch.isdigit() for ch in (row[0] or "")):
            continue
        lt = num(row[6])
        subtotal = num(row[7])
        if lt is None or subtotal is None:
            continue
        rows.append((normalize_week(row[0]), lt / 10000.0, subtotal / 10000.0))
    if len(rows) < 2:
        raise RuntimeError(f"MOF week.csv needs >=2 complete rows, got {len(rows)}")
    prev, cur = rows[-2], rows[-1]
    return MofFlow(
        latest_week=cur[0],
        previous_week=prev[0],
        latest_lt_debt_trillion_yen=cur[1],
        previous_lt_debt_trillion_yen=prev[1],
        two_week_lt_debt_trillion_yen=cur[1] + prev[1],
        latest_equity_plus_lt_trillion_yen=cur[2],
    )


def norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def parse_jgb_yields(text: str) -> tuple[dict, dict]:
    rows = list(csv.reader(io.StringIO(text.lstrip("\ufeff"))))
    header_i = next((i for i, row in enumerate(rows[:12]) if any(norm(c) == "date" for c in row)), None)
    if header_i is None:
        raise RuntimeError("MOF JGB yield header not found")
    header = [c.strip() for c in rows[header_i]]
    nh = [norm(c) for c in header]

    def col(*candidates: str) -> int:
        wanted = {norm(x) for x in candidates}
        for index, key in enumerate(nh):
            if key in wanted:
                return index
        raise RuntimeError(f"JGB column missing {candidates}; header={header}")

    idx = {
        "date": col("Date"),
        "jgb2": col("2", "2Y", "2 year", "2-year"),
        "jgb10": col("10", "10Y", "10 year", "10-year"),
        "jgb20": col("20", "20Y", "20 year", "20-year"),
        "jgb30": col("30", "30Y", "30 year", "30-year"),
        "jgb40": col("40", "40Y", "40 year", "40-year"),
    }
    good: list[dict] = []
    for row in rows[header_i + 1 :]:
        if not row or len(row) <= max(idx.values()):
            continue
        item = {"date": row[idx["date"]].strip()}
        ok = bool(item["date"])
        for key in ("jgb2", "jgb10", "jgb20", "jgb30", "jgb40"):
            item[key] = num(row[idx[key]])
            ok = ok and item[key] is not None
        if ok:
            good.append(item)
    if len(good) < 2:
        raise RuntimeError("MOF JGB yield CSV has fewer than two complete rows")
    return good[-2], good[-1]


@dataclass(frozen=True)
class Auction:
    tenor: int
    date: str
    url: str
    bids_bn_yen: float
    accepted_bn_yen: float
    low_yield: float
    avg_yield: float

    @property
    def btc(self) -> float:
        return self.bids_bn_yen / self.accepted_bn_yen

    @property
    def tail_bp(self) -> float:
        return (self.low_yield - self.avg_yield) * 100.0


def absolute(base: str, href: str) -> str:
    return urllib.parse.urljoin(base, href)


def parse_auction(text: str, url: str, tenor: int) -> Auction:
    soup = BeautifulSoup(text, "html.parser")
    for tr in soup.find_all("tr"):
        cells = [" ".join(td.stripped_strings) for td in tr.find_all(["td", "th"])]
        if not cells or len(cells) < 13:
            continue
        if not re.fullmatch(rf"{tenor}-Year", cells[0].strip(), re.I):
            continue
        bids = num(cells[6])
        accepted = num(cells[7])
        low_y = num(cells[9])
        avg_y = num(cells[12])
        if None not in (bids, accepted, low_y, avg_y):
            return Auction(tenor, cells[2].strip(), url, float(bids), float(accepted), float(low_y), float(avg_y))
    raise RuntimeError(f"auction row not found: {tenor}Y {url}")


def latest_two_auctions(news_text: str, tenor: int, now: dt.datetime) -> tuple[Auction, Auction] | None:
    soup = BeautifulSoup(news_text, "html.parser")
    pattern = re.compile(rf"Auction Result of {tenor}-Year JGBs", re.I)
    links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        label = " ".join(anchor.stripped_strings)
        if pattern.search(label) and "Market Special Participants" not in label:
            url = absolute(MOF_JGB_NEWS, anchor["href"])
            if url not in links:
                links.append(url)
    if len(links) < 2:
        return None
    new_url, old_url = links[0], links[1]
    new_text = source(f"MOF {tenor}Y auction new", new_url, now)
    old_text = source(f"MOF {tenor}Y auction old", old_url, now)
    return parse_auction(old_text, old_url, tenor), parse_auction(new_text, new_url, tenor)


@dataclass(frozen=True)
class FimaProxy:
    release_date: str
    level_bn_usd: float
    weekly_change_bn_usd: float | None


def parse_h41_foreign_official_repo(text: str) -> FimaProxy:
    soup = BeautifulSoup(text, "html.parser")
    plain = " ".join(soup.stripped_strings)
    release_match = re.search(r"Release Date:\s*([A-Z][a-z]+\s+\d{1,2},\s+20\d{2})", plain)
    release_date = release_match.group(1) if release_match else "unknown"
    in_repo = False
    for tr in soup.find_all("tr"):
        cells = [" ".join(td.stripped_strings) for td in tr.find_all(["td", "th"])]
        if not cells:
            continue
        first = cells[0].strip().lower()
        if "reverse repurchase" in first:
            in_repo = False
        elif first.startswith("repurchase agreements"):
            in_repo = True
            continue
        if in_repo and first == "foreign official":
            values = [num(cell) for cell in cells[1:]]
            values = [x for x in values if x is not None]
            if not values:
                break
            level = values[0] / 1000.0
            change = values[1] / 1000.0 if len(values) > 1 else None
            return FimaProxy(release_date, level, change)
    match = re.search(
        r"Repurchase agreements(?:\s+\d+)?\s+[^A-Za-z]{0,80}Foreign official\s+([+\-]?\s*[\d,]+)\s+([+\-]?\s*[\d,]+)",
        plain,
        re.I,
    )
    if match:
        level = num(match.group(1))
        change = num(match.group(2))
        if level is not None:
            return FimaProxy(release_date, level / 1000.0, None if change is None else change / 1000.0)
    raise RuntimeError("Fed H.4.1 foreign official repo row not found")


def fred_map(series: str, now: dt.datetime) -> dict[str, float]:
    today = now.astimezone(dt.timezone.utc).date()
    start = today - dt.timedelta(days=45)
    url = FRED + "?" + urllib.parse.urlencode({"id": series, "cosd": start.isoformat(), "coed": today.isoformat()})
    text = source(f"FRED {series}", url, now, accept="text/csv,text/plain,*/*")
    out: dict[str, float] = {}
    for row in csv.DictReader(io.StringIO(text.lstrip("\ufeff"))):
        date = (row.get("DATE") or row.get("observation_date") or "").strip()
        value = num(row.get(series))
        if date and value is not None:
            out[date] = value
    if not out:
        raise RuntimeError(f"FRED {series}: no observations")
    return out


def latest_two(values: dict[str, float]) -> tuple[tuple[str, float], tuple[str, float]]:
    keys = sorted(values)
    if len(keys) < 2:
        raise RuntimeError("series needs two observations")
    return (keys[-2], values[keys[-2]]), (keys[-1], values[keys[-1]])


def market_snapshot(now: dt.datetime) -> dict:
    d10 = fred_map("DGS10", now)
    d30 = fred_map("DGS30", now)
    so = fred_map("SOFR", now)
    io_ = fred_map("IORB", now)
    jpy = fred_map("DEXJPUS", now)
    (_, d10p), (d10d, d10c) = latest_two(d10)
    (_, d30p), (d30d, d30c) = latest_two(d30)
    (_, jpyp), (jpyd, jpyc) = latest_two(jpy)
    common = sorted(set(so) & set(io_))
    if len(common) < 2:
        raise RuntimeError("SOFR/IORB have fewer than two common dates")
    pday, cday = common[-2], common[-1]
    spread_prev = (so[pday] - io_[pday]) * 100.0
    spread_cur = (so[cday] - io_[cday]) * 100.0
    return {
        "market_date": max(d10d, d30d, jpyd, cday),
        "dgs10": d10c,
        "dgs10_change_bp": (d10c - d10p) * 100.0,
        "dgs30": d30c,
        "dgs30_change_bp": (d30c - d30p) * 100.0,
        "sofr_iorb_date": cday,
        "sofr_iorb_bp": spread_cur,
        "sofr_iorb_change_bp": spread_cur - spread_prev,
        "usdjpy_date": jpyd,
        "usdjpy": jpyc,
        "usdjpy_change_pct": (jpyc / jpyp - 1.0) * 100.0,
    }


def pct(new: float, old: float) -> float:
    return (new / old - 1.0) * 100.0


def bp(new: float, old: float) -> float:
    return (new - old) * 100.0


def fmt_trillion_yen(value: float, quote) -> str:
    won = value * 1_000_000_000_000.0 * quote.krw_per_yen
    return f"{value:+,.2f}조엔 (약 {format_krw(won)})"


def fmt_usd_bn(value: float, quote) -> str:
    won = value * 1_000_000_000.0 * quote.usdkrw
    return f"{value:,.2f}십억달러 (약 {format_krw(won)})"


def classify_events(*, first: bool, state: dict, flow: MofFlow | None, yields: tuple[dict, dict] | None,
                    auctions: dict[str, dict], fima: FimaProxy | None, market: dict | None) -> list[dict]:
    events: list[dict] = []
    old_sources = state.get("source_dates") or {}
    old_snap = state.get("snapshot") or {}

    flow_new = bool(flow and flow.latest_week != old_sources.get("mof_week"))
    if not first and flow_new and flow:
        if (flow.latest_lt_debt_trillion_yen <= LT_DEBT_WEEKLY_SELL_TRILLION_YEN or
                flow.two_week_lt_debt_trillion_yen <= LT_DEBT_TWO_WEEK_SELL_TRILLION_YEN):
            events.append({"kind": "lt_debt_sale", "severity": "WATCH"})

    if not first:
        for tenor, row in auctions.items():
            old_date = ((state.get("auctions") or {}).get(tenor) or {}).get("date")
            if row.get("date") == old_date:
                continue
            weak = (
                row["btc"] < JGB_BTC_WEAK
                or row["btc_drop_pct"] <= JGB_BTC_DROP_PCT
                or (row["tail_bp"] >= JGB_TAIL_BP and row["tail_widen_bp"] >= JGB_TAIL_WIDEN_BP)
            )
            if weak:
                sev = "HIGH" if int(tenor) in (2, 10) else "WATCH"
                events.append({"kind": "jgb_auction", "severity": sev, "tenor": int(tenor)})

    if not first and fima and fima.release_date != old_sources.get("h41"):
        old_level = float(old_snap.get("fima_bn_usd") or 0.0)
        if fima.level_bn_usd > 0 and (old_level <= 0 or fima.level_bn_usd > old_level):
            sev = "HIGH" if fima.level_bn_usd >= FIMA_HIGH_BN_USD else "WATCH"
            events.append({"kind": "fima", "severity": sev})

    if not first and market and market.get("market_date") != old_sources.get("market"):
        repo_stress = (
            market["sofr_iorb_bp"] >= REPO_SPREAD_BP
            or market["sofr_iorb_change_bp"] >= REPO_SPREAD_JUMP_BP
        )
        long_yield_jump = max(market["dgs10_change_bp"], market["dgs30_change_bp"]) >= UST_LONG_YIELD_JUMP_BP
        if repo_stress and long_yield_jump:
            events.append({"kind": "basis_proxy", "severity": "HIGH"})

    if not first and flow_new and flow and yields and market:
        prev_y, cur_y = yields
        jgb2_up = bp(cur_y["jgb2"], prev_y["jgb2"])
        selling = (
            flow.latest_lt_debt_trillion_yen <= LT_DEBT_WEEKLY_SELL_TRILLION_YEN
            or flow.two_week_lt_debt_trillion_yen <= LT_DEBT_TWO_WEEK_SELL_TRILLION_YEN
        )
        yen_strong = market["usdjpy_change_pct"] <= YEN_STRENGTH_PCT
        ust_up = max(market["dgs10_change_bp"], market["dgs30_change_bp"]) >= UST_LONG_YIELD_JUMP_BP
        if selling and jgb2_up >= JGB2_UP_BP and yen_strong:
            events.append({"kind": "repatriation_combo", "severity": "CRITICAL"})
        elif selling and ust_up:
            events.append({"kind": "ust_spillover", "severity": "HIGH"})

    kinds = {event["kind"] for event in events}
    if "fima" in kinds and ({"lt_debt_sale", "repatriation_combo", "basis_proxy"} & kinds):
        events.append({"kind": "official_private_overlap", "severity": "CRITICAL"})
    return events


def event_text(event: dict) -> str:
    kind = event["kind"]
    if kind == "lt_debt_sale":
        return "일본 거주자의 해외 중장기채 순매도가 임계치를 넘음"
    if kind == "jgb_auction":
        return f"JGB {event['tenor']}년 입찰 수요 약화"
    if kind == "fima":
        return "Fed H.4.1 외국공식 레포 사용 증가 — FIMA 사용 가능성 프록시"
    if kind == "basis_proxy":
        return "SOFR-IORB와 미국 10·30년 금리가 함께 긴장 — 베이시스/레포 스트레스 프록시"
    if kind == "repatriation_combo":
        return "해외 중장기채 매도 + JGB2 상승 + 엔화 강세가 동시 발생 — 본국회귀 위험"
    if kind == "ust_spillover":
        return "일본 해외채 매도와 미국 장기금리 상승이 동시 발생"
    if kind == "official_private_overlap":
        return "공적 달러조달과 민간 해외채 매도가 겹침 — 최상위 복합 경보"
    return kind


def main() -> int:
    now = dt.datetime.now(KST)
    for path in (ALERT_PATH, TITLE_PATH):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    state = load_state()
    first = not bool(state.get("initialized"))
    errors: list[str] = []

    flow = None
    yields = None
    fima = None
    market = None
    auctions: dict[str, dict] = {}

    try:
        flow = parse_mof_week_csv(source("Japan MOF weekly securities", MOF_WEEK, now, accept="text/csv,text/plain,*/*"))
    except Exception as exc:
        errors.append(f"MOF weekly: {type(exc).__name__}: {exc}")

    try:
        yields = parse_jgb_yields(source("Japan MOF JGB yields", MOF_JGB_YIELDS, now, accept="text/csv,text/plain,*/*"))
    except Exception as exc:
        errors.append(f"JGB yields: {type(exc).__name__}: {exc}")

    try:
        news = source("Japan MOF JGB what's new", MOF_JGB_NEWS, now)
        for tenor in TENORS:
            pair = latest_two_auctions(news, tenor, now)
            if pair is None:
                continue
            old, new = pair
            auctions[str(tenor)] = {
                "date": new.date,
                "url": new.url,
                "btc": new.btc,
                "btc_drop_pct": pct(new.btc, old.btc),
                "tail_bp": new.tail_bp,
                "tail_widen_bp": new.tail_bp - old.tail_bp,
                "prev_date": old.date,
                "prev_btc": old.btc,
                "prev_tail_bp": old.tail_bp,
            }
    except Exception as exc:
        errors.append(f"JGB auctions: {type(exc).__name__}: {exc}")

    try:
        fima = parse_h41_foreign_official_repo(source("Federal Reserve H.4.1", FED_H41, now))
    except Exception as exc:
        errors.append(f"FIMA/H41: {type(exc).__name__}: {exc}")

    try:
        market = market_snapshot(now)
    except Exception as exc:
        errors.append(f"market: {type(exc).__name__}: {exc}")

    try:
        quote = latest_jpy_krw()
    except Exception as exc:
        quote = None
        errors.append(f"FX conversion: {type(exc).__name__}: {exc}")

    events = classify_events(
        first=first,
        state=state,
        flow=flow,
        yields=yields,
        auctions=auctions,
        fima=fima,
        market=market,
    )

    source_dates = {
        "mof_week": flow.latest_week if flow else None,
        "jgb_yield": yields[1]["date"] if yields else None,
        "h41": fima.release_date if fima else None,
        "market": market.get("market_date") if market else None,
    }
    snapshot = {
        "lt_debt_week_trillion_yen": flow.latest_lt_debt_trillion_yen if flow else None,
        "lt_debt_two_week_trillion_yen": flow.two_week_lt_debt_trillion_yen if flow else None,
        "equity_plus_lt_week_trillion_yen": flow.latest_equity_plus_lt_trillion_yen if flow else None,
        "fima_bn_usd": fima.level_bn_usd if fima else None,
        "fima_weekly_change_bn_usd": fima.weekly_change_bn_usd if fima else None,
        "market": market,
    }
    pending = {
        "initialized": True,
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "source_dates": source_dates,
        "snapshot": snapshot,
        "auctions": auctions,
    }
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    status_lines = [
        "# 일본→미국채 복합 수급 감시",
        "",
        f"- 조회: {now.isoformat(timespec='seconds')}",
        f"- 상태: {'초기 기준선 생성 — 발송 안 함' if first else ('경보 생성' if events else '새 복합 경보 없음')}",
        "- 소스: MOF 해외 중장기채·JGB 2/10/20/30/40년 입찰·Fed H.4.1 외국공식 레포·FRED SOFR/IORB/UST/JPY",
    ]
    if errors:
        status_lines += ["", "## 부분 확인"] + [f"- {html.escape(err)}" for err in errors]
    STATUS_PATH.write_text("\n".join(status_lines) + "\n", encoding="utf-8")

    if first or not events:
        return 0

    rank = {"WATCH": 1, "HIGH": 2, "CRITICAL": 3}
    severity = max((event["severity"] for event in events), key=lambda x: rank[x])
    badge = {"WATCH": "🟡", "HIGH": "🟠", "CRITICAL": "🔴"}[severity]
    TITLE_PATH.write_text(f"{badge} 일본→미국채 복합 수급 {severity}", encoding="utf-8")

    lines: list[str] = [
        "<b>핵심 판단</b>",
        *[f"• {html.escape(event_text(event))}" for event in events],
        "",
        "<b>확정 숫자</b>",
    ]
    if flow:
        latest = fmt_trillion_yen(flow.latest_lt_debt_trillion_yen, quote) if quote else f"{flow.latest_lt_debt_trillion_yen:+.2f}조엔"
        two = fmt_trillion_yen(flow.two_week_lt_debt_trillion_yen, quote) if quote else f"{flow.two_week_lt_debt_trillion_yen:+.2f}조엔"
        lines += [
            f"• 일본 거주자 해외 중장기채: {html.escape(flow.latest_week)} <b>{latest}</b>",
            f"  └ 최근 2주 합계 <b>{two}</b> · 2014년 이후 +는 순매수, -는 순매도",
        ]
    if yields:
        prev_y, cur_y = yields
        lines.append(
            f"• JGB: 2년 {cur_y['jgb2']:.3f}% ({bp(cur_y['jgb2'], prev_y['jgb2']):+.1f}bp) / "
            f"10년 {cur_y['jgb10']:.3f}% ({bp(cur_y['jgb10'], prev_y['jgb10']):+.1f}bp) / "
            f"30년 {cur_y['jgb30']:.3f}% ({bp(cur_y['jgb30'], prev_y['jgb30']):+.1f}bp)"
        )
    for event in events:
        if event["kind"] == "jgb_auction":
            row = auctions[str(event["tenor"])]
            lines.append(
                f"• JGB {event['tenor']}년 입찰: BTC <b>{row['btc']:.3f}배</b> "
                f"(직전 대비 {row['btc_drop_pct']:+.1f}%) / 꼬리 {row['tail_bp']:.1f}bp"
            )
    if fima:
        fima_text = fmt_usd_bn(fima.level_bn_usd, quote) if quote else f"{fima.level_bn_usd:.2f}십억달러"
        change = "확인 불가" if fima.weekly_change_bn_usd is None else f"{fima.weekly_change_bn_usd:+.2f}십억달러"
        lines.append(f"• Fed 외국공식 레포: <b>{fima_text}</b> / 주간 {change} · H.4.1 {html.escape(fima.release_date)}")
    if market:
        lines += [
            f"• SOFR-IORB: <b>{market['sofr_iorb_bp']:+.1f}bp</b> / 직전 대비 {market['sofr_iorb_change_bp']:+.1f}bp",
            f"• UST 10년 {market['dgs10']:.3f}% ({market['dgs10_change_bp']:+.1f}bp) / 30년 {market['dgs30']:.3f}% ({market['dgs30_change_bp']:+.1f}bp)",
            f"• USD/JPY {market['usdjpy']:.2f} / 직전 대비 {market['usdjpy_change_pct']:+.2f}%",
        ]

    lines += [
        "",
        "<b>왜 이 조합을 보는가</b>",
        "• 일본의 미국채 보유액과 헤지펀드의 미국채 총 롱은 성격이 다릅니다. 이 알림은 ‘규모 비교’가 아니라 실제 자금 이동 경로를 추적합니다.",
        "• Fed 2026 분석의 대형 헤지펀드 미국채 롱 2.4조달러 중 현선물 베이시스 거래만 약 0.83조달러로, 레포·선물과 묶인 레버리지 포지션이 큽니다.",
        "• H.4.1 ‘외국공식 레포’는 일본 단독 사용액이 아니므로 <b>FIMA 사용 가능성 프록시</b>로만 표시합니다.",
        "",
        "<b>실패 경로·먼저 볼 지표</b>",
        "• 가장 현실적인 경로: BOJ 긴축 → 엔화 강세·JGB 단기금리 상승 → 일본 해외채 순매도 → 미국 장기금리 상승 → 레포/베이시스 포지션 축소.",
        "• 먼저 보이는 지표: 일본 해외 <b>중장기채</b> 순매도, JGB 2년 입찰 BTC/꼬리, SOFR-IORB, H.4.1 외국공식 레포.",
        "",
        "<b>원문</b>",
        f"• <a href=\"{MOF_WEEK}\">일본 재무성 해외증권투자 주간 CSV</a>",
        f"• <a href=\"{MOF_JGB_NEWS}\">일본 재무성 JGB 입찰</a>",
        f"• <a href=\"{FED_H41}\">Fed H.4.1</a> · <a href=\"{FED_FIMA}\">FIMA 설명</a>",
        f"• <a href=\"{FED_HF}\">Fed 헤지펀드 미국채 노출 분석</a>",
        "",
        f"조회 {now.strftime('%Y-%m-%d %H:%M:%S')} KST",
    ]
    ALERT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
