"""Delivery decisions for the daily US positioning snapshot."""

from datetime import date


def daily_digest_due(state, delivery_date_kst):
    """Allow one scheduled daily digest per Korea calendar date."""
    if isinstance(delivery_date_kst, date):
        target = delivery_date_kst.isoformat()
    else:
        target = date.fromisoformat(str(delivery_date_kst)[:10]).isoformat()
    return not isinstance(state, dict) or state.get("daily_digest_sent_date_kst") != target


def daily_event_label(updates, correction=False):
    """Describe a daily snapshot without calling an unchanged report new."""
    if correction:
        detail = "정정·보강"
    elif updates:
        detail = "신규 변화"
    else:
        return "일일 정기 현황"
    return f"일일 정기 현황 · {detail}"


# AAII / Conference Board official monthly retail-crowding overlay. The two
# surveys have different populations and horizons. No trading signal is
# generated from either survey alone; no percentage is inferred from a chart.
import re
from datetime import datetime


def parse_aaii_allocation(text):
    """Parse AAII's dated five-component survey, not the weekly bull/bear poll."""
    month = re.search(r"Asset Allocation Results for\s+([A-Z][a-z]+)\s+(20\d{2})", text)
    if not month:
        raise ValueError("AAII monthly asset-allocation period missing")
    observed = datetime.strptime(month.group(1) + " " + month.group(2), "%B %Y").date()
    section = text[month.end():month.end() + 1800]

    def field(pattern):
        m = re.search(pattern, section, flags=re.I)
        if not m:
            raise ValueError("AAII official survey component missing")
        return float(m.group(1))

    stocks = field(r"\bStocks Total\s+([\d.]+)\s*%")
    stock_funds = field(r"\bStock Funds\s+(?:Image\s+)?([\d.]+)\s*%")
    direct = field(r"\bStocks\s+(?:Image\s+)?([\d.]+)\s*%")
    bonds = field(r"\bBonds Total\s+([\d.]+)\s*%")
    cash = field(r"\bCash\s+(?:Image\s+)?([\d.]+)\s*%")
    if not all(0 <= x <= 100 for x in (stocks, stock_funds, direct, bonds, cash)):
        raise ValueError("AAII percentage outside 0–100")
    if abs((stock_funds + direct) - stocks) > 0.15 or abs((stocks + bonds + cash) - 100) > 0.3:
        raise ValueError("AAII stock components or three-way allocation inconsistent")
    return {
        "period": observed.strftime("%Y-%m"),
        "stocks_pct": stocks, "stock_funds_pct": stock_funds,
        "direct_stock_pct": direct, "bonds_pct": bonds, "cash_pct": cash,
    }


def parse_conference_board_confidence(text):
    """Only public headline/index and qualitative stock expectation; no fake %."""
    m = re.search(r"Updated:\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday),?\s+"
                  r"([A-Z][a-z]+\s+\d{1,2},\s*20\d{2})", text)
    if not m:
        raise ValueError("Conference Board updated release date missing")
    release = datetime.strptime(m.group(1), "%B %d, %Y").date()
    headline = re.search(r"Consumer Confidence Index.{0,120}?"
                         r"(?:rose|increased|fell|declined|decreased) by\s+([\d.]+)"
                         r"\s+points to\s+([\d.]+)", text, re.I | re.S)
    if not headline:
        raise ValueError("Conference Board headline index and monthly move unavailable")
    change_points = float(headline.group(1))
    value = float(headline.group(2))
    if not (1 <= value <= 200) or not (0 <= change_points <= 100):
        raise ValueError("Conference Board index out of bounds")
    exp = re.search(r"Expectations Index.{0,220}?\bto\s+(\d+(?:\.\d+)?)", text, re.I | re.S)
    if not exp:
        raise ValueError("Conference Board expectations index unavailable")
    expectation_value = float(exp.group(1))
    if not 1 <= expectation_value <= 200:
        raise ValueError("Conference Board expectations index outside plausible range")
    bull_phrase = re.search(r"more consumers(?:\s+in\s+\w+)?\s+expected stock prices"
                            r"\s+to increase rather than decrease", text, re.I)
    bear_phrase = re.search(r"more consumers(?:\s+in\s+\w+)?\s+expected stock prices"
                            r"\s+to decrease rather than increase", text, re.I)
    stock_up_majority = True if bull_phrase else False if bear_phrase else None
    return {
        "period": release.strftime("%Y-%m"), "published_date": release.isoformat(),
        "confidence_index": value, "headline_move_abs_points": change_points,
        "expectations_index": expectation_value,
        "stock_up_vs_down_majority": stock_up_majority,
    }


def evaluate_retail_crowding(previous, aaii, conference, on_date):
    """Silent first baseline; subsequent *new release* may notify once per pair."""
    previous = previous if isinstance(previous, dict) else {}
    observed_date = date.fromisoformat(str(on_date)[:10])
    aaii_day = date.fromisoformat(aaii["period"] + "-01")
    conference_day = date.fromisoformat(conference["published_date"])
    old_a, old_c = previous.get("aaii") or {}, previous.get("conference") or {}
    if old_a.get("period") and aaii["period"] < old_a["period"]:
        raise ValueError("AAII official period rolled back")
    if old_c.get("period") and conference["period"] < old_c["period"]:
        raise ValueError("Conference Board official period rolled back")
    if (not 0 <= (observed_date - aaii_day).days <= 75
            or not 0 <= (observed_date - conference_day).days <= 50):
        raise ValueError("AAII/Conference Board survey is stale or future-dated")
    crowded = aaii["stocks_pct"] >= 70 and aaii["cash_pct"] <= 15
    up = conference["stock_up_vs_down_majority"]
    # Absence of an official numeric stock-expectations table is NOT ATH evidence.
    regime = "동반 높은 주식노출·상승기대" if crowded and up is True else (
        "개인 주식 비중 높음·기대 정밀확인 대기" if crowded else "주식비중 경계 완화")
    pair = aaii["period"] + "|" + conference["period"]
    old_pair = str(previous.get("pair") or "")
    prior_initialized = bool(old_pair and old_a and old_c)
    notify = bool(prior_initialized and pair != old_pair and
                  (crowded and up is True or previous.get("regime") == "동반 높은 주식노출·상승기대"))
    upcoming = {
        "aaii": aaii, "conference": conference, "pair": pair,
        "regime": regime,
    }
    return {"state": upcoming, "alert": notify, "baseline": not prior_initialized,
            "source_period_changed": bool(prior_initialized and pair != old_pair)}


AAII_ALLOCATIONS_URL = "https://www.aaii.com/assetallocationsurvey"
AAII_OFFICIAL_ARCHIVE = "https://www.aaii.com/latest/updatearchive?category=487"
BOARD_CONFIDENCE_URL = "https://www.conference-board.org/topics/consumer-confidence/"


def official_page_text(raw):
    """Normalize verified first-party HTML without substituting a search snippet."""
    if "<" not in raw:
        return " ".join(raw.split())
    from bs4 import BeautifulSoup
    return BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)


def parse_aaii_monthly_article(raw):
    """Read numeric AAII official monthly release at its PUBLISHED precision.

    Unlike the dynamic overview, the staff article may report rounded 0.1pp
    allocations. Do not rewrite them as the more precise webpage figures.
    """
    from calendar import month_name
    text = official_page_text(raw)
    months = "|".join(month_name[i] for i in range(1, 13))
    title = re.search(r"\b(" + months + r") AAII Asset Allocation Survey results:", text, re.I)
    if not title:
        raise ValueError("AAII official article monthly results title missing")
    before = text[max(0, title.start() - 1100):title.start()]
    published_candidates = re.findall(
        r"\b(?:" + months + r")\s+\d{1,2},\s+20\d{2}\b", before, re.I)
    if not published_candidates:
        raise ValueError("AAII official article publication date missing")
    published = datetime.strptime(published_candidates[-1].title(), "%B %d, %Y").date()
    survey_month = datetime.strptime(title.group(1).title(), "%B").month
    expected_release_month = (survey_month % 12) + 1
    expected_year = published.year if expected_release_month != 1 else published.year - 1
    if published.month != expected_release_month or published.day > 12:
        raise ValueError("AAII release date not aligned to survey month")
    section = text[title.end():title.end() + 1500]

    def get(name):
        match = re.search(name + r"\s*:\s*(\d+(?:\.\d+)?)\s*%", section, re.I)
        if not match:
            raise ValueError("AAII official article missing allocation component")
        return float(match.group(1))
    stocks = get(r"Stocks and Stock Funds")
    bonds = get(r"Bonds and Bond Funds")
    cash = get(r"Cash")
    direct = get(r"Stocks")
    stock_funds = get(r"Stocks Funds?")
    if not all(0 <= v <= 100 for v in (stocks, bonds, cash, direct, stock_funds)):
        raise ValueError("AAII official article percentage out of bounds")
    if abs(stocks + bonds + cash - 100.0) > 0.4:
        raise ValueError("AAII article totals do not approximately sum to 100")
    if abs(direct + stock_funds - stocks) > 0.25:
        raise ValueError("AAII article direct stock and fund subtotals disagree")
    return {
        "period": f"{expected_year:04d}-{survey_month:02d}",
        "stocks_pct": stocks, "stock_funds_pct": stock_funds,
        "direct_stock_pct": direct, "bonds_pct": bonds, "cash_pct": cash,
        "source_precision": "AAII 공식 해설 기사 소수 첫째 자리",
    }


def aaii_latest_official_article_links(raw):
    """Select only AAII official dated monthly asset-allocation articles."""
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin, urlsplit
    from calendar import month_name
    matches = []
    for a in BeautifulSoup(raw, "html.parser").find_all("a", href=True):
        title = a.get_text(" ", strip=True)
        if not re.match(r"^(" + "|".join(month_name[i] for i in range(1, 13))
                        + r") AAII Asset Allocation Survey:", title, re.I):
            continue
        url = urljoin("https://www.aaii.com/", a["href"])
        parts = urlsplit(url)
        if (parts.scheme == "https" and parts.hostname == "www.aaii.com"
                and re.fullmatch(r"/latest/article/\d+-[a-z0-9-]+/?", parts.path)
                and not parts.query and not parts.fragment):
            matches.append(url)
    return list(dict.fromkeys(matches))[:3]


def fetch_current_aaii_allocation(fetch, now):
    """Prefer dated exact official table, use independently dated AAII article."""
    current = fetch(AAII_ALLOCATIONS_URL)
    try:
        value = parse_aaii_allocation(official_page_text(current))
        month_date = date.fromisoformat(value["period"] + "-01")
        if not 0 <= (now - month_date).days <= 75:
            raise ValueError("AAII exact table stale; retry dated official article")
        value["source_url"] = AAII_ALLOCATIONS_URL
        value["source_precision"] = "AAII 공식 자산배분 표 소수 둘째 자리"
        return value
    except ValueError:
        pass
    for listing in (current, None):
        if listing is None:
            listing = fetch(AAII_OFFICIAL_ARCHIVE)
        for official_url in aaii_latest_official_article_links(listing):
            try:
                value = parse_aaii_monthly_article(fetch(official_url))
                month_date = date.fromisoformat(value["period"] + "-01")
                if not 0 <= (now - month_date).days <= 75:
                    continue
                value["source_url"] = official_url
                return value
            except (ValueError, RuntimeError):
                continue
    raise ValueError("AAII current official allocation table and dated article unavailable")


def update_retail_survey_overlay(*, repo_root=None, fetch=None, on_date=None):
    """Optional verified monthly overlay on the existing US fund-flow delivery.

    Reads/writes only existing state and pending paths. No Telegram API call,
    new bot, or additional schedule; existing workflow owns send and commit.
    """
    import json
    from pathlib import Path
    from html import escape
    from zoneinfo import ZoneInfo

    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[1]
    root = Path(repo_root)
    saved = root / "data" / "us_fund_flow_state.json"
    pending = root / "out" / "us_fund_flow_pending_state.json"
    alert = root / "out" / "us_fund_flow_alert.html"
    status = root / "out" / "us_fund_flow_status.md"
    if not saved.is_file():
        raise RuntimeError("Existing US fund-flow state missing; refuse to create new baseline")
    candidate = json.loads(pending.read_text(encoding="utf-8") if pending.exists()
                           else saved.read_text(encoding="utf-8"))
    if not isinstance(candidate, dict) or not isinstance(candidate.get("seen"), dict) or not isinstance(candidate.get("values"), dict):
        raise RuntimeError("Existing US fund-flow state malformed; refuse to overwrite")

    if fetch is None:
        import requests
        from bs4 import BeautifulSoup
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; khs-watch-retail-survey/1.0)",
            "Accept-Language": "en-US,en;q=0.9",
        })
        def fetch(url):
            response = session.get(url, timeout=(7, 19))
            response.raise_for_status()
            return response.text

    # Both dated primary sources must be valid. A failure here does not silence
    # existing ICI, margin, Goldman, or options/SOX watchers.
    try:
        today = on_date or datetime.now(ZoneInfo("America/New_York")).date()
        asset = fetch_current_aaii_allocation(fetch, today)
        confidence = parse_conference_board_confidence(
            official_page_text(fetch(BOARD_CONFIDENCE_URL)))
        previous = (candidate.get("derived") or {}).get("retail_survey")
        evaluated = evaluate_retail_crowding(previous, asset, confidence, today)
    except Exception as exc:
        detail = f"retail_survey_source_withheld=true reason={type(exc).__name__} {str(exc)[:125]}"
        print(detail)
        if status.exists():
            with status.open("a", encoding="utf-8") as writer:
                writer.write("\n- 월간 AAII/Conference Board: 공식 원문 검증 실패, 새 경보·상태 갱신 보류\n")
        return {"status": "source_withheld", "telegram_sent": False, "reason": type(exc).__name__}

    next_snapshot = evaluated["state"]
    old_snapshot = (candidate.get("derived") or {}).get("retail_survey")
    if old_snapshot == next_snapshot:
        print("retail_survey_status=unchanged monthly_periods_verified=true")
        return {"status": "unchanged", "telegram_sent": False, "pair": next_snapshot["pair"]}

    # Only an official new period triggers. An initial read never replays
    # months-old survey observations as an alleged new market event.
    candidate.setdefault("derived", {})["retail_survey"] = next_snapshot
    if evaluated["alert"]:
        a, c = next_snapshot["aaii"], next_snapshot["conference"]
        lines = [
            "<b>미국 개인투자자 주식비중·주가 기대 변화</b>",
            f"• AAII {escape(a['period'])}: 주식·주식형펀드 {a['stocks_pct']:.2f}% / 현금 {a['cash_pct']:.2f}% "
            f"({escape(a.get('source_precision','공식 자료'))})",
            f"• Conference Board {escape(c['period'])}: 소비자신뢰지수 {c['confidence_index']:.1f} / 기대지수 {c['expectations_index']:.1f}",
            "• 12개월 주가 전망: 상승 예상 응답이 하락 예상 응답보다 많음" if c["stock_up_vs_down_majority"] is True
            else "• 12개월 주가 전망: 최신 원문만으로 우위 확인 보류",
            f"• 감시 판정: {escape(next_snapshot['regime'])}; 기준월 변동이 확인됨",
            "• AAII 자산배분 월간 조사와 Conference Board 소비자 기대는 표본·질문·기간이 다르며"
            " 신규 순매수액, 역사적 최고치 또는 증시 하락 확정 신호가 아닙니다.",
            "• Goldman Prime 헤지펀드 포지션은 별도 기준주간의 공개보도이며 같은 날 수치로 합산하지 않습니다.",
            f'• <a href="{escape(a.get("source_url", AAII_ALLOCATIONS_URL),quote=True)}">AAII 월간 자산배분 공식</a> · '
            f'<a href="{BOARD_CONFIDENCE_URL}">Conference Board 공식 발표</a>',
        ]
        previous_body = alert.read_text(encoding="utf-8").strip() if alert.exists() else ""
        alert.write_text((previous_body + "\n\n" if previous_body else "")
                         + "\n".join(lines) + "\n", encoding="utf-8")

    # Pending state is persisted only by the existing workflow after successful
    # send (or safely with no alert), preserving historic source fingerprints.
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if status.exists():
        with status.open("a", encoding="utf-8") as writer:
            writer.write(
                f"\n- 월간 개인 수급 공식검증: AAII {asset['period']} 주식 {asset['stocks_pct']:.2f}%"
                f" / 현금 {asset['cash_pct']:.2f}% · Conference Board {confidence['period']}"
                f" 신뢰 {confidence['confidence_index']:.1f} · 기존 대비"
                f" {'신규 경보' if evaluated['alert'] else '초기 기준선 또는 관찰 업데이트'}\n"
            )
    result = {"status": "alert_ready" if evaluated["alert"] else "baseline_saved",
              "pair": next_snapshot["pair"], "telegram_sent": False}
    print("retail_survey_status=" + json.dumps(result, ensure_ascii=False))
    return result
