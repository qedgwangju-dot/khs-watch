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
UA = "Mozilla/5.0 (compatible; EnhertuALT-B4Watch/1.0)"
STATE = Path("data/enhertu_altb4_watch_state.json")
OUT = Path("out")
PENDING = OUT / "enhertu_altb4_watch_state_pending.json"
ALERT = OUT / "enhertu_altb4_alert.md"
STATUS = OUT / "enhertu_altb4_status.md"
NEWS_MAX_AGE_DAYS = 10

CURRENT_AZ_TITLE = (
    "Enhertu plus pertuzumab approved in the EU as first new regimen in more than a decade "
    "for first-line treatment of patients with HER2-positive metastatic breast cancer"
)
CURRENT_AZ_URL = (
    "https://www.astrazeneca.com/media-centre/press-releases/2026/"
    "enhertu-approved-in-eu-for-1l-her2-positive-mbc.html"
)

QUERIES = [
    '"Enhertu" pertuzumab EU approval',
    '"Enhertu" first line HER2 positive metastatic breast cancer',
    '"Enhertu" DESTINY-Breast09 approval',
    '"Enhertu" FDA approval indication',
    '"Enhertu" EMA approval indication',
    '"Enhertu" sales revenue Daiichi Sankyo',
    '"Enhertu" subcutaneous ALT-B4',
    '"Enhertu" NCT07015697',
    '"trastuzumab deruxtecan" subcutaneous Hybrozyme',
    '"Enhertu" Alteogen',
    '"엔허투" 승인 알테오젠',
]

OFFICIAL_DOMAINS = (
    "astrazeneca.com", "daiichisankyo.com", "daiichi-sankyo.eu",
    "fda.gov", "ema.europa.eu", "ec.europa.eu", "alteogen.com", "clinicaltrials.gov", "sec.gov"
)
TRIGGER_TERMS = ("enhertu", "trastuzumab deruxtecan", "엔허투")
MATERIAL_TERMS = (
    "approval", "approved", "recommended", "chmp", "ema", "european commission", "fda",
    "first-line", "first line", "1st-line", "1l", "indication", "regulatory", "submission",
    "destiny-breast09", "destiny-breast05", "phase 3", "phase iii", "pfs", "overall survival",
    "objective response", "orr", "hazard ratio", "sales", "revenue",
    "subcutaneous", "alt-b4", "hybrozyme", "nct07015697", "피하주사", "허가", "승인", "매출",
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
        stamp = parse_published(self.published)
        day = stamp.date().isoformat() if stamp else ""
        return digest(f"{normalize(self.title)}|{day}|{self.canonical}")


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
            if not k.lower().startswith("utm_")
            and k.lower() not in {"ocid", "ref", "source", "cmpid", "cid", "oc"}
        ]
        return urllib.parse.urlunparse(
            (p.scheme.lower(), host, p.path.rstrip("/"), "", urllib.parse.urlencode(q), "")
        )
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


def fetch(url: str, timeout: int = 25, limit: int = 1_500_000) -> tuple[str, str]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read(limit)
        enc = r.headers.get_content_charset() or "utf-8"
        final = r.geturl()
    return raw.decode(enc, errors="replace"), final


def strip_html(value: str) -> str:
    value = re.sub(r"(?is)<script.*?</script>|<style.*?</style>|<noscript.*?</noscript>", " ", value)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def extract_article_text(page: str) -> str:
    candidates: list[str] = []
    for block in re.findall(
        r"(?is)<script[^>]+type=[\"\']application/ld\+json[\"\'][^>]*>(.*?)</script>", page
    ):
        try:
            data = json.loads(html.unescape(block.strip()))
        except Exception:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            obj = stack.pop()
            if isinstance(obj, dict):
                body = obj.get("articleBody")
                if isinstance(body, str) and len(body) > 250:
                    candidates.append(body)
                graph = obj.get("@graph")
                if isinstance(graph, list):
                    stack.extend(graph)
            elif isinstance(obj, list):
                stack.extend(obj)
    for article in re.findall(r"(?is)<article\b[^>]*>(.*?)</article>", page):
        text = strip_html(article)
        if len(text) > 300:
            candidates.append(text)
    paras = [strip_html(x) for x in re.findall(r"(?is)<p\b[^>]*>(.*?)</p>", page)]
    paras = [x for x in paras if 45 <= len(x) <= 3000]
    if paras:
        joined = " ".join(paras)
        if len(joined) > 300:
            candidates.append(joined)
    if not candidates:
        return ""
    return re.sub(r"\s+", " ", max(candidates, key=len)).strip()[:20000]


def rss(query: str, engine: str) -> list[Item]:
    if engine == "Google News":
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
            {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
        )
    else:
        url = "https://www.bing.com/news/search?" + urllib.parse.urlencode({"q": query, "format": "rss"})
    xml, _ = fetch(url, timeout=20, limit=800_000)
    root = ET.fromstring(xml)
    out: list[Item] = []
    for node in root.findall(".//item")[:30]:
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        pub = (node.findtext("pubDate") or "").strip()
        desc = strip_html(node.findtext("description") or "")
        if link:
            out.append(Item(engine, title, link, pub, desc))
    return out


def official_items() -> list[Item]:
    return [Item("AstraZeneca 공식", CURRENT_AZ_TITLE, CURRENT_AZ_URL, "")]


def is_recent(item: Item) -> bool:
    if item.source.endswith("공식"):
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
    if item.source.endswith("공식") or any(host.endswith(d) for d in OFFICIAL_DOMAINS):
        return "공식자료"
    return "2차 자료"


def event_key(item: Item) -> str:
    low = item.full.lower()
    klass = source_class(item)
    if "destiny-breast09" in low or ("pertuzumab" in low and any(x in low for x in ("first-line", "first line", "1st-line"))):
        indication = "her2_mbc_1l"
    elif "destiny-breast05" in low:
        indication = "her2_early_residual"
    else:
        indication = "other"

    if any(x in low for x in ("approved in the eu", "european commission approval", "eu approval")):
        stage = "eu_approved"
    elif "chmp" in low and "recommended" in low:
        stage = "chmp_positive"
    elif "fda" in low and any(x in low for x in ("approved", "approval")):
        stage = "fda_approved"
    elif any(x in low for x in ("subcutaneous", "alt-b4", "hybrozyme", "nct07015697", "피하주사")):
        stage = "sc_altb4"
    elif any(x in low for x in ("sales", "revenue", "매출")):
        stage = "sales"
    elif any(x in low for x in ("phase 3", "phase iii", "pfs", "overall survival", "orr")):
        stage = "clinical_update"
    else:
        stage = "material"
    return digest(f"enhertu|{indication}|{stage}|{klass}")


def rank_item(item: Item) -> tuple[int, int]:
    official = 0 if source_class(item) == "공식자료" else 1
    direct = 0 if any(x in item.canonical for x in ("astrazeneca.com", "daiichisankyo.com", "daiichi-sankyo.eu")) else 1
    return official, direct


def collect() -> tuple[list[Item], list[str]]:
    items: list[Item] = []
    errors: list[str] = []
    items.extend(official_items())
    for q in QUERIES:
        for engine in ("Google News", "Bing News"):
            try:
                items.extend(rss(q, engine))
            except Exception as exc:
                errors.append(f"{engine} {q}: {type(exc).__name__}: {exc}")
    unique: dict[str, Item] = {}
    for item in items:
        if is_recent(item) and is_relevant(item):
            unique.setdefault(item.key, item)
    return list(unique.values()), errors


def fetch_body(item: Item) -> tuple[str, str]:
    url = item.canonical
    try:
        page, final = fetch(url, timeout=20)
        return extract_article_text(page), canonicalize_url(final or url)
    except Exception:
        return "", url


def find_metric(pattern: str, text: str) -> str:
    m = re.search(pattern, text, re.I)
    return m.group(1) if m else ""


def build_item_summary(item: Item) -> str:
    body, resolved = fetch_body(item)
    full = f"{item.full} {body}".strip()
    low = full.lower()
    official = source_class(item) == "공식자료"

    is_1l_eu = (
        any(x in low for x in ("approved in the european union", "approved in the eu", "eu approval"))
        and "pertuzumab" in low
        and any(x in low for x in ("first-line", "first line", "1st-line"))
        and ("her2" in low and "breast cancer" in low)
    )

    headline = (
        "Enhertu+pertuzumab, EU HER2+ 전이성 유방암 1차 치료 승인"
        if is_1l_eu
        else "Enhertu 규제·임상 업데이트"
    )

    hr = find_metric(r"hazard ratio\s*[:=]?\s*(0?\.\d+)", full)
    risk = find_metric(r"reduced the risk[^.]{0,100}?by\s+(\d{1,2})%", full)
    pfs_combo = find_metric(r"median progression[- ]free survival[^.]{0,120}?(40\.7)\s+months", full)
    pfs_thp = find_metric(r"compared to\s+(26\.9)\s+months", full)
    orr_combo = find_metric(r"objective response rate[^.]{0,100}?(85\.1)%", full)
    orr_thp = find_metric(r"compared to\s+(78\.6)%", full)

    approval_parts: list[str] = []
    if is_1l_eu:
        approval_parts.append("유럽연합 집행위원회 승인")
        approval_parts.append("HER2+ 절제불가·전이성 유방암 1차 치료")
        if "more than a decade" in low:
            approval_parts.append("10년 넘게 유지된 THP 이후 첫 신규 1차 치료요법")
    approval_line = " · ".join(approval_parts) if approval_parts else "허가 단계 추가 확인 필요"

    trial_parts: list[str] = []
    if "destiny-breast09" in low:
        trial_parts.append("DESTINY-Breast09 3상")
    if risk:
        trial_parts.append(f"질병 진행·사망 위험 {risk}% 감소")
    if hr:
        trial_parts.append(f"HR {hr}")
    if pfs_combo and pfs_thp:
        trial_parts.append(f"중앙값 PFS {pfs_combo}개월 vs THP {pfs_thp}개월")
    if orr_combo and orr_thp:
        trial_parts.append(f"ORR {orr_combo}% vs {orr_thp}%")
    trial_line = " · ".join(trial_parts) if trial_parts else "임상 핵심 수치 추가 확인 필요"

    alteogen_line = (
        "이번 승인은 정맥주사 Enhertu 병용요법의 적응증 확대이며 ALT-B4 피하주사 허가 자체는 아닙니다. "
        "다만 1차 치료로 사용 범위가 앞당겨지면 향후 ALT-B4 기반 Enhertu 피하주사가 성공할 경우 전환 가능한 치료 횟수·환자·매출 기반이 커집니다."
    )

    sc_line = (
        "Daiichi Sankyo는 ALT-B4를 적용한 Enhertu 피하주사 임상 1상(NCT07015697)을 진행 중. "
        "알테오젠 계약은 로열티 제외 최대 3억달러 규모이며 상업화 시 단계별 판매 로열티가 별도입니다."
    )

    lines = [
        f"**{headline}**",
        "",
        f"- **승인:** {approval_line}",
        "",
        f"- **3상:** {trial_line}",
        "",
        f"- **알테오젠:** {alteogen_line}",
        "",
        f"- **SC 연결:** {sc_line}",
        "",
        "- **다음 확인:** Enhertu 피하주사 임상 1상 데이터 → 후속 임상 → 허가 신청·승인 → 판매 로열티 기반 확대",
        "",
        f"- **원문 확인:** {'공식자료 본문 직접 열람' if official and body else ('기사 본문 직접 열람' if body else '원문 본문 자동 추출 불완전')}",
        f"- 원문: {resolved}",
    ]
    return "\n".join(lines)


def load_state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"initialized": False, "seen_keys": [], "seen_event_keys": []}


def cap(values: set[str], limit: int = 4000) -> list[str]:
    return sorted(values)[-limit:]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    state = load_state()
    items, errors = collect()
    now = dt.datetime.now(KST).isoformat(timespec="seconds")

    seen = set(state.get("seen_keys") or [])
    seen_events = set(state.get("seen_event_keys") or [])

    by_event: dict[str, Item] = {}
    for item in sorted(items, key=rank_item):
        ekey = event_key(item)
        if ekey not in by_event:
            by_event[ekey] = item

    new_items: list[Item] = []
    first_run = not state.get("initialized")
    for ekey, item in by_event.items():
        if item.key in seen or ekey in seen_events:
            seen.add(item.key)
            seen_events.add(ekey)
            continue
        if first_run:
            current = (
                "astrazeneca.com" in item.canonical
                and "enhertu-approved-in-eu-for-1l-her2-positive-mbc" in item.canonical
            ) or (
                "pertuzumab" in item.full.lower()
                and "approved" in item.full.lower()
                and "eu" in item.full.lower()
                and (parse_published(item.published) is None or is_recent(item))
            )
            if not current:
                seen.add(item.key)
                seen_events.add(ekey)
                continue
        new_items.append(item)
        seen.add(item.key)
        seen_events.add(ekey)

    if new_items:
        summaries = [build_item_summary(x) for x in new_items[:5]]
        ALERT.write_text(
            "[바이오 감시] Enhertu 새 데이터\n\n" + "\n\n".join(summaries) + "\n",
            encoding="utf-8",
        )
    elif ALERT.exists():
        ALERT.unlink()

    state["initialized"] = True
    state.setdefault("initialized_at_kst", now)
    state["last_check_kst"] = now
    state["seen_keys"] = cap(seen)
    state["seen_event_keys"] = cap(seen_events)
    PENDING.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    status = f"Enhertu ALT-B4 감시 정상 — {now}; 신규={len(new_items)}, 후보={len(items)}, 사건중복키={len(seen_events)}"
    if errors:
        status += f"; 검색오류={len(errors)}"
        (OUT / "enhertu_altb4_errors.log").write_text("\n".join(errors) + "\n", encoding="utf-8")
    STATUS.write_text(status + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
