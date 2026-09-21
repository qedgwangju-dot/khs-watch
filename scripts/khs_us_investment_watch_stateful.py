#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import html
import importlib.util
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WATCH_PATH = HERE / "khs_us_investment_watch.py"

spec = importlib.util.spec_from_file_location("khs_us_investment_watch", WATCH_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"watcher load failed: {WATCH_PATH}")
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)
core = watch.core

GUARD_VERSION = 3

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

    if ("ap1000" in low or "apr1400" in low) and re.search(r"\d+\s*기", low):
        return "nuclear_build"

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


# v3 원칙: 기사/URL 자체는 절대 알림 상태가 아니다.
# 기사와 공식자료는 아래의 정규화된 사건 상태값을 뒷받침하는 증거로만 사용한다.
_RAW_MATERIAL_FACTS = _material_facts

_NEGATION_TERMS = (
    "확정된 바 없습니다",
    "결정된 바 없습니다",
    "정해진 바 없습니다",
    "미확정",
    "아직 확정 전",
    "사실이 아닙니다",
    "not confirmed",
    "not decided",
)

def _source_key(row: dict) -> str:
    source = _norm(str(row.get("source") or "unknown"))
    link = _norm(str(row.get("link") or ""))

    # 포털 재게시본과 원매체 URL을 서로 다른 독립 출처로 이중 계산하지 않는다.
    # 네이버 언론사 코드: 015=한국경제, 008=머니투데이, 421=뉴스1.
    aliases = (
        (("한국경제", "한경", "hankyung.com", "article/015/"), "한국경제"),
        (("머니투데이", "moneytoday", "mt.co.kr", "article/008/"), "머니투데이"),
        (("뉴스1", "news1.kr", "article/421/"), "뉴스1"),
        (("연합뉴스", "yna.co.kr", "article/001/"), "연합뉴스"),
        (("reuters", "reuters.com"), "reuters"),
        (("bloomberg", "bloomberg.com"), "bloomberg"),
    )
    blob = f"{source} {link}"
    for tokens, canonical in aliases:
        if any(token in blob for token in tokens):
            return canonical
    return source

def _published_key(row: dict) -> str:
    return str(row.get("published") or "")

def _official_status_fact(row: dict) -> str:
    low = _norm(str(row.get("title") or ""))
    if _is_official(row) and any(term in low for term in _NEGATION_TERMS):
        return "official_status:unconfirmed"
    if _is_official(row) and any(
        term in low for term in ["공식 확정", "최종 확정", "확정 발표", "공식 발표", "approved", "signed"]
    ):
        return "official_status:confirmed"
    return ""

def _korean_usd_tokens(low: str) -> list[str]:
    out: list[str] = []
    for match in re.finditer(r"(\d+(?:\.\d+)?(?:천|백)?)\s*(억|조)\s*달러", low):
        out.append(f"{match.group(1)}{match.group(2)}")
    for match in re.finditer(r"\$\s*(\d+(?:\.\d+)?)\s*(billion|million|trillion)?", low):
        out.append(f"{match.group(1)}{match.group(2) or ''}")
    return list(dict.fromkeys(out))

def _explicit_model_units(low: str, model: str) -> set[str]:
    values: set[str] = set()
    escaped = re.escape(model)
    patterns = [
        rf"{escaped}\s*(?:형|노형)?\s*(\d+)\s*기",
        rf"(\d+)\s*기\s*(?:의\s*)?{escaped}",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, low):
            values.add(match.group(1))
    return values

def _explicit_total_nuclear_units(low: str) -> set[str]:
    values: set[str] = set()
    patterns = [
        r"(?:미국\s*)?(?:대형\s*)?원전\s*(?:최대\s*)?(\d+)\s*기",
        r"(\d+)\s*기\s*(?:의\s*)?(?:미국\s*)?(?:대형\s*)?원전",
        r"(?:up to\s*)?(\d+)\s+(?:nuclear\s+)?reactors?",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, low):
            values.add(match.group(1))
    return values

def _money_near_anchor(low: str, anchors: tuple[str, ...]) -> set[str]:
    out: set[str] = set()
    for match in re.finditer(r"(\d+(?:\.\d+)?(?:천|백)?)\s*(억|조)\s*달러", low):
        start, end = match.span()
        window = low[max(0, start - 45): min(len(low), end + 45)]
        if any(anchor in window for anchor in anchors):
            if any(term in window for term in ["전체 대미투자", "총 대미투자", "총 투자약속", "전체 투자"]):
                continue
            out.add(f"{match.group(1)}{match.group(2)}")
    for match in re.finditer(r"\$\s*(\d+(?:\.\d+)?)\s*(billion|million|trillion)?", low):
        start, end = match.span()
        window = low[max(0, start - 45): min(len(low), end + 45)]
        if any(anchor in window for anchor in anchors):
            out.add(f"{match.group(1)}{match.group(2) or ''}")
    return out

def _candidate_facts(row: dict, family: str) -> set[str]:
    low = _norm(str(row.get("title") or ""))
    raw = _RAW_MATERIAL_FACTS(row)
    facts: set[str] = set()
    official_status = _official_status_fact(row)
    if official_status:
        # 정부가 '미확정'이라고 밝힌 기사에서는 제목 속 배경 숫자를 상태값으로 승격하지 않는다.
        facts.add(official_status)
        if official_status.endswith("unconfirmed"):
            return facts

    parties = {x for x in raw if x.startswith("party:")}
    stages = {x for x in raw if x.startswith("stage:") and x != "stage:공식정정"}

    if family == "nuclear_build":
        for value in _explicit_total_nuclear_units(low):
            facts.add(f"nuclear_total_units:{value}")
        for value in _explicit_model_units(low, "ap1000"):
            facts.add(f"ap1000_units:{value}")
        for value in _explicit_model_units(low, "apr1400"):
            facts.add(f"apr1400_units:{value}")
        facts |= parties
        facts |= stages
        return facts

    if family == "westinghouse_stake":
        for pattern in [
            r"(?:지분(?:율)?|stake)\D{0,18}(\d+(?:\.\d+)?)\s*%",
            r"(\d+(?:\.\d+)?)\s*%\D{0,18}(?:지분(?:율)?|stake)",
        ]:
            for match in re.finditer(pattern, low):
                facts.add(f"stake_percent:{match.group(1)}")
        facts |= {x for x in raw if x.startswith("governance:")}
        facts |= parties
        facts |= stages
        return facts

    if family == "funding_execution":
        if "45영업일" in low:
            facts.add("funding_wait:45영업일")
        if any(term in low for term in ["송금", "납입", "집행", "capital call"]):
            if any(term in low for term in ["예정", "가능성", "가능", "검토", "협의", "요구"]):
                facts.add("stage:송금예정")
            if any(term in low for term in ["송금 완료", "납입 완료", "집행 완료", "송금했다", "납입했다", "집행했다"]):
                facts.add("stage:송금집행")
            for value in _money_near_anchor(low, ("첫 송금", "첫 납입", "초기 집행", "자금 납입", "capital call")):
                facts.add(f"funding_amount_usd:{value}")
            for match in re.finditer(r"(20\d{2})[-./년]\s*(\d{1,2})[-./월]\s*(\d{1,2})", low):
                window = low[max(0, match.start()-40): min(len(low), match.end()+40)]
                if any(anchor in window for anchor in ["송금", "납입", "집행"]):
                    facts.add(f"funding_date:{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}")
        facts |= parties
        return facts

    if family == "return_safeguard":
        if any(term in low for term in ["수익배분", "원리금", "risk-pooling", "리스크 풀링", "손실분담", "투자회수"]):
            facts |= {x for x in raw if x.startswith("percent:")}
            if "20년" in low:
                facts.add("repayment_horizon:20년")
            facts |= stages
        return facts | parties

    if family == "energy_package":
        for value in _explicit_total_nuclear_units(low):
            facts.add(f"package_nuclear_units:{value}")
        if any(term in low for term in ["패키지", "대미투자", "첫 사업", "첫사업", "합의"]):
            for value in _korean_usd_tokens(low):
                facts.add(f"package_usd:{value}")
        facts |= stages
        return facts | parties

    if family == "encinal":
        if "6.3gw" in low or "엔시날" in low or "encinal" in low:
            if "6.3gw" in low:
                facts.add("encinal_total_gw:6.3")
            if "1.4gw" in low:
                facts.add("encinal_phase1_gw:1.4")
            if "4.9gw" in low:
                facts.add("encinal_phase2_gw:4.9")
            if any(term in low for term in ["사업비", "투자", "project cost"]):
                for value in _korean_usd_tokens(low):
                    facts.add(f"encinal_project_usd:{value}")
            facts |= stages
        return facts | parties

    if family == "alaska_lng":
        for match in re.finditer(r"(\d+(?:\.\d+)?)\s*mtpa\b", low):
            facts.add(f"alaska_mtpa:{match.group(1)}")
        if any(term in low for term in ["사업비", "투자", "project cost"]):
            for value in _korean_usd_tokens(low):
                facts.add(f"alaska_project_usd:{value}")
        facts |= stages
        return facts | parties

    if family == "ercot_large_load":
        for match in re.finditer(r"(\d+(?:\.\d+)?)\s*gw\b", low):
            facts.add(f"ercot_request_gw:{match.group(1)}")
        facts |= stages
        return facts | parties

    if family == "power_equipment_supply":
        facts |= parties
        facts |= stages
        for match in re.finditer(r"(\d+(?:\.\d+)?)\s*(gw|mw)\b", low):
            facts.add(f"equipment_capacity_{match.group(2)}:{match.group(1)}")
        if any(term in low for term in ["계약", "수주", "발주", "구매주문", "purchase order"]):
            for value in _korean_usd_tokens(low):
                facts.add(f"equipment_contract_usd:{value}")
        return facts

    if family == "semiconductor_investment":
        if any(term in low for term in ["대미투자", "미국 투자", "반도체 투자"]):
            for value in _korean_usd_tokens(low):
                facts.add(f"semiconductor_investment_usd:{value}")
        return facts | stages | parties

    if family == "texas_ai_power":
        facts |= stages
        facts |= parties
        for match in re.finditer(r"(\d+(?:\.\d+)?)\s*gw\b", low):
            facts.add(f"texas_power_gw:{match.group(1)}")
        if "20년" in low and any(term in low for term in ["ppa", "전력구매", "전력판매", "계약기간", "장기계약"]):
            facts.add("ppa_years:20")
        return facts

    # 구형/기타 사건축도 기사 URL이 아니라 단계·당사자 변화만 상태로 사용한다.
    return stages | parties | ({official_status} if official_status else set())

def _fact_slot(family: str, fact: str) -> str:
    fixed_prefixes = (
        "nuclear_total_units:", "ap1000_units:", "apr1400_units:",
        "stake_percent:", "funding_amount_usd:", "funding_date:", "funding_wait:",
        "repayment_horizon:", "package_nuclear_units:", "package_usd:",
        "encinal_total_gw:", "encinal_phase1_gw:", "encinal_phase2_gw:", "encinal_project_usd:",
        "ercot_request_gw:", "semiconductor_investment_usd:", "ppa_years:",
        "official_status:",
    )
    for prefix in fixed_prefixes:
        if fact.startswith(prefix):
            return f"{family}|{prefix[:-1]}"
    if fact.startswith("stage:") or fact.startswith("party:") or fact.startswith("governance:"):
        return f"{family}|{fact}"
    # 여러 설비 용량·계약금처럼 동시에 존재할 수 있는 값은 값 자체를 슬롯으로 둔다.
    return f"{family}|{fact}"

def _accepted_facts_for_group(family: str, rows: list[dict]) -> tuple[set[str], dict[str, list[dict]]]:
    support: dict[str, list[dict]] = {}
    for row in rows:
        for fact in _candidate_facts(row, family):
            support.setdefault(fact, []).append(row)

    eligible: dict[str, list[dict]] = {}
    for fact, evidence in support.items():
        sources = {_source_key(r) for r in evidence}
        official = any(_is_official(r) for r in evidence)
        # 공식자료 1건 또는 서로 다른 출처 2곳 이상이 같은 상태값을 지지해야 승격한다.
        if official or len(sources) >= 2:
            eligible[fact] = evidence

    # 한 슬롯에 상충하는 값이 여럿이면 공식성→독립 출처 수→최신성 순으로 하나만 채택한다.
    chosen: dict[str, str] = {}
    for fact, evidence in eligible.items():
        slot = _fact_slot(family, fact)
        score = (
            1 if any(_is_official(r) for r in evidence) else 0,
            len({_source_key(r) for r in evidence}),
            max((_published_key(r) for r in evidence), default=""),
            fact,
        )
        prev = chosen.get(slot)
        if prev is None:
            chosen[slot] = fact
            continue
        prev_evidence = eligible[prev]
        prev_score = (
            1 if any(_is_official(r) for r in prev_evidence) else 0,
            len({_source_key(r) for r in prev_evidence}),
            max((_published_key(r) for r in prev_evidence), default=""),
            prev,
        )
        if score > prev_score:
            chosen[slot] = fact

    accepted = set(chosen.values())

    # 원전 전체 기수보다 노형별 합계가 커지는 상태는 논리적으로 불가능하므로
    # 노형별 수치를 상태값으로 승격하지 않는다. 전체 기수는 별도로 유지한다.
    if family == "nuclear_build":
        def _unit(prefix: str) -> int | None:
            values = [
                int(item.split(":", 1)[1])
                for item in accepted
                if item.startswith(prefix) and item.split(":", 1)[1].isdigit()
            ]
            return values[0] if len(values) == 1 else None

        total = _unit("nuclear_total_units:")
        ap1000 = _unit("ap1000_units:")
        apr1400 = _unit("apr1400_units:")
        if total is not None and ap1000 is not None and apr1400 is not None and ap1000 + apr1400 > total:
            accepted = {
                item for item in accepted
                if not item.startswith(("ap1000_units:", "apr1400_units:"))
            }
            print(
                "nuclear_model_split_inconsistent_suppressed=true "
                f"total={total} ap1000={ap1000} apr1400={apr1400}"
            )

    return accepted, support


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
    labels = {
        "official_status:unconfirmed": "정부 공식상태 미확정",
        "official_status:confirmed": "정부 공식확정",
        "funding_wait:45영업일": "선정 통지 후 최소 45영업일",
        "repayment_horizon:20년": "원리금 회수 기준 20년",
        "ppa_years:20": "전력계약 20년",
    }
    if value in labels:
        return labels[value]
    prefix_labels = {
        "nuclear_total_units:": "원전 전체 ",
        "ap1000_units:": "AP1000 ",
        "apr1400_units:": "APR1400 ",
        "stake_percent:": "웨스팅하우스 지분 ",
        "funding_amount_usd:": "첫 자금 집행 ",
        "funding_date:": "자금 집행일 ",
        "package_nuclear_units:": "패키지 원전 ",
        "package_usd:": "에너지 패키지 ",
        "encinal_total_gw:": "Encinal 총 ",
        "encinal_phase1_gw:": "Encinal 1단계 ",
        "encinal_phase2_gw:": "Encinal 후속 ",
        "encinal_project_usd:": "Encinal 사업비 ",
        "ercot_request_gw:": "ERCOT 요청 ",
        "semiconductor_investment_usd:": "반도체 대미투자 ",
        "alaska_project_usd:": "알래스카 LNG 사업비 ",
        "alaska_mtpa:": "알래스카 LNG ",
        "equipment_contract_usd:": "설비 계약 ",
        "equipment_capacity_gw:": "설비 용량 ",
        "equipment_capacity_mw:": "설비 용량 ",
        "texas_power_gw:": "텍사스 전력 ",
    }
    for prefix, label in prefix_labels.items():
        if value.startswith(prefix):
            raw = value.split(":", 1)[1]
            suffix = ""
            if prefix.endswith("_units:"):
                suffix = "기"
            elif prefix.endswith("_percent:"):
                suffix = "%"
            elif prefix.endswith("_gw:"):
                suffix = "GW"
            elif prefix.endswith("_mw:"):
                suffix = "MW"
            elif prefix.endswith("_mtpa:"):
                suffix = "MTPA"
            elif "_usd:" in prefix:
                suffix = "달러"
            return f"{label}{raw}{suffix}"
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
    if value.startswith("stage:"):
        return value.split(":", 1)[1]
    if value == "governance:board":
        return "이사회 참여"
    if value == "governance:voting":
        return "의결권"
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


def _migration_seed(state: dict) -> None:
    # v2에서 기사 제목의 주변 숫자가 상태로 누적된 오염값을 제거하고,
    # 현재 교차검증된 기준선만 사건 상태로 다시 잡는다.
    buckets = state.setdefault("event_states", {})
    buckets.clear()
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    buckets["nuclear_build"] = {
        "facts": [
            "nuclear_total_units:8",
            "ap1000_units:6",
            "apr1400_units:2",
            "official_status:unconfirmed",
        ],
        "slots": {
            "nuclear_build|nuclear_total_units": "nuclear_total_units:8",
            "nuclear_build|ap1000_units": "ap1000_units:6",
            "nuclear_build|apr1400_units": "apr1400_units:2",
            "nuclear_build|official_status": "official_status:unconfirmed",
        },
        "initialized_at": now,
        "updated_at": now,
        "last_title": "교차검증 기준선: 전체 8기·AP1000 6기·APR1400 2기 보도 / 정부 세부 미확정",
        "last_source": "migration-v3",
        "evidence": [],
    }
    buckets["funding_execution"] = {
        "facts": ["official_status:unconfirmed"],
        "slots": {"funding_execution|official_status": "official_status:unconfirmed"},
        "initialized_at": now,
        "updated_at": now,
        "last_title": "정부 기준선: 송금 규모·시기 미확정",
        "last_source": "migration-v3",
        "evidence": [],
    }

def _load() -> dict:
    global _SHARED_STATE, _BOOTSTRAP_GUARD
    state = _ORIG_LOAD()
    old_version = int(state.get("event_state_guard_version") or 0)
    _BOOTSTRAP_GUARD = old_version < GUARD_VERSION
    state.setdefault("event_states", {})
    if _BOOTSTRAP_GUARD:
        state["event_state_guard_version"] = GUARD_VERSION
        state["event_state_guard_started_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        # 기사/URL 기반 v2 event key와 오염된 사건 상태는 v3에서 재사용하지 않는다.
        state["seen"] = {
            k: v for k, v in (state.get("seen") or {}).items()
            if not str(k).startswith("stateevt_")
        }
        state["semantic_seen"] = {
            k: v for k, v in (state.get("semantic_seen") or {}).items()
            if not str(k).startswith("eventstate_")
        }
        _migration_seed(state)
    _SHARED_STATE = state
    return state

def _bucket(family: str) -> dict:
    assert _SHARED_STATE is not None
    buckets = _SHARED_STATE.setdefault("event_states", {})
    item = buckets.setdefault(
        family,
        {
            "facts": [],
            "slots": {},
            "initialized_at": "",
            "updated_at": "",
            "last_title": "",
            "last_source": "",
            "evidence": [],
        },
    )
    item.setdefault("facts", [])
    item.setdefault("slots", {})
    item.setdefault("initialized_at", "")
    item.setdefault("evidence", [])
    return item

def _apply_state(family: str, evidence_row: dict, facts: set[str], evidence_map: dict[str, list[dict]]) -> set[str]:
    bucket = _bucket(family)
    slots = {str(k): str(v) for k, v in (bucket.get("slots") or {}).items()}
    changed: set[str] = set()
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    if not bucket.get("initialized_at"):
        bucket["initialized_at"] = now

    for fact in sorted(facts):
        slot = _fact_slot(family, fact)
        if slots.get(slot) == fact:
            continue
        slots[slot] = fact
        changed.add(fact)

    if changed:
        bucket["slots"] = dict(sorted(slots.items()))
        bucket["facts"] = sorted(set(slots.values()))
        bucket["updated_at"] = now
        bucket["last_title"] = str(evidence_row.get("title") or "")
        bucket["last_source"] = str(evidence_row.get("source") or "")
        refs = []
        seen_refs = set()
        for fact in sorted(changed):
            for row in evidence_map.get(fact, []):
                key = (_source_key(row), str(row.get("link") or ""))
                if key in seen_refs:
                    continue
                seen_refs.add(key)
                refs.append({
                    "source": str(row.get("source") or ""),
                    "title": str(row.get("title") or ""),
                    "link": str(row.get("link") or ""),
                    "published": str(row.get("published") or ""),
                })
                if len(refs) >= 5:
                    break
            if len(refs) >= 5:
                break
        bucket["evidence"] = refs
    return changed

def _pick_evidence_row(changed: set[str], evidence_map: dict[str, list[dict]], fallback: list[dict]) -> dict:
    candidates: list[dict] = []
    seen = set()
    for fact in changed:
        for row in evidence_map.get(fact, []):
            key = (str(row.get("link") or ""), str(row.get("title") or ""))
            if key in seen:
                continue
            seen.add(key)
            candidates.append(row)
    if not candidates:
        candidates = list(fallback)
    candidates.sort(
        key=lambda r: (
            1 if _is_official(r) else 0,
            _published_key(r),
        ),
        reverse=True,
    )
    return candidates[0] if candidates else {}

def _collapse_rows(rows: list[dict]) -> list[dict]:
    assert _SHARED_STATE is not None
    now = dt.datetime.now(dt.timezone.utc)

    # URL/기사 단위 중복 제거는 수집 정리에만 사용한다. 알림 판정 key에는 쓰지 않는다.
    unique: dict[str, dict] = {}
    for row in rows:
        evidence_key = hashlib.sha256(
            f"{_norm(str(row.get('title') or ''))}|{_source_key(row)}".encode("utf-8")
        ).hexdigest()[:20]
        unique.setdefault(evidence_key, row)

    groups: dict[str, list[dict]] = {}
    suppressed_unclassified = 0
    for row in unique.values():
        family = _family(row)
        if not family:
            suppressed_unclassified += 1
            continue
        groups.setdefault(family, []).append(row)

    # v3 전환 첫 실행은 현재 주제·사건 상태만 기준선으로 흡수하고 과거 기사를 재발송하지 않는다.
    if _BOOTSTRAP_GUARD:
        for family, family_rows in groups.items():
            accepted, evidence_map = _accepted_facts_for_group(family, family_rows)
            if not accepted:
                continue
            evidence_row = _pick_evidence_row(accepted, evidence_map, family_rows)
            _apply_state(family, evidence_row, accepted, evidence_map)
        _SHARED_STATE["event_state_guard_baselined_at"] = now.isoformat()
        print(f"event_state_guard_v3_baseline_families={len(groups)}")
        return []

    out: list[dict] = []
    for family, family_rows in sorted(groups.items()):
        accepted, evidence_map = _accepted_facts_for_group(family, family_rows)
        if not accepted:
            continue

        evidence_row = _pick_evidence_row(accepted, evidence_map, family_rows)

        # 정부 공식상태가 '미확정'인 동안 AP1000/APR1400 노형별 기수 변경은
        # 언론 2곳만으로 상태 전이시키지 않는다. 정부·발주처 등 공식 근거가
        # 해당 노형별 새 기수를 직접 확인한 경우에만 기존 기준선을 바꾼다.
        if family == "nuclear_build":
            bucket = _bucket(family)
            slots = {str(k): str(v) for k, v in (bucket.get("slots") or {}).items()}
            official_unconfirmed = (
                slots.get("nuclear_build|official_status") == "official_status:unconfirmed"
                or "official_status:unconfirmed" in set(bucket.get("facts") or [])
            )
            if official_unconfirmed:
                filtered = set(accepted)
                for fact in list(filtered):
                    if not fact.startswith(("ap1000_units:", "apr1400_units:")):
                        continue
                    slot = _fact_slot(family, fact)
                    previous = slots.get(slot)
                    if previous and previous != fact:
                        evidence = evidence_map.get(fact, [])
                        if not any(_is_official(row) for row in evidence):
                            filtered.discard(fact)
                            print(
                                "nuclear_model_transition_pending_official=true "
                                f"previous={previous} candidate={fact}"
                            )
                accepted = filtered
                if not accepted:
                    continue
                evidence_row = _pick_evidence_row(accepted, evidence_map, family_rows)

        changed = _apply_state(family, evidence_row, accepted, evidence_map)
        if not changed:
            continue

        current = set(str(x) for x in _bucket(family).get("facts") or [])
        state_key = _event_key(family, current)
        label = _FAMILY_LABELS.get(family, family.replace("_", " "))
        visible = [_human_fact(x) for x in sorted(changed)]

        synthetic = dict(evidence_row)
        synthetic["title"] = (
            f"[상태 변화] {label} — " + " · ".join(visible[:6])
            if visible else f"[신규 사건] {label}"
        )
        synthetic["_state_guard_family"] = family
        synthetic["_state_guard_key"] = state_key
        synthetic["_state_guard_delta"] = sorted(changed)
        synthetic["_state_guard_evidence"] = _bucket(family).get("evidence") or []
        # 기사 제목·URL은 근거일 뿐 상태 key/변화판정에는 포함되지 않는다.
        synthetic["_state_guard_evidence_title"] = str(evidence_row.get("title") or "")
        out.append(synthetic)

        if len(out) >= 5:
            break

    if suppressed_unclassified:
        print(f"event_state_guard_unclassified_suppressed={suppressed_unclassified}")
    print(f"event_state_changes={len(out)}")
    return out

def _self_test() -> int:
    nuclear_rows = [
        {
            "title": "미국 원전 8기 검토…AP1000 6기·APR1400 2기",
            "source": "Reuters",
            "link": "https://example.com/a",
            "published": "2026-09-20T00:00:00+00:00",
        },
        {
            "title": "美 원전 8기 협의, AP1000 6기 APR1400 2기 거론",
            "source": "뉴스1",
            "link": "https://example.com/b",
            "published": "2026-09-20T00:05:00+00:00",
        },
    ]
    accepted, _ = _accepted_facts_for_group("nuclear_build", nuclear_rows)
    expected = {"nuclear_total_units:8", "ap1000_units:6", "apr1400_units:2"}
    if not expected.issubset(accepted):
        raise RuntimeError(f"nuclear state parsing failed: {accepted}")
    if "ap1000_units:8" in accepted or "apr1400_units:8" in accepted:
        raise RuntimeError(f"model unit double count regression: {accepted}")

    ambiguous_total_rows = [
        {
            "title": "대미투자 원전 AP1000·APR1400 포함 총 8기 건설 보도",
            "source": "한국경제",
            "link": "https://www.hankyung.com/example",
            "published": "2026-09-20T00:10:00+00:00",
        },
        {
            "title": "미국 원전 AP1000과 APR1400 포함 전체 8기 협의",
            "source": "머니투데이",
            "link": "https://www.mt.co.kr/example",
            "published": "2026-09-20T00:11:00+00:00",
        },
    ]
    accepted, _ = _accepted_facts_for_group("nuclear_build", ambiguous_total_rows)
    if "nuclear_total_units:8" not in accepted:
        raise RuntimeError(f"ambiguous total units not retained: {accepted}")
    if any(x.startswith(("ap1000_units:", "apr1400_units:")) for x in accepted):
        raise RuntimeError(f"ambiguous total leaked into model split: {accepted}")

    inconsistent_rows = [
        {
            "title": "미국 원전 8기, AP1000 6기·APR1400 8기 보도",
            "source": "한국경제",
            "link": "https://www.hankyung.com/bad-a",
            "published": "2026-09-20T00:12:00+00:00",
        },
        {
            "title": "원전 8기, AP1000 6기 APR1400 8기라는 보도",
            "source": "뉴스1",
            "link": "https://www.news1.kr/bad-b",
            "published": "2026-09-20T00:13:00+00:00",
        },
    ]
    accepted, _ = _accepted_facts_for_group("nuclear_build", inconsistent_rows)
    if "nuclear_total_units:8" not in accepted:
        raise RuntimeError(f"inconsistent total units lost: {accepted}")
    if any(x.startswith(("ap1000_units:", "apr1400_units:")) for x in accepted):
        raise RuntimeError(f"inconsistent model split survived: {accepted}")

    same_publisher_rows = [
        {
            "title": "APR1400 8기 검토 보도",
            "source": "한국경제",
            "link": "https://www.hankyung.com/article/example",
            "published": "2026-09-20T00:14:00+00:00",
        },
        {
            "title": "APR1400 8기 검토 보도",
            "source": "네이버",
            "link": "https://n.news.naver.com/mnews/article/015/0000000000",
            "published": "2026-09-20T00:15:00+00:00",
        },
    ]
    accepted, _ = _accepted_facts_for_group("nuclear_build", same_publisher_rows)
    if "apr1400_units:8" in accepted:
        raise RuntimeError(f"same publisher was double-counted as independent confirmation: {accepted}")

    official_funding = [{
        "title": "대미투자 3,500억달러 약속…첫 송금 규모·시기는 확정된 바 없습니다",
        "source": "대한민국 정책브리핑",
        "link": "https://example.com/official",
        "published": "2026-09-20T01:00:00+00:00",
    }]
    accepted, _ = _accepted_facts_for_group("funding_execution", official_funding)
    if accepted != {"official_status:unconfirmed"}:
        raise RuntimeError(f"funding background number leaked into state: {accepted}")

    single_article = [{
        "title": "텍사스 AI 전력사업 20년 장기계약 검토",
        "source": "한국경제",
        "link": "https://example.com/one",
        "published": "2026-09-20T02:00:00+00:00",
    }]
    accepted, _ = _accepted_facts_for_group("texas_ai_power", single_article)
    if accepted:
        raise RuntimeError(f"single article became event state: {accepted}")

    ercot = [{
        "title": "ERCOT 데이터센터 계통연계 요청 474GW",
        "source": "ERCOT",
        "link": "https://example.com/ercot",
        "published": "2026-09-20T03:00:00+00:00",
    }]
    accepted, _ = _accepted_facts_for_group("ercot_large_load", ercot)
    if "ercot_request_gw:474" not in accepted or any("474기" in x for x in accepted):
        raise RuntimeError(f"ERCOT unit contamination regression: {accepted}")

    print("state_event_guard_self_test=passed")
    return 0


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
    if "--self-test" in sys.argv:
        raise SystemExit(_self_test())
    raise SystemExit(main())
