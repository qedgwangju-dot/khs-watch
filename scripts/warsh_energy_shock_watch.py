#!/usr/bin/env python3
"""Warsh/Fed energy-shock watcher.

Separates two very different paths when oil surges:
1) second-round inflation pass-through -> tighter-policy case;
2) real-income/demand destruction -> 2008-style over-tightening risk.

The alert is intentionally conditional and does not equate a high oil price with an
automatic rate hike. It follows the framework laid out by Vice Chair Jefferson on
2026-07-16 and combines oil, inflation expectations, PCE trend, consumption,
employment and credit.
"""
import csv
import html
import io
import json
import math
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
STATE_PATH=ROOT/'data/warsh_energy_shock_watch_state.json'
PCE_STATE=ROOT/'data/warsh_pce_trend_watch_state.json'
CRED_STATE=ROOT/'data/warsh_credibility_pretightening_watch_state.json'
CREDIT_STATE=ROOT/'data/warsh_new_axes_watch_state.json'
POLICY_STATE=ROOT/'data/warsh_policy_path_watch_state.json'
TOKEN=(os.getenv('TELEGRAM_BOT_TOKEN') or '').strip()
CHAT_ID=(os.getenv('TELEGRAM_CHAT_ID') or '').strip()
EXPECTED_BOT=(os.getenv('EXPECTED_BOT_USERNAME') or 'khs8879887988798879_bot').strip().lstrip('@')
FORCE_NOTIFY=os.getenv('FORCE_NOTIFY','0')=='1'
BRENT_LEVEL=float(os.getenv('WARSH_ENERGY_BRENT_USD','100'))
BRENT_20D_PCT=float(os.getenv('WARSH_ENERGY_20D_PCT','15'))
OIL10Y_CORR_WARN=float(os.getenv('WARSH_OIL10Y_CORR_WARN','0.50'))
OIL10Y_CORR_STRONG=float(os.getenv('WARSH_OIL10Y_CORR_STRONG','0.60'))
OIL10Y_BETA_ALERT=float(os.getenv('WARSH_OIL10Y_BETA_BP_PER_1PCT','1.0'))
OIL10Y_LOOKBACK=max(40,int(os.getenv('WARSH_OIL10Y_LOOKBACK','63')))
OIL10Y_MOVE_DAYS=max(1,int(os.getenv('WARSH_OIL10Y_MOVE_DAYS','5')))
UA='Mozilla/5.0 (compatible; khs-watch/1.0; +https://github.com/qedgwangju-dot/khs-watch)'

YAHOO_CHART='https://query1.finance.yahoo.com/v8/finance/chart/{}?range=6mo&interval=1d&includePrePost=false'
FRED_CSV='https://fred.stlouisfed.org/graph/fredgraph.csv?id={}'
JEFFERSON_URL='https://www.federalreserve.gov/newsevents/speech/jefferson20260716a.htm'
BRENT_PAGE='https://finance.yahoo.com/quote/BZ=F/'
FRED_BRENT='https://fred.stlouisfed.org/series/DCOILBRENTEU'
FRED_BEI='https://fred.stlouisfed.org/series/T5YIE'
FRED_REAL_PCE='https://fred.stlouisfed.org/series/PCEC96'
WTI_PAGE='https://finance.yahoo.com/quote/CL=F/'
FRED_DGS10='https://fred.stlouisfed.org/series/DGS10'
CBOE_OIL_RATES='https://www.cboe.com/insights/posts/week-of-9-21-2026-oil-rates-correlation-jumps-to-a-35-year-high'


def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept-Language':'en-US,en;q=0.9'})
    with urllib.request.urlopen(req,timeout=25) as r:
        return r.read().decode('utf-8',errors='replace')


def load_json(path):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except Exception:return {}


def save_json(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    obj['updated_at_utc']=datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def fred_series(series):
    raw=fetch(FRED_CSV.format(series)); out=[]
    for r in csv.DictReader(io.StringIO(raw)):
        v=r.get(series)
        if not v or v=='.':continue
        try:out.append((r['observation_date'],float(v)))
        except Exception:pass
    if len(out)<5:raise RuntimeError(f'FRED {series} unavailable')
    return out


def yahoo_series(symbol):
    url=YAHOO_CHART.format(urllib.parse.quote(symbol,safe=''))
    d=json.loads(fetch(url)); result=((d.get('chart') or {}).get('result') or [None])[0]
    if not result:raise RuntimeError('Yahoo chart unavailable')
    ts=result.get('timestamp') or []
    quote=((result.get('indicators') or {}).get('quote') or [{}])[0]
    closes=quote.get('close') or []
    highs=quote.get('high') or []
    lows=quote.get('low') or []
    meta=result.get('meta') or {}
    rows=[]
    for i,(t,c) in enumerate(zip(ts,closes)):
        if c is None:continue
        h=highs[i] if i<len(highs) else None
        l=lows[i] if i<len(lows) else None
        rows.append({
            'date':datetime.fromtimestamp(t,timezone.utc).date().isoformat(),
            'close':float(c),
            'high':float(h) if h is not None else None,
            'low':float(l) if l is not None else None,
        })
    if len(rows)<21:raise RuntimeError('Brent history too short')
    return rows,meta


def brent_snapshot():
    # 이 거시 경보는 장중 틱이 아니라 '완료된 일봉 종가'만 사용합니다.
    # 현재 뉴욕 날짜의 BZ=F 일봉은 세션 진행 중 값일 수 있으므로 판정에서 제외합니다.
    rows,meta=yahoo_series('BZ=F')
    ny_today=datetime.now(ZoneInfo('America/New_York')).date().isoformat()
    completed=[r for r in rows if r['date'] < ny_today]
    if len(completed)<21:
        raise RuntimeError('Brent completed-session history too short')

    latest_row=completed[-1]
    latest_date=latest_row['date']
    latest=float(latest_row['close'])
    d20=(latest/float(completed[-21]['close'])-1)*100
    last3=[float(x['close']) for x in completed[-3:]]

    # 완료 일봉 내부 일관성 검사. 종가가 고가/저가 범위를 벗어나면 사용하지 않습니다.
    lo=latest_row.get('low'); hi=latest_row.get('high')
    if lo is not None and hi is not None and not (float(lo)*0.999 <= latest <= float(hi)*1.001):
        raise RuntimeError(f'Brent completed close outside candle range: close={latest} range={lo}-{hi}')

    active=(all(x>=BRENT_LEVEL for x in last3) or d20>=BRENT_20D_PCT)
    return {
        'date':latest_date,'value':latest,'d20_pct':d20,'last3':last3,'active':active,
        'source':'Yahoo Finance 브렌트 선물 완료 일봉','url':BRENT_PAGE,
        'live':False,'quality_note':'현재 진행 중 일봉 제외 · 최근 완료 거래일 종가 기준',
        'measurement_basis':'최근 완료 거래일 종가'
    }

def _pearson(xs,ys):
    if len(xs)!=len(ys) or len(xs)<3:return None
    mx=sum(xs)/len(xs); my=sum(ys)/len(ys)
    vx=sum((x-mx)**2 for x in xs); vy=sum((y-my)**2 for y in ys)
    if vx<=0 or vy<=0:return None
    return sum((x-mx)*(y-my) for x,y in zip(xs,ys))/math.sqrt(vx*vy)


def _slope(xs,ys):
    if len(xs)!=len(ys) or len(xs)<3:return None
    mx=sum(xs)/len(xs); my=sum(ys)/len(ys)
    den=sum((x-mx)**2 for x in xs)
    if den<=0:return None
    return sum((x-mx)*(y-my) for x,y in zip(xs,ys))/den


def oil_rates_snapshot():
    # Cboe의 2026-09-21 자료는 'WTI 가격 ↔ 미국 10년물 금리' 3개월 이동상관을 제시했습니다.
    # 여기서는 동일 개념을 실시간 감시에 맞게 자체 재계산합니다:
    # ① 완료된 WTI 선물 일봉 수준 vs FRED DGS10 수준의 최근 63개 공통 거래일 상관
    # ② 같은 공통 거래일의 WTI 일간 %변화 1%당 DGS10 일간 변화(bp) 회귀 민감도.
    rows,_=yahoo_series('CL=F')
    ny_today=datetime.now(ZoneInfo('America/New_York')).date().isoformat()
    wti={r['date']:float(r['close']) for r in rows if r['date'] < ny_today}
    d10={d:float(v) for d,v in fred_series('DGS10')}
    dates=sorted(set(wti).intersection(d10))
    if len(dates)<OIL10Y_LOOKBACK:
        raise RuntimeError(f'WTI-DGS10 aligned history too short: {len(dates)} < {OIL10Y_LOOKBACK}')
    dates=dates[-OIL10Y_LOOKBACK:]
    oils=[wti[d] for d in dates]; yields=[d10[d] for d in dates]
    corr=_pearson(oils,yields)

    oil_ret=[]; y_bp=[]
    for i in range(1,len(dates)):
        if oils[i-1] <= 0:continue
        oil_ret.append((oils[i]/oils[i-1]-1)*100.0)
        y_bp.append((yields[i]-yields[i-1])*100.0)
    beta=_slope(oil_ret,y_bp)

    n=min(OIL10Y_MOVE_DAYS,len(dates)-1)
    oil_move=(oils[-1]/oils[-1-n]-1)*100.0 if oils[-1-n] > 0 else None
    y_move=(yields[-1]-yields[-1-n])*100.0
    if corr is None:
        band='확인 불가'
    elif corr>=OIL10Y_CORR_STRONG:
        band='강한 경보'
    elif corr>=OIL10Y_CORR_WARN:
        band='경계'
    else:
        band='일반'
    return {
        'date':dates[-1],'observations':len(dates),'corr_3m':corr,'corr_band':band,
        'beta_bp_per_1pct':beta,'beta_hot':bool(beta is not None and beta>=OIL10Y_BETA_ALERT),
        'wti':oils[-1],'wti_move_pct':oil_move,'dgs10':yields[-1],'dgs10_move_bp':y_move,
        'move_days':n,
        'measurement_basis':'WTI 선물 완료 일봉·FRED DGS10 공통 거래일 자체 계산',
        'wti_url':WTI_PAGE,'dgs10_url':FRED_DGS10,'cboe_url':CBOE_OIL_RATES,
    }


def policy_snapshot():
    state=load_json(POLICY_STATE)
    meetings=state.get('meetings') or []
    cls=state.get('classification') or {}
    first=meetings[0] if meetings else {}
    return {
        'date':state.get('updated_at_utc'),
        'meeting_date':first.get('date'),
        'hike25_prob':first.get('hike25_prob'),
        'extra_bp':cls.get('extra_bp'),
        'verdict':cls.get('verdict'),
        'source':state.get('source'),
        'source_status':state.get('source_status'),
    }


def oil_rates_verdict(orate,policy):
    corr=orate.get('corr_3m')
    oil=orate.get('wti_move_pct')
    yld=orate.get('dgs10_move_bp')
    prob=policy.get('hike25_prob')
    if corr is None:
        return '유가·10년물 연결 확인 불가'
    if oil is not None and yld is not None and oil < 0 and yld > 0:
        return '유가와 10년물 분리 — 재정·실질금리·기간프리미엄 등 비유가 요인 우세'
    aligned_up=(oil is not None and yld is not None and oil > 0 and yld > 0)
    policy_hawk=(prob is not None and float(prob) >= 60.0)
    if corr>=OIL10Y_CORR_STRONG and aligned_up and policy_hawk:
        if orate.get('beta_hot'):
            return '유가발 긴축 강경보 — 상관·민감도·시장 추가인상 기대 동시 확인'
        return '유가발 긴축 강경보 — 상관·방향·시장 추가인상 기대 동시 확인'
    if corr>=OIL10Y_CORR_STRONG and aligned_up:
        return '유가발 금리 전이 강함 — 추가인상 기대 동반 여부 확인'
    if corr>=OIL10Y_CORR_WARN:
        return '유가·장기금리 연결 경계 — 단순 동행인지 정책 전이인지 확인'
    return '유가·장기금리 상관 일반 범위'


def macro_snapshot():
    pce=load_json(PCE_STATE); cred=load_json(CRED_STATE); credit=load_json(CREDIT_STATE)
    real=fred_series('PCEC96')
    real3=((real[-1][1]/real[-4][1])**4-1)*100 if real[-4][1]>0 else None
    bei=fred_series('T5YIE')
    bei10bp=(bei[-1][1]-bei[-11][1])*100 if len(bei)>=11 else None
    macro=(cred.get('macro') or {})
    h8=(credit.get('h8') or {}).get('regime')
    sloos=(credit.get('sloos') or {}).get('regime')
    return {
        'core_3m_ann':pce.get('core_3m_ann'),'core_6m_ann':pce.get('core_6m_ann'),'core_yoy':pce.get('core_yoy'),
        'employment_soft':bool(macro.get('employment_soft')),'payroll_change_k':macro.get('payroll_change_k'),
        'unemployment_rate':macro.get('unemployment_rate'),'h8':h8,'sloos':sloos,
        'real_pce_3m_ann':real3,'real_pce_date':real[-1][0],
        'bei5y':bei[-1][1],'bei5y_10d_bp':bei10bp,'bei_date':bei[-1][0],
    }


def verdict(br,ma):
    if not br['active']:
        return '에너지 충격 경보 기준 미충족'
    pass_score=0; demand_score=0
    if ma.get('core_3m_ann') is not None and ma['core_3m_ann']>=3.0:pass_score+=1
    if ma.get('core_yoy') is not None and ma['core_yoy']>=3.0:pass_score+=1
    if ma.get('bei5y_10d_bp') is not None and ma['bei5y_10d_bp']>=20:pass_score+=1
    if ma.get('real_pce_3m_ann') is not None and ma['real_pce_3m_ann']<=1.0:demand_score+=1
    if ma.get('employment_soft'):demand_score+=1
    if ma.get('h8')=='신용 긴축' or ma.get('sloos')=='신용 긴축':demand_score+=1
    if pass_score>=2 and demand_score>=2:return '스태그플레이션형 충돌 — 물가 전이와 수요 약화가 동시에 진행'
    if pass_score>=2 and demand_score<=1:return '2차 물가 전이 우세 — 추가긴축 논리 강화'
    if demand_score>=2 and pass_score<=1:return '수요 파괴 우세 — 추가인상 시 2008형 과잉긴축 위험'
    return '판정 유보 — 유가 충격은 크지만 물가 전이와 수요 파괴의 우열 불명확'


def get_bot_username():
    with urllib.request.urlopen(f'https://api.telegram.org/bot{TOKEN}/getMe',timeout=20) as r:
        d=json.loads(r.read().decode())
    return str((d.get('result') or {}).get('username') or '')


def link(label,url):return f'<a href="{html.escape(url,quote=True)}">{html.escape(label)}</a>'

def send(text):
    if not TOKEN or not CHAT_ID:raise RuntimeError('Telegram token/chat id missing')
    u=get_bot_username()
    if u.lower()!=EXPECTED_BOT.lower():raise RuntimeError(f'Wrong Telegram bot: expected @{EXPECTED_BOT}, got @{u}')
    data=urllib.parse.urlencode({'chat_id':CHAT_ID,'text':text[:4090],'parse_mode':'HTML','disable_web_page_preview':'true'}).encode()
    req=urllib.request.Request(f'https://api.telegram.org/bot{TOKEN}/sendMessage',data=data,method='POST')
    with urllib.request.urlopen(req,timeout=20) as r:
        out=json.loads(r.read().decode())
    if not out.get('ok'):raise RuntimeError(f'Telegram send failed: {out}')
    return (out.get('result') or {}).get('message_id')


def message(br,ma,v,orate,policy,oil_v):
    pce3='확인 불가' if ma.get('core_3m_ann') is None else f"{ma['core_3m_ann']:.2f}%"
    pce6='확인 불가' if ma.get('core_6m_ann') is None else f"{ma['core_6m_ann']:.2f}%"
    real='확인 불가' if ma.get('real_pce_3m_ann') is None else f"{ma['real_pce_3m_ann']:+.1f}%"
    bei='확인 불가' if ma.get('bei5y_10d_bp') is None else f"{ma['bei5y_10d_bp']:+.0f}bp"
    emp='약화' if ma.get('employment_soft') else '급랭 미확인'
    corr='확인 불가' if orate.get('corr_3m') is None else f"{orate['corr_3m']*100:.1f}%"
    beta='확인 불가' if orate.get('beta_bp_per_1pct') is None else f"{orate['beta_bp_per_1pct']:+.2f}bp"
    wti_move='확인 불가' if orate.get('wti_move_pct') is None else f"{orate['wti_move_pct']:+.1f}%"
    y10_move='확인 불가' if orate.get('dgs10_move_bp') is None else f"{orate['dgs10_move_bp']:+.0f}bp"
    hike_prob='확인 불가' if policy.get('hike25_prob') is None else f"{float(policy['hike25_prob']):.0f}%"
    extra_bp='확인 불가' if policy.get('extra_bp') is None else f"{float(policy['extra_bp']):+.1f}bp"

    if '분리' in oil_v:
        rate_read='최근 10년물 상승은 유가보다 비유가 요인 우세'
    elif '강경보' in oil_v:
        rate_read='유가 상승이 장기금리·추가인상 기대로 전이되는 신호'
    elif '전이 강함' in oil_v:
        rate_read='유가와 장기금리의 동행이 강해지는 구간'
    else:
        rate_read=oil_v

    if '2차 물가 전이 우세' in v:
        energy_read='고유가의 2차 물가 전이 압력 유지'
    elif '수요 파괴 우세' in v:
        energy_read='고유가보다 수요 둔화·과잉긴축 위험 우세'
    elif '스태그플레이션형' in v:
        energy_read='물가 전이와 수요 약화가 동시에 진행'
    else:
        energy_read=v

    policy_read=policy.get('verdict') or '금리경로 확인 필요'
    return '\n'.join([
        '<b>[Warsh | 유가 → 금리 → 추가인상]</b>',
        f"기준 {br['date']} · 완료 종가 기준",
        '',
        '<b>한눈에 보기</b>',
        f"• <b>에너지</b> | 브렌트 {br['value']:.2f}달러 · 20일 {br['d20_pct']:+.1f}% → {html.escape(energy_read)}",
        f"• <b>금리</b> | WTI 5일 {wti_move} vs 10년물 {y10_move} → {html.escape(rate_read)}",
        f"• <b>Fed</b> | 다음 회의 +25bp {hike_prob} · 연말 {extra_bp} → {html.escape(policy_read)}",
        '',
        '<b>핵심 숫자</b>',
        f"• 유가 | Brent {br['value']:.2f}달러 ({br['d20_pct']:+.1f}%/20일) · WTI {orate['wti']:.2f}달러 ({wti_move}/5일)",
        f"• 금리 | 미국 10년물 {orate['dgs10']:.2f}% ({y10_move}/5일)",
        f"• 연결 | 3개월 상관 <b>{corr}</b> · WTI +1%당 10년물 {beta}",
        f"• 물가 | 근원 PCE 3개월 {pce3} · 6개월 {pce6} · 5년 기대인플레 {ma['bei5y']:.2f}% ({bei}/10일)",
        f"• 경기 | 실질소비 {real}/3개월 · 고용 {emp}" + (f" · NFP {ma['payroll_change_k']:+.0f}천명 · 실업률 {ma['unemployment_rate']:.1f}%" if ma.get('payroll_change_k') is not None and ma.get('unemployment_rate') is not None else ''),
        f"• 신용 | H.8 {ma.get('h8') or '확인 불가'} · SLOOS {ma.get('sloos') or '확인 불가'}",
        '',
        '<b>판정</b>',
        f"① 중기 연결: 3개월 상관 {corr} → {html.escape(orate.get('corr_band') or '확인 불가')}",
        f"② 단기 방향: WTI {wti_move} / 10년물 {y10_move} → {html.escape(rate_read)}",
        f"③ 정책 경로: +25bp {hike_prob} · 연말 {extra_bp} → {html.escape(policy_read)}",
        '',
        '<b>경보선</b>',
        f"• 상관 {OIL10Y_CORR_WARN*100:.0f}% = 경계 · {OIL10Y_CORR_STRONG*100:.0f}% = 강경보",
        f"• WTI +1%당 10년물 +{OIL10Y_BETA_ALERT:.1f}bp 이상 = 민감도 경보",
        '• 유가↑ + 10년물↑ + 추가인상확률↑ 동시 확인 시 → 유가발 긴축',
        '',
        '<b>한 줄 해석</b>',
        f"• {html.escape(energy_read)}. 다만 {html.escape(rate_read)}.",
        '• 상관은 인과관계가 아닙니다. Cboe의 65%는 역사적 비교 기준이고, 위 상관은 매 실행마다 63개 공통 거래일로 다시 계산합니다.',
        '',
        '<b>원천</b>',
        f"{link('Brent',BRENT_PAGE)} · {link('WTI',WTI_PAGE)} · {link('미 10년물',FRED_DGS10)} · {link('Cboe',CBOE_OIL_RATES)}",
        f"{link('5년 기대인플레',FRED_BEI)} · {link('실질소비',FRED_REAL_PCE)} · " +
        (f"{link('금리선물 경로',policy.get('source'))}" if policy.get('source') else '금리선물 경로 확인 불가'),
        f"{link('연준 Jefferson',JEFFERSON_URL)}",
    ])


def main():
    old=load_json(STATE_PATH)
    try:
        br=brent_snapshot()
    except Exception as exc:
        # 선물 원자료 검증 실패 시 현물 등 다른 상품으로 치환해 판정하지 않습니다.
        print(json.dumps({
            'first_run':not bool(old),'sent':False,'data_valid':False,
            'error':f'{type(exc).__name__}: {exc}',
            'rule':'브렌트 선물 완료종가 확인 실패 → 기존 상태 유지·알림 금지'
        },ensure_ascii=False))
        return

    ma=macro_snapshot(); v=verdict(br,ma)
    try:
        orate=oil_rates_snapshot()
    except Exception as exc:
        print(json.dumps({
            'first_run':not bool(old),'sent':False,'oil_rates_valid':False,
            'error':f'{type(exc).__name__}: {exc}',
            'rule':'WTI-10Y 상관 계산 실패 → 기존 에너지 판정은 유지하되 유가발 긴축 신규 경보는 발송 금지'
        },ensure_ascii=False))
        orate=(old.get('oil_rates') or {})
    policy=policy_snapshot()
    oil_v=oil_rates_verdict(orate,policy) if orate else '유가·10년물 연결 확인 불가'

    new={'schema_version':5,'brent':br,'macro':ma,'verdict':v,'oil_rates':orate,'policy':policy,'oil_rates_verdict':oil_v}; first=not bool(old)
    changed=(old.get('brent',{}).get('active') not in (None,br['active']) or old.get('verdict') not in (None,v))

    old_or=(old.get('oil_rates') or {})
    if not changed and orate:
        if old.get('oil_rates_verdict') not in (None,oil_v):
            changed=True
        elif old_or.get('corr_band') not in (None,orate.get('corr_band')):
            changed=True
        elif old_or.get('beta_hot') not in (None,orate.get('beta_hot')):
            changed=True

    upgrade=bool(old) and int(old.get('schema_version') or 1)<5
    upgrade_signal=upgrade and orate and orate.get('corr_band') in ('경계','강한 경보')

    correction=False
    old_br=(old.get('brent') or {})
    if old and int(old.get('schema_version') or 1)<3:
        ov=old_br.get('value')
        old_basis=old_br.get('measurement_basis')
        if old_basis!='최근 완료 거래일 종가' or (isinstance(ov,(int,float)) and abs(float(ov)-float(br['value']))>=2.0):
            correction=True

    sent_message_id=None
    if FORCE_NOTIFY or correction or upgrade_signal or (not first and changed):
        if correction:
            oldv=old_br.get('value')
            oldtxt=f'{float(oldv):.2f}달러' if isinstance(oldv,(int,float)) else '이전값'
            correction_head='\n'.join([
                '<b>[최종 정정 · Warsh 에너지 공급충격]</b>',
                f'• 직전 {oldtxt} 값은 동일한 브렌트 선물의 완료 종가 기준이 아니어서 폐기합니다.',
                f"• 재검증 기준: {br['date']} 브렌트 선물 완료 종가 {br['value']:.2f}달러",
                '• 앞으로 이 거시 경보는 현재 진행 중 일봉·현물가격으로 대체하지 않고 브렌트 선물의 완료된 거래일 종가만 사용합니다.',
                ''
            ])
            sent_message_id=send(correction_head+message(br,ma,v,orate,policy,oil_v))
        else:
            sent_message_id=send(message(br,ma,v,orate,policy,oil_v))

    save_json(STATE_PATH,new)
    print(json.dumps({
        'first_run':first,'sent':bool(sent_message_id),'message_id':sent_message_id,
        'data_valid':True,'date':br['date'],'active':br['active'],'brent':br['value'],
        'd20_pct':br['d20_pct'],'verdict':v,'basis':br.get('measurement_basis'),
        'correction':correction,'upgrade_signal':bool(upgrade_signal),'oil_rates_verdict':oil_v,
        'oil_rates':orate,'policy':policy
    },ensure_ascii=False))

if __name__=='__main__':main()
