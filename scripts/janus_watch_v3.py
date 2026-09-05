#!/usr/bin/env python3
import sys
from functools import lru_cache

import requests

import janus_watch_v2 as j2

# DOE Advanced Nuclear 2025 Liftoff benchmark:
# best-practice FOAK overnight capital cost ~ $6,200/kW,
# recent U.S. projects > $10,000/kW, and mature NOAK ~ $3,600/kW.
# For alert readability we use a conservative FOAK range of $6,000-$10,000/kW
# and show the mature NOAK benchmark separately. These are NOT NYPA's official budget.
FOAK_LOW_USD_PER_KW = 6000
FOAK_HIGH_USD_PER_KW = 10000
NOAK_USD_PER_KW = 3600
NY_TARGET_KW = 5_000_000


@lru_cache(maxsize=1)
def _usdkrw_rate():
    """Fetch a live/recent USD/KRW rate from public FX APIs. Return (rate, source)."""
    errors = []
    try:
        r = requests.get(
            "https://api.frankfurter.app/latest",
            params={"from": "USD", "to": "KRW"},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        rate = float((data.get("rates") or {}).get("KRW"))
        if rate > 0:
            return rate, "Frankfurter API"
    except Exception as exc:
        errors.append(f"Frankfurter={exc}")

    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=15)
        r.raise_for_status()
        data = r.json()
        rate = float((data.get("rates") or {}).get("KRW"))
        if rate > 0:
            return rate, "ExchangeRate-API"
    except Exception as exc:
        errors.append(f"ExchangeRate-API={exc}")

    j2._append_error("USD/KRW 환율 API 조회 실패 | " + "; ".join(errors))
    return None, ""


def _format_krw(amount_krw):
    amount = int(round(amount_krw))
    jo = amount // 1_000_000_000_000
    rem = amount % 1_000_000_000_000
    eok = int(round(rem / 100_000_000))
    if eok >= 10000:
        jo += 1
        eok = 0
    if jo and eok:
        return f"약 {jo}조{eok:,}억원"
    if jo:
        return f"약 {jo}조원"
    return f"약 {eok:,}억원"


def _format_usd_billion(amount_usd):
    return f"{amount_usd / 1_000_000_000:.0f}억달러"


def _ny_cost_lines():
    low_usd = NY_TARGET_KW * FOAK_LOW_USD_PER_KW
    high_usd = NY_TARGET_KW * FOAK_HIGH_USD_PER_KW
    noak_usd = NY_TARGET_KW * NOAK_USD_PER_KW
    rate, source = _usdkrw_rate()

    if rate:
        initial = (
            f"{_format_usd_billion(low_usd)}~{_format_usd_billion(high_usd)} "
            f"≈ {_format_krw(low_usd * rate)}~{_format_krw(high_usd * rate).replace('약 ', '')}"
        )
        mature = f"{_format_usd_billion(noak_usd)} ≈ {_format_krw(noak_usd * rate)}"
        fx_note = f"환율 {rate:,.2f}원/달러 · {source}"
    else:
        initial = f"{_format_usd_billion(low_usd)}~{_format_usd_billion(high_usd)}"
        mature = _format_usd_billion(noak_usd)
        fx_note = "환율 API 일시 실패로 원화 환산 보류"
    return initial, mature, fx_note


_ORIGINAL_HIGHLIGHTS = j2._macro_highlights
_ORIGINAL_BOTTLENECKS = j2._bottleneck_lines
_ORIGINAL_NEXT_CHECK = j2._next_check


def _macro_highlights_with_cost(event):
    slug = j2.urlparse(event.get("url", "")).path.rstrip("/").split("/")[-1].lower()
    if slug == "new-york-big-new-bet-on-nuclear-energy":
        initial, mature, _ = _ny_cost_lines()
        return [
            ("신규 원전 목표", "5GW"),
            ("NYPA 역할", "최소 1GW 우선 개발"),
            ("초기 건설비 추산", initial),
            ("반복 건설 성숙 시", mature),
            ("설계 표준화", "온타리오와 1~2개 원자로 설계"),
            ("지역 협력", "뉴잉글랜드 6개주까지 확대"),
        ]
    return _ORIGINAL_HIGHLIGHTS(event)


def _bottleneck_lines_with_cost(event):
    slug = j2.urlparse(event.get("url", "")).path.rstrip("/").split("/")[-1].lower()
    if slug == "new-york-big-new-bet-on-nuclear-energy":
        _, _, fx_note = _ny_cost_lines()
        return [
            "비용 수치는 뉴욕주의 확정 예산이 아니라 DOE 원전 자본비용 벤치마크를 5GW에 적용한 추산",
            "초기비용은 6,000~10,000달러/kW, 반복 건설 성숙비용은 3,600달러/kW를 적용",
            "금융비용·송전망·부지·공기 지연 비용은 별도여서 실제 총사업비는 더 커질 수 있음",
            fx_note,
            "기술보다 금융·비용회수 구조가 우선 병목",
            "NYISO 경쟁 전력시장에서는 민간이 장기 건설비 위험을 감당하기 어려움",
            "NYPA의 공공금융·개발 역할이 실제 착공 가능성을 좌우",
        ]
    return _ORIGINAL_BOTTLENECKS(event)


def _next_check_with_cost(event, category):
    slug = j2.urlparse(event.get("url", "")).path.rstrip("/").split("/")[-1].lower()
    if slug == "new-york-big-new-bet-on-nuclear-energy":
        return "NYPA 공식 사업비 · 부지 선정 · 노형 선정 · 금융 구조 · 인허가 · 설계·조달·시공(EPC)·장납기 기자재 발주"
    return _ORIGINAL_NEXT_CHECK(event, category)


# j2._render_alert_korean resolves these names from the j2 module globals at runtime.
j2._macro_highlights = _macro_highlights_with_cost
j2._bottleneck_lines = _bottleneck_lines_with_cost
j2._next_check = _next_check_with_cost

if __name__ == "__main__":
    sys.exit(j2.base.main())
