from __future__ import annotations

import json
import urllib.request

import qlex_wac_ir_watch as base

UA = 'Mozilla/5.0 (compatible; AlteogenQlexWACKRW/1.0)'
_original_build_alert = base.build_alert


def usdkrw() -> tuple[float | None, str]:
    try:
        req = urllib.request.Request(
            'https://api.frankfurter.app/latest?from=USD&to=KRW',
            headers={'User-Agent': UA},
        )
        with urllib.request.urlopen(req, timeout=12) as response:
            payload = json.loads(response.read().decode('utf-8', errors='replace'))
        return float(payload['rates']['KRW']), str(payload.get('date') or '')
    except Exception:
        return None, ''


def format_krw_from_usd_m(usd_m: float, rate: float) -> str:
    eok = usd_m * rate / 100.0
    if eok >= 10000:
        jo = int(eok // 10000)
        rem = int(round(eok - jo * 10000))
        if rem:
            return f'약 {jo}조{rem:,.0f}억원'
        return f'약 {jo}조원'
    return f'약 {eok:,.0f}억원'


def build_alert(post, metrics, state) -> str:
    text = _original_build_alert(post, metrics, state)
    if metrics.cumulative_m is None:
        return text

    rate, day = usdkrw()
    if rate is None:
        return text

    cum_month = metrics.cumulative_month or metrics.month
    old = f'- **누적 추정:** 1~{cum_month}월 약 {base.fmt_usd_m(metrics.cumulative_m)}'
    new = (
        f'{old} → {format_krw_from_usd_m(metrics.cumulative_m, rate)} '
        f'(USD/KRW {rate:,.2f}, {day}, ECB 기준)'
    )
    return text.replace(old, new)


base.build_alert = build_alert


if __name__ == '__main__':
    raise SystemExit(base.main())
