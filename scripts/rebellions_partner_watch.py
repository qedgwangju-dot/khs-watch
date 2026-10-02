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

SPECULATION_TERMS = [
    "특징주", "관련주", "부각", "기대감", "가능성", "검토", "논의", "거론",
    "상한가", "급등", "주가", "인수 가능", "ipo 부각"
]

FOREIGN_PARTNER_MARKERS = [
    "arm", "marvell", "기가컴퓨팅", "giga computing", "gigabyte", "페가트론", "pegatron",
    "토멘디바이스", "tomen devices", "aramco", "아람코", "wa'ed", "말레이시아 주정부"
]

KNOWN_KOREAN_PARTNERS = [
    "삼성전자", "sk텔레콤", "skt", "kt cloud", "kt클라우드", "네이버클라우드", "nhn클라우드",
    "세미파이브", "에이디테크놀로지", "코아시아세미", "큐알티", "코난테크놀로지",
    "코오롱베니트", "이글루코퍼레이션", "슈퍼브에이아이", "솔트룩스", "스탠다드에너지",
    "엘리스그룹", "이노뎁", "루닛", "워트인텔리전스", "cck솔루션", "에코피스",
    "베슬ai", "엑셈", "시즐", "라이너", "kb금융", "가비아", "제이디원",
    "아이에이", "아이에이클라우드", "몬드리안에이아이", "스퀴즈비츠", "비투엔", "모레",
    "한국정보통신기술협회", "tta", "한국컴퓨팅산업협회",
    "한국전력", "한국전력공사", "한전", "kepco"
]

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


def tg_html(value):
    return html.escape(str(value or ""), quote=True)


def norm_title(value):
    v = norm_text(value).lower()
    # RSS providers may change only the publisher suffix (e.g. "- 디일렉" -> "- thelec.kr").
    # Strip that suffix before hashing so the exact same story cannot alert twice.
    v = re.sub(r"\s+-\s+[^-]{2,60}$", "", v)
    v = re.sub(r"\s*[-|]\s*(리벨리온|rebellions).*$", "", v)
    v = re.sub(r"[^0-9a-z가-힣]+", " ", v)
    return re.sub(r"\s+", " ", v).strip()


def key_for(title):
    return hashlib.sha256(norm_title(title).encode("utf-8")).hexdigest()[:24]


def canonical_url(value):
    value = norm_text(value)
    if not value:
        return ""
    try:
        p = urllib.parse.urlsplit(value)
        # Google News repeatedly exposes the same article with cosmetic query changes.
        query = "" if p.netloc.lower() == "news.google.com" else p.query
        return urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), query, ""))
    except Exception:
        return value


def event_signature(title, summary=""):
    """Underlying business-event key. Action wording is intentionally excluded to cluster same-event coverage."""
    text = (norm_text(title) + " " + norm_text(summary)).lower()

    # Primary counterparty. Put end-customers / adopters before validators and ecosystem bodies.
    partner_aliases = [
        ("kepco", ["한국전력공사", "한국전력", "한전", "kepco"]),
        ("skt", ["sk텔레콤", "skt"]),
        ("ktcloud", ["kt cloud", "kt클라우드"]),
        ("navercloud", ["네이버클라우드"]),
        ("nhncloud", ["nhn클라우드"]),
        ("samsung", ["삼성전자"]),
        ("kb", ["kb금융"]),
        ("gabia", ["가비아"]),
        ("konan", ["코난테크놀로지"]),
        ("kolonbenit", ["코오롱베니트"]),
        ("igloo", ["이글루코퍼레이션"]),
        ("superbai", ["슈퍼브에이아이"]),
        ("saltlux", ["솔트룩스"]),
        ("standardenergy", ["스탠다드에너지"]),
        ("elice", ["엘리스그룹"]),
        ("innodep", ["이노뎁"]),
        ("lunit", ["루닛"]),
        ("wert", ["워트인텔리전스"]),
        ("cck", ["cck솔루션"]),
        ("ecopeace", ["에코피스"]),
        ("vesslai", ["베슬ai", "vessl ai"]),
        ("exem", ["엑셈"]),
        ("sizl", ["시즐"]),
        ("liner", ["라이너"]),
        ("jdone", ["제이디원"]),
        ("ia", ["아이에이클라우드", "아이에이그룹", "아이에이"]),
        ("mondrian", ["몬드리안에이아이"]),
        ("squeezebits", ["스퀴즈비츠"]),
        ("b2en", ["비투엔"]),
        ("moreh", ["모레"]),
        ("semifive", ["세미파이브"]),
        ("adtechnology", ["에이디테크놀로지"]),
        ("coasisemi", ["코아시아세미"]),
        ("qrt", ["큐알티"]),
        ("tta", ["한국정보통신기술협회", "tta"]),
    ]
    partner = next((name for name, aliases in partner_aliases if any(a in text for a in aliases)), None)
    if not partner:
        return None

    if any(x in text for x in ["리벨100", "rebel100", "rebel 100"]):
        product = "rebel100"
    elif any(x in text for x in ["아톰맥스", "atom-max", "atom max"]):
        product = "atommax"
    elif any(x in text for x in ["리벨랙", "rebelrack"]):
        product = "rebelrack"
    elif any(x in text for x in ["리벨서버", "rebelserver", "ai 서버", "ai server"]):
        product = "server"
    elif any(x in text for x in ["아톰", " atom ", "npu", "ai반도체", "ai 반도체"]):
        product = "npu"
    elif any(x in text for x in ["칩렛", "chiplet"]):
        product = "chiplet"
    else:
        product = "general"

    # Application/project context prevents unrelated deals with the same counterparty from colliding.
    if any(x in text for x in ["변전소", "전력 현장", "전력분야", "전력 분야", "영상분석", "영상 분석", "영상 관제", "ai 관제"]):
        context = "power_video"
    elif any(x in text for x in ["cctv", "관제센터", "관제 센터"]):
        context = "cctv"
    elif any(x in text for x in ["금융", "은행"]):
        context = "finance"
    elif any(x in text for x in ["의료", "병원", "헬스케어"]):
        context = "healthcare"
    elif any(x in text for x in ["클라우드", "cloud", "npuass", "npu as a service"]):
        context = "cloud"
    elif any(x in text for x in ["특허", "patent"]):
        context = "patent"
    elif any(x in text for x in ["데이터센터", "data center", "aidc"]):
        context = "datacenter"
    elif any(x in text for x in ["로봇", "robot"]):
        context = "robot"
    elif any(x in text for x in ["보안", "security"]):
        context = "security"
    else:
        context = "general"

    return f"{partner}|{product}|{context}"


def material_stage(title, summary=""):
    """Material stage used only to avoid suppressing a true commercial step-up."""
    text = (norm_text(title) + " " + norm_text(summary)).lower()
    if any(x in text for x in [
        "수주", "공급계약", "공급 계약", "구매계약", "구매 계약", "발주",
        "납품 완료", "납품한다", "정식 공급", "계약금액", "계약 금액"
    ]):
        return 5
    if any(x in text for x in [
        "상용화", "상용 서비스", "정식 도입", "전면 도입", "양산 시작", "양산 개시",
        "실제 도입", "운영 개시"
    ]):
        return 4
    if any(x in text for x in ["실증 완료", "검증 완료", "poc 완료", "시범운영 완료"]):
        return 3
    if any(x in text for x in ["실증", "검증", "poc", "시범운영", "시범 운영", "현장 적용", "현장 투입"]):
        return 2
    if any(x in text for x in ["mou", "업무협약", "파트너십", "공동개발", "공동 개발", "협력", "제휴"]):
        return 1
    return 0


def source_rank(source, official=False):
    if official:
        return 100
    text = norm_text(source).lower()
    high = [
        "연합뉴스", "뉴시스", "전자신문", "지디넷", "zdnet", "이데일리", "조선비즈",
        "한국경제", "매일경제", "머니투데이", "서울경제", "뉴스핌", "아시아경제",
        "파이낸셜뉴스", "디지털데일리", "아이뉴스24", "블로터", "thelec", "디일렉"
    ]
    return 80 if any(x in text for x in high) else 50


def seen_time(entry):
    raw = str((entry or {}).get("first_seen_kst") or "")
    try:
        value = dt.datetime.fromisoformat(raw)
        if value.tzinfo is None:
            value = value.replace(tzinfo=ZoneInfo("Asia/Seoul"))
        return value
    except Exception:
        return None


def find_duplicate_event(item, seen, now, semantic_hours=72):
    """Return duplicate reason when this is another article about the same already-seen event."""
    item_url = canonical_url(item.get("url"))
    item_title = norm_title(item.get("title"))
    item_sig = event_signature(item.get("title"), item.get("summary", ""))
    item_stage = material_stage(item.get("title"), item.get("summary", ""))

    for prior in seen.values():
        prior_url = canonical_url(prior.get("url"))
        if item_url and prior_url and item_url == prior_url:
            return "same_url"
        if item_title and item_title == norm_title(prior.get("title")):
            return "same_title"

    if not item_sig:
        return None

    cutoff = now - dt.timedelta(hours=semantic_hours)
    for prior in seen.values():
        if not (prior.get("alerted") or prior.get("pending_alert")):
            continue
        when = seen_time(prior)
        if not when or when < cutoff:
            continue
        prior_sig = prior.get("event_signature") or event_signature(prior.get("title"), prior.get("summary", ""))
        if prior_sig != item_sig:
            continue

        # A genuinely stronger commercial event is allowed through.
        prior_stage = int(prior.get("material_stage") or material_stage(prior.get("title"), prior.get("summary", "")))
        if item_stage >= 4 and item_stage > prior_stage:
            return None
        return f"same_event:{item_sig}"

    return None


def resolve_original_url(value):
    """Best effort: follow a Google News link to the publisher; safe fallback is the Google News URL."""
    value = norm_text(value)
    if "news.google.com/" not in value:
        return value
    try:
        req = urllib.request.Request(value, headers={"User-Agent": UA, "Accept-Language": "ko,en;q=0.8"})
        with urllib.request.urlopen(req, timeout=12) as r:
            final = r.geturl()
        if final and "news.google.com/" not in final:
            return final
    except Exception:
        pass
    return value


def relevant(title, summary=""):
    text = (norm_text(title) + " " + norm_text(summary)).lower()
    return any(x in text for x in SUBJECT_TERMS) and any(x in text for x in ACTION_TERMS)


def domestic_candidate(title, summary=""):
    text = (norm_text(title) + " " + norm_text(summary)).lower()
    if any(x in text for x in SPECULATION_TERMS):
        return False
    if any(x in text for x in KNOWN_KOREAN_PARTNERS):
        return True
    if any(x in text for x in FOREIGN_PARTNER_MARKERS):
        return False
    # Keep new, previously unknown Korean partners discoverable when the article explicitly
    # frames the deal around Korean/domestic AI infrastructure.
    return any(x in text for x in ["국내", "국산", "한국형", "k-ai", "k-npu", "k ai", "k npu"])


def classify(title, summary=""):
    text = (norm_text(title) + " " + norm_text(summary)).lower()
    has_mou = any(x in text for x in ["mou", "업무협약", "협력", "파트너", "공동개발", "공동 개발", "제휴"])
    has_validation = any(x in text for x in ["실증", "검증", "poc", "시범운영", "시범 운영", "현장 투입"])
    if any(x in text for x in ["수주", "공급계약", "공급 계약", "구매계약", "구매 계약", "납품", "발주", "contract", "order"]):
        return "수주·공급·계약"
    if any(x in text for x in ["도입", "채택", "상용", "출시", "deployment", "adoption"]):
        return "도입·상용화"
    if any(x in text for x in ["양산", "생산", "mass production"]):
        return "양산·생산"
    if has_mou and has_validation:
        return "협력·MOU·실증"
    if has_validation:
        return "실증·검증"
    if has_mou:
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
    for page in range(1, 11):
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
            if not domestic_candidate(title):
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
            if not domestic_candidate(title, summary):
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
    ordered.sort(
        key=lambda kv: (
            1 if kv[1]["official"] else 0,
            source_rank(kv[1].get("source", ""), kv[1]["official"]),
            kv[1].get("published_kst") or "",
        ),
        reverse=True,
    )

    if not state.get("initialized"):
        for k, item in ordered:
            seen[k] = {
                "title": item["title"],
                "url": item["url"],
                "summary": item.get("summary", ""),
                "event_signature": event_signature(item["title"], item.get("summary", "")),
                "material_stage": material_stage(item["title"], item.get("summary", "")),
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
    duplicate_suppressed = 0
    dedupe_seen = dict(seen)
    for k, item in ordered:
        if k in seen:
            continue

        duplicate_reason = find_duplicate_event(item, dedupe_seen, now)
        if duplicate_reason:
            duplicate_suppressed += 1
            duplicate_entry = {
                "title": item["title"],
                "url": item["url"],
                "summary": item.get("summary", ""),
                "event_signature": event_signature(item["title"], item.get("summary", "")),
                "material_stage": material_stage(item["title"], item.get("summary", "")),
                "first_seen_kst": now.isoformat(timespec="seconds"),
                "suppressed_duplicate": duplicate_reason,
            }
            seen[k] = duplicate_entry
            dedupe_seen[k] = duplicate_entry
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
        # Reserve the event immediately so a second publisher in this very same run is suppressed.
        dedupe_seen[k] = {
            "title": item["title"],
            "url": item["url"],
            "summary": item.get("summary", ""),
            "event_signature": event_signature(item["title"], item.get("summary", "")),
            "material_stage": material_stage(item["title"], item.get("summary", "")),
            "first_seen_kst": now.isoformat(timespec="seconds"),
            "pending_alert": True,
        }

    if fresh:
        lines = [
            "<b>리벨리온 협력·수주·도입 웹감시</b>",
            "",
            f"조회시각: {now:%Y-%m-%d %H:%M} KST",
            f"신규 핵심 변화: {len(fresh)}건",
            "",
        ]
        for idx, (k, item) in enumerate(fresh[:8], start=1):
            category = tg_html(classify(item['title'], item.get('summary','')))
            title = tg_html(item['title'])
            source = tg_html(item['source'])
            published = tg_html(item.get('published_kst') or '페이지 직접 확인')
            direct_url = resolve_original_url(item['url'])
            link = tg_html(direct_url)
            lines.extend([
                f"{idx}. [{category}] {title}",
                f"- 출처: {source}" + (" · 공식" if item["official"] else ""),
                f"- 공개시각: {published}",
                f'- <a href="{link}">원문</a>',
                "",
            ])
            seen[k] = {
                "title": item["title"],
                "url": item["url"],
                "direct_url": direct_url,
                "summary": item.get("summary", ""),
                "event_signature": event_signature(item["title"], item.get("summary", "")),
                "material_stage": material_stage(item["title"], item.get("summary", "")),
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
        f"# 리벨리온 협력 웹감시\n\n- 상태: 정상 조회\n- 후보 항목: {len(ordered)}개\n- 신규 알림: {len(fresh)}개\n- 이번 실행 중복 억제: {duplicate_suppressed}개\n- 누적 중복키: {len(seen)}개\n- 조회시각: {now:%Y-%m-%d %H:%M} KST\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
