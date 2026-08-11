#!/usr/bin/env python3
import datetime as dt
import hashlib
import html
import json
import pathlib
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "texas_data_center_watch_state.json"
OUT_DIR = ROOT / "out"
OUT_DIR.mkdir(parents=True, exist_ok=True)
SOURCE_VERSION = 1

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; KHS-Texas-DC-Watch/1.0; +https://github.com/qedgwangju-dot/khs-watch)",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

OFFICIAL_DOMAINS = {
    "gov.texas.gov",
    "www.ercot.com",
    "ercot.com",
    "www.puc.texas.gov",
    "puc.texas.gov",
    "interchange.puc.texas.gov",
}

TOPIC_RE = re.compile(
    r"(?:data[ -]?cent(?:er|re)s?|large (?:electricity )?(?:load|user)s?|"
    r"artificial intelligence infrastructure|AI infrastructure|hyperscale|hyperscaler|"
    r"Stargate|Meta|OpenAI|Oracle|QTS|Digital Realty|Amazon|Google|Microsoft)",
    re.I,
)

GRID_RE = re.compile(
    r"(?:ERCOT|PUCT?|Public Utility Commission|interconnection|grid connection|"
    r"transmission|substation|generation|power plant|electric(?:ity| grid)|ratepayer|"
    r"water use|water reuse|cooling|tax incentive)",
    re.I,
)

ACTION_RE = re.compile(
    r"(?:audit|review|pause|hold|suspend|resume|reopen|restart|approve|approval|"
    r"reject|den(?:y|ial)|withdraw|cancel|comply|commit|standard|require|cost|"
    r"protect|rule|order|directive|filing|batch zero|connect|interconnect|"
    r"energiz|service date|in-service|moratorium|waiver|exemption|incentive|tax)",
    re.I,
)

MATERIAL_RE = re.compile(
    r"(?:audit|pause|hold|suspend|resume|reopen|approve|approval|reject|den(?:y|ial)|"
    r"withdraw|cancel|compliance|comply|commit|standard|require|order|directive|"
    r"interconnection|grid connection|batch zero|energiz|service date|in-service|"
    r"ratepayer|infrastructure cost|transmission cost|generation cost|water|"
    r"tax incentive|moratorium)",
    re.I,
)


@dataclass(frozen=True)
class Event:
    source: str
    title: str
    url: str
    date: str = ""
    detail: str = ""

    @property
    def key(self):
        raw = "|".join([self.source, self.title, self.url, self.date])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def now_kst():
    return dt.datetime.now(ZoneInfo("Asia/Seoul"))


def clean(text):
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def fetch(url, timeout=30):
    host = urllib.parse.urlparse(url).netloc.lower()
    if host not in OFFICIAL_DOMAINS:
        raise RuntimeError(f"non-official domain blocked: {host}")
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()
        except Exception as exc:
            last = exc
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"fetch failed: {url}: {last}")


def soup_for(url):
    return BeautifulSoup(fetch(url), "html.parser")


def abs_url(base, href):
    return urllib.parse.urljoin(base, href)


def page_text(url):
    soup = soup_for(url)
    for node in soup(["script", "style", "noscript", "svg"]):
        node.decompose()
    return clean(soup.get_text(" ", strip=True))


def extract_date(text):
    patterns = [
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+2026\b",
        r"\b\d{2}/\d{2}/2026\b",
        r"\b2026-\d{2}-\d{2}\b",
    ]
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            return m.group(0)
    return ""


def relevant(title, body):
    signal = f"{title} {body[:18000]}"
    if TOPIC_RE.search(signal) and (GRID_RE.search(signal) or ACTION_RE.search(signal)):
        return True
    # Data-center language itself plus a material regulatory/project action is sufficient.
    if re.search(r"data[ -]?cent(?:er|re)s?", signal, re.I) and MATERIAL_RE.search(signal):
        return True
    return False


def summarize_detail(body):
    body = clean(body)
    snippets = []
    for pattern in [
        r".{0,180}(?:audit|pause|hold|resume|reopen|approve|reject|withdraw|comply|interconnection).{0,260}",
        r".{0,180}(?:ratepayer|infrastructure cost|transmission|generation|water|tax incentive).{0,260}",
    ]:
        m = re.search(pattern, body, re.I)
        if m:
            s = clean(m.group(0))
            if s and s not in snippets:
                snippets.append(s)
    return " / ".join(snippets)[:900]


def collect_governor(errors):
    base = "https://gov.texas.gov/news"
    events = []
    try:
        soup = soup_for(base)
        links = []
        for a in soup.find_all("a", href=True):
            href = abs_url(base, a["href"])
            if "/news/post/" not in href:
                continue
            title = clean(a.get_text(" ", strip=True))
            if not title:
                continue
            links.append((title, href.split("?")[0]))
        # Newest page is enough for hourly monitoring; cap network work.
        for title, href in list(dict.fromkeys(links))[:45]:
            try:
                body = page_text(href)
            except Exception as exc:
                errors.append(f"Texas Governor article {href}: {exc}")
                continue
            if relevant(title, body):
                events.append(Event(
                    source="Texas Governor",
                    title=title,
                    url=href,
                    date=extract_date(body),
                    detail=summarize_detail(body),
                ))
    except Exception as exc:
        errors.append(f"Texas Governor news: {exc}")
    return events


def collect_ercot(errors):
    base = "https://www.ercot.com/news/releases"
    events = []
    try:
        soup = soup_for(base)
        links = []
        for a in soup.find_all("a", href=True):
            href = abs_url(base, a["href"])
            if "/news/release/" not in href:
                continue
            title = clean(a.get_text(" ", strip=True))
            if not title:
                continue
            links.append((title, href.split("?")[0]))
        for title, href in list(dict.fromkeys(links))[:35]:
            try:
                body = page_text(href)
            except Exception as exc:
                errors.append(f"ERCOT release {href}: {exc}")
                continue
            if relevant(title, body):
                events.append(Event(
                    source="ERCOT",
                    title=title,
                    url=href,
                    date=extract_date(body),
                    detail=summarize_detail(body),
                ))
    except Exception as exc:
        errors.append(f"ERCOT releases: {exc}")
    return events


def collect_puct_search(errors):
    # PUCT's public site search is useful because press-release URLs have changed over time.
    events = []
    queries = ["data center", "large load", "interconnection", "ratepayer data center"]
    for q in queries:
        url = "https://www.puc.texas.gov/agency/sitesearch.aspx?q=" + urllib.parse.quote_plus(q)
        try:
            soup = soup_for(url)
            candidates = []
            for a in soup.find_all("a", href=True):
                href = abs_url(url, a["href"])
                host = urllib.parse.urlparse(href).netloc.lower()
                title = clean(a.get_text(" ", strip=True))
                if not title or host not in OFFICIAL_DOMAINS:
                    continue
                if href.rstrip("/") == url.rstrip("/"):
                    continue
                candidates.append((title, href.split("#")[0]))
            for title, href in list(dict.fromkeys(candidates))[:20]:
                signal = title
                body = ""
                try:
                    body = page_text(href)
                    signal += " " + body[:18000]
                except Exception:
                    pass
                if relevant(title, signal):
                    events.append(Event(
                        source="PUCT",
                        title=title,
                        url=href,
                        date=extract_date(body or signal),
                        detail=summarize_detail(body or signal),
                    ))
        except Exception as exc:
            errors.append(f"PUCT search {q}: {exc}")
    return events


def load_state():
    if not STATE_PATH.exists():
        return None
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def format_alert(new_events, checked_at):
    lines = [
        "🚨 텍사스 데이터센터 규제·계통연결 변화",
        "",
        f"확인시각: {checked_at.strftime('%Y-%m-%d %H:%M:%S KST')}",
        "",
    ]
    for idx, e in enumerate(new_events[:10], 1):
        lines.extend([
            f"[{idx}] {e.source}",
            f"제목: {e.title}",
            f"날짜: {e.date or '공식 페이지에서 날짜 자동추출 안 됨'}",
        ])
        if e.detail:
            lines.append(f"핵심: {e.detail}")
        lines.append(f"원문: {e.url}")
        lines.append("")
    lines.extend([
        "감시 기준: 감사 완료·승인 보류/해제·계통연결 재개·승인/거부/철회·기업 준수 약속·전력망/발전/용수/비용부담 기준의 공식 변화",
        "※ 단순 페이지 수정이 아니라 새 공식 문서·발표가 생긴 경우만 전송합니다.",
    ])
    return "\n".join(lines).strip() + "\n"


def main():
    checked_at = now_kst()
    errors = []
    events = []
    events.extend(collect_governor(errors))
    events.extend(collect_ercot(errors))
    events.extend(collect_puct_search(errors))

    dedup = {}
    for e in events:
        dedup[e.key] = e
    events = sorted(dedup.values(), key=lambda e: (e.date, e.source, e.title), reverse=True)

    state = load_state()
    current_keys = [e.key for e in events]
    rebaseline = state is None or state.get("source_version") != SOURCE_VERSION
    seen = set((state or {}).get("seen_keys", []))
    new_events = [] if rebaseline else [e for e in events if e.key not in seen]

    # Keep a generous rolling set so an older official article that reappears does not re-alert.
    merged_seen = list(dict.fromkeys(current_keys + list(seen)))[:2000]
    pending = {
        "source_version": SOURCE_VERSION,
        "last_checked_kst": checked_at.isoformat(timespec="seconds"),
        "seen_keys": merged_seen,
        "event_count": len(events),
        "sources_ok": {
            "texas_governor": not any(x.startswith("Texas Governor news:") for x in errors),
            "ercot": not any(x.startswith("ERCOT releases:") for x in errors),
            "puct_search": not all(x.startswith("PUCT search") for x in errors) if errors else True,
        },
        "last_errors": errors[-20:],
    }
    (OUT_DIR / "texas_data_center_watch_pending_state.json").write_text(
        json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    if rebaseline:
        (OUT_DIR / "texas_data_center_watch_rebaseline.txt").write_text("baseline\n", encoding="utf-8")
    elif new_events:
        (OUT_DIR / "texas_data_center_watch_alert.md").write_text(
            format_alert(new_events, checked_at), encoding="utf-8"
        )
        (OUT_DIR / "texas_data_center_watch_alert.json").write_text(
            json.dumps([e.__dict__ for e in new_events], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    status = [
        "# 텍사스 데이터센터 감시 상태",
        "",
        f"- 확인시각: {checked_at.isoformat(timespec='seconds')}",
        f"- 관련 공식 항목 수: {len(events)}",
        f"- 신규 알림 항목 수: {len(new_events)}",
        f"- 초기 기준값 생성: {'예' if rebaseline else '아니오'}",
        f"- 오류 수: {len(errors)}",
    ]
    if errors:
        status.append("")
        status.append("## 접근 오류")
        status.extend(f"- {x}" for x in errors[-10:])
    (OUT_DIR / "texas_data_center_watch_status.md").write_text("\n".join(status) + "\n", encoding="utf-8")

    print(f"events={len(events)} new={len(new_events)} rebaseline={rebaseline} errors={len(errors)}")


if __name__ == "__main__":
    main()
