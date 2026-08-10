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
from urllib.parse import quote_plus

import requests

STATE_PATH = Path("data/us_army_test_range_kdefense_state.json")
OUT_DIR = Path("out")
LOOKBACK_DAYS = 45

QUERIES = (
    '"Army" "test range" interceptor missile private industry 30 days',
    '"testrange.army.mil" missile OR interceptor',
    '"LIG Defense" Poniard OR "LIG Nex1" Poniard OR "M-SAM II" OR Cheongung',
    '비궁 미국 시험 OR 천궁 미국 시험 OR LIG 미국 미사일 시험',
    '"Hanwha Aerospace" "Northrop Grumman" AReS missile',
    '한화에어로스페이스 노스롭그루먼 AReS 미사일 시험',
    '"Covenant Industries" Anthem missile Morocco',
)

ENTITY_GROUPS = {
    "미 육군 시험장": (
        "testrange.army.mil", "test range", "test ranges", "white sands", "camp grayling",
        "camp shelby", "dugway", "west cibola", "yuma proving ground", "morocco",
    ),
    "LIG D&A": (
        "lig defense", "lig d&a", "lig nex1", "lig넥스원", "poniard", "비궁",
        "m-sam", "cheongung", "천궁",
    ),
    "한화에어로스페이스": (
        "hanwha aerospace", "한화에어로스페이스", "northrop grumman", "노스롭그루먼", "ares",
    ),
    "Covenant Industries": ("covenant industries", "anthem missile", "anthem"),
}

TRIGGER_TERMS = (
    "access", "approval", "approved", "award", "awarded", "contract", "evaluation", "fct",
    "foreign comparative testing", "live fire", "live-fire", "procurement", "production",
    "range", "selected", "slot", "test", "testing", "trial", "agreement", "teaming",
    "승인", "계약", "도입", "생산", "선정", "실사격", "시험", "시험평가", "조달",
    "평가", "협력", "현지생산", "양산", "수주",
)

TRUSTED_SOURCES = (
    "reuters", "associated press", "ap news", "breaking defense", "defense news",
    "the war zone", "army", "dvids", "hanwha", "lig", "northrop grumman",
)


def normalize(value: str | None) -> str:
    return " ".join((value or "").split())


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"version": 1, "seen": []}
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        state = {"version": 1, "seen": []}
    state.setdefault("seen", [])
    state["version"] = 1
    return state


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    seen = list(dict.fromkeys(state.get("seen", [])))[-2500:]
    state["seen"] = seen
    state["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(STATE_PATH)


def github_output(key: str, value: str) -> None:
    path = os.getenv("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"{key}={value}\n")


def rss_url(query: str, korean: bool = False) -> str:
    suffix = "when:45d"
    q = quote_plus(f"{query} {suffix}")
    if korean:
        return f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def parse_date(value: str) -> datetime | None:
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def fetch_query(session: requests.Session, query: str) -> list[dict[str, str]]:
    korean = bool(re.search(r"[가-힣]", query))
    response = session.get(rss_url(query, korean=korean), timeout=30)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    items: list[dict[str, str]] = []
    for node in root.findall(".//item")[:35]:
        title = normalize(node.findtext("title"))
        link = normalize(node.findtext("link"))
        pub = normalize(node.findtext("pubDate"))
        source_node = node.find("source")
        source = normalize(source_node.text if source_node is not None else "")
        if not title or not link:
            continue
        dt = parse_date(pub)
        if dt and dt < datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS):
            continue
        item_id = digest(f"{title.lower()}|{link}")
        items.append({
            "id": item_id,
            "title": title,
            "link": link,
            "published": pub,
            "source": source or "Google News",
            "query": query,
        })
    return items


def entities(text: str) -> list[str]:
    lower = text.lower()
    found: list[str] = []
    for name, terms in ENTITY_GROUPS.items():
        if any(term in lower for term in terms):
            found.append(name)
    return found


def stage(text: str) -> tuple[str, int]:
    lower = text.lower()
    if any(term in lower for term in (
        "procurement", "contract award", "awarded", "order", "production contract",
        "local production", "현지생산", "조달", "수주", "양산 계약", "도입 계약",
    )):
        return "조달·양산", 5
    if any(term in lower for term in (
        "live-fire", "live fire", "foreign comparative testing", "fct", "evaluation",
        "trial", "실사격", "시험평가", "평가 완료", "시험 성공",
    )):
        return "실사격·평가", 4
    if any(term in lower for term in (
        "approved", "approval", "range access", "test slot", "test range", "testing",
        "시험 승인", "시험장", "시험 일정", "승인",
    )):
        return "시험장·시험 승인", 3
    if any(term in lower for term in (
        "agreement", "teaming", "memorandum", "moa", "mou", "joint development",
        "협력", "공동개발", "업무협약",
    )):
        return "협력·공동개발", 2
    return "관련 동향", 1


def significant(item: dict[str, str]) -> bool:
    text = f"{item['title']} {item['source']} {item['query']}".lower()
    if not entities(text):
        return False
    if not any(term in text for term in TRIGGER_TERMS):
        return False
    _, score = stage(text)
    return score >= 2


def verification(item: dict[str, str]) -> str:
    source = item.get("source", "").lower()
    title = item.get("title", "").lower()
    if any(term in source or term in title for term in ("u.s. army", "army.mil", "dvids", "hanwha", "lig defense", "northrop grumman")):
        return "공식·당사자 자료 가능성 높음"
    if any(term in source for term in TRUSTED_SOURCES):
        return "신뢰 보도 — 공식 확인 병행"
    return "초기 보도 — 공식 확인 필요"


def meaning(stage_name: str) -> str:
    return {
        "시험장·시험 승인": "기존 12~18개월 시험대기 병목이 줄어드는지 확인할 첫 지표",
        "실사격·평가": "미군 요구성능 검증이 실제 조달 후보 편입으로 넘어가는 핵심 관문",
        "협력·공동개발": "미국 현지 체계통합·공급망 진입 가능성은 커지지만 매출 확정 전 단계",
        "조달·양산": "시험·평가 옵션이 실제 수주·생산 물량과 매출로 연결되는 단계",
    }.get(stage_name, "미국 시험·평가 및 조달 시간표 변화 여부 확인")


def build_report(items: list[dict[str, str]], force: bool) -> str:
    now_kst = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST")
    if force:
        return (
            "✅ 미 육군 시험장·K-미사일 웹 감시 연결 완료\n"
            "대상: 미 육군 30일 시험장 접근 정책, LIG D&A 비궁·천궁Ⅱ, 한화에어로스페이스·Northrop Grumman AReS, Covenant Anthem\n"
            "알림 조건: 시험장/시험 승인 → 실사격 → 공식 평가/FCT → 미국 현지 협력·생산 → 조달·양산 계약의 단계 변화\n"
            "중복 기사·단순 재인용은 알리지 않고, 새 단계 변화가 있을 때만 전송합니다.\n"
            f"확인시각: {now_kst}"
        )

    lines = ["🚨 미 육군 시험장·K-미사일 새 변화", f"확인시각: {now_kst}"]
    for idx, item in enumerate(items[:5], start=1):
        text = f"{item['title']} {item['source']} {item['query']}"
        names = ", ".join(entities(text)) or "관련 체계"
        stage_name, _ = stage(text)
        lines.extend([
            "",
            f"{idx}. {item['title']}",
            f"- 단계: {stage_name}",
            f"- 관련: {names}",
            f"- 의미: {meaning(stage_name)}",
            f"- 확정도: {verification(item)}",
            f"- 출처: {item['source']}",
            f"- 원문: {item['link']}",
        ])
    lines.append("\n※ 시험 성공은 조달 계약과 동일하지 않습니다. 실제 미군 평가·현지 공급망·계약 물량까지 별도 추적합니다.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-notify", action="store_true")
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update({"User-Agent": "khs-watch/1.0 (+GitHub Actions)"})
    state = load_state()
    seen = set(state.get("seen", []))

    all_items: dict[str, dict[str, str]] = {}
    errors: list[str] = []
    for query in QUERIES:
        try:
            for item in fetch_query(session, query):
                all_items[item["id"]] = item
        except Exception as exc:
            errors.append(f"{query}: {exc}")

    if not all_items and errors:
        raise RuntimeError("모든 웹 검색 실패: " + " | ".join(errors[:3]))

    ordered = sorted(
        all_items.values(),
        key=lambda item: parse_date(item.get("published", "")) or datetime(1970, 1, 1, tzinfo=timezone.utc),
        reverse=True,
    )
    new_items = [item for item in ordered if item["id"] not in seen and significant(item)]

    # 현재 검색 결과를 기준선으로 저장해 과거 기사 재알림을 막는다.
    state["seen"] = list(seen.union(all_items.keys()))
    state["last_scan_count"] = len(all_items)
    state["last_errors"] = errors[:10]
    save_state(state)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUT_DIR / "us_army_test_range_kdefense_alert.txt"

    if args.force_notify:
        report_path.write_text(build_report([], force=True) + "\n", encoding="utf-8")
        github_output("changed", "true")
        github_output("report_path", str(report_path))
        print(f"force_notify=true baseline_items={len(all_items)}")
        return 0

    if not new_items:
        github_output("changed", "false")
        github_output("report_path", str(report_path))
        print(f"changed=false scanned={len(all_items)} errors={len(errors)}")
        return 0

    # 가장 높은 단계부터, 같은 단계면 최신 기사 순으로 전송한다.
    new_items.sort(
        key=lambda item: (
            stage(f"{item['title']} {item['source']} {item['query']}")[1],
            parse_date(item.get("published", "")) or datetime(1970, 1, 1, tzinfo=timezone.utc),
        ),
        reverse=True,
    )
    report_path.write_text(build_report(new_items, force=False) + "\n", encoding="utf-8")
    github_output("changed", "true")
    github_output("report_path", str(report_path))
    print(f"changed=true new_items={len(new_items)} scanned={len(all_items)} errors={len(errors)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
