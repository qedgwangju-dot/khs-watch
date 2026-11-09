#!/usr/bin/env python3
"""NVIDIA/Korean AI startup engagement and overseas commercialization watch.

Strictly separates reported meetings from official attendance, paid pilots,
signed agreements, funding, overseas customer awards, and deliveries.
"""
from __future__ import annotations
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

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "nvidia_kstartup_global_watch_state.json"
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)
PENDING = OUT / "nvidia_kstartup_global_pending_state.json"
ALERT = OUT / "nvidia_kstartup_global_alert.html"
STATUS = OUT / "nvidia_kstartup_global_status.md"
KST = ZoneInfo("Asia/Seoul")
UA = {"User-Agent": "Mozilla/5.0 (compatible; khs-nvidia-kstartup-watch/1.0)",
      "Accept-Language": "ko,en;q=0.8"}

USER_HEADLINE = "[단독] 리벨리온 등 엔비디아와 간담회…AI 스타트업 해외진출 길 열리나"
USER_ARTICLE = "https://www.hankyung.com/article/2026110590351"
OFFICIAL_AI_DAY = "https://www.nvidia.com/ko-kr/ai-days/"
NVIDIA_BLOG = "https://blogs.nvidia.co.kr/blog/ai-day-seoul-2026-preview/"
RELEVANT_FIRMS = (
    ("rebellions", ("리벨리온", "rebellions")),
    ("furiosa", ("퓨리오사", "furiosa")),
    ("deepx", ("딥엑스", "deepx")),
    ("mobilint", ("모빌린트", "mobilint")),
    ("hyperaccel", ("하이퍼엑셀", "hyperaccel")),
    ("upstage", ("업스테이지", "upstage")),
    ("elice", ("엘리스그룹", "엘리스", "elice group")),
    ("nota", ("노타", "nota ai", "nota inc", "nota.ai")),
    ("lunit", ("루닛", "lunit")),
    ("vesslai", ("베슬ai", "vessl ai", "vesslai")),
    ("superbai", ("슈퍼브에이아이", "superb ai")),
    ("robotis", ("로보티즈", "robotis")),
    ("realworld", ("리얼월드", "realworld")),
    ("arobot", ("에이로봇", "a-robot")),
    ("frdai", ("프렌들리ai", "friendli ai")),
    ("twelvelabs", ("트웰브랩스", "twelvelabs")),
    ("piler", ("파일러", "piler")),
    ("ncai", ("nc ai", "엔씨ai", "ncai")),
    ("xyz", ("엑스와이지", "xyz robotics")),
)
EVENT_TERMS = (
    "간담회", "회동", "면담", "라운드테이블", "roundtable", "reception", "리셉션",
    "초청", "참석", "선정", "inception", "인셉션", "스타트업 커넥트",
    "startup connect", "해외진출", "해외 진출", "글로벌", "global",
    "미국 진출", "해외고객", "해외 고객", "공동개발", "공동 개발",
    "공동 실증", "실증", "기술제휴", "기술 제휴", "파트너십", "파트너",
    "업무협약", "mou", "협약 체결", "공급계약", "공급 계약",
    "납품", "발주", "수주", "고객 확보", "고객 계약", "투자", "지분", "인수",
    "협력", "partnership", "investment", "acquisition", "collaboration",
    "포럼", "forum", "공식 발표", "nvlink", "엔브이링크", "r200", "기업 방문",
    "방한 취소", "면담 취소", "회의 취소", "행사 무산",
)
NOISE = (
    "특징주", "관련주", "테마주", "상한가", "급등주", "주가 급등",
    "목표주가", "희망회로",
)
NEWS_SOURCES = (
    "한국경제", "hankyung", "연합뉴스", "yonhap", "뉴스핌", "이데일리",
    "전자신문", "머니투데이", "조선비즈", "지디넷", "zdnet",
    "디일렉", "thelec", "뉴시스", "매일경제", "서울경제",
    "아시아경제", "블룸버그", "bloomberg", "로이터", "reuters",
    "딜사이트", "더벨", "아이뉴스24", "디지털데일리", "techcrunch",
)
OFFICIAL_DOMAINS = (
    "nvidia.com", "blogs.nvidia.co.kr", "nvidianews.nvidia.com", "rebellions.ai", "kr.rebellions.ai",
    "fsc.go.kr", "msit.go.kr", "korea.kr", "nipa.kr", "kotra.or.kr",
    "furiosa.ai", "nota.ai", "upstage.ai", "lunit.io",
)
QUERIES = [
    '"리벨리온" "엔비디아" "간담회" when:30d',
    '"리벨리온" "엔비디아" "NVLink Fusion" when:30d',
    '"NVIDIA" "Rebellions" "NVLink Fusion" when:30d',
    'site:nvidianews.nvidia.com "Rebellions" "SK Telecom" when:45d',
    'site:msit.go.kr "엔비디아" "스타트업" "포럼" when:45d',
    '"리벨리온" "R200" (엔비디아 OR NVIDIA) when:45d',
    '"리벨리온" "엔비디아" (투자 OR 협력 OR 인수 OR 기술제휴) when:30d',
    '"엔비디아" "AI 스타트업" (해외진출 OR 간담회 OR 수출 OR 협력) when:30d',
    '"엔비디아" (리벨리온 OR 퓨리오사AI OR 업스테이지 OR 노타) (협력 OR 해외진출 OR 간담회) when:30d',
    '"NVIDIA" "Rebellions" (meeting OR investment OR partnership OR acquisition) when:45d',
    '"NVIDIA" ("Upstage" OR "Nota" OR "Furiosa") (partnership OR global OR customer) when:45d',
    '"NVIDIA" "Korean AI startups" (roundtable OR investment OR overseas) when:45d',
    '"엔비디아" "AI Day Seoul" (스타트업 OR 파트너 OR 인셉션 OR 투자) when:45d',
    '"NVIDIA" "Startup Connect" "Korea" when:45d',
    '"NVIDIA Inception" (한국 OR 리벨리온 OR 노타 OR 업스테이지 OR 루닛) when:60d',
    'site:blogs.nvidia.co.kr (스타트업 OR 인셉션 OR 리벨리온) when:90d',
    'site:nvidia.com ("Rebellions" OR "Korean startups") when:90d',
    'site:kr.rebellions.ai (NVIDIA OR 엔비디아) when:120d',
    '(리벨리온 OR 업스테이지 OR 노타 OR 루닛) 엔비디아 (해외 고객 OR 공급 계약 OR 글로벌) when:45d',
]
SEED_EVENTS = {
    "nvidia_korea|meeting|2026-06": {
        "title": "2026-06-08 엔비디아 젠슨 황 국내 AI·로봇 스타트업 회동",
        "stage": 1, "baseline": True,
        "source": "https://www.hankyung.com/article/2026060841581",
        "evidence": "과거 보도·공식 공급계약 아님",
    },
    "rebellions|deal_talk|2026-08": {
        "title": "2026-08 리벨리온-엔비디아 CEO 기술제휴·투자·인수 초기 논의 보도",
        "stage": 1, "baseline": True,
        "source": "https://news.bloomberglaw.com/artificial-intelligence/nvidia-in-talks-with-chip-startup-rebellions-for-potential-deal",
        "evidence": "초기 논의·투자/인수 확정 아님",
    },
    "nvidia_korea|meeting|2026-11": {
        "title": USER_HEADLINE,
        "stage": 1, "baseline": True,
        "source": USER_ARTICLE,
        "evidence": "2026-11-05 한국경제 본문 확인: 과기정통부 주선 11월 9일 비공개 간담회 예정, 리벨리온·퓨리오사AI·딥엑스·업스테이지·엘리스그룹 등은 참석 예정 또는 검토 중(전원 확정 아님)",
    },
    "nvidia_korea|ai_day_schedule|2026-11": {
        "title": "2026-11-09~10 NVIDIA AI Day Seoul 2026 및 11-10 Startup Connect 공식 행사 예정",
        "stage": 1, "baseline": True,
        "source": OFFICIAL_AI_DAY,
        "evidence": "NVIDIA 공식 일정, 리벨리온 개별 참가 여부 미확정",
    },
}

def now_kst():
    return dt.datetime.now(KST)

def clean(value):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))).strip()

def esc(value):
    return html.escape(str(value or ""), quote=True)

def fetch(url, timeout=15):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as resp:
        return resp.read().decode(resp.headers.get_content_charset() or "utf-8", "replace"), resp.geturl()

def pubdate(value):
    try:
        obj = email.utils.parsedate_to_datetime(value)
        if not obj.tzinfo:
            obj = obj.replace(tzinfo=dt.timezone.utc)
        return obj.astimezone(KST)
    except (ValueError, TypeError, OverflowError):
        return None

def firm_id(text):
    lower = clean(text).lower()
    for firm, aliases in RELEVANT_FIRMS:
        if any(a in lower for a in aliases):
            return firm
    return "nvidia_korea"

def source_tier(name, source_url):
    host = (urllib.parse.urlsplit(source_url or "").hostname or "").lower()
    if any(host == x or host.endswith("." + x) for x in OFFICIAL_DOMAINS):
        return "공식"
    if any(t.lower() in clean(name).lower() for t in NEWS_SOURCES):
        return "신뢰보도"
    return "기타"

def is_relevant(title, summary=""):
    lower = (clean(title) + " " + clean(summary)).lower()
    if not ("엔비디아" in lower or "nvidia" in lower or "젠슨 황" in lower or "jensen huang" in lower):
        return False
    if not any(t in lower for t in EVENT_TERMS):
        return False
    if any(t in lower for t in NOISE):
        return False
    has_startup = any(any(a in lower for a in aliases) for _, aliases in RELEVANT_FIRMS)
    has_korea = any(x in lower for x in ("한국", "국내", "korean", "korea", "k-ai"))
    return has_startup or (has_korea and any(x in lower for x in ("스타트업", "startup", "npu", "ai 반도체", "ai ecosystem", "인셉션")))

def exact_terms(text, terms):
    return any(x in text for x in terms)

def classify(title, source_tier_value="신뢰보도"):
    """Do not upgrade article speculation to a signed deal."""
    t = clean(title).lower()
    uncertain = exact_terms(t, ("검토", "논의", "협의", "추진", "가능", "예정",
                                 "관측", "유력", "기대", "전망", "모색", "열리나", "설"))
    if exact_terms(t, ("매디슨 황 방한 취소", "매디슨 황 방한 불참", "매디슨 황 방한 무산",
                       "기업 방문 무산", "본사 방문 취소", "본사 방문 무산", "면담 취소",
                       "회의 무산", "방한 취소", "불참", "방문 무산")) and not exact_terms(t,("계약 해지",)):
        return "visit_cancelled", 3, "방한·개별 면담 취소(포럼·협력 자체의 무산 아님)"
    if exact_terms(t, ("계약 해지", "투자 중단", "인수 중단", "협약 철회", "사업 철회")):
        return "deal_cancelled", 6, "계약 철회·중단"
    if exact_terms(t, ("NVLink Fusion", "nvlink fusion", "엔브이링크 퓨전", "nvlink")) and exact_terms(t, (
        "리벨리온", "rebellions")) and exact_terms(t, (
        "공식 발표", "발표", "협력", "collaboration", "announce", "협약", "체결", "연동")):
        return "nvlink_r200_collaboration", (5 if source_tier_value == "공식" else 4), "R200·NVLink Fusion 기술협력 발표(양산·납품 아님)"
    if exact_terms(t, ("스타트업 포럼 개최", "파트너십 포럼 개최", "스타트업 파트너십 포럼",
                       "startup partnership forum", "스타트업 22개사", "22개사 참여")):
        return "startup_forum_held", 2, "AI 스타트업 포럼 개최·교류(개별 계약 아님)"
    if not uncertain and exact_terms(t, ("투자 계약 체결", "지분 투자 확정", "인수 계약 체결",
                                        "투자 완료", "지분 취득 완료", "인수 완료")):
        return "capital_signed", 6, "투자·인수 확정"
    if not uncertain and exact_terms(t, ("해외 고객 공급계약", "해외 고객 공급 계약",
                                        "해외 수주", "글로벌 고객 계약", "판매계약 체결",
                                        "최초 해외 납품", "미국 고객 납품", "해외 공급계약 체결")):
        return "global_customer", 6, "해외 고객 계약·납품"
    if not uncertain and exact_terms(t, ("공동개발 계약 체결", "기술제휴 계약 체결", "전략적 제휴 계약 체결",
                                        "업무협약 체결", "파트너십 체결", "협력 계약 체결")):
        return "partnership_signed", 5, "기술·사업 협력 계약"
    if not uncertain and exact_terms(t, ("유료 실증", "실증 착수", "실증 계약", "공동 검증 개시",
                                        "기술 검증 완료", "고객 실증 완료", "공동 시연")):
        return "validation", 4, "공동 기술·고객 검증"
    if exact_terms(t, ("인셉션 선정", "inception 선정", "스타트업 커넥트 선정",
                       "startup connect 선정", "글로벌 파트너 프로그램 선정")):
        return "program_selected", 3, "공식 프로그램 선정" if source_tier_value == "공식" else "프로그램 선정 보도"
    if exact_terms(t, ("간담회 개최", "간담회 참석", "간담회 열려", "회의 참석",
                       "회동", "라운드테이블 참석", "초청 받아 참석")):
        return ("meeting_confirmed" if source_tier_value == "공식" else "meeting_reported",
                2, "간담회 참석 공식 확인" if source_tier_value == "공식" else "간담회 참석·회동 보도")
    if exact_terms(t, ("간담회", "초청", "만난다", "리셉션", "roundtable")):
        return "meeting", 1, "간담회·초청 보도(계약 미확정)"
    if exact_terms(t, ("ai day", "ai 데이", "스타트업 커넥트", "startup connect")):
        return "ai_day_schedule", 1, "행사 일정·교류(공급계약 아님)"
    if exact_terms(t, ("인수", "투자", "지분")) and uncertain:
        return "deal_talk", 1, "투자·인수 초기 논의(미확정)"
    if exact_terms(t, ("해외진출", "해외 진출", "글로벌", "global")):
        return "global_discussion", 1, "해외진출 가능성·지원 논의"
    return "ecosystem_news", 1, "협력 생태계 동향"

def event_id(item):
    title = item["title"]
    kind, stage, _ = classify(title, item.get("tier", "신뢰보도"))
    low = clean(title).lower()
    pdate = item.get("published_kst") or ""
    year_month = pdate[:7] if pdate else "unknown"
    if "2026-11" in year_month and kind in ("meeting", "meeting_reported", "meeting_confirmed"):
        # Same Nov-5 Korea startup roundtable in different publications; not the Jun-8 one.
        return f"nvidia_korea|{kind}|2026-11"
    if kind == "ai_day_schedule" and "2026-11" in year_month:
        return "nvidia_korea|ai_day_schedule|2026-11"
    if kind in ("nvlink_r200_collaboration", "startup_forum_held", "visit_cancelled"):
        return f"nvidia_korea|{kind}|{year_month}"
    firm = firm_id(title)
    if kind in ("meeting", "meeting_reported", "meeting_confirmed") and firm == "nvidia_korea":
        return f"nvidia_korea|{kind}|{year_month}"
    if kind in ("global_customer", "capital_signed", "partnership_signed", "validation"):
        # Different legal customers or agreement dates must not be silently folded into one deal.
        # An unidentified second deal remains a candidate for review in a new reporting month.
        normalized = re.sub(r"\s+", " ", re.sub(r"[^0-9a-z가-힣]+", " ", low))
        amount = re.search(r"\d+(?:[,.]\d+)*\s*(?:억원|조원|억달러|달러)", normalized)
        disambiguator = amount.group(0) if amount else year_month
        return f"{firm}|{kind}|{disambiguator}"
    return f"{firm}|{kind}|{year_month}"

def norm_title(title):
    t = clean(title).lower()
    t = re.sub(r"\s+-\s+[^-]{2,60}$", "", t)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9가-힣]+", " ", t)).strip()

def canonical_url(url):
    p = urllib.parse.urlsplit(clean(url))
    query = "" if p.hostname == "news.google.com" else p.query
    return urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), query, ""))

def article_key(item):
    value = canonical_url(item.get("url", "")) or norm_title(item["title"])
    return hashlib.sha256(value.encode()).hexdigest()[:24]

def collect():
    records, ok, errs = [], 0, []
    for query in QUERIES:
        url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(query) + "&hl=ko&gl=KR&ceid=KR:ko"
        try:
            raw, _ = fetch(url)
            root = ET.fromstring(raw)
            ok += 1
            for node in root.findall("./channel/item"):
                title = clean(node.findtext("title"))
                summary = clean(node.findtext("description"))
                if not is_relevant(title, summary):
                    continue
                source_node = node.find("source")
                source = clean(source_node.text) if source_node is not None else "Google News"
                source_url = source_node.get("url", "") if source_node is not None else ""
                tier = source_tier(source, source_url)
                if tier == "기타":
                    continue
                link = clean(node.findtext("link"))
                if not link:
                    continue
                published = pubdate(node.findtext("pubDate"))
                item = {
                    "title": title, "summary": summary, "url": link,
                    "source": source, "source_url": source_url, "tier": tier,
                    "published_kst": published.isoformat(timespec="minutes") if published else None,
                }
                kind, stage, label = classify(title, tier)
                item.update(kind=kind, stage=stage, label=label, event_id=event_id(item))
                records.append(item)
        except (OSError, ValueError, ET.ParseError) as exc:
            errs.append(type(exc).__name__ + ":" + query[:60])
    if ok < max(5, len(QUERIES) // 2):
        raise RuntimeError(f"NVIDIA/Korea startup news search unhealthy ({ok}/{len(QUERIES)} feeds)")
    official_ok = 0
    for source in (OFFICIAL_AI_DAY, NVIDIA_BLOG):
        try:
            body, _ = fetch(source, timeout=18)
            if "NVIDIA" in body or "엔비디아" in body:
                official_ok += 1
        except (OSError, ValueError):
            pass
    print(f"nvidia_kstartup_feed_health google={ok}/{len(QUERIES)} official_event={official_ok}/2 matches={len(records)}")
    return records, {"rss_ok": ok, "rss_total": len(QUERIES), "official_ok": official_ok, "errors": errs}

def read_state():
    if not STATE.exists():
        return {"initialized": False, "seen": {}, "events": {}}
    try:
        result = json.loads(STATE.read_text(encoding="utf-8"))
        if not isinstance(result, dict):
            raise ValueError("state is not an object")
        result.setdefault("seen", {})
        result.setdefault("events", {})
        return result
    except (OSError, ValueError, TypeError) as exc:
        raise RuntimeError("NVIDIA/Korea startup state damaged; do not silently re-bootstrap") from exc

def direct_url(url):
    if "news.google.com/" not in url:
        return url, "원문"
    try:
        from googlenewsdecoder import gnewsdecoder
        decoded = gnewsdecoder(url, interval=0)
        link = decoded.get("decoded_url") if isinstance(decoded, dict) and decoded.get("status") else None
        if link and link.startswith(("https://", "http://")) and "news.google.com/" not in link:
            return link, "원문"
    except Exception:
        pass
    try:
        _, link = fetch(url, timeout=8)
        if link and "news.google.com/" not in link:
            return link, "원문"
    except Exception:
        pass
    return url, "기사 보기(구글뉴스 경유)"

def record(item, now, **extra):
    return {k: item.get(k) for k in ("title", "url", "source", "published_kst",
                                   "event_id", "kind", "stage", "tier")} | {
        "first_seen_kst": now.isoformat(timespec="seconds"), **extra,
    }

def main():
    for f in (PENDING, ALERT, STATUS):
        f.unlink(missing_ok=True)
    now = now_kst()
    state = read_state()
    seen = dict(state.get("seen") or {})
    events = dict(state.get("events") or {})
    candidates, health = collect()
    unique = {}
    for item in candidates:
        key = article_key(item)
        if key not in unique or (item["tier"] == "공식" and unique[key]["tier"] != "공식"):
            unique[key] = item
    ordered = sorted(unique.values(), key=lambda x: (x.get("published_kst") or "", x.get("stage", 0)), reverse=True)

    if not state.get("initialized"):
        for k, v in SEED_EVENTS.items():
            events.setdefault(k, v | {"registered_kst": now.isoformat(timespec="seconds")})
        for item in ordered:
            seen[article_key(item)] = record(item, now, baseline=True)
            events.setdefault(item["event_id"], {
                "title": item["title"], "stage": item["stage"],
                "source": item["url"], "baseline": True,
                "registered_kst": now.isoformat(timespec="seconds"),
            })
        next_state = {"initialized": True, "bootstrap_kst": now.isoformat(timespec="seconds"),
                      "last_checked_kst": now.isoformat(timespec="seconds"),
                      "seen": seen, "events": events}
        PENDING.write_text(json.dumps(next_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        STATUS.write_text(
            f"# 엔비디아·한국 AI스타트업 해외사업 감시\n\n"
            f"- 상태: 최초 기준선\n- 뉴스 기준선: {len(seen)}건\n- 사건 기준선: {len(events)}개\n"
            f"- 신규 발송: 0건\n- RSS: {health['rss_ok']}/{health['rss_total']}\n"
            f"- 엔비디아 공식: {health['official_ok']}/2\n- 조회: {now:%Y-%m-%d %H:%M} KST\n",
            encoding="utf-8",
        )
        return

    try:
        checked = dt.datetime.fromisoformat(state["last_checked_kst"])
    except (KeyError, ValueError) as exc:
        raise RuntimeError("Last successful check missing") from exc
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=KST)
    new_items = []
    duplicates = stale = 0
    for item in ordered:
        key = article_key(item)
        if key in seen:
            continue
        date = dt.datetime.fromisoformat(item["published_kst"]) if item["published_kst"] else None
        if date and date > now + dt.timedelta(hours=2):
            continue
        if date and date < checked - dt.timedelta(hours=36) and date < now - dt.timedelta(days=7):
            seen[key] = record(item, now, suppressed_stale=True)
            stale += 1
            continue
        if item["event_id"] in events:
            seen[key] = record(item, now, suppressed_duplicate="same_event")
            duplicates += 1
            continue
        if len(new_items) >= 5:
            # Do not mark unsent events as sent, so later runs can deliver them.
            continue
        seen[key] = record(item, now, pending_alert=True)
        events[item["event_id"]] = {
            "title": item["title"], "source": item["url"], "stage": item["stage"],
            "registered_kst": now.isoformat(timespec="seconds"),
        }
        new_items.append(item)
    if new_items:
        lines = [
            "<b>엔비디아–국내 AI 스타트업 해외사업 변화 감시</b>",
            f"조회시각: {now:%Y-%m-%d %H:%M} KST · 신규 사건 {len(new_items)}건",
            "",
        ]
        for i, item in enumerate(new_items, 1):
            link, link_label = direct_url(item["url"])
            proof = "공식 발표 확인" if item["tier"] == "공식" else "언론 보도 · 공식 추가 확인 필요"
            lines.extend([
                f"<b>{i}. [{esc(item['label'])}] {esc(item['title'])}</b>",
                f"• 상태: {proof} · 단계 {item['stage']}/6",
                f"• 출처: {esc(item['source'])} · 공개: {esc(item['published_kst'] or '날짜 확인 필요')}",
            ])
            if item["stage"] <= 2:
                lines.append("• 주의: 간담회·초청·논의는 투자·수주·해외 고객 계약이 아닙니다.")
            if item.get("published_kst"):
                lag = int((now - dt.datetime.fromisoformat(item["published_kst"])).total_seconds() // 60)
                if lag > 90:
                    lines.append(f"• 검색·감지 시차: 약 {lag // 60}시간 {lag % 60}분")
            lines += [f'• <a href="{esc(link)}">{link_label}</a>', ""]
            seen[article_key(item)] = record(item, now, alerted=True)
            events[item["event_id"]]["alerted"] = True
        ALERT.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    if len(seen) > 1800:
        seen = dict(list(seen.items())[-1800:])
    next_state = {**{k: v for k, v in state.items() if k not in ("seen", "events")},
                  "initialized": True, "seen": seen, "events": events,
                  "last_checked_kst": now.isoformat(timespec="seconds")}
    PENDING.write_text(json.dumps(next_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    STATUS.write_text(
        f"# 엔비디아·한국 AI스타트업 해외사업 감시\n\n"
        f"- 후보: {len(ordered)}개 · 신규 사건: {len(new_items)}개\n"
        f"- 중복 억제: {duplicates}건 · 오래된 기사 억제: {stale}건\n"
        f"- RSS: {health['rss_ok']}/{health['rss_total']} · 공식: {health['official_ok']}/2\n"
        f"- 사건: {len(events)}개 · 조회: {now:%Y-%m-%d %H:%M} KST\n",
        encoding="utf-8",
    )

if __name__ == "__main__":
    main()
