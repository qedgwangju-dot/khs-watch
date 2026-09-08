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
    return (float(old), "직전 저장 환율") if old else (None, "조회 실패")


def krw(usd_million, fx):
    if not fx:
        raise RuntimeError("KRW conversion unavailable")
    eok = round(usd_million * fx / 100)
    jo, rem = divmod(eok, 10000)
    if jo and rem:
        return f"약 {jo:,}조 {rem:,}억원"
    if jo:
        return f"약 {jo:,}조원"
    return f"약 {rem:,}억원"


def fp(x):
    return "확인 불가" if x is None else f"{x:+.2f}%"


def fpp(x):
    return "확인 불가" if x is None else f"{x:+.2f}%p"


def usd_exact(usd_million):
    return f"${usd_million/1000:,.3f}B (원자료 {usd_million:,.0f}백만달러)"


def money_line(label, usd_million, fx):
    return f"• {label}: {usd_exact(usd_million)} = {krw(usd_million, fx)}"


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
prev = lookup.get((py, pm))
ago = lookup.get((yy, ym))
ago_prev = lookup.get((pyy, pym))
mom = pct(value, prev)
yoy = pct(value, ago)
prev_yoy = pct(prev, ago_prev) if prev and ago_prev else None
yoy_accel = (yoy - prev_yoy) if yoy is not None and prev_yoy is not None else None
prior_vals = [v for sy, sm, v in series if (sy, sm) < (y, m)]
prior_record = max(prior_vals) if prior_vals else None
record = prior_record is None or value > prior_record

old = load_state()
period = f"{y:04d}-{m:02d}"
baseline = not old.get("last_period")
new_period = old.get("last_period") != period
revision_pct = None
if not new_period and old.get("last_value_musd"):
    revision_pct = pct(value, float(old["last_value_musd"]))
revision = revision_pct is not None and abs(revision_pct) >= 2
fx, fx_source = fx_rate(old.get("last_fx_krw_per_usd"))
if not fx:
    raise SystemExit("USD/KRW 환율을 확보하지 못해 원화 병기 없이 알림을 보내지 않습니다.")
fx_checked_utc = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
reasons = []
if record:
    reasons.append("사상 최고치 경신")
if mom is not None and abs(mom) >= 5:
    reasons.append(f"전월 대비 {mom:+.2f}%")
if yoy_accel is not None and abs(yoy_accel) >= 10:
    reasons.append(f"전년 대비 증가율 {abs(yoy_accel):.2f}%p 변화")
if yoy is not None and abs(yoy) >= 30:
    reasons.append(f"전년 대비 고강도 변화 {yoy:+.2f}%")
if revision:
    reasons.append(f"동일 기준월 공식치 {revision_pct:+.2f}% 수정")
should_alert = baseline or (new_period and bool(reasons)) or revision

pending = {
    "last_period": period,
    "last_value_musd": value,
    "last_mom_pct": mom,
    "last_yoy_pct": yoy,
    "last_prev_yoy_pct": prev_yoy,
    "last_yoy_accel_pctp": yoy_accel,
    "record_high": record,
    "last_fx_krw_per_usd": fx,
    "fx_source": fx_source,
    "fx_checked_utc": fx_checked_utc,
    "updated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    "tail": [{"period": f"{sy:04d}-{sm:02d}", "value_musd": sv} for sy, sm, sv in series[-18:]],
}
PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

if should_alert:
    title = "✅ 미국 AI 데이터센터 건설지출 감시 연결 완료" if baseline else "🚨 미국 AI 데이터센터 건설지출 추세 변화"
    why = "현재 공식 수치를 기준선으로 저장. 이후 의미 있는 변화만 알림" if baseline else " / ".join(reasons)
    monthly = value / 12
    trend_word = "가속" if yoy_accel is not None and yoy_accel > 0 else "둔화"
    msg = [
        title,
        "",
        "[현재 숫자]",
        f"• 기준월: {y}년 {m}월",
        "• 공식 기준: U.S. Census / 민간 데이터센터 건설지출 / 계절조정 연율(SAAR)",
        money_line("공식치", value, fx),
        money_line("전월 공식치", prev, fx) if prev is not None else "• 전월 공식치: 확인 불가",
        f"• 전월 대비: {fp(mom)}",
        money_line("전년동월 공식치", ago, fx) if ago is not None else "• 전년동월 공식치: 확인 불가",
        f"• 전년 대비: {fp(yoy)}",
    ]
    if prev_yoy is not None and yoy_accel is not None:
        msg += [
            f"• 직전월 전년 대비: {fp(prev_yoy)}",
            f"• 증가율 변화: {fpp(yoy_accel)} → {trend_word}",
        ]
    msg += [
        f"• 사상 최고치: {'예' if record else '아니오'}",
        "",
        "[월간 속도 환산]",
        money_line("SAAR÷12", monthly, fx),
        "• 주의: 위 값은 연율을 12로 나눈 산술 환산이며 Census의 비계절조정 실제 월간 지출액이 아닙니다.",
        "",
        "[알림 사유]",
        f"• {why}",
    ]
    if revision:
        old_value = float(old["last_value_musd"])
        msg += [
            money_line("수정 전", old_value, fx),
            money_line("수정 후", value, fx),
            f"• 수정폭: {fp(revision_pct)}",
        ]
    msg += [
        "",
        "[해석]",
        "• 계획 설비투자가 실제 데이터센터 건설 현장 지출로 전환되는 속도를 보는 공식 지표입니다.",
        "• 상승 지속은 전력기기·버스덕트·케이블·무정전전원장치·냉각·현장 발전 발주에 우호적입니다.",
        "• 다만 이 수치는 GPU·HBM·서버 전체 설비투자액이 아니라 건설공사 집행액입니다.",
        "",
        "[다음 확인]",
        "• 신규 착공액 → 전력기기 실제 수주 → 전원 인가 MW → 서버 반입 → 실제 가동 MW",
        "",
        "[환율]",
        f"• 1달러 = {fx:,.2f}원",
        f"• 출처: {fx_source}",
        f"• 조회시각(UTC): {fx_checked_utc}",
        "• 모든 외화 금액은 같은 알림 안에서 위 환율로 원화 환산해 병기합니다.",
        "• 최신 환율 조회가 실패하면 직전 저장 환율을 명시해 사용하며, 환율 자체가 없으면 원화 없는 알림은 보내지 않습니다.",
        "",
        f"원문: {SOURCE}",
    ]
    ALERT.write_text("\n".join(msg) + "\n", encoding="utf-8")

STATUS.write_text(
    f"# 데이터센터 증가 감시\n\n"
    f"- 최신 기준월: **{period}**\n"
    f"- 공식 SAAR: **{usd_exact(value)} = {krw(value, fx)}**\n"
    f"- 전월 공식치: **{usd_exact(prev)} = {krw(prev, fx)}**\n" if prev is not None else ""
    f"- 전월 대비: **{fp(mom)}**\n"
    f"- 전년동월 공식치: **{usd_exact(ago)} = {krw(ago, fx)}**\n" if ago is not None else ""
    f"- 전년 대비: **{fp(yoy)}**\n"
    f"- 직전월 전년 대비: **{fp(prev_yoy)}**\n"
    f"- 증가율 변화: **{fpp(yoy_accel)}**\n"
    f"- 사상 최고치: **{'예' if record else '아니오'}**\n"
    f"- 알림: **{'예' if should_alert else '아니오'}**\n"
    f"- 사유: **{', '.join(reasons) if reasons else '기준선/임계치 미충족'}**\n"
    f"- 환율: **1달러={fx:,.2f}원 ({fx_source})**\n",
    encoding="utf-8",
)
print(
    f"period={period} value_musd={value:.0f} "
    f"mom={mom:.2f} yoy={yoy:.2f} prev_yoy={prev_yoy:.2f} "
    f"yoy_accel={yoy_accel:.2f} fx={fx:.2f} alert={should_alert}"
)
