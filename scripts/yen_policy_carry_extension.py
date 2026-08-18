#!/usr/bin/env python3
"""Extend yen policy-news monitoring with carry-trade and intervention-fade signals."""

from __future__ import annotations

import json

import yen_policy_news_alert as news

EXTRA_RSS_QUERIES = (
    ("en", 'yen "carry trade" intervention fades Japan'),
    ("en", 'yen carry trade resumes Japan BOJ'),
    ("en", 'yen shorts resume intervention Japan'),
    ("en", '"Japanese investors" overseas assets yen intervention'),
    ("en", 'yen intervention gains fade 160 carry trade'),
    ("ja", '円 キャリートレード 再開 為替介入'),
    ("ja", '円売り 再開 介入 効果'),
    ("ja", '日本 投資家 海外資産 円 介入'),
)

CARRY_MARKERS = (
    "carry trade",
    "carry-trade",
    "yen carry",
    "yen-funded",
    "borrow in yen",
    "borrowing yen",
    "キャリートレード",
    "円キャリー",
)

REBUILD_MARKERS = (
    "resume",
    "resumes",
    "resumed",
    "resuming",
    "rebuild",
    "rebuilding",
    "re-established",
    "reestablished",
    "return",
    "returns",
    "returned",
    "revive",
    "revives",
    "reviving",
    "renewed",
    "again",
    "再開",
    "再構築",
    "復活",
    "再び",
)

YEN_SHORT_MARKERS = (
    "short yen",
    "yen short",
    "yen shorts",
    "short positions",
    "bearish bets",
    "bearish yen",
    "selling of the yen",
    "selling yen",
    "sell yen",
    "円売り",
    "円ショート",
    "弱気",
)

INTERVENTION_FADE_MARKERS = (
    "intervention fades",
    "intervention fading",
    "effect of intervention fades",
    "effect of intervention is fading",
    "effect is fading",
    "intervention effect fading",
    "gives up half",
    "given up half",
    "relinquished half",
    "half of its gains",
    "half its gains",
    "pares intervention gains",
    "erases intervention gains",
    "back near 160",
    "near 160 per dollar",
    "near ¥160",
    "介入効果",
    "効果薄れ",
    "上昇分の半分",
    "160円近辺",
)

JAPAN_INVESTOR_MARKERS = (
    "japanese investors",
    "japanese retail",
    "japanese institutions",
    "japan investors",
    "domestic japanese investors",
    "国内投資家",
    "個人投資家",
    "機関投資家",
)

OVERSEAS_ASSET_MARKERS = (
    "overseas assets",
    "foreign assets",
    "overseas securities",
    "foreign securities",
    "overseas bonds",
    "foreign bonds",
    "overseas equities",
    "foreign equities",
    "capital outflow",
    "capital outflows",
    "海外資産",
    "外国証券",
    "対外証券",
    "海外投資",
    "資本流出",
)

FLOW_ACCELERATION_MARKERS = (
    "largest",
    "biggest",
    "most in",
    "two-year",
    "2-year",
    "record",
    "surge",
    "surged",
    "jump",
    "jumped",
    "increase",
    "increased",
    "accelerate",
    "accelerated",
    "最大",
    "急増",
    "増加",
    "2年ぶり",
    "2年余り",
)

STRUCTURAL_TOPICS = {
    "엔캐리 재구축·엔화 숏 재개",
    "개입 효과 약화·엔화 재약세",
    "일본 자금 해외유출·캐리 연료 확대",
}

_INSTALLED = False
_ORIGINAL_CLASSIFY = None
_ORIGINAL_FALLBACK = None
_ORIGINAL_AXIS_LINES = None
_ORIGINAL_BUILD_MESSAGE = None


def _has(text: str, markers: tuple[str, ...]) -> bool:
    return news.contains_any(text, markers)


def classify_structure(item: news.NewsItem) -> news.ClassifiedItem | None:
    text = item.text
    carry = _has(text, CARRY_MARKERS)
    rebuild = _has(text, REBUILD_MARKERS)
    yen_short = _has(text, YEN_SHORT_MARKERS)
    intervention = _has(text, news.INTERVENTION_MARKERS)
    fade = _has(text, INTERVENTION_FADE_MARKERS)
    japan_investor = _has(text, JAPAN_INVESTOR_MARKERS)
    overseas_assets = _has(text, OVERSEAS_ASSET_MARKERS)
    flow_acceleration = _has(text, FLOW_ACCELERATION_MARKERS)

    if (carry and rebuild) or (yen_short and rebuild) or (carry and yen_short and intervention):
        topic, score = "엔캐리 재구축·엔화 숏 재개", 4
    elif intervention and fade:
        topic, score = "개입 효과 약화·엔화 재약세", 4
    elif japan_investor and overseas_assets and flow_acceleration:
        topic, score = "일본 자금 해외유출·캐리 연료 확대", 3
    else:
        return None

    level = news.source_level(item)
    if level == 0:
        return None
    return news.ClassifiedItem(
        item=item,
        topic=topic,
        material_score=score,
        source_level=level,
        source_group=news.source_group(item.source, item.text),
    )


def _fallback_korean_headline(topic: str) -> str:
    mapping = {
        "엔캐리 재구축·엔화 숏 재개": "엔화 약세 베팅과 엔 캐리 트레이드가 다시 확대되고 있다는 주요 보도",
        "개입 효과 약화·엔화 재약세": "미·일 개입 이후 엔화 강세 효과가 빠르게 약해지고 있다는 주요 보도",
        "일본 자금 해외유출·캐리 연료 확대": "일본 투자자의 해외자산 매수가 크게 늘어 엔화 매도 수요가 확대됐다는 주요 보도",
    }
    if topic in mapping:
        return mapping[topic]
    assert _ORIGINAL_FALLBACK is not None
    return _ORIGINAL_FALLBACK(topic)


def _axis_lines(topic: str) -> list[str]:
    if topic == "엔캐리 재구축·엔화 숏 재개":
        return [
            "수급: 엔화 매도·해외 위험자산 매수 포지션 재축적 → 향후 엔고 시 청산 압력 확대",
            "할인율: 미·일 금리차가 유지되는 동안 엔 캐리 유인 지속",
            "돈 버는 능력: 엔저 재확대 시 일본 수입업종 원가 부담↑·한국 자동차의 상대 가격경쟁 부담 재확대 가능",
            "시간표: USD/JPY 160선·개입 전 고점 재접근, BOJ 차기 회의, CFTC 엔화 포지션 확인",
        ]
    if topic == "개입 효과 약화·엔화 재약세":
        return [
            "수급: 개입 효과 약화로 엔화 숏 재진입 가능성이 커지지만 추가 개입 위험도 동시에 상승",
            "할인율: 미·일 금리차 축소가 확인되지 않으면 개입만으로 추세 전환이 지속되기 어려움",
            "돈 버는 능력: 엔저 재확대는 일본 수출주 환산이익에 우호적이지만 수입 원가 업종에는 부담",
            "시간표: USD/JPY 160선·개입 전 고점 재시험과 미·일 추가 개입·BOJ 매파화 여부 확인",
        ]
    if topic == "일본 자금 해외유출·캐리 연료 확대":
        return [
            "수급: 일본 국내자금의 해외자산 매수 확대는 엔 매도·외화 매수 수요를 늘리는 방향",
            "할인율: 해외 금리가 일본보다 높게 유지될수록 해외자산 선호와 캐리 유인이 지속",
            "돈 버는 능력: 엔저 지속 시 일본 수입업종 비용 부담과 가계 실질구매력 압박이 커질 수 있음",
            "시간표: 일본 주간 대외증권 투자, CFTC 엔화 포지션, USD/JPY 160선 재시험 확인",
        ]
    assert _ORIGINAL_AXIS_LINES is not None
    return _ORIGINAL_AXIS_LINES(topic)


def install() -> None:
    global _INSTALLED, _ORIGINAL_CLASSIFY, _ORIGINAL_FALLBACK, _ORIGINAL_AXIS_LINES, _ORIGINAL_BUILD_MESSAGE
    if _INSTALLED:
        return

    _ORIGINAL_CLASSIFY = news.classify
    _ORIGINAL_FALLBACK = news.fallback_korean_headline
    _ORIGINAL_AXIS_LINES = news.axis_lines
    _ORIGINAL_BUILD_MESSAGE = news.build_message

    existing = list(news.RSS_QUERIES)
    for query in EXTRA_RSS_QUERIES:
        if query not in existing:
            existing.append(query)
    news.RSS_QUERIES = tuple(existing)

    def classify(item: news.NewsItem) -> news.ClassifiedItem | None:
        structural = classify_structure(item)
        if structural is not None:
            return structural
        assert _ORIGINAL_CLASSIFY is not None
        return _ORIGINAL_CLASSIFY(item)

    def build_message(selected, current):
        assert _ORIGINAL_BUILD_MESSAGE is not None
        title, body, payload = _ORIGINAL_BUILD_MESSAGE(selected, current)
        if any(classified.topic in STRUCTURAL_TOPICS for classified, _rank, _groups in selected):
            title = title.replace("엔화 정책 촉매 알림", "엔화 정책·수급 촉매 알림")
            body = body.replace(
                "가격 조건과 별개인 선행 정책·개입 뉴스 경보입니다.",
                "가격 조건과 별개인 선행 정책·수급·개입 뉴스 경보입니다.",
                1,
            )
        return title, body, payload

    news.classify = classify
    news.fallback_korean_headline = _fallback_korean_headline
    news.axis_lines = _axis_lines
    news.build_message = build_message
    _INSTALLED = True


def main() -> int:
    install()
    result = news.process()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
