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
    "bloombergtax.com", "advisorperspectives.com",
)

NEWS_QUERIES = (
    'data center power plant gas turbine BESS 500 MW contract construction United States',
    'data center behind-the-meter power 500 MW gas BESS NRG GE Vernova Crusoe',
    'AI data center power generation project commercial operation 500 MW United States',
    'gas turbine data center order supply 500 MW United States',
    'Moody data center 45 GW 110 billion power plants 2030',
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
        ("advisorperspectives", "Bloomberg"),
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
    low = text.lower().replace(",", "")
    vals = []
    vals += [float(x) for x in re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*mw", low)]
    vals += [float(x) * 1000 for x in re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*gw", low)]
    return max(vals + [0.0])


def is_meaningful(text: str, source: str) -> bool:
    low = text.lower()
    scale = extract_scale_mw(text)
    if "mood" in low and any(k in low for k in ("45 gw", "110 billion", "$110")):
        return True
    if "ge vernova" in low and any(k in low for k in ("gas turbine", "slot", "data center", "data centre")):
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
    title = "✅ 미국 데이터센터 발전설비 감시 분리 완료" if baseline_run else "🔥 미국 데이터센터 발전설비 실행 변화"
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
