#!/usr/bin/env python3
"""Public-evidence Goldman Sachs Prime Korea allocation watch (no private API)."""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data/gs_prime_korea_allocation_state.json"
PENDING = ROOT / "out/gs_prime_korea_allocation_pending_state.json"
ALERT = ROOT / "out/gs_prime_korea_allocation_alert.html"
STATUS = ROOT / "out/gs_prime_korea_allocation_status.md"
KST = ZoneInfo("Asia/Seoul")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; khs-market-stress/1.0)",
           "Accept-Language": "en-US,en;q=0.8"}
ALLOWED = ("goldmansachs.com", "gs.com", "alpharis.cn", "finvaulta.com",
           "xxquant.com", "reuters.com", "bloomberg.com")
STATIC = (
    "https://alpharis.cn/events/2386",
    "https://finvaulta.com/research/goldman-sachs/em-weekly-fund-flows-monitor-october-selling-2026-10-30",
    "https://finvaulta.com/research/goldman-sachs/korea-weekly-kickstart-kospi-declined-further-by-2-percent-2026-10-25",
)
QUERIES = (
    '"Goldman Sachs" "Korea" "gross allocation" "net allocation"',
    '"GS Prime" "Korea" "gross" "net" allocations',
    '"Gross and Net Allocation: Korea"',
)
MAX_DOCS = 12
CHECK_HOURS = 3
DISCOVERY_REV = 2  # A source-discovery upgrade must be checked once despite the normal 3-hour gate.
FRESH_DAYS = 10
MONTHS = {s.lower(): i for i, s in enumerate(
    "January February March April May June July August September October November December".split(), 1)}


def domain(url):
    try:
        u = urllib.parse.urlsplit(url)
        h = (u.hostname or "").lower().removeprefix("www.")
        return h if u.scheme == "https" and any(h == d or h.endswith("." + d) for d in ALLOWED) else ""
    except Exception:
        return ""


def fetch(url, timeout=9):
    if not url.startswith("https://"):
        raise ValueError("https only")
    r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    if domain(url) and not domain(r.url):
        raise ValueError("source redirected outside trusted domain list")
    if len(r.content) > 1_300_000:
        raise ValueError("response too large")
    return r.text


def date_in(value):
    m = re.search(r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b", value)
    if m:
        try:
            return dt.date(*map(int, m.groups())).isoformat()
        except ValueError:
            pass
    m = re.search(r"\b(" + "|".join(MONTHS) + r")\s+(\d{1,2}),?\s+(20\d{2})\b", value, re.I)
    if m:
        try:
            return dt.date(int(m[3]), MONTHS[m[1].lower()], int(m[2])).isoformat()
        except ValueError:
            pass
    return None


def publication(soup, url):
    for tag in soup.select('meta[property="article:published_time"],meta[name="date"],meta[itemprop="datePublished"],time[datetime]'):
        found = date_in(str(tag.get("content") or tag.get("datetime") or ""))
        if found:
            return found
    return date_in(url)


def numeric(scope, label):
    if label == "gross":
        patterns = (
            r"\bgross\s+(?:allocation|exposure|weight)\b.{0,50}?\b(?:at|of|to|was|is|latest)\s*[:=]?\s*(\d{1,2}(?:\.\d+)?)\s*%",
            r"\bgross\s+(?:allocation|exposure)\s*[:=]\s*(\d{1,2}(?:\.\d+)?)\s*%",
        )
    else:
        patterns = (
            r"\bnet\s+(?:allocation|exposure|weight)\b.{0,50}?\b(?:at|of|to|was|is|latest)\s*[:=]?\s*(\d{1,2}(?:\.\d+)?)\s*%",
            r"\bnet\s+(?:allocation|exposure)\s*[:=]\s*(\d{1,2}(?:\.\d+)?)\s*%",
            r"\bkorea(?:'s)?\s+allocations?\b.{0,150}?\bto\s*(\d{1,2}(?:\.\d+)?)\s*%",
        )
    for pattern in patterns:
        m = re.search(pattern, scope, re.I)
        if m and 0 < float(m[1]) < 12:
            return float(m[1])
    return None


def percentile(scope, label):
    if label == "gross":
        pat = r"\bgross\s+allocation\b.{0,85}?\b(\d{1,3})(?:st|nd|rd|th)\s+percentile\s*(?:1[- ]?year|1Y)"
    else:
        pat = r"\bkorea(?:'s)?\s+(?:net\s+)?allocation[s]?\b.{0,185}?\b(\d{1,3})(?:st|nd|rd|th)\s+percentile\s*(?:1[- ]?year|1Y)"
    m = re.search(pat, scope, re.I)
    return int(m[1]) if m and int(m[1]) <= 100 else None


def parse_document(raw, url, now=None):
    if not domain(url):
        return None
    now = now or dt.datetime.now(KST)
    soup = BeautifulSoup(raw, "html.parser")
    published = publication(soup, url)
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    if not re.search(r"Goldman Sachs|GS Prime|Prime Services", text, re.I):
        return None
    pattern = r"\bKorea(?:'s)?\s+(?:allocations?|net allocation|gross allocation|net exposure|gross exposure)\b"
    for hit in re.finditer(pattern, text, re.I):
        section = text[hit.start():hit.start()+420]
        section = re.split(r"\bExhibit\s+\d+\s*[:.]|\b(?:Taiwan|China|India|Japan|Hong Kong)\b",
                           section, 1, re.I)[0]
        gross, net = numeric(section, "gross"), numeric(section, "net")
        if gross is None or net is None:
            continue
        prefix = text[max(0, hit.start()-2400):hit.start()]
        marks = list(re.finditer(r"\bAs of\s+(?:" + "|".join(MONTHS) + r")\s+\d{1,2},?\s+20\d{2}", prefix, re.I))
        asof = date_in(marks[-1][0]) if marks else published
        if not asof or dt.date.fromisoformat(asof) > now.date():
            continue
        return {
            "asof": asof, "gross": gross, "net": net,
            "gross_1y_percentile": percentile(section, "gross"),
            "net_1y_percentile": percentile(section, "net"),
            "source": url, "source_domain": domain(url),
            "date_basis": "관측일" if marks else "게시일 대용·관측일 미확인",
            "publication": published,
        }
    return None


def rss_links(query):
    q = urllib.parse.quote(query)
    feeds = (
        "https://www.bing.com/news/search?q=" + q + "&format=RSS",
        "https://news.google.com/rss/search?q=" + q + "&hl=en-US&gl=US&ceid=US:en",
    )
    urls, online = [], False
    for feed in feeds:
        try:
            xml = ET.fromstring(fetch(feed, 7))
            online = True
            for item in xml.findall(".//item")[:15]:
                link = (item.findtext("link") or "").strip()
                if domain(link):
                    urls.append(link)
                excerpt = html.unescape(item.findtext("description") or "")
                for url in re.findall(r'href=["\'](https://[^"\']+)', excerpt):
                    if domain(url):
                        urls.append(url)
        except (requests.RequestException, ValueError, ET.ParseError):
            pass
    return urls, online


def discover():
    # Discover current public reports before checking dated backstop URLs.
    urls, online = [], False
    for q in QUERIES:
        links, ready = rss_links(q)
        urls.extend(links)
        online |= ready
    for query in (
        'site:alpharis.cn/events "Korea allocations" "Goldman"',
        'site:finvaulta.com/research/goldman-sachs "Korea" "hedge fund" allocation',
        'site:xxquant.com "Korea" "gross allocation" "Goldman"',
    ):
        try:
            page = fetch("https://www.bing.com/search?q=" + urllib.parse.quote(query), 7)
            links = [urllib.parse.urljoin("https://www.bing.com", a.get("href", ""))
                     for a in BeautifulSoup(page, "html.parser").select("a[href]")]
            urls.extend(u for u in links if domain(u))
            online = True
        except (requests.RequestException, ValueError):
            pass
    for home in ("https://finvaulta.com", "https://alpharis.cn"):
        try:
            sitemap = ET.fromstring(fetch(home + "/sitemap.xml", 8))
            locations = [(el.text or "").strip() for el in sitemap.iter() if el.tag.rsplit("}", 1)[-1] == "loc"]
            indices = [u for u in locations if domain(u) and u.endswith(".xml")]
            for child in indices[:2]:
                try:
                    inner = ET.fromstring(fetch(child, 8))
                    locations.extend((el.text or "").strip() for el in inner.iter() if el.tag.rsplit("}", 1)[-1] == "loc")
                except (requests.RequestException, ValueError, ET.ParseError):
                    pass
            candidates = [
                u for u in locations
                if domain(u) and (
                    ("finvaulta.com/research/goldman-sachs/" in u and any(s in u for s in ("em-weekly", "korea-weekly", "hedge", "positioning")))
                    or ("alpharis.cn/events/" in u and re.search(r"/events/\d{3,}", u))
                )
            ]
            # Dated report URLs newest first; non-dated event IDs highest first.
            candidates.sort(key=lambda u: (
                date_in(u) or "",
                int((re.search(r"/events/(\d+)", u) or [None, 0])[1] or 0),
            ), reverse=True)
            urls.extend(candidates[:12])
            online = True
        except (requests.RequestException, ValueError, ET.ParseError):
            pass
    try:
        page = fetch("https://finvaulta.com/research/goldman-sachs", 7)
        for a in BeautifulSoup(page, "html.parser").select("a[href]"):
            url = urllib.parse.urljoin("https://finvaulta.com", a["href"])
            if domain(url) and any(x in url.lower() for x in ("em-weekly", "korea-weekly", "hedge", "positioning")):
                urls.append(url)
        online = True
    except (requests.RequestException, ValueError):
        pass
    # Historical reports only serve as dated reference points, never live readings.
    urls.extend(STATIC)
    seen, unique, counts = set(), [], {}
    for url in urls:
        url = url.split("#", 1)[0]
        d = domain(url)
        if not d or url in seen or counts.get(d, 0) >= 6:
            continue
        seen.add(url)
        counts[d] = counts.get(d, 0) + 1
        unique.append(url)
    return unique[:MAX_DOCS], online


def load_state():
    try:
        x = json.loads(STATE.read_text(encoding="utf-8"))
        return x if isinstance(x, dict) else {}
    except (OSError, TypeError, ValueError):
        return {}


def event_key(item):
    return f'gsprime-korea:{item["asof"]}:{item["gross"]:.2f}:{item["net"]:.2f}'


def select(readings, now, previous, seen):
    if not readings:
        return None, previous, "해당 지표의 새로운 공개 수치 없음"
    grouped = {}
    for r in readings:
        grouped.setdefault(r["asof"], []).append(r)
    day = max(grouped)
    values = {}
    for r in grouped[day]:
        values.setdefault((r["gross"], r["net"]), []).append(r)
    if len(values) > 1:
        return None, previous, f"같은 기준일 {day}의 수치 충돌 — 판정 보류"
    group = next(iter(values.values()))
    chosen = dict(group[0])
    chosen["sources"] = sorted({r["source"] for r in group})[:3]
    chosen["source_domains"] = sorted({r["source_domain"] for r in group})
    if previous and day < str(previous.get("asof", "")):
        return None, previous, "저장된 자료보다 과거 자료"
    if chosen["date_basis"] != "관측일":
        return None, previous, "수치 관측일이 확인되지 않아 판정 보류"
    if (now.date() - dt.date.fromisoformat(day)).days > FRESH_DAYS:
        baseline = chosen if not previous or day > previous.get("asof", "") else previous
        return None, baseline, "오래된 공개 보고서 — 최신 알림 생략"
    if event_key(chosen) in seen:
        return None, chosen, "동일 기준일·동일 수치 중복 생략"
    return chosen, chosen, "새 공개 수치 감지"


def format_alert(item, previous):
    proof = "서로 다른 공개 경로 2곳 이상" if len(item["source_domains"]) >= 2 else "단일 공개본·독립 확인 전"
    lines = [
        "<b>한국 헤지펀드 포지션 · GS 프라임서비스 인용 수치</b>",
        f"• 확인 수준: <b>{proof}</b> (기관용 원본 직접 조회 아님)",
        f'• 관측 기준일: <b>{item["asof"]}</b>',
        f'• 한국 총노출: <b>{item["gross"]:.2f}%</b> · 글로벌 총포지션 대비',
        f'• 한국 순노출: <b>{item["net"]:.2f}%</b> · 글로벌 순포지션 대비',
    ]
    for prop, name in (("gross_1y_percentile", "총노출"), ("net_1y_percentile", "순노출")):
        if item.get(prop) is not None:
            lines.append(f'• {name} 1년 백분위: {item[prop]}')
    if previous and previous.get("asof") != item["asof"]:
        try:
            dg = item["gross"] - float(previous["gross"])
            dn = item["net"] - float(previous["net"])
            lines.append(f'• 전 확인일({previous["asof"]}) 대비: 총노출 {dg:+.2f}%p / 순노출 {dn:+.2f}%p')
            if dg <= -0.3 or dn <= -0.3:
                lines.append("• 선행 위험: 한국 노출 축소 — 실제 순매도금액 확정 신호 아님")
            if dg >= 0.3 and dn >= 0.3:
                lines.append("• 선행 변화: 한국 노출 동반 확대 — 실제 매수 확정 신호 아님")
        except (KeyError, TypeError, ValueError):
            pass
    lines += ["• 총노출과 순노출은 서로 분모가 다르며 KRX 실제 외국인 매매와 별개",
              "• 공개 인용 자료이므로 골드만삭스 원본 확인 전에는 참고 지표로만 사용"]
    for idx, url in enumerate(item["sources"][:2], 1):
        lines.append(f'• 출처 {idx}: <a href="{html.escape(url, quote=True)}">공개 자료</a>')
    return "\n".join(lines).strip() + "\n"


def main():
    now = dt.datetime.now(KST)
    old = load_state()
    PENDING.parent.mkdir(parents=True, exist_ok=True)
    ALERT.unlink(missing_ok=True)
    try:
        since = dt.datetime.fromisoformat(str(old["last_checked_at"]))
        elapsed = (now - since).total_seconds()
    except (KeyError, ValueError, TypeError):
        elapsed = 999999
    if 0 <= elapsed < CHECK_HOURS * 3600 and old.get("discovery_revision") == DISCOVERY_REV and os.getenv("GS_PRIME_FORCE_REFRESH") != "1":
        STATUS.write_text("- GS 한국 헤지펀드 비중: 3시간 미경과 · 재조회 생략\n", encoding="utf-8")
        print("gs_prime_korea=not_due")
        return 0
    urls, discovery_ok = discover()
    rows, fetched = [], 0
    for url in urls:
        try:
            raw = fetch(url)
            fetched += 1
            row = parse_document(raw, url, now)
            if row:
                rows.append(row)
        except (requests.RequestException, ValueError):
            continue
    state = dict(old)
    state.update({"discovery_revision": DISCOVERY_REV, "last_checked_at": now.isoformat(timespec="seconds"),
                  "last_candidates": len(urls), "last_fetched": fetched,
                  "last_parsed": len(rows), "last_discovery_ok": discovery_ok})
    state["consecutive_source_failures"] = 0 if fetched else int(old.get("consecutive_source_failures") or 0) + 1
    seen = set(state.get("seen_keys") or [])
    previous = state.get("last_known") if isinstance(state.get("last_known"), dict) else None
    candidate, known, decision = select(rows, now, previous, seen)
    if known:
        state["last_known"] = known
    if candidate:
        ALERT.write_text(format_alert(candidate, previous), encoding="utf-8")
        seen.add(event_key(candidate))
    elif not fetched and state["consecutive_source_failures"] >= 3:
        fault_key = "gsprime-source-error:" + now.date().isoformat()
        if fault_key not in seen:
            ALERT.write_text(
                "<b>골드만삭스 한국 헤지펀드 노출 · 공개 원천 수집 장애</b>\n"
                "• 서로 다른 예약 실행에서 공개문서 조회가 3회 연속 실패했습니다.\n"
                "• 현재 총노출·순노출 최신값은 확인할 수 없어 숫자 경보를 보류합니다.\n"
                "• 기존 한국 시장 스트레스·환율 감시는 별도 작동하며, 이 메시지는 시장 위험 확정 신호가 아닙니다.\n",
                encoding="utf-8")
            seen.add(fault_key)
    state["seen_keys"] = sorted(seen)[-150:]
    state["last_decision"] = decision
    PENDING.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    line = f"- GS 한국 헤지펀드 비중: {decision} / 수집 {fetched}/{len(urls)} / 한국 총·순노출 쌍 {len(rows)}"
    if fetched == 0:
        line += " / 원천 접근 실패 — 최신 자료 확인 불가"
    STATUS.write_text(line + "\n", encoding="utf-8")
    print(f"gs_prime_korea=checked documents={fetched}/{len(urls)} pairs={len(rows)} alert={bool(candidate)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
