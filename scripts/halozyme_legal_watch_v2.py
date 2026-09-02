from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import os
import pathlib
import re
import subprocess
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo('Asia/Seoul')
UTC = dt.timezone.utc
UA = 'Mozilla/5.0 (compatible; HalozymeLegalWatch/2.0)'
ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / 'data/halozyme_ptab_watch_state.json'
STATUS = ROOT / 'out/halozyme_ptab_status.md'
ROUTE = ROOT / 'data/bio_telegram_chat_id.enc'

KNOWN_CASES = {
    'PGR2025-00003': '11,952,600', 'PGR2025-00004': '12,018,298',
    'PGR2025-00006': '12,152,262', 'PGR2025-00009': '12,123,035',
    'PGR2025-00017': '12,110,520', 'PGR2025-00024': '12,060,590',
    'PGR2025-00030': '12,054,758', 'PGR2025-00033': '12,049,652',
    'PGR2025-00039': '12,104,185', 'PGR2025-00042': '12,037,618',
    'PGR2025-00046': '12,091,692', 'PGR2025-00050': '12,077,791',
    'PGR2025-00052': '12,264,345', 'PGR2025-00053': '12,195,773',
    'PGR2025-00087': '12,371,685', 'IPR2026-00312': '10,865,400',
    'IPR2026-00313': '11,041,149', 'IPR2026-00314': '11,066,656',
}
DISTRICT_CASE = '2:25-cv-03179'

SEARCHES = [
    '"Halozyme" "Merck" PTAB PGR',
    '"Halozyme" "Merck" "Final Written Decision"',
    '"Halozyme" "Merck" "Director Review" PTAB',
    '"Halozyme" "Merck" rehearing PTAB',
    '"Halozyme" "Merck" "Federal Circuit" patent',
    '"Halozyme" "Merck" MDASE patent',
    '"Halozyme" "Merck" modified PH20 patent',
    '"2:25-cv-03179" Halozyme Merck',
    '"PGR2025-00024" OR "PGR2025-00030" OR "PGR2025-00033" OR "PGR2025-00039" Halozyme',
    '"PGR2025-00042" OR "PGR2025-00046" OR "PGR2025-00050" OR "PGR2025-00052" Halozyme',
    '"PGR2025-00053" OR "PGR2025-00087" OR "IPR2026-00312" OR "IPR2026-00313" OR "IPR2026-00314" Halozyme',
]

EVENTS = [
    ('final_unpatentable', ('determining all challenged claims unpatentable', 'all challenged claims unpatentable', 'final written decision', '청구항 전부 무효', '전부 무효')),
    ('director_review', ('director review', '국장 재검토')),
    ('rehearing', ('request for rehearing', 'rehearing', '재심')),
    ('appeal', ('notice of appeal', 'federal circuit', 'court of appeals', '연방순회항소법원', '항소')),
    ('institution', ('granting institution', 'institution decision', 'trial instituted', 'institution denied', '심판 개시')),
    ('termination', ('motion to terminate', 'terminated', 'settlement', 'stipulation of dismissal', '합의', '종결')),
    ('disclaimer', ('statutory disclaimer', 'disclaimed claims', '청구항 포기')),
    ('district_order', ('district court', 'd.n.j.', DISTRICT_CASE, 'new jersey', '뉴저지')),
]


def digest(v: str) -> str:
    return hashlib.sha256(v.encode('utf-8')).hexdigest()[:24]


def fetch(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'en-US,en;q=0.9,ko;q=0.8'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(900_000).decode(r.headers.get_content_charset() or 'utf-8', errors='replace')


def clean_url(url: str) -> str:
    try:
        p = urllib.parse.urlparse(html.unescape(url))
        if p.netloc.lower().endswith('bing.com') and p.path.endswith('/news/apiclick.aspx'):
            target = urllib.parse.parse_qs(p.query).get('url', [''])[0]
            if target.startswith(('http://','https://')):
                return clean_url(target)
        q = [(k,v) for k,v in urllib.parse.parse_qsl(p.query) if not k.lower().startswith('utm_') and k.lower() not in {'ocid','ref','source','cid'}]
        return urllib.parse.urlunparse((p.scheme,p.netloc,p.path,'',urllib.parse.urlencode(q),''))
    except Exception:
        return url


def rss(query: str, engine: str) -> list[dict]:
    if engine == 'Google 뉴스':
        url = 'https://news.google.com/rss/search?' + urllib.parse.urlencode({'q':query,'hl':'en-US','gl':'US','ceid':'US:en'})
    else:
        url = 'https://www.bing.com/search?' + urllib.parse.urlencode({'q':query,'format':'rss'})
    root = ET.fromstring(fetch(url))
    out=[]
    for n in root.findall('.//item')[:30]:
        title=html.unescape((n.findtext('title') or '').strip())
        link=clean_url((n.findtext('link') or '').strip())
        desc=re.sub(r'<[^>]+>',' ',html.unescape(n.findtext('description') or ''))
        pub=(n.findtext('pubDate') or '').strip()
        if link:
            out.append({'engine':engine,'title':title,'url':link,'description':desc,'published':pub})
    return out


def get_case(text: str) -> tuple[str,str]:
    up=text.upper()
    m=re.search(r'\b(?:PGR|IPR)20\d{2}-\d{5}\b',up)
    if m:
        case=m.group(0); return case,KNOWN_CASES.get(case,'')
    digits=re.sub(r'[^0-9]','',text)
    for case,patent in KNOWN_CASES.items():
        if re.sub(r'[^0-9]','',patent) in digits:
            return case,patent
    if DISTRICT_CASE.lower() in text.lower():
        return DISTRICT_CASE,''
    return '',''


def classify(text: str, case: str) -> str:
    low=text.lower()
    # 민사사건은 PGR/IPR 절차 키워드보다 우선 구분한다.
    if case == DISTRICT_CASE:
        return 'district_order'
    for key,terms in EVENTS:
        if key == 'district_order':
            continue
        if any(t.lower() in low for t in terms):
            return key
    return ''


def official(url: str) -> bool:
    host=urllib.parse.urlparse(url).netloc.lower()
    return host.endswith('uspto.gov') or host.endswith('ptacts.uspto.gov') or host.endswith('uscourts.gov') or host.endswith('cafc.uscourts.gov')


def load_state() -> dict:
    if STATE.exists():
        try: return json.loads(STATE.read_text(encoding='utf-8'))
        except Exception: pass
    return {'initialized':False,'seen_events':[],'seen_urls':[],'discovered_cases':{}}


def resolve_chat_id(token: str) -> str:
    direct=(os.getenv('BIO_TELEGRAM_CHAT_ID') or '').strip()
    if direct: return direct
    if not ROUTE.exists(): return ''
    env=os.environ.copy(); env['BIO_TELEGRAM_BOT_TOKEN']=token
    p=subprocess.run(['openssl','enc','-d','-aes-256-cbc','-a','-A','-pbkdf2','-pass','env:BIO_TELEGRAM_BOT_TOKEN','-in',str(ROUTE)],cwd=ROOT,text=True,capture_output=True,timeout=20,env=env)
    return p.stdout.strip() if p.returncode==0 else ''


def send(token: str, chat: str, text: str) -> int:
    body=urllib.parse.urlencode({'chat_id':chat,'text':text,'parse_mode':'HTML','disable_web_page_preview':'true'}).encode()
    req=urllib.request.Request(f'https://api.telegram.org/bot{token}/sendMessage',data=body,method='POST')
    with urllib.request.urlopen(req,timeout=25) as r: payload=json.loads(r.read().decode())
    if not payload.get('ok'): raise RuntimeError(str(payload))
    return int((payload.get('result') or {}).get('message_id') or 0)


def alert(case: str, patent: str, kind: str, item: dict) -> str:
    if kind=='final_unpatentable':
        title=f'MSD 승소 — {case}, Halozyme 특허 {patent or "관련 특허"} 심판대상 청구항 무효'
        decision='PTAB가 심판 대상 청구항을 특허 받을 수 없음으로 최종 판단'
        impact='ALT-B4 자체 특허가 유효하다고 판정한 사건은 아닙니다. 다만 Halozyme의 변형 PH20 특허 장벽이 약해지는 만큼 MSD·알테오젠의 미국 피하주사 전환 관련 특허분쟁 부담을 낮추는 방향입니다.'
    elif kind=='director_review':
        title=f'{case} — USPTO 국장 재검토 새 결정'
        decision='최종서면결정에 대한 USPTO 국장 재검토 절차 변화'
        impact='기존 PTAB 승패가 유지되는지 뒤집히는지 확인이 핵심입니다.'
    elif kind=='rehearing':
        title=f'{case} — PTAB 재심 절차 변화'
        decision='당사자의 재심 신청 또는 PTAB 재심 결과 확인'
        impact='최종 무효 판단의 유지 여부를 확인해야 합니다.'
    elif kind=='appeal':
        title=f'{case} — 연방순회항소법원 항소 변화'
        decision='PTAB 결정에 대한 항소 단계 변화'
        impact='PTAB 무효 결정이 법원 단계에서도 유지되는지가 최종 특허 장벽 판단에 중요합니다.'
    elif kind=='institution':
        title=f'{case} — PGR·IPR 심판 개시 결정'
        decision='PTAB가 본안 심리를 개시하거나 개시를 거부한 사건'
        impact='향후 최종서면결정 가능성과 Halozyme 특허 장벽의 추가 약화·유지 여부를 가르는 초기 단계입니다.'
    elif kind=='termination':
        title=f'{case} — 특허분쟁 종결·합의 변화'
        decision='심판 또는 소송의 종결·합의 관련 새 문서'
        impact='합의 조건과 특허 존속 여부에 따라 알테오젠 경쟁구도가 달라질 수 있습니다.'
    elif kind=='district_order':
        title='Halozyme vs MSD 뉴저지 연방법원 민사소송 새 결정'
        decision='PTAB와 별도로 진행되는 특허침해 민사소송의 새 명령·판결·합의'
        impact='PTAB 특허성 판단과 별개로 침해·금지명령·손해배상 위험이 남아 있는지 확인해야 합니다.'
    else:
        title=f'{case} — Halozyme 특허분쟁 새 변화'; decision=item['title']; impact='MSD·알테오젠의 피하주사 사업과 연결되는 특허 리스크 변화입니다.'
    src='USPTO/PTAB·법원 공식자료' if official(item['url']) else '2차 자료 — 공식 원문 교차확인 대상'
    url=html.escape(item['url'],quote=True)
    return ('<b>[바이오 감시] Halozyme 특허분쟁</b>\n\n'
            f'<b>{html.escape(title)}</b>\n\n'
            f'- <b>사건:</b> {html.escape(case)}' + (f' · 미국 특허 {html.escape(patent)}' if patent else '') + '\n'
            f'- <b>결정:</b> {html.escape(decision)}\n'
            f'- <b>알테오젠:</b> {html.escape(impact)}\n'
            '- <b>아직 남음:</b> USPTO 국장 재검토·PTAB 재심·연방순회항소법원 항소 + 다른 PGR·IPR + 뉴저지 연방법원 민사소송\n'
            '- <b>다음 확인:</b> 국장 재검토·재심 → 항소 → 다른 관련 사건 최종서면결정\n'
            f'- <b>원문 확인:</b> {src}\n'
            f'- <a href="{url}">원문 뉴스보기</a>')


def main() -> int:
    STATE.parent.mkdir(parents=True,exist_ok=True); STATUS.parent.mkdir(parents=True,exist_ok=True)
    state=load_state(); first=not state.get('initialized')
    seen_events=set(state.get('seen_events') or []); seen_urls=set(state.get('seen_urls') or [])
    discovered=dict(state.get('discovered_cases') or {})
    errors=[]; candidates=[]
    for q in SEARCHES:
        for engine in ('Bing 웹','Google 뉴스'):
            try:
                for item in rss(q,engine):
                    blob=f"{item['title']} {item['description']} {item['url']}"
                    if 'halozyme' not in blob.lower() or not any(x in blob.lower() for x in ('merck','msd','pgr','ipr','ptab','2:25-cv-03179')):
                        continue
                    case,patent=get_case(blob)
                    if not case: continue
                    if case.startswith(('PGR','IPR')): discovered[case]=patent or discovered.get(case,'')
                    kind=classify(blob,case)
                    if not kind: continue
                    ekey=digest(f'{case}|{kind}')
                    candidates.append((0 if official(item['url']) else 1,ekey,case,patent or discovered.get(case,''),kind,item))
            except Exception as exc:
                errors.append(f'{engine}:{type(exc).__name__}')
    best={}
    for row in sorted(candidates,key=lambda x:x[0]):
        best.setdefault(row[1],row)

    # 최초 도입 시 과거 기사·과거 절차가 한꺼번에 Telegram으로 쏟아지는 것을 막고 현재 기준선만 저장한다.
    if first:
        for ekey,row in best.items():
            seen_events.add(ekey); seen_urls.add(row[5]['url'])
        sent=[]
    else:
        token=(os.getenv('BIO_TELEGRAM_BOT_TOKEN') or '').strip(); chat=resolve_chat_id(token) if token else ''
        sent=[]
        if not token or not chat:
            errors.append('Telegram 경로 없음')
        else:
            for ekey,row in list(best.items()):
                _,_,case,patent,kind,item=row
                if ekey in seen_events or item['url'] in seen_urls: continue
                mid=send(token,chat,alert(case,patent,kind,item)); sent.append(mid)
                seen_events.add(ekey); seen_urls.add(item['url'])

    now=dt.datetime.now(KST).isoformat(timespec='seconds')
    state.update({'initialized':True,'last_check_kst':now,'seen_events':sorted(seen_events)[-5000:],'seen_urls':sorted(seen_urls)[-5000:],'tracked_known_cases':KNOWN_CASES,'discovered_cases':discovered,'district_case':DISTRICT_CASE,'errors_last_run':errors[-20:]})
    STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    STATUS.write_text(f'Halozyme 특허분쟁 감시 — {now}; 신규송출={len(sent)}; 알려진 PGR·IPR={len(KNOWN_CASES)}; 발견사건={len(discovered)}; 오류={len(errors)}\n',encoding='utf-8')
    print(json.dumps({'status':'ok' if not errors else 'partial','first_run':first,'sent_message_ids':sent,'tracked_known_cases':len(KNOWN_CASES),'discovered_cases':len(discovered),'errors':errors[-5:]},ensure_ascii=False))
    return 0

if __name__=='__main__': raise SystemExit(main())
