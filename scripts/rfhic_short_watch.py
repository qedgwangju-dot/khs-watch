#!/usr/bin/env python3
import datetime as dt
import json
import pathlib
from zoneinfo import ZoneInfo

from pykrx import stock

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "rfhic_short_watch_state.json"
OUT_DIR = ROOT / "out"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TICKER = "218410"
NAME = "RFHIC"
KRX_URL = "https://data.krx.co.kr/comm/srt/srtLoader/index.cmd?isuCd=218410&screenId=MDCSTAT300"
SOURCE_VERSION = 4


def now_kst():
    return dt.datetime.now(ZoneInfo("Asia/Seoul"))


def load_state():
    if not STATE_PATH.exists():
        return None
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def fmt_int(v):
    try:
        return f"{int(round(float(v))):,}"
    except Exception:
        return "-"


def fmt_pct(v, digits=2):
    try:
        return f"{float(v):,.{digits}f}%"
    except Exception:
        return "-"


def fmt_krw(v):
    try:
        n = float(v)
    except Exception:
        return "-"
    if abs(n) >= 100_000_000:
        return f"{n / 100_000_000:,.2f}억원"
    if abs(n) >= 10_000:
        return f"{n / 10_000:,.1f}만원"
    return f"{n:,.0f}원"


def date_str(x):
    return x.strftime("%Y-%m-%d") if hasattr(x, "strftime") else str(x)[:10]


def extract_latest():
    now = now_kst()
    start = (now.date() - dt.timedelta(days=14)).strftime("%Y%m%d")
    end = now.date().strftime("%Y%m%d")

    volume = stock.get_shorting_volume_by_date(start, end, TICKER)
    value = stock.get_shorting_value_by_date(start, end, TICKER)
    balance = stock.get_shorting_balance_by_date(start, end, TICKER)

    if volume is None or volume.empty:
        raise RuntimeError("KRX 공매도 거래 데이터가 비어 있습니다")
    if balance is None or balance.empty:
        raise RuntimeError("KRX 공매도 순보유잔고 데이터가 비어 있습니다")

    volume = volume.sort_index()
    value = value.sort_index()
    balance = balance.sort_index()

    v = volume.iloc[-1]
    v_date = date_str(volume.index[-1])
    short_volume = int(v["공매도"])
    total_volume = int(v["매수"])
    short_ratio = float(v["비중"])

    short_value = 0.0
    if value is not None and not value.empty and volume.index[-1] in value.index:
        short_value = float(value.loc[volume.index[-1], "공매도"])

    b = balance.iloc[-1]
    b_date = date_str(balance.index[-1])
    short_balance = int(b["공매도잔고"])
    listed_shares = int(b["상장주식수"])
    balance_value = float(b["공매도금액"])
    market_cap = float(b["시가총액"])
    balance_ratio = float(b["비중"])

    prev_balance = None
    prev_balance_date = None
    if len(balance) >= 2:
        p = balance.iloc[-2]
        prev_balance = int(p["공매도잔고"])
        prev_balance_date = date_str(balance.index[-2])

    delta = short_balance - prev_balance if prev_balance is not None else None
    delta_pct = (delta / prev_balance * 100) if prev_balance not in (None, 0) else None

    return {
        "ticker": TICKER,
        "name": NAME,
        "volume_date": v_date,
        "short_volume": short_volume,
        "total_volume": total_volume,
        "short_ratio": short_ratio,
        "short_value": short_value,
        "balance_date": b_date,
        "short_balance": short_balance,
        "listed_shares": listed_shares,
        "balance_value": balance_value,
        "market_cap": market_cap,
        "balance_ratio": balance_ratio,
        "prev_balance_date": prev_balance_date,
        "prev_balance": prev_balance,
        "balance_delta": delta,
        "balance_delta_pct": delta_pct,
        "checked_at_kst": now.isoformat(timespec="seconds"),
    }


def make_alert(d):
    delta = d["balance_delta"]
    if delta is None:
        delta_text = "비교값 없음"
    else:
        arrow = "증가" if delta > 0 else "감소" if delta < 0 else "변화없음"
        pct = f" ({d['balance_delta_pct']:+.2f}%)" if d["balance_delta_pct"] is not None else ""
        delta_text = f"{arrow} {fmt_int(abs(delta))}주{pct}"

    if delta is None:
        interpretation = "순보유잔고 이전 비교값이 없어 방향 판단을 보류합니다."
    elif delta > 0:
        interpretation = "당일 공매도와 별개로 신고대상 순보유잔고도 늘어, 실제 누적 숏 포지션이 최근 더 쌓인 방향입니다."
    elif delta < 0:
        interpretation = "당일 공매도 거래가 있어도 신고대상 순보유잔고는 줄어, 실제 누적 숏 포지션은 최근 감소한 방향입니다."
    else:
        interpretation = "신고대상 순보유잔고는 직전 보고일과 같습니다."

    return (
        f"📉 {NAME}({TICKER}) KRX 공매도\n\n"
        f"[당일 거래 {d['volume_date']}]\n"
        f"• 공매도량: {fmt_int(d['short_volume'])}주\n"
        f"• 공매도량 비율: {fmt_pct(d['short_ratio'])}\n"
        f"• 공매도 거래대금: {fmt_krw(d['short_value'])}\n"
        f"• 전체 거래량: {fmt_int(d['total_volume'])}주\n\n"
        f"[최신 순보유잔고 {d['balance_date']}] ※ KRX T+2 보고\n"
        f"• 순보유잔고수량: {fmt_int(d['short_balance'])}주\n"
        f"• 상장주식수 대비: {fmt_pct(d['balance_ratio'])}\n"
        f"• 순보유잔고금액: {fmt_krw(d['balance_value'])}\n"
        f"• 직전 보고일 대비: {delta_text}\n\n"
        f"판단: {interpretation}\n"
        f"원문: {KRX_URL}\n"
    )


def main():
    state = load_state()
    data = extract_latest()
    rebaseline = state is None or state.get("source_version") != SOURCE_VERSION
    previous_volume_date = (state or {}).get("last_sent_volume_date")
    is_new = (not rebaseline) and data["volume_date"] != previous_volume_date

    pending = {
        "source_version": SOURCE_VERSION,
        "ticker": TICKER,
        "name": NAME,
        "last_checked_kst": data["checked_at_kst"],
        "last_seen_volume_date": data["volume_date"],
        "last_seen_balance_date": data["balance_date"],
        "last_snapshot": data,
        "last_sent_volume_date": previous_volume_date,
    }

    if rebaseline:
        pending["last_sent_volume_date"] = data["volume_date"]
        (OUT_DIR / "rfhic_short_watch_rebaseline.txt").write_text("baseline\n", encoding="utf-8")
    elif is_new:
        (OUT_DIR / "rfhic_short_watch_alert.txt").write_text(make_alert(data), encoding="utf-8")
        (OUT_DIR / "rfhic_short_watch_alert.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        pending["last_sent_volume_date"] = data["volume_date"]

    (OUT_DIR / "rfhic_short_watch_pending_state.json").write_text(
        json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    status = (
        "# RFHIC 공매도 감시 상태\n\n"
        f"- 확인시각: {data['checked_at_kst']}\n"
        f"- 최신 당일 공매도 데이터: {data['volume_date']} / {fmt_int(data['short_volume'])}주 / {fmt_pct(data['short_ratio'])}\n"
        f"- 최신 순보유잔고: {data['balance_date']} / {fmt_int(data['short_balance'])}주 / {fmt_pct(data['balance_ratio'])}\n"
        f"- 초기 기준값 생성: {'예' if rebaseline else '아니오'}\n"
        f"- 신규 Telegram 알림: {'예' if is_new else '아니오'}\n"
    )
    (OUT_DIR / "rfhic_short_watch_status.md").write_text(status, encoding="utf-8")
    print(f"volume_date={data['volume_date']} balance_date={data['balance_date']} rebaseline={rebaseline} new={is_new}")


if __name__ == "__main__":
    main()
