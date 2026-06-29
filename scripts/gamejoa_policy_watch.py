#!/usr/bin/env python3
"""GAMEJOA real-time policy/regulatory watch.

Runs on a short schedule, writes a report every run, and writes alert artifacts
only when unseen high-impact policy/regulatory items are found.
"""

from __future__ import annotations

import datetime as dt
import email.utils
import hashlib
import html
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "out"
DATA_DIR = ROOT / "data"
SEEN_PATH = DATA_DIR / "gamejoa_policy_watch_seen.json"
KST = ZoneInfo("Asia/Seoul")
UA = os.getenv("SEC_USER_AGENT", "GAMEJOA-policy-watch contact=please-set-repo-variable")
MAX_AGE_HOURS = int(os.getenv("GAMEJOA_WATCH_MAX_AGE_HOURS", "72"))
MAX_ALERTS = int(os.getenv("GAMEJOA_WATCH_MAX_ALERTS", "5"))

SOURCES = [
    ("FERC news", "https://www.ferc.gov/news-events/news/rss.xml", "rss"),
    ("DOE news", "https://www.energy.gov/rss.xml", "rss"),
    ("Commerce news", "https://www.commerce.gov/news/rss.xml", "rss"),
    ("BIS news", "https://www.bis.doc.gov/index.php/newsroom/news-releases?format=feed&type=rss", "rss"),
    ("SEC press", "https://www.sec.gov/news/pressreleases.rss", "rss"),
    ("FTC press", "https://www.ftc.gov/news-events/news/press-releases/rss.xml", "rss"),
    ("Federal Register tariffs", "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bterm%5D=tariff%20section%20301%20final%20rule&order=newest&per_page=15", "fr"),
    ("Federal Register export controls", "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bterm%5D=semiconductor%20export%20controls%20entity%20list&order=newest&per_page=15", "fr"),
    ("Federal Register energy/grid", "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bterm%5D=energy%20grid%20permit%20final%20rule%20data%20center&order=newest&per_page=15", "fr"),
    ("Federal Register FDA material", "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bagencies%5D%5B%5D=food-and-drug-administration&conditions%5Bterm%5D=BLA%20NDA%20PDUFA%20advisory%20committee%20complete%20response%20letter%20clinical%20hold&order=newest&per_page=15", "fr"),
]

STAGE_KEYWORDS = {
    "final_rule": ["final rule", "effective date", "implementation", "interim final rule", "최종 규칙", "시행일"],
    "permit_restart": ["permit", "permitting", "authorization", "license", "record of decision", "environmental impact statement", "approval", "허가", "승인"],
    "sanctions_tariffs_export": ["sanctions", "tariff", "section 301", "export controls", "entity list", "ofac", "bis", "관세", "제재", "수출통제"],
    "agency_order": ["order", "directive", "notice of proposed rulemaking", "nopr", "request for comments", "hearing", "comment deadline", "명령", "의견수렴", "청문"],
    "fda_decision": ["fda approves", "fda approval", "complete response letter", "crl", "pdufa", "biologics license application", "new drug application", "advisory committee", "clinical hold", "rejection", "거절"],
}

SECTOR_KEYWORDS = {
    "전력망/데이터센터": ["ferc", "grid", "transmission", "large load", "data center", "power", "interconnection"],
    "원전/전력기기": ["nuclear", "reactor", "uranium", "transformer"],
    "반도체/AI": ["semiconductor", "chips", "bis", "export controls", "nvidia", "hbm", "ai", "entity list"],
    "2차전지/핵심광물": ["battery", "lithium", "critical minerals", "ira", "ev"],
    "방산/지정학": ["sanctions", "missile", "defense", "iran", "russia", "china", "taiwan"],
    "바이오/FDA": ["fda", "clinical", "drug", "crl", "pdufa", "bla", "nda"],
    "관세/수출주": ["tariff", "section 301", "ustr", "customs"],
}

FDA_MATERIAL_TERMS = [
    "fda approves", "fda approval", "complete response letter", "crl", "pdufa",
    "biologics license application", "new drug application", "advisory committee",
    "clinical hold", "priority review", "accelerated approval", "approval letter",
    "phase 3", "bla", "nda", "임상 3상", "허가",
]
FDA_LOW_IMPACT_ADMIN_TERMS = [
    "tobacco", "establishment registration", "product listing", "medical devices",
    "orthopedic devices", "classification of", "patent extension",
    "regulatory review period", "device classification", "food additive",
    "color additive", "medial knee implanted shock absorber", "vyalev",
]


def now_kst() -> dt.datetime:
    return dt.datetime.now(tz=KST)


def clean(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<!\[CDATA\[|\]\]>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_text(url: str, timeout: int = 25) -> tuple[str | None, str | None]:
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


def parse_rss(text: str, source: str) -> list[dict]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    rows = []
    for node in root.findall(".//item")[:25]:
        rows.append({
            "source": source,
            "publisher": clean(node.findtext("source")) or source,
            "title": clean(node.findtext("title")),
            "link": clean(node.findtext("link")),
            "summary": clean(node.findtext("description")),
            "published_kst": (parse_date(node.findtext("pubDate") or node.findtext("date")) or now_kst()).isoformat(timespec="seconds"),
        })
    return rows


def parse_fr(text: str, source: str) -> list[dict]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    rows = []
    for row in (data.get("results") or [])[:15]:
        published = parse_date(row.get("publication_date") or row.get("signing_date")) or now_kst()
        rows.append({
            "source": source,
            "publisher": "Federal Register",
            "title": clean(row.get("title") or row.get("citation")),
            "link": clean(row.get("html_url") or row.get("pdf_url")),
            "summary": clean(" ".join(str(row.get(k, "")) for k in ("type", "document_number", "abstract", "excerpt"))),
            "published_kst": published.isoformat(timespec="seconds"),
        })
    return rows


def item_age_hours(item: dict, now: dt.datetime) -> float | None:
    try:
        published = dt.datetime.fromisoformat(item.get("published_kst") or "")
    except ValueError:
        return None
    return (now - published).total_seconds() / 3600


def has_term(haystack: str, terms: list[str]) -> bool:
    return any(term.lower() in haystack for term in terms)


def korean_alert_title(alert: dict) -> str:
    title = (alert.get("title") or "").lower()
    sectors = alert.get("sectors") or []
    if "바이오/FDA" in sectors:
        if has_term(title, ["complete response letter", "crl"]):
            return "FDA CRL/거절: 바이오 승인 지연 리스크"
        if "clinical hold" in title:
            return "FDA 임상보류: 개발 시간표 지연 리스크"
        if has_term(title, ["advisory committee", "biologics license application", "bla"]):
            return "FDA 자문위/BLA 일정: 바이오 심사 시간표 체크"
        if has_term(title, ["fda approves", "fda approval", "approval letter", "accelerated approval"]):
            return "FDA 승인/허가: 바이오 매출 전환 가능성 체크"
        if has_term(title, ["pdufa", "priority review", "nda", "new drug application"]):
            return "FDA 심사 일정: PDUFA/NDA 승인 시간표 체크"
        return "FDA 바이오 규제 일정: 매출·승인 시간표 체크"
    return alert.get("title") or "제목 확인 불가"


def classify_item(item: dict) -> dict | None:
    haystack = f"{item.get('title', '')} {item.get('summary', '')} {item.get('source', '')}".lower()
    matched = {bucket: [kw for kw in keywords if kw.lower() in haystack] for bucket, keywords in STAGE_KEYWORDS.items()}
    matched = {bucket: kws for bucket, kws in matched.items() if kws}
    if not matched:
        return None

    sectors = [sector for sector, keywords in SECTOR_KEYWORDS.items() if any(kw.lower() in haystack for kw in keywords)] or ["정책/규제 일반"]
    if "바이오/FDA" in sectors:
        if has_term(haystack, FDA_LOW_IMPACT_ADMIN_TERMS) or not has_term(haystack, FDA_MATERIAL_TERMS):
            return None

    impacts, paths = [], []
    if any(bucket in matched for bucket in ("final_rule", "permit_restart", "agency_order")):
        impacts += ["시간표", "할인율"]
        paths += ["정책 타임라인", "할인율"]
    if any(bucket in matched for bucket in ("sanctions_tariffs_export", "fda_decision")):
        impacts += ["돈 버는 능력", "수급"]
        paths += ["이익", "수급"]
    impacts = list(dict.fromkeys(impacts)) or ["의사결정 영향 제한적"]
    paths = list(dict.fromkeys(paths)) or ["정책 타임라인"]

    stage_score = sum(len(v) for v in matched.values())
    if any(bucket in matched for bucket in ("final_rule", "sanctions_tariffs_export", "fda_decision")):
        importance = "상"
    elif stage_score >= 3:
        importance = "중"
    else:
        importance = "하"

    fingerprint = hashlib.sha256(f"{item.get('source')}|{item.get('title')}|{item.get('link')}".encode("utf-8")).hexdigest()[:16]
    return {
        **item,
        "fingerprint": fingerprint,
        "matched": matched,
        "importance": importance,
        "status": "확정" if item.get("publisher") == "Federal Register" or "news" in item.get("source", "").lower() else "예비",
        "impacts": impacts,
        "paths": paths,
        "sectors": sectors,
    }


def load_seen() -> dict:
    if not SEEN_PATH.exists():
        return {"seen": {}, "updated_at_kst": ""}
    try:
        return json.loads(SEEN_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"seen": {}, "updated_at_kst": ""}


def save_seen(seen: dict) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    seen["updated_at_kst"] = now_kst().isoformat(timespec="seconds")
    SEEN_PATH.write_text(json.dumps(seen, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def collect_candidates(now: dt.datetime) -> tuple[list[dict], list[str]]:
    candidates, notes = [], []
    for source, url, kind in SOURCES:
        text, error = fetch_text(url)
        if error:
            notes.append(f"- {source}: 확인 불가 ({error})")
            continue
        items = parse_fr(text or "", source) if kind == "fr" else parse_rss(text or "", source)
        notes.append(f"- {source}: {len(items)}건 확인")
        for item in items:
            age = item_age_hours(item, now)
            if age is not None and age > MAX_AGE_HOURS:
                continue
            classified = classify_item(item)
            if classified:
                classified["age_hours"] = age
                candidates.append(classified)
    return candidates, notes


def render_report(alerts: list[dict], source_notes: list[str], now: dt.datetime) -> str:
    title = f"🚨 GAMEJOA 정책·규제 고충격 워치 · {now:%Y년 %m월 %d일 %H:%M KST}"
    lines = [title, ""]
    if not alerts:
        lines += [
            "고충격 정책·규제 변경 직접 확인 없음", "", "확인 범위:", *source_notes[:24], "",
            "💡 워치 판단: 이번 실행에서 돈 버는 능력, 할인율, 수급, 시간표를 새로 바꾼 확정 이벤트는 직접 확인되지 않았습니다.", "",
            "투자 조언이 아닌 참고용 정책·규제 알림입니다.",
        ]
        return "\n".join(lines) + "\n"

    for idx, alert in enumerate(alerts, 1):
        matched_terms = sorted({term for terms in alert["matched"].values() for term in terms})
        display_title = korean_alert_title(alert)
        lines += [
            f"## {idx}. [{alert['importance']}·{alert['status']}] {display_title}",
            f"- 상태 변화: {', '.join(alert['matched'].keys())} 신호 확인 ({', '.join(matched_terms[:8])})",
            f"- 원문/출처: [{alert['source']}]({alert['link']}) · 원천시각 {alert.get('published_kst') or '확인 불가'} · 조회 {now:%H:%M KST}",
            f"- 한국장 영향: {', '.join(alert['impacts'])}",
            f"- 영향 경로: {', '.join(alert['paths'])}",
            f"- 영향 섹터: {', '.join(alert['sectors'])}",
            "- 반영 가능성: 낮음~중간. 공식 원문/신뢰 소스 확인 후 한국장 확산 여부를 06:30 레이더에서 재확인해야 합니다.",
            "- 반대 근거: 제목·요약 기반 1차 감시라 원문 세부 조건, 시행일, 예외 조항, 개별 프로젝트 적용 여부 확인이 필요합니다.",
            "- 즉시 체크: 원문 전문, 시행일/마감일, 한국 밸류체인 노출, 관련 해외 티커·ETF 반응", "",
        ]
    lines += [
        "💡 워치 판단: 이번 실행은 시간표·할인율을 바꿀 수 있는 정책/규제 상태 변화 후보를 우선 감지했습니다. 06:30 레이더에서 원문 전문과 시장 반응을 재확인해야 합니다.", "",
        "투자 조언이 아닌 참고용 정책·규제 알림입니다.",
    ]
    return "\n".join(lines) + "\n"


def write_outputs(alerts: list[dict], source_notes: list[str], now: dt.datetime) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    report = render_report(alerts, source_notes, now)
    (OUT_DIR / "gamejoa_policy_watch.md").write_text(report, encoding="utf-8")
    if alerts:
        top = alerts[0]
        title = f"GAMEJOA 정책 워치: [{top['importance']}] {korean_alert_title(top)[:70]}"
        (OUT_DIR / "gamejoa_policy_watch_alert_title.txt").write_text(title + "\n", encoding="utf-8")
        (OUT_DIR / "gamejoa_policy_watch_alert.md").write_text(report, encoding="utf-8")
        (OUT_DIR / "gamejoa_policy_watch_alerts.json").write_text(json.dumps(alerts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    now = now_kst()
    seen = load_seen()
    seen_map = seen.setdefault("seen", {})
    candidates, source_notes = collect_candidates(now)
    new_alerts = []
    for item in sorted(candidates, key=lambda x: (x["importance"] != "상", x.get("age_hours") or 999)):
        if item["fingerprint"] in seen_map:
            continue
        new_alerts.append(item)
        seen_map[item["fingerprint"]] = {"title": item["title"], "source": item["source"], "seen_at_kst": now.isoformat(timespec="seconds")}
        if len(new_alerts) >= MAX_ALERTS:
            break
    save_seen(seen)
    write_outputs(new_alerts, source_notes, now)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
