#!/usr/bin/env python3
"""KHS high-impact nuclear / Westinghouse policy watch."""

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

KST = ZoneInfo("Asia/Seoul")
UTC = dt.timezone.utc
OUT_DIR = Path("out")
DATA_DIR = Path("data")
SEEN_PATH = DATA_DIR / "khs_nuclear_policy_seen.json"
ALERT_PATH = OUT_DIR / "khs_nuclear_policy_alert.md"
TITLE_PATH = OUT_DIR / "khs_nuclear_policy_title.txt"
ALERTS_JSON_PATH = OUT_DIR / "khs_nuclear_policy_alerts.json"
MAX_SOURCE_AGE_HOURS = int(os.getenv("KHS_NUCLEAR_MAX_AGE_HOURS", "72"))
DIRECT_FINGERPRINT_VERSION = "ko-v2"

SOURCES = [
    {"name": "Westinghouse strategic partnership", "url": "https://westinghousenuclear.com/strategic-partnership/press-releases/brookfield/"},
    {"name": "DOE Nuclear Energy", "url": "https://www.energy.gov/ne/articles/9-key-takeaways-president-trumps-executive-orders-nuclear-energy"},
]
WEC_RSS_QUERIES = [
    ("웨스팅하우스 지분·한국 뉴스", "웨스팅하우스 지분 인수 한국전력 산업통상부 한수원 브룩필드 카메코 when:14d"),
    ("웨스팅하우스 지분·해외 뉴스", "Westinghouse stake Korea KEPCO KHNP Brookfield Cameco when:14d"),
    ("웨스팅하우스 지분·공식입장 추적", "웨스팅하우스 산업통상부 한국전력 공식 발표 when:30d"),
]
NUCLEAR_TERMS = [
    "westinghouse", "ap1000", "ap300", "nuclear reactor", "nuclear reactors", "new reactors", "nuclear power", "nuclear energy",
    "uranium", "nuclear fuel", "loan guarantee", "low-cost loans", "strategic partnership", "nuclear regulatory commission", "nrc",
    "data center", "data centers", "artificial intelligence", "ai race",
]
HIGH_IMPACT_TERMS = [
    "$80 billion", "80 billion", "$17.5 billion", "17.5 billion", "10 new reactors", "10 nuclear reactors", "at least $80 billion",
    "executive order", "president trump", "department of energy", "secretary of energy", "commerce", "u.s. government",
]
WEC_CORE = ["westinghouse", "웨스팅하우스", "wec"]
WEC_TRANSACTION = [
    "지분", "인수", "투자", "공동 인수", "공동인수", "출자", "주주", "경영 참여", "stake", "equity", "acquisition", "invest",
    "shareholder", "buyout", "ipo", "상장", "기업공개", "brookfield", "브룩필드", "cameco", "카메코", "kepco", "한국전력", "한전",
    "khnp", "한수원", "산업통상부", "산업부", "미국 정부", "u.s. government", "ap1000", "지식재산", "입찰 제한",
]
WEC_MATERIAL = [
    "공식 발표", "공식 확인", "공식 부인", "사실과 다르", "부인", "합의", "계약", "loi", "mou", "양해각서", "실사", "due diligence",
    "협상 개시", "협상 착수", "본협상", "우선협상", "term sheet", "텀시트", "취득", "매각", "지분율", "인수가격", "매각가격",
    "출자액", "투자금", "경영권", "이사회", "의결권", "voting rights", "cfius", "nrc", "승인", "인가", "사업권", "설계권",
    "조달권", "시공권", "입찰 제한", "지식재산권", "상장 신청", "ipo filing", "ipo 신청",
]
WEC_COMMENTARY_OR_MARKET = [
    "고차방정식", "열쇠", "주식인가", "사업인가", "전망", "분석", "진단", "수혜", "들썩", "특징주", "상승세", "주목", "기대",
    "논란", "평가", "급등", "급락", "상승", "하락", "마감", "장중", "주가", "투자심리", "테마", "관련주",
]
WEC_STRONG_EXECUTION = [
    "공식", "합의", "계약", "loi", "mou", "양해각서", "실사", "due diligence", "협상 개시", "협상 착수", "본협상", "우선협상",
    "term sheet", "텀시트", "취득", "매각", "지분율", "인수가격", "매각가격", "출자액", "투자금", "cfius", "nrc", "승인", "인가",
    "사업권", "설계권", "조달권", "시공권", "지식재산권",
]
WEC_OFFICIAL_OUTLETS = ["산업통상부", "정책브리핑", "한국전력", "한수원", "kepco", "khnp", "westinghouse", "cameco", "brookfield"]
SOURCE_LABELS = {
    "Westinghouse strategic partnership": "Westinghouse 공식 전략 파트너십 발표",
    "DOE Nuclear Energy": "미국 에너지부 원전정책 공식자료",
}
TERM_LABELS = {
    "$80 billion": "최소 800억 달러 규모", "80 billion": "800억 달러", "$17.5 billion": "175억 달러", "17.5 billion": "175억 달러",
    "10 new reactors": "신규 원전 10기", "10 nuclear reactors": "원전 10기", "at least $80 billion": "최소 800억 달러",
    "executive order": "행정명령", "president trump": "트럼프 대통령", "department of energy": "미국 에너지부",
    "secretary of energy": "미국 에너지부 장관", "commerce": "상무부", "u.s. government": "미국 정부", "westinghouse": "Westinghouse",
    "ap1000": "AP1000", "ap300": "AP300", "nuclear reactor": "원자로", "nuclear reactors": "원자로", "new reactors": "신규 원전",
    "nuclear power": "원전", "nuclear energy": "원자력 에너지", "uranium": "우라늄", "nuclear fuel": "핵연료", "loan guarantee": "대출보증",
    "low-cost loans": "저리 대출", "strategic partnership": "전략적 파트너십", "nuclear regulatory commission": "미 원자력규제위원회",
    "nrc": "미 원자력규제위원회", "data center": "데이터센터", "data centers": "데이터센터", "artificial intelligence": "인공지능", "ai race": "AI 경쟁",
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
        for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
            try:
                return dt.datetime.strptime(match.group(0), fmt).replace(tzinfo=KST)
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
        if published and (now - published).total_seconds() / 3600 > MAX_SOURCE_AGE_HOURS:
            continue
        haystack = f"{title} {body}".lower()
        matched = [term for term in NUCLEAR_TERMS + HIGH_IMPACT_TERMS if term.lower() in haystack]
        if not any(term in matched for term in NUCLEAR_TERMS) or not any(term in matched for term in HIGH_IMPACT_TERMS):
            continue
        fingerprint = hashlib.sha256(f"{DIRECT_FINGERPRINT_VERSION}|{source['name']}|{title}|{source['url']}".encode("utf-8")).hexdigest()[:16]
        items.append({
            "kind": "direct_official", "fingerprint": fingerprint, "source": source["name"], "title": title, "link": source["url"],
            "published_kst": published.isoformat() if published else "확인 불가", "matched": sorted(set(matched))[:12],
        })
    return items

def _google_news_url(query: str) -> str:
    return "https://news.google.com/rss/search?q=" + urllib.parse.quote_plus(query) + "&hl=ko&gl=KR&ceid=KR:ko"

def _clean_rss_title(title: str) -> str:
    return re.sub(r"\s+-\s+[^-]{2,80}$", "", clean_text(title)).strip()

def _is_official_outlet(outlet: str) -> bool:
    low = (outlet or "").lower()
    return any(term.lower() in low for term in WEC_OFFICIAL_OUTLETS)

def _has_numeric_terms(title: str) -> bool:
    return bool(re.search(r"(?:\$|달러|원|억원|조원|%|퍼센트).*?\d|\d[\d,.]*\s*(?:억달러|달러|억원|조원|%)", title.lower()))

def _is_material_westinghouse(title: str, outlet: str = "") -> bool:
    low = title.lower()
    if not (any(term in low for term in WEC_CORE) and any(term in low for term in WEC_TRANSACTION)):
        return False
    if _is_official_outlet(outlet):
        return True
    if any(term in low for term in WEC_COMMENTARY_OR_MARKET):
        return any(term in low for term in WEC_STRONG_EXECUTION)
    return any(term in low for term in WEC_MATERIAL) or _has_numeric_terms(title)

def _self_test_material_filter() -> None:
    if _is_material_westinghouse("[특징주] 한전, 웨스팅하우스 지분투자설에 6%대 급등 마감", "연합뉴스"):
        raise RuntimeError("Westinghouse market-reaction filter regression")
    if _is_material_westinghouse("한전, 웨스팅하우스 지분확보설에 장중 7%대 급등", "연합뉴스"):
        raise RuntimeError("Westinghouse intraday-price filter regression")
    if not _is_material_westinghouse("한국전력, 웨스팅하우스 지분 인수 실사 착수…지분율 10% 협상", "연합뉴스"):
        raise RuntimeError("Westinghouse execution-state filter regression")
    if not _is_material_westinghouse("웨스팅하우스 지분 공동인수 보도는 사실과 다르다", "산업통상부"):
        raise RuntimeError("Westinghouse official-state filter regression")

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
    found = re.findall(r"\d[\d,.]*(?:\s*)?(?:%|퍼센트|억달러|달러|억원|조원|원)", title, flags=re.I)
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
        try:
            root = ET.fromstring(fetch_text(_google_news_url(query)))
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
            if (now.astimezone(UTC) - published).total_seconds() / 86400 > 30:
                continue
            story_key = f"{title.lower()}|{outlet.lower()}"
            if story_key in seen_story:
                continue
            seen_story.add(story_key)
            rows.append({
                "kind": "westinghouse_stake", "source": outlet or source_name, "title": title[:500], "link": link,
                "published_kst": published.astimezone(KST).isoformat(timespec="seconds"), "published_utc": published.isoformat(timespec="seconds"),
                "state_key": _wec_state_key(title, outlet), "status": _wec_status(title, outlet), "matched": ["westinghouse", "stake", "korea"],
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

def _short_source_time(value: str) -> str:
    try:
        parsed = dt.datetime.fromisoformat(str(value)).astimezone(KST)
        return parsed.strftime("%m-%d %H:%M KST")
    except Exception:
        return str(value or "확인 불가")

def _render_direct(item: dict, idx: int, now: dt.datetime) -> list[str]:
    ko_title = "미국, Westinghouse AP1000 원전·AI 전력 지원"
    if "80" in " ".join(item["matched"]):
        ko_title = "미국, Westinghouse 원전 건설 대형 지원"
    source_label = SOURCE_LABELS.get(item["source"], item["source"])
    evidence = ", ".join(dict.fromkeys(TERM_LABELS.get(term, term) for term in item["matched"]))
    compact_evidence = concise_text(evidence, fallback="AP1000·AI 전력·원전 지원 신호 확인")
    return [
        f"{idx}. [확정] {ko_title}",
        f"📌 판정: 공식자료 기반 확정",
        f"▶ 변화: {compact_evidence}",
        "💰 의미: 미국 원전·AI 전력 투자 확대는 AP1000·원전기기·전력 인프라 수요에 직접 연결됩니다.",
        "⏭ 다음: 후속 공시 · DOE/NRC 일정 · 실제 발주",
        f"- 출처: [{source_label}]({item['link']}) · {_short_source_time(item['published_kst'])}",
        "",
    ]

def _render_westinghouse_stake(item: dict, idx: int, now: dt.datetime) -> list[str]:
    status = item.get("status") or "추가 확인 필요"
    unconfirmed = status not in {"계약·합의 단계", "지분 거래 확정 신호", "공식 부인·정정"}
    verdict = "보도·검토 단계 — 공식 거래조건 미확정" if unconfirmed else status
    return [
        f"{idx}. [{'보도' if unconfirmed else '상태 변화'}] 한국의 Westinghouse 지분 참여",
        f"📌 판정: {verdict}",
        f"▶ 변화: {item['title']}",
        "💰 의미: 지분과 실제 사업권이 함께 확보될 때 AP1000 사업개발·조달까지 역할 확대가 가능합니다.",
        "⚠️ 미확정·병목: 지분율 · 가격 · 경영참여권 · 사업권 · CFIUS/NRC",
        "⏭ 다음: 공식 발표 → LOI/MOU → 실사 → 지분율·가격 → 규제 승인",
        f"- 출처: [{item['source']}]({item['link']}) · {_short_source_time(item['published_kst'])}",
        "",
    ]

def render(alerts: list[dict], now: dt.datetime) -> str:
    lines = [f"조회 {now:%m-%d %H:%M KST}", ""]
    for idx, item in enumerate(alerts, 1):
        lines.extend(_render_westinghouse_stake(item, idx, now) if item.get("kind") == "westinghouse_stake" else _render_direct(item, idx, now))
    return "\n".join(lines).rstrip() + "\n"

def clear_outputs() -> None:
    for path in (ALERT_PATH, TITLE_PATH, ALERTS_JSON_PATH):
        if path.exists():
            path.unlink()

def main() -> int:
    _self_test_material_filter()
    now = now_kst()
    seen = load_seen()
    seen_map = seen.setdefault("seen", {})
    alerts: list[dict] = []
    direct_items = collect_direct_items(now)
    for item in direct_items:
        if item["fingerprint"] in seen_map:
            continue
        alerts.append(item)
        seen_map[item["fingerprint"]] = {"title": item["title"], "source": item["source"], "link": item["link"], "first_seen_kst": now.isoformat(timespec="seconds")}
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
                "state_key": latest_stake["state_key"], "status": latest_stake["status"], "title": latest_stake["title"], "source": latest_stake["source"],
                "link": latest_stake["link"], "published_utc": latest_stake["published_utc"], "first_seen_kst": now.isoformat(timespec="seconds"),
            }
    if not alerts:
        clear_outputs()
        print(f"nuclear_policy_alerts=0 direct={len(direct_items)} westinghouse_material={len(stake_items)}")
        return 0
    OUT_DIR.mkdir(exist_ok=True)
    ALERT_PATH.write_text(render(alerts, now), encoding="utf-8")
    ALERTS_JSON_PATH.write_text(json.dumps(alerts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    TITLE_PATH.write_text("🚨 원전·Westinghouse 웹감시\n", encoding="utf-8")
    save_seen(seen, now)
    print(f"nuclear_policy_alerts={len(alerts)} westinghouse_material={len(stake_items)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
