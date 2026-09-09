#!/usr/bin/env python3
import argparse
import hashlib
import re
import urllib.parse

import war_peace_reconstruction_watch_bodycolor_strict as prev

watch = prev.watch
runner = prev.runner
base = prev.base

_prev_score = watch.score_item
_prev_build_alert = watch.build_alert
_prev_item_id = watch.item_id
_orig_strict_body_color = prev._strict_body_color

# 직전 두 건을 전용 검색어로 보강한다.
EXTRA_QUERIES = [
    'site:reuters.com Russia Ukraine Kremlin Peskov resume talks trilateral Abu Dhabi when:6h',
    '(Russia OR 러시아) (Ukraine OR 우크라이나) (Kremlin OR 크렘린궁 OR Peskov OR 페스코프) (resume talks OR talks resume OR trilateral talks OR 3자 회담 OR 3자 협상 OR 협상 재개) when:6h',
    '(Iran OR 이란 OR Hormuz OR 호르무즈) (Sirik OR 시리크 OR Qeshm OR Keshm OR 게슘 OR 케슘 OR Minab OR 미나브) (explosion OR explosions OR projectile OR projectiles OR strike OR hit OR 폭발 OR 폭발음 OR 발사체 OR 피격) when:3h',
    '(Sirik OR 시리크 OR Qeshm OR 게슘 OR 케슘) (Fars OR IRNA OR 파르스 OR 이란 국영) (explosion OR projectile OR 폭발음 OR 발사체) when:6h',
]
watch.QUERIES = EXTRA_QUERIES + list(watch.QUERIES)

THEATER_TERMS = (
    'ukraine','ukrainian','russia','russian','putin','zelensky','zelenskiy','kyiv','crimea','donbas',
    '우크라이나','러시아','푸틴','젤렌스키','키이우','크림','돈바스',
    'iran','iranian','tehran','hormuz','irgc','sirik','qeshm','keshm','minab','hormozgan',
    '이란','테헤란','호르무즈','혁명수비대','시리크','게슘','케슘','미나브','호르무즈간',
    'israel','israeli','lebanon','hezbollah','gaza','이스라엘','레바논','헤즈볼라','가자',
    'saudi','saudi arabia','houthi','houthis','yemen','red sea','bab el-mandeb','bab al-mandab',
    '사우디','후티','예멘','홍해','바브엘만데브','바브 알만데브',
)

SPECIFIC_ACTIONS = (
    'ceasefire','truce','peace talks','peace agreement','peace deal','negotiations','talks resume','resume talks',
    'summit','trilateral talks','three-way talks','end the war','ending the war','reconstruction','rebuilding','reconstruction fund','rebuild',
    'airstrike','airstrikes','missile attack','missile strike','missiles launched','drone attack','drone strike','shelling',
    'bombardment','blockade','invasion','military attack','military operation','retaliatory attack','retaliatory strike',
    'fighting intensified','clashes','killed','wounded','displaced','evacuated','explosion','explosions','projectile','projectiles',
    '휴전','정전','종전','평화협상','평화 협상','협상 재개','3자 협상','3자 회담','정상회담','재건','복구',
    '공습','폭격','포격','피격','미사일 공격','미사일 발사','드론 공격','무인기 공격','봉쇄','전면전','교전 격화',
    '보복 공격','보복 공습','사망','부상','피란','폭발','폭발음','발사체',
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
        row.get('article_text',''),
    ]).lower()


def _contains_word(text, word):
    if re.fullmatch(r'[a-z ]+', word):
        return re.search(r'(?<![a-z])' + re.escape(word) + r'(?![a-z])', text) is not None
    return word in text


def _stage_marks(row):
    t = _raw_text(row)
    marks = []

    # 🟢 러·우 3자회담: 단순 '가능성 배제 안 함'과 실제 '재개 기대·준비'를 분리한다.
    rus = any(k in t for k in ('russia','russian','러시아'))
    ukr = any(k in t for k in ('ukraine','ukrainian','우크라이나'))
    kremlin = any(k in t for k in ('kremlin','peskov','크렘린','페스코프'))
    trilateral = any(k in t for k in ('trilateral','three-way','3자 회담','3자회담','3자 협상','3자협상'))
    resume = any(k in t for k in ('resume soon','resume talks','talks resume','restart peace talks','협상 재개','회담 재개','재개될 것','재개 기대'))
    open_to_talks = any(k in t for k in ('willing to resume','open to talks','political will','협상에 열려','정치적 의지'))
    possibility_only = any(k in t for k in ('does not rule out','not rule out','배제하지 않','가능성을 열어'))
    abu_dhabi = any(k in t for k in ('abu dhabi','아부다비','uae','아랍에미리트'))
    september = any(k in t for k in ('september','9월'))

    if rus and ukr and kremlin and (trilateral or resume):
        if resume or open_to_talks:
            marks.append('러우3자회담재개기대')
        elif possibility_only:
            marks.append('러우3자회담가능성')
        if abu_dhabi:
            marks.append('아부다비후보지')
        if september:
            marks.append('9월개최신호')

    # 🔴 이란 남부: 폭발음과 발사체 피격을 단계 분리한다.
    iran_south = any(k in t for k in ('sirik','qeshm','keshm','minab','hormozgan','시리크','게슘','케슘','미나브','호르무즈간'))
    explosions = any(k in t for k in ('explosion','explosions','blast','blasts','폭발','폭발음'))
    projectile = any(k in t for k in ('projectile','projectiles','struck by projectiles','hit by projectiles','발사체','피격','타격'))
    if iran_south and explosions:
        marks.append('이란남부복수폭발')
    if iran_south and projectile:
        marks.append('이란남부발사체피격')
    return sorted(set(marks))


def _stage_signals(row, marks):
    sig = []
    if '러우3자회담재개기대' in marks:
        sig.append('크렘린궁: 미·러·우 3자 종전협상 재개 기대·의지 확인 — 단순 가능성 언급보다 한 단계 상승')
        if '아부다비후보지' in marks:
            sig.append('회담 후보지로 UAE 아부다비가 다시 거론됨')
        if '9월개최신호' in marks:
            sig.append('9월 개최·조기 재개 신호 확인 — 실제 날짜 확정 여부가 다음 촉발 요인')
    elif '러우3자회담가능성' in marks:
        sig.append('크렘린궁: 미·러·우 3자 종전협상 재개 가능성을 열어둠 — 아직 탐색 단계')

    if '이란남부발사체피격' in marks:
        sig.append('이란 남부 시리크·게슘 일대: 단순 폭발음에서 발사체 피격 보도로 단계 상승')
        sig.append('공격 주체·정확한 표적·사상자·시설 피해는 공식 후속 확인 전까지 미확정')
    elif '이란남부복수폭발' in marks:
        sig.append('이란 남부 시리크·게슘·미나브 일대 복수 폭발음 — 원인 미확인 단계, 발사체·공습 확인 여부 추적')
    return sig


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

    score, tags = _prev_score(row, now)
    marks = _stage_marks(row)
    if marks:
        row['stage_marks'] = marks
        sig = _stage_signals(row, marks)
        if sig:
            row['signals_ko'] = list(dict.fromkeys(sig + list(row.get('signals_ko', []))))

        if '러우3자회담재개기대' in marks:
            score += 42
            tags = sorted(set(tags + ['종전·협상','휴전·평화']))
        elif '러우3자회담가능성' in marks:
            score += 22
            tags = sorted(set(tags + ['종전·협상','휴전·평화']))

        if '이란남부발사체피격' in marks:
            score += 45
            tags = sorted(set(tags + ['확전']))
        elif '이란남부복수폭발' in marks:
            score += 28
            tags = sorted(set(tags + ['확전']))
    return score, tags

watch.score_item = score_item


def item_id(row):
    base_id = _prev_item_id(row)
    marks = _stage_marks(row)
    # 동일 사건도 '폭발음→발사체 피격', '가능성→재개 기대'로 단계 상승하면 후속 알림 허용.
    stage = [m for m in marks if m in ('러우3자회담가능성','러우3자회담재개기대','이란남부복수폭발','이란남부발사체피격')]
    if not stage:
        return base_id
    return hashlib.sha256((base_id + '|stage|' + '|'.join(stage)).encode()).hexdigest()[:20]

watch.item_id = item_id


def _enhanced_body_color(row):
    marks = _stage_marks(row)
    headline = ' '.join([row.get('title_original',''), row.get('title_ko',''), row.get('description','')]).lower()

    # 이란 남부 폭발·발사체 피격은 전쟁 현장 위험 신호이므로 빨강.
    if '이란남부발사체피격' in marks or '이란남부복수폭발' in marks:
        return 'red'

    # 3자회담 재개·기대 기사는 과거 공격 이력이 본문에 있어도 현재 핵심 행동이 협상이라면 초록.
    if '러우3자회담재개기대' in marks or '러우3자회담가능성' in marks:
        attack_now = any(k in headline for k in ('missile attack','drone attack','airstrike','공습 재개','미사일 공격','드론 공격','피격','사망','부상'))
        if not attack_now:
            return 'green'

    return _orig_strict_body_color(row)

# 병렬 색상 재적용 단계에서도 이 강화 판정을 사용한다.
prev._strict_body_color = _enhanced_body_color
prev.core._body_color = _enhanced_body_color


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
            c = _enhanced_body_color(row)
        except Exception:
            c = ''
        if c:
            colors.append(c)
    return colors


def _verdict(items):
    colors = _actual_colors(items)
    red = 'red' in colors
    green = 'green' in colors
    all_marks = {m for row in items for m in _stage_marks(row)}

    if red and not green:
        if '이란남부발사체피격' in all_marks:
            core = '이란 남부 폭발음이 발사체 피격 확인 단계로 상승 — 공격 주체·표적·피해 규모 후속 확인 필요'
            nxt = '공격 주체 공식 확인 → 표적 실명 → 사상자·시설 피해 → 후속 보복 여부'
        else:
            core = '신규 변화의 중심은 실제 공격·확전'
            nxt = '추가 공격·보복 → 피해 규모 → 실제 교전 강도 변화'
        return (
            '<b>투자 판정</b>\n'
            f'- <b>핵심:</b> {core}\n'
            '- <b>현재 단계:</b> 군사행동·확전 지속 단계 — 휴전·협상 진전은 이번 변화에서 확인되지 않음\n'
            '- <b>시장:</b> 유가·해운·보험 위험프리미엄 상승 압력 / 위험자산 변동성 확대 가능\n'
            f'- <b>다음:</b> {nxt}'
        )
    if green and not red:
        if '러우3자회담재개기대' in all_marks:
            core = '러·우 3자 종전협상이 단순 가능성 언급에서 재개 기대·준비 단계로 상승'
            stage = '협상 재개 준비 단계 — 실제 회담 날짜·대표단·의제 확정이 다음 확인점'
            nxt = '회담 날짜 확정 → 대표단 발표 → 의제·공동성명 → 실제 휴전 문안'
        else:
            core = '신규 변화의 중심은 휴전·종전·재건 진전'
            stage = '협상·완화 진행 단계 — 공식 합의와 실제 이행 여부를 분리 확인'
            nxt = '공식 합의문 → 실제 이행 → 후속 회담·재건 일정'
        return (
            '<b>투자 판정</b>\n'
            f'- <b>핵심:</b> {core}\n'
            f'- <b>현재 단계:</b> {stage}\n'
            '- <b>시장:</b> 완화 진전 시 유가·전쟁 위험프리미엄 하락 가능\n'
            f'- <b>다음:</b> {nxt}'
        )
    if red and green:
        return (
            '<b>투자 판정</b>\n'
            '- <b>핵심:</b> 공격·확전과 휴전·종전 신호가 동시에 존재\n'
            '- <b>현재 단계:</b> 혼재 단계 — 협상 발언보다 실제 교전 감소·합의 이행이 우선\n'
            '- <b>시장:</b> 완화 기대와 확전 위험이 충돌해 유가·위험자산 변동성 확대 가능\n'
            '- <b>다음:</b> 실제 교전 감소 여부 → 회담 일정 확정 → 위반·보복 여부'
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
