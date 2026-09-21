#!/usr/bin/env python3
import html
import json
import os
import urllib.parse
import urllib.request
import time
from datetime import datetime, timezone
from pathlib import Path

STATE_PATH=Path('data/market_internal_strength_watch_state.json')
TOKEN=(os.getenv('TELEGRAM_BOT_TOKEN') or '').strip()
CHAT_ID=(os.getenv('TELEGRAM_CHAT_ID') or '').strip()
EXPECTED_BOT=(os.getenv('EXPECTED_BOT_USERNAME') or 'khs887900887900008879_bot').strip().lstrip('@')
FORCE=os.getenv('FORCE_NOTIFY','0')=='1'
UA='Mozilla/5.0 (compatible; khs-watch/3.0; +https://github.com/qedgwangju-dot/khs-watch)'
YAHOO='https://query1.finance.yahoo.com/v8/finance/chart/{}?range=1mo&interval=1d&includePrePost=false'

SYMBOLS={
    'S&P500':'SPY','동일가중 S&P500':'RSP','중소형주':'IWM','하이일드 회사채':'HYG','VIX':'^VIX',
    '커뮤니케이션':'XLC','경기소비재':'XLY','필수소비재':'XLP','에너지':'XLE','금융':'XLF','헬스케어':'XLV',
    '산업재':'XLI','소재':'XLB','부동산':'XLRE','기술':'XLK','유틸리티':'XLU',
}
SECTORS=['커뮤니케이션','경기소비재','필수소비재','에너지','금융','헬스케어','산업재','소재','부동산','기술','유틸리티']


def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept-Language':'en-US,en;q=0.9'})
    with urllib.request.urlopen(req,timeout=25) as r:return r.read().decode('utf-8','replace')

def series(symbol):
    d=json.loads(fetch(YAHOO.format(urllib.parse.quote(symbol,safe=''))))
    r=((d.get('chart') or {}).get('result') or [None])[0]
    if not r: raise RuntimeError(f'{symbol} unavailable')
    ts=r.get('timestamp') or []; q=(((r.get('indicators') or {}).get('quote') or [{}])[0].get('close') or [])
    meta=r.get('meta') or {}
    regular=((meta.get('currentTradingPeriod') or {}).get('regular') or {})
    regular_start=regular.get('start'); regular_end=regular.get('end')
    now=time.time()
    rows=[]
    for t,v in zip(ts,q):
        if v is None:
            continue
        # Yahoo 1d chart can expose the current, still-open U.S. session as a daily bar.
        # Do not treat that partial bar as a completed daily close.
        if regular_start and regular_end and regular_start <= t <= regular_end and now < regular_end + 900:
            continue
        rows.append((datetime.fromtimestamp(t,timezone.utc).date().isoformat(),float(v)))
    if len(rows)<7: raise RuntimeError(f'{symbol} completed-session history too short')
    return rows

def ret(rows,n): return (rows[-1][1]/rows[-1-n][1]-1)*100.0

def snapshot():
    data={k:series(v) for k,v in SYMBOLS.items()}
    out={'date':data['S&P500'][-1][0],'returns':{}}
    for name,rows in data.items(): out['returns'][name]={'1d':ret(rows,1),'3d':ret(rows,3),'5d':ret(rows,5)}
    spy=out['returns']['S&P500']; rsp=out['returns']['동일가중 S&P500']; iwm=out['returns']['중소형주']; hyg=out['returns']['하이일드 회사채']; vix=out['returns']['VIX']
    out['rsp_rel_5d']=rsp['5d']-spy['5d']; out['iwm_rel_5d']=iwm['5d']-spy['5d']
    out['sector_up_1d']=sum(1 for s in SECTORS if out['returns'][s]['1d']>0)
    out['sector_up_5d']=sum(1 for s in SECTORS if out['returns'][s]['5d']>0)
    if spy['5d']<0 and out['rsp_rel_5d']<=-1.0 and out['iwm_rel_5d']<=-1.0 and hyg['5d']<=-1.0 and vix['5d']>=15:
        verdict='광범위 위험회피 — 순환매보다 자금 이탈 경계'
    elif out['rsp_rel_5d']<=-1.5 and out['sector_up_5d']<=4:
        verdict='대형주 편중 — 지수보다 시장 내부 체력 약함'
    elif (out['rsp_rel_5d']>=0.75 or out['iwm_rel_5d']>=0.75) and hyg['5d']>-1.0 and vix['5d']<15 and out['sector_up_5d']>=6:
        verdict='순환매·시장 내부 체력 양호'
    elif out['sector_up_5d']>=7 and hyg['5d']>-0.5:
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

def easy_read(s):
    r=s['returns']; hyg=r['하이일드 회사채']; vix=r['VIX']
    if s['verdict']=='순환매·시장 내부 체력 양호':
        return '지수 몇 종목만 버티는 장이 아니라 동일가중·중소형주·여러 업종까지 같이 움직이고 있어, 돈이 시장 밖으로 빠지기보다 업종 사이를 돌고 있는 모습에 가깝습니다.'
    if s['verdict']=='종목·업종 순환매 유지':
        return '지수는 흔들려도 여러 업종이 번갈아 오르고 회사채도 크게 흔들리지 않아, 아직 전면적인 위험회피보다 순환매 성격이 남아 있습니다.'
    if s['verdict'].startswith('광범위 위험회피'):
        return '대형주뿐 아니라 동일가중·중소형주·회사채까지 같이 약해지고 변동성도 뛰어, 단순 순환매가 아니라 실제 위험회피로 번질 가능성을 경계해야 합니다.'
    if s['verdict'].startswith('대형주 편중'):
        return '지수는 버텨 보여도 동일가중과 여러 업종이 뒤처져, 소수 대형주가 지수를 받치는 장에 가깝습니다.'
    return '좋은 업종과 약한 업종이 섞여 있어, 순환매가 살아 있다고 단정하기도 전면 위험회피라고 보기도 이릅니다.'

def message(s, correction=False, old_date=None):
    r=s['returns']; spy=r['S&P500']; rsp=r['동일가중 S&P500']; iwm=r['중소형주']; hyg=r['하이일드 회사채']; vix=r['VIX']
    title='[정정·미국 증시 내부 체력·순환매]' if correction else '[미국 증시 내부 체력·순환매]'
    lines=[f'<b>{title}</b>',f"기준: {s['date']} 미국 정규장 종가"]
    if correction:
        lines += ['', '<b>정정 사유</b>', f"• 직전 {old_date or '당일'} 값은 정규장 진행 중의 부분 일봉이 섞인 값이어서 종가 기준 판정에서 제외했습니다."]
    lines += ['', '<b>한눈에 보기</b>',
           f"• <b>{html.escape(s['verdict'])}</b>",
           f"• S&P 500(SPY): 5거래일 {spy['5d']:+.1f}%",
           f"• 동일가중 S&P 500(RSP): 5거래일 {rsp['5d']:+.1f}% · S&P 대비 {s['rsp_rel_5d']:+.1f}%p",
           f"• 중소형주(IWM): 5거래일 {iwm['5d']:+.1f}% · S&P 대비 {s['iwm_rel_5d']:+.1f}%p",
           f"• 11개 업종 중 상승: 1거래일 {s['sector_up_1d']}개 · 5거래일 {s['sector_up_5d']}개",
           f"• 하이일드 회사채(HYG): 5거래일 {hyg['5d']:+.1f}% · VIX(주식시장 공포·변동성 지수): 5거래일 {vix['5d']:+.1f}%",'',
           '<b>쉽게 말하면</b>',f"• {easy_read(s)}",'',
           '<b>왜 보나</b>',
           '• RSP가 SPY보다 강하면 몇몇 초대형주만 오르는 게 아니라 종목 전체로 상승이 퍼지는지 보는 대용지표입니다.',
           '• HYG(하이일드 회사채)는 신용위험이 커질 때 먼저 약해질 수 있어, 주식의 순환매가 진짜 체력인지 확인하는 보조지표입니다.',
           '• VIX는 주식시장 변동성 기대를 보여주는 지수로, 급등하면 위험회피가 강해졌다는 뜻입니다.', '',
           '<b>판정이 나빠지는 조건</b>',
           '• 동일가중·중소형주가 S&P보다 5거래일 기준 1%포인트 이상 더 약해짐',
           '• HYG가 5거래일 -1% 이하로 밀리고 VIX가 15% 이상 급등',
           '• 11개 업종 중 상승 업종이 4개 이하로 축소', '',
           '<b>원천</b>', f"{link('SPY',quote_url('SPY'))} · {link('RSP',quote_url('RSP'))} · {link('IWM',quote_url('IWM'))} · {link('HYG',quote_url('HYG'))} · {link('VIX',quote_url('^VIX'))}"]
    return '\n'.join(lines)

def main():
    s=snapshot(); old=load_state(); first=not bool(old)
    new_day=old.get('date') not in (None,s['date']); changed=old.get('verdict') not in (None,s['verdict'])
    correction=bool(old.get('date') and old.get('date') > s['date'])
    shock=(s['returns']['VIX']['5d']>=20 or s['returns']['하이일드 회사채']['5d']<=-2.0)
    old_shock=bool(old.get('shock'))
    should=FORCE or correction or (not first and (changed or (shock and not old_shock)))
    if should: send(message(s, correction=correction, old_date=old.get('date')))
    if first or new_day or changed or shock!=old_shock:
        save_state({'date':s['date'],'verdict':s['verdict'],'shock':shock,'rsp_rel_5d':s['rsp_rel_5d'],'iwm_rel_5d':s['iwm_rel_5d'],'sector_up_1d':s['sector_up_1d'],'sector_up_5d':s['sector_up_5d'],'returns':s['returns']})
    print(json.dumps({'first_run':first,'date':s['date'],'verdict':s['verdict'],'shock':shock,'rsp_rel_5d':s['rsp_rel_5d'],'iwm_rel_5d':s['iwm_rel_5d'],'sector_up_5d':s['sector_up_5d'],'sent':should},ensure_ascii=False))

if __name__=='__main__': main()
