#!/usr/bin/env python3
"""Memory spot/contract/HBM web watch for Telegram alerts.

The watcher is intentionally conservative:
- scans multiple Google News RSS queries in Korean and English,
- scores only memory-supply/price/capacity items,
- translates English alert titles into Korean before Telegram delivery,
- stays silent when there is no new meaningful change,
- deduplicates by normalized title/source,
- emits a compact Telegram alert only for new meaningful items.
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
STATE_PATH = ROOT / "data" / "memory_spot_cycle_watch_state.json"
OUT_DIR = ROOT / "out"
PENDING_PATH = OUT_DIR / "memory_spot_cycle_watch_pending_state.json"
ALERT_PATH = OUT_DIR / "memory_spot_cycle_watch_telegram.txt"
STATUS_PATH = OUT_DIR / "memory_spot_cycle_watch_status.md"
KST = ZoneInfo("Asia/Seoul")

QUERIES = [
    ("ko", 'DRAM 현물 가격 공급 부족 BofA OR 뱅크오브아메리카'),
    ("ko", 'NAND 현물 가격 공급 부족 TrendForce OR 트렌드포스'),
    ("ko", '서버 DRAM 고정가격 계약가격 ASP 삼성전자 SK하이닉스'),
    ("ko", '2028 HBM 공급확약 브로드컴 엔비디아 구글 AMD'),
    ("en", 'DRAM spot price shortage BofA Bank of America memory'),
    ("en", 'NAND spot price shortage TrendForce memory'),
    ("en", 'server DRAM contract price TrendForce Samsung SK hynix Micron'),
    ("en", '2028 HBM supply commitment Broadcom NVIDIA Google AMD'),
    ("en", 'HBM trade ratio Micron HBM4E DRAM capacity'),
]

MEMORY_MARKERS = {
    "dram", "ddr4", "ddr5", "lpddr", "hbm", "hbm4", "hbm4e", "nand",
    "essd", "ssd", "memory", "메모리", "디램", "낸드", "현물", "고정가",
}
CHANGE_MARKERS = {
    "spot", "contract", "price", "asp", "shortage", "supply", "capacity", "capa",
    "inventory", "lta", "commitment", "allocation", "raise", "increase", "forecast",
    "outlook", "revised", "revision", "현물", "고정가", "계약가", "가격", "부족",
    "공급", "재고", "증설", "인상", "상향", "전망", "확약", "배정", "수급",
}
HIGH_SIGNAL = {
    "bofa", "bank of america", "trendforce", "dram exchange", "dramexchange", "omdia",
    "reuters", "bloomberg", "citi", "ubs", "micron", "samsung", "sk hynix", "sk하이닉스",
    "삼성전자", "nvidia", "엔비디아", "broadcom", "브로드컴", "google", "구글", "amd",
}
CRITICAL_MARKERS = {
    "sufficiency", "공급 충족", "under supply", "undersupply", "shortage", "공급부족",
    "2027", "2028", "hbm4e", "lta", "장기계약", "공급확약", "commitment",
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
            "User-Agent": "Mozilla/5.0 (compatible; khs-memory-watch/1.1)",
            "Accept": "application/rss+xml,application/xml,text/xml,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        return response.read()


def _clean(text: str | None) -> str:
    value = html.unescape(text or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _translate_to_ko(text: str) -> str:
    """Translate non-Korean alert text to Korean.

    We deliberately do not expose an English title if translation is temporarily
    unavailable. The source name and original link remain untouched identifiers.
    """
    text = _clean(text)
    if not text:
        return "메모리 관련 신규 변화"
    hangul = len(re.findall(r"[가-힣]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if hangul >= max(4, latin // 3):
        return text

    params = {
        "client": "gtx",
        "sl": "auto",
        "tl": "ko",
        "dt": "t",
        "ie": "UTF-8",
        "oe": "UTF-8",
        "q": text,
    }
    url = "https://translate.googleapis.com/translate_a/single?" + urllib.parse.urlencode(params)
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/json,text/plain,*/*",
                },
            )
            with urllib.request.urlopen(req, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8"))
            translated = "".join(
                str(part[0]) for part in (data[0] or [])
                if isinstance(part, list) and part and part[0]
            ).strip()
            if translated and re.search(r"[가-힣]", translated):
                return translated
        except Exception:
            if attempt < 2:
                time.sleep(1.0 + attempt)

    lower = text.lower()
    if "spot" in lower and "price" in lower:
        return "메모리 현물가격 관련 신규 상승·수급 변화 기사 감지"
    if "shortage" in lower or "supply" in lower:
        return "메모리 공급부족·수급 관련 신규 변화 기사 감지"
    if "hbm" in lower:
        return "HBM 수요·공급능력 관련 신규 변화 기사 감지"
    if "dram" in lower:
        return "DRAM 가격·수급 관련 신규 변화 기사 감지"
    if "nand" in lower or "ssd" in lower:
        return "NAND·SSD 가격·수급 관련 신규 변화 기사 감지"
    return "해외 메모리 관련 신규 변화 기사 감지"


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


def _normalize_title(title: str) -> str:
    title = title.lower()
    title = re.sub(r"\s+-\s+[^-]{1,80}$", "", title)
    title = re.sub(r"[^0-9a-z가-힣%]+", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def _fingerprint(item: dict) -> str:
    base = f"{_normalize_title(item['title'])}|{item.get('source','').lower()}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:24]


def _score(item: dict) -> int:
    blob = f"{item['title']} {item.get('source','')} {item.get('description','')}".lower()
    score = 0
    mem_hits = sum(1 for x in MEMORY_MARKERS if x in blob)
    change_hits = sum(1 for x in CHANGE_MARKERS if x in blob)
    high_hits = sum(1 for x in HIGH_SIGNAL if x in blob)
    critical_hits = sum(1 for x in CRITICAL_MARKERS if x in blob)

    if mem_hits == 0 or change_hits == 0:
        return 0
    score += min(mem_hits, 3) * 2
    score += min(change_hits, 3) * 2
    score += min(high_hits, 2) * 2
    score += min(critical_hits, 2) * 2
    if re.search(r"(?:\+|-)?\d+(?:\.\d+)?%", blob):
        score += 2
    if re.search(r"\b(?:2027|2028)\b", blob):
        score += 1
    return score


def collect() -> tuple[list[dict], list[str]]:
    items: list[dict] = []
    errors: list[str] = []
    now = dt.datetime.now(KST)
    cutoff = now - dt.timedelta(days=10)

    for lang, query in QUERIES:
        url = _rss_url(lang, query)
        try:
            root = ET.fromstring(_fetch(url))
            for node in root.findall(".//item"):
                title = _clean(node.findtext("title"))
                link = _clean(node.findtext("link"))
                description = _clean(node.findtext("description"))
                pub = _parse_date(node.findtext("pubDate"))
                source_node = node.find("source")
                source = _clean(source_node.text if source_node is not None else "")
                if not title or not link:
                    continue
                if pub and pub < cutoff:
                    continue
                item = {
                    "title": title,
                    "link": link,
                    "description": description,
                    "source": source,
                    "published_kst": pub.isoformat(timespec="seconds") if pub else None,
                    "query": query,
                }
                item["score"] = _score(item)
                if item["score"] >= 8:
                    item["fingerprint"] = _fingerprint(item)
                    items.append(item)
        except Exception as exc:
            errors.append(f"{lang}:{query}: {type(exc).__name__}: {exc}")

    by_fp: dict[str, dict] = {}
    for item in items:
        fp = item["fingerprint"]
        prev = by_fp.get(fp)
        if prev is None or (item["score"], item.get("published_kst") or "") > (
            prev["score"], prev.get("published_kst") or ""
        ):
            by_fp[fp] = item
    return sorted(
        by_fp.values(),
        key=lambda x: (x.get("published_kst") or "", x["score"]),
        reverse=True,
    ), errors


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"initialized": False, "seen": {}, "updated_at_kst": None}
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(state.get("seen"), dict):
            state["seen"] = {}
        return state
    except Exception:
        return {"initialized": False, "seen": {}, "updated_at_kst": None}


def classify(title: str) -> str:
    t = title.lower()
    if "hbm" in t or "2028" in t:
        return "HBM/CAPA"
    if "spot" in t or "현물" in t:
        return "현물가"
    if "contract" in t or "고정가" in t or "계약가" in t:
        return "계약가"
    if "nand" in t or "낸드" in t or "ssd" in t:
        return "NAND/eSSD"
    if "inventory" in t or "재고" in t or "sufficiency" in t:
        return "재고/수급"
    return "DRAM"


def compact_title(title: str, source: str) -> str:
    suffix = f" - {source}" if source else ""
    if suffix and title.endswith(suffix):
        title = title[: -len(suffix)]
    return title.strip()


def write_outputs(items: list[dict], errors: list[str]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()
    seen: dict = state.get("seen", {})
    now = dt.datetime.now(KST)
    initialized = bool(state.get("initialized"))

    new_items = [x for x in items if x["fingerprint"] not in seen]
    force_notify = os.getenv("FORCE_NOTIFY", "").strip().lower() in {"1", "true", "yes"}
    if force_notify:
        report_items = items[:5]
    elif initialized:
        report_items = new_items[:5]
    else:
        report_items = []

    for item in items:
        seen[item["fingerprint"]] = {
            "title": item["title"],
            "source": item.get("source"),
            "published_kst": item.get("published_kst"),
            "first_seen_kst": seen.get(item["fingerprint"], {}).get("first_seen_kst") or now.isoformat(timespec="seconds"),
        }

    if len(seen) > 700:
        keys = list(seen.keys())[-700:]
        seen = {k: seen[k] for k in keys}

    pending = {
        "initialized": True,
        "seen": seen,
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "last_scan_count": len(items),
        "last_new_count": len(new_items),
    }
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    status_lines = [
        "# 메모리 현물·계약가·HBM 웹 감시",
        "",
        f"- 조회시각(KST): {now.isoformat(timespec='seconds')}",
        f"- 유효 후보: {len(items)}건",
        f"- 신규 후보: {len(new_items)}건",
        f"- Telegram 대상 신규: {len(report_items)}건",
        f"- 원천 오류: {len(errors)}건",
    ]
    if errors:
        status_lines += ["", "## 오류", *[f"- {x}" for x in errors[:6]]]
    STATUS_PATH.write_text("\n".join(status_lines) + "\n", encoding="utf-8")

    if ALERT_PATH.exists():
        ALERT_PATH.unlink()
    if not report_items:
        return

    lines = [
        "<b>[메모리 수급 변화 감지]</b>",
        f"조회 {now.strftime('%Y-%m-%d %H:%M')} KST · 신규 {len(report_items)}건",
    ]
    for item in report_items:
        label = classify(item["title"])
        raw_title = compact_title(item["title"], item.get("source", ""))
        title = _translate_to_ko(raw_title)
        if len(title) > 112:
            title = title[:109].rstrip() + "…"
        pub = item.get("published_kst")
        date_text = ""
        if pub:
            try:
                date_text = dt.datetime.fromisoformat(pub).strftime("%m/%d %H:%M")
            except Exception:
                pass
        safe_title = html.escape(title)
        safe_link = html.escape(item["link"], quote=True)
        lines.append(f"• <b>{label}</b> | {safe_title}")
        if date_text:
            lines.append(f"  {date_text} · <a href=\"{safe_link}\">원문</a>")
        else:
            lines.append(f"  <a href=\"{safe_link}\">원문</a>")
    lines.append("※ 가격·수급·LTA·2027~28 HBM/CAPA의 신규 변화만 알림")
    ALERT_PATH.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def main() -> int:
    items, errors = collect()
    write_outputs(items, errors)
    print(f"memory_watch_candidates={len(items)} errors={len(errors)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
