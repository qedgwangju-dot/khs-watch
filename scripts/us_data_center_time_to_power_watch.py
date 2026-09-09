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
STATE = Path("data/us_data_center_time_to_power_state.json")
PJM_STATE = Path("data/pjm_data_center_policy_state.json")
ALERT = OUT / "us_data_center_time_to_power_alert.txt"
PENDING = OUT / "us_data_center_time_to_power_pending_state.json"
STATUS = OUT / "us_data_center_time_to_power_status.md"

FERC_LARGE_LOAD = "https://www.ferc.gov/news-events/news/ferc-launches-aggressive-targeted-action-speed-large-load-integration"
FERC_DECISIONS = "https://www.ferc.gov/news-events/news/decisions-notices"
FEDERAL_REGISTER_API = "https://www.federalregister.gov/api/v1/documents.json"
MISO_LARGE_LOAD = "https://www.misoenergy.org/planning/large-loads---container-page/large-load-additions/"
MISO_ERAS5 = "https://www.misoenergy.org/meet-miso/media-center/2026---news-releases/miso-accelerates-new-generation-and-storage-projects-with-fifth-eras-cycle/"
ERCOT_ARCHIVE = "https://www.ercot.com/services/comm/mkt_notices/archives"
ERCOT_LARGE_LOAD = "https://www.ercot.com/services/rq/large-load-integration"
ABB_MEDIA = "https://www.abb.com/global/en/company/media"
ABB_800V = "https://www.abb.com/global/en/company/innovation/hybrid-ac-dc-power"

# FERC's June 18, 2026 large-load show-cause proceedings.
FERC_DOCKETS = {
    "PJM": "EL26-67-000",
    "SPP": "EL26-68-000",
    "NYISO": "EL26-69-000",
    "MISO": "EL26-70-000",
    "CAISO": "EL26-71-000",
    "ISO-NE": "EL26-72-000",
}

OFFICIAL_DOMAINS = (
    "ferc.gov", "federalregister.gov", "misoenergy.org", "ercot.com",
    "abb.com", "nvidia.com", "eaton.com", "lguplus.com", "ls-electric.com",
)
TRUSTED_NEWS_DOMAINS = (
    "reuters.com", "utilitydive.com", "rtoinsider.com", "energy-storage.news",
    "datacenterdynamics.com", "publicpower.org",
)

NEWS_QUERIES = (
    'FERC large load data center PJM MISO SPP CAISO ISO-NE NYISO',
    'MISO ERAS large load Zero Injection ZGIA data center',
    'ERCOT Batch Zero BYOG WLPUN large load data center',
    '800V DC data center NVIDIA ABB Eaton LS ELECTRIC',
    'data center onsite power gas generation BESS 500 MW ERCOT MISO PJM',
)

HEADERS = {"User-Agent": "khs-watch/1.0 (+https://github.com/qedgwangju-dot/khs-watch)"}
FORMAT_VERSION = 1


def fetch(url: str, timeout: int = 35):
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


def absurl(base: str, href: str) -> str:
    return urllib.parse.urljoin(base, href or "")


def domain_of(url: str) -> str:
    return urllib.parse.urlparse(url or "").netloc.lower().replace("www.", "")


def domain_matches(domain: str, domains: tuple[str, ...]) -> bool:
    return any(domain == d or domain.endswith("." + d) for d in domains)


def has_korean(text: str) -> bool:
    return bool(re.search(r"[가-힣]", text or ""))


def fx_rate(old=None):
    sources = [
        ("https://open.er-api.com/v6/latest/USD", lambda d: d["rates"]["KRW"], "ER-API"),
        ("https://api.frankfurter.app/latest?from=USD&to=KRW", lambda d: d["rates"]["KRW"], "Frankfurter"),
    ]
    for url, parser, name in sources:
        try:
            v = float(parser(fetch(url, 20).json()))
            if 500 < v < 3000:
                return v, name
        except Exception:
            pass
    if old:
        return float(old), "직전 저장값"
    return None, "조회 실패"


def krw_from_usd(usd: float, fx: float) -> str:
    eok = round(usd * fx / 100_000_000)
    jo, rem = divmod(eok, 10000)
    if jo and rem:
        return f"약 {jo:,}조 {rem:,}억원"
    if jo:
        return f"약 {jo:,}조원"
    return f"약 {rem:,}억원"


def money_suffix_from_title(title: str, fx: float | None) -> str:
    if not fx:
        return ""
    low = title.lower().replace(",", "")
    patterns = [
        (r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*(?:billion|bn|b)\b", 1e9),
        (r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*(?:million|mn|m)\b", 1e6),
    ]
    vals = []
    for pat, mult in patterns:
        for m in re.finditer(pat, low, re.I):
            try:
                vals.append(float(m.group(1)) * mult)
            except Exception:
                pass
    if not vals:
        return ""
    return " · " + ", ".join(krw_from_usd(v, fx) for v in vals[:2])


def translate_google(text: str) -> str | None:
    if not text or has_korean(text):
        return text
    try:
        params = {"client": "gtx", "sl": "auto", "tl": "ko", "dt": "t", "q": text}
        url = "https://translate.googleapis.com/translate_a/single?" + urllib.parse.urlencode(params)
        data = fetch(url, 15).json()
        out = "".join(seg[0] for seg in (data[0] or []) if isinstance(seg, list) and seg and isinstance(seg[0], str))
        out = normalize(out)
        return out if has_korean(out) else None
    except Exception:
        return None


def translate_mymemory(text: str) -> str | None:
    if not text or has_korean(text):
        return text
    try:
        data = fetch(
            "https://api.mymemory.translated.net/get?" + urllib.parse.urlencode({"q": text, "langpair": "en|ko"}),
            15,
        ).json()
        out = normalize((data.get("responseData") or {}).get("translatedText") or "")
        return out if has_korean(out) else None
    except Exception:
        return None


def fallback_korean(theme: str, source: str) -> str:
    labels = {
        "FERC·대형부하 규칙": "대형부하 계통접속·비용배분 규칙 관련 신규 공식자료",
        "MISO·계통접속": "MISO 발전·ESS 신속 계통접속 관련 신규 자료",
        "ERCOT·Batch Zero": "ERCOT 데이터센터 대형부하 Batch Zero 관련 신규 자료",
        "800V DC": "AI 데이터센터 800V DC 상용화 관련 신규 자료",
        "발전·BESS 프로젝트": "데이터센터 연계 발전·BESS 프로젝트 관련 신규 자료",
    }
    return f"{source} · {labels.get(theme, '미국 데이터센터 전력 인가 관련 신규 자료')}"


def translate_title(text: str, theme: str, source: str) -> str:
    text = normalize(html.unescape(text))
    if has_korean(text):
        return text
    out = translate_google(text) or translate_mymemory(text)
    if not out:
        return fallback_korean(theme, source)
    replacements = {
        "데이터 센터": "데이터센터",
        "대규모 부하": "대형부하",
        "백 스톱": "백스톱",
        "배치 제로": "Batch Zero",
        "제로 인젝션": "Zero Injection",
        "그리드": "전력망",
    }
    for old, new in replacements.items():
        out = out.replace(old, new)
    return out


def clean_source(source: str, url: str = "") -> str:
    s = (source or domain_of(url)).lower()
    mapping = (
        ("miso", "MISO"), ("ercot", "ERCOT"), ("ferc", "FERC"),
        ("federal register", "Federal Register"), ("utility", "Utility Dive"),
        ("rto", "RTO Insider"), ("reuters", "Reuters"),
        ("energy-storage", "Energy-Storage.News"), ("datacenterdynamics", "Data Center Dynamics"),
        ("abb", "ABB"), ("nvidia", "NVIDIA"), ("eaton", "Eaton"),
        ("lguplus", "LG유플러스"), ("ls-electric", "LS ELECTRIC"),
    )
    for key, label in mapping:
        if key in s:
            return label
    return normalize(source)[:35] or domain_of(url)[:35]


def classify(text: str) -> str:
    low = (text or "").lower()
    if "800v" in low and any(k in low for k in ("dc", "direct current", "data center", "data centre", "rack")):
        return "800V DC"
    if any(k in low for k in ("batch zero", "byog", "wlpun", "sb6", "large load curtail", "community impact rfi")):
        return "ERCOT·Batch Zero"
    if any(k in low for k in ("eras", "zero injection", "zgia", "large load framework", "large load additions", "120 days")):
        return "MISO·계통접속"
    if any(d.lower() in low for d in FERC_DOCKETS.values()) or any(k in low for k in ("show cause", "section 206", "cost recovery agreement")):
        return "FERC·대형부하 규칙"
    if ("data center" in low or "data centre" in low or "hyperscaler" in low) and any(
        k in low for k in ("mw", "gw", "gas generation", "power plant", "battery", "bess", "onsite power", "on-site power")
    ):
        return "발전·BESS 프로젝트"
    return "기타"


def is_meaningful(item: dict) -> bool:
    text = f"{item.get('title','')} {item.get('summary','')}".lower()
    theme = item.get("theme") or classify(text)
    if item.get("official") and theme != "기타":
        return True
    if theme == "800V DC":
        return any(k in text for k in (
            "customer", "adopt", "deploy", "contract", "order", "supply", "production",
            "validation", "validated", "certif", "launch", "reference design", "commercial",
            "파트너", "수주", "공급", "양산", "인증", "검증",
        ))
    if theme == "발전·BESS 프로젝트":
        # Avoid broad commentary: require a concrete >=500 MW/GW-scale project or a named execution step.
        mw = [float(x.replace(",", "")) for x in re.findall(r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*mw", text, re.I)]
        gw = [float(x.replace(",", "")) * 1000 for x in re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*gw", text, re.I)]
        scale = max(mw + gw + [0])
        return scale >= 500 and any(k in text for k in (
            "approved", "selected", "studied", "interconnection", "agreement", "construction",
            "contract", "conditional", "filed", "commission", "commercial operation",
        ))
    return theme in {"FERC·대형부하 규칙", "MISO·계통접속", "ERCOT·Batch Zero"}


def collect_anchor_rows(url: str, source: str, keywords: tuple[str, ...], row_mode: bool = False) -> list[dict]:
    soup = BeautifulSoup(fetch(url).text, "html.parser")
    out = []
    if row_mode:
        containers = soup.find_all("tr")
        for row in containers:
            text = normalize(row.get_text(" "))
            low = text.lower()
            if not any(k in low for k in keywords):
                continue
            link = row.find("a", href=True)
            href = absurl(url, link.get("href")) if link else url
            theme = classify(text)
            out.append({"id": sig(source, text, href), "source": source, "title": text[:420], "url": href,
                        "official": True, "theme": theme, "summary": text[:800]})
        return out

    for link in soup.find_all("a", href=True):
        text = normalize(link.get_text(" "))
        href = absurl(url, link.get("href"))
        blob = f"{text} {href}".lower()
        if not text or not href.startswith("http") or not any(k in blob for k in keywords):
            continue
        theme = classify(blob)
        out.append({"id": sig(source, text, href), "source": source, "title": text[:420], "url": href,
                    "official": True, "theme": theme, "summary": text[:800]})
    return list({x["id"]: x for x in out}.values())


def parse_miso_eras5() -> tuple[dict, dict[str, dict]]:
    text = normalize(BeautifulSoup(fetch(MISO_ERAS5).text, "html.parser").get_text(" "))
    projects: dict[str, dict] = {}
    # Project list format: Name (Developer) – 750 megawatts (MW) of new gas generation ...
    for m in re.finditer(
        r"([A-Z][A-Za-z0-9&.' /-]{2,90}?)\s*\([^)]{2,100}\)\s*[–-]\s*([0-9,]+(?:\.[0-9]+)?)\s*(?:megawatts?\s*\(MW\)|MW)\s+of\s+new\s+([^.;]{3,80})",
        text,
        re.I,
    ):
        name = normalize(m.group(1))
        mw = float(m.group(2).replace(",", ""))
        desc = normalize(m.group(3))
        low = desc.lower()
        tech = "BESS" if "battery" in low else "가스" if "gas" in low else "태양광" if "solar" in low else "풍력" if "wind" in low else "기타"
        projects[name] = {"mw": mw, "tech": tech}

    sums = {"가스": 0.0, "BESS": 0.0, "태양광": 0.0, "풍력": 0.0, "기타": 0.0}
    for p in projects.values():
        sums[p["tech"]] = sums.get(p["tech"], 0) + p["mw"]

    metrics = {
        "cycle5_projects": len(projects) if projects else 15,
        "cycle5_mw": round(sum(p["mw"] for p in projects.values()), 1) if projects else 7297.5,
        "cycle5_gas_mw": round(sums.get("가스", 0), 1) if projects else 3692.5,
        "cycle5_bess_mw": round(sums.get("BESS", 0), 1) if projects else 2905.0,
        "cycle5_solar_mw": round(sums.get("태양광", 0), 1) if projects else 400.0,
        "cycle5_wind_mw": round(sums.get("풍력", 0), 1) if projects else 300.0,
        "program_projects": 58,
        "program_gw": 29.0,
        "gia_projects": 38,
        "gia_gw": 18.0,
        "nearing_projects": 5,
        "nearing_gw": 3.0,
    }
    patterns = {
        "program_projects": r"(\d+)\s+projects representing nearly\s+([0-9.]+)\s*GW",
        "gia_projects": r"(\d+)\s+projects representing approximately\s+([0-9.]+)\s*GW[^.]{0,100}completed generator interconnection agreements",
        "nearing_projects": r"additional\s+(\d+)\s+projects representing approximately\s+([0-9.]+)\s*GW[^.]{0,80}nearing completion",
    }
    m = re.search(patterns["program_projects"], text, re.I)
    if m:
        metrics["program_projects"], metrics["program_gw"] = int(m.group(1)), float(m.group(2))
    m = re.search(patterns["gia_projects"], text, re.I)
    if m:
        metrics["gia_projects"], metrics["gia_gw"] = int(m.group(1)), float(m.group(2))
    m = re.search(patterns["nearing_projects"], text, re.I)
    if m:
        metrics["nearing_projects"], metrics["nearing_gw"] = int(m.group(1)), float(m.group(2))
    return metrics, projects


def collect_federal_register() -> list[dict]:
    out = []
    for rto, docket in FERC_DOCKETS.items():
        try:
            url = FEDERAL_REGISTER_API + "?" + urllib.parse.urlencode({
                "per_page": 20, "order": "newest", "conditions[term]": docket,
            })
            data = fetch(url, 30).json()
            for row in data.get("results", []):
                title = normalize(f"{row.get('publication_date','')} {row.get('title','')} {row.get('abstract','')}")
                href = row.get("html_url") or row.get("pdf_url") or FERC_DECISIONS
                out.append({"id": sig("Federal Register", docket, row.get("document_number", ""), title),
                            "source": f"Federal Register/{rto}", "title": title[:420], "url": href,
                            "official": True, "theme": "FERC·대형부하 규칙", "summary": title[:800]})
        except Exception:
            continue
    return list({x["id"]: x for x in out}.values())


def collect_google_news() -> list[dict]:
    out = []
    for query in NEWS_QUERIES:
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
        try:
            root = ET.fromstring(fetch(url, 30).content)
        except Exception:
            continue
        for item in root.findall("./channel/item")[:20]:
            title = normalize(item.findtext("title") or "")
            link = normalize(item.findtext("link") or "")
            pub = normalize(item.findtext("pubDate") or "")
            source_el = item.find("source")
            source = normalize(source_el.text if source_el is not None else "")
            source_url = normalize(source_el.attrib.get("url", "") if source_el is not None else "")
            domain = domain_of(source_url)
            if not (domain_matches(domain, OFFICIAL_DOMAINS) or domain_matches(domain, TRUSTED_NEWS_DOMAINS)):
                continue
            theme = classify(title)
            official = domain_matches(domain, OFFICIAL_DOMAINS)
            candidate = {"id": sig("News", title, link), "source": source or domain, "title": title[:420],
                         "url": link, "official": official, "theme": theme, "summary": f"{title} {pub}"}
            if is_meaningful(candidate):
                out.append(candidate)
    return list({x["id"]: x for x in out}.values())


def detect_metric_changes(old: dict, metrics: dict, projects: dict) -> list[str]:
    changes = []
    oldm = old.get("miso_metrics") or {}
    for key, label, unit in (
        ("program_gw", "MISO ERAS 심사·예정 누적", "GW"),
        ("gia_gw", "MISO GIA 완료", "GW"),
        ("nearing_gw", "MISO GIA 완료 근접", "GW"),
        ("cycle5_mw", "MISO 제5차 ERAS", "MW"),
    ):
        ov, nv = oldm.get(key), metrics.get(key)
        if ov is not None and nv is not None and float(ov) != float(nv):
            changes.append(f"{label}: {ov:g}{unit} → {nv:g}{unit}")

    oldp = old.get("miso_eras_projects") or {}
    if oldp:
        for name, p in projects.items():
            if name not in oldp:
                changes.append(f"MISO ERAS 프로젝트 추가: {name} {p['mw']:g}MW")
            elif float(oldp[name].get("mw", 0)) != float(p.get("mw", 0)):
                changes.append(f"MISO ERAS 용량 변경: {name} {oldp[name].get('mw')}MW → {p.get('mw')}MW")
        for name, p in oldp.items():
            if name not in projects:
                changes.append(f"MISO ERAS 프로젝트 제외·철회 가능성: {name} {p.get('mw')}MW")
    return changes


def source_priority(item: dict) -> tuple[int, int, str]:
    theme_order = {"FERC·대형부하 규칙": 0, "MISO·계통접속": 1, "ERCOT·Batch Zero": 2, "발전·BESS 프로젝트": 3, "800V DC": 4}
    return (0 if item.get("official") else 1, theme_order.get(item.get("theme"), 9), item.get("title", ""))


OUT.mkdir(exist_ok=True)
for p in (ALERT, PENDING, STATUS):
    if p.exists():
        p.unlink()

old = load_json(STATE)
pjm = load_json(PJM_STATE)
fx, fx_source = fx_rate(old.get("last_fx_krw_per_usd"))
if fx is None:
    raise SystemExit("KRW exchange rate unavailable; refusing to send monetary alerts without KRW conversion")
fx_checked = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

errors = []
try:
    miso_metrics, miso_projects = parse_miso_eras5()
except Exception as exc:
    errors.append(f"MISO ERAS: {type(exc).__name__}")
    miso_metrics = old.get("miso_metrics") or {
        "cycle5_projects": 15, "cycle5_mw": 7297.5, "cycle5_gas_mw": 3692.5,
        "cycle5_bess_mw": 2905.0, "cycle5_solar_mw": 400.0, "cycle5_wind_mw": 300.0,
        "program_projects": 58, "program_gw": 29.0, "gia_projects": 38, "gia_gw": 18.0,
        "nearing_projects": 5, "nearing_gw": 3.0,
    }
    miso_projects = old.get("miso_eras_projects") or {}

items: list[dict] = []
for args in (
    (MISO_LARGE_LOAD, "MISO", ("eras", "zgia", "large load", "zero-injection", "zero injection", "epr"), False),
    (ERCOT_ARCHIVE, "ERCOT", ("batch zero", "large load", "data center", "data centre", "byog", "wlpun", "sb6"), True),
    (ABB_MEDIA, "ABB", ("800v", "direct current", "data center", "data centre"), False),
):
    try:
        items += collect_anchor_rows(*args)
    except Exception as exc:
        errors.append(f"{args[1]}: {type(exc).__name__}")
try:
    items += collect_federal_register()
except Exception as exc:
    errors.append(f"Federal Register: {type(exc).__name__}")
try:
    items += collect_google_news()
except Exception as exc:
    errors.append(f"News: {type(exc).__name__}")

items = [x for x in items if is_meaningful(x)]
items = list({x["id"]: x for x in items}.values())
items.sort(key=source_priority)
old_ids = set(old.get("seen_ids", []))
new_items = [x for x in items if x["id"] not in old_ids]
metric_changes = detect_metric_changes(old, miso_metrics, miso_projects)
baseline_run = not old.get("initialized")
format_upgrade = int(old.get("format_version", 0) or 0) < FORMAT_VERSION
should_alert = baseline_run or format_upgrade or bool(new_items) or bool(metric_changes)

seen = list(dict.fromkeys(list(old_ids) + [x["id"] for x in items]))[-1800:]
pending = {
    "initialized": True,
    "format_version": FORMAT_VERSION,
    "miso_metrics": miso_metrics,
    "miso_eras_projects": miso_projects,
    "seen_ids": seen,
    "last_fx_krw_per_usd": fx,
    "fx_source": fx_source,
    "fx_checked_utc": fx_checked,
    "updated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    "source_errors": errors,
}
PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

if should_alert:
    if baseline_run:
        headline = "✅ 미국 데이터센터 전력 인가 감시 확장 완료"
    elif format_upgrade and not new_items and not metric_changes:
        headline = "✅ 미국 데이터센터 전력 인가 알림 업그레이드 완료"
    else:
        headline = "🚨 미국 데이터센터 전력 인가 실행 변화"

    pjm_baseline = pjm.get("baseline") or {}
    pjm_target = pjm_baseline.get("target_mw") or 6831
    gia_rate = (float(miso_metrics.get("gia_gw", 0)) / float(miso_metrics.get("program_gw", 1)) * 100) if miso_metrics.get("program_gw") else 0

    msg = [f"<b>{h(headline)}</b>", "", "<b>⚡ 전력 인가 실행판</b>"]
    msg.append(f"• <b>PJM</b> · 신뢰도 부족 <b>{int(pjm_target):,}MW</b> → RBP·IRAS 별도 추적")
    msg.append(
        f"• <b>MISO</b> · ERAS 누적 약 <b>{miso_metrics['program_gw']:g}GW</b> → GIA 완료 약 <b>{miso_metrics['gia_gw']:g}GW</b> "
        f"(<b>{gia_rate:.1f}%</b>)"
    )
    msg.append(
        f"  ↳ 제5차 <b>{miso_metrics['cycle5_projects']}개·{miso_metrics['cycle5_mw']:,.1f}MW</b> "
        f"= 가스 {miso_metrics['cycle5_gas_mw']:,.1f}MW + BESS {miso_metrics['cycle5_bess_mw']:,.0f}MW + "
        f"태양광 {miso_metrics['cycle5_solar_mw']:,.0f}MW + 풍력 {miso_metrics['cycle5_wind_mw']:,.0f}MW"
    )
    msg.append("• <b>ERCOT</b> · Batch Zero → 조건부 분류·검증·BYOG/BYOP 실행 단계 추적")
    msg.append("• <b>FERC</b> · 6개 RTO/ISO 대형부하 접속·비용배분 규칙 동시 추적")
    msg.append("• <b>800V DC</b> · 기사량이 아니라 고객 채택·양산·수주·인증·검증만 알림")

    if metric_changes:
        msg += ["", "<b>🔄 실행 숫자 변경</b>"]
        for ch in metric_changes[:6]:
            msg.append(f"• <b>{h(ch)}</b>")

    if new_items:
        msg += ["", "<b>🆕 핵심 신규 변화</b>"]
        official_count = sum(1 for x in new_items if x.get("official"))
        msg.append(f"• 새 자료 <b>{len(new_items)}건</b> · 공식 <b>{official_count}건</b> · 신뢰보도 <b>{len(new_items)-official_count}건</b>")
        chosen = []
        used_theme = set()
        # Show at most one per theme first, then fill to five with highest-priority extras.
        for x in new_items:
            if x.get("theme") in used_theme:
                continue
            used_theme.add(x.get("theme"))
            chosen.append(x)
            if len(chosen) >= 5:
                break
        if len(chosen) < 5:
            for x in new_items:
                if x in chosen:
                    continue
                chosen.append(x)
                if len(chosen) >= 5:
                    break
        for x in chosen:
            src = clean_source(x.get("source", ""), x.get("url", ""))
            badge = "공식" if x.get("official") else "보도"
            ko = translate_title(x.get("title", ""), x.get("theme", "기타"), src)
            ko = ko[:180].rstrip() + ("…" if len(ko) > 180 else "")
            krw_note = money_suffix_from_title(x.get("title", ""), fx)
            msg.append(f"• <b>{h(x.get('theme','기타'))}</b> · [{badge}] {h(src)}")
            msg.append(f"  ↳ 🔗 {a(ko, x.get('url',''))}{h(krw_note)}")
        if len(new_items) > len(chosen):
            msg.append(f"• <i>나머지 {len(new_items)-len(chosen)}건은 중복방지 상태에 저장해 다음 변화 판정에 반영합니다.</i>")
    elif baseline_run:
        msg += ["", "<b>👀 새 감시 범위</b>"]
        msg.append("• FERC 6개 전력시장 대형부하 규칙·비용배분·공동입지 발전")
        msg.append("• MISO ERAS·ZGIA/Zero Injection·GIA·상업운전 일정")
        msg.append("• ERCOT Batch Zero·BYOG/WLPUN·검증·대형부하 감축 규칙")
        msg.append("• 500MW 이상 데이터센터 연계 발전·BESS 프로젝트의 심사→계약→착공→상업운전")
        msg.append("• 800V DC는 고객 채택·수주·양산·인증 단계 전환만 알림")

    msg += ["", "<b>📊 투자 해석</b>"]
    msg.append("• <b>핵심 순서:</b> 계획 MW → 심사 MW → 계통연계계약(GIA) MW → 착공 MW → 상업운전 MW")
    msg.append("• 발표 용량이 늘어도 GIA·착공·전원 인가로 내려오지 않으면 실적 전환으로 보지 않습니다.")
    msg.append("• 500MW 이상 신규·취소·용량 변경과 단계 전환을 우선 알리고, 단순 재인용·의견기사는 제외합니다.")
    msg.append("• 발전·BESS와 부하 위치가 다르면 변전소·송전선 비용이 다음 병목인지 함께 봅니다.")

    msg += ["", "<b>💱 환율</b>"]
    msg.append(f"• <b>1달러 = {fx:,.2f}원</b> · {h(fx_source)} · {h(fx_checked)} UTC")
    msg.append("• 외화 금액이 확인되면 같은 줄에 원화 환산을 붙입니다.")

    msg += ["", "<b>🔗 공식 원문</b>"]
    msg.append(f"• {a('FERC 6개 전력시장 대형부하 개편', FERC_LARGE_LOAD)}")
    msg.append(f"• {a('MISO 대형부하·신속 계통접속', MISO_LARGE_LOAD)}")
    msg.append(f"• {a('MISO 제5차 ERAS 7.3GW', MISO_ERAS5)}")
    msg.append(f"• {a('ERCOT 대형부하 Batch Zero', ERCOT_LARGE_LOAD)}")

    text = "\n".join(msg)
    # Telegram limit is 4096 characters after entity parsing. Preserve the dashboard and interpretation;
    # trim excess source rows if translation makes a rare alert too long.
    visible = re.sub(r"<[^>]+>", "", text)
    if len(visible) > 3900 and new_items:
        # Rebuild with first 3 linked items by removing source rows after the third pair.
        lines = text.splitlines()
        out_lines = []
        source_pairs = 0
        skip_next = False
        for line in lines:
            if line.startswith("• <b>") and " · [" in line and source_pairs >= 3:
                skip_next = True
                continue
            if skip_next and line.startswith("  ↳ 🔗"):
                skip_next = False
                continue
            if line.startswith("• <b>") and " · [" in line:
                source_pairs += 1
            out_lines.append(line)
        text = "\n".join(out_lines)
    ALERT.write_text(text.strip() + "\n", encoding="utf-8")

STATUS.write_text(
    "# 미국 데이터센터 전력 인가 실행 감시\n\n"
    f"- 형식 버전: **{FORMAT_VERSION}**\n"
    f"- MISO ERAS 누적: **{miso_metrics.get('program_gw')} GW / {miso_metrics.get('program_projects')}개**\n"
    f"- MISO GIA 완료: **{miso_metrics.get('gia_gw')} GW / {miso_metrics.get('gia_projects')}개**\n"
    f"- MISO 제5차: **{miso_metrics.get('cycle5_mw')} MW / {miso_metrics.get('cycle5_projects')}개**\n"
    f"- 신규 의미자료: **{len(new_items)}건**\n"
    f"- 숫자 변경: **{len(metric_changes)}건**\n"
    f"- 알림: **{'예' if should_alert else '아니오'}**\n"
    f"- 원천 오류: **{'; '.join(errors) if errors else '없음'}**\n",
    encoding="utf-8",
)
print(
    f"time_to_power format={FORMAT_VERSION} miso={miso_metrics.get('program_gw')}GW "
    f"gia={miso_metrics.get('gia_gw')}GW new={len(new_items)} changes={len(metric_changes)} alert={should_alert}"
)
