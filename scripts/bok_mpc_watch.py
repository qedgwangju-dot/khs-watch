#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import pathlib
import re
import urllib.parse
import urllib.parse as urlparse
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

BOK_LIST = "https://www.bok.or.kr/portal/bbs/P0000559/list.do?menuNo=200690"
GOOGLE_NEWS = "https://news.google.com/rss/search"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; khs-bok-mpc-watch/1.0)",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}


def get(url: str, timeout: int = 35) -> requests.Response:
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def find_latest_statement() -> dict[str, Any]:
    soup = BeautifulSoup(get(BOK_LIST).text, "html.parser")
    candidates = []
    for a in soup.find_all("a", href=True):
        label = normalize(a.get_text(" ", strip=True))
        if "통화정책방향" not in label:
            continue
        href = urllib.parse.urljoin(BOK_LIST, a["href"])
        if "view.do" not in href:
            continue
        candidates.append((label, href))
    if not candidates:
        raise RuntimeError("한국은행 통화정책방향 최신 게시물 링크를 찾지 못함")
    title, url = candidates[0]
    detail = BeautifulSoup(get(url).text, "html.parser")
    text = normalize(detail.get_text(" ", strip=True))
    return {
        "title": title,
        "url": url,
        "text": text,
        "hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def first_match(pattern: str, text: str, flags: int = 0) -> str | None:
    m = re.search(pattern, text, flags)
    return m.group(1) if m else None


def parse_statement(stmt: dict[str, Any]) -> dict[str, Any]:
    text = stmt["text"]
    result: dict[str, Any] = {
        "title": stmt["title"],
        "url": stmt["url"],
        "hash": stmt["hash"],
    }

    m = re.search(r"기준금리를 현재의\s*([0-9.]+)%?\s*수준에서\s*([0-9.]+)%?로", text)
    if m:
        result["rate_from"] = float(m.group(1))
        result["rate_to"] = float(m.group(2))

    m = re.search(r"금년 및 내년 성장률은[^.]{0,180}?([0-9.]+)%\s*및\s*([0-9.]+)%", text)
    if m:
        result["growth_this"] = float(m.group(1))
        result["growth_next"] = float(m.group(2))

    m = re.search(r"금년 및 내년 소비자물가 상승률은[^.]{0,180}?([0-9.]+)%\s*및\s*([0-9.]+)%", text)
    if m:
        result["cpi_this"] = float(m.group(1))
        result["cpi_next"] = float(m.group(2))

    m = re.search(r"근원물가 상승률은[^.]{0,180}?금년 및 내년 모두[^0-9]{0,30}?([0-9.]+)%", text)
    if m:
        result["core_this"] = float(m.group(1))
        result["core_next"] = float(m.group(1))
    else:
        m = re.search(r"근원물가 상승률은[^.]{0,180}?([0-9.]+)%\s*및\s*([0-9.]+)%", text)
        if m:
            result["core_this"] = float(m.group(1))
            result["core_next"] = float(m.group(2))

    m = re.search(r"금번 기준금리 (?:인상|동결) 결정에 대해 금융통화위원\s*([0-9]+)명은 찬성", text)
    if m:
        result["vote_for"] = int(m.group(1))
    result["minority_hold"] = bool(re.search(r"위원은 기준금리를\s*[0-9.]+%로 유지", text))

    keys = {
        "preemptive": "선제적 대응" in text,
        "hike_bias": "금리인상 기조를 이어나갈 필요" in text,
        "timing_speed": "추가 인상의 시기와 속도" in text or "추가 인상의 시기와 속도 등을 결정" in text,
        "housing": "수도권 주택가격" in text,
        "household_debt": "가계부채" in text or "가계대출" in text,
        "fx_volatility": "높은 환율 변동성" in text,
        "domestic_recovery": "내수 회복" in text or "소비 회복세" in text,
        "exports_investment": "수출 및 투자 호조" in text or "수출과 투자의 높은 증가세" in text,
    }
    result["flags"] = keys
    return result


def google_news(query: str, limit: int = 15) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"})
    root = ET.fromstring(get(f"{GOOGLE_NEWS}?{params}").content)
    out = []
    for item in root.findall(".//item")[:limit]:
        pub = (item.findtext("pubDate") or "").strip()
        try:
            pdt = parsedate_to_datetime(pub)
            if pdt.tzinfo is None:
                pdt = pdt.replace(tzinfo=dt.timezone.utc)
        except Exception:
            pdt = None
        out.append({
            "title": (item.findtext("title") or "").strip(),
            "link": (item.findtext("link") or "").strip(),
            "description": normalize(BeautifulSoup(item.findtext("description") or "", "html.parser").get_text(" ", strip=True)),
            "published": pub,
            "published_dt": pdt,
        })
    return out


def parse_dotplot(now: dt.datetime) -> dict[str, Any] | None:
    items = google_news('한국은행 금통위원 6개월 금리전망 3.00 3.25 3.50', 20)
    cutoff = now.astimezone(dt.timezone.utc) - dt.timedelta(days=10)
    for item in items:
        if not item.get("published_dt") or item["published_dt"] < cutoff:
            continue
        blob = item["title"] + " " + item["description"]
        counts: dict[str, int] = {}
        for level in ("2.75", "3.00", "3.25", "3.50", "3.75"):
            m = re.search(rf"{re.escape(level)}%?[^0-9]{{0,18}}([0-9]+)개", blob)
            if m:
                counts[level] = int(m.group(1))
        if len(counts) >= 2:
            total = sum(counts.values())
            return {
                "title": item["title"],
                "link": item["link"],
                "counts": counts,
                "total": total,
                "hash": hashlib.sha256(json.dumps(counts, sort_keys=True).encode()).hexdigest(),
            }
    return None


def fmt_pct(x: float | None) -> str:
    return "확인 불가" if x is None else f"{x:.2f}%".replace(".00", "")


def build_summary(parsed: dict[str, Any], dot: dict[str, Any] | None, previous: dict[str, Any] | None = None) -> str:
    lines = ["🏦 <b>한국은행 금통위 핵심 변화</b>", ""]
    if "rate_to" in parsed:
        lines.append(f"• 기준금리: <b>{fmt_pct(parsed.get('rate_from'))} → {fmt_pct(parsed.get('rate_to'))}</b>")
    if parsed.get("vote_for"):
        minority = " / 동결 소수의견 1명" if parsed.get("minority_hold") else ""
        lines.append(f"• 표결: <b>찬성 {parsed['vote_for']}명{minority}</b>")
    if "growth_this" in parsed:
        lines.append(f"• 성장률 전망: <b>올해 {parsed['growth_this']:.1f}% / 내년 {parsed['growth_next']:.1f}%</b>")
    if "cpi_this" in parsed:
        lines.append(f"• 소비자물가: <b>올해 {parsed['cpi_this']:.1f}% / 내년 {parsed['cpi_next']:.1f}%</b>")
    if "core_this" in parsed:
        lines.append(f"• 근원물가: <b>올해 {parsed['core_this']:.1f}% / 내년 {parsed['core_next']:.1f}%</b>")

    if dot:
        order = [k for k in ("2.75", "3.00", "3.25", "3.50", "3.75") if k in dot["counts"]]
        dist = " / ".join(f"{k}% {dot['counts'][k]}개" for k in order)
        current = parsed.get("rate_to")
        above = sum(v for k, v in dot["counts"].items() if current is not None and float(k) > current)
        lines += ["", f"• 6개월 조건부 금리전망: <b>{dist}</b>"]
        if current is not None and dot.get("total"):
            lines.append(f"• 현재 {current:.2f}%보다 높은 점: <b>{above}/{dot['total']}개</b> → 추가 인상 쪽 우세")

    flags = parsed.get("flags") or {}
    lines += ["", "<b>문구 판정</b>"]
    if flags.get("preemptive"):
        lines.append("• 신규 핵심: <b>‘선제적 대응으로 물가 오름세 확산 방지’</b> → 행동은 매파적")
    if flags.get("domestic_recovery"):
        lines.append("• 성장: 수출뿐 아니라 <b>내수·소비 회복</b>까지 확인")
    if flags.get("housing") and flags.get("household_debt"):
        lines.append("• 금융안정: <b>수도권 집값 + 가계부채</b>가 여전히 추가 인상 근거")
    if flags.get("timing_speed") and not flags.get("hike_bias"):
        lines.append("• 포워드 가이던스: ‘금리인상 기조 지속 필요’보다 <b>시기·속도 판단</b>으로 유연해짐")
    if not flags.get("fx_volatility"):
        lines.append("• 환율: 정책방향의 핵심 위험 문구에서는 비중이 낮아지고, 집값·가계부채가 전면에 남음")

    lines += ["", "<b>한 줄 판정</b>"]
    lines.append("• <b>행동은 매파적 / 향후 속도는 유연 / 최종금리 방향은 아직 상향 / 핵심 확인은 근원물가·소비·수도권 집값·가계대출</b>")
    lines += ["", f'• <a href="{html.escape(parsed["url"], quote=True)}">한국은행 원문</a>']
    if dot:
        lines.append(f'• <a href="{html.escape(dot["link"], quote=True)}">6개월 금리전망 근거</a>')
    return "\n".join(lines)


def main() -> int:
    for p in (ALERT_PATH, ERROR_PATH):
        p.unlink(missing_ok=True)
    now = dt.datetime.now(KST)
    old = load_state()
    errors = []

    try:
        stmt = find_latest_statement()
        parsed = parse_statement(stmt)
    except Exception as exc:
        ERROR_PATH.write_text(f"통화정책방향 조회 실패: {type(exc).__name__}: {exc}\n", encoding="utf-8")
        return 2

    try:
        dot = parse_dotplot(now)
    except Exception as exc:
        dot = None
        errors.append(f"점도표 조회 실패: {type(exc).__name__}: {exc}")

    statement_changed = old.get("statement_hash") != parsed.get("hash")
    dot_changed = bool(dot) and old.get("dotplot_hash") != dot.get("hash")
    bootstrap = not bool(old)

    if bootstrap or statement_changed or dot_changed:
        ALERT_PATH.write_text(build_summary(parsed, dot, old), encoding="utf-8")

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
        f"- 기준금리: {parsed.get('rate_to', '확인불가')}",
        f"- 성장률: {parsed.get('growth_this', '확인불가')} / {parsed.get('growth_next', '확인불가')}",
        f"- 근원물가: {parsed.get('core_this', '확인불가')} / {parsed.get('core_next', '확인불가')}",
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
