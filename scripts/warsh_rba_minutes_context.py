"""The RBA's November 2026 minutes, released two weeks after the decision."""
import datetime as dt
import re
from collections.abc import Callable

from warsh_speech_watch import clean_text


RBA_KEY = "rba:minutes:20261117:20261103"
RBA_RELEASED_AT = dt.datetime(2026, 11, 17, 0, 30, tzinfo=dt.timezone.utc)
RBA_MINUTES_URL = "https://www.rba.gov.au/monetary-policy/rba-board-minutes/2026/2026-11-03.html"


def rba_minutes_message(fetch: Callable[[str], str]) -> str:
    """Require the minutes' dated vote and both sides' reasoning before delivery."""
    text = " ".join(clean_text(fetch(RBA_MINUTES_URL)).lower().split())
    majority, separator, minority = text.partition("a minority of members determined")
    _, has_majority, majority = majority.partition("most members determined")
    vote = re.search(
        r"raise the cash rate target to 4\.85 per cent\.\s*six members voted in favour;\s*"
        r"three members voted to leave the cash rate target unchanged at 4\.60 per cent",
        text,
    )
    if not (vote and "minutes of the monetary policy board meeting" in text
            and "2 and 3 november 2026" in text):
        raise RuntimeError("RBA minutes: meeting date, vote or rates could not be verified")
    if not (has_majority and separator
            and all(term in majority for term in ("neutral interest rate", "inflation expectations to rise"))
            and all(term in minority for term in ("100 basis points of tightening", "sharper downturn", "unemployment"))):
        raise RuntimeError("RBA minutes: majority and minority reasons could not be verified")
    unemployment = re.search(
        r"(?:½|1/2|0\.5) percentage point rise in the unemployment rate over the preceding six months\b",
        text,
    )
    business_debt = (
        "data centre developers had raised debt equivalent to at least one-fifth "
        "of the increase in business debt this year"
    )
    if not unemployment or business_debt not in text:
        raise RuntimeError("RBA minutes: unemployment change or share of business debt growth could not be verified")

    return "\n".join((
        "<b>[호주중앙은행 의사록] 6명이 인상을, 3명이 동결을 택한 이유</b>",
        "11월 2~3일 회의 · 2026년 11월 17일 오전 9시 30분 공개(한국시간)",
        "",
        "■ 11월 3일 기준금리를 4.60%에서 4.85%로 올린 표결에서 6명이 인상, 3명이 동결에 찬성했습니다.",
        "■ 인상을 지지한 위원들은 중립금리가 높아졌을 가능성을 짚고, 긴축이 부족해 중장기 기대인플레이션이 오를 위험에 더 무게를 뒀습니다.",
        "■ 동결을 지지한 위원들은 앞서 누적 1.00%포인트 올린 효과를 기다리자고 봤으며, 동결 논거에는 최근 6개월간 실업률이 0.5%포인트 올랐다는 점도 포함됐습니다.",
        "■ 호주중앙은행은 연초부터 이번 회의까지 데이터센터 개발사들이 조달한 부채가 같은 기간 호주 기업부채 전체 증가분의 최소 5분의 1에 해당한다고 밝혔습니다.",
        "",
        f'<a href="{RBA_MINUTES_URL}">호주중앙은행 의사록 원문</a>',
    ))
