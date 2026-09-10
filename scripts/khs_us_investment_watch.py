#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import email.utils
import hashlib
import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
DATA = ROOT / "data"
STATE = DATA / "khs_us_investment_seen.json"
PENDING = OUT / "khs_us_investment_pending_seen.json"
ALERT = OUT / "khs_us_investment_alert.html"
KST = ZoneInfo("Asia/Seoul")

QUERIES = [
    '"대미투자" 엔시날 when:3d',
    '"Encinal" 6.3GW gas plant Korea when:3d',
    '"한미전략투자" I-SPV OR SPV when:3d',
    '"대미투자" PPA OR EPC OR 가스터빈 when:3d',
    '"텍사스" "AI 데이터센터" 가스발전 when:3d',
    '"Texas" "data center" "gas power" when:3d',
    '"Texas" "data center" "gas plant" when:3d',
    '"Texas" data center combined-cycle turbine when:3d',
    '"대미투자" 반도체 OR 삼성전자 OR SK하이닉스 when:3d',
    '"대미투자" 원전 OR AP1000 OR APR1400 when:3d',
    '"대미투자" "알래스카 LNG" when:3d',
    '"알래스카 LNG" 한국 참여 OR 투자 OR 압박 when:3d',
    '"Alaska LNG" Korea POSCO KOGAS when:3d',
    '"Alaska LNG" offtake OR FID OR financing when:7d',
    '"Alaska LNG" 13 MTPA OR 16 MTPA when:7d',
    '"Alaska LNG" tax OR property tax OR pipeline when:7d',
    '"대미투자" 수익배분 OR "위험 통합" OR risk-pooling when:3d',
    '"대미투자" "프로젝트별 손익" OR 손실분담 OR 원리금 when:3d',
    '"대미투자" "45영업일" OR "선정 통지" OR 송금 when:3d',
    '"대미투자" "확정된 바 없습니다" OR 설명자료 when:3d',
    '"대미투자" 관세 OR 301조 OR 232조 when:3d',
]

TRUSTED = [
    "산업통상", "정책브리핑", "대한민국 정책브리핑", "재정경제부", "연합뉴스", "뉴시스", "뉴스1",
    "이데일리", "헤럴드경제", "한국경제", "중앙일보", "머니투데이", "글로벌경제신문", "GetNews",
    "Reuters", "Yahoo", "Inside Climate News", "San Antonio Express-News", "Global Energy Monitor",
    "Pipeline & Gas Journal", "Bloomberg", "Utility Dive", "Glenfarne", "Alaska's News Source",
]

MATERIAL = [
    "확정", "의결", "합의", "계약", "체결", "승인", "허가", "착공", "증액", "감액", "사업비",
    "I-SPV", "PPA", "EPC", "가스터빈", "스팀터빈", "HRSG", "수주", "발전소", "가스발전",
    "현장발전", "데이터센터", "반도체", "원전", "LNG", "관세", "301조", "232조", "제외", "포함",
    "압박", "참여", "최종투자결정", "FID", "금융종결", "오프테이크", "구매계약", "SPA", "HOA",
    "MTPA", "세제", "재산세", "파이프라인", "Glenfarne", "POSCO", "포스코", "KOGAS", "한국가스공사",
    "수익배분", "손실분담", "위험 통합", "risk-pooling", "프로젝트별 손익", "원리금", "상위 SPV",
    "투자 SPV", "손실 상계", "45영업일", "선정 통지", "자금 납입", "송금", "확정된 바 없습니다",
    "gas power", "gas plant", "gas-fired", "combined-cycle", "data center", "turbine", "permit", "construction",
    "offtake", "financial close", "pipeline", "property tax", "6.3GW", "22.3 billion", "ERCOT", "behind-the-meter",
]

MARKET_REACTION_TERMS = [
    "강세", "급등", "상한가", "상승세", "주가", "관련주", "테마주", "株", "%↑", "% 상승",
]

OPINION_TERMS = [
    "[사설]", "사설]", "오피니언", "칼럼", "기고",
]

HARD_PROGRESS_TERMS = [
    "확정", "의결", "계약", "체결", "승인", "허가", "착공", "fid", "최종투자결정",
    "financial close", "금융종결", "spa", "hoa", "오프테이크", "offtake", "구매계약",
    "투자액", "투자규모", "배정액", "지분", "사업비", "증액", "감액", "수주", "수익배분",
    "손실분담", "프로젝트별 손익", "원리금", "45영업일", "선정 통지", "자금 납입", "송금",
    "확정된 바 없습니다", "설명자료", "epc", "강재 공급", "mtpa", "만톤", "억달러", "조원", "재산세", "세제",
]

ALASKA_PRESSURE_TERMS = [
    "압박", "빨리", "서둘러", "참여하라", "참여 요구", "참여 촉구", "pressure", "urge", "urges",
]

OFFICIAL_SOURCE_TERMS = [
    "정책브리핑", "산업통상", "재정경제부", "기획재정부", "대한민국 정책브리핑",
]

SAFEGUARD_TERMS = [
    "수익배분", "손실분담", "위험 통합", "risk-pooling", "리스크 풀링", "프로젝트별 손익", "원리금",
    "상위 spv", "투자 spv", "손실 상계", "안전판", "회수",
]

FUNDING_GUARD_TERMS = [
    "45영업일", "선정 통지", "자금 납입", "자금납입", "capital call", "송금", "첫 집행", "첫 납입",
]


def _load() -> dict:
    if not STATE.exists():
        return {"bootstrap": False, "seen": {}, "semantic_seen": {}}
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
        state.setdefault("seen", {})
        state.setdefault("semantic_seen", {})
        return state
    except Exception:
        return {"bootstrap": False, "seen": {}, "semantic_seen": {}}


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 KHS-US-Investment-Watch"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def _is_simple_market_reaction(title: str) -> bool:
    low = title.lower()
    market = any(term.lower() in low for term in MARKET_REACTION_TERMS)
    hard = any(term.lower() in low for term in HARD_PROGRESS_TERMS)
    return market and not hard


def _is_low_value_opinion(title: str) -> bool:
    low = title.lower()
    opinion = any(term.lower() in low for term in OPINION_TERMS)
    hard = any(term.lower() in low for term in HARD_PROGRESS_TERMS)
    return opinion and not hard


def _is_official(row: dict) -> bool:
    blob = f"{row.get('title', '')} {row.get('source', '')}".lower()
    return any(term.lower() in blob for term in OFFICIAL_SOURCE_TERMS)


def _rss(query: str) -> list[dict]:
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"}
    )
    root = ET.fromstring(_fetch(url))
    rows = []
    for node in root.findall(".//item"):
        title = html.unescape(re.sub(r"\s+", " ", node.findtext("title") or "")).strip()
        source = (node.findtext("source") or "").strip()
        link = (node.findtext("link") or "").strip()
        pub = node.findtext("pubDate") or ""
        try:
            published = email.utils.parsedate_to_datetime(pub)
            if published.tzinfo is None:
                published = published.replace(tzinfo=dt.timezone.utc)
        except Exception:
            published = dt.datetime.now(dt.timezone.utc)
        blob = f"{title} {source}"
        if not any(x.lower() in blob.lower() for x in TRUSTED):
            continue
        if not any(x.lower() in blob.lower() for x in MATERIAL):
            continue
        if _is_simple_market_reaction(title):
            continue
        if _is_low_value_opinion(title):
            continue
        rows.append(
            {
                "title": title,
                "source": source or "신뢰자료",
                "link": link,
                "published": published.isoformat(),
            }
        )
    return rows


def _key(row: dict) -> str:
    raw = f"{row['title']}|{row['link']}"
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def _parse_utc(value: str) -> dt.datetime | None:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except Exception:
        return None


def _semantic_key(row: dict) -> str:
    low = row["title"].lower()
    alaska = "알래스카" in low or "alaska lng" in low
    if not alaska:
        return ""
    pressure = any(term.lower() in low for term in ALASKA_PRESSURE_TERMS)
    hard = any(term.lower() in low for term in HARD_PROGRESS_TERMS)
    if pressure and not hard:
        return "alaska_participation_pressure"
    return ""


def _run_event_key(row: dict) -> str:
    low = row["title"].lower()
    official = _is_official(row)
    if any(term.lower() in low for term in SAFEGUARD_TERMS):
        return "safeguard_official" if official else "safeguard_media"
    if any(term.lower() in low for term in FUNDING_GUARD_TERMS):
        return "funding_official" if official else "funding_media"
    if "웨스팅하우스" in low or "westinghouse" in low:
        return "westinghouse"
    if "엔시날" in low or "encinal" in low or "6.3gw" in low:
        return "encinal"
    if "알래스카" in low or "alaska lng" in low:
        return "alaska"
    if "원전" in low or "ap1000" in low or "apr1400" in low:
        return "nuclear"
    if "텍사스" in low or "texas" in low or "데이터센터" in low or "data center" in low:
        return "texas_ai_power"
    if "반도체" in low or "삼성전자" in low or "sk하이닉스" in low:
        return "semiconductor"
    return ""


def _tags(title: str, source: str = "") -> list[str]:
    low = title.lower()
    source_low = source.lower()
    out = []
    if any(term.lower() in f"{low} {source_low}" for term in OFFICIAL_SOURCE_TERMS):
        if "설명자료" in low or "확정된 바 없습니다" in low or "사실이 아닙니다" in low or "정부 입장" in low:
            out.append("공식정정/정부입장")
    for tag, terms in [
        ("수익배분/손실분담", ["수익배분", "손실분담", "위험 통합", "risk-pooling", "프로젝트별 손익", "원리금", "안전판", "회수"]),
        ("송금절차/45영업일", ["45영업일", "선정 통지", "자금 납입", "자금납입", "capital call", "송금", "첫 집행"]),
        ("1호/엔시날", ["엔시날", "encinal", "6.3gw"]),
        ("텍사스 AI 전력", ["texas", "텍사스", "data center", "데이터센터"]),
        ("현장발전/오프그리드", ["behind-the-meter", "on-site", "현장발전", "자체발전", "off-grid"]),
        ("투자구조", ["i-spv", "spv", "지분", "소유권", "의결권"]),
        ("PPA/전력판매", ["ppa", "전력판매"]),
        ("한국기업 수주", ["epc", "가스터빈", "스팀터빈", "hrsg", "수주", "doosan", "두산"]),
        ("가스발전 설비", ["gas power", "gas plant", "gas-fired", "combined-cycle", "가스발전", "복합화력", "turbine"]),
        ("허가/착공", ["permit", "허가", "construction", "착공", "groundbreaking", "ercot"]),
        ("반도체", ["반도체", "삼성전자", "sk하이닉스"]),
        ("원전", ["원전", "ap1000", "apr1400"]),
        ("알래스카 LNG 압박", ["압박", "참여하라", "참여 촉구", "빨리", "서둘러"]),
        ("알래스카 LNG 실질진전", ["fid", "최종투자결정", "financial close", "금융종결", "offtake", "오프테이크", "spa", "hoa", "mtpa", "재산세"]),
        ("알래스카 LNG", ["알래스카", "alaska lng"]),
        ("관세", ["301조", "232조", "관세"]),
        ("사업비", ["사업비", "증액", "감액", "22.3 billion", "223억"]),
    ]:
        if any(t in low for t in terms):
            out.append(tag)
    return out or ["대미투자·AI전력"]


def _meaning(tags: list[str]) -> str:
    if "공식정정/정부입장" in tags:
        return "언론 제목보다 정부 공식 설명자료를 우선해 확정·미확정 상태를 갱신해야 합니다."
    if "수익배분/손실분담" in tags:
        return "risk-pooling 유지 여부·원리금 회수·손실 상계 범위가 2,000억달러 투자의 실제 위험을 바꿉니다."
    if "송금절차/45영업일" in tags:
        return "선정 통지일·45영업일·연 200억달러 상한·자금요청 순서를 검산해야 실제 집행 확정 여부를 판단할 수 있습니다."
    if "1호/엔시날" in tags:
        return "6.3GW·223억달러 검토안의 정부 확정 여부와 한국 실제 투자부담이 핵심입니다."
    if "텍사스 AI 전력" in tags:
        return "AI 데이터센터가 전력망 대신 자체 발전을 요구하면서 가스터빈·엔진·변압기·배전설비 수요가 실제 프로젝트로 전환되는 신호입니다."
    if "현장발전/오프그리드" in tags:
        return "전력망 접속을 기다리지 않고 현장에서 먼저 전원을 인가하는 설비가 AI 증설 속도를 좌우합니다."
    if "투자구조" in tags:
        return "지분·의결권·손실분담이 실제 투자 회수액과 위험을 바꿉니다."
    if "PPA/전력판매" in tags:
        return "계약 GW·기간·가격이 잠기면 발전소 현금흐름을 계산할 수 있습니다."
    if "한국기업 수주" in tags:
        return "본계약부터 국내 기업의 수주잔고·매출로 연결됩니다."
    if "가스발전 설비" in tags:
        return "발전기술보다 실제 납기와 공급 슬롯이 중요해져 가스터빈·왕복동식 엔진·항공파생 터빈 간 침투율 변화가 발생합니다."
    if "허가/착공" in tags:
        return "발표 GW보다 허가·착공·전원 인가 시점이 실제 매출과 가동률을 결정합니다."
    if "반도체" in tags:
        return "미국 팹이 구체화되면 관세우대와 국내 설비투자 분산을 함께 봐야 합니다."
    if "원전" in tags:
        return "노형·사업 주도권에 따라 한국의 시공·기자재·운영 몫이 달라집니다."
    if "알래스카 LNG 실질진전" in tags:
        return "구속력 있는 장기구매계약·FID·금융종결·한국 투자액이 실제 착공과 매출을 결정합니다."
    if "알래스카 LNG 압박" in tags:
        return "단순 참여 압박 반복은 제외하고 새 시한·금액·당사자·계약이 붙을 때만 단계 상승으로 봅니다."
    if "알래스카 LNG" in tags:
        return "장기구매계약·세제·금융종결이 실제 착공을 결정합니다."
    if "관세" in tags:
        return "관세 변화는 한국 수출기업의 마진과 할인율을 직접 바꿉니다."
    if "사업비" in tags:
        return "사업비가 늘면 투자수익률과 초과비용 부담이 핵심이 됩니다."
    return "프로젝트 확정도와 집행 시간표가 한 단계 바뀐 신호입니다."


def _fixed_project_cost_block() -> list[str]:
    return [
        "<b>💰 대미투자 프로젝트 기준 사업비</b>",
        "",
        "🔥 <b>엔시날 가스복합발전</b>",
        "• 6.3GW · <b>223억달러 ≈ 30조69억원</b>",
        "└ GW당 <b>35.40억달러 ≈ 4조7,630억원</b>",
        "",
        "⚛️ <b>미국 대형원전</b>",
        "• 8기 · <b>1,200억달러 ≈ 161조4,720억원</b>",
        "└ 기당 <b>150억달러 ≈ 20조1,840억원</b>",
        "",
        "🧊 <b>알래스카 LNG</b>",
        "• <b>670억달러 ≈ 90조1,552억원</b> · 한국 협상 보도 기준",
        "",
        "📦 <b>3개 프로젝트 보도상 총사업비 단순합</b>",
        "• <b>2,093억달러 ≈ 281조6,341억원</b>",
        "",
        "<b>⚠️ 꼭 구분할 숫자</b>",
        "• 보도상 첫 송금: <b>22억달러+α ≈ 2조9,603억원+α</b>",
        "• 엔시날 총사업비 223억달러의 <b>약 9.9%</b>",
        "• 첫 송금 전액이 엔시날에 들어간다는 의미는 아님",
        "• 전략투자 한도: <b>총 2,000억달러 / 연 200억달러</b>",
        "• 2,093억달러는 후보사업 총사업비 단순합이며 <b>한국 실제 투자액·한도 초과를 뜻하지 않음</b>",
        "└ 한국 투자지분·미국 측·민간·PF 자금·보증을 분리 확인",
        "• 정부 최종발표·국회 절차·본계약 전에는 확정 수주로 간주하지 않음",
        "",
        "원화 환산 기준: 1달러=1,345.6원 · 2026-09-08 15:30 기준값",
    ]


def _safeguard_block() -> list[str]:
    return [
        "<b>🛡️ 대미투자 안전판·원금회수 기준선</b>",
        "• 2025-11-14 MOU 기준: 상위 투자 SPV가 개별 프로젝트 SPV 수익을 모아 <b>한국 원금+이자를 상환하는 risk-pooling 구조</b>",
        "• 특정 프로젝트 손실을 다른 성공 프로젝트 수익으로 보전할 수 있도록 설계",
        "• 원리금 상환 전 수익배분 <b>한·미 5:5</b> → 상환 후 <b>한국 1 : 미국 9</b>",
        "• <b>20년 내 전체 원리금 상환이 어려우면 수익배분 비율 조정 가능</b>",
        "• 상환이자: 미국 국채 20년물 고정금리 + 가산금리, 가산금리 상한 존재",
        "",
        "<b>🚨 2026-09-10 정부 공식상태</b>",
        "• 산업통상부·재정경제부: <b>수익배분 구조는 한미 협의 중이며 아직 확정되지 않음</b>",
        "• 따라서 '프로젝트별 손익분배 관철·안전판 폐기'는 <b>보도 단계</b>로 관리하고 공식 합의문 전 확정으로 승격하지 않음",
        "",
        "<b>다음 확인</b>",
        "1) risk-pooling 유지/폐기  2) 손실 상계 허용 범위  3) 원리금 상환 순서  4) 프로젝트별 수익배분  5) 이자율·가산금리",
    ]


def _funding_guard_block() -> list[str]:
    return [
        "<b>⏱️ 선정·송금 절차 검증 기준선</b>",
        "• 미국의 투자처 선정 통지 후 <b>최소 45영업일 경과 뒤</b> 사업자금 납입",
        "• 전략투자 실제 납입은 <b>연간 최대 200억달러</b>",
        "• 사업 진척도에 따른 <b>자금요청(capital call)</b> 방식",
        "• 외환시장 불안 우려 시 한국은 <b>납입 시기·규모 조정 요구 가능</b>",
        "• 따라서 '첫 송금 확정' 알림은 <b>선정 통지일 → 45영업일 → 국내 심의·의결 → 자금요청 → 실제 송금</b> 순서 확인",
    ]


def _texas_ai_power_block() -> list[str]:
    return [
        "<b>⚡ 텍사스 AI 현장발전 기준선</b>",
        "• Global Energy Monitor 최신 집계: 텍사스 가스발전 개발 파이프라인 <b>약 122GW</b>",
        "• 이 중 데이터센터 직접 전력용이 <b>약 77GW</b>",
        "• 6개월 동안 텍사스 개발물량이 <b>약 51% 증가</b>",
        "• Yahoo/Inside Climate News가 인용한 분류: 기존 개발 99.4GW + 최근 발표 22.4GW ≈ <b>121.8GW</b>",
        "• 텍사스 최대 12개 신규 가스발전 프로젝트는 모두 데이터센터 전력용으로 파악",
        "• 다만 글로벌 개발물량의 4분의 3 이상이 초기단계이고 일정 지연 사례가 많아 발표 GW=실제 가동 GW는 아님",
        "",
        "<b>정책 병목</b>",
        "• 텍사스 주정부는 데이터센터가 전력망 비용을 주민에게 넘기지 않고 자체 전원을 확보하도록 요구",
        "• ERCOT 접속 요청은 약 <b>474GW</b>, 신규 요청의 약 <b>90%</b>가 데이터센터로 주정부가 집계",
        "",
        "<b>다음 확인</b>",
        "1) Encinal 정부 공식 확정  2) AI 고객 실명·PPA  3) EPC·터빈·HRSG 공급사  4) 가스관·환경허가  5) 착공·전원 인가",
    ]


def _alaska_lng_block() -> list[str]:
    return [
        "<b>🧊 알래스카 LNG 실질 진전 기준선</b>",
        "• 수출설비: <b>20MTPA</b> · 금융종결 목표 <b>16MTPA(80%)</b>",
        "• Reuters 2026-08-13: 확보 약정 <b>13MTPA</b> → 추가 <b>3MTPA</b> 필요",
        "• 포스코인터내셔널: <b>1MTPA × 20년</b> + 최종투자결정 전 투자 + 42인치 가스관 강재 공급",
        "• 1단계: 739마일·42인치 가스관, ConocoPhillips 30년 가스공급계약 확보",
        "• 일정 기준선: 가스관 기계적 완공 2028년 · 첫 가스 2029년 · LNG 수출 목표 2031년",
        "• 사업비 차이: 한국 협상 보도 <b>670억달러 ≈ 90조1,552억원</b> vs Reuters 8월 보도 약 <b>500억달러 ≈ 67조2,800억원</b>",
        "└ 차이 <b>170억달러 ≈ 22조8,752억원</b>의 산정 범위 확인 필요",
        "",
        "<b>알림 승격 조건</b>",
        "• 한국 투자액·배정액 확정 / SPA 체결 또는 HOA→SPA 전환·물량 변화 / FID·금융종결",
        "• 포스코·한국가스공사·EPC·강재·LNG선 본계약 / 세제·재산세·허가 해결",
        "• 단순 '한국 참여 압박' 반복과 관련주 급등은 제외",
        "기준: Reuters 2026-08-13 · Glenfarne 공식자료",
    ]


def _bootstrap(now: dt.datetime) -> str:
    parts = [
        "<b>🇺🇸 대미투자 | 텍사스 Encinal 6.3GW 협의 보도</b>",
        "",
        "<b>무엇이 바뀌었나</b>",
        "• 한국 언론을 통해 텍사스 Encinal에 <b>6.3GW 가스발전·223억달러</b> 규모 투자안이 논의된다는 보도가 나왔습니다.",
        "• Reuters 확인에서 한국 산업부는 해당 보도의 구체적 내용이 정확하지 않으며 <b>한미 협의가 진행 중이라 세부사항을 확정할 수 없다고 설명</b>했습니다.",
        "• 따라서 현재 단계는 <b>확정 프로젝트·확정 수주가 아니라 협의·검토 단계</b>로 관리합니다.",
        "",
        "<b>왜 중요한가</b>",
        "• AI 데이터센터 확대로 텍사스 전력수요가 급증하면서 발전소 자체를 새로 짓는 논의가 실제 정책·투자협상으로 연결되고 있습니다.",
        "• 현실화되면 가스터빈뿐 아니라 스팀터빈·HRSG·발전기·변압기·배전설비·가스관까지 매출 경로가 열립니다.",
        "",
    ]
    parts += _fixed_project_cost_block()
    parts += [""] + _texas_ai_power_block()
    parts += [""] + _safeguard_block()
    parts += [""] + _funding_guard_block()
    parts += [
        "",
        '<b>출처</b> · <a href="https://www.reuters.com/business/energy/south-korea-us-agree-more-than-20-billion-gas-plant-investment-texas-media-2026-09-07/">Reuters</a> · <a href="https://www.motir.go.kr/kor/article/ATCL3f49a5a8c/171196/view">산업통상부 MOU</a>',
        f"조회 {now.astimezone(KST).strftime('%Y-%m-%d %H:%M KST')} · 정부 최종문서가 나오면 확정 단계로 갱신",
    ]
    return "\n".join(parts)


def main() -> int:
    OUT.mkdir(exist_ok=True)
    DATA.mkdir(exist_ok=True)
    if ALERT.exists():
        ALERT.unlink()
    state = _load()
    now = dt.datetime.now(dt.timezone.utc)

    if not state.get("bootstrap"):
        ALERT.write_text(_bootstrap(now) + "\n", encoding="utf-8")
        state["bootstrap"] = True
        PENDING.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("bootstrap_alert=true")
        return 0

    seen = state.setdefault("seen", {})
    semantic_seen = state.setdefault("semantic_seen", {})
    rows = []
    for q in QUERIES:
        try:
            rows.extend(_rss(q))
        except Exception as exc:
            print(f"rss_error={type(exc).__name__}")

    rows.sort(key=lambda r: r["published"], reverse=True)
    fresh = []
    run_events: set[str] = set()
    for row in rows:
        key = _key(row)
        if key in seen:
            continue
        seen[key] = now.isoformat()

        semantic_key = _semantic_key(row)
        if semantic_key:
            previous = _parse_utc(str(semantic_seen.get(semantic_key) or ""))
            if previous and now - previous < dt.timedelta(hours=72):
                continue
            semantic_seen[semantic_key] = now.isoformat()

        event_key = _run_event_key(row)
        if event_key and event_key in run_events:
            continue
        if event_key:
            run_events.add(event_key)

        fresh.append(row)
        if len(fresh) >= 5:
            break

    PENDING.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not fresh:
        print("new_alerts=0")
        return 0

    saw_texas = False
    saw_alaska = False
    saw_safeguard = False
    saw_funding_guard = False
    tagged_rows: list[tuple[dict, list[str]]] = []
    for row in fresh:
        tags = _tags(row["title"], row["source"])
        tagged_rows.append((row, tags))
        if "텍사스 AI 전력" in tags or "1호/엔시날" in tags or "가스발전 설비" in tags:
            saw_texas = True
        if any(tag.startswith("알래스카 LNG") for tag in tags):
            saw_alaska = True
        if "수익배분/손실분담" in tags or "공식정정/정부입장" in tags:
            saw_safeguard = True
        if "송금절차/45영업일" in tags:
            saw_funding_guard = True

    if saw_safeguard:
        alert_title = "🇺🇸 대미투자·투자회수 안전판 | 최상위 중요 업데이트"
    elif saw_alaska and saw_texas:
        alert_title = "🇺🇸 대미투자·미국 에너지 | 중요 업데이트"
    elif saw_alaska:
        alert_title = "🇺🇸 대미투자·알래스카 LNG | 중요 업데이트"
    else:
        alert_title = "🇺🇸 대미투자·텍사스 AI 전력 | 중요 업데이트"

    parts = [f"<b>{alert_title}</b>", ""]
    for idx, (row, tags) in enumerate(tagged_rows, 1):
        parts += [
            f"<b>{idx}. {html.escape(row['title'])}</b>",
            f"• 🟧 <b>구분: {' / '.join(html.escape(x) for x in tags[:3])}</b>",
            f"• 의미: {html.escape(_meaning(tags))}",
            f"• 출처: <a href=\"{html.escape(row['link'], quote=True)}\">{html.escape(row['source'])}</a>",
            "",
        ]

    if saw_safeguard:
        parts += _safeguard_block()
        parts += [""]

    if saw_funding_guard:
        parts += _funding_guard_block()
        parts += [""]

    if saw_texas:
        parts += _texas_ai_power_block()
        parts += [""]

    if saw_alaska:
        parts += _alaska_lng_block()
        parts += [""]

    parts += _fixed_project_cost_block()
    parts += [
        "",
        f"조회 {now.astimezone(KST).strftime('%Y-%m-%d %H:%M KST')} · 공식자료 우선 · 단순 주가 반응·사설·반복 압박·동일 사건 중복 제외",
    ]
    ALERT.write_text("\n".join(parts) + "\n", encoding="utf-8")
    print(f"new_alerts={len(fresh)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())