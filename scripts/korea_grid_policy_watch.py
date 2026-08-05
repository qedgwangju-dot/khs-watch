from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

STATE_PATH = Path("data/korea_grid_policy_state.json")
OUT_DIR = Path("out")

MCEE_PRESS_URLS = (
    "https://www.mcee.go.kr/home/web/board/list.do?boardCategoryId=39&boardMasterId=1&menuId=10525&maxPageItems=50",
    "https://www.mcee.go.kr/home/web/board/list.do?boardCategoryId=&boardMasterId=939&menuId=10598&maxPageItems=50",
)

LAW_PAGES = (
    {
        "name": "송전설비주변법 시행령",
        "url": (
            "https://www.law.go.kr/LSW/lsInfoP.do?ancYnChk=0&chrClsCd=010202"
            "&efYd=20260603&lsiSeq=286475&urlMode=lsInfoP"
        ),
    },
    {
        "name": "송·변전설비 주변지역 보상·지원 기준 고시",
        "url": (
            "https://www.law.go.kr/LSW/admRulInfoP.do?admRulSeq=2100000277830"
            "&chrClsCd=010202&urlMode=admRulLsInfoP"
        ),
    },
)

RSS_SOURCES = (
    {
        "name": "기후에너지환경부 공식 검색",
        "url": (
            "https://news.google.com/rss/search?q=site%3Amcee.go.kr+"
            "%28%22%EC%A0%84%EB%A0%A5%EB%A7%9D%22+OR+%22%EC%86%A1%EC%A0%84%EC%84%A0%EB%A1%9C%22+OR+"
            "%22%EC%86%A1%EC%A0%84%EC%B2%A0%ED%83%91%22+OR+%22%EC%9E%85%EC%A7%80%EC%84%A0%EC%A0%95%EC%9C%84%EC%9B%90%ED%9A%8C%22+OR+"
            "%22%EA%B3%84%ED%86%B5%EC%86%8C%EB%93%9D%22+OR+%22%EC%A7%80%EC%A4%91%ED%99%94%22%29+when%3A90d"
            "&hl=ko&gl=KR&ceid=KR%3Ako"
        ),
    },
    {
        "name": "한국전력 공식 검색",
        "url": (
            "https://news.google.com/rss/search?q=site%3Akepco.co.kr+"
            "%28%22%EC%86%A1%EC%A0%84%EC%84%A0%EB%A1%9C%22+OR+%22%EB%B3%80%EC%A0%84%EC%86%8C%22+OR+%22345kV%22+OR+%22765kV%22+OR+"
            "%22%EC%A7%80%EC%A4%91%ED%99%94%22+OR+%22%EA%B5%AD%EA%B0%80%EA%B8%B0%EA%B0%84%EC%A0%84%EB%A0%A5%EB%A7%9D%22%29+"
            "%28%22%EA%B3%B5%EA%B3%A0%22+OR+%22%EC%9E%85%EC%B0%B0%22+OR+%22%EB%B0%9C%EC%A3%BC%22+OR+%22%EC%B0%A9%EA%B3%B5%22+OR+"
            "%22%ED%99%95%EC%A0%95%22%29+when%3A90d&hl=ko&gl=KR&ceid=KR%3Ako"
        ),
    },
    {
        "name": "국가법령정보센터 공식 검색",
        "url": (
            "https://news.google.com/rss/search?q=site%3Alaw.go.kr+"
            "%28%22%EC%86%A1%C2%B7%EB%B3%80%EC%A0%84%EC%84%A4%EB%B9%84%22+OR+%22%EC%9E%85%EC%A7%80%EC%84%A0%EC%A0%95%EC%9C%84%EC%9B%90%ED%9A%8C%22+OR+"
            "%22%EA%B3%84%ED%86%B5%EC%86%8C%EB%93%9D%22%29+%28%22%EA%B0%9C%EC%A0%95%22+OR+%22%EA%B3%A0%EC%8B%9C%22+OR+"
            "%22%EC%8B%9C%ED%96%89%EB%A0%B9%22%29+when%3A180d&hl=ko&gl=KR&ceid=KR%3Ako"
        ),
    },
)

PRIMARY_TERMS = (
    "국가기간 전력망",
    "국가기간전력망",
    "전력망 건설",
    "전력망 갈등",
    "송전철탑",
    "송전선로",
    "송ㆍ변전",
    "송·변전",
    "송변전",
    "전력구",
    "입지선정위원회",
    "계통소득",
    "주민 수용성",
    "주민수용성",
    "345kv",
    "765kv",
    "154kv",
    "초고압",
)

ACTION_TERMS = (
    "최종",
    "확정",
    "의결",
    "개정",
    "고시",
    "시행령",
    "행정예고",
    "입찰",
    "발주",
    "낙찰",
    "착공",
    "공고",
    "사업비",
    "예산",
    "보상",
    "지원금",
    "고정금리",
    "도입",
    "노선",
    "경과지",
    "주민협의체",
    "실무위원회",
)

VERSION_PATTERNS = (
    re.compile(r"\[시행\s*\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.\]"),
    re.compile(r"\[(?:대통령령|기후에너지환경부고시|산업통상자원부고시)\s*제[^\]]+\]"),
    re.compile(r"(?:대통령령|기후에너지환경부고시|산업통상자원부고시)\s*제\d+-?\d*호"),
)


class FetchError(RuntimeError):
    pass


def normalize(value: str | None) -> str:
    return " ".join((value or "").split())


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"version": 1, "seen_items": [], "page_versions": {}}
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    state.setdefault("seen_items", [])
    state.setdefault("page_versions", {})
    state["version"] = 1
    return state


def write_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(STATE_PATH)


def output(key: str, value: str) -> None:
    path = os.getenv("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"{key}={value}\n")


def request(session: requests.Session, url: str, timeout: int = 35) -> requests.Response:
    try:
        response = session.get(url, timeout=timeout, allow_redirects=True)
        response.raise_for_status()
        return response
    except requests.RequestException as exc:
        raise FetchError(f"{url}: {exc}") from exc


def topic_match(text: str) -> bool:
    lower = normalize(text).lower()
    if any(term in lower for term in PRIMARY_TERMS):
        return True
    if "지중화" in lower:
        return any(
            term in lower
            for term in (
                "송전",
                "변전",
                "전력구",
                "국가기간",
                "철탑",
                "345kv",
                "765kv",
                "154kv",
                "민가 밀집",
            )
        )
    return any(term in lower for term in ("전력망", "변전소", "철탑")) and any(
        term in lower for term in ACTION_TERMS
    )


def classify_item(text: str) -> tuple[str, int]:
    lower = normalize(text).lower()
    if any(term in lower for term in ("최종 대책", "최종 확정", "실무위원회 의결")):
        return "최종 대책", 5
    if ("입지선정위원회" in lower and any(term in lower for term in ("개정", "고시", "행정예고"))) or (
        any(term in lower for term in ("시행령", "고시")) and "개정" in lower
    ):
        return "법령·고시 개정", 4
    if any(term in lower for term in ("입찰", "발주", "낙찰", "착공")):
        return "실제 발주·착공", 4
    if any(term in lower for term in ("계통소득", "지원금", "고정금리", "햇빛소득마을")):
        return "보상·이익공유", 3
    if any(term in lower for term in ("지중화", "철탑", "노선 통합", "송전선로")):
        return "노선·지중화", 2
    return "전력망 정책", 1


def parse_date(value: str) -> datetime | None:
    value = normalize(value)
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        pass
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def parse_html_items(html: str, base_url: str, source: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict[str, Any]] = []
    for anchor in soup.find_all("a", href=True):
        title = normalize(anchor.get_text(" ", strip=True))
        if len(title) < 4:
            continue
        parent = getattr(anchor, "parent", None)
        context = normalize(parent.get_text(" ", strip=True) if parent else title)
        haystack = f"{title} {context}"
        if not topic_match(haystack):
            continue
        url = urljoin(base_url, str(anchor.get("href")))
        category, stage = classify_item(haystack)
        date_match = re.search(r"20\d{2}[-./]\d{1,2}[-./]\d{1,2}", context)
        items.append(
            {
                "id": digest(f"{source}|{url}|{title}"),
                "title": title,
                "source": source,
                "url": url,
                "published": date_match.group(0) if date_match else "",
                "category": category,
                "stage": stage,
            }
        )
    return list({str(item["id"]): item for item in items}.values())


def tag_text(item: ET.Element, name: str) -> str:
    for node in item.iter():
        if node.tag.split("}")[-1].lower() == name.lower():
            return normalize(node.text)
    return ""


def parse_rss(xml_text: str, source_name: str) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise FetchError(f"RSS 분석 실패: {exc}") from exc
    items: list[dict[str, Any]] = []
    for node in root.iter():
        if node.tag.split("}")[-1].lower() != "item":
            continue
        title = tag_text(node, "title")
        link = tag_text(node, "link")
        guid = tag_text(node, "guid") or link or title
        published = tag_text(node, "pubDate")
        if not topic_match(title):
            continue
        category, stage = classify_item(title)
        items.append(
            {
                "id": digest(f"{source_name}|{guid}"),
                "title": title,
                "source": source_name,
                "url": link,
                "published": published,
                "category": category,
                "stage": stage,
            }
        )
    return list({str(item["id"]): item for item in items}.values())


def extract_law_version(html: str, name: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    text = normalize(soup.get_text(" ", strip=True))
    parts: list[str] = []
    for pattern in VERSION_PATTERNS:
        parts.extend(pattern.findall(text))
    if not parts:
        title = normalize(soup.title.get_text(" ", strip=True) if soup.title else name)
        parts = [title, digest(text[:4000])]
    return " | ".join(dict.fromkeys(parts))


def setup_report() -> str:
    return "\n".join(
        [
            "# 전력망 정책 알림 경로 변경 완료",
            "- 수신 봇: @hs8879887988798879_bot · 알림",
            "- 감시 1: 정부 최종 대책 확정과 국가기간 전력망 확충 실무위원회 의결",
            "- 감시 2: 입지선정위원회 고시·시행령 개정",
            "- 감시 3: 지중화 구간·전압·총사업비·정부와 한전의 비용 분담",
            "- 감시 4: 계통소득·지원금·햇빛소득마을·물가연동 보상",
            "- 감시 5: 154·345·765kV 송전선로·변전소·전력구 입찰·발주·착공",
            "- 발송 기준: 새 공식 문서·법령 변경·실제 발주가 확인될 때만 전송",
        ]
    ) + "\n"


def investment_meaning(category: str) -> str:
    mapping = {
        "최종 대책": "초안이 확정 정책으로 전환돼 지중화·노선 통합·보상의 집행 가능성이 상승",
        "법령·고시 개정": "주민협의·인허가·보상 절차가 바뀌어 전력망 준공 시간표와 사업 위험이 변동",
        "실제 발주·착공": "정책 기대가 케이블·변압기·GIS·전력구·설계·시공의 실제 매출 시간표로 이동",
        "보상·이익공유": "주민 수용성과 함께 한전·정부의 보상비·금융비용 부담이 변동",
        "노선·지중화": "가공철탑 물량과 지중 케이블·전력구 설비투자의 품목 배분이 변동",
    }
    return mapping.get(category, "전력망 건설의 시간표·설비투자 품목·지역 갈등 비용이 변동")


def render_report(items: list[dict[str, Any]], errors: list[str]) -> str:
    lines = ["# 전력망 정책·발주 새 공식 변화"]
    for index, item in enumerate(items[:6], start=1):
        category = str(item.get("category") or "전력망 정책")
        published = normalize(str(item.get("published") or "")) or "발표일 확인 필요"
        lines.extend(
            [
                f"\n## {index}. {item.get('title')}",
                f"- 단계: {category}",
                f"- 기관: {item.get('source')}",
                f"- 발표일: {published}",
                f"- 투자 의미: {investment_meaning(category)}",
                f"- 공식 원문: {item.get('url')}",
            ]
        )
    if len(items) > 6:
        lines.append(f"\n- 같은 실행에서 추가 확인된 공식 변화: {len(items) - 6}건")
    if errors:
        lines.append(f"- 일부 원천 접근 지연: {len(errors)}곳")
    return "\n".join(lines).rstrip() + "\n"


def collect(session: requests.Session) -> tuple[list[dict[str, Any]], dict[str, str], list[str]]:
    items: list[dict[str, Any]] = []
    versions: dict[str, str] = {}
    errors: list[str] = []

    for url in MCEE_PRESS_URLS:
        try:
            response = request(session, url)
            items.extend(parse_html_items(response.text, response.url, "기후에너지환경부"))
        except FetchError as exc:
            errors.append(str(exc))

    for source in RSS_SOURCES:
        try:
            response = request(session, str(source["url"]))
            items.extend(parse_rss(response.text, str(source["name"])))
        except FetchError as exc:
            errors.append(str(exc))

    for page in LAW_PAGES:
        try:
            response = request(session, str(page["url"]))
            versions[str(page["name"])] = extract_law_version(response.text, str(page["name"]))
        except FetchError as exc:
            errors.append(str(exc))

    return list({str(item["id"]): item for item in items}.values()), versions, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-notify", action="store_true")
    args = parser.parse_args(argv)

    now = datetime.now(timezone.utc)
    initial_run = not STATE_PATH.exists()
    state = load_state()
    seen = set(str(value) for value in state.get("seen_items", []))
    old_versions = {str(k): str(v) for k, v in dict(state.get("page_versions", {})).items()}

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "khs-watch-korea-grid-policy/1.0",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
        }
    )

    items, versions, errors = collect(session)
    recent: list[dict[str, Any]] = []
    for item in items:
        published = parse_date(str(item.get("published", "")))
        if published and now - published > timedelta(days=180):
            continue
        recent.append(item)

    new_items = [item for item in recent if str(item["id"]) not in seen]
    law_changes: list[dict[str, Any]] = []
    for page in LAW_PAGES:
        name = str(page["name"])
        new_version = versions.get(name)
        old_version = old_versions.get(name)
        if new_version and old_version and new_version != old_version:
            category, stage = classify_item(f"{name} 개정 고시")
            law_changes.append(
                {
                    "id": digest(f"law-change|{name}|{new_version}"),
                    "title": f"{name} 버전 변경 감지",
                    "source": "국가법령정보센터",
                    "url": str(page["url"]),
                    "published": "",
                    "category": category,
                    "stage": stage,
                }
            )

    next_seen = sorted(seen | {str(item["id"]) for item in recent} | {str(item["id"]) for item in law_changes})
    if len(next_seen) > 5000:
        next_seen = next_seen[-5000:]
    write_state(
        {
            "version": 1,
            "seen_items": next_seen,
            "page_versions": {**old_versions, **versions},
            "updated_at": now.isoformat(),
            "last_source_errors": errors[-20:],
        }
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.force_notify:
        report_path = OUT_DIR / now.strftime("%Y%m%dT%H%M%SZ-korea-grid-policy-route.md")
        report_path.write_text(setup_report(), encoding="utf-8")
        output("changed", "true")
        output("report_path", str(report_path))
        output("report_title", f"[전력망 정책] 알림 봇 경로 확인 {now:%Y-%m-%d}")
        return 0

    if initial_run:
        print("전력망 정책 최초 기준선 저장 완료")
        output("changed", "false")
        return 0

    notify_items = sorted(
        law_changes + new_items,
        key=lambda item: (int(item.get("stage", 0)), str(item.get("published", ""))),
        reverse=True,
    )
    if not notify_items:
        print("전력망 정책·발주 신규 공식 변화 없음")
        output("changed", "false")
        return 0

    report_path = OUT_DIR / now.strftime("%Y%m%dT%H%M%SZ-korea-grid-policy.md")
    report_path.write_text(render_report(notify_items, errors), encoding="utf-8")
    output("changed", "true")
    output("report_path", str(report_path))
    output("report_title", f"[전력망 정책] 공식 변화 {now:%Y-%m-%d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
