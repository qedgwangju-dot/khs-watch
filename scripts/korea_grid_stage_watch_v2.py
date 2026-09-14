from __future__ import annotations

import math
import re
from typing import Any

from bs4 import BeautifulSoup

try:
    import korea_grid_stage_watch as base
except ModuleNotFoundError:
    from scripts import korea_grid_stage_watch as base

_BASE_PARSE_STAGE_ROWS = base.parse_stage_rows
_BASE_LOAD_STATE = base.load_state
_BASE_RENDER_REPORT = base.render_report

COMPLETION_URL = (
    "https://www.kepco.co.kr/home/disclosure/transdisclosure/transstatus/"
    "completetoyear/boardList.do"
)


def parse_stage_rows(html_text: str, stage: str, stage_order: int, base_url: str) -> list[dict[str, Any]]:
    # 1차: 일반 표 구조
    rows = _BASE_PARSE_STAGE_ROWS(html_text, stage, stage_order, base_url)
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


def _page_count(html_text: str, expected_count: int) -> int:
    soup = BeautifulSoup(html_text, "html.parser")
    text = " ".join(soup.get_text(" ", strip=True).split())
    patterns = (
        r"페이지\s*번호\s*입력\s*/\s*(\d+)",
        r"페이지\s*번호\s*입력.*?/\s*(\d+)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return max(1, int(match.group(1)))
    return max(1, math.ceil(expected_count / base.PAGE_SIZE))


def fetch_all_stage_rows(
    session,
    stage: str,
    stage_order: int,
    url: str,
    expected_count: int,
) -> tuple[list[dict[str, Any]], bool]:
    # 상단 요약 건수는 목록 페이지보다 늦게 갱신될 수 있으므로,
    # expected_count로 페이지 수를 잘라버리지 않고 실제 목록의 마지막 페이지까지 읽는다.
    response = session.get(url, timeout=30)
    response.raise_for_status()
    first_rows = parse_stage_rows(response.text, stage, stage_order, response.url)
    if not first_rows and expected_count:
        return [], False

    total_pages = _page_count(response.text, expected_count)
    if total_pages <= 1:
        return first_rows, True

    page_method = base._discover_page_method(session, url, stage, stage_order, first_rows)
    if page_method is None:
        return first_rows, False

    method, parameter = page_method
    rows = list(first_rows)
    pages_read = 1
    for page in range(2, total_pages + 1):
        page_response = base._request_page(session, url, parameter, page, method)
        page_rows = parse_stage_rows(page_response.text, stage, stage_order, page_response.url)
        if not page_rows:
            break
        rows.extend(page_rows)
        pages_read += 1

    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        deduped[row["key"]] = row
    result = list(deduped.values())
    return result, pages_read == total_pages


def load_state() -> dict[str, Any]:
    state = _BASE_LOAD_STATE()
    # 과거 첫 페이지만 저장하던 기준선은 비교 기준으로 쓰지 않는다.
    # 4단계 목록을 실제 페이지 끝까지 읽은 이후에만 개별 사업 비교를 활성화한다.
    coverage = state.get("coverage") or {}
    if coverage and all(bool((coverage.get(stage) or {}).get("complete")) for stage in base.STAGE_ORDER):
        state["full_projects_initialized"] = True
    return state


def render_report(events, counts, coverage=None) -> str:
    text = _BASE_RENDER_REPORT(events, counts, coverage)

    def replace(match: re.Match[str]) -> str:
        parsed = int(match.group(1))
        expected = int(match.group(2))
        if parsed == expected:
            return match.group(0)
        return (
            f"• 목록 대조: 목록 {parsed}건 전수 확인 · 상단 요약 {expected}건"
            " → <b>한국전력 화면 간 집계 시차</b>"
        )

    return re.sub(r"• 목록 대조: (\d+)/(\d+)건 전수 확인", replace, text)


def main(argv: list[str] | None = None) -> int:
    # 운영 경로는 v2 파일을 유지하면서 base의 검증·상태 관리 구조를 그대로 사용한다.
    # 사업완료 공식 페이지까지 포함해 네 단계의 개별 사업명을 비교한다.
    base.DEFAULT_STAGE_PAGES["사업완료"] = (4, COMPLETION_URL)

    original_parser = base.parse_stage_rows
    original_fetch = base.fetch_all_stage_rows
    original_load = base.load_state
    original_render = base.render_report
    base.parse_stage_rows = parse_stage_rows
    base.fetch_all_stage_rows = fetch_all_stage_rows
    base.load_state = load_state
    base.render_report = render_report
    try:
        return base.main(argv)
    finally:
        base.parse_stage_rows = original_parser
        base.fetch_all_stage_rows = original_fetch
        base.load_state = original_load
        base.render_report = original_render


if __name__ == "__main__":
    raise SystemExit(main())
