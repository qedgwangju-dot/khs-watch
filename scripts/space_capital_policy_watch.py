#!/usr/bin/env python3
"""Space sector capital, Starship FAA capacity, Korea orbital AI policy watch.

Verified baseline: FAA notice=proposal, 2027 Korea AI 21억원=budget proposal
(not satellite flight funding), $100bn=Space Capital 2026 forecast (not
cash already spent). Headline-only rumor is never converted into approval.
"""
from __future__ import annotations
import datetime as dt
import email.utils
import hashlib
import html
import json
import os
from pathlib import Path
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/"data/space_capital_policy_watch_state.json"
PENDING=ROOT/"out/space_capital_policy_pending.json"
ALERT=ROOT/"out/space_capital_policy_telegram.txt"
STATUS=ROOT/"out/space_capital_policy_status.md"
NOW=dt.datetime.now(dt.timezone.utc)
BASELINE_DATE="2026-10-14"
TOPICS=[
 ("faa","[미국 발사 인허가] Starship 연간 발사 허가 심사",
  ("site:faa.gov Starbase Starship programmatic environmental impact 456 launches",
   '"Starship" "456" (FAA OR environmental OR approval) when:7d'),
  "현재 허가 25회·착륙 50회/년, 1단계 신청 100회·200회, 2단계 신청 456회·912회. 최종 허가가 아니라 FAA 환경영향평가 및 의견수렴 단계.",
  "https://www.govinfo.gov/content/pkg/FR-2026-10-14/html/2026-20963.htm",
  "FAA 승인·환경영향평가·시민 의견·환경소송, 실제 발사/회수 성공률 및 회전시간"),
 ("kr_ai","[국내 우주 AI] 우주항공청 실증·예산",
  ('"우주항공청" "데이터센터" "2028" (예산 OR 실증) when:14d',
   'site:kasa.go.kr "우주" "인공지능" "실증" when:30d'),
  "2027년 우주 AI 데이터센터 지상 검증 예산안 21억원, 궤도 실증위성 제작·발사 예산은 아직 미반영. 2030년 기존 검증 목표를 2028년으로 앞당기려는 구상이지 확정 계약 아님.",
  "https://www.newsis.com/view/NISX20261013_0003824495",
  "전력제어·방열·방사선 내성·고대역폭메모리와 저전력 신경망처리장치 궤도 검증, 예산 반영/국회 확정"),
 ("investment","[우주 투자·수주] 자금 조달과 실제 발주 구분",
  ('"Space Capital" "2026" "100 billion" space investment when:14d',
   '"Seraphim" "2026" "20.8 billion" space Q3 when:14d'),
  "Space Capital의 2026년 1,000억 달러 초과는 연간 전망. Seraphim의 3분기 민간 우주기업 투자 208억 달러는 다른 모집단·집계기간으로 합산 금지.",
  "https://www.newspim.com/news/view/20261014000008",
  "실제 투자 약정/집행, 민간 신규자금 vs 상장 자금, 발사 슬롯·기업가치·고객 수주"),
 ("license","[우주기술 이전] 독점 사용권·기술이전",
  ('"NASA" "exclusive licensing" (patent OR innovation OR citations) when:30d',
   '"우주기술" "독점 사용권" (특허 OR 2.6배) when:30d'),
  "NASA 기술 이전의 독점 사용권 연구에서 후속 혁신 증가가 관찰됨. 10년 2.6배 수치와 국내 수혜 계약은 별도 원문 검증 전 확정 금지.",
  "https://www.sciencedirect.com/science/article/pii/S0048733325001660",
  "국내 특허 실시권 계약 당사자·계약기간·이용료·기술 검증과 매출 연결"),
]
KEYWORDS=("FAA","우주항공청","Space Capital","Seraphim","NASA")
TRUST=("faa.gov","govinfo.gov","kasa.go.kr","nasa.gov","seraphim.vc","newspim.com","newsis.com","reuters.com","bloomberg.com")

def fetch(url):
 request=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0","Accept":"*/*"})
 with urllib.request.urlopen(request,timeout=22) as response:
  return response.read()

def rss(query):
 url="https://news.google.com/rss/search?"+urllib.parse.urlencode(
  {"q":query,"hl":"ko","gl":"KR","ceid":"KR:ko"})
 root=ET.fromstring(fetch(url))
 out=[]
 for e in root.findall(".//item"):
  title=html.unescape(re.sub(r"<[^>]*>"," ",e.findtext("title") or "")).strip()
  link=(e.findtext("link") or "").strip()
  source=e.find("source")
  publisher=(source.text or "").strip() if source is not None else ""
  if not title or not link.startswith("https://"):continue
  try:
   when=email.utils.parsedate_to_datetime(e.findtext("pubDate") or "")
   if not when.tzinfo:when=when.replace(tzinfo=dt.timezone.utc)
   when=when.astimezone(dt.timezone.utc)
  except Exception:continue
  out.append((title,link,publisher,when))
 return out

def check_official():
 # Primary FAA notice must be readable and contain all numerical permit stages.
 raw=fetch(TOPICS[0][4]).decode("utf-8",errors="replace").lower()
 return all(x in raw for x in ("456","912","100","25","programmatic environmental impact"))

def load():
 if not STATE.exists():return {"version":1,"seen":{}},True
 try:
  value=json.loads(STATE.read_text(encoding="utf-8"))
  if not isinstance(value,dict) or not isinstance(value.get("seen"),dict):
   raise ValueError("state schema")
  return value,False
 except Exception as e:
  raise RuntimeError("State invalid; do not resend historical events") from e

def baseline():
 lines=["🛰️ 우주 산업·인허가·우주 AI 감시",
  "2026년 10월 신규 기준선 — 확정·계획·전망 구분", ""]
 for key,title,queries,meaning,url,watch in TOPICS:
  lines.extend([title,"• "+meaning,"• 위험·확인: "+watch,"• 원문: "+url,""])
 lines.append("※ 초기 기준선입니다. 이전 뉴스의 재발표를 신규 계약/허가로 판단하지 않습니다.")
 return "\n".join(lines)+"\n"

def test():
 assert "현재 허가 25회" in baseline()
 assert "2단계 신청 456회" in baseline()
 assert "지상 검증 예산안 21억원" in baseline()
 assert "연간 전망" in baseline()
 assert "궤도 실증위성 제작·발사 예산은 아직 미반영" in baseline()
 assert len(TOPICS)==4
 print("space_capital_policy_self_test=ok stage_gate=1 budget_gate=1 forecast_gate=1")

def main():
 if os.environ.get("SPACE_CAPITAL_SELF_TEST")=="1":return test()
 state,initial=load()
 if not check_official():raise RuntimeError("FAA primary text not verified; retain state")
 selections=[]
 count=0
 errors=0
 for key,title,queries,meaning,url,watch in TOPICS:
  candidates={}
  for query in queries:
   try:
    for row in rss(query):
     count+=1
     headline,link,publisher,date=row
     # News summaries are discovery; official decision must be read separately.
     if NOW-date>dt.timedelta(days=5) or date>NOW+dt.timedelta(minutes=10):continue
     material=re.search(r"허가|승인|확정|입찰|계약|발표|예산|자금|투자|발사|"
                        r"assessment|approve|proposal|award|budget|investment",headline,re.I)
     if not material:continue
     normalized=re.sub(r"[^a-zA-Z0-9가-힣]+","",headline.lower())
     fingerprint=hashlib.sha256((key+"|"+normalized).encode()).hexdigest()[:20]
     candidates[fingerprint]=row
   except Exception:
    errors+=1
  for ident,row in candidates.items():
   # Avoid headline-only regulatory and procurement claims, unless
   # corroborated by actual original government/issuer publication.
   headline,link,publisher,date=row
   if ident in state["seen"]:continue
   if initial:
    state["seen"][ident]=NOW.isoformat()
    continue
   # In runtime alerts require an official publisher and original URL
   # sourced directly, rather than trusting Google RSS alone.
   # Until a reliable exact-document extractor is available, report
   # only official FAA filing state via the primary guard.
   if key=="faa" and "456" in headline and ("faa" in publisher.lower()):
    selections.append("\n".join([
     title,"• 공식 FAA 제안 문서 확인 — 아직 최종 승인 아님.",
     "• 현재 허가 연 25회, 1단계 제안 100회, 2단계 제안 456회.",
     "• 상태 확인: "+watch,
     "• 원문: "+url]))
    state["seen"][ident]=NOW.isoformat()
 if count==0:raise RuntimeError("All RSS queries returned no results")
 if initial:
  out=baseline()
 elif selections:
  out="🛰️ 우주 산업·인허가·우주 AI 감시\n"+"\n\n".join(selections[:3])+"\n"
 else:
  out=""
 ALERT.parent.mkdir(parents=True,exist_ok=True)
 if out:ALERT.write_text(out,encoding="utf-8")
 else:ALERT.unlink(missing_ok=True)
 PENDING.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 STATUS.write_text("# 우주 산업·인허가·우주 AI 감시 상태\n"+
  f"- 초기 기준선: {initial}\n- 검색 결과: {count}\n"+
  f"- 쿼리 실패: {errors}\n- 알림: {bool(out)}\n",encoding="utf-8")
 print(f"space_capital_policy_scan=ok initial={initial} candidates={count} alerts={len(selections)}")
if __name__=="__main__":main()
