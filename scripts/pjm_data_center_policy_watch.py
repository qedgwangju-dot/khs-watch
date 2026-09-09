#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import html
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

DOCKETS = ("ER26-3380", "ER26-3515")
KEYWORDS = (
    "reliability backstop", "rbp", "interim resource adequacy", "iras",
    "large load", "data center", "data centre", "elcc",
    "bring your own new capacity", "byonc", "resource adequacy",
    "capacity shortfall", "backstop procurement",
)
NEWS_QUERIES = (
    'PJM "Reliability Backstop Procurement"',
    'PJM "Interim Resource Adequacy Service"',
    'PJM data center large load FERC',
)
TRUSTED_NEWS_DOMAINS = (
    "pjm.com", "ferc.gov", "reuters.com", "energy-storage.news",
    "utilitydive.com", "rtoinsider.com", "publicpower.org",
    "federalregister.gov", "govinfo.gov",
)
HEADERS = {"User-Agent": "khs-watch/1.0 (+https://github.com/qedgwangju-dot/khs-watch)"}
FORMAT_VERSION = 2


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


def h(text) -> str:
    return html.escape(str(text), quote=True)


def a(label: str, url: str) -> str:
    return f'<a href="{h(url)}">{h(label)}</a>'


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


def usd_korean(usd: float) -> str:
    # Exact dollar amount in Korean-readable units, with $B for identification.
    eok_usd = round(usd / 100_000_000)
    jo, rem_eok = divmod(eok_usd, 10000)
    if jo:
        korean = f"{jo:,}조 {rem_eok:,}억달러" if rem_eok else f"{jo:,}조달러"
    else:
        korean = f"{eok_usd:,}억달러"
    return f"{korean} (${usd/1e9:,.3f}B)"


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
    if re.search(r"Sept\.\s*30,\s*2026", text, re.I):
        start_date = "2026-09-30"
    return {
        "target_mw": target,
        "max_price_usd_mw_day": price,
        "max_years": years,
        "planned_start": start_date,
    }


def collect_pjm_page(url: str, label: str):
    soup = BeautifulSoup(fetch(url).text, "html.parser")
    items = []
    seen_url_title = set()

    # Only evaluate the anchor itself. Using a large parent container can make
    # hundreds of unrelated links look relevant when one keyword occurs nearby.
    for link in soup.find_all("a"):
        text = normalize(link.get_text(" "))
        href = absurl(url, link.get("href"))
        if not text or not href.startswith("http"):
            continue
        blob = f"{text} {href}"
        if not relevant(blob):
            continue
        key = (text.lower(), href)
        if key in seen_url_title:
            continue
        seen_url_title.add(key)
        items.append({
            "id": sig(label, text, href),
            "source": label,
            "title": text[:240],
            "url": href,
            "official": True,
        })

    # Capture docket mentions that are not linked directly.
    body = normalize(soup.get_text(" "))
    for docket in DOCKETS:
        for match in re.finditer(re.escape(docket), body, re.I):
            frag = body[max(0, match.start() - 120):match.end() + 260]
            items.append({
                "id": sig(label, docket, frag),
                "source": label,
                "title": frag[:360],
                "url": url,
                "official": True,
            })

    return list({x["id"]: x for x in items}.values())


def collect_federal_register():
    out = []
    for docket in DOCKETS:
        params = {"per_page": 20, "order": "newest", "conditions[term]": docket}
        try:
            data = fetch(FR_API + "?" + urllib.parse.urlencode(params), 30).json()
            for row in data.get("results", []):
                title = normalize(
                    f"{row.get('publication_date', '')} {row.get('title', '')} {row.get('abstract', '')}"
                )
                url = row.get("html_url") or row.get("pdf_url") or "https://www.federalregister.gov/"
                if docket.lower() in title.lower() or relevant(title):
                    out.append({
                        "id": sig("Federal Register", docket, row.get("document_number", ""), title),
                        "source": "Federal Register",
                        "title": title[:420],
                        "url": url,
                        "official": True,
                    })
        except Exception:
            pass
    return list({x["id"]: x for x in out}.values())


def collect_google_news():
    out = []
    for query in NEWS_QUERIES:
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
            {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
        )
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
                out.append({
                    "id": sig("News", title, link),
                    "source": source or domain,
                    "title": title[:320],
                    "url": link,
                    "official": domain.endswith("pjm.com") or domain.endswith("ferc.gov") or domain.endswith("federalregister.gov"),
                })
        except Exception:
            pass
    return list({x["id"]: x for x in out}.values())


def event_priority(item):
    low = item["title"].lower()
    if any(k in low for k in (
        "order", "approved", "accept", "reject", "denied", "effective",
        "award", "selected", "procurement result", "ferc",
    )):
        return 0
    if any(d.lower() in low for d in DOCKETS):
        return 1
    if any(k in low for k in (
        "elcc", "participant", "training", "manual", "rfi", "rfp",
        "large load", "data center", "data centre",
    )):
        return 2
    return 3


def source_short(source: str) -> str:
    s = source.lower()
    if "pjm" in s:
        return "PJM"
    if "federal register" in s:
        return "Federal Register"
    if "utility dive" in s:
        return "Utility Dive"
    if "rto" in s:
        return "RTO Insider"
    if "reuters" in s:
        return "Reuters"
    if "energy-storage" in s:
        return "Energy-Storage.News"
    if "public power" in s:
        return "Public Power"
    return source[:40]


def concise_title(title: str, max_len: int = 150) -> str:
    text = normalize(title)
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


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
for url, label in (
    (PJM_HOME, "PJM 최신 공시·명령"),
    (PJM_RBP, "PJM RBP 공식 페이지"),
):
    try:
        items += collect_pjm_page(url, label)
    except Exception as exc:
        errors.append(f"{label}: {type(exc).__name__}")
try:
    items += collect_federal_register()
except Exception as exc:
    errors.append(f"Federal Register: {type(exc).__name__}")
try:
    items += collect_google_news()
except Exception as exc:
    errors.append(f"News: {type(exc).__name__}")

items = list({x["id"]: x for x in items}.values())
items.sort(key=lambda x: (event_priority(x), 0 if x.get("official") else 1, x["source"], x["title"]))
old_ids = set(old.get("seen_ids", []))
new_items = [x for x in items if x["id"] not in old_ids]
baseline_run = not old.get("initialized")
format_upgrade = int(old.get("format_version", 0) or 0) < FORMAT_VERSION

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

# New trusted items remain alert-worthy, but the message only surfaces the most
# decision-relevant items. The rest are retained in state for deduplication.
should_alert = baseline_run or format_upgrade or bool(changes) or bool(new_items)

seen = list(dict.fromkeys(list(old_ids) + [x["id"] for x in items]))[-1200:]
pending = {
    "initialized": True,
    "format_version": FORMAT_VERSION,
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

    if baseline_run:
        title = "✅ PJM 데이터센터 전력정책 감시 연결 완료"
    elif format_upgrade and not changes and not new_items:
        title = "✅ PJM 데이터센터 전력정책 알림 표시방식 업그레이드 완료"
    else:
        title = "🚨 PJM 데이터센터 전력정책 변화"

    msg = [f"<b>{h(title)}</b>", ""]

    msg += ["<b>📌 현재 공식 기준</b>"]
    if target:
        msg.append(f"• 신뢰도 부족분  <b>{target:,}MW</b>")
    if price:
        msg.append(
            f"• RBP 최대가격  <b>${price:,.0f}/MW-day</b> = <b>{h(krw_unit(price, fx, 'MW-day'))}</b>"
        )
    if years:
        msg.append(f"• 최대 계약기간  <b>{years}년</b>")
    if baseline.get("planned_start"):
        msg.append(f"• 개시 목표  <b>{h(baseline['planned_start'])}</b> · FERC 승인 전제")

    if annual_usd or total_usd:
        msg += ["", "<b>💰 비용 감각</b>"]
    if annual_usd:
        msg.append(
            f"• 1년 단순상단  <b>{h(usd_korean(annual_usd))}</b> = <b>{h(krw_from_usd(annual_usd, fx))}</b>"
        )
    if total_usd:
        msg.append(
            f"• {years}년 단순상단  <b>{h(usd_korean(total_usd))}</b> = <b>{h(krw_from_usd(total_usd, fx))}</b>"
        )
        msg.append("• <i>실제 낙찰가격·목표MW·계약기간은 달라질 수 있어 확정비용이 아닙니다.</i>")

    if changes:
        msg += ["", "<b>🔄 숫자 변경</b>"]
        for label, old_v, new_v in changes:
            msg.append(f"• {h(label)}  <b>{h(old_v)} → {h(new_v)}</b>")

    if new_items:
        official_count = sum(1 for x in new_items if x.get("official"))
        news_count = len(new_items) - official_count
        msg += ["", "<b>🆕 신규 확인</b>"]
        msg.append(
            f"• 새 자료 <b>{len(new_items)}건</b> · 공식 <b>{official_count}건</b> · 신뢰보도 <b>{news_count}건</b>"
        )
        shown = new_items[:6]
        for x in shown:
            src = source_short(x["source"])
            title_text = concise_title(x["title"], 145)
            badge = "공식" if x.get("official") else "보도"
            msg.append(
                f"• <b>[{h(badge)}] {h(src)}</b> · {h(title_text)}  {a('원문', x['url'])}"
            )
        if len(new_items) > len(shown):
            msg.append(
                f"• 나머지 <b>{len(new_items)-len(shown)}건</b>은 중복방지용 상태에 저장하고 다음 변화 판정에 반영합니다."
            )
    elif baseline_run or format_upgrade:
        msg += [
            "",
            "<b>👀 감시 범위</b>",
            "• FERC/PJM RBP·IRAS 승인·반려·발효일",
            "• 9월 30일 RBP 개시 여부와 일정 변경",
            "• 실제 목표MW → 낙찰MW → 낙찰가격 → 계약기간",
            "• BESS·가스·원전·청정에너지 낙찰 기술과 사업자",
            "• BESS ELCC·대형부하 등록·BYONC·비상 감축 규칙",
            "• 데이터센터 비용부담·송전/변전 비용 사회화 변화",
        ]

    msg += [
        "",
        "<b>📊 투자 해석</b>",
        "• <b>가장 먼저 볼 숫자:</b> 부족분 MW → 실제 RBP 목표MW → 낙찰MW → 상업운전 MW",
        "• BESS는 빠른 건설·입지 유연성이 장점이지만 <b>6,831MW 전부를 배터리 수주로 보지 않습니다.</b>",
        "• 발전원과 대형부하의 위치가 다르면 송전·변전 증설비가 별도 병목이 될 수 있습니다.",
        "",
        "<b>💱 환율</b>",
        f"• <b>1달러 = {fx:,.2f}원</b> · {h(fx_source)} · {h(fx_checked)} UTC",
        "• 외화 금액은 전부 같은 환율로 원화 환산합니다.",
        "",
        "<b>🔗 공식 원문</b>",
        f"• {a('PJM RBP 원문', PJM_RBP)}",
        f"• {a('PJM 기준 설명', PJM_BASELINE)}",
        f"• {a('FERC Decisions', FERC_DECISIONS)}",
    ]

    # Telegram sendMessage limit is 4096 characters after entity parsing.
    # Keep the core numbers and interpretation intact; only trim low-priority
    # source rows if an unusually long title set pushes the body too far.
    text = "\n".join(msg)
    if len(re.sub(r"<[^>]+>", "", text)) > 3900 and new_items:
        # Rebuild with only top 3 new source rows, preserving all core sections.
        marker = "<b>🆕 신규 확인</b>"
        start = msg.index(marker)
        end = next((i for i in range(start + 1, len(msg)) if msg[i] == "<b>📊 투자 해석</b>"), len(msg))
        replacement = [marker]
        official_count = sum(1 for x in new_items if x.get("official"))
        news_count = len(new_items) - official_count
        replacement.append(
            f"• 새 자료 <b>{len(new_items)}건</b> · 공식 <b>{official_count}건</b> · 신뢰보도 <b>{news_count}건</b>"
        )
        for x in new_items[:3]:
            badge = "공식" if x.get("official") else "보도"
            replacement.append(
                f"• <b>[{h(badge)}] {h(source_short(x['source']))}</b> · {h(concise_title(x['title'], 120))}  {a('원문', x['url'])}"
            )
        if len(new_items) > 3:
            replacement.append(f"• 나머지 <b>{len(new_items)-3}건</b>은 상태에 저장·추적합니다.")
        msg = msg[:start] + replacement + [""] + msg[end:]
        text = "\n".join(msg)

    ALERT.write_text(text + "\n", encoding="utf-8")

STATUS.write_text(
    "# PJM 데이터센터 전력정책 감시\n\n"
    f"- 형식 버전: **{FORMAT_VERSION}**\n"
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
print(
    f"pjm_policy format={FORMAT_VERSION} baseline={baseline} "
    f"new_items={len(new_items)} changes={len(changes)} format_upgrade={format_upgrade} alert={should_alert}"
)
