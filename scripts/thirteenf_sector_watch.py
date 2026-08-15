#!/usr/bin/env python3
import datetime as dt
import json
import os
import pathlib
import re
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
    raise RuntimeError(f"information table XML not found: {accession}")


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


def classify_changes(cur, prev):
    changes = []
    keys = set(cur) | set(prev)
    for k in keys:
        c = cur.get(k)
        p = prev.get(k)
        if c and not p:
            action = "신규"
            delta_shares = c["shares"]
        elif p and not c:
            action = "청산"
            delta_shares = -p["shares"]
        else:
            delta_shares = c["shares"] - p["shares"]
            if p["shares"] == 0 and c["shares"] == 0:
                continue
            tol = max(1.0, abs(p["shares"]) * 1e-6)
            if abs(delta_shares) <= tol:
                continue
            action = "확대" if delta_shares > 0 else "축소"
        x = dict(c or p)
        x["action"] = action
        x["delta_shares"] = delta_shares
        x["cur_value"] = c["value"] if c else 0.0
        x["prev_value"] = p["value"] if p else 0.0
        x["sector"] = sector_for(x["issuer"])
        changes.append(x)
    return changes


def money(v):
    # Modern 13F XML value is reported in dollars. Keep compact and avoid treating it as trade cash flow.
    if abs(v) >= 1_000_000_000:
        return f"${v/1_000_000_000:.2f}bn"
    if abs(v) >= 1_000_000:
        return f"${v/1_000_000:.1f}m"
    if abs(v) >= 1_000:
        return f"${v/1_000:.1f}k"
    return f"${v:,.0f}"


def shares_fmt(v):
    a = abs(v)
    if a >= 1_000_000:
        return f"{a/1_000_000:.2f}m주"
    if a >= 1_000:
        return f"{a/1_000:.1f}k주"
    return f"{a:,.0f}주"


def top_rows(changes, positive=True, limit=5):
    acts = {"신규", "확대"} if positive else {"청산", "축소"}
    rows = [x for x in changes if x["action"] in acts]
    rows.sort(key=lambda x: max(x["cur_value"], x["prev_value"]), reverse=True)
    return rows[:limit]


def sector_summary(changes):
    d = defaultdict(lambda: {"buy": 0, "sell": 0, "buy_value": 0.0, "sell_value": 0.0})
    for x in changes:
        sec = x["sector"]
        if x["action"] in {"신규", "확대"}:
            d[sec]["buy"] += 1
            d[sec]["buy_value"] += x["cur_value"]
        else:
            d[sec]["sell"] += 1
            d[sec]["sell_value"] += x["prev_value"]
    return sorted(d.items(), key=lambda kv: kv[1]["buy_value"] + kv[1]["sell_value"], reverse=True)


def line_for(x):
    opt = f" {x['putcall']}" if x["putcall"] else ""
    base_value = x["cur_value"] if x["action"] in {"신규", "확대"} else x["prev_value"]
    arrow = "+" if x["action"] in {"신규", "확대"} else "-"
    return f"• {x['action']} {x['issuer']}{opt}: {arrow}{shares_fmt(x['delta_shares'])} / 분기말 평가액 {money(base_value)}"


def build_message(label, filing, previous, changes, info_url):
    sectors = sector_summary(changes)
    buys = top_rows(changes, True)
    sells = top_rows(changes, False)
    lines = [
        f"📊 [13F 새 공시] {label}",
        f"기준분기: {filing['report_date']} | 제출일: {filing['filing_date']}",
        f"형식: {filing['form']} | 이전 비교: {previous['report_date'] if previous else '없음'}",
        "",
        "▶ 섹터 방향(보유주식 수 변화 기준)",
    ]
    for sec, s in sectors[:6]:
        if sec == "기타" and len(sectors) > 1:
            continue
        if s["buy"] > s["sell"]:
            direction = "매수 우위"
        elif s["sell"] > s["buy"]:
            direction = "매도 우위"
        else:
            direction = "혼조"
        lines.append(f"• {sec}: {direction} (매수·확대 {s['buy']} / 축소·청산 {s['sell']})")
    if buys:
        lines += ["", "▶ 주요 신규·확대"] + [line_for(x) for x in buys]
    if sells:
        lines += ["", "▶ 주요 축소·청산"] + [line_for(x) for x in sells]
    lines += [
        "",
        "※ 13F 분기말 평가액은 실제 매수·매도 금액이 아니며 가격 변동이 섞입니다.",
        "※ PUT/CALL은 보통주와 분리해서 표시합니다.",
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
    # Telegram sendMessage text limit is 4096 chars; chunk conservatively.
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
        telegram_api(token, "sendMessage", {"chat_id": chat_id, "text": chunk, "disable_web_page_preview": "true"})


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
            # First run creates a baseline and does not spam historical filings.
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
        alerts.insert(0, "✅ [13F 감시 테스트]\nSEC 13F 섹터 로테이션 감시가 정상 실행됐습니다.\n발신 봇 확인 대상: @" + EXPECTED_BOT_USERNAME)

    if alerts:
        if not token or not chat_id:
            raise RuntimeError("Telegram secrets missing: set THIRTEENF_* or KHS_POLICY_TELEGRAM_* secrets")
        username = verify_bot(token)
        print(f"Telegram bot verified: @{username}")
        for msg in alerts:
            send_message(token, chat_id, msg)
    else:
        print("No new 13F filings; no Telegram message.")

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
