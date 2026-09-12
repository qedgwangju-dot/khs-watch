#!/usr/bin/env python3
import calendar
import html
import json
import os
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

STATE_PATH = Path('data/warsh_inflation_market_watch_state.json')
BLS_API = 'https://api.bls.gov/publicAPI/v2/timeseries/data/'
PPI_URL = 'https://www.bls.gov/news.release/ppi.htm'
CPI_URL = 'https://www.bls.gov/news.release/cpi.htm'
TREASURY_TEXT_URL = 'https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve'
TOKEN = (os.getenv('TELEGRAM_BOT_TOKEN') or '').strip()
CHAT_ID = (os.getenv('TELEGRAM_CHAT_ID') or '').strip()
EXPECTED_BOT = (os.getenv('EXPECTED_BOT_USERNAME') or 'khs8879887988798879_bot').strip().lstrip('@')
FORCE_NOTIFY = os.getenv('FORCE_NOTIFY', '0') == '1'
UA = 'Mozilla/5.0 (compatible; khs-watch/1.1; +https://github.com/qedgwangju-dot/khs-watch)'

SERIES = {
    'ppi_sa': 'WPSFD4',
    'ppi_core_sa': 'WPSFD49116',
    'ppi_nsa': 'WPUFD4',
    'ppi_core_nsa': 'WPUFD49116',
    'cpi_sa': 'CUSR0000SA0',
    'cpi_core_sa': 'CUSR0000SA0L1E',
    'cpi_nsa': 'CUUR0000SA0',
    'cpi_core_nsa': 'CUUR0000SA0L1E',
}


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/xml,text/xml,*/*'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8', errors='replace')


def post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type':'application/json','User-Agent':UA}, method='POST')
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode('utf-8'))


def bls_values() -> dict[str, dict[str,float]]:
    now = datetime.now(timezone.utc)
    payload = {'seriesid': list(SERIES.values()), 'startyear': str(now.year-1), 'endyear': str(now.year)}
    data = post_json(BLS_API, payload)
    if data.get('status') != 'REQUEST_SUCCEEDED':
        raise RuntimeError(f"BLS API failed: {data.get('message')}")
    reverse = {v:k for k,v in SERIES.items()}
    out = {k:{} for k in SERIES}
    for s in data.get('Results',{}).get('series',[]):
        key = reverse.get(s.get('seriesID'))
        if not key: continue
        for obs in s.get('data',[]):
            p = str(obs.get('period') or '')
            if not p.startswith('M') or p == 'M13': continue
            try:
                period = f"{int(obs['year']):04d}-{int(p[1:]):02d}"
                out[key][period] = float(obs['value'])
            except Exception:
                continue
    return out


def pct(a, b):
    return round((a/b - 1.0) * 100.0, 1)


def prev_period(period: str, months: int=1) -> str:
    y,m = map(int, period.split('-'))
    idx = y*12 + (m-1) - months
    return f'{idx//12:04d}-{idx%12+1:02d}'


def snapshot(kind: str, vals: dict[str,dict[str,float]]) -> dict:
    if kind == 'PPI':
        sa, core_sa, nsa, core_nsa = 'ppi_sa','ppi_core_sa','ppi_nsa','ppi_core_nsa'
        url = PPI_URL
    else:
        sa, core_sa, nsa, core_nsa = 'cpi_sa','cpi_core_sa','cpi_nsa','cpi_core_nsa'
        url = CPI_URL
    common = sorted(set(vals[sa]) & set(vals[core_sa]) & set(vals[nsa]) & set(vals[core_nsa]))
    if not common: raise RuntimeError(f'BLS {kind} common period not found')
    period = common[-1]
    pm = prev_period(period,1); py = prev_period(period,12)
    needed = [(sa,pm),(core_sa,pm),(nsa,py),(core_nsa,py)]
    if any(p not in vals[k] for k,p in needed): raise RuntimeError(f'BLS {kind} comparison period missing')
    m = int(period[-2:])
    return {
        'kind': kind,
        'period': period,
        'period_label': f'{m}월 {kind}',
        'url': url,
        'headline_mom': pct(vals[sa][period], vals[sa][pm]),
        'headline_yoy': pct(vals[nsa][period], vals[nsa][py]),
        'core_mom': pct(vals[core_sa][period], vals[core_sa][pm]),
        'core_yoy': pct(vals[core_nsa][period], vals[core_nsa][py]),
    }


def treasury_url(year: int) -> str:
    return ('https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml'
            f'?data=daily_treasury_yield_curve&field_tdr_date_value={year}')


def treasury_rows() -> list[dict]:
    year = datetime.now(timezone.utc).year
    raw = fetch(treasury_url(year))
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


def annualized(mom):
    if mom is None: return None
    return ((1.0 + float(mom)/100.0) ** 12 - 1.0) * 100.0


def inflation_speed_text(event: dict) -> str:
    core=event.get('core_mom'); head=event.get('headline_mom')
    if core is None: return '월간 물가 속도 확인 필요'
    if core >= 0.3:
        return f"근원 월간 {core:+.1f}%는 2% 물가목표와 맞는 속도보다 높습니다. 이 속도가 12개월 반복된다고 단순 가정하면 연율 약 {annualized(core):.1f}%입니다."
    if core <= 0.2:
        return f"근원 월간 {core:+.1f}%는 2% 물가목표에 가까워지는 쪽입니다. 다만 한 달 수치만으로 추세 전환을 확정하지 않습니다."
    return f"근원 월간 {core:+.1f}%는 2% 목표와 완전히 일치한다고 보기에는 아직 애매한 구간입니다."


def market_verdict(d2: float, d10: float, d30: float) -> tuple[str,str]:
    avg_long=(d10+d30)/2
    if d2 <= -5 and avg_long >= 0:
        return ('연준 추가긴축 기대 약화·장기금리 부담 유지', '2년물은 내려갔지만 10·30년물은 버텨 재정·유가·국채 공급 등 장기 요인의 부담이 남은 패턴입니다.')
    if d2 <= -5 and avg_long > d2 + 4:
        return ('연준 추가긴축 기대 약화·장기금리는 상대적으로 덜 하락', '물가 발표는 단기 정책금리를 낮추는 방향이지만 장기 위험보상은 충분히 내려오지 않은 패턴입니다.')
    if d2 >= 5 and avg_long >= 5 and abs(avg_long-d2) <= 3:
        return ('정책금리 기대와 장기금리 위험 동반 상승', '연준 추가긴축 기대와 장기 물가·재정 위험이 함께 커지는 패턴입니다.')
    if d2 >= 5 and d2 >= avg_long + 4:
        return ('연준 추가긴축 기대 강화 — 2년물 재가격 주도', '2년물이 장기물보다 더 많이 올라 시장이 장기 인플레이션 공포보다 연준의 정책금리 경로를 먼저 재가격한 패턴입니다.')
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
    curve_move=((s210-ps210)+(s230-ps230))/2
    if d2 >= 5 and d2 > max(d10,d30)+3:
        market_plain='단기금리인 2년물이 장기물보다 훨씬 더 올라, 시장은 “연준이 더 오래 또는 더 많이 긴축할 수 있다”는 쪽을 우선 반영했습니다.'
    elif d2 <= -5 and d2 < min(d10,d30)-3:
        market_plain='2년물이 장기물보다 더 크게 내려, 시장은 연준의 추가긴축 가능성을 낮추는 쪽으로 우선 반영했습니다.'
    else:
        market_plain='2년물과 장기물이 함께 움직여 정책금리 기대와 장기 물가·재정 위험이 섞여 있습니다.'

    lines=[
        f"<b>[Warsh 물가 발표 후 정책 재가격] {html.escape(event['period_label'])}</b>",
        f"공식 발표일 {event['release_date']} · 미 재무부 공식 종가 {row['date']}", '',
        '<b>한눈에 보기</b>',
        f"• <b>물가</b> | 종합 {fmt(event.get('headline_mom'))} 전월 · 근원 {fmt(event.get('core_mom'))} 전월",
        f"• <b>시장</b> | 2년물 {d2:+.1f}bp · 10년물 {d10:+.1f}bp · 30년물 {d30:+.1f}bp",
        f"• <b>결론</b> | {html.escape(verdict)}", '',
        '<b>물가를 쉽게 읽으면</b>',
        f"• {html.escape(inflation_speed_text(event))}",
        f"• 전년 대비는 종합 {fmt(event.get('headline_yoy'))} · 근원 {fmt(event.get('core_yoy'))}입니다.",
    ]
    if event['kind']=='CPI' and event.get('headline_mom') is not None:
        lines.append(f"• 참고용 단순 연율: 종합 약 {annualized(event['headline_mom']):.1f}% · 근원 약 {annualized(event['core_mom']):.1f}% — 실제 전망이 아니라 현재 한 달 속도 비교용입니다.")
    lines += [
        '', '<b>채권시장이 말한 것</b>',
        f"• {html.escape(market_plain)}",
        f"• 2년-10년 금리차 {s210:+.0f}bp ({s210-ps210:+.1f}bp) · 2년-30년 금리차 {s230:+.0f}bp ({s230-ps230:+.1f}bp)",
        f"• 평균 금리차 변화 {curve_move:+.1f}bp → {'장단기 금리차 축소' if curve_move < 0 else '장단기 금리차 확대'}", '',
        '<b>Warsh 기준 해석</b>',
        f"• {html.escape(detail)}",
    ]
    if event['kind']=='PPI':
        lines += ['• 생산자물가는 연준의 2% 목표지표가 아닙니다. CPI와 PCE까지 같은 방향인지 확인해야 합니다.']
    else:
        lines += ['• CPI는 방향 확인용이고 연준의 공식 2% 목표지표는 PCE입니다. 따라서 CPI가 강해도 PCE가 식으면 최종 판단은 약해질 수 있습니다.']
    lines += [
        '', '<b>다음에 무엇을 보면 되나</b>',
        '• 다음 미 재무부 공식 종가에서 2년물 상승분이 유지되는지: 유지되면 정책경로 재가격 지속, 크게 반납하면 하루짜리 반응 가능성 증가',
        '• 다음 PCE에서 근원 월간 속도가 0.2% 안팎으로 낮아지는지와 고용이 함께 둔화하는지 확인',
        '', '<b>원천</b>', f"{link('BLS 공식 물가보고서',event['url'])} · {link('미 재무부 공식 금리',TREASURY_TEXT_URL)}", '※ 1bp = 0.01%포인트'
    ]
    return '\n'.join(lines)


def prior_month(today):
    y=today.year; m=today.month-1
    if m==0: y-=1; m=12
    return f'{y:04d}-{m:02d}'


def main():
    state=load_state(); first=not bool(state)
    vals=bls_values(); ppi=snapshot('PPI',vals); cpi=snapshot('CPI',vals); snapshots={'PPI':ppi,'CPI':cpi}
    last_seen=state.get('last_seen',{})
    pending=state.get('pending_events',[])
    processed=set(state.get('processed_events',[]))
    today_et=datetime.now(ZoneInfo('America/New_York')).date()
    expected_ref=prior_month(today_et)

    known={x.get('key') for x in pending}
    for kind,snap in snapshots.items():
        key=f"{kind}:{snap['period']}"
        is_new=last_seen.get(kind) not in (None,snap['period'])
        fresh_bootstrap=first and snap['period']==expected_ref and today_et.day<=15
        if (is_new or fresh_bootstrap) and key not in known and key not in processed:
            pending.append({'key':key,'release_date':today_et.isoformat(),**snap}); known.add(key)
        last_seen[kind]=snap['period']

    rows=treasury_rows(); by_date={r['date']:i for i,r in enumerate(rows)}
    keep=[]; integrated_date=state.get('last_integrated_market_date')
    sent=[]
    for event in pending:
        idx=by_date.get(event.get('release_date'))
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
