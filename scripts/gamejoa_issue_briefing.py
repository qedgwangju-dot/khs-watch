#!/usr/bin/env python3
"""Source-backed, twice-daily market issue digest; independent of live alerts."""
from __future__ import annotations

import base64
import concurrent.futures
import datetime as dt
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo


KST = ZoneInfo("Asia/Seoul")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
KRX_LIST_URL = "https://kind.krx.co.kr/corpgeneral/corpList.do?method=download"
NAVER_CHART_URL = "https://fchart.stock.naver.com/sise.nhn"
LEDGER_PATH = "data/gamejoa_issue_briefing_receipts.json"
USER_AGENT = "Mozilla/5.0 (compatible; GAMEJOA-issue-briefing/1.0)"
MAX_TOPICS = 4
MAX_STOCKS_PER_TOPIC = 3
TOPIC_AI_CHEATING = re.compile(
    r"(?:(?:AI|인공지능|스마트\s*안경).{0,35}(?:커닝|컨닝|부정\s*행위|부정\s*시험)|"
    r"(?:커닝|컨닝|부정\s*행위|부정\s*시험).{0,35}(?:AI|인공지능|스마트\s*안경))",
    re.I,
)
MARKET_EVIDENCE = re.compile(r"상한가|하한가|주가|증시|증권시장|관련주|테마주|보안주|카메라주|종목|주식|급등|급락|상승|하락|거래대금|株|솟구쳐")
SOCIAL_LINK_EVIDENCE = re.compile(r"관련주|테마주|보안|카메라|전파|탐지|촬영|시험|부정|커닝|컨닝")
TRACKING_KEYS = {"utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "ref", "source", "oc", "input"}
HEADLINE_ACTIONS = [
    ("acquisition", re.compile(r"인수|인수합병|매입"), re.compile(r"인수|인수합병|매입")),
    ("disposal", re.compile(r"매각|매도"), re.compile(r"매각|매도")),
    ("contract", re.compile(r"수주|발주|계약"), re.compile(r"수주|발주|계약")),
    ("shareholder", re.compile(r"자사주|자기주식|배당"), re.compile(r"자사주|자기주식|배당")),
    ("financing", re.compile(r"출자|자금\s*조달|증자"), re.compile(r"출자|자금\s*조달|증자")),
    ("layoffs", re.compile(r"감원|해고|정리해고"), re.compile(r"감원|해고|정리해고")),
    ("revenue", re.compile(r"매출(?:액)?"), re.compile(r"매출(?:액)?")),
    ("operating_profit", re.compile(r"영업(?:이익|손실|적자)"), re.compile(r"영업(?:이익|손실|적자)")),
    ("net_profit", re.compile(r"순(?:이익|손실|적자)"), re.compile(r"순(?:이익|손실|적자)")),
]
MONEY_IN_HEADLINE = re.compile(r"\d[\d,.]*(?:\s*조\s*\d[\d,.]*\s*억|\s*억\s*\d[\d,.]*\s*만|\s*(?:조|억|만))\s*(?:원|달러|유로|위안)")


def briefing_window(slot: str, now: dt.datetime) -> tuple[dt.datetime, dt.datetime]:
    if now.tzinfo is None:
        raise ValueError("timezone-aware now is required")
    now = now.astimezone(KST)
    day = now.date()
    if slot == "preopen":
        end = dt.datetime.combine(day, dt.time(6, 30), KST)
        return end - dt.timedelta(hours=15), end
    if slot == "close":
        return (dt.datetime.combine(day, dt.time(6, 30), KST),
                dt.datetime.combine(day, dt.time(15, 30), KST))
    raise ValueError("slot must be preopen or close")


def parse_time(value: object) -> dt.datetime | None:
    if isinstance(value, dt.datetime):
        return value.astimezone(KST) if value.tzinfo else None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed.astimezone(KST) if parsed.tzinfo else None


def in_window(value: object, start: dt.datetime, end: dt.datetime) -> bool:
    when = parse_time(value)
    return bool(when and start <= when < end)


def canonical_url(value: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return ""
        query = [(k, v) for k, v in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
                 if k.lower() not in TRACKING_KEYS]
        return urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(),
                                       parsed.path.rstrip("/") or "/", urllib.parse.urlencode(sorted(query)), ""))
    except ValueError:
        return ""


def unique_sample(rows: list[dict], start: dt.datetime, end: dt.datetime) -> list[dict]:
    unique: dict[str, dict] = {}
    for row in rows:
        url = canonical_url(str(row.get("link") or ""))
        if not url or not in_window(row.get("published"), start, end):
            continue
        previous = unique.get(url)
        if previous is None or (row.get("body_verified") and not previous.get("body_verified")):
            unique[url] = row
    return list(unique.values())


class KRXTable(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self.row: list[str] | None = None
        self.cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self.row = []
        elif tag in {"td", "th"} and self.row is not None:
            self.cell = []

    def handle_data(self, data: str) -> None:
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self.cell is not None and self.row is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def parse_krx_list(data: bytes) -> dict[str, str]:
    parser = KRXTable()
    parser.feed(data.decode("euc-kr", errors="strict"))
    header = next((row for row in parser.rows if "회사명" in row and "종목코드" in row), None)
    if not header:
        raise ValueError("KRX listing headers missing")
    name_idx, code_idx = header.index("회사명"), header.index("종목코드")
    market_idx = header.index("시장구분") if "시장구분" in header else None
    result: dict[str, str] = {}
    ambiguous: set[str] = set()
    for row in parser.rows:
        if len(row) <= max(name_idx, code_idx) or (market_idx is not None and len(row) <= market_idx):
            continue
        name, code = row[name_idx].strip(), row[code_idx].strip()
        if market_idx is not None and row[market_idx] not in {"유가", "유가증권시장", "코스피", "코스닥"}:
            continue
        if len(name) < 2 or not re.fullmatch(r"\d{6}", code):
            continue
        if name in result and result[name] != code:
            ambiguous.add(name)
        result[name] = code
    for name in ambiguous:
        result.pop(name, None)
    if len(result) < 100:
        raise ValueError("KRX listing unexpectedly incomplete")
    return result


def get_bytes(url: str, timeout: int = 15) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def parse_daily_quote(data: bytes, code: str, expected_name: str, now: dt.datetime) -> dict:
    if re.search(br'encoding=["\'](?:euc-kr|ks_c_5601-1987)["\']', data[:150], re.I):
        xml = data.decode("euc-kr", errors="strict")
        root = ET.fromstring(re.sub(r"^\s*<\?xml[^?]*\?>", "", xml, count=1))
    else:
        root = ET.fromstring(data)
    chart = root.find(".//chartdata")
    if chart is None or chart.get("symbol") != code:
        raise ValueError("chart symbol mismatch")
    if re.sub(r"\s+", "", chart.get("name") or "") != re.sub(r"\s+", "", expected_name):
        raise ValueError("chart name mismatch")
    now = now.astimezone(KST)
    cutoff = now.date() if now.time() >= dt.time(15, 30) else now.date() - dt.timedelta(days=1)
    bars: dict[dt.date, tuple[Decimal, int]] = {}
    for item in chart.findall("item"):
        parts = (item.get("data") or "").split("|")
        if len(parts) < 6:
            continue
        try:
            day = dt.datetime.strptime(parts[0], "%Y%m%d").date()
            close = Decimal(parts[4])
            volume = int(parts[5])
        except (ValueError, InvalidOperation):
            continue
        if close <= 0 or day > cutoff:
            continue
        if day in bars and bars[day] != (close, volume):
            raise ValueError("conflicting daily bars")
        bars[day] = (close, volume)
    days = sorted(bars)
    if len(days) < 2 or (now.date() - days[-1]).days > 7:
        raise ValueError("completed daily close unavailable or stale")
    latest, latest_volume = bars[days[-1]]
    previous, previous_volume = bars[days[-2]]
    if latest_volume <= 0 or previous_volume <= 0:
        raise ValueError("daily close has no reported trading volume")
    change = ((latest / previous - 1) * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {"name": expected_name, "code": code, "date": days[-1].isoformat(),
            "previous_date": days[-2].isoformat(), "close": str(latest),
            "previous_close": str(previous), "change_pct": str(change),
            "source": "네이버 금융 일봉", "source_url": chart_url(code),
            "queried_at_kst": now.isoformat(timespec="seconds")}


def chart_url(code: str) -> str:
    return NAVER_CHART_URL + "?" + urllib.parse.urlencode({
        "symbol": code, "timeframe": "day", "count": "12", "requestType": "0"})


def company_mentions(text: str, listed: dict[str, str]) -> list[tuple[str, str]]:
    # Longest match first; a short company must not match inside another name.
    matches: list[tuple[int, int, str, str]] = []
    for name, code in listed.items():
        for match in re.finditer(re.escape(name), text, re.I):
            start, end = match.span()
            if start and (text[start - 1].isalnum() or "가" <= text[start - 1] <= "힣"):
                continue
            tail = text[end:]
            if tail and (tail[0].isalnum() or "가" <= tail[0] <= "힣"):
                if not re.match(r"(?:은|는|이|가|을|를|과|와|의|도|에|에서|로|으로)(?:[^가-힣A-Za-z0-9]|$)", tail):
                    continue
            if len(re.sub(r"\s+", "", name)) <= 2:
                sentence = re.split(r"(?<!\d)[.!?。](?!\d)|\n", text[max(0, start - 120):min(len(text), end + 120)])
                if not any(name in part and (MARKET_EVIDENCE.search(part) or code in part) for part in sentence):
                    continue
            matches.append((start, end, name, code))
    matches.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    result: list[tuple[str, str]] = []
    occupied = -1
    for start, end, name, code in matches:
        if start < occupied:
            continue
        occupied = end
        if (name, code) not in result:
            result.append((name, code))
    return result


def ai_cheating_market_observation(row: dict, listed: dict[str, str]) -> dict:
    if not row.get("body_verified") or not TOPIC_AI_CHEATING.search(str(row.get("source_title") or row.get("title") or "")):
        return {}
    body = re.sub(r"\s+", " ", str(row.get("source_body") or ""))
    sentences = re.split(r"(?<=[.!?。])\s+", body)
    for index, sentence in enumerate(sentences):
        if not TOPIC_AI_CHEATING.search(sentence) or len(sentence) > 230 or not re.search(r"[.!?。]$", sentence):
            continue
        neighbors = sorted(range(max(0, index - 2), min(len(sentences), index + 3)), key=lambda i: abs(i - index))
        for nearby in neighbors:
            market_sentence = sentences[nearby]
            companies = company_mentions(market_sentence, listed) if (MARKET_EVIDENCE.search(market_sentence)
                                                                      and SOCIAL_LINK_EVIDENCE.search(market_sentence)) else []
            if companies:
                return {"core": sentence, "companies": companies, "company_evidence": market_sentence}
    return {}


def social_observation_verified(alert: dict, observation: dict, runner) -> bool:
    title = str(alert.get("source_title") or "")
    body = re.sub(r"\s+", " ", str(alert.get("source_body") or "")).strip()
    core = re.sub(r"\s+", " ", str(observation.get("core") or "")).strip()
    evidence = re.sub(r"\s+", " ", str(observation.get("company_evidence") or "")).strip()
    if not (alert.get("body_verified") and runner.korean_business_source_allowed(alert)
            and TOPIC_AI_CHEATING.search(title) and TOPIC_AI_CHEATING.search(core)
            and core in body and evidence in body and MARKET_EVIDENCE.search(evidence) and SOCIAL_LINK_EVIDENCE.search(evidence)
            and observation.get("companies") and runner.core_sentence_is_complete(core)
            and not runner.core_has_ui_garbage(core) and not runner.core_has_ui_garbage(evidence)
            and runner.korean_title_core_aligned(title, core)):
        return False
    # The ordinary gate expects the market movement in the same sentence as
    # the event. Here it is independently bound to a nearby source sentence.
    allowable = {"article_without_headline_market_change_evidence", "core_without_market_change_evidence"}
    return not (set(runner.source_core_fact_errors(alert)) - allowable)


def event_matches(a: str, b: str, materiality) -> bool:
    if re.sub(r"\s+", " ", a).strip().casefold() == re.sub(r"\s+", " ", b).strip().casefold():
        return bool(a.strip())
    if TOPIC_AI_CHEATING.search(a) and TOPIC_AI_CHEATING.search(b):
        return True
    return bool(materiality.same_headline_event(a, b))


def topic_statistics(title: str, sample: list[dict], start: dt.datetime, end: dt.datetime, materiality) -> dict:
    matching = [row for row in sample if event_matches(title, str(row.get("source_title") or row.get("title") or ""), materiality)]
    midpoint = start + (end - start) / 2
    early = sum(in_window(row.get("published"), start, midpoint) for row in matching)
    late = sum(in_window(row.get("published"), midpoint, end) for row in matching)
    publishers = {str(row.get("publisher") or "").strip() for row in matching} - {""}
    return {"articles": len(matching), "publishers": len(publishers), "early": early, "late": late}


def group_sort_key(group: dict) -> tuple[int, int, int, int]:
    count = group["stats"]["articles"]
    return (group["rank"] * 2 + min(4, max(0, count - 1)), group["priority"], count, group["stats"]["late"])


def headline_action(title: str):
    hits = [(match.start(), kind, core_pattern) for kind, title_pattern, core_pattern in HEADLINE_ACTIONS
            if (match := title_pattern.search(title))]
    return min(hits, key=lambda item: item[0]) if hits else None


def action_core_aligned(title: str, core: str, runner) -> bool:
    action = headline_action(title)
    if not action:
        return True
    if not action[2].search(core):
        return False
    if action[1] in {"revenue", "operating_profit", "net_profit"}:
        quarters = set(re.findall(r"([1-4])\s*분기", title))
        if quarters and not quarters.issubset(set(re.findall(r"([1-4])\s*분기", core))):
            return False
        if not re.search(r"전망|예상|추정|컨센서스", title) and re.search(r"전망|예상|추정|컨센서스", core):
            return False
    # On transaction headlines, do not replace the deal amount with a
    # different revenue, loan, valuation, or prior-period number.
    if action[1] in {"acquisition", "disposal", "contract", "financing"}:
        amounts = MONEY_IN_HEADLINE.findall(title)
        if amounts:
            normalize = lambda value: re.sub(r"[\s,]", "", value)
            if not any(normalize(value) in normalize(core) for value in amounts):
                return False
    if (re.search(r"(?:인수|계약|수주|매각).{0,15}(?:완료|확정|체결)", title)
            and not re.search(r"완료|확정|체결", core)):
        return False
    return bool(runner.korean_title_core_aligned(title, core))


def low_materiality_foreign_earnings(alert: dict, listed: dict[str, str], runner, telegram) -> bool:
    title = str(alert.get("source_title") or alert.get("news") or "")
    if not re.search(r"[1-4]\s*분기|실적", title) or not re.search(r"매출|영업이익|순손실", title):
        return False
    if company_mentions(title, listed) or telegram.alert_issuer_keys(alert):
        return False
    amounts = runner.extract_foreign_amounts(title)
    return bool(amounts and all(item["code"] == "USD" and item["amount"] < 100_000_000 for item in amounts))


def headline_backed_core(alert: dict, runner) -> str:
    title = str(alert.get("source_title") or alert.get("news") or "").strip()
    core = str(alert.get("telegram_core_fact") or alert.get("policy_plain_summary") or "").strip()
    body = str(alert.get("source_body") or "")
    normalized_body = re.sub(r"\s+", " ", html.unescape(body)).strip()
    normalized_core = re.sub(r"\s+", " ", html.unescape(core)).strip()
    if normalized_core and normalized_core in normalized_body and action_core_aligned(title, core, runner):
        return core
    for part in re.split(r"(?<=[.!?。])\s+|\n+", body):
        candidate = runner.clean_article_summary_text(part).strip()
        if (candidate and len(candidate) <= 240 and runner.core_sentence_is_complete(candidate)
                and not runner.core_has_ui_garbage(candidate)
                and runner.korean_title_core_aligned(title, candidate)
                and re.sub(r"\s+", " ", html.unescape(candidate)).strip() in normalized_body
                and action_core_aligned(title, candidate, runner)):
            return candidate
    return ""


def group_alerts(alerts: list[dict], sample: list[dict], start: dt.datetime, end: dt.datetime, materiality) -> list[dict]:
    groups: list[dict] = []
    for alert in alerts:
        if not alert.get("body_verified"):
            continue
        source_title = str(alert.get("source_title") or alert.get("news") or "").strip()
        title = source_title if re.search(r"[가-힣]", source_title) else str(alert.get("news") or "").strip()
        core = str(alert.get("telegram_core_fact") or alert.get("policy_plain_summary") or "").strip()
        url = canonical_url(str(alert.get("link") or ""))
        if not title or not core or not url or not re.search(r"[가-힣]", title) or not re.search(r"[가-힣]", core):
            continue
        existing = next((g for g in groups if event_matches(source_title, g["source_title"], materiality)), None)
        if existing:
            continue
        audit = alert.get("market_materiality") or {}
        groups.append({"title": title, "source_title": source_title, "core": core, "url": url, "alert": alert,
                       "stats": topic_statistics(source_title, sample, start, end, materiality),
                       "rank": int(audit.get("news_value_rank") or 0),
                       "priority": int(audit.get("priority") or 0)})
    groups.sort(key=group_sort_key, reverse=True)
    return groups[:MAX_TOPICS]


def digest_groups(fresh: list[dict], previously_sent: list[dict], sample: list[dict],
                  start: dt.datetime, end: dt.datetime, materiality) -> list[dict]:
    groups = group_alerts(fresh, sample, start, end, materiality)
    for group in group_alerts(previously_sent, sample, start, end, materiality):
        if group["stats"]["articles"] < 2:
            continue
        if any(event_matches(group["source_title"], item["source_title"], materiality) for item in groups):
            continue
        group["previously_sent"] = True
        groups.append(group)
    groups.sort(key=group_sort_key, reverse=True)
    return groups[:MAX_TOPICS]


def add_social_evidence(groups: list[dict], sample: list[dict], listed: dict[str, str],
                        start: dt.datetime, end: dt.datetime, now: dt.datetime, runner, telegram) -> list[dict]:
    for row in sample:
        observation = ai_cheating_market_observation(row, listed)
        if not observation:
            continue
        core = observation["core"]
        title = str(row.get("source_title") or row.get("title") or "")
        alert = {"source_title": title, "news": title, "source_body": row.get("source_body"),
                 "source_abstract": row.get("source_body"), "publisher": row.get("publisher"),
                 "body_verified": True, "korean_business_news": True,
                 "telegram_core_fact": core, "policy_plain_summary": core,
                 "link": row.get("link"), "published": row.get("published")}
        if not social_observation_verified(alert, observation, runner):
            continue
        link = canonical_url(str(row.get("link") or ""))
        existing = next((group for group in groups if TOPIC_AI_CHEATING.search(group["title"])), None)
        if existing:
            existing["explicit_companies"] = observation["companies"]
            existing["company_evidence"] = observation["company_evidence"]
            existing["company_source_url"] = link
            break
        fresh, seen = telegram.filter_previously_seen_alerts([alert], now, lane="all")
        stats = topic_statistics(title, sample, start, end, runner.market_materiality)
        if not fresh and not (seen and stats["articles"] >= 2):
            continue
        groups.append({"title": title, "source_title": title, "core": core, "url": link,
                       "alert": alert, "stats": stats, "explicit_companies": observation["companies"],
                       "company_evidence": observation["company_evidence"], "company_source_url": link,
                       "previously_sent": bool(seen), "rank": 3, "priority": 2})
        break
    groups.sort(key=group_sort_key, reverse=True)
    return groups[:MAX_TOPICS]


def refresh_sent_history(telegram) -> None:
    """Read and verify only the latest main receipt blob, not repository history."""
    if os.getenv("BRIEFING_REFRESH_SEEN", "").lower() not in {"1", "true", "yes"}:
        return
    repo = os.getenv("GITHUB_REPOSITORY", "")
    token = os.getenv("GITHUB_TOKEN", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) or not token:
        raise RuntimeError("Cannot authenticate live alert history refresh")
    root = f"https://api.github.com/repos/{repo}"
    code, head = api_json("GET", root + "/commits/main", token)
    commit = str(head.get("sha") or "")
    if code != 200 or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise RuntimeError("Cannot resolve current main for live alert history")
    url = root + "/contents/data/gamejoa_preopen_news_radar_seen.json?ref=" + commit
    code, metadata = api_json("GET", url, token)
    blob = str(metadata.get("sha") or "")
    size = metadata.get("size")
    if code != 200 or not re.fullmatch(r"[0-9a-f]{40}", blob) or not isinstance(size, int) or not 0 < size <= 100_000_000:
        raise RuntimeError("Cannot verify live alert history metadata")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                     "Authorization": "Bearer " + token,
                                     "Accept": "application/vnd.github.raw+json"})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = response.read(size + 1)
    except Exception as exc:
        raise RuntimeError("Cannot download live alert history: " + type(exc).__name__) from None
    digest = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    if len(data) != size or digest != blob:
        raise RuntimeError("Live alert history blob failed size or SHA verification")
    try:
        if not isinstance(json.loads(data), dict):
            raise ValueError("not an object")
    except Exception:
        raise RuntimeError("Live alert history is not valid JSON") from None
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "gamejoa_issue_briefing_seen_snapshot.json"
    path.write_bytes(data)
    telegram.SEEN_PATH = path
    print(f"Briefing: refreshed sent history commit={commit[:12]} blob={blob[:12]}", flush=True)


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def normalize_currency_labels(value: str) -> str:
    text = str(value or "")
    for compact, spaced in (("스웨덴크로나", "스웨덴 크로나"), ("노르웨이크로네", "노르웨이 크로네"),
                            ("덴마크크로네", "덴마크 크로네")):
        text = text.replace(compact, spaced)
    return text


def converted_field(value: str, conversion: dict, runner) -> str | None:
    text = normalize_currency_labels(value)
    for item in conversion.get("amounts") or []:
        raw = str(item.get("original") or "").strip()
        if not raw:
            continue
        krw = str(item.get("krw_text") or "원화 환산 확인 불가")
        replacement = f"{raw}(약 {krw})" if item.get("krw_value") is not None else f"{raw}(원화 환산 확인 불가)"
        pattern = r"(?<![\d,.])" + re.escape(raw) + r"(?!\s*\((?:약\s*[^)]*원|원화 환산 확인 불가)\))"
        text = re.sub(pattern, lambda _: replacement, text)
    for amount in runner.extract_foreign_amounts(text):
        following = text[amount["end"]:]
        if not re.match(r"\s*\((?:약\s*[^()]*원|원화 환산 확인 불가)\)", following):
            return None
    depth = 0
    for char in text:
        if char == "(":
            depth += 1
            if depth > 1:
                return None
        elif char == ")":
            depth = max(0, depth - 1)
    return text


def normalized_fx_alert(alert: dict) -> dict:
    result = dict(alert)
    for key in ("policy_plain_summary", "telegram_core_fact", "source_title", "original_news", "news"):
        if key in result:
            result[key] = normalize_currency_labels(str(result.get(key) or ""))
    return result


def render_report(slot: str, now: dt.datetime, start: dt.datetime, end: dt.datetime,
                  sample_count: int, groups: list[dict], quotes: dict[str, dict],
                  coverage_incomplete: bool, listing_error: str, fx_snapshot: dict, runner) -> str:
    label = "장전" if slot == "preopen" else "장 마감"
    lines = [f"📰 {label} 핵심 이슈 브리핑 · {now:%Y-%m-%d %H:%M} KST",
             f"기사 시각: {start:%m/%d %H:%M}~{end:%m/%d %H:%M} KST",
             f"수집 표본: 기사 {sample_count}건 · 전수 아님", ""]
    if not groups:
        lines.append("원문과 시장 관련성을 함께 확인한 새 이슈가 없습니다.")
    for index, group in enumerate(groups, 1):
        stats = group["stats"]
        core = group.get("converted_core", group["core"])
        title = group.get("converted_title", group["title"])
        recap_label = " (기존 속보 이슈 재정리)" if group.get("previously_sent") else ""
        lines.extend([f"{index}. {escape(title)}{recap_label}", f"- 핵심: {escape(core)}",
                      f"- 기사 표본: {stats['articles']}건 · {stats['publishers']}개 매체 (전반 {stats['early']}건 → 후반 {stats['late']}건)"])
        names = group.get("companies") or []
        quote_parts = []
        for name, code in names[:MAX_STOCKS_PER_TOPIC]:
            q = quotes.get(code)
            if q:
                pct = Decimal(q["change_pct"])
                quote_parts.append(f"{name} {int(Decimal(q['close'])):,}원({pct:+.2f}%)")
            else:
                quote_parts.append(f"{name} 종가 확인 불가")
        if quote_parts:
            dates = {quotes[code]["date"] for _, code in names[:MAX_STOCKS_PER_TOPIC] if code in quotes}
            date_label = next(iter(dates)) if len(dates) == 1 else "각 종목 조회 기준일"
            source_link = group.get("company_source_url") or ""
            extra_link = f' · <a href="{escape(source_link)}">종목 근거</a>' if source_link and source_link != group["url"] else ""
            lines.append(f"- 기사 직접 언급: {escape(' · '.join(quote_parts))} | {date_label} 종가{extra_link}")
        lines.append(f'- 출처: <a href="{escape(group["url"])}">원문</a>')
        lines.append("")
    if coverage_incomplete:
        lines.append("※ 일부 출처 또는 기사 본문 확인 불가. 기사 수는 수집 표본 기준입니다.")
    if listing_error:
        lines.append("※ 거래소 종목목록 확인 불가: 관련주 확인을 생략했습니다.")
    if any(quotes.values()):
        lines.append("※ 주가: 네이버 금융 일봉의 확인된 정규장 종가와 직전 거래일 종가로 계산. 시간외 미포함.")
    rates = fx_snapshot.get("rates") or {}
    if rates:
        provenance = []
        for code, rate in sorted(rates.items()):
            if rate.get("value") is None:
                provenance.append(f"{code}/KRW 확인 불가")
            else:
                provenance.append(f"{code}/KRW {rate['value']}원 ({rate.get('source') or '출처 확인 불가'}, {rate.get('reference_time_kst') or '기준일 확인 불가'})")
        lines.append("※ 환산: " + escape(" · ".join(provenance)))
    return "\n".join(lines).strip() + "\n"


def api_json(method: str, url: str, token: str, payload: dict | None = None) -> tuple[int, dict]:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json",
               "Authorization": "Bearer " + token, "Content-Type": "application/json"}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in {404, 409, 422}:
            return exc.code, {}
        raise RuntimeError(f"GitHub state HTTP {exc.code}") from None


class GitHubLedger:
    def __init__(self, repo: str, token: str, api=api_json) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) or not token:
            raise ValueError("GitHub ledger configuration missing")
        self.url = f"https://api.github.com/repos/{repo}/contents/{LEDGER_PATH}"
        self.token, self.api = token, api

    def read(self) -> tuple[dict, str]:
        code, doc = self.api("GET", self.url + "?ref=main", self.token)
        if code == 404:
            return {"version": 1, "slots": {}}, ""
        if code != 200:
            raise RuntimeError(f"GitHub ledger read HTTP {code}")
        try:
            payload = json.loads(base64.b64decode(doc["content"]).decode("utf-8"))
            if not isinstance(payload.get("slots"), dict):
                raise ValueError("missing slots")
            return payload, str(doc.get("sha") or "")
        except Exception:
            raise RuntimeError("Invalid briefing delivery ledger") from None

    def has_slot(self, key: str) -> bool:
        payload, _ = self.read()
        return key in payload["slots"]

    def update(self, key: str, run_id: str, status: str, message_id: int | None = None) -> bool:
        for _ in range(4):
            payload, sha = self.read()
            slots = payload.setdefault("slots", {})
            existing = slots.get(key)
            if status == "reserved" and existing:
                return False
            if status != "reserved" and (not existing or existing.get("run_id") != run_id):
                raise RuntimeError("Delivery reservation ownership mismatch")
            slots[key] = {"run_id": run_id, "status": status,
                          "updated_at_kst": dt.datetime.now(KST).isoformat(timespec="seconds")}
            if message_id is not None:
                slots[key]["message_id"] = message_id
            body = {"message": f"Record GAMEJOA issue briefing {key} {status}", "branch": "main",
                    "content": base64.b64encode((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode()).decode()}
            if sha:
                body["sha"] = sha
            code, _ = self.api("PUT", self.url, self.token, body)
            if code in {200, 201}:
                return True
            if code not in {409, 422}:
                raise RuntimeError(f"GitHub ledger write HTTP {code}")
            time.sleep(0.5)
        raise RuntimeError("GitHub ledger conflict; sending blocked")


def send_telegram(text: str, token: str, chat_id: str, runner) -> int:
    if not token or not chat_id:
        raise RuntimeError("Telegram credentials missing")
    message, entities = runner.telegram_text_and_entities(text)
    if runner.telegram_utf16_length(message) > 4096:
        raise RuntimeError("Telegram message exceeds limit; sending blocked")
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": message,
                                   "disable_web_page_preview": "true",
                                   "entities": json.dumps(entities, ensure_ascii=False)}).encode()
    request = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            result = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        # A timeout can occur after Telegram accepted the message; do not retry.
        raise RuntimeError("Telegram result uncertain: " + type(exc).__name__) from None
    message_id = (result.get("result") or {}).get("message_id")
    if not result.get("ok") or not isinstance(message_id, int):
        raise RuntimeError("Telegram acknowledgement missing")
    return message_id


def main() -> int:
    # Importing this entrypoint installs the existing source and quality overlays.
    import gamejoa_preopen_news_radar_fda_quality_runner as pipeline

    runner, base, telegram = pipeline.runner, pipeline.base, pipeline.telegram
    slot = os.getenv("BRIEFING_SLOT", "").strip()
    now = base.kst_now()
    start, end = briefing_window(slot, now)
    scheduled = dt.datetime.combine(now.date(), dt.time(6, 30) if slot == "preopen" else dt.time(16, 30), KST)
    dry = os.getenv("TELEGRAM_DRY_RUN", "true").lower() in {"1", "true", "yes"}
    if not dry and os.getenv("GITHUB_REF") != "refs/heads/main":
        raise RuntimeError("Live briefing delivery requires main")
    if not dry and not dt.timedelta() <= now - scheduled <= dt.timedelta(hours=2):
        raise RuntimeError("Outside briefing delivery window")
    if dry and now < end:
        end = now
    ledger = None
    key, run_id = f"{now.date().isoformat()}:{slot}", os.getenv("GITHUB_RUN_ID", "")
    if not dry:
        if not os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or not os.getenv("TELEGRAM_CHAT_ID", "").strip() or not run_id:
            raise RuntimeError("Telegram credentials or GitHub run identifier missing")
        ledger = GitHubLedger(os.getenv("GITHUB_REPOSITORY", ""), os.getenv("GITHUB_TOKEN", ""))
        if ledger.has_slot(key):
            OUT.mkdir(parents=True, exist_ok=True)
            (OUT / "gamejoa_issue_briefing.json").write_text(json.dumps({
                "slot": slot, "delivery_status": "skipped_existing_reservation", "slot_key": key,
            }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print("Briefing: existing reservation; duplicate send skipped", flush=True)
            return 0
    print(f"Briefing: slot={slot} window={start.isoformat()}..{end.isoformat()} dry_run={dry}", flush=True)
    additions = [
        ("국내 신뢰매체 AI 시험 부정행위", runner.korean_news_search_url('(AI OR 인공지능 OR 스마트안경) (커닝 OR 컨닝 OR 부정행위) (수능 OR 정부 OR 증시 OR 관련주)'), "trusted"),
        ("국내 신뢰매체 주식 이슈", runner.korean_news_search_url('(증시 OR 코스피 OR 코스닥 OR 관련주) (상한가 OR 급등 OR 수주 OR 계약 OR 규제 OR 실적)'), "trusted"),
    ]
    for item in additions:
        if item not in base.SOURCES:
            base.SOURCES.append(item)
    os.environ["RADAR_RUN_MODE"] = "briefing"
    original_hydrate = runner.hydrate_korean_business_details
    def hydrate_window(rows, query_time):
        candidates = [row for row in rows if in_window(row.get("published"), start, end)]
        # Reserve retrieval priority only for headlines that explicitly connect
        # the social event with market action; this is not publication approval.
        for row in candidates:
            title = str(row.get("title") or "")
            if TOPIC_AI_CHEATING.search(title) and MARKET_EVIDENCE.search(title):
                row["_pinned_direct_article"] = True
        return original_hydrate(candidates, query_time)
    runner.hydrate_korean_business_details = hydrate_window
    try:
        rows, notes = pipeline.contract.strict.collect_items(now)
    finally:
        runner.hydrate_korean_business_details = original_hydrate
    sample = unique_sample(rows, start, end)
    print(f"Briefing: collected={len(rows)} window_unique={len(sample)}", flush=True)
    listing_error = ""
    try:
        listed = parse_krx_list(get_bytes(KRX_LIST_URL, 25))
    except Exception as exc:
        listed, listing_error = {}, type(exc).__name__
    os.environ["RADAR_RUN_MODE"] = "live"
    classified = []
    for row in sample:
        if not row.get("body_verified"):
            continue
        alert = pipeline.contract.strict.classify(row, now)
        if alert:
            classified.append(telegram.normalize_alert(alert))
    quality = runner.quality_display_alerts(classified, 100)
    aligned = []
    for alert in quality:
        core = headline_backed_core(alert, runner)
        updated = {**alert, "telegram_core_fact": core, "policy_plain_summary": core}
        if core and runner.source_output_aligned(updated) and not low_materiality_foreign_earnings(updated, listed, runner, telegram):
            aligned.append(updated)
    quality = aligned
    print(f"Briefing: verified_classified={len(classified)} quality_candidates={len(quality)}", flush=True)
    refresh_sent_history(telegram)
    fresh, skipped = telegram.filter_previously_seen_alerts(quality, now, lane="all")
    groups = digest_groups(fresh, skipped, sample, start, end, runner.market_materiality)
    print(f"Briefing: unseen_candidates={len(fresh)} seen_suppressed={len(skipped)}", flush=True)
    groups = add_social_evidence(groups, sample, listed, start, end, now, runner, telegram)
    for group in groups:
        mentions = company_mentions(group["title"] + " " + group["core"], listed)
        for company in group.get("explicit_companies") or []:
            if company not in mentions:
                mentions.append(company)
        group["companies"] = mentions[:MAX_STOCKS_PER_TOPIC]
    companies = {(name, code) for group in groups for name, code in group["companies"]}
    quotes: dict[str, dict] = {}
    def quote(company):
        name, code = company
        try:
            return code, parse_daily_quote(get_bytes(chart_url(code)), code, name, now)
        except Exception:
            return code, None
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        for code, result in executor.map(quote, companies):
            if result:
                quotes[code] = result
    fx_snapshot = runner.collect_fx_snapshot([normalized_fx_alert(group["alert"]) for group in groups], now)
    fx_safe = []
    for group in groups:
        fx_alert = normalized_fx_alert(group["alert"])
        conversion = runner.build_alert_fx_conversion(fx_alert, fx_snapshot, now)
        converted_title = converted_field(group["title"], conversion, runner)
        converted_core = converted_field(group["core"], conversion, runner)
        if converted_title is None or converted_core is None:
            print("Briefing: suppressed ambiguous currency formatting", flush=True)
            continue
        group["converted_title"] = converted_title
        group["converted_core"] = converted_core
        fx_safe.append(group)
    groups = fx_safe
    incomplete = any("확인 불가" in str(note) or re.search(r"failed=[1-9]|deferred=[1-9]", str(note)) for note in notes)
    report = render_report(slot, now, start, end, len(sample), groups, quotes, incomplete, listing_error, fx_snapshot, runner)
    plain, entities = runner.telegram_text_and_entities(report)
    if runner.telegram_utf16_length(plain) > 4096:
        raise RuntimeError("Report too long; no partial message sent")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "gamejoa_issue_briefing.md").write_text(report, encoding="utf-8")
    result = {"slot": slot, "window_start_kst": start.isoformat(), "window_end_kst": end.isoformat(),
              "query_time_kst": now.isoformat(timespec="seconds"), "sample_count": len(sample),
              "selected_topics": len(groups), "seen_suppressed": len(skipped),
              "coverage_incomplete": incomplete, "listing_error": listing_error,
              "quotes": quotes, "groups": [{k: v for k, v in g.items() if k != "alert"} for g in groups],
              "source_notes": notes, "fx_rates": fx_snapshot.get("rates", {}), "delivery_status": "dry_run"}
    receipt = OUT / "gamejoa_issue_briefing.json"
    receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(plain)
    if dry:
        print("Briefing: dry run; no delivery reservation or Telegram send")
        return 0
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        raise RuntimeError("Telegram credentials missing")
    if ledger is None:
        raise RuntimeError("GitHub ledger missing")
    if not ledger.update(key, run_id, "reserved"):
        result["delivery_status"] = "skipped_existing_reservation"
        receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        print("Briefing: already reserved; duplicate send skipped")
        return 0
    try:
        message_id = send_telegram(report, token, chat, runner)
    except Exception:
        result["delivery_status"] = "uncertain_reserved"
        receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        raise
    result.update({"delivery_status": "sent", "message_id": message_id,
                   "report_sha256": hashlib.sha256(report.encode()).hexdigest()})
    receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    ledger.update(key, run_id, "sent", message_id)
    print(f"Briefing: Telegram acknowledged message_id={message_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
