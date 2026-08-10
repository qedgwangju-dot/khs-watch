from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote_plus

import requests

STATE_PATH = Path("data/us_datacenter_execution_bottleneck_state.json")
OUT_DIR = Path("out")
LOOKBACK_DAYS = 45
STATE_VERSION = 2
MIN_INDEPENDENT_SOURCES = 2

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
    'site:reuters.com US data center permit financing opposition interconnection construction 2026',
    'site:utilitydive.com data center interconnection permit utility 2026',
    'site:datacenterdynamics.com US data center permit construction financing power 2026',
)

STAGES = (
    (8, "전원 인가", ("energized", "energization", "power-on", "power on", "전원 인가")),
    (7, "착공", ("groundbreaking", "construction begins", "construction started", "breaks ground", "착공")),
    (6, "실제 자금 인출", ("drawdown", "draw down", "funds drawn", "funding draw", "자금 인출", "대출 실행")),
    (5, "금융 종결", ("financial close", "financing closed", "construction loan", "credit facility", "bond sale", "financing secured", "금융 종결", "대출 약정")),
    (4, "주민 반대", ("community opposition", "resident opposition", "local opposition", "moratorium", "blocked", "lawsuit", "referendum", "주민 반대")),
    (3, "인허가", ("zoning approved", "permit approved", "planning approval", "special use permit", "rezoning", "permit denied", "zoning denied", "인허가", "허가 승인", "허가 거부")),
    (2, "계통접속", ("interconnection", "grid connection", "utility agreement", "substation", "transmission", "power agreement", "계통접속", "변전소", "송전")),
    (1, "토지", ("land purchase", "site acquired", "site control", "land deal", "parcel", "토지 매입", "부지 확보")),
)

PROJECT_TERMS = ("data center", "datacenter", "ai campus", "compute campus", "데이터센터")

FORWARD_TERMS = (
    "approved", "approval", "secured", "closed", "begins", "started", "starts", "groundbreaking",
    "acquired", "purchase", "agreement", "signed", "energized", "energization", "cleared", "authorized",
    "승인", "확보", "체결", "착공", "인가", "인출", "실행",
)
BACKWARD_TERMS = (
    "denied", "rejected", "blocked", "delay", "delayed", "moratorium", "lawsuit", "opposition",
    "suspend", "suspended", "cancel", "cancelled", "canceled", "halt", "paused", "appeal",
    "거부", "반대", "지연", "중단", "취소", "소송", "모라토리엄",
)

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
    "Vantage": ("vantage",),
    "Digital Realty": ("digital realty",),
    "Equinix": ("equinix",),
    "Lancium": ("lancium",),
    "Blackstone": ("blackstone",),
    "xAI": ("xai",),
    "Anthropic": ("anthropic",),
}

OFFICIAL_OR_PARTY_HINTS = (
    "city of ", "county", "planning commission", "public service commission", "public utility commission",
    "public utilities commission", "sec.gov", "securities and exchange commission", "department of energy",
    "federal energy regulatory commission", "ferc", "ercot", "pjm", "dominion energy", "duke energy",
    "american electric power", "aep", "meta", "microsoft", "amazon", "google", "oracle", "coreweave",
    "qts", "cyrusone", "vantage data centers", "digital realty", "equinix", "lancium", "crusoe",
)
REPUTABLE_HINTS = (
    "reuters", "associated press", "ap news", "bloomberg", "wall street journal", "financial times",
    "utility dive", "data center dynamics", "datacenterdynamics", "s&p global", "moody", "fitch",
    "the information", "bisnow", "commercial observer",
)

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "data", "center", "centers", "centre", "centres",
    "datacenter", "for", "from", "in", "into", "is", "its", "new", "of", "on", "or", "the", "to", "us",
    "u", "s", "with", "2026", "project", "projects", "site", "plans", "plan", "says", "said",
}


@dataclass
class EventCluster:
    rank: int
    stage_name: str
    direction: str
    items: list[dict[str, str]]


def norm(v: str | None) -> str:
    return " ".join((v or "").split())


def sha(v: str) -> str:
    return hashlib.sha256(v.encode("utf-8")).hexdigest()


def parse_date(v: str) -> datetime | None:
    try:
        d = parsedate_to_datetime(v)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except Exception:
        return None


def stage(text: str) -> tuple[int, str]:
    t = text.lower()
    for rank, name, terms in STAGES:
        if any(term in t for term in terms):
            return rank, name
    return 0, "관련 동향"


def direction(text: str, stage_name: str = "") -> str:
    t = text.lower()
    backward = sum(1 for x in BACKWARD_TERMS if x in t)
    forward = sum(1 for x in FORWARD_TERMS if x in t)
    if stage_name == "주민 반대" and backward == 0:
        backward = 1
    if backward > forward:
        return "후퇴"
    if forward > backward:
        return "전진"
    return "변화"


def companies(text: str) -> list[str]:
    t = text.lower()
    return [name for name, terms in COMPANY_TERMS.items() if any(term in t for term in terms)]


def source_class(source: str) -> str:
    s = source.lower()
    if any(x in s for x in OFFICIAL_OR_PARTY_HINTS):
        return "공식·당사자"
    if any(x in s for x in REPUTABLE_HINTS):
        return "신뢰보도"
    return "기타"


def title_tokens(title: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", title.lower())
    return {w for w in words if len(w) >= 3 and w not in STOPWORDS}


def similarity(a: dict[str, str], b: dict[str, str]) -> float:
    ta, tb = title_tokens(a["title"]), title_tokens(b["title"])
    if not ta or not tb:
        return 0.0
    union = ta | tb
    return len(ta & tb) / len(union) if union else 0.0


def same_event(a: dict[str, str], b: dict[str, str]) -> bool:
    ra, sa = stage(a["title"])
    rb, sb = stage(b["title"])
    if ra == 0 or rb == 0 or sa != sb:
        return False
    if direction(a["title"], sa) != direction(b["title"], sb):
        return False
    ca, cb = set(companies(a["title"])), set(companies(b["title"]))
    if ca and cb and ca & cb:
        return similarity(a, b) >= 0.16
    return similarity(a, b) >= 0.34


def independent_sources(items: list[dict[str, str]]) -> list[str]:
    seen: dict[str, str] = {}
    for item in items:
        key = re.sub(r"[^a-z0-9]+", "", item["source"].lower())
        if key and key not in seen:
            seen[key] = item["source"]
    return list(seen.values())


def cluster_items(items: list[dict[str, str]]) -> list[EventCluster]:
    clusters: list[EventCluster] = []
    for item in items:
        rank, stage_name = stage(item["title"])
        if rank == 0:
            continue
        d = direction(item["title"], stage_name)
        placed = False
        for cluster in clusters:
            if cluster.stage_name == stage_name and cluster.direction == d and any(same_event(item, x) for x in cluster.items):
                cluster.items.append(item)
                placed = True
                break
        if not placed:
            clusters.append(EventCluster(rank=rank, stage_name=stage_name, direction=d, items=[item]))
    return clusters


def verified(cluster: EventCluster) -> bool:
    sources = independent_sources(cluster.items)
    if len(sources) < MIN_INDEPENDENT_SOURCES:
        return False
    classes = {source_class(s) for s in sources}
    return bool(classes & {"공식·당사자", "신뢰보도"})


def event_fingerprint(cluster: EventCluster) -> str:
    all_companies = sorted({name for item in cluster.items for name in companies(item["title"])})
    token_counts: dict[str, int] = {}
    for item in cluster.items:
        for token in title_tokens(item["title"]):
            token_counts[token] = token_counts.get(token, 0) + 1
    common = sorted(token for token, count in token_counts.items() if count >= min(2, len(cluster.items)))[:16]
    basis = "|".join([
        str(cluster.rank), cluster.stage_name, cluster.direction,
        ",".join(all_companies), ",".join(common),
    ])
    return sha(basis)


def significant(item: dict[str, str]) -> bool:
    t = f"{item['title']} {item['source']}".lower()
    return any(x in t for x in PROJECT_TERMS) and stage(item["title"])[0] > 0


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"version": STATE_VERSION, "alerted_events": []}
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        state = {}
    state.setdefault("version", 1)
    state.setdefault("alerted_events", [])
    return state


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["version"] = STATE_VERSION
    state["alerted_events"] = list(dict.fromkeys(state.get("alerted_events", [])))[-2500:]
    state["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(STATE_PATH)


def output(k: str, v: str) -> None:
    p = os.getenv("GITHUB_OUTPUT")
    if p:
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"{k}={v}\n")


def fetch(session: requests.Session, query: str) -> list[dict[str, str]]:
    url = f"https://news.google.com/rss/search?q={quote_plus(query + f' when:{LOOKBACK_DAYS}d')}&hl=en-US&gl=US&ceid=US:en"
    r = session.get(url, timeout=30)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    rows: list[dict[str, str]] = []
    for n in root.findall(".//item")[:40]:
        title = norm(n.findtext("title"))
        link = norm(n.findtext("link"))
        pub = norm(n.findtext("pubDate"))
        src_node = n.find("source")
        src = norm(src_node.text if src_node is not None else "") or "Google News"
        if not title or not link:
            continue
        d = parse_date(pub)
        if d and d < cutoff:
            continue
        rows.append({
            "id": sha(title.lower() + "|" + link),
            "title": title,
            "link": link,
            "published": pub,
            "source": src,
        })
    return rows


def axis(stage_name: str) -> str:
    if stage_name in {"토지", "계통접속", "인허가", "주민 반대"}:
        return "시간표·실행 가능성"
    if stage_name in {"금융 종결", "실제 자금 인출"}:
        return "할인율·자금조달·실행 가능성"
    return "시간표 → 실제 설비투자·매출 연결"


def meaning(stage_name: str) -> str:
    return {
        "토지": "발표 용량이 실제 부지 통제권으로 넘어갔는지 확인",
        "계통접속": "전력망·변전소 병목이 실제로 해소되는지 확인",
        "인허가": "법적 착공 가능 상태가 전진·후퇴했는지 확인",
        "주민 반대": "소송·모라토리엄·주민투표가 착공·금융을 막는지 확인",
        "금융 종결": "대주단이 인허가·전력·지역 리스크를 감수하고 자금을 확정했는지 확인",
        "실제 자금 인출": "약정이 아니라 실제 건설비 집행이 시작됐는지 확인",
        "착공": "계획이 기자재·설계·조달·시공 매출로 전환되는 첫 구간",
        "전원 인가": "실제 가동 가능한 상태에 도달하는 최종 병목",
    }.get(stage_name, "프로젝트 실행 가능성 변화 확인")


def next_indicator(stage_name: str) -> str:
    return {
        "토지": "계통접속 신청·전력회사 협약",
        "계통접속": "변전소·송전 증설 일정과 인허가",
        "인허가": "금융 종결 또는 착공 허가",
        "주민 반대": "소송·주민투표·모라토리엄의 법적 효력과 인허가 일정",
        "금융 종결": "실제 대출 인출·공사비 집행",
        "실제 자금 인출": "착공·주요 기자재 발주",
        "착공": "전력망 공정률·전원 인가 예정일",
        "전원 인가": "실제 서버 반입·가동률 상승",
    }.get(stage_name, "다음 공식 단계 변화")


def best_items(cluster: EventCluster) -> list[dict[str, str]]:
    priority = {"공식·당사자": 0, "신뢰보도": 1, "기타": 2}
    return sorted(
        cluster.items,
        key=lambda x: (
            priority[source_class(x["source"])],
            -(parse_date(x.get("published", "")) or datetime(1970, 1, 1, tzinfo=timezone.utc)).timestamp(),
        ),
    )


def report(clusters: list[EventCluster], force: bool) -> str:
    now = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST")
    if force:
        return (
            "✅ 미국 데이터센터 실행 병목 감시 연결·검증 완료\n"
            "추적: ① 토지 ② 계통접속 ③ 인허가 ④ 주민 반대 ⑤ 금융 종결 ⑥ 실제 자금 인출 ⑦ 착공 ⑧ 전원 인가\n"
            "알림 조건: 같은 단계 변화가 서로 다른 2개 이상 출처에서 확인되고, 그중 최소 1개가 공식·당사자 또는 신뢰 매체일 때만 전송\n"
            "단순 GW·투자계획·중복 재인용은 전송하지 않습니다.\n"
            f"확인시각: {now}"
        )

    lines = ["🚨 미국 데이터센터 실행 병목 변화", f"확인시각: {now}"]
    for i, cluster in enumerate(clusters[:5], 1):
        items = best_items(cluster)
        sources = independent_sources(items)
        names = sorted({name for item in items for name in companies(item["title"])})
        lines.extend([
            "",
            f"{i}. {items[0]['title']}",
            f"- 단계: {cluster.rank}/8 {cluster.stage_name} · {cluster.direction}",
            f"- 관련: {', '.join(names) if names else '프로젝트/지역'}",
            f"- 투자축: {axis(cluster.stage_name)}",
            f"- 의미: {meaning(cluster.stage_name)}",
            f"- 교차검증: {len(sources)}개 독립 출처 ({', '.join(sources[:4])})",
            f"- 다음 확인지표: {next_indicator(cluster.stage_name)}",
        ])
        for idx, item in enumerate(items[:2], 1):
            lines.append(f"- 근거{idx}: [{source_class(item['source'])}] {item['source']} · {item['link']}")
    lines.append("\n※ 1개 출처뿐인 속보·루머·단순 재인용은 보류하고, 2개 출처가 맞을 때만 알립니다.")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force-notify", action="store_true")
    args = ap.parse_args()

    session = requests.Session()
    session.headers.update({"User-Agent": "khs-watch/2.0 (+GitHub Actions)"})
    state = load_state()
    all_items: dict[str, dict[str, str]] = {}
    errors: list[str] = []

    for q in QUERIES:
        try:
            for item in fetch(session, q):
                all_items[item["id"]] = item
        except Exception as e:
            errors.append(f"{q}: {e}")

    if not all_items and errors:
        raise RuntimeError("모든 검색 실패: " + " | ".join(errors[:3]))

    candidates = [x for x in all_items.values() if significant(x)]
    clusters = [c for c in cluster_items(candidates) if verified(c)]
    clusters.sort(
        key=lambda c: (
            c.rank,
            max((parse_date(x.get("published", "")) or datetime(1970, 1, 1, tzinfo=timezone.utc)).timestamp() for x in c.items),
        ),
        reverse=True,
    )

    current_fps = [event_fingerprint(c) for c in clusters]
    migrating = int(state.get("version", 1)) < STATE_VERSION
    alerted = set(state.get("alerted_events", []))

    # v1 -> v2 전환 시 현재 확인된 이벤트를 기준선으로만 저장해 과거 기사 폭탄을 막는다.
    if migrating:
        alerted.update(current_fps)
        new_clusters: list[EventCluster] = []
    else:
        new_clusters = [c for c in clusters if event_fingerprint(c) not in alerted]
        alerted.update(event_fingerprint(c) for c in new_clusters)

    state["alerted_events"] = list(alerted)
    state["last_scan_count"] = len(all_items)
    state["last_candidate_count"] = len(candidates)
    state["last_verified_cluster_count"] = len(clusters)
    state["last_errors"] = errors[:10]
    save_state(state)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / "us_datacenter_execution_bottleneck_alert.txt"

    if args.force_notify:
        path.write_text(report([], True) + "\n", encoding="utf-8")
        output("changed", "true")
        output("report_path", str(path))
        print(f"force_notify=true scanned={len(all_items)} verified_clusters={len(clusters)}")
        return 0

    if not new_clusters:
        output("changed", "false")
        output("report_path", str(path))
        print(
            f"changed=false scanned={len(all_items)} candidates={len(candidates)} "
            f"verified_clusters={len(clusters)} migrating={migrating} errors={len(errors)}"
        )
        return 0

    path.write_text(report(new_clusters, False) + "\n", encoding="utf-8")
    output("changed", "true")
    output("report_path", str(path))
    print(
        f"changed=true new_clusters={len(new_clusters)} scanned={len(all_items)} "
        f"verified_clusters={len(clusters)} errors={len(errors)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
