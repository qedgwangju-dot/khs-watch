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
# Reuters 기사가 차단된 환경에서는 Reuters 저작권 표기·동일 행사와
# 발표일을 확인한 정식 재공표 페이지를 2차 접근경로로 쓴다.
REUTERS_MIRRORS=[
    'https://www.investing.com/news/economy-news/feds-warsh-gives-no-hint-on-october-policy-decision-4953046',
    'https://finance.yahoo.com/economy/policy/articles/feds-warsh-gives-no-hint-040051405.html',
    'https://kfgo.com/2026/10/15/feds-warsh-gives-no-hint-on-october-policy-decision/',
]
CITI_REUTERS_MIRRORS=[
    'https://www.investing.com/news/economy-news/citi-turns-hawkish-on-fed-after-inflation-surprise-expects-december-rate-hike-4949657',
    'https://www.kitco.com/news/off-the-wire/2026-10-14/citi-turns-hawkish-fed-after-inflation-surprise-expects-december-rate',
    'https://www.marketscreener.com/news/citi-turns-hawkish-on-fed-after-inflation-surprise-expects-december-rate-hike-ce785dd2de8af72c',
]
TOKEN=(os.getenv('TELEGRAM_BOT_TOKEN') or '').strip()
CHAT=(os.getenv('TELEGRAM_CHAT_ID') or '').strip()
BOT=(os.getenv('EXPECTED_BOT_USERNAME') or '').strip().lstrip('@')
FORCE=os.getenv('FORCE_NOTIFY','0')=='1'
ET=ZoneInfo('America/New_York')
UA='Mozilla/5.0 (compatible; khs-watch/imf-warsh-1.0)'
EVENT_ID='2026-10-16|Warsh|IMF-Bangkok'
AI_POLICY_KEY='2026-10-16|Warsh|AI-Data-Policy-Verified'
FED_TASKFORCES='https://www.federalreserve.gov/monetarypolicy/task-forces.htm'
AFP_RTHK='https://news.rthk.hk/rthk/en/component/k2/1874182-20261016.htm'


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


def _reuters_article_proof(text):
    """검증한 Reuters 기사·대담·날짜를 모두 식별해야만 보도 확인."""
    low=plain(text).lower()
    return (
        'reuters' in low
        and 'warsh' in low
        and ('imf' in low or 'bangkok' in low)
        and ('rate' in low or 'monetary policy' in low)
        and ('oct 16' in low or 'october 16' in low or '2026-10-16' in low)
    )


def dated_coverage():
    # 직접 Reuters 원문이 차단된 GitHub runner에 대응해 검증된 Reuters 재공표를 조회한다.
    # 동일 원기사는 재공표 매체가 여럿이어도 '독립 보도 다수'로 계산하지 않는다.
    rows=[]
    try:
        if _reuters_article_proof(get(REUTERS,timeout=8)):
            rows.append({'publisher':'Reuters','title':'Warsh IMF Bangkok',
                         'url':REUTERS})
    except Exception:
        pass

    if not rows:
        for url in REUTERS_MIRRORS:
            try:
                raw=get(url,timeout=7)
                if _reuters_article_proof(raw):
                    rows.append({'publisher':'Reuters(재공표)','title':'Warsh IMF Bangkok',
                                 'url':url})
                    break
            except Exception:
                continue

    if not rows:
        # 단순 검색결과 제목, 사용자 제공 요약, 출처 없는 복제 기사는 인증하지 않는다.
        raise RuntimeError('신뢰 보도 Reuters 원문·재공표 모두 검증 실패 — 알림 보류')
    return rows

def ai_policy_sources():
    """기존 대담에서 빠진 데이터·정책 축을 독립 보도와 연준 공식 과제로 검증."""
    official=plain(get(FED_TASKFORCES, timeout=8)).lower()
    if not all(x in official for x in (
        'data', 'productivity and jobs', 'artificial intelligence',
        'federal reserve'
    )):
        raise RuntimeError('연준 공식 데이터·생산성 태스크포스 범위 검증 실패')
    report=plain(get(AFP_RTHK, timeout=8)).lower()
    # Reuters 재공표 중복은 독립 근거로 세지 않는다. RTHK의 AFP 보도를 활용.
    if not all(x in report for x in (
        'warsh', '2026-10-16', 'imf', 'monetary policy', 'ai',
        'data', 'supply'
    )):
        raise RuntimeError('AFP 대담 보도·발언 범위 검증 실패')
    return {'federal':FED_TASKFORCES,'press':AFP_RTHK}


def ai_policy_followup_message(sources):
    return '\n'.join([
        '<b>[Warsh | AI·통화정책 데이터 변화]</b>',
        '2026년 10월 16일 IMF 대담 · 이미 발송한 행사 요약의 추가 검증 내용',
        '',
        '<b>핵심 신규 변화</b>',
        '• <b>데이터·정책</b>: AI를 물가·경제지표 분석과 정책 판단에 활용할 가능성 제시. 실제 정책 운영의 변경·도입 확정은 아님',
        '• <b>효과의 시차</b>: 단기 AI 설비투자·총수요 확대 ↔ 중기 생산성 향상·공급능력 확대',
        '• <b>미확정 위험</b>: 직무·고용 영향, AI 기업의 수익배분과 시장구조, 금융안정 부담은 추가 검증 대상',
        '• <b>금리</b>: 10월·12월 결정은 미리 약속하지 않음. AI 낙관론을 금리인하·인상 확정으로 해석하지 않음',
        '',
        '<b>앞으로 확인할 공식 지표</b>',
        '• 연준 데이터·생산성/고용 태스크포스 결과의 실제 공개 여부와 시행 단계',
        '• 근원 PCE 3·6개월 연율, 고용·단위노동비용, AI 설비투자 대비 현금창출·자금조달 부담',
        '',
        '<b>근거 구분</b>',
        '• IMF 발언은 AFP 보도 내용이며, 태스크포스 존재·목표는 연준 공식자료로 별도 확인했습니다.',
        '• 새로운 FOMC 의결·시장 인상확률·연준의 확정 투자계약은 발표된 사실이 아닙니다.',
        '',
        '<b>원천</b>',
        link('IMF 공식 행사',IMF)+' · '+link('AFP 대담 보도',sources['press']),
        link('연준 공식 태스크포스',sources['federal'])
    ])


def citi_reported():
    # 공식 시장확률과 IB 전망을 혼동하지 않는다. Reuters 원문 또는 Reuters 저작권
    # 표시가 있는 재공표에서 확인한 단일 보도이며 Citi 공식 전망으로 단정하지 않는다.
    for url in [REUTERS_CITI]+CITI_REUTERS_MIRRORS:
        try:
            text=plain(get(url,timeout=7)).lower()
            if ('reuters' in text and ('citi' in text or 'citigroup' in text)
                    and 'december' in text and 'hike' in text and
                    ('oct 14' in text or 'october 14' in text or '2026-10-14' in text
                     or '10/14/2026' in text)):
                return url
        except Exception:
            continue
    return None


def citi_followup_message(url):
    return '\n'.join([
        '<b>[Warsh | Citi 12월 인상 전망 변경]</b>',
        'Reuters 2026년 10월 14일 보도 · 금융기관 전망',
        '',
        '• <b>이전</b>: 2026년 추가 금리인상 0회 전망',
        '• <b>변경</b>: 10월 동결 후 12월 0.25%포인트 인상 전망',
        '• <b>2027년</b>: 6월부터 금리인하 가능성 전망',
        '• 이는 Citi 전망에 관한 단일 Reuters 보도입니다. 연준 결정이나 확인된 CME 시장확률이 아닙니다.',
        '',
        link('Reuters 원문·재공표 확인 경로',url),
    ])


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
        link('Reuters 대담 보도(실제 확인 경로)',coverage[0]['url'])
            +' · '+link('연준 행사 일정',FED_CAL),
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
        # 원 행사 알림의 중복은 차단하되, 사후 독립 검증된 Citi 전망은 별도 1회 보충.
        event_age=(datetime.now(ET).date()-datetime(2026,10,15).date()).days
        if not old.get('citi_reported') and 0 <= event_age <= 7:
            citi_key='2026-10-14|Citi|December-25bp'
            if old.get('citi_pending_key')==citi_key and old.get('citi_delivery_status')=='sending':
                raise RuntimeError('Citi 후속 알림 전송 결과 불명확 — 중복 발송 중단')
            citi_url=citi_reported()
            if citi_url:
                old.update({'citi_pending_key':citi_key,'citi_delivery_status':'sending'})
                save(old)
                mid=send(citi_followup_message(citi_url))
                old.update({
                    'citi_reported':True,'citi_source':citi_url,'citi_message_id':mid,
                    'citi_sent_key':citi_key,'citi_pending_key':None,
                    'citi_delivery_status':'confirmed',
                })
                save(old)
                print(json.dumps({'status':'citi_followup_sent','message_id':mid,
                                  'citi_source':citi_url,'imf_message_id':old.get('message_id')},ensure_ascii=False))
                return
        # 기존 행사·Citi 알림은 재전송하지 않고, 이번에 추가 확인된 AI
        # 통화정책 데이터 활용 축만 공식 + 독립 언론 근거가 있을 때 1회 보충.
        if old.get('ai_policy_sent_key')!=AI_POLICY_KEY and 0 <= event_age <= 3:
            if old.get('ai_policy_pending_key')==AI_POLICY_KEY and old.get('ai_policy_delivery_status')=='sending':
                raise RuntimeError('AI 통화정책 추가 알림 전송 결과 불명확 — 중복 전송 보류')
            try:
                sources=ai_policy_sources()
            except Exception as exc:
                print(json.dumps({'status':'ai_policy_source_pending','sent':False,
                                  'reason':f'{type(exc).__name__}: {exc}'},ensure_ascii=False))
                return
            old.update({'ai_policy_pending_key':AI_POLICY_KEY,
                        'ai_policy_delivery_status':'sending'})
            save(old)
            receipt=send(ai_policy_followup_message(sources))
            old.update({'ai_policy_sent_key':AI_POLICY_KEY,
                        'ai_policy_message_id':receipt,
                        'ai_policy_pending_key':None,
                        'ai_policy_delivery_status':'confirmed',
                        'ai_policy_sources':sources})
            save(old)
            print(json.dumps({'status':'ai_policy_followup_sent','message_id':receipt,
                              'imf_message_id':old.get('message_id'),
                              'citi_message_id':old.get('citi_message_id')},ensure_ascii=False))
            return
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
    citi_source=citi_reported()
    has_citi=bool(citi_source)
    msg=compose(official,coverage,has_citi)
    old.update({'pending_key':EVENT_ID,'delivery_status':'sending'})
    save(old)
    mid=send(msg)
    old.update({
        'last_sent_key':EVENT_ID,'message_id':mid,'pending_key':None,
        'delivery_status':'confirmed','sources':[FED_CAL,IMF,REUTERS],
        'citi_reported':has_citi,'citi_source':citi_source,
        'coverage_sources':[x['url'] for x in coverage],
        'coverage_publishers':sorted(set(x['publisher'] for x in coverage)),
        'sent_at_utc':datetime.now(timezone.utc).isoformat()
    })
    save(old)
    print(json.dumps({'status':'sent','message_id':mid,'official':official,
                      'publishers':old['coverage_publishers'],'citi_reported':has_citi},ensure_ascii=False))


if __name__=='__main__':main()
