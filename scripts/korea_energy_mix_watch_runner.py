from __future__ import annotations

import html
import re
from typing import Any

import requests
from bs4 import BeautifulSoup

try:
    import korea_energy_mix_watch as watch
except ModuleNotFoundError:
    from scripts import korea_energy_mix_watch as watch


_ORIGINAL_RENDER = watch.render
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.6",
}


def headline_match(title: str) -> bool:
    lower = watch.norm(title).lower()
    return any(term in lower for term in watch.ENERGY_TERMS)


def resolve_article_url(url: str) -> str:
    url = str(url or "").strip()
    if not url or "news.google.com" not in url:
        return url
    try:
        from googlenewsdecoder import new_decoderv1

        result = new_decoderv1(url, interval=0.2)
        if isinstance(result, dict) and result.get("status") and result.get("decoded_url"):
            return str(result["decoded_url"]).strip()
    except Exception as exc:  # noqa: BLE001
        print(f"google_news_decode_failed={type(exc).__name__}")
    try:
        response = requests.get(url, headers=_HEADERS, timeout=15, allow_redirects=True)
        response.raise_for_status()
        if response.url and "news.google.com" not in response.url:
            return response.url
    except Exception as exc:  # noqa: BLE001
        print(f"google_news_redirect_failed={type(exc).__name__}")
    return url


def _clean_paragraph(value: str) -> str:
    text = " ".join(str(value or "").split())
    noise = (
        "재판매 및 db 금지",
        "무단전재",
        "copyright",
        "기사제보",
        "관련기사",
        "많이 본",
        "이시간 핫 뉴스",
    )
    if any(token in text.lower() for token in noise):
        return ""
    return text


def fetch_article_body(url: str) -> tuple[str, str, str]:
    """실제 언론사 원문을 열어 본문을 추출한다. 실패하면 추정하지 않는다."""
    resolved = resolve_article_url(url)
    if not resolved:
        return url, "", "원문 URL 없음"
    try:
        response = requests.get(resolved, headers=_HEADERS, timeout=20, allow_redirects=True)
        response.raise_for_status()
        if response.url and "news.google.com" not in response.url:
            resolved = response.url
        soup = BeautifulSoup(response.text, "html.parser")
        for node in soup.select("script, style, noscript, nav, footer, header, aside"):
            node.decompose()

        selectors = (
            "article p",
            "#articleBody p",
            "#article_body p",
            "#textBody p",
            ".articleBody p",
            ".article-body p",
            ".article_view p",
            ".article-view p",
            ".articleView p",
            ".view_text p",
            ".viewer p",
            ".news_body p",
            ".news-body p",
            ".article_txt p",
            ".article-txt p",
            "main p",
        )
        best: list[str] = []
        for selector in selectors:
            paragraphs: list[str] = []
            for node in soup.select(selector):
                text = _clean_paragraph(node.get_text(" ", strip=True))
                if len(text) >= 35:
                    paragraphs.append(text)
            if sum(map(len, paragraphs)) > sum(map(len, best)):
                best = paragraphs

        if sum(map(len, best)) < 500:
            fallback: list[str] = []
            for node in soup.find_all("p"):
                text = _clean_paragraph(node.get_text(" ", strip=True))
                if len(text) >= 45:
                    fallback.append(text)
            if sum(map(len, fallback)) > sum(map(len, best)):
                best = fallback

        unique: list[str] = []
        seen: set[str] = set()
        for paragraph in best:
            key = re.sub(r"\s+", " ", paragraph).strip()
            if key and key not in seen:
                seen.add(key)
                unique.append(key)
        body = "\n".join(unique)
        if len(body) < 350:
            return resolved, "", "본문 추출량 부족"
        return resolved, body, ""
    except Exception as exc:  # noqa: BLE001
        return resolved, "", f"{type(exc).__name__}: {exc}"


def _has_any(text: str, *terms: str) -> bool:
    lower = text.lower()
    return any(term.lower() in lower for term in terms)


def _sentences(body: str) -> list[str]:
    parts = re.split(r"(?<=[.!?]|다\.)\s+|\n+", body)
    return [" ".join(x.split()) for x in parts if len(" ".join(x.split())) >= 30]


def _generic_extract(body: str) -> list[str]:
    """전용 규칙이 없는 기사도 빈 해석 대신 원문 핵심 문장을 추려 보여준다."""
    keywords = (
        "전력수요", "원전", "원자력", "재생에너지", "석탄", "lng", "가스발전",
        "ess", "송변전", "전력망", "공청회", "정부안", "확정", "준공", "부지",
        "발전소", "전력시장", "계통", "투자", "공론화",
    )
    scored: list[tuple[int, int, str]] = []
    for idx, sentence in enumerate(_sentences(body)):
        lower = sentence.lower()
        score = sum(3 for k in keywords if k in lower)
        score += min(len(re.findall(r"\d+(?:\.\d+)?(?:gw|기|년|%)?", lower)), 4) * 2
        if "정부" in sentence or "기후" in sentence:
            score += 2
        if score > 0:
            scored.append((score, -idx, sentence))
    best = sorted(scored, reverse=True)[:5]
    return [html.escape(x[2]) for x in sorted(best, key=lambda x: -x[1])]


def _interpret_renewable(body: str) -> list[str]:
    lower = body.lower()
    if not ("재생" in lower and "220gw" in lower):
        return []
    lines = [
        "<b>원문이 말하는 핵심</b>",
        "• 정부가 제12차 전기본에 반영할 재생에너지 보급 경로를 크게 끌어올리지만, <b>목표 GW만 늘려서는 실제 전력 공급이 보장되지 않는다는 내용</b>",
    ]
    if "33.4gw" in lower and "2040" in lower:
        lines.append("• 재생에너지 설비는 <b>2025년 33.4GW → 2040년 220GW</b>로 확대하는 구상")
    if all(x in lower for x in ("155gw", "45gw", "16gw")):
        lines.append("• 2040년 중심축은 <b>태양광 155GW > 해상풍력 45GW > 육상풍력 16GW</b>")
    if _has_any(lower, "전력망", "송배전망", "계통") and "ess" in lower:
        lines.extend([
            "",
            "<b>쉽게 풀면</b>",
            "• 발전소를 많이 지어도 송전선·변전소·ESS가 늦으면 전기를 필요한 곳으로 보내지 못함",
            "• 따라서 실질적인 병목은 <b>발전설비 → 계통 접속 → 송변전망 → ESS·양수발전</b> 순서에서 생길 수 있음",
        ])
    return lines


def _interpret_nuclear_coal_lng(body: str) -> list[str]:
    """신규 원전·2040 탈석탄·LNG 보완전원 기사를 원문 사실만으로 풀어쓴다."""
    lower = body.lower()
    if not (_has_any(lower, "신규 원전", "원전을 더", "원전 확대") and "석탄" in lower):
        return []

    lines = [
        "<b>원문이 말하는 핵심</b>",
        "• 전력수요 전망이 크게 올라간 상황에서 <b>2040년 석탄발전까지 없애려 하니, 그 빈자리를 어떤 발전원으로 채울지 다시 결정해야 한다</b>는 기사",
    ]

    if _has_any(lower, "다음 달", "내달") and "공청회" in lower:
        lines.append("• 정부와 제12차 전기본 총괄위원회는 <b>다음 달부터 신규 원전 확대와 2040년 석탄발전 폐지 등을 공론화</b>할 예정")

    if all(x in lower for x in ("대형원전 2기", "smr 1기")):
        lines.extend([
            "",
            "<b>이미 정해진 원전과 새로 검토하는 원전을 구분</b>",
            "• 제11차 전기본의 <b>대형원전 2기 + 소형모듈원전 1기</b>는 기존 확정 계획",
        ])
        if all(x in lower for x in ("영덕", "기장", "2037", "2038", "2035")):
            lines.append("• 기사 기준 예정지는 대형원전 2기 <b>경북 영덕</b>, 소형모듈원전 1기 <b>부산 기장</b>; 준공 예상은 소형모듈원전 2035년, 대형원전 2037·2038년")

    if "팹 4기" in lower and _has_any(lower, "원전을 더", "신규 원전"):
        lines.extend([
            "",
            "<b>이번에 새로 열린 가능성</b>",
            "• 김성환 장관은 호남 반도체 산단이 당초 <b>팹 4기보다 더 커지면 추가 원전 등 추가 대책을 검토</b>해야 한다고 언급",
        ])
        if "한빛 원전" in lower and "2개" in lower:
            lines.append("• 장관은 <b>한빛 원전에 2기를 더 지을 수 있는 부지</b>가 있다고 구체적으로 언급했지만, 이는 아직 신규 2기 건설 확정이 아니라 검토 가능성")

    if "최대 9기" in lower or "9기의 팹" in lower:
        lines.append("• 호남 산단 <b>최대 9개 팹</b> 가능성은 기사에 소개된 업계 관측으로, 정부 확정 물량과는 구분해야 함")

    if "2040" in lower and _has_any(lower, "석탄발전 폐지", "석탄발전 중단", "석탄발전 폐지 로드맵"):
        lines.extend([
            "",
            "<b>석탄을 없애면 생기는 문제</b>",
            "• 2040년까지 석탄발전을 단계적으로 폐지하면 <b>폐지 시점과 대체 발전소 준공 시점 사이의 발전 공백</b>을 막아야 함",
            "• 동시에 석탄발전 지역의 고용·지역경제를 옮기는 <b>정의로운 전환</b>까지 전기본과 함께 풀어야 함",
        ])

    if _has_any(lower, "1사 통합안", "발전공기업 5사"):
        lines.append("• 석탄발전 비중 축소와 함께 발전공기업 5사 재편도 논의 중이며, 기사상 <b>1사 통합안은 연구용역 권고 단계</b>로 최종 확정은 아님")

    if _has_any(lower, "lng 발전", "가스발전"):
        lines.extend([
            "",
            "<b>LNG가 왜 다시 거론되나</b>",
            "• LNG는 원전보다 건설기간이 짧고 출력 조절이 쉬워 <b>재생에너지의 간헐성과 탈석탄 공백을 메우는 보완전원</b>으로 검토",
            "• 다만 가스발전도 탄소를 배출하므로 장기적으로는 감축·수소화·비상전원화가 필요하다는 것이 정부의 방향",
        ])
        if "열 스팀" in lower and "호남" in lower:
            lines.append("• 호남 반도체 산단은 공정용 열·스팀 수요 때문에 <b>LNG 발전소 건설 가능성도 열어둔 상태</b>")

    if "10월" in lower and "정부안" in lower and "연내" in lower:
        lines.extend([
            "",
            "<b>앞으로 시간표</b>",
            "• 다음 달부터 신규 원전·탈석탄·전력시장·송변전 계획 토론 → <b>10월 정부안</b> → 국회 보고 등 절차 → <b>연내 제12차 전기본 확정</b>",
        ])

    lines.extend([
        "",
        "<b>쉽게 풀면</b>",
        "전력수요는 늘고 석탄은 없애야 하므로 <b>재생에너지 + 기존·신규 원전 + 일정 기간 LNG</b>를 어떤 비율과 일정으로 조합할지가 이번 전기본의 핵심. 추가 원전은 아직 확정이 아니라 공론화·검토 단계이고, 가장 먼저 볼 것은 <b>신규 원전 기수·부지, LNG 신규 용량, 석탄 폐지 연도별 물량, 10월 정부안</b>임",
    ])
    return lines


def interpret_article_body(row: dict[str, Any], body: str, error: str) -> str:
    if not body:
        return "\n".join([
            "<b>원문 본문 해석</b>",
            f"원문 본문 직접 확인 실패 — 임의 해석 생략 ({html.escape(error or '접근 제한')})",
        ])

    specialized = _interpret_nuclear_coal_lng(body) or _interpret_renewable(body)
    lines = ["<b>원문 본문 해석</b>"]
    if specialized:
        lines.extend(specialized)
        return "\n".join(lines)

    extracted = _generic_extract(body)
    if extracted:
        lines.extend([
            "<b>원문에서 확인되는 핵심</b>",
            *[f"• {x}" for x in extracted],
            "",
            "<b>해석 상태</b>",
            "전용 해석 규칙이 없는 기사라 원문 핵심 문장만 추려 표시 — 원문에 없는 의미는 임의로 추가하지 않음",
        ])
    else:
        lines.append("원문 본문은 확인했지만 핵심 문장을 안전하게 추출하지 못해 임의 해석은 생략")
    return "\n".join(lines)


def render_with_linked_source(rows: list[dict[str, Any]]) -> str:
    body = _ORIGINAL_RENDER(rows)
    for row in rows[:5]:
        original_url = str(row.get("url", ""))
        resolved_url, article_body, fetch_error = fetch_article_body(original_url)

        publisher = html.escape(str(row.get("publisher", "")))
        original_escaped = html.escape(original_url, quote=True)
        resolved_escaped = html.escape(resolved_url or original_url, quote=True)
        if publisher and (resolved_url or original_url):
            source_line = f"<b>출처</b>  {publisher}"
            linked_source_line = f'<b>출처</b>  <a href="{resolved_escaped}"><b>{publisher}</b></a>'
            body = body.replace(source_line, linked_source_line, 1)

            link_label = "공식 원문 보기" if row.get("official") else "기사 원문 보기"
            standalone_link = f'\n<a href="{original_escaped}"><b>{link_label}</b></a>'
            body = body.replace(standalone_link, "", 1)

        explanation = interpret_article_body(row, article_body, fetch_error)
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
