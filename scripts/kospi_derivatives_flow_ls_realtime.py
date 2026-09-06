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
BASE_URL = "https://openapi.ls-sec.co.kr:8080"
STATE_PATH = Path("data/kospi_derivatives_flow_ls_state.json")
STATUS_PATH = Path("out/kospi_derivatives_flow_ls_status.md")
RAW_PATH = Path("out/kospi_derivatives_flow_ls_raw_sample.json")

START_TIME = dt.time(13, 35)
END_TIME = dt.time(15, 25)
EARLY_3M = -0.80
EARLY_5M = -1.00
MAIN_10M = -1.50
MAIN_DD15 = -2.00
REBOUND = 1.20
EPISODE_TTL_MIN = 60

KOSPI_URL = "https://m.stock.naver.com/domestic/index/KOSPI/total"
KPI200_URL = "https://m.stock.naver.com/domestic/index/KPI200/total"
LS_GUIDE_URL = "https://openapi.ls-sec.co.kr/apiservice"
KRX_WEEKLY_URL = "https://global.krx.co.kr/contents/GLB/02/0201/0201040202/GLB0201040202.jsp"
NEWS_URL = "https://search.naver.com/search.naver?where=news&query=" + urllib.parse.quote("코스피 급락")


def fnum(v: Any, default: float | None = None) -> float | None:
    try:
        if v is None or str(v).strip() == "":
            return default
        return float(str(v).replace(",", "").strip())
    except Exception:
        return default


def pct(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or a == 0:
        return None
    return (b / a - 1.0) * 100.0


def expiry_label(now: dt.datetime) -> tuple[bool, str]:
    if now.weekday() == 0:
        return True, "월요일 KOSPI200 위클리옵션 만기"
    if now.weekday() == 3:
        week = (now.day - 1) // 7 + 1
        if week == 2:
            return True, "둘째 목요일 KOSPI200 정규 월물 만기(위클리 미상장)"
        return True, "목요일 KOSPI200 위클리옵션 만기"
    return False, "정규 월·목 파생 만기일 아님"


def link(url: str, label: str) -> str:
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'


def telegram_send(text: str) -> int:
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = ((os.getenv("TELEGRAM_CHAT_ID_PRIMARY") or "").strip()
               or (os.getenv("TELEGRAM_CHAT_ID_FALLBACK") or "").strip())
    expected = (os.getenv("EXPECTED_TELEGRAM_BOT_USERNAME") or "").strip().lstrip("@")
    if not token or not chat_id:
        raise RuntimeError("Telegram token/chat id missing")
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getMe", timeout=20) as response:
        ident = json.loads(response.read().decode("utf-8"))
    actual = str((ident.get("result") or {}).get("username") or "")
    if not ident.get("ok") or (expected and actual.lower() != expected.lower()):
        raise RuntimeError(f"Wrong Telegram bot: expected @{expected}, got @{actual or 'unknown'}")
    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=payload, method="POST")
    with urllib.request.urlopen(req, timeout=30) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not result.get("ok"):
        raise RuntimeError(f"Telegram rejected message: {result}")
    return int(result["result"]["message_id"])


def get_ls_token() -> str:
    app_key = (os.getenv("LS_OPENAPI_APP_KEY") or "").strip()
    app_secret = (os.getenv("LS_OPENAPI_APP_SECRET") or "").strip()
    if not app_key or not app_secret:
        raise RuntimeError("LS_OPENAPI_APP_KEY / LS_OPENAPI_APP_SECRET missing")
    r = requests.post(
        f"{BASE_URL}/oauth2/token",
        headers={"content-type": "application/x-www-form-urlencoded"},
        params={
            "grant_type": "client_credentials",
            "appkey": app_key,
            "appsecretkey": app_secret,
            "scope": "oob",
        },
        timeout=30,
    )
    r.raise_for_status()
    token = str(r.json().get("access_token") or "").strip()
    if not token:
        raise RuntimeError("LS access token issue failed")
    return token


def ls_rest(token: str, path: str, tr_cd: str, body: dict[str, Any]) -> dict[str, Any]:
    r = requests.post(
        f"{BASE_URL}/{path}",
        headers={
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "tr_cd": tr_cd,
            "tr_cont": "N",
            "tr_cont_key": "",
        },
        data=json.dumps(body),
        timeout=20,
    )
    if not r.ok:
        raise RuntimeError(f"{tr_cd} HTTP {r.status_code}: {(r.text or '')[:300]}")
    return r.json()


def fetch_kpi200() -> float | None:
    try:
        r = requests.get("https://m.stock.naver.com/api/index/KPI200/basic", headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        r.raise_for_status()
        return fnum(r.json().get("closePrice"))
    except Exception:
        return None


def parse_weekly_options(rows: list[dict[str, Any]], current: float | None, limit: int = 7) -> list[dict[str, Any]]:
    parsed = []
    for row in rows:
        name = str(row.get("hname") or "").strip()
        code = str(row.get("shcode") or "").strip()
        if not code or not name:
            continue
        if not re.match(r"^P(?:\s|$)", name, flags=re.I):
            continue
        m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*$", name)
        strike = fnum(m.group(1)) if m else fnum(row.get("recprice"))
        if strike is None:
            continue
        parsed.append({"code": code, "name": name, "strike": strike})
    if current is not None:
        parsed.sort(key=lambda x: abs(float(x["strike"]) - current))
    return parsed[:limit]


def get_weekly_puts(token: str, current: float | None) -> list[dict[str, Any]]:
    try:
        d = ls_rest(token, "futureoption/market-data", "t8435", {"t8435InBlock": {"gubun": "WK"}})
        rows = d.get("t8435OutBlock") or []
        return parse_weekly_options(rows, current)
    except Exception:
        return []


def get_program_snapshot(token: str) -> dict[str, Any] | None:
    # Current LS docs: t1640 program mini snapshot. gubun=11 is the official request example.
    candidates = [
        {"t1640InBlock": {"gubun": "11", "exchgubun": "K"}},
        {"t1640InBlock": {"gubun": "11", "exchgubun": ""}},
        {"t1640InBlock": {"gubun": "11"}},
    ]
    for body in candidates:
        try:
            d = ls_rest(token, "stock/program", "t1640", body)
            row = d.get("t1640OutBlock")
            if isinstance(row, dict) and row:
                return row
        except Exception:
            continue
    return None


class RealtimeWatch:
    def __init__(self, api: ebest.OpenApi, ls_token: str, weekly_puts: list[dict[str, Any]], test: bool = False):
        self.api = api
        self.ls_token = ls_token
        self.weekly_puts = weekly_puts
        self.test = test
        self.idx: deque[tuple[float, float]] = deque(maxlen=3000)
        self.fut: deque[tuple[float, float]] = deque(maxlen=3000)
        self.puts: dict[str, deque[tuple[float, float]]] = defaultdict(lambda: deque(maxlen=3000))
        self.last_idx: dict[str, Any] = {}
        self.last_fut: dict[str, Any] = {}
        self.last_pm: dict[str, Any] = {}
        self.last_pm_ts: float | None = None
        self.program: dict[str, Any] | None = None
        self.program_prev: dict[str, Any] | None = None
        self.episode: dict[str, Any] | None = None
        self.early_sent = False
        self.main_sent = False
        self.rebound_sent = False
        self.last_program_poll = 0.0
        self.raw_sample: dict[str, Any] = {}
        self.front_future = ""
        self.msg_ids: list[int] = []

    @staticmethod
    def _at(buf: deque[tuple[float, float]], minutes: float) -> float | None:
        if not buf:
            return None
        target = time.time() - minutes * 60
        return min(buf, key=lambda x: abs(x[0] - target))[1]

    @staticmethod
    def _recent_high(buf: deque[tuple[float, float]], minutes: float) -> float | None:
        cutoff = time.time() - minutes * 60
        vals = [v for t, v in buf if t >= cutoff]
        return max(vals) if vals else None

    def metrics(self) -> dict[str, Any]:
        cur = self.idx[-1][1] if self.idx else None
        fut_cur = self.fut[-1][1] if self.fut else None
        m: dict[str, Any] = {"idx": cur, "fut": fut_cur}
        for mins in (1, 3, 5, 10):
            m[f"idx{mins}"] = pct(self._at(self.idx, mins), cur)
            m[f"fut{mins}"] = pct(self._at(self.fut, mins), fut_cur)
        hi = self._recent_high(self.idx, 15)
        m["dd15"] = pct(hi, cur)
        put_moves = []
        for opt in self.weekly_puts:
            b = self.puts.get(opt["code"])
            if not b:
                continue
            pcur = b[-1][1]
            pbase = self._at(b, 3)
            if pbase and pbase > 0:
                put_moves.append((pcur / pbase, opt, pcur, pbase))
        put_moves.sort(key=lambda x: x[0], reverse=True)
        m["put_best"] = put_moves[0] if put_moves else None
        return m

    def program_view(self) -> dict[str, Any]:
        row = self.program or {}
        prev = self.program_prev or {}
        value = fnum(row.get("value"))
        sunvaldiff = fnum(row.get("sunvaldiff"))
        basis = fnum(row.get("basis"))
        prev_value = fnum(prev.get("value"))
        delta = (value - prev_value) if value is not None and prev_value is not None else None
        return {"value": value, "delta": delta, "sunvaldiff": sunvaldiff, "basis": basis}

    def classify(self, m: dict[str, Any]) -> tuple[str, list[str]]:
        reasons = []
        expiry, expiry_text = expiry_label(dt.datetime.now(KST))
        if expiry:
            reasons.append(expiry_text)
        i3, f3 = m.get("idx3"), m.get("fut3")
        if i3 is not None and f3 is not None and f3 <= i3 - 0.10:
            reasons.append(f"KOSPI200 선물이 3분 기준 현물보다 {abs(f3-i3):.2f}%p 더 약함")
        pb = m.get("put_best")
        if pb and pb[0] >= 2.0:
            reasons.append(f"근접 위클리 풋 {pb[1]['name']} 3분 {pb[0]:.1f}배")
        pv = self.program_view()
        if pv["sunvaldiff"] is not None and pv["sunvaldiff"] < 0:
            reasons.append("프로그램 순매수금액 증감이 매도 방향")
        elif pv["delta"] is not None and pv["delta"] < 0:
            reasons.append("프로그램 순매수금액이 직전 조회보다 감소")
        elif self.last_pm_ts and time.time() - self.last_pm_ts < 15:
            reasons.append("KOSPI 프로그램매매 실시간 피드 동시 갱신")
        score = len(reasons)
        if score >= 3:
            return "파생·프로그램 수급이 가격 급락과 동시 악화 — 수급 증폭 가능성 높음", reasons
        if score >= 1:
            return "가격 급락에 파생·수급 신호 일부 동반 — 원인 교차확인 필요", reasons
        return "가격 급락 우선 감지 — 뉴스·현물 수급 원인을 먼저 확인", reasons

    def alert_text(self, level: int, m: dict[str, Any]) -> str:
        verdict, reasons = self.classify(m)
        now = dt.datetime.now(KST)
        idx = m.get("idx")
        fut = m.get("fut")
        pv = self.program_view()
        pb = m.get("put_best")
        title = "🟠 <b>코스피 파생·수급 급변 1단계</b>" if level == 1 else "🚨 <b>코스피 파생·수급 이상변동 2단계</b>"
        lines = [
            title,
            f"<code>{now:%Y-%m-%d %H:%M:%S} KST</code>",
            "",
            f"<b>판정</b>  {html.escape(verdict)}",
            "",
            "<b>현재 움직임</b>",
            f"• KOSPI <b>{idx:,.2f}</b>" if idx is not None else "• KOSPI 계산 대기",
            f"• 3분 <b>{m['idx3']:+.2f}%</b> · 5분 <b>{m['idx5']:+.2f}%</b> · 10분 <b>{m['idx10']:+.2f}%</b>" if all(m.get(k) is not None for k in ("idx3","idx5","idx10")) else "• 단기 변동률 표본 축적 중",
            f"• 최근 15분 고점 대비 <b>{m['dd15']:+.2f}%</b>" if m.get("dd15") is not None else "• 최근 15분 고점 대비 계산 대기",
        ]
        if fut is not None:
            lines.append(f"• KOSPI200 선물 <b>{fut:,.2f}</b> · 3분 <b>{m['fut3']:+.2f}%</b>" if m.get("fut3") is not None else f"• KOSPI200 선물 <b>{fut:,.2f}</b>")
        if pb:
            lines.append(f"• 위클리 풋 <b>{html.escape(pb[1]['name'])}</b> · 3분 <b>{pb[0]:.1f}배</b>")
        if pv["basis"] is not None:
            lines.append(f"• 프로그램/선물 베이시스 참고값 <b>{pv['basis']:.2f}</b>")
        lines += ["", "<b>왜 경보가 울렸나</b>"]
        if level == 1:
            if m.get("idx3") is not None and m["idx3"] <= EARLY_3M:
                lines.append(f"• KOSPI 3분 <b>{m['idx3']:+.2f}%</b> ≤ {EARLY_3M:.2f}%")
            if m.get("idx5") is not None and m["idx5"] <= EARLY_5M:
                lines.append(f"• KOSPI 5분 <b>{m['idx5']:+.2f}%</b> ≤ {EARLY_5M:.2f}%")
        else:
            if m.get("idx10") is not None and m["idx10"] <= MAIN_10M:
                lines.append(f"• KOSPI 10분 <b>{m['idx10']:+.2f}%</b> ≤ {MAIN_10M:.2f}%")
            if m.get("dd15") is not None and m["dd15"] <= MAIN_DD15:
                lines.append(f"• 15분 고점 대비 <b>{m['dd15']:+.2f}%</b> ≤ {MAIN_DD15:.2f}%")
        for r in reasons[:4]:
            lines.append(f"• {html.escape(r)}")
        lines += [
            "",
            "<b>해석</b>",
            "• 선물 선행·풋 급등·프로그램 매도 방향이 겹칠수록 <b>파생·수급 증폭</b> 가능성을 높게 봅니다.",
            "• 이것만으로 불법 시세조종이나 업틱룰 예외 공매도를 원인으로 확정하지 않습니다.",
            "• 급락 직후 매매 지시가 아니라 <b>펀더멘털 뉴스인지 수급 충격인지 먼저 구분하는 경보</b>입니다.",
            "",
            "<b>바로 확인</b>",
            "• " + " · ".join([link(KOSPI_URL, "KOSPI"), link(KPI200_URL, "KOSPI200"), link(NEWS_URL, "급락 뉴스")]),
            "• " + " · ".join([link(LS_GUIDE_URL, "LS증권 OpenAPI"), link(KRX_WEEKLY_URL, "KRX 옵션 규정")]),
        ]
        return "\n".join(lines)

    def rebound_text(self, m: dict[str, Any], low: float, rebound: float) -> str:
        now = dt.datetime.now(KST)
        idx = m.get("idx")
        return "\n".join([
            "🟢 <b>코스피 급변동 되돌림 확인</b>",
            f"<code>{now:%Y-%m-%d %H:%M:%S} KST</code>",
            "",
            "<b>판정</b>  급락 뒤 빠른 복원 — 일시적 파생·수급 충격 가능성 상승",
            "",
            "<b>현재 움직임</b>",
            f"• 급락 구간 저점 <b>{low:,.2f}</b> → 현재 <b>{idx:,.2f}</b>",
            f"• 저점 대비 <b>{rebound:+.2f}%</b> · 경보기준 +{REBOUND:.2f}%",
            "",
            "<b>해석</b>",
            "• 새로운 펀더멘털 악재가 확인되지 않으면서 빠르게 되돌리면 만기·헤지·차익거래 등 일시적 수급 충격 설명력이 커집니다.",
            "• 반등만으로 원인을 확정하지 않고 뉴스·선물·프로그램매매를 다시 확인합니다.",
            "",
            "• " + " · ".join([link(KOSPI_URL, "KOSPI"), link(NEWS_URL, "관련 뉴스"), link(KRX_WEEKLY_URL, "KRX 옵션 규정")]),
        ])

    async def maybe_poll_program(self) -> None:
        now = time.time()
        if now - self.last_program_poll < 5:
            return
        self.last_program_poll = now
        row = await asyncio.to_thread(get_program_snapshot, self.ls_token)
        if row:
            self.program_prev = self.program
            self.program = row
            self.raw_sample.setdefault("t1640_fields", sorted(row.keys()))

    async def evaluate(self) -> None:
        if len(self.idx) < 2:
            return
        await self.maybe_poll_program()
        m = self.metrics()
        cur = m.get("idx")
        if cur is None:
            return
        now = dt.datetime.now(KST)
        early = ((m.get("idx3") is not None and m["idx3"] <= EARLY_3M) or
                 (m.get("idx5") is not None and m["idx5"] <= EARLY_5M))
        main = ((m.get("idx10") is not None and m["idx10"] <= MAIN_10M) or
                (m.get("dd15") is not None and m["dd15"] <= MAIN_DD15))

        if early or main:
            if self.episode is None:
                self.episode = {"started_at": now.isoformat(timespec="seconds"), "low": cur}
                self.early_sent = False
                self.main_sent = False
                self.rebound_sent = False
            self.episode["low"] = min(float(self.episode.get("low") or cur), cur)
            if early and not self.early_sent:
                self.msg_ids.append(await asyncio.to_thread(telegram_send, self.alert_text(1, m)))
                self.early_sent = True
            if main and not self.main_sent:
                self.msg_ids.append(await asyncio.to_thread(telegram_send, self.alert_text(2, m)))
                self.main_sent = True
        elif self.episode:
            started = dt.datetime.fromisoformat(str(self.episode["started_at"]))
            age = (now - started).total_seconds() / 60
            low = min(float(self.episode.get("low") or cur), cur)
            self.episode["low"] = low
            rebound = pct(low, cur) or 0.0
            if (self.early_sent or self.main_sent) and not self.rebound_sent and rebound >= REBOUND and age <= EPISODE_TTL_MIN:
                self.msg_ids.append(await asyncio.to_thread(telegram_send, self.rebound_text(m, low, rebound)))
                self.rebound_sent = True
                self.episode = None
            elif age > EPISODE_TTL_MIN:
                self.episode = None

    def on_realtime(self, api_obj: ebest.OpenApi, trcode: str, key: str, data: dict[str, Any]) -> None:
        t = time.time()
        self.raw_sample.setdefault(str(trcode), {"key": str(key), "fields": sorted(data.keys()), "sample": data})
        if trcode == "IJ_":
            j = fnum(data.get("jisu"))
            if j is not None and j > 0:
                self.last_idx = data
                self.idx.append((t, j))
        elif trcode == "FC0":
            p = fnum(data.get("price"))
            if p is not None and p > 0:
                self.last_fut = data
                self.fut.append((t, p))
        elif trcode == "OC0":
            p = fnum(data.get("price"))
            if p is not None and p >= 0:
                self.puts[str(key)].append((t, p))
        elif trcode == "PM_":
            self.last_pm = data
            self.last_pm_ts = t

    async def register(self) -> None:
        rsp = await self.api.request("t9943", {"t9943InBlock": {"gubun": "1"}})
        if not rsp:
            raise RuntimeError(f"t9943 failed: {self.api.last_message}")
        rows = rsp.body.get("t9943OutBlock") or []
        if not rows:
            raise RuntimeError("No KOSPI200 future master rows")
        self.front_future = str(rows[0].get("shcode") or "").strip()
        regs = [("IJ_", "001"), ("PM_", "001"), ("FC0", self.front_future)]
        if not self.weekly_puts:
            orsp = await self.api.request("t9944", {"t9944InBlock": {"dummy": ""}})
            opts = (orsp.body.get("t9944OutBlock") or []) if orsp else []
            if opts:
                code = str(opts[0].get("shcode") or "").strip()
                if code:
                    self.weekly_puts = [{"code": code, "name": str(opts[0].get("hname") or code), "strike": 0.0}]
        for opt in self.weekly_puts:
            regs.append(("OC0", opt["code"]))
        failed = []
        for tr, key in regs:
            ok = await self.api.add_realtime(tr, key)
            if not ok:
                failed.append((tr, key, str(self.api.last_message)))
        if failed:
            raise RuntimeError(f"Realtime registration failed: {failed}")

    async def close(self) -> None:
        for tr, key in [("IJ_", "001"), ("PM_", "001"), ("FC0", self.front_future)]:
            if key:
                try:
                    await self.api.remove_realtime(tr, key)
                except Exception:
                    pass
        for opt in self.weekly_puts:
            try:
                await self.api.remove_realtime("OC0", opt["code"])
            except Exception:
                pass

    async def run(self, seconds: int | None = None) -> None:
        self.api.on_realtime.connect(self.on_realtime)
        await self.register()
        started = time.time()
        try:
            while True:
                now = dt.datetime.now(KST)
                if seconds is not None and time.time() - started >= seconds:
                    break
                if seconds is None and now.time() >= END_TIME:
                    break
                await self.evaluate()
                await asyncio.sleep(1)
        finally:
            try:
                self.api.on_realtime.disconnect(self.on_realtime)
            except Exception:
                pass
            await self.close()


def write_status(w: RealtimeWatch, started: dt.datetime, result: str) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    m = w.metrics()
    STATUS_PATH.write_text(
        "# 코스피 LS 실시간 파생·수급 감시\n\n"
        f"- 시작: {started:%Y-%m-%d %H:%M:%S} KST\n"
        f"- 종료/상태: {result}\n"
        f"- 최근월물 선물: {w.front_future or '미확인'}\n"
        f"- 구독 옵션: {len(w.weekly_puts)}개\n"
        f"- KOSPI 실시간 표본: {len(w.idx)}개\n"
        f"- 선물 실시간 표본: {len(w.fut)}개\n"
        f"- PM_ 마지막 수신: {'있음' if w.last_pm_ts else '없음'}\n"
        f"- 마지막 KOSPI: {m.get('idx')}\n"
        f"- 텔레그램 발송 ID: {w.msg_ids}\n",
        encoding="utf-8",
    )
    RAW_PATH.write_text(json.dumps(w.raw_sample, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


async def async_main(test: bool, test_seconds: int) -> int:
    now = dt.datetime.now(KST)
    if not test:
        if now.weekday() >= 5:
            STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
            STATUS_PATH.write_text(f"# 코스피 LS 실시간 파생·수급 감시\n\n- 상태: 주말\n- 조회: {now:%Y-%m-%d %H:%M:%S} KST\n", encoding="utf-8")
            return 0
        if now.time() < START_TIME:
            target = dt.datetime.combine(now.date(), START_TIME, tzinfo=KST)
            await asyncio.sleep(max(0.0, (target - now).total_seconds()))
        if dt.datetime.now(KST).time() >= END_TIME:
            return 0

    appkey = (os.getenv("LS_OPENAPI_APP_KEY") or "").strip()
    appsecret = (os.getenv("LS_OPENAPI_APP_SECRET") or "").strip()
    if not appkey or not appsecret:
        raise RuntimeError("LS OpenAPI secrets missing")

    ls_token = await asyncio.to_thread(get_ls_token)
    current200 = await asyncio.to_thread(fetch_kpi200)
    weekly_puts = await asyncio.to_thread(get_weekly_puts, ls_token, current200)

    api = ebest.OpenApi()
    if not await api.login(appkey, appsecret):
        raise RuntimeError(f"LS login failed: {api.last_message}")
    watch = RealtimeWatch(api, ls_token, weekly_puts, test=test)
    started = dt.datetime.now(KST)
    try:
        await watch.run(seconds=test_seconds if test else None)
        write_status(watch, started, "정상 종료")
        return 0
    except Exception as exc:
        write_status(watch, started, f"오류: {type(exc).__name__}: {exc}")
        raise
    finally:
        try:
            await api.close()
        except Exception:
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--test-seconds", type=int, default=8)
    args = ap.parse_args()
    return asyncio.run(async_main(args.test, args.test_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
