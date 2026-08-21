from __future__ import annotations

import datetime as dt
import html
import json
import os
import pathlib
import re
import sys
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

import qlex_telegram_send as base

KST = ZoneInfo('Asia/Seoul')
CONFIRM_PATH = pathlib.Path('out/intismeran_structured_send_confirmed.json')


def report_blocks(text: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    current: list[str] = []
    for line in text.splitlines():
        if re.match(r'^\d+[.)]\s+', line.strip()):
            if current:
                blocks.append(parse_block(current))
            current = [line]
        elif current:
            if line.strip() == '판정':
                break
            current.append(line)
    if current:
        blocks.append(parse_block(current))
    return [x for x in blocks if x[0] and x[1]]


def parse_block(lines: list[str]) -> tuple[str, str]:
    title = re.sub(r'^\d+[.)]\s+', '', lines[0].strip()).strip() if lines else ''
    url = ''
    for line in lines:
        if line.strip().startswith('- 원문:'):
            url = line.split(':', 1)[1].strip()
            break
    return title, url


def extract_enrollment(text: str) -> str:
    patterns = [
        r'(?:enrolled|included)\s+(\d{1,3}(?:,\d{3})+)\s+(?:patients|participants)',
        r'(\d{1,3}(?:,\d{3})+)\s+(?:patients|participants)',
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return m.group(1)
    return ''


def sentence_candidates(text: str) -> list[str]:
    return [re.sub(r'\s+', ' ', s).strip() for s in re.split(r'(?<=[.!?])\s+', text) if len(s.strip()) >= 30]


def phase3_hr(text: str, label: str) -> str:
    for sentence in sentence_candidates(text):
        low = sentence.lower()
        if 'hr' not in low:
            continue
        if 'phase 2' in low or 'phase ii' in low or 'keynote-942' in low or 'p201' in low:
            continue
        if label.lower() not in low and ({'rfs': 'recurrence-free', 'dmfs': 'distant metastasis', 'os': 'overall survival'}[label.lower()] not in low):
            continue
        m = re.search(r'\bHR\s*[=:]?\s*(0?\.\d+)', sentence, re.I)
        if m:
            return m.group(1)
    return ''


def build_structured_summary(title: str, article_text: str, resolved_url: str) -> str:
    low = article_text.lower()
    title_low = title.lower()
    is_interpath001 = 'interpath-001' in low or 'interpath-001' in title_low
    has_rfs = 'recurrence-free survival' in low or re.search(r'\bRFS\b', article_text)
    has_dmfs = 'distant metastasis-free survival' in low or re.search(r'\bDMFS\b', article_text)
    endpoints_met = any(x in low for x in ('met endpoints', 'met its primary endpoint', 'met the primary endpoint', 'statistically significant'))

    if is_interpath001 and has_rfs and has_dmfs and endpoints_met:
        headline = 'Merck·Moderna, INTerpath-001 흑색종 3상에서 RFS·DMFS 모두 달성'
    else:
        headline = base.translate_title_to_ko(title)

    enrollment = extract_enrollment(article_text)
    stage = '완전 절제된 IIB~IV기 흑색종 환자' if ('stage iib' in low and ('stage iv' in low or 'iib-iv' in low)) else '시험 대상 환자'
    if enrollment:
        trial_line = f'{stage} {enrollment}명'
        if 'randomized 2:1' in low or '2:1' in low:
            trial_line += ', 2:1 무작위 배정'
    else:
        trial_line = f'{stage} — 원문에서 등록인원 직접 확인되지 않음'

    if has_rfs and has_dmfs and ('clinically meaningful' in low and 'statistically significant' in low):
        result_line = 'Intismeran+KEYTRUDA가 KEYTRUDA 단독 대비 RFS·DMFS를 모두 통계적으로 유의하고 임상적으로 의미 있게 개선'
    elif has_rfs and has_dmfs and endpoints_met:
        result_line = 'Intismeran+KEYTRUDA가 RFS·DMFS 평가변수를 모두 달성'
    else:
        result_line = '원문에서 핵심 효능 결과를 자동 확정하지 못함'

    if 'first positive phase 3' in low or 'first positive phase iii' in low:
        meaning_line = '개인맞춤형 신생항원 치료이자 mRNA 기반 항암치료의 첫 긍정적 3상 결과'
    elif is_interpath001 and endpoints_met:
        meaning_line = '개인맞춤형 mRNA 항암치료의 후기 임상 플랫폼 검증이 강화됨'
    else:
        meaning_line = '원문의 임상적 의미를 추가 확인해야 함'

    rfs_hr = phase3_hr(article_text, 'RFS')
    dmfs_hr = phase3_hr(article_text, 'DMFS')
    os_hr = phase3_hr(article_text, 'OS')
    missing: list[str] = []
    if not rfs_hr:
        missing.append('3상 RFS HR')
    if not dmfs_hr:
        missing.append('3상 DMFS HR')
    if not rfs_hr or not dmfs_hr:
        missing.append('정확한 위험감소율')
    if not os_hr:
        missing.append('OS 세부값')
    unpublished_line = '·'.join(missing) + '은 아직 미공개' if missing else f'3상 RFS HR {rfs_hr}, DMFS HR {dmfs_hr}'

    next_parts: list[str] = []
    if any(x in low for x in ('upcoming international medical meeting', 'future medical meeting', 'will present data', 'present detailed results')):
        next_parts.append('상세 데이터를 후속 국제 의학 학회에서 공개')
    if any(x in low for x in ('engage with regulators', 'regulatory submissions', 'filing submissions', 'discuss with regulators')):
        next_parts.append('Merck·Moderna가 규제기관과 허가신청 제출 협의')
    next_line = ' → '.join(next_parts) if next_parts else '후속 데이터 공개·허가 일정은 원문에서 추가 확인 필요'

    if 'safety profile' in low and ('consistent' in low or 'no new safety' in low or 'no new signals' in low):
        safety_line = '기존 병용요법 경험과 대체로 일관됐고 새로운 안전성 신호는 없었다는 설명'
    elif 'no new safety' in low or 'no new signals' in low:
        safety_line = '새로운 안전성 신호 없음'
    else:
        safety_line = '안전성 세부 내용은 원문에서 직접 확인되지 않음'

    alteogen_line = ('이번 흑색종 3상에는 ALT-B4가 직접 사용된 것은 아닙니다. '
                     '다만 Intismeran 병용영역 확대 후 해당 적응증에서 KEYTRUDA QLEX 사용·허가가 확대되면 '
                     '알테오젠 판매 마일스톤·후속 로열티 기반이 넓어질 수 있습니다.')

    lines = [
        f'**{headline}**',
        '',
        f'- **시험:** {trial_line}',
        f'- **결과:** {result_line}',
        f'- **의미:** {meaning_line}',
        f'- **아직 미공개:** {unpublished_line}',
        f'- **다음 일정:** {next_line}',
        f'- **안전성:** {safety_line}',
        f'- **알테오젠 관점:** {alteogen_line}',
        '- **원문 확인:** 기사 본문 직접 열람',
        f'- 원문: {resolved_url}',
    ]
    return '\n'.join(lines)


def build_message(report_text: str) -> str:
    summaries: list[str] = []
    for title, url in report_blocks(report_text):
        resolved = base.resolve_google_news_url(title, url)
        try:
            page, final, ctype = base.fetch_response(resolved, timeout=20)
            if final:
                resolved = base.clean_source_url(final)
            if not ('html' in ctype or '<html' in page[:1000].lower()):
                continue
            article_text = base.extract_article_text(page)
        except Exception:
            continue
        if len(article_text) < 350:
            continue
        summaries.append(build_structured_summary(title, article_text, resolved))
    return '\n\n'.join(summaries).strip()


def render_html(text: str) -> str:
    rendered: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith('- 원문:'):
            url = stripped.split(':', 1)[1].strip()
            rendered.append(f'- <a href="{html.escape(url, quote=True)}">원문 뉴스보기</a>')
            continue
        escaped = html.escape(line, quote=False)
        escaped = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', escaped)
        rendered.append(escaped)
    return '\n'.join(rendered)


def send_message(text: str) -> list[int]:
    token = (os.getenv('BIO_TELEGRAM_BOT_TOKEN') or '').strip()
    chat_id = (os.getenv('BIO_TELEGRAM_CHAT_ID') or '').strip()
    expected = (os.getenv('EXPECTED_TELEGRAM_BOT_USERNAME') or '').strip().lstrip('@')
    if not token or not chat_id or not expected:
        raise RuntimeError('bio Telegram token/chat_id/expected username is missing')
    with urllib.request.urlopen(f'https://api.telegram.org/bot{token}/getMe', timeout=25) as response:
        identity = json.loads(response.read().decode('utf-8'))
    actual = str((identity.get('result') or {}).get('username') or '')
    if not identity.get('ok') or actual.lower() != expected.lower():
        raise RuntimeError(f'Wrong Telegram bot: expected @{expected}, got @{actual or "unknown"}')

    ids: list[int] = []
    for chunk in base.split_message(text):
        payload = urllib.parse.urlencode({
            'chat_id': chat_id,
            'text': render_html(chunk),
            'parse_mode': 'HTML',
            'disable_web_page_preview': 'true',
        }).encode('utf-8')
        request = urllib.request.Request(f'https://api.telegram.org/bot{token}/sendMessage', data=payload, method='POST')
        with urllib.request.urlopen(request, timeout=25) as response:
            result = json.loads(response.read().decode('utf-8'))
        if not result.get('ok'):
            raise RuntimeError(f'Telegram rejected message: {result}')
        ids.append(int(result['result']['message_id']))
    return ids


def main() -> int:
    CONFIRM_PATH.unlink(missing_ok=True)
    if len(sys.argv) != 2:
        print('usage: intismeran_structured_telegram_send.py REPORT_PATH', file=sys.stderr)
        return 2
    report = pathlib.Path(sys.argv[1]).read_text(encoding='utf-8').strip()
    message = build_message(report)
    if not message:
        print('intismeran_structured_alert_skipped=true reason=original_body_not_verified')
        return 0
    ids = send_message(message)
    CONFIRM_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIRM_PATH.write_text(json.dumps({
        'status': 'confirmed',
        'confirmed_at_kst': dt.datetime.now(KST).isoformat(timespec='seconds'),
        'message_ids': ids,
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'intismeran_structured_delivery_confirmed=true message_ids={ids}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

# Telegram route smoke trigger 2026-08-21
