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

GUARD_VERSION = 4

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

    # 기사 제목에 기관·기업명이 들어갔다는 이유만으로 '공식자료'로 승격하지 않는다.
    # 발행 출처명 또는 실제 링크 도메인이 공식기관/공식회사인 경우만 fallback 공식으로 본다.
    source_blob = _norm(str(row.get("source") or ""))
    link_blob = _norm(str(row.get("link") or ""))
    official_source_tokens = [
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
        "white house",
        "백악관",
        "sec",
        "westinghouse",
        "cameco",
        "brookfield",
        "한국전력",
        "한국수력원자력",
        "kepco",
        "khnp",
    ]
    official_domains = [
        "korea.kr", "motir.go.kr", "moef.go.kr", "msit.go.kr",
        "whitehouse.gov", "sec.gov", "ercot.com", "puc.texas.gov",
        "westinghousenuclear.com", "cameco.com", "brookfield.com",
        "kepco.co.kr", "khnp.co.kr",
    ]
    return (
        any(token in source_blob for token in official_source_tokens)
        or any(domain in link_blob for domain in official_domains)
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
            "2천억달러",
            "2000억달러",
            "200 billion",
            "원전 8기",
            "원전8기",
            "eight nuclear",
            "첫 사업",
            "첫사업",
            "첫 사업군",
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
        r"(\d+(?:\.\d+)?(?:천|백)?)\s*(억|조)\s*(?:달러|불)", low
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
        ("발표실행", ["발표했다", "공개했다", "공식 발표했다", "unveils", "unveiled", "announced"]),
        ("발표예정", ["발표 가능성", "발표 예상", "발표 예정", "expected to announce", "set to announce", "could announce"]),
        ("체결", ["체결", "본계약", "계약 체결", "signed agreement"]),
        ("수주발주", ["수주", "발주", "구매주문", "purchase order"]),
        ("승인", ["승인", "approved", "벤더 승인", "vendor approval"]),
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

    # 한국어 기사 제목은 실제 발표 후에도 단순히 '발표'라고 쓰는 경우가 많다.
    # 다만 예정/예고/전망 기사와 혼동하지 않도록 트럼프 직접 발표 문맥 + 미래표현 부재일 때만 실행 단계로 본다.
    if "트럼프" in low and "발표" in low and not any(
        term in low
        for term in ["발표 예정", "발표 예상", "발표 가능성", "발표 전망", "발표 예고", "앞두고", "곧 발표", "발표할", "발표할 듯", "발표할 것으로"]
    ):
        facts.add("stage:발표실행")

    if "이사회" in low or "board seat" in low:
        facts.add("governance:board")
    if "의결권" in low or "voting right" in low:
        facts.add("governance:voting")

    parties = [
        ("westinghouse", ["웨스팅하우스", "westinghouse"]),
        ("khnp", ["한수원", "한국수력원자력", "khnp"]),
        ("kepco", ["한전", "한국전력", "kepco"]),
        ("doosan", ["두산에너빌리티", "doosan enerbility"]),
        ("hyundaiec", ["현대건설", "hyundai e&c", "hyundai engineering & construction"]),
        ("beomhanmecatec", ["범한메카텍", "beomhan mecatec"]),
        ("bhi", ["비에이치아이", "bhi"]),
        ("gevernova", ["ge vernova"]),
        ("siemens", ["siemens energy"]),
        ("bw", ["babcock & wilcox", "b&w"]),
        ("baseelectron", ["base electron"]),
        ("applieddigital", ["applied digital"]),
        ("posco", ["포스코", "posco"]),
        ("kogas", ["한국가스공사", "kogas"]),
        ("glenfarne", ["glenfarne"]),
        ("kumkang", ["금강공업", "kumkang kind"]),
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
        term in low for term in ["공식 확정", "최종 확정", "확정 발표", "공식 발표", "announces", "announced", "fact sheet", "approved", "signed"]
    ):
        return "official_status:confirmed"
    return ""

def _korean_usd_tokens(low: str) -> list[str]:
    out: list[str] = []
    for match in re.finditer(r"(\d+(?:\.\d+)?(?:천|백)?)\s*(억|조)\s*(?:달러|불)", low):
        out.append(f"{match.group(1)}{match.group(2)}")
    for match in re.finditer(r"\$\s*(\d+(?:\.\d+)?)\s*(billion|million|trillion)?", low):
        out.append(f"{match.group(1)}{match.group(2) or ''}")
    return list(dict.fromkeys(out))

def _usd_billion_mentions(low: str) -> list[tuple[str, int, int]]:
    out: list[tuple[str, int, int]] = []
    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*(억|조)\s*(?:달러|불)", low):
        number = float(match.group(1))
        value = number / 10.0 if match.group(2) == "억" else number * 1000.0
        normalized = f"{value:.3f}".rstrip("0").rstrip(".")
        out.append((normalized, match.start(), match.end()))
    for match in re.finditer(r"\$?\s*(\d+(?:\.\d+)?)\s*(billion|million|trillion)\b", low):
        number = float(match.group(1))
        unit = match.group(2)
        if unit == "million":
            number /= 1000.0
        elif unit == "trillion":
            number *= 1000.0
        normalized = f"{number:.3f}".rstrip("0").rstrip(".")
        out.append((normalized, match.start(), match.end()))
    dedup: list[tuple[str, int, int]] = []
    seen: set[tuple[str, int, int]] = set()
    for item in out:
        if item not in seen:
            dedup.append(item)
            seen.add(item)
    return dedup


def _usd_billion_values(low: str) -> list[str]:
    out: list[str] = []
    for value, _, _ in _usd_billion_mentions(low):
        if value not in out:
            out.append(value)
    return out


def _alaska_specific_usd_values(low: str) -> list[str]:
    out: list[str] = []
    broad_terms = (
        "대미투자", "대미 투자", "전략투자", "전략 투자", "전략적 투자",
        "investment plan", "strategic investment", "investment package", "total investment",
    )
    for value, start, end in _usd_billion_mentions(low):
        before = low[max(0, start - 60):start]
        after = low[end:min(len(low), end + 70)]
        specific = False
        if "알래스카" in before[-40:] or "alaska lng" in before[-60:]:
            specific = True
        if re.search(r"(?:investment|funding|spending|use).{0,28}alaska(?:\s+lng)?", after):
            specific = True
        alaska_pos = after.find("알래스카")
        if 0 <= alaska_pos <= 45:
            bridge = after[:alaska_pos]
            if not any(term in bridge for term in broad_terms):
                specific = True
        if specific and value not in out:
            out.append(value)
    return out


def _overall_investment_usd_values(low: str) -> list[str]:
    alaska_values = set(_alaska_specific_usd_values(low))
    out: list[str] = []
    broad_terms = (
        "대미투자", "대미 투자", "전략투자", "전략 투자", "전략적 투자",
        "investment plan", "strategic investment", "investment package", "total investment",
    )
    for value, start, end in _usd_billion_mentions(low):
        if value in alaska_values:
            continue
        window = low[max(0, start - 45):min(len(low), end + 45)]
        if any(term in window for term in broad_terms) and value not in out:
            out.append(value)
    return out


def _explicit_model_units(low: str, model: str) -> set[str]:
    escaped = re.escape(model)

    # 같은 제목에 "원전 8기 AP1000 6기 APR1400 2기"처럼 여러 숫자·노형이
    # 연속으로 나오면 역방향 정규식이 앞 노형의 숫자를 다음 노형에 잘못 붙일 수 있다.
    # 노형→기수 표기가 있으면 그것만 우선 사용하고, 없을 때만 기수→노형을 허용한다.
    forward = {
        match.group(1)
        for match in re.finditer(rf"{escaped}\s*(?:형|노형)?\s*(\d+)\s*기", low)
    }
    if forward:
        return forward

    return {
        match.group(1)
        for match in re.finditer(rf"(?<![a-z0-9])(\d+)\s*기\s*(?:의\s*)?{escaped}\b", low)
    }

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
    for match in re.finditer(r"(\d+(?:\.\d+)?(?:천|백)?)\s*(억|조)\s*(?:달러|불)", low):
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
        if _is_official(row) and any(term in low for term in ["원전 프레임워크", "project power"]):
            if any(term in low for term in ["합의", "agreed", "agreement"]):
                facts.add("nuclear_framework_status:agreed")
                facts.add("nuclear_project_status:individual_projects_pending")
            usd_values = set(_usd_billion_values(low))
            # 총재원·건설비·예비비·선지급금을 같은 슬롯에 섞지 않는다.
            if "120" in usd_values:
                facts.add("nuclear_framework_usd_b:120")
            if "100" in usd_values and any(term in low for term in ["건설비", "건설비용", "overnight cost", "construction cost"]):
                facts.add("nuclear_construction_cost_usd_b:100")
            if "20" in usd_values and any(term in low for term in ["예비비", "contingency"]):
                facts.add("nuclear_contingency_usd_b:20")
            upfront_terms = ["선지급", "먼저 지급", "선제 지급", "upfront payment", "advance payment", "prepayment"]
            longlead_terms = ["장주기", "장납기", "long lead", "long-lead"]
            if "10" in usd_values and any(term in low for term in upfront_terms):
                facts.add("nuclear_upfront_payment_usd_b:10")
                executed_upfront = any(
                    term in low
                    for term in [
                        "선지급 완료", "지급 완료", "송금 완료", "집행 완료",
                        "선지급했다", "지급했다", "송금했다", "집행했다",
                        "upfront payment completed", "advance payment completed",
                        "prepayment completed", "paid", "transferred", "disbursed",
                    ]
                )
                facts.add(
                    "nuclear_upfront_payment_status:executed"
                    if executed_upfront
                    else "nuclear_upfront_payment_status:conditional"
                )
            if any(term in low for term in longlead_terms) and any(
                term in low for term in ["구매주문", "구매 주문", "발주 완료", "발주했다", "purchase order", "ordered", "po issued"]
            ):
                facts.add("nuclear_longlead_order_status:ordered")
        if _is_official(row):
            source_low = _norm(str(row.get("source") or ""))
            project_power_context = (
                "project power" in low
                or "한미 원전" in low
                or (
                    any(model in low for model in ["ap1000", "apr1400"])
                    and any(place in low for place in ["미국", "united states", "u.s.", "usg", "korea", "한국"])
                )
            )

            # Project Power는 '프레임워크 합의'와 실제 실행단계를 분리한다.
            # 실행단계 승격은 Project Power/미국 배치 문맥 + 공식자료가 동시에 확인될 때만 허용한다.
            if project_power_context and any(term in low for term in [
                "framework signed", "framework has been signed", "signed the framework",
                "프레임워크 서명 완료", "프레임워크에 서명했다", "프레임워크 공식 서명",
            ]):
                facts.add("nuclear_framework_signature_status:signed")

            if project_power_context and any(term in low for term in [
                "definitive agreement signed", "definitive agreements signed",
                "definitive agreements executed", "최종 계약 체결", "본계약 체결",
            ]):
                facts.add("nuclear_definitive_agreement_status:signed")

            if project_power_context and any(term in low for term in [
                "specific site selected", "specific sites selected", "specific site identified",
                "specific federal site selected", "specific federal site identified",
                "개별 부지 확정", "부지 선정 완료", "부지 확정", "사업 부지 선정",
            ]):
                facts.add("nuclear_federal_site_status:selected")

            if project_power_context and any(term in low for term in [
                "waiver agreement signed", "waiver executed", "waiver finalized",
                "one-time waiver approved", "예외 합의 체결", "예외 적용 확정",
                "일회성 예외 확정", "타협협정 예외 체결",
            ]):
                facts.add("nuclear_settlement_waiver_status:executed")

            if project_power_context and any(term in low for term in [
                "financial close", "financing closed", "financing finalized",
                "금융종결", "자금조달 종결", "금융약정 체결",
            ]):
                facts.add("nuclear_financing_status:closed")

            if project_power_context and any(term in low for term in [
                "combined license approved", "combined license issued",
                "construction permit approved", "construction permit issued",
                "복합허가 승인", "건설허가 승인", "건설허가 발급",
            ]):
                facts.add("nuclear_regulatory_status:approved")

            if (
                "ap1000" in low
                and any(term in low for term in ["2기", "two ap1000", "two units"])
                and any(term in low for term in [
                    "epc contract signed", "epc agreement signed", "epc 계약 체결", "설계·조달·시공 계약 체결",
                ])
            ):
                facts.add("nuclear_phase1_epc_status:signed")

            award_terms = [
                "purchase order", "po issued", "contract awarded", "supply contract",
                "공급계약", "구매주문", "발주", "수주", "공급사 선정",
            ]
            qualify_terms = [
                "vendor approval", "vendor qualification", "qualified supplier",
                "공급사 승인", "벤더 승인", "품질 검증 완료", "공급자 등록",
            ]
            supplier_tokens = {
                "doosan": ["두산에너빌리티", "doosan enerbility"],
                "hyundaiec": ["현대건설", "hyundai e&c", "hyundai engineering & construction"],
                "beomhanmecatec": ["범한메카텍", "beomhan mecatec"],
                "bhi": ["비에이치아이", "bhi"],
            }
            if project_power_context:
                for supplier, tokens in supplier_tokens.items():
                    if not any(token in low for token in tokens):
                        continue
                    if any(term in low for term in award_terms):
                        facts.add(f"nuclear_supplier_award:{supplier}")
                    if any(term in low for term in qualify_terms):
                        facts.add(f"nuclear_vendor_qualification:{supplier}")

            if any(term in low for term in ["non-binding", "nonbinding", "비구속"]):
                facts.add("nuclear_framework_binding:nonbinding")
            if any(term in low for term in ["definitive agreements pending", "definitive agreement pending", "subject to definitive agreements", "final negotiations pending", "최종 협상 필요", "본계약 후속 확정"]):
                facts.add("nuclear_definitive_agreement_status:pending")
            if any(term in low for term in ["federal sites planned", "federal sites designated", "연방정부 부지 예정", "연방정부 지정 부지"]):
                facts.add("nuclear_federal_site_status:planned")
            if (
                "ap1000" in low
                and any(term in low for term in ["beginning with ap1000 2기", "starting with ap1000 2기", "ap1000 2기부터", "1단계 ap1000 2기"])
            ):
                facts.add("nuclear_initial_ap1000_units:2")
            if (
                "waiver" in low
                and "2025" in low
                and any(term in low for term in ["contemplated", "would allow", "예외 적용 검토", "일회성 예외"])
            ):
                facts.add("nuclear_settlement_waiver_status:contemplated")
            if (
                "apr1400" in low
                and "westinghouse" in low
                and any(term in low for term in ["20억달러", "$2 billion", "us$2 billion", "2 billion"])
                and any(term in low for term in ["per apr1400", "reactor당", "기당", "per reactor"])
            ):
                facts.add("nuclear_apr1400_wh_value_per_unit_usd_b:2")
            if (
                "ap1000" in low
                and any(term in low for term in ["한국 시공사", "한국 건설사", "korean construction"])
                and any(term in low for term in ["기자재", "equipment", "supply chain"])
                and any(term in low for term in ["참여", "include", "participat"])
            ):
                facts.add("nuclear_korean_ap1000_supply_chain:included")
            if any(term in source_low for term in ["westinghouse", "cameco", "brookfield"]):
                facts.add("nuclear_counterparty_confirmation:official")
        facts |= parties
        facts |= stages
        return facts

    if family == "westinghouse_stake":
        for match in re.finditer(r"(\d+(?:\.\d+)?)\s*(?:~|-|to)\s*(\d+(?:\.\d+)?)\s*%", low):
            facts.add(f"stake_range_percent:{match.group(1)}~{match.group(2)}")
        for pattern in [
            r"(?:지분(?:율)?|stake)\D{0,18}(\d+(?:\.\d+)?)\s*%",
            r"(\d+(?:\.\d+)?)\s*%\D{0,18}(?:지분(?:율)?|stake)",
        ]:
            for match in re.finditer(pattern, low):
                facts.add(f"stake_percent:{match.group(1)}")
        if _is_official(row):
            if any(term in low for term in ["cornerstone equity investment", "potential equity investment", "지분 투자 예정", "지분 투자 검토"]):
                facts.add("stake_status:contemplated")
            if any(term in low for term in ["subject to definitive agreements", "definitive agreements pending", "최종 계약 필요", "본계약 후속 확정"]):
                facts.add("equity_definitive_agreement_status:pending")
            if "due diligence" in low or "실사 필요" in low:
                facts.add("equity_due_diligence_status:pending")
            if any(term in low for term in ["regulatory approvals", "regulatory approval", "규제 승인 필요"]):
                facts.add("equity_regulatory_approval_status:pending")
            if any(term in low for term in ["definitive agreement signed", "definitive agreements signed", "최종 계약 체결"]):
                facts.add("equity_definitive_agreement_status:signed")
            if any(term in low for term in ["due diligence completed", "실사 완료"]):
                facts.add("equity_due_diligence_status:completed")
            if any(term in low for term in ["regulatory approval obtained", "regulatory approvals obtained", "규제 승인 완료"]):
                facts.add("equity_regulatory_approval_status:approved")
            if any(term in low for term in ["equity investment closed", "transaction closed", "지분 취득 완료", "투자 종결"]):
                facts.add("equity_closing_status:completed")
        facts |= {x for x in raw if x.startswith("governance:")}
        facts |= parties
        facts |= stages
        return facts

    if family == "funding_execution":
        if "45영업일" in low:
            facts.add("funding_wait:45영업일")
        if any(term in low for term in ["송금", "납입", "집행", "capital call"]):
            future_terms = [
                "예정", "가능성", "가능", "검토", "협의", "요구", "임박", "계획",
                "이달 말", "월말", "곧 송금", "송금할", "납입할", "집행할",
            ]
            executed_terms = [
                "송금 완료", "납입 완료", "집행 완료", "송금했다", "납입했다", "집행했다",
                "송금됐다", "송금돼", "송금해", "첫 송금", "첫 투자금", "첫 자금 집행",
                "투자금 송금", "자금 송금",
            ]
            future = any(term in low for term in future_terms)
            executed = any(term in low for term in executed_terms) and not future
            if executed:
                facts.add("stage:송금집행")
            elif future:
                facts.add("stage:송금예정")

            for value in _money_near_anchor(
                low,
                ("첫 송금", "첫 투자금", "첫 자금 집행", "첫 납입", "초기 집행", "자금 납입", "투자금 송금", "capital call"),
            ):
                facts.add(f"funding_amount_usd:{value}")
            for match in re.finditer(r"(20\d{2})[-./년]\s*(\d{1,2})[-./월]\s*(\d{1,2})", low):
                window = low[max(0, match.start()-55): min(len(low), match.end()+55)]
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
        for value in _overall_investment_usd_values(low):
            facts.add(f"package_overall_usd_b:{value}")
        facts |= stages
        return facts | parties

    if family == "encinal":
        if "6.3gw" in low or "엔시날" in low or "encinal" in low or "project star" in low:
            if "6.3gw" in low:
                facts.add("encinal_total_gw:6.3")
            for match in re.finditer(r"(\d+(?:\.\d+)?)\s*mw\b", low):
                facts.add(f"encinal_total_mw:{match.group(1)}")
            if "1.4gw" in low:
                facts.add("encinal_phase1_gw:1.4")
            if "4.9gw" in low:
                facts.add("encinal_phase2_gw:4.9")
            if any(term in low for term in ["사업비", "총사업비", "project cost", "project costs", "estimated cost"]):
                for value in _usd_billion_values(low):
                    facts.add(f"encinal_project_cost_usd_b:{value}")
            if _is_official(row) and any(term in low for term in ["제1호", "제 1 호", "1호", "공식 추진", "project star"]):
                facts.add("encinal_status:confirmed_first")
            if "2029" in low:
                facts.add("encinal_phase1_year:2029")
            if "2032" in low:
                facts.add("encinal_full_year:2032")
            facts |= stages
        return facts | parties

    if family == "alaska_lng":
        for match in re.finditer(r"(\d+(?:\.\d+)?)\s*mtpa\b", low):
            facts.add(f"alaska_mtpa:{match.group(1)}")
        if _is_official(row) and any(term in low for term in ["검토 착수", "검토에 착수", "project north"]):
            facts.add("alaska_bilateral_status:review_started")
        alaska_usd = _alaska_specific_usd_values(low)
        if any(term in low for term in ["사업비", "총사업비", "project cost", "estimated cost", "project costs"]):
            for value in alaska_usd:
                facts.add(f"alaska_project_cost_usd_b:{value}")
        if (
            any(term in low for term in ["한국", "south korea", "korean"])
            and any(term in low for term in ["투자", "investment"])
        ):
            for value in alaska_usd:
                if _is_official(row) and official_status == "official_status:confirmed":
                    facts.add(f"alaska_korea_investment_usd_b:{value}")
                else:
                    facts.add(f"alaska_reported_amount_usd_b:{value}")
        facts |= stages
        # 금강공업의 API 5L X70 인증 연관성만으로 프로젝트 공급사 상태를 올리지 않는다.
        # 공급계약/선정/승인/공식확정처럼 프로젝트 단계가 실제 상승한 경우에만 당사자로 채택한다.
        if "party:kumkang" in parties and not any(
            stage in stages
            for stage in ["stage:수주발주", "stage:체결", "stage:선정", "stage:승인", "stage:공식확정"]
        ):
            parties.discard("party:kumkang")
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
    if family == "westinghouse_stake" and fact.startswith(("stake_percent:", "stake_range_percent:")):
        return f"{family}|stake_equity_percent"
    fixed_prefixes = (
        "nuclear_total_units:", "ap1000_units:", "apr1400_units:", "nuclear_framework_status:", "nuclear_project_status:", "nuclear_framework_usd_b:",
        "nuclear_framework_binding:", "nuclear_definitive_agreement_status:", "nuclear_federal_site_status:",
        "nuclear_initial_ap1000_units:", "nuclear_settlement_waiver_status:", "nuclear_apr1400_wh_value_per_unit_usd_b:",
        "nuclear_korean_ap1000_supply_chain:", "nuclear_counterparty_confirmation:",
        "nuclear_construction_cost_usd_b:", "nuclear_contingency_usd_b:", "nuclear_upfront_payment_usd_b:",
        "nuclear_upfront_payment_status:", "nuclear_longlead_order_status:",
        "nuclear_framework_signature_status:", "nuclear_financing_status:", "nuclear_regulatory_status:",
        "nuclear_phase1_epc_status:",
        "stake_percent:", "stake_range_percent:", "stake_status:", "equity_definitive_agreement_status:",
        "equity_due_diligence_status:", "equity_regulatory_approval_status:", "equity_closing_status:", "funding_amount_usd:", "funding_date:", "funding_wait:",
        "repayment_horizon:", "package_nuclear_units:", "package_overall_usd_b:",
        "encinal_total_gw:", "encinal_total_mw:", "encinal_phase1_gw:", "encinal_phase2_gw:",
        "encinal_project_usd:", "encinal_project_cost_usd_b:", "encinal_status:", "encinal_phase1_year:", "encinal_full_year:",
        "alaska_project_cost_usd_b:", "alaska_korea_investment_usd_b:", "alaska_reported_amount_usd_b:", "alaska_bilateral_status:",
        "ercot_request_gw:", "semiconductor_investment_usd:", "ppa_years:",
        "official_status:",
    )
    for prefix in fixed_prefixes:
        if fact.startswith(prefix):
            return f"{family}|{prefix[:-1]}"
    if fact in {"stage:발표예정", "stage:발표실행"}:
        return f"{family}|stage:announcement"
    if family == "funding_execution" and fact in {"stage:송금예정", "stage:송금집행"}:
        return f"{family}|stage:funding"
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

    # 미국 대미투자 원전의 기수·노형 구성은 정부가 공식적으로
    # "구체적인 사항은 아직 정해지지 않았다"고 밝힌 상태다.
    # 따라서 기사 2건 이상이 같은 숫자를 반복해도 원전 기수·노형의
    # 상태 전이로 승격하지 않는다. 공식 자료가 해당 숫자를 확정했을 때만 바꾼다.
    if family == "nuclear_build":
        quantitative = {
            item for item in accepted
            if item.startswith(("nuclear_total_units:", "ap1000_units:", "apr1400_units:"))
        }
        framework_official = "nuclear_framework_status:agreed" in accepted
        for item in list(quantitative):
            evidence = eligible.get(item, [])
            official_support = framework_official or any(
                _is_official(row)
                and _official_status_fact(row) == "official_status:confirmed"
                for row in evidence
            )
            if not official_support:
                accepted.discard(item)
                print(f"nuclear_unconfirmed_quantitative_suppressed=true fact={item}")

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
        "nuclear_framework_status:agreed": "한미 원전 프레임워크 합의",
        "nuclear_project_status:individual_projects_pending": "개별 원전 프로젝트 후속 확정 필요",
        "nuclear_framework_binding:nonbinding": "프레임워크 비구속",
        "nuclear_definitive_agreement_status:pending": "최종 계약 후속 협상 필요",
        "nuclear_federal_site_status:planned": "연방정부 부지 배치 예정·개별 부지 미확정",
        "nuclear_initial_ap1000_units:2": "1단계 AP1000 2기",
        "nuclear_settlement_waiver_status:contemplated": "2025 타협협정 일회성 예외 검토",
        "nuclear_korean_ap1000_supply_chain:included": "AP1000 한국 시공·기자재 참여 방향 포함",
        "nuclear_counterparty_confirmation:official": "Westinghouse·Cameco 측 공식 확인",
        "nuclear_upfront_payment_status:conditional": "최대 100억달러 선지급은 조건부 협의 단계",
        "nuclear_upfront_payment_status:executed": "원전 선지급 실제 집행 확인",
        "nuclear_longlead_order_status:ordered": "장주기 품목 구매주문·발주 확인",
        "nuclear_framework_signature_status:signed": "한미 원전 프레임워크 공식 서명 완료",
        "nuclear_financing_status:closed": "원전 사업 금융종결 확인",
        "nuclear_regulatory_status:approved": "원전 사업 건설·복합허가 승인 확인",
        "nuclear_phase1_epc_status:signed": "1단계 AP1000 2기 EPC 계약 체결",
        "nuclear_settlement_waiver_status:executed": "2025 타협협정 일회성 예외 최종 체결",
        "nuclear_federal_site_status:selected": "개별 원전 부지 선정·확정",
        "nuclear_definitive_agreement_status:signed": "Project Power 최종 계약 체결",
        "stake_status:contemplated": "Westinghouse 지분투자 프레임워크 포함·미종결",
        "equity_definitive_agreement_status:pending": "지분 최종계약 미체결",
        "equity_due_diligence_status:pending": "지분투자 실사 필요",
        "equity_regulatory_approval_status:pending": "지분투자 규제승인 필요",
        "equity_definitive_agreement_status:signed": "지분 최종계약 체결",
        "equity_due_diligence_status:completed": "지분투자 실사 완료",
        "equity_regulatory_approval_status:approved": "지분투자 규제승인 완료",
        "equity_closing_status:completed": "지분투자 종결",
        "encinal_status:confirmed_first": "대미투자 1호 공식 확정",
        "alaska_bilateral_status:review_started": "한미 공식상태 검토 착수",
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
        "nuclear_framework_usd_b:": "원전 프레임워크 총재원 ",
        "nuclear_construction_cost_usd_b:": "원전 건설비 ",
        "nuclear_contingency_usd_b:": "원전 예비비 ",
        "nuclear_upfront_payment_usd_b:": "원전 선지급 한도 ",
        "nuclear_apr1400_wh_value_per_unit_usd_b:": "APR1400 1기당 Westinghouse 예상 가치 ",
        "stake_percent:": "웨스팅하우스 지분 ",
        "stake_range_percent:": "웨스팅하우스 지분 범위 ",
        "funding_amount_usd:": "첫 자금 집행 ",
        "funding_date:": "자금 집행일 ",
        "package_nuclear_units:": "패키지 원전 ",
        "package_overall_usd_b:": "대미투자 전체/전략 규모 ",
        "encinal_total_gw:": "Encinal 총 ",
        "encinal_total_mw:": "Encinal 총 ",
        "encinal_phase1_gw:": "Encinal 1단계 ",
        "encinal_phase2_gw:": "Encinal 후속 ",
        "encinal_project_usd:": "Encinal 사업비 ",
        "encinal_project_cost_usd_b:": "Encinal 공식 사업비 ",
        "encinal_phase1_year:": "Encinal 1단계 상업운전 ",
        "encinal_full_year:": "Encinal 전체 가동 ",
        "ercot_request_gw:": "ERCOT 요청 ",
        "semiconductor_investment_usd:": "반도체 대미투자 ",
        "alaska_project_cost_usd_b:": "알래스카 LNG 총사업비 ",
        "alaska_korea_investment_usd_b:": "알래스카 LNG 한국 전략투자 ",
        "alaska_reported_amount_usd_b:": "알래스카 LNG 보도수치 ",
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
            elif prefix.endswith("_usd_b:"):
                try:
                    raw = f"{float(raw) * 10:g}억"
                except Exception:
                    pass
                suffix = "달러"
            elif "_usd:" in prefix:
                suffix = "달러"
            return f"{label}{raw}{suffix}"
    supplier_names = {
        "doosan": "두산에너빌리티",
        "hyundaiec": "현대건설",
        "beomhanmecatec": "범한메카텍",
        "bhi": "비에이치아이",
    }
    if value.startswith("nuclear_supplier_award:"):
        raw = value.split(":", 1)[1]
        return f"Project Power/AP1000 공급·발주 확정: {supplier_names.get(raw, raw)}"
    if value.startswith("nuclear_vendor_qualification:"):
        raw = value.split(":", 1)[1]
        return f"Project Power/AP1000 공급사 검증·승인: {supplier_names.get(raw, raw)}"
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
        "party:hyundaiec": "현대건설",
        "party:beomhanmecatec": "범한메카텍",
        "party:bhi": "비에이치아이",
        "party:gevernova": "GE Vernova",
        "party:siemens": "Siemens Energy",
        "party:bw": "Babcock & Wilcox",
        "party:baseelectron": "Base Electron",
        "party:applieddigital": "Applied Digital",
        "party:posco": "포스코",
        "party:kogas": "한국가스공사",
        "party:glenfarne": "Glenfarne",
        "party:kumkang": "금강공업",
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
            "official_status:unconfirmed",
        ],
        "slots": {
            "nuclear_build|official_status": "official_status:unconfirmed",
        },
        "initialized_at": now,
        "updated_at": now,
        "last_title": "정부 기준선: 대미투자 원전 프로젝트의 기수·노형·부지·사업자는 미확정",
        "last_source": "migration-v4",
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

def _migrate_alaska_investment_semantics(state: dict) -> None:
    if int(state.get("alaska_investment_semantics_version") or 0) >= 2:
        return
    bucket = (state.setdefault("event_states", {}).get("alaska_lng") or {})
    facts = [str(x) for x in (bucket.get("facts") or [])]
    slots = {str(k): str(v) for k, v in (bucket.get("slots") or {}).items()}
    evidence = bucket.get("evidence") or []
    evidence_text = _norm(" ".join(str(x.get("title") or "") for x in evidence if isinstance(x, dict)))
    old_fact = slots.get("alaska_lng|alaska_project_usd")
    if old_fact == "alaska_project_usd:540억" and "540억" in evidence_text and any(x in evidence_text for x in ["한국", "korea", "korean"]):
        facts = [x for x in facts if x != old_fact]
        slots.pop("alaska_lng|alaska_project_usd", None)

    # v1에서 54B를 '한국 전략투자 확정액'처럼 저장한 값을 되돌린다.
    old_korea = slots.get("alaska_lng|alaska_korea_investment_usd_b")
    if old_korea == "alaska_korea_investment_usd_b:54":
        facts = [x for x in facts if x != old_korea]
        slots.pop("alaska_lng|alaska_korea_investment_usd_b", None)

    if "540억" in evidence_text or "54 billion" in evidence_text:
        facts.append("alaska_reported_amount_usd_b:54")
        slots["alaska_lng|alaska_reported_amount_usd_b"] = "alaska_reported_amount_usd_b:54"
        bucket["facts"] = sorted(set(facts))
        bucket["slots"] = slots
        bucket["last_source"] = str(bucket.get("last_source") or "") + " · amount-role-unconfirmed"
    state["alaska_investment_semantics_version"] = 2


def _migrate_amount_scope_guard(state: dict) -> None:
    if int(state.get("amount_scope_guard_version") or 0) >= 1:
        return
    buckets = state.setdefault("event_states", {})
    package = buckets.get("energy_package") or {}
    if package:
        package["facts"] = sorted(set(str(x) for x in (package.get("facts") or []) if not str(x).startswith("package_usd:")))
        package["slots"] = {str(k): str(v) for k, v in (package.get("slots") or {}).items() if str(k) != "energy_package|package_usd"}
        package["last_source"] = str(package.get("last_source") or "") + " · amount-scope-corrected"
    alaska = buckets.get("alaska_lng") or {}
    if alaska:
        bad = "alaska_reported_amount_usd_b:200"
        alaska["facts"] = sorted(set(str(x) for x in (alaska.get("facts") or []) if str(x) != bad))
        slots = {str(k): str(v) for k, v in (alaska.get("slots") or {}).items()}
        if slots.get("alaska_lng|alaska_reported_amount_usd_b") == bad:
            slots.pop("alaska_lng|alaska_reported_amount_usd_b", None)
        alaska["slots"] = slots
        alaska["last_source"] = str(alaska.get("last_source") or "") + " · total-vs-alaska-corrected"
    state["amount_scope_guard_version"] = 1


def _migrate_announcement_stage_guard(state: dict) -> None:
    if int(state.get("announcement_stage_guard_version") or 0) >= 1:
        return
    for family, bucket in (state.setdefault("event_states", {}) or {}).items():
        facts = [str(x) for x in (bucket.get("facts") or [])]
        slots = {str(k): str(v) for k, v in (bucket.get("slots") or {}).items()}
        executed = "stage:발표실행" in facts
        pending = "stage:발표예정" in facts
        slots.pop(f"{family}|stage:발표실행", None)
        slots.pop(f"{family}|stage:발표예정", None)
        if executed:
            facts = [x for x in facts if x != "stage:발표예정"]
            slots[f"{family}|stage:announcement"] = "stage:발표실행"
        elif pending:
            slots[f"{family}|stage:announcement"] = "stage:발표예정"
        bucket["facts"] = sorted(set(facts))
        bucket["slots"] = slots
    state["announcement_stage_guard_version"] = 1


def _migrate_joint_fact_sheet_status(state: dict) -> None:
    if int(state.get("joint_fact_sheet_status_version") or 0) >= 1:
        return
    nuclear = (state.setdefault("event_states", {}).get("nuclear_build") or {})
    facts = [str(x) for x in (nuclear.get("facts") or [])]
    slots = {str(k): str(v) for k, v in (nuclear.get("slots") or {}).items()}
    if "nuclear_framework_status:agreed" in facts:
        facts = [x for x in facts if x != "official_status:unconfirmed"]
        slots.pop("nuclear_build|official_status", None)
        facts.append("nuclear_project_status:individual_projects_pending")
        slots["nuclear_build|nuclear_project_status"] = "nuclear_project_status:individual_projects_pending"
        nuclear["facts"] = sorted(set(facts))
        nuclear["slots"] = slots
    state["joint_fact_sheet_status_version"] = 1


def _migrate_westinghouse_framework_equity(state: dict) -> None:
    if int(state.get("westinghouse_framework_equity_version") or 0) >= 1:
        return
    bucket = (state.setdefault("event_states", {}).get("westinghouse_stake") or {})
    if bucket:
        stale = {"stake_percent:10", "stage:의결", "governance:board", "governance:voting"}
        bucket["facts"] = sorted(set(str(x) for x in (bucket.get("facts") or []) if str(x) not in stale))
        bucket["slots"] = {
            str(k): str(v) for k, v in (bucket.get("slots") or {}).items()
            if str(v) not in stale and str(k) not in {
                "westinghouse_stake|stake_percent",
                "westinghouse_stake|stake_equity_percent",
                "westinghouse_stake|stage:의결",
                "westinghouse_stake|governance:board",
                "westinghouse_stake|governance:voting",
            }
        }
        bucket["last_source"] = str(bucket.get("last_source") or "") + " · official-framework-reset"
    state["westinghouse_framework_equity_version"] = 1


def _migrate_project_power_funding_roles(state: dict) -> None:
    if int(state.get("project_power_funding_roles_version") or 0) >= 1:
        return
    bucket = (state.setdefault("event_states", {}).get("nuclear_build") or {})
    if bucket:
        facts = {str(x) for x in (bucket.get("facts") or [])}
        slots = {str(k): str(v) for k, v in (bucket.get("slots") or {}).items()}

        # 과거 파서가 1,200억 총재원과 1,000억 건설비·200억 예비비·100억 선지급을
        # nuclear_framework_usd_b 한 슬롯에 섞을 수 있었으므로 총재원은 120으로 고정하고 역할별로 분리한다.
        facts = {x for x in facts if not x.startswith("nuclear_framework_usd_b:")}
        facts.add("nuclear_framework_usd_b:120")
        slots["nuclear_build|nuclear_framework_usd_b"] = "nuclear_framework_usd_b:120"

        baseline = {
            "nuclear_construction_cost_usd_b:100",
            "nuclear_contingency_usd_b:20",
            "nuclear_upfront_payment_usd_b:10",
            "nuclear_upfront_payment_status:conditional",
        }
        facts |= baseline
        slots["nuclear_build|nuclear_construction_cost_usd_b"] = "nuclear_construction_cost_usd_b:100"
        slots["nuclear_build|nuclear_contingency_usd_b"] = "nuclear_contingency_usd_b:20"
        slots["nuclear_build|nuclear_upfront_payment_usd_b"] = "nuclear_upfront_payment_usd_b:10"
        slots["nuclear_build|nuclear_upfront_payment_status"] = "nuclear_upfront_payment_status:conditional"
        bucket["facts"] = sorted(facts)
        bucket["slots"] = slots
        bucket["last_source"] = str(bucket.get("last_source") or "") + " · project-power-funding-roles"
    state["project_power_funding_roles_version"] = 1


def _migrate_encinal_project_cost_role(state: dict) -> None:
    if int(state.get("encinal_project_cost_role_version") or 0) >= 1:
        return
    bucket = (state.setdefault("event_states", {}).get("encinal") or {})
    if bucket:
        facts = {str(x) for x in (bucket.get("facts") or [])}
        slots = {str(k): str(v) for k, v in (bucket.get("slots") or {}).items()}
        # 첫 송금 24억달러(2.4B)가 Project Star 총사업비로 오염된 과거 상태를
        # 산업통상부 확정 총사업비 223억달러(22.3B)로 교정한다.
        facts = {x for x in facts if not x.startswith("encinal_project_cost_usd_b:")}
        facts.add("encinal_project_cost_usd_b:22.3")
        slots["encinal|encinal_project_cost_usd_b"] = "encinal_project_cost_usd_b:22.3"
        bucket["facts"] = sorted(facts)
        bucket["slots"] = slots
        bucket["last_source"] = str(bucket.get("last_source") or "") + " · project-cost-vs-funding-corrected"
    state["encinal_project_cost_role_version"] = 1


def _load() -> dict:
    global _SHARED_STATE, _BOOTSTRAP_GUARD
    state = _ORIG_LOAD()
    old_version = int(state.get("event_state_guard_version") or 0)
    _BOOTSTRAP_GUARD = old_version < GUARD_VERSION
    state.setdefault("event_states", {})
    _migrate_alaska_investment_semantics(state)
    _migrate_amount_scope_guard(state)
    _migrate_announcement_stage_guard(state)
    _migrate_joint_fact_sheet_status(state)
    _migrate_westinghouse_framework_equity(state)
    _migrate_project_power_funding_roles(state)
    _migrate_encinal_project_cost_role(state)
    if _BOOTSTRAP_GUARD:
        state["event_state_guard_version"] = GUARD_VERSION
        state["event_state_guard_started_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        # 기사/URL 기반 과거 event key와 오염된 원전 기수·노형 상태는 v4에서 재사용하지 않는다.
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

    if family == "funding_execution" and "stage:송금집행" in facts:
        stale = slots.pop("funding_execution|official_status", None)
        if stale == "official_status:unconfirmed":
            print("funding_stale_unconfirmed_removed=true")

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

def _source_quality(row: dict) -> int:
    blob = _norm(f"{row.get('source', '')} {row.get('link', '')}")
    top = [
        "reuters", "bloomberg", "연합뉴스", "뉴스1", "뉴시스", "mbc",
        "산업통상", "정책브리핑", "white house", "백악관",
    ]
    solid = [
        "한국경제", "머니투데이", "한겨레", "서울경제", "매일경제",
        "한국일보", "조선비즈", "전자신문", "뉴스핌", "ytn", "동아일보",
    ]
    if any(token in blob for token in top):
        return 2
    if any(token in blob for token in solid):
        return 1
    return 0


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
            _source_quality(r),
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

    # v4 전환 첫 실행은 공식 확인 상태만 기준선으로 흡수하고 과거 기사를 재발송하지 않는다.
    if _BOOTSTRAP_GUARD:
        for family, family_rows in groups.items():
            accepted, evidence_map = _accepted_facts_for_group(family, family_rows)
            if not accepted:
                continue
            evidence_row = _pick_evidence_row(accepted, evidence_map, family_rows)
            _apply_state(family, evidence_row, accepted, evidence_map)
        _SHARED_STATE["event_state_guard_baselined_at"] = now.isoformat()
        print(f"event_state_guard_v4_baseline_families={len(groups)}")
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
    if accepted:
        raise RuntimeError(f"unconfirmed nuclear numbers became state: {accepted}")

    official_nuclear_rows = [
        {
            "title": "미국 원전 8기·AP1000 6기·APR1400 2기 공식 확정 발표",
            "source": "산업통상부",
            "link": "https://example.com/official-nuclear",
            "published": "2026-09-20T00:06:00+00:00",
        },
    ]
    accepted, _ = _accepted_facts_for_group("nuclear_build", official_nuclear_rows)
    expected = {"nuclear_total_units:8", "ap1000_units:6", "apr1400_units:2", "official_status:confirmed"}
    if not expected.issubset(accepted):
        raise RuntimeError(f"official nuclear state parsing failed: {accepted}")

    ambiguous_total_rows = [
        {
            "title": "대미투자 AP1000·APR1400 포함 원전 8기 건설 보도",
            "source": "한국경제",
            "link": "https://www.hankyung.com/example",
            "published": "2026-09-20T00:10:00+00:00",
        },
        {
            "title": "미국 AP1000과 APR1400 포함 원전 8기 협의",
            "source": "머니투데이",
            "link": "https://www.mt.co.kr/example",
            "published": "2026-09-20T00:11:00+00:00",
        },
    ]
    accepted, _ = _accepted_facts_for_group("nuclear_build", ambiguous_total_rows)
    if accepted:
        raise RuntimeError(f"ambiguous unconfirmed total became state: {accepted}")

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
    if accepted:
        raise RuntimeError(f"inconsistent unconfirmed nuclear numbers became state: {accepted}")

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

    if "540억" not in _korean_usd_tokens("알래스카 LNG에 한국 540억불 투자 발표 가능성"):
        raise RuntimeError("억불 parser regression")
    canonical = _usd_billion_values("알래스카 LNG에 한국 540억불 투자, Reuters $54 billion")
    if canonical != ["54"]:
        raise RuntimeError(f"Alaska investment canonicalization regression: {canonical}")
    reported_rows = [
        {
            "title": "트럼프, 알래스카 LNG 사업에 한국 540억불 투자 발표 가능성",
            "source": "연합뉴스",
            "link": "https://example.com/alaska-report-a",
            "published": "2026-09-30T00:10:00+00:00",
        },
        {
            "title": "Trump set to announce $54 billion Korean investment in Alaska LNG",
            "source": "Reuters",
            "link": "https://example.com/alaska-report-b",
            "published": "2026-09-30T00:11:00+00:00",
        },
    ]
    accepted, _ = _accepted_facts_for_group("alaska_lng", reported_rows)
    if "alaska_reported_amount_usd_b:54" not in accepted:
        raise RuntimeError(f"Alaska reported amount parsing regression: {accepted}")
    if "alaska_korea_investment_usd_b:54" in accepted or "alaska_project_cost_usd_b:54" in accepted:
        raise RuntimeError(f"Alaska 54B was over-classified before official confirmation: {accepted}")

    bad_package_rows = [
        {"title": "백악관, 한국 대미투자 발표에 알래스카 LNG 540억달러·원전 8기 포함 확인", "source": "MBC 뉴스", "link": "https://example.com/package-bad-a", "published": "2026-10-01T00:00:00+00:00"},
        {"title": "한국 대미투자 발표에 알래스카 LNG 540억달러와 원전 8기 포함", "source": "디지털타임스", "link": "https://example.com/package-bad-b", "published": "2026-10-01T00:01:00+00:00"},
    ]
    accepted, _ = _accepted_facts_for_group("energy_package", bad_package_rows)
    if "package_overall_usd_b:54" in accepted or any(x.startswith("package_usd:") for x in accepted):
        raise RuntimeError(f"Alaska 54B leaked into package total: {accepted}")
    if "package_nuclear_units:8" not in accepted:
        raise RuntimeError(f"package nuclear units lost while filtering amount: {accepted}")

    bad_alaska_rows = [
        {"title": "백악관 트럼프, 한국 2000억 달러 대미 투자 곧 공개…알래스카 LNG 포함", "source": "뉴스핌", "link": "https://example.com/alaska-bad-a", "published": "2026-10-01T00:02:00+00:00"},
        {"title": "한국 2000억달러 대미투자 계획 공개, 알래스카 LNG 포함", "source": "연합뉴스", "link": "https://example.com/alaska-bad-b", "published": "2026-10-01T00:03:00+00:00"},
    ]
    accepted, _ = _accepted_facts_for_group("alaska_lng", bad_alaska_rows)
    if any(x.endswith(":200") and x.startswith("alaska_") for x in accepted):
        raise RuntimeError(f"overall 200B leaked into Alaska amount: {accepted}")

    executed_rows = [
        {"title": "백악관 트럼프, 2000억달러 한국 대미투자 발표…에너지사업 집중", "source": "뉴스1", "link": "https://example.com/executed-a", "published": "2026-10-01T01:00:00+00:00"},
        {"title": "트럼프, 2000억달러 한국 대미투자 발표…원전·가스 포함", "source": "한국경제", "link": "https://example.com/executed-b", "published": "2026-10-01T01:01:00+00:00"},
    ]
    accepted, _ = _accepted_facts_for_group("energy_package", executed_rows)
    if "stage:발표실행" not in accepted:
        raise RuntimeError(f"actual Trump announcement was not promoted: {accepted}")

    upcoming_rows = [
        {"title": "트럼프, 2000억달러 한국 대미투자 발표 예정", "source": "뉴스1", "link": "https://example.com/upcoming-a", "published": "2026-10-01T01:02:00+00:00"},
        {"title": "트럼프, 2000억달러 한국 대미투자 발표 가능성", "source": "한국경제", "link": "https://example.com/upcoming-b", "published": "2026-10-01T01:03:00+00:00"},
    ]
    accepted, _ = _accepted_facts_for_group("energy_package", upcoming_rows)
    if "stage:발표실행" in accepted:
        raise RuntimeError(f"upcoming announcement was falsely promoted as executed: {accepted}")

    good_alaska_rows = [
        {"title": "백악관, 한국 대미투자에 알래스카 LNG 540억달러 포함", "source": "MBC 뉴스", "link": "https://example.com/alaska-good-a", "published": "2026-10-01T00:04:00+00:00"},
        {"title": "한국 대미투자에 알래스카 LNG 540억달러 포함", "source": "디지털타임스", "link": "https://example.com/alaska-good-b", "published": "2026-10-01T00:05:00+00:00"},
    ]
    accepted, _ = _accepted_facts_for_group("alaska_lng", good_alaska_rows)
    if "alaska_reported_amount_usd_b:54" not in accepted:
        raise RuntimeError(f"direct Alaska 54B amount not captured: {accepted}")

    kumkang_candidate_rows = [
        {
            "title": "금강공업, 알래스카 LNG API 5L X70 공급 자격 확보",
            "source": "데이터투자",
            "link": "https://example.com/kumkang-a",
            "published": "2026-09-28T03:13:00+00:00",
        },
        {
            "title": "금강공업 알래스카 LNG X70 공급 참여 가능성",
            "source": "뉴스1",
            "link": "https://example.com/kumkang-b",
            "published": "2026-09-28T04:00:00+00:00",
        },
    ]
    accepted, _ = _accepted_facts_for_group("alaska_lng", kumkang_candidate_rows)
    if "party:kumkang" in accepted:
        raise RuntimeError(f"kumkang candidate was promoted without project award: {accepted}")

    split_title = "원전 8기 AP1000 6기 APR1400 2기"
    if _explicit_model_units(_norm(split_title), "ap1000") != {"6"}:
        raise RuntimeError("AP1000 unit adjacency regression")
    if _explicit_model_units(_norm(split_title), "apr1400") != {"2"}:
        raise RuntimeError("APR1400 unit adjacency regression")

    funding_rows = _verified_funding_baseline_rows()
    accepted, _ = _accepted_facts_for_group("funding_execution", funding_rows)
    required_funding = {
        "funding_amount_usd:24억",
        "funding_date:2026-10-01",
        "stage:송금집행",
    }
    if not required_funding.issubset(accepted):
        raise RuntimeError(f"completed first funding baseline failed: {accepted}")
    if "stage:송금예정" in accepted:
        raise RuntimeError(f"completed first funding was misclassified as pending: {accepted}")

    planned_funding_rows = [
        {
            "title": "2026-10-31 첫 송금 21억~24억달러 예정",
            "source": "뉴스1",
            "link": "https://example.com/funding-planned-a",
            "published": "2026-09-30T00:00:00+00:00",
        },
        {
            "title": "첫 투자금 24억달러 이달 말 송금할 계획",
            "source": "한국일보",
            "link": "https://example.com/funding-planned-b",
            "published": "2026-09-30T00:01:00+00:00",
        },
    ]
    accepted, _ = _accepted_facts_for_group("funding_execution", planned_funding_rows)
    if "stage:송금집행" in accepted:
        raise RuntimeError(f"planned funding was falsely promoted as executed: {accepted}")

    official_rows = _official_project_baseline_rows()
    by_family = {}
    for row in official_rows:
        by_family.setdefault(_family(row), []).append(row)

    accepted, _ = _accepted_facts_for_group("encinal", by_family.get("encinal", []))
    required_encinal = {
        "encinal_status:confirmed_first",
        "encinal_project_cost_usd_b:22.3",
        "encinal_total_mw:6472",
        "encinal_phase1_year:2029",
        "encinal_full_year:2032",
    }
    if not required_encinal.issubset(accepted):
        raise RuntimeError(f"official Project Star baseline failed: {accepted}")

    transfer_only_encinal = [{
        "title": "텍사스 엔시날 첫 투자금 24억달러 미국 송금 완료",
        "source": "아주경제",
        "link": "https://example.com/encinal-transfer-only",
        "published": "2026-10-01T05:30:00+00:00",
    }]
    transfer_accepted, _ = _accepted_facts_for_group("encinal", transfer_only_encinal)
    if any(x.startswith("encinal_project_cost_usd_b:") for x in transfer_accepted):
        raise RuntimeError(f"Encinal first transfer contaminated project cost: {transfer_accepted}")

    accepted, _ = _accepted_facts_for_group("nuclear_build", by_family.get("nuclear_build", []))
    required_nuclear = {
        "nuclear_framework_status:agreed",
        "nuclear_total_units:8",
        "ap1000_units:6",
        "apr1400_units:2",
        "nuclear_framework_usd_b:120",
        "nuclear_construction_cost_usd_b:100",
        "nuclear_contingency_usd_b:20",
        "nuclear_upfront_payment_usd_b:10",
        "nuclear_upfront_payment_status:conditional",
        "nuclear_framework_binding:nonbinding",
        "nuclear_definitive_agreement_status:pending",
        "nuclear_federal_site_status:planned",
        "nuclear_initial_ap1000_units:2",
        "nuclear_settlement_waiver_status:contemplated",
        "nuclear_apr1400_wh_value_per_unit_usd_b:2",
        "nuclear_korean_ap1000_supply_chain:included",
        "nuclear_counterparty_confirmation:official",
    }
    if not required_nuclear.issubset(accepted):
        raise RuntimeError(f"official Project Power baseline failed: {accepted}")

    if any(x in accepted for x in {"nuclear_framework_usd_b:100", "nuclear_framework_usd_b:20", "nuclear_framework_usd_b:10"}):
        raise RuntimeError(f"Project Power amount roles collapsed into total framework slot: {accepted}")

    executed_power = [{
        "title": "산업통상부 공식 Project Power 최대 100억달러 선지급 완료 장주기 품목 구매주문 발주 완료",
        "source": "대한민국 정책브리핑",
        "link": "https://example.com/project-power-executed",
        "published": "2026-12-15T00:00:00+00:00",
    }]
    executed_accepted, _ = _accepted_facts_for_group("nuclear_build", executed_power)
    if "nuclear_upfront_payment_status:executed" not in executed_accepted:
        raise RuntimeError(f"Project Power upfront execution parsing failed: {executed_accepted}")
    if "nuclear_longlead_order_status:ordered" not in executed_accepted:
        raise RuntimeError(f"Project Power long-lead PO parsing failed: {executed_accepted}")

    accepted, _ = _accepted_facts_for_group("westinghouse_stake", by_family.get("westinghouse_stake", []))
    required_stake = {
        "stake_range_percent:5~10",
        "stake_status:contemplated",
        "equity_definitive_agreement_status:pending",
        "equity_due_diligence_status:pending",
        "equity_regulatory_approval_status:pending",
    }
    if not required_stake.issubset(accepted):
        raise RuntimeError(f"official Westinghouse equity baseline failed: {accepted}")

    accepted, _ = _accepted_facts_for_group("alaska_lng", by_family.get("alaska_lng", []))
    if "alaska_bilateral_status:review_started" not in accepted:
        raise RuntimeError(f"official Project North baseline failed: {accepted}")

    print("state_event_guard_self_test=passed")
    return 0


def _verified_funding_baseline_rows() -> list[dict]:
    return [
        {
            "title": "재정경제부 확인 2026-10-01 정부 첫 대미투자금 24억달러 첫 송금 완료 텍사스 엔시날",
            "source": "뉴스1",
            "link": "https://www.news1.kr/economy/trend/6307297",
            "published": "2026-10-01T01:56:00+00:00",
        },
        {
            "title": "재정경제부 확인 2026-10-01 텍사스 엔시날 첫 투자금 24억달러 미국 송금 완료",
            "source": "아주경제",
            "link": "https://v.daum.net/v/qxaIoHd8vp",
            "published": "2026-10-01T05:30:00+00:00",
        },
    ]


def _official_project_baseline_rows() -> list[dict]:
    link = "https://www.korea.kr/briefing/pressReleaseView.do?newsId=156783865"
    published = "2026-10-01T00:00:00+00:00"
    return [
        {
            "title": "산업통상부 공식 Project Star 엔시날 제1호 공식 추진 사업비 223억달러 6472MW 2029 1단계 2032 전체 가동",
            "source": "대한민국 정책브리핑",
            "link": link,
            "published": published,
        },
        {
            "title": "산업통상부 공식 Project Power 한미 원전 프레임워크 합의 원전 8기 AP1000 6기 APR1400 2기 최대 1200억달러 건설비용 1000억달러 예비비 200억달러 연말까지 최대 100억달러 먼저 지급 장주기 품목 선제 확보 상업적 합리성 검토와 국회보고를 전제로 협의",
            "source": "대한민국 정책브리핑",
            "link": link,
            "published": published,
        },
        {
            "title": "산업통상부 공식 Project North 알래스카 LNG 검토 착수 상업적 합리성 국내법 요건 충족 시 추진 여부 결정",
            "source": "대한민국 정책브리핑",
            "link": link,
            "published": published,
        },
        {
            "title": "Cameco 공식 Project Power 원전 프레임워크 원전 8기 AP1000 6기 APR1400 2기 최대 1200억달러 terms non-binding definitive agreements pending federal sites planned beginning with AP1000 2기 2025 settlement agreement one-time waiver contemplated APR1400 reactor당 20억달러 Westinghouse value",
            "source": "Cameco",
            "link": "https://www.cameco.com/media/news/cameco-acknowledges-united-states-and-republic-of-korea-announcement-of-framework-for",
            "published": "2026-09-30T12:00:00+00:00",
        },
        {
            "title": "Westinghouse Brookfield 공식 한국 Westinghouse cornerstone equity investment 5~10% potential equity investment terms non-binding subject to definitive agreements due diligence regulatory approvals pending",
            "source": "Westinghouse",
            "link": "https://info.westinghousenuclear.com/news/u.s.-korea-framework-advances-deployment-of-westinghouse-nuclear-technology-in-the-united-states",
            "published": "2026-10-01T12:00:00+00:00",
        },
        {
            "title": "산업통상부 공식 Project Power AP1000 6기 한국 시공사 기자재기업 참여 확대 한미 원전 프레임워크 합의",
            "source": "산업통상부",
            "link": "https://www.motir.go.kr/kor/article/ATCL3f49a5a8c/172253/view",
            "published": "2026-10-01T00:00:00+00:00",
        },
    ]


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

    _RSS_BUFFER.extend(_official_project_baseline_rows())
    _RSS_BUFFER.extend(_verified_funding_baseline_rows())
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


# Project Power 실행단계는 일반 '원전' 기사보다 좁은 키워드로 추가 감시한다.
# 새 워크플로를 만들지 않고 기존 대미투자 watcher의 검색면만 넓힌다.
for _query in [
    '"Project Power" Westinghouse Korea definitive agreement waiver site AP1000 APR1400 when:30d',
    '"Project Power" AP1000 EPC purchase order long lead Korea when:30d',
    'Westinghouse AP1000 Korea Doosan Hyundai E&C BHI Beomhan purchase order contract when:30d',
    '웨스팅하우스 AP1000 한국 두산에너빌리티 현대건설 비에이치아이 범한메카텍 발주 수주 공급계약 when:30d',
    'APR1400 미국 waiver 타협협정 예외 최종계약 부지 건설허가 when:30d',
]:
    if _query not in core.QUERIES:
        core.QUERIES.append(_query)

for _term in [
    "Project Power", "definitive agreement", "waiver", "financial close",
    "purchase order", "long lead", "EPC", "vendor qualification",
    "건설허가", "복합허가", "부지 선정", "공급계약", "벤더 승인",
    "두산에너빌리티", "현대건설", "비에이치아이", "범한메카텍",
]:
    if _term not in core.MATERIAL:
        core.MATERIAL.append(_term)

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
