from __future__ import annotations

import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

try:
    from googlenewsdecoder import gnewsdecoder
except Exception:
    gnewsdecoder = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "nvidia_exec_signal_state.json"
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)
ALERT = OUT / "nvidia_exec_signal_alert.html"
STATUS = OUT / "nvidia_exec_signal_status.md"

UA = "Mozilla/5.0 (compatible; khs-watch/1.0; +https://github.com/qedgwangju-dot/khs-watch)"
FRESH_HOURS = 36
FORMAT_VERSION = 2

OFFICIAL_Q2_TRANSCRIPT = (
    "https://investor.nvidia.com/files/content_files/TRANSCRIPT_-NVIDIA-Corp-NVDA-US-Q2-2027-"
    "Earnings-Call-26-August-2026-5_00-PM-ET.pdf"
)
REUTERS_SCOTLAND = (
    "https://www.reuters.com/world/uk/king-charles-urge-ai-leaders-protect-humanity-scottish-meeting-2026-09-17/"
)

QUERIES = [
    '"Jensen Huang" Nvidia (double OR doubling OR twice) chip sales 2027',
    '"Jensen Huang" Nvidia (sales OR demand OR growth OR shipments) next year',
    '"NVIDIA" "customer forecasts" doubling next year',
    '"Jensen Huang" AI safety unsafe product release pause',
    '"Jensen Huang" safety engineering problem unsafe products',
    '"젠슨 황" 엔비디아 내년 칩 판매 두 배',
    '"젠슨 황" AI 안전 제품 출시 보류',
]

TRUSTED = (
    "reuters", "bloomberg", "nvidia", "financial times", "ft.com", "techcrunch",
    "associated press", "ap news", "barron's", "barrons", "marketscreener", "mt newswires",
    "cnbc", "wall street journal", "wsj", "연합뉴스", "yonhap",
)


def fetch(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def clean(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def parse_pub(value: str) -> datetime | None:
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo("Asia/Seoul"))
    except Exception:
        return None


def rss_url(query: str, lang: str) -> str:
    q = urllib.parse.quote(query)
    if lang == "ko":
        return f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def decode_google(link: str) -> str:
    if "news.google.com" not in (link or ""):
        return link
    if gnewsdecoder is None:
        return ""
    try:
        result = gnewsdecoder(link, interval=0.2)
        if isinstance(result, dict) and result.get("status"):
            decoded = str(result.get("decoded_url") or "").strip()
            if decoded.startswith("http") and "news.google.com" not in decoded:
                return decoded
    except Exception:
        pass
    return ""


def event_id(title: str, source: str) -> str:
    return hashlib.sha256(f"{title}|{source}".encode()).hexdigest()[:24]


def source_rank(source: str, title: str = "") -> int:
    low = f"{source} {title}".lower()
    if "nvidia" in low and ("investor" in low or "newsroom" in low):
        return 100
    if "reuters" in low:
        return 95
    if "bloomberg" in low:
        return 90
    if "financial times" in low or "ft.com" in low:
        return 85
    if "techcrunch" in low:
        return 80
    if "associated press" in low or "ap news" in low:
        return 78
    if "barron" in low:
        return 75
    if "marketscreener" in low or "mt newswires" in low:
        return 70
    if "cnbc" in low or "wall street journal" in low or "wsj" in low:
        return 70
    if "yonhap" in low or "연합뉴스" in low:
        return 65
    return 10


def classify(text: str) -> str:
    low = text.lower()
    nvidia = "nvidia" in low or "엔비디아" in low
    jensen = "jensen huang" in low or "젠슨 황" in low
    if not (nvidia or jensen):
        return ""

    demand_terms = (
        "double", "doubling", "twice", "70%", "sales", "revenue", "demand", "shipments",
        "chip sales", "growth", "두 배", "판매", "수요", "매출", "출하",
    )
    safety_terms = (
        "safety", "unsafe", "don't release", "do not release", "pause", "engineering problem",
        "안전", "출시 보류", "출시하지", "보류",
    )

    if any(k in low for k in demand_terms):
        return "demand"
    if jensen and any(k in low for k in safety_terms):
        return "safety"
    return ""


def fact_key(kind: str, text: str) -> str:
    low = text.lower()
    if kind == "demand":
        if any(k in low for k in ("double", "doubling", "twice", "두 배")) and "2027" in low:
            return "nvidia_2027_chip_sales_double"
        if "70%" in low and any(k in low for k in ("growth", "revenue", "매출", "성장")):
            return "nvidia_fy28_revenue_growth_70pct"
        nums = "_".join(re.findall(r"\d+(?:\.\d+)?%", text)[:2])
        return "nvidia_demand_" + (nums.replace("%", "pct") or hashlib.sha1(text.encode()).hexdigest()[:10])
    if kind == "safety":
        if any(k in low for k in ("unsafe", "don't release", "do not release", "pause", "출시 보류", "출시하지")):
            return "nvidia_safety_do_not_release_unsafe"
        return "nvidia_safety_" + hashlib.sha1(text.encode()).hexdigest()[:10]
    return hashlib.sha1(text.encode()).hexdigest()[:12]


def read_events() -> list[dict]:
    rows: dict[str, dict] = {}
    for query in QUERIES:
        for lang in ("en", "ko"):
            try:
                root = ET.fromstring(fetch(rss_url(query, lang)))
            except Exception:
                continue
            for item in root.findall("./channel/item"):
                title = clean(item.findtext("title") or "")
                desc = clean(item.findtext("description") or "")
                link = clean(item.findtext("link") or "")
                source_node = item.find("source")
                source = clean(source_node.text if source_node is not None and source_node.text else "")
                pub = parse_pub(clean(item.findtext("pubDate") or ""))
                text = f"{title} {desc}"
                kind = classify(text)
                if not title or not link or not kind:
                    continue
                if not any(k in source.lower() for k in TRUSTED):
                    # MarketScreener often republishes MT/Bloomberg headlines; allow when title names Bloomberg.
                    if not ("bloomberg" in title.lower() and "marketscreener" in source.lower()):
                        continue
                direct = decode_google(link)
                if not direct:
                    continue
                key = event_id(title, source)
                rows[key] = {
                    "id": key,
                    "kind": kind,
                    "fact_key": fact_key(kind, text),
                    "title": title,
                    "description": desc,
                    "source": source or "출처 미표시",
                    "published_at_kst": pub.isoformat(timespec="seconds") if pub else "",
                    "direct_link": direct,
                    "rank": source_rank(source, title),
                }
    return sorted(rows.values(), key=lambda x: x.get("published_at_kst") or "")


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"seen_ids": [], "seen_fact_keys": []}


def write_state(state: dict) -> None:
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def link(url: str, label: str = "원문") -> str:
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'


def choose_new(events: list[dict], seen_ids: set[str], seen_fact_keys: set[str], now: datetime) -> list[dict]:
    cutoff = now - timedelta(hours=FRESH_HOURS)
    candidates: list[dict] = []
    for e in events:
        try:
            dt = datetime.fromisoformat(e.get("published_at_kst") or "")
        except Exception:
            continue
        if not (cutoff <= dt <= now + timedelta(minutes=10)):
            continue
        if e["id"] in seen_ids or e["fact_key"] in seen_fact_keys:
            continue
        candidates.append(e)

    # One best source per fact.
    chosen: dict[str, dict] = {}
    for e in candidates:
        old = chosen.get(e["fact_key"])
        if old is None or e["rank"] > old["rank"] or (
            e["rank"] == old["rank"] and e.get("published_at_kst", "") > old.get("published_at_kst", "")
        ):
            chosen[e["fact_key"]] = e
    return sorted(chosen.values(), key=lambda x: x.get("published_at_kst") or "")


def build_alert(events: list[dict], now: datetime) -> str:
    demand = next((e for e in reversed(events) if e["kind"] == "demand"), None)
    safety = next((e for e in reversed(events) if e["kind"] == "safety"), None)

    lines = [
        "🚨 <b>NVIDIA 경영진·AI 수요·안전 전략 변화</b>",
        "━━━━━━━━━━━━━━━━",
        "<b>[무엇이 달라졌나]</b>",
    ]

    if demand:
        lines += [
            "• 9월 17일 스코틀랜드에서 Jensen Huang은 찰스 3세 AI 정상회의 전 취재진에게 <b>2027년에 올해보다 약 2배 많은 칩을 판매할 것으로 예상</b>한다고 말했습니다.",
            "• 여기서 ‘칩’은 AI GPU만이 아니라 <b>CPU·스위치·광 네트워킹·노트북·Jetson 등 NVIDIA 전체 반도체 제품군</b>을 포함합니다.",
            "• 따라서 이 발언을 <b>GPU 출하 2배 또는 HBM 수요 2배</b>로 바로 환산하면 안 됩니다.",
        ]
    if safety:
        lines += [
            "• 같은 스코틀랜드 회의 현장에서 Huang은 AI 안전과 관련해 <b>제품이 준비되지 않았으면 출시를 보류하고 더 개발해야 한다</b>는 원칙을 강조했습니다.",
        ]

    lines += [
        "",
        "<b>[공식 기준선과 비교]</b>",
        "• NVIDIA의 2026년 8월 26일 FY27 2분기 공식 실적발표에서는 <b>고객 수요 전망상 다음 해 성장 잠재력이 약 2배</b>라고 설명했습니다.",
        "• 그러나 회사가 공식적으로 제시한 FY28 매출 성장 전망은 <b>약 +70%</b>였습니다.",
        "• 차이는 수요가 부족해서가 아니라 <b>공급 제약</b> 때문이라고 회사가 명시했습니다.",
        "→ 따라서 ‘판매 2배’는 수요 강도의 상단 신호이고, 실제 매출은 HBM·DRAM·파운드리·첨단패키징·전력 등 공급망이 얼마나 따라오느냐에 달려 있습니다.",
        "",
        "<b>[출처·맥락 구분]</b>",
        "• <b>칩 판매 2배</b>: 9월 17일 스코틀랜드 찰스 3세 AI 정상회의 전 취재진 발언으로 CNBC·Bloomberg가 보도했습니다.",
        "• <b>안전 발언</b>: Reuters도 같은 스코틀랜드 회의 현장에서 Huang이 ‘준비되지 않았으면 보류하라’고 말했다고 확인했습니다.",
        "• 두 발언 모두 스코틀랜드 행사 맥락이지만, <b>칩 판매 2배는 수량 전망</b>, <b>안전 발언은 출시 원칙</b>으로 분리해서 해석합니다.",
        "",
        "<b>[투자적으로 왜 중요한가]</b>",
        "• <b>전체 칩 수량 2배 전망 + FY28 매출 +70% 공식 전망</b>의 차이는 제품혼합과 공급 제약을 함께 봐야 한다는 뜻입니다.",
        "• HBM·서버 DRAM·첨단패키징·파운드리 생산능력이 늘면 NVIDIA가 현재 못 받는 주문을 추가 매출로 전환할 여지가 큽니다.",
        "• 다만 CPU·스위치·광통신·노트북용 칩까지 포함된 수량 전망이므로 <b>HBM 업체 매출을 2배로 직접 계산하지 않습니다.</b>",
        "• 반대로 안전 발언만으로 제품 출시 지연을 의미하지는 않습니다. 실제 <b>Blackwell·Rubin 일정 변경이나 고객 승인 지연</b>이 확인될 때만 실적 시간표 악화로 판정합니다.",
        "",
        "<b>[다음 알림 조건]</b>",
        "• NVIDIA가 FY28 매출 성장률을 <b>+70%에서 상향·하향</b>",
        "• GPU·AI 가속기와 CPU·네트워킹 등 <b>제품별 출하량·판매량 목표</b>를 새로 제시",
        "• 전체 칩 2배 전망 중 <b>AI GPU가 차지하는 비중</b>이 공개",
        "• 고객 수요가 2배인데 실제 공급 가능 비율이 <b>70%에서 변화</b>",
        "• HBM·DRAM·CoWoS·파운드리·전력 가운데 병목 순위가 구체화",
        "• Blackwell·Rubin 또는 신규 AI 제품이 <b>안전·신뢰성 이유로 실제 연기·출시 보류</b>",
        "• AI 규제·안전 기준이 NVIDIA 제품 출시·데이터센터 도입 일정에 직접 영향",
        "",
        f"<b>조회</b>: {now.strftime('%Y-%m-%d %H:%M:%S KST')}",
        f"<b>공식 기준</b>: {link(OFFICIAL_Q2_TRANSCRIPT, 'NVIDIA FY27 2Q 실적발표 원문')}",
        f"<b>스코틀랜드 회의</b>: {link(REUTERS_SCOTLAND, 'Reuters 원문')}",
    ]

    if demand:
        lines.append(
            f"<b>수요·판매 전망 출처</b>: {html.escape(demand['source'])} · {link(demand['direct_link'])}"
        )
    if safety:
        lines.append(
            f"<b>안전 발언 출처</b>: {html.escape(safety['source'])} · {link(safety['direct_link'])}"
        )

    return "\n".join(lines) + "\n"


def main() -> None:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    state = load_state()
    seen_ids = set(state.get("seen_ids") or [])
    seen_fact_keys = set(state.get("seen_fact_keys") or [])

    events = read_events()
    new_events = choose_new(events, seen_ids, seen_fact_keys, now)

    # Format/context correction: when the alert interpretation changes materially,
    # resend the best still-fresh demand/safety facts once even if the fact itself was already seen.
    if not new_events and int(state.get("format_version") or 0) < FORMAT_VERSION:
        cutoff = now - timedelta(hours=FRESH_HOURS)
        best_by_kind: dict[str, dict] = {}
        for e in events:
            try:
                dt = datetime.fromisoformat(e.get("published_at_kst") or "")
            except Exception:
                continue
            if not (cutoff <= dt <= now + timedelta(minutes=10)):
                continue
            old = best_by_kind.get(e["kind"])
            if old is None or e["rank"] > old["rank"] or (
                e["rank"] == old["rank"] and e.get("published_at_kst", "") > old.get("published_at_kst", "")
            ):
                best_by_kind[e["kind"]] = e
        new_events = sorted(best_by_kind.values(), key=lambda x: x.get("published_at_kst") or "")

    # For the first run, intentionally allow fresh current signals to be sent once.
    if new_events:
        ALERT.write_text(build_alert(new_events, now), encoding="utf-8")
    elif ALERT.exists():
        ALERT.unlink()

    seen_ids.update(e["id"] for e in events)
    seen_fact_keys.update(e["fact_key"] for e in new_events)
    state = {
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "seen_ids": sorted(seen_ids)[-1000:],
        "seen_fact_keys": sorted(seen_fact_keys)[-300:],
        "last_event_count": len(events),
        "last_new_event_count": len(new_events),
        "alert_generated": bool(new_events),
        "format_version": FORMAT_VERSION,
    }
    write_state(state)

    STATUS.write_text(
        "# NVIDIA executive signal watch\n"
        f"- checked_at_kst: {now.isoformat(timespec='seconds')}\n"
        f"- events: {len(events)}\n"
        f"- new_events: {len(new_events)}\n"
        f"- alert_generated: {str(bool(new_events)).lower()}\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
