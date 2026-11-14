#!/usr/bin/env python3
"""Official Fed policymaker and FOMC schedule additions inside the existing Warsh workflow.

Only the Federal Reserve's actual speech/release body can authorize an alert.
Confirmed send receipts are deduplicated; ambiguous sends remain quarantined.
"""
import calendar
import datetime as dt
import email.utils
import html
import json
import os
import re
import subprocess
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from warsh_speech_watch import clean_text

ROOT = "https://www.federalreserve.gov"
RSS = ROOT + "/feeds/speeches.xml"
ARCHIVE = ROOT + "/newsevents/{year}-speeches.htm"
SCHEDULE = ROOT + "/newsevents/pressreleases/monetary20261112a.htm"
STATE_PATH = Path("data/warsh_fed_board_context_state.json")
BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
EXPECTED_BOT = (os.getenv("EXPECTED_BOT_USERNAME") or "").lstrip("@").strip()
SPEECH_RE = re.compile(
    r"^https://www\.federalreserve\.gov/newsevents/speech/(waller|bowman)(20\d{6}[a-z])\.htm$", re.I
)
SEEDS = (
    ROOT + "/newsevents/speech/waller20261110a.htm",
    ROOT + "/newsevents/speech/bowman20261110a.htm",
)
EVENT_START = dt.date(2026, 11, 10)
SCHEDULE_KEY = "calendar:2027:monetary20261112a"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; KHS-Warsh-watch/2.0)"})
    with urllib.request.urlopen(req, timeout=16) as response:
        actual = urllib.parse.urlparse(response.geturl())
        if actual.scheme != "https" or actual.hostname != "www.federalreserve.gov":
            raise RuntimeError("Official Federal Reserve source redirected to an untrusted host")
        return response.read().decode("utf-8", errors="replace")


def _extract_pubday(link: str):
    match = SPEECH_RE.fullmatch(link)
    if not match:
        return None
    try:
        return dt.datetime.strptime(match.group(2)[:8], "%Y%m%d").date()
    except ValueError:
        return None


def speech_urls(now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    cutoff = max(EVENT_START, now.date() - dt.timedelta(days=21))
    result = {url for url in SEEDS if cutoff <= _extract_pubday(url) <= now.date()}
    errors = []
    try:
        root = ET.fromstring(fetch(RSS))
        for item in root.findall(".//item"):
            url = (item.findtext("link") or "").strip().split("?")[0]
            day = _extract_pubday(url)
            if day and cutoff <= day <= now.date():
                result.add(url)
    except Exception as exc:
        errors.append("연준 연설 RSS: " + type(exc).__name__)

    try:
        archive = fetch(ARCHIVE.format(year=now.year))
        for match in re.finditer(
            r"""href=["']([^"']*/newsevents/speech/(?:waller|bowman)20\d{6}[a-z]\.htm)["']""",
            archive, flags=re.I,
        ):
            url = urllib.parse.urljoin(ROOT, match.group(1))
            day = _extract_pubday(url)
            if day and cutoff <= day <= now.date():
                result.add(url)
    except Exception as exc:
        errors.append("연준 연설 연도별 목록: " + type(exc).__name__)

    return sorted(result, key=lambda x: (_extract_pubday(x), x)), errors


def speech_message(url: str, raw: str):
    match = SPEECH_RE.fullmatch(url)
    if not match:
        return None
    speaker, stamp = match.groups()
    day = dt.datetime.strptime(stamp[:8], "%Y%m%d").date()
    plain = re.sub(r"\s+", " ", clean_text(raw))
    month = calendar.month_name[day.month]
    if f"{month} {day.day}, {day.year}" not in plain:
        raise RuntimeError("Official Fed speech date does not match the link")
    low = plain.lower()
    identity = "christopher j. waller" if speaker.lower() == "waller" else "michelle w. bowman"
    if identity not in low:
        raise RuntimeError("Official Fed speech speaker does not match the link")
    date_label = day.strftime("%Y-%m-%d")
    if speaker.lower() == "waller" and stamp == "20261110a":
        must = ("support a 25 basis point increase", "50 basis point hike", "core cpi", "december meeting")
        if not all(x in low for x in must):
            raise RuntimeError("Waller 25bp/50bp conditional policy text is not verified")
        return "\n".join((
            "[Warsh 연관 연준 위원 공식 발언] 월러",
            "공식 연설: 2026-11-10 / 12월 8~9일 FOMC 전망 (결정 아님)",
            "• 물가가 다소 둔화해도 12월 기준금리 0.25%p 인상을 지지.",
            "• 10월 근원 CPI 전월비가 0.3% 이상이면 0.50%p 인상 검토 필요라는 조건부 견해.",
            "• 물가·연준 신뢰도와 추가긴축 경로가 핵심. 위원 개인 견해이지 FOMC 확정 결정은 아님.",
            "• 이데일리 11월10일 07:50 미 동부시간 보도 당시 0.25%p 인상 확률 84.0%→99.1%(+15.1%p).",
            "  역사적 보도 수치이며 현재 CME 확률이 아님. 공식 API 인증 전 현재 확률 판정은 보류.",
            "보도: https://tv.edaily.co.kr/News/NewsRead?Kind=257&NewsId=07216006645644408",
            "연준 공식 원문: " + url,
        ))
    if speaker.lower() == "bowman" and stamp == "20261110a":
        must = ("off-balance-sheet liabilities", "revenues from ai customers disappoint",
                "benefit of additional policy tightening")
        if not all(x in low for x in must):
            raise RuntimeError("Bowman AI-financing risk/monetary-policy caveat not verified")
        return "\n".join((
            "[Warsh 연관 연준 위원 공식 발언] 보먼",
            "공식 연설: 2026-11-10 / 금융안정 위험 (확정 사고 아님)",
            "• AI 투자의 외부 차입·장기 임대·장부 밖 지급 의무가 확대.",
            "• 2026년 AI 관련 부채 8,000억달러(약 1,069조3,600억원) 초과 전망.",
            "  장기 약정 잠재지급액은 부채의 3배 이상 추정; 기업별 확정 차입액은 아님.",
            "• AI 매출이 비용에 못 미치면 주가 조정→조달비용 상승→신용 축소→투자 둔화 위험.",
            "• 추가 금리 인상은 주택·중소기업 등 차입 민감 부문의 비용과 함께 판단해야 한다는 견해.",
            "• 환산: 11월13일 정부 공표 원/달러 종가 1,336.7원 적용. 금융위기 발생·금리 결정 확정 아님.",
            "연준 공식 원문: " + url,
        ))
    # Subsequent official speeches: only concrete rates/AI-credit text; no invented
    # directional stance or extrapolation of the November 10 probability.
    policy = any(x in low for x in (
        "support an increase in", "support a 25 basis point increase",
        "50 basis point hike", "further tightening of monetary policy",
        "benefit of additional policy tightening",
    ))
    finance = "off-balance-sheet" in low and any(
        x in low for x in ("ai", "artificial intelligence", "data center")
    )
    if not (policy or finance):
        return None
    details = []
    if policy:
        details.append("• 정책금리·추가 긴축과 관련된 명시적 발언이 존재하며, 실행 여부는 미확정.")
    if finance:
        details.append("• AI 투자자금 조달·장부 밖 금융위험에 관한 명시적 경고가 존재하며, 발생 여부는 미확정.")
    return "\n".join((
        f"[Warsh 연관 연준 위원 공식 발언] {'월러' if speaker.lower() == 'waller' else '보먼'}",
        f"공식 연설 날짜: {date_label}",
        *details,
        "원문 표현 확인 단계: 개별 위원의 판단을 FOMC 확정 결정이나 금융위기 발생으로 해석하지 않음.",
        "연준 공식 원문: " + url,
    ))


def schedule_message(raw: str):
    plain = re.sub(r"\s+", " ", clean_text(raw))
    lower = plain.lower()
    required = (
        "revised tentative schedule", "2027", "october 26-27",
        "november 16-17", "broad monetary policy strategy",
        "january 26-27", "march 16-17", "april 27-28",
        "june 8-9", "july 27-28", "september 14-15",
    )
    if not all(x in lower for x in required):
        raise RuntimeError("Official 2027 FOMC schedule revision is not fully verified")
    return "\n".join((
        "[Warsh FOMC 공식 일정 변경] 2027년",
        "연준 발표: 2026-11-12 / 수정 잠정 일정",
        "• 2027년 정례회의 8회 중 실제 금리 결정 회의는 7회.",
        "• 10월 26~27일은 전략 논의 전용: 기준금리 결정·통상 성명 발표 예정 없음.",
        "• 금리 결정일: 1/27·3/17·4/28·6/9·7/28·9/15·11/17 (미국 현지 날짜).",
        "• 기존 12월 연말 회의→11월 16~17일 회의로 변경.",
        "• 2026년 12월 8~9일 예정된 이번 FOMC와 혼동 금지.",
        "• 2027년의 확정 정책경로·인상 횟수가 아니라 회의 운영일정 변경.",
        "연준 공식 원문: " + SCHEDULE,
    ))


def _load_state():
    if not STATE_PATH.exists():
        return {}
    data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("Warsh Fed context state must be a JSON object")
    return data


def load_state():
    state = _load_state()
    # A queued checkout may predate the prior successful sender's state push.
    # Fail closed instead of duplicate sending when the remote status cannot be checked.
    proc = subprocess.run(
        ["git", "fetch", "--quiet", "origin", "main"],
        capture_output=True, text=True, timeout=18,
    )
    if proc.returncode != 0:
        raise RuntimeError("Cannot verify latest remote Warsh state: GitHub fetch failed")
    result = subprocess.run(
        ["git", "show", "origin/main:" + STATE_PATH.as_posix()],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode == 0:
        remote = json.loads(result.stdout)
        if not isinstance(remote, dict):
            raise RuntimeError("Remote Warsh state is invalid")
        for section in ("sent", "pending", "skipped"):
            current = state.setdefault(section, {})
            for key, value in (remote.get(section) or {}).items():
                current[key] = value
        if remote.get("schedule_last_seen") and not state.get("schedule_last_seen"):
            state["schedule_last_seen"] = remote["schedule_last_seen"]
    return state


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def send(msg: str):
    if not BOT_TOKEN or not CHAT_ID or not EXPECTED_BOT:
        raise RuntimeError("Existing Telegram bot/chat settings missing")
    bot_url = f"https://api.telegram.org/bot{BOT_TOKEN}/"
    with urllib.request.urlopen(bot_url + "getMe", timeout=18) as r:
        bot = json.loads(r.read().decode("utf-8"))
    if not bot.get("ok") or str((bot.get("result") or {}).get("username") or "").lower() != EXPECTED_BOT.lower():
        raise RuntimeError("Warsh Telegram bot identity mismatch")
    payload = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": msg[:4000],
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    req = urllib.request.Request(bot_url + "sendMessage", data=payload, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        response = json.loads(r.read().decode("utf-8"))
    result = response.get("result") or {}
    chat = result.get("chat") or {}
    if not response.get("ok"):
        raise RuntimeError("Telegram sendMessage API returned failure")
    actual_id = str(chat.get("id") or "")
    matched = (
        actual_id == CHAT_ID if re.fullmatch(r"-?\d+", CHAT_ID)
        else CHAT_ID.startswith("@") and str(chat.get("username") or "").lower() == CHAT_ID[1:].lower()
    )
    message_id = result.get("message_id")
    if not matched or not isinstance(message_id, int) or message_id <= 0:
        raise RuntimeError("Telegram delivery recipient/message_id cannot be verified; no automatic resend")
    return {"message_id": message_id, "recipient_verified": True}


def deliver(state, key, message, url):
    if key in state.setdefault("sent", {}) or key in state.setdefault("pending", {}):
        return False
    state["pending"][key] = {"status": "sending", "source": url}
    save_state(state)
    try:
        receipt = send(message)
    except Exception:
        state["pending"][key]["status"] = "delivery_uncertain"
        save_state(state)
        raise
    state["sent"][key] = {**receipt, "source": url}
    state["pending"].pop(key, None)
    save_state(state)
    return True


def main():
    state = load_state()
    state.setdefault("sent", {})
    state.setdefault("pending", {})
    state.setdefault("skipped", {})
    delivered = []
    errors = []
    urls, source_errors = speech_urls()
    errors.extend(source_errors)

    for url in urls:
        match = SPEECH_RE.fullmatch(url)
        key = "speech:" + match.group(1).lower() + ":" + match.group(2).lower()
        if key in state["sent"] or key in state["pending"] or key in state["skipped"]:
            continue
        try:
            message = speech_message(url, fetch(url))
            if message is None:
                state["skipped"][key] = {"reason": "no_direct_policy_or_ai_financing_signal"}
                save_state(state)
            elif deliver(state, key, message, url):
                delivered.append(key)
        except Exception as exc:
            errors.append(key + " source/delivery: " + type(exc).__name__)
            if key in state["pending"]:
                raise

    if SCHEDULE_KEY not in state["sent"] and SCHEDULE_KEY not in state["pending"]:
        try:
            message = schedule_message(fetch(SCHEDULE))
            if deliver(state, SCHEDULE_KEY, message, SCHEDULE):
                delivered.append(SCHEDULE_KEY)
        except Exception as exc:
            errors.append("FOMC schedule source/delivery: " + type(exc).__name__)
            if SCHEDULE_KEY in state["pending"]:
                raise

    previous = state.get("source_errors") or []
    if errors != previous:
        state["source_errors"] = errors[:10]
        save_state(state)
    print(json.dumps({
        "official_fed_context": True, "new_sent": delivered,
        "sent_receipts": {key: state["sent"].get(key) for key in delivered},
        "already_sent": len(state["sent"]) - len(delivered),
        "delivery_uncertain": list(state["pending"]),
        "source_errors": errors[:10],
    }, ensure_ascii=False))
    if errors:
        raise RuntimeError("Some official Fed sources could not be verified; confirmed keys preserved")


if __name__ == "__main__":
    main()
