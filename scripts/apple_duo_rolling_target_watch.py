#!/usr/bin/env python3
"""iPhone Duo first-12-month supply target watch (NOT calendar-2026 forecast).

The 2026-10-22 DigiTimes 9.7m -> 14m / +44% claim is a reported
rolling-12-month supplier target, not actual shipments, firm purchase orders,
a confirmed Apple guidance figure, or Counterpoint/TrendForce's 2026 estimate.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT=pathlib.Path(__file__).resolve().parents[1]
DATA=ROOT/"data"/"apple_duo_rolling_target_state.json"
OUT=ROOT/"out"
OUT.mkdir(exist_ok=True)
PENDING=OUT/"apple_duo_rolling_target_pending_state.json"
STATUS=OUT/"apple_duo_rolling_target_status.md"
FRAGMENT=OUT/"apple_duo_rolling_target_alert.html"
TELEGRAM=OUT/"apple_duo_supply_watch_telegram.txt"
KST=ZoneInfo("Asia/Seoul")

DIGITIMES="https://www.digitimes.com/news/a20261022PD219/iphone-apple-shipments-demand-foldable.html"
APPLE_LAUNCH="https://www.apple.com/kr/iphone-duo/"
APPLE_APPS="https://www.apple.com/hk/en/newsroom/2026/10/developers-bring-incredible-new-app-experiences-to-iphone-duo/"
TRENDFORCE="https://www.trendforce.com/presscenter/news/20260910-13228.html"
APPLEINSIDER="https://appleinsider.com/articles/26/10/22/more-iphone-duo-parts-ordered-does-not-mean-an-increase-in-shipments"
BASELINE_FACT="duo:rolling_12mo:2026-10-22:digitimes:from_9.7_to_14.0"
BASELINE={
    "period_basis":"rolling_first_12_months",
    "start_end_dates_confirmed":False,
    "report_date":"2026-10-22",
    "reporting_root":"digitimes_2026-10-22",
    "previous_target_m":9.7,
    "reported_target_m":14.0,
    "reported_increase_m":4.3,
    "reported_change_pct":44.3,
    "source_status":"DigiTimes 공급망 보도·Apple 공식 목표 확인 안 됨",
    "apple_officially_confirmed":False,
    "actual_shipments_m":None,
    "named_suppliers_with_verified_incremental_po":[],
    "calendar_2026_counterpoint_forecast_m":6.0,
    "calendar_2026_trendforce_forecast_m":5.0,
    "first_preorder_date":"2026-10-16",
    "retail_launch_date":"2026-10-23",
    "app_showcase_korea":"Apple 공식 2026-10-22 개발자 앱 소개: 카카오톡·WEBTOON·NAVER SERIES·카카오페이지·BAND",
}
QUERIES=[
 ("ko", '"아이폰 듀오" "1,400만" "12개월" 폭스콘'),
 ("ko", '"아이폰 듀오" "970만" "1400만" 목표'),
 ("ko", '"아이폰 듀오" 12개월 생산 출하 목표 주문 상향 폭스콘'),
 ("ko", '"아이폰 듀오" 2027년 첫 12개월 생산목표 수정'),
 ("en", '"iPhone Duo" "14 million" "12 months" DigiTimes'),
 ("en", '"iPhone Duo" "9.7 million" "14 million" orders'),
 ("en", '"iPhone Duo" first year production target revised Foxconn'),
 ("en", '"iPhone Duo" 12-month shipment target lowered raised 2027'),
]
HORIZON=(
    "12-month","12 month","12 months","12-months","twelve months",
    "first year","first 12","over a year","one-year",
    "1-year","rolling year","12개월","12 개월","첫 1년","첫해","1년간",
    "1년 출하","一年","十二个月",
)
MODEL=(
    "iphone duo","foldable iphone","apple foldable",
    "아이폰 듀오","폴더블 아이폰","애플 폴더블",
)
TARGET_WORDS=(
    "shipment target","production target","build target","order target",
    "unit target","supply target","shipment goal","production goal",
    "orders","order","forecast","target","목표","발주","생산 계획","지침","계획","出货目标",
)
CHANGE_WORDS=(
    "raise","raised","increase","increased","boost","boosted","revise","revised",
    "reduce","reduced","cut","cuts","down","lower","lowered","upgraded",
    "상향","하향","증가","늘렸","줄였","감축","조정","상승","下调","上调",
)
HIGH=("digitimes","reuters","nikkei","bloomberg","financial times","trendforce","counterpoint")
MID=("macrumors","9to5mac","appleinsider","investing.com","전자신문","한국경제","매일경제","연합뉴스","zdnet","newsis")
LOW=("wccftech","notebookcheck","reddit","technobezz","note.com","cupertino.news")
UA="Mozilla/5.0 (compatible; khs-duo-12month-target/1.0)"

def _clean(x:str|None)->str:
    return re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",html.unescape(x or ""))).strip()

def _get(url:str, timeout:int=18)->bytes:
    with urllib.request.urlopen(urllib.request.Request(
        url, headers={"User-Agent":UA,"Accept":"application/rss+xml,application/xml,*/*"}
    ), timeout=timeout) as response:
        return response.read()

def _rank(source:str)->int:
    low=_clean(source).lower()
    if any(x in low for x in LOW):return 0
    if any(x in low for x in HIGH):return 3
    if any(x in low for x in MID):return 2
    return 1

def _official(item:dict)->bool:
    domain=(urlparse(item.get("source_url") or "").hostname or "").lower().removeprefix("www.")
    source=_clean(item.get("source")).lower()
    return bool(
        (domain in ("apple.com","newsroom.apple.com") and "apple" in source)
        or (domain in ("honhai.com","foxconn.com") and
            ("foxconn" in source or "hon hai" in source or "홍하이" in source))
    )

def _original_root(item:dict)->str:
    blob=(" ".join(str(item.get(k) or "") for k in ("source","title","description"))).lower()
    if "digitimes" in blob or "디지타임즈" in blob: return "digitimes_2026-10-22"
    if "nikkei" in blob or "니케이" in blob: return "nikkei"
    if _official(item): return "manufacturer_official"
    return "unattributed_supplier_report"

def _million_numbers(text:str)->list[tuple[int,float]]:
    low=_clean(text).lower().replace(",","")
    found=[]
    for m in re.finditer(
        r"(?<!\d)(\d+(?:\.\d+)?)\s*(million|mn|m\s+units|백만|만)\s*(?:units|devices|handsets|phones|대)?",
        low,re.I,
    ):
        v=float(m.group(1))
        if m.group(2)=="만": v/=100
        if 1<=v<=35: found.append((m.start(),round(v,2)))
    return found

def _typed_target(text:str)->dict|None:
    low=_clean(text).lower()
    if not any(x in low for x in MODEL):return None
    if not any(x in low for x in HORIZON):return None
    if not any(x in low for x in TARGET_WORDS):return None
    if not any(x in low for x in CHANGE_WORDS):return None
    points=_million_numbers(low)
    if not points:return None
    # Prefer the explicit "from OLD to NEW" clause if present.
    m=re.search(
        r"(?:from|기존|종전|从)\s*(\d+(?:\.\d+)?)\s*(?:million|mn|백만)?"
        r"\s*(?:units|devices|대)?\s*(?:to|→|에서|至|到)\s*"
        r"(\d+(?:\.\d+)?)\s*(million|mn|백만|만)\s*(?:units|devices|대)?",
        low,
    )
    if m:
        old=float(m.group(1))
        new=float(m.group(2))
        if m.group(3)=="만":new/=100
        if 1<=old<=35 and 1<=new<=35:
            return {"old":round(old,2),"target":round(new,2),"period_basis":"rolling_first_12_months"}
    # Korean two amounts with units, e.g. "970만 대에서 1400만 대로"
    m=re.search(
        r"(\d+(?:\.\d+)?)\s*(만|백만)\s*대?\s*(?:에서|→|~>|to)\s*"
        r"(\d+(?:\.\d+)?)\s*(만|백만)\s*대?",
        low,
    )
    if m:
        old=float(m.group(1))/(100 if m.group(2)=="만" else 1)
        new=float(m.group(3))/(100 if m.group(4)=="만" else 1)
        if 1<=old<=35 and 1<=new<=35:
            return {"old":round(old,2),"target":round(new,2),"period_basis":"rolling_first_12_months"}
    # One target amount is valid only when its surrounding text actually refers
    # to a 12-month target. Do not take "20.2m global foldable market" as Duo.
    for position, number in points:
        near=low[max(0,position-130):min(len(low),position+90)]
        if not any(x in near for x in ("duo","아이폰 듀오","애플 폴더블","foldable iphone")):
            continue
        if any(x in near for x in ("global foldable market","전세계 폴더블 시장","全球折叠")):
            continue
        if any(x in near for x in HORIZON) or any(x in near for x in ("target","목표","지침")):
            return {"old":None,"target":number,"period_basis":"rolling_first_12_months"}
    return None

def _fingerprint(item:dict)->str:
    txt="|".join(_clean(item.get(k)).lower() for k in ("title","source"))
    return hashlib.sha256(txt.encode()).hexdigest()[:24]

def _date(raw:str|None)->dt.datetime|None:
    try:
        d=parsedate_to_datetime(raw or "")
        if d.tzinfo is None:d=d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(KST)
    except Exception:return None

def _search(lang:str, q:str)->str:
    params={"q":q,"hl":"ko" if lang=="ko" else "en-US",
            "gl":"KR" if lang=="ko" else "US",
            "ceid":"KR:ko" if lang=="ko" else "US:en"}
    return "https://news.google.com/rss/search?"+urllib.parse.urlencode(params)

def collect()->tuple[list[dict],list[str]]:
    now=dt.datetime.now(KST)
    cutoff=now-dt.timedelta(days=21)
    result={}
    errors=[]
    for language,query in QUERIES:
        try:root=ET.fromstring(_get(_search(language,query)))
        except Exception as exc:
            errors.append(f"{language}:{type(exc).__name__}")
            continue
        for node in root.findall(".//item"):
            title=_clean(node.findtext("title"))
            desc=_clean(node.findtext("description"))
            url=_clean(node.findtext("link"))
            src=node.find("source")
            source=_clean(src.text) if src is not None else ""
            source_url=_clean(src.attrib.get("url")) if src is not None else ""
            published=_date(node.findtext("pubDate"))
            if not title or not url or not published or published<cutoff or published>now+dt.timedelta(minutes=10):
                continue
            if not any(x in (title+" "+desc).lower() for x in MODEL):
                continue
            item={"title":title,"description":desc,"link":url,
                  "source":source or "출처 미표시","source_url":source_url,
                  "published_at_kst":published.isoformat(timespec="seconds")}
            result[_fingerprint(item)]=item
    return sorted(result.values(),key=lambda x:x["published_at_kst"]),errors

def _load()->dict:
    if not DATA.exists():
        return {"schema_version":1,"initial_alert_sent":False,
                "seen":[],"seen_fact_keys":[BASELINE_FACT],
                "metrics":dict(BASELINE),"last_alert":None}
    try:
        state=json.loads(DATA.read_text(encoding="utf-8"))
        if not isinstance(state,dict) or not isinstance(state.get("initial_alert_sent"),bool):
            raise ValueError("invalid state schema")
        for key in ("seen","seen_fact_keys","metrics"):
            state.setdefault(key, [] if key.startswith("seen") else {})
        return state
    except Exception as exc:
        raise RuntimeError("rolling target state unreadable: do not replay baseline") from exc

def _signal(item:dict, state:dict)->dict|None:
    rank=_rank(item.get("source",""))
    if rank<2 and not _official(item):return None
    text=f"{item.get('title','')} {item.get('description','')}"
    data=_typed_target(text)
    if data is None:return None
    last=float((state.get("metrics") or {}).get("reported_target_m") or 14.0)
    target=float(data["target"])
    official=_official(item)
    if abs(target-last)<1.0 and not official:return None
    if not official and _original_root(item)=="digitimes_2026-10-22" and target==14.0:return None
    key=f"duo|rolling_12m|{target:.2f}|{'official' if official else _original_root(item)}"
    if key in set(state.get("seen_fact_keys") or []):return None
    return {"item":item,"data":data,"rank":3 if official else rank,
            "stage":3 if official else (2 if rank>=3 else 1),
            "fact_key":key,"source_root":_original_root(item)}

def _base_alert()->str:
    lines=[
        "🍎 <b>[iPhone Duo 첫 12개월 목표 | 최초 상향 보도 기준선]</b>",
        "━━━━━━━━━━━━━━━━",
        "• <b>DigiTimes 10월22일 공급망 취재</b>: 첫 12개월 목표 "
        "<b>970만 대 → 1,400만 대</b>, <b>+430만 대 / +44.3%</b>.",
        "• <b>단위는 출시 이후 첫 12개월 목표</b>이며 기간 시작·종료의 정확한 날짜와 "
        "공급사별 추가 구매계약 물량은 공개되지 않았습니다.",
        "• <b>Apple 공식 목표·실제 출하·확정 매출은 아닙니다.</b> "
        "Foxconn·부품 제조사에 목표 상향 지시가 있었다는 보도 단계입니다.",
        "• Reuters 등의 2차 재인용은 별도 독립 공급사 확인으로 세지 않습니다.",
        "",
        "<b>[반드시 분리할 기존 숫자]</b>",
        "• 2026년 말까지의 전망: Counterpoint 약 600만 대 / TrendForce 약 500만 대. "
        "기간이 달라 1,400만 대로 덮어쓰거나 합산하지 않습니다.",
        "• 예약배송이 2027년 1월로 밀린 현상은 수요 증가와 초기 재고 부족이 모두 가능.",
        "• Apple은 높은 사전주문 반응을 밝혔지만 직접 예약 대수는 공개하지 않았습니다.",
        "",
        "<b>[상충 관점·한국 사업 연결]</b>",
        "• AppleInsider는 부품 주문과 완제품 출하 목표를 혼동할 위험을 지적했습니다.",
        "• Apple 공식 개발자 소개에 카카오톡, WEBTOON, NAVER SERIES, "
        "카카오페이지, BAND의 Duo 화면 최적화 사례가 등장합니다. "
        "이는 앱 개발·제품 통합이지 추가 매출 확정이 아닙니다.",
        "",
        "<b>[다음 승격·실패 기준]</b>",
        "• <b>🟠</b> 12개월 목표가 현재 1,400만 대에서 100만 대 이상 변경되면 "
        "기간·새 단가·출처를 확인해 별도 보고.",
        "• <b>🔴</b> Apple·Foxconn 공식 물량 확인 또는 공급사별 실제 추가 발주 "
        "물량·검수·납기 확인 시 계약 범위만 확정 단계로 승격.",
        "• Foxconn 최종 조립 수율, 힌지·폴더블 OLED 패널 양품률, "
        "추가 주문과 실제 출하량이 맞지 않으면 상향 목표 달성 실패 가능.",
        "",
        f'<a href="{DIGITIMES}">DIGITIMES 원보도(유료 일부)</a>',
        f'<a href="{APPLEINSIDER}">수치·생산범위 반대 검증</a>',
        f'<a href="{APPLE_APPS}">Apple 공식 앱 최적화 소개</a>',
        f'<a href="{APPLE_LAUNCH}">Apple 출시 일정</a>',
        f'<a href="{TRENDFORCE}">TrendForce 2026년 전망</a>',
    ]
    return "\n".join(lines)+"\n"

def _change_alert(rows:list[dict], previous:float)->str:
    lines=["🍎 <b>[iPhone Duo 첫 12개월 목표 | 신규 변경]</b>","━━━━━━━━━━━━━━━━"]
    for e in rows[:2]:
        d=e["data"];item=e["item"]
        label="🔴 제조사 공식자료" if e["stage"]==3 else "🟠 12개월 목표 신규 보도"
        lines += [
            f"• {label}: {previous:g}백만 대 → {d['target']:g}백만 대",
            f"• 비교기준: 첫 12개월 부품·생산 목표(연말 출하 전망과 별개). "
            f"원인·추가 실제 발주 확인 전에는 판매실적으로 승격 금지.",
            f"• 출처: {html.escape(item.get('source') or '')} · "
            f"{html.escape(item.get('published_at_kst') or '')}",
            f'<a href="{html.escape(item.get("link") or "",quote=True)}">근거 원문</a>'
        ]
    return "\n".join(lines)+"\n"

def main()->None:
    now=dt.datetime.now(KST)
    state=_load()
    rows,errors=collect()
    if len(errors)==len(QUERIES) and not rows:
        raise RuntimeError("Every source query failed; no alert or state checkpoint")
    first=not state["initial_alert_sent"]
    seen=set(state.get("seen") or [])
    facts=set(state.get("seen_fact_keys") or [])
    facts.add(BASELINE_FACT)
    updates=[]
    metrics=dict(BASELINE);metrics.update(state.get("metrics") or {})
    if first:
        seen.update(_fingerprint(row) for row in rows)
    else:
        candidates={}
        for row in rows:
            fid=_fingerprint(row)
            if fid in seen:continue
            result=_signal(row,{**state,"metrics":metrics,"seen_fact_keys":list(facts)})
            seen.add(fid)
            if not result:continue
            key=result["fact_key"]
            best=candidates.get(key)
            if not best or (result["stage"],result["rank"])>(best["stage"],best["rank"]):
                candidates[key]=result
        updates=sorted(candidates.values(),
                       key=lambda a:(a["stage"],a["rank"],a["item"]["published_at_kst"]),
                       reverse=True)[:2]
        for signal in updates:
            facts.add(signal["fact_key"])
            # A later rumored number should not erase the official target,
            # should a later manufacturer confirmation be available.
            if signal["stage"]>=2 and not metrics.get("apple_officially_confirmed"):
                metrics["reported_target_m"]=signal["data"]["target"]
                metrics["source_status"]="후속 12개월 목표 보도·제조사 미확인"
            if signal["stage"]==3:
                metrics["apple_officially_confirmed"]=True
                metrics["reported_target_m"]=signal["data"]["target"]
                metrics["source_status"]="제조사 공식 출처 확인"
    alert=_base_alert() if first else (_change_alert(updates,float(
        (state.get("metrics") or {}).get("reported_target_m") or 14.0)) if updates else "")
    pending={**state,"schema_version":1,"initial_alert_sent":True,
             "updated_at_kst":now.isoformat(timespec="seconds"),
             "seen":sorted(seen)[-600:],
             "seen_fact_keys":sorted(facts)[-250:],
             "metrics":metrics,"last_scan_items":len(rows),"last_new_signals":len(updates),
             "errors":errors[-16:],
             "last_alert":({"at_kst":now.isoformat(timespec="seconds"),
                            "kind":"first_baseline" if first else "change"}
                           if alert else state.get("last_alert"))}
    PENDING.write_text(json.dumps(pending,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if alert:
        FRAGMENT.write_text(alert,encoding="utf-8")
        existing=TELEGRAM.read_text(encoding="utf-8").strip() if TELEGRAM.exists() else ""
        TELEGRAM.write_text((existing+"\n\n━━━━━━━━━━━━━━━━\n\n" if existing else "")+alert,encoding="utf-8")
    else:
        FRAGMENT.unlink(missing_ok=True)
    STATUS.write_text(
        "# Apple Duo 첫 12개월 목표 감시\n"
        f"- 확인시각: {now.isoformat(timespec='seconds')}\n"
        f"- 기준선 전송대상: {str(first).lower()}\n"
        f"- 기사검색: {len(rows)}건\n"
        f"- 신규 변경: {len(updates)}건\n"
        f"- 원천접근 오류: {len(errors)}건\n"
        f"- 실제 알림 생성: {str(bool(alert)).lower()}\n"
        "- 구분: 12개월 목표 ≠ 2026 연말 출하 ≠ 삼성디스플레이 패널 수 ≠ 소비자 주문\n",
        encoding="utf-8")

if __name__=="__main__":
    main()
