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
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
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
            if INDEX_WORDS.search(label):
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
    return {
        "event_type": "official_fiscal_plan_publication",
        "id": "official_fiscal_plan:" + hashlib.sha256(url.encode()).hexdigest()[:24],
        "published_date": published,
        "title": label,
        "source_url": url,
        "stage": "공식안 공개(입법·집행 전)",
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
    return f"{usd / Decimal('1000000000'):,.2f}억달러" if False else (
        f"{usd / Decimal('1000000000000'):,.3f}조달러"
    )


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
        status.append("공식 Debt to the Penny: " + debt["record_date"])
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

    event_id = None
    kind = None
    fx = None
    fx_basis = ""
    if plan is not None:
        event_id = plan["id"]
        kind = "official_plan"
    elif debt is not None:
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
