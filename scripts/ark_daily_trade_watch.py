#!/usr/bin/env python3
"""ARK official daily trading monitor (separate from quarterly 13F).
Source: ARK's latest trade file. The file is an unreconciled activity notice,
not the exact fill price nor the comprehensive set of ETF creations/redemptions.
"""
import argparse
import csv
import datetime as dt
import hashlib
import html
import io
import json
import os
import pathlib
import re
import urllib.request
import zoneinfo
import math
import ark_notional_enrichment as notional
import ark_sector_rank as sector_rank

SOURCE="https://etfs.ark-funds.com/hubfs/idt/trades/ARK_Trades.xls"
DISCLOSURE="https://www.ark-funds.com/ark-trade-notifications"
STATE=pathlib.Path("data/ark_daily_trades_watch_state.json")
OUT=pathlib.Path("out")
FUNDS={"ARKK","ARKQ","ARKX","ARKG","ARKW","ARKF"}
NAMES={
    "XE":"엑스에너지","OKLO":"오클로","LUNR":"인튜이티브 머신스",
    "IAM":"아이앰빅 테라퓨틱스","SCTX":"스크라이브 테라퓨틱스",
    "PACB":"팩바이오","PLTR":"팔란티어","SHOP":"쇼피파이",
    "TER":"테라다인","ESLT":"엘빗 시스템즈","PSNL":"퍼스널리스",
    "HO":"탈레스","CRWV":"코어위브","BABA":"알리바바","DKNG":"드래프트킹스",
    "META":"메타 플랫폼스","ISRG":"인튜이티브 서지컬",
    "FRNM":"프리놈","XYZ":"블록","RBLX":"로블록스",
    "CBRS":"세레브라스 시스템즈","JOBY":"조비 에비에이션","KDK":"코디악 AI",
    "BEAM":"빔 테라퓨틱스","ARCT":"아크투루스 테라퓨틱스",
    "TEM":"템퍼스 AI","TXG":"10x 지노믹스",
}
ET=zoneinfo.ZoneInfo("America/New_York")
REPORT_FORMAT_VERSION=3

def _fetch():
    req=urllib.request.Request(SOURCE, headers={
        "User-Agent":"Mozilla/5.0 (KHS-ARK-Trades-Monitor; fund holdings audit)",
        "Accept":"application/vnd.ms-excel,text/csv,*/*",
    })
    with urllib.request.urlopen(req,timeout=35) as response:
        payload=response.read(5_000_001)
        kind=response.headers.get("Content-Type","")
    if len(payload)>5_000_000 or len(payload)<40:
        raise ValueError("Invalid official ARK trade file size")
    return payload,kind

def _all_rows(payload):
    """Accept ARK Excel 97, modern xlsx and CSV/text under a .xls URL."""
    if payload.startswith(b"\xd0\xcf\x11\xe0"):
        import xlrd
        book=xlrd.open_workbook(file_contents=payload, ignore_workbook_corruption=True)
        return [[sh.cell_value(i,j) for j in range(sh.ncols)]
                for sh in book.sheets() for i in range(sh.nrows)]
    if payload.startswith(b"PK\x03\x04"):
        import openpyxl
        book=openpyxl.load_workbook(io.BytesIO(payload),read_only=True,data_only=True)
        try:
            return [[v for v in row] for sh in book for row in sh.iter_rows(values_only=True)]
        finally:
            book.close()
    if payload.lstrip().startswith(b"<"):
        import pandas as pd
        frames=pd.read_html(io.StringIO(payload.decode("utf-8","replace")))
        if not frames:
            raise ValueError("ARK spreadsheet HTML has no tables")
        return [list(map(str,df.columns)) for df in frames][:1]+[
            list(row) for df in frames for row in df.itertuples(index=False,name=None)]
    try:
        text=payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        text=payload.decode("latin1")
    if not ("ticker" in text.lower() and "share" in text.lower()):
        raise ValueError("Source did not return an ARK trade table")
    delimiter="\t" if text.count("\t")>text.count(",") else ","
    return list(csv.reader(io.StringIO(text),delimiter=delimiter))

def _norm(x):
    return re.sub(r"[^a-z0-9%]+","",str(x or "").lower())

def _col_index(header,candidates):
    flat=[_norm(x) for x in header]
    for candidate in candidates:
        normalized=_norm(candidate)
        if normalized in flat:
            return flat.index(normalized)
    for candidate in candidates:
        normalized=_norm(candidate)
        for i,v in enumerate(flat):
            if normalized and normalized in v:
                return i
    return None

def _date(value):
    if isinstance(value,dt.datetime):
        return value.date()
    if isinstance(value,dt.date):
        return value
    if isinstance(value,(int,float)) and 35000<float(value)<90000:
        return (dt.datetime(1899,12,30)+dt.timedelta(days=float(value))).date()
    v=str(value or "").strip()
    for fmt in ("%Y-%m-%d","%m/%d/%Y","%m/%d/%y","%Y/%m/%d","%d-%b-%Y"):
        try:
            return dt.datetime.strptime(v[:15],fmt).date()
        except ValueError:
            pass
    try:
        return dt.date.fromisoformat(v[:10])
    except ValueError:
        return None

def parse(payload):
    raw=_all_rows(payload)
    rows=[]
    matched=False
    for j in range(min(len(raw),30)):
        header=raw[j]
        mapping={
            "date":_col_index(header,["date","trade date"]),
            "fund":_col_index(header,["fund","etf"]),
            "direction":_col_index(header,["direction","action","trade"]),
            "ticker":_col_index(header,["ticker","symbol"]),
            "shares":_col_index(header,["shares","share count"]),
            "pct":_col_index(header,["% of etf","percent of etf","% of fund"]),
        }
        if any(mapping[k] is None for k in ["date","fund","direction","ticker","shares"]):
            continue
        matched=True
        for raw_row in raw[j+1:]:
            def val(key):
                idx=mapping[key]
                return raw_row[idx] if idx is not None and idx<len(raw_row) else ""
            fund=str(val("fund") or "").strip().upper()
            ticker=str(val("ticker") or "").strip().upper()
            direction=str(val("direction") or "").strip().upper()
            if fund not in FUNDS or not re.fullmatch(r"[A-Z0-9.\-]{1,10}",ticker):
                continue
            if direction in ("BUY","B","PURCHASE"):
                action="매수"
            elif direction in ("SELL","S","SALE"):
                action="매도"
            else:
                continue
            try:
                shares=round(float(str(val("shares")).replace(",","")))
            except (TypeError,ValueError):
                continue
            if not 0<abs(shares)<100_000_000:
                continue
            date=_date(val("date"))
            if not date:
                continue
            pct=None
            try:
                raw_pct=str(val("pct")).replace("%","").replace(",","").strip()
                pct=float(raw_pct) if raw_pct else None
            except (TypeError,ValueError):
                pass
            rows.append({"date":date.isoformat(),"fund":fund,"ticker":ticker,
                         "action":action,"shares":abs(shares),"pct":pct})
        break
    if not matched:
        raise ValueError("ARK official spreadsheet header/schema changed")
    if not rows:
        raise ValueError("Official ARK file has no parsable transactions")
    # Drop exact duplicated lines if the source file includes repeated sheet headers.
    uniq={}
    for row in rows:
        uniq[(row["date"],row["fund"],row["ticker"],row["action"],row["shares"])]=row
    return sorted(uniq.values(),key=lambda x:(x["date"],x["fund"],x["ticker"],x["action"]))

def _load():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"version":1,"last_date":"","digest":"","updated_at":None}

def _fingerprint(records):
    compact=[(r["date"],r["fund"],r["ticker"],r["action"],r["shares"]) for r in records]
    return hashlib.sha256(json.dumps(compact,ensure_ascii=False).encode()).hexdigest()[:24]

def _link(label,url):
    return f'<a href="{html.escape(url,quote=True)}">{html.escape(label)}</a>'

def build(rows, day, is_revision=False, rate=None, basis="", prices=None, enrichment=False,
          history=None, digest="", sector_upgrade=False):
    buys=[r for r in rows if r["action"]=="매수"]
    sells=[r for r in rows if r["action"]=="매도"]
    titles=[("ARKK","혁신"),("ARKQ","자동화·로봇"),("ARKX","우주·방산"),
            ("ARKG","유전체·바이오"),("ARKW","인터넷"),("ARKF","금융기술")]
    header=[
        "📊 <b>ARK Invest 일별 매매"+(" 업종 순위 보강본" if sector_upgrade else (" 금액 보강본" if enrichment else (" 수정본" if is_revision else "")))+"</b>",
        f"<b>거래 기준일: {day} (미국 현지 날짜)</b>",
        f"공시 주체: ARK Invest · 매수 {len(buys)}개 거래행 / 매도 {len(sells)}개 거래행",
        "<b>판정: ARK 공식 잠정 매매 파일 · 분기 13F와 별개</b>",
        f"원화 환산 기준: 1달러={rate:,.2f}원 ({html.escape(str(basis))})" if rate else "원화 환산 기준: 조회 불가",
        "매매대금: 미국 현지 거래일 종가 × 주식 수의 참고 추정액 (실제 체결대금 아님)",
        "",
    ]
    # The official ARK trade file contains share quantities but no executed fill prices.
    # NEVER substitute zero or an unverified filled-notional for missing ticker prices.
    # Do not call a partial price-covered aggregate the total actual trade amount.
    if prices and rate:
        for action,subset in [("매수",buys),("매도",sells)]:
            quoted=[r for r in subset if r["ticker"] in prices]
            usd=sum(r["shares"]*prices[r["ticker"]]["close"] for r in quoted)
            marker="일부 추정 합계" if len(quoted)<len(subset) else "종가 기준 추정 합계"
            header.append(
                f"• {action} {marker}: <b>{notional.usd_krw(usd,rate)}</b>"
                f" · 가격 확인 {len(quoted)}/{len(subset)}개 거래행"
            )
    else:
        header.append("• 거래대금: 장마감 가격 미확인으로 총액 추정 불가")

    if rate:
        # Snapshot for the new trade date replaces that date, not adds another
        # sample. Keep previous confirmed snapshots unchanged, including legacy
        # sector-unknown classification and missing historical dates.
        totals_for_history, _ = sector_rank.aggregate(rows, prices or {})
        current_for_history = sector_rank.snapshot(day,digest,totals_for_history)
        merged_for_report = sector_rank.merged_history(history or [],current_for_history)
        header.extend(sector_rank.direction_summary(
            merged_for_report,day,rate,notional.usd_krw))
        ranked, _, _ = sector_rank.build_sector_digest(
            rows, prices or {}, rate, notional.usd_krw,
            history=history, day=day, digest=digest,
        )
        header.extend(ranked)
    else:
        header.extend(["", "<b>업종별 매수 순위</b>",
                       "• 현재 환율·종가가 확인되지 않아 금액 순위를 산출할 수 없습니다."])

    xe=[r for r in buys if r["ticker"]=="XE"]
    if xe:
        total=sum(r['shares'] for r in xe)
        estimate=notional.estimated_amount('XE',total,prices,rate)
        header.append(f"• 엑스에너지(XE): {len(xe)}개 펀드 합계 <b>{total:,}주 매수</b> · {estimate}")
    for direction,subset in [("매수",buys),("매도",sells)]:
        header.extend(["",f"<b>{direction} · 펀드별 거래</b>"])
        for fund,_ in titles:
            for r in (r for r in subset if r["fund"]==fund):
                name=NAMES.get(r["ticker"],r["ticker"])
                amount=notional.estimated_amount(r['ticker'],r['shares'],prices,rate)
                header.append(f"• {fund} | {html.escape(name)}({r['ticker']}) | <b>{r['shares']:,}주 {direction}</b> · {amount}")
    header.extend([
       "",
       "<b>해석 주의</b>",
       "• 위 수량은 해당 일자의 펀드 거래 수량이며, 총 보유주식 수나 펀드 최종 보유비중이 아닙니다.",
       "• 공식 매매 알림은 잠정 자료이고 ETF 설정·환매/일부 공모거래 등이 제외될 수 있습니다.",
       "• 매매대금은 공식 거래수량 × 해당일 미국 종가로 계산한 참고 추정액입니다. 실제 체결단가·실제 체결대금은 ARK 공식 매매 파일에 공개되지 않습니다.",
       "• 종가 확인에 실패하거나 독립 가격 자료가 4% 넘게 다르면 추정액을 표시하지 않습니다.",
       "• 가격 출처: Stooq·Yahoo Finance의 해당 거래일 종가. 프랑스 상장 탈레스(HO)는 달러 종가로 환산하지 않습니다.",
       "",
       _link("ARK 공식 당일 매매 파일",SOURCE)+" | "+_link("ARK 공식 안내",DISCLOSURE),
    ])
    return "\n".join(header)

def main(probe=False):
    data,kind=_fetch()
    rows=parse(data)
    latest=max(x["date"] for x in rows)
    now=dt.datetime.now(ET).date()
    age=(now-dt.date.fromisoformat(latest)).days
    latest_rows=[r for r in rows if r["date"]==latest]
    digest=_fingerprint(latest_rows)
    print(f"ark_official_file_bytes={len(data)} content_type={kind!r} latest={latest} count={len(latest_rows)} age_days={age} digest={digest}")
    for r in latest_rows[:22]:
        print("ARK_ROW "+json.dumps(r,ensure_ascii=False))
    if age<0 or age>5:
        raise RuntimeError("ARK latest official trade file is stale/future; will not send")
    if probe:
        return
    state=_load()
    # A Telegram send may have succeeded when confirmation/checkpoint failed.
    # Block re-sends until the reserved attempt is reconciled.
    if state.get("pending_delivery"):
        raise RuntimeError("ARK_DELIVERY_UNCERTAIN: reserved send not finalized; automatic resend blocked")
    previous_date=state.get("last_date","")
    previous_digest=state.get("digest","")
    if (latest==previous_date and digest==previous_digest
            and state.get("format_version",0)>=REPORT_FORMAT_VERSION):
        print("ARK_TRADE_NO_CHANGE")
        return
    # Avoid sending historical backfill older than the last successful date.
    if previous_date and latest<previous_date:
        raise RuntimeError("ARK official latest trade date older than previously sent date")
    changed=latest==previous_date and bool(previous_digest)
    from fx_api import daily_krw
    fx=daily_krw()
    rate=float(fx.rate)
    if not math.isfinite(rate) or rate<=0:
        raise RuntimeError("Invalid USD/KRW quote; do not send an unconverted amount")
    prices=notional.close_prices(latest_rows,latest)
    distinct_tickers=len({row["ticker"] for row in latest_rows})
    print(f"ARK_NOTIONAL_PRICE_COVERAGE={len(prices)}/{distinct_tickers}")
    rank_upgrade=bool(latest==previous_date and state.get("format_version",0)<REPORT_FORMAT_VERSION)
    msg=build(latest_rows,latest,is_revision=changed,rate=rate,basis=fx.basis,
              prices=prices,enrichment=False,
              history=state.get("sector_history",[]),digest=digest,sector_upgrade=rank_upgrade)
    pathlib.Path("out").mkdir(exist_ok=True)
    pathlib.Path("out/ark_trade_alert.html").write_text(msg+"\n",encoding="utf-8")
    aggregated_sectors, _ = sector_rank.aggregate(latest_rows,prices)
    current_sector_snapshot = sector_rank.snapshot(latest,digest,aggregated_sectors)
    sector_history = sector_rank.merged_history(state.get("sector_history",[]),current_sector_snapshot)
    pathlib.Path("out/ark_trade_pending.json").write_text(json.dumps({
      "version":1,"last_date":latest,"digest":digest,"format_version":REPORT_FORMAT_VERSION,
      "sector_history":sector_history,
      "updated_at":dt.datetime.now(dt.timezone.utc).isoformat()
    },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("ARK_ALERT_READY")

if __name__=="__main__":
    main(probe="--probe" in __import__("sys").argv)
