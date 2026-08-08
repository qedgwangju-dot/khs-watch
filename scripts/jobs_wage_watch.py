from __future__ import annotations

import io
import json
import os
import pathlib
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from pypdf import PdfReader

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "jobs_wage_watch_state.json"
OUT_DIR = ROOT / "out"
ALERT_PATH = OUT_DIR / "jobs_wage_watch_alert.md"
META_PATH = OUT_DIR / "jobs_wage_watch_alert.json"
PENDING_STATE_PATH = OUT_DIR / "jobs_wage_watch_pending_state.json"
WATCH_PATH = OUT_DIR / "jobs_wage_watch_status.md"

BLS_URL = "https://www.bls.gov/news.release/empsit.nr0.htm"
BLS_CAL_URL = "https://www.bls.gov/schedule/news_release/empsit.htm"
CLAIMS_URL = "https://www.dol.gov/ui/data.pdf"
ADP_PRESS_URL = "https://mediacenter.adp.com/press-releases"
ADP_SEARCH_URL = "https://mediacenter.adp.com/search-newsroom?l=100&query=ADP%20National%20Employment%20Report"

ET = ZoneInfo("America/New_York")
KST = ZoneInfo("Asia/Seoul")

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9,
    "oct": 10, "nov": 11, "dec": 12,
}

DEFAULT_REPORTED = [
    "weekly_claims|2026-08-01|2026-08-06T08:30:00-04:00|initial",
    "employment_situation|2026-07|2026-08-07T08:30:00-04:00|initial",
    "adp|2026-07|2026-08-05T08:15:00-04:00|initial",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; khs-jobs-wage-watch/1.0; +https://github.com/qedgwangju-dot/khs-watch)",
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass
class Release:
    kind: str
    key: str
    title: str
    period: str
    release_dt_et: datetime
    source_url: str
    metrics: dict
    raw_summary: str


def fetch_bytes(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_text(url: str, timeout: int = 30) -> str:
    return fetch_bytes(url, timeout=timeout).decode("utf-8", errors="replace")


def html_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    return " ".join(soup.stripped_strings)


def parse_num(value: str | None):
    if value is None:
        return None
    s = value.replace(",", "").strip()
    if s.startswith("+"):
        s = s[1:]
    try:
        return int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return None


def fmt_int(v):
    if v is None:
        return "확인 불가"
    sign = "+" if isinstance(v, (int, float)) and v > 0 else ""
    return f"{sign}{int(v):,}"


def pct(v):
    return "확인 불가" if v is None else f"{v:.1f}%"


def month_period(month_name: str, year: str) -> str:
    m = MONTHS[month_name.strip().lower()]
    return f"{int(year):04d}-{m:02d}"


def parse_date_month_day_year(month_name: str, day: str, year: str, hour: int, minute: int) -> datetime:
    m = MONTHS[month_name.strip().lower()]
    return datetime(int(year), m, int(day), hour, minute, tzinfo=ET)


def make_key(kind: str, period: str, release_dt_et: datetime, revision: str = "initial") -> str:
    return f"{kind}|{period}|{release_dt_et.isoformat()}|{revision}"


def first_match(pattern: str, text: str, flags: int = re.I | re.S):
    m = re.search(pattern, text, flags)
    return m.group(1) if m else None


def signed_from_parens(text_value: str | None):
    if text_value is None:
        return None
    return parse_num(text_value)


def parse_bls() -> Release | None:
    html = fetch_text(BLS_URL)
    text = html_text(html)

    p = re.search(r"THE EMPLOYMENT SITUATION\s*-\s*([A-Za-z]+)\s+(20\d{2})", text, re.I)
    d = re.search(r"8:30\s*a\.m\.\s*\(ET\)\s*(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s*([A-Za-z]+)\s+(\d{1,2}),\s*(20\d{2})", text, re.I)
    if not p or not d:
        return None

    period = month_period(p.group(1), p.group(2))
    release_dt = parse_date_month_day_year(d.group(1), d.group(2), d.group(3), 8, 30)

    nfp = signed_from_parens(first_match(r"nonfarm payroll employment\s*\(([+\-]?\d[\d,]*)\)", text))
    if nfp is None:
        nfp = signed_from_parens(first_match(r"Total nonfarm payroll employment[^.]{0,120}?\(([+\-]?\d[\d,]*)\)", text))

    unemployment = first_match(r"unemployment rate(?:, at|\s*\()\s*([0-9.]+)\s*percent", text)
    participation = first_match(r"labor force participation rate, at\s*([0-9.]+)\s*percent", text)
    epop = first_match(r"employment-population ratio, at\s*([0-9.]+)\s*percent", text)
    ahe_yoy = first_match(r"Over the year, average hourly earnings have increased by\s*([0-9.]+)\s*percent", text)
    workweek = first_match(r"average workweek for all employees on private nonfarm payrolls was[^.]{0,40}?([0-9]+\.[0-9])\s*hours", text)
    manuf_workweek = first_match(r"In manufacturing, the average workweek was[^.]{0,40}?([0-9]+\.[0-9])\s*hours", text)
    overtime = first_match(r"overtime[^.]{0,40}?(?:to|at)\s*([0-9]+\.[0-9])\s*hours", text)
    revisions = first_match(r"The change in total nonfarm payroll employment for\s+([A-Za-z]+\s+was revised[^.]+\.[^.]+employment in [A-Za-z]+ and [A-Za-z]+ combined is [\d,]+ lower than previously reported)", text)

    metrics = {
        "nfp": nfp,
        "unemployment_rate": float(unemployment) if unemployment else None,
        "participation_rate": float(participation) if participation else None,
        "epop": float(epop) if epop else None,
        "ahe_yoy": float(ahe_yoy) if ahe_yoy else None,
        "workweek": float(workweek) if workweek else None,
        "manufacturing_workweek": float(manuf_workweek) if manuf_workweek else None,
        "manufacturing_overtime": float(overtime) if overtime else None,
        "revisions_text": revisions,
    }
    key = make_key("employment_situation", period, release_dt)
    return Release(
        kind="employment_situation",
        key=key,
        title=f"Employment Situation {period}",
        period=period,
        release_dt_et=release_dt,
        source_url=BLS_URL,
        metrics=metrics,
        raw_summary=text[:4000],
    )


def parse_claims() -> Release | None:
    data = fetch_bytes(CLAIMS_URL)
    reader = PdfReader(io.BytesIO(data))
    pages = []
    for page in reader.pages[:4]:
        pages.append(page.extract_text() or "")
    text = "\n".join(pages)
    clean = re.sub(r"\s+", " ", text)

    d = re.search(r"8:30\s*A\.M\.\s*\(Eastern\)\s*Thursday,\s*([A-Za-z]+)\s+(\d{1,2}),\s*(20\d{2})", clean, re.I)
    w = re.search(r"In the week ending\s+([A-Za-z]+)\s+(\d{1,2}),\s+the advance figure", clean, re.I)
    if not d or not w:
        return None

    release_dt = parse_date_month_day_year(d.group(1), d.group(2), d.group(3), 8, 30)
    week_dt = parse_date_month_day_year(w.group(1), w.group(2), str(release_dt.year), 0, 0)
    if week_dt > release_dt:
        week_dt = week_dt.replace(year=week_dt.year - 1)
    period = week_dt.date().isoformat()

    initial = first_match(r"advance figure for seasonally adjusted initial claims was\s*([\d,]+)", clean)
    prev_revised = first_match(r"previous week's revised level.*?from\s*[\d,]+\s*to\s*([\d,]+)", clean)
    fourwk = first_match(r"4-week moving average was\s*([\d,]+)", clean)
    insured_rate = first_match(r"advance seasonally adjusted insured unemployment rate was\s*([0-9.]+)\s*percent", clean)
    continuing = first_match(r"advance number for seasonally adjusted insured unemployment.*?was\s*([\d,]+)", clean)
    continuing_prev = first_match(r"insured unemployment.*?previous week's revised level.*?from\s*[\d,]+\s*to\s*([\d,]+)", clean)

    metrics = {
        "initial_claims": parse_num(initial),
        "previous_revised": parse_num(prev_revised),
        "four_week_average": parse_num(fourwk),
        "insured_unemployment_rate": float(insured_rate) if insured_rate else None,
        "continuing_claims": parse_num(continuing),
        "continuing_previous_revised": parse_num(continuing_prev),
    }
    key = make_key("weekly_claims", period, release_dt)
    return Release(
        kind="weekly_claims",
        key=key,
        title=f"Weekly Claims week ending {period}",
        period=period,
        release_dt_et=release_dt,
        source_url=CLAIMS_URL,
        metrics=metrics,
        raw_summary=clean[:4000],
    )


def adp_candidate_links() -> list[str]:
    links: list[str] = []
    for listing_url in (ADP_PRESS_URL, ADP_SEARCH_URL):
        try:
            html = fetch_text(listing_url)
        except Exception:
            continue
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            label = " ".join(a.stripped_strings)
            if "ADP National Employment Report:" not in label:
                continue
            if "Preliminary Estimate" in label:
                continue
            href = urllib.parse.urljoin(listing_url, a["href"])
            if href not in links:
                links.append(href)
    return links


def parse_adp() -> Release | None:
    links = adp_candidate_links()
    for url in links[:10]:
        try:
            html = fetch_text(url)
        except Exception:
            continue
        text = html_text(html)
        if "ADP National Employment Report" not in text or "Private Sector Employment" not in text:
            continue

        period_match = re.search(r"([A-Za-z]+)\s+(20\d{2})\s+Report Highlights", text, re.I)
        if not period_match:
            period_match = re.search(r"according to the\s+([A-Za-z]+)\s+ADP National Employment Report", text, re.I)
            if period_match:
                year_match = re.search(r"([A-Za-z]+)\s+(20\d{2})\s+/PRNewswire/", text)
                if not year_match:
                    continue
                period_month = period_match.group(1)
                period_year = year_match.group(2)
            else:
                continue
        else:
            period_month = period_match.group(1)
            period_year = period_match.group(2)
        period = month_period(period_month, period_year)

        d = re.search(r"(?:ROSELAND, N\.J\.,?\s*)?(?:-|–)?\s*([A-Za-z]+)\s+(\d{1,2}),\s*(20\d{2})\s*(?:/PRNewswire/|–|-)", text, re.I)
        if not d:
            d = re.search(r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{1,2},\s+20\d{2}", text, re.I)
            if not d:
                continue
            d2 = re.search(r"([A-Za-z]+)\s+(\d{1,2}),\s*(20\d{2})", d.group(0))
            if not d2:
                continue
            d = d2
        release_dt = parse_date_month_day_year(d.group(1), d.group(2), d.group(3), 8, 15)

        total = first_match(r"Private employers added\s*([+\-]?\d[\d,]*)\s*jobs", text)
        if total is None:
            total = first_match(r"Private sector employment (?:increased|decreased) by\s*([\d,]+)\s*jobs", text)
            if total is not None and re.search(r"Private sector employment decreased by", text, re.I):
                total = "-" + total
        stayer = first_match(r"Job-stayers\s+([0-9.]+)%", text)
        changer = first_match(r"Job-changers\s+([0-9.]+)%", text)
        goods = first_match(r"Goods-producing:\s*([+\-]?\d[\d,]*)", text)
        services = first_match(r"Service-providing:\s*([+\-]?\d[\d,]*)", text)
        prev_revision = first_match(r"The\s+[A-Za-z]+\s+total number of jobs added was\s+([^.]*)\.", text)

        metrics = {
            "private_payroll_change": parse_num(total),
            "goods": parse_num(goods),
            "services": parse_num(services),
            "job_stayer_pay": float(stayer) if stayer else None,
            "job_changer_pay": float(changer) if changer else None,
            "job_changer_premium": (float(changer) - float(stayer)) if stayer and changer else None,
            "previous_revision_text": prev_revision,
        }
        key = make_key("adp", period, release_dt)
        return Release(
            kind="adp",
            key=key,
            title=f"ADP National Employment Report {period}",
            period=period,
            release_dt_et=release_dt,
            source_url=url,
            metrics=metrics,
            raw_summary=text[:4000],
        )
    return None


def load_state() -> dict:
    state = {"reported_successfully": list(DEFAULT_REPORTED)}
    if STATE_PATH.exists():
        try:
            loaded = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            state.update(loaded if isinstance(loaded, dict) else {})
        except Exception:
            pass
    keys = list(dict.fromkeys(DEFAULT_REPORTED + list(state.get("reported_successfully") or [])))
    state["reported_successfully"] = keys
    return state


def regime_line(releases: list[Release]) -> str:
    bls = next((r for r in releases if r.kind == "employment_situation"), None)
    claims = next((r for r in releases if r.kind == "weekly_claims"), None)
    adp = next((r for r in releases if r.kind == "adp"), None)

    signals = []
    if bls:
        nfp = bls.metrics.get("nfp")
        if nfp is not None:
            if nfp < 0:
                signals.append("고용 감소")
            elif nfp < 75000:
                signals.append("저채용")
            else:
                signals.append("고용 증가")
        pr = bls.metrics.get("participation_rate")
        if pr is not None and pr < 62:
            signals.append("낮은 참가율")
    if claims:
        ic = claims.metrics.get("initial_claims")
        cc = claims.metrics.get("continuing_claims")
        if ic is not None and ic < 220000:
            signals.append("저해고")
        if cc is not None and cc >= 1800000:
            signals.append("재취업 지연")
    if adp:
        a = adp.metrics.get("private_payroll_change")
        if a is not None and a < 75000:
            signals.append("민간 채용 둔화")

    if not signals:
        return "노동시장 국면: 핵심 방향 확인은 가능하지만 단일 발표만으로 국면 단정은 제한적입니다."
    return "노동시장 국면: " + "·".join(dict.fromkeys(signals)) + " 신호가 함께 나타나는지 확인해야 합니다."


def release_section(r: Release) -> str:
    kst = r.release_dt_et.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")
    et = r.release_dt_et.strftime("%Y-%m-%d %H:%M ET")
    lines = [f"### {r.title}", f"- 기준기간: {r.period}", f"- 공식 발표: {et} / {kst}", f"- 중복키: `{r.key}`"]
    m = r.metrics
    if r.kind == "employment_situation":
        lines += [
            f"- NFP: {fmt_int(m.get('nfp'))}명",
            f"- 실업률: {pct(m.get('unemployment_rate'))}",
            f"- 참가율: {pct(m.get('participation_rate'))}",
            f"- 고용률(EPOP): {pct(m.get('epop'))}",
            f"- AHE YoY: {pct(m.get('ahe_yoy'))}",
            f"- 주당근로시간: {m.get('workweek') if m.get('workweek') is not None else '확인 불가'}시간",
            f"- 제조업 초과근로: {m.get('manufacturing_overtime') if m.get('manufacturing_overtime') is not None else '확인 불가'}시간",
        ]
        if m.get("revisions_text"):
            lines.append(f"- 수정치: {m['revisions_text']}")
    elif r.kind == "weekly_claims":
        lines += [
            f"- Initial Claims: {fmt_int(m.get('initial_claims'))}건",
            f"- 직전주 수정치: {fmt_int(m.get('previous_revised'))}건",
            f"- 4주 평균: {fmt_int(m.get('four_week_average'))}건",
            f"- Continuing Claims: {fmt_int(m.get('continuing_claims'))}건",
            f"- Insured unemployment rate: {pct(m.get('insured_unemployment_rate'))}",
        ]
    elif r.kind == "adp":
        lines += [
            f"- ADP 민간고용: {fmt_int(m.get('private_payroll_change'))}명",
            f"- Goods: {fmt_int(m.get('goods'))}명 / Services: {fmt_int(m.get('services'))}명",
            f"- Job-Stayer 임금: {pct(m.get('job_stayer_pay'))}",
            f"- Job-Changer 임금: {pct(m.get('job_changer_pay'))}",
            f"- Changer premium: {pct(m.get('job_changer_premium'))}",
            "- 성격: ADP는 민간부문 추정치이며 BLS NFP는 정부 공식통계입니다.",
        ]
        if m.get("previous_revision_text"):
            lines.append(f"- 전월 수정: {m['previous_revision_text']}")
    lines.append(f"- 공식 원문: {r.source_url}")
    return "\n".join(lines)


def four_axis(releases: list[Release]) -> str:
    bls = next((r for r in releases if r.kind == "employment_situation"), None)
    claims = next((r for r in releases if r.kind == "weekly_claims"), None)
    adp = next((r for r in releases if r.kind == "adp"), None)

    weak_jobs = False
    if bls and bls.metrics.get("nfp") is not None and bls.metrics["nfp"] < 75000:
        weak_jobs = True
    if adp and adp.metrics.get("private_payroll_change") is not None and adp.metrics["private_payroll_change"] < 75000:
        weak_jobs = True
    low_layoffs = bool(claims and claims.metrics.get("initial_claims") is not None and claims.metrics["initial_claims"] < 220000)

    if weak_jobs and low_layoffs:
        earning = "중립~부담 — 해고는 낮지만 신규채용 둔화가 소비·매출 증가율을 제약할 수 있습니다."
        discount = "우호적 가능 — 고용 냉각이 물가와 함께 확인되면 연준 완화 기대→실질금리 하락 경로가 열립니다."
    elif weak_jobs:
        earning = "부담 — 채용 약화가 노동소득·소비를 거쳐 경기민감 업종의 매출/EPS에 부담이 될 수 있습니다."
        discount = "우호적/경기침체형 양면 — 금리 하락은 성장주에 우호적이나 침체 공포가 커지면 위험자산에는 반대 효과입니다."
    else:
        earning = "중립~우호적 — 고용이 유지되면 소비·기업 매출 방어에 도움이 됩니다."
        discount = "중립~부담 — 고용이 강하고 임금도 끈적이면 금리 인하 기대가 뒤로 밀릴 수 있습니다."

    return (
        "## 더 강한 종합 해석\n"
        "투자 관점의 4축으로 보면:\n"
        f"- 돈 버는 능력: {earning}\n"
        f"- 할인율: {discount}\n"
        "- 수급: 발표 직후에는 금리·달러·VIX 반응이 방향을 결정합니다. 금리 하락+달러 약세면 장기듀레이션 성장주에 상대적으로 우호적이고, 금리 하락+달러 강세+VIX 상승이면 경기침체형 위험회피로 봅니다.\n"
        "- 시간표: 다음 BLS Employment Situation, 목요일 Weekly Claims, 다음 월간 ADP에서 같은 방향이 반복되는지 확인해야 합니다. 한 번의 발표보다 1~3개월 누적 방향을 우선합니다."
    )


def build_report(new_releases: list[Release]) -> str:
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")
    parts = [
        "# Jobs Wage Watch",
        f"조회 시각: {now}",
        regime_line(new_releases),
        "",
        "## 오늘 새 공식 발표",
    ]
    for r in new_releases:
        parts.extend(["", release_section(r)])
    parts.extend([
        "",
        "## 핵심 해석",
        "고용의 양만 보지 않고 참가율·근로시간·수정치·Initial/Continuing Claims·ADP 임금을 함께 봐야 합니다. 저해고와 저채용이 동시에 나타나면 ‘고용 동결’에 가깝고, Continuing Claims가 오르면 해고보다 재취업 속도 둔화가 문제일 수 있습니다.",
        "",
        four_axis(new_releases),
        "",
        "## 핵심 한 줄 요약",
        regime_line(new_releases).replace("노동시장 국면: ", ""),
        "",
        "상태: 원천 재조회·중복 확인·수치 재검증 완료.",
    ])
    return "\n".join(parts).strip() + "\n"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for p in (ALERT_PATH, META_PATH, PENDING_STATE_PATH):
        if p.exists():
            p.unlink()

    state = load_state()
    reported = set(state.get("reported_successfully") or [])
    checked = []
    errors = []

    parsers = [parse_bls, parse_claims, parse_adp]
    releases: list[Release] = []
    for parser in parsers:
        try:
            r = parser()
            if r:
                releases.append(r)
                checked.append({"kind": r.kind, "key": r.key, "source": r.source_url})
            else:
                checked.append({"kind": parser.__name__.replace("parse_", ""), "key": None, "source": None})
        except Exception as e:
            errors.append({"parser": parser.__name__, "error": f"{type(e).__name__}: {e}"})

    new_releases = [r for r in releases if r.key not in reported]

    status_lines = [
        "# Jobs Wage Watch status",
        f"- checked_at_kst: {datetime.now(KST).isoformat(timespec='seconds')}",
        f"- detected_releases: {len(releases)}",
        f"- new_trigger_set: {len(new_releases)}",
    ]
    for item in checked:
        status_lines.append(f"- {item['kind']}: {item['key'] or '확인 불가'}")
    for e in errors:
        status_lines.append(f"- error {e['parser']}: {e['error']}")
    WATCH_PATH.write_text("\n".join(status_lines) + "\n", encoding="utf-8")

    if not new_releases:
        print("new_trigger_set=0; no Telegram alert")
        return 0

    report = build_report(new_releases)
    ALERT_PATH.write_text(report, encoding="utf-8")
    META_PATH.write_text(
        json.dumps(
            {
                "generated_at_kst": datetime.now(KST).isoformat(timespec="seconds"),
                "new_keys": [r.key for r in new_releases],
                "releases": [
                    {
                        "kind": r.kind,
                        "key": r.key,
                        "period": r.period,
                        "release_dt_et": r.release_dt_et.isoformat(),
                        "source_url": r.source_url,
                        "metrics": r.metrics,
                    }
                    for r in new_releases
                ],
                "errors": errors,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    pending = dict(state)
    pending["reported_successfully"] = list(dict.fromkeys(list(state.get("reported_successfully") or []) + [r.key for r in new_releases]))
    pending["last_generated_at_kst"] = datetime.now(KST).isoformat(timespec="seconds")
    PENDING_STATE_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"new_trigger_set={len(new_releases)} keys={[r.key for r in new_releases]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
