#!/usr/bin/env python3
import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

STATE_PATH = Path('data/warsh_policy_path_watch_state.json')
FOMC_STATE_PATH = Path('data/warsh_fomc_event_watch_state.json')
SEP_STATE_PATH = Path('data/warsh_sep_path_watch_state.json')
BALANCE_STATE_PATH = Path('data/warsh_balance_sheet_watch_state.json')
SCHEMA_VERSION = 4
FEDWATCH_URL = 'https://www.frenzycap.com/fedwatch'
CME_URL = 'https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html'
FED_CALENDAR = 'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm'
TOKEN = (os.getenv('TELEGRAM_BOT_TOKEN') or '').strip()
CHAT_ID = (os.getenv('TELEGRAM_CHAT_ID') or '').strip()
EXPECTED_BOT = (os.getenv('EXPECTED_BOT_USERNAME') or 'khs8879887988798879_bot').strip().lstrip('@')
FORCE = os.getenv('FORCE_NOTIFY', '0') == '1'
PROB_ALERT_PP = float(os.getenv('WARSH_PATH_PROB_ALERT_PP') or '15')
EXTRA_ALERT_BP = float(os.getenv('WARSH_PATH_EXTRA_ALERT_BP') or '10')
MARKET_SEP_GAP_ALERT_BP = float(os.getenv('WARSH_PATH_MARKET_SEP_GAP_BP') or '10')
UA = 'Mozilla/5.0 (compatible; khs-watch/3.0)'

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
    last=None
    for attempt in range(3):
        try:
            req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept-Language':'en-US,en;q=0.9'})
            with urllib.request.urlopen(req,timeout=30) as r:return r.read().decode('utf-8','replace'),r.geturl()
        except Exception as e:
            last=e
            if attempt<2:time.sleep(2*(attempt+1))
    raise last

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
    m=re.search(r'Current EFFR:\s*([\d.]+)%',text,re.I)
    if not m:raise RuntimeError('현재 유효 연방기금금리 파싱 실패')
    effr=float(m.group(1)); p=TableParser(); p.feed(raw); meetings=[]
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

def load_json(path):
    try:return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    except:return {}

def official_sep_baseline():
    state=load_json(SEP_STATE_PATH); snap=state.get('snapshot') or {}
    funds=snap.get('funds') or []
    if len(funds)>=2 and funds[0] is not None and funds[1] is not None:
        return {'date':snap.get('date'),'yearend':float(funds[0]),'nextyear':float(funds[1]),'url':snap.get('url')}
    return None

def balance_sheet_baseline():
    state=load_json(BALANCE_STATE_PATH); impl=state.get('implementation') or {}
    if not state:return None
    return {'mode':impl.get('mode') or '확인 필요','regime':state.get('regime') or '확인 필요',
            'date':impl.get('date'),'url':impl.get('url'),'h41_url':(state.get('h41') or {}).get('url')}

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
    if extra < 6.25: verdict='이번 인상 후 종료 쪽'
    elif extra < 31.25: verdict='추가 1회 인상 가능성 반영'
    else: verdict='추가 1회는 상당히 반영·두 번째 인상 가능성도 일부 반영'
    sep=official_sep_baseline(); bal=balance_sheet_baseline()
    sep_extra=None; market_sep_gap=None; sep_read='점도표 확인 불가'
    if sep:
        sep_extra=(sep['yearend']-base)*100
        market_sep_gap=(last26['post_rate']-sep['yearend'])*100
        if market_sep_gap >= MARKET_SEP_GAP_ALERT_BP: sep_read='시장이 연준 점도표보다 더 매파적'
        elif market_sep_gap <= -MARKET_SEP_GAP_ALERT_BP: sep_read='시장이 연준 점도표보다 덜 매파적'
        else: sep_read='시장과 연준 점도표가 대체로 비슷한 경로'
    mix='대차대조표 확인 필요'
    if bal:
        if 'QT' in bal['mode'] or '총량 축소' in bal['mode'] or '총량 축소' in bal['regime']:
            mix='정책금리 + 대차대조표 이중긴축 신호'
        elif '충분한 준비금' in bal['mode'] or '구성 전환' in bal['regime']:
            mix='정책금리 중심 긴축 · 대차대조표는 충분한 준비금 유지/자산 구성 전환'
        else:
            mix='정책금리 긴축 · 대차대조표 방향 추가 확인'
    return {'verdict':verdict,'extra_bp':extra,'basis':basis,'baseline_rate':base,'baseline_kind':base_kind,
            'baseline_date':base_date,'baseline_source':base_source,'sep':sep,'sep_extra_bp':sep_extra,
            'market_sep_gap_bp':market_sep_gap,'sep_read':sep_read,'balance':bal,'tightening_mix':mix,
            'yearend_market_rate':last26['post_rate']}

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

def hike_equivalent(bp):
    return float(bp)/25.0

def easy_extra_read(bp):
    h=hike_equivalent(bp)
    if h < 0.25:
        return '추가 인상을 거의 가격에 넣지 않은 수준'
    if h < 0.75:
        return '추가 1회 인상 가능성을 일부만 가격에 넣은 수준'
    if h < 1.25:
        return '추가 1회 인상을 대체로 가격에 넣은 수준'
    if h < 1.75:
        return '추가 1회는 상당히 반영하고, 두 번째 인상 가능성도 일부 반영한 수준'
    return '추가 2회 인상을 거의 가격에 넣은 수준'

def fmt_meeting(m, baseline):
    p=float(m['hike25_prob'])
    expected=float(m.get('change_bp') or 0.0)
    cumulative=(float(m['post_rate'])-float(baseline))*100
    return (
        f"• {ko_date(m['date'])} | +0.25%p 인상 확률 {p:.0f}% | "
        f"해당 회의 기대변화 {expected:+.1f}bp | 회의 후 금리 기대 {m['post_rate']:.3f}%\n"
        f"  ↳ 현재 공식 기준 대비 누적 기대 {cumulative:+.1f}bp"
    )

def message(snap, cls):
    eq=hike_equivalent(cls['extra_bp'])
    sep=cls.get('sep')
    bal=cls.get('balance')
    lines=[
        '<b>[Warsh 금리경로·대차대조표 종합]</b>',
        f"기준금리 중심값 {cls['baseline_rate']:.3f}% · {html.escape(cls['baseline_kind'])}",
        '',
        '<b>한눈에 보기</b>',
        f"• <b>시장 금리경로</b>: {html.escape(cls['verdict'])}",
        f"• <b>연말 누적 기대</b>: {cls['extra_bp']:+.1f}bp = +25bp 인상 {eq:.2f}회 상당 <i>(확률가중 평균)</i>",
        f"• <b>대차대조표</b>: {html.escape(cls['tightening_mix'])}",
    ]
    if sep:
        lines += [
            f"• <b>연준 점도표</b>: 2026년 말 {sep['yearend']:.3f}% · 2027년 말 {sep['nextyear']:.3f}%",
            f"• <b>시장 vs 연준</b>: 시장 연말 {cls['yearend_market_rate']:.3f}% · 점도표보다 {cls['market_sep_gap_bp']:+.1f}bp → {html.escape(cls['sep_read'])}",
        ]
    if cls.get('market_source_stale'):
        lines += ['', '⚠️ 선물시장 원천이 일시적으로 응답하지 않아 아래 값은 <b>직전 정상 조회값</b>입니다. 새 시장값으로 단정하지 않습니다.']

    lines += [
        '',
        '<b>회의별 선물시장 경로</b>',
        *[fmt_meeting(m, cls['baseline_rate']) for m in snap['meetings'][:4]],
    ]

    if sep:
        lines += [
            '',
            '<b>연준 점도표와 비교</b>',
            f"• 현재 공식 기준 대비 2026년 말 점도표: {cls['sep_extra_bp']:+.1f}bp = +25bp 인상 {hike_equivalent(cls['sep_extra_bp']):.2f}회 상당",
            f"• 시장 연말 기대: {cls['yearend_market_rate']:.3f}% · 연준 중앙값 {sep['yearend']:.3f}% · 차이 {cls['market_sep_gap_bp']:+.1f}bp",
            '• 점도표는 FOMC의 약속이 아니라 각 참가자가 적절하다고 보는 연말 정책금리의 중앙값입니다.',
        ]

    if bal:
        official_combo = (
            '현재 공식 조합은 <b>정책금리 인상 + 충분한 준비금 유지·자산 구성 전환</b>입니다. “금리 대신 QT”가 아닙니다.'
            if '충분한 준비금' in bal.get('mode','')
            else '대차대조표 총량 축소형 양적긴축(QT)이 실제로 추가됐는지 공식 시행지침과 H.4.1을 따로 확인합니다.'
        )
        lines += [
            '',
            '<b>대차대조표 확인</b>',
            f"• 시행지침: {html.escape(bal['mode'])}",
            f"• H.4.1 구조: {html.escape(bal['regime'])}",
            f"• {official_combo}",
        ]

    lines += [
        '',
        '<b>숫자 읽는 법</b>',
        '• <b>확률 %</b> = 특정 회의에서 +25bp 인상이 일어날 가능성입니다.',
        '• <b>기대변화 bp</b> = 여러 가능한 결과에 확률을 곱해 평균낸 시장 기대입니다. 확률과 인상폭을 같은 숫자로 읽지 않습니다.',
        '• 예를 들어 +25bp 인상 확률이 80%라면 그 한 회의의 확률가중 기대폭은 약 +20bp입니다.',
        '• “1.38회 상당” 같은 값은 실제로 1.38번 인상한다는 뜻이 아니라 0회·1회·2회 경로를 확률로 섞은 평균입니다.',
        '• 1bp = 0.01%포인트입니다.',
        '',
        '<b>다음 확인</b>',
        '• 첫 회의 인상 확률뿐 아니라 12월·2027년 경로가 함께 올라가는지',
        '• 2년물이 추가 긴축 기대를 계속 유지하는지',
        '• 대차대조표가 충분한 준비금 유지에서 실제 총량 축소형 QT로 바뀌는지',
        '',
        '<b>원천</b>',
    ]
    source_bits=[link('연방기금금리 선물 기반 경로',snap['url']),link('CME FedWatch 방법론',CME_URL),link('연준 FOMC 일정',FED_CALENDAR)]
    if sep and sep.get('url'):source_bits.append(link('연준 경제전망·점도표',sep['url']))
    if bal and bal.get('url'):source_bits.append(link('연준 FOMC 시행지침',bal['url']))
    if bal and bal.get('h41_url'):source_bits.append(link('연준 H.4.1',bal['h41_url']))
    lines.append(' · '.join(source_bits))
    return '\n'.join(lines)

def main():
    old=load_state(); first=not bool(old); source_error=None; stale_fallback=False
    try:
        snap=parse_snapshot()
    except Exception as e:
        source_error=str(e); stale_fallback=True
        if not old.get('meetings'):
            raise
        snap={'effr':old.get('effr'),'meetings':old.get('meetings') or [],'url':old.get('source') or FEDWATCH_URL}
        if not snap['meetings']:
            raise
    cls=classify(snap)
    cls['market_source_stale']=stale_fallback
    cls['market_source_error']=source_error
    upgrade=old.get('schema_version',1)<SCHEMA_VERSION
    old_cls=old.get('classification',{}); changed=old_cls.get('verdict') not in (None,cls['verdict'])
    if not changed and old_cls.get('extra_bp') is not None:
        changed=abs(float(cls['extra_bp'])-float(old_cls['extra_bp']))>=EXTRA_ALERT_BP
    old_ms={m['date']:m for m in old.get('meetings',[])}
    if not changed and snap['meetings']:
        m=snap['meetings'][0]; om=old_ms.get(m['date'])
        if om and om.get('hike25_prob') is not None:
            changed=abs(m['hike25_prob']-float(om['hike25_prob']))>=PROB_ALERT_PP
    if not changed and cls.get('market_sep_gap_bp') is not None and old_cls.get('market_sep_gap_bp') is not None:
        changed=abs(float(cls['market_sep_gap_bp'])-float(old_cls['market_sep_gap_bp']))>=MARKET_SEP_GAP_ALERT_BP
    if not changed and old_cls.get('tightening_mix') not in (None,cls.get('tightening_mix')):
        changed=True
    if stale_fallback and not upgrade and not changed and not FORCE:
        print(json.dumps({'schema_version':SCHEMA_VERSION,'first_run':first,'stale_fallback':True,'source_error':source_error,
                          'message':'선물시장 원천 일시 오류 — 직전 정상 상태 보존, 신규 시장 판정 발송 안 함'},ensure_ascii=False))
        return
    if FORCE or (not first and changed):send(message(snap,cls))
    save_state({'schema_version':SCHEMA_VERSION,'effr':snap['effr'],'meetings':snap['meetings'],'classification':cls,'source':snap['url'],
                'source_status':'직전 정상값 사용' if stale_fallback else '실시간 조회','source_error':source_error})
    print(json.dumps({'schema_version':SCHEMA_VERSION,'upgrade':upgrade,'first_run':first,'changed':changed,'stale_fallback':stale_fallback,
                      'source_error':source_error,'effr':snap['effr'],'classification':cls,
                      'meetings':[{'date':m['date'],'change_bp':m['change_bp'],'hike25_prob':m['hike25_prob'],'post_rate':m['post_rate']} for m in snap['meetings'][:4]]},ensure_ascii=False))

if __name__=='__main__':main()
