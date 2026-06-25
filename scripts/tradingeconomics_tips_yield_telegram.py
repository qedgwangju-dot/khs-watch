#!/usr/bin/env python3
"""Send the Trading Economics US 10Y TIPS yield to Telegram."""

from __future__ import annotations

import datetime as dt
import html
import os
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "out"
OUT_PATH = OUT_DIR / "tradingeconomics_tips_yield_telegram.md"
KST = ZoneInfo("Asia/Seoul")
SOURCE_URL = os.getenv(
    "TE_TIPS_YIELD_URL",
    "https://tradingeconomics.com/united-states/10-year-tips-yield",
)
USER_AGENT = os.getenv(
    "TE_USER_AGENT",
    "Mozilla/5.0 (compatible; khs-watch-tips-yield/1.0; +https://github.com/qedgwangju-dot/khs-watch)",
)


@dataclass
class TipsYieldSnapshot:
    query_time_kst: dt.datetime
    source_url: str
    status: str
    description: str = ""
    yield_pct: float | None = None
    reference_date: str | None = None
    day_change_pp: float | None = None
    month_change_pp: float | None = None
    year_change_pp: float | None = None
    error: str | None = None


class MetaDescriptionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.description = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "meta":
            return
        attr = {key.lower(): value or "" for key, value in attrs}
        if attr.get("id") == "metaDesc" or attr.get("name", "").lower() == "description":
            self.description = html.unescape(attr.get("content", "")).strip()


def fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "replace")


def extract_description(page_html: str) -> str:
    parser = MetaDescriptionParser()
    parser.feed(page_html)
    return parser.description


def signed_value(raw: str, direction: str) -> float:
    value = float(raw)
    direction = direction.lower()
    negative_words = ("decrease", "decreased", "down", "fallen", "lower", "declined")
    return -value if any(word in direction for word in negative_words) else value


def parse_change(pattern: str, text: str) -> float | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    return signed_value(match.group("value"), match.group("direction"))


def format_reference_date(reference_date: str | None) -> str:
    if not reference_date:
        return "확인 불가"
    try:
        parsed = dt.datetime.strptime(reference_date, "%B %d, %Y").date()
    except ValueError:
        return reference_date
    return f"{parsed:%Y-%m-%d} ({reference_date})"


def format_change(value: float | None) -> str:
    if value is None:
        return "확인 불가"
    return f"{value:+.2f}%p ({value * 100:+.0f}bp)"


def render_korean_summary(snapshot: TipsYieldSnapshot) -> str:
    if snapshot.yield_pct is None:
        return "Trading Economics 원문에서 미국 10년 TIPS 수익률 값을 확인하지 못했습니다."

    ref_date = format_reference_date(snapshot.reference_date)
    parts = [
        f"Trading Economics에 따르면 미국 10년 TIPS 수익률은 {ref_date} 기준 {snapshot.yield_pct:.2f}%입니다.",
    ]
    if snapshot.day_change_pp is not None:
        parts.append(f"전일 대비 {format_change(snapshot.day_change_pp)} 변동했습니다.")
    if snapshot.month_change_pp is not None:
        parts.append(f"지난 한 달 동안 {format_change(snapshot.month_change_pp)} 움직였습니다.")
    if snapshot.year_change_pp is not None:
        parts.append(f"1년 전 대비 {format_change(snapshot.year_change_pp)} 수준입니다.")
    parts.append(
        "이 값은 해당 만기의 미국 물가연동국채에 대한 장외 은행 간 수익률 호가 기준이며, "
        "Trading Economics 페이지의 기준일이 실제 조회시각보다 늦거나 빠를 수 있습니다."
    )
    return " ".join(parts)


def parse_snapshot(description: str, now_kst: dt.datetime) -> TipsYieldSnapshot:
    text = " ".join(description.split())
    value_match = re.search(
        r"10 Year TIPS Yield\s+(?:[a-z]+\s+)*?to\s+(-?\d+(?:\.\d+)?)%\s+on\s+"
        r"([A-Za-z]+ \d{1,2}, \d{4})",
        text,
        flags=re.IGNORECASE,
    )
    if not value_match:
        value_match = re.search(
            r"10 Year TIPS Yield.{0,120}?(-?\d+(?:\.\d+)?)\s*(?:%|percent)\s+on\s+"
            r"([A-Za-z]+ \d{1,2}, \d{4})",
            text,
            flags=re.IGNORECASE,
        )

    day_change_pp = parse_change(
        r"marking a\s+(?P<value>\d+(?:\.\d+)?)\s+percentage points\s+(?P<direction>increase|decrease)",
        text,
    )
    month_change_pp = parse_change(
        r"Over the past month,\s+the yield has\s+(?P<direction>.+?)\s+by\s+"
        r"(?P<value>\d+(?:\.\d+)?)\s+points",
        text,
    )
    year_change_pp = parse_change(
        r"is\s+(?P<value>\d+(?:\.\d+)?)\s+points\s+(?P<direction>higher|lower)\s+than a year ago",
        text,
    )

    if not value_match:
        return TipsYieldSnapshot(
            query_time_kst=now_kst,
            source_url=SOURCE_URL,
            status="확인 불가",
            description=text,
            day_change_pp=day_change_pp,
            month_change_pp=month_change_pp,
            year_change_pp=year_change_pp,
            error="Trading Economics meta description에서 yield/reference date 패턴을 찾지 못함",
        )

    return TipsYieldSnapshot(
        query_time_kst=now_kst,
        source_url=SOURCE_URL,
        status="확인됨",
        description=text,
        yield_pct=float(value_match.group(1)),
        reference_date=value_match.group(2),
        day_change_pp=day_change_pp,
        month_change_pp=month_change_pp,
        year_change_pp=year_change_pp,
    )


def collect_snapshot() -> TipsYieldSnapshot:
    now_kst = dt.datetime.now(tz=KST)
    try:
        page_html = fetch_html(SOURCE_URL)
        description = extract_description(page_html)
        if not description:
            return TipsYieldSnapshot(
                query_time_kst=now_kst,
                source_url=SOURCE_URL,
                status="확인 불가",
                error="Trading Economics meta description 비어 있음",
            )
        return parse_snapshot(description, now_kst)
    except Exception as exc:
        return TipsYieldSnapshot(
            query_time_kst=now_kst,
            source_url=SOURCE_URL,
            status="접근 제한 또는 조회 실패",
            error=f"{type(exc).__name__}: {exc}",
        )


def render_message(snapshot: TipsYieldSnapshot) -> str:
    query_time = snapshot.query_time_kst.strftime("%Y-%m-%d %H:%M KST")
    lines = [
        "[Trading Economics] 미국 10년 TIPS Yield",
        "",
    ]
    if snapshot.yield_pct is None:
        lines.append("값: 확인 불가")
    else:
        lines.append(f"값: {snapshot.yield_pct:.2f}%")

    lines.extend(
        [
            f"전일 대비: {format_change(snapshot.day_change_pp)}",
            f"전월 대비: {format_change(snapshot.month_change_pp)}",
            f"전년 대비: {format_change(snapshot.year_change_pp)}",
            f"기준일: {format_reference_date(snapshot.reference_date)}",
            f"조회시각: {query_time}",
            f"상태: {snapshot.status}",
            f"출처: {snapshot.source_url}",
        ]
    )

    if snapshot.error:
        lines.append(f"오류: {snapshot.error}")

    if snapshot.description:
        lines.extend(["", f"원문 요약(한국어): {render_korean_summary(snapshot)}"])

    lines.append("")
    lines.append("주의: Trading Economics 페이지 기준값이며, 기준일/시각이 조회시각과 다를 수 있습니다.")
    return "\n".join(lines).strip() + "\n"


def send_telegram(text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("Telegram: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing")
        return

    data = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text[:4096],
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        resp.read()
    print("Telegram: sent")


def main() -> int:
    snapshot = collect_snapshot()
    message = render_message(snapshot)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(message, encoding="utf-8")
    print(message)

    if os.getenv("TELEGRAM_DRY_RUN", "").lower() in {"1", "true", "yes", "y"}:
        print("Telegram: dry run")
        return 0

    try:
        send_telegram(message)
    except Exception as exc:
        print(f"Telegram: send failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
