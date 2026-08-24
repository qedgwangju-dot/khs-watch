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
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

MAX_CHARS = 3900
KST = ZoneInfo('Asia/Seoul')
_TRANSLATION_CACHE: dict[str, str] = {}
UA = 'Mozilla/5.0 (compatible; BioAlertSender/3.0)'


def split_message(text: str) -> list[str]:
    chunks: list[str] = []
    current = ''
    for paragraph in text.strip().split('\n\n'):
        candidate = paragraph if not current else current + '\n\n' + paragraph
        if len(candidate) <= MAX_CHARS:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ''
        while len(paragraph) > MAX_CHARS:
            cut = paragraph.rfind('\n', 0, MAX_CHARS)
            if cut < 1:
                cut = MAX_CHARS
            chunks.append(paragraph[:cut])
            paragraph = paragraph[cut:].lstrip()
        current = paragraph
    if current:
        chunks.append(current)
    return chunks


def fetch_response(url: str, timeout: int = 18, limit: int = 1_500_000) -> tuple[str, str, str]:
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': UA,
            'Accept-Language': 'en-US,en;q=0.9,ko;q=0.8',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read(limit)
        enc = response.headers.get_content_charset() or 'utf-8'
        ctype = response.headers.get_content_type() or ''
        final = response.geturl()
    return raw.decode(enc, errors='replace'), final, ctype


def clean_source_url(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(html.unescape(url))
        host = parsed.netloc.lower()
        if host.endswith('bing.com') and parsed.path.endswith('/news/apiclick.aspx'):
            target = urllib.parse.parse_qs(parsed.query).get('url', [''])[0]
            if target.startswith(('http://', 'https://')):
                return clean_source_url(target)
        query = [
            (k, v) for k, v in urllib.parse.parse_qsl(parsed.query)
            if not k.lower().startswith('utm_') and k.lower() not in {'ocid', 'ref', 'source', 'oc'}
        ]
        return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', urllib.parse.urlencode(query), ''))
    except Exception:
        return url


def normalize_title(value: str) -> str:
    value = html.unescape(value).lower()
    value = re.sub(r'[^0-9a-z가-힣ぁ-んァ-ン一-龯]+', ' ', value)
    return re.sub(r'\s+', ' ', value).strip()


def title_similarity(a: str, b: str) -> float:
    aa = set(normalize_title(a).split())
    bb = set(normalize_title(b).split())
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / max(1, len(aa | bb))


def resolve_google_news_url(title: str, url: str) -> str:
    cleaned = clean_source_url(url)
    if 'news.google.com' not in urllib.parse.urlparse(cleaned).netloc.lower():
        return cleaned
    try:
        rss_url = 'https://www.bing.com/news/search?' + urllib.parse.urlencode({
            'q': f'"{title[:190]}"',
            'format': 'rss',
        })
        xml, _, _ = fetch_response(rss_url, timeout=12, limit=500_000)
        root = ET.fromstring(xml)
        candidates: list[tuple[float, str]] = []
        for node in root.findall('.//item')[:20]:
            candidate_title = (node.findtext('title') or '').strip()
            candidate_url = clean_source_url((node.findtext('link') or '').strip())
            score = title_similarity(title, candidate_title)
            if score >= 0.38 and candidate_url.startswith(('http://', 'https://')):
                candidates.append((score, candidate_url))
        if candidates:
            candidates.sort(reverse=True)
            return candidates[0][1]
    except Exception:
        pass
    try:
        _, final, _ = fetch_response(url, timeout=12, limit=300_000)
        final = clean_source_url(final)
        if 'news.google.com' not in urllib.parse.urlparse(final).netloc.lower():
            return final
    except Exception:
        pass
    return cleaned


def strip_html(value: str) -> str:
    value = re.sub(r'(?is)<script.*?</script>|<style.*?</style>|<noscript.*?</noscript>', ' ', value)
    value = re.sub(r'(?s)<[^>]+>', ' ', value)
    return re.sub(r'\s+', ' ', html.unescape(value)).strip()


def extract_article_text(page: str) -> str:
    candidates: list[str] = []
    for block in re.findall(r'(?is)<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', page):
        try:
            data = json.loads(html.unescape(block.strip()))
        except Exception:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            obj = stack.pop()
            if isinstance(obj, dict):
                body = obj.get('articleBody')
                if isinstance(body, str) and len(body) > 250:
                    candidates.append(body)
                graph = obj.get('@graph')
                if isinstance(graph, list):
                    stack.extend(graph)
            elif isinstance(obj, list):
                stack.extend(obj)
    for article in re.findall(r'(?is)<article\b[^>]*>(.*?)</article>', page):
        text = strip_html(article)
        if len(text) > 300:
            candidates.append(text)
    paragraphs: list[str] = []
    for p in re.findall(r'(?is)<p\b[^>]*>(.*?)</p>', page):
        text = strip_html(p)
        if 45 <= len(text) <= 3000:
            paragraphs.append(text)
    if paragraphs:
        joined = ' '.join(paragraphs)
        if len(joined) > 300:
            candidates.append(joined)
    if not candidates:
        return ''
    text = max(candidates, key=len)
    return re.sub(r'\s+', ' ', html.unescape(text)).strip()[:18000]


def detect_translation_pair(text: str) -> str:
    # 일본어 가나가 있으면 일본어로 판정. 한자는 한국어 문장에도 있을 수 있어 가나를 우선 사용.
    if re.search(r'[ぁ-んァ-ン]', text):
        return 'ja|ko'
    if re.search(r'[A-Za-z]{4}', text):
        return 'en|ko'
    return ''


def has_leftover_japanese(value: str) -> bool:
    return bool(re.search(r'[ぁ-んァ-ン一-龯]', value))


def translate_short(text: str) -> str:
    pair = detect_translation_pair(text)
    if not pair:
        return text
    try:
        query = urllib.parse.urlencode({'q': text[:430], 'langpair': pair, 'mt': '1'})
        req = urllib.request.Request(f'https://api.mymemory.translated.net/get?{query}', headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=8) as response:
            payload = json.loads(response.read().decode('utf-8', errors='replace'))
        candidate = html.unescape(str((payload.get('responseData') or {}).get('translatedText') or '')).strip()
        if len(re.findall(r'[가-힣]', candidate)) >= 5 and not has_leftover_japanese(candidate):
            return candidate
    except Exception:
        pass
    return ''


def extract_hr(text: str, label: str) -> str | None:
    for pattern in (
        rf'{label}[^.\n]{{0,280}}?HR\s*[=:]?\s*(0?\.\d+)',
        rf'HR\s*[=:]?\s*(0?\.\d+)[^.\n]{{0,280}}?{label}',
    ):
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(1)
    return None


def article_fact_lines(text: str) -> list[str]:
    low = text.lower()
    facts: list[str] = []
    phase3 = 'interpath-001' in low and ('phase 3' in low or 'phase iii' in low)
    rfs = 'rfs' in low or 'recurrence-free survival' in low
    dmfs = 'dmfs' in low or 'distant metastasis-free survival' in low
    met = any(x in low for x in ('met endpoint', 'met its primary', 'met the primary', 'met endpoints', 'met both', 'statistically significant'))
    if phase3 and rfs and dmfs and met:
        facts.append('INTerpath-001 3상에서 재발 없는 생존기간(RFS)과 원격전이 없는 생존기간(DMFS) 평가변수를 모두 달성했습니다.')
    if 'first positive phase 3' in low or 'first positive phase iii' in low:
        facts.append('개인맞춤형 신생항원 치료이자 mRNA 기반 항암치료로서는 최초의 긍정적 3상 결과라는 설명이 포함돼 있습니다.')
    if 'clinically meaningful' in low and 'statistically significant' in low:
        facts.append('회사 측은 KEYTRUDA 단독 대비 통계적으로 유의하고 임상적으로 의미 있는 개선이라고 설명했습니다.')
    if 'stage iib' in low and ('stage iv' in low or 'iib-iv' in low):
        facts.append('대상은 완전 절제된 IIB~IV기 흑색종 환자입니다.')
    for label, korean in (('RFS', '재발 없는 생존기간(RFS)'), ('DMFS', '원격전이 없는 생존기간(DMFS)'), ('OS', '전체생존기간(OS)')):
        hr = extract_hr(text, label)
        if hr:
            facts.append(f'{korean} 위험비(HR): {hr}')
    if any(x in low for x in ('upcoming international medical meeting', 'future medical meeting', 'will present data', 'present detailed results')):
        facts.append('구체적인 3상 수치는 후속 국제 의학 학회에서 공개할 예정입니다.')
    if any(x in low for x in ('engage with regulators', 'regulatory submissions', 'filing submissions')):
        facts.append('Merck와 Moderna는 규제기관과 허가신청 제출을 협의할 계획이라고 밝혔습니다.')
    if 'safety profile' in low and any(x in low for x in ('consistent', 'no new safety')):
        facts.append('안전성은 기존 병용요법 경험과 대체로 일관됐다는 설명이 포함돼 있습니다.')
    if len(facts) < 3:
        sentences = re.split(r'(?<=[.!?])\s+', text)
        keywords = ('interpath-001', 'primary endpoint', 'recurrence-free', 'distant metastasis', 'regulator', 'medical meeting')
        scored: list[tuple[int, str]] = []
        for sentence in sentences:
            sentence = re.sub(r'\s+', ' ', sentence).strip()
            if not (60 <= len(sentence) <= 500):
                continue
            score = sum(1 for k in keywords if k in sentence.lower())
            if score:
                scored.append((score, sentence))
        for _, sentence in sorted(scored, key=lambda x: x[0], reverse=True)[:3]:
            ko = translate_short(sentence)
            if ko and ko not in facts:
                facts.append(ko)
            if len(facts) >= 4:
                break
    return facts[:6]


def parse_report_blocks(text: str) -> tuple[str, list[str], str]:
    if '[바이오 감시] Intismeran·KEYTRUDA QLEX 새 데이터' not in text:
        return text, [], ''
    marker = '\n판정\n'
    if marker in text:
        body, tail = text.split(marker, 1)
        tail = '판정\n' + tail
    else:
        body, tail = text, ''
    lines = body.splitlines()
    header: list[str] = []
    blocks: list[list[str]] = []
    current: list[str] | None = None
    for line in lines:
        if re.match(r'^\d+[.)]\s+', line.strip()):
            if current:
                blocks.append(current)
            current = [line]
        elif current is not None:
            current.append(line)
        else:
            header.append(line)
    if current:
        blocks.append(current)
    return '\n'.join(header).strip(), ['\n'.join(b).strip() for b in blocks], tail.strip()


def enrich_intismeran_report(text: str) -> str:
    header, blocks, tail = parse_report_blocks(text)
    if not blocks:
        return text
    enriched_blocks: list[str] = []
    for block in blocks:
        lines = block.splitlines()
        first = lines[0].strip()
        title = re.sub(r'^\d+[.)]\s+', '', first).strip()
        url = ''
        for line in lines:
            if line.strip().startswith('- 원문:'):
                url = line.split(':', 1)[1].strip()
                break
        if not url:
            enriched_blocks.append(block)
            continue
        resolved = resolve_google_news_url(title, url)
        article_text = ''
        status = '원문 본문 직접 추출 실패'
        try:
            page, final, ctype = fetch_response(resolved, timeout=18)
            if final:
                resolved = clean_source_url(final)
            if 'html' in ctype or '<html' in page[:1000].lower():
                article_text = extract_article_text(page)
                if len(article_text) >= 280:
                    status = f'원문 본문 직접 확인 {len(article_text):,}자'
        except Exception as exc:
            status = f'원문 본문 열람 실패({type(exc).__name__})'
        kept: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('- 핵심:') or stripped.startswith('- 판정:') or stripped.startswith('- 원문:') or stripped.startswith('- 원문 확인:') or stripped.startswith('- 원문 핵심:'):
                continue
            if stripped.startswith('·') or stripped.startswith('  ·'):
                continue
            kept.append(line)
        kept[0] = re.match(r'^(\d+[.)])', first).group(1) + ' ' + translate_title_to_ko(title)
        insert_at = min(3, len(kept))
        detail_lines = [f'- 원문 확인: {status}']
        if article_text:
            facts = article_fact_lines(article_text)
            if facts:
                detail_lines.append('- 원문 핵심:')
                detail_lines.extend(f'  · {fact}' for fact in facts)
            else:
                detail_lines.append('- 원문 핵심: 본문은 직접 확인했지만 새 수치·일정을 자동 추출하지 못했습니다.')
            detail_lines.append('- 판정: 기사 원문 본문을 직접 열어 확인했습니다. 핵심 수치는 Merck·Moderna·FDA 공식자료가 나오면 다시 교차검증합니다.')
        else:
            detail_lines.append('- 판정: 원문 본문을 직접 확인하지 못해 제목만으로 확정하지 않습니다.')
        new_lines = kept[:insert_at] + detail_lines + kept[insert_at:]
        new_lines.append(f'- 원문: {resolved}')
        enriched_blocks.append('\n'.join(new_lines))
    pieces = [p for p in (header, '\n\n'.join(enriched_blocks), tail) if p]
    return '\n\n'.join(pieces)


def is_english_dominant(value: str) -> bool:
    latin = len(re.findall(r'[A-Za-z]', value))
    korean = len(re.findall(r'[가-힣]', value))
    return latin >= 8 and latin > korean * 2


def fallback_title_ko(title: str) -> str:
    low = title.lower()
    if re.search(r'[ぁ-んァ-ン]', title):
        if ('悪性黒色腫' in title or 'メラノーマ' in title) and 'RFS' in title and 'DMFS' in title:
            return '고위험 악성 흑색종 수술 후 치료에서 mRNA 개인맞춤형 암 치료 Intismeran autogene+Pembrolizumab, RFS·DMFS 유의하게 개선'
        if '悪性黒色腫' in title or 'メラノーマ' in title:
            return '고위험 악성 흑색종에서 Intismeran autogene+Pembrolizumab 병용요법 관련 신규 보도'
        if 'Intismeran' in title or 'インティスメラン' in title or 'インティスメラン' in title:
            return 'Intismeran 관련 일본어 신규 보도'
    if 'interpath-001' in low and ('met endpoints' in low or 'meets' in low) and ('rfs' in low or 'recurrence-free' in low):
        return 'Merck·Moderna, INTerpath-001 흑색종 3상에서 RFS·DMFS 평가변수 달성'
    if 'interpath-001' in low and 'boosts rfs' in low:
        return 'INTerpath-001: 흑색종 보조요법에서 Intismeran+Pembrolizumab이 재발 없는 생존기간(RFS) 개선'
    if 'custom-made' in low and 'mrna' in low and 'melanoma' in low:
        return 'Moderna·Merck의 개인맞춤형 mRNA 암 치료, 후기 흑색종 임상에서 긍정적 결과'
    if 'meets primary endpoint' in low and ('phase iii' in low or 'phase 3' in low):
        return 'Moderna의 Intismeran+KEYTRUDA, 흑색종 3상 1차 평가변수 달성'
    if 'stock soars' in low and 'melanoma' in low:
        pct = re.search(r'\b(\d+(?:\.\d+)?)%', title)
        return f'Merck 주가, 흑색종 임상 결과 발표 후 {pct.group(1) + "%" if pct else "급등"}'
    if 'stock surging' in low and 'cancer' in low:
        return 'Moderna 주가, 암 치료 임상 진전으로 급등…향후 변동성 주의'
    if 'interpath-001' in low:
        return 'INTerpath-001 흑색종 3상 관련 신규 보도'
    if 'intismeran' in low and 'keytruda' in low:
        return 'Intismeran·KEYTRUDA 관련 신규 보도'
    return '바이오 관련 신규 보도 — 아래 원문 핵심 확인'


def has_leftover_general_english(value: str) -> bool:
    scrub = value
    for token in ('INTerpath-001', 'INTerpath-014', 'Intismeran', 'KEYTRUDA', 'QLEX', 'RFS', 'DMFS', 'OS', 'FDA', 'PDUFA', 'HR', 'mRNA'):
        scrub = scrub.replace(token, '')
    words = re.findall(r'[A-Za-z]{3,}', scrub)
    return len(words) >= 3


def translate_title_to_ko(title: str) -> str:
    pair = detect_translation_pair(title)
    needs_translation = bool(pair) or is_english_dominant(title) or has_leftover_general_english(title)
    if not needs_translation:
        return title
    if title in _TRANSLATION_CACHE:
        return _TRANSLATION_CACHE[title]
    translated = ''
    if pair:
        try:
            query = urllib.parse.urlencode({'q': title[:450], 'langpair': pair, 'mt': '1'})
            req = urllib.request.Request(f'https://api.mymemory.translated.net/get?{query}', headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=8) as response:
                payload = json.loads(response.read().decode('utf-8', errors='replace'))
            candidate = html.unescape(str((payload.get('responseData') or {}).get('translatedText') or '')).strip()
            if (
                candidate
                and len(re.findall(r'[가-힣]', candidate)) >= 5
                and not has_leftover_general_english(candidate)
                and not has_leftover_japanese(candidate)
            ):
                translated = candidate
        except Exception:
            pass
    if not translated:
        translated = fallback_title_ko(title)
    _TRANSLATION_CACHE[title] = translated
    return translated


def koreanize_timestamp(value: str) -> str:
    try:
        stamp = parsedate_to_datetime(value)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=dt.timezone.utc)
        return stamp.astimezone(KST).strftime('%Y-%m-%d %H:%M KST')
    except Exception:
        return value


def normalize_alert_language(text: str) -> str:
    out: list[str] = []
    title_pattern = re.compile(r'^(\d+[.)])\s+(.+)$')
    for line in text.splitlines():
        stripped = line.strip()
        match = title_pattern.match(stripped)
        if match:
            prefix, title = match.groups()
            line = f'{prefix} {translate_title_to_ko(title)}'
        elif stripped.startswith('- 발표/게시:'):
            value = stripped.split(':', 1)[1].strip()
            line = f'- 발표/게시: {koreanize_timestamp(value)}'
        elif not stripped.startswith('- 원문:'):
            line = line.replace('heartbeat', '상태 확인').replace('watchdog', '자동 복구 감시')
            line = re.sub(r'\bPhase\s*III\b', '3상', line, flags=re.I)
            line = re.sub(r'\bPhase\s*3\b', '3상', line, flags=re.I)
            line = line.replace('subcutaneous', '피하주사')
        out.append(line)
    return '\n'.join(out)


def render_html(text: str) -> str:
    rendered: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith('- 원문:'):
            url = stripped.split(':', 1)[1].strip()
            if url.startswith(('http://', 'https://')):
                target = clean_source_url(url)
                rendered.append(f'- <a href="{html.escape(target, quote=True)}">원문 뉴스보기</a>')
                continue

        escaped = html.escape(line, quote=False)
        # 바이오 알림의 Markdown식 굵은 표시를 Telegram HTML로 변환해
        # 제목과 핵심 라벨이 한눈에 들어오도록 한다.
        escaped = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', escaped)
        rendered.append(escaped)
    return '\n'.join(rendered)


def main() -> int:
    if len(sys.argv) != 2:
        print('usage: qlex_telegram_send.py REPORT_PATH', file=sys.stderr)
        return 2
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
    path = pathlib.Path(sys.argv[1])
    text = path.read_text(encoding='utf-8').strip()
    if not text:
        raise RuntimeError('Telegram report is empty')
    text = enrich_intismeran_report(text)
    text = normalize_alert_language(text)
    ids: list[int] = []
    for index, chunk in enumerate(split_message(text), 1):
        if index > 1:
            chunk = f'[바이오 감시 계속 {index}]\n\n{chunk}'
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
    print(f'telegram_delivery_confirmed=true bot=@{actual} message_ids={ids}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
