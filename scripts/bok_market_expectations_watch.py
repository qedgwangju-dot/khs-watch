#!/usr/bin/env python3
"""한국은행 정책금리와 국고채 금리의 시장 선행 신호를 기존 BOK MPC 알림에 추가한다.

원시 금리스왑 호가 없이 언론의 '50bp·70%'를 확정 확률로 재계산하지 않는다.
기존 workflow, Telegram 봇·chat, state delivery gate를 그대로 사용한다.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import urlencode
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup

import bok_rate_signal_upgrade as base

ECOS_STAT = "817Y002"
ECOS_CODES = {"3년": "010200000", "10년": "010210000"}
ECOS_SOURCE = "https://ecos.bok.or.kr/"
ECOS_MAX_LAG_DAYS = 7
ONE_DAY_BP = 10.0
FIVE_DAY_BP = 20.0
BOOTSTRAP_DATE = dt.date(2026, 10, 12)
BOOTSTRAP_SOURCES = (
    ("https://www.fx678.com/C/20261012/202610120838522463.html", "汇通财经", "2026-10-12"),
    ("https://www.fx168news.com/express/fastnews/1445865", "FX168", "2026-10-12"),
)
MARKET_QUERIES = (
    "한국은행 금리스왑 6개월 금리인상 확률 50bp",
    "한국 국고채 3년 10년 기준금리 인상 기대",
    "South Korea swap market 50 basis points probability rate hikes",
    "韩元 利率互换 未来六个月 加息 概率 韩国",
)


def _error(label: str, exc: BaseException) -> None:
    # HTTPError.__str__ can include an ECOS API key in its URL. Never log it.
    base.err(f"시장기대 감시 {label} 조회 실패: {type(exc).__name__}")


def extract_swap_report(blob: str) -> dict[str, float] | None:
    """기간·인상 방향·확률 표현이 모두 확인된 단일 전망만 수집한다."""
    x = re.sub(r"\s+", " ", BeautifulSoup(blob, "html.parser").get_text(" ", strip=True))
    market = bool(re.search(r"스왑|swap|利率互换|시장\s*반영|市场\s*预期|市场\s*定价", x, re.I))
    horizon = bool(re.search(r"6\s*개?월|six\s*months|6\s*months|六个?月|未来\s*六个?月", x, re.I))
    hike = bool(re.search(r"인상|hike|tighten|加息", x, re.I))
    basis = set(float(m) for m in re.findall(
        r"(\d{1,3}(?:\.\d+)?)\s*(?:bp|bps|basis\s*points|베이시스포인트|基点)", x, re.I
    ))
    probs = set(float(m) for m in re.findall(
        r"(?:확률|概率|probability|chance)[^.!?。]{0,45}?(\d{1,3}(?:\.\d+)?)\s*[%％]", x, re.I
    ))
    probs.update(float(m) for m in re.findall(
        r"(\d{1,3}(?:\.\d+)?)\s*[%％][^.!?。]{0,28}?(?:확률|概率|probability|chance)", x, re.I
    ))
    if not market or not horizon or not hike or len(basis) != 1 or len(probs) != 1:
        return None
    bp, pct = next(iter(basis)), next(iter(probs))
    if not 0 < bp <= 200 or not 0 <= pct <= 100:
        return None
    return {"horizon_months": 6, "cumulative_hike_bp": bp, "reported_probability_pct": pct}

def parse_ecos_rows(doc: dict, code: str) -> list[dict[str, Any]]:
    obj = doc.get("StatisticSearch")
    if not isinstance(obj, dict):
        raise ValueError("ECOS 통계응답 누락")
    rows: list[dict[str, Any]] = []
    for record in obj.get("row") or []:
        d = str(record.get("TIME") or "").strip()
        if not re.fullmatch(r"20\d{6}", d):
            continue
        if str(record.get("ITEM_CODE1") or "").strip() != code:
            continue
        try:
            rate = float(str(record.get("DATA_VALUE")).replace(",", ""))
            parsed = dt.datetime.strptime(d, "%Y%m%d").date()
        except (ValueError, TypeError):
            continue
        if 0.0 < rate < 30.0:
            rows.append({"date": parsed.isoformat(), "rate_pct": rate})
    return sorted({r["date"]: r for r in rows}.values(), key=lambda z: z["date"])


def official_yields(now: dt.datetime) -> dict[str, Any]:
    key = (os.environ.get("ECOS_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("ECOS_API_KEY 미설정")
    start = (now.date() - dt.timedelta(days=26)).strftime("%Y%m%d")
    end = now.strftime("%Y%m%d")

    def fetch_one(tenor: str, code: str):
        url = f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/100/{ECOS_STAT}/D/{start}/{end}/{code}"
        response = requests.get(url, timeout=25, headers=base.HEADERS)
        response.raise_for_status()
        rows = parse_ecos_rows(response.json(), code)
        if len(rows) < 2:
            raise ValueError(f"{tenor} ECOS 관측치 부족")
        latest = rows[-1]
        prev = rows[-2]
        if latest["date"] > now.date().isoformat():
            raise ValueError(f"{tenor} 현재보다 미래 날짜")
        lag = (now.date() - dt.date.fromisoformat(latest["date"])).days
        if lag > ECOS_MAX_LAG_DAYS:
            raise ValueError(f"{tenor} 데이터 지연 {lag}일")
        prior = rows[max(0, len(rows)-6)]
        return tenor, {
            "date": latest["date"],
            "rate_pct": latest["rate_pct"],
            "previous_date": prev["date"],
            "previous_rate_pct": prev["rate_pct"],
            "change_1d_bp": round((latest["rate_pct"] - prev["rate_pct"]) * 100, 2),
            "change_5obs_bp": round((latest["rate_pct"] - prior["rate_pct"]) * 100, 2),
            "lag_days": lag,
            "source": ECOS_SOURCE,
            "code": code,
        }

    data = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = [pool.submit(fetch_one, tenor, code) for tenor, code in ECOS_CODES.items()]
        for future in as_completed(tasks):
            try:
                tenor, row = future.result()
                data[tenor] = row
            except Exception as exc:
                _error("ECOS 국고채", exc)
    if len(data) != 2:
        raise RuntimeError("3년·10년 공식 금리를 모두 확인할 수 없음")
    if data["3년"]["date"] != data["10년"]["date"]:
        raise ValueError("3년·10년 공식 금리 기준일 불일치")
    return {
        "as_of": data["3년"]["date"],
        "spreads_bp": round((data["10년"]["rate_pct"]-data["3년"]["rate_pct"])*100, 2),
        "tenors": data,
    }


def market_mentions(now: dt.datetime) -> list[dict[str, Any]]:
    """RSS의 제목/요약에 수치·기간이 모두 있을 때만 숫자 있는 보도로 취급."""
    sources: list[dict[str, Any]] = []
    from email.utils import parsedate_to_datetime
    from urllib.parse import urlencode

    def fetch_rss(q):
        url = "https://news.google.com/rss/search?" + urlencode(
            {"q": q + " when:3d", "hl": "ko", "gl": "KR", "ceid": "KR:ko"}
        )
        response = requests.get(url, timeout=15, headers=base.HEADERS)
        response.raise_for_status()
        root = ElementTree.fromstring(response.content)
        result = []
        for item in root.findall(".//item")[:25]:
            try:
                stamp = parsedate_to_datetime(item.findtext("pubDate") or "")
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=dt.timezone.utc)
                stamp = stamp.astimezone(base.KST)
            except Exception:
                continue
            if stamp < now - dt.timedelta(days=3) or stamp > now + dt.timedelta(hours=1):
                continue
            title = (item.findtext("title") or "").strip()
            desc = BeautifulSoup(item.findtext("description") or "", "html.parser").get_text(" ", strip=True)
            found = extract_swap_report(f"{title} {desc}")
            if not found:
                continue
            publisher = item.find("source")
            result.append({
                **found, "published_date": stamp.date().isoformat(),
                "title": title,
                "url": (item.findtext("link") or "").strip(),
                "publisher": (publisher.text if publisher is not None else "") or "뉴스 검색",
                "origin": "언론 보도",
            })
        return result

    with ThreadPoolExecutor(max_workers=4) as pool:
        tasks = [pool.submit(fetch_rss, q) for q in MARKET_QUERIES]
        for future in as_completed(tasks):
            try:
                sources.extend(future.result())
            except Exception as exc:
                _error("시장확률 뉴스", exc)

    # 당일 제공한 원문의 합법적 재게시 두 곳은 10월 12일에만 보조 확인한다.
    # 서로 독립적인 스왑 호가 두 개가 아니므로 '원시호가 검증 완료'로 승격하지 않는다.
    if now.date() == BOOTSTRAP_DATE:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [(pool.submit(requests.get, url, timeout=12, headers=base.HEADERS), url, publisher, published)
                       for url, publisher, published in BOOTSTRAP_SOURCES]
            for future, url, publisher, published in futures:
                try:
                    response = future.result()
                    response.raise_for_status()
                    excerpt = BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True)
                    found = extract_swap_report(excerpt)
                    if found and "韩国" in excerpt and len(excerpt) < 500000:
                        sources.append({
                            **found, "published_date": published,
                            "title": "한국은행 향후 6개월 50bp 인상 확률 약 70% 보도",
                            "url": url, "publisher": publisher,
                            "origin": "중국 금융언론 재게시",
                        })
                except Exception as exc:
                    _error("중국 금융언론 재게시", exc)

    dedup = {}
    for item in sources:
        url = item.get("url")
        if url:
            dedup[url] = item
    return sorted(dedup.values(), key=lambda x: (x["published_date"], x["url"]), reverse=True)


def market_event(mentions: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not mentions:
        return None
    # 복수 재인용을 개별 독립 시장호가로 계산하지 않는다.
    newest = max(m["published_date"] for m in mentions)
    today = [m for m in mentions if m["published_date"] == newest]
    if not today:
        return None
    # 동시 보도가 여러 수치로 충돌하면 수치를 임의로 선택하지 않는다.
    readings = {(m["cumulative_hike_bp"], m["reported_probability_pct"]) for m in today}
    if len(readings) != 1:
        return None
    bp, pct = next(iter(readings))
    chosen = sorted(today, key=lambda m: (bool(m["url"]), m["publisher"]), reverse=True)[0]
    return {
        "event_key": f"media_swap:6m:{bp:g}bp:{pct:g}pct:{newest}",
        "date": newest,
        "hike_bp": bp,
        "probability_pct": pct,
        "source_name": chosen["publisher"],
        "source_url": chosen["url"],
        "source_count": len(today),
        "evidence": "언론 보도·재인용 가능 · 원시 스왑 호가 미확인",
    }

def yield_event(new: dict[str, Any], old: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not old or not old.get("as_of") or new["as_of"] <= old["as_of"]:
        return []
    events = []
    for tenor, row in new["tenors"].items():
        prev = (old.get("tenors") or {}).get(tenor) or {}
        for period, threshold in (("1d", ONE_DAY_BP), ("5obs", FIVE_DAY_BP)):
            change = row[f"change_{period}_bp"]
            try:
                old_change = float(prev[f"change_{period}_bp"])
            except (KeyError, TypeError, ValueError):
                # 이전 공식값이 없을 때 신규 급등 경보를 생성하지 않는다.
                continue
            # 매일 계속 임계치 위에 머무는 경우 반복 전송하지 않는다.
            sign = "rise" if change > 0 else "fall"
            old_sign = "rise" if old_change > 0 else "fall"
            crossed = abs(old_change) < threshold or sign != old_sign
            if abs(change) < threshold or not crossed:
                continue
            events.append({
                "key": f"yield:{tenor}:{period}:{sign}:{new['as_of']}",
                "tenor": tenor, "period": period, "change_bp": change,
                "rate_pct": row["rate_pct"], "as_of": new["as_of"],
            })
    return events

def _append_alert(payload: str) -> None:
    previous = base.ALERT.read_text(encoding="utf-8").rstrip() if base.ALERT.exists() else ""
    merged = previous + "\n\n──────────\n\n" + payload if previous else payload
    base.ALERT.write_text(merged.rstrip() + "\n", encoding="utf-8")


def main() -> int:
    base.OUT.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(base.KST)
    state = base.root_state()
    old = state.get("market_expectations") or {}
    old_bonds = old.get("official_yields") or {}

    try:
        yields = official_yields(now)
        yield_error = None
    except Exception as exc:
        yields = None
        yield_error = type(exc).__name__
        _error("ECOS 국고채 전체", exc)

    try:
        mentions = market_mentions(now)
        mention = market_event(mentions)
    except Exception as exc:
        mention = None
        mentions = []
        _error("금리스왑 시장보도 전체", exc)

    old_report = old.get("last_market_report") or {}
    market_level_changed = (
        not old_report or mention is not None
        and (float(mention["hike_bp"]) != float(old_report.get("hike_bp", -1))
             or float(mention["probability_pct"]) != float(old_report.get("probability_pct", -1)))
    )
    # 배포 직후 과거 언론 전망을 신규 신호로 재발송하지 않고 기준선으로만 저장한다.
    new_market = bool(
        old and mention and market_level_changed
        and mention["event_key"] not in set(old.get("seen_event_keys") or [])
    )
    new_yield = yield_event(yields, old_bonds) if yields else []
    seen = set(old.get("seen_event_keys") or [])
    new_yield = [x for x in new_yield if x["key"] not in seen]

    events = []
    if new_market:
        events.append(
            f"• <b>향후 6개월 누적 {mention['hike_bp']:g}bp 인상 가능성 약 "
            f"{mention['probability_pct']:g}%</b> — {html.escape(mention['source_name'])}의 {mention['date']} 보도"
        )
        events.append("  └ 이는 <b>언론이 전한 시장 가격 해석</b>이며 실제 기준금리 인상 확률의 공식 확정치가 아닙니다.")
        events.append("  └ 금리스왑 원시 호가·산출 방식 미확인. 실시간 수치로 갱신하거나 자동 계산하지 않음")
    for item in new_yield:
        label = "전 거래일" if item["period"] == "1d" else "최근 5개 관측치"
        events.append(
            f"• 국고채 <b>{item['tenor']}</b> <b>{item['rate_pct']:.3f}%</b> / "
            f"{label} <b>{item['change_bp']:+.1f}bp</b> ({item['as_of']})"
        )
    if events:
        lines = [
            "<b>한국은행 금리 인상 기대·국고채 선행 변화</b>",
            f"• 감지시각: {now:%Y-%m-%d %H:%M} (한국시간)",
            "• 정책금리 결정, 시장 기대, 채권금리의 변화를 서로 분리해서 판정",
        ] + events
        if yields:
            lines += [
                f"• 한국은행 ECOS <b>{yields['as_of']}</b> 확정 일별 국고채:"
                f" 3년 <b>{yields['tenors']['3년']['rate_pct']:.3f}%</b>,"
                f" 10년 <b>{yields['tenors']['10년']['rate_pct']:.3f}%</b>,"
                f" 10년-3년 <b>{yields['spreads_bp']:+.1f}bp</b>",
                '• <a href="https://ecos.bok.or.kr/">한국은행 ECOS 공식 시장금리</a>',
            ]
        if mention and new_market:
            lines.append(f'• <a href="{html.escape(mention["source_url"], quote=True)}">50bp·70% 언론 보도 확인 출처</a>')
        lines += [
            "• 먼저 확인할 지표: 다음 금통위 실제 결정·근원물가·국고채 3년/10년 동반 변화·외국인 국채선물 수급",
            "• 국채 발행 축소에 따른 수급 안정과 인플레이션발 금리 상승을 동일 원인으로 단정하지 않음",
        ]
        _append_alert("\n".join(lines))

    updated = dict(old)
    updated["version"] = 1
    updated["checked_at_kst"] = now.isoformat(timespec="seconds")
    updated["last_market_report"] = mention or old.get("last_market_report")
    updated["official_yields"] = yields or old_bonds
    updated["market_data_status"] = (
        "한국은행 ECOS 일별금리 확인" if yields else f"확인 불가: {yield_error}"
    )
    updated["swap_probability_status"] = (
        "언론 보도치(원시 스왑 호가 미검증)" if mention else
        "공식·직접 확인 가능한 시장 내재확률 없음"
    )
    updated["seen_event_keys"] = sorted(
        seen | ({mention["event_key"]} if new_market and mention else set()) |
        {event["key"] for event in new_yield}
    )[-200:]
    state["market_expectations"] = updated
    base.PENDING.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with base.STATUS.open("a", encoding="utf-8") as f:
        f.write(
            "\n## 국고채·금리스왑 시장 선행 신호\n\n"
            f"- 한국은행 공식 국고채 수익률: {updated['market_data_status']}\n"
            f"- 국고채 수익률 기준일: {(yields or old_bonds).get('as_of') or '확인 불가'}\n"
            f"- 50bp·70% 보도: {updated['swap_probability_status']}\n"
            f"- 새 시장 기대 보도: {'예' if new_market else '아니오'}\n"
            f"- 새 국고채 금리 경보: {len(new_yield)}건\n"
            f"- 신규 텔레그램 알림: {'예' if events else '아니오'}\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
