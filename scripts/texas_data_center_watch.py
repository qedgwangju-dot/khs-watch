#!/usr/bin/env python3
import datetime as dt
import hashlib
import html
import json
import pathlib
import re
import ssl
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from zoneinfo import ZoneInfo

import certifi
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator

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
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

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
    r"Stargate|Meta|OpenAI|Oracle|QTS|Digital Realty|Amazon|Google|Microsoft|"
    r"EdgeConneX|Stream Data Centers)",
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

SOURCE_KO = {
    "Texas Governor": "텍사스 주지사실",
    "ERCOT": "ERCOT",
    "PUCT": "PUCT",
}

MONTHS = {
    "January": 1,
    "February": 2,
    "March": 3,
    "April": 4,
    "May": 5,
    "June": 6,
    "July": 7,
    "August": 8,
    "September": 9,
    "October": 10,
    "November": 11,
    "December": 12,
}


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
            with urllib.request.urlopen(req, timeout=timeout, context=SSL_CONTEXT) as response:
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
    for node in soup(["script", "style", "noscript", "svg", "nav", "header", "footer", "form"]):
        node.decompose()

    # Prefer the page's main/article body so navigation text never leaks into Telegram summaries.
    container = soup.find("article") or soup.find("main") or soup.find(attrs={"role": "main"}) or soup
    return clean(container.get_text(" ", strip=True))


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


def date_to_korean(value):
    value = clean(value)
    if not value:
        return "공식 페이지에서 날짜 자동추출 안 됨"

    m = re.fullmatch(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(\d{4})",
        value,
        re.I,
    )
    if m:
        month_name = m.group(1).title()
        return f"{int(m.group(3))}년 {MONTHS[month_name]}월 {int(m.group(2))}일"

    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", value)
    if m:
        return f"{int(m.group(3))}년 {int(m.group(1))}월 {int(m.group(2))}일"

    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", value)
    if m:
        return f"{int(m.group(1))}년 {int(m.group(2))}월 {int(m.group(3))}일"

    return value


def relevant(title, body):
    signal = f"{title} {body[:18000]}"
    if TOPIC_RE.search(signal) and (GRID_RE.search(signal) or ACTION_RE.search(signal)):
        return True
    if re.search(r"data[ -]?cent(?:er|re)s?", signal, re.I) and MATERIAL_RE.search(signal):
        return True
    return False


def summarize_detail(body):
    body = clean(body)
    snippets = []
    for pattern in [
        r".{0,220}(?:audit|pause|hold|resume|reopen|approve|reject|withdraw|comply|interconnection).{0,360}",
        r".{0,220}(?:ratepayer|infrastructure cost|transmission|generation|water|tax incentive).{0,360}",
    ]:
        m = re.search(pattern, body, re.I)
        if m:
            s = clean(m.group(0))
            if s and s not in snippets:
                snippets.append(s)
    return " / ".join(snippets)[:1200]


def translate_to_korean(text):
    text = clean(text)
    if not text:
        return ""
    # If it is already effectively Korean, keep it as-is.
    if re.search(r"[가-힣]", text) and not re.search(r"[A-Za-z]{4,}", text):
        return text

    last = None
    for attempt in range(3):
        try:
            translated = GoogleTranslator(source="auto", target="ko").translate(text)
            translated = clean(translated)
            if translated and re.search(r"[가-힣]", translated):
                return translated
            last = RuntimeError("translation returned no Korean text")
        except Exception as exc:
            last = exc
        time.sleep(2 ** attempt)
    # Fail closed: never send the original English alert when translation failed.
    raise RuntimeError(f"한국어 번역 실패: {last}")


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
        source_ko = html.escape(SOURCE_KO.get(e.source, e.source))
        title_ko = html.escape(translate_to_korean(e.title))
        date_ko = html.escape(date_to_korean(e.date))
        detail_ko = html.escape(translate_to_korean(e.detail)) if e.detail else ""
        url_html = html.escape(e.url, quote=True)
        lines.extend([
            f"[{idx}] {source_ko}",
            f"제목: {title_ko}",
            f"날짜: {date_ko}",
        ])
        if detail_ko:
            lines.append(f"핵심: {detail_ko}")
        lines.append(f'<a href="{url_html}">원문</a>')
        lines.append("")
    lines.extend([
        "감시 기준: 감사 완료·승인 보류/해제·계통연결 재개·승인/거부/철회·기업 준수 약속·전력망/발전/용수/비용부담 기준의 공식 변화",
        "※ 제목과 핵심 내용은 한국어로 번역하며, 기업명·기관명·고유명사는 식별을 위해 원문 표기를 유지할 수 있습니다.",
        "※ 번역이 실패하면 영어 원문을 대신 보내지 않고 다음 실행에서 다시 시도합니다.",
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
        # Translation happens before the state is persisted. If translation fails, the run fails
        # and the event remains unseen so it can be retried instead of sending English text.
        alert_text = format_alert(new_events, checked_at)
        (OUT_DIR / "texas_data_center_watch_alert.md").write_text(alert_text, encoding="utf-8")
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
        "- Telegram 출력 언어: 한국어",
    ]
    if errors:
        status.append("")
        status.append("## 접근 오류")
        status.extend(f"- {x}" for x in errors[-10:])
    (OUT_DIR / "texas_data_center_watch_status.md").write_text("\n".join(status) + "\n", encoding="utf-8")

    print(f"events={len(events)} new={len(new_events)} rebaseline={rebaseline} errors={len(errors)} language=ko")


if __name__ == "__main__":
    main()
