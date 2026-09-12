#!/usr/bin/env python3
"""Add an ex-post real-policy-rate regime layer to the live yen-carry composite alert.

This is a structural overlay, not a fast FX trigger. Existing USD/JPY, U.S.-Japan
2Y spread, volatility and positioning logic remain intact. The overlay adds official
Fed/BOJ policy rates, headline CPI, the U.S.-Japan ex-post real-policy-rate gap,
relative policy-rate changes, and agreement/conflict with the market 2Y spread.

Real-rate information alone can create at most a yellow structural alert. It never
promotes the active unwind alert to orange/red without existing market confirmation.
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import io
import json
import pathlib
import re
from dataclasses import asdict, dataclass
from zoneinfo import ZoneInfo

from khs_source_fetch import fetch_text

KST = ZoneInfo("Asia/Seoul")
ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "out"

STATE_PATH = DATA / "yen_carry_composite_state.json"
PENDING_PATH = OUT / "yen_carry_composite_pending_state.json"
ALERT_TITLE = OUT / "yen_carry_composite_alert_title.txt"
ALERT_BODY = OUT / "yen_carry_composite_alert.md"
ALERT_JSON = OUT / "yen_carry_composite_alert.json"
CONTEXT_JSON = OUT / "yen_carry_real_rate_context.json"
CONTEXT_MD = OUT / "yen_carry_real_rate_context.md"

FED_UPPER_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFEDTARU"
FED_LOWER_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFEDTARL"
FED_SOURCE_URL = "https://fred.stlouisfed.org/graph/?id=DFEDTARU,DFEDTARL"
BLS_CPI_API = "https://api.bls.gov/publicAPI/v2/timeseries/data/CUUR0000SA0"
BOJ_HOME = "https://www.boj.or.jp/en/"
JP_CPI_JP_URL = "https://www.stat.go.jp/data/cpi/sokuhou/tsuki/index-z.htm"
JP_CPI_EN_HOME = "https://www.stat.go.jp/english/"
JP_CPI_SOURCE_URL = "https://www.stat.go.jp/english/data/cpi/"
USER_AGENT = "Mozilla/5.0 khs-yen-carry-real-rate/1.3"

REAL_GAP_ALERT_PP = 0.25
POLICY_GAP_ALERT_PP = 0.25
REAL_DIRECTION_PP = 0.10
MARKET_DIRECTION_BP = 10.0
STRUCTURAL_LEVEL_BAND_PP = 0.50


@dataclass(frozen=True)
class RealRateInputs:
    fed_lower: float
    fed_upper: float
    fed_midpoint: float
    fed_observation_date: str
    us_cpi_yoy: float
    us_cpi_period: str
    boj_policy_rate: float
    boj_effective_date: str | None
    jp_cpi_yoy: float
    jp_cpi_period: str


@dataclass(frozen=True)
class RealRateMetrics:
    us_real_policy_rate: float
    jp_real_policy_rate: float
    us_jp_real_gap: float
    nominal_policy_gap: float
    real_gap_change_pp: float | None
    policy_gap_change_pp: float | None
    us_jp_2y_spread_change_bp: float | None
    real_rate_direction: str
    market_rate_direction: str
    signal_alignment: str
    structural_bias: str
    official_event_changed: bool
    changed_sources: tuple[str, ...]


def load_json(path: pathlib.Path, default):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, type(default)) else default
    except Exception:
        return default


def write_json(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def plain_html(text: str) -> str:
    value = re.sub(r"<script\b.*?</script>", " ", text or "", flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<style\b.*?</style>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    value = html.unescape(re.sub(r"<[^>]+>", " ", value))
    return " ".join(value.replace("\xa0", " ").split())


def parse_fred_latest_csv(text: str) -> tuple[str, float]:
    rows = list(csv.reader(io.StringIO((text or "").strip())))
    if len(rows) < 2:
        raise RuntimeError("FRED target-rate CSV has no observations")
    latest: tuple[str, float] | None = None
    for row in rows[1:]:
        if len(row) < 2:
            continue
        date = row[0].strip()
        try:
            value = float(row[1])
        except (TypeError, ValueError):
            continue
        latest = (date, value)
    if latest is None:
        raise RuntimeError("FRED target-rate CSV has no numeric observation")
    return latest


def parse_bls_cpi_api(text: str) -> tuple[str, float]:
    payload = json.loads(text)
    if payload.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(f"BLS API request failed: {payload.get('message')}")
    series = (((payload.get("Results") or {}).get("series")) or [])
    if not series:
        raise RuntimeError("BLS CPI series missing")
    rows: dict[tuple[int, int], float] = {}
    for item in series[0].get("data") or []:
        period = str(item.get("period") or "")
        if not re.fullmatch(r"M(?:0[1-9]|1[0-2])", period):
            continue
        try:
            year = int(item["year"])
            month = int(period[1:])
            value = float(item["value"])
        except (KeyError, TypeError, ValueError):
            continue
        rows[(year, month)] = value
    if not rows:
        raise RuntimeError("BLS CPI monthly observations missing")
    year, month = max(rows)
    current = rows[(year, month)]
    prior = rows.get((year - 1, month))
    if prior is None or prior <= 0:
        raise RuntimeError("BLS CPI year-ago observation missing")
    return f"{year:04d}-{month:02d}", (current / prior - 1.0) * 100.0


def parse_boj_policy_home(text: str) -> tuple[float, str | None]:
    plain = plain_html(text)
    match = re.search(
        r"Guideline\s+The Bank will encourage the uncollateralized overnight call rate to remain at around\s*([0-9.]+)\s*percent",
        plain,
        flags=re.IGNORECASE,
    )
    if not match:
        raise RuntimeError("BOJ current policy guideline not found")
    rate = float(match.group(1))
    effective = None
    deposit = re.search(
        r"Interest Rate Applied to the Complementary Deposit Facility\s*([0-9.]+)%\s*since\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        plain,
        flags=re.IGNORECASE,
    )
    if deposit and abs(float(deposit.group(1)) - rate) < 0.001:
        try:
            effective = dt.datetime.strptime(deposit.group(2), "%B %d, %Y").date().isoformat()
        except ValueError:
            effective = deposit.group(2)
    return rate, effective


def parse_japan_cpi_page(text: str) -> tuple[str, float]:
    """Parse latest nationwide headline CPI from an official Statistics Bureau page."""
    plain = plain_html(text)

    # English Statistics Bureau home page has a compact, UTF-8 latest-indicator block:
    # Consumer Price Index 1.9% / July 2026 / change over the year.
    en = re.search(
        r"Consumer\s+Price\s+Index\s*([+-]?[0-9.]+)\s*%\s*([A-Za-z]+)\s+(20\d{2})\s*change\s+over\s+the\s+year",
        plain,
        flags=re.IGNORECASE,
    )
    if en:
        try:
            month = dt.datetime.strptime(en.group(2), "%B").month
        except ValueError as exc:
            raise RuntimeError(f"Japan CPI English month invalid: {en.group(2)}") from exc
        return f"{int(en.group(3)):04d}-{month:02d}", float(en.group(1))

    # Japanese monthly summary fallback. Exclude the 2025-base phrase and anchor the
    # rate to point (1), the nationwide all-items index.
    period = re.search(
        r"全国\s*(20\d{2})年(?:\s*(?:（\s*令和\d+年\s*）|\(\s*令和\d+年\s*\)))?\s*(\d{1,2})月分",
        plain,
    )
    if not period:
        period = re.search(
            r"(20\d{2})年(?:\s*(?:（\s*令和\d+年\s*）|\(\s*令和\d+年\s*\)))?\s*(\d{1,2})月分",
            plain,
        )
    if not period:
        raise RuntimeError("Japan CPI survey month not found")

    yoy = re.search(
        r"(?:\(\s*1\s*\)|（\s*1\s*）)\s*総合指数.*?前年同月比は\s*([0-9.]+)\s*[％%]\s*の\s*(上昇|下落)",
        plain,
        flags=re.DOTALL,
    )
    if not yoy:
        point1 = re.search(
            r"(?:\(\s*1\s*\)|（\s*1\s*）)(.*?)(?=(?:\(\s*2\s*\)|（\s*2\s*）))",
            plain,
            flags=re.DOTALL,
        )
        segment = point1.group(1) if point1 else ""
        yoy = re.search(
            r"総合指数.*?前年同月比は\s*([0-9.]+)\s*[％%].*?(上昇|下落)",
            segment,
            flags=re.DOTALL,
        )
    if not yoy:
        raise RuntimeError("Japan all-items CPI YoY not found")
    value = float(yoy.group(1)) * (-1.0 if yoy.group(2) == "下落" else 1.0)
    return f"{int(period.group(1)):04d}-{int(period.group(2)):02d}", value


def _fetch(url: str, *, accept: str = "text/html,*/*") -> str:
    text, error = fetch_text(url, USER_AGENT, timeout=20, attempts=2, accept=accept)
    if error or not text:
        raise RuntimeError(error or f"empty response: {url}")
    return text


def fetch_japan_cpi() -> tuple[str, float]:
    errors: list[str] = []
    # Prefer the simple English official home page because it avoids Japanese charset
    # variations seen through proxy/direct routes. Fall back to the detailed Japanese page.
    for url in (JP_CPI_EN_HOME, JP_CPI_JP_URL):
        try:
            return parse_japan_cpi_page(_fetch(url))
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {exc}")
    raise RuntimeError(" | ".join(errors))


def fetch_inputs() -> RealRateInputs:
    upper_date, upper = parse_fred_latest_csv(_fetch(FED_UPPER_CSV, accept="text/csv,text/plain,*/*"))
    lower_date, lower = parse_fred_latest_csv(_fetch(FED_LOWER_CSV, accept="text/csv,text/plain,*/*"))
    if abs(upper - lower) > 2.0 or upper < lower:
        raise RuntimeError(f"Fed target range invalid: lower={lower}, upper={upper}")
    fed_date = min(upper_date, lower_date)

    us_period, us_cpi = parse_bls_cpi_api(_fetch(BLS_CPI_API, accept="application/json,*/*"))
    boj_rate, boj_effective = parse_boj_policy_home(_fetch(BOJ_HOME))
    jp_period, jp_cpi = fetch_japan_cpi()

    return RealRateInputs(
        fed_lower=lower,
        fed_upper=upper,
        fed_midpoint=(lower + upper) / 2.0,
        fed_observation_date=fed_date,
        us_cpi_yoy=us_cpi,
        us_cpi_period=us_period,
        boj_policy_rate=boj_rate,
        boj_effective_date=boj_effective,
        jp_cpi_yoy=jp_cpi,
        jp_cpi_period=jp_period,
    )


def source_fingerprint(inputs: RealRateInputs) -> dict:
    return {
        "fed_midpoint": round(inputs.fed_midpoint, 4),
        "us_cpi_period": inputs.us_cpi_period,
        "us_cpi_yoy": round(inputs.us_cpi_yoy, 4),
        "boj_policy_rate": round(inputs.boj_policy_rate, 4),
        "jp_cpi_period": inputs.jp_cpi_period,
        "jp_cpi_yoy": round(inputs.jp_cpi_yoy, 4),
    }


def _direction(change: float | None, threshold: float) -> str:
    if change is None:
        return "기준값 저장 중"
    if change <= -threshold:
        return "엔화 강세 방향"
    if change >= threshold:
        return "엔화 약세 방향"
    return "중립"


def classify(previous: dict, pending: dict, inputs: RealRateInputs) -> dict:
    prev_overlay = previous.get("real_rate_overlay") or {}
    prev_metrics = prev_overlay.get("metrics") or {}
    prev_values = previous.get("values") or {}
    current_values = pending.get("values") or {}

    us_real = inputs.fed_midpoint - inputs.us_cpi_yoy
    jp_real = inputs.boj_policy_rate - inputs.jp_cpi_yoy
    real_gap = us_real - jp_real
    policy_gap = inputs.fed_midpoint - inputs.boj_policy_rate

    prev_real_gap = num(prev_metrics.get("us_jp_real_gap"))
    prev_policy_gap = num(prev_metrics.get("nominal_policy_gap"))
    real_gap_change = None if prev_real_gap is None else real_gap - prev_real_gap
    policy_gap_change = None if prev_policy_gap is None else policy_gap - prev_policy_gap

    current_spread = num(current_values.get("us_jp_2y_spread"))
    previous_spread = num(prev_values.get("us_jp_2y_spread"))
    spread_change_bp = None
    if current_spread is not None and previous_spread is not None:
        spread_change_bp = (current_spread - previous_spread) * 100.0

    fingerprint = source_fingerprint(inputs)
    prev_fingerprint = prev_overlay.get("source_fingerprint") or {}
    changed_sources: list[str] = []
    if prev_overlay.get("available"):
        if prev_fingerprint.get("fed_midpoint") != fingerprint["fed_midpoint"]:
            changed_sources.append("Fed 정책금리")
        if prev_fingerprint.get("us_cpi_period") != fingerprint["us_cpi_period"] or prev_fingerprint.get("us_cpi_yoy") != fingerprint["us_cpi_yoy"]:
            changed_sources.append("미국 CPI")
        if prev_fingerprint.get("boj_policy_rate") != fingerprint["boj_policy_rate"]:
            changed_sources.append("BOJ 정책금리")
        if prev_fingerprint.get("jp_cpi_period") != fingerprint["jp_cpi_period"] or prev_fingerprint.get("jp_cpi_yoy") != fingerprint["jp_cpi_yoy"]:
            changed_sources.append("일본 CPI")

    real_direction = _direction(real_gap_change, REAL_DIRECTION_PP)
    market_direction = _direction(spread_change_bp, MARKET_DIRECTION_BP)
    if real_direction.startswith("엔화") and market_direction.startswith("엔화"):
        alignment = "일치" if real_direction == market_direction else "충돌"
    else:
        alignment = "확인 대기"

    if real_gap >= STRUCTURAL_LEVEL_BAND_PP:
        structural_bias = "미국 실질금리 우위 — 엔화 구조적 약세 압력"
    elif real_gap <= -STRUCTURAL_LEVEL_BAND_PP:
        structural_bias = "일본 실질금리 우위 — 엔화 구조적 강세 압력"
    else:
        structural_bias = "실질정책금리 격차 중립권"

    metrics = RealRateMetrics(
        us_real_policy_rate=us_real,
        jp_real_policy_rate=jp_real,
        us_jp_real_gap=real_gap,
        nominal_policy_gap=policy_gap,
        real_gap_change_pp=real_gap_change,
        policy_gap_change_pp=policy_gap_change,
        us_jp_2y_spread_change_bp=spread_change_bp,
        real_rate_direction=real_direction,
        market_rate_direction=market_direction,
        signal_alignment=alignment,
        structural_bias=structural_bias,
        official_event_changed=bool(changed_sources),
        changed_sources=tuple(changed_sources),
    )
    return {
        "initialized": True,
        "available": True,
        "checked_at_kst": dt.datetime.now(KST).isoformat(timespec="seconds"),
        "inputs": asdict(inputs),
        "metrics": asdict(metrics),
        "source_fingerprint": fingerprint,
        "thresholds": {
            "real_gap_alert_pp": REAL_GAP_ALERT_PP,
            "policy_gap_alert_pp": POLICY_GAP_ALERT_PP,
            "real_direction_pp": REAL_DIRECTION_PP,
            "market_direction_bp": MARKET_DIRECTION_BP,
        },
        "note": "사후 실질정책금리는 후행 구조지표로만 사용하며, 단독으로 🟠·🔴 엔캐리 청산 경보를 만들지 않음.",
    }


def alert_reasons(previous: dict, context: dict) -> list[str]:
    prev_overlay = previous.get("real_rate_overlay") or {}
    if not prev_overlay.get("available"):
        return []
    metrics = context.get("metrics") or {}
    if not metrics.get("official_event_changed"):
        return []

    out: list[str] = []
    real_change = num(metrics.get("real_gap_change_pp"))
    policy_change = num(metrics.get("policy_gap_change_pp"))
    current_gap = num(metrics.get("us_jp_real_gap"))
    prior_gap = num((prev_overlay.get("metrics") or {}).get("us_jp_real_gap"))

    if real_change is not None and real_change <= -REAL_GAP_ALERT_PP:
        out.append(f"미·일 실질정책금리 갭 {abs(real_change):.2f}%p 축소 — 엔화 정상화 구조 강화")
    elif real_change is not None and real_change >= REAL_GAP_ALERT_PP:
        out.append(f"미·일 실질정책금리 갭 {abs(real_change):.2f}%p 확대 — 엔화 약세 구조 강화")

    if policy_change is not None and policy_change <= -POLICY_GAP_ALERT_PP:
        out.append(f"Fed-BOJ 명목 정책금리 격차 {abs(policy_change):.2f}%p 축소 — BOJ 상대 정상화 속도 우위")
    elif policy_change is not None and policy_change >= POLICY_GAP_ALERT_PP:
        out.append(f"Fed-BOJ 명목 정책금리 격차 {abs(policy_change):.2f}%p 확대 — 미국 상대 긴축 우위")

    if current_gap is not None and prior_gap is not None and current_gap * prior_gap < 0:
        out.append("미·일 실질정책금리 우위 국가가 역전")

    previous_alignment = (prev_overlay.get("metrics") or {}).get("signal_alignment")
    if metrics.get("signal_alignment") == "충돌" and previous_alignment != "충돌":
        out.append("사후 실질금리와 미·일 2년 시장금리 신호가 서로 반대 방향으로 전환")
    return out


def fmt(value, suffix="", digits=2) -> str:
    if value is None:
        return "확인 불가"
    return f"{float(value):+.{digits}f}{suffix}"


def context_block(context: dict) -> str:
    if not context.get("available"):
        return "\n".join([
            "실질금리·정책 정상화",
            "- 공식 원천 조회 실패로 이번 실행에서는 실질금리 점수를 사용하지 않습니다.",
            "※ 기존 USD/JPY·미일 2년 금리차·변동성·포지션 경보는 그대로 작동합니다.",
        ])
    inputs = context.get("inputs") or {}
    m = context.get("metrics") or {}
    changed = ", ".join(m.get("changed_sources") or []) or "새 공식 이벤트 없음"
    return "\n".join([
        "실질금리·정책 정상화",
        f"- 미국 사후 실질정책금리: {fmt(m.get('us_real_policy_rate'), '%')} = Fed 중간값 {fmt(inputs.get('fed_midpoint'), '%')} - 전체 CPI {fmt(inputs.get('us_cpi_yoy'), '%')} ({inputs.get('us_cpi_period')})",
        f"- 일본 사후 실질정책금리: {fmt(m.get('jp_real_policy_rate'), '%')} = BOJ {fmt(inputs.get('boj_policy_rate'), '%')} - 전체 CPI {fmt(inputs.get('jp_cpi_yoy'), '%')} ({inputs.get('jp_cpi_period')})",
        f"- 미·일 실질정책금리 갭: {fmt(m.get('us_jp_real_gap'), '%p')} / 직전 공식 이벤트 대비 {fmt(m.get('real_gap_change_pp'), '%p')}",
        f"- Fed-BOJ 명목 정책금리 격차: {fmt(m.get('nominal_policy_gap'), '%p')} / 직전 대비 {fmt(m.get('policy_gap_change_pp'), '%p')}",
        f"- 미·일 2년 시장금리차 변화: {fmt(m.get('us_jp_2y_spread_change_bp'), 'bp', digits=1)}",
        f"- 신호 비교: 실질금리 {m.get('real_rate_direction')} / 시장금리 {m.get('market_rate_direction')} → {m.get('signal_alignment')}",
        f"- 구조 판정: {m.get('structural_bias')}",
        f"- 새 공식 입력: {changed}",
        "※ 사후 실질금리는 현재 물가를 빼는 후행 구조지표입니다. 미·일 2년 금리차와 충돌하면 시장금리 신호를 단기 판단에 우선합니다.",
        "※ ECB는 글로벌 배경 참고 대상일 뿐 USD/JPY 엔캐리 점수에는 직접 넣지 않습니다.",
    ])


def _add_reason_lines(body: str, reasons: list[str]) -> str:
    if not reasons or "이번 변화\n" not in body:
        return body
    additions = "\n".join(f"- {reason}" for reason in reasons)
    return body.replace("이번 변화\n", "이번 변화\n" + additions + "\n", 1)


def _reposition_blocks(body: str, real_block: str) -> str:
    policy_block = ""
    match = re.search(r"\n\n(긴축 경로·레버리지\n.*)\Z", body, flags=re.DOTALL)
    if match:
        policy_block = match.group(1).strip()
        body = body[: match.start()].rstrip()
    combined = real_block.strip()
    if policy_block:
        combined += "\n\n" + policy_block
    marker = "\n\n출처\n"
    if marker in body:
        return body.replace(marker, "\n\n" + combined + marker, 1)
    return body.rstrip() + "\n\n" + combined + "\n"


def source_lines() -> list[str]:
    return [
        f"- Federal Reserve target range: {FED_SOURCE_URL}",
        f"- U.S. CPI (BLS): {BLS_CPI_API}",
        f"- Bank of Japan policy guideline: {BOJ_HOME}",
        f"- Japan CPI (Statistics Bureau): {JP_CPI_SOURCE_URL}",
    ]


def _ensure_sources(body: str) -> str:
    missing = [line for line in source_lines() if line not in body]
    if not missing:
        return body
    if "\n\n출처\n" in body:
        return body.rstrip() + "\n" + "\n".join(missing) + "\n"
    return body.rstrip() + "\n\n출처\n" + "\n".join(missing) + "\n"


def create_yellow_alert(pending: dict, context: dict, reasons: list[str]) -> None:
    values = pending.get("values") or {}
    ALERT_TITLE.write_text("🟡 엔캐리 복합 수급 알림\n", encoding="utf-8")
    lines = [
        f"조회 시각: {dt.datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S KST')}", "", "판정",
        f"- 캐리 청산 위험: {pending.get('unwind_label') or '엔캐리 청산 미확인'}",
        f"- 엔화 재약세·캐리 재구축: {pending.get('rebuild_label') or '엔화 재약세·캐리 재구축 미확인'}",
        "- 실질금리 구조 변화: 보조 신호만 반영 — 단독으로 🟠·🔴 승격하지 않음", "", "이번 변화",
        *[f"- {item}" for item in reasons], "", "시장·금리",
        f"- USD/JPY {float(values.get('usdjpy') or 0):.3f}",
        f"- 일본 2년 JGB {float(values.get('jgb2') or 0):.3f}% / 미국 2년 국채 {float(values.get('ust2') or 0):.3f}% / 미·일 2년 금리차 {float(values.get('us_jp_2y_spread') or 0):.3f}%p",
        "", context_block(context), "", "출처", *source_lines(),
    ]
    ALERT_BODY.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    write_json(ALERT_JSON, {
        "verdict": {
            "unwind_level": int(pending.get("unwind_level") or 0), "unwind_label": pending.get("unwind_label"),
            "rebuild_level": int(pending.get("rebuild_level") or 0), "rebuild_label": pending.get("rebuild_label"),
        },
        "reasons": reasons, "real_rate_overlay": context,
        "generated_at_kst": dt.datetime.now(KST).isoformat(timespec="seconds"),
    })


def main() -> int:
    pending = load_json(PENDING_PATH, {})
    if not pending:
        print("yen carry real-rate overlay: pending composite state missing")
        return 0
    previous = load_json(STATE_PATH, {})
    errors: list[str] = []
    try:
        context = classify(previous, pending, fetch_inputs())
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
        context = {
            "initialized": True, "available": False,
            "checked_at_kst": dt.datetime.now(KST).isoformat(timespec="seconds"),
            "errors": errors, "note": "공식 원천 조회 실패 시 실질금리 신호를 점수에 넣지 않음.",
        }

    reasons = alert_reasons(previous, context) if context.get("available") else []
    pending["real_rate_overlay"] = context
    write_json(PENDING_PATH, pending)
    write_json(CONTEXT_JSON, context)
    CONTEXT_MD.write_text("# 엔캐리 실질금리·정책 정상화\n\n" + context_block(context) + "\n", encoding="utf-8")

    if reasons and not ALERT_BODY.exists():
        create_yellow_alert(pending, context, reasons)
    elif ALERT_BODY.exists():
        body = _add_reason_lines(ALERT_BODY.read_text(encoding="utf-8"), reasons)
        if "실질금리·정책 정상화" not in body:
            body = _reposition_blocks(body, context_block(context))
        body = _ensure_sources(body)
        ALERT_BODY.write_text(body.rstrip() + "\n", encoding="utf-8")
        payload = load_json(ALERT_JSON, {})
        payload.setdefault("reasons", [])
        for item in reasons:
            if item not in payload["reasons"]:
                payload["reasons"].append(item)
        payload["real_rate_overlay"] = context
        write_json(ALERT_JSON, payload)

    print(json.dumps({"available": context.get("available"), "reasons": reasons, "metrics": context.get("metrics"), "errors": errors}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
