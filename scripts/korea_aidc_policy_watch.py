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
    category_raw = str(row.get("category", "AIDC 특별법"))
    category = html.escape(category_raw)
    published = kdate(str(row.get("published", "")))
    source = source_link(row)

    stage_summary = {
        "시행령 확정": "시행령·하위규칙이 확정돼 실제 사업 적용 기준이 법적 효력을 갖는 단계",
        "입법예고": "정부 초안이 공개돼 AIDC 인정·전력·인허가 특례의 구체 문구를 확인할 수 있는 단계",
        "하위법령 설계": "특별법 시행 전에 실제 적용 기준을 설계하고 이해관계자 의견을 받는 단계",
        "전력 특례": "AIDC의 계통영향평가·전력공급 규칙이 바뀌어 전원 인가 시간표에 직접 영향을 주는 단계",
        "특구": "비수도권 AIDC 특구의 지정·지원 조건이 구체화되는 단계",
        "AIDC 특별법": "AIDC 산업 지원·인허가·전력 특례의 제도 변화가 확인된 단계",
    }.get(category_raw, "AIDC 사업의 인허가·전력·지원 조건이 바뀌는 단계")

    if category_raw == "시행령 확정":
        change_lines = [
            "• 시행령·하위규칙이 확정되면 <b>누가 AIDC로 인정되는지, 어떤 특례를 실제로 적용받는지</b>가 실행 기준으로 전환",
            "• 확정 조문에서 전력계통영향평가·인허가·특구·지원 범위를 기존 논의안과 대조해야 함",
        ]
        uncertain = "확정 조문에 없는 세부 고시·사업별 전원 인가·실제 특구 지정은 후속 확인"
    elif category_raw == "입법예고":
        change_lines = [
            "• 정부가 시행령 초안을 공개한 단계로, <b>AIDC 인정 기준·전력 특례·인허가 특례의 구체 문구</b>를 처음 숫자로 검증할 수 있음",
            "• 의견수렴 뒤 조문이 바뀔 수 있으므로 입법예고안과 최종 시행령을 구분해야 함",
        ]
        uncertain = "입법예고안은 최종 확정안이 아니며 국무회의·공포 전까지 변경 가능"
    elif category_raw == "전력 특례":
        change_lines = [
            "• 핵심은 데이터센터 기사 자체가 아니라 <b>전력계통영향평가·전력공급·전원 인가 규칙이 실제로 바뀌었는지</b>",
            "• 특례가 커져도 발전·송전·변전 용량이 자동으로 늘어나는 것은 아니므로 물리적 계통 여유를 별도 확인",
        ]
        uncertain = "면제·특례의 정확한 MW 기준과 적용 지역·프로젝트가 확정됐는지 확인 필요"
    elif category_raw == "특구":
        change_lines = [
            "• 비수도권 AIDC 특구 지정 기준과 지원수단이 구체화되면 지역별 사업성·착공 우선순위가 달라질 수 있음",
            "• 특구 지정과 실제 전력 접속·용수·부지 확보는 별도 단계로 추적",
        ]
        uncertain = "특구 후보와 실제 지정, 예산·보조·세제 지원 수준은 각각 분리 확인"
    else:
        change_lines = [
            "• 2027년 3월 10일 특별법 시행을 앞두고 <b>AIDC 인정·신고·인허가·전력·비수도권 특구</b>의 실제 적용기준이 구체화되는 흐름",
            "• 기사 한 건을 추적하는 것이 아니라 같은 주제의 <b>공식자료 → 입법예고 → 확정 → 실제 전원 인가·착공</b> 변화를 이어서 추적",
        ]
        uncertain = "토론회·검토안·언론 전망은 확정 조문과 구분"

    lines = [
        "<b>한국 AIDC 정책·전력 특례 새 변화</b>",
        "",
        "<b>한눈에 보기</b>",
        f"• <b>현재 단계</b>  {category}",
        f"• <b>핵심 의미</b>  {stage_summary}",
        "• <b>실제 돈이 움직이는 시점</b>  시행령·전력 기준 확정 → 프로젝트 전원 인가 → 착공 → 전력기기·UPS·BESS·냉각·건설 발주",
        f"• <b>가장 큰 미확정</b>  {uncertain}",
        "",
        f"<b>{title}</b>",
        f"<b>발표일</b>  {published}",
        f"<b>출처</b>  {source}",
        "",
        "<b>무엇이 달라졌나</b>",
        *change_lines,
        "",
        "<b>확정된 큰 틀</b>",
        "• 특별법은 <b>2027년 3월 10일 시행</b>",
        "• 제도의 핵심 축은 AIDC 인정·신고, 인허가 일괄처리, 전력 특례, 비수도권 특구·지원",
        "",
        "<b>쉽게 풀면</b>",
        "• 중요한 것은 기사 제목이 아니라 <b>데이터센터가 실제로 전력을 받고 착공하는 데 필요한 규칙이 한 단계 전진했는지</b>임",
        "• 같은 내용을 다른 언론이 다시 써도 새 사실이 없으면 재알림하지 않고, 공식화·숫자 변경·단계 상승이 있을 때 다시 알림",
        "",
        "<b>투자 연결</b>",
        "• 규정 완화 자체보다 <b>실제 전원 인가·부지·용수·착공</b>으로 이어지는 프로젝트가 중요",
        "• 이후 변압기·개폐기·케이블·UPS·BESS·냉각·건설 발주가 확인돼야 실적 연결 강도가 올라감",
        "",
        "<b>다음 확인</b>",
        "• 입법예고·시행령 확정 여부",
        "• AIDC 인정 기준과 전력용량 요건",
        "• 전력계통영향평가 특례·면제 범위",
        "• 비수도권 특구 지정과 실제 프로젝트 전원 인가·착공",
    ]
    return "\n".join(lines) + "\n"


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
