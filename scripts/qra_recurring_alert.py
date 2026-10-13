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
try:
    from scripts.qra_long_end_issuance import (
        nominal_long_end_table, summarize_long_end_supply,
        expectation_comparison, dealer_agenda_mentions_long_end, CITI_20261009,
    )
except ModuleNotFoundError:
    from qra_long_end_issuance import (
        nominal_long_end_table, summarize_long_end_supply,
        expectation_comparison, dealer_agenda_mentions_long_end, CITI_20261009,
    )

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
            if re.search(r"documents\s+released\s+at\s+(?:8:30|3:00|12:00)", heading, re.I):
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


def section_date_key(section: ReleaseSection) -> tuple[str, int]:
    """Sort by actual release date, not the Treasury page's block layout."""
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2}),\s+(20\d{2})", section.heading)
    if not m:
        return ("", 0)
    try:
        day = datetime.strptime(
            f"{m.group(1).title()} {m.group(2)} {m.group(3)}",
            "%B %d %Y",
        ).date().isoformat()
    except ValueError:
        return ("", 0)
    clock = 15 if "3:00" in section.heading else 12 if "12:00" in section.heading else 8
    return day, clock


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


def financing_estimates_link(section: ReleaseSection) -> LinkItem | None:
    return next((x for x in section.links if "financing estimate" in x.text.lower()
                 or "marketable borrowing estimate" in x.text.lower()), None)


def extract_financing_estimates(text: str) -> dict[str, float]:
    amounts = {}
    pat = (
        r"During the\\s+([A-Za-z]+\\s*[–—-]\\s*[A-Za-z]+\\s+20\\d{2})\\s+quarter"
        r".{0,220}?expects\\s+to\\s+borrow\\s+\\$\\s*([\\d,]+)\\s+billion"
    )
    for match in re.finditer(pat.replace("\\\\", "\\"), text, re.I):
        amounts[match.group(1)] = float(match.group(2).replace(",", ""))
    return amounts


MONTH_LABELS = {
    "january": "1월", "february": "2월", "march": "3월", "april": "4월",
    "may": "5월", "june": "6월", "july": "7월", "august": "8월",
    "september": "9월", "october": "10월", "november": "11월", "december": "12월",
}


def quarter_ko(label: str) -> str:
    m = re.search(r"([A-Za-z]+)\s*[–—-]\s*([A-Za-z]+)\s+(20\d{2})", label)
    if not m:
        return label
    return f"{m.group(3)}년 {MONTH_LABELS.get(m.group(1).lower(),m.group(1))}~{MONTH_LABELS.get(m.group(2).lower(),m.group(2))}"


def financing_krw(bn: float, fx: float | None) -> str:
    if fx is None:
        return "원화 환산 확인 불가"
    eok = int(round(bn * fx * 10))
    return f"약 {eok // 10000:,}조{eok % 10000:,}억원"


def build_financing_alert(current: ReleaseSection, previous: ReleaseSection | None):
    link = financing_estimates_link(current)
    if not link:
        raise RuntimeError("공식 3시 차입추정 발표 링크 확인 불가")
    text = fetch_clean(link)
    amounts = extract_financing_estimates(text)
    if len(amounts) < 2:
        raise RuntimeError("민간보유 순시장성 차입 두 분기 금액 확인 전")
    prior_link = financing_estimates_link(previous) if previous else None
    prior = extract_financing_estimates(fetch_clean(prior_link)) if prior_link else {}
    fx = None
    fx_basis = "공식 환율 조회 실패, 원화 환산 보류"
    try:
        from fx_api import daily_krw
        quote = daily_krw()
        fx, fx_basis = quote.rate, str(quote.basis)
    except Exception:
        pass
    rows = []
    for quarter, billion in amounts.items():
        if quarter in prior:
            change = billion - prior[quarter]
            compare = f" (직전 {prior[quarter] * 10:,.0f}억달러 → 변화 {change * 10:+,.0f}억달러)"
        else:
            compare = " (직전 동일 분기 추정 확인 불가)"
        rows.append(f"• {quarter_ko(quarter)}: ${billion:,.0f}B({billion * 10:,.0f}억달러, {financing_krw(billion, fx)}){compare}")
    title = "미 재무부 분기 순차입 추정 신규 발표"
    body = "\n".join([
        "새 3시 공식 차입추정 자료 확인", *rows,
        "• 분기 순차입 추정과 정부 총부채 잔액은 서로 다릅니다.",
        "• 만기별 국채 발행정책은 별도 QRA에서 확정·교차검증합니다.",
        f"환율 기준: {fx_basis}",
        f"미 재무부 원문: {link.url}",
    ])
    return title, body, {"heading": current.heading, "type": "financing_estimate",
                          "source": link.url, "amounts_bn_usd": amounts}


def build_alert(current: ReleaseSection, previous: ReleaseSection | None) -> tuple[str, str, dict[str, object]]:
    current_policy_item = policy_link(current)
    previous_policy_item = policy_link(previous) if previous else None
    current_raw_policy = ""
    if current_policy_item is not None:
        try:
            current_raw_policy = fetch_text(current_policy_item.url, attempts=2, timeout=25)
        except RuntimeError:
            current_raw_policy = ""
    current_policy = strip_html(current_raw_policy)
    previous_policy = fetch_clean(previous_policy_item)
    minutes = fetch_clean(tbac_minutes_link(current))
    report = fetch_clean(tbac_report_link(current))

    maintain = maintain_guidance(current_policy)
    current_word = guidance_word(current_policy)
    previous_word = guidance_word(previous_policy)
    amounts = extract_refunding_amounts(current_policy)
    supply_fx = None
    try:
        from fx_api import daily_krw
        supply_fx = daily_krw().rate
    except Exception:
        pass
    supply = summarize_long_end_supply(
        nominal_long_end_table(current_raw_policy), fx=supply_fx
    )
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

    if supply.get("available"):
        shift = supply["delta_bn"]
        if shift < 0:
            headline = "20·30년 장기국채 예정 발행 축소(공식 QRA)"
            core = (
                "공식 발행표에서 20·30년물의 다음 3개월 예정 발행 합계가 "
                "직전 3개월보다 감소했습니다. 공급부담 완화와 국가채무 감소는 다르며 "
                "단기국채 등 대체 조달을 함께 확인해야 합니다."
            )
        elif shift > 0:
            headline = "20·30년 장기국채 예정 발행 확대(공식 QRA)"
            core = (
                "공식 발행표에서 20·30년물 예정 공급이 증가했습니다. "
                "기존 바이백 집행액과 신규 발행액을 혼합하지 않습니다."
            )

    amount_lines: list[str] = []
    for label in ("3년물", "10년물", "30년물"):
        if label in amounts:
            amount_lines.append(f"• {label}: {amounts[label]:g}0억달러")

    if amounts:
        total = sum(amounts.values())
        amount_lines.append(f"• 3·10·30년물 환매차환 입찰 합계: {total:g}0억달러")
    amount_lines.append(expectation_comparison(supply))
    amount_lines.append(
        "• Citi 미확정 시나리오(10/9): 20·30년물 각각 회당 30억달러 축소,"
        " 3개월 총 180억달러 장기채 감축·단기국채 대체 예상."
        " 20년물 중단은 추가 가능성이며 재무부 결정이 아닙니다."
    )

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

    if supply.get("available") and supply["delta_bn"] < 0:
        market = (
            "20·30년 예정 발행 감축은 장기 위험보상 압력 완화 가능성이 있으나,"
            " 단기국채 대체 발행·물가·연준·회사채 경쟁 때문에 금리 하락이 보장되지는 않습니다."
            " AI·성장주에는 직접 매출이 아닌 할인율의 간접 영향입니다."
        )
    elif supply.get("available") and supply["delta_bn"] > 0:
        market = (
            "20·30년 예정 공급 증가는 기간프리미엄 부담이 될 수 있습니다."
            " 실제 금리·수요·인플레이션에 따라 반응이 달라지므로 공급만으로 예단하지 않습니다."
        )
    else:
        market = (
            "20·30년 공식 발행표 직접 검증 전에는 Citi 전망만으로 감축을 단정하지 않습니다."
            " 11/4 QRA 확정표와 차입추정·단기국채 이전·장기금리 반응을 분리 확인합니다."
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
        "official_20y_30y_issuance": supply,
        "source_version": "official_qra_monthly_table_if_available",
        "analyst_comparator": CITI_20261009,
        "policy_url": current_policy_item.url if current_policy_item else None,
    }
    return title, body, detail


def official_dealer_document_text(link: LinkItem) -> str:
    """Read actual Treasury agenda/questionnaire; a title is not evidence."""
    req = urllib.request.Request(
        link.url, headers={"User-Agent": "Mozilla/5.0 KHS-QRA-Dealer/1.0"}
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        raw = response.read()
        media = str(response.headers.get("Content-Type") or "").lower()
    if raw.startswith(b"%PDF") or "application/pdf" in media:
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        return clean_text(" ".join(page.extract_text() or "" for page in reader.pages))
    return strip_html(raw.decode("utf-8", errors="replace"))


def build_dealer_survey_alert(section: ReleaseSection) -> tuple[str, str, dict] | None:
    items = [
        link for link in section.links
        if any(word in link.text.lower() for word in (
            "primary dealer meeting agenda", "primary dealer survey",
            "primary dealer auction size survey", "dealer questionnaire",
        ))
    ]
    if not items:
        return None
    primary = None
    inspected_text = ""
    failures = []
    for document in items:
        try:
            body = official_dealer_document_text(document)
        except Exception as exc:
            failures.append(f"{document.url}: {type(exc).__name__}")
            continue
        if dealer_agenda_mentions_long_end(body):
            primary = document
            inspected_text = body
            break
    if primary is None:
        if failures and len(failures) == len(items):
            raise RuntimeError("공식 딜러 자료 전부 접근 실패: " + "; ".join(failures))
        return None
    checks = {
        "20년물": r"20[\s-]*year",
        "30년물": r"30[\s-]*year",
        "장기채 수요": r"long[\s-]*(?:dated|end|bond)|coupon\s+issuance",
        "대형 기술기업 회사채 경쟁": r"hyperscal|corporate\s+(?:bond|debt|issuance)|investment[\s-]*grade",
        "연기금 장기수요": r"pension\s+fund",
        "국채 경매규모": r"auction\s+siz",
    }
    signals = [label for label, pattern in checks.items() if re.search(pattern, inspected_text, re.I)]
    if not signals:
        return None
    title = "미 재무부 딜러 자료 | 장기국채 공급 검토 신호"
    body = "\n".join([
        "확정 단계: 공식 딜러 설문·의제 공개. 장기채 감축 결정이 아닙니다.",
        "• 공식 공개일: " + section_date_key(section)[0] + " · 확인 주제: " + "·".join(signals),
        "• Citi 미확정 예상: 20년·30년물 각각 회당 30억달러 감축"
        " → 3개월 180억달러 장기채 공급 감축·단기국채 대체 가능."
        " 20년물 발행 중단은 추가 시나리오.",
        "• 정부 질문·설문은 정책 검토의 증거이지 시행 결정이 아닙니다.",
        "• 다음 확인: 11/2 분기 차입추정, 11/4 QRA 확정 발행표·가이던스.",
        "• 역풍: 단기국채 차환 위험·대형 기술기업 회사채 경쟁·인플레이션·기간프리미엄.",
        "공식 문서: " + primary.url,
        "시장 예상: " + CITI_20261009,
    ])
    return title, body, {
        "type": "dealer_long_end_survey_official_document",
        "heading": section.heading,
        "official_url": primary.url,
        "signals": signals,
        "decision_status": "survey_not_final_policy",
    }


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

    # The official Treasury page groups documents by category rather than
    # always putting the most recent release first. Date-sort both types.
    sections = sorted(parser.sections, key=section_date_key, reverse=True)
    if not section_date_key(sections[0])[0]:
        raise RuntimeError("미 재무부 공식 발표일 추출 실패 — 오래된 발표 재발송 방지")
    current = sections[0]
    is_financing = "3:00" in current.heading
    is_dealer = "12:00" in current.heading
    previous = next(
        (section for section in sections[1:]
         if ("3:00" in section.heading) == is_financing
         and ("12:00" in section.heading) == is_dealer),
        None,
    )
    state = load_state()
    if state.get("last_heading") == current.heading:
        write_watch("새 QRA 없음", current.heading)
        return 0

    if is_dealer:
        if section_date_key(current)[0] < "2026-10-13":
            write_watch("과거 딜러 의제 기준선", current.heading)
            return 0
        report = build_dealer_survey_alert(current)
        if report is None:
            write_watch("공식 딜러 자료의 장기채 검토 의제 미확인", current.heading)
            return 0
        title, body, detail = report
    else:
        title, body, detail = (
            build_financing_alert(current, previous)
            if is_financing else build_alert(current, previous)
        )
    TITLE_PATH.write_text(title + "\n", encoding="utf-8")
    ALERT_PATH.write_text(body + "\n", encoding="utf-8")
    DETAIL_PATH.write_text(json.dumps(detail, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_watch("새 QRA 감지·해석 완료", current.heading)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
