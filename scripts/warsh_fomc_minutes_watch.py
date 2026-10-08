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
POLICY_STATE = Path('data/warsh_policy_path_watch_state.json')
FED_CAL = 'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm'
TOKEN = (os.getenv('TELEGRAM_BOT_TOKEN') or '').strip()
CHAT = (os.getenv('TELEGRAM_CHAT_ID') or '').strip()
BOT = (os.getenv('EXPECTED_BOT_USERNAME') or 'hshs8879_bot').strip().lstrip('@')
FORCE = os.getenv('FORCE_NOTIFY', '0') == '1'
UA = 'Mozilla/5.0 (compatible; khs-watch/4.1)'
ET = ZoneInfo('America/New_York')
FORMAT_VERSION = 3


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
    """원문에서 근거가 잡힌 항목만 참으로 판정. 참가자/시장보고/위원회 결정을 분리."""
    text = ' '.join(text.split())
    views = section(
        text, "Participants' Views on Current Conditions and the Economic Outlook",
        'Committee Policy Actions',
    )
    outlook = views.split('In their consideration of monetary policy at this meeting')[0]
    policy = section(
        views, 'In their consideration of monetary policy at this meeting',
        'Regarding balance sheet policy',
    )
    balance = views.split('Regarding balance sheet policy', 1)[-1]
    manager = section(text, 'Developments in Financial Markets and Open Market Operations',
                      'Staff Review of the Economic Situation')
    actions = text.split('Committee Policy Actions',1)[-1]

    def has(where, pattern):
        return bool(re.search(pattern, where, flags=re.I))

    signals = {
        # 의결권자 12인 표결과 참가자 의견(18인 전망)은 서로 별개.
        'all_support': has(policy, r'all participants supported raising the target range'),
        'unanimous_vote': has(actions, r'12\s*[–—-]\s*0 vote') or has(
            actions, r'Voting against this action:\s*None'),
        'most_yearend': has(policy,
            r'most participants assessed that another increase.{0,180}?by year end'),
        'many_risk': has(policy,
            r'many participants emphasized that a higher path.{0,210}?risk-management grounds'),
        'number_modal': has(policy,
            r'a number of participants viewed a higher path.{0,220}?modal outlooks'),
        'several_not_restrictive': has(policy,
            r'several participants stated that they viewed the current policy rate as not restrictive or only mildly restrictive'),
        'couple_neutral': has(policy,
            r'a couple of participants remarked on having increased their estimate of the neutral federal funds rate'),
        'almost_all_risks': has(policy,
            r'almost all participants assessed that.{0,190}?inflation risks.{0,90}?upside'),

        # 유동성 운영과 향후 시장 스트레스 대비 논의를 총량축소형 QT와 혼동하지 않음.
        'few_treasury': has(balance,
            r'a few participants observed that Treasury markets had been functioning smoothly'),
        'treasury_stress': has(balance,
            r'importance of planning for market stress'),
        'strengthen_tools': has(balance,
            r'strengthening the Federal Reserve.s strategy, communications, and tools for addressing market dysfunction'),
        'limit_footprint': has(balance,
            r'limiting the Federal Reserve.s footprint in the Treasury market'),
        'ample_reserves': has(actions,
            r'maintaining ample reserves in the banking system'),
        'principal_reinvestment': has(actions,
            r'Roll over at auction all principal payments.*?Reinvest all principal payments'),

        # 물가: 의사록 시점 참가자 의견과 직원 추산, 공개일 현재 공식치 구별.
        'inflation_sticky': has(outlook,
            r'Participants noted that inflation remained elevated and that they had not seen sufficient progress'),
        'ai_inflation': has(outlook,
            r'ongoing geopolitical developments.{0,160}?surging AI-related investments.{0,90}?inflation pressures'),
        'core_services_ex_housing': has(outlook,
            r'Several participants observed that the rate of price increases in core services excluding housing remained elevated'),
        'ai_core_goods': has(outlook,
            r'core goods category.{0,120}?AI buildout.{0,110}?tariff increases waned'),
        'inflation_upside': has(outlook,
            r'Participants generally assessed inflation risk as skewed to the upside'),
        'inflation_upside_more': has(outlook,
            r'some participants remarked that those risks had become more skewed to the upside'),
        'inflation_expectations_warning': has(outlook,
            r'after more than five years of inflation above 2 percent.{0,165}?inflation expectations and wage- and price-setting'),
        'inflation_exp_anchored': has(outlook,
            r'medium- and longer-term inflation expectations remained at levels consistent with the Committee.s 2 percent objective'),
        'pce_methodology': has(outlook,
            r'software and portfolio management fees.{0,220}?upcoming changes to the BEA.s methodology'),
        'pce_3m_warning': has(outlook,
            r'3-month change measure of core PCE inflation.{0,245}?volatile.{0,185}?understate inflation'),

        # 고용: 낮은 노동이동성과 전체 임금·AI 숙련인력 임금을 별개 기록.
        'employment_stable': has(outlook,
            r'Participants judged that labor market conditions were stable and generally viewed the labor market as close to maximum employment'),
        'employment_majority': has(outlook,
            r'A majority of participants assessed that the labor market had strengthened a bit recently'),
        'employment_low_dynamism': has(outlook,
            r'Several participants noted that dynamism in the labor market was unusually low'),
        'employment_low_hire_layoff_find': has(outlook,
            r'low rates of hiring and layoffs, a low job-finding rate, and a persistently elevated long-term unemployment rate'),
        'employment_ai_skilled_wages': has(outlook,
            r'Some participants observed that strong demand for skilled workers.{0,150}?driving strong wage gains'),
        'employment_moderate_wages': has(outlook,
            r'some participants also commented that aggregate wage growth was moderate'),
        'employment_outlook_balanced': has(outlook,
            r'Participants generally viewed the upside and downside risks to the labor market as broadly balanced'),

        # 실물 성장: AI 투자, 장기금리/주택, 고소득층/저소득층, 생산성 불확실성.
        'growth_solid': has(outlook,
            r'Participants generally assessed that economic activity was expanding at a solid pace'),
        'business_investment_consumption': has(outlook,
            r'Robust business investment and resilient consumer spending had supported economic activity'),
        'growth_momentum': has(outlook,
            r'Several participants commented that the underlying momentum in the economy appeared to have increased'),
        'ai_surprise': has(outlook,
            r'Several participants commented that the scale and pace of the AI buildout had continued to surprise to the upside'),
        'financial_supportive': has(outlook,
            r'Many participants commented that, despite the recent rise in longer-term Treasury yields, financial conditions appeared to be supportive of economic growth'),
        'housing_exception': has(outlook,
            r'A few participants commented that housing was a sector in which financial conditions did not appear supportive'),
        'consumer_high_income': has(outlook,
            r'Several participants observed that stock market gains had provided support to consumer spending, particularly among higher-income households'),
        'consumer_low_income': has(outlook,
            r'Several participants noted, however, that low- and moderate-income households faced strains'),
        'productivity_future_uncertain': has(outlook,
            r'Participants generally judged that AI-related investments would likely contribute to stronger gains in productivity and potential output.{0,175}?uncertainty over the magnitude or timing'),
        'ai_cyber_risk': has(outlook,
            r'A few participants flagged emerging concerns regarding potential repercussions associated with rapid adoption of AI, including cybersecurity'),

        # 별도 공개 당시 시장보고: 참가자 일반 합의가 아님.
        'ai_private_debt_term_premium': has(manager,
            r'heavy private debt issuance to finance the development of artificial intelligence.{0,135}?term premiums'),
        'yields_2y10y_35bp': has(manager,
            r'Nominal yields increased around 35 basis points across the 2- to 10-year segment'),
    }
    if stmt_date == '2026-09-16':
        mandatory = (
            'all_support','unanimous_vote','most_yearend','many_risk','number_modal',
            'few_treasury','treasury_stress','limit_footprint','ample_reserves',
            'inflation_sticky','ai_inflation','core_services_ex_housing','ai_core_goods',
            'inflation_upside','employment_stable','employment_majority',
            'employment_low_dynamism','growth_solid','ai_surprise',
            'consumer_high_income','consumer_low_income','productivity_future_uncertain',
        )
        missing = [k for k in mandatory if not signals[k]]
        if missing:
            raise RuntimeError(
                '9월 FOMC 의사록 필수 근거 파싱 실패 — 알림 보류: ' + ','.join(missing)
            )
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


def _date_ko(value):
    try:
        d = datetime.strptime(str(value)[:10], '%Y-%m-%d')
        return f'{d.year}년 {d.month}월 {d.day}일'
    except ValueError:
        return '날짜 확인 필요'


def market_status():
    state = load(POLICY_STATE)
    if state.get('source_status') != '시장원천 최신성·연준 공식범위 교차검증 통과':
        return 'CME 공식 금리선물 최신값 확인 실패 · 과거 인상확률 재사용 금지'
    return '금리선물 결제값은 참고용 · 의사록 참가자 의견과 별도 판정'


def message(stmt_date, minutes_link, press_link, rel, sig, upgraded=False):
    sep = current_sep(stmt_date)
    meeting_day = datetime.strptime(stmt_date, '%Y-%m-%d').date()
    # 정례 2일 회의 기준. 다른 형식일 때는 날짜 범위 추정 대신 마지막 날만 표시.
    meeting_label = _date_ko(stmt_date) + ' 종료 회의'
    followup = '10월 27~28일 FOMC' if stmt_date == '2026-09-16' else '다음 FOMC'
    known = lambda name: bool(sig.get(name))

    def group(name, items):
        true_lines = [line for signal, line in items if known(signal)]
        if not true_lines:
            return ['<b>' + name + '</b>', '• 참가자 의견의 해당 문구 자동 검증 보류 · 공식 원문 확인 필요', '']
        return ['<b>' + name + '</b>'] + true_lines + ['']

    lines = [
        ('<b>[보강 · Warsh | FOMC 의사록 · 반응함수]</b>' if upgraded else
         '<b>[Warsh | FOMC 의사록 · 반응함수]</b>'),
        f'대상: {meeting_label} · 공개: {_date_ko(rel)} (미국 동부시간 오후 2시)',
        '',
        '<b>한눈에 보기</b>',
        ('• <b>정책 결정</b> | 참가자 전원 25bp 인상 지지 · FOMC 표결 12대 0 · 3.75~4.00%'
         if stmt_date == '2026-09-16' and known('all_support') and known('unanimous_vote')
         else '• <b>정책 결정</b> | 참석자 의견과 실제 의결 결과를 별도 확인'),
        ('• <b>연말 경로</b> | 대부분이 추가 인상 1회 적절할 가능성 평가 · 다음 회의 확정 아님'
         if known('most_yearend') else
         '• <b>연말 경로</b> | 추가 인상 우세 여부의 공식 근거 자동 검증 보류'),
        ('• <b>물가</b> | 유가·AI 인프라 투자발 압력, 서비스·근원 재화 상승률 주시'
         if known('ai_inflation') and known('core_services_ex_housing') and known('ai_core_goods') else
         '• <b>물가</b> | 세부 위험 판단 확인 필요'),
        ('• <b>고용·성장</b> | 완전고용 근접, 노동이동성 저하 · 투자·소비는 견조'
         if known('employment_stable') and known('employment_low_dynamism') and known('growth_solid') else
         '• <b>고용·성장</b> | 공식 문구 확인 필요'),
        ('• <b>대차대조표</b> | 충분한 준비금 유지와 국채시장 위기 대비 · QT 재개 결정 아님'
         if known('ample_reserves') and known('few_treasury') else
         '• <b>대차대조표</b> | 시행지침 및 참가자 제안 구분 필요'),
        '',
    ]
    lines += group('금리경로 · 참가자 강도', [
        ('many_risk', '• 많은 참석자: 강한 수요·추가 공급 충격에 대비하는 위험관리 차원의 높은 금리경로'),
        ('number_modal', '• 상당수 참석자: 위험관리만이 아니라 기본 경제전망 자체로 높은 금리경로 필요'),
        ('several_not_restrictive', '• 여러 명: 현 정책금리가 비제약적이거나 제약 정도가 약하다고 평가'),
        ('couple_neutral', '• 두어 명: 중립금리 추정치를 상향'),
        ('almost_all_risks', '• 거의 모든 참석자: 물가 위험은 상방, 고용 위험은 줄어 대체로 균형'),
    ])
    if sep:
        lines.append(f"• <b>당시 점도표</b> | 연말 {sep['yearend']:.1f}% · 다음 해 {sep['nextyear']:.1f}% (약속 아님)")
    lines += ['', *group('대차대조표 · 실제 지침과 제안 구분', [
        ('few_treasury', '• 몇몇 참석자: 현재 국채시장은 원활하게 작동 중'),
        ('treasury_stress', '• 같은 논의: 시장 기능 장애에 대비하는 사전 대응 필요'),
        ('strengthen_tools', '• 연준 대응 전략·의사소통·시장안정 수단 강화 제안'),
        ('limit_footprint', '• 다만 연준의 국채시장 영향력·개입 범위는 제한할 필요'),
        ('principal_reinvestment', '• 당시 확정 지침: 국채 원금 전액 차환·기관채 원금 단기국채 재투자 → 총량축소형 QT 재개로 단정 금지'),
    ])]
    lines += group('물가 · 공급과 수요 압력', [
        ('inflation_sticky', '• 참가자들: 물가가 여전히 높고 최근 충분한 둔화 진전이 없음'),
        ('ai_inflation', '• 지정학적 유가 상승과 AI 관련 설비투자가 물가상승 압력에 기여'),
        ('core_services_ex_housing', '• 여러 명: 주거비 제외 근원서비스 상승률이 여전히 높음'),
        ('ai_core_goods', '• 여러 명: 근원 재화 상승률도 높음 · 관세 영향은 약해지고 AI 설비투자 영향 확대'),
        ('inflation_upside', '• 참가자들: 물가 전망 위험은 상방으로 치우침'),
        ('inflation_upside_more', '• 일부: 최근 물가 위험의 상방 쏠림이 심해짐'),
        ('inflation_expectations_warning', '• 일부: 5년 넘게 목표 2% 상회한 물가가 향후 기대인플레이션·임금·가격 결정에 전이될 위험'),
        ('inflation_exp_anchored', '• 중장기 기대인플레이션은 당시 공식 목표 2%와 대체로 일치'),
    ])
    lines += group('고용 · 전체와 AI 숙련인력 분리', [
        ('employment_stable', '• 참가자들: 노동시장은 대체로 안정적이며 최대고용에 근접'),
        ('employment_majority', '• 과반: 고용 증가가 노동력 증가를 소폭 웃도는 등 최근 다소 강화'),
        ('employment_low_dynamism', '• 여러 명: 채용·해고·구직 성공률은 낮고 장기실업률은 높아 노동시장 이동성 저하'),
        ('employment_ai_skilled_wages', '• 일부: AI 관련 숙련인력 수요로 해당 인력 임금은 강세'),
        ('employment_moderate_wages', '• 반면 일부: 전체 임금 상승률은 완만하며 노동시장 자체가 물가 압력 원천은 아니라는 평가'),
        ('employment_outlook_balanced', '• 참가자들: 실업률은 현 수준 부근 유지 전망 · 고용 위험 상·하방 대체로 균형'),
    ])
    lines += group('성장 · AI 설비투자와 소비 양극화', [
        ('growth_solid', '• 경제활동 견조한 확장 · 기업투자·소비가 공급 충격을 상쇄'),
        ('growth_momentum', '• 여러 명: 기저 성장 모멘텀 강화'),
        ('ai_surprise', '• 여러 명: AI 인프라 투자 규모와 속도가 지속적으로 예상 상회'),
        ('financial_supportive', '• 많은 참석자: 장기금리 상승에도 금융여건은 성장에 우호적'),
        ('housing_exception', '• 다만 몇몇은 높은 주택담보대출 금리로 주택부문은 예외라고 평가'),
        ('consumer_high_income', '• 여러 명: 주가 상승이 고소득층 소비를 뒷받침'),
        ('consumer_low_income', '• 여러 명: 저·중소득층은 높은 에너지 가격으로 실질 가처분소득 부담'),
        ('productivity_future_uncertain', '• AI는 장기 생산성·잠재성장에 긍정적일 수 있지만 효과의 크기·시점은 불확실'),
        ('ai_cyber_risk', '• 몇몇: 사이버보안 등 AI 도입 위험은 오히려 생산성을 낮출 가능성'),
    ])
    lines += ['<b>시장보고 · 참가자 합의와 구분</b>']
    if known('ai_private_debt_term_premium'):
        lines.append('• 당시 시장보고는 AI 인프라용 대규모 민간채권 발행과 자금경쟁을 장기국채 기간프리미엄 상승 요인으로 언급')
    if known('yields_2y10y_35bp'):
        lines.append('• 회의 사이 미국 국채 2~10년 구간 수익률 약 35bp 상승 · 현재 거래일 움직임이 아님')
    if not known('ai_private_debt_term_premium') and not known('yields_2y10y_35bp'):
        lines.append('• 시장 관련 세부 근거 확인 필요')
    lines += [
        '',
        '<b>먼저 볼 실패 경로·다음 일정</b>',
        '• 3개월 근원 PCE 둔화와 전년 동월비·새 통계방식 차이를 분리. 의사록 내 직원 추정은 발표 당시 정보이며 최신 확정치로 재사용하지 않음',
        '• 유가·AI 투자비 상승 → 물가 전이와 소비·고용 위축 중 어느 경로가 우세한지 확인',
        '• 장기국채 금리·기업채 조달비·주택대출 비용이 높아져 투자·채택 일정이 밀리는지 점검',
        f'• {followup}의 실제 금리 결정과 신규 성명 확인 · 의사록은 과거 회의 기록',
        f'• 시장 기대: {market_status()}',
        '',
        '<b>원천</b>',
        link('연준 의사록', minutes_link) + ' · ' +
        link('연준 공개문', press_link) + ' · ' +
        link('연준 일정', FED_CAL),
    ]
    if sep and sep.get('url'):
        lines.append(link('당시 공식 점도표', sep['url']))
    # 텔레그램에서 길이 초과를 조용히 자르지 않도록 전송 전에 검사한다.
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
    # 이미 전송된 동일 회의도 승인된 상세 형식 업그레이드는 한 번만 보강 송출한다.
    # 결측/실패 상태에서는 최신 의사록 자체를 발송 처리하지 않는다.
    delta = (datetime.now(ET).date() - datetime.fromisoformat(rel).date()).days
    eligible = 0 <= delta <= 7
    old_version = int(old.get('last_sent_format_version') or 2)
    upgraded = bool(already and eligible and old_version < FORMAT_VERSION)
    should_send = FORCE or (not already and eligible) or upgraded

    new = {
        'schema_version': FORMAT_VERSION,
        'last_statement_date': stmt_date,
        'last_minutes_url': final,
        'last_release_date': rel,
        'last_sent_key': key if already else old.get('last_sent_key'),
        'last_sent_format_version': old.get('last_sent_format_version'),
        'message_id': old.get('message_id'),
        'previous_message_id': old.get('previous_message_id'),
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
        receipt = send(message(stmt_date, final, press_url, rel, signals, upgraded=upgraded))
        new.update({
            'sent': True, 'last_sent_key': key,
            'message_id': receipt, 'delivery_status': 'confirmed',
            'last_sent_format_version': FORMAT_VERSION,
            'previous_message_id': old.get('message_id') if upgraded else old.get('previous_message_id'),
            'format_upgrade_sent': upgraded,
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
        'format_upgrade_sent': upgraded,
        'message_id': new.get('message_id'),
        'most_yearend': signals['most_yearend'],
        'many_risk': signals['many_risk'],
        'number_modal': signals['number_modal'],
        'balance_sheet_qt_claim': False,
        'delivery_status': new.get('delivery_status'),
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
