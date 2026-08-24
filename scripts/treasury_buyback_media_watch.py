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
FORMAT_REVISION = 4


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


def latest_fx() -> tuple[float, str]:
    errors: list[str] = []
    try:
        rows = [line.strip().split(",") for line in fetch(FRED_FX).splitlines()[1:] if "," in line]
        for date, value, *_ in reversed(rows):
            if value and value != ".":
                return float(value), date
    except Exception as exc:
        errors.append(f"csv={exc}")

    try:
        text = fetch(FRED_FX_ALT)
        matches = re.findall(r"^(20\d{2}-\d{2}-\d{2})\s+([0-9]+(?:\.[0-9]+)?)\s*$", text, flags=re.M)
        if matches:
            date, value = matches[-1]
            return float(value), date
    except Exception as exc:
        errors.append(f"txt={exc}")

    raise RuntimeError("FRED DEXKOUS 환율 확인 실패: " + " | ".join(errors))


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
        f"• 장기 비지표물 바이백: 회당 20억달러({fmt_krw(2, fx)}) → 최소 40억달러({fmt_krw(4, fx)}), 9월 9일 시행.",
        f"• Fed 공식 TGA(8월 19일): 약 9,364억달러({fmt_krw(936.4, fx)}).",
        f"• 8월 QRA: 9월말 TGA 9,500억달러({fmt_krw(950, fx)}), 10월말 1조500억달러({fmt_krw(1050, fx)})±500억달러({fmt_krw(50, fx)}).",
        f"• 현재 공식 20년물 경매 계획: 8월 160억달러({fmt_krw(16, fx)}), 9월 130억달러({fmt_krw(13, fx)}), 10월 130억달러({fmt_krw(13, fx)}). 즉 <b>20년물 중단은 아직 공식 정책이 아닙니다.</b>",
        "",
        "<b>새 보도 신호</b>",
        "• CNBC 인용 보도: TGA 현금을 미 국채 바이백 재원으로 활용할 수 있다는 재무부 관계자 설명.",
        "• Fox Business 기자 Charles Gasparino의 월가 관계자 인용 보도: 장기물을 숏쳐 10년물 금리를 5% 쪽으로 밀어올리는 채권 자경단을 억제하기 위해 재무부가 추가 수단을 동원할 수 있다는 취지.",
        "• 거론 수단에는 바이백 확대·단기국채 비중 확대·20년물 등 장기물 발행 조정이 포함될 수 있지만 <b>정책 확정이 아니라 보도·시나리오 단계</b>입니다.",
        "",
        "<b>쉽게 해석하면</b>",
        "TGA로 장기채를 먼저 매입 → 신규 발행과 바이백 시점을 분리 → 장기 듀레이션·딜러 재고 부담↓ → 기간 프리미엄↓ → 10년·30년 금리 완충. 이후 단기국채로 TGA를 재충전하면 부담을 장기물에서 단기물로 옮기는 ‘재무부판 만기구조 조정’에 가까워집니다.",
        "",
        "<b>5%의 의미</b>",
        "• 10년물 5%는 Bessent가 공식 선언한 목표나 수익률곡선통제 상한이 아닙니다.",
        "• 시장이 재무부의 정책 민감 구간으로 받아들일 가능성은 있지만, Fed와 달리 재무부는 돈을 무제한 창출할 수 없어 방어선의 신뢰도는 실제 매입 규모와 발행구조 변화로 확인해야 합니다.",
        "",
        "<b>하지만</b>",
        f"TGA는 정부 운영 현금이라 약 1조달러({fmt_krw(1000, fx)})를 전부 쓸 수 없습니다. TGA를 쓰더라도 나중에 국채를 발행해 다시 채워야 하므로 <b>재정적자·국가부채 문제를 해결하는 QE가 아니라 수급과 시점을 조절하는 한시적 완충책</b>입니다.",
        "",
        "<b>시장·AI 연결</b>",
        "• TGA 활용 가능성 보도 뒤 미 10년물 금리는 약 3bp 하락. 다만 다른 시장요인도 있어 단독 인과로 단정하지 않습니다.",
        "• 장기금리↓ → 회사채·프로젝트 금융비용↓ → AI 데이터센터 투자 지연 위험↓. NVIDIA·HBM·전력·냉각에는 직접 매출 호재가 아니라 <b>할인율·시간표 측면의 간접 호재</b>입니다.",
        "",
        "<b>다음 확인</b>",
        f"① 9월 9일 실제 회당 바이백이 40억달러({fmt_krw(4, fx)})를 얼마나 넘는지 ② TGA 실제 감소 ③ Bill 발행 증가 ④ 20년물 공식 경매 변경 여부 ⑤ 10년물 5% 접근 시 재무부 행동 ⑥ 11월 4일 QRA.",
        "",
        "<b>한 줄 결론</b>",
        f"재무부가 1조달러({fmt_krw(1000, fx)})를 당장 푸는 것이 아니라 약 9,364억달러({fmt_krw(936.4, fx)}) TGA·바이백·만기구조 조정을 조합해 장기금리 상승을 완충할 수 있다는 신호이며, 5% 방어선·20년물 중단은 아직 비공식 보도 단계라 9월 9일 실제 매입과 11월 4일 QRA가 진짜 시험대입니다.",
        "",
        f"환율 기준: FRED DEXKOUS {fx_date}, 1달러={fx:,.2f}원",
        f'<a href="{TREASURY_BUYBACK_RELEASE}">미 재무부 바이백 공식 발표</a> · <a href="{TREASURY_QRA}">8월 QRA</a> · <a href="{tga_link}">TGA 보도</a> · <a href="{vigilante_link}">5%·채권 자경단 보도</a> · <a href="{FED_H41}">Fed TGA 원문</a> · <a href="{TREASURY_BUYBACK_FAQ}">바이백 설명</a>',
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
        f"- 신규 신호: {'예' if has_new else '아니오'}\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
