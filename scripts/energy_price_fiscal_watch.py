#!/usr/bin/env python3
"""한국 에너지 가격통제·재정부담 공식 변화 감시.
공식 게시물 신규성 확인, 최초 기준선 무발송, 송출 성공 후 상태 저장.
"""
from __future__ import annotations
import argparse, datetime as dt, html, json, re, sys
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data/energy_price_fiscal_state.json"
OUT = ROOT / "out"
PENDING = OUT / "energy_price_fiscal_pending.json"
ALERT = OUT / "energy_price_fiscal_alert.html"
STATUS = OUT / "energy_price_fiscal_status.md"
KST = ZoneInfo("Asia/Seoul")
SOURCES = {
 "motir_press": ("https://www.motir.go.kr/kor/article/ATCL3f49a5a8c?pageIndex=1", "산업통상부 보도·참고자료"),
 "motir_clarification": ("https://www.motir.go.kr/kor/article/ATCLe0854704d?pageIndex=1", "산업통상부 보도설명자료"),
 "kepco_notice": ("https://www.kepco.co.kr/home/media/newsroom/notice/boardList.do", "한국전력 공지사항"),
 "kepco_press": ("https://www.kepco.co.kr/home/media/newsroom/pr/boardList.do", "한국전력 보도자료"),
 "kogas_press": ("https://www.kogas.or.kr/site/koGas/goBoard.do?Key=1010202000000&boardNo=41&pageIndex=1&pageOffset=0&pageSize=10", "한국가스공사 보도자료"),
}
CATEGORIES = {
 "oil_compensation": r"(?:석유|정유|최고가격|최고액).{0,60}(?:손실보전|손실보상|정산|재정지원)|(?:손실보전|정산).{0,50}(?:정유|석유|최고가격)",
 "oil_cap": r"석유.{0,12}최고가격|최고가격.{0,16}(?:동결|인상|인하|지정|해제|변경)|\d{1,2}차\s*최고가격",
 "oil_budget": r"(?:정유|석유|유류).{0,40}(?:예비비|예산|재정부담)|(?:예비비|예산).{0,40}(?:정유|석유|최고가격)",
 "electric_tariff": r"전기요금|연료비\s*조정단가|연료비조정요금|기후환경요금",
 "gas_tariff": r"도시가스.{0,25}(?:요금|가격|동결|인상|인하)|(?:가스요금).{0,25}(?:조정|변경|인상|인하|동결|산정)",
 "kepco_financial": r"(?:한국전력|한전).{0,40}(?:결산|실적|부채|차입|재무|공사채)|(?:결산|실적|부채).{0,25}(?:한국전력|한전)",
 "kogas_financial": r"(?:가스공사|한국가스공사).{0,40}(?:결산|실적|미수금|부채|차입)|(?:미수금|부채|결산).{0,30}가스공사",
}
LABELS = {"oil_compensation":"석유 최고가격제 손실보전·정산", "oil_cap":"정유사 석유제품 공급가격 상한",
 "oil_budget":"석유가격 통제 재정부담", "electric_tariff":"전기요금", "gas_tariff":"도시가스요금",
 "kepco_financial":"한국전력 재무·차입", "kogas_financial":"가스공사 미수금·차입"}
SESSION=requests.Session()
SESSION.headers.update({"User-Agent":"Mozilla/5.0 (compatible; khs-energy-price-fiscal-watch/1.0)","Accept-Language":"ko-KR,ko;q=0.9"})

def compact(s):
    return re.sub(r"\s+"," ",s or "").strip()

def category(title):
    for name, pattern in CATEGORIES.items():
        if re.search(pattern,title,re.I):
            return name
    return None

def official_id(url,source):
    p=urlparse(url)
    if p.scheme!="https" or p.hostname not in {"www.motir.go.kr","motir.go.kr","www.kepco.co.kr","kepco.co.kr","www.kogas.or.kr","kogas.or.kr"}:
        return None
    if source.startswith("motir"):
        m=re.search(r"/kor/article/(ATCL\w+)/(\d+)/view",p.path)
        return ("motir:"+m.group(1)+":"+m.group(2)) if m else None
    if source.startswith("kepco") and p.path.endswith("/boardView.do"):
        v=parse_qs(p.query).get("boardNo",[""])[0]
        return "kepco:"+v if v.isdigit() else None
    if source=="kogas_press":
        v=parse_qs(p.query).get("boardIdx",[""])[0]
        return "kogas:"+v if v.isdigit() else None
    return None

def candidates(page,list_url,source):
    soup=BeautifulSoup(page,"html.parser")
    found={}
    for a in soup.select("a"):
        title_node=a.select_one("strong.tit, strong.title")
        title=compact(title_node.get_text(" ",strip=True) if title_node else a.get_text(" ",strip=True))
        href=str(a.get("href") or "")
        onclick=str(a.get("onclick") or "")
        url=urljoin(list_url,href)
        if source.startswith("kepco") and not official_id(url,source):
            # KEPCO 게시판의 실제 목록 링크는 javascript:fn_Detail('15','3189') 형태
            m=re.search(r"fn_Detail\s*\(\s*['\"]?(\d+)['\"]?\s*,\s*['\"]?(\d+)['\"]?\s*\)",href+" "+onclick,re.I)
            if m:
                section="pr" if source=="kepco_press" else "notice"
                url=f"https://www.kepco.co.kr/home/media/newsroom/{section}/boardView.do?boardMngNo={m.group(1)}&boardNo={m.group(2)}"
        if source=="kogas_press" and not official_id(url,source):
            # KOGAS 공식 목록: javascript:readPermissionChk(47879);
            m=re.search(r"(?:readPermissionChk|goView|fnView)\s*\(\s*['\"]?(\d{4,})",href+" "+onclick,re.I)
            if m:
                url="https://www.kogas.or.kr/site/koGas/bbs/View.do?Key=1010202000000&cbIdx=41&boardIdx="+m.group(1)
        ident=official_id(url,source)
        if ident and len(title)>=5:
            found.setdefault(ident,{"id":ident,"title":title,"url":url,"source":source,"category":category(title)})
    if len(found)<2:
        sample=[]
        for tag in soup.find_all(["a","div","li","button","span"]):
            title=compact(tag.get_text(" ",strip=True))
            if re.search(r"요금|미수금|3분기|보도|가스|전기|부채|연료비|단가|결산|한전|경영|최고가격",title):
                attrs={k:str(v)[:150] for k,v in tag.attrs.items() if k in ("href","onclick","data-id","data-board-no","class")}
                if attrs:
                    sample.append({"tag":tag.name,"text":title[:65],"attrs":attrs})
            if len(sample)>=8:break
        raw_samples=[]
        for word in ("2026년 4분기", "연료비조정단가", "2026년 3분기", "결산실적", "가스公,", "보도자료", "2026.11.13"):
            idx=page.find(word)
            if idx>=0:
                raw_samples.append({"word":word, "context":page[max(0,idx-220):idx+300][:520]})
            if len(raw_samples)>=4:break
        raise RuntimeError("공식 목록 게시물 링크 2개 미만; raw_snippets="+repr(raw_samples)+"; elements="+repr(sample[:2]))
    return list(found.values())

def get_page(url):
    r=SESSION.get(url,timeout=(10,22))
    r.raise_for_status()
    if len(r.content)<800 or "<html" not in r.text.lower():
        raise RuntimeError("공식 서버의 HTML 응답 형식 오류")
    return r.text

def published_date(detail):
    t=compact(BeautifulSoup(detail,"html.parser").get_text(" ",strip=True))[:2500]
    m=re.search(r"(?:등록일|작성일|게시일)\s*(20\d{2})[.\-/년 ]+\s*(\d{1,2})[.\-/월 ]+\s*(\d{1,2})",t)
    if not m: raise ValueError("공식 문서 발표일 확인 불가")
    return dt.date(int(m.group(1)),int(m.group(2)),int(m.group(3))).isoformat()

def prices(detail):
    t=compact(BeautifulSoup(detail,"html.parser").get_text(" ",strip=True))
    found={}
    for name in ("휘발유","경유","등유"):
        m=re.search(rf"{name}\s*(?:리터당\s*)?(\d{{1,2}},\d{{3}})\s*원",t)
        if m:
            n=int(m.group(1).replace(",",""))
            if 400<=n<=4000:found[name]=n
    return found

def stage(item):
    title=item["title"]; cat=item["category"]
    if cat=="oil_compensation":
        if re.search(r"아직\s*결정|미확정|결정되지|확정되지",title):return "정부 금액 미확정(심의 중)"
        if re.search(r"지급\s*(?:완료|결정|개시)|지급했다",title):return "지급 관련 공식 발표"
        if re.search(r"정산액\s*(?:확정|결정)|지원금\s*(?:확정|결정)",title) and not re.search(r"예정|계획|검토",title):return "정부 금액 결정 발표(입금 여부 별도)"
        return "손실보전 제도·심의 설명(확정 지급과 구별)"
    if cat=="oil_cap":return "정유사 주유소 공급가격 상한(소비자 주유소 가격 아님)"
    if cat in ("kepco_financial","kogas_financial"):return "공기업 공식 실적/재무 발표(연결·별도 구분 필요)"
    return "공식 정책 발표(예산·계획·실제 지급 단계 구별)"

def scan(now):
    fetched={}; failed={}; visited={}
    for key,(url,_) in SOURCES.items():
        try:
            entries=candidates(get_page(url),url,key)
            visited[key]=len(entries)
            good=[]
            for item in [x for x in entries if x["category"]][:10]:
                content=get_page(item["url"])
                item=dict(item)
                item["published"]=published_date(content)
                item["stage"]=stage(item)
                item["prices"]=prices(content) if item["category"]=="oil_cap" else {}
                good.append(item)
            fetched[key]=good
        except Exception as exc:
            failed[key]=type(exc).__name__+": "+str(exc)
    return fetched,failed,visited

def transition(prior,fetched,now):
    # 기존에 없던 source를 복구했을 때도 과거 게시물 소급 알림 차단
    root=json.loads(json.dumps(prior)) if prior else {"version":1,"initialized":False,"seen":{},"sources":{}}
    root.setdefault("seen",{}); root.setdefault("sources",{})
    before=bool(prior.get("initialized")); events=[]
    for source,docs in fetched.items():
        seen=set(root["seen"].get(source,[]))
        for doc in docs:
            if doc["id"] not in seen and before and doc.get("published")>=str(prior.get("seeded_date") or "9999-01-01"):
                events.append(doc)
            seen.add(doc["id"])
        root["seen"][source]=sorted(seen)[-2500:]
        root["sources"][source]={"last_ok_kst":now.isoformat(timespec="seconds"),"matched":len(docs)}
    root["initialized"]=True
    if not before:root["seeded_date"]=now.date().isoformat()
    root["updated_at_kst"]=now.isoformat(timespec="seconds")
    return root,list({x["id"]:x for x in events}.values())

def render(items,now,errors):
    lines=["<b>에너지 가격통제·재정부담 신규 공식 발표</b>",f"조회: {now:%Y-%m-%d %H:%M} KST",
           "석유(정부 손실보전), 전기·가스(공기업 재무)를 구분합니다."]
    for item in items:
        lines+=["", "■ <b>"+html.escape(LABELS[item["category"]])+"</b> / "+html.escape(item["published"]),
                 "• "+html.escape(item["title"]), "• 현재 단계: "+html.escape(item["stage"])]
        if item.get("prices"):
            lines.append("• 정유사 공급상한: "+", ".join(f"{n} {p:,}원/ℓ" for n,p in item["prices"].items()))
        if item["category"]=="oil_compensation":
            lines.append("• 정유업계 요구액·정부 인정액·실제 지급액은 별개입니다.")
        if item["category"]=="oil_budget":
            lines.append("• 연도와 용도가 다른 예비비·사업예산을 합산하지 않습니다.")
        lines.append('<a href="'+html.escape(item["url"],quote=True)+'">공식 원문: '+html.escape(SOURCES[item["source"]][1])+"</a>")
    if errors:
        lines+=["", "• 일부 공식 출처 조회 지연: "+html.escape(", ".join(SOURCES[k][1] for k in errors))]
    return "\n".join(lines)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--no-alert",action="store_true")
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    now=dt.datetime.now(KST)
    previous=json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    fetched,failed,visited=scan(now)
    if "motir_press" not in fetched:
        raise RuntimeError("산업통상부 보도 원천 조회 실패: 상태 전진 및 전송 금지 "+str(failed))
    state,items=transition(previous,fetched,now)
    state["source_health"]={"ok":sorted(fetched),"failed":failed,"complete":not bool(failed)}
    PENDING.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    ALERT.unlink(missing_ok=True)
    if items and not args.no_alert:
        ALERT.write_text(render(items,now,failed)+"\n",encoding="utf-8")
    summary=[
        f"# 에너지 가격통제·재정부담 감시 {now.isoformat(timespec='seconds')}",
        f"- 최초 기준선 구축: {'예' if not previous.get('initialized') else '아니오'}",
        f"- 공식 원천 목록 성공: {len(fetched)}/{len(SOURCES)}",
        f"- 미확인 원천: {failed or '없음'}",
        f"- 신규 공식 문서: {len(items)}",
        f"- 실제 전송 후보: {bool(items) and not args.no_alert}",
    ]
    STATUS.write_text("\n".join(summary)+"\n",encoding="utf-8")
    print("\n".join(summary))
    if failed:print("partial_source_failures="+json.dumps(failed,ensure_ascii=False),file=sys.stderr)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
