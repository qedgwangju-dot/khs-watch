#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import html
import importlib.util
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
WATCH_PATH = HERE / "khs_us_investment_watch.py"

spec = importlib.util.spec_from_file_location("khs_us_investment_watch", WATCH_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"watcher load failed: {WATCH_PATH}")
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)
core = watch.core

GUARD_VERSION = 2

_ORIG_LOAD = core._load
_ORIG_RSS = core._rss
_ORIG_KEY = core._key
_ORIG_SEMANTIC_KEY = core._semantic_key
_ORIG_RUN_EVENT_KEY = core._run_event_key

_SHARED_STATE: dict | None = None
_BOOTSTRAP_GUARD = False
_RSS_CALLS = 0
_RSS_BUFFER: list[dict] = []


def _norm(value: str) -> str:
    value = html.unescape(value or "").lower().replace("韓", "한국")
    value = (
        value.replace("–", "-")
        .replace("—", "-")
        .replace("∼", "~")
        .replace("～", "~")
    )
    return re.sub(r"\s+", " ", value).strip()


def _is_official(row: dict) -> bool:
    try:
        if core._is_official(row):
            return True
    except Exception:
        pass
    blob = _norm(f"{row.get('title', '')} {row.get('source', '')}")
    return any(
        token in blob
        for token in [
            "정책브리핑",
            "대한민국 정책브리핑",
            "산업통상부",
            "산업통상",
            "재정경제부",
            "기획재정부",
            "과학기술정보통신부",
            "과기정통부",
            "ercot",
            "puct",
            "texas governor",
            "sec",
        ]
    )


def _family(row: dict) -> str:
    low = _norm(f"{row.get('title', '')} {row.get('source', '')}")

    westinghouse = "웨스팅하우스" in low or "westinghouse" in low
    stake = any(
        token in low
        for token in [
            "지분",
            "소수지분",
            "지분인수",
            "인수 추진",
            "stake",
            "equity",
            "acquisition",
            "acquire",
            "이사회",
            "board seat",
            "의결권",
        ]
    )
    if westinghouse and stake:
        return "westinghouse_stake"

    if any(
        token in low
        for token in [
            "파이로",
            "파이로프로세싱",
            "pyroprocessing",
            "사용후핵연료",
            "spent nuclear fuel",
            "핵연료주기",
            "fuel cycle",
            "핵연료 재활용",
            "재처리",
        ]
    ):
        return "nuclear_fuel_cycle_pyro"

    if any(
        token in low
        for token in [
            "45영업일",
            "45일 안전판",
            "조기 송금",
            "조기송금",
            "자금 납입",
            "첫 송금",
            "첫 집행",
            "첫 납입",
            "capital call",
        ]
    ):
        return "funding_execution"

    if any(
        token in low
        for token in [
            "수익배분",
            "손실분담",
            "risk-pooling",
            "리스크 풀링",
            "프로젝트별 손익",
            "원리금",
            "손실 상계",
            "투자회수",
        ]
    ):
        return "return_safeguard"

    if any(
        token in low
        for token in [
            "1천억달러",
            "100 billion",
            "원전 8기",
            "원전8기",
            "eight nuclear",
            "첫 사업",
            "첫사업",
            "first project",
            "합의 임박",
            "합의 근접",
            "nears agreement",
        ]
    ) and any(token in low for token in ["대미투자", "한국", "korea", "한미"]):
        return "energy_package"

    if "엔시날" in low or "encinal" in low or "6.3gw" in low:
        return "encinal"

    if "알래스카" in low or "alaska lng" in low:
        return "alaska_lng"

    if "ercot" in low or "batch zero" in low or "large load" in low:
        return "ercot_large_load"

    if any(
        token in low
        for token in [
            "두산에너빌리티",
            "doosan enerbility",
            "비에이치아이",
            "babcock & wilcox",
            "base electron",
            "siemens energy",
            "ge vernova",
            "fastpower",
            "가스터빈",
            "gas turbine",
            "hrsg",
            "증기터빈",
            "steam turbine",
            "천연가스 보일러",
            "natural gas boiler",
        ]
    ):
        return "power_equipment_supply"

    if any(
        token in low
        for token in ["원전", "ap1000", "apr1400", "nuclear"]
    ):
        return "nuclear_build"

    if any(
        token in low
        for token in ["반도체", "삼성전자", "sk하이닉스", "semiconductor"]
    ):
        return "semiconductor_investment"

    if any(
        token in low
        for token in ["텍사스", "texas", "데이터센터", "data center", "가스발전", "gas power", "gas plant"]
    ):
        return "texas_ai_power"

    try:
        legacy = _ORIG_RUN_EVENT_KEY(row)
    except Exception:
        legacy = ""
    if legacy:
        return f"legacy_{legacy}"

    try:
        semantic = _ORIG_SEMANTIC_KEY(row)
    except Exception:
        semantic = ""
    if semantic:
        return f"legacy_{semantic}"

    return ""


def _material_facts(row: dict) -> set[str]:
    low = _norm(str(row.get("title") or ""))
    facts: set[str] = set()

    # 퍼센트 범위는 단일 퍼센트보다 먼저 뽑아 중복을 막는다.
    range_re = re.compile(
        r"(\d+(?:\.\d+)?)\s*(?:~|-|to)\s*(\d+(?:\.\d+)?)\s*%"
    )
    for match in range_re.finditer(low):
        facts.add(f"percent:{match.group(1)}~{match.group(2)}")
    without_ranges = range_re.sub(" ", low)
    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*%", without_ranges):
        facts.add(f"percent:{match.group(1)}")

    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*(gw|mw|mtpa)\b", low):
        facts.add(f"{match.group(2)}:{match.group(1)}")

    # 원화 환산값은 환율에 따라 움직이므로 상태 변화 판정에서 제외한다.
    for match in re.finditer(
        r"(\d+(?:\.\d+)?(?:천|백)?)\s*(억|조)\s*달러", low
    ):
        facts.add(f"usd:{match.group(1)}{match.group(2)}")
    for match in re.finditer(
        r"\$\s*(\d+(?:\.\d+)?)\s*(billion|million|trillion)?", low
    ):
        facts.add(f"usd:{match.group(1)}{match.group(2) or ''}")

    for model in ["ap1000", "apr1400"]:
        if model in low:
            start = low.find(model)
            window = low[start : start + 80]
            for match in re.finditer(r"(\d+)\s*기", window):
                facts.add(f"{model}:{match.group(1)}기")

    if any(
        token in low
        for token in [
            "원전",
            "reactor",
            "터빈",
            "turbine",
            "hrsg",
            "보일러",
            "ap1000",
            "apr1400",
        ]
    ):
        for match in re.finditer(r"(\d+)\s*기", low):
            facts.add(f"units:{match.group(1)}기")

    for token in ["45영업일", "12~15개월", "12-15개월", "20년", "30년"]:
        if token in low:
            facts.add(f"schedule:{token}")

    milestones = [
        ("공식확정", ["공식 확정", "최종 확정", "확정 발표"]),
        ("체결", ["체결", "본계약", "계약 체결", "signed agreement"]),
        ("수주발주", ["수주", "발주", "구매주문", "purchase order"]),
        ("승인", ["승인", "approved"]),
        ("허가", ["허가", "permit"]),
        ("착공", ["착공", "groundbreaking", "construction start"]),
        ("최종투자결정", ["최종투자결정", " fid"]),
        ("금융종결", ["금융종결", "financial close"]),
        ("전력구매계약", ["ppa", "전력구매계약", "전력판매계약"]),
        ("장기구매계약", [" spa", "장기구매계약"]),
        ("기본합의", [" hoa", "heads of agreement"]),
        ("송금집행", ["송금", "첫 집행", "첫 납입", "자금 납입"]),
        ("의결", ["의결"]),
        ("선정", ["선정"]),
        (
            "공식정정",
            [
                "정정",
                "사실이 아닙니다",
                "확정된 바 없습니다",
                "결정된 바 없습니다",
                "미확정",
            ],
        ),
        ("전원인가", ["전원 인가", "energized"]),
    ]
    for tag, terms in milestones:
        if any(term in low for term in terms):
            facts.add(f"stage:{tag}")

    if "이사회" in low or "board seat" in low:
        facts.add("governance:board")
    if "의결권" in low or "voting right" in low:
        facts.add("governance:voting")

    parties = [
        ("westinghouse", ["웨스팅하우스", "westinghouse"]),
        ("khnp", ["한수원", "한국수력원자력", "khnp"]),
        ("kepco", ["한전", "한국전력", "kepco"]),
        ("doosan", ["두산에너빌리티", "doosan enerbility"]),
        ("bhi", ["비에이치아이", "bhi"]),
        ("gevernova", ["ge vernova"]),
        ("siemens", ["siemens energy"]),
        ("bw", ["babcock & wilcox", "b&w"]),
        ("baseelectron", ["base electron"]),
        ("applieddigital", ["applied digital"]),
        ("posco", ["포스코", "posco"]),
        ("kogas", ["한국가스공사", "kogas"]),
        ("glenfarne", ["glenfarne"]),
        ("ercot", ["ercot"]),
    ]
    for label, terms in parties:
        if any(term in low for term in terms):
            facts.add(f"party:{label}")

    if _is_official(row):
        facts.add("source:official")

    return facts


_FAMILY_LABELS = {
    "westinghouse_stake": "웨스팅하우스 지분·거버넌스",
    "nuclear_fuel_cycle_pyro": "사용후핵연료·파이로 투자",
    "funding_execution": "대미투자 자금 집행·45영업일",
    "return_safeguard": "대미투자 수익배분·원금회수",
    "energy_package": "대미투자 에너지 패키지",
    "encinal": "텍사스 엔시날 발전사업",
    "alaska_lng": "알래스카 LNG",
    "ercot_large_load": "ERCOT 대형부하·계통연계",
    "power_equipment_supply": "가스터빈·증기터빈·HRSG 공급망",
    "nuclear_build": "미국 원전 구성·발주",
    "semiconductor_investment": "반도체 대미투자",
    "texas_ai_power": "텍사스 AI 전력",
}


def _human_fact(value: str) -> str:
    if value.startswith("percent:"):
        return value.split(":", 1)[1] + "%"
    if value.startswith("gw:"):
        return value.split(":", 1)[1] + "GW"
    if value.startswith("mw:"):
        return value.split(":", 1)[1] + "MW"
    if value.startswith("mtpa:"):
        return value.split(":", 1)[1] + "MTPA"
    if value.startswith("usd:"):
        return value.split(":", 1)[1] + "달러"
    if value.startswith("ap1000:"):
        return "AP1000 " + value.split(":", 1)[1]
    if value.startswith("apr1400:"):
        return "APR1400 " + value.split(":", 1)[1]
    if value.startswith("units:"):
        return value.split(":", 1)[1]
    if value.startswith("stage:"):
        return value.split(":", 1)[1]
    if value == "source:official":
        return "공식자료 확인"
    if value == "governance:board":
        return "이사회 참여"
    if value == "governance:voting":
        return "의결권"
    if value.startswith("schedule:"):
        return value.split(":", 1)[1]
    party_names = {
        "party:westinghouse": "Westinghouse",
        "party:khnp": "한국수력원자력",
        "party:kepco": "한국전력",
        "party:doosan": "두산에너빌리티",
        "party:bhi": "비에이치아이",
        "party:gevernova": "GE Vernova",
        "party:siemens": "Siemens Energy",
        "party:bw": "Babcock & Wilcox",
        "party:baseelectron": "Base Electron",
        "party:applieddigital": "Applied Digital",
        "party:posco": "포스코",
        "party:kogas": "한국가스공사",
        "party:glenfarne": "Glenfarne",
        "party:ercot": "ERCOT",
    }
    return party_names.get(value, value)


def _event_key(family: str, facts: set[str]) -> str:
    payload = family + "|" + "|".join(sorted(facts))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def _load() -> dict:
    global _SHARED_STATE, _BOOTSTRAP_GUARD
    state = _ORIG_LOAD()
    _BOOTSTRAP_GUARD = int(state.get("event_state_guard_version") or 0) < GUARD_VERSION
    state.setdefault("event_states", {})
    if _BOOTSTRAP_GUARD:
        state["event_state_guard_version"] = GUARD_VERSION
        state["event_state_guard_started_at"] = dt.datetime.now(
            dt.timezone.utc
        ).isoformat()
    _SHARED_STATE = state
    return state


def _bucket(family: str) -> dict:
    assert _SHARED_STATE is not None
    buckets = _SHARED_STATE.setdefault("event_states", {})
    item = buckets.setdefault(
        family,
        {
            "facts": [],
            "initialized_at": "",
            "updated_at": "",
            "last_title": "",
            "last_source": "",
        },
    )
    item.setdefault("facts", [])
    item.setdefault("initialized_at", "")
    return item


def _remember(family: str, row: dict, facts: set[str]) -> set[str]:
    bucket = _bucket(family)
    known = set(str(x) for x in bucket.get("facts") or [])
    new_facts = facts - known
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    if not bucket.get("initialized_at"):
        bucket["initialized_at"] = now
    if new_facts:
        known.update(new_facts)
        bucket["facts"] = sorted(known)
        bucket["updated_at"] = now
        bucket["last_title"] = str(row.get("title") or "")
        bucket["last_source"] = str(row.get("source") or "")
    return new_facts


def _collapse_rows(rows: list[dict]) -> list[dict]:
    assert _SHARED_STATE is not None
    now = dt.datetime.now(dt.timezone.utc)

    # 여러 검색어에서 같은 기사가 반복 수집되는 것을 먼저 제거한다.
    unique: dict[str, dict] = {}
    for row in rows:
        raw_key = _ORIG_KEY(row)
        unique.setdefault(raw_key, row)
    ordered = sorted(
        unique.values(),
        key=lambda r: str(r.get("published") or ""),
        reverse=True,
    )

    if _BOOTSTRAP_GUARD:
        # 전환 첫 실행은 현재 보이는 기사들을 '현재 상태 기준선'으로만 흡수한다.
        # 과거 기사 재전송을 하지 않고 다음 실행부터 실제 새 상태값만 알린다.
        seen = _SHARED_STATE.setdefault("seen", {})
        for row in ordered:
            seen[_ORIG_KEY(row)] = now.isoformat()
            family = _family(row)
            if not family:
                continue
            _remember(family, row, _material_facts(row))
        _SHARED_STATE["event_state_guard_baselined_at"] = now.isoformat()
        print(f"event_state_guard_baseline_rows={len(ordered)}")
        return []

    out: list[dict] = []
    suppressed_unclassified = 0

    for row in ordered:
        if len(out) >= 5:
            break

        family = _family(row)
        if not family:
            # 사건축을 판정하지 못한 기사 자체를 알림 사유로 삼지 않는다.
            # 검색 범위는 유지하되 다음 코드 보강 대상으로만 남긴다.
            suppressed_unclassified += 1
            continue

        bucket = _bucket(family)
        initialized = bool(bucket.get("initialized_at"))
        facts = _material_facts(row)

        if not initialized:
            new_facts = _remember(family, row, facts)
            if not new_facts:
                new_facts = {"event:first_seen"}
        else:
            new_facts = _remember(family, row, facts)

        # 같은 사건·같은 수치·같은 단계는 기사 제목/URL/언론사가 달라도 재알림하지 않는다.
        if not new_facts:
            continue

        cumulative = set(str(x) for x in _bucket(family).get("facts") or [])
        state_key = _event_key(family, cumulative | set(new_facts))

        label = _FAMILY_LABELS.get(family, family.replace("_", " "))
        visible = [
            _human_fact(x)
            for x in sorted(new_facts)
            if x != "event:first_seen"
        ]

        synthetic = dict(row)
        if visible:
            synthetic["title"] = (
                f"[상태 변화] {label} — " + " · ".join(visible[:6])
            )
        else:
            synthetic["title"] = f"[신규 사건] {label}"

        synthetic["_state_guard_family"] = family
        synthetic["_state_guard_key"] = state_key
        synthetic["_state_guard_delta"] = sorted(new_facts)
        synthetic["_state_guard_evidence_title"] = str(row.get("title") or "")
        out.append(synthetic)

    if suppressed_unclassified:
        print(f"event_state_guard_unclassified_suppressed={suppressed_unclassified}")
    print(f"event_state_changes={len(out)}")
    return out


def _rss(query: str) -> list[dict]:
    global _RSS_CALLS, _RSS_BUFFER
    _RSS_CALLS += 1
    try:
        rows = _ORIG_RSS(query)
    except Exception as exc:
        print(f"state_guard_rss_error={type(exc).__name__}")
        rows = []
    _RSS_BUFFER.extend(rows)

    if _RSS_CALLS < len(core.QUERIES):
        return []

    flushed = _collapse_rows(_RSS_BUFFER)
    _RSS_BUFFER = []
    return flushed


def _key(row: dict) -> str:
    state_key = str(row.get("_state_guard_key") or "")
    if state_key:
        return f"stateevt_{state_key}"
    return _ORIG_KEY(row)


def _semantic_key(row: dict) -> str:
    state_key = str(row.get("_state_guard_key") or "")
    family = str(row.get("_state_guard_family") or "")
    if state_key and family:
        return f"eventstate_{family}_{state_key}"
    return _ORIG_SEMANTIC_KEY(row)


def _run_event_key(row: dict) -> str:
    family = str(row.get("_state_guard_family") or "")
    state_key = str(row.get("_state_guard_key") or "")
    if family and state_key:
        return f"eventstate_{family}_{state_key}"
    if family:
        return f"eventstate_{family}"
    return _ORIG_RUN_EVENT_KEY(row)


core._load = _load
core._rss = _rss
core._key = _key
core._semantic_key = _semantic_key
core._run_event_key = _run_event_key


def main() -> int:
    return watch.main()


if __name__ == "__main__":
    raise SystemExit(main())
