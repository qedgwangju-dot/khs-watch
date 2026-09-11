#!/usr/bin/env python3
"""KHS high-impact nuclear / AI power policy watch."""

from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from khs_compact_text import concise_text
from khs_policy_alert_explainer import ensure_explained
from khs_policy_alert_router import compact_explanation_lines

KST = ZoneInfo("Asia/Seoul")
UTC = dt.timezone.utc
OUT_DIR = Path("out")
DATA_DIR = Path("data")
SEEN_PATH = DATA_DIR / "khs_nuclear_policy_seen.json"
ALERT_PATH = OUT_DIR / "khs_nuclear_policy_alert.md"
TITLE_PATH = OUT_DIR / "khs_nuclear_policy_title.txt"
ALERTS_JSON_PATH = OUT_DIR / "khs_nuclear_policy_alerts.json"
MAX_SOURCE_AGE_HOURS = int(os.getenv("KHS_NUCLEAR_MAX_AGE_HOURS", "72"))
FORMAT_VERSION = "ko-v3-westinghouse-state"

SOURCES = [
    {
        "name": "Westinghouse strategic partnership",
        "url": "https://westinghousenuclear.com/strategic-partnership/press-releases/brookfield/",
        "kind": "direct",
    },
    {
        "name": "DOE Nuclear Energy",
        "url": "https://www.energy.gov/ne/articles/9-key-takeaways-president-trumps-executive-orders-nuclear-energy",
        "kind": "direct",
    },
]

WEC_RSS_QUERIES = [
    ("웨스팅하우스 지분·한국 뉴스", "웨스팅하우스 지분 인수 한국전력 산업통상부 한수원 브룩필드 카메코 when:14d"),
    ("웨스팅하우스 지분·해외 뉴스", "Westinghouse stake Korea KEPCO KHNP Brookfield Cameco when:14d"),
    ("웨스팅하우스 지분·공식입장 추적", "웨스팅하우스 산업통상부 한국전력 공식 발표 when:30d"),
]

NUCLEAR_TERMS = [
    "westinghouse", "ap1000", "ap300", "nuclear reactor", "nuclear reactors",
    "new reactors", "nuclear power", "nuclear energy", "uranium", "nuclear fuel",
    "loan guarantee", "low-cost loans", "strategic partnership", "nuclear regulatory commission",
    "nrc", "data center", "data centers", "artificial intelligence", "ai race",
]
HIGH_IMPACT_TERMS = [
    "$80 billion", "80 billion", "$17.5 billion", "17.5 billion", "10 new reactors",
    "10 nuclear reactors", "at least $80 billion", "executive order", "president trump",
    "department of energy", "secretary of energy", "commerce", "u.s. government",
]

WEC_CORE = ["westinghouse", "웨스팅하우스", "wec"]
WEC_TRANSACTION = [
    "지분", "인수", "투자", "공동 인수", "공동인수", "출자", "주주", "경영 참여",
    "stake", "equity", "acquisition", "invest", "shareholder", "buyout", "ipo", "상장", "기업공개",
    "brookfield", "브룩필드", "cameco", "카메코", "kepco", "한국전력", "한전", "khnp", "한수원",
    "산업통상부", "산업부", "미국 정부", "u.s. government", "ap1000", "지식재산", "입찰 제한",
]
WEC_MATERIAL = [
    "공식 발표", "공식 확인", "공식 부인", "사실과 다르", "부인",
    "합의", "계약", "loi", "mou", "양해각서", "실사", "due diligence",
    "협상 개시", "협상 착수", "본협상", "우선협상", "term sheet", "텀시트",
    "취득", "매각", "지분율", "인수가격", "매각가격", "출자액", "투자금",
    "경영권", "이사회", "의결권", "voting rights",
    "cfius", "nrc", "승인", "인가",
    "사업권", "설계권", "조달권", "시공권", "입찰 제한", "지식재산권",
    "상장 신청", "ipo filing", "ipo 신청",
]
WEC_COMMENTARY = [
    "고차방정식", "열쇠", "주식인가", "사업인가", "전망", "분석", "진단",
    "수혜", "들썩", "특징주", "상승세", "주목", "기대", "논란", "평가",
]
WEC_OFFICIAL_OUTLETS = [
    "산업통상부", "정책브리핑", "한국전력", "한수원", "kepco", "khnp",
    "westinghouse", "cameco", "brookfield",
]

SOURCE_LABELS = {
    "Westinghouse strategic partnership": "Westinghouse 공식 전략 파트너십 발표",
    "DOE Nuclear Energy": "미국 에너지부 원전정책 공식자료",
}

TERM_LABELS = {
    "$80 billion": "최소 800억 달러 규모",
    "80 billion": "800억 달러",
    "$17.5 billion": "175억 달러",
    "17.5 billion": "175억 달러",
    "10 new reactors": "신규 원전 10기",
    "10 nuclear reactors": "원전 10기",
    "at least $80 billion": "최소 800억 달러",
    "executive order": "행정명령",
    "president trump": "트럼프 대통령",
    "department of energy": "미국 에너지부",
    "secretary of energy": "미국 에너지부 장관",
    "commerce": "상무부",
    "u.s. government": "미국 정부",
    "westinghouse": "Westinghouse",
    "ap1000": "AP1000",
    "ap300": "AP300",
    "nuclear reactor": "원자로",
    "nuclear reactors": "원자로",
    "new reactors": "신규 원전",
    "nuclear power": "원전",
    "nuclear energy": "원자력 에너지",
    "uranium": "우라늄",
    "nuclear fuel": "핵연료",
    "loan guarantee": "대출보증",
    "low-cost loans": "저리 대출",
    "strategic partnership": "전략적 파트너십",
    "nuclear regulatory commission": "미 원자력규제위원회",
    "nrc": "미 원자력규제위원회",
    "data center": "데이터센터",
    "data centers": "데이터센터",
    "artificial intelligence": "인공지능",
    "ai race": "AI 경쟁",
}


def now_kst() -> dt.datetime:
    return dt.datetime.now(tz=KST)


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = re.sub(r"<script\b.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style\b.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "KHS-nuclear-policy-watch contact=github-actions"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode(resp.headers.get_content_charset() or "utf-8", errors="replace")


def parse_date(text: str) -> dt.datetime | None:
    patterns = [
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+20\d{2}\b",
        r"\b20\d{2}-\d{2}-\d{2}\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        value = match.group(0)
        for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
            try:
                return dt.datetime.strptime(value, fmt).replace(tzinfo=KST)
            except ValueError:
                pass
    return None


def title_from_text(text: str, fallback: str) -> str:
    match = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.I | re.S)
    return clean_text(match.group(1)) if match else fallback


def collect_direct_items(now: dt.datetime) -> list[dict]:
    items: list[dict] = []
    for source in SOURCES:
        try:
            raw = fetch_text(source["url"])
        except Exception as exc:
            print(f"nuclear_source_error={source['name']} {exc}")
            continue
        title = title_from_text(raw, source["name"])
        body = clean_text(raw)
        published = parse_date(body)
        if published:
            age_hours = (now - published).total_seconds() / 3600
            if age_hours > MAX_SOURCE_AGE_HOURS:
                continue
        haystack = f"{title} {body}".lower()
        matched = [term for term in NUCLEAR_TERMS + HIGH_IMPACT_TERMS if term.lower() in haystack]
        if not any(term in matched for term in NUCLEAR_TERMS):
            continue
        if not any(term in matched for term in HIGH_IMPACT_TERMS):
            continue
        fingerprint = hashlib.sha256(
            f"{FORMAT_VERSION}|direct|{source['name']}|{title}|{source['url']}".encode("utf-8")
        ).hexdigest()[:16]
        items.append({
            "kind": "direct_official",
            "fingerprint": fingerprint,
            "source": source["name"],
            "title": title,
            "link": source["url"],
            "published_kst": published.isoformat() if published else "확인 불가",
            "matched": sorted(set(matched))[:12],
        })
    return items


def _google_news_url(query: str) -> str:
    return (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote_plus(query)
        + "&hl=ko&gl=KR&ceid=KR:ko"
    )


def _clean_rss_title(title: str) -> str:
    title = clean_text(title)
    return re.sub(r"\s+-\s+[^-]{2,80}$", "", title).strip()


def _is_official_outlet(outlet: str) -> bool:
    low = (outlet or "").lower()
    return any(term.lower() in low for term in WEC_OFFICIAL_OUTLETS)


def _has_numeric_terms(title: str) -> bool:
    return bool(
        re.search(
            r"(?:\$|달러|원|억원|조원|%|퍼센트).*?\d|\d[\d,.]*\s*(?:억달러|달러|억원|조원|%)",
            title.lower(),
        )
    )


def _is_material_westinghouse(title: str, outlet: str = "") -> bool:
    low = title.lower()
    if not (any(term in low for term in WEC_CORE) and any(term in low for term in WEC_TRANSACTION)):
        return False

    if _is_official_outlet(outlet):
        return True

    if any(term in low for term in WEC_COMMENTARY):
        strong = [
            "공식", "합의", "계약", "loi", "mou", "실사", "취득", "매각",
            "지분율", "인수가격", "출자액", "투자금", "cfius", "nrc", "승인",
        ]
        if not any(term in low for term in strong):
            return False

    return any(term in low for term in WEC_MATERIAL) or _has_numeric_terms(title)


def _wec_status(title: str, outlet: str = "") -> str:
    low = title.lower()
    if any(term in low for term in ("사실과 다르", "공식 부인", "부인", "denies", "not true")):
        return "공식 부인·정정" if _is_official_outlet(outlet) or "공식" in low else "부인 보도"
    if any(term in low for term in ("계약", "합의", "agreement", "contract")):
        return "계약·합의 단계"
    if any(term in low for term in ("loi", "mou", "양해각서", "term sheet", "텀시트")):
        return "LOI·MOU·텀시트 단계"
    if any(term in low for term in ("실사", "due diligence")):
        return "실사 단계"
    if any(term in low for term in ("협상 개시", "협상 착수", "본협상", "우선협상")):
        return "협상 단계"
    if any(term in low for term in ("취득", "매각", "인수 확정", "투자 확정")):
        return "지분 거래 확정 신호"
    if any(term in low for term in ("cfius", "nrc", "승인", "인가")):
        return "규제·승인 단계"
    if any(term in low for term in ("사업권", "설계권", "조달권", "시공권", "입찰 제한", "지식재산권")):
        return "사업권·지식재산 조건 변화"
    if any(term in low for term in ("지분율", "인수가격", "매각가격", "출자액", "투자금")) or _has_numeric_terms(title):
        return "지분율·가격 등 거래조건 변화"
    if _is_official_outlet(outlet):
        return "공식 입장 변화"
    return "새 물질적 조건 확인"


def _wec_numbers(title: str) -> tuple[str, ...]:
    found = re.findall(
        r"\d[\d,.]*(?:\s*)?(?:%|퍼센트|억달러|달러|억원|조원|원)",
        title,
        flags=re.I,
    )
    return tuple(dict.fromkeys(re.sub(r"\s+", "", value) for value in found))[:6]


def _wec_state_key(title: str, outlet: str = "") -> str:
    status = _wec_status(title, outlet)
    numbers = "|".join(_wec_numbers(title)) or "no-number"
    official = "official" if _is_official_outlet(outlet) else "reported"
    return f"{status}|{numbers}|{official}"


def collect_westinghouse_stake_items(now: dt.datetime) -> list[dict]:
    rows: list[dict] = []
    seen_story: set[str] = set()
    for source_name, query in WEC_RSS_QUERIES:
        url = _google_news_url(query)
        try:
            raw = fetch_text(url)
            root = ET.fromstring(raw)
        except Exception as exc:
            print(f"westinghouse_rss_error={source_name} {exc}")
            continue

        for node in root.findall(".//item"):
            title = _clean_rss_title(node.findtext("title") or "")
            link = clean_text(node.findtext("link") or "")
            source_node = node.find("source")
            outlet = clean_text(source_node.text if source_node is not None and source_node.text else source_name)
            pub_text = clean_text(node.findtext("pubDate") or "")
            if not title or not link or not _is_material_westinghouse(title, outlet):
                continue
            try:
                published = parsedate_to_datetime(pub_text)
                if published.tzinfo is None:
                    published = published.replace(tzinfo=UTC)
                published = published.astimezone(UTC)
            except Exception:
                published = now.astimezone(UTC)
            age_days = (now.astimezone(UTC) - published).total_seconds() / 86400
            if age_days > 30:
                continue

            story_key = f"{title.lower()}|{outlet.lower()}"
            if story_key in seen_story:
                continue
            seen_story.add(story_key)
            rows.append({
                "kind": "westinghouse_stake",
                "source": outlet or source_name,
                "title": title[:500],
                "link": link,
                "published_kst": published.astimezone(KST).isoformat(timespec="seconds"),
                "published_utc": published.isoformat(timespec="seconds"),
                "state_key": _wec_state_key(title, outlet),
                "status": _wec_status(title, outlet),
                "matched": ["westinghouse", "stake", "korea"],
            })
    rows.sort(key=lambda item: item.get("published_utc", ""), reverse=True)
    return rows[:20]


def load_seen() -> dict:
    if not SEEN_PATH.exists():
        return {"seen": {}, "updated_at_kst": ""}
    try:
        return json.loads(SEEN_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"seen": {}, "updated_at_kst": ""}


def save_seen(seen: dict, now: dt.datetime) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    seen["updated_at_kst"] = now.isoformat(timespec="seconds")
    SEEN_PATH.write_text(json.dumps(seen, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _render_direct(item: dict, idx: int, now: dt.datetime) -> list[str]:
    ko_title = "미국, Westinghouse AP1000 원전·AI 전력 정책 지원 신호"
    if "80" in " ".join(item["matched"]):
        ko_title = "미국, Westinghouse 원전 건설 대형 지원 신호"
    source_label = SOURCE_LABELS.get(item["source"], item["source"])
    evidence = ", ".join(dict.fromkeys(TERM_LABELS.get(term, term) for term in item["matched"]))
    explain_item = {
        **item,
        "title": ko_title,
        "summary": evidence,
        "matched": {"energy_security_policy": list(item["matched"])},
        "impacts": ["시간표", "돈 버는 능력", "수급"],
        "paths": ["원전 정책 타임라인", "AI 데이터센터 전력수요", "원전 밸류체인", "우라늄/원전기기 수급"],
        "sectors": ["원전/전력기기", "전력망/데이터센터", "우라늄", "SMR/대형원전 기자재"],
    }
    ensure_explained(explain_item)
    compact_evidence = concise_text(
        evidence,
        fallback="AP1000·AI 전력·원전 지원 근거를 확인했습니다.",
    )
    return [
        f"## {idx}. [상·확정] {ko_title}",
        f"- 출처: [{source_label}]({item['link']}) · 원천시각 {item['published_kst']} · 조회 {now:%H:%M KST}",
        f"- 확인 근거: {compact_evidence}",
        *compact_explanation_lines(explain_item),
        "- 다음 확인: 후속 공시·DOE/NRC 일정·국내 수급",
        "",
    ]


def _render_westinghouse_stake(item: dict, idx: int, now: dt.datetime) -> list[str]:
    status = item.get("status") or "추가 확인 필요"
    unconfirmed = status not in {"계약·합의 단계", "지분 거래 확정 신호", "공식 부인·정정"}
    verdict = "보도·검토 단계 — 공식 거래조건 확인 전" if unconfirmed else status
    return [
        f"## {idx}. [상·{'보도 단계' if unconfirmed else '상태 변화'}] 한국의 Westinghouse 지분 참여 이슈",
        f"- 출처: [{item['source']}]({item['link']}) · 원천시각 {item['published_kst']} · 조회 {now:%H:%M KST}",
        f"- 현재 판정: {verdict}",
        f"- 이번에 달라진 것: {item['title']}",
        "- 투자 의미: 지분 참여가 실제화되면 미국 AP1000 사업 참여가 기자재·시공을 넘어 사업개발·조달로 넓어질 여지가 있습니다.",
        "- 미확정: 지분율·가격·의결권·경영참여권, AP1000 설계·조달·시공 권한, 지식재산권·입찰제한 완화는 별도 확인이 필요합니다.",
        "- 핵심 병목: Brookfield 51%·Cameco 49% 기존 주주 합의, CFIUS/NRC 심사, 투자 재원과 실제 사업권 연결 조건.",
        "- 다음 실제 트리거: 산업통상부·한국전력·한수원·Westinghouse·Brookfield·Cameco 공식 발표, LOI/MOU·실사·본협상, 지분율·인수가격 공개.",
        "",
    ]


def render(alerts: list[dict], now: dt.datetime) -> str:
    lines = [f"🚨 [원전·Westinghouse 웹감시] · {now:%Y년 %m월 %d일 %H:%M KST}", ""]
    for idx, item in enumerate(alerts, 1):
        if item.get("kind") == "westinghouse_stake":
            lines.extend(_render_westinghouse_stake(item, idx, now))
        else:
            lines.extend(_render_direct(item, idx, now))
    lines.extend([
        "💡 워치 판단: 새 기사 수가 아니라 공식 입장·거래단계·지분율·가격·권한·규제 상태가 실제로 바뀔 때만 알립니다.",
        "",
        "투자 조언이 아닌 참고용 원전·Westinghouse 정책 알림입니다.",
    ])
    return "\n".join(lines) + "\n"


def clear_outputs() -> None:
    for path in (ALERT_PATH, TITLE_PATH, ALERTS_JSON_PATH):
        if path.exists():
            path.unlink()


def main() -> int:
    now = now_kst()
    seen = load_seen()
    seen_map = seen.setdefault("seen", {})
    alerts: list[dict] = []

    direct_items = collect_direct_items(now)
    for item in direct_items:
        if item["fingerprint"] in seen_map:
            continue
        alerts.append(item)
        seen_map[item["fingerprint"]] = {
            "title": item["title"],
            "source": item["source"],
            "link": item["link"],
            "first_seen_kst": now.isoformat(timespec="seconds"),
        }

    stake_items = collect_westinghouse_stake_items(now)
    latest_stake = stake_items[0] if stake_items else None
    previous_state = seen.get("westinghouse_issue_state") or {}
    if latest_stake:
        previous_published = str(previous_state.get("published_utc") or "")
        current_published = str(latest_stake.get("published_utc") or "")
        is_newer = not previous_published or current_published > previous_published
        changed = latest_stake["state_key"] != previous_state.get("state_key")
        if is_newer and changed:
            alerts.append(latest_stake)
            seen["westinghouse_issue_state"] = {
                "state_key": latest_stake["state_key"],
                "status": latest_stake["status"],
                "title": latest_stake["title"],
                "source": latest_stake["source"],
                "link": latest_stake["link"],
                "published_utc": latest_stake["published_utc"],
                "first_seen_kst": now.isoformat(timespec="seconds"),
            }

    if not alerts:
        clear_outputs()
        print(f"nuclear_policy_alerts=0 direct={len(direct_items)} westinghouse_material={len(stake_items)}")
        return 0

    OUT_DIR.mkdir(exist_ok=True)
    report = render(alerts, now)
    ALERT_PATH.write_text(report, encoding="utf-8")
    ALERTS_JSON_PATH.write_text(json.dumps(alerts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    TITLE_PATH.write_text("원전·Westinghouse 웹감시: 물질적 상태 변화\n", encoding="utf-8")
    save_seen(seen, now)
    print(f"nuclear_policy_alerts={len(alerts)} westinghouse_material={len(stake_items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
