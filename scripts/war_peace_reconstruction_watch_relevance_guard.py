#!/usr/bin/env python3
import argparse
import re
import urllib.parse

import war_peace_reconstruction_watch_bodycolor_strict as prev

watch = prev.watch
runner = prev.runner
base = prev.base

_prev_score = watch.score_item
_prev_build_alert = watch.build_alert

THEATER_TERMS = (
    'ukraine','ukrainian','russia','russian','putin','zelensky','zelenskiy','kyiv','crimea','donbas',
    '우크라이나','러시아','푸틴','젤렌스키','키이우','크림','돈바스',
    'iran','iranian','tehran','hormuz','irgc','이란','테헤란','호르무즈','혁명수비대',
    'israel','israeli','lebanon','hezbollah','gaza','이스라엘','레바논','헤즈볼라','가자',
    'saudi','saudi arabia','houthi','houthis','yemen','red sea','bab el-mandeb','bab al-mandab',
    '사우디','후티','예멘','홍해','바브엘만데브','바브 알만데브',
)

SPECIFIC_ACTIONS = (
    'ceasefire','truce','peace talks','peace agreement','peace deal','negotiations','talks resume','summit','trilateral talks',
    'end the war','ending the war','reconstruction','rebuilding','reconstruction fund','rebuild',
    'airstrike','airstrikes','missile attack','missile strike','missiles launched','drone attack','drone strike','shelling',
    'bombardment','blockade','invasion','military attack','military operation','retaliatory attack','retaliatory strike',
    'fighting intensified','clashes','killed','wounded','displaced','evacuated',
    '휴전','정전','종전','평화협상','평화 협상','협상 재개','3자 협상','3자 회담','정상회담','재건','복구',
    '공습','폭격','포격','피격','미사일 공격','미사일 발사','드론 공격','무인기 공격','봉쇄','전면전','교전 격화',
    '보복 공격','보복 공습','사망','부상','피란',
)

GENERIC_CONFLICT_WORDS = ('war','attack','attacks','strike','strikes','fighting','conflict','공격','전쟁','충돌','교전')

MARKET_LINK_ACTIONS = (
    'oil prices','crude prices','brent','wti','tanker','shipping','insurance','energy infrastructure','energy facilities',
    '유가','원유','브렌트','탱커','유조선','해운','보험','에너지 인프라','에너지 시설',
)

IRRELEVANT_TECH = (
    'openai','artificial intelligence','artificial general intelligence','agi','chatgpt','anthropic','deepmind',
    'ai race','ai safety','ai model','cyberattack','cyber attack','cybersecurity',
    '인공지능','오픈ai','챗gpt','ai 경쟁','ai 안전','사이버공격','사이버 공격','사이버보안',
)

ROUNDUP_TERMS = (
    'morning bid','daily briefing','what you need to know','news roundup','podcast','팟캐스트','뉴스 브리핑','오늘의 주요 뉴스',
)


def _raw_text(row):
    return ' '.join([
        row.get('title_original',''), row.get('title_ko',''), row.get('description',''),
    ]).lower()


def _contains_word(text, word):
    if re.fullmatch(r'[a-z ]+', word):
        return re.search(r'(?<![a-z])' + re.escape(word) + r'(?![a-z])', text) is not None
    return word in text


def is_relevant(row):
    t = _raw_text(row)
    has_theater = any(_contains_word(t, k) for k in THEATER_TERMS)
    if not has_theater:
        return False

    has_specific_action = any(_contains_word(t, k) for k in SPECIFIC_ACTIONS)
    has_market_link = any(_contains_word(t, k) for k in MARKET_LINK_ACTIONS)
    tech_context = any(_contains_word(t, k) for k in IRRELEVANT_TECH)

    if tech_context and not has_specific_action and not has_market_link:
        return False
    if has_specific_action or has_market_link:
        return True
    if not tech_context and any(_contains_word(t, k) for k in GENERIC_CONFLICT_WORDS):
        return True
    return False


def score_item(row, now):
    if not is_relevant(row):
        row['relevance_rejected'] = True
        return -1000, []
    return _prev_score(row, now)

watch.score_item = score_item


def _norm_url(row):
    url = (row.get('resolved_url') or row.get('link') or '').strip()
    if not url:
        return ''
    try:
        p = urllib.parse.urlparse(url)
        host = p.netloc.lower().replace('www.', '')
        path = re.sub(r'/+$', '', p.path or '/')
        return f'{host}{path}'.lower()
    except Exception:
        return url.lower()


def _is_roundup(row):
    url = (row.get('resolved_url') or row.get('link') or '').lower()
    t = _raw_text(row)
    if '/podcasts/' in url:
        return True
    return any(k in t for k in ROUNDUP_TERMS)


def _dedupe_and_filter(items):
    out = []
    seen_urls = set()
    seen_titles = set()
    for row in items:
        if row.get('relevance_rejected'):
            continue
        if _is_roundup(row):
            row['final_rejected_reason'] = '혼합형 팟캐스트·뉴스요약'
            continue
        key_url = _norm_url(row)
        key_title = re.sub(r'\W+', ' ', (row.get('title_original') or row.get('title_ko') or '').lower()).strip()[:220]
        if key_url and key_url in seen_urls:
            continue
        if key_title and key_title in seen_titles:
            continue
        if key_url:
            seen_urls.add(key_url)
        if key_title:
            seen_titles.add(key_title)
        out.append(row)
    return out


def _strip_old_verdict(text):
    marker = '<b>투자 판정</b>'
    pos = text.find(marker)
    if pos != -1:
        return text[:pos].rstrip()
    return text.rstrip()


def _actual_colors(items):
    colors = []
    for row in items:
        try:
            c = prev._strict_body_color(row)
        except Exception:
            c = ''
        if c:
            colors.append(c)
    return colors


def _verdict(items):
    colors = _actual_colors(items)
    red = 'red' in colors
    green = 'green' in colors

    if red and not green:
        return (
            '<b>투자 판정</b>\n'
            '- <b>핵심:</b> 신규 변화의 중심은 실제 공격·확전\n'
            '- <b>현재 단계:</b> 군사행동·확전 지속 단계 — 휴전·협상 진전은 이번 변화에서 확인되지 않음\n'
            '- <b>시장:</b> 유가·해운·보험 위험프리미엄 상승 압력 / 위험자산 변동성 확대 가능\n'
            '- <b>다음:</b> 추가 공격·보복 → 피해 규모 → 실제 교전 강도 변화'
        )
    if green and not red:
        return (
            '<b>투자 판정</b>\n'
            '- <b>핵심:</b> 신규 변화의 중심은 휴전·종전·재건 진전\n'
            '- <b>현재 단계:</b> 협상·완화 진행 단계 — 공식 합의와 실제 이행 여부를 분리 확인\n'
            '- <b>시장:</b> 완화 진전 시 유가·전쟁 위험프리미엄 하락 가능\n'
            '- <b>다음:</b> 공식 합의문 → 실제 이행 → 후속 회담·재건 일정'
        )
    if red and green:
        return (
            '<b>투자 판정</b>\n'
            '- <b>핵심:</b> 공격·확전과 휴전·재건 신호가 동시에 존재\n'
            '- <b>현재 단계:</b> 혼재 단계 — 협상 발언보다 실제 교전 감소·합의 이행이 우선\n'
            '- <b>시장:</b> 완화 기대와 확전 위험이 충돌해 유가·위험자산 변동성 확대 가능\n'
            '- <b>다음:</b> 실제 교전 감소 여부 → 공식 합의 → 위반·보복 여부'
        )
    return (
        '<b>투자 판정</b>\n'
        '- <b>핵심:</b> 전쟁·휴전 방향을 확정할 실제 행동 변화는 확인되지 않음\n'
        '- <b>현재 단계:</b> 방향성 미확인 — 정책·해설·시장기사와 실제 사건을 분리\n'
        '- <b>시장:</b> 별도 군사·휴전 행동 확인 전 방향성 판정 보류\n'
        '- <b>다음:</b> 공식 행동·합의·공격 발생 여부 재확인'
    )


def build_alert(items, markets, now):
    filtered = _dedupe_and_filter(items)
    if not filtered:
        return ''
    text = _prev_build_alert(filtered, markets, now)
    text = _strip_old_verdict(text)
    text = text.rstrip() + '\n\n' + _verdict(filtered)
    return text.strip()[:4000] + '\n'

watch.build_alert = build_alert


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
