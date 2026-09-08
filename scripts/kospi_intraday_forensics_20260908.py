#!/usr/bin/env python3
from __future__ import annotations
import json, os, requests
from typing import Any

BASE='https://openapi.ls-sec.co.kr:8080'

def token():
    r=requests.post(BASE+'/oauth2/token',headers={'content-type':'application/x-www-form-urlencoded'},params={
        'grant_type':'client_credentials','appkey':os.environ['LS_OPENAPI_APP_KEY'],'appsecretkey':os.environ['LS_OPENAPI_APP_SECRET'],'scope':'oob'},timeout=30)
    r.raise_for_status(); return r.json()['access_token']

def post(tok,path,tr,body):
    r=requests.post(BASE+path,headers={'content-type':'application/json; charset=utf-8','authorization':'Bearer '+tok,'tr_cd':tr,'tr_cont':'N','tr_cont_key':''},data=json.dumps(body),timeout=30)
    r.raise_for_status(); d=r.json()
    if str(d.get('rsp_cd') or '') not in ('','00000','0000'): raise RuntimeError((tr,d.get('rsp_cd'),d.get('rsp_msg')))
    return d

def sec(v:Any):
    s=''.join(c for c in str(v or '') if c.isdigit())
    if len(s)>=6:s=s[:6]
    else:return None
    h,m,x=int(s[:2]),int(s[2:4]),int(s[4:6]); return h*3600+m*60+x

def series(tok,market,upcode):
    rows=[]; cts=''; seen=set()
    for _ in range(12):
        body={'t1602InBlock':{'market':market,'upcode':upcode,'gubun1':'2','gubun2':'0','cts_time':cts,'cts_idx':0,'cnt':100,'gubun3':'','exchgubun':'K'}}
        d=post(tok,'/stock/investor','t1602',body)
        page=d.get('t1602OutBlock1') or []
        if isinstance(page,dict):page=[page]
        rows += [r for r in page if isinstance(r,dict)]
        nxt=str((d.get('t1602OutBlock') or {}).get('cts_time') or '')
        if not nxt or nxt==cts or nxt in seen: break
        seen.add(nxt); cts=nxt
        if any((sec(r.get('time')) or 999999) <= 13*3600+20*60 for r in rows): break
    uniq={str(r.get('time')):r for r in rows if sec(r.get('time')) is not None}
    return sorted(uniq.values(),key=lambda r:sec(r.get('time')) or 0)

def nearest(rows,hhmm):
    h,m=map(int,hhmm.split(':')); t=h*3600+m*60
    return min(rows,key=lambda r:abs((sec(r.get('time')) or 0)-t)) if rows else None

def slim(r):
    if not r:return None
    return {'time':r.get('time'),'개인':r.get('sv_08'),'외국인':r.get('sv_17'),'기관계':r.get('sv_18'),'증권':r.get('sv_01'),'투신':r.get('sv_03'),'기금':r.get('sv_06'),'기타':r.get('sv_07'),'사모':r.get('sv_00')}

def delta(a,b):
    A=slim(a) or {}; B=slim(b) or {}; out={'from':A.get('time'),'to':B.get('time')}
    for k in ('개인','외국인','기관계','증권','투신','기금','기타','사모'):
        try: out[k]=float(B.get(k))-float(A.get(k))
        except: out[k]=None
    return out

def main():
    tok=token(); times=['13:30','13:40','13:50','14:00','14:10','14:20','14:30','14:37','14:45','15:00']
    result={}
    for name,market,upcode in [('KOSPI현물','1','001'),('KOSPI200','2','101'),('국내선물','4','900')]:
        rows=series(tok,market,upcode)
        snaps={t:nearest(rows,t) for t in times}
        result[name]={'rows':len(rows),'first':slim(rows[0]) if rows else None,'last':slim(rows[-1]) if rows else None,'snapshots':{t:slim(r) for t,r in snaps.items()},'deltas':{
            '13:50→14:10':delta(snaps['13:50'],snaps['14:10']),
            '14:10→14:30':delta(snaps['14:10'],snaps['14:30']),
            '13:50→14:37':delta(snaps['13:50'],snaps['14:37']),
            '14:30→14:45':delta(snaps['14:30'],snaps['14:45']),
            '14:37→15:00':delta(snaps['14:37'],snaps['15:00'])}}
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
