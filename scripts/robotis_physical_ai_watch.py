#!/usr/bin/env python3
"""High-signal physical-AI / robotics supply-chain watcher.

Tracks four investment-relevant lanes:
1) ROBOTIS / DYNAMIXEL / AI Sapiens / Pollen Robotics / logistics deployments
2) Korean battery materials and cells entering humanoid-robot supply chains
3) Tesla Optimus supplier orders, production ramp, yield and capacity
4) BYD / PaXini tactile sensing, dexterous hands and factory-data flywheel

Google News RSS is the broad discovery layer. The first scheduled run seeds a
baseline; later runs only emit genuinely new, high-signal items. FORCE_SUMMARY=1
emits a current diversified summary for manual testing.
"""
from __future__ import annotations

import datetime as dt
import email.utils
import hashlib
import html
import json
import os
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "robotis_physical_ai_watch_state.json"
OUT_DIR = ROOT / "out"
PENDING_PATH = OUT_DIR / "robotis_physical_ai_watch_pending_state.json"
ALERT_PATH = OUT_DIR / "robotis_physical_ai_watch_telegram.txt"
STATUS_PATH = OUT_DIR / "robotis_physical_ai_watch_status.md"

KST = ZoneInfo("Asia/Seoul")
NOW = dt.datetime.now(dt.timezone.utc)
FORCE = os.getenv("FORCE_SUMMARY", "").strip().lower() in {"1", "true", "yes", "on"}
MAX_ALERTS = 8

QUERIES = [
    # ROBOTIS / DYNAMIXEL / actual deployment
    '로보티즈 (휴머노이드 OR "AI 사피엔스" OR K1 OR "AI Worker" OR 액추에이터 OR 다이나믹셀 OR 우즈베키스탄 OR CJ대한통운)',
    'ROBOTIS (humanoid OR "AI Sapiens" OR K1 OR DYNAMIXEL OR actuator OR Uzbekistan OR "CJ Logistics")',
    '(Microduck OR "Reachy Mini") (ROBOTIS OR Dynamixel OR actuator OR "Pollen Robotics")',
    '("Pollen Robotics" OR "Hugging Face") (Dynamixel OR ROBOTIS OR Microduck OR actuator)',
    '("Goldman Sachs" OR 골드만삭스) (ROBOTIS OR 로보티즈 OR Microduck OR actuator OR 액추에이터)',
    '로보티즈 (블록딜 OR 외국계 OR 기관 OR 지분 OR 수주잔고 OR 생산능력 OR 출하량 OR 완판 OR 공급계약 OR 양산)',
    '(DYNAMIXEL-Q OR "DYNAMIXEL Q" OR XL330) (humanoid OR robot OR Microduck OR 로봇)',

    # Korean battery -> humanoid / physical AI supply chain
    '(휴머노이드 OR humanoid OR 피지컬AI OR "physical AI") (배터리 OR battery OR 하이니켈 OR "high nickel" OR 전고체 OR "solid-state") (에코프로 OR EcoPro OR LG에너지솔루션 OR "LG Energy Solution" OR 삼성SDI OR "Samsung SDI" OR SK온 OR "SK On" OR 포스코퓨처엠 OR "POSCO Future M" OR 엘앤에프 OR L&F)',
    '(EcoPro OR 에코프로) (humanoid OR 휴머노이드 OR robot OR 로봇) (battery OR 배터리 OR high-nickel OR 하이니켈 OR sulfide OR 황화물 OR solid-state OR 전고체)',
    '"Korean Battery Sector" humanoid robots EcoPro',

    # Tesla Optimus production / supplier orders / yield
    '(Tesla OR 테슬라) (Optimus OR 옵티머스) (supplier OR 공급업체 OR 공급망 OR order OR 발주 OR 주문 OR 양산 OR 생산 OR 수율 OR yield OR capacity OR 생산능력 OR shipment OR 출하)',
    '(特斯拉 OR Tesla) (Optimus OR 擎天柱) (5000 OR 订单 OR 供应商 OR 量产 OR 良率 OR 产能 OR 出货)',
    '(Optimus OR 옵티머스) (5000 OR 5,000 OR 수천 OR batch OR 일괄 OR 대량) (order OR 발주 OR 주문 OR supplier OR 공급업체)',

    # BYD / PaXini tactile-data flywheel
    '(BYD OR 비야디 OR 比亚迪) (PaXini OR 파시니 OR 帕西尼) (robot OR 로봇 OR 机器人 OR tactile OR 촉각 OR 触觉 OR data OR 데이터 OR 数据 OR factory OR 공장 OR 工厂)',
    '(PaXini OR 帕西尼) (BYD OR 比亚迪) (dexterous hand OR 로봇손 OR 灵巧手 OR tactile sensor OR 촉각센서 OR 触觉传感器)',
]

OFFICIAL_OR_PRIMARY = {
    "ROBOTIS", "CJ대한통운", "Pollen Robotics", "Hugging Face", "EcoPro",
    "에코프로", "BYD", "比亚迪", "Tesla",
}

TRUSTED = {
    "Reuters", "Bloomberg", "블룸버그", "The Wall Street Journal", "Financial Times",
    "파이낸셜뉴스", "연합뉴스", "한국경제", "매일경제", "전자신문",
    "ZDNet Korea", "시사저널e", "뉴스핌", "로봇신문", "서울경제",
    "界面新闻", "Jiemian", "Jiemian Global", "第一财经", "新浪财经",
    "The Auto Wire", "CnEVPost",
}

LOW_QUALITY_SOURCES = {
    "데일리머니",
}

HIGH = [
    r"공급계약|수주|주문|수주잔고|backlog|order|contract|supply|발주|订单",
    r"양산|생산능력|캐파|capa|capacity|factory|plant|공장|출하|shipment|production|产能|量产|出货",
    r"고객|customer|채택|adopt|qualification|인증|검증|deployment|투입|배치|供应商",
    r"완판|sold out|예약|preorder|사전주문|판매|launch|출시",
    r"액추에이터|actuator|DYNAMIXEL|다이나믹셀|XL330|DYNAMIXEL-Q",
    r"Microduck|Reachy Mini|Pollen Robotics|Hugging Face",
    r"AI 사피엔스|AI Sapiens|\bK1\b|AI Worker|세미 휴머노이드|humanoid|휴머노이드",
    r"우즈베키스탄|Uzbekistan|CJ대한통운|CJ Logistics|올리브영|Olive Young",
    r"Goldman Sachs|골드만삭스|목표주가|price target|리포트|report",
    r"블록딜|block deal|외국계|기관|institution|지분|stake|5%",
    r"배터리|battery|하이니켈|high[- ]nickel|전고체|solid[- ]state|황화물|sulfide|에너지 밀도|energy density",
    r"Optimus|옵티머스|擎天柱|5000|5,000|수천|良率|yield|주간 생산|weekly production",
    r"BYD|비야디|比亚迪|PaXini|파시니|帕西尼|촉각|tactile|灵巧手|dexterous hand|로봇손|데이터|data",
]

NUMERIC = re.compile(
    r"(?:\b\d+(?:\.\d+)?\s*(?:만|억|조|백만|million|billion|%|대|개|달러|원|USD|KRW|톤|GWh|MWh)\b|"
    r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b)", re.I
)

TITLE_NOISE = re.compile(
    r"오늘의 종목|급등주|상한가 종목|테마주 정리|관련주 정리|단순 추천|"
    r"stock to buy|top stocks|technical analysis", re.I
)

DIRECT_EVENT = re.compile(
    r"공급계약|수주|발주|주문|order|contract|양산|생산|production|출하|shipment|"
    r"배치|투입|deployment|협력|partnership|전략적 협력|상업 생산|commercial production|"
    r"수율|yield|생산능력|capacity|공장|factory|지분|stake|블록딜|block deal|"
    r"완판|sold out|예약|preorder|订单|量产|良率|合作", re.I
)


def fetch(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 khs-watch/2.0",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def norm(v: str | None) -> str:
    v = html.unescape(v or "")
    v = re.sub(r"<[^>]+>", " ", v)
    return re.sub(r"\s+", " ", v).strip()


def parse_date(v: str | None) -> dt.datetime | None:
    if not v:
        return None
    try:
        x = email.utils.parsedate_to_datetime(v)
        if x.tzinfo is None:
            x = x.replace(tzinfo=dt.timezone.utc)
        return x.astimezone(dt.timezone.utc)
    except Exception:
        return None


def query_news(q: str) -> list[dict]:
    p = urllib.parse.urlencode({"q": q, "hl": "ko", "gl": "KR", "ceid": "KR:ko"})
    root = ET.fromstring(fetch(f"https://news.google.com/rss/search?{p}"))
    out: list[dict] = []
    for it in root.findall("./channel/item")[:35]:
        title = norm(it.findtext("title"))
        link = norm(it.findtext("link"))
        desc = norm(it.findtext("description"))
        pub = parse_date(it.findtext("pubDate"))
        src_node = it.find("source")
        src = norm(src_node.text if src_node is not None else "")
        if title and link:
            out.append({
                "title": title,
                "link": link,
                "description": desc,
                "published": pub.isoformat() if pub else None,
                "source": src,
            })
    return out


def key(item: dict) -> str:
    title = re.sub(r"\s+-\s+[^-]+$", "", item["title"].lower()).strip()
    base = f"{title}|{item.get('source','').lower()}"
    return hashlib.sha256(base.encode()).hexdigest()


def topic_group(text: str) -> str | None:
    if re.search(r"로보티즈|ROBOTIS|DYNAMIXEL|다이나믹셀|Microduck|Reachy Mini|Pollen Robotics", text, re.I):
        return "robotis"

    battery_company = re.search(
        r"에코프로|EcoPro|LG에너지솔루션|LG Energy Solution|삼성SDI|Samsung SDI|SK온|SK On|"
        r"포스코퓨처엠|POSCO Future M|엘앤에프|L&F|한국 배터리|Korean Battery", text, re.I
    )
    battery_robot = re.search(
        r"휴머노이드|humanoid|피지컬AI|physical AI|robot|로봇", text, re.I
    )
    battery_term = re.search(
        r"배터리|battery|하이니켈|high[- ]nickel|전고체|solid[- ]state|황화물|sulfide|양극재|음극재|전해질", text, re.I
    )
    if battery_company and battery_robot and battery_term:
        return "battery"

    if re.search(r"Tesla|테슬라|特斯拉", text, re.I) and re.search(r"Optimus|옵티머스|擎天柱", text, re.I):
        return "tesla"

    if re.search(r"BYD|비야디|比亚迪", text, re.I) and re.search(r"PaXini|파시니|帕西尼", text, re.I):
        return "byd_paxini"

    return None


def score(item: dict) -> int:
    title = item["title"]
    text = f"{title} {item.get('description','')} {item.get('source','')}"
    source = item.get("source") or ""
    group = topic_group(text)
    if group is None:
        return -20
    if source in LOW_QUALITY_SOURCES:
        return -30
    if TITLE_NOISE.search(title) and not DIRECT_EVENT.search(text):
        return -20

    s = {
        "robotis": 6,
        "battery": 7,
        "tesla": 8,
        "byd_paxini": 7,
    }[group]

    for pat in HIGH:
        if re.search(pat, text, re.I):
            s += 1
    if NUMERIC.search(text):
        s += 3
    if source in OFFICIAL_OR_PRIMARY:
        s += 5
    elif source in TRUSTED:
        s += 3
    if DIRECT_EVENT.search(text):
        s += 4

    if group == "tesla" and re.search(r"5000|5,000|수천|千台|订单|batch|발주|주문", text, re.I):
        s += 5
    if group == "battery" and re.search(r"상업 생산|commercial production|40톤|하이니켈|high[- ]nickel|전고체|solid[- ]state", text, re.I):
        s += 4
    if group == "byd_paxini" and re.search(r"공장|factory|工厂|데이터|data|数据|촉각|tactile|触觉|지분|stake", text, re.I):
        s += 4
    if group == "robotis" and re.search(r"수주|고객|양산|출하|완판|생산능력|우즈베키스탄|블록딜", text, re.I):
        s += 4
    return s


def category(text: str, group: str) -> str:
    if group == "battery":
        return "휴머노이드 배터리 공급망"
    if group == "tesla":
        if re.search(r"5000|5,000|수천|order|주문|발주|订单", text, re.I):
            return "Optimus 양산·발주"
        return "Optimus 생산·공급망"
    if group == "byd_paxini":
        return "촉각·로봇 데이터"

    if re.search(r"블록딜|block deal|외국계|institution|지분|stake", text, re.I):
        return "수급·지분"
    if re.search(r"Goldman Sachs|골드만삭스|목표주가|price target|리포트", text, re.I):
        return "리서치·재평가"
    if re.search(r"우즈베키스탄|Uzbekistan|생산능력|capa|capacity|공장|factory|plant", text, re.I):
        return "생산능력·원가"
    if re.search(r"CJ대한통운|CJ Logistics|올리브영|Olive Young|투입|배치|deployment", text, re.I):
        return "현장 배치·고객 검증"
    if re.search(r"공급계약|수주|order|contract|customer|고객|납품|supply", text, re.I):
        return "수주·고객"
    if re.search(r"Microduck|Reachy Mini|Pollen Robotics|XL330", text, re.I):
        return "대당 액추에이터 탑재가치"
    if re.search(r"AI 사피엔스|AI Sapiens|\bK1\b|완판|sold out|판매|launch", text, re.I):
        return "완제품·플랫폼"
    return "액추에이터·피지컬AI"


def tag_for(group: str) -> str:
    return {
        "robotis": "로보티즈",
        "battery": "배터리",
        "tesla": "테슬라옵티머스",
        "byd_paxini": "촉각·로봇데이터",
    }[group]


def meaning(cat: str) -> str:
    mapping = {
        "휴머노이드 배터리 공급망": "EV 외 수요처가 휴머노이드로 넓어지는 신호입니다. 고에너지 밀도·경량화 요구가 하이니켈·전고체 소재의 신규 매출 경로로 이어지는지 봅니다.",
        "Optimus 양산·발주": "샘플·시험물량에서 배치 단위 발주로 넘어가는 신호입니다. 공급업체 생산능력 확대와 실제 부품 매출의 시간표를 앞당길 수 있습니다.",
        "Optimus 생산·공급망": "Fremont 생산라인 수율·주간 생산량·내부 출하가 공급망 주문으로 연결되는지 확인하는 신호입니다.",
        "촉각·로봇 데이터": "BYD 공장이 PaXini의 실제 산업 검증·데이터 수집장으로 바뀌는 구조입니다. 촉각센서·로봇손뿐 아니라 현장 데이터 자체가 자산화되는지 봅니다.",
        "수급·지분": "본업 매출보다 외국인·기관 수급과 오버행을 바꾸는 신호입니다. 기관 실명·보호예수·추가 지분변동을 확인합니다.",
        "리서치·재평가": "로봇 출하량뿐 아니라 로봇 1대당 액추에이터 수·탑재금액이 늘어나는 이중 물량 레버리지를 숫자로 확인하는 신호입니다.",
        "생산능력·원가": "현재 수요보다 생산능력이 병목인지를 확인합니다. 실제 가동률·수율·외부 OEM 주문이 매출과 총자산이익률을 좌우합니다.",
        "현장 배치·고객 검증": "연구용 시연에서 실제 물류·산업 작업으로 넘어가는 신호입니다. 소수 실증이 수십·수백대로 확대되는지가 핵심입니다.",
        "수주·고객": "테마가 실제 고객·수주·반복발주로 바뀌는 가장 강한 매출 확인 신호입니다.",
        "대당 액추에이터 탑재가치": "로봇 고도화로 관절 수가 늘면 완제품 출하 증가와 별개로 로봇 1대당 ROBOTIS 부품 매출 기회가 커집니다.",
        "완제품·플랫폼": "K1 자체 매출보다 연구자가 DYNAMIXEL-Q와 제어환경에 락인돼 향후 외부 OEM 액추에이터 수요로 이어지는지가 중요합니다.",
        "액추에이터·피지컬AI": "DYNAMIXEL이 연구용 부품에서 휴머노이드 양산 부품으로 전환되는지를 확인하는 신호입니다.",
    }
    return mapping[cat]


def risk(cat: str) -> str:
    mapping = {
        "휴머노이드 배터리 공급망": "아직 휴머노이드 대량 양산이 초기 단계라 소재 채택·셀 규격·고객 실명이 확정되지 않으면 실제 매출까지 시간이 걸릴 수 있습니다.",
        "Optimus 양산·발주": "공급망 보도는 Tesla 공식 발주 공시와 다릅니다. 공급업체 실명·수량·납기·실제 출하를 추가 확인해야 합니다.",
        "Optimus 생산·공급망": "생산 수율이 계획보다 늦게 오르면 부품 발주와 공급업체 증설이 함께 지연될 수 있습니다.",
        "촉각·로봇 데이터": "전략협력과 대규모 상용매출은 다릅니다. 실제 로봇 배치 대수·데이터 유료화·촉각센서 반복수주를 확인해야 합니다.",
        "생산능력·원가": "증설보다 고객 채택이 늦으면 감가상각·운전자본 부담이 먼저 커질 수 있습니다.",
        "현장 배치·고객 검증": "작업 성공률·가동률·안전 검증이 낮으면 고객 확대가 지연될 수 있습니다.",
        "수급·지분": "클럽딜·외국계 인수만으로 장기 보유를 확정할 수 없으며 보호예수 미확인이 핵심 역풍입니다.",
        "리서치·재평가": "증권사 탑재가치는 실제 OEM 납품단가가 아니며 액추에이터 평균판매단가 상승과 혼동하면 안 됩니다.",
        "대당 액추에이터 탑재가치": "대량양산 과정에서 저가 대체품이나 자체 액추에이터로 전환되면 탑재가치가 낮아질 수 있습니다.",
        "수주·고객": "수주 규모·납기·반복 주문이 작으면 테마 대비 실적 민감도가 낮을 수 있습니다.",
        "완제품·플랫폼": "초기 연구용 수요가 산업용 대량 주문으로 이어지지 않으면 자체 완제품 매출은 제한적일 수 있습니다.",
        "액추에이터·피지컬AI": "실제 고객명·납품량·반복주문이 확인되지 않으면 기대감에 그칠 수 있습니다.",
    }
    return mapping[cat]


def verification(item: dict, group: str, text: str) -> str:
    source = item.get("source") or ""
    if group == "tesla" and re.search(r"5000|5,000|수천|订单|order|발주|주문", text, re.I):
        return "공급망 보도 · Tesla 공식 확인 전"
    if source in OFFICIAL_OR_PRIMARY:
        return "공식·1차 자료"
    if source in TRUSTED:
        return "신뢰 매체 보도"
    return "보도 단계 · 추가 교차검증 필요"


def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"seen": [], "seeded": False}


def clean_title(title: str, source: str) -> str:
    if source:
        suffix = f" - {source}"
        if title.endswith(suffix):
            return title[:-len(suffix)].strip()
    return title.strip()


def esc_text(value: str) -> str:
    return html.escape(value or "", quote=False)


def esc_attr(value: str) -> str:
    return html.escape(value or "", quote=True)


def select_diverse(items: list[dict], seen: set[str], force: bool, limit: int) -> list[dict]:
    candidates = items if force else [x for x in items if x["key"] not in seen]
    if not candidates:
        return []

    chosen: list[dict] = []
    used_keys: set[str] = set()
    groups = ["tesla", "battery", "robotis", "byd_paxini"]

    # First pass: make sure one high-signal item from each lane can surface.
    for group in groups:
        for x in candidates:
            if x.get("group") == group and x["key"] not in used_keys:
                chosen.append(x)
                used_keys.add(x["key"])
                break
        if len(chosen) >= limit:
            return chosen

    # Second pass: fill by score / freshness.
    for x in candidates:
        if x["key"] in used_keys:
            continue
        chosen.append(x)
        used_keys.add(x["key"])
        if len(chosen) >= limit:
            break
    return chosen


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()
    seen = set(state.get("seen", []))
    all_items: dict[str, dict] = {}
    errors: list[str] = []
    ok_queries = 0

    for q in QUERIES:
        try:
            items = query_news(q)
            ok_queries += 1
            for x in items:
                text = f"{x['title']} {x.get('description','')} {x.get('source','')}"
                group = topic_group(text)
                if group is None:
                    continue
                k = key(x)
                x["key"] = k
                x["group"] = group
                x["score"] = score(x)
                prev = all_items.get(k)
                if prev is None or x["score"] > prev["score"]:
                    all_items[k] = x
        except Exception as e:
            errors.append(f"{q}: {type(e).__name__}: {e}")

    if ok_queries == 0:
        raise SystemExit("All Google News RSS queries failed")

    cutoff = NOW - dt.timedelta(days=4)
    recent: list[dict] = []
    for x in all_items.values():
        pub = None
        if x.get("published"):
            try:
                pub = dt.datetime.fromisoformat(x["published"])
            except Exception:
                pass
        if pub and pub < cutoff:
            continue
        if x["score"] >= 11:
            recent.append(x)
    recent.sort(key=lambda x: (x["score"], x.get("published") or ""), reverse=True)

    first = not bool(state.get("seeded"))
    if first and not FORCE:
        selected: list[dict] = []
    else:
        selected = select_diverse(recent, seen, FORCE, MAX_ALERTS)

    for x in recent:
        seen.add(x["key"])
    seen_list = list(seen)[-3500:]
    pending = {
        "seeded": True,
        "updated_at": NOW.isoformat(),
        "seen": seen_list,
        "last_selected": [x["key"] for x in selected],
        "groups": sorted({x.get("group", "") for x in recent}),
    }
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: list[str] = []
    if selected:
        lines.extend([
            "🚨 <b>피지컬AI·로봇 공급망 구조 변화 감지</b>",
            f"<b>신규 고신호 {len(selected)}건</b>",
            "━━━━━━━━━━━━━━━━━━",
            "",
        ])

        for i, x in enumerate(selected, 1):
            text = f"{x['title']} {x.get('description','')}"
            group = x["group"]
            cat = category(text, group)
            when = ""
            if x.get("published"):
                try:
                    when = dt.datetime.fromisoformat(x["published"]).astimezone(KST).strftime("%m/%d %H:%M")
                except Exception:
                    pass

            source = x.get("source") or "미상"
            title = clean_title(x["title"], source)
            source_time = esc_text(source)
            if when:
                source_time += f" · {esc_text(when)} KST"

            lines.extend([
                f"<b>{i}. {esc_text(tag_for(group))} {esc_text(title)}</b>",
                f"<b>분류</b>  {esc_text(cat)}",
                f"<b>출처</b>  {source_time}",
                f"<b>확인</b>  {esc_text(verification(x, group, text))}",
                "",
                f"💡 <b>핵심</b>  {esc_text(meaning(cat))}",
                f"⚠️ <b>체크</b>  {esc_text(risk(cat))}",
                f"<a href=\"{esc_attr(x['link'])}\"><b>원문</b></a>",
                "",
                "──────────────────",
                "",
            ])

        lines.extend([
            "<b>판정 기준</b>",
            "신규 수주·고객 실명·배치 발주·양산/출하·생산 수율·생산능력·현장 배치·대당 부품 탑재가치·배터리 소재 채택·촉각/데이터 사업화·기관 지분 변화처럼 돈 버는 능력·수급·시간표를 바꾸는 내용만 알림.",
            "단순 주가 기사·ETF 움직임·테마 반복은 제외.",
        ])

    ALERT_PATH.write_text("\n".join(lines).strip(), encoding="utf-8")

    counts: dict[str, int] = {}
    for x in recent:
        counts[x["group"]] = counts.get(x["group"], 0) + 1

    status = [
        "# Physical AI Supply Chain Watch",
        f"- checked_at_kst: {NOW.astimezone(KST).isoformat()}",
        f"- queries_ok: {ok_queries}/{len(QUERIES)}",
        f"- high_signal_recent: {len(recent)}",
        f"- selected_new: {len(selected)}",
        f"- first_seed: {first}",
        f"- force_summary: {FORCE}",
        f"- group_counts: {json.dumps(counts, ensure_ascii=False)}",
        "- telegram_format: HTML",
        "- original_link_emoji: none",
    ]
    if errors:
        status.append("- errors:")
        status.extend(f"  - {e}" for e in errors)
    STATUS_PATH.write_text("\n".join(status) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
