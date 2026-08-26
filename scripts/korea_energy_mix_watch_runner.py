from __future__ import annotations

import korea_energy_mix_watch as watch


def headline_match(title: str) -> bool:
    lower = watch.norm(title).lower()
    # RSS 검색식 자체가 제12차 전기본/전력수급기본계획으로 제한되어 있으므로,
    # 제목에 '전기본'이 반복되지 않아도 재생에너지·원전·전력수요 핵심어가 있으면 잡는다.
    return any(term in lower for term in watch.ENERGY_TERMS)


def main() -> int:
    watch.topic_match = headline_match
    return watch.main()


if __name__ == "__main__":
    raise SystemExit(main())
