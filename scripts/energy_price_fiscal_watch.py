#!/usr/bin/env python3
"""한국 에너지 가격통제·재정부담 공식 변화 감시.
공식 게시물 신규성 확인, 최초 기준선 무발송, 송출 성공 후 상태 저장.
"""
from __future__ import annotations
import argparse, datetime as dt, html, json, re, sys, os, subprocess, time, hashlib
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data/energy_price_fiscal_state.json"
OUT = ROOT / "out"
PENDING = OUT / "energy_price_fiscal_pending.json"
BASELINE = OUT / "energy_price_fiscal_baseline.json"
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
    # A customer efficiency/consulting campaign is not a tariff decision.
    # Do not suppress an actual tariff or fuel-adjustment decision in the same title.
    if re.search(r"전기요금\s*절감\s*(?:컨설팅|서비스)|전기요금\s*절약\s*(?:컨설팅|서비스)",title) and not re.search(r"조정단가|요금\s*(?:인상|인하|동결|조정|개정|확정)|공급약관",title):
        return None
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
            date_node=a.select_one(".date")
            list_date=None
            if date_node:
                m=re.search(r"(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})",date_node.get_text(" ",strip=True))
                if m:
                    list_date=dt.date(int(m.group(1)),int(m.group(2)),int(m.group(3))).isoformat()
            found.setdefault(ident,{"id":ident,"title":title,"url":url,"source":source,"category":category(title),"list_date":list_date})
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
    t=compact(BeautifulSoup(detail,"html.parser").get_text(" ",strip=True))[:15000]
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

def scan(now, prior=None):
    fetched={}; failed={}; visited={}
    prior=prior or {}
    for key,(url,_) in SOURCES.items():
        try:
            entries=candidates(get_page(url),url,key)
            # Overlap verified MOTIR pagination; inspect deeper after an execution gap.
            if key.startswith("motir"):
                last=(prior.get("sources",{}).get(key) or {}).get("last_ok_kst")
                gap=now-dt.datetime.fromisoformat(last) if last else dt.timedelta(days=1)
                page_limit=5 if gap>dt.timedelta(hours=4) else 2
                ids={x["id"] for x in entries}
                for page in range(2,page_limit+1):
                    page_url=url.replace("pageIndex=1",f"pageIndex={page}")
                    try:
                        more=candidates(get_page(page_url),page_url,key)
                        novel=[x for x in more if x["id"] not in ids]
                        if not novel:
                            raise RuntimeError("공식 목록 추가 페이지 중복")
                        entries.extend(novel)
                        ids.update(x["id"] for x in novel)
                    except Exception as exc:
                        failed[key]="추가 페이지 확인 실패: "+type(exc).__name__
                        break
            visited[key]=len(entries)
            good=[]
            for item in [x for x in entries if x["category"]]:
                try:
                    content=get_page(item["url"])
                    item=dict(item)
                    try:
                        item["published"]=published_date(content)
                    except ValueError:
                        if not item.get("list_date"):
                            raise
                        item["published"]=item["list_date"]
                    item["stage"]=stage(item)
                    item["prices"]=prices(content) if item["category"]=="oil_cap" else {}
                    good.append(item)
                except Exception as exc:
                    failed[key]="공식 상세 문서 확인 실패: "+type(exc).__name__
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
    parser.add_argument("--deliver",action="store_true")
    args=parser.parse_args()
    if args.deliver:
        return deliver_pending()
    OUT.mkdir(parents=True,exist_ok=True)
    now=dt.datetime.now(KST)
    previous=json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    fetched,failed,visited=scan(now,previous)
    if not fetched:
        raise RuntimeError("모든 공식 원천 조회 실패: 신규 발표 없음으로 처리하지 않음")
    state,items=prepare_operational_state(previous,fetched,now)
    for key in failed:
        # Keep last fully successful coverage time, so catch-up continues after partial errors.
        if key in previous.get("sources",{}):
            state["sources"][key]=previous["sources"][key]
        else:
            state["sources"].pop(key,None)
    BASELINE.write_text(json.dumps(previous,ensure_ascii=False)+"\n",encoding="utf-8")
    state["source_health"]={"ok":sorted(set(fetched)-set(failed)),
                            "partial":sorted(set(fetched)&set(failed)),
                            "failed":failed,"complete":not bool(failed)}
    PENDING.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    ALERT.unlink(missing_ok=True)
    if items and not args.no_alert:
        ALERT.write_text(render(items,now,failed)+"\n",encoding="utf-8")
    summary=[
        f"# 에너지 가격통제·재정부담 감시 {now.isoformat(timespec='seconds')}",
        f"- 최초 기준선 구축: {'예' if not previous.get('initialized') else '아니오'}",
        f"- 공식 원천 전체 조회 성공: {len(set(fetched)-set(failed))}/{len(SOURCES)}",
        f"- 일부 자료만 확인된 원천: {sorted(set(fetched)&set(failed)) or '없음'}",
        f"- 미확인 원천: {failed or '없음'}",
        f"- 발송 대기 공식 문서: {len(items)}",
        f"- 발송 미확인/보류: {sum(v.get('status')!='queued' for v in state.get('pending_delivery',{}).values())}",
        f"- 조회 판정: {'부분 조회 실패' if failed else ('신규/미발송 문서 있음' if items else '신규 문서 없음')}",
        f"- 실제 전송 후보: {bool(items) and not args.no_alert}",
    ]
    STATUS.write_text("\n".join(summary)+"\n",encoding="utf-8")
    print("\n".join(summary))
    if failed:print("partial_source_failures="+json.dumps(failed,ensure_ascii=False),file=sys.stderr)
    return 0


def copy_state(value):
    return json.loads(json.dumps(value,ensure_ascii=False))

def prepare_operational_state(prior,fetched,now):
    root,events=transition(prior,fetched,now)
    pending=root.setdefault("pending_delivery",{})
    receipts=root.setdefault("delivery_receipts",{})
    old_ids={i for values in prior.get("seen",{}).values() for i in values}
    for doc in events:
        ident=doc["id"]
        if ident not in old_ids and ident not in pending and ident not in receipts:
            pending[ident]={"document":doc,"status":"queued","discovered_at_kst":now.isoformat(timespec="seconds")}
    for record in pending.values():
        if record.get("status")=="sending":
            record["status"]="uncertain"
            record["reason"]="previous_attempt_interrupted"
    for source,ids in root["seen"].items():
        root["seen"][source]=sorted((set(ids)|set(prior.get("seen",{}).get(source,[])))-set(pending))
    queue=[v["document"] for v in pending.values() if v.get("status")=="queued"]
    queue.sort(key=lambda d:(d.get("published",""),d["id"]))
    return root,queue

def batches(docs,now,errors):
    group=[]
    for doc in docs:
        if len(render([doc],now,errors))>3500:
            raise RuntimeError("단일 문서 안전 전송 길이 초과")
        if group and len(render(group+[doc],now,errors))>3500:
            yield group,render(group,now,errors)
            group=[]
        group.append(doc)
    if group:
        yield group,render(group,now,errors)

def git(*args):
    return subprocess.run(["git",*args],cwd=ROOT,check=True,capture_output=True,text=True).stdout

def persist_state(expected,incoming):
    # Shared branch may advance, but the dedicated state must match the expected snapshot.
    git("config","user.name","energy-price-fiscal-watch[bot]")
    git("config","user.email","energy-price-fiscal-watch[bot]@users.noreply.github.com")
    for attempt in range(5):
        try:
            git("fetch","origin","main")
            git("reset","--hard","origin/main")
            remote=json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
            if remote==incoming:
                return
            if remote!=expected:
                raise RuntimeError("운영 상태 동시 변경: 덮어쓰기 및 전송 중단")
            STATE.parent.mkdir(parents=True,exist_ok=True)
            STATE.write_text(json.dumps(incoming,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
            git("add",str(STATE.relative_to(ROOT)))
            git("commit","-m","Update energy price fiscal watch state [skip ci]")
            git("push","origin","HEAD:main")
            print("energy_state_committed=true",flush=True)
            return
        except subprocess.CalledProcessError:
            time.sleep((attempt+1)*3)
    raise RuntimeError("운영 상태 저장 실패: 전송 중단")

def resolve_chat(token,configured):
    # Do not log tokens, raw chat IDs, or raw Telegram exceptions.
    try:
        r=requests.post(f"https://api.telegram.org/bot{token}/getChat",json={"chat_id":configured},timeout=20)
        obj=r.json()
        chat=obj.get("result") or {}
        cid=chat.get("id")
        if not r.ok or obj.get("ok") is not True or type(cid) is not int:
            raise ValueError()
        if configured.startswith("@"):
            if str(chat.get("username") or "").lower()!=configured[1:].lower():
                raise ValueError()
        elif str(cid)!=configured:
            raise ValueError()
        return cid
    except Exception:
        raise RuntimeError("Telegram 지정 수신처 확인 실패: 전송하지 않음") from None

def classify_response(http_status,obj,target):
    if not isinstance(obj,dict):
        return "uncertain",None
    result=obj.get("result")
    if 200<=http_status<300 and obj.get("ok") is True and isinstance(result,dict):
        chat=result.get("chat")
        cid=chat.get("id") if isinstance(chat,dict) else None
        mid=result.get("message_id")
        if type(cid) is int and cid==target and type(mid) is int and mid>0:
            return "confirmed",hashlib.sha256(f"{cid}:{mid}".encode()).hexdigest()
        return "uncertain",None
    if obj.get("ok") is False and obj.get("error_code")==http_status and http_status in (400,401,403,404,429):
        return ("queued" if http_status==429 else "blocked"),None
    return "uncertain",None

def finalize_delivery(state,docs,status,receipt,now):
    result=copy_state(state)
    for doc in docs:
        ident=doc["id"]
        record=result["pending_delivery"][ident]
        record["status"]=status
        record["last_attempt_kst"]=now.isoformat(timespec="seconds")
        if status=="confirmed":
            if not receipt:
                raise ValueError("확인된 전송 증빙 없음")
            result["delivery_receipts"][ident]={"confirmed_at_kst":now.isoformat(timespec="seconds"),
                "chat_match":True,"message_id_present":True,"receipt_sha256":receipt,
                "run_id":os.getenv("GITHUB_RUN_ID","")}
            source=doc["source"]
            result["seen"][source]=sorted(set(result["seen"].get(source,[]))|{ident})
            del result["pending_delivery"][ident]
    return result

def deliver_pending():
    prior=json.loads(BASELINE.read_text(encoding="utf-8"))
    state=json.loads(PENDING.read_text(encoding="utf-8"))
    persist_state(prior,state)
    # Discovery survives a Telegram outage, but no send may bypass route verification.
    if os.getenv("TELEGRAM_ROUTE_VALID")!="true":
        raise RuntimeError("Telegram 경로 미검증: 신규 문서는 대기 상태 보존, 전송 금지")
    pending=state.get("pending_delivery",{})
    docs=[v["document"] for v in pending.values() if v.get("status")=="queued"]
    docs.sort(key=lambda d:(d.get("published",""),d["id"]))
    if not docs:
        if pending:
            print("::error::발송 미확인/차단 문서 보존: 자동 재발송 금지")
            return 1
        print("telegram_delivery_skipped=true reason=no_queued_documents")
        return 0
    token=(os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    configured=(os.getenv("TELEGRAM_CHAT_ID") or "").strip() or (os.getenv("FALLBACK_TELEGRAM_CHAT_ID") or "").strip()
    if not token or not configured:
        raise RuntimeError("기존 Telegram 경로 설정 누락")
    target=resolve_chat(token,configured)
    print("telegram_chat_resolved=true",flush=True)
    now=dt.datetime.now(KST)
    errors=state.get("source_health",{}).get("failed",{})
    for group,msg in batches(docs,now,errors):
        intent=copy_state(state)
        for doc in group:
            record=intent["pending_delivery"][doc["id"]]
            record["status"]="sending"
            record["attempt_run_id"]=os.getenv("GITHUB_RUN_ID","")
            record["last_attempt_kst"]=now.isoformat(timespec="seconds")
        # Save intent before send; interrupted requests must never be blindly replayed.
        persist_state(state,intent)
        state=intent
        status,receipt="uncertain",None
        try:
            response=requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id":target,"text":msg,"parse_mode":"HTML","disable_web_page_preview":True},timeout=30)
            status,receipt=classify_response(response.status_code,response.json(),target)
        except Exception:
            pass
        after=finalize_delivery(state,group,status,receipt,dt.datetime.now(KST))
        if status=="confirmed":
            print(f"telegram_delivery_confirmed=true chat_match=true message_id_present=true documents={len(group)} receipt_sha256={receipt}",flush=True)
        else:
            print(f"::error::telegram_delivery_status={status}; 성공 키 미확정",flush=True)
        persist_state(state,after)
        state=after
        if status!="confirmed":
            return 1
    if state.get("pending_delivery"):
        print("::error::기존 발송 미확인/차단 문서 보존: 자동 재발송 금지")
        return 1
    return 0

if __name__=="__main__":
    raise SystemExit(main())
