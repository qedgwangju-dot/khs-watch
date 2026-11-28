#!/usr/bin/env python3
import datetime as dt
import json
import os
import pathlib
import sys
import subprocess
import hashlib
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict

SEC_BASE = "https://www.sec.gov"
SEC_DATA = "https://data.sec.gov"
STATE_PATH = pathlib.Path("data/thirteenf_sector_watch_state.json")
EXPECTED_BOT_USERNAME = "khs887988798879_bot"

RECOVER_MISSING_MANAGERS = set()

MANAGERS = {
    "Situational Awareness": ["0002045724"],
    "Duquesne Family Office": ["0001536411"],
    "Pershing Square": ["0001336528", "0002026053"],
    "Third Point": ["0001040273"],
    "NVIDIA": ["0001045810"],
    "Appaloosa": ["0001656456"],
    "Berkshire Hathaway": ["0001067983"],
}

MANAGER_KR = {
    "Situational Awareness": "시추에이셔널 어웨어니스",
    "Duquesne Family Office": "듀케인 패밀리 오피스",
    "Pershing Square": "퍼싱스퀘어",
    "Third Point": "서드포인트",
    "NVIDIA": "엔비디아",
    "Appaloosa": "아팔루사",
    "Berkshire Hathaway": "버크셔 해서웨이",
}

# SEC 원문 회사명은 검색·공시 식별을 위해 내부적으로 보존하고,
# Telegram 표시만 한국어 통용명 + 티커 중심으로 바꾼다.
SECURITY_DISPLAY_RULES = [
    ("AMAZON", "아마존(AMZN)"),
    ("MICROSOFT", "마이크로소프트(MSFT)"),
    ("META PLATFORMS", "메타(META)"),
    ("CLOUDFLARE", "클라우드플레어(NET)"),
    ("UBER", "우버(UBER)"),
    ("NVIDIA", "엔비디아(NVDA)"),
    ("BROADCOM", "브로드컴(AVGO)"),
    ("MICRON", "마이크론(MU)"),
    ("SANDISK", "샌디스크(SNDK)"),
    ("ADVANCED MICRO", "AMD(AMD)"),
    ("INTEL", "인텔(INTC)"),
    ("TAIWAN SEMICONDUCTOR", "TSMC(TSM)"),
    ("STMICRO", "ST마이크로일렉트로닉스(STM)"),
    ("ARM HOLDINGS", "Arm(ARM)"),
    ("LAM RESEARCH", "램리서치(LRCX)"),
    ("KLA CORP", "KLA(KLAC)"),
    ("ENTEGRIS", "인테그리스(ENTG)"),
    ("RAMBUS", "램버스(RMBS)"),
    ("NAVITAS", "나비타스 세미컨덕터(NVTS)"),
    ("RIOT PLATFORMS", "라이엇 플랫폼스(RIOT)"),
    ("BITDEER", "비트디어(BTDR)"),
    ("EQUINIX", "에퀴닉스(EQIX)"),
    ("HUT 8", "헛8(HUT)"),
    ("IREN LTD", "아이렌(IREN)"),
    ("CORE SCIENTIFIC", "코어 사이언티픽(CORZ)"),
    ("DIGITAL REALTY", "디지털 리얼티(DLR)"),
    ("NETFLIX", "넷플릭스(NFLX)"),
    ("WARNER BROS", "워너브라더스 디스커버리(WBD)"),
    ("FOX CORP", "폭스(FOX/FOXA)"),
    ("LIVE NATION", "라이브네이션(LYV)"),
    ("NEW YORK TIMES", "뉴욕타임스(NYT)"),
    ("PARAMOUNT", "파라마운트(PSKY)"),
    ("SPOTIFY", "스포티파이(SPOT)"),
    ("VISA", "비자(V)"),
    ("MASTERCARD", "마스터카드(MA)"),
    ("INTERCONTINENTAL EXCHANGE", "인터컨티넨털 익스체인지(ICE)"),
    ("S&P GLOBAL", "S&P 글로벌(SPGI)"),
    ("BLOCK INC", "블록(XYZ)"),
    ("MOODYS", "무디스(MCO)"),
    ("CME GROUP", "CME 그룹(CME)"),
    ("BANK OF AMERICA", "뱅크오브아메리카(BAC)"),
    ("CAPITAL ONE", "캐피털원(COF)"),
    ("ALLY FINANCIAL", "앨리 파이낸셜(ALLY)"),
    ("CITIGROUP", "씨티그룹(C)"),
    ("JPMORGAN", "JP모건(JPM)"),
    ("GOLDMAN SACHS", "골드만삭스(GS)"),
    ("MORGAN STANLEY", "모건스탠리(MS)"),
    ("DELTA AIR", "델타항공(DAL)"),
    ("UNITED AIR", "유나이티드항공(UAL)"),
    ("BOEING", "보잉(BA)"),
    ("SOUTHWEST AIR", "사우스웨스트항공(LUV)"),
    ("AMERICAN AIR", "아메리칸항공(AAL)"),
    ("BOOKING HOLDINGS", "부킹홀딩스(BKNG)"),
    ("D R HORTON", "D.R. 호튼(DHI)"),
    ("DR HORTON", "D.R. 호튼(DHI)"),
    ("LENNAR", "레나(LEN)"),
    ("HOWARD HUGHES", "하워드 휴즈(HHH)"),
    ("PULTEGROUP", "풀티그룹(PHM)"),
    ("NVR INC", "NVR(NVR)"),
    ("NATERA", "나테라(NTRA)"),
    ("ALCON", "알콘(ALC)"),
    ("DAVITA", "다비타(DVA)"),
    ("UNITEDHEALTH", "유나이티드헬스(UNH)"),
    ("ELI LILLY", "일라이 릴리(LLY)"),
    ("ABBVIE", "애브비(ABBV)"),
    ("MERCK", "머크(MRK)"),
    ("ALIBABA", "알리바바(BABA)"),
    ("PDD HOLDINGS", "PDD 홀딩스(PDD)"),
    ("JD.COM", "징둥닷컴(JD)"),
    ("BAIDU", "바이두(BIDU)"),
    ("KE HOLDINGS", "KE 홀딩스(BEKE)"),
    ("KROGER", "크로거(KR)"),
    ("CONSTELLATION BRANDS", "컨스텔레이션 브랜즈(STZ)"),
    ("RESTAURANT BRANDS", "레스토랑 브랜즈(QSR)"),
    ("MCDONALDS", "맥도날드(MCD)"),
    ("NIKE", "나이키(NKE)"),
    ("WALMART", "월마트(WMT)"),
    ("COSTCO", "코스트코(COST)"),
    ("ALCOA", "알코아(AA)"),
    ("NUCOR", "뉴코(NUE)"),
    ("CATERPILLAR", "캐터필러(CAT)"),
    ("DEERE", "디어(DE)"),
    ("GE AEROSPACE", "GE 에어로스페이스(GE)"),
    ("GENERAL ELECTRIC", "GE 에어로스페이스(GE)"),
    ("OCCIDENTAL", "옥시덴털 페트롤리엄(OXY)"),
    ("CHEVRON", "셰브론(CVX)"),
    ("EXXON", "엑슨모빌(XOM)"),
    ("CONOCOPHILLIPS", "코노코필립스(COP)"),
    ("EOG RESOURCES", "EOG 리소시스(EOG)"),
]

SECTOR_RULES = [
    ("AI 플랫폼·클라우드", ["ALPHABET", "AMAZON", "MICROSOFT", "META PLATFORMS", "CLOUDFLARE", "UBER"]),
    ("반도체·파운드리·장비", ["NVIDIA", "BROADCOM", "MICRON", "SANDISK", "ADVANCED MICRO", "INTEL", "TAIWAN SEMICONDUCTOR", "STMICRO", "ARM HOLDINGS", "LAM RESEARCH", "KLA CORP", "ENTEGRIS", "RAMBUS", "NAVITAS"]),
    ("AI 데이터센터·전력자산", ["RIOT PLATFORMS", "BITDEER", "EQUINIX", "HUT 8", "IREN LTD", "CORE SCIENTIFIC", "DIGITAL REALTY"]),
    ("미디어·콘텐츠", ["NETFLIX", "WARNER BROS", "FOX CORP", "LIVE NATION", "NEW YORK TIMES", "PARAMOUNT", "SPOTIFY"]),
    ("금융 인프라·결제·시장데이터", ["VISA", "MASTERCARD", "INTERCONTINENTAL EXCHANGE", "S&P GLOBAL", "BLOCK INC", "MOODYS", "CME GROUP"]),
    ("은행·신용", ["BANK OF AMERICA", "CAPITAL ONE", "ALLY FINANCIAL", "CITIGROUP", "JPMORGAN", "GOLDMAN SACHS", "MORGAN STANLEY"]),
    ("항공·항공우주·여행", ["DELTA AIR", "UNITED AIR", "BOEING", "SOUTHWEST AIR", "AMERICAN AIR", "BOOKING HOLDINGS"]),
    ("주택·부동산", ["D R HORTON", "DR HORTON", "LENNAR", "HOWARD HUGHES", "PULTEGROUP", "NVR INC"]),
    ("헬스케어", ["NATERA", "ALCON", "DAVITA", "UNITEDHEALTH", "ELI LILLY", "ABBVIE", "MERCK"]),
    ("중국 인터넷·소비", ["ALIBABA", "PDD HOLDINGS", "JD.COM", "BAIDU", "KE HOLDINGS"]),
    ("소비재·유통", ["KROGER", "CONSTELLATION BRANDS", "RESTAURANT BRANDS", "MCDONALDS", "NIKE", "WALMART", "COSTCO"]),
    ("소재·산업재", ["ALCOA", "NUCOR", "CATERPILLAR", "DEERE", "GENERAL ELECTRIC", "GE AEROSPACE"]),
    ("에너지", ["OCCIDENTAL", "CHEVRON", "EXXON", "CONOCOPHILLIPS", "EOG RESOURCES"]),
]


def http_json(url: str, sec: bool = True):
    headers = {"Accept": "application/json"}
    if sec:
        headers["User-Agent"] = os.environ.get(
            "SEC_USER_AGENT", "KHS 13F watch contact=github-actions"
        )
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


def http_text(url: str, sec: bool = True):
    headers = {"Accept": "application/xml,text/xml,text/plain,*/*"}
    if sec:
        headers["User-Agent"] = os.environ.get(
            "SEC_USER_AGENT", "KHS 13F watch contact=github-actions"
        )
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", errors="replace")


def recent_13f(cik: str):
    data = http_json(f"{SEC_DATA}/submissions/CIK{cik}.json")
    recent = data.get("filings", {}).get("recent", {})
    rows = []
    forms = recent.get("form", [])
    for i, form in enumerate(forms):
        if form not in {"13F-HR", "13F-HR/A"}:
            continue
        rows.append({
            "cik": cik,
            "name": data.get("name", cik),
            "form": form,
            "accession": recent["accessionNumber"][i],
            "filing_date": recent["filingDate"][i],
            "accepted_at": (recent.get("acceptanceDateTime") or [""] * len(forms))[i],
            "report_date": recent["reportDate"][i],
            "primary_document": recent["primaryDocument"][i],
        })
    rows.sort(key=lambda x: (x["report_date"], x["filing_date"], x["accession"]), reverse=True)
    return rows


def filing_dir(cik: str, accession: str):
    return f"{SEC_BASE}/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}"


def info_xml_url(cik: str, accession: str):
    base = filing_dir(cik, accession)
    idx = http_json(base + "/index.json")
    items = idx.get("directory", {}).get("item", [])
    xmls = []
    for item in items:
        name = item.get("name", "")
        low = name.lower()
        if low.endswith(".xml") and low not in {"primary_doc.xml", "primarydoc.xml"}:
            xmls.append(name)
    preferred = [n for n in xmls if any(k in n.lower() for k in ["info", "13f", "table", "form13f"])]
    candidates = preferred + [n for n in xmls if n not in preferred]
    for name in candidates:
        try:
            text = http_text(base + "/" + name)
            if "infoTable" in text or "infotable" in text.lower():
                return base + "/" + name, text
        except Exception:
            continue
    raise RuntimeError(f"13F 보유종목 정보표 XML을 찾지 못했습니다: {accession}")


def local_name(tag):
    return tag.split("}")[-1]


def child_text(node, path_names):
    cur = node
    for name in path_names:
        found = None
        for ch in cur:
            if local_name(ch.tag).lower() == name.lower():
                found = ch
                break
        if found is None:
            return ""
        cur = found
    return (cur.text or "").strip()


def num(s):
    try:
        return float(str(s).replace(",", ""))
    except Exception:
        return 0.0


def parse_holdings(cik: str, accession: str):
    url, text = info_xml_url(cik, accession)
    root = ET.fromstring(text)
    out = {}
    for node in root.iter():
        if local_name(node.tag).lower() != "infotable":
            continue
        issuer = child_text(node, ["nameOfIssuer"])
        title = child_text(node, ["titleOfClass"])
        cusip = child_text(node, ["cusip"])
        raw_value = child_text(node, ["value"])
        raw_shares = child_text(node, ["shrsOrPrnAmt", "sshPrnamt"])
        try:
            value = float(raw_value.replace(",", ""))
            shares = float(raw_shares.replace(",", ""))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"SEC 13F missing or invalid shares/value in {accession}") from exc
        import math
        if not math.isfinite(value) or not math.isfinite(shares) or value < 0 or shares <= 0:
            raise ValueError(f"SEC 13F non-finite or invalid shares/value in {accession}")
        if not cusip or not issuer:
            raise ValueError(f"SEC 13F missing CUSIP/issuer in {accession}")
        putcall = child_text(node, ["putCall"]).upper()
        if putcall not in ("", "PUT", "CALL"):
            raise ValueError(f"SEC 13F unexpected option classification {putcall!r}")
        key = "|".join([cusip, title, putcall])
        if key in out:
            # SEC explicitly permits separate rows by investment discretion.
            # Earlier code overwrote such rows, creating false reductions/exits.
            previous = out[key]
            if previous["issuer"].strip().upper() != issuer.strip().upper():
                raise ValueError("SEC 13F same CUSIP/title/option with conflicting issuers")
            previous["value"] += value
            previous["shares"] += shares
            previous["source_rows"] += 1
        else:
            out[key] = {
                "issuer": issuer,
                "title": title,
                "cusip": cusip,
                "value": value,
                "shares": shares,
                "putcall": putcall,
                "source_rows": 1,
            }
    if not out:
        raise RuntimeError(f"SEC 13F empty information table: {accession}; no false liquidation alert")
    return out, url


def sector_for(issuer: str):
    u = issuer.upper()
    for sector, needles in SECTOR_RULES:
        if any(n in u for n in needles):
            return sector
    return "기타"


def security_name_kr(x):
    issuer = x.get("issuer", "")
    title = x.get("title", "")
    u = issuer.upper()
    if "ALPHABET" in u:
        t = title.upper()
        if "CL A" in t or "CLASS A" in t:
            return "알파벳 A(GOOGL)"
        if "CL C" in t or "CLASS C" in t:
            return "알파벳 C(GOOG)"
        return "알파벳(GOOGL/GOOG)"
    for needle, display in SECURITY_DISPLAY_RULES:
        if needle in u:
            return display
    # 매핑되지 않은 종목은 SEC 원문을 버리지 않는다.
    return issuer


def option_name_kr(putcall):
    pc = (putcall or "").upper()
    if pc == "CALL":
        return " 콜옵션(CALL)"
    if pc == "PUT":
        return " 풋옵션(PUT)"
    return ""


def classify_changes(cur, prev):
    """Compare complete 13F tables by CUSIP+option before security-title wording.

    SEC security titles sometimes change (e.g. YPF SPON ADR CL D ->
    SPONSORED ADS), while CUSIP, issuer, and instrument are identical.
    Keying on CUSIP/title/putCall alone would fabricate an EXIT and a NEW.
    Only reconcile if CUSIP+option is unambiguous *in both quarters*.
    """
    from collections import Counter
    def identity(record):
        return (str(record.get("cusip") or "").strip().upper(),
                str(record.get("putcall") or "").strip().upper())
    current_count=Counter(identity(x) for x in cur.values())
    prior_count=Counter(identity(x) for x in prev.values())
    unique_previous={}
    for key,p in prev.items():
        k=identity(p)
        if k[0] and prior_count[k]==1:
            unique_previous[k]=(key,p)
    used_previous=set()
    changes=[]
    for k,c in sorted(cur.items()):
        p=prev.get(k)
        if p is not None:
            used_previous.add(k)
        else:
            ident=identity(c)
            match=unique_previous.get(ident)
            if (match and current_count[ident]==1
                    and str(match[1].get("issuer") or "").strip().upper()
                        == str(c.get("issuer") or "").strip().upper()):
                oldkey,p=match
                if oldkey not in used_previous:
                    used_previous.add(oldkey)
                    print(f"13F_SECURITY_TITLE_RECONCILED "
                          f"cusip={ident[0]} prior_title={p.get('title')} "
                          f"current_title={c.get('title')}")
                else:
                    p=None
        if p is None:
            action="신규 매수"
            delta_shares=float(c["shares"])
        else:
            delta_shares=float(c["shares"])-float(p["shares"])
            tol=max(1.0,abs(float(p["shares"]))*1e-6)
            if abs(delta_shares)<=tol:
                continue
            action="보유 확대" if delta_shares>0 else "보유 축소"
        x=dict(c)
        x.update({"action":action,"delta_shares":delta_shares,
                  "cur_value":float(c["value"]),
                  "prev_value":float(p["value"]) if p else 0.0,
                  "sector":sector_for(c["issuer"])})
        changes.append(x)
    for k,p in sorted(prev.items()):
        if k in used_previous:
            continue
        x=dict(p)
        x.update({"action":"전량 청산","delta_shares":-float(p["shares"]),
                  "cur_value":0.0,"prev_value":float(p["value"]),
                  "sector":sector_for(p["issuer"])})
        changes.append(x)
    return changes


def money(v):
    a = abs(v)
    if a >= 100_000_000:
        return f"약 {v/100_000_000:.2f}억달러"
    if a >= 1_000_000:
        return f"약 {v/1_000_000:.1f}백만달러"
    if a >= 1_000:
        return f"약 {v/1_000:.1f}천달러"
    return f"약 {v:,.0f}달러"


def shares_fmt(v):
    a = abs(v)
    if a >= 100_000_000:
        return f"{a/100_000_000:.2f}억주"
    if a >= 10_000:
        return f"{a/10_000:.2f}만주"
    return f"{a:,.0f}주"


def top_rows(changes, positive=True, limit=5):
    acts = {"신규 매수", "보유 확대"} if positive else {"전량 청산", "보유 축소"}
    rows = [x for x in changes if x["action"] in acts]
    rows.sort(key=lambda x: max(x["cur_value"], x["prev_value"]), reverse=True)
    return rows[:limit]


def sector_summary(changes):
    d = defaultdict(lambda: {"buy": 0, "sell": 0, "buy_value": 0.0, "sell_value": 0.0})
    for x in changes:
        sec = x["sector"]
        if x["action"] in {"신규 매수", "보유 확대"}:
            d[sec]["buy"] += 1
            d[sec]["buy_value"] += x["cur_value"]
        else:
            d[sec]["sell"] += 1
            d[sec]["sell_value"] += x["prev_value"]
    return sorted(d.items(), key=lambda kv: kv[1]["buy_value"] + kv[1]["sell_value"], reverse=True)


def line_for(x):
    opt = option_name_kr(x.get("putcall"))
    base_value = x["cur_value"] if x["action"] in {"신규 매수", "보유 확대"} else x["prev_value"]
    sign = "+" if x["action"] in {"신규 매수", "보유 확대"} else "-"
    return (
        f"• {x['action']} | {security_name_kr(x)}{opt}: "
        f"{sign}{shares_fmt(x['delta_shares'])} / 분기말 평가액 {money(base_value)}"
    )


def build_message(label, filing, previous, changes, info_url,
                  current_holdings=None, previous_holdings=None):
    sectors = sector_summary(changes)
    buys = top_rows(changes, True)
    sells = top_rows(changes, False)
    display_label = MANAGER_KR.get(label, label)
    lines = [
        f"📊 [13F 새 공시] {display_label}",
        f"기준일: {filing['report_date']} | 제출일: {filing['filing_date']}",
        f"공시 형식: {filing['form']} | 비교 기준: {previous['report_date'] if previous else '이전 분기 없음'}",
        "",
        "▶ 산업별 매수·매도 방향",
    ]
    for sec, s in sectors[:6]:
        if sec == "기타" and len(sectors) > 1:
            continue
        if s["buy"] > s["sell"]:
            direction = "매수·확대 우위"
        elif s["sell"] > s["buy"]:
            direction = "축소·청산 우위"
        else:
            direction = "매수·매도 혼조"
        lines.append(f"• {sec}: {direction} (신규·확대 {s['buy']}건 / 축소·청산 {s['sell']}건)")
    if buys:
        lines += ["", "▶ 주요 신규 매수·보유 확대"] + [line_for(x) for x in buys]
    if sells:
        lines += ["", "▶ 주요 보유 축소·전량 청산"] + [line_for(x) for x in sells]
    lines += [
        "",
        "※ 13F는 분기말 보유 현황 공시입니다. 분기말 평가액에는 주가 변동이 섞여 있어 실제 매수·매도 대금과 같지 않습니다.",
        "※ 풋옵션(PUT)·콜옵션(CALL)은 보통주와 분리해 표시하며, 옵션의 실제 위험노출은 행사가·만기 등 추가 정보가 필요합니다.",
        f"SEC 원문: {info_url}",
    ]
    return "\n".join(lines)


def telegram_api(token, method, params=None):
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = None
    if params is not None:
        data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=25) as r:
        payload = json.load(r)
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {payload}")
    return payload["result"]


def verify_bot(token):
    me = telegram_api(token, "getMe")
    username = me.get("username", "")
    if username.lower() != EXPECTED_BOT_USERNAME.lower():
        raise RuntimeError(
            f"Telegram bot mismatch: expected @{EXPECTED_BOT_USERNAME}, got @{username or 'unknown'}"
        )
    return username


def send_message(token, chat_id, text):
    chunks = []
    current = ""
    for line in text.splitlines(True):
        if len(current) + len(line) > 3800 and current:
            chunks.append(current.rstrip())
            current = line
        else:
            current += line
    if current.strip():
        chunks.append(current.rstrip())
    for chunk in chunks:
        telegram_api(
            token,
            "sendMessage",
            {"chat_id": chat_id, "text": chunk, "disable_web_page_preview": "true"},
        )


def load_state():
    if not STATE_PATH.exists():
        return {"version": 1, "managers": {}, "updated_at": None}
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(state, dict) or not isinstance(state.get("managers"), dict):
            raise ValueError("invalid 13F state")
        return state
    except (ValueError, OSError) as exc:
        raise RuntimeError("13F state unreadable; refuse reset or repeat delivery") from exc


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def amendment_metadata(filing):
    """Read the official cover page, not a news headline or the holdings table."""
    url=filing_dir(filing["cik"],filing["accession"])+"/primary_doc.xml"
    root=ET.fromstring(http_text(url))
    covers=[node for node in root.iter() if local_name(node.tag)=="coverPage"]
    if len(covers)!=1:
        raise RuntimeError("13F amendment cover page missing or ambiguous")
    cover=covers[0]
    kind=child_text(cover,["amendmentInfo","amendmentType"]).upper()
    if kind not in ("RESTATEMENT","NEW HOLDINGS","NEW HOLDINGS ENTRIES"):
        raise RuntimeError("13F amendment type unavailable; refuse misleading quarterly alert")
    return {"type":kind,"reason":child_text(cover,["additionalInformation"]),
            "url":url,"number":child_text(cover,["amendmentNo"])}


def filing_order(row):
    """Submission chronology, distinct from the quarter-end date."""
    return (str(row.get("filing_date") or ""), str(row.get("accepted_at") or ""),
            str(row.get("accession") or ""))


def after_legacy_cutoff(row, cutoff):
    if row["accession"] == cutoff.get("accession"):
        return False
    date, accepted, accession = filing_order(row)
    old_date, old_accepted, old_acc = filing_order(cutoff)
    if date != old_date:
        return date > old_date
    if accepted and old_accepted:
        return accepted > old_accepted or (accepted == old_accepted and accession > old_acc)
    # Without acceptance times only same accession series is safely ordered.
    return bool(old_acc and accession.rsplit("-", 1)[0] == old_acc.rsplit("-", 1)[0]
                and accession > old_acc)


def filing_event_key(label, row):
    return "|".join((label, row["cik"], row["accession"]))


def effective_holdings(rows, cik, period, before=None):
    """Reconstruct a complete quarter: last full filing + subsequent add-only amendments.

    A restatement replaces the earlier complete table. Add-only filings supplement it.
    No complete base means no inferred additions/exits.
    """
    ordered = sorted((r for r in rows if r["cik"] == cik and
                      r["report_date"] == period and
                      (before is None or filing_order(r) < filing_order(before))),
                     key=filing_order)
    base = None
    holdings = {}
    accessions = []
    for row in ordered:
        kind = "FULL" if row["form"] == "13F-HR" else amendment_metadata(row)["type"]
        if kind in ("FULL", "RESTATEMENT"):
            holdings, _ = parse_holdings(row["cik"], row["accession"])
            holdings = {k: dict(v) for k, v in holdings.items()}
            base = dict(row)
            accessions = [row["accession"]]
        elif base is not None:
            additions, _ = parse_holdings(row["cik"], row["accession"])
            for key, item in additions.items():
                if key not in holdings:
                    holdings[key] = dict(item)
                    continue
                old = holdings[key]
                if old["issuer"].strip().upper() != item["issuer"].strip().upper():
                    raise RuntimeError("13F supplemental security identity conflict")
                old["shares"] += item["shares"]
                old["value"] += item["value"]
                old["source_rows"] = old.get("source_rows", 1) + item.get("source_rows", 1)
            accessions.append(row["accession"])
    if base is not None:
        base["effective_accessions"] = accessions
    return base, holdings


def previous_quarter_holdings(rows, filing):
    periods = sorted({r["report_date"] for r in rows
                      if r["report_date"] < filing["report_date"]}, reverse=True)
    if not periods:
        return None, {}
    period = periods[0]
    candidates = [r for r in rows if r["report_date"] == period and r["form"] == "13F-HR"]
    if not candidates:
        candidates = [r for r in rows if r["report_date"] == period and r["form"] == "13F-HR/A"
                      and amendment_metadata(r)["type"] == "RESTATEMENT"]
    if not candidates:
        return None, {}
    same = [r for r in candidates if r["cik"] == filing["cik"]]
    ciks = {r["cik"] for r in same or candidates}
    # Preserve known CIK succession, never merge different legal filers.
    if len(ciks) != 1:
        return None, {}
    return effective_holdings(rows, next(iter(ciks)), period)


def amendment_comparison(filing, rows, seen, metadata):
    """Last complete earlier same-period report, never an add-only report."""
    if metadata["type"] != "RESTATEMENT":
        return None
    same = sorted((r for r in rows if r["cik"] == filing["cik"]
                   and r["report_date"] == filing["report_date"]
                   and filing_order(r) < filing_order(filing)), key=filing_order, reverse=True)
    for prior in same:
        if prior["form"] == "13F-HR" or amendment_metadata(prior)["type"] == "RESTATEMENT":
            return prior
    return None


def prepare_filing_message(label, filing, rows, recovery=False):
    latest = dict(filing)
    current, url = parse_holdings(latest["cik"], latest["accession"])
    previous, prior = None, {}
    if latest["form"] == "13F-HR/A":
        latest["amendment"] = amendment_metadata(latest)
        if latest["amendment"]["type"] == "RESTATEMENT":
            previous, prior = effective_holdings(
                rows, latest["cik"], latest["report_date"], before=latest)
    else:
        previous, prior = previous_quarter_holdings(rows, latest)
    changes = classify_changes(current, prior) if previous else []
    latest["recovery"] = recovery
    return build_message(label, latest, previous, changes, url,
                         current_holdings=current, previous_holdings=prior)


def _git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True)


def persist_delivery_state(state, description):
    """Persist reservation before send, and receipt immediately after success.

    Fail closed if an uncertain prior send exists. No force push or state reset.
    """
    save_state(state)
    if os.environ.get("GITHUB_ACTIONS", "").lower() != "true":
        return
    path = STATE_PATH.as_posix()
    if _git("fetch", "origin", "main").returncode:
        raise RuntimeError("13F state remote fetch failed")
    remote = _git("show", "origin/main:" + path)
    local = _git("show", "HEAD:" + path)
    if remote.returncode != local.returncode or remote.stdout != local.stdout:
        raise RuntimeError("13F state changed concurrently; refuse stale send/checkpoint")
    for args in (("config", "user.name", "github-actions[bot]"),
                 ("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"),
                 ("add", "--", path), ("commit", "-m", description)):
        if _git(*args).returncode:
            raise RuntimeError("13F delivery state commit failed")
    for attempt in range(3):
        if _git("fetch", "origin", "main").returncode:
            raise RuntimeError("13F delivery state remote fetch failed")
        if _git("rebase", "origin/main").returncode:
            _git("rebase", "--abort")
            raise RuntimeError("13F state rebase conflict; no force push")
        if _git("push", "origin", "HEAD:main").returncode == 0:
            return
        time.sleep(attempt + 1)
    raise RuntimeError("13F delivery state push unconfirmed; no automatic resend")


def checkpoint_for(row):
    return {key: row.get(key, "") for key in
            ("accession", "report_date", "filing_date", "cik", "accepted_at")}


def main():
    state = load_state()
    if state.get("pending_13f_delivery"):
        raise RuntimeError("13F_DELIVERY_UNCERTAIN: existing reservation requires reconciliation")
    token = os.environ.get("THIRTEENF_TELEGRAM_BOT_TOKEN") or os.environ.get("KHS_POLICY_TELEGRAM_BOT_TOKEN") or ""
    chat_id = os.environ.get("THIRTEENF_TELEGRAM_CHAT_ID") or os.environ.get("KHS_POLICY_TELEGRAM_CHAT_ID") or ""
    force_test = os.environ.get("THIRTEENF_FORCE_TEST", "false").lower() == "true"
    checkpoints = state.setdefault("managers", {})
    cutoffs = state.setdefault("13f_legacy_cutoffs", {})
    receipts = state.setdefault("13f_delivery_receipts", {})
    if not isinstance(cutoffs, dict) or not isinstance(receipts, dict):
        raise RuntimeError("13F delivery ledger invalid")
    grouped = {}
    incomplete = []
    for label, ciks in MANAGERS.items():
        rows = []
        errors = []
        for cik in ciks:
            try:
                rows.extend(recent_13f(cik))
            except Exception as exc:
                errors.append(cik)
                print(f"13F_SOURCE_ERROR {label} {cik}: {type(exc).__name__}", file=sys.stderr)
        if errors or not rows:
            incomplete.append(label)
            continue
        grouped[label] = sorted(rows, key=filing_order)

    if not grouped:
        raise RuntimeError("13F source coverage unavailable; not a no-news result")
    confirmed = 0
    target = None
    for label, rows in grouped.items():
        seen = checkpoints.get(label)
        latest = max(rows, key=lambda r: (r["report_date"], filing_order(r)))
        recovery = not seen and label in RECOVER_MISSING_MANAGERS
        if not seen and not recovery:
            checkpoints[label] = checkpoint_for(latest)
            cutoffs[label] = checkpoint_for(rows[-1])
            print(f"BASELINE {label}: {latest['accession']} {latest['report_date']}")
            continue
        if recovery:
            # Only recover the latest complete quarter, not a flood of old amendments.
            full = [r for r in rows if r["report_date"] == latest["report_date"]
                    and r["form"] == "13F-HR"]
            if not full:
                incomplete.append(label)
                continue
            candidates = [max(full, key=filing_order)]
        else:
            if label not in cutoffs:
                legacy = next((r for r in rows if r["accession"] == seen.get("accession")
                               and r["cik"] == seen.get("cik")), None)
                cutoffs[label] = checkpoint_for(legacy or seen)
            candidates = [r for r in rows if after_legacy_cutoff(r, cutoffs[label])
                          and filing_event_key(label, r) not in receipts]
        if not candidates:
            print(f"UNCHANGED {label}: {seen.get('accession') if seen else 'baseline'}")
            continue
        for filing in candidates:
            key = filing_event_key(label, filing)
            if key in receipts:
                continue
            try:
                message = prepare_filing_message(label, filing, rows, recovery=recovery)
            except Exception as exc:
                incomplete.append(label)
                print(f"13F_PARSE_ERROR {label} {filing['accession']}: {type(exc).__name__}", file=sys.stderr)
                break
            if not token or not chat_id:
                raise RuntimeError("13F Telegram configuration unavailable")
            if target is None:
                verify_bot(token)
                target = telegram_api(token, "getChat", {"chat_id": chat_id}).get("id")
                if type(target) is not int or not target:
                    raise RuntimeError("13F Telegram recipient not verified")
                if str(chat_id).strip().lstrip("-").isdigit() and int(chat_id) != target:
                    raise RuntimeError("13F Telegram recipient mismatch")
            state["pending_13f_delivery"] = {"key": key, "reserved_at": dt.datetime.now(dt.timezone.utc).isoformat()}
            persist_delivery_state(state, "Reserve verified 13F filing delivery")
            receipt = send_message(token, str(target), message)
            mid = (receipt or {}).get("message_id")
            actual = ((receipt or {}).get("chat") or {}).get("id")
            if type(mid) is not int or mid <= 0 or actual != target:
                raise RuntimeError("13F delivery uncertain; reservation preserved")
            receipts[key] = {"message_id": mid,
                             "recipient_fingerprint": hashlib.sha256(str(actual).encode()).hexdigest()[:16],
                             "confirmed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                             "report_date": filing["report_date"], "filing_date": filing["filing_date"],
                             "recovery": recovery}
            if recovery:
                cutoffs[label] = checkpoint_for(filing)
            prior_checkpoint = checkpoints.get(label)
            if (not prior_checkpoint or
                    (filing["report_date"], filing_order(filing)) >
                    (prior_checkpoint["report_date"], filing_order(prior_checkpoint))):
                checkpoints[label] = checkpoint_for(filing)
            state.pop("pending_13f_delivery", None)
            persist_delivery_state(state, "Confirm verified 13F filing delivery")
            confirmed += 1
            print(f"13F_FILING_RECEIPT_SAVED {label} {filing['accession']} recipient_verified=true")
    if force_test:
        if not token or not chat_id:
            raise RuntimeError("13F Telegram configuration unavailable")
        verify_bot(token)
        send_message(token, chat_id, "13F 감시 한국어 알림 테스트")
    print(f"13F_SOURCE_COVERAGE {len(grouped)}/{len(MANAGERS)} confirmed={confirmed}")
    if incomplete:
        print("13F_PARTIAL_COVERAGE no-all-clear: " + ", ".join(sorted(set(incomplete))), file=sys.stderr)
    elif not confirmed and not force_test:
        print("새 13F 공시 없음: Telegram 메시지를 보내지 않습니다.")
    save_state(state)


if __name__ == "__main__":
    main()
