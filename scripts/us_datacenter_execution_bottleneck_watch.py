from __future__ import annotations

import argparse
import hashlib
import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
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
COMPANY_TERMS = {
    "Meta": ("meta",), "Amazon/AWS": ("amazon", "aws"), "Google": ("google",),
    "Microsoft": ("microsoft",), "Oracle": ("oracle",), "OpenAI/Stargate": ("openai", "stargate"),
    "CoreWeave": ("coreweave",), "Crusoe": ("crusoe",), "QTS": ("qts",),
    "CyrusOne": ("cyrusone",), "Vantage": ("vantage",), "Digital Realty": ("digital realty",),
    "Equinix": ("equinix",), "Lancium": ("lancium",), "Blackstone": ("blackstone",),
    "xAI": ("xai",), "Anthropic": ("anthropic",),
}
TRUSTED = ("reuters", "associated press", "ap news", "bloomberg", "wall street journal", "financial times", "utility dive", "data center dynamics", "s&p global", "moody", "fitch", "city", "county", "commission")


def norm(v: str | None) -> str:
    return " ".join((v or "").split())


def h(v: str) -> str:
    return hashlib.sha256(v.encode()).hexdigest()


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


def companies(text: str) -> list[str]:
    t = text.lower()
    return [name for name, terms in COMPANY_TERMS.items() if any(term in t for term in terms)]


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"version": 1, "seen": []}
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        state = {"version": 1, "seen": []}
    state.setdefault("seen", [])
    return state


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["seen"] = list(dict.fromkeys(state.get("seen", [])))[-4000:]
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
    rows = []
    for n in root.findall(".//item")[:40]:
        title, link, pub = norm(n.findtext("title")), norm(n.findtext("link")), norm(n.findtext("pubDate"))
        src = norm(n.find("source").text if n.find("source") is not None else "") or "Google News"
        if not title or not link:
            continue
        d = parse_date(pub)
        if d and d < cutoff:
            continue
        rows.append({"id": h(title.lower() + "|" + link), "title": title, "link": link, "published": pub, "source": src})
    return rows


def significant(item: dict[str, str]) -> bool:
    text = f"{item['title']} {item['source']}"
    t = text.lower()
    return any(x in t for x in PROJECT_TERMS) and stage(text)[0] > 0


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


def report(items: list[dict[str, str]], force: bool) -> str:
    now = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST")
    if force:
        return (
            "✅ 미국 데이터센터 실행 병목 감시 연결 완료\n"
            "추적: ① 토지 ② 계통접속 ③ 인허가 ④ 주민 반대 ⑤ 금융 종결 ⑥ 실제 자금 인출 ⑦ 착공 ⑧ 전원 인가\n"
            "단순 GW·투자계획 발표는 제외하고 실제 실행 가능성이 전진·후퇴할 때만 알립니다.\n"
            "기준점: 2026년 1분기 최소 75개·1,300억달러 규모 프로젝트 차질 흐름부터 추적합니다.\n"
            f"확인시각: {now}"
        )
    lines = ["🚨 미국 데이터센터 실행 병목 변화", f"확인시각: {now}"]
    for i, item in enumerate(items[:6], 1):
        text = f"{item['title']} {item['source']}"
        rank, s = stage(text)
        names = ", ".join(companies(text)) or "프로젝트/지역"
        trust = "신뢰도 높은 출처 — 공식자료 교차확인 우선" if any(x in item['source'].lower() for x in TRUSTED) else "초기 보도 — 지방정부·전력회사·금융자료 확인 필요"
        lines += ["", f"{i}. {item['title']}", f"- 단계: {rank}/8 {s}", f"- 관련: {names}", f"- 투자축: {axis(s)}", f"- 의미: {meaning(s)}", f"- 검증상태: {trust}", f"- 출처: {item['source']}", f"- 원문: {item['link']}"]
    lines.append("\n※ 발표 GW보다 토지·전력·허가·금융·착공·전원 인가를 우선합니다. 동일 기사 재전송은 막습니다.")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force-notify", action="store_true")
    args = ap.parse_args()
    session = requests.Session()
    session.headers.update({"User-Agent": "khs-watch/1.0 (+GitHub Actions)"})
    state, errors, all_items = load_state(), [], {}
    seen = set(state.get("seen", []))
    for q in QUERIES:
        try:
            for item in fetch(session, q):
                all_items[item["id"]] = item
        except Exception as e:
            errors.append(f"{q}: {e}")
    if not all_items and errors:
        raise RuntimeError("모든 검색 실패: " + " | ".join(errors[:3]))
    ordered = sorted(all_items.values(), key=lambda x: parse_date(x.get("published", "")) or datetime(1970, 1, 1, tzinfo=timezone.utc), reverse=True)
    new_items = [x for x in ordered if x["id"] not in seen and significant(x)]
    state["seen"] = list(seen.union(all_items.keys()))
    state["last_scan_count"], state["last_errors"] = len(all_items), errors[:10]
    save_state(state)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / "us_datacenter_execution_bottleneck_alert.txt"
    if args.force_notify:
        path.write_text(report([], True) + "\n", encoding="utf-8")
        output("changed", "true"); output("report_path", str(path))
        print(f"force_notify=true baseline_items={len(all_items)}")
        return 0
    if not new_items:
        output("changed", "false"); output("report_path", str(path))
        print(f"changed=false scanned={len(all_items)} errors={len(errors)}")
        return 0
    new_items.sort(key=lambda x: (stage(f"{x['title']} {x['source']}")[0], parse_date(x.get("published", "")) or datetime(1970, 1, 1, tzinfo=timezone.utc)), reverse=True)
    path.write_text(report(new_items, False) + "\n", encoding="utf-8")
    output("changed", "true"); output("report_path", str(path))
    print(f"changed=true new_items={len(new_items)} scanned={len(all_items)} errors={len(errors)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
