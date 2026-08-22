#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import html
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
BOARD_URL = "https://new.kpx.or.kr/board.es?bid=0042&mid=a11201000000"
EXPECTED_BOT = "hs8879887988798879_bot"
STATE_PATH = pathlib.Path("data/kpx_ess_3rd_watch_state.json")
STATUS_PATH = pathlib.Path("out/kpx_ess_3rd_watch_status.md")
CONFIRM_PATH = pathlib.Path("out/kpx_ess_3rd_telegram_confirmed.json")

ROUTES = [
    ("KHS_POLICY", "KHS_POLICY_TELEGRAM_BOT_TOKEN", "KHS_POLICY_TELEGRAM_CHAT_ID"),
    ("GLOBAL_RATES", "GLOBAL_RATES_TELEGRAM_BOT_TOKEN", "GLOBAL_RATES_TELEGRAM_CHAT_ID"),
    ("BIO", "BIO_TELEGRAM_BOT_TOKEN", "BIO_TELEGRAM_CHAT_ID"),
    ("GENERIC", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"),
]


class AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.anchors: list[dict[str, str]] = []
        self._href: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        if tag.lower() != "a":
            return
        values = dict(attrs)
        href = values.get("href")
        if href:
            self._href = href
            self._parts = []

    def handle_data(self, data: str):
        if self._href is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str):
        if tag.lower() == "a" and self._href is not None:
            text = re.sub(r"\s+", " ", "".join(self._parts)).strip()
            self.anchors.append({"href": self._href, "text": html.unescape(text)})
            self._href = None
            self._parts = []


def fetch(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; khs-watch/1.0; +https://github.com/qedgwangju-dot/khs-watch)",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        charset = r.headers.get_content_charset() or "utf-8"
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def normalize_title(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def is_target_title(title: str) -> bool:
    t = normalize_title(title).lower()
    if "ess" not in t or "중앙계약시장" not in t:
        return False
    # 의견수렴/간담회/설명회는 제외하고 실제 입찰 공고만 잡는다.
    if any(x in t for x in ["의견수렴", "간담회", "설명회"]):
        return False
    if not any(x in t for x in ["경쟁입찰", "입찰공고", "입찰 공고"]):
        return False
    # 제3차 표기가 가장 강한 조건. 2026년 공고가 제3차 표기를 생략할 경우도 보조 허용.
    third = any(x in t for x in ["제3차", "제 3차", "3차"])
    year_2026 = any(x in t for x in ["2026", "'26", "‘26", "26년도", "26년"])
    return third or year_2026


def extract_candidates(page: str) -> list[dict[str, str]]:
    parser = AnchorParser()
    parser.feed(page)
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for a in parser.anchors:
        title = normalize_title(a["text"])
        if not is_target_title(title):
            continue
        href = urllib.parse.urljoin(BOARD_URL, a["href"])
        # 목록 이동/검색 링크가 섞이는 것을 막고 게시물 상세 링크만 보존한다.
        if "board.es" not in href or "act=view" not in href:
            continue
        key = href
        if key in seen:
            continue
        seen.add(key)
        out.append({"title": title, "url": href})
    return out


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def find_telegram_route() -> tuple[str, str, str, str]:
    checked: list[str] = []
    for label, token_env, chat_env in ROUTES:
        token = (os.getenv(token_env) or "").strip()
        chat_id = (os.getenv(chat_env) or "").strip()
        if not token or not chat_id:
            continue
        checked.append(label)
        try:
            with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getMe", timeout=25) as r:
                result = json.loads(r.read().decode("utf-8"))
        except Exception as e:
            print(f"telegram_route_check_failed={label}: {e}", file=sys.stderr)
            continue
        username = str((result.get("result") or {}).get("username") or "").strip()
        if result.get("ok") and username.lower() == EXPECTED_BOT.lower():
            return label, token, chat_id, username
    raise RuntimeError(
        f"No configured Telegram secret pair matched @{EXPECTED_BOT}; checked={checked or ['none configured']}"
    )


def send_telegram(token: str, chat_id: str, text: str) -> int:
    payload = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        result = json.loads(r.read().decode("utf-8"))
    if not result.get("ok"):
        raise RuntimeError(f"Telegram rejected message: {result}")
    return int((result.get("result") or {}).get("message_id"))


def write_status(lines: list[str]) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    now = dt.datetime.now(KST)
    page = fetch(BOARD_URL)
    candidates = extract_candidates(page)
    state = load_state()
    first_run = not bool(state)
    seen_urls = set(state.get("seen_urls") or [])
    new_items = [x for x in candidates if x["url"] not in seen_urls]

    route_label, token, chat_id, bot_username = find_telegram_route()
    message_ids: list[int] = []

    if first_run:
        setup_text = (
            "✅ <b>제3차 ESS 중앙계약시장 웹 감시 설정 완료</b>\n\n"
            "전력거래소 공식 공지사항을 15분 간격으로 확인합니다.\n"
            "- 감시 대상: 제3차 ESS 중앙계약시장 경쟁입찰 공고\n"
            "- 알림 조건: 새 공식 입찰 공고가 게시될 때만\n"
            f"- 확인 시각: {now.strftime('%Y-%m-%d %H:%M:%S KST')}\n"
            f"- 대상 봇: @{html.escape(bot_username)}\n\n"
            f"<a href=\"{html.escape(BOARD_URL, quote=True)}\">전력거래소 공식 공지사항</a>"
        )
        message_ids.append(send_telegram(token, chat_id, setup_text))
        # 최초 기준선에서는 이미 존재하던 게시물은 경보로 보내지 않는다.
        new_items = []

    for item in new_items:
        alert = (
            "🚨 <b>제3차 ESS 중앙계약시장 입찰 공고 감지</b>\n\n"
            f"<b>{html.escape(item['title'])}</b>\n"
            f"- 감지 시각: {now.strftime('%Y-%m-%d %H:%M:%S KST')}\n"
            "- 원천: 한국전력거래소 공식 공지사항\n\n"
            f"<a href=\"{html.escape(item['url'], quote=True)}\">공고 원문 열기</a>"
        )
        message_ids.append(send_telegram(token, chat_id, alert))

    # Telegram 성공 후에만 상태를 전진시킨다. 실패 시 다음 실행에서 재시도된다.
    merged_seen = sorted(seen_urls | {x["url"] for x in candidates})
    new_state = {
        "watch": "KPX 3rd ESS central contract market competitive bidding notice",
        "source": BOARD_URL,
        "expected_bot_username": EXPECTED_BOT,
        "telegram_route_label": route_label,
        "seen_urls": merged_seen,
        "last_candidates": candidates,
        "last_checked_at_kst": now.isoformat(timespec="seconds"),
        "last_new_items": new_items,
    }
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(new_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if message_ids:
        CONFIRM_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIRM_PATH.write_text(
            json.dumps(
                {
                    "telegram_delivery_confirmed": True,
                    "bot_username": bot_username,
                    "route_label": route_label,
                    "message_ids": message_ids,
                    "confirmed_at_kst": now.isoformat(timespec="seconds"),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    write_status(
        [
            "# 제3차 ESS 중앙계약시장 감시 상태",
            "",
            f"- 확인 시각: {now.strftime('%Y-%m-%d %H:%M:%S KST')}",
            f"- 공식 원천: {BOARD_URL}",
            f"- 대상 봇: @{bot_username}",
            f"- Telegram 경로: {route_label}",
            f"- 현재 대상 공고 수: {len(candidates)}",
            f"- 이번 신규 공고 수: {len(new_items)}",
            f"- Telegram 전송 메시지 ID: {message_ids or '없음'}",
        ]
    )
    print(
        f"kpx_ess_watch_ok=true bot=@{bot_username} route={route_label} "
        f"candidates={len(candidates)} new={len(new_items)} messages={message_ids}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
