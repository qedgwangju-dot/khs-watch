#!/usr/bin/env python3
"""Smartphone memory-cost pass-through watch.

Purpose
- Track when mobile DRAM/NAND cost inflation is passed through into handset MSRP,
  storage-tier pricing, memory/storage configuration cuts, or shipment-demand revisions.
- Run inside the existing Memory Spot Contract HBM Telegram Watch.
- Keep rumor/tipster claims separate from confirmed OEM pricing actions.
- Keep DRAM and NAND 2027 outlooks separate: DRAM remains structurally tight,
  while NAND may ease in 2H27.

Baseline as of 2026-10-05
- Galaxy S27 Korea price-hike rumor: KRW 100,000 to >130,000 across models/capacities.
- S26/A-series price increases are already a real downstream pass-through precedent.
- Samsung official 2Q26: MX revenue grew YoY, but profit fell on elevated component costs.
- TrendForce: 2027 mobile DRAM remains tight; NAND may ease in 2H27.
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
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "smartphone_memory_price_pass_through_state.json"
OUT_DIR = ROOT / "out"
OUT_DIR.mkdir(exist_ok=True)
PENDING_PATH = OUT_DIR / "smartphone_memory_price_pass_through_pending_state.json"
STATUS_PATH = OUT_DIR / "smartphone_memory_price_pass_through_status.md"
FRAGMENT_PATH = OUT_DIR / "smartphone_memory_price_pass_through_alert.html"
MAIN_ALERT_PATH = OUT_DIR / "memory_spot_cycle_watch_telegram.txt"
KST = ZoneInfo("Asia/Seoul")

SAMSUNG_Q2_OFFICIAL = "https://news.samsung.com/global/samsung-electronics-announces-second-quarter-2026-results"
S26_PRICE_REUTERS = "https://www.reuters.com/world/asia-pacific/samsung-electronics-raises-galaxy-s26-smartphone-prices-yonhap-reports-2026-10-01/"
TRENDFORCE_2027 = "https://www.trendforce.com/presscenter/news/20260730-13158.html"

BASELINE = {
    "s27_korea_hike_low_krw": 100000,
    "s27_korea_hike_high_krw": 130000,
    "s27_status": "팁스터 기반 전망·삼성전자 공식 미확정",
    "s26_price_pass_through_confirmed": True,
    "s26_confirmation": "Reuters/연합뉴스가 메모리 비용 상승에 따른 가격 인상 보도",
    "samsung_mx_component_cost_pressure_official": True,
    "dram_2027_tight": True,
    "nand_2h27_easing": True,
    "s27_lpddr6_ufs51_some_models_status": "루머",
}

QUERIES = [
    ("ko", '"갤럭시 S27" 가격 인상 메모리 LPDDR6 NAND 13만원'),
    ("ko", '"갤럭시 S27" 한국 10만원 13만원 가격 인상'),
    ("ko", '"갤럭시 S27" LPDDR6 UFS 5.1 가격'),
    ("ko", '삼성 스마트폰 가격 인상 메모리 가격 S26 A시리즈'),
    ("ko", '스마트폰 가격 인상 메모리 DRAM NAND 애플 OPPO vivo 구글'),
    ("ko", '스마트폰 메모리 원가 사양 축소 저장용량 가격 인상'),
    ("en", '"Galaxy S27" price increase memory LPDDR6 UFS 5.1'),
    ("en", '"Galaxy S27" 130000 won price increase'),
    ("en", 'smartphone price increase memory DRAM NAND Samsung Apple Oppo vivo Google'),
    ("en", 'smartphone memory cost storage tier price hike shipment forecast'),
]

HIGH_SOURCES = (
    "reuters", "yonhap", "연합뉴스", "trendforce", "counterpoint",
    "idc", "canalys", "omdia", "bloomberg", "financial times", "wsj",
    "wall street journal",
)
MID_SOURCES = (
    "android authority", "9to5google", "sammobile", "tom's guide", "tomsguide",
    "technews", "科技新報", "sogi", "fnnews", "파이낸셜뉴스", "전자신문", "etnews",
    "zdnet", "the elec", "한국경제", "매일경제", "서울경제",
)
LOW_SOURCES = (
    "notebookcheck", "wccftech", "technobezz", "reddit", "note.com",
)

OEM_MARKERS = (
    "samsung", "galaxy", "apple", "iphone", "oppo", "vivo", "google", "pixel",
    "삼성", "갤럭시", "애플", "아이폰", "구글",
)
MEMORY_MARKERS = (
    "dram", "lpddr", "lpddr6", "nand", "ufs", "memory", "storage",
    "메모리", "디램", "낸드", "저장", "스토리지",
)
PRICE_MARKERS = (
    "price", "prices", "pricing", "msrp", "price hike", "increase price",
    "raise prices", "price increase", "가격", "가격 인상", "출고가", "인상",
)
COST_MARKERS = (
    "memory cost", "component cost", "higher memory", "rising memory", "memory prices",
    "부품 원가", "메모리 가격", "메모리 원가", "원가 상승", "칩플레이션",
)
CONFIG_MARKERS = (
    "reduce ram", "reduce storage", "cut ram", "cut storage", "same configuration",
    "no upgrade", "사양 축소", "용량 축소", "메모리 축소", "저장용량 축소",
)
SHIPMENT_MARKERS = (
    "shipment", "shipments", "forecast", "출하", "출하량", "전망",
)

UA = "Mozilla/5.0 (compatible; khs-smartphone-memory-price-watch/1.0)"


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


def _normalize(value: str) -> str:
    text = _clean(value).lower()
    text = re.sub(r"\s+-\s+[^-]{1,80}$", "", text)
    text = re.sub(r"[^0-9a-z가-힣一-龥%₩원만억~+\-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _source_rank(source: str) -> int:
    raw = _clean(source).lower()
    if any(x.lower() in raw for x in LOW_SOURCES):
        return 0
    if any(x.lower() in raw for x in HIGH_SOURCES):
        return 3
    if raw in ("samsung electronics", "samsung global newsroom", "samsung newsroom", "삼성전자 뉴스룸"):
        return 3
    if any(x.lower() in raw for x in MID_SOURCES):
        return 2
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
    base = f"{_normalize(item.get('title',''))}|{_normalize(item.get('source',''))}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:24]


def _extract_krw_hike(blob: str) -> tuple[int | None, int | None]:
    low = blob.lower().replace(",", "")
    if not any(x in low for x in ("인상", "상승", "올리", "오른", "price hike", "price increase", "increase", "raise", "higher")):
        return None, None
    values: list[int] = []
    for m in re.finditer(
        r"(\d+(?:\.\d+)?)\s*만\s*(?:원)?\s*(?:~|–|—|-|to|에서|부터)\s*(\d+(?:\.\d+)?)\s*만\s*원",
        low,
    ):
        values.extend([round(float(m.group(1)) * 10000), round(float(m.group(2)) * 10000)])
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*만\s*원", low):
        values.append(round(float(m.group(1)) * 10000))
    for m in re.finditer(r"(?:₩\s*|krw\s*)(\d{4,7})\b|\b(\d{4,7})\s*(?:원|krw|won)\b", low):
        values.append(int(m.group(1) or m.group(2)))
    values = [v for v in values if 30000 <= v <= 500000]
    return (min(values), max(values)) if values else (None, None)


def _material_s27_change(lo: int, hi: int, old_lo: int, old_hi: int) -> bool:
    # A headline that repeats only the known upper bound (13만원) is not new.
    if lo == hi and old_lo <= lo <= old_hi:
        return False
    return abs(lo - old_lo) >= 30000 or abs(hi - old_hi) >= 30000


def _is_uncertain(blob: str) -> bool:
    return any(word in blob.lower() for word in (
        "rumor", "rumour", "leak", "tipster", "tipped", "could ", "may ",
        "might ", "expected", "likely", "전망", "예상", "추정",
        "루머", "유출", "가능성", "보도에 따르면", "傳出", "可能", "預計",
    ))


def _model_name(blob: str) -> str:
    low = blob.lower()
    for regex, name in (
        (r"(?:galaxy\s*)?s26\s*ultra", "S26 Ultra"),
        (r"(?:galaxy\s*)?s26\s*plus", "S26 Plus"),
        (r"(?:galaxy\s*)?s26\b", "S26"),
        (r"iphone\s*18\s*pro\s*max", "iPhone 18 Pro Max"),
        (r"iphone\s*18\s*pro", "iPhone 18 Pro"),
        (r"iphone\s*18\b", "iPhone 18"),
        (r"pixel\s*1[01]\b", "Pixel"),
    ):
        if re.search(regex, low):
            return name
    return ""


def _storage_tier(blob: str) -> str | None:
    tiers = {re.sub(r"\s+", "", x).upper()
             for x in re.findall(r"\b(?:128|256|512)\s*gb\b|\b1\s*tb\b", blob.lower())}
    if len(tiers) > 1:
        return None
    return next(iter(tiers)) if tiers else "용량 미확인"


def _retail_price_event(item: dict) -> dict | None:
    blob = f"{item.get('title','')} {item.get('description','')}"
    low = blob.lower()
    if _is_s27(blob) or _is_uncertain(blob) or not _is_price_pass_through(blob):
        return None
    if not any(x in low for x in ("raises", "raised", "hiked", "increase", "인상", "올렸")):
        return None
    model = _model_name(blob)
    if not model:
        return None
    tier = _storage_tier(blob)
    if tier is None:
        return None
    if re.search(r"(?:\bunited states\b|\bu\.s\.?(?=\W|$)|\busa\b|미국)", low):
        matches = re.findall(r"\$\s*(\d{2,3})\b|\b(\d{2,3})\s*(?:usd|dollars?)\b", low)
        dollars = [int(v) for row in matches for v in row if v]
        if dollars and len(set(dollars)) == 1:
            return {"model": model, "market": "미국", "currency": "USD", "amount": dollars[0], "capacity": tier}
    if re.search(r"(?:한국|국내|korea|\bkrw\b|만원)", low):
        lo, hi = _extract_krw_hike(blob)
        if lo is not None and lo == hi:
            return {"model": model, "market": "한국", "currency": "KRW", "amount": lo, "capacity": tier}
    return None


def _extract_pct(blob: str) -> float | None:
    vals = []
    for raw in re.findall(r"([+\-]?\d{1,3}(?:\.\d+)?)\s*%", blob):
        value = float(raw)
        if abs(value) <= 100:
            vals.append(value)
    return vals[0] if vals else None


def _is_s27(blob: str) -> bool:
    low = blob.lower()
    return "galaxy s27" in low or "갤럭시 s27" in low or "갤럭시s27" in low


def _is_price_pass_through(blob: str) -> bool:
    low = blob.lower()
    if not (any(x in low for x in OEM_MARKERS)
            and any(x in low for x in MEMORY_MARKERS)
            and any(x in low for x in COST_MARKERS)):
        return False
    # Memory price appreciation itself is NOT a new handset MSRP increase.
    # Demand clear language about handset selling prices, not just "price".
    handset_price_terms = (
        "smartphone price", "phone price", "galaxy price",
        "iphone price", "pixel price", "handset price",
        "스마트폰 가격", "휴대폰 가격", "갤럭시 가격", "아이폰 가격",
        "폰 가격", "출고가", "출시가",
    )
    if any(x in low for x in handset_price_terms):
        return True
    return bool(re.search(
        r"(?:galaxy|iphone|pixel|스마트폰|휴대폰|갤럭시|아이폰)"
        r"[^.!?\n]{0,55}?(?:prices?|msrp|가격|인상)",
        low
    ) and any(x in low for x in ("raise", "hike", "increase", "인상", "올려", "상향")))


def _is_config_pressure(blob: str) -> bool:
    low = blob.lower()
    return (
        any(x in low for x in OEM_MARKERS)
        and any(x in low for x in MEMORY_MARKERS)
        and any(x in low for x in CONFIG_MARKERS)
    )


def _shipment_revision_pct(blob: str) -> float | None:
    low = blob.lower()
    if not any(x in low for x in OEM_MARKERS) or not any(x in low for x in MEMORY_MARKERS):
        return None
    for clause in re.split(r"[!?;；。]|\n|\|", low):
        # The direction word must be near the SHIPMENT quantity, not near a
        # memory-price percentage somewhere else in the same article.
        forward = (
            r"(?:shipments?|출하량|출하전망|출하 목표)"
            r"[^,.]{0,90}?(?:cut|lowered|reduced|fall|drop|하향|감소|축소)"
            r"[^,.]{0,25}?(\d{1,3}(?:\.\d+)?)\s*%"
        )
        reverse = (
            r"(?:shipments?|출하량|출하전망|출하 목표)"
            r"[^,.]{0,70}?(\d{1,3}(?:\.\d+)?)\s*%"
            r"[^,.]{0,20}?(?:cut|lowered|reduced|fall|drop|하향|감소|축소)"
        )
        m = re.search(forward, clause) or re.search(reverse, clause)
        if m:
            value = float(m.group(1))
            if 5 <= value <= 100:
                return -value
    return None


def _is_shipment_revision(blob: str) -> bool:
    return _shipment_revision_pct(blob) is not None


def _is_official_samsung_item(item: dict) -> bool:
    # A media headline saying "Samsung" is never a manufacturer statement.
    # Google News links are redirects: use the RSS publisher's source URL.
    origin = item.get("source_url") or item.get("link") or ""
    host = (urlparse(origin).hostname or "").lower().removeprefix("www.")
    source = _clean(item.get("source", "")).lower()
    return host in ("news.samsung.com", "samsung.com", "shop.samsung.com") and ("samsung" in source or "삼성" in source)


def _official_s27_price(item: dict) -> bool:
    blob = f"{item.get('title','')} {item.get('description','')}"
    low = blob.lower()
    return (
        _is_official_samsung_item(item)
        and _is_s27(blob)
        and not _is_uncertain(blob)
        and bool(re.search(r"(?:128|256|512)\s*gb|1\s*tb", low))
        and any(x in low for x in ("price", "msrp", "가격", "출고가"))
        and any(x in low for x in ("announc", "increas", "raise", "인상", "발표", "확정"))
        and _extract_krw_hike(blob)[0] is not None
    )


def _load_state() -> dict:
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("seen", [])
            data.setdefault("metrics", {})
            data.setdefault("seen_fact_keys", [])
            return data
    except Exception as exc:
        raise RuntimeError("State file unreadable: stop alerting rather than replaying baseline") from exc
    return {
        "schema_version": 2,
        "initial_alert_sent": False,
        "seen": [],
        "seen_fact_keys": [],
        "metrics": dict(BASELINE),
        "last_alert": None,
    }


def collect() -> tuple[list[dict], list[str]]:
    now = dt.datetime.now(KST)
    cutoff = now - dt.timedelta(days=14)
    rows: dict[str, dict] = {}
    errors: list[str] = []

    for lang, query in QUERIES:
        try:
            root = ET.fromstring(_fetch(_rss_url(lang, query)))
        except Exception as exc:
            errors.append(f"{lang}:{query[:50]} -> {type(exc).__name__}")
            continue

        for node in root.findall(".//item"):
            title = _clean(node.findtext("title"))
            description = _clean(node.findtext("description"))
            link = _clean(node.findtext("link"))
            source_node = node.find("source")
            source = _clean(source_node.text if source_node is not None else "")
            source_url = _clean(source_node.attrib.get("url")) if source_node is not None else ""
            published = _parse_date(_clean(node.findtext("pubDate")))
            if not title or not published or published < cutoff or published > now + dt.timedelta(minutes=15):
                continue
            blob = f"{title} {description} {source}"
            if not (
                _is_price_pass_through(blob)
                or _is_config_pressure(blob)
                or _is_shipment_revision(blob)
                or _is_s27(blob)
            ):
                continue
            item = {
                "title": title,
                "description": description,
                "link": link,
                "source": source or "출처 미표시",
                "source_url": source_url,
                "published_at_kst": published.isoformat(timespec="seconds"),
            }
            rows[_fingerprint(item)] = item

    return sorted(rows.values(), key=lambda x: x["published_at_kst"]), errors


def _fact_keys(item: dict) -> set[str]:
    blob = f"{item.get('title','')} {item.get('description','')}"
    low = blob.lower()
    keys: set[str] = set()
    if _is_s27(blob):
        lo, hi = _extract_krw_hike(blob)
        if lo is not None:
            tier = "official" if _official_s27_price(item) else "rumor"
            keys.add(f"s27_{tier}_krw_hike_{lo}_{hi}")
        if (_is_official_samsung_item(item) and not _is_uncertain(blob)
                and "lpddr6" in low and ("ufs 5.1" in low or "ufs5.1" in low)):
            keys.add("s27_lpddr6_ufs51_official")
    retail = _retail_price_event(item)
    if retail:
        key = (
            f"retail_{retail['model']}_{retail['market']}_{retail['currency']}_"
            f"{retail['amount']}_{retail['capacity']}"
        )
        keys.add(key.lower().replace(" ", "_"))
    if _is_config_pressure(blob) and not _is_uncertain(blob):
        model = "S27" if _is_s27(blob) else _model_name(blob)
        capacities = sorted(set(re.findall(r"(?:8|12|16|24|32|128|256|512)\s*gb", low)))
        if model and capacities:
            keys.add(f"config_{model}_{'_'.join(capacities)}".lower().replace(" ", "_"))
    pct = _shipment_revision_pct(blob)
    if pct is not None:
        model = _model_name(blob) or "brand"
        year = re.search(r"20(?:26|27|28)", low)
        keys.add(f"shipments_{model}_{year.group(0) if year else 'unknown'}_{pct}".lower().replace(" ", "_"))
    return keys


def _signal(item: dict, state: dict) -> dict | None:
    blob = f"{item['title']} {item.get('description','')}"
    low = blob.lower()
    rank = _source_rank(item.get("source", ""))
    if rank < 2:
        return None
    metrics = state.get("metrics") or {}
    reasons: list[str] = []
    changes: dict[str, object] = {}
    stage = 0

    if _is_s27(blob):
        lo, hi = _extract_krw_hike(blob)
        old_lo = int(metrics.get("s27_korea_hike_low_krw") or 0)
        old_hi = int(metrics.get("s27_korea_hike_high_krw") or 0)
        official = _official_s27_price(item)
        if lo is not None and hi is not None and (official or _material_s27_change(lo, hi, old_lo, old_hi)):
            if official:
                reasons.append(f"삼성전자 공식 S27 한국 256GB 등 모델·용량 확인 인상액 {lo//10000}~{hi//10000}만원")
                changes.update({"s27_status": "제조사 공식 발표 확인",
                                "s27_korea_hike_low_krw": lo,
                                "s27_korea_hike_high_krw": hi})
                stage = 3
            else:
                reasons.append(
                    f"S27 한국 가격 인상 전망 변경(공식 미확정) "
                    f"{old_lo//10000}~{old_hi//10000}만원 기준 → {lo//10000}~{hi//10000}만원 보도"
                )
                # A single report never rewrites the standing rumor baseline.
                stage = max(stage, 1)
        if (_is_official_samsung_item(item) and not _is_uncertain(blob)
                and "lpddr6" in low and ("ufs 5.1" in low or "ufs5.1" in low)
                and any(x in low for x in ("채택", "탑재", "ships with", "equipped", "확정"))):
            reasons.append("삼성전자 공식: S27 LPDDR6 및 UFS 5.1 채택 확인")
            changes["s27_lpddr6_ufs51_some_models_status"] = "제조사 공식 확인"
            stage = 3

    retail = _retail_price_event(item)
    if retail and rank >= 3:
        unit = "원" if retail["currency"] == "KRW" else "달러(원화 환산 필수)"
        reasons.append(
            f"스마트폰 출고가 변경 보도: {retail['model']} {retail['market']} "
            f"{retail['capacity']} 인상액 {retail['amount']}{unit} (제조사 직접발표 여부 별도)"
        )
        stage = max(stage, 3 if _is_official_samsung_item(item) else 2)

    if (_is_config_pressure(blob)
            and (_is_s27(blob) or bool(_model_name(blob)))
            and re.search(r"(?:8|12|16|24|32|128|256|512)\s*gb", low)
            and any(x in low for x in ("reduc", "cut ", "축소", "하향"))
            and rank >= 3 and not _is_uncertain(blob)):
        reasons.append("메모리 원가 때문에 스마트폰 RAM·저장용량 사양을 실제 축소한 보도")
        stage = max(stage, 2)

    pct = _shipment_revision_pct(blob)
    if pct is not None and abs(pct) >= 5 and rank >= 3:
        reasons.append(f"메모리 비용에 따른 스마트폰 출하전망 하향 {pct:g}%")
        stage = max(stage, 2)

    if not reasons:
        return None
    return {
        "item": item, "rank": rank, "stage": stage,
        "reasons": reasons[:3], "changes": changes,
        "fact_keys": sorted(_fact_keys(item)),
    }


def _baseline_alert(metrics: dict) -> str:
    return "\n".join([
        "📱 <b>[스마트폰 메모리 원가·판매가 전가 | 기준선]</b>",
        "━━━━━━━━━━━━━━━━",
        "<b>[확정된 전가]</b>",
        "• 삼성전자는 이미 Galaxy S26와 일부 Galaxy A 시리즈 가격을 메모리 비용 상승 국면에서 인상한 것으로 확인됩니다.",
        "• 삼성전자 공식 2분기 자료에서도 MX는 S26·A 시리즈 판매가 견조했지만 <b>부품 원가 상승으로 영업이익이 감소</b>했습니다.",
        "",
        "<b>[Galaxy S27 현재 단계]</b>",
        f"• 한국 가격 인상 전망: <b>{metrics['s27_korea_hike_low_krw']//10000:g}만~{metrics['s27_korea_hike_high_krw']//10000:g}만원 이상</b>",
        "• 현재는 <b>팁스터 기반 전망</b>이며 삼성전자 공식 가격이 아닙니다.",
        "• LPDDR6·UFS 5.1 채택 보도도 일부 Pro/Ultra 모델 대상 루머 단계로 분리합니다.",
        "",
        "<b>[메모리 업황 연결]</b>",
        "• 2027 모바일 DRAM: 공급 타이트·높은 가격 압력 지속 가능성",
        "• 2027 NAND: 하반기 공급 완화 가능성 — DRAM과 NAND를 같은 방향으로 단정하지 않음",
        "",
        "<b>[투자 판정]</b>",
        "• 🟠 <b>메모리 가격결정력의 완제품 전가 확인</b>",
        "• 메모리 업체에는 평균판매단가 방어 신호지만, 스마트폰 업체에는 마진·출하량 역풍입니다.",
        "",
        "<b>[앞으로 새 알림이 가는 조건]</b>",
        "• 삼성전자가 S27 공식 출고가를 발표하거나 가격 인상폭을 확정",
        "• S27 한국 인상폭이 현재 10만~13만원대에서 3만원 이상 추가 변화",
        "• Apple·OPPO·vivo·Google 등 다른 주요 업체가 메모리 원가를 이유로 가격 인상",
        "• 원가 때문에 RAM·저장용량 사양 축소 또는 상위 용량 가격차 확대",
        "• 높은 가격 때문에 스마트폰 출하전망이 5% 이상 하향",
        "• TrendForce가 2027 NAND 하반기 완화 전망을 뒤집거나 모바일 DRAM 부족 전망을 완화",
        "",
        f'<a href="{SAMSUNG_Q2_OFFICIAL}">삼성전자 공식 2분기 실적</a>',
        f'<a href="{S26_PRICE_REUTERS}">Reuters · S26 가격 전가 사례</a>',
        f'<a href="{TRENDFORCE_2027}">TrendForce · 2027 DRAM/NAND 전망</a>',
    ]) + "\n"


def _change_alert(signals: list[dict]) -> str:
    best = max(signals, key=lambda s: (s["stage"], s["rank"], s["item"]["published_at_kst"]))
    stage_text = (
        "🔴 제조사 공식 확인"
        if best["stage"] >= 3
        else ("🟠 실제 출고가·출하 전망 확인" if best["stage"] >= 2 else "🟡 미확정 전망 변화")
    )
    selected = sorted(
        signals,
        key=lambda s: (s["stage"], s["rank"], s["item"]["published_at_kst"]),
        reverse=True,
    )[:3]

    lines = [
        "📱 <b>[스마트폰 메모리 원가·판매가 전가 변화]</b>",
        "━━━━━━━━━━━━━━━━",
        f"• <b>{stage_text}</b>",
    ]
    for signal in selected:
        item = signal["item"]
        lines.append("• " + html.escape(" / ".join(signal["reasons"])))
        lines.append(f"  └ {html.escape(item['source'])} · {html.escape(item['published_at_kst'])}")

    lines += [
        "",
        "<b>[해석 규칙]</b>",
        "• 루머는 공식 확정이 아닙니다. 언론사가 삼성전자를 언급한 것만으로 공식 발표로 승격하지 않습니다.",
        "• 서로 다른 국가·모델·통화·저장용량 숫자는 비교하지 않습니다.",
        "• DRAM과 NAND 수급을 분리합니다. 2027 NAND 완화 가능성을 무시하지 않습니다.",
        "• 가격 전가는 메모리 업체 가격결정력에는 호재지만 스마트폰 출하·부품 수요에는 역풍이 될 수 있습니다.",
        "",
    ]
    for signal in selected:
        item = signal["item"]
        lines.append(f'<a href="{html.escape(item["link"], quote=True)}">원문 · {html.escape(item["source"])}</a>')
    return "\n".join(lines) + "\n"


def _append_alert(alert: str) -> None:
    existing = MAIN_ALERT_PATH.read_text(encoding="utf-8").strip() if MAIN_ALERT_PATH.exists() else ""
    if existing:
        MAIN_ALERT_PATH.write_text(
            existing + "\n\n<<<TELEGRAM_MESSAGE_BREAK>>>\n\n" + alert,
            encoding="utf-8",
        )
    else:
        MAIN_ALERT_PATH.write_text(alert, encoding="utf-8")


def main() -> None:
    now = dt.datetime.now(KST)
    state = _load_state()
    seen = set(state.get("seen") or [])
    seen_fact_keys = set(state.get("seen_fact_keys") or [])
    metrics = dict(BASELINE)
    metrics.update(state.get("metrics") or {})
    items, errors = collect()
    if not items and len(errors) == len(QUERIES):
        raise RuntimeError("All smartphone news queries failed; no-alert state must not advance")
    signals: list[dict] = []

    initial_pending = not bool(state.get("initial_alert_sent"))

    if initial_pending:
        for item in items:
            seen.add(_fingerprint(item))
            seen_fact_keys.update(_fact_keys(item))
    else:
        for item in items:
            fid = _fingerprint(item)
            if fid in seen:
                continue
            fact_keys = _fact_keys(item)
            seen.add(fid)

            # If every fact in an article is already known, treat it as a
            # syndicated repeat even if the headline/source is new.
            if fact_keys and fact_keys.issubset(seen_fact_keys):
                continue

            signal = _signal(item, {**state, "metrics": metrics})
            if signal:
                signals.append(signal)
                metrics.update(signal.get("changes") or {})
                seen_fact_keys.update(signal.get("fact_keys") or [])

    pending = {
        "schema_version": 2,
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "initial_alert_sent": True,
        "seen": sorted(seen)[-700:],
        "seen_fact_keys": sorted(seen_fact_keys)[-300:],
        "metrics": metrics,
        "confirmations": {
            "s27": BASELINE["s27_status"],
            "s26": BASELINE["s26_confirmation"],
            "dram_2027": "TrendForce 공식: 타이트한 모바일 DRAM 공급·높은 비용 압력",
            "nand_2h27": "TrendForce 공식: 2027 하반기 NAND 공급 완화 가능성",
        },
        "last_scan_items": len(items),
        "errors": errors[-20:],
        "last_signal_count": len(signals),
        "last_alert": (
            {
                "at_kst": now.isoformat(timespec="seconds"),
                "kind": "baseline" if initial_pending else "change",
            }
            if initial_pending or signals
            else state.get("last_alert")
        ),
    }
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if initial_pending:
        alert = _baseline_alert(metrics)
        FRAGMENT_PATH.write_text(alert, encoding="utf-8")
        _append_alert(alert)
    elif signals:
        alert = _change_alert(signals)
        FRAGMENT_PATH.write_text(alert, encoding="utf-8")
        _append_alert(alert)
    elif FRAGMENT_PATH.exists():
        FRAGMENT_PATH.unlink()

    STATUS_PATH.write_text(
        "# 스마트폰 메모리 원가·판매가 전가 감시\n"
        f"- checked_at_kst: {now.isoformat(timespec='seconds')}\n"
        f"- items: {len(items)}\n"
        f"- new_signals: {len(signals)}\n"
        f"- initial_alert_pending: {str(initial_pending).lower()}\n"
        f"- s27_korea_hike_low_krw: {metrics.get('s27_korea_hike_low_krw')}\n"
        f"- s27_korea_hike_high_krw: {metrics.get('s27_korea_hike_high_krw')}\n"
        f"- s27_status: {metrics.get('s27_status')}\n"
        f"- dram_2027_tight: {str(bool(metrics.get('dram_2027_tight'))).lower()}\n"
        f"- nand_2h27_easing: {str(bool(metrics.get('nand_2h27_easing'))).lower()}\n"
        f"- errors: {len(errors)}\n",
        encoding="utf-8",
    )


def _merge_checkpoint_states(remote: dict, local: dict) -> dict:
    newer = local if str(local.get("updated_at_kst") or "") >= str(remote.get("updated_at_kst") or "") else remote
    older = remote if newer is local else local
    out = dict(older)
    out.update(newer)
    out["schema_version"] = 2
    out["initial_alert_sent"] = bool(remote.get("initial_alert_sent") or local.get("initial_alert_sent"))
    out["seen"] = sorted(set(remote.get("seen") or []) | set(local.get("seen") or []))[-700:]
    out["seen_fact_keys"] = sorted(set(remote.get("seen_fact_keys") or []) | set(local.get("seen_fact_keys") or []))[-300:]
    official_states = [x for x in (remote, local)
                       if "제조사 공식 발표 확인" in str((x.get("metrics") or {}).get("s27_status") or "")]
    if official_states:
        official = max(official_states, key=lambda x: str(x.get("updated_at_kst") or ""))
        out["metrics"] = dict(out.get("metrics") or {})
        for name in ("s27_status", "s27_korea_hike_low_krw", "s27_korea_hike_high_krw"):
            if name in (official.get("metrics") or {}):
                out["metrics"][name] = official["metrics"][name]
    alerts = [x["last_alert"] for x in (remote, local) if isinstance(x.get("last_alert"), dict)]
    if alerts:
        out["last_alert"] = max(alerts, key=lambda x: x.get("at_kst") or "")
    return out


if __name__ == "__main__":
    main()
