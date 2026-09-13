from __future__ import annotations

import argparse
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

try:
    import korea_grid_stage_watch as base
except ModuleNotFoundError:
    from scripts import korea_grid_stage_watch as base


def parse_stage_rows(html_text: str, stage: str, stage_order: int, base_url: str) -> list[dict[str, Any]]:
    # 1차: 일반 표 구조
    rows = base.parse_stage_rows(html_text, stage, stage_order, base_url)
    if rows:
        return rows

    # 2차: KEPCO 현재 페이지처럼 목록이 표가 아닌 텍스트 노드로 렌더링되는 구조.
    soup = BeautifulSoup(html_text, "html.parser")
    tokens = [base.normalize(text) for text in soup.stripped_strings]
    tokens = [token for token in tokens if token]
    try:
        header = next(
            i for i in range(len(tokens) - 4)
            if tokens[i : i + 5] == ["번호", "사업명", "설비종류", "담당본부", "담당사업소"]
        )
    except StopIteration:
        return []

    result: list[dict[str, Any]] = []
    i = header + 5
    stop_words = {"이전", "다음", "페이지 번호 입력", "이 페이지에서 제공하는 정보에 만족하셨습니까?"}
    while i < len(tokens):
        token = tokens[i]
        if token in stop_words or token.startswith("이 페이지에서 제공하는 정보"):
            break
        if not re.fullmatch(r"\d+", token):
            i += 1
            continue
        if i + 4 >= len(tokens):
            break
        number, name, equipment, hq, office = tokens[i : i + 5]
        if not name or equipment in {"사업명", "설비종류"}:
            i += 1
            continue
        result.append(
            {
                "number": int(number),
                "name": name,
                "key": base.project_key(name),
                "equipment": equipment,
                "hq": hq,
                "office": office,
                "stage": stage,
                "stage_order": stage_order,
                "url": base_url,
            }
        )
        i += 5
    return result


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
            "User-Agent": "khs-watch-kepco-grid-stage-v2/1.0",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
        }
    )

    overview = session.get(base.KEPCO_OVERVIEW_URL, timeout=30)
    overview.raise_for_status()
    counts = base.parse_overview_counts(overview.text)
    if len(counts) < 4:
        raise RuntimeError(f"한국전력 단계별 건수 파싱 실패: {counts}")

    projects: dict[str, dict[str, Any]] = {}
    parsed_counts: dict[str, int] = {}
    for stage, order, url in base.STAGE_PAGES:
        response = session.get(url, timeout=30)
        response.raise_for_status()
        rows = parse_stage_rows(response.text, stage, order, response.url)
        parsed_counts[stage] = len(rows)
        for row in rows:
            projects[row["key"]] = row

    if not projects:
        raise RuntimeError("한국전력 사업 목록 파싱 결과가 0건입니다. 상태를 덮어쓰지 않습니다.")

    state = base.load_state()
    events = base.compare_state(state.get("counts", {}), state.get("projects", {}), counts, projects)
    initialized = bool(state.get("initialized")) and bool(state.get("projects"))
    base.save_state(counts, projects)

    print(
        "kepco_stage_snapshot="
        + ",".join(f"{stage}:{parsed_counts.get(stage, 0)}" for stage, _, _ in base.STAGE_PAGES)
        + f" total_visible={len(projects)}"
    )

    if not initialized and not args.force_notify:
        print("KEPCO 송변전 사업단계 v2 기준선 저장 완료")
        github_output("changed", "false")
        return 0

    if args.force_notify and not events:
        events = [{"type": "count_change", "changes": []}]

    if not events:
        print("KEPCO 송변전 사업단계 신규 변화 없음")
        github_output("changed", "false")
        return 0

    base.OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    report_path = base.OUT_DIR / now.strftime("%Y%m%dT%H%M%SZ-korea-grid-stage.html")
    report_path.write_text(base.render_report(events, counts), encoding="utf-8")
    github_output("changed", "true")
    github_output("report_path", str(report_path))
    print(f"kepco_grid_stage_changed=true events={len(events)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
