#!/usr/bin/env python3
"""공식 베이지북: 발표 완료 확인 → 지역 가격·AI/고용 분리 → 1회 송출."""
import hashlib
import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/'data/warsh_beige_book_watch_state.json'
FED='https://www.federalreserve.gov'
TOKEN=(os.getenv('TELEGRAM_BOT_TOKEN') or '').strip()
CHAT=(os.getenv('TELEGRAM_CHAT_ID') or '').strip()
EXPECTED=(os.getenv('EXPECTED_BOT_USERNAME') or '').strip().lstrip('@')
FORCE=(os.getenv('FORCE_NOTIFY') or '0')=='1'
ET=ZoneInfo('America/New_York')
UA='Mozilla/5.0 (compatible; khs-watch/beige-book-1.0)'
MONTHS={m:i for i,m in enumerate(
    ['','January','February','March','April','May','June','July','August',
     'September','October','November','December']) if m}


def load():
    try:return json.loads(STATE.read_text(encoding='utf-8'))
    except (OSError,ValueError):return {}


def save(state):
    STATE.parent.mkdir(parents=True,exist_ok=True)
    state['updated_at_utc']=datetime.now(timezone.utc).isoformat()
    STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def get(url,timeout=14):
    last=None
    for attempt in range(2):
        try:
            req=urllib.request.Request(url,headers={
                'User-Agent':UA,'Accept-Language':'en-US,en;q=0.9',
            })
            with urllib.request.urlopen(req,timeout=timeout) as resp:
                return resp.read().decode('utf-8','replace'),resp.geturl()
        except urllib.error.HTTPError as exc:
            if exc.code==404:return None,None
            last=exc
        except Exception as exc:last=exc
        if attempt==0:time.sleep(1)
    raise last


def clean(raw):
    s=re.sub(r'(?is)<script[^>]*>.*?</script>|<style[^>]*>.*?</style>',' ',raw)
    s=re.sub(r'(?i)</(?:p|h[1-6]|li|div|section)>',' ',s)
    s=re.sub(r'(?s)<[^>]*>',' ',s)
    return ' '.join(html.unescape(s).replace('\xa0',' ').split())


def number(word):
    w=str(word).strip().lower()
    words={'zero':0,'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,
           'seven':7,'eight':8,'nine':9,'ten':10,'eleven':11,'twelve':12}
    return words.get(w,int(w)) if w.isdigit() else words.get(w)


def release_meta(raw,year,month):
    txt=clean(raw)
    m=re.search(r'Last Update:\s*([A-Z][a-z]+)\s+(\d{1,2}),?\s+(20\d{2})',txt,re.I)
    if not m or m.group(1).capitalize() not in MONTHS:
        return None
    try:
        date=datetime(int(m.group(3)),MONTHS[m.group(1).capitalize()],int(m.group(2))).date()
    except ValueError:return None
    if (date.year,date.month)!=(year,month):return None
    if datetime.now(ET) < datetime(date.year,date.month,date.day,14,0,tzinfo=ET):
        return None
    if not ('National Summary' in txt and 'Overall Economic Activity' in txt and 'Prices' in txt):
        return None
    return date.isoformat()


def parse_national(raw):
    text=clean(raw)
    a=text.find('National Summary')
    if a<0:raise ValueError('연준 국가별 요약 제목 없음')
    # 기업의 지역 보고와 국가 총괄을 섞지 않는다.
    b=text.find('Highlights by Federal Reserve District',a)
    if b<0:b=text.find('Boston Economic',a)
    section=text[a:b] if b>a else text[a:]
    def match(pattern):
        m=re.search(pattern,section,re.I)
        return number(m.group(1)) if m else None

    robust=match(r'(\w+) Districts characterized overall price growth as robust')
    moderate=match(r'while (\w+) noted that growth was moderate')
    modest=match(r'(\w+) District reported modest price growth')
    acceleration=match(r'(\w+) Districts reported that the pace of price increases picked up')
    ai_hiring=match(r'(\w+) Districts reported that some firms had either reduced staffing')
    if None in (robust,moderate,acceleration,ai_hiring):
        raise ValueError('국가 요약의 필수 물가·고용 문구 파싱 실패 — 알림 보류')
    if not (0 <= robust <= 12 and 0 <= moderate <= 12 and robust+moderate<=12):
        raise ValueError('지역 숫자 합계 부정확')
    if modest is None:
        modest=12-robust-moderate
    if robust+moderate+modest != 12:
        raise ValueError('지역 물가 구분 합계가 12가 아님')

    return {
        'strong_price_districts':robust,
        'moderate_price_districts':moderate,
        'modest_price_districts':modest,
        'price_acceleration_districts':acceleration,
        'ai_hiring_districts':ai_hiring,
        'energy_freight':('fuel surcharges' in section.lower()
                          and 'diesel' in section.lower()),
        'insurer_tariff':('insurance' in section.lower()
                          and 'tariffs' in section.lower()),
        'consumer_resistance':('price-sensitive' in section.lower()
                               or 'resist price hikes' in section.lower()),
        'contract_lag':('contracts expire' in section.lower()
                        and 'renegotiate' in section.lower()),
        'consumer_little_change':('little or no change in overall consumer spending'
                                  in section.lower()),
    }


def candidates():
    today=datetime.now(ET).date()
    y,m=today.year,today.month
    out=[]
    for offset in range(3):
        year=y+(m-1-offset)//12
        month=(m-1-offset)%12+1
        if year>=2026:
            out.append((year,month))
    return out


def official_latest():
    errors=[]
    for year,month in candidates():
        url=f'{FED}/monetarypolicy/beigebook{year:04d}{month:02d}-summary.htm'
        try:raw,final=get(url)
        except Exception as e:
            errors.append(f'{year}-{month:02d}: {type(e).__name__}')
            continue
        if not raw:continue
        rel=release_meta(raw,year,month)
        if not rel:continue
        values=parse_national(raw)
        return {'release_date':rel,'url':final,'values':values}
    raise RuntimeError('최근 3개월 공식 베이지북 확정 요약 확인 실패: '+'; '.join(errors))


def fmt_link(url):
    return '<a href="'+html.escape(url,quote=True)+'">연준 공식 베이지북</a>'


def message(item,revision=False):
    v=item['values']; date=item['release_date']
    lines=[
        '<b>[Warsh | 연준 베이지북 물가·AI 고용 감시]</b>',
        f'발표: {date} · 전국 12개 지역 기업 설문',
        '• <b>공식 원문 수치 정정</b>' if revision else '• <b>신규 공식 보고서</b>',
        '',
        '<b>한눈에 보기</b>',
        f"• 물가: 강함 {v['strong_price_districts']}곳 · 보통 {v['moderate_price_districts']}곳 · 완만함 {v['modest_price_districts']}곳",
        f"• 물가 상승 속도 확대: <b>{v['price_acceleration_districts']}곳</b>",
        f"• AI 생산성 향상 이후 인원 감축·채용 지연 사례 보고: <b>{v['ai_hiring_districts']}곳</b>",
        '',
        '<b>역풍·정책 연결</b>',
    ]
    if v['energy_freight']:lines.append('• 경유값 상승 → 운송 유류할증료 → 공급망 원가 전가')
    if v['insurer_tariff']:lines.append('• 관세·보험료·원자재 가격도 기업 투입원가 압박')
    if v['consumer_resistance']:lines.append('• 소비자는 가격 인상에 저항 → 비용 상승과 판매가격 전가를 분리')
    if v['contract_lag']:lines.append('• 기존 계약 만료·재협상 시기에 가격 전이 지연 가능성')
    if v['consumer_little_change']:lines.append('• 소비지출은 다수 지역에서 큰 변화 없어 수요 둔화 위험도 관찰')
    lines += [
        '• 베이지북은 기업 접촉 조사이며 연준 위원의 투표·금리인상 확정이 아닙니다.',
        '• 다음 PCE·고용·2년물과 대조하되 공식 시장확률 검증 실패 시 수치를 표시하지 않습니다.',
        '',
        fmt_link(item['url'])
    ]
    return '\n'.join(lines)


def send(body):
    if not TOKEN or not CHAT or not EXPECTED:raise RuntimeError('Warsh Telegram 인증값 없음')
    with urllib.request.urlopen(f'https://api.telegram.org/bot{TOKEN}/getMe',timeout=18) as r:
        bot=json.loads(r.read().decode('utf-8'))
    user=str((bot.get('result') or {}).get('username') or '').lower()
    if not bot.get('ok') or user!=EXPECTED.lower():raise RuntimeError('알림 발신 봇이 기존 Warsh 봇과 다름')
    if len(body)>3800:raise RuntimeError('Telegram 메시지 길이 초과')
    req=urllib.request.Request(
        f'https://api.telegram.org/bot{TOKEN}/sendMessage',
        data=urllib.parse.urlencode({
            'chat_id':CHAT,'text':body,'parse_mode':'HTML','disable_web_page_preview':'true'
        }).encode('utf-8'),method='POST')
    with urllib.request.urlopen(req,timeout=20) as r:
        answer=json.loads(r.read().decode('utf-8'))
    id=(answer.get('result') or {}).get('message_id')
    if answer.get('ok') is not True or not isinstance(id,int):
        raise RuntimeError('Telegram API 확인 또는 message_id 없음')
    return id


def main():
    state=load()
    item=official_latest()
    digest=hashlib.sha256(json.dumps(item['values'],sort_keys=True).encode()).hexdigest()[:16]
    key=item['release_date']+'|'+digest
    sent=set(state.get('sent_keys') or [])
    if state.get('pending_key')==key and state.get('delivery_status')=='sending':
        raise RuntimeError('이전 발송 확인 불명확 — 중복 전송 방지 위해 운영확인 필요')
    if key in sent and not FORCE:
        print(json.dumps({'status':'duplicate_skipped','release_date':item['release_date'],'sent':False},ensure_ascii=False))
        return
    # 과거 백필은 발표일 이후 7일 이내에만 허용.
    age=(datetime.now(ET).date()-datetime.fromisoformat(item['release_date']).date()).days
    if age>7 and not FORCE:
        print(json.dumps({'status':'historical_baseline_only','age_days':age,'sent':False},ensure_ascii=False))
        return
    revision=any(x.startswith(item['release_date']+'|') for x in sent)
    state.update({'pending_key':key,'delivery_status':'sending','release_date':item['release_date']})
    save(state)
    id=send(message(item,revision))
    sent.add(key)
    state.update({
        'last_sent_key':key,'message_id':id,'sent_keys':list(sorted(sent))[-30:],
        'pending_key':None,'delivery_status':'confirmed','source_url':item['url'],
        'values':item['values'],'last_sent_at_utc':datetime.now(timezone.utc).isoformat(),
    })
    save(state)
    print(json.dumps({'status':'sent','message_id':id,'release_date':item['release_date'],
                      'values':item['values'],'revision':revision},ensure_ascii=False))


if __name__=='__main__':main()
