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
except Exception:  # pragma: no cover
    gnewsdecoder = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "rubin_hbm_watch_state.json"
PENDING_PATH = ROOT / "out" / "rubin_hbm_pending_state.json"
ALERT_PATH = ROOT / "out" / "rubin_hbm_alert.md"

UA = "Mozilla/5.0 (compatible; khs-watch/4.0; +https://github.com/qedgwangju-dot/khs-watch)"

BASELINE = {
    "as_of": "2026-09-23",
    "company": "삼성전기",
    "source_kind": "메리츠증권 전망 + 삼성전기 공식 실적/계약 교차검증",
    "metrics": {
        "q3_revenue_forecast_krw_100m": 38200.0,
        "q3_operating_profit_forecast_krw_100m": 6571.0,
        "q3_consensus_operating_profit_krw_100m": 6010.0,
        "q3_implied_opm_pct": 6571.0 / 38200.0 * 100.0,
        "component_opm_floor_pct": 20.0,
        "abf_opm_floor_pct": 30.0,
        "cpu_abf_share_floor_pct": 45.0,
        "q2_revenue_actual_krw_100m": 34572.0,
        "q2_operating_profit_actual_krw_100m": 4404.0,
        "q2_component_revenue_krw_100m": 16494.0,
        "q2_package_revenue_krw_100m": 7716.0,
        "ai_server_mlcc_contract_2027_krw_100m": 10722.0,
    },
    "facts": {
        "server_cpu_fcbga_mass_production": True,
        "mlcc_lta_customer_count_min": 10,
        "north_america_cpu_mlcc_lta_named_customer": False,
        "sixth_gen_server_cpu_abf_customer_named": False,
        "meta_venice_validation": True,
        "meta_venice_large_scale_deployment_confirmed": False,
    },
    "seen_urls": [
        "https://biz.chosun.com/stock/stock_general/2026/09/23/GAZ6ULSXUJDFJB2VFLWMC4DFBY/",
        "https://www.samsungsem.com/kr/newsroom/news/view.do?id=10461",
        "https://www.samsungsem.com/kr/newsroom/news/view.do?id=10501",
        "https://ir.amd.com/news-events/press-releases/detail/1294/aai-2026-amd-delivers-full-stack-compute-for-the-agentic-ai-era",
        "https://newsroom.amd.com/news/amd-and-meta-announce-expanded-strategic-partnersh/",
    ],
    "last_checked_cutoff": "2026-09-23",
}

SEARCHES = [
    ("google", 'site:samsungsem.com 삼성전기 2026 3분기 경영실적 서버 CPU FCBGA MLCC'),
    ("google", 'site:samsungsem.com 삼성전기 AI 서버 MLCC 공급계약 장기공급계약 CPU'),
    ("google", 'site:samsungsem.com 삼성전기 FCBGA 서버 CPU 베트남 6세대'),
    ("google", '"삼성전기" "메리츠" (ABF OR FCBGA OR MLCC) CPU 2026'),
    ("google", '"삼성전기" "CPU 관련 비중" ABF 2026'),
    ("google", 'site:amd.com OR site:ir.amd.com Meta Venice "6th Gen EPYC" deployment shipments'),
]

OFFICIAL_DOMAINS = (
    "samsungsem.com",
    "amd.com",
    "ir.amd.com",
    "newsroom.amd.com",
)

TRUSTED_RESEARCH_DOMAINS = (
    "biz.chosun.com",
    "hankyung.com",
    "mt.co.kr",
    "sedaily.com",
    "etnews.com",
)

MATERIAL_TERMS = (
    "3분기", "3q", "경영실적", "영업이익", "매출",
    "mlcc", "fcbga", "abf", "server cpu", "서버 cpu",
    "공급계약", "장기공급계약", "lta", "6세대", "venice",
    "deploy", "deployment", "shipments", "출하", "양산",
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


def rss_url(kind: str, query: str) -> str:
    q = urllib.parse.quote(query)
    if kind == "google":
        return f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
    return f"https://www.bing.com/search?format=rss&q={q}"


def read_rss(kind: str, query: str) -> list[dict]:
    root = ET.fromstring(fetch(rss_url(kind, query)))
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
        result = gnewsdecoder(link, interval=0.2)
        if isinstance(result, dict) and result.get("status"):
            decoded = str(result.get("decoded_url") or "").strip()
            if decoded.startswith("http") and "news.google.com" not in decoded:
                return decoded
    except Exception:
        pass
    return ""


def direct_url(item: dict) -> str:
    return decode_google_news(item.get("link") or "") if item.get("kind") == "google" else item.get("link") or ""


def article_text(url: str) -> str:
    if not url:
        return ""
    try:
        return clean_text(fetch(url, timeout=18).decode("utf-8", errors="ignore"))[:35000]
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


def is_official(url: str) -> bool:
    host = host_of(url)
    return any(host == d or host.endswith("." + d) for d in OFFICIAL_DOMAINS)


def is_trusted_research(url: str) -> bool:
    host = host_of(url)
    return any(host == d or host.endswith("." + d) for d in TRUSTED_RESEARCH_DOMAINS)


def parse_krw_100m(raw: str) -> float | None:
    raw = (raw or "").replace(",", "").replace(" ", "")
    jo = re.search(r"(\d+(?:\.\d+)?)조", raw)
    eok = re.search(r"(\d+(?:\.\d+)?)억", raw)
    if not jo and not eok:
        return None
    value = 0.0
    if jo:
        value += float(jo.group(1)) * 10000.0
    if eok:
        value += float(eok.group(1))
    return value


def amount_after_label(text: str, labels: tuple[str, ...], max_chars: int = 160) -> float | None:
    low = text.lower()
    for label in labels:
        start = 0
        while True:
            pos = low.find(label.lower(), start)
            if pos < 0:
                break
            chunk = text[pos: min(len(text), pos + max_chars)]
            m = re.search(r"(\d+(?:\.\d+)?조(?:\s*\d[\d,]*(?:\.\d+)?억)?|\d[\d,]*(?:\.\d+)?억)\s*원", chunk)
            if m:
                return parse_krw_100m(m.group(1))
            start = pos + len(label)
    return None


def percent_near(text: str, labels: tuple[str, ...], max_chars: int = 180) -> float | None:
    low = text.lower()
    for label in labels:
        pos = low.find(label.lower())
        if pos < 0:
            continue
        chunk = text[max(0, pos - 40): min(len(text), pos + max_chars)]
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", chunk)
        if m:
            return float(m.group(1))
    return None


def parse_q3_result(text: str, official: bool) -> dict:
    low = text.lower()
    if not official or not (("3분기" in text or "3q" in low) and "영업이익" in text and "매출" in text):
        return {}
    revenue = amount_after_label(text, ("매출액", "매출"))
    op = amount_after_label(text, ("영업이익",))
    if revenue is None or op is None:
        return {}
    if not (20000 <= revenue <= 60000 and 1000 <= op <= 15000):
        return {}
    return {
        "kind": "q3_actual",
        "revenue_krw_100m": revenue,
        "operating_profit_krw_100m": op,
        "opm_pct": op / revenue * 100.0,
    }


def parse_research_update(text: str, trusted: bool) -> dict:
    low = text.lower()
    if not trusted or not ("삼성전기" in text and ("메리츠" in text or "meritz" in low)):
        return {}
    result: dict[str, float | str] = {"kind": "research_update"}
    revenue = amount_after_label(text, ("3분기 매출액", "3분기 매출", "3q 매출"))
    op = amount_after_label(text, ("3분기 영업이익", "3q 영업이익"))
    if revenue is not None and 20000 <= revenue <= 60000:
        result["q3_revenue_forecast_krw_100m"] = revenue
    if op is not None and 1000 <= op <= 15000:
        result["q3_operating_profit_forecast_krw_100m"] = op

    comp = percent_near(text, ("컴포넌트 사업부 영업이익률", "컴포넌트 영업이익률"))
    abf_opm = percent_near(text, ("abf 영업이익률", "패키지 영업이익률"))
    cpu_share = percent_near(text, ("cpu 관련 비중", "cpu향 비중", "cpu 관련 매출 비중"))
    if comp is not None:
        result["component_opm_pct"] = comp
    if abf_opm is not None:
        result["abf_opm_pct"] = abf_opm
    if cpu_share is not None:
        result["cpu_abf_share_pct"] = cpu_share
    return result if len(result) > 1 else {}


def named_cpu_customer_signal(text: str, official: bool) -> str:
    low = text.lower()
    if not official:
        return ""
    if not any(x in low for x in ("amd", "intel", "meta")):
        return ""
    if not any(x in low for x in ("fcbga", "abf", "mlcc", "server cpu", "서버 cpu")):
        return ""
    if "amd" in low:
        return "삼성전기/AMD 연결 또는 AMD CPU 최종수요가 공식자료에서 구체화"
    if "intel" in low:
        return "삼성전기/Intel CPU 연결이 공식자료에서 구체화"
    if "meta" in low:
        return "Meta의 서버 CPU 최종수요·배치가 공식자료에서 구체화"
    return ""


def mlcc_contract_signal(text: str, official: bool) -> dict:
    low = text.lower()
    if not official or not ("mlcc" in low and ("공급계약" in text or "장기공급계약" in text or "lta" in low)):
        return {}
    amount = amount_after_label(text, ("공급계약", "계약", "mlcc"))
    if amount is None:
        return {}
    return {"kind": "mlcc_contract", "amount_krw_100m": amount}


def venice_deployment_signal(text: str, official: bool) -> str:
    low = text.lower()
    if not official:
        return ""
    if not ("venice" in low or "6th gen epyc" in low or "6세대 epyc" in low):
        return ""
    if not "meta" in low:
        return ""
    if any(k in low for k in ("deploy at scale", "deployment", "shipments", "scheduled to begin", "lead customer", "validation", "validating")):
        return "AMD/Meta의 6세대 EPYC Venice 검증·배치·출하 단계 진전"
    return ""


def material_research_changes(old_metrics: dict, update: dict) -> list[dict]:
    rules = {
        "q3_revenue_forecast_krw_100m": ("3Q26 매출 전망", "pct", 5.0),
        "q3_operating_profit_forecast_krw_100m": ("3Q26 영업이익 전망", "pct", 10.0),
        "component_opm_pct": ("컴포넌트 영업이익률", "pp", 5.0),
        "abf_opm_pct": ("ABF 영업이익률", "pp", 5.0),
        "cpu_abf_share_pct": ("CPU향 ABF 비중", "pp", 5.0),
    }
    out = []
    for key, (label, mode, threshold) in rules.items():
        if key not in update:
            continue
        if key == "component_opm_pct":
            before = float(old_metrics.get("component_opm_floor_pct") or 0)
        elif key == "abf_opm_pct":
            before = float(old_metrics.get("abf_opm_floor_pct") or 0)
        elif key == "cpu_abf_share_pct":
            before = float(old_metrics.get("cpu_abf_share_floor_pct") or 0)
        else:
            before = float(old_metrics.get(key) or 0)
        after = float(update[key])
        if not before:
            continue
        delta = after - before if mode == "pp" else (after / before - 1.0) * 100.0
        if abs(delta) >= threshold:
            out.append({"key": key, "label": label, "mode": mode, "before": before, "after": after, "delta": delta})
    return out


def actual_vs_forecast(actual: dict, baseline: dict) -> dict:
    m = baseline.get("metrics") or {}
    rev_f = float(m.get("q3_revenue_forecast_krw_100m") or 0)
    op_f = float(m.get("q3_operating_profit_forecast_krw_100m") or 0)
    rev = float(actual.get("revenue_krw_100m") or 0)
    op = float(actual.get("operating_profit_krw_100m") or 0)
    return {
        "revenue_delta_pct": (rev / rev_f - 1.0) * 100.0 if rev_f else 0.0,
        "operating_profit_delta_pct": (op / op_f - 1.0) * 100.0 if op_f else 0.0,
    }


def fmt_eok(v: float) -> str:
    if v >= 10000:
        jo = int(v // 10000)
        eok = int(round(v - jo * 10000))
        return f"{jo}조{eok:,}억원" if eok else f"{jo}조원"
    return f"{v:,.0f}억원"


def build_alert(events: list[dict], baseline: dict, source_url: str, published: str) -> str:
    lines = [
        "<b>🚨 삼성전기 CPU 매출 실현 게이트 — 변화 감지</b>",
        "",
        "<b>핵심 변화</b>",
    ]
    for event in events:
        kind = event.get("kind")
        if kind == "q3_actual":
            comp = actual_vs_forecast(event, baseline)
            lines.append(
                f"• <b>3Q26 실제 실적:</b> 매출 {fmt_eok(float(event['revenue_krw_100m']))}, "
                f"영업이익 {fmt_eok(float(event['operating_profit_krw_100m']))}, "
                f"영업이익률 {float(event['opm_pct']):.1f}%"
            )
            lines.append(
                f"• 메리츠 기준 대비: 매출 {comp['revenue_delta_pct']:+.1f}% / "
                f"영업이익 {comp['operating_profit_delta_pct']:+.1f}%"
            )
        elif kind == "research_change":
            for ch in event.get("changes") or []:
                suffix = "%p" if ch["mode"] == "pp" else "%"
                lines.append(f"• <b>{html.escape(ch['label'])}</b>: {ch['before']:.1f} → {ch['after']:.1f} ({ch['delta']:+.1f}{suffix})")
        elif kind == "mlcc_contract":
            lines.append(f"• <b>신규 MLCC 계약:</b> {fmt_eok(float(event['amount_krw_100m']))}")
        elif kind == "customer":
            lines.append(f"• <b>CPU 고객/최종수요 구체화:</b> {html.escape(str(event['text']))}")
        elif kind == "venice":
            lines.append(f"• <b>6세대 EPYC 실제 수요 검증:</b> {html.escape(str(event['text']))}")

    m = baseline.get("metrics") or {}
    lines += [
        "",
        "<b>현재 기준선</b>",
        f"• 메리츠 3Q26 매출 {fmt_eok(float(m['q3_revenue_forecast_krw_100m']))} / 영업이익 {fmt_eok(float(m['q3_operating_profit_forecast_krw_100m']))} / 내재 영업이익률 {float(m['q3_implied_opm_pct']):.1f}%",
        f"• 컴포넌트 영업이익률 20%+ / ABF 영업이익률 30%+ / CPU향 ABF 비중 45%+는 증권사 추정 기준선",
        f"• 2027 AI 서버 MLCC 공식 계약 {fmt_eok(float(m['ai_server_mlcc_contract_2027_krw_100m']))} / 글로벌 고객 10여개 LTA는 회사 공식 확인",
        "",
        "<b>매출 연결</b>",
        "• Agentic AI CPU 증가 → 서버 CPU FCBGA/ABF 물량 + CPU 주변 고용량 MLCC → 패키지솔루션·컴포넌트 동시 매출·제품 혼합 개선",
        "",
        "<b>확정·추정 구분</b>",
        "• 회사 공식: 서버 CPU·AI 가속기용 FCBGA 양산, 10여개 MLCC LTA, 2027년 AI 서버 MLCC 1조722억원 계약",
        "• 증권사 추정: CPU향 ABF 비중 45%+, ABF 영업이익률 30%+, 북미 CPU 업체 MLCC LTA 및 6세대 서버용 ABF 물량 증가",
        "",
        "<b>숨은 역풍·실패모드</b>",
        "• 실패 경로: CPU 수요는 늘어도 대면적·고다층 FCBGA 수율·고객 인증이 늦어 가동률보다 감가상각이 먼저 증가",
        "• 조기경보: 패키지 가동률·ABF 수율/영업이익률·고객 승인·RDIMM/eSSD 동반 수요",
        "• 위험 구간: 6~12개월은 고객 승인·출하, 12~24개월은 증설 후 가동률·총자산이익률",
        "",
        "<b>알림 기준</b>",
        "• 3Q26 실제 실적 발표, 매출 전망 ±5% 이상, 영업이익 전망 ±10% 이상, 컴포넌트/ABF 이익률 또는 CPU향 ABF 비중 ±5%p 이상 변화",
        "• CPU 고객 실명·공식 LTA·신규 대형 MLCC 계약·6세대 EPYC Venice 실제 대규모 배치/출하가 새로 확인될 때만 알림",
        "• 목표주가만 바뀌거나 동일 기사·동일 전망이 재인용되면 알리지 않습니다.",
    ]
    if published:
        lines.append(f"• 공개시각: {html.escape(published)}")
    if source_url:
        lines.append(f'• <a href="{html.escape(source_url, quote=True)}">근거 원문</a>')
    return "\n".join(lines).strip() + "\n"


def discover(now: datetime, cutoff: str, seen_urls: set[str]) -> list[dict]:
    out = []
    local_seen = set()
    for kind, query in SEARCHES:
        try:
            items = read_rss(kind, query)
        except Exception:
            continue
        for item in items:
            url = direct_url(item)
            if not url or url in local_seen or url in seen_urls:
                continue
            local_seen.add(url)
            published = item.get("published_at_kst") or ""
            date = published[:10] if published else ""
            if cutoff and date and date <= cutoff:
                continue
            try:
                dt = datetime.fromisoformat(published) if published else None
            except Exception:
                dt = None
            if dt and dt < now - timedelta(days=120):
                continue
            base = clean_text(f"{item.get('title','')} {item.get('description','')}")
            low = base.lower()
            if not any(term in low for term in MATERIAL_TERMS):
                continue
            body = article_text(url)
            text = clean_text(f"{base} {body}")
            official = is_official(url)
            trusted = is_trusted_research(url)

            events = []
            q3 = parse_q3_result(text, official and "samsungsem.com" in host_of(url))
            if q3:
                events.append(q3)

            research = parse_research_update(text, trusted)
            if research:
                changes = material_research_changes(BASELINE["metrics"], research)
                if changes:
                    events.append({"kind": "research_change", "changes": changes})

            contract = mlcc_contract_signal(text, official and "samsungsem.com" in host_of(url))
            if contract and float(contract.get("amount_krw_100m") or 0) != float(BASELINE["metrics"]["ai_server_mlcc_contract_2027_krw_100m"]):
                events.append(contract)

            customer = named_cpu_customer_signal(text, official)
            if customer:
                events.append({"kind": "customer", "text": customer})

            venice = venice_deployment_signal(text, official)
            if venice:
                events.append({"kind": "venice", "text": venice})

            if events:
                out.append({**item, "url": url, "events": events, "text": text})
    out.sort(key=lambda x: x.get("published_at_kst") or "")
    return out


def main() -> None:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    committed = load_json(STATE_PATH)
    pending = load_json(PENDING_PATH)
    previous = committed.get("samsung_electromechanics_cpu_realization") or BASELINE
    latest = copy.deepcopy(previous)
    seen_urls = set(previous.get("seen_urls") or [])
    cutoff = str(previous.get("last_checked_cutoff") or BASELINE["last_checked_cutoff"])

    candidates = discover(now, cutoff, seen_urls)
    notify_blocks = []
    for item in candidates:
        url = item.get("url") or ""
        events = item.get("events") or []
        if not events:
            continue
        notify_blocks.append(build_alert(events, previous, url, item.get("published_at_kst") or ""))
        if url:
            seen_urls.add(url)

        for event in events:
            if event.get("kind") == "q3_actual":
                latest.setdefault("facts", {})["q3_actual_confirmed"] = True
                latest["facts"]["q3_actual_revenue_krw_100m"] = event.get("revenue_krw_100m")
                latest["facts"]["q3_actual_operating_profit_krw_100m"] = event.get("operating_profit_krw_100m")
            elif event.get("kind") == "mlcc_contract":
                latest.setdefault("facts", {})["latest_new_mlcc_contract_krw_100m"] = event.get("amount_krw_100m")
            elif event.get("kind") == "customer":
                latest.setdefault("facts", {})["cpu_customer_or_end_demand_newly_confirmed"] = True
            elif event.get("kind") == "venice":
                latest.setdefault("facts", {})["venice_demand_validation_advanced"] = True

    latest["seen_urls"] = sorted(seen_urls)[-200:]
    latest["last_checked_cutoff"] = now.date().isoformat()
    latest["last_checked_at_kst"] = now.isoformat(timespec="seconds")
    latest["candidate_count"] = len(candidates)

    pending["samsung_electromechanics_cpu_realization"] = latest
    write_json(PENDING_PATH, pending)

    if notify_blocks:
        existing = ALERT_PATH.read_text(encoding="utf-8").strip() if ALERT_PATH.exists() else ""
        addition = "\n\n".join(x.strip() for x in notify_blocks)
        merged = (existing + "\n\n" + addition).strip() if existing else addition
        ALERT_PATH.write_text(merged + "\n", encoding="utf-8")

    print(
        "samsung_electromechanics_cpu_watch=true "
        f"candidates={len(candidates)} notify={str(bool(notify_blocks)).lower()}"
    )


if __name__ == "__main__":
    main()
