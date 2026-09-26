#!/usr/bin/env python3
import os, re, json, hashlib, html
from io import StringIO
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import requests
import pandas as pd
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from playwright.sync_api import sync_playwright

ROOT = Path.cwd()
OUT = ROOT / "out"
DATA = ROOT / "data"
OUT.mkdir(exist_ok=True)
DATA.mkdir(exist_ok=True)
ALERT = OUT / "us_fund_flow_alert.html"
STATUS = OUT / "us_fund_flow_status.md"
PENDING = OUT / "us_fund_flow_pending_state.json"
STATE = DATA / "us_fund_flow_state.json"

for p in (ALERT, STATUS, PENDING):
    try:
        p.unlink()
    except FileNotFoundError:
        pass

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/152 Safari/537.36"
S = requests.Session()
S.headers.update({
    "User-Agent": UA,
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})

ICI_COMBINED = "https://www.ici.org/research/stats/combined_flows"
ICI_MMF = "https://www.ici.org/research/stats/mmf"
FINRA_MARGIN = "https://www.finra.org/rules-guidance/key-topics/margin-accounts/margin-statistics"
BING_Bofa = 'BofA EPFR US stocks money market Reuters'
BING_LIPPER = 'LSEG Lipper U.S. equity funds money market Reuters'


def get(url, timeout=35):
    r = S.get(url, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return r


def browser_html(url):
    exe = next(
        (p for p in [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
        ] if os.path.exists(p)),
        None,
    )
    if not exe:
        raise RuntimeError("system Chrome/Chromium not found")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=exe,
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
        )
        page = browser.new_page(user_agent=UA, locale="en-US")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(1200)
        out = page.content()
        browser.close()
        return out


def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"seen": {}, "values": {}}


def parse_num(x):
    if x is None:
        return None
    if isinstance(x, (int, float)) and pd.notna(x):
        return float(x)
    s = str(x).replace(",", "").replace("$", "").replace("%", "").strip()
    m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


def clean_text(x):
    return re.sub(r"\s+", " ", BeautifulSoup(str(x), "html.parser").get_text(" ", strip=True)).strip()


def semantic_core(x):
    """Only economically meaningful fields participate in duplicate detection."""
    return {
        "source": x.get("source"),
        "kind": x.get("kind"),
        "period": x.get("period"),
        "metrics": x.get("metrics") or {},
    }


def semantic_fingerprint(x):
    return hashlib.sha256(
        json.dumps(semantic_core(x), sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def fetch_fx():
    key = (os.getenv("ECOS_API_KEY") or "").strip()
    if not key:
        return None
    today = datetime.now(timezone(timedelta(hours=9))).date()
    start = (today - timedelta(days=12)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    url = f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/100/731Y001/D/{start}/{end}/0000001"
    try:
        j = get(url).json()
        rows = (j.get("StatisticSearch") or {}).get("row") or []
        vals = []
        for row in rows:
            v = parse_num(row.get("DATA_VALUE"))
            d = str(row.get("TIME") or "")
            if v is not None and d:
                vals.append((d, v))
        vals.sort()
        if vals:
            return {"date": vals[-1][0], "usdkrw": vals[-1][1]}
    except Exception:
        return None
    return None


def krw_trillion(bn_usd, fx):
    if bn_usd is None or not fx:
        return None
    return bn_usd * fx["usdkrw"] / 1000.0


def fmt_krw_trillion(v, signed=False):
    if v is None:
        return "원화 환산 확인 불가"
    if signed:
        return f"약 {v:+,.2f}조원"
    return f"약 {v:,.2f}조원"


def fmt_usd_bn_kr(x, fx):
    if x is None:
        return "확인 불가"
    sign = "+" if x > 0 else ""
    base = f"{sign}{x:,.2f}B달러"
    kr = krw_trillion(x, fx) if fx else None
    return f"{base}({fmt_krw_trillion(kr, signed=True)})"


def fmt_usd_trillion_kr(x, fx):
    if x is None:
        return "확인 불가"
    base = f"{x:,.3f}조달러"
    kr = x * fx["usdkrw"] if fx else None
    return f"{base}({fmt_krw_trillion(kr, signed=False)})"


def first_date(text):
    m = re.search(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+20\d{2}",
        text,
    )
    return m.group(0) if m else None


def normalize_columns(t):
    out = t.copy()
    cols = []
    for c in out.columns:
        if isinstance(c, tuple):
            vals = [str(v).strip() for v in c if str(v).strip().lower() not in ("nan", "")]
            cols.append(" | ".join(vals))
        else:
            cols.append(str(c).strip())
    out.columns = cols
    return out


def parse_ici_combined():
    page_html = browser_html(ICI_COMBINED)
    text = clean_text(page_html)

    def signed_amount(pattern):
        m = re.search(pattern, text, re.I)
        if not m:
            return None
        direction = m.group(1).lower()
        value = float(m.group(2).replace(",", ""))
        return -value if "outflow" in direction else value

    total = signed_amount(
        r"Total estimated (inflows|outflows).*?(?:were|was) \$([\\d,.]+) billion"
    )
    domestic = signed_amount(
        r"Domestic equity funds had estimated (inflows|outflows) of \$([\\d,.]+) billion"
    )
    world = signed_amount(
        r"world equity funds had estimated (inflows|outflows) of \$([\\d,.]+) billion"
    )
    bond = signed_amount(
        r"Bond funds.*?had estimated (inflows|outflows) of \$([\\d,.]+) billion"
    )
    hybrid = signed_amount(
        r"Hybrid funds.*?had estimated (inflows|outflows) of \$([\\d,.]+) billion"
    )

    pm = re.search(
        r"week ended(?: Wednesday,?)?\\s+([A-Za-z]+\\s+\\d{1,2},\\s+20\\d{2})",
        text,
        re.I,
    )
    period = pm.group(1) if pm else "latest"

    if domestic is None and total is None:
        raise RuntimeError("ICI combined release prose values not found")

    current = {
        "equity": None,
        "domestic": domestic,
        "world": world,
        "bond": bond,
        "hybrid": hybrid,
        "total": total,
    }

    pub_m = re.search(
        r"((?:January|February|March|April|May|June|July|August|September|October|November|December)\\s+\\d{1,2},\\s+20\\d{2})\\s*\\|\\s*Print",
        text,
        re.I,
    )
    published = pub_m.group(1) if pub_m else first_date(text)

    payload = {
        "source": "ICI",
        "kind": "combined",
        "period": period,
        "published": published,
        "url": ICI_COMBINED,
        "metrics": current,
        "domestic_4w": None,
    }
    payload["fingerprint"] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return payload


def parse_ici_mmf():
    page_html = browser_html(ICI_MMF)
    text = clean_text(page_html)

    # Prefer the release prose because it states both level and weekly change.
    patterns = [
        re.compile(
            r"Total money market fund assets.*?(increased|decreased) by \$([\d,.]+) billion to \$([\d,.]+) trillion.*?week ended(?: Wednesday,?)?\s+([A-Za-z]+\s+\d{1,2})",
            re.I,
        ),
        re.compile(
            r"money market fund assets.*?(increased|decreased).*?\$([\d,.]+) billion.*?\$([\d,.]+) trillion.*?([A-Za-z]+\s+\d{1,2})",
            re.I,
        ),
    ]
    m = next((p.search(text) for p in patterns if p.search(text)), None)
    if not m:
        raise RuntimeError("ICI MMF release values not found")

    direction = 1 if m.group(1).lower() == "increased" else -1
    change_bn = direction * float(m.group(2).replace(",", ""))
    assets_trillion = float(m.group(3).replace(",", ""))
    period = m.group(4)
    pub_m = re.search(
        r"((?:January|February|March|April|May|June|July|August|September|October|November|December)\\s+\\d{1,2},\\s+20\\d{2})\\s*\\|\\s*Print",
        text,
        re.I,
    )
    published = pub_m.group(1) if pub_m else first_date(text)

    payload = {
        "source": "ICI",
        "kind": "mmf",
        "period": period,
        "published": published,
        "url": ICI_MMF,
        "metrics": {"assets_trillion": assets_trillion, "weekly_change_bn": change_bn},
    }
    payload["fingerprint"] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return payload


def parse_finra():
    r = get(FINRA_MARGIN)
    tables = pd.read_html(StringIO(r.text))
    target = None
    for raw in tables:
        t = normalize_columns(raw)
        flat = " ".join(t.columns) + " " + " ".join(map(str, t.astype(str).values.flatten()[:40]))
        if re.search(r"Debit Balances", flat, re.I) and re.search(r"Free Credit", flat, re.I):
            target = t
            break
    if target is None:
        raise RuntimeError("FINRA margin table not found")

    # Locate date/month column and three numeric columns by header labels.
    month_col = target.columns[0]
    debit_col = next((c for c in target.columns if re.search(r"Debit Balances", c, re.I)), target.columns[1])
    free_cols = [c for c in target.columns if re.search(r"Free Credit", c, re.I)]
    if len(free_cols) < 2:
        # Some FINRA pages have headers collapsed; fall back by column position only if there are 4+ cols.
        if len(target.columns) < 4:
            raise RuntimeError(f"FINRA margin columns unexpected: {list(target.columns)}")
        free_cols = [target.columns[2], target.columns[3]]

    rows = []
    for _, row in target.iterrows():
        period = str(row[month_col]).strip()
        if not re.search(r"\d{2}|20\d{2}|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec", period, re.I):
            continue
        debit = parse_num(row[debit_col])
        cash = parse_num(row[free_cols[0]])
        margin_cash = parse_num(row[free_cols[1]])
        if debit is not None:
            rows.append((period, debit, cash, margin_cash))
    if len(rows) < 2:
        raise RuntimeError("FINRA margin data rows not found")

    def month_key(period):
        p = period.strip()
        for fmt in ("%b-%y", "%b %Y", "%B %Y", "%m/%Y", "%Y-%m"):
            try:
                return datetime.strptime(p, fmt)
            except Exception:
                pass
        # Fallback to order on page; mark as minimal.
        return datetime.min

    if any(month_key(r[0]) != datetime.min for r in rows):
        rows.sort(key=lambda r: month_key(r[0]), reverse=True)
    latest, prev = rows[0], rows[1]

    # FINRA values are $ millions.
    metrics = {
        "margin_debt_bn": latest[1] / 1000.0,
        "cash_free_bn": latest[2] / 1000.0 if latest[2] is not None else None,
        "margin_free_bn": latest[3] / 1000.0 if latest[3] is not None else None,
        "margin_debt_mom_bn": (latest[1] - prev[1]) / 1000.0,
    }
    payload = {
        "source": "FINRA",
        "kind": "margin",
        "period": latest[0],
        "published": None,
        "url": FINRA_MARGIN,
        "metrics": metrics,
    }
    payload["fingerprint"] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return payload


def rss_items(url):
    try:
        root = ET.fromstring(get(url).content)
    except Exception:
        return []
    out = []
    for item in root.findall(".//item")[:40]:
        out.append({
            "title": (item.findtext("title") or "").strip(),
            "link": (item.findtext("link") or "").strip(),
            "pub": (item.findtext("pubDate") or "").strip(),
            "desc": clean_text(item.findtext("description") or ""),
        })
    return out


def news_items(query):
    bing = "https://www.bing.com/news/search?q=" + quote(query) + "&format=rss"
    google = "https://news.google.com/rss/search?q=" + quote(query) + "&hl=en-US&gl=US&ceid=US:en"
    seen = set()
    out = []
    for it in rss_items(bing) + rss_items(google):
        k = it["title"] + "|" + it["link"]
        if k not in seen:
            seen.add(k)
            out.append(it)
    return out


def extract_article_body(url):
    try:
        try:
            r = get(url, timeout=25)
            raw_html = r.text
            final_url = r.url
        except Exception:
            raw_html = browser_html(url)
            final_url = url
        soup = BeautifulSoup(raw_html, "html.parser")
        bodies = []
        for s in soup.find_all("script", attrs={"type": "application/ld+json"}):
            try:
                j = json.loads(s.string or "")
                stack = j if isinstance(j, list) else [j]
                for o in stack:
                    if isinstance(o, dict) and o.get("articleBody"):
                        bodies.append(str(o["articleBody"]))
                    if isinstance(o, dict) and isinstance(o.get("@graph"), list):
                        for q in o["@graph"]:
                            if isinstance(q, dict) and q.get("articleBody"):
                                bodies.append(str(q["articleBody"]))
            except Exception:
                pass
        body = max(bodies, key=len) if bodies else clean_text(raw_html)
        return final_url, body
    except Exception:
        return url, ""


def signed_flow_sentence(text, concept_regex):
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for sent in sentences:
        if not re.search(concept_regex, sent, re.I):
            continue
        amounts = re.findall(r"\$([\d,.]+)\s*billion", sent, re.I)
        if not amounts:
            continue
        # Only accept when direction word is in same sentence; prevents accidental amount assignment.
        low = sent.lower()
        if re.search(r"outflow|outflows|withdrawn|withdrew|pulled|redemption|redemptions", low):
            sign = -1
        elif re.search(r"inflow|inflows|received|attracted|bought|poured|added", low):
            sign = 1
        else:
            continue
        return sign * float(amounts[0].replace(",", "")), sent[:700]
    return None, None


def parse_reuters(kind):
    query = BING_Bofa if kind == "bofa" else BING_LIPPER
    seeds = {
        "bofa": [{
            "title": "Investors buy US stocks at fastest pace in three months, BofA says - Reuters",
            "link": "https://www.reuters.com/world/china/investors-buy-us-stocks-fastest-pace-three-months-bofa-says-2026-09-18/",
            "pub": "Fri, 18 Sep 2026 00:00:00 GMT",
            "desc": "BofA EPFR fund flows Reuters",
        }],
        "lipper": [{
            "title": "Global equity fund outflows hit nine-month high on inflation fears - Reuters",
            "link": "https://www.reuters.com/business/us-equity-funds-post-fourth-weekly-outflow-inflation-worries-rate-concerns-2026-09-18/",
            "pub": "Fri, 18 Sep 2026 00:00:00 GMT",
            "desc": "LSEG Lipper global equity fund flows Reuters",
        }],
    }
    items = seeds.get(kind, []) + news_items(query)
    for it in items:
        blob = (it["title"] + " " + it["desc"])
        if "Reuters" not in blob and "reuters" not in blob.lower():
            continue
        if kind == "bofa" and not re.search(r"BofA|Bank of America|EPFR", blob, re.I):
            continue
        if kind == "lipper" and not re.search(r"LSEG|Lipper|global equity fund", blob, re.I):
            continue

        final, body = extract_article_body(it["link"])
        combined = blob + " " + body
        if kind == "bofa" and not re.search(r"BofA|Bank of America|EPFR", combined, re.I):
            continue
        if kind == "lipper" and not re.search(r"LSEG|Lipper", combined, re.I):
            continue

        us, us_sent = signed_flow_sentence(combined, r"(U\.?S\.?|United States).*?(equity|stock)|(?:equity|stock).*?(U\.?S\.?|United States)")
        glob, glob_sent = signed_flow_sentence(combined, r"global.*?(equity|stock)|(?:equity|stock).*?global")
        mmf, mmf_sent = signed_flow_sentence(combined, r"money[- ]market|money market")

        if us is None and glob is None and mmf is None:
            continue

        payload = {
            "source": "BofA/EPFR via Reuters" if kind == "bofa" else "LSEG Lipper via Reuters",
            "kind": kind,
            "period": it["pub"],
            "published": it["pub"],
            "url": final or it["link"],
            "title": it["title"],
            "metrics": {"us_equity_bn": us, "global_equity_bn": glob, "mmf_bn": mmf},
            "evidence": {"us": us_sent, "global": glob_sent, "mmf": mmf_sent},
        }
        payload["fingerprint"] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        return payload
    # Include a compact diagnostic in status logs only when no matching Reuters item can be parsed.
    sample = [it.get("title","") for it in news_items(query)[:5]]
    if sample:
        raise RuntimeError("Reuters discovery sample: " + " || ".join(sample))
    return None


def period_date(x):
    if not x:
        return None
    p = str(x.get("period") or "").strip()
    pub = str(x.get("published") or "").strip()
    year = None
    ym = re.search(r"(20\\d{2})", p) or re.search(r"(20\\d{2})", pub)
    if ym:
        year = int(ym.group(1))
    else:
        year = datetime.now(timezone(timedelta(hours=9))).year

    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(p, fmt).date()
        except Exception:
            pass
    for fmt in ("%B %d", "%b %d"):
        try:
            d = datetime.strptime(p, fmt)
            return d.replace(year=year).date()
        except Exception:
            pass
    return None


def same_reference_week(a, b):
    da, db = period_date(a), period_date(b)
    return bool(da and db and da == db)


def flow_direction(us, mmf):
    if us is None or mmf is None:
        return "주식과 MMF를 같은 출처에서 동시에 확인하지 못해 자금 회전 방향 판정 보류"
    if us > 0 and mmf < 0:
        return "미국 주식 유입 + MMF 유출 → 같은 출처 안에서는 현금성 주차자금에서 위험자산으로 기울 가능성이 강화"
    if us < 0 and mmf > 0:
        return "미국 주식 유출 + MMF 유입 → 같은 출처 안에서는 위험자산 축소·현금성 주차 강화"
    if us > 0 and mmf > 0:
        return "미국 주식 + MMF 동반 유입 → 유동성 총량 확대 가능성, 단순한 MMF→주식 이동으로는 해석하지 않음"
    if us < 0 and mmf < 0:
        return "미국 주식 + MMF 동반 유출 → 채권·해외자산·결제 등 다른 목적지 확인 필요"
    return "방향 혼재"


def source_block(x, fx):
    m = x["metrics"]
    lines = []
    if x["kind"] == "combined":
        lines.append(f"• 미국 국내주식형(뮤추얼펀드+ETF) {fmt_usd_bn_kr(m.get('domestic'), fx)}")
        lines.append(f"• 세계주식형 {fmt_usd_bn_kr(m.get('world'), fx)} / 채권형 {fmt_usd_bn_kr(m.get('bond'), fx)}")
        if x.get("domestic_4w") is not None:
            lines.append(f"• 미국 국내주식형 최근 4주 합계 {fmt_usd_bn_kr(x['domestic_4w'], fx)}")
    elif x["kind"] == "mmf":
        ch = m["weekly_change_bn"]
        lines.append(
            f"• MMF(단기 현금 주차성 펀드) 총자산 {fmt_usd_trillion_kr(m['assets_trillion'], fx)} "
            f"/ 주간 {fmt_usd_bn_kr(ch, fx)}"
        )
    elif x["kind"] == "margin":
        lines.append(
            f"• 마진부채(주식담보 신용거래 차입) {fmt_usd_bn_kr(m['margin_debt_bn'], fx)} "
            f"/ 전월 {fmt_usd_bn_kr(m['margin_debt_mom_bn'], fx)}"
        )
        if m.get("cash_free_bn") is not None and m.get("margin_free_bn") is not None:
            lines.append(
                f"• 현금계좌 가용현금 {fmt_usd_bn_kr(m['cash_free_bn'], fx)} "
                f"/ 마진계좌 가용현금 {fmt_usd_bn_kr(m['margin_free_bn'], fx)}"
            )
    else:
        lines.append(f"• 미국 주식형 {fmt_usd_bn_kr(m.get('us_equity_bn'), fx)}")
        if m.get("global_equity_bn") is not None:
            lines.append(f"• 글로벌 주식형 {fmt_usd_bn_kr(m.get('global_equity_bn'), fx)}")
        if m.get("mmf_bn") is not None:
            lines.append(f"• MMF {fmt_usd_bn_kr(m.get('mmf_bn'), fx)}")
        lines.append("• 같은 출처 판정: " + flow_direction(m.get("us_equity_bn"), m.get("mmf_bn")))
    return "\n".join(lines)


state = load_state()
fx = fetch_fx()
results = []
errors = []

for name, fn in [
    ("ICI 장기펀드+ETF", parse_ici_combined),
    ("ICI MMF", parse_ici_mmf),
    ("FINRA 마진", parse_finra),
    ("BofA/EPFR Reuters", lambda: parse_reuters("bofa")),
    ("LSEG Lipper Reuters", lambda: parse_reuters("lipper")),
]:
    try:
        x = fn()
        if x:
            results.append(x)
        else:
            errors.append(f"{name}: 최신 데이터 항목 미발견")
    except Exception as e:
        errors.append(f"{name}: {type(e).__name__}: {e}")

updates = []
for x in results:
    key = f"{x['source']}|{x['kind']}"
    current_fp = semantic_fingerprint(x)
    x["fingerprint"] = current_fp

    # Backward-compatible migration: old state may have fingerprints that included URL/title metadata.
    old_value = state.get("values", {}).get(key)
    old_semantic = semantic_fingerprint(old_value) if isinstance(old_value, dict) else None
    old_seen = state.get("seen", {}).get(key)

    # A source URL/domain change, article title edit, published timestamp change, or parser metadata
    # must NOT create a Telegram alert when period + metrics are identical.
    if old_semantic == current_fp or old_seen == current_fp:
        continue
    updates.append(x)

ici = next((x for x in results if x["kind"] == "combined"), None)
ici_mmf = next((x for x in results if x["kind"] == "mmf"), None)
finra = next((x for x in results if x["kind"] == "margin"), None)
bofa = next((x for x in results if x["kind"] == "bofa"), None)
lipper = next((x for x in results if x["kind"] == "lipper"), None)

cross = []
pairs = [
    ("BofA/EPFR", bofa["metrics"].get("us_equity_bn") if bofa else None),
    ("LSEG Lipper", lipper["metrics"].get("us_equity_bn") if lipper else None),
    ("ICI", ici["metrics"].get("domestic") if ici else None),
]
known = [(n, v) for n, v in pairs if v is not None]
for i in range(len(known)):
    for j in range(i + 1, len(known)):
        n1, v1 = known[i]
        n2, v2 = known[j]
        if v1 * v2 < 0:
            cross.append(f"{n1}와 {n2}의 미국 주식 흐름 방향이 반대 → 모집단·분류 차이로 보고 합산·평균하지 않음")

interpret = []
if bofa:
    interpret.append("BofA/EPFR: " + flow_direction(bofa["metrics"].get("us_equity_bn"), bofa["metrics"].get("mmf_bn")))
if lipper:
    interpret.append("LSEG Lipper: " + flow_direction(lipper["metrics"].get("us_equity_bn"), lipper["metrics"].get("mmf_bn")))
if ici:
    d = ici["metrics"].get("domestic")
    if d is not None:
        interpret.append(f"ICI 공식 미국 국내주식형: {'순유입' if d > 0 else '순유출'} {fmt_usd_bn_kr(d, fx)}")
if ici_mmf:
    ch = ici_mmf["metrics"].get("weekly_change_bn")
    if ch is not None:
        interpret.append(f"ICI 공식 MMF: {'증가' if ch > 0 else '감소'} {fmt_usd_bn_kr(ch, fx)}")
if finra:
    md = finra["metrics"].get("margin_debt_mom_bn")
    if md is not None:
        interpret.append(
            f"FINRA 월간 마진부채: {'증가 → 레버리지 확대' if md > 0 else '감소 → 레버리지 축소'} "
            f"({fmt_usd_bn_kr(md, fx)} 전월비)"
        )

# ICI equity and MMF must refer to the same week before treating them as a rotation pair.
if ici and ici_mmf:
    d = ici["metrics"].get("domestic")
    ch = ici_mmf["metrics"].get("weekly_change_bn")
    if d is not None and ch is not None:
        if same_reference_week(ici, ici_mmf):
            interpret.append("ICI 조합: " + flow_direction(d, ch))
        else:
            interpret.append(
                f"ICI 기간 차이: 미국 국내주식형 {ici.get('period')} / MMF {ici_mmf.get('period')} "
                "→ 서로 다른 주간이라 직접 자금 회전 판정 보류"
            )

def direction_word(v, up="증가", down="감소"):
    if v is None:
        return "확인 대기"
    if v > 0:
        return up
    if v < 0:
        return down
    return "변화 없음"


stock_signals = []
if ici and ici["metrics"].get("domestic") is not None:
    stock_signals.append(("ICI", ici["metrics"]["domestic"]))
if bofa and bofa["metrics"].get("us_equity_bn") is not None:
    stock_signals.append(("BofA/EPFR", bofa["metrics"]["us_equity_bn"]))
if lipper and lipper["metrics"].get("us_equity_bn") is not None:
    stock_signals.append(("LSEG Lipper", lipper["metrics"]["us_equity_bn"]))

mmf_change = ici_mmf["metrics"].get("weekly_change_bn") if ici_mmf else None
margin_change = finra["metrics"].get("margin_debt_mom_bn") if finra else None

if cross:
    overall_easy = (
        "주식형 펀드 방향이 출처마다 엇갈립니다. "
        "모집단과 기준기간이 다를 수 있어 합산·평균하지 않고 각 출처를 따로 봅니다."
    )
elif bofa and bofa["metrics"].get("us_equity_bn") is not None and bofa["metrics"].get("mmf_bn") is not None:
    overall_easy = "BofA/EPFR 같은 출처 내 판정: " + flow_direction(
        bofa["metrics"].get("us_equity_bn"), bofa["metrics"].get("mmf_bn")
    )
elif lipper and lipper["metrics"].get("us_equity_bn") is not None and lipper["metrics"].get("mmf_bn") is not None:
    overall_easy = "LSEG Lipper 같은 출처 내 판정: " + flow_direction(
        lipper["metrics"].get("us_equity_bn"), lipper["metrics"].get("mmf_bn")
    )
elif ici and ici_mmf and same_reference_week(ici, ici_mmf):
    overall_easy = "ICI 같은 주간 판정: " + flow_direction(
        ici["metrics"].get("domestic"), ici_mmf["metrics"].get("weekly_change_bn")
    )
elif stock_signals and ici_mmf and not same_reference_week(ici, ici_mmf):
    overall_easy = (
        "주식형과 MMF 최신값의 기준주간이 달라 직접 자금 회전 판정을 보류합니다. "
        "각 수치는 별도 신호로만 봅니다."
    )
elif not stock_signals and mmf_change is not None and margin_change is not None:
    overall_easy = (
        f"MMF는 {direction_word(mmf_change)}, 마진부채는 "
        f"{'확대' if margin_change > 0 else '축소' if margin_change < 0 else '보합'}입니다. "
        "주간 현금성 자금과 월간 레버리지는 기간이 달라 각각 별도 신호로 봅니다."
    )
else:
    overall_easy = "비교 가능한 최신값이 부족하거나 기준기간이 달라 한 방향으로 단정하지 않습니다."



status_lines = [
    "# US Fund Flow Watch",
    "",
    f"- parsed sources: {len(results)}",
    f"- updates: {len(updates)}",
]
for x in results:
    status_lines.append(f"- {x['source']} {x['kind']} | {x['period']} | {x['fingerprint'][:12]}")
for e in errors:
    status_lines.append(f"- error: {e}")
if fx:
    status_lines.append(f"- USD/KRW: {fx['usdkrw']} ({fx['date']})")
STATUS.write_text("\n".join(status_lines) + "\n", encoding="utf-8")

force = (os.getenv("FORCE_SEND") or "").lower() in ("1", "true", "yes")
if updates or force:
    body = [
        "🇺🇸 <b>[미국 증시 자금흐름 추적 | 신규 변화]</b>",
        "",
        "<b>한눈에 보기</b>",
    ]

    if ici_mmf:
        ch = ici_mmf["metrics"].get("weekly_change_bn")
        body.append(
            f"• 현금성 대기자금(MMF): {fmt_usd_bn_kr(ch, fx)} → "
            f"{'감소' if ch is not None and ch < 0 else '증가' if ch is not None and ch > 0 else '변화 없음'}"
        )
    if finra:
        md = finra["metrics"].get("margin_debt_mom_bn")
        body.append(
            f"• 레버리지(마진부채): {fmt_usd_bn_kr(md, fx)} 전월비 → "
            f"{'빚투 확대' if md is not None and md > 0 else '빚투 축소' if md is not None and md < 0 else '변화 제한'}"
        )
    if stock_signals:
        stock_text = " / ".join(
            f"{name} {fmt_usd_bn_kr(value, fx)}({'유입' if value > 0 else '유출' if value < 0 else '보합'})"
            for name, value in stock_signals
        )
        body.append("• 미국 주식형: " + stock_text)
    else:
        body.append("• 미국 주식형: 최신 비교값 자동 확인 대기")

    body += [
        f"→ <b>종합</b>: {html.escape(overall_easy)}",
        "",
        "<b>이번에 실제로 바뀐 값</b>",
    ]

    selected = updates if updates else results
    for x in selected:
        body += [
            f"<b>{html.escape(x['source'])} | {html.escape(str(x.get('period') or ''))}</b>",
            source_block(x, fx),
            f'• 원천: <a href="{html.escape(x["url"], quote=True)}">열기</a>',
            "",
        ]

    body.append("<b>현재 판정</b>")
    for s in interpret:
        body.append("• " + html.escape(s))
    for s in cross:
        body.append("• ⚠️ " + html.escape(s))
    if not interpret:
        body.append("• 비교 가능한 최신 공식 수치가 부족해 방향 판정을 보류합니다.")
    if not cross:
        body.append("• 출처 간 미국 주식 방향 충돌은 확인되지 않았거나 동시 비교 가능한 값이 부족합니다.")

    # Keep technical parser errors in the workflow status only. Telegram gets simple availability labels.
    if errors:
        body += ["", "<b>확인 대기</b>"]
        seen_labels = set()
        for e in errors:
            label = e.split(":", 1)[0].strip()
            if label and label not in seen_labels:
                seen_labels.add(label)
                body.append(f"• {html.escape(label)}: 최신값 자동 수집 재확인 중")

    body += [
        "",
        "<b>해석 원칙</b>",
        "• 같은 출처 안에서만 미국주식↔MMF 방향을 조합해 자금 회전을 해석",
        "• ICI·BofA/EPFR·LSEG Lipper는 모집단이 달라 합산·평균하지 않음",
        "• FINRA 마진부채는 월간 레버리지 확인용으로 주간 펀드 흐름과 기간을 섞지 않음",
        "• MMF 유출액이 그대로 주식으로 이동했다고 단정하지 않음",
        "• 같은 기준기간·같은 수치면 원천 URL이나 문구가 바뀌어도 중복 알림하지 않음",
        "• 모든 달러 금액은 같은 문장 바로 뒤 괄호에 한국은행 ECOS 환율 기준 원화 환산액을 함께 표시",
    ]
    if fx:
        body.append(f"• 원화 환산: 한국은행 ECOS USD/KRW {fx['usdkrw']:,.2f} ({fx['date']})")

    ALERT.write_text("\n".join(body) + "\n", encoding="utf-8")

    newstate = state
    newstate.setdefault("seen", {})
    newstate.setdefault("values", {})
    for x in results:
        key = f"{x['source']}|{x['kind']}"
        newstate["seen"][key] = x["fingerprint"]
        newstate["values"][key] = x
    newstate["updated_at_kst"] = datetime.now(timezone(timedelta(hours=9))).isoformat()
    PENDING.write_text(json.dumps(newstate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"us_fund_flow_alert_ready=true updates={len(updates)}")
else:
    print("us_fund_flow_alert_ready=false unchanged=true")
