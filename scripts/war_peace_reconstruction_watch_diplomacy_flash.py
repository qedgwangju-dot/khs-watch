#!/usr/bin/env python3
"""종전·에너지 감시 최종 보강: Walter Bloomberg 실시간 외교/에너지 정책 신호.

기존 war-peace 감지·상태·텔레그램 경로는 그대로 사용하고,
1) 이란 외무장관의 중국 방문/왕이 회담,
2) 중국계 주체의 이란 위성영상 제공 보도(미확인),
3) 크렘린의 트럼프 에너지 표적 휴전 제안 긍정 평가,
4) 크렘린의 제재 해제→세계 에너지 가격 하락 발언
만 단계별로 추가한다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html as html_lib
import re
from email.utils import format_datetime

import war_peace_reconstruction_watch_energy_ceasefire as prev

watch = prev.watch
runner = prev.runner
base = prev.base
guard = prev.guard

_prev_google_news = watch.google_news
_prev_score = watch.score_item
_prev_item_id = watch.item_id
_prev_topic_label = watch.topic_label
_prev_verdict = guard._verdict

WALTER_SENTINEL = "__WALTER_BLOOMBERG_WAR_PEACE_FLASH__"
WALTER_PUBLIC_URL = "https://t.me/s/WalterBloomberg"

FLASH_QUERIES = [
    WALTER_SENTINEL,
    'site:reuters.com (Araghchi OR "Iranian foreign minister") (China OR Beijing OR "Wang Yi") (visit OR meeting OR talks) when:2d',
    '(Araghchi OR "Iranian foreign minister" OR 아라치 OR 이란 외무장관) (China OR Beijing OR 중국 OR 베이징 OR "Wang Yi" OR 왕이) (visit OR meeting OR 회담 OR 방문) when:2d',
    'site:reuters.com (China OR Chinese) Iran ("satellite images" OR "satellite imagery") ("US base" OR "U.S. base") when:3d',
    '(Kremlin OR Peskov OR 크렘린 OR 페스코프) Trump Ukraine ("energy targets" OR "energy facilities" OR 에너지 시설 OR 에너지 표적) ("good idea" OR welcomes OR 환영 OR "좋은 생각") when:2d',
    '(Kremlin OR Peskov OR 크렘린 OR 페스코프) sanctions ("world energy prices" OR "global energy prices" OR 에너지 가격) (lower OR fall OR down OR 하락) when:2d',
]
watch.QUERIES = FLASH_QUERIES + list(watch.QUERIES)

IRAN_FM_TERMS = ('araghchi', 'iranian foreign minister', 'iran foreign minister', '아라치', '이란 외무장관')
CHINA_TERMS = ('china', 'chinese', 'beijing', 'wang yi', '중국', '중국계', '베이징', '왕이')
VISIT_TERMS = ('visit', 'visiting', 'travel to', 'meet wang yi', 'meeting with wang yi', 'talks with wang yi', '방문', '회담', '왕이와 회담', '왕이 외교부장')
SATELLITE_TERMS = ('satellite image', 'satellite images', 'satellite imagery', '위성 이미지', '위성영상', '위성 영상')
US_BASE_TERMS = ('u.s. base', 'us base', 'american base', 'u.s. military base', '미국 기지', '미군 기지')
PROVIDE_TERMS = ('provided', 'supplied', 'gave', 'provide', '제공', '넘겼', '전달')
KREMLIN_TERMS = ('kremlin', 'peskov', '크렘린', '페스코프')
TRUMP_TERMS = ('trump', '트럼프')
UKRAINE_TERMS = ('ukraine', 'ukrainian', '우크라이나', '우크라')
ENERGY_TARGET_TERMS = ('energy target', 'energy targets', 'energy facility', 'energy facilities', 'energy infrastructure', 'refinery', 'diesel facility', '에너지 시설', '에너지 표적', '에너지 인프라', '정유시설', '정유 공장', '경유 시설')
POSITIVE_IDEA_TERMS = ('good idea', 'welcomes', 'welcome', 'positive idea', 'supports the proposal', 'support the proposal', '좋은 생각', '좋은 아이디어', '긍정 평가', '환영')
SANCTION_TERMS = ('sanctions are lifted', 'sanctions lifted', 'lifting sanctions', 'lift sanctions', 'sanction relief', '제재가 해제', '제재 해제', '제재 완화')
WORLD_ENERGY_PRICE_TERMS = ('world energy prices', 'global energy prices', 'energy prices', 'oil prices', 'fuel prices', '세계 에너지 가격', '글로벌 에너지 가격', '국제 에너지 가격', '유가')
PRICE_DOWN_TERMS = ('will go down', 'would go down', 'will fall', 'would fall', 'lower prices', 'bring down', 'decline', '하락', '낮아질', '떨어질')


def _clean_html(raw: str) -> str:
    raw = re.sub(r'<br\s*/?>', '\n', raw, flags=re.I)
    raw = re.sub(r'<[^>]+>', ' ', raw)
    raw = html_lib.unescape(raw)
    raw = re.sub(r'[ \t]+', ' ', raw)
    raw = re.sub(r'\n\s*\n+', '\n', raw)
    return raw.strip()


def _walter_rows():
    try:
        page = watch.req(WALTER_PUBLIC_URL, 15).decode('utf-8', errors='ignore')
    except Exception as exc:
        return [], f"WalterBloomberg: {type(exc).__name__}"

    chunks = page.split('<div class="tgme_widget_message_wrap js-widget_message_wrap">')[1:]
    rows = []
    now = dt.datetime.now(dt.timezone.utc)
    for chunk in chunks[-40:]:
        post = re.search(r'data-post="WalterBloomberg/(\d+)"', chunk)
        text_match = re.search(r'<div class="tgme_widget_message_text[^>]*>(.*?)</div>', chunk, re.S)
        time_match = re.search(r'<time datetime="([^"]+)"', chunk)
        if not post or not text_match:
            continue
        text = _clean_html(text_match.group(1))
        if not text:
            continue
        published = ''
        if time_match:
            try:
                stamp = dt.datetime.fromisoformat(time_match.group(1).replace('Z', '+00:00'))
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=dt.timezone.utc)
                stamp = stamp.astimezone(dt.timezone.utc)
                if (now - stamp).total_seconds() > 24 * 3600:
                    continue
                published = format_datetime(stamp)
            except Exception:
                pass
        title = text if len(text) <= 300 else text[:297].rstrip() + '...'
        rows.append({
            'title': title,
            'title_original': title,
            'title_ko': '',
            'link': f"https://t.me/WalterBloomberg/{post.group(1)}",
            'published': published,
            'source': 'Walter Bloomberg',
            'description': text,
            'article_text': text,
        })
    return rows, None


def google_news(query):
    if query == WALTER_SENTINEL:
        return _walter_rows()
    return _prev_google_news(query)

watch.google_news = google_news


def _text(row):
    return ' '.join([
        row.get('title_original', ''), row.get('title_ko', ''), row.get('description', ''),
        row.get('article_text', ''), ' '.join(row.get('signals_ko', [])),
    ]).lower()


def _has(text, terms):
    return any(term in text for term in terms)


def _marks(row):
    text = _text(row)
    marks = []

    if _has(text, IRAN_FM_TERMS) and _has(text, CHINA_TERMS) and _has(text, VISIT_TERMS):
        marks.append('이란외무장관중국방문')

    if ('iran' in text or '이란' in text) and _has(text, CHINA_TERMS) and _has(text, SATELLITE_TERMS) and _has(text, US_BASE_TERMS) and _has(text, PROVIDE_TERMS):
        marks.append('중국계위성영상제공보도')

    energy_context = _has(text, KREMLIN_TERMS) and _has(text, TRUMP_TERMS) and _has(text, UKRAINE_TERMS) and _has(text, ENERGY_TARGET_TERMS)
    if energy_context and _has(text, POSITIVE_IDEA_TERMS):
        marks.append('크렘린에너지휴전긍정평가')

    if _has(text, KREMLIN_TERMS) and _has(text, SANCTION_TERMS) and _has(text, WORLD_ENERGY_PRICE_TERMS) and _has(text, PRICE_DOWN_TERMS):
        marks.append('크렘린제재해제에너지가격하락발언')

    return sorted(set(marks))


def _korean_title(marks):
    if '크렘린에너지휴전긍정평가' in marks:
        return '크렘린, 트럼프의 우크라이나 에너지 표적 휴전 제안에 “좋은 생각” 평가'
    if '크렘린제재해제에너지가격하락발언' in marks:
        return '크렘린 “제재가 해제되면 세계 에너지 가격이 하락할 것”'
    if '이란외무장관중국방문' in marks:
        return '이란 아라치 외무장관, 중국 방문·왕이 외교부장 회담 일정 신호'
    if '중국계위성영상제공보도' in marks:
        return '중국계 주체가 이란에 미군기지 위성영상을 제공했다는 보도'
    return ''


def _signals(marks):
    out = []
    if '이란외무장관중국방문' in marks:
        out.append('이란 아라치 외무장관의 중국 방문·왕이 외교부장 회담 일정 신호 — 중국 중재채널 확대 여부 추적')
        out.append('확정 수준: 방문·회담 일정 단계 — 실제 회담 개최와 공동발표 내용은 후속 확인')
    if '중국계위성영상제공보도' in marks:
        out.append('보도: 중국계 주체가 미국 기지 공격 전 이란에 위성영상을 제공했다는 의혹')
        out.append('확정 수준: 중국 정부 직접 관여는 미확인 — 중국 외교부는 근거 없는 비난이라고 반박')
    if '크렘린에너지휴전긍정평가' in marks:
        out.append('크렘린: 트럼프의 우크라이나 에너지 표적 휴전 제안을 “좋은 생각”으로 긍정 평가')
        out.append('확정 수준: 러시아의 긍정 평가 단계 — 정식 합의·발효·실제 공격 중단과는 구분')
    if '크렘린제재해제에너지가격하락발언' in marks:
        out.append('크렘린: 대러 제재가 해제되면 세계 에너지 가격이 하락할 것이라고 주장')
        out.append('시장 경로: 제재 완화 → 러시아 원유·제품 공급 접근성 확대 → 유가·디젤 위험프리미엄 완화 가능성')
    return out


def score_item(row, now):
    marks = _marks(row)
    if not marks:
        return _prev_score(row, now)

    row['diplomacy_flash_marks'] = marks
    row['title_ko'] = _korean_title(marks) or row.get('title_ko', '')
    row['signals_ko'] = list(dict.fromkeys(_signals(marks) + list(row.get('signals_ko', []))))

    tags = ['종전·협상']
    if '이란외무장관중국방문' in marks:
        tags += ['이란·중국','중동외교']
    if '중국계위성영상제공보도' in marks:
        tags += ['이란·중국','미중긴장','미확인보도']
    if '크렘린에너지휴전긍정평가' in marks:
        tags += ['우크라이나·러시아','에너지부분휴전']
    if '크렘린제재해제에너지가격하락발언' in marks:
        tags += ['우크라이나·러시아','대러제재','에너지가격']
    row['forced_tags'] = list(dict.fromkeys(list(row.get('forced_tags', [])) + tags))

    if '크렘린에너지휴전긍정평가' in marks or '크렘린제재해제에너지가격하락발언' in marks:
        score = 94
    elif '이란외무장관중국방문' in marks:
        score = 91
    else:
        score = 86
    if len(marks) >= 2:
        score += 3
    src = ' '.join([row.get('source', ''), row.get('link', ''), row.get('resolved_url', '')]).lower()
    if any(x in src for x in ('reuters', 'tass', 'kremlin.ru', 'fmprc.gov.cn', 'walterbloomberg')):
        score += 3
    age = watch.age_minutes(row, now)
    if age is not None and age <= 30:
        score += 2
    return min(score, 100), sorted(set(tags))

watch.score_item = score_item


def item_id(row):
    marks = _marks(row)
    if not marks:
        return _prev_item_id(row)
    if any(m.startswith('크렘린') for m in marks):
        key = 'kremlin-energy-diplomacy-2026-09-15|' + '|'.join(marks)
    else:
        key = 'iran-china-diplomacy-2026-09-15|' + '|'.join(marks)
    return hashlib.sha256(key.encode()).hexdigest()[:20]

watch.item_id = item_id


def topic_label(row):
    marks = _marks(row)
    if any(m.startswith('크렘린') for m in marks):
        return '우크라이나·러시아 · 에너지 휴전·제재'
    if marks:
        return '이란·중국 · 중동 외교'
    return _prev_topic_label(row)

watch.topic_label = topic_label


def _verdict(items):
    flash = [x for x in items if _marks(x)]
    others = [x for x in items if x not in flash]
    if not flash:
        return _prev_verdict(items)

    marks = {m for x in flash for m in _marks(x)}
    lines = ['<b>투자 판정</b>']
    if '크렘린에너지휴전긍정평가' in marks:
        lines.append('- <b>핵심:</b> 🟢 크렘린이 트럼프의 에너지 표적 휴전 제안을 긍정 평가 — 러시아 측 수용 가능성이 한 단계 올라감')
        lines.append('- <b>확정 수준:</b> 긍정 평가이지 정식 휴전 합의·발효 확정은 아님')
    if '크렘린제재해제에너지가격하락발언' in marks:
        lines.append('- <b>에너지:</b> 🟡 크렘린이 제재 해제와 세계 에너지 가격 하락을 직접 연결 — 향후 제재 협상이 유가·디젤 완화 촉매가 될 수 있음')
    if '이란외무장관중국방문' in marks:
        lines.append('- <b>중동 외교:</b> 🟢 이란 외무장관의 중국 방문·왕이 회담 일정 — 중국 중재채널이 다시 전면에 나오는지 확인')
    if '중국계위성영상제공보도' in marks:
        lines.append('- <b>미확인 리스크:</b> 🟠 중국계 주체의 이란 위성영상 제공 보도는 중국 정부 직접 관여가 확인되지 않았고 중국 외교부가 반박')
    lines.append('- <b>시장:</b> 실제 에너지 휴전·대러 제재 완화·중국 중재 진전이 이어지면 유가·디젤·장기금리 위험프리미엄 완화 방향')
    lines.append('- <b>다음:</b> 크렘린 정식 합의 여부 → 우크라이나 확인 → 공격 중단 이행 → 제재 협상 구체화 → 아라치·왕이 실제 회담 결과')
    block = '\n'.join(lines)
    if others:
        return block + '\n' + _prev_verdict(others)
    return block

guard._verdict = _verdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--finalize', action='store_true')
    ap.add_argument('--telegram-test', action='store_true')
    args = ap.parse_args()
    if args.finalize:
        watch.finalize(); return
    if args.telegram_test:
        base._write_inline_test()
    else:
        watch.run(test=False)
    runner.verify_alert(test_mode=False)


if __name__ == '__main__':
    main()
