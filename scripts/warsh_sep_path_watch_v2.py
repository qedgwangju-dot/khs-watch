#!/usr/bin/env python3
import html
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

STATE = Path('data/warsh_sep_path_watch_state.json')
PATH_STATE = Path('data/warsh_policy_path_watch_state.json')
FED_CAL = 'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm'
TOKEN = (os.getenv('TELEGRAM_BOT_TOKEN') or '').strip()
CHAT = (os.getenv('TELEGRAM_CHAT_ID') or '').strip()
BOT = (os.getenv('EXPECTED_BOT_USERNAME') or 'hshs8879_bot').strip().lstrip('@')
FORCE = os.getenv('FORCE_NOTIFY','0') == '1'
UA = 'Mozilla/5.0 (compatible; khs-watch/3.0)'
SCHEMA_VERSION = 2

class TableParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.tables=[]; self.table=None; self.row=None; self.cell=None
    def handle_starttag(self, tag, attrs):
        if tag == 'table': self.table=[]
        elif tag == 'tr' and self.table is not None: self.row=[]
        elif tag in ('td','th') and self.row is not None: self.cell=[]
    def handle_data(self, data):
        if self.cell is not None: self.cell.append(data)
    def handle_endtag(self, tag):
        if tag in ('td','th') and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split())); self.cell=None
        elif tag == 'tr' and self.row is not None:
            if any(self.row): self.table.append(self.row)
            self.row=None
        elif tag == 'table' and self.table is not None:
            self.tables.append(self.table); self.table=None

def fetch(url):
    q=urllib.request.Request(url,headers={'User-Agent':UA,'Accept-Language':'en-US,en;q=0.9'})
    with urllib.request.urlopen(q,timeout=30) as r:return r.read().decode('utf-8','replace'),r.geturl()

def num(s):
    s=html.unescape(str(s)).replace('\xa0',' ').strip()
    return float(s) if re.fullmatch(r'\d+(?:\.\d+)?',s) else None

def find_latest_sep_url():
    raw,_=fetch(FED_CAL); found={}
    for href,ds in re.findall(r'href=["\']([^"\']*fomcprojtabl(20\d{6})\.htm)["\']',raw,re.I):
        found[ds]=urllib.parse.urljoin(FED_CAL,href)
    if not found: raise RuntimeError('연준 경제전망·점도표 링크를 찾지 못함')
    ds,url=sorted(found.items())[-1]
    return ds,url

def row_values(table, label):
    for i,row in enumerate(table):
        if row and re.sub(r'\s+',' ',row[0]).strip().lower().startswith(label.lower()):
            current=[num(x) for x in row[1:6]]
            prior=[None]*5
            if i+1 < len(table) and table[i+1] and table[i+1][0].lower().startswith('june projection'):
                prior=[num(x) for x in table[i+1][1:6]]
            return current,prior
    return None,None

def latest_sep():
    ds,url=find_latest_sep_url(); page,final=fetch(url); p=TableParser(); p.feed(page)
    target=None
    for t in p.tables:
        if any(r and r[0].lower().startswith('change in real gdp') for r in t): target=t; break
    if target is None: raise RuntimeError('SEP 표 파싱 실패')
    gdp,gdp_prev=row_values(target,'Change in real GDP')
    unemp,unemp_prev=row_values(target,'Unemployment rate')
    pce,pce_prev=row_values(target,'PCE inflation')
    core,core_prev=row_values(target,'Core PCE inflation')
    funds,funds_prev=row_values(target,'Federal funds rate')
    if not funds or funds[0] is None or funds[4] is None: raise RuntimeError('연준 정책금리 중앙값 파싱 실패')
    return {
        'date':f'{ds[:4]}-{ds[4:6]}-{ds[6:]}','url':final,
        'gdp':gdp,'gdp_prev':gdp_prev,'unemp':unemp,'unemp_prev':unemp_prev,
        'pce':pce,'pce_prev':pce_prev,'core':core,'core_prev':core_prev,
        'funds':funds,'funds_prev':funds_prev,
    }

def load(path,default=None):
    try:return json.loads(path.read_text(encoding='utf-8')) if path.exists() else (default or {})
    except:return default or {}

def save(s):
    STATE.parent.mkdir(parents=True,exist_ok=True); s['updated_at_utc']=datetime.now(timezone.utc).isoformat(); STATE.write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def botname():
    with urllib.request.urlopen(f'https://api.telegram.org/bot{TOKEN}/getMe',timeout=20) as r:return json.loads(r.read().decode())['result']['username']

def link(label,url):return f'<a href="{html.escape(url,quote=True)}">{html.escape(label)}</a>'
def send(msg):
    if not TOKEN or not CHAT:raise RuntimeError('Telegram 비밀값 없음')
    if botname().lower()!=BOT.lower():raise RuntimeError(f'Telegram 봇 불일치: expected @{BOT}')
    d=urllib.parse.urlencode({'chat_id':CHAT,'text':msg[:4090],'parse_mode':'HTML','disable_web_page_preview':'true'}).encode(); q=urllib.request.Request(f'https://api.telegram.org/bot{TOKEN}/sendMessage',data=d,method='POST')
    with urllib.request.urlopen(q,timeout=20) as r:
        x=json.loads(r.read().decode())
        if not x.get('ok'):raise RuntimeError('Telegram 전송 실패')

def market_dec():
    p=load(PATH_STATE,{})
    ms=[m for m in p.get('meetings',[]) if str(m.get('date','')).startswith('2026-')]
    return sorted(ms,key=lambda x:x['date'])[-1].get('post_rate') if ms else None

def d(cur,prev,idx):
    if not cur or not prev or idx>=len(cur) or idx>=len(prev) or cur[idx] is None or prev[idx] is None:return None
    return cur[idx]-prev[idx]

def bp(x): return '' if x is None else f' ({x*100:+.0f}bp)'
def pp(x): return '' if x is None else f' ({x:+.1f}%p)'

def message(cur,market,correction=False):
    f,fp=cur['funds'],cur['funds_prev']; g,gp=cur['gdp'],cur['gdp_prev']; u,up=cur['unemp'],cur['unemp_prev']; p,pprev=cur['pce'],cur['pce_prev']; c,cp=cur['core'],cur['core_prev']
    diff=(f[0]-float(market))*100 if market is not None else None
    lines=['<b>[Warsh FOMC 점도표·경제전망·시장 경로]</b>',f"기준: {cur['date']}",'']
    if correction:
        lines += ['<b>정정</b>','• 기존 알림의 “장기 3.60%”는 2029년 값을 장기값으로 잘못 읽은 표기였습니다.','• 공식 장기 정책금리 중앙값은 <b>3.20%</b>이며, 6월 3.10%에서 +10bp 상승했습니다.','']
    lines += ['<b>핵심 판정</b>','• <b>경기는 더 강하게 · 실업률은 더 낮게 · 물가는 더 높게 · 정책금리는 더 높게</b>','• 쉽게 말하면: 연준은 “경기가 금리인상을 버틸 수 있고, 물가는 아직 끈적하다”는 쪽으로 전망을 옮겼습니다.','',
              '<b>정책금리 점도표</b>',
              f"• 2026년 말 {f[0]:.1f}%{bp(d(f,fp,0))} · 2027년 말 {f[1]:.1f}%{bp(d(f,fp,1))}",
              f"• 2028년 말 {f[2]:.1f}%{bp(d(f,fp,2))} · 2029년 말 {f[3]:.1f}% · 장기 {f[4]:.1f}%{bp(d(f,fp,4))}",
              '• 2027년 말도 4.1%라는 것은 중앙값 기준으로 연내 추가 인상 뒤 높은 금리를 다음 해 말까지 유지하는 경로입니다.','',
              '<b>경제·고용·물가 전망</b>',
              f"• 실질 GDP 성장률: 2026년 {g[0]:.1f}%{pp(d(g,gp,0))} · 2027년 {g[1]:.1f}%{pp(d(g,gp,1))}",
              f"• 실업률: 2026년 {u[0]:.1f}%{pp(d(u,up,0))} · 2027년 {u[1]:.1f}%{pp(d(u,up,1))}",
              f"• PCE(전체 개인소비지출 물가): 2026년 {p[0]:.1f}%{pp(d(p,pprev,0))}",
              f"• 근원 PCE(식품·에너지 제외): 2026년 {c[0]:.1f}%{pp(d(c,cp,0))}",'']
    if market is not None:
        lines += ['<b>시장 선물경로와 비교</b>',f"• 현재 공개 선물경로의 2026년 말 유효 연방기금금리 약 {float(market):.3f}%",f"• 연준 2026년 말 중앙값 - 시장 경로: {diff:+.0f}bp",'']
    lines += ['<b>왜 중요한가</b>','• 이번 변화는 단순히 “한 번 더 올릴 수 있다”는 수준보다 큽니다. 성장·고용 전망은 좋아졌는데 물가와 장기 적정금리 전망도 함께 올라, 고금리를 더 오래 유지할 수 있다는 논리가 강화됐습니다.','• 장기 정책금리 3.2%는 경기·물가 충격이 사라졌을 때 참가자들이 적절하다고 보는 장기 정책금리 중앙값입니다. 실제 금리를 3.2%로 고정하겠다는 약속은 아닙니다.','',
              '<b>다음 확인</b>','• 근원 PCE 3·6개월 연율이 실제로 내려오는지','• 실업률과 비농업 고용 3개월 평균이 약해지는지','• 2년물 금리가 추가 인상 경로를 계속 유지하는지','',
              '<b>원천</b>',f"{link('연준 경제전망·점도표',cur['url'])} · {link('연준 FOMC 일정',FED_CAL)}"]
    return '\n'.join(lines)

def main():
    cur=latest_sep(); old=load(STATE,{}); market=market_dec()
    old_schema=old.get('schema_version',1)
    old_url=(old.get('snapshot') or {}).get('url')
    new_release=bool(old_url and old_url!=cur['url'])
    correction=(old_schema<SCHEMA_VERSION)
    should_send=FORCE or correction or new_release
    if should_send: send(message(cur,market,correction=correction))
    save({'schema_version':SCHEMA_VERSION,'snapshot':cur,'market_2026_yearend':market,'sent_upgrade':should_send})
    print(json.dumps({'schema_version':SCHEMA_VERSION,'new_release':new_release,'correction':correction,'sent':should_send,'date':cur['date'],'funds':cur['funds'],'market_2026_yearend':market},ensure_ascii=False))

if __name__=='__main__':main()
