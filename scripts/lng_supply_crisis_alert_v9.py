#!/usr/bin/env python3
"""LNG 공급 위기 감시 v9.

v8의 가격·번역·Telegram 링크 규칙을 유지하면서 알래스카 LNG 정책/사업 촉매를 추가한다.

핵심 추가 규칙
1) 한국·일본의 알래스카 LNG 참여를 거론한 대통령/정부 발언도 '정책 촉매'로 조기 경보한다.
2) 발언과 실제 계약을 구분한다: 정치 발언 → 정부 합의/MOU → 오프테이크/SPA → FID → EPC/발주.
3) 알래스카 LNG는 현재 호르무즈 공급 정상화로 오해하지 않고 장기 공급 다변화 축으로 별도 해석한다.
4) 지연·취소·투자 철회·주 의회 제동도 반대 방향 촉매로 경보한다.
"""

from __future__ import annotations

import html

import lng_supply_crisis_alert_v2 as core
import lng_supply_crisis_alert_v8 as v8


ALASKA_NEWS_QUERIES = (
    ("alaska_lng", '"Alaska LNG" Korea Japan Trump pipeline investment when:3d'),
    ("alaska_lng", '"Alaska LNG" Korea KOGAS POSCO offtake investment FID pipeline when:7d'),
    ("alaska_lng", '"Alaska LNG" Japan JERA Tokyo Gas offtake investment FID when:7d'),
    ("alaska_lng", '"Alaska LNG" Glenfarne offtake SPA LOI FID EPC pipeline financing when:7d'),
    ("alaska_lng", '알래스카 LNG 한국 일본 트럼프 투자 가스관 수주 when:7d'),
)
core.NEWS_QUERIES = tuple(core.NEWS_QUERIES) + ALASKA_NEWS_QUERIES

# 한국·미국 1차/신뢰 출처를 보강한다.
core.TRUSTED_SOURCE_ALIASES = tuple(core.TRUSTED_SOURCE_ALIASES) + (
    "yonhap", "yonhap news agency", "sbs", "korea economic daily", "한국경제",
    "chosunbiz", "조선비즈", "herald economy", "헤럴드경제",
    "the white house", "white house", "u.s. department of energy", "department of energy",
    "state of alaska", "glenfarne", "alaska gasline development corporation", "agdc",
)
core.OFFICIAL_SOURCE_ALIASES = tuple(core.OFFICIAL_SOURCE_ALIASES) + (
    "the white house", "white house", "u.s. department of energy", "department of energy",
    "state of alaska", "glenfarne", "alaska gasline development corporation", "agdc",
)

core.WORSENING_TERMS["alaska_lng"] = (
    "stalled", "stall", "delay", "delayed", "postpone", "postponed", "cancel", "cancelled",
    "canceled", "withdraw", "withdraws", "withdrawal", "opposition", "uncertain", "uncertainty",
    "fails", "failed", "no decision", "not decided", "cost overrun", "cost increase",
    "제동", "지연", "연기", "취소", "철회", "불확실", "미정", "무산", "비용 증가",
)
core.EASING_TERMS["alaska_lng"] = (
    "going to alaska", "go to alaska", "participate", "participation", "join", "investment",
    "invest", "funding", "funds", "pipeline", "build pipelines", "offtake", "spa",
    "letter of intent", "loi", "memorandum of understanding", "mou", "agreement", "contract",
    "final investment decision", "fid", "epc", "notice to proceed", "committed", "commitment",
    "알래스카로 간다", "참여", "투자", "자금", "가스관", "파이프라인", "구매계약",
    "장기계약", "양해각서", "협약", "계약", "최종투자결정", "발주", "수주",
)

# 동일 사건의 매체별 제목이 같은 단계로 묶이도록 알래스카 전용 subtype을 최우선 적용한다.
core.SUBTYPE_TERMS = (
    ("alaska_setback", ("stalled", "delay", "delayed", "cancel", "withdraw", "제동", "지연", "취소", "철회", "무산")),
    ("alaska_fid", ("final investment decision", "fid", "최종투자결정")),
    ("alaska_offtake", ("offtake", "spa", "letter of intent", "loi", "구매계약", "장기계약")),
    ("alaska_epc", ("epc", "notice to proceed", "pipeline contract", "pipe order", "발주", "수주")),
    ("alaska_policy_signal", ("trump", "president", "going to alaska", "korea", "japan", "트럼프", "대통령", "한국", "일본")),
) + tuple(core.SUBTYPE_TERMS)

# 자주 나오는 영문 헤드라인은 번역 서비스 장애와 무관하게 정확히 한국어로 고정한다.
v8.KNOWN_TRANSLATIONS.update(
    {
        "Trump says S. Korea, Japan, others going to Alaska to 'load up' with oil, build pipelines":
            "트럼프, 한국·일본의 알래스카행 재차 언급…연료·석유 조달·파이프라인 건설 거론",
        'Trump Says South Korea and Japan Are "Going to Alaska" Over LNG Project':
            "트럼프, 알래스카 LNG 프로젝트 관련 한국·일본 참여 재차 언급",
        "Trump touts Alaska LNG plan, urges Korea and Japan to invest and build pipelines":
            "트럼프, 알래스카 LNG 계획 강조…한국·일본의 투자·파이프라인 건설 거론",
    }
)

_original_category_label = core.category_label
_original_classify_context = core.classify_alert_context
_original_impact_text = core.impact_text


def category_label_v9(category: str) -> str:
    if category == "alaska_lng":
        return "알래스카 LNG·미국 공급 다변화"
    return _original_category_label(category)


def classify_alert_context_v9(groups, new_signals, cleared_signals) -> str:
    alaska = [group for group in groups if group.get("category") == "alaska_lng"]
    if alaska:
        has_progress = any(group.get("polarity") == "easing" for group in alaska)
        has_setback = any(group.get("polarity") == "worsening" for group in alaska)
        if has_progress and not has_setback:
            return "strategic_supply_progress"
        if has_setback and not has_progress:
            return "strategic_supply_setback"
        return "strategic_supply_mixed"
    return _original_classify_context(groups, new_signals, cleared_signals)


def impact_text_v9(context: str):
    if context == "strategic_supply_progress":
        return (
            "알래스카 LNG는 한국의 당장 부족분을 메우는 물량이 아니라 중장기 공급 다변화 카드입니다. "
            "정책 발언 자체는 한국의 투자·구매 확정이 아니므로, 산업부·한국가스공사 등 한국 측 공식 확인과 실제 계약 단계로 넘어가는지 분리해서 봅니다.",
            "돈 버는 능력: 가스관용 강관·철강, LNG 플랜트/EPC, LNG선·기자재의 장기 수주 기대가 커질 수 있습니다. "
            "수급: 중동·호르무즈 의존도를 낮추는 전략적 옵션입니다. "
            "시간표: 대통령 발언 → 정부 협의/MOU → 오프테이크·SPA → FID → EPC·강관/설비 발주 순으로 확인합니다. "
            "정치 발언만으로 국내 업체의 실제 수주를 확정하지 않습니다.",
            "알래스카 LNG의 정책 촉매가 강화됐습니다. 다음 핵심은 한국 측 공식 참여 확인과 오프테이크·FID·실제 발주입니다.",
        )
    if context == "strategic_supply_setback":
        return (
            "알래스카 LNG의 일정·자금조달·정책 추진에 제동이 확인됐습니다. 이는 한국의 현재 LNG 수급 차질을 뜻하지는 않지만 장기 공급 다변화 옵션의 가시성을 낮춥니다.",
            "돈 버는 능력: 강관·EPC·LNG선 등 프로젝트 기대 수혜주의 시간표가 뒤로 밀릴 수 있습니다. "
            "수급: 중동 외 대체 공급원의 중장기 확보 기대가 약화됩니다. "
            "시간표: 지연 원인이 법안·자금·오프테이크·FID 중 어디인지와 재개 조건을 추적합니다.",
            "알래스카 LNG 추진에 제동이 확인됐으며, 재개 조건과 FID 일정이 핵심 확인점입니다.",
        )
    if context == "strategic_supply_mixed":
        return (
            "알래스카 LNG 관련 진전과 제약 신호가 동시에 확인됐습니다. 정치적 지원과 실제 상업성·일정은 분리해 판단해야 합니다.",
            "관련주는 정책 발언에 반응할 수 있지만 오프테이크·FID·EPC 발주가 확인되기 전까지는 기대와 실적을 분리합니다.",
            "알래스카 LNG는 정책 지원과 상업적 제약이 엇갈려 실제 계약·FID 확인이 필요합니다.",
        )
    return _original_impact_text(context)


def build_regular_alert_v9(groups, quotes, new_signals, cleared_signals):
    # v8의 한국어 번역 + HTML 원문 링크 포맷을 그대로 사용한다.
    title, body, metadata = v8.build_regular_alert_v8(groups, quotes, new_signals, cleared_signals)
    body = body.replace(
        "알래스카 LNG·미국 공급 다변화: 완화",
        "알래스카 LNG·미국 공급 다변화: 정책·사업 진전",
    ).replace(
        "알래스카 LNG·미국 공급 다변화: 악화",
        "알래스카 LNG·미국 공급 다변화: 지연·후퇴",
    )
    metadata["version"] = 9
    metadata["alaska_lng_stage_rule"] = [
        "정책 발언", "정부 협의/MOU", "오프테이크/SPA", "FID", "EPC/발주"
    ]
    return title, body, metadata


def build_setup_test_v9(quotes):
    title, body, metadata = v8.v7.build_setup_test_v7(quotes)
    title = "✅ LNG·천연가스 감시 정확도 규칙 v9 적용"
    body += (
        "\n• 알래스카 LNG: 한국·일본 참여 관련 대통령/정부 발언부터 조기 경보"
        "\n• 정치 발언과 실제 계약을 분리: 발언 → 정부 협의/MOU → 오프테이크/SPA → FID → EPC/발주"
        "\n• 알래스카 LNG 진전은 현재 호르무즈 정상화가 아니라 장기 공급 다변화 촉매로 별도 해석"
        "\n• 지연·취소·투자 철회·주 의회 제동도 반대 방향으로 경보"
    )
    metadata["version"] = 9
    return title, body, metadata


core.category_label = category_label_v9
core.classify_alert_context = classify_alert_context_v9
core.impact_text = impact_text_v9
core.fetch_market_quotes = v8.v7.fetch_market_quotes_v7
core.format_quote = v8.v7.v6.format_quote_v6
core.signal_label = v8.v7.te.signal_label_v4
core.build_regular_alert = build_regular_alert_v9
core.build_setup_test = build_setup_test_v9


if __name__ == "__main__":
    raise SystemExit(core.main())
