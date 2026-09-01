#!/usr/bin/env python3
import html, json, os, re, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

STATE=Path('data/warsh_credibility_pretightening_watch_state.json')
PCE_STATE=Path('data/warsh_pce_trend_watch_state.json')
TOKEN=(os.getenv('TELEGRAM_BOT_TOKEN') or '').strip(); CHAT=(os.getenv('TELEGRAM_CHAT_ID') or '').strip()
BOT=(os.getenv('EXPECTED_BOT_USERNAME') or 'khs8879887988798879_bot').lstrip('@')
FORCE=os.getenv('FORCE_NOTIFY','0')=='1'
LOOKBACK=int(os.getenv('WARSH_PRETIGHTEN_LOOKBACK') or '5')
TWOY_BP=float(os.getenv('WARSH_PRETIGHTEN_2Y_BP') or '15')
CURVE_BP=float(os.getenv('WARSH_PRETIGHTEN_CURVE_BP') or '8')
STEEP_BP=float(os.getenv('WARSH_CREDIBILITY_STEEPEN_BP') or '8')
LONG_BP=float(os.getenv('WARSH_CREDIBILITY_LONG_END_BP') or '5')
UA='Mozilla/5.0 (compatible; khs-watch/2.0)'
TREASURY='https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve'
FEDCAL='https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm'
BLS='https://api.bls.gov/publicAPI/v2/timeseries/data/'
EMP='https://www.bls.gov/news.release/empsit.htm'; CPI='https://www.bls.gov/news.release/cpi.nr0.htm'

def get(url, accept='text/html,*/*'):
    q=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':accept})
    with urllib.request.urlopen(q,timeout=30) as r:return r.read(),r.geturl()
def post(url,obj):
    q=urllib.request.Request(url,data=json.dumps(obj).encode(),headers={'User-Agent':UA,'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(q,timeout=30) as r:return json.loads(r.read().decode())
def jload(path,default):
    try:return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default
    except:return default
def jsave(obj):
    STATE.parent.mkdir(parents=True,exist_ok=True); obj['updated_at_utc']=datetime.now(timezone.utc).isoformat(); STATE.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def safe_float(v):
    try:
        s=str(v).replace(',','').strip()
        if not s or s in {'-','—','–','na','n/a','NA','N/A'}: return None
        return float(s)
    except:return None

def treasury_rows():
    y=datetime.now(timezone.utc).year
    u=f'https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value={y}'
    raw,_=get(u,'application/xml,text/xml,*/*'); root=ET.fromstring(raw); out=[]
    for p in root.findall('.//{*}properties'):
        d={'date':None,'2y':None,'10y':None,'30y':None}
        for c in list(p):
            n=c.tag.split('}')[-1]; t=(c.text or '').strip()
            if n=='NEW_DATE': d['date']=t[:10]
            elif n=='BC_2YEAR': d['2y']=safe_float(t)
            elif n=='BC_10YEAR': d['10y']=safe_float(t)
            elif n=='BC_30YEAR': d['30y']=safe_float(t)
        if d['date'] and all(d[k] is not None for k in ('2y','10y','30y')): out.append(d)
    out.sort(key=lambda x:x['date'])
    if len(out)<LOOKBACK+1: raise RuntimeError('미 재무부 금리 데이터 부족')
    return out

def spread(r,k):return (r[k]-r['2y'])*100

def bls_macro():
    y=datetime.now(timezone.utc).year; ids=['CES0000000001','LNS14000000','CUSR0000SA0L1E']
    data=post(BLS,{'seriesid':ids,'startyear':str(y-1),'endyear':str(y)})
    if data.get('status')!='REQUEST_SUCCEEDED':raise RuntimeError('BLS API 오류')
    series={}
    for s in data.get('Results',{}).get('series',[]):
        vals={}
        for r in s.get('data',[]):
            p=r.get('period',''); v=safe_float(r.get('value'))
            if re.fullmatch(r'M(0[1-9]|1[0-2])',p) and v is not None: vals[(int(r['year']),int(p[1:]))]=v
        series[s['seriesID']]=vals
    pay=series.get(ids[0],{}); un=series.get(ids[1],{}); core=series.get(ids[2],{})
    ce=sorted(set(pay)&set(un)); cc=sorted(core)
    if len(ce)<2 or len(cc)<2:raise RuntimeError('BLS 유효 시계열 부족')
    e,e0=ce[-1],ce[-2]; c,c0=cc[-1],cc[-2]
    pc=pay[e]-pay[e0]; uc=un[e]-un[e0]; cm=(core[c]/core[c0]-1)*100
    return {'employment_period':f'{e[0]}-{e[1]:02d}','payroll_change_k':pc,'unemployment_rate':un[e],'unemployment_change_pp':uc,'cpi_period':f'{c[0]}-{c[1]:02d}','core_cpi_mom':cm,'employment_soft':pc<=50 or uc>=0.2,'inflation_cooling':cm<=0.205}

def pce_ctx():
    p=jload(PCE_STATE,{}) ; cy=p.get('core_yoy'); c6=p.get('core_6m_ann')
    sticky=(isinstance(cy,(int,float)) and cy>=2.8) or (isinstance(c6,(int,float)) and c6>=3.0)
    return {'regime':p.get('regime','확인 필요'),'core_yoy':cy,'core_6m_ann':c6,'sticky':sticky}

def clean(raw):
    s=raw.decode('utf-8','replace'); s=re.sub(r'(?is)<script.*?>.*?</script>|<style.*?>.*?</style>',' ',s); s=re.sub(r'(?s)<[^>]+>',' ',s); return html.unescape(re.sub(r'\s+',' ',s))
def num(t):
    t=t.strip().replace('–','-').replace('—','-')
    if re.fullmatch(r'\d+(?:\.\d+)?',t):return float(t)
    m=re.fullmatch(r'(\d+)-(\d+)/(\d+)',t)
    if m:return float(m.group(1))+float(m.group(2))/float(m.group(3))
    m=re.fullmatch(r'(\d+)/(\d+)',t)
    if m:return float(m.group(1))/float(m.group(2))
    raise ValueError(t)
def rate_range(text):
    for pat in [r'target range for the federal funds rate (?:at|to)\s+([0-9.]+|\d+-\d+/\d+)\s+to\s+([0-9.]+|\d+-\d+/\d+)\s+percent',r'target range[^.]{0,140}?([0-9.]+|\d+-\d+/\d+)\s+to\s+([0-9.]+|\d+-\d+/\d+)\s+percent']:
        m=re.search(pat,text,re.I)
        if m:return (num(m.group(1)),num(m.group(2)))
    return None
def statements():
    raw,_=get(FEDCAL); txt=raw.decode('utf-8','replace'); found={}
    for href,ds in re.findall(r'href=["\']([^"\']*/newsevents/pressreleases/monetary(\d{8})a\.htm)["\']',txt,re.I):found[ds]=urllib.parse.urljoin(FEDCAL,href)
    if len(found)<2:raise RuntimeError('FOMC 성명 링크 부족')
    out=[]
    for ds,u in sorted(found.items())[-3:]:
        b,final=get(u); out.append({'date':f'{ds[:4]}-{ds[4:6]}-{ds[6:]}','url':final,'range':rate_range(clean(b))})
    return out

def botname():
    with urllib.request.urlopen(f'https://api.telegram.org/bot{TOKEN}/getMe',timeout=20) as r:return json.loads(r.read().decode())['result']['username']
def send(msg):
    if not TOKEN or not CHAT:raise RuntimeError('Telegram 비밀값 없음')
    if botname().lower()!=BOT.lower():raise RuntimeError('Telegram 봇 불일치')
    d=urllib.parse.urlencode({'chat_id':CHAT,'text':msg[:4090],'parse_mode':'HTML','disable_web_page_preview':'true'}).encode(); q=urllib.request.Request(f'https://api.telegram.org/bot{TOKEN}/sendMessage',data=d,method='POST')
    with urllib.request.urlopen(q,timeout=20) as r:
        x=json.loads(r.read().decode())
        if not x.get('ok'):raise RuntimeError('Telegram 전송 실패')

def pre_snapshot(rows,macro):
    a=rows[-1-LOOKBACK]; z=rows[-1]; d2=(z['2y']-a['2y'])*100; d210=spread(z,'10y')-spread(a,'10y'); d230=spread(z,'30y')-spread(a,'30y'); av=(d210+d230)/2; active=d2>=TWOY_BP and av<=-CURVE_BP
    if active and macro['employment_soft'] and macro['inflation_cooling']:v='시장이 먼저 긴축했고 경제지표도 식는 중 — 실제 추가 인상 필요성이 일부 낮아질 수 있음'
    elif active and not macro['employment_soft'] and not macro['inflation_cooling']:v='시장이 먼저 긴축했지만 고용·물가도 강함 — 실제 인상 논리는 아직 유지'
    elif active:v='시장이 먼저 긴축한 후보 — 고용·물가 추가 확인 필요'
    else:v='시장 선긴축 기준 미충족'
    return {'date':z['date'],'base_date':a['date'],'active':active,'d2_bp':d2,'d2s10s_bp':d210,'d2s30s_bp':d230,'avg_curve_bp':av,'verdict':v}
def pre_msg(s,m):
    return '\n'.join(['<b>[워시 반응함수 · 시장이 먼저 긴축했는지 감지]</b>',f"기간: {s['base_date']} → {s['date']} ({LOOKBACK}거래일)",f"미 국채 2년물: {s['d2_bp']:+.1f}bp",f"2년-10년 금리차: {s['d2s10s_bp']:+.1f}bp | 2년-30년 금리차: {s['d2s30s_bp']:+.1f}bp",'',f"고용: 비농업 고용 {m['payroll_change_k']:+.0f}천명 / 실업률 {m['unemployment_rate']:.1f}%",f"근원 소비자물가: 전월 대비 {m['core_cpi_mom']:+.2f}%",'',f"판정: <b>{html.escape(s['verdict'])}</b>",'쉽게 보면: 연준이 금리를 올리기 전에 2년물 금리가 먼저 크게 오르면 시장금리 자체가 대출·투자를 억제합니다. 이후 고용과 물가까지 식으면 실제 추가 인상 필요성이 줄 수 있습니다.','※ 1bp = 0.01%포인트','',f'<a href="{TREASURY}">미 재무부 공식 금리 원천</a> · <a href="{EMP}">미 노동부 고용 원천</a> · <a href="{CPI}">미 노동부 물가 원천</a>'])
def event_rows(rows,d):
    for i,r in enumerate(rows):
        if r['date']>=d:return (rows[i-1],r) if i else (None,None)
    return None,None
def cred_verdict(delta,b,a,m,p):
    d2=(a['2y']-b['2y'])*100; d30=(a['30y']-b['30y'])*100; d230=spread(a,'30y')-spread(b,'30y'); cooling=m['employment_soft'] and m['inflation_cooling']
    if delta>=20:
        if d230<=-5 or d2>=d30+5:return '인상 실행 + 장기금리 상대 안정 — 워시의 물가 대응 말과 행동이 일치하고 신뢰가 강화되는 패턴'
        if d30>=LONG_BP and d230>=STEEP_BP:return '금리를 올렸지만 장기금리도 더 크게 상승 — 시장이 물가·재정 위험을 아직 신뢰하지 않는 패턴'
        return '금리 인상 실행 — 장기채 반응은 혼합'
    if abs(delta)<10:
        if p['sticky'] and d30>=LONG_BP and d230>=STEEP_BP:return '높은 물가 속 동결 + 장기금리 상승·장단기 금리차 확대 — 7월형 말-행동 괴리와 신뢰 우려 재발 가능성'
        if cooling:return '동결했지만 고용·물가 둔화 확인 — 데이터에 따른 동결 근거가 있어 신뢰 훼손으로 단정하기 어려움'
        if p['sticky'] and d230<=0:return '높은 물가 속 동결이지만 장기채 반응 안정 — 시장이 설명을 일단 수용한 패턴'
        return '동결 — 물가·고용·장기채 반응 혼합'
    if delta<=-20:
        if cooling:return '금리 인하 + 고용·물가 둔화 — 완화 근거가 데이터에서 확인되는 패턴'
        if p['sticky'] and d30>=LONG_BP:return '물가 고착 속 금리 인하 + 장기금리 상승 — 정책 신뢰 부담 확대'
        return '금리 인하 — 추가 확인 필요'
    return '정책금리 변화 비정형 — 추가 확인'
def cred_msg(e,b,a,m,p):
    old=sum(e['old_range'])/2; new=sum(e['new_range'])/2; delta=(new-old)*100; d2=(a['2y']-b['2y'])*100; d10=(a['10y']-b['10y'])*100; d30=(a['30y']-b['30y'])*100; d210=spread(a,'10y')-spread(b,'10y'); d230=spread(a,'30y')-spread(b,'30y'); action='인상' if delta>=20 else ('인하' if delta<=-20 else '동결'); v=cred_verdict(delta,b,a,m,p)
    return '\n'.join(['<b>[워시 FOMC · 말과 행동 신뢰도 판정]</b>',f"FOMC: {e['date']} | 결정: <b>{action}</b>",f"정책금리 범위: {e['old_range'][0]:.2f}~{e['old_range'][1]:.2f}% → {e['new_range'][0]:.2f}~{e['new_range'][1]:.2f}%",'',f"FOMC 전후 미 국채: 2년 {d2:+.1f}bp | 10년 {d10:+.1f}bp | 30년 {d30:+.1f}bp",f"금리차 변화: 2년-10년 {d210:+.1f}bp | 2년-30년 {d230:+.1f}bp",f"물가 추세: {html.escape(str(p['regime']))}",f"고용: 비농업 고용 {m['payroll_change_k']:+.0f}천명 / 실업률 {m['unemployment_rate']:.1f}% | 근원 소비자물가 전월 대비 {m['core_cpi_mom']:+.2f}%",'',f"판정: <b>{html.escape(v)}</b>",'쉽게 보면: 인상·동결 자체보다 그 뒤 30년물과 장단기 금리차가 어떻게 움직이는지가 시장이 연준의 물가 대응을 믿는지 보여줍니다.','※ 1bp = 0.01%포인트','',f'<a href="{html.escape(e["url"],quote=True)}">연준 FOMC 공식 성명</a> · <a href="{TREASURY}">미 재무부 공식 금리 원천</a>'])
def main():
    st=jload(STATE,{}); first=not bool(st); rows=treasury_rows(); macro=bls_macro(); pce=pce_ctx(); ss=statements(); last=ss[-1]; prev=ss[-2]
    if not last['range'] or not prev['range']:raise RuntimeError('FOMC 정책금리 범위 파싱 실패')
    ps=pre_snapshot(rows,macro); oldactive=bool(st.get('pretightening_active',False)); newdate=st.get('treasury_date') not in (None,ps['date'])
    if FORCE or (newdate and ps['active'] and not oldactive):send(pre_msg(ps,macro))
    elif newdate and oldactive and not ps['active']:send('\n'.join(['<b>[워시 반응함수 · 시장 선긴축 경보 해제]</b>',f"기준일 {ps['date']}",f"최근 {LOOKBACK}거래일 2년물 {ps['d2_bp']:+.1f}bp / 금리차 평균 {ps['avg_curve_bp']:+.1f}bp",'판정: 2년물 급등과 장단기 금리차 축소가 기준 아래로 내려왔습니다. 시장이 연준 대신 긴축하는 압력은 약해졌습니다.','',f'<a href="{TREASURY}">미 재무부 공식 금리 원천</a>']))
    seen=st.get('last_seen_fomc_url'); pending=st.get('pending_fomc')
    if first:seen=last['url']
    elif last['url']!=seen:pending={'date':last['date'],'url':last['url'],'old_range':list(prev['range']),'new_range':list(last['range'])}; seen=last['url']
    done=False
    if pending:
        b,a=event_rows(rows,pending['date'])
        if b and a:send(cred_msg(pending,b,a,macro,pce)); pending=None; done=True
    jsave({'treasury_date':ps['date'],'pretightening_active':ps['active'],'pretightening':ps,'macro':macro,'pce':pce,'last_seen_fomc_url':seen,'pending_fomc':pending,'last_credibility_completed':done})
    print(json.dumps({'first_run':first,'treasury_date':ps['date'],'pretightening_active':ps['active'],'pretightening':ps,'macro':macro,'pce':pce,'latest_fomc':last['date'],'pending_fomc':pending,'credibility_done':done},ensure_ascii=False))
if __name__=='__main__':main()
