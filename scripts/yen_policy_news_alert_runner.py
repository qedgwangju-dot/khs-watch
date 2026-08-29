#!/usr/bin/env python3
"""Operational runner for yen policy-news alerts with source-fidelity guardrails."""

from __future__ import annotations

import datetime as dt
import html
import re
import sys
import urllib.parse

import yen_policy_news_alert as base
from krw_fx import JpyKrwQuote, format_krw, latest_jpy_krw, yen_to_krw

WSJ_MARKERS = (
    "wall street journal",
    "the wall street journal",
    "wsj",
    "wsj.com",
    "dow jones newswires",
)

FORECAST_MARKERS = (
    "has chance to",
    "could",
    "may",
    "might",
    "strategist",
    "analyst",
    "forecast",
    "forecasts",
    "expects",
    "expectation",
    "hsbc",
    "전망",
    "예상",
    "가능성",
)

KOREAN_MODAL_MARKERS = (
    "가능",
    "기회",
    "전망",
    "예상",
    "수 있",
    "할 수",
)

INTERVENTION_SCALE_TOPIC = "엔화 개입 실적·규모 공개"
INTERVENTION_SCALE_MARKERS = (
    "record",
    "past month",
    "spent",
    "amount",
    "total",
    "ministry data",
    "official data",
    "実施状況",
    "操作額",
    "過去最大",
    "사상 최대",
    "개입 규모",
    "개입액",
    "실시 상황",
)
INTERVENTION_SCALE_CONTEXT = (
    "intervention",
    "foreign exchange intervention",
    "yen-buying",
    "yen buying",
    "為替介入",
    "外国為替平衡操作",
    "円買い介入",
    "환율 개입",
    "외환시장 개입",
    "엔화 매수",
)
MOF_MONTHLY_INDEX = "https://www.mof.go.jp/policy/international_policy/reference/feio/data/monthly/index.html"
MOF_MONTHLY_BASE = "https://www.mof.go.jp/policy/international_policy/reference/feio/data/monthly/"

VERIFIED_LITERAL_TRANSLATIONS = {
    "boj has chance to support yen with september rate hike":
        "BOJ는 9월 금리 인상으로 엔화를 지지할 기회가 있다",
    "japan yen intervention hits record 96 billion in past month":
        "일본의 엔화 개입 규모, 지난 한 달간 사상 최대 960억달러 기록",
}

_original_source_group = base.source_group
_original_classify = base.classify
_original_translate_headline = base.translate_headline_to_korean
_original_build_message = base.build_message
_original_collect_items = base.collect_items


def _contains(text: str, markers: tuple[str, ...]) -> bool:
    lowered = html.unescape(text or "").lower()
    return any(marker.lower() in lowered for marker in markers)


def _normalized_headline(value: str) -> str:
    return base.normalize_text(value)


def _has_money(text: str) -> bool:
    value = html.unescape(text or "")
    patterns = (
        r"\$\s*\d+(?:\.\d+)?\s*(?:billion|bn|million|trillion)",
        r"\d+(?:\.\d+)?\s*(?:billion|bn|million|trillion)\s+(?:u\.s\.\s*)?dollars?",
        r"\d+(?:\.\d+)?\s*trillion\s+yen",
        r"\d+\s*兆\s*[\d,]*\s*億?円",
        r"\d+(?:\.\d+)?\s*조엔",
    )
    return any(re.search(pattern, value, flags=re.IGNORECASE) for pattern in patterns)


def _is_intervention_scale_disclosure(item: base.NewsItem) -> bool:
    text = item.text
    context = _contains(text, INTERVENTION_SCALE_CONTEXT)
    reuters_style = (
        "yen" in text.lower()
        and _contains(text, ("spent", "support yen", "ministry data", "official data"))
        and _contains(text, ("record", "past month", "amount", "total"))
    )
    return _has_money(text) and (context or reuters_style) and _contains(text, INTERVENTION_SCALE_MARKERS)


def source_group(source: str, full_text: str) -> str:
    if _contains(f"{source} {full_text}", WSJ_MARKERS):
        return "Wall Street Journal"
    return _original_source_group(source, full_text)


def classify(item: base.NewsItem) -> base.ClassifiedItem | None:
    if _is_intervention_scale_disclosure(item):
        level = base.source_level(item)
        if level == 0:
            return None
        return base.ClassifiedItem(
            item=item,
            topic=INTERVENTION_SCALE_TOPIC,
            material_score=5,
            source_level=level,
            source_group=source_group(item.source, item.text),
        )

    result = _original_classify(item)
    if result is None:
        return None
    if result.topic == "BOJ 9월 인상 기대·신호" and _contains(item.text, FORECAST_MARKERS):
        return base.ClassifiedItem(
            item=result.item,
            topic="BOJ 9월 인상 전망·시장 기대",
            material_score=result.material_score,
            source_level=result.source_level,
            source_group=result.source_group,
        )
    return result


def translate_headline_to_korean(
    title: str,
    source: str,
    topic: str,
    current,
) -> tuple[str, str]:
    headline = base.clean_headline(title, source)
    normalized = _normalized_headline(headline)
    literal = VERIFIED_LITERAL_TRANSLATIONS.get(normalized)
    if literal:
        return literal, "verified_literal"

    translated, status = _original_translate_headline(title, source, topic, current)
    if _contains(headline, ("has chance to", "could", "may", "might")) and not _contains(
        translated, KOREAN_MODAL_MARKERS
    ):
        if (
            "boj" in normalized
            and "september" in normalized
            and "rate hike" in headline.lower()
            and "yen" in normalized
        ):
            return "BOJ의 9월 금리 인상으로 엔화를 지지할 가능성에 관한 전망", "fidelity_fallback"
        return base.fallback_korean_headline(topic), "fidelity_fallback"
    return translated, status


def _latest_mof_monthly_item(current: dt.datetime) -> base.NewsItem | None:
    index_text, error = base.fetch_text(
        MOF_MONTHLY_INDEX,
        base.USER_AGENT,
        timeout=18,
        attempts=2,
        accept="text/html,*/*",
    )
    if error or not index_text:
        base.record_source_failure(
            lane="yen_policy_news_mof_intervention",
            source_name="Japan MOF monthly intervention index",
            source_url=MOF_MONTHLY_INDEX,
            error=error or "empty response",
            checked_at=current.astimezone(base.KST),
        )
        return None

    filenames = sorted(set(re.findall(r"(20\d{6}\.html)", index_text)))
    if not filenames:
        return None
    filename = filenames[-1]
    try:
        release_date = dt.datetime.strptime(filename[:8], "%Y%m%d").date()
    except ValueError:
        return None
    current_date = current.astimezone(base.KST).date()
    if release_date > current_date or (current_date - release_date).days > 1:
        return None

    url = urllib.parse.urljoin(MOF_MONTHLY_BASE, filename)
    page_text, page_error = base.fetch_text(
        url,
        base.USER_AGENT,
        timeout=18,
        attempts=2,
        accept="text/html,*/*",
    )
    if page_error or not page_text:
        base.record_source_failure(
            lane="yen_policy_news_mof_intervention",
            source_name="Japan MOF monthly intervention disclosure",
            source_url=url,
            error=page_error or "empty response",
            checked_at=current.astimezone(base.KST),
        )
        return None

    plain = html.unescape(re.sub(r"<[^>]+>", " ", page_text))
    plain = re.sub(r"\s+", " ", plain).strip()
    if not re.search(r"外国為替平衡操作", plain) or not re.search(r"\d+\s*兆\s*[\d,]+\s*億円", plain):
        return None
    title_match = re.search(r"外国為替平衡操作の実施状況\s*[（(]([^）)]+)[）)]", plain)
    period = title_match.group(1).strip() if title_match else release_date.isoformat()
    amount_match = re.search(r"(\d+)\s*兆\s*([\d,]+)\s*億円", plain)
    amount_text = f"{amount_match.group(1)}兆{amount_match.group(2)}億円" if amount_match else ""
    published = dt.datetime.combine(release_date, dt.time(17, 0), tzinfo=base.KST).astimezone(base.UTC)
    return base.NewsItem(
        title=f"日本財務省 外国為替平衡操作の実施状況 {period} {amount_text}".strip(),
        link=url,
        source="Japan Ministry of Finance",
        description=f"外国為替平衡操作 実施状況 操作額 {amount_text}",
        published=published,
    )


def collect_items(current: dt.datetime):
    items, errors = _original_collect_items(current)
    official = _latest_mof_monthly_item(current)
    if official is not None and official.item_id not in {item.item_id for item in items}:
        items.append(official)
        items.sort(key=lambda item: item.published, reverse=True)
    return items, errors


def _source_nature(topic: str, rank: int) -> str:
    if topic == INTERVENTION_SCALE_TOPIC:
        if rank >= 3:
            return "일본 재무성 공식 월간 외환시장 개입 실적 공개"
        return "주요매체의 외환시장 개입 실적 보도 — 실행기간과 발표시점을 구분"
    if "전망·시장 기대" in topic:
        return "시장 전망·분석 — BOJ 공식 결정이나 확정 신호 아님"
    if rank >= 3:
        return "공식자료·당국 발언"
    if "기대·신호" in topic:
        return "주요매체 보도·시장 신호 — 공식 결정 여부는 별도 확인"
    return "주요매체 보도 — 사실관계와 공식 확인 여부를 분리"


def _extract_jpy_amount(text: str) -> float | None:
    value = html.unescape(text or "")
    exact = re.search(r"(\d+)\s*兆\s*([\d,]+)\s*億円", value)
    if exact:
        return int(exact.group(1)) * 1_000_000_000_000.0 + int(exact.group(2).replace(",", "")) * 100_000_000.0
    trillion = re.search(r"(\d+(?:\.\d+)?)\s*trillion\s+yen", value, flags=re.IGNORECASE)
    if trillion:
        return float(trillion.group(1)) * 1_000_000_000_000.0
    korean = re.search(r"(\d+(?:\.\d+)?)\s*조엔", value)
    if korean:
        return float(korean.group(1)) * 1_000_000_000_000.0
    return None


def _extract_usd_amount(text: str) -> float | None:
    value = html.unescape(text or "")
    match = re.search(r"\$\s*(\d+(?:\.\d+)?)\s*(billion|bn|million|trillion)", value, flags=re.IGNORECASE)
    if not match:
        return None
    scale = {"million": 1e6, "billion": 1e9, "bn": 1e9, "trillion": 1e12}[match.group(2).lower()]
    return float(match.group(1)) * scale


def _format_yen_amount(yen: float) -> str:
    oku = int(round(yen / 100_000_000.0))
    cho, remainder = divmod(abs(oku), 10_000)
    sign = "-" if oku < 0 else ""
    return f"{sign}{cho:,}조{remainder:,}억엔" if remainder else f"{sign}{cho:,}조엔"


def _format_usd_amount(usd: float) -> str:
    if abs(usd) >= 1e9:
        return f"{usd / 1e9:,.1f}십억달러"
    if abs(usd) >= 1e6:
        return f"{usd / 1e6:,.1f}백만달러"
    return f"{usd:,.0f}달러"


def _money_context(item: base.NewsItem, quote: JpyKrwQuote) -> list[str]:
    text = item.text
    lines: list[str] = []
    yen = _extract_jpy_amount(text)
    usd = _extract_usd_amount(text)
    if yen is not None:
        lines.append(f"개입 규모: {_format_yen_amount(yen)} (약 {format_krw(yen_to_krw(yen, quote))})")
    if usd is not None:
        lines.append(f"기사 달러 환산: {_format_usd_amount(usd)} (약 {format_krw(usd * quote.usdkrw)})")
    if not lines:
        raise RuntimeError("intervention-scale alert contains money but amount parsing failed; refusing unconverted alert")
    lines.extend(
        [
            "해석: 이는 발표 시점의 신규 개입액이 아니라 원문에 명시된 기간의 누적 집행 실적입니다.",
            f"원화 환산 기준: 1엔={quote.krw_per_yen:.4f}원 / 100엔={quote.krw_per_100_yen:,.2f}원, USD/KRW={quote.usdkrw:,.2f}원 (FRED H.10 동일 기준일 {quote.date})",
        ]
    )
    return lines


def build_message(selected, current):
    title, body, payload = _original_build_message(selected, current)
    rows = body.splitlines()
    output: list[str] = []
    item_index = -1
    interpretation_label_added = False
    axis_pattern = re.compile(r"^(?:수급|할인율|돈 버는 능력|시간표):")
    money_quote: JpyKrwQuote | None = None
    scale_present = any(classified.topic == INTERVENTION_SCALE_TOPIC for classified, _rank, _groups in selected)
    if scale_present:
        money_quote = latest_jpy_krw()
        title = title.replace("엔화 정책 촉매 알림", "엔화 정책·개입 실적 촉매 알림")

    for line in rows:
        if re.match(r"^\d+\)\s", line):
            item_index += 1
            interpretation_label_added = False
            output.append(line)
            continue

        if line.startswith("헤드라인: "):
            output.append("원문 번역: " + line[len("헤드라인: "):])
            output.append("확인 범위: 원문 헤드라인·Google News RSS 요약 기준")
            if 0 <= item_index < len(selected):
                classified, rank, _groups = selected[item_index]
                output.append(f"원문 성격: {_source_nature(classified.topic, rank)}")
                if classified.topic == INTERVENTION_SCALE_TOPIC:
                    if money_quote is None:
                        raise RuntimeError("KRW quote unavailable for intervention-scale alert")
                    output.extend(_money_context(classified.item, money_quote))
            continue

        if axis_pattern.match(line) and not interpretation_label_added:
            output.append("시장 해석(원문 외 연결):")
            interpretation_label_added = True

        output.append(line)

    for index, item_payload in enumerate(payload.get("items") or []):
        item_payload["evidence_scope"] = "headline_and_google_news_rss_summary"
        item_payload["source_translation_separated_from_market_interpretation"] = True
        if index < len(selected):
            classified, rank, _groups = selected[index]
            item_payload["source_nature"] = _source_nature(classified.topic, rank)
            if classified.topic == INTERVENTION_SCALE_TOPIC and money_quote is not None:
                item_payload["krw_conversion"] = {
                    "required": True,
                    "date": money_quote.date,
                    "usdkrw": money_quote.usdkrw,
                    "usdjpy": money_quote.usdjpy,
                    "krw_per_yen": money_quote.krw_per_yen,
                    "method": "FRED H.10 same-date DEXKOUS / DEXJPUS",
                }

    payload["fidelity_policy"] = {
        "translation": "preserve modality, timing, actor and attribution from source",
        "interpretation": "market interpretation is labeled separately and must not be presented as source text",
        "full_text_rule": "do not infer article-body details when only headline/RSS summary is available",
        "money_rule": "foreign-currency money in intervention-scale alerts must include a verified KRW conversion",
    }
    return title, "\n".join(output), payload


def install() -> None:
    extra_queries = (
        ("en", 'Japan yen intervention record amount Ministry Finance'),
        ("en", 'Japan spent record support yen past month ministry data'),
        ("ja", '財務省 外国為替平衡操作 実施状況 円 兆円'),
    )
    for entry in extra_queries:
        if entry not in base.RSS_QUERIES:
            base.RSS_QUERIES = base.RSS_QUERIES + (entry,)
    if not any("Wall Street Journal" in query for _lang, query in base.RSS_QUERIES):
        base.RSS_QUERIES = base.RSS_QUERIES + (
            ("en", '"Bank of Japan" September rate hike yen "Wall Street Journal"'),
            ("en", 'BOJ September rate hike support yen WSJ'),
        )
    for marker in WSJ_MARKERS:
        if marker not in base.MAJOR_SOURCE_MARKERS:
            base.MAJOR_SOURCE_MARKERS = base.MAJOR_SOURCE_MARKERS + (marker,)
    base.source_group = source_group
    base.classify = classify
    base.translate_headline_to_korean = translate_headline_to_korean
    base.collect_items = collect_items
    base.build_message = build_message


install()


def main() -> int:
    return base.main()


if __name__ == "__main__":
    sys.exit(main())
