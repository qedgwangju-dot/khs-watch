#!/usr/bin/env python3
"""러시아산 경유 공급·OFAC 제135호 별도 사건 확인.

기존 이란·호르무즈 감시가 생성한 출력을 우선하며 같은 Telegram 발송/상태 갱신 경로를 재사용한다.
"""
from __future__ import annotations
import argparse
import datetime as dt
import email.utils
import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

UTC = dt.timezone.utc
KST = ZoneInfo("Asia/Seoul")
OFAC_URL = "https://ofac.treasury.gov/recent-actions/20261009_33"
STATE = pathlib.Path("data/russian_diesel_supply_state.json")
PENDING = pathlib.Path("out/russian_diesel_supply_pending.json")
QUERIES = (
    '"Russia" "diesel" "Putin" "300,000" when:3d',
    '"Russian diesel" "General License 135" OFAC when:3d',
    '"Trump" "Putin" "diesel" supply agreement when:3d',
    '트럼프 푸틴 러시아 경유 공급 합의 제재 완화 when:3d',
)

def norm(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip().lower()

def publisher(source: str, title: str) -> str:
    a, b = norm(source), norm(title)
    if "reuters" in a or "marketscreener" in a or "euronext" in a or b.endswith(" - reuters"):
        return "reuters"
    if "associated press" in a or a in ("ap","ap news"):
        return "ap"
    if "연합뉴스" in a or "yonhap" in a:
        return "yonhap"
    return a

def policy_headline(title: str) -> bool:
    a=norm(title)
    return (
        any(k in a for k in ("russia","russian","putin","러시아","푸틴","러 경유"))
        and any(k in a for k in ("diesel","gasoil","경유","디젤"))
        and any(k in a for k in ("deal","agreed","agreement","supply","export","sanction","license","import","공급","합의","수출","제재","면허"))
    )

def actual_shipment(title: str) -> bool:
    a=norm(title)
    if any(k in a for k in ("will ","expected","plans ","to be ","agreed","예정","계획")):
        return False
    return policy_headline(title) and any(k in a for k in ("shipments loaded","cargoes loaded","tankers departed","confirmed unloading","선적 확인","출항 확인","하역 완료"))

def official_item(raw: str, current: dt.datetime) -> dict:
    text=norm(re.sub(r"<[^>]*>", " ", re.sub(r"(?is)<script\b.*?</script>|<style\b.*?</style>"," ",raw)))
    if not (
        any(k in text for k in ("10/09/2026","october 9, 2026","october 09, 2026"))
        and "general license 135" in text
        and "diesel fuel of russian federation origin" in text
        and "sale, delivery, offloading, and importation" in text
    ):
        raise ValueError("OFAC 공식 원문 일자·면허번호·허용행위 검증 실패")
    return {"source":"OFAC","title":"러시아산 경유 거래 일반면허 제135호 발급",
            "url":OFAC_URL,"time":current.timestamp(),"official":True}

def parse_rss(raw: bytes, now: dt.datetime) -> list[dict]:
    root=ET.fromstring(raw)
    output=[]
    for node in root.findall(".//item"):
        title=node.findtext("title") or ""
        src=node.find("source")
        name=(src.text if src is not None and src.text else title.rsplit(" - ",1)[-1]).strip()
        if not policy_headline(title) or publisher(name,title) not in ("reuters","ap","yonhap"):
            continue
        try:
            stamp=email.utils.parsedate_to_datetime(node.findtext("pubDate") or "").astimezone(UTC).timestamp()
        except (TypeError, ValueError, OverflowError):
            continue
        if stamp < now.timestamp()-24*3600 or stamp > now.timestamp()+600:
            continue
        output.append({"source":name,"title":title,"url":node.findtext("link") or "",
                       "time":stamp,"official":False})
    return output

def observe(core, now: dt.datetime) -> tuple[str, list[dict]] | None:
    items=[]
    try:
        raw=core.fetch_bytes(OFAC_URL,timeout=15,attempts=2).decode("utf-8","replace")
        items.append(official_item(raw,now))
    except Exception as err:
        print(f"russian_diesel_official_unavailable={type(err).__name__}")
    for query in QUERIES:
        try:
            raw=core.fetch_bytes(core.google_news_url(query),timeout=12,attempts=2)
            items.extend(parse_rss(raw,now))
        except Exception as err:
            print(f"russian_diesel_news_feed_unavailable={type(err).__name__}")
    unique={}
    for row in sorted(items,key=lambda x:x["time"],reverse=True):
        key="ofac" if row["official"] else publisher(row["source"],row["title"])
        unique.setdefault(key,row)
    independent=list(unique.values())
    ofac=any(r["official"] for r in independent)
    physical={publisher(r["source"],r["title"]) for r in independent if actual_shipment(r["title"])}
    if len(physical)>=2:
        stage="shipment_confirmed"
    elif ofac:
        stage="license_issued"
    elif len(independent)>=2:
        stage="agreement_reported"
    else:
        return None
    return stage,sorted(independent,key=lambda x:(not x["official"],-x["time"]))

def event_key(stage: str) -> str:
    basis=f"russian_diesel_supply|2026-10-09|GL135|{stage}"
    return "russian_diesel_supply:"+hashlib.sha256(basis.encode()).hexdigest()[:16]

def make_body(core,stage: str, sources: list[dict], now:dt.datetime) -> str:
    labels={"license_issued":"OFAC 일반면허 제135호 발급 확인",
            "agreement_reported":"트럼프·푸틴 경유 공급 합의 발표",
            "shipment_confirmed":"러시아산 경유 실제 선적 보도 복수 확인"}
    lines=[now.astimezone(KST).strftime("%Y년 %m월 %d일 %H:%M KST"),"",
      "[한눈에]",
      "정책         "+labels[stage],
      "발표 규모    30만+50만+100만+조건부 300만 = 총 480만 톤",
      "환산 물량    약 3,571만 배럴 · 경유 7.44배럴/톤 가정",
      "공급 일정    첫 30만 톤 즉시 · 11월 50만 톤 · 이후 100만 톤 · 추가 300만 톤 조건부"]
    if stage!="shipment_confirmed":
        lines.append("실물         실제 선적·수입항 도착 미검증")
    lines += ["","[핵심]",
      "미국의 한시적 러시아산 경유 거래 허용은 러시아 에너지 제재 전체 해제가 아닙니다.",
      "→ 발표한 공급 계획과 실제 수출·선적·도착량을 구분합니다.",
      "","[한국 전이]",
      "정유         공급 증가가 실현되면 경유 정제마진 하방 가능성",
      "운송         경유 가격 하락 시 비용 완화 · 항공유는 별도 품목",
      "","[다음 확인]",
      "공식         OFAC 제135호 변경·종료, 러시아 국내 수출금지 완화",
      "선적         러시아 최초 30만 톤의 출항·실제 수입 통관",
      "가격         미국 초저유황경유·싱가포르 경유 정제마진, EIA 실제 수입",
      "","[근거]"]
    for row in sources[:3]:
        src="미 재무부 해외자산통제국" if row["official"] else core._source_name_ko(row["source"])
        desc="10월 9일 발행, 일반면허 제135호" if row["official"] else "러시아 경유 공급 관련 보도"
        lines.append(src+" · "+desc)
        if row["url"].startswith("https://"):
            lines.append("원문: "+row["url"])
    lines+=["","[주의]",
      "480만 톤은 트럼프 발표의 계획량이며 조건부 300만 톤도 포함됩니다. 인도 확정 물량이 아닙니다.",
      "원유·경유·항공유를 혼합 계산하지 않습니다. 제135호의 구체적인 예외 범위는 공식 문서 기준입니다."]
    return "\n".join(lines)+"\n"

def run() -> int:
    import iran_hormuz_market_turn_alert as core
    now=dt.datetime.now(UTC)
    PENDING.unlink(missing_ok=True)
    if core.BODY_PATH.exists():
        print("russian_diesel_queued=main_alert_already_pending")
        return 0
    result=observe(core,now)
    if result is None:
        print("russian_diesel_verified_new_event=false")
        return 0
    stage,sources=result
    state=json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"sent":[]}
    key=event_key(stage)
    if key in state.get("sent",[]) or (stage=="agreement_reported" and event_key("license_issued") in state.get("sent",[])):
        print("russian_diesel_duplicate_blocked=true")
        return 0
    core.OUT_DIR.mkdir(parents=True,exist_ok=True)
    core.TITLE_PATH.write_text("러시아 경유 공급 합의·미국 제재 예외 변화\n",encoding="utf-8")
    core.BODY_PATH.write_text(make_body(core,stage,sources,now),encoding="utf-8")
    core.ALERT_JSON_PATH.write_text(json.dumps({"event_kind":"russian_diesel_supply","event_id":key,"sources":sources},
        ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    core.PENDING_STATE_PATH.write_text(json.dumps(core.build_pending_state(core.load_state(),
        key,"russian_diesel_supply",now,{"oil":None,"usdkrw":None}),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    PENDING.write_text(json.dumps({"key":key,"stage":stage},ensure_ascii=False)+"\n",encoding="utf-8")
    print(f"russian_diesel_new_event={stage}")
    return 0

def finalize() -> int:
    import iran_hormuz_market_turn_alert as core
    if not PENDING.exists() or not core.TELEGRAM_CONFIRMED_PATH.exists():
        print("russian_diesel_state_finalize=skipped")
        return 0
    confirmed=json.loads(core.TELEGRAM_CONFIRMED_PATH.read_text(encoding="utf-8"))
    if confirmed.get("status")!="confirmed" or not isinstance(confirmed.get("message_id"),int):
        raise RuntimeError("Russian diesel Telegram confirmation missing")
    data=json.loads(PENDING.read_text(encoding="utf-8"))
    state=json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"sent":[]}
    state["sent"]=list(dict.fromkeys(state.get("sent",[])+[data["key"]]))
    state["last_stage"]=data["stage"]
    state["message_id"]=confirmed["message_id"]
    state["updated_kst"]=dt.datetime.now(KST).isoformat(timespec="seconds")
    STATE.parent.mkdir(parents=True,exist_ok=True)
    STATE.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"russian_diesel_state_saved=true message_id={confirmed['message_id']}")
    return 0

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--finalize",action="store_true")
    args=parser.parse_args()
    raise SystemExit(finalize() if args.finalize else run())
