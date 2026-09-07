#!/usr/bin/env python3
"""LNG 공급·가격 감시 v19: 유럽 국채 매도·ECB 재가격·가스→금리 전이 감시 추가."""
from __future__ import annotations

import datetime as dt
import html
import re
import time
import urllib.request

import lng_supply_crisis_alert_v2 as core
import lng_supply_crisis_alert_v4 as te
import lng_supply_crisis_alert_v18 as v18

UTC = dt.timezone.utc

# 유럽 가스 충격이 인플레이션 기대와 ECB 경로를 거쳐 장기금리/할인율로 전이되는 축을 별도로 감시한다.
EUROPE_RATES_QUERIES = (
    ("europe_rates", 'European bond selloff Germany Bund yield ECB hike gas inflation when:3d'),
    ("europe_rates", 'Germany 10-year Bund 3.4 ECB rate hike energy prices when:3d'),
    ("europe_rates", 'Bund yields rate-hike prospects energy inflation Europe when:3d'),
    ("europe_rates", 'France Germany bond spread fiscal political risk eurozone when:3d'),
    ("europe_rates", '유럽 국채 매도 독일 10년물 ECB 금리인상 가스 가격 when:3d'),
    ("europe_rates", '유럽 장기금리 미국보다 빠르게 상승 독일 국채 가스 인플레이션 when:7d'),
)
for item in EUROPE_RATES_QUERIES:
    if item not in core.NEWS_QUERIES:
        core.NEWS_QUERIES = tuple(core.NEWS_QUERIES) + (item,)

core.TRUSTED_SOURCE_ALIASES = tuple(core.TRUSTED_SOURCE_ALIASES) + (
    "bundesbank", "deutsche bundesbank", "ecb", "european central bank",
    "marketscreener", "euronews", "associated press", "ap",
)
core.WORSENING_TERMS["europe_rates"] = (
    "bond selloff", "bond sell-off", "bund yields rise", "bund yield rises", "yields rise",
    "yield surge", "multi-year high", "15-year high", "rate-hike prospects", "rate hike prospects",
    "ecb hike", "ecb rate hike", "higher for longer", "fiscal risk", "political risk",
    "spread widens", "france spread", "gas inflation", "energy inflation",
    "국채 매도", "채권 매도", "금리 상승", "장기금리 상승", "15년 최고", "ECB 인상",
    "재정 불안", "정치 불안", "스프레드 확대", "에너지 인플레이션",
)
core.EASING_TERMS["europe_rates"] = (
    "bond rally", "bund yields fall", "yields fall", "yield pullback", "rate hike bets ease",
    "ecb hike bets ease", "spread narrows", "energy prices ease", "채권 강세", "금리 하락",
    "ECB 인상 기대 완화", "스프레드 축소", "에너지 가격 하락",
)
core.SUBTYPE_TERMS = (
    ("europe_rates_energy_ecb", (
        "ecb", "rate hike", "rate-hike", "gas inflation", "energy inflation", "가스", "에너지", "금리인상",
    )),
    ("europe_rates_fiscal_political", (
        "fiscal", "political", "france", "budget", "spread", "재정", "정치", "프랑스", "스프레드",
    )),
    ("europe_rates_bund_selloff", (
        "bond selloff", "bond sell-off", "bund yield", "bund yields", "국채 매도", "장기금리",
    )),
) + tuple(core.SUBTYPE_TERMS)

# 독일/미국 10년물을 bp 단위 Quote로 넣어 기존 임계값 히스테리시스를 재사용한다.
# 예: 3.40% = 340bp. 소수점 레벨이 int()로 뭉개지는 기존 코어 구조를 피하기 위함이다.
core.PRICE_SPECS["bund10"] = {
    "symbol": "DE10Y",
    "label": "독일 10년 Bund",
    "unit": "bp",
    "levels": (330.0, 340.0, 350.0, 375.0),
    "exit_buffer": 3.0,
}
core.PRICE_SPECS["us10"] = {
    "symbol": "US10Y",
    "label": "미국 10년 국채",
    "unit": "bp",
    "levels": (480.0, 500.0, 525.0),
    "exit_buffer": 4.0,
}

TREND_URLS = {
    "bund10": "https://trendonify.com/germany/government-bond-yield",
    "us10": "https://trendonify.com/united-states/government-bond-yield",
}
TE_URLS = {
    "bund10": "https://de.tradingeconomics.com/germany/government-bond-yield",
    "us10": "https://tradingeconomics.com/united-states/government-bond-yield",
}
BOND_MAX_AGE_DAYS = 5
BOND_TE_CROSSCHECK_MAX_GAP_PCT_POINTS = 0.06  # 6bp; 페이지 갱신시각 차이를 넘으면 보류


def _fetch_html(url: str) -> str:
    req = urllib.request.Request(
        f"{url}?v={int(time.time())}",
        headers={
            "User-Agent": "Mozilla/5.0 khs-lng-europe-rates-alert/19.0",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        return response.read().decode("utf-8", errors="replace")


def _visible(raw: str) -> str:
    raw = re.sub(r"(?is)<script\b.*?</script>|<style\b.*?</style>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"(?s)<[^>]+>", " ", raw))).strip()


def _parse_trendonify_bond(raw: str) -> dict[str, object]:
    text = _visible(raw)
    last = re.search(r"Last\s+Updated\s*:\s*(\d{4}-\d{2}-\d{2})", text, flags=re.I)
    current = re.search(r"current\s+yield.*?is\s+([0-9.]+)%", text, flags=re.I)
    if not current:
        current = re.search(r"\b([0-9]+\.[0-9]+)%\s*[+-][0-9.()\s%+-]*Last\s+Updated", text, flags=re.I)
    previous = re.search(r"Previous\s+Value\s+([0-9.]+)%", text, flags=re.I)
    aug4 = re.search(r"Aug\s+4,\s+2026\s+\|?\s*([0-9.]+)%", text, flags=re.I)
    if not (last and current and previous and aug4):
        raise RuntimeError("Trendonify bond current/previous/Aug4/date parse failed")
    data_date = dt.date.fromisoformat(last.group(1))
    age_days = (core.now_utc().astimezone(core.KST).date() - data_date).days
    if age_days < 0 or age_days > BOND_MAX_AGE_DAYS:
        raise RuntimeError(f"Trendonify bond stale date={data_date} age={age_days}d")
    return {
        "date": data_date.isoformat(),
        "current_pct": float(current.group(1)),
        "previous_pct": float(previous.group(1)),
        "aug4_pct": float(aug4.group(1)),
        "age_days": age_days,
    }


def _parse_te_bond_actual(raw: str) -> tuple[float, float]:
    text = te.visible_text(raw)
    patterns = (
        r"Actual\s+Previous\s+Highest\s+Lowest\s+Dates\s+Unit\s+Frequency\s+([0-9.,]+)\s+([0-9.,]+)",
        r"Aktuell\s+Zuletzt\s+Höchste\s+Unterste\s+Termine\s+Einheit\s+Häufigkeit\s+([0-9.,]+)\s+([0-9.,]+)",
    )
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.I)
        if m:
            return te.number(m.group(1)), te.number(m.group(2))
    raise RuntimeError("Trading Economics bond actual/previous parse failed")


def fetch_bond_quote(key: str) -> core.Quote:
    snap = _parse_trendonify_bond(_fetch_html(TREND_URLS[key]))
    te_actual, te_previous = _parse_te_bond_actual(_fetch_html(TE_URLS[key]))
    current = float(snap["current_pct"])
    previous = float(snap["previous_pct"])
    if abs(current - te_actual) > BOND_TE_CROSSCHECK_MAX_GAP_PCT_POINTS:
        raise RuntimeError(
            f"bond cross-source current mismatch key={key} trend={current} TE={te_actual}"
        )
    # 이전값은 소스별 세션 컷이 다를 수 있어 현재값보다 조금 넓게 본다.
    if abs(previous - te_previous) > 0.10:
        raise RuntimeError(
            f"bond cross-source previous mismatch key={key} trend={previous} TE={te_previous}"
        )
    aug4 = float(snap["aug4_pct"])
    delta_aug4_bp = (current - aug4) * 100.0
    observed = core.now_utc()
    return core.Quote(
        key=key,
        symbol=str(core.PRICE_SPECS[key]["symbol"]),
        label=str(core.PRICE_SPECS[key]["label"]),
        unit="bp",
        price=current * 100.0,
        previous_close=previous * 100.0,
        change_pct=(current / previous - 1.0) * 100.0 if previous else 0.0,
        timestamp_epoch=observed.timestamp(),
        timestamp_utc=observed.isoformat(timespec="seconds"),
        age_minutes=0,
        source_note=(
            f"Trendonify current/history + Trading Economics actual cross-check; "
            f"basis_date={snap['date']}; aug4={aug4:.4f}; since_aug4_bp={delta_aug4_bp:+.1f}; "
            f"TE_actual={te_actual:.4f}"
        ),
    )


_base_fetch_market_quotes = core.fetch_market_quotes
_base_apply_hysteresis = core.apply_hysteresis
_base_signal_label = core.signal_label
_base_category_label = core.category_label
_base_context = core.classify_alert_context
_base_impact_text = core.impact_text
_base_confirmed_news_groups = core.confirmed_news_groups
_base_format_quote = core.format_quote


def fetch_market_quotes_v19():
    quotes, errors = _base_fetch_market_quotes()
    for key in ("bund10", "us10"):
        try:
            quotes[key] = fetch_bond_quote(key)
        except Exception as exc:
            errors.append(f"{key}: {type(exc).__name__}: {exc}")
    return quotes, errors


def _aug4_delta_bp(quote: core.Quote) -> float | None:
    m = re.search(r"since_aug4_bp=([+-]?[0-9.]+)", quote.source_note)
    return float(m.group(1)) if m else None


def apply_hysteresis_v19(quotes, previous_signals):
    current = _base_apply_hysteresis(quotes, previous_signals)
    bund = quotes.get("bund10")
    us = quotes.get("us10")
    if bund:
        de = _aug4_delta_bp(bund)
        if de is not None:
            if de >= 20.0:
                current.add("bund10_since_aug4_20bp")
            elif de < 15.0:
                current.discard("bund10_since_aug4_20bp")
            if de >= 30.0:
                current.add("bund10_since_aug4_30bp")
            elif de < 25.0:
                current.discard("bund10_since_aug4_30bp")
    if bund and us:
        de = _aug4_delta_bp(bund)
        usa = _aug4_delta_bp(us)
        if de is not None and usa is not None:
            lead = de - usa
            if lead >= 5.0:
                current.add("bund10_rise_leads_us10_5bp")
            elif lead < 3.0:
                current.discard("bund10_rise_leads_us10_5bp")
    return current


def signal_label_v19(signal: str, cleared: bool = False) -> str:
    labels = {
        "bund10_above_330": "독일 10년 Bund 3.30% 상회",
        "bund10_above_340": "독일 10년 Bund 3.40% 상회",
        "bund10_above_350": "독일 10년 Bund 3.50% 상회",
        "bund10_above_375": "독일 10년 Bund 3.75% 상회",
        "us10_above_480": "미국 10년 국채 4.80% 상회",
        "us10_above_500": "미국 10년 국채 5.00% 상회",
        "us10_above_525": "미국 10년 국채 5.25% 상회",
        "bund10_since_aug4_20bp": "독일 10년 Bund 8월 4일 대비 +20bp 이상",
        "bund10_since_aug4_30bp": "독일 10년 Bund 8월 4일 대비 +30bp 이상",
        "bund10_rise_leads_us10_5bp": "8월 4일 이후 독일 10년 금리 상승폭이 미국 10년보다 +5bp 이상 큼",
        "bund10_up_5": "독일 10년 Bund 일일 수익률 상대변화 +5% 이상",
        "bund10_down_5": "독일 10년 Bund 일일 수익률 상대변화 -5% 이하",
        "us10_up_5": "미국 10년 국채 일일 수익률 상대변화 +5% 이상",
        "us10_down_5": "미국 10년 국채 일일 수익률 상대변화 -5% 이하",
    }
    if signal in labels:
        return f"{labels[signal]} 종료" if cleared else labels[signal]
    return _base_signal_label(signal, cleared)


def format_quote_v19(quote: core.Quote) -> str:
    if quote.key not in ("bund10", "us10"):
        return _base_format_quote(quote)
    basis = re.search(r"basis_date=(\d{4}-\d{2}-\d{2})", quote.source_note)
    aug = re.search(r"aug4=([0-9.]+)", quote.source_note)
    delta = _aug4_delta_bp(quote)
    current_pct = quote.price / 100.0
    previous_pct = quote.previous_close / 100.0
    day_bp = (current_pct - previous_pct) * 100.0
    extra = ""
    if aug and delta is not None:
        extra = f" · 8/4 {float(aug.group(1)):.3f}% 대비 {delta:+.1f}bp"
    return (
        f"{quote.label} <b>{current_pct:.3f}%</b> · 전일 {previous_pct:.3f}% 대비 {day_bp:+.1f}bp"
        f"{extra} · 기준 {basis.group(1) if basis else '미확인'}"
    )


def category_label_v19(category: str) -> str:
    if category == "europe_rates":
        return "유럽 국채·ECB 재가격"
    return _base_category_label(category)


def classify_alert_context_v19(groups, new_signals, cleared_signals):
    rate_groups = [g for g in groups if g.get("category") == "europe_rates"]
    rate_signals = {
        s for s in new_signals
        if s.startswith("bund10_") or s.startswith("us10_")
    }
    if rate_groups or rate_signals:
        worsening = any(g.get("polarity") == "worsening" for g in rate_groups) or bool(rate_signals)
        easing = any(g.get("polarity") == "easing" for g in rate_groups)
        if worsening and not easing:
            return "europe_rates_stress"
        if easing and not worsening:
            return "europe_rates_relief"
        return "europe_rates_mixed"
    return _base_context(groups, new_signals, cleared_signals)


def impact_text_v19(context: str):
    if context == "europe_rates_stress":
        return (
            "유럽 에너지 가격 상승이 단기 인플레이션과 ECB 금리인상 기대를 자극하고, 재정·정치 불안까지 겹치면 유럽 장기금리가 추가 상승할 수 있습니다. 한국에는 직접 LNG 조달비뿐 아니라 글로벌 장기금리·할인율 상승 경로가 추가됩니다.",
            "할인율: 유럽 장기금리 상승이 미국보다 빠르면 글로벌 성장주·장기듀레이션 자산의 밸류에이션 부담이 커질 수 있습니다. 돈 버는 능력: 은행은 금리마진 측면의 일부 수혜가 가능하지만 경기·신용비용 상승을 함께 봐야 하고, 고부채 유틸리티·부동산·인프라는 조달비 부담이 커집니다. 수급·시간표: TTF/Brent → 유로존 단기 인플레이션 기대 → ECB 인상경로 → 독일 2Y/10Y/30Y → 프랑스-독일 스프레드 순으로 확인합니다.",
            "유럽 가스 충격이 채권시장과 할인율로 전이되는 단계인지 확인해야 하며, 독일 금리 상승폭이 미국보다 커지는지가 핵심 비교 신호입니다.",
        )
    if context == "europe_rates_relief":
        return (
            "에너지 가격 또는 ECB 인상 기대가 완화되며 유럽 국채금리가 되돌림을 보이는 신호입니다. 다만 재정·정치 프리미엄이 남아 있으면 금리 하락이 제한될 수 있습니다.",
            "할인율 부담은 완화되지만 TTF·ECB 경로·프랑스 스프레드가 동시에 안정되는지 확인합니다.",
            "유럽 채권 스트레스가 완화되고 있으나 에너지와 재정 리스크의 동시 진정이 최종 확인점입니다.",
        )
    if context == "europe_rates_mixed":
        return (
            "유럽 채권시장의 정책·에너지·재정 신호가 엇갈립니다.",
            "독일 Bund 절대금리와 ECB 기대, 프랑스 스프레드를 분리해 판단합니다.",
            "금리 방향만으로 원인을 단정하지 않고 정책 기대와 재정 프리미엄을 분리합니다.",
        )
    return _base_impact_text(context)


EARLY_RATE_SOURCES = (
    "reuters", "wall street journal", "wsj", "financial times", "bloomberg",
    "bundesbank", "deutsche bundesbank", "ecb", "european central bank", "euronews",
)


def confirmed_news_groups_v19(items: list[core.NewsItem]):
    confirmed = _base_confirmed_news_groups(items)
    existing = {str(g.get("event_id")) for g in confirmed}
    for item in sorted(items, key=lambda x: x.published_epoch, reverse=True):
        if item.category != "europe_rates" or item.event_id in existing:
            continue
        if not (item.official or core.source_matches(item.source, EARLY_RATE_SOURCES)):
            continue
        normalized = core.normalize_text(item.title)
        if not any(token in normalized for token in (
            "bond", "bund", "yield", "ecb", "rate hike", "국채", "금리", "채권"
        )):
            continue
        confirmed.append({
            "category": item.category,
            "polarity": item.polarity,
            "subtype": item.subtype,
            "event_id": item.event_id,
            "latest_epoch": item.published_epoch,
            "evidence": [item],
            "verification": "유럽 금리 조기신호 · 주요 금융매체/공식기관 확인",
        })
        existing.add(item.event_id)
    confirmed.sort(key=lambda g: float(g["latest_epoch"]), reverse=True)
    return confirmed


def build_regular_alert_v19(groups, quotes, new_signals, cleared_signals):
    title, body, metadata = v18.build_regular_alert_v18(groups, quotes, new_signals, cleared_signals)
    rate_groups = [g for g in groups if g.get("category") == "europe_rates"]
    rate_signal_set = {
        s for s in (set(new_signals) | set(cleared_signals))
        if s.startswith("bund10_") or s.startswith("us10_")
    }
    if rate_groups or rate_signal_set:
        title = "⚠️ 유럽 가스·채권금리 스트레스 경보"
        lines = ["<b>가스 → 인플레이션 → ECB → 유럽 장기금리</b>"]
        bund = quotes.get("bund10")
        us = quotes.get("us10")
        if bund:
            lines.append("• <b>독일 10년</b> " + format_quote_v19(bund))
        if us:
            lines.append("• <b>미국 10년 비교</b> " + format_quote_v19(us))
        if bund and us:
            de = _aug4_delta_bp(bund)
            usa = _aug4_delta_bp(us)
            if de is not None and usa is not None:
                lines.append(
                    f"• <b>8/4 이후 상대 매도강도</b> 독일 {de:+.1f}bp vs 미국 {usa:+.1f}bp · 독일이 <b>{de-usa:+.1f}bp</b> 더 상승"
                )
        if "ttf" in quotes:
            lines.append(f"• <b>에너지 연결</b> {core.format_quote(quotes['ttf'])}")
        evidence_text = " ".join(
            f"{item.title} {item.source}" for g in rate_groups for item in g.get("evidence", [])
        ).lower()
        if any(x in evidence_text for x in ("ecb", "rate hike", "rate-hike", "inflation", "gas", "energy")):
            lines.append("• <b>정책 경로</b> 가스·에너지 상승 → 단기 인플레이션 기대 상승 → ECB 인상 기대 강화 → Bund 금리 상승")
        if any(x in evidence_text for x in ("fiscal", "political", "france", "budget", "spread")):
            lines.append("• <b>재정·정치 경로</b> 프랑스/유럽 재정·정치 불확실성 → 기간·국가위험 프리미엄 상승 → 장기물 추가 매도")
        lines.extend([
            "• <b>분리 판정</b> Bund 금리 상승을 전부 가스 탓으로 단정하지 않음. ECB 정책기대와 재정·정치/기간프리미엄을 별도 원인으로 표시",
            "• <b>핵심 임계값</b> 독일 10년 3.30% → 3.40% → 3.50% → 3.75% · 8/4 대비 +20/+30bp · 미국보다 상승폭 +5bp 이상",
            "• <b>투자 영향</b> 할인율 상승은 유럽·글로벌 장기듀레이션 성장주와 고부채 유틸리티·부동산·인프라에 부담. 은행은 NIM 수혜와 신용비용 상승을 함께 확인",
            "• <b>한국 연결</b> LNG 조달원가 상승에 글로벌 장기금리 상승이 겹치면 국내 할인율·회사채 조달비 부담까지 확대될 수 있음",
            "• <b>다음 확인</b> TTF/Brent → 유로존 단기 인플레이션 기대 → ECB 회의/금리선물 → 독일 2Y·10Y·30Y → 프랑스-독일 10Y 스프레드 → 유럽 주식/신용스프레드",
            "• <b>정확도 규칙</b> ‘가스 +120%’ 같은 누적상승률은 같은 벤치마크·같은 기준일 시계열로 재계산될 때만 숫자로 송출. 기사 문구를 그대로 고정값으로 재사용하지 않음",
        ])
        body += "\n\n" + "\n".join(lines)

    metadata["version"] = 19
    metadata["europe_rates_watch"] = {
        "bond_thresholds": {"bund10_pct": [3.30, 3.40, 3.50, 3.75], "us10_pct": [4.80, 5.00, 5.25]},
        "aug4_relative_rules_bp": {"bund_since_aug4": [20, 30], "bund_minus_us": 5},
        "causal_split": ["energy/inflation/ECB repricing", "fiscal/political/term premium"],
        "next_checks": ["TTF/Brent", "ECB pricing", "Germany 2Y/10Y/30Y", "France-Bund spread", "credit/equity discount rate"],
        "numeric_source": "Trendonify current/history with Trading Economics current cross-check; suppress on mismatch/staleness",
    }
    return title, body, metadata


def build_setup_test_v19(quotes):
    title, body, metadata = v18.build_setup_test_v18(quotes)
    title = "✅ LNG·유럽 채권금리 전이 감시 v19 적용"
    body += (
        "\n\n<b>유럽 채권·ECB 재가격</b>"
        "\n• 독일 10년 3.30·3.40·3.50·3.75% 임계값 감시"
        "\n• 2026-08-04 대비 독일 +20/+30bp, 독일 상승폭이 미국보다 +5bp 이상이면 상대 매도강도 경보"
        "\n• 가스/에너지→인플레이션→ECB 정책기대 경로와 재정·정치/기간프리미엄 경로를 분리"
        "\n• 독일/미국 10년은 Trendonify 현재·과거값을 Trading Economics 현재값으로 교차검증하고 불일치/지연 시 숫자 보류"
        "\n• 누적 가스 상승률은 동일 벤치마크·동일 기준일 시계열로 직접 재계산할 때만 표시"
    )
    metadata["version"] = 19
    return title, body, metadata


core.fetch_market_quotes = fetch_market_quotes_v19
core.apply_hysteresis = apply_hysteresis_v19
core.signal_label = signal_label_v19
core.format_quote = format_quote_v19
core.category_label = category_label_v19
core.classify_alert_context = classify_alert_context_v19
core.impact_text = impact_text_v19
core.confirmed_news_groups = confirmed_news_groups_v19
core.build_regular_alert = build_regular_alert_v19
core.build_setup_test = build_setup_test_v19

if __name__ == "__main__":
    raise SystemExit(core.main())
