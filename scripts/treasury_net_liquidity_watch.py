#!/usr/bin/env python3
"""Treasury/Fed net-liquidity watcher for long-rate interpretation.

This watcher intentionally does NOT duplicate QRA, buyback-policy, buyback-execution,
CTA-squeeze, or TIC alerts. It answers one question only:

    Did Treasury/Fed cash operations actually add or drain dollar liquidity?

Core inputs
- Treasury Daily Treasury Statement (daily TGA closing balance)
- Treasury public debt transactions (daily Bill issues/redemptions)
- Fed H.4.1/FRED: Treasury securities held outright (TREAST), reserve balances (WRESBAL)
- NY Fed/FRED: ON RRP (RRPONTSYD)

Because the source frequencies differ, the script does NOT add daily TGA and weekly Fed
series into a fake precise 'net liquidity dollars' number. It reports each leg separately
and assigns only a directional regime.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
OUT.mkdir(parents=True, exist_ok=True)
STATE_PATH = ROOT / "data" / "treasury_net_liquidity_state.json"
NEXT_STATE = OUT / "treasury_net_liquidity_state_next.json"
ALERT = OUT / "treasury_net_liquidity_alert.html"
TITLE = OUT / "treasury_net_liquidity_title.txt"
DETAIL = OUT / "treasury_net_liquidity_detail.json"
STATUS = OUT / "treasury_net_liquidity_status.md"

KST = ZoneInfo("Asia/Seoul")
UA = "Mozilla/5.0 (compatible; khs-watch-treasury-liquidity/1.0)"
FISCAL_BASE = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts"
TGA_URL = f"{FISCAL_BASE}/operating_cash_balance"
DEBT_URL = f"{FISCAL_BASE}/public_debt_transactions"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
DTS_PAGE = "https://fiscaldata.treasury.gov/datasets/daily-treasury-statement/operating-cash-balance"
FED_H41 = "https://www.federalreserve.gov/releases/h41/current/"
NYFED_RRP = "https://www.newyorkfed.org/markets/desk-operations/reverse-repo"


def fetch(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json,text/csv,*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def api(path: str, params: dict) -> dict:
    url = path + "?" + urllib.parse.urlencode(params)
    return json.loads(fetch(url).decode("utf-8"))


def f(v):
    try:
        return float(str(v).replace(",", ""))
    except Exception:
        return None


def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def fred(series: str, n: int = 12) -> list[tuple[str, float]]:
    url = FRED_CSV + "?" + urllib.parse.urlencode({"id": series})
    text = fetch(url).decode("utf-8-sig", errors="replace")
    out = []
    for line in text.splitlines()[1:]:
        p = line.split(",")
        if len(p) >= 2 and p[1].strip() not in {"", "."}:
            try:
                out.append((p[0].strip(), float(p[1].strip())))
            except ValueError:
                pass
    return out[-n:]


def latest_fx() -> tuple[str | None, float | None]:
    rows = fred("DEXKOUS", 5)
    return rows[-1] if rows else (None, None)


def krw_usd_bn(usd_bn: float | None, fx: float | None) -> str:
    if usd_bn is None or fx is None:
        return "원화 환산 확인 불가"
    won = usd_bn * 1e9 * fx
    if abs(won) >= 1e12:
        return f"약 {won/1e12:,.2f}조원"
    return f"약 {won/1e8:,.0f}억원"


def tga_rows() -> list[dict]:
    obj = api(TGA_URL, {"sort": "-record_date", "page[size]": 30, "format": "json"})
    rows = []
    for x in obj.get("data", []):
        acct = str(x.get("account_type") or "")
        # The API can contain multiple account rows; prefer Treasury General Account / Federal Reserve Account.
        if "treasury general" not in acct.lower() and "federal reserve" not in acct.lower():
            continue
        bal_mn = f(x.get("close_today_bal"))
        if bal_mn is not None:
            rows.append({"date": x.get("record_date"), "tga_bn": bal_mn / 1000.0})
    # Deduplicate date while preserving newest first.
    out, seen = [], set()
    for x in rows:
        if x["date"] not in seen:
            out.append(x); seen.add(x["date"])
    return out


def bill_net_by_date() -> dict[str, float]:
    obj = api(DEBT_URL, {"sort": "-record_date", "page[size]": 500, "format": "json"})
    out: dict[str, float] = {}
    for x in obj.get("data", []):
        desc = " ".join([str(x.get("security_type") or ""), str(x.get("security_type_desc") or "")]).lower()
        if "bill" not in desc:
            continue
        amt_mn = f(x.get("transaction_today_amt"))
        if amt_mn is None:
            continue
        typ = str(x.get("transaction_type") or "").lower()
        sign = 1.0 if "issue" in typ else -1.0 if "redemp" in typ else 0.0
        if sign:
            d = str(x.get("record_date") or "")
            out[d] = out.get(d, 0.0) + sign * amt_mn / 1000.0
    return out


def delta(rows: list[tuple[str, float]], lookback: int = 1) -> tuple[str | None, float | None, float | None]:
    if len(rows) <= lookback:
        return (rows[-1][0], rows[-1][1], None) if rows else (None, None, None)
    return rows[-1][0], rows[-1][1], rows[-1][1] - rows[-1-lookback][1]


def bucket(name: str, value: float | None) -> int:
    if value is None:
        return 0
    limits = {
        "tga1": 50.0,
        "tga5": 100.0,
        "bill5": 100.0,
        "treast1": 5.0,
        "res1": 75.0,
        "rrp5": 10.0,
    }
    lim = limits[name]
    return 1 if value >= lim else -1 if value <= -lim else 0


def main() -> int:
    now = dt.datetime.now(KST)
    errors = []
    try:
        tga = tga_rows()
    except Exception as e:
        tga = []; errors.append(f"TGA: {type(e).__name__}: {e}")
    try:
        bill = bill_net_by_date()
    except Exception as e:
        bill = {}; errors.append(f"Bills: {type(e).__name__}: {e}")
    try:
        treast = fred("TREAST", 8)  # millions USD
        treast = [(d, v/1000.0) for d,v in treast]
    except Exception as e:
        treast = []; errors.append(f"TREAST: {type(e).__name__}: {e}")
    try:
        reserves = fred("WRESBAL", 8)
        reserves = [(d, v/1000.0) for d,v in reserves]
    except Exception as e:
        reserves = []; errors.append(f"WRESBAL: {type(e).__name__}: {e}")
    try:
        rrp = fred("RRPONTSYD", 10)  # already billions
    except Exception as e:
        rrp = []; errors.append(f"RRP: {type(e).__name__}: {e}")

    if len(tga) < 2 or not treast or not reserves:
        STATUS.write_text(
            "# TGA·Bill·SOMA 순유동성 감시\n\n"
            f"- 조회: {now.isoformat(timespec='seconds')}\n"
            f"- 상태: 확인 불가 — 핵심 공식 데이터 누락\n"
            + ("\n".join(f"- {x}" for x in errors) if errors else ""), encoding="utf-8")
        return 2

    tga = sorted(tga, key=lambda x: x["date"])
    tga_latest = tga[-1]
    tga1 = tga[-1]["tga_bn"] - tga[-2]["tga_bn"]
    tga5 = tga[-1]["tga_bn"] - tga[max(0, len(tga)-6)]["tga_bn"]
    recent_dates = [x["date"] for x in tga[-5:]]
    bill5 = sum(bill.get(d, 0.0) for d in recent_dates)

    treast_date, treast_level, treast1 = delta(treast, 1)
    res_date, res_level, res1 = delta(reserves, 1)
    rrp_date, rrp_level, rrp5 = delta(rrp, min(4, len(rrp)-1)) if rrp else (None, None, None)
    fx_date, fx = latest_fx()

    # Liquidity direction: TGA falling is positive, Fed Treasury holdings rising positive,
    # RRP falling positive. Bill net issuance is negative. Reserve balances are confirmation.
    legs = {
        "tga1": bucket("tga1", tga1),
        "tga5": bucket("tga5", tga5),
        "bill5": bucket("bill5", bill5),
        "treast1": bucket("treast1", treast1),
        "res1": bucket("res1", res1),
        "rrp5": bucket("rrp5", rrp5),
    }
    directional_score = (-legs["tga5"]) + (-legs["bill5"]) + legs["treast1"] + (-legs["rrp5"]) + legs["res1"]
    regime = "🟢 순유동성 완화 방향" if directional_score >= 2 else "🔴 순유동성 긴축 방향" if directional_score <= -2 else "🟡 순유동성 혼조"

    snapshot = {
        "tga_date": tga_latest["date"], "tga_bn": tga_latest["tga_bn"], "tga1_bn": tga1, "tga5_bn": tga5,
        "bill5_bn": bill5,
        "treast_date": treast_date, "treast_bn": treast_level, "treast1_bn": treast1,
        "reserves_date": res_date, "reserves_bn": res_level, "reserves1_bn": res1,
        "rrp_date": rrp_date, "rrp_bn": rrp_level, "rrp5_bn": rrp5,
        "regime": regime, "score": directional_score, "legs": legs,
    }
    state = load_state()
    prev = state.get("snapshot") or {}
    meaningful = (not state) or regime != prev.get("regime") or legs != prev.get("legs")

    NEXT_STATE.write_text(json.dumps({"snapshot": snapshot, "updated_at_kst": now.isoformat(timespec="seconds")}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    DETAIL.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")

    # First install = baseline only, no Telegram.
    if not state:
        STATUS.write_text(f"# TGA·Bill·SOMA 순유동성 감시\n\n- 조회: {now.isoformat(timespec='seconds')}\n- 상태: 초기 기준선 생성 — 발송 안 함\n", encoding="utf-8")
        return 0
    if not meaningful:
        STATUS.write_text(f"# TGA·Bill·SOMA 순유동성 감시\n\n- 조회: {now.isoformat(timespec='seconds')}\n- 상태: 의미 있는 유동성 레짐 변화 없음\n", encoding="utf-8")
        return 0

    def signed(v):
        return "확인 불가" if v is None else f"{v:+,.1f}십억달러"

    body = [
        f"<b>🎯 핵심 판단</b>\n{regime}",
        "",
        "<b>💵 실제 돈의 이동</b>",
        f"• TGA: <b>{tga_latest['tga_bn']:,.1f}십억달러</b> ({krw_usd_bn(tga_latest['tga_bn'], fx)})",
        f"  └ 1일 {signed(tga1)} / 최근 5영업일 {signed(tga5)}",
        f"• Bill 순발행(최근 5영업일): <b>{signed(bill5)}</b>",
        f"• Fed 보유 미 국채: {treast_level:,.1f}십억달러 / 주간 {signed(treast1)}" if treast_level is not None else "• Fed 보유 미 국채: 확인 불가",
        f"• 은행 지급준비금: {res_level:,.1f}십억달러 / 주간 {signed(res1)}" if res_level is not None else "• 은행 지급준비금: 확인 불가",
        f"• ON RRP: {rrp_level:,.3f}십억달러 / 최근 변화 {signed(rrp5)}" if rrp_level is not None else "• ON RRP: 확인 불가",
        "",
        "<b>🧭 쉽게 해석하면</b>",
    ]
    if regime.startswith("🟢"):
        body.append("TGA 감소·Fed 보유국채 증가·RRP 감소·준비금 증가 중 여러 축이 유동성 공급 방향으로 겹침 → 장기금리·위험자산 할인율에 우호적인 수급 환경.")
    elif regime.startswith("🔴"):
        body.append("TGA 적립·Bill 순발행·Fed 유동성 축소 중 여러 축이 겹침 → 시중 달러 흡수 → 장기금리 및 성장주 할인율에 부담.")
    else:
        body.append("Treasury와 Fed의 현금 흐름이 서로 상쇄되고 있어 한 방향의 순유동성 신호로 보기 어려움.")
    body += [
        "",
        "<b>🔗 바이백과 연결</b>",
        "장기채 바이백 자체는 별도 ‘실제 집행’ 알림이 담당합니다. 여기서는 그 결제 이후 TGA가 실제 줄었는지, Bill 발행으로 다시 채웠는지, Fed 준비금이 어떻게 변했는지만 확인합니다.",
        "",
        "<b>⚠️ 오해 방지</b>",
        "• TGA·RRP는 일별, Fed 보유국채·준비금은 주별이라 서로 다른 빈도의 금액을 단순 합산한 가짜 ‘순유동성 총액’은 만들지 않습니다.",
        "• Bill 순발행 증가가 곧바로 장기금리 악재라는 뜻은 아닙니다. 장기물 대신 단기물로 조달 부담을 옮기면 장기 듀레이션에는 오히려 상대적으로 우호적일 수 있습니다.",
        "• 최종 판단은 신규 10·20·30년 입찰수요와 CTA 숏커버 알림에서 교차검증합니다.",
        "",
        "<b>🔍 다음 확인</b>",
        "TGA 5일 변화 · Bill 순발행 · Fed TREAST · 지급준비금 · ON RRP · 10/20/30년 입찰 결과",
        "",
        f"환율 기준: FRED DEXKOUS {fx_date or '확인 불가'}, 1달러={fx:,.2f}원" if fx is not None else "환율 기준: FRED DEXKOUS 확인 불가 — 원화 환산 미제공",
        f'<a href="{DTS_PAGE}">미 재무부 일일 TGA 원문</a> · <a href="{FED_H41}">Fed H.4.1</a> · <a href="{NYFED_RRP}">NY Fed ON RRP</a>',
    ]
    TITLE.write_text("🇺🇸 TGA·Bill·SOMA 순유동성 — 실제 달러가 들어오나 빠지나", encoding="utf-8")
    ALERT.write_text("\n".join(body), encoding="utf-8")
    STATUS.write_text(f"# TGA·Bill·SOMA 순유동성 감시\n\n- 조회: {now.isoformat(timespec='seconds')}\n- 상태: 유동성 레짐 변화 감지 — {regime}\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
