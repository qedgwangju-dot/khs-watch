#!/usr/bin/env python3
"""Smartphone memory-cost pass-through / retail-price watch.

Purpose
- Track when DRAM/NAND inflation moves from component pricing into handset MSRP,
  storage tiers, or specifications across Samsung/Apple/Google/OPPO/vivo/Xiaomi.
- Keep official industry evidence separate from single-source product-price rumors.
- Treat the Galaxy S27 Korea KRW 100k-130k hike as a rumor baseline, not a
  confirmed Samsung price decision.
- Do not use the conflicting UDN US$1,400 / US$1,299 framing as a baseline.

Alert route
- Appends to the existing Memory Spot Contract HBM Telegram alert file.
- No new bot or workflow.
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
STATE_PATH = ROOT / "data" / "smartphone_memory_pass_through_state.json"
OUT_DIR = ROOT / "out"
OUT_DIR.mkdir(exist_ok=True)
PENDING_PATH = OUT_DIR / "smartphone_memory_pass_through_pending_state.json"
STATUS_PATH = OUT_DIR / "smartphone_memory_pass_through_status.md"
FRAGMENT_PATH = OUT_DIR / "smartphone_memory_pass_through_alert.html"
MAIN_ALERT_PATH = OUT_DIR / "memory_spot_cycle_watch_telegram.txt"
KST = ZoneInfo("Asia/Seoul")

UDN_SOURCE = "https://money.udn.com/money/story/5612/9793022"
COUNTERPOINT_PRICE = "https://counterpointresearch.com/en/insights/global-existing-smartphone-prices-climb-about-15-percent-in-2026"
COUNTERPOINT_SOC = "https://counterpointresearch.com/en/insights/global-smartphone-soc-shipments-fall-15percent-yoy-in-h12026"
TRENDFORCE_Q4 = "https://www.trendforce.com/presscenter/news/20260930-13258.html"
TRENDFORCE_SMARTPHONE = "https://www.trendforce.com/presscenter/news/20260211-12922.html"

BASELINE = {
    "s27_korea_hike_low_krw": 100_000,
    "s27_korea_hike_high_krw": 130_000,
    "s27_status": "단일 한국 팁스터(Lanzuk/yeux1122)발 루머·삼성전자 공식 미확인",
    "counterpoint_existing_phone_price_yoy_pct": 15.0,
    "counterpoint_new_launch_price_yoy_pct": 25.0,
    "counterpoint_models_hiked_share_pct": 40.0,
    "trendforce_q4_dram_qoq_low_pct": 10.0,
    "trendforce_q4_dram_qoq_high_pct": 15.0,
    "trendforce_q4_nand_qoq_low_pct": 15.0,
    "trendforce_q4_nand_qoq_high_pct": 20.0,
}

QUERIES = [
    ("ko", '"갤럭시 S27" 가격 인상 메모리 LPDDR6 NAND 10만 13만원'),
    ("ko", '"갤럭시 S27" 가격 삼성 공식 출시가'),
    ("ko", '스마트폰 가격 인상 메모리 부족 NAND LPDDR 삼성 애플 구글 OPPO vivo'),
    ("ko", '스마트폰 저장용량 축소 메모리 가격 인상 삼성 애플 구글'),
    ("en", '"Galaxy S27" price hike 100000 130000 won LPDDR6 NAND'),
    ("en", '"Galaxy S27" official price Samsung memory'),
    ("en", 'smartphone price hike memory shortage NAND LPDDR Samsung Apple Google OPPO vivo'),
    ("en", 'smartphone lower storage specification changes memory cost Counterpoint TrendForce'),
]

HIGH_SOURCES = (
    "samsung", "apple", "google", "oppo", "vivo", "xiaomi",
    "counterpoint", "trendforce", "reuters", "bloomberg",
    "financial times", "wall street journal", "wsj", "nikkei",
)
MID_SOURCES = (
    "android authority", "9to5google", "sammobile", "gsmarena",
    "digitimes", "udn", "經濟日報", "经济日报", "business today",
    "tom's guide", "tom's hardware", "it之家", "ithome",
)
LOW_SOURCES = (
    "notebookcheck", "wccftech", "technobezz", "reddit", "note.com",
)

OEM_MARKERS = {
    "Samsung": ("samsung", "삼성", "三星"),
    "Apple": ("apple", "애플", "苹果"),
    "Google": ("google", "pixel", "구글", "谷歌"),
    "OPPO": ("oppo",),
    "vivo": ("vivo",),
    "Xiaomi": ("xiaomi", "redmi", "샤오미", "小米"),
}
S27_MARKERS = ("galaxy s27", "갤럭시 s27", "三星 s27", "三星s27")
MEMORY_MARKERS = (
    "memory", "dram", "lpddr", "lpddr6", "nand", "ufs",
    "메모리", "디램", "낸드", "램", "記憶體", "内存", "闪存", "儲存",
)
PRICE_MARKERS = (
    "price", "pricing", "msrp", "price hike", "increase", "higher price",
    "가격", "출고가", "인상", "涨价", "漲價", "售價", "售价",
)
RUMOR_MARKERS = (
    "rumor", "rumour", "leak", "leaker", "tipster", "could", "may", "might",
    "expected", "reportedly", "rumored", "전망", "예상", "루머", "유출",
    "팁스터", "爆料", "传闻", "傳聞", "可能", "傳出",
)
CONFIRM_MARKERS = (
    "official", "officially", "announced", "launch price", "price starts",
    "공식", "발표", "출시가", "정식", "官方", "宣布", "起售价",
)
SPEC_CUT_MARKERS = (
    "lower storage", "reduced storage", "storage cut", "lower capacity",
    "reduced camera", "4g model", "specification change",
    "저장용량 축소", "용량 축소", "사양 축소", "카메라 축소",
)

UA = "Mozilla/5.0 (compatible; khs-smartphone-memory-pass-through/1.0)"


def _fetch(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept": "application/rss+xml,application/xml,text/xml,*/*"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def _clean(value: str | None) -> str:
    text = html.unescape(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _norm(value: str) -> str:
    text = _clean(value).lower()
    text = re.sub(r"\s+-\s+[^-]{1,80}$", "", text)
    text = re.sub(r"[^0-9a-z가-힣一-龥%.,~+\-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _source_rank(source: str) -> int:
    raw = _clean(source).lower()
    low = _norm(source)
    if any(x.lower() in raw or x.lower() in low for x in HIGH_SOURCES):
        return 3
    if any(x.lower() in raw or x.lower() in low for x in MID_SOURCES):
        return 2
    if any(x.lower() in raw or x.lower() in low for x in LOW_SOURCES):
        return 0
    return 1


def _parse_date(value: str | None) -> dt.datetime | None:
    try:
        parsed = parsedate_to_datetime(value or "")
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(KST)
    except Exception:
        return None


def _rss_url(lang: str, query: str) -> str:
    if lang == "ko":
        params = {"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"}
    else:
        params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)


def _fingerprint(item: dict) -> str:
    base = f"{_norm(item.get('title',''))}|{_norm(item.get('source',''))}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:24]


def _oems(blob: str) -> list[str]:
    low = blob.lower()
    return [name for name, markers in OEM_MARKERS.items() if any(x in low for x in markers)]


def _is_rumor(blob: str) -> bool:
    low = blob.lower()
    return any(x in low for x in RUMOR_MARKERS)


def _is_official_like(blob: str, source: str) -> bool:
    low = blob.lower()
    src = source.lower()
    source_is_oem = any(
        any(marker in src for marker in markers)
        for markers in OEM_MARKERS.values()
    )
    return source_is_oem and any(x in low for x in CONFIRM_MARKERS)


def _krw_amounts(blob: str) -> list[int]:
    text = blob.replace(",", "")
    vals: list[int] = []
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*만\s*원", text):
        val = int(round(float(m.group(1)) * 10_000))
        if 10_000 <= val <= 2_000_000:
            vals.append(val)
    for m in re.finditer(r"(\d{4,7})\s*(?:원|won|krw|韩元|韓元)", text, re.I):
        val = int(m.group(1))
        if 10_000 <= val <= 2_000_000:
            vals.append(val)
    return sorted(set(vals))


def _pct_near_price(blob: str) -> float | None:
    low = blob.lower()
    vals: list[float] = []
    for m in re.finditer(r"([+\-]?\d{1,3}(?:\.\d+)?)\s*%", blob):
        window = low[max(0, m.start() - 120): min(len(low), m.end() + 120)]
        if any(x in window for x in PRICE_MARKERS):
            val = float(m.group(1))
            if not m.group(1).startswith(("+", "-")):
                if any(x in window for x in ("increase", "rose", "higher", "인상", "상승", "涨", "漲")):
                    val = abs(val)
            vals.append(val)
    return vals[0] if vals else None


def _s27_fact_key(blob: str) -> str:
    low = blob.lower()
    if not any(x in low for x in S27_MARKERS):
        return ""
    vals = _krw_amounts(blob)
    if vals:
        return f"s27_korea_hike_{min(vals)}_{max(vals)}"
    if _is_rumor(blob):
        return "s27_price_hike_rumor_unspecified"
    return ""


def _collect() -> tuple[list[dict], list[str]]:
    now = dt.datetime.now(KST)
    cutoff = now - dt.timedelta(days=14)
    rows: dict[str, dict] = {}
    errors: list[str] = []
    for lang, query in QUERIES:
        try:
            root = ET.fromstring(_fetch(_rss_url(lang, query)))
        except Exception as exc:
            errors.append(f"{lang}:{query[:45]} -> {type(exc).__name__}")
            continue
        for node in root.findall(".//item"):
            title = _clean(node.findtext("title"))
            desc = _clean(node.findtext("description"))
            link = _clean(node.findtext("link"))
            source_node = node.find("source")
            source = _clean(source_node.text if source_node is not None else "")
            published = _parse_date(_clean(node.findtext("pubDate")))
            if not title or not link or not published:
                continue
            if published < cutoff or published > now + dt.timedelta(minutes=15):
                continue
            blob = f"{title} {desc} {source}".lower()
            if not (
                any(x in blob for x in MEMORY_MARKERS)
                and (any(x in blob for x in PRICE_MARKERS) or any(x in blob for x in SPEC_CUT_MARKERS))
            ):
                continue
            item = {
                "title": title,
                "description": desc,
                "link": link,
                "source": source or "출처 미표시",
                "published_at_kst": published.isoformat(timespec="seconds"),
            }
            rows[_fingerprint(item)] = item
    return sorted(rows.values(), key=lambda x: x["published_at_kst"]), errors


def _load_state() -> dict:
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("seen", [])
            data.setdefault("seen_fact_keys", [])
            data.setdefault("metrics", {})
            return data
    except Exception:
        pass
    return {
        "schema_version": 1,
        "initial_alert_sent": False,
        "seen": [],
        "seen_fact_keys": [],
        "metrics": dict(BASELINE),
        "last_alert": None,
    }


def _signal(item: dict, state: dict) -> dict | None:
    blob = f"{item['title']} {item.get('description','')} {item.get('source','')}"
    low = blob.lower()
    rank = _source_rank(item.get("source", ""))
    if rank < 2:
        return None

    metrics = state.get("metrics") or {}
    oems = _oems(blob)
    rumor = _is_rumor(blob)
    official = _is_official_like(blob, item.get("source", ""))
    reasons: list[str] = []
    changes: dict[str, object] = {}
    stage = 0
    fact_key = _s27_fact_key(blob)

    if any(x in low for x in S27_MARKERS):
        vals = _krw_amounts(blob)
        if vals:
            low_krw, high_krw = min(vals), max(vals)
            prev_low = int(metrics.get("s27_korea_hike_low_krw") or 0)
            prev_high = int(metrics.get("s27_korea_hike_high_krw") or 0)
            materially_new = (
                abs(low_krw - prev_low) >= 50_000
                or abs(high_krw - prev_high) >= 50_000
                or official
            )
            if materially_new:
                reasons.append(
                    f"Galaxy S27 한국 가격 인상 범위 {prev_low//10000:g}만~{prev_high//10000:g}만원"
                    f" → {low_krw//10000:g}만~{high_krw//10000:g}만원"
                )
                changes["s27_korea_hike_low_krw"] = low_krw
                changes["s27_korea_hike_high_krw"] = high_krw
                stage = max(stage, 3 if official else 1)
        elif official:
            reasons.append("Samsung 공식 Galaxy S27 가격 발표 감지")
            stage = max(stage, 3)

    price_pct = _pct_near_price(blob)
    if oems and price_pct is not None and abs(price_pct) >= 5:
        # General OEM price pass-through is only meaningful from official/high
        # sources, or when the article is not merely a leak/rumor.
        if rank >= 3 and (official or not rumor):
            reasons.append(f"{'/'.join(oems)} 스마트폰 가격 변화 {price_pct:+g}%")
            stage = max(stage, 2)

    if any(x in low for x in SPEC_CUT_MARKERS) and rank >= 3:
        reasons.append("메모리 원가 대응 저장용량·사양 조정 신호")
        stage = max(stage, 2)

    if not reasons:
        return None

    if rumor and not official:
        status = "루머·공식 미확인"
    elif official:
        status = "공식 가격 확인"
    else:
        status = "고신뢰 업황·가격전가 보도"

    return {
        "item": item,
        "rank": rank,
        "stage": stage,
        "status": status,
        "oems": oems,
        "reasons": reasons[:3],
        "changes": changes,
        "fact_key": fact_key,
    }


def _baseline_alert() -> str:
    return "\n".join([
        "📱 <b>[스마트폰 메모리 원가 전가 | 기준선]</b>",
        "━━━━━━━━━━━━━━━━",
        "<b>[확정 업황]</b>",
        "• Counterpoint: 2026년 기존 스마트폰 평균 판매가격 약 <b>+15%</b>, 신제품은 전년 동급 대비 약 <b>+25%</b>, 전체 모델의 40% 이상이 가격 인상.",
        "• TrendForce: 2026년 4분기 범용 DRAM 계약가격 <b>+10~15% QoQ</b>, NAND Flash 계약가격 <b>+15~20% QoQ</b> 전망.",
        "• 따라서 메모리 원가가 완제품 가격·저장용량·사양으로 전가되는 현상 자체는 공식 업황 자료로 확인됩니다.",
        "",
        "<b>[Galaxy S27 현재 상태]</b>",
        "• 한국 시장 가격 인상 폭 <b>10만~13만원 이상</b>은 Lanzuk/yeux1122 단일 팁스터발 루머가 여러 매체로 재전달된 단계입니다.",
        "• 전 모델 가격 인상·대용량 저장 버전의 더 큰 가격격차·일부 모델 LPDDR6/신형 UFS 채택 가능성이 거론되지만 <b>삼성전자 공식 가격은 아직 미확정</b>입니다.",
        "• UDN의 ‘S27 시작가 1,400달러 / S26 1,299달러’ 표현은 다른 보도의 가격 체계와 충돌해 <b>기준선에서 제외</b>했습니다.",
        "",
        "<b>[알림 단계]</b>",
        "• 🟡 단일 루머: 구체 인상 폭이 있지만 삼성 공식 미확인",
        "• 🟠 가격 전가 확인: 주요 OEM의 실제 가격·저장용량·사양 조정이 고신뢰 자료로 확인",
        "• 🔴 공식 가격 확정: Samsung 등 OEM 공식 출시가에서 메모리 원가 전가가 확인",
        "",
        "<b>[다음 알림 조건]</b>",
        "• Galaxy S27 한국 인상 폭이 현재 10만~13만원에서 5만원 이상 변경",
        "• 삼성전자 공식 S27 출시가 공개",
        "• Samsung·Apple·Google·OPPO·vivo·Xiaomi 중 추가 OEM이 메모리 때문에 가격을 5% 이상 공식 인상",
        "• 저장용량 축소·상위 저장용량 가격격차 확대·사양 축소가 공식 확인",
        "• DRAM/NAND 공식 전망이 현재 4Q26 범위를 다시 크게 상향·하향",
        "",
        f'<a href="{UDN_SOURCE}">經濟日報 · S27 가격 인상 보도</a>',
        f'<a href="{COUNTERPOINT_PRICE}">Counterpoint · 스마트폰 가격 전가</a>',
        f'<a href="{TRENDFORCE_Q4}">TrendForce · 4Q26 DRAM/NAND 가격</a>',
    ]) + "\n"


def _change_alert(signals: list[dict]) -> str:
    best = max(signals, key=lambda s: (s["stage"], s["rank"], s["item"]["published_at_kst"]))
    stage = int(best["stage"])
    stage_text = "🔴 공식 가격 확정" if stage >= 3 else ("🟠 가격 전가 확인" if stage >= 2 else "🟡 루머 업데이트")
    selected = sorted(
        signals,
        key=lambda s: (s["stage"], s["rank"], s["item"]["published_at_kst"]),
        reverse=True,
    )[:3]

    lines = [
        "📱 <b>[스마트폰 메모리 원가 전가 변화]</b>",
        "━━━━━━━━━━━━━━━━",
        f"• <b>{stage_text}</b>",
    ]
    for signal in selected:
        item = signal["item"]
        lines.append("• " + html.escape(" / ".join(signal["reasons"])))
        lines.append(f"  └ {html.escape(signal['status'])} · {html.escape(item['source'])} · {html.escape(item['published_at_kst'])}")

    lines += [
        "",
        "<b>[판정 규칙]</b>",
        "• 메모리 가격 상승과 스마트폰 가격 인상을 인과관계가 확인된 경우에만 연결합니다.",
        "• 단일 팁스터 루머를 Samsung 공식 가격으로 승격하지 않습니다.",
        "• 같은 Lanzuk/yeux1122 루머의 매체 재인용은 신규 사실로 반복 알림하지 않습니다.",
        "",
    ]
    for signal in selected:
        item = signal["item"]
        lines.append(f'<a href="{html.escape(item["link"], quote=True)}">원문 · {html.escape(item["source"])}</a>')
    return "\n".join(lines) + "\n"


def _append_alert(alert: str) -> None:
    existing = MAIN_ALERT_PATH.read_text(encoding="utf-8").strip() if MAIN_ALERT_PATH.exists() else ""
    if existing:
        MAIN_ALERT_PATH.write_text(existing + "\n\n<<<TELEGRAM_MESSAGE_BREAK>>>\n\n" + alert, encoding="utf-8")
    else:
        MAIN_ALERT_PATH.write_text(alert, encoding="utf-8")


def main() -> None:
    now = dt.datetime.now(KST)
    state = _load_state()
    seen = set(state.get("seen") or [])
    seen_fact_keys = set(state.get("seen_fact_keys") or [])
    metrics = dict(BASELINE)
    metrics.update(state.get("metrics") or {})
    items, errors = _collect()
    signals: list[dict] = []

    initial_pending = not bool(state.get("initial_alert_sent"))
    if initial_pending:
        # Absorb current syndicated S27 rumor coverage so only the baseline is sent.
        for item in items:
            seen.add(_fingerprint(item))
            key = _s27_fact_key(f"{item['title']} {item.get('description','')}")
            if key:
                seen_fact_keys.add(key)
    else:
        for item in items:
            fid = _fingerprint(item)
            if fid in seen:
                continue
            blob = f"{item['title']} {item.get('description','')}"
            fact_key = _s27_fact_key(blob)
            if fact_key and fact_key in seen_fact_keys:
                seen.add(fid)
                continue
            signal = _signal(item, {**state, "metrics": metrics})
            seen.add(fid)
            if signal:
                signals.append(signal)
                metrics.update(signal.get("changes") or {})
                if signal.get("fact_key"):
                    seen_fact_keys.add(signal["fact_key"])

    pending = {
        "schema_version": 1,
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "initial_alert_sent": True,
        "seen": sorted(seen)[-700:],
        "seen_fact_keys": sorted(seen_fact_keys)[-300:],
        "metrics": metrics,
        "confirmations": {
            "s27": BASELINE["s27_status"],
            "industry_price_pass_through": "Counterpoint·TrendForce 공식자료 확인",
        },
        "last_scan_items": len(items),
        "last_signal_count": len(signals),
        "last_alert": (
            {"at_kst": now.isoformat(timespec="seconds"), "kind": "baseline" if initial_pending else "change"}
            if initial_pending or signals else state.get("last_alert")
        ),
    }
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if initial_pending:
        alert = _baseline_alert()
        FRAGMENT_PATH.write_text(alert, encoding="utf-8")
        _append_alert(alert)
    elif signals:
        alert = _change_alert(signals)
        FRAGMENT_PATH.write_text(alert, encoding="utf-8")
        _append_alert(alert)
    elif FRAGMENT_PATH.exists():
        FRAGMENT_PATH.unlink()

    STATUS_PATH.write_text(
        "# Smartphone memory cost pass-through watch\n"
        f"- checked_at_kst: {now.isoformat(timespec='seconds')}\n"
        f"- items: {len(items)}\n"
        f"- new_signals: {len(signals)}\n"
        f"- initial_alert_pending: {str(initial_pending).lower()}\n"
        f"- s27_korea_hike_krw: {metrics.get('s27_korea_hike_low_krw')}~{metrics.get('s27_korea_hike_high_krw')}\n"
        f"- errors: {len(errors)}\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
