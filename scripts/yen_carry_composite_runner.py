#!/usr/bin/env python3
"""Operational wrapper for yen_carry_composite_watch.

CFTC migrated the Socrata dataset to API v3 in 2026. To avoid depending on an
app token or a deprecated /resource endpoint, this wrapper reads the official
CFTC Traders in Financial Futures current report page directly and derives the
previous week's leveraged-fund net position from the published change row.
It also normalizes MOF weekly date labels when the legacy CSV arrives with a
Shift-JIS separator decoded imperfectly by the HTTP server.

All monetary JPY amounts exposed in the Telegram body are paired with a KRW
conversion using the latest same-date Federal Reserve H.10 USD/KRW and USD/JPY
observations. If that conversion cannot be verified, the monetary alert is not
allowed to advance state or send.

The live composite lane also enforces two freshness rules already used by the
main global-rates lane: the U.S.-Japan 2Y spread is calculated only from the
same market date, and stale Yahoo five-minute USD/JPY observations are retained
for reference but excluded from current yen-carry signal classification.
"""
from __future__ import annotations

import datetime as dt
import html
import pathlib
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET

import yen_carry_composite_watch as base
from khs_source_fetch import fetch_text
from krw_fx import FRED_USDJPY, FRED_USDKRW, JpyKrwQuote, format_krw, latest_jpy_krw, yen_to_krw

CFTC_TFF_REPORT = "https://www.cftc.gov/dea/futures/financial_lf.htm"
KRW_FAILURE_PATH = pathlib.Path("out/yen_carry_krw_conversion_failed.txt")
MAX_LIVE_FX_AGE_SECONDS = 12 * 60

_original_parse_mof_week_csv = base.parse_mof_week_csv
_original_build_message = base.build_message
_original_classify = base.classify
_original_make_state = base.make_state
_original_fetch_move = base.fx.fetch_move
_original_fetch_jgb = base.rates.fetch_jgb
_original_fetch_ust_curve = base.rates.fetch_ust_curve
_target_rate_date: str | None = None
_last_fx_freshness = {"signal_eligible": False, "age_seconds": None, "latest_epoch": None}


def normalize_date(value: str | None) -> str | None:
    nums = [int(x) for x in re.findall(r"\d+", value or "")]
    if len(nums) >= 3 and nums[0] >= 2000:
        return f"{nums[0]:04d}-{nums[1]:02d}-{nums[2]:02d}"
    return None


def fetch_jgb_aligned():
    global _target_rate_date
    jgb2, jgb10 = _original_fetch_jgb()
    _target_rate_date = normalize_date(jgb2.date)
    return jgb2, jgb10


def fetch_ust_curve_aligned(data_key: str = "daily_treasury_yield_curve"):
    latest = _original_fetch_ust_curve(data_key)
    target = _target_rate_date
    latest_ust2 = latest.get("ust2")
    if not target or (latest_ust2 and normalize_date(latest_ust2.date) == target):
        return latest

    year = int(target[:4])
    params = urllib.parse.urlencode({"data": data_key, "field_tdr_date_value": str(year)})
    url = f"{base.rates.UST_XML_BASE}?{params}"
    root = ET.fromstring(base.rates.http_get(url))
    matched = None
    for entry in root.iter():
        if base.rates.localname(entry.tag) != "entry":
            continue
        props = next((node for node in entry.iter() if base.rates.localname(node.tag) == "properties"), None)
        if props is None:
            continue
        rec = {base.rates.localname(child.tag): (child.text or "").strip() for child in list(props)}
        raw_date = rec.get("NEW_DATE") or rec.get("QUOTE_DATE") or ""
        if normalize_date(raw_date) == target:
            matched = rec
            break
    if matched is None:
        raise RuntimeError(f"U.S. Treasury 2Y same-date observation unavailable for JGB date {target}")

    out = {}
    for key, name in (("BC_2YEAR", "ust2"), ("BC_10YEAR", "ust10"), ("BC_30YEAR", "ust30")):
        value = base.rates.to_float(matched.get(key))
        if value is not None:
            out[name] = base.rates.Point(name, target, value, url)
    if not {"ust2", "ust10", "ust30"}.issubset(out):
        raise RuntimeError(f"U.S. Treasury same-date curve incomplete for {target}")
    return out


def fetch_move_freshness():
    global _last_fx_freshness
    move = _original_fetch_move()
    age = dt.datetime.now(dt.timezone.utc).timestamp() - float(move.latest_epoch)
    eligible = -120 <= age <= MAX_LIVE_FX_AGE_SECONDS
    _last_fx_freshness = {
        "signal_eligible": eligible,
        "age_seconds": max(0.0, age),
        "latest_epoch": float(move.latest_epoch),
    }
    return move


def classify_with_freshness(*, move, fx_vol, jgb2, spread, previous_jgb2, previous_spread, cftc, mof, policy):
    if _last_fx_freshness.get("signal_eligible"):
        return _original_classify(
            move=move,
            fx_vol=fx_vol,
            jgb2=jgb2,
            spread=spread,
            previous_jgb2=previous_jgb2,
            previous_spread=previous_spread,
            cftc=cftc,
            mof=mof,
            policy=policy,
        )

    jgb2_change_bp = None if previous_jgb2 is None else (jgb2 - previous_jgb2) * 100.0
    spread_change_bp = None if previous_spread is None else (spread - previous_spread) * 100.0
    short_rate_up = bool(jgb2_change_bp is not None and jgb2_change_bp >= base.JGB2_CHANGE_BP)
    spread_narrow = bool(spread <= base.SPREAD_NARROW_LEVEL or (spread_change_bp is not None and spread_change_bp <= -base.SPREAD_CHANGE_BP))
    spread_wide = bool(spread > base.SPREAD_NARROW_LEVEL and not spread_narrow)
    spread_widening = bool(spread_change_bp is not None and spread_change_bp >= base.SPREAD_CHANGE_BP)
    leveraged_net_short = bool(cftc is not None and cftc.net_short > 0)
    outward_buying = bool(mof is not None and mof.outward_buying)
    outward_accelerating = bool(mof is not None and mof.outward_accelerating)
    policy_recent = bool(policy and policy.get("recent") and policy.get("further_joint_intervention_signal"))

    unwind_evidence = {
        "일본 단기금리 상승": short_rate_up,
        "미·일 2년 금리차 축소": spread_narrow,
        "USD/JPY 급락·엔화 급등": False,
        "FX 실현변동성 상승": False,
        "레버리지 펀드 엔화 순숏": leveraged_net_short,
        "최근 공식 공동개입·추가개입 경고": policy_recent,
    }
    if sum(bool(v) for v in unwind_evidence.values()) >= 3 and (spread_narrow or short_rate_up):
        unwind_level, unwind_label = 1, "엔캐리 청산 구조적 경계"
    else:
        unwind_level, unwind_label = 0, "엔캐리 청산 미확인"

    rebuild_evidence = {
        "USD/JPY 상승·엔화 재약세": False,
        "USD/JPY 완만한 상승 방향": False,
        "미·일 2년 금리차 여전히 넓음": spread_wide,
        "미·일 2년 금리차 재확대": spread_widening,
        "일본 거주자 해외주식·장기채 순매수": outward_buying,
        "최근 2주 해외매수 가속": outward_accelerating,
        "레버리지 엔화 숏 축소에도 USD/JPY 상승": False,
        "FX 변동성 비상승": False,
    }
    if outward_buying and spread_wide and outward_accelerating:
        rebuild_level, rebuild_label = 2, "엔화 재약세·캐리 재구축 압력 강화"
    elif sum(bool(v) for v in rebuild_evidence.values()) >= 4 and outward_buying:
        rebuild_level, rebuild_label = 1, "엔화 재약세·캐리 재구축 경계"
    else:
        rebuild_level, rebuild_label = 0, "엔화 재약세·캐리 재구축 미확인"

    evidence = {"unwind::" + k: v for k, v in unwind_evidence.items()}
    evidence.update({"rebuild::" + k: v for k, v in rebuild_evidence.items()})
    evidence["meta::USD/JPY 현재 신호 사용 가능"] = False
    return base.CompositeVerdict(unwind_level, unwind_label, rebuild_level, rebuild_label, False, evidence)


def make_state_with_freshness(*args, **kwargs):
    state = _original_make_state(*args, **kwargs)
    state["fx_signal_eligible"] = bool(_last_fx_freshness.get("signal_eligible"))
    state["fx_age_seconds"] = _last_fx_freshness.get("age_seconds")
    return state


def normalize_mof_week_label(value: str) -> str:
    nums = [int(x) for x in re.findall(r"\d+", value or "")]
    if len(nums) >= 5 and nums[0] >= 2000:
        year, m1, d1, m2, d2 = nums[:5]
        return f"{year:04d}-{m1:02d}-{d1:02d}~{m2:02d}-{d2:02d}"
    return (value or "").strip()


def parse_mof_week_csv(text: str) -> base.MofOutwardFlow:
    result = _original_parse_mof_week_csv(text)
    return base.MofOutwardFlow(
        latest_week=normalize_mof_week_label(result.latest_week),
        previous_week=normalize_mof_week_label(result.previous_week),
        latest_two_week_trillion_yen=result.latest_two_week_trillion_yen,
        previous_two_week_trillion_yen=result.previous_two_week_trillion_yen,
        outward_buying=result.outward_buying,
        outward_accelerating=result.outward_accelerating,
    )


def _ints(text: str) -> list[int]:
    return [int(token.replace(",", "")) for token in re.findall(r"[+-]?\d[\d,]*", text)]


def _parse_date(value: str) -> dt.date:
    return dt.datetime.strptime(value.strip(), "%B %d, %Y").date()


def parse_cftc_tff_html(text: str) -> base.CftcPosition:
    plain = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    plain = plain.replace("\xa0", " ")
    start = re.search(
        r"JAPANESE\s+YEN\s*-\s*CHICAGO\s+MERCANTILE\s+EXCHANGE.*?CFTC\s+Code\s*#?097741",
        plain,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not start:
        raise RuntimeError("CFTC TFF Japanese Yen block not found")
    block = plain[start.start() : start.start() + 7000]

    oi_match = re.search(r"Open\s+Interest\s+is\s*([\d,]+)", block, flags=re.IGNORECASE)
    positions_match = re.search(
        r"Positions\s+((?:[\s,+-]*\d[\d,]*){14})\s+Changes\s+from:",
        block,
        flags=re.IGNORECASE | re.DOTALL,
    )
    changes_match = re.search(
        r"Changes\s+from:\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})\s+Total\s+Change\s+is:\s*[+-]?[\d,]+\s+((?:[\s,+-]*\d[\d,]*){14})\s+Percent",
        block,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not oi_match or not positions_match or not changes_match:
        raise RuntimeError("CFTC TFF Japanese Yen positions/change fields not found")

    positions = _ints(positions_match.group(1))
    changes = _ints(changes_match.group(2))
    if len(positions) != 14 or len(changes) != 14:
        raise RuntimeError(f"CFTC TFF Japanese Yen field count mismatch: positions={len(positions)} changes={len(changes)}")

    leveraged_long = positions[6]
    leveraged_short = positions[7]
    previous_long = leveraged_long - changes[6]
    previous_short = leveraged_short - changes[7]
    net = leveraged_long - leveraged_short
    net_short = max(leveraged_short - leveraged_long, 0)
    previous_net_short = max(previous_short - previous_long, 0)
    previous_date = _parse_date(changes_match.group(1))
    report_date = previous_date + dt.timedelta(days=7)
    open_interest = int(oi_match.group(1).replace(",", ""))

    return base.CftcPosition(
        report_date=report_date.isoformat(),
        open_interest=open_interest,
        leveraged_long=leveraged_long,
        leveraged_short=leveraged_short,
        net=net,
        net_short=net_short,
        net_short_pct_oi=(net_short / open_interest * 100.0) if open_interest else 0.0,
        previous_report_date=previous_date.isoformat(),
        previous_net_short=previous_net_short,
        short_covering=net_short < previous_net_short,
    )


def fetch_cftc(now: dt.datetime) -> base.CftcPosition:
    text, error = fetch_text(
        CFTC_TFF_REPORT,
        base.USER_AGENT,
        timeout=20,
        attempts=2,
        accept="text/html,text/plain,*/*",
    )
    if error or not text:
        raise RuntimeError(error or "empty CFTC TFF report")
    return parse_cftc_tff_html(text)


def enrich_krw_lines(body: str, mof: base.MofOutwardFlow | None, quote: JpyKrwQuote) -> str:
    if mof is None:
        return body

    latest_won = yen_to_krw(mof.latest_two_week_trillion_yen * 1_000_000_000_000.0, quote)
    prior_won = yen_to_krw(mof.previous_two_week_trillion_yen * 1_000_000_000_000.0, quote)
    latest_sign = "+" if mof.latest_two_week_trillion_yen >= 0 else ""
    prior_sign = "+" if mof.previous_two_week_trillion_yen >= 0 else ""
    replacement = (
        f"- 일본 거주자 해외주식+장기채: 최근 2주 {latest_sign}{mof.latest_two_week_trillion_yen:.2f}조엔 "
        f"(약 {format_krw(latest_won)}) / 직전 2주 {prior_sign}{mof.previous_two_week_trillion_yen:.2f}조엔 "
        f"(약 {format_krw(prior_won)}) (순매수 +)"
    )

    lines = body.splitlines()
    converted = False
    output: list[str] = []
    for line in lines:
        if line.startswith("- 일본 거주자 해외주식+장기채:"):
            output.append(replacement)
            converted = True
        else:
            output.append(line)
    if not converted:
        raise RuntimeError("MOF outward-flow monetary line missing; refusing unconverted alert")

    basis = (
        f"- 원화 환산 기준: 1엔={quote.krw_per_yen:.4f}원 / 100엔={quote.krw_per_100_yen:,.2f}원 "
        f"(FRED H.10 동일 기준일 {quote.date}, USD/KRW {quote.usdkrw:,.2f} ÷ USD/JPY {quote.usdjpy:.2f})"
    )
    try:
        source_index = output.index("출처")
    except ValueError:
        source_index = len(output)
    output[source_index:source_index] = [basis, ""]
    if source_index < len(output):
        output.extend([
            f"- FRED USD/KRW: {FRED_USDKRW}",
            f"- FRED USD/JPY: {FRED_USDJPY}",
        ])
    return "\n".join(output)


def build_message(*args, **kwargs):
    title, body, payload = _original_build_message(*args, **kwargs)
    if not _last_fx_freshness.get("signal_eligible"):
        age = _last_fx_freshness.get("age_seconds")
        age_text = f"{float(age)/60:.0f}분 전" if age is not None else "시각 확인 불가"
        lines = []
        for line in body.splitlines():
            if line.startswith("- USD/JPY "):
                lines.append("- USD/JPY 최근 관측(현재 신호 제외): " + line[len("- USD/JPY "):])
            else:
                lines.append(line)
        insert_at = 1 if lines else 0
        lines[insert_at:insert_at] = [f"- USD/JPY 현재신호: 보류 ({age_text})"]
        body = "\n".join(lines)
    mof = kwargs.get("mof")
    if mof is not None:
        try:
            quote = latest_jpy_krw()
            body = enrich_krw_lines(body, mof, quote)
        except Exception as exc:
            KRW_FAILURE_PATH.parent.mkdir(parents=True, exist_ok=True)
            KRW_FAILURE_PATH.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
            raise
        payload["krw_conversion"] = {
            "required": True,
            "date": quote.date,
            "usdkrw": quote.usdkrw,
            "usdjpy": quote.usdjpy,
            "krw_per_yen": quote.krw_per_yen,
            "method": "FRED H.10 same-date DEXKOUS / DEXJPUS",
        }
    payload["fx_freshness"] = dict(_last_fx_freshness)
    return title, body, payload


def install_source_overrides() -> None:
    base.CFTC_TFF_API = CFTC_TFF_REPORT
    base.parse_mof_week_csv = parse_mof_week_csv
    base.fetch_cftc = fetch_cftc
    base.build_message = build_message


def install_live_guards() -> None:
    base.classify = classify_with_freshness
    base.make_state = make_state_with_freshness
    base.fx.fetch_move = fetch_move_freshness
    base.rates.fetch_jgb = fetch_jgb_aligned
    base.rates.fetch_ust_curve = fetch_ust_curve_aligned


install_source_overrides()


def main() -> int:
    if "--finalize" in sys.argv and KRW_FAILURE_PATH.exists():
        print("KRW conversion failed; yen-carry state intentionally not advanced")
        return 1
    install_live_guards()
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
