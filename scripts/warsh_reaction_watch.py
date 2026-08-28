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
UA = "Mozilla/5.0 (compatible; khs-watch/1.1; +https://github.com/qedgwangju-dot/khs-watch)"
EXPECTED_BOT = os.getenv("EXPECTED_BOT_USERNAME", "khs8879887988798879_bot").lstrip("@")
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
FORCE_NOTIFY = os.getenv("FORCE_NOTIFY", "0") == "1"
STARTUP_NOTIFY = os.getenv("STARTUP_NOTIFY", "0") == "1"

URLS = {
    "employment": "https://www.bls.gov/news.release/empsit.htm",
    "cpi": "https://www.bls.gov/news.release/cpi.nr0.htm",
    "bls_api": "https://api.bls.gov/publicAPI/v2/timeseries/data/",
    "bea_schedule": "https://www.bea.gov/news/schedule/full",
    "fed_speeches": "https://www.federalreserve.gov/newsevents/speeches.htm",
    "fomc_calendar": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
}

KEYWORDS = {
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


def post_json(url: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"User-Agent": UA, "Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))


def clean_text(raw: str) -> str:
    raw = re.sub(r"(?is)<script.*?>.*?</script>|<style.*?>.*?</style>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</tr>|</h[1-6]>", "\n", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    text = html.unescape(raw).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def fingerprint_obj(obj) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def fingerprint_text(text: str) -> str:
    return fingerprint_obj(re.sub(r"\s+", " ", text).strip())


def abs_url(base: str, href: str) -> str:
    return urllib.parse.urljoin(base, href)


def find_latest_pce(schedule_html: str) -> str | None:
    hrefs = re.findall(r'href=["\']([^"\']*personal-income-and-outlays[^"\']*)["\']', schedule_html, flags=re.I)
    urls = [abs_url(URLS["bea_schedule"], h) for h in hrefs if "/news/" in h]
    return urls[-1] if urls else None


def _dated_url(urls: list[str], pattern: str) -> str | None:
    dated = []
    for u in urls:
        m = re.search(pattern, u, re.I)
        if m:
            dated.append((m.group(1), u))
    return max(dated)[1] if dated else None


def find_latest_warsh(speeches_html: str) -> str | None:
    hrefs = re.findall(r'href=["\']([^"\']*warsh\d{8}[a-z]?\.htm)["\']', speeches_html, flags=re.I)
    urls = [abs_url(URLS["fed_speeches"], h) for h in hrefs]
    return _dated_url(urls, r"warsh(\d{8})")


def find_latest_fomc_statement(calendar_html: str) -> str | None:
    hrefs = re.findall(r'href=["\']([^"\']*/newsevents/pressreleases/monetary\d{8}a\.htm)["\']', calendar_html, flags=re.I)
    urls = [abs_url(URLS["fomc_calendar"], h) for h in hrefs]
    return _dated_url(urls, r"monetary(\d{8})a")


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


def select_lines(text: str, keywords: list[str], limit: int = 7) -> list[str]:
    chunks = re.split(r"(?<=[.!?])\s+|\n+", text)
    out, seen = [], set()
    for c in chunks:
        s = re.sub(r"\s+", " ", c).strip(" -•\t")
        low = s.lower()
        if len(s) < 25 or len(s) > 450:
            continue
        if any(k in low for k in keywords):
            k = low[:180]
            if k not in seen:
                seen.add(k)
                out.append(s)
        if len(out) >= limit:
            break
    return out


def series_values(series: dict) -> dict[tuple[int, int], float]:
    out = {}
    for row in series.get("data", []):
        p = row.get("period", "")
        if not re.fullmatch(r"M(0[1-9]|1[0-2])", p):
            continue
        try:
            out[(int(row["year"]), int(p[1:]))] = float(row["value"].replace(",", ""))
        except Exception:
            pass
    return out


def previous_month(period: tuple[int, int]) -> tuple[int, int]:
    y, m = period
    return (y - 1, 12) if m == 1 else (y, m - 1)


def bls_snapshots() -> dict:
    now = datetime.now(timezone.utc)
    series_ids = ["CES0000000001", "LNS14000000", "CUSR0000SA0", "CUSR0000SA0L1E"]
    data = post_json(URLS["bls_api"], {
        "seriesid": series_ids,
        "startyear": str(now.year - 1),
        "endyear": str(now.year),
    })
    if data.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(f"BLS API failed: {data.get('message')}")
    by_id = {s["seriesID"]: series_values(s) for s in data.get("Results", {}).get("series", [])}

    payroll = by_id.get("CES0000000001", {})
    urate = by_id.get("LNS14000000", {})
    common_emp = sorted(set(payroll) & set(urate))
    if not common_emp:
        raise RuntimeError("BLS employment series have no common month")
    ep = common_emp[-1]
    eprev = previous_month(ep)
    payroll_change = payroll.get(ep) - payroll.get(eprev) if eprev in payroll else None
    emp_payload = {"period": ep, "payroll": payroll.get(ep), "payroll_change": payroll_change, "unemployment_rate": urate.get(ep)}
    emp_summary = [f"실업률 {urate[ep]:.1f}%"]
    if payroll_change is not None:
        emp_summary.append(f"비농업 고용 전월 대비 {payroll_change:+.0f}천명")
    emp_summary.append("Warsh 기준: full-employment 전제가 약화되는지 확인")

    cpi = by_id.get("CUSR0000SA0", {})
    core = by_id.get("CUSR0000SA0L1E", {})
    common_cpi = sorted(set(cpi) & set(core))
    if not common_cpi:
        raise RuntimeError("BLS CPI series have no common month")
    cp = common_cpi[-1]
    cprev = previous_month(cp)
    cyago = (cp[0] - 1, cp[1])
    def pct(a, b):
        return (a / b - 1.0) * 100.0
    cpi_mom = pct(cpi[cp], cpi[cprev]) if cprev in cpi else None
    cpi_yoy = pct(cpi[cp], cpi[cyago]) if cyago in cpi else None
    core_mom = pct(core[cp], core[cprev]) if cprev in core else None
    core_yoy = pct(core[cp], core[cyago]) if cyago in core else None
    cpi_payload = {"period": cp, "cpi": cpi[cp], "core": core[cp], "cpi_mom": cpi_mom, "cpi_yoy": cpi_yoy, "core_mom": core_mom, "core_yoy": core_yoy}
    cpi_summary = []
    if cpi_mom is not None and cpi_yoy is not None:
        cpi_summary.append(f"Headline CPI {cpi_mom:+.1f}% MoM / {cpi_yoy:+.1f}% YoY")
    if core_mom is not None and core_yoy is not None:
        cpi_summary.append(f"Core CPI {core_mom:+.1f}% MoM / {core_yoy:+.1f}% YoY")
    cpi_summary.append("Warsh 기준: 2% 목표로 명확하고 충분한 속도로 둔화하는지 확인")

    return {
        "employment": {"url": URLS["employment"], "key": f"{ep[0]}-{ep[1]:02d}", "fingerprint": fingerprint_obj(emp_payload), "summary": emp_summary},
        "cpi": {"url": URLS["cpi"], "key": f"{cp[0]}-{cp[1]:02d}", "fingerprint": fingerprint_obj(cpi_payload), "summary": cpi_summary},
    }


def get_bot_username() -> str:
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN secret is missing")
    with urllib.request.urlopen(f"https://api.telegram.org/bot{TOKEN}/getMe", timeout=20) as r:
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
        return {"version": 2, "sources": {}}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 2, "sources": {}}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def html_snapshot(url: str, keywords: list[str]) -> dict:
    raw, final = fetch(url)
    text = clean_text(raw)
    return {"url": final, "key": release_key(text, final), "fingerprint": fingerprint_text(text), "summary": select_lines(text, keywords)}


def build_snapshots() -> tuple[dict, list[str]]:
    snaps, errors = {}, []
    try:
        snaps.update(bls_snapshots())
    except Exception as e:
        errors.append(f"BLS: {e}")

    try:
        bea_html, _ = fetch(URLS["bea_schedule"])
        pce_url = find_latest_pce(bea_html)
        if pce_url:
            snaps["pce"] = html_snapshot(pce_url, KEYWORDS["pce"])
        else:
            errors.append("BEA PCE: latest release link not found")
    except Exception as e:
        errors.append(f"BEA PCE: {e}")

    try:
        speeches_html, _ = fetch(URLS["fed_speeches"])
        warsh_url = find_latest_warsh(speeches_html)
        if warsh_url:
            snaps["warsh"] = html_snapshot(warsh_url, KEYWORDS["warsh"])
        else:
            errors.append("Fed speeches: latest Warsh speech not found")
    except Exception as e:
        errors.append(f"Fed speeches: {e}")

    try:
        fomc_html, _ = fetch(URLS["fomc_calendar"])
        fomc_url = find_latest_fomc_statement(fomc_html)
        if fomc_url:
            snaps["fomc"] = html_snapshot(fomc_url, KEYWORDS["fomc"])
        else:
            errors.append("FOMC: latest statement not found")
    except Exception as e:
        errors.append(f"FOMC: {e}")
    return snaps, errors


def label(name: str) -> str:
    return {"employment": "BLS 고용", "cpi": "BLS CPI", "pce": "BEA PCE", "warsh": "Kevin Warsh 공식 발언", "fomc": "FOMC 결정"}.get(name, name)


def message_for(name: str, snap: dict) -> str:
    lines = [f"[Warsh 반응함수 변화 감지] {label(name)}", f"기준: {snap.get('key','')}"]
    if snap.get("summary"):
        lines.append("")
        lines.extend(f"• {s}" for s in snap["summary"][:7])
    lines += ["", f"원문: {snap['url']}", "", "판정: full-employment 전제, 물가 2%로의 충분한 둔화, 추가긴축 가능성이 강화/약화되는지 확인"]
    return "\n".join(lines)


def main() -> int:
    state = load_state()
    old_sources = state.setdefault("sources", {})
    first_run = not bool(old_sources)
    snaps, errors = build_snapshots()
    if not snaps:
        raise RuntimeError("All official sources failed: " + " | ".join(errors))
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
            "공식 원천: Federal Reserve / BLS API(고용·CPI) / BEA PCE / FOMC\n"
            "현재 자료를 기준선으로 저장하고 이후 새 발표·공식 변경이 있을 때만 알립니다.\n"
            f"발신 봇: @{EXPECTED_BOT}"
        )
    for name, snap in changed:
        telegram_send(message_for(name, snap))

    state["last_errors"] = errors
    save_state(state)
    print(json.dumps({"first_run": first_run, "changed": [n for n, _ in changed], "sources": list(snaps), "errors": errors}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise
