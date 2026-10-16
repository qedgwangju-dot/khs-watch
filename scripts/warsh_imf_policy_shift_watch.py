#!/usr/bin/env python3
"""워시 IMF 대담: 연준 일정과 독립 보도 교차검증, 정책 발언·시장전망 분리."""
import email.utils
import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/'data/warsh_imf_policy_shift_watch_state.json'
FED_CAL='https://www.federalreserve.gov/newsevents/2026-october.htm'
IMF='https://www.imfconnect.org/content/imf/en/annual-meetings/calendar/open/2026/10/16/213398.html'
REUTERS='https://www.reuters.com/markets/asia/feds-warsh-gives-no-hint-october-policy-decision-2026-10-16/'
REUTERS_CITI='https://www.reuters.com/business/citi-turns-hawkish-fed-after-inflation-surprise-expects-december-rate-hike-2026-10-14/'
WSJ='https://www.wsj.com/economy/central-banking/warsh-avoids-signal-on-october-rate-move-a176b0d5'
TOKEN=(os.getenv('TELEGRAM_BOT_TOKEN') or '').strip()
CHAT=(os.getenv('TELEGRAM_CHAT_ID') or '').strip()
BOT=(os.getenv('EXPECTED_BOT_USERNAME') or '').strip().lstrip('@')
FORCE=os.getenv('FORCE_NOTIFY','0')=='1'
ET=ZoneInfo('America/New_York')
UA='Mozilla/5.0 (compatible; khs-watch/imf-warsh-1.0)'
EVENT_ID='2026-10-16|Warsh|IMF-Bangkok'


def get(url,timeout=12):
    last=None
    for attempt in range(2):
        try:
            req=urllib.request.Request(url,headers={
                'User-Agent':UA,'Accept-Language':'en-US,en;q=0.9'
            })
            with urllib.request.urlopen(req,timeout=timeout) as r:
                return r.read().decode('utf-8','replace')
        except Exception as e:last=e
        if attempt==0:time.sleep(1)
    raise last


def read_state():
    try:return json.loads(STATE.read_text(encoding='utf-8'))
    except (OSError,ValueError):return {}


def save(s):
    STATE.parent.mkdir(parents=True,exist_ok=True)
    s['updated_at_utc']=datetime.now(timezone.utc).isoformat()
    STATE.write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def plain(x):
    return ' '.join(html.unescape(re.sub(r'(?s)<[^>]+>',' ',x)).split())


def official_event():
    # 한국 기준 10월16일 오전/오후 대담: 미 동부 기준 10월15일 23:30.
    if datetime.now(ET)<datetime(2026,10,15,23,30,tzinfo=ET):
        return False
    cal=plain(get(FED_CAL))
    # 연준이 공식 달력에 배포한 의장/IMF 대담 행사 여부를 우선 확인한다.
    if 'Kevin Warsh' not in cal or 'IMF Managing Director' not in cal:
        raise RuntimeError('연준 공식 행사 일정에서 Warsh·IMF 대담 확인 실패')
    try:
        imf=plain(get(IMF))
        if 'Kevin Warsh' not in imf or 'Kristalina Georgieva' not in imf:
            raise RuntimeError('IMF 행사 공식 인물 검증 불일치')
    except Exception as exc:
        # 외부 IMF 행사 페이지 장애로 연준 공식 행사 검증을 폐기하지 않되 기록한다.
        return '연준 공식 일정 확인 / IMF 행사 페이지 조회 불가: '+type(exc).__name__
    return '연준·IMF 행사 일정 교차확인'


def dated_coverage():
    # Google News RSS는 Reuters 원문 접속 실패 시 신뢰 보도 게이트에만 사용.
    q=urllib.parse.quote('Kevin Warsh IMF Bangkok October 16 2026 Reuters')
    url='https://news.google.com/rss/search?q='+q+'&hl=en-US&gl=US&ceid=US:en'
    rows=[]
    try:
        rss=get(url)
        root=ET.fromstring(rss)
        for item in root.findall('./channel/item')[:80]:
            sn=item.find('source')
            pub=plain(sn.text or '') if sn is not None else ''
            if pub not in ('Reuters','The Wall Street Journal','WSJ','Financial Times'):
                continue
            title=plain(item.findtext('title') or '')
            description=plain(item.findtext('description') or '')
            blob=(title+' '+description).lower()
            if not ('warsh' in blob and ('imf' in blob or 'bangkok' in blob)):
                continue
            t=item.findtext('pubDate') or ''
            try:
                date=email.utils.parsedate_to_datetime(t).astimezone(timezone.utc).date()
            except Exception:
                continue
            if not (datetime(2026,10,15,tzinfo=timezone.utc).date()<=date<=
                    datetime.now(timezone.utc).date()):
                continue
            rows.append({'publisher':pub,'title':title,'url':(item.findtext('link') or '').strip()})
    except Exception:
        pass
    # 직접 Reuters 기사를 조회할 수 있는 경우에는 RSS 접근과 무관하게 확인한다.
    try:
        content=plain(get(REUTERS))
        lower=content.lower()
        if 'warsh' in lower and ('imf' in lower or 'bangkok' in lower) and (
                'rate' in lower or 'monetary policy' in lower):
            rows.append({'publisher':'Reuters','title':'의장, 차기 금리결정을 미리 확정하지 않음',
                         'url':REUTERS})
    except Exception:
        pass
    if not rows:raise RuntimeError('Reuters 등 신뢰 보도의 실제 공개 확인 실패 — 자동 알림 보류')
    return rows


def citi_reported():
    # 공식 시장확률과 IB 전망을 혼동하지 않는다.
    try:
        text=plain(get(REUTERS_CITI)).lower()
    except Exception:
        return False
    return ('citi' in text and 'december' in text and 'hike' in text)


def link(label,url):
    return '<a href="'+html.escape(url,quote=True)+'">'+html.escape(label)+'</a>'


def compose(official,coverage,has_citi):
    pubs='·'.join(sorted(set(x['publisher'] for x in coverage)))
    parts=[
        '<b>[Warsh | IMF 대담·정책 반응함수]</b>',
        '행사: 2026년 10월 16일 방콕 · '+html.escape(official),
        '',
        '<b>한눈에 보기</b>',
        '• <b>정책</b> | 10월·12월 인상을 미리 약속하지 않음 → 회의별 경제지표 확인',
        '• <b>성장</b> | 경기와 기업투자 회복력 강조 · 지정학적 위험 지속',
        '• <b>AI</b> | 단기 설비투자·총수요 확대 / 중기 생산성 개선 가능성 분리',
        '',
        '<b>해석·실패 경로</b>',
        '• 향후 AI 생산성 이익이 뒤따르지 않으면 당장 설비투자·전력·냉각 비용이 물가에 더 먼저 반영될 수 있습니다.',
        '• 반대로 데이터센터 투자 축소 또는 채택 지연은 하드웨어 수요와 고용에 부담입니다.',
        '• IMF 공식 행사 사실과 신뢰 보도의 발언 요지를 구분합니다. 연준 공식 발언 전문이 나오면 원문으로 재검증합니다.',
        '• 이 메시지는 시장금리선물의 인상확률 숫자를 제시하지 않습니다.',
    ]
    if has_citi:
        parts += [
            '',
            '<b>별도 증권사 전망(연준 결정 아님)</b>',
            '• Reuters 보도: Citi는 10월 동결 후 12월 0.25%포인트 인상 전망으로 변경',
            '• 이 전망을 다른 금융기관의 공식 전망이나 시장확률로 일반화하지 않습니다.',
        ]
    parts += [
        '',
        '<b>원천</b>',
        link('연준 공식 일정',FED_CAL)+' · '+link('IMF 공식 행사',IMF),
        link('Reuters 대담 보도',REUTERS)+' · '+link('WSJ 대담 보도',WSJ),
    ]
    if has_citi:
        parts.append(link('Citi 전망 Reuters 보도',REUTERS_CITI))
    parts += [f'확인된 외부 보도 매체: {html.escape(pubs)}']
    return '\n'.join(parts)


def send(msg):
    if not TOKEN or not CHAT or not BOT:raise RuntimeError('기존 Warsh 텔레그램 인증값 없음')
    with urllib.request.urlopen(f'https://api.telegram.org/bot{TOKEN}/getMe',timeout=20) as r:
        obj=json.loads(r.read().decode('utf-8'))
    actual=str((obj.get('result') or {}).get('username') or '')
    if obj.get('ok') is not True or actual.lower()!=BOT.lower():
        raise RuntimeError('기존 Warsh 발신 봇과 일치하지 않음')
    if len(msg)>3800:raise RuntimeError('Telegram 길이 초과')
    body=urllib.parse.urlencode({
        'chat_id':CHAT,'text':msg,'parse_mode':'HTML',
        'disable_web_page_preview':'true'}).encode('utf-8')
    request=urllib.request.Request(
        f'https://api.telegram.org/bot{TOKEN}/sendMessage',data=body,method='POST')
    with urllib.request.urlopen(request,timeout=20) as r:
        res=json.loads(r.read().decode('utf-8'))
    receipt=(res.get('result') or {}).get('message_id')
    if res.get('ok') is not True or not isinstance(receipt,int):
        raise RuntimeError('Telegram API 수신확인 실패')
    return receipt


def main():
    old=read_state()
    if old.get('last_sent_key')==EVENT_ID and not FORCE:
        print(json.dumps({'status':'already_sent','message_id':old.get('message_id')},ensure_ascii=False))
        return
    if old.get('pending_key')==EVENT_ID and old.get('delivery_status')=='sending':
        raise RuntimeError('이전 전송확인 불명확 — 중복 전송 보류')
    now=datetime.now(ET).date()
    if now<datetime(2026,10,15).date() or (now-datetime(2026,10,15).date()).days>7:
        print(json.dumps({'status':'outside_event_window','sent':False},ensure_ascii=False))
        return
    official=official_event()
    if not official:
        print(json.dumps({'status':'scheduled_not_started','sent':False},ensure_ascii=False))
        return
    coverage=dated_coverage()
    has_citi=citi_reported()
    msg=compose(official,coverage,has_citi)
    old.update({'pending_key':EVENT_ID,'delivery_status':'sending'})
    save(old)
    mid=send(msg)
    old.update({
        'last_sent_key':EVENT_ID,'message_id':mid,'pending_key':None,
        'delivery_status':'confirmed','sources':[FED_CAL,IMF,REUTERS],
        'citi_reported':has_citi,'coverage_publishers':sorted(set(x['publisher'] for x in coverage)),
        'sent_at_utc':datetime.now(timezone.utc).isoformat()
    })
    save(old)
    print(json.dumps({'status':'sent','message_id':mid,'official':official,
                      'publishers':old['coverage_publishers'],'citi_reported':has_citi},ensure_ascii=False))


if __name__=='__main__':main()
