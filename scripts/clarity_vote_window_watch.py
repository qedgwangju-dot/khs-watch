#!/usr/bin/env python3
import datetime as dt
import email.utils
import html
import json
import pathlib
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "clarity_vote_window_state.json"
PENDING_STATE_PATH = ROOT / "out" / "clarity_vote_window_pending_state.json"
ALERT_JSON = ROOT / "out" / "clarity_watch_alert.json"
STATUS_PATH = ROOT / "out" / "clarity_vote_window_status.json"
GATE_PATH = ROOT / "out" / "clarity_vote_gate.json"

DEMOCRATS_SCHEDULE = "https://www.democrats.senate.gov/2026/08/08/schedule-for-pro-forma-sessions-and-monday-september-14-2026"
DAILY_PRESS = "https://www.dailypress.senate.gov/thursday-september-10-2026/"
ROLL_CALL_MENU = "https://www.senate.gov/legislative/LIS/roll_call_lists/vote_menu_119_2.htm"
FLOOR_ACTIVITY = "https://www.senate.gov/legislative/LIS/floor_activity/09_15_2026_Senate_Floor.htm"
NEWS_RSS = "https://news.google.com/rss/search"

SCHEDULE_ET = dt.datetime(2026, 9, 15, 14, 15, tzinfo=ZoneInfo("America/New_York"))
SCHEDULE_KST = SCHEDULE_ET.astimezone(ZoneInfo("Asia/Seoul"))
VOTES_REQUIRED = 60

TIER1 = {
    "reuters": "Reuters",
    "associated press": "Associated Press",
    "ap news": "Associated Press",
    "bloomberg": "Bloomberg",
    "bloomberg law": "Bloomberg Law",
    "the block": "The Block",
    "coindesk": "CoinDesk",
    "semafor": "Semafor",
}

LUMMIS_QUERY = '"CLARITY Act" Lummis Democrats vote'
BESSENT_QUERY = '"CLARITY Act" Bessent community banks stablecoin'
LUMMIS_RE = re.compile(r"\bLummis\b", re.I)
LUMMIS_RISK_RE = re.compile(r"never\s+agree|hostage|take\s+yes|what\s+they\s+wanted|126|more,\s*more,\s*more|60\s+votes?", re.I)
BESSENT_RE = re.compile(r"\bBessent\b", re.I)
BESSENT_BANK_RE = re.compile(r"community\s+banks?|stablecoin|deposit\s+outflows?|circuit[- ]breaker|Treasury\s+Secretary|fully\s+protected", re.I)

MARKET_SYMBOLS = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "COIN": "COIN",
    "CRCL": "CRCL",
    "Nasdaq": "^IXIC",
    "S&P 500": "^GSPC",
    "DXY": "DX-Y.NYB",
    "US10Y": "^TNX",
}


def clean(value):
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def fetch_bytes(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (KHS-CLARITY-Vote-Window/1.2)"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def fetch_text(url, timeout=20):
    return fetch_bytes(url, timeout=timeout).decode("utf-8", "ignore")


def parse_rfc_date(value):
    try:
        parsed = email.utils.parsedate_to_datetime(clean(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
        return parsed.astimezone(ZoneInfo("UTC"))
    except Exception:
        return None


def source_tier(label):
    low = clean(label).lower()
    for key in sorted(TIER1, key=len, reverse=True):
        if key in low:
            return 1, TIER1[key]
    return 0, clean(label)


def load_state():
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def schedule_text_matches(text):
    low = clean(text).lower()
    compact = "".join(ch for ch in low if not ch.isspace()).replace(".", "")
    has_bill = "hr3633" in compact or "digitalassetmarketclarityact" in compact
    has_cloture = "cloture" in low
    has_date = "september15" in compact
    has_time = "2:15pm" in compact
    return has_bill and has_cloture and has_date and has_time


def official_schedule_check():
    checks = []
    errors = []
    for label, url in [("Senate Democrats", DEMOCRATS_SCHEDULE), ("U.S. Senate Daily Press", DAILY_PRESS)]:
        try:
            text = clean(BeautifulSoup(fetch_text(url), "html.parser").get_text(" ", strip=True))
            matched = schedule_text_matches(text)
            checks.append({"source": label, "url": url, "matched": matched})
        except Exception as exc:
            checks.append({"source": label, "url": url, "matched": False})
            errors.append(f"{label}: {exc}")
    return checks, errors


def parse_vote_time(detail_text):
    match = re.search(r"Vote Date:\\s*([A-Za-z]+ \\d{1,2}, \\d{4}, \\d{1,2}:\\d{2} [AP]M)", clean(detail_text), re.I)
    if not match:
        return None, None
    try:
        parsed = dt.datetime.strptime(match.group(1), "%B %d, %Y, %I:%M %p").replace(tzinfo=ZoneInfo("America/New_York"))
        return parsed, parsed.astimezone(ZoneInfo("Asia/Seoul"))
    except Exception:
        return None, None


def reconsideration_text_matches(text):
    value = clean(text)
    has_bill = bool(re.search(r"H\\.?R\\.?\\s*3633|Digital\\s+Asset\\s+Market\\s+Clarity", value, re.I))
    has_motion = bool(re.search(r"Motion\\s+by\\s+Senator\\s+Tillis\\s+to\\s+reconsider", value, re.I))
    has_vote = bool(re.search(r"Record\\s+Vote(?:\\s+No\\.?|\\s+Number)?[:\\s]+234", value, re.I))
    return has_bill and has_motion and has_vote


def reconsideration_status():
    try:
        text = clean(BeautifulSoup(fetch_text(FLOOR_ACTIVITY), "html.parser").get_text(" ", strip=True))
        entered = reconsideration_text_matches(text)
        return {
            "entered": entered,
            "url": FLOOR_ACTIVITY,
            "status": "Thom Tillis 재고동의 제출 확인" if entered else "재고동의 공식 확인 안 됨",
        }
    except Exception as exc:
        return {
            "entered": None,
            "url": FLOOR_ACTIVITY,
            "status": f"재고동의 원문 확인 실패: {exc}",
        }


def roll_call_result():
    try:
        soup = BeautifulSoup(fetch_text(ROLL_CALL_MENU), "html.parser")
    except Exception:
        return None
    for node in soup.find_all(["tr", "li", "p", "div"]):
        text = clean(node.get_text(" ", strip=True))
        if not re.search(r"H\.?R\.?\s*3633|Digital\s+Asset\s+Market\s+Clarity", text, re.I):
            continue
        if not re.search(r"cloture|motion\s+to\s+proceed|yeas|nays|agreed|rejected", text, re.I):
            continue
        link = node.find("a", href=True)
        url = urllib.parse.urljoin(ROLL_CALL_MENU, link["href"]) if link else ROLL_CALL_MENU
        detail_text = text
        try:
            detail_soup = BeautifulSoup(fetch_text(url), "html.parser")
            detail_text = clean(detail_soup.get_text(" ", strip=True))
        except Exception:
            pass
        yeas = re.search(r"Yeas?\s*[-:]?\s*(\d+)", detail_text, re.I)
        nays = re.search(r"Nays?\s*[-:]?\s*(\d+)", detail_text, re.I)
        not_voting = re.search(r"Not\s+Voting\s*[-:]?\s*(\d+)", detail_text, re.I)
        result_match = re.search(r"Result\s*[:\-]?\s*(Agreed|Rejected|Failed|Passed)", detail_text, re.I)
        result = result_match.group(1).title() if result_match else ""
        if not result and yeas:
            result = "Agreed" if int(yeas.group(1)) >= VOTES_REQUIRED else "Rejected"
        if not result:
            continue
        vote_time_et, vote_time_kst = parse_vote_time(detail_text)
        return {
            "url": url,
            "text": text,
            "result": result,
            "yeas": int(yeas.group(1)) if yeas else None,
            "nays": int(nays.group(1)) if nays else None,
            "not_voting": int(not_voting.group(1)) if not_voting else None,
            "vote_time_et": vote_time_et.isoformat() if vote_time_et else None,
            "vote_time_kst": vote_time_kst.isoformat() if vote_time_kst else None,
        }
    return None


def google_news_items(query):
    params = urllib.parse.urlencode({"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    root = ET.fromstring(fetch_bytes(f"{NEWS_RSS}?{params}"))
    rows = []
    for item in root.findall(".//item")[:50]:
        source_node = item.find("source")
        rows.append({
            "title": clean(item.findtext("title")),
            "description": clean(item.findtext("description")),
            "url": clean(item.findtext("link")),
            "pubDate": clean(item.findtext("pubDate")),
            "source": clean(source_node.text if source_node is not None else ""),
        })
    return rows


def best_context_signal(query, actor_re, content_re, now_utc):
    cutoff = now_utc - dt.timedelta(days=3)
    candidates = []
    try:
        for row in google_news_items(query):
            published = parse_rfc_date(row.get("pubDate"))
            tier, source = source_tier(row.get("source"))
            signal = clean(f"{row.get('title','')} {row.get('description','')}")
            if tier != 1 or published is None or published < cutoff or published > now_utc + dt.timedelta(hours=2):
                continue
            if actor_re.search(signal) and content_re.search(signal):
                row["source_label"] = source
                row["published"] = published
                candidates.append(row)
    except Exception:
        return None
    return max(candidates, key=lambda x: x["published"]) if candidates else None


def yahoo_snapshot(symbol):
    encoded = urllib.parse.quote(symbol, safe="")
    errors = []
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        url = f"https://{host}/v8/finance/chart/{encoded}?interval=5m&range=1d&includePrePost=true"
        try:
            payload = json.loads(fetch_text(url, timeout=12))
            result = ((payload.get("chart") or {}).get("result") or [None])[0]
            if not result:
                continue
            meta = result.get("meta") or {}
            timestamps = result.get("timestamp") or []
            quote = (((result.get("indicators") or {}).get("quote") or [{}])[0])
            closes = quote.get("close") or []
            volumes = quote.get("volume") or []
            latest_idx = None
            for idx in range(min(len(timestamps), len(closes)) - 1, -1, -1):
                if closes[idx] is not None:
                    latest_idx = idx
                    break
            price = float(closes[latest_idx]) if latest_idx is not None else float(meta.get("regularMarketPrice"))
            ts = int(timestamps[latest_idx]) if latest_idx is not None else int(meta.get("regularMarketTime") or 0)
            volume = None
            if latest_idx is not None and latest_idx < len(volumes) and volumes[latest_idx] is not None:
                volume = int(volumes[latest_idx])
            return {
                "price": price,
                "timestamp": ts,
                "interval_volume": volume,
                "regular_market_volume": meta.get("regularMarketVolume"),
                "source": host,
            }
        except Exception as exc:
            errors.append(f"{host}:{exc}")
    raise RuntimeError("; ".join(errors) or f"no data for {symbol}")


def market_snapshot():
    out = {}
    errors = []
    for label, symbol in MARKET_SYMBOLS.items():
        try:
            out[label] = yahoo_snapshot(symbol)
        except Exception as exc:
            errors.append(f"{label}:{exc}")
    return out, errors


def pct_change(before, after):
    if before in (None, 0) or after is None:
        return None
    return (float(after) / float(before) - 1.0) * 100.0


def market_reaction(pre, post):
    rows = {}
    for label in MARKET_SYMBOLS:
        before = pre.get(label) or {} if isinstance(pre, dict) else {}
        after = post.get(label) or {} if isinstance(post, dict) else {}
        b = before.get("price")
        a = after.get("price")
        if b is None or a is None:
            continue
        row = {"before": b, "after": a, "change_pct": pct_change(b, a)}
        if before.get("regular_market_volume") is not None and after.get("regular_market_volume") is not None:
            row["volume_before"] = before.get("regular_market_volume")
            row["volume_after"] = after.get("regular_market_volume")
            row["volume_change_pct"] = pct_change(before.get("regular_market_volume"), after.get("regular_market_volume"))
        rows[label] = row
    return rows


def append_events(events):
    if not events:
        return
    existing = []
    if ALERT_JSON.exists():
        try:
            existing = json.loads(ALERT_JSON.read_text(encoding="utf-8"))
        except Exception:
            existing = []
    existing.extend(events)
    write_json(ALERT_JSON, existing)


def main():
    now_utc = dt.datetime.now(ZoneInfo("UTC"))
    now_kst = now_utc.astimezone(ZoneInfo("Asia/Seoul"))
    state = load_state()
    baseline = not bool(state)
    schedule_checks, schedule_errors = official_schedule_check()
    schedule_confirmed = sum(1 for x in schedule_checks if x["matched"]) >= 2
    schedule_signature = f"H.R.3633|motion_to_proceed_cloture|{SCHEDULE_ET.isoformat()}|60"

    events = []
    seen_context = set(state.get("seen_context_events") or [])
    previous_schedule = state.get("schedule_signature")

    if previous_schedule and previous_schedule != schedule_signature and schedule_confirmed:
        events.append({
            "source": "미 상원 공식 일정 교차확인",
            "event_type": "상원 본회의 일정 변경",
            "event_subtype": "cloture_schedule_change",
            "title": "CLARITY 절차표결 시간표 변경 확인",
            "url": DEMOCRATS_SCHEDULE,
            "date": SCHEDULE_ET.isoformat(),
            "detail": f"H.R.3633 motion to proceed cloture의 공식 일정이 변경됐습니다. 현재 공식 확인 시각은 한국시간 {SCHEDULE_KST:%Y년 %m월 %d일 %H:%M} KST이며 60표가 필요합니다.",
            "verification_status": "Senate Democrats + U.S. Senate Daily Press 교차확인",
            "monitoring_unit": "event_state_change",
        })

    result = roll_call_result()
    reconsideration = reconsideration_status() if result else {"entered": None, "url": FLOOR_ACTIVITY, "status": "표결 결과 확인 전"}
    result_signature = ""
    result_is_new = False
    if result:
        result_signature = f"{result.get('result')}|{result.get('yeas')}|{result.get('nays')}|{result.get('not_voting')}"
        result_is_new = result_signature != state.get("roll_call_signature")
        if result_is_new:
            outcome_ko = "통과" if str(result.get("result")).lower() in {"agreed", "passed"} and (result.get("yeas") or 0) >= VOTES_REQUIRED else "부결"
            events.append({
                "source": "미 상원 표결기록",
                "event_type": "상원 토론종결·절차 표결 — 실제 결과",
                "event_subtype": "motion_to_proceed_cloture_result",
                "title": f"CLARITY motion to proceed cloture {outcome_ko}",
                "url": result["url"],
                "date": now_utc.isoformat(),
                "detail": f"실제 상원 표결 결과가 확인됐습니다. 찬성 {result.get('yeas') if result.get('yeas') is not None else '확인 중'}표, 반대 {result.get('nays') if result.get('nays') is not None else '확인 중'}표, 불참 {result.get('not_voting') if result.get('not_voting') is not None else '확인 중'}표입니다. 이번 표결은 최종 법안 통과 표결이 아니라 H.R.3633 본회의 심의를 진행하기 위한 motion to proceed의 cloture 관문입니다.",
                "verification_status": "U.S. Senate roll call 공식 결과",
                "monitoring_unit": "event_state_change",
                "vote_result": result,
            })

    lummis = best_context_signal(LUMMIS_QUERY, LUMMIS_RE, LUMMIS_RISK_RE, now_utc)
    lummis_key = "lummis_whip_risk_post_final_draft_2026-09-14"
    if lummis and lummis_key not in seen_context and not baseline:
        events.append({
            "source": f"{lummis['source_label']} 협상위험 검증",
            "event_type": "핵심 협상자 60표 위험 경고",
            "event_subtype": "whip_risk_warning",
            "title": "Lummis, 대규모 양보 후에도 일부 민주당 반대 가능성 경고",
            "url": lummis["url"],
            "date": lummis["pubDate"],
            "detail": "Cynthia Lummis 상원의원이 최종 문안에 민주당 요구를 대폭 반영하고 Trump 대통령이 핵심 윤리 요구를 수용했는데도 일부 민주당 의원들이 추가 요구를 이어갈 수 있다고 공개 경고했습니다. 이 발언은 실제 찬성표가 줄었다는 뜻은 아니며, 정확한 판정은 의원별 공개 입장과 실제 roll call로 확인해야 합니다.",
            "policy_actor": "Cynthia Lummis 상원의원",
            "verification_status": "핵심 협상자 발언 확인 / 실제 표 수 변화는 미확인",
            "monitoring_unit": "event_state_change",
        })
        seen_context.add(lummis_key)

    bessent = best_context_signal(BESSENT_QUERY, BESSENT_RE, BESSENT_BANK_RE, now_utc)
    bessent_key = "bessent_community_bank_circuit_breaker_support_2026-09-14"
    if bessent and bessent_key not in seen_context and not baseline:
        events.append({
            "source": f"{bessent['source_label']} 정책발언 검증",
            "event_type": "행정부 정책 압력 — 최종안·예금유출 방어장치 집행의지",
            "event_subtype": "treasury_circuit_breaker_support",
            "title": "Bessent, CLARITY 최종안 지지와 community bank 보호수단 집행 의지 확인",
            "url": bessent["url"],
            "date": bessent["pubDate"],
            "detail": "Bessent 재무장관은 CLARITY가 미국의 디지털자산 경쟁력에 필수적이라고 재확인하면서, stablecoin으로 community bank 예금 유출이 실제 악화될 경우 최종안이 재무장관에게 부여하는 추가 대응수단을 사용해 은행을 보호하겠다는 입장을 밝혔습니다. 이는 단순 통과 촉구보다 한 단계 강한 신호로, stablecoin 혁신과 지역밀착형 은행의 예금기반 보호를 동시에 약속한 것입니다. 다만 법 통과 전에는 권한이 발생하지 않고, 은행권이 rewards 규정을 충분하다고 보는지도 별도 확인해야 합니다.",
            "policy_actor": "Bessent 재무장관",
            "verification_status": "최종안 지지·community bank 방어장치 집행의지 확인 / 법 통과·발동조건은 미확정",
            "monitoring_unit": "event_state_change",
        })
        seen_context.add(bessent_key)

    if baseline:
        if lummis:
            seen_context.add(lummis_key)
        if bessent:
            seen_context.add(bessent_key)
        events = [e for e in events if e.get("event_subtype") == "motion_to_proceed_cloture_result"]

    pre_vote_market = state.get("pre_vote_market") or {}
    market_errors = []
    now_et = now_utc.astimezone(ZoneInfo("America/New_York"))
    if SCHEDULE_ET - dt.timedelta(hours=1) <= now_et <= SCHEDULE_ET + dt.timedelta(minutes=5):
        snap, market_errors = market_snapshot()
        if snap and now_et < SCHEDULE_ET:
            pre_vote_market = snap

    reaction = {}
    reaction_window = ""
    if result and pre_vote_market:
        post_vote_market, post_errors = market_snapshot()
        market_errors.extend(post_errors)
        reaction = market_reaction(pre_vote_market, post_vote_market)
        reaction_window = "즉시"
        if result_is_new:
            for event in events:
                if event.get("event_subtype") == "motion_to_proceed_cloture_result":
                    event["market_reaction"] = reaction
                    event["market_reaction_window"] = reaction_window

    market_24h_done = bool(state.get("market_24h_done"))
    vote_time_utc = SCHEDULE_ET.astimezone(ZoneInfo("UTC"))
    if result and pre_vote_market and now_utc >= vote_time_utc + dt.timedelta(hours=24) and not market_24h_done:
        followup_market, followup_errors = market_snapshot()
        market_errors.extend(followup_errors)
        reaction_24h = market_reaction(pre_vote_market, followup_market)
        if reaction_24h:
            reaction = reaction_24h
            reaction_window = "24시간"
            events.append({
                "source": "동일 시세원 24시간 후속 검산",
                "event_type": "시장 반응 후속 — 절차표결 24시간",
                "event_subtype": "cloture_market_24h",
                "title": "CLARITY 절차표결 24시간 시장 반응",
                "url": result["url"],
                "date": now_utc.isoformat(),
                "detail": "표결 전 저장한 기준값과 약 24시간 후의 BTC·ETH·COIN·CRCL 가격 및 동일 소스 거래량을 비교했습니다. Nasdaq·S&P 500·DXY·미 10년물도 같은 기준으로 함께 비교해 CLARITY 직접 효과와 거시 효과를 분리합니다.",
                "verification_status": "표결 전 사전 스냅샷과 24시간 후 동일 시세원 비교",
                "monitoring_unit": "event_state_change",
                "market_reaction": reaction_24h,
                "market_reaction_window": reaction_window,
            })
            market_24h_done = True

    roll_rejected = bool(result) and str(result.get("result") or "").lower() in {"rejected", "failed"}
    gate = {
        "status": "roll_call_completed" if result else ("confirmed_two_official_sources" if schedule_confirmed else "schedule_verification_incomplete"),
        "current_stage": ("60표 미달로 본회의 심의 진입 실패 — 최종 법안 부결은 아님" if roll_rejected else ("cloture 관문 통과 — 후속 본회의 절차 확인" if result else "예정 표결 대기")),
        "next_vote_status": "공식 새 CLARITY 표결 일정 미확인" if roll_rejected else ("후속 본회의 절차 확인 중" if result else "예정된 cloture 표결 대기"),
        "reconsideration": reconsideration,
        "procedure": "H.R.3633 motion to proceed cloture",
        "official_time_et": SCHEDULE_ET.isoformat(),
        "official_time_kst": SCHEDULE_KST.isoformat(),
        "votes_required": VOTES_REQUIRED,
        "whip_count_status": "공식 확정표 미공개 — 정당 의석수만으로 찬반을 추정하지 않음",
        "final_draft_context": "민주당 요구 126건 반영 + Tillis–Gallego 윤리안 상당 부분 반영 + Treasury의 payment-stablecoin 예금유출 방어장치",
        "main_bottlenecks": ["실제 60표 확보", "추가 윤리·State AG 집행력 논쟁", "stablecoin rewards·은행 예금유출", "illicit finance/AML", "공화당 이탈 가능성"],
        "schedule_sources": schedule_checks,
        "roll_call": result,
        "market_reaction": reaction,
        "market_reaction_window": reaction_window,
        "checked_at_kst": now_kst.isoformat(timespec="seconds"),
    }
    write_json(GATE_PATH, gate)

    new_state = dict(state)
    new_state.update({
        "schedule_signature": schedule_signature if schedule_confirmed else previous_schedule,
        "roll_call_signature": result_signature or state.get("roll_call_signature", ""),
        "seen_context_events": sorted(seen_context),
        "pre_vote_market": pre_vote_market,
        "market_24h_done": market_24h_done,
        "updated_at_kst": now_kst.isoformat(timespec="seconds"),
        "monitoring_unit": "event_state_change_not_article",
    })
    write_json(PENDING_STATE_PATH, new_state)
    append_events(events)
    write_json(STATUS_PATH, {
        "baseline": baseline,
        "new_events": len(events),
        "schedule_confirmed": schedule_confirmed,
        "schedule_checks": schedule_checks,
        "schedule_errors": schedule_errors,
        "roll_call_found": bool(result),
        "reconsideration": reconsideration,
        "lummis_signal_found": bool(lummis),
        "bessent_signal_found": bool(bessent),
        "market_24h_done": market_24h_done,
        "market_errors": market_errors,
        "monitoring_unit": "event_state_change_not_article",
    })
    print(f"clarity_vote_window_new={len(events)} schedule_confirmed={schedule_confirmed} roll_call={bool(result)} baseline={baseline} market24h={market_24h_done}")


if __name__ == "__main__":
    main()
