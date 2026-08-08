#!/usr/bin/env python3
"""One-time U.S. Treasury 2026 Q3 QRA Telegram release watcher.

The alert is intentionally interpretation-first: official decision -> wording
change -> market mechanism -> limits -> next checkpoint. Telegram delivery and
duplicate-state persistence are handled by the GitHub Actions workflow.
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
CURRENT_POLICY_RELEASE = "https://home.treasury.gov/news/press-releases/sb0590"
PREVIOUS_POLICY_RELEASE = "https://home.treasury.gov/news/press-releases/sb0489"
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


def html_to_text(source: str) -> str:
    source = re.sub(
        r"<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>",
        " ",
        source,
        flags=re.I | re.S,
    )
    return _clean_text(re.sub(r"<[^>]+>", " ", source))


def load_state() -> dict[str, object]:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def extract_policy_signal(links: list[LinkItem]) -> tuple[str, str | None]:
    """Read current and prior Treasury policy statements and classify wording."""
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
    policy_url = policy.url if policy else CURRENT_POLICY_RELEASE

    try:
        current = html_to_text(fetch_text(policy_url, attempts=2, timeout=25)).lower()
        previous = html_to_text(fetch_text(PREVIOUS_POLICY_RELEASE, attempts=2, timeout=25)).lower()
    except RuntimeError:
        return "공식 문구 자동 비교 보류 — 원문 직접 확인 필요", policy_url

    maintain = "at least the next several quarters" in current
    current_changes = "potential future changes to nominal coupon and frn auction sizes" in current
    previous_increases = "potential future increases to nominal coupon and frn auction sizes" in previous

    if maintain and current_changes and previous_increases:
        return (
            "현 발행 규모 최소 몇 분기 유지 + 직전 ‘future increases(향후 증액)’를 "
            "‘future changes(향후 변경)’로 완화 — 단기 장기금리 우호적, 증액 위험 제거는 아님",
            policy_url,
        )
    if maintain:
        return (
            "현 발행 규모 최소 몇 분기 유지 확인 — 단기 장기금리 우호적, 향후 조정 가능성은 별도 점검",
            policy_url,
        )
    return "정책문구 자동 판정 보류 — 만기별 발행표와 원문 직접 확인 필요", policy_url


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
    title = "🇺🇸 미 재무부, 당분간 중장기 국채 발행 규모 유지 시사"
    selected = preferred_links(links)
    policy_url = next(
        (item.url for item in selected if "policy statement" in item.text.lower()),
        CURRENT_POLICY_RELEASE,
    )

    body_lines = [
        "[핵심 판단]",
        "장기국채 공급 문제가 해결된 것이 아니라, 장기 이표채 증액 신호를 최소 몇 분기 뒤로 미룬 QRA입니다. 단기적으로 10·30년 금리에는 우호적이지만 중장기 공급 부담은 남아 있습니다.",
        "",
        "[확정 결정]",
        "• 재무부: 명목 이표채·FRN 경매 규모를 ‘적어도 향후 몇 분기’ 현 수준으로 유지",
        "• 8월 차환발행: 3년 580억달러 + 10년 420억달러 + 30년 250억달러 = 1,250억달러",
        "• 이 중 만기 차환 963억달러, 민간 신규 현금조달은 287억달러",
        "• 8~10월 2·3·5·7·10·20·30년물 및 FRN 규모는 5~7월과 동일",
        "• 계절적·예상 밖 자금수요는 우선 Bill·CMB 발행 조정으로 대응",
        "",
        "[가장 중요한 문구 변화]",
        "• 5월: potential future increases = ‘향후 증액’ 평가",
        "• 8월: potential future changes = ‘향후 변경’ 평가",
        "→ 향후 발행 확대 가능성을 없앤 것은 아니지만, ‘증액’을 기본 방향처럼 보이게 하던 표현에서 한발 물러났습니다.",
        "",
        f"[자동 원문 대조] {policy_signal}",
        "",
        "[시장 해석]",
        "장기채 증액 신호 없음 → 장기채 공급 충격 완화 → 기간 프리미엄 상승 압력 완화 → 10·30년 금리 안정에 우호적 → AI·성장주 할인율 부담 완화.",
        "",
        "[주의]",
        "• 이것은 ‘TGA가 줄어 유동성이 풀린다’는 호재와 다른 이야기입니다. 이번 QRA의 핵심은 TGA보다 장기 쿠폰채 공급입니다.",
        "• 재무부는 future changes를 계속 평가한다고 명시했습니다. 즉 국채 공급 리스크 제거가 아니라 시간표 이연입니다.",
        "• ‘2027년까지 확정 동결’로 읽으면 과도합니다. 공식 문구는 정확한 종료 시점이 아니라 ‘at least the next several quarters’입니다.",
        "",
        "[다음 확인]",
        "11월 QRA에서 ① ‘at least the next several quarters’ 유지 여부 ② changes가 다시 increases로 바뀌는지 ③ 10·20·30년물 실제 증액 여부를 확인해야 합니다.",
        "",
        "[한 줄] 지금은 안 늘린다 → 단기 장기금리·AI주에 우호적 / 그러나 재정 차입 부담은 남아 있어 장기채 증액 위험은 뒤로 미뤄졌을 뿐.",
        "",
        f"• 재무부 Policy Statement: {policy_url}",
        f"• 차입 추정치: {BORROWING_RELEASE}",
    ]
    body = "\n".join(body_lines).strip()
    detail = {
        "status": "release_detected",
        "detected_at_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "qra_page": QRA_PAGE,
        "borrowing_release": BORROWING_RELEASE,
        "policy_release": policy_url,
        "previous_policy_release": PREVIOUS_POLICY_RELEASE,
        "policy_signal": policy_signal,
        "alert_structure": [
            "핵심 판단",
            "확정 결정",
            "가장 중요한 문구 변화",
            "시장 해석",
            "주의",
            "다음 확인",
            "한 줄",
        ],
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
            "QRA 알림 형식 테스트입니다. 실제 알림은 단순 공개 통지가 아니라 "
            "‘확정 결정 → 문구 변화 → 시장 해석 → 한계 → 다음 확인’ 순서로 전송합니다."
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
    write_watch("공개 감지·해석 완료·전송 대기", policy_signal)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
