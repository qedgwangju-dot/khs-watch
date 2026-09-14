#!/usr/bin/env python3
"""에너지 공급감시 v29: 영문 기사 제목 원천 차단 + 호르무즈 우회망 알림 가독성 강화.

v28의 사건 감지·중복방지·시장값 규칙은 유지한다.
이번 버전은 출력만 보강한다.
- 기사 제목은 v12의 엄격 한국어 번역/한국어 대체문을 반드시 거친다.
- 영문 매체명은 가능한 한국어 표기로 바꾼다.
- 같은 핵심 정보는 삭제하지 않고 '한눈에 → 공급 충격 → 확인 근거 → 병목 구조 → 한국 영향 → 투자 4축 → 다음 확인 → 핵심 한 줄'로 재배치한다.
"""
from __future__ import annotations

import html

import lng_supply_crisis_alert_v2 as core
import lng_supply_crisis_alert_v28 as v28

v27 = v28.v27
v12 = v27.v12
v8 = v12.v8

_BASE_BUILD = core.build_regular_alert
_BASE_SETUP = core.build_setup_test

# 기사/매체의 영문 원문이 Telegram 본문으로 새는 것을 막기 위한 고정 표기.
v8.SOURCE_KO.update({
    "yahoo finance uk": "야후 파이낸스 영국",
    "yahoo finance": "야후 파이낸스",
    "the guardian": "가디언",
    "guardian": "가디언",
})

v8.KNOWN_TRANSLATIONS.update({
    "Oil and gas prices climb after Saudi Arabia closes east-west pipeline - Yahoo Finance UK":
        "사우디 동서 송유관 폐쇄로 국제유가·가스가격 상승",
    "Oil and gas prices climb after Saudi Arabia closes east-west pipeline":
        "사우디 동서 송유관 폐쇄로 국제유가·가스가격 상승",
    "Oil prices rise after drone attacks shut down Saudi Arabia’s East-West pipeline - The Guardian":
        "드론 공격으로 사우디 동서 송유관 가동 중단…국제유가 상승",
    "Oil prices rise after drone attacks shut down Saudi Arabia's East-West pipeline - The Guardian":
        "드론 공격으로 사우디 동서 송유관 가동 중단…국제유가 상승",
    "Oil prices rise after drone attacks shut down Saudi Arabia’s East-West pipeline":
        "드론 공격으로 사우디 동서 송유관 가동 중단…국제유가 상승",
    "Saudi pipeline outage threatens loss of 4% of global oil supply":
        "사우디 송유관 중단 장기화 시 세계 원유 공급 최대 4% 차질 위험",
    "Oil prices continue surge, rising 3% amid Saudi pipeline outage after attack":
        "사우디 송유관 공격 여파로 국제유가 3%대 추가 상승",
})


def _bypass_groups(groups):
    return [g for g in groups if str(g.get("subtype") or "") in v27.BYPASS_SUBTYPES]


def _source_ko(source: str) -> str:
    try:
        return v8.source_name_ko(source)
    except Exception:
        return "주요 매체"


def _title_ko(item: core.NewsItem) -> str:
    translated = v12.translate_title_ko_strict(item).strip()
    if not translated or v12._contains_untranslated_prose(translated):
        translated = v12.fallback_korean_title_v12(item)
    return translated


def _evidence_lines(groups) -> list[str]:
    lines: list[str] = []
    seen: set[tuple[str, str]] = set()
    for group in sorted(groups, key=lambda g: float(g.get("latest_epoch") or 0), reverse=True):
        for item in list(group.get("evidence") or []):
            raw_title = str(getattr(item, "title", "") or "").strip()
            link = str(getattr(item, "link", "") or "").strip()
            key = (raw_title, link)
            if key in seen:
                continue
            seen.add(key)
            source = _source_ko(str(getattr(item, "source", "주요 매체") or "주요 매체"))
            title = _title_ko(item)
            if link:
                lines.append(
                    f'• <b>{html.escape(source)}</b> · {html.escape(title)} · '
                    f'<a href="{html.escape(link, quote=True)}">원문</a>'
                )
            else:
                lines.append(f"• <b>{html.escape(source)}</b> · {html.escape(title)}")
            if len(lines) >= 4:
                return lines
    return lines


def _market_line(quotes) -> str | None:
    brent = quotes.get("brent") if isinstance(quotes, dict) else None
    if brent is None:
        return None
    try:
        text = core.format_quote(brent)
        text = text.replace("Yahoo Brent 선물 ", "")
        text = text.replace("Yahoo", "야후 파이낸스")
        text = text.replace("Brent", "브렌트유")
        return f"• <b>브렌트유</b> {html.escape(text)} · <b>원천</b> 야후 파이낸스 선물"
    except Exception:
        try:
            return f"• <b>브렌트유</b> {float(brent.price):,.2f}달러/배럴"
        except Exception:
            return None


def _other_changes(groups) -> list[str]:
    lines: list[str] = []
    seen: set[tuple[str, str]] = set()
    for group in groups:
        subtype = str(group.get("subtype") or "")
        if subtype in v27.BYPASS_SUBTYPES:
            continue
        category = str(group.get("category") or "")
        polarity = str(group.get("polarity") or "")
        key = (category, subtype)
        if key in seen:
            continue
        seen.add(key)
        try:
            category_text = core.category_label(category)
        except Exception:
            category_text = category or "동시 변화"
        stage = v27.v26.STAGE_LABELS.get(subtype, subtype or "상태 변화")
        state = "악화" if polarity == "worsening" else "완화" if polarity == "easing" else "혼재"
        lines.append(f"• <b>{html.escape(category_text)}</b> · {html.escape(stage)} · {state}")
        if len(lines) >= 4:
            break
    return lines


def _build_bypass_body(groups, quotes) -> str:
    selected = _bypass_groups(groups)
    latest = max(selected, key=lambda g: float(g.get("latest_epoch") or 0))
    subtype = str(latest.get("subtype") or "")
    polarity = str(latest.get("polarity") or "")
    state = "악화" if polarity == "worsening" else "완화" if polarity == "easing" else "확인 필요"
    stage = v27._stage_name(subtype)

    if polarity == "worsening":
        verdict = "호르무즈 우회 공급망까지 차질 · 원유 공급 스트레스 단계 상승"
    elif polarity == "easing":
        verdict = "호르무즈 우회 공급망 복구 진전 · 실제 수송량 정상화 확인 필요"
    else:
        verdict = "호르무즈 우회 공급망 상태 변화 · 방향 추가 확인 필요"

    lines = [
        "<b>한눈에</b>",
        f"• <b>판정</b> {verdict}",
        f"• <b>현재 단계</b> {stage} · {state}",
        "• <b>핵심 의미</b> 호르무즈 본선에 이어 사우디의 핵심 우회 송유관까지 멈추면 공급 완충장치가 동시에 약해짐",
        "",
        "<b>공급 충격</b>",
        "• <b>우회 능력</b> 최대 <b>700만배럴/일</b> · 전쟁 중 실제 우회수송 약 <b>400만배럴/일</b>",
        "• <b>재고 버퍼</b> 홍해 얀부 수출재고 약 <b>5~7일</b> · 로이터 2026-09-13 추정",
        "• <b>최대 공급 위험</b> 중단 장기화 시 약 <b>세계 원유 공급 4%</b> 추가 차질 가능 · 로이터 추정",
    ]
    market = _market_line(quotes)
    if market:
        lines.append(market)

    lines.extend(["", "<b>확인 근거</b>"])
    lines.extend(_evidence_lines(selected) or ["• 공식기관·주요 매체에서 우회 송유관 운영상태 변화 확인"])

    lines.extend([
        "",
        "<b>병목 구조</b>",
        "• <b>1차</b> 동부 유전지대 → 동서 송유관 → 홍해 얀부가 막히면 호르무즈를 피해 내보내던 물량이 다시 제약됨",
        "• <b>2차</b> 송유관이 복구돼도 바브엘만데브·홍해 통항이 막히면 서쪽 우회효과가 제한됨",
        "• <b>확정/미확정</b> 가동중단은 확인 · 영구 생산능력 상실은 미확정 · 실제 피해·수리기간·부분 재가동·정상용량 복구를 별도 판정",
        "",
        "<b>한국 영향</b>",
        "• <b>원가</b> 원유 도입가격·정유 원재료비·항공유·경유·운임 상승 압력",
        "• <b>물가·금리</b> 에너지발 물가 상승이 글로벌 장기금리와 국내 할인율을 다시 밀어올리는지 확인",
        "",
        "<b>투자 4축</b>",
        "• <b>돈버는능력</b> 비호르무즈 원유 공급원·정제마진에는 수혜 가능성 / 원유 수입기업·항공·운송에는 원가 부담",
        "• <b>할인율</b> 유가·디젤 상승 → 기대인플레이션 → 장기금리 상승 여부",
        "• <b>수급</b> 실제 사우디 수출 감소를 전략비축 방출·대체 원유가 얼마나 상쇄하는지 확인",
        "• <b>시간표</b> 수리 예상기간 → 부분 재가동 → 전면 재가동 → 실제 일일 수송량 회복",
    ])

    other = _other_changes(groups)
    if other:
        lines.extend(["", "<b>동시 감지</b>", *other])

    lines.extend([
        "",
        "<b>다음 확인</b>",
        "• ① 수리 예상기간 → ② 부분 재가동 → ③ 실제 일일 수송량 → ④ 얀부 재고 → ⑤ 바브엘만데브·홍해 통항 → ⑥ 브렌트유·디젤 → ⑦ 인플레이션·금리",
        "",
        "<b>핵심 한 줄</b>",
        "• 호르무즈 차질을 버티던 사우디의 핵심 우회로까지 멈춰, 단순 지정학 뉴스가 실제 세계 원유 공급 감소로 번질 수 있는 단계로 올라감",
    ])
    return "\n".join(lines)


def build_regular_alert_v29(groups, quotes, new_signals, cleared_signals):
    title, body, metadata = _BASE_BUILD(groups, quotes, new_signals, cleared_signals)
    if _bypass_groups(groups):
        title = "🚨 호르무즈 우회망·사우디 송유관 공급경보"
        body = _build_bypass_body(groups, quotes)
    metadata["version"] = 29
    metadata.setdefault("hormuz_bypass_watch", {})["headline_language"] = "ko-strict"
    metadata["hormuz_bypass_watch"]["readability"] = (
        "한눈에→공급 충격→확인 근거→병목 구조→한국 영향→투자 4축→다음 확인→핵심 한 줄"
    )
    return title, body, metadata


def build_setup_test_v29(quotes):
    title, body, metadata = _BASE_SETUP(quotes)
    body += (
        "\n• 호르무즈 우회망 근거 기사 제목은 엄격 한국어 번역을 거치며 영문 원문 제목 송출 차단"
        "\n• Yahoo Finance UK→야후 파이낸스 영국, The Guardian→가디언 등 매체명도 한국어 표기"
        "\n• 정보량은 유지하되 공급 충격·근거·병목·한국 영향·투자 4축을 분리해 한눈에 읽히도록 재배치"
    )
    metadata["version"] = 29
    return title, body, metadata


core.build_regular_alert = build_regular_alert_v29
core.build_setup_test = build_setup_test_v29

if __name__ == "__main__":
    raise SystemExit(core.main())
