from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

try:
    import korea_grid_stage_watch as base
except ModuleNotFoundError:
    from scripts import korea_grid_stage_watch as base

_BASE_PARSE_STAGE_ROWS = base.parse_stage_rows


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


def main(argv: list[str] | None = None) -> int:
    # 운영 경로는 v2 파일을 유지하되, 전체 로직은 단일 기준 구현(base)에 모은다.
    # KEPCO의 텍스트 노드형 목록 파싱만 v2 파서로 주입한다.
    original_parser = base.parse_stage_rows
    base.parse_stage_rows = parse_stage_rows
    try:
        return base.main(argv)
    finally:
        base.parse_stage_rows = original_parser


if __name__ == "__main__":
    raise SystemExit(main())
