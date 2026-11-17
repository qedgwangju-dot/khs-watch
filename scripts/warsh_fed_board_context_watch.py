#!/usr/bin/env python3
"""Official Fed policymaker and FOMC schedule additions inside the existing Warsh workflow.

Only the Federal Reserve's actual speech/release body can authorize an alert.
Confirmed send receipts are deduplicated; ambiguous sends remain quarantined.
"""
import calendar
import datetime as dt
import email.utils
import html
import json
import os
import re
import subprocess
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path

from warsh_speech_watch import clean_text
from warsh_rba_minutes_context import RBA_KEY, RBA_MINUTES_URL, RBA_RELEASED_AT, rba_minutes_message

ROOT = "https://www.federalreserve.gov"
RSS = ROOT + "/feeds/speeches.xml"
ARCHIVE = ROOT + "/newsevents/{year}-speeches.htm"
SCHEDULE = ROOT + "/newsevents/pressreleases/monetary20261112a.htm"
STATE_PATH = Path("data/warsh_fed_board_context_state.json")
BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
EXPECTED_BOT = (os.getenv("EXPECTED_BOT_USERNAME") or "").lstrip("@").strip()
SPEECH_RE = re.compile(
    r"^https://www\.federalreserve\.gov/newsevents/speech/(waller|bowman)(20\d{6}[a-z])\.htm$", re.I
)
SEEDS = (
    ROOT + "/newsevents/speech/waller20261110a.htm",
    ROOT + "/newsevents/speech/bowman20261110a.htm",
)
EVENT_START = dt.date(2026, 11, 10)
SCHEDULE_KEY = "calendar:2027:monetary20261112a"
DALY_KEY = "regional:daly:20261113:unlv-services"
DALY_OFFICIAL = "https://www.frbsf.org/news-and-media/events/2026/11/conversation-mary-c-daly-unlv-2026-economic-forecast/"
DALY_UNLV_OFFICIAL = "https://cber.unlv.edu/events/outlook/"
DALY_REUTERS = "https://www.reuters.com/business/fed-likely-need-raise-rates-amid-worsening-inflation-daly-2026-11-13/"
DALY_NEWS_SOURCES = (
    DALY_REUTERS,
    "https://kfgo.com/2026/11/13/fed-likely-to-need-to-raise-rates-amid-worsening-inflation-daly/",
    "https://wdez.com/2026/11/13/fed-likely-to-need-to-raise-rates-amid-worsening-inflation-daly/",
    "https://www.investing.com/news/economy-news/fed-likely-to-need-to-raise-rates-amid-worsening-inflation-daly-5026338",
)
DALY_NEWS_KO = "https://news.einfomax.co.kr/news/articleView.html?idxno=4444757"
FORMAT_VERSION = 2
WALLER_KEY = "speech:waller:20261110a"
WALLER_FORMAT_VERSION = 3
NEWS_WALLER = "https://tv.edaily.co.kr/News/NewsRead?Kind=257&NewsId=07216006645644408"
BLS_CPI = "https://www.bls.gov/news.release/archives/cpi_11102026.htm"
BEA_PCE = "https://www.bea.gov/news/2026/personal-income-and-outlays-september-2026"
FOMC_CALENDAR = ROOT + "/monetarypolicy/fomccalendars.htm"
OFFICIAL_FX = "https://english.mofe.go.kr/"


def shortlink(label: str, url: str) -> str:
    """Telegram-supported HTML link, never an exposed long URL."""
    parsed = urllib.parse.urlsplit(url)
    allowed = {
        "www.federalreserve.gov", "www.bls.gov", "www.bea.gov",
        "tv.edaily.co.kr", "english.mofe.go.kr",
        "www.frbsf.org", "cber.unlv.edu", "www.reuters.com",
        "news.einfomax.co.kr",
    }
    if parsed.scheme != "https" or parsed.hostname not in allowed:
        raise ValueError("Unapproved Telegram source URL")
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'



def fetch(url: str) -> str:
    host = urllib.parse.urlsplit(url).hostname
    if host != "www.federalreserve.gov" and url not in (BLS_CPI, BEA_PCE):
        raise ValueError("Unapproved official source")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; KHS-Warsh-watch/2.0)"})
    with urllib.request.urlopen(req, timeout=16) as response:
        actual = urllib.parse.urlparse(response.geturl())
        if actual.scheme != "https" or actual.hostname != host:
            raise RuntimeError("Official source redirected to an untrusted host")
        return response.read().decode("utf-8", errors="replace")


def _extract_pubday(link: str):
    match = SPEECH_RE.fullmatch(link)
    if not match:
        return None
    try:
        return dt.datetime.strptime(match.group(2)[:8], "%Y%m%d").date()
    except ValueError:
        return None


def speech_urls(now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    cutoff = max(EVENT_START, now.date() - dt.timedelta(days=21))
    result = {url for url in SEEDS if cutoff <= _extract_pubday(url) <= now.date()}
    errors = []
    try:
        root = ET.fromstring(fetch(RSS))
        for item in root.findall(".//item"):
            url = (item.findtext("link") or "").strip().split("?")[0]
            day = _extract_pubday(url)
            if day and cutoff <= day <= now.date():
                result.add(url)
    except Exception as exc:
        errors.append("연준 연설 RSS: " + type(exc).__name__)

    try:
        archive = fetch(ARCHIVE.format(year=now.year))
        for match in re.finditer(
            r"""href=["']([^"']*/newsevents/speech/(?:waller|bowman)20\d{6}[a-z]\.htm)["']""",
            archive, flags=re.I,
        ):
            url = urllib.parse.urljoin(ROOT, match.group(1))
            day = _extract_pubday(url)
            if day and cutoff <= day <= now.date():
                result.add(url)
    except Exception as exc:
        errors.append("연준 연설 연도별 목록: " + type(exc).__name__)

    return sorted(result, key=lambda x: (_extract_pubday(x), x)), errors


def verify_waller_releases():
    """Check the dated releases, including units and comparison periods, before publishing."""
    sources = (
        (BLS_CPI, (
            "consumer price index - october 2026",
            "increased 0.4 percent on a seasonally adjusted basis in october after rising 0.6 percent in september",
            "index for all items less food and energy rose 0.3 percent in october, as it did in september and august",
            "november 2026 is scheduled to be published on thursday, december 10, 2026",
        )),
        (BEA_PCE, (
            "personal income and outlays, september 2026",
            "from the preceding month, the pce price index for september increased 0.5 percent",
            "excluding food and energy, the pce price index increased 0.3 percent",
            "from the same month one year ago, the pce price index for september increased 3.6 percent",
            "excluding food and energy, the pce price index increased 3.1 percent from one year ago",
        )),
    )
    for url, phrases in sources:
        plain = " ".join(clean_text(fetch(url)).lower().split())
        plain = re.sub(r"\s+([,.])", r"\1", plain).replace("–", "-").replace("—", "-")
        if not all(phrase in plain for phrase in phrases):
            raise RuntimeError(f"Release contents could not be verified: {url}")
    calendar_text = " ".join(clean_text(fetch(FOMC_CALENDAR)).lower().split())
    if not re.search(r"2026 fomc meetings(?:(?!20\d{2} fomc meetings).)*?december\s+8\s*[-–]\s*9\b", calendar_text):
        raise RuntimeError("December 2026 FOMC dates could not be verified")


def speech_message(url: str, raw: str):
    match = SPEECH_RE.fullmatch(url)
    if not match:
        return None
    speaker, stamp = match.groups()
    day = dt.datetime.strptime(stamp[:8], "%Y%m%d").date()
    plain = re.sub(r"\s+", " ", clean_text(raw))
    month = calendar.month_name[day.month]
    if f"{month} {day.day}, {day.year}" not in plain:
        raise RuntimeError("Official Fed speech date does not match the link")
    low = plain.lower()
    identity = "christopher j. waller" if speaker.lower() == "waller" else "michelle w. bowman"
    if identity not in low:
        raise RuntimeError("Official Fed speech speaker does not match the link")
    date_label = day.strftime("%Y-%m-%d")
    original = shortlink("연준 공식 연설", url)

    if speaker.lower() == "waller" and stamp == "20261110a":
        must = ("support a 25 basis point increase", "50 basis point hike", "december meeting",
                "core cpi inflation around 0.3 percent or even higher", "should be considered",
                "3.7 percent over the previous 12 months", "put our credibility at risk",
                "markets to price in some tightening", "3.4 percent in the third quarter",
                "4.1 percent in october", "october gains of 165,000 jobs", "80,000 jobs a month",
                "low hire, low fire", "share of new labor force entrants in unemployment",
                "more than 70 percent of the components of core pce service prices",
                "core inflation may be more responsive to energy shocks",
                "ship-to-ship transfer of oil", "reportedly boosting oil prices")
        if not all(x in low for x in must):
            raise RuntimeError("Waller's conditional 25/50bp policy view cannot be verified")
        verify_waller_releases()
        return "\n".join((
            "<b>[연준 공식 발언] 월러 | 12월 금리 인상 주장</b>",
            "발언 2026.11.10 · <i>연준 이사 개인 견해 / FOMC 확정 결정 아님</i>",
            "",
            "<b>핵심 사실</b>",
            "■ 월러는 10월 물가가 다소 둔화해도 12월 연방공개시장위원회(FOMC)에서 <b>0.25%p 인상</b>을 지지한다고 밝혔습니다.",
            "■ 월러는 10월 근원 소비자물가지수(CPI)가 전월비 <b>0.3% 안팎이거나 더 높으면 0.50%p 인상을 검토</b>해야 하며, 이 경우 0.25%p 인상에 그치면 연준의 신뢰성이 흔들릴 수 있다고 말했습니다.",
            "■ 연설 뒤 미국 노동통계국이 발표한 10월 CPI는 계절조정 전월비 <b>0.6% → 0.4%</b>로 둔화했고, 근원 CPI는 8~10월 석 달 연속 <b>0.3%</b> 올라 월러가 언급한 범위에 들었습니다.",
            "■ 9월 전체 개인소비지출(PCE) 물가 전년비는 <b>월러 연설문 3.7%, 미국 경제분석국 발표 3.6%</b>이며, 경제분석국 기준 전체 전월비는 0.5%, 근원은 전월비 0.3%·전년비 3.1%입니다.",
            "■ 월러는 9월 근원 PCE 서비스 구성 항목의 <b>70% 넘는 항목</b>이 전년비 3% 넘게 올랐고, 근원 상품과 주거비 제외 시장 서비스로 물가 압력이 번졌다고 설명했습니다.",
            "■ 월러는 에너지 충격이 근원 물가에 더 오래 전가될 수 있다는 연준 연구와, 호르무즈해협의 선박 보험료·해상 환적비가 유가를 높인다는 현장 보도를 각각 인용했습니다.",
            "■ 그는 10월에는 시장금리에 긴축 예고가 이미 반영돼 동결에 찬성했지만, 예고한 인상을 합리적인 기간 안에 이행해야 한다고 봤습니다.",
            "■ 월러가 인용한 미국 3분기 실질 국내총생산 속보치는 전분기 대비 연율 <b>3.4%</b>, 10월 실업률은 <b>4.1%</b>, 비농업 고용은 <b>16만 5천 명 증가</b>였고, 6개월·12개월 평균 증가폭은 각각 월 약 8만 명이었습니다.",
            "■ 단기적으로 노동 수급은 대체로 균형이라고 평가했지만, 저채용·저해고 속에서 실업자 중 장기 실업자와 신규 진입자 비중이 높아진 점은 생산성에 영향을 줄 중장기 문제로 짚었습니다.",
            "■ 이데일리가 인용한 12월 0.25%p 인상 확률은 전날 84.0%에서 <b>11월 10일 미 동부시간 07:50에 99.1%</b>로 올랐으며, 이날 08:30 CPI 발표 전 가격입니다.",
            "",
            "<b>쉽게 말하면</b>",
            "물가가 조금 식더라도 지금 수준이 높아 금리를 올려야 한다는 주장입니다. 다만 최종 결정은 연준 위원들의 표결과 새 경제지표에 달렸습니다.",
            "",
            "<b>다음 확인</b>",
            "■ 12월 FOMC는 현지시간 8~9일 열리며, 11월 CPI는 회의가 끝난 뒤인 <b>12월 10일</b> 발표 예정입니다.",
            "■ 회의 전에는 후속 PCE 물가와 고용지표를 확인할 수 있으며, 위 확률은 11월 10일 보도 시점 기준입니다.",
            "",
            "원문 " + original + " · " + shortlink("BLS 10월 CPI", BLS_CPI) +
            " · " + shortlink("미 경제분석국 9월 PCE", BEA_PCE) +
            " · " + shortlink("연준 회의 일정", FOMC_CALENDAR) +
            " · " + shortlink("당시 확률 보도", NEWS_WALLER),
        ))

    if speaker.lower() == "bowman" and stamp == "20261110a":
        must = ("off-balance-sheet liabilities", "revenues from ai customers disappoint",
                "benefit of additional policy tightening")
        if not all(x in low for x in must):
            raise RuntimeError("Bowman AI-financing risk and policy tradeoff not verified")
        if not all(x in low for x in ("exceed $800 billion", "three times the amount of debt")):
            raise RuntimeError("Bowman AI debt/long-term commitments values not verified")
        return "\n".join((
            "<b>[연준 공식 발언] 보먼 | AI 투자 금융위험 경고</b>",
            "발언 2026.11.10 · <i>금융안정 위험 시나리오 / 위기 확정 아님</i>",
            "",
            "<b>핵심 사실</b>",
            "• <b>부채:</b> 회사채·사모대출·프로젝트금융 등 2026년 AI 관련 부채가 <b>8,000억달러(약 1,069조3,600억원) 초과</b>할 전망.",
            "• <b>장부 밖 부담:</b> 장기 임대·공급계약·잔존가치 보증의 잠재 지급액은 부채의 <b>3배 초과 추정</b>. 확정 차입금이나 단순 합산 가능한 매출이 아님.",
            "• <b>매출과 비용:</b> AI 매출은 증가하지만 현재의 모델·데이터센터 유지 및 신규 구축 비용을 충분히 감당하지 못한다고 평가.",
            "• <b>위험 경로:</b> 기대 매출 미달 → AI 기업 주가 하락 → 차입비용 상승·신용 축소 → 데이터센터 투자 둔화.",
            "• <b>이미 보인 조짐:</b> 일부 관련 기업의 주가 하락·회사채 신용가산금리 및 신용부도스와프 비용 상승을 관찰했다고 언급.",
            "• <b>금리 판단:</b> 추가 긴축의 물가 억제 편익뿐 아니라 주택·중소기업·투자에 미칠 비용도 함께 고려해야 한다는 입장.",
            "",
            "<b>쉽게 말하면</b>",
            "AI 투자액이 늘어도 <b>실제 고객 매출로 빚과 장기 지급 약정을 감당할 수 있는지</b> 봐야 합니다. 금융위기 발생이나 금리 동결·인상 확정 발표는 아닙니다.",
            "",
            "<b>다음 확인</b>",
            "• AI 서비스 매출·현금흐름, 회사채 신용가산금리, 자금조달 금리, 데이터센터 투자 취소·지연.",
            "• 원화 환산: 2026.11.13 정부 발표 원/달러 종가 1달러=1,336.7원 적용.",
            "",
            "원문 " + original + " · " + shortlink("환율 근거", OFFICIAL_FX),
        ))

    # For later speeches do not make up a policy decision, probability, or crisis.
    policy = any(x in low for x in (
        "support an increase in", "support a 25 basis point increase",
        "50 basis point hike", "further tightening of monetary policy",
        "benefit of additional policy tightening",
    ))
    finance = "off-balance-sheet" in low and any(
        x in low for x in ("artificial intelligence", "data center", "ai-related")
    )
    if not (policy or finance):
        return None
    speaker_ko = "월러" if speaker.lower() == "waller" else "보먼"
    rows = [
        f"<b>[연준 공식 연설] {speaker_ko} | 정책·금융위험</b>",
        f"발언 {date_label} · <i>개별 위원의 공식 연설, 정책 결정 아님</i>",
        "",
        "<b>원문에서 확인된 주제</b>",
    ]
    if policy:
        rows.append("• 기준금리·추가 긴축과 관련된 명시적 발언 확인. 찬반·조건은 공식 원문으로 구분.")
    if finance:
        rows.append("• AI 투자자금·장부 밖 지급 의무와 관련된 위험 언급. 금융사고 발생 확정 아님.")
    rows += [
        "", "<b>쉬운 해석</b>",
        "연설에서 관련 위험이나 정책 선택지를 논의한 것이며, 실제 FOMC 결정과 구분해야 합니다.",
        "", "원문 " + original,
    ]
    return "\n".join(rows)


def schedule_message(raw: str):
    plain = re.sub(r"\s+", " ", clean_text(raw))
    lower = plain.lower()
    required = (
        "revised tentative schedule", "2027", "october 26-27",
        "november 16-17", "broad monetary policy strategy",
        "january 26-27", "march 16-17", "april 27-28",
        "june 8-9", "july 27-28", "september 14-15",
    )
    if not all(x in lower for x in required):
        raise RuntimeError("Official 2027 FOMC schedule revision is not fully verified")
    return "\n".join((
        "<b>[연준 공식 일정 변경] 2027년 FOMC</b>",
        "연준 발표 2026.11.12 · <i>수정 잠정 일정</i>",
        "",
        "<b>무엇이 달라졌나</b>",
        "• 정례회의는 <b>8회 유지</b>, 이 중 <b>7회만 정규 금리 결정.</b>",
        "• <b>10월 26~27일:</b> 통화정책 전략을 논의하는 회의. 통상적인 금리 표결과 정책성명 발표는 예정돼 있지 않음.",
        "• <b>연말 결정:</b> 기존 <s>12월 7~8일</s> → <b>11월 16~17일</b>로 이동. 2027년 마지막 예정 금리 결정일은 <b>11월 17일</b>.",
        "",
        "<b>2027년 금리 결정일 (미국 현지 날짜)</b>",
        "1/27 · 3/17 · 4/28 · 6/9",
        "7/28 · 9/15 · <b>11/17</b>",
        "",
        "<b>쉽게 말하면</b>",
        "연준이 모이는 횟수는 그대로지만 금리를 정하는 정례회의가 1번 줄었습니다. 7번 금리를 인상하거나 인하한다는 뜻은 아닙니다.",
        "",
        "<b>확인할 일정</b>",
        "• 다음 2026년 12월 FOMC: <b>8~9일</b>(변경 없음).",
        "• 2028년 첫 예정 FOMC: 1월 25~26일. 일정은 최종 확정 전 변경될 수 있음.",
        "",
        "원문 " + shortlink("연준 일정 변경 발표", SCHEDULE) +
        " · " + shortlink("공식 FOMC 달력", ROOT + "/monetarypolicy/fomccalendars.htm"),
    ))


# Regional Fed presidents speak at separately hosted bank events, outside the
# Federal Reserve Board's speeches.xml feed. This is one verified high-impact
# policy event, not an automatic conversion of every Fed event to an alert.
DALY_PUBLIC_HOSTS = frozenset({
    "www.frbsf.org", "frbsf.org", "cber.unlv.edu", "www.reuters.com",
    "kfgo.com", "www.kfgo.com", "wdez.com", "www.wdez.com",
    "www.investing.com", "investing.com",
})


def fetch_public_event(url: str) -> str:
    """Read only known HTTPS source hosts. Never use external snippets as official text."""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in DALY_PUBLIC_HOSTS:
        raise ValueError("Unapproved policy-event source host")
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (compatible; KHS-Warsh-macro-watch/2.0)",
                      "Accept-Language": "en-US,en;q=0.9"},
    )
    with urllib.request.urlopen(req, timeout=12) as response:
        final = urllib.parse.urlsplit(response.geturl())
        if final.scheme != "https" or final.hostname not in DALY_PUBLIC_HOSTS:
            raise RuntimeError("Untrusted redirect in regional Fed event source")
        return response.read().decode("utf-8", errors="replace")


def verify_daly_official_event(raw: str) -> bool:
    text = re.sub(r"\s+", " ", clean_text(raw)).lower()
    has_day = bool(re.search(r"(?:nov(?:ember)?\.?\s+13,?\s+2026|2026[./-]11[./-]13)", text))
    return (has_day
            and ("mary c. daly" in text or "mary daly" in text)
            and ("unlv" in text or "university of nevada" in text)
            and ("economic forecast" in text or "economic outlook" in text))


def verify_daly_report(raw: str) -> bool:
    """Reuters account must corroborate the exact date, venue and rate/services claim."""
    text = re.sub(r"\s+", " ", clean_text(raw)).lower()
    date_ok = bool(re.search(r"(?:nov(?:ember)?\.?\s+13\b|2026-11-13)", text))
    name_ok = "daly" in text and ("san francisco" in text or "fed" in text)
    site_ok = "las vegas" in text or "unlv" in text or "nevada" in text
    service_ok = ("services inflation excluding housing" in text
                  or "services inflation ex-housing" in text
                  or "services ex-housing inflation" in text)
    direction_ok = ("not moving in the correct direction" in text
                    or "wrong direction" in text
                    or "not moving in the right direction" in text)
    hike_ok = ("raise rates" in text or "increase its policy rate" in text
               or "rates need to go up" in text)
    pass_ok = ("pass" in text and ("cost" in text or "consumer" in text))
    return bool(date_ok and name_ok and site_ok and service_ok
                and direction_ok and hike_ok and pass_ok)


def daly_event_sources():
    """Official event page proves participation, Reuters reporting proves spoken words.

    The official event listing is *not* a transcript or a Fed rate decision.
    Do not emit the quote when independent live report text is unavailable.
    """
    official_source = None
    issues = []
    for url in (DALY_OFFICIAL, DALY_UNLV_OFFICIAL):
        try:
            if verify_daly_official_event(fetch_public_event(url)):
                official_source = url
                break
            issues.append("official page lacks matching date/speaker/venue")
        except Exception as exc:
            issues.append("official " + type(exc).__name__)
    if not official_source:
        raise RuntimeError("Daly official UNLV appearance unverified: " + ", ".join(issues)[:170])

    quoted_source = None
    for url in DALY_NEWS_SOURCES:
        try:
            if verify_daly_report(fetch_public_event(url)):
                quoted_source = url
                break
            issues.append("Reuters report lacks matching services/rates quotes")
        except Exception as exc:
            issues.append("Reuters " + type(exc).__name__)
    if not quoted_source:
        raise RuntimeError("Daly remarks lack a directly verified Reuters source: " +
                           ", ".join(issues)[:170])
    return official_source, quoted_source


def daly_event_message(official_source: str, quoted_source: str) -> str:
    """Date-qualified official event + reported quotes, with attribution kept separate."""
    return "\n".join((
        "<b>[Warsh 관련 연준 발언] 데일리 | 서비스 물가·추가 인상</b>",
        "발언 2026.11.13 · 샌프란시스코 연은 총재 · UNLV 경제전망 행사",
        "<i>연준 공식 행사 확인 · 발언 내용은 로이터 현장 취재</i>",
        "",
        "<b>핵심 사실</b>",
        "• <b>정책 방향:</b> 데일리는 추가 금리 인상이 <b>필요할 가능성이 높다</b>고 밝혔으나, 12월 인상 여부·폭을 확정하지 않았습니다.",
        "• <b>끈적한 물가:</b> 특히 <b>주거비 제외 서비스 물가</b>가 올바른 방향으로 움직이지 않는다고 우려했습니다.",
        "• <b>근원 CPI:</b> 최근 3개월간 전월 대비 약 <b>+0.3%씩</b> 상승(로이터 보도). 연준의 공식 2% 목표 지표는 CPI가 아닌 <b>PCE 물가지수</b>입니다.",
        "• <b>기업의 가격 전가:</b> 에너지·IT 기기 등 원가 상승을 이익으로 흡수하기 어려워 고객 가격을 올리려는 움직임을 경고했습니다.",
        "• <b>소비 확인:</b> 소비는 예상보다 견조하지만 일부 지역에서 둔화 조짐이 있어 향후 <b>1~3개월, 특히 연말 소비</b>를 살피겠다고 밝혔습니다.",
        "",
        "<b>쉽게 말하면</b>",
        "상품·유가가 안정돼도 서비스 요금이 계속 오르면 물가가 쉽게 내려가지 않습니다. 기업이 오른 원가를 소비자에게 넘기면 금리 인상이 더 필요할 수 있다는 뜻입니다.",
        "",
        "<b>시장과 다음 확인</b>",
        "• <b>주식·채권:</b> 추가 긴축 우려는 단기 국채금리와 성장주 할인율에 부담이 될 수 있습니다. 실제 시장 반응을 확인해야 합니다.",
        "• 2026.12.8~9 FOMC · 다음 근원 PCE · 주거비 제외 서비스 물가 · 임금·연말 소비.",
        "• <b>구분:</b> 11월 12일 스탠퍼드 발언과 13일 UNLV 발언은 별도 행사입니다. 동일한 정책 입장을 신규 결정 2건으로 계산하지 않습니다.",
        "",
        "출처 " + shortlink("샌프란시스코 연은 행사", official_source) +
        " · " + shortlink("로이터 현장 보도", DALY_REUTERS) +
        " · " + shortlink("연합인포맥스 기사", DALY_NEWS_KO),
    ))


def _load_state():
    if not STATE_PATH.exists():
        return {}
    data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("Warsh Fed context state must be a JSON object")
    return data


def load_state():
    state = _load_state()
    # A queued checkout may predate the prior successful sender's state push.
    # Fail closed instead of duplicate sending when the remote status cannot be checked.
    proc = subprocess.run(
        ["git", "fetch", "--quiet", "origin", "main"],
        capture_output=True, text=True, timeout=18,
    )
    if proc.returncode != 0:
        raise RuntimeError("Cannot verify latest remote Warsh state: GitHub fetch failed")
    result = subprocess.run(
        ["git", "show", "origin/main:" + STATE_PATH.as_posix()],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode == 0:
        remote = json.loads(result.stdout)
        if not isinstance(remote, dict):
            raise RuntimeError("Remote Warsh state is invalid")
        for section in ("sent", "pending", "skipped", "formatted"):
            current = state.setdefault(section, {})
            for key, value in (remote.get(section) or {}).items():
                current[key] = value
        if remote.get("schedule_last_seen") and not state.get("schedule_last_seen"):
            state["schedule_last_seen"] = remote["schedule_last_seen"]
    return state


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class TelegramNotSent(RuntimeError):
    """No message was created. A later scheduled run may retry delivery."""


def _verified_telegram_call(method: str, data: dict, expected_message_id=None):
    if not BOT_TOKEN or not CHAT_ID or not EXPECTED_BOT:
        raise TelegramNotSent("Existing Telegram bot/chat settings missing")
    bot_url = f"https://api.telegram.org/bot{BOT_TOKEN}/"
    try:
        with urllib.request.urlopen(bot_url + "getMe", timeout=18) as r:
            bot = json.loads(r.read().decode("utf-8"))
    except Exception as exc:
        raise TelegramNotSent("Telegram identity check failed before delivery") from exc
    if not bot.get("ok") or str((bot.get("result") or {}).get("username") or "").lower() != EXPECTED_BOT.lower():
        raise TelegramNotSent("Warsh Telegram bot identity mismatch")
    payload = {
        "chat_id": CHAT_ID,
        "text": data["text"],
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }
    if expected_message_id is not None:
        payload["message_id"] = str(expected_message_id)
    req = urllib.request.Request(
        bot_url + method,
        data=urllib.parse.urlencode(payload).encode("utf-8"),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            response = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        response = json.loads(exc.read().decode("utf-8", errors="replace"))
        description = str(response.get("description") or "").lower()
        if method == "editMessageText" and "message is not modified" in description:
            # An idempotent edit succeeded earlier but its state wasn't yet saved.
            return {"message_id": expected_message_id, "recipient_verified": True, "unchanged": True}
        if method == "sendMessage" and 400 <= exc.code < 500 and response.get("ok") is False:
            raise TelegramNotSent(f"Telegram rejected the delivery (HTTP {exc.code})") from exc
        raise RuntimeError("Telegram request failed without a verified receipt") from exc
    if not response.get("ok"):
        raise RuntimeError("Telegram send/editMessageText returned ok=false")
    result = response.get("result") or {}
    chat = result.get("chat") or {}
    actual_id = str(chat.get("id") or "")
    matched = (
        actual_id == CHAT_ID if re.fullmatch(r"-?\d+", CHAT_ID)
        else CHAT_ID.startswith("@") and str(chat.get("username") or "").lower() == CHAT_ID[1:].lower()
    )
    mid = result.get("message_id")
    if not matched or not isinstance(mid, int) or mid <= 0:
        raise RuntimeError("Telegram response does not match the existing recipient/message_id")
    if expected_message_id is not None and mid != expected_message_id:
        raise RuntimeError("Telegram edit returned an unexpected message_id")
    return {"message_id": mid, "recipient_verified": True}


def send(msg: str):
    if len(msg) > 3900:
        raise ValueError("Telegram HTML alert is too long; do not cut inside HTML tags")
    return _verified_telegram_call("sendMessage", {"text": msg})


def edit_message(message_id: int, msg: str):
    if len(msg) > 3900:
        raise ValueError("Telegram HTML alert is too long; do not cut inside HTML tags")
    if not isinstance(message_id, int) or message_id <= 0:
        raise ValueError("Cannot edit Telegram without a confirmed numeric message_id")
    return _verified_telegram_call("editMessageText", {"text": msg}, expected_message_id=message_id)


def _upgrade_message(key: str, receipt: dict):
    """Refetch official text before editing a previously delivered old-format alert."""
    url = receipt.get("source") or ""
    speech_match = SPEECH_RE.fullmatch(url)
    if speech_match and key == "speech:" + ":".join(speech_match.groups()).lower():
        return speech_message(url, fetch(url))
    if key == SCHEDULE_KEY and url == SCHEDULE:
        return schedule_message(fetch(SCHEDULE))
    if key == DALY_KEY and url in (DALY_OFFICIAL, DALY_UNLV_OFFICIAL):
        official, reported = daly_event_sources()
        return daly_event_message(official, reported)
    return None


def upgrade_delivered_messages(state):
    """Edit known old messages in place: never emit a duplicate Telegram message."""
    updated = []
    state.setdefault("formatted", {})
    for key, receipt in sorted(state.get("sent", {}).items()):
        if (not isinstance(receipt, dict) or receipt.get("recipient_verified") is not True
                or not isinstance(receipt.get("message_id"), int)):
            continue
        target_version = WALLER_FORMAT_VERSION if key == WALLER_KEY else FORMAT_VERSION
        if (state["formatted"].get(key) or {}).get("version", 0) >= target_version:
            continue
        message = _upgrade_message(key, receipt)
        if message is None:
            continue
        answer = edit_message(receipt["message_id"], message)
        if not answer.get("recipient_verified") or answer.get("message_id") != receipt["message_id"]:
            raise RuntimeError("Unverified Telegram edit response")
        state["formatted"][key] = {
            "version": target_version, "message_id": receipt["message_id"],
            "edited_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        save_state(state)
        updated.append(key)
    return updated


def deliver(state, key, message, url):
    if key in state.setdefault("sent", {}) or key in state.setdefault("pending", {}):
        return False
    state["pending"][key] = {"status": "sending", "source": url}
    save_state(state)
    try:
        receipt = send(message)
    except TelegramNotSent:
        state["pending"].pop(key)
        save_state(state)
        raise
    except Exception:
        state["pending"][key]["status"] = "delivery_uncertain"
        save_state(state)
        raise
    state["sent"][key] = {**receipt, "source": url}
    target_version = WALLER_FORMAT_VERSION if key == WALLER_KEY else FORMAT_VERSION
    state.setdefault("formatted", {})[key] = {"version": target_version, "message_id": receipt["message_id"]}
    state["pending"].pop(key, None)
    save_state(state)
    return True


def fetch_rba_minutes(url):
    if url != RBA_MINUTES_URL:
        raise ValueError("Unexpected RBA minutes URL")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; KHS-macro-watch/2.0)"})
    with urllib.request.urlopen(req, timeout=16) as response:
        if response.geturl() != url:
            raise RuntimeError("Unexpected RBA minutes redirect")
        return response.read().decode("utf-8")


def check_rba_minutes(state, now):
    if now < RBA_RELEASED_AT or RBA_KEY in state["sent"] or RBA_KEY in state["pending"]:
        return False
    return deliver(state, RBA_KEY, rba_minutes_message(fetch_rba_minutes), RBA_MINUTES_URL)


def main():
    state = load_state()
    state.setdefault("sent", {})
    state.setdefault("pending", {})
    state.setdefault("skipped", {})
    delivered = []
    edited = []
    errors = []
    urls, source_errors = speech_urls()
    errors.extend(source_errors)

    for url in urls:
        match = SPEECH_RE.fullmatch(url)
        key = "speech:" + match.group(1).lower() + ":" + match.group(2).lower()
        if key in state["sent"] or key in state["pending"] or key in state["skipped"]:
            continue
        try:
            message = speech_message(url, fetch(url))
            if message is None:
                state["skipped"][key] = {"reason": "no_direct_policy_or_ai_financing_signal"}
                save_state(state)
            elif deliver(state, key, message, url):
                delivered.append(key)
        except Exception as exc:
            errors.append(key + " source/delivery: " + type(exc).__name__)
            if key in state["pending"]:
                raise

    # One event = one key. A rate-hike remark is not an FOMC decision;
    # do not conflate Nov 12 Stanford coverage with Nov 13 UNLV quotes.
    if DALY_KEY not in state["sent"] and DALY_KEY not in state["pending"]:
        try:
            verified_official, quoted_report = daly_event_sources()
            if deliver(state, DALY_KEY,
                       daly_event_message(verified_official, quoted_report),
                       verified_official):
                delivered.append(DALY_KEY)
        except Exception as exc:
            errors.append("SF Fed Daly UNLV source/delivery: " + type(exc).__name__)
            if DALY_KEY in state["pending"]:
                raise

    if SCHEDULE_KEY not in state["sent"] and SCHEDULE_KEY not in state["pending"]:
        try:
            message = schedule_message(fetch(SCHEDULE))
            if deliver(state, SCHEDULE_KEY, message, SCHEDULE):
                delivered.append(SCHEDULE_KEY)
        except Exception as exc:
            errors.append("FOMC schedule source/delivery: " + type(exc).__name__)
            if SCHEDULE_KEY in state["pending"]:
                raise

    try:
        if check_rba_minutes(state, dt.datetime.now(dt.timezone.utc)):
            delivered.append(RBA_KEY)
    except Exception as exc:
        errors.append("RBA minutes source/delivery: " + type(exc).__name__)

    try:
        edited = upgrade_delivered_messages(state)
    except Exception as exc:
        errors.append("기존 메시지 서식 수정 실패: " + type(exc).__name__)

    previous = state.get("source_errors") or []
    if errors != previous:
        state["source_errors"] = errors[:10]
        save_state(state)
    print(json.dumps({
        "official_fed_context": True, "new_sent": delivered,
        "sent_receipts": {key: state["sent"].get(key) for key in delivered},
        "already_sent": len(state["sent"]) - len(delivered),
        "edited_in_place": edited,
        "formatted_count": len(state.get("formatted") or {}),
        "delivery_uncertain": list(state["pending"]),
        "source_errors": errors[:10],
    }, ensure_ascii=False))
    if errors or state["pending"]:
        raise RuntimeError("Policy source or delivery unresolved; see per-event status above")


if __name__ == "__main__":
    main()
