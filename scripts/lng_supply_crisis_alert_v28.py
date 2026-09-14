#!/usr/bin/env python3
"""에너지 공급감시 v28: 호르무즈 우회 송유관 뉴스 회수율 + 전용 가독성 본문.

v27의 사건·상태 변화 기준은 유지하고, 제목에 East-West/Petroline이 직접 안 들어간
Reuters/AP류 'Saudi pipeline outage' 표현도 같은 우회망 사건으로 잡는다.
우회 송유관 사건이 감지되면 일반 LNG 문구를 재사용하지 않고 원유 우회망 전용 본문을 만든다.
"""
from __future__ import annotations

import html

import lng_supply_crisis_alert_v2 as core
import lng_supply_crisis_alert_v27 as v27

_BASE_BUILD = core.build_regular_alert
_BASE_SETUP = core.build_setup_test

BYPASS_RECALL_QUERIES = (
    ("hormuz_shipping", '"East-West pipeline" Saudi when:7d'),
    ("hormuz_shipping", '"East-West oil pipeline" Saudi when:7d'),
    ("hormuz_shipping", '"Saudi pipeline outage" Hormuz when:7d'),
    ("hormuz_shipping", '"Saudi Arabia shuts" "oil pipeline" when:7d'),
    ("hormuz_shipping", '"Yanbu" Saudi pipeline outage when:7d'),
    ("hormuz_shipping", '사우디 송유관 가동 중단 호르무즈 우회 when:7d'),
)
for item in BYPASS_RECALL_QUERIES:
    if item not in core.NEWS_QUERIES:
        core.NEWS_QUERIES = tuple(core.NEWS_QUERIES) + (item,)

core.WORSENING_TERMS["hormuz_shipping"] = tuple(core.WORSENING_TERMS["hormuz_shipping"]) + (
    "saudi pipeline outage", "saudi pipeline attack", "shuts key oil pipeline",
    "shut key oil pipeline", "shuts down a pipeline", "shuts down oil pipeline",
    "shut down oil pipeline", "saudis shut down oil pipeline",
    "pipeline outage threatens", "송유관 중단 장기화", "사우디 송유관 중단",
)

core.SUBTYPE_TERMS = (
    ("hormuz_bypass_shutdown", (
        "saudi pipeline outage", "shuts key oil pipeline", "shut key oil pipeline",
        "shuts down key oil pipeline", "shuts down a pipeline", "shuts down oil pipeline",
        "shut down oil pipeline", "saudis shut down oil pipeline", "pipeline outage threatens",
        "사우디 송유관 중단", "송유관 중단 장기화",
    )),
) + tuple(core.SUBTYPE_TERMS)

# 현재 기사군의 다양한 표기를 한국어로 고정한다. 감시대상은 기사가 아니라 상태변화다.
v27.v12.v8.KNOWN_TRANSLATIONS.update({
    "Saudi Arabia shuts down a pipeline as Houthis seize an island, opening a new front in the Iran war":
        "사우디, 핵심 송유관 가동 중단…후티의 홍해 요충지 장악으로 중동 전선 확대",
    "Saudis shut down oil pipeline as Houthis tighten grip on Red Sea shipping":
        "사우디, 동서 송유관 가동 중단…후티의 홍해 항로 압박 확대",
    "Saudi Arabia shuts key oil pipeline after drone attack launched from Iraq":
        "사우디, 이라크발 드론 공격 뒤 핵심 동서 송유관 가동 중단",
    "Oil and gas prices climb after Saudi Arabia closes east-west pipeline - Yahoo Finance UK":
        "사우디의 동서 송유관 가동 중단 뒤 유가·가스 가격 상승",
    "Oil prices rise after drone attacks shut down Saudi Arabia’s East-West pipeline - The Guardian":
        "드론 공격으로 사우디 동서 송유관 가동 중단…유가 상승",
    "Oil prices rise after drone attacks shut down Saudi Arabia's East-West pipeline - The Guardian":
        "드론 공격으로 사우디 동서 송유관 가동 중단…유가 상승",
})
v27.v12.v8.SOURCE_KO.update({
    "yahoo finance uk": "야후 파이낸스",
    "yahoo finance": "야후 파이낸스",
})


def _bypass_groups(groups):
    return [g for g in groups if str(g.get("subtype") or "") in v27.BYPASS_SUBTYPES]


def _evidence_lines(groups) -> list[str]:
    """증거 기사 제목은 반드시 한국어로 표시하고 출처와 제목을 두 줄로 분리한다."""
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
            source = v27.v12.v8.source_name_ko(str(getattr(item, "source", "주요 매체") or "주요 매체"))
            title = v27.v12.v8.translate_title_ko(item)
            lines.append(f"• <b>{html.escape(source)}</b>")
            if link:
                lines.append(
                    f'  └ {html.escape(title)} · '
                    f'<a href="{html.escape(link, quote=True)}">원문</a>'
                )
            else:
                lines.append(f"  └ {html.escape(title)}")
            if len(lines) >= 8:
                return lines
    return lines


def _market_line(quotes) -> str | None:
    brent = quotes.get("brent") if isinstance(quotes, dict) else None
    if brent is None:
        return None
    try:
        return f"• <b>브렌트유</b> {html.escape(core.format_quote(brent))}"
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
        verdict = "🔴 호르무즈 우회 공급망까지 차질 · 원유 공급 스트레스 단계 상승"
    elif polarity == "easing":
        verdict = "🟢 호르무즈 우회 공급망 복구 진전 · 실제 수송량 정상화 확인 필요"
    else:
        verdict = "🟠 호르무즈 우회 공급망 상태 변화 · 방향 추가 확인 필요"

    lines = [
        "📌 <b>한눈에</b>",
        f"• <b>판정</b> {verdict}",
        f"• <b>현재 단계</b> {stage} · {state}",
        "• <b>핵심 의미</b> 호르무즈 자체 차질에 이어 우회 송유관까지 멈추면 사우디의 공급 완충장치가 동시에 약해짐",
        "",
        "📊 <b>핵심 숫자</b>",
        "• <b>최대 수송능력</b> 아람코 2026년 1분기 공식 · <b>700만배럴/일</b>",
        "• <b>전쟁 중 우회수송</b> 로이터 기준 약 <b>400만배럴/일</b>",
        "• <b>얀부 재고 버퍼</b> 송유관 중단 지속 시 약 <b>5~7일</b> 내 소진 가능 · 로이터 2026-09-13 추정",
        "• <b>최대 공급 위험</b> 장기 중단 시 약 <b>세계 원유 공급 4%</b> 추가 위험 · 로이터 추정",
    ]
    market = _market_line(quotes)
    if market:
        lines.append(market)

    lines.extend(["", "🔴 <b>무엇이 바뀌었나</b>"])
    evidence = _evidence_lines(selected)
    lines.extend(evidence or ["• 공식기관·주요 매체에서 우회 송유관 운영상태 변화 확인"])

    lines.extend([
        "",
        "🧭 <b>공급망 병목</b>",
        "• <b>우회 경로</b> 동부 유전지대 → 동서 송유관 → 홍해 얀부 → 해외 수출",
        "• <b>1차 병목</b> 동부 유전지대 → 동서 송유관 → 홍해 얀부 경로가 막히면 호르무즈를 피해 수출하던 물량이 다시 제약됨",
        "• <b>2차 병목</b> 송유관이 복구돼도 바브엘만데브 해협·홍해 통항이 막히면 서쪽 우회효과가 제한됨",
        "• <b>구분</b> 예방적 가동중단은 영구 생산능력 상실이 아님 · 실제 피해·수리기간·부분 재가동·정상용량 복구를 따로 판정",
        "",
        "🇰🇷 <b>한국 영향</b>",
        "• 원유 도입가격·정유 원재료비·항공유·경유·운임·물가 압력이 동시에 커지고, 에너지발 인플레이션이 글로벌 금리와 국내 할인율을 다시 밀어올릴 수 있음",
        "",
        "💰 <b>투자 포인트</b>",
        "• <b>돈 버는 능력</b> 비호르무즈 원유 공급원·정제마진 수혜 가능성 vs 원유 수입기업·항공·운송 원가 부담",
        "• <b>할인율</b> 유가·디젤 상승이 인플레이션 기대와 장기금리를 다시 올리는지 확인",
        "• <b>수급</b> 실제 사우디 수출 감소와 전략비축 방출·대체 원유 공급으로 상쇄되는지 확인",
        "• <b>시간표</b> 수리 예상기간 → 부분 재가동 → 전면 재가동 → 실제 일일 수송량 회복 순으로 추적",
    ])

    other = _other_changes(groups)
    if other:
        lines.extend(["", "🔎 <b>동시 감지</b>", *other])

    lines.extend([
        "",
        "⏱ <b>다음 확인</b>",
        "• 수리 예상기간 → 실제 일일 수송량 → 얀부 재고 → 바브엘만데브 해협·홍해 통항 → 브렌트유·디젤 → 인플레이션·금리",
        "",
        "🎯 <b>핵심 한 줄</b>",
        "• 호르무즈 차질을 버티던 사우디의 핵심 우회로까지 멈춰, 이번 사건은 단순 지정학 뉴스가 아니라 실제 세계 원유 공급량을 줄일 수 있는 단계로 올라감",
    ])
    return "\n".join(lines)


def build_regular_alert_v28(groups, quotes, new_signals, cleared_signals):
    title, body, metadata = _BASE_BUILD(groups, quotes, new_signals, cleared_signals)
    if _bypass_groups(groups):
        title = "🚨 호르무즈 우회망·사우디 송유관 공급경보"
        body = _build_bypass_body(groups, quotes)
    metadata["version"] = 28
    metadata.setdefault("hormuz_bypass_watch", {})["recall_queries"] = "East-West + Saudi pipeline outage + Yanbu + Korean variants"
    metadata["hormuz_bypass_watch"]["readability"] = "Korean evidence titles; scan-first sections; dedicated oil-bypass body"
    return title, body, metadata


def build_setup_test_v28(quotes):
    title, body, metadata = _BASE_SETUP(quotes)
    body += (
        "\n• 우회 송유관 기사 제목에 East-West/Petroline이 없어도 'Saudi pipeline outage/shuts key oil pipeline' 표현을 같은 사건으로 분류"
        "\n• 검색은 East-West·Saudi pipeline outage·Yanbu·한국어 표현을 별도 쿼리로 나눠 회수율 보강"
        "\n• 우회 송유관 사건은 일반 LNG 영향문구 대신 원유 공급망 전용 본문으로 출력"
        "\n• 영문 기사 제목은 한국어로 변환하고, 출처·제목을 두 줄로 분리해 가독성을 높임"
    )
    metadata["version"] = 28
    return title, body, metadata


core.build_regular_alert = build_regular_alert_v28
core.build_setup_test = build_setup_test_v28

if __name__ == "__main__":
    raise SystemExit(core.main())