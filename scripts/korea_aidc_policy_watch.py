#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import requests

STATE = Path("data/korea_aidc_policy_state.json")
OUT = Path("out")
ALERT = OUT / "korea_aidc_policy_alert.txt"
PENDING = OUT / "korea_aidc_policy_pending_state.json"
STATUS = OUT / "korea_aidc_policy_status.md"
KST = timezone(timedelta(hours=9))
HEADERS = {"User-Agent": "khs-watch-korea-aidc-policy/1.0", "Accept-Language": "ko-KR,ko;q=0.9"}
MAX_AGE_DAYS = 21
BOOTSTRAP_CUTOFF = datetime(2026, 9, 1, tzinfo=KST)

RSS_SOURCES = (
    (
        "과학기술정보통신부",
        True,
        "https://news.google.com/rss/search?q=site%3Amsit.go.kr+%28%22%EC%9D%B8%EA%B3%B5%EC%A7%80%EB%8A%A5+%EB%8D%B0%EC%9D%B4%ED%84%B0%EC%84%BC%ED%84%B0%22+OR+%22AIDC%22%29+%28%22%ED%8A%B9%EB%B3%84%EB%B2%95%22+OR+%22%EC%8B%9C%ED%96%89%EB%A0%B9%22+OR+%22%ED%95%98%EC%9C%84%EB%B2%95%EB%A0%B9%22+OR+%22%EC%A0%84%EB%A0%A5%22+OR+%22%EC%9D%B8%ED%97%88%EA%B0%80%22+OR+%22%ED%8A%B9%EA%B5%AC%22%29+when%3A30d&hl=ko&gl=KR&ceid=KR%3Ako",
    ),
    (
        "대한민국 정책브리핑",
        True,
        "https://news.google.com/rss/search?q=site%3Akorea.kr+%28%22%EC%9D%B8%EA%B3%B5%EC%A7%80%EB%8A%A5+%EB%8D%B0%EC%9D%B4%ED%84%B0%EC%84%BC%ED%84%B0%22+OR+%22AIDC%22%29+%28%22%ED%8A%B9%EB%B3%84%EB%B2%95%22+OR+%22%EC%8B%9C%ED%96%89%EB%A0%B9%22+OR+%22%ED%95%98%EC%9C%84%EB%B2%95%EB%A0%B9%22+OR+%22%EC%A0%84%EB%A0%A5%22+OR+%22%EC%9D%B8%ED%97%88%EA%B0%80%22+OR+%22%ED%8A%B9%EA%B5%AC%22%29+when%3A30d&hl=ko&gl=KR&ceid=KR%3Ako",
    ),
    (
        "국가법령정보센터",
        True,
        "https://news.google.com/rss/search?q=site%3Alaw.go.kr+%22%EC%9D%B8%EA%B3%B5%EC%A7%80%EB%8A%A5+%EB%8D%B0%EC%9D%B4%ED%84%B0%EC%84%BC%ED%84%B0+%EC%82%B0%EC%97%85+%EC%A7%84%ED%9D%A5%EC%97%90+%EA%B4%80%ED%95%9C+%ED%8A%B9%EB%B3%84%EB%B2%95%22+when%3A90d&hl=ko&gl=KR&ceid=KR%3Ako",
    ),
    (
        "국내 주요 언론",
        False,
        "https://news.google.com/rss/search?q=%28%22AIDC+%ED%8A%B9%EB%B3%84%EB%B2%95%22+OR+%22%EC%9D%B8%EA%B3%B5%EC%A7%80%EB%8A%A5+%EB%8D%B0%EC%9D%B4%ED%84%B0%EC%84%BC%ED%84%B0+%ED%8A%B9%EB%B3%84%EB%B2%95%22%29+%28%22%EC%8B%9C%ED%96%89%EB%A0%B9%22+OR+%22%ED%95%98%EC%9C%84%EB%B2%95%EB%A0%B9%22+OR+%22%EC%A0%84%EB%A0%A5+%ED%8A%B9%EB%A1%80%22+OR+%22%EC%9D%B8%ED%97%88%EA%B0%80%22+OR+%22%EC%A0%84%EB%A0%A5%EA%B3%84%ED%86%B5%EC%98%81%ED%96%A5%ED%8F%89%EA%B0%80%22%29+when%3A14d&hl=ko&gl=KR&ceid=KR%3Ako",
    ),
)

TRUSTED_MEDIA = (
    "연합뉴스", "뉴시스", "뉴스1", "머니투데이", "한국경제", "매일경제", "서울경제", "이데일리", "전자신문", "디지털데일리",
)


def norm(v: str | None) -> str:
    return " ".join((v or "").split())


def digest(v: str) -> str:
    return hashlib.sha256(v.encode("utf-8")).hexdigest()


def parse_date(v: str) -> datetime | None:
    v = norm(v)
    if not v:
        return None
    try:
        dt = parsedate_to_datetime(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(v, fmt).replace(tzinfo=KST)
        except ValueError:
            continue
    return None


def kdate(v: str) -> str:
    dt = parse_date(v)
    if not dt:
        return "발표일 확인 필요"
    x = dt.astimezone(KST)
    return f"{x.year}년 {x.month}월 {x.day}일"


def tag_text(item: ET.Element, name: str) -> str:
    for node in item.iter():
        if node.tag.split("}")[-1].lower() == name.lower():
            return norm(node.text)
    return ""


def classify(title: str) -> tuple[str, int]:
    t = norm(title).lower()
    if any(x in t for x in ("공포", "국무회의", "시행령 확정", "시행령 제정")):
        return "시행령 확정", 6
    if "입법예고" in t:
        return "입법예고", 5
    if any(x in t for x in ("하위법령", "시행령", "공개토론회", "토론회")):
        return "하위법령 설계", 4
    if "전력계통영향평가" in t or "전력 특례" in t:
        return "전력 특례", 4
    if "특구" in t:
        return "특구", 3
    return "AIDC 특별법", 2


def event_key(row: dict[str, Any]) -> str:
    t = norm(str(row.get("title", ""))).lower()
    category = str(row.get("category", ""))
    if any(x in t for x in ("하위법령", "시행령", "공개토론회")) and "입법예고" not in t and not any(x in t for x in ("확정", "공포", "국무회의")):
        return "aidc|subordinate-rules-design"
    if "입법예고" in t:
        return "aidc|decree-preannouncement"
    if any(x in t for x in ("시행령 확정", "시행령 제정", "국무회의", "공포")):
        return "aidc|decree-final"
    if "전력계통영향평가" in t or "전력 특례" in t:
        return "aidc|power-special"
    if "특구" in t:
        return "aidc|special-zone"
    cleaned = re.sub(r"\s+-\s+[^-]{1,50}$", "", t)
    cleaned = re.sub(r"[^0-9a-z가-힣]+", " ", cleaned)
    return f"aidc|{category}|{digest(cleaned)[:14]}"


def source_score(row: dict[str, Any]) -> int:
    if row.get("official"):
        return 1000
    p = str(row.get("publisher", ""))
    order = {"연합뉴스": 95, "뉴스1": 92, "뉴시스": 92, "머니투데이": 90, "한국경제": 88, "매일경제": 88, "서울경제": 86, "이데일리": 85, "전자신문": 85, "디지털데일리": 84}
    return max((score for name, score in order.items() if name in p), default=0)


def event_level(row: dict[str, Any]) -> int:
    base = int(row.get("stage", 0))
    return base * 10 + (5 if row.get("official") else 0)


def parse_rss(xml_text: str, source: str, official: bool) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    out: list[dict[str, Any]] = []
    for node in root.iter():
        if node.tag.split("}")[-1].lower() != "item":
            continue
        title = tag_text(node, "title")
        if not ("aidc" in title.lower() or "인공지능 데이터센터" in title):
            continue
        publisher = tag_text(node, "source") or source
        if not official and not any(x in publisher for x in TRUSTED_MEDIA):
            continue
        link = tag_text(node, "link")
        guid = tag_text(node, "guid") or link or title
        pub = tag_text(node, "pubDate")
        category, stage = classify(title)
        out.append({
            "id": digest(f"{source}|{guid}"),
            "title": title,
            "publisher": publisher,
            "source": source,
            "official": official,
            "url": link,
            "published": pub,
            "category": category,
            "stage": stage,
        })
    return list({x["id"]: x for x in out}.values())


def collapse(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(event_key(row), []).append(row)
    result: list[dict[str, Any]] = []
    for key, members in groups.items():
        best = max(members, key=lambda r: (event_level(r), source_score(r), str(r.get("published", "")))).copy()
        best["event_key"] = key
        best["members"] = members
        result.append(best)
    result.sort(key=lambda r: (int(r.get("stage", 0)), parse_date(str(r.get("published", ""))) or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
    return result


def load_state() -> dict[str, Any]:
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    data.setdefault("initialized", False)
    data.setdefault("seen_events", {})
    return data


def source_link(row: dict[str, Any]) -> str:
    label = html.escape(str(row.get("publisher") or row.get("source") or "원문"))
    url = html.escape(str(row.get("url") or ""), quote=True)
    return f'<a href="{url}"><b>{label}</b></a>' if url else label


def render(row: dict[str, Any]) -> str:
    title = html.escape(norm(str(row.get("title", ""))))
    category = html.escape(str(row.get("category", "AIDC 특별법")))
    return "\n".join([
        "<b>한국 AIDC 정책·전력 특례 새 변화</b>",
        "",
        f"<b>{title}</b>",
        f"<b>단계</b>  {category}",
        f"<b>발표일</b>  {kdate(str(row.get('published', '')))}",
        f"<b>출처</b>  {source_link(row)}",
        "",
        "<b>무엇이 달라졌나</b>",
        "• 2027년 3월 10일 AIDC 특별법 시행을 앞두고 <b>시행령·하위법령의 실제 적용기준을 정하는 단계</b>로 들어감",
        "• 이번 논의 대상은 <b>AIDC 인정 기준, 구축·운영 신고, 인허가 일괄처리, 시설 특례, 전력 특례, 비수도권 특구</b>",
        "• 토론회에서는 구체 조문 초안을 확정·공개한 것이 아니라 위임사항과 검토 방향에 대한 의견수렴을 진행한 단계",
        "",
        "<b>이미 법률에서 확정된 기준</b>",
        "• 특별법은 2026년 6월 9일 공포, <b>2027년 3월 10일 시행</b>",
        "• 인허가 일괄처리: 전력계통영향평가 등 <b>150일</b>, 에너지사용계획·교통/경관 등 <b>90일</b>, 건축허가 등 <b>40일</b>; 특별사유 시 1회 최대 30일 연장 가능",
        "• 비수도권 AIDC의 신축·확장·전환은 <b>전력계통영향평가 면제 대상</b>이 될 수 있고, 면제 가능한 전력용량은 시행령에서 정함",
        "• 재생에너지전기공급사업자·저장판매사업자는 전력시장을 거치지 않고 AIDC에 직접 전력 공급 가능",
        "• 국가·지자체는 전력·용수 시설 우선 설치와 융자·투자·보조 지원 가능",
        "",
        "<b>이번 하위법령에서 진짜 중요한 미확정 숫자</b>",
        "• 어떤 시설을 AIDC로 인정할지: 설비·규모 기준",
        "• 비수도권 전력계통영향평가 면제 한도: <b>몇 MW까지인지</b>",
        "• 건축·산업단지·항만 특례의 구체 적용 범위",
        "• 비수도권 AIDC 특구 지정 기준·절차·지원 수준",
        "",
        "<b>쉽게 풀면</b>",
        "AIDC 특별법 자체는 이미 만들어졌고, 지금은 <b>누가 혜택을 받고 얼마나 빨리 전력·인허가를 통과할 수 있는지</b>를 시행령으로 정하는 구간. 특히 비수도권의 전력계통영향평가 면제 MW가 크게 잡히면 지역 AIDC의 착공·전원 인가 시간표가 앞당겨질 수 있음.",
        "",
        "<b>투자 의미</b>",
        "• 수혜의 핵심은 단순 데이터센터 테마가 아니라 <b>실제 착공·전원 인가가 빨라지는 프로젝트</b>",
        "• 전력기기·변압기·개폐기·케이블·UPS·BESS·냉각·건설 발주는 시행령 기준 확정 뒤 구체화될 가능성이 큼",
        "• 다만 전력계통영향평가를 면제해도 <b>실제 발전·송전·변전 용량이 생기는 것은 아니므로 물리적 전력 병목은 별도</b>",
        "",
        "<b>다음 확인</b>",
        "입법예고 → 시행령 조문 → AIDC 인정 기준 → 전력계통영향평가 면제 MW → 특구 기준 → 실제 프로젝트 전원 인가·착공 순으로 추적",
    ]) + "\n"


def main() -> int:
    OUT.mkdir(exist_ok=True)
    for p in (ALERT, PENDING, STATUS):
        if p.exists():
            p.unlink()
    state = load_state()
    now = datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    session = requests.Session()
    session.headers.update(HEADERS)
    for source, official, url in RSS_SOURCES:
        try:
            r = session.get(url, timeout=30)
            r.raise_for_status()
            rows.extend(parse_rss(r.text, source, official))
        except Exception as exc:
            errors.append(f"{source}: {type(exc).__name__}")
    recent = []
    for row in rows:
        dt = parse_date(str(row.get("published", "")))
        if dt and now - dt.astimezone(timezone.utc) > timedelta(days=MAX_AGE_DAYS):
            continue
        recent.append(row)
    events = collapse(recent)
    seen = {str(k): int(v) for k, v in dict(state.get("seen_events", {})).items()}
    notify: list[dict[str, Any]] = []
    for row in events:
        key = str(row["event_key"])
        cur = event_level(row)
        prev = int(seen.get(key, 0))
        pub = parse_date(str(row.get("published", "")))
        if state.get("initialized"):
            if cur > prev:
                notify.append(row)
        else:
            if pub and pub.astimezone(KST) >= BOOTSTRAP_CUTOFF:
                notify.append(row)
        seen[key] = max(prev, cur)
    # 최초 도입 시 최근 사건이 여러 언론사/공지로 겹쳐도 가장 중요한 1건만 백필 알림.
    if not state.get("initialized") and notify:
        notify = sorted(notify, key=lambda r: (event_level(r), source_score(r), parse_date(str(r.get("published", ""))) or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)[:1]
    pending = {
        "initialized": True,
        "seen_events": seen,
        "updated_at": now.isoformat(),
        "source_errors": errors,
    }
    PENDING.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if notify:
        ALERT.write_text(render(notify[0]), encoding="utf-8")
    STATUS.write_text(
        "# 한국 AIDC 특별법 감시\n\n"
        f"- 감지 이벤트: **{len(events)}건**\n"
        f"- 신규 알림: **{'예' if notify else '아니오'}**\n"
        f"- 최신 단계: **{notify[0]['category'] if notify else (events[0]['category'] if events else '확인 불가')}**\n"
        f"- 원천 오류: **{len(errors)}곳**\n",
        encoding="utf-8",
    )
    print(f"aidc_events={len(events)} notify={bool(notify)} errors={len(errors)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
