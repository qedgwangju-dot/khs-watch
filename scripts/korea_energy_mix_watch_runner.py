from __future__ import annotations

import html

import korea_energy_mix_watch as watch


_ORIGINAL_RENDER = watch.render


def headline_match(title: str) -> bool:
    lower = watch.norm(title).lower()
    # RSS 검색식 자체가 제12차 전기본/전력수급기본계획으로 제한되어 있으므로,
    # 제목에 '전기본'이 반복되지 않아도 재생에너지·원전·전력수요 핵심어가 있으면 잡는다.
    return any(term in lower for term in watch.ENERGY_TERMS)


def render_with_linked_source(rows: list[dict]) -> str:
    """별도 원문 보기 줄을 없애고 출처명 자체를 클릭 가능한 링크로 만든다."""
    body = _ORIGINAL_RENDER(rows)
    for row in rows[:5]:
        publisher = html.escape(str(row.get("publisher", "")))
        url = html.escape(str(row.get("url", "")), quote=True)
        if not publisher or not url:
            continue

        source_line = f"<b>출처</b>  {publisher}"
        linked_source_line = f'<b>출처</b>  <a href="{url}"><b>{publisher}</b></a>'
        body = body.replace(source_line, linked_source_line, 1)

        link_label = "공식 원문 보기" if row.get("official") else "기사 원문 보기"
        standalone_link = f'\n<a href="{url}"><b>{link_label}</b></a>'
        body = body.replace(standalone_link, "", 1)

    return body


def main() -> int:
    watch.topic_match = headline_match
    watch.render = render_with_linked_source
    return watch.main()


if __name__ == "__main__":
    raise SystemExit(main())
