#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import re
import urllib.parse

import disaster_reconstruction_watch as base

KST = base.KST

_prev_phase_lines = base.phase_lines
_prev_build_alert = base.build_alert

FX_CODES = {
    'USD': ('미국달러', '달러'),
    'EUR': ('유로',),
    'GBP': ('파운드', '영국파운드'),
    'JPY': ('엔', '엔화'),
    'NPR': ('네팔루피', '네팔 루피'),
    'CNY': ('위안', '위안화'),
    'CHF': ('스위스프랑', '스위스 프랑'),
    'SGD': ('싱가포르달러', '싱가포르 달러'),
    'AUD': ('호주달러', '호주 달러'),
    'CAD': ('캐나다달러', '캐나다 달러'),
    'AED': ('UAE디르함', '디르함'),
}

EN_MULT = {'thousand': 1e3, 'million': 1e6, 'billion': 1e9, 'trillion': 1e12, 'k': 1e3, 'm': 1e6, 'bn': 1e9, 'b': 1e9}
KO_MULT = {'만': 1e4, '억': 1e8, '조': 1e12}


def _req_json(url, timeout=12):
    return json.loads(base.req(url, timeout).decode('utf-8'))


def _live_fx_to_krw(code):
    """발송 시점 환율 우선. Yahoo 5분봉 마지막 체결값, 실패 시 Frankfurter 일일값."""
    if code == 'KRW':
        return 1.0, dt.datetime.now(KST), '원화'

    # 1) 발송 직전 시세: Yahoo Finance chart JSON
    try:
        symbol = urllib.parse.quote(f'{code}KRW=X')
        url = f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=5m'
        data = _req_json(url, 12)
        r = data['chart']['result'][0]
        timestamps = r.get('timestamp') or []
        closes = (((r.get('indicators') or {}).get('quote') or [{}])[0].get('close') or [])
        latest = None
        latest_ts = None
        for ts, px in zip(timestamps, closes):
            if px is not None and float(px) > 0:
                latest = float(px)
                latest_ts = int(ts)
        if latest and latest_ts:
            when = dt.datetime.fromtimestamp(latest_ts, tz=dt.timezone.utc).astimezone(KST)
            if (dt.datetime.now(KST) - when).total_seconds() <= 24 * 3600:
                return latest, when, '실시간 환율 API'
    except Exception:
        pass

    # 2) 무료 공식·중앙은행 혼합 일일 환율 API
    try:
        url = f'https://api.frankfurter.dev/v2/rate/{code}/KRW'
        data = _req_json(url, 12)
        rate = float(data['rate'])
        date_str = str(data.get('date') or '')
        when = dt.datetime.now(KST)
        if date_str:
            try:
                d = dt.date.fromisoformat(date_str)
                when = dt.datetime.combine(d, dt.time(0, 0), tzinfo=KST)
            except Exception:
                pass
        if rate > 0:
            return rate, when, '일일 환율 API'
    except Exception:
        pass
    return None, None, None


def _format_krw(v):
    v = float(v)
    if v >= 1e12:
        jo = int(v // 1e12)
        eok = int(round((v - jo * 1e12) / 1e8))
        if eok >= 10000:
            jo += 1
            eok -= 10000
        return f'약 {jo:,}조{eok:,}억원' if eok else f'약 {jo:,}조원'
    if v >= 1e8:
        eok = v / 1e8
        return f'약 {eok:,.1f}억원' if abs(eok - round(eok)) >= 0.05 else f'약 {round(eok):,}억원'
    if v >= 1e4:
        man = v / 1e4
        return f'약 {man:,.0f}만원'
    return f'약 {v:,.0f}원'


def _num(s):
    try:
        return float(str(s).replace(',', ''))
    except Exception:
        return None


def _add_amount(out, seen, code, amount, label):
    if amount is None or amount <= 0:
        return
    key = (code, round(float(amount), 4), label.lower())
    if key in seen:
        return
    seen.add(key)
    out.append((code, float(amount), label))


def _extract_amounts(text):
    """기사 제목·요약에 명시된 외화 금액만 추출. 통화가 불명확한 숫자는 환산하지 않는다."""
    src = base.clean(text or '')
    low = src.lower()
    out, seen = [], set()

    # USD: $1 million / USD 1 million / 2.6 billion dollars
    for m in re.finditer(r'(?i)(?:us\$|\$|usd)\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(thousand|million|billion|trillion|k|m|bn|b)?\b', src):
        n = _num(m.group(1)); mult = EN_MULT.get((m.group(2) or '').lower(), 1)
        _add_amount(out, seen, 'USD', n * mult if n else None, m.group(0))
    for m in re.finditer(r'(?i)([0-9][0-9,]*(?:\.[0-9]+)?)\s*(thousand|million|billion|trillion)\s+(?:u\.?s\.?\s*)?dollars?\b', src):
        n = _num(m.group(1)); mult = EN_MULT.get(m.group(2).lower(), 1)
        _add_amount(out, seen, 'USD', n * mult if n else None, m.group(0))
    for m in re.finditer(r'([0-9][0-9,]*(?:\.[0-9]+)?)\s*(만|억|조)?\s*달러', src):
        n = _num(m.group(1)); mult = KO_MULT.get(m.group(2) or '', 1)
        _add_amount(out, seen, 'USD', n * mult if n else None, m.group(0))

    # ISO 통화코드가 명시된 금액. USD는 위에서 처리.
    for code in FX_CODES:
        if code == 'USD':
            continue
        patt = rf'(?i)\b{code}\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(thousand|million|billion|trillion|k|m|bn|b)?\b'
        for m in re.finditer(patt, src):
            n = _num(m.group(1)); mult = EN_MULT.get((m.group(2) or '').lower(), 1)
            _add_amount(out, seen, code, n * mult if n else None, m.group(0))

    # 명확한 영문 통화명
    names = {
        'EUR': 'euros?', 'GBP': '(?:british\s+)?pounds?', 'JPY': '(?:japanese\s+)?yen',
        'NPR': 'nepalese\s+rupees?', 'CNY': '(?:chinese\s+)?yuan', 'CHF': 'swiss\s+francs?',
        'SGD': 'singapore\s+dollars?', 'AUD': 'australian\s+dollars?', 'CAD': 'canadian\s+dollars?',
        'AED': '(?:uae\s+)?dirhams?',
    }
    for code, name_pat in names.items():
        patt = rf'(?i)([0-9][0-9,]*(?:\.[0-9]+)?)\s*(thousand|million|billion|trillion)?\s+{name_pat}\b'
        for m in re.finditer(patt, src):
            n = _num(m.group(1)); mult = EN_MULT.get((m.group(2) or '').lower(), 1)
            _add_amount(out, seen, code, n * mult if n else None, m.group(0))

    # 한국어 통화명
    ko_names = {'EUR':'유로', 'GBP':'파운드', 'JPY':'엔', 'NPR':'네팔\s*루피', 'CNY':'위안', 'CHF':'스위스\s*프랑', 'SGD':'싱가포르\s*달러', 'AUD':'호주\s*달러', 'CAD':'캐나다\s*달러', 'AED':'(?:UAE\s*)?디르함'}
    for code, name_pat in ko_names.items():
        patt = rf'([0-9][0-9,]*(?:\.[0-9]+)?)\s*(만|억|조)?\s*{name_pat}'
        for m in re.finditer(patt, src):
            n = _num(m.group(1)); mult = KO_MULT.get(m.group(2) or '', 1)
            _add_amount(out, seen, code, n * mult if n else None, m.group(0))

    return out[:6]


def _fx_lines(row):
    text = ' '.join([row.get('title_original', ''), row.get('description', '')])
    amounts = _extract_amounts(text)
    if not amounts:
        return []
    lines = []
    rate_cache = {}
    for code, amount, label in amounts:
        if code not in rate_cache:
            rate_cache[code] = _live_fx_to_krw(code)
        rate, when, source = rate_cache[code]
        if not rate:
            lines.append(f'<b>원화 환산:</b> {base.html.escape(label)} · 환율 확인 불가 — 추정값 미표시')
            continue
        krw = amount * rate
        rate_txt = f'{rate:,.2f}원' if rate < 100 else f'{rate:,.0f}원'
        when_txt = when.strftime('%Y-%m-%d %H:%M KST') if when else '기준시각 확인 필요'
        lines.append(f'<b>원화 환산:</b> {base.html.escape(label)} ≈ <b>{_format_krw(krw)}</b> · {code}/KRW {rate_txt} · {when_txt} · {source}')
    return lines


def phase_lines_krw(row):
    lines = list(_prev_phase_lines(row))
    # 기존 고정 100만달러 문구도 환율 API로 원화 병기
    fixed = []
    for line in lines:
        if '긴급 인도지원 100만달러' in line and '원' not in line.split('100만달러', 1)[-1]:
            rate, when, source = _live_fx_to_krw('USD')
            if rate:
                krw = _format_krw(1_000_000 * rate)
                line = line.replace('100만달러', f'100만달러 ({krw})')
        fixed.append(line)
    fx = _fx_lines(row)
    # 본문 길이를 과도하게 늘리지 않도록 상세 환산은 최대 3개
    return fixed + fx[:3]


def build_alert_krw(items, now):
    text = _prev_build_alert(items, now)
    # 기존 build_alert가 phase_lines를 전역에서 다시 읽기 때문에 monkeypatch된 함수가 반영됨.
    return text


base.phase_lines = phase_lines_krw
base.build_alert = build_alert_krw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--finalize', action='store_true')
    args = ap.parse_args()
    if args.finalize:
        base.finalize()
    else:
        base.run()


if __name__ == '__main__':
    main()
