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
    '"Encinal" 1.4GW 4.9GW when:7d',
    '"한미전략투자" I-SPV OR SPV when:3d',
    '"대미투자" PPA OR EPC OR 가스터빈 when:3d',
    '"텍사스" "AI 데이터센터" 가스발전 when:3d',
    '"Texas" "data center" "gas power" when:3d',
    '"Texas" "data center" "gas plant" when:3d',
    '"Texas" data center combined-cycle turbine when:3d',
    '"ERCOT" 474GW data center when:7d',
    '"ERCOT" "Batch Zero" "Large Load" when:7d',
    '"ERCOT" large load interconnection energized approval when:7d',
    '"대미투자" 반도체 OR 삼성전자 OR SK하이닉스 when:3d',
    '"대미투자" 원전 OR AP1000 OR APR1400 when:3d',
    '"대미투자" "8기" 원전 when:3d',
    '"대미투자" "1천억달러" OR "100 billion" when:3d',
    '"대미투자" "합의 임박" OR "첫 사업" when:3d',
    '"대미투자" "20억달러" OR "2 billion" OR "첫 집행" when:3d',
    '"대미투자" "알래스카 LNG" when:3d',
    '"알래스카 LNG" 한국 참여 OR 투자 OR 압박 when:3d',
    '"Alaska LNG" Korea POSCO KOGAS when:3d',
    '"Alaska LNG" offtake OR FID OR financing when:7d',
    '"Alaska LNG" 13 MTPA OR 16 MTPA when:7d',
    '"Alaska LNG" tax OR property tax OR pipeline when:7d',
    '"대미투자" 수익배분 OR "위험 통합" OR risk-pooling when:3d',
    '"대미투자" "프로젝트별 손익" OR 손실분담 OR 원리금 when:3d',
    '"대미투자" "45영업일" OR "선정 통지" OR 송금 when:3d',
    '"대미투자" "45일 안전판" OR "조기 송금" OR 조기송금 OR 조기집행 when:3d',
    '"대미투자" "확정된 바 없습니다" OR 설명자료 when:3d',
    '"대미투자" 관세 OR 301조 OR 232조 when:3d',
]

TRUSTED = [
    "산업통상", "정책브리핑", "대한민국 정책브리핑", "재정경제부", "기획재정부",
    "연합뉴스", "뉴시스", "뉴스1", "이데일리", "헤럴드경제", "한국경제", "중앙일보", "머니투데이",
    "글로벌경제신문", "GetNews", "Reuters", "Wall Street Journal", "WSJ", "Yahoo",
    "Inside Climate News", "San Antonio Express-News", "Global Energy Monitor", "Pipeline & Gas Journal",
    "Bloomberg", "Utility Dive", "Glenfarne", "Alaska's News Source", "ERCOT", "PUCT", "Texas Governor",
]

MATERIAL = [
    "확정", "의결", "합의", "합의 임박", "계약", "체결", "승인", "허가", "착공", "증액", "감액", "사업비",
    "첫 사업", "첫사업", "I-SPV", "PPA", "EPC", "가스터빈", "스팀터빈", "HRSG", "수주", "발전소", "가스발전",
    "현장발전", "데이터센터", "반도체", "원전", "8기", "LNG", "관세", "301조", "232조", "제외", "포함",
    "압박", "참여", "최종투자결정", "FID", "금융종결", "오프테이크", "구매계약", "SPA", "HOA",
    "MTPA", "세제", "재산세", "파이프라인", "Glenfarne", "POSCO", "포스코", "KOGAS", "한국가스공사",
    "수익배분", "손실분담", "위험 통합", "risk-pooling", "프로젝트별 손익", "원리금", "상위 SPV",
    "투자 SPV", "손실 상계", "45영업일", "45일 안전판", "선정 통지", "자금 납입", "송금", "조기 송금",
    "조기송금", "조기 납입", "조기집행", "MOU 무시", "확정된 바 없습니다", "첫 집행", "첫 납입",
    "gas power", "gas plant", "gas-fired", "combined-cycle", "data center", "turbine", "permit", "construction",
    "offtake", "financial close", "pipeline", "property tax", "6.3GW", "1.4GW", "4.9GW", "22.3 billion",
    "100 billion", "1천억달러", "20억달러", "2 billion", "ERCOT", "474GW", "438GW", "Batch Zero",
    "Large Load", "interconnection", "energized", "approval", "audit", "behind-the-meter",
]

MARKET_REACTION_TERMS = ["강세", "급등", "상한가", "상승세", "주가", "관련주", "테마주", "株", "%↑", "% 상승"]
OPINION_TERMS = ["[사설]", "사설]", "오피니언", "칼럼", "기고"]
HARD_PROGRESS_TERMS = [
    "확정", "의결", "합의", "합의 임박", "계약", "체결", "승인", "허가", "착공", "fid", "최종투자결정",
    "financial close", "금융종결", "spa", "hoa", "오프테이크", "offtake", "구매계약", "투자액", "투자규모",
    "배정액", "지분", "사업비", "증액", "감액", "수주", "수익배분", "손실분담", "프로젝트별 손익", "원리금",
    "45영업일", "45일 안전판", "선정 통지", "자금 납입", "송금", "조기 송금", "조기송금", "조기 납입",
    "조기집행", "MOU 무시", "확정된 바 없습니다", "설명자료", "epc", "강재 공급", "mtpa", "만톤", "억달러",
    "조원", "재산세", "세제", "첫 사업", "첫사업", "1.4gw", "4.9gw", "474gw", "batch zero", "energized",
]
ALASKA_PRESSURE_TERMS = ["압박", "빨리", "서둘러", "참여하라", "참여 요구", "참여 촉구", "pressure", "urge", "urges"]
OFFICIAL_SOURCE_TERMS = [
    "정책브리핑", "산업통상", "재정경제부", "기획재정부", "대한민국 정책브리핑", "ercot", "puct", "texas governor",
]
SAFEGUARD_TERMS = [
    "수익배분", "손실분담", "위험 통합", "risk-pooling", "리스크 풀링", "프로젝트별 손익", "원리금",
    "상위 spv", "투자 spv", "손실 상계", "회수 구조", "투자회수",
]
FUNDING_GUARD_TERMS = [
    "45영업일", "45일 안전판", "선정 통지", "자금 납입", "자금납입", "capital call", "송금", "첫 집행",
    "첫 납입", "20억달러", "2 billion", "조기 송금", "조기송금", "조기 납입", "조기집행", "MOU 무시", "no less than",
]
FUNDING_CONFLICT_TERMS = ["45일 안전판", "45영업일", "조기 송금", "조기송금", "조기 납입", "조기집행", "MOU 무시", "no less than"]
ENERGY_PACKAGE_TERMS = [
    "1천억달러", "100 billion", "합의 임박", "agreement", "8기", "eight nuclear", "첫 사업", "첫사업", "first project",
]
ERCOT_QUEUE_TERMS = [
    "474gw", "438gw", "batch zero", "large load", "계통연계", "interconnection", "energized", "approval", "approved", "audit", "감사",
]
ENCINAL_STAGE_TERMS = ["1.4gw", "4.9gw", "단계적", "단계별", "순차", "증설", "1단계"]


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
    return any(t.lower() in low for t in MARKET_REACTION_TERMS) and not any(t.lower() in low for t in HARD_PROGRESS_TERMS)


def _is_low_value_opinion(title: str) -> bool:
    low = title.lower()
    return any(t.lower() in low for t in OPINION_TERMS) and not any(t.lower() in low for t in HARD_PROGRESS_TERMS)


def _is_official(row: dict) -> bool:
    blob = f"{row.get('title', '')} {row.get('source', '')}".lower()
    return any(term.lower() in blob for term in OFFICIAL_SOURCE_TERMS)


def _rss(query: str) -> list[dict]:
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"})
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
        if _is_simple_market_reaction(title) or _is_low_value_opinion(title):
            continue
        rows.append({"title": title, "source": source or "신뢰자료", "link": link, "published": published.isoformat()})
    return rows


def _key(row: dict) -> str:
    return hashlib.sha256(f"{row['title']}|{row['link']}".encode()).hexdigest()[:20]


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
    official = _is_official(row)
    if any(t.lower() in low for t in ENERGY_PACKAGE_TERMS) and ("대미투자" in low or "korea" in low or "south korea" in low):
        return "energy_package_official" if official else "energy_package_media"
    if any(t.lower() in low for t in ERCOT_QUEUE_TERMS):
        return "ercot_large_load_official" if official else "ercot_large_load_media"
    if ("엔시날" in low or "encinal" in low) and any(t.lower() in low for t in ENCINAL_STAGE_TERMS):
        return "encinal_stage"
    if any(t.lower() in low for t in FUNDING_CONFLICT_TERMS):
        return "funding_45day_official" if official else "funding_45day_media"
    alaska = "알래스카" in low or "alaska lng" in low
    if alaska:
        pressure = any(t.lower() in low for t in ALASKA_PRESSURE_TERMS)
        hard = any(t.lower() in low for t in HARD_PROGRESS_TERMS)
        if pressure and not hard:
            return "alaska_participation_pressure"
    return ""


def _run_event_key(row: dict) -> str:
    low = row["title"].lower()
    official = _is_official(row)
    if any(t.lower() in low for t in ENERGY_PACKAGE_TERMS) and ("대미투자" in low or "korea" in low or "south korea" in low):
        return "energy_package_official" if official else "energy_package_media"
    if any(t.lower() in low for t in ERCOT_QUEUE_TERMS):
        return "ercot_large_load_official" if official else "ercot_large_load_media"
    if ("엔시날" in low or "encinal" in low) and any(t.lower() in low for t in ENCINAL_STAGE_TERMS):
        return "encinal_stage"
    if any(t.lower() in low for t in FUNDING_CONFLICT_TERMS):
        return "funding_45day_official" if official else "funding_45day_media"
    if any(t.lower() in low for t in FUNDING_GUARD_TERMS):
        return "funding_official" if official else "funding_media"
    if any(t.lower() in low for t in SAFEGUARD_TERMS):
        return "safeguard_official" if official else "safeguard_media"
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
    if any(t.lower() in f"{low} {source_low}" for t in OFFICIAL_SOURCE_TERMS):
        if "설명자료" in low or "확정된 바 없습니다" in low or "사실이 아닙니다" in low or "정부 입장" in low:
            out.append("공식정정/정부입장")
    for tag, terms in [
        ("대미투자 첫사업/에너지패키지", ENERGY_PACKAGE_TERMS),
        ("ERCOT 신청/실수요 구분", ERCOT_QUEUE_TERMS),
        ("엔시날 단계증설", ENCINAL_STAGE_TERMS),
        ("수익배분/손실분담", ["수익배분", "손실분담", "위험 통합", "risk-pooling", "프로젝트별 손익", "원리금", "손실 상계", "투자회수"]),
        ("45영업일 적용충돌", FUNDING_CONFLICT_TERMS),
        ("송금절차/45영업일", ["45영업일", "45일", "선정 통지", "자금 납입", "자금납입", "capital call", "송금", "첫 집행", "첫 납입", "20억달러", "2 billion", "조기집행"]),
        ("1호/엔시날", ["엔시날", "encinal", "6.3gw"]),
        ("텍사스 AI 전력", ["texas", "텍사스", "data center", "데이터센터", "ercot"]),
        ("현장발전/오프그리드", ["behind-the-meter", "on-site", "현장발전", "자체발전", "off-grid", "byog"]),
        ("투자구조", ["i-spv", "spv", "지분", "소유권", "의결권"]),
        ("PPA/전력판매", ["ppa", "전력판매"]),
        ("한국기업 수주", ["epc", "가스터빈", "스팀터빈", "hrsg", "수주", "doosan", "두산"]),
        ("가스발전 설비", ["gas power", "gas plant", "gas-fired", "combined-cycle", "가스발전", "복합화력", "turbine"]),
        ("허가/착공", ["permit", "허가", "construction", "착공", "groundbreaking", "ercot", "interconnection", "energized"]),
        ("반도체", ["반도체", "삼성전자", "sk하이닉스"]),
        ("원전", ["원전", "ap1000", "apr1400", "8기", "westinghouse", "웨스팅하우스"]),
        ("알래스카 LNG 압박", ["압박", "참여하라", "참여 촉구", "빨리", "서둘러"]),
        ("알래스카 LNG 실질진전", ["fid", "최종투자결정", "financial close", "금융종결", "offtake", "오프테이크", "spa", "hoa", "mtpa", "재산세"]),
        ("알래스카 LNG", ["알래스카", "alaska lng"]),
        ("관세", ["301조", "232조", "관세"]),
        ("사업비", ["사업비", "증액", "감액", "22.3 billion", "223억", "220억", "1천억달러", "100 billion"]),
    ]:
        if any(str(t).lower() in low for t in terms):
            out.append(tag)
    return out or ["대미투자·AI전력"]


def _meaning(tags: list[str]) -> str:
    if "공식정정/정부입장" in tags:
        return "언론 제목보다 정부 공식 설명자료를 우선해 확정·미확정 상태를 갱신해야 합니다."
    if "대미투자 첫사업/에너지패키지" in tags:
        return "1천억달러+ 에너지 패키지·원전 최대 8기·첫 자금 집행은 협상 단계와 집행 시간표를 바꾸는 고신호입니다. 보도와 정부 공식 확정을 분리합니다."
    if "ERCOT 신청/실수요 구분" in tags:
        return "474GW는 계통연계 요청이지 확정 실수요가 아닙니다. 감사·연계요건 충족·전원 인가 승인·실제 가동 순으로 단계 상승을 추적합니다."
    if "엔시날 단계증설" in tags:
        return "엔시날은 1.4GW를 먼저 건설해 수요·경제성을 검증한 뒤 4.9GW 복합화력을 증설하는 구조입니다. PPA와 후속 발주가 2단계 촉발 요인입니다."
    if "수익배분/손실분담" in tags:
        return "risk-pooling 유지 여부·원리금 회수·손실 상계 범위가 2,000억달러 투자의 실제 위험을 바꿉니다."
    if "45영업일 적용충돌" in tags:
        return "공개 MOU에는 최소 45영업일 문구가 존재하므로, 조기송금 보도는 실제 적용·별도 합의 여부를 확인해야 합니다."
    if "송금절차/45영업일" in tags:
        return "선정일·한국 통보일·별도 조기집행 합의·운영위 의결·실제 송금일과 금액을 순서대로 확인해야 합니다."
    if "1호/엔시날" in tags:
        return "6.3GW·220억~223억달러 검토안의 정부 확정 여부와 한국 실제 투자부담이 핵심입니다."
    if "텍사스 AI 전력" in tags:
        return "데이터센터 전력 부족이 발전·변전 설비 투자로 연결되는지 PPA·계통연계·전원 인가 기준으로 확인합니다."
    if "현장발전/오프그리드" in tags:
        return "전력망 접속을 기다리지 않고 현장에서 먼저 전원을 인가하는 설비가 AI 증설 속도를 좌우합니다."
    if "투자구조" in tags:
        return "지분·의결권·손실분담이 실제 투자 회수액과 위험을 바꿉니다."
    if "PPA/전력판매" in tags:
        return "계약 GW·기간·가격이 잠기면 발전소 현금흐름을 계산할 수 있습니다."
    if "한국기업 수주" in tags:
        return "본계약부터 국내 기업의 수주잔고·매출로 연결됩니다."
    if "가스발전 설비" in tags:
        return "실제 납기와 공급 슬롯이 중요해져 가스터빈·스팀터빈·HRSG·발전기 발주 시점이 매출을 결정합니다."
    if "허가/착공" in tags:
        return "발표 GW보다 허가·계통연계·착공·전원 인가 시점이 실제 매출과 가동률을 결정합니다."
    if "반도체" in tags:
        return "미국 팹이 구체화되면 관세우대와 국내 설비투자 분산을 함께 봐야 합니다."
    if "원전" in tags:
        return "노형·기수·사업 주도권에 따라 한국의 시공·기자재·운영 몫이 달라집니다."
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
        "<b>💰 대미투자 프로젝트 기준 사업비</b>", "",
        "🔥 <b>엔시날 가스발전</b>",
        "• 6.3GW · 보도 범위 <b>220억~223억달러 ≈ 29조5,249억~29조9,275억원</b>",
        "└ 223억달러 기준 GW당 <b>35.40억달러 ≈ 4조7,509억원</b>", "",
        "⚛️ <b>미국 대형원전</b>",
        "• 최대 8기 · 기존 보도상 <b>1,200억달러 ≈ 161조448억원</b>",
        "└ 기당 <b>150억달러 ≈ 20조1,306억원</b>", "",
        "🟧 <b>WSJ 2026-09-10 에너지 패키지 신호</b>",
        "• 원전 최대 8기+텍사스 가스발전 포함 <b>1,000억달러 초과 ≈ 134조2,040억원 초과</b>",
        "• 이달 초기 집행 <b>20억달러 초과 ≈ 2조6,841억원 초과</b> 가능성 보도",
        "• 전략투자 실제 납입 한도: <b>총 2,000억달러 / 연 200억달러</b>", "",
        "<b>⚠️ 꼭 구분할 숫자</b>",
        "• 총사업비 ≠ 한국 정부 실제 송금액 ≠ 한국 기업 수주액",
        "• 1,000억달러 초과는 패키지 하한 표현이며 원전 8기+엔시날 단순합 확정치가 아님",
        "• 정부 최종발표·국회 절차·본계약 전에는 확정 수주로 간주하지 않음", "",
        "원화 환산 기준: 1달러=1,342.04원 · 2026-09-10 17:26 KST 기준값",
    ]


def _safeguard_block() -> list[str]:
    return [
        "<b>🛡️ 대미투자 안전판·원금회수 기준선</b>",
        "• 2025-11-14 MOU 기준: 상위 투자 SPV가 개별 프로젝트 SPV 수익을 모아 <b>한국 원금+이자를 상환하는 risk-pooling 구조</b>",
        "• 특정 프로젝트 손실을 다른 성공 프로젝트 수익으로 보전할 수 있도록 설계",
        "• 원리금 상환 전 수익배분 <b>한·미 5:5</b> → 상환 후 <b>한국 1 : 미국 9</b>",
        "• <b>20년 내 전체 원리금 상환이 어려우면 수익배분 비율 조정 가능</b>",
        "• 상환이자: 미국 국채 20년물 고정금리 + 가산금리, 가산금리 상한 존재", "",
        "<b>🚨 2026-09-10 정부 공식상태</b>",
        "• 산업통상부·재정경제부: <b>수익배분 구조와 구체 투자내용은 한미 협의 중이며 아직 확정되지 않음</b>",
        "• 따라서 언론의 '합의 임박·첫 사업'과 정부 공식 확정을 별도 단계로 관리", "",
        "<b>다음 확인</b>",
        "1) risk-pooling 유지/폐기  2) 손실 상계 허용 범위  3) 원리금 상환 순서  4) 프로젝트별 수익배분  5) 이자율·가산금리",
    ]


def _funding_guard_block() -> list[str]:
    return [
        "<b>⏱️ 45영업일·첫 자금 집행 기준선</b>",
        "• 📜 <b>문서상 원칙</b>: 공개 MOU에는 미국의 투자처 선정 통지 후 <b>최소 45영업일 경과 뒤</b> 사업자금 납입 문구가 존재",
        "• ⚠️ <b>WSJ 2026-09-10</b>: 이달 <b>20억달러 초과 초기 집행 가능성</b> 보도 → 실제 적용·별도 합의 여부 확인 필요",
        "• 🏛 <b>정부 공식상태</b>: 첫 송금 규모·시기 및 세부 투자내용은 아직 확정되지 않았다는 입장",
        "• 전략투자 실제 납입은 <b>연간 최대 200억달러</b>이며 사업 진척도에 따른 <b>자금요청(capital call)</b> 방식",
        "• 외환시장 불안 우려 시 한국은 <b>납입 시기·규모 조정 요구 가능</b>", "",
        "<b>다음 확인</b>",
        "1) 미국 대통령 사업 선정일  2) 한국 통보일  3) 조기집행 별도 합의·운영해석  4) 국내 운영위 의결  5) 실제 송금일·금액",
    ]


def _energy_package_block() -> list[str]:
    return [
        "<b>🟧 대미투자 첫사업·에너지 패키지 기준선</b>",
        "• WSJ/Reuters 2026-09-10: 한국이 <b>1,000억달러 초과</b> 미국 에너지 투자 패키지 합의에 근접했다는 보도",
        "• 후보 범위: <b>텍사스 가스발전 + 대형원전 최대 8기</b>",
        "• 원전은 초기 Westinghouse 기술, 후속 한국 설계 가능성이 보도됐으나 <b>노형·기수·발주주체는 미확정</b>",
        "• 이르면 다음 주 발표 가능성 보도와 정부 공식 확정을 별도 사건으로 추적", "",
        "<b>알림 승격 조건</b>",
        "1) 정부 공식 첫 사업 선정  2) 투자금·지분·수익배분 확정  3) 원전 부지·노형·기수 확정  4) 실제 첫 자금요청·송금",
    ]


def _texas_ai_power_block() -> list[str]:
    return [
        "<b>⚡ 텍사스 AI 전력·계통연계 기준선</b>",
        "• 텍사스 주지사 2026-08-03: ERCOT 대형부하 계통연계 요청 <b>474GW+</b>, 텍사스 기록적 피크수요의 <b>5배 초과</b>",
        "• 신규 요청의 약 <b>90%</b>가 데이터센터로 집계",
        "• 단, <b>474GW는 신청·요청 물량이지 접속 확정 또는 실제 소비전력이 아님</b>",
        "• ERCOT 2026-04 공식 기준: 신청 445.8GW 중 <b>321GW는 연구 미제출</b>, <b>93.7GW 검토 중</b>, <b>22GW 요건 충족</b>",
        "• 같은 공식 기준 실제 단계: <b>관측 전원 인가 5.9GW + 전원 인가 승인·미가동 3.2GW</b>", "",
        "<b>정책·공정 병목</b>",
        "• Abbott 주지사 지침: 데이터센터 감사가 끝나기 전 프로젝트를 진전시키지 않으며 기준 미충족 시 계통연계 거절",
        "• ERCOT는 Batch Zero로 대형부하를 일괄 심사하며 전압 유지·계통 안정성 요건을 강화", "",
        "<b>엔시날 단계증설</b>",
        "• 총 6.3GW 중 <b>1단계 1.4GW 가스터빈</b>을 먼저 건설해 실제 수요·경제성을 확인",
        "• 이후 <b>4.9GW 복합화력</b>을 순차 증설하는 구상",
        "• 따라서 474GW 신청 증가보다 <b>AI 고객 실명·PPA·전원 인가·1.4GW 발주·4.9GW 후속 승인</b>이 더 중요한 촉발 요인", "",
        "<b>다음 확인</b>",
        "1) Encinal 정부 공식 확정  2) AI 고객 실명·PPA  3) 1.4GW 가스터빈 제조사  4) 4.9GW HRSG·스팀터빈 발주  5) 가스관·환경허가·전원 인가",
    ]


def _alaska_lng_block() -> list[str]:
    return [
        "<b>🧊 알래스카 LNG 실질 진전 기준선</b>",
        "• 수출설비: <b>20MTPA</b> · 금융종결 목표 <b>16MTPA(80%)</b>",
        "• Reuters 2026-08-13: 확보 약정 <b>13MTPA</b> → 추가 <b>3MTPA</b> 필요",
        "• 포스코인터내셔널: <b>1MTPA × 20년</b> + 최종투자결정 전 투자 + 42인치 가스관 강재 공급",
        "• 일정 기준선: 가스관 기계적 완공 2028년 · 첫 가스 2029년 · LNG 수출 목표 2031년", "",
        "<b>알림 승격 조건</b>",
        "• 한국 투자액·배정액 확정 / SPA 체결 또는 HOA→SPA 전환·물량 변화 / FID·금융종결",
        "• 포스코·한국가스공사·EPC·강재·LNG선 본계약 / 세제·재산세·허가 해결",
        "• 단순 '한국 참여 압박' 반복과 관련주 급등은 제외",
    ]


def _bootstrap(now: dt.datetime) -> str:
    parts = [
        "<b>🇺🇸 대미투자 | 텍사스 Encinal 6.3GW 협의 보도</b>", "",
        "<b>무엇이 바뀌었나</b>",
        "• 텍사스 Encinal에 <b>6.3GW 가스발전·220억~223억달러</b> 규모 투자안이 논의되고 있습니다.",
        "• 한국 정부는 구체적 사업 내용과 금액이 아직 확정되지 않았다는 입장을 유지합니다.",
        "• 따라서 현재 단계는 <b>확정 프로젝트·확정 수주가 아니라 협의·검토 단계</b>로 관리합니다.", "",
    ]
    parts += _fixed_project_cost_block()
    parts += [""] + _energy_package_block()
    parts += [""] + _texas_ai_power_block()
    parts += [""] + _safeguard_block()
    parts += [""] + _funding_guard_block()
    parts += [
        "",
        '<b>출처</b> · <a href="https://www.reuters.com/business/energy/south-korea-us-agree-more-than-20-billion-gas-plant-investment-texas-media-2026-09-07/">Reuters</a> · <a href="https://gov.texas.gov/news/post/governor-abbott-directs-comprehensive-data-center-audit">Texas Governor</a>',
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
    saw_funding_conflict = False
    saw_energy_package = False
    tagged_rows: list[tuple[dict, list[str]]] = []

    for row in fresh:
        tags = _tags(row["title"], row["source"])
        tagged_rows.append((row, tags))
        if "텍사스 AI 전력" in tags or "1호/엔시날" in tags or "가스발전 설비" in tags or "ERCOT 신청/실수요 구분" in tags or "엔시날 단계증설" in tags:
            saw_texas = True
        if any(tag.startswith("알래스카 LNG") for tag in tags):
            saw_alaska = True
        if "수익배분/손실분담" in tags or "공식정정/정부입장" in tags:
            saw_safeguard = True
        if "송금절차/45영업일" in tags or "45영업일 적용충돌" in tags:
            saw_funding_guard = True
        if "45영업일 적용충돌" in tags:
            saw_funding_conflict = True
        if "대미투자 첫사업/에너지패키지" in tags:
            saw_energy_package = True

    if saw_energy_package and (saw_safeguard or saw_funding_guard):
        alert_title = "🇺🇸 대미투자 첫사업·에너지 패키지 | 최상위 중요 업데이트"
    elif saw_energy_package:
        alert_title = "🇺🇸 대미투자 첫사업·에너지 패키지 | 중요 업데이트"
    elif saw_safeguard and saw_funding_conflict:
        alert_title = "🇺🇸 대미투자·회수·집행 안전판 | 최상위 중요 업데이트"
    elif saw_safeguard:
        alert_title = "🇺🇸 대미투자·투자회수 안전판 | 최상위 중요 업데이트"
    elif saw_funding_conflict:
        alert_title = "🇺🇸 대미투자·45영업일·조기송금 | 최상위 중요 업데이트"
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

    if saw_energy_package:
        parts += _energy_package_block() + [""]
    if saw_safeguard:
        parts += _safeguard_block() + [""]
    if saw_funding_guard:
        parts += _funding_guard_block() + [""]
    if saw_texas:
        parts += _texas_ai_power_block() + [""]
    if saw_alaska:
        parts += _alaska_lng_block() + [""]

    parts += _fixed_project_cost_block()
    parts += ["", f"조회 {now.astimezone(KST).strftime('%Y-%m-%d %H:%M KST')} · 공식자료 우선 · 신청≠승인≠전원 인가≠실제 가동 · 단순 주가 반응·사설·동일 사건 중복 제외"]
    ALERT.write_text("\n".join(parts) + "\n", encoding="utf-8")
    print(f"new_alerts={len(fresh)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
