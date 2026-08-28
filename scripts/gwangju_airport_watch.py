#!/usr/bin/env python3
import argparse
import datetime as dt
import hashlib
import html
import json
import os
import pathlib
import re
from collections import defaultdict
from email.utils import parsedate_to_datetime
from urllib.parse import quote, urlparse

import xml.etree.ElementTree as ET
import requests

KST = dt.timezone(dt.timedelta(hours=9))
ROOT = pathlib.Path(__file__).resolve().parents[1] if "scripts" in pathlib.Path(__file__).parts else pathlib.Path.cwd()
STATE_PATH = ROOT / "data" / "gwangju_airport_watch_state.json"
PENDING_STATE_PATH = ROOT / "out" / "gwangju_airport_watch_state_pending.json"
ALERT_PATH = ROOT / "out" / "gwangju_airport_alert.md"
STATUS_PATH = ROOT / "out" / "gwangju_airport_status.md"
ERROR_PATH = ROOT / "out" / "gwangju_airport_errors.log"

BASELINE = (
    "2026-08-28 국방부 이전부지 선정위원회가 전남 무안군 망운면 일대를 "
    "광주 군 공항 이전후보지로 선정. 최종 이전부지는 아직 미확정."
)
DEFAULT_CUTOFF = "2026-08-28T21:53:24+09:00"
USER_AGENT = os.getenv("GWANGJU_AIRPORT_WATCH_USER_AGENT", "KHS-Gwangju-Airport-Watch/1.0")
TIMEOUT = 25

QUERIES = [
    '"광주 군공항" 무안',
    '"광주 군 공항" 망운면',
    '"광주 군공항" 주민투표',
    '"광주 군공항" 유치 신청',
    '"광주 군공항" 이전부지 선정',
    '"광주 군공항" 지원계획 1조',
    '"광주 군공항" 이전사업 지원위원회',
    '"광주 군공항" 제1전투비행단 예천 서산 중원',
    '"광주 군공항" 반도체 클러스터 착공',
    '"광주 군공항" 지연 철회 소송',
    'site:korea.kr "광주 군 공항"',
    'site:mnd.go.kr "광주 군 공항"',
    'site:jeonnam.go.kr "광주 군 공항"',
    'site:muan.go.kr "광주 군공항"',
]

CATEGORY_RULES = {
    "지원계획·예산": ["지원계획", "1조", "지원위원회", "지원사업", "예산", "국비", "지원방안"],
    "주민투표": ["주민투표", "투표율", "찬성", "반대", "투표 결과"],
    "무안군 유치신청": ["유치 신청", "유치신청", "무안군수", "신청서"],
    "최종 이전부지": ["최종 이전부지", "이전부지 선정", "최종 선정", "이전부지로 선정"],
    "지연·철회·법적절차": ["지연", "연기", "철회", "취소", "가처분", "소송", "행정심판", "재검토", "무산"],
    "제1전투비행단 임시배치": ["제1전투비행단", "임시 배치", "임시배치", "예천", "서산", "중원기지", "기능 이전"],
    "반도체 클러스터·기존부지": ["반도체 클러스터", "반도체 산단", "국가산단", "산업단지", "착공", "부지 인도", "전력", "용수"],
}

ACTION_TERMS = [
    "확정", "선정", "의결", "발표", "공고", "구성", "출범", "개최", "실시", "결과",
    "찬성", "반대", "신청", "제출", "착공", "준공", "계약", "반영", "증액", "감액",
    "지연", "연기", "철회", "취소", "소송", "가처분", "재검토", "배치", "이전", "승인",
]

OFFICIAL_DOMAIN_SUFFIXES = (
    "korea.kr", "mnd.go.kr", "molit.go.kr", "opm.go.kr", "gwangju.go.kr", "jeonnam.go.kr", "muan.go.kr",
)
OFFICIAL_NAME_TOKENS = ["국방부", "정책브리핑", "국토교통부", "국무조정실", "광주광역시", "전라남도", "무안군"]
TRUSTED_DOMAIN_SUFFIXES = (
    "yna.co.kr", "newsis.com", "news1.kr", "kbs.co.kr", "imbc.com", "sbs.co.kr", "hankyung.com",
    "mk.co.kr", "sedaily.com", "mt.co.kr", "etnews.com", "chosun.com", "joongang.co.kr", "donga.com",
)
TRUSTED_NAME_TOKENS = ["연합뉴스", "뉴시스", "뉴스1", "KBS", "MBC", "SBS", "한국경제", "매일경제", "서울경제", "머니투데이", "전자신문"]


def now_kst():
    return dt.datetime.now(dt.timezone.utc).astimezone(KST)


def parse_iso(value):
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=KST)
        return parsed
    except Exception:
        return None


def normalize_text(text):
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_title(title):
    title = normalize_text(title)
    title = re.sub(r"\s+-\s+[^-]{1,30}$", "", title).strip()
    return title


def item_id(item):
    basis = "|".join([item.get("title", ""), item.get("source", ""), item.get("link", "")])
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:24]


def domain_from_url(url):
    try:
        return (urlparse(url).hostname or "").lower().removeprefix("www.")
    except Exception:
        return ""


def source_rank(source, source_url, link):
    source = source or ""
    domain = domain_from_url(source_url) or domain_from_url(link)
    if any(domain == suffix or domain.endswith("." + suffix) for suffix in OFFICIAL_DOMAIN_SUFFIXES) or any(tok in source for tok in OFFICIAL_NAME_TOKENS):
        return "공식"
    if any(domain == suffix or domain.endswith("." + suffix) for suffix in TRUSTED_DOMAIN_SUFFIXES) or any(tok in source for tok in TRUSTED_NAME_TOKENS):
        return "신뢰언론"
    return "기타"


def classify(text):
    return [category for category, words in CATEGORY_RULES.items() if any(word in text for word in words)]


def relevant(text):
    compact = text.replace(" ", "")
    return ("광주" in text and "군공항" in compact) or ("무안" in text and "군공항" in compact) or ("망운면" in text and "공항" in text)


def decisive(text):
    return any(term in text for term in ACTION_TERMS)


def fetch_rss(url, provider, query):
    headers = {"User-Agent": USER_AGENT, "Accept": "application/rss+xml,application/xml,text/xml,*/*"}
    response = requests.get(url, headers=headers, timeout=TIMEOUT)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    items = []
    for node in root.findall(".//item"):
        source_node = node.find("source")
        source = normalize_text(source_node.text if source_node is not None and source_node.text else "")
        source_url = source_node.attrib.get("url", "") if source_node is not None else ""
        title = normalize_title(node.findtext("title") or "")
        link = (node.findtext("link") or "").strip()
        description = normalize_text(node.findtext("description") or "")
        raw_time = node.findtext("pubDate") or node.findtext("date") or ""
        try:
            published = parsedate_to_datetime(raw_time) if raw_time else None
            if published is not None and published.tzinfo is None:
                published = published.replace(tzinfo=dt.timezone.utc)
        except Exception:
            published = None
        item = {
            "title": title,
            "link": link,
            "description": description,
            "source": source or provider,
            "source_url": source_url,
            "provider": provider,
            "query": query,
            "published": published.isoformat() if published else None,
        }
        item["rank"] = source_rank(item["source"], source_url, link)
        item["id"] = item_id(item)
        items.append(item)
    return items


def collect_items():
    all_items, errors = [], []
    for query in QUERIES:
        encoded = quote(query)
        feeds = [
            ("Google 뉴스", f"https://news.google.com/rss/search?q={encoded}&hl=ko&gl=KR&ceid=KR:ko"),
            ("Bing 뉴스", f"https://www.bing.com/news/search?q={encoded}&format=rss&setlang=ko-kr"),
        ]
        for provider, url in feeds:
            try:
                all_items.extend(fetch_rss(url, provider, query))
            except Exception as exc:
                errors.append(f"{provider} | {query} | {type(exc).__name__}: {exc}")
    deduped = {}
    for item in all_items:
        key = (item["title"].lower(), item["source"].lower())
        current = deduped.get(key)
        if current is None or (item.get("published") or "") > (current.get("published") or ""):
            deduped[key] = item
    return list(deduped.values()), errors


def load_state():
    if STATE_PATH.exists():
        try:
            state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(state, dict):
                return state
        except Exception:
            pass
    return {
        "version": 1,
        "baseline": BASELINE,
        "cutoff_kst": DEFAULT_CUTOFF,
        "seen_ids": [],
        "last_scan_kst": None,
    }


def select_alerts(items, state):
    cutoff = parse_iso(state.get("cutoff_kst") or DEFAULT_CUTOFF) or parse_iso(DEFAULT_CUTOFF)
    seen = set(state.get("seen_ids") or [])
    candidates = []
    for item in items:
        if item["id"] in seen:
            continue
        published = parse_iso(item.get("published"))
        if published and cutoff and published.astimezone(KST) <= cutoff.astimezone(KST):
            continue
        text = " ".join([item.get("title", ""), item.get("description", "")])
        if not relevant(text):
            continue
        categories = classify(text)
        if not categories or not decisive(text):
            continue
        item = dict(item)
        item["categories"] = categories
        candidates.append(item)

    official = [i for i in candidates if i["rank"] == "공식"]
    trusted = [i for i in candidates if i["rank"] == "신뢰언론"]
    selected = list(official)

    corroboration = defaultdict(list)
    for item in trusted:
        for category in item["categories"]:
            corroboration[category].append(item)
    for category, group in corroboration.items():
        distinct_sources = {i["source"] for i in group}
        if len(distinct_sources) >= 2:
            for item in group:
                if item not in selected:
                    selected.append(item)

    selected.sort(key=lambda x: x.get("published") or "")
    return selected, candidates


def format_time(value):
    parsed = parse_iso(value)
    if not parsed:
        return "시각 미표기"
    return parsed.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")


def build_alert(selected):
    ts = now_kst().strftime("%Y-%m-%d %H:%M KST")
    lines = [
        "[광주 군공항 이전 감시] 신규 변화",
        f"조회: {ts}",
        f"기준선: {BASELINE}",
        "",
    ]
    for idx, item in enumerate(selected[:8], 1):
        lines.extend([
            f"{idx}. {'·'.join(item['categories'])}",
            f"- {item['title']}",
            f"- 확정도: {'공식자료' if item['rank']=='공식' else '신뢰언론 2곳 이상 교차'}",
            f"- 출처: {item['source']} | {format_time(item.get('published'))}",
            f"- 링크: {item['link']}",
            "",
        ])
    lines.extend([
        "다음 핵심 절차: 이전주변지역 지원계획 구체화 → 주민투표 → 무안군 유치신청 → 최종 이전부지 선정.",
        "중복 기사·단순 재전송은 제외하고 공식 변화 또는 복수 신뢰언론의 동일 변화만 알림.",
    ])
    return "\n".join(lines).strip() + "\n"


def write_status(total, candidates, selected, errors):
    ts = now_kst().strftime("%Y-%m-%d %H:%M:%S KST")
    lines = [
        "# 광주 군공항 이전 감시 상태",
        f"- 조회: {ts}",
        f"- 수집 항목: {total}건",
        f"- 의미 변화 후보: {len(candidates)}건",
        f"- 알림 확정: {len(selected)}건",
        f"- 수집 오류: {len(errors)}건",
        f"- 기준선: {BASELINE}",
    ]
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ERROR_PATH.write_text("\n".join(errors) + ("\n" if errors else ""), encoding="utf-8")


def build_pending_state(items, state):
    seen = list(dict.fromkeys((state.get("seen_ids") or []) + [i["id"] for i in items]))[-2500:]
    return {
        "version": 1,
        "baseline": BASELINE,
        "cutoff_kst": state.get("cutoff_kst") or DEFAULT_CUTOFF,
        "seen_ids": seen,
        "last_scan_kst": now_kst().isoformat(),
    }


def self_test():
    sample = {
        "title": "국방부, 광주 군공항 최종 이전부지 선정 결과 발표",
        "description": "무안군 주민투표 결과를 반영해 최종 선정",
    }
    text = sample["title"] + " " + sample["description"]
    assert relevant(text)
    cats = classify(text)
    assert "최종 이전부지" in cats and "주민투표" in cats
    assert decisive(text)
    assert normalize_title("테스트 - 연합뉴스") == "테스트"
    print("self_test=ok")


def run_check():
    for path in (ALERT_PATH, STATUS_PATH, ERROR_PATH, PENDING_STATE_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()
    state = load_state()
    items, errors = collect_items()
    selected, candidates = select_alerts(items, state)
    if selected:
        ALERT_PATH.write_text(build_alert(selected), encoding="utf-8")
    pending = build_pending_state(items, state)
    PENDING_STATE_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_status(len(items), candidates, selected, errors)
    print(f"collected={len(items)} candidates={len(candidates)} alerts={len(selected)} errors={len(errors)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["check", "self-test"], default="check")
    args = parser.parse_args()
    if args.mode == "self-test":
        self_test()
    else:
        run_check()


if __name__ == "__main__":
    main()
