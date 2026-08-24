#!/usr/bin/env python3
"""Watch trusted-media Treasury buyback/TGA intervention signals.

This complements the official Treasury watcher. It catches material interviews
and sourced reports (CNBC/Reuters/Bloomberg/WSJ/FT/AP/Barron's/MarketWatch)
that can change the expected size, funding source, or market impact of Treasury
buybacks before an official press release is posted.
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
TREASURY_BORROWING = "https://home.treasury.gov/news/press-releases/sb0584"
TREASURY_BUYBACK_FAQ = "https://www.treasurydirect.gov/help-center/faqs/buyback-faqs/"
TREASURY_OIG_AFR = "https://oig.treasury.gov/system/files/2026-02/OIG-26-014-%28508%29.pdf"

QUERIES = (
    'Bessent Treasury buyback "general account"',
    'Treasury official CNBC buyback general account',
    'Bessent Treasury buyback more than $4 billion',
    'Treasury buyback TGA long-term yields Bessent',
)
TRUSTED = (
    "CNBC", "Reuters", "Bloomberg", "The Wall Street Journal", "Wall Street Journal",
    "Financial Times", "Associated Press", "AP News", "MarketWatch", "Barron's"
)
MATERIAL_TERMS = (
    "general account", "tga", "$1 trillion", "1 trillion", "toolkit",
    "more than $4 billion", "could increase", "increase further", "buyback",
)
KEY_INTERVENTION_TERMS = ("buyback", "buybacks", "repurchase", "repurchases")
FORMAT_REVISION = 2


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 khs-watch/1.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", errors="replace")


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(s or ""))).strip()


def news_items() -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for q in QUERIES:
        url = (
            "https://news.google.com/rss/search?q="
            + urllib.parse.quote(q + " when:2d")
            + "&hl=en-US&gl=US&ceid=US:en"
        )
        try:
            root = ET.fromstring(fetch(url))
        except Exception:
            continue
        for item in root.findall(".//item"):
            title = strip_html(item.findtext("title") or "")
            link = (item.findtext("link") or "").strip()
            desc = strip_html(item.findtext("description") or "")
            source = strip_html(item.findtext("source") or "")
            pub = (item.findtext("pubDate") or "").strip()
            key = link or title
            if not key or key in seen:
                continue
            seen.add(key)
            blob = f"{title} {desc} {source}".lower()
            if not any(t.lower() in blob for t in KEY_INTERVENTION_TERMS):
                continue
            if not any(t.lower() in blob for t in MATERIAL_TERMS):
                continue
            if source and not any(name.lower() in source.lower() for name in TRUSTED):
                continue
            out.append({"title": title, "link": link, "description": desc, "source": source, "pubDate": pub})
    return out


def parse_pub_epoch(value: str) -> float:
    try:
        dt = email.utils.parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return 0.0


def is_tga_signal(item: dict) -> bool:
    blob = f"{item.get('title','')} {item.get('description','')}".lower()
    return (
        ("general account" in blob or "tga" in blob or "1 trillion" in blob)
        and any(x in blob for x in KEY_INTERVENTION_TERMS)
    )


def build_tga_alert(item: dict) -> tuple[str, str, dict]:
    source = item.get("source") or "신뢰 보도"
    source_link = item.get("link") or TREASURY_QRA
    title = "🇺🇸 미 재무부, TGA를 장기국채 바이백 재원으로 활용 가능 — ‘1조달러 전액 투입’은 아님"
    body = "\n".join([
        "<b>핵심 판단</b>",
        "🟢 재무부가 약 1조달러 규모의 TGA(재무부 일반계정)를 장기국채 바이백의 <b>추가 재원·시간조절 수단</b>으로 활용할 수 있다는 보도입니다. 장기물 수급·금리에는 우호적이지만, 1조달러를 전부 시장에 투입한다는 확정 계획은 아닙니다.",
        "",
        "<b>확정 사실 / 보도 단계</b>",
        f"• <b>보도 단계:</b> {source}가 재무부 고위 관계자들을 인용해 TGA로 미 국채 바이백 자금을 댈 수 있다고 전했습니다.",
        "• <b>공식 확정:</b> 재무부는 8월 19일 10~20년·20~30년 비지표물 바이백을 회당 최대 20억달러 → 최소 40억달러로 확대했습니다.",
        "• <b>공식 숫자:</b> Fed H.4.1의 8월 19일 TGA는 약 9,364억달러로 ‘거의 1조달러’와 대체로 일치합니다.",
        "• <b>공식 계획:</b> 8월 QRA는 9월말 TGA 9,500억달러, 10월말 1조500억달러±500억달러를 예상합니다.",
        "",
        "<b>가장 중요한 오해 방지</b>",
        "• 재무부가 <b>회사채를 사는 이야기가 아닙니다.</b> 매입 대상은 미국 정부가 발행한 국채입니다.",
        "• ‘1조달러 화력’은 TGA 총잔액을 뜻할 뿐, 전액을 바이백에 쓸 수 있는 자유자금이 아닙니다.",
        "• Fed의 QE가 아닙니다.",
        "",
        "<b>쉽게 해석하면</b>",
        "TGA 현금으로 장기국채를 먼저 매입 → 신규 국채 발행과 바이백 시점을 분리 → 민간 장기채·딜러 재고 부담 완화 → 기간 프리미엄 하락 압력 → 10년·30년 금리 완충. TGA가 실제 감소하면 단기적으로 은행 준비금에도 플러스일 수 있습니다.",
        "",
        "<b>하지만</b>",
        "TGA를 나중에 다시 채우려면 Bill 등 국채 발행이 필요합니다. 그래서 <b>재정적자·국가부채·순국채 공급 문제를 없애는 정책이 아니라, 부담의 시점과 만기를 조절하는 수급 완충책</b>에 가깝습니다.",
        "",
        "<b>시장 실제 반응</b>",
        "• CNBC 보도 뒤 MarketWatch 기준 미 10년물 금리는 약 3bp 하락했습니다.",
        "• 같은 날 10년물 4.702%(-3.4bp), 30년물 5.236%(-3.9bp) 수준. 다만 유가 하락도 함께 작용해 전부 TGA 뉴스 효과로 단정할 수는 없습니다.",
        "",
        "<b>AI 투자 연결</b>",
        "장기금리↓ → 회사채·프로젝트 금융비용↓ → AI 데이터센터 요구수익률 부담↓ → 투자 지연 위험 완화. 즉 직접 매출 호재가 아니라 <b>할인율·자금조달비용 측면의 간접 호재</b>입니다.",
        "",
        "<b>Fed 관련 해석</b>",
        "‘Fed 개입 필요가 줄어든다’는 것은 <b>시장 해석</b>이지 공식 확정 정책이 아닙니다.",
        "",
        "<b>다음 확인</b>",
        "① 실제 바이백 회당 금액이 40억달러를 얼마나 넘는지 ② TGA가 실제 감소하는지 ③ 이후 Bill 발행으로 얼마나 재충전하는지 ④ 10년·30년 명목·실질금리와 기간 프리미엄 ⑤ 11월 4일 QRA.",
        "",
        "<b>한 줄 결론</b>",
        "‘재무부가 1조달러를 푼다’가 아니라, 약 9,364억달러 TGA를 장기국채 바이백의 추가 재원·타이밍 도구로 쓸 수 있다는 신호입니다. 단기 장기금리·AI 할인율에는 우호적이지만 구조적 부채 해결책이나 QE는 아닙니다.",
        "",
        f'<a href="{source_link}">보도 원문</a> · <a href="https://www.marketwatch.com/livecoverage/stock-market-today-dow-s-p-500-nasdaq-nvidia-earnings-results-jackson-hole/card/10-year-yield-drifts-lower-on-report-treasury-could-tap-tga-for-bond-buybacks-Z0to77hREQ4eoFTuD7Ao">시장 반응</a> · <a href="{FED_H41}">Fed TGA 원문</a> · <a href="{TREASURY_QRA}">8월 QRA</a> · <a href="{TREASURY_BUYBACK_FAQ}">바이백 설명</a>',
    ])
    detail = {
        "type": "tga_buyback_media_signal",
        "format_revision": FORMAT_REVISION,
        "item": item,
        "checked_kst": datetime.now(KST).isoformat(timespec="seconds"),
    }
    return title, body, detail


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    for p in (ALERT, TITLE, DETAIL):
        try:
            p.unlink()
        except FileNotFoundError:
            pass

    state = load_state()
    seen = set(state.get("seen", []))
    items = sorted(news_items(), key=lambda x: parse_pub_epoch(x.get("pubDate", "")), reverse=True)
    force_format_resend = int(state.get("format_revision", 0) or 0) < FORMAT_REVISION
    if force_format_resend:
        new = [x for x in items if is_tga_signal(x)]
    else:
        new = [x for x in items if (x.get("link") or x.get("title")) not in seen and is_tga_signal(x)]

    checked = datetime.now(KST).isoformat(timespec="seconds")
    next_state = {**state, "last_checked_kst": checked}

    if new:
        item = new[0]
        title, body, detail = build_tga_alert(item)
        TITLE.write_text(title + "\n", encoding="utf-8")
        if len(title) + 2 + len(body) > 4096:
            raise RuntimeError(f"Telegram message too long: {len(title) + 2 + len(body)}")
        ALERT.write_text(body.rstrip() + "\n", encoding="utf-8")
        DETAIL.write_text(json.dumps(detail, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        next_state["pending"] = item.get("link") or item.get("title")
        next_state["format_revision"] = FORMAT_REVISION

    NEXT_STATE.write_text(json.dumps(next_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    STATUS.write_text(
        "# 재무부 바이백 보도·인터뷰 신호 점검\n\n"
        f"- 조회시각: {checked}\n"
        f"- 후보 기사: {len(items)}\n"
        f"- 신규 TGA/바이백 중요 신호: {'예' if new else '아니오'}\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
