function content(value) {
    const iterate =
      typeof value === "string" ? undefined : value?.[iteratorKey];
    if (typeof iterate !== "function") {
      return emitBlock(value);
    }

    // Reuse the method from a potentially stateful getter, with its original
    // receiver. The for-of loop closes the iterator if the host rejects a block.
    const blocks = { [iteratorKey]: () => apply(iterate, value, []) };
    for (const block of blocks) {
      emitBlock(block);
    }
  }

# One-time value-restored correction to the already delivered 2026-Q3
# cross-manager comparison (the original report remains immutable).
Q3_VALUE_KEY="verified-13f-q3-value-addendum-20261117-v1"


def q3_amount_ready(state):
    if Q3_COMPARE_KEY not in state.get("seen_context_events",[]):
        return False
    if Q3_VALUE_KEY in state.get("seen_context_events",[]):
        return False
    if state.get("q3_value_pending_delivery"):
        return False
    return all((state.get("managers",{}).get(k) or {}).get("report_date")==Q3_REPORT_DATE
               for k in Q3_FOCUS_MANAGERS)


def _q3_valuation(snapshots,label,term,quarter="current",pc=""):
    """Verified SEC reference value for matched issuer and security type.

    Factor 1000 applies ONLY to independently reconciled Duquesne 2026Q2/Q3.
    All other 2026 values remain the SEC-specified actual-dollar fields.
    """
    import thirteenf_sector_rank as ranking
    snap=snapshots[label]
    accession=snap["accession" if quarter=="current" else "previous_accession"]
    scale=ranking.verified_scale(label,{"accession":accession})
    if scale is None:
        raise RuntimeError(f"13F valuation unit not verified: {label} {accession}")
    rows=[row for row in snap[quarter].values()
          if term.upper() in str(row.get("issuer") or "").upper()
          and str(row.get("putcall") or "").upper()==pc]
    shares=sum(float(r["shares"]) for r in rows)
    value=sum(float(r["value"]) for r in rows)*scale
    return (shares,value)


def _q3_reference_change(snapshots,label,term,short):
    old_n,old_value=_q3_valuation(snapshots,label,term,"previous")
    new_n,new_value=_q3_valuation(snapshots,label,term,"current")
    delta=new_n-old_n
    if delta==0:
        return None
    if delta>0:
        if new_n<=0:
            return None
        usd=new_value*delta/new_n
        status="신규·확대"
    else:
        if old_n<=0:
            return None
        usd=old_value*(-delta)/old_n
        status="축소·신고상 소멸"
    return {"label":short,"status":status,"change":int(delta),"usd":usd,
            "q":"3분기말" if delta>0 else "2분기말"}


def build_q3_amount_addendum(snapshots,rate,basis):
    """A short money-reference supplement, not executed trading cash."""
    import math
    import thirteenf_sector_watch_entry as entry
    if not math.isfinite(float(rate)) or rate<=0:
        raise ValueError("Q3 amount supplement missing validated USD/KRW")
    if any(k not in snapshots for k in Q3_FOCUS_MANAGERS):
        raise RuntimeError("Q3 money supplement requires six SEC-sourced managers")

    # Hard guards on cross-reconciled independent Q3/2026-Q2 observations:
    stx_current=_q3_valuation(snapshots,"Duquesne Family Office","SEAGATE")[1]
    stx_previous=_q3_valuation(snapshots,"Duquesne Family Office","SEAGATE","previous")[1]
    shaz=_q3_valuation(snapshots,"Situational Awareness","SHARONAI")[1]
    if not (310_000_000<=stx_current<=320_000_000
            and 115_000_000<=stx_previous<=125_000_000
            and 435_000_000<=shaz<=445_000_000):
        raise RuntimeError("SEC amount reference did not match independent Q3/Q2 valuation checks")

    def fmt(usd):
        return entry._usd_text(usd)+" ("+entry._krw_text(usd*rate)+")"
    def line(label,term,short):
        row=_q3_reference_change(snapshots,label,term,short)
        if row is None:
            return f"• {short}: 보유수량 변동 없음"
        label_sign="+" if row["change"]>0 else "-"
        return (f"• {short}: {label_sign}{abs(row['change']):,}주"
                f" · 변경분 {fmt(row['usd'])}"
                f" ({row['q']} 단가 기준)")

    d="Duquesne Family Office"
    a="Situational Awareness"
    n="NVIDIA"
    tp="Third Point"
    ap="Appaloosa"
    lines=[
        "[13F 평가액 보강 | 2026년 3분기 · 기존 교차검증 후속]",
        f"환율 1달러={rate:,.2f}원 ({basis})",
        "참고 평가액이며 실제 매수·매도 체결금액이 아닙니다.",
        "듀케인 Q2·Q3 제출액은 독립 검증된 원문 단위 차이에 한해 ×1,000 보정.",
        "",
        "■ 듀케인 확대(3분기말 기준)",
        line(d,"SEAGATE","시게이트(STX)"),
        line(d,"UNITY SOFTWARE","유니티(U)"),
        line(d,"AMAZON","아마존(AMZN)"),
        "■ 듀케인 축소(2분기말 기준)",
        line(d,"TAIWAN SEMICONDUCTOR","TSMC(TSM)"),
        line(d,"STMICRO","STM(STM)"),
        "",
        "■ 시추에이셔널: 메모리 보통주 신고상 소멸",
        line(a,"MICRON","마이크론(MU)"),
        line(a,"SANDISK","샌디스크(SNDK)"),
        "■ 시추에이셔널: 샤론AI 확대",
        line(a,"SHARONAI","샤론AI(SHAZ)"),
        "",
        "■ 반대 매매 사례",
        line(ap,"MICRON","아팔루사 MU"),
        line(tp,"NVIDIA","서드포인트 NVDA"),
        line(n,"INTEL","엔비디아 INTC"),
        "",
        "※ 기존 비교 알림의 금액 보강본이며 신규 13F 공시는 아닙니다.",
        "※ 모든 변경분 평가액은 증가수량×3분기말 단가 또는"
        " 감소수량×2분기말 단가입니다. 두 값을 차감해 순현금흐름으로 해석하지 마세요.",
        "SEC 듀케인: "+snapshots[d]["url"],
        "SEC 시추에이셔널: "+snapshots[a]["url"],
    ]
    result="\n".join(lines)
    if len(result)>3600:
        raise RuntimeError(f"Q3 amount addendum exceeds Telegram limit: {len(result)}")
    return result


def q3_amount_followup_main():
    state=w.load_state()
    if not q3_amount_ready(state):
        print("Q3_AMOUNT_FOLLOWUP_NO_ACTION already_sent_or_pending")
        return False
    snapshots=_q3_snapshots(state)
    from fx_api import daily_krw
    quote=daily_krw()
    report=build_q3_amount_addendum(snapshots,quote.rate,quote.basis)
    if (os.getenv("THIRTEENF_Q3_AMOUNT_PROBE_ONLY","true").lower()=="true"
            or os.getenv("THIRTEENF_Q3_AMOUNT_ENABLED","false").lower()!="true"):
        print(f"Q3_AMOUNT_VERIFIED_PROBE managers={len(snapshots)} chars={len(report)}")
        print("Q3_AMOUNT_PREVIEW_BEGIN\n"+report+"\nQ3_AMOUNT_PREVIEW_END")
        return False
    token=(os.getenv("THIRTEENF_TELEGRAM_BOT_TOKEN") or "").strip()
    chat=(os.getenv("THIRTEENF_TELEGRAM_CHAT_ID") or
          os.getenv("KHS_POLICY_TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat:
        raise RuntimeError("Q3 amount followup Telegram secret unavailable")
    name=w.verify_bot(token)
    if name.lower()!="khs887988798879_bot":
        raise RuntimeError("Unexpected Q3 followup bot")
    state["q3_value_pending_delivery"]={
        "key":Q3_VALUE_KEY,
        "reserved_utc":__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "accessions":{k:v["accession"] for k,v in snapshots.items()},
    }
    w.save_state(state)
    import subprocess,time
    subprocess.run(["git","config","user.name","github-actions[bot]"],check=True)
    subprocess.run(["git","config","user.email","41898282+github-actions[bot]@users.noreply.github.com"],check=True)
    subprocess.run(["git","add",w.STATE_PATH.as_posix()],check=True)
    subprocess.run(["git","commit","-m","Reserve one-time Q3 13F verified amount addendum"],check=True)
    confirmed=False
    for attempt in range(4):
        subprocess.run(["git","fetch","origin","main"],check=True)
        subprocess.run(["git","rebase","origin/main"],check=True)
        push=subprocess.run(["git","push","origin","HEAD:main"],capture_output=True,text=True)
        if push.returncode==0:
            confirmed=True
            break
        time.sleep(attempt+1)
    if not confirmed:
        raise RuntimeError("Could not commit Q3 value addendum reservation; no Telegram send")
    print("Q3_AMOUNT_PRE_SEND_RESERVATION_COMMITTED")
    # One send only; ambiguous response blocks replay until manual reconciliation.
    receipt=w.telegram_api(token,"sendMessage",{
        "chat_id":chat,"text":report,"disable_web_page_preview":"true",
    })
    mid=(receipt or {}).get("message_id")
    chat_result=str((receipt.get("chat") or {}).get("id") or "")
    if mid is None or not chat_result or (chat.lstrip("-").isdigit() and chat_result!=chat):
        raise RuntimeError("Q3 value addendum Telegram receipt incomplete; no auto resend")
    state.pop("q3_value_pending_delivery",None)
    state["seen_context_events"]=sorted(set(state.get("seen_context_events",[]))|{Q3_VALUE_KEY})
    state.setdefault("context_receipts",{})[Q3_VALUE_KEY]={
        "message_id":mid,"bot":name,"confirmed_at":__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "accessions":{k:v["accession"] for k,v in snapshots.items()},
    }
    w.save_state(state)
    print(f"Q3_AMOUNT_TELEGRAM_CONFIRMED chat_match=true message_id={mid}")
    return True
