#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import html
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests

KST = ZoneInfo("Asia/Seoul")
STATE_PATH = Path("data/kospi_derivatives_flow_state.json")
ALERT_PATH = Path("out/kospi_derivatives_flow_alert.html")
STATUS_PATH = Path("out/kospi_derivatives_flow_status.md")
ERROR_PATH = Path("out/kospi_derivatives_flow_errors.log")

POLLING_URL = "https://polling.finance.naver.com/api/realtime?query=SERVICE_INDEX:KOSPI,KPI200"
KOSPI_BASIC_URL = "https://m.stock.naver.com/api/index/KOSPI/basic"
KPI200_BASIC_URL = "https://m.stock.naver.com/api/index/KPI200/basic"
KRX_WEEKLY_URL = "https://global.krx.co.kr/contents/GLB/02/0201/0201040202/GLB0201040202.jsp"
KRX_UPTICK_URL = "https://data.krx.co.kr/contents/MDC/STAT/srt/MDCSTAT317.jsp"
KRX_SHORT_URL = "https://data.krx.co.kr/contents/MDC/STAT/srt/MDCSTAT300.jsp"
KOSPI_PAGE = "https://m.stock.naver.com/domestic/index/KOSPI/total"
KPI200_PAGE = "https://m.stock.naver.com/domestic/index/KPI200/total"
NEWS_URL = "https://search.naver.com/search.naver?where=news&query=" + quote("코스피 급락")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; khs-watch/1.0)",
    "Accept": "application/json,text/plain,*/*",
}
WINDOW_START = dt.time(13, 45)
WINDOW_END = dt.time(15, 25)
DROP_10M_PCT = -1.50
DRAWDOWN_15M_PCT = -2.00
REBOUND_PCT = 1.20
EPISODE_TTL_MIN = 60


def num(v: Any) -> float:
    if v is None:
        raise ValueError("missing numeric value")
    return float(str(v).replace(",", "").strip())


def scaled(v: Any) -> float:
    x = num(v)
    return x / 100.0 if abs(x) > 20000 else x


def fetch_basic(code: str) -> dict[str, Any]:
    url = KOSPI_BASIC_URL if code == "KOSPI" else KPI200_BASIC_URL
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    d = r.json()
    price = num(d.get("closePrice"))
    return {
        "code": code,
        "price": price,
        "open": num(d.get("openPrice") or price),
        "high": num(d.get("highPrice") or price),
        "low": num(d.get("lowPrice") or price),
        "change_pct": num(d.get("fluctuationsRatio") or 0),
        "market_status": str(d.get("marketStatus") or ""),
    }


def fetch_quote() -> dict[str, Any]:
    try:
        r = requests.get(POLLING_URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
        payload = r.json()
        areas = ((payload or {}).get("result") or {}).get("areas") or []
        datas: list[dict[str, Any]] = []
        for area in areas:
            datas.extend(area.get("datas") or [])
        by_code = {str(d.get("cd") or "").upper(): d for d in datas}
        if "KOSPI" not in by_code:
            raise RuntimeError(f"KOSPI missing; codes={list(by_code)}")

        def one(code: str) -> dict[str, Any] | None:
            d = by_code.get(code)
            if not d:
                return None
            return {
                "code": code,
                "price": scaled(d.get("nv")),
                "open": scaled(d.get("ov")),
                "high": scaled(d.get("hv")),
                "low": scaled(d.get("lv")),
                "change_pct": num(d.get("cr") or 0),
                "market_status": str(d.get("ms") or ""),
            }

        return {
            "kospi": one("KOSPI"),
            "kpi200": one("KPI200") or fetch_basic("KPI200"),
            "source_label": "네이버페이 증권 실시간 지수 폴링",
        }
    except Exception as first:
        try:
            return {
                "kospi": fetch_basic("KOSPI"),
                "kpi200": fetch_basic("KPI200"),
                "source_label": "네이버페이 증권 지수 기본 시세",
                "fallback_reason": f"{type(first).__name__}: {first}",
            }
        except Exception:
            raise first


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"date": None, "samples": [], "episode": None, "last_alert_keys": []}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"date": None, "samples": [], "episode": None, "last_alert_keys": []}


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def pct(a: float, b: float) -> float:
    return (b / a - 1.0) * 100.0 if a else 0.0


def parse_ts(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s)


def nearest_sample(samples: list[dict[str, Any]], now: dt.datetime, minutes: int) -> dict[str, Any] | None:
    target = now - dt.timedelta(minutes=minutes)
    candidates = []
    for s in samples[:-1]:
        try:
            t = parse_ts(str(s["time"]))
        except Exception:
            continue
        age = (now - t).total_seconds() / 60.0
        if 5 <= age <= 25:
            candidates.append((abs((t - target).total_seconds()), s))
    return min(candidates, default=(None, None), key=lambda x: x[0])[1]


def recent_high(samples: list[dict[str, Any]], now: dt.datetime) -> float | None:
    vals = []
    for s in samples:
        try:
            t = parse_ts(str(s["time"]))
        except Exception:
            continue
        age = (now - t).total_seconds() / 60.0
        if 0 <= age <= 20:
            vals.append(float(s["kospi"]))
    return max(vals) if vals else None


def expiry_label(now: dt.datetime) -> tuple[bool, str]:
    if now.weekday() == 0:
        return True, "월요일 KOSPI200 위클리옵션 만기"
    if now.weekday() == 3:
        if (now.day - 1) // 7 + 1 == 2:
            return True, "둘째 목요일 KOSPI200 정규 월물 만기(위클리 미상장)"
        return True, "목요일 KOSPI200 위클리옵션 만기"
    return False, "정규 월·목 파생 만기일 아님"


def link(url: str, label: str) -> str:
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'


def fmt_move(value: float | None) -> str:
    return "계산 대기" if value is None else f"{value:+.2f}%"


def build_shock_alert(
    now: dt.datetime,
    quote: dict[str, Any],
    p10: float | None,
    dd15: float | None,
    expiry: bool,
    expiry_text: str,
) -> str:
    k = quote["kospi"]
    k2 = quote.get("kpi200")

    reasons = []
    if p10 is not None and p10 <= DROP_10M_PCT:
        reasons.append(f"10분 변화 <b>{p10:+.2f}%</b> → 기준 {DROP_10M_PCT:.2f}% 하회")
    if dd15 is not None and dd15 <= DRAWDOWN_15M_PCT:
        reasons.append(f"최근 15분 고점 대비 <b>{dd15:+.2f}%</b> → 기준 {DRAWDOWN_15M_PCT:.2f}% 하회")

    if expiry:
        verdict = "🔴 <b>급락 + 파생 만기 중첩</b> — 만기·헤지·차익거래가 변동성을 키웠는지 확인"
        meaning = "월·목 만기 오후에는 옵션 감마·선물 헤지·차익거래 청산이 현물 움직임을 증폭할 수 있습니다."
    else:
        verdict = "🔴 <b>단기 급락 감지</b> — 만기 직접 영향보다 뉴스·현물 수급 원인을 우선 확인"
        meaning = "정규 월·목 파생 만기일이 아니므로 새 뉴스, 대형주 급락, 현물·선물 수급 변화를 먼저 확인합니다."

    lines = [
        "🚨 <b>코스피 파생·수급 급변 경보</b>",
        f"<code>{now:%Y-%m-%d %H:%M:%S} KST</code>",
        "",
        "<b>판정</b>",
        verdict,
        f"• 파생 일정: <b>{expiry_text}</b>",
        "• <b>원인 확인 전 단순 손절·저가매수 신호로 해석하지 않음</b>",
        "",
        "<b>현재 움직임</b>",
        f"• KOSPI <b>{k['price']:,.2f}</b>  |  당일 <b>{k['change_pct']:+.2f}%</b>",
        f"• 10분 <b>{fmt_move(p10)}</b>  |  15분 고점 대비 <b>{fmt_move(dd15)}</b>",
    ]
    if k2:
        lines.append(f"• KOSPI200 <b>{k2['price']:,.2f}</b>  |  당일 <b>{k2['change_pct']:+.2f}%</b>")

    lines += [
        "",
        "<b>왜 경보가 울렸나</b>",
        *[f"• {reason}" for reason in reasons],
        "",
        "<b>해석</b>",
        f"• {meaning}",
        "• 다만 이 경보만으로 <b>펀더멘털 악재·불법 시세조종·업틱룰 예외 공매도</b>를 원인으로 확정하지 않습니다.",
        "• 이후 급반등이 나오면 별도 <b>되돌림 경보</b>로 일시적 수급 충격 가능성을 다시 판정합니다.",
        "",
        "<b>바로 확인</b>",
        "• " + " · ".join([
            link(KOSPI_PAGE, "KOSPI 실시간"),
            link(KPI200_PAGE, "KOSPI200"),
            link(NEWS_URL, "급락 뉴스"),
        ]),
        "• " + " · ".join([
            link(KRX_WEEKLY_URL, "KRX 옵션 규정"),
            link(KRX_UPTICK_URL, "KRX 업틱룰"),
            link(KRX_SHORT_URL, "KRX 공매도"),
        ]),
        "",
        f"• 시세 출처: {html.escape(quote.get('source_label', '네이버페이 증권'))}",
        "• KRX 기준: 위클리옵션은 월·목 만기. 둘째 목요일은 정규 월물과 겹쳐 위클리 계약이 상장되지 않음.",
    ]
    return "\n".join(lines) + "\n"


def build_rebound_alert(now: dt.datetime, quote: dict[str, Any], episode: dict[str, Any], rebound: float) -> str:
    k = quote["kospi"]
    k2 = quote.get("kpi200")
    low = float(episode["low"])

    lines = [
        "🟢 <b>코스피 급변동 되돌림 확인</b>",
        f"<code>{now:%Y-%m-%d %H:%M:%S} KST</code>",
        "",
        "<b>판정</b>",
        f"🟢 저점 대비 <b>{rebound:+.2f}%</b> 회복 — 일시적 수급 충격 가능성 상승",
        "• 새 펀더멘털 악재가 확인되지 않는다면 만기·헤지·차익거래성 급락 가능성이 이전보다 높아진 패턴",
        "",
        "<b>현재 움직임</b>",
        f"• KOSPI 저점 <b>{low:,.2f}</b> → 현재 <b>{k['price']:,.2f}</b>",
        f"• 저점 대비 <b>{rebound:+.2f}%</b>  |  당일 <b>{k['change_pct']:+.2f}%</b>",
    ]
    if k2:
        lines.append(f"• KOSPI200 <b>{k2['price']:,.2f}</b>  |  당일 <b>{k2['change_pct']:+.2f}%</b>")

    lines += [
        "",
        "<b>되돌림 기준</b>",
        f"• 급락 구간 저점 대비 <b>+{REBOUND_PCT:.2f}% 이상</b> 회복",
        "",
        "<b>해석</b>",
        "• 급반등은 펀더멘털 악화보다 수급성 충격이었다는 정황을 강화하지만 <b>원인을 확정하지는 않습니다.</b>",
        "• 뉴스·선물·프로그램 매매·공매도 최종 자료를 함께 확인합니다.",
        "",
        "<b>바로 확인</b>",
        "• " + " · ".join([
            link(KOSPI_PAGE, "KOSPI 실시간"),
            link(NEWS_URL, "급락 뉴스"),
            link(KRX_WEEKLY_URL, "KRX 옵션 규정"),
            link(KRX_SHORT_URL, "KRX 공매도"),
        ]),
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    now = dt.datetime.now(KST)
    ALERT_PATH.parent.mkdir(parents=True, exist_ok=True)
    for p in (ALERT_PATH, STATUS_PATH, ERROR_PATH):
        if p.exists():
            p.unlink()

    state = load_state()
    today = now.date().isoformat()
    if state.get("date") != today:
        state = {"date": today, "samples": [], "episode": None, "last_alert_keys": []}

    if now.weekday() >= 5 or not (WINDOW_START <= now.time() <= WINDOW_END):
        save_state(state)
        STATUS_PATH.write_text(
            f"# 코스피 파생·수급 이상변동 감시\n\n"
            f"- 상태: 감시 시간 외\n"
            f"- 조회: {now:%Y-%m-%d %H:%M:%S} KST\n"
            f"- 감시창: 평일 13:45~15:25 KST\n",
            encoding="utf-8",
        )
        return 0

    try:
        quote = fetch_quote()
        k = quote["kospi"]
        samples = list(state.get("samples") or [])
        samples.append({
            "time": now.isoformat(timespec="seconds"),
            "kospi": round(float(k["price"]), 4),
            "kpi200": round(float((quote.get("kpi200") or {}).get("price") or 0), 4),
        })

        cutoff = now - dt.timedelta(minutes=120)
        kept = []
        for s in samples:
            try:
                if parse_ts(str(s["time"])) >= cutoff:
                    kept.append(s)
            except Exception:
                pass
        samples = kept[-40:]
        state["samples"] = samples

        base10 = nearest_sample(samples, now, 10)
        p10 = pct(float(base10["kospi"]), float(k["price"])) if base10 else None
        hi15 = recent_high(samples, now)
        dd15 = pct(float(hi15), float(k["price"])) if hi15 else None
        expiry, expiry_text = expiry_label(now)
        shock = (
            (p10 is not None and p10 <= DROP_10M_PCT)
            or (dd15 is not None and dd15 <= DRAWDOWN_15M_PCT)
        )
        episode = state.get("episode")
        last_keys = list(state.get("last_alert_keys") or [])[-30:]

        if shock:
            if not episode:
                episode = {
                    "started_at": now.isoformat(timespec="seconds"),
                    "low": float(k["price"]),
                    "shock_alerted": False,
                    "rebound_alerted": False,
                }
            episode["low"] = min(float(episode.get("low") or k["price"]), float(k["price"]))
            key = f"shock:{today}:{episode['started_at'][:16]}"
            if not episode.get("shock_alerted") and key not in last_keys:
                ALERT_PATH.write_text(
                    build_shock_alert(now, quote, p10, dd15, expiry, expiry_text),
                    encoding="utf-8",
                )
                episode["shock_alerted"] = True
                last_keys.append(key)
            state["episode"] = episode

        elif episode:
            try:
                started = parse_ts(str(episode["started_at"]))
                age_min = (now - started).total_seconds() / 60.0
            except Exception:
                age_min = EPISODE_TTL_MIN + 1

            episode["low"] = min(float(episode.get("low") or k["price"]), float(k["price"]))
            rebound = pct(float(episode["low"]), float(k["price"]))
            key = f"rebound:{today}:{episode.get('started_at', '')[:16]}"
            if (
                episode.get("shock_alerted")
                and not episode.get("rebound_alerted")
                and rebound >= REBOUND_PCT
                and age_min <= EPISODE_TTL_MIN
                and key not in last_keys
            ):
                ALERT_PATH.write_text(
                    build_rebound_alert(now, quote, episode, rebound),
                    encoding="utf-8",
                )
                episode["rebound_alerted"] = True
                last_keys.append(key)
            state["episode"] = (
                None
                if age_min > EPISODE_TTL_MIN or episode.get("rebound_alerted")
                else episode
            )

        state["last_alert_keys"] = last_keys[-30:]
        save_state(state)
        STATUS_PATH.write_text(
            "# 코스피 파생·수급 이상변동 감시\n\n"
            f"- 조회: {now:%Y-%m-%d %H:%M:%S} KST\n"
            f"- KOSPI: {k['price']:,.2f} ({k['change_pct']:+.2f}%)\n"
            f"- 10분 변화: {fmt_move(p10)}\n"
            f"- 최근 15분 고점 대비: {fmt_move(dd15)}\n"
            f"- 파생 일정: {expiry_text}\n"
            f"- 경보 생성: {'예' if ALERT_PATH.exists() else '아니오'}\n"
            f"- 시세 출처: {quote.get('source_label')}\n",
            encoding="utf-8",
        )
        return 0
    except Exception as exc:
        ERROR_PATH.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        STATUS_PATH.write_text(
            f"# 코스피 파생·수급 이상변동 감시\n\n- 조회 실패: {type(exc).__name__}: {exc}\n",
            encoding="utf-8",
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
