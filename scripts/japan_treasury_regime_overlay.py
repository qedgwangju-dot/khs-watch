#!/usr/bin/env python3
"""Japan FX intervention -> Treasury/repatriation regime overlay.

This monitor adds the causal distinctions highlighted by the September 7-8, 2026
reserve/intervention disclosures:
1) one-off official FX-intervention funding versus persistent private repatriation,
2) visible FIMA/foreign-official repo mitigation versus securities-funded intervention,
3) Japan-flow/term-premium long-end selloff versus Fed/front-end repricing,
4) high-materiality U.S. pressure on Japan's reflation/BOJ policy.

It is intentionally an overlay. Existing Japan reserve, JGB auction, global-rates,
Treasury auction and buyback monitors remain the source-specific lanes.
"""
from __future__ import annotations

import csv
import datetime as dt
import email.utils
import hashlib
import html
import io
import json
import pathlib
import re
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from khs_source_fetch import fetch_text, record_source_failure
from krw_fx import format_krw, latest_jpy_krw
from japan_reserve_funding_watch import (
    MOF_INTERVENTION_INDEX,
    MOF_RESERVE_INDEX,
    latest_intervention_link,
    latest_reserve_links,
    parse_intervention_page,
    parse_reserve_page,
)
from japan_treasury_spillover_watch import (
    FED_H41,
    MOF_WEEK,
    normalize_week,
    num,
    parse_h41_foreign_official_repo,
)
import yen_carry_alert as legacy
from yen_carry_market_data_v2 import fetch_quote

KST = ZoneInfo("Asia/Seoul")
UTC = dt.timezone.utc
ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "out"
DATA.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)

STATE_PATH = DATA / "japan_treasury_regime_overlay_state.json"
PENDING_PATH = OUT / "japan_treasury_regime_overlay_pending.json"
ALERT_PATH = OUT / "japan_treasury_regime_overlay_alert.html"
TITLE_PATH = OUT / "japan_treasury_regime_overlay_title.txt"
STATUS_PATH = OUT / "japan_treasury_regime_overlay_status.md"

UA = "Mozilla/5.0 khs-japan-treasury-regime-overlay/1.0"

# Official intervention-funding fingerprint.
SECURITIES_DROP_HIGH_BN = 50.0
SECURITIES_DROP_CRITICAL_BN = 75.0
INTERVENTION_HIGH_TRN_YEN = 5.0
INTERVENTION_CRITICAL_TRN_YEN = 10.0
FUNDING_RATIO_HIGH = 0.60
FUNDING_RATIO_CRITICAL = 0.75
FIMA_MITIGATION_BN = 1.0

# Private-flow regime: do not call one week a structural repatriation trend.
FLOW_4W_HIGH_TRN_YEN = -2.0
FLOW_12W_HIGH_TRN_YEN = -5.0
FLOW_NEGATIVE_STREAK_WATCH = 3

# Live price discriminator. Yield quote units are percentage points, converted to bp.
YEN_STRENGTH_PCT = -0.75
UST_LONG_UP_BP = 6.0
UST_FRONT_MAX_BP = 4.0
CURVE_STEEPEN_BP = 4.0
FED_FRONT_UP_BP = 8.0
EVENT_UST10_LEVEL = 4.82
EVENT_UST30_LEVEL = 5.27
EVENT_LEVELS_END = dt.date(2026, 9, 15)

POLICY_MAX_AGE_HOURS = 18
POLICY_QUERIES = (
    ("en", 'Bessent Japan BOJ "stop the reflation"'),
    ("en", 'Bessent Japan BOJ decisive monetary policy yen fiscal'),
    ("ja", 'ベッセント 日本 日銀 リフレ 財政 金融政策 円'),
)
MAJOR_SOURCES = ("reuters", "bloomberg", "financial times", "nikkei", "日本経済新聞", "nhk")
POLICY_US = ("bessent", "ベッセント", "u.s. treasury", "us treasury", "米財務")
POLICY_JAPAN = ("japan", "boj", "bank of japan", "日本", "日銀", "財務省")
POLICY_PRESSURE = (
    "stop the reflation", "reflation", "abenomics", "decisive monetary", "decisive action",
    "raise rates", "rate hike", "fiscal discipline", "policy change", "リフレ", "利上げ", "財政規律",
)
POLICY_SOVEREIGNTY = (
    "independence", "independent", "sovereignty", "no request", "not requested",
    "中立性", "独立", "主権", "要求はない", "要請はない",
)


def source(name: str, url: str, now: dt.datetime, *, accept: str = "text/html,application/xhtml+xml,*/*") -> str:
    text, error = fetch_text(url, UA, timeout=20, attempts=2, accept=accept)
    if error or not text:
        record_source_failure(
            lane="japan_treasury_regime_overlay",
            source_name=name,
            source_url=url,
            error=error or "empty response",
            checked_at=now,
        )
        raise RuntimeError(error or f"{name}: empty response")
    return text


def load_state() -> dict:
    try:
        value = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


@dataclass(frozen=True)
class FlowRegime:
    latest_week: str
    one_week: float
    two_week: float
    four_week: float
    twelve_week: float
    negative_streak: int


def parse_flow_regime(text: str) -> FlowRegime:
    rows: list[tuple[str, float]] = []
    for row in csv.reader(io.StringIO(text.lstrip("\ufeff"))):
        if len(row) < 8 or not any(ch.isdigit() for ch in (row[0] or "")):
            continue
        value = num(row[6])
        if value is None:
            continue
        rows.append((normalize_week(row[0]), value / 10000.0))
    if len(rows) < 12:
        raise RuntimeError(f"MOF weekly long-term debt needs 12 rows, got {len(rows)}")
    values = [x[1] for x in rows]
    streak = 0
    for value in reversed(values):
        if value < 0:
            streak += 1
        else:
            break
    return FlowRegime(
        latest_week=rows[-1][0],
        one_week=values[-1],
        two_week=sum(values[-2:]),
        four_week=sum(values[-4:]),
        twelve_week=sum(values[-12:]),
        negative_streak=streak,
    )


@dataclass(frozen=True)
class LiveMarket:
    observed_at_utc: str
    usdjpy: float
    usdjpy_change_pct: float
    ust2: float | None
    ust2_change_bp: float | None
    ust10: float
    ust10_change_bp: float
    ust30: float
    ust30_change_bp: float


def _yield_quote(symbol: str, label: str):
    q = fetch_quote(legacy.SymbolSpec(symbol, label, "현물"))
    return q, (q.price - q.previous_close) * 100.0


def live_market() -> LiveMarket:
    fx = fetch_quote(legacy.SYMBOLS["usd_jpy"])
    q10, c10 = _yield_quote("^TNX", "미국 10년 국채금리")
    q30, c30 = _yield_quote("^TYX", "미국 30년 국채금리")
    q2 = None
    c2 = None
    try:
        q2, c2 = _yield_quote("^UST2Y", "미국 2년 국채금리")
    except Exception:
        q2 = None
        c2 = None
    observed = max(fx.timestamp_epoch, q10.timestamp_epoch, q30.timestamp_epoch, q2.timestamp_epoch if q2 else 0)
    return LiveMarket(
        observed_at_utc=dt.datetime.fromtimestamp(observed, tz=UTC).isoformat().replace("+00:00", "Z"),
        usdjpy=fx.price,
        usdjpy_change_pct=fx.change_pct,
        ust2=None if q2 is None else q2.price,
        ust2_change_bp=c2,
        ust10=q10.price,
        ust10_change_bp=c10,
        ust30=q30.price,
        ust30_change_bp=c30,
    )


def google_rss_url(lang: str, query: str) -> str:
    if lang == "ja":
        params = {"q": query, "hl": "ja", "gl": "JP", "ceid": "JP:ja"}
    else:
        params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)


def _policy_items(now: dt.datetime) -> list[dict]:
    out: dict[str, dict] = {}
    cutoff = now.astimezone(UTC) - dt.timedelta(hours=POLICY_MAX_AGE_HOURS)
    for lang, query in POLICY_QUERIES:
        url = google_rss_url(lang, query)
        try:
            text = source(f"Google News policy {lang}", url, now, accept="application/rss+xml,application/xml,text/xml,*/*")
            root = ET.fromstring(text)
        except Exception:
            continue
        for node in root.findall(".//item"):
            title = (node.findtext("title") or "").strip()
            desc = (node.findtext("description") or "").strip()
            link = (node.findtext("link") or "").strip()
            pub = email.utils.parsedate_to_datetime((node.findtext("pubDate") or "").strip())
            src_node = node.find("source")
            src = (src_node.text or "").strip() if src_node is not None else ""
            if not title or not link or pub is None:
                continue
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=UTC)
            pub = pub.astimezone(UTC)
            if pub < cutoff or pub > now.astimezone(UTC) + dt.timedelta(minutes=10):
                continue
            full = html.unescape(f"{title} {desc} {src}").lower()
            if not any(x in full for x in MAJOR_SOURCES):
                continue
            if not any(x in full for x in POLICY_US) or not any(x in full for x in POLICY_JAPAN):
                continue
            pressure = any(x in full for x in POLICY_PRESSURE)
            sovereignty = any(x in full for x in POLICY_SOVEREIGNTY)
            if not pressure and not sovereignty:
                continue
            key = hashlib.sha256(f"{src}|{title}|{link}".encode("utf-8")).hexdigest()[:20]
            out[key] = {
                "id": key,
                "title": re.sub(r"\s+", " ", title),
                "source": src or "major media",
                "link": link,
                "published_utc": pub.isoformat(),
                "pressure": pressure,
                "sovereignty": sovereignty,
            }
    return sorted(out.values(), key=lambda x: x["published_utc"], reverse=True)


def signal_levels(*, sec_drop_bn: float | None, intervention_trn: float | None, funding_ratio: float | None,
                  fima_bn: float | None, flow: FlowRegime | None, market: LiveMarket | None,
                  today: dt.date) -> dict[str, int]:
    result = {
        "official_funding": 0,
        "structural_repatriation": 0,
        "japan_long_end_fingerprint": 0,
        "event_long_end_breakout": 0,
        "fed_repricing_dominant": 0,
        "one_off_relief": 0,
    }
    if sec_drop_bn is not None and intervention_trn is not None and funding_ratio is not None:
        if sec_drop_bn <= -SECURITIES_DROP_HIGH_BN and intervention_trn >= INTERVENTION_HIGH_TRN_YEN:
            result["official_funding"] = 2
        if (
            sec_drop_bn <= -SECURITIES_DROP_CRITICAL_BN
            and intervention_trn >= INTERVENTION_CRITICAL_TRN_YEN
            and funding_ratio >= FUNDING_RATIO_CRITICAL
            and (fima_bn or 0.0) < FIMA_MITIGATION_BN
        ):
            result["official_funding"] = 3
        elif funding_ratio >= FUNDING_RATIO_HIGH and result["official_funding"]:
            result["official_funding"] = max(result["official_funding"], 2)

    if flow:
        if flow.four_week <= FLOW_4W_HIGH_TRN_YEN or flow.twelve_week <= FLOW_12W_HIGH_TRN_YEN:
            result["structural_repatriation"] = 2
        elif flow.negative_streak >= FLOW_NEGATIVE_STREAK_WATCH:
            result["structural_repatriation"] = 1

    if market:
        front = market.ust2_change_bp
        long_both = min(market.ust10_change_bp, market.ust30_change_bp)
        yen_strong = market.usdjpy_change_pct <= YEN_STRENGTH_PCT
        front_quiet = front is None or front <= UST_FRONT_MAX_BP
        steep = front is None or min(market.ust10_change_bp - front, market.ust30_change_bp - front) >= CURVE_STEEPEN_BP
        if yen_strong and long_both >= UST_LONG_UP_BP and front_quiet and steep:
            result["japan_long_end_fingerprint"] = 3
        if (
            today <= EVENT_LEVELS_END
            and yen_strong
            and market.ust10 >= EVENT_UST10_LEVEL
            and market.ust30 >= EVENT_UST30_LEVEL
            and front_quiet
        ):
            result["event_long_end_breakout"] = 3
        if front is not None and front >= FED_FRONT_UP_BP and market.ust10_change_bp >= UST_LONG_UP_BP:
            result["fed_repricing_dominant"] = 1
        if yen_strong and market.ust10_change_bp <= 0 and market.ust30_change_bp <= 0:
            result["one_off_relief"] = 1
    return result


def event_text(key: str) -> str:
    return {
        "official_funding": "대규모 엔화개입과 외화증권 감소의 동행이 강함 — 공적 개입 재원이 외화증권 수급으로 전이된 흔적",
        "structural_repatriation": "일본 거주자의 해외 중장기채 매도가 4주·12주 기준으로 구조화 — 일회성 정부 매도와 별개",
        "japan_long_end_fingerprint": "엔화 강세와 미국 10·30년 금리 상승이 동시에 발생하고 2년물은 상대적으로 조용함 — 일본/기간프리미엄 경로 강화",
        "event_long_end_breakout": "9월 이벤트 구간에서 미국 10년 4.82%·30년 5.27%를 동시에 상향 — 일본 매도/본국회귀 재평가 경계",
        "fed_repricing_dominant": "미국 2년물이 장기물과 함께 크게 상승 — 일본 수급보다 Fed·미국 물가 재가격 가능성이 더 큼",
        "one_off_relief": "엔화는 강해지지만 미국 10·30년 금리는 하락/안정 — 과거 개입 매도 확인 후 추가 강제매도 우려 완화",
        "policy_pressure": "미국 측의 일본 reflation/BOJ·재정정책 압박성 메시지 신규 확인",
        "policy_sovereignty": "일본 측의 정책독립성·공식요구 부인 메시지 신규 확인",
        "official_private_overlap": "공적 개입 재원 압력과 민간 해외채 본국회귀가 동시에 강함 — 단발성에서 구조적 수급 문제로 승격",
    }.get(key, key)


def fmt_usd_bn(value: float, quote, signed: bool = False) -> str:
    lead = "+" if signed and value > 0 else ""
    raw = f"{lead}{value:,.2f}십억달러"
    if quote is None:
        return raw
    return f"{raw} (약 {format_krw(value * 1_000_000_000 * quote.usdkrw)})"


def fmt_yen_trn(value: float, quote) -> str:
    if quote is None:
        return f"{value:,.4f}조엔"
    return f"{value:,.4f}조엔 (약 {format_krw(value * 1_000_000_000_000 * quote.krw_per_yen)})"


def main() -> int:
    now = dt.datetime.now(KST)
    for path in (ALERT_PATH, TITLE_PATH):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    state = load_state()
    first = not bool(state.get("initialized"))
    errors: list[str] = []

    current = previous = intervention = fima = flow = market = None
    quote = None
    try:
        idx = source("MOF reserve index", MOF_RESERVE_INDEX, now)
        cur_url, prev_url = latest_reserve_links(idx)
        current = parse_reserve_page(source("MOF reserve current", cur_url, now), cur_url)
        previous = parse_reserve_page(source("MOF reserve previous", prev_url, now), prev_url)
    except Exception as exc:
        errors.append(f"reserve: {type(exc).__name__}: {exc}")
    try:
        idx = source("MOF intervention index", MOF_INTERVENTION_INDEX, now)
        url = latest_intervention_link(idx)
        intervention = parse_intervention_page(source("MOF intervention", url, now), url)
    except Exception as exc:
        errors.append(f"intervention: {type(exc).__name__}: {exc}")
    try:
        fima = parse_h41_foreign_official_repo(source("Fed H.4.1", FED_H41, now))
    except Exception as exc:
        errors.append(f"H41: {type(exc).__name__}: {exc}")
    try:
        flow = parse_flow_regime(source("MOF weekly securities", MOF_WEEK, now, accept="text/csv,text/plain,*/*"))
    except Exception as exc:
        errors.append(f"flow: {type(exc).__name__}: {exc}")
    try:
        market = live_market()
    except Exception as exc:
        errors.append(f"live market: {type(exc).__name__}: {exc}")
    try:
        quote = latest_jpy_krw()
    except Exception as exc:
        errors.append(f"FX conversion: {type(exc).__name__}: {exc}")

    sec_drop = None if not current or not previous else current.securities_bn - previous.securities_bn
    intervention_usd_bn = None
    funding_ratio = None
    if intervention and quote and quote.usdjpy > 0:
        intervention_usd_bn = intervention.trillion_yen * 1000.0 / quote.usdjpy
        if sec_drop is not None and intervention_usd_bn > 0:
            funding_ratio = abs(min(sec_drop, 0.0)) / intervention_usd_bn

    levels = signal_levels(
        sec_drop_bn=sec_drop,
        intervention_trn=None if intervention is None else intervention.trillion_yen,
        funding_ratio=funding_ratio,
        fima_bn=None if fima is None else fima.level_bn_usd,
        flow=flow,
        market=market,
        today=now.date(),
    )
    if levels["official_funding"] >= 2 and levels["structural_repatriation"] >= 2:
        levels["official_private_overlap"] = 3
    else:
        levels["official_private_overlap"] = 0

    old_levels = state.get("levels") or {}
    events: list[dict] = []
    if not first:
        for key, level in levels.items():
            old_level = int(old_levels.get(key) or 0)
            if level > old_level:
                events.append({"kind": key, "level": level})
            elif level == 0 < old_level and key in {"structural_repatriation", "official_funding"}:
                events.append({"kind": f"{key}_eased", "level": 0})

    policy_items = _policy_items(now)
    old_policy = set(state.get("seen_policy_ids") or [])
    if not first:
        for item in policy_items[:5]:
            if item["id"] in old_policy:
                continue
            if item["pressure"]:
                events.append({"kind": "policy_pressure", "level": 2, "item": item})
            elif item["sovereignty"]:
                events.append({"kind": "policy_sovereignty", "level": 1, "item": item})

    pending = {
        "initialized": True,
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "levels": levels,
        "seen_policy_ids": list(dict.fromkeys([x["id"] for x in policy_items[:40]] + list(old_policy)))[:120],
        "snapshot": {
            "reserve_period": None if current is None else current.period,
            "securities_drop_bn_usd": sec_drop,
            "intervention_trillion_yen": None if intervention is None else intervention.trillion_yen,
            "intervention_usd_bn": intervention_usd_bn,
            "funding_ratio": funding_ratio,
            "fima_bn_usd": None if fima is None else fima.level_bn_usd,
            "flow": None if flow is None else flow.__dict__,
            "market": None if market is None else market.__dict__,
        },
    }
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    status = [
        "# 일본 FX개입→미국채 체제 전환 오버레이",
        "",
        f"- 조회: {now.isoformat(timespec='seconds')}",
        f"- 상태: {'초기 기준선 생성' if first else ('신규 경보' if events else '신규 경보 없음')}",
        f"- 신호: {levels}",
    ]
    if errors:
        status += ["", "## 부분 확인"] + [f"- {x}" for x in errors]
    STATUS_PATH.write_text("\n".join(status) + "\n", encoding="utf-8")

    if first or not events:
        return 0

    risk_levels = [x["level"] for x in events if x["level"] > 0]
    top = max(risk_levels) if risk_levels else 1
    badge = {1: "🟡", 2: "🟠", 3: "🔴"}.get(top, "🟡")
    TITLE_PATH.write_text(f"{badge} 일본→미국채 체제 전환 {'CRITICAL' if top >= 3 else ('HIGH' if top == 2 else 'WATCH')}", encoding="utf-8")

    lines = ["<b>핵심 판정</b>"]
    for event in events:
        if event["kind"].endswith("_eased"):
            lines.append(f"• 🟢 {html.escape(event['kind'].replace('_eased', ''))} 경보가 해제 임계치로 복귀")
        else:
            lines.append(f"• {html.escape(event_text(event['kind']))}")
            if event.get("item"):
                item = event["item"]
                lines.append(f"  └ {html.escape(item['source'])}: <a href=\"{html.escape(item['link'])}\">{html.escape(item['title'])}</a>")

    lines += ["", "<b>범인 찾음 vs 계속 파나 — 분리 판정</b>"]
    if sec_drop is not None:
        lines.append(f"• 외화증권 전월 변화: <b>{fmt_usd_bn(sec_drop, quote, signed=True)}</b>")
    if intervention:
        lines.append(f"• FX 개입: <b>{fmt_yen_trn(intervention.trillion_yen, quote)}</b>")
    if intervention_usd_bn is not None:
        lines.append(f"• 같은 환율 기준 개입액: 약 <b>{fmt_usd_bn(intervention_usd_bn, quote)}</b>")
    if funding_ratio is not None:
        lines.append(f"• 외화증권 감소/개입액 비율: <b>{funding_ratio * 100:.1f}%</b> · 미국채 정확 매도액이 아닌 재원 압력 보조지표")
    if fima:
        lines.append(f"• Fed H.4.1 외국공식 레포 프록시: <b>{fima.level_bn_usd:.3f}십억달러</b> · 일본 단독 FIMA 사용액은 아님")
    if flow:
        lines += [
            f"• 일본 거주자 해외 중장기채: 1주 {flow.one_week:+.3f}조엔 / 4주 <b>{flow.four_week:+.3f}조엔</b> / 12주 <b>{flow.twelve_week:+.3f}조엔</b>",
            f"  └ 연속 순매도 {flow.negative_streak}주 · 4주/12주가 계속 음수면 ‘정부 일회성’보다 구조적 본국회귀 위험을 상향",
        ]

    if market:
        u2 = "확인 불가" if market.ust2 is None else f"{market.ust2:.3f}% ({market.ust2_change_bp:+.1f}bp)"
        lines += [
            "",
            "<b>미국 금리 원인 분리</b>",
            f"• USD/JPY <b>{market.usdjpy:.2f}</b> ({market.usdjpy_change_pct:+.2f}%)",
            f"• UST 2년 {u2}",
            f"• UST 10년 <b>{market.ust10:.3f}%</b> ({market.ust10_change_bp:+.1f}bp) / 30년 <b>{market.ust30:.3f}%</b> ({market.ust30_change_bp:+.1f}bp)",
            "• 엔화 강세 + 10·30년 상승 + 2년 상대 안정이면 일본 본국회귀/기간프리미엄 쪽, 2년까지 급등하면 Fed·미국 물가 쪽에 무게.",
        ]

    lines += [
        "",
        "<b>주식시장 해석</b>",
        "• 별도 주가 경보를 만들지는 않습니다. 이 신호가 실제 발생할 때만 ‘일본 수출주→은행·내수 상대회전’과 ‘고베타 AI→더 싼/짧은 듀레이션 AI 현금흐름’ 가능성을 보조 해석으로 붙입니다.",
        "• 이유: 이것은 아직 확정된 자금 이동이 아니라 금리·환율 체제가 만들어내는 상대가치 시나리오이므로 단독 경보로 쓰면 잡음이 큽니다.",
        "",
        "<b>시간표</b>",
        "• 9/8 미국 3년물, 9/9 10년물, 9/10 30년물 입찰 결과는 기존 미국채 입찰 감시가 별도 확인합니다.",
        "• 9/9부터 미 재무부 장기물 유동성 지원 바이백 확대는 기존 바이백 감시가 완화요인으로 별도 확인합니다.",
        "",
        "<b>실패 경로·완화요인</b>",
        "• 최대 실패 경로: BOJ 정상화 → JGB 매력 상승 → 일본 민간 해외채 매도 지속 → UST 장기금리 상승 → 엔캐리/베이시스 레버리지 축소 → 글로벌 성장주 할인율 상승.",
        "• 완화요인: 엔화 안정으로 추가 개입이 멈추거나 FIMA 프록시가 실제 증가하고, 일본 해외 중장기채 4주·12주 흐름이 순매수로 복귀하는 경우.",
        "",
        f"조회 {now.strftime('%Y-%m-%d %H:%M:%S')} KST",
    ]
    ALERT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
