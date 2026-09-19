#!/usr/bin/env python3
"""Apple iPhone Duo demand/competition leading-signal watch.

This module complements the existing production/supply watcher. It monitors
consumer demand and competitive substitution without treating one-week sales
noise as an Apple production cut. It writes into the existing Telegram alert
file so the operating route remains unchanged.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "apple_duo_demand_competition_state.json"
OUT_DIR = ROOT / "out"
OUT_DIR.mkdir(exist_ok=True)
PENDING_PATH = OUT_DIR / "apple_duo_demand_competition_pending_state.json"
STATUS_PATH = OUT_DIR / "apple_duo_demand_competition_status.md"
FRAGMENT_PATH = OUT_DIR / "apple_duo_demand_competition_alert.html"
MAIN_ALERT_PATH = OUT_DIR / "apple_duo_supply_watch_telegram.txt"
KST = ZoneInfo("Asia/Seoul")

# The 2026-09-17 Fnnews/Yonhap Fold8 +10% article is intentionally a baseline,
# not a replay alert. New information after this timestamp can trigger.
BASELINE_AT_KST = dt.datetime(2026, 9, 17, 9, 45, tzinfo=KST)
APPLE_PREORDER_KST = dt.datetime(2026, 10, 16, 21, 0, tzinfo=KST)
APPLE_LAUNCH_DATE = dt.date(2026, 10, 23)
BASELINE_SOURCE = "https://www.fnnews.com/news/202609170939497768"
APPLE_OFFICIAL = "https://www.apple.com/kr/shop/buy-iphone/iphone-duo"

QUERIES = [
    ("ko", '"아이폰 듀오" 사전예약 예약판매 판매량 배송 대기 품절'),
    ("ko", '"아이폰 듀오" 개통량 취소 반품 판매 부진 흥행'),
    ("ko", '"아이폰 듀오" "갤럭시 Z 폴드8" 판매 증가 감소'),
    ("ko", '"애플 폴더블" 예약 판매 수요 배송기간 통신사 개통'),
    ("en", '"iPhone Duo" preorders sales sell-through sold out shipping wait'),
    ("en", '"iPhone Duo" carrier activations cancellations returns demand'),
    ("en", '"iPhone Duo" "Galaxy Z Fold 8" sales demand after launch'),
    ("en", '"Apple foldable" preorder demand shipping delay competitor sales'),
]

APPLE_MARKERS = (
    "iphone duo", "apple foldable", "foldable iphone",
    "아이폰 듀오", "애플 폴더블", "폴더블 아이폰",
)
DIRECT_DEMAND_MARKERS = (
    "preorder", "pre-order", "preorders", "sales", "sell-through", "sold out",
    "backorder", "shipping", "delivery", "wait time", "activation", "activations",
    "cancellation", "cancellations", "return", "returns", "demand",
    "사전예약", "사전 주문", "예약판매", "판매량", "판매", "품절", "배송",
    "대기", "개통", "개통량", "취소", "반품", "수요", "흥행", "부진",
)
COMPETITOR_MARKERS = (
    "galaxy z fold 8", "galaxy z fold8", "z fold 8", "z fold8", "fold8",
    "pixel fold", "pixel 10 pro fold", "huawei", "mate x", "pura x",
    "갤럭시 z 폴드8", "갤럭시 폴드8", "폴드8", "화웨이",
)
LINKAGE_MARKERS = (
    "after iphone duo", "following iphone duo", "after apple", "since apple",
    "아이폰 듀오 공개 후", "아이폰 듀오 공개 이후", "듀오 공개 후", "듀오 공개 이후",
    "아이폰 듀오 대신", "애플 공개 후", "애플 공개 이후", "예약 시작 후", "출시 후",
)
UP_WORDS = (
    "increase", "increased", "rose", "rise", "up ", "grew", "growth", "surge", "boost",
    "증가", "늘어", "늘었", "상승", "급증", "확대", "흥행", "강세",
)
DOWN_WORDS = (
    "decrease", "decreased", "fell", "fall", "down ", "decline", "drop", "cut", "weak",
    "감소", "줄어", "줄었", "하락", "급감", "축소", "부진", "약세",
)

HIGH_SOURCES = (
    "apple", "samsung", "reuters", "연합뉴스", "yonhap", "counterpoint", "idc",
    "omdia", "canalys", "bloomberg", "financial times", "wall street journal", "wsj",
)
MID_SOURCES = (
    "파이낸셜뉴스", "fnnews", "전자신문", "etnews", "zdnet", "the elec", "digitimes",
    "매일경제", "한국경제", "서울경제", "머니투데이",
)
LOW_SOURCES = (
    "wccftech", "technobezz", "note.com", "reddit", "notebookcheck",
)

GEO_MARKERS = {
    "한국": ("korea", "south korea", "한국", "국내"),
    "미국": ("united states", "u.s.", " u.s ", "america", "미국"),
    "중국": ("china", "중국"),
    "일본": ("japan", "일본"),
    "유럽": ("europe", "european", "유럽"),
    "영국": ("uk", "united kingdom", "영국"),
    "인도": ("india", "인도"),
}


def _rss_url(lang: str, query: str) -> str:
    if lang == "ko":
        params = {"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"}
    else:
        params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; khs-apple-duo-demand-watch/1.0)",
            "Accept": "application/rss+xml,application/xml,text/xml,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        return response.read()


def _clean(value: str | None) -> str:
    text = html.unescape(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_date(value: str | None) -> dt.datetime | None:
    try:
        parsed = parsedate_to_datetime(value or "")
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(KST)
    except Exception:
        return None


def _normalize(text: str) -> str:
    text = _clean(text).lower()
    text = re.sub(r"\s+-\s+[^-]{1,80}$", "", text)
    text = re.sub(r"[^0-9a-z가-힣%.$~+\-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _fingerprint(item: dict) -> str:
    base = f"{_normalize(item.get('title',''))}|{_normalize(item.get('source',''))}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:24]


def _source_rank(source: str) -> int:
    low = _normalize(source)
    if any(x in low for x in HIGH_SOURCES):
        return 3
    if any(x in low for x in MID_SOURCES):
        return 2
    if any(x in low for x in LOW_SOURCES):
        return 0
    return 1


def _geo(blob: str) -> str:
    low = blob.lower()
    for name, markers in GEO_MARKERS.items():
        if any(marker in low for marker in markers):
            return name
    return "지역 미확인"


def _direction(window: str) -> int:
    low = window.lower()
    up = any(x in low for x in UP_WORDS)
    down = any(x in low for x in DOWN_WORDS)
    if up and not down:
        return 1
    if down and not up:
        return -1
    return 0


DEMAND_METRIC_WORDS = (
    "sales", "sell-through", "orders", "preorders", "pre-orders", "activations",
    "판매", "판매량", "예약", "주문", "개통", "개통량",
)


def _nearest_marker_distance(low: str, pos: int, markers: tuple[str, ...]) -> int | None:
    distances: list[int] = []
    for marker in markers:
        start = 0
        while True:
            idx = low.find(marker, start)
            if idx < 0:
                break
            distances.append(abs(pos - (idx + len(marker) // 2)))
            start = idx + 1
    return min(distances) if distances else None


def _entity_is_closest(
    low: str,
    pos: int,
    target_markers: tuple[str, ...],
    other_markers: tuple[str, ...],
    max_distance: int = 180,
) -> bool:
    target = _nearest_marker_distance(low, pos, target_markers)
    other = _nearest_marker_distance(low, pos, other_markers)
    if target is None or target > max_distance:
        return False
    return other is None or target < other


def _nearest_direction(low: str, pos: int, max_distance: int = 90) -> int:
    candidates: list[tuple[int, int]] = []
    for word in UP_WORDS:
        start = 0
        while True:
            idx = low.find(word, start)
            if idx < 0:
                break
            dist = abs(pos - (idx + len(word) // 2))
            if dist <= max_distance:
                candidates.append((dist, 1))
            start = idx + 1
    for word in DOWN_WORDS:
        start = 0
        while True:
            idx = low.find(word, start)
            if idx < 0:
                break
            dist = abs(pos - (idx + len(word) // 2))
            if dist <= max_distance:
                candidates.append((dist, -1))
            start = idx + 1
    if not candidates:
        return 0
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def _sales_pct_for_entity(
    blob: str,
    target_markers: tuple[str, ...],
    other_markers: tuple[str, ...],
) -> float | None:
    # Attribute each percentage to the closest named product. This prevents a
    # Galaxy Fold8 +10% figure from also being labeled as iPhone Duo +10%.
    low = blob.lower()
    for m in re.finditer(r"([+\-]?\d{1,3}(?:\.\d+)?)\s*%", blob):
        window = blob[max(0, m.start() - 120): min(len(blob), m.end() + 120)]
        if not any(word in window.lower() for word in DEMAND_METRIC_WORDS):
            continue
        if not _entity_is_closest(low, m.start(), target_markers, other_markers):
            continue
        value = abs(float(m.group(1)))
        direction = _nearest_direction(low, m.start())
        if m.group(1).startswith("-"):
            direction = -1
        elif m.group(1).startswith("+"):
            direction = 1
        if direction:
            return round(direction * value, 2)
    return None


def _wait_days(blob: str) -> int | None:
    low = blob.lower()
    if not any(x in low for x in ("shipping", "delivery", "wait", "backorder", "배송", "대기", "출고")):
        return None
    candidates: list[int] = []
    for m in re.finditer(r"(\d{1,2})\s*(days?|일|weeks?|주)", low):
        value = int(m.group(1))
        unit = m.group(2)
        days = value * 7 if unit in ("week", "weeks", "주") else value
        if 1 <= days <= 90:
            candidates.append(days)
    return max(candidates) if candidates else None


def _unit_millions_for_entity(
    blob: str,
    target_markers: tuple[str, ...],
    other_markers: tuple[str, ...],
) -> float | None:
    low = blob.lower().replace(",", "")
    vals: list[float] = []
    patterns = [
        (r"(\d+(?:\.\d+)?)\s*(?:million|mn)\s*(?:units|devices|phones|orders|preorders)?", 1.0),
        (r"(\d+(?:\.\d+)?)\s*백만\s*(?:대|건)?", 1.0),
        (r"(\d+(?:\.\d+)?)\s*만\s*(?:대|건)", 0.01),
    ]
    for pattern, mult in patterns:
        for m in re.finditer(pattern, low):
            if not _entity_is_closest(low, m.start(), target_markers, other_markers):
                continue
            value = float(m.group(1)) * mult
            if 0.01 <= value <= 100:
                vals.append(value)
    return max(vals) if vals else None


def _load_state() -> dict:
    if STATE_PATH.exists():
        try:
            data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("seen", [])
                data.setdefault("metrics", {})
                return data
        except Exception:
            pass
    return {
        "schema_version": 1,
        "baseline_at_kst": BASELINE_AT_KST.isoformat(timespec="seconds"),
        "seen": [],
        "metrics": {
            "fold8_korea_wow_pct": 10.0,
            "duo_256_price_krw": 3290000,
            "fold8_256_price_krw": 2278100,
            "price_gap_krw": 1011900,
        },
        "last_alert": None,
    }


def collect() -> tuple[list[dict], list[str]]:
    now = dt.datetime.now(KST)
    cutoff = now - dt.timedelta(days=10)
    rows: dict[str, dict] = {}
    errors: list[str] = []
    for lang, query in QUERIES:
        try:
            root = ET.fromstring(_fetch(_rss_url(lang, query)))
        except Exception as exc:
            errors.append(f"{lang}:{query[:40]} -> {type(exc).__name__}")
            continue
        for node in root.findall(".//item"):
            title = _clean(node.findtext("title"))
            description = _clean(node.findtext("description"))
            link = _clean(node.findtext("link"))
            source_node = node.find("source")
            source = _clean(source_node.text if source_node is not None else "")
            published = _parse_date(_clean(node.findtext("pubDate")))
            if not title or not published or published < cutoff or published > now + dt.timedelta(minutes=15):
                continue
            blob = f"{title} {description} {source}".lower()
            if not any(x in blob for x in APPLE_MARKERS):
                continue
            item = {
                "title": title,
                "description": description,
                "link": link,
                "source": source or "출처 미표시",
                "published_at_kst": published.isoformat(timespec="seconds"),
            }
            rows[_fingerprint(item)] = item
    return sorted(rows.values(), key=lambda x: x["published_at_kst"]), errors


def _signal(item: dict, state: dict) -> dict | None:
    blob = f"{item['title']} {item.get('description','')} {item.get('source','')}"
    low = blob.lower()
    rank = _source_rank(item.get("source", ""))
    if rank == 0:
        return None
    direct = any(x in low for x in DIRECT_DEMAND_MARKERS)
    competitor = any(x in low for x in COMPETITOR_MARKERS)
    linkage = any(x in low for x in LINKAGE_MARKERS)
    competitor_pct = _sales_pct_for_entity(blob, COMPETITOR_MARKERS, APPLE_MARKERS)
    direct_pct = _sales_pct_for_entity(blob, APPLE_MARKERS, COMPETITOR_MARKERS)

    try:
        published_at = dt.datetime.fromisoformat(item.get("published_at_kst") or "")
    except Exception:
        published_at = None
    direct_commercial_open = bool(published_at and published_at >= APPLE_PREORDER_KST)

    # Before official preorder opens, sales/preorders/activations cannot be a
    # direct iPhone Duo commercial-demand datapoint. Competitor reaction can
    # still be monitored during this period.
    wait_days = _wait_days(blob) if direct_commercial_open else None
    units_m = (
        _unit_millions_for_entity(blob, APPLE_MARKERS, COMPETITOR_MARKERS)
        if direct_commercial_open
        else None
    )
    sold_out = direct_commercial_open and any(x in low for x in ("sold out", "sellout", "품절"))
    if not direct_commercial_open:
        direct_pct = None
    geo = _geo(blob)
    reasons: list[str] = []
    stage = 0
    direction = 0
    metric_key = ""
    metric_value: float | int | None = None

    if competitor and linkage and competitor_pct is not None and abs(competitor_pct) >= 10:
        pct = competitor_pct
        direction = 1 if pct > 0 else -1
        previous = None
        if "fold8" in low and geo in ("한국", "지역 미확인"):
            previous = float((state.get("metrics") or {}).get("fold8_korea_wow_pct") or 0)
            # If geography is missing and the article merely repeats the exact
            # +10% baseline, treat it as a syndicated baseline repeat rather
            # than a new market datapoint.
            if geo == "한국":
                metric_key = "fold8_korea_wow_pct"
                metric_value = pct
        # Suppress syndicated repeats of the +10% baseline unless the measured
        # change moves by at least 5 percentage points or reverses direction.
        if previous is not None and previous and abs(pct - previous) < 5 and (pct > 0) == (previous > 0):
            return None
        reasons.append(f"{geo} 경쟁 폴더블 판매 변화 {pct:+g}%")
        stage = max(stage, 1)

    if direct and direct_pct is not None and abs(direct_pct) >= 10:
        pct = direct_pct
        direction = 1 if pct > 0 else -1
        reasons.append(f"iPhone Duo 직접 수요 지표 {pct:+g}%")
        stage = max(stage, 2 if rank >= 3 else 1)

    if direct and units_m is not None:
        reasons.append(f"iPhone Duo 주문·판매 물량 {units_m:g}백만대 수준")
        stage = max(stage, 2 if rank >= 3 else 1)

    if direct and wait_days is not None and wait_days >= 7:
        direction = 1
        reasons.append(f"배송·대기기간 약 {wait_days}일")
        stage = max(stage, 2 if rank >= 2 else 1)

    if direct and sold_out:
        direction = 1
        reasons.append("품절·백오더 신호")
        stage = max(stage, 2 if rank >= 2 else 1)

    if direct_commercial_open and direct and any(x in low for x in ("cancellation", "cancellations", "returns", "return rate", "취소", "반품")):
        if direct_pct is not None or units_m is not None or rank >= 3:
            direction = -1
            reasons.append("취소·반품 수요 약화 신호")
            stage = max(stage, 2 if rank >= 3 else 1)

    if not reasons:
        return None

    return {
        "item": item,
        "rank": rank,
        "geo": geo,
        "direction": direction,
        "stage": stage,
        "reasons": reasons[:3],
        "metric_key": metric_key,
        "metric_value": metric_value,
    }


def _build_alert(signals: list[dict]) -> str:
    best = max(signals, key=lambda s: (s["stage"], s["rank"], s["item"]["published_at_kst"]))
    direction = best.get("direction") or 0
    same_direction_geos = {
        s["geo"] for s in signals
        if s.get("direction") == direction and s.get("geo") != "지역 미확인"
    }
    stage = int(best["stage"])
    if direction and len(same_direction_geos) >= 2:
        stage = max(stage, 2)
    stage_text = "🟠 수요 변화 확인" if stage >= 2 else "🟡 수요 선행 경고"

    selected = sorted(
        signals,
        key=lambda s: (s["stage"], s["rank"], s["item"]["published_at_kst"]),
        reverse=True,
    )[:3]
    lines = [
        "📱 <b>[Apple Duo 수요·경쟁 반응]</b>",
        "━━━━━━━━━━━━━━━━",
        "<b>[무엇이 달라졌나]</b>",
    ]
    for signal in selected:
        item = signal["item"]
        reason = " / ".join(signal["reasons"])
        lines.append(f"• {html.escape(reason)}")
        lines.append(f"  └ {html.escape(item['source'])} · {html.escape(item['published_at_kst'])}")

    lines += [
        "",
        "<b>[현재 판정]</b>",
        f"• {stage_text}",
    ]
    if len(same_direction_geos) >= 2:
        lines.append("• 서로 다른 2개 이상 지역에서 같은 방향의 수요 신호가 확인됐습니다.")
    else:
        lines.append("• 아직 한 지역·한 지표 중심이면 Apple 전체 수요나 생산계획 변화로 단정하지 않습니다.")

    lines += [
        "",
        "<b>[공급망 연결]</b>",
        "• 이 모듈은 소비자 수요 선행지표입니다. 실제 Apple 생산목표·Samsung Display 패널·LPDDR/NAND·Foxconn 발주 변경은 기존 생산·공급망 모듈에서 별도로 확인합니다.",
        "• 수요 신호와 부품 발주가 같은 방향으로 확인될 때만 공급망 전환으로 봅니다.",
        "",
        "<b>[다음 핵심 일정]</b>",
        "• 한국 사전 주문: 2026-10-16 21:00 KST",
        "• 출시: 2026-10-23",
        "• 이후 예약 속도·배송 대기기간·통신사 개통량·경쟁 Fold8 판매 변화와 Apple 부품 발주를 함께 추적",
        "",
        "<b>[기준선]</b>",
        "• 2026-09-17 국내 Galaxy Z Fold8 판매: iPhone Duo 공개 후 1주일간 직전 주 대비 약 +10%",
        "• 256GB 출고가: iPhone Duo 329만원 vs Galaxy Z Fold8 227만8,100원 → 차이 101만1,900원",
        "",
    ]
    for signal in selected:
        item = signal["item"]
        lines.append(f"<a href=\"{html.escape(item['link'], quote=True)}\">원문 · {html.escape(item['source'])}</a>")
    lines.append(f"<a href=\"{APPLE_OFFICIAL}\">Apple 공식 판매 일정</a>")
    return "\n".join(lines).strip() + "\n"


def main() -> None:
    now = dt.datetime.now(KST)
    state = _load_state()
    seen = set(state.get("seen") or [])
    metrics = dict(state.get("metrics") or {})
    items, errors = collect()
    new_signals: list[dict] = []

    for item in items:
        fid = _fingerprint(item)
        published = dt.datetime.fromisoformat(item["published_at_kst"])
        # Everything through the baseline article is absorbed without alerting.
        if published <= BASELINE_AT_KST:
            seen.add(fid)
            continue
        if fid in seen:
            continue
        signal = _signal(item, {**state, "metrics": metrics})
        seen.add(fid)
        if signal:
            new_signals.append(signal)
            key = signal.get("metric_key")
            if key and signal.get("metric_value") is not None:
                metrics[key] = signal["metric_value"]

    pending = {
        "schema_version": 1,
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "baseline_at_kst": BASELINE_AT_KST.isoformat(timespec="seconds"),
        "baseline_source": BASELINE_SOURCE,
        "preorder_at_kst": APPLE_PREORDER_KST.isoformat(timespec="seconds"),
        "launch_date": APPLE_LAUNCH_DATE.isoformat(),
        "seen": sorted(seen)[-800:],
        "metrics": metrics,
        "last_scan_items": len(items),
        "last_signal_count": len(new_signals),
        "last_alert": (
            {
                "at_kst": now.isoformat(timespec="seconds"),
                "title": new_signals[0]["item"]["title"],
                "source": new_signals[0]["item"]["source"],
            }
            if new_signals else state.get("last_alert")
        ),
    }
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if new_signals:
        alert = _build_alert(new_signals)
        FRAGMENT_PATH.write_text(alert, encoding="utf-8")
        if MAIN_ALERT_PATH.exists() and MAIN_ALERT_PATH.read_text(encoding="utf-8").strip():
            existing = MAIN_ALERT_PATH.read_text(encoding="utf-8").rstrip()
            MAIN_ALERT_PATH.write_text(existing + "\n\n━━━━━━━━━━━━━━━━\n\n" + alert, encoding="utf-8")
        else:
            MAIN_ALERT_PATH.write_text(alert, encoding="utf-8")
    elif FRAGMENT_PATH.exists():
        FRAGMENT_PATH.unlink()

    STATUS_PATH.write_text(
        "# Apple Duo demand/competition watch\n"
        f"- checked_at_kst: {now.isoformat(timespec='seconds')}\n"
        f"- baseline_at_kst: {BASELINE_AT_KST.isoformat(timespec='seconds')}\n"
        f"- items: {len(items)}\n"
        f"- new_signals: {len(new_signals)}\n"
        f"- errors: {len(errors)}\n"
        "- baseline: Fold8 Korea +10% WoW after Duo reveal; Duo/Fold8 256GB price gap KRW 1,011,900\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
