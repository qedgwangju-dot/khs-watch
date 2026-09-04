#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import html
import re
import urllib.request

import lng_supply_crisis_alert_v2 as core
import lng_supply_crisis_alert_v14 as v14

UTC = dt.timezone.utc
GIE_URL = "https://www.gie.eu/"

# 유럽 저장량 부족 + 아시아와의 LNG 카고 경쟁 + 겨울 가격 리스크를 별도 조기 경보 축으로 강화한다.
EXTRA_STORAGE_QUERIES = (
    ("europe_storage", '"Europe gas storage" LNG competition winter prices when:3d'),
    ("europe_storage", '"EU gas storage" 75% 80% 90% target LNG cargo competition when:7d'),
    ("europe_storage", '"100 TWh" Europe gas storage LNG when:7d'),
    ("europe_storage", 'Europe gas storage "global scramble" LNG Asia winter when:7d'),
    ("europe_storage", '유럽 가스 저장량 LNG 조달 경쟁 겨울 가격 when:7d'),
)

# 알래스카 LNG의 정책 발언뿐 아니라 실제 국내 기업 수혜 연결고리도 별도 사건으로 포착한다.
# 같은 날 대통령 발언이 먼저 나왔더라도 포스코/강재/강관 관련 후속 구체화가 나오면 별도 알림할 수 있게 한다.
EXTRA_ALASKA_BENEFICIARY_QUERIES = (
    ("alaska_lng", '"Alaska LNG" POSCO steel supply pipeline FID when:7d'),
    ("alaska_lng", '"Alaska LNG" POSCO International steel pipeline 42-inch when:7d'),
    ("alaska_lng", '알래스카 LNG 포스코 강관재 철강재 공급 FID 발주 when:7d'),
    ("alaska_lng", '알래스카 LNG 강관 철강 수혜 포스코인터내셔널 when:3d'),
)

for item in EXTRA_STORAGE_QUERIES + EXTRA_ALASKA_BENEFICIARY_QUERIES:
    if item not in core.NEWS_QUERIES:
        core.NEWS_QUERIES = tuple(core.NEWS_QUERIES) + (item,)

core.TRUSTED_SOURCE_ALIASES = tuple(core.TRUSTED_SOURCE_ALIASES) + (
    "kpler", "goldman sachs", "rystad energy", "morningstar", "jin10", "jin10 data",
    "金十数据", "gate news", "gate.com",
    "시사저널e", "sisajournal e", "sisajournal-e", "페로타임즈", "ferrotimes",
    "서울경제", "seoul economic daily",
)

core.WORSENING_TERMS["europe_storage"] = tuple(core.WORSENING_TERMS["europe_storage"]) + (
    "global scramble", "fuel scramble", "lng competition", "cargo competition",
    "winter price rise", "winter prices rise", "price surge", "storage gap",
    "refill gap", "refilling gap", "100 twh", "75%", "80%", "90%",
    "lowest", "record low", "insufficient storage", "short of target",
    "글로벌 조달 경쟁", "연료 쟁탈전", "lng 경쟁", "카고 경쟁", "겨울 가격 상승",
    "저장량 부족", "비축 부족", "재충전 부족", "저장 목표 미달",
)
core.EASING_TERMS["europe_storage"] = tuple(core.EASING_TERMS["europe_storage"]) + (
    "injections accelerate", "refill accelerates", "storage target achieved",
    "lng competition eases", "cargo competition eases", "재고 보충 가속",
    "저장 목표 달성", "조달 경쟁 완화",
)

# 알래스카 LNG 기업 수혜 연결을 정책 발언과 다른 subtype으로 분리해 중복방지 키가 뭉개지지 않게 한다.
core.EASING_TERMS["alaska_lng"] = tuple(core.EASING_TERMS["alaska_lng"]) + (
    "steel supply", "supply steel", "pipeline steel", "line pipe", "posco",
    "강관재 공급", "철강재 공급", "강재 공급", "공급 기대", "수혜 기대", "포스코",
)
core.SUBTYPE_TERMS = (
    ("alaska_beneficiary_chain", (
        "posco", "포스코", "steel supply", "pipeline steel", "line pipe",
        "강관재", "철강재", "강재 공급", "강관사", "강관주", "수혜 기대",
    )),
    ("storage_lng_competition", ("global scramble", "fuel scramble", "lng competition", "cargo competition", "연료 쟁탈전", "조달 경쟁")),
    ("storage_refill_gap", ("100 twh", "75%", "80%", "90%", "storage gap", "refill gap", "목표 미달", "저장량 부족")),
) + tuple(core.SUBTYPE_TERMS)

EARLY_STORAGE_SOURCES = (
    "reuters", "bloomberg", "financial times", "wall street journal", "the wall street journal",
    "cnbc", "kpler", "goldman sachs", "rystad energy", "morningstar", "jin10", "jin10 data",
    "金十数据", "gate news", "gate.com",
)

EARLY_ALASKA_BENEFICIARY_SOURCES = (
    "reuters", "bloomberg", "financial times", "연합뉴스", "한국경제", "korea economic daily",
    "시사저널e", "sisajournal e", "sisajournal-e", "페로타임즈", "ferrotimes",
    "서울경제", "seoul economic daily", "glenfarne", "agdc", "alaska gasline development corporation",
)


def fetch_gie_storage() -> dict[str, object]:
    req = urllib.request.Request(
        GIE_URL,
        headers={"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache"},
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        raw = response.read().decode("utf-8", errors="replace")
    raw = re.sub(r"<script\b.*?</script>", " ", raw, flags=re.I | re.S)
    raw = re.sub(r"<style\b.*?</style>", " ", raw, flags=re.I | re.S)
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    text = re.sub(r"\s+", " ", text).strip()

    match = re.search(
        r"Status on\s+(\d{2}/\d{2}/\d{4})\s+at\s+6AM\s+CEST.*?\bEU\s+([+-]?\d+(?:\.\d+)?)\s+([0-9.,]+)\s+TWh\s+stored\s+([0-9.]+)%\s+full",
        text,
        flags=re.I | re.S,
    )
    if not match:
        raise RuntimeError("GIE EU storage summary parse failed")

    data_date = dt.datetime.strptime(match.group(1), "%d/%m/%Y").date()
    trend_pp = float(match.group(2))
    stored_twh = float(match.group(3).replace(",", ""))
    fill_pct = float(match.group(4))
    if not (0 < fill_pct <= 120 and stored_twh > 0):
        raise RuntimeError("GIE EU storage values invalid")

    age_days = (dt.datetime.now(UTC).date() - data_date).days
    if age_days < 0 or age_days > 5:
        raise RuntimeError(f"GIE storage stale: {age_days} days")

    capacity_twh = stored_twh / (fill_pct / 100.0)
    gaps = {}
    for target in (75.0, 80.0, 90.0):
        gaps[str(int(target))] = {
            "target_pct": target,
            "gap_pp": max(0.0, target - fill_pct),
            "required_twh": max(0.0, capacity_twh * target / 100.0 - stored_twh),
        }
    return {
        "date": data_date.isoformat(),
        "trend_pp": trend_pp,
        "stored_twh": stored_twh,
        "fill_pct": fill_pct,
        "capacity_twh": capacity_twh,
        "gaps": gaps,
        "source": "Gas Infrastructure Europe (GIE/AGSI+) official summary",
    }


def confirmed_news_groups_v15(items: list[core.NewsItem]):
    confirmed = v14.v13.v12.confirmed_news_groups_v12(items)
    existing_ids = {str(group.get("event_id")) for group in confirmed}

    try:
        gie = fetch_gie_storage()
    except Exception:
        gie = None

    # 유럽 저장 부족은 주요 매체/분석기관 1곳 + GIE 공식 저장량 자체가 부족한 경우 조기신호를 허용한다.
    if gie and float(gie["fill_pct"]) < 80.0:
        for item in sorted(items, key=lambda value: value.published_epoch, reverse=True):
            if item.category != "europe_storage" or item.event_id in existing_ids:
                continue
            if not (item.official or core.source_matches(item.source, EARLY_STORAGE_SOURCES)):
                continue
            confirmed.append(
                {
                    "category": item.category,
                    "polarity": item.polarity,
                    "subtype": item.subtype,
                    "event_id": item.event_id,
                    "latest_epoch": item.published_epoch,
                    "evidence": [item],
                    "verification": "유럽 저장부족 조기신호 + GIE 공식 재고 검산",
                }
            )
            existing_ids.add(item.event_id)

    # 포스코/강재/강관 등 국내 기업 수혜 연결은 아침 정책발언과 별개의 투자정보다.
    # 주요 산업매체 1곳만 먼저 잡혀도 '기업 수혜 연결 조기신호'로 보내되 실제 발주·매출 확정으로 표현하지 않는다.
    for item in sorted(items, key=lambda value: value.published_epoch, reverse=True):
        if item.category != "alaska_lng" or item.subtype != "alaska_beneficiary_chain":
            continue
        if item.event_id in existing_ids:
            continue
        if not (item.official or core.source_matches(item.source, EARLY_ALASKA_BENEFICIARY_SOURCES)):
            continue
        confirmed.append(
            {
                "category": item.category,
                "polarity": item.polarity,
                "subtype": item.subtype,
                "event_id": item.event_id,
                "latest_epoch": item.published_epoch,
                "evidence": [item],
                "verification": "기업 수혜 연결 조기신호 · 공식 파트너십 기준선과 분리 판정",
            }
        )
        existing_ids.add(item.event_id)

    confirmed.sort(key=lambda group: float(group["latest_epoch"]), reverse=True)
    return confirmed


def _append_alaska_beneficiary_section(body: str, groups: list[dict[str, object]]) -> str:
    beneficiary_groups = [
        group for group in groups
        if str(group.get("category")) == "alaska_lng" and str(group.get("subtype")) == "alaska_beneficiary_chain"
    ]
    if not beneficiary_groups:
        return body

    lines = [
        "<b>기업 수혜 연결</b>",
        "• <b>포스코인터내셔널</b> 글렌파른과 알래스카 LNG 전략적 파트너십 · 연 <b>100만t</b> LNG를 <b>20년</b> 구매하는 기본합의서(HOA)와 FID 이전 투자 구조",
        "• <b>포스코</b> 알래스카 LNG의 약 1,300㎞·42인치 파이프라인 제작에 필요한 강재의 상당 부분을 공급하기로 한 공식 파트너십 기준선 존재",
        "• <b>최근 공식 파이프 제작 구조</b> 코린트 파이프웍스·유로파이프가 라인파이프 공급사로 조건부 선정됐고, 포스코는 파이프 제작용 강재 일부를 공급하는 구조",
        "• <b>보도 추정치</b> 포스코 철강재 약 <b>30만t</b> 공급 가능성이 거론되지만 <b>확정 발주 물량은 아님</b>",
        "• <b>국내 강관주</b> 정책 기대감에 주가가 반응할 수 있으나 국내 강관사의 실제 제작·수주가 확인된 것은 아니므로 <b>테마 수혜와 실적 수혜를 분리</b>",
        "• <b>다음 확인</b> Phase 1 FID → EPC·라인파이프 최종계약 → 포스코 강재 물량·납기 확정 → 국내 강관사 실제 참여 여부 → LNG 터미널·수출 Phase 2 FID",
    ]
    return body + "\n\n" + "\n".join(lines)


def build_regular_alert_v15(groups, quotes, new_signals, cleared_signals):
    title, body, metadata = v14.build_regular_alert_v14(groups, quotes, new_signals, cleared_signals)
    storage_groups = [group for group in groups if str(group.get("category")) == "europe_storage"]
    gie = None
    gie_error = None

    if storage_groups:
        title = "⚠️ LNG·유럽 가스 재고 변화 감지"
        try:
            gie = fetch_gie_storage()
            gaps = gie["gaps"]
            lines = [
                "<b>유럽 저장량·글로벌 LNG 경쟁</b>",
                f"• <b>GIE 공식 재고</b> <b>{gie['fill_pct']:.2f}%</b> · {gie['stored_twh']:.2f}TWh · 일일 변화 {gie['trend_pp']:+.2f}%p · 기준 {gie['date']}",
                f"• <b>75% 하단</b>까지 +{gaps['75']['gap_pp']:.2f}%p · 약 <b>{gaps['75']['required_twh']:.1f}TWh</b> 추가 필요",
                f"• <b>80% 유연 목표</b>까지 +{gaps['80']['gap_pp']:.2f}%p · 약 <b>{gaps['80']['required_twh']:.1f}TWh</b> 추가 필요",
                f"• <b>90% 기본 목표</b>까지 +{gaps['90']['gap_pp']:.2f}%p · 약 <b>{gaps['90']['required_twh']:.1f}TWh</b> 추가 필요",
                "• <b>규정 구분</b> EU 기본 목표는 90% · 어려운 시장 여건에서는 10%p 이탈(80%) 가능 · 지속적 불리한 여건이면 추가 5%p 유연성으로 75%까지 가능",
                "• <b>핵심 해석</b> 75%는 평상시 기본 목표가 아니라 최대 유연성 적용 시 하단으로 구분",
            ]

            if "ttf" in quotes:
                lines.append(f"• <b>가격 연결</b> {core.format_quote(quotes['ttf'])}")

            evidence_text = " ".join(
                f"{item.title} {item.source}"
                for group in storage_groups
                for item in group.get("evidence", [])
            ).lower()
            if any(token in evidence_text for token in ("jin10", "金十", "gate")):
                try:
                    eur = v14.fetch_verified_fx("EUR")
                    krw_value, krw_label = v14.convert_to_krw(7_000_000_000.0, "EUR", eur)
                    rate = float(eur["rate"])
                    lines.append(
                        f"• <b>시장 추산 비용</b> 70억유로 ({krw_label}) · 1유로={rate:,.2f}원 · 70억×{rate:,.2f}원={krw_value:,.0f}원 · 기준 {eur['timestamp_kst']}"
                    )
                except Exception:
                    lines.append("• <b>시장 추산 비용</b> 70억유로 · 원화 환산 보류(환율 검증 실패)")

            lines.extend(
                [
                    "• <b>한국 영향</b> 유럽이 저장 목표를 맞추기 위해 현물 LNG 가격을 높이면 동북아와 같은 유연 카고를 두고 경쟁 · JKM·한국 현물 조달 프리미엄 상승 위험",
                    "• <b>투자 연결</b> LNG 판매자·미국/비호르무즈 공급원 우위 가능 · 한국 가스발전·도시가스·전력 원가에는 부담 · TTF-JKM 스프레드와 카고 목적지 전환 확인",
                    "• <b>다음 확인</b> GIE 저장률·일일 주입속도 → TTF/JKM → 유럽-아시아 차익거래 → 카타르/호르무즈 공급 → 한·일 현물 입찰",
                ]
            )
            body += "\n\n" + "\n".join(lines)
        except Exception as exc:
            gie_error = f"{type(exc).__name__}: {exc}"
            body += "\n\n<b>유럽 저장량</b>\n• GIE 공식 수치 검증 실패 · 저장량 숫자 판정 보류"

    body = _append_alaska_beneficiary_section(body, groups)

    metadata["version"] = 15
    metadata["europe_storage_watch"] = {
        "thresholds": [75, 80, 90],
        "legal_note": "90% base; up to 10pp deviation in difficult conditions; Commission may add 5pp in persistent adverse conditions",
        "required_fields": ["GIE 저장률", "TWh", "목표별 갭", "주입속도", "TTF", "유럽-아시아 LNG 경쟁", "한국 영향"],
        "gie": gie,
        "gie_error": gie_error,
    }
    metadata["alaska_beneficiary_watch"] = {
        "subtype": "alaska_beneficiary_chain",
        "direct": ["포스코인터내셔널 전략적 파트너십", "포스코 파이프 제작용 강재 공급"],
        "thematic_only_until_order": ["국내 강관사/철강주"],
        "required_next_checks": ["Phase 1 FID", "EPC/라인파이프 최종계약", "포스코 물량·납기", "국내 강관사 실제 수주", "Phase 2 FID"],
    }
    return title, body, metadata


def build_setup_test_v15(quotes):
    title, body, metadata = v14.build_setup_test_v14(quotes)
    title = "✅ LNG·유럽 가스 재고 경쟁 감시 v15 적용"
    body += (
        "\n\n<b>유럽 저장량·글로벌 LNG 경쟁</b>"
        "\n• GIE 공식 EU 저장률/TWh와 75·80·90% 목표별 부족분을 계산"
        "\n• 75%는 기본 목표가 아니라 최대 유연성 적용 시 하단으로 구분"
        "\n• 유럽의 재고 보충과 아시아 LNG 카고 경쟁·TTF/JKM·한국 현물조달 영향을 함께 표시"
        "\n• 저장 부족 주요 보도 1곳 + GIE 공식 재고 검산이면 조기신호 허용"
        "\n\n<b>알래스카 LNG 기업 수혜 연결</b>"
        "\n• 대통령 정책 발언과 포스코/강재/강관의 기업 수혜 구체화를 별도 사건으로 감지"
        "\n• 포스코 직접 연결과 국내 강관주 테마 기대를 분리"
        "\n• 30만t은 공급 가능 추정치로 표시하고 확정 발주로 과장하지 않음"
        "\n• 확인 순서: Phase 1 FID → 최종 발주 → 포스코 물량/납기 → 국내 강관사 실제 참여 → Phase 2 FID"
    )
    metadata["version"] = 15
    return title, body, metadata


core.confirmed_news_groups = confirmed_news_groups_v15
core.build_regular_alert = build_regular_alert_v15
core.build_setup_test = build_setup_test_v15

if __name__ == "__main__":
    raise SystemExit(core.main())
