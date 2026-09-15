#!/usr/bin/env python3
"""Panel-leading overlay and final quality gate for Apple iPhone Duo alerts.

Rules:
- panel/share data are leading indicators, never finished-device confirmation alone;
- alert only on material metric deltas versus stored baseline;
- secondary-source changes require corroboration unless unusually large;
- generic panel headlines from the broad watcher are suppressed before Telegram delivery;
- finished-device confirmation still requires Foxconn output / hinge yield / shipment forecast.
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
    "chosunbiz", "biz.chosun.com", "조선비즈",
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


def _clean(value: str | None) -> str:
    text = html.unescape(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize(value: str) -> str:
    text = _clean(value).lower()
    text = re.sub(r"\s+-\s+[^-]{1,80}$", "", text)
    text = re.sub(r"[^0-9a-z가-힣%+./~-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


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
            "User-Agent": "Mozilla/5.0 (compatible; khs-apple-duo-panel-watch/3.0)",
            "Accept": "application/rss+xml,application/xml,text/xml,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        return response.read()


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
    return hashlib.sha256(base.encode()).hexdigest()[:24]


def _load_json(path: pathlib.Path, fallback: dict) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else json.loads(json.dumps(fallback))
    except Exception:
        return json.loads(json.dumps(fallback))


def _load_state() -> dict:
    state = _load_json(STATE_PATH, {
        "schema_version": 3,
        "baseline_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "seen": [], "metrics": DEFAULT_METRICS, "last_alert": None,
    })
    state.setdefault("seen", [])
    state.setdefault("metrics", {})
    for key, value in DEFAULT_METRICS.items():
        state["metrics"].setdefault(key, value)
    return state


def _baseline_dt(state: dict) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(str(state.get("baseline_at_utc") or "").replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(KST)
    except Exception:
        return dt.datetime.now(KST) - dt.timedelta(minutes=5)


def collect() -> tuple[list[dict], list[str]]:
    cutoff = dt.datetime.now(KST) - dt.timedelta(days=7)
    rows, errors = [], []
    for lang, query in QUERIES:
        try:
            root = ET.fromstring(_fetch(_rss_url(lang, query)))
            for node in root.findall(".//item"):
                title, link = _clean(node.findtext("title")), _clean(node.findtext("link"))
                if not title or not link:
                    continue
                source_node = node.find("source")
                published = _parse_date(node.findtext("pubDate"))
                if published and published < cutoff:
                    continue
                rows.append({
                    "title": title, "link": link,
                    "description": _clean(node.findtext("description")),
                    "source": _clean(source_node.text if source_node is not None else ""),
                    "published": published.isoformat(timespec="seconds") if published else None,
                })
        except Exception as exc:
            errors.append(f"{lang}:{query[:45]}… -> {type(exc).__name__}: {exc}")
    dedup = {}
    for row in rows:
        dedup.setdefault(_fingerprint(row), row)
    return list(dedup.values()), errors


def _first(patterns: list[str], text: str) -> float | None:
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            try:
                return float(m.group(1))
            except Exception:
                pass
    return None


def _extract_metrics(item: dict) -> dict[str, float]:
    text = _normalize(f"{item['title']} {item.get('description','')}")
    out = {}
    checks = {
        "apple_panel_share_pct": [
            r"apple[^%]{0,90}?(?:share|account|비중|점유율)[^0-9]{0,20}(\d{1,2}(?:\.\d+)?)\s*%",
            r"apple[^%]{0,90}?(\d{1,2}(?:\.\d+)?)\s*%[^\n]{0,50}(?:panel|패널)",
        ],
        "sdc_q2_share_pct": [
            r"(?:q2|2q|2분기)[^%]{0,100}?(?:samsung display|삼성디스플레이)[^%]{0,60}?(\d{1,2}(?:\.\d+)?)\s*%",
            r"(?:samsung display|삼성디스플레이)[^%]{0,80}?(?:q2|2q|2분기)[^%]{0,50}?(\d{1,2}(?:\.\d+)?)\s*%",
        ],
        "h2_vs_h1_growth_pct": [
            r"(?:h2|하반기)[^%]{0,100}?(?:h1|상반기)[^%]{0,50}?\+?(\d{1,3}(?:\.\d+)?)\s*%",
        ],
        "h2_yoy_growth_pct": [
            r"(?:h2|하반기)[^%]{0,100}?(?:yoy|전년 대비)[^0-9]{0,20}\+?(\d{1,3}(?:\.\d+)?)\s*%",
        ],
        "annual_panel_growth_pct": [
            r"(?:2026|연간|full year)[^%]{0,100}?(?:panel|패널)[^%]{0,70}?(?:growth|증가|성장)[^0-9]{0,20}\+?(\d{1,3}(?:\.\d+)?)\s*%",
        ],
    }
    for key, patterns in checks.items():
        value = _first(patterns, text)
        if value is not None:
            out[key] = value

    m = re.search(r"(?:apple|iphone duo|아이폰 듀오|애플)[^0-9]{0,100}(\d+(?:\.\d+)?)\s*(million|mn|백만|만)\s*(?:panels|panel|장)?", text, re.I)
    if m:
        value, unit = float(m.group(1)), m.group(2).lower()
        if unit == "만":
            value /= 100.0
        if 1 <= value <= 30:
            out["apple_panel_units_m"] = value
    return out


def _is_relevant(item: dict) -> bool:
    text = _normalize(f"{item['title']} {item.get('description','')} {item.get('source','')}")
    return (
        any(x in text for x in ("apple", "iphone duo", "foldable iphone", "아이폰 듀오", "애플 폴더블", "폴더블 아이폰"))
        and any(x in text for x in ("panel", "oled", "display", "패널", "디스플레이", "samsung display", "삼성디스플레이"))
    )


def _metric_events(items: list[dict], state: dict, baseline: dt.datetime) -> tuple[list[dict], list[str]]:
    seen = set(str(x) for x in state.get("seen") or [])
    new_seen, raw = list(seen), []
    old_metrics = state.get("metrics") or {}
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
                pass
        if published and published <= baseline:
            continue
        rank = _source_rank(item.get("source", ""))
        if rank <= 0 or not _is_relevant(item):
            continue
        for metric, new in _extract_metrics(item).items():
            old = float(old_metrics.get(metric, DEFAULT_METRICS.get(metric, new)))
            delta = new - old
            if abs(delta) < THRESHOLDS[metric]:
                continue
            raw.append({"metric": metric, "old": old, "new": new, "delta": delta,
                        "rank": rank, "source": item.get("source") or "미상",
                        "title": item["title"], "link": item["link"],
                        "published": item.get("published"), "fingerprint": fp})

    grouped = defaultdict(list)
    for row in raw:
        grouped[(row["metric"], round(float(row["new"]), 1))].append(row)
    final = []
    for rows in grouped.values():
        sources = sorted(set(r["source"] for r in rows))
        best = sorted(rows, key=lambda x: (x["rank"], x.get("published") or ""), reverse=True)[0]
        strong = abs(best["delta"]) >= 2 * THRESHOLDS[best["metric"]]
        if best["rank"] < 3 and len(sources) < 2 and not strong:
            continue
        best = dict(best, sources=sources, corroboration=len(sources))
        final.append(best)
    final.sort(key=lambda x: (x["rank"], x["corroboration"], abs(x["delta"])), reverse=True)
    return final[:4], list(dict.fromkeys(new_seen))[-600:]


def _confirmation_ladder() -> tuple[str, list[str]]:
    main = _load_json(MAIN_STATE_PATH, {"metrics": {}})
    metrics = main.get("metrics") or {}
    daily = int(float(metrics.get("daily_output_units") or 0))
    hinge = float(metrics.get("hinge_yield_pct") or 0)
    finished = float(metrics.get("finished_units_high_m") or 0)
    score, reasons = 1, ["패널 선행지표"]
    if hinge >= 75:
        score, reasons = max(score, 2), reasons + [f"힌지 수율 {hinge:g}%"]
    if daily >= 10_000:
        score, reasons = max(score, 3), reasons + [f"Foxconn 일 생산 {daily:,}대"]
    if daily >= 30_000 and finished >= 7.5:
        score, reasons = 4, reasons + [f"완제품 전망 상단 {finished:g}백만대"]
    labels = {1:"1/4 선행신호", 2:"2/4 병목 개선 확인중", 3:"3/4 실제 양산 램프업 강함", 4:"4/4 완제품 증산 확인도 높음"}
    return labels[score], reasons


def _fmt(metric: str, value: float) -> str:
    return f"{value:g}백만장" if metric == "apple_panel_units_m" else f"{value:g}%"


def _append_metric_alert(events: list[dict]) -> None:
    if not events:
        return
    existing = ALERT_PATH.read_text(encoding="utf-8").rstrip() if ALERT_PATH.exists() else ""
    ladder, reasons = _confirmation_ladder()
    lines = [existing, "", "<b>📺 패널 선행지표 업데이트</b>"] if existing else [
        "🚨 <b>[Apple iPhone Duo 생산·공급망 감시]</b>",
        f"<i>{dt.datetime.now(KST).strftime('%Y-%m-%d %H:%M KST')}</i>", "", "<b>📺 패널 선행지표 업데이트</b>"]
    for e in events:
        direction = "상향" if e["delta"] > 0 else "하향"
        confidence = "높음" if e["rank"] >= 3 else "중간"
        if e["corroboration"] >= 2:
            confidence += f"·복수출처 {e['corroboration']}곳"
        lines += [
            f"• <b>무엇이 달라졌나:</b> {html.escape(LABELS[e['metric']])} {_fmt(e['metric'],e['old'])} → <b>{_fmt(e['metric'],e['new'])}</b> ({direction})",
            f"• <b>현재 판정:</b> 부품 선행지표 {direction} / 완제품 증산 확정 아님",
            f"• <b>신뢰도:</b> {confidence}",
            f"• {html.escape(_clean(e['title']), quote=False)}",
            f"• <b>출처:</b> {html.escape(_clean(e['source']), quote=False)} · <a href=\"{html.escape(e['link'], quote=True)}\">원문</a>", ""]
    lines += [
        "<b>완제품 확인도</b>", f"• <b>{ladder}</b> — {html.escape(' / '.join(reasons), quote=False)}", "",
        "<b>해석 잠금</b>",
        "• 패널 점유율·패널 출하·Apple 조달 비중은 <b>선행증산</b>입니다. 패널 1장 증가를 Duo 1대 증가로 계산하지 않습니다.",
        "• 실제 완제품 상향은 <b>Foxconn 일 생산량 + 힌지 양품률 + Apple 추가 PO + 완제품 출하전망</b>이 함께 올라갈 때만 판정합니다.", "",
        "<b>다음 확인</b>",
        "• Foxconn 일 생산량 → 힌지 수율/골든샘플 → Samsung Display 추가 PO → 메모리·FPCB·카메라 동시 발주 → TrendForce·Counterpoint·IDC 출하전망"]
    ALERT_PATH.write_text("\n".join(lines).strip()+"\n", encoding="utf-8")


def _final_quality_gate(events: list[dict]) -> tuple[bool, str]:
    """Suppress broad-watcher panel recaps unless overlay found a material delta."""
    if not ALERT_PATH.exists():
        return False, "알림파일 없음"
    text = ALERT_PATH.read_text(encoding="utf-8")
    if events:
        return False, "정량 패널 변화 확인"

    # Generic panel-only main-watcher alerts were too noisy (e.g. recycled Counterpoint headlines).
    panel_only = (
        "<b>현재 판정:</b> 부품 선행증산" in text
        or "<b>현재 판정:</b> 부품 준비 축소" in text
    )
    if panel_only and "📺 패널 선행지표 업데이트" not in text:
        ALERT_PATH.unlink(missing_ok=True)
        return True, "정량 변화 없는 패널 헤드라인 재전송 차단"

    # Generic component-order wording requires a concrete numeric line to justify an alert.
    component_only = "<b>현재 판정:</b> 부품 주문 변화" in text
    if component_only and "<b>숫자:</b>" not in text:
        ALERT_PATH.unlink(missing_ok=True)
        return True, "숫자 없는 부품 주문 헤드라인 차단"
    return False, "통과"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    state = _load_state()
    items, errors = collect()
    events, new_seen = _metric_events(items, state, _baseline_dt(state))

    pending = json.loads(json.dumps(state, ensure_ascii=False))
    pending["schema_version"] = 3
    pending["seen"] = new_seen
    pending["last_scan_kst"] = dt.datetime.now(KST).isoformat(timespec="seconds")
    pending["errors"] = errors[-20:]
    if events:
        for e in events:
            pending.setdefault("metrics", {})[e["metric"]] = e["new"]
        pending["last_alert"] = {"at_kst": dt.datetime.now(KST).isoformat(timespec="seconds"),
                                 "events": [{"metric":e["metric"],"old":e["old"],"new":e["new"],"sources":e["sources"]} for e in events]}
        _append_metric_alert(events)

    suppressed, gate_reason = _final_quality_gate(events)
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")

    ladder, ladder_reasons = _confirmation_ladder()
    lines = [
        "# Apple Duo 패널 선행지표 감시 v3", "",
        f"- 실행시각: {dt.datetime.now(KST).isoformat(timespec='seconds')}",
        f"- 수집항목: {len(items)}", f"- 의미있는 지표 변화: {len(events)}", f"- 오류: {len(errors)}",
        f"- 완제품 확인도: {ladder} ({' / '.join(ladder_reasons)})",
        f"- 최종 알림 품질게이트: {'차단' if suppressed else '통과'} ({gate_reason})", "",
        "## 현재 기준선", f"- {BASELINE_TEXT}", "",
        "## 알림 기준",
        "- Apple 패널 비중 ±2%p, Samsung Display 분기 점유율 ±5%p",
        "- H2/H1·H2 YoY ±8%p, 연간 성장률 ±5%p, Apple향 패널 ±75만장",
        "- 2차 매체 단독 보도는 원칙적으로 복수출처 또는 2배 이상 큰 변화가 있어야 알림",
        "- 숫자 변화 없는 단순 '패널 반등/급증' 헤드라인은 최종 품질게이트에서 삭제",
    ]
    if errors:
        lines += ["", "## 조회 오류"] + [f"- {e}" for e in errors[:8]]
    STATUS_PATH.write_text("\n".join(lines)+"\n", encoding="utf-8")


if __name__ == "__main__":
    main()
