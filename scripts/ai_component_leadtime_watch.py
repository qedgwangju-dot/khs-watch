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

    # 예: "균형 상태인 품목은 GPU뿐"
    for m in re.finditer(
        r"(심각한 공급 부족|공급 제약(?: 상태)?|균형 상태|Very\s+Tight|Tight|Balanced)"
        rf"[^.\n]{{0,50}}?(?:품목(?:은|이)?\s*)?{group}",
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
) -> str:
    signals = signals or {}
    changed_signals = changed_signals or []
    lines = ["<b>🚨 AI 부품 리드타임 감시 — 변화 감지</b>", "", "<b>무엇이 달라졌나</b>"]

    if evidence is not None:
        missing_status = [name for name in ("GPU", "DRAM", "NAND(eSSD)", "HDD", "ABF", "MLCC")
                          if "status" not in (evidence.get(name) or set())]
        if missing_status:
            lines.append(
                "• ⚠️ 이번 주 공식 공개본문에서 상태를 직접 판독하지 못한 품목: "
                + ", ".join(html.escape(x) for x in missing_status)
                + ". 해당 상태는 직전 확정값을 유지하며 새 상태로 추정하지 않습니다."
            )

    biggest = biggest_current_change(old, new)
    if biggest:
        name, delta = biggest
        before = old.get(name) or {}
        after = new.get(name) or {}
        direction = "상승" if delta > 0 else "하락"
        summary = (
            f"• <b>가장 큰 수치 변화:</b> {html.escape(name)} 리드타임 {direction} — "
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

    if signal_only:
        lines.append("• TrendForce의 새 Weekly Radar를 감지했습니다.")
        lines.append("• 새 표의 숫자 자동 판독이 불완전해 직전 확정값을 임의로 바꾸지 않았습니다.")
    elif changed:
        for name in changed:
            lines.append(
                f"• <b>{html.escape(name)}</b>: "
                f"{html.escape(fmt_change(old.get(name) or {}, new.get(name) or {}))}"
            )

    if signals:
        lines += ["", "<b>이번 주 새 원인·병목 신호</b>"]
        preferred = ("GPU", "DRAM", "NAND(eSSD)", "HDD", "ABF", "MLCC")
        shown = changed_signals if changed_signals else [name for name in preferred if name in signals]
        for name in shown:
            if name in signals:
                lines.append(f"• <b>{html.escape(name)}</b>: {html.escape(signals[name])}")

    lines += ["", "<b>현재 6개 품목 상태</b>"]
    order = ("GPU", "DRAM", "NAND(eSSD)", "HDD", "ABF", "MLCC")
    for name in order:
        entry = new.get(name) or old.get(name) or {}
        change = fmt_change(old.get(name) or {}, entry)
        current_text = fmt_week(entry.get("current")) + evidence_note(name, evidence, "current")
        balanced_text = fmt_week(entry.get("balanced")) + evidence_note(name, evidence, "balanced")
        status_text = fmt_status(entry) + evidence_note(name, evidence, "status")
        lines.append(
            f"• <b>{html.escape(name)}</b> | "
            f"현재 {html.escape(current_text)} | "
            f"균형 {html.escape(balanced_text)} | "
            f"상태 {html.escape(status_text)} | "
            f"전주 대비 {html.escape(change)}"
        )

    ranked = []
    for name, entry in (new or old).items():
        ratio = ratio_value(str(entry.get("current") or ""), str(entry.get("balanced") or ""))
        if ratio is not None:
            ranked.append((ratio, name, entry))
    ranked.sort(reverse=True)

    lines += ["", "<b>현재 판정</b>"]
    if ranked:
        ratio, name, entry = ranked[0]
        lines.append(
            f"• 가장 강한 병목: <b>{html.escape(name)}</b> — "
            f"{html.escape(fmt_entry(entry))}, 균형 대비 약 {ratio:.1f}배"
        )
    else:
        lines.append("• 새 업데이트 자체는 확인했지만 수치 비교는 확인 불가입니다.")

    lines += [
        "",
        "<b>추적 기준</b>",
        "• 현재 리드타임, 균형 리드타임, 공급 상태와 원인·병목 신호를 직전 주와 1:1 비교합니다.",
        "• 숫자가 그대로여도 RDIMM 수요, eSSD 생산능력 재배분, Rubin 사양 조정처럼 원인이 바뀌면 알림합니다.",
        "• 새 Weekly Radar인데 숫자 또는 원인 문구 판독이 불완전하면 임의 추정하지 않고 별도 경고합니다.",
    ]
    if published:
        lines.append(f"• 공개시각: {html.escape(published)}")
    if source_url:
        safe_url = html.escape(source_url, quote=True)
        lines.append(f'• <a href="{safe_url}">원문</a>')
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
