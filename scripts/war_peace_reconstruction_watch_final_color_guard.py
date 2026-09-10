#!/usr/bin/env python3
import argparse

import war_peace_reconstruction_watch_relevance_guard as guard

watch = guard.watch
runner = guard.runner
base = guard.base
_prev_color = guard._enhanced_body_color


def _headline_text(row):
    return ' '.join([
        row.get('title_original', ''),
        row.get('title_ko', ''),
        row.get('description', ''),
    ]).lower()


def _final_color(row):
    """최종 송출 직전 색상 안전장치.

    기사 제목·요약 자체에 현재의 공격·확전 행동이 명확하면, 본문 안에
    협상·종전 전망 발언이 함께 있어도 빨강을 우선한다.
    """
    h = _headline_text(row)

    iran_hormuz = any(k in h for k in (
        'iran', 'iranian', 'hormuz', 'sirik', 'qeshm', 'keshm', 'minab', 'hormozgan',
        '이란', '호르무즈', '시리크', '게슘', '케슘', '미나브', '호르무즈간',
    ))
    explosion_now = any(k in h for k in (
        'explosion', 'explosions', 'blast', 'blasts', '폭발', '폭발음',
    ))
    escalation_now = any(k in h for k in (
        'escalation', 'escalate', 'retaliation', 'retaliatory', 'enemy attack', 'under attack',
        '확전', '확전 불사', '보복', '재보복', '적의 공격', '적군', '피격', '공격을 받',
    ))

    # 이란·호르무즈에서 새 폭발이 보도되면 원인 미확정이어도 전쟁현장 위험 신호로 빨강.
    if iran_hormuz and explosion_now:
        return 'red'

    # 제목에서 현재 확전·보복·피격이 명시되면 과거/전망성 평화 문구보다 빨강 우선.
    if iran_hormuz and escalation_now:
        return 'red'

    # 일반 전선에서도 제목에 실제 공격 재개·피격·사상자가 명시되면 빨강 우선.
    hard_red = any(k in h for k in (
        'attack resumed', 'attacks resumed', 'airstrikes resumed', 'missile attack', 'drone attack',
        'retaliatory strike', 'retaliatory attack', 'was struck', 'were struck',
        '공격 재개', '공습 재개', '미사일 공격', '드론 공격', '보복 공격', '보복 공습',
        '피격', '전면전', '사망', '부상', '피란',
    ))
    if hard_red:
        return 'red'

    return _prev_color(row)


# relevance_guard의 최종 투자판정과 bodycolor의 개별 기사 색상 모두 동일 함수 사용.
guard._enhanced_body_color = _final_color
guard.prev._strict_body_color = _final_color
guard.prev.core._body_color = _final_color


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
