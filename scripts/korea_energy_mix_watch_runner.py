from __future__ import annotations

import html
import re
from typing import Any

import requests
from bs4 import BeautifulSoup

import korea_energy_mix_watch as watch


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
    # RSS 검색식 자체가 제12차 전기본/전력수급기본계획으로 제한되어 있으므로,
    # 제목에 '전기본'이 반복되지 않아도 재생에너지·원전·전력수요 핵심어가 있으면 잡는다.
    return any(term in lower for term in watch.ENERGY_TERMS)


def resolve_article_url(url: str) -> str:
    """Google News RSS 링크면 원 언론사 URL로 풀고, 실패하면 기존 URL을 유지한다."""
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

    # 드물게 일반 리다이렉트로도 원문이 풀리는 경우가 있어 한 번 더 시도한다.
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
        "구독",
        "기자 구독",
        "Copyright",
        "기사제보",
        "관련기사",
        "많이 본",
    )
    if any(token.lower() in text.lower() for token in noise):
        return ""
    return text


def fetch_article_body(url: str) -> tuple[str, str, str]:
    """원문 URL과 본문 텍스트를 반환한다. 본문 확인 실패 시 추정하지 않고 오류 사유를 함께 반환한다."""
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
            ".articleBody p",
            ".article-body p",
            ".article_view p",
            ".article-view p",
            ".view_text p",
            ".news_body p",
            ".news-body p",
            ".article_txt p",
            ".article-txt p",
            "main p",
        )
        best: list[str] = []
        for selector in selectors:
            paragraphs = []
            for node in soup.select(selector):
                text = _clean_paragraph(node.get_text(" ", strip=True))
                if len(text) >= 35:
                    paragraphs.append(text)
            if sum(len(x) for x in paragraphs) > sum(len(x) for x in best):
                best = paragraphs

        if sum(len(x) for x in best) < 500:
            fallback = []
            for node in soup.find_all("p"):
                text = _clean_paragraph(node.get_text(" ", strip=True))
                if len(text) >= 45:
                    fallback.append(text)
            if sum(len(x) for x in fallback) > sum(len(x) for x in best):
                best = fallback

        # 같은 문단이 모바일/PC 영역에 중복 삽입된 경우 제거한다.
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


def _has(text: str, *terms: str) -> bool:
    lower = text.lower()
    return all(term.lower() in lower for term in terms)


def _has_any(text: str, *terms: str) -> bool:
    lower = text.lower()
    return any(term.lower() in lower for term in terms)


def interpret_article_body(row: dict[str, Any], body: str, error: str) -> str:
    """제목이 아니라 실제 원문 본문에 존재하는 사실만 골라 읽기 쉬운 해석으로 재구성한다."""
    if not body:
        return "\n".join(
            [
                "<b>원문 본문 해석</b>",
                f"원문 본문 직접 확인 실패 — 임의 해석 생략 ({html.escape(error or '접근 제한')})",
            ]
        )

    lower = body.lower()
    points: list[str] = []
    execution: list[str] = []
    risks: list[str] = []

    # 목표와 시간표 — 원문에 수치가 실제로 있을 때만 작성한다.
    if "220gw" in lower and ("2040" in lower or "2040년" in body):
        if "33.4gw" in lower:
            points.append(
                "정부가 제시한 큰 그림은 <b>2025년 33.4GW 수준의 재생에너지를 2040년 220GW까지 확대</b>하는 것"
            )
        else:
            points.append("정부가 제시한 2040년 재생에너지 설비 목표·전망은 <b>220GW</b>")

    if "2030" in lower and "100gw" in lower and "2035" in lower and "163gw" in lower:
        points.append(
            "중간 경로는 <b>2030년 100GW → 2035년 163GW → 2040년 220GW</b>로, 한 번에 늘리는 계획이 아니라 단계적으로 증설하는 구조"
        )

    if _has_any(lower, "태양광을 중심", "태양광 중심", "태양광 먼저") and _has_any(
        lower, "2030년 이후", "해상풍력 확대", "해상풍력"
    ):
        points.append(
            "보급 순서는 <b>초반 태양광을 빠르게 늘리고, 2030년 이후 해상풍력을 본격 확대</b>하는 방식"
        )

    # 정부 실행수단 — 기사 본문에 실제 등장한 항목만 붙인다.
    support_terms = []
    for label, terms in (
        ("이격거리 규제 완화", ("이격거리",)),
        ("공공입지 활용", ("공공입지", "공공 입지")),
        ("공장 지붕 활용", ("공장 지붕", "산단 지붕", "산업단지 지붕")),
        ("햇빛소득마을", ("햇빛소득마을", "햇빛 소득마을")),
        ("정부 주도 해상풍력 발전지구", ("발전지구", "정부 주도")),
        ("인허가 절차 단축", ("인허가", "의제")),
        ("지원항만·설치선박 확충", ("지원항만", "설치선박", "설치 선박")),
        ("노후 풍력 리파워링", ("리파워링",)),
    ):
        if any(term.lower() in lower for term in terms):
            support_terms.append(label)
    if support_terms:
        execution.append("정부가 기사에서 제시한 실행수단: " + " · ".join(support_terms))

    # 단가 목표 — 숫자가 본문에 실제로 있는 경우에만 해석한다.
    price_bits = []
    if "80원" in body and "태양광" in body:
        price_bits.append("태양광 80원/kWh")
    if "120원" in body and "육상풍력" in body:
        price_bits.append("육상풍력 120원/kWh")
    if "150원" in body and "해상풍력" in body:
        price_bits.append("해상풍력 150원/kWh")
    if price_bits:
        execution.append(
            "보급량 확대와 동시에 발전비용도 낮추려는 구상이며, 기사에 제시된 목표는 " + " · ".join(price_bits)
        )

    # 병목과 저장 — 본문에서 해당 용어가 확인된 경우만 설명한다.
    if _has_any(lower, "송배전망", "전력망", "계통") and "ess" in lower:
        risks.append(
            "기사의 핵심 경고는 <b>재생에너지 설비 증가 속도를 전력망과 ESS가 따라가지 못할 수 있다는 점</b> — 발전소를 지어도 계통에 연결하지 못하면 실제 공급력으로 전환되지 않음"
        )
    if _has_any(lower, "장주기", "양수발전", "양수 발전", "저풍속", "저일사"):
        risks.append(
            "몇 시간짜리 변동은 배터리 ESS로 대응할 수 있지만, 장기간 저풍속·저일사에는 <b>양수발전·장주기 저장자원</b>이 별도로 필요하다는 의미"
        )
    if _has_any(lower, "출력제어", "접속 대기", "접속대기", "계통 접속"):
        risks.append(
            "실패 경로는 <b>설비 준공 → 계통 접속 지연 → 출력제어·대기물량 증가</b> 순서로 먼저 나타날 가능성이 큼"
        )

    # 전원별 현재/미래 숫자가 본문에 있으면 계산 없이 의미만 정리한다.
    if all(term in lower for term in ("155gw", "45gw", "16gw")):
        points.append(
            "2040년 전원별 중심축은 <b>태양광 155GW > 해상풍력 45GW > 육상풍력 16GW</b> 순으로, 절대 물량은 태양광이 가장 큼"
        )

    lines = ["<b>원문 본문 해석</b>"]
    if points:
        lines.append("<b>원문이 말하는 핵심</b>")
        lines.extend(f"• {point}" for point in points[:5])
    if execution:
        lines.extend(["", "<b>정부가 실제로 하려는 것</b>"])
        lines.extend(f"• {item}" for item in execution[:4])
    if risks:
        lines.extend(["", "<b>왜 전력망·ESS가 핵심인가</b>"])
        lines.extend(f"• {item}" for item in risks[:4])

    if len(lines) == 1:
        # 본문은 읽었지만 현재 도메인 규칙으로 안전하게 풀 수 있는 문장이 없는 경우 추정하지 않는다.
        lines.append("원문 본문은 확인했지만 확정적으로 재구성할 핵심 수치·정책 문구가 부족해 임의 해석은 생략")
    else:
        if risks:
            one_line = "재생에너지 목표 자체보다 <b>계통 접속·송배전망·ESS/장주기 저장이 같은 속도로 따라오는지가 실제 성패</b>"
        elif points:
            one_line = "기사의 숫자는 단순 목표치가 아니라 <b>정부가 언제 어떤 전원을 우선 증설할지 보여주는 투자 시간표</b>"
        else:
            one_line = "기사의 핵심은 발표 숫자보다 <b>이를 실행하기 위한 제도·인프라가 실제로 뒤따르는지</b> 확인하는 것"
        lines.extend(["", "<b>한마디로</b>", one_line])

    return "\n".join(lines)


def render_with_linked_source(rows: list[dict[str, Any]]) -> str:
    """출처명 자체를 링크로 만들고, 실제 원문 본문에 근거한 해석을 붙인다."""
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
