#!/usr/bin/env python3
"""Treasury buyback/TGA/media signal watcher.

Monitors trusted reports that materially change the expected size, funding
source, maturity mix, or market impact of Treasury buybacks. User-facing
Telegram output is Korean, interpretation-first, and separates official facts
from sourced reports and market inference.
"""
from __future__ import annotations

import email.utils
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
REUTERS_EXECUTION = "https://www.reuters.com/world/china/us-treasury-stick-debt-auction-schedule-despite-bigger-buybacks-bessent-says-2026-08-24/"
DRUCKENMILLER_WSJ = "https://www.wsj.com/opinion/let-the-bond-market-speak-81529d74"
FRED_FX = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXKOUS"
FRED_FX_ALT = "https://fred.stlouisfed.org/data/DEXKOUS.txt"
MARKETWATCH_TGA = "https://www.marketwatch.com/livecoverage/stock-market-today-dow-s-p-500-nasdaq-nvidia-earnings-results-jackson-hole/card/10-year-yield-drifts-lower-on-report-treasury-could-tap-tga-for-bond-buybacks-Z0to77hREQ4eoFTuD7Ao"
NEWSQUAWK_VIGILANTE = "https://www.newsquawk.com/headlines/fbns-gasparino-says-treasury-secretary-bessent-will-do-whatever-it-takes-to-put-the-fear-of-god-into-bond-vigilantes-shorting-the-long-end-of-the-curve-in-an-attempt-to-drive-the-10-year-yield-to-5-according-to-wall-st-execs-with-direct-knowledge"

QUERIES = (
    'Bessent Treasury buyback "general account"',
    'Treasury official CNBC buyback general account',
    'Bessent Treasury buyback more than $4 billion',
    'Bessent bond vigilantes 10-year 5% "fear of God"',
    'Gasparino Bessent 20-year issuance stop Treasury',
    'Treasury buyback TGA long-term yields Bessent',
)
TRUSTED = (
    "CNBC", "Reuters", "Bloomberg", "Fox Business", "FBN", "Newsquawk",
    "The Wall Street Journal", "Wall Street Journal", "Financial Times",
    "Associated Press", "AP News", "MarketWatch", "Barron's",
)
FORMAT_REVISION = 5


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 khs-watch/1.1"})
    with urllib.request.urlopen(req, timeout=25) as response:
        return response.read().decode("utf-8", errors="replace")


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def strip_html(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(value or ""))).strip()


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
        rss = (
            "https://news.google.com/rss/search?q="
            + urllib.parse.quote(query + " when:2d")
            + "&hl=en-US&gl=US&ceid=US:en"
        )
        try:
            root = ET.fromstring(fetch(rss))
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
            if item["source"] and not any(name.lower() in item["source"].lower() for name in TRUSTED):
                continue
            out.append(item)
    return sorted(out, key=lambda x: parse_pub_epoch(x.get("pubDate", "")), reverse=True)


def blob(item: dict) -> str:
    return f"{item.get('title','')} {item.get('description','')} {item.get('source','')}".lower()


def is_tga_signal(item: dict) -> bool:
    text = blob(item)
    return (
        ("general account" in text or " tga" in text or "1 trillion" in text)
        and ("buyback" in text or "repurchase" in text)
    )


def is_vigilante_signal(item: dict) -> bool:
    text = blob(item)
    return (
        ("vigilante" in text or "fear of god" in text or "gasparino" in text)
        and ("10-year" in text or "10 year" in text or "20-year" in text or "20 year" in text)
    )


def pick(items: list[dict], predicate) -> dict | None:
    return next((item for item in items if predicate(item)), None)


def build_alert(tga_item: dict | None, vigilante_item: dict | None, fx: float, fx_date: str) -> tuple[str, str, dict]:
    tga_link = (tga_item or {}).get("link") or MARKETWATCH_TGA
    vigilante_link = (vigilante_item or {}).get("link") or NEWSQUAWK_VIGILANTE
    title = "🇺🇸 미 재무부, 장기금리 방어 수단 확대 신호 — TGA·바이백·만기구조 조정 동시 점검"

    body = "\n".join([
        "<b>핵심 판단</b>",
        "🟢 재무부가 장기금리 급등을 막기 위해 바이백 확대뿐 아니라 TGA 활용과 만기구조 조정까지 검토할 수 있다는 신호입니다. 다만 <b>10년물 5%는 공식 금리 상한이 아니고, 20년물 발행 중단도 아직 공식 결정이 아닙니다.</b>",
        "",
        "<b>확정 사실</b>",
        f"• 장기 비지표물 바이백: 회당 20억달러({fmt_krw(2, fx)}) → 최소 40억달러({fmt_krw(4, fx)}). <b>9월 9일 효력 발생</b>, 수정 운영일정은 재무부가 별도 공개 예정.",
        f"• Fed 공식 TGA(8월 19일): 약 9,364억달러({fmt_krw(936.4, fx)}).",
        f"• 8월 QRA: 9월말 TGA 9,500억달러({fmt_krw(950, fx)}), 10월말 1조500억달러({fmt_krw(1050, fx)})±500억달러({fmt_krw(50, fx)}).",
        f"• 현재 공식 20년물 경매 계획: 8월 160억달러({fmt_krw(16, fx)}), 9월·10월 각 130억달러({fmt_krw(13, fx)}). <b>20년물 중단은 현재 정책이 아닙니다.</b>",
        "",
        "<b>실행 상태·정책 경계선</b>",
        "• Reuters 확인: 확대된 새 프로그램 아래 실제 장기채 바이백은 아직 집행 전이며, 재무부는 정규 장기채 경매 일정을 유지하고 있습니다.",
        "• 따라서 지금까지 금리 반응은 상당 부분 <b>정책 신호효과</b>. 실제 수급효과는 첫 확대 운영의 매입액·총 제시액에서 확인해야 합니다.",
        "• 재무부 바이백의 공식 목적은 비지표물 <b>유동성 지원</b>. 향후 문구와 운용이 ‘금리 수준 방어’로 바뀌는지가 더 큰 정책 체제 변화입니다.",
        "",
        "<b>새 보도 신호</b>",
        "• CNBC 인용 보도: TGA 현금을 미 국채 바이백 재원으로 활용할 수 있다는 재무부 관계자 설명.",
        "• Fox Business 기자 Charles Gasparino의 월가 관계자 인용 보도: 10년물 금리를 5% 쪽으로 밀어올리는 장기채 숏을 억제하기 위해 추가 수단을 동원할 수 있다는 취지.",
        "• 바이백 확대·단기국채 비중 확대·장기물 발행 조정은 <b>보도·시나리오 단계</b>이며 확정 정책과 분리합니다.",
        "",
        "<b>쉽게 해석하면</b>",
        "TGA로 장기채를 먼저 매입 → 신규 발행과 바이백 시점 분리 → 장기 듀레이션·딜러 재고 부담↓ → 기간 프리미엄↓ → 10년·30년 금리 완충. 이후 Bill로 TGA를 재충전하면 부담을 장기물에서 단기물로 옮기는 ‘재무부판 만기구조 조정’에 가깝습니다.",
        "",
        "<b>반대 논리·실패모드 — Druckenmiller</b>",
        "• Druckenmiller는 현재 장기금리가 시장 기능 장애가 아니라 재정적자·인플레이션·국채공급을 반영한 가격이라면, 바이백으로 금리를 누르는 것은 가격신호를 왜곡할 수 있다고 비판했습니다.",
        "• 30년물이 5.5%에서 소화된다면 그 가격을 받아들이고, <b>기초재정수지 적자·고령화 의무지출 개혁</b>이 장기금리를 지속적으로 낮추는 해법이라는 주장입니다.",
        "",
        "<b>하지만</b>",
        f"• TGA 약 1조달러({fmt_krw(1000, fx)})는 자유자금이 아닙니다. 정부 운영자금·예정 현금유출이 있어 총잔액과 실제 바이백 가용액은 다릅니다.",
        "• TGA를 쓰더라도 나중에 Bill 등으로 재충전하면 유동성 효과가 되돌려질 수 있습니다. <b>재정적자·국가부채 문제를 해결하는 QE가 아니라 수급과 시점을 조절하는 완충책</b>입니다.",
        "",
        "<b>시장·AI 연결</b>",
        "• TGA 활용 가능성 보도 뒤 미 10년물 금리는 약 3bp 하락했지만 다른 요인도 있어 단독 인과로 단정하지 않습니다.",
        "• 장기금리↓ → 회사채·프로젝트 금융비용↓ → AI 데이터센터 투자 지연 위험↓. NVIDIA·HBM·전력·냉각에는 직접 매출 호재가 아니라 <b>할인율·시간표 측면의 간접 호재</b>입니다.",
        "",
        "<b>다음 확인</b>",
        f"① 9월 9일 이후 첫 실제 확대 운영의 매입액·총 제시액 ② 회당 40억달러({fmt_krw(4, fx)}) 초과 여부 ③ TGA 실제 감소 ④ Bill 발행 증가 ⑤ 20년물 공식 경매 변경 ⑥ 10년물 5% 접근 시 행동 ⑦ 발표 후 +1·3·5일 금리 지속성 ⑧ 11월 4일 QRA.",
        "",
        "<b>한 줄 결론</b>",
        f"재무부가 1조달러({fmt_krw(1000, fx)})를 당장 푸는 것이 아니라 TGA·바이백·만기구조로 장기금리를 완충하려는 신호이며, <b>아직 확대 프로그램 실제 매입은 시작 전</b>입니다. 유동성 지원이 금리 관리로 변하는지와 첫 실제 매입, Druckenmiller가 지적한 재정 신뢰가 11월 4일 QRA까지의 핵심 시험대입니다.",
        "",
        f"환율 기준: {fx_date}, 1달러={fx:,.2f}원",
        f'<a href="{TREASURY_BUYBACK_RELEASE}">미 재무부 바이백 공식 발표</a> · <a href="{TREASURY_QRA}">8월 QRA</a> · <a href="{REUTERS_EXECUTION}">실행 상태·정규 경매 확인</a> · <a href="{DRUCKENMILLER_WSJ}">Druckenmiller 반론</a> · <a href="{tga_link}">TGA 보도</a> · <a href="{vigilante_link}">5%·채권 자경단 보도</a> · <a href="{FED_H41}">Fed TGA 원문</a> · <a href="{TREASURY_BUYBACK_FAQ}">바이백 설명</a>',
    ])
    detail = {
        "type": "treasury_long_rate_defense_signal",
        "format_revision": FORMAT_REVISION,
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

    checked = datetime.now(KST).isoformat(timespec="seconds")
    next_state = {**state, "last_checked_kst": checked}
    seen = set(state.get("seen", []))
    force_format_resend = int(state.get("format_revision", 0) or 0) < FORMAT_REVISION

    signals = [item for item in (tga_item, vigilante_item) if item]
    signal_ids = [item.get("link") or item.get("title") for item in signals]
    has_new = any(signal_id and signal_id not in seen for signal_id in signal_ids)

    if signals and (has_new or force_format_resend):
        title, body, detail = build_alert(tga_item, vigilante_item, fx, fx_date)
        text_length = len(title) + 2 + len(body)
        if text_length > 4096:
            raise RuntimeError(f"Telegram message too long: {text_length}")
        TITLE.write_text(title + "\n", encoding="utf-8")
        ALERT.write_text(body.rstrip() + "\n", encoding="utf-8")
        DETAIL.write_text(json.dumps(detail, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        next_state["pending_ids"] = [signal_id for signal_id in signal_ids if signal_id]
        next_state["format_revision"] = FORMAT_REVISION

    NEXT_STATE.write_text(json.dumps(next_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    STATUS.write_text(
        "# 미 재무부 장기금리 방어 신호 점검\n\n"
        f"- 조회시각: {checked}\n"
        f"- TGA·바이백 신호: {'예' if tga_item else '아니오'}\n"
        f"- 5%·채권 자경단 신호: {'예' if vigilante_item else '아니오'}\n"
        f"- 신규 신호: {'예' if has_new else '아니오'}\n"
        f"- 알림 형식 개정: {FORMAT_REVISION}\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
