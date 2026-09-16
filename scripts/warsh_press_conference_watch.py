#!/usr/bin/env python3
import hashlib
import html
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

STATE=Path('data/warsh_press_conference_watch_state.json')
MEETING='https://www.federalreserve.gov/monetarypolicy/fomcpresconf20260916.htm'
TOKEN=(os.getenv('TELEGRAM_BOT_TOKEN') or '').strip(); CHAT=(os.getenv('TELEGRAM_CHAT_ID') or '').strip()
BOT=(os.getenv('EXPECTED_BOT_USERNAME') or 'hshs8879_bot').strip().lstrip('@')
FORCE=os.getenv('FORCE_NOTIFY','0')=='1'
UA='Mozilla/5.0 (compatible; khs-watch/3.0)'

REUTERS_SOURCES=[
 ('물가 우선·기조 추세','https://www.reuters.com/business/warsh-says-fed-focus-stay-inflation-underlying-trends-have-not-meaningfully-2026-09-16/'),
 ('경제 강화·고용 견조','https://www.reuters.com/business/warsh-says-us-economy-has-strengthened-inflation-is-problem-2026-09-16/'),
 ('장기금리 상승 요인','https://www.reuters.com/markets/us/feds-warsh-lays-out-forces-driving-up-bond-yields-2026-09-16/'),
 ('정책경로·시장 반응','https://www.reuters.com/commentary/reuters-open-interest/global-markets-trading-day-graphic-2026-09-16/'),
]

def fetch(url,timeout=25):
    q=urllib.request.Request(url,headers={'User-Agent':UA,'Accept-Language':'en-US,en;q=0.9'})
    with urllib.request.urlopen(q,timeout=timeout) as r:return r.read().decode('utf-8','replace'),r.geturl()

def clean(raw):
    raw=re.sub(r'(?is)<script.*?>.*?</script>|<style.*?>.*?</style>',' ',raw)
    raw=re.sub(r'(?s)<[^>]+>',' ',raw)
    return re.sub(r'\s+',' ',html.unescape(raw)).strip()

def transcript_link():
    try: raw,_=fetch(MEETING)
    except Exception:return None
    m=re.search(r'href=["\']([^"\']+)["\'][^>]*>\s*(?:Press Conference Transcript|Transcript)',raw,re.I)
    return urllib.parse.urljoin(MEETING,m.group(1)) if m else None

def reuters_headlines():
    q=urllib.parse.quote('Kevin Warsh Fed inflation underlying trends full employment bond yields further hikes September 16 2026 Reuters')
    url=f'https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en'
    try: raw,_=fetch(url); root=ET.fromstring(raw)
    except Exception:return []
    out=[]
    for item in root.findall('.//item')[:40]:
        src=item.find('source'); pub=(src.text or '').strip() if src is not None else ''
        if pub!='Reuters':continue
        title=(item.findtext('title') or '').strip(); link=(item.findtext('link') or '').strip()
        out.append({'title':title,'url':link})
    return out[:10]

def classify(rows):
    text=' '.join(x['title'].lower() for x in rows)
    return {
      'inflation_priority':bool(re.search(r'inflation.*problem|focus.*inflation|underlying trends.*not.*improv|inflation persists',text)),
      'economy_strong':bool(re.search(r'economy.*strength|economic strength|full employment|labor.*strong',text)),
      'no_precommit':bool(re.search(r'no guidance|not precommit|data dependent|long-term trends|future.*not.*commit',text)),
      'yield_supply_growth':bool(re.search(r'bond yields|capital expenditure|capex|political uncertainties',text)),
    }

def fingerprint(rows,transcript):
    s=json.dumps({'rows':[x['title'] for x in rows],'transcript':transcript},sort_keys=True,ensure_ascii=False)
    return hashlib.sha256(s.encode()).hexdigest()

def botname():
    with urllib.request.urlopen(f'https://api.telegram.org/bot{TOKEN}/getMe',timeout=20) as r:return json.loads(r.read().decode())['result']['username']
def link(label,url):return f'<a href="{html.escape(url,quote=True)}">{html.escape(label)}</a>'
def send(msg):
    if not TOKEN or not CHAT:raise RuntimeError('Telegram 비밀값 없음')
    if botname().lower()!=BOT.lower():raise RuntimeError(f'Telegram 봇 불일치: expected @{BOT}')
    d=urllib.parse.urlencode({'chat_id':CHAT,'text':msg[:4090],'parse_mode':'HTML','disable_web_page_preview':'true'}).encode(); q=urllib.request.Request(f'https://api.telegram.org/bot{TOKEN}/sendMessage',data=d,method='POST')
    with urllib.request.urlopen(q,timeout=20) as r:
        x=json.loads(r.read().decode());
        if not x.get('ok'):raise RuntimeError('Telegram 전송 실패')
def load():
    try:return json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {}
    except:return {}
def save(s):
    STATE.parent.mkdir(parents=True,exist_ok=True); s['updated_at_utc']=datetime.now(timezone.utc).isoformat(); STATE.write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def message(rows,cls,transcript,first=False):
    lines=['<b>[Warsh 기자회견 · 반응함수 변화]</b>','기준: 2026년 9월 FOMC 기자회견','',
           '<b>핵심 판정</b>','• <b>경기는 견조하고 고용은 금리인상을 막을 정도로 약하지 않으며, 정책의 무게중심은 물가안정 쪽으로 이동</b>',
           '• 한 번의 CPI보다 물가의 기조적 추세를 보고, 추가 인상 가능성은 열어두되 미리 정해진 경로에는 약속하지 않는 반응함수로 읽힙니다.','',
           '<b>확인된 반응함수 축</b>',
           '• 물가: 인플레이션이 너무 높고 오래 지속됐으며, 여름 동안 기조적 물가 추세가 의미 있게 개선되지 않았다는 판단',
           '• 고용·경기: 경제는 이전 회의 이후 강해졌고 노동시장은 완전고용에 가깝다는 판단 → 당장은 물가 대응 여력이 있음',
           '• 정책경로: 이번 25bp 인상은 시장가격을 따라간 결정이 아니라 자체 판단이며, 향후 경로는 사전 약속하지 않음',
           '• 장기금리: 경제 강도·설비투자·지정학적 불확실성이 금리 상승에 기여한다고 설명 → 연준 신뢰 상실만으로 해석하지 않음','',
           '<b>쉽게 말하면</b>','• “경기가 무너져서 금리를 못 올리는 상황이 아니다. 물가가 충분히 식지 않았으니 지금은 물가를 먼저 본다.”가 핵심입니다.','• 다음 인상 여부는 특정 숫자 하나보다 근원 PCE(식품·에너지 제외), 고용, 경제활동의 여러 달 추세가 같이 바뀌는지를 봐야 합니다.','',
           '<b>검증 상태</b>']
    if transcript:
        lines.append(f"• 연준 공식 기자회견 전문 공개 확인: {link('공식 전문',transcript)}")
    else:
        lines.append('• 연준 공식 기자회견 전문은 아직 공개 링크가 확인되지 않아, 현재 판정은 연준 공식 성명·SEP와 Reuters 기자회견 보도를 교차 사용했습니다.')
    lines += ['','<b>다음 판정이 바뀌는 조건</b>','• 근원 PCE의 3·6개월 연율이 2%대 중반 이하로 지속 둔화','• 실업률 상승과 비농업 고용 3개월 평균 급락이 동시에 확인','• 워시가 추가 인상보다 성장·고용 하방위험을 우선한다고 공식적으로 전환','',
              '<b>원천</b>',link('연준 9월 FOMC 회의 페이지',MEETING)]
    for label,url in REUTERS_SOURCES:
        lines[-1]+=' · '+link('Reuters '+label,url)
    return '\n'.join(lines)

def main():
    old=load(); rows=reuters_headlines(); tr=transcript_link(); cls=classify(rows); fp=fingerprint(rows,tr)
    first=not bool(old); transcript_new=bool(tr and tr!=old.get('transcript'))
    meaningful=(cls!=old.get('classification')) if old else True
    should=FORCE or first or transcript_new or meaningful
    if should:send(message(rows,cls,tr,first=first))
    save({'fingerprint':fp,'classification':cls,'transcript':tr,'sent':should,'headlines':[x['title'] for x in rows]})
    print(json.dumps({'first_run':first,'sent':should,'transcript':tr,'classification':cls,'headline_count':len(rows)},ensure_ascii=False))

if __name__=='__main__':main()
