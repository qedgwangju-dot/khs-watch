#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALERT_PATH = ROOT / "out" / "crypto_liquidity_watch_telegram.txt"
PENDING_STATE_PATH = ROOT / "out" / "crypto_liquidity_watch_pending_state.json"


def format_trigger(line: str, is_partial: bool = False) -> list[str]:
    text = line.removeprefix("• ").strip()

    if text.startswith("BTC 현물 ETF 5거래일 구간 이동:"):
        body = text.split(":", 1)[1].strip()
        if " / 이전5 " in body:
            recent, previous = body.split(" / 이전5 ", 1)
            recent = recent.removeprefix("최근5 ")
            heading = "• <b>5거래일 구간 이동 · 잠정</b>" if is_partial else "• <b>5거래일 구간 이동</b>"
            recent_label = "최근5(잠정)" if is_partial else "최근5"
            return [
                heading,
                f"  {recent_label}  {recent}",
                f"  이전5  {previous}",
            ]

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


def load_pending_state() -> dict:
    if not PENDING_STATE_PATH.exists():
        return {}
    try:
        return json.loads(PENDING_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def fmt_usd_m(value: float) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value:,.1f}백만달러"


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "비교 불가"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:,.1f}%"


def detailed_judgement() -> str | None:
    """Build a directional interpretation instead of a generic '혼조' label.

    Separate four things that can point in different directions:
    1) today's ETF flow direction, 2) change in daily flow intensity,
    3) 5-day flow trend, 4) long-rate discount-rate pressure.
    """
    state = load_pending_state()
    rates = state.get("rates") or {}
    etf = state.get("btc_etf") or {}
    if not rates or not etf:
        return None

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
    five_change = etf.get("five_day_change_usd_m")
    five_change = float(five_change) if five_change is not None else None
    five_pct = etf.get("five_day_change_pct")
    five_pct = float(five_pct) if five_pct is not None else None
    r10 = float(rates.get("daily_10y_bp", 0.0) or 0.0)
    r30 = float(rates.get("daily_30y_bp", 0.0) or 0.0)

    # ETF current direction.
    if flow > 0:
        flow_label = "우호적"
        flow_text = f"{fmt_usd_m(flow)} 순유입 → BTC 위험자산 수급에 플러스"
        flow_score = 1
    elif flow < 0:
        flow_label = "불리"
        flow_text = f"{fmt_usd_m(flow)} 순유출 → BTC 위험자산 수급에 마이너스"
        flow_score = -1
    else:
        flow_label = "중립"
        flow_text = "순유입·순유출이 0에 가까워 당일 ETF 수급 방향이 뚜렷하지 않음"
        flow_score = 0

    # Daily momentum: distinguish direction from strength.
    if flow > 0 and prev_flow > 0:
        if day_change < 0:
            momentum_label = "둔화"
            momentum_text = (
                f"순유입은 유지됐지만 {fmt_usd_m(prev_flow)} → {fmt_usd_m(flow)}"
                f" ({fmt_pct(day_change_pct)})로 매수 강도는 약해짐"
            )
        elif day_change > 0:
            momentum_label = "강화"
            momentum_text = (
                f"순유입이 {fmt_usd_m(prev_flow)} → {fmt_usd_m(flow)}"
                f" ({fmt_pct(day_change_pct)})로 확대"
            )
        else:
            momentum_label = "유지"
            momentum_text = "전일과 같은 수준의 순유입"
    elif flow < 0 and prev_flow < 0:
        if flow > prev_flow:
            momentum_label = "개선"
            momentum_text = f"순유출은 지속되지만 {fmt_usd_m(prev_flow)} → {fmt_usd_m(flow)}로 유출 강도 완화"
        elif flow < prev_flow:
            momentum_label = "악화"
            momentum_text = f"순유출이 {fmt_usd_m(prev_flow)} → {fmt_usd_m(flow)}로 확대"
        else:
            momentum_label = "유지"
            momentum_text = "전일과 같은 수준의 순유출"
    elif prev_flow <= 0 < flow:
        momentum_label = "개선"
        momentum_text = f"전일 순유출/중립에서 {fmt_usd_m(flow)} 순유입으로 전환"
    elif prev_flow >= 0 > flow:
        momentum_label = "악화"
        momentum_text = f"전일 순유입/중립에서 {fmt_usd_m(flow)} 순유출로 전환"
    else:
        momentum_label = "중립"
        momentum_text = "전일 대비 자금흐름 강도 변화 제한"

    # 5-day trend.
    five_score = 0
    if last5 is not None and prev5 is not None:
        if last5 > 0 and prev5 > 0:
            if last5 > prev5:
                five_label = "개선"
                five_score = 1
                five_text = f"최근5 {fmt_usd_m(last5)} vs 이전5 {fmt_usd_m(prev5)} · {fmt_pct(five_pct)} → 누적 순유입 확대"
            elif last5 < prev5:
                five_label = "둔화"
                five_score = 0
                five_text = f"최근5 {fmt_usd_m(last5)} vs 이전5 {fmt_usd_m(prev5)} · {fmt_pct(five_pct)} → 순유입은 유지되지만 누적 강도 둔화"
            else:
                five_label = "유지"
                five_text = f"최근5와 이전5 모두 {fmt_usd_m(last5)} → 누적 흐름 변화 없음"
        elif last5 > 0 >= prev5:
            five_label = "강한 개선"
            five_score = 1
            five_text = f"최근5 {fmt_usd_m(last5)} · 이전5 {fmt_usd_m(prev5)} → 순유출에서 순유입으로 전환"
        elif last5 < 0 <= prev5:
            five_label = "강한 악화"
            five_score = -1
            five_text = f"최근5 {fmt_usd_m(last5)} · 이전5 {fmt_usd_m(prev5)} → 순유입에서 순유출로 전환"
        elif last5 < 0 and prev5 < 0:
            if last5 > prev5:
                five_label = "개선"
                five_score = 0
                five_text = f"최근5 {fmt_usd_m(last5)} vs 이전5 {fmt_usd_m(prev5)} → 순유출 지속이나 유출 규모 축소"
            else:
                five_label = "악화"
                five_score = -1
                five_text = f"최근5 {fmt_usd_m(last5)} vs 이전5 {fmt_usd_m(prev5)} → 누적 순유출 확대"
        else:
            five_label = "중립"
            five_text = "5거래일 누적 자금흐름 방향 제한"
    else:
        five_label = "확인 불가"
        five_text = "검증된 10개 거래일이 부족해 5거래일 구간 비교 보류"

    # Rate effect. Opposite-sign or tiny moves are treated as near-neutral rather than generic mixed.
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
        rate_label = "중립"
        rate_score = 0
        rate_text = "10Y·30Y 모두 전일 대비 변화 없음 → 할인율 영향 제한"
    else:
        rate_label = "거의 중립"
        rate_score = 0
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


def format_alert(text: str) -> str:
    raw_lines = text.splitlines()
    out: list[str] = []
    in_trigger_block = False
    inserted_trigger_heading = False
    is_partial = "잠정 집계" in text

    for line in raw_lines:
        stripped = line.strip()

        if stripped == "[크립토 유동성 변화 감지]":
            out.append("<b>크립토 유동성 변화 감지</b>")
            continue

        if stripped.startswith("조회시각(KST):"):
            value = stripped.split(":", 1)[1].strip()
            out.append(f"<code>조회 {value}</code>")
            in_trigger_block = True
            continue

        if in_trigger_block and stripped.startswith("• "):
            if not inserted_trigger_heading:
                if out and out[-1] != "":
                    out.append("")
                out.append("<b>핵심 변화</b>")
                inserted_trigger_heading = True
            out.extend(format_trigger(stripped, is_partial=is_partial))
            continue

        if stripped.startswith("미 국채 — 미 재무부 공식 수익률곡선 기준일"):
            in_trigger_block = False
            date = stripped.rsplit(" ", 1)[-1]
            if out and out[-1] != "":
                out.append("")
            out.append(f"<b>미 국채</b> · 공식 기준일 <code>{date}</code>")
            continue

        m_rate = re.match(
            r"• (10Y|30Y) ([\d.]+)% \| 직전 공식일\(([^)]+)\) 대비 ([+-][\d.]+bp) \| 5거래일 ([+-][\d.]+bp)",
            stripped,
        )
        if m_rate:
            out.append(
                f"• <b>{m_rate.group(1)} {m_rate.group(2)}%</b> | 직전({m_rate.group(3)}) {m_rate.group(4)} | 5거래일 {m_rate.group(5)}"
            )
            continue

        if stripped.startswith("※ 미 재무부 일일 수익률은"):
            out.append(stripped)
            continue

        if stripped.startswith("BTC 현물 ETF — Farside 기준 최신 유효일"):
            date = stripped.rsplit(" ", 1)[-1]
            if out and out[-1] != "":
                out.append("")
            out.append(f"<b>BTC 현물 ETF</b> · Farside <code>{date}</code>")
            continue

        if stripped.startswith("• 최신:"):
            body = stripped.removeprefix("• 최신:").strip()
            m = re.match(r"(\d{4}-\d{2}-\d{2})\s+(.+?)\s+\((잠정 집계|현재 집계 완료[^,)]*)(.*)\)$", body)
            if m:
                out.append(f"• <b>최신 {m.group(2)}</b>")
                status = m.group(3)
                if status == "잠정 집계":
                    status += " · 일부 ETF 미보고"
                out.append(f"  {m.group(1)} · {status}{m.group(4)}")
            else:
                out.append(f"• <b>최신</b> {body}")
            continue

        if stripped.startswith("• 직전:"):
            out.append(stripped.replace("• 직전:", "• 직전  ", 1))
            continue

        if stripped.startswith("• 전일 대비:"):
            label = "전일 대비 · 잠정" if is_partial else "전일 대비"
            out.append(f"• <b>{label}</b>  {stripped.split(':', 1)[1].strip()}")
            continue

        if stripped.startswith("• 최근 5거래일("):
            label = "최근 5거래일 · 잠정" if is_partial else "최근 5거래일"
            out.append(f"• <b>{label}</b> {stripped.split('):', 1)[0].split('(', 1)[1]} · {stripped.split('):', 1)[1].strip()}")
            continue

        if stripped.startswith("• 이전 5거래일("):
            out.append(f"• 이전 5거래일 {stripped.split('):', 1)[0].split('(', 1)[1]} · {stripped.split('):', 1)[1].strip()}")
            continue

        if stripped.startswith("• 5거래일 구간 대비:"):
            label = "5거래일 구간 대비 · 잠정" if is_partial else "5거래일 구간 대비"
            out.append(f"• <b>{label}</b>  {stripped.split(':', 1)[1].strip()}")
            continue

        if stripped.startswith("• 5거래일 변화율:"):
            label = "5거래일 변화율 · 잠정" if is_partial else "5거래일 변화율"
            out.append(f"• {label}  {stripped.split(':', 1)[1].strip()}")
            continue

        if stripped.startswith("※ ") and "미보고" in stripped:
            out.append(stripped)
            continue

        if stripped.startswith("판단:"):
            detailed = detailed_judgement()
            body = detailed or stripped.split(":", 1)[1].strip()
            if out and out[-1] != "":
                out.append("")
            out.append(f"<blockquote><b>판단</b>\n{body}</blockquote>")
            continue

        if stripped.startswith("원화 환산 기준:"):
            if out and out[-1] != "":
                out.append("")
            out.extend(format_fx_line(stripped))
            continue

        if stripped == "공식·데이터 원천:":
            if out and out[-1] != "":
                out.append("")
            out.append("<b>원문</b>")
            continue

        if stripped.startswith("※ CLARITY Act"):
            out.append("")
            out.append(stripped)
            continue

        out.append(line)

    compact: list[str] = []
    for line in out:
        if line == "" and compact and compact[-1] == "":
            continue
        compact.append(line)
    return "\n".join(compact).strip() + "\n"


def main() -> None:
    if not ALERT_PATH.exists():
        return
    text = ALERT_PATH.read_text(encoding="utf-8")
    ALERT_PATH.write_text(format_alert(text), encoding="utf-8")


if __name__ == "__main__":
    main()
