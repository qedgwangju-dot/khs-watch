#!/usr/bin/env python3
"""Monitor iPhone Duo preorder allocation and per-market shipping lead times.

Shipping backlogs are a supply-demand balance, NOT a measured sales volume.
The launch date is distinct from the promised date for new online orders.
Keep a stable source-verified first-day chronology (2026-10-16), and alert again
only for a fresh material ETA extension in the SAME market. Do not infer
country/colour/capacity absent an explicit claim. No new Telegram route.
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

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "apple_duo_preorder_delivery_state.json"
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)
PENDING = OUT / "apple_duo_preorder_delivery_pending_state.json"
STATUS = OUT / "apple_duo_preorder_delivery_status.md"
FRAGMENT = OUT / "apple_duo_preorder_delivery_alert.html"
TELEGRAM = OUT / "apple_duo_supply_watch_telegram.txt"
KST = ZoneInfo("Asia/Seoul")
PREORDER = dt.datetime(2026, 10, 16, 21, tzinfo=KST)
LAUNCH = dt.date(2026, 10, 23)
APPLE = "https://www.apple.com/kr/newsroom/2026/10/open-up-to-new-possibilities-with-iphone-duo/"
AI = "https://appleinsider.com/articles/26/10/16/iphone-duo-sells-out-moments-after-pre-orders-begin"
MR = "https://www.macrumors.com/2026/10/16/iphone-duo-preorder-shipping-wait-times/"
VERGE = "https://www.theverge.com/tech/1012805/apple-iphone-duo-preorder-delay"
QUERY = [
    ("ko", '"아이폰 듀오" 사전 예약 품절 배송 예정일'),
    ("ko", '"아이폰 듀오" 배송 지연 11월 12월 2027년'),
    ("en", '"iPhone Duo" preorders delivery estimated November December January'),
    ("en", '"iPhone Duo" shipping dates backorder 2027'),
    ("en", '"iPhone Duo" preorder sold out production supply shortage'),
]
FEEDS = [
    ("MacRumors", "https://feeds.macrumors.com/MacRumors-All"),
    ("AppleInsider", "https://appleinsider.com/rss/news/"),
    ("The Verge", "https://www.theverge.com/rss/index.xml"),
]
HIGH = ("reuters", "bloomberg", "the verge", "financial times", "nikkei", "apple newsroom")
MID = ("appleinsider", "macrumors", "9to5mac", "the elec", "연합뉴스", "zdnet", "전자신문")
UA = "Mozilla/5.0 (compatible; khs-iphone-duo-delivery-watch/1.0)"

BASELINE = {
    "2026-10-16_initial_stock_out": {
        "status": "초기 10월23일 배송분 소진 보도·총주문 마감 아님",
        "source": AI,
    },
    "US": {
        "latest_reported_delivery": "2027-01",
        "precision": "1월 말(일자 미확정)",
        "source": VERGE,
        "source_quality": "독립 보도, Apple 공식 동적 배송 견적 미열람",
        "first_retail_date": LAUNCH.isoformat(),
    },
    "KR": {"latest_reported_delivery": None, "precision": "확인 불가"},
}

def _clean(v: str | None) -> str:
    s = re.sub(r"<[^>]*>", " ", v or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()

def _rank(v: str) -> int:
    s = _clean(v).lower()
    if any(x in s for x in HIGH):
        return 3
    if any(x in s for x in MID):
        return 2
    return 0

def _fingerprint(v: dict) -> str:
    key = f"{v.get('title','')}|{v.get('source','')}|{v.get('published_at_kst','')}".lower()
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]

def _date(v: str | None) -> dt.datetime | None:
    try:
        t = parsedate_to_datetime(v or "")
        if t.tzinfo is None:
            t = t.replace(tzinfo=dt.timezone.utc)
        return t.astimezone(KST)
    except Exception:
        return None

def _month_and_day(phrase: str, pub: dt.datetime) -> tuple[str, str, str | None] | None:
    s = phrase.lower()
    month_map = {
        "october":10, "oct":10, "november":11, "nov":11,
        "december":12, "dec":12, "january":1, "jan":1,
        "february":2, "feb":2, "march":3, "mar":3,
        "april":4, "apr":4, "may":5, "june":6, "jun":6,
        "july":7, "jul":7, "august":8, "aug":8, "september":9, "sep":9,
    }
    found: list[tuple[int,int|None]]=[]
    month_name=r"october|oct|november|nov|december|dec|january|jan|february|feb|march|mar|april|apr|may|june|jun|july|jul|august|aug|september|sep"
    # Range like November 16–23: track its *latest* delivery day.
    for m in re.finditer(
        r"\b("+month_name+r")\s+(\d{1,2})\s*(?:-|–|—|to|through|~)\s*(\d{1,2})\b",s
    ):
        start_day,end_day=int(m.group(2)),int(m.group(3))
        if start_day<=end_day:
            found.append((month_map[m.group(1)],end_day))
    for m in re.finditer(r"\b("+month_name+r")\s+(\d{1,2})\b",s):
        found.append((month_map[m.group(1)],int(m.group(2))))
    for m in re.finditer(r"\b("+month_name+r")\b",s):
        month=month_map[m.group(1)]
        if not any(f[0]==month for f in found):
            found.append((month,None))
    for m in re.finditer(r"(\d{1,2})\s*월\s*(\d{1,2})?\s*일?",s):
        found.append((int(m.group(1)),int(m.group(2)) if m.group(2) else None))
    found=[(mo,day) for mo,day in found if 1<=mo<=12 and (day is None or 1<=day<=31)]
    if not found:
        return None
    # Never convert an October 23 launch date into a reported new-order delay.
    future=[]
    for month,day in found:
        year=pub.year+(1 if month < pub.month-1 else 0)
        try:
            value=dt.date(year,month,day or 1)
        except ValueError:
            continue
        if value<=LAUNCH:
            continue
        future.append((year,month,day))
    if not future:
        return None
    year,month,day=max(future)
    precision=f"{year}년 {month}월 {day}일" if day else f"{year}년 {month}월(정확한 일자 확인 불가)"
    if day is None and ("late " in s or "말" in s):
        precision=f"{year}년 {month}월 말(정확한 일자 확인 불가)"
    exact=f"{year:04d}-{month:02d}-{day:02d}" if day is not None else None
    return f"{year:04d}-{month:02d}", precision, exact

def _shipping_event(blob: str, published: dt.datetime) -> dict | None:
    low=blob.lower()
    if published < PREORDER:
        return None
    if not ("iphone duo" in low or "아이폰 듀오" in low):
        return None
    # Delivery of new orders differs from release on 10/23 and from original preorders.
    eta_words=("shipping","delivery","delivered","ships","backorder","wait times",
               "배송","출고","납기","대기 기간")
    # Prefer shipment-related sentences. Do not take unrelated dates from sidebars.
    clauses=re.split(r"[\n;。!?]+",blob)
    selected=[]
    for clause in clauses:
        cs=clause.lower()
        if any(k in cs for k in eta_words):
            selected.append(clause)
    if not selected:
        return None
    info=_month_and_day(" ".join(selected),published)
    if info is None:
        return None
    # No cross-country comparisons based on unspecified geography.
    has_us=bool(re.search(r"\b(?:u\.s\.?|united states|usa|us apple store)\b",low))
    has_kr=bool(re.search(r"\b(?:south korea|korea|한국|국내|대한민국)\b",low))
    market="미국" if has_us and not has_kr else ("한국" if has_kr and not has_us else "지역 미확인")
    capacities=set(re.findall(r"\b(?:256|512)\s*gb\b|\b(?:1|2)\s*tb\b",low))
    colours={x for x in ("star white","night sky","스타 화이트","나이트 스카이") if x in low}
    storage=next(iter(capacities)).replace(" ","").upper() if len(capacities)==1 else "구성 미확인"
    colour=next(iter(colours)) if len(colours)==1 else "색상 미확인"
    return {"market":market,"month":info[0],"label":info[1],"exact_date":info[2],
            "capacity":storage,"colour":colour}

def _initial_alert() -> str:
    return "\n".join([
        "📦 <b>[iPhone Duo 초기 예약·배송 지연 | 첫 기준선]</b>",
        "━━━━━━━━━━━━━━━━",
        "<b>[공식 일정과 실시간 배송 추정치를 분리]</b>",
        "• Apple 공식: 2026년 10월 16일 21:00 KST 사전주문 시작, 10월 23일 정식 출시.",
        "• AppleInsider(21:07 KST): 초기 10월23일 수령분 소진, 주문 배송 예정일 11월16일→23일로 이동 보도.",
        "• MacRumors(21:22 KST): 미국 온라인 2색상×4저장용량(8개 구성)의 신규 주문 배송 견적 12월15~22일.",
        "• The Verge(약 22시 KST): 미국 온라인 신규 주문 배송 전망이 2027년 1월 말까지 이동했다고 보도.",
        "",
        "<b>[판정]</b>",
        "🟠 <b>초기 공급 가능 물량 대비 주문 집중·배송 장기화</b>",
        "• 초기 배송분 소진은 총주문 마감 아님. 신규 사전주문은 계속 가능하지만 배송이 늦어질 수 있습니다.",
        "• 배송 대기 증가 ≠ 실제 판매 대수·예상 대비 수요 증가율 확정.",
        "• Apple의 초기 재고 대수와 일 생산량이 공개되지 않아 수요 강세와 생산 부족의 기여도를 분리할 수 없습니다.",
        "• 위 배송 추정치는 언론사의 미국 온라인 주문 확인 보도이며, Apple 공식 지역별 동적 배송 견적을 직접 확인한 것은 아닙니다.",
        "• 공식 출시일 10월23일 변경과 신규 주문 배송 지연을 혼동하지 않습니다.",
        "",
        "<b>[후속 확인]</b>",
        "• 한국/미국·색상·저장용량·조회시각별 실제 배송일과 매장 픽업 재고",
        "• 7일 이상 추가 배송 지연, 2027년 2월 이후 확장, 배송기간 단축의 공식 확인",
        "• Foxconn 완제품 생산량·최종 조립 수율·힌지 품질·Samsung Display 추가 OLED 발주",
        "",
        f'<a href="{APPLE}">Apple 공식 사전예약·출시 일정</a>',
        f'<a href="{AI}">AppleInsider 초기 11월 배송 전망</a>',
        f'<a href="{MR}">MacRumors 미국 12월15~22일</a>',
        f'<a href="{VERGE}">The Verge 미국 2027년 1월 말</a>',
    ])+"\n"

def _request(url: str) -> bytes:
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"application/rss+xml,application/atom+xml,application/xml,text/html,*/*"})
    with urllib.request.urlopen(req,timeout=12) as r:
        return r.read(500000)

def _publisher_article_text(link: str, source: str) -> str:
    """Read a direct publisher's main article, never a Google redirect."""
    host=(urlparse(link).hostname or "").lower()
    permitted={
        "macrumors.com":("macrumors.com","www.macrumors.com"),
        "appleinsider":("appleinsider.com","www.appleinsider.com"),
        "the verge":("theverge.com","www.theverge.com"),
    }
    prefix=next((name for name in permitted if name in source.lower()),None)
    if not prefix or host not in permitted[prefix]:
        return ""
    try:
        raw=_request(link).decode("utf-8",errors="replace")
    except Exception:
        return ""
    # Some sites use multiple article tags; read the main one only. Do not
    # mistake "related articles" and footer dates for current availability.
    block=re.search(r"<article\b[^>]*>(.*?)</article\s*>",raw,re.I|re.S)
    if not block:
        return ""
    value=re.sub(r"<(?:script|style|nav)[^>]*>.*?</(?:script|style|nav)>"," ",block.group(1),flags=re.I|re.S)
    return _clean(value)[:16000]


def _collect() -> tuple[list[dict],list[str]]:
    now=dt.datetime.now(KST)
    results:dict[str,dict]={}
    errors:list[str]=[]
    sources=[]
    for name,url in FEEDS:
        sources.append((name,url))
    for lang,q in QUERY:
        p={"q":q,"hl":"ko" if lang=="ko" else "en-US",
           "gl":"KR" if lang=="ko" else "US",
           "ceid":"KR:ko" if lang=="ko" else "US:en"}
        sources.append(("", "https://news.google.com/rss/search?"+urllib.parse.urlencode(p)))
    article_fetches=0
    for source_name,url in sources:
        try:
            root=ET.fromstring(_request(url))
        except Exception as e:
            errors.append(f"{source_name or '검색'}: {type(e).__name__}")
            continue
        nodes=root.findall(".//item")
        atom=False
        if not nodes:
            nodes=root.findall(".//{http://www.w3.org/2005/Atom}entry")
            atom=True
        for n in nodes[:60]:
            if atom:
                title=_clean(n.findtext("{http://www.w3.org/2005/Atom}title"))
                desc=_clean(n.findtext("{http://www.w3.org/2005/Atom}summary") or n.findtext("{http://www.w3.org/2005/Atom}content"))
                date_str=n.findtext("{http://www.w3.org/2005/Atom}published") or n.findtext("{http://www.w3.org/2005/Atom}updated")
                try:
                    pub=dt.datetime.fromisoformat((date_str or "").replace("Z","+00:00")).astimezone(KST)
                except Exception:
                    pub=None
                link_node=n.find("{http://www.w3.org/2005/Atom}link")
                link=(link_node.attrib.get("href") or "") if link_node is not None else ""
            else:
                title=_clean(n.findtext("title"))
                desc=_clean(n.findtext("description"))
                pub=_date(n.findtext("pubDate"))
                link=_clean(n.findtext("link"))
            source_tag=n.find("source")
            source=source_name or _clean(source_tag.text if source_tag is not None else "")
            if not title or not pub or pub < PREORDER or pub > now+dt.timedelta(minutes=15):
                continue
            if pub < now-dt.timedelta(days=14):
                continue
            blob=f"{title} {desc}".lower()
            if not ("iphone duo" in blob or "아이폰 듀오" in blob):
                continue
            if _rank(source)<2 or not any(k in blob for k in ("preorder","pre-order","shipping","delivery","ship","sold out","backorder","배송","예약","품절","출고")):
                continue
            if (source_name and article_fetches < 5 and
                    _month_and_day(title+" "+desc,pub) is None):
                article_fetches+=1
                full=_publisher_article_text(link,source_name)
                if full and ("iphone duo" in full.lower() or "아이폰 듀오" in full.lower()):
                    desc=full
            row={"title":title,"description":desc,"source":source,"link":link,
                 "published_at_kst":pub.isoformat(timespec="seconds")}
            results[_fingerprint(row)]=row
    return sorted(results.values(),key=lambda x:x["published_at_kst"]),errors

def _load() -> dict:
    if not STATE_PATH.exists():
        return {"schema_version":1,"initial_alert_sent":False,
                "seen_ids":[],"seen_fact_keys":[],"baseline":BASELINE,
                "market_latest":{"미국":"2027-01"}}
    try:
        val=json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        raise RuntimeError("Preorder delivery state corrupt; fail closed to prevent duplicate alert") from e
    if not isinstance(val,dict):
        raise RuntimeError("Preorder delivery state invalid; fail closed")
    val.setdefault("seen_ids",[])
    val.setdefault("seen_fact_keys",[])
    val.setdefault("market_latest",{"미국":"2027-01"})
    val.setdefault("market_day_latest",{})
    val.setdefault("market_sku_day_latest",{})
    return val

def _new_delivery_signals(rows: list[dict], state: dict) -> tuple[list[dict],set[str]]:
    seen=set(state.get("seen_ids") or [])
    known=set(state.get("seen_fact_keys") or [])
    latest=dict(state.get("market_latest") or {})
    sku_latest=dict(state.get("market_sku_latest") or {})
    sku_dates=dict(state.get("market_sku_day_latest") or {})
    market_dates=dict(state.get("market_day_latest") or {})
    new=[]
    for row in rows:
        fp=_fingerprint(row)
        if fp in seen:
            continue
        seen.add(fp)
        body=f"{row['title']}. {row.get('description','')}"
        pub=dt.datetime.fromisoformat(row["published_at_kst"])
        info=_shipping_event(body,pub)
        if info is None:
            continue
        market=info["market"]
        # Unspecified region cannot be used to upgrade a US or KR delivery ETA.
        if market=="지역 미확인":
            continue
        scope=f"{market}|{info['capacity']}|{info['colour']}"
        fingerprint=f"{scope}:{info['exact_date'] or info['month']}"
        if fingerprint in known:
            continue
        sku_specific=info["capacity"]!="구성 미확인"
        prior=sku_latest.get(scope) if sku_specific else latest.get(market)
        if prior is None and sku_specific:
            prior=latest.get(market)
        previous_date=sku_dates.get(scope) if sku_specific else market_dates.get(market)
        current_date=info["exact_date"]
        # Prior later-month report is not invalidated by an earlier ETA from
        # another colour or capacity variant. This is a *later* ETA watch.
        advanced_month=prior is None or info["month"]>prior
        advanced_day=False
        if prior==info["month"] and current_date and previous_date:
            try:
                diff=(dt.date.fromisoformat(current_date)-dt.date.fromisoformat(previous_date)).days
                advanced_day=diff>=7
            except ValueError:
                advanced_day=False
        if not advanced_month and not advanced_day:
            continue
        if _rank(row.get("source") or "")<2:
            continue
        info.update({"item":row,"previous_month":prior,"previous_date":previous_date,
                     "fact_key":fingerprint,"change_type":"추가 배송 지연"})
        new.append(info)
        known.add(fingerprint)
        if latest.get(market) is None or info["month"]>latest[market]:
            latest[market]=info["month"]
        if sku_specific:
            sku_latest[scope]=info["month"]
            if current_date:
                sku_dates[scope]=current_date
            else:
                sku_dates.pop(scope,None)
        else:
            if current_date:
                market_dates[market]=current_date
            else:
                market_dates.pop(market,None)
    state["market_latest"]=latest
    state["market_sku_latest"]=sku_latest
    state["market_day_latest"]=market_dates
    state["market_sku_day_latest"]=sku_dates
    state["seen_fact_keys"]=sorted(known)[-400:]
    return new,seen

def _update_alert(changes: list[dict]) -> str:
    lines=["📦 <b>[iPhone Duo 사전주문 배송 추정 변경]</b>","━━━━━━━━━━━━━━━━",
           "🟠 <b>기존 배송 예상보다 추가 지연 보도</b>"]
    for ch in changes[:3]:
        row=ch["item"]
        lines += [
            f"• {html.escape(ch['market'])} / {html.escape(ch['capacity'])} / {html.escape(ch['colour'])}: "
            f"{html.escape(ch.get('previous_month') or '이전 수치 없음')} → {html.escape(ch['label'])}",
            f"  └ {html.escape(row['source'])} · {html.escape(row['published_at_kst'])}",
            f'<a href="{html.escape(row.get("link") or "",quote=True)}">배송 전망 원문</a>',
        ]
    lines += ["","• 배송일은 국가·색상·저장용량·조회시각별로 달라질 수 있습니다.",
              "• 예약 대기 확대는 수요와 초기 공급의 합성 지표로, 실제 예약 대수나 공식 출시 연기를 뜻하지 않습니다.",
              "• Apple 주문 구성별 원문 배송일의 직접 확인 전에는 '언론 보도' 단계입니다."]
    return "\n".join(lines)+"\n"

def _append(alert: str) -> None:
    text=TELEGRAM.read_text(encoding="utf-8").strip() if TELEGRAM.exists() else ""
    TELEGRAM.write_text((text+"\n\n━━━━━━━━━━━━━━━━\n\n" if text else "")+alert,encoding="utf-8")

def main() -> None:
    now=dt.datetime.now(KST)
    state=_load()
    rows,errors=_collect()
    first=not state.get("initial_alert_sent")
    alerts=[]
    if first:
        alerts.append(_initial_alert())
        state["initial_alert_sent"]=True
        state["market_latest"]={"미국":"2027-01"}
        state["market_sku_latest"]={}
        state["market_day_latest"]={}
        state["market_sku_day_latest"]={}
        state["baseline"]=BASELINE
        state["seen_ids"]=sorted(set(state.get("seen_ids") or []) | {_fingerprint(x) for x in rows})[-800:]
        state["seen_fact_keys"]=sorted(set(state.get("seen_fact_keys") or []) | {"미국:2026-11","미국:2026-12","미국:2027-01","initial_launch_allocation"})[-400:]
    else:
        updates,seen=_new_delivery_signals(rows,state)
        state["seen_ids"]=sorted(seen)[-800:]
        if updates:
            alerts.append(_update_alert(updates))
    state.update({"schema_version":1,"updated_at_kst":now.isoformat(timespec="seconds"),
                  "last_scan_items":len(rows),"errors":errors[-20:],
                  "last_signal_count":len(alerts)-(1 if first else 0),
                  "last_alert":{"at_kst":now.isoformat(timespec="seconds"),"kind":"baseline" if first else "extension"} if alerts else state.get("last_alert")})
    PENDING.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if alerts:
        txt="\n\n".join(alerts)
        FRAGMENT.write_text(txt,encoding="utf-8")
        _append(txt)
    elif FRAGMENT.exists():
        FRAGMENT.unlink()
    STATUS.write_text("# 아이폰 듀오 예약·배송 추적\n"
        f"- checked_at_kst: {now.isoformat(timespec='seconds')}\n"
        f"- initial_alert_pending: {str(first).lower()}\n"
        f"- checked_news: {len(rows)}\n"
        f"- new_changes: {len(alerts)-(1 if first else 0)}\n"
        f"- country_shipping_latest: {json.dumps(state.get('market_latest'),ensure_ascii=False)}\n"
        f"- failed_queries: {len(errors)}\n",
        encoding="utf-8")

if __name__=="__main__":
    main()
