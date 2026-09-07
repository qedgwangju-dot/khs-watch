#!/usr/bin/env python3
import argparse
import hashlib

import war_peace_reconstruction_watch_newideas as prev

watch = prev.watch
runner = prev.runner
base = prev.base

# '평화/휴전'이라는 단어가 없어도 겨울철 긴장 완화·에너지 공격 자제처럼
# 실질적인 단계적 완화 신호를 놓치지 않도록 별도 검색축을 둔다.
WINTER_QUERIES = [
    'site:axios.com (Zelensky OR Zelenskiy OR Ukraine) ("winter de-escalation" OR "de-escalation steps" OR de-escalation OR winter) (Russia OR Moscow OR U.S. OR US) when:6h',
    'site:axios.com Ukraine Russia (energy OR winter) (de-escalation OR restraint OR "reduce strikes" OR "pause strikes" OR "no strikes") when:6h',
    'site:president.gov.ua Zelensky (winter OR energy) (de-escalation OR ceasefire OR restraint OR attacks OR strikes) Russia US when:1d',
    'site:reuters.com Zelenskiy Ukraine Russia (winter OR energy) (de-escalation OR restraint OR "reduce strikes" OR "pause strikes") when:12h',
    'site:apnews.com Zelensky Ukraine Russia (winter OR energy) (de-escalation OR restraint OR "reduce strikes" OR "pause strikes") when:12h',
    '(Zelensky OR Zelenskiy OR 젤렌스키) ("winter de-escalation" OR "de-escalation steps" OR "겨울 긴장 완화" OR "겨울철 긴장 완화" OR "에너지 공격 중단") (Russia OR Ukraine OR 러시아 OR 우크라이나) when:6h',
]
watch.QUERIES = WINTER_QUERIES + list(watch.QUERIES)

_prev_google_news = watch.google_news
_prev_score = watch.score_item
_prev_item_id = watch.item_id
_prev_build_alert = watch.build_alert


def _text(row):
    return ' '.join([
        row.get('title_ko', ''),
        row.get('title_original', ''),
        row.get('description', ''),
        ' '.join(row.get('signals_ko', [])),
    ]).lower()


def _winter_signals(row):
    text = _text(row)
    signals, marks = [], []

    ruua = any(k in text for k in ('russia', 'russian', 'ukraine', '러시아', '우크라이나'))
    winter = any(k in text for k in ('winter', 'cold season', '겨울', '동절기'))
    deesc = any(k in text for k in (
        'de-escalation', 'de escalation', 'deescalation', 'reduce strikes', 'pause strikes',
        'no strikes', 'restraint', 'mutual restraint', 'energy truce', 'energy ceasefire',
        '긴장 완화', '긴장완화', '공격 자제', '공습 자제', '공격 중단', '공습 중단', '상호 자제'
    ))
    energy = any(k in text for k in ('energy infrastructure', 'power grid', 'power plants', 'energy facilities', '에너지 인프라', '전력망', '발전소', '에너지 시설'))
    us = any(k in text for k in ('u.s.', ' us ', 'united states', 'america', 'trump', 'witkoff', 'kushner', '미국', '트럼프', '윗코프', '위트코프', '쿠슈너'))

    if ruua and winter and deesc:
        signals.append('미국이 러시아·우크라이나의 겨울철 긴장 완화 조치를 모색')
        marks.append('겨울긴장완화')
        if us:
            marks.append('미국중재')
    if ruua and energy and deesc:
        signals.append('에너지 인프라 상호 공격 자제·중단이 단계적 완화 카드로 부상')
        marks.append('에너지공격완화')

    # 단계 구분: 탐색 → 제안 → 합의 → 이행 → 위반 시 각각 후속 알림 가능
    if marks and any(k in text for k in ('exploring', 'explore', 'considering', 'consider', 'discussing', 'looking at', '모색', '검토', '논의 중', '논의중')):
        marks.append('탐색')
    if marks and any(k in text for k in ('proposal', 'proposed', 'proposes', 'offer', '제안', '방안 제시')):
        marks.append('제안')
    if marks and any(k in text for k in ('agreed', 'agreement', 'accepts', 'accepted', '합의', '수용')):
        marks.append('합의')
    if marks and any(k in text for k in ('in effect', 'implemented', 'observing', 'halted', 'stopped strikes', '시행', '이행', '공격을 중단', '공습을 중단')):
        marks.append('이행')
    if marks and any(k in text for k in ('violation', 'violated', 'breach', 'resumed strikes', '위반', '공격 재개', '공습 재개')):
        marks.append('위반')

    if ruua and winter and any(k in text for k in ('winter package', 'air defense', 'patriot', 'energy assistance', '겨울 패키지', '방공', '에너지 지원')):
        signals.append('미국의 겨울철 방공·에너지 지원 패키지도 협상 지속성의 핵심 변수')
        marks.append('겨울지원패키지')

    return list(dict.fromkeys(signals)), sorted(set(marks))


def winter_google_news(query):
    rows, err = _prev_google_news(query)
    for row in rows:
        signals, marks = _winter_signals(row)
        if not marks:
            continue
        row['signals_ko'] = list(dict.fromkeys(signals + list(row.get('signals_ko', []))))
        row['winter_marks'] = marks
        row['forced_tags'] = list(dict.fromkeys(list(row.get('forced_tags', [])) + ['종전·협상', '겨울긴장완화']))
        row['deep_signal'] = True
    return rows, err


watch.google_news = winter_google_news


def winter_score_item(x, now):
    score, tags = _prev_score(x, now)
    signals, marks = _winter_signals(x)
    if marks:
        if '겨울긴장완화' in marks:
            score += 45
        elif '에너지공격완화' in marks:
            score += 32
        else:
            score += 15
        src = (x.get('source') or '').lower()
        if any(k in src for k in ('axios', 'reuters', 'associated press', 'ap news', 'president of ukraine')):
            score += 10
        tags = sorted(set(tags + ['종전·협상', '겨울긴장완화']))
        x['winter_marks'] = marks
        if signals:
            x['signals_ko'] = list(dict.fromkeys(signals + list(x.get('signals_ko', []))))
            x['deep_signal'] = True
    return score, tags


watch.score_item = winter_score_item


def winter_item_id(x):
    base_id = _prev_item_id(x)
    _, marks = _winter_signals(x)
    if not marks:
        return base_id
    # 단계가 바뀌면 동일 기사 업데이트라도 다시 알릴 수 있게 한다.
    stage = [m for m in marks if m in ('탐색', '제안', '합의', '이행', '위반')]
    core = [m for m in marks if m in ('겨울긴장완화', '에너지공격완화', '겨울지원패키지')]
    key = base_id + '|winter|' + '|'.join(sorted(core + stage))
    return hashlib.sha256(key.encode('utf-8')).hexdigest()[:20]


watch.item_id = winter_item_id


def _inject_winter(text, items):
    marks = set()
    for x in items:
        _, m = _winter_signals(x)
        marks.update(m)
    if not marks:
        return text

    rows = []
    if '겨울긴장완화' in marks:
        rows.append('- <b>새 조치:</b> 미국, 러·우 겨울철 긴장 완화 방안 모색')
    if '탐색' in marks and not {'합의', '이행'} & marks:
        rows.append('- <b>판정:</b> 현재 탐색·협의 단계 — 합의·휴전 확정 아님')
    elif '합의' in marks:
        rows.append('- <b>판정:</b> 합의 문안·적용 범위·시작 시각 확인 필요')
    if '에너지공격완화' in marks:
        rows.append('- <b>핵심:</b> 에너지 인프라 상호 공격 자제가 실제 포함되는지 확인')
    rows.append('- <b>다음:</b> 러시아 수용 여부 → 적용 기간 → 실제 공격 감소·위반 여부')

    marker = '<b>투자 판정</b>\n'
    pos = text.find(marker)
    if pos != -1:
        insert = pos + len(marker)
        return text[:insert] + '\n'.join(rows[:4]) + '\n' + text[insert:]
    return text.rstrip() + '\n\n<b>겨울 긴장 완화</b>\n' + '\n'.join(rows[:4]) + '\n'


def winter_build_alert(items, markets, now):
    text = _prev_build_alert(items, markets, now)
    return _inject_winter(text, items).strip()[:4000] + '\n'


watch.build_alert = winter_build_alert


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--finalize', action='store_true')
    ap.add_argument('--telegram-test', action='store_true')
    args = ap.parse_args()
    if args.finalize:
        watch.finalize()
        return
    if args.telegram_test:
        base._write_inline_test()
    else:
        watch.run(test=False)
    runner.verify_alert(test_mode=False)


if __name__ == '__main__':
    main()
