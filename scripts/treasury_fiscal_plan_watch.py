#!/usr/bin/env python3
"""Event-level U.S. fiscal consolidation plan + $41T federal debt gate.

Runs INSIDE the pre-existing QRA GitHub Actions workflow and uses its existing
Telegram bot. Articles/URLs are discovery aids, not event identities.
Only a newly published primary-source U.S. fiscal plan or an OFFICIAL Treasury
debt milestone can produce a message. No alert on unchanged news or intention.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "treasury_fiscal_plan_state.json"
OUT = ROOT / "out"
ALERT = OUT / "treasury_fiscal_plan_alert.txt"
DETAIL = OUT / "treasury_fiscal_plan_detail.json"
NEXT = OUT / "treasury_fiscal_plan_state_next.json"
STATUS = OUT / "treasury_fiscal_plan_status.md"

# Monthly Treasury Statement is a separate published statistical release,
# not a proposal, not a Treasury auction, and not a debt-to-the-penny milestone.
MTS_ROOT = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/mts/"
MTS_MONTHLY_API = (
    MTS_ROOT + "mts_receipts_outlays_deficit_surplus?"
    "filter=record_date:gte:2024-10-01&sort=-record_date&page%5Bsize%5D=250"
)
MTS_TARIFF_API = MTS_ROOT + "mts_table_4"
MTS_INTEREST_API = MTS_ROOT + "mts_table_9"
MTS_PAGE = (
    "https://fiscaldata.treasury.gov/datasets/monthly-treasury-statement/"
    "summary-of-receipts-outlays-and-the-deficit-surplus-of-the-u-s-government"
)
FIRST_BUDGET_PERIOD = "2026-09-30"

KST = ZoneInfo("Asia/Seoul")
ET = ZoneInfo("America/New_York")

DEBT_API = (
    "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/"
    "accounting/od/debt_to_penny?sort=-record_date&page%5Bsize%5D=7"
)
DEBT_PAGE = "https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/"
QRA_PAGE = (
    "https://home.treasury.gov/policy-issues/financing-the-government/"
    "quarterly-refunding/most-recent-quarterly-refunding-documents"
)
SOURCE_INDEXES = (
    "https://home.treasury.gov/news/press-releases",
    "https://www.whitehouse.gov/releases/",
    "https://www.whitehouse.gov/omb/information-resources/budget/",
    "https://www.whitehouse.gov/omb/information-resources/legislative/supplementals-amendments-and-releases/",
)
# Only a public, dated formal plan after the interview. The 2026-09-08 comments
# and 2026-10-08 NPolicy Summit interview are not newly adopted fiscal policy.
EARLIEST_PLAN = "2026-10-09"
START_MILESTONE = 41
ALLOWED_HOSTS = {"home.treasury.gov", "www.whitehouse.gov"}
INDEX_WORDS = re.compile(
    r"fiscal|deficit|debt|budget|spending|borrow|consolidat|"
    r"financial framework|rescission|federal savings|reconciliation",
    re.I,
)
PLAN_WORDS = re.compile(
    r"fiscal consolidation (?:plan|package|framework)|"
    r"deficit.reduction (?:plan|package|framework|proposal)|"
    r"debt.reduction (?:plan|package|proposal)|"
    r"(?:federal|national) (?:budget|fiscal) (?:reform|framework|plan)|"
    r"multi.year (?:federal )?(?:savings|spending cuts)",
    re.I,
)
FINAL_WORDS = re.compile(
    r"\b(?:unveiled|released|published|submitted|presented|enacted|signed|"
    r"adopted|announces|announced|introduces|introduced)\b",
    re.I,
)
FUTURE_ONLY = re.compile(
    r"\b(?:will|would|may|might|plans to|working on|preparing to|expected to|"
    r"scheduled to|intends to)\b.{0,70}\b(?:unveil|release|publish|introduce|submit)\b",
    re.I,
)


def fetch_text(url: str, attempts: int = 2, timeout: int = 17) -> str:
    errors = []
    for i in range(attempts):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 KHS-Fiscal-Plan-Watch/1.0",
                         "Accept": "application/json,text/html,*/*;q=0.8",
                         "Cache-Control": "no-cache"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read().decode("utf-8-sig", "replace")
        except Exception as exc:
            errors.append(f"{type(exc).__name__}:{exc}")
            if i < attempts - 1:
                time.sleep(i + 1)
    raise RuntimeError("; ".join(errors))


class OfficialLinks(HTMLParser):
    def __init__(self, base: str):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.anchor: str | None = None
        self.words: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self.anchor = dict(attrs).get("href")
            self.words = []

    def handle_data(self, value):
        if self.anchor is not None:
            self.words.append(value)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.anchor is not None:
            label = re.sub(r"\s+", " ", html.unescape(" ".join(self.words))).strip()
            url = urllib.parse.urljoin(self.base, self.anchor)
            host = urllib.parse.urlsplit(url).hostname
            if host in ALLOWED_HOSTS and label:
                self.links.append((label, url.split("#")[0]))
            self.anchor = None
            self.words = []


def official_plan_links(html_indexes: dict[str, str]) -> list[tuple[str, str]]:
    unique: dict[str, str] = {}
    for base, raw in html_indexes.items():
        p = OfficialLinks(base)
        p.feed(raw)
        for label, url in p.links:
            parsed = urllib.parse.urlsplit(url)
            path = parsed.path.lower()
            if parsed.hostname == "home.treasury.gov":
                is_release = bool(re.fullmatch(r"/news/press-releases/[a-z]{2}[0-9]+/?", path))
            else:
                is_release = (
                    bool(re.match(r"/(?:releases|briefings-statements|fact-sheets|presidential-actions)/20[0-9]{2}/", path))
                    or (path.endswith(".pdf")
                        and re.search(r"/wp-content/uploads/(?:2026/11|2026/12|2027)/", path)
                        and INDEX_WORDS.search(label))
                )
            if is_release and INDEX_WORDS.search(label + " " + path):
                unique.setdefault(url, label)
    return [(title, url) for url, title in list(unique.items())[:24]]


def parsed_date(body: str, url: str) -> str | None:
    candidates = [
        re.search(r'"datePublished"\s*:\s*"(\d{4}-\d{2}-\d{2})', body),
        re.search(r'property="article:published_time"[^>]+content="(\d{4}-\d{2}-\d{2})', body),
        re.search(r'<time[^>]+datetime="(\d{4}-\d{2}-\d{2})', body),
        re.search(r'/(20\d{2})/(0[1-9]|1[0-2])/([0-3]\d)/', url),
    ]
    for m in candidates:
        if not m:
            continue
        if len(m.groups()) == 1:
            return m.group(1)
        return "-".join(m.groups())
    # Drupal/White House primary pages may lack schema.org metadata:
    # accept a visible date ONLY from the article header after the first h1.
    article = re.split(r"<h1[^>]*>", body, maxsplit=1, flags=re.I)
    if len(article) > 1:
        header = article[1][:2200]
        visible = re.search(
            r"(January|February|March|April|May|June|July|August|September|"
            r"October|November|December)\s+(\d{1,2}),\s+(20\d{2})",
            re.sub(r"<[^>]+>", " ", header), re.I,
        )
        if visible:
            months = {m.lower(): i for i, m in enumerate(
                ("January","February","March","April","May","June",
                 "July","August","September","October","November","December"), 1)}
            return f"{visible.group(3)}-{months[visible.group(1).lower()]:02d}-{int(visible.group(2)):02d}"
    # Undated static index pages / OMB legacy budget items must never be
    # mistaken for a newly released fiscal plan.
    return None


def plain_html(body: str) -> str:
    body = re.sub(r"<script\b[^>]*>.*?</script>", " ", body, flags=re.I | re.S)
    body = re.sub(r"<style\b[^>]*>.*?</style>", " ", body, flags=re.I | re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", body))).strip()


def classify_plan(label: str, page: str, url: str) -> dict | None:
    published = parsed_date(page, url)
    if not published or published < EARLIEST_PLAN:
        return None
    narrative = plain_html(page)
    # The release must concern U.S. federal finances, not debt of another
    # country, a private corporation or an ordinary Treasury auction.
    if not re.search(
        r"United States|U\.S\. (?:government|federal|budget)|"
        r"White House|U\.S\. Treasury|American federal|federal (?:spending|deficit|budget)",
        narrative, re.I,
    ):
        return None
    if not PLAN_WORDS.search(label + " " + narrative[:20000]):
        return None
    relevant = " ".join(
        m.group(0) for m in re.finditer(
            r".{0,140}(?:fiscal consolidation|deficit reduction|debt reduction|"
            r"fiscal reform|budget framework|multi.year savings).{0,160}",
            narrative[:16000], re.I,
        )
    )
    if not relevant or not FINAL_WORDS.search(relevant):
        return None
    if FUTURE_ONLY.search(relevant) and not re.search(
        r"\b(?:has|have|today|now)\s+(?:announced|released|published|"
        r"submitted|unveiled|introduced|presented)\b", relevant, re.I,
    ):
        return None
    # The official primary source provides a new published document. This
    # does not yet mean Congress has enacted the proposal.
    # Same-date White House/Treasury announcements of the same fiscal
    # framework are ONE policy event, regardless of the URL or headline.
    # A new dated formal release may be a subsequent material update.
    return {
        "event_type": "official_fiscal_plan_publication",
        "id": "official_federal_fiscal_framework:" + published.replace("-", ""),
        "published_date": published,
        "title": label,
        "source_url": url,
        "stage": "공식 재정계획 문서 공개(입법·집행 여부 별도 확인)",
    }


def parse_debt(payload: object) -> dict:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("Fiscal Data Debt to the Penny 응답 형식 불일치")
    valid = []
    today_us = datetime.now(ET).date().isoformat()
    for raw in payload["data"]:
        if not isinstance(raw, dict):
            continue
        day = str(raw.get("record_date") or "")[:10]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) or day > today_us:
            continue
        try:
            total = Decimal(str(raw["tot_pub_debt_out_amt"]))
            public = Decimal(str(raw["debt_held_public_amt"]))
            intra = Decimal(str(raw["intragov_hold_amt"]))
        except (KeyError, ValueError, InvalidOperation):
            continue
        if not (total > 0 and public > 0 and intra > 0):
            continue
        if abs(total - public - intra) > Decimal("0.02"):
            raise ValueError("총국가채무 != 민간보유+정부내부 보유: 공식자료 일치 오류")
        valid.append((day, total, public, intra))
    if not valid:
        raise ValueError("현재 날짜 이전 공식 국가채무 관측치 없음")
    day, total, public, intra = max(valid, key=lambda x: x[0])
    return {"record_date": day, "total": str(total),
            "public": str(public), "intragov": str(intra)}


def fmt_bn(usd: Decimal) -> str:
    return f"{usd / Decimal('1000000000000'):,.3f}조달러"


def fx_quote() -> tuple[Decimal | None, str]:
    try:
        from fx_api import daily_krw
        q = daily_krw()
        return Decimal(str(q.rate)), str(q.basis)
    except Exception as exc:
        return None, f"환율 확인 불가({type(exc).__name__})"


def fmt_krw(usd: Decimal, fx: Decimal | None) -> str:
    if fx is None:
        return "원화 환산 확인 불가"
    won = usd * fx
    gyeong = int(won // Decimal("10000000000000000"))
    trillion = int((won % Decimal("10000000000000000")) // Decimal("1000000000000"))
    hundred_m = int((won % Decimal("1000000000000")) // Decimal("100000000"))
    if gyeong:
        return f"약 {gyeong}경{trillion:,}조원"
    if trillion:
        return f"약 {trillion:,}조{hundred_m:,}억원"
    return f"약 {hundred_m:,}억원"


def report_debt_milestone(level: int, d: dict, fx: Decimal | None, fx_basis: str):
    total = Decimal(d["total"])
    public = Decimal(d["public"])
    intra = Decimal(d["intragov"])
    heading = f"미 재무부 국가채무 {level}조달러 공식 돌파"
    body = "\n".join([
        "미국 국가채무 공식 임계값 돌파 — 기사상의 반올림 표현과 구분",
        f"• 기준일: {d['record_date']} (재무부 Fiscal Data 원문)",
        f"• 총채무: {fmt_bn(total)} ({fmt_krw(total, fx)})",
        f"• 민간 등 정부 외부 보유: {fmt_bn(public)} ({fmt_krw(public, fx)})",
        f"• 정부 내부 보유: {fmt_bn(intra)} ({fmt_krw(intra, fx)})",
        f"• 확인된 임계값: {level}조달러 ({fmt_krw(Decimal(level)*Decimal('1000000000000'), fx)})",
        "• 총채무 증가만으로 분기 신규 국채 발행액이나 재정적자액을 단정하지 않습니다.",
        "• 다음 확인: QRA 민간보유 순시장성 차입·TGA·만기별 발행·예산지출/세입.",
        f"• 환율: {fx_basis}",
        f"공식 원문: {DEBT_PAGE}",
    ])
    return heading, body


def report_plan(p: dict, d: dict | None, fx: Decimal | None, fx_basis: str):
    heading = "미국 재정건전화 공식안 공개 — 규모·발행 영향 검증"
    lines = [
        "발언·초안·정식 발표·법안 통과를 구분합니다.",
        f"• 단계: {p['stage']} · 발표일 {p['published_date']}",
        f"• 공식 발표: {p['title']}",
        "• 확정 총 감축액·부문별 삭감·세율·시행일은 공식 첨부표와 입법자료로 별도 확인해야 합니다.",
        "• 채무·재정적자 감소 목표와 민간보유 순차입·총국채발행·재발행은 서로 다릅니다.",
        "• 시장 판정: QRA 전망·2/10/30년 금리·실질금리·기간프리미엄을 같은 기준일로 비교.",
    ]
    if d:
        total = Decimal(d["total"])
        lines.append(
            f"• 현재 총국가채무 {d['record_date']}: {fmt_bn(total)} ({fmt_krw(total, fx)})"
        )
    lines += [f"• 환율: {fx_basis}", f"공식 계획: {p['source_url']}",
              f"QRA 발행 추정·만기별 공급: {QRA_PAGE}"]
    return heading, "\n".join(lines)



def _fiscal_year(day: date) -> int:
    return day.year + (1 if day.month >= 10 else 0)


def _fiscal_months(fiscal_year: int, months_elapsed: int) -> list[str]:
    if not (1 <= months_elapsed <= 12):
        raise ValueError("회계연도 누적 개월 수 범위 오류")
    out = []
    for i in range(months_elapsed):
        month = 10 + i
        year = fiscal_year - 1
        if month > 12:
            month -= 12
            year = fiscal_year
        last_day = (
            date(year + 1, 1, 1) if month == 12
            else date(year, month + 1, 1)
        ) - timedelta(days=1)
        out.append(last_day.isoformat())
    return out


def parse_mts_budget(payload: object, as_of: date | None = None) -> dict:
    """Trust only complete monthly Treasury rows in *millions* of dollars.

    Table 1 mixes historical and FYTD rows. The dedicated monthly summary
    has one amount category per month; summing a complete FY avoids silent
    double counting and 1,000,000x unit mistakes.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("MTS 공식 API 응답 형식 불일치")
    meta = payload.get("meta") or {}
    if isinstance(meta, dict) and int(meta.get("total-pages") or 1) > 1:
        raise ValueError("MTS 공식 API 결과 페이지가 잘림")
    as_of = as_of or datetime.now(ET).date()
    categories = {
        "receipts": "receipts",
        "outlays": "outlays",
        "deficit/surplus (-)": "deficit",
    }
    observations: dict[tuple[str, str], Decimal] = {}
    for raw in payload["data"]:
        if not isinstance(raw, dict):
            continue
        day = str(raw.get("record_date") or "")[:10]
        category = re.sub(r"\s+", " ", str(raw.get("amt_category") or "").strip().lower())
        if category not in categories:
            continue
        try:
            parsed = date.fromisoformat(day)
            if parsed > as_of or parsed.day != (
                (date(parsed.year + 1, 1, 1) if parsed.month == 12
                 else date(parsed.year, parsed.month + 1, 1)) - timedelta(days=1)
            ).day:
                continue
            fy_raw = str(raw.get("record_fiscal_year") or "")
            if fy_raw and int(fy_raw) != _fiscal_year(parsed):
                raise ValueError("MTS 공식 회계연도·기준월 불일치")
            amount = Decimal(str(raw["mil_amt"]).replace(",", "")) * Decimal("1000000")
            if not amount.is_finite():
                raise ValueError("MTS 비유한 수치")
        except (TypeError, InvalidOperation, KeyError, ValueError) as exc:
            raise ValueError("MTS 월별 수치·단위 파싱 실패") from exc
        key = (day, categories[category])
        if key in observations and observations[key] != amount:
            raise ValueError("MTS 동일 기준월·항목 값 충돌")
        observations[key] = amount

    eligible = sorted({d for d, _ in observations if d >= FIRST_BUDGET_PERIOD})
    if not eligible:
        raise ValueError("MTS 2026년 9월 이후 공식 발표 수치 없음")
    latest = eligible[-1]
    latest_date = date.fromisoformat(latest)
    if (as_of - latest_date).days > 70:
        raise ValueError("MTS 공식자료 지연 — 과거 월을 신규 발표로 재사용 금지")
    fiscal_year = _fiscal_year(latest_date)
    months_elapsed = (latest_date.month - 10) % 12 + 1
    def totals(fy: int) -> dict[str, Decimal]:
        months = _fiscal_months(fy, months_elapsed)
        result = {"receipts": Decimal("0"), "outlays": Decimal("0"), "deficit": Decimal("0")}
        for day in months:
            values = {}
            for category in result:
                key = (day, category)
                if key not in observations:
                    raise ValueError(f"MTS 월별/전년 동기 항목 누락: {day} {category}")
                values[category] = observations[key]
            residual = values["outlays"] - values["receipts"] - values["deficit"]
            if abs(residual) > Decimal("750000000"):
                raise ValueError(f"MTS 세입·세출·적자 불일치: {day}")
            for k, val in values.items():
                result[k] += val
        return result

    current = totals(fiscal_year)
    previous = totals(fiscal_year - 1)
    if any(current[k] <= 0 or previous[k] <= 0 for k in ("receipts", "outlays")):
        raise ValueError("MTS 세입·세출 유효성 불일치")
    if current["outlays"] > Decimal("20000000000000") or current["receipts"] > Decimal("20000000000000"):
        raise ValueError("MTS 백만 달러와 달러 단위 혼동")
    def serialize(amounts: dict[str, Decimal]) -> dict[str, str]:
        return {k: str(v) for k, v in amounts.items()}
    month_vals = {
        k: str(observations[(latest, k)]) for k in ("receipts", "outlays", "deficit")
    }
    return {
        "record_date": latest,
        "fiscal_year": fiscal_year,
        "months_elapsed": months_elapsed,
        "current": serialize(current),
        "previous": serialize(previous),
        "latest_month": month_vals,
        "source_url": MTS_PAGE,
    }


def parse_mts_tariffs(payload: object, record_date: str) -> dict | None:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("MTS 관세 세입표 응답 형식 불일치")
    meta = payload.get("meta") or {}
    if isinstance(meta, dict) and int(meta.get("total-pages") or 1) > 1:
        raise ValueError("MTS 관세 세입표 페이지 불완전")
    candidates = [
        row for row in payload["data"] if isinstance(row, dict)
        and str(row.get("record_date") or "")[:10] == record_date
        and str(row.get("classification_desc") or "").strip(" :").casefold() == "customs duties"
    ]
    if not candidates:
        return None
    if len(candidates) != 1:
        raise ValueError("MTS 관세 항목 중복 — 임의 선택 금지")
    r = candidates[0]
    keys = ("current_fytd_gross_rcpt_amt", "current_fytd_refund_amt", "current_fytd_net_rcpt_amt")
    try:
        gross, refund, net = [Decimal(str(r[k]).replace(",", "")) for k in keys]
    except (KeyError, ValueError, InvalidOperation) as exc:
        raise ValueError("MTS 관세 총수입·환급·순수입 파싱 실패") from exc
    if min(gross, refund, net) < 0 or abs((gross - refund) - net) > Decimal("10000000"):
        raise ValueError("MTS 관세 총액·환급·순액 검산 실패")
    return {"gross": str(gross), "refund": str(refund), "net": str(net)}


def parse_mts_net_interest(payload: object, record_date: str) -> str | None:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("MTS 순이자 지출표 응답 형식 불일치")
    meta = payload.get("meta") or {}
    if isinstance(meta, dict) and int(meta.get("total-pages") or 1) > 1:
        raise ValueError("MTS 순이자 지출표 페이지 불완전")
    rows = [
        row for row in payload["data"] if isinstance(row, dict)
        and str(row.get("record_date") or "")[:10] == record_date
        and str(row.get("classification_desc") or "").strip(" :").casefold() == "net interest"
    ]
    if len(rows) != 1:
        return None
    try:
        amount = Decimal(str(rows[0]["current_fytd_rcpt_outly_amt"]).replace(",", ""))
        if not amount.is_finite() or amount <= 0:
            return None
        return str(amount)
    except (KeyError, ValueError, InvalidOperation):
        return None


def _usd_ko(usd: Decimal) -> str:
    eok = int((abs(usd) / Decimal("100000000")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    jo, remain = divmod(eok, 10000)
    raw = f"{jo:,}조{remain:04d}억달러" if jo else f"{remain:,}억달러"
    return ("-" if usd < 0 else "") + raw


def report_mts_budget(budget: dict, tariff: dict | None, interest: str | None,
                      fx: Decimal | None, fx_basis: str) -> tuple[str, str]:
    fy = budget["fiscal_year"]
    months = budget["months_elapsed"]
    current = {k: Decimal(v) for k, v in budget["current"].items()}
    prior = {k: Decimal(v) for k, v in budget["previous"].items()}
    month = {k: Decimal(v) for k, v in budget["latest_month"].items()}
    diff = current["deficit"] - prior["deficit"]
    ratio = (
        diff / abs(prior["deficit"]) * Decimal("100")
        if prior["deficit"] else None
    )
    def dual(value: Decimal) -> str:
        return f"{_usd_ko(value)}({fmt_krw(value, fx)})"
    comparison = (
        f"{'증가' if diff > 0 else '감소'} {dual(abs(diff))}"
        + (f" · {abs(ratio):.1f}%" if ratio is not None else "")
    )
    period = f"회계연도 전체 12개월" if months == 12 else f"회계연도 {months}개월 누적"
    title = f"미국 재정적자 공식 월간 재무보고 — {fy}회계연도 {budget['record_date'][-5:]}"
    lines = [
        "미 재무부 월간 재무보고(MTS) 신규 공식자료 · 전년 동기와 비교",
        f"• 기준: {budget['record_date']} · {period} · 조회: {datetime.now(KST).isoformat(timespec='seconds')}",
        f"• 적자: {dual(current['deficit'])} · 전년 동기 {dual(prior['deficit'])} · {comparison}",
        f"• 세입: {dual(current['receipts'])} · 전년 동기 {dual(prior['receipts'])}",
        f"• 세출: {dual(current['outlays'])} · 전년 동기 {dual(prior['outlays'])}",
        f"• 기준월 단월 적자/흑자: {dual(month['deficit'])}",
    ]
    if tariff:
        lines.append(
            f"• 관세 총수입 {dual(Decimal(tariff['gross']))} · "
            f"관세 환급 {dual(Decimal(tariff['refund']))} · "
            f"관세 순수입 {dual(Decimal(tariff['net']))}"
        )
    else:
        lines.append("• 관세 환급·순수입: 해당 기준월 공식 세입표 검증 보류(추정·과거값 미사용)")
    if interest is not None:
        lines.append(f"• 순이자 지출: {dual(Decimal(interest))} · 총이자 지급액과 구분")
    else:
        lines.append("• 순이자 지출: 공식 세출표 확인 전까지 수치 미기재")
    lines.extend([
        "• 원인 판정: 지출 증가와 순세입 변화를 나눠 해석. 관세 환급 총액을 적자 증가액과 동일시하지 않음.",
        "• 반복성: 이자·복지 등 구조적 지출과 관세 환급 같은 정책·회계성 변화를 분리.",
        "• 국채 영향: 재정적자와 실제 순차입·TGA·장단기 국채 발행계획(QRA)은 서로 다른 수치.",
        "• 조기경보: 다음 MTS 세입·세출 변화, 재무부 QRA 만기별 발행계획, 장기물 입찰 수요.",
        f"• 환율: {fx_basis}",
        f"공식 원문: {budget['source_url']}",
        f"미 재무부 분기 국채발행 자료: {QRA_PAGE}",
    ])
    return title, "\n".join(lines)


def load_state() -> dict:
    try:
        value = json.loads(STATE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (ValueError, OSError):
        return {}


def check() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for p in (ALERT, DETAIL, NEXT):
        p.unlink(missing_ok=True)
    state = load_state()
    already = list(state.get("seen_events") or [])
    status = []
    debt = None
    try:
        debt = parse_debt(json.loads(fetch_text(DEBT_API, timeout=18)))
        status.append("공식 Debt to the Penny: " + debt["record_date"] + " · 총잔액 $" + format(Decimal(debt["total"]), ",.2f") + " (41조달러 발언과 공식 잔액 분리)")
    except Exception as exc:
        status.append("국가채무 원천 장애: " + type(exc).__name__ + " " + str(exc)[:110])
    plan = None
    pages = {}
    for source in SOURCE_INDEXES:
        try:
            pages[source] = fetch_text(source, timeout=12)
        except Exception as exc:
            status.append("공식 문서 목록 조회 실패: " + source + " " + type(exc).__name__)
    candidates = official_plan_links(pages)
    status.append(f"공식 문서 후보 수: {len(candidates)}")
    dated = 0
    verified_docs = 0
    examined = []
    for title, url in candidates:
        try:
            page = fetch_text(url, timeout=12)
            verified_docs += 1
            published = parsed_date(page, url)
            if published:
                dated += 1
            if len(examined) < 24:
                examined.append(f"{published or '날짜 미인식'} | {title[:62]} | {url}")
            found = classify_plan(title, page, url)
        except Exception as exc:
            status.append("후보 원문 검증 실패: " + url[:80] + " " + type(exc).__name__)
            continue
        if found and found["id"] not in already:
            plan = found
            break
    status.append(f"공식 후보 직접검증 {verified_docs}개, 게시일 식별 {dated}개")
    status.extend(examined)
    if candidates and dated == 0:
        status.append("주의: 공식 문서 게시일 파싱 결과 0건 — 계획 발표 감시 정확도 점검 필요")

    # A new MTS publication is a distinct fiscal-statistics event.
    # Never substitute a CBO estimate, news headline, or cached number.
    budget = None
    try:
        budget = parse_mts_budget(json.loads(fetch_text(MTS_MONTHLY_API, timeout=18)))
        status.append(
            "미 재무부 MTS 확인: 기준월=" + budget["record_date"]
            + " · 누적개월=" + str(budget["months_elapsed"])
        )
    except Exception as exc:
        status.append("MTS 공식 원천 점검 보류: " + type(exc).__name__ + " " + str(exc)[:140])

    event_id = None
    kind = None
    fx = None
    fx_basis = ""
    if plan is not None:
        event_id = plan["id"]
        kind = "official_plan"
    elif budget is not None:
        candidate = "mts_budget:" + budget["record_date"]
        if candidate not in already:
            event_id = candidate
            kind = "mts_budget"
    if event_id is None and debt is not None:
        total = Decimal(debt["total"])
        level = int(total // Decimal("1000000000000"))
        if level >= START_MILESTONE:
            for milestone in range(START_MILESTONE, level + 1):
                identifier = f"debt_total_crossed:{milestone}T"
                if identifier not in already:
                    event_id, kind = identifier, "debt_milestone"
                    break

    if event_id:
        fx, fx_basis = fx_quote()
        if kind == "official_plan":
            heading, body = report_plan(plan, debt, fx, fx_basis)
        elif kind == "mts_budget":
            customs = None
            net_interest = None
            day = budget["record_date"]
            for label, table, parser in (
                ("관세 세입표", MTS_TARIFF_API, parse_mts_tariffs),
                ("순이자 세출표", MTS_INTEREST_API, parse_mts_net_interest),
            ):
                try:
                    query = table + "?" + urllib.parse.urlencode({
                        "filter": f"record_date:eq:{day}",
                        "page[size]": "900",
                    })
                    data = json.loads(fetch_text(query, timeout=14))
                    parsed = parser(data, day)
                    if label == "관세 세입표":
                        customs = parsed
                    else:
                        net_interest = parsed
                    status.append(label + (" 검증됨" if parsed is not None else " 항목 미확인"))
                except Exception as exc:
                    status.append(label + " 검증 보류: " + type(exc).__name__ + " " + str(exc)[:70])
            heading, body = report_mts_budget(budget, customs, net_interest, fx, fx_basis)
        else:
            heading, body = report_debt_milestone(
                int(event_id.split(":")[1][:-1]), debt, fx, fx_basis
            )
        message = heading + "\n\n" + body
        if len(message) > 4000:
            raise ValueError("Telegram 메시지 길이 초과")
        ALERT.write_text(message + "\n", encoding="utf-8")
        DETAIL.write_text(
            json.dumps({"kind": kind, "event_id": event_id, "plan": plan,
                        "budget": budget if kind == "mts_budget" else None,
                        "debt": debt, "fx": str(fx) if fx else None,
                        "fx_basis": fx_basis,
                        "checked_kst": datetime.now(KST).isoformat(timespec="seconds")},
                       ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
        pending = {**state, "pending_event_id": event_id}
        NEXT.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        status.append("새 공식 사건: " + event_id)
    else:
        if debt is None:
            status.append("국가채무 41조달러 돌파 판정 보류 — 공식 API 응답 없음")
        if not pages:
            status.append("재정건전화 계획 공개 여부 판정 보류 — 공식 목록 조회 실패")
        if debt is not None and pages:
            status.append("신규 공식 계획·41조달러 임계값 없음 → 무알림")
    STATUS.write_text(
        "# 미국 재정건전화 계획·채무 임계값 점검\n\n" +
        "조회: " + datetime.now(KST).isoformat(timespec="seconds") + "\n" +
        "\n".join("• " + s for s in status) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(check())
