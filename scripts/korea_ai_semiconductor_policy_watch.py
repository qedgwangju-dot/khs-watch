#!/usr/bin/env python3
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
STATE = ROOT / "data" / "korea_ai_semiconductor_policy_watch_state.json"
OUT = ROOT / "out"
OUT.mkdir(parents=True, exist_ok=True)
ALERT = OUT / "korea_ai_semiconductor_policy_watch_alert.html"
PENDING = OUT / "korea_ai_semiconductor_policy_watch_pending_state.json"
STATUS = OUT / "korea_ai_semiconductor_policy_watch_status.md"

KST = ZoneInfo("Asia/Seoul")
UA = "Mozilla/5.0 (compatible; KHSAISemiconductorPolicyWatch/1.0; +https://github.com/qedgwangju-dot/khs-watch)"

COMPANIES = (
    "리벨리온", "rebellions", "퓨리오사ai", "퓨리오사 ai", "furiosa", "딥엑스", "deepx",
    "모빌린트", "mobilint", "하이퍼엑셀", "hyperaccel",
)
CORE_TERMS = (
    "국산 ai 반도체", "국산 ai반도체", "국산 npu", "ai 반도체", "ai반도체", "npu",
) + COMPANIES

ACTION_TERMS = (
    "보조금", "지원금", "세제", "세액공제", "조달", "공공구매", "시범구매", "구매",
    "초기수요", "초기 수요", "지원사업", "사업공고", "공모", "선정", "협약", "예산",
    "출자", "투자", "정책금융", "수출금융", "무역보험", "보증", "해외실증", "해외 실증",
    "해외진출", "해외 진출", "수출", "공급계약", "공급 계약", "수주", "계약", "납품",
    "실증", "poc", "데이터센터", "국부펀드", "사우디", "아랍에미리트", "uae", "중동",
    "정상외교", "경제사절단", "정부지원", "정부 지원", "혁신제품", "수의계약",
)
NOISE_TERMS = (
    "특징주", "관련주", "상한가", "급등", "주가", "테마주", "목표주가", "증권사",
    "단순 부각", "수혜주",
)

OFFICIAL_MARKERS = (
    "과학기술정보통신부", "산업통상자원부", "금융위원회", "조달청", "기획재정부",
    "정보통신산업진흥원", "nipa", "한국수출입은행", "해외경제연구소", "수출입은행",
    "한국무역보험공사", "무역보험공사", "k-sure", "kotra", "대한무역투자진흥공사",
    "정책브리핑", "대통령실", "산업은행", "한국산업은행", "국회도서관", "국가전략포털",
)
TRUSTED_NEWS_MARKERS = (
    "연합뉴스", "뉴시스", "전자신문", "지디넷코리아", "zdnet", "디지털데일리",
    "디일렉", "thelec", "서울경제", "한국경제", "매일경제", "머니투데이", "이데일리",
    "조선비즈", "아시아경제", "파이낸셜뉴스", "뉴스핌", "블로터", "아이뉴스24",
    "이투데이", "아주경제", "비즈워치", "서울경제tv", "더벨",
)

QUERY_SPECS = [
    ("정책·초기수요", '"국산 AI 반도체" (보조금 OR 세액공제 OR 세제 OR 조달 OR 공공구매 OR 시범구매 OR 초기수요 OR 지원사업) when:60d'),
    ("정책·초기수요", '"국산 NPU" (조달 OR 구매 OR 보조금 OR 세액공제 OR 지원사업 OR 공공기관 OR 혁신제품) when:60d'),
    ("해외지원", '(리벨리온 OR 퓨리오사AI OR 딥엑스 OR 모빌린트 OR 하이퍼엑셀) (수출금융 OR 무역보험 OR 해외실증 OR 해외진출 OR 수출계약 OR 공급계약) when:60d'),
    ("중동", '(리벨리온 OR 퓨리오사AI OR 딥엑스 OR 모빌린트 OR 하이퍼엑셀) (사우디 OR UAE OR 아랍에미리트 OR 중동) (계약 OR 실증 OR 데이터센터 OR 국부펀드 OR 정부) when:60d'),
    ("공식-과기정통부", 'site:msit.go.kr ("AI 반도체" OR "NPU") (지원 OR 조달 OR 실증 OR 해외) when:90d'),
    ("공식-정책브리핑", 'site:korea.kr ("AI 반도체" OR "NPU") (지원 OR 조달 OR 실증 OR 해외) when:90d'),
    ("공식-금융위", 'site:fsc.go.kr ("AI 반도체" OR 리벨리온 OR 퓨리오사AI) (투자 OR 지원 OR 펀드 OR 금융) when:120d'),
    ("공식-조달청", 'site:pps.go.kr ("AI 반도체" OR "NPU") (혁신제품 OR 시범구매 OR 조달 OR 구매) when:120d'),
    ("공식-NIPA", 'site:nipa.kr ("AI 반도체" OR "NPU") (해외실증 OR 지원사업 OR 공모 OR 선정) when:120d'),
    ("공식-수은", '(site:koreaexim.go.kr OR site:keri.koreaexim.go.kr) ("AI 반도체" OR "NPU") when:180d'),
    ("공식-국가전략포털", 'site:nsp.nanet.go.kr ("AI반도체" OR "AI 반도체" OR "NPU") (한국수출입은행 OR 정부 OR 정책 OR 지원) when:180d'),
    ("공식-KOTRA", 'site:kotra.or.kr ("AI 반도체" OR "NPU") (중동 OR 사우디 OR UAE OR 해외진출) when:180d'),
    ("공식-무보", 'site:ksure.or.kr ("AI 반도체" OR "NPU") (수출 OR 보증 OR 금융 OR 중동) when:180d'),
]


def now_kst() -> dt.datetime:
    return dt.datetime.now(KST)


def norm(value: str | None) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", " ", value or ""))
    return re.sub(r"\s+", " ", value).strip()


def esc(value: str | None) -> str:
    return html.escape(str(value or ""), quote=True)


def fetch_text(url: str, timeout: int = 30) -> tuple[str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
        final_url = resp.geturl()
        charset = resp.headers.get_content_charset() or "utf-8"
    return data.decode(charset, errors="replace"), final_url


def parse_pubdate(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(KST)
    except Exception:
        return None


def normalize_title(value: str) -> str:
    text = norm(value).lower()
    text = re.sub(r"\s+-\s+[^-]{2,60}$", "", text)
    text = re.sub(r"[^0-9a-z가-힣]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def canonical_url(value: str) -> str:
    value = norm(value)
    try:
        p = urllib.parse.urlsplit(value)
        query = "" if p.netloc.lower() == "news.google.com" else p.query
        return urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), query, ""))
    except Exception:
        return value


def resolve_original_url(value: str) -> str:
    if "news.google.com/" not in value:
        return value
    try:
        _, final = fetch_text(value, timeout=12)
        if final and "news.google.com/" not in final:
            return final
    except Exception:
        pass
    return value


def source_quality(source: str, lane: str) -> str:
    text = f"{source} {lane}".lower()
    if lane.startswith("공식-") or any(x.lower() in text for x in OFFICIAL_MARKERS):
        return "공식"
    if any(x.lower() in text for x in TRUSTED_NEWS_MARKERS):
        return "신뢰보도"
    return "기타보도"


def is_relevant(title: str, summary: str) -> bool:
    text = f"{norm(title)} {norm(summary)}".lower()
    if any(term in text for term in NOISE_TERMS):
        return False
    return any(term in text for term in CORE_TERMS) and any(term in text for term in ACTION_TERMS)


def classify(text: str, quality: str) -> tuple[str, int]:
    t = norm(text).lower()

    # Highest-priority: money or purchase commitment is actually fixed.
    if any(x in t for x in ("수주", "공급계약", "공급 계약", "구매계약", "구매 계약", "발주", "낙찰", "납품")):
        return "실제 수주·구매", 5
    if any(x in t for x in ("수출금융 승인", "보증 승인", "금융지원 확정", "투자 승인", "직접투자", "출자 승인")):
        return "정책금융 확정", 5
    if any(x in t for x in ("세액공제", "보조금", "지원금")) and any(x in t for x in ("신설", "확정", "시행", "의결", "공고")):
        return "세제·보조금 확정", 5
    if any(x in t for x in ("예산", "사업비")) and any(x in t for x in ("확정", "의결", "공고", "편성", "배정")):
        return "예산·사업 확정", 5

    if any(x in t for x in ("선정", "협약체결", "협약 체결", "시범구매", "수의계약", "혁신제품")):
        return "조달·선정·협약", 4
    if any(x in t for x in ("해외실증", "해외 실증", "현지실증", "현지 실증", "poc", "실증")) and any(
        x in t for x in ("사우디", "uae", "아랍에미리트", "중동", "해외")
    ):
        return "해외 실증", 4
    if any(x in t for x in ("정상외교", "경제사절단", "정부 간", "정부간", "국부펀드")):
        return "정부·중동 사업화 지원", 4

    if any(x in t for x in ("지원사업", "사업공고", "공모", "조달", "공공구매", "초기수요", "초기 수요")):
        return "초기수요 정책", 3
    if any(x in t for x in ("수출금융", "무역보험", "보증", "해외진출", "해외 진출")):
        return "해외진출 지원", 3
    if quality == "공식" and any(x in t for x in ("보고서", "연구소", "제안", "필요")) and any(
        x in t for x in ("보조금", "세액공제", "초기수요", "초기 수요", "해외진출", "해외 진출", "공공구매")
    ):
        return "정책 선행신호", 2

    return "정책·산업 변화", 1


def entity_key(text: str) -> str:
    t = norm(text).lower()
    aliases = [
        ("리벨리온", ("리벨리온", "rebellions")),
        ("퓨리오사AI", ("퓨리오사ai", "퓨리오사 ai", "furiosa")),
        ("딥엑스", ("딥엑스", "deepx")),
        ("모빌린트", ("모빌린트", "mobilint")),
        ("하이퍼엑셀", ("하이퍼엑셀", "hyperaccel")),
    ]
    found = [name for name, xs in aliases if any(x in t for x in xs)]
    return "+".join(found) if found else "국산AI반도체산업"


def topic_key(text: str) -> str:
    t = norm(text).lower()
    for key, terms in [
        ("혁신제품", ("혁신제품", "시범구매", "수의계약")),
        ("해외실증", ("해외실증", "해외 실증", "현지실증", "현지 실증")),
        ("세제보조", ("세액공제", "보조금", "지원금")),
        ("정책금융", ("수출금융", "무역보험", "보증", "직접투자", "출자")),
        ("중동", ("사우디", "uae", "아랍에미리트", "중동", "국부펀드")),
        ("공공수요", ("공공구매", "초기수요", "초기 수요", "조달")),
        ("지원사업", ("지원사업", "사업공고", "공모", "선정")),
    ]:
        if any(x in t for x in terms):
            return key
    return "일반"


def event_signature(item: dict) -> str:
    category, _ = classify(f"{item['title']} {item.get('summary','')}", item["quality"])
    return f"{entity_key(item['title'] + ' ' + item.get('summary',''))}|{category}|{topic_key(item['title'] + ' ' + item.get('summary',''))}"


def amount_tokens(text: str) -> list[str]:
    found = re.findall(
        r"(?:약\s*)?\d+(?:[,.]\d+)*(?:조\s*원|억원|만억원|천억원|백억원|억\s*달러|만\s*달러|달러|억원\s*내외)",
        norm(text),
    )
    out = []
    for value in found:
        value = re.sub(r"\s+", "", value)
        if value not in out:
            out.append(value)
    return out[:5]


def key_for(item: dict) -> str:
    raw = f"{normalize_title(item['title'])}|{canonical_url(item['url'])}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def collect_google_news() -> list[dict]:
    items = []
    for lane, query in QUERY_SPECS:
        url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(query) + "&hl=ko&gl=KR&ceid=KR:ko"
        try:
            xml_text, _ = fetch_text(url)
            root = ET.fromstring(xml_text)
        except Exception:
            continue
        for node in root.findall(".//item"):
            title = norm(node.findtext("title") or "")
            link = norm(node.findtext("link") or "")
            summary = norm(node.findtext("description") or "")
            source_node = node.find("source")
            source = norm(source_node.text if source_node is not None else "Google News")
            if not title or not link or not is_relevant(title, summary):
                continue
            pub = parse_pubdate(node.findtext("pubDate"))
            quality = source_quality(source, lane)
            category, stage = classify(f"{title} {summary}", quality)
            # Low-signal items are only kept when they come from official sources.
            if stage <= 1 and quality != "공식":
                continue
            items.append(
                {
                    "title": title,
                    "url": link,
                    "summary": summary,
                    "source": source,
                    "lane": lane,
                    "quality": quality,
                    "category": category,
                    "stage": stage,
                    "published_kst": pub.isoformat(timespec="minutes") if pub else None,
                }
            )
    return items


def load_state() -> dict:
    if not STATE.exists():
        return {"initialized": False, "seen": {}}
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"initialized": False, "seen": {}}
    state.setdefault("seen", {})
    return state


def entry_time(entry: dict) -> dt.datetime | None:
    raw = str(entry.get("first_seen_kst") or "")
    try:
        value = dt.datetime.fromisoformat(raw)
        if value.tzinfo is None:
            value = value.replace(tzinfo=KST)
        return value
    except Exception:
        return None


def duplicate_reason(item: dict, seen: dict, now: dt.datetime) -> str | None:
    url = canonical_url(item["url"])
    title = normalize_title(item["title"])
    sig = event_signature(item)
    for prior in seen.values():
        if url and canonical_url(prior.get("url", "")) == url:
            return "same_url"
        if title and normalize_title(prior.get("title", "")) == title:
            return "same_title"

    # Same underlying stage/event from another publisher: suppress for 7 days.
    cutoff = now - dt.timedelta(days=7)
    for prior in seen.values():
        if not prior.get("alerted"):
            continue
        when = entry_time(prior)
        if not when or when < cutoff:
            continue
        if prior.get("event_signature") == sig:
            return f"same_event:{sig}"
    return None


def main() -> None:
    for path in (ALERT, PENDING, STATUS):
        if path.exists():
            path.unlink()

    now = now_kst()
    state = load_state()
    seen = dict(state.get("seen") or {})

    candidates = collect_google_news()
    deduped = {}
    for item in candidates:
        key = key_for(item)
        current = deduped.get(key)
        if current is None or item["stage"] > current["stage"] or item["quality"] == "공식":
            deduped[key] = item

    ordered = sorted(
        deduped.items(),
        key=lambda kv: (kv[1].get("published_kst") or "", kv[1]["stage"]),
    )

    if not state.get("initialized"):
        for key, item in ordered:
            seen[key] = {
                "title": item["title"],
                "url": item["url"],
                "event_signature": event_signature(item),
                "stage": item["stage"],
                "category": item["category"],
                "first_seen_kst": now.isoformat(timespec="seconds"),
                "baseline": True,
            }
        pending = {
            "initialized": True,
            "bootstrap_kst": now.isoformat(timespec="seconds"),
            "last_checked_kst": now.isoformat(timespec="seconds"),
            "seen": seen,
        }
        PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        STATUS.write_text(
            f"# 국산 AI반도체 정책·초기수요·해외수주 감시\n\n"
            f"- 상태: 초기 기준선 생성\n"
            f"- 기준선 후보: {len(ordered)}개\n"
            f"- 신규 알림: 0개\n"
            f"- 조회시각: {now:%Y-%m-%d %H:%M:%S} KST\n",
            encoding="utf-8",
        )
        return

    try:
        last_checked = dt.datetime.fromisoformat(str(state.get("last_checked_kst") or ""))
        if last_checked.tzinfo is None:
            last_checked = last_checked.replace(tzinfo=KST)
    except Exception:
        last_checked = now - dt.timedelta(days=2)

    fresh = []
    suppressed_duplicate = 0
    suppressed_stale = 0

    for key, item in ordered:
        if key in seen:
            continue

        reason = duplicate_reason(item, seen, now)
        if reason:
            suppressed_duplicate += 1
            seen[key] = {
                "title": item["title"],
                "url": item["url"],
                "event_signature": event_signature(item),
                "stage": item["stage"],
                "category": item["category"],
                "first_seen_kst": now.isoformat(timespec="seconds"),
                "suppressed_duplicate": reason,
            }
            continue

        pub = None
        if item.get("published_kst"):
            try:
                pub = dt.datetime.fromisoformat(item["published_kst"])
            except Exception:
                pass
        if pub and pub < last_checked - dt.timedelta(hours=30):
            suppressed_stale += 1
            seen[key] = {
                "title": item["title"],
                "url": item["url"],
                "event_signature": event_signature(item),
                "stage": item["stage"],
                "category": item["category"],
                "first_seen_kst": now.isoformat(timespec="seconds"),
                "suppressed_stale": True,
            }
            continue

        # Telegram should prioritize verified policy/business changes, not theme/news noise.
        if item["quality"] == "기타보도":
            seen[key] = {
                "title": item["title"],
                "url": item["url"],
                "event_signature": event_signature(item),
                "stage": item["stage"],
                "category": item["category"],
                "first_seen_kst": now.isoformat(timespec="seconds"),
                "suppressed_low_quality": True,
            }
            continue
        # Stage 2 policy research is useful only from official/public research sources.
        if item["stage"] == 2 and item["quality"] != "공식":
            continue
        fresh.append((key, item))

    if fresh:
        fresh.sort(key=lambda kv: (kv[1]["stage"], kv[1].get("published_kst") or ""), reverse=True)
        lines = [
            "<b>국산 AI반도체 정책·초기수요·해외수주</b>",
            "",
            f"조회시각: {now:%Y-%m-%d %H:%M} KST",
            f"신규 핵심 변화: {len(fresh)}건",
            "",
        ]

        for idx, (key, item) in enumerate(fresh[:6], start=1):
            direct = resolve_original_url(item["url"])
            amounts = amount_tokens(f"{item['title']} {item.get('summary','')}")
            priority = "최우선" if item["stage"] >= 5 else "중요" if item["stage"] >= 3 else "선행신호"
            lines.extend(
                [
                    f"<b>{idx}. [{esc(priority)} · {esc(item['category'])}] {esc(item['title'])}</b>",
                    f"• 상태: {esc(item['quality'])} · 단계 {item['stage']}/5",
                    f"• 대상: {esc(entity_key(item['title'] + ' ' + item.get('summary','')))}",
                ]
            )
            if amounts:
                lines.append("• 금액: " + esc(" · ".join(amounts)))
            if item.get("published_kst"):
                lines.append(f"• 공개: {esc(item['published_kst'])}")
            lines.append(f"• 출처: {esc(item['source'])}")
            lines.append(f'<a href="{esc(direct)}">원문</a>')
            lines.append("")

            seen[key] = {
                "title": item["title"],
                "url": item["url"],
                "direct_url": direct,
                "event_signature": event_signature(item),
                "stage": item["stage"],
                "category": item["category"],
                "first_seen_kst": now.isoformat(timespec="seconds"),
                "alerted": True,
            }

        if len(fresh) > 6:
            lines.append(f"※ 한 번에 6건만 송출. 추가 {len(fresh)-6}건은 다음 실행에서 재평가합니다.")

        ALERT.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

    if len(seen) > 1200:
        seen = dict(list(seen.items())[-1200:])

    pending = {
        **{k: v for k, v in state.items() if k != "seen"},
        "initialized": True,
        "last_checked_kst": now.isoformat(timespec="seconds"),
        "seen": seen,
    }
    PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    STATUS.write_text(
        f"# 국산 AI반도체 정책·초기수요·해외수주 감시\n\n"
        f"- 상태: 정상 조회\n"
        f"- 후보 항목: {len(ordered)}개\n"
        f"- 신규 알림: {len(fresh)}개\n"
        f"- 중복 억제: {suppressed_duplicate}개\n"
        f"- 오래된 재노출 억제: {suppressed_stale}개\n"
        f"- 누적 상태: {len(seen)}개\n"
        f"- 조회시각: {now:%Y-%m-%d %H:%M:%S} KST\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
