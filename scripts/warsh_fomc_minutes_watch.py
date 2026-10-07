#!/usr/bin/env python3
import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

STATE = Path('data/warsh_fomc_minutes_watch_state.json')
FOMC_STATE = Path('data/warsh_fomc_event_watch_state.json')
SEP_STATE = Path('data/warsh_sep_path_watch_state.json')
FED_CAL = 'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm'
TOKEN = (os.getenv('TELEGRAM_BOT_TOKEN') or '').strip()
CHAT = (os.getenv('TELEGRAM_CHAT_ID') or '').strip()
BOT = (os.getenv('EXPECTED_BOT_USERNAME') or 'hshs8879_bot').strip().lstrip('@')
FORCE = os.getenv('FORCE_NOTIFY','0') == '1'
UA = 'Mozilla/5.0 (compatible; khs-watch/4.0)'
ET = ZoneInfo('America/New_York')


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={'User-Agent':UA,'Accept-Language':'en-US,en;q=0.9'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8','replace'), r.geturl()


def clean(raw):
    raw = re.sub(r'(?is)<script.*?>.*?</script>|<style.*?>.*?</style>', ' ', raw)
    raw = re.sub(r'(?i)<br\s*/?>|</p>|</li>|</tr>|</h[1-6]>', '\n', raw)
    raw = re.sub(r'(?s)<[^>]+>', ' ', raw)
    text = html.unescape(raw).replace('\xa0',' ')
    text = re.sub(r'[ \t]+',' ',text)
    text = re.sub(r'\n\s*\n+','\n',text)
    return text.strip()


def load(path):
    try:
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    except Exception:
        return {}


def save(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    state['updated_at_utc'] = datetime.now(timezone.utc).isoformat()
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def botname():
    with urllib.request.urlopen(f'https://api.telegram.org/bot{TOKEN}/getMe', timeout=20) as r:
        d=json.loads(r.read().decode())
    return str((d.get('result') or {}).get('username') or '')


def link(label,url):
    return f'<a href="{html.escape(url,quote=True)}">{html.escape(label)}</a>'


def send(msg):
    if not TOKEN or not CHAT:
        raise RuntimeError('Telegram 비밀값 없음')
    if botname().lower() != BOT.lower():
        raise RuntimeError(f'Telegram 봇 불일치: expected @{BOT}')
    data=urllib.parse.urlencode({
        'chat_id':CHAT,'text':msg[:4090],'parse_mode':'HTML','disable_web_page_preview':'true'
    }).encode()
    req=urllib.request.Request(f'https://api.telegram.org/bot{TOKEN}/sendMessage',data=data,method='POST')
    with urllib.request.urlopen(req,timeout=20) as r:
        out=json.loads(r.read().decode())
    if not out.get('ok'):
        raise RuntimeError('Telegram 전송 실패')


def latest_statement_date():
    state=load(FOMC_STATE)
    cur=state.get('current_statement') or {}
    if cur.get('date'):
        return str(cur['date'])
    # Official-calendar fallback.
    raw,_=fetch(FED_CAL)
    rows=re.findall(r'href=["\']([^"\']*/newsevents/pressreleases/monetary(20\d{6})a\.htm)["\']',raw,re.I)
    if not rows:
        return None
    ds=max(d for _,d in rows)
    return f'{ds[:4]}-{ds[4:6]}-{ds[6:]}'


def minutes_url(statement_date):
    return 'https://www.federalreserve.gov/monetarypolicy/fomcminutes' + statement_date.replace('-','') + '.htm'


def release_date(text):
    patterns=[
        r'For release at\s+\d{1,2}:\d{2}\s+[ap]\.m\.\s+(?:EDT|EST)\s+([A-Z][a-z]+\s+\d{1,2},\s+20\d{2})',
        r'Released?\s+([A-Z][a-z]+\s+\d{1,2},\s+20\d{2})',
    ]
    for pat in patterns:
        m=re.search(pat,text,re.I)
        if m:
            try:
                return datetime.strptime(m.group(1),'%B %d, %Y').date().isoformat()
            except Exception:
                pass
    return None


def participant_sentences(text):
    out=[]
    for s in re.split(r'(?<=[.!?])\s+', text):
        s=' '.join(s.split())
        if len(s)<30 or len(s)>1200:
            continue
        if re.search(r'\bparticipants?\b|\bmembers?\b',s,re.I):
            out.append(s)
    return out


def quantify(sentence):
    low=sentence.lower()
    for eng,ko in [
        ('all participants','모든 참가자'),('almost all','거의 모든 참가자'),
        ('most participants','대부분 참가자'),('many participants','많은 참가자'),
        ('a number of participants','여러 참가자'),('several participants','여러 참가자'),
        ('some participants','일부 참가자'),('a few participants','소수 참가자'),
        ('one participant','한 참가자')
    ]:
        if eng in low:
            return ko
    return '참가자'


def classify(text):
    sents=participant_sentences(text)
    hike=[]; wait=[]; balance=[]
    hike_pat=re.compile(
        r'further (?:tightening|firming|increase)|additional (?:tightening|firming|increase)|'
        r'raise the target range|further increases? in (?:the )?federal funds rate|'
        r'additional increases? in (?:the )?policy rate',
        re.I
    )
    wait_pat=re.compile(
        r'maintain (?:the )?(?:current )?(?:target range|policy rate)|'
        r'keep (?:the )?(?:target range|policy rate).*unchanged|'
        r'hold (?:the )?(?:federal funds rate|policy rate)|'
        r'wait for|patient|pause|no further (?:increase|tightening|firming)',
        re.I
    )
    balance_pat=re.compile(
        r'ample reserves|balance sheet|treasury bills|reinvest|roll over|'
        r'run[- ]?off|redemption cap|securities holdings|reserve balances',
        re.I
    )
    for s in sents:
        if hike_pat.search(s): hike.append((quantify(s),s))
        if wait_pat.search(s): wait.append((quantify(s),s))
        if balance_pat.search(s): balance.append((quantify(s),s))

    if hike and wait:
        rate='위원 의견 갈림 — 추가인상과 관망 경로 모두 존재'
    elif hike:
        rate='추가인상 옵션 유지'
    elif wait:
        rate='인상 후 관망 가능성 강화'
    else:
        rate='명확한 추가 금리경로 약속 자동 식별 안 됨'

    low=text.lower()
    if re.search(r'run[- ]?off|redemption cap|reduce.*securities holdings',low):
        bal='총량축소형 대차대조표 긴축 논의 확인'
    elif re.search(r'ample reserves|treasury bills|roll over.*principal|reinvest.*principal',low,re.I|re.S):
        bal='충분한 준비금 유지·재투자/구성 전환 논의 확인'
    else:
        bal='대차대조표 방향의 명확한 변경 문구 자동 식별 안 됨'
    return {'rate':rate,'balance':bal,'hike':hike,'wait':wait,'balance_hits':balance}


def compact_evidence(rows, label):
    if not rows:
        return f'• {label}: 명확한 관련 문장 자동 식별 없음'
    seen=[]
    for q,_ in rows[:4]:
        if q not in seen: seen.append(q)
    return f"• {label}: " + '·'.join(seen) + '의 관련 논의 확인'


def current_sep():
    s=load(SEP_STATE).get('snapshot') or {}
    funds=s.get('funds') or []
    return {
        'date':s.get('date'),'url':s.get('url'),
        'yearend':funds[0] if len(funds)>0 else None,
        'nextyear':funds[1] if len(funds)>1 else None,
    }


def message(stmt_date,url,rel,cls):
    fomc=load(FOMC_STATE)
    stmt=fomc.get('current_statement') or {}
    sep=current_sep()
    lines=[
        '<b>[Warsh FOMC 의사록 · 반응함수 변화]</b>',
        f'대상 회의: {stmt_date} · 의사록 공개: {rel or "공식 페이지 확인"}',
        '',
        '<b>핵심 판정</b>',
        f"• <b>금리경로</b>: {html.escape(cls['rate'])}",
        f"• <b>대차대조표</b>: {html.escape(cls['balance'])}",
        '',
        '<b>왜 이렇게 봤나</b>',
        compact_evidence(cls['hike'],'추가긴축 관련'),
        compact_evidence(cls['wait'],'관망·유지 관련'),
    ]
    if stmt.get('low') is not None:
        lines.append(f"• 현재 공식 목표범위: {float(stmt['low']):.2f}~{float(stmt['high']):.2f}%")
    if sep.get('yearend') is not None:
        lines.append(f"• 최신 점도표: 2026년 말 {float(sep['yearend']):.1f}% · 2027년 말 {float(sep['nextyear']):.1f}%")
    lines += [
        '',
        '<b>정확히 읽는 법</b>',
        '• 의사록은 해당 회의에서 실제로 어떤 의견이 오갔는지를 보여주는 <b>과거 회의 기록</b>입니다. 오늘 새로운 금리결정이 내려졌다는 뜻이 아닙니다.',
        '• 참가자 수 표현과 추가긴축·관망 문구를 함께 보고, 한 문장만으로 “다음 회의 확정”이라고 해석하지 않습니다.',
        '• 대차대조표 태스크포스의 검토와 FOMC가 실제 채택한 시행지침도 분리합니다.',
        '',
        '<b>다음 확인</b>',
        '• 의사록 공개 뒤 2년물과 다음 FOMC 선물경로가 실제로 재가격되는지',
        '• 다음 CPI·PCE와 고용이 의사록의 우려를 강화하거나 약화시키는지',
        '• 실제 FOMC 시행지침에서 대차대조표 문구가 바뀌는지',
        '',
        '<b>원천</b>',
        link('연준 FOMC 의사록',url) + ' · ' + link('연준 FOMC 일정',FED_CAL),
    ]
    if sep.get('url'):
        lines[-1] += ' · ' + link('연준 경제전망·점도표',sep['url'])
    return '\n'.join(lines)


def main():
    old=load(STATE)
    stmt_date=latest_statement_date()
    if not stmt_date:
        raise RuntimeError('최신 FOMC 회의일 확인 실패')
    url=minutes_url(stmt_date)
    try:
        raw,final=fetch(url)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            save({
                'last_statement_date':stmt_date,
                'last_minutes_url':old.get('last_minutes_url'),
                'last_release_date':old.get('last_release_date'),
                'status':'공식 의사록 공개 대기',
            })
            print(json.dumps({'available':False,'statement_date':stmt_date,'status':'공식 의사록 공개 대기'},ensure_ascii=False))
            return
        raise
    text=clean(raw)
    rel=release_date(text)
    cls=classify(text)
    already=old.get('last_minutes_url')==final
    today_et=datetime.now(ET).date().isoformat()
    first=not bool(old)
    # On installation, baseline old minutes silently unless it is the release day.
    should=FORCE or (not already and (not first or rel==today_et))
    if should:
        send(message(stmt_date,final,rel,cls))
    save({
        'last_statement_date':stmt_date,
        'last_minutes_url':final,
        'last_release_date':rel,
        'classification':cls,
        'sent':should,
        'status':'공식 의사록 확인',
    })
    print(json.dumps({
        'available':True,'statement_date':stmt_date,'release_date':rel,
        'sent':should,'classification':{'rate':cls['rate'],'balance':cls['balance']}
    },ensure_ascii=False))


if __name__=='__main__':
    main()
