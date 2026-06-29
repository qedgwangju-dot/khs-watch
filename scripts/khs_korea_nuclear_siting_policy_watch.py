#!/usr/bin/env python3
"""KHS domestic nuclear siting and licensing policy watch."""

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
ALERTS_JSON_PATH = OUT_DIR / "khs_policy_watch_alerts.json"
SEEN_PATH = DATA_DIR / "khs_korea_nuclear_siting_policy_seen.json"
KST = ZoneInfo("Asia/Seoul")
MAX_AGE_HOURS = int(os.getenv("KHS_SOURCE_MAX_AGE_HOURS", "72"))
MAX_ALERTS = int(os.getenv("KHS_KOREA_NUCLEAR_SITING_MAX_ALERTS", "3"))
UA = os.getenv("SEC_USER_AGENT", "KHS-korea-nuclear-siting-policy-watch contact=github-actions")

SOURCES = [
    ("Korea nuclear siting policy news", "https://news.google.com/rss/search?q=" + urllib.parse.quote('"신규 원전" 입지 SMR 표준설계인가 2028 2029 2037 2038 연합뉴스') + "&hl=ko&gl=KR&ceid=KR:ko"),
    ("Korea SMR licensing policy news", "https://news.google.com/rss/search?q=" + urllib.parse.quote('SMR 표준설계인가 2028 방폐장 송전망 안전성 검증 주민 수용성') + "&hl=ko&gl=KR&ceid=KR:ko"),
    ("Korea large nuclear licensing news", "https://news.google.com/rss/search?q=" + urllib.parse.quote('"대형 원전" 인허가 2029 완공 2037 2038 방폐장 송전망') + "&hl=ko&gl=KR&ceid=KR:ko"),
]
TRUSTED_PUBLISHERS = ["연합뉴스", "yna", "정책브리핑", "korea.kr", "산업통상자원부", "motie", "motir", "원자력안전위원회", "nssc", "한국수력원자력", "khnp", "한국경제", "매일경제", "서울경제"]
NUCLEAR_TERMS = ["원전", "원자력", "신규 원전", "대형 원전", "smr", "SMR", "소형모듈원전", "혁신형 smr", "혁신형 SMR", "i-smr", "i-SMR"]
TIMELINE_TERMS = ["입지", "후보지", "부지", "표준설계인가", "표준설계", "설계인가", "2028", "인허가", "건설허가", "운영허가", "2029", "2037", "2038", "완공", "상업운전"]
RISK_TERMS = ["방폐장", "방사성폐기물", "고준위", "사용후핵연료", "송전망", "계통", "안전성 검증", "안전성", "주민 수용성", "주민수용성", "주민", "환경영향평가"]
SECTORS = ["국내 원전/SMR", "원전 기자재/전력기기", "송전망/전선", "두산에너빌리티/KHNP"]
CHECK = "SMR 2028년 표준설계인가, 대형 원전 2029년 인허가, 2037~2038년 완공 목표, 입지 선정 후속 일정, 방폐장·송전망·안전성 검증·주민 수용성 확인"
RISK_TABLE = "당장 수주 확정 아님: 입지 선정으로 밸류체인 기대가 살아나는 단계 / 방폐장·송전망: 인허가와 주민 수용성 병목 / 안전성 검증: 표준설계인가·건설허가 지연 시 모멘텀 약화 / 테마 과열: 실제 계약·공시·착공 전까지 매출 인식 시차 큼"
STRUCTURE_NOTE = "이번 이슈는 확정 수주보다 입지 선정으로 원전 밸류체인이 다시 살아났는지를 보는 단계입니다. 짧게는 테마 과열, 길게는 실제 인허가와 주민 수용성이 따라오는지 끝까지 확인해야 합니다."
COUNTER = "SMR은 2028년 표준설계인가 일정이 남아 있고 대형 원전도 2029년까지 인허가, 완공 목표는 2037~2038년으로 장기입니다. 방폐장·송전망·안전성 검증이 지연되면 입지 선정 뉴스만으로 실제 수주나 매출을 확정하기 어렵습니다."


def now_kst() -> dt.datetime:
    return dt.datetime.now(tz=KST)


def clean_text(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_text(url: str, timeout: int = 10) -> tuple[str | None, str | None]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace"), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def parse_date(value: object) -> dt.datetime | None:
    raw = clean_text(value)
    if not raw:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(raw)
        return parsed.astimezone(KST) if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc).astimezone(KST)
    except (TypeError, ValueError):
        return None


def age_hours(published: dt.datetime | None, now: dt.datetime) -> float | None:
    if not published:
        return None
    return (now - published).total_seconds() / 3600


def has_any(text: str, terms: list[str]) -> bool:
    lower = text.lower()
    return any(term.lower() in lower for term in terms)


def matched_terms(text: str, terms: list[str]) -> list[str]:
    lower = text.lower()
    return [term for term in terms if term.lower() in lower]


def trusted_source(publisher: str, text: str) -> bool:
    return has_any(f"{publisher} {text}", TRUSTED_PUBLISHERS)


def is_candidate(text: str) -> bool:
    return has_any(text, NUCLEAR_TERMS) and has_any(text, TIMELINE_TERMS) and has_any(text, RISK_TERMS)


def build_alert(source: str, title: str, link: str, summary: str, published: dt.datetime | None, matched: list[str], status: str) -> dict:
    fingerprint = hashlib.sha256(f"korea-nuclear-siting|{title}|{link}".encode("utf-8")).hexdigest()[:16]
    return {
        "source": source,
        "title": "국내 원전 정책: 입지 선정·SMR 표준설계·대형원전 인허가 체크",
        "original_title": title,
        "link": link,
        "summary": summary[:900],
        "published_kst": published.isoformat(timespec="seconds") if published else "",
        "fingerprint": fingerprint,
        "matched": {"korea_nuclear_siting_policy": matched[:14] or ["국내 원전 입지/인허가"]},
        "importance": "상",
        "status": status,
        "impacts": ["시간표", "수급", "할인율"],
        "paths": ["정책 타임라인", "밸류체인", "수급", "인허가 리스크"],
        "sectors": SECTORS[:],
        "korea_nuclear_siting_policy_watch": True,
        "domestic_nuclear_siting_check": CHECK,
        "domestic_nuclear_siting_risk_table": RISK_TABLE,
        "domestic_nuclear_siting_structure_note": STRUCTURE_NOTE,
        "counter": COUNTER,
        "reflection": "중간",
    }


def parse_rss(text: str, source_name: str, now: dt.datetime) -> list[dict]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    alerts: list[dict] = []
    for item in root.findall(".//item"):
        title = clean_text(item.findtext("title"))
        summary = clean_text(item.findtext("description"))
        link = clean_text(item.findtext("link"))
        published = parse_date(item.findtext("pubDate"))
        source_node = item.find("source")
        publisher = clean_text(source_node.text if source_node is not None else source_name)
        haystack = f"{title} {summary} {publisher} {source_name}"
        if not trusted_source(publisher, haystack) or not is_candidate(haystack):
            continue
        age = age_hours(published, now)
        if age is None or age < -1 or age > MAX_AGE_HOURS:
            continue
        hits = matched_terms(haystack, NUCLEAR_TERMS + TIMELINE_TERMS + RISK_TERMS)
        status = "확정" if has_any(haystack, ["정책브리핑", "korea.kr", "산업통상자원부", "motie", "motir", "원자력안전위원회", "nssc"]) else "예비"
        alerts.append(build_alert(publisher or source_name, title, link, summary, published, hits, status))
    return alerts


def load_seen() -> dict:
    if not SEEN_PATH.exists():
        return {"seen": {}, "updated_at_kst": ""}
    try:
        return json.loads(SEEN_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"seen": {}, "updated_at_kst": ""}


def save_seen(seen: dict, now: dt.datetime) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    seen["updated_at_kst"] = now.isoformat(timespec="seconds")
    SEEN_PATH.write_text(json.dumps(seen, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_existing_alerts() -> list[dict]:
    if not ALERTS_JSON_PATH.exists():
        return []
    try:
        data = json.loads(ALERTS_JSON_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def write_alerts(alerts: list[dict]) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    ALERTS_JSON_PATH.write_text(json.dumps(alerts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    now = now_kst()
    candidates: list[dict] = []
    for source_name, source_url in SOURCES:
        text, error = fetch_text(source_url)
        if error:
            print(f"korea_nuclear_siting_source_failed source={source_name} error={error}")
            continue
        candidates.extend(parse_rss(text or "", source_name, now))
    seen = load_seen()
    seen_map = seen.setdefault("seen", {})
    new_alerts: list[dict] = []
    for item in candidates:
        fp = item["fingerprint"]
        if fp in seen_map:
            continue
        new_alerts.append(item)
        seen_map[fp] = {"title": item.get("original_title") or item.get("title"), "source": item.get("source"), "link": item.get("link"), "first_seen_kst": now.isoformat(timespec="seconds"), "importance": item.get("importance"), "status": item.get("status")}
        if len(new_alerts) >= MAX_ALERTS:
            break
    if not new_alerts:
        print(f"korea_nuclear_siting_alerts=0 candidates={len(candidates)}")
        return 0
    existing = load_existing_alerts()
    existing_keys = {str(item.get("fingerprint") or item.get("link") or "") for item in existing}
    merged = existing[:]
    for item in new_alerts:
        key = str(item.get("fingerprint") or item.get("link") or "")
        if key not in existing_keys:
            merged.append(item)
            existing_keys.add(key)
    write_alerts(merged)
    save_seen(seen, now)
    print(f"korea_nuclear_siting_alerts={len(new_alerts)} candidates={len(candidates)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
