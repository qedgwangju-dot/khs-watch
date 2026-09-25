#!/usr/bin/env python3
"""Warsh/Fed energy-shock watcher.

Separates two very different paths when oil surges:
1) second-round inflation pass-through -> tighter-policy case;
2) real-income/demand destruction -> 2008-style over-tightening risk.

The alert is intentionally conditional and does not equate a high oil price with an
automatic rate hike. It follows the framework laid out by Vice Chair Jefferson on
2026-07-16 and combines oil, inflation expectations, PCE trend, consumption,
employment and credit.
"""
import csv
import html
import io
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
STATE_PATH=ROOT/'data/warsh_energy_shock_watch_state.json'
PCE_STATE=ROOT/'data/warsh_pce_trend_watch_state.json'
CRED_STATE=ROOT/'data/warsh_credibility_pretightening_watch_state.json'
CREDIT_STATE=ROOT/'data/warsh_new_axes_watch_state.json'
TOKEN=(os.getenv('TELEGRAM_BOT_TOKEN') or '').strip()
CHAT_ID=(os.getenv('TELEGRAM_CHAT_ID') or '').strip()
EXPECTED_BOT=(os.getenv('EXPECTED_BOT_USERNAME') or 'khs8879887988798879_bot').strip().lstrip('@')
FORCE_NOTIFY=os.getenv('FORCE_NOTIFY','0')=='1'
BRENT_LEVEL=float(os.getenv('WARSH_ENERGY_BRENT_USD','100'))
BRENT_20D_PCT=float(os.getenv('WARSH_ENERGY_20D_PCT','15'))
UA='Mozilla/5.0 (compatible; khs-watch/1.0; +https://github.com/qedgwangju-dot/khs-watch)'

YAHOO_CHART='https://query1.finance.yahoo.com/v8/finance/chart/{}?range=2mo&interval=1d&includePrePost=false'
FRED_CSV='https://fred.stlouisfed.org/graph/fredgraph.csv?id={}'
JEFFERSON_URL='https://www.federalreserve.gov/newsevents/speech/jefferson20260716a.htm'
BRENT_PAGE='https://finance.yahoo.com/quote/BZ=F/'
FRED_BRENT='https://fred.stlouisfed.org/series/DCOILBRENTEU'
FRED_BEI='https://fred.stlouisfed.org/series/T5YIE'
FRED_REAL_PCE='https://fred.stlouisfed.org/series/PCEC96'


def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept-Language':'en-US,en;q=0.9'})
    with urllib.request.urlopen(req,timeout=25) as r:
        return r.read().decode('utf-8',errors='replace')


def load_json(path):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except Exception:return {}


def save_json(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    obj['updated_at_utc']=datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def fred_series(series):
    raw=fetch(FRED_CSV.format(series)); out=[]
    for r in csv.DictReader(io.StringIO(raw)):
        v=r.get(series)
        if not v or v=='.':continue
        try:out.append((r['observation_date'],float(v)))
        except Exception:pass
    if len(out)<5:raise RuntimeError(f'FRED {series} unavailable')
    return out


def yahoo_series(symbol):
    url=YAHOO_CHART.format(urllib.parse.quote(symbol,safe=''))
    d=json.loads(fetch(url)); result=((d.get('chart') or {}).get('result') or [None])[0]
    if not result:raise RuntimeError('Yahoo chart unavailable')
    ts=result.get('timestamp') or []
    quote=((result.get('indicators') or {}).get('quote') or [{}])[0]
    closes=quote.get('close') or []
    highs=quote.get('high') or []
    lows=quote.get('low') or []
    meta=result.get('meta') or {}
    rows=[]
    for i,(t,c) in enumerate(zip(ts,closes)):
        if c is None:continue
        h=highs[i] if i<len(highs) else None
        l=lows[i] if i<len(lows) else None
        rows.append({
            'date':datetime.fromtimestamp(t,timezone.utc).date().isoformat(),
            'close':float(c),
            'high':float(h) if h is not None else None,
            'low':float(l) if l is not None else None,
        })
    if len(rows)<21:raise RuntimeError('Brent history too short')
    return rows,meta


def brent_snapshot():
    # 이 거시 경보는 장중 틱이 아니라 '완료된 일봉 종가'만 사용합니다.
    # 현재 뉴욕 날짜의 BZ=F 일봉은 세션 진행 중 값일 수 있으므로 판정에서 제외합니다.
    rows,meta=yahoo_series('BZ=F')
    ny_today=datetime.now(ZoneInfo('America/New_York')).date().isoformat()
    completed=[r for r in rows if r['date'] < ny_today]
    if len(completed)<21:
        raise RuntimeError('Brent completed-session history too short')

    latest_row=completed[-1]
    latest_date=latest_row['date']
    latest=float(latest_row['close'])
    d20=(latest/float(completed[-21]['close'])-1)*100
    last3=[float(x['close']) for x in completed[-3:]]

    # 완료 일봉 내부 일관성 검사. 종가가 고가/저가 범위를 벗어나면 사용하지 않습니다.
    lo=latest_row.get('low'); hi=latest_row.get('high')
    if lo is not None and hi is not None and not (float(lo)*0.999 <= latest <= float(hi)*1.001):
        raise RuntimeError(f'Brent completed close outside candle range: close={latest} range={lo}-{hi}')

    active=(all(x>=BRENT_LEVEL for x in last3) or d20>=BRENT_20D_PCT)
    return {
        'date':latest_date,'value':latest,'d20_pct':d20,'last3':last3,'active':active,
        'source':'Yahoo Finance 브렌트 선물 완료 일봉','url':BRENT_PAGE,
        'live':False,'quality_note':'현재 진행 중 일봉 제외 · 최근 완료 거래일 종가 기준',
        'measurement_basis':'최근 완료 거래일 종가'
    }

def macro_snapshot():
    pce=load_json(PCE_STATE); cred=load_json(CRED_STATE); credit=load_json(CREDIT_STATE)
    real=fred_series('PCEC96')
    real3=((real[-1][1]/real[-4][1])**4-1)*100 if real[-4][1]>0 else None
    bei=fred_series('T5YIE')
    bei10bp=(bei[-1][1]-bei[-11][1])*100 if len(bei)>=11 else None
    macro=(cred.get('macro') or {})
    h8=(credit.get('h8') or {}).get('regime')
    sloos=(credit.get('sloos') or {}).get('regime')
    return {
        'core_3m_ann':pce.get('core_3m_ann'),'core_6m_ann':pce.get('core_6m_ann'),'core_yoy':pce.get('core_yoy'),
        'employment_soft':bool(macro.get('employment_soft')),'payroll_change_k':macro.get('payroll_change_k'),
        'unemployment_rate':macro.get('unemployment_rate'),'h8':h8,'sloos':sloos,
        'real_pce_3m_ann':real3,'real_pce_date':real[-1][0],
        'bei5y':bei[-1][1],'bei5y_10d_bp':bei10bp,'bei_date':bei[-1][0],
    }


def verdict(br,ma):
    if not br['active']:
        return '에너지 충격 경보 기준 미충족'
    pass_score=0; demand_score=0
    if ma.get('core_3m_ann') is not None and ma['core_3m_ann']>=3.0:pass_score+=1
    if ma.get('core_yoy') is not None and ma['core_yoy']>=3.0:pass_score+=1
    if ma.get('bei5y_10d_bp') is not None and ma['bei5y_10d_bp']>=20:pass_score+=1
    if ma.get('real_pce_3m_ann') is not None and ma['real_pce_3m_ann']<=1.0:demand_score+=1
    if ma.get('employment_soft'):demand_score+=1
    if ma.get('h8')=='신용 긴축' or ma.get('sloos')=='신용 긴축':demand_score+=1
    if pass_score>=2 and demand_score>=2:return '스태그플레이션형 충돌 — 물가 전이와 수요 약화가 동시에 진행'
    if pass_score>=2 and demand_score<=1:return '2차 물가 전이 우세 — 추가긴축 논리 강화'
    if demand_score>=2 and pass_score<=1:return '수요 파괴 우세 — 추가인상 시 2008형 과잉긴축 위험'
    return '판정 유보 — 유가 충격은 크지만 물가 전이와 수요 파괴의 우열 불명확'


def get_bot_username():
    with urllib.request.urlopen(f'https://api.telegram.org/bot{TOKEN}/getMe',timeout=20) as r:
        d=json.loads(r.read().decode())
    return str((d.get('result') or {}).get('username') or '')


def link(label,url):return f'<a href="{html.escape(url,quote=True)}">{html.escape(label)}</a>'

def send(text):
    if not TOKEN or not CHAT_ID:raise RuntimeError('Telegram token/chat id missing')
    u=get_bot_username()
    if u.lower()!=EXPECTED_BOT.lower():raise RuntimeError(f'Wrong Telegram bot: expected @{EXPECTED_BOT}, got @{u}')
    data=urllib.parse.urlencode({'chat_id':CHAT_ID,'text':text[:4090],'parse_mode':'HTML','disable_web_page_preview':'true'}).encode()
    req=urllib.request.Request(f'https://api.telegram.org/bot{TOKEN}/sendMessage',data=data,method='POST')
    with urllib.request.urlopen(req,timeout=20) as r:
        out=json.loads(r.read().decode())
    if not out.get('ok'):raise RuntimeError(f'Telegram send failed: {out}')


def message(br,ma,v):
    pce3='확인 불가' if ma.get('core_3m_ann') is None else f"{ma['core_3m_ann']:.2f}%"
    pce6='확인 불가' if ma.get('core_6m_ann') is None else f"{ma['core_6m_ann']:.2f}%"
    real='확인 불가' if ma.get('real_pce_3m_ann') is None else f"{ma['real_pce_3m_ann']:+.1f}%"
    bei='확인 불가' if ma.get('bei5y_10d_bp') is None else f"{ma['bei5y_10d_bp']:+.0f}bp"
    emp='약화' if ma.get('employment_soft') else '급랭 미확인'
    return '\n'.join([
        '[Warsh 에너지 공급충격 판정]',
        f"기준: {br['date']}", '',
        '<b>핵심 판정</b>', f"• <b>{html.escape(v)}</b>", '',
        '<b>현재 숫자</b>',
        f"• 브렌트유: {br['value']:.2f}달러/배럴 · 최근 20거래일 {br['d20_pct']:+.1f}%",
        f"• 기준시점: {html.escape(br.get('measurement_basis') or '최근 완료 거래일 종가')} · {html.escape(br.get('quality_note') or '정상')}",
        f"• 근원 PCE 추세: 3개월 연율 {pce3} · 6개월 연율 {pce6}",
        f"• 5년 기대인플레이션: {ma['bei5y']:.2f}% · 최근 10거래일 {bei}",
        f"• 실질 개인소비: 최근 3개월 연율 {real}",
        f"• 고용: {emp}" + (f" · 비농업 고용 {ma['payroll_change_k']:+.0f}천명 · 실업률 {ma['unemployment_rate']:.1f}%" if ma.get('payroll_change_k') is not None and ma.get('unemployment_rate') is not None else ''),
        f"• 신용: H.8 {ma.get('h8') or '확인 불가'} · SLOOS {ma.get('sloos') or '확인 불가'}", '',
        '<b>해석</b>',
        '• 유가 상승만으로 금리인상을 판정하지 않습니다. 근원물가·기대인플레이션으로 번지는지와 실질소비·고용·신용이 먼저 약해지는지를 분리합니다.',
        '• 물가 전이가 우세하면 추가긴축 논리가 강해지고, 수요 파괴가 우세하면 같은 시점의 추가인상은 경기하강을 키울 위험이 커집니다.',
        '• 이는 Jefferson 부의장이 설명한 공급충격의 물가·고용 상충 구조를 최신 데이터에 대입한 해석입니다.', '',
        '<b>원천</b>',
        f"{link(br['source'],br['url'])} · {link('연준 Jefferson 공식 발언',JEFFERSON_URL)}",
        f"{link('FRED 5년 기대인플레이션',FRED_BEI)} · {link('FRED 실질 개인소비',FRED_REAL_PCE)}",
    ])


def main():
    old=load_json(STATE_PATH)
    try:
        br=brent_snapshot()
    except Exception as exc:
        # 선물 원자료 검증 실패 시 현물 등 다른 상품으로 치환해 판정하지 않습니다.
        print(json.dumps({
            'first_run':not bool(old),'sent':False,'data_valid':False,
            'error':f'{type(exc).__name__}: {exc}',
            'rule':'브렌트 선물 완료종가 확인 실패 → 기존 상태 유지·알림 금지'
        },ensure_ascii=False))
        return

    ma=macro_snapshot(); v=verdict(br,ma)
    new={'schema_version':3,'brent':br,'macro':ma,'verdict':v}; first=not bool(old)
    changed=(old.get('brent',{}).get('active') not in (None,br['active']) or old.get('verdict') not in (None,v))

    correction=False
    old_br=(old.get('brent') or {})
    if old and int(old.get('schema_version') or 1)<3:
        ov=old_br.get('value')
        old_basis=old_br.get('measurement_basis')
        if old_basis!='최근 완료 거래일 종가' or (isinstance(ov,(int,float)) and abs(float(ov)-float(br['value']))>=2.0):
            correction=True

    if FORCE_NOTIFY or correction or (not first and changed):
        if correction:
            oldv=old_br.get('value')
            oldtxt=f'{float(oldv):.2f}달러' if isinstance(oldv,(int,float)) else '이전값'
            correction_head='\n'.join([
                '<b>[최종 정정 · Warsh 에너지 공급충격]</b>',
                f'• 직전 {oldtxt} 값은 동일한 브렌트 선물의 완료 종가 기준이 아니어서 폐기합니다.',
                f"• 재검증 기준: {br['date']} 브렌트 선물 완료 종가 {br['value']:.2f}달러",
                '• 앞으로 이 거시 경보는 현재 진행 중 일봉·현물가격으로 대체하지 않고 브렌트 선물의 완료된 거래일 종가만 사용합니다.',
                ''
            ])
            send(correction_head+message(br,ma,v))
        else:
            send(message(br,ma,v))

    save_json(STATE_PATH,new)
    print(json.dumps({
        'first_run':first,'sent':bool(FORCE_NOTIFY or correction or (not first and changed)),
        'data_valid':True,'date':br['date'],'active':br['active'],'brent':br['value'],
        'd20_pct':br['d20_pct'],'verdict':v,'basis':br.get('measurement_basis'),
        'correction':correction
    },ensure_ascii=False))

if __name__=='__main__':main()
