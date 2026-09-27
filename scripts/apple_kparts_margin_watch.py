#!/usr/bin/env python3
"""Apple-linked Korean component margin-pressure watch.

Runs inside the existing Apple Duo workflow and appends to the existing
Telegram alert file. It does not create a new delivery route.

Signals
- USD/KRW quarterly-average appreciation pressure using live FX data.
- Explicit operating-profit estimate/consensus revisions for Apple-exposed K-parts.
- Apple / anonymous North American customer component price-cut pressure.
- Existing Apple DRAM/NAND procurement-price state as cross-context only.

Guardrails
- High-to-low daily FX moves are not substituted for quarterly-average FX.
- Samsung Electro-Mechanics is not treated as a consensus downgrade when a
  report says KRW 650bn is ~9% ABOVE market consensus.
- Anonymous "North American customer" is never silently relabeled as Apple.
- Only explicit estimate/consensus revisions near operating-profit language
  can trigger an earnings-revision alert.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import html
import io
import json
import pathlib
import re
import statistics
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

from fx_api import daily_krw

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "apple_kparts_margin_watch_state.json"
MEMORY_STATE_PATH = ROOT / "data" / "apple_memory_procurement_watch_state.json"
OUT_DIR = ROOT / "out"
OUT_DIR.mkdir(exist_ok=True)
PENDING_PATH = OUT_DIR / "apple_kparts_margin_watch_pending_state.json"
STATUS_PATH = OUT_DIR / "apple_kparts_margin_watch_status.md"
FRAGMENT_PATH = OUT_DIR / "apple_kparts_margin_watch_alert.html"
MAIN_ALERT_PATH = OUT_DIR / "apple_duo_supply_watch_telegram.txt"
KST = ZoneInfo("Asia/Seoul")

BASELINE_AT_KST = dt.datetime(2026, 9, 27, 17, 5, tzinfo=KST)
BASELINE_SOURCE = "https://www.hankyung.com/article/2026092776221"
LGD_CROSSCHECK = "https://www.newspim.com/news/view/20260915000115"
LGI_CROSSCHECK = "https://www.fnnews.com/news/202609210824330199"
SEMCO_CROSSCHECK = "https://kr.investing.com/news/stock-market-news/article-2099123"
SDC_CROSSCHECK = "https://zdnet.co.kr/view/?no=20260923165035"

BASELINE = {
    "lg_display_op_est_eok": 2572,
    "lg_display_consensus_eok": 4291,
    "lg_display_revision_pct": round((2572 / 4291 - 1) * 100, 1),
    "lg_innotek_op_est_eok": 1501,
    "lg_innotek_consensus_eok": 3112,
    "lg_innotek_revision_pct": round((1501 / 3112 - 1) * 100, 1),
    "semco_op_est_eok": 6500,
    "semco_consensus_comment": "시장 컨센서스·기존 추정치 약 9% 상회 보도",
}

COMPANIES = {
    "LG디스플레이": ("lg디스플레이", "lg display"),
    "LG이노텍": ("lg이노텍", "lg innotek"),
    "삼성디스플레이": ("삼성디스플레이", "samsung display"),
    "삼성전기": ("삼성전기", "samsung electro-mechanics", "semco"),
    "비에이치": ("비에이치", "bh"),
    "자화전자": ("자화전자",),
    "덕우전자": ("덕우전자",),
}

QUERIES = [
    ("ko", '"LG디스플레이" 3분기 영업이익 컨센서스 환율 애플'),
    ("ko", '"LG이노텍" 3분기 영업이익 컨센서스 환율 애플'),
    ("ko", '"삼성디스플레이" 판가 인하 북미 고객 애플 환율'),
    ("ko", '"삼성전기" 3분기 영업이익 컨센서스 환율 MLCC'),
    ("ko", '애플 부품 단가 인하 LG디스플레이 LG이노텍 삼성디스플레이 비에이치'),
    ("ko", '애플 카메라 모듈 FPCB 판가 인하 자화전자 덕우전자 비에이치'),
    ("en", '"Apple" component price cut LG Display LG Innotek Samsung Display'),
    ("en", '"Apple supplier" operating profit estimate Korea component FX'),
]

HIGH_SOURCES = (
    "reuters", "bloomberg", "financial times", "wall street journal", "wsj",
    "lg display", "lg이노텍", "samsung", "삼성전자", "삼성전기", "trendforce",
    "fn guide", "fnguide",
)
MID_SOURCES = (
    "한국경제", "hankyung", "뉴스핌", "newspim", "이데일리", "edaily",
    "파이낸셜뉴스", "fnnews", "zdnet", "머니투데이", "매일경제", "서울경제",
    "아주경제", "newsway", "브릿지경제", "alphabiz", "알파경제", "investing",
)
LOW_SOURCES = ("notebookcheck", "wccftech", "technobezz", "reddit", "note.com")

DOWN_WORDS = (
    "하향", "낮춘", "낮춰", "밑돌", "하회", "감소", "줄여", "삭감", "lower",
    "below", "cut", "reduced", "down",
)
UP_WORDS = (
    "상향", "상회", "높인", "높여", "증가", "raise", "raised", "above", "up",
)
REVISION_CONTEXT = (
    "기존 추정치", "기존 전망", "기존 컨센서스", "시장 컨센서스", "컨센서스",
    "시장 기대", "눈높이", "consensus", "prior estimate", "previous estimate",
)
OP_WORDS = ("영업이익", "operating profit", "operating income")
PRICE_PRESSURE = (
    "단가 인하", "판가 인하", "가격 인하 압박", "단가 압박", "판가 압박",
    "price cut", "pricing pressure", "lower component price", "price reduction",
)
APPLE_MARKERS = ("apple", "애플")
ANON_APPLE_MARKERS = ("북미 고객", "북미 전략 고객", "north american customer", "north american client")

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
UA = "Mozilla/5.0 (compatible; khs-apple-kparts-margin-watch/1.0)"


def _clean(v: str | None) -> str:
    s = html.unescape(v or "")
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _norm(v: str) -> str:
    s = _clean(v).lower()
    s = re.sub(r"[^0-9a-z가-힣%.$~+\-]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _source_rank(source: str) -> int:
    s = _norm(source)
    if any(x in s for x in HIGH_SOURCES):
        return 3
    if any(x in s for x in MID_SOURCES):
        return 2
    if any(x in s for x in LOW_SOURCES):
        return 0
    return 1


def _parse_date(v: str | None) -> dt.datetime | None:
    try:
        x = parsedate_to_datetime(v or "")
        if x.tzinfo is None:
            x = x.replace(tzinfo=dt.timezone.utc)
        return x.astimezone(KST)
    except Exception:
        return None


def _rss_url(lang: str, query: str) -> str:
    if lang == "ko":
        params = {"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"}
    else:
        params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)


def _fetch(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml,text/csv,*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _fingerprint(item: dict) -> str:
    base = f"{_norm(item.get('title',''))}|{_norm(item.get('source',''))}"
    return hashlib.sha256(base.encode()).hexdigest()[:24]


def _company_names(blob: str) -> list[str]:
    low = blob.lower()
    out = []
    for name, aliases in COMPANIES.items():
        if any(alias.lower() in low for alias in aliases):
            out.append(name)
    return out


def _revision_stage(revision_pct: float) -> int:
    if revision_pct <= -25:
        return 3
    if revision_pct <= -10:
        return 2
    if revision_pct >= 10:
        return 1
    return 0


def _fx_bucket(qoq_pct: float | None) -> str:
    if qoq_pct is None:
        return "unknown"
    if qoq_pct <= -5:
        return "orange"
    if qoq_pct <= -3:
        return "yellow"
    return "normal"


def _extract_revision(blob: str) -> list[dict]:
    low = blob.lower()
    if not any(word in low for word in OP_WORDS):
        return []

    companies = _company_names(blob)
    if not companies:
        return []

    out: list[dict] = []
    for m in re.finditer(r"(\d{1,3}(?:\.\d+)?)\s*%", blob):
        window = blob[max(0, m.start() - 180): min(len(blob), m.end() + 180)]
        wlow = window.lower()
        if not any(x in wlow for x in OP_WORDS):
            continue
        if not any(x in wlow for x in REVISION_CONTEXT):
            continue
        value = abs(float(m.group(1)))
        direction = 0
        if any(x in wlow for x in DOWN_WORDS):
            direction = -1
        if any(x in wlow for x in UP_WORDS) and not any(x in wlow for x in DOWN_WORDS):
            direction = 1
        if not direction:
            continue
        revision = round(direction * value, 1)
        for company in companies:
            aliases = COMPANIES[company]
            if any(a.lower() in wlow for a in aliases):
                out.append({"company": company, "revision_pct": revision})
    unique = {}
    for row in out:
        key = (row["company"], row["revision_pct"])
        unique[key] = row
    return list(unique.values())


def _extract_pricing_pressure(blob: str) -> dict | None:
    low = blob.lower()
    if not any(x in low for x in PRICE_PRESSURE):
        return None
    companies = _company_names(blob)
    if not companies:
        return None
    named = any(x in low for x in APPLE_MARKERS)
    anonymous = any(x in low for x in ANON_APPLE_MARKERS)
    if not (named or anonymous):
        return None
    return {
        "companies": companies,
        "customer": "Apple" if named else "북미 고객(실명 미확인)",
        "named_customer": named,
    }


def _fetch_fred_usdkrw_series(now: dt.datetime) -> dict[dt.date, float]:
    start = dt.date(2026, 4, 1)
    params = urllib.parse.urlencode({
        "id": "DEXKOUS",
        "cosd": start.isoformat(),
        "coed": now.date().isoformat(),
    })
    raw = _fetch(f"{FRED_CSV}?{params}", timeout=30).decode("utf-8-sig", errors="replace")
    rows: dict[dt.date, float] = {}
    for row in csv.DictReader(io.StringIO(raw)):
        day_raw = (row.get("DATE") or row.get("observation_date") or "").strip()
        val_raw = (row.get("DEXKOUS") or "").strip()
        if not day_raw or not val_raw or val_raw == ".":
            continue
        try:
            day = dt.date.fromisoformat(day_raw)
            val = float(val_raw)
        except Exception:
            continue
        if 500 <= val <= 3000:
            rows[day] = val
    if not rows:
        raise RuntimeError("FRED DEXKOUS recent series unavailable")
    return rows


def _fx_snapshot(now: dt.datetime) -> dict:
    current = daily_krw("USD")
    snap = {
        "latest_rate": round(current.rate, 2),
        "latest_date": current.date,
        "latest_source": current.source,
        "q2_avg": None,
        "q3_avg": None,
        "qoq_pct": None,
        "bucket": "unknown",
        "average_source": "Fed H.10/FRED",
    }
    try:
        rows = _fetch_fred_usdkrw_series(now)
        q2 = [v for d, v in rows.items() if dt.date(2026, 4, 1) <= d <= dt.date(2026, 6, 30)]
        q3 = [v for d, v in rows.items() if dt.date(2026, 7, 1) <= d <= min(now.date(), dt.date(2026, 9, 30))]
        if len(q2) < 20 or len(q3) < 20:
            raise RuntimeError("insufficient quarterly FX observations")
        q2_avg = statistics.mean(q2)
        q3_avg = statistics.mean(q3)
        qoq = (q3_avg / q2_avg - 1) * 100
        snap.update({
            "q2_avg": round(q2_avg, 2),
            "q3_avg": round(q3_avg, 2),
            "qoq_pct": round(qoq, 2),
            "bucket": _fx_bucket(qoq),
        })
    except Exception as exc:
        snap["average_error"] = type(exc).__name__
    return snap


def _load_memory_context() -> dict:
    try:
        data = json.loads(MEMORY_STATE_PATH.read_text(encoding="utf-8"))
        baseline = data.get("baseline") or {}
        return {
            "increase_low": baseline.get("increase_pct_low"),
            "increase_high": baseline.get("increase_pct_high"),
            "confirmation": baseline.get("confirmation"),
        }
    except Exception:
        return {}


def _load_state() -> dict:
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("seen", [])
            return data
    except Exception:
        pass
    return {
        "schema_version": 1,
        "initial_alert_sent": False,
        "seen": [],
        "last_fx_bucket": None,
        "last_alert": None,
    }


def _collect_news(now: dt.datetime) -> tuple[list[dict], list[str]]:
    cutoff = now - dt.timedelta(days=14)
    items: dict[str, dict] = {}
    errors: list[str] = []
    for lang, query in QUERIES:
        try:
            root = ET.fromstring(_fetch(_rss_url(lang, query)))
        except Exception as exc:
            errors.append(f"{lang}:{type(exc).__name__}")
            continue
        for node in root.findall(".//item"):
            title = _clean(node.findtext("title"))
            desc = _clean(node.findtext("description"))
            link = _clean(node.findtext("link"))
            src_node = node.find("source")
            source = _clean(src_node.text if src_node is not None else "")
            published = _parse_date(_clean(node.findtext("pubDate")))
            if not title or not link or not published:
                continue
            if published < cutoff or published > now + dt.timedelta(minutes=15):
                continue
            item = {
                "title": title,
                "description": desc,
                "link": link,
                "source": source or "출처 미표시",
                "published_at_kst": published.isoformat(timespec="seconds"),
            }
            items[_fingerprint(item)] = item
    return sorted(items.values(), key=lambda x: x["published_at_kst"]), errors


def _append_alert(text: str) -> None:
    existing = MAIN_ALERT_PATH.read_text(encoding="utf-8").strip() if MAIN_ALERT_PATH.exists() else ""
    combined = text.strip() if not existing else existing + "\n\n━━━━━━━━━━━━━━━━\n\n" + text.strip()
    MAIN_ALERT_PATH.write_text(combined + "\n", encoding="utf-8")


def _fmt_fx(fx: dict) -> str:
    if fx.get("qoq_pct") is None:
        return f"분기 평균 확인 불가 / 최신 {fx.get('latest_rate')}원({fx.get('latest_date')})"
    return (
        f"2Q 평균 {fx['q2_avg']:,.1f}원 → 3Q 누적 평균 {fx['q3_avg']:,.1f}원 "
        f"({fx['qoq_pct']:+.2f}% QoQ) / 최신 {fx['latest_rate']:,.1f}원"
    )


def _initial_alert(fx: dict, memory: dict) -> str:
    mem = "확인 불가"
    if memory.get("increase_low") is not None and memory.get("increase_high") is not None:
        mem = f"Apple 메모리 조달가격 기준선 +{memory['increase_low']}~{memory['increase_high']}%"
    return "\n".join([
        "🧩 <b>[Apple K부품 마진 압박 | 기준선]</b>",
        "━━━━━━━━━━━━━━━━",
        "<b>[현재 숫자]</b>",
        f"• 원·달러: <b>{html.escape(_fmt_fx(fx))}</b>",
        f"• LG디스플레이 3Q 영업이익: <b>2,572억원</b> vs 컨센서스 4,291억원 → <b>{BASELINE['lg_display_revision_pct']:+.1f}%</b>",
        f"• LG이노텍 3Q 영업이익: <b>1,501억원</b> vs 컨센서스 3,112억원 → <b>{BASELINE['lg_innotek_revision_pct']:+.1f}%</b>",
        "• 삼성전기 3Q 영업이익: <b>6,500억원</b> — 별도 iM증권 보도 기준 시장 컨센서스·기존 추정치보다 약 <b>9% 높음</b>",
        f"• 메모리 압박: <b>{html.escape(mem)}</b>",
        "",
        "<b>[현재 판정]</b>",
        "• 🔴 <b>Apple 민감 K부품 마진 압박 확인</b>",
        "• LG디스플레이·LG이노텍은 이익 눈높이 급락이 확인됐지만, 삼성전기는 AI 서버용 MLCC·FC-BGA가 환율 역풍을 상당 부분 상쇄합니다.",
        "",
        "<b>[앞으로 새 알림이 가는 조건]</b>",
        "• 분기 평균 원·달러가 전분기 대비 -3%/-5% 임계치를 새로 통과하거나 다시 회복",
        "• Apple 민감 부품사의 영업이익 추정치·컨센서스가 추가로 -10%/-25% 이상 조정",
        "• Apple 또는 '북미 고객(실명 미확인)'의 부품 판가·단가 인하 압박이 새로 확인",
        "• 수요 약화와 실제 패널·카메라·FPCB 발주 하향이 같은 방향으로 확인",
        "",
        "<b>[교차검증]</b>",
        f'<a href="{BASELINE_SOURCE}">한국경제 기준 기사</a>',
        f'<a href="{LGD_CROSSCHECK}">LG디스플레이 교차검증</a>',
        f'<a href="{LGI_CROSSCHECK}">LG이노텍 교차검증</a>',
        f'<a href="{SEMCO_CROSSCHECK}">삼성전기 상쇄 요인</a>',
        f'<a href="{SDC_CROSSCHECK}">삼성디스플레이 판가 압박</a>',
    ])


def _fx_alert(old_bucket: str | None, fx: dict) -> str | None:
    new_bucket = fx.get("bucket")
    if new_bucket in (None, "unknown") or new_bucket == old_bucket:
        return None
    labels = {
        "normal": "🟢 환율 부담 완화",
        "yellow": "🟡 환율 경고",
        "orange": "🟠 환율 마진 압박",
    }
    return "\n".join([
        f"💱 <b>[Apple K부품 | {labels.get(new_bucket, new_bucket)}]</b>",
        f"• {_fmt_fx(fx)}",
        "• 고점 대비 하락률이 아니라 분기 평균 환율 변화로 판정합니다.",
    ])


def _news_signal(item: dict) -> dict | None:
    rank = _source_rank(item.get("source", ""))
    if rank < 2:
        return None
    blob = f"{item.get('title','')} {item.get('description','')}"
    revisions = [r for r in _extract_revision(blob) if _revision_stage(r["revision_pct"]) > 0]
    pricing = _extract_pricing_pressure(blob)
    if not revisions and not pricing:
        return None
    stage = 0
    for r in revisions:
        stage = max(stage, _revision_stage(r["revision_pct"]))
    if pricing:
        stage = max(stage, 2 if rank >= 3 else 1)
    return {"item": item, "rank": rank, "revisions": revisions, "pricing": pricing, "stage": stage}


def _news_alert(signal: dict) -> str:
    item = signal["item"]
    lines = ["🧩 <b>[Apple K부품 마진 압박 | 신규 변화]</b>", "━━━━━━━━━━━━━━━━"]
    for r in signal["revisions"]:
        stage = _revision_stage(r["revision_pct"])
        label = "🔴 급격한 이익 눈높이 하향" if stage >= 3 else ("🟠 이익 눈높이 하향" if r["revision_pct"] < 0 else "🟢 이익 눈높이 상향")
        lines.append(f"• {label}: <b>{html.escape(r['company'])} {r['revision_pct']:+.1f}%</b>")
    if signal["pricing"]:
        p = signal["pricing"]
        lines.append(f"• 판가 압박: <b>{html.escape(', '.join(p['companies']))}</b> / 고객: {html.escape(p['customer'])}")
        if not p["named_customer"]:
            lines.append("  └ 고객 실명이 Apple로 확인되지 않았으므로 Apple로 치환하지 않습니다.")
    lines += [
        f"• 출처: {html.escape(item['source'])} · {html.escape(item['published_at_kst'])}",
        f'<a href="{html.escape(item["link"], quote=True)}">원문</a>',
    ]
    return "\n".join(lines)


def main() -> None:
    now = dt.datetime.now(KST)
    state = _load_state()
    seen = set(state.get("seen") or [])
    fx = _fx_snapshot(now)
    memory = _load_memory_context()
    items, errors = _collect_news(now)

    alerts: list[str] = []
    initial_pending = not bool(state.get("initial_alert_sent"))
    if initial_pending:
        alerts.append(_initial_alert(fx, memory))
        state["initial_alert_sent"] = True

    if not initial_pending:
        fx_block = _fx_alert(state.get("last_fx_bucket"), fx)
        if fx_block:
            alerts.append(fx_block)

    fresh_signals: list[dict] = []
    for item in items:
        fid = _fingerprint(item)
        published = dt.datetime.fromisoformat(item["published_at_kst"])
        if published <= BASELINE_AT_KST:
            seen.add(fid)
            continue
        if fid in seen:
            continue
        seen.add(fid)
        signal = _news_signal(item)
        if signal:
            fresh_signals.append(signal)

    fresh_signals.sort(key=lambda x: (x["stage"], x["rank"], x["item"]["published_at_kst"]), reverse=True)
    for signal in fresh_signals[:2]:
        alerts.append(_news_alert(signal))

    pending = {
        "schema_version": 1,
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "initial_alert_sent": bool(state.get("initial_alert_sent")),
        "baseline_at_kst": BASELINE_AT_KST.isoformat(timespec="seconds"),
        "baseline": BASELINE,
        "seen": sorted(seen)[-700:],
        "last_fx_bucket": fx.get("bucket"),
        "last_fx": fx,
        "last_scan_items": len(items),
        "last_signal_count": len(fresh_signals),
        "last_alert": (
            {"at_kst": now.isoformat(timespec="seconds"), "count": len(alerts)}
            if alerts else state.get("last_alert")
        ),
    }
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if alerts:
        text = "\n\n".join(alerts)
        FRAGMENT_PATH.write_text(text + "\n", encoding="utf-8")
        _append_alert(text)
    elif FRAGMENT_PATH.exists():
        FRAGMENT_PATH.unlink()

    STATUS_PATH.write_text(
        "# Apple K부품 마진 압박 감시\n"
        f"- checked_at_kst: {now.isoformat(timespec='seconds')}\n"
        f"- fx: {_fmt_fx(fx)}\n"
        f"- fx_bucket: {fx.get('bucket')}\n"
        f"- scanned_items: {len(items)}\n"
        f"- new_signals: {len(fresh_signals)}\n"
        f"- alert_generated: {str(bool(alerts)).lower()}\n"
        f"- errors: {len(errors)}\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
