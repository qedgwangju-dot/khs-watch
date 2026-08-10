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

STATE_PATH = Path("data/us_datacenter_execution_bottleneck_state.json")
OUT_DIR = Path("out")
LOOKBACK_DAYS = 45

QUERIES = (
    'US data center local opposition moratorium zoning permit community 2026',
    'US data center financing lenders permits zoning community opposition construction loan 2026',
    'US data center financial close drawdown construction financing permits 2026',
    'US data center grid interconnection utility substation energization delay 2026',
    'US data center power agreement interconnection approved energization 2026',
    'US data center construction starts groundbreaking permit approved 2026',
    'Data Center Watch opposition projects delayed blocked 2026',
    'Meta Amazon Google Microsoft Oracle OpenAI CoreWeave data center permit financing opposition 2026',
    'QTS CyrusOne Vantage Digital Realty Equinix data center zoning financing opposition 2026',
    'Lancium Crusoe data center power interconnection construction financing 2026',
)

STAGES = (
    (8, "전원 인가", ("energized", "energization", "power-on", "power on", "전원 인가", "전력 공급 개시")),
    (7, "착공", ("groundbreaking", "construction begins", "construction started", "breaks ground", "착공", "공사 시작")),
    (6, "실제 자금 인출", ("drawdown", "draw down", "funds drawn", "funding draw", "자금 인출", "대출 실행")),
    (5, "금융 종결", ("financial close", "financing closed", "construction loan", "credit facility", "bond sale", "financing secured", "금융 종결", "대출 약정", "채권 발행")),
    (4, "주민 반대", ("community opposition", "resident opposition", "local opposition", "moratorium", "blocked", "lawsuit", "referendum", "주민 반대", "건설 금지", "모라토리엄")),
    (3, "인허가", ("zoning approved", "permit approved", "planning approval", "special use permit", "rezoning", "entitlement", "permit denied", "zoning denied", "인허가", "허가 승인", "허가 거부")),
    (2, "계통접속", ("interconnection", "grid connection", "utility agreement", "substation", "transmission", "power agreement", "계통접속", "변전소", "송전")),
    (1, "토지", ("land purchase", "site acquired", "site control", "land deal", "parcel", "토지 매입", "부지 확보")),
)

PROJECT_TERMS = (
    "data center", "datacenter", "ai campus", "compute campus", "데이터센터", "ai 데이터센터",
)

EXECUTION_TERMS = tuple(term for _, _, terms in STAGES for term in terms)

COMPANY_TERMS = {
    "Meta": ("meta",),
    "Amazon/AWS": ("amazon", "aws"),
    "Google": ("google",),
    "Microsoft": ("microsoft",),
    "Oracle": ("oracle",),
    "OpenAI/Stargate": ("openai", "stargate"),
    "CoreWeave": ("coreweave",),
    "Crusoe": ("crusoe",),
    "QTS": ("qts",),
    "CyrusOne": ("cyrusone",),
    "Vantage": ("vantage data centers", "vantage"),
    "Digital Realty": ("digital realty",),
    "Equinix": ("equinix",),
    "Lancium": ("lancium",),
    "Blackstone": ("blackstone",),
    "xAI": ("xai",),
    "Anthropic": ("anthropic",),
}

HIGH_TRUST_SOURCES = (
    "reuters", "associated press", "ap news", "bloomberg", "wall street journal", "financial times",
    "utility dive", "data center dynamics", "datacenterdynamics", "s&p global", "moody", "fitch",
    "sec", "public utility commission", "city council", "county", "planning commission",
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
    return state


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["seen"] = list(dict.fromkeys(state.get("seen", [])))[-4000:]
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


def rss_url(query: str) -> str:
    q = quote_plus(f"{query} when:{LOOKBACK_DAYS}d")
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
    response = session.get(rss_url(query), timeout=30)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    items: list[dict[str, str]] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    for node in root.findall(".//item")[:40]:
        title = normalize(node.findtext("title"))
        link = normalize(node.findtext("link"))
        pub = normalize(node.findtext("pubDate"))
        source_node = node.find("source")
        source = normalize(source_node.text if source_node is not None else "") or "Google News"
        if not title or not link:
            continue
        dt = parse_date(pub)
        if dt and dt < cutoff:
            continue
        items.append({
            "id": digest(f"{title.lower()}|{link}"),
            "title": title,
            "link": link,
            "published": pub,
            "source": source,
            "query": query,
        })
    return items


def stage(text: str) -> tuple[int, str]:
    lower = text.lower()
    for rank, name, terms in STAGES:
        if any(term in lower for term in terms):
            return rank, name
    return 0, "관련 동향"


def companies(text: str) -> list[str]:
    lower = text.lower()
    found = []
    for name, terms in COMPANY_TERMS.items():
        if any(term in lower for term in terms):
            found.append(name)
    return found


def is_significant(item: dict[str, str]) -> bool:
    text = f"{item['title']} {item['query']}".lower()
    has_dc = any(term in text for term in PROJECT_TERMS)
    has_execution = any(term in text for term in EXECUTION_TERMS)
    return has_dc and has_execution and stage(text)[0] >= 1


def trust_label(item: dict[str, str]) -> str:
    source = item.get("source", "").lower()
    if any(term in source for term in HIGH_TRUST_SOURCES):
        return "신뢰도 높은 출처 — 공식자료 교차확인 우선"
    return "초기 보도 — 지방정부·전력회사·금융자료 확인 필요"


def investment_axis(stage_name: str) -> str:
    if stage_name in {"토지", "계통접속", "인허가", "주민 반대"}:
        return "시간표·실행 가능성"
    if stage_name in {"금융 종결", "실제 자금 인출"}:
        return "할인율·자금조달·실행 가능성"
    if stage_name in {"착공", "전원 인가"}:
        return "시간표 → 실제 설비투자·매출 연결"
    return "시간표"


def meaning(stage_name: str) -> str:
    return {
        "토지": "발표 용량이 실제 부지 통제권으로 넘어갔는지 확인",
        "계통접속": "GPU보다 앞선 전력 병목 해소 여부를 확인",
        "인허가": "프로젝트가 법적 착공 가능 상태로 전진·후퇴했는지 확인",
        "주민 반대": "소송·모라토리엄·주민투표가 착공 지연과 금융조건 악화로 번지는지 확인",
        "금융 종결": "대주단이 인허가·전력·지역 리스크를 감수하고 자금을 확정했는지 확인",
        "실제 자금 인출": "약정만이 아니라 실제 건설비 집행이 시작됐는지 확인",
        "착공": "발표 계획이 실제 기자재·EPC 매출로 전환되는 첫 구간",
        "전원 인가": "데이터센터가 실제 가동 가능한 상태에 도달하는 최종 병목",
    }.get(stage_name, "프로젝트 실행 가능성 변화 확인")


def build_report(items: list[dict[str, str]], force: bool) -> str:
    now_kst = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST")
    if force:
        return (
            "✅ 미국 데이터센터 실행 병목 감시 연결 완료\n"
            "기준: ① 토지 ② 계통접속 ③ 인허가 ④ 주민 반대 ⑤ 금융 종결 ⑥ 실제 자금 인출 ⑦ 착공 ⑧ 전원 인가\n"
            "단순 GW·투자계획 발표는 제외하고, 실제 실행 가능성이 전진·후퇴할 때만 알립니다.\n"
            "기준점: 2026년 1분기 최소 75개·1,300억달러 규모 프로젝트가 주민 반대 등으로 차질을 겪었다는 흐름을 출발점으로 추적합니다.\n"
            f"확인시각: {now_kst}"
        )

    lines = ["🚨 미국 데이터센터 실행 병목 변화", f"확인시각: {now_kst}"]
    for idx, item in enumerate(items[:6], start=1):
        text = f"{item['title']} {item['query']}"
        rank, stage_name = stage(text)
        names = ", ".join(companies(text)) or "프로젝트/지역"
        lines.extend([
            "",
            f"{idx}. {item['title']}",
            f"- 단계: {rank}/8 {stage_name}",
            f"- 관련: {names}",
            f"- 투자축: {investment_axis(stage_name)}",
            f"- 의미: {meaning(stage_name)}",
            f"- 검증상태: {trust_label(item)}",
            f"- 출처: {item['source']}",
            f"- 원문: {item['link']}",
        ])
    lines.append("\n※ 발표 GW보다 토지·전력·허가·금융·착공·전원 인가가 우선입니다. 동일 기사 재전송은 막습니다.")
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
        raise RuntimeError("모든 검색 실패: " + " | ".join(errors[:3]))

    ordered = sorted(
        all_items.values(),
        key=lambda item: parse_date(item.get("published", "")) or datetime(1970, 1, 1, tzinfo=timezone.utc),
        reverse=True,
    )
    new_items = [item for item in ordered if item["id"] not in seen and is_significant(item)]

    # 최초 실행 때 현재 검색 결과를 기준선으로 잡아 과거 기사 폭탄을 방지한다.
    state["seen"] = list(seen.union(all_items.keys()))
    state["last_scan_count"] = len(all_items)
    state["last_errors"] = errors[:10]
    save_state(state)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUT_DIR / "us_datacenter_execution_bottleneck_alert.txt"

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

    new_items.sort(
        key=lambda item: (
            stage(f"{item['title']} {item['query']}")[0],
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
