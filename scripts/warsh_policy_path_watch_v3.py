#!/usr/bin/env python3
import html
import json
import re
from datetime import datetime, timezone

import warsh_policy_path_watch_v2 as v2

base = v2.base
SCHEMA_VERSION = 7


def _validated_probability(prob_cell, change_bp):
    nums = [float(x) for x in re.findall(r'(\d+(?:\.\d+)?)\s*%', prob_cell or '')]
    ch = float(change_bp or 0.0)
    # The public mirror omits zero-probability labels. With exactly two non-zero
    # buckets and a 0~25bp expected hike, the right-hand bucket is the +25bp hike.
    # Anything more complex is intentionally left unclassified rather than guessed.
    if len(nums) == 2 and 0.0 <= ch <= 25.0:
        return max(0.0, min(100.0, nums[-1]))
    if len(nums) == 1 and 0.0 <= ch <= 25.0:
        return max(0.0, min(100.0, ch / 25.0 * 100.0))
    return None


def validated_snapshot():
    snap = base.parse_snapshot()
    today = datetime.now(timezone.utc).date().isoformat()
    future = []
    for m in snap.get('meetings') or []:
        if str(m.get('date') or '') < today:
            continue
        mm = dict(m)
        mm['hike25_prob'] = _validated_probability(mm.get('prob_cell'), mm.get('change_bp'))
        future.append(mm)
    if not future:
        raise RuntimeError('선물시장 원천에 미래 FOMC 회의가 없음 — 오래된 화면 가능성')

    official = base.official_policy_baseline()
    if official and official.get('low') is not None and official.get('high') is not None:
        effr = float(snap['effr'])
        low = float(official['low']); high = float(official['high'])
        if not (low - 0.03 <= effr <= high + 0.03):
            raise RuntimeError(
                f"선물 원천 EFFR {effr:.3f}%가 연준 공식 목표범위 {low:.2f}~{high:.2f}%와 불일치"
            )
    snap['meetings'] = future[:6]
    return snap


def _meeting_line(m):
    p = m.get('hike25_prob')
    prob = f"+0.25%p 인상 확률 {float(p):.0f}%" if p is not None else '세부 +0.25%p 확률은 원천 구조상 판정 유보'
    ch = float(m.get('change_bp') or 0.0)
    return (
        f"• {base.ko_date(m['date'])} | {prob} | "
        f"확률가중 기대변화 {ch:+.1f}bp | 회의 후 금리 기대 {float(m['post_rate']):.3f}%"
    )


def message_v3(snap, cls):
    sep = cls.get('sep'); bal = cls.get('balance')
    extra = float(cls.get('extra_bp') or 0.0)
    eq = extra / 25.0
    lines = [
        '<b>[Warsh 금리경로·대차대조표 종합]</b>',
        '',
        f"• <b>시장자료 기준</b>: {html.escape(str(snap.get('market_data_basis') or snap.get('source_kind') or '연방기금금리 선물 기반 경로'))}",
        '<b>핵심 판정</b>',
        f"• <b>시장 경로</b>: {html.escape(cls['verdict'])}",
        f"• <b>현재 공식 기준</b>: {cls['baseline_rate']:.3f}% ({html.escape(cls['baseline_kind'])})",
        f"• <b>연말 시장 기대</b>: {cls['yearend_market_rate']:.3f}% · 현재보다 {extra:+.1f}bp",
        f"  ↳ +25bp 인상 {eq:.2f}회 상당의 <b>확률가중 평균</b>이며 실제 인상 횟수 확정값이 아닙니다.",
    ]
    if sep:
        lines += [
            f"• <b>연준 점도표</b>: 2026년 말 {sep['yearend']:.3f}% · 2027년 말 {sep['nextyear']:.3f}%",
            f"• <b>시장-점도표 차이</b>: {cls['market_sep_gap_bp']:+.1f}bp → {html.escape(cls['sep_read'])}",
        ]
    if bal:
        lines += [f"• <b>대차대조표</b>: {html.escape(cls['tightening_mix'])}"]

    lines += ['', '<b>회의별 시장 경로</b>']
    lines += [_meeting_line(m) for m in snap.get('meetings', [])[:4]]
    lines += [
        '',
        '<b>정확도 가드</b>',
        '• 확률 %와 금리변화 bp는 완전히 다른 숫자입니다.',
        '• 원천이 여러 금리결과를 동시에 제시해 +25bp 확률을 정확히 식별할 수 없으면 확률을 추정하지 않고 “판정 유보”로 표시합니다.',
        '• 선물 원천의 EFFR가 연준 공식 목표범위를 벗어나거나 미래 회의가 없으면 오래된 값으로 간주해 신규 시장판정을 중지합니다.',
        '• 점도표는 연준 참가자 전망의 중앙값이지 FOMC의 약속이 아닙니다.',
        '',
        '<b>다음 확인</b>',
        '• 10월·12월 경로가 같이 더 올라가는지',
        '• 2년물이 추가긴축 기대를 유지하는지',
        '• 연준 점도표와 시장의 괴리가 확대되는지',
        '• 충분한 준비금 유지가 실제 총량축소형 QT로 바뀌는지',
        '',
        '<b>원천</b>',
    ]
    src = [
        base.link('연방기금금리 선물 결제값·경로', snap['url']),
        base.link('CME FedWatch 방법론', base.CME_URL),
        base.link('연준 FOMC 일정', base.FED_CALENDAR),
    ]
    if sep and sep.get('url'):
        src.append(base.link('연준 경제전망·점도표', sep['url']))
    if bal and bal.get('url'):
        src.append(base.link('연준 FOMC 시행지침', bal['url']))
    lines.append(' · '.join(src))
    return '\n'.join(lines)


def _source_health_message(kind, err=None):
    if kind == 'error':
        return '\n'.join([
            '<b>[Warsh 금리경로 원천 점검]</b>',
            '연방기금금리 선물 원천이 연속 조회에서 최신성 검증을 통과하지 못했습니다.',
            '• 직전 정상값은 보존하지만 <b>새로운 금리경로 판정은 중지</b>합니다.',
            '• 연준 공식 FOMC·점도표·2년물·대차대조표 감시는 계속 작동합니다.',
            f"• 원인: {html.escape(str(err or '확인 필요'))}",
            '',
            '<b>원천</b>',
            base.link('CME FedWatch 방법론', base.CME_URL),
        ])
    return '\n'.join([
        '<b>[Warsh 금리경로 원천 복구]</b>',
        '연방기금금리 선물 원천이 최신성 검증을 다시 통과했습니다.',
        '• 연준 공식 목표범위와 EFFR가 일치하고 미래 FOMC 회의도 정상 인식했습니다.',
        '• 이후부터 시장경로 변화 알림을 다시 정상 판정합니다.',
    ])


def main():
    old = base.load_state()
    first = not bool(old)
    source_error = None
    try:
        snap = validated_snapshot()
    except Exception as exc:
        source_error = str(exc)
        # 최초 수집이 실패해도 다른 감시를 멈추거나 과거 확률을 만들지 않는다.
        # 자료가 복구되기 전에는 금리경로 수치 자체를 새로 판정하지 않는다.
        streak = int(old.get('source_error_streak') or 0) + 1
        alerted = bool(old.get('source_health_alerted'))
        if streak >= 2 and not alerted and not first:
            base.send(_source_health_message('error', source_error))
            alerted = True
        state = dict(old)
        state.update({
            'schema_version': SCHEMA_VERSION,
            'source_status': '최신성 검증 실패 — 직전 정상값 보존',
            'source_error': source_error,
            'source_error_streak': streak,
            'source_health_alerted': alerted,
        })
        base.save_state(state)
        print(json.dumps({
            'schema_version': SCHEMA_VERSION,
            'fresh': False,
            'source_error': source_error,
            'source_error_streak': streak,
            'new_market_verdict_sent': False,
        }, ensure_ascii=False))
        return

    cls = base.classify(snap)
    cls['market_source_stale'] = False
    cls['market_source_error'] = None

    old_cls = old.get('classification', {})
    changed = old_cls.get('verdict') not in (None, cls['verdict'])
    if not changed and old_cls.get('extra_bp') is not None:
        changed = abs(float(cls['extra_bp']) - float(old_cls['extra_bp'])) >= base.EXTRA_ALERT_BP

    old_ms = {m['date']: m for m in old.get('meetings', [])}
    if not changed and snap.get('meetings'):
        m = snap['meetings'][0]
        om = old_ms.get(m['date'])
        if om and m.get('hike25_prob') is not None and om.get('hike25_prob') is not None:
            changed = abs(float(m['hike25_prob']) - float(om['hike25_prob'])) >= base.PROB_ALERT_PP

    if not changed and cls.get('market_sep_gap_bp') is not None and old_cls.get('market_sep_gap_bp') is not None:
        changed = abs(float(cls['market_sep_gap_bp']) - float(old_cls['market_sep_gap_bp'])) >= base.MARKET_SEP_GAP_ALERT_BP
    if not changed and old_cls.get('tightening_mix') not in (None, cls.get('tightening_mix')):
        changed = True

    if old.get('source_health_alerted'):
        base.send(_source_health_message('recovery'))

    if base.FORCE or (not first and changed):
        base.send(message_v3(snap, cls))

    base.save_state({
        'schema_version': SCHEMA_VERSION,
        'effr': snap['effr'],
        'meetings': snap['meetings'],
        'classification': cls,
        'source': snap['url'],
        'source_status': '시장원천 최신성·연준 공식범위 교차검증 통과',
        'official_settlement_date': snap.get('official_settlement_date'),
        'last_validated_at_utc': datetime.now(timezone.utc).isoformat(),
        'source_error': None,
        'source_error_streak': 0,
        'source_health_alerted': False,
    })
    print(json.dumps({
        'schema_version': SCHEMA_VERSION,
        'fresh': True,
        'changed': changed,
        'effr': snap['effr'],
        'first_meeting': snap['meetings'][0]['date'] if snap.get('meetings') else None,
        'classification': cls,
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
