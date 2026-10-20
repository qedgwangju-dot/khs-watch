#!/usr/bin/env python3
"""Samsung Galaxy Buds On commercial rollout watch.

Samsung officially announced Galaxy Buds On October 1, 2026 with KRW299,000
Korea price, black-only, planned October 27 release. A media briefing on
October 20 is NOT an additional launch. No reported customer sales yet.
Only official/OEM-supported retail launch, price changes or regional
rollouts beyond baseline are material; rumors and syndicated briefs are not.
No new Telegram route is created.
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
STATE=ROOT/"data"/"samsung_buds_on_rollout_state.json"
OUT=ROOT/"out"
OUT.mkdir(exist_ok=True)
PENDING=OUT/"samsung_buds_on_rollout_pending_state.json"
STATUS=OUT/"samsung_buds_on_rollout_status.md"
ALERT=OUT/"samsung_buds_on_rollout_alert.html"
TELEGRAM=OUT/"memory_spot_cycle_watch_telegram.txt"
KST=ZoneInfo("Asia/Seoul")
OFFICIAL=("https://news.samsung.com/kr/%EC%82%BC%EC%84%B1%EC%A0%84%EC%9E%90-%EA%B0%A4%EB%9F%AD%EC%8B%9C-"
          "%EC%B5%9C%EC%B4%88-%ED%81%B4%EB%A6%BD%ED%98%95-%EB%AC%B4%EC%84%A0-"
          "%EC%9D%B4%EC%96%B4%ED%8F%B0-%EA%B0%A4%EB%9F%AD%EC%8B%9C-%EB%B2%84")
YONHAP="https://en.yna.co.kr/view/AEN20261020004400320"
BASELINE={
    "product":"갤럭시 버즈 온",
    "korean_price_krw":299000,
    "korean_retail_launch":"2026-10-27",
    "status":"공식 공개·판매 시작 전",
    "color":"블랙 단일",
    "global_schedule":"국가별 일정 미공개",
    "units_sold":None,
}
SEARCHES=[
  ("ko",'"갤럭시 버즈 온" 판매 시작 출시 27일 삼성'),
  ("ko",'"갤럭시 버즈 온" 해외 출시 글로벌 판매 가격'),
  ("ko",'"갤럭시 버즈 온" 판매량 예약량 생산 주문'),
  ("en",'"Galaxy Buds On" worldwide launch regional price sales'),
]
UA="Mozilla/5.0 (compatible; khs-buds-on-rollout/1.0)"


def _fetch(url: str) -> str:
    request=urllib.request.Request(url,headers={"User-Agent":UA})
    with urllib.request.urlopen(request,timeout=22) as f:
        return f.read().decode("utf-8",errors="replace")


def _plain(value: str) -> str:
    value=re.sub(r"(?is)<(?:style|script)[^>]*>.*?</(?:style|script)>"," ",value)
    return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]+>"," ",value))).strip()


def _official_baseline_present(raw: str) -> bool:
    low=_plain(raw).lower()
    return all(x in low for x in ("갤럭시 버즈 온","10월 27일","299,000"))


def _parse_date(raw: str) -> dt.datetime | None:
    try:
        t=parsedate_to_datetime(raw)
        return t.astimezone(KST) if t.tzinfo else t.replace(tzinfo=dt.timezone.utc).astimezone(KST)
    except Exception:
        return None


def _rss_url(lang: str, q: str) -> str:
    options={"q":q,"hl":"ko" if lang=="ko" else "en-US",
             "gl":"KR" if lang=="ko" else "US",
             "ceid":"KR:ko" if lang=="ko" else "US:en"}
    return "https://news.google.com/rss/search?"+urllib.parse.urlencode(options)


def _is_verified_samsung(item:dict) -> bool:
    src=(item.get("source") or "").lower()
    host=(urlparse(item.get("source_url") or "").hostname or "").lower().removeprefix("www.")
    return host=="news.samsung.com" and ("samsung" in src or "삼성" in src)


def _news_items(now:dt.datetime) -> tuple[list[dict],list[str]]:
    cutoff=now-dt.timedelta(days=14)
    out={}
    errs=[]
    for lang,q in SEARCHES:
        try:
            xml=ET.fromstring(_fetch(_rss_url(lang,q)))
            for el in xml.findall(".//item"):
                title=_plain(el.findtext("title") or "")
                description=_plain(el.findtext("description") or "")
                pub=_parse_date(el.findtext("pubDate") or "")
                if not pub or pub<cutoff or pub>now or not title:
                    continue
                blob=(title+" "+description).lower()
                if not ("갤럭시 버즈 온" in blob or "galaxy buds on" in blob):
                    continue
                source=el.find("source")
                item={"title":title, "description":description,
                      "source":_plain(source.text or "") if source is not None else "",
                      "source_url":source.attrib.get("url","") if source is not None else "",
                      "published_at_kst":pub.isoformat(timespec="seconds"),
                      "link":el.findtext("link") or ""}
                fid=hashlib.sha256((title.lower()+"|"+item["source"].lower()).encode()).hexdigest()[:24]
                item["id"]=fid
                out[fid]=item
        except Exception as exc:
            errs.append(type(exc).__name__)
    return list(out.values()),errs


def _signal(item:dict,state:dict) -> dict | None:
    blob=item.get("title","")+" "+item.get("description","")
    low=blob.lower()
    if not _is_verified_samsung(item):
        return None
    if not ("갤럭시 버즈 온" in low or "galaxy buds on" in low):
        return None
    metrics=state.get("metrics") or BASELINE
    markets={
        "미국": ("미국", "united states", "u.s.", "usa"),
        "일본": ("일본", "japan"),
        "중국": ("중국", "china"),
        "인도": ("인도", "india"),
        "유럽": ("유럽", "europe"),
    }
    if any(x in low for x in (
        "해외 판매 시작", "현지 판매 시작", "launches in",
        "available in", "on sale in", "sales start in"
    )):
        for region, aliases in markets.items():
            if any(x in low for x in aliases) and region not in (state.get("released_markets") or []):
                return {"kind": "market_launch", "value": region, "item": item}
    # ISO timestamps already checked by _news_items.
    on_or_after_release=(item.get("published_at_kst","")[:10] >= "2026-10-27")
    if (metrics.get("status")!="국내 정식판매 확인" and on_or_after_release
        and any(k in low for k in ("판매 시작", "정식 출시", "구매 가능", "now available", "officially available", "goes on sale"))):
        return {"kind":"launch","value":"국내 정식판매 확인", "item":item}
    # A new price must be marked as a CHANGE; the old KRW299,000 baseline
    # appearing in the text of another announcement cannot be a new signal.
    if any(k in low for k in ("가격 인상", "가격 변경", "판매가 변경", "price increase", "new price")):
        values=[int(x.replace(",","")) for x in re.findall(r"(\d{3},\d{3})\s*원",blob)]
        uniq=set(x for x in values if 100000<=x<=600000)
        if len(uniq)==1:
            val=next(iter(uniq))
            old=int(metrics.get("korean_price_krw") or 299000)
            if abs(val-old)>=10000:
                return {"kind":"price","value":val,"old":old,"item":item}
    return None


def _load_state() -> dict:
    if not STATE.exists():
        return {"schema_version":1,"initial_alert_sent":False,
                "metrics":dict(BASELINE),"seen_ids":[],"last_alert":None}
    try:
        state=json.loads(STATE.read_text(encoding="utf-8"))
        if not isinstance(state,dict):
            raise ValueError("Invalid JSON state")
        return state
    except Exception as exc:
        raise RuntimeError("Galaxy Buds On state invalid; no baseline replay") from exc


def _merge_buds_state(remote:dict,local:dict) -> dict:
    newer=local if str(local.get("updated_at_kst") or "") >= str(remote.get("updated_at_kst") or "") else remote
    older=remote if newer is local else local
    result=dict(older)
    result.update(newer)
    result["initial_alert_sent"]=bool(remote.get("initial_alert_sent") or local.get("initial_alert_sent"))
    result["seen_ids"]=sorted(set(remote.get("seen_ids") or [])|set(local.get("seen_ids") or []))[-600:]
    result["released_markets"]=sorted(set(remote.get("released_markets") or [])|set(local.get("released_markets") or []))
    if any((x.get("metrics") or {}).get("status")=="국내 정식판매 확인" for x in (remote,local)):
        result["metrics"]=dict(result.get("metrics") or {})
        result["metrics"]["status"]="국내 정식판매 확인"
    return result


def _baseline_message() -> str:
    return "\n".join([
        "🎧 <b>[갤럭시 버즈 온 | 신사업 출시 기준선]</b>",
        "━━━━━━━━━━━━━━━━",
        "• 삼성전자 공식 10월 1일 공개: 갤럭시 최초 클립형 무선 이어폰.",
        "• 국내 10월 27일 출시 예정 / 블랙 / 판매가 <b>299,000원</b>.",
        "• 10월 20일 브리핑은 기존 공개 제품의 기술 설명으로 재출시가 아닙니다.",
        "• 형상기억합금 밴드·음 누출 저감·헤드 제스처·스마트폰 AI 연동.",
        "• 판매·주문 대수, 해외 출시국별 일정, 협력사 부품 매출은 아직 공개되지 않았습니다.",
        "• 차기 알림: 10월 27일 실제 국내 판매 시작 확인, 공식 가격 변경, 해외 판매 개시.",
        f'<a href="{OFFICIAL}">삼성전자 공식 제품 발표</a>',
        f'<a href="{YONHAP}">연합뉴스 10월 20일 브리핑</a>',
    ])+"\n"


def _append(msg:str) -> None:
    existing=TELEGRAM.read_text(encoding="utf-8").strip() if TELEGRAM.exists() else ""
    TELEGRAM.write_text((existing+"\n\n" if existing else "")+msg,encoding="utf-8")


def main() -> None:
    now=dt.datetime.now(KST)
    state=_load_state()
    metrics=dict(BASELINE)
    metrics.update(state.get("metrics") or {})
    errors=[]
    try:
        official_ok=_official_baseline_present(_fetch(OFFICIAL))
    except Exception as exc:
        errors.append("official:"+type(exc).__name__)
        official_ok=False
    items,errs=_news_items(now)
    errors+=errs
    alerts=[]
    seen=set(state.get("seen_ids") or [])
    if not state.get("initial_alert_sent"):
        if official_ok:
            alerts.append(_baseline_message())
            state["initial_alert_sent"]=True
        else:
            errors.append("Samsung official source did not confirm baseline")
    for item in items:
        fid=item["id"]
        if fid in seen:
            continue
        if alerts:
            # Do not consume the next potentially actionable event: retry next run.
            break
        seen.add(fid)
        if not state.get("initial_alert_sent"):
            continue
        signal=_signal(item, {"metrics": metrics, "released_markets": state.get("released_markets") or []})
        if signal is None:
            continue
        if signal["kind"]=="launch":
            metrics["status"]=signal["value"]
            message="삼성전자 공식: 갤럭시 버즈 온 국내 정식판매 개시 확인"
        elif signal["kind"]=="market_launch":
            released=set(state.get("released_markets") or [])
            released.add(signal["value"])
            state["released_markets"]=sorted(released)
            message=f"삼성전자 공식: 갤럭시 버즈 온 {signal['value']} 지역 판매 개시 확인"
        else:
            metrics["korean_price_krw"]=signal["value"]
            message=f"국내 공식 판매가 {signal['old']:,}원 → {signal['value']:,}원 변경"
        alerts.append(
            "🎧 <b>[갤럭시 버즈 온 | 새로운 상용화 사실]</b>\n"
            f"• {html.escape(message)}\n"
            f'<a href="{html.escape(item["link"],quote=True)}">삼성전자 원문</a>'
        )

    state.update({
        "schema_version":1,
        "updated_at_kst":now.isoformat(timespec="seconds"),
        "metrics":metrics,
        "seen_ids":sorted(seen)[-600:],
        "last_scan_count":len(items),
        "last_new_signal_count":len(alerts),
        "errors":errors[-20:],
        "last_alert":{"at_kst":now.isoformat(timespec="seconds"),"count":len(alerts)}
            if alerts else state.get("last_alert"),
    })
    PENDING.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if alerts:
        text="\n\n".join(alerts)
        ALERT.write_text(text+"\n",encoding="utf-8")
        _append(text+"\n")
    else:
        ALERT.unlink(missing_ok=True)
    STATUS.write_text(
        "# 삼성전자 갤럭시 버즈 온 출시·판매 감시\n"
        f"- 검사: {now.isoformat(timespec='seconds')}\n"
        f"- 삼성 공식 페이지: {'확인' if official_ok else '확인 불가'}\n"
        f"- 뉴스 검색: {len(items)} / 신규신호: {len(alerts)}\n"
        f"- 상태: {metrics.get('status')} / 예정 10월27일, 299,000원\n"
        f"- 오류: {errors}\n",encoding="utf-8"
    )


if __name__=="__main__":
    main()
