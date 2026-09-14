from __future__ import annotations

import argparse
import html
import json
import math
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
DEFAULT_STAGE_PAGES = {
    "계획확정": (
        1,
        "https://www.kepco.co.kr/home/disclosure/transdisclosure/transstatus/plantoapprove/boardList.do",
    ),
    "사업승인": (
        2,
        "https://www.kepco.co.kr/home/disclosure/transdisclosure/transstatus/approvetostart/boardList.do",
    ),
    "공사착수": (
        3,
        "https://www.kepco.co.kr/home/disclosure/transdisclosure/transstatus/starttocomplete/boardList.do",
    ),
}
COUNT_LABELS = (
    ("계획확정", "계획확정 - 사업승인전"),
    ("사업승인", "사업승인 - 공사착수전"),
    ("공사착수", "공사착수 - 사업완료전"),
    ("사업완료", "사업완료 - 준공후 1년"),
)
STAGE_ORDER = {"계획확정": 1, "사업승인": 2, "공사착수": 3, "사업완료": 4}
FULL_CRAWL_MAX_AGE = timedelta(hours=6)
PAGE_SIZE = 10


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


def _extract_board_url(tag: Any, base_url: str) -> str:
    href = normalize(str(tag.get("href") or ""))
    if href and "boardList.do" in href:
        return urljoin(base_url, href)
    onclick = normalize(str(tag.get("onclick") or ""))
    match = re.search(r"['\"]([^'\"]*boardList\.do[^'\"]*)['\"]", onclick)
    if match:
        return urljoin(base_url, match.group(1))
    return ""


def discover_stage_pages(html_text: str, base_url: str) -> dict[str, tuple[int, str]]:
    pages = dict(DEFAULT_STAGE_PAGES)
    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup.find_all(["a", "button"]):
        text = normalize(tag.get_text(" ", strip=True))
        url = _extract_board_url(tag, base_url)
        if not url:
            continue
        if "계획확정" in text and "사업승인전" in text:
            pages["계획확정"] = (1, url)
        elif "사업승인" in text and "공사착수전" in text:
            pages["사업승인"] = (2, url)
        elif "공사착수" in text and "사업완료전" in text:
            pages["공사착수"] = (3, url)
        elif "사업완료" in text and ("준공후" in text or "완료후" in text):
            pages["사업완료"] = (4, url)

    if "사업완료" not in pages:
        patterns = (
            r"(?:href|location\.href)\s*=\s*['\"]([^'\"]*boardList\.do[^'\"]*)['\"][^>]{0,500}>[^<]{0,100}사업완료",
            r"사업완료[^<]{0,200}</[^>]+>[^<]{0,200}<[^>]+(?:href|onclick)=['\"]([^'\"]*boardList\.do[^'\"]*)['\"]",
        )
        for pattern in patterns:
            match = re.search(pattern, html_text, flags=re.I | re.S)
            if match:
                pages["사업완료"] = (4, urljoin(base_url, match.group(1)))
                break
    return pages


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


def _request_page(
    session: requests.Session,
    url: str,
    parameter: str,
    page: int,
    method: str = "get",
) -> requests.Response:
    value: int = (page - 1) * PAGE_SIZE if parameter == "pagerOffset" else page
    payload = {parameter: value}
    if method == "post":
        response = session.post(url, data=payload, timeout=30)
    else:
        response = session.get(url, params=payload, timeout=30)
    response.raise_for_status()
    return response


def _discover_page_method(
    session: requests.Session,
    url: str,
    stage: str,
    stage_order: int,
    first_rows: list[dict[str, Any]],
) -> tuple[str, str] | None:
    first_keys = [row["key"] for row in first_rows]
    candidates = (
        "pageIndex",
        "page",
        "pageNo",
        "currentPageNo",
        "currentPage",
        "pageNum",
        "pagerOffset",
    )
    for method in ("get", "post"):
        for parameter in candidates:
            try:
                response = _request_page(session, url, parameter, 2, method)
            except requests.RequestException:
                continue
            rows = parse_stage_rows(response.text, stage, stage_order, response.url)
            keys = [row["key"] for row in rows]
            if keys and keys != first_keys:
                print(f"kepco_grid_paging stage={stage} method={method} parameter={parameter}")
                return method, parameter
    return None


def fetch_all_stage_rows(
    session: requests.Session,
    stage: str,
    stage_order: int,
    url: str,
    expected_count: int,
) -> tuple[list[dict[str, Any]], bool]:
    response = session.get(url, timeout=30)
    response.raise_for_status()
    first_rows = parse_stage_rows(response.text, stage, stage_order, response.url)
    if expected_count <= len(first_rows) or expected_count <= PAGE_SIZE:
        return first_rows, len(first_rows) == expected_count
    if not first_rows:
        return [], False

    page_method = _discover_page_method(session, url, stage, stage_order, first_rows)
    if page_method is None:
        print(f"kepco_grid_paging_unresolved stage={stage} expected={expected_count} first={len(first_rows)}")
        return first_rows, False

    method, parameter = page_method
    rows = list(first_rows)
    total_pages = max(1, math.ceil(expected_count / PAGE_SIZE))
    for page in range(2, total_pages + 1):
        response = _request_page(session, url, parameter, page, method)
        page_rows = parse_stage_rows(response.text, stage, stage_order, response.url)
        if not page_rows:
            break
        rows.extend(page_rows)

    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        deduped[row["key"]] = row
    result = list(deduped.values())
    return result, len(result) == expected_count


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {
            "initialized": False,
            "counts": {},
            "projects": {},
            "coverage": {},
            "full_projects_initialized": False,
            "last_full_crawl_at": "",
        }
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "initialized": False,
            "counts": {},
            "projects": {},
            "coverage": {},
            "full_projects_initialized": False,
            "last_full_crawl_at": "",
        }
    data.setdefault("initialized", True)
    data.setdefault("counts", {})
    data.setdefault("projects", {})
    data.setdefault("coverage", {})
    data.setdefault("full_projects_initialized", False)
    data.setdefault("last_full_crawl_at", "")
    return data


def save_state(
    counts: dict[str, int],
    projects: dict[str, dict[str, Any]],
    coverage: dict[str, dict[str, Any]],
    full_projects_initialized: bool,
    last_full_crawl_at: str,
) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(
            {
                "initialized": True,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "counts": counts,
                "projects": projects,
                "coverage": coverage,
                "full_projects_initialized": full_projects_initialized,
                "last_full_crawl_at": last_full_crawl_at,
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


def count_change_event(old_counts: dict[str, Any], new_counts: dict[str, int]) -> dict[str, Any] | None:
    changes = []
    for stage in STAGE_ORDER:
        new_value = new_counts.get(stage)
        old_value = old_counts.get(stage)
        if isinstance(old_value, int) and isinstance(new_value, int) and old_value != new_value:
            changes.append((stage, old_value, new_value))
    if not changes:
        return None
    return {"type": "count_change", "changes": changes}


def compare_state(
    old_counts: dict[str, Any],
    old_projects: dict[str, dict[str, Any]],
    new_counts: dict[str, int],
    new_projects: dict[str, dict[str, Any]],
    *,
    allow_exits: bool = True,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    count_event = count_change_event(old_counts, new_counts)
    if count_event:
        events.append(count_event)

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

    if allow_exits:
        for key, previous in old_projects.items():
            if key not in new_projects:
                events.append({"type": "stage_exit", "previous": previous})

    return events


def _event_stage(event: dict[str, Any]) -> str:
    if event.get("type") == "stage_exit":
        return str((event.get("previous") or {}).get("stage", ""))
    return str((event.get("current") or {}).get("stage", ""))


def _net_project_delta(events: list[dict[str, Any]], stage: str) -> int:
    delta = 0
    for event in events:
        event_type = event.get("type")
        if event_type == "stage_entry" and _event_stage(event) == stage:
            delta += 1
        elif event_type == "stage_exit" and _event_stage(event) == stage:
            delta -= 1
        elif event_type == "stage_change":
            previous_stage = str((event.get("previous") or {}).get("stage", ""))
            current_stage = str((event.get("current") or {}).get("stage", ""))
            if previous_stage == stage:
                delta -= 1
            if current_stage == stage:
                delta += 1
    return delta


def _project_event_line(event: dict[str, Any]) -> str:
    event_type = str(event.get("type", ""))
    current = event.get("current") or {}
    previous = event.get("previous") or {}
    record = current or previous
    name = html.escape(str(record.get("name", "")))
    equipment = html.escape(str(record.get("equipment", "")) or "설비종류 확인 필요")
    hq = html.escape(str(record.get("hq", "")))
    office = html.escape(str(record.get("office", "")))
    owner = " / ".join(part for part in (hq, office) if part)
    suffix = f" · {equipment}" + (f" · {owner}" if owner else "")

    if event_type == "stage_change":
        old_stage = html.escape(str(previous.get("stage", "")))
        new_stage = html.escape(str(current.get("stage", "")))
        return f"• {name}: <b>{old_stage} → {new_stage}</b>{suffix}"
    if event_type == "stage_entry":
        stage = html.escape(str(current.get("stage", "")))
        return f"• {name}: <b>{stage} 목록 신규 확인</b>{suffix}"
    if event_type == "stage_exit":
        stage = html.escape(str(previous.get("stage", "")))
        return f"• {name}: <b>{stage} 목록에서 이탈</b>{suffix}"
    if event_type == "equipment_change":
        old_equipment = html.escape(str(previous.get("equipment", "")))
        new_equipment = html.escape(str(current.get("equipment", "")))
        return f"• {name}: 설비종류 <b>{old_equipment} → {new_equipment}</b>"
    return f"• {name}"


def render_report(
    events: list[dict[str, Any]],
    counts: dict[str, int],
    coverage: dict[str, dict[str, Any]] | None = None,
) -> str:
    now_kst = datetime.now(timezone.utc).astimezone(KST)
    coverage = coverage or {}
    lines = [
        "<b>전력망 사업단계 새 공식 변화</b>",
        "특정 기사 추적이 아니라 한국전력 송변전 사업현황의 실제 단계·물량 변화 감지",
    ]

    count_event = next((e for e in events if e.get("type") == "count_change"), None)
    count_delta_map: dict[str, int] = {}
    if count_event:
        lines.extend(["", "<b>무엇이 달라졌나</b>"])
        for stage, old_value, new_value in count_event["changes"]:
            delta = new_value - old_value
            count_delta_map[stage] = delta
            sign = "+" if delta > 0 else ""
            lines.append(f"• {stage}: <b>{old_value}건 → {new_value}건 ({sign}{delta})</b>")

    detailed = [e for e in events if e.get("type") != "count_change"]
    if detailed or count_delta_map:
        lines.extend(["", "<b>어떤 사업이 바뀌었나</b>"])
        for stage in STAGE_ORDER:
            stage_events = [e for e in detailed if _event_stage(e) == stage]
            moved_out = [
                e
                for e in detailed
                if e.get("type") == "stage_change"
                and str((e.get("previous") or {}).get("stage", "")) == stage
                and _event_stage(e) != stage
            ]
            display_events = stage_events + moved_out
            if stage not in count_delta_map and not display_events:
                continue
            delta = count_delta_map.get(stage)
            suffix = ""
            if delta is not None:
                suffix = f" ({'+' if delta > 0 else ''}{delta})"
            lines.append(f"\n<b>{stage}{suffix}</b>")
            if display_events:
                seen_lines: set[str] = set()
                for event in display_events:
                    line = _project_event_line(event)
                    if line in seen_lines:
                        continue
                    seen_lines.add(line)
                    lines.append(line)
            else:
                lines.append("• 요약 건수는 변했지만 개별 사업 목록에서 대응 사업명을 아직 확정하지 못함")

            if delta is not None:
                reconciled = _net_project_delta(detailed, stage)
                if reconciled != delta:
                    lines.append(
                        f"• 대조 상태: 요약 건수 변화 {delta:+d}건 / 개별 목록 확인 {reconciled:+d}건 → <b>목록 갱신 시차 확인 필요</b>"
                    )

            info = coverage.get(stage) or {}
            expected = info.get("expected")
            parsed = info.get("parsed")
            complete = info.get("complete")
            if isinstance(expected, int) and isinstance(parsed, int):
                if complete:
                    lines.append(f"• 목록 대조: {parsed}/{expected}건 전수 확인")
                else:
                    lines.append(f"• 목록 대조: {parsed}/{expected}건 확보 — 전수 확인 아님")

    stage_events = [e for e in detailed if e.get("type") in {"stage_change", "stage_entry", "equipment_change"}]
    if stage_events:
        axes = []
        meanings = []
        for event in stage_events:
            current = event.get("current") or {}
            stage = str(current.get("stage", ""))
            equipment = str(current.get("equipment", ""))
            axis = investment_axis(stage)
            meaning = investment_text(stage, equipment)
            if axis not in axes:
                axes.append(axis)
            if meaning not in meanings:
                meanings.append(meaning)
        lines.extend(["", "<b>투자 의미</b>"])
        if axes:
            lines.append("• 바뀐 축: " + " · ".join(f"<b>{html.escape(axis)}</b>" for axis in axes))
        for meaning in meanings[:4]:
            lines.append(f"• {html.escape(meaning)}")

    lines.extend(
        [
            "",
            "<b>다음 확인</b>",
            "• 상세 사업비·노선 km·발주 규격·낙찰사·계약금액·공사기간·전원 인가 시점",
            "",
            "<b>단계별 현재 건수</b>",
            "• " + " · ".join(f"{stage} {counts.get(stage, 0)}건" for stage in STAGE_ORDER),
            f"• 확인 시각: {now_kst:%Y년 %m월 %d일 %H:%M} KST",
            f'• 출처: <a href="{html.escape(KEPCO_OVERVIEW_URL, quote=True)}"><b>한국전력 송변전 건설 사업현황</b></a>',
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def github_output(key: str, value: str) -> None:
    path = os.getenv("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"{key}={value}\n")


def _last_full_crawl_is_stale(value: str) -> bool:
    if not value:
        return True
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - parsed > FULL_CRAWL_MAX_AGE


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-notify", action="store_true")
    args = parser.parse_args(argv)

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "khs-watch-kepco-grid-stage/2.0",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
        }
    )

    overview = session.get(KEPCO_OVERVIEW_URL, timeout=30)
    overview.raise_for_status()
    counts = parse_overview_counts(overview.text)
    if len(counts) < 4:
        raise RuntimeError(f"한국전력 단계별 건수 파싱 실패: {counts}")

    state = load_state()
    old_counts = state.get("counts", {})
    old_projects = state.get("projects", {})
    counts_changed = count_change_event(old_counts, counts) is not None
    need_full_crawl = (
        not bool(state.get("full_projects_initialized"))
        or counts_changed
        or _last_full_crawl_is_stale(str(state.get("last_full_crawl_at") or ""))
        or args.force_notify
    )

    projects = dict(old_projects)
    coverage = dict(state.get("coverage", {}))
    full_crawl_complete = bool(state.get("full_projects_initialized"))
    full_crawl_at = str(state.get("last_full_crawl_at") or "")

    if need_full_crawl:
        stage_pages = discover_stage_pages(overview.text, overview.url)
        crawled_projects: dict[str, dict[str, Any]] = {}
        new_coverage: dict[str, dict[str, Any]] = {}
        all_complete = True
        for stage in STAGE_ORDER:
            expected = counts.get(stage, 0)
            page = stage_pages.get(stage)
            if page is None:
                new_coverage[stage] = {"expected": expected, "parsed": 0, "complete": expected == 0, "url": ""}
                all_complete = all_complete and expected == 0
                print(f"kepco_grid_stage_page_unresolved stage={stage} expected={expected}")
                continue
            order, url = page
            rows, complete = fetch_all_stage_rows(session, stage, order, url, expected)
            for row in rows:
                crawled_projects[row["key"]] = row
            new_coverage[stage] = {
                "expected": expected,
                "parsed": len(rows),
                "complete": complete,
                "url": url,
            }
            all_complete = all_complete and complete
        projects = crawled_projects
        coverage = new_coverage
        full_crawl_complete = all_complete
        full_crawl_at = datetime.now(timezone.utc).isoformat()

    initialized = bool(state.get("initialized"))
    old_full = bool(state.get("full_projects_initialized"))

    if old_full and need_full_crawl:
        events = compare_state(old_counts, old_projects, counts, projects, allow_exits=full_crawl_complete)
    else:
        events = []
        count_event = count_change_event(old_counts, counts)
        if count_event:
            events.append(count_event)

    save_state(
        counts,
        projects,
        coverage,
        full_crawl_complete,
        full_crawl_at,
    )

    if not initialized and not args.force_notify:
        print("KEPCO 송변전 사업단계 기준선 저장 완료")
        github_output("changed", "false")
        return 0

    if not old_full and need_full_crawl and not args.force_notify:
        print(
            "KEPCO 송변전 개별사업 전수 기준선 재구축 완료 "
            f"complete={str(full_crawl_complete).lower()} projects={len(projects)}"
        )
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
    report_path.write_text(render_report(events, counts, coverage), encoding="utf-8")
    github_output("changed", "true")
    github_output("report_path", str(report_path))
    print(f"kepco_grid_stage_changed=true events={len(events)} projects={len(projects)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
