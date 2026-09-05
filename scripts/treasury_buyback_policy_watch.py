#!/usr/bin/env python3
"""Watch official Treasury long-end buyback policy changes.

Sources:
1) U.S. Treasury press releases (catches intra-quarter policy announcements)
2) TreasuryDirect special buyback announcement PDFs
3) The tentative quarterly buyback schedule

Only material changes affecting the 10Y-20Y or 20Y-30Y nominal
liquidity-support buyback program generate an alert.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

from pypdf import PdfReader

KST = ZoneInfo("Asia/Seoul")
ET = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "out"
STATE = DATA / "treasury_buyback_policy_state.json"
NEXT_STATE = DATA / "treasury_buyback_policy_state_next.json"
ALERT = OUT / "treasury_buyback_policy_alert.html"
TITLE = OUT / "treasury_buyback_policy_title.txt"
DETAIL = OUT / "treasury_buyback_policy_detail.json"
STATUS = OUT / "treasury_buyback_policy_status.md"

PRESS_RELEASES = "https://home.treasury.gov/news/press-releases"
BUYBACK_PAGE = "https://treasurydirect.gov/auctions/announcements-data-results/buy-backs/"
SCHEDULE_PDF = "https://home.treasury.gov/system/files/221/Tentative-Buyback-Schedule.pdf"
FAQ = "https://www.treasurydirect.gov/help-center/faqs/buyback-faqs/"
FRED_FX = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXKOUS"
SPECIAL_TEMPLATE = "https://www.treasurydirect.gov/instit/annceresult/press/preanre/{year}/SPL_{ymd}_{n}.pdf"

BUCKETS = ("10Y to 20Y", "20Y to 30Y")
DEFAULT_BASELINE_BN = 2.0
MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

# Verified market-reaction snippets are only inserted when we have a named,
# externally verifiable source. Do not invent a reaction for future releases.
MARKET_REACTIONS: dict[str, dict[str, str]] = {
    "https://home.treasury.gov/news/press-releases/sb0607": {
        "text": (
            "Financial Times 보도 기준 발표 뒤 미 30년물 금리는 장중 약 5.34%에서 "
            "5.20~5.21% 부근으로 내려왔고, 10년물도 약 4.67%까지 하락했습니다. "
            "즉 시장도 이번 조치를 장기물 수급·유동성 부담 완화로 받아들였습니다."
        ),
        "url": "https://www.ft.com/content/777c9014-2f12-45cf-8224-6bbe808c62cb",
    }
}


class LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self._href = href
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href is not None:
            text = re.sub(r"\s+", " ", " ".join(self._text)).strip()
            self.links.append((self._href, text))
            self._href = None
            self._text = []


class TextCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = re.sub(r"\s+", " ", data).strip()
        if value:
            self.parts.append(value)


def fetch_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 khs-watch/1.3"})
    with urllib.request.urlopen(req, timeout=25) as response:
        return response.read()


def maybe_fetch(url: str) -> bytes | None:
    try:
        return fetch_bytes(url)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return None


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def pdf_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def html_text(data: bytes) -> str:
    parser = TextCollector()
    parser.feed(data.decode("utf-8", errors="replace"))
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


def parse_bucket_maxima(text: str) -> dict[str, list[float]]:
    clean = re.sub(r"\s+", " ", text)
    out: dict[str, list[float]] = {bucket: [] for bucket in BUCKETS}
    for bucket in BUCKETS:
        for match in re.finditer(re.escape(bucket), clean, flags=re.I):
            window = clean[match.end() : match.end() + 280]
            amount = re.search(r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*billion", window, flags=re.I)
            if amount:
                out[bucket].append(float(amount.group(1)))
    return out


def latest_fx():
    from fx_api import daily_krw
    q = daily_krw()
    return q.rate, q.basis


def fmt_krw(usd_bn: float, fx: float) -> str:
    trillion = usd_bn * fx / 1000.0
    return f"약 {trillion:,.2f}조원" if trillion >= 1 else f"약 {trillion * 10000:,.0f}억원"


def is_long_end_buyback_change(text: str) -> bool:
    clean = re.sub(r"\s+", " ", text).lower()
    if "buyback" not in clean and "buy-back" not in clean:
        return False
    long_terms = (
        "10-year to 20-year",
        "10 year to 20 year",
        "10- to 20-year",
        "10y to 20y",
        "20-year to 30-year",
        "20 year to 30 year",
        "20- to 30-year",
        "20y to 30y",
        "long-end",
        "long end",
    )
    policy_terms = (
        "increase",
        "decrease",
        "double",
        "maximum",
        "liquidity support",
        "size",
        "frequency",
        "expand",
        "reduce",
    )
    return any(term in clean for term in long_terms) and any(term in clean for term in policy_terms)


def dollar_amounts_bn(text: str) -> list[float]:
    clean = re.sub(r"\s+", " ", text)
    values: list[float] = []
    for number, unit in re.findall(
        r"\$\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(billion|million)?",
        clean,
        flags=re.I,
    ):
        value = float(number.replace(",", ""))
        unit = unit.lower()
        if unit == "million":
            value /= 1000.0
        elif unit == "":
            if value >= 1_000_000:
                value /= 1_000_000_000.0
            else:
                continue
        if 0.1 <= value <= 200:
            values.append(value)
    return values


def release_date_iso(text: str) -> str | None:
    match = re.search(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+([0-9]{1,2}),\s+(20[0-9]{2})\b",
        text,
        flags=re.I,
    )
    if not match:
        return None
    month = MONTHS[match.group(1).lower()]
    return f"{int(match.group(3)):04d}-{month:02d}-{int(match.group(2)):02d}"


def press_release_links() -> list[tuple[str, str]]:
    raw = fetch_bytes(PRESS_RELEASES)
    parser = LinkCollector()
    parser.feed(raw.decode("utf-8", errors="replace"))
    unique: list[tuple[str, str]] = []
    seen: set[str] = set()
    for href, title in parser.links:
        url = urllib.parse.urljoin(PRESS_RELEASES, href)
        if "/news/press-releases/" not in url or url.rstrip("/") == PRESS_RELEASES.rstrip("/"):
            continue
        if url in seen:
            continue
        seen.add(url)
        unique.append((url, title))
    return unique


def find_new_press_releases(state: dict) -> list[dict]:
    seen_ids = set(state.get("seen_source_ids", []))
    found: list[dict] = []
    for url, title in press_release_links()[:40]:
        source_id = f"press:{url}"
        if source_id in seen_ids:
            continue
        title_lower = title.lower()
        if not any(key in title_lower for key in ("buyback", "buy-back", "long-end", "refunding")):
            continue
        raw = maybe_fetch(url)
        if not raw:
            continue
        text = html_text(raw)
        combined = f"{title} {text}"
        if not is_long_end_buyback_change(combined):
            continue
        found.append(
            {
                "kind": "press_release",
                "source_id": source_id,
                "url": url,
                "title": title or "미 재무부 공식 보도자료",
                "date": release_date_iso(text),
                "text": text,
                "amounts_bn": dollar_amounts_bn(text),
            }
        )
    return found


def find_new_specials(state: dict) -> list[dict]:
    seen_ids = set(state.get("seen_source_ids", []))
    old_seen_shas = set(state.get("seen_long_end_special_shas", []))
    found: list[dict] = []
    now_et = datetime.now(ET)
    for delta in range(0, 3):
        day = now_et.date() - timedelta(days=delta)
        ymd = day.strftime("%Y%m%d")
        for number in range(1, 13):
            url = SPECIAL_TEMPLATE.format(year=day.year, ymd=ymd, n=number)
            raw = maybe_fetch(url)
            if not raw or not raw.startswith(b"%PDF"):
                continue
            sha = hashlib.sha256(raw).hexdigest()
            source_id = f"spl:{sha}"
            if source_id in seen_ids or sha in old_seen_shas:
                continue
            try:
                text = pdf_text(raw)
            except Exception:
                continue
            if is_long_end_buyback_change(text):
                found.append(
                    {
                        "kind": "special_pdf",
                        "source_id": source_id,
                        "url": url,
                        "title": "TreasuryDirect 특별공지",
                        "date": day.isoformat(),
                        "text": re.sub(r"\s+", " ", text).strip(),
                        "amounts_bn": dollar_amounts_bn(text),
                        "legacy_sha": sha,
                    }
                )
    return found


def build_change_lines(source: dict, fx: float) -> list[str]:
    lines = [f"• 공식 출처: <b>{source.get('title') or '미 재무부 공식 발표'}</b>"]
    if source.get("date"):
        lines.append(f"• 발표일: {source['date']}")
    amounts = sorted(set(source.get("amounts_bn") or []))
    if amounts:
        lines.append("• 본문에서 확인된 주요 금액: " + ", ".join(f"${value:g}B" for value in amounts))
    if 2.0 in amounts and any(value >= 4.0 for value in amounts):
        higher = min(value for value in amounts if value >= 4.0)
        lines.append(
            f"• 회당 최대 $2B({fmt_krw(2.0, fx)}) → 최소 ${higher:g}B({fmt_krw(higher, fx)})로 확대"
        )
    return lines


def title_for(source: dict | None, schedule_changes: list[dict]) -> str:
    if source is not None:
        amounts = sorted(set(source.get("amounts_bn") or []))
        url = source.get("url") or ""
        if url.endswith("/sb0607") or (2.0 in amounts and any(value >= 4.0 for value in amounts)):
            return "🇺🇸 미 재무부, 장기물 바이백 최소 2배 확대 — 총량 문제는 그대로, 장기금리 완충 강화"
        return "🇺🇸 미 재무부 장기채 바이백 정책 변경 — 장기금리 수급 영향 점검"
    if schedule_changes:
        if any(change["current_bn"] > change["previous_bn"] for change in schedule_changes):
            return "🇺🇸 미 재무부, 장기물 바이백 확대 — 장기금리 수급 완충 강화"
        return "🇺🇸 미 재무부, 장기물 바이백 축소 — 장기금리 수급 부담 확대"
    return "🇺🇸 미 재무부 장기채 바이백 정책 변경"


def market_reaction_lines(source_url: str) -> list[str]:
    reaction = MARKET_REACTIONS.get(source_url)
    if not reaction:
        return []
    return [
        "",
        "<b>시장 실제 반응</b>",
        f"• {reaction['text']}",
        f'<a href="{reaction["url"]}">시장 반응 원문</a>',
    ]


def build_common_body(
    fx: float,
    fx_date: str,
    source_url: str,
    change_lines: list[str],
    verdict: str,
) -> str:
    lines = [
        "<b>쉽게 말하면</b>",
        f"🟢 {verdict}",
        "",
        "<b>무엇이 바뀌었나</b>",
        *change_lines,
        "• 대상은 10~20년·20~30년 구간의 <b>비지표물 명목 이표채 유동성 지원 바이백</b>입니다.",
        "",
        "<b>금리 해석</b>",
        "• 재무부가 오래된 장기채를 더 많이 되살 수 있음 → 딜러 재고·유통 공급 부담 완화 → 시장 유동성 개선 → 기간 프리미엄·10년/30년 금리 상승 압력을 일부 완화하는 방향입니다.",
        "• 장기 실질금리까지 내려오면 AI·성장주의 할인율에도 단기적으로 우호적입니다.",
    ]
    lines.extend(market_reaction_lines(source_url))
    lines.extend(
        [
            "",
            "<b>중요한 오해 방지</b>",
            "• <b>신규 10년·20년·30년물 발행 확대가 아닙니다.</b> 기존에 유통 중인 비지표물 국채를 재무부가 되사는 조치입니다.",
            "• Fed의 QE가 아닙니다. 재무부의 부채관리 작업이라 은행 준비금을 새로 만드는 통화완화와 다릅니다.",
            "• 바이백 재원은 다른 국채 발행 등으로 조달되므로 국가부채·순국채 공급 문제 자체를 구조적으로 없애지는 못합니다.",
            "• 발표 금액은 최대 매입 상한일 수 있습니다. 실제 매입은 제시 물량·가격에 따라 상한보다 작을 수 있습니다.",
            "",
            "<b>다음 확인</b>",
            "• 실제 매입액 / 총 제시액 / 제시액÷매입상한 비율",
            "• 20년·30년 입찰 꼬리와 간접낙찰 비중",
            "• 10년·30년 명목금리·실질금리가 실제로 내려오는지",
            "• 다음 QRA에서 바이백 규모와 이표채 발행 가이던스가 어떻게 바뀌는지",
            "",
            f"환율 기준: {fx_date}, 1달러={fx:,.1f}원",
            (
                f'<a href="{source_url}">미 재무부 공식 발표</a> · '
                f'<a href="{BUYBACK_PAGE}">바이백 공지·결과</a> · '
                f'<a href="{SCHEDULE_PDF}">기존 바이백 일정</a> · '
                f'<a href="{FAQ}">바이백 설명</a>'
            ),
        ]
    )
    return "\n".join(lines)


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    for path in (ALERT, TITLE, DETAIL):
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    state = load_state()
    raw_schedule = fetch_bytes(SCHEDULE_PDF)
    schedule_text = pdf_text(raw_schedule)
    maxima = parse_bucket_maxima(schedule_text)
    schedule_sha = hashlib.sha256(raw_schedule).hexdigest()
    fx, fx_date = latest_fx()

    current: dict[str, float | None] = {}
    for bucket in BUCKETS:
        values = maxima.get(bucket) or []
        current[bucket] = max(values) if values else None

    previous = state.get("long_end_max_bn") or {bucket: DEFAULT_BASELINE_BN for bucket in BUCKETS}
    schedule_changes: list[dict] = []
    for bucket in BUCKETS:
        cur = current.get(bucket)
        prev = float(previous.get(bucket, DEFAULT_BASELINE_BN))
        if cur is not None and abs(cur - prev) > 1e-9:
            schedule_changes.append({"bucket": bucket, "previous_bn": prev, "current_bn": cur})

    press_releases = find_new_press_releases(state)
    specials = find_new_specials(state)
    official_changes = press_releases + specials

    checked = datetime.now(KST).isoformat(timespec="seconds")
    next_state = {
        **state,
        "last_checked_kst": checked,
        "schedule_sha256": schedule_sha,
        "long_end_max_bn": {
            key: (value if value is not None else previous.get(key, DEFAULT_BASELINE_BN))
            for key, value in current.items()
        },
    }

    detail: dict | None = None
    alert_title = title_for(None, schedule_changes)

    if official_changes:
        source = official_changes[0]
        change_lines = build_change_lines(source, fx)
        body = build_common_body(
            fx,
            fx_date,
            source["url"],
            change_lines,
            "미 재무부가 장기 비지표물 국채를 더 적극적으로 흡수하는 정책 변경을 발표했습니다. 장기물 수급·유동성에는 우호적이지만 재정적자와 전체 국채 공급 문제를 해결하는 조치는 아닙니다.",
        )
        alert_title = title_for(source, schedule_changes)
        detail = {
            "type": source["kind"],
            "source": source,
            "fx": fx,
            "fx_date": fx_date,
            "checked_kst": checked,
        }
        pending_ids = [source["source_id"]]
        if source["kind"] == "press_release":
            for special in specials:
                if not source.get("date") or special.get("date") == source.get("date"):
                    pending_ids.append(special["source_id"])
        next_state["pending_source_ids"] = list(dict.fromkeys(pending_ids))

    elif schedule_changes:
        increases = [change for change in schedule_changes if change["current_bn"] > change["previous_bn"]]
        verdict = (
            "장기물 바이백 상한 확대입니다. 신규 장기채 발행 확대가 아니라 기존 장기채 흡수가 늘어나는 방향이라 장기물 수급에 우호적입니다."
            if increases
            else "장기물 바이백 상한 축소입니다. 재무부의 유동성 지원이 줄어드는 방향이라 장기물 수급에는 부담입니다."
        )
        change_lines: list[str] = []
        for change in schedule_changes:
            change_lines.append(
                f"• {change['bucket']}: 회당 최대 ${change['previous_bn']:g}B → ${change['current_bn']:g}B "
                f"({fmt_krw(change['previous_bn'], fx)} → {fmt_krw(change['current_bn'], fx)})"
            )
        body = build_common_body(fx, fx_date, SCHEDULE_PDF, change_lines, verdict)
        alert_title = title_for(None, schedule_changes)
        detail = {
            "type": "schedule_change",
            "changes": schedule_changes,
            "fx": fx,
            "fx_date": fx_date,
            "checked_kst": checked,
        }
        next_state["pending_schedule_change"] = schedule_changes

    if detail is not None:
        TITLE.write_text(alert_title + "\n", encoding="utf-8")
        ALERT.write_text(body[:4096].rstrip() + "\n", encoding="utf-8")
        DETAIL.write_text(json.dumps(detail, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    NEXT_STATE.write_text(json.dumps(next_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    STATUS.write_text(
        "# 미 재무부 장기채 바이백 정책 점검\n\n"
        f"- 조회시각: {checked}\n"
        f"- 10Y~20Y 일정상 최대: {current.get('10Y to 20Y')}B\n"
        f"- 20Y~30Y 일정상 최대: {current.get('20Y to 30Y')}B\n"
        f"- 신규 관련 재무부 보도자료: {'예' if press_releases else '아니오'}\n"
        f"- 신규 TreasuryDirect 특별공지: {'예' if specials else '아니오'}\n"
        f"- 일정 자체 변경: {'예' if schedule_changes else '아니오'}\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
