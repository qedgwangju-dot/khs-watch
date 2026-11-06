#!/usr/bin/env python3
"""Independent manager-distress event lane for the existing 13F Telegram route.

SEC 13F is a delayed holdings snapshot, not a bankruptcy or liquidation registry.
Never infer liquidation, entry prices, or legal insolvency from 13F or stock drops.
"""
from __future__ import annotations

import datetime as dt
import email.utils
import hashlib
import html
import json
import os
import pathlib
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import thirteenf_sector_watch as sec_watch

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data/thirteenf_fund_distress_watch_state.json"
RECEIPT_PATH = ROOT / "out/thirteenf_fund_distress_delivery.json"
UTC = dt.timezone.utc
EXPECTED_BOT = "khs887988798879_bot"
MANAGER_CIK = "0002045724"
MANAGER_NAME = "Situational Awareness"
SUBMITTED_CLAIM_KEY = "situational:user-submitted-x:2118364772370427985:2026-11-06"
CLAIM_LINK = "https://x.com/MrMikeInvesting/status/2118364772370427985"
SEC_FILING = "https://www.sec.gov/Archives/edgar/data/2045724/000093583626000418/0000935836-26-000418-index.html"
REUTERS_JULY = "https://www.investing.com/news/stock-market-news/situational-awareness-portfolio-sinks-67-in-july-on-ai-stock-rout-letter-shows-4828944"
REUTERS_AUGUST = "https://www.marketscreener.com/news/ken-griffin-s-citadel-sheds-over-4-billion-of-situational-awareness-bets-ce7858dadd8cf425"
REUTERS_SEPT = "https://www.marketscreener.com/news/jpmorgan-curbed-lending-to-situational-awareness-after-ai-losses-source-says-ce785bdfd18af62c"
SEC_13F_GUIDE = "https://www.sec.gov/rules-regulations/staff-guidance/division-investment-management-frequently-asked-questions/frequently-asked-questions-about-form-13f"
USER_AGENT = "Mozilla/5.0 (compatible; KHS-fund-event-monitor/1.0)"
QUERIES = (
    '"Situational Awareness" Aschenbrenner (bankruptcy OR bankrupt OR insolvency OR liquidation OR "wind down") when:7d',
    '"Situational Awareness" Aschenbrenner (margin call OR Citadel OR lending OR forced sale OR broker OR position) when:7d',
    '"Leopold Aschenbrenner" (fund OR hedge) (shutdown OR bankruptcy OR liquidated OR restructuring OR resumed) when:7d',
)
TRUSTED = (
    "reuters", "financial times", "bloomberg", "wall street journal", "associated press",
    "cnbc", "barron's", "barrons",
)
LEVELS = {"single": 1, "corroborated": 2}
MAX_LIVE_ALERTS = 2


def manager_related(text: str) -> bool:
    return bool(re.search(r"\bsituational awareness\b|\baschenbrenner\b", text, flags=re.I))


def type_of_event(text: str) -> str | None:
    low = text.lower()
    if re.search(r"\b(bankrupt|bankruptcy|insolvency|insolvent|chapter 11|bankruptcy filing|bankruptcy petition)\b", low):
        return "파산 보도·주장"
    if re.search(r"\b(wind(?:ing)? down|shut(?:ting)? down|shutter(?:ed)?|close(?:d|s|ing)? (?:the )?fund|full liquidation|liquidat(?:ion|ed|ing))\b", low):
        return "펀드 청산·운용 종료"
    if re.search(r"\b(margin call|forced sale|forced unwind|distress sale|citadel|block trade)\b", low):
        return "마진콜·대규모 매각"
    if re.search(r"\b(lending|prime broker|cut off|credit line|financing|funding)\b", low):
        return "차입·주거래은행 변화"
    if re.search(r"\b(resum(?:e|ed|ing)|restart(?:ed)?|rebuild(?:ing)?|re-enter(?:ed)?|new options)\b", low):
        return "거래 재개·운용 재편"
    return None


def trusted(publisher: str) -> bool:
    low = (publisher or "").lower()
    return any(x == low or x in low for x in TRUSTED)


def old_event_recap(title: str, kind: str) -> bool:
    """A new article repeating the known July forced unwind is not a new trade."""
    if kind not in {"마진콜·대규모 매각", "펀드 청산·운용 종료"}:
        return False
    is_old = bool(re.search(
        r"\b(?:July 2026|Jul(?:y)?\.? 30|in July|July unwind|last summer|summer 2026)\b",
        title, re.I,
    ))
    fresh = bool(re.search(
        r"\b(?:new|fresh|another|additional|again|second|second round|November)\b",
        title, re.I,
    ))
    return is_old and not fresh


def parse_feed(xml_data: bytes, now: dt.datetime) -> list[dict]:
    root = ET.fromstring(xml_data)
    found = []
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        desc = re.sub(r"<[^>]*>", " ", item.findtext("description") or "")
        source = (item.findtext("source") or "").strip()
        if not trusted(source) or not manager_related(title):
            continue
        kind = type_of_event(title)
        if not kind or old_event_recap(title, kind):
            continue
        try:
            published = email.utils.parsedate_to_datetime(item.findtext("pubDate") or "")
            published = published.astimezone(UTC)
        except (TypeError, ValueError, OverflowError):
            continue
        if not dt.timedelta(0) <= now - published <= dt.timedelta(days=7):
            continue
        url = (item.findtext("link") or "").strip()
        if not url.startswith("https://"):
            continue
        found.append({
            "kind": kind, "source": source, "title": title,
            "url": url, "published": published.isoformat(),
        })
    return found


def collect_news(now: dt.datetime) -> tuple[list[dict], list[str]]:
    unique = {}
    errors = []
    for query in QUERIES:
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({
            "q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"
        })
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=14) as response:
                feed = response.read(700_000)
            for row in parse_feed(feed, now):
                digest = hashlib.sha256(
                    (row["title"].lower() + "|" + row["source"].lower() + "|" + row["published"][:10]).encode()
                ).hexdigest()[:24]
                unique[digest] = row
        except Exception as exc:
            errors.append(f"{type(exc).__name__} ({len(errors)+1}/{len(QUERIES)} 원천)")
    return list(unique.values()), errors


def make_events(items: list[dict], old: dict) -> list[tuple[str, str, list[dict]]]:
    groups: dict[str, list[dict]] = {}
    for item in items:
        day = dt.datetime.fromisoformat(item["published"]).date()
        year, week, _ = day.isocalendar()
        key = f"situational:news:{item['kind']}:{year}-W{week:02d}"
        groups.setdefault(key, []).append(item)
    ready = []
    for key, rows in groups.items():
        distinct = {}
        for item in sorted(rows, key=lambda x: x["published"], reverse=True):
            distinct.setdefault(item["source"].lower(), item)
        sources = list(distinct.values())
        level = "corroborated" if len(sources) >= 2 else "single"
        prior = old.get(key, {})
        if LEVELS.get(prior.get("level"), 0) >= LEVELS[level]:
            continue
        ready.append((key, level, sources[:3]))
    priority = {"파산 보도·주장": 0, "펀드 청산·운용 종료": 1,
                "마진콜·대규모 매각": 2, "차입·주거래은행 변화": 3, "거래 재개·운용 재편": 4}
    ready.sort(key=lambda x: (priority.get(x[2][0]["kind"], 10), x[0]))
    return ready[:MAX_LIVE_ALERTS]


def sec_source_status() -> str:
    # SEC company submissions support accurate filing-date evidence. The SEC
    # submissions feed is NOT a court bankruptcy docket or a fund NAV source.
    try:
        obj = sec_watch.http_json("https://data.sec.gov/submissions/CIK0002045724.json")
        recent = (obj.get("filings") or {}).get("recent") or {}
        forms, accessions, dates = (recent.get(k) or [] for k in ("form", "accessionNumber", "filingDate"))
        filings = [
            (when, form, accession)
            for when, form, accession in zip(dates, forms, accessions)
            if form in {"13F-HR", "13F-HR/A"}
        ]
        if not filings:
            return "SEC 13F 최신 제출 서류 재확인 불가(13F 부재는 파산 증거 아님)"
        date, form, accession = max(filings)
        return f"SEC 13F 공시 {date} 제출({form}, {accession}); 분기말 보유 자료이며 파산 판정 불가"
    except Exception as exc:
        return f"SEC 직접 조회 실패({type(exc).__name__}); 이전 공시를 최신 확인으로 대체하지 않음"


def build_manual_alert(sec_status: str) -> str:
    # User-provided source text, not independent access to the X post.
    return "\n".join([
        "[Situational Awareness 펀드 긴급 사실확인]",
        "판정: 공식 파산 미확인 · SNS 주장(독립 확인 전)",
        "■ 2026-11-06 제공된 X 게시물은 '공식 파산·전량 청산'을 주장하지만 법원 접수번호·펀드 공식 발표는 제시되지 않았습니다.",
        "■ 검증된 7월 사건: 로이터는 포트폴리오 가치 67% 하락 및 상장주식 대부분의 시타델 매각을 보도했습니다.",
        "■ 검증된 8월 사건: 시타델이 인수한 포트폴리오의 80% 이상을 다시 매각했습니다. 시타델의 매각을 펀드의 11월 신규 청산으로 계산하면 안 됩니다.",
        "■ 9월 로이터는 JP모건 대출 중단과 다른 중개은행의 거래 관계 유지를 보도했습니다. 7월 청산 이후 운용 종료가 확정된 상태는 아니었습니다.",
        "■ SNS의 6개 종목 '매입가→현재가'는 출처·거래명세 검증 전이며, 펀드 실제 매수가·확정 실현손실이 아닙니다.",
        f"■ SEC 확인 범위: {sec_status}",
        "■ 다음 확정 관문: 법원 파산 접수·운용사 발표·독립 언론 보도·9월 말 13F 신규 제출. SEC 공식 안내상 3분기 13F 제출기한은 2026-11-16입니다.",
        "원문(SNS·미확인): " + CLAIM_LINK,
        "기존 확인(로이터 7월): " + REUTERS_JULY,
        "기존 확인(로이터 8월): " + REUTERS_AUGUST,
        "기존 확인(로이터 9월): " + REUTERS_SEPT,
        "SEC 공시: " + SEC_FILING,
        "SEC 13F 기한 안내: " + SEC_13F_GUIDE,
    ])


def build_news_alert(level: str, rows: list[dict], sec_status: str) -> str:
    kind = rows[0]["kind"]
    label = "복수 원출처 보도" if level == "corroborated" else "신뢰매체 1곳 보도·독립 확인 전"
    lines = [
        "[Situational Awareness 펀드 위기 사건 감지]",
        f"판정: {kind} · {label}",
        "■ 언론 보도를 확인했으나 법원 파산·펀드 청산의 공식 법적 확정과 구분합니다.",
        f"■ SEC 확인 범위: {sec_status}",
        "■ 분기말 13F 평가액과 당일 보유·체결가격·실제 실현손익은 다릅니다.",
        "확인한 원출처:",
    ]
    for row in rows:
        lines.append(f"- {row['source']} · {row['published'][:10]} · {row['title']}")
        lines.append(row["url"])
    return "\n".join(lines)


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {"schema": 1, "events": {}, "manual_claim": {}}
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("events"), dict):
            raise ValueError("invalid previous delivery state")
        return data
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError("펀드 이벤트 중복방지 상태파일 훼손 — 자동 재전송 차단") from exc


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def send_verified(message: str) -> dict:
    token = (os.getenv("THIRTEENF_TELEGRAM_BOT_TOKEN") or "").strip()
    configured = (os.getenv("THIRTEENF_TELEGRAM_CHAT_ID") or os.getenv("KHS_POLICY_TELEGRAM_CHAT_ID") or "").strip()
    if not token or not configured:
        raise RuntimeError("기존 13F 전용 Telegram 봇/수신처 미설정 — 다른 봇으로 대체하지 않음")
    bot = sec_watch.verify_bot(token)
    if bot.lower() != EXPECTED_BOT:
        raise RuntimeError("기존 13F 봇 수신처 불일치")
    recipient = sec_watch.telegram_api(token, "getChat", {"chat_id": configured})
    expected_chat_id = recipient.get("id")
    if expected_chat_id is None:
        raise RuntimeError("Telegram 수신 대화 ID 확인 실패")
    if configured.lstrip("-").isdigit() and str(expected_chat_id) != configured:
        raise RuntimeError("Telegram 구성된 숫자 chat_id와 실제 수신 대화 불일치")
    if configured.startswith("@") and (recipient.get("username") or "").lower() != configured.lstrip("@").lower():
        raise RuntimeError("Telegram @username 대화와 조회 결과 불일치")
    if len(message) > 3750:
        raise RuntimeError("Telegram 알림 길이 초과 — 임의 절단 금지")
    result = sec_watch.telegram_api(token, "sendMessage", {
        "chat_id": configured, "text": message, "disable_web_page_preview": "true"
    })
    mid = result.get("message_id")
    actual = (result.get("chat") or {}).get("id")
    if mid is None or str(actual) != str(expected_chat_id):
        raise RuntimeError("Telegram 전송 응답의 message_id/chat.id 확인 실패; 재전송 보류")
    hashed = hashlib.sha256(str(actual).encode()).hexdigest()[:12]
    print(f"fund_distress_delivery_confirmed=true message_id={mid} chat_fingerprint={hashed}")
    return {"message_id": mid, "chat_fingerprint": hashed, "sent_at_utc": dt.datetime.now(UTC).isoformat()}


def main() -> int:
    now = dt.datetime.now(UTC)
    state = load_state()
    news, errors = collect_news(now)
    status = sec_source_status()
    print(f"fund_distress_source_health={len(QUERIES)-len(errors)}/{len(QUERIES)} sec_status={status}")
    if errors:
        print("::warning::Situational Awareness 일부 뉴스원천 수집 불완전; 부분 수집을 전체 무변화로 간주하지 않음")
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    # A specific user's submitted, dated claim gets a one-time *fact-check*
    # alert. It is not upgraded to a confirmed bankruptcy signal.
    notified = 0
    if not state.get("manual_claim", {}).get(SUBMITTED_CLAIM_KEY):
        receipt = send_verified(build_manual_alert(status))
        state.setdefault("manual_claim", {})[SUBMITTED_CLAIM_KEY] = receipt
        save_state(state)
        notified += 1
    for key, level, sources in make_events(news, state.get("events", {})):
        receipt = send_verified(build_news_alert(level, sources, status))
        state.setdefault("events", {})[key] = {
            "level": level, "source_names": [x["source"] for x in sources], **receipt
        }
        save_state(state)
        notified += 1
    if len(errors) != len(QUERIES):
        state["last_complete_news_scan_utc"] = now.isoformat() if not errors else state.get("last_complete_news_scan_utc")
    state["last_scan_errors"] = errors
    state["last_checked_utc"] = now.isoformat()
    save_state(state)
    # A separate local audit survives the step as an artifact when upload works.
    RECEIPT_PATH.write_text(json.dumps({
        "checked_utc": now.isoformat(),
        "sent_count": notified,
        "event_count": len(news),
        "news_source_errors": errors,
        "last_delivery": state.get("manual_claim", {}).get(SUBMITTED_CLAIM_KEY),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"fund_distress_checked=true notified={notified} candidates={len(news)} news_sources_ok={len(QUERIES)-len(errors)}")
    if len(errors) == len(QUERIES):
        # A completely dark feed cannot be reported as a successful scan.
        # The separate state persistence step still saves any confirmed
        # Telegram delivery receipt because it runs under always().
        raise RuntimeError("3개 뉴스 수집 경로 전부 실패 — 감시 실패로 표시하고 무변화로 판정하지 않음")
    return 0


def self_test() -> None:
    assert manager_related("Situational Awareness manager")
    assert manager_related("Leopold Aschenbrenner sold shares")
    assert not manager_related("Citadel liquidated an unrelated book")
    assert type_of_event("Situational Awareness bankrupt") == "파산 보도·주장"
    assert type_of_event("Situational Awareness forced sale to Citadel") == "마진콜·대규모 매각"
    assert not type_of_event("Situational Awareness new 13F filing")
    assert trusted("Reuters") and not trusted("Telegram channel")
    assert old_event_recap(
        "Situational Awareness: lessons from July 2026 Citadel forced sale",
        "마진콜·대규모 매각"
    )
    assert not old_event_recap(
        "Situational Awareness fresh new margin call after July 2026",
        "마진콜·대규모 매각"
    )
    now = dt.datetime(2026, 11, 6, 4, 0, tzinfo=UTC)
    sample = b"""<rss><channel><item><title>Situational Awareness hedge fund bankruptcy claims</title>
    <source>Reuters</source><link>https://example.com/one</link><pubDate>Fri, 06 Nov 2026 02:00:00 GMT</pubDate>
    </item><item><title>Situational Awareness bankruptcy is unconfirmed</title>
    <source>Random X Channel</source><link>https://example.com/two</link><pubDate>Fri, 06 Nov 2026 03:00:00 GMT</pubDate>
    </item><item><title>Situational Awareness margin call in July</title>
    <source>Reuters</source><link>https://example.com/old</link><pubDate>Fri, 31 Jul 2026 02:00:00 GMT</pubDate>
    </item></channel></rss>"""
    parsed = parse_feed(sample, now)
    assert len(parsed) == 1, parsed
    first = make_events(parsed, {})
    assert len(first) == 1 and first[0][1] == "single"
    key = first[0][0]
    assert not make_events(parsed, {key: {"level": "single"}})
    confirm = dict(parsed[0], source="Financial Times", title="Situational Awareness bankruptcy", published=parsed[0]["published"])
    assert make_events([parsed[0], confirm], {key: {"level": "single"}})[0][1] == "corroborated"
    assert not make_events([parsed[0], confirm], {key: {"level": "corroborated"}})
    manual = build_manual_alert("SEC 미확인")
    assert "공식 파산 미확인" in manual and "시타델" in manual
    assert "실현손실이 아닙니다" in manual
    print("fund_distress_regression=PASS checks=rumor_gate,aged_news,old_recap_filter,source_quality,dedup,upgrade,manual_caveat,source_outage_fail_visible")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        raise SystemExit(main())
