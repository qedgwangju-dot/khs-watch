#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

OUT = Path("out")
STATE = Path("data/us_data_center_cancellation_risk_state.json")
ALERT = OUT / "us_data_center_cancellation_risk_alert.txt"
PENDING = OUT / "us_data_center_cancellation_risk_pending_state.json"
STATUS = OUT / "us_data_center_cancellation_risk_status.md"

DCK_RIPPLE = "https://www.datacenterknowledge.com/energy-power-supply/the-ripple-effect-of-data-center-project-cancellations-and-delays"
CAPGEMINI = "https://www.capgemini.com/insights/research-library/data-centers-and-electricity-demand/"
FERC_LARGE_LOAD = "https://www.ferc.gov/news-events/news/ferc-launches-aggressive-targeted-action-speed-large-load-integration"
FERC_ROSNER = "https://www.ferc.gov/news-events/news/commissioner-rosners-remarks-large-load-show-cause-orders-e-7-e-12-june-18-2026"
FERC_PJM_COST = "https://www.ferc.gov/news-events/news/commissioner-changs-concurrence-transmission-security-agreement-between-peco"

# Verified reference points. The restudy duration is an industry-experience range
# quoted by Data Center Knowledge, not a statutory nationwide deadline.
BASELINE = {
    "phantom_load_pct": 19.0,
    "restudy_min_months": 6,
    "restudy_one_year_plus": True,
    "pjm_2024_dc_transmission_projects": 130,
    "pjm_2024_dc_transmission_usd_b": 4.3,
    "cost_recovery_agreement": True,
    "escalating_readiness_requirements": True,
}

TRUSTED_DOMAINS = (
    "ferc.gov", "federalregister.gov", "pjm.com", "capgemini.com",
    "datacenterknowledge.com", "reuters.com", "utilitydive.com", "rtoinsider.com",
    "datacenterdynamics.com", "publicpower.org", "bisnow.com",
)

NEWS_QUERIES = (
    'data center project cancellation delay interconnection restudy stranded cost utility',
    'data center cost recovery agreement FERC large load readiness financial security site control',
    'data center phantom load forecast utility cancellation transmission substation',
    'data center restudy interconnection capacity reassignment queue delay',
    'hyperscale data center withdraw cancel delay transmission utility project',
)

HEADERS = {"User-Agent": "khs-watch/1.0 (+https://github.com/qedgwangju-dot/khs-watch)"}
FORMAT_VERSION = 1
NEWS_ALERT_MAX_AGE_DAYS = 7
SEEN_ID_LIMIT = 5000


def fetch(url: str, timeout: int = 25):
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


def krw_from_usd(usd: float, fx: float) -> str:
    eok = round(usd * fx / 100_000_000)
    jo, rem = divmod(eok, 10000)
    if jo and rem:
        return f"약 {jo:,}조 {rem:,}억원"
    if jo:
        return f"약 {jo:,}조원"
    return f"약 {rem:,}억원"


def dollar_values(text: str) -> list[float]:
    low = (text or "").lower().replace(",", "")
    vals = []
    pats = (
        (r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*(?:billion|bn|b)\b", 1e9),
        (r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*(?:million|mn|m)\b", 1e6),
    )
    for pat, mult in pats:
        for m in re.finditer(pat, low, re.I):
            try:
                vals.append(float(m.group(1)) * mult)
            except Exception:
                pass
    return vals


def money_suffix(text: str, fx: float) -> str:
    vals = dollar_values(text)
    if not vals:
        return ""
    return " · " + ", ".join(krw_from_usd(v, fx) for v in vals[:2])


def extract_scale_mw(text: str) -> float:
    low = (text or "").lower().replace(",", "")
    vals = []
    vals += [float(x) for x in re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*mw", low)]
    vals += [float(x) * 1000 for x in re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*gw", low)]
    return max(vals + [0.0])


def extract_percent(text: str) -> float:
    vals = []
    for x in re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*%", text or ""):
        try:
            vals.append(float(x))
        except Exception:
            pass
    return max(vals + [0.0])


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


def source_label(source: str, url: str = "") -> str:
    s = f"{source} {domain_of(url)}".lower()
    mapping = (
        ("ferc", "FERC"), ("federal register", "미국 연방관보"), ("pjm", "PJM"),
        ("capgemini", "Capgemini"), ("datacenterknowledge", "Data Center Knowledge"),
        ("reuters", "Reuters"), ("utilitydive", "Utility Dive"),
        ("rtoinsider", "RTO Insider"), ("datacenterdynamics", "Data Center Dynamics"),
        ("publicpower", "Public Power"), ("bisnow", "Bisnow"),
    )
    for key, label in mapping:
        if key in s:
            return label
    return normalize(source)[:40] or domain_of(url)[:40]


def classify(text: str) -> str:
    low = (text or "").lower()
    if any(k in low for k in ("cost recovery agreement", "transmission security agreement", "financial security", "site control", "readiness requirement")):
        return "비용보호·준비도 규칙"
    if any(k in low for k in ("phantom load", "speculative load", "duplicate request", "double counting", "load forecast")):
        return "Phantom load·수요전망"
    if any(k in low for k in ("restudy", "re-study", "reassign", "reassignment", "fresh study", "new study")):
        return "재심사·접속승계"
    if any(k in low for k in ("stranded", "rate base", "cost allocation", "sunk cost", "deposit", "clawback")):
        return "매몰·송전비용"
    if any(k in low for k in ("cancel", "cancelled", "canceled", "withdraw", "walk away", "abandon", "delay", "postpone", "suspend")):
        return "프로젝트 취소·지연"
    return "기타"


def is_meaningful(title: str, source: str, domain: str) -> bool:
    low = f"{title} {source}".lower()
    theme = classify(low)
    if theme == "기타":
        return False

    official = domain.endswith("ferc.gov") or domain.endswith("federalregister.gov") or domain.endswith("pjm.com")
    if official and theme in {"비용보호·준비도 규칙", "Phantom load·수요전망", "매몰·송전비용", "재심사·접속승계"}:
        return True

    dc_context = any(k in low for k in ("data center", "data centre", "hyperscale", "large load", "ai campus", "ai factory"))
    if not dc_context:
        return False

    if theme == "프로젝트 취소·지연":
        scale = extract_scale_mw(low)
        money = max(dollar_values(low) + [0.0])
        # Prefer large projects; trusted specialist outlets may omit MW in the headline.
        return scale >= 250 or money >= 100e6 or domain in {
            "datacenterknowledge.com", "reuters.com", "utilitydive.com", "rtoinsider.com", "bisnow.com"
        }
    if theme == "재심사·접속승계":
        return True
    if theme == "매몰·송전비용":
        money = max(dollar_values(low) + [0.0])
        return money >= 100e6 or any(k in low for k in ("stranded", "rate base", "cost allocation"))
    if theme == "Phantom load·수요전망":
        return extract_percent(low) >= 10 or extract_scale_mw(low) >= 1000 or "phantom load" in low
    if theme == "비용보호·준비도 규칙":
        return True
    return False


def translate_title(text: str, theme: str, source: str) -> str:
    clean = normalize(html.unescape(text))
    # Strip common source suffix from Google News title.
    clean = re.sub(r"\s+-\s+[^-]{2,80}$", "", clean).strip()
    if has_korean(clean):
        return clean
    out = translate_google(clean)
    if out:
        replacements = {
            "데이터 센터": "데이터센터",
            "대규모 부하": "대형부하",
            "재 연구": "재심사",
            "재연구": "재심사",
            "좌초 비용": "매몰비용",
            "그리드": "전력망",
        }
        for old, new in replacements.items():
            out = out.replace(old, new)
        return out
    labels = {
        "프로젝트 취소·지연": "대형 데이터센터 프로젝트 취소·지연 관련 신규 자료",
        "재심사·접속승계": "데이터센터 계통연계 재심사·접속승계 관련 신규 자료",
        "매몰·송전비용": "데이터센터 매몰비용·송전비용 관련 신규 자료",
        "Phantom load·수요전망": "데이터센터 Phantom load·수요전망 관련 신규 자료",
        "비용보호·준비도 규칙": "대형부하 비용보호·준비도 규칙 관련 신규 자료",
    }
    return f"{source} · {labels.get(theme, '데이터센터 취소·지연 위험 관련 신규 자료')}"


def collect_news() -> list[dict]:
    out = []
    for query in NEWS_QUERIES:
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({
            "q": query, "hl": "en-US", "gl": "US", "ceid": "US:en",
        })
        try:
            root = ET.fromstring(fetch(url, 25).content)
        except Exception:
            continue
        for item in root.findall("./channel/item")[:25]:
            title = normalize(item.findtext("title") or "")
            link = normalize(item.findtext("link") or "")
            pub = normalize(item.findtext("pubDate") or "")
            if not pub:
                continue
            try:
                published = parsedate_to_datetime(pub)
                if published.tzinfo is None:
                    published = published.replace(tzinfo=dt.timezone.utc)
                if published.astimezone(dt.timezone.utc) < dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=NEWS_ALERT_MAX_AGE_DAYS):
                    continue
            except Exception:
                continue
            source_el = item.find("source")
            source = normalize(source_el.text if source_el is not None else "")
            source_url = normalize(source_el.attrib.get("url", "") if source_el is not None else "")
            domain = domain_of(source_url)
            if not trusted(domain):
                continue
            if not is_meaningful(title, source, domain):
                continue
            theme = classify(f"{title} {source}")
            out.append({
                "id": sig(title, link),
                "title": title,
                "url": link,
                "source": source_label(source, source_url),
                "theme": theme,
                "published": pub,
                "scale_mw": extract_scale_mw(title),
            })
    return list({x["id"]: x for x in out}.values())


def source_priority(item: dict) -> tuple[int, int, str]:
    src = item.get("source", "")
    official = 0 if src in {"FERC", "미국 연방관보", "PJM", "Capgemini"} else 1
    theme_order = {
        "프로젝트 취소·지연": 0,
        "재심사·접속승계": 1,
        "매몰·송전비용": 2,
        "비용보호·준비도 규칙": 3,
        "Phantom load·수요전망": 4,
    }
    return official, theme_order.get(item.get("theme"), 9), item.get("title", "")


OUT.mkdir(exist_ok=True)
for p in (ALERT, PENDING, STATUS):
    if p.exists():
        p.unlink()

old = load_json(STATE)
fx, fx_source = fx_rate(old.get("last_fx_krw_per_usd"))
if fx is None:
    raise SystemExit("KRW exchange rate unavailable; refusing to send monetary alerts without KRW conversion")
fx_checked = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

items = collect_news()
items.sort(key=source_priority)
old_seen = list(old.get("seen_ids", []))
old_ids = set(old_seen)
new_items = [x for x in items if x["id"] not in old_ids]
baseline_run = not old.get("initialized")
format_upgrade = int(old.get("format_version", 0) or 0) < FORMAT_VERSION
should_alert = baseline_run or format_upgrade or bool(new_items)

seen = list(dict.fromkeys(old_seen + [x["id"] for x in items]))[-SEEN_ID_LIMIT:]
pending = {
    "initialized": True,
    "format_version": FORMAT_VERSION,
    "baseline": BASELINE,
    "seen_ids": seen,
    "last_fx_krw_per_usd": fx,
    "fx_source": fx_source,
    "fx_checked_utc": fx_checked,
    "updated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
}
PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

if should_alert:
    if baseline_run:
        headline = "✅ 미국 데이터센터 취소·지연·계통비용 위험 감시 시작"
    else:
        headline = "⚠️ 미국 데이터센터 취소·지연·계통비용 변화"

    msg = [f"<b>{h(headline)}</b>", ""]

    if baseline_run:
        pjm_cost_krw = krw_from_usd(BASELINE["pjm_2024_dc_transmission_usd_b"] * 1e9, fx)
        threshold_krw = krw_from_usd(100e6, fx)
        msg += ["<b>🧭 한눈에</b>"]
        msg.append("• 핵심 위험 │ 데이터센터가 취소돼도 전력망 비용과 재심사 시간이 그대로 남을 수 있음")
        msg.append("• 판단 기준 │ 취소 건수보다 매몰비용·재심사·비용부담 주체·후속 프로젝트 전환시간을 우선")

        msg += ["", "<b>⚠️ 기준 위험판</b>"]
        msg.append(f"• Phantom load │ 전력요청의 약 <b>{BASELINE['phantom_load_pct']:.0f}%</b>가 실제 부하로 이어지지 않을 수 있음")
        msg.append("• 재심사 │ 산업 경험상 <b>6개월~1년 이상</b> 걸릴 수 있음 · 전국 공통 법정기간은 아님")
        msg.append(
            f"• PJM 2024 데이터센터 송전사업 │ <b>{BASELINE['pjm_2024_dc_transmission_projects']}건 · "
            f"43억달러 = {h(pjm_cost_krw)}</b>"
        )
        msg.append("• FERC │ Cost Recovery Agreement + 단계별 준비도 요건으로 소비자 비용전가·중복신청 방지 추진")

        msg += ["", "<b>🔔 알림 조건</b>"]
        msg.append("• 250MW 이상 대형 프로젝트 취소·대규모 지연·축소")
        msg.append("• 후속 프로젝트가 기존 접속을 승계하지 못하고 재심사에 들어간 사실이 확인될 때")
        msg.append(f"• 매몰·송전·변전 비용이 <b>1억달러 = {h(threshold_krw)}</b> 이상 확인될 때")
        msg.append("• FERC·RTO·주 규제기관의 Cost Recovery Agreement·준비도·site control·금융보증 규칙 변경")
        msg.append("• Phantom load 제거로 공식 수요전망이 10% 이상 또는 1GW 이상 하향될 때")
    else:
        msg += ["<b>🧭 한눈에</b>"]
        if new_items:
            first = new_items[0]
            src = first.get("source", "")
            title_ko = translate_title(first.get("title", ""), first.get("theme", "기타"), src)
            msg.append(f"• 이번 핵심 변화 │ {a(title_ko, first.get('url',''))}")
        msg.append("• 판단 기준 │ 취소 → stranded cost → restudy → 추가 CAPEX·금융비용 → IRR 악화 경로 확인")

    if new_items:
        msg += ["", "<b>🆕 핵심 신규 변화</b>"]
        chosen = []
        used_theme = set()
        for item in new_items:
            theme = item.get("theme")
            if theme in used_theme:
                continue
            chosen.append(item)
            used_theme.add(theme)
            if len(chosen) >= 5:
                break
        if len(chosen) < 5:
            for item in new_items:
                if item in chosen:
                    continue
                chosen.append(item)
                if len(chosen) >= 5:
                    break
        for idx, item in enumerate(chosen, 1):
            src = item.get("source", "")
            theme = item.get("theme", "기타")
            title_ko = translate_title(item.get("title", ""), theme, src)
            suffix = money_suffix(item.get("title", ""), fx)
            msg.append(f"{idx}. {a(title_ko, item.get('url',''))}{h(suffix)}")
            msg.append(f"   {h(theme)} · {h(src)}")
        if len(new_items) > len(chosen):
            msg.append(f"• 나머지 {len(new_items)-len(chosen)}건은 중복·추적 상태에 저장해 다음 변화 판정에 반영")

    msg += ["", "<b>📊 투자 판단</b>"]
    msg.append("• 실행률 │ 신청 MW보다 보증금·부지·전력계약·송전착공·실제 데이터센터 착공·전원 인가 MW를 우선")
    msg.append("• 비용 │ 개발사 매몰비용과 유틸리티 송전·변전 투자비를 분리해 확인")
    msg.append("• 후속사업자 │ 같은 부지라도 부하규모·접속점·가동시점이 달라지면 재심사 가능성을 확인")
    msg.append("• 조기경보 │ 대형 취소→restudy 증가→COD 지연→금융비용 상승이 연속으로 나타나는지 추적")

    msg += ["", "<b>💱 환율</b>"]
    msg.append(f"• <b>1달러 = {fx:,.2f}원</b> │ {h(fx_source)} │ {h(fx_checked)} UTC")
    msg.append("• 외화 금액은 확인되는 즉시 같은 줄에 원화 환산")

    msg += ["", "<b>🔗 기준 원문</b>"]
    msg.append(f"• {a('Data Center Knowledge · 취소·지연 파급효과', DCK_RIPPLE)}")
    msg.append(f"• {a('Capgemini · Phantom load 19% 기준', CAPGEMINI)}")
    msg.append(f"• {a('FERC · 대형부하 Cost Recovery·준비도 개편', FERC_LARGE_LOAD)}")
    msg.append(f"• {a('FERC · Cost Recovery Agreement 설명', FERC_ROSNER)}")

    ALERT.write_text("\n".join(msg).strip() + "\n", encoding="utf-8")

STATUS.write_text(
    "# 미국 데이터센터 취소·지연·계통비용 위험 감시\n\n"
    f"- Phantom load 기준: **{BASELINE['phantom_load_pct']}%**\n"
    f"- 재심사 기준: **{BASELINE['restudy_min_months']}개월~1년 이상(산업 경험치)**\n"
    f"- PJM 2024 DC 송전사업: **{BASELINE['pjm_2024_dc_transmission_projects']}건 / ${BASELINE['pjm_2024_dc_transmission_usd_b']}B**\n"
    f"- 신규 의미자료: **{len(new_items)}건**\n"
    f"- 알림: **{'예' if should_alert else '아니오'}**\n",
    encoding="utf-8",
)
print(
    f"cancellation_risk baseline={BASELINE['phantom_load_pct']}% "
    f"new={len(new_items)} alert={should_alert}"
)
