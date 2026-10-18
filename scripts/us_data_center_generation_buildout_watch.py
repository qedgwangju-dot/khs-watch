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
    "gas_contract_slot_gw": 116.0,
    "year_end_target_gw": 125.0,
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
    try:
        text = normalize(BeautifulSoup(fetch(GEV_Q2_2026).text, "html.parser").get_text(" "))
    except Exception:
        return dict(VERIFIED_GEV)
    metrics = dict(VERIFIED_GEV)
    patterns = {
        "gas_contract_slot_gw": r"(?:grew from 100 to|from 100 to)\s*([0-9.]+)\s*GW",
        "year_end_target_gw": r"(?:at least|reaching at least)\s*([0-9.]+)\s*GW\s+by year-end 2026",
        "output_2026_gw": r"deliver\s*([0-9.]+)\s*GW\s+of annual gas turbine output.*?third quarter of 2026",
        "output_2028_gw": r"with\s*([0-9.]+)\s*GW\s+in 2028",
        "output_2030_gw": r"produce\s*([0-9.]+)\s*GW\s+in 2030",
        "dc_orders_ytd_usd_b": r"data center orders reaching over\s*\$?([0-9.]+)\s*billion",
    }
    for key, pat in patterns.items():
        m = re.search(pat, text, re.I)
        if m:
            metrics[key] = float(m.group(1))
    return metrics


def stage_of(text: str) -> str:
    low = text.lower()
    if any(k in low for k in ("forecast", "outlook", "projection", "estimate", "전망", "추정")) and any(k in low for k in ("data center", "data centre", "데이터센터", "power", "capacity", "gw", "gwh")):
        return "전망 변경"
    if any(k in low for k in ("cancel", "withdraw", "delay", "postpone", "suspend", "canceled", "cancelled")):
        return "취소·지연"
    if any(k in low for k in ("commercial operation", "commissioned", "online", "operational", "cod")):
        return "상업운전"
    if any(k in low for k in ("construction", "groundbreak", "build begins", "under construction")):
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
            title = normalize(item.findtext("title") or "")
            link = normalize(item.findtext("link") or "")
            source_el = item.find("source")
            source = normalize(source_el.text if source_el is not None else "")
            source_url = normalize(source_el.attrib.get("url", "") if source_el is not None else "")
            domain = domain_of(source_url)
            if not trusted(domain):
                continue
            blob = f"{title} {source}"
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
should_alert = baseline_run or format_upgrade or bool(new_items) or bool(gev_changes)

seen = list(dict.fromkeys(list(old_ids) + [x["id"] for x in items]))[-1600:]
pending = {
    "initialized": True,
    "format_version": FORMAT_VERSION,
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
        chosen = sorted(new_items, key=lambda x: (0 if x['stage'] in ('상업운전','착공','계약·수주') else 1, -x.get('scale_mw',0)))[:5]
        for idx, x in enumerate(chosen, 1):
            ko = translate_title(x['title'], x['stage'], x['source'])
            if len(ko) > 170:
                ko = ko[:167].rstrip() + "…"
            scale = f" · {x['scale_mw']:,.0f}MW" if x.get('scale_mw') else ""
            msg.append(f"{idx}. 🔗 {a(ko, x['url'])}")
            msg.append(f"   {h(x['stage'])} · {h(x['source'])}{h(scale)}")
        if len(new_items) > len(chosen):
            msg.append(f"• 나머지 {len(new_items)-len(chosen)}건은 중복방지 상태에 저장해 다음 변화 판정에 반영합니다.")
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
