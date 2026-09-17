#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import html
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

import korea_market_stress_watch_v11 as v11
import korea_market_stress_watch_v14 as fx_basis

KST = ZoneInfo("Asia/Seoul")
ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "fx_sector_rotation_state.json"
MARKET_STATE_PATH = ROOT / "data" / "korea_market_stress_watch_state.json"
PENDING_PATH = ROOT / "out" / "fx_sector_rotation_pending_state.json"
ALERT_PATH = ROOT / "out" / "fx_sector_rotation_alert.html"
STATUS_PATH = ROOT / "out" / "fx_sector_rotation_status.md"

FX_URL = "https://api.stock.naver.com/marketindex/exchange/FX_USDKRW/prices?page=1&pageSize=5"
KOSPI_URL = "https://m.stock.naver.com/api/index/KOSPI/basic"
VALIDATION_FOOTER = "• 검증 원칙: 값의 시장·시점·산출방식을 확인한 뒤 사용하며, 서로 다른 기준값은 혼용하지 않음"

START = dt.time(9, 0)
MARKET_CLOSE = dt.time(15, 35)
END = dt.time(23, 59, 59)

FX_REBOUND_KRW = 10.0
FX_REBOUND_PCT = 0.5
FX_STRONG_KRW = 20.0
FX_STRONG_PCT = 1.0
SECTOR_RELATIVE_PPT = 1.0
COUNTER_RELATIVE_PPT = -0.5

SHIPBUILDING = [
    ("HD현대중공업", "329180"),
    ("삼성중공업", "010140"),
    ("HD한국조선해양", "009540"),
    ("한화오션", "042660"),
]
DEFENSE = [
    ("한화에어로스페이스", "012450"),
    ("현대로템", "064350"),
    ("LIG넥스원", "079550"),
    ("한국항공우주", "047810"),
]
COUNTER = [
    ("대한항공", "003490"),
    ("제주항공", "089590"),
    ("한국전력", "015760"),
    ("한국가스공사", "036460"),
]

TODAY_FX_SOURCE = "https://nwww.newsis.com/view/NISI20260917_0021440924"
TODAY_SHIP_SOURCE = "https://search.newspim.com/news/view/20260917000373"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; khs-fx-sector-rotation-watch/1.0)",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
}


def fnum(v: Any) -> float | None:
    try:
        if v is None or str(v).strip() == "":
            return None
        return float(str(v).replace(",", "").replace("%", "").strip())
    except Exception:
        return None


def load_state(today: str) -> dict[str, Any]:
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        state = {}
    if state.get("date") != today:
        state = {
            "date": today,
            "fx_samples": [],
            "sent_level": 0,
            "sent_weakening": False,
            "last_signal": None,
        }
    return state


def save_pending(state: dict[str, Any]) -> None:
    PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
    PENDING_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _validated_prev_close_from_market_watch(today: str) -> dict[str, Any] | None:
    try:
        state = json.loads(MARKET_STATE_PATH.read_text(encoding="utf-8"))
        fx = (state.get("snapshot") or {}).get("usdkrw") or {}
        if str(fx.get("date") or "") != today:
            return None
        if fx.get("comparison_valid") is not True:
            return None
        basis = str(fx.get("comparison_basis") or "")
        if "서울외환시장 15:30" not in basis:
            return None
        prev = float(fx["prev_value"])
        if not (900.0 <= prev <= 2500.0):
            return None
        return {
            "value": prev,
            "source": str(fx.get("seoul_close_source") or ""),
            "basis": basis,
        }
    except Exception:
        return None


def fetch_fx() -> dict[str, Any]:
    r = requests.get(FX_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    payload = r.json()
    rows = payload.get("result") if isinstance(payload, dict) else payload
    rows = rows or []
    if not rows:
        raise RuntimeError("원/달러 시세 없음")
    row = rows[0]
    value = fnum(row.get("closePrice"))
    if value is None:
        raise RuntimeError("원/달러 현재값 없음")

    today = str(row.get("localTradedAt") or row.get("localDate") or "")[:10]
    naver_prev = fnum(rows[1].get("closePrice")) if len(rows) > 1 else None
    prev = None
    prev_source = None
    basis = "서울외환시장 15:30 USD/KRW 종가"
    basis_error = None
    basis_reused = False
    try:
        ref = fx_basis.fetch_seoul_prev_close()
        prev = float(ref["value"])
        prev_source = str(ref.get("source") or "")
    except Exception as exc:
        cached = _validated_prev_close_from_market_watch(today)
        if cached:
            prev = float(cached["value"])
            prev_source = str(cached.get("source") or "")
            basis = str(cached.get("basis") or basis) + " · 시장 스트레스 감시 검증값 재사용"
            basis_reused = True
        else:
            basis_error = f"{type(exc).__name__}: {exc}"

    return {
        "value": value,
        "prev_close": prev,
        "naver_prev_close": naver_prev,
        "date": today,
        "source": FX_URL,
        "comparison_basis": basis,
        "prev_close_source": prev_source,
        "basis_error": basis_error,
        "basis_reused": basis_reused,
    }


def fetch_kospi() -> dict[str, Any]:
    r = requests.get(KOSPI_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()
    d = r.json()
    pct = fnum(d.get("fluctuationsRatio"))
    price = fnum(d.get("closePrice") or d.get("currentPrice"))
    if pct is None:
        raise RuntimeError("KOSPI 등락률 없음")
    return {"change_pct": pct, "price": price, "source": KOSPI_URL}


def fetch_quote(name: str, code: str) -> dict[str, Any]:
    q = v11.fetch_stock_quote(code)
    return {
        "name": str(q.get("name") or name),
        "code": code,
        "price": float(q["price"]),
        "change_pct": float(q["change_pct"]),
    }


def fetch_group(items: list[tuple[str, str]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name, code in items:
        try:
            out.append(fetch_quote(name, code))
        except Exception:
            out.append({"name": name, "code": code, "price": None, "change_pct": None})
    return out


def group_stats(rows: list[dict[str, Any]], benchmark: float) -> dict[str, Any]:
    vals = [float(r["change_pct"]) for r in rows if r.get("change_pct") is not None]
    if not vals:
        return {"avg": None, "positive": 0, "relative": None, "valid": 0, "confirmed": False}
    avg = sum(vals) / len(vals)
    pos = sum(1 for v in vals if v > 0)
    rel = avg - benchmark
    confirmed = len(vals) >= 3 and pos >= 3 and rel >= SECTOR_RELATIVE_PPT
    return {"avg": avg, "positive": pos, "relative": rel, "valid": len(vals), "confirmed": confirmed}


def quote_lines(rows: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for r in rows:
        if r.get("change_pct") is None:
            lines.append(f"• {html.escape(str(r['name']))}: 시세 확인 실패")
        else:
            lines.append(
                f"• {html.escape(str(r['name']))}: <b>{float(r['price']):,.0f}원 ({float(r['change_pct']):+.2f}%)</b>"
            )
    return lines


def fmt_stats(label: str, s: dict[str, Any], benchmark: float) -> list[str]:
    if s.get("avg") is None:
        return [f"• {label}: 확인 실패"]
    verdict = "확인" if s.get("confirmed") else "미확인"
    return [
        f"• {label}: {int(s['positive'])}/{int(s['valid'])} 상승 · 평균 <b>{float(s['avg']):+.2f}%</b>",
        f"  ↳ KOSPI {benchmark:+.2f}% 대비 상대강도 <b>{float(s['relative']):+.2f}%p</b> · 로테이션 {verdict}",
    ]


def build_alert(
    now: dt.datetime,
    fx: dict[str, Any],
    session_low: float,
    rebound_krw: float,
    rebound_pct: float,
    daily_krw: float | None,
    daily_pct: float | None,
    kospi: dict[str, Any],
    ship_rows: list[dict[str, Any]],
    defense_rows: list[dict[str, Any]],
    counter_rows: list[dict[str, Any]],
    ship: dict[str, Any],
    defense: dict[str, Any],
    counter: dict[str, Any],
    level: int,
) -> str:
    after_close = now.time() > MARKET_CLOSE
    if level >= 2:
        verdict = "🔴 <b>강한 환율 민감 업종 로테이션</b> — 환율 강한 반등과 조선·방산 동반 상대강세 확인"
    elif ship.get("confirmed") and defense.get("confirmed"):
        verdict = "🟠 <b>환율 민감 업종 로테이션 확인</b> — 조선·방산 동반 상대강세"
    else:
        confirmed = "조선" if ship.get("confirmed") else "방산"
        verdict = f"🟡 <b>부분 로테이션</b> — {confirmed} 상대강세 우선 확인"

    counter_note = ""
    if counter.get("relative") is not None:
        if float(counter["relative"]) <= COUNTER_RELATIVE_PPT:
            counter_note = "  ↳ 달러비용 민감 업종의 상대약세까지 동반 → 환율 설명력 보강"
        else:
            counter_note = "  ↳ 반대편 업종 상대약세는 뚜렷하지 않음 → 환율 단독 설명은 제한"

    reaction_label = "당일 종가 반응" if after_close else "현재 반응"
    lines = [
        "🔄 <b>환율 민감 업종 로테이션 감지</b>",
        f"<code>{now:%Y-%m-%d %H:%M:%S} KST</code>",
        "",
        verdict,
    ]
    if after_close:
        lines += [
            "• 시점 구분: <b>주식은 정규장 종가 반응</b>, <b>환율은 장마감 후 현재값</b>",
            "  ↳ 장마감 후 환율 추가 상승이 확인된 것이므로 당일 주가 상승을 그 이후 환율 움직임의 결과라고 역으로 단정하지 않음",
        ]
    lines += [
        "",
        "<b>원/달러 반등</b>",
        f"• 표본 장중 저점 <b>{session_low:,.1f}원</b> → 현재 <b>{float(fx['value']):,.1f}원</b>",
        f"• 저점 대비 <b>+{rebound_krw:,.1f}원 (+{rebound_pct:.2f}%)</b>",
    ]
    if daily_krw is not None and daily_pct is not None:
        lines.append(f"• 전일 서울 15:30 종가 대비 <b>{daily_krw:+,.1f}원 ({daily_pct:+.2f}%)</b>")
        if fx.get("basis_reused"):
            lines.append("  ↳ 서울 종가 원천 일시 조회 실패 → 시장 스트레스 감시에서 이미 검증한 동일 공식 기준값 재사용")
    elif fx.get("basis_error"):
        lines.append("• 전일 서울 15:30 종가 조회 실패 → 일간 강한 신호 판정 보류")

    lines += [
        "",
        "<b>업종 상대강도</b>",
        *fmt_stats("조선", ship, float(kospi["change_pct"])),
        *fmt_stats("방산", defense, float(kospi["change_pct"])),
        *fmt_stats("달러비용 민감 업종", counter, float(kospi["change_pct"])),
    ]
    if counter_note:
        lines.append(counter_note)

    lines += [
        "",
        f"<b>조선 {reaction_label}</b>",
        *quote_lines(ship_rows),
        "",
        f"<b>방산 {reaction_label}</b>",
        *quote_lines(defense_rows),
        "",
        "<b>반대편 확인</b>",
        *quote_lines(counter_rows),
        "",
        "<b>해석</b>",
        "• 원/달러 반등은 원화 강세로 약화됐던 수출형 산업재의 환산실적 우려를 완화하는 방향입니다.",
        "• 다만 조선·방산 주가를 환율 하나로 설명하지 않습니다. 수주잔고·신규수주·실적 개선·낙폭 과대·정책/지정학 재료를 별도로 확인합니다.",
        "• 조선은 외화 수주와 환헤지 구조, 방산은 계약통화·환헤지·매출 인식 시점·현지조달 비중에 따라 실제 이익 민감도가 달라집니다.",
        "",
        "<b>무효화 조건</b>",
        "• 원/달러 반등폭이 이번 신호의 50% 이상 반납하거나",
        "• 조선·방산이 모두 KOSPI 대비 상대강도 +1%p를 잃으면 환율 로테이션 신호 약화로 봅니다.",
        "",
        "<b>원문</b>",
        f'• <a href="{html.escape(str(fx["source"]), quote=True)}">원/달러 시세</a>',
        f'• <a href="{html.escape(KOSPI_URL, quote=True)}">KOSPI 시세</a>',
        f'• <a href="{html.escape(TODAY_FX_SOURCE, quote=True)}">환율 반등 사례 확인</a>',
        f'• <a href="{html.escape(TODAY_SHIP_SOURCE, quote=True)}">조선주 반등 사례 확인</a>',
    ]
    if fx.get("prev_close_source"):
        lines.append(f'• <a href="{html.escape(str(fx["prev_close_source"]), quote=True)}">전일 서울 15:30 종가 근거</a>')
    lines += ["", VALIDATION_FOOTER]
    return "\n".join(lines)


def build_weakening_alert(now: dt.datetime, fx: dict[str, Any], state: dict[str, Any], kospi_pct: float,
                          ship: dict[str, Any], defense: dict[str, Any]) -> str:
    sig = state.get("last_signal") or {}
    peak = float(sig.get("rebound_krw") or 0.0)
    low = float(sig.get("session_low") or fx["value"])
    cur_rebound = float(fx["value"]) - low
    return "\n".join([
        "⚠️ <b>환율 민감 업종 로테이션 약화</b>",
        f"<code>{now:%Y-%m-%d %H:%M:%S} KST</code>",
        "",
        f"• 직전 신호 반등폭 <b>+{peak:,.1f}원</b> → 현재 저점 대비 <b>+{cur_rebound:,.1f}원</b>",
        f"• 조선 KOSPI 대비 상대강도: <b>{float(ship.get('relative') or 0):+.2f}%p</b>",
        f"• 방산 KOSPI 대비 상대강도: <b>{float(defense.get('relative') or 0):+.2f}%p</b>",
        f"• KOSPI: <b>{kospi_pct:+.2f}%</b>",
        "• 판정: 환율 반등분 50% 이상 반납 또는 조선·방산 동반 상대강도 소멸 — 직전 로테이션 신호의 설명력이 약해졌습니다.",
        "",
        VALIDATION_FOOTER,
    ])


def write_status(now: dt.datetime, text: str) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(f"# 환율 민감 업종 로테이션\n\n- 조회: {now:%Y-%m-%d %H:%M:%S} KST\n- 상태: {text}\n", encoding="utf-8")


def main() -> int:
    ALERT_PATH.unlink(missing_ok=True)
    now = dt.datetime.now(KST)
    today = now.date().isoformat()
    state = load_state(today)

    if now.weekday() >= 5 or not (START <= now.time() <= END):
        save_pending(state)
        write_status(now, "감시 시간 외 — 평일 09:00~23:59만 감시")
        return 0

    fx = fetch_fx()
    kospi = fetch_kospi()

    samples = list(state.get("fx_samples") or [])
    samples.append({"ts": now.isoformat(timespec="seconds"), "value": float(fx["value"])})
    samples = samples[-80:]
    state["fx_samples"] = samples
    session_low = min(float(x["value"]) for x in samples)
    rebound_krw = float(fx["value"]) - session_low
    rebound_pct = (float(fx["value"]) / session_low - 1.0) * 100 if session_low else 0.0

    daily_krw = None
    daily_pct = None
    if fx.get("prev_close") is not None:
        daily_krw = float(fx["value"]) - float(fx["prev_close"])
        daily_pct = (float(fx["value"]) / float(fx["prev_close"]) - 1.0) * 100

    ship_rows = fetch_group(SHIPBUILDING)
    defense_rows = fetch_group(DEFENSE)
    counter_rows = fetch_group(COUNTER)
    benchmark = float(kospi["change_pct"])
    ship = group_stats(ship_rows, benchmark)
    defense = group_stats(defense_rows, benchmark)
    counter = group_stats(counter_rows, benchmark)

    fx_hit = rebound_krw >= FX_REBOUND_KRW or rebound_pct >= FX_REBOUND_PCT
    strong_fx = bool(
        (daily_krw is not None and daily_krw >= FX_STRONG_KRW)
        or (daily_pct is not None and daily_pct >= FX_STRONG_PCT)
    )
    sectors_confirmed = int(bool(ship.get("confirmed"))) + int(bool(defense.get("confirmed")))

    level = 0
    if fx_hit and sectors_confirmed >= 1:
        level = 1
    if strong_fx and sectors_confirmed >= 2:
        level = 2

    sent_level = int(state.get("sent_level") or 0)
    if level > sent_level:
        ALERT_PATH.write_text(
            build_alert(now, fx, session_low, rebound_krw, rebound_pct, daily_krw, daily_pct,
                        kospi, ship_rows, defense_rows, counter_rows, ship, defense, counter, level) + "\n",
            encoding="utf-8",
        )
        state["sent_level"] = level
        state["sent_weakening"] = False
        state["last_signal"] = {
            "time": now.isoformat(timespec="seconds"),
            "level": level,
            "session_low": session_low,
            "fx_value": float(fx["value"]),
            "rebound_krw": rebound_krw,
            "ship_relative": ship.get("relative"),
            "defense_relative": defense.get("relative"),
            "after_close": now.time() > MARKET_CLOSE,
        }
        write_status(now, f"신규 로테이션 레벨 {level} 감지")
    else:
        sig = state.get("last_signal") or {}
        if sig and not state.get("sent_weakening"):
            peak = float(sig.get("rebound_krw") or 0.0)
            low = float(sig.get("session_low") or session_low)
            cur_rebound = float(fx["value"]) - low
            half_retrace = peak > 0 and cur_rebound <= peak * 0.5
            rel_lost = (
                float(ship.get("relative") or -999) < SECTOR_RELATIVE_PPT
                and float(defense.get("relative") or -999) < SECTOR_RELATIVE_PPT
            )
            if half_retrace or rel_lost:
                ALERT_PATH.write_text(build_weakening_alert(now, fx, state, benchmark, ship, defense) + "\n", encoding="utf-8")
                state["sent_weakening"] = True
                write_status(now, "직전 로테이션 신호 약화")
            else:
                write_status(now, "신규 상향 신호 없음")
        else:
            write_status(now, "신규 상향 신호 없음")

    state["latest"] = {
        "checked_at": now.isoformat(timespec="seconds"),
        "market_phase": "장마감 후" if now.time() > MARKET_CLOSE else "정규장",
        "fx": fx,
        "session_low": session_low,
        "rebound_krw": rebound_krw,
        "rebound_pct": rebound_pct,
        "daily_krw": daily_krw,
        "daily_pct": daily_pct,
        "kospi_pct": benchmark,
        "ship": ship,
        "defense": defense,
        "counter": counter,
    }
    save_pending(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())