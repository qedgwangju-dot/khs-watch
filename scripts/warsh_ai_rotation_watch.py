#!/usr/bin/env python3
"""AI 하드웨어·소프트웨어 상대강도: 동일 거래일 종가·독립 가격원천 검증."""
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / 'data/warsh_ai_rotation_watch_state.json'
TOKEN = (os.getenv('TELEGRAM_BOT_TOKEN') or '').strip()
CHAT_ID = (os.getenv('TELEGRAM_CHAT_ID') or '').strip()
EXPECTED_BOT = (os.getenv('EXPECTED_BOT_USERNAME') or 'khs887900887900008879_bot').strip().lstrip('@')
FORCE_NOTIFY = os.getenv('FORCE_NOTIFY', '0') == '1'
THRESH_5D = float(os.getenv('WARSH_ROTATION_5D_PP') or '5')
THRESH_3D = float(os.getenv('WARSH_ROTATION_3D_PP') or '3')
MAX_SOURCE_GAP_BP = float(os.getenv('WARSH_AI_ROTATION_MAX_SOURCE_GAP_BP') or '12')
METHODOLOGY_VERSION = '2026-10-10-v2'
UA = 'Mozilla/5.0 (compatible; khs-watch/3.2; +https://github.com/qedgwangju-dot/khs-watch)'
YAHOO = 'https://query1.finance.yahoo.com/v8/finance/chart/{}?range=1mo&interval=1d&includePrePost=false'
SYMBOLS = {
    '반도체': 'SOXX', '소프트웨어': 'IGV',
    'Micron': 'MU', 'SanDisk': 'SNDK',
    'Coherent': 'COHR', 'Lumentum': 'LITE', 'Marvell': 'MRVL',
    'Applied Materials': 'AMAT', 'KLA': 'KLAC',
}
BASKETS = {
    '메모리': ['Micron', 'SanDisk'],
    '광연결·네트워크': ['Coherent', 'Lumentum', 'Marvell'],
    '반도체 장비': ['Applied Materials', 'KLA'],
}
NUM = r'[0-9][0-9,.]*'
ROW_PATTERN = re.compile(
    rf'(?<![A-Za-z])([A-Z][a-z]{{2}}\s+\d{{1,2}},\s+20\d{{2}})\s+'
    rf'({NUM})\s+({NUM})\s+({NUM})\s+({NUM})\s+({NUM}|-)\s+'
)
NY = ZoneInfo('America/New_York')

def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'en-US,en;q=0.9'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode('utf-8', 'replace')

def parse_independent_history(raw):
    plain = html.unescape(re.sub(r'<[^>]+>', ' ', raw))
    plain = re.sub(r'\s+', ' ', plain)
    if 'Historical Data' not in plain:
        raise RuntimeError('외부 마감가격 제공처: 과거가격 표 누락')
    plain = plain.split('Historical Data', 1)[1]
    if 'Data Source:' in plain:
        plain = plain.split('Data Source:', 1)[0]
    out = {}
    for match in ROW_PATTERN.finditer(plain):
        date = datetime.strptime(match.group(1), '%b %d, %Y').date().isoformat()
        price = float(match.group(5).replace(',', ''))
        if price <= 0:
            raise RuntimeError(f'비정상 종가: {date} {price}')
        out[date] = price
    if len(out) < 7:
        raise RuntimeError(f'외부 마감가격 제공처: 유효 일봉 {len(out)}개로 부족')
    return out

def independent_series(symbol):
    group = 'etf' if symbol in {'SOXX', 'IGV'} else 'stocks'
    url = f'https://stockanalysis.com/{group}/{symbol.lower()}/history/'
    series = parse_independent_history(fetch(url))
    return series, url

def yahoo_series(symbol, now=None):
    ny_now = now or datetime.now(NY)
    raw = fetch(YAHOO.format(urllib.parse.quote(symbol, safe='')) + f'&cb={int(time.time())}')
    result = ((json.loads(raw).get('chart') or {}).get('result') or [None])[0]
    if not result:
        raise RuntimeError(f'{symbol} Yahoo 가격 이력 없음')
    ticks = result.get('timestamp') or []
    quotes = (((result.get('indicators') or {}).get('quote') or [{}])[0]).get('close') or []
    if len(ticks) != len(quotes):
        raise RuntimeError(f'{symbol} Yahoo 일자/종가 길이 불일치')
    out = {}
    for stamp, value in zip(ticks, quotes):
        if value is None:
            continue
        d = datetime.fromtimestamp(stamp, NY).date().isoformat()
        if d == ny_now.date().isoformat() and (ny_now.hour < 16 or (ny_now.hour == 16 and ny_now.minute < 45)):
            continue
        value = float(value)
        if value <= 0:
            raise RuntimeError(f'{symbol} Yahoo 비정상 종가: {d}={value}')
        out[d] = value
    if len(out) < 7:
        raise RuntimeError(f'{symbol} Yahoo 완료 일봉 부족')
    return out

def compare_two_sources(name, symbol, official, yahoo, sample_dates):
    differences = {}
    for d in sample_dates:
        if d not in official or d not in yahoo:
            raise RuntimeError(f'{symbol} {d} 두 제공처의 완료 종가가 일치하는 날짜에 없음')
        a = float(official[d])
        b = float(yahoo[d])
        diff_bp = abs(a - b) / a * 10000
        differences[d] = round(diff_bp, 4)
        if diff_bp > MAX_SOURCE_GAP_BP:
            raise RuntimeError(
                f'{symbol} {d} 마감 종가 제공처 불일치 {diff_bp:.2f}bp '
                f'(독립 마감가격 {a:.4f}, Yahoo {b:.4f})'
            )
    return {
        'ticker': symbol,
        'date': sample_dates[-1],
        'primary_close': float(official[sample_dates[-1]]),
        'yahoo_close': float(yahoo[sample_dates[-1]]),
        'max_gap_bp': max(differences.values()),
        'gap_by_date_bp': differences,
    }

def build_snapshot(independent, yahoo, now=None):
    ny_now = now or datetime.now(NY)
    syms = set(SYMBOLS.values())
    if set(independent) != syms or set(yahoo) != syms:
        raise RuntimeError('9개 검증 종목 목록 불일치')
    latest_independent = {max(independent[t]) for t in syms}
    latest_yahoo = {max(yahoo[t]) for t in syms}
    if len(latest_independent) != 1 or len(latest_yahoo) != 1:
        raise RuntimeError(f'종목 간 최종 일자 불일치: 독립 {sorted(latest_independent)}, Yahoo {sorted(latest_yahoo)}')
    latest = next(iter(latest_independent))
    if latest != next(iter(latest_yahoo)):
        raise RuntimeError(f'제공처 간 최신 일자 불일치: {latest} vs {next(iter(latest_yahoo))}')

    # Completed sessions only; Friday on a Saturday is valid. Weekday after close needs a fresh bar.
    ny_today = ny_now.date().isoformat()
    if latest > ny_today:
        raise RuntimeError('미국 현지 미래 날짜 일봉')
    if ny_now.weekday() < 5 and (ny_now.hour > 16 or (ny_now.hour == 16 and ny_now.minute >= 45)):
        if latest != ny_today:
            raise RuntimeError(f'당일 마감 일봉 미게시: 미국 현지 {ny_today}, 제공처 최신 {latest}')
    age_days = (ny_now.date() - datetime.strptime(latest, '%Y-%m-%d').date()).days
    if age_days > 4:
        raise RuntimeError(f'최신 거래일 종가 과거 데이터: {age_days}일 지연')

    common = set.intersection(*(set(independent[t]) & set(yahoo[t]) for t in syms))
    dates = sorted(d for d in common if d <= latest)
    if len(dates) < 7 or dates[-1] != latest:
        raise RuntimeError('공통 거래일 기준 7개 완료 종가 부족')
    d1, d3, d5 = dates[-2], dates[-4], dates[-6]
    check_dates = dates[-7:]
    source_checks = {}
    returns = {}
    for name, symbol in SYMBOLS.items():
        a, b = independent[symbol], yahoo[symbol]
        source_checks[name] = compare_two_sources(name, symbol, a, b, check_dates)
        returns[name] = {
            '1d': (a[latest] / a[d1] - 1) * 100,
            '3d': (a[latest] / a[d3] - 1) * 100,
            '5d': (a[latest] / a[d5] - 1) * 100,
        }
    sw, semi = returns['소프트웨어'], returns['반도체']
    rel3 = semi['3d'] - sw['3d']
    rel5 = semi['5d'] - sw['5d']
    baskets = {}
    count = 0
    for group, names in BASKETS.items():
        ret5 = sum(returns[name]['5d'] for name in names) / len(names)
        diff5 = ret5 - sw['5d']
        baskets[group] = {'5d': ret5, 'vs_software_5d': diff5, 'sample_count': len(names)}
        if diff5 >= THRESH_5D:
            count += 1
    active = rel5 >= THRESH_5D and rel3 >= THRESH_3D and count >= 2
    if active and count == 3:
        verdict = 'AI 하드웨어 확산 확인 — 반도체에서 메모리·광연결·장비까지 동반 우위'
    elif active:
        verdict = 'AI 하드웨어 우위 지속 — 공급망 확산 일부 확인'
    elif rel5 >= THRESH_5D:
        verdict = '반도체 우위지만 공급망 확산 확인 부족'
    elif rel5 <= -THRESH_5D:
        verdict = '소프트웨어 상대우위 — 하드웨어 로테이션 약화'
    else:
        verdict = '뚜렷한 구조적 로테이션 미확인'
    return {
        'date': latest, 'window': {'1d': d1, '3d': d3, '5d': d5},
        'methodology_version': METHODOLOGY_VERSION,
        'price_basis': 'StockAnalysis / S&P Global Market Intelligence 마감 종가·Yahoo 완료 일봉 교차확인',
        'source_gap_limit_bp': MAX_SOURCE_GAP_BP,
        'source_checks': source_checks,
        'returns': returns, 'relative_3d': rel3, 'relative_5d': rel5,
        'baskets': baskets, 'confirm_count': count, 'active': active,
        'verdict': verdict, 'updated_at_utc': datetime.now(timezone.utc).isoformat(),
    }

def snapshot():
    independent, yahoo = {}, {}
    for symbol in SYMBOLS.values():
        independent[symbol], _ = independent_series(symbol)
        yahoo[symbol] = yahoo_series(symbol)
    return build_snapshot(independent, yahoo)

def load_state():
    try:
        return json.loads(STATE_PATH.read_text(encoding='utf-8')) if STATE_PATH.exists() else {}
    except Exception:
        return {}

def save_state(s):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(s, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

def get_bot_username():
    if not TOKEN:
        raise RuntimeError('Telegram 토큰이 없습니다')
    with urllib.request.urlopen(f'https://api.telegram.org/bot{TOKEN}/getMe', timeout=20) as response:
        payload = json.loads(response.read().decode('utf-8'))
    if not payload.get('ok'):
        raise RuntimeError('Telegram 봇 신원확인 실패')
    return str((payload.get('result') or {}).get('username') or '')

def source_link(label, url):
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'

def send(msg):
    if not CHAT_ID:
        raise RuntimeError('Telegram 채팅 식별값이 없습니다')
    username = get_bot_username()
    if username.lower() != EXPECTED_BOT.lower():
        raise RuntimeError(f'Telegram 봇 불일치: 예상 @{EXPECTED_BOT}, 실제 @{username}')
    if len(msg) >= 4096:
        raise RuntimeError('Telegram 글자 수 초과 — 내용 잘림 전송 금지')
    payload = urllib.parse.urlencode({
        'chat_id': CHAT_ID, 'text': msg, 'parse_mode': 'HTML', 'disable_web_page_preview': 'true'
    }).encode()
    request = urllib.request.Request(f'https://api.telegram.org/bot{TOKEN}/sendMessage', data=payload, method='POST')
    with urllib.request.urlopen(request, timeout=25) as response:
        output = json.loads(response.read().decode('utf-8'))
    if not output.get('ok') or not (output.get('result') or {}).get('message_id'):
        raise RuntimeError('Telegram 메시지 전송 확인 실패')
    mid = output['result']['message_id']
    print(f'ai_rotation_telegram_delivery_confirmed=true bot=@{username} id={mid}')
    return mid

def visible_changed(old, s):
    def fmt(x): return f'{float(x):+.1f}'
    try:
        fields = [
            ('반도체', '3d'), ('반도체', '5d'),
            ('소프트웨어', '3d'), ('소프트웨어', '5d')
        ]
        if any(fmt(old['returns'][n][w]) != fmt(s['returns'][n][w]) for n, w in fields):
            return True
        for w in ('relative_3d', 'relative_5d'):
            if fmt(old[w]) != fmt(s[w]):
                return True
        for group in BASKETS:
            for key in ('5d', 'vs_software_5d'):
                if fmt(old['baskets'][group][key]) != fmt(s['baskets'][group][key]):
                    return True
    except (KeyError, TypeError, ValueError):
        return True
    return False

def message(s, correction=False, old=None):
    old = old or {}
    semi = s['returns']['반도체']
    sw = s['returns']['소프트웨어']
    title = '[정정·AI 하드웨어·소프트웨어 상대강도]' if correction else '[AI 하드웨어·소프트웨어 상대강도]'
    lines = [
        title, f"기준: {s['date']} 미국 정규장 마감 종가",
        f"3거래일 비교: {s['window']['3d']} → {s['date']}",
        f"5거래일 비교: {s['window']['5d']} → {s['date']}", ''
    ]
    if correction:
        lines += [
            '<b>정정·검증 강화 사유</b>',
            '• 이전 알림은 Yahoo 일봉 하나로 계산했고 모든 종목의 비교 시작일과 최종 종가를 독립 검증하지 않았습니다.',
            '• 이번부터 모든 표본을 같은 거래일로 정렬하고 외부 마감 종가와 교차검증했습니다.',
            ''
        ]
        if old.get('date') == s['date']:
            lines.append(f"• 직전 반도체 3거래일 {float(old.get('returns',{}).get('반도체',{}).get('3d',0)):+.1f}% → 재검산 {semi['3d']:+.1f}%")
    lines += [
        '<b>핵심 판정</b>', f"• <b>{html.escape(s['verdict'])}</b>", '',
        '<b>현재 숫자</b>',
        f"• 반도체(SOXX): 3거래일 {semi['3d']:+.1f}% · 5거래일 {semi['5d']:+.1f}%",
        f"• 소프트웨어(IGV): 3거래일 {sw['3d']:+.1f}% · 5거래일 {sw['5d']:+.1f}%",
        f"• 반도체 초과수익: 3거래일 {s['relative_3d']:+.1f}%p · 5거래일 {s['relative_5d']:+.1f}%p"
    ]
    for group, basket in s['baskets'].items():
        lines.append(
            f"• {html.escape(group)} 표본 {basket['sample_count']}개: "
            f"5거래일 {basket['5d']:+.1f}% · 소프트웨어 대비 {basket['vs_software_5d']:+.1f}%p"
        )
    if s['relative_5d'] <= -THRESH_5D:
        meaning = '최근 5거래일은 반도체가 소프트웨어보다 약했습니다. 주가의 상대강도 신호이지 실제 AI 설비투자 축소나 기업 수주 감소가 확인됐다는 뜻은 아닙니다.'
    elif s['relative_5d'] >= THRESH_5D:
        meaning = '최근 5거래일은 반도체가 소프트웨어보다 강했습니다. 본업 수주·매출까지 개선됐는지는 따로 확인해야 합니다.'
    else:
        meaning = '현재 상대강도 차이만으로 지속적인 투자자 선호 변화를 단정하기 어렵습니다.'
    maxgap = max(row['max_gap_bp'] for row in s['source_checks'].values())
    lines += [
        '', '<b>쉽게 말하면</b>', f"• {meaning}",
        '• 메모리·광연결·장비는 지정된 대표 종목의 동일가중 수익률 평균이며 업종 전체의 수익률이나 자금유입 통계가 아닙니다.',
        '• 첫째, 3거래일·5거래일 신호가 이어지는지 보고, 둘째, 실제 실적·주문·ETF 자금흐름을 별도로 확인합니다.',
        '', '<b>가격 검증</b>',
        f"• 기준: 9개 종목 공통 마감일·시작일 일치 · 두 제공처 최대 차이 {maxgap:.2f}bp (허용 {MAX_SOURCE_GAP_BP:.0f}bp)",
        '• 두 제공처가 허용범위 밖이거나 최종 거래일이 일치하지 않으면 판정과 알림을 보내지 않습니다.',
        '', '<b>원천</b>',
        f"{source_link('SOXX 마감가격', 'https://stockanalysis.com/etf/soxx/history/')} · "
        f"{source_link('IGV 마감가격', 'https://stockanalysis.com/etf/igv/history/')} · "
        f"{source_link('SOXX 원자료 보조', 'https://finance.yahoo.com/quote/SOXX/')} · "
        f"{source_link('IGV 원자료 보조', 'https://finance.yahoo.com/quote/IGV/')}"
    ]
    return '\n'.join(lines)

def main():
    old = load_state()
    try:
        s = snapshot()
    except Exception as exc:
        print(json.dumps({
            'data_valid': False, 'sent': False,
            'failure': f'{type(exc).__name__}: {exc}',
            'rule': '데이터 검증 실패 → 판정·송출·상태 갱신 차단'
        }, ensure_ascii=False))
        raise
    old_version = old.get('methodology_version')
    method_change = bool(old and old_version != METHODOLOGY_VERSION)
    changed = (old.get('active') not in (None, s['active']) or old.get('verdict') not in (None, s['verdict']))
    correction = bool(method_change or (old.get('date') and old['date'] > s['date']))
    relevant_changed = visible_changed(old, s) if old else False
    should_send = FORCE_NOTIFY or correction or (bool(old) and changed)

    if should_send:
        mid = send(message(s, correction=correction, old=old))
        s['last_sent_message_id'] = mid
        s['last_sent_date'] = s['date']
        s['last_sent_verdict'] = s['verdict']
    else:
        s['last_sent_message_id'] = old.get('last_sent_message_id')
        s['last_sent_date'] = old.get('last_sent_date')
        s['last_sent_verdict'] = old.get('last_sent_verdict')
    save_state(s)
    print(json.dumps({
        'data_valid': True, 'date': s['date'], 'methodology': METHODOLOGY_VERSION,
        'window': s['window'], 'source_checks': s['source_checks'],
        'relative_3d': s['relative_3d'], 'relative_5d': s['relative_5d'],
        'verdict': s['verdict'], 'method_change': method_change,
        'visible_changed': relevant_changed,
        'correction': correction, 'sent': bool(should_send),
        'message_id': s.get('last_sent_message_id') if should_send else None
    }, ensure_ascii=False))

def self_test():
    sample = ('Historical Data Daily Date Open High Low Close Adj. Close Change Volume '
              'Oct 9, 2026 1.00 1.10 0.95 1.02 1.02 +2.0% 123,456 '
              'Oct 8, 2026 1.03 1.09 0.97 1.00 1.00 -1.0% 123,456 ')
    assert len(ROW_PATTERN.findall(sample)) == 2
    assert abs(parse_independent_history(
        'Historical Data ' + ' '.join(
            f'Oct {i}, 2026 1.00 1.10 0.95 1.02 1.02 +2.0% 123,456'
            for i in range(1, 8))
        + ' Data Source: S&P'
    )['2026-10-07'] - 1.02) < 1e-9
    dates = ['2026-10-01','2026-10-02','2026-10-05','2026-10-06',
             '2026-10-07','2026-10-08','2026-10-09']
    independent = {symbol: {d: 100 + i for i, d in enumerate(dates)} for symbol in SYMBOLS.values()}
    yahoo = {symbol: dict(rows) for symbol, rows in independent.items()}
    yahoo['SOXX']['2026-10-09'] = 106.07
    check = compare_two_sources('반도체', 'SOXX', independent['SOXX'], yahoo['SOXX'], dates)
    assert check['max_gap_bp'] > 6 and check['max_gap_bp'] < MAX_SOURCE_GAP_BP
    now = datetime(2026,10,9,18,30,tzinfo=NY)
    out = build_snapshot(independent, yahoo, now)
    assert out['window']['3d'] == '2026-10-06'
    assert out['window']['5d'] == '2026-10-02'
    assert out['date'] == '2026-10-09'
    yahoo['SOXX']['2026-10-09'] = 108
    try:
        build_snapshot(independent,yahoo,now)
        raise AssertionError('disagreement must block')
    except RuntimeError as e:
        assert '불일치' in str(e)
    print('ai_rotation_regression_tests=true checks=source_disagreement,6shared_dates,close_alignment')

if __name__ == '__main__':
    if '--self-test' in sys.argv:
        self_test()
    else:
        main()
