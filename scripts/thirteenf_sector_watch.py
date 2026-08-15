#!/usr/bin/env python3
import datetime as dt
import json
import os
import pathlib
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict

SEC_BASE = "https://www.sec.gov"
SEC_DATA = "https://data.sec.gov"
STATE_PATH = pathlib.Path("data/thirteenf_sector_watch_state.json")
EXPECTED_BOT_USERNAME = "khs887988798879_bot"

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
        value = num(child_text(node, ["value"]))
        shares = num(child_text(node, ["shrsOrPrnAmt", "sshPrnamt"]))
        putcall = child_text(node, ["putCall"]).upper()
        key = "|".join([cusip, title, putcall])
        out[key] = {
            "issuer": issuer,
            "title": title,
            "cusip": cusip,
            "value": value,
            "shares": shares,
            "putcall": putcall,
        }
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
    changes = []
    keys = set(cur) | set(prev)
    for k in keys:
        c = cur.get(k)
        p = prev.get(k)
        if c and not p:
            action = "신규 매수"
            delta_shares = c["shares"]
        elif p and not c:
            action = "전량 청산"
            delta_shares = -p["shares"]
        else:
            delta_shares = c["shares"] - p["shares"]
            if p["shares"] == 0 and c["shares"] == 0:
                continue
            tol = max(1.0, abs(p["shares"]) * 1e-6)
            if abs(delta_shares) <= tol:
                continue
            action = "보유 확대" if delta_shares > 0 else "보유 축소"
        x = dict(c or p)
        x["action"] = action
        x["delta_shares"] = delta_shares
        x["cur_value"] = c["value"] if c else 0.0
        x["prev_value"] = p["value"] if p else 0.0
        x["sector"] = sector_for(x["issuer"])
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


def build_message(label, filing, previous, changes, info_url):
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
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "managers": {}, "updated_at": None}


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    state = load_state()
    token = os.environ.get("THIRTEENF_TELEGRAM_BOT_TOKEN") or os.environ.get("KHS_POLICY_TELEGRAM_BOT_TOKEN") or ""
    chat_id = os.environ.get("THIRTEENF_TELEGRAM_CHAT_ID") or os.environ.get("KHS_POLICY_TELEGRAM_CHAT_ID") or ""
    force_test = os.environ.get("THIRTEENF_FORCE_TEST", "false").lower() == "true"

    grouped_latest = {}
    for label, ciks in MANAGERS.items():
        rows = []
        for cik in ciks:
            try:
                rows.extend(recent_13f(cik))
            except Exception as e:
                print(f"WARN submissions {label} {cik}: {e}", file=sys.stderr)
        rows.sort(key=lambda x: (x["report_date"], x["filing_date"], x["accession"]), reverse=True)
        if rows:
            grouped_latest[label] = rows

    alerts = []
    pending_updates = {}
    for label, rows in grouped_latest.items():
        latest = rows[0]
        seen = state.get("managers", {}).get(label, {}).get("accession")
        if not seen:
            pending_updates[label] = latest
            print(f"BASELINE {label}: {latest['accession']} {latest['report_date']}")
            continue
        if latest["accession"] == seen:
            print(f"UNCHANGED {label}: {seen}")
            continue

        previous = None
        for r in rows[1:]:
            if r["report_date"] < latest["report_date"] and r["form"] == "13F-HR":
                previous = r
                break
        if previous is None and len(rows) > 1:
            previous = rows[1]
        try:
            cur, info_url = parse_holdings(latest["cik"], latest["accession"])
            prev = {}
            if previous:
                prev, _ = parse_holdings(previous["cik"], previous["accession"])
            changes = classify_changes(cur, prev)
            alerts.append(build_message(label, latest, previous, changes, info_url))
            pending_updates[label] = latest
        except Exception as e:
            print(f"ERROR parse {label}: {e}", file=sys.stderr)
            raise

    if force_test:
        alerts.insert(
            0,
            "✅ [13F 감시 한국어 알림 테스트]\n"
            "앞으로 운용사명·종목명·산업·매수/매도 표현은 한국어 중심으로 표시합니다.\n"
            "티커·13F-HR·풋옵션(PUT)·콜옵션(CALL)처럼 식별에 필요한 원문만 괄호로 유지합니다.\n"
            "발신 봇: @" + EXPECTED_BOT_USERNAME,
        )

    if alerts:
        if not token or not chat_id:
            raise RuntimeError("Telegram 비밀값이 없습니다: THIRTEENF_* 또는 KHS_POLICY_TELEGRAM_* 설정을 확인하세요")
        username = verify_bot(token)
        print(f"Telegram bot verified: @{username}")
        for msg in alerts:
            send_message(token, chat_id, msg)
    else:
        print("새 13F 공시 없음: Telegram 메시지를 보내지 않습니다.")

    for label, latest in pending_updates.items():
        state.setdefault("managers", {})[label] = {
            "accession": latest["accession"],
            "report_date": latest["report_date"],
            "filing_date": latest["filing_date"],
            "cik": latest["cik"],
        }
    save_state(state)


if __name__ == "__main__":
    main()
