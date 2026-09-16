#!/usr/bin/env python3
import hashlib
import html
import json
import os
import re
import statistics
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

STATE_PATH = Path('data/warsh_ib_consensus_watch_state.json')
TOKEN = (os.getenv('TELEGRAM_BOT_TOKEN') or '').strip()
CHAT_ID = (os.getenv('TELEGRAM_CHAT_ID') or '').strip()
EXPECTED_BOT = (os.getenv('EXPECTED_BOT_USERNAME') or 'khs8879887988798879_bot').strip().lstrip('@')
FORCE = os.getenv('FORCE_NOTIFY', '0') == '1'
UA = 'Mozilla/5.0 (compatible; khs-watch/3.0; +https://github.com/qedgwangju-dot/khs-watch)'

# Baseline is the 2026-09-15 WSJ table supplied for this watch.
BASELINE = {
    'Bank of America': {'next_move':'Sep hike','change_2026_bp':75},
    'Barclays': {'next_move':'Sep hike','change_2026_bp':50},
    'BNP Paribas': {'next_move':'Sep hike','change_2026_bp':50},
    'Citigroup': {'next_move':'Sep hike','change_2026_bp':50},
    'Deutsche Bank': {'next_move':'Sep hike','change_2026_bp':75},
    'Goldman Sachs': {'next_move':'Sep hike','change_2026_bp':25},
    'HSBC': {'next_move':'Sep hike','change_2026_bp':50},
    'Jefferies': {'next_move':'Dec cut','change_2026_bp':-25},
    'JPMorgan': {'next_move':'Sep hike','change_2026_bp':50},
    'Mizuho': {'next_move':'Sep hike','change_2026_bp':50},
    'Morgan Stanley': {'next_move':'Sep hike','change_2026_bp':50},
    'MPA Macro': {'next_move':'Sep hike','change_2026_bp':50},
    'MUFG': {'next_move':'Sep hike','change_2026_bp':50},
    'Nationwide': {'next_move':'Sep hike','change_2026_bp':50},
    'Nomura': {'next_move':'Sep hike','change_2026_bp':50},
    'Oxford Economics': {'next_move':'2027 cut','change_2026_bp':0},
    'Piper Sandler': {'next_move':'Sep hike','change_2026_bp':50},
    'RBC': {'next_move':'Sep hike','change_2026_bp':75},
    'Societe Generale': {'next_move':'Sep hike','change_2026_bp':50},
    'TD Securities': {'next_move':'Sep hike','change_2026_bp':50},
    'UBS': {'next_move':'Sep hike','change_2026_bp':50},
    'Wells Fargo': {'next_move':'Sep hike','change_2026_bp':50},
}

ALIASES = {
    'Bank of America':['Bank of America','BofA'], 'Barclays':['Barclays'], 'BNP Paribas':['BNP Paribas','BNPP'],
    'Citigroup':['Citigroup','Citi'], 'Deutsche Bank':['Deutsche Bank'], 'Goldman Sachs':['Goldman Sachs','Goldman'],
    'HSBC':['HSBC'], 'Jefferies':['Jefferies'], 'JPMorgan':['JPMorgan','JP Morgan','J.P. Morgan'], 'Mizuho':['Mizuho'],
    'Morgan Stanley':['Morgan Stanley'], 'MPA Macro':['MPA Macro'], 'MUFG':['MUFG'], 'Nationwide':['Nationwide'],
    'Nomura':['Nomura'], 'Oxford Economics':['Oxford Economics'], 'Piper Sandler':['Piper Sandler'], 'RBC':['RBC','Royal Bank of Canada'],
    'Societe Generale':['Societe Generale','Société Générale'], 'TD Securities':['TD Securities'], 'UBS':['UBS'], 'Wells Fargo':['Wells Fargo'],
}

TRUSTED = {'Reuters','The Wall Street Journal','WSJ','CNBC','Bloomberg','Financial Times','Barron’s','Barrons'}
QUERIES = [
    'Fed September 2026 hike forecast Goldman Sachs Morgan Stanley JPMorgan HSBC',
    'Fed September 2026 hike forecast Bank of America Deutsche Bank RBC Citigroup',
    'Fed September 2026 hike forecast Barclays UBS Wells Fargo Nomura Mizuho',
    'Fed September 2026 hike forecast Jefferies Oxford Economics Piper Sandler TD Securities BNP MUFG',
]


def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept-Language':'en-US,en;q=0.9'})
    with urllib.request.urlopen(req,timeout=25) as r:return r.read().decode('utf-8','replace')


def clean(value):
    value=re.sub(r'(?s)<[^>]+>',' ',value or '')
    return html.unescape(re.sub(r'\s+',' ',value)).strip()


def rss_items(query):
    q=urllib.parse.quote(query)
    url=f'https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en'
    raw=fetch(url); root=ET.fromstring(raw); out=[]
    for item in root.findall('.//item')[:60]:
        title=clean(item.findtext('title')); desc=clean(item.findtext('description')); link=(item.findtext('link') or '').strip()
        src=item.find('source'); publisher=clean(src.text if src is not None else '')
        if publisher not in TRUSTED: continue
        out.append({'title':title,'description':desc,'url':link,'publisher':publisher})
    return out


def identify_institutions(text):
    low=text.lower(); found=[]
    for inst,als in ALIASES.items():
        if any(a.lower() in low for a in als): found.append(inst)
    return found


def parse_forecast(text):
    low=text.lower().replace('basis points','bp').replace('basis point','bp')
    out={}
    if re.search(r'september\s+(?:rate\s+)?hike|hike\s+(?:in|at)\s+september|raise[^.]{0,50}september',low): out['next_move']='Sep hike'
    elif re.search(r'december\s+(?:rate\s+)?cut|cut\s+(?:in|at)\s+december',low): out['next_move']='Dec cut'
    elif re.search(r'2027[^.]{0,40}cut|cut[^.]{0,40}2027',low): out['next_move']='2027 cut'
    elif re.search(r'september[^.]{0,30}(?:hold|unchanged|no hike)|(?:hold|unchanged|no hike)[^.]{0,30}september',low): out['next_move']='Sep hold'

    if re.search(r'(?:three|3)\s+(?:rate\s+)?hikes|(?:total|cumulative)[^.]{0,20}75\s*bp|75\s*bp[^.]{0,25}(?:2026|year)',low): out['change_2026_bp']=75
    elif re.search(r'(?:two|2)\s+(?:rate\s+)?hikes|(?:total|cumulative)[^.]{0,20}50\s*bp|50\s*bp[^.]{0,25}(?:2026|year)',low): out['change_2026_bp']=50
    elif re.search(r'(?:one|1)\s+(?:rate\s+)?hike|(?:total|cumulative)[^.]{0,20}25\s*bp|25\s*bp[^.]{0,25}(?:2026|year)',low): out['change_2026_bp']=25
    elif out.get('next_move')=='Dec cut' and re.search(r'25\s*bp|quarter[- ]point',low): out['change_2026_bp']=-25
    elif out.get('next_move')=='2027 cut': out['change_2026_bp']=0
    return out


def explicit_change_language(text):
    low=text.lower()
    return bool(re.search(r'now expects|turns more hawkish|turns hawkish|revises|revised|changes? forecast|shifts? forecast|forecasts?|expects?',low))


def gather_evidence():
    items=[]; seen=set()
    for q in QUERIES:
        try: rows=rss_items(q)
        except Exception: continue
        for row in rows:
            key=row['url'] or row['title']
            if key in seen: continue
            seen.add(key); items.append(row)
    ev={k:[] for k in BASELINE}
    for row in items:
        text=row['title']+' '+row['description']
        if not explicit_change_language(text): continue
        parsed=parse_forecast(text)
        if not parsed: continue
        for inst in identify_institutions(text):
            ev[inst].append({**row,'parsed':parsed})
    return ev


def merged_candidate(current, parsed):
    x=dict(current); x.update(parsed); return x


def candidate_key(x): return (x.get('next_move'),x.get('change_2026_bp'))


def evaluate(current, evidence):
    confirmed=[]; candidates=[]
    for inst,rows in evidence.items():
        if not rows: continue
        groups={}
        for row in rows:
            cand=merged_candidate(current[inst],row['parsed']); groups.setdefault(candidate_key(cand),[]).append(row)
        for key,group in groups.items():
            cand={'next_move':key[0],'change_2026_bp':key[1]}
            if candidate_key(current[inst])==key: continue
            pubs={r['publisher'] for r in group}
            obj={'institution':inst,'old':current[inst],'new':cand,'evidence':group[:4]}
            if len(pubs)>=2: confirmed.append(obj)
            elif group[0]['publisher'] in {'Reuters','The Wall Street Journal','WSJ','Bloomberg','Financial Times','CNBC'}:
                candidates.append(obj)
    return confirmed,candidates


def stats(forecasts):
    vals=[v['change_2026_bp'] for v in forecasts.values()]
    return {
        'total':len(vals),
        'sep_hike':sum(1 for v in forecasts.values() if v['next_move']=='Sep hike'),
        'net_hike':sum(1 for v in forecasts.values() if v['change_2026_bp']>0),
        'at_least_50':sum(1 for v in forecasts.values() if v['change_2026_bp']>=50),
        'median':statistics.median(vals),
        'mean':sum(vals)/len(vals),
    }


def load_state():
    try:return json.loads(STATE_PATH.read_text(encoding='utf-8')) if STATE_PATH.exists() else {}
    except Exception:return {}


def save_state(s):
    STATE_PATH.parent.mkdir(parents=True,exist_ok=True); STATE_PATH.write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def botname():
    with urllib.request.urlopen(f'https://api.telegram.org/bot{TOKEN}/getMe',timeout=20) as r:return str((json.loads(r.read().decode()).get('result') or {}).get('username') or '')

def link(label,url):return f'<a href="{html.escape(url,quote=True)}">{html.escape(label)}</a>'
def send(msg):
    if not TOKEN or not CHAT_ID: raise RuntimeError('Telegram token/chat id missing')
    actual=botname()
    if actual.lower()!=EXPECTED_BOT.lower(): raise RuntimeError(f'Wrong Telegram bot: expected @{EXPECTED_BOT}, got @{actual}')
    data=urllib.parse.urlencode({'chat_id':CHAT_ID,'text':msg[:4090],'parse_mode':'HTML','disable_web_page_preview':'true'}).encode()
    req=urllib.request.Request(f'https://api.telegram.org/bot{TOKEN}/sendMessage',data=data,method='POST')
    with urllib.request.urlopen(req,timeout=25) as r:
        out=json.loads(r.read().decode())
    if not out.get('ok'): raise RuntimeError(f'Telegram send failed: {out}')


def move_ko(v):
    return {'Sep hike':'9월 인상','Sep hold':'9월 동결','Dec cut':'12월 인하','2027 cut':'2027년 인하'}.get(v,v)


def message(title, forecasts, changes, candidate=False):
    s=stats(forecasts)
    lines=[f'<b>[Fed 주요 IB 정책경로 컨센서스 변화]</b>','',f'<b>{html.escape(title)}</b>',
           f"• 9월 인상 전망: {s['sep_hike']}/{s['total']}곳",
           f"• 2026년 순인상 전망: {s['net_hike']}/{s['total']}곳",
           f"• 연내 최소 +50bp 전망: {s['at_least_50']}/{s['total']}곳",
           f"• 2026년 정책변화 중앙값: {s['median']:+.0f}bp · 평균 {s['mean']:+.1f}bp",'', '<b>무엇이 달라졌나</b>']
    for c in changes:
        old,new=c['old'],c['new']
        lines.append(f"• {html.escape(c['institution'])}: {move_ko(old['next_move'])} / {old['change_2026_bp']:+.0f}bp → {move_ko(new['next_move'])} / {new['change_2026_bp']:+.0f}bp")
    lines += ['', '<b>쉽게 말하면</b>']
    if s['at_least_50'] >= 15:
        lines.append('• 월가의 질문이 “이번에 올릴까?”보다 “이번 인상 뒤 몇 번 더 올릴까?” 쪽으로 이동한 상태입니다.')
    else:
        lines.append('• IB들의 추가 인상 전망이 약해지고 있는지 확인해야 하는 구간입니다.')
    lines += ['• 2년물 금리가 같이 오르면 시장도 같은 정책경로를 가격에 넣는다는 뜻이고, 10년물까지 크게 오르면 장기 할인율 부담도 함께 커집니다.',
              '• 1bp = 0.01%포인트입니다.']
    if candidate:
        lines += ['', '<b>주의</b>', '• 아래 변화는 단일 신뢰보도에서만 잡힌 변화 후보입니다. 두 번째 독립 출처가 확인되기 전에는 전체 컨센서스 숫자에 반영하지 않습니다.']
    lines += ['', '<b>근거</b>']
    for c in changes:
        for i,row in enumerate(c['evidence'][:2],1):
            lines.append(f"• {html.escape(c['institution'])} {i}: {link(row['publisher'],row['url'])}")
    return '\n'.join(lines)


def main():
    state=load_state()
    if not state:
        state={'baseline_date':'2026-09-15','baseline_source':'WSJ 표','forecasts':BASELINE,'candidate_seen':[]}
        save_state(state)
        if FORCE: send(message('기준선 저장',state['forecasts'],[],False))
        print(json.dumps({'first_run':True,'stats':stats(BASELINE)},ensure_ascii=False)); return

    current=state.get('forecasts') or BASELINE
    evidence=gather_evidence(); confirmed,candidates=evaluate(current,evidence)
    sent=[]
    if confirmed:
        for c in confirmed: current[c['institution']]=c['new']
        send(message('교차검증된 전망 변경',current,confirmed,False)); sent.append('confirmed')
        state['forecasts']=current

    seen=set(state.get('candidate_seen') or [])
    fresh=[]
    for c in candidates:
        raw=c['institution']+'|'+json.dumps(c['new'],sort_keys=True,ensure_ascii=False)+'|'+(c['evidence'][0].get('url') or c['evidence'][0].get('title',''))
        h=hashlib.sha256(raw.encode()).hexdigest()
        if h not in seen:
            seen.add(h); fresh.append(c)
    if fresh:
        # Do not alter consensus counts until a second independent source confirms the change.
        send(message('단일 신뢰보도 변화 후보 — 재검증 필요',current,fresh,True)); sent.append('candidate')
    state['candidate_seen']=list(seen)[-200:]
    state['last_checked_utc']=datetime.now(timezone.utc).isoformat() if sent else state.get('last_checked_utc')
    save_state(state)
    print(json.dumps({'first_run':False,'sent':sent,'confirmed':len(confirmed),'candidates':len(fresh),'stats':stats(current)},ensure_ascii=False))

if __name__=='__main__': main()
