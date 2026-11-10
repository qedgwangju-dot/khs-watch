#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from email.utils import parsedate_to_datetime

import requests
from bs4 import BeautifulSoup

OUT = Path("out")
STATE = Path("data/us_data_center_generation_buildout_state.json")
ALERT = OUT / "us_data_center_generation_buildout_alert.txt"
PENDING = OUT / "us_data_center_generation_buildout_pending_state.json"
STATUS = OUT / "us_data_center_generation_buildout_status.md"

MOODYS_BLOOMBERG = "https://news.bloombergtax.com/financial-accounting/us-ai-boom-needs-110-billion-of-new-power-plants-moodys-says"
IEA_AI = "https://www.iea.org/reports/energy-and-ai/energy-demand-from-ai"
EIA_HIGH_DEMAND = "https://www.eia.gov/todayinenergy/detail.php?id=67344"
GEV_Q2_2026 = "https://www.gevernova.com/news/articles/ge-vernova-releases-second-quarter-2026-financial-results"
GEV_Q3_2026 = "https://www.gevernova.com/news/articles/ge-vernova-releases-third-quarter-2026-financial-results-announces-agreement-acquire"

# Verified Sep. 14, 2026 Moody's/Bloomberg baseline. These are a planning
# benchmark, not confirmed construction or awarded projects.
BASELINE = {
    "need_generation_gw": 45.0,
    "gas_min_gw": 30.0,
    "capex_usd_b": 110.0,
    "annual_cost_low_usd_b": 25.0,
    "annual_cost_high_usd_b": 30.0,
    "dc_direct_cost_usd_b": 15.0,
    "behind_meter_share_pct": 30.0,
    "iea_2030_twh": 426.0,
    "incremental_gas_bcf_day": 4.0,
}

VERIFIED_GEV = {
    # 2026-10-28 Q3 issuer release (prior Q2: 116 and 125 GW).
    # Do NOT count combined firm backlog and slot reservations as firm orders.
    "gas_contract_slot_gw": 122.0,
    "year_end_target_gw": 130.0,
    "output_2026_gw": 20.0,
    "output_2028_gw": 24.0,
    "output_2030_gw": 30.0,
    "dc_orders_ytd_usd_b": 5.0,
}

TRUSTED_DOMAINS = (
    "gevernova.com", "doosanenerbility.com", "nrg.com", "investors.nrg.com",
    "eia.gov", "iea.org", "moodys.com", "reuters.com", "utilitydive.com",
    "datacenterdynamics.com", "energy-storage.news", "publicpower.org",
    "bloombergtax.com", "advisorperspectives.com", "morganstanley.com", "goldmansachs.com",
    "hamiltonlane.com",
)

NEWS_QUERIES = (
    'data center power plant gas turbine BESS 500 MW contract construction United States',
    'data center behind-the-meter power 500 MW gas BESS NRG GE Vernova Crusoe',
    'AI data center power generation project commercial operation 500 MW United States',
    'gas turbine data center order supply 500 MW United States',
    'Moody data center 45 GW 110 billion power plants 2030',
    'Morgan Stanley data center onsite power distributed generation fuel cell BESS forecast United States',
    'Morgan Stanley data center ESS 279 GWh 169 GWh forecast',
    'Goldman Sachs US data center capacity 2027 GW forecast community opposition',
    '"Anthropic" "OnePWR" Caterpillar generators delivered installation permit',
)

HEADERS = {"User-Agent": "khs-watch/1.0 (+https://github.com/qedgwangju-dot/khs-watch)"}
FORMAT_VERSION = 1


def fetch(url: str, timeout: int = 30):
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def sig(*parts: str) -> str:
    return hashlib.sha256("\n".join(str(x) for x in parts).encode("utf-8")).hexdigest()[:20]


def h(text) -> str:
    return html.escape(str(text), quote=True)


def a(label: str, url: str) -> str:
    return f'<a href="{h(url)}">{h(label)}</a>'


def _plain(line: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", line or "")).strip()


def compact_generation_message(msg: list[str]) -> list[str]:
    headings = {
        "<b>🔥 발전설비 실행판</b>",
        "<b>🏭 가스터빈 공급 병목</b>",
        "<b>⚡ 미국 전력수요·전력기기 병목</b>",
        "<b>🌐 전력망 투자·접속 병목</b>",
        "<b>💻 반복 장비투자·한국 전력기기 실수주</b>",
        "<b>⚡ Morgan Stanley·Goldman Sachs 전력 병목 기준선</b>",
        "<b>🔄 공급능력 숫자 변경</b>",
        "<b>🔄 전력수요·병목 기준 변경</b>",
        "<b>🔄 PwC 자본투자 전망 변경</b>",
        "<b>🆕 핵심 실행 변화</b>",
        "<b>👀 별도 감시 범위</b>",
        "<b>📊 판단 기준</b>",
        "<b>💱 환율</b>",
        "<b>🔗 기준 원문</b>",
    }

    def sec(heading: str) -> list[str]:
        try:
            s = msg.index(heading) + 1
        except ValueError:
            return []
        e = len(msg)
        for i in range(s, len(msg)):
            if msg[i] in headings:
                e = i
                break
        return [x for x in msg[s:e] if str(x).strip()]

    base = sec("<b>🔥 발전설비 실행판</b>")
    turbine = sec("<b>🏭 가스터빈 공급 병목</b>")
    grid = sec("<b>🌐 전력망 투자·접속 병목</b>")
    orders = sec("<b>💻 반복 장비투자·한국 전력기기 실수주</b>")
    research = sec("<b>⚡ Morgan Stanley·Goldman Sachs 전력 병목 기준선</b>")
    new = sec("<b>🆕 핵심 실행 변화</b>")
    fx = sec("<b>💱 환율</b>")
    change_rows = []
    for heading in (
        "<b>🔄 공급능력 숫자 변경</b>",
        "<b>🔄 전력수요·병목 기준 변경</b>",
        "<b>🔄 PwC 자본투자 전망 변경</b>",
    ):
        change_rows.extend(sec(heading))

    out = [msg[0], "", "<b>🧭 핵심</b>"]
    if new:
        first = next((x for x in new if "<a href=" in x), new[0])
        out.append(f"• <b>변화</b> │ {_plain(first)}")
    elif change_rows:
        out.append(f"• <b>변화</b> │ {_plain(change_rows[0]).lstrip('• ')}")
    else:
        out.append("• <b>변화</b> │ 발전설비·공급망 실행 기준 업데이트")
    if "가독성·정확도 업그레이드" in _plain(msg[0]):
        out.append("• <b>정정</b> │ 비나텍 기사에 붙었던 ‘1MW’는 프로젝트 용량이 아니라 기사 내 단위 오인 추출이라 제거 · 확정 수주액 <b>412.15억원</b>만 유지")
    out.append("• <b>판정</b> │ 필요 GW → 장비발주·터빈슬롯 → 착공 → 연료·송전 연결 → 상업운전")

    current = []
    for prefix in ("• 2030 필요 신규발전", "• 가스발전", "• 총 필요투자"):
        row = next((x for x in base if _plain(x).startswith(prefix)), None)
        if row:
            current.append(row)
    if current:
        out += ["", "<b>🔥 현재 숫자</b>"] + current

    bottleneck = []
    for prefix in ("• GE Vernova 계약·슬롯", "• 데이터센터 주문"):
        row = next((x for x in turbine if _plain(x).startswith(prefix)), None)
        if row:
            bottleneck.append(row)
    for prefix in ("• 현재 연간 전력망 투자", "• 시간표 불일치"):
        row = next((x for x in grid if _plain(x).startswith(prefix)), None)
        if row:
            bottleneck.append(row)
    if bottleneck:
        out += ["", "<b>🏭 병목</b>"] + bottleneck[:4]

    confirmed = [
        x for x in orders
        if any(name in _plain(x) for name in ("효성중공업", "HD현대일렉트릭", "LS ELECTRIC", "비나텍"))
    ]
    if confirmed:
        out += ["", "<b>💰 국내 확정 수주·매출 연결</b>"] + confirmed[:4]

    research_keep = []
    for prefix in (
        "• Goldman Sachs 2026~2027 미국 용량",
        "• Morgan Stanley 공개 기준",
        "• Morgan Stanley 장비·계약 시간표",
        "• Morgan Stanley ESS",
    ):
        row = next((x for x in research if _plain(x).startswith(prefix)), None)
        if row:
            research_keep.append(row)
    if research_keep:
        out += ["", "<b>📡 최신 수요·분산전원</b>"] + research_keep[:4]

    if change_rows:
        out += ["", "<b>🔄 숫자 변경</b>"] + change_rows[:6]

    if new:
        # Keep every chosen event row emitted by the watcher, but drop generic
        # bookkeeping lines such as "remaining N stored".
        visible_new = [x for x in new if "나머지" not in _plain(x)]
        out += ["", "<b>🆕 실행 변화</b>"] + visible_new[:10]

    out += [
        "",
        "<b>📊 투자 의미</b>",
        "• <b>수혜</b> │ 발표 MW가 아니라 실제 장비발주·착공·상업운전으로 내려오는 기업만 실적 연결",
        "• <b>실패모드</b> │ 터빈·변압기·송전·연료 연결이 늦으면 데이터센터 전원 인가와 매출 인식이 함께 지연",
    ]

    fx_row = next((x for x in fx if "1달러" in _plain(x)), None)
    if fx_row:
        out += ["", "<b>💱 환율</b>", fx_row]

    visible = _plain("\n".join(out))
    if len(visible) > 3200:
        raise RuntimeError(f"compact generation alert too long: {len(visible)} chars")
    return out


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def domain_of(url: str) -> str:
    return urllib.parse.urlparse(url or "").netloc.lower().replace("www.", "")


def trusted(domain: str) -> bool:
    return any(domain == d or domain.endswith("." + d) for d in TRUSTED_DOMAINS)


def has_korean(text: str) -> bool:
    return bool(re.search(r"[가-힣]", text or ""))


def fx_rate(old=None):
    sources = [
        ("https://open.er-api.com/v6/latest/USD", lambda d: d["rates"]["KRW"], "ER-API"),
        ("https://api.frankfurter.app/latest?from=USD&to=KRW", lambda d: d["rates"]["KRW"], "Frankfurter"),
    ]
    for url, parser, name in sources:
        try:
            v = float(parser(fetch(url, 15).json()))
            if 500 < v < 3000:
                return v, name
        except Exception:
            pass
    if old:
        return float(old), "직전 저장값"
    return None, "조회 실패"


def krw_from_usd_b(usd_b: float, fx: float) -> str:
    eok = round(usd_b * 1e9 * fx / 1e8)
    jo, rem = divmod(eok, 10000)
    if jo and rem:
        return f"약 {jo:,}조 {rem:,}억원"
    if jo:
        return f"약 {jo:,}조원"
    return f"약 {rem:,}억원"


def translate_google(text: str) -> str | None:
    if not text or has_korean(text):
        return text
    try:
        url = "https://translate.googleapis.com/translate_a/single?" + urllib.parse.urlencode({
            "client": "gtx", "sl": "auto", "tl": "ko", "dt": "t", "q": text,
        })
        data = fetch(url, 15).json()
        out = "".join(seg[0] for seg in (data[0] or []) if isinstance(seg, list) and seg and isinstance(seg[0], str))
        out = normalize(out)
        return out if has_korean(out) else None
    except Exception:
        return None


def translate_title(text: str, stage: str, source: str) -> str:
    text = normalize(html.unescape(text))
    if has_korean(text):
        return text
    out = translate_google(text)
    if out:
        for old, new in {
            "데이터 센터": "데이터센터", "가스 터빈": "가스터빈", "상업 운영": "상업운전",
            "그리드": "전력망", "배터리 저장": "배터리저장장치",
        }.items():
            out = out.replace(old, new)
        return out
    return f"{source} · 데이터센터 발전설비 {stage} 관련 신규 자료"


def source_label(source: str, url: str) -> str:
    s = f"{source} {domain_of(url)}".lower()
    for key, label in (
        ("ge vernova", "GE Vernova"), ("gevernova", "GE Vernova"),
        ("doosan", "두산에너빌리티"), ("nrg", "NRG"), ("eia", "EIA"),
        ("iea", "IEA"), ("mood", "Moody's"), ("reuters", "Reuters"),
        ("utilitydive", "Utility Dive"), ("datacenterdynamics", "Data Center Dynamics"),
        ("energy-storage", "Energy-Storage.News"), ("bloomberg", "Bloomberg"),
        ("advisorperspectives", "Bloomberg"), ("morganstanley", "Morgan Stanley"),
        ("goldmansachs", "Goldman Sachs"), ("hamiltonlane", "Hamilton Lane"),
    ):
        if key in s:
            return label
    return normalize(source)[:40] or domain_of(url)[:40]


def parse_gev() -> dict:
    """Latest issuer Q3 gas-order/slot totals; never revert to Q2 on source outage."""
    metrics = dict(VERIFIED_GEV)
    metrics["source_release"] = "2026-10-28 Q3 official"
    metrics["source_live_verified"] = False
    try:
        body = normalize(BeautifulSoup(fetch(GEV_Q3_2026, 22).text, "html.parser").get_text(" "))
        # A generic page/redirect is not the earnings release. Require both
        # Q3-specific gas-slot figures, not just '2026' in a footer.
        if not (
            re.search(r"third quarter 2026", body, re.I)
            and re.search(r"(?:from\s+116\s+to|grew\s+from\s+116\s+to)\s*122\s*GW", body, re.I)
            and re.search(r"at least\s+130\s*GW\s+by\s+year.end\s+2026", body, re.I)
        ):
            return metrics
        metrics["source_live_verified"] = True
        # The Q3 source explicitly documents these revised outlooks; 2028
        # and 2030 production targets remain as already announced in Q2.
        metrics["gas_contract_slot_gw"] = 122.0
        metrics["year_end_target_gw"] = 130.0
        return metrics
    except Exception:
        return metrics

def stage_of(text: str) -> str:
    low = text.lower()
    if any(k in low for k in ("forecast", "outlook", "projection", "estimate", "전망", "추정")) and any(k in low for k in ("data center", "data centre", "데이터센터", "power", "capacity", "gw", "gwh")):
        return "전망 변경"
    if any(k in low for k in ("cancel", "withdraw", "delay", "postpone", "suspend", "canceled", "cancelled")):
        return "취소·지연"
    if any(k in low for k in ("commercial operation", "commissioned", "online", "operational", "cod")):
        return "상업운전"
    # Merely mentioning construction/engineering capabilities is not a groundbreaking.
    # Require a completed/started action, not a future plan or bundled service.
    if re.search(r"\b(?:construction (?:has )?(?:started|begun|commenced)|"
                 r"construction (?:starts|begins)|broke ground|breaks ground|"
                 r"groundbreaking|under construction|build began)\b", low):
        if not re.search(r"\b(?:plans? to|will|expects? to|aims? to|"
                         r"may|could|scheduled to)\b.{0,50}\b(?:construction|ground)\b", low):
            return "착공"
    if any(k in low for k in ("financial close", "financing", "project finance", "funding secured")):
        return "금융종결"
    if any(k in low for k in ("slot", "reservation", "turbine reservation")):
        return "공급슬롯"
    if any(k in low for k in ("contract", "order", "selected", "supply agreement", "award", "purchase agreement")):
        return "계약·수주"
    if any(k in low for k in ("interconnection", "studied load", "approved", "permit")):
        return "접속·허가"
    return "실행 변화"


def extract_scale_mw(text: str) -> float:
    """Only power capacity (MW/GW); never classify energy (MWh/GWh) as MW/GW."""
    low = text.lower().replace(",", "")
    vals = []
    vals += [float(x) for x in re.findall(r"(?<![\w])([0-9]+(?:\.[0-9]+)?)\s*mw\b", low)]
    vals += [float(x) * 1000 for x in re.findall(r"(?<![\w])([0-9]+(?:\.[0-9]+)?)\s*gw\b", low)]
    vals += [float(x) for x in re.findall(r"(?<![\w])([0-9]+(?:\.[0-9]+)?)\s*megawatts?\b", low)]
    vals += [float(x) * 1000 for x in re.findall(r"(?<![\w])([0-9]+(?:\.[0-9]+)?)\s*gigawatts?\b", low)]
    return max(vals + [0.0])


def _test_capacity_unit_guard() -> None:
    # Regression: Morgan Stanley 279 GWh ESS is not a 279 GW power project.
    cases = (
        ("Morgan Stanley 2030 US ESS 279GWh DC 169GWh", 0.0),
        ("2027 data center battery 31 GWh", 0.0),
        ("2026 energy storage 100 MWh, 600 kWh", 0.0),
        ("500 MW natural-gas power project", 500.0),
        ("AI data center 2.5 GW capacity", 2500.0),
        ("1,200MW plant", 1200.0),
        ("Anthropic bought commitments for 1.7 gigawatts of generators", 1700.0),
        ("Anthropic agreed for 1.7 GW of gas-fired power", 1700.0),
        ("2,500 megawatts of generating capacity", 2500.0),
    )
    for value, expected in cases:
        got = extract_scale_mw(value)
        if got != expected:
            raise RuntimeError(f"Capacity vs storage-energy unit regression: {value}: {got} != {expected}")


_test_capacity_unit_guard()


def is_meaningful(text: str, source: str) -> bool:
    low = text.lower()
    scale = extract_scale_mw(text)
    if "mood" in low and any(k in low for k in ("45 gw", "110 billion", "$110")):
        return True
    if "ge vernova" in low and any(k in low for k in ("gas turbine", "slot", "data center", "data centre")):
        return True
    research_house = any(k in low for k in ("morgan stanley", "goldman sachs", "모건스탠리", "골드만삭스"))
    research_revision = any(k in low for k in ("forecast", "outlook", "projection", "estimate", "전망", "추정", "revised", "raised", "lowered"))
    if research_house and research_revision and any(k in low for k in ("data center", "data centre", "데이터센터")) and scale >= 500:
        return True
    if not any(k in low for k in ("data center", "data centre", "hyperscaler", "ai campus", "ai factory")):
        return False
    execution = any(k in low for k in (
        "contract", "order", "selected", "approved", "construction", "commercial operation",
        "commissioned", "interconnection", "financial close", "financing", "slot", "reservation",
        "cancel", "delay", "suspend", "studied load", "permit",
    ))
    return execution and scale >= 500


def collect_news() -> list[dict]:
    out = []
    for query in NEWS_QUERIES:
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
        try:
            root = ET.fromstring(fetch(url, 25).content)
        except Exception:
            continue
        for item in root.findall("./channel/item")[:25]:
            # A resurfaced historical article is not a newly announced contract.
            try:
                timestamp = parsedate_to_datetime(item.findtext("pubDate") or "")
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=dt.timezone.utc)
                age_hours = (dt.datetime.now(dt.timezone.utc) - timestamp).total_seconds() / 3600
                if not (-2 <= age_hours <= 14 * 24):
                    continue
            except (TypeError, ValueError, OverflowError):
                continue
            title = normalize(item.findtext("title") or "")
            link = normalize(item.findtext("link") or "")
            source_el = item.find("source")
            source = normalize(source_el.text if source_el is not None else "")
            source_url = normalize(source_el.attrib.get("url", "") if source_el is not None else "")
            domain = domain_of(source_url)
            if not trusted(domain):
                continue
            blob = f"{title} {source}"
            # The Anthropic/OnePWR original report has its own source-grade and
            # semantic fingerprint below; avoid a URL-specific duplicate.
            if ("anthropic" in blob.lower() and "onepwr" in blob.lower()
                    and re.search(r"\b(?:1[.,]7|3[.,]4)\b", blob)):
                continue
            if not is_meaningful(blob, source):
                continue
            stage = stage_of(blob)
            out.append({
                "id": sig(title, link), "title": title, "url": link,
                "source": source_label(source, source_url), "stage": stage,
                "scale_mw": extract_scale_mw(blob),
            })
    return list({x["id"]: x for x in out}.values())


def detect_gev_changes(old: dict, now: dict) -> list[str]:
    changes = []
    oldm = old.get("gev_metrics") or {}
    labels = {
        "gas_contract_slot_gw": "GE Vernova 가스터빈 계약·슬롯(글로벌)",
        "year_end_target_gw": "GE Vernova 2026년말 계약 목표(글로벌)",
        "output_2026_gw": "GE Vernova 연간 생산능력 2026",
        "output_2028_gw": "GE Vernova 연간 생산능력 2028",
        "output_2030_gw": "GE Vernova 연간 생산능력 2030",
        "dc_orders_ytd_usd_b": "GE Vernova 데이터센터 주문 YTD",
    }
    for key, label in labels.items():
        ov, nv = oldm.get(key), now.get(key)
        if ov is not None and nv is not None and float(ov) != float(nv):
            unit = "십억달러" if key == "dc_orders_ytd_usd_b" else "GW"
            changes.append(f"{label}: {float(ov):g}{unit} → {float(nv):g}{unit}")
    return changes


OUT.mkdir(exist_ok=True)
for p in (ALERT, PENDING, STATUS):
    if p.exists():
        p.unlink()

old = load_json(STATE)
fx, fx_source = fx_rate(old.get("last_fx_krw_per_usd"))
if fx is None:
    raise SystemExit("KRW exchange rate unavailable; refusing to send monetary alerts without KRW conversion")
fx_checked = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
gev = parse_gev()
items = collect_news()
old_ids = set(old.get("seen_ids", []))
new_items = [x for x in items if x["id"] not in old_ids]
gev_changes = detect_gev_changes(old, gev)
baseline_run = not old.get("initialized")
format_upgrade = int(old.get("format_version", 0) or 0) < FORMAT_VERSION
# Never acknowledge candidates that were not included in the Telegram report.
# Initial baseline is the one exception: historical articles are not replayed.
chosen_news = sorted(
    new_items,
    key=lambda x: (0 if x['stage'] in ('상업운전', '착공', '계약·수주') else 1,
                   -x.get('scale_mw', 0))
)[:5]
should_alert = baseline_run or format_upgrade or bool(new_items) or bool(gev_changes)
acknowledged_news = items if baseline_run else chosen_news
seen = list(dict.fromkeys(
    list(old.get("seen_ids", [])) + [x["id"] for x in acknowledged_news]
))[-1600:]
pending = {
    **old,  # Preserve existing event keys, source checks, and historical baselines.
    "initialized": True,
    "format_version": max(FORMAT_VERSION, int(old.get("format_version") or 0)),
    "baseline": BASELINE,
    "gev_metrics": gev,
    "seen_ids": seen,
    "last_fx_krw_per_usd": fx,
    "fx_source": fx_source,
    "fx_checked_utc": fx_checked,
    "updated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
}
PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

if should_alert:
    title = ("✅ 미국 데이터센터 발전설비 감시 분리 완료" if baseline_run else ("✅ 미국 데이터센터 발전설비 알림 가독성·정확도 업그레이드" if format_upgrade and not new_items and not gev_changes else "🔥 미국 데이터센터 발전설비 실행 변화"))
    b = BASELINE
    msg = [f"<b>{h(title)}</b>", "", "<b>🔥 발전설비 실행판</b>"]
    msg.append(f"• <b>2030 필요 신규발전</b> │ <b>{b['need_generation_gw']:g}GW</b>")
    msg.append(f"• <b>가스발전</b> │ <b>{b['gas_min_gw']:g}GW+</b> │ 전체 필요량의 최소 약 {b['gas_min_gw']/b['need_generation_gw']*100:.1f}%")
    msg.append(f"• <b>자체발전</b> │ 전체 증설의 약 <b>{b['behind_meter_share_pct']:g}%</b> │ 단순 용량 환산 약 {b['need_generation_gw']*b['behind_meter_share_pct']/100:g}GW")
    msg.append(f"• <b>총 필요투자</b> │ 1,100억달러 = <b>{krw_from_usd_b(b['capex_usd_b'], fx)}</b>")
    msg.append(
        f"• <b>연간 추가 전력비</b> │ 250억~300억달러 = <b>{krw_from_usd_b(b['annual_cost_low_usd_b'], fx)}~{krw_from_usd_b(b['annual_cost_high_usd_b'], fx)}</b>"
    )
    msg.append(f"• <b>데이터센터 직접부담</b> │ 최대 150억달러 = <b>{krw_from_usd_b(b['dc_direct_cost_usd_b'], fx)}</b>")

    msg += ["", "<b>🏭 가스터빈 공급 병목</b>"]
    msg.append(f"• <b>GE Vernova 계약·슬롯</b> │ 글로벌 <b>{gev['gas_contract_slot_gw']:g}GW</b> │ 2026년말 목표 {gev['year_end_target_gw']:g}GW+")
    msg.append(f"• <b>연간 생산능력</b> │ 2026 {gev['output_2026_gw']:g}GW → 2028 {gev['output_2028_gw']:g}GW → 2030 {gev['output_2030_gw']:g}GW")
    msg.append(f"• <b>데이터센터 주문</b> │ GE Vernova YTD {gev['dc_orders_ytd_usd_b']:g}0억달러+ = {krw_from_usd_b(gev['dc_orders_ytd_usd_b'], fx)}+")
    msg.append("• 주의: GE Vernova 수치는 <b>글로벌 공급능력 선행지표</b>이며 미국 데이터센터 45GW와 직접 동일 비교하지 않습니다.")

    if gev_changes:
        msg += ["", "<b>🔄 공급능력 숫자 변경</b>"]
        for ch in gev_changes[:5]:
            msg.append(f"• {h(ch)}")

    if new_items and not baseline_run:
        msg += ["", "<b>🆕 핵심 실행 변화</b>"]
        chosen = chosen_news
        for idx, x in enumerate(chosen, 1):
            ko = translate_title(x['title'], x['stage'], x['source'])
            if len(ko) > 170:
                ko = ko[:167].rstrip() + "…"
            scale = f" · {x['scale_mw']:,.0f}MW" if x.get('scale_mw') else ""
            msg.append(f"{idx}. 🔗 {a(ko, x['url'])}")
            msg.append(f"   {h(x['stage'])} · {h(x['source'])}{h(scale)}")
        if len(new_items) > len(chosen):
            msg.append(f"• 나머지 {len(new_items)-len(chosen)}건은 미전송으로 유지하고 다음 조회에서 재검토합니다.")
    elif baseline_run:
        msg += ["", "<b>👀 별도 감시 범위</b>"]
        msg.append("• 500MW 이상 데이터센터 연계 가스발전·BESS의 계약 → 금융종결 → 착공 → 상업운전")
        msg.append("• 가스터빈 계약·슬롯과 연간 생산능력 변화")
        msg.append("• 데이터센터 부지 내·인접 자체발전과 장기 전력계약")
        msg.append("• 1,100억달러 투자 프레임과 소비자 비용부담 변화")

    msg += ["", "<b>📊 판단 기준</b>"]
    msg.append("• <b>실행순서</b> │ 필요 GW → 계약·터빈슬롯 → 금융종결 → 착공 → 연료·송전 연결 → 상업운전")
    msg.append("• <b>매출 연결</b> │ 발표 MW가 아니라 장비 발주·착공·상업운전 단계로 내려올 때 실적 전환으로 봅니다.")
    msg.append("• <b>분리 이유</b> │ 계통접속 감시는 ‘전기를 받을 수 있나’, 발전설비 감시는 ‘그 전기를 실제 만들 수 있나’를 추적합니다.")

    msg += ["", "<b>💱 환율</b>"]
    msg.append(f"• <b>1달러 = {fx:,.2f}원</b> │ {h(fx_source)} │ {h(fx_checked)} UTC")
    msg.append("• 외화 금액은 항상 같은 줄에 원화 환산을 붙입니다.")

    msg += ["", "<b>🔗 기준 원문</b>"]
    msg.append(f"• {a('Moody’s 45GW·1,100억달러 분석 보도', MOODYS_BLOOMBERG)}")
    msg.append(f"• {a('IEA 미국 데이터센터 전력수요', IEA_AI)}")
    msg.append(f"• {a('EIA 고수요 가스발전 시나리오', EIA_HIGH_DEMAND)}")
    msg.append(f"• {a('GE Vernova 가스터빈 공급능력', GEV_Q2_2026)}")
    msg.append(f"• {a('GE Vernova 2026년 3분기 최신 계약·슬롯', GEV_Q3_2026)}")
    msg = compact_generation_message(msg)
    ALERT.write_text("\n".join(msg).strip() + "\n", encoding="utf-8")

STATUS.write_text(
    "# 미국 데이터센터 발전설비 실행 감시\n\n"
    f"- 2030 필요 신규발전 기준: **{BASELINE['need_generation_gw']} GW**\n"
    f"- 가스발전 기준: **{BASELINE['gas_min_gw']} GW+**\n"
    f"- 총 필요투자: **${BASELINE['capex_usd_b']}B**\n"
    f"- GE Vernova 계약·슬롯: **{gev['gas_contract_slot_gw']} GW**\n"
    f"- 신규 의미자료: **{len(new_items)}건**\n"
    f"- 공급능력 숫자 변경: **{len(gev_changes)}건**\n"
    f"- 알림: **{'예' if should_alert else '아니오'}**\n",
    encoding="utf-8",
)
print(
    f"generation_buildout baseline={BASELINE['need_generation_gw']}GW "
    f"gev_slots={gev['gas_contract_slot_gw']}GW new={len(new_items)} changes={len(gev_changes)} alert={should_alert}"
)


# VENTURE_GLOBAL_POWER_ISLAND_EXTENSION_V1
# Existing generation-buildout workflow, pending state, and Telegram route only.
# This block executes after the original watcher, before the already deployed
# nuclear-PPA runtime extension. It does not create independent workflows/files.
VG_RELEASE = "https://investors.ventureglobal.com/news/news-details/2026/Venture-Global-Secures-New-Agreements-to-Support-Expansion-of-Existing-Grid-Independent-Power-Network/default.aspx"
VG_SEC_8K = "https://www.sec.gov/Archives/edgar/data/2007855/000200785526000081/vg-20261009.htm"
VG_BAKER_RELEASE = "https://investors.bakerhughes.com/news/press-releases/news-details/2026/Baker-Hughes-and-Venture-Global-Expand-Strategic-Long-Term-Power-Generation-Partnership/default.aspx"
VG_BASELINE = {
    "framework_signed": "2026-10-09",
    "announcement_date": "2026-10-15",
    "power_island_max_units": 16,
    "power_island_unit_mw": 720,
    "power_island_max_mw": 11520,
    "existing_island_mode_mw": 4500,
    "ge_manufacturing_reservation_units": 8,
    "ge_manufacturing_reservation_denominator_remaining": 15,
    "ge_grid_equipment_max_packages": 21,
    "ge_grid_initial_reservation_packages": 5,
    "full_option_equipment_usd_b": 17.2,
    "potential_compute_gw": 10,
    "conditional_target_year": 2034,
    "first_power_island_po_target": "2026-12-31",
    "grid_first_po_target": "2026-Q4",
    "delivery_window": "2028~2034",
    "customer_signed": False,
    "first_power_island_po_placed": False,
    "facility_energized": False,
    "phase": "기본계약·일부 제조능력 예약",
    "scope": "가스터빈·증기터빈·E-house·전력변압기·가스절연 개폐장치·전기제어/통합서비스",
}
VG_OFFICIAL_DOMAINS = (
    "ventureglobal.com",
    "gevernova.com",
    "bakerhughes.com",
    "sec.gov",
)
VG_STAGE_LABELS = {
    "first-po": "첫 발전설비 구매주문 실제 발행",
    "additional-po": "추가 발전설비 실제 발주",
    "customer-signed": "데이터센터 장기 전력구매·사용권 계약 체결",
    "permit-approved": "가스발전·데이터센터 인허가 승인",
    "financial-close": "프로젝트 금융종결",
    "construction-start": "신규 발전설비 실제 착공",
    "delivery": "발전설비 납품·현장 인수",
    "energization": "발전설비 실제 전원 인가·상업운전",
    "risk-delay": "발주·인허가·전원 인가 일정 지연",
    "risk-cancel": "고객·발주·프로젝트 취소",
}


def vg_classify_official_headline(title: str):
    """Forward plans and headline reprints cannot be marked as actual orders."""
    t = normalize(html.unescape(title))
    if not re.search(r"venture global|ventureglobal|\bVGLNG\b", t, re.I):
        return None
    if not re.search(r"power islands?|power plants?|generation|gas[- ]fired|data cent(?:er|re)", t, re.I):
        return None
    if re.search(r"\bexpects?\b|\bplans?\b|\btargets?\b|\bmay\b|\bcould\b|"
                 r"\bpotential\b|\bup to\b|\bframework\b|\bwill\b|\bplanned\b|"
                 r"\bscheduled\b|\bforecast\b|\benvisag\w*|\banticipat\w*|"
                 r"\boutline\b|\bwants?\s+to\b|\bto place\b|"
                 r"\bto submit\b|\bset to\b|\bis poised to\b|\bproposes?\b|"
                 r"\bprepar(?:e|es|ing)\b", t, re.I):
        return None
    if re.search(r"cancel(?:led|ed|lation)?|terminate[sd]?|withdrawn", t, re.I):
        return "risk-cancel"
    if re.search(r"delay(?:ed)?|postpon(?:e|ed|ement)|suspend(?:ed)?", t, re.I):
        return "risk-delay"
    if re.search(r"first.{0,35}(?:purchase order|firm order)|"
                 r"placed.{0,35}first.{0,25}order|first.{0,25}purchase order.{0,25}placed", t, re.I):
        return "first-po"
    if re.search(r"(?:additional|another|second|third).{0,35}(?:purchase orders?|firm orders?)|"
                 r"(?:placed|awarded|issued).{0,35}(?:additional|new).{0,35}(?:orders?|purchase)", t, re.I):
        return "additional-po"
    if re.search(r"(?:data cent(?:er|re)|hyperscaler|AI compute).{0,65}"
                 r"(?:signed|secures?|executes?|finalizes?).{0,35}(?:power|electricity).{0,25}"
                 r"(?:contract|agreement|PPA)|"
                 r"(?:signed|executed|secured).{0,40}(?:data cent(?:er|re)|hyperscaler).{0,35}"
                 r"(?:power|electricity).{0,30}(?:agreement|contract)", t, re.I):
        return "customer-signed"
    if re.search(r"(?:permit|approval).{0,30}(?:issued|granted|approved)|"
                 r"(?:regulator|authority).{0,40}approves?", t, re.I):
        return "permit-approved"
    if re.search(r"(?:financial close|financing closed|project financing secured)", t, re.I):
        return "financial-close"
    if re.search(r"breaks ground|construction (?:starts|begins|started)", t, re.I):
        return "construction-start"
    if re.search(r"power island.{0,45}(?:delivered|installed|commissioned)|"
                 r"(?:first|new).{0,30}turbine.{0,25}(?:delivered|installed)", t, re.I):
        return "delivery"
    if re.search(r"power island.{0,45}(?:energized|in commercial operation|starts operation)|"
                 r"(?:commissioned|energized).{0,40}(?:power island|power plant)", t, re.I):
        return "energization"
    return None


def vg_parser_self_test():
    b = VG_BASELINE
    assert b["power_island_max_units"] * b["power_island_unit_mw"] == b["power_island_max_mw"] == 11520
    assert b["power_island_max_mw"] != 720
    assert b["ge_manufacturing_reservation_units"] < b["power_island_max_units"]
    assert b["ge_grid_equipment_max_packages"] != b["power_island_max_units"]
    assert not b["first_power_island_po_placed"] and not b["customer_signed"]
    cases = (
        ("Venture Global expects to place first power island purchase order by end 2026", None),
        ("Venture Global will issue first power island purchase order in December 2026", None),
        ("Venture Global and GE Vernova agree on up to 16 power islands of 720 MW", None),
        ("Venture Global submits first permit applications for gas power island", None),
        ("Venture Global announces 10 GW potential data center capacity by 2034", None),
        ("Venture Global placed first firm purchase order for 720 MW power island", "first-po"),
        ("Venture Global secured project financing closed for 720 MW gas-fired power plant", "financial-close"),
        ("Venture Global says data center power island energization delayed", "risk-delay"),
        ("Venture Global says new 720 MW power island energized", "energization"),
    )
    for headline, expected in cases:
        got = vg_classify_official_headline(headline)
        assert got == expected, (headline, got, expected)


def vg_official_text(url: str):
    try:
        content = fetch(url, 18).content
        body = normalize(BeautifulSoup(content, "html.parser").get_text(" ", strip=True))
        if len(body) < 300:
            raise ValueError("official text too short")
        return body, None
    except Exception as exc:
        return "", f"{type(exc).__name__}: {str(exc)[:90]}"


def vg_official_rss_events():
    """Official-party news only. Google News syndication alone is not evidence."""
    query = (
        '"Venture Global" ("power island" OR "power generation" OR "AI data center") '
        '(purchase order OR "financial close" OR permit OR construction OR energized OR cancellation)'
    )
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({
        "q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"
    })
    events = {}
    try:
        root = ET.fromstring(fetch(url, 17).content)
    except Exception:
        return []
    import email.utils
    try:
        from googlenewsdecoder import gnewsdecoder
    except ImportError:
        gnewsdecoder = None

    for node in root.findall("./channel/item")[:35]:
        title = normalize(node.findtext("title") or "")
        source_el = node.find("source")
        domain = domain_of(source_el.attrib.get("url", "") if source_el is not None else "")
        if not trusted(domain) and not any(
            domain == d or domain.endswith("." + d) for d in VG_OFFICIAL_DOMAINS
        ):
            continue
        if not any(domain == d or domain.endswith("." + d) for d in VG_OFFICIAL_DOMAINS):
            # Independent news is useful for research but cannot alone
            # promote a purchase order, customer or energization to confirmed.
            continue
        published = node.findtext("pubDate") or ""
        try:
            day = email.utils.parsedate_to_datetime(published)
            if day.tzinfo is None:
                day = day.replace(tzinfo=dt.timezone.utc)
            if day.date() < dt.date(2026, 10, 15):
                continue
            if (dt.datetime.now(dt.timezone.utc) - day).days > 30:
                continue
        except Exception:
            continue
        stage = vg_classify_official_headline(title)
        if not stage:
            continue
        original_link = normalize(node.findtext("link") or "")
        if "news.google.com" in original_link:
            decoded = None
            if gnewsdecoder is not None:
                try:
                    result = gnewsdecoder(original_link, interval=0.1)
                    if isinstance(result, dict) and result.get("status"):
                        decoded = str(result.get("decoded_url") or "")
                except Exception:
                    decoded = None
            original_link = decoded or ""
        article_domain = domain_of(original_link)
        if not original_link or not any(
            article_domain == d or article_domain.endswith("." + d)
            for d in VG_OFFICIAL_DOMAINS
        ):
            # Never send a future milestone with a generic/old source link.
            continue
        key = "vg-power|" + stage
        # Preserve one commercial stage across press reprints; a fresh
        # numbered shipment/plant can be tracked separately after confirmation.
        if stage in {"additional-po", "energization", "delivery"}:
            number = re.search(r"\b(?:number|unit|site)\s*#?\s*(\d+)\b", title, re.I)
            if number:
                key += "|unit-" + number.group(1)
        events.setdefault(key, {
            "stage": stage,
            "title": title,
            "source_domain": domain,
            "url": original_link,
        })
    return list(events.values())


def vg_run_existing_generation_watch():
    vg_parser_self_test()
    previous = old.get("venture_global_power_island") or {}
    checked = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    release_text, release_error = vg_official_text(VG_RELEASE)
    baker_text, baker_error = vg_official_text(VG_BAKER_RELEASE)
    sec_text, sec_error = vg_official_text(VG_SEC_8K)

    release_ok = all(x in release_text.lower() for x in (
        "720 mw", "16", "ge vernova", "baker hughes", "10 gw"
    ))
    baker_ok = all(x in baker_text.lower() for x in (
        "venture global", "ge vernova", "16", "gas turbines"
    ))
    sec_ok = all(x in sec_text.lower() for x in (
        "17.2 billion", "initial unit manufacturing reservation",
        "initial long lead equipment"
    ))
    # The SEC baseline was independently verified on its filed Oct-15 8-K.
    # A temporary SEC website rejection must never silently upgrade a
    # proposed 16-unit maximum to firm orders.
    source_ok = release_ok and baker_ok
    errors = []
    if not release_ok:
        errors.append("Venture Global 공식 보도자료: " + str(release_error or "필수 내용 확인 실패"))
    if not baker_ok:
        errors.append("Baker Hughes 공식 보도자료: " + str(baker_error or "필수 내용 확인 실패"))
    if not sec_ok:
        errors.append("SEC 2026-10-15 8-K 실시간 확인 불가: " + str(sec_error or "필수 문구 확인 실패"))

    # Current framework reservations may be used in LNG projects; there is
    # still no publicly confirmed data center customer/offtake contract.
    stage = dict(previous)
    if source_ok:
        stage.update(VG_BASELINE)
        # Once an actual customer/order/energization was confirmed, do not
        # reset it to False merely because the original framework press
        # release still describes the earlier planning state.
        for confirmed_key in (
            "first_power_island_po_placed", "customer_signed", "facility_energized"
        ):
            if previous.get(confirmed_key) is True:
                stage[confirmed_key] = True
        stage.update({
            "version": 1,
            "official_release_verified_live": True,
            "baker_official_verified_live": True,
            "sec_verified_live": sec_ok,
            "last_checked_utc": checked,
            "source_errors": errors,
        })
    new = []
    if source_ok and not previous.get("framework_alert_delivered"):
        new.append({
            "key": "vg-power|framework-reservations|2026-10-09",
            "stage": "기본계약·예약",
            "title": "Venture Global 16×720MW 조건부 전력섬 기본계약·제조능력 예약",
            "url": VG_RELEASE,
        })
    prior_keys = set(previous.get("alerted_milestones") or [])
    for event in vg_official_rss_events():
        key = "vg-power|" + event["stage"]
        if event["stage"] in {"additional-po", "energization", "delivery"}:
            number = re.search(r"\b(?:number|unit|site)\s*#?\s*(\d+)\b", event["title"], re.I)
            if number:
                key += "|unit-" + number.group(1)
        if key not in prior_keys and source_ok:
            new.append(dict(event, key=key, stage=VG_STAGE_LABELS[event["stage"]]))
    if new:
        seen = list(dict.fromkeys(list(prior_keys) + [x["key"] for x in new]))
        stage["alerted_milestones"] = seen[-180:]
        stage["framework_alert_delivered"] = True
        for event in new:
            key = event["key"]
            if key.startswith("vg-power|first-po") or key.startswith("vg-power|additional-po"):
                stage["first_power_island_po_placed"] = True
                stage["phase"] = "발전설비 실제 구매주문"
            elif key.startswith("vg-power|customer-signed"):
                stage["customer_signed"] = True
                stage["phase"] = "데이터센터 고객 전력계약"
            elif key.startswith("vg-power|energization"):
                stage["facility_energized"] = True
                stage["phase"] = "전원 인가·상업운전"

    # Do not advance the watch on official-source outage. Never send a claim
    # based on RSS third-party paraphrase, historical cache, or target dates.
    if source_ok and new:
        reported_fx = fx if fx_source != "직전 저장값" else 1334.61
        fx_label = (
            fx_source if fx_source != "직전 저장값"
            else "2026-10-16 확인 시장 종가(직전 저장환율 대신 명시적 과거기준)"
        )
        money = krw_from_usd_b(17.2, reported_fx)
        lines = [
            "<b>⚡ LNG→AI 데이터센터 자체발전 실행 감시 · Venture Global(VG)</b>",
            "",
            "• <b>공식 기본계약</b> │ GE Vernova(GEV)·Baker Hughes(BKR)·GE Grid Solutions",
            "• <b>전체 선택권</b> │ 발전설비 최대 16기 × 720MW = <b>11,520MW(11.52GW)</b>",
            "• <b>기존 4.5GW</b> │ 운영·건설·발주를 합친 규모. 모두 현재 발전 중이라는 뜻 아님",
            "• <b>제조능력 예약</b> │ 첫 발주 예정 1기 제외 나머지 15기 중 8기, 전력망 장비 21묶음 중 최초 5묶음",
            f"• <b>SEC 조건부 총 대금</b> │ $17.2B ({money}) · 모든 향후 구매주문 진행 시. 실제 확정 수주 아님",
            "• <b>컴퓨팅 10GW</b> │ 고객·자금조달·인허가 조건이 충족될 때 2034년 말까지의 목표. 이미 계약된 AI 용량 아님",
            "• <b>시간표</b> │ 첫 발전설비 구매주문 2026년 말 목표 → 장비 인도 2028~2034",
            "• <b>초기 수익</b> │ 터빈·증기터빈·변압기·가스절연 개폐장치·전기제어·통합설비",
            "• <b>반복 수익</b> │ 유지보수·부품·성능개선 가능성은 별도 장기 서비스계약 검증 필요",
            "• <b>역풍</b> │ 발전·대기배출 인허가, 가스 연료비, 냉각·방폭·보험, 고객 부족, 대규모 차입·설비투자",
            "",
            "<b>신규 확인·단계 변화</b>",
        ]
        for event in new[:5]:
            lines.append("• " + h(event["stage"]) + ": " + h(event["title"]))
        lines.extend([
            "",
            f"• 환산 기준: 1달러={reported_fx:,.2f}원 · {h(fx_label)}",
            f"• {a('Venture Global 공식발표', VG_RELEASE)}",
            f"• {a('SEC 8-K 기본계약·예약·조건부 금액', VG_SEC_8K)}",
            f"• {a('Baker Hughes 공식 공급범위', VG_BAKER_RELEASE)}",
            "",
            "• 다음 통보: 실제 구매주문·고객 전력계약·인허가 승인·금융종결·장비 인도·상업운전·취소/지연",
        ])
        existing = ALERT.read_text(encoding="utf-8").strip() if ALERT.exists() else ""
        report = "\n".join(lines).strip()
        ALERT.write_text((existing + "\n\n" if existing else "") + report + "\n", encoding="utf-8")

    # Existing watcher already wrote pending state. Extend that one JSON only.
    pending = load_json(PENDING)
    if stage:
        pending["venture_global_power_island"] = stage
        PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if STATUS.exists():
        with STATUS.open("a", encoding="utf-8") as fp:
            fp.write(
                f"- VG 전력섬: {'공식 2자 교차확인' if source_ok else '원천 일시 확인 불가'}"
                f" · 16×720MW=11520MW · SEC 실시간={sec_ok}"
                f" · 신규 의미변화={len(new)}건 · 오류={len(errors)}건\n"
            )
    print(
        f"vg_power_island source_ok={source_ok} sec_ok={sec_ok} "
        f"new_changes={len(new)} alert={bool(new and source_ok)} "
        f"errors={len(errors)} previous_state={bool(previous)}"
    )


vg_run_existing_generation_watch()

# JEFFERIES_ONSITE_SOURCE_GRADED_V1
# Append only to the EXISTING generation-watch alert, pending state and Telegram path.
# A forwarded quotation is not a confirmed Jefferies analyst report.
JEFFERIES_ONSITE_EVENT = "jefferies-onsite-grid-delay-tech-differences-source-graded-20261105"
JEFFERIES_MAY_OFFICIAL = "https://www.jefferies.com/insights/markets/five-trends-shaping-the-future-of-power-and-utilities/"
RABO_ONSITE_RESEARCH = "https://www.rabobank.com/knowledge/d011524694-the-sprint-data-centers-are-building-a-parallel-energy-system-in-the-us"
BLOOM_ORACLE_OFFICIAL = "https://www.bloomenergy.com/news/bloom-energy-and-oracle-expand-strategic-partnership-to-deploy-up-to-2-8-gw-to-accelerate-ai-infrastructure-build-out/"
AEP_GOOGLE_OFFICIAL = "https://www.aep.com/news/stories/view/12314/"
XENERGY_SMRS_SEC = "https://www.sec.gov/Archives/edgar/data/2088896/000119312526347752/xe-20260630.htm"

ONSITE_TECH_REFERENCE = {
    "as_of": "2026-11-05",
    "jefferies_verbatim_2_3_to_4_5_years_confirmed": False,
    "jefferies_verbatim_immediate_sofc_smr_bess_orders_confirmed": False,
    "jefferies_may_2026_published_view": "단기 가스발전·전력망 접속 병목, 원전은 장기",
    "rabobank_grid_36_to_84_months_estimate": [36, 84],
    "rabobank_build_12_to_24_months_estimate": [12, 24],
    "oracle_bloom_firm_contracted_gw": 1.2,
    "oracle_bloom_master_ceiling_gw": 2.8,
    "aep_google_sofc_project_mw": 702,
    "aep_google_ppa_years": 20,
    "aep_google_total_project_capex_usd_b_approx": 4.0,
    "aep_google_target_full_operation": "2028년 말 목표",
    "xenergy_energy_northwest_first_project_mwe": 320,
    "xenergy_energy_northwest_potential_mwe": 960,
    "xenergy_first_operations": "2030년대 초반 전망",
    "bess_1gw_4hr_energy_gwh": 4,
    "bess_1gw_24hr_energy_gwh": 24,
    "scope": "SOFC=연료 투입 발전; BESS=충전된 에너지의 저장·출력; SMR=건설·허가·핵연료 조건을 갖춘 장기 전원",
    "sources": [
        JEFFERIES_MAY_OFFICIAL, RABO_ONSITE_RESEARCH,
        BLOOM_ORACLE_OFFICIAL, AEP_GOOGLE_OFFICIAL, XENERGY_SMRS_SEC
    ],
}


def onsite_bridge_regression_checks() -> None:
    b = ONSITE_TECH_REFERENCE
    assert b["bess_1gw_4hr_energy_gwh"] == 1 * 4
    assert b["bess_1gw_24hr_energy_gwh"] == 1 * 24
    assert b["oracle_bloom_firm_contracted_gw"] < b["oracle_bloom_master_ceiling_gw"]
    assert b["xenergy_first_operations"] != b["aep_google_target_full_operation"]
    assert b["jefferies_verbatim_2_3_to_4_5_years_confirmed"] is False
    assert b["jefferies_verbatim_immediate_sofc_smr_bess_orders_confirmed"] is False


def onsite_official_source_status() -> dict:
    """First-party corroboration only; no news summary can upgrade the quote."""
    checks = {
        "jefferies": (JEFFERIES_MAY_OFFICIAL,
                     ("gas generation is the bridge", "nuclear", "data center")),
        "bloom": (BLOOM_ORACLE_OFFICIAL, ("oracle", "2.8", "1.2", "contracted")),
        "aep": (AEP_GOOGLE_OFFICIAL, ("google", "702", "20-year", "bloom")),
    }
    found = {}
    for key, (url, tokens) in checks.items():
        try:
            page = normalize(BeautifulSoup(fetch(url, 15).text, "html.parser").get_text(" ")).lower()
            found[key] = all(token in page for token in tokens)
        except Exception:
            found[key] = False
    return found


def run_onsite_jefferies_source_graded_extension() -> None:
    onsite_bridge_regression_checks()
    previous = dict(old.get("jefferies_onsite_bridge") or {})
    if previous.get("delivered_id") == JEFFERIES_ONSITE_EVENT:
        print("onsite_jefferies_addendum=duplicate-suppressed")
        return

    # Preserve the normal monitor's event gating and never use an old FX quote
    # or fabricate Jefferies wording when a primary publisher is inaccessible.
    source_check = onsite_official_source_status()
    verified = all(source_check.values())
    fresh_fx = fx is not None and fx_source != "직전 저장값"
    checked = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    if not old.get("initialized") or not verified or not fresh_fx:
        print(f"onsite_jefferies_addendum=hold source_check={source_check} fresh_fx={fresh_fx}")
        if STATUS.exists():
            with STATUS.open("a", encoding="utf-8") as fp:
                fp.write(
                    f"- Jefferies·현장전력 관점: **미발송/원천 확인 보류**"
                    f" · Jefferies={source_check['jefferies']}"
                    f" · Bloom={source_check['bloom']} · AEP={source_check['aep']}"
                    f" · 현재 환율={fresh_fx}\n"
                )
        return

    money_krw = krw_from_usd_b(4.0, fx)
    rows = [
        "<b>전력망 병목·현장발전 3기술 검증 보강 │ 2026-11-05</b>",
        "",
        "<b>■ 핵심 구분</b>",
        "• <b>제프리스 원문 확인 범위</b> │ 2026-05-04 공식 발표는 단기 가스발전 확대·계통접속 병목을 강조.",
        "  전달된 'GW급 센터 전체 공사기간 2~3년→4~5년'과 'SOFC·SMR·BESS 즉시 선주문 폭증'이라는 정확한 인용은 원문 확인 전.",
        "• <b>건설과 전력 접속은 별도 시계</b> │ 라보뱅크 2026-05-06 분석: 건물 12~24개월 / 계통접속 36~84개월.",
        "  모두 같은 프로젝트의 평균 공사기간은 아니며, 전원 인가 전에는 실제 가동·임대매출을 확정할 수 없음.",
        "",
        "<b>■ SOFC: 실제 고객 계약과 상업화</b>",
        "• <b>Bloom–Oracle</b> │ 고체산화물 연료전지 최대 2.8GW 공급 기본계약 상한."
        " 이 가운데 초기 1.2GW 계약·배치 진행, 나머지 최대 1.6GW는 확정 납품 아님.",
        f"• <b>AEP–Google</b> │ 와이오밍 702MW SOFC 발전사업, 총사업비 약 40억달러({money_krw}).",
        "  Google 20년 전력구매계약, 2026년 착공 계획·2028년 말 전체 상업운전 목표.",
        "• <b>전제</b> │ 천연가스 공급·연료개질·현장전력 배전·배출인허가·냉각·장기정비·보증 조건 필요.",
        "",
        "<b>■ SMR과 BESS는 같은 속도의 대체 발전원이 아님</b>",
        "• <b>SMR</b> │ X-energy SEC 공시상 Amazon·Energy Northwest 초기 320MWe 개발,"
        " 확대 가능성 960MWe, 첫 가동은 2030년대 초반 전망. 현재 즉시 공급/가동 아님.",
        "• <b>BESS</b> │ 전기를 생산하지 않고 저장·방전. 1GW를 4시간 공급하려면 4GWh,"
        " 24시간이면 손실 고려 전 최소 24GWh와 재충전 발전원이 필요.",
        "  전력품질·피크·비상 대응과 24시간 주전원 공급을 동일시하지 않음.",
        "",
        "<b>■ 다음 실적 촉발·위험</b>",
        "• 발표 GW → 실제 확정 발주·선수금 → 금융종결·연료계약 → 인허가 → 설비 설치·검수"
        " → 발전 시작 → 데이터센터 전원 인가 순서로 추적.",
        "• 기계 납기·가스관 공급·변압기·보험·방재·배터리 열폭주·SMR 허가가 주요 실패 경로.",
        "  신규 수주량·실제 설치 MW·첫 전원 인가일·유지보수 계약과 현금회수를 확인.",
        "• 기존 발전설비 감시를 보강한 1회 검증 관점이며, Jefferies 미확인 문구를 확정 통계로 저장하지 않음.",
        "",
        "<b>■ 공식 원문 및 대조 자료</b>",
        f"• {a('Jefferies 2026-05-04 공식 발표', JEFFERIES_MAY_OFFICIAL)}",
        f"• {a('Rabobank 건설·접속 대기기간', RABO_ONSITE_RESEARCH)}",
        f"• {a('Bloom–Oracle 공식 계약 단계', BLOOM_ORACLE_OFFICIAL)}",
        f"• {a('AEP–Google 702MW 공식 발표', AEP_GOOGLE_OFFICIAL)}",
        f"• {a('X-energy SEC 2026년 공시', XENERGY_SMRS_SEC)}",
        f"• 환율: 1달러={fx:,.2f}원 · {h(fx_source)} · {checked} UTC",
    ]
    required = (
        "2~3년→4~5년", "12~24개월", "36~84개월", "2.8GW", "1.2GW",
        "702MW", "40억달러", "20년", "2028년 말", "320MWe", "960MWe",
        "2030년대 초반", "4GWh", "24GWh",
        JEFFERIES_MAY_OFFICIAL, BLOOM_ORACLE_OFFICIAL, AEP_GOOGLE_OFFICIAL,
        XENERGY_SMRS_SEC,
    )
    rendered = "\n".join(rows).strip()
    missing = [item for item in required if item not in rendered]
    if missing or any(len(row) > 2800 for row in rows):
        raise RuntimeError(f"현장발전 검증 알림 누락·과긴 문장: {missing}")
    if rendered.count("<b>") != rendered.count("</b>"):
        raise RuntimeError("현장발전 검증 알림 Telegram HTML 굵기 태그 불일치")
    if rendered.count("<a href=") != rendered.count("</a>"):
        raise RuntimeError("현장발전 검증 알림 Telegram 링크 태그 불일치")

    old_text = ALERT.read_text(encoding="utf-8").strip() if ALERT.exists() else ""
    ALERT.write_text((old_text + "\n\n" if old_text else "") + rendered + "\n", encoding="utf-8")
    pending = load_json(PENDING)
    next_state = dict(previous)
    next_state["source_snapshot"] = ONSITE_TECH_REFERENCE
    next_state["official_verified_live"] = source_check
    next_state["delivered_id"] = JEFFERIES_ONSITE_EVENT
    next_state["delivered_at_utc"] = checked
    pending["jefferies_onsite_bridge"] = next_state
    PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if STATUS.exists():
        with STATUS.open("a", encoding="utf-8") as fp:
            fp.write(
                "- Jefferies·현장전력 관점: **원문 대조 1회 보강 알림**"
                f" · source={source_check} · 실제 Telegram 수신은 전송단계 확인 필요\n"
            )
    print(f"onsite_jefferies_addendum=source_checked_and_prepared source={source_check}")


run_onsite_jefferies_source_graded_extension()


# ANTHROPIC_ONEPWR_REPORTED_GENERATOR_ORDERS_V1
# Only the existing generation watcher / Telegram output / JSON state are used.
# Financial Times is the original source; Reuters and CNA reproduce that report,
# not independent confirmation of the private generator purchase.
ANTHRO_ONEPWR_EVENT = "anthropic-onepwr-reported-generator-order-assignment-202609-1p7gw-3p4b"
ANTHRO_ONEPWR_FT = "https://www.ft.com/content/41bf5c6a-9735-4f1a-a8e3-2bcccad58ba0"
ANTHRO_ONEPWR_REUTERS = "https://www.reuters.com/business/energy/anthropic-secures-34-billion-generator-deal-ai-data-centers-ft-reports-2026-11-08/"
ANTHRO_ONEPWR_REUTERS_REPRINT = "https://www.channelnewsasia.com/business/anthropic-secures-34-billion-generator-deal-ai-data-centers-ft-reports-6534256"
ANTHRO_ONEPWR_ET_REPRINT = "https://economictimes.indiatimes.com/tech/artificial-intelligence/anthropic-strikes-3-4bn-deal-to-generate-gas-fired-power-for-data-centres-report/articleshow/135657486.cms"
ANTHRO_ONEPWR_BLOOMBERG_REPRINT = "https://theedgemalaysia.com/node/825001"
ANTHRO_ONEPWR_SEC = "https://www.sec.gov/Archives/edgar/data/2130357/000162828026068676/anthropicpbc-sx1ax1.htm"
ANTHRO_ONEPWR_EO = "https://www.energy.gov/ceser/declaring-national-emergency-secure-united-states-bulk-power-system-executive-order"
ANTHRO_ONEPWR_REPORTED_DATE = dt.date(2026, 11, 8)


def anthro_onepwr_report_valid(text: str) -> bool:
    body = normalize(BeautifulSoup(text or "", "html.parser").get_text(" ", strip=True)).lower()
    if len(body) < 150 or "anthropic" not in body or "onepwr" not in body:
        return False
    if not re.search(r"\b1[.,]7\s*(?:gigawatts?|gw)\b", body):
        return False
    if not re.search(r"\b3[.,]4\s*(?:billion|bn)\b", body):
        return False
    if "generators" not in body and "gas-fired" not in body:
        return False
    # A negated deal or a prospective discussion must never be announced as a purchase.
    if any(term in body for term in (
        "have not struck a deal", "has not struck a deal", "never struck a deal",
        "no agreement has been reached", "may discuss", "still negotiating",
        "only considering the purchase", "deal was denied",
    )):
        return False
    return any(phrase in body for phrase in (
        "has struck a deal", "struck a deal", "bought commitments",
        "agreed to pay", "purchased commitments", "bought generator",
        "acquired the generator", "took over the equipment orders",
        "secured a deal", "secured a 3.4 billion",
    ))


def anthro_onepwr_regression_checks() -> None:
    article = (
        "Anthropic has struck a deal worth about $3.4 billion to secure gas-fired "
        "power generators for data centers. It bought commitments for 1.7 "
        "gigawatts of heavy-duty generators in late September from OnePWR Solutions."
    )
    assert anthro_onepwr_report_valid(article)
    assert not anthro_onepwr_report_valid(
        "Anthropic and OnePWR may discuss 1.7 gigawatts and 3.4 billion dollars "
        "of generators but have not struck a deal."
    )
    assert not anthro_onepwr_report_valid(article.replace("OnePWR", "other supplier"))
    assert not anthro_onepwr_report_valid(article.replace("1.7", "0.7"))
    assert not anthro_onepwr_report_valid(article.replace("$3.4", "$2.4"))
    assert extract_scale_mw("1.7 gigawatts of heavy-duty generators") == 1700.0
    assert stage_of("Gas project includes construction capabilities in purchase deal") != "착공"
    assert stage_of("Gas power plant construction started last week") == "착공"
    assert (3.4 * 1e9 / 1700.0) == 2_000_000


def anthro_onepwr_source_check() -> tuple[list[dict], list[str]]:
    verified, failures = [], []
    for label, url in (
        ("FT 최초 취재", ANTHRO_ONEPWR_FT),
        ("로이터 FT 재인용", ANTHRO_ONEPWR_REUTERS),
        ("로이터 제휴 재게시", ANTHRO_ONEPWR_REUTERS_REPRINT),
        ("로이터 재게시(Economic Times)", ANTHRO_ONEPWR_ET_REPRINT),
        ("블룸버그 FT 재인용", ANTHRO_ONEPWR_BLOOMBERG_REPRINT),
    ):
        try:
            response = fetch(url, timeout=9)
            if anthro_onepwr_report_valid(response.text):
                verified.append({"label": label, "url": url})
                # Reprints of the same FT report are not independent confirmations.
                # One fully verified publisher body is sufficient for 'reported'.
                break
            else:
                failures.append(label + ": 필수 당사자·용량·금액·거래동사 불일치")
        except Exception as exc:
            failures.append(label + ": " + type(exc).__name__)
    return verified, failures


def anthro_onepwr_sec_commitments() -> bool:
    try:
        page = normalize(BeautifulSoup(fetch(ANTHRO_ONEPWR_SEC, timeout=12).text,
                                       "html.parser").get_text(" ", strip=True)).lower()
        return all(term in page for term in ("anthropic", "895.4 billion", "447.5 billion", "69.8 billion"))
    except Exception:
        return False


def run_anthro_onepwr_existing_generation_watch() -> None:
    anthro_onepwr_regression_checks()
    previous = dict(old.get("anthropic_onepwr_generator_orders") or {})
    if previous.get("delivered_event_id") == ANTHRO_ONEPWR_EVENT:
        print("anthropic_onepwr_alert=duplicate_suppressed")
        return

    now = dt.datetime.now(dt.timezone.utc)
    article_age_days = (now.date() - ANTHRO_ONEPWR_REPORTED_DATE).days
    if article_age_days < 0 or article_age_days > 14:
        print("anthropic_onepwr_alert=outside_news_window")
        return

    verified, failures = anthro_onepwr_source_check()
    sec_verified = anthro_onepwr_sec_commitments() if verified else False
    fresh_fx = fx is not None and fx_source != "직전 저장값"
    if not verified or not fresh_fx:
        # A failed source/FX lookup must not mark the event as delivered.
        print(
            "anthropic_onepwr_alert=not_ready "
            f"report_verified={bool(verified)} fresh_fx={fresh_fx} "
            f"source_errors={failures[:3]}"
        )
        return

    original_checked = any(row["url"] == ANTHRO_ONEPWR_FT for row in verified)
    report_status = (
        "FT 원문 직접 확인(기업 공식 계약자료는 미확인)"
        if original_checked else
        f"FT 원보도를 {verified[0]['label']} 경로에서 확인(기업 공식 계약자료·원보도 전문 독립 확인 전)"
    )
    scope = [
        "<b>🔥 [AI 데이터센터 현장발전·발전기 발주권] 앤트로픽–OnePWR</b>",
        "",
        f"• <b>확인 단계</b> │ 2026-11-08 {h(report_status)}. 보도 이후 공식 계약 공시·당사자 확인은 별개.",
        "• <b>거래</b> │ 2026년 9월 말 앤트로픽이 OnePWR의 캐터필러 가스발전기 구매약정 1.7GW(1,700MW)를 양수했다는 FT 보도.",
        "• <b>범위</b> │ OnePWR 법인·직원 인수 아님. 장비 발주권과 설치를 위한 설계·건설 역량을 포함한다는 보도.",
        "• <b>거래 변경 배경</b> │ OnePWR의 약 2년 전 캐터필러 기발주 물량을 원래 전력 고객이 될 예정인 앤트로픽이 직접 승계. OnePWR의 자금조달 제약은 FT 취재 보도.",
        f"• <b>금액</b> │ 34억달러({krw_from_usd_b(3.4, fx)}) · {h(fx_source)} 조회 1달러={fx:,.2f}원 / {h(fx_checked)} UTC.",
        "• <b>단위 비용</b> │ 총액÷1,700MW = MW당 200만달러. 설치·건설 역량 포함 거래여서 발전기 공장출하 평균판매단가로 사용할 수 없음.",
        "• <b>규모 비교</b> │ FT 보도 기준 AI 연구소 단일 발전 장비 확보로 알려진 최대. xAI의 약 20억달러(" + krw_from_usd_b(2.0, fx) + ") 매입 보도보다 70% 크지만 계약 범위·장비 구성이 달라 직접 단가 비교 불가.",
        "• <b>납기·상태</b> │ 단기 및 향후 2년 내 장비 확보 전망은 보도 단계. 납품·시공·가스연료·배출허가·전원 인가·상업운전은 별도 미확인.",
        "• <b>공급망</b> │ OnePWR의 캐터필러 기발주분 승계 보도. 캐터필러 신규 제조 발주나 GE Vernova 신규 수주로 중복 집계 금지.",
    ]
    if sec_verified:
        scope += [
            "• <b>공식 자금약정</b> │ 앤트로픽 2026-11-02 SEC 수정 증권신고서: 컴퓨팅·인프라 구매/리스 약정 총 8,954억달러, 2030년 말까지 4,475억달러 지출 예정, 12개월 내 698억달러.",
            "• <b>금융 구분</b> │ 위 SEC 총 약정은 이번 발전기 보도 계약액이나 이미 집행된 설비투자와 동일하지 않음.",
            "• <b>상장 단계</b> │ 11월 2일 SEC 수정 증권신고서 제출은 확인. 공모가격·상장 완료·최종 신용등급은 아직 별도 확인 대상.",
        ]
    else:
        scope.append("• <b>자금조달</b> │ 앤트로픽 SEC 총 약정 수치는 공식 원문 재조회 불가로 이번 알림의 확인된 거래규모에 합산하지 않음.")
    scope.extend([
        "• <b>신용위험</b> │ 블랙스톤의 신용등급 전망은 보도·의견 단계이며 신용평가사 최종 등급과 구분.",
        "• <b>규제 구분</b> │ 미국 전력망 안보 명령은 EO 14421이며 모든 외국산 발전기를 일괄 금지하지 않음. 이번 계약 직접 적용 여부 미확인.",
        "• <b>다음 확인</b> │ 앤트로픽·OnePWR·캐터필러 공식 확인 → 발주권 이전 범위 → 납품·부지·인허가 → 가스 공급·전력 접속 → 전원 인가 → 실제 운영·정비계약.",
        "",
        "• " + a("FT 최초 취재 원문", ANTHRO_ONEPWR_FT),
        "• " + a(verified[0]["label"] + " 확인 경로", verified[0]["url"]),
        "• " + a("미국 SEC 앤트로픽 수정 증권신고서", ANTHRO_ONEPWR_SEC),
        "• " + a("미국 에너지부 EO 14421 설명", ANTHRO_ONEPWR_EO),
    ])
    rendered = "\n".join(scope).strip()
    if rendered.count("<b>") != rendered.count("</b>") or rendered.count("<a href=") != rendered.count("</a>"):
        raise RuntimeError("Anthropic OnePWR Telegram HTML imbalance")
    if max(map(len, scope)) >= 3200:
        raise RuntimeError("Anthropic OnePWR Telegram line too long")

    preexisting = ALERT.read_text(encoding="utf-8").strip() if ALERT.exists() else ""
    ALERT.write_text((preexisting + "\n\n" if preexisting else "") + rendered + "\n",
                     encoding="utf-8")

    # Only the existing pending JSON is extended. The workflow commits this
    # state after successful Telegram delivery; if sending fails, it retries.
    pending = load_json(PENDING)
    state = dict(previous)
    state.update({
        "model_version": 1,
        "delivered_event_id": ANTHRO_ONEPWR_EVENT,
        "event_kind": "reported_generator_order_assignment",
        "first_reported_on": "2026-11-08",
        "original_contract_month": "2026-09",
        "buyer": "Anthropic",
        "order_rights_seller": "OnePWR Solutions",
        "hardware": "Caterpillar gas-fired generators (FT reported)",
        "generator_orders_mw": 1700,
        "transaction_report_usd_b": 3.4,
        "company_acquired": False,
        "official_contract_confirmed": False,
        "equipment_delivered": False,
        "power_energized": False,
        "source_grade": ("ft_original_article_fetched" if original_checked
                         else "secondary_reprint_of_ft_not_independently_verified"),
        "source_urls": [item["url"] for item in verified],
        "sec_compute_commitments_checked": sec_verified,
        "source_failures": failures[:4],
        "first_alert_prepared_utc": now.isoformat(timespec="seconds"),
    })
    pending["anthropic_onepwr_generator_orders"] = state
    PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
    if STATUS.exists():
        with STATUS.open("a", encoding="utf-8") as handle:
            handle.write(
                "- 앤트로픽–OnePWR: FT 원보도·FT 재인용 자료 단계"
                f" · 1700MW · 34억달러 · SEC 공식 재조회={sec_verified}"
                " · 단일 사건키 · 실제 Telegram 발송 후 상태 저장\n"
            )
    print(
        f"anthropic_onepwr_alert=prepared "
        f"report_sources={len(verified)} ft_direct={original_checked} "
        f"sec_checked={sec_verified} fresh_fx={fresh_fx} "
        f"event_id={ANTHRO_ONEPWR_EVENT}"
    )


run_anthro_onepwr_existing_generation_watch()


# MHI_GTCC_AND_GENERATION_ENGINE_CAPACITY_WATCH_V1
# Existing generation-buildout monitor, sender, and state; NO new bot/workflow.
# 11/6 is the official FY2026 first-half earnings publication, NOT 11/9.
# 11/9 is the date of a user-supplied recap, and of the yen/KRW rate lock.
MHI_GTCC_EVENT = "mhi-7011-20261106-gtcc-500bn-engines-100bn-fy2030-double-v1"
MHI_OFFICIAL_EARNINGS = "https://www.mhi.com/jp/news/26110601.html"
MHI_OFFICIAL_RESULTS = "https://www.mhi.com/jp/finance/library/result"
MHI_TECS_DETAIL = "https://www.tecshx.com/news/mhi-first-half-fy2026-gas-turbine-backlog-83-units-37-gw-forecast-raised"
MHI_MONOSCOPE_DETAIL = "https://monoscope-media.com/mhi-earnings-2026-interim/"
MHI_100JPY_KRW_NOV9 = 856.72  # KEXIM Nov 9 snapshot, NOT a live FX quotation.
MHI_GTCC_CAPEX_JPY_B = 500.0
MHI_ENGINE_CAPEX_JPY_B = 100.0


def mhi_issuer_text_verified(body: str) -> bool:
    text = normalize(BeautifulSoup(body or "", "html.parser").get_text(" ", strip=True)).lower()
    # A generic site footer containing "2026"/"決算" is NOT proof that the
    # actual November 6 quarterly announcement was fetched.
    has_issuer = "三菱重工" in text or "mitsubishi heavy industries" in text
    dated = bool(re.search(r"(?:2026[年./\-]\s*11[月./\-]\s*0?6|nov(?:ember)?\s+6,?\s*2026)", text))
    specific = bool(re.search(
        r"(?:2026年度.{0,16}第2四半期.{0,16}決算|"
        r"fy\s*2026.{0,25}(?:1h|first six months|second quarter|2q))",
        text,
    ))
    return len(text) > 160 and has_issuer and dated and specific


def mhi_capex_text_verified(body: str) -> bool:
    text = normalize(BeautifulSoup(body or "", "html.parser").get_text(" ", strip=True)).lower()
    if len(text) <= 200:
        return False
    # Both amounts must independently attach to the corresponding product,
    # not to nuclear/shipbuilding investment or an explicit denial.
    money_500 = r"(?:5,?000\s*億|(?:¥|jpy)?\s*500\s*(?:billion|bn))"
    money_100 = r"(?:1,?000\s*億|(?:¥|jpy)?\s*100\s*(?:billion|bn))"
    turbine = r"(?:gtcc|gas[\s-]*turbine|ガスタービン|高温部品|hot parts?|blades?)"
    engine = r"(?:engines?|エンジン|発電用エンジン)"
    gtcc_scoped = bool(re.search(
        rf"(?:{turbine}).{{0,140}}?(?:{money_500})|(?:{money_500}).{{0,140}}?(?:{turbine})",
        text, re.I
    ))
    engine_scoped = False
    for m in re.finditer(money_100, text, re.I):
        # The 100-billion amount must be explicitly assigned to engines,
        # and a denial of engine capex takes precedence.
        context = text[max(0, m.start() - 100):min(len(text), m.end() + 110)]
        if re.search(r"\b(?:no|not|without)\s+(?:\w+\s+){0,4}(?:engines?|engine\s+capex)\b", context):
            continue
        if re.search(rf"(?:{engine}).{{0,85}}?{money_100}|{money_100}.{{0,85}}?(?:{engine})", context, re.I):
            engine_scoped = True
            break
    return gtcc_scoped and engine_scoped


def mhi_capex_official_and_independent_checks() -> tuple[str, str]:
    """Return verified issuer URL and independent writeup URL; fail closed."""
    issuer = ""
    detail = ""
    for url in (MHI_OFFICIAL_EARNINGS, MHI_OFFICIAL_RESULTS):
        try:
            if mhi_issuer_text_verified(fetch(url, 10).text):
                issuer = url
                break
        except Exception:
            continue
    for url in (MHI_TECS_DETAIL, MHI_MONOSCOPE_DETAIL):
        try:
            if mhi_capex_text_verified(fetch(url, 10).text):
                detail = url
                break
        except Exception:
            continue
    return issuer, detail


def mhi_gtcc_signal_tests() -> None:
    assert mhi_capex_text_verified(
        "Mitsubishi 2026 GTCC gas turbine hot parts investment ¥500 billion; "
        "data-center power generation engines expansion ¥100 billion. "
        "Factory capacity enhancement and gas turbine blades manufacturing. " * 3
    )
    assert not mhi_capex_text_verified(
        ("GTCC gas turbines hot parts ¥500 billion and nuclear ¥100 billion, "
         "no engines capex data is shown. ") * 5
    )
    assert not mhi_capex_text_verified(
        ("GTCC gas turbines hot parts ¥500 billion and gas generator engines capacity "
         "discussed, but no amount for engine spending. ") * 5
    )
    assert int(round(MHI_GTCC_CAPEX_JPY_B * 1e9 * (MHI_100JPY_KRW_NOV9 / 100) / 1e8)) == 42836
    assert int(round(MHI_ENGINE_CAPEX_JPY_B * 1e9 * (MHI_100JPY_KRW_NOV9 / 100) / 1e8)) == 8567
    assert "gas turbine" not in "GTCC".lower()  # Don't confuse combined cycle with dual fuel.


def run_mhi_gtcc_existing_generation_watch() -> None:
    mhi_gtcc_signal_tests()
    prev = dict(old.get("mhi_gtcc_supply_capacity") or {})
    if prev.get("delivered_event_id") == MHI_GTCC_EVENT:
        print("mhi_gtcc_alert=duplicate_suppressed")
        return
    today = dt.datetime.now(dt.timezone.utc).date()
    if (today - dt.date(2026, 11, 6)).days not in range(0, 15):
        print("mhi_gtcc_alert=outside_initial_news_window")
        return
    issuer, detail = mhi_capex_official_and_independent_checks()
    if not issuer or not detail:
        print("mhi_gtcc_alert=source_hold issuer_checked=" + str(bool(issuer))
              + " capex_independent_checked=" + str(bool(detail)))
        return
    gtcc_won = int(round(MHI_GTCC_CAPEX_JPY_B * 1e9 * (MHI_100JPY_KRW_NOV9 / 100) / 1e8))
    engine_won = int(round(MHI_ENGINE_CAPEX_JPY_B * 1e9 * (MHI_100JPY_KRW_NOV9 / 100) / 1e8))
    source_link = a("미쓰비시중공업 11/6 공식 실적발표", issuer)
    detail_link = a("생산능력·설비투자 보강 근거", detail)
    rows = [
        "<b>가스터빈 공급능력·데이터센터 발전 엔진 변화 — 미쓰비시중공업(7011)</b>",
        "",
        "• <b>기준일</b> │ 실적 공식 발표 2026-11-06; 11/09는 재전달일.",
        "• <b>생산능력 목표</b> │ 대형 GTCC 가스터빈 FY2024 대비 FY2030까지 약 2배. "
        "기존 2026년 중 언급된 목표의 재확인이며 새 수주·실제 출하 2배 아님.",
        f"• <b>고온부품·블레이드</b> │ FY2027 이후 주요 투자 약 5,000억엔(약 {gtcc_won:,}억원). "
        "완제품 공장 2배 증설비 전액과 동일시하지 않음.",
        f"• <b>데이터센터 발전용 피스톤엔진</b> │ 별도 투자 약 1,000억엔(약 {engine_won:,}억원). "
        "가스터빈과 다른 제품·생산능력이며 함께 6,000억엔 성장투자로 추적.",
        "• <b>현재 수주</b> │ FY2026 상반기 대형 가스터빈 19대·약 8GW 신규 주문, "
        "2026년 9월 말 계약 잔량 83대·약 37GW(설명자료 보도 기준).",
        "• <b>실적 연결</b> │ 부품·조립 자동화→검사·가동률→터빈 납품·검수→발전소 "
        "연료·환경허가·전원 인가→실제 발전; 발표된 생산 목표가 즉시 납기 단축은 아님.",
        "• <b>리드타임 주의</b> │ 전달 메모의 36~48개월은 산업 일반 주장으로 회사별 최신 확정 납기 아님. "
        "수주잔고·계약 납기·고객 취소·설비 가동을 분리해 재확인.",
        "• <b>GTCC 뜻</b> │ 가스터빈의 폐열로 증기터빈을 추가 구동하는 복합화력. "
        "경유+가스 동시 연소를 뜻하지 않음.",
        "• <b>다음 경보</b> │ 새 블레이드 생산라인 양산·공장 가동률·대형터빈 발주/납기 "
        "변화·발전 엔진 고객계약·대형 전원 인가/인허가 지연.",
        "• <b>확인 수준</b> │ 공식 실적발표 날짜 확인 + 관련 세부 금액에 관한 독립 자료 대조. "
        "공식 IR PDF의 모든 페이지를 직접 재추출한 것은 아님.",
        "• <b>원화 환산</b> │ 2026-11-09 수출입은행 기준 100엔=856.72원; "
        "과거 기준일 환율이며 향후 현재 환율로 재사용 금지.",
        "",
        "• " + source_link,
        "• " + detail_link,
    ]
    payload = "\n".join(rows).strip()
    if payload.count("<b>") != payload.count("</b>") or payload.count("<a href=") != payload.count("</a>"):
        raise RuntimeError("MHI gas turbine Telegram HTML tags unbalanced")
    if len(payload) > 3400:
        raise RuntimeError("MHI gas turbine alert unexpectedly exceeds one-chunk budget")
    previous_alert = ALERT.read_text(encoding="utf-8").strip() if ALERT.exists() else ""
    ALERT.write_text((previous_alert + "\n\n" if previous_alert else "") + payload + "\n", encoding="utf-8")
    state = load_json(PENDING)
    state["mhi_gtcc_supply_capacity"] = {
        **prev,
        "version": 1,
        "delivered_event_id": MHI_GTCC_EVENT,
        "announcement_date": "2026-11-06",
        "baseline_fy": "2024",
        "target_fy": "2030",
        "target_gtcc_capacity_multiple": 2.0,
        "capex_hot_parts_jpy_b": 500,
        "capex_engine_jpy_b": 100,
        "investment_from_fy": 2027,
        "first_half_large_turbine_orders_units": 19,
        "first_half_large_turbine_orders_gw": 8,
        "large_turbine_contract_backlog_units": 83,
        "large_turbine_contract_backlog_gw": 37,
        "source_urls": [issuer, detail],
        "evidence": "issuer_release_and_independent_capex_coverage; slide_pages_not_directly_parsed",
        "stage": "capacity_investment_plan_not_delivered_turbines",
        "last_prepared_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    PENDING.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if STATUS.exists():
        with STATUS.open("a", encoding="utf-8") as fp:
            fp.write("- MHI GTCC/engine capacity: **2026-11-06 verified official date + independent capex, alert pending delivery**\n")
    print("mhi_gtcc_alert=prepared event=" + MHI_GTCC_EVENT)


run_mhi_gtcc_existing_generation_watch()


# JET_ENGINE_TURBINE_REUSE_WATCH_V1
# Nov-09 Reuters/Decrypt industry story. Track the manufacturer's actual
# orders, not the misleading implication that Crusoe bought used aircraft
# engines. Stay inside this already-running generation/Telegram pipeline.
JET_TURBINE_EVENT = "used-turbines-aircraft-derived-ai-power-20261109-reuters-firstparty-v1"
JET_REUTERS_NOV9 = "https://www.reuters.com/business/aerospace-defense/ai-power-rush-sends-data-centres-hunting-used-turbines-jet-engines-2026-11-09/"
JET_DECRYPT_NOV9 = "https://decrypt.co/382890/ai-data-centers-used-jet-engines-power-turbines"
JET_PROENERGY_CRUSOE = "https://www.proenergyservices.com/2026/04/proenergy-to-deliver-major-generating-equipment-to-power-crusoe-ai-factories/"
JET_FTAI_POWER_ORIGINAL = "https://ir.ftaiaviation.com/news-releases/news-release-details/ftai-aviation-announces-launch-ftai-power-ftai-adapts-worlds"
JET_FTAI_FIRM_ORDER = "https://ir.ftaiaviation.com/news-releases/news-release-details/ftai-announces-1465-billion-gas-turbine-generator-set-order"
JET_EPA_DATA_CENTERS = "https://www.epa.gov/stationary-sources-air-pollution/clean-air-act-resources-data-centers"
JET_REFERENCE = {
    "story_date": "2026-11-09",
    "woodmac_us_new_turbine_average_delivery_years_reported": 6,
    "global_orders_gw_over": 100,
    "global_annual_production_capacity_gw_range": [60, 70],
    "crusoe_proenergy_original_contract_date": "2026-04-16",
    "crusoe_units_contracted": 13,
    "crusoe_pe6000_mw_each": 50,
    "crusoe_contract_total_mw": 650,
    "crusoe_ordered_used_retired_aircraft_engines": False,
    "ftai_original_conversion_platform": "CFM56",
    "ftai_mod1_unit_mw": 25,
    "ftai_jf_initial_purchase_order_usd_b": 1.465,
    "ftai_jf_order_date": "2026-07-22",
    "ftai_jf_delivery_target": "2027-11",
    "ftai_cloud_customer_publicly_named": False,
    "ftai_jf_master_contract_years": 5,
    "ftai_performance_price_downward_adjustment_cap_pct": 10,
    "used_turbine_price_usd_m_per_mw_reported": [1.5, 1.7],
    "new_turbine_price_usd_m_per_mw_reported": [2.0, 2.5],
    "broker_used_pair_mw_reported": 29,
    "broker_used_pair_usd_m_reported": 12.5,
    "broker_equivalent_new_pair_usd_m_reported": 35,
    "cleanview_proposed_onsite_generation_gw_reported": 90,
    "cleanview_operating_onsite_generation_gw_reported": 2,
    "w506_gas_piston_engines_us_data_center_orders_gw_reported": 3,
    "gev_q2_contract_and_reservation_gw": 116,
    "gev_q3_contract_and_reservation_gw": 122,
    "gev_q2_year_end_target_gw": 125,
    "gev_q3_year_end_target_gw": 130,
    "contract_scope_warning": "Crusoe PE6000 is aircraft-derived generator, not proof it bought retired aircraft engines; FTAI order different customer",
    "source_level": "Reuters/Decrypt Nov09 interviews for lead time/price; manufacturer primary for Crusoe & FTAI orders; GE official Q3",
    "official": [JET_PROENERGY_CRUSOE, JET_FTAI_POWER_ORIGINAL, JET_FTAI_FIRM_ORDER,
                 GEV_Q3_2026, JET_EPA_DATA_CENTERS],
    "reported": [JET_REUTERS_NOV9, JET_DECRYPT_NOV9],
}


def jet_turbine_regression_checks() -> None:
    b = JET_REFERENCE
    assert b["crusoe_units_contracted"] * b["crusoe_pe6000_mw_each"] == b["crusoe_contract_total_mw"]
    assert b["crusoe_ordered_used_retired_aircraft_engines"] is False
    assert b["ftai_cloud_customer_publicly_named"] is False
    assert b["ftai_performance_price_downward_adjustment_cap_pct"] == 10
    assert b["gev_q3_contract_and_reservation_gw"] - b["gev_q2_contract_and_reservation_gw"] == 6
    assert b["gev_q3_year_end_target_gw"] - b["gev_q2_year_end_target_gw"] == 5
    assert b["used_turbine_price_usd_m_per_mw_reported"][1] < b["new_turbine_price_usd_m_per_mw_reported"][0]
    assert b["global_annual_production_capacity_gw_range"][1] < b["global_orders_gw_over"]
    assert "FTAI" in "FTAI" and JET_PROENERGY_CRUSOE != JET_FTAI_FIRM_ORDER


def jet_turbine_primary_probe() -> dict:
    """Publisher evidence, with no fallback pretending Reuters was fetched."""
    sites = (
        ("proenergy_crusoe", JET_PROENERGY_CRUSOE, ("crusoe", "13", "pe6000", "50 mw")),
        ("ftai_jf_order", JET_FTAI_FIRM_ORDER, ("1.465", "initial purchase order", "cfm56", "november 2027")),
        ("ftai_engine_conversion", JET_FTAI_POWER_ORIGINAL, ("cfm56", "25-megawatt", "remanufacture")),
        ("gev_q3", GEV_Q3_2026, ("third quarter 2026", "116 to 122 gw", "130 gw")),
        ("epa_standards", JET_EPA_DATA_CENTERS, ("stationary", "emission", "data centers")),
    )
    out = {}
    for label, url, required in sites:
        try:
            body = normalize(BeautifulSoup(fetch(url, 12).text, "html.parser").get_text(" ")).lower()
            out[label] = all(term in body for term in required)
        except Exception:
            out[label] = False
    return out


def jet_turbine_event_due(prev: dict, proof: dict, first: bool, fresh_fx: bool,
                          today: dt.date | None = None) -> bool:
    today = today or dt.datetime.now(dt.timezone.utc).date()
    age = (today - dt.date(2026, 11, 9)).days
    return bool(
        not first and fresh_fx and 0 <= age <= 14
        and prev.get("delivered_event_id") != JET_TURBINE_EVENT
        and proof.get("proenergy_crusoe") and proof.get("ftai_jf_order")
    )


def jet_turbine_alert_text(proof: dict) -> str:
    b = JET_REFERENCE
    usd = fx
    def mw_cost(usd_m: float) -> str:
        return krw_from_usd_b(usd_m / 1000, usd)
    content = [
        "<b>데이터센터 중고 가스터빈·항공기 엔진 기반 발전기 | 11월 9일 뉴스</b>",
        "",
        "<b>■ 핵심 · 새 기사와 과거 확정 수주를 분리</b>",
        "• <b>미국 신형 가스터빈 납기 평균 6년</b> │ Wood Mackenzie 분석을 Reuters가 11월9일 인용."
        " 개발 기간 6년이라는 뜻 아님; 제조사·모델·납품 순서마다 달라질 수 있음.",
        "• <b>글로벌 수급</b> │ 신규 주문 100GW 초과 대 추정 연간 생산능력 60~70GW."
        " 전체 주문잔고와 연간 생산능력을 같은 분모의 당해연도 부족 물량으로 계산하지 않음.",
        "• <b>사용 장비 2종 분리</b> │ ① 중고·재정비된 발전용 가스터빈,"
        " ② 항공기 엔진 기술을 이용해 신규 조립한 항공기 유래형 발전기.",
        "",
        "<b>■ 1. ProEnergy–Crusoe 공식 계약 · 2026년 4월 16일</b>",
        "• <b>PE6000 13기 × 50MW = 650MW</b> 실제 장비 공급계약."
        " 13기 전부 폐항공기에서 떼어낸 중고 엔진을 구매했다는 뜻 아님.",
        "• <b>납품 전 검증</b> │ 미국 Sedalia 공장에서 설치적합성·품질검사 후 인도 예정."
        " 실제 발전소 설치·연료 연결·전원 인가·운영 매출 시점은 공식 확인 전.",
        "• <b>매출·단가</b> │ 이 개별 계약의 대금·개당 평균판매단가 미공개."
        " 중고 발전기 시장 평균가격을 650MW 계약의 확정 매출로 적용 금지.",
        "",
        "<b>■ 2. FTAI Aviation–J&F 발전기 사업 공식 주문</b>",
        f"• <b>7월22일 초기 발주 14억6,500만달러({krw_from_usd_b(1.465, usd)})</b>."
        " FTAI·Jereh 합작사 J&F가 해외 클라우드 사업자(실명 비공개)와 체결.",
        "• <b>CFM56 항공기 엔진 재제조 기반 Mod-1</b>."
        " 2027년 11월까지 분할 납품; 5년 기본공급계약 추가발주 여부는 별도.",
        "• <b>현금회수·보증</b> │ 계약 시 선급금·제작·시험·현장검수 단계별 대금."
        " 출력 미달에 따른 최종 대금 감액 상한은 해당 장비가치의 10%.",
        "• <b>고객 관계</b> │ FTAI 고객을 Crusoe 또는 특정 빅테크로 추측해 확정하지 않음.",
        "",
        "<b>■ 3. 장비 가격·대체 시장 (11월9일 Reuters 취재)</b>",
        f"• 중고 발전용 가스터빈 <b>1MW당 150만~170만달러({mw_cost(1.5)}~{mw_cost(1.7)})</b>.",
        f"• 신규 발전용 가스터빈 <b>1MW당 200만~250만달러({mw_cost(2.0)}~{mw_cost(2.5)})</b>.",
        f"• 중개사 사례 <b>29MW 중고 1,250만달러({mw_cost(12.5)})</b> 대"
        f" 동급 신품 약 3,500만달러({mw_cost(35)}) 추정."
        " 장비 사양·설치비·정비보증 차이를 보정한 공통가격이 아님.",
        "• Cleanview 중간연도 추정: 미국 데이터센터 현장발전 제안 90GW 중"
        " 실제 가동 약 2GW. 발표 용량을 기가와트급 준공과 혼동 금지.",
        "• Wärtsilä의 미국 데이터센터 가스 피스톤엔진 주문 약 3GW도 Reuters 보도."
        " 터빈 수주와 피스톤엔진 수주 중복 합산 금지.",
        "",
        "<b>■ 4. GE Vernova 3분기 공식 수치 · 2분기와 비교</b>",
        "• 가스터빈 확정 잔고 + 슬롯 예약 합계 <b>116GW → 122GW(+6GW)</b>."
        " 2026년 말 목표 <b>125GW → 130GW(+5GW)</b>.",
        "• 122GW는 전량 확정발주·이미 출하한 장비나 미국 데이터센터 전용 수주가 아님.",
        "",
        "<b>■ 실패경로 및 다음 추적</b>",
        "• 중고 장비 정비 이력·잔존 수명·연료효율·연속 가동 신뢰성과"
        " 새 발전기와 다른 유지보수 비용·보험·보증충당금 확인.",
        "• EPA 고정형 터빈 대기오염 규제와 지역 배출허가·가스관·송전·변압기 병목."
        " 발표 전력→납품→환경허가→상업운전→데이터센터 전원 인가 구분.",
        "• 다음 알림은 신규 실제 주문·납품·인수시험·가동·취소·지연과"
        " 중고단가·신제품 납기의 동일 기준 변화가 공식 문서에 확인될 때만.",
        "",
        "<b>■ 근거 수준</b>",
        "• 납기 6년·중고단가·90GW/2GW는 Reuters/Decrypt 11월9일 산업 보도 인용."
        " Wood Mackenzie·Cleanview 원표와 개별 중고 매매서류는 별도 미확인.",
        "• ProEnergy·FTAI 공식 보도에서 실제 계약 범위·납기·고객 익명 여부 확인."
        " 원문 뉴스 기사를 이들 회사의 공식 발언으로 바꿔 쓰지 않음.",
        "",
        f"• {a('Reuters 11월9일 원보도', JET_REUTERS_NOV9)}",
        f"• {a('Decrypt 11월9일 재보도', JET_DECRYPT_NOV9)}",
        f"• {a('ProEnergy–Crusoe 13기 공식계약', JET_PROENERGY_CRUSOE)}",
        f"• {a('FTAI–J&F 14억6,500만달러 공식계약', JET_FTAI_FIRM_ORDER)}",
        f"• {a('FTAI CFM56 재제조 기술 공표', JET_FTAI_POWER_ORIGINAL)}",
        f"• {a('GE Vernova 2026년 3분기 공식실적', GEV_Q3_2026)}",
        f"• {a('미국 EPA 데이터센터 배출규정', JET_EPA_DATA_CENTERS)}",
        f"• 환율 1달러={usd:,.2f}원 · {h(fx_source)} · 조회 {h(fx_checked)} UTC",
        f"• 원천 확인: ProEnergy={proof.get('proenergy_crusoe')},"
        f" FTAI={proof.get('ftai_jf_order')}, GE Q3={proof.get('gev_q3')}"
    ]
    report = "\n".join(content).strip()
    required = ("6년", "650MW", "13기", "1.465", "14억6,500만달러",
                "2027년 11월", "116GW", "122GW", "125GW", "130GW",
                "1,250만달러", "3,500만달러", "EPA",
                JET_PROENERGY_CRUSOE, JET_FTAI_FIRM_ORDER, JET_REUTERS_NOV9)
    missing = [t for t in required if t not in report]
    # The USD amount appears as Korean money without a literal 1.465.
    missing = [t for t in missing if t != "1.465"]
    if missing or report.count("<b>") != report.count("</b>") or report.count("<a href=") != report.count("</a>"):
        raise RuntimeError(f"Jet turbine data-center alert lost critical fact or HTML tag: {missing}")
    if any(len(line) >= 2800 for line in content):
        raise RuntimeError("Jet turbine alert has a single line too large to split safely")
    return report


def run_jet_turbine_existing_generation_watch() -> None:
    jet_turbine_regression_checks()
    prev = dict(old.get("jet_turbine_reuse_data_center") or {})
    if prev.get("delivered_event_id") == JET_TURBINE_EVENT:
        print("jet_turbine_reuse_alert=duplicate_suppressed")
        return
    proof = jet_turbine_primary_probe()
    fresh_fx = fx is not None and fx_source != "직전 저장값"
    if not jet_turbine_event_due(prev, proof, not old.get("initialized"), fresh_fx):
        print(f"jet_turbine_reuse_alert=source_or_date_hold official={proof} fresh_fx={fresh_fx}")
        return
    rendered = jet_turbine_alert_text(proof)
    # Append after all older integrated alerts; never replace earlier content.
    previous_text = ALERT.read_text(encoding="utf-8").strip() if ALERT.exists() else ""
    ALERT.write_text((previous_text + "\n\n" if previous_text else "") + rendered + "\n",
                     encoding="utf-8")
    stage = dict(prev)
    stage.update({
        "version": 1,
        "event_id": JET_TURBINE_EVENT,
        "delivered_event_id": JET_TURBINE_EVENT,
        "first_source_date": JET_REFERENCE["story_date"],
        "source_snapshot": JET_REFERENCE,
        "official_sources_verified_live": proof,
        "press_report_status": "Reuters/Decrypt Nov09 attributed; direct Reuters text may be access-limited",
        "crusoe_contract_stage": "signed_equipment_supply_not_energized",
        "ftai_contract_stage": "signed_initial_order_not_delivered",
        "gev_reference_period": "2026-Q3",
        "prepared_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    })
    pending = load_json(PENDING)
    pending["jet_turbine_reuse_data_center"] = stage
    PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if STATUS.exists():
        with STATUS.open("a", encoding="utf-8") as fd:
            fd.write(
                f"- 중고·항공유래 발전기 11월9일 보강: **보낼 자료 작성**"
                f" · ProEnergy={proof.get('proenergy_crusoe')}"
                f" · FTAI={proof.get('ftai_jf_order')}"
                f" · GE={proof.get('gev_q3')}"
                " · Telegram 발송 후에만 상태 확정\n"
            )
    print(f"jet_turbine_reuse_alert=prepared source={proof} old_state_preserved=true")


run_jet_turbine_existing_generation_watch()
