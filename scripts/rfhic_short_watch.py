#!/usr/bin/env python3
import datetime as dt
import json
import pathlib
from zoneinfo import ZoneInfo

import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "rfhic_short_watch_state.json"
OUT_DIR = ROOT / "out"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TICKER = "218410"
NAME = "RFHIC"
KRX_URL = "https://data.krx.co.kr/comm/srt/srtLoader/index.cmd?isuCd=218410&screenId=MDCSTAT300"
KRX_API = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
SOURCE_VERSION = 3

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "*/*",
    "Referer": "https://data.krx.co.kr/contents/MDC/MDI/outerLoader/index.cmd",
    "X-Requested-With": "XMLHttpRequest",
}


def now_kst():
    return dt.datetime.now(ZoneInfo("Asia/Seoul"))


def load_state():
    if not STATE_PATH.exists():
        return None
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def as_num(value, kind=float):
    if value is None:
        return kind(0)
    s = str(value).replace(",", "").strip()
    if s in ("", "-"):
        return kind(0)
    return kind(float(s)) if kind is int else kind(s)


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


def date_norm(s):
    return str(s or "").replace("/", "-")


def krx_post(session, bld, **params):
    data = dict(params)
    data["bld"] = bld
    r = session.post(KRX_API, headers=HEADERS, data=data, timeout=30)
    if not r.ok:
        raise RuntimeError(
            f"KRX 요청 실패: status={r.status_code} bld={bld} body={r.text[:500]!r}"
        )
    try:
        return r.json()
    except Exception as exc:
        raise RuntimeError(
            f"KRX JSON 응답 해석 실패: status={r.status_code} bld={bld} body={r.text[:500]!r}"
        ) from exc


def find_isin(session):
    payload = krx_post(
        session,
        "dbms/comm/finder/finder_stkisu",
        locale="ko_KR",
        mktsel="ALL",
        searchText=NAME,
        typeNo="0",
    )
    rows = payload.get("block1") or []
    for row in rows:
        if str(row.get("short_code", "")).strip() == TICKER:
            full = str(row.get("full_code", "")).strip()
            if full:
                return full
    raise RuntimeError(f"KRX 종목검색에서 {NAME}({TICKER}) ISIN을 찾지 못했습니다")


def extract_latest():
    now = now_kst()
    start = (now.date() - dt.timedelta(days=14)).strftime("%Y%m%d")
    end = now.date().strftime("%Y%m%d")

    session = requests.Session()
    session.get(
        "https://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd",
        headers=HEADERS,
        timeout=30,
    )
    isin = find_isin(session)

    volume_payload = krx_post(
        session,
        "dbms/MDC/STAT/srt/MDCSTAT30102",
        strtDd=start,
        endDd=end,
        isuCd=isin,
    )
    balance_payload = krx_post(
        session,
        "dbms/MDC/STAT/srt/MDCSTAT30502",
        strtDd=start,
        endDd=end,
        isuCd=isin,
    )

    volume_rows = volume_payload.get("OutBlock_1") or []
    balance_rows = balance_payload.get("OutBlock_1") or []
    if not volume_rows:
        raise RuntimeError("KRX 공매도 거래 데이터가 비어 있습니다")
    if not balance_rows:
        raise RuntimeError("KRX 공매도 순보유잔고 데이터가 비어 있습니다")

    v = volume_rows[0]
    b = balance_rows[0]
    prev = balance_rows[1] if len(balance_rows) >= 2 else None

    short_volume = as_num(v.get("CVSRTSELL_TRDVOL"), int)
    total_volume = as_num(v.get("ACC_TRDVOL"), int)
    short_ratio = as_num(v.get("TRDVOL_WT"), float)

    short_balance = as_num(b.get("BAL_QTY"), int)
    listed_shares = as_num(b.get("LIST_SHRS"), int)
    balance_value = as_num(b.get("BAL_AMT"), float)
    market_cap = as_num(b.get("MKTCAP"), float)
    balance_ratio = as_num(b.get("BAL_RTO"), float)

    prev_balance = as_num(prev.get("BAL_QTY"), int) if prev else None
    prev_balance_date = date_norm(prev.get("RPT_DUTY_OCCR_DD")) if prev else None
    delta = short_balance - prev_balance if prev_balance is not None else None
    delta_pct = (delta / prev_balance * 100) if prev_balance not in (None, 0) else None

    return {
        "ticker": TICKER,
        "name": NAME,
        "isin": isin,
        "volume_date": date_norm(v.get("TRD_DD")),
        "short_volume": short_volume,
        "uptick_volume": as_num(v.get("UPTICKRULE_APPL_TRDVOL"), int),
        "uptick_except_volume": as_num(v.get("UPTICKRULE_EXCPT_TRDVOL"), int),
        "total_volume": total_volume,
        "short_ratio": short_ratio,
        "short_value": as_num(v.get("CVSRTSELL_TRDVAL"), float),
        "balance_date": date_norm(b.get("RPT_DUTY_OCCR_DD")),
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
        interpretation = "순보유잔고의 이전 비교값이 없어 방향 판단을 보류합니다."
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
    print(f"isin={data['isin']} volume_date={data['volume_date']} balance_date={data['balance_date']} rebaseline={rebaseline} new={is_new}")


if __name__ == "__main__":
    main()
