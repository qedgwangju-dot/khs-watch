#!/usr/bin/env python3
import datetime as dt
import hashlib
import html
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

import treasury_etf_flow_watch as base

KST = ZoneInfo("Asia/Seoul")

FUNDS = {
    "SHY": {"label": "미 국채 1~3년", "url": "https://www.ishares.com/us/products/239452/ishares-13-year-treasury-bond-etf"},
    "IEF": {"label": "미 국채 7~10년", "url": "https://www.ishares.com/us/products/239456/ishares-7-10-year-treasury-bond-etf"},
    "TLT": {"label": "미 국채 20년 이상", "url": "https://www.ishares.com/us/products/239454/ishares-20-year-treasury-bond-etf"},
    "LQD": {"label": "미 투자등급 회사채", "url": "https://www.ishares.com/us/products/239566/ishares-iboxx-investment-grade-corporate-bond-etf"},
    "HYG": {"label": "미 고수익 회사채", "url": "https://www.ishares.com/us/products/239565/ishares-iboxx-high-yield-corporate-bond-etf"},
}


def arrow(v):
    if v is None:
        return "·"
    return "↑" if v > 0 else "↓" if v < 0 else "→"


def flow_word(v):
    if v is None:
        return "기준점 수집 중"
    return "순유입" if v > 0 else "순유출" if v < 0 else "중립"


def parse_oas_snapshot(meta):
    r = requests.get(meta["url"], headers=base.HEADERS, timeout=35)
    r.raise_for_status()
    text = BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    m = re.search(
        r"Option Adjusted Spread\s+([0-9,.]+)\s*bps\s+as of\s+([A-Za-z]{3}\s+\d{1,2},\s+\d{4})",
        text,
        re.I,
    )
    if not m:
        return None
    return {
        "value": float(m.group(1).replace(",", "")),
        "date": dt.datetime.strptime(m.group(2), "%b %d, %Y").date().isoformat(),
    }


def parse_oas_bps(meta):
    snap = parse_oas_snapshot(meta)
    return None if not snap else snap["value"]


def get_curve_pair():
    year = dt.datetime.now(KST).year
    url = (
        "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
        f"?data=daily_treasury_yield_curve&field_tdr_date_value={year}"
    )
    r = requests.get(url, headers=base.HEADERS, timeout=35)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    ns_d = "http://schemas.microsoft.com/ado/2007/08/dataservices"
    rows = []
    for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
        def val(name):
            node = entry.find(f".//{{{ns_d}}}{name}")
            return None if node is None or node.text in (None, "") else node.text
        d = val("NEW_DATE")
        if not d:
            continue
        rows.append({
            "date": d[:10],
            "2Y": float(val("BC_2YEAR")) if val("BC_2YEAR") else None,
            "10Y": float(val("BC_10YEAR")) if val("BC_10YEAR") else None,
            "30Y": float(val("BC_30YEAR")) if val("BC_30YEAR") else None,
        })
    rows.sort(key=lambda x: x["date"])
    if not rows:
        raise RuntimeError("Treasury yield curve returned no rows")
    return rows[-1], rows[-2] if len(rows) >= 2 else None


def bp(cur, prev, key):
    if not prev or cur.get(key) is None or prev.get(key) is None:
        return None
    return (cur[key] - prev[key]) * 100.0


def fmt_bp(v):
    if v is None:
        return "비교불가"
    return f"{arrow(v)} {v:+.0f}bp"


def curve_regime(cur, prev):
    if not prev:
        return "판정 대기", "직전 거래일 자료 부족", None, None
    d2, d10, d30 = bp(cur, prev, "2Y"), bp(cur, prev, "10Y"), bp(cur, prev, "30Y")
    s210_now = (cur["10Y"] - cur["2Y"]) * 100
    s210_prev = (prev["10Y"] - prev["2Y"]) * 100
    ds210 = s210_now - s210_prev
    s1030_now = (cur["30Y"] - cur["10Y"]) * 100
    s1030_prev = (prev["30Y"] - prev["10Y"]) * 100
    ds1030 = s1030_now - s1030_prev

    if d2 > 0 and d10 > 0 and ds210 < 0:
        name = "베어 플래트닝"
        easy = "금리↑ + 단기금리 상승폭이 더 큼 → Fed 고금리 장기화·추가 긴축 위험을 더 반영하는 패턴"
    elif d2 > 0 and d10 > 0 and ds210 > 0:
        name = "베어 스티프닝"
        easy = "금리↑ + 장기금리 상승폭이 더 큼 → 재정·국채 공급·인플레이션·기간프리미엄 부담이 커지는 패턴"
    elif d2 < 0 and d10 < 0 and ds210 > 0:
        name = "불 스티프닝"
        easy = "금리↓ + 단기금리 하락폭이 더 큼 → Fed 인하·경기둔화 기대를 더 반영하는 패턴"
    elif d2 < 0 and d10 < 0 and ds210 < 0:
        name = "불 플래트닝"
        easy = "금리↓ + 장기금리 하락폭이 더 큼 → 장기 성장·물가 기대 약화를 더 반영하는 패턴"
    else:
        name = "커브 트위스트·혼조"
        easy = "2년·10년 금리가 한 방향으로 정렬되지 않음 → Fed와 장기 재정·성장 요인 분리 확인"

    if ds1030 > 0.5:
        back = "10년-30년 금리차 확대 → 30년물이 상대적으로 더 약함 → 재정·장기채 공급·기간프리미엄 부담 강화"
    elif ds1030 < -0.5:
        back = "10년-30년 금리차 축소 → 30년물이 상대적으로 덜 약함/더 강함 → 뒷단 재정·장기채 공급 압력 상대 완화"
    else:
        back = "10년-30년 금리차 변화 제한 → 뒷단 재정·장기채 공급 압력 추가 변화 제한"

    front_fed = d2 > 0 and d10 > 0 and d2 > d10
    back_fiscal = d30 > d10 and d30 > 0
    if front_fed and not back_fiscal:
        driver = "오늘의 주도축: 앞단 정책금리 기대 압력이 상대적으로 큰 패턴 → Fed 고금리 장기화·추가 긴축 우려 후보(원인 확정 아님)"
    elif back_fiscal and not front_fed:
        driver = "오늘의 주도축: 뒷단 기간프리미엄 압력이 상대적으로 큰 패턴 → 재정·국채 공급 부담 후보(원인 확정 아님)"
    elif front_fed and back_fiscal:
        driver = "오늘의 주도축: 앞단 정책금리 기대와 뒷단 기간프리미엄 압력이 동시에 커지는 패턴(원인 확정 아님)"
    else:
        driver = "오늘의 주도축: 금리곡선만으로 Fed·재정 중 한쪽 원인을 확정하기 어려움"
    return name, easy, (s210_now, s210_prev, ds210), (s1030_now, s1030_prev, ds1030, back, driver)


def etf_interpretation(ticker, price, flow):
    if ticker == "SHY":
        return "단기채 피신 여부 판정 대기" if flow is None else ("짧은 미 국채에서 이자를 받으며 기다리는 방어자금 유입" if flow > 0 else "단기 안전자산 자금 일부 이탈")
    if ticker == "IEF":
        return "중기채 방향 판정 대기" if flow is None else ("7~10년 국채로 실제 자금 유입 → 금리하락 베팅이 중기물로 이동" if flow > 0 else "10년물 금리하락 확신 약화 → 중기채 자금 이탈")
    if ticker == "TLT":
        if flow is None:
            return "장기채 방향 판정 대기"
        if price is not None and price > 0 and flow > 0:
            return "가격↑ + 자금↑ → 장기금리 하락에 실제 돈까지 베팅, 장기채 강세 확인"
        if price is not None and price > 0 and flow < 0:
            return "가격↑ + 자금↓ → 반등 매도·신규 장기매수 확신 부족"
        if price is not None and price < 0 and flow > 0:
            return "가격↓ + 자금↑ → 장기금리 고점에 선행 베팅하는 저가매수"
        if price is not None and price < 0 and flow < 0:
            return "가격↓ + 자금↓ → 장기채 회피"
        return "장기채 방향 혼조"
    if ticker == "LQD":
        if flow is None:
            return "투자등급 회사채 방향 판정 대기"
        if price is not None and price < 0 and flow < 0:
            return "가격↓ + 자금↓ → 우량 회사채에서도 위험 축소, 품질 선호 강화"
        return "투자등급 회사채 자금 유입" if flow > 0 else "우량 회사채 노출 축소·신용위험 경계"
    if ticker == "HYG":
        if flow is None:
            return "고수익 회사채 방향 판정 대기"
        if price is not None and price < 0 and flow < 0:
            return "가격↓ + 자금↓ → 위험선호 약화가 가격·자금에서 동시에 확인"
        if price is not None and price > 0 and flow < 0:
            return "가격↑ + 자금↓ → 가격은 버티지만 위험자금이 먼저 이탈하는 초기 경계"
        return "고위험 신용자산 선호 회복" if flow > 0 else "고위험 회사채 회피·위험선호 약화"
    return ""


def treasury_class(results, curve):
    shy, ief, tlt = [results[x].get("flow_usd") for x in ("SHY", "IEF", "TLT")]
    if None in (shy, ief, tlt):
        return "국채 Fund Flow 판정 대기", "기준점 부족으로 국채 만기 이동 판정 대기"
    if curve["30Y"] >= 5.30:
        return "장기채 위험 확대", "30년물 5.30% 이상 → 장기채·고밸류 할인율 부담 확대"
    if shy > 0 and ief <= 0 and tlt <= 0:
        return "단기채 피신·방어적", "SHY 유입 + IEF/TLT 이탈 → 장기금리 하락보다 짧은 만기 이자 선호"
    if ief > 0 and tlt > 0 and (results["TLT"].get("nav_change_pct") or 0) > 0:
        return "장기채 로테이션 확인", "IEF 유입 + TLT 가격·자금 동반 상승 → 실제 자금이 중·장기 만기로 이동"
    if ief > 0 and tlt > 0:
        return "중·장기채 저가매수", "IEF·TLT 동시 유입 → 장기금리 고점 베팅 일부 시작"
    return "국채 내부 혼조", "SHY·IEF·TLT 자금이 한 방향으로 정렬되지 않음"


def credit_class(results, prev_rows):
    lqd, hyg = results["LQD"].get("flow_usd"), results["HYG"].get("flow_usd")
    lp, hp = results["LQD"].get("nav_change_pct"), results["HYG"].get("nav_change_pct")
    loas, hoas = results["LQD"].get("oas_bps"), results["HYG"].get("oas_bps")
    ploas = (prev_rows.get("LQD") or {}).get("oas_bps")
    phoas = (prev_rows.get("HYG") or {}).get("oas_bps")
    ldoas = None if loas is None or ploas is None else loas - float(ploas)
    hdoas = None if hoas is None or phoas is None else hoas - float(phoas)

    if lqd is None or hyg is None:
        return "신용 Fund Flow 판정 대기", "LQD·HYG 첫 기준점 확보 중", ldoas, hdoas

    # 신용스프레드는 실제 위험가격이므로 대규모 OAS 확대를 ETF 자금유입만으로 상쇄하지 않는다.
    if hdoas is not None and hdoas >= 10:
        if hyg < 0 and (hp or 0) < 0:
            return (
                "신용위험 확대 확인",
                f"HYG 가격↓ + 자금↓ + OAS {hdoas:+.1f}bp 급확대 → 가격·수급·신용에서 위험회피가 동시에 확인",
                ldoas, hdoas,
            )
        if hyg < 0:
            return (
                "신용위험 경계 강화",
                f"HYG 자금유출 + OAS {hdoas:+.1f}bp 급확대 → 신용위험 가격이 빠르게 악화",
                ldoas, hdoas,
            )
        return (
            "신용위험 경계 강화",
            f"HYG OAS {hdoas:+.1f}bp 급확대 → 신용위험 가격은 악화. HYG 자금은 유입이라 전면 위험회피 확정은 아님",
            ldoas, hdoas,
        )

    if hdoas is not None and hdoas >= 5:
        if hyg < 0:
            return (
                "신용위험 경계 강화",
                f"HYG 자금유출 + OAS {hdoas:+.1f}bp 확대 → 위험회피가 수급과 신용가격에서 동시 확인",
                ldoas, hdoas,
            )
        return (
            "신용가격 악화·자금흐름 혼조",
            f"HYG OAS {hdoas:+.1f}bp 확대에도 자금은 유입 → 신용가격 악화와 저가매수 흐름이 엇갈림",
            ldoas, hdoas,
        )

    if lqd < 0 and hyg < 0:
        if (ldoas is None or abs(ldoas) < 5) and (hdoas is None or abs(hdoas) < 5):
            return "품질 선호·선제적 위험축소", "LQD·HYG 자금은 빠지지만 OAS 급등은 아직 없음 → 신용위기보다 자금이 먼저 방어적으로 이동", ldoas, hdoas
        return "회사채 위험축소", "LQD·HYG 동반 유출 → 기업 신용위험 노출 축소", ldoas, hdoas
    if lqd > 0 and hyg < 0:
        return "우량 신용만 선호", "LQD 유입·HYG 유출 → 회사채 안에서도 투자등급으로 품질 이동", ldoas, hdoas
    if lqd > 0 and hyg > 0:
        if (ldoas is None or ldoas <= 0) and (hdoas is None or hdoas <= 0):
            return "신용 위험선호 회복 확인", "LQD·HYG 동반 유입 + OAS 안정/축소 → 자금과 신용가격이 함께 개선", ldoas, hdoas
        return "자금유입·신용가격 혼조", "LQD·HYG 자금은 유입됐지만 OAS가 축소되지 않아 위험선호 회복 확인은 보류", ldoas, hdoas
    return "신용시장 혼조", "LQD·HYG 방향이 엇갈림", ldoas, hdoas


def overall_class(t_head, c_head, results):
    shy = results["SHY"].get("flow_usd")
    lqd = results["LQD"].get("flow_usd")
    hyg = results["HYG"].get("flow_usd")
    if None not in (shy, lqd, hyg) and shy > 0 and lqd < 0 and hyg < 0:
        return "방어적·품질 선호 강화", "회사채에서 빠진 자금이 안전한 미 국채, 특히 짧은 만기로 이동하는 품질 이동"
    if "신용위험 확대 확인" in c_head:
        return "위험회피 강화", "신용위험이 자금흐름을 넘어 가격·스프레드까지 번지는 단계"
    if ("신용위험 경계" in c_head or "신용가격 악화" in c_head) and "장기채 위험 확대" in t_head:
        return (
            "금리·신용 위험경계 강화",
            "장기금리 스트레스와 신용스프레드 악화가 동시에 확인. 다만 ETF 자금이 전면 유출로 정렬된 것은 아니어서 전면 위험회피 확정 단계는 아님",
        )
    if "신용위험 경계" in c_head or "신용가격 악화" in c_head:
        return "신용 위험경계 강화", "신용스프레드 악화가 확인됐지만 자금흐름은 전면 위험회피로 정렬되지 않음"
    if "위험선호 회복 확인" in c_head and "장기채 로테이션" in t_head:
        return "위험선호·금리하락 베팅 동시 회복", "중·장기 국채와 회사채로 자금이 함께 복귀"
    return "혼조·추가 확인", "국채 만기 이동과 회사채 위험선호가 아직 완전히 같은 방향으로 정렬되지 않음"


def fmt_html(chunk):
    out = []
    for line in chunk.splitlines():
        e = html.escape(line, quote=False)
        bold = (
            line == "[오늘의 결론]"
            or line.startswith("전체 자금 방향:")
            or line.startswith("ETF 자금 방향:")
            or line.startswith("신용자금 방향:")
            or line.startswith("• 현재 형태:")
            or line.startswith("• 오늘의 주도축:")
            or line.startswith("• 신용 위험:")
        )
        out.append(f"<b>{e}</b>" if bold else e)
    return "\n".join(out)


def send_exact(text):
    token = (base.os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_id = (base.os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    expected = (base.os.getenv("EXPECTED_TELEGRAM_BOT_USERNAME") or "khs8879887988798879_bot").strip().lstrip("@")
    if not token or not chat_id:
        raise RuntimeError("Telegram secrets missing")
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getMe", timeout=25) as r:
        ident = json.loads(r.read().decode("utf-8"))
    actual = str((ident.get("result") or {}).get("username") or "")
    if not ident.get("ok") or actual.lower() != expected.lower():
        raise RuntimeError(f"Wrong Telegram bot: expected @{expected}, got @{actual or 'unknown'}")
    chunks, cur = [], ""
    for para in text.split("\n\n"):
        cand = para if not cur else cur + "\n\n" + para
        if len(cand) <= 3800:
            cur = cand
        else:
            if cur:
                chunks.append(cur)
            cur = para
    if cur:
        chunks.append(cur)
    ids = []
    for chunk in chunks:
        payload = urllib.parse.urlencode({"chat_id": chat_id, "text": fmt_html(chunk), "parse_mode": "HTML", "disable_web_page_preview": "true"}).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=25) as r:
            res = json.loads(r.read().decode("utf-8"))
        if not res.get("ok"):
            raise RuntimeError(f"Telegram rejected: {res}")
        ids.append((res.get("result") or {}).get("message_id"))
    return actual, ids


def main():
    state = base.load_state()
    state.setdefault("history", {})
    now = dt.datetime.now(KST)
    event_name = os.getenv("GITHUB_EVENT_NAME", "").strip()
    if event_name == "workflow_run":
        minute_of_day = now.hour * 60 + now.minute
        if not (8 * 60 + 20 <= minute_of_day <= 15 * 60 + 30):
            print(f"treasury_fallback_noop=true kst={now:%H:%M} reason=outside_0820_1530")
            return
    fx = base.get_usdkrw()
    curve, prev_curve = get_curve_pair()
    results, prev_rows = {}, {}

    for ticker, meta in FUNDS.items():
        cur = base.get_ishares(ticker, meta)
        hist = list(state["history"].get(ticker, []))
        prev = base.previous_snapshot(hist, cur["date"])
        prev_rows[ticker] = prev
        if cur.get("nav_change_pct") is None and prev and prev.get("nav") not in (None, 0):
            try:
                cur["nav_change_pct"] = (cur["nav"] / float(prev["nav"]) - 1.0) * 100.0
                cur["nav_change_source"] = "official_nav_derived"
            except Exception:
                pass
        if ticker in ("LQD", "HYG"):
            try:
                oas_snap = parse_oas_snapshot(meta)
                cur["oas_bps"] = None if not oas_snap else oas_snap["value"]
                cur["oas_date"] = None if not oas_snap else oas_snap["date"]
            except Exception:
                cur["oas_bps"] = None
                cur["oas_date"] = None
        flow = base.compute_flow(cur, hist)
        cur["flow_usd"] = flow
        hist = base.upsert_history(hist, cur, flow)
        state["history"][ticker] = hist
        cur["flow_5d_usd"] = base.last_n_flows(hist, 5)
        results[ticker] = cur

    fund_dates = {ticker: results[ticker].get("date") for ticker in FUNDS}
    unique_fund_dates = {d for d in fund_dates.values() if d}
    component_date_mismatch = {
        ticker: {
            "nav_date": results[ticker].get("nav_date"),
            "shares_date": results[ticker].get("shares_date"),
        }
        for ticker in FUNDS
        if results[ticker].get("nav_date") != results[ticker].get("shares_date")
    }
    missing_oas = [ticker for ticker in ("LQD", "HYG") if results[ticker].get("oas_bps") is None]
    oas_date_mismatch = {
        ticker: {
            "fund_date": results[ticker].get("date"),
            "oas_date": results[ticker].get("oas_date"),
        }
        for ticker in ("LQD", "HYG")
        if results[ticker].get("oas_date") != results[ticker].get("date")
    }
    curve_missing = [tenor for tenor in ("2Y", "10Y", "30Y") if curve.get(tenor) is None]
    if len(unique_fund_dates) != 1 or curve.get("date") not in unique_fund_dates:
        print(json.dumps({
            "report_withheld": "source_date_mismatch",
            "treasury_date": curve.get("date"),
            "fund_dates": fund_dates,
        }, ensure_ascii=False))
        return
    if component_date_mismatch:
        print(json.dumps({
            "report_withheld": "fund_component_date_mismatch",
            "details": component_date_mismatch,
        }, ensure_ascii=False))
        return
    if missing_oas:
        print(json.dumps({
            "report_withheld": "credit_oas_missing",
            "missing": missing_oas,
            "fund_dates": fund_dates,
        }, ensure_ascii=False))
        return
    if oas_date_mismatch:
        print(json.dumps({
            "report_withheld": "credit_oas_date_mismatch",
            "details": oas_date_mismatch,
        }, ensure_ascii=False))
        return
    if curve_missing:
        print(json.dumps({
            "report_withheld": "treasury_curve_incomplete",
            "missing": curve_missing,
            "treasury_date": curve.get("date"),
        }, ensure_ascii=False))
        return

    t_head, t_reason = treasury_class(results, curve)
    c_head, c_reason, ldoas, hdoas = credit_class(results, prev_rows)
    o_head, o_reason = overall_class(t_head, c_head, results)
    regime, regime_easy, s210, s1030 = curve_regime(curve, prev_curve)
    d2, d10, d30 = bp(curve, prev_curve, "2Y"), bp(curve, prev_curve, "10Y"), bp(curve, prev_curve, "30Y")
    gap30 = (5.30 - curve["30Y"]) * 100

    lines = [
        "[미 국채·회사채 ETF Fund Flow — 방향성·신용·수익률곡선 일일 보고]",
        f"조회시각(KST): {now:%Y-%m-%d %H:%M:%S}",
        f"환율: 1달러={fx['rate']:,.2f}원 | 기준 {fx.get('date') or '최신'}",
        "",
        "[한눈에 보기]",
        f"전체 자금 방향: {o_head}",
        f"→ {o_reason}",
        f"ETF 자금 방향: {t_head}",
        f"→ {t_reason}",
        f"신용자금 방향: {c_head}",
        f"→ {c_reason}",
        f"금리 구조: {regime}",
        f"→ {regime_easy}",
        "",
        "[미 국채 ETF]",
    ]

    for ticker in ("SHY", "IEF", "TLT"):
        r = results[ticker]
        p, flow, flow5 = r.get("nav_change_pct"), r.get("flow_usd"), r.get("flow_5d_usd")
        price = "확인불가" if p is None else f"{arrow(p)} {p:+.2f}%"
        sec = "확인불가" if r.get("sec_yield") is None else f"{r['sec_yield']:.2f}%"
        lines += [
            f"{ticker} ({r['label']}) — {r['date']}",
            f"• 가격: NAV ${r['nav']:.2f} | 1일 {price} | 30일 SEC {sec}",
            f"• 일간 자금: {arrow(flow)} {flow_word(flow)} {base.fmt_usd_flow(flow)} ({base.fmt_krw(flow, fx['rate'])})",
            f"• 최근 5회: {arrow(flow5)} {base.fmt_usd_flow(flow5)} ({base.fmt_krw(flow5, fx['rate'])})",
            f"• 해석: {etf_interpretation(ticker, p, flow)}",
            "",
        ]

    lines.append("[회사채 ETF — 위험선호 확인]")
    for ticker in ("LQD", "HYG"):
        r = results[ticker]
        p, flow, flow5 = r.get("nav_change_pct"), r.get("flow_usd"), r.get("flow_5d_usd")
        price = "확인불가" if p is None else f"{arrow(p)} {p:+.2f}%"
        sec = "확인불가" if r.get("sec_yield") is None else f"{r['sec_yield']:.2f}%"
        oas = "확인불가" if r.get("oas_bps") is None else f"{r['oas_bps']:.1f}bp"
        doas = ldoas if ticker == "LQD" else hdoas
        if doas is None:
            doas_text = "비교 대기"
        elif abs(doas) < 0.05:
            doas_text = "→ 0.0bp"
        else:
            doas_text = f"{arrow(doas)} {doas:+.1f}bp"
        lines += [
            f"{ticker} ({r['label']}) — {r['date']}",
            f"• 가격: NAV ${r['nav']:.2f} | 1일 {price} | 30일 SEC {sec}",
            f"• 일간 자금: {arrow(flow)} {flow_word(flow)} {base.fmt_usd_flow(flow)} ({base.fmt_krw(flow, fx['rate'])})",
            f"• 최근 5회: {arrow(flow5)} {base.fmt_usd_flow(flow5)} ({base.fmt_krw(flow5, fx['rate'])})",
            f"• 포트폴리오 OAS: {oas} | 직전 대비 {doas_text}",
            f"• 해석: {etf_interpretation(ticker, p, flow)}",
            "",
        ]

    lines += [
        "[신용위험 판독]",
        f"• 신용 위험: {c_head}",
        f"→ {c_reason}",
        "• 핵심 경보: HYG 가격↓ + Fund Flow↓ + OAS↑ = 위험회피가 가격·수급·신용에서 동시에 확인",
        "• 반대 신호: LQD/HYG 자금↑ + OAS↓ = 회사채 위험선호 회복",
        "",
        "[미 국채 금리 방향]",
        f"기준: {curve['date']} | 직전: {prev_curve['date'] if prev_curve else '없음'}",
        f"• 2년: {curve['2Y']:.2f}% | {fmt_bp(d2)}",
        f"• 10년: {curve['10Y']:.2f}% | {fmt_bp(d10)}",
        f"• 30년: {curve['30Y']:.2f}% | {fmt_bp(d30)}",
    ]
    if s210:
        lines.append(f"• 2년-10년 금리차: {s210[1]:.0f}bp → {s210[0]:.0f}bp ({s210[2]:+.0f}bp)")
    if s1030:
        lines.append(f"• 10년-30년 금리차: {s1030[1]:.0f}bp → {s1030[0]:.0f}bp ({s1030[2]:+.0f}bp)")
        lines.append(f"• 뒷단 해석: {s1030[3]}")
        lines.append(f"• {s1030[4]}")
    lines += [
        f"• 30년 5.30% 경계: {'위험구간 진입' if curve['30Y'] >= 5.30 else f'아직 {gap30:.0f}bp 아래'}",
        "",
        "[수익률곡선 고정 해석]",
        f"• 현재 형태: {regime}",
        f"• 쉬운 해석: {regime_easy}",
        "• 베어 플래트닝 = 금리↑ + 단기금리가 더 크게↑ → Fed 재인상·고금리 장기화 우려",
        "• 베어 스티프닝 = 금리↑ + 장기금리가 더 크게↑ → 재정·국채 공급·인플레이션·기간프리미엄 부담",
        "• 불 스티프닝 = 금리↓ + 단기금리가 더 크게↓ → Fed 인하·경기둔화 기대",
        "• 불 플래트닝 = 금리↓ + 장기금리가 더 크게↓ → 장기 성장·물가 기대 약화",
        "",
        "[투자 언어로 번역]",
        f"• 국채: {t_reason}",
        f"• 회사채: {c_reason}",
        f"• 전체: {o_reason}",
        "• 읽는 순서: SHY·IEF·TLT로 만기 이동 → LQD·HYG로 기업 신용위험 → OAS로 실제 신용악화 여부 확인",
        "",
        "[오늘의 결론]",
        f"전체 자금 방향: {o_head}",
        f"ETF 자금 방향: {t_head}",
        f"신용자금 방향: {c_head}",
        f"금리 구조: {regime}",
        f"→ {o_reason}",
        "",
        "자금흐름 산식: iShares 공식 발행좌수 변화 × 해당일 NAV. LQD·HYG 첫 기준점만 있을 때는 방향을 억지 판정하지 않음.",
        "신용스프레드: iShares 공식 LQD·HYG 포트폴리오 Option Adjusted Spread를 일별 저장해 직전 대비 계산.",
        "출처: iShares 공식 SHY·IEF·TLT·LQD·HYG, U.S. Treasury, 환율 교차자료",
    ]

    text = "\n".join(lines)
    (base.OUT / "treasury_etf_flow_telegram.txt").write_text(text + "\n", encoding="utf-8")
    (base.OUT / "treasury_etf_flow_status.md").write_text("```\n" + text + "\n```\n", encoding="utf-8")

    fingerprint_payload = {
        "curve_date": curve["date"],
        "curve": {k: curve.get(k) for k in ("2Y", "10Y", "30Y")},
        "funds": {
            ticker: {
                "date": results[ticker].get("date"),
                "nav": results[ticker].get("nav"),
                "shares": results[ticker].get("shares"),
                "flow_usd": results[ticker].get("flow_usd"),
                "oas_bps": results[ticker].get("oas_bps"),
                "oas_date": results[ticker].get("oas_date"),
            }
            for ticker in ("SHY", "IEF", "TLT", "LQD", "HYG")
        },
    }
    data_fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    last_delivery = state.get("last_delivery") or {}
    if (
        os.getenv("GITHUB_EVENT_NAME", "").strip() != "workflow_dispatch"
        and last_delivery.get("data_fingerprint") == data_fingerprint
    ):
        base.save_state(state)
        print(
            "duplicate_delivery_suppressed=true "
            f"treasury_date={curve['date']} fingerprint={data_fingerprint[:12]}"
        )
        return

    username, ids = send_exact(text)
    state["last_delivery"] = {
        "at_kst": now.isoformat(timespec="seconds"), "bot_username": username, "message_ids": ids,
        "overall": o_head, "treasury_flow": t_head, "credit_flow": c_head, "curve_regime": regime,
        "treasury_date": curve["date"], "format": "treasury-credit-ishares-oas-v2",
        "data_fingerprint": data_fingerprint,
    }
    base.save_state(state)
    print(f"telegram_delivery_confirmed=true bot=@{username} message_ids={ids} overall={o_head} treasury={t_head} credit={c_head} curve={regime} fingerprint={data_fingerprint[:12]}")


if __name__ == "__main__":
    main()
