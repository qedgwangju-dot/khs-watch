from __future__ import annotations

import html
import re
from urllib.parse import urlparse

SOURCE_LABELS = {
    "reuters.com": "Reuters",
    "www.reuters.com": "Reuters",
    "Reuters": "Reuters",
    "nwitimes.com": "NWI Times",
    "www.nwitimes.com": "NWI Times",
    "The Washington Post": "The Washington Post",
    "washingtonpost.com": "The Washington Post",
    "www.washingtonpost.com": "The Washington Post",
    "utilitydive.com": "Utility Dive",
    "www.utilitydive.com": "Utility Dive",
    "Utility Dive": "Utility Dive",
    "datacenterdynamics.com": "Data Center Dynamics",
    "www.datacenterdynamics.com": "Data Center Dynamics",
    "Data Center Dynamics": "Data Center Dynamics",
    "Bloomberg": "Bloomberg",
    "bloomberg.com": "Bloomberg",
    "Associated Press": "AP",
    "AP News": "AP",
}

BOILERPLATE_TERMS = (
    "귀하의 계정이 등록",
    "로그인되었습니다",
    "비밀번호 변경 링크",
    "아래 양식을 제출",
    "이메일로 전송됩니다",
    "최신 뉴스를 기기로 바로",
    "USA Today - Vertical",
    "Sign up for",
    "log in",
    "password reset",
    "your account",
)

EVIDENCE_RE = re.compile(
    r'^(?P<prefix>- 근거\d+: \[[^\]]+\]\s+)'
    r'(?P<source>.+?)\s+·\s+'
    r'(?:(?:<a href="(?P<href>[^"]+)">원문</a>)|(?:원문\s*\((?P<paren>https?://[^)]+)\)))\s*$'
)


def display_source(source: str) -> str:
    source = source.strip()
    if source in SOURCE_LABELS:
        return SOURCE_LABELS[source]
    lowered = source.lower().removeprefix("www.")
    if lowered in SOURCE_LABELS:
        return SOURCE_LABELS[lowered]
    if lowered.endswith(".com") or lowered.endswith(".org") or lowered.endswith(".net"):
        host = lowered.split(".")[0]
        return host.replace("-", " ").title()
    return source


def validate_direct_url(url: str) -> None:
    parsed = urlparse(html.unescape(url))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"잘못된 원문 URL: {url}")
    if parsed.netloc.lower().endswith("news.google.com"):
        raise ValueError("Google News 중계 URL은 원문 링크로 전송하지 않습니다.")


def sanitize_report(text: str) -> str:
    if not text.strip():
        raise ValueError("빈 보고서입니다.")

    # 로그인·회원가입·비밀번호 재설정 같은 사이트 UI가 '정확한 내용 요약'에 섞이면 발송을 막는다.
    summary_lines = [line for line in text.splitlines() if line.startswith("- 정확한 내용 요약:")]
    for line in summary_lines:
        if any(term.lower() in line.lower() for term in BOILERPLATE_TERMS):
            raise ValueError("기사 본문이 아닌 로그인/회원가입 문구가 요약에 섞여 있어 Telegram 발송을 차단했습니다.")

    out: list[str] = []
    evidence_count = 0
    for line in text.splitlines():
        match = EVIDENCE_RE.match(line.strip())
        if not match:
            out.append(line)
            continue

        evidence_count += 1
        url = match.group("href") or match.group("paren") or ""
        validate_direct_url(url)
        source = html.escape(display_source(match.group("source")))
        safe_url = html.escape(html.unescape(url), quote=True)
        # 출처명은 일반 텍스트. 오직 '원문'에만 링크를 건다.
        out.append(f'{match.group("prefix")}{source} · <a href="{safe_url}">원문</a>')

    if evidence_count == 0:
        raise ValueError("원문 링크가 하나도 없어 Telegram 발송을 차단했습니다.")

    result = "\n".join(out).strip()

    # href 속성 밖에 naked URL이 노출되면 실패시킨다.
    visible = re.sub(r'<a href="https?://[^"]+">원문</a>', '원문', result)
    if re.search(r'https?://', visible):
        raise ValueError("화면에 노출되는 긴 URL이 남아 있어 Telegram 발송을 차단했습니다.")

    return result
