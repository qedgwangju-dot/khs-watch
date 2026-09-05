#!/usr/bin/env python3
"""Treasury long-rate defense / buyback alert watcher v2.

Goal: preserve the full investment logic while making Telegram output scannable.
Monitors trusted media signals plus official Treasury buyback schedule/results-page changes.
"""
from __future__ import annotations

import email.utils
import hashlib
import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "out"
STATE = DATA / "treasury_buyback_media_state.json"
NEXT_STATE = DATA / "treasury_buyback_media_state_next.json"
ALERT = OUT / "treasury_buyback_media_alert.html"
TITLE = OUT / "treasury_buyback_media_title.txt"
DETAIL = OUT / "treasury_buyback_media_detail.json"
STATUS = OUT / "treasury_buyback_media_status.md"

FED_H41 = "https://www.federalreserve.gov/releases/h41/current/h41.htm"
TREASURY_QRA = "https://home.treasury.gov/news/press-releases/sb0590"
TREASURY_BUYBACK_RELEASE = "https://home.treasury.gov/news/press-releases/sb0607"
TREASURY_BUYBACK_FAQ = "https://www.treasurydirect.gov/help-center/faqs/buyback-faqs/"
BUYBACK_RESULTS_PAGE = "https://www.treasurydirect.gov/auctions/announcements-data-results/buy-backs/"
TENTATIVE_SCHEDULE_XML = "https://home.treasury.gov/system/files/221/Tentative-Buyback-Schedule.xml"
TENTATIVE_SCHEDULE_PDF = "https://home.treasury.gov/system/files/221/Tentative-Buyback-Schedule.pdf"
DTS_PAGE = "https://fiscaldata.treasury.gov/datasets/daily-treasury-statement/operating-cash-balance/"
REAL_YIELD_PAGE = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_real_yield_curve"
AUCTION_RESULTS_PAGE = "https://www.treasurydirect.gov/auctions/announcements-data-results/announcement-results-press-releases/"
REUTERS_EXECUTION = "https://www.reuters.com/world/china/us-treasury-stick-debt-auction-schedule-despite-bigger-buybacks-bessent-says-2026-08-24/"
DRUCKENMILLER_WSJ = "https://www.wsj.com/opinion/let-the-bond-market-speak-81529d74"
MARKETWATCH_TGA = "https://www.marketwatch.com/livecoverage/stock-market-today-dow-s-p-500-nasdaq-nvidia-earnings-results-jackson-hole/card/10-year-yield-drifts-lower-on-report-treasury-could-tap-tga-for-bond-buybacks-Z0to77hREQ4eoFTuD7Ao"
NEWSQUAWK_VIGILANTE = "https://www.newsquawk.com/headlines/fbns-gasparino-says-treasury-secretary-bessent-will-do-whatever-it-takes-to-put-the-fear-of-god-into-bond-vigilantes-shorting-the-long-end-of-the-curve-in-an-attempt-to-drive-the-10-year-yield-to-5-according-to-wall-st-execs-with-direct-knowledge"
FRED_FX = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXKOUS"
FRED_FX_ALT = "https://fred.stlouisfed.org/data/DEXKOUS.txt"

QUERIES = (
    'Bessent Treasury buyback "general account"',
    'Treasury official CNBC buyback general account',
    'Bessent Treasury buyback more than $4 billion',
    'Bessent bond vigilantes 10-year 5% "fear of God"',
    'Gasparino Bessent 20-year issuance stop Treasury',
    'Druckenmiller Treasury buyback bond market WSJ',
)
TRUSTED = (
    "CNBC", "Reuters", "Bloomberg", "Fox Business", "FBN", "Newsquawk",
    "The Wall Street Journal", "Wall Street Journal", "Financial Times",
    "Associated Press", "AP News", "MarketWatch", "Barron's",
)
FORMAT_REVISION = 6


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 khs-watch/2.0"})
    with urllib.request.urlopen(req, timeout=25) as response:
        return response.read().decode("utf-8", errors="replace")


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def strip_html(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(value or ""))).strip()


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def latest_fx():
    from fx_api import daily_krw
    q = daily_krw()
    return q.rate, q.basis


def fmt_krw(usd_bn: float, fx: float) -> str:
    return f"약 {usd_bn * fx / 1000:,.1f}조원"


def parse_pub_epoch(value: str) -> float:
    try:
        dt = email.utils.parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return 0.0


def news_items() -> list[dict]:
    out: list[dict] = []
    dedup: set[str] = set()
    for query in QUERIES:
        url = "https://news.google.com/rss/search?q=" + urllib.parse.quote(query + " when:2d") + "&hl=en-US&gl=US&ceid=US:en"
        try:
            root = ET.fromstring(fetch(url))
        except Exception:
            continue
        for node in root.findall(".//item"):
            item = {
                "title": strip_html(node.findtext("title") or ""),
                "link": (node.findtext("link") or "").strip(),
                "description": strip_html(node.findtext("description") or ""),
                "source": strip_html(node.findtext("source") or ""),
                "pubDate": (node.findtext("pubDate") or "").strip(),
            }
            key = item["link"] or item["title"]
            if not key or key in dedup:
                continue
            dedup.add(key)
            if item["source"] and not any(x.lower() in item["source"].lower() for x in TRUSTED):
                continue
            out.append(item)
    return sorted(out, key=lambda x: parse_pub_epoch(x.get("pubDate", "")), reverse=True)


def blob(item: dict) -> str:
    return f"{item.get('title','')} {item.get('description','')} {item.get('source','')}".lower()


def is_tga_signal(item: dict) -> bool:
    text = blob(item)
    return ("general account" in text or " tga" in text or "1 trillion" in text) and ("buyback" in text or "repurchase" in text)


def is_vigilante_signal(item: dict) -> bool:
    text = blob(item)
    return ("vigilante" in text or "fear of god" in text or "gasparino" in text) and ("10-year" in text or "10 year" in text or "20-year" in text or "20 year" in text)


def pick(items: list[dict], predicate) -> dict | None:
    return next((item for item in items if predicate(item)), None)


def extract_buyback_stats(page: str) -> dict | None:
    text = strip_html(page)
    def last(pattern: str) -> float | None:
        found = re.findall(pattern, text, flags=re.I)
        if not found:
            return None
        try:
            return float(found[-1].replace(",", "").replace("$", ""))
        except Exception:
            return None
    max_amt = last(r"Max(?:imum)? Par Amount(?: to be Redeemed)?\s*\$?([0-9,]+)")
    accepted = last(r"Total Par Amount Accepted\s*:?\s*\$?([0-9,]+)")
    offered = last(r"Total Par Amount Offered\s*:?\s*\$?([0-9,]+)")
    if not any(v is not None for v in (max_amt, accepted, offered)):
        return None
    out = {"max": max_amt, "accepted": accepted, "offered": offered}
    if max_amt and accepted is not None:
        out["cap_use_pct"] = accepted / max_amt * 100
    if offered and accepted is not None:
        out["accept_pct"] = accepted / offered * 100
    if max_amt and offered:
        out["offer_multiple"] = offered / max_amt
    return out


def build_alert(tga_item: dict | None, vigilante_item: dict | None, fx: float, fx_date: str,
                schedule_changed: bool, results_changed: bool, stats: dict | None) -> tuple[str, str, dict]:
    tga_link = (tga_item or {}).get("link") or MARKETWATCH_TGA
    vigilante_link = (vigilante_item or {}).get("link") or NEWSQUAWK_VIGILANTE
    title = "🇺🇸 미 재무부 장기금리 방어 — 발표가 아니라 ‘실제 돈의 이동’까지 추적"

    official_flags = []
    if schedule_changed:
        official_flags.append("🔔 수정 바이백 일정 변경 감지")
    if results_changed:
        official_flags.append("🔔 공식 바이백 결과 페이지 변경 감지")
    official_line = " · ".join(official_flags) if official_flags else "공식 일정·결과 페이지는 직전 감시 대비 추가 변경 미감지"

    stats_line = "• 결과 공개 시 <b>상한 소진율·제시액 대비 매입률·초과 제시배수</b>를 계산합니다."
    if stats and stats.get("max") and stats.get("accepted") is not None and stats.get("offered"):
        stats_line = (
            f"• 공식 결과 감지: 상한 소진율 {stats.get('cap_use_pct',0):.1f}% · "
            f"제시액 대비 매입률 {stats.get('accept_pct',0):.1f}% · 초과 제시배수 {stats.get('offer_multiple',0):.2f}배"
        )

    body = "\n".join([
        "<b>🎯 핵심 판단</b>",
        "재무부는 TGA·장기채 바이백·만기구조 조정으로 장기금리 급등을 완충하려 합니다. <b>하지만 아직 핵심은 ‘발표’이고, 진짜 효과는 실제 매입→TGA 감소→Bill 재발행까지 확인해야 합니다.</b>",
        "",
        "<b>✅ 지금 확정된 것</b>",
        f"• 장기 비지표물 바이백 상한: 20억달러({fmt_krw(2, fx)}) → 최소 40억달러({fmt_krw(4, fx)})",
        "• 9월 9일 정책 효력 발생. 기존 잠정 일정에는 9월 10일 10~20년물 운영이 잡혀 있으나 상한은 아직 20억달러로 표시 → <b>수정 공식 일정 공개가 다음 확정 이벤트</b>",
        f"• TGA: Fed 8월 19일 약 9,364억달러({fmt_krw(936.4, fx)}); QRA 9월말 목표 9,500억달러({fmt_krw(950, fx)})",
        f"• 20년물 공식 경매: 8월 160억달러({fmt_krw(16, fx)}), 9·10월 각 130억달러({fmt_krw(13, fx)}) → <b>발행 중단은 아직 아님</b>",
        "",
        "<b>🟡 아직 보도·시나리오</b>",
        "• TGA 현금을 바이백 재원으로 활용 가능(CNBC 인용 보도)",
        "• 10년물 5%는 공식 상한이 아니라 ‘채권 자경단’ 억제 관련 시장 보도상의 민감 구간",
        "• 단기국채 비중 확대·20년물 발행 조정도 공식 정책 변경 전까지는 시나리오로 분리",
        "",
        "<b>💰 이제부터 ‘실제 집행’은 이 순서로 판정</b>",
        "① <b>수정 일정</b> — 어느 만기·몇 회·회당 상한이 실제로 늘었나",
        "② <b>바이백 결과</b> — 총 제시액 / 실제 매입액 / 상한",
        stats_line,
        "③ <b>Daily Treasury Statement</b> — 결제일 전후 TGA가 실제로 빠졌나",
        "④ <b>Bill·CMB</b> — TGA 재충전을 위해 단기물 공급이 얼마나 다시 늘었나",
        "⑤ <b>20·30년 신규 입찰</b> — 꼬리·간접낙찰·딜러 인수로 최종수요 확인",
        "⑥ <b>금리 성분</b> — 10년 명목금리만 말고 실질금리·기간 프리미엄이 실제 하락했나",
        "",
        "<b>📌 왜 이게 중요한가</b>",
        "TGA로 장기채 매입 → 민간 장기 듀레이션·딜러 재고↓ → 기간 프리미엄↓ → 10·30년 금리 완충. 이후 Bill로 TGA를 채우면 <b>장기물 부담을 단기물로 옮기는 Treasury Twist</b>가 됩니다.",
        "",
        "<b>⚠️ 정책 경계선·반대 논리</b>",
        "• 재무부의 공식 바이백 목적은 <b>비지표물 유동성 지원</b>. 향후 ‘금리 수준 방어’가 공식 목적처럼 바뀌면 단순 증액보다 훨씬 큰 정책 체제 변화입니다.",
        "• Druckenmiller: 금리가 재정적자·인플레이션을 정상적으로 가격에 반영한다면 바이백으로 가격을 누르기보다 <b>기초재정수지·고령화 의무지출</b>을 고쳐야 지속적으로 금리가 내려간다는 반론.",
        f"• TGA 약 1조달러({fmt_krw(1000, fx)})는 자유자금이 아니며, 재충전 때 유동성 효과가 되돌려질 수 있습니다. QE나 부채문제 해결책이 아닙니다.",
        "",
        "<b>🤖 AI 투자 연결</b>",
        "장기 실질금리↓ → 회사채·프로젝트 금융비용↓ → AI 데이터센터 투자 지연 위험↓. NVIDIA·HBM·전력·냉각은 <b>직접 매출 호재가 아니라 할인율·시간표의 간접 호재</b>입니다.",
        "",
        "<b>🗓 다음 시험대</b>",
        "• 수정 바이백 일정 공개 → 첫 확대 운영 결과 → 결제일 DTS → 이후 Bill·CMB 공급 → 발표 후 +1·3·5일 금리 지속성 → 11월 4일 QRA",
        f"• 공식 변화 감지: {official_line}",
        "",
        "<b>한 줄 결론</b>",
        "지금은 ‘재무부가 장기금리를 누르겠다’는 신호가 강해진 단계이고, <b>진짜 정책효과는 40억달러 상한 자체가 아니라 실제 매입액·TGA 감소·단기국채 재충전·20/30년 입찰수요·실질금리가 한 방향으로 움직이는지</b>로 판정해야 합니다.",
        "",
        f"환율 기준: {fx_date}, 1달러={fx:,.2f}원",
        f'<a href="{TREASURY_BUYBACK_RELEASE}">바이백 공식 발표</a> · <a href="{TENTATIVE_SCHEDULE_PDF}">바이백 일정</a> · <a href="{BUYBACK_RESULTS_PAGE}">바이백 결과</a> · <a href="{DTS_PAGE}">일별 TGA</a> · <a href="{AUCTION_RESULTS_PAGE}">국채 입찰</a> · <a href="{REAL_YIELD_PAGE}">실질금리</a> · <a href="{TREASURY_QRA}">8월 QRA</a> · <a href="{REUTERS_EXECUTION}">실행 상태</a> · <a href="{DRUCKENMILLER_WSJ}">Druckenmiller 반론</a> · <a href="{tga_link}">TGA 보도</a> · <a href="{vigilante_link}">5% 보도</a>',
    ])
    detail = {
        "type": "treasury_long_rate_defense_execution_chain",
        "format_revision": FORMAT_REVISION,
        "schedule_changed": schedule_changed,
        "results_changed": results_changed,
        "buyback_stats": stats,
        "tga_item": tga_item,
        "vigilante_item": vigilante_item,
        "fx": fx,
        "fx_date": fx_date,
        "checked_kst": datetime.now(KST).isoformat(timespec="seconds"),
    }
    return title, body, detail


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    for path in (ALERT, TITLE, DETAIL):
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    state = load_state()
    items = news_items()
    tga_item = pick(items, is_tga_signal)
    vigilante_item = pick(items, is_vigilante_signal)
    fx, fx_date = latest_fx()

    schedule_xml = fetch(TENTATIVE_SCHEDULE_XML)
    results_page = fetch(BUYBACK_RESULTS_PAGE)
    schedule_hash = digest(schedule_xml)
    results_hash = digest(results_page)
    old_schedule_hash = state.get("schedule_hash")
    old_results_hash = state.get("results_hash")
    schedule_changed = bool(old_schedule_hash and old_schedule_hash != schedule_hash)
    results_changed = bool(old_results_hash and old_results_hash != results_hash)
    stats = extract_buyback_stats(results_page)

    checked = datetime.now(KST).isoformat(timespec="seconds")
    next_state = {
        **state,
        "last_checked_kst": checked,
        "schedule_hash": schedule_hash,
        "results_hash": results_hash,
    }
    seen = set(state.get("seen", []))
    force_format_resend = int(state.get("format_revision", 0) or 0) < FORMAT_REVISION

    signals = [item for item in (tga_item, vigilante_item) if item]
    signal_ids = [item.get("link") or item.get("title") for item in signals]
    has_new_media = any(signal_id and signal_id not in seen for signal_id in signal_ids)
    official_change = schedule_changed or results_changed

    if signals and (has_new_media or force_format_resend or official_change):
        title, body, detail = build_alert(tga_item, vigilante_item, fx, fx_date, schedule_changed, results_changed, stats)
        text_length = len(title) + 2 + len(body)
        if text_length > 4096:
            raise RuntimeError(f"Telegram message too long: {text_length}")
        TITLE.write_text(title + "\n", encoding="utf-8")
        ALERT.write_text(body.rstrip() + "\n", encoding="utf-8")
        DETAIL.write_text(json.dumps(detail, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        next_state["pending_items"] = [x for x in signal_ids if x]
        next_state["format_revision"] = FORMAT_REVISION

    NEXT_STATE.write_text(json.dumps(next_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    STATUS.write_text(
        "# 미 재무부 장기금리 방어·실제 집행 점검\n\n"
        f"- 조회시각: {checked}\n"
        f"- TGA 보도 신호: {'예' if tga_item else '아니오'}\n"
        f"- 5%·채권 자경단 신호: {'예' if vigilante_item else '아니오'}\n"
        f"- 수정 일정 변경: {'예' if schedule_changed else '아니오'}\n"
        f"- 바이백 결과 페이지 변경: {'예' if results_changed else '아니오'}\n"
        f"- 신규 미디어 신호: {'예' if has_new_media else '아니오'}\n"
        f"- 알림 형식 개정: {FORMAT_REVISION}\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
