"""Runtime Korean wording guard for Warsh Telegram alerts.

Loaded automatically through PYTHONPATH=scripts. It only rewrites the value of
Telegram-style `text` payloads passed to urllib.parse.urlencode, so data parsing
and source identifiers are untouched.
"""
import re
import urllib.parse as _urlparse

_ORIGINAL_URLENCODE = _urlparse.urlencode


def _koreanize_alert(text: str) -> str:
    replacements = [
        ("[Warsh 새 정보축] Money·Credit", "[Warsh 새 정보축] 통화·신용"),
        ("[Warsh 새 정보축] Productivity vs ULC", "[Warsh 새 정보축] 생산성·단위노동비용(ULC)"),
        ("Headline PCE", "종합 PCE"),
        ("Core PCE", "근원 PCE"),
        ("Headline CPI", "종합 CPI"),
        ("Core CPI", "근원 CPI"),
        ("Nonfarm productivity", "비농업 생산성"),
        ("Unit labor costs", "단위노동비용(ULC)"),
        ("H.8 C&I loans", "H.8 기업대출(C&I)"),
        ("H.8 Bank credit", "H.8 은행 신용"),
        ("Money·Credit", "통화·신용"),
        ("full-employment", "완전고용"),
        ("full employment", "완전고용"),
        ("non-restrictive", "충분히 긴축적이지 않음"),
        ("CapEx", "설비투자(CapEx)"),
        ("Trends matter most", "단일 수치보다 추세가 중요"),
        ("new variable / potentially a new factor of production", "새로운 변수 / 잠재적인 새로운 생산요소"),
        ("new variable", "새로운 변수"),
        ("potentially a new factor of production", "잠재적인 새로운 생산요소"),
        ("policy tone", "정책 톤"),
        ("Fed policy path", "연준 정책경로"),
        ("Fed 정책경로", "연준 정책경로"),
        ("Treasury 공식 종가", "미 재무부 공식 종가"),
        ("원문:", "원천:"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)

    # Only replace standalone abbreviations. Never corrupt words such as Federal.
    text = re.sub(r"\bFed\b", "연준(Fed)", text)
    text = re.sub(r"\bTreasury\b", "미 재무부(Treasury)", text)

    text = re.sub(r"\b2Y\b", "2년물", text)
    text = re.sub(r"\b10Y\b", "10년물", text)
    text = re.sub(r"\b30Y\b", "30년물", text)
    text = text.replace("QoQ SAAR", "전분기 대비 연율")
    text = text.replace("MoM", "전월 대비")
    text = text.replace("YoY", "전년 대비")

    text = text.replace("[AI·생산성·성장]", "[AI·생산성·성장 — 원문 문장은 식별용]")
    text = text.replace("[물가·고용·금리]", "[물가·고용·금리 — 원문 문장은 식별용]")
    text = text.replace(
        "[연준(Fed) AI 생산성·고용 태스크포스 변화 감지]",
        "[연준(Fed) AI 생산성·고용 태스크포스 변화 감지]",
    )

    text = text.replace("연준(연준(Fed))", "연준(Fed)")
    text = text.replace("미 재무부(미 재무부(Treasury))", "미 재무부(Treasury)")
    return text


def urlencode(query, doseq=False, safe="", encoding=None, errors=None):
    if isinstance(query, dict) and "text" in query:
        query = dict(query)
        query["text"] = _koreanize_alert(str(query["text"]))
    return _ORIGINAL_URLENCODE(query, doseq=doseq, safe=safe, encoding=encoding, errors=errors)


_urlparse.urlencode = urlencode
