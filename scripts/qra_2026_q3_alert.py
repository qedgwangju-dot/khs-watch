#!/usr/bin/env python3
"""One-time U.S. Treasury 2026 Q3 QRA Telegram release watcher.

The workflow polls the Treasury's official Quarterly Refunding document page,
waits for the 8:30 a.m. ET August 5, 2026 release block, then prepares one
Korean Telegram alert. Telegram delivery and duplicate-state persistence are
handled by the GitHub Actions workflow.
"""

from __future__ import annotations

import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "out"
DATA_DIR = ROOT / "data"
STATE_PATH = DATA_DIR / "qra_2026_q3_alert_state.json"
ALERT_PATH = OUT_DIR / "qra_2026_q3_alert.md"
TITLE_PATH = OUT_DIR / "qra_2026_q3_alert_title.txt"
DETAIL_PATH = OUT_DIR / "qra_2026_q3_alert.json"
WATCH_PATH = OUT_DIR / "qra_2026_q3_watch.md"

QRA_PAGE = (
    "https://home.treasury.gov/policy-issues/financing-the-government/"
    "quarterly-refunding/most-recent-quarterly-refunding-documents"
)
BORROWING_RELEASE = "https://home.treasury.gov/news/press-releases/sb0584"
TARGET_HEADING_RE = re.compile(
    r"documents\s+released\s+at\s+8:30\s*(?:am|a\.m\.)\s+"
    r"wednesday,?\s+august\s+5,?\s+2026",
    re.IGNORECASE,
)


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


@dataclass(frozen=True)
class LinkItem:
    text: str
    url: str


class QRASectionParser(HTMLParser):
    """Collect links only from the target August 5, 2026 QRA section."""

    def __init__(self, base_url: str = QRA_PAGE) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self._in_h3 = False
        self._h3_parts: list[str] = []
        self._target_active = False
        self.found_target = False
        self._anchor_href: str | None = None
        self._anchor_parts: list[str] = []
        self.links: list[LinkItem] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "h3":
            self._in_h3 = True
            self._h3_parts = []
            self._target_active = False
        elif tag == "a" and self._target_active:
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
            heading = _clean_text(" ".join(self._h3_parts))
            self._target_active = bool(TARGET_HEADING_RE.search(heading))
            self.found_target = self.found_target or self._target_active
            self._in_h3 = False
            self._h3_parts = []
        elif tag == "a" and self._anchor_href is not None:
            text = _clean_text(" ".join(self._anchor_parts))
            href = urllib.parse.urljoin(self.base_url, self._anchor_href)
            if text and href:
                self.links.append(LinkItem(text=text, url=href))
            self._anchor_href = None
            self._anchor_parts = []


def fetch_text(url: str, *, attempts: int = 3, timeout: int = 30) -> str:
    error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (compatible; KHS-QRA-Watch/1.0; "
                        "+https://github.com/qedgwangju-dot/khs-watch)"
                    ),
                    "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
                },
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                charset = response.headers.get_content_charset() or "utf-8"
            return raw.decode(charset, errors="replace")
        except Exception as exc:  # pragma: no cover - network dependent
            error = exc
            if attempt + 1 < attempts:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"공식 QRA 페이지 조회 실패: {error}")


def load_state() -> dict[str, object]:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def extract_policy_signal(links: list[LinkItem]) -> tuple[str, str | None]:
    policy = next(
        (
            item
            for item in links
            if "policy statement" in item.text.lower()
            and "2026" in item.text.lower()
            and ("3rd quarter" in item.text.lower() or "third quarter" in item.text.lower())
        ),
        None,
    )
    if policy is None:
        return "정책문구 자동 판정 보류", None

    try:
        source = fetch_text(policy.url, attempts=2, timeout=25)
    except RuntimeError:
        return "정책문구 자동 판정 보류", policy.url

    text = _clean_text(re.sub(r"<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>", " ", source, flags=re.I | re.S))
    text = _clean_text(re.sub(r"<[^>]+>", " ", text))
    lower = text.lower()

    maintain_markers = (
        "at least the next several quarters",
        "maintaining nominal coupon and frn auction sizes",
        "maintain nominal coupon and frn auction sizes",
    )
    increase_markers = (
        "increase nominal coupon auction sizes",
        "incremental increases to nominal coupon auction sizes",
        "further increases to nominal coupon auction sizes",
    )

    if any(marker in lower for marker in increase_markers):
        signal = "장기 쿠폰채 증액 또는 증액 예고 문구 감지 — 기간 프리미엄 상승 위험"
    elif any(marker in lower for marker in maintain_markers):
        signal = "명목 쿠폰채·변동금리채 규모 유지 가이던스 감지 — 장기금리 측면 우호적"
    else:
        signal = "정책문구 자동 판정 보류 — 만기별 발행표 직접 확인 필요"
    return signal, policy.url


def preferred_links(links: list[LinkItem]) -> list[LinkItem]:
    priorities = (
        "policy statement",
        "tbac report to secretary",
        "tbac minutes",
        "recommended financing table",
        "auction schedule: pdf",
        "buyback schedule: pdf",
    )
    selected: list[LinkItem] = []
    seen: set[str] = set()
    for priority in priorities:
        for item in links:
            if priority in item.text.lower() and item.url not in seen:
                selected.append(item)
                seen.add(item.url)
                break
    return selected


def build_alert(links: list[LinkItem], policy_signal: str) -> tuple[str, str, dict[str, object]]:
    title = "📋 미국 재무부 2026년 3분기 QRA 세부자료 공개"
    selected = preferred_links(links)
    link_lines = [f"• {item.text}: {item.url}" for item in selected]
    if not link_lines:
        link_lines = [f"• 공식 문서 모음: {QRA_PAGE}"]

    body_lines = [
        "미국 재무부가 2026년 8월 5일 오전 8시 30분(미 동부), 한국시간 오후 9시 30분 QRA 세부자료를 공개했습니다.",
        "",
        "사전 확정 숫자",
        "• 7~9월 민간 보유 순시장성 차입: 7,390억달러",
        "• 9월 말 TGA 목표: 9,500억달러",
        "• 10~12월 순시장성 차입: 6,280억달러",
        "• 12월 말 TGA 목표: 8,500억달러",
        "",
        f"자동 문구 판정: {policy_signal}",
        "",
        "시장 판정 기준",
        "• 10·20·30년물 동결 또는 예상 이하: 기간 프리미엄·장기금리 안정, AI·성장주 우호",
        "• 장기물 증액 또는 향후 증액 예고: 장기 실질금리 상승, AI·성장주 할인율 부담",
        "• 단기국채 중심 조달: 장기금리에는 상대적으로 우호적이나 단기자금시장 부담 점검",
        "",
        "반드시 확인할 항목",
        "• 2·3·5·7·10·20·30년물 및 변동금리채 발행 규모",
        "• ‘적어도 향후 몇 분기’ 유지 문구의 유지·삭제·재작성",
        "• 단기국채·물가연동국채·국채 바이백·SOMA 처리",
        "",
        *link_lines,
        f"• 차입 추정치 원문: {BORROWING_RELEASE}",
    ]
    body = "\n".join(body_lines).strip()
    detail = {
        "status": "release_detected",
        "detected_at_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "qra_page": QRA_PAGE,
        "borrowing_release": BORROWING_RELEASE,
        "policy_signal": policy_signal,
        "links": [{"text": item.text, "url": item.url} for item in selected],
    }
    return title, body, detail


def write_watch(status: str, detail: str = "") -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(KST).isoformat(timespec="seconds")
    text = f"# QRA 2026년 3분기 알림 상태\n\n- 조회시각: {now}\n- 상태: {status}\n"
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

    telegram_test = os.getenv("TELEGRAM_TEST", "false").strip().lower() == "true"
    if telegram_test:
        title = "🧪 QRA 텔레그램 경로 테스트"
        body = (
            "기존 KHS 정책 알림 봇 경로가 정상인지 확인하는 시험 메시지입니다.\n"
            "실제 QRA 세부자료는 2026년 8월 5일 한국시간 오후 9시 30분 이후 공식 공개를 감시합니다."
        )
        TITLE_PATH.write_text(title + "\n", encoding="utf-8")
        ALERT_PATH.write_text(body + "\n", encoding="utf-8")
        DETAIL_PATH.write_text(
            json.dumps({"status": "telegram_test"}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        write_watch("시험 메시지 생성")
        return 0

    state = load_state()
    if state.get("status") == "sent":
        write_watch("이미 전송됨", str(state.get("sent_at_kst", "")))
        return 0

    now_utc = datetime.now(UTC)
    # Avoid accidental annual re-runs of the month/day GitHub cron.
    if now_utc.year != 2026 or now_utc.month != 8 or now_utc.day not in (5, 6):
        write_watch("대상 시간 아님", now_utc.isoformat(timespec="seconds"))
        return 0

    try:
        source = fetch_text(QRA_PAGE)
    except RuntimeError as exc:
        write_watch("공식 페이지 조회 실패", str(exc))
        raise

    parser = QRASectionParser()
    parser.feed(source)
    if not parser.found_target:
        write_watch("세부자료 공개 대기", "8월 5일 8:30 ET 공개 블록 미탐지")
        return 0

    policy_signal, _ = extract_policy_signal(parser.links)
    title, body, detail = build_alert(parser.links, policy_signal)
    TITLE_PATH.write_text(title + "\n", encoding="utf-8")
    ALERT_PATH.write_text(body + "\n", encoding="utf-8")
    DETAIL_PATH.write_text(
        json.dumps(detail, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_watch("공개 감지·전송 대기", policy_signal)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
