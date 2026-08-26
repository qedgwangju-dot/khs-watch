from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import requests

STATE_PATH = Path("data/korea_energy_mix_state.json")
OUT_DIR = Path("out")
KST = timezone(timedelta(hours=9))
MAX_AGE_HOURS = int(os.getenv("KOREA_ENERGY_MIX_MAX_AGE_HOURS", "96"))

# 전기본은 세부 전원 키워드가 없어도 전부 잡는다.
RSS_SOURCES = (
    {
        "name": "기후에너지환경부 공식",
        "official": True,
        "url": (
            "https://news.google.com/rss/search?q=site%3Amcee.go.kr+"
            "%28%22%EC%A0%9C12%EC%B0%A8+%EC%A0%84%EB%A0%A5%EC%88%98%EA%B8%89%EA%B8%B0%EB%B3%B8%EA%B3%84%ED%9A%8D%22+OR+"
            "%2212%EC%B0%A8+%EC%A0%84%EA%B8%B0%EB%B3%B8%22+OR+"
            "%22%EC%A0%84%EB%A0%A5%EC%88%98%EA%B8%89%EA%B8%B0%EB%B3%B8%EA%B3%84%ED%9A%8D%22+OR+"
            "%22%EC%A0%84%EA%B8%B0%EB%B3%B8%22%29+when%3A30d"
            "&hl=ko&gl=KR&ceid=KR%3Ako"
        ),
    },
    {
        "name": "국내 주요 언론",
        "official": False,
        "url": (
            "https://news.google.com/rss/search?q=%28%22%EC%A0%9C12%EC%B0%A8+%EC%A0%84%EB%A0%A5%EC%88%98%EA%B8%89%EA%B8%B0%EB%B3%B8%EA%B3%84%ED%9A%8D%22+OR+"
            "%2212%EC%B0%A8+%EC%A0%84%EA%B8%B0%EB%B3%B8%22+OR+"
            "%22%EC%A0%84%EB%A0%A5%EC%88%98%EA%B8%89%EA%B8%B0%EB%B3%B8%EA%B3%84%ED%9A%8D%22+OR+"
            "%22%EC%A0%84%EA%B8%B0%EB%B3%B8%22%29+when%3A7d"
            "&hl=ko&gl=KR&ceid=KR%3Ako"
        ),
    },
)

TRUSTED_MEDIA = (
    "조선일보", "연합뉴스", "한국경제", "매일경제", "서울경제", "이데일리",
    "전자신문", "머니투데이", "뉴시스", "헤럴드경제", "파이낸셜뉴스", "뉴스1",
)

PLAN_TERMS = (
    "제12차 전력수급기본계획", "12차 전기본", "전력수급기본계획", "전기본",
)
ENERGY_TERMS = (
    "재생에너지", "태양광", "해상풍력", "육상풍력", "풍력", "220gw", "236gw",
    "원전", "원자력", "신규 원전", "에너지믹스", "전력수요", "석탄", "lng", "ess",
)


def norm(value: str | None) -> str:
    return " ".join((value or "").split())


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def parse_date(value: str) -> datetime | None:
    value = norm(value)
    if not value:
        return None
    try:
        result = parsedate_to_datetime(value)
        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)
        return result
    except (TypeError, ValueError, OverflowError):
        return None


def korean_date(value: str) -> str:
    parsed = parse_date(value)
    if parsed is None:
        return "발표일 확인 필요"
    local = parsed.astimezone(KST)
    return f"{local.year}년 {local.month}월 {local.day}일"


def topic_match(title: str) -> bool:
    """전기본이라는 핵심 식별어가 있으면 세부 전원 키워드가 없어도 알림 대상."""
    lower = norm(title).lower()
    return any(x in lower for x in PLAN_TERMS)


def plan_stage(title: str) -> str:
    lower = norm(title).lower()
    if any(x in lower for x in ("최종 확정", "확정", "의결", "정부안", "최종안")):
        return "확정·의결"
    if any(x in lower for x in ("공청회", "정책토론회", "토론회", "총괄위원회", "분과회의")):
        return "수립·공론화"
    if any(x in lower for x in ("전망", "잠정안", "실무안", "시나리오")):
        return "전망·잠정안"
    if any(x in lower for x in ("발표", "공개", "보도자료", "설명")):
        return "발표·공개"
    return "전기본 관련"


def classify(title: str) -> tuple[str, int]:
    lower = norm(title).lower()
    if any(x in lower for x in ("최종 확정", "확정", "의결", "정부안", "최종안")):
        return "전기본 확정·의결", 7
    if any(x in lower for x in ("원전", "원자력")):
        return "원전·전원믹스", 6
    if any(x in lower for x in ("재생에너지", "태양광", "해상풍력", "육상풍력", "풍력", "220gw", "236gw")):
        return "재생에너지·전원믹스", 6
    if "전력수요" in lower:
        return "전력수요 전망", 5
    if any(x in lower for x in ("공청회", "정책토론회", "토론회", "총괄위원회", "분과회의")):
        return "전기본 수립 절차", 5
    return "전력수급기본계획", 4


def tag_text(item: ET.Element, name: str) -> str:
    for node in item.iter():
        if node.tag.split("}")[-1].lower() == name.lower():
            return norm(node.text)
    return ""


def parse_rss(xml_text: str, source_name: str, official: bool) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    rows: list[dict[str, Any]] = []
    for node in root.iter():
        if node.tag.split("}")[-1].lower() != "item":
            continue
        title = tag_text(node, "title")
        if not topic_match(title):
            continue
        publisher = tag_text(node, "source") or source_name
        if not official and not any(name in publisher for name in TRUSTED_MEDIA):
            continue
        link = tag_text(node, "link")
        guid = tag_text(node, "guid") or link or title
        published = tag_text(node, "pubDate")
        category, stage = classify(title)
        rows.append(
            {
                "id": digest(f"{source_name}|{guid}"),
                "title": title,
                "publisher": publisher,
                "source": source_name,
                "official": official,
                "url": link,
                "published": published,
                "category": category,
                "plan_stage": plan_stage(title),
                "stage": stage,
            }
        )
    return list({str(row["id"]): row for row in rows}.values())


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"seen": []}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"seen": []}
    data.setdefault("seen", [])
    return data


def save_state(rows: list[dict[str, Any]]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    seen = [str(row["id"]) for row in rows][-5000:]
    STATE_PATH.write_text(
        json.dumps({"seen": seen, "updated_at": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def set_output(name: str, value: str) -> None:
    path = os.getenv("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def meaning(category: str) -> str:
    if category == "전기본 확정·의결":
        return "잠정 논의가 정부의 실제 전원·전력망 투자 기준으로 넘어가는 핵심 확정 이벤트"
    if category == "재생에너지·전원믹스":
        return "발전원 구성과 송전망·ESS·태양광·풍력 설비투자 시간표를 직접 바꿈"
    if category == "원전·전원믹스":
        return "신규 원전·계속운전·기저전원 투자와 장기 전력공급 시간표를 바꿈"
    if category == "전력수요 전망":
        return "발전·송전·변전·데이터센터 전원 인가에 필요한 총 설비투자 규모를 바꿈"
    if category == "전기본 수립 절차":
        return "향후 전원별 목표와 전력망 투자가 확정되기 전 정책 방향·일정이 바뀌는 단계"
    return "향후 발전원·전력망 투자 배분과 정책 시간표를 바꿈"


def renewable_220_detail(title: str) -> list[str]:
    """2026-08-26 제12차 전기본 재생에너지 잠정안의 검증된 핵심 수치."""
    lower = norm(title).lower()
    if not any(term in lower for term in ("220gw", "155gw", "61gw")):
        return []
    return [
        "<b>2040년 보급량 순위</b>",
        "1위  태양광  <b>155GW</b>",
        "2위  해상풍력  <b>45GW</b>",
        "3위  육상풍력  <b>16GW</b>",
        "풍력 합계  <b>61GW</b>  = 해상 45 + 육상 16",
        "사업용 재생에너지 합계  <b>220GW</b>",
        "",
        "<b>보급 경로</b>",
        "2025년 <b>33.4GW</b> → 2030년 <b>100GW</b> → 2035년 <b>163GW</b> → 2040년 <b>220GW</b>",
        "",
        "<b>현재 대비 증설 배수</b>",
        "태양광 31 → 155GW  <b>5.0배</b>",
        "해상풍력 0.4 → 45GW  <b>112.5배</b>",
        "육상풍력 2 → 16GW  <b>8.0배</b>",
        "",
        "<b>핵심 해석</b>",
        "절대 보급량 1위는 태양광, 증설 난도·배수 1위는 해상풍력",
        "",
        "<b>정책 단계</b>  제12차 전기본 반영 전 <b>잠정안</b>",
        "<b>주요 병목</b>  전력계통·ESS, 해상풍력 인허가, 지원항만·설치선박 확보",
    ]


def render(rows: list[dict[str, Any]]) -> str:
    lines = ["<b>한국 전기본·전원믹스 새 변화</b>"]
    for idx, row in enumerate(rows[:5], 1):
        status = "공식자료" if row["official"] else "신뢰 보도"
        title_raw = str(row["title"])
        title = html.escape(title_raw)
        publisher = html.escape(str(row["publisher"]))
        category = html.escape(str(row["category"]))
        stage_text = html.escape(str(row.get("plan_stage") or plan_stage(title_raw)))
        url = html.escape(str(row["url"]), quote=True)
        date_text = html.escape(korean_date(str(row["published"])))
        meaning_text = html.escape(meaning(str(row["category"])))
        link_label = "공식 원문 보기" if row["official"] else "기사 원문 보기"
        lines.extend(
            [
                "",
                f"<b>{idx}. {title}</b>",
                "",
                f"<b>핵심 분야</b>  {category}",
                f"<b>전기본 단계</b>  {stage_text}",
                f"<b>확인 상태</b>  {status}",
                f"<b>발표일</b>  {date_text}",
                f"<b>출처</b>  {publisher}",
            ]
        )
        detail = renewable_220_detail(title_raw)
        if detail:
            lines.extend(["", *detail])
        lines.extend(
            [
                "",
                f"<b>투자 의미</b>  {meaning_text}",
                f'<a href="{url}"><b>{link_label}</b></a>',
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def collect() -> tuple[list[dict[str, Any]], list[str]]:
    session = requests.Session()
    session.headers.update({"User-Agent": "khs-korea-energy-mix-watch/1.0", "Accept-Language": "ko-KR,ko;q=0.9"})
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for src in RSS_SOURCES:
        try:
            response = session.get(str(src["url"]), timeout=35)
            response.raise_for_status()
            rows.extend(parse_rss(response.text, str(src["name"]), bool(src["official"])))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{src['name']}: {exc}")
    unique = {str(row["id"]): row for row in rows}
    now = datetime.now(timezone.utc)
    recent = []
    for row in unique.values():
        published = parse_date(str(row["published"]))
        if published is not None and now - published.astimezone(timezone.utc) > timedelta(hours=MAX_AGE_HOURS):
            continue
        recent.append(row)
    recent.sort(key=lambda x: (int(x["stage"]), str(x["published"])), reverse=True)
    return recent, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-notify", action="store_true")
    args = parser.parse_args(argv)

    state = load_state()
    seen = set(str(x) for x in state.get("seen", []))
    rows, errors = collect()
    new_rows = [row for row in rows if str(row["id"]) not in seen]

    all_seen_rows = [{"id": item} for item in sorted(seen | {str(row["id"]) for row in rows})]
    save_state(all_seen_rows)

    notify = rows[:3] if args.force_notify else new_rows[:5]
    if not notify:
        print("한국 전기본·전원믹스 신규 변화 없음")
        if errors:
            print("; ".join(errors))
        set_output("changed", "false")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / "korea_energy_mix_alert.html"
    path.write_text(render(notify), encoding="utf-8")
    set_output("changed", "true")
    set_output("report_path", str(path))
    print(f"alert_rows={len(notify)} errors={len(errors)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
