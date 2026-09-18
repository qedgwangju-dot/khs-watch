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

STATE_PATH = Path('data/warsh_policy_path_watch_state.json')
FOMC_STATE_PATH = Path('data/warsh_fomc_event_watch_state.json')
FEDWATCH_URL = 'https://www.frenzycap.com/fedwatch'
CME_URL = 'https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html'
FED_CALENDAR = 'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm'
TOKEN = (os.getenv('TELEGRAM_BOT_TOKEN') or '').strip()
CHAT_ID = (os.getenv('TELEGRAM_CHAT_ID') or '').strip()
EXPECTED_BOT = (os.getenv('EXPECTED_BOT_USERNAME') or 'khs8879887988798879_bot').strip().lstrip('@')
FORCE = os.getenv('FORCE_NOTIFY', '0') == '1'
PROB_ALERT_PP = float(os.getenv('WARSH_PATH_PROB_ALERT_PP') or '15')
EXTRA_ALERT_BP = float(os.getenv('WARSH_PATH_EXTRA_ALERT_BP') or '10')
UA = 'Mozilla/5.0 (compatible; khs-watch/2.1)'

MONTHS = {'Jan':1,'Feb':2,'Mar':3,'Apr':4,'May':5,'Jun':6,'Jul':7,'Aug':8,'Sep':9,'Oct':10,'Nov':11,'Dec':12}

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
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept-Language':'en-US,en;q=0.9'})
    with urllib.request.urlopen(req,timeout=30) as r:return r.read().decode('utf-8','replace'),r.geturl()

def clean_text(raw):
    raw=re.sub(r'(?is)<script.*?>.*?</script>|<style.*?>.*?</style>',' ',raw)
    raw=re.sub(r'(?s)<[^>]+>',' ',raw)
    return html.unescape(re.sub(r'\s+',' ',raw)).strip()

def parse_pct(s):
    m=re.search(r'([+-]?[\d.]+)\s*%',s)
    return float(m.group(1)) if m else None

def parse_bp(s):
    m=re.search(r'([+-]?\d+(?:\.\d+)?)\s*bp',s,re.I)
    return float(m.group(1)) if m else None

def parse_date(s):
    m=re.match(r'([A-Z][a-z]{2})\s+(\d{1,2}),\s+(20\d{2})',s)
    if not m or m.group(1) not in MONTHS:return None
    return f"{m.group(3)}-{MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}"

def probability_from_row(prob_cell, change_bp):
    nums=[float(x) for x in re.findall(r'(\d+(?:\.\d+)?)\s*%',prob_cell or '')]
    # The source probability cell is the meeting outcome distribution. When it
    # provides explicit probabilities (for example 46% / 54%), use that
    # distribution directly. Do not convert a cumulative bp move into a fake
    # "100% hike probability".
    if len(nums)>=2:
        return max(0.0,min(100.0,nums[-1]))
    if 0 <= change_bp <= 25:
        return max(0.0,min(100.0,change_bp/25*100))
    if -25 <= change_bp < 0:
        return 0.0
    if change_bp > 25:
        return 100.0
    return 0.0

def parse_snapshot():
    raw, final=fetch(FEDWATCH_URL); text=clean_text(raw)
    m=re.search(r'Current EFFR(?:\s+estimate)?\s*:\s*([\d.]+)\s*%',text,re.I)
    if m:
        effr=float(m.group(1))
    else:
        official=official_policy_baseline()
        old=load_state()
        if official:
            effr=float(official['mid'])
            print(json.dumps({'effr_parse_fallback':'official_fomc_midpoint','effr':effr},ensure_ascii=False))
        elif old.get('effr') is not None:
            effr=float(old['effr'])
            print(json.dumps({'effr_parse_fallback':'previous_state','effr':effr},ensure_ascii=False))
        else:
            raise RuntimeError('현재 유효 연방기금금리 파싱 실패')
    p=TableParser(); p.feed(raw); meetings=[]
    for table in p.tables:
        for row in table:
            if len(row)<6:continue
            d=parse_date(row[0])
            if not d:continue
            if len(row)>=7 and parse_pct(row[2]) is not None and parse_pct(row[3]) is not None and parse_pct(row[4]) is not None and parse_bp(row[5]) is not None:
                change=parse_bp(row[5]); meetings.append({
                    'date':d,'label':row[0], 'prob_cell':row[1],
                    'implied_avg':parse_pct(row[2]),'pre_rate':parse_pct(row[3]),'post_rate':parse_pct(row[4]),
                    'change_bp':change,'hike25_prob':probability_from_row(row[1],change),
                    'contract':row[6]
                })
    if not meetings:
        pat=r'([A-Z][a-z]{2}\s+\d{1,2},\s+20\d{2})\s+([\d.%\s]+?)\s+([\d.]+)%\s+([\d.]+)%\s+([\d.]+)%\s+([+-]?\d+)\s*bp\s+/?(ZQ[A-Z]\d{2})'
        for mm in re.finditer(pat,text):
            d=parse_date(mm.group(1)); change=float(mm.group(6))
            if d: meetings.append({'date':d,'label':mm.group(1),'prob_cell':mm.group(2),'implied_avg':float(mm.group(3)),
                'pre_rate':float(mm.group(4)),'post_rate':float(mm.group(5)),'change_bp':change,
                'hike25_prob':probability_from_row(mm.group(2),change),'contract':mm.group(7)})
    meetings=sorted({x['date']:x for x in meetings}.values(),key=lambda x:x['date'])
    if not meetings:raise RuntimeError('연방기금금리 선물 회의별 경로 파싱 실패')
    return {'effr':effr,'meetings':meetings[:6],'url':final}

def official_policy_baseline():
    try:
        state=json.loads(FOMC_STATE_PATH.read_text(encoding='utf-8'))
        cur=state.get('current_statement') or {}
        mid=cur.get('mid'); date=cur.get('date')
        if mid is not None and date:
            return {'mid':float(mid),'date':str(date),'source':cur.get('url'),'kind':'연준 공식 목표범위 중간값'}
    except Exception:
        pass
    return None

def classify(snap):
    ms=snap['meetings']; effr=snap['effr']
    y26=[m for m in ms if m['date'].startswith('2026-')]
    last26=y26[-1] if y26 else ms[-1]
    official=official_policy_baseline()
    if official and official['date'] <= datetime.now(timezone.utc).date().isoformat():
        base=float(official['mid'])
        extra=(last26['post_rate']-base)*100
        basis=f"{official['date']} FOMC 인상 후 공식 목표범위 중간값에서 연말까지의 누적 기대"
        base_kind=official['kind']; base_date=official['date']; base_source=official.get('source')
    else:
        base=effr
        extra=(last26['post_rate']-base)*100
        basis='선물 소스의 현재 유효 연방기금금리에서 연말까지의 누적 기대'
        base_kind='선물 소스 EFFR'; base_date=None; base_source=snap.get('url')
    if extra < 6.25: verdict='현재부터 추가 인상 종료 쪽'
    elif extra < 18.75: verdict='현재부터 추가 인상 일부 반영'
    else: verdict='현재부터 연내 추가 인상 1회 이상 반영'
    return {'verdict':verdict,'extra_bp':extra,'basis':basis,'baseline_rate':base,'baseline_kind':base_kind,'baseline_date':base_date,'baseline_source':base_source}

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
    if not TOKEN or not CHAT_ID:raise RuntimeError('Telegram 비밀값 없음')
    if botname().lower()!=EXPECTED_BOT.lower():raise RuntimeError('Telegram 봇 불일치')
    data=urllib.parse.urlencode({'chat_id':CHAT_ID,'text':msg[:4090],'parse_mode':'HTML','disable_web_page_preview':'true'}).encode()
    req=urllib.request.Request(f'https://api.telegram.org/bot{TOKEN}/sendMessage',data=data,method='POST')
    with urllib.request.urlopen(req,timeout=20) as r:
        out=json.loads(r.read().decode())
        if not out.get('ok'):raise RuntimeError('Telegram 전송 실패')

def ko_date(date_text):
    try:
        d=datetime.strptime(date_text,'%Y-%m-%d')
        return f'{d.year}년 {d.month}월 {d.day}일'
    except:return date_text

def fmt_meeting(m, baseline):
    p=m['hike25_prob']
    cumulative=(float(m['post_rate'])-float(baseline))*100
    prob=f'0.25%포인트 인상 확률 약 {p:.0f}%'
    return f"• {ko_date(m['date'])} | {prob} | 현재 공식 기준 대비 누적 기대 {cumulative:+.1f}bp | 회의 후 금리 기대 {m['post_rate']:.3f}%"

def message(snap, cls):
    lines=['<b>[Warsh 정책금리 경로 변화]</b>',
           f"공식 기준금리 중심값 {cls['baseline_rate']:.3f}% ({html.escape(cls['baseline_kind'])})",'',
           f"<b>핵심 판정: {html.escape(cls['verdict'])}</b>",
           f"• {html.escape(cls['basis'])}: {cls['extra_bp']:+.1f}bp",'', '<b>선물시장 경로</b>']
    lines += [fmt_meeting(m, cls['baseline_rate']) for m in snap['meetings'][:4]]
    lines += ['', '<b>읽는 법</b>',
              '• “확률 %”는 특정 금리결정이 일어날 가능성이고, “bp”는 그 확률을 반영한 기대 금리변화입니다. 둘은 같은 숫자가 아닙니다.',
              '• 예: 0.25%포인트 인상확률 84%라면 확률가중 기대변화는 약 +21bp입니다.',
              '• 이번 회의 한 번으로 끝나는지, 뒤 회의에서도 추가 인상이 가격에 남는지를 같이 봅니다.',
              '• 1bp = 0.01%포인트입니다.','',
              '<b>원천</b>',f"{link('연방기금금리 선물 기반 경로',snap['url'])} · {link('CME FedWatch 방법론',CME_URL)} · {link('연준 FOMC 일정',FED_CALENDAR)}"]
    return '\n'.join(lines)

def main():
    snap=parse_snapshot(); cls=classify(snap); old=load_state(); first=not bool(old)
    old_cls=old.get('classification',{}); changed=old_cls.get('verdict') not in (None,cls['verdict'])
    if not changed and old_cls.get('extra_bp') is not None:
        changed=abs(float(cls['extra_bp'])-float(old_cls['extra_bp']))>=EXTRA_ALERT_BP
    old_ms={m['date']:m for m in old.get('meetings',[])}
    if not changed and snap['meetings']:
        m=snap['meetings'][0]; om=old_ms.get(m['date'])
        if om and om.get('hike25_prob') is not None:
            changed=abs(m['hike25_prob']-float(om['hike25_prob']))>=PROB_ALERT_PP
    if FORCE or (not first and changed):send(message(snap,cls))
    save_state({'effr':snap['effr'],'meetings':snap['meetings'],'classification':cls,'source':snap['url']})
    print(json.dumps({'first_run':first,'changed':changed,'effr':snap['effr'],'classification':cls,'meetings':[{'date':m['date'],'change_bp':m['change_bp'],'hike25_prob':m['hike25_prob'],'post_rate':m['post_rate']} for m in snap['meetings'][:4]]},ensure_ascii=False))

if __name__=='__main__':main()
