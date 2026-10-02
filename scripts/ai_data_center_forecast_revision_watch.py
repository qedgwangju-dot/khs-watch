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
STATE = Path("data/ai_data_center_forecast_revision_state.json")
ALERT = OUT / "ai_data_center_forecast_revision_alert.txt"
PENDING = OUT / "ai_data_center_forecast_revision_pending_state.json"
STATUS = OUT / "ai_data_center_forecast_revision_status.md"

GS_URL = "https://www.goldmansachs.com/insights/goldman-sachs-exchanges/the-outlook-for-data-center-power-demand-as-ai-token-use-grows"
MS_URL = "https://finance.yahoo.com/technology/ai/articles/morgan-stanley-warns-gpu-improvements-225257440.html"
BOFA_URL = "https://finance.yahoo.com/markets/stocks/article/ai-spending-will-fuel-wins-for-micron-nvidia-intel-and-other-chip-stocks-bofa-analyst-193925832.html"

BASELINE = {
    "Goldman Sachs": {
        "global_power_growth_2025_2030_pct": 170.0,
        "us_2030_power_gw": 108.0,
        "us_prior_2030_power_gw": 83.0,
        "btm_gas_capacity_2030_gw": 30.0,
        "btm_power_delivery_2030_gw": 20.0,
        "source": GS_URL,
    },
    "Morgan Stanley": {
        "us_it_power_2025_gw": 9.19,
        "us_it_power_2026_gw": 17.96,
        "us_it_power_2027_gw": 35.46,
        "us_it_power_2028_gw": 52.31,
        "us_it_power_2029_gw": 78.57,
        "new_power_need_2026_2028_gw": 97.0,
        "under_construction_gw": 21.0,
        "available_grid_gw": 19.0,
        "initial_shortfall_gw": 57.0,
        "alternative_supply_gw": 24.0,
        "residual_shortfall_gw": 33.0,
        "source": MS_URL,
    },
    "BofA": {
        "ai_dc_system_tam_2030_usd_t": 2.2,
        "prior_ai_dc_system_tam_usd_t": 1.8,
        "tam_cagr_pct": 40.0,
        "prior_tam_cagr_pct": 33.0,
        "cloud_capex_2026_usd_t": 1.0,
        "cloud_capex_2027_usd_t": 1.4,
        "cloud_capex_2030_low_usd_t": 2.0,
        "cloud_capex_2030_high_usd_t": 3.0,
        "server_cpu_tam_2030_usd_b": 210.0,
        "source": BOFA_URL,
    },
}

TRUSTED = (
    "goldmansachs.com", "finance.yahoo.com", "investing.com", "reuters.com",
    "cnbc.com", "datacenterdynamics.com", "bloomberg.com", "bloombergtax.com",
)
QUERIES = (
    '"Morgan Stanley" data center power demand forecast GW AI',
    '"Goldman Sachs" data center power demand forecast 2030 GW',
    '"BofA" AI data center systems TAM forecast 2030',
    '"Bank of America" AI data center capex forecast 2030',
)
HEADERS = {"User-Agent": "Mozilla/5.0 KHS-AI-DC-Forecast-Watch/1.0"}
FORMAT_VERSION = 1
SEEN_LIMIT = 2000
MAX_AGE_DAYS = 10


def fetch(url: str, timeout: int = 30):
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def domain(url: str) -> str:
    return urllib.parse.urlparse(url or "").netloc.lower().replace("www.", "")


def trusted(d: str) -> bool:
    return any(d == x or d.endswith("." + x) for x in TRUSTED)


def sig(*parts: str) -> str:
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:20]


def h(s) -> str:
    return html.escape(str(s), quote=True)


def a(label: str, url: str) -> str:
    return f'<a href="{h(url)}">{h(label)}</a>'


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def fx_rate(old=None):
    sources = (
        ("https://api.frankfurter.dev/v2/rates?base=USD&quotes=KRW&providers=ECB", "ECB/Frankfurter"),
        ("https://open.er-api.com/v6/latest/USD", "ExchangeRate-API"),
    )
    for url, name in sources:
        try:
            data = fetch(url, 15).json()
            if isinstance(data, list):
                row = next((x for x in data if x.get("quote") == "KRW"), None)
                value = float(row["rate"]) if row else None
            else:
                value = float((data.get("rates") or {}).get("KRW"))
            if value and 500 < value < 3000:
                return value, name
        except Exception:
            pass
    if old:
        return float(old), "직전 저장값"
    return None, "조회 실패"


def krw_from_usd_b(value_b: float, fx: float) -> str:
    eok = round(value_b * 1e9 * fx / 1e8)
    jo, rem = divmod(eok, 10000)
    if jo and rem:
        return f"약 {jo:,}조 {rem:,}억원"
    if jo:
        return f"약 {jo:,}조원"
    return f"약 {rem:,}억원"


def ko_title(text: str) -> str:
    text = norm(text)
    try:
        params = {"client": "gtx", "sl": "auto", "tl": "ko", "dt": "t", "q": text}
        data = fetch("https://translate.googleapis.com/translate_a/single?" + urllib.parse.urlencode(params), 15).json()
        out = norm("".join(seg[0] for seg in (data[0] or []) if isinstance(seg, list) and seg and isinstance(seg[0], str)))
        if re.search(r"[가-힣]", out):
            return out.replace("데이터 센터", "데이터센터")
    except Exception:
        pass
    return "AI 데이터센터 수요·전력·설비투자 전망 변경 관련 신규 자료"


def bank_of(text: str) -> str | None:
    low = text.lower()
    if "morgan stanley" in low:
        return "Morgan Stanley"
    if "goldman" in low:
        return "Goldman Sachs"
    if "bofa" in low or "bank of america" in low:
        return "BofA"
    return None


def meaningful_title(title: str) -> bool:
    low = title.lower()
    if not bank_of(low):
        return False
    if not any(x in low for x in ("data center", "data centre", "ai infrastructure", "server cpu", "power demand", "capex", "tam")):
        return False
    return any(x in low for x in (
        "raise", "raises", "raised", "lift", "lifts", "upgrade", "upgrades",
        "cut", "cuts", "lower", "lowers", "revise", "revises", "forecast",
        "outlook", "tam", "power demand", "capex",
    ))


def collect_news() -> list[dict]:
    out = []
    now = dt.datetime.now(dt.timezone.utc)
    for query in QUERIES:
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({
            "q": query, "hl": "en-US", "gl": "US", "ceid": "US:en",
        })
        try:
            root = ET.fromstring(fetch(url, 25).content)
        except Exception:
            continue
        for item in root.findall("./channel/item")[:30]:
            title = norm(item.findtext("title") or "")
            link = norm(item.findtext("link") or "")
            pub = norm(item.findtext("pubDate") or "")
            src_el = item.find("source")
            src = norm(src_el.text if src_el is not None else "")
            src_url = norm(src_el.attrib.get("url", "") if src_el is not None else "")
            d = domain(src_url)
            if not trusted(d) or not meaningful_title(title):
                continue
            try:
                published = parsedate_to_datetime(pub)
                if published.tzinfo is None:
                    published = published.replace(tzinfo=dt.timezone.utc)
                if published.astimezone(dt.timezone.utc) < now - dt.timedelta(days=MAX_AGE_DAYS):
                    continue
            except Exception:
                continue
            out.append({
                "id": sig(title, link),
                "bank": bank_of(title) or "확인 필요",
                "title": title,
                "url": link,
                "source": src or d,
                "published": pub,
            })
    return list({x["id"]: x for x in out}.values())


OUT.mkdir(exist_ok=True)
for p in (ALERT, PENDING, STATUS):
    p.unlink(missing_ok=True)

old = load_state()
fx, fx_source = fx_rate(old.get("last_fx"))
if fx is None:
    raise SystemExit("달러/원 환율을 확보하지 못해 전망 변경 알림을 보내지 않습니다.")

items = collect_news()
old_seen = set(old.get("seen_ids", []))
fresh = [x for x in items if x["id"] not in old_seen]
first = not old.get("initialized")
format_upgrade = int(old.get("format_version", 0) or 0) < FORMAT_VERSION
should_alert = first or format_upgrade or bool(fresh)

seen = list(dict.fromkeys(list(old_seen) + [x["id"] for x in items]))[-SEEN_LIMIT:]
pending = {
    "initialized": True,
    "format_version": FORMAT_VERSION,
    "baseline": BASELINE,
    "seen_ids": seen,
    "last_fx": fx,
    "fx_source": fx_source,
    "updated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
}
PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

if should_alert:
    headline = "✅ AI 데이터센터 전망 수정 감시 연결 완료" if first else "🚨 AI 데이터센터 핵심 전망 변경"
    msg = [f"<b>{headline}</b>", "", "<b>🧭 현재 기준선</b>"]

    gs = BASELINE["Goldman Sachs"]
    msg.append(f"• Goldman Sachs │ 2030 미국 데이터센터 전력 <b>{gs['us_2030_power_gw']:g}GW</b> · 2025→2030 글로벌 전력수요 <b>+{gs['global_power_growth_2025_2030_pct']:g}%</b>")
    msg.append(f"  ↳ 기존 미국 전망 {gs['us_prior_2030_power_gw']:g}GW → {gs['us_2030_power_gw']:g}GW")
    msg.append(f"  ↳ 2030 현장 가스발전 {gs['btm_gas_capacity_2030_gw']:g}GW · 실제 전력공급 {gs['btm_power_delivery_2030_gw']:g}GW+")

    ms = BASELINE["Morgan Stanley"]
    msg.append(f"• Morgan Stanley │ 미국 IT 전력 2025 {ms['us_it_power_2025_gw']:g}GW → 2029 <b>{ms['us_it_power_2029_gw']:g}GW</b>")
    msg.append(f"  ↳ 2026~2028 신규 필요 {ms['new_power_need_2026_2028_gw']:g}GW · 초기 부족 {ms['initial_shortfall_gw']:g}GW · 대체전원 반영 후 <b>{ms['residual_shortfall_gw']:g}GW</b>")

    bf = BASELINE["BofA"]
    tam_krw = krw_from_usd_b(bf["ai_dc_system_tam_2030_usd_t"] * 1000, fx)
    capex_krw = krw_from_usd_b(bf["cloud_capex_2027_usd_t"] * 1000, fx)
    msg.append(f"• BofA │ 2030 AI 데이터센터 시스템 시장 <b>{bf['ai_dc_system_tam_2030_usd_t']:g}조달러 = {h(tam_krw)}</b>")
    msg.append(f"  ↳ 기존 {bf['prior_ai_dc_system_tam_usd_t']:g}조달러·연 {bf['prior_tam_cagr_pct']:g}% → {bf['ai_dc_system_tam_2030_usd_t']:g}조달러·연 {bf['tam_cagr_pct']:g}%")
    msg.append(f"  ↳ 2027 클라우드 설비투자 {bf['cloud_capex_2027_usd_t']:g}조달러 = {h(capex_krw)}")

    if fresh:
        msg += ["", "<b>🆕 새 전망 변경 기사</b>"]
        for idx, x in enumerate(fresh[:6], 1):
            msg.append(f"{idx}. {a(ko_title(x['title']), x['url'])}")
            msg.append(f"   {h(x['bank'])} · {h(x['source'])}")
        if len(fresh) > 6:
            msg.append(f"• 나머지 {len(fresh)-6}건은 중복방지 상태에 저장")

    msg += ["", "<b>🔔 앞으로 별도 알림하는 경우</b>"]
    msg.append("• 전력수요·설비투자·시스템 시장 전망이 기존치 대비 약 10% 이상 상향·하향")
    msg.append("• 전력 부족분·현장발전(BTM)·계통접속 전망이 크게 바뀔 때")
    msg.append("• 서버 CPU·가속기·네트워크 시장 전망이 구조적으로 상향·하향될 때")
    msg.append("• 동일 숫자 재인용이나 단순 목표주가 변경은 이 알림에서 제외")

    msg += ["", "<b>📊 투자 해석</b>"]
    msg.append("• 이 알림은 실제 수주가 아니라 미래 시장 분모 변경을 잡습니다.")
    msg.append("• 실제 매출 확인은 기존 전력·착공·전원인가·발전설비 감시에서 별도로 검증합니다.")
    msg.append("• 전망 상향만 있고 수주잔고·가동률·매출이 따라오지 않으면 기대감으로 낮춰 봅니다.")

    msg += ["", "<b>💱 환율</b>"]
    msg.append(f"• 1달러 = <b>{fx:,.2f}원</b> │ {h(fx_source)}")
    msg.append("• 외화 전망은 알림 시점 환율로 원화 환산")

    msg += ["", "<b>🔗 기준 원문</b>"]
    msg.append(f"• {a('Goldman Sachs 전력수요 전망', GS_URL)}")
    msg.append(f"• {a('Morgan Stanley 전력부족 전망 보도', MS_URL)}")
    msg.append(f"• {a('BofA AI 데이터센터 시장 전망 보도', BOFA_URL)}")

    ALERT.write_text("\n".join(msg).strip() + "\n", encoding="utf-8")

STATUS.write_text(
    "# AI 데이터센터 전망 수정 감시\n\n"
    f"- Goldman Sachs 2030 미국 전력: **{BASELINE['Goldman Sachs']['us_2030_power_gw']}GW**\n"
    f"- Morgan Stanley 2029 IT 전력: **{BASELINE['Morgan Stanley']['us_it_power_2029_gw']}GW**\n"
    f"- Morgan Stanley 2026~28 잔여 부족: **{BASELINE['Morgan Stanley']['residual_shortfall_gw']}GW**\n"
    f"- BofA 2030 시스템 TAM: **{BASELINE['BofA']['ai_dc_system_tam_2030_usd_t']}조달러**\n"
    f"- 신규 전망 기사: **{len(fresh)}건**\n"
    f"- 알림: **{'예' if should_alert else '아니오'}**\n",
    encoding="utf-8",
)
print(f"forecast_watch new={len(fresh)} alert={should_alert}")
