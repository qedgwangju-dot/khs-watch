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
    '"대미투자" 관세 OR 301조 OR 232조 when:3d',
]

TRUSTED = [
    "산업통상", "연합뉴스", "뉴시스", "뉴스1", "이데일리", "헤럴드경제", "한국경제", "중앙일보",
    "머니투데이", "글로벌경제신문", "GetNews", "Reuters", "Yahoo", "Inside Climate News",
    "San Antonio Express-News", "Global Energy Monitor", "Pipeline & Gas Journal", "Bloomberg",
    "Utility Dive", "Glenfarne", "Alaska's News Source",
]

MATERIAL = [
    "확정", "의결", "합의", "계약", "체결", "승인", "허가", "착공", "증액", "감액", "사업비",
    "I-SPV", "PPA", "EPC", "가스터빈", "스팀터빈", "HRSG", "수주", "발전소", "가스발전",
    "현장발전", "데이터센터", "반도체", "원전", "LNG", "관세", "301조", "232조", "제외", "포함",
    "압박", "참여", "최종투자결정", "FID", "금융종결", "오프테이크", "구매계약", "SPA", "HOA",
    "MTPA", "세제", "재산세", "파이프라인", "Glenfarne", "POSCO", "포스코", "KOGAS", "한국가스공사",
    "gas power", "gas plant", "gas-fired", "combined-cycle", "data center", "turbine", "permit", "construction",
    "offtake", "financial close", "pipeline", "property tax", "6.3GW", "22.3 billion", "ERCOT", "behind-the-meter",
]

MARKET_REACTION_TERMS = [
    "강세", "급등", "상한가", "상승세", "주가", "관련주", "테마주", "株", "%↑", "% 상승",
]

HARD_PROGRESS_TERMS = [
    "확정", "의결", "계약", "체결", "승인", "허가", "착공", "fid", "최종투자결정",
    "financial close", "금융종결", "spa", "hoa", "오프테이크", "offtake", "구매계약",
    "투자액", "투자규모", "배정액", "지분", "사업비", "증액", "감액", "수주",
    "epc", "강재 공급", "mtpa", "만톤", "억달러", "조원", "재산세", "세제",
]

ALASKA_PRESSURE_TERMS = [
    "압박", "빨리", "서둘러", "참여하라", "참여 요구", "참여 촉구", "pressure", "urge", "urges",
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


def _tags(title: str) -> list[str]:
    low = title.lower()
    out = []
    for tag, terms in [
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
        "<b>💰 한미 대미투자 후보사업 기준 숫자</b>",
        "",
        "🔥 <b>텍사스 Encinal 가스복합발전</b>",
        "• 보도상 검토안: <b>6.3GW · 223억달러</b>",
        "└ GW당 <b>35.40억달러 ≈ 4조7,630억원</b>",
        "• <b>중요: 한국 산업부는 구체적 규모·참여가 확정되지 않았고 협의 중이라고 설명</b>",
        "",
        "⚛️ <b>미국 대형원전 후보</b>",
        "• 8기 · <b>1,200억달러 ≈ 161조4,720억원</b> 보도 기준",
        "",
        "🧊 <b>알래스카 LNG 후보</b>",
        "• <b>670억달러 ≈ 90조1,552억원</b> 한국 협상 보도 기준",
        "",
        "<b>⚠️ 숫자 해석</b>",
        "• 총사업비와 한국 정부 실제 투자액은 다를 수 있음",
        "• 미국 측·민간자금·프로젝트파이낸싱·지분구조를 분리 확인",
        "• 확정 수주로 간주하지 않고 정부 최종발표·국회 절차·본계약을 확인",
        "",
        "원화 환산 기준: 1달러=1,345.6원 · 기준값 고정, 후속 알림에서 최신 환율로 갱신 필요",
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
    parts += [
        "",
        '<b>출처</b> · <a href="https://www.reuters.com/business/energy/south-korea-us-agree-more-than-20-billion-gas-plant-investment-texas-media-2026-09-07/">Reuters</a> · <a href="https://www.yahoo.com/news/science/articles/data-center-developers-texas-plan-120000072.html">Yahoo/Inside Climate News</a>',
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

        fresh.append(row)
        if len(fresh) >= 5:
            break

    PENDING.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not fresh:
        print("new_alerts=0")
        return 0

    saw_texas = False
    saw_alaska = False
    tagged_rows: list[tuple[dict, list[str]]] = []
    for row in fresh:
        tags = _tags(row["title"])
        tagged_rows.append((row, tags))
        if "텍사스 AI 전력" in tags or "1호/엔시날" in tags or "가스발전 설비" in tags:
            saw_texas = True
        if any(tag.startswith("알래스카 LNG") for tag in tags):
            saw_alaska = True

    if saw_alaska and saw_texas:
        alert_title = "🇺🇸 대미투자·미국 에너지 | 중요 업데이트"
    elif saw_alaska:
        alert_title = "🇺🇸 대미투자·알래스카 LNG | 중요 업데이트"
    else:
        alert_title = "🇺🇸 대미투자·텍사스 AI 전력 | 중요 업데이트"

    parts = [f"<b>{alert_title}</b>", ""]
    for idx, (row, tags) in enumerate(tagged_rows, 1):
        parts += [
            f"<b>{idx}. {html.escape(row['title'])}</b>",
            f"• 구분: {' / '.join(html.escape(x) for x in tags[:3])}",
            f"• 의미: {html.escape(_meaning(tags))}",
            f"• 출처: <a href=\"{html.escape(row['link'], quote=True)}\">{html.escape(row['source'])}</a>",
            "",
        ]

    if saw_texas:
        parts += _texas_ai_power_block()
        parts += [""]

    if saw_alaska:
        parts += _alaska_lng_block()
        parts += [""]

    parts += _fixed_project_cost_block()
    parts += [
        "",
        f"조회 {now.astimezone(KST).strftime('%Y-%m-%d %H:%M KST')} · 단순 주가 반응·반복 압박 기사 제외",
    ]
    ALERT.write_text("\n".join(parts) + "\n", encoding="utf-8")
    print(f"new_alerts={len(fresh)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
