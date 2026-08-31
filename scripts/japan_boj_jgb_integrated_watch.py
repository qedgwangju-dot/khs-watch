#!/usr/bin/env python3
from __future__ import annotations
import csv, datetime as dt, email.utils, io, json, pathlib, re, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
from pypdf import PdfReader
KST=ZoneInfo('Asia/Seoul'); UTC=dt.timezone.utc
ROOT=pathlib.Path(__file__).resolve().parents[1]
DATA=ROOT/'data'; OUT=ROOT/'out'; DATA.mkdir(parents=True,exist_ok=True); OUT.mkdir(parents=True,exist_ok=True)
STATE_PATH=DATA/'japan_boj_jgb_integrated_state.json'; PENDING_PATH=OUT/'japan_boj_jgb_integrated_pending.json'; ALERT_PATH=OUT/'japan_boj_jgb_integrated_alert.html'; TITLE_PATH=OUT/'japan_boj_jgb_integrated_title.txt'; STATUS_PATH=OUT/'japan_boj_jgb_integrated_status.md'
UA='khs-watch-japan-boj-jgb-integrated/1.0'
MOF_YIELDS='https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv'; MOF_WHATSNEW='https://www.mof.go.jp/english/public_relations/whats_new/2026jgbs.html'; BOJ_RELEASES='https://www.boj.or.jp/en/mopo/mpmdeci/mpr_2026/'; BOJ_OPINIONS='https://www.boj.or.jp/en/mopo/mpmsche_minu/opinion_2026/index.htm'; FRED='https://fred.stlouisfed.org/graph/fredgraph.csv'
TENORS=(20,30,40)
def http_get(url,timeout=30):
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Cache-Control':'no-cache'})
    with urllib.request.urlopen(req,timeout=timeout) as r:return r.read()
def text_get(url,timeout=30):return http_get(url,timeout).decode('utf-8-sig',errors='replace')
def load_state():
    try:
        x=json.loads(STATE_PATH.read_text(encoding='utf-8')); return x if isinstance(x,dict) else {}
    except Exception:return {}
def write_json(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def fnum(x):
    try:return float(str(x).strip().replace('%',''))
    except Exception:return None
def norm(x):return re.sub(r'[^a-z0-9]','',(x or '').lower())
def pct(new,old):return (new/old-1.0)*100.0
def bp(new,old):return (new-old)*100.0
def fetch_jgb_latest_two():
    rows=list(csv.reader(io.StringIO(text_get(MOF_YIELDS)))); hi=next((i for i,r in enumerate(rows[:12]) if any(norm(c)=='date' for c in r)),None)
    if hi is None: raise RuntimeError('MOF JGB CSV header not found')
    header=[c.strip() for c in rows[hi]]; nh=[norm(c) for c in header]
    def col(*cands):
        wanted={norm(c) for c in cands}
        for i,c in enumerate(nh):
            if c in wanted:return i
        raise RuntimeError(f'missing JGB column: {cands}; header={header}')
    idx={'date':col('Date'),'jgb2':col('2','2Y','2 year','2-year'),'jgb10':col('10','10Y','10 year','10-year'),'jgb20':col('20','20Y','20 year','20-year'),'jgb30':col('30','30Y','30 year','30-year'),'jgb40':col('40','40Y','40 year','40-year')}
    good=[]
    for r in rows[hi+1:]:
        if not r or len(r)<=max(idx.values()):continue
        item={'date':r[idx['date']].strip()}; ok=bool(item['date'])
        for k in ('jgb2','jgb10','jgb20','jgb30','jgb40'):
            item[k]=fnum(r[idx[k]]); ok=ok and item[k] is not None
        if ok:good.append(item)
    if len(good)<2:raise RuntimeError('MOF JGB CSV has fewer than two complete rows')
    return good[-2],good[-1]
def fetch_fred_latest_two(series):
    url=FRED+'?'+urllib.parse.urlencode({'id':series}); rows=[]
    for row in csv.DictReader(io.StringIO(text_get(url))):
        d=(row.get('DATE') or row.get('observation_date') or '').strip(); v=fnum(row.get(series))
        if d and v is not None:rows.append((d,v))
    if len(rows)<2:raise RuntimeError(f'FRED {series}: not enough observations')
    return rows[-2],rows[-1]
def absolute(base,href):return urllib.parse.urljoin(base,href)
def extract_pdf_text(url):
    raw=http_get(url,40); tmp=OUT/'_tmp_boj.pdf'; tmp.write_bytes(raw)
    try:return '\n'.join((p.extract_text() or '') for p in PdfReader(str(tmp)).pages)
    finally:
        try:tmp.unlink()
        except Exception:pass
def latest_boj_document(index_url,anchor_pattern):
    soup=BeautifulSoup(text_get(index_url),'html.parser'); pat=re.compile(anchor_pattern,re.I)
    for a in soup.find_all('a',href=True):
        label=' '.join(a.stripped_strings)
        if pat.search(label):return label,absolute(index_url,a['href'])
    return None
def parse_policy_rate(text):
    clean=re.sub(r'\s+',' ',text)
    pats=[r'uncollateralized overnight call rate(?:\s+to remain)?\s+at around\s+([0-9]+(?:\.[0-9]+)?)\s*percent',r'uncollateralized overnight call rate.*?([0-9]+(?:\.[0-9]+)?)\s*percent']
    for p in pats:
        m=re.search(p,clean,re.I)
        if m:return float(m.group(1))
    return None
def scan_boj():
    out={}; stmt=latest_boj_document(BOJ_RELEASES,r'Statement on Monetary Policy')
    if stmt:
        label,url=stmt; out['statement_label']=label; out['statement_url']=url
        try:out['policy_rate']=parse_policy_rate(extract_pdf_text(url) if url.lower().endswith('.pdf') else text_get(url))
        except Exception as e:out['statement_error']=f'{type(e).__name__}: {e}'
    op=latest_boj_document(BOJ_OPINIONS,r'Meeting on')
    if op:
        label,url=op; out['opinion_label']=label; out['opinion_url']=url
        try:
            low=re.sub(r'\s+',' ',extract_pdf_text(url) if url.lower().endswith('.pdf') else text_get(url)).lower()
            phrases=['faster than currently expected by the market','nimbly','nimble','size of rate hikes','risk of waiting','preventing an excessive rise']
            out['hawkish_hits']=[p for p in phrases if p in low]
        except Exception as e:out['opinion_error']=f'{type(e).__name__}: {e}'
    return out
@dataclass
class Auction:
    tenor:int; date:str; url:str; bids:float; accepted:float; low_yield:float; avg_yield:float
    @property
    def btc(self):return self.bids/self.accepted
    @property
    def tail_bp(self):return (self.low_yield-self.avg_yield)*100.0
def parse_auction(url,tenor):
    soup=BeautifulSoup(text_get(url),'html.parser')
    for tr in soup.find_all('tr'):
        cells=[' '.join(td.stripped_strings) for td in tr.find_all(['td','th'])]
        if not cells or not re.fullmatch(rf'{tenor}-Year',cells[0],re.I) or len(cells)<13:continue
        bids=fnum(cells[6].replace(',','')); accepted=fnum(cells[7].replace(',','')); low_y=fnum(cells[9]); avg_y=fnum(cells[12]); date=cells[2]
        if None not in (bids,accepted,low_y,avg_y):return Auction(tenor,date,url,bids,accepted,low_y,avg_y)
    raise RuntimeError(f'auction row not found tenor={tenor} url={url}')
def latest_two_auctions(tenor):
    soup=BeautifulSoup(text_get(MOF_WHATSNEW),'html.parser'); links=[]; pat=re.compile(rf'Auction Result of {tenor}-Year JGBs',re.I)
    for a in soup.find_all('a',href=True):
        label=' '.join(a.stripped_strings)
        if pat.search(label) and 'Market Special Participants' not in label:
            url=absolute(MOF_WHATSNEW,a['href'])
            if url not in links:links.append(url)
    if len(links)<2:return None
    return parse_auction(links[1],tenor),parse_auction(links[0],tenor)
def google_news_rss(query,hl='en-US',gl='US',ceid='US:en'):
    params=urllib.parse.urlencode({'q':query,'hl':hl,'gl':gl,'ceid':ceid}); root=ET.fromstring(text_get('https://news.google.com/rss/search?'+params)); out=[]
    for node in root.findall('.//item'):
        title=(node.findtext('title') or '').strip(); link=(node.findtext('link') or '').strip(); pub=(node.findtext('pubDate') or '').strip(); src=node.find('source'); source=(src.text or '').strip() if src is not None else ''
        if title and link:out.append({'title':title,'link':link,'pub':pub,'source':source})
    return out
def fresh_within(pub,hours):
    try:
        x=email.utils.parsedate_to_datetime(pub); x=x if x.tzinfo else x.replace(tzinfo=UTC); return (dt.datetime.now(UTC)-x.astimezone(UTC)).total_seconds()<=hours*3600
    except Exception:return False
def scan_news(state):
    events=[]; seen=set(state.get('news_seen') or [])
    for item in google_news_rss('個人向け国債 NISA 財務省 税制 非課税',hl='ja',gl='JP',ceid='JP:ja')[:20]:
        if not fresh_within(item['pub'],72) or item['link'] in seen:continue
        t=item['title']; s=item['source'].lower(); official=any(x in s for x in ('ministry of finance','financial services agency','財務省','金融庁')); confirmed=any(x in t for x in ('税制改正','非課税','NISA','対象','tax','exempt')); jgb=any(x in t for x in ('国債','JGB','government bond'))
        if official and confirmed and jgb:events.append({'kind':'nisa',**item})
    return events
def main():
    now=dt.datetime.now(KST); state=load_state(); first=not bool(state.get('initialized')); events=[]; errors=[]
    try:prev_jgb,cur_jgb=fetch_jgb_latest_two()
    except Exception as e:errors.append(f'JGB: {type(e).__name__}: {e}'); prev_jgb=cur_jgb=None
    try:(usd_prev_date,usd_prev),(usd_date,usd_cur)=fetch_fred_latest_two('DEXJPUS')
    except Exception as e:errors.append(f'USDJPY: {type(e).__name__}: {e}'); usd_prev_date=usd_date=''; usd_prev=usd_cur=None
    try:boj=scan_boj()
    except Exception as e:errors.append(f'BOJ: {type(e).__name__}: {e}'); boj={}
    auctions={}
    for tenor in TENORS:
        try:
            pair=latest_two_auctions(tenor)
            if pair:
                old,new=pair; auctions[str(tenor)]={'date':new.date,'url':new.url,'btc':new.btc,'tail_bp':new.tail_bp,'prev_date':old.date,'prev_btc':old.btc,'prev_tail_bp':old.tail_bp}; seen_date=((state.get('auctions') or {}).get(str(tenor)) or {}).get('date')
                if not first and new.date!=seen_date:
                    btc_drop=pct(new.btc,old.btc); tail_widen=new.tail_bp-old.tail_bp; weak=new.btc<3.0 or btc_drop<=-15.0 or (new.tail_bp>=2.5 and tail_widen>=1.0)
                    if weak:events.append({'kind':'auction','tenor':tenor,'date':new.date,'url':new.url,'btc':new.btc,'btc_drop':btc_drop,'tail_bp':new.tail_bp,'tail_widen':tail_widen})
        except Exception as e:errors.append(f'{tenor}Y auction: {type(e).__name__}: {e}')
    policy_rate=fnum(boj.get('policy_rate')); old_rate=fnum(state.get('policy_rate')); statement_url=boj.get('statement_url') or ''; old_statement=state.get('statement_url') or ''; latest_hike_date=state.get('latest_hike_date')
    if not first and statement_url and statement_url!=old_statement:
        if policy_rate is not None and old_rate is not None and policy_rate>old_rate:
            latest_hike_date=now.date().isoformat(); events.append({'kind':'boj_hike','old_rate':old_rate,'new_rate':policy_rate,'url':statement_url})
        else:pass
    hawkish_hits=boj.get('hawkish_hits') or []; opinion_url=boj.get('opinion_url') or ''; old_opinion=state.get('opinion_url') or ''
    if not first and opinion_url and opinion_url!=old_opinion and hawkish_hits:events.append({'kind':'boj_hawkish','hits':hawkish_hits,'url':opinion_url})
    streak=int(state.get('jgb10_above3_streak') or 0); last_jgb_date=state.get('jgb_source_date') or ''
    if cur_jgb:
        if cur_jgb['date']!=last_jgb_date:streak=streak+1 if cur_jgb['jgb10']>=3.0 else 0
        old_active=bool(state.get('jgb10_above3_active')); new_active=cur_jgb['jgb10']>=3.0
        if not first and streak==3 and int(state.get('jgb10_above3_streak') or 0)<3:events.append({'kind':'jgb10_persist','value':cur_jgb['jgb10'],'date':cur_jgb['date'],'url':MOF_YIELDS})
    usd_change=pct(usd_cur,usd_prev) if None not in (usd_cur,usd_prev) else None; jgb2_change=bp(cur_jgb['jgb2'],prev_jgb['jgb2']) if cur_jgb and prev_jgb else None; combo=False
    if usd_change is not None and jgb2_change is not None:
        combo=usd_change<=-2.0 and jgb2_change>=5.0; was=bool(state.get('yen_carry_combo_active'))
        if not first and combo and not was:events.append({'kind':'yen_carry_combo','usdjpy':usd_cur,'usd_change':usd_change,'jgb2':cur_jgb['jgb2'],'jgb2_change':jgb2_change,'url':MOF_YIELDS})
    critical=False
    if latest_hike_date and cur_jgb and prev_jgb and usd_change is not None:
        try:age=(now.date()-dt.date.fromisoformat(latest_hike_date)).days
        except Exception:age=999
        if 0<=age<=5:
            d10=bp(cur_jgb['jgb10'],prev_jgb['jgb10']); d30=bp(cur_jgb['jgb30'],prev_jgb['jgb30']); critical=d10>0 and d30>0 and usd_change>0
            if not first and critical and not bool(state.get('critical_abnormal_active')):events.append({'kind':'critical','d10':d10,'d30':d30,'usd_change':usd_change,'usdjpy':usd_cur,'date':cur_jgb['date'],'url':MOF_YIELDS})
    try:news_events=scan_news(state); events.extend([] if first else news_events)
    except Exception as e:errors.append(f'news: {type(e).__name__}: {e}'); news_events=[]
    seen_news=list(dict.fromkeys((state.get('news_seen') or [])+[x['link'] for x in news_events]))[-200:]
    pending={'initialized':True,'updated_at_kst':now.isoformat(timespec='seconds'),'policy_rate':policy_rate if policy_rate is not None else old_rate,'statement_url':statement_url or old_statement,'opinion_url':opinion_url or old_opinion,'latest_hike_date':latest_hike_date,'hawkish_hits':hawkish_hits,'jgb_source_date':cur_jgb['date'] if cur_jgb else last_jgb_date,'jgb10_above3_active':bool(cur_jgb and cur_jgb['jgb10']>=3.0),'jgb10_above3_streak':streak,'yen_carry_combo_active':combo,'critical_abnormal_active':critical,'jgb':cur_jgb or state.get('jgb'),'usdjpy':{'date':usd_date,'value':usd_cur,'change_pct':usd_change} if usd_cur is not None else state.get('usdjpy'),'auctions':auctions or state.get('auctions',{}),'news_seen':seen_news}
    write_json(PENDING_PATH,pending)
    status=['# 일본 BOJ·JGB·엔캐리 통합 감시','',f'- 조회시각(KST): {now.isoformat(timespec="seconds")}',f'- 최초 기준선 설정: {"예" if first else "아니오"}',f'- 신규 경보: {len(events)}건']
    if cur_jgb:status += [f"- JGB 2Y {cur_jgb['jgb2']:.3f}% / 10Y {cur_jgb['jgb10']:.3f}% / 30Y {cur_jgb['jgb30']:.3f}% / 40Y {cur_jgb['jgb40']:.3f}% ({cur_jgb['date']})",f'- 10Y 3% 연속 일수: {streak}']
    if usd_cur is not None:status.append(f'- USD/JPY {usd_cur:.3f} / 일간 {usd_change:+.2f}% ({usd_date})')
    if policy_rate is not None:status.append(f'- BOJ 정책금리 자동 추출: {policy_rate:.2f}%')
    if errors:status += ['', '## 부분 확인 불가']+[f'- {e}' for e in errors]
    STATUS_PATH.write_text('\n'.join(status)+'\n',encoding='utf-8')
    if first or not events:
        for p in (ALERT_PATH,TITLE_PATH):
            if p.exists():p.unlink()
        return 0
    import html
    esc=lambda s:html.escape(str(s)); lines=[]; priority='일반'
    for e in events:
        k=e['kind']
        if k=='critical': priority='최상'; lines += ['🚨 <b>최상위 경보: BOJ 인상 뒤 비정상 조합</b>',f"정책 긴축 이후에도 JGB 10Y {e['d10']:+.1f}bp·30Y {e['d30']:+.1f}bp 상승, USD/JPY {e['usd_change']:+.2f}%로 엔화 약세.",'의미: 금리인상보다 재정·국채수급 불안이 더 크게 평가되는지 즉시 확인 필요.']
        elif k=='boj_hike': priority='최상'; lines += [f"🔴 <b>BOJ 정책금리 인상</b>: {e['old_rate']:.2f}% → {e['new_rate']:.2f}%",f'<a href="{esc(e["url"])}">BOJ 공식 결정</a>']
        elif k=='boj_hawkish': priority='최상'; lines += [f"🔴 <b>BOJ 매파 신호 강화</b>: {', '.join(e['hits'])}",f'<a href="{esc(e["url"])}">BOJ 주요 의견</a>']
        elif k=='jgb10_persist': priority='최상'; lines += [f"🔴 <b>일본 10년 JGB 3.0% 3영업일 고착</b>: {e['value']:.3f}%",'의미: 단발성 돌파보다 일본 전체 할인율·재정부담 재평가 가능성이 커짐.']
        elif k=='auction': priority='최상'; lines += [f"🔴 <b>{e['tenor']}년 JGB 입찰 수요 급격 악화</b> ({e['date']})",f"응찰배율 {e['btc']:.2f}배 ({e['btc_drop']:+.1f}% vs 직전), 테일 {e['tail_bp']:.1f}bp ({e['tail_widen']:+.1f}bp).",f'<a href="{esc(e["url"])}">일본 재무성 입찰 결과</a>']
        elif k=='yen_carry_combo': priority='최상'; lines += ['🔴 <b>엔캐리 청산 선행조합</b>',f"USD/JPY {e['usdjpy']:.3f} (1일 {e['usd_change']:+.2f}%) + 일본 2Y {e['jgb2']:.3f}% ({e['jgb2_change']:+.1f}bp).",'의미: 엔화 강세와 엔 조달비용 상승이 동시에 진행.']
        elif k=='nisa': lines += [f"🟠 <b>개인 JGB NISA·세제 정책 공식 변화</b>: {esc(e['title'])}",f'<a href="{esc(e["link"])}">공식 원문</a>']
        lines.append('')
    current=[]
    if cur_jgb:current.append(f"JGB 2Y {cur_jgb['jgb2']:.3f}% / 10Y {cur_jgb['jgb10']:.3f}% / 30Y {cur_jgb['jgb30']:.3f}% / 40Y {cur_jgb['jgb40']:.3f}%")
    if usd_cur is not None:current.append(f'USD/JPY {usd_cur:.3f} ({usd_change:+.2f}% 일간)')
    if policy_rate is not None:current.append(f'BOJ 정책금리 {policy_rate:.2f}%')
    title=f'일본 BOJ·JGB 통합 경보 [{priority}]'; TITLE_PATH.write_text(title+'\n',encoding='utf-8'); ALERT_PATH.write_text('\n'.join(lines+['<b>현재 숫자</b>',' / '.join(current),'',f"조회: {now.strftime('%Y-%m-%d %H:%M:%S')} KST"]).strip()+'\n',encoding='utf-8'); return 0
if __name__=='__main__':raise SystemExit(main())
