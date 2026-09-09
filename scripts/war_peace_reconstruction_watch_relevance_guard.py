#!/usr/bin/env python3
import argparse

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

WAR_PEACE_ACTIONS = (
    'ceasefire','truce','peace talks','peace agreement','peace deal','negotiations','talks resume','summit','trilateral',
    'end the war','ending the war','reconstruction','rebuilding','reconstruction fund','rebuild',
    'attack','attacks','strike','strikes','airstrike','airstrikes','missile','missiles','drone','drones','shelling',
    'bombardment','blockade','invasion','war','fighting','clashes','killed','wounded','displaced','evacuated',
    '휴전','정전','종전','평화협상','평화 협상','협상 재개','3자 협상','3자 회담','정상회담','재건','복구',
    '공격','공습','폭격','포격','피격','미사일','드론','무인기','봉쇄','전면전','교전','충돌','사망','부상','피란',
)

MARKET_LINK_ACTIONS = (
    'oil prices','crude prices','brent','wti','tanker','shipping','insurance','energy infrastructure','energy facilities',
    '유가','원유','브렌트','탱커','유조선','해운','보험','에너지 인프라','에너지 시설',
)

IRRELEVANT_TECH = (
    'openai','artificial intelligence','artificial general intelligence','agi','chatgpt','anthropic','deepmind',
    'ai race','ai safety','ai model','인공지능','오픈ai','챗gpt','ai 경쟁','ai 안전',
)


def _raw_text(row):
    return ' '.join([
        row.get('title_original',''), row.get('title_ko',''), row.get('description',''),
    ]).lower()


def is_relevant(row):
    t = _raw_text(row)
    has_theater = any(k in t for k in THEATER_TERMS)
    if not has_theater:
        return False

    has_action = any(k in t for k in WAR_PEACE_ACTIONS)
    has_market_link = any(k in t for k in MARKET_LINK_ACTIONS)

    # 기술·AI 기사는 지정학 단어가 설명에 우연히 섞여도, 실제 전쟁/휴전/재건 행동이 없으면 제외한다.
    if any(k in t for k in IRRELEVANT_TECH) and not has_action and not has_market_link:
        return False

    return has_action or has_market_link


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
