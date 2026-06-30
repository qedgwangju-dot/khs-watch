#!/usr/bin/env python3
"""KHS high-impact nuclear / AI power policy watch."""

from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import os
import re
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

from khs_policy_alert_explainer import ensure_explained, explanation_lines

KST = ZoneInfo("Asia/Seoul")
OUT_DIR = Path("out")
DATA_DIR = Path("data")
SEEN_PATH = DATA_DIR / "khs_nuclear_policy_seen.json"
ALERT_PATH = OUT_DIR / "khs_nuclear_policy_alert.md"
TITLE_PATH = OUT_DIR / "khs_nuclear_policy_title.txt"
ALERTS_JSON_PATH = OUT_DIR / "khs_nuclear_policy_alerts.json"
MAX_SOURCE_AGE_HOURS = int(os.getenv("KHS_NUCLEAR_MAX_AGE_HOURS", "72"))
FORMAT_VERSION = "ko-v2"

SOURCES = [
    {
        "name": "Westinghouse strategic partnership",
        "url": "https://westinghousenuclear.com/strategic-partnership/press-releases/brookfield/",
        "kind": "direct",
    },
    {
        "name": "DOE Nuclear Energy",
        "url": "https://www.energy.gov/ne/articles/9-key-takeaways-president-trumps-executive-orders-nuclear-energy",
        "kind": "direct",
    },
]

NUCLEAR_TERMS = [
    "westinghouse", "ap1000", "ap300", "nuclear reactor", "nuclear reactors",
    "new reactors", "nuclear power", "nuclear energy", "uranium", "nuclear fuel",
    "loan guarantee", "low-cost loans", "strategic partnership", "nuclear regulatory commission",
    "nrc", "data center", "data centers", "artificial intelligence", "ai race",
]
HIGH_IMPACT_TERMS = [
    "$80 billion", "80 billion", "$17.5 billion", "17.5 billion", "10 new reactors",
    "10 nuclear reactors", "at least $80 billion", "executive order", "president trump",
    "department of energy", "secretary of energy", "commerce", "u.s. government",
]

SOURCE_LABELS = {
    "Westinghouse strategic partnership": "Westinghouse 공식 전략 파트너십 발표",
    "DOE Nuclear Energy": "미국 에너지부 원전정책 공식자료",
}

TERM_LABELS = {
    "$80 billion": "최소 800억 달러 규모",
    "80 billion": "800억 달러",
    "$17.5 billion": "175억 달러",
    "17.5 billion": "175억 달러",
    "10 new reactors": "신규 원전 10기",
    "10 nuclear reactors": "원전 10기",
    "at least $80 billion": "최소 800억 달러",
    "executive order": "행정명령",
    "president trump": "트럼프 대통령",
    "department of energy": "미국 에너지부",
    "secretary of energy": "미국 에너지부 장관",
    "commerce": "상무부",
    "u.s. government": "미국 정부",
    "westinghouse": "Westinghouse",
    "ap1000": "AP1000",
    "ap300": "AP300",
    "nuclear reactor": "원자로",
    "nuclear reactors": "원자로",
    "new reactors": "신규 원전",
    "nuclear power": "원전",
    "nuclear energy": "원자력 에너지",
    "uranium": "우라늄",
    "nuclear fuel": "핵연료",
    "loan guarantee": "대출보증",
    "low-cost loans": "저리 대출",
    "strategic partnership": "전략적 파트너십",
    "nuclear regulatory commission": "미 원자력규제위원회",
    "nrc": "미 원자력규제위원회",
    "data center": "데이터센터",
    "data centers": "데이터센터",
    "artificial intelligence": "인공지능",
    "ai race": "AI 경쟁",
}


def now_kst() -> dt.datetime:
    return dt.datetime.now(tz=KST)


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = re.sub(r"<script\b.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style\b.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "KHS-nuclear-policy-watch contact=github-actions"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode(resp.headers.get_content_charset() or "utf-8", errors="replace")


def parse_date(text: str) -> dt.datetime | None:
    patterns = [
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+20\d{2}\b",
        r"\b20\d{2}-\d{2}-\d{2}\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        value = match.group(0)
        for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
            try:
                return dt.datetime.strptime(value, fmt).replace(tzinfo=KST)
            except ValueError:
                pass
    return None


def title_from_text(text: str, fallback: str) -> str:
    match = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.I | re.S)
    return clean_text(match.group(1)) if match else fallback


def collect_items(now: dt.datetime) -> list[dict]:
    items: list[dict] = []
    for source in SOURCES:
        try:
            raw = fetch_text(source["url"])
        except Exception as exc:
            print(f"nuclear_source_error={source['name']} {exc}")
            continue
        title = title_from_text(raw, source["name"])
        body = clean_text(raw)
        published = parse_date(body)
        if published:
            age_hours = (now - published).total_seconds() / 3600
            if age_hours > MAX_SOURCE_AGE_HOURS:
                continue
        haystack = f"{title} {body}".lower()
        matched = [term for term in NUCLEAR_TERMS + HIGH_IMPACT_TERMS if term.lower() in haystack]
        if not any(term in matched for term in NUCLEAR_TERMS):
            continue
        if not any(term in matched for term in HIGH_IMPACT_TERMS):
            continue
        fingerprint = hashlib.sha256(f"{FORMAT_VERSION}|{source['name']}|{title}|{source['url']}".encode("utf-8")).hexdigest()[:16]
        items.append({
            "fingerprint": fingerprint,
            "source": source["name"],
            "title": title,
            "link": source["url"],
            "published_kst": published.isoformat() if published else "확인 불가",
            "matched": sorted(set(matched))[:12],
        })
    return items


def load_seen() -> dict:
    if not SEEN_PATH.exists():
        return {"seen": {}, "updated_at_kst": ""}
    try:
        return json.loads(SEEN_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"seen": {}, "updated_at_kst": ""}


def save_seen(seen: dict, now: dt.datetime) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    seen["updated_at_kst"] = now.isoformat(timespec="seconds")
    SEEN_PATH.write_text(json.dumps(seen, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def render(alerts: list[dict], now: dt.datetime) -> str:
    lines = [f"🚨 KHS 원전/AI 전력 고충격 워치 · {now:%Y년 %m월 %d일 %H:%M KST}", ""]
    for idx, item in enumerate(alerts, 1):
        ko_title = "미국, Westinghouse AP1000 원전·AI 전력 정책 지원 신호"
        if "80" in " ".join(item["matched"]):
            ko_title = "미국, Westinghouse 원전 건설 대형 지원 신호"
        source_label = SOURCE_LABELS.get(item["source"], item["source"])
        evidence = ", ".join(dict.fromkeys(TERM_LABELS.get(term, term) for term in item["matched"]))
        explain_item = {
            **item,
            "title": ko_title,
            "summary": evidence,
            "impacts": ["시간표", "돈 버는 능력", "수급"],
            "paths": ["원전 정책 타임라인", "AI 데이터센터 전력수요", "원전 밸류체인", "우라늄/원전기기 수급"],
            "sectors": ["원전/전력기기", "전력망/데이터센터", "우라늄", "SMR/대형원전 기자재"],
        }
        ensure_explained(explain_item)
        lines.extend([
            f"## {idx}. [상·확정] {ko_title}",
            f"- 원문/출처: [{source_label}]({item['link']}) · 원천시각 {item['published_kst']} · 조회 {now:%H:%M KST}",
            f"- 확인 근거: {evidence}",
            *explanation_lines(explain_item),
            "- 즉시 체크: Westinghouse/Cameco/Brookfield 후속 공시, DOE·NRC 일정, 국내 원전기기·전력기기 수급 반응",
            "",
        ])
    lines.extend([
        "💡 워치 판단: 원전 정책은 단순 테마가 아니라 AI 전력수요와 장기 CAPEX 시간표를 함께 바꾸는 재료라 별도 송출합니다.",
        "",
        "투자 조언이 아닌 참고용 원전·AI 전력 정책 알림입니다.",
    ])
    return "\n".join(lines) + "\n"


def clear_outputs() -> None:
    for path in (ALERT_PATH, TITLE_PATH, ALERTS_JSON_PATH):
        if path.exists():
            path.unlink()


def main() -> int:
    now = now_kst()
    seen = load_seen()
    seen_map = seen.setdefault("seen", {})
    candidates = collect_items(now)
    alerts = []
    for item in candidates:
        if item["fingerprint"] in seen_map:
            continue
        alerts.append(item)
        seen_map[item["fingerprint"]] = {
            "title": item["title"],
            "source": item["source"],
            "link": item["link"],
            "first_seen_kst": now.isoformat(timespec="seconds"),
        }
    if not alerts:
        clear_outputs()
        print(f"nuclear_policy_alerts=0 candidates={len(candidates)}")
        return 0
    OUT_DIR.mkdir(exist_ok=True)
    report = render(alerts, now)
    ALERT_PATH.write_text(report, encoding="utf-8")
    ALERTS_JSON_PATH.write_text(json.dumps(alerts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    TITLE_PATH.write_text("KHS 원전/AI 전력 워치: 미국 원전 정책 고충격 신호\n", encoding="utf-8")
    save_seen(seen, now)
    print(f"nuclear_policy_alerts={len(alerts)} candidates={len(candidates)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
