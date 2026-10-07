#!/usr/bin/env python3
import html
import json
import os
import re
import urllib.parse
import urllib.request
import time
import csv
import io
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

STATE_PATH=Path('data/market_internal_strength_watch_state.json')
TOKEN=(os.getenv('TELEGRAM_BOT_TOKEN') or '').strip()
CHAT_ID=(os.getenv('TELEGRAM_CHAT_ID') or '').strip()
EXPECTED_BOT=(os.getenv('EXPECTED_BOT_USERNAME') or 'khs887900887900008879_bot').strip().lstrip('@')
FORCE=os.getenv('FORCE_NOTIFY','0')=='1'
UA='Mozilla/5.0 (compatible; khs-watch/3.0; +https://github.com/qedgwangju-dot/khs-watch)'
YAHOO='https://query1.finance.yahoo.com/v8/finance/chart/{}?range=1mo&interval=1d&includePrePost=false'
CBOE_VIX_CSV='https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv'
STOCKANALYSIS_HISTORY='https://stockanalysis.com/etf/{}/history/'
METHODOLOGY_VERSION='2026-10-07-v6'

SYMBOLS={
    'S&P500':'SPY','동일가중 S&P500':'RSP','중소형주':'IWM','하이일드 회사채':'HYG','VIX':'^VIX',
    '커뮤니케이션':'XLC','경기소비재':'XLY','필수소비재':'XLP','에너지':'XLE','금융':'XLF','헬스케어':'XLV',
    '산업재':'XLI','소재':'XLB','부동산':'XLRE','기술':'XLK','유틸리티':'XLU',
}
SECTORS=['커뮤니케이션','경기소비재','필수소비재','에너지','금융','헬스케어','산업재','소재','부동산','기술','유틸리티']


def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept-Language':'en-US,en;q=0.9'})
    with urllib.request.urlopen(req,timeout=25) as r:return r.read().decode('utf-8','replace')

def series(symbol, adjusted=False):
    yahoo_url=YAHOO.format(urllib.parse.quote(symbol,safe='')) + f'&cb={int(time.time())}'
    d=json.loads(fetch(yahoo_url))
    r=((d.get('chart') or {}).get('result') or [None])[0]
    if not r: raise RuntimeError(f'{symbol} unavailable')
    ts=r.get('timestamp') or []
    ind=r.get('indicators') or {}
    closes=(((ind.get('quote') or [{}])[0]).get('close') or [])
    adj=(((ind.get('adjclose') or [{}])[0]).get('adjclose') or [])
    if adjusted:
        if not adj or len(adj) != len(ts):
            raise RuntimeError(f'{symbol} adjusted close unavailable')
        values=adj
    else:
        values=closes

    meta=r.get('meta') or {}
    regular=((meta.get('currentTradingPeriod') or {}).get('regular') or {})
    regular_start=regular.get('start'); regular_end=regular.get('end')
    now=time.time()
    ny=ZoneInfo('America/New_York')
    ny_now=datetime.now(ny)
    ny_today=ny_now.date().isoformat()
    before_settlement=bool(regular_end and now < regular_end + 2700)  # 45m post-close guard

    by_date={}
    for t,v in zip(ts,values):
        if v is None:
            continue
        row_date=datetime.fromtimestamp(t,ny).date().isoformat()
        if row_date == ny_today and before_settlement:
            continue
        by_date[row_date]=float(v)

    # Yahoo's daily-array bar can stay stale or retain an intraday value after the
    # closing bell. Once the session has had a 45-minute settlement buffer, use the
    # chart meta regularMarketPrice/regularMarketTime as the authoritative Yahoo
    # completed-session close for that latest session. For adjusted series (HYG),
    # the current post-distribution adjusted close equals the current close, so this
    # safely extends an otherwise lagging adjusted-close array.
    reg_price=meta.get('regularMarketPrice')
    reg_time=meta.get('regularMarketTime')
    if (
        not before_settlement
        and isinstance(reg_price,(int,float))
        and isinstance(reg_time,(int,float))
    ):
        reg_date=datetime.fromtimestamp(int(reg_time),ny).date().isoformat()
        if reg_date <= ny_today:
            by_date[reg_date]=float(reg_price)

    rows=sorted(by_date.items())
    if len(rows)<7:
        raise RuntimeError(f'{symbol} completed-session history too short')
    return rows

def cboe_vix_series():
    raw=fetch(CBOE_VIX_CSV)
    rows=[]
    for row in csv.DictReader(io.StringIO(raw)):
        raw_date=str(row.get('DATE') or '').strip()
        raw_close=str(row.get('CLOSE') or '').strip()
        if not raw_date or not raw_close:
            continue
        try:
            d=datetime.strptime(raw_date,'%m/%d/%Y').date().isoformat()
            v=float(raw_close)
        except Exception:
            continue
        rows.append((d,v))
    rows.sort(key=lambda x:x[0])
    if len(rows)<7:
        raise RuntimeError('Cboe VIX official history too short')
    return rows

def stockanalysis_latest(symbol, adjusted=False):
    raw=fetch(STOCKANALYSIS_HISTORY.format(symbol.lower()))
    plain=html.unescape(re.sub(r'<[^>]+>',' ',raw))
    plain=re.sub(r'\s+',' ',plain)
    m=re.search(
        r'([A-Z][a-z]{2}\s+\d{1,2},\s+20\d{2})\s+'
        r'([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)',
        plain
    )
    if not m:
        raise RuntimeError(f'{symbol} StockAnalysis final-history row unavailable')
    d=datetime.strptime(m.group(1),'%b %d, %Y').date().isoformat()
    close=float(m.group(5))
    adj=float(m.group(6))
    return d,(adj if adjusted else close)

def ret(rows,n): return (rows[-1][1]/rows[-1-n][1]-1)*100.0

def snapshot():
    data={}
    final_rows={}
    for name,symbol in SYMBOLS.items():
        if name == '하이일드 회사채':
            # HYG is monthly-distributing. Use adjusted close so ex-dividend drops
            # are not misread as credit deterioration.
            data[name]=series(symbol, adjusted=True)
            final_rows[name]=stockanalysis_latest(symbol, adjusted=True)
        elif name == 'VIX':
            data[name]=series(symbol)
        else:
            data[name]=series(symbol)
            final_rows[name]=stockanalysis_latest(symbol)

    # Require every ETF lane to have the same independently settled daily close.
    # StockAnalysis states its history is sourced from S&P Global Market Intelligence.
    final_dates={d for d,_ in final_rows.values()}
    if len(final_dates) != 1:
        raise RuntimeError(f'ETF final-close source dates are not aligned: {sorted(final_dates)}')
    final_date=next(iter(final_dates))
    settlement_overrides={}
    for name,(d,v) in final_rows.items():
        m={x:y for x,y in data[name]}
        old=m.get(d)
        if old is None or abs(old-v) > 1e-8:
            settlement_overrides[name]={'yahoo':old,'final':v}
        m[d]=v
        data[name]=sorted(m.items())

    cboe_vix=cboe_vix_series()

    # 일부 ETF/지수의 Yahoo 종가 반영이 하루 늦을 수 있다.
    # 서로 다른 기준일을 억지로 섞지 말고, 모든 시계열에 공통으로 존재하는
    # 가장 최근 '완료 정규장' 날짜에 맞춰 정렬한다.
    common_dates=None
    for rows in data.values():
        dates={d for d,_ in rows}
        common_dates=dates if common_dates is None else (common_dates & dates)
    if not common_dates:
        latest_dates=sorted({rows[-1][0] for rows in data.values()})
        raise RuntimeError(f'공통 완료 종가 기준일 없음: {latest_dates}')
    common_dates=sorted(common_dates)
    if len(common_dates)<6:
        raise RuntimeError(f'공통 완료 거래일 부족: {common_dates}')
    common_date=common_dates[-1]
    d1,d3,d5=common_dates[-2],common_dates[-4],common_dates[-6]

    # 모든 자산을 정확히 같은 시작일/종료일로 비교한다.
    # 한 종목의 데이터 누락 때문에 "5거래일"의 시작일이 달라지는 것을 금지한다.
    maps={name:{d:v for d,v in rows} for name,rows in data.items()}

    # VIX timing guard: use Yahoo's completed-session close so all market lanes
    # stay on the same trading date, while validating the latest overlapping date
    # against Cboe's official daily-history file. Cboe's CSV can publish one session late;
    # never roll the whole snapshot back to a stale date just because that file lags.
    yahoo_vix=maps['VIX']
    cboe_map={d:v for d,v in cboe_vix}
    overlap=[d for d in cboe_map if d in yahoo_vix and d <= common_date]
    if not overlap:
        raise RuntimeError('VIX Cboe/Yahoo overlapping completed date unavailable')
    official_check_date=max(overlap)
    official_diff=abs(cboe_map[official_check_date]-yahoo_vix[official_check_date])
    if official_diff > 0.05:
        raise RuntimeError(
            f'VIX Cboe/Yahoo mismatch {official_check_date}: '
            f'Cboe={cboe_map[official_check_date]:.2f} Yahoo={yahoo_vix[official_check_date]:.2f}'
        )
    official_same_day=common_date in cboe_map
    lag_days=(datetime.fromisoformat(common_date).date()-datetime.fromisoformat(official_check_date).date()).days
    if lag_days < 0 or lag_days > 4:
        raise RuntimeError(
            f'Cboe VIX official history lag too large: market={common_date} official={official_check_date}'
        )

    out={'date':common_date,'window':{'1d':d1,'3d':d3,'5d':d5},'returns':{},
         'methodology_version':METHODOLOGY_VERSION,
         'hyg_basis':'Yahoo adjusted close total return',
         'vix_source':'Yahoo completed close with Cboe official overlap validation',
         'vix_official_crosscheck_date':official_check_date,
         'vix_official_same_day':official_same_day,
         'vix_official_lag_days':lag_days,
         'vix_crosscheck_max_abs_diff':official_diff,
         'etf_final_close_source':'StockAnalysis / S&P Global Market Intelligence',
         'etf_final_close_date':final_date,
         'settlement_overrides':settlement_overrides}
    for name,m in maps.items():
        for d in (common_date,d1,d3,d5):
            if d not in m:
                raise RuntimeError(f'{name} 공통 비교일 {d} 종가 누락')
        out['returns'][name]={
            '1d':(m[common_date]/m[d1]-1)*100.0,
            '3d':(m[common_date]/m[d3]-1)*100.0,
            '5d':(m[common_date]/m[d5]-1)*100.0,
        }
    spy=out['returns']['S&P500']; rsp=out['returns']['동일가중 S&P500']; iwm=out['returns']['중소형주']; hyg=out['returns']['하이일드 회사채']; vix=out['returns']['VIX']
    out['rsp_rel_5d']=rsp['5d']-spy['5d']; out['iwm_rel_5d']=iwm['5d']-spy['5d']
    out['sector_up_1d']=sum(1 for s in SECTORS if out['returns'][s]['1d']>0)
    out['sector_up_5d']=sum(1 for s in SECTORS if out['returns'][s]['5d']>0)
    rsp_warn=out['rsp_rel_5d']<=-1.0
    iwm_warn=out['iwm_rel_5d']<=-1.0
    breadth_warn=rsp_warn or iwm_warn
    credit_stress=hyg['5d']<=-1.0
    vol_stress=vix['5d']>=15.0
    sector_narrow=out['sector_up_5d']<=4
    out['breadth_warning']=breadth_warn
    out['rsp_warning']=rsp_warn
    out['iwm_warning']=iwm_warn
    out['credit_stress']=credit_stress
    out['vol_stress']=vol_stress

    if spy['5d']<0 and rsp_warn and iwm_warn and credit_stress and vol_stress and sector_narrow:
        verdict='광범위 위험회피 — 순환매보다 자금 이탈 경계'
    elif rsp_warn and iwm_warn and out['sector_up_5d']<=5:
        verdict='대형주 편중 — 시장 폭 약화'
    elif breadth_warn and out['sector_up_5d']>=6 and not credit_stress and not vol_stress:
        if iwm_warn and not rsp_warn:
            verdict='업종 순환 유지·중소형주 확산 약화'
        elif rsp_warn and not iwm_warn:
            verdict='업종 순환 유지·동일가중 확산 약화'
        else:
            verdict='업종 순환 유지·시장 폭 약화'
    elif (out['rsp_rel_5d']>=0.75 or out['iwm_rel_5d']>=0.75) and not credit_stress and not vol_stress and out['sector_up_5d']>=6:
        verdict='순환매·시장 내부 체력 양호'
    elif out['sector_up_5d']>=7 and hyg['5d']>-0.5 and not vol_stress and not breadth_warn:
        verdict='종목·업종 순환매 유지'
    else:
        verdict='혼합 — 뚜렷한 순환매/위험회피 미확인'
    out['verdict']=verdict
    return out

def load_state():
    try:return json.loads(STATE_PATH.read_text(encoding='utf-8')) if STATE_PATH.exists() else {}
    except Exception:return {}

def save_state(s):
    STATE_PATH.parent.mkdir(parents=True,exist_ok=True); STATE_PATH.write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def botname():
    with urllib.request.urlopen(f'https://api.telegram.org/bot{TOKEN}/getMe',timeout=20) as r:return str((json.loads(r.read().decode()).get('result') or {}).get('username') or '')
def link(label,url):return f'<a href="{html.escape(url,quote=True)}">{html.escape(label)}</a>'
def quote_url(sym):return 'https://finance.yahoo.com/quote/'+urllib.parse.quote(sym,safe='=^')+'/'
def send(msg):
    if not TOKEN or not CHAT_ID: raise RuntimeError('Telegram token/chat id missing')
    actual=botname()
    if actual.lower()!=EXPECTED_BOT.lower(): raise RuntimeError(f'Wrong Telegram bot: expected @{EXPECTED_BOT}, got @{actual}')
    data=urllib.parse.urlencode({'chat_id':CHAT_ID,'text':msg[:4090],'parse_mode':'HTML','disable_web_page_preview':'true'}).encode()
    req=urllib.request.Request(f'https://api.telegram.org/bot{TOKEN}/sendMessage',data=data,method='POST')
    with urllib.request.urlopen(req,timeout=25) as r:
        out=json.loads(r.read().decode())
    if not out.get('ok'): raise RuntimeError(f'Telegram send failed: {out}')
    mid=(out.get('result') or {}).get('message_id')
    print(f'market_internal_telegram_delivery_confirmed=true bot=@{actual} id={mid}')
    return mid

def easy_read(s):
    r=s['returns']; hyg=r['하이일드 회사채']; vix=r['VIX']
    if s['verdict']=='순환매·시장 내부 체력 양호':
        return '지수 몇 종목만 버티는 장이 아니라 동일가중·중소형주·여러 업종까지 같이 움직이고 있어, 돈이 시장 밖으로 빠지기보다 업종 사이를 돌고 있는 모습에 가깝습니다.'
    if s['verdict']=='종목·업종 순환매 유지':
        return '동일가중·중소형주의 상대성과 여러 업종의 참여가 크게 훼손되지 않았고, 신용시장과 변동성도 안정적이라 순환매가 유지되는 쪽입니다.'
    if s['verdict']=='업종 순환 유지·중소형주 확산 약화':
        return '여러 업종은 오르고 신용·변동성도 안정적이지만 중소형주가 S&P보다 5거래일 기준 1%포인트 넘게 뒤처집니다. 전면 위험회피는 아니지만 상승의 폭이 충분히 넓다고 보기는 어렵습니다.'
    if s['verdict']=='업종 순환 유지·동일가중 확산 약화':
        return '여러 업종은 오르고 신용·변동성도 안정적이지만 동일가중 S&P 500이 시가총액가중 S&P보다 5거래일 기준 1%포인트 넘게 뒤처집니다. 업종 순환은 남아 있어도 종목 확산은 약합니다.'
    if s['verdict']=='업종 순환 유지·시장 폭 약화':
        return '업종별 상승은 남아 있지만 동일가중과 중소형주가 모두 뒤처져 시장 폭은 약합니다. 전면 위험회피와는 다르지만 대형주 의존도가 높아지는 구간입니다.'
    if s['verdict'].startswith('광범위 위험회피'):
        return '대형주뿐 아니라 동일가중·중소형주·회사채까지 같이 약해지고 변동성도 뛰어, 단순 순환매가 아니라 실제 위험회피로 번질 가능성을 경계해야 합니다.'
    if s['verdict'].startswith('대형주 편중'):
        return '지수는 버텨 보여도 동일가중과 여러 업종이 뒤처져, 소수 대형주가 지수를 받치는 장에 가깝습니다.'
    return '좋은 업종과 약한 업종이 섞여 있어, 순환매가 살아 있다고 단정하기도 전면 위험회피라고 보기도 이릅니다.'

def message(s, correction=False, old_date=None, correction_reason=None):
    r=s['returns']; spy=r['S&P500']; rsp=r['동일가중 S&P500']; iwm=r['중소형주']; hyg=r['하이일드 회사채']; vix=r['VIX']
    title='[정정·미국 증시 내부 체력·순환매]' if correction else '[미국 증시 내부 체력·순환매]'
    lines=[f'<b>{title}</b>',f"기준: {s['date']} 미국 정규장 종가",
           f"5거래일 비교구간: {s.get('window',{}).get('5d','확인 불가')} → {s['date']}"]
    if correction:
        reason=correction_reason or f"직전 {old_date or '당일'} 값의 기준 또는 산식이 현재 검증 기준과 달라 재계산했습니다."
        lines += ['', '<b>정정 사유</b>', f"• {html.escape(reason)}"]
    lines += ['', '<b>한눈에 보기</b>',
           f"• <b>{html.escape(s['verdict'])}</b>",
           f"• S&P 500(SPY): 5거래일 {spy['5d']:+.1f}%",
           f"• 동일가중 S&P 500(RSP): 5거래일 {rsp['5d']:+.1f}% · S&P 대비 {s['rsp_rel_5d']:+.1f}%p",
           f"• 중소형주(IWM): 5거래일 {iwm['5d']:+.1f}% · S&P 대비 {s['iwm_rel_5d']:+.1f}%p",
           f"• 11개 업종 중 상승: 1거래일 {s['sector_up_1d']}개 · 5거래일 {s['sector_up_5d']}개",
           f"• 하이일드 회사채(HYG, 분배금 반영 총수익): 5거래일 {hyg['5d']:+.1f}% · VIX(주식시장 공포·변동성 지수): 5거래일 {vix['5d']:+.1f}%",'',
           f"• 시장 폭 경고: RSP {'예' if s.get('rsp_warning') else '아니오'} · IWM {'예' if s.get('iwm_warning') else '아니오'}",'',
           '<b>쉽게 말하면</b>',f"• {easy_read(s)}",'',
           '<b>왜 보나</b>',
           '• RSP가 SPY보다 강하면 몇몇 초대형주만 오르는 게 아니라 종목 전체로 상승이 퍼지는지 보는 대용지표입니다.',
           '• HYG(하이일드 회사채)는 월별 분배금 때문에 단순 가격수익률이 왜곡될 수 있어 분배금을 반영한 조정종가 총수익으로 봅니다.',
           '• ETF 종가는 Yahoo 일봉만 믿지 않고 StockAnalysis의 S&P Global Market Intelligence 마감 종가로 확정합니다. Yahoo 일봉이 장중값 또는 지연값이면 마감값으로 교정합니다.',
           '• VIX는 같은 완료 거래일의 종가를 쓰고, Cboe 공식 일별자료가 같은 날까지 갱신됐으면 당일값을 직접 검산합니다. 공식 파일이 하루 늦으면 최신 겹치는 날짜를 검산하고 지수 전체 기준일은 뒤로 돌리지 않습니다.', '',
           '<b>판정이 나빠지는 조건</b>',
           '• RSP 또는 IWM 중 하나라도 S&P보다 5거래일 기준 1%포인트 이상 더 약해지면 시장 폭 경고',
           '• HYG가 5거래일 -1% 이하로 밀리고 VIX가 15% 이상 급등',
           '• 11개 업종 중 상승 업종이 4개 이하로 축소', '',
           '<b>원천</b>',
           f"{link('SPY',quote_url('SPY'))} · {link('RSP',quote_url('RSP'))} · {link('IWM',quote_url('IWM'))} · "
           f"{link('HYG',quote_url('HYG'))} · {link('iShares HYG','https://www.ishares.com/us/products/239565/ishares-iboxx-high-yield-corporate-bond-etf')} · "
           f"{link('Cboe VIX','https://www.cboe.com/tradable-products/vix/vix-historical-data/')}"]
    return '\n'.join(lines)

def main():
    s=snapshot(); old=load_state(); first=not bool(old)
    new_day=old.get('date') not in (None,s['date'])
    changed=old.get('verdict') not in (None,s['verdict'])
    method_changed=old.get('methodology_version') != METHODOLOGY_VERSION
    method_correction=bool(old and method_changed)
    stale_date_correction=bool(old.get('date') and old.get('date') > s['date'])
    correction=stale_date_correction or method_correction
    correction_reason=None
    if method_correction:
        correction_reason=(
            "HYG는 분배금 반영 조정종가 총수익으로 재계산하고, RSP 또는 IWM의 상대약세를 시장 폭 경고에 반영했습니다. "
            "VIX는 모든 자산과 같은 완료 거래일의 Yahoo 종가를 사용하되 Cboe 공식 일별자료의 최신 겹치는 날짜와 0.05포인트 이내로 교차검증하며, "
            "Cboe 파일 갱신이 하루 늦어도 전체 기준일을 과거로 되돌리지 않도록 수정했습니다."
        )
    elif stale_date_correction:
        correction_reason=f"직전 {old.get('date')} 값보다 최신 완료 종가 기준일이 뒤로 돌아가 데이터 시점 오류를 정정했습니다."
    shock=(s['returns']['VIX']['5d']>=20 or s['returns']['하이일드 회사채']['5d']<=-2.0)
    old_shock=bool(old.get('shock'))
    should=FORCE or correction or (not first and (changed or (shock and not old_shock)))
    if should:
        send(message(s, correction=correction, old_date=old.get('date'), correction_reason=correction_reason))
    if first or new_day or changed or shock!=old_shock or method_changed:
        save_state({
            'date':s['date'],'window':s.get('window'),'verdict':s['verdict'],'shock':shock,
            'methodology_version':METHODOLOGY_VERSION,
            'hyg_basis':s.get('hyg_basis'),'vix_source':s.get('vix_source'),
            'vix_official_crosscheck_date':s.get('vix_official_crosscheck_date'),
            'vix_official_same_day':s.get('vix_official_same_day'),
            'vix_official_lag_days':s.get('vix_official_lag_days'),
            'vix_crosscheck_max_abs_diff':s.get('vix_crosscheck_max_abs_diff'),
            'etf_final_close_source':s.get('etf_final_close_source'),
            'etf_final_close_date':s.get('etf_final_close_date'),
            'settlement_overrides':s.get('settlement_overrides'),
            'breadth_warning':s.get('breadth_warning'),'rsp_warning':s.get('rsp_warning'),'iwm_warning':s.get('iwm_warning'),
            'rsp_rel_5d':s['rsp_rel_5d'],'iwm_rel_5d':s['iwm_rel_5d'],
            'sector_up_1d':s['sector_up_1d'],'sector_up_5d':s['sector_up_5d'],'returns':s['returns']
        })
    print(json.dumps({
        'first_run':first,'date':s['date'],'verdict':s['verdict'],'shock':shock,
        'methodology_version':METHODOLOGY_VERSION,'hyg_basis':s.get('hyg_basis'),
        'vix_source':s.get('vix_source'),'vix_official_crosscheck_date':s.get('vix_official_crosscheck_date'),
        'vix_official_same_day':s.get('vix_official_same_day'),'vix_official_lag_days':s.get('vix_official_lag_days'),
        'vix_crosscheck_max_abs_diff':s.get('vix_crosscheck_max_abs_diff'),
        'etf_final_close_source':s.get('etf_final_close_source'),
        'etf_final_close_date':s.get('etf_final_close_date'),
        'settlement_overrides':s.get('settlement_overrides'),
        'rsp_rel_5d':s['rsp_rel_5d'],'iwm_rel_5d':s['iwm_rel_5d'],
        'rsp_warning':s.get('rsp_warning'),'iwm_warning':s.get('iwm_warning'),
        'sector_up_5d':s['sector_up_5d'],'correction':correction,'sent':should
    },ensure_ascii=False))

if __name__=='__main__': main()
