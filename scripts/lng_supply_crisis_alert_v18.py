#!/usr/bin/env python3
"""LNG 공급·가격 감시 v18: 유럽 저장 충전속도·국가별 병목·TTF/JKM 단위정규화 경쟁판정 추가."""
from __future__ import annotations

import datetime as dt
import html
import re
import urllib.request

import lng_supply_crisis_alert_v2 as core
import lng_supply_crisis_alert_v17 as v17

v16 = v17.v16
v15 = v16.v15
v14 = v15.v14

# 유럽 저장 부족을 단순 저장률이 아니라 '남은 시간 대비 필요한 충전속도'와
# 유럽↔아시아 LNG 카고 가격경쟁까지 연결해 감시한다.
EXTRA_STORAGE_STRESS_QUERIES = (
    ("europe_storage", 'Europe gas storage winter prices above 100 euros MWh LNG competition when:7d'),
    ("europe_storage", 'Europe gas storage Germany Netherlands low storage LNG competition when:7d'),
    ("europe_storage", 'European storage lowest 15 years 65% winter LNG Asia when:7d'),
    ("europe_storage", '유럽 가스 저장 독일 네덜란드 100유로 LNG 조달 경쟁 when:7d'),
)
for item in EXTRA_STORAGE_STRESS_QUERIES:
    if item not in core.NEWS_QUERIES:
        core.NEWS_QUERIES = tuple(core.NEWS_QUERIES) + (item,)

core.TRUSTED_SOURCE_ALIASES = tuple(core.TRUSTED_SOURCE_ALIASES) + (
    "bloomberg", "bloomberg news", "financial times", "wall street journal", "wsj",
)
core.WORSENING_TERMS["europe_storage"] = tuple(core.WORSENING_TERMS["europe_storage"]) + (
    "above 100 euros", "100 euros a megawatt-hour", "€100", "100유로",
    "germany", "netherlands", "독일", "네덜란드", "lowest in 15 years", "15-year low",
)
core.SUBTYPE_TERMS = (
    ("storage_winter_100_eur_risk", ("above 100 euros", "100 euros a megawatt-hour", "€100", "100유로")),
    ("storage_core_country_bottleneck", ("germany", "netherlands", "독일", "네덜란드")),
) + tuple(core.SUBTYPE_TERMS)

# 기존 TTF 50/60/70/80 경보에 100유로/MWh 스트레스 레벨을 추가한다.
if "ttf" in core.PRICE_SPECS:
    _ttf_levels = tuple(float(x) for x in core.PRICE_SPECS["ttf"].get("levels", ()))
    core.PRICE_SPECS["ttf"]["levels"] = tuple(sorted(set(_ttf_levels + (100.0,))))

_base_signal_label = core.signal_label


def signal_label_v18(signal: str, cleared: bool = False) -> str:
    if signal == "ttf_above_100":
        base = "Trading Economics TTF 추종 공개값 100유로/MWh 상회 · 겨울 스트레스 레벨"
        return f"{base} 종료" if cleared else base
    return _base_signal_label(signal, cleared)


def _visible_gie_text() -> str:
    req = urllib.request.Request(
        v15.GIE_URL,
        headers={"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache", "Pragma": "no-cache"},
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        raw = response.read().decode("utf-8", errors="replace")
    raw = re.sub(r"<script\b.*?</script>", " ", raw, flags=re.I | re.S)
    raw = re.sub(r"<style\b.*?</style>", " ", raw, flags=re.I | re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw))).strip()


def _parse_country(text: str, code: str) -> dict[str, float] | None:
    m = re.search(
        rf"\b{re.escape(code)}\s+([+-]?\d+(?:\.\d+)?)\s+([0-9.,]+)\s+TWh\s+stored\s+([0-9.]+)%\s+full",
        text,
        flags=re.I | re.S,
    )
    if not m:
        return None
    return {
        "trend_pp": float(m.group(1)),
        "stored_twh": float(m.group(2).replace(",", "")),
        "fill_pct": float(m.group(3)),
    }


def fetch_gie_storage_v18() -> dict[str, object]:
    gie = dict(v15.fetch_gie_storage())
    text = _visible_gie_text()
    countries: dict[str, dict[str, float]] = {}
    for code, label in (("DE", "독일"), ("NL", "네덜란드"), ("IT", "이탈리아"), ("FR", "프랑스")):
        row = _parse_country(text, code)
        if row:
            row["label"] = label  # type: ignore[index]
            countries[code] = row
    gie["countries"] = countries

    data_date = dt.date.fromisoformat(str(gie["date"]))
    capacity = float(gie["capacity_twh"])
    trend_pp = float(gie["trend_pp"])
    # GIE 홈페이지의 일일 저장률 변화(%p)를 TWh로 환산한 '순증 환산치'.
    # gross injection이 아니며 반올림·출고를 포함한 순변화이므로 알림에서도 그렇게 표시한다.
    net_change_twh = capacity * trend_pp / 100.0
    gie["net_change_twh_est"] = net_change_twh

    horizons = {
        "oct1": dt.date(data_date.year, 10, 1),
        "dec1": dt.date(data_date.year, 12, 1),
    }
    pace: dict[str, dict[str, float | int | None]] = {}
    for target_key, gap in dict(gie["gaps"]).items():
        target_pace: dict[str, float | int | None] = {}
        required = float(gap["required_twh"])
        for horizon_key, horizon_date in horizons.items():
            days = (horizon_date - data_date).days
            target_pace[f"days_to_{horizon_key}"] = max(days, 0)
            target_pace[f"twh_per_day_to_{horizon_key}"] = (required / days) if days > 0 else None
        pace[str(target_key)] = target_pace
    gie["pace"] = pace
    return gie


def _krw_cost_line(gap_twh: float, ttf_eur_mwh: float, target: str) -> str:
    # 1 TWh = 1,000,000 MWh
    eur_cost = gap_twh * 1_000_000.0 * ttf_eur_mwh
    try:
        fx = v14.fetch_verified_fx("EUR")
        krw, krw_label = v14.convert_to_krw(eur_cost, "EUR", fx)
        return (
            f"• <b>{target}% 현재가격 환산비용</b> 약 {eur_cost/1e9:,.2f}십억유로 ({krw_label}) · "
            f"TTF {ttf_eur_mwh:,.2f}유로/MWh 기준 · 1유로={float(fx['rate']):,.2f}원 · {float(fx['timestamp_kst']) if False else fx['timestamp_kst']}"
        )
    except Exception:
        return f"• <b>{target}% 현재가격 환산비용</b> 약 {eur_cost/1e9:,.2f}십억유로 · 원화 환산 보류(환율 검증 실패)"


def _competition_lines(quotes) -> list[str]:
    if "ttf" not in quotes or "jkm" not in quotes:
        return []
    try:
        eur = v14.fetch_verified_fx("EUR")
        usd = v14.fetch_verified_fx("USD")
        eurusd = float(eur["rate"]) / float(usd["rate"])
        # 1 MMBtu = 0.29307107 MWh
        ttf_usd_mmbtu = float(quotes["ttf"].price) * 0.29307107 * eurusd
        jkm = float(quotes["jkm"].price)
        spread_pct = (ttf_usd_mmbtu / jkm - 1.0) * 100.0 if jkm > 0 else 0.0
        if spread_pct > 2.0:
            verdict = "유럽 가격이 아시아보다 높아 유연 LNG 카고의 유럽 유입 유인이 상대적으로 강함"
        elif spread_pct < -2.0:
            verdict = "아시아 가격이 유럽보다 높아 동북아가 유연 LNG 카고 경쟁에서 상대적으로 우위"
        else:
            verdict = "유럽·아시아 가격이 비슷해 작은 운임·항로 변화에도 카고 목적지가 바뀔 수 있는 구간"
        return [
            "<b>유럽 ↔ 아시아 LNG 카고 가격경쟁</b>",
            f"• <b>유럽 TTF 단위정규화</b> {quotes['ttf'].price:,.2f}유로/MWh → 약 <b>{ttf_usd_mmbtu:,.2f}달러/MMBtu</b>",
            f"• <b>아시아 JKM</b> {jkm:,.2f}달러/MMBtu · 유럽-아시아 가격차 <b>{spread_pct:+.1f}%</b>",
            f"• <b>판정</b> {verdict}",
            "• <b>주의</b> TTF와 JKM의 평가시각·상품구조가 다를 수 있어 방향성 경쟁지표로 사용하고 실제 카고 차익거래는 운임·항로·재기화비용까지 확인",
        ]
    except Exception:
        return ["<b>유럽 ↔ 아시아 LNG 카고 가격경쟁</b>", "• 환율/가격 검증 실패로 단위정규화 경쟁판정 보류"]


def build_regular_alert_v18(groups, quotes, new_signals, cleared_signals):
    title, body, metadata = v17.build_regular_alert_v17(groups, quotes, new_signals, cleared_signals)
    storage_groups = [g for g in groups if str(g.get("category")) == "europe_storage"]
    gie = None
    gie_error = None

    if storage_groups:
        try:
            gie = fetch_gie_storage_v18()
            gaps = gie["gaps"]
            pace = gie["pace"]
            net = float(gie["net_change_twh_est"])
            lines = [
                "<b>저장 충전속도·겨울 스트레스 업그레이드</b>",
                f"• <b>현재</b> EU {float(gie['fill_pct']):.2f}% · {float(gie['stored_twh']):.2f}TWh · GIE 일일 저장률 변화 {float(gie['trend_pp']):+.2f}%p ≈ <b>{net:+.2f}TWh 순증 환산</b>",
                "• <b>기사값과 현재값 분리</b> ‘100TWh 이상·70억유로’는 9월 3일 당시 계산. 알림은 매 실행마다 GIE 최신값으로 부족분을 다시 계산",
            ]
            for target in ("75", "80", "90"):
                gap = float(gaps[target]["required_twh"])
                p_oct = pace[target]["twh_per_day_to_oct1"]
                p_dec = pace[target]["twh_per_day_to_dec1"]
                lines.append(
                    f"• <b>{target}%</b>까지 {gap:.1f}TWh 부족 · 10/1까지 단순 균등충전 {float(p_oct):.2f}TWh/일 · 12/1까지 {float(p_dec):.2f}TWh/일"
                )

            countries = dict(gie.get("countries") or {})
            if countries:
                country_bits = []
                for code in ("DE", "NL", "IT", "FR"):
                    row = countries.get(code)
                    if row:
                        country_bits.append(f"{row['label']} {float(row['fill_pct']):.2f}%")
                if country_bits:
                    lines.append("• <b>국가별 병목</b> " + " · ".join(country_bits))
                    weak = [str(row["label"]) for row in countries.values() if float(row["fill_pct"]) < 60.0]
                    if weak:
                        lines.append("• <b>취약국가</b> " + "·".join(weak) + " 저장률 60% 미만 · EU 평균만 보면 가려지는 지역 병목")

            if "ttf" in quotes:
                ttf = float(quotes["ttf"].price)
                lines.append(_krw_cost_line(float(gaps["75"]["required_twh"]), ttf, "75"))
                lines.append(_krw_cost_line(float(gaps["80"]["required_twh"]), ttf, "80"))
                if ttf >= 100.0:
                    lines.append("• <b>가격 경보</b> TTF 100유로/MWh 상회 · 분석기관들이 경고한 겨울 스트레스 구간 진입")
                else:
                    lines.append("• <b>100유로 스트레스선</b> 아직 미진입 · 저장 부족/공급 차질이 지속되면 재평가")

            lines.extend(_competition_lines(quotes))
            lines.extend([
                "• <b>속도 판정 주의</b> 위 TWh/일은 현재 부족분을 남은 날짜로 나눈 단순 필요속도. 실제 주입능력·출고·기온·수요는 별도라 ‘달성 확정’으로 해석하지 않음",
                "• <b>다음 확인</b> GIE 순증 속도 3~5일 이동평균 → 독일/네덜란드 저장률 → TTF 80·100유로 → JKM → 유럽/아시아 단위정규화 가격차 → LNG 카고 목적지 변경 → 한국 현물입찰",
            ])
            body += "\n\n" + "\n".join(lines)
        except Exception as exc:
            gie_error = f"{type(exc).__name__}: {exc}"
            body += "\n\n<b>저장 충전속도·겨울 스트레스</b>\n• GIE 최신값 재검증 실패 · 속도/국가별 병목 계산 보류"

    metadata["version"] = 18
    metadata["europe_storage_pace_watch"] = {
        "gie": gie,
        "gie_error": gie_error,
        "compliance_window": "EU 90% filling target may be met at any point between Oct 1 and Dec 1; flexibilities are treated separately",
        "pace_method": "remaining TWh divided by days; simple equal-fill pace, not a forecast",
        "core_countries": ["DE", "NL", "IT", "FR"],
        "ttf_stress_levels_eur_mwh": [80, 100],
        "unit_normalization": "TTF EUR/MWh -> USD/MMBtu using 1 MMBtu=0.29307107 MWh and verified FX; compared with JKM USD/MMBtu",
    }
    return title, body, metadata


def build_setup_test_v18(quotes):
    title, body, metadata = v17.build_setup_test_v17(quotes)
    title = "✅ LNG·유럽 겨울 저장 스트레스 감시 v18 적용"
    body += (
        "\n\n<b>유럽 겨울 저장 스트레스</b>"
        "\n• GIE 최신 저장률/TWh를 매번 다시 조회하고 기사 시점 숫자와 분리"
        "\n• 75·80·90% 부족분을 10/1·12/1 기준 단순 필요 충전속도(TWh/일)로 계산"
        "\n• 독일·네덜란드·이탈리아·프랑스 저장률을 함께 보여 EU 평균에 가려진 병목 감시"
        "\n• TTF 100유로/MWh 스트레스 경보 추가"
        "\n• TTF를 USD/MMBtu로 환산해 JKM과 동일 단위로 비교하고 유럽↔아시아 카고 경쟁 방향 판정"
        "\n• 현재 부족분×TTF로 조달비용을 재계산하고 검증된 환율로 원화 환산"
    )
    metadata["version"] = 18
    return title, body, metadata


core.signal_label = signal_label_v18
core.build_regular_alert = build_regular_alert_v18
core.build_setup_test = build_setup_test_v18

if __name__ == "__main__":
    raise SystemExit(core.main())
