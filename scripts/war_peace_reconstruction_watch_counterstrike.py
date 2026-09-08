#!/usr/bin/env python3
import argparse
import hashlib

import war_peace_reconstruction_watch_finalcompact as prev

watch = prev.watch
runner = prev.runner
base = prev.base

COUNTERSTRIKE_QUERIES = [
    'site:reuters.com Saratov drone civilian infrastructure governor Ukraine when:6h',
    'site:tass.com Saratov drone civilian infrastructure governor Ukraine when:6h',
    '(Saratov OR Engels OR 사라토프 OR 엥겔스) (drone OR UAV OR 드론) (civilian infrastructure OR 민간 인프라 OR refinery OR 정유공장 OR airbase OR 공군기지) when:6h',
    '(Roman Busargin OR Роман Бусаргин OR 부사르긴) (drone OR БПЛА OR 드론) (infrastructure OR инфраструктур OR 인프라) when:6h',
]
watch.QUERIES = COUNTERSTRIKE_QUERIES + list(watch.QUERIES)

_prev_google_news = watch.google_news
_prev_score = watch.score_item
_prev_item_id = watch.item_id
_prev_build_alert = watch.build_alert


def _text(row):
    return ' '.join([
        row.get('title_ko', ''), row.get('title_original', ''), row.get('description', ''),
        ' '.join(row.get('signals_ko', [])), ' '.join(row.get('forced_tags', [])),
    ]).lower()


def _counter_signals(row):
    t = _text(row)
    signals, marks = [], []
    saratov = any(k in t for k in ('saratov', 'саратов', '사라토프', 'engels', 'энгельс', '엥겔스'))
    drone = any(k in t for k in ('drone', 'uav', 'бпла', '드론', '무인기'))
    civ = any(k in t for k in ('civilian infrastructure', 'гражданской инфраструкт', '민간 인프라', '민간 기반시설'))
    refinery = any(k in t for k in ('refinery', 'oil refinery', 'нефтеперераб', '정유공장', '정유시설'))
    airbase = any(k in t for k in ('airbase', 'air base', 'airfield', 'аэродром', '공군기지', '비행장'))
    gov = any(k in t for k in ('governor', 'busargin', 'бусаргин', '주지사', '부사르긴'))

    if saratov and drone and civ:
        signals.append('사라토프 지역 드론 공격으로 민간 인프라 피해 — 현지 주지사 발표')
        marks += ['사라토프민간인프라', '확전반대신호']
        if gov:
            marks.append('주지사발표')
    if saratov and drone and refinery:
        signals.append('사라토프 정유시설 피격 여부 확인 필요 — 에너지 공급·유가 파급 가능')
        marks += ['정유시설공격', '에너지시설']
    if saratov and drone and airbase:
        signals.append('엥겔스 공군기지 등 군사시설 피격 여부도 별도 확인 필요')
        marks.append('군사시설가능성')
    return list(dict.fromkeys(signals)), sorted(set(marks))


def counter_google_news(query):
    rows, err = _prev_google_news(query)
    for row in rows:
        signals, marks = _counter_signals(row)
        if marks:
            row['signals_ko'] = list(dict.fromkeys(signals + list(row.get('signals_ko', []))))
            row['counter_marks'] = marks
            row['forced_tags'] = list(dict.fromkeys(list(row.get('forced_tags', [])) + ['확전', '반대신호']))
            row['deep_signal'] = True
    return rows, err

watch.google_news = counter_google_news


def counter_score_item(x, now):
    score, tags = _prev_score(x, now)
    signals, marks = _counter_signals(x)
    if marks:
        score += 42 if '사라토프민간인프라' in marks else 25
        src = (x.get('source') or '').lower()
        if any(k in src for k in ('reuters', 'tass', 'interfax')):
            score += 10
        tags = sorted(set(tags + ['확전', '반대신호']))
        x['counter_marks'] = marks
        if signals:
            x['signals_ko'] = list(dict.fromkeys(signals + list(x.get('signals_ko', []))))
            x['deep_signal'] = True
    return score, tags

watch.score_item = counter_score_item


def counter_item_id(x):
    base_id = _prev_item_id(x)
    _, marks = _counter_signals(x)
    if not marks:
        return base_id
    key = base_id + '|counterstrike|' + '|'.join(marks)
    return hashlib.sha256(key.encode('utf-8')).hexdigest()[:20]

watch.item_id = counter_item_id


def _inject_counter(text, items):
    marks = set()
    for x in items:
        _, m = _counter_signals(x)
        marks.update(m)
    if not marks:
        return text

    # finalcompact가 만든 투자판정 3줄만 교체해 가독성 유지
    marker = '<b>투자 판정</b>\n'
    pos = text.find(marker)
    if pos == -1:
        return text
    head = text[:pos].rstrip()
    rows = [
        '<b>투자 판정</b>',
        '- <b>핵심:</b> 종전 협상 재개와 별개로 장거리 드론 공격은 계속 — 실제 군사 완화는 아직 미확인',
        '- <b>시장:</b> 정유시설 피격 확인 시 유가·에너지 위험프리미엄 재상승 가능',
        '- <b>다음:</b> 피해 대상 실명 → 사상자·가동중단 → 러시아 보복·협상 영향 확인',
    ]
    return head + '\n\n' + '\n'.join(rows)


def counter_build_alert(items, markets, now):
    text = _prev_build_alert(items, markets, now)
    return _inject_counter(text, items).strip()[:4000] + '\n'

watch.build_alert = counter_build_alert


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
