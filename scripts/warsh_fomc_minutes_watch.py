#!/usr/bin/env python3
"""기존 Warsh FOMC 의사록 감시: 공식 공개 검증·회의별 중복 방지·한국어 판정."""
import calendar
import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

STATE = Path('data/warsh_fomc_minutes_watch_state.json')
FOMC_STATE = Path('data/warsh_fomc_event_watch_state.json')
SEP_STATE = Path('data/warsh_sep_path_watch_state.json')
FED_CAL = 'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm'
TOKEN = (os.getenv('TELEGRAM_BOT_TOKEN') or '').strip()
CHAT = (os.getenv('TELEGRAM_CHAT_ID') or '').strip()
BOT = (os.getenv('EXPECTED_BOT_USERNAME') or 'hshs8879_bot').strip().lstrip('@')
FORCE = os.getenv('FORCE_NOTIFY', '0') == '1'
UA = 'Mozilla/5.0 (compatible; khs-watch/4.1)'
ET = ZoneInfo('America/New_York')
FORMAT_VERSION = 2


def fetch(url, timeout=18):
    last = None
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': UA,
                'Accept-Language': 'en-US,en;q=0.9',
            })
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode('utf-8', 'replace'), r.geturl()
        except urllib.error.HTTPError as exc:
            if exc.code == 404 or 400 <= exc.code < 500 and exc.code != 429:
                raise
            last = exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
        if attempt == 0:
            time.sleep(2)
    raise last


def clean(raw):
    raw = re.sub(r'(?is)<script.*?>.*?</script>|<style.*?>.*?</style>', ' ', raw)
    raw = re.sub(r'(?i)<br\s*/?>|</p>|</li>|</tr>|</h[1-6]>', '\n', raw)
    raw = re.sub(r'(?s)<[^>]+>', ' ', raw)
    value = html.unescape(raw).replace('\xa0', ' ')
    value = re.sub(r'[ \t]+', ' ', value)
    return re.sub(r'\n\s*\n+', '\n', value).strip()


def load(path):
    try:
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    except Exception:
        return {}


def save(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    state['updated_at_utc'] = datetime.now(timezone.utc).isoformat()
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def botname():
    if not TOKEN or not CHAT:
        raise RuntimeError('Telegram 비밀값 없음')
    with urllib.request.urlopen(f'https://api.telegram.org/bot{TOKEN}/getMe', timeout=18) as r:
        data = json.loads(r.read().decode('utf-8'))
    if not data.get('ok'):
        raise RuntimeError('Telegram getMe 응답 실패')
    return str((data.get('result') or {}).get('username') or '')


def send(message):
    # 전송 전 한국어 본문이 4096자보다 길면 조용히 잘라내지 않고 실패시킨다.
    if len(re.sub(r'<[^>]+>', '', message)) > 3900:
        raise RuntimeError('의사록 알림이 Telegram 문자 한도를 초과합니다')
    if botname().lower() != BOT.lower():
        raise RuntimeError(f'Telegram 발신 봇 불일치: @{BOT} 사용 필요')
    data = urllib.parse.urlencode({
        'chat_id': CHAT, 'text': message,
        'parse_mode': 'HTML', 'disable_web_page_preview': 'true',
    }).encode('utf-8')
    req = urllib.request.Request(
        f'https://api.telegram.org/bot{TOKEN}/sendMessage',
        data=data, method='POST',
    )
    # 중간에 네트워크가 끊기면 실제 수신 여부가 불확실하므로 자동 재전송하지 않는다.
    with urllib.request.urlopen(req, timeout=18) as r:
        response = json.loads(r.read().decode('utf-8'))
    result = response.get('result') or {}
    message_id = result.get('message_id')
    if response.get('ok') is not True or not isinstance(message_id, int):
        raise RuntimeError('Telegram 정상 응답 또는 message_id 확인 실패')
    return message_id


def link(label, url):
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'


def latest_statement_date():
    state = load(FOMC_STATE)
    cur = state.get('current_statement') or {}
    if re.fullmatch(r'20\d{2}-\d{2}-\d{2}', str(cur.get('date') or '')):
        return str(cur['date'])
    # 기존 FOMC 상태가 깨졌을 때만 공식 달력의 성명 URL을 확인한다.
    raw, _ = fetch(FED_CAL)
    dates = re.findall(r'/newsevents/pressreleases/monetary(20\d{6})a\.htm', raw, re.I)
    if not dates:
        raise RuntimeError('연준 공식 FOMC 성명 회의일 확인 실패')
    d = max(dates)
    return f'{d[:4]}-{d[4:6]}-{d[6:]}'


def minutes_url(statement_date):
    return ('https://www.federalreserve.gov/monetarypolicy/fomcminutes'
            + statement_date.replace('-', '') + '.htm')


def official_release_date(calendar_html, statement_date):
    """공식 FOMC 달력에서 대상 회의의 의사록 링크 직후 게시된 Released 날짜."""
    needle = 'fomcminutes' + statement_date.replace('-', '') + '.htm'
    dates = []
    for match in re.finditer(re.escape(needle), calendar_html, re.I):
        # PDF·HTML 표기의 본문 다음에 놓이는 실제 Released 메타데이터만 인식.
        nearby = clean(calendar_html[match.end():match.end()+650])
        m = re.search(r'\bReleased\s+([A-Z][a-z]+)\s+(\d{1,2}),\s+(20\d{2})', nearby, re.I)
        if m:
            try:
                month = list(calendar.month_name).index(m.group(1).capitalize())
                dates.append(datetime(int(m.group(3)), month, int(m.group(2))).date().isoformat())
            except (ValueError, IndexError):
                continue
    if not dates:
        return None
    if len(set(dates)) != 1:
        raise RuntimeError(f'의사록 공개일 공식 달력 불일치: {dates}')
    return dates[0]


def meeting_date_pattern(statement_date):
    d = datetime.strptime(statement_date, '%Y-%m-%d').date()
    prev = d - timedelta(days=1)
    if d.month == prev.month:
        return rf'\b{calendar.month_name[d.month]}\s+{prev.day}\s*[-–—]\s*{d.day},?\s+{d.year}\b'
    return rf'\b{calendar.month_name[prev.month]}\s+{prev.day}\s*[-–—]\s*{calendar.month_name[d.month]}\s+{d.day},?\s+{d.year}\b'


def verify_official_publication(calendar_html, minute_html, release_date, stmt_date):
    """URL 1개나 변경시각만으로 발표 확정 금지: 달력·본문·별도 연준 발표문 교차확인."""
    if not release_date:
        raise RuntimeError('연준 달력 Released 공개일 미확인 — 전송·중복확정 금지')
    now_et = datetime.now(ET)
    release_gate = datetime.fromisoformat(release_date + 'T14:00:00').replace(tzinfo=ET)
    if now_et < release_gate:
        raise RuntimeError('의사록 공식 공개 예정시각 이전 — 전송 금지')
    raw = clean(minute_html)
    target = meeting_date_pattern(stmt_date)
    if not re.search(target, raw, re.I):
        raise RuntimeError('의사록 본문 대상 회의 날짜 불일치')
    if not all(t in raw for t in [
        'Minutes of the Federal Open Market Committee',
        "Participants' Views on Current Conditions and the Economic Outlook",
        'Committee Policy Actions',
    ]):
        raise RuntimeError('의사록 본문 필수 절 누락 — 조기 공개·불완전 페이지 가능성')
    pathdate = release_date.replace('-', '')
    press_url = f'https://www.federalreserve.gov/newsevents/pressreleases/monetary{pathdate}a.htm'
    press_html, final_press = fetch(press_url)
    press = clean(press_html)
    if ('Minutes of the Federal Open Market Committee' not in press
            or not re.search(target, press, re.I)):
        raise RuntimeError('별도 연준 의사록 공개 보도자료 내용 불일치')
    if release_date > now_et.date().isoformat():
        raise RuntimeError('미래 공개일 불일치')
    return raw, final_press


def section(text, start, end):
    low = text.lower()
    a = low.find(start.lower())
    b = low.find(end.lower(), a + len(start)) if a >= 0 else -1
    if a < 0 or b < 0 or b <= a:
        raise RuntimeError('연준 의사록 절 구분 실패 — 발표 요지 오검출 방지')
    return text[a:b]


def extract_signals(text, stmt_date):
    text = ' '.join(text.split())
    views = section(
        text, "Participants' Views on Current Conditions and the Economic Outlook",
        'Committee Policy Actions',
    )
    # 금리정책 논의 부분만 별도로 분리해 단순 과거 표결을 향후 인상 경로로 오인하지 않음.
    policy = section(views, 'In their consideration of monetary policy at this meeting',
                     'Regarding balance sheet policy')

    signals = {
        'all_support': bool(re.search(
            r'all participants supported raising the target range', policy, re.I)),
        'most_yearend': bool(re.search(
            r'most participants assessed that another increase.{0,160}?by year end',
            policy, re.I | re.S)),
        'many_risk': bool(re.search(
            r'many participants emphasized that a higher path.{0,200}?risk-management grounds',
            policy, re.I | re.S)),
        'number_modal': bool(re.search(
            r'a number of participants viewed a higher path.{0,200}?modal outlooks',
            policy, re.I | re.S)),
        'several_not_restrictive': bool(re.search(
            r'several participants stated that they viewed the current policy rate '
            r'as not restrictive or only mildly restrictive', policy, re.I)),
        'couple_neutral': bool(re.search(
            r'a couple of participants remarked on having increased their estimate '
            r'of the neutral federal funds rate', policy, re.I)),
        'almost_all_risks': bool(re.search(
            r'almost all participants assessed that.{0,200}?inflation risks.{0,140}?upside',
            policy, re.I | re.S)),
        'few_treasury': bool(re.search(
            r'a few participants observed that Treasury markets had been functioning smoothly',
            views, re.I)),
        'limit_footprint': bool(re.search(
            r'limiting the Federal Reserve.s footprint in the Treasury market',
            views, re.I)),
        'ai_inflation': bool(re.search(
            r'ongoing geopolitical developments.{0,170}?AI-related investments'
            r'.{0,90}?inflation pressures', views, re.I | re.S)),
        'ai_core_goods': bool(re.search(
            r'core goods category.{0,130}?AI buildout.{0,130}?tariff',
            views, re.I | re.S)),
        'pce_methodology': bool(re.search(
            r'software and portfolio management fees.{0,180}?upcoming changes'
            r' to the BEA.s methodology', views, re.I | re.S)),
        'pce_3m_warning': bool(re.search(
            r'3-month change measure of core PCE inflation.{0,260}?volatile'
            r'.{0,230}?understate inflation', views, re.I | re.S)),
        'ai_private_debt_term_premium': bool(re.search(
            r'heavy private debt issuance to finance the development of '
            r'artificial intelligence.{0,200}?term premiums',
            text, re.I | re.S)),
        'unanimous_vote': bool(re.search(
            r'approved the following statement for release by a 12\s*[–—-]\s*0 vote',
            text, re.I)),
    }
    if stmt_date == '2026-09-16' and not all((
            signals['all_support'], signals['most_yearend'],
            signals['many_risk'], signals['number_modal'])):
        raise RuntimeError('9월 의사록 필수 연말 인상/이유 원문 탐지 실패 — 오판 알림 금지')
    return signals


def current_sep(stmt_date):
    snapshot = load(SEP_STATE).get('snapshot') or {}
    funds = snapshot.get('funds') or []
    if snapshot.get('date') != stmt_date or len(funds) < 2:
        return None
    try:
        return {'yearend': float(funds[0]), 'nextyear': float(funds[1]),
                'url': snapshot.get('url')}
    except (TypeError, ValueError):
        return None


def message(stmt_date, minutes_link, press_link, rel, sig):
    stmt = load(FOMC_STATE).get('current_statement') or {}
    sep = current_sep(stmt_date)
    rate = ('대부분이 연내 추가 인상 적절 가능성 평가 · 시점과 폭은 미확정'
            if sig['most_yearend'] else
            '추가 인상 의견의 우세 정도 자동 확인 불가 · 원문 참조')
    why = ('위험관리 목적 다수 / 기본 전망상 필요 상당수'
           if sig['many_risk'] and sig['number_modal'] else
           '추가 인상 근거의 참가자별 차이 확인 필요')
    lines = [
        '<b>[Warsh | FOMC 의사록 · 정책경로]</b>',
        f"대상: {stmt_date} 회의 · 공식 공개: {rel} (미국 현지)",
        '',
        '<b>한눈에 보기</b>',
        '• <b>9월 결정</b>: ' +
            ('전원 25bp 인상 지지 · 표결 12대 0 · 3.75~4.00%'
             if sig['all_support'] and sig['unanimous_vote'] else
             '9월 정책결정 결과 공식 성명 재확인 필요'),
        f'• <b>연말 전망</b>: {html.escape(rate)}',
        f'• <b>인상 근거</b>: {html.escape(why)}',
        '• <b>대차대조표</b>: 충분한 준비금 유지 · 시장기능 대비 ≠ QT 재개',
        '',
        '<b>확정 당사자·발언 강도</b>',
        '• 정책 지지: 모든 참석자(회의 의견) / FOMC 표결 12대 0(의결)' if sig['all_support'] else
            '• 정책 지지: 전원 여부 확인 필요',
        '• 연말 추가 인상 전망: 대부분(most) · 10월 인상 확정 아님' if sig['most_yearend'] else
            '• 연말 추가 인상 전망: 자동 판독 보류',
        '• 추가긴축 근거: 많은 참석자(many)는 위험관리, 상당수(a number of)는 기본 전망' if
            sig['many_risk'] and sig['number_modal'] else
            '• 추가긴축 근거: 참가자별 차이 재검증 필요',
    ]
    if sig['several_not_restrictive']:
        lines.append('• 제약 수준: 여러 명(several)은 금리가 비제약적 또는 약한 제약이라고 평가')
    if sig['couple_neutral']:
        lines.append('• 중립금리: 두어 명(a couple)은 추정치를 상향')
    if sep:
        lines.append(f"• 공식 점도표(당시 전망): 2026년 말 {sep['yearend']:.1f}% · 2027년 말 {sep['nextyear']:.1f}%")
    else:
        lines.append('• 공식 점도표: 해당 회의 전망치 확인 불가(다른 회의 전망 재사용 안 함)')
    lines += [
        '',
        '<b>새로 확인된 위험</b>',
    ]
    if sig['ai_inflation'] or sig['ai_core_goods']:
        lines.append('• AI 인프라 설비투자·유가가 물가 압력에 기여. 핵심 제품가격·투입비·전력 병목 관찰')
    if sig['ai_private_debt_term_premium']:
        lines.append('• AI 투자용 민간채권 대량 발행 → 자본조달 경쟁·국채 기간프리미엄 상승 우려')
    if sig['pce_3m_warning']:
        lines.append('• 몇몇은 근원 PCE 3개월 상승률의 하반기 과소평가 가능성을 경고')
    if sig['pce_methodology']:
        lines.append('• 몇몇은 소프트웨어·포트폴리오 운용수수료 물가의 향후 BEA 방식 변경을 언급')
    if sig['few_treasury'] and sig['limit_footprint']:
        lines.append('• 일부 참석자는 국채시장 스트레스 대비를 원하지만 연준의 국채시장 개입은 제한하자고 제안')
    if not any(sig[k] for k in ('ai_inflation','ai_private_debt_term_premium','pce_3m_warning','few_treasury')):
        lines.append('• 관련 정책·물가 세부 논의는 공식 원문으로 추가 확인')
    lines += [
        '',
        '<b>다음 확인·실패 경로</b>',
        '• 10월 27~28일 FOMC에서 실제 추가 인상 여부와 논거 변화를 확인',
        '• 유가·AI발 비용이 물가로 확산하는지, 아니면 소비·고용이 먼저 약해지는지 구분',
        '• 대차대조표 태스크포스 제안과 정식 시행지침/자산총량 변화를 분리',
        '• 이번 의사록은 과거 회의 기록이지 오늘의 금리결정이 아닙니다.',
        '',
        '<b>원천</b>',
        f"{link('연준 의사록', minutes_link)} · {link('공식 공개문', press_link)} · {link('연준 회의일정', FED_CAL)}",
    ]
    if sep and sep.get('url'):
        lines.append(link('연준 당시 점도표', sep['url']))
    return '\n'.join(lines)


def main():
    old = load(STATE)
    stmt_date = latest_statement_date()
    if not stmt_date:
        raise RuntimeError('최신 FOMC 회의일 확인 실패')
    target = minutes_url(stmt_date)
    cal_html, _ = fetch(FED_CAL)
    rel = official_release_date(cal_html, stmt_date)
    if not rel:
        print(json.dumps({
            'available': False, 'statement_date': stmt_date,
            'release_verified': False, 'sent': False,
            'reason': '공식 달력의 Released 표기 없음 — 미확정'
        }, ensure_ascii=False))
        return
    try:
        raw, final = fetch(target)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            print(json.dumps({
                'available': False, 'statement_date': stmt_date,
                'release_date': rel, 'sent': False,
                'reason': '본문 404 — 미확정'
            }, ensure_ascii=False))
            return
        raise
    body, press_url = verify_official_publication(cal_html, raw, rel, stmt_date)
    signals = extract_signals(body, stmt_date)
    key = f'{stmt_date}|{rel}'
    legacy_sent = (
        bool(old.get('sent')) and old.get('last_minutes_url') == final
        and not old.get('last_sent_key')
    )
    already = old.get('last_sent_key') == key or legacy_sent
    if old.get('pending_key') == key and old.get('delivery_status') == 'sending':
        raise RuntimeError('이전 Telegram 전송 결과 불명확 — 자동 재전송 중단, 운영 확인 필요')
    # 설치 때 오래된 의사록을 다시 알리지 않되, 이번 미전송 건은 복원한다.
    delta = (datetime.now(ET).date() - datetime.fromisoformat(rel).date()).days
    eligible = 0 <= delta <= 7
    should_send = FORCE or (not already and eligible)

    new = {
        'schema_version': FORMAT_VERSION,
        'last_statement_date': stmt_date,
        'last_minutes_url': final,
        'last_release_date': rel,
        'last_sent_key': key if already else old.get('last_sent_key'),
        'message_id': old.get('message_id'),
        'classification': signals,
        'status': '공식 공개·본문·보도자료 확인',
        'sent': bool(already),
        'source': {'minutes': final, 'announcement': press_url, 'calendar': FED_CAL},
    }
    if should_send:
        # 전송 대기 상태를 먼저 남겨서 같은 Actions 작업 내 자동 재시도 시
        # 수신 여부가 불명확한 메시지를 중복 발송하지 않도록 한다.
        new.update({'pending_key': key, 'delivery_status': 'sending', 'sent': False})
        save(new)
        receipt = send(message(stmt_date, final, press_url, rel, signals))
        new.update({
            'sent': True, 'last_sent_key': key,
            'message_id': receipt, 'delivery_status': 'confirmed',
            'pending_key': None, 'sent_at_utc': datetime.now(timezone.utc).isoformat(),
        })
        save(new)
    elif not already and not eligible:
        new['status'] = '7일 경과 과거 의사록 — 기준선만 설정'
        new['delivery_status'] = 'not_sent_historical'
        save(new)
    else:
        new['delivery_status'] = 'confirmed' if already else old.get('delivery_status')
        new['pending_key'] = None
        save(new)
    print(json.dumps({
        'available': True, 'statement_date': stmt_date, 'release_date': rel,
        'verified': True, 'sent': should_send, 'already_sent': bool(already),
        'message_id': new.get('message_id'),
        'most_yearend': signals['most_yearend'],
        'many_risk': signals['many_risk'],
        'number_modal': signals['number_modal'],
        'balance_sheet_qt_claim': False,
        'delivery_status': new.get('delivery_status'),
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
