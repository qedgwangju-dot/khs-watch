#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import re

import lng_supply_crisis_alert_v2 as core
import lng_supply_crisis_alert_v4 as te
import lng_supply_crisis_alert_v15 as v15

v14 = v15.v14
UTC = dt.timezone.utc
JKM_URL = "https://ko.tradingeconomics.com/commodity/liquefied-natural-gas-japan-korea"

# 카타르 불가항력 장기화와 아시아 현물 LNG(JKM) 급등을 별도 핵심 경보축으로 추가한다.
EXTRA_QATAR_JKM_QUERIES = (
    ("qatar_supply", 'QatarEnergy Edison early November LNG cancelled cargoes force majeure when:7d'),
    ("qatar_supply", '"Qatar LNG" force majeure November deliveries Asia when:7d'),
    ("asia_procurement", '"JKM" "highest since December 2022" Qatar force majeure when:3d'),
    ("asia_procurement", '"Asian LNG" "highest since 2022" Qatar November when:3d'),
    ("asia_procurement", '아시아 LNG 현물 2022년 12월 이후 최고 카타르 불가항력 11월 when:7d'),
)
for item in EXTRA_QATAR_JKM_QUERIES:
    if item not in core.NEWS_QUERIES:
        core.NEWS_QUERIES = tuple(core.NEWS_QUERIES) + (item,)

core.TRUSTED_SOURCE_ALIASES = tuple(core.TRUSTED_SOURCE_ALIASES) + (
    "s&p global", "s&p global energy", "s&p global commodity insights", "platts",
    "wallstreetcn", "wall street cn", "华尔街见闻", "the national",
)

core.WORSENING_TERMS["qatar_supply"] = tuple(core.WORSENING_TERMS["qatar_supply"]) + (
    "cancelled cargoes", "canceled cargoes", "cancels gas deliveries", "early november",
    "until november", "into november", "11월", "11월까지", "카고 취소",
)
core.WORSENING_TERMS["asia_procurement"] = tuple(core.WORSENING_TERMS["asia_procurement"]) + (
    "jkm soars", "highest since december 2022", "highest since 2022", "25.908",
    "2022년 12월 이후 최고", "2022년 이후 최고", "现货价格", "2022年12月以来最高",
)
core.SUBTYPE_TERMS = (
    ("qatar_force_majeure_november", ("early november", "until november", "into november", "11월까지", "11월")),
    ("asia_jkm_2022_high", ("highest since december 2022", "highest since 2022", "2022년 12월 이후 최고", "2022년 이후 최고", "25.908")),
) + tuple(core.SUBTYPE_TERMS)

# Trading Economics 공개 JKM 추종값도 수치 모니터링에 추가한다. Platts 공식 평가값과는 구분한다.
core.PRICE_SPECS["jkm"] = {
    "symbol": "TE-KO:LNG-JKM",
    "label": "Trading Economics 한국 LNG JKM 추종 공개값",
    "unit": "달러/MMBtu",
    "levels": (20.0, 25.0, 30.0, 40.0),
    "exit_buffer": 0.5,
}

# 영문 제목은 기존 한국어 전용 송출 규칙에 따라 번역한다.
v8 = v15.v14.v13.v12.v8
v8.SOURCE_KO.update(
    {
        "s&p global": "S&P 글로벌",
        "s&p global energy": "S&P 글로벌 에너지",
        "s&p global commodity insights": "S&P 글로벌 커머디티 인사이트",
        "platts": "플래츠",
        "wallstreetcn": "화얼제젠원",
        "wall street cn": "화얼제젠원",
        "the national": "더 내셔널",
    }
)
v8.KNOWN_TRANSLATIONS.update(
    {
        "JKM soars to highest since December 2022 as Middle East war shuts arbitrage window":
            "중동 전쟁으로 차익거래 창구가 막히며 JKM, 2022년 12월 이후 최고치",
        "QatarEnergy cancels gas deliveries to Italy's Edison until early November over Iran war":
            "카타르에너지, 이란 전쟁 여파로 이탈리아 에디슨향 가스 공급을 11월 초까지 취소",
        "QatarEnergy extends LNG supply suspension to Italy until November":
            "카타르에너지, 이탈리아 LNG 공급 중단을 11월까지 연장",
        "Asian LNG Prices Surge to Highest Since 2022 as Iran War Escalates":
            "이란 전쟁 격화로 아시아 LNG 가격, 2022년 이후 최고 수준으로 급등",
    }
)


def parse_te_jkm(raw_html: str) -> dict[str, object]:
    text = te.visible_text(raw_html)
    stats = re.search(
        r"실제\s+이전\s+최고\s+최저\s+날짜\s+단위\s+업데이트\s*주기\s+([0-9.,]+)\s+([0-9.,]+)",
        text,
        flags=re.I,
    )
    if not stats:
        raise RuntimeError("Trading Economics JKM actual/previous table not found")
    actual = te.number(stats.group(1))
    previous = te.number(stats.group(2))
    if previous <= 0:
        raise RuntimeError("Trading Economics JKM previous value invalid")

    date_match = re.search(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일\s+lng\s+jkm", text, flags=re.I)
    if not date_match:
        raise RuntimeError("Trading Economics JKM source date not found")
    source_date = dt.date(int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3)))
    today_kst = core.now_utc().astimezone(core.KST).date()
    age_days = (today_kst - source_date).days
    if age_days < 0 or age_days > 5:
        raise RuntimeError(f"Trading Economics JKM stale source date={source_date} age={age_days}d")

    calculated_pct = (actual / previous - 1.0) * 100.0
    rows = []
    for match in re.finditer(
        r"LNG\s+JKM\s+([0-9.,]+)\s+([+-]?[0-9.,]+)\s+([+-]?[0-9.,]+)%",
        text,
        flags=re.I,
    ):
        rows.append((te.number(match.group(1)), te.number(match.group(3))))
    coherent = [
        row for row in rows
        if abs(row[0] / actual - 1.0) * 100.0 <= 0.20 and abs(row[1] - calculated_pct) <= 0.25
    ]
    if not coherent:
        raise RuntimeError(
            f"Trading Economics JKM internal values disagree actual={actual} previous={previous} pct={calculated_pct:.2f}"
        )
    return {
        "actual": actual,
        "previous": previous,
        "change_pct": calculated_pct,
        "source_date": source_date.isoformat(),
    }


def fetch_te_jkm_quote() -> core.Quote:
    parsed = parse_te_jkm(te.fetch_te_html(JKM_URL))
    observed = core.now_utc()
    return core.Quote(
        key="jkm",
        symbol="TE-KO:LNG-JKM",
        label="Trading Economics 한국 LNG JKM 추종 공개값",
        unit="달러/MMBtu",
        price=float(parsed["actual"]),
        previous_close=float(parsed["previous"]),
        change_pct=float(parsed["change_pct"]),
        timestamp_epoch=observed.timestamp(),
        timestamp_utc=observed.isoformat(timespec="seconds"),
        age_minutes=0,
        source_note=(
            "Trading Economics 한국 LNG JKM 공개페이지 actual/previous/내부 시세표 검증; "
            f"기준일={parsed['source_date']}; Platts 공식 평가값 아님"
        ),
    )


_base_fetch_market_quotes = core.fetch_market_quotes
_base_format_quote = core.format_quote
_base_signal_label = core.signal_label


def fetch_market_quotes_v16():
    quotes, errors = _base_fetch_market_quotes()
    try:
        quotes["jkm"] = fetch_te_jkm_quote()
    except Exception as exc:
        errors.append(f"jkm: {type(exc).__name__}: {exc}")
    return quotes, errors


def format_quote_v16(quote: core.Quote) -> str:
    if quote.key != "jkm":
        return _base_format_quote(quote)
    source_date = "미확인"
    match = re.search(r"기준일=(\d{4}-\d{2}-\d{2})", quote.source_note)
    if match:
        source_date = match.group(1)
    observed_kst = dt.datetime.fromtimestamp(quote.timestamp_epoch, UTC).astimezone(core.KST)
    return (
        f"{quote.label} {quote.price:,.2f}{quote.unit} "
        f"(이전값 {quote.previous_close:,.2f} 대비 {quote.change_pct:+.2f}%, "
        f"기준일 {source_date}, 조회 {observed_kst:%Y-%m-%d %H:%M KST}; Platts 공식 평가값 아님)"
    )


def signal_label_v16(signal: str, cleared: bool = False) -> str:
    labels = {
        "jkm_up_5": "Trading Economics JKM 추종 공개값 이전값 대비 +5% 이상",
        "jkm_down_5": "Trading Economics JKM 추종 공개값 이전값 대비 -5% 이하",
        "jkm_above_20": "Trading Economics JKM 추종 공개값 20달러/MMBtu 상회",
        "jkm_above_25": "Trading Economics JKM 추종 공개값 25달러/MMBtu 상회",
        "jkm_above_30": "Trading Economics JKM 추종 공개값 30달러/MMBtu 상회",
        "jkm_above_40": "Trading Economics JKM 추종 공개값 40달러/MMBtu 상회",
    }
    if signal in labels:
        return f"{labels[signal]} 종료" if cleared else labels[signal]
    return _base_signal_label(signal, cleared)


EARLY_QATAR_SOURCES = ("reuters", "로이터")
EARLY_JKM_BENCHMARK_SOURCES = ("s&p global", "s&p global energy", "s&p global commodity insights", "platts")


def confirmed_news_groups_v16(items: list[core.NewsItem]):
    confirmed = v15.confirmed_news_groups_v15(items)
    existing = {
        (str(group.get("category")), str(group.get("polarity")), str(group.get("subtype")), str(group.get("event_id")))
        for group in confirmed
    }
    for item in sorted(items, key=lambda value: value.published_epoch, reverse=True):
        normalized = core.normalize_text(item.title)
        allow = False
        verification = ""
        if item.category == "qatar_supply" and item.polarity == "worsening":
            if core.source_matches(item.source, EARLY_QATAR_SOURCES) and (
                "november" in normalized or "11월" in normalized or "cancels gas deliveries" in normalized
            ):
                allow = True
                verification = "카타르 공급 장기화 조기신호·로이터 확인"
        elif item.category == "asia_procurement" and item.polarity == "worsening":
            if core.source_matches(item.source, EARLY_JKM_BENCHMARK_SOURCES) and (
                "highest since december 2022" in normalized or "highest since 2022" in normalized or "25 908" in normalized
            ):
                allow = True
                verification = "Platts JKM 가격평가 원천·S&P 글로벌 확인"
        if not allow:
            continue
        key = (item.category, item.polarity, item.subtype, item.event_id)
        if key in existing:
            continue
        confirmed.append(
            {
                "category": item.category,
                "polarity": item.polarity,
                "subtype": item.subtype,
                "event_id": item.event_id,
                "latest_epoch": item.published_epoch,
                "evidence": [item],
                "verification": verification,
            }
        )
        existing.add(key)
    confirmed.sort(key=lambda group: float(group["latest_epoch"]), reverse=True)
    return confirmed


def build_regular_alert_v16(groups, quotes, new_signals, cleared_signals):
    title, body, metadata = v15.build_regular_alert_v15(groups, quotes, new_signals, cleared_signals)
    qatar_groups = [g for g in groups if g.get("category") == "qatar_supply" and g.get("subtype") == "qatar_force_majeure_november"]
    jkm_groups = [g for g in groups if g.get("category") == "asia_procurement" and g.get("subtype") == "asia_jkm_2022_high"]

    if qatar_groups or jkm_groups:
        title = "⚠️ 카타르 LNG·아시아 현물가격 경보"
        lines = ["<b>카타르 공급 장기화·아시아 JKM</b>"]

        if qatar_groups:
            evidence_text = " ".join(
                f"{item.title} {item.source}" for group in qatar_groups for item in group.get("evidence", [])
            ).lower()
            if "edison" in evidence_text or "에디슨" in evidence_text:
                lines.extend([
                    "• <b>확정 범위</b> 카타르에너지의 이탈리아 에디슨향 공급 중단이 <b>11월 초</b>까지 연장",
                    "• <b>물량</b> 9월 말~11월 초 예정 <b>5개 추가 LNG 카고 취소</b> · 누적 29개 선적 취소 보도",
                    "• <b>주의</b> 이 확인은 에디슨 계약 범위다. 아시아 전체 구매자에게 동일하게 11월까지 연장됐다고 자동 확대해석하지 않음",
                ])
            else:
                lines.append("• <b>카타르</b> 11월까지 불가항력/공급중단 연장 보도 · 구매자별 적용 범위를 별도 확인")

        if jkm_groups:
            lines.extend([
                "• <b>Platts JKM</b> 10월물 <b>25.908달러/MMBtu</b> · 2026-09-02 평가",
                "• <b>역사 비교</b> <b>2022년 12월 이후 최고</b> · 2022-12-30 당시 28.315달러/MMBtu",
            ])
            try:
                usd = v14.fetch_verified_fx("USD")
                rate = float(usd["rate"])
                krw_per_mmbtu = 25.908 * rate
                lines.append(
                    f"• <b>원화 환산</b> 25.908달러/MMBtu ≈ <b>{krw_per_mmbtu:,.0f}원/MMBtu</b> · 1달러={rate:,.2f}원 · 기준 {usd['timestamp_kst']}"
                )
            except Exception:
                lines.append("• <b>원화 환산</b> 환율 검증 실패로 보류 · 달러 원값은 유지")

        if "jkm" in quotes:
            lines.append(f"• <b>공개 추종값</b> {format_quote_v16(quotes['jkm'])}")
            lines.append("• <b>가격 구분</b> Platts 공식 JKM 평가값과 Trading Economics 공개 CFD 추종값은 동일한 숫자로 취급하지 않음")

        lines.extend([
            "• <b>한국 영향</b> 카타르 장기계약 물량 공백이 길어질수록 10~11월 대체 현물 카고 경쟁과 한국 조달 프리미엄 상승 위험 확대",
            "• <b>투자 영향</b> LNG 판매자·미국/호주 등 비호르무즈 공급원 가격결정력 강화 가능 · 한국 가스발전·도시가스·전력 원가에는 부담",
            "• <b>다음 확인</b> 구매자별 불가항력 종료일 → 카타르 실제 선적량/STS → 호르무즈 통항 → Platts JKM → 한·일 현물입찰",
            "• <b>핵심 한 줄</b> 카타르 공급차질이 겨울 조달기로 넘어가며 아시아 현물가격이 2022년 말 이후 최고 수준까지 올라간 것은 단순 가격 변동이 아니라 <b>수급 스트레스의 단계 상승</b>으로 봄",
        ])
        body += "\n\n" + "\n".join(lines)

    metadata["version"] = 16
    metadata["qatar_jkm_watch"] = {
        "qatar_rule": "buyer-specific November extension; do not generalize to all Asian buyers without confirmation",
        "jkm_benchmark_rule": "Platts/S&P assessment separated from Trading Economics public CFD tracking value",
        "jkm_public_source": JKM_URL,
        "jkm_levels": [20, 25, 30, 40],
    }
    return title, body, metadata


def build_setup_test_v16(quotes):
    title, body, metadata = v15.build_setup_test_v15(quotes)
    title = "✅ 카타르 불가항력·아시아 JKM 감시 v16 적용"
    body += (
        "\n\n<b>카타르·JKM 추가 규칙</b>"
        "\n• 카타르 불가항력/공급중단이 11월로 연장되는 구매자별 공지를 별도 경보"
        "\n• Platts JKM이 2022년 12월 이후 최고 등 역사적 고점을 경신하면 가격평가 원천 기준으로 조기 경보"
        "\n• Trading Economics 한국 LNG JKM 공개값을 20·25·30·40달러 및 일간 ±5%로 별도 수치 감시"
        "\n• Platts 공식 평가값과 Trading Economics 공개 CFD 추종값은 혼합하지 않음"
        "\n• 영문 기사는 한국어 번역, 외화는 검증 환율로 원화 환산 병기"
    )
    metadata["version"] = 16
    return title, body, metadata


core.fetch_market_quotes = fetch_market_quotes_v16
core.format_quote = format_quote_v16
core.signal_label = signal_label_v16
core.confirmed_news_groups = confirmed_news_groups_v16
core.build_regular_alert = build_regular_alert_v16
core.build_setup_test = build_setup_test_v16

if __name__ == "__main__":
    raise SystemExit(core.main())
