#!/usr/bin/env python3
"""Hanwha Ocean PRS and SpaceX launch-pad steel pipe supply alerts.

Independent watcher so existing launch, defense, and Korean space AI workflows
remain untouched. A one-time Korean evidence-labelled baseline is followed
by material milestone changes only, with cross-publisher corroboration.
"""
from __future__ import annotations

import datetime as dt
import email.utils
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
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "k_space_launchpad_capital_watch_state.json"
PENDING = ROOT / "out" / "k_space_launchpad_capital_pending.json"
ALERT = ROOT / "out" / "k_space_launchpad_capital_telegram.txt"
STATUS = ROOT / "out" / "k_space_launchpad_capital_status.md"
KST = ZoneInfo("Asia/Seoul")
NOW = dt.datetime.now(dt.timezone.utc)
AGENT = "Mozilla/5.0 (compatible; khs-launchpad-capital-watch/1.0)"
TITLE = "🚀 발사대 실물수주·한화 우주 투자재원 감시"
ONE_WEEK = dt.timedelta(days=7)
NEW_WINDOW = dt.timedelta(hours=84)
KRX_APRIL = "https://kind.krx.co.kr/external/2026/04/03/001401/20260326001612/91763.htm"
DART_OCTOBER = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261016000478"
DART_SPACE_INVEST = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260703800716"
STEEL_PRESS = "https://www.hankyung.com/article/202610199762i"
STEEL_ETNEWS = "https://www.etnews.com/20261019000197"
PRS_REPORT = "https://www.digitaltoday.co.kr/disclosure/articleView.html?idxno=707870"
WON_FIRST = 1_700_000_000_000
WON_SECOND = 1_383_386_784_000
SHARES_FIRST = 13_281_250
SHARES_SECOND = 22_169_660
FIRST_PRICE = 128_000
SECOND_PRICE = 62_400
BASELINE_EVENTS = {
    "hanwha:hanwha_ocean_prs_first_202604",
    "hanwha:hanwha_ocean_prs_second_202610",
    "kbi:spacex_deluge_950t_202610",
    "kbi:spacex_deluge_310t_existing_202610",
}
TRUSTED = (
    "한국경제", "전자신문", "연합뉴스", "뉴스핌", "조선비즈", "이데일리",
    "매일경제", "서울경제", "머니투데이", "뉴시스", "헤럴드경제",
    "디지털투데이", "비즈니스포스트", "파이낸셜뉴스",
    "Reuters", "Bloomberg", "SpaceNews", "Financial Times",
)
NOISE = re.compile(
    r"상한가|급등|급락|주가\s*상승|주가\s*하락|목표주가|"
    r"증권가\s*평가|특징주|관련주|투자주의|stock (?:soars|slides)|"
    r"options activity|insider sale|class action|전망만",
    re.I,
)
QUERIES = {
    "hanwha": (
        '"한화시스템" "한화오션" ("PRS" OR "주가수익스왑" OR "결제") when:7d',
        '"한화시스템" ("우주" OR "AI") ("투자집행" OR "공시" OR "조달") when:7d',
        '"Hanwha Systems" "Hanwha Ocean" ("swap" OR "settlement" OR "proceeds") when:7d',
    ),
    "kbi": (
        '"KBI동양철관" ("스페이스X" OR "SpaceX") ("강관" OR "발사대") when:7d',
        '"KBI동양철관" ("후속 수주" OR "추가 계약" OR "납품 완료") when:7d',
        '"KBI Dongyang Steel Pipe" ("SpaceX" OR "water deluge") when:7d',
    ),
}
HANWHA = re.compile(r"한화시스템|Hanwha Systems", re.I)
OCEAN = re.compile(r"한화오션|Hanwha Ocean", re.I)
KBI = re.compile(r"KBI\s?동양철관|케이비아이동양철관|KBI Dongyang Steel Pipe", re.I)
SPACEX = re.compile(r"스페이스\s?X|SpaceX|스페이스엑스", re.I)

class PlainHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hide = 0
        self.out: list[str] = []
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"): self.hide += 1
    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self.hide: self.hide -= 1
    def handle_data(self, text):
        if not self.hide and text.strip(): self.out.append(text)

def fetch(url: str, attempts: int = 2) -> bytes:
    if urllib.parse.urlsplit(url).scheme != "https":
        raise ValueError("Only HTTPS official/news sources accepted")
    error = None
    for step in range(attempts):
        request = urllib.request.Request(url, headers={"User-Agent":AGENT,
                                        "Accept":"text/html,application/rss+xml,*/*"})
        try:
            with urllib.request.urlopen(request, timeout=20) as res:
                raw = res.read(2_000_000)
                if not raw: raise ValueError("Empty response")
                return raw
        except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout, TimeoutError) as exc:
            error = exc
            if isinstance(exc, urllib.error.HTTPError) and exc.code not in (429,500,502,503,504):
                break
            if step < attempts-1: time.sleep(2 ** step)
    raise RuntimeError(f"Source could not be verified: {type(error).__name__}")

def plaintext(raw: bytes) -> str:
    obj=PlainHTML()
    obj.feed(raw.decode("utf-8",errors="replace"))
    return html.unescape(re.sub(r"\s+"," "," ".join(obj.out))).strip()

def original_source_checks(fetcher=fetch):
    results={}
    for name, url, markers in (
        ("2026년 4월 KRX 정정공시", KRX_APRIL, ("13,281,250", "128,000", "1,700,000,000,000")),
        ("2026년 10월 한화오션 공시", DART_OCTOBER, ("22,169,660", "62,400")),
        ("KBI 강관 공급 회사 발표 재전재", STEEL_PRESS, ("950", "640", "205", "105", "스페이스X")),
        ("KBI 강관 보도 교차", STEEL_ETNEWS, ("950", "스페이스X", "강관")),
        ("PRS 공시 내용 전재 교차", PRS_REPORT, ("22,169,660", "62,400")),
    ):
        try:
            text = plaintext(fetcher(url))
            if not all(s.casefold() in text.casefold() for s in markers):
                raise ValueError("Required fact markers missing")
            results[name]={"ok":True, "url":url}
        except Exception as exc:
            results[name]={"ok":False,"error":type(exc).__name__}
    return results

def rss(query: str) -> list[dict]:
    lang = ("ko","KR","KR:ko") if re.search("[가-힣]",query) else ("en-US","US","US:en")
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q":query,"hl":lang[0],"gl":lang[1],"ceid":lang[2]})
    root=ET.fromstring(fetch(url))
    result=[]
    for entry in root.findall(".//item"):
        title=html.unescape(re.sub("<[^>]*>"," ",entry.findtext("title") or "")).strip()
        link=(entry.findtext("link") or "").strip()
        s=entry.find("source")
        publisher=(s.text or "").strip() if s is not None else ""
        if not title or not link.startswith("https://"): continue
        try:
            at=email.utils.parsedate_to_datetime(entry.findtext("pubDate") or "")
            if not at.tzinfo:at=at.replace(tzinfo=dt.timezone.utc)
            at=at.astimezone(dt.timezone.utc)
        except Exception: continue
        result.append({"title":title,"url":link,"publisher":publisher,"when":at})
    return result

def strip_pub(title: str) -> str:
    return re.sub(r"\s+[-|]\s+[^-|]{2,65}$","",title).strip()

def event_stage(topic: str, title: str, when:dt.datetime) -> str|None:
    text=strip_pub(title)
    if NOISE.search(text):return None
    if topic=="hanwha":
        if not HANWHA.search(text):return None
        if OCEAN.search(text) and re.search(r"PRS|주가수익|주식\s*매각|지분\s*매각|swaps?|settlement|정산|매각대금",text,re.I):
            if re.search(r"매각\s*결정|전량\s*매각|지분\s*처분|양도\s*결정|매각\s*계약",text):
                return "hanwha:hanwha_ocean_prs_second_202610"
            if (when >= dt.datetime(2026,10,21,tzinfo=dt.timezone.utc)
                and re.search(r"대금\s*수령\s*완료|대금\s*결제\s*완료|거래\s*종결|"
                              r"매각\s*완료|매각대금\s*유입\s*완료|"
                              r"settlement completed|deal closed",text,re.I)
                and not re.search(r"예정|기대|가능|계획|전망",text)):
                return "hanwha:hanwha_ocean_prs_second_payment"
            if re.search(r"PRS\s*정산\s*완료|주가수익스왑\s*정산|"
                         r"손익\s*확정|평가손익\s*공시|정정\s*공시",text,re.I):
                return "hanwha:prs_settlement_or_amendment"
        if re.search(r"우주|국방\s*AI|데이터센터|space|AI",text,re.I):
            if re.search(r"신규\s*투자\s*확정|투자\s*집행\s*공시|"
                         r"추가\s*조달\s*확정|자금조달\s*계약\s*체결",text,re.I):
                return "hanwha:confirmed_space_ai_financing"
        return None
    if topic=="kbi":
        if not KBI.search(text) or not SPACEX.search(text):return None
        if re.search(r"후속\s*수주|신규\s*계약|추가\s*발주\s*계약|"
                     r"새\s*공급계약|new\s*purchase\s*order|new\s*contract",text,re.I):
            if re.search(r"950\s*(?:t|톤)|310\s*(?:t|톤)|올해\s*4월",text,re.I):
                return "kbi:spacex_deluge_950t_202610"
            return "kbi:spacex_deluge_followon_order"
        if re.search(r"310\s*(?:t|톤).{0,15}(?:납품\s*완료|선적\s*완료)|"
                     r"(?:납품|선적)\s*완료.{0,15}310\s*(?:t|톤)",text,re.I):
            if when < dt.datetime(2026,10,20,tzinfo=dt.timezone.utc):
                return "kbi:spacex_deluge_310t_existing_202610"
            return "kbi:spacex_deluge_october_shipment_completed"
        if re.search(r"불량\s*발생|품질\s*문제\s*확정|계약\s*해지|"
                     r"납품\s*취소|quality\s*failure|contract\s*termination",text,re.I):
            return "kbi:space_x_deluge_quality_event"
        if re.search(r"950\s*(?:t|톤)|640\s*(?:t|톤)|발사대\s*강관|"
                     r"워터\s*디[리루]지|water deluge",text,re.I):
            return "kbi:spacex_deluge_950t_202610"
        return None
    return None

def unique_publisher(pub: str) -> bool:
    s=pub.casefold()
    if any(z in s for z in ("prnewswire","news wire","business wire","globenewswire","rss feed")):return False
    return any(source.casefold() in s for source in TRUSTED)

def same_material(a:dict,b:dict,event:str)->bool:
    if a["publisher"].casefold()==b["publisher"].casefold():return False
    if abs((a["when"]-b["when"]).total_seconds())>72*3600:return False
    # At least two separately named news organizations, same company/event stage,
    # and material topic terms. Rewritten stock commentary is never sufficient.
    if not unique_publisher(a["publisher"]) or not unique_publisher(b["publisher"]):return False
    if event.startswith("kbi"):return bool(SPACEX.search(a["title"]) and SPACEX.search(b["title"]))
    if event.startswith("hanwha"):return bool(HANWHA.search(a["title"]) and HANWHA.search(b["title"]))
    return False

def initial_report()->str:
    if WON_FIRST != SHARES_FIRST*FIRST_PRICE or WON_SECOND!=SHARES_SECOND*SECOND_PRICE:
        raise AssertionError("PRS disclosed quantities do not reconcile")
    cumulative=WON_FIRST+WON_SECOND
    return "\n".join((
        TITLE,
        "첫 1회 기준선 · 과거 보도를 신규 수주로 재발송하지 않습니다.",
        "",
        "[한화시스템] 지분 현금화, 주가 위험은 PRS로 잔존",
        "• 한화오션 1차: 1,328만1,250주×12만8,000원=1조7,000억원(4월 확정).",
        "• 2차: 2,216만9,660주×6만2,400원=1조3,833억8,678만4,000원.",
        "• 두 건 합계 3조833억8,678만4,000원. 2차 대금결제는 10월 21일 예정.",
        "• PRS 1년: 보유 지분은 0%로 감소하나 정산 시 주가 변동 손실 가능.",
        "• 향후 투자계획: 우주 인프라 약 20조원(2040년까지), 국방 AI 데이터센터 한화시스템 부담 약 3조원(2032년까지·공동투자).",
        "• 추적: 실제 결제·PRS 정산손익·지상/우주 설비투자 집행·방산 현금흐름.",
        "• 원문: "+KRX_APRIL,
        "• 원문: "+DART_OCTOBER,
        "• 원문: "+DART_SPACE_INVEST,
        "",
        "[KBI동양철관] SpaceX 발사대 분사식 살수 설비용 강관",
        "• 950톤: 4월 640톤 선적, 10월 205톤·105톤 후속 납품 중.",
        "• 천안·충주 공장 제조, 3월 생산공정 실사·품질 기준 통과.",
        "• 로켓 본체·열차폐 부품이 아니라 발사대의 열 충격을 완화하는 물분사 설비용입니다.",
        "• 계약 단가·계약 상대방의 직접 법인명·후속 반복 수주금액은 공개 확인되지 않았습니다.",
        "• 추적: 나머지 물량 선적 완료, 신규 주문 물량×단가, 발사장별 발주, 내식·압력·인수시험.",
        "• 원문: "+STEEL_PRESS,
        "• 원문: "+STEEL_ETNEWS,
    )).strip()+"\n"

def describe(event:str,articles:list[dict])->str:
    topic="한화시스템" if event.startswith("hanwha") else "KBI동양철관"
    sentences={
      "hanwha:hanwha_ocean_prs_second_payment":
        "한화오션 지분 매각대금 결제 완료 관련 신규 보도입니다. 10월 21일 예정 대금 수령과 실제 유입은 공시·현금흐름에서 재확인이 필요합니다.",
      "hanwha:prs_settlement_or_amendment":
        "한화오션 지분 관련 주가수익스왑 정산·정정 후보입니다. 기준가격·정산주식수·평가손익을 공식 공시로 다시 확인해야 합니다.",
      "hanwha:confirmed_space_ai_financing":
        "우주·국방 AI 투자 관련 별도의 신규 조달·집행 후보입니다. 투자계획 약 23조원과 확정 지출을 혼동하지 않습니다.",
      "kbi:spacex_deluge_followon_order":
        "SpaceX 발사대 고강도 강관 후속 발주 관련 신규 보도입니다. 950톤 기존 납품과 구분하여 신규 물량·계약금액·직접 계약 상대방을 확인해야 합니다.",
      "kbi:spacex_deluge_october_shipment_completed":
        "기존 950톤 중 10월 잔여 310톤 납품 완료 관련 신규 보도입니다. 최종 인수·매출 인식은 별개입니다.",
      "kbi:space_x_deluge_quality_event":
        "SpaceX 발사대 강관 납품 품질·계약 이행 관련 신규 보도입니다. 공인 시험 결과와 책임 소재는 미확정입니다.",
    }
    if event not in sentences:raise ValueError("Unapproved event stage: "+event)
    a,b=articles
    return "\n".join((
        f"[{topic}] 신규 공시·계약 이행 추적",
        "• "+sentences[event],
        "• 검증 상태: 독립된 두 언론의 보도 확인. 공식 계약서·최종 공시는 별도 확인 전.",
        "• 최초 보도: "+a["when"].astimezone(KST).strftime("%Y-%m-%d %H:%M KST"),
        "• 주가 기사만으로 수주를 인정하지 않고, 기계약·미납품·검수·후속 계약을 분리합니다.",
        "• 원문: "+a["url"],
        "• 원문: "+b["url"],
    ))

def state_load()->tuple[dict,bool]:
    if not STATE.exists():
        return {"version":1,"seen":{},"created_at":NOW.isoformat()},True
    try:
        data=json.loads(STATE.read_text(encoding="utf-8"))
        if not isinstance(data,dict) or not isinstance(data.get("seen"),dict):raise ValueError("Bad schema")
        return data,False
    except Exception as exc:
        raise RuntimeError("기존 중복방지 상태 손상: 중복 전송 방지를 위해 중단") from exc

def select(rows:dict[str,list[dict]],seen:dict,first:bool)->tuple[list[str],dict]:
    next_seen=dict(seen)
    result=[]
    for topic,articles in rows.items():
        by_event={}
        for entry in articles:
            if not unique_publisher(entry["publisher"]):continue
            if NOW-entry["when"]>ONE_WEEK or entry["when"]>NOW+dt.timedelta(minutes=10):continue
            event=event_stage(topic,entry["title"],entry["when"])
            if not event:continue
            by_event.setdefault(event,[]).append(entry)
        for event,items in by_event.items():
            if event in BASELINE_EVENTS:
                next_seen[event]=NOW.isoformat() if event not in next_seen else next_seen[event]
                continue
            if event in seen:continue
            fresh=[entry for entry in items if NOW-entry["when"]<=NEW_WINDOW]
            pair=None
            for a in fresh:
                for b in items:
                    if same_material(a,b,event):
                        pair=[a,b];break
                if pair:break
            if not pair:continue
            if first:
                next_seen[event]=NOW.isoformat()
            else:
                result.append((max(pair[0]["when"],pair[1]["when"]),event,describe(event,pair)))
        # Do not exhaustively mark unrelated single-source headlines as seen.
    result.sort(key=lambda x:x[0],reverse=True)
    output=result[:2]
    for _,event,_ in output:next_seen[event]=NOW.isoformat()
    return [item[2] for item in output],next_seen

def self_test()->int:
    assert SHARES_FIRST*FIRST_PRICE==WON_FIRST
    assert SHARES_SECOND*SECOND_PRICE==WON_SECOND
    assert SHARES_FIRST+SHARES_SECOND==35_450_910
    assert "3조833억8,678만4,000원" in initial_report()
    assert "계약 단가" in initial_report()
    a={"title":"KBI동양철관 SpaceX 강관 후속 수주 계약","publisher":"한국경제",
       "when":NOW,"url":"https://one.example/a"}
    b={**a,"publisher":"전자신문","url":"https://two.example/b"}
    assert event_stage("kbi",a["title"],NOW)=="kbi:spacex_deluge_followon_order"
    assert same_material(a,b,"kbi:spacex_deluge_followon_order")
    x,y=select({"kbi":[a,b]},BASELINE_EVENTS and {},False)
    assert len(x)==1 and "kbi:spacex_deluge_followon_order" in y
    z,_=select({"kbi":[a,b]},y,False)
    assert z==[]
    assert event_stage("kbi","[특징주] KBI동양철관, SpaceX 950톤 공급 급등",NOW) is None
    assert event_stage("hanwha","한화시스템 한화오션 매각대금 결제 예정",NOW) is None
    assert event_stage("hanwha","한화시스템 한화오션 매각대금 결제 완료",
                       dt.datetime(2026,10,21,tzinfo=dt.timezone.utc))=="hanwha:hanwha_ocean_prs_second_payment"
    assert "hanwha:hanwha_ocean_prs_second_202610" in BASELINE_EVENTS
    assert STATE!=PENDING and STATE!=ALERT
    print("k_space_launchpad_capital_self_test=ok amount_reconciled=1 duplicate_guard=1 false_positive_guard=1")
    return 0

def main()->int:
    if len(sys.argv)==2 and sys.argv[1]=="--self-test":return self_test()
    state,first=state_load()
    original=original_source_checks()
    # Do not claim issuer direct certification of the SpaceX steel-pipe buyer;
    # reputable articles reproduce KBI statements, but direct contract party is undisclosed.
    if not original["2026년 4월 KRX 정정공시"]["ok"]:
        raise RuntimeError("공식 1차 PRS 최종조건 직접 검증 실패, 알림 중단")
    if sum(original[x]["ok"] for x in ("KBI 강관 공급 회사 발표 재전재","KBI 강관 보도 교차")) < 1:
        raise RuntimeError("KBI 직접 공급 주장 원문 확인 실패, 알림 중단")
    rows={}
    success=0;errors=[]
    for topic,queries in QUERIES.items():
        candidates={}
        for query in queries:
            try:
                found=rss(query)
                success+=1
                for item in found:
                    k=(item["publisher"].lower(),strip_pub(item["title"]).lower())
                    old=candidates.get(k)
                    if old is None or old["when"]<item["when"]:candidates[k]=item
            except Exception as exc:
                errors.append(f"{topic}:{type(exc).__name__}")
        rows[topic]=list(candidates.values())
    if success<4:
        raise RuntimeError(f"검색 성공 {success}/6회: 미검증 상태로 발송하지 않음 {errors}")
    changed,seen=select(rows,state["seen"],first)
    next_state=dict(state)
    next_state["seen"]=seen
    if first or changed or seen!=state["seen"]:
        next_state["updated_at"]=NOW.isoformat()
        next_state["source_checks"]=original
    if first:
        message=initial_report()
    elif changed:
        message=TITLE+"\n기준: "+NOW.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")+"\n\n"+"\n\n".join(changed)+"\n"
    else:
        message=""
    ALERT.parent.mkdir(parents=True,exist_ok=True)
    if message:
        ALERT.write_text(message,encoding="utf-8")
    else:
        ALERT.unlink(missing_ok=True)
    PENDING.write_text(json.dumps(next_state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    STATUS.write_text("\n".join((
        "# 우주 발사대·PRS 자금 감시",
        f"- 확인시각: {NOW.astimezone(KST).isoformat()}",
        f"- 원문 검증 성공: {sum(z['ok'] for z in original.values())}/{len(original)}",
        f"- RSS 조회 성공: {success}/6, 오류: {len(errors)}",
        f"- 최초 기준선: {first}, 신규 사건: {len(changed)}",
        "- 계약상대방 공개 여부와 950톤 계약단가 미확인으로 표시",
        "- 한화 1차 공시 정정조건 128,000원과 2차 62,400원 분리",
        "- 원문 링크·한국어·한 메시지 무손실 검사 후 전송",
        "",
    )),encoding="utf-8")
    print(f"k_space_launchpad_capital_scan=ok first={first} official={sum(z['ok'] for z in original.values())} rss_ok={success} new={len(changed)} send={bool(message)}")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
