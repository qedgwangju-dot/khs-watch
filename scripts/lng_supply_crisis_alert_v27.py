#!/usr/bin/env python3
"""에너지 공급감시 v27: 호르무즈 우회 원유수송망(East-West/Red Sea) 상태변화 감시 추가.

특정 CNBC/Reuters 기사 자체가 아니라 다음 사건 상태를 감시한다.
- 호르무즈 우회 송유관 공격·손상
- 처리용량 축소·가동중단
- 재가동·정상용량 복구
- Yanbu/Red Sea 측 재고 버퍼와 Bab el-Mandeb 2차 병목
"""
from __future__ import annotations

import hashlib
import html

import lng_supply_crisis_alert_v2 as core
import lng_supply_crisis_alert_v12 as v12
import lng_supply_crisis_alert_v26 as v26

_BASE_CONFIRMED = core.confirmed_news_groups
_BASE_BUILD = core.build_regular_alert
_BASE_SETUP = core.build_setup_test

BYPASS_QUERIES = (
    ("hormuz_shipping", 'Saudi East-West Pipeline Petroline Yanbu shutdown restart attack capacity Hormuz bypass when:3d'),
    ("hormuz_shipping", 'Hormuz bypass oil pipeline Saudi UAE Fujairah Yanbu outage damage restart throughput when:3d'),
    ("hormuz_shipping", 'Saudi Aramco East-West pipeline drone attack repair estimate Yanbu stocks when:7d'),
    ("hormuz_shipping", 'Bab el-Mandeb Perim Mayun Red Sea Saudi oil exports Yanbu blockade tanker when:3d'),
    ("hormuz_shipping", '사우디 동서 송유관 호르무즈 우회 얀부 가동중단 재가동 공격 복구 when:7d'),
    ("hormuz_shipping", '호르무즈 우회 송유관 사우디 UAE 후자이라 홍해 원유 수출 병목 when:7d'),
)
for item in BYPASS_QUERIES:
    if item not in core.NEWS_QUERIES:
        core.NEWS_QUERIES = tuple(core.NEWS_QUERIES) + (item,)

core.TRUSTED_SOURCE_ALIASES = tuple(core.TRUSTED_SOURCE_ALIASES) + (
    "saudi energy ministry", "saudi ministry of energy", "ministry of energy saudi arabia",
    "saudi aramco", "aramco", "associated press", "ap news", "the guardian",
)
core.OFFICIAL_SOURCE_ALIASES = tuple(core.OFFICIAL_SOURCE_ALIASES) + (
    "saudi energy ministry", "saudi ministry of energy", "ministry of energy saudi arabia",
    "saudi aramco", "aramco",
)

core.WORSENING_TERMS["hormuz_shipping"] = tuple(core.WORSENING_TERMS["hormuz_shipping"]) + (
    "east-west pipeline", "east west pipeline", "petroline", "yanbu", "pipeline shut",
    "pipeline shutdown", "pipeline offline", "pipeline suspended", "reduced throughput",
    "capacity loss", "drone attack", "bypass pipeline", "red sea export route",
    "동서 송유관", "우회 송유관", "송유관 가동 중단", "송유관 중단", "처리용량 축소",
    "얀부", "송유관 공격", "우회망 차질",
)
core.EASING_TERMS["hormuz_shipping"] = tuple(core.EASING_TERMS["hormuz_shipping"]) + (
    "east-west pipeline restarts", "east-west pipeline resumes", "pipeline restarted",
    "pipeline resumes operations", "pipeline restored", "full capacity restored",
    "throughput restored", "petroline restarts", "동서 송유관 재가동", "송유관 재가동",
    "정상 용량 복구", "처리용량 복구", "우회망 복구",
)

# 기존 'attack' 같은 일반 분류보다 앞에서 우회망의 실제 운영상태를 잡는다.
core.SUBTYPE_TERMS = (
    ("hormuz_bypass_restored", (
        "full capacity restored", "throughput restored", "pipeline fully restored",
        "정상 용량 복구", "처리용량 복구", "완전 복구",
    )),
    ("hormuz_bypass_restart", (
        "east-west pipeline restarts", "east-west pipeline resumes", "pipeline restarted",
        "pipeline resumes operations", "petroline restarts", "동서 송유관 재가동", "송유관 재가동",
    )),
    ("hormuz_bypass_shutdown", (
        "east-west pipeline shut", "east-west pipeline is shut", "pipeline shut down",
        "pipeline shutdown", "pipeline offline", "pipeline suspended", "petroline shut",
        "동서 송유관 가동 중단", "동서 송유관 중단", "우회 송유관 가동 중단",
    )),
    ("hormuz_bypass_capacity_loss", (
        "reduced throughput", "capacity loss", "flows cut", "flow cut", "throughput cut",
        "처리용량 축소", "수송량 감소", "수송량 축소",
    )),
    ("hormuz_bypass_attack", (
        "east-west pipeline" , "petroline", "동서 송유관", "우회 송유관",
    )),
) + tuple(core.SUBTYPE_TERMS)

BYPASS_SUBTYPES = {
    "hormuz_bypass_attack",
    "hormuz_bypass_capacity_loss",
    "hormuz_bypass_shutdown",
    "hormuz_bypass_restart",
    "hormuz_bypass_restored",
}

MAJOR_SOURCES = (
    "reuters", "bloomberg", "cnbc", "associated press", "ap news",
    "financial times", "wall street journal", "the guardian",
    "saudi energy ministry", "saudi ministry of energy", "saudi aramco", "aramco",
)

v26.STAGE_LABELS.update({
    "hormuz_bypass_attack": "호르무즈 우회 송유관 공격·손상",
    "hormuz_bypass_capacity_loss": "호르무즈 우회 송유관 수송능력 축소",
    "hormuz_bypass_shutdown": "호르무즈 우회 송유관 가동중단",
    "hormuz_bypass_restart": "호르무즈 우회 송유관 재가동",
    "hormuz_bypass_restored": "호르무즈 우회 송유관 정상용량 복구",
})

# 자주 노출되는 헤드라인은 식별 정확도를 위해 한국어를 잠근다.
v12.v8.KNOWN_TRANSLATIONS.update({
    "Saudi Energy Ministry: East-West pipeline shut down as a precaution following several attacks":
        "사우디 에너지부, 연이은 공격 뒤 동서 송유관 예방적 가동 중단",
    "Saudi Energy Ministry: East-West pipeline is shut down as a precaution following multiple attacks":
        "사우디 에너지부, 연이은 공격 뒤 동서 송유관 예방적 가동 중단",
    "Saudi pipeline outage threatens loss of 4% of global oil supply":
        "사우디 송유관 중단 장기화 시 세계 원유 공급 최대 4% 차질 위험",
})


def _event_id(subtype: str, published_epoch: float) -> str:
    # 동일 운영단계의 반복기사만 묶고, 중단→재가동→완전복구 같은 단계전환은 새 알림으로 살린다.
    bucket = int(published_epoch // (7 * 24 * 3600))
    raw = f"hormuz_bypass|{subtype}|{bucket}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def confirmed_news_groups_v27(items: list[core.NewsItem]):
    confirmed = list(_BASE_CONFIRMED(items))
    existing_stage = {
        (str(g.get("category")), str(g.get("polarity")), str(g.get("subtype")))
        for g in confirmed
    }
    existing_ids = {str(g.get("event_id")) for g in confirmed}

    for item in sorted(items, key=lambda x: x.published_epoch, reverse=True):
        if item.category != "hormuz_shipping" or item.subtype not in BYPASS_SUBTYPES:
            continue
        if not (item.official or core.source_matches(item.source, MAJOR_SOURCES)):
            continue
        stage_key = (item.category, item.polarity, item.subtype)
        if stage_key in existing_stage:
            continue
        event_id = _event_id(item.subtype, item.published_epoch)
        if event_id in existing_ids:
            continue
        confirmed.append({
            "category": item.category,
            "polarity": item.polarity,
            "subtype": item.subtype,
            "event_id": event_id,
            "latest_epoch": item.published_epoch,
            "evidence": [item],
            "verification": "호르무즈 우회수송망 조기경보 · 공식기관/주요 통신·금융매체 확인",
        })
        existing_stage.add(stage_key)
        existing_ids.add(event_id)

    confirmed.sort(key=lambda g: float(g.get("latest_epoch") or 0), reverse=True)
    return confirmed


def _stage_name(subtype: str) -> str:
    return v26.STAGE_LABELS.get(subtype, "호르무즈 우회수송망 변화")


def _bypass_section(groups, quotes) -> list[str]:
    selected = [g for g in groups if str(g.get("subtype") or "") in BYPASS_SUBTYPES]
    if not selected:
        return []
    latest = max(selected, key=lambda g: float(g.get("latest_epoch") or 0))
    subtype = str(latest.get("subtype") or "")
    polarity = str(latest.get("polarity") or "")
    state = "악화" if polarity == "worsening" else "완화" if polarity == "easing" else "확인 필요"

    lines = [
        "<b>호르무즈 우회 원유수송망</b>",
        f"• <b>현재 단계</b> {_stage_name(subtype)} · {state}",
        "• <b>왜 핵심인가</b> 사우디 동서 송유관은 호르무즈를 거치지 않고 동부 유전지대에서 홍해 얀부로 원유를 보내는 핵심 우회로",
        "• <b>수송능력 기준선</b> Aramco 공식 Q1 2026 최대 <b>700만배럴/일</b> · 전쟁 중 실제 우회수송은 Reuters 기준 약 <b>400만배럴/일</b>",
        "• <b>단기 버퍼</b> Reuters 2026-09-13 추정으로 송유관이 계속 멈추면 얀부 재고가 약 <b>5~7일</b> 내 소진될 수 있음",
        "• <b>세계 공급 위험</b> 장기 중단 시 최대 약 <b>세계 원유 공급 4%</b>가 추가로 위험해질 수 있다는 Reuters 추정",
        "• <b>2차 병목</b> 얀부로 보내도 홍해·Bab el-Mandeb 항로가 다시 막히면 우회 효과가 약해지므로 송유관과 해상항로를 함께 감시",
    ]
    brent = quotes.get("brent") if isinstance(quotes, dict) else None
    if brent is not None:
        try:
            lines.append(f"• <b>시장 확인</b> {html.escape(core.format_quote(brent))}")
        except Exception:
            pass
    lines.extend([
        "• <b>한국 영향</b> 원유 도입가격·정유 원재료비·항공유/경유·운임·물가 압력이 동시에 커질 수 있고, 에너지발 인플레이션이 장기금리까지 자극할 수 있음",
        "• <b>주의</b> 예방적 가동중단 ≠ 영구 생산능력 상실. 실제 피해·수리기간·부분 재가동·정상용량 복구를 단계별로 분리",
        "• <b>다음 확인</b> 수리 예상기간 → 부분/전면 재가동 → 실제 일일 수송량 → 얀부 재고 → Bab el-Mandeb/홍해 통항 → Brent·디젤 → 인플레이션·금리",
        "• <b>핵심 한 줄</b> 호르무즈가 막힌 상황에서 우회로까지 멈추면 사우디의 공급 완충장치가 약해져 단순 지정학 뉴스가 실제 세계 원유 공급 차질로 바뀔 수 있음",
    ])
    return lines


def _insert_after_top_summary(body: str, section: list[str]) -> str:
    if not section:
        return body
    block = "\n".join(section)
    if body.startswith("<b>한눈에</b>") and "\n\n" in body:
        head, tail = body.split("\n\n", 1)
        return f"{head}\n\n{block}\n\n{tail}"
    return f"{block}\n\n{body}".strip()


def build_regular_alert_v27(groups, quotes, new_signals, cleared_signals):
    title, body, metadata = _BASE_BUILD(groups, quotes, new_signals, cleared_signals)
    section = _bypass_section(groups, quotes)
    if section:
        title = "🚨 호르무즈 우회망·사우디 송유관 공급경보"
        body = _insert_after_top_summary(body, section)
    metadata["version"] = 27
    metadata["hormuz_bypass_watch"] = {
        "target": "bypass infrastructure state changes, not specific articles",
        "stages": ["attack/damage", "capacity loss", "shutdown", "restart", "full restoration"],
        "assets": ["Saudi East-West Pipeline/Petroline", "Yanbu export buffer", "Red Sea/Bab el-Mandeb", "UAE Fujairah bypass route"],
        "dedupe": "same stage weekly bucket; stage transitions alert separately",
    }
    return title, body, metadata


def build_setup_test_v27(quotes):
    title, body, metadata = _BASE_SETUP(quotes)
    title = "✅ 호르무즈 우회 원유수송망 감시 v27 적용"
    body += (
        "\n\n<b>호르무즈 우회망 감시</b>"
        "\n• 특정 기사 대신 송유관 공격 → 용량축소 → 가동중단 → 재가동 → 정상복구의 상태변화를 추적"
        "\n• 사우디 동서 송유관·얀부 재고·UAE 후자이라 우회망·홍해/Bab el-Mandeb를 함께 확인"
        "\n• 가동중단은 실제 피해와 수리기간을 분리하고, 복구 단계가 바뀔 때만 새 알림"
    )
    metadata["version"] = 27
    return title, body, metadata


core.confirmed_news_groups = confirmed_news_groups_v27
core.build_regular_alert = build_regular_alert_v27
core.build_setup_test = build_setup_test_v27

if __name__ == "__main__":
    raise SystemExit(core.main())
