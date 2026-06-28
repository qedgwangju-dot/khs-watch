#!/usr/bin/env python3
"""Contract overlay for the compact preopen news radar.

This keeps the Telegram-only report renderer, while enforcing the broader
source and classification contract requested for the 06:30 radar.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import os
import urllib.parse
import urllib.request

import gamejoa_preopen_news_radar_telegram_runner as telegram


base = telegram.base
strict = telegram.strict

DART_KEYWORDS = [
    "단일판매", "공급계약", "수주", "유상증자", "전환사채", "신주인수권",
    "자기주식", "타법인주식", "회사합병", "회사분할", "주요사항보고서",
    "투자판단", "최대주주", "소송",
]


def append_unique(seq: list, values: list) -> None:
    for value in values:
        if value not in seq:
            seq.append(value)


append_unique(base.SOURCES, [
    ("Commerce", "https://www.commerce.gov/news/rss.xml", "official"),
    ("BIS", "https://www.bis.doc.gov/index.php/newsroom/news-releases?format=feed&type=rss", "official"),
    ("FTC", "https://www.ftc.gov/news-events/news/press-releases/rss.xml", "official"),
    ("Federal Register USTR", "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bagencies%5D%5B%5D=trade-representative-office-of-united-states&order=newest&per_page=15", "fr"),
    ("Federal Register sanctions", "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bterm%5D=OFAC%20sanctions%20export%20controls&order=newest&per_page=15", "fr"),
    ("Federal Register FDA", "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bagencies%5D%5B%5D=food-and-drug-administration&order=newest&per_page=15", "fr"),
    ("Federal Register FTC", "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bagencies%5D%5B%5D=federal-trade-commission&order=newest&per_page=15", "fr"),
])

append_unique(base.QUERIES, [
    ("반도체/AI", "Nvidia Micron Broadcom AMD Intel TSMC ASML ARM Apple Microsoft Oracle AI chip HBM data center server network cooling guidance supply agreement Reuters Bloomberg MarketWatch"),
    ("정책/규제", "USTR FTC SEC DOE FERC Commerce BIS OFAC CHIPS Act IRA tariff sanctions export controls Reuters Bloomberg AP"),
    ("기업 이벤트", "MOU LOI contract supply agreement joint venture capex buyback offering convertible bond guidance Reuters Bloomberg MarketWatch Korea"),
    ("원자재/매크로", "oil natural gas copper lithium uranium gold dollar won treasury yield Fed real yield TIPS Reuters Bloomberg CNBC MarketWatch"),
])

append_unique(base.TRUSTED, ["opendart", "open dart", "news herald", "dispatch", "local news"])
append_unique(base.TERMS, [
    "broadcom", "intel", "arm", "apple", "microsoft", "oracle", "server", "network", "cooling",
    "buyback", "convertible", "joint venture", "loi", "mou", "offering",
    "copper", "dollar", "fed", "gold", "lithium", "natural gas", "oil", "real yield",
    "tips", "treasury", "uranium", "won", "yield",
    *DART_KEYWORDS,
])

for idx, (label, keys) in enumerate(base.SECTORS):
    if label == "반도체/AI":
        merged = list(keys)
        append_unique(merged, ["broadcom", "amd", "intel", "arm", "apple", "microsoft", "oracle"])
        base.SECTORS[idx] = (label, merged)
    if label == "데이터센터/전력망/전력기기":
        merged = list(keys)
        append_unique(merged, ["server", "network", "cooling"])
        base.SECTORS[idx] = (label, merged)
    if label == "한국 직접 영향":
        merged = list(keys)
        append_unique(merged, DART_KEYWORDS)
        base.SECTORS[idx] = (label, merged)

if not any(label == "원자재/매크로" for label, _ in base.SECTORS):
    base.SECTORS.append((
        "원자재/매크로",
        ["oil", "natural gas", "copper", "lithium", "uranium", "gold", "dollar", "won", "treasury", "yield", "fed", "real yield", "tips"],
    ))


def fetch_fred_csv(timeout: int = 60) -> tuple[str | None, str | None]:
    req = urllib.request.Request(base.FRED_CSV, headers={"User-Agent": "Mozilla/5.0", "Accept": "text/csv,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace"), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def collect_dfii10() -> dict:
    if getattr(base, "FRED_API_KEY", ""):
        url = "https://api.stlouisfed.org/fred/series/observations?" + urllib.parse.urlencode({
            "series_id": "DFII10", "file_type": "json", "sort_order": "desc", "limit": "10", "api_key": base.FRED_API_KEY,
        })
        text, err = base.fetch(url, 30)
        if not err and text:
            for row in json.loads(text).get("observations", []):
                if row.get("value") and row.get("value") != ".":
                    return {"source": "FRED API DFII10", "status": "확인됨", "reference": row.get("date"), "value": float(row.get("value")), "error": None}
    text, err = fetch_fred_csv(60)
    if err or not text:
        return {"source": base.FRED_CSV, "status": "확인 불가", "reference": "확인 불가", "value": None, "error": err}
    for row in reversed(list(csv.DictReader(text.splitlines()))):
        if row.get("DFII10") and row.get("DFII10") != ".":
            return {"source": base.FRED_CSV, "status": "확인됨", "reference": row.get("observation_date"), "value": float(row.get("DFII10")), "error": None}
    return {"source": base.FRED_CSV, "status": "확인 불가", "reference": "확인 불가", "value": None, "error": "latest non-empty row not found"}


def collect_dart(now) -> tuple[list[dict], str]:
    dart_api_key = os.getenv("DART_API_KEY", "").strip()
    if not dart_api_key:
        return [], "OpenDART: 접근 제한 (DART_API_KEY 미설정)"
    days_back = max(1, int(os.getenv("DART_DAYS_BACK", "3")))
    watch_codes = {code.strip() for code in os.getenv("DART_WATCH_STOCK_CODES", "").split(",") if code.strip()}
    start = (now.date() - dt.timedelta(days=days_back)).strftime("%Y%m%d")
    end = now.date().strftime("%Y%m%d")
    url = "https://opendart.fss.or.kr/api/list.json?" + urllib.parse.urlencode({
        "crtfc_key": dart_api_key, "bgn_de": start, "end_de": end, "last_reprt_at": "N",
        "page_no": "1", "page_count": "100", "sort": "date", "sort_mth": "desc",
    })
    text, err = base.fetch(url, 30)
    if err:
        return [], f"OpenDART: 확인 불가 ({err})"
    try:
        data = json.loads(text or "")
    except json.JSONDecodeError:
        return [], "OpenDART: 확인 불가 (JSON 파싱 실패)"
    if str(data.get("status")) != "000":
        return [], f"OpenDART: 확인 불가/status {data.get('status')} ({data.get('message')})"

    rows = []
    for item in data.get("list", []):
        stock_code = base.clean(item.get("stock_code"))
        if watch_codes and stock_code not in watch_codes:
            continue
        report = base.clean(item.get("report_nm"))
        if not any(keyword in report for keyword in DART_KEYWORDS):
            continue
        receipt = base.clean(item.get("rcept_no"))
        rows.append({
            "source": "OpenDART",
            "layer": "official",
            "publisher": "OpenDART",
            "title": f"{base.clean(item.get('corp_name'))} {report}",
            "link": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}" if receipt else "https://dart.fss.or.kr/",
            "summary": f"stock_code={stock_code or 'N/A'} receipt={receipt or 'N/A'}",
            "published": base.parse_date(base.clean(item.get("rcept_dt"))),
        })
    return rows, f"OpenDART: {len(data.get('list', []))}건 조회, {len(rows)}건 후보"


original_collect_items = strict.collect_items


def collect_items(now):
    rows, notes = original_collect_items(now)
    dart_rows, dart_note = collect_dart(now)
    notes.append(dart_note)
    rows.extend(dart_rows)
    return rows, notes


def classify(row: dict, now):
    title = base.clean(row.get("title"))
    if len(title) < 8:
        return None
    text = base.norm(f"{title} {row.get('summary')} {row.get('publisher')} {row.get('source')}")
    local_dc_policy = strict.is_local_dc_policy(row)
    matched = [t for t in base.TERMS if base.has(text, t)]
    sectors = [label for label, keys in base.SECTORS if any(base.has(text, k) for k in keys)]
    if not matched or not sectors:
        return None

    impacts = []
    if any(t in matched for t in ["contract", "earnings", "guidance", "approval", "supply agreement", "fda", "capex", "oil", "natural gas", "copper", "lithium", "uranium", "단일판매", "공급계약", "수주", "투자판단"]):
        impacts.append("돈 버는 능력")
    if any(t in matched for t in ["ban", "banned", "banning", "block", "blocked", "city council", "dollar", "fed", "gold", "moratorium", "ordinance", "real yield", "regulation", "tariff", "tips", "treasury", "won", "yield", "zoning"]):
        impacts.append("할인율")
    if any(t in matched for t in ["buyback", "convertible", "entity list", "export control", "offering", "sanction", "supply", "유상증자", "전환사채", "신주인수권", "자기주식", "최대주주"]):
        impacts.append("수급")
    if any(t in matched for t in ["city council", "court order", "final rule", "injunction", "joint venture", "loi", "merger", "mou", "permit", "planning commission", "public hearing", "residents", "township", "vote", "타법인주식", "회사합병", "회사분할", "주요사항보고서", "소송"]):
        impacts.append("시간표")
    impacts = list(dict.fromkeys(impacts)) or ["의사결정 영향 제한적"]

    age = base.age_hours(row, now)
    score = (
        (28 if row.get("layer") == "official" else 0)
        + (20 if base.trusted(row.get("publisher") or row.get("source")) else 0)
        + min(36, len(matched) * 6)
        + len(impacts) * 10
        + len(sectors) * 6
    )
    if age is not None and age <= 12:
        score += 14
    if "데이터센터/전력망/전력기기" in sectors and any(t in matched for t in ["ban", "banned", "banning", "block", "blocked", "moratorium", "city council", "residents", "vote", "zoning"]):
        score += 18
    if local_dc_policy:
        score += 36
    if score < 58:
        return None

    status = "확정" if row.get("layer") == "official" else "공식 확인 전"
    importance = "상" if score >= 100 else "중" if score >= 76 else "하"
    if local_dc_policy:
        interp = "미국 지역 단위 데이터센터 금지·모라토리엄·주민투표는 AI CAPEX의 승인 시간표와 전력망 접속 프리미엄을 바꾸는 조기 신호입니다."
        fail = "시의회 안건·조례·투표 일정 등 공식 후속 확인이 없거나 빅테크 CAPEX/전력기기 수주 전망이 유지되면 지역성 뉴스로 약화"
    elif "원자재/매크로" in sectors:
        interp = "원자재 가격·달러·실질금리는 한국장 이익 추정과 할인율을 동시에 흔드는 축입니다."
        fail = "유가·금리·달러·원화·원자재 가격이 동행하지 않거나 하루짜리 헤드라인에 그치면 재료 약화"
    elif "반도체/AI" in sectors:
        interp = "AI·메모리 수요 또는 공급 제한을 건드릴 수 있어 한국 반도체 대형주와 소부장 수급에 연결됩니다."
        fail = "SOX/MU/NVDA/메모리 가격이 반응하지 않거나 가이던스가 수요 둔화를 시사하면 실패"
    else:
        interp = "돈 버는 능력, 할인율, 수급, 시간표 중 하나를 바꿀 수 있는 후보입니다."
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
        "local_dc_policy": local_dc_policy,
        "reflection": "낮음" if age is not None and age <= 6 else "중간" if age is None or age <= 24 else "높음",
        "counter": "제목·요약 기반 1차 감지라 원문 세부조건과 공식 문서 확인 전 과대해석 가능" if status != "확정" else "시행일, 적용 대상, 금액, 기간, 독점성, 매출 인식 조건 확인 전 영향이 제한될 수 있음",
        "interpretation": interp,
        "failed_signal": fail,
        "korea_basis": "예고된 이벤트의 공식화" if status == "확정" else "외신 확산",
    }


base.collect_dfii10 = collect_dfii10
base.collect_dart = collect_dart
strict.collect_items = collect_items
strict.classify = classify


if __name__ == "__main__":
    raise SystemExit(telegram.main())
