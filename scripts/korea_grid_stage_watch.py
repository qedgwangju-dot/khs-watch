from __future__ import annotations

import argparse
import html
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

STATE_PATH = Path("data/korea_grid_stage_state.json")
OUT_DIR = Path("out")
KST = timezone(timedelta(hours=9))

KEPCO_OVERVIEW_URL = (
    "https://www.kepco.co.kr/home/disclosure/transdisclosure/transstatus/transinfo.do"
)
STAGE_PAGES = (
    (
        "계획확정",
        1,
        "https://www.kepco.co.kr/home/disclosure/transdisclosure/transstatus/plantoapprove/boardList.do",
    ),
    (
        "사업승인",
        2,
        "https://www.kepco.co.kr/home/disclosure/transdisclosure/transstatus/approvetostart/boardList.do",
    ),
    (
        "공사착수",
        3,
        "https://www.kepco.co.kr/home/disclosure/transdisclosure/transstatus/starttocomplete/boardList.do",
    ),
)
COUNT_LABELS = (
    ("계획확정", "계획확정 - 사업승인전"),
    ("사업승인", "사업승인 - 공사착수전"),
    ("공사착수", "공사착수 - 사업완료전"),
    ("사업완료", "사업완료 - 준공후 1년"),
)


def normalize(value: str | None) -> str:
    return " ".join((value or "").split())


def project_key(name: str) -> str:
    text = normalize(name).lower()
    text = re.sub(r"\s+", "", text)
    text = text.replace("t/l", "송전선로").replace("s/s", "변전소")
    return text


def parse_overview_counts(html_text: str) -> dict[str, int]:
    soup = BeautifulSoup(html_text, "html.parser")
    text = " ".join(soup.get_text(" ", strip=True).split())
    counts: dict[str, int] = {}
    for key, label in COUNT_LABELS:
        patterns = (
            rf"(\d[\d,]*)\s*건\s*{re.escape(label)}",
            rf"{re.escape(label)}.*?(\d[\d,]*)\s*건",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                counts[key] = int(match.group(1).replace(",", ""))
                break
    return counts


def parse_stage_rows(html_text: str, stage: str, stage_order: int, base_url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html_text, "html.parser")
    rows: list[dict[str, Any]] = []
    for tr in soup.find_all("tr"):
        cells = [normalize(td.get_text(" ", strip=True)) for td in tr.find_all(["td", "th"])]
        if len(cells) < 5 or not re.fullmatch(r"\d+", cells[0]):
            continue
        name, equipment, hq, office = cells[1:5]
        if not name:
            continue
        anchor = tr.find("a", href=True)
        detail_url = urljoin(base_url, str(anchor.get("href"))) if anchor else base_url
        rows.append(
            {
                "name": name,
                "key": project_key(name),
                "equipment": equipment,
                "hq": hq,
                "office": office,
                "stage": stage,
                "stage_order": stage_order,
                "url": detail_url,
            }
        )
    return rows


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"initialized": False, "counts": {}, "projects": {}}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"initialized": False, "counts": {}, "projects": {}}
    data.setdefault("initialized", True)
    data.setdefault("counts", {})
    data.setdefault("projects", {})
    return data


def save_state(counts: dict[str, int], projects: dict[str, dict[str, Any]]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(
            {
                "initialized": True,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "counts": counts,
                "projects": projects,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def investment_axis(stage: str) -> str:
    if stage == "공사착수":
        return "시간표·돈 버는 능력"
    if stage == "사업승인":
        return "시간표·할인율"
    if stage == "사업완료":
        return "시간표·돈 버는 능력"
    return "시간표"


def investment_text(stage: str, equipment: str) -> str:
    equipment = normalize(equipment)
    if stage == "공사착수":
        if "지중" in equipment or "전력구" in equipment:
            return "정책·인허가가 실제 지중 케이블·접속재·전력구 토목 발주와 공사 단계로 이동"
        if "변전" in equipment:
            return "정책·인허가가 변압기·GIS·차단기·보호계전 등 실제 변전 설비투자 단계로 이동"
        if "가공" in equipment or "송전" in equipment:
            return "정책·인허가가 철탑·가공선·애자·금구류 등 실제 송전 공사 단계로 이동"
        return "정책·인허가가 실제 설비투자·공사 단계로 이동"
    if stage == "사업승인":
        return "실시계획 승인을 거쳐 착공 가능성이 높아져 발주 시간표가 한 단계 구체화"
    if stage == "사업완료":
        return "공사가 완료돼 전원 인가·운영 개시와 관련 매출 인식 시점에 가까워짐"
    return "전력수급기본계획 반영 이후 실시계획 승인 절차가 시작되는 초기 시간표 변화"


def compare_state(
    old_counts: dict[str, Any],
    old_projects: dict[str, dict[str, Any]],
    new_counts: dict[str, int],
    new_projects: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    count_changes = []
    for stage, new_value in new_counts.items():
        old_value = old_counts.get(stage)
        if isinstance(old_value, int) and old_value != new_value:
            count_changes.append((stage, old_value, new_value))
    if count_changes:
        events.append({"type": "count_change", "changes": count_changes})

    for key, current in new_projects.items():
        previous = old_projects.get(key)
        if previous is None:
            events.append({"type": "stage_entry", "current": current})
            continue
        old_stage = str(previous.get("stage", ""))
        new_stage = str(current.get("stage", ""))
        if old_stage and old_stage != new_stage:
            events.append({"type": "stage_change", "previous": previous, "current": current})
            continue
        if normalize(str(previous.get("equipment", ""))) != normalize(str(current.get("equipment", ""))):
            events.append({"type": "equipment_change", "previous": previous, "current": current})

    return events


def render_report(events: list[dict[str, Any]], counts: dict[str, int]) -> str:
    now_kst = datetime.now(timezone.utc).astimezone(KST)
    lines = [
        "<b>전력망 사업단계 새 공식 변화</b>",
        "<i>특정 기사 추적이 아니라 한국전력 송변전 사업현황의 실제 단계·물량 변화 감지</i>",
    ]

    count_event = next((e for e in events if e.get("type") == "count_change"), None)
    if count_event:
        lines.extend(["", "<b>무엇이 달라졌나</b>"])
        for stage, old_value, new_value in count_event["changes"]:
            delta = new_value - old_value
            sign = "+" if delta > 0 else ""
            lines.append(f"• {stage}: <b>{old_value}건 → {new_value}건 ({sign}{delta})</b>")

    detailed = [e for e in events if e.get("type") != "count_change"]
    for event in detailed[:8]:
        current = event["current"]
        event_type = event["type"]
        name = html.escape(str(current.get("name", "")))
        stage = str(current.get("stage", ""))
        equipment = str(current.get("equipment", ""))
        url = html.escape(str(current.get("url") or KEPCO_OVERVIEW_URL), quote=True)
        lines.extend(["", f"<b>{name}</b>", "", "<b>무엇이 달라졌나</b>"])
        if event_type == "stage_change":
            previous = event["previous"]
            lines.append(f"• <b>{html.escape(str(previous.get('stage', '')))} → {html.escape(stage)}</b> 단계 이동")
        elif event_type == "equipment_change":
            previous = event["previous"]
            lines.append(
                f"• 설비종류 <b>{html.escape(str(previous.get('equipment', '')))} → {html.escape(equipment)}</b> 변경"
            )
        else:
            lines.append(f"• <b>{html.escape(stage)}</b> 단계 최신 목록에 새로 진입")

        lines.extend(
            [
                "",
                "<b>현재 판정</b>",
                f"• {html.escape(stage)} · {html.escape(equipment or '설비종류 확인 필요')}",
                f"• 바뀐 축: <b>{html.escape(investment_axis(stage))}</b>",
                "",
                "<b>투자 의미</b>",
                f"• {html.escape(investment_text(stage, equipment))}",
                "",
                "<b>다음 확인</b>",
                "• 상세 사업비·노선 km·발주 규격·낙찰사·계약금액·공사기간·전원 인가 시점",
                "",
                "<b>확정 정보</b>",
                f"• 담당: {html.escape(str(current.get('hq', '')))} / {html.escape(str(current.get('office', '')))}",
                f'• 출처: <a href="{url}"><b>한국전력 공식 원문</b></a>',
            ]
        )

    lines.extend(
        [
            "",
            "<b>단계별 현재 건수</b>",
            "• " + " · ".join(f"{stage} {value}건" for stage, value in counts.items()),
            f"• 확인 시각: {now_kst:%Y년 %m월 %d일 %H:%M} KST",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def github_output(key: str, value: str) -> None:
    path = os.getenv("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"{key}={value}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-notify", action="store_true")
    args = parser.parse_args(argv)

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "khs-watch-kepco-grid-stage/1.0",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
        }
    )

    overview = session.get(KEPCO_OVERVIEW_URL, timeout=30)
    overview.raise_for_status()
    counts = parse_overview_counts(overview.text)
    if len(counts) < 4:
        raise RuntimeError(f"한국전력 단계별 건수 파싱 실패: {counts}")

    projects: dict[str, dict[str, Any]] = {}
    for stage, order, url in STAGE_PAGES:
        response = session.get(url, timeout=30)
        response.raise_for_status()
        for row in parse_stage_rows(response.text, stage, order, response.url):
            projects[row["key"]] = row

    state = load_state()
    events = compare_state(state.get("counts", {}), state.get("projects", {}), counts, projects)
    initialized = bool(state.get("initialized"))
    save_state(counts, projects)

    if not initialized and not args.force_notify:
        print("KEPCO 송변전 사업단계 기준선 저장 완료")
        github_output("changed", "false")
        return 0

    if args.force_notify and not events:
        events = [{"type": "count_change", "changes": []}]

    if not events:
        print("KEPCO 송변전 사업단계 신규 변화 없음")
        github_output("changed", "false")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    report_path = OUT_DIR / now.strftime("%Y%m%dT%H%M%SZ-korea-grid-stage.html")
    report_path.write_text(render_report(events, counts), encoding="utf-8")
    github_output("changed", "true")
    github_output("report_path", str(report_path))
    print(f"kepco_grid_stage_changed=true events={len(events)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
