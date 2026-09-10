#!/usr/bin/env python3
import html
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

STATE_PATH = Path('data/warsh_inflation_market_watch_state.json')
PPI_URL = 'https://www.bls.gov/news.release/ppi.htm'
CPI_URL = 'https://www.bls.gov/news.release/cpi.htm'
TREASURY_TEXT_URL = 'https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve'
TOKEN = (os.getenv('TELEGRAM_BOT_TOKEN') or '').strip()
CHAT_ID = (os.getenv('TELEGRAM_CHAT_ID') or '').strip()
EXPECTED_BOT = (os.getenv('EXPECTED_BOT_USERNAME') or 'khs8879887988798879_bot').strip().lstrip('@')
FORCE_NOTIFY = os.getenv('FORCE_NOTIFY', '0') == '1'
UA = 'Mozilla/5.0 (compatible; khs-watch/1.0; +https://github.com/qedgwangju-dot/khs-watch)'
MONTHS = {m.lower(): i for i, m in enumerate(['January','February','March','April','May','June','July','August','September','October','November','December'], 1)}


def fetch(url: str) -> tuple[str, str]:
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'en-US,en;q=0.9'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8', errors='replace'), r.geturl()


def clean_text(raw: str) -> str:
    raw = re.sub(r'(?is)<script.*?>.*?</script>|<style.*?>.*?</style>', ' ', raw)
    raw = re.sub(r'(?i)<br\s*/?>|</p>|</li>|</h[1-6]>', '\n', raw)
    raw = re.sub(r'(?s)<[^>]+>', ' ', raw)
    text = html.unescape(raw).replace('\xa0', ' ')
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n\s*\n+', '\n', text)
    return text.strip()


def signed(direction: str, value: str) -> float:
    v = float(value)
    return -v if direction.lower().startswith(('fell','declin','decreas','drop','moved down')) else v


def period_key(month: str, year: int) -> str:
    return f'{year}-{MONTHS[month.lower()]:02d}'


def parse_release_date(text: str) -> str | None:
    m = re.search(r'embargoed until.*?([A-Z][a-z]+\s+\d{1,2},\s+20\d{2})', text, re.I | re.S)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), '%B %d, %Y').date().isoformat()
    except Exception:
        return None


def parse_ppi() -> dict:
    raw, final = fetch(PPI_URL)
    text = clean_text(raw)
    h = re.search(r'PRODUCER PRICE INDEX(?:ES)?\s*-\s*([A-Z]+)\s+(20\d{2})', text, re.I)
    if not h:
        raise RuntimeError('BLS PPI period not parsed')
    month = h.group(1).title(); year = int(h.group(2)); pkey = period_key(month, year)
    action = r'(increased|rose|advanced|fell|declined|decreased|dropped|moved up|moved down)'
    hm = re.search(rf'Producer Price Index for final demand\s+{action}\s+([\d.]+)\s+percent in {month}', text, re.I)
    hy = re.search(rf'On an unadjusted basis, the index for final demand\s+{action}\s+([\d.]+)\s+percent for the 12 months ended in {month}', text, re.I)
    cm = re.search(rf'index for final demand less foods, energy, and trade services\s+{action}\s+([\d.]+)\s+percent in {month}', text, re.I)
    cy = re.search(r'for the 12 months ended in [A-Za-z]+, prices for final demand less foods, energy, and trade services\s+(increased|rose|advanced|fell|declined|decreased|dropped)\s+([\d.]+)\s+percent', text, re.I)
    return {
        'kind': 'PPI', 'period': pkey, 'period_label': f'{MONTHS[month.lower()]}월 PPI',
        'release_date': parse_release_date(text), 'url': final,
        'headline_mom': signed(hm.group(1), hm.group(2)) if hm else None,
        'headline_yoy': signed(hy.group(1), hy.group(2)) if hy else None,
        'core_mom': signed(cm.group(1), cm.group(2)) if cm else None,
        'core_yoy': signed(cy.group(1), cy.group(2)) if cy else None,
    }


def parse_cpi() -> dict:
    raw, final = fetch(CPI_URL)
    text = clean_text(raw)
    h = re.search(r'CONSUMER PRICE INDEX\s*-\s*([A-Z]+)\s+(20\d{2})', text, re.I)
    if not h:
        raise RuntimeError('BLS CPI period not parsed')
    month = h.group(1).title(); year = int(h.group(2)); pkey = period_key(month, year)
    action = r'(increased|rose|advanced|fell|declined|decreased|dropped)'
    hm = re.search(rf'Consumer Price Index for All Urban Consumers \(CPI-U\)\s+{action}\s+([\d.]+)\s+percent on a seasonally adjusted basis in {month}', text, re.I)
    hy = re.search(r'Over the last 12 months, the all items index\s+(increased|rose|advanced|fell|declined|decreased|dropped)\s+([\d.]+)\s+percent before seasonal adjustment', text, re.I)
    cm = re.search(rf'index for all items less food and energy\s+{action}\s+([\d.]+)\s+percent in {month}', text, re.I)
    cy = re.search(r'(?:all items less food and energy index|index for all items less food and energy)\s+(increased|rose|advanced|fell|declined|decreased|dropped)\s+([\d.]+)\s+percent over the last 12 months', text, re.I)
    return {
        'kind': 'CPI', 'period': pkey, 'period_label': f'{MONTHS[month.lower()]}월 CPI',
        'release_date': parse_release_date(text), 'url': final,
        'headline_mom': signed(hm.group(1), hm.group(2)) if hm else None,
        'headline_yoy': signed(hy.group(1), hy.group(2)) if hy else None,
        'core_mom': signed(cm.group(1), cm.group(2)) if cm else None,
        'core_yoy': signed(cy.group(1), cy.group(2)) if cy else None,
    }


def treasury_url(year: int) -> str:
    return ('https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml'
            f'?data=daily_treasury_yield_curve&field_tdr_date_value={year}')


def treasury_rows() -> list[dict]:
    year = datetime.now(timezone.utc).year
    raw, _ = fetch(treasury_url(year))
    root = ET.fromstring(raw.encode('utf-8'))
    rows=[]
    for props in root.findall('.//{*}properties'):
        row={'date':None,'2y':None,'10y':None,'30y':None}
        for child in list(props):
            name=child.tag.split('}')[-1]; text=(child.text or '').strip()
            if name=='NEW_DATE': row['date']=text[:10]
            elif name=='BC_2YEAR' and text: row['2y']=float(text)
            elif name=='BC_10YEAR' and text: row['10y']=float(text)
            elif name=='BC_30YEAR' and text: row['30y']=float(text)
        if row['date'] and all(row[k] is not None for k in ('2y','10y','30y')): rows.append(row)
    rows.sort(key=lambda x:x['date'])
    if len(rows)<2: raise RuntimeError('Treasury official curve rows not found')
    return rows


def get_bot_username() -> str:
    with urllib.request.urlopen(f'https://api.telegram.org/bot{TOKEN}/getMe', timeout=20) as r:
        data=json.loads(r.read().decode('utf-8'))
    if not data.get('ok'): raise RuntimeError('Telegram getMe failed')
    return str((data.get('result') or {}).get('username') or '')


def link(label: str, url: str) -> str:
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'


def send(text: str):
    if not TOKEN or not CHAT_ID: raise RuntimeError('Telegram token/chat id missing')
    username=get_bot_username()
    if username.lower()!=EXPECTED_BOT.lower(): raise RuntimeError(f'Wrong Telegram bot: expected @{EXPECTED_BOT}, got @{username}')
    payload=urllib.parse.urlencode({'chat_id':CHAT_ID,'text':text[:4090],'parse_mode':'HTML','disable_web_page_preview':'true'}).encode('utf-8')
    req=urllib.request.Request(f'https://api.telegram.org/bot{TOKEN}/sendMessage',data=payload,method='POST')
    with urllib.request.urlopen(req,timeout=20) as r:
        result=json.loads(r.read().decode('utf-8'))
    if not result.get('ok'): raise RuntimeError(f'Telegram send failed: {result}')


def load_state() -> dict:
    if not STATE_PATH.exists(): return {}
    try: return json.loads(STATE_PATH.read_text(encoding='utf-8'))
    except Exception: return {}


def save_state(state: dict):
    STATE_PATH.parent.mkdir(parents=True,exist_ok=True)
    state['updated_at_utc']=datetime.now(timezone.utc).isoformat()
    STATE_PATH.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def fmt(v):
    return '확인 불가' if v is None else f'{v:+.1f}%'


def market_verdict(d2: float, d10: float, d30: float) -> tuple[str,str]:
    avg_long=(d10+d30)/2
    if d2 <= -5 and avg_long >= 0:
        return ('연준 추가긴축 기대 약화·장기금리 부담 유지', '2년물은 내려갔지만 10·30년물은 버텨 재정·유가·국채 공급 등 장기 요인의 부담이 남은 패턴입니다.')
    if d2 <= -5 and avg_long > d2 + 4:
        return ('연준 추가긴축 기대 약화·장기금리는 상대적으로 덜 하락', '물가 발표는 단기 정책금리를 낮추는 방향이지만 장기 위험보상은 충분히 내려오지 않은 패턴입니다.')
    if d2 >= 5 and avg_long >= 5 and abs(avg_long-d2) <= 3:
        return ('정책금리 기대와 장기금리 위험 동반 상승', '연준 추가긴축 기대와 장기 물가·재정 위험이 함께 커지는 패턴입니다.')
    if d2 >= 5 and d2 >= avg_long + 4:
        return ('연준 추가긴축 기대 강화 — 2년물 재가격 주도', '장기물보다 2년물이 더 많이 올라 시장이 연준 정책경로를 우선 재가격한 패턴입니다.')
    if abs(d2) < 5 and avg_long >= 5:
        return ('연준 기대 변화는 제한적·장기금리 상승 압력 우세', '물가 발표보다 재정·국채 공급·유가 같은 장기 요인이 금리를 더 밀어올린 패턴입니다.')
    if abs(d2) < 5 and abs(avg_long) < 5:
        return ('정책경로 재가격 제한적', '2년물과 장기물 모두 움직임이 작아 시장이 이번 발표로 연준 경로를 크게 바꾸지 않은 패턴입니다.')
    return ('혼합 반응 — 단기 정책 기대와 장기 위험 분리 확인 필요', '2년물과 장기물이 한 방향으로 명확하게 정렬되지 않아 다음 공식 종가까지 확인이 필요합니다.')


def build_message(event: dict, row: dict, prev: dict) -> str:
    d2=(row['2y']-prev['2y'])*100; d10=(row['10y']-prev['10y'])*100; d30=(row['30y']-prev['30y'])*100
    s210=(row['10y']-row['2y'])*100; ps210=(prev['10y']-prev['2y'])*100
    s230=(row['30y']-row['2y'])*100; ps230=(prev['30y']-prev['2y'])*100
    verdict, detail=market_verdict(d2,d10,d30)
    lines=[
        f"<b>[Warsh 물가 발표 후 정책 재가격] {html.escape(event['period_label'])}</b>",
        f"공식 발표일 {event['release_date']} · 미 재무부 공식 종가 {row['date']}", '',
        '<b>물가 발표</b>',
        f"• 종합 전월 대비 {fmt(event.get('headline_mom'))} · 전년 대비 {fmt(event.get('headline_yoy'))}",
        f"• 근원 전월 대비 {fmt(event.get('core_mom'))} · 전년 대비 {fmt(event.get('core_yoy'))}", '',
        '<b>채권시장 반응</b>',
        f"• 2년물 {prev['2y']:.2f}% → {row['2y']:.2f}% ({d2:+.1f}bp)",
        f"• 10년물 {prev['10y']:.2f}% → {row['10y']:.2f}% ({d10:+.1f}bp)",
        f"• 30년물 {prev['30y']:.2f}% → {row['30y']:.2f}% ({d30:+.1f}bp)",
        f"• 2년-10년 금리차 {s210:+.0f}bp ({s210-ps210:+.1f}bp)",
        f"• 2년-30년 금리차 {s230:+.0f}bp ({s230-ps230:+.1f}bp)", '',
        f"<b>판정: {html.escape(verdict)}</b>",
        f"• {html.escape(detail)}",
    ]
    if event['kind']=='PPI':
        lines += ['• PPI는 연준의 2% 목표지표가 아니므로 PPI 하나만으로 물가 2% 경로를 확정하지 않습니다. CPI·PCE와 함께 봅니다.']
    else:
        lines += ['• CPI는 소비자물가 방향을 보여주지만 연준의 2% 목표 판단은 PCE와 함께 확인합니다.']
    lines += ['', '<b>원천</b>', f"{link('BLS 공식 물가보고서',event['url'])} · {link('미 재무부 공식 금리',TREASURY_TEXT_URL)}", '※ 1bp = 0.01%포인트']
    return '\n'.join(lines)


def main():
    state=load_state(); first=not bool(state)
    ppi=parse_ppi(); cpi=parse_cpi(); snapshots={'PPI':ppi,'CPI':cpi}
    last_seen=state.get('last_seen',{})
    pending=state.get('pending_events',[])
    processed=set(state.get('processed_events',[]))
    today_et=datetime.now(ZoneInfo('America/New_York')).date().isoformat()

    known={x.get('key') for x in pending}
    for kind,snap in snapshots.items():
        key=f"{kind}:{snap['period']}"
        is_new=last_seen.get(kind) not in (None,snap['period'])
        fresh_bootstrap=first and snap.get('release_date')==today_et
        if (is_new or fresh_bootstrap) and key not in known and key not in processed:
            pending.append({'key':key,**snap}); known.add(key)
        last_seen[kind]=snap['period']

    rows=treasury_rows(); by_date={r['date']:i for i,r in enumerate(rows)}
    keep=[]; integrated_date=state.get('last_integrated_market_date')
    sent=[]
    for event in pending:
        release_date=event.get('release_date')
        idx=by_date.get(release_date)
        if idx is None or idx==0:
            keep.append(event); continue
        row=rows[idx]; prev=rows[idx-1]
        if FORCE_NOTIFY or event['key'] not in processed:
            send(build_message(event,row,prev))
            processed.add(event['key']); sent.append(event['key']); integrated_date=row['date']
        else:
            processed.add(event['key'])

    save_state({'last_seen':last_seen,'pending_events':keep,'processed_events':sorted(processed)[-24:],
                'last_integrated_market_date':integrated_date,'latest_ppi':ppi,'latest_cpi':cpi})
    print(json.dumps({'first_run':first,'sent':sent,'pending':[e['key'] for e in keep],
                      'latest_ppi':ppi['period'],'latest_cpi':cpi['period'],
                      'treasury_latest':rows[-1]['date'],'last_integrated_market_date':integrated_date},ensure_ascii=False))


if __name__=='__main__': main()
