from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
UTC = dt.timezone.utc
UA = "Mozilla/5.0 (compatible; IntismeranQlexWatch/1.1)"
STATE = Path("data/intismeran_qlex_watch_state.json")
OUT = Path("out")
PENDING = OUT / "intismeran_qlex_watch_state_pending.json"
ALERT = OUT / "intismeran_qlex_alert.md"
STATUS = OUT / "intismeran_qlex_status.md"
NEWS_MAX_AGE_DAYS = 10

QUERIES = [
    '"INTerpath-001" intismeran RFS DMFS',
    '"INTerpath-001" phase 3 topline',
    '"INTerpath-001" hazard ratio',
    '"intismeran autogene" FDA submission melanoma',
    '"mRNA-4157" FDA submission melanoma',
    '"intismeran" FDA approval KEYTRUDA',
    '"INTerpath-014" pembrolizumab berahyaluronidase',
    '"INTerpath-014" KEYTRUDA QLEX',
    '"인티스메란" 3상 흑색종',
    '"INTerpath-001" FDA',
]

OFFICIAL_DOMAINS = ("merck.com", "modernatx.com", "investors.modernatx.com", "clinicaltrials.gov", "fda.gov")
TRIGGER_TERMS = (
    "interpath-001", "intismeran", "mrna-4157", "v940",
    "interpath-014", "nct05933577", "nct07513376",
)
MATERIAL_TERMS = (
    "phase 3", "3상", "topline", "rfs", "dmfs", "overall survival", "os ",
    "hazard ratio", "hr=", "hr ", "met primary", "met the primary", "primary endpoint",
    "fda", "submission", "filed", "filing", "accepted", "pdufa", "approval", "approved",
    "regulatory", "sbla", "bla", "supplemental biologics license",
    "subcutaneous", "berahyaluronidase", "keytruda qlex", "피하주사", "허가",
)


@dataclass
class Item:
    source: str
    title: str
    url: str
    published: str = ""
    text: str = ""

    @property
    def full(self) -> str:
        return f"{self.title} {self.text}".strip()

    @property
    def canonical(self) -> str:
        return canonicalize_url(self.url)

    @property
    def key(self) -> str:
        day = ""
        stamp = parse_published(self.published)
        if stamp:
            day = stamp.date().isoformat()
        return digest(f"{normalize(self.title)}|{day}|{self.canonical}")

    @property
    def semantic_key(self) -> str:
        nums = "|".join(metric_tokens(self.full))
        return digest(f"{normalize(self.title)}|{nums}")


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def normalize(value: str) -> str:
    value = html.unescape(value).lower()
    value = re.sub(r"[^0-9a-z가-힣]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def canonicalize_url(url: str) -> str:
    try:
        p = urllib.parse.urlparse(html.unescape(url))
        host = p.netloc.lower()
        if host.endswith("bing.com") and p.path.endswith("/news/apiclick.aspx"):
            target = urllib.parse.parse_qs(p.query).get("url", [""])[0]
            if target.startswith(("http://", "https://")):
                return canonicalize_url(target)
        q = [
            (k, v) for k, v in urllib.parse.parse_qsl(p.query)
            if not k.lower().startswith("utm_") and k.lower() not in {"ocid", "ref", "source"}
        ]
        return urllib.parse.urlunparse((p.scheme.lower(), host, p.path.rstrip("/"), "", urllib.parse.urlencode(q), ""))
    except Exception:
        return url


def parse_published(value: str) -> dt.datetime | None:
    if not value:
        return None
    try:
        stamp = parsedate_to_datetime(value)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=UTC)
        return stamp.astimezone(UTC)
    except Exception:
        return None


def fetch(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9,ko;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        enc = r.headers.get_content_charset() or "utf-8"
    return raw.decode(enc, errors="replace")


def strip_html(value: str) -> str:
    value = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", value)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def rss(query: str, engine: str) -> list[Item]:
    if engine == "Google News":
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    else:
        url = "https://www.bing.com/news/search?" + urllib.parse.urlencode({"q": query, "format": "rss"})
    root = ET.fromstring(fetch(url))
    out: list[Item] = []
    for node in root.findall(".//item")[:30]:
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        pub = (node.findtext("pubDate") or "").strip()
        desc = strip_html(node.findtext("description") or "")
        if link:
            out.append(Item(engine, title, link, pub, desc))
    return out


def clinical_trial(nct: str) -> dict:
    return json.loads(fetch(f"https://clinicaltrials.gov/api/v2/studies/{nct}"))


def trial_snapshot(nct: str) -> dict:
    try:
        data = clinical_trial(nct)
        p = data.get("protocolSection", {})
        design = p.get("designModule", {})
        status = p.get("statusModule", {})
        return {
            "nct": nct,
            "overallStatus": status.get("overallStatus"),
            "enrollment": (design.get("enrollmentInfo") or {}).get("count"),
            "enrollmentType": (design.get("enrollmentInfo") or {}).get("type"),
            "startDate": (status.get("startDateStruct") or {}).get("date"),
            "primaryCompletion": (status.get("primaryCompletionDateStruct") or {}).get("date"),
            "completion": (status.get("completionDateStruct") or {}).get("date"),
            "lastUpdate": (status.get("studyFirstPostDateStruct") or {}).get("date"),
        }
    except Exception as exc:
        return {"nct": nct, "error": str(exc)}


def metric_tokens(text: str) -> list[str]:
    pats = (
        r"\bHR\s*[=:]?\s*0?\.\d+",
        r"\b\d{1,3}(?:\.\d+)?\s*%",
        r"\bN\s*[=:]?\s*\d{2,5}\b",
        r"\b\d{3,5}\s*(?:participants|patients|명)\b",
        r"\b20\d{2}-\d{2}-\d{2}\b",
    )
    vals: list[str] = []
    for pat in pats:
        for m in re.finditer(pat, text, re.I):
            v = re.sub(r"\s+", " ", m.group(0)).strip()
            if v not in vals:
                vals.append(v)
    return vals[:15]


def is_recent(item: Item) -> bool:
    if item.source not in ("Google News", "Bing News"):
        return True
    stamp = parse_published(item.published)
    if stamp is None:
        return True
    age = dt.datetime.now(UTC) - stamp
    return dt.timedelta(days=-1) <= age <= dt.timedelta(days=NEWS_MAX_AGE_DAYS)


def is_relevant(item: Item) -> bool:
    low = item.full.lower()
    return any(t in low for t in TRIGGER_TERMS) and any(t.lower() in low for t in MATERIAL_TERMS)


def source_class(item: Item) -> str:
    host = urllib.parse.urlparse(item.canonical).netloc.lower()
    if any(host.endswith(d) for d in OFFICIAL_DOMAINS):
        return "공식"
    return "2차 자료"


def extract_hr(text: str, label: str) -> str | None:
    patterns = [
        rf"{label}[^\n]{{0,220}}?HR\s*[=:]?\s*(0?\.\d+)",
        rf"HR\s*[=:]?\s*(0?\.\d+)[^\n]{{0,220}}?{label}",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            return m.group(1)
    return None


def looks_like_phase3_result(item: Item) -> bool:
    low = item.full.lower()
    return "interpath-001" in low and ("phase 3" in low or "3상" in low) and any(
        k in low for k in ("rfs", "dmfs", "primary endpoint", "topline", "met endpoint", "meets endpoint")
    )


def looks_like_regulatory(item: Item) -> bool:
    low = item.full.lower()
    return any(k in low for k in ("fda", "sbla", "submission", "filing", "accepted", "pdufa", "approval", "허가")) and any(
        k in low for k in ("intismeran", "mrna-4157", "v940", "interpath-001")
    )


def looks_like_sc_link(item: Item) -> bool:
    low = item.full.lower()
    return "interpath-014" in low and any(k in low for k in ("subcutaneous", "berahyaluronidase", "keytruda qlex", "피하주사"))


def event_key(item: Item) -> str | None:
    """Deduplicate one clinical/regulatory event across many news outlets, while allowing official upgrades/new HRs."""
    low = item.full.lower()
    klass = source_class(item)
    hrs = sorted(set(re.findall(r"\bHR\s*[=:]?\s*(0?\.\d+)", item.full, re.I)))

    if looks_like_phase3_result(item):
        if hrs:
            base = "interpath001_phase3_hr_" + "_".join(hrs)
        else:
            base = "interpath001_phase3_endpoints_met"
        return digest(f"{base}|{klass}")

    if looks_like_regulatory(item):
        if "approved" in low or "approval" in low:
            stage = "approved"
        elif "pdufa" in low:
            stage = "pdufa"
        elif "accepted" in low:
            stage = "accepted"
        elif "submission" in low or "filed" in low or "filing" in low:
            stage = "submitted"
        else:
            stage = "regulatory"
        return digest(f"interpath001_{stage}|{klass}")

    if looks_like_sc_link(item):
        nums = "|".join(metric_tokens(item.full))
        return digest(f"interpath014_sc_update|{nums}|{klass}")

    return None


def load_state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"initialized": False, "seen": [], "seen_semantic": [], "seen_event_keys": [], "trials": {}}


def cap(values: set[str], limit: int = 5000) -> list[str]:
    return sorted(values)[-limit:]


def collect() -> list[Item]:
    items: list[Item] = []
    errors: list[str] = []
    for q in QUERIES:
        for engine in ("Google News", "Bing News"):
            try:
                items.extend(rss(q, engine))
            except Exception as exc:
                errors.append(f"{engine} {q}: {exc}")
    unique: dict[str, Item] = {}
    for item in items:
        unique.setdefault(item.key, item)
    if errors:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "intismeran_qlex_errors.log").write_text("\n".join(errors) + "\n", encoding="utf-8")
    return list(unique.values())


def build_alert(new_items: list[Item], trial_changes: list[str]) -> str:
    lines = ["[바이오 감시] Intismeran·KEYTRUDA QLEX 새 데이터", ""]
    idx = 1
    for item in new_items[:8]:
        klass = source_class(item)
        rfs = extract_hr(item.full, "RFS")
        dmfs = extract_hr(item.full, "DMFS")
        os_hr = extract_hr(item.full, "OS")
        lines.append(f"{idx}. {item.title}")
        lines.append(f"- 출처 구분: {klass}")
        if item.published:
            lines.append(f"- 발표/게시: {item.published}")
        if looks_like_phase3_result(item):
            lines.append("- 핵심: INTerpath-001 3상 효능 결과 후보입니다. 2b상 KEYNOTE-942의 기존 HR과 섞지 않습니다.")
            if rfs:
                lines.append(f"- 3상 RFS HR 후보: {rfs}")
            if dmfs:
                lines.append(f"- 3상 DMFS HR 후보: {dmfs}")
            if os_hr:
                lines.append(f"- 3상 OS HR 후보: {os_hr}")
        if looks_like_regulatory(item):
            lines.append("- 허가 경로: FDA 제출·접수·PDUFA·승인 중 어느 단계인지 구분해 추적합니다.")
        if looks_like_sc_link(item):
            lines.append("- 알테오젠 연결: INTerpath-014는 Intismeran과 Pembrolizumab+berahyaluronidase alfa 피하주사를 직접 시험하는 별도 3상입니다.")
        if klass == "공식":
            lines.append("- 판정: 공식자료 확인치")
        else:
            lines.append("- 판정: 2차 자료. Merck·Moderna·ClinicalTrials.gov·FDA 중 최소 1곳의 공식 확인 전에는 확정하지 않습니다.")
        lines.append("- 알테오젠 관점: Intismeran 성공은 KEYTRUDA 병용 수요 기반을 넓힐 수 있지만, 곧바로 QLEX 매출이 늘어난다는 뜻은 아닙니다. 실제 QLEX/피하주사 적용 적응증·임상·허가 확대가 확인돼야 판매 마일스톤·후속 로열티 기반으로 연결됩니다.")
        lines.append(f"- 원문: {item.canonical}")
        lines.append("")
        idx += 1
    if trial_changes:
        lines.append("임상등록 변경")
        for change in trial_changes:
            lines.append(f"- {change}")
        lines.append("")
    lines.append("판정")
    lines.append("- INTerpath-001: 3상 톱라인에서 RFS·DMFS 평가변수 달성은 발표됐습니다. 정확한 3상 HR·위험감소율·OS는 아직 미공개이므로 후속 학회 수치를 별도 추적합니다.")
    lines.append("- 기존 2b상 5년 추적: RFS HR 0.51, DMFS HR 0.411은 배경자료일 뿐 새 3상 결과가 아닙니다.")
    lines.append("- INTerpath-014: 약 876명 폐암 3상에서 Intismeran+Pembrolizumab/berahyaluronidase alfa 피하주사 경로를 직접 추적합니다.")
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    state = load_state()
    items = [x for x in collect() if is_recent(x) and is_relevant(x)]
    current_trials = {
        "NCT05933577": trial_snapshot("NCT05933577"),
        "NCT07513376": trial_snapshot("NCT07513376"),
    }

    seen = set(state.get("seen") or [])
    seen_semantic = set(state.get("seen_semantic") or [])
    seen_events = set(state.get("seen_event_keys") or [])
    now = dt.datetime.now(KST).isoformat(timespec="seconds")

    if not state.get("initialized"):
        state["initialized"] = True
        state["initialized_at_kst"] = now
        state["seen"] = cap({x.key for x in items})
        state["seen_semantic"] = cap({x.semantic_key for x in items})
        state["seen_event_keys"] = cap({k for x in items if (k := event_key(x))})
        state["trials"] = current_trials
        state["last_check_kst"] = now
        PENDING.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        STATUS.write_text("Intismeran 감시 초기 기준선 저장 완료 — 기존 2b상 자료는 새 알림으로 보내지 않음.\n", encoding="utf-8")
        return 0

    # Migration from pre-event-dedupe state: mark all currently visible repeated stories as already represented.
    if "seen_event_keys" not in state:
        seen_events.update(k for x in items if (k := event_key(x)))

    new_items: list[Item] = []
    for item in items:
        ekey = event_key(item)
        if item.key in seen or item.semantic_key in seen_semantic or (ekey and ekey in seen_events):
            seen.add(item.key)
            seen_semantic.add(item.semantic_key)
            if ekey:
                seen_events.add(ekey)
            continue
        new_items.append(item)
        seen.add(item.key)
        seen_semantic.add(item.semantic_key)
        if ekey:
            seen_events.add(ekey)

    trial_changes: list[str] = []
    previous_trials = state.get("trials") or {}
    for nct, snap in current_trials.items():
        prev = previous_trials.get(nct) or {}
        for field in ("overallStatus", "enrollment", "primaryCompletion", "completion"):
            if prev.get(field) not in (None, "") and snap.get(field) not in (None, "") and prev.get(field) != snap.get(field):
                trial_changes.append(f"{nct} {field}: {prev.get(field)} → {snap.get(field)}")

    if new_items or trial_changes:
        ALERT.write_text(build_alert(new_items, trial_changes), encoding="utf-8")
    elif ALERT.exists():
        ALERT.unlink()

    state["seen"] = cap(seen)
    state["seen_semantic"] = cap(seen_semantic)
    state["seen_event_keys"] = cap(seen_events)
    state["trials"] = current_trials
    state["last_check_kst"] = now
    PENDING.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    STATUS.write_text(
        f"Intismeran 감시 정상 — {now}; 신규={len(new_items)}, 임상등록변경={len(trial_changes)}, 사건중복키={len(seen_events)}\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
