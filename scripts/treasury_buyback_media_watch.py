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
    title = "🇺🇸 미 재무부, TGA 현금을 장기채 바이백 재원으로 활용 가능 — 장기금리 완충 수단 확대 가능성"
    body = "\n".join([
        "<b>핵심 판단</b>",
        "🟢 보도대로라면 재무부가 장기채 바이백 재원을 신규 국채 발행에만 의존하지 않고 TGA(재무부 일반계정) 현금에서도 일시적으로 꺼내 쓸 수 있다는 뜻입니다. 장기물 수급에는 우호적이지만, ‘1조달러를 전부 시장에 푼다’는 의미는 아닙니다.",
        "",
        "<b>무엇이 새로 나왔나</b>",
        f"• 보도 단계: <b>{source}</b>가 재무부 관계자·소식통을 인용해 TGA를 바이백 재원으로 활용할 수 있다고 전했습니다.",
        "• 현재 Fed H.4.1의 8월 19일 수요일 TGA 잔액은 약 <b>9,364억달러</b>로 ‘거의 1조달러’라는 표현과 부합합니다.",
        "• 미 재무부 8월 QRA는 9월말 TGA 9,500억달러, 10월말에는 1조500억달러±500억달러까지 오를 수 있다고 가정하고 있습니다.",
        "",
        "<b>가장 중요한 정정</b>",
        "• 이번 이야기는 <b>회사채를 재무부가 사는 것</b>이 아닙니다. 대상은 미국 정부가 발행한 국채 바이백입니다.",
        "• Bessent가 언급한 ‘corporate issuance’는 최근 장기금리를 밀어올린 원인 중 하나라는 설명이지, 재무부의 매입 대상이라는 뜻이 아닙니다.",
        "",
        "<b>쉽게 해석하면</b>",
        "기존 설명은 ‘오래된 장기국채를 사고 → 새 국채 발행으로 재원을 보충’하는 만기구조 조정에 가까웠습니다. TGA 현금을 먼저 쓰면 <b>바이백 시점과 신규 발행 시점을 분리</b>할 수 있어 단기적으로 장기채 매수 압력을 더 강하게 만들 수 있습니다.",
        "",
        "<b>유동성·금리 경로</b>",
        "TGA 현금 사용 → 재무부가 장기국채 매입 → 민간 보유 장기채 감소·딜러 재고 부담 완화 → 기간 프리미엄 하락 압력 → 10년·30년 금리 완충.",
        "또 TGA가 실제로 줄어들면 은행 준비금에는 단기적으로 플러스가 될 수 있습니다. 다만 이후 TGA를 국채 발행으로 다시 채우면 그 유동성 효과는 되돌려질 수 있습니다.",
        "",
        "<b>하지만 ‘1조달러 화력’은 과장해서 보면 안 됨</b>",
        "• TGA는 정부의 운영 현금이라 전액을 바이백에 쓸 수 있는 자유자금이 아닙니다.",
        "• 8월 QRA 자체가 9월말 9,500억달러와 10월말 최대 1조1,000억달러 수준의 현금 보유 필요성을 전제로 합니다.",
        "• 따라서 ‘1조달러 전부 투입’이 아니라 <b>TGA를 추가 재원·시간조절 수단으로 활용할 여지가 있다</b>가 정확한 해석입니다.",
        "• 구조적으로는 재정적자·국가부채·향후 국채 발행 필요성이 그대로 남습니다.",
        "",
        "<b>시장 실제 반응</b>",
        "• CNBC의 TGA 활용 가능성 보도가 전해진 뒤 MarketWatch 기준 미 10년물 금리는 약 3bp 하락했습니다.",
        "• Barron's는 같은 날 10년물 -3.4bp(4.702%), 30년물 -3.9bp(5.236%)를 집계했습니다. 다만 유가 하락도 동시에 작용해 전부 TGA 보도 효과로 단정하면 안 됩니다.",
        "",
        "<b>Fed 개입 관련 해석</b>",
        "• TGA를 활용한 재무부 바이백이 커지면 장기물 시장 기능을 지원하는 역할은 강화될 수 있습니다.",
        "• 그러나 ‘Fed 개입 필요가 줄어든다’는 것은 공식 확정이 아니라 시장 해석입니다. 재무부는 돈을 창출하는 중앙은행이 아니며, 인플레이션·재정적자가 장기금리를 밀어올리면 Fed와 별개로 한계가 있습니다.",
        "",
        "<b>투자 의미</b>",
        "• 할인율: 장기금리 상단을 누를 수 있어 AI·성장주에 우호적.",
        "• 수급: 장기 비지표물 국채에 추가 공적 매수자 역할 강화 가능.",
        "• 시간표: 실제 TGA 사용 규모, 수정 바이백 일정, 11월 4일 QRA가 핵심.",
        "• 돈 버는 능력: 기업 실적을 직접 늘리는 정책은 아니지만, AI 데이터센터의 회사채 조달금리를 낮추면 투자 지연 위험을 완화할 수 있습니다.",
        "",
        "<b>실패 경로</b>",
        "TGA를 써서 장기채를 사도 → 인플레이션·재정적자 우려 지속 → TGA 재충전을 위해 Bill 발행 증가 → 장기금리 완화 효과가 일시적 → 달러·단기자금시장 부담으로 이동할 수 있습니다.",
        "",
        "<b>다음 확인</b>",
        "① 실제 바이백 회당 금액이 40억달러를 얼마나 넘어서는지 ② TGA 잔액이 실제 감소하는지 ③ Bill 발행이 얼마나 늘어나는지 ④ 10년·30년 기간 프리미엄·실질금리 ⑤ 11월 4일 QRA.",
        "",
        "<b>한 줄 결론</b>",
        "재무부가 ‘1조달러를 풀겠다’가 아니라, 거의 1조달러인 TGA를 장기채 바이백의 추가 재원·타이밍 도구로 쓸 수 있다는 신호라 단기 장기금리에는 우호적이지만, 결국 TGA를 다시 채워야 하므로 재정·국채 공급 문제를 없애는 QE는 아닙니다.",
        "",
        f'<a href="{source_link}">보도 원문</a> · <a href="https://www.marketwatch.com/livecoverage/stock-market-today-dow-s-p-500-nasdaq-nvidia-earnings-results-jackson-hole/card/10-year-yield-drifts-lower-on-report-treasury-could-tap-tga-for-bond-buybacks-Z0to77hREQ4eoFTuD7Ao">시장 반응</a> · <a href="{FED_H41}">Fed TGA 원문</a> · <a href="{TREASURY_QRA}">8월 QRA</a> · <a href="{TREASURY_BORROWING}">재무부 차입 추정치</a> · <a href="{TREASURY_BUYBACK_FAQ}">바이백 설명</a>',
    ])
    detail = {"type": "tga_buyback_media_signal", "item": item, "checked_kst": datetime.now(KST).isoformat(timespec="seconds")}
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
    new = [x for x in items if (x.get("link") or x.get("title")) not in seen and is_tga_signal(x)]

    checked = datetime.now(KST).isoformat(timespec="seconds")
    next_state = {**state, "last_checked_kst": checked}

    if new:
        item = new[0]
        title, body, detail = build_tga_alert(item)
        TITLE.write_text(title + "\n", encoding="utf-8")
        ALERT.write_text(body[:4096].rstrip() + "\n", encoding="utf-8")
        DETAIL.write_text(json.dumps(detail, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        next_state["pending"] = item.get("link") or item.get("title")

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
