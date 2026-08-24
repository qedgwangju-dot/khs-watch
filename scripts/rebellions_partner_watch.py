#!/usr/bin/env python3
import datetime as dt
import email.utils
import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "rebellions_partner_watch_state.json"
OUT = ROOT / "out"
OUT.mkdir(parents=True, exist_ok=True)
ALERT = OUT / "rebellions_partner_watch_alert.md"
PENDING = OUT / "rebellions_partner_watch_pending_state.json"
STATUS = OUT / "rebellions_partner_watch_status.md"

UA = "Mozilla/5.0 (compatible; RebellionsPartnerWatch/1.0; +https://github.com/qedgwangju-dot/khs-watch)"

ACTION_TERMS = [
    "협력", "업무협약", "mou", "파트너", "공동개발", "공동 개발", "공동사업", "공동 사업",
    "공급", "수주", "계약", "도입", "채택", "상용", "출시", "양산", "생산",
    "실증", "poc", "검증", "고객", "제휴", "납품", "선정", "탑재", "장착",
    "투자", "지분", "인수", "합병", "유통", "총판", "var"
]
SUBJECT_TERMS = ["리벨리온", "rebellions", "rebel", "atom-max", "atom max", "atom"]

GOOGLE_QUERIES = [
    '리벨리온 (협력 OR 업무협약 OR MOU OR 파트너 OR 공동개발)',
    '리벨리온 (공급 OR 수주 OR 계약 OR 도입 OR 채택 OR 상용화 OR 양산)',
    '리벨리온 (NPU OR Rebel OR ATOM) (고객 OR 서버 OR 클라우드 OR 데이터센터)',
    'Rebellions (partnership OR MOU OR supply OR contract OR deployment OR production)'
]


def now_kst():
    return dt.datetime.now(ZoneInfo("Asia/Seoul"))


def fetch_text(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
        charset = r.headers.get_content_charset() or "utf-8"
    return data.decode(charset, errors="replace")


def norm_text(value):
    value = html.unescape(re.sub(r"<[^>]+>", " ", value or ""))
    value = re.sub(r"\s+", " ", value).strip()
    return value


def norm_title(value):
    v = norm_text(value).lower()
    v = re.sub(r"\s*[-|]\s*(리벨리온|rebellions).*$", "", v)
    v = re.sub(r"[^0-9a-z가-힣]+", " ", v)
    return re.sub(r"\s+", " ", v).strip()


def key_for(title):
    return hashlib.sha256(norm_title(title).encode("utf-8")).hexdigest()[:24]


def relevant(title, summary=""):
    text = (norm_text(title) + " " + norm_text(summary)).lower()
    return any(x in text for x in SUBJECT_TERMS) and any(x in text for x in ACTION_TERMS)


def classify(title, summary=""):
    text = (norm_text(title) + " " + norm_text(summary)).lower()
    if any(x in text for x in ["수주", "공급계약", "공급 계약", "계약 체결", "contract", "order"]):
        return "수주·공급·계약"
    if any(x in text for x in ["도입", "채택", "상용", "출시", "deployment", "adoption"]):
        return "도입·상용화"
    if any(x in text for x in ["양산", "생산", "mass production"]):
        return "양산·생산"
    if any(x in text for x in ["mou", "업무협약", "협력", "파트너", "공동개발", "공동 개발"]):
        return "협력·MOU·공동개발"
    if any(x in text for x in ["투자", "지분", "인수", "합병"]):
        return "투자·지분·인수"
    return "기타 핵심 변화"


def parse_pubdate(value):
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(ZoneInfo("Asia/Seoul"))
    except Exception:
        return None


def collect_official():
    items = []
    seen_urls = set()
    for page in range(1, 4):
        url = "https://kr.rebellions.ai/company/newsroom/" + (f"page/{page}/" if page > 1 else "")
        try:
            body = fetch_text(url)
        except Exception:
            continue
        soup = BeautifulSoup(body, "html.parser")
        for a in soup.find_all("a", href=True):
            href = urllib.parse.urljoin(url, a["href"])
            if "/newsroom/" not in href or href in seen_urls:
                continue
            title = norm_text(a.get_text(" ", strip=True))
            if len(title) < 8:
                continue
            seen_urls.add(href)
            if not relevant(title):
                continue
            items.append({
                "title": title,
                "url": href.split("#")[0],
                "source": "리벨리온 공식 뉴스룸",
                "published_kst": None,
                "summary": "",
                "official": True,
            })
    return items


def collect_google_news():
    items = []
    for query in GOOGLE_QUERIES:
        url = (
            "https://news.google.com/rss/search?q="
            + urllib.parse.quote(query)
            + "&hl=ko&gl=KR&ceid=KR:ko"
        )
        try:
            xml = fetch_text(url)
            root = ET.fromstring(xml)
        except Exception:
            continue
        for node in root.findall(".//item"):
            title = norm_text(node.findtext("title") or "")
            link = norm_text(node.findtext("link") or "")
            summary = norm_text(node.findtext("description") or "")
            source_node = node.find("source")
            source = norm_text(source_node.text if source_node is not None else "Google News")
            pub = parse_pubdate(node.findtext("pubDate"))
            if not relevant(title, summary):
                continue
            items.append({
                "title": title,
                "url": link,
                "source": source or "Google News",
                "published_kst": pub.isoformat(timespec="minutes") if pub else None,
                "summary": summary,
                "official": False,
            })
    return items


def load_state():
    if not STATE.exists():
        return {"seen": {}, "initialized": False}
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"seen": {}, "initialized": False}


def main():
    for p in (ALERT, PENDING, STATUS):
        if p.exists():
            p.unlink()

    now = now_kst()
    state = load_state()
    seen = dict(state.get("seen") or {})

    candidates = collect_official() + collect_google_news()

    deduped = {}
    for item in candidates:
        k = key_for(item["title"])
        old = deduped.get(k)
        if old is None or (item["official"] and not old["official"]):
            deduped[k] = item

    ordered = list(deduped.items())
    ordered.sort(key=lambda kv: (not kv[1]["official"], kv[1].get("published_kst") or ""), reverse=False)

    if not state.get("initialized"):
        for k, item in ordered:
            seen[k] = {
                "title": item["title"],
                "url": item["url"],
                "first_seen_kst": now.isoformat(timespec="seconds"),
            }
        pending = {
            "initialized": True,
            "bootstrap_kst": now.isoformat(timespec="seconds"),
            "last_checked_kst": now.isoformat(timespec="seconds"),
            "seen": seen,
        }
        PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        STATUS.write_text(
            f"# 리벨리온 협력 웹감시\n\n- 상태: 초기 기준선 생성\n- 기준선 항목: {len(seen)}개\n- 신규 알림: 0개\n- 조회시각: {now:%Y-%m-%d %H:%M} KST\n",
            encoding="utf-8",
        )
        return

    last_checked_raw = state.get("last_checked_kst")
    try:
        last_checked = dt.datetime.fromisoformat(last_checked_raw)
        if last_checked.tzinfo is None:
            last_checked = last_checked.replace(tzinfo=ZoneInfo("Asia/Seoul"))
    except Exception:
        last_checked = now - dt.timedelta(hours=48)

    fresh = []
    for k, item in ordered:
        if k in seen:
            continue
        pub = None
        if item.get("published_kst"):
            try:
                pub = dt.datetime.fromisoformat(item["published_kst"])
            except Exception:
                pass
        # Prevent stale RSS reshuffles from causing old-news spam. Official newsroom is always allowed.
        if not item["official"] and pub and pub < last_checked - dt.timedelta(hours=36):
            seen[k] = {
                "title": item["title"],
                "url": item["url"],
                "first_seen_kst": now.isoformat(timespec="seconds"),
                "suppressed_stale": True,
            }
            continue
        fresh.append((k, item))

    if fresh:
        lines = [
            "리벨리온 협력·수주·도입 웹감시",
            "",
            f"조회시각: {now:%Y-%m-%d %H:%M} KST",
            f"신규 핵심 변화: {len(fresh)}건",
            "",
        ]
        for idx, (k, item) in enumerate(fresh[:8], start=1):
            lines.extend([
                f"{idx}. [{classify(item['title'], item.get('summary',''))}] {item['title']}",
                f"- 출처: {item['source']}" + (" · 공식" if item["official"] else ""),
                f"- 공개시각: {item.get('published_kst') or '페이지 직접 확인'}",
                f"- 링크: {item['url']}",
                "",
            ])
            seen[k] = {
                "title": item["title"],
                "url": item["url"],
                "first_seen_kst": now.isoformat(timespec="seconds"),
                "alerted": True,
            }
        if len(fresh) > 8:
            lines.append(f"※ 한 번에 8건만 송출. 추가 {len(fresh)-8}건은 다음 실행에서 이어서 확인합니다.")
        ALERT.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

    # Retain a bounded history.
    if len(seen) > 800:
        seen = dict(list(seen.items())[-800:])

    pending = {
        **{k: v for k, v in state.items() if k != "seen"},
        "initialized": True,
        "last_checked_kst": now.isoformat(timespec="seconds"),
        "seen": seen,
    }
    PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    STATUS.write_text(
        f"# 리벨리온 협력 웹감시\n\n- 상태: 정상 조회\n- 후보 항목: {len(ordered)}개\n- 신규 알림: {len(fresh)}개\n- 누적 중복키: {len(seen)}개\n- 조회시각: {now:%Y-%m-%d %H:%M} KST\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
