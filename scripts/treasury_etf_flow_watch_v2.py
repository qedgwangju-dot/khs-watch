#!/usr/bin/env python3
import re
import requests
from bs4 import BeautifulSoup

import treasury_etf_flow_watch as base
import treasury_etf_flow_watch_readable as report

_original_get_ishares = base.get_ishares
_original_send_exact_telegram = report.send_exact_telegram


def robust_get_ishares(ticker, meta):
    row = _original_get_ishares(ticker, meta)
    if row.get("nav_change_pct") is not None:
        return row

    response = requests.get(meta["url"], headers=base.HEADERS, timeout=35)
    response.raise_for_status()
    text = BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)

    pattern = (
        r"1 Day NAV Change as of [A-Za-z]{3} \d{1,2}, \d{4}"
        r".*?\(([-+]?\d+(?:\.\d+)?)%\)"
    )
    match = re.search(pattern, text)
    if match:
        row["nav_change_pct"] = float(match.group(1))
    return row


def _extract_bp(text, tenor):
    m = re.search(rf"• {tenor}년:\s*[\d.]+%\s*\|\s*[↑↓→·]\s*([+-]?\d+)bp", text)
    return int(m.group(1)) if m else None


def fixed_curve_label(text):
    d2 = _extract_bp(text, 2)
    d10 = _extract_bp(text, 10)
    if d2 is None or d10 is None:
        return None

    if d2 > 0 and d10 > 0:
        if d2 > d10:
            return "베어 플래트닝 = 금리↑ + 단기금리가 더 크게↑ → Fed 재인상·고금리 장기화 우려"
        if d10 > d2:
            return "베어 스티프닝 = 금리↑ + 장기금리가 더 크게↑ → 재정·국채 공급·인플레이션·기간프리미엄 부담"
    elif d2 < 0 and d10 < 0:
        if abs(d2) > abs(d10):
            return "불 스티프닝 = 금리↓ + 단기금리가 더 크게↓ → Fed 인하·경기둔화 기대"
        if abs(d10) > abs(d2):
            return "불 플래트닝 = 금리↓ + 장기금리가 더 크게↓ → 장기 성장·물가 기대 약화"

    return "혼합 이동 = 단기·장기 금리가 같은 방향으로 정렬되지 않음 → 한 가지 커브 용어로 억지 분류하지 않고 개별 원인 확인"


def send_with_fixed_curve_language(text):
    label = fixed_curve_label(text)
    if label and "[금리 구조 쉬운 해석]" not in text:
        marker = "\n[방향성 판독]"
        block = f"\n[금리 구조 쉬운 해석]\n• {label}\n"
        if marker in text:
            text = text.replace(marker, block + marker, 1)
        else:
            text += block
    return _original_send_exact_telegram(text)


base.get_ishares = robust_get_ishares
report.send_exact_telegram = send_with_fixed_curve_language

if __name__ == "__main__":
    report.main()
