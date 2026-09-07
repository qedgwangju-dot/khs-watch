#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import html
import os
import re
from typing import Any

import requests
from bs4 import BeautifulSoup

import korea_market_stress_watch_v10 as v10

watch = v10.watch
_original_fetch_usdkrw = watch.fetch_usdkrw
_original_add_event = watch.add_event

ECOS_API_HOME = "https://ecos.bok.or.kr/api/"
ECOS_STAT_CODE = "731Y001"
ECOS_ITEM_CODE_USD = "0000001"

SAMYANG_FX_NEWS = "https://www.inews24.com/view/2002549"
FX_SECTOR_NEWS = "https://www.yna.co.kr/view/AKR20260904167300008"
TRANSPORT_FX_NEWS = "https://m.edaily.co.kr/News/Read?mediaCodeNo=257&newsId=01954886645577824"
SAMYANG_IR = "https://www.samyangfoods.com/kor/ir/list.do?pageIndex=1&pageUnit=20&seq=76"

NAVER_STOCK_BASIC = "https://m.stock.naver.com/api/stock/{code}/basic"
NAVER_STOCK_MAIN = "https://finance.naver.com/item/main.naver?code={code}"

FX_DOWN_BURDEN = [
    {
        "label": "삼양식품",
        "codes": ["003230"],
        "reason": "상반기 해외매출 비중 83% → 같은 달러 매출의 원화 환산액 감소 부담. 수입 원재료 비용 감소가 일부 상쇄",
    },
    {
        "label": "현대차·기아",
        "codes": ["005380", "000270"],
        "reason": "수출·해외 판매의 달러 매출을 원화로 환산할 때 매출·이익 부담",
    },
    {
        "label": "삼성전자·SK하이닉스",
        "codes": ["005930", "000660"],
        "reason": "달러 매출 비중이 크고 원화 비용이 존재해 원화 강세가 단기 이익 역풍으로 작용 가능",
    },
]

FX_DOWN_BENEFIT = [
    {
        "label": "대한항공·아시아나항공",
        "codes": ["003490", "020560"],
        "reason": "항공유·리스·정비 등 달러 비용의 원화 환산 부담 감소",
    },
    {
        "label": "현대제철",
        "codes": ["004020"],
        "reason": "철광석·원료탄 등 달러 결제 수입 원재료의 원화 비용 감소",
    },
    {
        "label": "한국전력·한국가스공사",
        "codes": ["015760", "036460"],
        "reason": "연료·에너지 수입 비용의 원화 환산 부담 감소",
    },
]

_last_fx: dict[str, Any] = {}


def fetch_ecos_usdkrw(now: dt.datetime | None = None) -> dict[str, Any]:
    """Fetch the latest official BOK ECOS daily USD/KRW reference rate.

    ECOS 731Y001 / 0000001 = 원/미국달러(매매기준율), daily.
    This is an official daily validation series, not an intraday trigger feed.
    The API key is never persisted or emitted in logs/state/source URLs.
    """
    now = now or dt.datetime.now(watch.KST)
    api_key = (os.getenv("ECOS_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("ECOS_API_KEY missing")

    start = (now.date() - dt.timedelta(days=14)).strftime("%Y%m%d")
    end = now.date().strftime("%Y%m%d")
    url = (
        "https://ecos.bok.or.kr/api/StatisticSearch/"
        f"{api_key}/json/kr/1/100/{ECOS_STAT_CODE}/D/{start}/{end}/{ECOS_ITEM_CODE_USD}"
    )
    r = requests.get(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; khs-korea-market-stress-watch/11.1)",
            "Accept": "application/json",
        },
        timeout=30,
    )
    r.raise_for_status()
    payload = r.json()
    block = payload.get("StatisticSearch") if isinstance(payload, dict) else None
    rows = (block or {}).get("row") if isinstance(block, dict) else None
    if not isinstance(rows, list) or not rows:
        result = payload.get("RESULT") if isinstance(payload, dict) else None
        msg = ""
        if isinstance(result, dict):
            msg = str(result.get("MESSAGE") or result.get("CODE") or "")
        raise RuntimeError(f"ECOS 731Y001 응답에 환율 행 없음{': ' + msg if msg else ''}")

    parsed: list[tuple[str, float, str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_time = str(row.get("TIME") or "").strip()
        raw_value = row.get("DATA_VALUE")
        if len(raw_time) != 8 or not raw_time.isdigit() or raw_value in (None, ""):
            continue
        try:
            value = float(str(raw_value).replace(",", ""))
            day = dt.datetime.strptime(raw_time, "%Y%m%d").date().isoformat()
        except Exception:
            continue
        item_name = str(row.get("ITEM_NAME1") or "원/미국달러(매매기준율)").strip()
        unit = str(row.get("UNIT_NAME") or "원").strip()
        parsed.append((day, value, item_name, unit))

    if not parsed:
        raise RuntimeError("ECOS 원/달러 일별 환율 파싱 실패")

    day, value, item_name, unit = max(parsed, key=lambda x: x[0])
    return {
        "date": day,
        "value": value,
        "item_name": item_name,
        "unit": unit,
        "stat_code": ECOS_STAT_CODE,
        "item_code": ECOS_ITEM_CODE_USD,
        "source": ECOS_API_HOME,
        "role": "한국은행 공식 일일 검증값(장중 경보 판정에는 사용하지 않음)",
    }


def fetch_usdkrw() -> dict[str, Any]:
    fx = _original_fetch_usdkrw()
    try:
        fx["ecos_official"] = fetch_ecos_usdkrw()
        fx.pop("ecos_error", None)
    except Exception as exc:
        fx["ecos_error"] = f"{type(exc).__name__}: {exc}"
    _last_fx.clear()
    _last_fx.update(fx)
    return fx


def add_event_crossing_only(events, key: str, text: str, source: str) -> None:
    """Threshold labels mean a real crossing, not simply remaining beyond a level."""
    if key.startswith("fx_1350_down:"):
        prev = _last_fx.get("prev_value")
        cur = _last_fx.get("value")
        if not isinstance(prev, (int, float)) or not isinstance(cur, (int, float)):
            return
        if not (prev > 1350 and cur <= 1350):
            return
    elif key.startswith("fx_1400_up:"):
        prev = _last_fx.get("prev_value")
        cur = _last_fx.get("value")
        if not isinstance(prev, (int, float)) or not isinstance(cur, (int, float)):
            return
        if not (prev < 1400 and cur >= 1400):
            return
    _original_add_event(events, key, text, source)


def fetch_stock_quote(code: str) -> dict[str, Any]:
    """Fetch a live/delayed Naver quote; use the HTML page as a fallback."""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; khs-korea-market-stress-watch/11.1)",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
        "Referer": "https://finance.naver.com/",
    }
    api_url = NAVER_STOCK_BASIC.format(code=code)
    try:
        r = requests.get(api_url, headers=headers, timeout=20)
        r.raise_for_status()
        row = r.json()
        if isinstance(row, dict):
            name = str(row.get("stockName") or row.get("itemName") or "").strip()
            price_raw = row.get("closePrice") or row.get("currentPrice")
            pct_raw = row.get("fluctuationsRatio") or row.get("changeRate")
            if price_raw not in (None, "") and pct_raw not in (None, ""):
                return {
                    "code": code,
                    "name": name or code,
                    "price": float(str(price_raw).replace(",", "")),
                    "change_pct": float(str(pct_raw).replace(",", "").replace("%", "")),
                    "source": NAVER_STOCK_MAIN.format(code=code),
                }
    except Exception:
        pass

    page_url = NAVER_STOCK_MAIN.format(code=code)
    r = requests.get(page_url, headers=headers, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    name_node = soup.select_one("div.wrap_company h2 a")
    price_node = soup.select_one("p.no_today .blind")
    exday = soup.select_one("p.no_exday")
    if price_node is None or exday is None:
        raise RuntimeError(f"네이버 종목시세 파싱 실패: {code}")
    price = float(price_node.get_text(strip=True).replace(",", ""))
    text = exday.get_text(" ", strip=True)
    pct_match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%", text)
    if not pct_match:
        raise RuntimeError(f"네이버 종목 등락률 파싱 실패: {code}")
    pct = float(pct_match.group(1))
    if exday.select_one("em.no_down") is not None or "하락" in text:
        pct = -pct
    elif exday.select_one("em.no_up") is not None or "상승" in text:
        pct = abs(pct)
    else:
        pct = 0.0 if "보합" in text else pct
    return {
        "code": code,
        "name": name_node.get_text(strip=True) if name_node else code,
        "price": price,
        "change_pct": pct,
        "source": page_url,
    }


def _quote_group(codes: list[str]) -> tuple[str, list[str]]:
    parts: list[str] = []
    errors: list[str] = []
    for code in codes:
        try:
            q = fetch_stock_quote(code)
            parts.append(
                f"{html.escape(str(q['name']))} <b>{q['price']:,.0f}원 ({q['change_pct']:+.2f}%)</b>"
            )
        except Exception as exc:
            parts.append(f"{code} 시세 확인 실패")
            errors.append(f"{code}: {type(exc).__name__}: {exc}")
    return " · ".join(parts), errors


def _fx_alert_direction(text: str) -> str | None:
    head = text.split("<b>알림 기준</b>", 1)[0]
    down_markers = ("원/달러 일간 급락:", "원/달러 1,350원 하단 진입:")
    up_markers = ("원/달러 일간 급등:", "원/달러 1,400원 상단 진입:")
    if any(marker in head for marker in down_markers):
        return "down"
    if any(marker in head for marker in up_markers):
        return "up"
    return None


def _impact_lines(groups: list[dict[str, Any]], direction_label: str) -> tuple[list[str], list[str]]:
    lines: list[str] = [f"<b>{direction_label}</b>"]
    errors: list[str] = []
    for group in groups:
        quote_text, quote_errors = _quote_group(list(group["codes"]))
        errors.extend(quote_errors)
        lines.append(f"• {html.escape(str(group['label']))}: {quote_text}")
        lines.append(f"  ↳ {html.escape(str(group['reason']))}")
    return lines, errors


def _append_fx_equity_context() -> None:
    if not watch.ALERT_PATH.exists():
        return
    text = watch.ALERT_PATH.read_text(encoding="utf-8").strip()
    direction = _fx_alert_direction(text)
    if direction is None or "<b>환율 → 국내주식 영향</b>" in text:
        return

    errors: list[str] = []
    if direction == "down":
        burden_groups = FX_DOWN_BURDEN
        benefit_groups = FX_DOWN_BENEFIT
        headline = "원/달러 하락 = 원화 강세"
        burden_title = "🔻 환율 하락 시 실적 부담이 커질 수 있는 기업"
        benefit_title = "🔺 환율 하락 시 비용 절감 수혜가 가능한 기업"
    else:
        burden_groups = FX_DOWN_BENEFIT
        benefit_groups = FX_DOWN_BURDEN
        headline = "원/달러 상승 = 원화 약세"
        burden_title = "🔻 환율 상승 시 비용 부담이 커질 수 있는 기업"
        benefit_title = "🔺 환율 상승 시 원화 환산 실적 수혜가 가능한 기업"

    burden_lines, burden_errors = _impact_lines(burden_groups, burden_title)
    benefit_lines, benefit_errors = _impact_lines(benefit_groups, benefit_title)
    errors.extend(burden_errors)
    errors.extend(benefit_errors)

    lines = text.splitlines()
    insert_at = next((i for i, line in enumerate(lines) if "<b>알림 기준</b>" in line), len(lines))
    additions = [
        "<b>환율 → 국내주식 영향</b>",
        f"• 방향: <b>{headline}</b>",
        "",
        *burden_lines,
        "",
        *benefit_lines,
        "",
        "• 해석 원칙: 당일 주가 등락은 환율 외 개별 재료도 포함. 환율이 직접 원인이라고 단정하는 것은 최신 기사·공시로 확인된 경우에만 적용",
        "• 최근 확인 사례: 삼양식품은 2026-09-07 원/달러 급락에 따른 실적 우려가 부각되며 장중 -7.48%; 상반기 해외매출 비중은 83%",
        "",
    ]
    lines[insert_at:insert_at] = additions

    source_block = [
        f'• <a href="{html.escape(SAMYANG_FX_NEWS, quote=True)}">삼양식품 환율·주가 실제 반응</a>',
        f'• <a href="{html.escape(FX_SECTOR_NEWS, quote=True)}">환율 하락 업종별 주가 영향</a>',
        f'• <a href="{html.escape(TRANSPORT_FX_NEWS, quote=True)}">운송업 환율·실적 영향</a>',
        f'• <a href="{html.escape(SAMYANG_IR, quote=True)}">삼양식품 공식 IR</a>',
    ]
    if "<b>원문</b>" in lines:
        src_idx = lines.index("<b>원문</b>") + 1
        for item in reversed(source_block):
            if item not in lines:
                lines.insert(src_idx, item)
    else:
        lines.extend(["", "<b>원문</b>", *source_block])

    watch.ALERT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if errors:
        with watch.ERROR_PATH.open("a", encoding="utf-8") as f:
            for err in errors:
                f.write("환율 주가 영향 시세 조회 실패: " + err + "\n")


def _append_ecos_context() -> None:
    ecos = _last_fx.get("ecos_official") if isinstance(_last_fx, dict) else None
    ecos_error = _last_fx.get("ecos_error") if isinstance(_last_fx, dict) else None

    if watch.STATUS_PATH.exists():
        try:
            status = watch.STATUS_PATH.read_text(encoding="utf-8").rstrip()
            if isinstance(ecos, dict):
                status += (
                    f"\n- 한국은행 ECOS 원/달러 공식 일일값: {ecos['value']:,.2f}원, "
                    f"기준일 {ecos['date']} · {ECOS_STAT_CODE}/{ECOS_ITEM_CODE_USD}"
                )
            elif ecos_error:
                status += f"\n- 한국은행 ECOS 환율 검증: 조회 실패({ecos_error})"
            watch.STATUS_PATH.write_text(status + "\n", encoding="utf-8")
        except Exception:
            pass

    if ecos_error:
        try:
            with watch.ERROR_PATH.open("a", encoding="utf-8") as f:
                f.write(f"한국은행 ECOS 원/달러 검증 실패: {ecos_error}\n")
        except Exception:
            pass

    if not watch.ALERT_PATH.exists():
        return
    try:
        text = watch.ALERT_PATH.read_text(encoding="utf-8").strip()
        if "원/달러" not in text:
            return
        lines = text.splitlines()
        insert_at = next((i for i, line in enumerate(lines) if "<b>원문</b>" in line), len(lines))
        additions: list[str] = []
        if isinstance(ecos, dict):
            current_date = str(_last_fx.get("date") or "")
            label = "동일 기준일 공식값" if ecos.get("date") == current_date else "최근 공식 일일값"
            additions.append(
                f"• 한국은행 ECOS {label}: {ecos['date']} {ecos['value']:,.2f}원 "
                f"({html.escape(str(ecos.get('item_name') or '원/미국달러(매매기준율)'))})"
            )
            additions.append("• 판정 역할: 장중 임계치 감지는 실시간 피드, ECOS는 공식 일일값 검증만 사용")
        elif ecos_error:
            additions.append("• 한국은행 ECOS 공식 일일값: 이번 실행 조회 실패 — 장중 경보값과 혼합하지 않음")
        if additions and not any("한국은행 ECOS" in line for line in lines):
            lines[insert_at:insert_at] = additions + [""]
        if isinstance(ecos, dict):
            ecos_link = f'• <a href="{html.escape(ECOS_API_HOME, quote=True)}">한국은행 ECOS Open API</a>'
            if ecos_link not in lines:
                lines.append(ecos_link)
        watch.ALERT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception as exc:
        try:
            with watch.ERROR_PATH.open("a", encoding="utf-8") as f:
                f.write(f"ECOS 알림 문구 보강 실패: {type(exc).__name__}: {exc}\n")
        except Exception:
            pass


watch.fetch_usdkrw = fetch_usdkrw
watch.add_event = add_event_crossing_only


def main() -> int:
    rc = v10.main()
    _append_fx_equity_context()
    _append_ecos_context()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
