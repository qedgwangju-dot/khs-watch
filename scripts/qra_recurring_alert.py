#!/usr/bin/env python3
"""Recurring U.S. Treasury QRA watcher with interpretation-first Telegram output.

Checks the Treasury's most-recent quarterly refunding page, detects a newly
released 8:30 a.m. ET QRA document block, compares policy wording with the
previous QRA, extracts the core refunding sizes and TBAC financing-shortfall
signal when available, then emits a concise Korean interpretation alert.

Telegram delivery is handled by the GitHub Actions workflow.
"""

from __future__ import annotations

import html
import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "out"
DATA_DIR = ROOT / "data"
STATE_PATH = DATA_DIR / "qra_recurring_alert_state.json"
ALERT_PATH = OUT_DIR / "qra_recurring_alert.md"
TITLE_PATH = OUT_DIR / "qra_recurring_alert_title.txt"
DETAIL_PATH = OUT_DIR / "qra_recurring_alert.json"
WATCH_PATH = OUT_DIR / "qra_recurring_watch.md"

KST = ZoneInfo("Asia/Seoul")
QRA_PAGE = (
    "https://home.treasury.gov/policy-issues/financing-the-government/"
    "quarterly-refunding/most-recent-quarterly-refunding-documents"
)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def strip_html(source: str) -> str:
    source = re.sub(r"<script\b[^>]*>.*?</script>", " ", source, flags=re.I | re.S)
    source = re.sub(r"<style\b[^>]*>.*?</style>", " ", source, flags=re.I | re.S)
    source = re.sub(r"<[^>]+>", " ", source)
    return clean_text(source)


def fetch_text(url: str, *, attempts: int = 3, timeout: int = 30) -> str:
    error: Exception | None = None
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; KHS-QRA-Watch/2.0)",
                    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw = response.read()
                charset = response.headers.get_content_charset() or "utf-8"
            return raw.decode(charset, errors="replace")
        except Exception as exc:  # pragma: no cover - network dependent
            error = exc
            if attempt + 1 < attempts:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"공식 QRA 페이지 조회 실패: {error}")


@dataclass(frozen=True)
class LinkItem:
    text: str
    url: str


@dataclass
class ReleaseSection:
    heading: str
    links: list[LinkItem]


class ReleaseParser(HTMLParser):
    def __init__(self, base_url: str = QRA_PAGE) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.sections: list[ReleaseSection] = []
        self._in_h3 = False
        self._h3_parts: list[str] = []
        self._current: ReleaseSection | None = None
        self._anchor_href: str | None = None
        self._anchor_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "h3":
            self._in_h3 = True
            self._h3_parts = []
        elif tag == "a" and self._current is not None:
            self._anchor_href = dict(attrs).get("href")
            self._anchor_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_h3:
            self._h3_parts.append(data)
        if self._anchor_href is not None:
            self._anchor_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "h3" and self._in_h3:
            heading = clean_text(" ".join(self._h3_parts))
            self._in_h3 = False
            self._h3_parts = []
            if re.search(r"documents\s+released\s+at\s+8:30", heading, re.I):
                self._current = ReleaseSection(heading=heading, links=[])
                self.sections.append(self._current)
            else:
                self._current = None
        elif tag == "a" and self._anchor_href is not None:
            text = clean_text(" ".join(self._anchor_parts))
            href = urllib.parse.urljoin(self.base_url, self._anchor_href)
            if self._current is not None and text and href:
                self._current.links.append(LinkItem(text=text, url=href))
            self._anchor_href = None
            self._anchor_parts = []


def policy_link(section: ReleaseSection) -> LinkItem | None:
    return next((x for x in section.links if "policy statement" in x.text.lower()), None)


def tbac_minutes_link(section: ReleaseSection) -> LinkItem | None:
    return next((x for x in section.links if "tbac minutes" in x.text.lower()), None)


def tbac_report_link(section: ReleaseSection) -> LinkItem | None:
    return next((x for x in section.links if "tbac report to secretary" in x.text.lower()), None)


def fetch_clean(link: LinkItem | None) -> str:
    if link is None:
        return ""
    try:
        return strip_html(fetch_text(link.url, attempts=2, timeout=25))
    except RuntimeError:
        return ""


def guidance_word(text: str) -> str | None:
    lower = text.lower()
    if "potential future changes" in lower:
        return "changes"
    if "potential future increases" in lower:
        return "increases"
    if "potential future decreases" in lower:
        return "decreases"
    return None


def maintain_guidance(text: str) -> bool:
    lower = text.lower()
    return "at least the next several quarters" in lower and (
        "nominal coupon" in lower or "frn auction sizes" in lower
    )


def extract_refunding_amounts(text: str) -> dict[str, float]:
    patterns = {
        "3년물": r"3-year\s+note[^$]{0,140}\$([0-9]+(?:\.[0-9]+)?)\s*billion",
        "10년물": r"10-year\s+note[^$]{0,140}\$([0-9]+(?:\.[0-9]+)?)\s*billion",
        "30년물": r"30-year\s+bond[^$]{0,140}\$([0-9]+(?:\.[0-9]+)?)\s*billion",
    }
    found: dict[str, float] = {}
    lower = text.lower()
    for label, pattern in patterns.items():
        m = re.search(pattern, lower, re.I)
        if m:
            found[label] = float(m.group(1))
    return found


def extract_shortfall(text: str) -> tuple[str | None, str | None]:
    if not text:
        return None, None
    patterns = [
        r"(?:financing|funding)\s+shortfall[^$]{0,180}\$([0-9]+(?:\.[0-9]+)?)\s*trillion",
        r"shortfall[^$]{0,180}\$([0-9]+(?:\.[0-9]+)?)\s*trillion",
    ]
    value = None
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            value = m.group(1)
            break
    years = None
    ym = re.search(r"FY\s*20\d{2}\s*(?:-|–|to|through|and)\s*FY?\s*20\d{2}", text, re.I)
    if ym:
        years = clean_text(ym.group(0)).upper()
    return value, years


def load_state() -> dict[str, object]:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def format_billion(value: float) -> str:
    return f"{value:,.0f}억달러" if False else f"{value:g}0억달러"  # kept for compatibility; not used


def build_alert(current: ReleaseSection, previous: ReleaseSection | None) -> tuple[str, str, dict[str, object]]:
    current_policy_item = policy_link(current)
    previous_policy_item = policy_link(previous) if previous else None
    current_policy = fetch_clean(current_policy_item)
    previous_policy = fetch_clean(previous_policy_item)
    minutes = fetch_clean(tbac_minutes_link(current))
    report = fetch_clean(tbac_report_link(current))

    maintain = maintain_guidance(current_policy)
    current_word = guidance_word(current_policy)
    previous_word = guidance_word(previous_policy)
    amounts = extract_refunding_amounts(current_policy)
    shortfall, shortfall_years = extract_shortfall(minutes + " " + report)

    if maintain and current_word == "changes" and previous_word == "increases":
        headline = "장기국채 발행 유지 + 향후 ‘증액’ 표현 완화"
        core = (
            "미 재무부는 명목 이표채·FRN 경매 규모를 ‘적어도 향후 몇 분기’ 현 수준으로 유지하고, "
            "향후 정책 문구도 직전 QRA의 ‘증액(increases)’에서 ‘변경(changes)’으로 완화했습니다. "
            "즉 장기채 공급 확대 위험이 사라진 것은 아니지만, 당장 증액을 기본 시나리오로 제시하는 신호는 약해졌습니다."
        )
    elif maintain:
        headline = "장기국채 발행 규모 최소 몇 분기 유지"
        core = (
            "미 재무부는 명목 이표채·FRN 경매 규모를 ‘적어도 향후 몇 분기’ 현 수준으로 유지했습니다. "
            "이번 QRA의 핵심은 장기채 공급 충격이 당장 추가되지 않았다는 점입니다."
        )
    else:
        headline = "장기국채 가이던스 변화 감지"
        core = (
            "이번 QRA에서 기존 ‘향후 몇 분기 현 수준 유지’ 가이던스의 유지 여부가 불명확하거나 변경됐습니다. "
            "만기별 발행표와 정책문구를 보수적으로 확인해야 합니다."
        )

    amount_lines: list[str] = []
    for label in ("3년물", "10년물", "30년물"):
        if label in amounts:
            amount_lines.append(f"• {label}: {amounts[label]:g}0억달러")

    if amounts:
        total = sum(amounts.values())
        amount_lines.append(f"• 3·10·30년물 합계: {total:g}0억달러")

    if current_word and previous_word and current_word != previous_word:
        wording = f"• 정책문구 변화: {previous_word} → {current_word}"
    elif current_word:
        wording = f"• 향후 발행 정책 표현: {current_word}"
    else:
        wording = "• 향후 발행 정책 표현: 자동 판정 보류"

    shortfall_line = ""
    if shortfall:
        when = f" ({shortfall_years})" if shortfall_years else ""
        shortfall_line = (
            f"• TBAC 중장기 경고: 현재 발행구조가 이어질 경우 약 {shortfall}조달러의 잠재 자금조달 부족{when}. "
            "이는 당장 부족한 현금이 아니라 현 구조 지속 가정의 미래 부족분입니다."
        )

    market = (
        "장기채 증액 없음 → 장기국채 공급 충격 완화 → 기간 프리미엄·10년/30년 금리 상승 압력 완화 "
        "→ 기업 할인율 부담 완화 → AI·성장주에는 단기 우호적입니다. 다만 이는 기업 실적을 직접 늘리는 호재가 아니라 할인율·수급 측 호재입니다."
    )

    risk = (
        "재정적자·차입 수요가 계속 늘면 단기국채만으로 부담을 흡수하기 어려워지고, 결국 이표채 증액 신호가 다시 나올 수 있습니다. "
        "따라서 ‘국채 공급 문제 해결’이 아니라 ‘장기채 증액 결정을 뒤로 미룸’으로 해석하는 것이 정확합니다."
    )

    next_watch = (
        "다음 QRA에서 ① ‘at least the next several quarters’ 유지·삭제, "
        "② changes가 다시 increases로 바뀌는지, ③ 10·20·30년물 실제 증액 여부, "
        "④ 단기국채로 추가 차입을 얼마나 흡수하는지를 확인합니다."
    )

    body_lines = [
        f"🇺🇸 미 재무부 QRA — {headline}",
        "",
        "핵심 판단",
        core,
        "",
        "확정 결정",
        *(amount_lines or ["• 3·10·30년물 금액 자동 추출 보류 — 공식 발행표 직접 확인 필요"]),
        f"• 이표채·FRN 최소 몇 분기 유지: {'확인' if maintain else '재확인 필요'}",
        wording,
        "",
        "시장 해석",
        market,
        "",
        "중장기 한계",
        *( [shortfall_line] if shortfall_line else [] ),
        risk,
        "",
        "다음 확인",
        next_watch,
        "",
        "핵심 한 줄",
        "지금은 장기채를 늘리지 않아 단기 장기금리·AI주에 우호적이지만, 재정적자와 미래 차입 부담은 그대로라 공급 위험은 사라진 것이 아니라 뒤로 미뤄졌습니다.",
        "",
        f"공식 문서: {current_policy_item.url if current_policy_item else QRA_PAGE}",
    ]

    title = f"📋 미 재무부 QRA: {headline}"
    body = "\n".join(x for x in body_lines if x is not None).strip()
    detail = {
        "status": "new_qra_detected",
        "heading": current.heading,
        "detected_at_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "maintain_guidance": maintain,
        "previous_word": previous_word,
        "current_word": current_word,
        "amounts_billion_usd": amounts,
        "shortfall_trillion_usd": shortfall,
        "shortfall_years": shortfall_years,
        "policy_url": current_policy_item.url if current_policy_item else None,
    }
    return title, body, detail


def write_watch(status: str, detail: str = "") -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    text = (
        f"# QRA 상시 감시 상태\n\n"
        f"- 조회시각: {datetime.now(KST).isoformat(timespec='seconds')}\n"
        f"- 상태: {status}\n"
    )
    if detail:
        text += f"- 상세: {detail}\n"
    WATCH_PATH.write_text(text, encoding="utf-8")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for path in (ALERT_PATH, TITLE_PATH, DETAIL_PATH):
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    parser = ReleaseParser()
    parser.feed(fetch_text(QRA_PAGE))
    if not parser.sections:
        write_watch("QRA 공개 섹션 미탐지")
        return 0

    # Treasury page is normally newest first. Keep a conservative fallback.
    current = parser.sections[0]
    previous = parser.sections[1] if len(parser.sections) > 1 else None
    state = load_state()
    if state.get("last_heading") == current.heading:
        write_watch("새 QRA 없음", current.heading)
        return 0

    title, body, detail = build_alert(current, previous)
    TITLE_PATH.write_text(title + "\n", encoding="utf-8")
    ALERT_PATH.write_text(body + "\n", encoding="utf-8")
    DETAIL_PATH.write_text(json.dumps(detail, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_watch("새 QRA 감지·해석 완료", current.heading)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
