#!/usr/bin/env python3
"""Official SEC beneficial ownership changes for the existing 13F manager list.

No new workflow, no historical replays, no inference from an issuer-side filing.
Situational Awareness already has its own ownership lane and is not duplicated.
Only exact reporting-person CIK matches are eligible for delivery.
"""
import datetime as dt
import hashlib
import os
import re
import sys
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET
import thirteenf_sector_watch as w

FORMS={"SCHEDULE 13D","SCHEDULE 13D/A","SCHEDULE 13G","SCHEDULE 13G/A",
       "SC 13D","SC 13D/A","SC 13G","SC 13G/A"}
SAMPLE={"cik":"0001393818","accession":"0001193125-26-455574",
        "filing_date":"2026-11-10","form":"SCHEDULE 13D/A",
        "primary_document":"primary_doc.xml","issuer_hint":"0001730463"}


def norm_cik(value):
    raw=str(value or "").strip()
    return raw.zfill(10) if raw.isdigit() and len(raw)<=10 and int(raw)>0 else ""


def field(node,*names):
    wanted={x.lower() for x in names}
    for child in node:
        if w.local_name(child.tag).lower() in wanted and (child.text or "").strip():
            return (child.text or "").strip()
    return ""


def deep_field(node,*names):
    wanted={x.lower() for x in names}
    for child in node.iter():
        if w.local_name(child.tag).lower() in wanted and (child.text or "").strip():
            return (child.text or "").strip()
    return ""


def number(raw,percent=False):
    if not raw:
        return None
    try:
        value=Decimal(str(raw).strip().replace(",","").rstrip("%"))
    except InvalidOperation as exc:
        raise ValueError("Invalid SEC ownership number") from exc
    if not value.is_finite() or value<0 or (percent and value>100):
        raise ValueError("Invalid SEC ownership range")
    return value


def rows_from_submissions(payload,cik):
    actual=norm_cik(payload.get("cik"))
    if actual and actual!=cik:
        raise ValueError("SEC submissions CIK mismatch")
    recent=payload["filings"]["recent"]
    fields=[recent.get(k) for k in ("form","accessionNumber","filingDate","primaryDocument")]
    if not all(isinstance(x,list) for x in fields) or len({len(x) for x in fields})!=1:
        raise ValueError("Incomplete SEC submission arrays")
    rows=[]
    for form,acc,date,document in zip(*fields):
        form=str(form).upper().strip()
        if form not in FORMS:
            continue
        if not re.fullmatch(r"\d{10}-\d{2}-\d{6}",str(acc)):
            raise ValueError("Invalid SEC ownership accession")
        dt.date.fromisoformat(date)
        pieces=str(document).split("/")
        if any(not re.fullmatch(r"[A-Za-z0-9_.-]+",x) or x in (".","..") for x in pieces):
            raise ValueError("Invalid SEC document path")
        rows.append({"cik":cik,"accession":acc,"filing_date":date,
                     "form":form,"primary_document":pieces[-1]})
    return sorted(rows,key=lambda x:(x["filing_date"],x["accession"]))


def official_archive_candidates(row):
    """EDGAR full-text index fallback; only exact accession and SEC CIKs."""
    day=row["filing_date"]
    query=urlencode({"dateRange":"custom","startdt":day,"enddt":day,
                     "ciks":row["cik"],"forms":row["form"]})
    payload=w.http_json("https://efts.sec.gov/LATEST/search-index?"+query)
    candidates=[]
    for hit in (payload.get("hits") or {}).get("hits",[]):
        source=hit.get("_source") or {}
        if str(source.get("adsh") or "")!=row["accession"]:
            continue
        for raw in source.get("ciks") or []:
            cik=norm_cik(raw)
            if cik and cik not in candidates:
                candidates.append(cik)
    return candidates


def read_xml(row):
    doc=row.get("primary_document") or "primary_doc.xml"
    if not re.fullmatch(r"[A-Za-z0-9_.-]+\.xml",doc,re.I):
        # Structured filings since SEC's 2024 machine-readable mandate.
        raise RuntimeError("Structured SEC ownership XML unavailable")
    tried=set()
    def try_ciks(ciks):
        for cik in ciks:
            cik=norm_cik(cik)
            if not cik or cik in tried:
                continue
            tried.add(cik)
            url=w.filing_dir(cik,row["accession"])+"/"+doc
            try:
                root=ET.fromstring(w.http_text(url))
                if w.local_name(root.tag)!="edgarSubmission" or not re.search(r"schedule13[dg]",root.tag,re.I):
                    raise ValueError("Not SEC schedule13D/G XML")
                return root,url,cik
            except Exception:
                continue
        return None
    result=try_ciks([row["cik"],row.get("issuer_hint")])
    if result:
        return result
    result=try_ciks(official_archive_candidates(row))
    if result:
        return result
    raise RuntimeError("SEC ownership primary XML not verified")


def parse_document(root,cik):
    headers=[n for n in root.iter() if w.local_name(n.tag).lower() in ("coverpageheader","coverpage")]
    header=headers[0] if headers else root
    issuer=deep_field(header,"issuerName","nameOfIssuer")
    issuer_cik=norm_cik(deep_field(header,"issuerCik"))
    title=deep_field(header,"titleOfClass","securityTitle","titleOfSecurities")
    date=deep_field(header,"dateOfEvent","dateOfEventRequiresFiling","eventDate","eventDateRequiresFiling")
    owners=[]
    known_ids=set()
    for node in root.iter():
        name=field(node,"reportingPersonName")
        if not name:
            continue
        owner_cik=norm_cik(field(node,"reportingPersonCIK","reportingCik"))
        if owner_cik:
            known_ids.add(owner_cik)
        if owner_cik!=cik:
            continue
        shares=number(field(node,"aggregateAmountOwned","reportingPersonBeneficiallyOwnedAggregateNumberOfShares"))
        pct=number(field(node,"percentOfClass","classPercent","amountAsPercent"),percent=True)
        owners.append({"name":name,"shares":shares,"pct":pct})
    if not owners:
        if known_ids or issuer_cik==cik:
            return None  # subject-side or different reporting person; not a manager trade
        raise RuntimeError("Reporting-person identity unavailable")
    if len(owners)!=1 or not issuer:
        raise RuntimeError("Ambiguous owner/issuer in SEC filing")
    owner=owners[0]
    owner.update({"issuer":issuer,"issuer_cik":issuer_cik,"security":title,
                  "event_date":date,"previous":deep_field(root,"previousAccessionNumber"),
                  "purpose":deep_field(root,"transactionPurpose","purposeOfTransaction")})
    return owner


def exact_prior(row,current):
    accession=current.get("previous") or ""
    if not re.fullmatch(r"\d{10}-\d{2}-\d{6}",accession) or accession==row["accession"]:
        return None
    prev=dict(row,accession=accession,issuer_hint=current.get("issuer_cik"))
    try:
        root,_,_=read_xml(prev)
        old=parse_document(root,row["cik"])
        if not old or old["issuer"].upper()!=current["issuer"].upper():
            return None
        if not old.get("security") or old["security"].upper()!=current.get("security","").upper():
            return None
        return old
    except Exception:
        return None


def fmt(value,suffix):
    if value is None:
        return "미기재"
    return f"{value:,f}".rstrip("0").rstrip(".")+suffix if "." in format(value,"f") else f"{value:,f}"+suffix


def message(label,row,current,previous,url):
    owner=w.MANAGER_KR.get(label,label)
    lines=[f"[13D/G 지분신고] {owner}",
           f"신고 종류: {row['form']} · 제출 {row['filing_date']}",
           f"■ 신고 법인: {current['name']}",
           f"■ 발행사: {current['issuer']} · {current['security'] or '증권 종류 미확인'}",
           f"■ 사건 기준일: {current['event_date'] or '공시 별도 확인'}"]
    if previous and current["shares"] is not None and previous["shares"] is not None:
        lines.append(f"■ 보유 수량: {fmt(previous['shares'],'주')} → {fmt(current['shares'],'주')}")
    else:
        lines.append(f"■ 이번 신고 보유 수량: {fmt(current['shares'],'주')}")
    if previous and current["pct"] is not None and previous["pct"] is not None:
        lines.append(f"■ 보유 지분율: {fmt(previous['pct'],'%')} → {fmt(current['pct'],'%')}")
    else:
        lines.append(f"■ 이번 신고 지분율: {fmt(current['pct'],'%')}")
    if not previous and row["form"].endswith("/A"):
        lines.append("※ 직전 원문 비교 미확인: 신규 매수·매도 방향 단정 금지.")
    if current.get("purpose") and previous and current["purpose"]!=previous.get("purpose"):
        lines.append("■ 신고 목적 문구 변경 확인: SEC 원문에서 확인.")
    lines.extend(["※ 특정 발행사 지분 신고이며 13F 전체 포트폴리오·실제 체결대금과 다릅니다.",
                  "SEC 공식 원문: "+url])
    return "\n".join(lines)


def self_test():
    raw="""<edgarSubmission xmlns="http://www.sec.gov/edgar/schedule13d">
    <formData><coverPageHeader><issuerInfo><issuerName>Example Inc</issuerName><issuerCik>987</issuerCik></issuerInfo>
    <titleOfClass>COMMON STOCK</titleOfClass><dateOfEvent>2026-11-27</dateOfEvent></coverPageHeader>
    <reportingPersons><reportingPersonInfo><reportingPersonCIK>0001393818</reportingPersonCIK>
    <reportingPersonName>Blackstone Inc.</reportingPersonName><aggregateAmountOwned>120000</aggregateAmountOwned>
    <percentOfClass>5.5</percentOfClass></reportingPersonInfo></reportingPersons></formData></edgarSubmission>"""
    root=ET.fromstring(raw)
    owner=parse_document(root,"0001393818")
    assert owner["shares"]==Decimal("120000") and owner["pct"]==Decimal("5.5")
    assert parse_document(root,"0000000987") is None
    previous=dict(owner,shares=Decimal("100000"),pct=Decimal("5"))
    msg=message("Blackstone",SAMPLE,owner,previous,"https://www.sec.gov/Archives/test.xml")
    assert "100,000주 → 120,000주" in msg and "5% → 5.5%" in msg
    assert "실제 체결대금과 다릅니다" in msg
    print("13DG_OWNERSHIP_IDENTITY_REGRESSION_PASS no_network=true no_telegram_send=true")


def main():
    state=w.load_state()
    if state.get("pending_ownership_13dg"):
        print("13DG_DELIVERY_UNCERTAIN: reservation preserved; not retried",file=sys.stderr)
        return
    lane=state.setdefault("ownership_13dg",{"baseline":{},"observed":{},"source_validated":False})
    if not lane.get("source_validated"):
        # Deployment gate: official live XML must establish actual reporting CIK.
        try:
            root,url,_=read_xml(SAMPLE)
            sample=parse_document(root,SAMPLE["cik"])
            if not sample or sample["shares"] is None or sample["pct"] is None:
                raise RuntimeError("Live sample incomplete")
            lane["source_validated"]=True
            print("13DG_LIVE_OFFICIAL_SAMPLE_PASS reporting_cik_verified=true issuer="+sample["issuer"])
        except Exception as exc:
            print("13DG_LIVE_SAMPLE_UNVERIFIED "+type(exc).__name__+"; no ownership alerts",file=sys.stderr)
            return
    today=dt.datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    expected=sum(len(ciks) for label,ciks in w.MANAGERS.items() if label!="Situational Awareness")
    healthy=0
    confirmed=0
    blocked=0
    target=None
    token=(os.environ.get("THIRTEENF_TELEGRAM_BOT_TOKEN") or os.environ.get("KHS_POLICY_TELEGRAM_BOT_TOKEN") or "").strip()
    chat=(os.environ.get("THIRTEENF_TELEGRAM_CHAT_ID") or os.environ.get("KHS_POLICY_TELEGRAM_CHAT_ID") or "").strip()
    for label,ciks in w.MANAGERS.items():
        if label=="Situational Awareness":
            continue
        for cik in ciks:
            try:
                rows=rows_from_submissions(w.http_json(w.SEC_DATA+"/submissions/CIK"+cik+".json"),cik)
                healthy+=1
            except Exception as exc:
                print(f"13DG_SOURCE_ERROR {label} {type(exc).__name__}",file=sys.stderr)
                continue
            if cik not in lane["baseline"]:
                lane["baseline"][cik]={"date":today,"same_day":[r["accession"] for r in rows if r["filing_date"]==today]}
                print(f"13DG_BASELINE {label} existing_filings={len(rows)} no_replay=true")
                continue
            baseline=lane["baseline"][cik]
            for row in rows:
                key=cik+"|"+row["accession"]
                if key in lane["observed"] or row["filing_date"]<baseline["date"] or row["accession"] in baseline["same_day"]:
                    continue
                try:
                    root,url,archive=read_xml(row)
                    current=parse_document(root,cik)
                    if current is None:
                        lane["observed"][key]={"status":"not_reporting_owner"}
                        continue
                    previous=exact_prior(dict(row,issuer_hint=archive),current)
                    if previous and all(current[k]==previous[k] for k in ("shares","pct","purpose")):
                        lane["observed"][key]={"status":"no_verified_change"}
                        continue
                    if current["shares"] is None and current["pct"] is None and not current.get("purpose"):
                        raise RuntimeError("No current ownership fields")
                    msg=message(label,row,current,previous,url)
                except Exception as exc:
                    blocked+=1
                    print(f"13DG_PARSE_UNCONFIRMED {label} {row['accession']} {type(exc).__name__}",file=sys.stderr)
                    continue
                if not token or not chat:
                    raise RuntimeError("Existing Telegram route missing")
                if target is None:
                    w.verify_bot(token)
                    target=w.telegram_api(token,"getChat",{"chat_id":chat}).get("id")
                    if type(target) is not int or not target or (chat.lstrip("-").isdigit() and int(chat)!=target):
                        raise RuntimeError("Existing Telegram recipient not verified")
                state["pending_ownership_13dg"]={"key":key,"reserved_at":dt.datetime.now(dt.timezone.utc).isoformat()}
                w.persist_delivery_state(state,"Reserve verified SEC ownership delivery")
                receipt=w.send_message(token,str(target),msg)
                mid=(receipt or {}).get("message_id")
                actual=((receipt or {}).get("chat") or {}).get("id")
                if type(mid) is not int or mid<=0 or actual!=target:
                    raise RuntimeError("SEC ownership delivery uncertain; reservation preserved")
                lane["observed"][key]={"status":"delivered","message_id":mid,
                    "recipient_fingerprint":hashlib.sha256(str(actual).encode()).hexdigest()[:16]}
                state.pop("pending_ownership_13dg",None)
                w.persist_delivery_state(state,"Confirm verified SEC ownership delivery")
                confirmed+=1
    w.save_state(state)
    print(f"13DG_SOURCE_COVERAGE {healthy}/{expected} initialized={len(lane['baseline'])} confirmed={confirmed} parse_blocked={blocked}")
    if healthy!=expected or blocked:
        print("13DG_PARTIAL_COVERAGE no-all-clear",file=sys.stderr)
    elif not confirmed:
        print("13DG_NO_NEW_VERIFIED_FILING no_telegram_send=true")
