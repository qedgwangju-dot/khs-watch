#!/usr/bin/env python3
"""Apple iPhone Duo production/supply-chain watch.

The watcher is conservative by design:
- monitors only production, shipment, component-order, hinge-yield and assembly changes,
- separates finished-device volume from panel/component preparation,
- suppresses pre-baseline headlines so old articles are not replayed,
- labels source strength instead of treating every supply-chain report as confirmed,
- emits Telegram text only for a new meaningful change.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import os
import pathlib
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "apple_duo_supply_watch_state.json"
OUT_DIR = ROOT / "out"
PENDING_PATH = OUT_DIR / "apple_duo_supply_watch_pending_state.json"
ALERT_PATH = OUT_DIR / "apple_duo_supply_watch_telegram.txt"
STATUS_PATH = OUT_DIR / "apple_duo_supply_watch_status.md"
KST = ZoneInfo("Asia/Seoul")

QUERIES = [
    ("ko", '"아이폰 듀오" 생산량 증산 출하량 폭스콘'),
    ("ko", '"아이폰 듀오" 힌지 수율 골든 샘플 폭스콘'),
    ("ko", '"아이폰 듀오" 삼성디스플레이 패널 주문 발주 출하'),
    ("ko", '"아이폰 듀오" 메모리 FPCB 카메라 부품 주문 상향'),
    ("ko", '"애플 폴더블" 생산 목표 증산 출하량 힌지 수율'),
    ("en", '"iPhone Duo" production shipment build target Foxconn'),
    ("en", '"iPhone Duo" hinge yield Foxconn production'),
    ("en", '"iPhone Duo" Samsung Display panel order shipment'),
    ("en", '"iPhone Duo" component orders memory FPCB camera'),
    ("en", '"Apple foldable" production target shipment hinge yield'),
]

APPLE_MARKERS = {
    "apple", "iphone duo", "iphone fold", "iphone ultra", "foldable iphone",
    "아이폰 듀오", "아이폰 폴드", "아이폰 울트라", "애플 폴더블", "폴더블 아이폰",
}
PRODUCTION_MARKERS = {
    "production", "produce", "build", "shipment", "shipments", "output", "assembly",
    "ramp", "ramp-up", "capacity", "order", "orders", "allocation", "forecast",
    "target", "units", "foxconn", "mass production", "supply chain",
    "생산", "생산량", "증산", "감산", "출하", "출하량", "조립", "램프", "가동",
    "물량", "발주", "주문", "배정", "전망", "목표", "폭스콘", "양산", "공급망",
}
COMPONENT_MARKERS = {
    "panel", "oled", "display", "hinge", "amphenol", "shin zu shing", "eontec",
    "memory", "dram", "lpddr", "nand", "fpcb", "camera", "lens",
    "패널", "디스플레이", "힌지", "신즈싱", "앰페놀", "이온텍",
    "메모리", "디램", "낸드", "카메라", "렌즈",
}
CHANGE_WORDS = {
    "raise", "raises", "raised", "increase", "increases", "increased", "boost",
    "boosts", "boosted", "expand", "expands", "expanded", "double", "doubles",
    "cut", "cuts", "lower", "lowers", "reduce", "reduces", "reduced",
    "tight", "shortage", "delay", "delayed", "improve", "improves", "improved",
    "normalize", "normalizes", "normalized", "surge", "surges", "ramp",
    "상향", "증가", "증산", "확대", "추가", "두 배", "감소", "감산", "축소",
    "부족", "지연", "개선", "정상화", "급증", "램프업", "확보", "늘려",
}
HIGH_SOURCES = {
    "reuters", "nikkei", "bloomberg", "financial times", "trendforce",
    "counterpoint", "idc", "apple", "the information", "wall street journal",
    "wsj", "omdia",
}
MID_SOURCES = {
    "the elec", "zdnet korea", "zdnet", "서울경제", "seoul economic daily",
    "etnews", "전자신문", "macrumors", "digitimes", "businesskorea", "더구루",
    "jiemian", "界面新闻",
}
LOW_SOURCES = {
    "wccftech", "ibtimes", "technobezz", "biggo", "note.com",
    "jablíčkář", "jablickar", "aob news", "macnews", "secnews", "gate",
}

BASELINE_TEXT = (
    "기준선: 2026 완제품 공개 전망 약 500만~700만 대와 별도로, "
    "界面新闻은 9월 17일 기준 글로벌 비축 목표 약 600만~800만 대를 보도. "
    "Apple용 폴더블 OLED 준비량은 약 800만 장 수준, "
    "Foxconn 최종 조립 수율은 9월 17일 기준 60%대 초반으로 보도됐고 "
    "OLED·힌지 납기/수율 병목도 같은 원보도에서 확인됨."
)


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
            "User-Agent": "Mozilla/5.0 (compatible; khs-apple-duo-watch/1.0)",
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
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(KST)
    except Exception:
        return None


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {
            "schema_version": 1,
            "baseline_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "seen": [],
            "metrics": {
                "finished_units_low_m": 5.0,
                "finished_units_high_m": 7.0,
                "stocking_target_low_m": 6.0,
                "stocking_target_high_m": 8.0,
                "panel_units_m": 8.0,
                "daily_output_units": 500,
                "assembly_yield_pct": 60.0,
                "hinge_yield_pct": 65.0,
            },
            "seen_fact_keys": [
                "assembly_yield_60",
                "sep17_assembly_bottleneck",
            ],
            "last_alert": None,
        }
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("state is not an object")
        data.setdefault("seen", [])
        data.setdefault("metrics", {})
        data.setdefault("seen_fact_keys", [])
        return data
    except Exception:
        return {
            "schema_version": 1,
            "baseline_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "seen": [],
            "metrics": {},
            "seen_fact_keys": [],
            "last_alert": None,
        }


def _normalize(text: str) -> str:
    text = _clean(text).lower()
    text = re.sub(r"\s+-\s+[^-]{1,80}$", "", text)
    text = re.sub(r"[^0-9a-z가-힣%.$~+-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _fingerprint(item: dict) -> str:
    base = f"{_normalize(item['title'])}|{_normalize(item.get('source', ''))}"
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


def _is_apple_duo(blob: str) -> bool:
    low = blob.lower()
    return any(x in low for x in APPLE_MARKERS)


def _classify(blob: str) -> set[str]:
    low = blob.lower()
    topics: set[str] = set()
    if any(x in low for x in (
        "shipment", "shipments", "production target", "build target", "출하량",
        "생산 목표", "생산량", "완제품", "build",
    )):
        topics.add("finished")
    if any(x in low for x in (
        "daily output", "per day", "units a day", "units/day", "하루", "일일", "일 생산", "일생산",
    )):
        topics.add("daily")
    if any(x in low for x in ("panel", "oled", "display", "패널", "디스플레이")):
        topics.add("panel")
    if any(x in low for x in ("hinge", "golden sample", "힌지", "골든 샘플")):
        topics.add("hinge")
    if any(x in low for x in ("yield", "yields", "수율", "양품률")):
        topics.add("yield")
    if any(x in low for x in ("foxconn", "assembly", "폭스콘", "조립")):
        topics.add("assembly")
    if any(x in low for x in ("dram", "lpddr", "nand", "memory", "메모리", "디램", "낸드")):
        topics.add("memory")
    if any(x in low for x in ("fpcb", "camera", "lens", "카메라", "렌즈")):
        topics.add("components")
    return topics


def _extract_million_units(blob: str) -> list[float]:
    vals: list[float] = []
    low = blob.lower().replace(",", "")
    patterns = [
        r"(\d+(?:\.\d+)?)\s*(?:million|mn)\s*(?:units|iphones|devices|phones|panels)?",
        r"(\d+(?:\.\d+)?)\s*백만\s*(?:대|장)?",
        r"(\d+(?:\.\d+)?)\s*만\s*(?:대|장)",
    ]
    for idx, pattern in enumerate(patterns):
        for match in re.finditer(pattern, low):
            value = float(match.group(1))
            if idx == 2:
                value /= 100.0
            if 0.05 <= value <= 100:
                vals.append(round(value, 3))
    return vals


def _extract_daily_units(blob: str) -> list[int]:
    vals: list[int] = []
    low = blob.lower().replace(",", "")
    patterns = [
        r"(?:daily|per day|a day)[^0-9]{0,20}(\d{2,7})\s*(?:units|devices|phones)?",
        r"(\d{2,7})\s*(?:units|devices|phones)\s*(?:per day|a day|daily)",
        r"(?:하루|일일|일 생산량|일생산량)[^0-9]{0,20}(\d{2,7})\s*대?",
        r"(\d{2,7})\s*대[^가-힣a-z0-9]{0,8}(?:하루|일일|/일)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, low):
            try:
                value = int(match.group(1))
            except ValueError:
                continue
            if 50 <= value <= 500000:
                vals.append(value)
    return vals


def _extract_percentages(blob: str) -> list[float]:
    return [
        float(value) for value in re.findall(r"(\d{1,3}(?:\.\d+)?)\s*%", blob)
        if 0 <= float(value) <= 100
    ]


def _fact_keys(blob: str) -> set[str]:
    low = blob.lower()
    topics = _classify(low)
    keys: set[str] = set()
    percentages = _extract_percentages(low)

    if "assembly" in topics and "yield" in topics:
        plausible = [x for x in percentages if 20 <= x <= 100]
        for value in plausible:
            keys.add(f"assembly_yield_{int(round(value))}")

    if "hinge" in topics and "yield" in topics:
        plausible = [x for x in percentages if 20 <= x <= 100]
        for value in plausible:
            keys.add(f"hinge_yield_{int(round(value))}")

    if (
        ("assembly" in topics or "hinge" in topics)
        and any(x in low for x in ("low yield", "low yields", "yield issue", "yield issues", "수율 저하", "낮은 수율"))
        and any(x in low for x in ("delay", "delayed", "defect", "defects", "결함", "지연"))
    ):
        keys.add("sep17_assembly_bottleneck")

    return keys


def _translate_to_ko(text: str) -> str:
    text = _clean(text)
    if not text:
        return "Apple iPhone Duo 생산·공급망 신규 변화"
    if len(re.findall(r"[가-힣]", text)) >= 5:
        return text
    params = {
        "client": "gtx", "sl": "auto", "tl": "ko", "dt": "t",
        "ie": "UTF-8", "oe": "UTF-8", "q": text,
    }
    url = "https://translate.googleapis.com/translate_a/single?" + urllib.parse.urlencode(params)
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8"))
            translated = "".join(
                str(part[0]) for part in (data[0] or [])
                if isinstance(part, list) and part and part[0]
            ).strip()
            if translated:
                return translated
        except Exception:
            if attempt == 0:
                time.sleep(1)
    return text


def _meaningful(item: dict, state: dict) -> tuple[bool, str, str]:
    blob = f"{item['title']} {item.get('description', '')} {item.get('source', '')}".lower()
    if not _is_apple_duo(blob):
        return False, "", ""
    if not any(x in blob for x in PRODUCTION_MARKERS | COMPONENT_MARKERS):
        return False, "", ""

    rank = _source_rank(item.get("source", ""))
    # Precision-first gate: unknown/low-grade outlets cannot create a production
    # alert by themselves. They remain searchable context only.
    if rank <= 1:
        return False, "", ""

    topics = _classify(blob)
    change_word = any(x in blob for x in CHANGE_WORDS)
    units_m = _extract_million_units(blob)
    daily = _extract_daily_units(blob)
    percentages = _extract_percentages(blob)
    metrics = state.get("metrics") or {}

    reasons: list[str] = []
    verdict = "공급망 신규 변화"
    metric_change = False
    quantitative_context = bool(units_m or daily or percentages)

    if "daily" in topics and daily:
        previous = int(metrics.get("daily_output_units") or 0)
        current = max(daily)
        if previous <= 0 or current >= max(previous * 1.8, previous + 2000):
            reasons.append(f"일 생산량 {previous:,}→{current:,}대 수준 신호")
            verdict = "완제품 생산 램프업"
            metric_change = True
        elif current <= max(100, int(previous * 0.6)):
            reasons.append(f"일 생산량 둔화 {previous:,}→{current:,}대 수준 신호")
            verdict = "완제품 생산 둔화"
            metric_change = True

    if "finished" in topics and units_m:
        low = float(metrics.get("finished_units_low_m") or 0)
        high = float(metrics.get("finished_units_high_m") or 0)
        current_high = max(units_m)
        if current_high >= max(high + 0.5, 7.5):
            reasons.append(f"완제품 전망/목표 상단 {high:g}→{current_high:g}백만대 상향 신호")
            verdict = "완제품 물량 상향"
            metric_change = True
        elif low and current_high <= low - 0.5:
            reasons.append(f"완제품 전망 {low:g}백만대 기준보다 하향 신호")
            verdict = "완제품 물량 하향"
            metric_change = True

    if "panel" in topics and units_m:
        previous = float(metrics.get("panel_units_m") or 0)
        panel_vals = [x for x in units_m if x >= 1]
        if panel_vals:
            current = max(panel_vals)
            if previous <= 0 or abs(current - previous) >= 1.0:
                direction = "상향" if current > previous else "하향"
                reasons.append(f"OLED 패널 준비량 {previous:g}→{current:g}백만장 {direction} 신호")
                verdict = "부품 선행증산" if current > previous else "부품 준비 축소"
                metric_change = True

    if "assembly" in topics and "yield" in topics and percentages:
        plausible = [x for x in percentages if 20 <= x <= 100]
        if plausible:
            current = max(plausible)
            previous = float(metrics.get("assembly_yield_pct") or 0)
            if previous <= 0 or abs(current - previous) >= 5:
                direction = "개선" if current > previous else "악화"
                reasons.append(f"Foxconn 최종 조립 수율 {previous:g}%→{current:g}% {direction} 신호")
                verdict = "최종 조립 수율 개선" if current > previous else "최종 조립 수율 악화"
                metric_change = True

    if "hinge" in topics and "yield" in topics and percentages and "assembly" not in topics:
        plausible = [x for x in percentages if 20 <= x <= 100]
        if plausible:
            current = max(plausible)
            previous = float(metrics.get("hinge_yield_pct") or 0)
            if previous <= 0 or abs(current - previous) >= 5:
                direction = "개선" if current > previous else "악화"
                reasons.append(f"힌지 수율 {previous:g}%→{current:g}% {direction} 신호")
                verdict = "힌지 병목 개선" if current > previous else "힌지 병목 악화"
                metric_change = True

    # A qualitative bottleneck headline without a new number is alertable only
    # from a high-trust source. Mid-tier or unknown republications cannot
    # generate a fresh alert merely because the article is newly published.
    if (
        not metric_change
        and not quantitative_context
        and rank >= 3
        and change_word
        and ("hinge" in topics or "assembly" in topics)
    ):
        reasons.append("고신뢰 출처에서 생산 램프 병목의 신규 정성 변화 표현 감지")
        verdict = "생산 램프 병목 변화"

    if rank >= 2 and change_word and ("memory" in topics or "components" in topics):
        reasons.append("메모리·FPCB·카메라 등 부품 발주 변화 신호")
        verdict = "부품 주문 변화"

    if rank >= 2 and change_word and "panel" in topics and not reasons:
        reasons.append("OLED 패널 발주·생산 계획 변화 신호")
        verdict = "부품 선행증산"

    if not reasons and rank >= 3 and change_word and topics & {"finished", "daily", "hinge", "assembly", "panel"}:
        reasons.append("고신뢰 출처에서 생산·출하·수율 변화 표현 감지")
        verdict = "고신뢰 생산 변화"

    if not reasons and rank == 2 and change_word and (units_m or daily or percentages):
        reasons.append("공급망 매체의 구체 숫자 포함 변화 보도")
        verdict = "공급망 보도 단계"

    if not reasons:
        return False, "", ""

    confidence = "높음" if rank >= 3 else "중간·추가 교차검증 필요"
    return True, verdict, f"{confidence} | " + " / ".join(reasons[:3])


def collect() -> tuple[list[dict], list[str]]:
    now = dt.datetime.now(KST)
    cutoff = now - dt.timedelta(days=7)
    items: list[dict] = []
    errors: list[str] = []
    for lang, query in QUERIES:
        try:
            root = ET.fromstring(_fetch(_rss_url(lang, query)))
            for node in root.findall(".//item"):
                title = _clean(node.findtext("title"))
                link = _clean(node.findtext("link"))
                description = _clean(node.findtext("description"))
                source_node = node.find("source")
                source = _clean(source_node.text if source_node is not None else "")
                published = _parse_date(node.findtext("pubDate"))
                if published and published < cutoff:
                    continue
                if not title or not link:
                    continue
                items.append({
                    "title": title,
                    "link": link,
                    "description": description,
                    "source": source,
                    "published": published.isoformat(timespec="seconds") if published else None,
                    "lang": lang,
                    "query": query,
                })
        except Exception as exc:
            errors.append(f"{lang}:{query[:42]}… -> {type(exc).__name__}: {exc}")

    dedup: dict[str, dict] = {}
    for item in items:
        dedup.setdefault(_fingerprint(item), item)
    return list(dedup.values()), errors


def _baseline_dt(state: dict) -> dt.datetime:
    raw = str(state.get("baseline_at_utc") or "")
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(KST)
    except Exception:
        return dt.datetime.now(KST) - dt.timedelta(minutes=5)


def _update_metrics(state: dict, item: dict) -> None:
    blob = f"{item['title']} {item.get('description', '')}".lower()
    topics = _classify(blob)
    metrics = state.setdefault("metrics", {})
    units_m = _extract_million_units(blob)
    daily = _extract_daily_units(blob)
    percentages = _extract_percentages(blob)

    if "daily" in topics and daily:
        metrics["daily_output_units"] = max(daily)
    if "finished" in topics and units_m:
        metrics["finished_units_low_m"] = min(units_m)
        metrics["finished_units_high_m"] = max(units_m)
    if "panel" in topics and units_m:
        panel_vals = [x for x in units_m if x >= 1]
        if panel_vals:
            metrics["panel_units_m"] = max(panel_vals)
    if "assembly" in topics and "yield" in topics and percentages:
        plausible = [x for x in percentages if 20 <= x <= 100]
        if plausible:
            metrics["assembly_yield_pct"] = max(plausible)
    if "hinge" in topics and "yield" in topics and percentages and "assembly" not in topics:
        plausible = [x for x in percentages if 20 <= x <= 100]
        if plausible:
            metrics["hinge_yield_pct"] = max(plausible)


def _escape(text: str) -> str:
    return html.escape(_clean(text), quote=False)


def _format_alert(rows: list[dict]) -> str:
    now = dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    lines = [
        "🚨 <b>[Apple iPhone Duo 생산·공급망 감시]</b>",
        f"<i>{now}</i>",
        "",
    ]
    for idx, row in enumerate(rows[:4], 1):
        title_ko = _translate_to_ko(row["title"])
        lines += [
            f"<b>{idx}. 무엇이 달라졌나</b>",
            f"• {_escape(title_ko)}",
            f"• <b>현재 판정:</b> {_escape(row['verdict'])}",
            f"• <b>신뢰도:</b> {_escape(row['reason'])}",
            f"• <b>출처:</b> {_escape(row.get('source') or '미상')}",
        ]
        if row.get("published"):
            try:
                stamp = dt.datetime.fromisoformat(row["published"]).astimezone(KST).strftime("%m-%d %H:%M KST")
                lines.append(f"• <b>보도시각:</b> {stamp}")
            except Exception:
                pass
        blob = f"{row['title']} {row.get('description', '')}"
        units_m = _extract_million_units(blob)
        daily = _extract_daily_units(blob)
        percentages = _extract_percentages(blob)
        nums: list[str] = []
        if units_m:
            nums.append("물량 " + ", ".join(f"{x:g}백만" for x in units_m[:4]))
        if daily:
            nums.append("일 생산 " + ", ".join(f"{x:,}대" for x in daily[:3]))
        if percentages:
            nums.append("비율 " + ", ".join(f"{x:g}%" for x in percentages[:4]))
        if nums:
            lines.append("• <b>숫자:</b> " + " / ".join(nums))
        lines.append(f"• <a href=\"{html.escape(row['link'], quote=True)}\">원문 보기</a>")
        lines.append("")

    lines += [
        "<b>기준선</b>",
        "• " + _escape(BASELINE_TEXT),
        "",
        "<b>투자 의미</b>",
        "• 패널·부품 주문 상향과 Foxconn 완제품 증산은 분리해 판단합니다.",
        "• 실제 완제품 상향은 Foxconn 일 생산량·최종 조립 수율·힌지 양품률·추가 PO·독립기관 출하전망이 함께 올라갈 때 확인합니다.",
        "• 생산 램프 병목 보도와 출시 일정 변경은 분리합니다. Apple 공식 일정은 현재 10월 16일 사전주문·10월 23일 출시로 유지됩니다.",
        "",
        "<b>다음 확인</b>",
        "• Foxconn 일 생산량 → 최종 조립 수율 → 힌지 수율/골든샘플 → Samsung Display 추가 PO → 메모리·FPCB·카메라 동시 발주 → 2026 출하전망 순으로 재검증",
    ]
    return "\n".join(lines).strip() + "\n"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ALERT_PATH.unlink(missing_ok=True)

    state = _load_state()
    seen = set(str(x) for x in state.get("seen") or [])
    seen_fact_keys = set(str(x) for x in state.get("seen_fact_keys") or [])
    baseline = _baseline_dt(state)
    force = str(os.getenv("FORCE_NOTIFY") or "").lower() in {"1", "true", "yes", "on"}

    items, errors = collect()
    candidates: list[dict] = []
    new_seen = list(seen)

    for item in sorted(items, key=lambda x: x.get("published") or "", reverse=True):
        fp = _fingerprint(item)
        if fp in seen:
            continue

        published = None
        if item.get("published"):
            try:
                published = dt.datetime.fromisoformat(item["published"]).astimezone(KST)
            except Exception:
                published = None

        if not force and published and published <= baseline:
            new_seen.append(fp)
            continue

        fact_keys = _fact_keys(f"{item['title']} {item.get('description', '')}")
        if fact_keys and fact_keys.issubset(seen_fact_keys):
            new_seen.append(fp)
            continue

        meaningful, verdict, reason = _meaningful(item, state)
        new_seen.append(fp)
        if meaningful:
            row = dict(item)
            row.update({
                "verdict": verdict,
                "reason": reason,
                "fingerprint": fp,
                "fact_keys": sorted(fact_keys),
                "source_rank": _source_rank(item.get("source", "")),
            })
            candidates.append(row)

    if force and not candidates:
        for item in sorted(items, key=lambda x: x.get("published") or "", reverse=True):
            blob = f"{item['title']} {item.get('description', '')} {item.get('source', '')}".lower()
            if _is_apple_duo(blob) and _source_rank(item.get("source", "")) >= 2 and _classify(blob):
                row = dict(item)
                row.update({
                    "verdict": "수동 점검용 최신 공급망 항목",
                    "reason": "수동 force_notify 실행",
                    "fingerprint": _fingerprint(item),
                })
                candidates = [row]
                break

    pending = json.loads(json.dumps(state, ensure_ascii=False))
    # For the same underlying fact, prefer the strongest source before alerting.
    deduped_candidates: dict[str, dict] = {}
    passthrough: list[dict] = []
    for row in candidates:
        keys = row.get("fact_keys") or []
        if not keys:
            passthrough.append(row)
            continue
        group = "|".join(keys)
        current = deduped_candidates.get(group)
        if current is None or int(row.get("source_rank") or 0) > int(current.get("source_rank") or 0):
            deduped_candidates[group] = row
    candidates = list(deduped_candidates.values()) + passthrough
    candidates.sort(
        key=lambda x: (int(x.get("source_rank") or 0), x.get("published") or ""),
        reverse=True,
    )

    pending["seen"] = list(dict.fromkeys(new_seen))[-800:]
    pending["seen_fact_keys"] = sorted(
        seen_fact_keys | {
            key
            for row in candidates[:4]
            for key in (row.get("fact_keys") or [])
        }
    )[-300:]
    pending["last_scan_kst"] = dt.datetime.now(KST).isoformat(timespec="seconds")
    pending["errors"] = errors[-20:]
    if candidates:
        for row in candidates[:4]:
            _update_metrics(pending, row)
        pending["last_alert"] = {
            "at_kst": dt.datetime.now(KST).isoformat(timespec="seconds"),
            "fingerprints": [x["fingerprint"] for x in candidates[:4]],
            "verdicts": [x["verdict"] for x in candidates[:4]],
        }

    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if candidates:
        ALERT_PATH.write_text(_format_alert(candidates[:4]), encoding="utf-8")

    status = [
        "# Apple Duo 생산·공급망 감시",
        "",
        f"- 실행시각: {dt.datetime.now(KST).isoformat(timespec='seconds')}",
        f"- 수집항목: {len(items)}",
        f"- 신규 의미있는 변화: {len(candidates)}",
        f"- 기존 seen: {len(seen)}",
        f"- 오류: {len(errors)}",
        f"- 알림파일: {'생성' if ALERT_PATH.exists() else '없음'}",
        "",
        "## 기준선",
        f"- {BASELINE_TEXT}",
    ]
    if errors:
        status += ["", "## 조회 오류"] + [f"- {error}" for error in errors[:10]]
    STATUS_PATH.write_text("\n".join(status) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
