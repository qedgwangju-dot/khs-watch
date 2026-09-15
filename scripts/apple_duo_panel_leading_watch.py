#!/usr/bin/env python3
"""Panel-leading overlay for the existing Apple iPhone Duo supply watcher.

Key rules:
- panel/share data are leading indicators, never finished-device confirmation by themselves;
- alert only when a tracked metric changes materially versus the stored baseline;
- suppress headline recycling that merely repeats old 51%/66%/27% figures;
- prefer primary/research sources and require stronger evidence for secondary sources;
- show a confirmation ladder using Foxconn daily output, hinge yield and finished-device forecast.
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
from collections import defaultdict
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "apple_duo_panel_leading_state.json"
MAIN_STATE_PATH = ROOT / "data" / "apple_duo_supply_watch_state.json"
OUT_DIR = ROOT / "out"
PENDING_PATH = OUT_DIR / "apple_duo_panel_leading_pending_state.json"
ALERT_PATH = OUT_DIR / "apple_duo_supply_watch_telegram.txt"
STATUS_PATH = OUT_DIR / "apple_duo_panel_leading_status.md"
KST = ZoneInfo("Asia/Seoul")

QUERIES = [
    ("ko", '애플 폴더블 패널 점유율 삼성디스플레이 카운터포인트'),
    ("ko", '아이폰 듀오 OLED 패널 조달 점유율 출하량'),
    ("ko", '아이폰 듀오 삼성디스플레이 패널 발주 상향 하향'),
    ("ko", '애플 폴더블 패널 하반기 출하 전년 대비 상반기 대비'),
    ("ko", '애플 폴더블 패널 800만 1000만 장 삼성디스플레이'),
    ("en", 'Apple foldable panel procurement share Samsung Display Counterpoint'),
    ("en", 'iPhone Duo OLED panel orders shipment forecast Samsung Display'),
    ("en", 'Apple foldable panel H2 shipments YoY HoH Counterpoint'),
    ("en", 'Apple foldable panel 8 million 10 million Samsung Display'),
]

HIGH_SOURCES = {
    "counterpoint", "trendforce", "reuters", "nikkei", "bloomberg", "financial times",
    "idc", "omdia", "apple", "the information", "wall street journal", "wsj",
}
MID_SOURCES = {
    "financialpost", "파이낸셜포스트", "zdnet", "zdnet korea", "서울경제",
    "seoul economic daily", "전자신문", "etnews", "the elec", "macrumors", "digitimes",
}
LOW_SOURCES = {"wccftech", "ibtimes", "technobezz", "biggo", "note.com"}

DEFAULT_METRICS = {
    "apple_panel_share_pct": 27.0,
    "sdc_q2_share_pct": 66.0,
    "h2_vs_h1_growth_pct": 53.0,
    "h2_yoy_growth_pct": 71.0,
    "annual_panel_growth_pct": 23.0,
    "apple_panel_units_m": 8.0,
}

THRESHOLDS = {
    "apple_panel_share_pct": 2.0,
    "sdc_q2_share_pct": 5.0,
    "h2_vs_h1_growth_pct": 8.0,
    "h2_yoy_growth_pct": 8.0,
    "annual_panel_growth_pct": 5.0,
    "apple_panel_units_m": 0.75,
}

LABELS = {
    "apple_panel_share_pct": "Apple 연간 폴더블 패널 조달 비중",
    "sdc_q2_share_pct": "Samsung Display 분기 폴더블 패널 점유율",
    "h2_vs_h1_growth_pct": "하반기 패널 출하 상반기 대비 성장률",
    "h2_yoy_growth_pct": "하반기 패널 출하 전년 대비 성장률",
    "annual_panel_growth_pct": "연간 폴더블 패널 출하 성장률",
    "apple_panel_units_m": "Apple향 폴더블 패널 준비량",
}

BASELINE_TEXT = (
    "Counterpoint 2026-09 기준 Apple 연간 패널 비중 27%, Samsung Display Q2 점유율 66%, "
    "H2 패널 출하 H1 대비 +53%·YoY +71%, 연간 +23%, Apple향 패널 약 800만 장 수준."
)


def _rss_url(lang: str, query: str) -> str:
    params = {"q": query}
    if lang == "ko":
        params.update({"hl": "ko", "gl": "KR", "ceid": "KR:ko"})
    else:
        params.update({"hl": "en-US", "gl": "US", "ceid": "US:en"})
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; khs-apple-duo-panel-watch/2.0)",
            "Accept": "application/rss+xml,application/xml,text/xml,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        return response.read()


def _clean(value: str | None) -> str:
    text = html.unescape(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize(value: str) -> str:
    text = _clean(value).lower()
    text = re.sub(r"\s+-\s+[^-]{1,80}$", "", text)
    text = re.sub(r"[^0-9a-z가-힣%+./~-]+", " ", text)
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


def _source_rank(source: str) -> int:
    low = _normalize(source)
    if any(x in low for x in HIGH_SOURCES):
        return 3
    if any(x in low for x in MID_SOURCES):
        return 2
    if any(x in low for x in LOW_SOURCES):
        return 0
    return 1


def _fingerprint(item: dict) -> str:
    base = f"{_normalize(item['title'])}|{_normalize(item.get('source', ''))}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:24]


def _load_json(path: pathlib.Path, fallback: dict) -> dict:
    if not path.exists():
        return json.loads(json.dumps(fallback))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else json.loads(json.dumps(fallback))
    except Exception:
        return json.loads(json.dumps(fallback))


def _load_state() -> dict:
    state = _load_json(
        STATE_PATH,
        {
            "schema_version": 2,
            "baseline_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "seen": [],
            "metrics": DEFAULT_METRICS,
            "last_alert": None,
        },
    )
    state.setdefault("seen", [])
    state.setdefault("metrics", {})
    for key, value in DEFAULT_METRICS.items():
        state["metrics"].setdefault(key, value)
    return state


def _baseline_dt(state: dict) -> dt.datetime:
    raw = str(state.get("baseline_at_utc") or "")
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(KST)
    except Exception:
        return dt.datetime.now(KST) - dt.timedelta(minutes=5)


def collect() -> tuple[list[dict], list[str]]:
    cutoff = dt.datetime.now(KST) - dt.timedelta(days=7)
    rows: list[dict] = []
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
                if title and link:
                    rows.append({
                        "title": title,
                        "link": link,
                        "description": description,
                        "source": source,
                        "published": published.isoformat(timespec="seconds") if published else None,
                    })
        except Exception as exc:
            errors.append(f"{lang}:{query[:48]}… -> {type(exc).__name__}: {exc}")

    dedup: dict[str, dict] = {}
    for row in rows:
        dedup.setdefault(_fingerprint(row), row)
    return list(dedup.values()), errors


def _first_float(patterns: list[str], text: str) -> float | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            try:
                return float(match.group(1))
            except Exception:
                pass
    return None


def _extract_metrics(item: dict) -> dict[str, float]:
    text = _normalize(f"{item['title']} {item.get('description', '')}")
    out: dict[str, float] = {}

    value = _first_float([
        r"apple[^%]{0,90}?(\d{1,2}(?:\.\d+)?)\s*%[^\n]{0,80}(?:panel|패널)",
        r"(?:panel|패널)[^%]{0,90}?apple[^%]{0,60}?(\d{1,2}(?:\.\d+)?)\s*%",
        r"apple[^%]{0,80}?(?:account|share|비중|점유율)[^0-9]{0,20}(\d{1,2}(?:\.\d+)?)\s*%",
    ], text)
    if value is not None:
        out["apple_panel_share_pct"] = value

    value = _first_float([
        r"(?:q2|2q|2분기)[^%]{0,100}?(?:samsung display|삼성디스플레이)[^%]{0,60}?(\d{1,2}(?:\.\d+)?)\s*%",
        r"(?:samsung display|삼성디스플레이)[^%]{0,100}?(?:q2|2q|2분기)[^%]{0,60}?(\d{1,2}(?:\.\d+)?)\s*%",
        r"(?:samsung display|삼성디스플레이)[^%]{0,50}?(?:share|점유율)[^0-9]{0,20}(\d{1,2}(?:\.\d+)?)\s*%[^\n]{0,40}(?:q2|2q|2분기)",
    ], text)
    if value is not None:
        out["sdc_q2_share_pct"] = value

    value = _first_float([
        r"(?:h2|2h|하반기)[^%]{0,100}?(?:h1|1h|상반기)[^%]{0,60}?(\d{1,3}(?:\.\d+)?)\s*%",
        r"(?:h2|2h|하반기)[^%]{0,100}?(?:hoh|half on half|상반기 대비)[^0-9]{0,20}\+?(\d{1,3}(?:\.\d+)?)\s*%",
    ], text)
    if value is not None:
        out["h2_vs_h1_growth_pct"] = value

    value = _first_float([
        r"(?:h2|2h|하반기)[^%]{0,120}?(?:yoy|year on year|전년 대비)[^0-9]{0,20}\+?(\d{1,3}(?:\.\d+)?)\s*%",
        r"(?:yoy|전년 대비)[^0-9]{0,20}\+?(\d{1,3}(?:\.\d+)?)\s*%[^\n]{0,80}(?:h2|2h|하반기)",
    ], text)
    if value is not None:
        out["h2_yoy_growth_pct"] = value

    value = _first_float([
        r"(?:2026|full year|annual|연간)[^%]{0,100}?(?:panel|패널)[^%]{0,70}?(?:yoy|growth|증가|성장)[^0-9]{0,20}\+?(\d{1,3}(?:\.\d+)?)\s*%",
        r"(?:panel|패널)[^%]{0,70}?(?:2026|연간)[^%]{0,70}?(?:yoy|증가|성장)[^0-9]{0,20}\+?(\d{1,3}(?:\.\d+)?)\s*%",
    ], text)
    if value is not None:
        out["annual_panel_growth_pct"] = value

    value = _first_float([
        r"(?:apple|iphone duo|아이폰 듀오|애플)[^0-9]{0,100}(\d+(?:\.\d+)?)\s*(?:million|mn)\s*(?:panels|panel|units)?",
        r"(?:apple|iphone duo|아이폰 듀오|애플)[^0-9]{0,100}(\d+(?:\.\d+)?)\s*백만\s*장",
        r"(?:apple|iphone duo|아이폰 듀오|애플)[^0-9]{0,100}(\d+(?:\.\d+)?)\s*만\s*장",
    ], text)
    if value is not None:
        if "만 장" in text and value > 20:
            value /= 100.0
        if 1.0 <= value <= 30.0:
            out["apple_panel_units_m"] = value

    return out


def _is_panel_relevant(item: dict) -> bool:
    text = _normalize(f"{item['title']} {item.get('description', '')} {item.get('source', '')}")
    apple = any(x in text for x in ("apple", "iphone duo", "foldable iphone", "아이폰 듀오", "애플 폴더블", "폴더블 아이폰"))
    panel = any(x in text for x in ("panel", "oled", "display", "패널", "디스플레이", "samsung display", "삼성디스플레이"))
    return apple and panel


def _metric_events(items: list[dict], state: dict, baseline: dt.datetime) -> tuple[list[dict], list[str]]:
    seen = set(str(x) for x in state.get("seen") or [])
    new_seen = list(seen)
    old_metrics = state.get("metrics") or {}
    raw_events: list[dict] = []

    for item in sorted(items, key=lambda x: x.get("published") or "", reverse=True):
        fp = _fingerprint(item)
        if fp in seen:
            continue
        new_seen.append(fp)
        published = None
        if item.get("published"):
            try:
                published = dt.datetime.fromisoformat(item["published"]).astimezone(KST)
            except Exception:
                published = None
        if published and published <= baseline:
            continue
        if not _is_panel_relevant(item):
            continue
        rank = _source_rank(item.get("source", ""))
        if rank <= 0:
            continue
        extracted = _extract_metrics(item)
        for metric, new_value in extracted.items():
            old_value = float(old_metrics.get(metric, DEFAULT_METRICS.get(metric, new_value)))
            threshold = THRESHOLDS[metric]
            delta = new_value - old_value
            if abs(delta) < threshold:
                continue
            raw_events.append({
                "metric": metric,
                "old": old_value,
                "new": new_value,
                "delta": delta,
                "rank": rank,
                "source": item.get("source") or "미상",
                "title": item["title"],
                "link": item["link"],
                "published": item.get("published"),
                "fingerprint": fp,
            })

    grouped: dict[tuple[str, float], list[dict]] = defaultdict(list)
    for event in raw_events:
        grouped[(event["metric"], round(float(event["new"]), 1))].append(event)

    final: list[dict] = []
    for (_, _), rows in grouped.items():
        sources = sorted(set(str(row["source"]) for row in rows))
        best = sorted(rows, key=lambda x: (x["rank"], x.get("published") or ""), reverse=True)[0]
        corroboration = len(sources)
        # Primary/research source can alert alone. Secondary source needs corroboration,
        # unless the move is at least twice the materiality threshold.
        strong_move = abs(float(best["delta"])) >= THRESHOLDS[best["metric"]] * 2
        if best["rank"] < 3 and corroboration < 2 and not strong_move:
            continue
        best = dict(best)
        best["sources"] = sources
        best["corroboration"] = corroboration
        final.append(best)

    final.sort(key=lambda x: (x["rank"], x["corroboration"], abs(x["delta"])), reverse=True)
    return final[:4], list(dict.fromkeys(new_seen))[-600:]


def _confirmation_ladder() -> tuple[str, list[str]]:
    main = _load_json(MAIN_STATE_PATH, {"metrics": {}, "last_alert": None})
    metrics = main.get("metrics") or {}
    daily = int(float(metrics.get("daily_output_units") or 0))
    hinge = float(metrics.get("hinge_yield_pct") or 0)
    finished_high = float(metrics.get("finished_units_high_m") or 0)

    score = 1
    reasons = ["패널 선행지표"]
    if hinge >= 75:
        score += 1
        reasons.append(f"힌지 수율 {hinge:g}%")
    if daily >= 10_000:
        score += 1
        reasons.append(f"Foxconn 일 생산 {daily:,}대")
    if finished_high >= 7.5 and daily >= 30_000:
        score = 4
        reasons.append(f"완제품 전망 상단 {finished_high:g}백만대")

    label = {
        1: "1/4 선행신호",
        2: "2/4 병목 개선 확인중",
        3: "3/4 실제 양산 램프업 강함",
        4: "4/4 완제품 증산 확인도 높음",
    }[min(score, 4)]
    return label, reasons


def _fmt_value(metric: str, value: float) -> str:
    if metric == "apple_panel_units_m":
        return f"{value:g}백만장"
    return f"{value:g}%"


def _append_alert(events: list[dict]) -> None:
    if not events:
        return
    existing = ALERT_PATH.read_text(encoding="utf-8").rstrip() if ALERT_PATH.exists() else ""
    ladder, ladder_reasons = _confirmation_ladder()
    lines: list[str] = []
    if existing:
        lines += [existing, "", "<b>📺 패널 선행지표 업데이트</b>"]
    else:
        lines += [
            "🚨 <b>[Apple iPhone Duo 생산·공급망 감시]</b>",
            f"<i>{dt.datetime.now(KST).strftime('%Y-%m-%d %H:%M KST')}</i>",
            "",
            "<b>📺 패널 선행지표 업데이트</b>",
        ]

    for event in events:
        metric = event["metric"]
        direction = "상향" if event["delta"] > 0 else "하향"
        confidence = "높음" if event["rank"] >= 3 else "중간"
        if event["corroboration"] >= 2:
            confidence += f"·복수출처 {event['corroboration']}곳"
        label = html.escape(LABELS[metric], quote=False)
        title = html.escape(_clean(event["title"]), quote=False)
        source = html.escape(_clean(event["source"]), quote=False)
        link = html.escape(event["link"], quote=True)
        lines += [
            f"• <b>무엇이 달라졌나:</b> {label} {_fmt_value(metric, event['old'])} → <b>{_fmt_value(metric, event['new'])}</b> ({direction})",
            f"• <b>현재 판정:</b> 부품 선행지표 {direction} / 완제품 증산 확정 아님",
            f"• <b>신뢰도:</b> {confidence}",
            f"• {title}",
            f"• <b>출처:</b> {source} · <a href=\"{link}\">원문</a>",
            "",
        ]

    lines += [
        "<b>완제품 확인도</b>",
        f"• <b>{html.escape(ladder, quote=False)}</b> — " + html.escape(" / ".join(ladder_reasons), quote=False),
        "",
        "<b>해석 잠금</b>",
        "• 패널 점유율·패널 출하·Apple 조달 비중은 <b>선행증산</b>입니다. 패널 1장 증가를 Duo 1대 증가로 계산하지 않습니다.",
        "• 실제 완제품 상향은 <b>Foxconn 일 생산량 + 힌지 양품률 + Apple 추가 PO + 완제품 출하전망</b>이 함께 올라갈 때만 판정합니다.",
        "",
        "<b>다음 확인</b>",
        "• Foxconn 일 생산량 → 힌지 수율/골든샘플 → Samsung Display 추가 PO → 메모리·FPCB·카메라 동시 발주 → TrendForce·Counterpoint·IDC 출하전망",
    ]
    ALERT_PATH.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    state = _load_state()
    baseline = _baseline_dt(state)
    items, errors = collect()
    events, new_seen = _metric_events(items, state, baseline)

    pending = json.loads(json.dumps(state, ensure_ascii=False))
    pending["schema_version"] = 2
    pending["seen"] = new_seen
    pending["last_scan_kst"] = dt.datetime.now(KST).isoformat(timespec="seconds")
    pending["errors"] = errors[-20:]

    if events:
        for event in events:
            pending.setdefault("metrics", {})[event["metric"]] = event["new"]
        pending["last_alert"] = {
            "at_kst": dt.datetime.now(KST).isoformat(timespec="seconds"),
            "events": [
                {
                    "metric": event["metric"],
                    "old": event["old"],
                    "new": event["new"],
                    "sources": event["sources"],
                }
                for event in events
            ],
        }
        _append_alert(events)

    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    ladder, ladder_reasons = _confirmation_ladder()
    lines = [
        "# Apple Duo 패널 선행지표 감시 v2",
        "",
        f"- 실행시각: {dt.datetime.now(KST).isoformat(timespec='seconds')}",
        f"- 수집항목: {len(items)}",
        f"- 의미있는 지표 변화: {len(events)}",
        f"- 오류: {len(errors)}",
        f"- 완제품 확인도: {ladder} ({' / '.join(ladder_reasons)})",
        "",
        "## 현재 기준선",
        f"- {BASELINE_TEXT}",
        "",
        "## 알림 기준",
        "- Apple 패널 비중 ±2%p, Samsung Display 분기 점유율 ±5%p",
        "- H2/H1·H2 YoY ±8%p, 연간 성장률 ±5%p, Apple향 패널 ±75만장",
        "- 2차 매체 단독 보도는 원칙적으로 복수출처 또는 2배 이상 큰 변화가 있어야 알림",
    ]
    if errors:
        lines += ["", "## 조회 오류"] + [f"- {error}" for error in errors[:8]]
    STATUS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
