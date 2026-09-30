#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALERT_PATH = ROOT / "out" / "crypto_liquidity_watch_telegram.txt"
PENDING_STATE_PATH = ROOT / "out" / "crypto_liquidity_watch_pending_state.json"


def load_pending_state() -> dict:
    if not PENDING_STATE_PATH.exists():
        return {}
    try:
        return json.loads(PENDING_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def extract_fx_rate(text: str) -> float | None:
    patterns = [
        r"1달러\s*=\s*([\d,]+(?:\.\d+)?)원",
        r"1달러=([\d,]+(?:\.\d+)?)원",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if not m:
            continue
        try:
            rate = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if 800.0 <= rate <= 2500.0:
            return rate
    return None


def format_krw_from_usd_m(value_usd_m: float, rate: float) -> str:
    eok = value_usd_m * rate / 100.0
    sign = "-" if eok < 0 else "+" if eok > 0 else ""
    rounded = int(round(abs(eok)))
    jo, rem = divmod(rounded, 10000)
    if jo:
        body = f"{jo}조{rem:,}억원" if rem else f"{jo}조원"
    else:
        body = f"{rounded:,}억원"
    return f"약 {sign}{body}"


def fmt_usd_m(value: float, rate: float | None = None) -> str:
    sign = "+" if value > 0 else ""
    base = f"{sign}{value:,.1f}백만달러"
    if rate is None:
        return base
    return f"{base} ({format_krw_from_usd_m(value, rate)})"


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "비교 불가"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:,.1f}%"


def ensure_krw_for_bare_usd(text: str, rate: float | None) -> str:
    """Final guard: no 백만달러 amount should be left without KRW when FX exists."""
    if rate is None:
        return text
    pattern = re.compile(r"(?P<amount>[+-]?\d[\d,]*(?:\.\d+)?)백만달러(?!\s*\(약)")

    def repl(m: re.Match[str]) -> str:
        raw = m.group("amount")
        value = float(raw.replace(",", ""))
        return f"{raw}백만달러 ({format_krw_from_usd_m(value, rate)})"

    return pattern.sub(repl, text)


def format_trigger(line: str, is_partial: bool = False) -> list[str]:
    text = line.removeprefix("• ").strip()

    if text.startswith("BTC 현물 ETF 새 일간 자금흐름"):
        m = re.match(r"BTC 현물 ETF 새 일간 자금흐름\(([^)]+)\):\s*(.+)", text)
        if m:
            return [f"• <b>새 일간 자금흐름</b> · {m.group(1)}", f"  <b>{m.group(2)}</b>"]

    if text.startswith("BTC 현물 ETF 당일 합계 수정"):
        m = re.match(r"BTC 현물 ETF 당일 합계 수정\(([^)]+)\):\s*(.+)", text)
        if m:
            return [f"• <b>당일 합계 수정</b> · {m.group(1)}", f"  {m.group(2)}"]

    if text.startswith("BTC 현물 ETF 과거 원자료 수정:"):
        return ["• <b>과거 원자료 수정</b>", f"  {text.split(':', 1)[1].strip()}"]

    if text.startswith("미 국채 장기금리 큰 변동:"):
        return ["• <b>미 국채 장기금리 큰 변동</b>", f"  {text.split(':', 1)[1].strip()}"]

    if text.startswith("미 재무부 공식 바이백"):
        return [f"• <b>{text}</b>"]

    return [line]


# Read rolling ETF flow in one fixed order: current 5-day window → prior 5-day window → difference.
def five_day_reading(etf: dict, rate: float | None, is_partial: bool) -> list[str]:
    last5 = etf.get("last5_usd_m")
    prev5 = etf.get("prev5_usd_m")
    if last5 is None or prev5 is None:
        return ["• <b>5거래일 비교</b> · 검증된 비교 구간 부족"]

    last5 = float(last5)
    prev5 = float(prev5)
    delta = etf.get("five_day_change_usd_m")
    delta = float(delta) if delta is not None else last5 - prev5
    pct = etf.get("five_day_change_pct")
    pct = float(pct) if pct is not None else None

    last_dates = etf.get("last5_dates") or []
    prev_dates = etf.get("prev5_dates") or []
    last_range = (
        f"{last_dates[0]}~{last_dates[-1]}" if len(last_dates) == 5 else "기간 확인 불가"
    )
    prev_range = (
        f"{prev_dates[0]}~{prev_dates[-1]}" if len(prev_dates) == 5 else "기간 확인 불가"
    )

    if last5 > 0 and prev5 > 0:
        direction = "순유입 강도 확대" if last5 > prev5 else "순유입 강도 둔화" if last5 < prev5 else "순유입 강도 동일"
    elif last5 < 0 and prev5 < 0:
        direction = "순유출 규모 축소" if last5 > prev5 else "순유출 규모 확대" if last5 < prev5 else "순유출 규모 동일"
    elif prev5 <= 0 < last5:
        direction = "순유출 → 순유입 전환"
    elif prev5 >= 0 > last5:
        direction = "순유입 → 순유출 전환"
    else:
        direction = "흐름 변화 제한"

    heading = "• <b>5거래일 비교 · 잠정</b>" if is_partial else "• <b>5거래일 비교</b>"
    recent_label = "최근5(잠정)" if is_partial else "최근5"
    pct_text = f" · {fmt_pct(pct)}" if pct is not None else ""
    return [
        heading,
        f"  {recent_label} {last_range} · <b>{fmt_usd_m(last5, rate)}</b>",
        f"  이전5 {prev_range} · {fmt_usd_m(prev5, rate)}",
        f"  → 구간 차이 {fmt_usd_m(delta, rate)}{pct_text} · {direction}",
    ]


def format_fx_line(line: str) -> list[str]:
    body = line.removeprefix("원화 환산 기준:").strip()
    parts = [x.strip() for x in body.split(" | ") if x.strip()]
    if not parts:
        return ["<b>원화 환산</b>", line]
    first = " · ".join(parts[:2])
    rest = parts[2:]
    out = ["<b>원화 환산</b>", f"• {first}"]
    if rest:
        out.append(f"• {' · '.join(rest)}")
    return out


def detailed_judgement(source_text: str) -> str | None:
    state = load_pending_state()
    rates = state.get("rates") or {}
    etf = state.get("btc_etf") or {}
    if not rates or not etf:
        return None

    fx_rate = extract_fx_rate(source_text)
    rate_date = str(rates.get("date") or "")
    etf_date = str(etf.get("date") or "")
    status = str(etf.get("status") or "")
    flow = float(etf.get("total_usd_m", 0.0) or 0.0)
    prev_flow = float(etf.get("prev_total_usd_m", 0.0) or 0.0)
    day_change = float(etf.get("day_change_usd_m", flow - prev_flow) or 0.0)
    day_change_pct = etf.get("day_change_pct")
    day_change_pct = float(day_change_pct) if day_change_pct is not None else None
    last5 = etf.get("last5_usd_m")
    prev5 = etf.get("prev5_usd_m")
    last5 = float(last5) if last5 is not None else None
    prev5 = float(prev5) if prev5 is not None else None
    five_pct = etf.get("five_day_change_pct")
    five_pct = float(five_pct) if five_pct is not None else None
    r10 = float(rates.get("daily_10y_bp", 0.0) or 0.0)
    r30 = float(rates.get("daily_30y_bp", 0.0) or 0.0)

    if flow > 0:
        flow_label, flow_score = "우호적", 1
        flow_text = f"{fmt_usd_m(flow, fx_rate)} 순유입 → BTC 위험자산 수급에 플러스"
    elif flow < 0:
        flow_label, flow_score = "불리", -1
        flow_text = f"{fmt_usd_m(flow, fx_rate)} 순유출 → BTC 위험자산 수급에 마이너스"
    else:
        flow_label, flow_score = "중립", 0
        flow_text = "순유입·순유출이 0에 가까워 당일 ETF 수급 방향이 뚜렷하지 않음"

    if flow > 0 and prev_flow > 0:
        if day_change < 0:
            momentum_label = "둔화"
            momentum_text = (
                f"순유입은 유지됐지만 {fmt_usd_m(prev_flow, fx_rate)} → {fmt_usd_m(flow, fx_rate)} "
                f"({fmt_pct(day_change_pct)})로 매수 강도는 약해짐"
            )
        elif day_change > 0:
            momentum_label = "강화"
            momentum_text = (
                f"순유입이 {fmt_usd_m(prev_flow, fx_rate)} → {fmt_usd_m(flow, fx_rate)} "
                f"({fmt_pct(day_change_pct)})로 확대"
            )
        else:
            momentum_label, momentum_text = "유지", "전일과 같은 수준의 순유입"
    elif flow < 0 and prev_flow < 0:
        if flow > prev_flow:
            momentum_label = "개선"
            momentum_text = f"순유출은 지속되지만 {fmt_usd_m(prev_flow, fx_rate)} → {fmt_usd_m(flow, fx_rate)}로 유출 강도 완화"
        elif flow < prev_flow:
            momentum_label = "악화"
            momentum_text = f"순유출이 {fmt_usd_m(prev_flow, fx_rate)} → {fmt_usd_m(flow, fx_rate)}로 확대"
        else:
            momentum_label, momentum_text = "유지", "전일과 같은 수준의 순유출"
    elif prev_flow <= 0 < flow:
        momentum_label = "개선"
        momentum_text = f"전일 순유출/중립에서 {fmt_usd_m(flow, fx_rate)} 순유입으로 전환"
    elif prev_flow >= 0 > flow:
        momentum_label = "악화"
        momentum_text = f"전일 순유입/중립에서 {fmt_usd_m(flow, fx_rate)} 순유출로 전환"
    else:
        momentum_label, momentum_text = "중립", "전일 대비 자금흐름 강도 변화 제한"

    five_score = 0
    if last5 is not None and prev5 is not None:
        if last5 > 0 and prev5 > 0:
            if last5 > prev5:
                five_label, five_score = "개선", 1
                five_text = f"최근5 {fmt_usd_m(last5, fx_rate)} vs 이전5 {fmt_usd_m(prev5, fx_rate)} · {fmt_pct(five_pct)} → 누적 순유입 확대"
            elif last5 < prev5:
                five_label = "둔화"
                five_text = f"최근5 {fmt_usd_m(last5, fx_rate)} vs 이전5 {fmt_usd_m(prev5, fx_rate)} · {fmt_pct(five_pct)} → 순유입은 유지되지만 누적 강도 둔화"
            else:
                five_label = "유지"
                five_text = f"최근5와 이전5 모두 {fmt_usd_m(last5, fx_rate)} → 누적 흐름 변화 없음"
        elif last5 > 0 >= prev5:
            five_label, five_score = "강한 개선", 1
            five_text = f"최근5 {fmt_usd_m(last5, fx_rate)} · 이전5 {fmt_usd_m(prev5, fx_rate)} → 순유출에서 순유입으로 전환"
        elif last5 < 0 <= prev5:
            five_label, five_score = "강한 악화", -1
            five_text = f"최근5 {fmt_usd_m(last5, fx_rate)} · 이전5 {fmt_usd_m(prev5, fx_rate)} → 순유입에서 순유출로 전환"
        elif last5 < 0 and prev5 < 0:
            if last5 > prev5:
                five_label = "개선"
                five_text = f"최근5 {fmt_usd_m(last5, fx_rate)} vs 이전5 {fmt_usd_m(prev5, fx_rate)} → 순유출 지속이나 유출 규모 축소"
            else:
                five_label, five_score = "악화", -1
                five_text = f"최근5 {fmt_usd_m(last5, fx_rate)} vs 이전5 {fmt_usd_m(prev5, fx_rate)} → 누적 순유출 확대"
        else:
            five_label, five_text = "중립", "5거래일 누적 자금흐름 방향 제한"
    else:
        five_label, five_text = "확인 불가", "검증된 10개 거래일이 부족해 5거래일 구간 비교 보류"

    max_rate_move = max(abs(r10), abs(r30))
    if r10 > 0 and r30 > 0:
        rate_label = "불리" if max_rate_move >= 3 else "소폭 불리"
        rate_score = -1 if max_rate_move >= 3 else 0
        rate_text = f"10Y {r10:+.1f}bp · 30Y {r30:+.1f}bp 상승 → 할인율 부담 확대"
    elif r10 < 0 and r30 < 0:
        rate_label = "우호적" if max_rate_move >= 3 else "소폭 우호적"
        rate_score = 1 if max_rate_move >= 3 else 0
        rate_text = f"10Y {r10:+.1f}bp · 30Y {r30:+.1f}bp 하락 → 할인율 부담 완화"
    elif r10 == 0 and r30 == 0:
        rate_label, rate_score = "중립", 0
        rate_text = "10Y·30Y 모두 전일 대비 변화 없음 → 할인율 영향 제한"
    else:
        rate_label, rate_score = "거의 중립", 0
        rate_text = f"10Y {r10:+.1f}bp · 30Y {r30:+.1f}bp로 방향이 엇갈려 서로 상쇄 → 할인율 영향 제한"

    same_date = bool(rate_date and etf_date and rate_date == etf_date)
    complete = status == "complete"

    if not same_date:
        overall = "최종판정 보류"
        one_liner = (
            f"ETF는 {flow_label} 신호지만 미 국채({rate_date})와 ETF({etf_date}) 기준일이 달라 "
            "같은 날의 종합 방향으로 확정하지 않음"
        )
    else:
        score = flow_score + five_score + rate_score
        if score >= 2:
            overall = "우호적"
        elif score == 1:
            overall = "소폭 우호적"
        elif score == 0:
            overall = "중립·혼조"
        elif score == -1:
            overall = "소폭 불리"
        else:
            overall = "불리"

        if flow > 0 and day_change < 0 and last5 is not None and prev5 is not None and last5 > prev5:
            one_liner = "돈은 계속 들어오고 5일 누적도 개선됐지만, 전일보다 유입 강도는 약해져 강한 호재보다는 완만한 우호 신호"
        elif flow > 0 and day_change > 0:
            one_liner = "당일 순유입과 유입 강도가 함께 개선돼 유동성 측면의 우호 신호가 강화"
        elif flow < 0 and day_change < 0:
            one_liner = "당일 순유출이 이어지고 유출 강도도 커져 유동성 측면의 부담이 확대"
        elif flow < 0 and day_change > 0:
            one_liner = "순유출은 남아 있지만 유출 강도는 완화돼 악화 속도는 둔화"
        else:
            one_liner = f"ETF 수급은 {flow_label}, 5일 흐름은 {five_label}, 금리는 {rate_label} → 현재 종합은 {overall}"

    lines = [
        f"<b>현재 방향 · {overall}</b>",
        f"• <b>ETF 유동성 · {flow_label}</b> — {flow_text}",
        f"• <b>유입/유출 강도 · {momentum_label}</b> — {momentum_text}",
        f"• <b>5거래일 흐름 · {five_label}</b> — {five_text}",
        f"• <b>금리 · {rate_label}</b> — {rate_text}",
        f"• <b>한마디로</b> — {one_liner}",
    ]

    if not complete:
        missing = int(etf.get("missing_funds", 0) or 0)
        reported = int(etf.get("reported_funds", 0) or 0)
        total_funds = reported + missing
        coverage = f"{total_funds}개 중 {reported}개 반영·{missing}개 미보고" if total_funds else "일부 ETF 미보고"
        lines.append(f"• <b>주의</b> — Farside {coverage}라 ETF 값과 종합판정은 잠정")

    return "\n".join(lines)


def compact_judgement(state: dict) -> tuple[str, str]:
    rates = state.get("rates") or {}
    etf = state.get("btc_etf") or {}
    if not rates or not etf:
        return "판정 보류", "핵심 데이터가 부족해 종합 방향을 확정하지 않음"

    flow = float(etf.get("total_usd_m", 0.0) or 0.0)
    last5 = etf.get("last5_usd_m")
    prev5 = etf.get("prev5_usd_m")
    last5 = float(last5) if last5 is not None else None
    prev5 = float(prev5) if prev5 is not None else None
    r10 = float(rates.get("daily_10y_bp", 0.0) or 0.0)
    r30 = float(rates.get("daily_30y_bp", 0.0) or 0.0)
    same_date = str(rates.get("date") or "") == str(etf.get("date") or "")

    if not same_date:
        return "판정 보류", (
            f"미 국채({rates.get('date', 'N/A')})와 ETF({etf.get('date', 'N/A')}) 기준일이 달라 "
            "같은 날의 종합 방향으로 묶지 않음"
        )

    flow_score = 1 if flow > 0 else -1 if flow < 0 else 0
    five_score = 0
    if last5 is not None and prev5 is not None:
        if last5 > prev5:
            five_score = 1
        elif last5 < prev5:
            five_score = -1

    if r10 > 0 and r30 > 0 and max(abs(r10), abs(r30)) >= 3:
        rate_score = -1
    elif r10 < 0 and r30 < 0 and max(abs(r10), abs(r30)) >= 3:
        rate_score = 1
    else:
        rate_score = 0

    score = flow_score + five_score + rate_score
    if score >= 2:
        overall = "우호적"
    elif score == 1:
        overall = "소폭 우호적"
    elif score == 0:
        overall = "중립·혼조"
    elif score == -1:
        overall = "소폭 불리"
    else:
        overall = "불리"

    if flow > 0:
        day_text = "당일 ETF 순유입"
    elif flow < 0:
        day_text = "당일 ETF 순유출"
    else:
        day_text = "당일 ETF 수급 중립"

    if r10 > 0 and r30 > 0:
        rate_text = "장기금리 상승"
    elif r10 < 0 and r30 < 0:
        rate_text = "장기금리 하락"
    else:
        rate_text = "장기금리 혼조"

    if last5 is not None and prev5 is not None:
        if last5 > prev5:
            five_text = "5거래일 누적 흐름은 개선"
        elif last5 < prev5:
            five_text = "5거래일 누적 흐름은 둔화"
        else:
            five_text = "5거래일 누적 흐름은 보합"
    else:
        five_text = "5거래일 비교는 확인 불가"

    if flow < 0 and r10 > 0 and r30 > 0:
        reason = f"{day_text}과 {rate_text}은 부담. 다만 {five_text}."
    elif flow > 0 and r10 < 0 and r30 < 0:
        reason = f"{day_text}과 {rate_text}이 우호적. {five_text}."
    else:
        reason = f"{day_text} · {rate_text}. {five_text}."

    if str(etf.get("status") or "") != "complete":
        overall += " · 잠정"
    return overall, reason


def source_link(text: str, source_label: str, display: str) -> str | None:
    pattern = rf'• {re.escape(source_label)}:\s*<a href="([^"]+)">원문</a>'
    m = re.search(pattern, text)
    if not m:
        return None
    return f'<a href="{m.group(1)}">{display}</a>'


def format_alert(text: str) -> str:
    state = load_pending_state()
    rates = state.get("rates") or {}
    etf = state.get("btc_etf") or {}
    fx_rate = extract_fx_rate(text)
    is_partial = str(etf.get("status") or "") != "complete"

    raw_lines = text.splitlines()
    out: list[str] = ["<b>크립토 유동성 변화</b>"]

    lookup = ""
    for line in raw_lines:
        stripped = line.strip()
        if stripped.startswith("조회시각(KST):"):
            lookup = stripped.split(":", 1)[1].strip()
            break
        if stripped.startswith("<code>조회 ") and stripped.endswith("</code>"):
            lookup = stripped.removeprefix("<code>조회 ").removesuffix("</code>").strip()
            break
    if lookup:
        out.append(f"<code>{lookup}</code>")

    trigger_lines: list[str] = []
    capture = False
    known_trigger_prefixes = (
        "• BTC 현물 ETF",
        "• 미 국채 장기금리 큰 변동:",
        "• 미 재무부 공식 바이백",
    )
    for line in raw_lines:
        stripped = line.strip()
        if stripped.startswith("조회시각(KST):"):
            capture = True
            continue
        if not capture:
            continue
        if stripped.startswith("<b>BTC 자금 위치</b>") or stripped.startswith("미 국채 —"):
            break
        if stripped.startswith(known_trigger_prefixes):
            if stripped.startswith("• BTC 현물 ETF 5거래일 구간 이동:"):
                label = "• <b>5거래일 비교 갱신 · 잠정</b>" if is_partial else "• <b>5거래일 비교 갱신</b>"
                trigger_lines.append(label)
            else:
                trigger_lines.extend(format_trigger(stripped, is_partial=is_partial))

    if trigger_lines:
        out += ["", "<b>무엇이 바뀌었나</b>", *trigger_lines]

    out += ["", "<b>지금 숫자</b>"]

    if etf:
        flow = float(etf.get("total_usd_m", 0.0) or 0.0)
        status_text = ""
        reported = int(etf.get("reported_funds", 0) or 0)
        missing = int(etf.get("missing_funds", 0) or 0)
        total_funds = reported + missing
        if is_partial:
            status_text = (
                f" · 잠정 {reported}/{total_funds} 반영"
                if total_funds
                else " · 잠정"
            )
        out.append(
            f"• ETF {etf.get('date', 'N/A')} · <b>{fmt_usd_m(flow, fx_rate)}</b>{status_text}"
        )

        last5 = etf.get("last5_usd_m")
        prev5 = etf.get("prev5_usd_m")
        if last5 is not None and prev5 is not None:
            ordered = five_day_reading(etf, fx_rate, is_partial)
            # "지금 숫자"에서는 제목을 빼고 최근5 → 이전5 → 구간 차이 순서만 표시.
            for row in ordered[1:]:
                clean = row.strip()
                if clean.startswith("→ "):
                    clean = clean[2:]
                out.append(f"• {clean}")

    if rates:
        out.append(
            f"• 금리 · 10Y <b>{float(rates.get('10y', 0.0)):.2f}%</b>"
            f" ({float(rates.get('daily_10y_bp', 0.0)):+.1f}bp)"
            f" | 30Y <b>{float(rates.get('30y', 0.0)):.2f}%</b>"
            f" ({float(rates.get('daily_30y_bp', 0.0)):+.1f}bp)"
        )

    overall, reason = compact_judgement(state)
    out += ["", f"<blockquote><b>판정 · {overall}</b>\n{reason}</blockquote>"]

    fx_match = re.search(
        r"원화 환산 기준:\s*1달러=([\d,]+(?:\.\d+)?)원\s*\|\s*기준일\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|",
        text,
    )
    if fx_match:
        out += [
            "",
            f"• 환율 · 1달러={fx_match.group(1)}원 · {fx_match.group(2).strip()} · {fx_match.group(3).strip()}",
        ]

    links: list[str] = []
    for label, display in (
        ("BTC 현물 ETF", "Farside"),
        ("미 국채 금리", "미 재무부"),
        ("원/달러 환율", "ECOS"),
    ):
        link = source_link(text, label, display)
        if link:
            links.append(link)

    if any("바이백" in x for x in trigger_lines):
        buyback = source_link(text, "미 재무부 바이백", "바이백")
        if buyback:
            links.insert(1, buyback)

    if links:
        out += ["<b>원문</b> · " + " · ".join(links)]

    compact: list[str] = []
    for line in out:
        if line == "" and compact and compact[-1] == "":
            continue
        compact.append(line)

    formatted = "\n".join(compact).strip() + "\n"
    return ensure_krw_for_bare_usd(formatted, fx_rate)

def main() -> None:
    if not ALERT_PATH.exists():
        return
    text = ALERT_PATH.read_text(encoding="utf-8")
    ALERT_PATH.write_text(format_alert(text), encoding="utf-8")


if __name__ == "__main__":
    main()
