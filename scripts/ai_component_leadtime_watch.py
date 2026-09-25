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

UA = "Mozilla/5.0 (compatible; khs-watch/2.0; +https://github.com/qedgwangju-dot/khs-watch)"
BASELINE_DATE = "2026-09-21"
BASELINE = {
    "as_of": BASELINE_DATE,
    "source": "https://insights.trendforce.com/p/weekly-radar-002",
    "components": {
        "GPU": {"status": "Balanced", "current": "30-40", "balanced": "30-40"},
        "DRAM": {"status": "Very Tight", "current": "20", "balanced": "8"},
        "NAND(eSSD)": {"status": "Tight", "current": "16", "balanced": "8"},
        "HDD": {"status": "Very Tight", "current": "50", "balanced": "16"},
        "ABF": {"status": "Very Tight", "current": "48-56", "balanced": "12"},
        "MLCC": {"status": "Tight", "current": "32", "balanced": "12"},
    },
    "signals": {
        "GPU": "Rubin 사양 조정 → Blackwell보다 리드타임 장기화 가능성",
        "DRAM": "미국 CSP의 2027년 서버 증설 대비 RDIMM 수요 증가",
        "NAND(eSSD)": "수요 증가 → 공급사가 기업용 SSD로 생산능력 재배분, 전체 공급은 여전히 부족",
        "HDD": "에이전틱 AI 수요 급증 → 2027년 말까지 리드타임 개선 제한",
        "ABF": "2027년 일본 Low-CTE 유리섬유 천 증설로 소재 병목 완화 가능, 기판 생산능력은 예약 포화",
        "MLCC": "신학기 수요 부진 → 저가 범용 유통가격 하락, 고급 소비자용 가격은 안정",
    },
    "seen_urls": ["https://insights.trendforce.com/p/weekly-radar-002"],
}

CPU_BASELINE = {
    "as_of": "2026-08-12",
    "source": "BofA Global Research (2026-08-12), public recap verification",
    "source_url": "https://finvaulta.com/research/bank-of-america/rise-of-the-agents-raising-cpu-tam-again-to-210bn-2026-08-12",
    "server_cpu_tam_2030_bn": 210.6,
    "server_cpu_tam_2026_bn": 61.4,
    "agentic_cpu_tam_2030_bn": 90.2,
    "compute_head_cpu_tam_2030_bn": 90.2,
    "traditional_cpu_tam_2030_bn": 30.0,
    "ai_cpu_tam_2030_bn": 180.4,
    "agentic_share_pct": 42.8,
    "ai_related_share_pct": 85.7,
    "cpu_gpu_ratio": "1:1",
    "prior_server_cpu_tam_2030_bn": 170.0,
    "earlier_server_cpu_tam_2030_bn": 125.0,
    "seen_urls": [
        "https://finvaulta.com/research/bank-of-america/rise-of-the-agents-raising-cpu-tam-again-to-210bn-2026-08-12"
    ],
}

CPU_SEARCHES = [
    ("google_news", '"BofA" "server CPU" (agentic OR agents) (2030 OR TAM)'),
    ("bing_web", '"BofA" "server CPU TAM" agentic 2030 210'),
    ("bing_web", '"Rise of the Agents" "server CPU" BofA'),
    ("bing_web", 'site:amd.com "agentic AI" "CPU" "GPU" "1:1"'),
    ("bing_web", 'site:ir.amd.com "agentic AI" EPYC server CPU'),
    ("bing_web", 'site:intc.com server CPU AI agentic data center revenue'),
]

SEARCHES = [
    ("trendforce_feed", ""),
    (
        "google_news",
        'TrendForce ("lead time" OR "lead times" OR "리드타임") (ABF OR MLCC OR HDD OR DRAM OR NAND OR GPU) "AI infrastructure"',
    ),
    ("bing_web", 'site:insights.trendforce.com/p/weekly-radar TrendForce "Weekly Radar"'),
    ("bing_web", 'site:x.com/trendforce "lead time" "AI infrastructure" ABF MLCC'),
    ("bing_web", 'site:trendforce.com TrendForce "lead time" ABF DRAM NAND HDD MLCC GPU'),
    ("bing_web", '"current vs balanced lead times" TrendForce'),
    ("bing_web", '"TrendForce" GPU DRAM NAND HDD ABF MLCC 리드타임'),
    ("bing_web", '"TrendForce" "Weekly Radar" GPU DRAM NAND HDD ABF MLCC'),
]

ALIASES = {
    "GPU": ("GPU",),
    "DRAM": ("DRAM",),
    "NAND(eSSD)": ("NAND", "eSSD", "enterprise SSD"),
    "HDD": ("HDD", "hard disk"),
    "ABF": ("ABF substrates", "ABF substrate", "ABF"),
    "MLCC": ("MLCCs", "MLCC"),
}

STATUS_KO = {
    "Very Tight": "심각한 공급 부족",
    "Tight": "공급 제약",
    "Balanced": "균형",
}

STATUS_SEVERITY = {"Balanced": 0, "Tight": 1, "Very Tight": 2}

REVENUE_PATHS = {
    "GPU": "AI 가속기 출하 → 첨단패키징·HBM·기판·전력·냉각 동반 수요 → 시스템 매출",
    "DRAM": "서버·RDIMM 수요 → 출하량·평균판매단가·제품 혼합 개선 → 메모리 매출·마진",
    "NAND(eSSD)": "기업용 SSD 수요 → NAND 생산능력 재배분 → eSSD 출하·평균판매단가 → 스토리지 매출",
    "HDD": "에이전틱 AI 데이터·로그·장기보관 증가 → nearline HDD 용량·출하 → 스토리지 매출",
    "ABF": "GPU·ASIC·CPU 대형·고다층화 → FC-BGA/ABF 유효 생산능력 소모 → 고부가 기판 출하·제품 혼합 개선",
    "MLCC": "AI 서버·네트워크 전력밀도 상승 → 고용량·고신뢰성 MLCC 탑재량 증가 → 고부가 부품 매출",
}

COMPANY_WATCH = {
    "GPU": "NVIDIA·AMD — AI 가속기 수요축",
    "DRAM": "삼성전자·SK하이닉스·Micron — 서버 DRAM/RDIMM",
    "NAND(eSSD)": "삼성전자·SK하이닉스/Solidigm·Micron — 기업용 SSD/NAND",
    "HDD": "Seagate·Western Digital — nearline HDD",
    "ABF": "삼성전기·Ibiden·Unimicron·Nan Ya PCB — 고성능 FC-BGA/ABF 기판",
    "MLCC": "삼성전기·Murata·Taiyo Yuden — 고용량·고신뢰성 MLCC",
}

FAILURE_MODES = {
    "GPU": ("사양 변경·플랫폼 전환 지연", "샘플→양산 일정·랙 출하", "6~12개월"),
    "DRAM": ("선주문 이후 실제 서버 출하가 따라오지 않아 재고가 다시 쌓이는 경로", "RDIMM 가격·재고·출하", "6~12개월"),
    "NAND(eSSD)": ("eSSD로 생산능력을 옮겼지만 실제 수요가 둔화돼 가격과 가동률이 동시에 꺾이는 경로", "기업용 SSD 가격·가동률·재고", "6~12개월"),
    "HDD": ("대용량 드라이브 수율·생산능력 확대가 지연돼 납기만 길어지는 경로", "출하 EB·리드타임·고객 재고", "6~12개월"),
    "ABF": ("T-glass·압합장비·휨·수율·고객 인증이 증설 속도를 따라오지 못하는 경로", "리드타임·SAP 가동률·수율·고객 승인", "12~24개월"),
    "MLCC": ("범용 수요 약세가 AI용 고사양 가격 방어보다 커져 제품 혼합 효과가 약화되는 경로", "고사양/범용 가격·BB비율·가동률", "6~12개월"),
}

WEEK = r"(\d{1,2}(?:\s*[-–—~]\s*\d{1,2})?)\s*(?:weeks?|w|주)\b"


def fetch(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<(script|style|svg|noscript)[^>]*>.*?</\1>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_week(value: str) -> str:
    return re.sub(r"\s*[-–—~]\s*", "-", (value or "").strip())


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


def bing_rss_url(query: str) -> str:
    q = urllib.parse.quote(query)
    return f"https://www.bing.com/search?format=rss&q={q}"


def read_rss(kind: str, query: str) -> list[dict]:
    if kind == "trendforce_feed":
        url = "https://insights.trendforce.com/feed"
    elif kind == "google_news":
        url = google_news_url(query)
    else:
        url = bing_rss_url(query)
    root = ET.fromstring(fetch(url))
    out: list[dict] = []
    for item in root.findall("./channel/item"):
        title = clean_text(item.findtext("title") or "")
        link = clean_text(item.findtext("link") or "")
        desc = clean_text(item.findtext("description") or "")
        pub = clean_text(item.findtext("pubDate") or "")
        dt = parse_pubdate(pub)
        if title and link:
            out.append(
                {
                    "kind": kind,
                    "title": title,
                    "link": link,
                    "description": desc,
                    "published_at_kst": dt.isoformat(timespec="seconds") if dt else "",
                }
            )
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


def candidate_url(item: dict) -> str:
    if item.get("kind") == "google_news":
        return decode_google_news(item.get("link") or "")
    return item.get("link") or ""


def is_trendforce_source(url: str, text: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    low = text.lower()
    return (
        "trendforce.com" in host
        or (host.endswith("x.com") and "/trendforce" in url.lower())
        or "trendforce" in low
    )


def is_relevant(text: str) -> bool:
    low = text.lower()
    component_hits = sum(1 for aliases in ALIASES.values() if any(a.lower() in low for a in aliases))
    lead_hit = any(k in low for k in ("lead time", "lead times", "balanced lead", "current lead", "리드타임", "납기"))
    weekly_phrase = "six ai infrastructure components" in low or "current vs balanced" in low
    return lead_hit and (component_hits >= 2 or weekly_phrase)


def article_text(url: str) -> str:
    if not url:
        return ""
    host = (urlparse(url).hostname or "").lower()
    if host.endswith("x.com"):
        return ""
    try:
        raw = fetch(url, timeout=18).decode("utf-8", errors="ignore")
        return clean_text(raw)[:24000]
    except Exception:
        return ""


def status_from_exact(value: str) -> str:
    low = (value or "").lower()
    if "very tight" in low or "severe shortage" in low or "심각한 공급 부족" in value or "심각한 부족" in value:
        return "Very Tight"
    if re.search(r"\btight\b", low) or "constrained supply" in low or "공급 제약" in value:
        return "Tight"
    if "balanced" in low or "균형" in value:
        return "Balanced"
    return ""


def extract_structured_row(text: str, alias: str) -> dict:
    # 표가 실제 텍스트로 노출된 경우에만 사용한다.
    # 컴포넌트명 뒤에 상태→현재 납기→균형 납기가 연속해서 붙은 경우만 인정한다.
    pattern = (
        rf"\b{re.escape(alias)}\b"
        rf"(?:\s+substrates?)?\s*[:|\-]?\s*"
        rf"(Very\s+Tight|Tight|Balanced)\s*"
        rf"{WEEK}\s*{WEEK}"
    )
    m = re.search(pattern, text, re.I)
    if not m:
        return {}
    return {
        "status": status_from_exact(m.group(1)),
        "current": normalize_week(m.group(2)),
        "balanced": normalize_week(m.group(3)),
    }


def extract_labeled_narrative(text: str, alias: str) -> dict:
    # 영문 원문과 국내 재전달 문구를 모두 읽되, 숫자는 alias 이후 문맥에서만 채택한다.
    positions = [m for m in re.finditer(re.escape(alias), text, re.I)]
    best: dict = {}
    for m in positions:
        chunk = text[m.start() : min(len(text), m.end() + 420)]
        entry: dict[str, str] = {}

        b = re.search(
            rf"(?:balanced(?:\s+market|\s+lead\s+time|\s+lead\s+times)?|균형(?:\s*리드타임|\s*수준)?)"
            rf"[^.\n]{{0,120}}?{WEEK}",
            chunk,
            re.I,
        )
        if b:
            entry["balanced"] = normalize_week(b.group(1))

        c = re.search(
            rf"(?:current(?:\s+lead\s+time|\s+lead\s+times)?|리드타임(?:은|는|:)?|납기(?:는|:)?|현재(?:\s*리드타임)?)"
            rf"[^.\n]{{0,80}}?{WEEK}",
            chunk,
            re.I,
        )
        if c:
            entry["current"] = normalize_week(c.group(1))

        # 상태는 표의 구조화 행 또는 "X는 Very Tight/Tight/Balanced"처럼
        # 부품명과 상태가 직접 연결된 명시 문구에서만 갱신한다.
        # "balanced lead time" 같은 벤치마크 문구를 상태로 오인하지 않는다.

        if len(entry) > len(best):
            best = entry
    return best


def extract_group_statuses(text: str) -> dict[str, str]:
    # 예: "DRAM·HDD·ABF는 심각한 공급 부족, NAND eSSD·MLCC는 공급 제약 상태"
    token = r"(?:GPU|DRAM|NAND(?:\s*\(eSSD\)|\s+eSSD)?|eSSD|HDD|ABF|MLCC)"
    group = rf"({token}(?:\s*[·,/＋+&]\s*{token})*)"
    out: dict[str, str] = {}

    for m in re.finditer(
        rf"{group}\s*(?:은|는|이|가|are|remain)?\s*"
        r"(심각한 공급 부족|심각한 부족|공급 제약(?: 상태)?|균형(?: 상태)?|Very\s+Tight|Tight|Balanced|severe shortage|constrained supply)",
        text,
        re.I,
    ):
        status = status_from_exact(m.group(2))
        names = m.group(1)
        for name, aliases in ALIASES.items():
            if any(re.search(re.escape(a), names, re.I) for a in aliases):
                out[name] = status

    # 예: "균형 상태인 품목은 GPU뿐"처럼 상태와 품목군이 문법적으로 직접 연결된 경우만 인정한다.
    # 쉼표 뒤의 다음 상태군을 앞 상태가 덮어쓰지 않도록 임의 거리 매칭은 사용하지 않는다.
    for m in re.finditer(
        r"(심각한 공급 부족|공급 제약|균형|Very\s+Tight|Tight|Balanced)"
        r"(?:\s+상태)?(?:인)?\s+품목(?:은|이|으로는)?\s*"
        rf"{group}",
        text,
        re.I,
    ):
        status = status_from_exact(m.group(1))
        names = m.group(2)
        for name, aliases in ALIASES.items():
            if any(re.search(re.escape(a), names, re.I) for a in aliases):
                out[name] = status
    return out


def extract_components(text: str) -> dict:
    result: dict[str, dict] = {}
    normalized = text.replace("–", "-").replace("—", "-")
    for name, aliases in ALIASES.items():
        best: dict = {}
        for alias in aliases:
            structured = extract_structured_row(normalized, alias)
            if structured:
                best = structured
                break
            narrative = extract_labeled_narrative(normalized, alias)
            if len(narrative) > len(best):
                best = narrative
        if best.get("current") or best.get("balanced") or best.get("status"):
            result[name] = best

    for name, status in extract_group_statuses(normalized).items():
        result.setdefault(name, {})["status"] = status
    return result


def extract_signals(text: str, source_url: str = "") -> dict[str, str]:
    low = (text or "").lower()
    signals: dict[str, str] = {}

    if "rubin" in low and ("specification" in low or "adjustment" in low or "사양 조정" in text):
        signals["GPU"] = "Rubin 사양 조정 → Blackwell보다 리드타임 장기화 가능성"

    if "rdimm" in low and "2027" in low and any(k in low for k in ("demand", "pick up", "수요")):
        signals["DRAM"] = "미국 CSP의 2027년 서버 증설 대비 RDIMM 수요 증가"

    if (
        any(k in low for k in ("enterprise ssds", "enterprise ssd", "essd"))
        and any(k in low for k in ("reallocat", "capacity toward", "생산능력 재배분", "캐파 재배분"))
    ):
        signals["NAND(eSSD)"] = "수요 증가 → 공급사가 기업용 SSD로 생산능력 재배분, 전체 공급은 여전히 부족"

    if "hdd" in low and "agentic ai" in low:
        if "late 2027" in low or "2027년 말" in text:
            signals["HDD"] = "에이전틱 AI 수요 급증 → 2027년 말까지 리드타임 개선 제한"
        else:
            signals["HDD"] = "에이전틱 AI 수요 증가 → HDD 공급 압박 지속"

    if (
        "abf" in low
        and any(k in low for k in ("low-cte", "low cte"))
        and any(k in low for k in ("glass fiber", "유리섬유"))
    ):
        signals["ABF"] = "2027년 일본 Low-CTE 유리섬유 천 증설로 소재 병목 완화 가능, 기판 생산능력은 예약 포화"

    if "mlcc" in low and any(k in low for k in ("back-to-school", "신학기")):
        signals["MLCC"] = "신학기 수요 부진 → 저가 범용 유통가격 하락, 고급 소비자용 가격은 안정"

    if source_url.rstrip("/").endswith("weekly-radar-002"):
        for name, value in BASELINE["signals"].items():
            signals.setdefault(name, value)

    return signals


def canonical_component(entry: dict) -> tuple[str, str, str]:
    return (
        str(entry.get("status") or ""),
        str(entry.get("current") or ""),
        str(entry.get("balanced") or ""),
    )


def changed_components(old: dict, new: dict) -> list[str]:
    changed = []
    for name, new_entry in new.items():
        old_entry = old.get(name) or {}
        if canonical_component(old_entry) != canonical_component(new_entry):
            changed.append(name)
    return changed


def midpoint_week(value: str) -> float | None:
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", value or "")]
    if not nums:
        return None
    return sum(nums) / len(nums)


def ratio_value(current: str, balanced: str) -> float | None:
    c = midpoint_week(current)
    b = midpoint_week(balanced)
    if c is None or b in (None, 0):
        return None
    return c / b


def biggest_current_change(old: dict, new: dict) -> tuple[str, float] | None:
    ranked: list[tuple[float, str, float]] = []
    for name, new_entry in new.items():
        old_entry = old.get(name) or {}
        before = midpoint_week(str(old_entry.get("current") or ""))
        after = midpoint_week(str(new_entry.get("current") or ""))
        if before is None or after is None or before == after:
            continue
        ranked.append((abs(after - before), name, after - before))
    if not ranked:
        return None
    ranked.sort(reverse=True)
    _, name, delta = ranked[0]
    return name, delta


def bottleneck_ranking(components: dict) -> list[tuple[float, str, dict]]:
    ranked: list[tuple[float, str, dict]] = []
    for name, entry in components.items():
        ratio = ratio_value(str(entry.get("current") or ""), str(entry.get("balanced") or ""))
        if ratio is not None:
            ranked.append((ratio, name, entry))
    ranked.sort(reverse=True)
    return ranked


def supply_direction(old: dict, new: dict) -> tuple[str, int, int]:
    worse = 0
    better = 0
    for name, entry in new.items():
        before = old.get(name) or {}
        old_ratio = ratio_value(str(before.get("current") or ""), str(before.get("balanced") or ""))
        new_ratio = ratio_value(str(entry.get("current") or ""), str(entry.get("balanced") or ""))
        old_sev = STATUS_SEVERITY.get(str(before.get("status") or ""), 0)
        new_sev = STATUS_SEVERITY.get(str(entry.get("status") or ""), 0)
        if new_sev > old_sev or (old_ratio is not None and new_ratio is not None and new_ratio > old_ratio + 0.05):
            worse += 1
        elif new_sev < old_sev or (old_ratio is not None and new_ratio is not None and new_ratio < old_ratio - 0.05):
            better += 1
    if worse > better:
        return "↗ 병목 확대", worse, better
    if better > worse:
        return "↘ 병목 완화", worse, better
    return "→ 혼조·변화 제한", worse, better


def focus_components(changed: list[str], signal_names: list[str], components: dict, limit: int = 4) -> list[str]:
    out: list[str] = []
    ranked = bottleneck_ranking(components)

    # 가장 강한 병목은 변화 여부와 무관하게 항상 투자판단 초점에 남긴다.
    if ranked:
        strongest_name = ranked[0][1]
        if strongest_name in components:
            out.append(strongest_name)

    for name in [*changed, *signal_names]:
        if name in components and name not in out:
            out.append(name)
        if len(out) >= limit:
            return out[:limit]

    for _, name, _ in ranked:
        if name not in out:
            out.append(name)
        if len(out) >= limit:
            break
    return out[:limit]


def source_score(url: str, components: dict, text: str) -> int:
    host = (urlparse(url).hostname or "").lower()
    score = len(components) * 10
    # 공식 원문이 일부 필드만 노출하더라도 2차 재인용보다 항상 우선한다.
    if "trendforce.com" in host:
        score += 1000
    elif host.endswith("x.com") and "/trendforce" in url.lower():
        score += 900
    elif "trendforce" in text.lower():
        score += 100
    if "current vs balanced" in text.lower():
        score += 20
    if "weekly radar" in text.lower():
        score += 20
    return score


def cpu_source_score(url: str, text: str) -> int:
    host = (urlparse(url).hostname or "").lower()
    low = (text or "").lower()
    score = 0
    if "bank of america" in low or "bofa" in low:
        score += 300
    if "server cpu" in low:
        score += 150
    if "agentic" in low:
        score += 100
    if "amd.com" in host or "intc.com" in host:
        score += 400
    if "finvaulta.com" in host:
        score += 250
    return score


def _context_number(text: str, phrases: tuple[str, ...], max_chars: int = 220) -> float | None:
    low = text.lower()
    for phrase in phrases:
        start = 0
        while True:
            pos = low.find(phrase.lower(), start)
            if pos < 0:
                break
            chunk = text[max(0, pos - 80): min(len(text), pos + max_chars)]
            m = re.search(r"\$?\s*(\d{2,4}(?:\.\d+)?)\s*(?:bn|billion|b)\b", chunk, re.I)
            if m:
                try:
                    return float(m.group(1))
                except Exception:
                    pass
            start = pos + len(phrase)
    return None


def extract_cpu_snapshot(text: str, source_url: str = "") -> dict:
    low = (text or "").lower()
    if "server cpu" not in low and not ("agentic" in low and "cpu" in low):
        return {}

    out: dict[str, object] = {}
    server = _context_number(text, ("server cpu tam", "server cpu market", "server cpu total addressable market", "cpu tam"))
    if server is not None and 50 <= server <= 500:
        out["server_cpu_tam_2030_bn"] = server

    agentic = _context_number(
        text,
        ("agentic ai cpu racks", "agentic ai nodes", "agentic cpu", "standalone processors running ai agents", "agentic ai")
    )
    if agentic is not None and 10 <= agentic <= 250:
        out["agentic_cpu_tam_2030_bn"] = agentic

    ai_cpu = _context_number(text, ("ai cpu tam", "ai cpus grow", "ai cpu"))
    if ai_cpu is not None and 50 <= ai_cpu <= 350:
        out["ai_cpu_tam_2030_bn"] = ai_cpu

    # 2030 agentic share. Only accept when the percent is near an agentic phrase.
    for m in re.finditer(r"agentic[^.\n]{0,160}?(\d{1,2}(?:\.\d+)?)\s*%", text, re.I):
        pct = float(m.group(1))
        if 10 <= pct <= 90:
            out["agentic_share_pct"] = pct
            break

    ratio = re.search(r"(?:cpu\s*(?:-|to|:)\s*gpu|cpu[- ]to[- ]gpu)[^.\n]{0,100}?\b(\d+)\s*[:to-]\s*(\d+)\b", text, re.I)
    if not ratio:
        ratio = re.search(r"(?:toward|towards|to|at)\s*(?:roughly|about|~)?\s*(\d+)\s*:\s*(\d+)", text, re.I)
    if ratio:
        out["cpu_gpu_ratio"] = f"{ratio.group(1)}:{ratio.group(2)}"

    if "bofa" in low or "bank of america" in low:
        out["source_kind"] = "BofA 전망"
    elif "amd.com" in source_url.lower():
        out["source_kind"] = "AMD 공식"
    elif "intc.com" in source_url.lower():
        out["source_kind"] = "Intel 공식"
    else:
        out["source_kind"] = "신뢰 보도"

    out["source_url"] = source_url
    return out


def cpu_actual_validation_event(text: str, source_url: str) -> str:
    host = (urlparse(source_url).hostname or "").lower()
    low = (text or "").lower()
    official = any(x in host for x in ("amd.com", "intc.com"))
    if not official:
        return ""
    if not any(k in low for k in ("agentic", "epyc", "xeon", "server cpu", "data center cpu")):
        return ""
    if any(k in low for k in ("validating", "validation", "deploy at scale", "deployed", "production", "unit volume", "shipments", "revenue")):
        if "amd.com" in host:
            return "AMD 공식자료에서 Agentic AI/EPYC의 실제 검증·배치·생산 신호 확인"
        if "intc.com" in host:
            return "Intel 공식자료에서 서버 CPU의 실제 출하·매출·수요 검증 신호 확인"
    return ""


def cpu_material_changes(old: dict, new: dict) -> list[str]:
    changes: list[str] = []
    for key in ("server_cpu_tam_2030_bn", "agentic_cpu_tam_2030_bn", "ai_cpu_tam_2030_bn"):
        ov = old.get(key)
        nv = new.get(key)
        if isinstance(ov, (int, float)) and isinstance(nv, (int, float)) and ov:
            if abs(float(nv) / float(ov) - 1.0) >= 0.10:
                changes.append(key)
    ov = old.get("agentic_share_pct")
    nv = new.get("agentic_share_pct")
    if isinstance(ov, (int, float)) and isinstance(nv, (int, float)):
        if abs(float(nv) - float(ov)) >= 5.0:
            changes.append("agentic_share_pct")
    if new.get("cpu_gpu_ratio") and old.get("cpu_gpu_ratio") and new.get("cpu_gpu_ratio") != old.get("cpu_gpu_ratio"):
        changes.append("cpu_gpu_ratio")
    return changes


def cpu_snapshot_summary(cpu: dict) -> list[str]:
    total = cpu.get("server_cpu_tam_2030_bn")
    agentic = cpu.get("agentic_cpu_tam_2030_bn")
    ai_total = cpu.get("ai_cpu_tam_2030_bn")
    share = cpu.get("agentic_share_pct")
    ratio = cpu.get("cpu_gpu_ratio")
    lines: list[str] = []
    if isinstance(total, (int, float)):
        lines.append(f"2030 서버 CPU 시장 {float(total):.1f}십억달러")
    if isinstance(agentic, (int, float)):
        lines.append(f"에이전트형 AI CPU {float(agentic):.1f}십억달러")
    if isinstance(share, (int, float)):
        lines.append(f"에이전트형 비중 {float(share):.1f}%")
    if isinstance(ai_total, (int, float)):
        lines.append(f"AI CPU 전체 {float(ai_total):.1f}십억달러")
    if ratio:
        lines.append(f"CPU:GPU {ratio}")
    return lines


def build_cpu_alert(
    old: dict,
    new: dict,
    changes: list[str],
    source_url: str,
    published: str,
    validation_note: str = "",
) -> str:
    lines = [
        "<b>🚨 AI 인프라 병목 감시 — CPU·에이전트형 AI 변화</b>",
        "",
        "<b>핵심 변화</b>",
    ]
    label_map = {
        "server_cpu_tam_2030_bn": "2030 서버 CPU 시장",
        "agentic_cpu_tam_2030_bn": "2030 에이전트형 AI CPU",
        "ai_cpu_tam_2030_bn": "2030 AI CPU 전체",
        "agentic_share_pct": "에이전트형 비중",
        "cpu_gpu_ratio": "CPU:GPU 구조",
    }
    for key in changes:
        label = label_map.get(key, key)
        ov, nv = old.get(key), new.get(key)
        if key.endswith("_bn"):
            lines.append(f"• <b>{label}</b>: {ov} → {nv}십억달러")
        elif key.endswith("_pct"):
            lines.append(f"• <b>{label}</b>: {ov}% → {nv}%")
        else:
            lines.append(f"• <b>{label}</b>: {html.escape(str(ov))} → {html.escape(str(nv))}")

    if validation_note:
        lines.append(f"• <b>실제 수요 검증:</b> {html.escape(validation_note)}")

    lines += [
        "",
        "<b>수익구조</b>",
        "• 에이전트형 AI 확산 → 별도 CPU 연산·오케스트레이션 계층 증가 → 서버 CPU 출하·평균판매단가 → DDR5 RDIMM·기업용 SSD·네트워크·ABF 동반 수요",
        "",
        "<b>1단계 현재 숫자 추적</b>",
    ]
    for item in cpu_snapshot_summary(new):
        lines.append("• " + html.escape(item))

    lines += [
        "",
        "<b>2단계 미래 재평가 요인 발굴</b>",
        "• BofA 기준선은 2030 서버 CPU 2,106억달러, 에이전트형 AI CPU 902억달러, AI CPU 전체 1,804억달러입니다.",
        "• AMD는 Agentic AI에서 CPU:GPU가 기존 1:4~1:8에서 1:1 방향으로 이동하며 별도 CPU compute layer가 필요하다고 설명합니다.",
        "• 따라서 실제 재평가는 전망치 자체보다 CPU 서버 주문·출하와 CPU당 RDIMM·eSSD 탑재량이 확인될 때 강화됩니다.",
        "",
        "<b>관련 기업 지도</b>",
        "• CPU 직접: AMD·Intel·Arm 생태계 — 서버 CPU 출하·평균판매단가",
        "• 서버 메모리: 삼성전자·SK하이닉스·Micron — DDR5·고용량 RDIMM",
        "• 기업용 SSD: 삼성전자·SK하이닉스/Solidigm·Micron — eSSD·NAND",
        "• 기판: 삼성전기·Ibiden·Unimicron·Nan Ya PCB — 서버 CPU용 FC-BGA/ABF",
        "• 시스템·네트워크: Dell·HPE·Supermicro / Broadcom·NVIDIA — 노드·연결 수요",
        "",
        "<b>공정 병목 후보</b>",
        "• CPU 공급 | 첨단공정·패키징·ABF | 먼저 볼 지표: 서버 CPU 리드타임·출하",
        "• 메모리 | 고용량 DDR5·RDIMM | 먼저 볼 지표: 64GB·128GB RDIMM 가격·재고",
        "• 저장장치 | KV 캐시·상태 저장 | 먼저 볼 지표: 기업용 SSD 출하·평균판매단가",
        "",
        "<b>숨은 역풍·실패모드</b>",
        "• 가장 현실적인 실패 경로: 에이전트 사용량은 늘지만 가상화·통합·소프트웨어 효율화가 더 빨라 실제 CPU 노드 증설이 전망을 밑도는 경우",
        "• 조기경보: CPU 서버 주문·출하가 전망 상향을 따라오지 않거나 RDIMM·eSSD 가격과 출하가 동반 둔화",
        "• 위험 구간: 6~12개월은 주문 검증, 12~24개월은 실제 노드 배치·메모리·스토리지 동반 증가 확인",
        "",
        "<b>결론</b>",
        "• CPU 축은 별도 테마가 아니라 기존 DRAM·eSSD·ABF·MLCC 병목의 수요 원인을 설명하는 상위 수요축으로 추적합니다.",
        "",
        "<b>핵심 한 줄 요약</b>",
        "• 에이전트형 AI의 CPU 구조 전망이 materially 상향되면 서버 CPU → DDR5 RDIMM → eSSD → 네트워크·ABF로 수요가 확장되는지 실제 주문·출하로 재검증합니다.",
    ]
    if published:
        lines.append(f"• 공개시각: {html.escape(published)}")
    if source_url:
        lines.append(f'• <a href="{html.escape(source_url, quote=True)}">근거 원문</a>')
    return "\n".join(lines).strip() + "\n"


def load_json(path: pathlib.Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: pathlib.Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def repair_bad_initial_state(previous: dict) -> dict:
    # 2026-09-15 최초 배포 검증 중 서문에 있던 '56W'를 GPU 값으로 오인한 상태를 자동 복구한다.
    comps = previous.get("components") or {}
    if (
        str(previous.get("source") or "").endswith("/weekly-radar-001")
        and str((comps.get("GPU") or {}).get("current") or "") == "56"
    ):
        fixed = copy.deepcopy(BASELINE)
        fixed["seen_urls"] = list(previous.get("seen_urls") or [])
        return fixed
    return previous


def repair_weekly_002_state(previous: dict) -> tuple[dict, list[str]]:
    # Weekly Radar 002 공식 표(사용자 제공 TrendForce 원본 캡처) 기준 상태를 잠근다.
    # 2026-09-22 배포본에서 "균형 리드타임" 문구를 공급 상태로 잘못 읽은 회귀를 복구한다.
    if not str(previous.get("source") or "").rstrip("/").endswith("weekly-radar-002"):
        return previous, []
    comps = previous.get("components") or {}
    expected = BASELINE["components"]
    repaired = copy.deepcopy(previous)
    repaired.setdefault("components", {})
    changed: list[str] = []
    for name, exp in expected.items():
        cur = dict(repaired["components"].get(name) or {})
        # 숫자는 Weekly Radar 002 기준값과 일치할 때만 상태를 강제 복구한다.
        if (
            str(cur.get("current") or "") == str(exp.get("current") or "")
            and str(cur.get("balanced") or "") == str(exp.get("balanced") or "")
            and str(cur.get("status") or "") != str(exp.get("status") or "")
        ):
            cur["status"] = exp["status"]
            repaired["components"][name] = cur
            changed.append(name)
    repaired["signals"] = copy.deepcopy(BASELINE.get("signals") or repaired.get("signals") or {})
    return repaired, changed


def build_status_correction_alert(old: dict, corrected: dict, names: list[str], source_url: str) -> str:
    lines = [
        "<b>⚠️ AI 부품 리드타임 감시 — 상태 정정</b>",
        "",
        "직전 알림에서 균형 리드타임 문구를 공급 상태로 잘못 읽은 항목을 정정합니다.",
    ]
    for name in names:
        old_status = fmt_status(old.get(name) or {})
        new_status = fmt_status(corrected.get(name) or {})
        lines.append(f"• <b>{html.escape(name)}</b>: {html.escape(old_status)} → {html.escape(new_status)}")
    lines += ["", "<b>정정 후 6개 품목 상태</b>"]
    for name in ("GPU", "DRAM", "NAND(eSSD)", "HDD", "ABF", "MLCC"):
        entry = corrected.get(name) or {}
        lines.append(
            f"• <b>{html.escape(name)}</b> | 현재 {html.escape(fmt_week(entry.get('current')))} | "
            f"균형 {html.escape(fmt_week(entry.get('balanced')))} | 상태 {html.escape(fmt_status(entry))}"
        )
    if source_url:
        safe_url = html.escape(source_url, quote=True)
        lines.append(f'• <a href="{safe_url}">TrendForce 원문</a>')
    return "\n".join(lines).strip() + "\n"


def fmt_week(value: str) -> str:
    value = str(value or "확인 불가").replace("-", "~")
    return value if value == "확인 불가" else value + "주"


def fmt_status(entry: dict) -> str:
    status = str(entry.get("status") or "")
    return STATUS_KO.get(status, status or "상태 미확인")


def fmt_entry(entry: dict) -> str:
    return f"현재 {fmt_week(entry.get('current'))} / 균형 {fmt_week(entry.get('balanced'))} / 상태 {fmt_status(entry)}"


def fmt_change(old_entry: dict, new_entry: dict) -> str:
    parts = []
    old_current = str(old_entry.get("current") or "")
    new_current = str(new_entry.get("current") or "")
    if old_current != new_current:
        parts.append(f"{fmt_week(old_current)} → {fmt_week(new_current)}")

    old_balanced = str(old_entry.get("balanced") or "")
    new_balanced = str(new_entry.get("balanced") or "")
    if old_balanced != new_balanced:
        parts.append(f"균형 {fmt_week(old_balanced)} → {fmt_week(new_balanced)}")

    old_status = fmt_status(old_entry)
    new_status = fmt_status(new_entry)
    if old_status != new_status:
        parts.append(f"상태 {old_status} → {new_status}")
    return ", ".join(parts) if parts else "동일"


def evidence_note(name: str, evidence: dict[str, set[str]] | None, field: str) -> str:
    if evidence is None:
        return ""
    fields = evidence.get(name) or set()
    if field in fields:
        return ""
    return " (직전 확정값 유지·이번 주 직접 판독 미확인)"


def build_alert(
    old: dict,
    new: dict,
    changed: list[str],
    source_url: str,
    published: str,
    signal_only: bool,
    signals: dict[str, str] | None = None,
    changed_signals: list[str] | None = None,
    evidence: dict[str, set[str]] | None = None,
    cpu_state: dict | None = None,
) -> str:
    signals = signals or {}
    cpu_state = cpu_state or CPU_BASELINE
    changed_signals = changed_signals or []
    ranked = bottleneck_ranking(new or old)
    strongest = ranked[0] if ranked else None
    direction, worse_count, better_count = supply_direction(old, new)
    focus = focus_components(changed, changed_signals, new or old, limit=4)

    lines = [
        "<b>🚨 AI 부품 리드타임 감시 — 변화 감지</b>",
        "",
        "<b>핵심 변화</b>",
        f"• <b>현재 방향:</b> {html.escape(direction)}"
        + (f" — 악화 {worse_count}개 / 완화 {better_count}개" if (worse_count or better_count) else ""),
    ]

    if evidence is not None:
        missing_status = [
            name for name in ("GPU", "DRAM", "NAND(eSSD)", "HDD", "ABF", "MLCC")
            if "status" not in (evidence.get(name) or set())
        ]
        if missing_status:
            lines.append(
                "• ⚠️ 이번 주 공식 공개본문에서 상태를 직접 판독하지 못한 품목: "
                + ", ".join(html.escape(x) for x in missing_status)
                + ". 직전 확정값을 유지하며 새 상태로 추정하지 않습니다."
            )

    biggest = biggest_current_change(old, new)
    if biggest:
        name, delta = biggest
        before = old.get(name) or {}
        after = new.get(name) or {}
        change_dir = "상승" if delta > 0 else "하락"
        summary = (
            f"• <b>가장 큰 수치 변화:</b> {html.escape(name)} 리드타임 {change_dir} — "
            f"{html.escape(fmt_week(before.get('current')))} → {html.escape(fmt_week(after.get('current')))}"
        )
        if str(before.get("balanced") or "") != str(after.get("balanced") or ""):
            summary += (
                f", 균형 기준도 {html.escape(fmt_week(before.get('balanced')))}"
                f" → {html.escape(fmt_week(after.get('balanced')))}"
            )
        if fmt_status(before) == fmt_status(after):
            summary += f", 상태는 {html.escape(fmt_status(after))} 유지"
        else:
            summary += f", 상태 {html.escape(fmt_status(before))} → {html.escape(fmt_status(after))}"
        lines.append(summary)

    if strongest:
        ratio, name, entry = strongest
        lines.append(
            f"• <b>가장 강한 병목:</b> {html.escape(name)} — "
            f"현재 {html.escape(fmt_week(entry.get('current')))} / "
            f"균형 {html.escape(fmt_week(entry.get('balanced')))} / "
            f"{html.escape(fmt_status(entry))} / 균형 대비 약 {ratio:.1f}배"
        )

    if signal_only:
        lines.append("• TrendForce의 새 Weekly Radar를 감지했지만 일부 숫자 판독이 불완전합니다.")
        lines.append("• 확인되지 않은 값은 새 숫자로 만들지 않고 직전 확정값을 유지합니다.")
    elif changed:
        for name in changed:
            lines.append(
                f"• <b>{html.escape(name)}</b>: "
                f"{html.escape(fmt_change(old.get(name) or {}, new.get(name) or {}))}"
            )

    lines += ["", "<b>수익구조</b>"]
    for name in focus:
        path = REVENUE_PATHS.get(name)
        if path:
            lines.append(f"• <b>{html.escape(name)}</b>: {html.escape(path)}")

    lines += ["", "<b>1단계 현재 숫자 추적</b>"]
    order = ("GPU", "DRAM", "NAND(eSSD)", "HDD", "ABF", "MLCC")
    for name in order:
        entry = new.get(name) or old.get(name) or {}
        change = fmt_change(old.get(name) or {}, entry)
        current_text = fmt_week(entry.get("current")) + evidence_note(name, evidence, "current")
        balanced_text = fmt_week(entry.get("balanced")) + evidence_note(name, evidence, "balanced")
        status_text = fmt_status(entry) + evidence_note(name, evidence, "status")
        ratio = ratio_value(str(entry.get("current") or ""), str(entry.get("balanced") or ""))
        ratio_text = f"{ratio:.1f}배" if ratio is not None else "확인 불가"
        lines.append(
            f"• <b>{html.escape(name)}</b> | "
            f"현재 {html.escape(current_text)} | "
            f"균형 {html.escape(balanced_text)} | "
            f"격차 {html.escape(ratio_text)} | "
            f"상태 {html.escape(status_text)} | "
            f"전주 대비 {html.escape(change)}"
        )

    lines += ["", "<b>2단계 미래 재평가 요인 발굴</b>"]
    if signals:
        preferred = ("GPU", "DRAM", "NAND(eSSD)", "HDD", "ABF", "MLCC")
        shown = changed_signals if changed_signals else [name for name in preferred if name in signals]
        shown = [name for name in shown if name in signals]
        if not shown:
            shown = [name for name in focus if name in signals]
        for name in shown[:6]:
            lines.append(f"• <b>{html.escape(name)}</b>: {html.escape(signals[name])}")
    else:
        lines.append("• 이번 주 원인·시간표의 새로운 확인사항은 없습니다.")

    lines += ["", "<b>CPU·에이전트형 AI 수요축</b>"]
    cpu_parts = cpu_snapshot_summary(cpu_state)
    if cpu_parts:
        lines.append("• " + " / ".join(html.escape(x) for x in cpu_parts))
    lines.append(
        "• 수요 연결: 에이전트형 AI 노드 증가 → 서버 CPU 출하·평균판매단가 → "
        "DDR5 RDIMM·기업용 SSD·네트워크·ABF·MLCC 동반 수요"
    )
    lines.append(
        "• 기준선 변화 조건: 서버 CPU 시장·에이전트형 CPU 전망 ±10% 이상, "
        "에이전트형 비중 ±5%p 이상, CPU:GPU 구조 변화, 실제 서버 주문·배치 확인"
    )

    lines += ["", "<b>관련 기업 지도</b>"]
    lines.append("• 아래는 제품 노출 기준 관찰 대상이며, 이번 알림에서 신규 계약·수주가 확정됐다는 뜻은 아닙니다.")
    for name in focus:
        watch = COMPANY_WATCH.get(name)
        if watch:
            lines.append(f"• <b>{html.escape(name)}</b>: {html.escape(watch)}")

    lines += ["", "<b>공정 병목 후보</b>"]
    for name in focus[:3]:
        failure, indicator, risk_window = FAILURE_MODES.get(
            name, ("공급능력·수율·고객 채택 지연", "리드타임·가격·가동률", "6~12개월")
        )
        lines.append(
            f"• <b>{html.escape(name)}</b> | 실패 경로: {html.escape(failure)} | "
            f"먼저 볼 지표: {html.escape(indicator)} | 위험 구간: {html.escape(risk_window)}"
        )

    lines += ["", "<b>숨은 역풍·실패모드</b>"]
    if strongest:
        ratio, name, _ = strongest
        failure, indicator, risk_window = FAILURE_MODES.get(
            name, ("공급능력·수율·고객 채택 지연", "리드타임·가격·가동률", "6~12개월")
        )
        lines.append(
            f"• 가장 현실적인 실패 경로: <b>{html.escape(name)}</b> — {html.escape(failure)}"
        )
        lines.append(
            f"• 조기경보: {html.escape(indicator)} / 위험 구간 {html.escape(risk_window)}"
        )
        lines.append(
            "• 리드타임이 짧아져도 가격·신규수주·가동률이 유지되면 증설 효과이고, "
            "이 지표들이 함께 꺾이면 공급 부족 프리미엄 약화로 봅니다."
        )

    lines += ["", "<b>결론</b>"]
    if strongest:
        ratio, name, _ = strongest
        lines.append(
            f"• 현재 병목 중심은 <b>{html.escape(name)}</b>이며 균형 대비 약 {ratio:.1f}배입니다. "
            f"{html.escape(direction)} 여부는 다음 주 리드타임과 가격·수주·가동률을 함께 봐야 합니다."
        )
    else:
        lines.append("• 현재 공개자료만으로 병목 강도를 정량 순위화하기 어렵습니다.")

    lines += ["", "<b>핵심 한 줄 요약</b>"]
    if strongest:
        ratio, name, entry = strongest
        summary_signal = signals.get(name) or "공급능력·수요 변화"
        lines.append(
            f"• {html.escape(name)} 현재 {html.escape(fmt_week(entry.get('current')))} "
            f"vs 균형 {html.escape(fmt_week(entry.get('balanced')))}(약 {ratio:.1f}배) → "
            f"{html.escape(summary_signal)}가 핵심 원인·재평가 조건이며, "
            f"다음 확인은 리드타임·가격·신규수주·가동률입니다."
        )

    lines += [
        "",
        "<b>추적 기준</b>",
        "• 현재 리드타임·균형 리드타임·공급 상태·원인·시간표를 직전 주와 1:1 비교합니다.",
        "• 숫자가 같아도 RDIMM 수요, eSSD 생산능력 재배분, Rubin 사양 조정처럼 원인이 바뀌면 알림합니다.",
        "• 같은 주차 재파싱으로 상태를 덮어쓰지 않고, 새 Weekly Radar에서만 기준값을 승격합니다.",
        "• 확인이 불완전하면 추정값을 보내지 않고 '직전 확정값 유지·이번 주 직접 판독 미확인'으로 표시합니다.",
    ]
    if published:
        lines.append(f"• 공개시각: {html.escape(published)}")
    if source_url:
        safe_url = html.escape(source_url, quote=True)
        lines.append(f'• <a href="{safe_url}">TrendForce 원문</a>')
    return "\n".join(lines).strip() + "\n"

def main() -> None:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    state = load_json(STATE_PATH)
    pending = load_json(PENDING_PATH)
    raw_previous = repair_bad_initial_state(state.get("ai_component_leadtime") or copy.deepcopy(BASELINE))
    raw_previous_components = copy.deepcopy(raw_previous.get("components") or BASELINE["components"])
    previous, repaired_status_names = repair_weekly_002_state(raw_previous)
    previous_components = previous.get("components") or BASELINE["components"]
    seen_urls = set(previous.get("seen_urls") or [])

    candidates: list[dict] = []
    errors: list[str] = []
    cutoff = now - timedelta(days=21)

    for kind, query in SEARCHES:
        try:
            items = read_rss(kind, query)
        except Exception as exc:
            errors.append(f"{kind}: {type(exc).__name__}: {exc}")
            continue
        for item in items:
            direct = candidate_url(item)
            if not direct:
                continue
            base_text = f"{item.get('title','')} {item.get('description','')}"
            if not is_trendforce_source(direct, base_text):
                continue
            dt = None
            if item.get("published_at_kst"):
                try:
                    dt = datetime.fromisoformat(item["published_at_kst"])
                except Exception:
                    pass
            if dt is not None and dt < cutoff:
                continue
            body = article_text(direct)
            full_text = clean_text(f"{base_text} {body}")
            if not is_relevant(full_text):
                continue
            components = extract_components(full_text)
            signals = extract_signals(full_text, direct)
            candidates.append(
                {
                    **item,
                    "direct_url": direct,
                    "full_text": full_text,
                    "components": components,
                    "signals": signals,
                    "score": source_score(direct, components, full_text) + len(signals) * 3,
                }
            )

    candidates.sort(key=lambda x: (x.get("score", 0), x.get("published_at_kst") or ""), reverse=True)
    best = candidates[0] if candidates else None

    previous_signals = previous.get("signals") or BASELINE.get("signals") or {}
    latest_components = copy.deepcopy(previous_components)
    latest_signals = copy.deepcopy(previous_signals)
    latest_source = previous.get("source") or BASELINE["source"]
    latest_as_of = previous.get("as_of") or BASELINE_DATE
    notify_text = ""
    if repaired_status_names:
        notify_text = build_status_correction_alert(
            raw_previous_components,
            previous_components,
            repaired_status_names,
            str(previous.get("source") or BASELINE["source"]),
        )
    new_seen = set(seen_urls)

    if best:
        url = best.get("direct_url") or ""
        published = best.get("published_at_kst") or ""
        if url:
            new_seen.add(url)
        extracted = best.get("components") or {}
        extracted_signals = best.get("signals") or {}
        evidence = {name: set(entry.keys()) for name, entry in extracted.items()}

        merged = copy.deepcopy(previous_components)
        for name, entry in extracted.items():
            old_entry = dict(merged.get(name) or {})
            for key in ("status", "current", "balanced"):
                if entry.get(key):
                    old_entry[key] = entry[key]
            merged[name] = old_entry

        merged_signals = copy.deepcopy(previous_signals)
        merged_signals.update({k: v for k, v in extracted_signals.items() if v})
        changed = changed_components(previous_components, merged)
        changed_signals = [
            name for name, value in extracted_signals.items()
            if value and str(previous_signals.get(name) or "") != str(value)
        ]
        published_date = published[:10] if published else ""
        previous_as_of = str(previous.get("as_of") or BASELINE_DATE)
        is_new_url = bool(url and url not in seen_urls)
        is_new_release = bool(published_date and published_date > previous_as_of)
        exact_weekly_signal = (
            "current vs balanced" in (best.get("full_text") or "").lower()
            or "six ai infrastructure components" in (best.get("full_text") or "").lower()
            or "weekly radar" in (best.get("title") or "").lower()
        )

        # 이미 저장한 같은 주차/과거 주차 자료를 다시 파싱해 상태를 덮어쓰지 않는다.
        # 새 주차(발행일이 직전 기준일보다 뒤)일 때만 숫자·상태·원인 신호를 승격한다.
        if is_new_release and (changed or changed_signals):
            fresh_alert = build_alert(
                previous_components,
                merged,
                changed,
                url,
                published,
                signal_only=False,
                signals=merged_signals,
                # 새 Weekly Radar에서는 이번 주 확인된 원인·병목 신호를 모두 보여준다.
                changed_signals=[name for name in ("GPU", "DRAM", "NAND(eSSD)", "HDD", "ABF", "MLCC") if name in extracted_signals],
                evidence=evidence,
            )
            notify_text = (notify_text.rstrip() + "\n\n" + fresh_alert.strip()).strip() + "\n" if notify_text else fresh_alert
            latest_components = merged
            latest_signals = merged_signals
            latest_source = url or latest_source
            latest_as_of = published_date
        elif is_new_release and is_new_url and exact_weekly_signal:
            fresh_alert = build_alert(
                previous_components,
                merged,
                [],
                url,
                published,
                signal_only=True,
                signals=extracted_signals,
                changed_signals=[name for name in ("GPU", "DRAM", "NAND(eSSD)", "HDD", "ABF", "MLCC") if name in extracted_signals],
                evidence=evidence,
            )
            notify_text = (notify_text.rstrip() + "\n\n" + fresh_alert.strip()).strip() + "\n" if notify_text else fresh_alert
            latest_signals = merged_signals
            latest_source = url or latest_source
            latest_as_of = published_date

    pending["ai_component_leadtime"] = {
        "as_of": latest_as_of,
        "source": latest_source,
        "components": latest_components,
        "signals": latest_signals,
        "seen_urls": sorted(new_seen)[-120:],
        "last_checked_at_kst": now.isoformat(timespec="seconds"),
        "candidate_count": len(candidates),
        "errors": errors[-10:],
    }
    write_json(PENDING_PATH, pending)

    if notify_text:
        existing = ALERT_PATH.read_text(encoding="utf-8").strip() if ALERT_PATH.exists() else ""
        merged_alert = (existing + "\n\n" + notify_text.strip()).strip() if existing else notify_text.strip()
        ALERT_PATH.write_text(merged_alert + "\n", encoding="utf-8")

    print(
        "ai_component_leadtime_watch=true "
        f"candidates={len(candidates)} notify={str(bool(notify_text)).lower()} "
        f"source={best.get('direct_url') if best else 'none'}"
    )


if __name__ == "__main__":
    main()
