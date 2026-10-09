#!/usr/bin/env python3
"""Verified October 8 release of Trump's August 2026 OGE Form 278-T.

Keep the reporting stage separate from a directly obtained official filing.
No guessed official PDF URL and no inference of insider trading.
"""

import datetime as dt
from email.utils import parsedate_to_datetime
import re

EVENT_KEY = "oge-filing:2026-08:trump-2026-09-17"
PERIOD = "2026-08"
CNBC_URL = "https://www.cnbc.com/2026/10/08/trump-august-trades-meta-spacex-financial-disclosure.html"
BLOOMBERG_URL = "https://news.bloomberglaw.com/antitrust/trumps-latest-trades-include-stakes-in-meta-and-spacex-debt"
WHITE_HOUSE_URL = "https://www.whitehouse.gov/presidential-actions/2026/08/national-security-presidential-memorandum-nspm-17/"
OGE_INDEX_URL = "https://extapps2.oge.gov/201/Presiden.nsf/PAS%20Filings%20by%20Date?OpenView&Start=1&Count=250"


def is_august_official_filing(url):
    low = (url or "").lower()
    if "278" not in low or "trump" not in low:
        return False
    return any(x in low for x in [
        "09.17.2026", "09-17-2026", "09_17_2026", "9.17.2026",
    ])


def is_august_news(event):
    """One stable event for contemporaneous Reuters/CNBC/Meta/SpaceX reprints."""
    title=(event.get("title") or "").lower()
    desc=(event.get("desc") or "").lower()
    text=title+" "+desc
    if not ("trump" in text or "트럼프" in text):
        return False
    pub=event.get("published") or ""
    try:
        stamp=parsedate_to_datetime(pub)
        day=stamp.date()
    except (TypeError, ValueError, IndexError):
        return False
    if not (dt.date(2026,10,8) <= day <= dt.date(2026,10,15)):
        return False

    if "517" in text and any(x in text for x in ["disclos", "filing", "oge", "거래"]):
        return True
    if any(x in text for x in ["august", "8월"]) and any(x in text for x in ["meta", "spacex"]) and any(
        x in text for x in ["disclos", "filing", "trade", "거래", "매수", "보유"]
    ):
        return True
    if "meta" in text and "spacex" in text and any(
        x in text for x in ["disclos", "filing", "purchase", "bought", "매수"]
    ):
        return True
    # Reuters October 8 headline on the same August filing, not a new Nvidia report.
    if "nvidia" in text and any(x in text for x in ["disclos", "filing"]) and any(
        x in text for x in ["huang", "honor", "science", "august", "8월"]
    ):
        return True
    return False


def build_august_report(rate, basis, money_range, official_pdf_url=None):
    """Narrative is source-bounded; currency immediately follows every dollar amount."""
    def amount(low,high):
        return f"{money_range(low,high,rate)}"
    lines = [
        "📊 [트럼프 OGE 8월 신규 거래신고 — 517건]",
        "공시 주체: 도널드 트럼프 대통령 명의 신고 투자계좌",
        "판정: 2026년 10월 8일 새 공개된 8월 거래신고 · 기존 6·7월 재보도 아님",
        "근거: CNBC 분석·Bloomberg 교차보도 / OGE PDF 개별 원문 직접 대조 전",
        f"원화 환산 기준: 1달러={rate:,.2f}원 ({basis})",
        "",
        "▶ 한눈에 보기",
        "• 8월 증권 매수·매도: 517건 (18쪽 신고서에 대한 CNBC 집계)",
        f"• 거래총액 신고범위: 7,430만~2억7,330만달러 ({amount(74_300_000,273_300_000)})",
        f"• 매수금액 하한: 4,420만달러 이상 ({amount(44_200_000,44_200_000)} 기준 이상)",
        f"• 매도금액 하한: 3,010만달러 이상 ({amount(30_100_000,30_100_000)} 기준 이상)",
        "• 거래총액은 8월 거래 범위의 합계이며, 전체 보유자산·정확한 매매대금이 아닙니다.",
        "",
        "▶ 최대 단일 주식 매수",
        f"• 8월 21일 메타(META) 주식: 500만~2,500만달러 ({amount(5_000_000,25_000_000)}) 매수",
        "• 같은 날 AT&T(T)·코노코필립스(COP)·애벗(ABT)·넷플릭스(NFLX)·셰브런(CVX)도 각각 100만~500만달러 매수.",
        "• AMD·처치앤드드와이트(CHD)는 같은 날 각각 100만~500만달러 매도.",
        "",
        "▶ SpaceX: 주식이 아니라 회사채",
        f"• 8월 18일 SpaceX 선순위 무담보 회사채: 100만~500만달러 ({amount(1_000_000,5_000_000)}) 매수",
        "• 표면금리 5.35%, 만기 2031년 7월. SpaceX 주식 취득과 구분합니다.",
        "• 8월 20일 미국 상업용 우주 운송 확대 정책 서명(매수 이틀 뒤).",
        "• 정책은 2030년까지 연간 발사·재진입 1,000회 초과를 목표로 하며 SpaceX 단독 계약이 아닙니다.",
        "",
        "▶ 추가 확인 및 주의",
        "• 8월 NVIDIA 거래는 매수와 매도가 모두 존재합니다. 일방적 순매수로 표현하지 않습니다.",
        "• 신고서만으로 트럼프 개인의 매수 지시나 정책과 거래의 인과관계를 확정할 수 없습니다.",
        "• 백악관은 제3자 금융기관이 독립적으로 해당 계좌를 운용한다고 설명했습니다.",
        "",
        "▶ 출처",
        f"CNBC 원문: {CNBC_URL}",
        f"Bloomberg 원문: {BLOOMBERG_URL}",
        f"백악관 정책 원문: {WHITE_HOUSE_URL}",
    ]
    if official_pdf_url:
        lines.append(f"OGE 원문: {official_pdf_url}")
    else:
        lines.append(f"OGE 공개목록: {OGE_INDEX_URL}")
        lines.append("※ OGE의 이번 신고 PDF 직접주소·전체 517행 직접검산은 아직 완료되지 않았습니다.")
    return "\n".join(lines)
