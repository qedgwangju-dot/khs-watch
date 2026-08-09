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
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "clarity_watch_state.json"
OUT_DIR = ROOT / "out"
OUT_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; KHS-CLARITY-Watch/1.0; +https://github.com/qedgwangju-dot/khs-watch)",
    "Accept-Language": "en-US,en;q=0.9",
}
OFFICIAL_DOMAINS = {
    "www.congress.gov", "www.senate.gov", "www.banking.senate.gov",
    "www.agriculture.senate.gov", "www.sec.gov", "www.cftc.gov",
    "comments.cftc.gov", "www.whitehouse.gov",
}
TOPIC_RE = re.compile(
    r"\b(?:CLARITY(?:\s+Act)?|H\.?\s*R\.?\s*3633|Digital\s+Asset\s+Market\s+Clarity|digital\s+asset\s+market\s+structure|crypto\s+asset\s+market\s+structure)\b",
    re.I,
)
CRYPTO_RE = re.compile(r"\b(?:crypto|digital asset|blockchain|tokeni[sz]|non-security crypto asset)\b", re.I)
REG_ACTION_RE = re.compile(
    r"\b(?:rule|rulemaking|propos(?:e|ed|al)|adopt(?:s|ed|ion)|final rule|interpretation|guidance|no-action|order|staff letter|framework|registration|market structure|jurisdiction|enforcement)\b",
    re.I,
)
LEG_ACTION_RE = re.compile(
    r"\b(?:markup|mark-up|vote|voted|advance(?:d)?|pass(?:ed|age)?|fail(?:ed|ure)?|reject(?:ed)?|cloture|floor|calendar|schedule|consideration|amendment|amended|new text|bill text|revised text|reported|referred|signed|signature|veto|became law|enacted|session adjourn|sine die)\b",
    re.I,
)

@dataclass(frozen=True)
class Event:
    source: str
    event_type: str
    title: str
    url: str
    date: str = ""
    detail: str = ""

    @property
    def key(self):
        raw = "|".join([self.source, self.event_type, self.title, self.url, self.date, self.detail])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def now_kst():
    return dt.datetime.now(ZoneInfo("Asia/Seoul"))


def now_et():
    return dt.datetime.now(ZoneInfo("America/New_York"))


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


def classify_leg(text):
    t = text.lower()
    if "cloture" in t:
        return "상원 토론종결·절차 표결"
    if any(x in t for x in ["passed", "passage", "agreed to", "rejected", "failed", "yeas", "nays", "vote"]):
        return "표결 결과"
    if any(x in t for x in ["new text", "revised text", "bill text", "amendment", "amended"]):
        return "법안 원문·핵심 조항 수정"
    if any(x in t for x in ["markup", "mark-up", "reported", "advance"]):
        return "위원회 표결·마크업"
    if any(x in t for x in ["calendar", "schedule", "floor", "consideration"]):
        return "상원 본회의 일정"
    if any(x in t for x in ["signed", "signature", "veto", "became law", "enacted"]):
        return "대통령 최종 조치"
    if any(x in t for x in ["adjourn", "sine die"]):
        return "회기 종료·지연"
    return "공식 입법 진행 변화"


def collect_congress(errors):
    events = []
    actions_url = "https://www.congress.gov/bill/119th-congress/house-bill/3633/all-actions"
    text_url = "https://www.congress.gov/bill/119th-congress/house-bill/3633/text"
    try:
        soup = soup_for(actions_url)
        for row in soup.find_all(["tr", "li"]):
            text = clean(row.get_text(" ", strip=True))
            if not text or not LEG_ACTION_RE.search(text):
                continue
            if not (TOPIC_RE.search(text) or re.search(r"\b(?:Senate|House)\b", text, re.I)):
                continue
            events.append(Event("Congress.gov", classify_leg(text), text[:800], actions_url))
        page_text = clean(soup.get_text(" ", strip=True))
        for pattern, label in [
            (r"Latest Action:\s*(.{1,500}?)(?=Roll Call Votes:|Tracker:|More on This Bill)", "최신 공식 조치"),
            (r"Tracker:\s*(.{1,300}?)(?=More on This Bill|Subject)", "법안 상태"),
        ]:
            match = re.search(pattern, page_text, re.I)
            if match:
                detail = clean(match.group(1))
                events.append(Event("Congress.gov", label, detail, actions_url, detail=detail))
    except Exception as exc:
        errors.append(f"Congress.gov actions: {exc}")
    try:
        soup = soup_for(text_url)
        seen = set()
        for a in soup.find_all("a", href=True):
            href = abs_url(text_url, a["href"])
            title = clean(a.get_text(" ", strip=True))
            if "/bill/119th-congress/house-bill/3633/text/" not in href or not title or len(title) > 220:
                continue
            if (title, href) in seen:
                continue
            seen.add((title, href))
            events.append(Event("Congress.gov", "법안 원문 버전", title, href))
    except Exception as exc:
        errors.append(f"Congress.gov text: {exc}")
    return events


def collect_banking(errors):
    url = "https://www.banking.senate.gov/search/?q=Clarity+Act"
    events = []
    try:
        soup = soup_for(url)
        pairs = []
        for a in soup.find_all("a", href=True):
            title = clean(a.get_text(" ", strip=True))
            href = abs_url(url, a["href"])
            if not title or "banking.senate.gov" not in urllib.parse.urlparse(href).netloc:
                continue
            if not TOPIC_RE.search(title) or ("/newsroom/" not in href and "/hearings/" not in href):
                continue
            pairs.append((title, href))
        for title, href in list(dict.fromkeys(pairs))[:20]:
            try:
                body = clean(soup_for(href).get_text(" ", strip=True))
            except Exception:
                body = title
            signal = f"{title} {body[:5000]}"
            if not LEG_ACTION_RE.search(signal):
                continue
            date = ""
            dm = re.search(r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+2026\b", body)
            if dm:
                date = dm.group(0)
            events.append(Event("상원 은행위원회", classify_leg(signal), title, href, date=date))
    except Exception as exc:
        errors.append(f"Senate Banking: {exc}")
    return events


def collect_agriculture(errors):
    events = []
    for url in ["https://www.agriculture.senate.gov/newsroom", "https://www.agriculture.senate.gov/hearings"]:
        try:
            soup = soup_for(url)
            for a in soup.find_all("a", href=True):
                title = clean(a.get_text(" ", strip=True))
                href = abs_url(url, a["href"])
                if not title or "agriculture.senate.gov" not in urllib.parse.urlparse(href).netloc:
                    continue
                if not (TOPIC_RE.search(title) or ("digital asset" in title.lower() and LEG_ACTION_RE.search(title))):
                    continue
                events.append(Event("상원 농업위원회", classify_leg(title), title, href))
        except Exception as exc:
            errors.append(f"Senate Agriculture {url}: {exc}")
    return list({e.key: e for e in events}.values())


def collect_floor(errors):
    sources = [
        ("상원 본회의", "https://www.senate.gov/floor/index.htm"),
        ("상원 의사기록", "https://www.senate.gov/legislative/LIS/floor_activity/all-floor-activity-files.htm"),
        ("상원 표결기록", "https://www.senate.gov/legislative/LIS/roll_call_lists/vote_menu_119_2.htm"),
    ]
    events = []
    for source, url in sources:
        try:
            soup = soup_for(url)
            for node in soup.find_all(["tr", "li", "p", "div"]):
                text = clean(node.get_text(" ", strip=True))
                if not text or len(text) > 1200 or not TOPIC_RE.search(text) or not LEG_ACTION_RE.search(text):
                    continue
                link = url
                a = node.find("a", href=True)
                if a:
                    link = abs_url(url, a["href"])
                events.append(Event(source, classify_leg(text), text[:800], link))
        except Exception as exc:
            errors.append(f"{source}: {exc}")
    return list({e.key: e for e in events}.values())


def parse_rss(url, source, errors):
    events = []
    try:
        root = ET.fromstring(fetch(url))
        items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
        for item in items[:80]:
            def text_of(names):
                for name in names:
                    node = item.find(name)
                    if node is not None and node.text:
                        return clean(node.text)
                return ""
            title = text_of(["title", "{http://www.w3.org/2005/Atom}title"])
            desc = text_of(["description", "summary", "{http://www.w3.org/2005/Atom}summary"])
            pub = text_of(["pubDate", "published", "updated", "{http://www.w3.org/2005/Atom}published", "{http://www.w3.org/2005/Atom}updated"])
            link = text_of(["link"])
            if not link:
                node = item.find("{http://www.w3.org/2005/Atom}link")
                if node is not None:
                    link = node.attrib.get("href", "")
            signal = clean(f"{title} {desc}")
            relevant = bool(TOPIC_RE.search(signal) or (CRYPTO_RE.search(signal) and REG_ACTION_RE.search(signal)))
            if not relevant or not REG_ACTION_RE.search(signal):
                continue
            events.append(Event(source, "SEC·CFTC 공식 규칙·해석·집행지침", title or signal[:180], link or url, date=pub, detail=desc[:600]))
    except Exception as exc:
        errors.append(f"{source}: {exc}")
    return events


def collect_regulators(errors):
    feeds = [
        ("SEC 보도자료", "https://www.sec.gov/news/pressreleases.rss"),
        ("SEC 발언·성명", "https://www.sec.gov/news/speeches-statements.rss"),
        ("CFTC 보도자료", "https://www.cftc.gov/RSS/RSSGP/rssgp.xml"),
        ("CFTC 제안규칙", "https://comments.cftc.gov/handlers/RSSHandler.ashx?category=Proposed+Rule&type=Releases"),
        ("CFTC 최종규칙", "https://comments.cftc.gov/handlers/RSSHandler.ashx?category=Final+Rule&type=Releases"),
    ]
    events = []
    for source, url in feeds:
        events.extend(parse_rss(url, source, errors))
    return list({e.key: e for e in events}.values())


def collect_whitehouse(errors):
    events = []
    for url in ["https://www.whitehouse.gov/presidential-actions/", "https://www.whitehouse.gov/briefings-statements/", "https://www.whitehouse.gov/releases/"]:
        try:
            soup = soup_for(url)
            for a in soup.find_all("a", href=True):
                title = clean(a.get_text(" ", strip=True))
                href = abs_url(url, a["href"])
                if not title or "whitehouse.gov" not in urllib.parse.urlparse(href).netloc or not TOPIC_RE.search(title):
                    continue
                try:
                    body = clean(soup_for(href).get_text(" ", strip=True))
                except Exception:
                    body = title
                signal = f"{title} {body[:4000]}"
                if re.search(r"\b(?:sign(?:ed|s)?|veto|law|enact|statement|presidential action)\b", signal, re.I):
                    events.append(Event("백악관", "대통령 최종 조치", title, href))
        except Exception as exc:
            errors.append(f"White House {url}: {exc}")
    return list({e.key: e for e in events}.values())


def load_state():
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def impact_hint(event):
    text = f"{event.event_type} {event.title} {event.detail}".lower()
    if any(x in text for x in ["passed", "advance", "agreed to", "signed", "became law", "enacted"]):
        return "시간표가 앞당겨지는 변화로 해석. 미국 내 규제 불확실성 축소 방향."
    if any(x in text for x in ["failed", "rejected", "veto", "adjourn", "sine die"]):
        return "시간표가 늦춰지는 변화로 해석. 법률 공백이 길어질 가능성."
    if any(x in text for x in ["new text", "amendment", "amended", "revised text"]):
        return "핵심 조항 재평가 필요. SEC·CFTC 권한 배분, DeFi·중개업자·윤리 조항 변경 여부를 우선 확인."
    if any(x in text for x in ["cloture", "floor", "calendar"]):
        return "상원 본회의 시간표가 구체화된 변화. 실제 최종 표결 가능성이 이전보다 높아졌는지 확인."
    if event.source.startswith(("SEC", "CFTC")):
        return "법 통과 전후와 별개로 규칙 제정을 통해 규제 공백이 줄어드는 경로."
    return "공식 진행 단계 변화. 통과 확률 자체보다 다음 절차와 규제 공백 기간을 재평가."


def build_alert(events):
    kst, et = now_kst(), now_et()
    lines = [
        "🔔 CLARITY 법안 공식 변화", "",
        f"확인 시각: 미국 동부 {et:%Y-%m-%d %H:%M %Z} / 한국 {kst:%Y-%m-%d %H:%M KST}", "",
    ]
    for i, event in enumerate(events[:8], 1):
        lines += [
            f"{i}. 사건 유형: {event.event_type}",
            f"공식 출처: {event.source}",
            f"내용: {event.title}",
        ]
        if event.date:
            lines.append(f"공식 날짜: {event.date}")
        if event.detail:
            lines.append(f"확인 내용: {clean(event.detail)[:500]}")
        lines += [f"해석: {impact_hint(event)}", f"원문: {event.url}", ""]
    lines += [
        "투자 4축",
        "- 돈 버는 능력: Coinbase·Circle 등 미국 규제권 내 사업자의 규제비용·상품 확장 가능성 변화 여부를 확인.",
        "- 할인율: 법안 자체보다 국채금리·유동성이 직접 변수. 이번 알림은 규제 불확실성 변화만 분리.",
        "- 수급: 법적 명확성이 기관·개발자·자본의 미국 잔류·유입 조건을 바꾸는지 후속 공식 자료로 확인.",
        "- 시간표: 이번 공식 변화가 상원 최종 표결 → 하원 재처리 → 대통령 조치의 순서를 얼마나 앞당기거나 늦추는지가 핵심.", "",
        "원인 분리: 가격 변동이 있더라도 이 알림은 공식 입법·규제 변화만 원인으로 확정하며, 시장 가격은 별도 데이터 검증 없이는 인과로 단정하지 않음.",
        "후속 확인: SEC·CFTC의 규칙·해석·집행지침, 상원 본회의 일정·cloture·표결, 백악관 서명·거부권.", "",
        "핵심 한 줄 요약: 새 공식 문서·표결·일정·규칙이 실제 확인된 경우에만 전송하며, 전망·루머·기사 재인용은 알림 대상에서 제외.",
    ]
    return "\n".join(lines).strip() + "\n"


def main():
    errors, events = [], []
    for collector in [collect_congress, collect_banking, collect_agriculture, collect_floor, collect_regulators, collect_whitehouse]:
        events.extend(collector(errors))
    events = sorted({e.key: e for e in events}.values(), key=lambda e: (e.source, e.event_type, e.date, e.title))
    state = load_state()
    baseline = not bool(state.get("initialized"))
    seen = set(state.get("seen_event_keys") or [])
    new_events = [] if baseline else [e for e in events if e.key not in seen]
    merged = list(dict.fromkeys(list(state.get("seen_event_keys") or []) + sorted(e.key for e in events)))
    if len(merged) > 1500:
        merged = merged[-1500:]
    pending = {
        "initialized": True,
        "bill": "H.R. 3633 — Digital Asset Market Clarity Act of 2025",
        "last_checked_kst": now_kst().isoformat(timespec="seconds"),
        "last_checked_et": now_et().isoformat(timespec="seconds"),
        "seen_event_keys": merged,
        "event_count": len(events),
        "source_errors": errors,
    }
    (OUT_DIR / "clarity_watch_pending_state.json").write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    status = [
        "# CLARITY Watch 상태", "", "- 기준 법안: H.R. 3633",
        f"- 확인 시각: {pending['last_checked_kst']}",
        f"- 공식 항목 수: {len(events)}", f"- 신규 공식 변화: {len(new_events)}",
        f"- 최초 기준선 생성: {'예' if baseline else '아니오'}",
        f"- Telegram 전송 대상: {'없음' if not new_events else '있음'}",
    ]
    if errors:
        status.append("- 일부 공식 출처 접근 오류: " + " | ".join(errors[:8]))
    (OUT_DIR / "clarity_watch_status.md").write_text("\n".join(status) + "\n", encoding="utf-8")
    alert_path = OUT_DIR / "clarity_watch_alert.md"
    alert_json = OUT_DIR / "clarity_watch_alert.json"
    for path in [alert_path, alert_json]:
        if path.exists():
            path.unlink()
    if new_events:
        alert_path.write_text(build_alert(new_events), encoding="utf-8")
        alert_json.write_text(json.dumps([asdict(e) | {"key": e.key} for e in new_events], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"clarity_new_official_change=true count={len(new_events)}")
    else:
        print("clarity_new_official_change=false")
    if errors:
        print("source_errors=" + " || ".join(errors[:8]))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
