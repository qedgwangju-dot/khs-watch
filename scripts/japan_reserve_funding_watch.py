#!/usr/bin/env python3
"""Japan FX-intervention funding monitor.

Tracks the bridge that was missing between yen intervention and U.S. Treasury spillover:
1) Japan MOF monthly reserve composition,
2) Japan MOF monthly FX-intervention amount,
3) Japan Treasury holdings in U.S. TIC Table 5,
4) Fed H.4.1 foreign-official repo and Treasury custody as non-Japan-specific cross-checks.

Important interpretation guardrails:
- Total official reserve assets and foreign-currency reserves are different denominators.
- A fall in MOF 'securities' is NOT an exact Japan U.S. Treasury sale amount.
- H.4.1 foreign-official repo/custody are global foreign-official aggregates, not Japan-only.
- TIC is the country-level after-the-fact confirmation lane and arrives with a lag.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import pathlib
import re
import urllib.parse
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from khs_source_fetch import fetch_text, record_source_failure
from krw_fx import format_krw, latest_jpy_krw
from japan_treasury_spillover_watch import parse_h41_foreign_official_repo

KST = ZoneInfo("Asia/Seoul")
ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "out"
DATA.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)

STATE_PATH = DATA / "japan_reserve_funding_state.json"
PENDING_PATH = OUT / "japan_reserve_funding_pending.json"
ALERT_PATH = OUT / "japan_reserve_funding_alert.html"
TITLE_PATH = OUT / "japan_reserve_funding_title.txt"
STATUS_PATH = OUT / "japan_reserve_funding_status.md"

UA = "Mozilla/5.0 khs-japan-reserve-funding/1.0"
MOF_RESERVE_INDEX = "https://www.mof.go.jp/english/policy/international_policy/reference/official_reserve_assets/index.htm"
MOF_INTERVENTION_INDEX = "https://www.mof.go.jp/policy/international_policy/reference/feio/data/monthly/index.html"
FED_H41 = "https://www.federalreserve.gov/releases/h41/current/"
FED_FIMA = "https://www.federalreserve.gov/monetarypolicy/fima-repo-facility-faqs.htm"
TIC_TABLE5 = "https://ticdata.treasury.gov/Publish/slt_table5.html"
TIC_TABLE5_TXT = "https://ticdata.treasury.gov/resource-center/data-chart-center/tic/Documents/slt_table5.txt"

OFFICIAL_RESERVE_DROP_HIGH_BN = 50.0
FX_RESERVE_FLOOR_BN = 1000.0
SECURITIES_DROP_HIGH_BN = 50.0
INTERVENTION_HIGH_TRILLION_YEN = 5.0
INTERVENTION_CRITICAL_TRILLION_YEN = 10.0
TIC_JAPAN_DROP_HIGH_BN = 25.0
FOREIGN_CUSTODY_DROP_HIGH_BN = 25.0
FIMA_ACTIVE_MIN_BN = 0.001
FIMA_LIMIT_BN = 60.0


def num(value) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace("%", "").replace("−", "-").replace("△", "-")
    text = re.sub(r"\s+", "", text)
    if text in {"", ".", "-", "+"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def source(name: str, url: str, now: dt.datetime, *, accept: str = "text/html,application/xhtml+xml,*/*") -> str:
    text, error = fetch_text(url, UA, timeout=20, attempts=2, accept=accept)
    if error or not text:
        record_source_failure(
            lane="japan_reserve_funding",
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


def abs_url(base: str, href: str) -> str:
    return urllib.parse.urljoin(base, href)


@dataclass(frozen=True)
class ReserveSnapshot:
    period: str
    release_date: str
    url: str
    official_reserve_bn: float
    fx_reserve_bn: float
    securities_bn: float
    deposits_bn: float
    gold_bn: float


@dataclass(frozen=True)
class InterventionSnapshot:
    period: str
    release_date: str
    url: str
    trillion_yen: float


@dataclass(frozen=True)
class TicJapan:
    latest_month: str
    previous_month: str
    latest_bn_usd: float
    previous_bn_usd: float

    @property
    def change_bn_usd(self) -> float:
        return self.latest_bn_usd - self.previous_bn_usd


@dataclass(frozen=True)
class ForeignCustody:
    level_bn_usd: float
    weekly_change_bn_usd: float | None


def _month_period(text: str) -> str:
    match = re.search(r"end of\s+([A-Z][a-z]+\s+20\d{2})", text, re.I)
    return match.group(1) if match else "unknown"


def _english_release_date(text: str) -> str:
    match = re.search(r"\b([A-Z][a-z]+\s+\d{1,2},\s+20\d{2})\b", text)
    return match.group(1) if match else "unknown"


def latest_reserve_links(index_html: str) -> tuple[str, str]:
    soup = BeautifulSoup(index_html, "html.parser")
    links: list[str] = []
    for anchor in soup.find_all("a", href=True):
        url = abs_url(MOF_RESERVE_INDEX, anchor["href"])
        if re.search(r"/official_reserve_assets/e\d{4}\.html$", url, re.I) and url not in links:
            links.append(url)
    if len(links) < 2:
        raise RuntimeError(f"reserve index needs at least 2 month links, got {len(links)}")
    return links[0], links[1]


def parse_reserve_page(page_html: str, url: str) -> ReserveSnapshot:
    soup = BeautifulSoup(page_html, "html.parser")
    plain = " ".join(soup.stripped_strings)
    found: dict[str, float] = {}
    for tr in soup.find_all("tr"):
        cells = [" ".join(x.stripped_strings) for x in tr.find_all(["td", "th"])]
        if not cells:
            continue
        label = " ".join(cells[:-1]) if len(cells) > 1 else cells[0]
        value = num(cells[-1]) if len(cells) > 1 else None
        if value is None:
            continue
        lowered = label.lower()
        if "official reserve assets" in lowered and "official_reserve" not in found:
            found["official_reserve"] = value / 1000.0
        elif "foreign currency reserves" in lowered and "fx_reserve" not in found:
            found["fx_reserve"] = value / 1000.0
        elif re.search(r"\bsecurities\b", lowered) and "securities" not in found:
            found["securities"] = value / 1000.0
        elif "deposits with" in lowered and "deposits" not in found:
            found["deposits"] = value / 1000.0
        elif re.search(r"\bgold\b", lowered) and "gold" not in found:
            found["gold"] = value / 1000.0
    required = {"official_reserve", "fx_reserve", "securities", "deposits", "gold"}
    missing = required - set(found)
    if missing:
        raise RuntimeError(f"reserve page missing {sorted(missing)}")
    return ReserveSnapshot(
        period=_month_period(plain),
        release_date=_english_release_date(plain),
        url=url,
        official_reserve_bn=found["official_reserve"],
        fx_reserve_bn=found["fx_reserve"],
        securities_bn=found["securities"],
        deposits_bn=found["deposits"],
        gold_bn=found["gold"],
    )


def latest_intervention_link(index_html: str) -> str:
    soup = BeautifulSoup(index_html, "html.parser")
    for anchor in soup.find_all("a", href=True):
        url = abs_url(MOF_INTERVENTION_INDEX, anchor["href"])
        if re.search(r"/feio/data/monthly/20\d{6}\.html$", url):
            return url
    raise RuntimeError("latest monthly intervention link not found")


def _parse_japanese_yen_amount(text: str) -> float:
    compact = re.sub(r"\s+", "", text.replace("，", ","))
    match = re.search(r"外国為替平衡操作額[^0-9０-９]*(?:(\d[\d,]*)兆)?(?:(\d[\d,]*)億)?円", compact)
    if match:
        cho = float((match.group(1) or "0").replace(",", ""))
        oku = float((match.group(2) or "0").replace(",", ""))
        return cho + oku / 10000.0
    zero = re.search(r"外国為替平衡操作額[^0-9０-９]*0円", compact)
    if zero:
        return 0.0
    raise RuntimeError("intervention amount not found")


def parse_intervention_page(page_html: str, url: str) -> InterventionSnapshot:
    soup = BeautifulSoup(page_html, "html.parser")
    plain = " ".join(soup.stripped_strings)
    period_match = re.search(r"(令和\d+年\d+月\d+日)[～~](令和\d+年\d+月\d+日)", plain)
    release_match = re.search(r"(令和\d+年\d+月\d+日)", plain)
    return InterventionSnapshot(
        period="～".join(period_match.groups()) if period_match else "unknown",
        release_date=release_match.group(1) if release_match else "unknown",
        url=url,
        trillion_yen=_parse_japanese_yen_amount(plain),
    )


def parse_tic_table5(page_html: str) -> TicJapan:
    soup = BeautifulSoup(page_html, "html.parser")
    months: list[str] = []
    japan: list[float] = []
    for tr in soup.find_all("tr"):
        cells = [" ".join(x.stripped_strings) for x in tr.find_all(["td", "th"])]
        if not cells:
            continue
        if cells[0].strip().lower() == "country":
            months = [c.strip() for c in cells[1:] if re.fullmatch(r"20\d{2}-\d{2}", c.strip())]
        if cells[0].strip().lower() == "japan":
            japan = [float(x.replace(",", "")) for x in cells[1:] if re.fullmatch(r"[\d,.]+", x.strip())]
    if len(months) < 2 or len(japan) < 2:
        raise RuntimeError("TIC Table 5 Japan row/header not found")
    return TicJapan(months[0], months[1], japan[0], japan[1])


def parse_h41_treasury_custody(page_html: str) -> ForeignCustody:
    soup = BeautifulSoup(page_html, "html.parser")
    for tr in soup.find_all("tr"):
        cells = [" ".join(x.stripped_strings) for x in tr.find_all(["td", "th"])]
        if not cells:
            continue
        if cells[0].strip().lower() == "marketable u.s. treasury securities":
            values = [num(x) for x in cells[1:]]
            values = [x for x in values if x is not None]
            if values:
                return ForeignCustody(
                    level_bn_usd=values[0] / 1000.0,
                    weekly_change_bn_usd=None if len(values) < 2 else values[1] / 1000.0,
                )
    raise RuntimeError("H.4.1 marketable U.S. Treasury custody row not found")


def delta(cur: float, prev: float) -> float:
    return cur - prev


def classify_events(*, first: bool, state: dict, current: ReserveSnapshot | None, previous: ReserveSnapshot | None,
                    intervention: InterventionSnapshot | None, tic: TicJapan | None,
                    fima_level_bn: float | None, fima_release_date: str | None,
                    custody: ForeignCustody | None) -> list[dict]:
    events: list[dict] = []
    old = state.get("source_ids") or {}
    reserve_new = bool(current and current.period != old.get("reserve_period"))
    intervention_new = bool(intervention and intervention.url != old.get("intervention_url"))
    tic_new = bool(tic and tic.latest_month != old.get("tic_month"))
    fima_new = bool(fima_release_date and fima_release_date != old.get("h41_release"))

    reserve_material = False
    if current and previous:
        total_drop = delta(current.official_reserve_bn, previous.official_reserve_bn)
        sec_drop = delta(current.securities_bn, previous.securities_bn)
        fx_cross = current.fx_reserve_bn < FX_RESERVE_FLOOR_BN <= previous.fx_reserve_bn
        reserve_material = total_drop <= -OFFICIAL_RESERVE_DROP_HIGH_BN or sec_drop <= -SECURITIES_DROP_HIGH_BN or fx_cross

        if reserve_new or (first and reserve_material):
            if current.fx_reserve_bn < FX_RESERVE_FLOOR_BN <= previous.fx_reserve_bn:
                events.append({"kind": "fx_reserve_below_1t", "severity": "HIGH"})
            if total_drop <= -OFFICIAL_RESERVE_DROP_HIGH_BN:
                events.append({"kind": "official_reserve_drop", "severity": "HIGH"})
            if sec_drop <= -SECURITIES_DROP_HIGH_BN:
                events.append({"kind": "securities_drop", "severity": "HIGH"})

    if intervention and (intervention_new or (first and intervention.trillion_yen >= INTERVENTION_HIGH_TRILLION_YEN)):
        if intervention.trillion_yen >= INTERVENTION_HIGH_TRILLION_YEN:
            sev = "CRITICAL" if intervention.trillion_yen >= INTERVENTION_CRITICAL_TRILLION_YEN else "HIGH"
            events.append({"kind": "large_intervention", "severity": sev})

    if tic and tic_new and tic.change_bn_usd <= -TIC_JAPAN_DROP_HIGH_BN:
        events.append({"kind": "tic_japan_sale", "severity": "HIGH"})

    if fima_level_bn is not None and fima_new and fima_level_bn >= FIMA_ACTIVE_MIN_BN:
        events.append({"kind": "fima_active", "severity": "MITIGATION"})

    if custody and custody.weekly_change_bn_usd is not None and fima_new and custody.weekly_change_bn_usd <= -FOREIGN_CUSTODY_DROP_HIGH_BN:
        events.append({"kind": "foreign_custody_drop", "severity": "WATCH"})

    kinds = {x["kind"] for x in events}
    if "large_intervention" in kinds and "securities_drop" in kinds:
        events.append({"kind": "funding_supply_combo", "severity": "CRITICAL"})
    return events


def event_text(kind: str) -> str:
    return {
        "fx_reserve_below_1t": "외화준비자산이 1조달러 아래로 내려감 — 총 공식 준비자산과는 다른 항목",
        "official_reserve_drop": "총 공식 준비자산 월간 감소폭이 500억달러를 넘음",
        "securities_drop": "외화준비자산 내 증권 감소폭이 500억달러를 넘음 — 미국채 매도 후보 신호",
        "large_intervention": "월간 엔화 방어 개입액이 5조엔을 넘음",
        "tic_japan_sale": "TIC에서 일본의 미국 국채 보유액이 한 달 250억달러 이상 감소",
        "fima_active": "Fed H.4.1 외국공식 레포 사용이 0보다 커짐 — 미국채 직접매도 대안 경로 활성화 가능성",
        "foreign_custody_drop": "Fed 보관 외국공식기관 미국 국채가 주간 250억달러 이상 감소",
        "funding_supply_combo": "대규모 엔화 개입과 외화증권 급감이 함께 확인됨 — 미국채 공급압력 후보 강화",
    }.get(kind, kind)


def fmt_usd_bn(value: float, quote, *, signed: bool = False) -> str:
    sign = "+" if signed and value > 0 else ""
    unit = f"{sign}{value * 10:,.1f}억달러"
    if quote is None:
        return unit
    won = value * 1_000_000_000.0 * quote.usdkrw
    return f"{unit} (약 {format_krw(won)})"


def fmt_yen_trillion(value: float, quote) -> str:
    if quote is None:
        return f"{value:,.4f}조엔"
    won = value * 1_000_000_000_000.0 * quote.krw_per_yen
    usd = won / quote.usdkrw
    return f"{value:,.4f}조엔 (약 {format_krw(won)} · {usd / 1_000_000_000.0:,.1f}십억달러)"


def build_alert(*, now: dt.datetime, events: list[dict], current: ReserveSnapshot | None,
                previous: ReserveSnapshot | None, intervention: InterventionSnapshot | None,
                tic: TicJapan | None, fima_level_bn: float | None, fima_release_date: str | None,
                custody: ForeignCustody | None, quote) -> tuple[str, str]:
    rank = {"MITIGATION": 0, "WATCH": 1, "HIGH": 2, "CRITICAL": 3}
    severity = max((x["severity"] for x in events), key=lambda x: rank[x])
    label = {"MITIGATION": "완화 신호", "WATCH": "1단계 · 주의", "HIGH": "2단계 · 강화", "CRITICAL": "3단계 · 위험"}[severity]
    badge = {"MITIGATION": "🟢", "WATCH": "🟡", "HIGH": "🟠", "CRITICAL": "🔴"}[severity]
    title = f"{badge} 일본 외환개입 재원·미국채 공급압력 {label}"

    lines = ["<b>핵심 판정</b>"]
    for event in events:
        lines.append(f"• {html.escape(event_text(event['kind']))}")

    if current and previous:
        total_d = delta(current.official_reserve_bn, previous.official_reserve_bn)
        fx_d = delta(current.fx_reserve_bn, previous.fx_reserve_bn)
        sec_d = delta(current.securities_bn, previous.securities_bn)
        dep_d = delta(current.deposits_bn, previous.deposits_bn)
        gold_d = delta(current.gold_bn, previous.gold_bn)
        lines += [
            "",
            "<b>외환보유액 — 분모를 반드시 분리</b>",
            f"• 총 공식 준비자산: <b>{fmt_usd_bn(current.official_reserve_bn, quote)}</b> / 전월 {fmt_usd_bn(total_d, quote, signed=True)}",
            f"  └ <b>1조달러 하회 아님</b> · 기준월 {html.escape(current.period)}",
            f"• 외화준비자산: <b>{fmt_usd_bn(current.fx_reserve_bn, quote)}</b> / 전월 {fmt_usd_bn(fx_d, quote, signed=True)}",
            f"  └ {'<b>1조달러 하회</b>' if current.fx_reserve_bn < 1000 else '1조달러 상회'}",
            f"• 외화증권: <b>{fmt_usd_bn(current.securities_bn, quote)}</b> / 전월 {fmt_usd_bn(sec_d, quote, signed=True)}",
            f"• 예치금: {fmt_usd_bn(current.deposits_bn, quote)} / 전월 {fmt_usd_bn(dep_d, quote, signed=True)}",
            f"• 금: {fmt_usd_bn(current.gold_bn, quote)} / 전월 {fmt_usd_bn(gold_d, quote, signed=True)}",
        ]

    if intervention:
        lines += [
            "",
            "<b>외환시장 개입</b>",
            f"• 최근 월간 개입액: <b>{fmt_yen_trillion(intervention.trillion_yen, quote)}</b>",
            f"• 대상 기간: {html.escape(intervention.period)}",
        ]

    lines += [
        "",
        "<b>미국채 매도 판정</b>",
        "• 외화증권 감소액을 곧바로 ‘일본의 미국채 매도액’으로 확정하지 않습니다.",
        "• 외화증권에는 미국채 외 자산과 평가변동·결제시차가 섞일 수 있어 <b>TIC 국가별 보유액으로 후행 확인</b>합니다.",
    ]
    if tic:
        lines.append(
            f"• TIC 일본 미국채: {html.escape(tic.latest_month)} <b>{fmt_usd_bn(tic.latest_bn_usd, quote)}</b> / 전월 {fmt_usd_bn(tic.change_bn_usd, quote, signed=True)}"
        )
        lines.append("  └ 8월 개입분과 동일월 확인치가 아직 아니면 ‘후행 미확정’으로 유지")

    lines += ["", "<b>FIMA·미국채 시장 완충 확인</b>"]
    if fima_level_bn is None:
        lines.append("• Fed H.4.1 외국공식 레포: 확인 실패")
    else:
        fima_text = fmt_usd_bn(fima_level_bn, quote)
        lines.append(f"• Fed H.4.1 외국공식 레포: <b>{fima_text}</b> · {html.escape(fima_release_date or '기준일 미상')}")
        lines.append(f"  └ 일본 단독 사용액이 아님 · FIMA 제도상 거래상대방당 한도 <b>{FIMA_LIMIT_BN:.0f}십억달러</b>")
    if custody:
        change = "확인 불가" if custody.weekly_change_bn_usd is None else fmt_usd_bn(custody.weekly_change_bn_usd, quote, signed=True)
        lines.append(f"• Fed 보관 외국공식기관 미국 국채: <b>{fmt_usd_bn(custody.level_bn_usd, quote)}</b> / 주간 {change}")
        lines.append("  └ 일본만의 수치가 아니므로 미국채 공급압력 교차검증용")

    lines += [
        "",
        "<b>최종 판정</b>",
        "• 경로: 엔화 방어 개입 → 예치금·외화증권 재원 확인 → FIMA 대체 여부 → TIC 일본 미국채 보유액 → 미국 장기금리·입찰로 후행 확인",
        "• 가장 현실적인 실패 경로: 반복 개입이 이어지는데 FIMA를 쓰지 못하고 외화증권 매각이 지속 → 미국 장기물 공급압력·기간프리미엄 상승.",
        "• 완화 경로: BOJ 정상화로 엔화가 자체 강세를 보이거나 FIMA가 실제 사용돼 미국채 현물 매도 필요가 줄어드는 경우.",
        "",
        "<b>원문</b>",
    ]
    if current:
        lines.append(f"• <a href=\"{html.escape(current.url)}\">일본 재무성 외환보유액</a>")
    if intervention:
        lines.append(f"• <a href=\"{html.escape(intervention.url)}\">일본 재무성 외환시장 개입액</a>")
    lines += [
        f"• <a href=\"{TIC_TABLE5}\">미 재무부 TIC 일본 미국채 보유액</a>",
        f"• <a href=\"{FED_H41}\">Fed H.4.1</a> · <a href=\"{FED_FIMA}\">FIMA 설명</a>",
        "",
        f"조회 {now.strftime('%Y-%m-%d %H:%M:%S')} KST",
    ]
    return title, "\n".join(lines) + "\n"


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
    current = previous = None
    intervention = None
    tic = None
    fima_level_bn = None
    fima_release_date = None
    custody = None

    try:
        reserve_index = source("Japan MOF reserve index", MOF_RESERVE_INDEX, now)
        cur_url, prev_url = latest_reserve_links(reserve_index)
        current = parse_reserve_page(source("Japan MOF reserves current", cur_url, now), cur_url)
        previous = parse_reserve_page(source("Japan MOF reserves previous", prev_url, now), prev_url)
    except Exception as exc:
        errors.append(f"외환보유액: {type(exc).__name__}: {exc}")

    try:
        intervention_index = source("Japan MOF intervention index", MOF_INTERVENTION_INDEX, now)
        intervention_url = latest_intervention_link(intervention_index)
        intervention = parse_intervention_page(source("Japan MOF intervention latest", intervention_url, now), intervention_url)
    except Exception as exc:
        errors.append(f"개입액: {type(exc).__name__}: {exc}")

    try:
        tic = parse_tic_table5(source("US Treasury TIC Table 5", TIC_TABLE5, now))
    except Exception as exc:
        errors.append(f"TIC: {type(exc).__name__}: {exc}")

    try:
        h41_text = source("Federal Reserve H.4.1", FED_H41, now)
        fima = parse_h41_foreign_official_repo(h41_text)
        fima_level_bn = fima.level_bn_usd
        fima_release_date = fima.release_date
        custody = parse_h41_treasury_custody(h41_text)
    except Exception as exc:
        errors.append(f"Fed H.4.1: {type(exc).__name__}: {exc}")

    try:
        quote = latest_jpy_krw()
    except Exception as exc:
        quote = None
        errors.append(f"원화 환산: {type(exc).__name__}: {exc}")

    events = classify_events(
        first=first,
        state=state,
        current=current,
        previous=previous,
        intervention=intervention,
        tic=tic,
        fima_level_bn=fima_level_bn,
        fima_release_date=fima_release_date,
        custody=custody,
    )

    pending = {
        "initialized": True,
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "source_ids": {
            "reserve_period": current.period if current else None,
            "intervention_url": intervention.url if intervention else None,
            "tic_month": tic.latest_month if tic else None,
            "h41_release": fima_release_date,
        },
        "snapshot": {
            "official_reserve_bn": current.official_reserve_bn if current else None,
            "fx_reserve_bn": current.fx_reserve_bn if current else None,
            "securities_bn": current.securities_bn if current else None,
            "deposits_bn": current.deposits_bn if current else None,
            "gold_bn": current.gold_bn if current else None,
            "intervention_trillion_yen": intervention.trillion_yen if intervention else None,
            "tic_japan_bn": tic.latest_bn_usd if tic else None,
            "fima_bn": fima_level_bn,
            "foreign_custody_bn": custody.level_bn_usd if custody else None,
        },
    }
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    status = [
        "# 일본 외환개입 재원·미국채 공급압력 감시",
        "",
        f"- 조회: {now.isoformat(timespec='seconds')}",
        f"- 상태: {'현재 중요 신호 1회 초기 발송' if first and events else ('새 경보 생성' if events else '새 경보 없음')}",
        "- 분리 원칙: 총 공식 준비자산 ≠ 외화준비자산 ≠ 외화증권 ≠ 일본 미국채 보유액",
        "- 확정 원칙: 외화증권 감소는 TIC 확인 전 미국채 매도액으로 확정하지 않음",
    ]
    if errors:
        status += ["", "## 부분 확인"] + [f"- {html.escape(x)}" for x in errors]
    STATUS_PATH.write_text("\n".join(status) + "\n", encoding="utf-8")

    if not events:
        return 0

    title, body = build_alert(
        now=now,
        events=events,
        current=current,
        previous=previous,
        intervention=intervention,
        tic=tic,
        fima_level_bn=fima_level_bn,
        fima_release_date=fima_release_date,
        custody=custody,
        quote=quote,
    )
    TITLE_PATH.write_text(title, encoding="utf-8")
    ALERT_PATH.write_text(body, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
