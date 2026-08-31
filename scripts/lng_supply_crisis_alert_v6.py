#!/usr/bin/env python3
"""LNG 공급 위기 감시 v6.

정확도 보강:
1) TTF는 사용자가 지정한 Trading Economics 한국 페이지를 기준 원천으로 사용한다.
2) 한국 페이지 내부 actual/previous/등락률 일치 + 기준일 신선도 + 다른 TE 지역 페이지 1곳 이상 일치를 요구한다.
3) 영어 페이지 하나가 캐시 지연이면 한국 페이지를 버리지 않고 독일/터키 페이지로 재검증한다.
4) 호르무즈 군사충돌·기뢰·로켓·Larak 관련 뉴스 쿼리와 분류어를 확대한다.
"""

from __future__ import annotations

import datetime as dt
import re

import lng_supply_crisis_alert_v2 as core
import lng_supply_crisis_alert_v3 as strict
import lng_supply_crisis_alert_v4 as te
import lng_supply_crisis_alert_v5 as v5

TTF_SUPPORT_URLS = (
    "https://tradingeconomics.com/commodity/eu-natural-gas",
    "https://de.tradingeconomics.com/commodity/eu-natural-gas",
    "https://tr.tradingeconomics.com/commodity/eu-natural-gas",
)
TTF_SUPPORT_PRICE_TOL_PCT = 0.20
TTF_SUPPORT_PREVIOUS_TOL_PCT = 0.20
TTF_MAX_SOURCE_AGE_DAYS = 3

EXTRA_NEWS_QUERIES = (
    ("hormuz_shipping", '"Strait of Hormuz" Iran attack strike rocket mine when:2d'),
    ("hormuz_shipping", '"Larak Island" Hormuz Iran attack strike when:2d'),
    ("hormuz_shipping", 'Hormuz Iran US attack oil LNG shipping when:2d'),
)

# 기존 검색에 현재 군사 충돌 축을 추가한다.
core.NEWS_QUERIES = tuple(core.NEWS_QUERIES) + EXTRA_NEWS_QUERIES

# Reuters/AP/WSJ의 서로 다른 제목이 같은 '군사적 악화' 사건으로 묶이도록 공통 subtype을 최우선 적용한다.
core.SUBTYPE_TERMS = (
    (
        "military_escalation",
        (
            "attack", "attacks", "strike", "strikes", "struck", "fighting",
            "rocket", "rockets", "launcher", "launchers", "sea mine", "sea mines",
            "mine-laden", "larak", "공격", "타격", "교전", "로켓", "기뢰",
        ),
    ),
) + tuple(core.SUBTYPE_TERMS)

core.WORSENING_TERMS["hormuz_shipping"] = tuple(core.WORSENING_TERMS["hormuz_shipping"]) + (
    "strike", "strikes", "struck", "fighting", "rocket", "rockets",
    "launcher", "launchers", "sea mine", "sea mines", "mine-laden", "larak",
    "타격", "교전", "로켓", "기뢰",
)


def _pct_gap(a: float, b: float) -> float:
    return abs(a / b - 1.0) * 100.0 if b else 999.0


def _validate_source_date(source_date: str) -> None:
    parsed = dt.date.fromisoformat(source_date)
    today = core.now_utc().astimezone(core.KST).date()
    age_days = (today - parsed).days
    if age_days < 0 or age_days > TTF_MAX_SOURCE_AGE_DAYS:
        raise RuntimeError(
            f"Trading Economics TTF 기준일이 오래됐거나 미래임: {source_date}, age={age_days}d"
        )


def fetch_te_ttf_quote_v6() -> core.Quote:
    raw_ko = te.fetch_te_html(te.TE_TTF_URLS[0])
    primary = te.parse_te_ttf(raw_ko)
    source_date = v5.parse_te_korean_source_date(raw_ko)
    _validate_source_date(source_date)

    # parse_te_ttf 자체가 한국 페이지 내부 actual/previous/표시 등락률 일치를 검증한다.
    corroborations: list[str] = []
    mismatches: list[str] = []
    for url in TTF_SUPPORT_URLS:
        try:
            candidate = te.parse_te_ttf(te.fetch_te_html(url))
        except Exception as exc:
            mismatches.append(f"{url}:parse:{type(exc).__name__}")
            continue

        price_gap = _pct_gap(candidate["actual"], primary["actual"])
        previous_gap = _pct_gap(candidate["previous"], primary["previous"])
        if (
            price_gap <= TTF_SUPPORT_PRICE_TOL_PCT
            and previous_gap <= TTF_SUPPORT_PREVIOUS_TOL_PCT
        ):
            corroborations.append(url)
        else:
            mismatches.append(
                f"{url}:actual={candidate['actual']},previous={candidate['previous']}"
            )

    if not corroborations:
        raise RuntimeError(
            "Trading Economics 한국 페이지 값을 다른 지역 페이지에서 재검증하지 못함; "
            + "; ".join(mismatches[:3])
        )

    observed = core.now_utc()
    price = float(primary["actual"])
    previous = float(primary["previous"])
    return core.Quote(
        key="ttf",
        symbol="TE:EU-GAS",
        label="Trading Economics EU Gas(TTF 추종 공개값)",
        unit="유로/MWh",
        price=price,
        previous_close=previous,
        change_pct=(price / previous - 1.0) * 100.0,
        timestamp_epoch=observed.timestamp(),
        timestamp_utc=observed.isoformat(timespec="seconds"),
        age_minutes=0,
        source_note=(
            "사용자 지정 Trading Economics 한국 페이지 기준; 내부 actual/previous/등락률 검증; "
            f"지역 페이지 재검증={len(corroborations)}곳; 기준일={source_date}"
        ),
    )


def fetch_market_quotes_v6() -> tuple[dict[str, core.Quote], list[str]]:
    quotes: dict[str, core.Quote] = {}
    errors: list[str] = []
    try:
        quotes["ttf"] = fetch_te_ttf_quote_v6()
    except Exception as exc:
        errors.append(f"ttf: {type(exc).__name__}: {exc}")
    try:
        quotes["brent"] = strict.fetch_verified_quote_strict("brent")
    except Exception as exc:
        errors.append(f"brent: {type(exc).__name__}: {exc}")
    return quotes, errors


def format_quote_v6(quote: core.Quote) -> str:
    observed_kst = dt.datetime.fromtimestamp(quote.timestamp_epoch, core.UTC).astimezone(core.KST)
    if quote.key == "ttf":
        match = re.search(r"기준일=(\d{4}-\d{2}-\d{2})", quote.source_note)
        if not match:
            raise RuntimeError("TTF 기준일 없는 값은 출력하지 않음")
        source_date = match.group(1)
        return (
            f"{quote.label} {quote.price:,.2f}{quote.unit} "
            f"(이전값 {quote.previous_close:,.2f} 대비 {quote.change_pct:+.2f}%, "
            f"기준일 {source_date}, 조회 {observed_kst:%Y-%m-%d %H:%M KST})"
        )
    return te.format_quote_v4(quote)


def build_setup_test_v6(quotes: dict[str, core.Quote]):
    title, body, metadata = v5.build_setup_test_v5(quotes)
    title = "✅ LNG·천연가스 감시 정확도 규칙 v6 적용"
    body += (
        "\n• TTF는 사용자 지정 한국 Trading Economics 페이지를 기준으로 하고 다른 지역 페이지 1곳 이상으로 재검증"
        "\n• 영어 페이지 캐시 지연 하나만으로 한국 기준값을 버리지 않음"
        "\n• 호르무즈 공격·타격·기뢰·로켓·Larak 군사악화 검색을 추가해 Reuters/AP 등 교차 확인"
    )
    metadata["version"] = 6
    metadata["ttf_primary"] = te.TE_TTF_URLS[0]
    metadata["ttf_support_pages"] = list(TTF_SUPPORT_URLS)
    return title, body, metadata


core.fetch_market_quotes = fetch_market_quotes_v6
core.format_quote = format_quote_v6
core.signal_label = te.signal_label_v4
core.build_setup_test = build_setup_test_v6


if __name__ == "__main__":
    raise SystemExit(core.main())
