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
}
ET=zoneinfo.ZoneInfo("America/New_York")

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

def build(rows, day, is_revision=False):
    buys=[r for r in rows if r["action"]=="매수"]
    sells=[r for r in rows if r["action"]=="매도"]
    titles=[("ARKK","혁신"),("ARKQ","자동화·로봇"),("ARKX","우주·방산"),
            ("ARKG","유전체·바이오"),("ARKW","인터넷"),("ARKF","금융기술")]
    header=[
        "📊 <b>ARK Invest 일별 매매"+(" 수정본" if is_revision else "")+"</b>",
        f"<b>거래 기준일: {day} (미국 현지 날짜)</b>",
        f"공시 주체: ARK Invest · 매수 {len(buys)}개 거래행 / 매도 {len(sells)}개 거래행",
        "<b>판정: ARK 공식 잠정 매매 파일 · 분기 13F와 별개</b>",
        "",
    ]
    xe=[r for r in buys if r["ticker"]=="XE"]
    if xe:
        header.append(f"• 엑스에너지(XE): {len(xe)}개 펀드 합계 <b>{sum(r['shares'] for r in xe):,}주 매수</b>")
    for direction,subset in [("매수",buys),("매도",sells)]:
        header.extend(["",f"<b>{direction} · 펀드별 거래</b>"])
        for fund,_ in titles:
            for r in (r for r in subset if r["fund"]==fund):
                name=NAMES.get(r["ticker"],r["ticker"])
                header.append(f"• {fund} | {html.escape(name)}({r['ticker']}) | <b>{r['shares']:,}주 {direction}</b>")
    header.extend([
       "",
       "<b>해석 주의</b>",
       "• 위 수량은 해당 일자의 펀드 거래 수량이며, 총 보유주식 수나 펀드 최종 보유비중이 아닙니다.",
       "• 공식 매매 알림은 잠정 자료이고 ETF 설정·환매/일부 공모거래 등이 제외될 수 있습니다.",
       "• 매매 파일에 실제 체결단가가 없으면 거래금액이나 원화 금액을 추정해 확정치처럼 표시하지 않습니다.",
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
    previous_date=state.get("last_date","")
    previous_digest=state.get("digest","")
    if latest==previous_date and digest==previous_digest:
        print("ARK_TRADE_NO_CHANGE")
        return
    # Avoid sending historical backfill older than the last successful date.
    if previous_date and latest<previous_date:
        raise RuntimeError("ARK official latest trade date older than previously sent date")
    changed=latest==previous_date and bool(previous_digest)
    msg=build(latest_rows,latest,is_revision=changed)
    pathlib.Path("out").mkdir(exist_ok=True)
    pathlib.Path("out/ark_trade_alert.html").write_text(msg+"\n",encoding="utf-8")
    pathlib.Path("out/ark_trade_pending.json").write_text(json.dumps({
      "version":1,"last_date":latest,"digest":digest,
      "updated_at":dt.datetime.now(dt.timezone.utc).isoformat()
    },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("ARK_ALERT_READY")

if __name__=="__main__":
    main(probe="--probe" in __import__("sys").argv)
