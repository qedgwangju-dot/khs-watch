from __future__ import annotations

import copy
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

try:
    from googlenewsdecoder import gnewsdecoder
except Exception:
    gnewsdecoder = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "us_ai_grid_bottleneck_state.json"
PENDING_PATH = ROOT / "out" / "us_ai_grid_bottleneck_pending_state.json"
ALERT_PATH = ROOT / "out" / "us_ai_grid_bottleneck_alert.txt"
STATUS_PATH = ROOT / "out" / "us_ai_grid_bottleneck_status.md"

UA = "Mozilla/5.0 (compatible; khs-watch/1.0; +https://github.com/qedgwangju-dot/khs-watch)"

BASELINE = {
    "as_of": "2026-09-27",
    "metrics": {
        "dc_electricity_2024_twh": 192.0,
        "dc_electricity_2030_twh": 649.0,
        "dc_electricity_2030_low_twh": 521.0,
        "dc_electricity_2030_high_twh": 843.0,
        "dc_share_2030_pct": 11.8,
        "transformer_avg_lead_weeks": 120.0,
        "large_transformer_low_weeks": 80.0,
        "large_transformer_high_weeks": 210.0,
        "queue_projects": 8200.0,
        "queue_gw": 2060.0,
        "transmission_345kv_plus_miles_2024": 888.0,
        "bushing_lead_low_weeks_secondary": 135.0,
        "bushing_lead_high_weeks_secondary": 145.0,
        "ms_it_power_2025_gw": 9.19,
        "ms_it_power_2026_gw": 17.96,
        "ms_it_power_2027_gw": 35.46,
        "ms_it_power_2028_gw": 52.31,
        "ms_it_power_2029_gw": 78.57,
        "ms_new_power_need_2026_2028_gw": 97.0,
        "ms_under_construction_gw": 21.0,
        "ms_grid_available_gw": 19.0,
        "ms_gross_gap_gw": 57.0,
        "ms_mitigation_gw": 24.0,
        "ms_residual_gap_gw": 33.0,
        "cw_padmount_transformer_low_weeks": 68.0,
        "cw_padmount_transformer_high_weeks": 113.0,
        "cw_generator_low_weeks": 60.0,
        "cw_generator_high_weeks": 100.0,
        "cw_mv_switchgear_low_weeks": 38.0,
        "cw_mv_switchgear_high_weeks": 63.0,
        "cw_lv_switchgear_low_weeks": 36.0,
        "cw_lv_switchgear_high_weeks": 60.0,
        "cw_ups_low_weeks": 36.0,
        "cw_ups_high_weeks": 42.0,
    },
    "sources": {
        "dc_demand": {
            "url": "https://escholarship.org/uc/item/33m6w3x0",
            "kind": "Lawrence Berkeley National Laboratory 공식 보고서",
        },
        "queue": {
            "url": "https://emp.lbl.gov/queues",
            "kind": "Lawrence Berkeley National Laboratory 공식",
        },
        "transformer": {
            "url": "https://www.nerc.com/globalassets/programs/rapa/ra/nerc_sra_2025.pdf",
            "kind": "NERC 2025 Summer Reliability Assessment",
        },
        "transmission": {
            "url": "https://www.cleanenergygrid.org/new-report-reveals-u-s-transmission-buildout-lagging-far-behind-national-needs/",
            "kind": "ACEG/Grid Strategies 공개자료",
        },
        "bushing": {
            "url": "",
            "kind": "사용자 제공 2차 기준선·공식 원천 확인 전",
        },
        "cw_equipment_2026": {
            "url": "https://www.cushmanwakefield.com/en/united-states/insights/data-center-development-cost-guide",
            "kind": "Cushman & Wakefield 2026 Data Center Development Cost Guide / 사용자 제공 현대차증권 도표 교차기준",
        },
        "jll_equipment_2026": {
            "url": "https://www.jll.com/content/dam/jllcom/en/global/documents/reports/research-reports/26-research-global-data-center-outlook-new.pdf",
            "kind": "JLL 2026 Global Data Center Outlook 교차검증",
        },
    },
    "seen_urls": [],
    "last_checked_at_kst": "",
}

SEARCHES = [
    ("google", 'site:lbl.gov OR site:escholarship.org "data center" 2030 649 TWh electricity'),
    ("google", 'site:emp.lbl.gov queues 2025 interconnection 8200 2060 GW'),
    ("google", 'site:nerc.com transformer lead times 120 weeks 80 210'),
    ("google", 'site:energy.gov large power transformer lead time 36 60 months'),
    ("google", '"power transformer" lead time data center 2026 Reuters'),
    ("google", '"generator step-up" transformer lead time 2026'),
    ("google", '"transformer bushing" lead time weeks 2026 high voltage'),
    ("google", 'site:cushmanwakefield.com 2026 data center transformer generator switchgear UPS lead time'),
    ("google", 'site:jll.com 2026 data center equipment lead time transformer generator switchgear UPS PDU chiller'),
    ("google", '"medium voltage switchgear" "lead time" data center 2026'),
    ("google", '"low voltage switchgear" "lead time" data center 2026'),
    ("google", '"UPS" "lead time" data center 2026'),
    ("google", '"data center" generator lead time 2026 Caterpillar Cummins Rolls-Royce'),
    ("google", 'site:eaton.com 2026 data center switchgear factory production'),
    ("google", 'site:se.com 2026 data center switchgear supply capacity agreement'),
    ("google", '"345 kV" transmission miles 2026 United States'),
    ("google", 'site:ferc.gov data center large load interconnection transmission 2026'),
    ("google", 'site:nerc.com large load data center reliability guideline 2026'),
    ("google", 'site:pjm.com data center large load interconnection 2026'),
    ("google", 'site:misoenergy.org large load data center interconnection 2026'),
    ("google", 'site:ercot.com large load data center interconnection 2026'),
    ("google", 'Hitachi Energy transformer factory United States 2026'),
    ("google", 'GE Vernova transformer factory expansion United States 2026'),
    ("google", 'Siemens Energy transformer capacity expansion United States 2026'),
    ("google", 'LS ELECTRIC data center transformer order United States 2026'),
    ("google", 'Hyosung Heavy Industries US transformer data center 2026'),
    ("google", 'HD Hyundai Electric US transformer data center 2026'),
    ("google", '"모건스탠리" data center 78.57 GW 2029 97 GW power shortfall'),
    ("google", '"모건스탠리" data center power 57 GW 33 GW 2026 2028'),
]

OFFICIAL_DOMAINS = (
    "lbl.gov", "escholarship.org", "emp.lbl.gov", "nerc.com", "energy.gov", "ferc.gov",
    "pjm.com", "misoenergy.org", "ercot.com", "hitachienergy.com", "gevernova.com",
    "siemens-energy.com", "ls-electric.com", "hyosungheavyindustries.com",
    "hd-hyundaielectric.com", "eaton.com", "se.com", "abb.com", "vertiv.com",
    "cat.com", "cummins.com", "rolls-royce.com", "cushmanwakefield.com", "jll.com",
)

TRUSTED_DOMAINS = (
    "reuters.com", "utilitydive.com", "datacenterdynamics.com", "cleanenergygrid.org",
    "woodmac.com", "spglobal.com", "bloomberg.com", "ft.com",
    "finance.yahoo.com", "investing.com", "credaily.com", "datacenterscouts.com",
)

MATERIAL_TERMS = (
    "transformer", "bushing", "transmission", "interconnection", "grid", "substation",
    "energization", "energized", "large load", "data center", "datacenter",
    "switchgear", "generator", "ups", "pdu", "power distribution", "electrical equipment",
    "변압기", "부싱", "송전", "계통", "변전소", "전원", "배전반", "발전기", "무정전전원",
)


def fetch(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<(script|style|svg|noscript)[^>]*>.*?</\1>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def parse_pubdate(value: str) -> datetime | None:
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo("Asia/Seoul"))
    except Exception:
        return None


def google_news_url(query: str) -> str:
    q = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def read_rss(kind: str, query: str) -> list[dict]:
    root = ET.fromstring(fetch(google_news_url(query)))
    out = []
    for item in root.findall("./channel/item"):
        title = clean_text(item.findtext("title") or "")
        link = clean_text(item.findtext("link") or "")
        desc = clean_text(item.findtext("description") or "")
        dt = parse_pubdate(clean_text(item.findtext("pubDate") or ""))
        if title and link:
            out.append({
                "kind": kind,
                "title": title,
                "link": link,
                "description": desc,
                "published_at_kst": dt.isoformat(timespec="seconds") if dt else "",
            })
    return out


def decode_google_news(link: str) -> str:
    if "news.google.com" not in (link or ""):
        return link
    if gnewsdecoder is None:
        return ""
    try:
        result = gnewsdecoder(link, interval=0.15)
        if isinstance(result, dict) and result.get("status"):
            decoded = str(result.get("decoded_url") or "").strip()
            if decoded.startswith("http") and "news.google.com" not in decoded:
                return decoded
    except Exception:
        pass
    return ""


def direct_url(item: dict) -> str:
    return decode_google_news(item.get("link") or "")


def article_text(url: str) -> str:
    if not url:
        return ""
    try:
        return clean_text(fetch(url, timeout=18).decode("utf-8", errors="ignore"))[:36000]
    except Exception:
        return ""


def load_json(path: pathlib.Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def source_rank(url: str) -> int:
    host = host_of(url)
    if any(host == d or host.endswith("." + d) for d in OFFICIAL_DOMAINS):
        return 3
    if any(host == d or host.endswith("." + d) for d in TRUSTED_DOMAINS):
        return 2
    return 1


def num(value: str) -> float | None:
    try:
        return float(str(value).replace(",", ""))
    except Exception:
        return None


def parse_metrics(text: str) -> dict:
    low = text.lower()
    out: dict[str, float] = {}

    m = re.search(r"2030[^.]{0,180}?(\d{3})\s*TWh", text, re.I)
    if m and "data center" in low:
        v = num(m.group(1))
        if v and 300 <= v <= 1200:
            out["dc_electricity_2030_twh"] = v

    m = re.search(r"(\d{1,2}(?:\.\d+)?)\s*%[^.]{0,100}?(?:U\.?S\.?\s+electricity|total.*electricity)", text, re.I)
    if m and "2030" in text and "data center" in low:
        v = num(m.group(1))
        if v and 5 <= v <= 30:
            out["dc_share_2030_pct"] = v

    m = re.search(r"(?:lead times? for transformers|transformer lead times?)[^.]{0,140}?(?:averag(?:e|ing)|average)[^.]{0,60}?(\d{2,3})\s*weeks", text, re.I)
    if m:
        v = num(m.group(1))
        if v and 30 <= v <= 300:
            out["transformer_avg_lead_weeks"] = v

    m = re.search(r"large transformer lead times?[^.]{0,120}?(\d{2,3})\s*[-–]\s*(\d{2,3})\s*weeks", text, re.I)
    if m:
        lo, hi = num(m.group(1)), num(m.group(2))
        if lo and hi and 30 <= lo < hi <= 400:
            out["large_transformer_low_weeks"] = lo
            out["large_transformer_high_weeks"] = hi

    m = re.search(r"(?:GSU|generator step[- ]up)[^.]{0,150}?(\d{2,3})\s*weeks", text, re.I)
    if m:
        v = num(m.group(1))
        if v and 40 <= v <= 350:
            out["gsu_lead_weeks"] = v

    m = re.search(r"(?:bushing|bushings)[^.]{0,140}?(\d{2,3})\s*[-–]\s*(\d{2,3})\s*weeks", text, re.I)
    if m:
        lo, hi = num(m.group(1)), num(m.group(2))
        if lo and hi and 20 <= lo < hi <= 350:
            out["bushing_lead_low_weeks_secondary"] = lo
            out["bushing_lead_high_weeks_secondary"] = hi

    if "interconnection" in low or "queue" in low:
        m = re.search(r"(?:about|approximately|roughly)?\s*([0-9,]{4,6})\s+(?:projects|active projects)", text, re.I)
        if m:
            v = num(m.group(1))
            if v and 1000 <= v <= 50000:
                out["queue_projects"] = v
        m = re.search(r"([0-9,]{3,5}(?:\.\d+)?)\s*GW", text, re.I)
        if m:
            v = num(m.group(1))
            if v and 500 <= v <= 10000:
                out["queue_gw"] = v

    if "345" in text and ("mile" in low or "transmission" in low):
        m = re.search(r"(\d{2,4}(?:,\d{3})?)\s*(?:miles?|mi)[^.]{0,100}?(?:345\s*kV|345-kV|345 kV)", text, re.I)
        if not m:
            m = re.search(r"(?:345\s*kV|345-kV|345 kV)[^.]{0,100}?(\d{2,4}(?:,\d{3})?)\s*(?:miles?|mi)", text, re.I)
        if m:
            v = num(m.group(1))
            if v and 50 <= v <= 5000:
                out["transmission_345kv_plus_miles_latest"] = v

    if "morgan stanley" in low and ("data center" in low or "datacenter" in low):
        year_patterns = {
            2025: "ms_it_power_2025_gw",
            2026: "ms_it_power_2026_gw",
            2027: "ms_it_power_2027_gw",
            2028: "ms_it_power_2028_gw",
            2029: "ms_it_power_2029_gw",
        }
        for year, key_name in year_patterns.items():
            m = re.search(rf"{year}[^.]{{0,120}}?([0-9]{{1,3}}(?:\.[0-9]+)?)\s*GW", text, re.I)
            if not m:
                m = re.search(rf"([0-9]{{1,3}}(?:\.[0-9]+)?)\s*GW[^.]{{0,120}}?{year}", text, re.I)
            if m:
                v = num(m.group(1))
                if v and 0.1 <= v <= 200:
                    out[key_name] = v

        semantic_patterns = [
            (
                "ms_new_power_need_2026_2028_gw",
                [
                    r"(?:2026\s*(?:to|through|[-–])\s*2028|2026[^.]{0,40}2028)[^.]{0,180}?([0-9]{1,3}(?:\.[0-9]+)?)\s*GW[^.]{0,100}?(?:power|electricity|demand|require|need)",
                    r"(?:require|need|demand)[^.]{0,120}?([0-9]{1,3}(?:\.[0-9]+)?)\s*GW[^.]{0,120}?(?:2026\s*(?:to|through|[-–])\s*2028|2026[^.]{0,40}2028)",
                ],
                40, 160,
            ),
            (
                "ms_under_construction_gw",
                [
                    r"([0-9]{1,3}(?:\.[0-9]+)?)\s*GW[^.]{0,100}?(?:under construction|being built|construction)",
                    r"(?:under construction|being built|construction)[^.]{0,100}?([0-9]{1,3}(?:\.[0-9]+)?)\s*GW",
                ],
                5, 80,
            ),
            (
                "ms_grid_available_gw",
                [
                    r"([0-9]{1,3}(?:\.[0-9]+)?)\s*GW[^.]{0,120}?(?:grid capacity|grid.*available|available.*grid)",
                    r"(?:grid capacity|grid.*available|available.*grid)[^.]{0,120}?([0-9]{1,3}(?:\.[0-9]+)?)\s*GW",
                ],
                5, 80,
            ),
            (
                "ms_gross_gap_gw",
                [
                    r"([0-9]{1,3}(?:\.[0-9]+)?)\s*GW[^.]{0,120}?(?:initial|potential)?\s*(?:gap|shortfall|deficit)",
                    r"(?:initial|potential)?\s*(?:gap|shortfall|deficit)[^.]{0,120}?([0-9]{1,3}(?:\.[0-9]+)?)\s*GW",
                ],
                10, 120,
            ),
            (
                "ms_residual_gap_gw",
                [
                    r"([0-9]{1,3}(?:\.[0-9]+)?)\s*GW[^.]{0,120}?(?:residual|remaining)[^.]{0,50}?(?:gap|shortfall|deficit)",
                    r"(?:residual|remaining)[^.]{0,80}?(?:gap|shortfall|deficit)[^.]{0,120}?([0-9]{1,3}(?:\.[0-9]+)?)\s*GW",
                ],
                5, 100,
            ),
        ]
        for key_name, patterns, lo, hi in semantic_patterns:
            for pat in patterns:
                m = re.search(pat, text, re.I)
                if not m:
                    continue
                v = num(m.group(1))
                if v is not None and lo <= v <= hi:
                    out[key_name] = v
                    break

    return out


def pct_change(new: float, old: float) -> float:
    return (new / old - 1.0) * 100.0 if old else 0.0


def material_metric_changes(old: dict, new: dict) -> list[dict]:
    rules = {
        "dc_electricity_2030_twh": ("2030 데이터센터 전력수요", "pct", 10.0),
        "dc_share_2030_pct": ("2030 미국 전력 비중", "pp", 1.5),
        "transformer_avg_lead_weeks": ("변압기 평균 납기", "abs", 10.0),
        "large_transformer_high_weeks": ("대형변압기 최장 납기", "abs", 10.0),
        "gsu_lead_weeks": ("발전기 승압용 변압기 납기", "abs", 10.0),
        "bushing_lead_high_weeks_secondary": ("초고압 부싱 납기", "abs", 10.0),
        "queue_projects": ("계통연결 대기 프로젝트", "pct", 10.0),
        "queue_gw": ("계통연결 대기 용량", "pct", 10.0),
        "transmission_345kv_plus_miles_latest": ("345kV+ 송전선 연간 준공", "pct", 25.0),
        "ms_it_power_2029_gw": ("모건스탠리 2029 데이터센터 IT 전력", "pct", 10.0),
        "ms_new_power_need_2026_2028_gw": ("모건스탠리 2026~2028 신규 전력 필요량", "abs", 10.0),
        "ms_gross_gap_gw": ("모건스탠리 1차 전력 부족분", "abs", 5.0),
        "ms_residual_gap_gw": ("모건스탠리 대체전원 반영 후 부족분", "abs", 5.0),
    }
    out = []
    for key, (label, mode, threshold) in rules.items():
        if key not in old or key not in new:
            continue
        before = float(old[key]); after = float(new[key])
        if mode == "pp":
            delta = after - before
        elif mode == "abs":
            delta = after - before
        else:
            delta = pct_change(after, before)
        if abs(delta) >= threshold:
            out.append({"key": key, "label": label, "mode": mode, "before": before, "after": after, "delta": delta})
    return out


def structural_event(text: str, url: str) -> str:
    low = text.lower()
    if source_rank(url) < 2:
        return ""
    if any(k in low for k in ("new factory", "new plant", "breaks ground", "expansion", "expand capacity", "capacity expansion")) and "transformer" in low:
        return "변압기 생산능력 증설·신공장 일정 변화"
    if any(k in low for k in ("energization delayed", "energization delay", "power-on delayed", "utility upgrade", "energized")) and any(k in low for k in ("data center", "datacenter")):
        return "데이터센터 전원 인가 일정 변화"
    if any(k in low for k in ("large load", "data center")) and any(k in low for k in ("interconnection rule", "tariff", "queue reform", "reliability guideline", "ferc order")):
        return "대형부하·데이터센터 계통접속 규칙 변화"
    if "transmission" in low and any(k in low for k in ("approved", "construction", "in service", "energized")) and any(k in low for k in ("345 kv", "500 kv", "765 kv")):
        return "345kV+ 송전망 승인·착공·준공 변화"
    return ""


def format_metric(key: str, value: float) -> str:
    if key.endswith("_twh"):
        return f"{value:,.0f}TWh"
    if key.endswith("_pct"):
        return f"{value:.1f}%"
    if "weeks" in key:
        return f"{value:,.0f}주"
    if key == "queue_projects":
        return f"{value:,.0f}개"
    if key == "queue_gw":
        return f"{value:,.0f}GW"
    if "miles" in key:
        return f"{value:,.0f}마일"
    if key.endswith("_gw") or "_gw" in key:
        return f"{value:,.2f}GW" if abs(value - round(value)) > 1e-6 else f"{value:,.0f}GW"
    return f"{value:,.1f}"


def build_alert(changes: list[dict], events: list[dict], state: dict) -> str:
    m = state.get("metrics") or {}
    lines = [
        "<b>⚡ 미국 AI 전력망 병목 감시 — 변화 감지</b>",
        "",
        "<b>핵심 변화</b>",
    ]
    for ch in changes:
        suffix = "%p" if ch["mode"] == "pp" else ("주" if ch["mode"] == "abs" and "납기" in ch["label"] else "%")
        lines.append(
            f"• <b>{html.escape(ch['label'])}</b>: "
            f"{html.escape(format_metric(ch['key'], ch['before']))} → "
            f"{html.escape(format_metric(ch['key'], ch['after']))} "
            f"({ch['delta']:+.1f}{suffix})"
        )
    for ev in events:
        lines.append(f"• <b>구조 변화:</b> {html.escape(ev['event'])} — {html.escape(ev['title'])}")
        if ev.get("url"):
            lines.append(f'  <a href="{html.escape(ev["url"], quote=True)}">원문</a>')

    lines += [
        "",
        "<b>1단계 현재 숫자 추적</b>",
        f"• 미국 데이터센터 전력사용 2030 기준: {format_metric('dc_electricity_2030_twh', float(m.get('dc_electricity_2030_twh') or 0))} "
        f"/ 범위 {format_metric('dc_electricity_2030_low_twh', float(m.get('dc_electricity_2030_low_twh') or 0))}~{format_metric('dc_electricity_2030_high_twh', float(m.get('dc_electricity_2030_high_twh') or 0))} "
        f"/ 미국 전체의 {float(m.get('dc_share_2030_pct') or 0):.1f}%",
        f"• 변압기 평균 납기: {format_metric('transformer_avg_lead_weeks', float(m.get('transformer_avg_lead_weeks') or 0))}; "
        f"대형변압기 {format_metric('large_transformer_low_weeks', float(m.get('large_transformer_low_weeks') or 0))}~"
        f"{format_metric('large_transformer_high_weeks', float(m.get('large_transformer_high_weeks') or 0))}",
        f"• 계통연결 대기: {format_metric('queue_projects', float(m.get('queue_projects') or 0))} / "
        f"{format_metric('queue_gw', float(m.get('queue_gw') or 0))}",
        f"• 345kV+ 송전선 최신 기준: "
        f"{format_metric('transmission_345kv_plus_miles_2024', float(m.get('transmission_345kv_plus_miles_latest') or m.get('transmission_345kv_plus_miles_2024') or 0))}",
        f"• 모건스탠리 IT 전력 경로: 2025 {float(m.get('ms_it_power_2025_gw') or 0):.2f}GW → "
        f"2026 {float(m.get('ms_it_power_2026_gw') or 0):.2f}GW → 2027 {float(m.get('ms_it_power_2027_gw') or 0):.2f}GW → "
        f"2028 {float(m.get('ms_it_power_2028_gw') or 0):.2f}GW → 2029 {float(m.get('ms_it_power_2029_gw') or 0):.2f}GW",
        f"• 모건스탠리 전력 수급 스트레스: 2026~2028 신규 필요 {float(m.get('ms_new_power_need_2026_2028_gw') or 0):.0f}GW "
        f"→ 건설 중 {float(m.get('ms_under_construction_gw') or 0):.0f}GW + 전력망 가용 {float(m.get('ms_grid_available_gw') or 0):.0f}GW "
        f"→ 1차 부족 {float(m.get('ms_gross_gap_gw') or 0):.0f}GW → 대체전원 반영 후 약 {float(m.get('ms_residual_gap_gw') or 0):.0f}GW",
        "",
        "<b>2단계 미래 재평가 요인 발굴</b>",
        "• 전력수요 ↑ + 변압기 납기 ↑ + 계통대기 ↑가 동시에 나오면 AI 데이터센터 전원 인가 지연 위험이 커집니다.",
        "• 반대로 변압기 납기 ↓ + 345kV+ 송전선 준공 ↑ + 계통대기 ↓ + 실제 전원 인가 ↑가 함께 나와야 병목 완화로 판정합니다.",
        "• 신공장 증설은 발표가 아니라 고객 인증·숙련공 채용·초기 양산·실제 출하 시점까지 추적합니다.",
        "",
        "<b>관련 기업 지도</b>",
        "• 직접 전력기기: Hitachi Energy·GE Vernova·Siemens Energy·Prolec GE",
        "• 국내 직접 수혜: 효성중공업·HD현대일렉트릭·LS ELECTRIC — 북미 변압기·배전·개폐기",
        "• 유틸리티/계통: PJM·MISO·ERCOT 및 지역 전력회사 — 접속·변전소·송전선·전원 인가",
        "• 최종 수요: Microsoft·Meta·Amazon·Google·Oracle·OpenAI/CoreWeave 등 대형 데이터센터",
        "",
        "<b>공정 병목 후보</b>",
        "• 대형변압기 | 주문형 설계·제조 | 먼저 볼 지표: 납기·수주잔고·가동률 | 위험 구간 12~36개월",
        "• 부싱·절연부품 | 본체 증설 뒤 부품 병목 | 먼저 볼 지표: 부싱 납기·공급사 증설 | 위험 구간 12~24개월",
        "• 송전선·변전소 | 장비가 있어도 전원 경로 부족 | 먼저 볼 지표: 345kV+ 준공·변전소 준공 | 위험 구간 12~36개월",
        "• 계통연결 | 발전·저장 프로젝트가 있어도 접속연구 지연 | 먼저 볼 지표: 대기 GW·프로젝트 수·처리기간 | 위험 구간 12~36개월",
        "",
        "<b>숨은 역풍·실패모드</b>",
        "• 가장 현실적인 실패 경로: 건물·GPU는 준비됐지만 변압기·변전소·송전선 또는 계통접속이 늦어 전원 인가가 지연되는 경우.",
        "• 조기경보: 변압기 납기 재상승, 계통 대기용량 증가, 345kV+ 준공 감소, 데이터센터 전원 인가일 연기.",
        "• 완화 확인: 납기 단축이 가격·수주잔고 붕괴가 아니라 증설 가동과 실제 출하 증가로 설명되고, 계통대기와 전원 인가가 동시에 개선될 때.",
        "",
        "<b>알림 기준</b>",
        "• 2030 데이터센터 전력수요 ±10% 이상, 전력 비중 ±1.5%p 이상.",
        "• 변압기·GSU·부싱 납기 ±10주 이상.",
        "• 계통연결 대기 프로젝트·GW ±10% 이상.",
        "• 345kV+ 송전선 연간 준공량 ±25% 이상.",
        "• 대형 변압기 신공장 생산개시·지연, 계통접속 규칙 변경, 데이터센터 전원 인가 6개월 이상 지연/앞당김은 즉시 알림.",
        "",
        "<b>결론</b>",
        "• 이 감시는 반도체 공급망과 분리해 '돈과 GPU가 있어도 전력이 늦어 실제 서버가 켜지지 않는가'를 추적합니다.",
        "",
        "<b>핵심 한 줄 요약</b>",
        f"• 현재 기준은 2030 데이터센터 {float(m.get('dc_electricity_2030_twh') or 0):.0f}TWh, "
        f"계통대기 {float(m.get('queue_projects') or 0):,.0f}개·{float(m.get('queue_gw') or 0):,.0f}GW, "
        f"변압기 평균 {float(m.get('transformer_avg_lead_weeks') or 0):.0f}주(대형 {float(m.get('large_transformer_low_weeks') or 0):.0f}~{float(m.get('large_transformer_high_weeks') or 0):.0f}주)이며, "
        "핵심은 송전·변전·계통접속·전원 인가가 실제로 빨라지는지입니다.",
    ]
    return "\n".join(lines).strip() + "\n"


def discover(now: datetime, seen_urls: set[str]) -> tuple[list[dict], list[dict]]:
    metric_obs: list[dict] = []
    events: list[dict] = []
    cutoff = now - timedelta(days=90)
    local_seen = set()
    fetch_budget = 18
    fetched = 0

    for kind, query in SEARCHES:
        try:
            items = read_rss(kind, query)
        except Exception:
            continue
        for item in items:
            url = direct_url(item)
            if not url or url in local_seen:
                continue
            local_seen.add(url)
            pub = item.get("published_at_kst") or ""
            try:
                dt = datetime.fromisoformat(pub) if pub else None
            except Exception:
                dt = None
            if dt and dt < cutoff:
                continue
            base = clean_text(f"{item.get('title','')} {item.get('description','')}")
            low = base.lower()
            if not any(term in low for term in MATERIAL_TERMS):
                continue
            if fetched >= fetch_budget:
                continue
            fetched += 1
            body = article_text(url)
            text = clean_text(f"{base} {body}")
            metrics = parse_metrics(text)
            if metrics:
                metric_obs.append({
                    "url": url, "published_at_kst": pub, "metrics": metrics,
                    "rank": source_rank(url), "title": item.get("title") or "",
                })
            if url not in seen_urls:
                ev = structural_event(text, url)
                if ev:
                    events.append({
                        "event": ev, "url": url, "published_at_kst": pub,
                        "title": item.get("title") or "", "rank": source_rank(url),
                    })

    metric_obs.sort(key=lambda x: (x["rank"], x.get("published_at_kst") or ""), reverse=True)
    events.sort(key=lambda x: (x["rank"], x.get("published_at_kst") or ""), reverse=True)
    return metric_obs, events


def merge_verified_metrics(previous: dict, observations: list[dict]) -> tuple[dict, list[str]]:
    latest = copy.deepcopy(previous)
    evidence = []
    claimed = set()
    for obs in observations:
        if obs["rank"] < 2:
            continue
        for key, value in (obs.get("metrics") or {}).items():
            if key in claimed:
                continue
            if key.startswith("bushing_") and obs["rank"] < 3:
                continue
            latest[key] = value
            claimed.add(key)
            evidence.append(obs["url"])
    return latest, list(dict.fromkeys(evidence))


def main() -> None:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    state = load_json(STATE_PATH) or copy.deepcopy(BASELINE)
    previous_metrics = copy.deepcopy(state.get("metrics") or BASELINE["metrics"])
    for k, v in BASELINE["metrics"].items():
        previous_metrics.setdefault(k, v)
    seen_urls = set(state.get("seen_urls") or [])

    observations, events = discover(now, seen_urls)
    new_metrics, evidence_urls = merge_verified_metrics(previous_metrics, observations)
    changes = material_metric_changes(previous_metrics, new_metrics)

    latest = copy.deepcopy(state)
    latest["metrics"] = new_metrics
    latest["seen_urls"] = sorted(seen_urls | {x.get("url") for x in observations + events if x.get("url")})[-300:]
    latest["last_checked_at_kst"] = now.isoformat(timespec="seconds")
    latest["metric_observation_count"] = len(observations)
    latest["event_count"] = len(events)
    latest["latest_evidence_urls"] = evidence_urls[-20:]

    write_json(PENDING_PATH, latest)

    notify = bool(changes or events)
    if notify:
        ALERT_PATH.parent.mkdir(parents=True, exist_ok=True)
        ALERT_PATH.write_text(build_alert(changes, events, latest), encoding="utf-8")
    else:
        ALERT_PATH.unlink(missing_ok=True)

    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(
        "# 미국 AI 전력망 병목 감시\n\n"
        f"- 확인시각: {now.isoformat(timespec='seconds')}\n"
        f"- 지표 관측: {len(observations)}개\n"
        f"- 구조 이벤트: {len(events)}개\n"
        f"- 중요 변화: {len(changes)}개\n"
        f"- 알림: {'예' if notify else '아니오'}\n",
        encoding="utf-8",
    )

    print(
        "us_ai_grid_bottleneck_watch=true "
        f"observations={len(observations)} events={len(events)} changes={len(changes)} "
        f"notify={str(notify).lower()}"
    )


if __name__ == "__main__":
    main()
