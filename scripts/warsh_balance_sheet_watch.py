#!/usr/bin/env python3
import hashlib
import html
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

STATE_PATH=Path('data/warsh_balance_sheet_watch_state.json')
H41_URL='https://www.federalreserve.gov/releases/h41/Current/'
TASK_URL='https://www.federalreserve.gov/monetarypolicy/balance-sheet-policy-task-force.htm'
FOMC_CAL='https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm'
TOKEN=(os.getenv('TELEGRAM_BOT_TOKEN') or '').strip(); CHAT=(os.getenv('TELEGRAM_CHAT_ID') or '').strip()
BOT=(os.getenv('EXPECTED_BOT_USERNAME') or 'khs8879887988798879_bot').strip().lstrip('@')
FORCE=os.getenv('FORCE_NOTIFY','0')=='1'
UA='Mozilla/5.0 (compatible; khs-watch/2.1)'
ASSET_4W=float(os.getenv('WARSH_BALANCE_ASSET_4W_BN') or '75')
RESERVE_4W=float(os.getenv('WARSH_BALANCE_RESERVE_4W_BN') or '100')

class TableParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.tables=[]; self.table=None; self.row=None; self.cell=None
    def handle_starttag(self, tag, attrs):
        if tag=='table': self.table=[]
        elif tag=='tr' and self.table is not None: self.row=[]
        elif tag in ('td','th') and self.row is not None: self.cell=[]
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

def clean(raw):
    raw=re.sub(r'(?is)<script.*?>.*?</script>|<style.*?>.*?</style>',' ',raw)
    raw=re.sub(r'(?i)<br\s*/?>|</p>|</li>|</h[1-6]>','\n',raw)
    raw=re.sub(r'(?s)<[^>]+>',' ',raw)
    return html.unescape(re.sub(r'\s+',' ',raw)).strip()

def number(s):
    s=s.replace(',','').replace('\xa0',' ').strip().replace('−','-').replace('–','-').replace('—','-')
    m=re.fullmatch(r'([+-]?)\s*(\d+(?:\.\d+)?)',s)
    if not m:return None
    v=float(m.group(2)); return -v if m.group(1)=='-' else v

def row_nums(row):
    out=[]
    for c in row[1:]:
        v=number(c)
        if v is not None:out.append(v)
    return out

def find_row(tables, label, starts=False):
    for table in tables:
        for row in table:
            if not row:continue
            lab=re.sub(r'\s+',' ',row[0]).strip()
            ok=lab.lower().startswith(label.lower()) if starts else lab.lower()==label.lower()
            if ok:
                nums=row_nums(row)
                if nums:return {'label':lab,'value':nums[0],'weekly_change':nums[1] if len(nums)>1 else None,'nums':nums}
    return None

def h41_snapshot():
    raw,final=fetch(H41_URL); p=TableParser(); p.feed(raw); text=clean(raw)
    d=re.search(r'Wednesday\s+([A-Z][a-z]{2})\s+(\d{1,2}),\s+(20\d{2})',text)
    date=f"{d.group(3)}-{datetime.strptime(d.group(1),'%b').month:02d}-{int(d.group(2)):02d}" if d else None
    total=find_row(p.tables,'Total assets')
    tsy=find_row(p.tables,'U.S. Treasury securities')
    bills=find_row(p.tables,'Bills',starts=True)
    mbs=find_row(p.tables,'Mortgage-backed securities',starts=True)
    reserves=find_row(p.tables,'Reserve balances with Federal Reserve Banks')
    held=find_row(p.tables,'Securities held outright',starts=True)
    if not all([total,tsy,bills,mbs,reserves,held]):
        missing=[k for k,v in {'total':total,'treasury':tsy,'bills':bills,'mbs':mbs,'reserves':reserves,'held':held}.items() if not v]
        raise RuntimeError('H.4.1 파싱 실패: '+','.join(missing))
    return {'date':date,'total_assets':total['value'],'total_assets_weekly':total['weekly_change'],
            'treasury':tsy['value'],'treasury_weekly':tsy['weekly_change'],'bills':bills['value'],'bills_weekly':bills['weekly_change'],
            'mbs':mbs['value'],'mbs_weekly':mbs['weekly_change'],'reserves':reserves['value'],'reserves_weekly':reserves['weekly_change'],
            'securities':held['value'],'securities_weekly':held['weekly_change'],'url':final}

def latest_impl_note():
    raw,_=fetch(FOMC_CAL); found={}
    for href,ds in re.findall(r'href=["\']([^"\']*/newsevents/pressreleases/monetary(\d{8})a1\.htm)["\']',raw,re.I):
        found[ds]=urllib.parse.urljoin(FOMC_CAL,href)
    if not found:return {'date':None,'url':FOMC_CAL,'fingerprint':None,'mode':'확인 필요','excerpt':''}
    ds,u=sorted(found.items())[-1]; page,final=fetch(u); t=clean(page)
    sentences=[]
    for s in re.split(r'(?<=[.!?])\s+',t):
        low=s.lower()
        if any(k in low for k in ['treasury securit','mortgage-backed','reserve balances','ample reserves','securities holdings','reinvest','principal payments','roll over','purchase']):
            if 20<=len(s)<=700:sentences.append(s)
    core=' '.join(sentences[:15]); low=core.lower()
    qt=any(re.search(p,low) for p in [r'reduc\w*.*securities holdings',r'declin\w*.*securities holdings',r'run[- ]?off',r'redemption cap',r'allow.*principal.*run off'])
    ample=any(x in low for x in ['ample reserves','purchase shorter-term treasury','roll over at auction','reinvest'])
    mode='대차대조표 총량 축소/QT 명시' if qt else ('충분한 준비금 유지·재투자/구성 전환' if ample else '정책문구 확인 필요')
    return {'date':f'{ds[:4]}-{ds[4:6]}-{ds[6:]}','url':final,'fingerprint':hashlib.sha256(core.encode()).hexdigest(),'mode':mode,'excerpt':core[:1600]}

def task_snapshot():
    raw,final=fetch(TASK_URL); t=clean(raw); parts=[]
    for s in re.split(r'(?<=[.!?])\s+',t):
        low=s.lower()
        if any(k in low for k in ['ample-reserves','ample reserves','balance sheet','alternative frameworks','composition of the fed']):
            if 20<=len(s)<=700:parts.append(s)
    core=' '.join(parts[:20])
    return {'url':final,'fingerprint':hashlib.sha256(core.encode()).hexdigest(),'excerpt':core[:1600]}

def classify_h41(cur,history):
    hist=[h for h in history if h.get('date') and h.get('date')!=cur.get('date')][-8:]+[cur]
    four=None
    if len(hist)>=5:
        base=hist[-5]
        four={k:(cur[k]-base[k])/1000 for k in ['total_assets','reserves','treasury','bills','mbs','securities']}
        if four['total_assets']<=-ASSET_4W and four['reserves']<=-RESERVE_4W and four['securities']<=-50:
            return '대차대조표 총량 축소 신호 강화',four
        if abs(four['total_assets'])<ASSET_4W and four['bills']>0 and four['mbs']<0:
            return '총량보다 자산 구성 전환 우세',four
    wa=(cur.get('total_assets_weekly') or 0)/1000; ws=(cur.get('securities_weekly') or 0)/1000; wr=(cur.get('reserves_weekly') or 0)/1000
    wb=(cur.get('bills_weekly') or 0)/1000; wm=(cur.get('mbs_weekly') or 0)/1000
    if wa<=-50 and ws<=-25 and wr<=-75:return '주간 기준 대차대조표 총량 축소 신호',four
    if abs(wa)<50 and wb>=0 and wm<=0:return '충분한 준비금 유지·자산 구성 전환에 가까움',four
    return '혼합 — 총량 축소 여부 추가 확인',four

def load_state():
    try:return json.loads(STATE_PATH.read_text(encoding='utf-8')) if STATE_PATH.exists() else {}
    except:return {}

def save_state(s):
    STATE_PATH.parent.mkdir(parents=True,exist_ok=True); s['updated_at_utc']=datetime.now(timezone.utc).isoformat()
    STATE_PATH.write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

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

def bn(v):return f'{v/1000:,.1f}십억달러'
def summary_message(cur,impl,task,regime,four,reason):
    lines=['<b>[Warsh 연준 대차대조표 정책 변화]</b>',f"변화 사유: {html.escape(reason)}",'',
           f"<b>정책문구 판정: {html.escape(impl['mode'])}</b>",f"• 최신 시행지침: {impl.get('date') or '확인 필요'}",'',
           '<b>H.4.1 현재 숫자</b>',f"• 총자산 {bn(cur['total_assets'])} · 주간 {cur['total_assets_weekly']/1000:+.1f}십억달러",
           f"• 미 국채 {bn(cur['treasury'])} · 단기국채 {bn(cur['bills'])} · 주택저당증권 {bn(cur['mbs'])}",
           f"• 은행 준비금 {bn(cur['reserves'])} · 주간 {cur['reserves_weekly']/1000:+.1f}십억달러",'',
           f"<b>시장·유동성 판정: {html.escape(regime)}</b>"]
    if four:
        lines += [f"• 최근 4주 총자산 {four['total_assets']:+.1f}십억달러 · 준비금 {four['reserves']:+.1f}십억달러 · 보유증권 {four['securities']:+.1f}십억달러"]
    lines += ['', '<b>읽는 법</b>',
              '• 현재처럼 총자산은 크게 줄지 않고 주택저당증권이 감소하는 대신 단기국채가 늘면, 강한 양적긴축보다 자산 구성 전환에 가깝습니다.',
              '• 실제 양적긴축 재개는 FOMC 시행지침에서 보유자산 축소·재투자 중단 등이 명시되거나, 총자산·보유증권·준비금이 여러 주 함께 감소하는지를 확인해 판정합니다.',
              '• 대차대조표 태스크포스 검토 자체는 정책 결정이 아니므로 공식 FOMC 문구와 구분합니다.','',
              '<b>원천</b>',f"{link('연준 H.4.1',cur['url'])} · {link('FOMC 시행지침',impl['url'])} · {link('연준 대차대조표 태스크포스',task['url'])}"]
    return '\n'.join(lines)

def main():
    old=load_state(); first=not bool(old); cur=h41_snapshot(); impl=latest_impl_note(); task=task_snapshot()
    history=old.get('history',[]); regime,four=classify_h41(cur,history)
    reasons=[]
    if old.get('implementation',{}).get('url') not in (None,impl['url']):reasons.append('새 FOMC 시행지침')
    if old.get('implementation',{}).get('mode') not in (None,impl['mode']):reasons.append('대차대조표 정책문구 판정 변경')
    if old.get('task_force',{}).get('fingerprint') not in (None,task['fingerprint']):reasons.append('대차대조표 태스크포스 공식내용 변경')
    if old.get('regime') not in (None,regime) and old.get('h41',{}).get('date')!=cur.get('date'):reasons.append('H.4.1 구조 판정 변경')
    if '대차대조표 총량 축소/QT 명시'==impl['mode'] and old.get('implementation',{}).get('mode')!=impl['mode']:reasons.append('QT 명시 감지')
    if FORCE or (not first and reasons):send(summary_message(cur,impl,task,regime,four,' · '.join(dict.fromkeys(reasons)) or '강제 점검'))
    newhist=[h for h in history if h.get('date')!=cur.get('date')][-11:]+[cur]
    save_state({'h41':cur,'history':newhist,'regime':regime,'four_week_change_bn':four,'implementation':impl,'task_force':task})
    print(json.dumps({'first_run':first,'reasons':reasons,'h41_date':cur.get('date'),'regime':regime,'implementation_mode':impl['mode'],'implementation_date':impl.get('date')},ensure_ascii=False))

if __name__=='__main__':main()
