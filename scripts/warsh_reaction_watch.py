#!/usr/bin/env python3
import hashlib
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

STATE_PATH = Path("data/warsh_reaction_watch_state.json")
UA = "Mozilla/5.0 (compatible; khs-watch/1.0; +https://github.com/qedgwangju-dot/khs-watch)"
EXPECTED_BOT = os.getenv("EXPECTED_BOT_USERNAME", "khs8879887988798879_bot").lstrip("@")
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
FORCE_NOTIFY = os.getenv("FORCE_NOTIFY", "0") == "1"
STARTUP_NOTIFY = os.getenv("STARTUP_NOTIFY", "0") == "1"

URLS = {
    "employment": "https://www.bls.gov/news.release/empsit.htm",
    "cpi": "https://www.bls.gov/news.release/cpi.nr0.htm",
    "bea_schedule": "https://www.bea.gov/news/schedule/full",
    "fed_speeches": "https://www.federalreserve.gov/newsevents/speeches.htm",
    "fomc_calendar": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
}

KEYWORDS = {
    "employment": ["unemployment rate", "total nonfarm payroll employment", "payroll employment", "unemployed", "average hourly earnings"],
    "cpi": ["consumer price index", "all items", "less food and energy", "core", "12 months", "0.1 percent", "0.2 percent", "0.3 percent", "0.4 percent"],
    "pce": ["pce price index", "excluding food and energy", "personal consumption expenditures", "from the same month one year ago", "prices"],
    "warsh": ["inflation", "prices", "interest rates", "restrictive", "full employment", "financial conditions", "work to do", "federal funds"],
    "fomc": ["federal funds rate", "inflation", "unemployment", "economic activity", "committee decided", "target range"],
}


def fetch(url: str) -> tuple[str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=25) as r:
        raw = r.read().decode("utf-8", errors="replace")
        final = r.geturl()
    return raw, final


def clean_text(raw: str) -> str:
    raw = re.sub(r"(?is)<script.*?>.*?</script>|<style.*?>.*?</style>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</tr>|</h[1-6]>", "\n", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    text = html.unescape(raw).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def fingerprint(text: str) -> str:
    norm = re.sub(r"\s+", " ", text).strip()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def abs_url(base: str, href: str) -> str:
    return urllib.parse.urljoin(base, href)


def find_latest_pce(schedule_html: str) -> str | None:
    hrefs = re.findall(r'href=["\']([^"\']*personal-income-and-outlays[^"\']*)["\']', schedule_html, flags=re.I)
    urls = [abs_url(URLS["bea_schedule"], h) for h in hrefs if "/news/" in h]
    return urls[-1] if urls else None


def find_latest_warsh(speeches_html: str) -> str | None:
    hrefs = re.findall(r'href=["\']([^"\']*warsh\d{8}[a-z]?\.htm)["\']', speeches_html, flags=re.I)
    urls = [abs_url(URLS["fed_speeches"], h) for h in hrefs]
    return urls[0] if urls else None


def find_latest_fomc_statement(calendar_html: str) -> str | None:
    hrefs = re.findall(r'href=["\']([^"\']*/newsevents/pressreleases/monetary\d{8}a\.htm)["\']', calendar_html, flags=re.I)
    urls = [abs_url(URLS["fomc_calendar"], h) for h in hrefs]
    return urls[-1] if urls else None


def release_key(text: str, fallback: str) -> str:
    pats = [
        r"Transmission of material in this release is embargoed until\s*([^\n]{5,100})",
        r"([A-Z][a-z]+ \d{1,2}, 20\d{2})",
        r"(20\d{2}-\d{2}-\d{2})",
    ]
    for p in pats:
        m = re.search(p, text, re.I)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()
    return fallback


def select_lines(text: str, keywords: list[str], limit: int = 8) -> list[str]:
    chunks = re.split(r"(?<=[.!?])\s+|\n+", text)
    out = []
    seen = set()
    for c in chunks:
        s = re.sub(r"\s+", " ", c).strip(" -•\t")
        low = s.lower()
        if len(s) < 25 or len(s) > 450:
            continue
        if any(k in low for k in keywords):
            key = low[:180]
            if key not in seen:
                seen.add(key)
                out.append(s)
        if len(out) >= limit:
            break
    return out


def get_bot_username() -> str:
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN secret is missing")
    url = f"https://api.telegram.org/bot{TOKEN}/getMe"
    with urllib.request.urlopen(url, timeout=20) as r:
        data = json.loads(r.read().decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError("Telegram getMe failed")
    return data["result"].get("username", "")


def telegram_send(text: str) -> None:
    if not TOKEN or not CHAT_ID:
        raise RuntimeError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID secret is missing")
    bot_user = get_bot_username()
    if EXPECTED_BOT and bot_user.lower() != EXPECTED_BOT.lower():
        raise RuntimeError(f"Telegram bot mismatch: token=@{bot_user}, expected=@{EXPECTED_BOT}")
    payload = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text[:4090], "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data=payload)
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read().decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError(f"Telegram sendMessage failed: {data}")


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"version": 1, "sources": {}}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "sources": {}}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def snapshot(name: str, url: str, keywords: list[str]) -> dict:
    raw, final = fetch(url)
    text = clean_text(raw)
    return {
        "url": final,
        "key": release_key(text, final),
        "fingerprint": fingerprint(text),
        "summary": select_lines(text, keywords),
    }


def build_snapshots() -> dict:
    snaps = {}
    snaps["employment"] = snapshot("employment", URLS["employment"], KEYWORDS["employment"])
    snaps["cpi"] = snapshot("cpi", URLS["cpi"], KEYWORDS["cpi"])

    bea_html, _ = fetch(URLS["bea_schedule"])
    pce_url = find_latest_pce(bea_html)
    if pce_url:
        snaps["pce"] = snapshot("pce", pce_url, KEYWORDS["pce"])

    speeches_html, _ = fetch(URLS["fed_speeches"])
    warsh_url = find_latest_warsh(speeches_html)
    if warsh_url:
        snaps["warsh"] = snapshot("warsh", warsh_url, KEYWORDS["warsh"])

    fomc_html, _ = fetch(URLS["fomc_calendar"])
    fomc_url = find_latest_fomc_statement(fomc_html)
    if fomc_url:
        snaps["fomc"] = snapshot("fomc", fomc_url, KEYWORDS["fomc"])
    return snaps


def label(name: str) -> str:
    return {
        "employment": "BLS 고용",
        "cpi": "BLS CPI",
        "pce": "BEA PCE",
        "warsh": "Kevin Warsh 공식 발언",
        "fomc": "FOMC 결정",
    }.get(name, name)


def message_for(name: str, snap: dict) -> str:
    lines = [f"[Warsh 반응함수 변화 감지] {label(name)}", f"기준: {snap.get('key','')}"]
    if snap.get("summary"):
        lines.append("")
        lines.extend(f"• {s}" for s in snap["summary"][:7])
    lines += ["", f"원문: {snap['url']}", "", "판정 기준: 고용 full-employment 전제, 물가 2%로의 충분한 둔화, 금융여건/추가긴축 가능성 변화를 재확인하세요."]
    return "\n".join(lines)


def main() -> int:
    state = load_state()
    old_sources = state.setdefault("sources", {})
    first_run = not bool(old_sources)
    snaps = build_snapshots()
    changed = []

    for name, snap in snaps.items():
        old = old_sources.get(name)
        is_changed = old is not None and (old.get("fingerprint") != snap["fingerprint"] or old.get("url") != snap["url"])
        if FORCE_NOTIFY or is_changed:
            changed.append((name, snap))
        old_sources[name] = {"fingerprint": snap["fingerprint"], "url": snap["url"], "key": snap.get("key")}

    if first_run and STARTUP_NOTIFY:
        telegram_send(
            "[Warsh 반응함수 웹 감시 시작]\n"
            "공식 원천: Federal Reserve / BLS Employment / BLS CPI / BEA PCE / FOMC\n"
            "기준선은 현재 자료로 저장했습니다. 이후 새 발표·공식 페이지 변경이 있을 때만 알립니다.\n"
            f"발신 봇: @{EXPECTED_BOT}"
        )

    for name, snap in changed:
        telegram_send(message_for(name, snap))

    save_state(state)
    print(json.dumps({"first_run": first_run, "changed": [n for n, _ in changed], "sources": list(snaps)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise
