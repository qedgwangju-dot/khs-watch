#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from typing import Any
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

KST = ZoneInfo("Asia/Seoul")
ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
DATA = ROOT / "data"
OUT.mkdir(parents=True, exist_ok=True)
DATA.mkdir(parents=True, exist_ok=True)
STATE_PATH = DATA / "bok_mpc_watch_state.json"
ALERT_PATH = OUT / "bok_mpc_alert.html"
STATUS_PATH = OUT / "bok_mpc_status.md"
ERROR_PATH = OUT / "bok_mpc_errors.log"
PENDING_PATH = OUT / "bok_mpc_pending_state.json"

BOK_RSS = "https://www.bok.or.kr/portal/bbs/P0000559/news.rss?menuNo=200690"
GOOGLE_NEWS = "https://news.google.com/rss/search"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; khs-bok-mpc-watch/2.1)",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}


def get(url: str, timeout: int = 35) -> requests.Response:
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def latest_bok_statement() -> dict[str, Any]:
    root = ET.fromstring(get(BOK_RSS).content)
    for item in root.findall(".//item"):
        title = normalize(item.findtext("title") or "")
        if "통화정책방향" not in title:
            continue
        link = normalize(item.findtext("link") or "")
        if not link:
            continue
        page = BeautifulSoup(get(link).text, "html.parser")
        text = normalize(page.get_text(" ", strip=True))
        return {
            "title": title,
            "url": link,
            "text": text,
            "hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        }
    raise RuntimeError("한국은행 통화정책 RSS에서 최신 통화정책방향을 찾지 못함")


def pct_values(text: str) -> list[float]:
    return [float(x) for x in re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*%", text)]


def window_after(text: str, key: str, length: int = 420) -> str:
    idx = text.find(key)
    if idx < 0:
        return ""
    return text[idx: idx + length]


def parse_statement(stmt: dict[str, Any]) -> dict[str, Any]:
    text = stmt["text"]
    out: dict[str, Any] = {"title": stmt["title"], "url": stmt["url"], "hash": stmt["hash"], "parser_version": 2}

    rate_window = window_after(text, "한국은행 기준금리를", 260)
    vals = pct_values(rate_window)
    if len(vals) >= 2:
        out["rate_from"], out["rate_to"] = vals[0], vals[1]

    growth_window = window_after(text, "금년 및 내년 성장률", 420)
    vals = pct_values(growth_window)
    if len(vals) >= 2:
        out["growth_this"], out["growth_next"] = vals[-2], vals[-1]

    cpi_window = window_after(text, "금년 및 내년 소비자물가 상승률", 420)
    vals = pct_values(cpi_window)
    if len(vals) >= 2:
        out["cpi_this"], out["cpi_next"] = vals[-2], vals[-1]

    core_window = window_after(text, "근원물가 상승률", 420)
    vals = pct_values(core_window)
    if vals:
        if "모두" in core_window[:260]:
            out["core_this"] = out["core_next"] = vals[-1]
        elif len(vals) >= 2:
            out["core_this"], out["core_next"] = vals[-2], vals[-1]

    m = re.search(r"금융통화위원\s*([0-9]+)명은\s*찬성", text)
    if m:
        out["vote_for"] = int(m.group(1))
    out["minority_hold"] = bool(
        re.search(r"위원은\s*기준금리를\s*[0-9.]+%?로\s*유지", text)
        or ("황건일 위원" in text and "유지하는 것이 바람직" in text)
    )

    out["flags"] = {
        "preemptive": "선제적 대응" in text,
        "hike_bias": "금리인상 기조를 이어나갈 필요" in text,
        "timing_speed": "추가 인상의 시기와 속도" in text,
        "housing": "수도권 주택가격" in text,
        "household_debt": "가계부채" in text or "가계대출" in text,
        "fx_volatility": "높은 환율 변동성" in text,
        "domestic_recovery": "내수 회복" in text or "소비 회복세" in text,
    }
    return out


def google_news(query: str, limit: int = 30) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"})
    root = ET.fromstring(get(f"{GOOGLE_NEWS}?{params}").content)
    rows = []
    for item in root.findall(".//item")[:limit]:
        pub = normalize(item.findtext("pubDate") or "")
        try:
            pdt = parsedate_to_datetime(pub)
            if pdt.tzinfo is None:
                pdt = pdt.replace(tzinfo=dt.timezone.utc)
        except Exception:
            pdt = None
        rows.append({
            "title": normalize(item.findtext("title") or ""),
            "link": normalize(item.findtext("link") or ""),
            "description": normalize(BeautifulSoup(item.findtext("description") or "", "html.parser").get_text(" ", strip=True)),
            "published_dt": pdt,
        })
    return rows


def latest_dotplot(now: dt.datetime) -> dict[str, Any] | None:
    cutoff = now.astimezone(dt.timezone.utc) - dt.timedelta(days=10)
    found: dict[str, int] = {}
    source_link = ""
    source_title = ""
    for item in google_news('금통위원 6개월 금리전망 3.00 3.25 3.50', 30):
        if not item.get("published_dt") or item["published_dt"] < cutoff:
            continue
        blob = item["title"] + " " + item["description"]
        for level in ("2.75", "3.00", "3.25", "3.50", "3.75"):
            if level in found:
                continue
            for pat in (
                rf"{re.escape(level)}%?[^0-9]{{0,30}}([0-9]+)개",
                rf"([0-9]+)개[^0-9]{{0,30}}{re.escape(level)}%",
            ):
                m = re.search(pat, blob)
                if m:
                    found[level] = int(m.group(1))
                    if not source_link:
                        source_link, source_title = item["link"], item["title"]
                    break
    if len(found) < 2:
        return None
    return {
        "title": source_title,
        "link": source_link,
        "counts": found,
        "total": sum(found.values()),
        "hash": hashlib.sha256(json.dumps(found, sort_keys=True).encode()).hexdigest(),
    }


def fmt_rate(x: float | None) -> str:
    if x is None:
        return "확인 불가"
    return f"{x:.2f}%".replace(".00%", "%")


def build_alert(p: dict[str, Any], dot: dict[str, Any] | None, correction: bool) -> str:
    title = "🔄 <b>한국은행 금통위 정정·최신 알림</b>" if correction else "🏦 <b>한국은행 금통위 핵심 알림</b>"
    lines = [title, ""]
    if "rate_to" in p:
        lines.append(f"• 기준금리: <b>{fmt_rate(p.get('rate_from'))} → {fmt_rate(p.get('rate_to'))}</b>")
    if p.get("vote_for"):
        tail = " / 동결 소수의견 1명" if p.get("minority_hold") else ""
        lines.append(f"• 표결: <b>인상 찬성 {p['vote_for']}명{tail}</b>")
    if "growth_this" in p:
        lines.append(f"• 성장률 전망: <b>올해 {p['growth_this']:.1f}% / 내년 {p['growth_next']:.1f}%</b>")
    if "cpi_this" in p:
        lines.append(f"• 소비자물가: <b>올해 {p['cpi_this']:.1f}% / 내년 {p['cpi_next']:.1f}%</b>")
    if "core_this" in p:
        lines.append(f"• 근원물가: <b>올해 {p['core_this']:.1f}% / 내년 {p['core_next']:.1f}%</b>")

    if dot:
        order = [x for x in ("2.75", "3.00", "3.25", "3.50", "3.75") if x in dot["counts"]]
        dist = " / ".join(f"{x}% {dot['counts'][x]}개" for x in order)
        lines += ["", f"• 6개월 조건부 금리전망: <b>{dist}</b>"]
        cur = p.get("rate_to")
        if cur is not None and dot.get("total"):
            above = sum(v for k, v in dot["counts"].items() if float(k) > cur)
            lines.append(f"• 현재보다 높은 점: <b>{above}/{dot['total']}개</b> → 추가 인상 쪽 우세")

    f = p.get("flags") or {}
    lines += ["", "<b>문구 변화 해석</b>"]
    if f.get("preemptive"):
        lines.append("• <b>‘선제적 대응으로 물가 오름세 확산 방지’</b> → 이번 행동은 매파적")
    if f.get("domestic_recovery"):
        lines.append("• 수출뿐 아니라 <b>내수·소비 회복</b>까지 성장 근거에 포함")
    if f.get("housing") and f.get("household_debt"):
        lines.append("• <b>수도권 집값 + 가계부채</b>는 여전히 추가 인상 근거")
    if f.get("timing_speed") and not f.get("hike_bias"):
        lines.append("• ‘금리인상 기조 지속 필요’보다 <b>추가 인상의 시기·속도 판단</b>으로 표현이 유연해짐")
    if not f.get("fx_volatility"):
        lines.append("• 환율 문구 비중은 낮아지고 <b>근원물가·내수·집값·가계부채</b>가 전면에 남음")

    lines += ["", "<b>최종 판정</b>", "• <b>행동은 매파적 / 향후 속도는 유연 / 최종금리 방향은 아직 상향 / 핵심 확인은 근원물가·소비·수도권 집값·가계대출</b>"]
    lines += ["", f'• <a href="{html.escape(p["url"], quote=True)}">한국은행 원문</a>']
    if dot:
        lines.append(f'• <a href="{html.escape(dot["link"], quote=True)}">6개월 금리전망 근거</a>')
    return "\n".join(lines)


def main() -> int:
    for path in (ALERT_PATH, ERROR_PATH):
        path.unlink(missing_ok=True)
    now = dt.datetime.now(KST)
    old = load_state()
    errors = []

    try:
        statement = latest_bok_statement()
        parsed = parse_statement(statement)
    except Exception as exc:
        ERROR_PATH.write_text(f"통화정책방향 조회 실패: {type(exc).__name__}: {exc}\n", encoding="utf-8")
        return 2

    try:
        dot = latest_dotplot(now)
    except Exception as exc:
        dot = None
        errors.append(f"점도표 조회 실패: {type(exc).__name__}: {exc}")

    correction = (old.get("statement") or {}).get("parser_version") != 2
    bootstrap = not bool(old)
    statement_changed = old.get("statement_hash") != parsed.get("hash")
    dot_changed = bool(dot) and old.get("dotplot_hash") != dot.get("hash")
    if bootstrap or correction or statement_changed or dot_changed:
        ALERT_PATH.write_text(build_alert(parsed, dot, correction and not bootstrap), encoding="utf-8")

    pending = {
        "updated_at_kst": now.isoformat(timespec="seconds"),
        "statement_hash": parsed.get("hash"),
        "statement": parsed,
        "dotplot_hash": dot.get("hash") if dot else old.get("dotplot_hash"),
        "dotplot": dot if dot else old.get("dotplot"),
    }
    PENDING_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    status = [
        "# 한국은행 금통위 감시", "",
        f"- 확인시각(KST): {now:%Y-%m-%d %H:%M:%S}",
        f"- 최신 문서: {parsed.get('title')}",
        f"- 기준금리: {parsed.get('rate_to', '확인 불가')}",
        f"- 성장률: {parsed.get('growth_this', '확인 불가')} / {parsed.get('growth_next', '확인 불가')}",
        f"- 소비자물가: {parsed.get('cpi_this', '확인 불가')} / {parsed.get('cpi_next', '확인 불가')}",
        f"- 근원물가: {parsed.get('core_this', '확인 불가')} / {parsed.get('core_next', '확인 불가')}",
        f"- 점도표: {dot.get('counts') if dot else '확인 불가'}",
        f"- 새 알림: {'예' if ALERT_PATH.exists() else '아니오'}",
        f"- 부분 오류: {len(errors)}건",
    ]
    STATUS_PATH.write_text("\n".join(status) + "\n", encoding="utf-8")
    if errors:
        ERROR_PATH.write_text("\n".join(errors) + "\n", encoding="utf-8")
    print(STATUS_PATH.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
