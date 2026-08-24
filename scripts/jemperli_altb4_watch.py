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
UA = "Mozilla/5.0 (compatible; JemperliALT-B4Watch/1.0)"
STATE = Path("data/jemperli_altb4_watch_state.json")
OUT = Path("out")
PENDING = OUT / "jemperli_altb4_watch_state_pending.json"
ALERT = OUT / "jemperli_altb4_alert.md"
STATUS = OUT / "jemperli_altb4_status.md"
NEWS_MAX_AGE_DAYS = 10

CURRENT_GSK_PR = (
    "Jemperli (dostarlimab) accepted for priority review by the US FDA "
    "for dMMR/MSI-H locally advanced rectal cancer"
)
CURRENT_GSK_URL = (
    "https://www.gsk.com/en-gb/media/press-releases/"
    "jemperli-dostarlimab-accepted-for-priority-review-by-the-us-fda/"
)

QUERIES = [
    '"Jemperli" dostarlimab FDA GSK',
    '"Jemperli" priority review rectal cancer',
    '"Jemperli" PDUFA',
    '"Jemperli" sBLA',
    '"Jemperli" approval FDA',
    '"Jemperli" AZUR-1',
    '"Jemperli" AZUR-2',
    '"Jemperli" AZUR-4',
    '"Jemperli" DOMENICA',
    '"Jemperli" JADE trial',
    '"Jemperli" subcutaneous ALT-B4',
    '"dostarlimab" subcutaneous Hybrozyme',
    '"Jemperli" Alteogen ALT-B4',
    '"젬퍼리" FDA 알테오젠',
]

OFFICIAL_DOMAINS = (
    "gsk.com", "fda.gov", "alteogen.com", "clinicaltrials.gov", "sec.gov"
)
TRIGGER_TERMS = ("jemperli", "dostarlimab", "젬퍼리")
MATERIAL_TERMS = (
    "priority review", "sBLA", "supplemental biologics license", "pdufa",
    "fda", "approval", "approved", "submission", "accepted", "project orbis",
    "national priority voucher", "commissioner's national priority voucher",
    "azur-1", "azur-2", "azur-4", "domenica", "jade",
    "phase 2", "phase ii", "phase 3", "phase iii", "cCR12",
    "complete response", "overall survival", "progression-free",
    "subcutaneous", "alt-b4", "hybrozyme", "berahyaluronidase",
    "sales", "revenue", "매출", "허가", "우선 검토", "피하주사",
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
            and k.lower() not in {"ocid", "ref", "source", "cmpid", "cid"}
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
        r"(?is)<script[^>]+type=[\"\']application/ld\+json[\"\'][^>]*>(.*?)</script>",
        page,
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
    paras = [
        strip_html(x)
        for x in re.findall(r"(?is)<p\b[^>]*>(.*?)</p>", page)
    ]
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
        url = "https://www.bing.com/news/search?" + urllib.parse.urlencode(
            {"q": query, "format": "rss"}
        )
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


def gsk_official_items() -> list[Item]:
    out = [Item("GSK 공식", CURRENT_GSK_PR, CURRENT_GSK_URL, "")]
    try:
        page, _ = fetch("https://www.gsk.com/en-gb/media/", timeout=20)
        for m in re.finditer(
            r'(?is)<a\b[^>]*href=[\"\']([^\"\']+)[\"\'][^>]*>(.*?)</a>',
            page,
        ):
            href = html.unescape(m.group(1)).strip()
            label = strip_html(m.group(2))
            if not href or not label:
                continue
            if not any(t in label.lower() for t in ("jemperli", "dostarlimab")):
                continue
            if href.startswith("/"):
                href = urllib.parse.urljoin("https://www.gsk.com", href)
            if href.startswith(("http://", "https://")):
                out.append(Item("GSK 공식", label, href))
    except Exception:
        pass
    return out


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
    indication = "rectal" if any(x in low for x in ("rectal", "직장암")) else "other"
    if any(x in low for x in ("approved", "approval", "승인")) and "fda" in low:
        stage = "fda_approved"
    elif "pdufa" in low:
        stage = "pdufa"
    elif "priority review" in low or "우선 검토" in low:
        stage = "priority_review"
    elif any(x in low for x in ("sbla", "submission", "filed", "accepted")):
        stage = "regulatory_filing"
    elif any(x in low for x in ("subcutaneous", "alt-b4", "hybrozyme", "berahyaluronidase", "피하주사")):
        stage = "sc_altb4"
    elif any(x in low for x in ("azur-1", "azur-2", "azur-4", "domenica", "jade", "phase 2", "phase 3")):
        stage = "clinical_update"
    elif any(x in low for x in ("sales", "revenue", "매출")):
        stage = "sales"
    else:
        stage = "material"
    # 공식 확인은 2차 보도 뒤에 별도 업그레이드 알림을 허용.
    return digest(f"jemperli|{indication}|{stage}|{klass}")


def rank_item(item: Item) -> tuple[int, int]:
    klass = source_class(item)
    official = 0 if klass == "공식자료" else 1
    direct_gsk = 0 if "gsk.com" in item.canonical else 1
    return official, direct_gsk


def collect() -> tuple[list[Item], list[str]]:
    items: list[Item] = []
    errors: list[str] = []
    items.extend(gsk_official_items())
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
        final = canonicalize_url(final or url)
        body = extract_article_text(page)
        return body, final
    except Exception:
        return "", url


def contains_any(text: str, terms: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(t.lower() in low for t in terms)


def build_item_summary(item: Item) -> str:
    body, resolved = fetch_body(item)
    full = f"{item.full} {body}".strip()
    low = full.lower()
    official = source_class(item) == "공식자료"

    rectal = any(x in low for x in ("rectal cancer", "직장암"))
    priority = "priority review" in low or "우선 검토" in low
    if rectal and priority:
        headline = "GSK Jemperli, dMMR/MSI-H 국소 진행성 직장암 적응증 FDA 우선 검토 수락"
    else:
        headline = "GSK Jemperli 관련 신규 규제·임상 업데이트"

    population = (
        "이전 치료를 받지 않은 2·3기 dMMR/MSI-H 국소 진행성 직장암"
        if rectal and ("stage ii" in low or "stage iii" in low)
        else "Jemperli 개발·허가 대상 환자군"
    )

    regulatory: list[str] = []
    if "supplemental biologics license" in low or "sbla" in low:
        regulatory.append("FDA가 추가 생물학적 제제 허가 신청(sBLA)을 접수")
    if priority:
        regulatory.append("우선 검토 지정")
    pdufa = re.search(r"(?:PDUFA[^.]{0,80}?|action date[^.]{0,50}?)(February\s+2027|Feb(?:ruary)?\.?\s+2027)", full, re.I)
    if pdufa or ("february 2027" in low and "pdufa" in low):
        regulatory.append("PDUFA 결정 예정 시점은 2027년 2월")
    if contains_any(full, ("National Priority Voucher", "Commissioner's National Priority Voucher")):
        regulatory.append("National Priority Voucher 신속 심사 대상이어서 FDA 결정이 2027년 2월보다 앞당겨질 가능성")
    if "project orbis" in low:
        regulatory.append("Project Orbis를 통한 국제 규제기관 공동 심사 대상")
    regulatory_line = " · ".join(regulatory) if regulatory else "규제 단계는 원문 추가 확인 필요"

    trial_parts: list[str] = []
    if "azur-1" in low:
        trial_parts.append("근거 임상은 단일군 등록 2상 AZUR-1")
    enroll = re.search(r"\b(154)\s+(?:patients|participants)", full, re.I)
    if enroll:
        trial_parts.append("등록환자 154명")
    if "500mg" in low or "500 mg" in low:
        trial_parts.append("500mg 정맥주사를 3주마다 투여")
    if "nine cycles" in low:
        trial_parts.append("총 9회 투여")
    if "six months" in low:
        trial_parts.append("약 6개월 치료")
    trial_line = " · ".join(trial_parts) if trial_parts else "임상 세부사항은 원문 추가 확인 필요"

    result_parts: list[str] = []
    if "clinical complete response" in low or "ccr12" in low:
        result_parts.append("12개월 임상적 완전반응(cCR12)을 의미 있게 지속")
    if "no detectable signs of cancer" in low:
        result_parts.append("치료 후 1년 이상 암이 검출되지 않은 환자 비율을 근거로 제출")
    if any(x in low for x in ("eliminate the need for chemotherapy", "eliminating or delaying the need for chemotherapy")):
        result_parts.append("일부 환자에서 항암화학요법·방사선·수술을 없애거나 늦출 가능성")
    result_line = " · ".join(result_parts) if result_parts else "핵심 효능 수치는 후속 공개자료에서 추가 확인"

    safety_line = (
        "기존 고형암에서 알려진 Jemperli 안전성·내약성 프로파일과 대체로 일관"
        if "safety" in low and "consistent" in low
        else "안전성 세부 내용은 원문 추가 확인 필요"
    )

    alteogen_line = (
        "Jemperli(dostarlimab)는 GSK 자회사 Tesaro와 알테오젠이 ALT-B4를 이용한 "
        "피하주사 제형 개발·상업화 독점 라이선스 계약을 체결한 제품입니다. "
        "다만 이번 직장암 FDA 신청은 정맥주사 Jemperli의 적응증 확대이므로 ALT-B4 피하주사 허가 자체는 아닙니다. "
        "적응증이 넓어지면 향후 Jemperli 피하주사 개발·허가가 성공할 경우 적용 가능한 환자·매출 기반이 커지는 간접 재평가 요인입니다."
    )

    next_line = (
        "2027년 2월 PDUFA 또는 National Priority Voucher에 따른 더 이른 FDA 결정, "
        "그리고 Jemperli 피하주사(ALT-B4) 임상 개시·허가 신청·승인을 별도로 추적"
        if rectal and priority
        else "후속 FDA·EMA 허가, 주요 임상 결과, ALT-B4 피하주사 개발 진행을 추적"
    )

    lines = [
        f"**{headline}**",
        "",
        f"- **출처 구분:** {'GSK·규제기관 공식자료' if official else '2차 자료 — 공식자료 교차확인 대상'}",
        f"- **대상:** {population}",
        f"- **규제:** {regulatory_line}",
        f"- **근거 임상:** {trial_line}",
        f"- **결과:** {result_line}",
        f"- **안전성:** {safety_line}",
        f"- **알테오젠 관점:** {alteogen_line}",
        f"- **다음 확인:** {next_line}",
        f"- **원문 확인:** {'기사·공식자료 본문 직접 열람' if body else '원문 본문 자동 추출 불완전 — 제목·검색원문 기준'}",
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
    now_dt = dt.datetime.now(KST)
    now = now_dt.isoformat(timespec="seconds")

    seen = set(state.get("seen_keys") or [])
    seen_events = set(state.get("seen_event_keys") or [])

    # 같은 사건은 공식자료를 우선한다.
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
            # 최초 실행에서는 과거 기사 폭탄을 막고, 현재 GSK 공식 직장암 우선검토 건만 즉시 알림.
            current = (
                "gsk.com" in item.canonical
                and "jemperli-dostarlimab-accepted-for-priority-review" in item.canonical
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
            "[바이오 감시] 알테오젠 파트너제품 Jemperli 새 데이터\n\n"
            + "\n\n".join(summaries)
            + "\n",
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

    status = (
        f"Jemperli ALT-B4 감시 정상 — {now}; 신규={len(new_items)}, "
        f"후보={len(items)}, 사건중복키={len(seen_events)}"
    )
    if errors:
        status += f"; 검색오류={len(errors)}"
        (OUT / "jemperli_altb4_errors.log").write_text("\n".join(errors) + "\n", encoding="utf-8")
    STATUS.write_text(status + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
