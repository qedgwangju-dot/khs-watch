#!/usr/bin/env python3
"""Same-date U.S. Treasury nominal / TIPS real-yield diagnostics. No sender."""
from __future__ import annotations
import datetime as dt
import xml.etree.ElementTree as ET

import requests

BASE = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
ATOM = "http://www.w3.org/2005/Atom"
DATA = "http://schemas.microsoft.com/ado/2007/08/dataservices"


class CurveMismatch(ValueError):
    pass


def parse_feed(raw: bytes, field: str) -> dict[str, float]:
    if field not in ("BC_10YEAR", "TC_10YEAR"):
        raise ValueError("unexpected Treasury XML field")
    root = ET.fromstring(raw)
    result = {}
    for entry in root.findall(f"{{{ATOM}}}entry"):
        date = entry.find(f".//{{{DATA}}}NEW_DATE")
        value = entry.find(f".//{{{DATA}}}{field}")
        if date is None or not date.text or value is None or not value.text:
            continue
        key = date.text[:10]
        dt.date.fromisoformat(key)
        number = float(value.text)
        if not -5.0 <= number <= 25.0:
            raise CurveMismatch("invalid official interest rate")
        if key in result and result[key] != number:
            raise CurveMismatch("conflicting official interest rate")
        result[key] = number
    if not result:
        raise CurveMismatch("no official observations for " + field)
    return result


def decompose(nominal: dict, real: dict, target_date: str, reported_nominal: float) -> dict:
    dt.date.fromisoformat(target_date)
    common = sorted(set(nominal) & set(real))
    if target_date not in common:
        raise CurveMismatch(f"날짜 불일치: 명목 {max(nominal, default='없음')} / 실질 {max(real, default='없음')} / 보고 {target_date}")
    i = common.index(target_date)
    n, r = nominal[target_date], real[target_date]
    if abs(n - reported_nominal) > 0.015:
        raise CurveMismatch(f"명목금리 출처 불일치: 원천 {n:.2f}% / 본문 {reported_nominal:.2f}%")
    b = n-r
    if not -2.0 <= b <= 10.0:
        raise CurveMismatch("BEI sanity check failed")
    out = dict(date=target_date, nominal=n, real=r, bei=b,
               prev=None, real1=None, bei1=None, nominal1=None,
               five=None, real5=None, bei5=None)
    if i >= 1:
        prev=common[i-1]
        out.update(prev=prev, real1=(r-real[prev])*100,
                   nominal1=(n-nominal[prev])*100,
                   bei1=(b-(nominal[prev]-real[prev]))*100)
    if i >= 5:
        five=common[i-5]
        out.update(five=five, real5=(r-real[five])*100,
                   bei5=(b-(nominal[five]-real[five]))*100)
    return out


def classify(data: dict) -> tuple[str, str]:
    real, r1, b1, r5, b5 = (data[k] for k in ("real","real1","bei1","real5","bei5"))
    if r5 is not None and b5 is not None and r5 >= 20 and abs(b5) <= 5:
        label = "실질금리 5거래일 급등·시장 내재 물가상승률 안정"
    elif r1 is not None and b1 is not None and r1 >= 10 and abs(b1) <= 3:
        label = "실질금리 하루 급등·시장 내재 물가상승률 안정"
    elif r1 is not None and b1 is not None and r1 >= 7 and b1 >= 7:
        label = "실질금리·시장 내재 물가상승률 동반 상승"
    elif r1 is not None and b1 is not None and b1 >= 10 and abs(r1) <= 4:
        label = "시장 내재 물가상승률 주도 상승"
    elif r1 is not None and r1 <= -7:
        label = "실질금리 하락·할인율 부담 완화"
    else:
        label = "실질금리 분해 관찰"
    if real >= 3.00:
        level = "실질금리 3.00% 이상(자체 경계)"
        if r1 is not None and real-r1/100 < 3.00:
            level += "·신규 진입"
    elif real >= 2.90:
        level = "실질금리 2.90~3.00% 접근(자체 관찰선)"
    else:
        level = "실질금리 2.90% 미만"
    return label, level


def bp(v):
    return "자료 부족" if v is None else f"{v:+.0f}bp"


def build_block(target_date: str, reported_nominal: float, requester=requests) -> str:
    year = target_date[:4]
    urls = [
        f"{BASE}?data=daily_treasury_yield_curve&field_tdr_date_value={year}",
        f"{BASE}?data=daily_treasury_real_yield_curve&field_tdr_date_value={year}",
    ]
    values = []
    for url, field in zip(urls, ("BC_10YEAR", "TC_10YEAR")):
        response = requester.get(url, timeout=(7, 18), headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        values.append(parse_feed(response.content, field))
    d = decompose(values[0], values[1], target_date, reported_nominal)
    signal, level = classify(d)
    return "\n".join([
        "[실질금리·시장 내재 물가상승률]",
        f"미 재무부 공식 기준일 {d['date']} | 10년 명목 {d['nominal']:.2f}% | 10년 실질(TIPS) {d['real']:.2f}%",
        f"10년 손익분기 물가상승률(BEI=명목−실질) {d['bei']:.2f}%",
        f"직전 거래일({d['prev'] or '자료 부족'}): 명목 {bp(d['nominal1'])} · 실질 {bp(d['real1'])} · BEI {bp(d['bei1'])}",
        f"5거래일({d['five'] or '자료 부족'}~{d['date']}): 실질 {bp(d['real5'])} · BEI {bp(d['bei5'])}",
        f"판정: {signal} / {level}",
        "주의: BEI는 순수 물가 전망이 아니라 물가 위험 프리미엄·TIPS 유동성 영향이 포함된 시장 내재 지표.",
        f"공식 원천: {urls[0]} | {urls[1]}",
    ])
