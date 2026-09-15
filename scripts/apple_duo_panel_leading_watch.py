#!/usr/bin/env python3
"""Panel-leading overlay for the existing Apple iPhone Duo supply watcher.

This is intentionally not a separate alert system. It runs inside the existing
Apple Duo workflow and appends a clearly labeled leading-indicator section only
when panel-market/procurement information changes materially.

Important distinction:
- panel share / panel shipment growth = leading component signal
- finished-device production / shipment = confirmation signal
The overlay never upgrades a panel-only change into a finished-device verdict.
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
STATE_PATH = ROOT / "data" / "apple_duo_panel_leading_state.json"
OUT_DIR = ROOT / "out"
PENDING_PATH = OUT_DIR / "apple_duo_panel_leading_pending_state.json"
ALERT_PATH = OUT_DIR / "apple_duo_supply_watch_telegram.txt"
STATUS_PATH = OUT_DIR / "apple_duo_panel_leading_status.md"
KST = ZoneInfo("Asia/Seoul")

QUERIES = [
    ("ko", '애플 폴더블 패널 점유율 삼성디스플레이 카운터포인트'),
    ("ko", '애플 폴더블 패널 출하 하반기 삼성디스플레이 점유율'),
    ("ko", '아이폰 듀오 OLED 패널 조달 점유율 Counterpoint'),
    ("en", 'Apple foldable panel procurement share Samsung Display Counterpoint'),
    ("en", 'Apple foldable panel shipments H2 Samsung Display share'),
    ("en", 'iPhone Duo OLED panel procurement forecast Counterpoint'),
]

HIGH_SOURCES = {
    "counterpoint", "trendforce", "reuters", "nikkei", "bloomberg", "financial times",
    "idc", "omdia", "apple", "the information", "wall street journal", "wsj",
}
MID_SOURCES = {
    "financialpost", "파이낸셜포스트", "zdnet", "zdnet korea", "서울경제",
    "seoul economic daily", "전자신문", "etnews", "the elec", "macrumors",
}
LOW_SOURCES = {"wccftech", "ibtimes", "technobezz", "biggo", "note.com"}

APPLE_MARKERS = {
    "apple", "iphone duo", "foldable iphone", "iphone fold", "아이폰 듀오",
    "애플 폴더블", "폴더블 아이폰",
}
PANEL_MARKERS = {
    "panel", "oled", "display", "procurement", "shipment", "shipments", "share",
    "market share", "samsung display", "sdc", "패널", "디스플레이", "조달",
    "출하", "출하량", "점유율", "삼성디스플레이",
}
CHANGE_MARKERS = {
    "increase", "increased", "rise", "rose", "growth", "grow", "forecast", "share",
    "rebound", "decline", "decrease", "cut", "revision", "revise", "raised", "lowered",
    "증가", "상승", "성장", "전망", "점유율", "반등", "감소", "하락", "상향", "하향", "수정",
}

BASELINE_TEXT = (
    "패널 선행 기준선: Counterpoint 2026-09 기준 Apple 연간 폴더블 패널 조달 비중 27% "
    "(전량 H2), Samsung Display Q2 공급사 점유율 66%, H2 패널 출하 H1 대비 +53%·YoY +71%, "
    "연간 패널 출하 +23%. 패널 지표만으로 Duo 완제품 증산을 확정하지 않음."
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
            "User-Agent": "Mozilla/5.0 (compatible; khs-apple-duo-panel-watch/1.0)",
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
    text = re.sub(r"[^0-9a-z가-힣%+.-]+", " ", text)
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


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {
            "schema_version": 1,
            "baseline_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "seen": [],
            "metrics": {
                "apple_panel_share_pct": 27.0,
                "sdc_q2_share_pct": 66.0,
                "h2_vs_h1_growth_pct": 53.0,
                "h2_yoy_growth_pct": 71.0,
                "annual_panel_growth_pct": 23.0,
            },
            "last_alert": None,
        }
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        data.setdefault("seen", [])
        data.setdefault("metrics", {})
        return data
    except Exception:
        return {
            "schema_version": 1,
            "baseline_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "seen": [],
            "metrics": {},
            "last_alert": None,
        }


def _baseline_dt(state: dict) -> dt.datetime:
    raw = str(state.get("baseline_at_utc") or "")
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(KST)
    except Exception:
        return dt.datetime.now(KST) - dt.timedelta(minutes=5)


def _is_relevant(blob: str) -> bool:
    low = blob.lower()
    return (
        any(x in low for x in APPLE_MARKERS)
        and any(x in low for x in PANEL_MARKERS)
        and any(x in low for x in CHANGE_MARKERS)
    )


def _percentages(blob: str) -> list[float]:
    return [
        float(x) for x in re.findall(r"(\d{1,3}(?:\.\d+)?)\s*%", blob)
        if 0 <= float(x) <= 100
    ]


def _meaningful(item: dict) -> tuple[bool, str, str]:
    blob = f"{item['title']} {item.get('description', '')} {item.get('source', '')}".lower()
    rank = _source_rank(item.get("source", ""))
    if rank == 0 or not _is_relevant(blob):
        return False, "", ""

    source = item.get("source") or "미상"
    pcts = _percentages(blob)
    if rank >= 3:
        confidence = "높음"
    elif rank == 2:
        confidence = "중간·원출처 교차검증 필요"
    else:
        confidence = "낮음"

    if "counterpoint" in blob or "카운터포인트" in blob:
        verdict = "패널 선행지표 변화"
        reason = f"{confidence} | Counterpoint 계열 패널 점유율·출하 전망 변화"
    elif "samsung display" in blob or "삼성디스플레이" in blob or "sdc" in blob:
        verdict = "삼성디스플레이 선행지표 변화"
        reason = f"{confidence} | Samsung Display 점유율·패널 조달/출하 변화"
    else:
        verdict = "Apple 폴더블 패널 선행 변화"
        reason = f"{confidence} | 패널 조달·출하·점유율 변화"

    if pcts:
        reason += " | 기사 내 비율 " + ", ".join(f"{x:g}%" for x in pcts[:5])
    return True, verdict, reason


def collect() -> tuple[list[dict], list[str]]:
    now = dt.datetime.now(KST)
    cutoff = now - dt.timedelta(days=7)
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
                if not title or not link:
                    continue
                rows.append({
                    "title": title,
                    "link": link,
                    "description": description,
                    "source": source,
                    "published": published.isoformat(timespec="seconds") if published else None,
                })
        except Exception as exc:
            errors.append(f"{lang}:{query[:45]}… -> {type(exc).__name__}: {exc}")

    dedup: dict[str, dict] = {}
    for row in rows:
        dedup.setdefault(_fingerprint(row), row)
    return list(dedup.values()), errors


def _append_alert(rows: list[dict]) -> None:
    if not rows:
        return
    existing = ALERT_PATH.read_text(encoding="utf-8").rstrip() if ALERT_PATH.exists() else ""
    lines = []
    if existing:
        lines += [existing, "", "<b>📺 패널 선행지표</b>"]
    else:
        lines += [
            "🚨 <b>[Apple iPhone Duo 생산·공급망 감시]</b>",
            f"<i>{dt.datetime.now(KST).strftime('%Y-%m-%d %H:%M KST')}</i>",
            "",
            "<b>📺 패널 선행지표</b>",
        ]

    for row in rows[:3]:
        title = html.escape(_clean(row["title"]), quote=False)
        source = html.escape(_clean(row.get("source") or "미상"), quote=False)
        verdict = html.escape(row["verdict"], quote=False)
        reason = html.escape(row["reason"], quote=False)
        link = html.escape(row["link"], quote=True)
        lines += [
            f"• {title}",
            f"• <b>현재 판정:</b> {verdict}",
            f"• <b>신뢰도:</b> {reason}",
            f"• <b>출처:</b> {source}",
            f"• <a href=\"{link}\">원문 보기</a>",
            "",
        ]

    lines += [
        "<b>해석 잠금</b>",
        "• 패널 점유율·패널 출하 증가는 <b>부품 선행증산</b>으로만 판정합니다.",
        "• <b>완제품 증산 확정 아님</b>. Foxconn 일 생산량·힌지 양품률·Apple 추가 PO·완제품 출하전망을 별도 확인합니다.",
    ]
    ALERT_PATH.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    state = _load_state()
    baseline = _baseline_dt(state)
    seen = set(str(x) for x in state.get("seen") or [])
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
        new_seen.append(fp)
        if published and published <= baseline:
            continue
        ok, verdict, reason = _meaningful(item)
        if not ok:
            continue
        row = dict(item)
        row.update({"fingerprint": fp, "verdict": verdict, "reason": reason})
        candidates.append(row)

    pending = json.loads(json.dumps(state, ensure_ascii=False))
    pending["seen"] = list(dict.fromkeys(new_seen))[-500:]
    pending["last_scan_kst"] = dt.datetime.now(KST).isoformat(timespec="seconds")
    pending["errors"] = errors[-20:]
    if candidates:
        pending["last_alert"] = {
            "at_kst": dt.datetime.now(KST).isoformat(timespec="seconds"),
            "fingerprints": [x["fingerprint"] for x in candidates[:3]],
            "verdicts": [x["verdict"] for x in candidates[:3]],
        }
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    _append_alert(candidates[:3])

    status = [
        "# Apple Duo 패널 선행지표 오버레이",
        "",
        f"- 실행시각: {dt.datetime.now(KST).isoformat(timespec='seconds')}",
        f"- 수집항목: {len(items)}",
        f"- 신규 패널 선행변화: {len(candidates)}",
        f"- 오류: {len(errors)}",
        "",
        "## 기준선",
        f"- {BASELINE_TEXT}",
    ]
    if errors:
        status += ["", "## 조회 오류"] + [f"- {x}" for x in errors[:10]]
    STATUS_PATH.write_text("\n".join(status) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
