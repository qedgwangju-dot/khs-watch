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
SCHEMA_VERSION=4

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

def _condition_table(tables):
    for table in tables:
        first_cells=' | '.join((row[0] if row else '') for row in table)
        if 'Assets, liabilities, and capital' in first_cells and any(row and row[0].strip().lower()=='total assets' for row in table):
            return table
    return None

def _find_in_table(table,label,starts=False):
    if not table:return None
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

    # Use one consistent stock basis: Wednesday levels from table 5.
    cond=_condition_table(p.tables)
    total=_find_in_table(cond,'Total assets')
    tsy=_find_in_table(cond,'U.S. Treasury securities')
    bills=_find_in_table(cond,'Bills',starts=True)
    mbs=_find_in_table(cond,'Mortgage-backed securities',starts=True)
    held=_find_in_table(cond,'Securities held outright',starts=True)

    # Reserve balances appear in table 1; its final numeric column is the Wednesday level.
    reserves=find_row(p.tables,'Reserve balances with Federal Reserve Banks')
    reserve_value=None
    if reserves:
        nums=reserves.get('nums') or []
        reserve_value=nums[-1] if len(nums)>=4 else reserves.get('value')

    if not all([total,tsy,bills,mbs,held]) or reserve_value is None:
        missing=[k for k,v in {'total':total,'treasury':tsy,'bills':bills,'mbs':mbs,'reserves':reserve_value,'held':held}.items() if v is None]
        raise RuntimeError('H.4.1 파싱 실패: '+','.join(missing))

    return {
        'date':date,
        'measurement_basis':'수요일 잔액',
        'total_assets':total['value'],'total_assets_weekly':total['weekly_change'],
        'treasury':tsy['value'],'treasury_weekly':tsy['weekly_change'],
        'bills':bills['value'],'bills_weekly':bills['weekly_change'],
        'mbs':mbs['value'],'mbs_weekly':mbs['weekly_change'],
        'reserves':reserve_value,'reserves_weekly':None,
        'securities':held['value'],'securities_weekly':held['weekly_change'],
        'url':final
    }

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

def usd_level(v_mn):
    v=float(v_mn)
    if abs(v)>=1_000_000:
        return f'{v/1_000_000:,.2f}조달러'
    return f'{v/100:,.0f}억달러'

def usd_week_change(v_mn):
    if v_mn is None:return '확인 불가'
    return f'{float(v_mn)/100:+,.1f}억달러'

def bn_change(v_bn):
    return f'{float(v_bn)*10:+,.1f}억달러'

def summary_message(cur,impl,task,regime,four,reason):
    ample='충분한 준비금' in impl.get('mode','')
    lines=[
        '<b>[Warsh 연준 대차대조표 정책 변화]</b>',
        f"기준: H.4.1 {cur.get('date') or '확인 필요'} 수요일 잔액 · 시행지침 {impl.get('date') or '확인 필요'}",
        '',
        '<b>핵심 3줄</b>',
        f"• <b>공식 정책</b>: {html.escape(impl['mode'])}",
        f"• <b>실제 흐름</b>: 총자산 주간 {usd_week_change(cur['total_assets_weekly'])} · 준비금 {usd_week_change(cur['reserves_weekly'])} · 미 국채 {usd_week_change(cur['treasury_weekly'])} · MBS {usd_week_change(cur['mbs_weekly'])}",
        ('• <b>판정</b>: 현재는 <b>정책금리 인상 + 충분한 준비금 유지</b> 조합입니다. “금리 대신 QT” 또는 “강한 총량 축소”로 읽지 않습니다.'
         if ample else
         '• <b>판정</b>: 총량 축소형 양적긴축(QT)이 실제로 시작됐는지 공식 시행지침과 여러 주의 H.4.1 흐름을 함께 확인합니다.'),
        f"• <b>이번 알림 사유</b>: {html.escape(reason)}",
        '',
        '<b>현재 숫자</b>',
        f"• 연준 총자산 {usd_level(cur['total_assets'])} · 주간 {usd_week_change(cur['total_assets_weekly'])}",
        f"• 미 국채 {usd_level(cur['treasury'])} · 주간 {usd_week_change(cur['treasury_weekly'])} · 단기국채 {usd_level(cur['bills'])}",
        f"• 주택저당증권(MBS) {usd_level(cur['mbs'])} · 주간 {usd_week_change(cur['mbs_weekly'])}",
        f"• 은행 준비금 {usd_level(cur['reserves'])} · 주간 {usd_week_change(cur['reserves_weekly'])}",
    ]
    if four:
        lines += [
            f"• 최근 4주: 총자산 {bn_change(four['total_assets'])} · 준비금 {bn_change(four['reserves'])} · 보유증권 {bn_change(four['securities'])}",
        ]
    else:
        lines += [
            '• 최근 4주 판정: 동일 기준 데이터가 아직 충분히 쌓이지 않아 <b>판정 유보</b> — 주간 한 번의 변화로 QT를 단정하지 않습니다.',
        ]
    lines += [
        '',
        '',
        '<b>확정 사실과 해석 분리</b>',
        '• <b>확정 사실</b>: FOMC 시행지침의 재투자·매입 문구와 H.4.1의 <b>동일한 수요일 잔액 기준</b> 실제 수치입니다.',
        '• <b>해석</b>: QT 여부는 공식 문구 + 총자산·보유증권·준비금의 여러 주 방향이 함께 맞을 때만 강하게 판정합니다.',
        '',
        '<b>공식 시행지침</b>',
        ( '• 미 국채 원금은 전액 재투자하고, 기관채·주택저당증권 원금은 단기국채에 재투자하며, 필요하면 단기국채·잔존 3년 이하 국채를 매입해 충분한 준비금을 유지합니다.'
          if ample else
          '• 보유자산 축소·재투자 중단·상환한도 같은 총량 축소 문구가 새로 들어왔는지 확인합니다.'),
        '',
        '<b>정확히 읽는 법</b>',
        '• 총자산이 거의 줄지 않으면서 주택저당증권이 감소하고 단기국채가 늘면, 총량 축소형 QT보다 자산 구성 전환에 가깝습니다.',
        '• 실제 QT 재개는 공식 시행지침의 문구 변화와 총자산·보유증권·준비금의 여러 주 동반 감소가 함께 확인돼야 강하게 판정합니다.',
        '• 대차대조표 태스크포스의 연구·권고는 정책 결정과 구분합니다. FOMC가 채택하기 전에는 “검토” 단계입니다.',
        '',
        '<b>다음 확인</b>',
        '• H.4.1 총자산·준비금이 4주 연속 구조적으로 감소하는지',
        '• FOMC 시행지침에서 재투자 중단·상환한도·보유자산 축소 문구가 생기는지',
        '• Repo·준비금 시장에 유동성 부족 신호가 나타나는지',
        '',
        '<b>원천</b>',
        f"{link('연준 H.4.1',cur['url'])} · {link('FOMC 시행지침',impl['url'])} · {link('연준 대차대조표 태스크포스',task['url'])}",
    ]
    return '\n'.join(lines)

def main():
    old=load_state(); first=not bool(old); old_schema=old.get('schema_version',1)
    cur=h41_snapshot(); impl=latest_impl_note(); task=task_snapshot()

    # Schema 4 switches every stock variable to the same Wednesday-level basis.
    # Discard pre-v4 history so weekly/4-week comparisons never mix averages and point-in-time balances.
    history=[] if old_schema<SCHEMA_VERSION else old.get('history',[])
    prev=history[-1] if history and history[-1].get('date')!=cur.get('date') else None
    if prev:
        for key in ['total_assets','treasury','bills','mbs','reserves','securities']:
            if cur.get(key) is not None and prev.get(key) is not None:
                cur[key+'_weekly']=cur[key]-prev[key]

    regime,four=classify_h41(cur,history)
    reasons=[]
    if old.get('implementation',{}).get('url') not in (None,impl['url']):reasons.append('새 FOMC 시행지침')
    if old.get('implementation',{}).get('mode') not in (None,impl['mode']):reasons.append('대차대조표 정책문구 판정 변경')
    if old.get('task_force',{}).get('fingerprint') not in (None,task['fingerprint']):reasons.append('대차대조표 태스크포스 공식내용 변경')
    if old.get('regime') not in (None,regime) and old.get('h41',{}).get('date')!=cur.get('date'):reasons.append('H.4.1 구조 판정 변경')
    if '대차대조표 총량 축소/QT 명시'==impl['mode'] and old.get('implementation',{}).get('mode')!=impl['mode']:reasons.append('QT 명시 감지')
    if FORCE or (not first and reasons):send(summary_message(cur,impl,task,regime,four,' · '.join(dict.fromkeys(reasons)) or '강제 점검'))
    newhist=[h for h in history if h.get('date')!=cur.get('date')][-11:]+[cur]
    save_state({'schema_version':SCHEMA_VERSION,'measurement_basis':'수요일 잔액','h41':cur,'history':newhist,'regime':regime,'four_week_change_bn':four,'implementation':impl,'task_force':task})
    print(json.dumps({'first_run':first,'reasons':reasons,'h41_date':cur.get('date'),'regime':regime,'implementation_mode':impl['mode'],'implementation_date':impl.get('date')},ensure_ascii=False))

if __name__=='__main__':main()
