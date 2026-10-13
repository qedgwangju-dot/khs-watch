#!/usr/bin/env python3
"""Interpret long-bond issuance shifts for the existing Treasury QRA alert.

Never treat broker predictions or Treasury primary-dealer questions as policy.
All confirmed auction sizes come only from an official Treasury QRA table.
"""
from __future__ import annotations
import html
import re
from datetime import datetime
from html.parser import HTMLParser

CITI_20261009 = (
    "https://www.bloomberg.com/news/articles/2026-10-09/"
    "bessent-will-likely-cut-us-long-bond-sales-next-month-says-citi"
)
MONTHS = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
          "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
RELEVANT_DEALER = re.compile(
    r"20[\s-]*year|30[\s-]*year|long[\s-]*(?:dated|end|bond)|"
    r"hyperscal|investment[\s-]*grade|corporate\s+(?:bond|debt|issuance)|"
    r"auction\s+siz|coupon\s+issuance|pension\s+fund",
    re.I,
)


class TreasuryTables(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.table = None
        self.row = None
        self.cell = None
    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.table = []
        elif tag == "tr" and self.table is not None:
            self.row = []
        elif tag in ("td","th") and self.row is not None:
            self.cell = []
    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)
    def handle_endtag(self, tag):
        if tag in ("td","th") and self.cell is not None:
            self.row.append(" ".join(" ".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            self.tables.append(self.table)
            self.table = None


def month_id(text):
    found = re.search(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[\s-]*(20\d{2}|\d{2})\b", text, re.I)
    if not found:
        return None
    year = int(found.group(2))
    if year < 100:
        year += 2000
    return f"{year:04d}-{MONTHS[found.group(1).lower()]:02d}"


def nominal_long_end_table(source: str) -> dict[str, dict[str, float]]:
    """Extract 20Y/30Y sizes from the actual official HTML auction-size table."""
    p = TreasuryTables()
    p.feed(source)
    out = {}
    for rows in p.tables:
        for i, row in enumerate(rows):
            labels = [re.sub(r"[^a-z0-9]", "", html.unescape(x).lower()) for x in row]
            if "20year" not in labels or "30year" not in labels:
                continue
            i20, i30 = labels.index("20year"), labels.index("30year")
            for values in rows[i+1:]:
                if len(values) <= max(i20, i30):
                    continue
                month = month_id(" ".join(values[:2]))
                if month is None:
                    continue
                try:
                    n20 = float(re.sub(r"[,$\s]", "", values[i20]))
                    n30 = float(re.sub(r"[,$\s]", "", values[i30]))
                except ValueError:
                    continue
                if not (0 <= n20 <= 100 and 0 <= n30 <= 100):
                    continue
                out[month] = {"20y": n20, "30y": n30}
    return dict(sorted(out.items()))


def summarize_long_end_supply(table: dict, fx: float | None = None) -> dict:
    """Requires six sequential months; otherwise report unavailable, never infer."""
    keys = sorted(table)
    if len(keys) < 6:
        return {"available": False, "reason": "공식 QRA 6개월 만기별 발행표 직접 추출 불가"}
    keys = keys[-6:]
    prev, future = keys[:3], keys[3:]
    def next_month(key):
        d = datetime.strptime(key + "-01", "%Y-%m-%d")
        y, m = d.year, d.month
        return f"{y+1}-01" if m == 12 else f"{y}-{m+1:02d}"
    if any(next_month(a) != b for a,b in zip(keys,keys[1:])):
        return {"available": False, "reason": "발행표 6개월 연속성 검증 실패"}
    before = sum(table[k][tenor] for k in prev for tenor in ("20y","30y"))
    after = sum(table[k][tenor] for k in future for tenor in ("20y","30y"))
    delta = round(after - before, 3)
    increments = {tenor:[round(table[future[i]][tenor] - table[prev[i]][tenor],3)
                        for i in range(3)] for tenor in ("20y","30y")}
    return {"available": True,"before_bn":before,"after_bn":after,
            "delta_bn":delta,"prior_months":prev,"next_months":future,
            "rows":{m:table[m] for m in keys},"per_auction_bn":increments,
            "citi_base_case_matches":all(all(abs(x+3) < 0.01 for x in changes)
                                         for changes in increments.values()),
            "fx":fx}


def dealer_agenda_mentions_long_end(text: str) -> bool:
    """Requiring inspected official document text prevents headline-only alerts."""
    return bool(RELEVANT_DEALER.search(text or ""))


def expectation_comparison(supply: dict) -> str:
    if not supply.get("available"):
        return "• 20·30년물 공식 발행표 검증 보류 — Citi 전망을 확정 정책으로 치환하지 않음"
    diff = supply["delta_bn"]
    before = supply["before_bn"]
    after = supply["after_bn"]
    if diff < 0:
        result = "장기채 예정 공급 축소(확정 QRA 발행계획)"
    elif diff > 0:
        result = "장기채 예정 공급 확대(확정 QRA 발행계획)"
    else:
        result = "장기채 예정 공급 유지(확정 QRA 발행계획)"
    match = ("Citi의 회당 30억달러 축소 시나리오와 만기별 일치"
             if supply["citi_base_case_matches"] else
             "Citi의 회당 30억달러 축소 시나리오와 불일치 또는 일부만 부합")
    krw_text = ""
    if supply.get("fx"):
        won = abs(diff) * 1_000_000_000 * float(supply["fx"])
        jo = int(won // 1_000_000_000_000)
        eok = round((won - jo * 1_000_000_000_000) / 100_000_000)
        if eok >= 10000:
            jo, eok = jo + 1, eok - 10000
        krw_text = f" (변화 원화 약 {jo:,}조{eok:,.0f}억원)"
    return (f"• 공식 20·30년물 3개월 합계: {before*10:,.0f}억달러 → "
            f"{after*10:,.0f}억달러 (변화 {diff*10:+,.0f}억달러){krw_text}; {result}\n"
            f"• Citi 전망 대비: {match}. 단기국채 대체액은 공식자료로 별도 확정")
