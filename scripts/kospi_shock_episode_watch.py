#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
from collections import defaultdict, deque
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import ebest
import requests

KST = ZoneInfo("Asia/Seoul")
BASE = "https://openapi.ls-sec.co.kr:8080"
STATUS = Path("out/kospi_shock_episode_status.md")
RAW = Path("out/kospi_shock_episode_raw.json")
KOSPI_URL = "https://m.stock.naver.com/domestic/index/KOSPI/total"
LS_URL = "https://openapi.ls-sec.co.kr/apiservice"
NEWS_URL = "https://search.naver.com/search.naver?where=news&query=" + urllib.parse.quote("코스피 급락")

PRICE_LOOKBACK_SEC = 3 * 60 * 60
FLOW_LOOKBACK_SEC = 4 * 60 * 60
FLOW_INTERVAL_SEC = 10
NEW_LOW_CONFIRM_SEC = 240
MAX_EPISODE_SEC = 3 * 60 * 60


def fnum(v: Any) -> float | None:
    try:
        if v is None or str(v).strip() == "":
            return None
        return float(str(v).replace(",", "").strip())
    except Exception:
        return None


def pct(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or a == 0:
        return None
    return (b / a - 1.0) * 100.0


def fmt_clock(ts: float | None) -> str:
    if ts is None:
        return "확인 불가"
    return dt.datetime.fromtimestamp(ts, KST).strftime("%H:%M:%S")


def fmt_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}시간 {m}분 {s}초"
    return f"{m}분 {s}초"


def link(url: str, label: str) -> str:
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'


def telegram_send(text: str) -> int:
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = ((os.getenv("TELEGRAM_CHAT_ID_PRIMARY") or "").strip()
               or (os.getenv("TELEGRAM_CHAT_ID_FALLBACK") or "").strip())
    expected = (os.getenv("EXPECTED_TELEGRAM_BOT_USERNAME") or "").strip().lstrip("@")
    if not token or not chat_id:
        raise RuntimeError("Telegram token/chat id missing")
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getMe", timeout=20) as r:
        ident = json.loads(r.read().decode("utf-8"))
    actual = str((ident.get("result") or {}).get("username") or "")
    if not ident.get("ok") or (expected and actual.lower() != expected.lower()):
        raise RuntimeError(f"Wrong Telegram bot: expected @{expected}, got @{actual or 'unknown'}")
    payload = urllib.parse.urlencode({
        "chat_id": chat_id, "text": text, "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=payload, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        out = json.loads(r.read().decode("utf-8"))
    if not out.get("ok"):
        raise RuntimeError(f"Telegram rejected message: {out}")
    return int(out["result"]["message_id"])


def get_token() -> str:
    key = (os.getenv("LS_OPENAPI_APP_KEY") or "").strip()
    secret = (os.getenv("LS_OPENAPI_APP_SECRET") or "").strip()
    if not key or not secret:
        raise RuntimeError("LS secrets missing")
    r = requests.post(
        BASE + "/oauth2/token",
        headers={"content-type": "application/x-www-form-urlencoded"},
        params={"grant_type": "client_credentials", "appkey": key,
                "appsecretkey": secret, "scope": "oob"}, timeout=30)
    r.raise_for_status()
    tok = str(r.json().get("access_token") or "").strip()
    if not tok:
        raise RuntimeError("LS access token issue failed")
    return tok


def ls_post(token: str, path: str, tr: str, body: dict[str, Any]) -> dict[str, Any]:
    r = requests.post(
        BASE + path,
        headers={"content-type": "application/json; charset=utf-8",
                 "authorization": "Bearer " + token, "tr_cd": tr,
                 "tr_cont": "N", "tr_cont_key": ""},
        data=json.dumps(body), timeout=20)
    if not r.ok:
        raise RuntimeError(f"{tr} HTTP {r.status_code}: {(r.text or '')[:250]}")
    d = r.json()
    code = str(d.get("rsp_cd") or "")
    if code and code not in {"00000", "0000"}:
        raise RuntimeError(f"{tr} rejected {code}: {d.get('rsp_msg')}")
    return d


def _latest_time_row(rows: Any) -> dict[str, Any] | None:
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list):
        return None
    valid = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        s = "".join(c for c in str(row.get("time") or "") if c.isdigit())
        if len(s) >= 6:
            valid.append((s[:6], row))
    return max(valid, key=lambda x: x[0])[1] if valid else None


def investor_current(token: str, market: str, upcode: str) -> dict[str, Any] | None:
    body = {"t1602InBlock": {"market": market, "upcode": upcode,
            "gubun1": "2", "gubun2": "0", "cts_time": "", "cts_idx": 0,
            "cnt": 100, "gubun3": "", "exchgubun": "K"}}
    d = ls_post(token, "/stock/investor", "t1602", body)
    row = _latest_time_row(d.get("t1602OutBlock1"))
    if not row:
        return None
    return {"time": row.get("time"), "개인": fnum(row.get("sv_08")),
            "외국인": fnum(row.get("sv_17")), "기관": fnum(row.get("sv_18"))}


def _program_mini(token: str, gubun: str) -> dict[str, Any] | None:
    # t1640: 11=거래소 전체, 12=거래소 차익, 13=거래소 비차익.
    d = ls_post(token, "/stock/program", "t1640", {"t1640InBlock": {"gubun": gubun, "exchgubun": "K"}})
    row = d.get("t1640OutBlock")
    return row if isinstance(row, dict) and row else None


def program_current(token: str) -> dict[str, Any] | None:
    # t1632의 '최신 행'을 누적값처럼 차감하지 않는다.
    # t1640 누적 스냅샷 3종을 동일 시점에 조회해 사건 시작→저점 차이를 계산한다.
    total = _program_mini(token, "11")
    time.sleep(1.05)
    arb = _program_mini(token, "12")
    time.sleep(1.05)
    nonarb = _program_mini(token, "13")
    if not total and not arb and not nonarb:
        return None
    return {
        "time": dt.datetime.now(KST).strftime("%H%M%S"),
        "전체": fnum((total or {}).get("value")),
        "차익": fnum((arb or {}).get("value")),
        "비차익": fnum((nonarb or {}).get("value")),
        "베이시스": fnum((total or {}).get("basis")),
        "전체_순매수증감": fnum((total or {}).get("sunvaldiff") or (total or {}).get("sundiff")),
    }


def fetch_flow_snapshot(token: str) -> dict[str, Any]:
    snap: dict[str, Any] = {"ts": time.time(), "errors": {}}
    for key, market, upcode in (("현물", "1", "001"), ("선물", "4", "900")):
        try:
            snap[key] = investor_current(token, market, upcode)
        except Exception as exc:
            snap[key] = None
            snap["errors"][key] = f"{type(exc).__name__}: {exc}"
        time.sleep(1.05)
    try:
        snap["프로그램"] = program_current(token)
    except Exception as exc:
        snap["프로그램"] = None
        snap["errors"]["프로그램"] = f"{type(exc).__name__}: {exc}"
    return snap


def fetch_kpi200() -> float | None:
    try:
        r = requests.get("https://m.stock.naver.com/api/index/KPI200/basic",
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        r.raise_for_status()
        return fnum(r.json().get("closePrice"))
    except Exception:
        return None


def get_weekly_puts(token: str, current: float | None, limit: int = 5) -> list[dict[str, Any]]:
    try:
        d = ls_post(token, "/futureoption/market-data", "t8435", {"t8435InBlock": {"gubun": "WK"}})
        rows = d.get("t8435OutBlock") or []
    except Exception:
        return []
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("hname") or "").strip()
        code = str(row.get("shcode") or "").strip()
        if not code or not re.match(r"^P(?:\s|$)", name, re.I):
            continue
        m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*$", name)
        strike = fnum(m.group(1)) if m else fnum(row.get("recprice"))
        if strike is None:
            continue
        out.append({"code": code, "name": name, "strike": strike})
    if current is not None:
        out.sort(key=lambda x: abs(float(x["strike"]) - current))
    return out[:limit]


def _actor_delta(start: dict[str, Any] | None, end: dict[str, Any] | None) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for actor in ("외국인", "기관", "개인"):
        a = fnum((start or {}).get(actor)); b = fnum((end or {}).get(actor))
        out[actor] = (b - a) if a is not None and b is not None else None
    return out


def _program_delta(start: dict[str, Any] | None, end: dict[str, Any] | None) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for k in ("전체", "차익", "비차익", "베이시스"):
        a = fnum((start or {}).get(k)); b = fnum((end or {}).get(k))
        out[k] = (b - a) if a is not None and b is not None else None
    return out


def fmt_eok(v: float | None) -> str:
    if v is None:
        return "확인 불가"
    return f"{v:+,.0f}억원"


def fmt_raw(v: float | None) -> str:
    if v is None:
        return "확인 불가"
    return f"{v:+,.0f}"


class Watch:
    def __init__(self, api: ebest.OpenApi, token: str, puts: list[dict[str, Any]], test: bool):
        self.api = api; self.token = token; self.put_defs = puts; self.test = test
        self.idx: deque[tuple[float, float]] = deque(maxlen=30000)
        self.fut: deque[tuple[float, float]] = deque(maxlen=30000)
        self.puts: dict[str, deque[tuple[float, float]]] = defaultdict(lambda: deque(maxlen=30000))
        self.flows: deque[dict[str, Any]] = deque(maxlen=2500)
        self.front_future = ""; self.episode: dict[str, Any] | None = None
        self.last_flow_poll = 0.0; self.flow_task: asyncio.Task | None = None
        self.msg_ids: list[int] = []; self.raw: dict[str, Any] = {}
        self.monitor_started_ts = time.time()
        self.last_idx_tick_ts: float | None = None
        self.last_fut_tick_ts: float | None = None
        self.last_flow_success_ts: float | None = None

    @staticmethod
    def _nearest(buf: deque[tuple[float, float]], ts: float) -> tuple[float, float] | None:
        return min(buf, key=lambda x: abs(x[0] - ts)) if buf else None

    def _ret(self, minutes: int) -> float | None:
        if not self.idx:
            return None
        cur_t, cur = self.idx[-1]
        p = self._nearest(self.idx, cur_t - minutes * 60)
        if not p or cur_t - p[0] < minutes * 60 * 0.65:
            return None
        return pct(p[1], cur)

    def _recent_peak(self, seconds: int = PRICE_LOOKBACK_SEC) -> tuple[float, float] | None:
        if not self.idx:
            return None
        cutoff = self.idx[-1][0] - seconds
        rows = [x for x in self.idx if x[0] >= cutoff]
        if not rows:
            return None
        high = max(v for _, v in rows)
        candidates = [x for x in rows if x[1] == high]
        return candidates[-1]

    def _window_peak(self, minutes: int, pad_minutes: int) -> tuple[float, float] | None:
        if not self.idx:
            return None
        now_t = self.idx[-1][0]
        cutoff = now_t - (minutes + pad_minutes) * 60
        rows = [x for x in self.idx if x[0] >= cutoff]
        if not rows:
            return None
        high = max(v for _, v in rows)
        # 같은 고점이 여러 번이면 급락 직전의 마지막 고점을 사용한다.
        return [x for x in rows if x[1] == high][-1]

    def _trigger(self) -> tuple[bool, dict[str, Any]]:
        if len(self.idx) < 2:
            return False, {}
        now_t, cur = self.idx[-1]
        returns = {m: self._ret(m) for m in (5, 10, 15, 30, 60)}
        # 가장 짧은 시간창부터 검사한다. 따라서 오전 세션고점이 아니라
        # 실제 급락 직전 국소고점이 사건 시작점으로 우선 선택된다.
        rules = [
            (5, -0.35, 2),
            (10, -0.55, 3),
            (15, -0.70, 5),
            (20, -0.90, 5),
            (30, -1.00, 7),
            (45, -1.10, 10),
            (60, -1.20, 10),
            (90, -1.30, 15),
            (120, -1.40, 20),
            (180, -1.50, 20),
        ]
        for window, threshold, pad in rules:
            peak = self._window_peak(window, pad)
            if not peak:
                continue
            duration = now_t - peak[0]
            if duration <= 0:
                continue
            drop = pct(peak[1], cur)
            if drop is None or drop > threshold:
                continue

            # 30분 이상 구간은 최근에도 하락 압력이 살아 있어야 사건으로 인정한다.
            active = True
            if window > 20 and window <= 60:
                active = any(
                    returns.get(m) is not None and returns[m] <= lim
                    for m, lim in ((10, -0.20), (15, -0.30), (30, -0.45))
                )
            elif window > 60:
                # 몇 시간짜리 완만한 하락은 급락 사건으로 보지 않는다.
                # 장시간 누적 낙폭에 더해 최근 15~60분 하락 가속이 확인돼야 한다.
                active = any(
                    returns.get(m) is not None and returns[m] <= lim
                    for m, lim in ((15, -0.55), (30, -0.70), (60, -0.90))
                )
            if not active:
                continue

            return True, {
                "peak_ts": peak[0], "peak": peak[1],
                "cur_ts": now_t, "cur": cur,
                "drop": drop, "duration": duration,
                "threshold": threshold, "window_minutes": window,
                "r5": returns.get(5), "r10": returns.get(10),
                "r15": returns.get(15), "r30": returns.get(30),
                "r60": returns.get(60),
            }
        return False, {}

    def _flow_near(self, ts: float, prefer_before: bool = True) -> dict[str, Any] | None:
        rows = list(self.flows)
        if not rows:
            return None
        if prefer_before:
            prior = [x for x in rows if float(x.get("ts", 0)) <= ts]
            if prior:
                return max(prior, key=lambda x: float(x.get("ts", 0)))
        return min(rows, key=lambda x: abs(float(x.get("ts", 0)) - ts))

    def attribution(self, start_ts: float, end_ts: float) -> dict[str, Any]:
        a = self._flow_near(start_ts, True); b = self._flow_near(end_ts, True)
        if not a or not b:
            return {"available": False}
        spot = _actor_delta(a.get("현물"), b.get("현물"))
        fut = _actor_delta(a.get("선물"), b.get("선물"))
        pgm = _program_delta(a.get("프로그램"), b.get("프로그램"))
        def dominant_seller(block: dict[str, float | None]) -> tuple[str | None, float | None]:
            sellers = [(actor, val) for actor, val in block.items() if val is not None and float(val) < 0]
            return min(sellers, key=lambda x: float(x[1])) if sellers else (None, None)

        spot_leader, spot_leader_val = dominant_seller(spot)
        fut_leader, fut_leader_val = dominant_seller(fut)
        cross_sellers = [actor for actor in ("외국인", "기관", "개인")
                         if spot.get(actor) is not None and fut.get(actor) is not None
                         and float(spot[actor]) < 0 and float(fut[actor]) < 0]
        pgm_neg = pgm.get("전체") is not None and float(pgm["전체"]) < 0

        # '두 시장 모두 음수'와 '두 시장을 주도'를 구분한다.
        # 현물/선물의 최다 매도자가 같을 때만 단일 주체 주도로 올린다.
        if spot_leader and spot_leader == fut_leader:
            if pgm_neg:
                verdict = f"{spot_leader}가 현물·선물 모두 최다 매도이고 프로그램 매도도 동반 — 주도 가능성 높음"
                confidence = "높음"
            else:
                verdict = f"{spot_leader}가 현물·선물 모두 최다 매도 — 주도 후보지만 프로그램 동조는 약함"
                confidence = "중간"
        elif spot_leader and fut_leader and spot_leader != fut_leader:
            verdict = f"현물은 {spot_leader}, 선물은 {fut_leader}가 최다 매도 — 주체 분산, 단일 주도자 확정 보류"
            confidence = "낮음" if not pgm_neg else "중간"
        elif fut_leader and pgm_neg:
            verdict = f"{fut_leader} 선물 최다 매도와 프로그램 매도가 동반 — 파생발 하락 전이 가능성 확인"
            confidence = "중간"
        else:
            verdict = "현물·선물·프로그램이 한 주체로 정렬되지 않아 단일 매도주체 확정 보류"
            confidence = "낮음"
        pgm_kind = "확인 불가"
        if pgm.get("전체") is not None:
            if float(pgm["전체"]) < 0:
                av, nv = pgm.get("차익"), pgm.get("비차익")
                if av is not None and nv is not None:
                    pgm_kind = "비차익 매도 우세" if nv < av else "차익 매도 우세"
                else:
                    pgm_kind = "프로그램 매도"
            elif float(pgm["전체"]) > 0:
                pgm_kind = "프로그램 매수"
            else:
                pgm_kind = "중립"
        return {"available": True, "start_ts": a.get("ts"), "end_ts": b.get("ts"),
                "spot": spot, "futures": fut, "program": pgm,
                "spot_leader": spot_leader, "spot_leader_value": spot_leader_val,
                "futures_leader": fut_leader, "futures_leader_value": fut_leader_val,
                "cross_sellers": cross_sellers,
                "verdict": verdict, "confidence": confidence, "program_kind": pgm_kind}

    def option_move(self, start_ts: float, end_ts: float) -> tuple[str, float] | None:
        best = None
        for opt in self.put_defs:
            b = self.puts.get(opt["code"])
            if not b:
                continue
            a = self._nearest(b, start_ts); z = self._nearest(b, end_ts)
            if not a or not z or a[1] <= 0:
                continue
            mult = z[1] / a[1]
            if best is None or mult > best[1]:
                best = (opt["name"], mult)
        return best

    def build_alert(self, stage: str, ep: dict[str, Any], end_ts: float, end_price: float) -> str:
        att = self.attribution(float(ep["start_ts"]), end_ts)
        drop = pct(float(ep["start_price"]), end_price) or 0.0
        title = "🚨 <b>코스피 급락 사건구간 포착</b>" if stage == "start" else "🔴 <b>코스피 급락 사건구간 확대</b>"
        lines = [title, f"<code>{dt.datetime.now(KST):%Y-%m-%d %H:%M:%S} KST</code>", "",
                 "<b>급락 구간</b>",
                 f"• 시작 <b>{fmt_clock(ep['start_ts'])}</b> → 현재 <b>{fmt_clock(end_ts)}</b> · {fmt_duration(end_ts-float(ep['start_ts']))}",
                 f"• KOSPI <b>{float(ep['start_price']):,.2f}</b> → <b>{end_price:,.2f}</b> · <b>{drop:+.2f}%</b>",
                 f"• 현재 구간 저점 <b>{float(ep['low_price']):,.2f}</b> ({fmt_clock(ep['low_ts'])})", "",
                 "<b>그 구간에서 누가 팔았나</b>"]
        if float(ep["start_ts"]) - self.monitor_started_ts < 15 * 60:
            lines += ["⚠️ <b>감시 시작 직후 포착</b> — 실제 급락 시작점이 이보다 앞설 수 있어 시작시각 확신도를 낮춥니다.", ""]
        if att.get("available"):
            s, f, p = att["spot"], att["futures"], att["program"]
            cross = ", ".join(att.get("cross_sellers") or []) or "없음"
            lines += [f"• 현물: 외국인 <b>{fmt_eok(s.get('외국인'))}</b> · 기관 <b>{fmt_eok(s.get('기관'))}</b> · 개인 <b>{fmt_eok(s.get('개인'))}</b>",
                      f"• KOSPI200 선물: 외국인 <b>{fmt_eok(f.get('외국인'))}</b> · 기관 <b>{fmt_eok(f.get('기관'))}</b> · 개인 <b>{fmt_eok(f.get('개인'))}</b>",
                      f"• 현물 최다매도: <b>{html.escape(str(att.get('spot_leader') or '없음'))}</b> {fmt_eok(att.get('spot_leader_value'))}",
                      f"• 선물 최다매도: <b>{html.escape(str(att.get('futures_leader') or '없음'))}</b> {fmt_eok(att.get('futures_leader_value'))}",
                      f"• 양시장 동시매도: <b>{html.escape(cross)}</b>",
                      f"• 프로그램 전체 <b>{fmt_raw(p.get('전체'))}</b> · 차익 <b>{fmt_raw(p.get('차익'))}</b> · 비차익 <b>{fmt_raw(p.get('비차익'))}</b> <i>(LS t1640 누적값 변화)</i>",
                      f"• 프로그램 방향: <b>{html.escape(str(att.get('program_kind')))}</b>", "",
                      "<b>판정</b>", f"• <b>{html.escape(str(att.get('verdict')))}</b> · 확신도 {html.escape(str(att.get('confidence')))}"]
        else:
            lines += ["• 사건 시작 직전 수급 스냅샷이 부족해 주체 판정 보류"]
        opt = self.option_move(float(ep["start_ts"]), end_ts)
        if opt:
            lines += ["", "<b>파생 증폭 확인</b>", f"• 근접 위클리 풋 <b>{html.escape(opt[0])}</b> · 사건 시작 대비 <b>{opt[1]:.1f}배</b>"]
        lines += ["", "<b>읽는 법</b>",
                  "• 하루 누적 수급이 아니라 <b>급락 시작 직전 → 현재</b> 변화량만 비교합니다.",
                  "• 현물·선물·프로그램이 같은 방향으로 겹칠 때만 특정 주체를 급락 주도 후보로 올립니다.",
                  "• 프로그램은 LS t1640 누적 스냅샷(전체·차익·비차익)의 사건 시작→현재 변화로 계산하며, 단위는 임의 환산하지 않습니다.", "",
                  "• " + " · ".join([link(KOSPI_URL,"KOSPI"), link(NEWS_URL,"급락 뉴스"), link(LS_URL,"LS OpenAPI")])]
        return "\n".join(lines)

    def build_end(self, ep: dict[str, Any], end_ts: float, end_price: float) -> str:
        att = self.attribution(float(ep["start_ts"]), float(ep["low_ts"]))
        drop = pct(float(ep["start_price"]), float(ep["low_price"])) or 0.0
        rebound = pct(float(ep["low_price"]), end_price) or 0.0
        lines = ["🟢 <b>코스피 급락 사건구간 종료·복원 확인</b>", f"<code>{dt.datetime.now(KST):%Y-%m-%d %H:%M:%S} KST</code>", "",
                 "<b>확정된 급락 구간</b>",
                 f"• <b>{fmt_clock(ep['start_ts'])} → {fmt_clock(ep['low_ts'])}</b> · {fmt_duration(float(ep['low_ts'])-float(ep['start_ts']))}",
                 f"• KOSPI <b>{float(ep['start_price']):,.2f}</b> → <b>{float(ep['low_price']):,.2f}</b> · <b>{drop:+.2f}%</b>",
                 f"• 저점 이후 현재 <b>{end_price:,.2f}</b> · 반등 <b>{rebound:+.2f}%</b>", "",
                 "<b>저점까지 실제 매도주체</b>"]
        if att.get("available"):
            s, f, p = att["spot"], att["futures"], att["program"]
            cross = ", ".join(att.get("cross_sellers") or []) or "없음"
            lines += [f"• 현물: 외국인 <b>{fmt_eok(s.get('외국인'))}</b> · 기관 <b>{fmt_eok(s.get('기관'))}</b> · 개인 <b>{fmt_eok(s.get('개인'))}</b>",
                      f"• KOSPI200 선물: 외국인 <b>{fmt_eok(f.get('외국인'))}</b> · 기관 <b>{fmt_eok(f.get('기관'))}</b> · 개인 <b>{fmt_eok(f.get('개인'))}</b>",
                      f"• 현물 최다매도: <b>{html.escape(str(att.get('spot_leader') or '없음'))}</b> {fmt_eok(att.get('spot_leader_value'))}",
                      f"• 선물 최다매도: <b>{html.escape(str(att.get('futures_leader') or '없음'))}</b> {fmt_eok(att.get('futures_leader_value'))}",
                      f"• 양시장 동시매도: <b>{html.escape(cross)}</b>",
                      f"• 프로그램: 전체 <b>{fmt_raw(p.get('전체'))}</b> · 차익 <b>{fmt_raw(p.get('차익'))}</b> · 비차익 <b>{fmt_raw(p.get('비차익'))}</b> <i>(LS t1640 누적값 변화)</i>",
                      f"• 최종 판정: <b>{html.escape(str(att.get('verdict')))}</b> · 확신도 {html.escape(str(att.get('confidence')))}"]
        else:
            lines += ["• 수급 스냅샷 부족 — 가격 구간만 확정"]
        lines += ["", "• " + " · ".join([link(KOSPI_URL,"KOSPI"), link(NEWS_URL,"관련 뉴스")])]
        return "\n".join(lines)

    async def maybe_flow(self) -> None:
        now = time.time()
        if self.flow_task and not self.flow_task.done():
            return
        if now - self.last_flow_poll < FLOW_INTERVAL_SEC:
            return
        self.last_flow_poll = now
        async def run_one():
            try:
                snap = await asyncio.to_thread(fetch_flow_snapshot, self.token)
                self.flows.append(snap)
                self.raw["last_flow_snapshot"] = snap
                if snap.get("현물") is not None and snap.get("선물") is not None and snap.get("프로그램") is not None:
                    self.last_flow_success_ts = time.time()
                cutoff = time.time() - FLOW_LOOKBACK_SEC
                while self.flows and float(self.flows[0].get("ts", 0)) < cutoff:
                    self.flows.popleft()
            except Exception as exc:
                self.raw["last_flow_error"] = f"{type(exc).__name__}: {exc}"
        self.flow_task = asyncio.create_task(run_one())

    async def evaluate(self) -> None:
        await self.maybe_flow()
        if not self.idx:
            return
        now_t, cur = self.idx[-1]
        if self.episode is None:
            hit, info = self._trigger()
            if not hit:
                return
            self.episode = {"start_ts": info["peak_ts"], "start_price": info["peak"],
                            "low_ts": now_t, "low_price": cur, "sent_drop": abs(float(info["drop"])),
                            "alerted": True, "trigger": info}
            self.msg_ids.append(await asyncio.to_thread(telegram_send, self.build_alert("start", self.episode, now_t, cur)))
            return
        ep = self.episode
        if cur < float(ep["low_price"]):
            ep["low_price"] = cur; ep["low_ts"] = now_t
        total_drop = abs(pct(float(ep["start_price"]), cur) or 0.0)
        if total_drop >= float(ep.get("sent_drop", 0.0)) + 0.50:
            ep["sent_drop"] = total_drop
            self.msg_ids.append(await asyncio.to_thread(telegram_send, self.build_alert("expand", ep, now_t, cur)))
        low_age = now_t - float(ep["low_ts"])
        full_drop = abs(pct(float(ep["start_price"]), float(ep["low_price"])) or 0.0)
        rebound = pct(float(ep["low_price"]), cur) or 0.0
        need_rebound = max(0.30, min(0.70, full_drop * 0.30))
        recovery_ratio = 0.0
        if float(ep["start_price"]) > float(ep["low_price"]):
            recovery_ratio = (cur - float(ep["low_price"])) / (float(ep["start_price"]) - float(ep["low_price"]))
        ended = ((low_age >= NEW_LOW_CONFIRM_SEC and rebound >= need_rebound) or
                 (low_age >= 120 and recovery_ratio >= 0.45) or
                 (now_t - float(ep["start_ts"]) >= MAX_EPISODE_SEC and low_age >= 600))
        if ended:
            self.msg_ids.append(await asyncio.to_thread(telegram_send, self.build_end(ep, now_t, cur)))
            self.episode = None

    def on_realtime(self, api_obj: ebest.OpenApi, trcode: str, key: str, data: dict[str, Any]) -> None:
        t = time.time(); self.raw.setdefault(trcode, {"key": key, "fields": sorted(data.keys())})
        if trcode == "IJ_":
            j = fnum(data.get("jisu"))
            if j is not None and j > 0:
                self.idx.append((t, j))
                self.last_idx_tick_ts = t
                cutoff = t - PRICE_LOOKBACK_SEC
                while self.idx and self.idx[0][0] < cutoff:
                    self.idx.popleft()
        elif trcode == "FC0":
            p = fnum(data.get("price"))
            if p is not None and p > 0:
                self.fut.append((t, p))
                self.last_fut_tick_ts = t
        elif trcode == "OC0":
            p = fnum(data.get("price"))
            if p is not None and p >= 0:
                self.puts[str(key)].append((t, p))

    async def register(self) -> None:
        rsp = await self.api.request("t9943", {"t9943InBlock": {"gubun": "1"}})
        if not rsp:
            raise RuntimeError(f"t9943 failed: {self.api.last_message}")
        rows = rsp.body.get("t9943OutBlock") or []
        if not rows:
            raise RuntimeError("No KOSPI200 future master")
        self.front_future = str(rows[0].get("shcode") or "").strip()
        regs = [("IJ_", "001"), ("FC0", self.front_future)] + [("OC0", x["code"]) for x in self.put_defs]
        failed = []
        for tr, key in regs:
            if not await self.api.add_realtime(tr, key):
                failed.append((tr, key, str(self.api.last_message)))
        if failed:
            raise RuntimeError(f"Realtime registration failed: {failed}")

    async def close(self) -> None:
        for tr, key in [("IJ_", "001"), ("FC0", self.front_future)] + [("OC0", x["code"]) for x in self.put_defs]:
            if not key: continue
            try: await self.api.remove_realtime(tr, key)
            except Exception: pass

    async def run(self, until: dt.time, test_seconds: int | None = None) -> None:
        self.api.on_realtime.connect(self.on_realtime)
        await self.register()
        started = time.time()
        try:
            while True:
                now = dt.datetime.now(KST)
                if test_seconds is not None and time.time() - started >= test_seconds: break
                if test_seconds is None and now.time() >= until: break

                # production 장중 생존검사: 프로세스만 살아 있고 데이터가 멈춘 상태를 허용하지 않는다.
                if test_seconds is None and dt.time(9, 2) <= now.time() < until and time.time() - started >= 180:
                    now_ts = time.time()
                    if self.last_idx_tick_ts is None or now_ts - self.last_idx_tick_ts > 75:
                        raise RuntimeError("KOSPI realtime feed stale >75s")
                    if self.last_fut_tick_ts is None or now_ts - self.last_fut_tick_ts > 90:
                        raise RuntimeError("KOSPI200 futures feed stale >90s")
                    if self.last_flow_success_ts is None or now_ts - self.last_flow_success_ts > 120:
                        raise RuntimeError("LS spot/futures/program flow snapshot stale >120s")

                await self.evaluate()
                await asyncio.sleep(1)
        finally:
            if self.flow_task:
                try: await asyncio.wait_for(self.flow_task, timeout=8)
                except Exception: pass
            try: self.api.on_realtime.disconnect(self.on_realtime)
            except Exception: pass
            await self.close()


def write_status(w: Watch, started: dt.datetime, status: str) -> None:
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text("\n".join([
        "# 코스피 급락 사건구간 감시", "",
        f"- 시작: {started:%Y-%m-%d %H:%M:%S} KST", f"- 상태: {status}",
        f"- KOSPI 틱: {len(w.idx)}", f"- 선물 틱: {len(w.fut)}", f"- 수급 스냅샷: {len(w.flows)}",
        f"- 최근월물 선물: {w.front_future or '미확인'}", f"- 구독 풋옵션: {len(w.put_defs)}",
        f"- 진행 중 사건: {'있음' if w.episode else '없음'}", f"- 텔레그램 ID: {w.msg_ids}",
    ]) + "\n", encoding="utf-8")
    RAW.write_text(json.dumps(w.raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def synthetic_test() -> int:
    base = time.time() - 60 * 70
    prices = []
    for i in range(15): prices.append((base+i*60, 7170 + i*0.1))
    for i in range(1, 48): prices.append((base+(15+i)*60, 7171.4 - i*2.7))
    for i in range(1, 9): prices.append((base+(62+i)*60, 7044.5 + i*5.0))
    class Dummy: pass
    d = Dummy(); d.idx = deque(prices, maxlen=30000)
    d._nearest = Watch._nearest; d._ret = Watch._ret.__get__(d, Dummy); d._recent_peak = Watch._recent_peak.__get__(d, Dummy)
    hit, info = Watch._trigger(d)
    print(json.dumps({"hit": hit, "start": fmt_clock(info.get("peak_ts")), "drop": info.get("drop"), "duration_min": (info.get("duration") or 0)/60}, ensure_ascii=False))
    return 0 if hit else 1


async def amain(test: bool, seconds: int, until: dt.time) -> int:
    key=(os.getenv("LS_OPENAPI_APP_KEY") or "").strip(); secret=(os.getenv("LS_OPENAPI_APP_SECRET") or "").strip()
    if not key or not secret: raise RuntimeError("LS secrets missing")
    token = await asyncio.to_thread(get_token)
    current = await asyncio.to_thread(fetch_kpi200)
    puts = await asyncio.to_thread(get_weekly_puts, token, current)
    api = ebest.OpenApi()
    if not await api.login(key, secret): raise RuntimeError(f"LS login failed: {api.last_message}")
    w = Watch(api, token, puts, test)
    started = dt.datetime.now(KST)
    try:
        await w.run(until, seconds if test else None)
        write_status(w, started, "정상 종료")
        return 0
    except Exception as exc:
        write_status(w, started, f"오류: {type(exc).__name__}: {exc}")
        raise
    finally:
        try: await api.close()
        except Exception: pass


def parse_hhmm(s: str) -> dt.time:
    h, m = map(int, s.split(":")); return dt.time(h, m)


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--test", action="store_true"); ap.add_argument("--test-seconds", type=int, default=12)
    ap.add_argument("--synthetic-test", action="store_true"); ap.add_argument("--until", default="15:25")
    args = ap.parse_args()
    if args.synthetic_test: return synthetic_test()
    return asyncio.run(amain(args.test, args.test_seconds, parse_hhmm(args.until)))

if __name__ == "__main__": raise SystemExit(main())
