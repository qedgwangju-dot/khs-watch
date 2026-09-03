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


def provisional_judgement() -> str | None:
    state = load_pending_state()
    rates = state.get("rates") or {}
    etf = state.get("btc_etf") or {}
    if not rates or not etf or etf.get("status") == "complete":
        return None
    if rates.get("date") != etf.get("date"):
        return None

    r10 = float(rates.get("daily_10y_bp", 0.0) or 0.0)
    r30 = float(rates.get("daily_30y_bp", 0.0) or 0.0)
    flow = float(etf.get("total_usd_m", 0.0) or 0.0)
    missing = int(etf.get("missing_funds", 0) or 0)
    reported = int(etf.get("reported_funds", 0) or 0)
    total_funds = reported + missing
    date = str(etf.get("date") or "")

    if r10 <= 0 and r30 <= 0 and flow > 0:
        view = "위험자산에 우호적 — 장기금리 하락 + 현재 확인분 BTC ETF 순유입"
    elif r10 >= 0 and r30 >= 0 and flow < 0:
        view = "위험자산에 불리 — 장기금리 상승 + 현재 확인분 BTC ETF 순유출"
    else:
        view = "혼조 — 장기금리와 현재 확인분 BTC ETF 자금흐름의 방향이 엇갈림"

    coverage = (
        f"Farside {total_funds}개 ETF 중 {reported}개 반영·{missing}개 미보고"
        if total_funds > 0
        else "일부 ETF 미보고"
    )
    return (
        f"<b>잠정판정</b> · {date} 기준 {view}\n"
        f"<b>최종판정 보류</b> · {coverage}라 당일 합계가 추가 수정될 수 있음"
    )


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
            body = stripped.split(":", 1)[1].strip()
            provisional = provisional_judgement() if "집계 미완료" in body else None
            if out and out[-1] != "":
                out.append("")
            if provisional:
                out.append(f"<blockquote><b>판단</b>\n{provisional}</blockquote>")
            else:
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
