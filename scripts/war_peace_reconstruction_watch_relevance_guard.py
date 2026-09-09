#!/usr/bin/env python3
import argparse
import re

import war_peace_reconstruction_watch_bodycolor_strict as prev

watch = prev.watch
runner = prev.runner
base = prev.base

_prev_score = watch.score_item

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

    # AI·기술 기사에서는 Russia/Ukraine 같은 단어가 설명에 우연히 있어도,
    # 실제 군사/휴전/재건 행동이나 중동 공급망 시장연결이 없으면 무조건 제외한다.
    if tech_context and not has_specific_action and not has_market_link:
        return False

    if has_specific_action or has_market_link:
        return True

    # 일반 war/attack 같은 단어는 단어 경계로만 보되, 기술 문맥에서는 절대 통과시키지 않는다.
    if not tech_context and any(_contains_word(t, k) for k in GENERIC_CONFLICT_WORDS):
        return True

    return False


def score_item(row, now):
    if not is_relevant(row):
        row['relevance_rejected'] = True
        return -1000, []
    return _prev_score(row, now)

watch.score_item = score_item


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
