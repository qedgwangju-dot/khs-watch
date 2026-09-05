#!/usr/bin/env python3
"""U.S. Treasury 10Y/20Y/30Y auction final-demand watcher.

Purpose
- Alert only when a NEW official 10Y, 20Y or 30Y auction result appears.
- Separate QRA issuance plans from actual end-investor demand at auction.
- Compare each result with the same tenor's previous auction and recent six-auction average.
- Do not infer foreign demand from Indirect Bidders; TreasuryDirect explicitly says the
  category includes both domestic and foreign customers.

Official source: TreasuryDirect recent auction results / competitive result PDFs.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import statistics
import urllib.request
from dataclasses import dataclass, asdict
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
OUT.mkdir(parents=True, exist_ok=True)
STATE_PATH = ROOT / "data" / "treasury_auction_final_demand_state.json"
NEXT_STATE = OUT / "treasury_auction_final_demand_state_next.json"
ALERT = OUT / "treasury_auction_final_demand_alert.html"
DETAIL = OUT / "treasury_auction_final_demand_detail.json"
TITLE = OUT / "treasury_auction_final_demand_title.txt"
STATUS = OUT / "treasury_auction_final_demand_status.md"

RECENT_URL = "https://www.treasurydirect.gov/auctions/results/"
BASE = "https://www.treasurydirect.gov"
FRED_FX = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXKOUS"
KST = ZoneInfo("Asia/Seoul")
UA = "Mozilla/5.0 (compatible; khs-watch-treasury-auction/1.0)"
TARGETS = {"10-Year Note": "10년물", "20-Year Bond": "20년물", "30-Year Bond": "30년물"}


def fetch(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"seen_result_urls": [], "history": {}}


def latest_fx():
    from fx_api import daily_krw
    try:
        q = daily_krw()
        return q.basis, q.rate
    except RuntimeError:
        return None, None


def krw(usd_bn: float | None, fx: float | None) -> str:
    if usd_bn is None or fx is None:
        return "원화 환산 확인 불가"
    won = usd_bn * 1e9 * fx
    if won >= 1e12:
        return f"약 {won/1e12:,.2f}조원"
    return f"약 {won/1e8:,.0f}억원"


def pct(n: float | None, d: float | None) -> float | None:
    if n is None or d in (None, 0):
        return None
    return n / d * 100.0


def num(text: str) -> float | None:
    m = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", text or "")
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def money_bn(text: str) -> float | None:
    v = num(text)
    if v is None:
        return None
    low = (text or "").lower()
    if "million" in low:
        return v / 1000.0
    if "billion" in low:
        return v
    # Treasury result PDFs usually print amounts in millions.
    if v > 1000:
        return v / 1000.0
    return v


def normalize_label(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


@dataclass
class Auction:
    tenor: str
    tenor_ko: str
    auction_date: str | None
    result_url: str
    offering_bn: float | None
    high_yield: float | None
    btc: float | None
    indirect_bn: float | None
    direct_bn: float | None
    dealer_bn: float | None
    soma_bn: float | None
    total_accepted_bn: float | None

    @property
    def indirect_pct(self): return pct(self.indirect_bn, self.total_accepted_bn)
    @property
    def direct_pct(self): return pct(self.direct_bn, self.total_accepted_bn)
    @property
    def dealer_pct(self): return pct(self.dealer_bn, self.total_accepted_bn)


def result_links() -> list[tuple[str, str, str]]:
    html = fetch(RECENT_URL).decode("utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    found = []
    for a in soup.find_all("a", href=True):
        href = a.get("href") or ""
        label = " ".join(a.get_text(" ", strip=True).split())
        if not ("R_20" in href and href.lower().endswith(".pdf")):
            continue
        # Inspect row/context to identify term.
        ctx = label
        tr = a.find_parent("tr")
        if tr:
            ctx = " ".join(tr.get_text(" ", strip=True).split())
        tenor = None
        for key in TARGETS:
            if key.lower() in ctx.lower() or key.replace("-", " ").lower() in ctx.lower():
                tenor = key
                break
        if tenor:
            url = href if href.startswith("http") else BASE + href
            found.append((tenor, TARGETS[tenor], url))
    # Keep order, dedupe URLs.
    out, seen = [], set()
    for x in found:
        if x[2] not in seen:
            out.append(x); seen.add(x[2])
    return out


def parse_pdf_text(raw: bytes) -> str:
    import io
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(raw))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def field(text: str, labels: list[str], money: bool = False) -> float | None:
    flat = " ".join(text.split())
    for lab in labels:
        # capture a nearby numeric token, optionally prefixed by $.
        m = re.search(re.escape(lab) + r"\s*[:\-]?\s*(\$?[\d,]+(?:\.\d+)?)", flat, flags=re.I)
        if m:
            token = m.group(1)
            return money_bn(token) if money else num(token)
    return None


def parse_result(tenor: str, tenor_ko: str, url: str) -> Auction:
    text = parse_pdf_text(fetch(url))
    flat = " ".join(text.split())
    dm = re.search(r"Auction Date\s*[:\-]?\s*([A-Za-z]+\s+\d{1,2},\s+\d{4}|\d{2}/\d{2}/\d{4})", flat, re.I)
    date_text = dm.group(1) if dm else None

    def alloc(label: str) -> float | None:
        # Result PDFs normally have separate accepted/tendered columns; capture the first amount after label,
        # then sanity-check later by percentages.
        m = re.search(re.escape(label) + r"\s+\$?([\d,]+(?:\.\d+)?)", flat, re.I)
        return money_bn(m.group(1)) if m else None

    return Auction(
        tenor=tenor,
        tenor_ko=tenor_ko,
        auction_date=date_text,
        result_url=url,
        offering_bn=field(text, ["Offering Amount"], money=True),
        high_yield=field(text, ["High Yield", "High Rate"]),
        btc=field(text, ["Bid-to-Cover Ratio"]),
        indirect_bn=alloc("Indirect Bidders"),
        direct_bn=alloc("Direct Bidders"),
        dealer_bn=alloc("Primary Dealers"),
        soma_bn=alloc("SOMA"),
        total_accepted_bn=field(text, ["Total Accepted"], money=True),
    )


def avg(values):
    vals = [v for v in values if isinstance(v, (int, float))]
    return statistics.mean(vals) if vals else None


def fmt(v, suffix="", digits=1):
    return "확인 불가" if v is None else f"{v:.{digits}f}{suffix}"


def verdict(cur: Auction, prev: dict | None, hist: list[dict]) -> tuple[str, list[str]]:
    refs = hist[-6:]
    avg_btc = avg([x.get("btc") for x in refs])
    avg_ind = avg([x.get("indirect_pct") for x in refs])
    avg_dealer = avg([x.get("dealer_pct") for x in refs])
    signals = []
    if cur.btc is not None and avg_btc is not None:
        signals.append(("응찰률", cur.btc - avg_btc))
    if cur.indirect_pct is not None and avg_ind is not None:
        signals.append(("간접낙찰", cur.indirect_pct - avg_ind))
    if cur.dealer_pct is not None and avg_dealer is not None:
        signals.append(("딜러인수", avg_dealer - cur.dealer_pct))  # dealer lower = stronger
    score = sum(1 if d > 0.15 else -1 if d < -0.15 else 0 for _, d in signals)
    if score >= 2:
        return "🟢 신규 장기채 최종수요 강함", [f"{n} 최근 평균 대비 개선" for n,d in signals if d > 0.15]
    if score <= -2:
        return "🔴 신규 장기채 최종수요 약함", [f"{n} 최근 평균 대비 악화" for n,d in signals if d < -0.15]
    return "🟡 신규 장기채 최종수요 혼조", ["핵심 수요지표가 한 방향으로 모이지 않음"]


def main() -> int:
    now = dt.datetime.now(KST)
    state = load_state()
    seen = set(state.get("seen_result_urls") or [])
    history = dict(state.get("history") or {})
    links = result_links()
    if not links:
        STATUS.write_text(f"# 미 국채 입찰 최종수요 감시\n\n- 조회: {now.isoformat(timespec='seconds')}\n- 상태: 공식 결과 링크 확인 불가\n", encoding="utf-8")
        return 2

    parsed = []
    for tenor, ko, url in links[:20]:
        try:
            parsed.append(parse_result(tenor, ko, url))
        except Exception:
            continue
    if not parsed:
        STATUS.write_text(f"# 미 국채 입찰 최종수요 감시\n\n- 조회: {now.isoformat(timespec='seconds')}\n- 상태: 결과 PDF 파싱 실패\n", encoding="utf-8")
        return 2

    new = [x for x in parsed if x.result_url not in seen]
    # Baseline: do not spam historical results on first install.
    if not STATE_PATH.exists():
        state = {"seen_result_urls": [x.result_url for x in parsed][-100:], "history": history}
        for x in parsed:
            rec = asdict(x)
            rec.update({"indirect_pct": x.indirect_pct, "direct_pct": x.direct_pct, "dealer_pct": x.dealer_pct})
            history.setdefault(x.tenor, []).append(rec)
            history[x.tenor] = history[x.tenor][-12:]
        state["history"] = history
        NEXT_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        STATUS.write_text(f"# 미 국채 입찰 최종수요 감시\n\n- 조회: {now.isoformat(timespec='seconds')}\n- 상태: 초기 기준선 생성 — 과거 결과는 발송하지 않음\n", encoding="utf-8")
        return 0

    if not new:
        STATUS.write_text(f"# 미 국채 입찰 최종수요 감시\n\n- 조회: {now.isoformat(timespec='seconds')}\n- 상태: 신규 10·20·30년물 입찰 결과 없음\n", encoding="utf-8")
        return 0

    # One alert per newest unseen long auction to keep Telegram readable.
    cur = new[0]
    hist = history.get(cur.tenor, [])
    prev = hist[-1] if hist else None
    tag, reasons = verdict(cur, prev, hist)
    fx_date, fx = latest_fx()
    refs = hist[-6:]
    avg_btc = avg([x.get("btc") for x in refs])
    avg_ind = avg([x.get("indirect_pct") for x in refs])
    avg_direct = avg([x.get("direct_pct") for x in refs])
    avg_dealer = avg([x.get("dealer_pct") for x in refs])

    body = [
        f"<b>🎯 핵심 판단</b>\n{tag}",
        "<b>📌 이번 입찰</b>",
        f"• 만기: <b>{cur.tenor_ko}</b>",
        f"• 발행액: {fmt(cur.offering_bn,'억달러' if False else '')}" if cur.offering_bn is not None else "• 발행액: 확인 불가",
    ]
    if cur.offering_bn is not None:
        body[-1] = f"• 발행액: <b>{cur.offering_bn:.2f}십억달러</b> ({krw(cur.offering_bn, fx)})"
    body += [
        f"• High Yield: <b>{fmt(cur.high_yield,'% ',3).strip()}</b>",
        f"• Bid-to-Cover: <b>{fmt(cur.btc,'배',2)}</b> / 최근 6회 평균 {fmt(avg_btc,'배',2)}",
        f"• Indirect: <b>{fmt(cur.indirect_pct,'%',1)}</b> / 최근 평균 {fmt(avg_ind,'%',1)}",
        f"• Direct: <b>{fmt(cur.direct_pct,'%',1)}</b> / 최근 평균 {fmt(avg_direct,'%',1)}",
        f"• Primary Dealer: <b>{fmt(cur.dealer_pct,'%',1)}</b> / 최근 평균 {fmt(avg_dealer,'%',1)}",
        "",
        "<b>🧭 쉽게 해석하면</b>",
    ]
    if tag.startswith("🟢"):
        body.append("민간 최종수요가 비교적 잘 받쳐줌 → 신규 duration에 더 높은 보상을 요구하는 압력이 완화 → 10·30년 금리에는 우호적.")
    elif tag.startswith("🔴"):
        body.append("재무부가 기존 장기채를 바이백해도 새 장기채를 시장이 약하게 받아줌 → 신규 duration에 더 높은 금리 요구 → 기간프리미엄·장기금리 상승 압력.")
    else:
        body.append("응찰률·Indirect·Dealer가 엇갈려 신규 장기채 최종수요가 한 방향으로 확인되지 않음.")
    body += [
        "",
        "<b>⚠️ 오해 방지</b>",
        "• Indirect Bidder는 해외수요와 동일하지 않습니다. 해외·국내 고객이 모두 포함됩니다.",
        "• WI tail/stop-through는 공식 Treasury 결과만으로 직접 계산하지 않습니다. 신뢰 가능한 WI 원자료가 확보된 경우에만 별도 표시합니다.",
        "• QRA의 발행계획과 이번 실제 입찰수요는 별개입니다.",
        "",
        "<b>🔍 다음 확인</b>",
        "20·30년물 후속 입찰 · 바이백 실제 집행 · 해외 TIC 수요 · CTA 숏커버 · 10년 실질금리",
        "",
        f"환율 기준: {fx_date or '확인 불가'}, 1달러={fx:,.2f}원" if fx is not None else "환율 기준: 확인 불가 — 원화 환산 미제공",
        f'<a href="{cur.result_url}">미 재무부 공식 입찰 결과</a>',
    ]
    TITLE.write_text(f"🇺🇸 미 국채 {cur.tenor_ko} 입찰 — 신규 장기채 최종수요 판정", encoding="utf-8")
    ALERT.write_text("\n".join(body), encoding="utf-8")
    DETAIL.write_text(json.dumps({"current": asdict(cur), "verdict": tag, "reasons": reasons}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")

    rec = asdict(cur); rec.update({"indirect_pct": cur.indirect_pct, "direct_pct": cur.direct_pct, "dealer_pct": cur.dealer_pct})
    history.setdefault(cur.tenor, []).append(rec); history[cur.tenor] = history[cur.tenor][-12:]
    seen.add(cur.result_url)
    NEXT_STATE.write_text(json.dumps({"seen_result_urls": list(seen)[-100:], "history": history}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    STATUS.write_text(f"# 미 국채 입찰 최종수요 감시\n\n- 조회: {now.isoformat(timespec='seconds')}\n- 상태: 신규 {cur.tenor_ko} 결과 감지\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
