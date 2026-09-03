#!/usr/bin/env python3
"""Monitor 40-year JGB Dutch-style auctions without inventing a nonexistent tail."""
from __future__ import annotations

import datetime as dt
import html
import json
import pathlib
import re
import urllib.parse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from khs_source_fetch import fetch_text, record_source_failure

KST = ZoneInfo("Asia/Seoul")
ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "out"
DATA.mkdir(exist_ok=True); OUT.mkdir(exist_ok=True)
STATE = DATA / "jgb40_dutch_state.json"
PENDING = OUT / "jgb40_dutch_pending.json"
TITLE = OUT / "jgb40_dutch_title.txt"
ALERT = OUT / "jgb40_dutch_alert.html"
STATUS = OUT / "jgb40_dutch_status.md"
NEWS = "https://www.mof.go.jp/english/public_relations/whats_new/2026jgbs.html"
UA = "Mozilla/5.0 khs-jgb40-dutch/1.0"


def get(url: str, now: dt.datetime) -> str:
    text, err = fetch_text(url, UA, timeout=20, attempts=2)
    if err or not text:
        record_source_failure(lane="jgb40_dutch", source_name="Japan MOF 40Y JGB", source_url=url,
                              error=err or "empty", checked_at=now)
        raise RuntimeError(err or "empty response")
    return text


def n(value: str) -> float | None:
    value = value.strip().replace(",", "").replace("%", "")
    try: return float(value)
    except ValueError: return None


def parse(text: str, url: str) -> dict:
    soup = BeautifulSoup(text, "html.parser")
    for tr in soup.find_all("tr"):
        cells = [" ".join(x.stripped_strings) for x in tr.find_all(["td", "th"])]
        if len(cells) < 10 or cells[0].strip().lower() != "40-year":
            continue
        bids, accepted, high_yield = n(cells[6]), n(cells[7]), n(cells[9])
        if None in (bids, accepted, high_yield):
            continue
        return {
            "date": cells[2].strip(), "url": url,
            "bids_bn_yen": bids, "accepted_bn_yen": accepted,
            "btc": bids / accepted, "highest_accepted_yield": high_yield,
        }
    raise RuntimeError(f"40Y auction row not found: {url}")


def latest_two(now: dt.datetime) -> tuple[dict, dict]:
    soup = BeautifulSoup(get(NEWS, now), "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        label = " ".join(a.stripped_strings)
        if re.search(r"Auction Result of 40-Year JGBs", label, re.I) and "Market Special Participants" not in label:
            url = urllib.parse.urljoin(NEWS, a["href"])
            if url not in links: links.append(url)
    if len(links) < 2:
        raise RuntimeError("fewer than two 40Y auction links")
    new, old = links[0], links[1]
    return parse(get(old, now), old), parse(get(new, now), new)


def load() -> dict:
    try: return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception: return {}


def main() -> int:
    now = dt.datetime.now(KST)
    for p in (TITLE, ALERT):
        try: p.unlink()
        except FileNotFoundError: pass
    state = load(); first = not bool(state.get("initialized"))
    old, cur = latest_two(now)
    drop = (cur["btc"] / old["btc"] - 1) * 100
    yield_change = (cur["highest_accepted_yield"] - old["highest_accepted_yield"]) * 100
    snap = {**cur, "prev_date": old["date"], "prev_btc": old["btc"],
            "btc_drop_pct": drop, "highest_yield_change_bp": yield_change,
            "auction_method": "Dutch-style yield competitive; average yield/tail not published"}
    PENDING.write_text(json.dumps({"initialized": True, "updated_at_kst": now.isoformat(timespec="seconds"),
                                   "snapshot": snap}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    prior_date = ((state.get("snapshot") or {}).get("date"))
    new_auction = not first and cur["date"] != prior_date
    weak = cur["btc"] < 3.0 or drop <= -15.0 or (yield_change >= 15.0 and drop <= -5.0)
    STATUS.write_text(
        f"# JGB 40년 Dutch 입찰 감시\n\n- 조회: {now.isoformat(timespec='seconds')}\n"
        f"- 최신: {cur['date']} · BTC {cur['btc']:.3f}배 · 최고낙찰수익률 {cur['highest_accepted_yield']:.3f}%\n"
        f"- 상태: {'초기 기준선' if first else ('약한 신규 입찰' if new_auction and weak else '신규 경보 없음')}\n"
        "- 주의: 40년물은 Dutch 방식이라 평균 낙찰수익률이 공표되지 않아 꼬리를 계산하지 않음\n",
        encoding="utf-8")
    if not (new_auction and weak): return 0
    TITLE.write_text("🟠 JGB 40년 Dutch 입찰 수요 약화", encoding="utf-8")
    ALERT.write_text("\n".join([
        "<b>핵심 판단</b>",
        "• JGB 40년물은 Dutch 방식이므로 일반 2·10·20·30년물처럼 꼬리를 만들지 않고 BTC와 최고낙찰수익률로 판정합니다.",
        "",
        "<b>확정 숫자</b>",
        f"• BTC <b>{cur['btc']:.3f}배</b> / 직전 {old['btc']:.3f}배 / 변화 {drop:+.1f}%",
        f"• 최고낙찰수익률 <b>{cur['highest_accepted_yield']:.3f}%</b> / 직전 대비 {yield_change:+.1f}bp",
        "• 평균 낙찰수익률 미공표 → 꼬리 계산 안 함",
        "",
        "<b>시장 의미</b>",
        "• 초장기 JGB 수요 약화가 2년·10년 금리 상승, 엔화 강세, 일본의 해외채 순매도와 겹치면 글로벌 듀레이션 본국회귀 위험을 상향합니다.",
        "",
        f"• <a href=\"{html.escape(cur['url'], quote=True)}\">일본 재무성 원문</a>",
    ]) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
