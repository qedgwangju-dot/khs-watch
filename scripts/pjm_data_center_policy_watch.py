#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

import requests
from bs4 import BeautifulSoup

OUT = Path("out")
STATE = Path("data/pjm_data_center_policy_state.json")
ALERT = OUT / "pjm_data_center_policy_alert.txt"
PENDING = OUT / "pjm_data_center_policy_pending_state.json"
STATUS = OUT / "pjm_data_center_policy_status.md"

PJM_HOME = "https://www.pjm.com/"
PJM_RBP = "https://www.pjm.com/committees-and-groups/cifp-rbp"
PJM_BASELINE = "https://insidelines.pjm.com/pjm-reliability-backstop-proposal-outlines-steps-to-secure-new-supply-and-maintain-reliability/"
FERC_DECISIONS = "https://www.ferc.gov/news-events/news/decisions-notices"
FR_API = "https://www.federalregister.gov/api/v1/documents.json"
SOURCE_LINKS = [PJM_HOME, PJM_RBP, PJM_BASELINE, FERC_DECISIONS]

DOCKETS = ("ER26-3380", "ER26-3515")
KEYWORDS = (
    "reliability backstop", "rbp", "interim resource adequacy", "iras",
    "large load", "data center", "data centre", "elcc", "bring your own new capacity",
    "byonc", "resource adequacy", "capacity shortfall", "backstop procurement",
)
NEWS_QUERIES = (
    'PJM "Reliability Backstop Procurement"',
    'PJM "Interim Resource Adequacy Service"',
    'PJM data center large load FERC',
)
TRUSTED_NEWS_DOMAINS = (
    "pjm.com", "ferc.gov", "reuters.com", "energy-storage.news", "utilitydive.com",
    "rtoinsider.com", "publicpower.org", "federalregister.gov", "govinfo.gov",
)
HEADERS = {"User-Agent": "khs-watch/1.0 (+https://github.com/qedgwangju-dot/khs-watch)"}


def fetch(url: str, timeout: int = 35):
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r


def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def absurl(base: str, href: str) -> str:
    return urllib.parse.urljoin(base, href or "")


def sig(*parts: str) -> str:
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:20]


def relevant(text: str) -> bool:
    low = (text or "").lower()
    return any(k in low for k in KEYWORDS) or any(d.lower() in low for d in DOCKETS)


def fx_rate(old=None):
    sources = [
        ("https://open.er-api.com/v6/latest/USD", lambda d: d["rates"]["KRW"], "ER-API"),
        ("https://api.frankfurter.app/latest?from=USD&to=KRW", lambda d: d["rates"]["KRW"], "Frankfurter"),
    ]
    for url, parser, name in sources:
        try:
            v = float(parser(fetch(url, 20).json()))
            if 500 < v < 3000:
                return v, name
        except Exception:
            pass
    if old:
        return float(old), "직전 저장값"
    return None, "조회 실패"


def krw_from_usd(usd: float, fx: float | None) -> str:
    if not fx:
        return "원화 환산 확인 불가"
    eok = round(usd * fx / 100_000_000)
    jo, rem = divmod(eok, 10000)
    if jo and rem:
        return f"약 {jo:,}조 {rem:,}억원"
    if jo:
        return f"약 {jo:,}조원"
    return f"약 {rem:,}억원"


def krw_unit(usd: float, fx: float | None, suffix: str) -> str:
    if not fx:
        return "원화 환산 확인 불가"
    return f"약 {usd * fx:,.0f}원/{suffix}"


def parse_baseline():
    text = normalize(BeautifulSoup(fetch(PJM_BASELINE).text, "html.parser").get_text(" "))
    target = None
    price = None
    years = None
    start_date = None
    m = re.search(r"([0-9,]+)\s*MW shortfall", text, re.I)
    if m:
        target = int(m.group(1).replace(",", ""))
    m = re.search(r"\$([0-9,]+)\s*/\s*MW-day", text, re.I)
    if m:
        price = float(m.group(1).replace(",", ""))
    m = re.search(r"terms of up to\s+(\d+)\s+years", text, re.I)
    if m:
        years = int(m.group(1))
    m = re.search(r"commencing .*? on\s+Sept\.\s*30,\s*2026", text, re.I)
    if m:
        start_date = "2026-09-30"
    return {"target_mw": target, "max_price_usd_mw_day": price, "max_years": years, "planned_start": start_date}


def collect_pjm_page(url: str, label: str):
    soup = BeautifulSoup(fetch(url).text, "html.parser")
    items = []
    for a in soup.find_all("a"):
        text = normalize(a.get_text(" "))
        href = absurl(url, a.get("href"))
        parent_text = normalize(a.parent.get_text(" ")) if a.parent else text
        blob = f"{text} {parent_text} {href}"
        if relevant(blob):
            title = text or parent_text[:180]
            items.append({"id": sig(label, title, href), "source": label, "title": title[:240], "url": href})
    # PJM homepage latest filings/orders often have useful docket text outside the anchor itself.
    body = normalize(soup.get_text(" "))
    for d in DOCKETS:
        for m in re.finditer(re.escape(d), body, re.I):
            frag = body[max(0, m.start()-180):m.end()+360]
            items.append({"id": sig(label, d, frag), "source": label, "title": frag[:500], "url": url})
    dedup = {x["id"]: x for x in items}
    return list(dedup.values())


def collect_federal_register():
    out = []
    for docket in DOCKETS:
        params = {"per_page": 20, "order": "newest", "conditions[term]": docket}
        try:
            data = fetch(FR_API + "?" + urllib.parse.urlencode(params), 30).json()
            for r in data.get("results", []):
                title = normalize(f"{r.get('publication_date','')} {r.get('title','')} {r.get('abstract','')}")
                url = r.get("html_url") or r.get("pdf_url") or "https://www.federalregister.gov/"
                if docket.lower() in title.lower() or relevant(title):
                    out.append({"id": sig("Federal Register", docket, r.get("document_number", ""), title), "source": "Federal Register", "title": title[:500], "url": url})
        except Exception:
            pass
    return list({x["id"]: x for x in out}.values())


def collect_google_news():
    out = []
    for q in NEWS_QUERIES:
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"})
        try:
            root = ET.fromstring(fetch(url, 30).content)
            for item in root.findall("./channel/item")[:15]:
                title = normalize(item.findtext("title") or "")
                link = normalize(item.findtext("link") or "")
                source_el = item.find("source")
                source = normalize(source_el.text if source_el is not None else "")
                source_url = normalize(source_el.attrib.get("url", "") if source_el is not None else "")
                domain = urllib.parse.urlparse(source_url).netloc.lower()
                if not any(domain.endswith(d) for d in TRUSTED_NEWS_DOMAINS):
                    continue
                if not relevant(title + " " + source):
                    continue
                out.append({"id": sig("News", title, link), "source": source or domain, "title": title[:350], "url": link})
        except Exception:
            pass
    return list({x["id"]: x for x in out}.values())


def event_priority(item):
    low = item["title"].lower()
    if any(k in low for k in ("order", "approved", "accept", "reject", "denied", "effective", "award", "selected", "procurement result", "ferc")):
        return 0
    if any(d.lower() in low for d in DOCKETS):
        return 1
    if any(k in low for k in ("elcc", "participant", "training", "manual", "rfi", "rfp")):
        return 2
    return 3


OUT.mkdir(exist_ok=True)
for p in (ALERT, PENDING, STATUS):
    if p.exists():
        p.unlink()

old = load_state()
fx, fx_source = fx_rate(old.get("last_fx_krw_per_usd"))
if fx is None:
    raise SystemExit("KRW exchange rate unavailable; refusing to create a monetary alert without KRW")
fx_checked = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

baseline = parse_baseline()
items = []
errors = []
for url, label in ((PJM_HOME, "PJM 최신 공시·명령"), (PJM_RBP, "PJM RBP 공식 페이지")):
    try:
        items += collect_pjm_page(url, label)
    except Exception as e:
        errors.append(f"{label}: {type(e).__name__}")
try:
    items += collect_federal_register()
except Exception as e:
    errors.append(f"Federal Register: {type(e).__name__}")
try:
    items += collect_google_news()
except Exception as e:
    errors.append(f"News: {type(e).__name__}")

items = list({x["id"]: x for x in items}.values())
items.sort(key=event_priority)
old_ids = set(old.get("seen_ids", []))
new_items = [x for x in items if x["id"] not in old_ids]
baseline_run = not old.get("initialized")

# Meaningful baseline changes are tracked separately from new documents.
changes = []
for key, label in (
    ("target_mw", "RBP 목표 부족분"),
    ("max_price_usd_mw_day", "RBP 최대 지급의향가격"),
    ("max_years", "최대 계약기간"),
    ("planned_start", "RBP 개시 목표일"),
):
    old_v = old.get("baseline", {}).get(key)
    new_v = baseline.get(key)
    if old_v is not None and new_v is not None and old_v != new_v:
        changes.append((label, old_v, new_v))

# First run sends one concise upgrade confirmation. Later runs send only new official/trusted developments or numeric changes.
should_alert = baseline_run or bool(changes) or bool(new_items)

seen = list(dict.fromkeys(list(old_ids) + [x["id"] for x in items]))[-800:]
pending = {
    "initialized": True,
    "baseline": baseline,
    "seen_ids": seen,
    "last_fx_krw_per_usd": fx,
    "fx_source": fx_source,
    "fx_checked_utc": fx_checked,
    "updated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    "source_errors": errors,
}
PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

if should_alert:
    target = baseline.get("target_mw")
    price = baseline.get("max_price_usd_mw_day")
    years = baseline.get("max_years")
    annual_usd = target * price * 365 if target and price else None
    total_usd = annual_usd * years if annual_usd and years else None
    title = "✅ PJM 데이터센터 전력정책 감시 업그레이드 완료" if baseline_run else "🚨 PJM 데이터센터 전력정책 변화"
    msg = [title, ""]

    msg += ["[현재 공식 기준]"]
    if target:
        msg.append(f"• 2028/2029 신뢰도 부족분: {target:,}MW")
    if price:
        msg.append(f"• RBP 최대 지급의향가격: ${price:,.0f}/MW-day = {krw_unit(price, fx, 'MW-day')}")
    if years:
        msg.append(f"• 최대 계약기간: {years}년")
    if baseline.get("planned_start"):
        msg.append(f"• PJM 개시 목표일: {baseline['planned_start']} (FERC 승인 전제)")
    if annual_usd:
        msg.append(f"• 전량 최대가격 1년 단순상단: ${annual_usd/1e9:,.3f}B = {krw_from_usd(annual_usd, fx)}")
    if total_usd:
        msg.append(f"• 같은 조건 {years}년 단순상단: ${total_usd/1e9:,.3f}B = {krw_from_usd(total_usd, fx)}")
        msg.append("• 주의: 실제 낙찰가격·목표MW·계약기간은 달라질 수 있어 위 금액은 확정비용이 아닙니다.")

    if changes:
        msg += ["", "[숫자 변경]"]
        for label, old_v, new_v in changes:
            msg.append(f"• {label}: {old_v} → {new_v}")

    if new_items:
        msg += ["", "[신규 확인]"]
        for x in new_items[:8]:
            msg.append(f"• {x['source']}: {x['title']}")
            msg.append(f"  {x['url']}")
        if len(new_items) > 8:
            msg.append(f"• 그 외 신규 자료 {len(new_items)-8}건")
    elif baseline_run:
        msg += ["", "[감시 범위]", "• FERC/PJM RBP·IRAS 승인·반려·발효일", "• 9월 30일 RBP 개시 여부 및 일정 변경", "• 실제 조달 목표MW·낙찰MW·낙찰가격·계약기간", "• 낙찰 기술(BESS·가스·원전·청정에너지)과 사업자", "• BESS ELCC 공식 수치 및 새 평가자료", "• 대형부하 등록·BYONC·비상 감축 우선순위", "• 데이터센터 비용부담·송전망 비용 사회화 변화"]

    msg += [
        "",
        "[투자 해석]",
        "• 가장 먼저 볼 숫자: 부족분 MW → 실제 RBP 목표MW → 낙찰MW → 상업운전 MW.",
        "• BESS는 빠른 건설·입지 유연성이 장점이지만 낙찰 확정 전에는 6,831MW 전부를 배터리 수주로 보지 않습니다.",
        "• 발전원과 대형부하의 위치가 다르면 송전·변전 증설비가 별도 병목이 될 수 있습니다.",
        "",
        "[환율]",
        f"• 1달러 = {fx:,.2f}원 ({fx_source})",
        f"• 조회시각(UTC): {fx_checked}",
        "• 외화 금액은 모두 같은 환율로 원화 환산합니다.",
        "",
        "[공식 원문]",
        f"• PJM RBP: {PJM_RBP}",
        f"• PJM 기준 설명: {PJM_BASELINE}",
        f"• FERC Decisions: {FERC_DECISIONS}",
    ]
    ALERT.write_text("\n".join(msg) + "\n", encoding="utf-8")

STATUS.write_text(
    "# PJM 데이터센터 전력정책 감시\n\n"
    f"- RBP 기준 부족분: **{baseline.get('target_mw')} MW**\n"
    f"- 최대가격: **${baseline.get('max_price_usd_mw_day')}/MW-day**\n"
    f"- 최대 계약기간: **{baseline.get('max_years')}년**\n"
    f"- 개시 목표: **{baseline.get('planned_start')}**\n"
    f"- 현재 신규 자료: **{len(new_items)}건**\n"
    f"- 숫자 변경: **{len(changes)}건**\n"
    f"- 알림: **{'예' if should_alert else '아니오'}**\n"
    f"- 원천 오류: **{'; '.join(errors) if errors else '없음'}**\n",
    encoding="utf-8",
)
print(f"pjm_policy baseline={baseline} new_items={len(new_items)} changes={len(changes)} alert={should_alert}")
