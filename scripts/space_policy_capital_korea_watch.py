#!/usr/bin/env python3
"""Four-axis space economics, FAA Starbase PEIS and Korean orbital AI watcher.

One initial evidence-labelled baseline; subsequent alerts only for newly
verifiable official milestones. It does not invent contracts or treat a
proposed launch ceiling or draft budget as completed expenditure.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/"data/space_policy_capital_korea_watch_state.json"
PENDING=ROOT/"out/space_policy_capital_korea_pending.json"
ALERT=ROOT/"out/space_policy_capital_korea_telegram.txt"
STATUS=ROOT/"out/space_policy_capital_korea_status.md"
KST=ZoneInfo("Asia/Seoul")
NOW=dt.datetime.now(dt.timezone.utc)
USER_AGENT="Mozilla/5.0 (compatible; khs-space-policy-watch/1.0)"
FAA_NOTICE="https://www.govinfo.gov/content/pkg/FR-2026-10-14/html/2026-20963.htm"
FAA_DOCKET="FAA-2026-12808"
FAA_INDEX="https://www.federalregister.gov/api/v1/documents.json"
CAPITAL_Q3="https://www.spacecapital.com/reports/space-iq-q3-2026"
CAPITAL_INDEX="https://www.spacecapital.com/reports"
NEWSIS_AI="https://www.newsis.com/view/NISX20261013_0003824495"
EDAILY_AI="https://www.edaily.co.kr/News/Read?mediaCodeNo=257&newsId=03608006645612592"
KARI_POLICY="https://www.kari.re.kr/download/viewer/1783325572235/index.html"
KASA_INDEX="https://www.kasa.go.kr/prog/plcyBrf/brief/kor/sub01_01_04/list.do"
STUDY="https://www.sciencedirect.com/science/article/pii/S0048733325001660"
SPREAD=1340.50 # Historical KRW per USD on 2026-10-14; baseline only, NEVER label live.

class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.text=[]; self.block=0; self.links=[]
    def handle_starttag(self,tag,attrs):
        if tag in ("script","style","noscript"): self.block+=1
        if tag=="a":
            href=dict(attrs).get("href","")
            if href:self.links.append(href)
    def handle_endtag(self,tag):
        if tag in ("script","style","noscript") and self.block:self.block-=1
    def handle_data(self,value):
        if not self.block and value.strip():self.text.append(value)

def fetch(url,tries=2):
    if urllib.parse.urlsplit(url).scheme!="https":raise ValueError("HTTPS required")
    err=None
    for i in range(tries):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":USER_AGENT,"Accept":"text/html,application/json,*/*"})
            with urllib.request.urlopen(req,timeout=18) as res:
                data=res.read(2000000)
            if not data:raise RuntimeError("empty source")
            return data.decode("utf-8",errors="replace")
        except (urllib.error.URLError,TimeoutError,socket.timeout,RuntimeError) as e:
            err=e
            if isinstance(e,urllib.error.HTTPError) and e.code not in (429,500,502,503,504):break
            if i+1<tries:time.sleep(i+1)
    raise RuntimeError(f"source unavailable: {type(err).__name__}")

def text_and_links(raw):
    p=TextParser();p.feed(raw)
    return html.unescape(re.sub(r"\s+"," "," ".join(p.text))).strip(),p.links

def contains(raw,*needles):
    t=text_and_links(raw)[0].lower()
    return all(x.lower() in t for x in needles)

def official_baseline(request=fetch):
    ok,errors=[],[]
    for name,url,check in (
        ("FAA 연방관보",FAA_NOTICE,("FAA-2026-12808","456","912","25")),
        ("Space Capital 3분기",CAPITAL_Q3,("$92.5 billion","$100 billion")),
        ("한국 우주 AI 실증 보도",NEWSIS_AI,("2028","21억원","2030")),
        ("한국 우주 AI 예산 교차보도",EDAILY_AI,("21억원","우주")),
    ):
        try:
            source=request(url)
            if not contains(source,*check):
                raise ValueError("Required numeric/identity markers missing")
            ok.append(name)
        except Exception as e:
            errors.append(f"{name}({type(e).__name__})")
    return ok,errors

def fresh_official_events(seen,request=fetch):
    """Only regulator/original-publisher pages can create a new event."""
    events=[]
    problems=[]
    try:
        params=urllib.parse.urlencode({"conditions[term]":FAA_DOCKET,"per_page":"15"})
        raw=request(FAA_INDEX+"?"+params)
        data=json.loads(raw)
        docs=data.get("results",[])
        if not isinstance(docs,list):raise RuntimeError("Invalid Federal Register response")
        for row in docs:
            number=row.get("document_number","")
            date=row.get("publication_date","")
            if not re.fullmatch(r"20\d{2}-\d{4,7}",number):continue
            if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}",date):continue
            if date<"2026-10-14" or number=="2026-20963":continue
            kind=str(row.get("type","")).lower()
            title=str(row.get("title",""))
            url=row.get("html_url","")
            if not url.startswith("https://www.federalregister.gov/"):continue
            if not re.search(r"Starship|SpaceX|Boca Chica",title,re.I):continue
            try:
                content=request(url)
                if not contains(content,FAA_DOCKET,"Starship"):continue
            except Exception:continue
            key="faa:official_document:"+number
            if key in seen:continue
            status=("최종 발사 허가 여부 별도 확인" if "rule" in kind else
                    "공식 절차문서 공개. 발사 증편 허가 완료 아님")
            events.append((key,
                f"[FAA 인허가] {date} 신규 공식문서 {number}\n"
                f"• {status}\n"
                f"• 확인: 스타십 최대 456회는 현재 환경영향평가 대상 상한입니다. 정식 허가와 분리해야 합니다.\n"
                f"• 조기경보: 소음·환경·지역의견, 착륙·발사장 처리능력, 인허가 일정\n"
                f"• 원문: {url}"))
    except Exception as e:
        problems.append("FAA 공식 신규자료 조회 실패: "+type(e).__name__)

    try:
        raw=request(CAPITAL_INDEX)
        _,links=text_and_links(raw)
        targets=set()
        for link in links:
            url=urllib.parse.urljoin(CAPITAL_INDEX,link)
            if (urllib.parse.urlsplit(url).hostname or "").lower() not in ("spacecapital.com","www.spacecapital.com"):
                continue
            match=re.search(r"/reports/space-iq-q([1-4])-20(2[6-9])",url,re.I)
            if not match:continue
            quarter,year=int(match.group(1)),2000+int(match.group(2))
            if year==2026 and quarter<=3:continue
            targets.add((year,quarter,url.split("?")[0]))
        for year,quarter,url in sorted(targets)[:3]:
            key=f"capital:space_iq:{year}:Q{quarter}"
            if key in seen:continue
            try:
                page=request(url)
                if not contains(page,f"Q{quarter}",str(year)):continue
            except Exception:continue
            events.append((key,
                f"[우주 투자자금] Space Capital {year}년 {quarter}분기 새 보고서\n"
                f"• 투자액은 자금조달 기준입니다. 실제 설비투자·기업매출과 섞지 않습니다.\n"
                f"• 확인: 발사체·위성·방산별 신규자금과 기존 자산 인수자금 분리\n"
                f"• 위험: IPO·대형 조달 1건에 따른 왜곡, 실적 없는 기업의 현금 소진\n"
                f"• 원문: {url}"))
    except Exception as e:
        problems.append("Space Capital 최신 보고서 조회 실패: "+type(e).__name__)

    try:
        raw=request(KASA_INDEX)
        txt,links=text_and_links(raw)
        targets={}
        for link in links:
            url=urllib.parse.urljoin(KASA_INDEX,link)
            if (urllib.parse.urlsplit(url).hostname or "").lower() not in ("kasa.go.kr","www.kasa.go.kr"):
                continue
            match=re.search(r"plcyBrfNo=(\d+)",url)
            if not match:continue
            id=int(match.group(1))
            if id<=449:continue
            targets[id]=url
        for id,url in sorted(targets.items(),reverse=True)[:8]:
            key="kasa:official_article:"+str(id)
            if key in seen:continue
            try:
                page=request(url)
                article,_=text_and_links(page)
                if not re.search(r"우주.{0,8}(AI|인공지능|데이터센터)|K-문샷",article,re.I):
                    continue
                if not re.search(r"실증|계약|예산|2028|2030|고대역폭|방열|전력제어",article):
                    continue
            except Exception:continue
            events.append((key,
                f"[국내 우주 AI] 우주항공청 신규 공식자료 {id}\n"
                f"• 단계: 공식자료 공개. 예산 확정·위성 양산·고객 수주는 문서상 계약이 있어야 확정합니다.\n"
                f"• 매출 연결: 지상검증→궤도 실증→고객 승인→위성 부품·소프트웨어 수주\n"
                f"• 병목: 방사선·발열·전력제어·우주 인증·검수 일정\n"
                f"• 원문: {url}"))
    except Exception as e:
        problems.append("우주항공청 공식 새 보도자료 조회 실패: "+type(e).__name__)
    return events,problems

def baseline():
    return "\n".join((
      "🛰️ 우주투자·발사허가·국내 우주AI 감시",
      "2026년 10월 14일 신규 감시 기준선 (1회만 송출)",
      "",
      "[발사허가] 스타십 456회는 제안, 승인 아님",
      "• FAA 현행 25회/년 → 1단계 100회 → 2단계 456회·착륙 912회(환경영향평가 대상).",
      "• FAA-2026-12808. 의견 마감 11월 30일. 정식 허가·실제 발사는 별도 검증.",
      "• 위험: 소음·환경민원, 열차폐·회수·발사장 회전시간.",
      "• 원문: "+FAA_NOTICE,
      "",
      "[투자자금] 올해 1,000억 달러 돌파는 전망",
      "• Space Capital: 3분기 누적 925억 달러(10/14 환율 기준 약 123조9,963억원).",
      "• 연간 1,000억 달러(약 134조500억원)는 예상치. 투자조달액≠실제 설비투자·매출.",
      "• 확인: 4분기 유입액·발사체/위성 투자 비중·현금 회수.",
      "• 원문: "+CAPITAL_Q3,
      "",
      "[한국 실증] 2027년 예산안 21억원",
      "• 지상 방열·전력제어 검증용. 궤도 실증위성 예산은 아직 반영되지 않음.",
      "• 2030년 기존 목표 → 2028년 조기 실증 노력(국정감사 발언). 확정 일정 아님.",
      "• HBM·저전력 NPU 위성 탑재도 검토 단계, 확정 납품처 없음.",
      "• 병목: 발열·방사선·전력·인증·실증위성 조달.",
      "• 원문: "+NEWSIS_AI,
      "• 원문: "+EDAILY_AI,
      "",
      "[우주기술 사용권] 특허 인용 2.6배는 계약 매출 아님",
      "• 독점 사용권의 파급효과를 다룬 연구는 확인되지만, 2.6배의 계산 기준은 별도 확인 필요.",
      "• 재평가 조건: 실제 사용권 계약금·사용료·사용권 갱신과 후속 제품 매출.",
      "• 원문: "+STUDY,
    )).strip()+"\n"

def read_state():
    if not STATE.exists():
        return {"version":1,"created_at":NOW.isoformat(),
                "seen":{"faa:official_document:2026-20963":NOW.isoformat(),
                        "capital:space_iq:2026:Q3":NOW.isoformat()}},True
    try:
        state=json.loads(STATE.read_text(encoding="utf-8"))
        if not isinstance(state,dict) or not isinstance(state.get("seen"),dict):
            raise ValueError("bad state")
        return state,False
    except Exception as exc:
        raise RuntimeError("중복 상태파일 손상. 초기화하지 않고 감시 중단.") from exc

def test():
    assert "승인 아님" in baseline() and "21억원" in baseline()
    assert "456회·착륙 912회" in baseline()
    assert "123조9,963억원" in baseline()
    assert "계산 기준은 별도 확인" in baseline()
    assert STATE!=PENDING and PENDING!=ALERT
    assert not any(re.search(r"확정 일정입니다",line) for line in baseline().splitlines())
    fake="<html><a href='/reports/space-iq-q4-2026'>Q4</a></html>"
    assert any("space-iq-q4-2026" in x for x in text_and_links(fake)[1])
    assert contains("FAA-2026-12808 456 912 25","456","25")
    print("space_policy_capital_korea_self_test=ok proposal_vs_permission=1 budget_draft=1 cross_category=1")
    return 0

def main():
    if len(sys.argv)==2 and sys.argv[1]=="--self-test":return test()
    state,first=read_state()
    verified,fail=official_baseline()
    # An investor brief based on scraps rather than primary sources is unsafe.
    if "FAA 연방관보" not in verified or "Space Capital 3분기" not in verified:
        raise RuntimeError("필수 FAA·Space Capital 공식 원문 조회 실패. 기존 상태·알림 보존: "+repr(fail))
    events,errors=fresh_official_events(state["seen"])
    existing=set(state["seen"])
    updates=[(key,text) for key,text in events if key not in existing]
    # Initial verified documents are historical context and must be registered
    # so the next 30-minute run cannot rediscover them as fresh approvals.
    if first:
        for key,_ in updates:state["seen"][key]=NOW.isoformat()
        updates=[]
    # Three independent latest notices in one run are one digest, not a flood.
    updates=updates[:3]
    if first:notice=baseline()
    elif updates:
        notice=("🛰️ 우주투자·발사허가·국내 우주AI 변경\n"
             +NOW.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")+"\n\n"
             +"\n\n".join(t for _,t in updates)+"\n")
    else:notice=""
    ALERT.parent.mkdir(exist_ok=True,parents=True)
    if notice:ALERT.write_text(notice,encoding="utf-8")
    else:ALERT.unlink(missing_ok=True)
    if updates:
        for key,_ in updates:state["seen"][key]=NOW.isoformat()
    if first or updates:
        state["updated_at"]=NOW.isoformat()
        PENDING.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    else:
        # No state file, no spurious commit when nothing changed.
        PENDING.unlink(missing_ok=True)
    STATUS.write_text(
        f"# 우주투자·허가·국내 우주AI 감시\n"
        f"- 기준: {NOW.astimezone(KST).isoformat()}\n"
        f"- 공식/원천 조회 성공: {len(verified)}, 실패: {len(fail)}\n"
        f"- 신규 공식 사건: {len(updates)}\n"
        f"- 새 알림: {bool(notice)}\n"
        f"- 추가 소스 접근 문제(알림 확정 불가): {', '.join(errors) or '없음'}\n",
        encoding="utf-8")
    print(f"space_policy_capital_korea_scan=ok baseline={first} official={verified} new_events={len(updates)} send={bool(notice)} errors={errors}")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
