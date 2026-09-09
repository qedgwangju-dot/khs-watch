#!/usr/bin/env python3
"""AI hardware vs software relative-strength watcher.

This is a price-based regime signal, not a fund-flow estimate. It looks for sustained
3/5 trading-day outperformance of semiconductors and confirms whether memory,
optical/networking and semiconductor-equipment baskets are participating.
"""
import html
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
STATE_PATH=ROOT/'data/warsh_ai_rotation_watch_state.json'
TOKEN=(os.getenv('TELEGRAM_BOT_TOKEN') or '').strip()
CHAT_ID=(os.getenv('TELEGRAM_CHAT_ID') or '').strip()
EXPECTED_BOT=(os.getenv('EXPECTED_BOT_USERNAME') or 'khs8879887988798879_bot').strip().lstrip('@')
FORCE_NOTIFY=os.getenv('FORCE_NOTIFY','0')=='1'
THRESH_5D=float(os.getenv('WARSH_ROTATION_5D_PP','5'))
THRESH_3D=float(os.getenv('WARSH_ROTATION_3D_PP','3'))
UA='Mozilla/5.0 (compatible; khs-watch/1.0; +https://github.com/qedgwangju-dot/khs-watch)'
YAHOO='https://query1.finance.yahoo.com/v8/finance/chart/{}?range=1mo&interval=1d&includePrePost=false'

SYMBOLS={
    '반도체':'SOXX','소프트웨어':'IGV',
    'Micron':'MU','SanDisk':'SNDK',
    'Coherent':'COHR','Lumentum':'LITE','Marvell':'MRVL',
    'Applied Materials':'AMAT','KLA':'KLAC',
}


def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept-Language':'en-US,en;q=0.9'})
    with urllib.request.urlopen(req,timeout=25) as r:return r.read().decode('utf-8',errors='replace')


def series(symbol):
    url=YAHOO.format(urllib.parse.quote(symbol,safe=''))
    d=json.loads(fetch(url)); result=((d.get('chart') or {}).get('result') or [None])[0]
    if not result:raise RuntimeError(f'{symbol} chart unavailable')
    ts=result.get('timestamp') or []; q=((result.get('indicators') or {}).get('quote') or [{}])[0]
    closes=q.get('close') or []; rows=[]
    for t,c in zip(ts,closes):
        if c is None:continue
        rows.append((datetime.fromtimestamp(t,timezone.utc).date().isoformat(),float(c)))
    if len(rows)<7:raise RuntimeError(f'{symbol} history too short')
    return rows


def ret(rows,n):
    return (rows[-1][1]/rows[-1-n][1]-1)*100


def avg(vals):return sum(vals)/len(vals) if vals else None


def snapshot():
    data={name:series(sym) for name,sym in SYMBOLS.items()}
    out={'date':data['반도체'][-1][0],'returns':{}}
    for name,rows in data.items():
        out['returns'][name]={'1d':ret(rows,1),'3d':ret(rows,3),'5d':ret(rows,5)}
    sw=out['returns']['소프트웨어']; semi=out['returns']['반도체']
    out['relative_3d']=semi['3d']-sw['3d']; out['relative_5d']=semi['5d']-sw['5d']
    baskets={
        '메모리':['Micron','SanDisk'],
        '광연결·네트워크':['Coherent','Lumentum','Marvell'],
        '반도체 장비':['Applied Materials','KLA'],
    }
    out['baskets']={}
    confirms=0
    for label,names in baskets.items():
        r5=avg([out['returns'][n]['5d'] for n in names]); rel=r5-sw['5d']
        out['baskets'][label]={'5d':r5,'vs_software_5d':rel}
        if rel>=THRESH_5D:confirms+=1
    out['confirm_count']=confirms
    active=(out['relative_5d']>=THRESH_5D and out['relative_3d']>=THRESH_3D and confirms>=2)
    out['active']=active
    if active and confirms==3:
        out['verdict']='AI 하드웨어 확산 확인 — 반도체에서 메모리·광연결·장비까지 동반 우위'
    elif active:
        out['verdict']='AI 하드웨어 우위 지속 — 공급망 확산 일부 확인'
    elif out['relative_5d']>=THRESH_5D:
        out['verdict']='반도체 우위지만 공급망 확산 확인 부족'
    elif out['relative_5d']<=-THRESH_5D:
        out['verdict']='소프트웨어 상대우위 — 하드웨어 로테이션 약화'
    else:
        out['verdict']='뚜렷한 구조적 로테이션 미확인'
    return out


def load_state():
    try:return json.loads(STATE_PATH.read_text(encoding='utf-8'))
    except Exception:return {}

def save_state(s):
    STATE_PATH.parent.mkdir(parents=True,exist_ok=True); s['updated_at_utc']=datetime.now(timezone.utc).isoformat()
    STATE_PATH.write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def get_bot_username():
    with urllib.request.urlopen(f'https://api.telegram.org/bot{TOKEN}/getMe',timeout=20) as r:d=json.loads(r.read().decode())
    return str((d.get('result') or {}).get('username') or '')
def link(label,url):return f'<a href="{html.escape(url,quote=True)}">{html.escape(label)}</a>'
def quote_url(sym):return 'https://finance.yahoo.com/quote/'+urllib.parse.quote(sym,safe='=^')+'/'
def send(text):
    if not TOKEN or not CHAT_ID:raise RuntimeError('Telegram token/chat id missing')
    u=get_bot_username()
    if u.lower()!=EXPECTED_BOT.lower():raise RuntimeError(f'Wrong Telegram bot: expected @{EXPECTED_BOT}, got @{u}')
    data=urllib.parse.urlencode({'chat_id':CHAT_ID,'text':text[:4090],'parse_mode':'HTML','disable_web_page_preview':'true'}).encode()
    req=urllib.request.Request(f'https://api.telegram.org/bot{TOKEN}/sendMessage',data=data,method='POST')
    with urllib.request.urlopen(req,timeout=20) as r:
        out=json.loads(r.read().decode())
    if not out.get('ok'):raise RuntimeError(f'Telegram send failed: {out}')


def message(s):
    sw=s['returns']['소프트웨어']; semi=s['returns']['반도체']
    lines=[
        '[AI 하드웨어·소프트웨어 상대강도]',f"기준: {s['date']}",'',
        '<b>핵심 판정</b>',f"• <b>{html.escape(s['verdict'])}</b>",'',
        '<b>현재 숫자</b>',
        f"• 반도체(SOXX): 3거래일 {semi['3d']:+.1f}% · 5거래일 {semi['5d']:+.1f}%",
        f"• 소프트웨어(IGV): 3거래일 {sw['3d']:+.1f}% · 5거래일 {sw['5d']:+.1f}%",
        f"• 반도체 초과수익: 3거래일 <b>{s['relative_3d']:+.1f}%p</b> · 5거래일 <b>{s['relative_5d']:+.1f}%p</b>",
    ]
    for label,b in s['baskets'].items():
        lines.append(f"• {label}: 5거래일 {b['5d']:+.1f}% · 소프트웨어 대비 {b['vs_software_5d']:+.1f}%p")
    lines += [
        '', '<b>해석</b>',
        '• 하루 급등은 숏커버나 개별 뉴스일 수 있어 3·5거래일 지속성과 메모리·광연결·장비의 동반 참여를 같이 봅니다.',
        '• 이 신호는 가격 상대강도입니다. ETF 자금유입이나 기관 순매수를 직접 측정한 것은 아니므로 ‘자금 이동 확정’으로 표현하지 않습니다.',
        '• 하드웨어 우위가 지속되면 시장이 금리민감한 기대형 성장주보다 실제 AI 설비투자→수주→매출 연결이 빠른 공급망을 선호하는지 확인하는 신호입니다.',
        '', '<b>원천</b>',
        f"{link('반도체 SOXX',quote_url('SOXX'))} · {link('소프트웨어 IGV',quote_url('IGV'))} · {link('Micron',quote_url('MU'))} · {link('Lumentum',quote_url('LITE'))}",
    ]
    return '\n'.join(lines)


def main():
    old=load_state(); s=snapshot(); first=not bool(old)
    changed=(old.get('active') not in (None,s['active']) or old.get('verdict') not in (None,s['verdict']))
    if FORCE_NOTIFY or (not first and changed):send(message(s))
    save_state(s)
    print(json.dumps({'first_run':first,'active':s['active'],'relative_3d':s['relative_3d'],'relative_5d':s['relative_5d'],'confirm_count':s['confirm_count'],'verdict':s['verdict']},ensure_ascii=False))

if __name__=='__main__':main()
