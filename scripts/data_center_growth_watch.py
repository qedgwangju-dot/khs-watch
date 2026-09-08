#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import io
import json
import re
from pathlib import Path

import requests
from openpyxl import load_workbook

URL = "https://www.census.gov/construction/c30/xlsx/privsatime.xlsx"
SOURCE = "https://www.census.gov/construction/c30/historical_data.html"
STATE = Path("data/data_center_growth_state.json")
OUT = Path("out")
ALERT = OUT / "data_center_growth_alert.txt"
PENDING = OUT / "data_center_growth_pending_state.json"
STATUS = OUT / "data_center_growth_status.md"
HEADERS = {"User-Agent": "khs-watch/1.0 (+https://github.com/qedgwangju-dot/khs-watch)"}
MONTHS = {m.lower(): i for i, m in enumerate(("Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"), 1)}


def fetch(url, timeout=40):
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r


def parse_period(raw):
    s = re.sub(r"[pr]$", "", str(raw or "").strip(), flags=re.I)
    m = re.fullmatch(r"([A-Za-z]{3})-(\d{2})", s)
    if not m:
        return None
    return 2000 + int(m.group(2)), MONTHS[m.group(1).lower()]


def pct(a, b):
    return None if not b else (a / b - 1) * 100


def prev_period(year, month, n=1):
    x = year * 12 + month - 1 - n
    return x // 12, x % 12 + 1


def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def fx_rate(old=None):
    sources = [
        ("https://open.er-api.com/v6/latest/USD", lambda d: d["rates"]["KRW"], "ER-API"),
        ("https://api.frankfurter.app/latest?from=USD&to=KRW", lambda d: d["rates"]["KRW"], "Frankfurter"),
    ]
    for url, parser, name in sources:
        try:
            v = float(parser(fetch(url, 20).json()))
            if 500 < v < 3000:
                return v, name
        except Exception:
            pass
    return (float(old), "직전 저장값") if old else (None, "조회 실패")


def krw(usd_million, fx):
    if not fx:
        return "원화 환산 확인 불가"
    eok = round(usd_million * fx / 100)
    jo, rem = divmod(eok, 10000)
    return f"약 {jo:,}조{rem:,}억원" if jo and rem else (f"약 {jo:,}조원" if jo else f"약 {rem:,}억원")


def fp(x):
    return "확인 불가" if x is None else f"{x:+.1f}%"


OUT.mkdir(exist_ok=True)
for p in (ALERT, PENDING, STATUS):
    if p.exists():
        p.unlink()

wb = load_workbook(io.BytesIO(fetch(URL).content), data_only=True)
ws = wb["Private SA"]
headers = {str(ws.cell(4, c).value).strip(): c for c in range(1, ws.max_column + 1)}
if "Data center" not in headers:
    raise SystemExit("Census workbook: Data center column not found")
dc_col = headers["Data center"]
series = []
for r in range(5, ws.max_row + 1):
    period = parse_period(ws.cell(r, 1).value)
    value = ws.cell(r, dc_col).value
    if period and isinstance(value, (int, float)):
        series.append((period[0], period[1], float(value)))
if len(series) < 14:
    raise SystemExit(f"Census data center series too short: {len(series)}")
series.sort()
lookup = {(y, m): v for y, m, v in series}
y, m, value = series[-1]
py, pm = prev_period(y, m)
yy, ym = prev_period(y, m, 12)
pyy, pym = prev_period(y, m, 13)
prev = lookup.get((py, pm)); ago = lookup.get((yy, ym)); ago_prev = lookup.get((pyy, pym))
mom = pct(value, prev)
yoy = pct(value, ago)
prev_yoy = pct(prev, ago_prev) if prev and ago_prev else None
prior_vals = [v for sy, sm, v in series if (sy, sm) < (y, m)]
prior_record = max(prior_vals) if prior_vals else None
record = prior_record is None or value > prior_record

old = load_state()
period = f"{y:04d}-{m:02d}"
baseline = not old.get("last_period")
new_period = old.get("last_period") != period
revision = (not new_period and old.get("last_value_musd") and abs(pct(value, float(old["last_value_musd"])) or 0) >= 2)
fx, fx_source = fx_rate(old.get("last_fx_krw_per_usd"))
reasons = []
if record: reasons.append("사상 최고치 경신")
if mom is not None and abs(mom) >= 5: reasons.append(f"전월 대비 {mom:+.1f}%")
if yoy is not None and prev_yoy is not None and abs(yoy - prev_yoy) >= 10: reasons.append(f"전년 대비 증가율 {abs(yoy-prev_yoy):.1f}%p 변화")
if yoy is not None and abs(yoy) >= 30: reasons.append(f"전년 대비 고강도 변화 {yoy:+.1f}%")
if revision: reasons.append("동일 기준월 공식치 2% 이상 수정")
should_alert = baseline or (new_period and bool(reasons)) or revision

pending = {
    "last_period": period,
    "last_value_musd": value,
    "last_mom_pct": mom,
    "last_yoy_pct": yoy,
    "last_prev_yoy_pct": prev_yoy,
    "record_high": record,
    "last_fx_krw_per_usd": fx,
    "fx_source": fx_source,
    "updated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    "tail": [{"period": f"{sy:04d}-{sm:02d}", "value_musd": sv} for sy, sm, sv in series[-18:]],
}
PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

if should_alert:
    title = "✅ 미국 AI 데이터센터 건설지출 감시 연결 완료" if baseline else "🚨 미국 AI 데이터센터 건설지출 추세 변화"
    why = "현재 공식 수치를 기준선으로 저장. 이후 의미 있는 변화만 알림" if baseline else " / ".join(reasons)
    monthly = value / 12
    trend = ""
    if yoy is not None and prev_yoy is not None:
        trend = f"전년 대비 증가율 {'가속' if yoy > prev_yoy else '둔화'} ({prev_yoy:+.1f}% → {yoy:+.1f}%)"
    msg = [
        title, "",
        f"• 기준: {y}년 {m}월 / U.S. Census / 계절조정 연율(SAAR)",
        f"• 건설지출: ${value/1000:,.1f}B ({krw(value, fx)})",
        f"• 전월 대비: {fp(mom)} | 전년 대비: {fp(yoy)}",
        f"• 월간 속도 단순환산(SAAR÷12): ${monthly/1000:,.2f}B ({krw(monthly, fx)})",
        f"• 기록: {'사상 최고치' if record else '사상 최고치 아님'}",
        f"• 추세: {trend or '비교값 확인 중'}",
        f"• 알림 사유: {why}", "",
        "해석",
        "• 계획 CAPEX가 실제 데이터센터 건설 현장 지출로 전환되는 속도를 보는 공식 지표입니다.",
        "• 상승 지속은 전력기기·버스덕트·케이블·UPS·냉각·현장 발전 발주에 우호적입니다.",
        "• SAAR는 해당 월 실제 현금지출액이 아니며 GPU·HBM·서버 전체 CAPEX도 포함하지 않습니다.", "",
        "다음 확인: 신규 착공액 → 전력기기 실제 수주 → 전원 인가 MW → 서버 반입 → 실제 가동 MW",
    ]
    if fx: msg.append(f"원화 환산: 1달러={fx:,.2f}원 ({fx_source})")
    msg += ["", f"원문: {SOURCE}"]
    ALERT.write_text("\n".join(msg) + "\n", encoding="utf-8")

STATUS.write_text(
    f"# 데이터센터 증가 감시\n\n- 최신: **{period}**\n- SAAR: **${value/1000:,.1f}B**\n- MoM: **{fp(mom)}**\n- YoY: **{fp(yoy)}**\n- 최고치: **{'예' if record else '아니오'}**\n- 알림: **{'예' if should_alert else '아니오'}**\n- 사유: **{', '.join(reasons) if reasons else '기준선/임계치 미충족'}**\n",
    encoding="utf-8",
)
print(f"period={period} value={value} mom={mom:.2f} yoy={yoy:.2f} alert={should_alert}")
