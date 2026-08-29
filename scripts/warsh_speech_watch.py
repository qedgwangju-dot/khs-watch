#!/usr/bin/env python3
import email.utils
import html
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

RSS_URL = "https://www.federalreserve.gov/feeds/speeches.xml"
STATE_PATH = Path("data/warsh_speech_watch_state.json")
UA = "Mozilla/5.0 (compatible; khs-watch/1.1; +https://github.com/qedgwangju-dot/khs-watch)"
TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
EXPECTED_BOT = (os.getenv("EXPECTED_BOT_USERNAME") or "khs8879887988798879_bot").strip().lstrip("@")
FORCE_NOTIFY = os.getenv("FORCE_NOTIFY", "0") == "1"

KEYWORDS = [
    "inflation", "prices", "interest rate", "federal funds", "restrictive",
    "financial conditions", "full employment", "labor market", "work to do",
    "forward guidance", "monetary policy", "rate hike", "raise rates",
    "further tightening", "rate cut", "lower rates"
]

# 'hike' by itself is not a monetary-policy signal. Jackson Hole trail/hiking jokes are excluded.
HIKING_CONTEXT = [
    "trail", "trails", "hiking", "stroll", "rockefeller preserve", "kohn day",
    "bernanke day", "don kohn", "ben bernanke", "wellness check"
]
MONETARY_HIKE_CONTEXT = [
    "rate hike", "interest-rate hike", "interest rate hike", "hike rates",
    "hiking rates", "raise rates", "raising rates", "federal funds rate"
]

HAWKISH_TERMS = [
    "predominant focus", "prices", "inflation", "work to do", "not restrictive",
    "hard pressed to describe broad financial conditions as restrictive",
    "rate hike", "raise rates", "raising rates", "further tightening",
    "short-term interest rates are the predominant tool"
]
DOVISH_TERMS = [
    "rate cut", "lower rates", "lowering rates", "labor market deterioration",
    "downside risks to employment", "unemployment has risen", "policy is restrictive"
]


def fetch(url: str) -> tuple[str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", errors="replace"), r.geturl()


def clean_text(raw: str) -> str:
    raw = re.sub(r"(?is)<script.*?>.*?</script>|<style.*?>.*?</style>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h[1-6]>", "\n", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    text = html.unescape(raw).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def parse_date(value: str) -> datetime:
    try:
        dt = email.utils.parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


def latest_warsh_item(xml_text: str):
    root = ET.fromstring(xml_text)
    items = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        desc = (item.findtext("description") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        blob = f"{title}\n{desc}".lower()
        if "warsh" not in blob and "kevin" not in blob:
            continue
        if not link:
            continue
        items.append((parse_date(pub), title, link, pub))
    if not items:
        return None
    items.sort(key=lambda x: x[0])
    return items[-1]


def is_hiking_only(sentence: str) -> bool:
    low = sentence.lower()
    has_hike = bool(re.search(r"\bhikes?\b|\bhiking\b", low))
    if not has_hike:
        return False
    if any(term in low for term in MONETARY_HIKE_CONTEXT):
        return False
    return any(term in low for term in HIKING_CONTEXT)


def select_lines(text: str, limit: int = 7):
    chunks = re.split(r"(?<=[.!?])\s+|\n+", text)
    out, seen = [], set()
    for chunk in chunks:
        s = re.sub(r"\s+", " ", chunk).strip(" -•\t")
        low = s.lower()
        if len(s) < 25 or len(s) > 450:
            continue
        if is_hiking_only(s):
            continue
        if any(k in low for k in KEYWORDS):
            key = low[:180]
            if key not in seen:
                seen.add(key)
                out.append(s)
        if len(out) >= limit:
            break
    return out


def classify_policy_tone(text: str) -> tuple[str, int, int]:
    low = text.lower()
    # Remove sentences that use hike only as recreation/trail language.
    cleaned = " ".join(
        s for s in re.split(r"(?<=[.!?])\s+|\n+", low)
        if s and not is_hiking_only(s)
    )
    hawk = sum(1 for term in HAWKISH_TERMS if term in cleaned)
    dove = sum(1 for term in DOVISH_TERMS if term in cleaned)
    if hawk >= dove + 2:
        tone = "매파 강화"
    elif dove >= hawk + 2:
        tone = "비둘기 강화"
    else:
        tone = "조건부/혼합"
    return tone, hawk, dove


def get_bot_username() -> str:
    if not TOKEN:
        raise RuntimeError("Telegram token missing")
    with urllib.request.urlopen(f"https://api.telegram.org/bot{TOKEN}/getMe", timeout=20) as r:
        data = json.loads(r.read().decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError("Telegram getMe failed")
    return str((data.get("result") or {}).get("username") or "")


def send(text: str):
    if not TOKEN or not CHAT_ID:
        raise RuntimeError("Telegram token/chat id missing")
    username = get_bot_username()
    if username.lower() != EXPECTED_BOT.lower():
        raise RuntimeError(f"Wrong Telegram bot: expected @{EXPECTED_BOT}, got @{username}")
    payload = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": text[:4090],
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data=payload, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read().decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError(f"Telegram send failed: {data}")


def load_state():
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    rss, _ = fetch(RSS_URL)
    item = latest_warsh_item(rss)
    if not item:
        raise RuntimeError("No Kevin Warsh item found in official Fed speeches RSS")
    dt, title, link, pub = item
    old = load_state()
    new_key = link
    first_run = not bool(old.get("last_link"))
    changed = old.get("last_link") not in (None, new_key)

    if FORCE_NOTIFY or changed:
        raw, final = fetch(link)
        text = clean_text(raw)
        lines = select_lines(text)
        tone, hawk, dove = classify_policy_tone(text)
        msg = [
            "[Kevin Warsh 공식 발언 변화 감지]",
            f"제목: {title}",
            f"발표: {pub or dt.isoformat()}",
            f"정책 톤: {tone} (매파 문맥 {hawk} / 비둘기 문맥 {dove})",
            "",
        ]
        msg.extend(f"• {x}" for x in lines)
        msg += [
            "",
            "오탐 필터: trail/stroll/Kohn/Bernanke 등 등산 문맥의 'hike'는 금리인상 신호에서 제외",
            f"원문: {final}",
            "",
            "판정: 물가 우선·금융여건·full employment·추가 금리인상 선택지가 강화/약화되는지 재확인",
        ]
        send("\n".join(msg))

    save_state({"last_link": new_key, "last_title": title, "last_pub_date": pub})
    print(json.dumps({"first_run": first_run, "changed": changed, "latest": link}, ensure_ascii=False))


if __name__ == "__main__":
    main()
