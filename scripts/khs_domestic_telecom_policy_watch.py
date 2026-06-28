#!/usr/bin/env python3
"""KHS domestic telecom-fee policy watch.

This lane catches Korean official policy signals that can pressure telecom
ARPU, margins, and dividend valuation before they are folded into the daily
preopen radar.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "out"
DATA_DIR = ROOT / "data"
ALERTS_JSON_PATH = OUT_DIR / "khs_policy_watch_alerts.json"
SEEN_PATH = DATA_DIR / "khs_domestic_telecom_policy_seen.json"
KST = ZoneInfo("Asia/Seoul")
MAX_AGE_HOURS = int(os.getenv("KHS_SOURCE_MAX_AGE_HOURS", "72"))
MAX_ALERTS = int(os.getenv("KHS_DOMESTIC_TELECOM_MAX_ALERTS", "3"))
UA = os.getenv("SEC_USER_AGENT", "KHS-domestic-telecom-policy-watch contact=github-actions")

SOURCES = [
    (
        "Korea Policy Briefing telecom policy",
        "https://www.korea.kr/news/policyNewsList.do",
    ),
    (
        "Korea Policy Briefing telecom search",
        "https://www.korea.kr/news/policyNewsList.do?srchKeyword=%ED%86%B5%EC%8B%A0%EB%B9%84",
    ),
    (
        "Korea Communications Commission notices",
        "https://www.kcc.go.kr/user.do?mode=list&page=A05030000",
    ),
]

ACTOR_TERMS = [
    "과학기술정보통신부", "과기정통부", "방송통신위원회", "방통위", "정부",
    "국회", "KCC", "MSIT", "통신3사", "SK텔레콤", "KT", "LG유플러스",
]
POLICY_TERMS = [
    "가계통신비", "통신비", "통신요금", "요금제", "5G 요금제", "5g 요금제",
    "중간요금제", "2만 원대 5G", "2만원대 5G", "선택약정", "선택약정 할인",
    "할인율", "단말기유통법", "단통법", "공시지원금", "전환지원금",
    "추가지원금", "알뜰폰", "도매대가", "최적요금제", "번호이동",
]
RISK_TERMS = [
    "ARPU", "가입자당 평균매출", "가입자당평균매출", "AI 데이터센터",
    "데이터센터", "IDC", "GPU 투자", "전기료", "전기요금", "전력요금",
    "금리 인하 지연", "배당", "배당주", "임대 단가", "과잉 공급",
]
STRUCTURE_NOTE = (
    "통신비 인하 압박은 오래된 리스크지만 AI 인프라·IDC·클라우드 매출 비중이 커질수록 "
    "통신사 실적에서 통신요금 의존도는 낮아집니다. 핵심은 요금 규제보다 수익 구조 전환 속도입니다."
)
HIGH_IMPACT_TERMS = [
    "인하", "부담 완화", "확대", "개편", "시행", "의무", "할인율",
    "선택약정", "단통법", "공시지원금", "전환지원금", "도매대가",
]


def now_kst() -> dt.datetime:
    return dt.datetime.now(tz=KST)


def clean_text(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<script\b.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_text(url: str, timeout: int = 20) -> tuple[str | None, str | None]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,*/*"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace"), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def parse_date(text: str) -> dt.datetime | None:
    match = re.search(r"\b20\d{2}[.-]\d{1,2}[.-]\d{1,2}\b", text)
    if not match:
        return None
    raw = match.group(0).replace("-", ".")
    try:
        return dt.datetime.strptime(raw, "%Y.%m.%d").replace(tzinfo=KST)
    except ValueError:
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


def is_policy_candidate(text: str, source_name: str) -> bool:
    has_policy = has_any(text, POLICY_TERMS)
    has_actor = has_any(text, ACTOR_TERMS) or source_name.startswith(("Korea Policy", "Korea Communications"))
    return has_policy and has_actor


def parse_links(text: str, source_name: str, source_url: str, now: dt.datetime) -> list[dict]:
    link_pattern = re.compile(r"<a\b[^>]*href=[\"'](?P<href>[^\"']+)[\"'][^>]*>(?P<label>.*?)</a>", re.I | re.S)
    deduped: dict[str, dict] = {}
    for match in link_pattern.finditer(text):
        title = clean_text(match.group("label"))
        if len(title) < 6:
            continue
        href = html.unescape(match.group("href"))
        link = urllib.parse.urljoin(source_url, href)
        link_lower = link.lower()
        if not any(domain in link_lower for domain in ("korea.kr", "kcc.go.kr")):
            continue
        context = clean_text(text[max(0, match.start() - 500): match.end() + 1200])
        if not is_policy_candidate(f"{title} {context}", source_name):
            continue

        detail_text, detail_error = fetch_text(link)
        detail_clean = clean_text(detail_text or "") if not detail_error else ""
        haystack = f"{title} {context} {detail_clean[:7000]}"
        if not is_policy_candidate(haystack, source_name):
            continue
        published = parse_date(haystack)
        age = age_hours(published, now)
        if age is None or age < -1 or age > MAX_AGE_HOURS:
            continue

        policy_hits = matched_terms(haystack, POLICY_TERMS)
        risk_hits = matched_terms(haystack, RISK_TERMS)
        all_hits = list(dict.fromkeys(policy_hits + risk_hits))
        high = has_any(haystack, HIGH_IMPACT_TERMS)
        fingerprint = hashlib.sha256(f"{source_name}|{title}|{link}".encode("utf-8")).hexdigest()[:16]
        summary = clean_text(detail_clean[:500] or context[:500])
        deduped[link] = {
            "source": source_name,
            "title": "정부, 통신비 인하·요금제 개편 정책 압박 확인",
            "original_title": title,
            "link": link,
            "summary": summary,
            "published_kst": published.isoformat() if published else "",
            "fingerprint": fingerprint,
            "matched": {"korea_telecom_policy": all_hits[:12] or ["통신비 정책"]},
            "importance": "상" if high else "중",
            "status": "확정",
            "impacts": ["돈 버는 능력", "할인율", "시간표"],
            "paths": ["이익", "할인율", "정책 타임라인", "수익구조 전환"],
            "sectors": ["국내 통신정책/통신3사"],
            "telecom_policy_risk": True,
            "telecom_policy_check": (
                "통신비 인하·5G 요금제·선택약정 할인율·단통법/지원금 변화가 "
                "SK텔레콤·KT·LG유플러스 ARPU와 마진을 압박하는지 확인"
            ),
            "telecom_risk_table": (
                "통신비 인하 정책 강화: ARPU 하락·이익 감소 가능성 중간 / "
                "AI 데이터센터 수요 둔화: GPU 투자 회수 지연 가능성 낮음 / "
                "금리 인하 지연: 배당주 매력 감소 가능성 중간 / "
                "데이터센터 과잉 공급: 임대 단가 하락 가능성 낮음~중간 / "
                "전기료 인상: 데이터센터 운영비 증가 가능성 중간"
            ),
            "telecom_structure_note": STRUCTURE_NOTE,
        }
    return list(deduped.values())


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
            print(f"domestic_telecom_source_failed source={source_name} error={error}")
            continue
        candidates.extend(parse_links(text or "", source_name, source_url, now))

    seen = load_seen()
    seen_map = seen.setdefault("seen", {})
    new_alerts: list[dict] = []
    for item in sorted(candidates, key=lambda x: x.get("importance") != "상"):
        fp = item["fingerprint"]
        if fp in seen_map:
            continue
        new_alerts.append(item)
        seen_map[fp] = {
            "title": item.get("original_title") or item.get("title"),
            "source": item.get("source"),
            "link": item.get("link"),
            "first_seen_kst": now.isoformat(timespec="seconds"),
            "importance": item.get("importance"),
        }
        if len(new_alerts) >= MAX_ALERTS:
            break

    if not new_alerts:
        print(f"domestic_telecom_alerts=0 candidates={len(candidates)}")
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
    print(f"domestic_telecom_alerts={len(new_alerts)} candidates={len(candidates)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
