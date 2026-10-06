#!/usr/bin/env python3
"""ABF / FC-BGA package-substrate cycle watcher.

Tracks the supply-demand cycle behind AI/server package substrates without
confusing ordinary PCB headlines with qualified high-end ABF capacity.

Baseline logic:
- The user-provided BofA chart corresponds to the older 2026/27/28 shortage
  forecast of 4%/10%/16%.
- BofA's 2026-08-19 update widened that forecast to 7%/14%/19%.
- The watcher treats 4%/10%/16% as a historical prior baseline and must never
  downgrade the live BofA state merely because the old chart is reposted.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import pathlib
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

try:
    from googlenewsdecoder import gnewsdecoder
except Exception:  # pragma: no cover
    gnewsdecoder = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "abf_package_substrate_cycle_state.json"
OUT_DIR = ROOT / "out"
ALERT_PATH = OUT_DIR / "abf_package_substrate_cycle_alert.html"
PENDING_PATH = OUT_DIR / "abf_package_substrate_cycle_pending_state.json"
STATUS_PATH = OUT_DIR / "abf_package_substrate_cycle_status.md"
KST = ZoneInfo("Asia/Seoul")

TRACK_VERSION = 1
PRIOR_BofA = {
    "as_of": "2026-06",
    "shortage_2026_pct": 4.0,
    "shortage_2027_pct": 10.0,
    "shortage_2028_pct": 16.0,
    "server_cpu_share_2026_pct": 13.0,
    "server_cpu_share_2027_pct": 14.0,
    "server_cpu_share_2028_pct": 14.0,
    "source_kind": "사용자 제공 BofA Global Research 차트 + 최신 BofA 리비전에서 과거 전망으로 재확인",
}
CURRENT_BofA = {
    "as_of": "2026-08-19",
    "shortage_2026_pct": 7.0,
    "shortage_2027_pct": 14.0,
    "shortage_2028_pct": 19.0,
    "server_cpu_share_2026_pct": 17.0,
    "server_cpu_share_2027_pct": 21.0,
    "server_cpu_share_2028_pct": 21.0,
    "supply_growth_2026_pct": 12.0,
    "supply_growth_2027_pct": 22.0,
    "supply_growth_2028_pct": 19.0,
    "unimicron_capacity_growth_2027_min_pct": 30.0,
    "unimicron_capacity_growth_2028_min_pct": 30.0,
    "unimicron_high_value_share_2h26_min_pct": 50.0,
    "nypcb_high_end_switch_share_min_pct": 50.0,
    "source": "BofA Global Research",
    "source_kind": "BofA 리포트 해설 재현자료 교차확인",
    "source_url": "https://www.xxquant.com/en/institution/institutional-research/e9049647f76459043c0fe4af2e72ff82",
    "secondary_source_url": "https://www.cmoney.tw/forum/article/182861822",
    "source_rank": 2,
}

SUPPLIERS = {
    "Unimicron": ("unimicron", "欣興", "欣兴"),
    "Nan Ya PCB": ("nan ya pcb", "nypcb", "南電", "南电"),
    "Kinsus": ("kinsus", "景碩", "景硕"),
    "Ibiden": ("ibiden", "揖斐電", "揖斐电"),
    "Samsung Electro-Mechanics": ("samsung electro-mechanics", "semco", "삼성전기"),
    "Daeduck Electronics": ("daeduck electronics", "대덕전자"),
    "AT&S": ("at&s", "ats austria"),
    "Shinko Electric": ("shinko electric", "新光電気", "新光电气"),
    "Ajinomoto": ("ajinomoto", "味の素"),
}

QUERIES = [
    ("en", '"BofA" ABF substrate shortage 2026 2027 2028 7% 14% 19%'),
    ("en", '"BofA Global Research" "ABF substrate" server CPU 17% 21% 21%'),
    ("en", 'ABF substrate supply shortage AI server CPU Unimicron NYPCB Kinsus Ibiden'),
    ("en", 'ABF substrate price increase capacity expansion qualification yield warpage'),
    ("en", 'FC-BGA substrate AI server GPU ASIC CPU capacity shortage Samsung Electro-Mechanics Daeduck'),
    ("en", 'Ajinomoto ABF film shortage capacity semiconductor package substrate'),
    ("ko", 'BofA ABF 기판 공급부족 2026 2027 2028 7% 14% 19%'),
    ("ko", 'ABF 기판 서버 CPU 수요 Unimicron 남전 Kinsus Ibiden 증설 가격 인상'),
    ("ko", 'FC-BGA 기판 AI 서버 삼성전기 대덕전자 증설 수율 고객인증'),
    ("ko", 'ABF 필름 아지노모토 기판 공급부족 증설'),
    ("zh", 'ABF 載板 供給不足 2026 2027 2028 美銀 欣興 南電 景碩'),
]

OFFICIAL_DOMAINS = {
    "unimicron.com", "nanyapcb.com.tw", "kinsus.com.tw", "ibiden.com",
    "samsungsem.com", "daeduck.com", "ats.net", "shinko.co.jp", "ajinomoto.com",
}
TIER1_DOMAINS = {
    "reuters.com", "bloomberg.com", "nikkei.com", "trendforce.com",
    "digitimes.com", "cmoney.tw", "xxquant.com",
}

def _clean(value: str | None) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def _rss_url(lang: str, query: str) -> str:
    if lang == "ko":
        p = {"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"}
    elif lang == "zh":
        p = {"q": query, "hl": "zh-TW", "gl": "TW", "ceid": "TW:zh-Hant"}
    else:
        p = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(p)

def _fetch(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; khs-abf-cycle-watch/1.0)"},
    )
    err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.read()
        except Exception as exc:
            err = exc
            if attempt < 2:
                time.sleep(1 + attempt)
    raise err

def _decode(link: str) -> str:
    if "news.google.com" not in (link or "") or gnewsdecoder is None:
        return link
    try:
        out = gnewsdecoder(link, interval=0.15)
        if isinstance(out, dict):
            url = str(out.get("decoded_url") or "").strip()
            if url.startswith("http") and "news.google.com" not in url:
                return url
    except Exception:
        pass
    return link

def _pub_kst(raw: str) -> str:
    try:
        d = parsedate_to_datetime(raw)
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d.astimezone(KST).isoformat(timespec="seconds")
    except Exception:
        return ""

def _host(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.lower()
    except Exception:
        return ""

def _source_rank(item: dict) -> int:
    host = _host(str(item.get("link") or ""))
    if any(host == d or host.endswith("." + d) for d in OFFICIAL_DOMAINS):
        return 3
    if any(host == d or host.endswith("." + d) for d in TIER1_DOMAINS):
        return 2
    src = _clean(str(item.get("source") or "")).lower()
    if any(k in src for k in ("bofa", "bank of america", "trendforce", "nikkei", "reuters", "bloomberg")):
        return 2
    return 0

def _normalize_title(value: str) -> str:
    value = _clean(value).lower()
    value = re.sub(r"\s+[-–—|]\s+[^-–—|]{1,80}$", "", value)
    value = re.sub(r"[^0-9a-z가-힣一-龥]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def _fingerprint(title: str, source: str) -> str:
    return hashlib.sha256((_normalize_title(title) + "|" + source.lower()).encode()).hexdigest()[:24]

def _suppliers(text: str) -> list[str]:
    low = " " + text.lower() + " "
    out = []
    for name, aliases in SUPPLIERS.items():
        if any(alias.lower() in low or alias in text for alias in aliases):
            out.append(name)
    return out

def _is_abf_item(item: dict) -> bool:
    text = _clean(f"{item.get('title','')} {item.get('description','')}")
    low = text.lower()
    substrate = any(k in low for k in (
        "abf substrate", "package substrate", "fc-bga", "fcbga",
        "載板", "载板", "패키지 기판", "반도체 기판",
    ))
    driver = any(k in low for k in (
        "supply", "shortage", "deficit", "undersupply", "capacity", "price", "asp",
        "server cpu", "gpu", "asic", "ai server", "qualification", "yield", "warpage",
        "공급", "부족", "수급", "증설", "가격", "서버 cpu", "수율", "휨",
        "供給", "供给", "短缺", "產能", "产能", "漲價", "涨价",
    ))
    return bool(substrate and driver)

def _extract_bofa(item: dict) -> dict | None:
    text = _clean(f"{item.get('title','')} {item.get('description','')}")
    low = text.lower()
    if not _is_abf_item(item) or not any(k in low for k in ("bofa", "bank of america", "美銀", "美银")):
        return None
    if _source_rank(item) < 2:
        return None

    obs: dict = {}
    # Known old forecast must never overwrite the live Aug-19 baseline merely
    # because a screenshot/repost is published later.
    old_triplet = bool(
        re.search(r"4\s*%[^0-9]{0,20}10\s*%[^0-9]{0,20}16\s*%", text)
        or re.search(r"4\s*/\s*10\s*/\s*16\s*%", text)
    )
    new_triplet = bool(
        re.search(r"7\s*%[^0-9]{0,20}14\s*%[^0-9]{0,20}19\s*%", text)
        or re.search(r"7\s*/\s*14\s*/\s*19\s*%", text)
    )
    if old_triplet and not new_triplet:
        obs["historical_prior_repost"] = True
        obs["prior_shortage_2026_pct"] = 4.0
        obs["prior_shortage_2027_pct"] = 10.0
        obs["prior_shortage_2028_pct"] = 16.0
    if new_triplet:
        obs.update({
            "shortage_2026_pct": 7.0,
            "shortage_2027_pct": 14.0,
            "shortage_2028_pct": 19.0,
        })

    if re.search(r"17\s*%[^0-9]{0,20}21\s*%[^0-9]{0,20}21\s*%", text):
        obs.update({
            "server_cpu_share_2026_pct": 17.0,
            "server_cpu_share_2027_pct": 21.0,
            "server_cpu_share_2028_pct": 21.0,
        })
    if re.search(r"12\s*%[^0-9]{0,20}22\s*%[^0-9]{0,20}19\s*%", text):
        obs.update({
            "supply_growth_2026_pct": 12.0,
            "supply_growth_2027_pct": 22.0,
            "supply_growth_2028_pct": 19.0,
        })

    if not obs:
        return None
    obs.update({
        "source": item.get("source") or "출처 미표시",
        "source_url": item.get("link") or "",
        "source_rank": _source_rank(item),
        "as_of": (item.get("published_kst") or "")[:10],
    })
    return obs

def _material_changes(old: dict, new: dict) -> list[str]:
    changes = []
    for key, label in (
        ("shortage_2026_pct", "ABF 2026E 공급부족"),
        ("shortage_2027_pct", "ABF 2027E 공급부족"),
        ("shortage_2028_pct", "ABF 2028E 공급부족"),
    ):
        a, b = old.get(key), new.get(key)
        if b is None:
            continue
        if a is None:
            changes.append(f"{label}: {float(b):.1f}% 신규 확인")
        elif abs(float(b) - float(a)) >= 2.0:
            changes.append(f"{label}: {float(a):.1f}%→{float(b):.1f}%")
    for key, label in (
        ("server_cpu_share_2026_pct", "서버 CPU ABF 수요비중 2026E"),
        ("server_cpu_share_2027_pct", "서버 CPU ABF 수요비중 2027E"),
        ("server_cpu_share_2028_pct", "서버 CPU ABF 수요비중 2028E"),
    ):
        a, b = old.get(key), new.get(key)
        if b is None:
            continue
        if a is None:
            changes.append(f"{label}: {float(b):.1f}% 신규 확인")
        elif abs(float(b) - float(a)) >= 3.0:
            changes.append(f"{label}: {float(a):.1f}%→{float(b):.1f}%")
    return changes

def _event(item: dict) -> dict | None:
    if not _is_abf_item(item):
        return None
    text = _clean(f"{item.get('title','')} {item.get('description','')}")
    low = text.lower()
    rank = _source_rank(item)
    if rank < 2:
        return None
    kinds = []
    if any(k in low for k in ("capacity", "expand", "ramp", "new plant", "new fab", "증설", "생산능력", "產能", "产能")):
        kinds.append("capacity")
    if any(k in low for k in ("price increase", "price hike", "pricing", "asp", "가격 인상", "漲價", "涨价")):
        kinds.append("pricing")
    if any(k in low for k in ("qualification", "qualified", "yield", "warpage", "수율", "휨", "認證", "认证")):
        kinds.append("qualification")
    if any(k in low for k in ("shortage", "deficit", "undersupply", "supply gap", "공급부족", "수급", "短缺")):
        kinds.append("supply-demand")
    if not kinds:
        return None
    suppliers = _suppliers(text)
    # BofA model revisions are handled by the typed state, not generic events.
    if _extract_bofa(item):
        return None
    key = "|".join(sorted(set(kinds))) + "|" + ",".join(sorted(suppliers or ["industry"]))
    return {
        **item,
        "event_key": key,
        "event_types": sorted(set(kinds)),
        "suppliers": suppliers,
        "source_rank": rank,
    }

def collect(cutoff: dt.datetime) -> tuple[list[dict], list[str]]:
    items, errors, seen = [], [], set()
    for lang, query in QUERIES:
        try:
            root = ET.fromstring(_fetch(_rss_url(lang, query)))
        except Exception as exc:
            errors.append(f"{query[:44]}: {type(exc).__name__}: {exc}")
            continue
        for node in root.findall(".//item")[:30]:
            title = _clean(node.findtext("title"))
            desc = _clean(node.findtext("description"))
            source = _clean(node.findtext("source"))
            link = _decode(_clean(node.findtext("link")))
            pub = _pub_kst(_clean(node.findtext("pubDate")))
            try:
                pubdt = dt.datetime.fromisoformat(pub) if pub else None
            except Exception:
                pubdt = None
            if pubdt and pubdt < cutoff:
                continue
            fp = _fingerprint(title, source)
            if fp in seen:
                continue
            seen.add(fp)
            item = {
                "title": title, "description": desc, "source": source, "link": link,
                "published_kst": pub, "fingerprint": fp, "query": query,
            }
            if _is_abf_item(item):
                items.append(item)
    return items, errors

def _load() -> dict:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))

def write_outputs(items: list[dict], errors: list[str]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    state = _load()
    now = dt.datetime.now(KST)
    baseline = dict(state.get("bofa_current") or CURRENT_BofA)
    seen = set(state.get("seen_fingerprints") or [])
    delivered = set(state.get("delivered_event_keys") or [])

    changes = []
    bofa_source = ""
    historical_reposts = 0
    for item in sorted(items, key=lambda x: x.get("published_kst") or ""):
        obs = _extract_bofa(item)
        if not obs:
            continue
        if obs.get("historical_prior_repost") and not any(k.startswith("shortage_") and not k.startswith("prior_") for k in obs):
            historical_reposts += 1
            continue
        merged = dict(baseline)
        for k, v in obs.items():
            if v not in (None, ""):
                merged[k] = v
        cur = _material_changes(baseline, merged)
        if cur:
            changes.extend(cur)
            baseline = merged
            bofa_source = obs.get("source_url") or bofa_source

    new_events = []
    for item in items:
        ev = _event(item)
        if not ev:
            continue
        if ev["fingerprint"] in seen or ev["event_key"] in delivered:
            continue
        new_events.append(ev)

    for item in items:
        seen.add(item["fingerprint"])

    bootstrap_pending = bool(state.get("bootstrap_pending"))
    if bootstrap_pending:
        changes.insert(
            0,
            "BofA 기준선 교정: 사용자 캡처의 2026/27/28 공급부족 4%/10%/16%는 과거 전망, "
            "2026-08-19 최신 공개 리비전은 7%/14%/19%"
        )

    new_events = new_events[:4]
    pending_delivered = set(delivered)
    pending_delivered.update(x["event_key"] for x in new_events)
    pending = {
        "initialized": True,
        "track_version": TRACK_VERSION,
        "bootstrap_pending": False if bootstrap_pending else bool(state.get("bootstrap_pending", False)),
        "bofa_prior": PRIOR_BofA,
        "bofa_current": baseline,
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "last_scan_count": len(items),
        "last_material_change_count": len(changes),
        "last_new_event_count": len(new_events),
        "historical_prior_reposts_suppressed": historical_reposts,
        "seen_fingerprints": sorted(seen)[-1200:],
        "delivered_event_keys": sorted(pending_delivered)[-500:],
    }
    for k in ("last_successful_delivery_kst", "telegram_message_ids", "telegram_message_id", "bot_username", "delivery_receipt"):
        if state.get(k) is not None:
            pending[k] = state[k]
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    status = [
        "# ABF·FC-BGA 패키지기판 수급 감시",
        "",
        f"- 조회시각(KST): {now.isoformat(timespec='seconds')}",
        f"- 후보: {len(items)}건",
        f"- BofA 숫자 변화: {len(changes)}건",
        f"- 구조 이벤트 신규: {len(new_events)}건",
        f"- 구형 4/10/16 재게시 억제: {historical_reposts}건",
        f"- 원천 오류: {len(errors)}건",
        "- 최신 기준선: BofA 2026/27/28 ABF 공급부족 7%/14%/19%",
        "- 과거 사용자 캡처: 4%/10%/16% (현재 기준으로 재사용 금지)",
    ]
    STATUS_PATH.write_text("\n".join(status) + "\n", encoding="utf-8")

    ALERT_PATH.unlink(missing_ok=True)
    if not changes and not new_events:
        return

    lines = [
        "<b>[ABF·FC-BGA 패키지기판 수급 변화]</b>",
        f"조회 {now.strftime('%Y-%m-%d %H:%M')} KST",
        "",
    ]
    if changes:
        lines.append("• <b>BofA 수급 모델 변화</b>")
        for c in dict.fromkeys(changes):
            lines.append("  " + html.escape(c))
        lines.append(
            "  최신 기준: <b>2026E 7% · 2027E 14% · 2028E 19% 공급부족</b> "
            "(과거 4% · 10% · 16%에서 확대)"
        )
        lines.append(
            "  수요 원인: 서버 CPU의 ABF 수요비중이 "
            "<b>13%/14%/14%→17%/21%/21%</b>로 상향 — AI칩 대형화로 기판은 개수보다 면적·층수·고사양 비중이 중요"
        )
        lines.append(
            "  공급: BofA 추정 2026/27/28 공급증가율 <b>12%/22%/19%</b>에도 수요 상향이 더 커 공급부족 확대"
        )
        lines.append(
            "  핵심 공급사: Unimicron · Nan Ya PCB · Kinsus · Ibiden · Samsung Electro-Mechanics · "
            "Daeduck Electronics · AT&S · Shinko Electric"
        )
        lines.append(
            "  병목: 공장 증설 ≠ 즉시 양산. 고다층 ABF의 고객인증·수율·휨·저열팽창 소재·Ajinomoto ABF 필름이 실제 유효 생산능력을 결정"
        )
        lines.append(
            "  실패 경로: 2027~2028 대규모 증설이 인증까지 조기 완료되거나 서버 CPU/AI 가속기 면적 증가가 둔화되면 공급부족률·가격결정력 약화"
        )
        lines.append(
            "  다음 확인: BofA 공급부족률 재리비전 · 서버 CPU 수요비중 · 기판 ASP · "
            "Unimicron/NYPCB/Kinsus/Ibiden/SEMCO/Daeduck 유효 생산능력·가동률·고객인증"
        )
        lines.append(
            '  <a href="https://www.xxquant.com/en/institution/institutional-research/e9049647f76459043c0fe4af2e72ff82">BofA 최신 리비전 교차확인</a>'
        )
    for ev in new_events:
        names = ", ".join(ev["suppliers"]) if ev["suppliers"] else "산업 전체"
        lines += [
            "",
            "• <b>구조 이벤트</b>",
            "  유형: " + html.escape(", ".join(ev["event_types"])),
            "  기업: " + html.escape(names),
            "  제목: " + html.escape(_clean(ev["title"])),
        ]
        if ev.get("link"):
            lines.append('  <a href="' + html.escape(str(ev["link"]), quote=True) + '">근거 원문</a>')
    lines.append("")
    lines.append("※ 같은 4%/10%/16% 구형 차트 재게시만으로는 재알림하지 않습니다.")
    ALERT_PATH.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

def main() -> None:
    items, errors = collect(dt.datetime.now(KST) - dt.timedelta(days=14))
    write_outputs(items, errors)
    print(f"abf_candidates={len(items)} errors={len(errors)} alert_exists={ALERT_PATH.exists()}")

if __name__ == "__main__":
    main()
