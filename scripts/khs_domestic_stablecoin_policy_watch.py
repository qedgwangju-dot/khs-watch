#!/usr/bin/env python3
"""KHS domestic stablecoin and digital-asset policy watch.

This lane catches Korean official policy signals on won stablecoins,
digital-asset legislation, payment infrastructure, and deposit-substitution
regulatory risk before they are folded into the policy Telegram alert.
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
SEEN_PATH = DATA_DIR / "khs_domestic_stablecoin_policy_seen.json"
KST = ZoneInfo("Asia/Seoul")
MAX_AGE_HOURS = int(os.getenv("KHS_SOURCE_MAX_AGE_HOURS", "72"))
MAX_ALERTS = int(os.getenv("KHS_DOMESTIC_STABLECOIN_MAX_ALERTS", "3"))
MAX_DETAIL_LINKS_PER_SOURCE = int(os.getenv("KHS_DOMESTIC_STABLECOIN_MAX_DETAIL_LINKS_PER_SOURCE", "8"))
UA = os.getenv("SEC_USER_AGENT", "KHS-domestic-stablecoin-policy-watch contact=github-actions")

STABLECOIN_QUERY = urllib.parse.quote("스테이블코인")
DIGITAL_ASSET_QUERY = urllib.parse.quote("디지털자산")
VIRTUAL_ASSET_QUERY = urllib.parse.quote("가상자산")

SOURCES = [
    (
        "Financial Services Commission stablecoin releases",
        f"https://www.fsc.go.kr/no010101?srchText={STABLECOIN_QUERY}",
    ),
    (
        "Financial Services Commission stablecoin explanations",
        f"https://www.fsc.go.kr/no010102?srchText={STABLECOIN_QUERY}",
    ),
    (
        "Financial Services Commission digital asset releases",
        f"https://www.fsc.go.kr/no010101?srchText={DIGITAL_ASSET_QUERY}",
    ),
    (
        "Korea Policy Briefing stablecoin search",
        f"https://www.korea.kr/news/policyNewsList.do?srchKeyword={STABLECOIN_QUERY}",
    ),
    (
        "Korea Policy Briefing digital asset search",
        f"https://www.korea.kr/news/policyNewsList.do?srchKeyword={DIGITAL_ASSET_QUERY}",
    ),
    (
        "Bank of Korea digital currency policy",
        "https://www.bok.or.kr/portal/submain/submain/cbdc.do?menuNo=201136",
    ),
    (
        "Bank of Korea payment research",
        "https://www.bok.or.kr/portal/bbs/B0000232/list.do?menuNo=200706",
    ),
    (
        "Korea FIU virtual asset notices",
        "https://www.kofiu.go.kr/kor/notification/notice.do",
    ),
]

ACTOR_TERMS = [
    "금융위원회", "금융위", "금융감독원", "금감원", "한국은행", "한은",
    "국회", "정무위원회", "정부", "당정", "가상자산위원회", "금융당국",
    "금융정보분석원", "FIU", "은행", "은행권", "핀테크", "가상자산거래소",
    "거래소", "전자금융업자", "결제사업자",
]
POLICY_TERMS = [
    "스테이블코인", "원화 스테이블코인", "디지털자산기본법", "디지털자산 기본법",
    "가상자산 2단계", "2단계 입법", "2단계법", "가상자산법", "디지털자산법",
    "디지털자산", "가상자산", "결제토큰", "지급결제", "디지털화폐", "CBDC",
]
EVENT_TERMS = [
    "발행", "발행인", "발행주체", "발행 주체", "유통", "허용", "규율",
    "규제", "법안", "입법", "준비자산", "상환청구권", "예금 대체",
    "은행 중심", "핀테크", "거래소", "상용화", "기술 검증", "테스트",
    "표준", "결제", "인프라", "협의", "확정", "미확정", "정해진 바",
]
HIGH_IMPACT_TERMS = [
    "발행주체", "발행 주체", "은행 중심", "핀테크", "거래소", "예금 대체",
    "준비자산", "상환청구권", "허용", "규제", "법안", "입법", "2단계법",
    "상용화", "표준", "결제 인프라", "확정된 바", "정해진 바",
]
SECTORS = [
    "금융/자본시장/스테이블코인",
    "은행/핀테크/결제",
    "가상자산거래소/디지털자산",
]
POLICY_CHECK = (
    "디지털자산기본법·가상자산 2단계법, 원화 스테이블코인 발행 주체"
    "(은행·핀테크·거래소), 준비자산·상환청구권, 예금 대체 논란, 한국은행·금융당국 규제 강도 확인"
)
RISK_TABLE = (
    "법 진행형: 발행 주체·업권 범위 미확정 / "
    "예금 대체 논란: 한국은행·금융당국 규제 강도 상승 가능 / "
    "기술 검증과 상용화 차이: 실적 연결 시차 큼 / "
    "자금 성격: 코인 가격보다 미래 결제·유통 표준 선점 베팅"
)
STRUCTURE_NOTE = (
    "이 테마는 코인 가격보다 금융 인프라 재편으로 봐야 합니다. "
    "지금 붙는 자금은 당장 실적보다 누가 미래 결제·유통 표준에 앉을 수 있느냐에 먼저 베팅하는 성격이 강합니다."
)
COUNTER = (
    "법안 세부안, 발행 주체, 준비자산 요건, 예금 대체 방지 장치가 확정되지 않았고 "
    "기술 검증이 실제 상용화와 수수료 매출로 이어지기까지 시간이 필요합니다."
)


def now_kst() -> dt.datetime:
    return dt.datetime.now(tz=KST)


def clean_text(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<script\b.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_text(url: str, timeout: int = 8) -> tuple[str | None, str | None]:
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
    if match:
        raw = match.group(0).replace("-", ".")
        try:
            return dt.datetime.strptime(raw, "%Y.%m.%d").replace(tzinfo=KST)
        except ValueError:
            pass
    match = re.search(r"\b(20\d{2})년\s*(\d{1,2})월\s*(\d{1,2})일\b", text)
    if match:
        year, month, day = (int(part) for part in match.groups())
        return dt.datetime(year, month, day, tzinfo=KST)
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
    has_event = has_any(text, EVENT_TERMS)
    has_actor = has_any(text, ACTOR_TERMS) or source_name.startswith(
        ("Financial Services Commission", "Korea Policy", "Bank of Korea", "National Assembly")
    )
    return has_policy and has_event and has_actor


def stablecoin_title(text: str) -> str:
    if has_any(text, ["발행주체", "발행 주체", "은행 중심", "핀테크", "거래소"]):
        return "국내 디지털자산 정책: 원화 스테이블코인 발행 주체·업권 범위 체크"
    if has_any(text, ["예금 대체", "한국은행", "한은", "준비자산", "상환청구권"]):
        return "국내 디지털자산 정책: 스테이블코인 예금 대체·준비자산 규제 체크"
    if has_any(text, ["상용화", "기술 검증", "테스트", "결제"]):
        return "국내 디지털자산 정책: 스테이블코인 결제 인프라 상용화 체크"
    return "국내 디지털자산 정책: 원화 스테이블코인 법안·결제 표준 체크"


def parse_links(text: str, source_name: str, source_url: str, now: dt.datetime) -> list[dict]:
    link_pattern = re.compile(r"<a\b[^>]*href=[\"'](?P<href>[^\"']+)[\"'][^>]*>(?P<label>.*?)</a>", re.I | re.S)
    deduped: dict[str, dict] = {}
    detail_fetches = 0
    for match in link_pattern.finditer(text):
        if detail_fetches >= MAX_DETAIL_LINKS_PER_SOURCE:
            break
        title = clean_text(match.group("label"))
        if len(title) < 5:
            continue
        href = html.unescape(match.group("href"))
        link = urllib.parse.urljoin(source_url, href)
        link_lower = link.lower()
        if not any(domain in link_lower for domain in ("fsc.go.kr", "korea.kr", "bok.or.kr", "kofiu.go.kr")):
            continue
        context = clean_text(text[max(0, match.start() - 600): match.end() + 1500])
        if not is_policy_candidate(f"{title} {context}", source_name):
            continue

        detail_fetches += 1
        detail_text, detail_error = fetch_text(link)
        detail_clean = clean_text(detail_text or "") if not detail_error else ""
        haystack = f"{title} {context} {detail_clean[:9000]}"
        if not is_policy_candidate(haystack, source_name):
            continue
        published = parse_date(haystack)
        age = age_hours(published, now)
        if age is None or age < -1 or age > MAX_AGE_HOURS:
            continue

        policy_hits = matched_terms(haystack, POLICY_TERMS + EVENT_TERMS + ACTOR_TERMS)
        high = has_any(haystack, HIGH_IMPACT_TERMS)
        fingerprint = hashlib.sha256(f"{source_name}|{title}|{link}".encode("utf-8")).hexdigest()[:16]
        summary = clean_text(detail_clean[:650] or context[:650])
        deduped[link] = {
            "source": source_name,
            "title": stablecoin_title(haystack),
            "original_title": title,
            "link": link,
            "summary": summary,
            "published_kst": published.isoformat() if published else "",
            "fingerprint": fingerprint,
            "matched": {"korea_stablecoin_policy": policy_hits[:14] or ["스테이블코인 정책"]},
            "importance": "상" if high else "중",
            "status": "확정",
            "impacts": ["시간표", "할인율", "수급"],
            "paths": ["정책 타임라인", "규제 강도", "금융 인프라 재편", "표준 선점", "테마 수급"],
            "sectors": SECTORS[:],
            "domestic_stablecoin_policy_watch": True,
            "stablecoin_policy_check": POLICY_CHECK,
            "stablecoin_risk_table": RISK_TABLE,
            "stablecoin_structure_note": STRUCTURE_NOTE,
            "counter": COUNTER,
            "reflection": "중간",
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
            print(f"domestic_stablecoin_source_failed source={source_name} error={error}")
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
        print(f"domestic_stablecoin_alerts=0 candidates={len(candidates)}")
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
    print(f"domestic_stablecoin_alerts={len(new_alerts)} candidates={len(candidates)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
