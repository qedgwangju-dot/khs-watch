#!/usr/bin/env python3
"""ARK sector rankings from verified trade quantities and same-day closing-price estimates.

Trade-file share quantities are official and preliminary; prices are external
close prices, not execution prices. Never mix share counts of different tickers.
"""

from collections import defaultdict
import html
import math

SECTOR_BY_TICKER = {
    # Genomics, diagnostics, therapeutics
    "FRNM": ("바이오·헬스케어", "암 조기진단"),
    "PACB": ("바이오·헬스케어", "유전체 분석 장비"),
    "SCTX": ("바이오·헬스케어", "유전자 편집 치료"),
    "IAM": ("바이오·헬스케어", "AI 신약개발"),
    "PSNL": ("바이오·헬스케어", "정밀의료·유전체 진단"),
    "NRIX": ("바이오·헬스케어", "신약개발"),
    "CMPS": ("바이오·헬스케어", "정신질환 신약개발"),
    "ADPT": ("바이오·헬스케어", "면역진단"),
    "SDGR": ("바이오·헬스케어", "컴퓨터 기반 신약개발"),
    "MASS": ("바이오·헬스케어", "바이오 분석 장비"),
    "GENB": ("바이오·헬스케어", "AI 단백질 설계"),
    "ISRG": ("바이오·헬스케어", "수술 로봇"),
    # Energy, space, defense
    "XE": ("원자력·에너지", "소형모듈원전"),
    "OKLO": ("원자력·에너지", "차세대 원자로"),
    "LUNR": ("우주·방산", "달 착륙·우주 시스템"),
    "ESLT": ("우주·방산", "방산 전자장비"),
    "HO": ("우주·방산", "방산·항공우주"),
    "KTOS": ("우주·방산", "방산·무인기"),
    "RKLB": ("우주·방산", "로켓 발사"),
    # AI / cloud / software
    "GOOG": ("AI·클라우드·기업용 소프트웨어", "클라우드·검색·광고"),
    "GOOGL": ("AI·클라우드·기업용 소프트웨어", "클라우드·검색·광고"),
    "NET": ("AI·클라우드·기업용 소프트웨어", "네트워크·클라우드 보안"),
    "PLTR": ("AI·클라우드·기업용 소프트웨어", "기업용 AI·데이터"),
    "MSFT": ("AI·클라우드·기업용 소프트웨어", "클라우드·소프트웨어"),
    "AMZN": ("AI·클라우드·기업용 소프트웨어", "클라우드·전자상거래"),
    "META": ("AI·클라우드·기업용 소프트웨어", "디지털 광고·AI"),
    "DDOG": ("AI·클라우드·기업용 소프트웨어", "클라우드 관측·운영"),
    "SNOW": ("AI·클라우드·기업용 소프트웨어", "데이터 클라우드"),
    "NOW": ("AI·클라우드·기업용 소프트웨어", "기업 업무 소프트웨어"),
    # Security, storage, chips
    "CRWD": ("사이버보안", "엔드포인트 보안"),
    "RBRK": ("사이버보안", "데이터 보안·복구"),
    "PANW": ("사이버보안", "네트워크 보안"),
    "ZS": ("사이버보안", "클라우드 보안"),
    "P": ("저장장치·데이터 인프라", "기업용 데이터 저장장치"),
    "NVDA": ("반도체·자동화 장비", "AI 가속기"),
    "AMD": ("반도체·자동화 장비", "컴퓨팅 반도체"),
    "TSM": ("반도체·자동화 장비", "파운드리"),
    "TER": ("반도체·자동화 장비", "반도체 검사·자동화"),
    "ASML": ("반도체·자동화 장비", "노광장비"),
    # Payments / assets / commerce
    "CRCL": ("금융기술·디지털자산", "스테이블코인"),
    "XYZ": ("금융기술·디지털자산", "전자결제"),
    "COIN": ("금융기술·디지털자산", "가상자산 거래소"),
    "MSTR": ("금융기술·디지털자산", "비트코인 보유기업"),
    "SOFI": ("금융기술·디지털자산", "디지털 금융"),
    "HOOD": ("금융기술·디지털자산", "금융·증권거래"),
    "SHOP": ("전자상거래", "상거래 소프트웨어"),
    "MELI": ("전자상거래", "중남미 전자상거래"),
    "RBLX": ("게임·디지털콘텐츠", "게임·가상세계"),
    "DKNG": ("게임·디지털콘텐츠", "스포츠 관련 서비스"),
    "TSLA": ("자동차·자율주행", "전기차·자율주행"),
    "CAT": ("산업재·자동화", "건설·광산장비"),
    "6301": ("산업재·자동화", "건설·광산장비"),
}

SECTOR_UNKNOWN = "업종 미확인"


def classify(ticker, company=""):
    code = (ticker or "").strip().upper()
    if code in SECTOR_BY_TICKER:
        return SECTOR_BY_TICKER[code]
    # Strictly mapped names only; never infer a sector from a broad ticker prefix.
    name = (company or "").upper()
    if "FREENOME" in name:
        return SECTOR_BY_TICKER["FRNM"]
    if "PACIFIC BIOSCIENCES" in name:
        return SECTOR_BY_TICKER["PACB"]
    if "SCRIBE THERAPEUTICS" in name:
        return SECTOR_BY_TICKER["SCTX"]
    return (SECTOR_UNKNOWN, "공식 기업 분류 확인 필요")


def _valid_close(quote):
    if not quote:
        return None
    try:
        v = float(quote["close"])
    except (KeyError, ValueError, TypeError):
        return None
    if not (math.isfinite(v) and v > 0):
        return None
    return v


def aggregate(rows, prices):
    """Aggregates by sector/action across funds; row counts stay distinct.

    An unpriced row remains missing; it is never counted as a zero-dollar trade.
    """
    totals = {}
    tickers = {}
    for r in rows:
        sec, sub = classify(r.get("ticker"), r.get("company", ""))
        if sec not in totals:
            totals[sec] = {
                "sector": sec,
                "매수": 0.0, "매도": 0.0,
                "buy_rows": 0, "sell_rows": 0,
                "buy_priced": 0, "sell_priced": 0,
                "buy_tickers": set(), "sell_tickers": set(),
            }
        t = totals[sec]
        action = r["action"]
        ticker = r["ticker"]
        if action == "매수":
            t["buy_rows"] += 1
            t["buy_tickers"].add(ticker)
        elif action == "매도":
            t["sell_rows"] += 1
            t["sell_tickers"].add(ticker)
        else:
            continue

        close = _valid_close((prices or {}).get(ticker))
        if close is not None:
            notional = float(r["shares"]) * close
            t[action] += notional
            t["buy_priced" if action == "매수" else "sell_priced"] += 1
        else:
            notional = None

        key = (action, ticker)
        if key not in tickers:
            tickers[key] = {"action": action, "ticker": ticker, "sector": sec,
                            "subsector": sub, "shares": 0, "value": 0.0,
                            "rows": 0, "priced": 0, "funds": set()}
        x = tickers[key]
        x["shares"] += int(r["shares"])
        x["rows"] += 1
        x["funds"].add(r["fund"])
        if notional is None:
            continue
        x["value"] += notional
        x["priced"] += 1
    return totals, tickers


def _amount(v, rate, money_fmt):
    return money_fmt(v, rate)


def _rank_lines(totals, tickers, rate, money_fmt):
    buy = sorted(
        (x for x in totals.values() if x["buy_rows"] and x["sector"] != SECTOR_UNKNOWN),
        key=lambda x: (-x["매수"], x["sector"]),
    )
    unknown = totals.get(SECTOR_UNKNOWN)
    total_buy = sum(x["매수"] for x in totals.values())
    all_buy_rows = sum(x["buy_rows"] for x in totals.values())
    all_buy_priced = sum(x["buy_priced"] for x in totals.values())

    lines = ["", "<b>업종별 매수 순위 · 전체 ARK 펀드 합산</b>"]
    if not buy:
        lines.append("• 업종 확인과 종가 검증이 완료된 매수가 없어 금액 순위를 산출할 수 없습니다.")
    else:
        for rank, x in enumerate(buy, 1):
            coverage = f"{x['buy_priced']}/{x['buy_rows']}행"
            amt = _amount(x["매수"], rate, money_fmt) if x["buy_priced"] else "종가 미확인"
            portion = f" · 매수 추정액의 {100*x['매수']/total_buy:.1f}%" if total_buy else ""
            suffix = " · 부분합" if x["buy_priced"] < x["buy_rows"] else ""
            lines.append(
                f"• <b>{rank}위 {html.escape(x['sector'])}</b>: {amt}{portion}"
                f" · {len(x['buy_tickers'])}종목 / {coverage}{suffix}"
            )
            if x["buy_priced"] == x["buy_rows"] and x["buy_rows"]:
                avg = x["매수"] / x["buy_rows"]
                lines.append(f"  거래행당 평균 매수 추정: {_amount(avg,rate,money_fmt)}")
    if unknown and unknown["buy_rows"]:
        lines.append(
            f"• 업종 미분류 매수: {unknown['buy_rows']}행 "
            f"(추정액 확인 {unknown['buy_priced']}행, 순위 제외)"
        )

    if all_buy_priced:
        global_avg = total_buy / all_buy_priced
        qualifier = " · 부분 집계" if all_buy_priced < all_buy_rows else ""
        lines.append(
            f"• <b>전체 매수 거래행당 평균</b>: {_amount(global_avg,rate,money_fmt)}"
            f" (가격 확인 {all_buy_priced}/{all_buy_rows}행){qualifier}"
        )
    else:
        lines.append("• 전체 매수 거래행당 평균: 종가 미확인으로 산출 불가")

    ordered_stocks = sorted(
        (x for x in tickers.values() if x["action"] == "매수"),
        key=lambda x: (-x["value"], x["ticker"]),
    )
    if ordered_stocks:
        lines.append("• <b>합산 매수 종목 순위</b> (여러 펀드에서 산 같은 종목은 합산)")
        for rank, x in enumerate(ordered_stocks[:5], 1):
            money = _amount(x["value"], rate, money_fmt) if x["priced"] == x["rows"] else (
                _amount(x["value"], rate, money_fmt)+" · 부분합" if x["priced"] else "금액 미확인"
            )
            lines.append(f"  {rank}. {html.escape(x['ticker'])} {x['shares']:,}주 · {money}")
    return lines


def _sell_lines(totals, rate, money_fmt):
    sells = sorted(
        [x for x in totals.values() if x["sell_rows"] and x["sector"] != SECTOR_UNKNOWN],
        key=lambda x: (-x["매도"], x["sector"]),
    )
    if not sells:
        return []
    lines = ["", "<b>매도금액 상위 업종 · 별도 집계</b>"]
    for rank, x in enumerate(sells[:5], 1):
        amt = _amount(x["매도"], rate, money_fmt) if x["sell_priced"] else "금액 확인 불가"
        partial = " · 부분합" if x["sell_priced"] < x["sell_rows"] else ""
        lines.append(
            f"• {rank}위 {html.escape(x['sector'])}: {amt} · {x['sell_priced']}/{x['sell_rows']}행{partial}"
        )
    unknown = totals.get(SECTOR_UNKNOWN)
    if unknown and unknown["sell_rows"]:
        lines.append(
            f"• 업종 미분류 매도: {unknown['sell_rows']}행 "
            "(섣부른 업종분류 대신 원문 종목 유지)"
        )
    return lines


def _net_line(totals, rate, money_fmt):
    priced_buy = sum(x["매수"] for x in totals.values())
    priced_sell = sum(x["매도"] for x in totals.values())
    required = sum(x["buy_rows"]+x["sell_rows"] for x in totals.values())
    covered = sum(x["buy_priced"]+x["sell_priced"] for x in totals.values())
    if required and covered == required:
        net = priced_buy - priced_sell
        direction = "순매수 우위" if net > 0 else ("순매도 우위" if net < 0 else "매수·매도 균형")
        sign = "+" if net>0 else "-" if net<0 else ""
        return f"• <b>업종 합산 매수−매도 추정</b>: {direction} {sign}{_amount(abs(net),rate,money_fmt)}"
    return f"• 업종 합산 매수−매도: 가격 검증 {covered}/{required}행으로 전체 순액 미산출"


def snapshot(day, digest, totals):
    complete=all(x["buy_rows"] == x["buy_priced"] and
                 x["sell_rows"] == x["sell_priced"] for x in totals.values())
    return {
        "date": day, "digest": digest,
        "complete": complete,
        "buy_usd": {key:round(v["매수"],6) for key,v in totals.items() if v["buy_rows"]},
        "sell_usd": {key:round(v["매도"],6) for key,v in totals.items() if v["sell_rows"]},
        "buy_rows": {key:v["buy_rows"] for key,v in totals.items() if v["buy_rows"]},
    }


def merged_history(state_history, current, max_days=20):
    # A revision replaces, not double counts, its earlier record for that trade date.
    days = {entry["date"]:entry for entry in (state_history or []) if isinstance(entry,dict) and entry.get("date")}
    days[current["date"]] = current
    return [days[k] for k in sorted(days)[-max_days:]]


def recent_average_lines(history, rate, money_fmt):
    complete=[x for x in history if x.get("complete")]
    if not complete:
        return ["", "<b>최근 관측일 업종별 일평균 매수</b>",
                "• 종가가 모두 확인된 거래일이 없어 일평균 산출 불가"]
    eligible=complete[-min(len(complete),20):]
    days=len(eligible)
    amounts=defaultdict(float)
    for entry in eligible:
        for sector, usd in entry.get("buy_usd",{}).items():
            if sector != SECTOR_UNKNOWN:
                amounts[sector]+=float(usd)
    ranked=sorted(amounts.items(),key=lambda kv:(-kv[1],kv[0]))
    lines=["",f"<b>최근 관측 {days}거래일 업종별 일평균 매수 추정</b>"]
    for rank,(sec,amount) in enumerate(ranked[:5],1):
        lines.append(f"• {rank}위 {html.escape(sec)}: {_amount(amount/days,rate,money_fmt)} /일")
    if days<5:
        lines.append(f"• 아직 5거래일 평균은 산출하지 않습니다. 관측 {days}/5거래일")
    elif days<20:
        lines.append(f"• 20거래일 평균 산출 전 · 누적 {days}/20거래일")
    lines.append("• 같은 날짜 수정본은 하루 한 번으로 계산하며, 공식매매 파일 미확보 과거일은 소급 추정하지 않습니다.")
    return lines


def build_sector_digest(rows, prices, rate, money_fmt, history=None, day="", digest=""):
    if not rate or not math.isfinite(rate) or rate<=0:
        raise ValueError("Validated USD/KRW rate required for sector digest")
    totals,tickers=aggregate(rows,prices)
    output = _rank_lines(totals,tickers,rate,money_fmt)
    output += _sell_lines(totals,rate,money_fmt)
    output += ["", _net_line(totals,rate,money_fmt)]
    snap = snapshot(day, digest, totals)
    merged = merged_history(history or [],snap) if day else []
    if merged:
        output += recent_average_lines(merged,rate,money_fmt)
    output += ["", "※ 순위·평균 금액은 주식 수×미국 거래일 종가의 추정치입니다. 실제 주문 체결금액과 다릅니다."]
    output += ["※ 같은 주식의 펀드별 수량만 합산하며 서로 다른 주식의 수량은 합산하지 않습니다."]
    return output, snap, merged
