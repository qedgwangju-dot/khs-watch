from __future__ import annotations

import html

import korea_energy_mix_watch as watch


_ORIGINAL_RENDER = watch.render


def headline_match(title: str) -> bool:
    lower = watch.norm(title).lower()
    # RSS 검색식 자체가 제12차 전기본/전력수급기본계획으로 제한되어 있으므로,
    # 제목에 '전기본'이 반복되지 않아도 재생에너지·원전·전력수요 핵심어가 있으면 잡는다.
    return any(term in lower for term in watch.ENERGY_TERMS)


def renewable_interpretation(row: dict) -> str:
    """220GW 재생에너지 기사에서 숫자 나열을 넘어 실행경로와 병목을 쉽게 풀어준다."""
    title = watch.norm(str(row.get("title", ""))).lower()
    if not (
        "재생" in title
        and any(term in title for term in ("220gw", "155gw", "61gw", "6배", "5.6배", "15년 뒤"))
    ):
        return ""

    return "\n".join(
        [
            "<b>쉽게 풀면</b>",
            "① <b>220GW는 지금 확정된 최종안이 아니라</b> 제12차 전기본에 반영하기 위한 잠정 전망",
            "② <b>2030년까지는 태양광을 먼저 빠르게 늘리고</b>, 2030년 이후 해상풍력 확대 속도를 높이는 구조",
            "③ <b>220GW는 설비용량</b>이라 날씨·시간대에 따라 실제 발전량은 달라짐 → 결국 송전망·ESS가 실제 공급력을 결정",
            "④ 배터리 ESS는 시간대별 변동 대응에 유리하지만, 며칠간 저풍속·저일사가 이어지면 <b>양수발전·장주기 저장</b>이 필요",
            "⑤ 따라서 핵심은 발전소 숫자보다 <b>계통 접속 → 송배전망·변전소 → ESS·양수 → 해상풍력 설치 인프라</b>가 같이 늘어나는지 확인하는 것",
            "",
            "<b>실제로 필요한 증설 속도</b>",
            "2025 → 2030  <b>+66.6GW</b>  = 연평균 약 <b>+13.3GW</b>",
            "2030 → 2035  <b>+63GW</b>  = 연평균 약 <b>+12.6GW</b>",
            "2035 → 2040  <b>+57GW</b>  = 연평균 약 <b>+11.4GW</b>",
            "태양광은 2025 → 2030에 <b>+56GW</b>를 먼저 늘려 연평균 약 <b>+11.2GW</b>",
            "해상풍력은 2030 → 2035에 <b>+22GW</b>를 늘려 연평균 약 <b>+4.4GW</b>가 필요한 후반 가속 구조",
            "",
            "<b>정부가 밀려는 실행수단</b>",
            "태양광  공공입지·햇빛소득마을·공장 지붕 활용·이격거리 규제 완화",
            "해상풍력  정부 주도 발전지구·인허가 의제·지원항만·전용 설치선박 확보",
            "육상풍력  기존 허가 물량 조기 보급·공공 계획입지·노후 설비 리파워링",
            "",
            "<b>기사에 나온 2035년 계약단가 목표</b>",
            "태양광  150 → <b>80원/kWh</b>  약 <b>-46.7%</b>",
            "육상풍력  180 → <b>120원/kWh</b>  약 <b>-33.3%</b>",
            "해상풍력  330 → <b>150원/kWh</b>  약 <b>-54.5%</b>",
            "",
            "<b>가장 현실적인 실패 경로</b>",
            "재생에너지 설비는 설치됐는데 계통 접속·ESS가 늦어짐 → 출력제어·접속 대기 증가 → 목표 GW가 실제 전력 공급으로 연결되지 못함",
            "",
            "<b>먼저 볼 지표</b>",
            "계통 접속 대기 물량 · 송변전 준공 일정 · ESS/양수 GW·GWh · 해상풍력 연간 준공 GW",
        ]
    )


def render_with_linked_source(rows: list[dict]) -> str:
    """출처명 자체를 링크로 만들고, 핵심 기사에는 읽기 쉬운 해석 블록을 추가한다."""
    body = _ORIGINAL_RENDER(rows)
    for row in rows[:5]:
        publisher = html.escape(str(row.get("publisher", "")))
        url = html.escape(str(row.get("url", "")), quote=True)
        if publisher and url:
            source_line = f"<b>출처</b>  {publisher}"
            linked_source_line = f'<b>출처</b>  <a href="{url}"><b>{publisher}</b></a>'
            body = body.replace(source_line, linked_source_line, 1)

            link_label = "공식 원문 보기" if row.get("official") else "기사 원문 보기"
            standalone_link = f'\n<a href="{url}"><b>{link_label}</b></a>'
            body = body.replace(standalone_link, "", 1)

        explanation = renewable_interpretation(row)
        if explanation:
            marker = f"\n<b>투자 의미</b>  {html.escape(watch.meaning(str(row.get('category', ''))))}"
            replacement = f"\n{explanation}\n\n<b>투자 의미</b>  {html.escape(watch.meaning(str(row.get('category', ''))))}"
            body = body.replace(marker, replacement, 1)

    return body


def main() -> int:
    watch.topic_match = headline_match
    watch.render = render_with_linked_source
    return watch.main()


if __name__ == "__main__":
    raise SystemExit(main())
