#!/usr/bin/env python3
"""Regime / capital-flow upgrade for the global-rates + yen-carry Telegram watch.

Adds three things the level-only watcher cannot answer well:
1) Why JGB yields are rising: BOJ-normalisation vs fiscal-risk-premium vs global-rate synchronisation.
2) Whether 3% JGB yields are actually attracting demand or coinciding with auction stress.
3) Whether Japanese residents are reducing overseas equity/long-term bond purchases.

Official sources only for the structural data. Live USD/JPY is supplied by the existing
query1/query2 cross-checked 5-minute guard. The module never labels a single 3% print
as a carry unwind and never converts an FX amount without a verified JPY/KRW rate.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
DATA = ROOT / "data"
OUT.mkdir(parents=True, exist_ok=True)
DATA.mkdir(parents=True, exist_ok=True)

STATE = DATA / "global_rates_regime_flow_state.json"
PENDING = OUT / "global_rates_regime_flow_pending.json"
RESULT = OUT / "global_rates_regime_flow.json"
EVENT = OUT / "global_rates_regime_flow_event.json"
BLOCK = OUT / "global_rates_regime_flow_block.md"

MOF_JGB = "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv"
MOF_WEEK = "https://www.mof.go.jp/policy/international_policy/reference/itn_transactions_in_securities/week.csv"
MOF_WEEK_INDEX = "https://www.mof.go.jp/english/policy/international_policy/reference/itn_transactions_in_securities/index.htm"
MOF_WEEK_SCHEDULE = "https://www.mof.go.jp/english/policy/international_policy/reference/itn_transactions_in_securities/schedule.htm"
UST_XML_BASE = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
UA = "khs-watch-global-rates-regime-flow/1.0"


def get_bytes(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Cache-Control": "no-cache", "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def load(path: pathlib.Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save(path: pathlib.Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fnum(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).replace(",", "").replace("*", "").replace("%", "").strip()
    if not text or text in {"-", "."}:
        return None
    try:
        return float(text)
    except Exception:
        return None


def norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def bp(new: float | None, old: float | None) -> float | None:
    if new is None or old is None:
        return None
    return (new - old) * 100.0


def decode_csv(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp932", "shift_jis"):
        try:
            text = raw.decode(encoding)
            if "�" not in text:
                return text
        except Exception:
            pass
    return raw.decode("utf-8", errors="replace")


def fetch_jgb_latest_two() -> tuple[dict[str, Any], dict[str, Any]]:
    rows = list(csv.reader(io.StringIO(decode_csv(get_bytes(MOF_JGB)))))
    hi = next((i for i, row in enumerate(rows[:12]) if any(norm(cell) == "date" for cell in row)), None)
    if hi is None:
        raise RuntimeError("MOF JGB header not found")
    header = [cell.strip() for cell in rows[hi]]
    normalized = [norm(cell) for cell in header]

    def col(*candidates: str) -> int:
        wanted = {norm(c) for c in candidates}
        for idx, key in enumerate(normalized):
            if key in wanted:
                return idx
        raise RuntimeError(f"MOF JGB column missing: {candidates}; header={header}")

    idx = {
        "date": col("Date"),
        "jgb2": col("2", "2Y", "2-year", "2 year"),
        "jgb5": col("5", "5Y", "5-year", "5 year"),
        "jgb10": col("10", "10Y", "10-year", "10 year"),
        "jgb30": col("30", "30Y", "30-year", "30 year"),
    }
    good: list[dict[str, Any]] = []
    for row in rows[hi + 1 :]:
        if not row or len(row) <= max(idx.values()):
            continue
        item = {"date": row[idx["date"]].strip()}
        for key in ("jgb2", "jgb5", "jgb10", "jgb30"):
            item[key] = fnum(row[idx[key]])
        if item["date"] and all(item[k] is not None for k in ("jgb2", "jgb5", "jgb10", "jgb30")):
            good.append(item)
    if len(good) < 2:
        raise RuntimeError("MOF JGB requires two complete observations")
    return good[-2], good[-1]


def localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def fetch_ust10_latest_two() -> tuple[dict[str, Any], dict[str, Any]]:
    year = dt.datetime.now(KST).year
    url = UST_XML_BASE + "?" + urllib.parse.urlencode({"data": "daily_treasury_yield_curve", "field_tdr_date_value": str(year)})
    root = ET.fromstring(get_bytes(url))
    rows: list[dict[str, Any]] = []
    for entry in root.iter():
        if localname(entry.tag) != "entry":
            continue
        props = next((node for node in entry.iter() if localname(node.tag) == "properties"), None)
        if props is None:
            continue
        rec = {localname(child.tag): (child.text or "").strip() for child in list(props)}
        raw_date = rec.get("NEW_DATE") or rec.get("QUOTE_DATE") or ""
        value = fnum(rec.get("BC_10YEAR"))
        if raw_date and value is not None:
            rows.append({"date": raw_date[:10], "ust10": value, "url": url})
    rows.sort(key=lambda row: row["date"])
    if len(rows) < 2:
        raise RuntimeError("U.S. Treasury 10Y requires two observations")
    return rows[-2], rows[-1]


def dateish(cell: str) -> bool:
    value = (cell or "").strip()
    return bool(
        re.search(r"令和\s*\d+年\s*\d+月\s*\d+日", value)
        or re.search(r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b", value, re.I)
        or re.search(r"\b20\d{2}[/-]\d{1,2}[/-]\d{1,2}\b", value)
    )


def fetch_weekly_outward_flows() -> list[dict[str, Any]]:
    """Parse the resident outward-investment table in the official weekly CSV.

    Expected numeric order after the period column follows the MOF press-release table:
    equity acquisition/disposition/net, long-term debt acquisition/disposition/net,
    subtotal net, short-term acquisition/disposition/net, total net. Unit: 100m yen.
    """
    rows = list(csv.reader(io.StringIO(decode_csv(get_bytes(MOF_WEEK)))))
    section = 0
    parsed: list[dict[str, Any]] = []
    for row in rows:
        joined = " ".join(row)
        low = joined.lower()
        if "portfolio investment assets" in low or "対外証券投資" in joined:
            section = 1
            continue
        if "portfolio investment liabilities" in low or "対内証券投資" in joined:
            section = 2
            continue
        if section == 2:
            continue
        if not row or not dateish(row[0]):
            continue
        nums = [fnum(cell) for cell in row[1:]]
        nums = [value for value in nums if value is not None]
        if len(nums) < 11:
            continue
        parsed.append({
            "period": re.sub(r"\s+", " ", row[0]).strip(),
            "equity_net_100m_yen": nums[2],
            "long_term_net_100m_yen": nums[5],
            "equity_long_subtotal_100m_yen": nums[6],
            "short_term_net_100m_yen": nums[9],
            "total_net_100m_yen": nums[10],
        })
    if len(parsed) < 2:
        raise RuntimeError(f"MOF weekly CSV parse failed: parsed_rows={len(parsed)}")
    return parsed


def fmt_bp(value: float | None) -> str:
    return "확인 불가" if value is None else f"{value:+.1f}bp"


def fmt_yen_krw_from_100m(value: float | None, yenkrw: float | None) -> str:
    if value is None:
        return "확인 불가"
    yen = value * 100_000_000.0
    sign = "+" if yen >= 0 else "-"
    trillion = abs(yen) / 1e12
    if yenkrw is None:
        return f"{sign}{trillion:.2f}조엔 / 원화 환산 확인 불가"
    krw = abs(yen) * yenkrw
    return f"{sign}{trillion:.2f}조엔(약 {sign}{krw / 1e12:.1f}조원)"


def classify_regime(prev_jgb: dict[str, Any], cur_jgb: dict[str, Any], prev_ust: dict[str, Any], cur_ust: dict[str, Any], live_fx: dict[str, Any]) -> dict[str, Any]:
    d2 = bp(cur_jgb["jgb2"], prev_jgb["jgb2"])
    d5 = bp(cur_jgb["jgb5"], prev_jgb["jgb5"])
    d10 = bp(cur_jgb["jgb10"], prev_jgb["jgb10"])
    d30 = bp(cur_jgb["jgb30"], prev_jgb["jgb30"])
    u10 = bp(cur_ust["ust10"], prev_ust["ust10"])
    fx_change = fnum(live_fx.get("live_fx_change_pct")) if live_fx else None

    policy = sum([bool(d2 is not None and d2 >= 5), bool(d5 is not None and d5 >= 5), bool(fx_change is not None and fx_change <= -0.50)])
    fiscal = sum([
        bool(d30 is not None and d10 is not None and d30 - d10 >= 5),
        bool(d30 is not None and d30 >= 8),
        bool(fx_change is not None and fx_change >= 0.30),
    ])
    global_sync = sum([bool(d10 is not None and d10 >= 5), bool(u10 is not None and u10 >= 5)])

    scores = {"BOJ 정상화형": policy, "재정 위험 프리미엄형": fiscal, "글로벌 금리 동조형": global_sync}
    top = max(scores.values())
    winners = [name for name, score in scores.items() if score == top and score >= 2]
    if len(winners) == 1:
        label = winners[0]
    elif len(winners) > 1:
        label = "혼재형(" + " + ".join(winners) + ")"
    else:
        label = "원인 미확정·혼재"

    return {
        "label": label,
        "scores": scores,
        "jgb_date": cur_jgb["date"],
        "ust_date": cur_ust["date"],
        "jgb2": cur_jgb["jgb2"],
        "jgb5": cur_jgb["jgb5"],
        "jgb10": cur_jgb["jgb10"],
        "jgb30": cur_jgb["jgb30"],
        "d2_bp": d2,
        "d5_bp": d5,
        "d10_bp": d10,
        "d30_bp": d30,
        "ust10": cur_ust["ust10"],
        "ust10_change_bp": u10,
        "live_usdjpy": fnum(live_fx.get("live_fx_price")) if live_fx else None,
        "live_usdjpy_change_pct": fx_change,
    }


def absorption_signal(regime: dict[str, Any], structural: dict[str, Any]) -> dict[str, Any]:
    auction = structural.get("auction") or {}
    if float(regime.get("jgb10") or 0) < 3.0 or str(auction.get("tenor")) != "10-Year":
        return {"label": "해당 없음", "key": "none"}
    btc = fnum(auction.get("bid_to_cover"))
    tail = fnum(auction.get("tail_bp"))
    grade = str(auction.get("grade") or "")
    if btc is not None and tail is not None and btc >= 3.0 and tail <= 2.0:
        label = "3%대에서도 입찰 흡수력 양호"
        key = f"good:{auction.get('auction_date')}"
    elif grade in {"수요 약함", "수요 매우 약함"} or (btc is not None and btc <= 2.8) or (tail is not None and tail >= 3.0):
        label = "3%대 + 입찰 수요 약화 동반"
        key = f"weak:{auction.get('auction_date')}"
    else:
        label = "3%대이나 입찰수요 중립"
        key = f"neutral:{auction.get('auction_date')}"
    return {
        "label": label,
        "key": key,
        "auction_date": auction.get("auction_date"),
        "bid_to_cover": btc,
        "tail_bp": tail,
        "grade": grade,
    }


def flow_signal(flows: list[dict[str, Any]], yenkrw: float | None) -> dict[str, Any]:
    latest = flows[-1]
    previous = flows[-2]
    latest_sub = fnum(latest.get("equity_long_subtotal_100m_yen"))
    prev_sub = fnum(previous.get("equity_long_subtotal_100m_yen"))
    delta = None if latest_sub is None or prev_sub is None else latest_sub - prev_sub
    two_week = None
    prior_two = None
    if len(flows) >= 4:
        vals = [fnum(row.get("equity_long_subtotal_100m_yen")) for row in flows[-4:]]
        if all(v is not None for v in vals):
            prior_two = vals[0] + vals[1]
            two_week = vals[2] + vals[3]
    material = bool(
        (latest_sub is not None and latest_sub <= 0)
        or (latest_sub is not None and latest_sub >= 10_000)
        or (delta is not None and abs(delta) >= 10_000)
        or (two_week is not None and prior_two is not None and abs(two_week - prior_two) >= 20_000)
    )
    if latest_sub is None:
        label = "확인 불가"
    elif latest_sub < 0:
        label = "일본 거주자 해외 주식+중장기채 순매도 — 환류 방향 확인"
    elif latest_sub >= 10_000:
        label = "일본 거주자 해외 주식+중장기채 대규모 순매수 지속"
    else:
        label = "해외 주식+중장기채 수급 중립"
    return {
        "period": latest.get("period"),
        "label": label,
        "material": material,
        "equity_net_100m_yen": latest.get("equity_net_100m_yen"),
        "long_term_net_100m_yen": latest.get("long_term_net_100m_yen"),
        "subtotal_100m_yen": latest_sub,
        "subtotal_change_100m_yen": delta,
        "two_week_100m_yen": two_week,
        "prior_two_week_100m_yen": prior_two,
        "subtotal_display": fmt_yen_krw_from_100m(latest_sub, yenkrw),
        "long_term_display": fmt_yen_krw_from_100m(fnum(latest.get("long_term_net_100m_yen")), yenkrw),
        "two_week_display": fmt_yen_krw_from_100m(two_week, yenkrw),
        "prior_two_week_display": fmt_yen_krw_from_100m(prior_two, yenkrw),
    }


def build_block(result: dict[str, Any]) -> str:
    regime = result.get("regime") or {}
    absorption = result.get("absorption") or {}
    flow = result.get("flow") or {}
    fx = result.get("krw_fx") or {}
    lines = ["②-2 JGB 3% 체제·실제 자금이동"]
    lines.append(
        f"- JGB 상승 원인: {regime.get('label','확인 불가')} / "
        f"2Y {regime.get('jgb2','?')}%({fmt_bp(regime.get('d2_bp'))}) · "
        f"5Y {regime.get('jgb5','?')}%({fmt_bp(regime.get('d5_bp'))}) · "
        f"10Y {regime.get('jgb10','?')}%({fmt_bp(regime.get('d10_bp'))}) · "
        f"30Y {regime.get('jgb30','?')}%({fmt_bp(regime.get('d30_bp'))})."
    )
    if regime.get("ust10") is not None:
        lines.append(f"- 글로벌 동조 검산: 미국 10Y {regime['ust10']:.3f}%({fmt_bp(regime.get('ust10_change_bp'))}) / JGB {regime.get('jgb_date')} · UST {regime.get('ust_date')} 기준.")
    if regime.get("live_usdjpy") is not None:
        lines.append(f"- 환율 검산: USD/JPY {regime['live_usdjpy']:.3f} / 기준변화 {regime.get('live_usdjpy_change_pct',0):+.2f}% — 현재 5분 교차확인값.")
    lines.append(
        f"- 3% 입찰 흡수력: {absorption.get('label','확인 불가')}"
        + (f" / 응찰배율 {absorption.get('bid_to_cover'):.2f}배 · 꼬리 {absorption.get('tail_bp'):.1f}bp." if absorption.get('bid_to_cover') is not None and absorption.get('tail_bp') is not None else ".")
    )
    if flow:
        lines.append(f"- 일본 거주자 해외 주식+중장기채: {flow.get('period','')} {flow.get('subtotal_display','확인 불가')} — {flow.get('label','')}.")
        lines.append(f"- 해외 중장기채만: {flow.get('long_term_display','확인 불가')} / 최근 2주 {flow.get('two_week_display','확인 불가')} / 직전 2주 {flow.get('prior_two_week_display','확인 불가')}.")
    if fx.get("date"):
        lines.append(f"- 원화 환산: 1엔={fx.get('yenkrw'):.4f}원 / FRED 동일 기준일 {fx.get('date')}; 서로 다른 기준일 환율 혼용 금지.")
    lines += [
        "- 정확한 의미: JGB 3% 하나로 재정위기·엔캐리 청산을 단정하지 않음. ① 단기·중기 금리와 엔화가 같이 움직이는지 ② 30년물이 더 가파르게 오르는지 ③ 미국 장기금리와 동조하는지 ④ 실제 일본 해외채권 매수가 줄었는지를 함께 판정.",
        "- 조기경보: 3%대에서 입찰 꼬리 확대·응찰배율 하락 + 일본 거주자의 해외 중장기채 순매도 전환 + USD/JPY 급락이 겹치면 캐리 청산 위험을 한 단계 높임.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    now = dt.datetime.now(KST)
    state = load(STATE, {})
    first = not bool(state)
    errors: list[str] = []

    try:
        prev_jgb, cur_jgb = fetch_jgb_latest_two()
    except Exception as exc:
        prev_jgb = cur_jgb = None
        errors.append(f"JGB: {type(exc).__name__}: {exc}")
    try:
        prev_ust, cur_ust = fetch_ust10_latest_two()
    except Exception as exc:
        prev_ust = cur_ust = None
        errors.append(f"UST10: {type(exc).__name__}: {exc}")

    freshness = load(OUT / "global_rates_freshness.json", {})
    structural = load(OUT / "global_rates_structural.json", {})
    fx = structural.get("fx") or {}
    yenkrw = fnum(fx.get("yenkrw"))

    try:
        flows = fetch_weekly_outward_flows()
    except Exception as exc:
        flows = []
        errors.append(f"MOF weekly flow: {type(exc).__name__}: {exc}")

    regime = classify_regime(prev_jgb, cur_jgb, prev_ust, cur_ust, freshness) if all((prev_jgb, cur_jgb, prev_ust, cur_ust)) else {"label": "확인 불가"}
    absorption = absorption_signal(regime, structural) if regime.get("jgb10") is not None else {"label": "확인 불가", "key": "unknown"}
    flow = flow_signal(flows, yenkrw) if flows else {}

    result = {
        "checked_at_kst": now.isoformat(timespec="seconds"),
        "regime": regime,
        "absorption": absorption,
        "flow": flow,
        "krw_fx": fx,
        "errors": errors,
        "sources": {"jgb": MOF_JGB, "weekly_flow": MOF_WEEK_INDEX, "weekly_schedule": MOF_WEEK_SCHEDULE},
    }
    save(RESULT, result)
    BLOCK.write_text(build_block(result), encoding="utf-8")

    events: list[dict[str, Any]] = []
    if not first:
        old_regime = state.get("regime_label")
        new_regime = regime.get("label")
        if new_regime and new_regime != "확인 불가" and new_regime != old_regime and float(regime.get("jgb10") or 0) >= 3.0:
            events.append({"type": "jgb_regime_change", "severity": 1, "summary": f"JGB 3%대 원인 판정 변화: {old_regime} → {new_regime}"})

        old_abs = state.get("absorption_key")
        new_abs = absorption.get("key")
        if new_abs and new_abs != "none" and new_abs != old_abs:
            severity = 2 if str(new_abs).startswith("weak:") else 1
            events.append({"type": "jgb_3pct_absorption", "severity": severity, "summary": absorption.get("label")})

        old_period = state.get("flow_period")
        if flow and flow.get("period") and flow.get("period") != old_period and flow.get("material"):
            events.append({"type": "japan_outward_flow", "severity": 2 if (flow.get("subtotal_100m_yen") or 0) <= 0 else 1, "summary": flow.get("label")})

    next_state = {
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "regime_label": regime.get("label"),
        "jgb_date": regime.get("jgb_date"),
        "absorption_key": absorption.get("key"),
        "flow_period": flow.get("period"),
        "flow_subtotal_100m_yen": flow.get("subtotal_100m_yen"),
    }
    save(PENDING, next_state)
    if events:
        save(EVENT, {"checked_at_kst": result["checked_at_kst"], "events": events})
    elif EVENT.exists():
        EVENT.unlink()

    print(json.dumps({"events": len(events), "regime": regime.get("label"), "absorption": absorption.get("label"), "flow": flow.get("label"), "errors": errors}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
