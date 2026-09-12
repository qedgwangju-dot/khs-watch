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

STATE=Path('data/warsh_sep_path_watch_state.json')
PATH_STATE=Path('data/warsh_policy_path_watch_state.json')
FED_CAL='https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm'
TOKEN=(os.getenv('TELEGRAM_BOT_TOKEN') or '').strip(); CHAT=(os.getenv('TELEGRAM_CHAT_ID') or '').strip()
BOT=(os.getenv('EXPECTED_BOT_USERNAME') or 'khs8879887988798879_bot').strip().lstrip('@')
FORCE=os.getenv('FORCE_NOTIFY','0')=='1'
UA='Mozilla/5.0 (compatible; khs-watch/2.1)'

class TableParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.tables=[]; self.table=None; self.row=None; self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=='table':self.table=[]
        elif tag=='tr' and self.table is not None:self.row=[]
        elif tag in ('td','th') and self.row is not None:self.cell=[]
    def handle_data(self,data):
        if self.cell is not None:self.cell.append(data)
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split())); self.cell=None
        elif tag=='tr' and self.row is not None:
            if any(self.row):self.table.append(self.row)
            self.row=None
        elif tag=='table' and self.table is not None:
            self.tables.append(self.table); self.table=None

def fetch(url):
    q=urllib.request.Request(url,headers={'User-Agent':UA,'Accept-Language':'en-US,en;q=0.9'})
    with urllib.request.urlopen(q,timeout=30) as r:return r.read().decode('utf-8','replace'),r.geturl()

def strict_num(s):
    s=html.unescape(s).replace('\xa0',' ').strip()
    return float(s) if re.fullmatch(r'\d+(?:\.\d+)?',s) else None

def latest_sep():
    raw,_=fetch(FED_CAL); found={}
    for href,ds in re.findall(r'href=["\']([^"\']*fomcprojtabl(20\d{6})\.htm)["\']',raw,re.I):
        found[ds]=urllib.parse.urljoin(FED_CAL,href)
    if not found:raise RuntimeError('연준 경제전망·점도표 링크를 찾지 못함')
    ds,url=sorted(found.items())[-1]; page,final=fetch(url); p=TableParser(); p.feed(page)
    vals=None
    for table in p.tables:
        for row in table:
            if row and re.sub(r'\s+',' ',row[0]).strip().lower().startswith('federal funds rate'):
                nums=[]
                for c in row[1:]:
                    v=strict_num(c)
                    if v is not None:nums.append(v)
                if len(nums)>=4:
                    vals=nums[:4]; break
        if vals:break
    if not vals:raise RuntimeError('연준 점도표 중앙값 파싱 실패')
    return {'date':f'{ds[:4]}-{ds[4:6]}-{ds[6:]}','url':final,'median_2026':vals[0],'median_2027':vals[1],'median_2028':vals[2],'median_longer':vals[3]}

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
    if botname().lower()!=BOT.lower():raise RuntimeError('Telegram 봇 불일치')
    d=urllib.parse.urlencode({'chat_id':CHAT,'text':msg[:4090],'parse_mode':'HTML','disable_web_page_preview':'true'}).encode(); q=urllib.request.Request(f'https://api.telegram.org/bot{TOKEN}/sendMessage',data=d,method='POST')
    with urllib.request.urlopen(q,timeout=20) as r:
        x=json.loads(r.read().decode())
        if not x.get('ok'):raise RuntimeError('Telegram 전송 실패')

def market_dec():
    p=load(PATH_STATE,{})
    ms=[m for m in p.get('meetings',[]) if str(m.get('date','')).startswith('2026-')]
    if not ms:return None
    return sorted(ms,key=lambda x:x['date'])[-1].get('post_rate')

def verdict(sep,market):
    if market is None:return '시장 선물경로 확인 필요',None
    diff=(sep['median_2026']-float(market))*100
    if diff>=12.5:v='연준 점도표가 시장보다 더 매파적'
    elif diff<=-12.5:v='연준 점도표가 시장보다 더 비둘기파적'
    else:v='연준 점도표와 시장 연말 경로가 대체로 정렬'
    return v,diff

def msg(cur,old,market,v,diff):
    prev=old.get('snapshot',{})
    def delta(k):
        return None if prev.get(k) is None else (cur[k]-float(prev[k]))*100
    d26=delta('median_2026'); d27=delta('median_2027')
    lines=['<b>[Warsh FOMC 점도표·시장 경로 비교]</b>',f"연준 경제전망 기준일 {cur['date']}",'',
           '<b>연준 점도표 중앙값</b>',f"• 2026년 말 {cur['median_2026']:.2f}%"+(f" · 직전 전망 대비 {d26:+.0f}bp" if d26 is not None else ''),
           f"• 2027년 말 {cur['median_2027']:.2f}%"+(f" · 직전 전망 대비 {d27:+.0f}bp" if d27 is not None else ''),
           f"• 2028년 말 {cur['median_2028']:.2f}% · 장기 {cur['median_longer']:.2f}%",'']
    if market is not None:
        lines += ['<b>시장 선물경로</b>',f"• 현재 공개 선물경로의 2026년 말 유효 연방기금금리 약 {float(market):.3f}%",'']
    lines += [f"<b>판정: {html.escape(v)}</b>"]
    if diff is not None:lines.append(f"• 2026년 말 기준 연준 중앙값 - 시장 경로: {diff:+.0f}bp")
    lines += ['• 점도표는 FOMC 참가자들의 적정 정책금리 중앙값이고, 선물시장은 실제 거래가격에 반영된 기대입니다. 서로 다른 개념이므로 같은 값으로 취급하지 않습니다.',
              '• 9월 인상 뒤 한 번으로 끝나는지, 추가 인상 사이클인지 판단할 때 점도표와 시장 경로가 같은 방향으로 움직이는지를 함께 봅니다.','',
              '<b>원천</b>',f"{link('연준 경제전망·점도표',cur['url'])} · {link('연준 FOMC 일정',FED_CAL)}"]
    return '\n'.join(lines)

def main():
    cur=latest_sep(); old=load(STATE,{}); first=not bool(old); new_release=old.get('snapshot',{}).get('url') not in (None,cur['url'])
    market=market_dec(); v,diff=verdict(cur,market)
    if FORCE or (not first and new_release):send(msg(cur,old,market,v,diff))
    save({'snapshot':cur,'market_2026_yearend':market,'verdict':v,'diff_bp':diff})
    print(json.dumps({'first_run':first,'new_release':new_release,'sep':cur,'market_2026_yearend':market,'verdict':v,'diff_bp':diff},ensure_ascii=False))

if __name__=='__main__':main()
