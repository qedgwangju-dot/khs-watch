#!/usr/bin/env python3
"""Compact GAMEJOA 06:30 KST news radar runner for GitHub Actions."""

from __future__ import annotations

import csv
import datetime as dt
import email.utils
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
KST = ZoneInfo("Asia/Seoul")
MAX_AGE_HOURS = int(os.getenv("RADAR_MAX_AGE_HOURS", "48"))
UA = os.getenv("SEC_USER_AGENT", "GAMEJOA-preopen-radar contact=please-set-secret")
FRED_API_KEY = os.getenv("FRED_API_KEY", "").strip()
TELEGRAM_LIMIT = 4096

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFII10"
TE_URL = "https://tradingeconomics.com/united-states/10-year-tips-yield"

SOURCES = [
    ("FERC", "https://www.ferc.gov/news-events/news/rss.xml", "official"),
    ("DOE", "https://www.energy.gov/rss.xml", "official"),
    ("SEC", "https://www.sec.gov/news/pressreleases.rss", "official"),
    ("Federal Register data center", "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bterm%5D=data%20center%20power%20grid&order=newest&per_page=15", "fr"),
    ("Federal Register export controls", "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bterm%5D=semiconductor%20export%20controls&order=newest&per_page=15", "fr"),
    ("Federal Register tariffs", "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bterm%5D=tariff%20section%20301&order=newest&per_page=15", "fr"),
]

QUERIES = [
    ("AI 전력망", "FERC DOE AI data center power grid nuclear energy policy Reuters Bloomberg CNBC"),
    ("데이터센터 지역 금지", '"data center" ban moratorium city council residents vote zoning power Reuters Bloomberg AP USA Today'),
    ("반도체/AI", "Nvidia Micron Broadcom AMD TSMC ASML AI chip guidance supply agreement Reuters Bloomberg MarketWatch"),
    ("수출통제/관세", "US Commerce BIS export controls tariffs China semiconductor Reuters Bloomberg AP"),
    ("지정학/에너지", "Iran Israel Hormuz Red Sea oil shipping sanctions Reuters Bloomberg AP CNBC MarketWatch"),
    ("한국 직접 영향", "Samsung SK Hynix LG Energy Solution Hyundai Korea export policy supply contract Reuters Bloomberg"),
    ("FDA/바이오", "FDA approval complete response letter clinical trial pharma acquisition Reuters Bloomberg CNBC"),
]

TRUSTED = ["reuters", "bloomberg", "associated press", "ap news", "cnbc", "marketwatch", "usa today", "panama city news herald", "columbus dispatch"]
TERMS = ["approval", "ban", "blocked", "capex", "city council", "contract", "court order", "crl", "data center", "earnings", "entity list", "export control", "fda", "final rule", "guidance", "injunction", "merger", "moratorium", "permit", "regulation", "sanction", "section 301", "semiconductor", "supply agreement", "tariff", "vote", "zoning"]

SECTORS = [
    ("반도체/AI", ["ai", "chip", "hbm", "micron", "nvidia", "semiconductor", "tsmc", "asml"]),
    ("데이터센터/전력망/전력기기", ["data center", "city council", "moratorium", "zoning", "grid", "power", "ferc", "doe"]),
    ("관세/수출통제", ["export control", "section 301", "tariff", "bis", "ustr"]),
    ("방산/정유/해운/지정학", ["hormuz", "iran", "israel", "oil", "red sea", "shipping", "ukraine"]),
    ("바이오/FDA", ["fda", "clinical", "crl", "pharma"]),
    ("한국 직접 영향", ["samsung", "sk hynix", "korea", "lg energy", "hyundai"]),
]


def kst_now() -> dt.datetime:
    return dt.datetime.now(tz=KST)


def clean(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<!\[CDATA\[|\]\]>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def norm(value: object) -> str:
    return clean(value).lower()


def fetch(url: str, timeout: int = 25) -> tuple[str | None, str | None]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, application/json, text/html, */*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, "replace"), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def parse_date(value: object) -> dt.datetime | None:
    text = clean(value)
    if not text:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(KST)
    except Exception:
        pass
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            parsed = dt.datetime.strptime(text[:25], fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            return parsed.astimezone(KST)
        except Exception:
            continue
    return None


def parse_rss(text: str, source: str, layer: str) -> list[dict]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    rows = []
    for node in root.findall(".//item")[:25]:
        rows.append({
            "source": source,
            "layer": layer,
            "publisher": clean(node.findtext("source")) or source,
            "title": clean(node.findtext("title")),
            "link": clean(node.findtext("link")),
            "summary": clean(node.findtext("description")),
            "published": parse_date(node.findtext("pubDate") or node.findtext("date")),
        })
    return rows


def parse_fr(text: str, source: str) -> list[dict]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    rows = []
    for row in (data.get("results") or [])[:15]:
        rows.append({
            "source": source,
            "layer": "official",
            "publisher": "Federal Register",
            "title": clean(row.get("title") or row.get("citation")),
            "link": clean(row.get("html_url") or row.get("pdf_url")),
            "summary": clean(" ".join(str(row.get(k, "")) for k in ("type", "document_number", "abstract", "excerpt"))),
            "published": parse_date(row.get("publication_date") or row.get("signing_date")),
        })
    return rows


def google_url(query: str) -> str:
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})


def age_hours(row: dict, now: dt.datetime) -> float | None:
    if not row.get("published"):
        return None
    return (now - row["published"]).total_seconds() / 3600


def fresh(row: dict, now: dt.datetime) -> bool:
    age = age_hours(row, now)
    if age is None:
        return row.get("layer") == "official"
    return -1 <= age <= MAX_AGE_HOURS


def trusted(source: str) -> bool:
    s = norm(source)
    return any(t in s for t in TRUSTED)


def has(text: str, term: str) -> bool:
    escaped = re.escape(term.lower()).replace(r"\ ", r"\s+")
    return re.search(rf"(^|[^a-z0-9]){escaped}($|[^a-z0-9])", text) is not None


def collect_items(now: dt.datetime) -> tuple[list[dict], list[str]]:
    rows, notes = [], []
    for name, url, kind in SOURCES:
        text, err = fetch(url)
        if err:
            notes.append(f"{name}: 확인 불가 ({err})")
            continue
        parsed = parse_fr(text or "", name) if kind == "fr" else parse_rss(text or "", name, "official")
        parsed = [r for r in parsed if fresh(r, now)]
        notes.append(f"{name}: {len(parsed)}건")
        rows.extend(parsed)
    for name, query in QUERIES:
        text, err = fetch(google_url(f"{query} when:{max(1, MAX_AGE_HOURS // 24)}d"))
        if err:
            notes.append(f"Trusted news {name}: 확인 불가 ({err})")
            continue
        parsed = [r for r in parse_rss(text or "", f"Trusted news {name}", "trusted") if fresh(r, now) and trusted(r.get("publisher") or r.get("source"))]
        notes.append(f"Trusted news {name}: {len(parsed)}건")
        rows.extend(parsed)
    return rows, notes


def classify(row: dict, now: dt.datetime) -> dict | None:
    title = clean(row.get("title"))
    if len(title) < 8:
        return None
    text = norm(f"{title} {row.get('summary')} {row.get('publisher')} {row.get('source')}")
    matched = [t for t in TERMS if has(text, t)]
    sectors = [label for label, keys in SECTORS if any(has(text, k) for k in keys)]
    if not matched or not sectors:
        return None
    impacts = []
    if any(t in matched for t in ["contract", "earnings", "guidance", "approval", "supply agreement", "fda", "capex"]):
        impacts.append("돈 버는 능력")
    if any(t in matched for t in ["ban", "blocked", "city council", "moratorium", "regulation", "tariff", "zoning"]):
        impacts.append("할인율")
    if any(t in matched for t in ["entity list", "export control", "sanction", "supply"]):
        impacts.append("수급")
    if any(t in matched for t in ["city council", "court order", "final rule", "injunction", "permit", "vote"]):
        impacts.append("시간표")
    impacts = list(dict.fromkeys(impacts)) or ["의사결정 영향 제한적"]
    age = age_hours(row, now)
    score = (28 if row.get("layer") == "official" else 0) + (20 if trusted(row.get("publisher") or row.get("source")) else 0) + min(36, len(matched) * 6) + len(impacts) * 10 + len(sectors) * 6
    if age is not None and age <= 12:
        score += 14
    if "데이터센터/전력망/전력기기" in sectors and any(t in matched for t in ["ban", "moratorium", "city council", "vote", "zoning"]):
        score += 18
    if score < 58:
        return None
    status = "확정" if row.get("layer") == "official" else "공식 확인 전"
    importance = "상" if score >= 100 else "중" if score >= 76 else "하"
    if "데이터센터/전력망/전력기기" in sectors:
        interp = "AI 인프라 병목이 GPU만이 아니라 전력·입지·주민수용성으로 번지는지 보는 재료입니다. 한국장에서는 전력기기와 데이터센터 밸류체인 프리미엄 지속성을 점검해야 합니다."
        fail = "전력기기·전선·원전·냉각·서버 밸류체인이 따라오지 않거나 공식 문서가 확인되지 않으면 재료 약화"
    elif "반도체/AI" in sectors:
        interp = "AI·메모리 수요 또는 공급 제한을 건드릴 수 있어 한국 반도체 대형주와 소부장 수급에 연결됩니다. 해외 티커 반응으로 이미 반영됐는지 재확인이 필요합니다."
        fail = "SOX/MU/NVDA/메모리 가격이 반응하지 않거나 가이던스가 수요 둔화를 시사하면 실패"
    else:
        interp = "돈 버는 능력, 할인율, 수급, 시간표 중 하나를 바꿀 수 있는 후보입니다. 원문 조건과 가격 반응을 장전 수치에서 재확인해야 합니다."
        fail = "관련 해외 티커·원자재·금리·환율·한국 수급이 동행하지 않으면 단발성 뉴스"
    return {
        "score": score,
        "importance": importance,
        "status": status,
        "news": title,
        "publisher": row.get("publisher") or row.get("source"),
        "source": row.get("source"),
        "link": row.get("link") or "",
        "published": row["published"].isoformat(timespec="minutes") if row.get("published") else "확인 불가",
        "impacts": impacts,
        "paths": ["이익" if x == "돈 버는 능력" else "할인율" if x == "할인율" else "수급" if x == "수급" else "정책 타임라인" for x in impacts],
        "sectors": sectors,
        "matched": matched[:10],
        "reflection": "낮음" if age is not None and age <= 6 else "중간" if age is None or age <= 24 else "높음",
        "counter": "제목·요약 기반 1차 감지라 원문 세부조건과 공식 문서 확인 전 과대해석 가능" if status != "확정" else "시행일, 적용 대상, 금액, 기간, 독점성, 매출 인식 조건 확인 전 영향이 제한될 수 있음",
        "interpretation": interp,
        "failed_signal": fail,
        "korea_basis": "예고된 이벤트의 공식화" if status == "확정" else "외신 확산",
    }


def collect_dfii10() -> dict:
    if FRED_API_KEY:
        url = "https://api.stlouisfed.org/fred/series/observations?" + urllib.parse.urlencode({"series_id": "DFII10", "file_type": "json", "sort_order": "desc", "limit": "10", "api_key": FRED_API_KEY})
        text, err = fetch(url, 30)
        if not err and text:
            for row in json.loads(text).get("observations", []):
                if row.get("value") and row.get("value") != ".":
                    return {"source": "FRED API DFII10", "status": "확인됨", "reference": row.get("date"), "value": float(row.get("value")), "error": None}
    text, err = fetch(FRED_CSV, 60)
    if err or not text:
        return {"source": FRED_CSV, "status": "확인 불가", "reference": "확인 불가", "value": None, "error": err}
    for row in reversed(list(csv.DictReader(text.splitlines()))):
        if row.get("DFII10") and row.get("DFII10") != ".":
            return {"source": FRED_CSV, "status": "확인됨", "reference": row.get("observation_date"), "value": float(row.get("DFII10")), "error": None}
    return {"source": FRED_CSV, "status": "확인 불가", "reference": "확인 불가", "value": None, "error": "latest non-empty row not found"}


def collect_te() -> dict:
    text, err = fetch(TE_URL)
    if err or not text:
        return {"source": TE_URL, "status": "확인 불가", "reference": "확인 불가", "value": None, "error": err}
    body = clean(text)
    row = re.search(r"US\s+10Y\s+TIPS\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)%\s+(-?\d+(?:\.\d+)?)%\s+(-?\d+(?:\.\d+)?)%\s+([A-Za-z]{3}/\d{1,2})", body, re.I)
    meta = re.search(r"10 Year TIPS Yield.{0,150}?(-?\d+(?:\.\d+)?)\s*(?:%|percent)\s+on\s+([A-Za-z]+ \d{1,2}, \d{4})", body, re.I)
    if row:
        return {"source": TE_URL, "status": "확인됨", "reference": row.group(5), "value": float(row.group(1)), "meta_value": float(meta.group(1)) if meta else None, "meta_reference": meta.group(2) if meta else None, "error": None}
    if meta:
        return {"source": TE_URL, "status": "확인됨", "reference": meta.group(2), "value": float(meta.group(1)), "error": None}
    return {"source": TE_URL, "status": "확인 불가", "reference": "확인 불가", "value": None, "error": "pattern not found"}


def real_yield_note(fred: dict, te: dict) -> str:
    if fred.get("value") is None or te.get("value") is None:
        return "FRED DFII10 또는 Trading Economics 10Y TIPS 중 하나가 확인되지 않아 할인율 교차확인 불완전"
    mismatch = abs(float(fred["value"]) - float(te["value"])) >= 0.03 or str(fred.get("reference")) != str(te.get("reference"))
    state = "지연/불일치 있음" if mismatch else "교차확인됨"
    return f"{state}: FRED DFII10 {fred['value']:.2f}%({fred.get('reference')}), Trading Economics 10Y TIPS {te['value']:.2f}%({te.get('reference')})"


def related(alert: dict, fred: dict, te: dict) -> str:
    out = []
    if "반도체/AI" in alert["sectors"]:
        out += ["NVDA", "MU", "AVGO", "AMD", "TSM", "ASML", "SOX"]
    if "데이터센터/전력망/전력기기" in alert["sectors"]:
        out += ["VRT", "ETN", "GEV", "CEG", "SMH"]
    if "방산/정유/해운/지정학" in alert["sectors"]:
        out += ["WTI", "Brent", "XLE", "운임"]
    if "할인율" in alert["impacts"]:
        out += [f"DFII10 {fred.get('value') if fred.get('value') is not None else '확인 불가'}", f"TE 10Y TIPS {te.get('value') if te.get('value') is not None else '확인 불가'}", "IWM/SPY 재확인"]
    return ", ".join(dict.fromkeys(out)) or "확인 가능한 직접 티커 없음"


def render_alert(alert: dict, idx: int, now: dt.datetime, fred: dict, te: dict) -> str:
    return "\n".join([
        f"## {idx}. [{alert['importance']} | {alert['status']}]",
        f"- `뉴스`: {alert['news']}",
        f"- `한국장 기준`: {alert['korea_basis']}",
        f"- `타임라인`: 최초 빌드업: 확인 불가 / 공식·원천 시각: {alert['published']} / 한국 투자자 확산: {now:%Y-%m-%d %H:%M KST} 조회 기준",
        f"- `출처`: [{alert['publisher']}]({alert['link']}) · 조회 {now:%Y-%m-%d %H:%M KST}",
        f"- `의사결정 영향`: {', '.join(alert['impacts'])}",
        f"- `영향 경로`: {', '.join(alert['paths'])}",
        f"- `영향 섹터`: {', '.join(alert['sectors'])}",
        f"- `관련 해외 티커/지표`: {related(alert, fred, te)}",
        f"- `반영 가능성`: {alert['reflection']}",
        f"- `반대 근거`: {alert['counter']}",
        f"- `해석`: {alert['interpretation']}",
        f"- `실패 신호`: {alert['failed_signal']}",
        "",
    ])


def render_report(alerts: list[dict], notes: list[str], fred: dict, te: dict, now: dt.datetime) -> str:
    title = f"📰 GAMEJOA 장전 핵심 뉴스 레이더 · {now:%Y년 %m월 %d일} · 06:30"
    lines = [
        title, "",
        f"조회 기준: {now:%Y-%m-%d %H:%M KST}. GitHub Actions 외부 러너 기준이며, 로컬 Codex/PC 절전 상태와 무관하게 실행됩니다.", "",
        "### 자료 처리 현황표",
        "| 항목 | 조회 시각 | 직접 확인 | 상태 |", "|---|---:|---:|---|",
        f"| 장전 뉴스 원천 | {now:%H:%M KST} | {sum('확인 불가' not in n for n in notes)}개 원천 | {' / '.join(notes[:5])} |",
        f"| FRED DFII10 | {now:%H:%M KST} | {'예' if fred.get('value') is not None else '아니오'} | {fred.get('status')} · {fred.get('reference')} |",
        f"| Trading Economics 10Y TIPS | {now:%H:%M KST} | {'예' if te.get('value') is not None else '아니오'} | {te.get('status')} · {te.get('reference')} |",
        "", f"할인율 교차확인: {real_yield_note(fred, te)}", "",
    ]
    if alerts:
        for idx, alert in enumerate(alerts[:7], 1):
            lines.append(render_alert(alert, idx, now, fred, te))
    else:
        lines += ["장전 고충격 뉴스 직접 확인 없음", "", "감정성 뉴스로 제외: 공식/신뢰 소스에서 돈 버는 능력, 할인율, 수급, 시간표를 명확히 바꾸는 후보가 직접 확인되지 않은 항목.", ""]
    top = alerts[0]["news"] if alerts else "장전 고충격 뉴스 직접 확인 없음"
    changed = ", ".join(alerts[0]["impacts"]) if alerts else "명확한 변화 없음"
    lines += [
        "💡 06:30 장전 뉴스 코멘트",
        f"오늘 1순위 체크는 `{top}`입니다. 오늘 가장 크게 바뀐 축은 `{changed}`이며, 한국장에서는 관련 해외 티커 반응과 국내 수급 확산 여부를 먼저 보겠습니다.",
        f"할인율은 FRED DFII10과 Trading Economics 10 Year TIPS Yield를 함께 확인했습니다: {real_yield_note(fred, te)}.",
        "06:50 투자기상도에서 수치·수급·테마와 재확인 필요.", "",
        "투자 조언이 아닌 참고용 뉴스 브리핑입니다.", "",
        "주요 출처:", *[f"- {n}" for n in notes[:18]], f"- FRED DFII10: {FRED_CSV}", f"- Trading Economics 10Y TIPS: {TE_URL}",
    ]
    return "\n".join(lines).strip() + "\n"


def send_telegram(text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("Telegram: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing")
        return
    repo, run_id = os.getenv("GITHUB_REPOSITORY", ""), os.getenv("GITHUB_RUN_ID", "")
    suffix = f"\n\n전체 보고서: https://github.com/{repo}/actions/runs/{run_id}" if repo and run_id else ""
    body = urllib.parse.urlencode({"chat_id": chat_id, "text": (text[: TELEGRAM_LIMIT - len(suffix) - 1] + suffix)[:TELEGRAM_LIMIT], "disable_web_page_preview": "true"}).encode("utf-8")
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body, method="POST")
    with urllib.request.urlopen(req, timeout=25) as resp:
        resp.read()
    print("Telegram: sent")


def print_utf8(text: str) -> None:
    try:
        sys.stdout.write(text)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(text.encode("utf-8", "replace"))


def main() -> int:
    now = kst_now()
    rows, notes = collect_items(now)
    alerts = [a for a in (classify(r, now) for r in rows if fresh(r, now)) if a]
    alerts.sort(key=lambda a: (-a["score"], a["published"]))
    deduped, seen = [], set()
    for alert in alerts:
        key = (norm(alert["news"]), norm(alert["publisher"]), alert["published"][:10])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(alert)
        if len(deduped) >= 7:
            break
    fred, te = collect_dfii10(), collect_te()
    report = render_report(deduped, notes, fred, te, now)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "gamejoa_preopen_news_radar.md").write_text(report, encoding="utf-8")
    (OUT / "gamejoa_preopen_news_radar_title.txt").write_text(report.splitlines()[0] + "\n", encoding="utf-8")
    (OUT / "gamejoa_preopen_news_radar.json").write_text(json.dumps({"query_time_kst": now.isoformat(timespec="seconds"), "alerts": deduped, "source_notes": notes, "fred_dfii10": fred, "tradingeconomics_tips": te}, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print_utf8(report)
    if os.getenv("TELEGRAM_DRY_RUN", "").lower() in {"1", "true", "yes", "y"}:
        print("Telegram: dry run")
        return 0
    if os.getenv("SEND_TELEGRAM", "").lower() in {"1", "true", "yes", "y"}:
        send_telegram(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
