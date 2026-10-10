#!/usr/bin/env python3
import html
import json
import re
from datetime import datetime, timezone, timedelta

import warsh_policy_path_watch_v2 as v2

base = v2.base
SCHEMA_VERSION = 9


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
    prob = (f"현 목표범위 대비 누적 +25bp 경로 {float(p):.1f}%"
            if p is not None else "정확한 목표금리 구간별 확률 판정 유보")
    if p is not None and m.get("hike25_or_more_prob") is not None:
        prob += f" · 누적 +25bp 이상 {float(m['hike25_or_more_prob']):.1f}%"
    ch = float(m.get('change_bp') or 0.0)
    move_label = "확률가중 기대변화" if p is not None else "공식 결제값 기반 기대변화"
    return (
        f"• {base.ko_date(m['date'])} | {prob} | "
        f"{move_label} {ch:+.1f}bp | 회의 후 금리 기대 {float(m['post_rate']):.3f}%"
    )


def message_v3(snap, cls):
    sep = cls.get('sep'); bal = cls.get('balance')
    extra = float(cls.get('extra_bp') or 0.0)
    eq = extra / 25.0
    api_probability = any(m.get('hike25_prob') is not None for m in snap.get('meetings', []))
    if api_probability:
        equivalent_note = (
            f"  ↳ +25bp 인상 {eq:.2f}회 상당의 <b>확률가중 평균</b>이며 실제 인상 횟수 확정값이 아닙니다."
        )
    else:
        equivalent_note = (
            f"  ↳ +25bp 단위로 환산하면 {eq:.2f}회 상당이지만, 이는 <b>공식 선물 결제값에서 계산한 기대금리 차이</b>이며 "
            "실제 인상 횟수나 구간별 확률이 아닙니다."
        )
    lines = [
        '<b>[Warsh 금리경로·대차대조표 종합]</b>',
        '',
        f"• <b>시장자료 기준</b>: {html.escape(str(snap.get('market_data_basis') or snap.get('source_kind') or '연방기금금리 선물 기반 경로'))}",
        f"• <b>확률 원천 상태</b>: {html.escape(str(snap.get('probability_source_status') or ('공식 구간별 확률 사용' if api_probability else '구간별 확률 판정 유보')))}",
        '<b>핵심 판정</b>',
        f"• <b>시장 경로</b>: {html.escape(cls['verdict'])}",
        f"• <b>현재 공식 기준</b>: {cls['baseline_rate']:.3f}% ({html.escape(cls['baseline_kind'])})",
        f"• <b>연말 시장 기대</b>: {cls['yearend_market_rate']:.3f}% · 현재보다 {extra:+.1f}bp",
        equivalent_note,
    ]
    if sep:
        lines += [
            f"• <b>연준 점도표</b>: {cls.get('reference_year', 2026)}년 말 {sep['yearend']:.3f}% · {cls.get('reference_year', 2026)+1}년 말 {sep['nextyear']:.3f}%",
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
        '• CME 공개 결제값은 기대금리 계산에는 사용할 수 있지만 FedWatch 목표금리 구간별 확률 자체는 아닙니다. 인증 API가 없으면 확률을 추정하지 않고 “판정 유보”로 표시합니다.',
        '• 선물 원천의 EFFR가 연준 공식 목표범위를 벗어나거나 미래 회의가 없으면 오래된 값으로 간주해 신규 시장판정을 중지합니다.',
        '• 점도표는 연준 참가자 전망의 중앙값이지 FOMC의 약속이 아닙니다.',
        '',
        '<b>다음 확인</b>',
        '• 향후 두 회의와 연말 정책금리 기대가 함께 올라가는지',
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
    if kind == 'error' and '인증정보 미설정' in str(err or ''):
        return '\n'.join([
            '<b>[Warsh 금리경로 공식 API 연결 필요]</b>',
            'CME FedWatch 확률은 공식 인증 API 구독과 OAuth 권한이 필요합니다.',
            '• 무료 공개 결제파일은 FedWatch 구간별 확률 원천이 아니므로 확률 수치로 승격하지 않습니다.',
            '• <b>시장 확률·기대금리 최신판정은 일시 중지</b>합니다.',
            '• 연준 공식 금리결정·점도표·2년물·대차대조표 감시는 계속됩니다.',
            '• 정식 API 권한이 연결되면 원천 날짜·구간별 확률 합계를 검증한 뒤 자동 재개합니다.',
            '',
            '<b>원천</b>',
            base.link('CME 공식 FedWatch API', 'https://www.cmegroup.com/market-data/market-data-api/fedwatch-api.html'),
        ])
    if kind == 'error' and ('HTTP Error 401' in str(err or '') or 'HTTP Error 403' in str(err or '')):
        return '\n'.join([
            '<b>[Warsh CME FedWatch 계정 권한 점검]</b>',
            '공식 API 인증·계약 권한을 확인하지 못했습니다.',
            '• API ID/암호·상품 이용권한을 CME 계정에서 점검해야 합니다.',
            '• 검증 완료 전에는 시장 인상확률과 연말 선물 경로를 발송하지 않습니다.',
            '<b>원천</b>',
            base.link('CME 공식 FedWatch API 안내',
                      'https://www.cmegroup.com/market-data/market-data-api/fedwatch-api.html'),
        ])
    if kind == 'error':
        return '\n'.join([
            '<b>[Warsh 금리경로 원천 점검]</b>',
            '연방기금금리 선물의 공식 CME 자료를 연속 조회했지만 최신성 검증을 통과하지 못했습니다.',
            '• 직전 수치는 기록용으로만 보존하며, <b>새로운 금리경로·확률 판정은 중지</b>합니다.',
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



def _partial_recovery_message(snap):
    return '\n'.join([
        '<b>[Warsh 시장 기대금리 경로 안전 복구]</b>',
        'CME 공식 공개 결제값과 뉴욕연은 EFFR로 기대금리 경로 감시를 다시 시작합니다.',
        '• <b>구간별 FedWatch 확률은 아직 판정 유보</b>입니다. 인증 API 권한이 연결되기 전에는 확률을 역산하지 않습니다.',
        '• 연말·회의 후 기대금리와 연준 점도표의 차이는 공식 결제값 기반 자체 계산으로만 표시합니다.',
        '• 과거 확률을 현재값으로 재사용하지 않습니다.',
        '',
        '<b>원천</b>',
        base.link('CME 연방기금금리 선물 결제값', snap.get('url') or base.CME_URL),
    ])


def _last_good_snapshot(state):
    """Quarantine the last validated snapshot for audit only.

    On an upstream outage active market fields are cleared. This prevents a
    stale probability/rate path from being accidentally promoted back to
    'current' by another watcher while still retaining the last good sample for
    diagnostics.
    """
    if not isinstance(state, dict):
        return None
    cached = state.get('last_good_snapshot')
    if isinstance(cached, dict) and cached.get('meetings'):
        return cached
    if state.get('source_status') == '시장원천 최신성·연준 공식범위 교차검증 통과' and state.get('meetings'):
        return {
            'effr': state.get('effr'),
            'meetings': state.get('meetings'),
            'classification': state.get('classification'),
            'source': state.get('source'),
            'market_data_basis': state.get('market_data_basis'),
            'official_settlement_date': state.get('official_settlement_date'),
            'forecast_reporting_date': state.get('forecast_reporting_date'),
            'source_api_url': state.get('source_api_url'),
            'probability_source_status': state.get('probability_source_status'),
            'probability_source_error': state.get('probability_source_error'),
            'last_validated_at_utc': state.get('last_validated_at_utc'),
        }
    return None


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
        # 2회 연속 오류 여부만 저장. 장기간 같은 장애로 상태 파일을
        # 매시간 수정/커밋하는 일을 방지한다.
        streak = min(2, int(old.get('source_error_streak') or 0) + 1)
        alerted = bool(old.get('source_health_alerted'))
        now = datetime.now(timezone.utc)
        last_notice = old.get('last_health_alert_at_utc')
        try:
            notice_at = datetime.fromisoformat(str(last_notice).replace('Z', '+00:00'))
            reminder_due = (now - notice_at.astimezone(timezone.utc)) >= timedelta(hours=72)
        except (ValueError, TypeError, AttributeError):
            # Legacy states may remember that an outage alert was already sent
            # without storing its timestamp.  Do not immediately duplicate that
            # alert during schema migration; start the 72-hour clock now.
            reminder_due = not alerted
            if alerted and not last_notice:
                last_notice = now.isoformat()
        permission_pending = '인증정보 미설정' in source_error
        permission_denied = ('HTTP Error 401' in source_error or 'HTTP Error 403' in source_error)
        reason_kind = ('auth_missing' if permission_pending else
                       'auth_rejected' if permission_denied else 'transport')
        # 인증 미설정으로 원인이 달라졌을 때는 단 한 번 안내한다.
        # 구독 미설정은 매시간 네트워크를 재시도할 사안이 아니므로 72시간 재알림을 중단한다.
        newly_classified = (permission_pending or permission_denied) and old.get('source_error_kind') != reason_kind
        health_message_id = None
        if streak >= 2 and not first and (
                not alerted or newly_classified or (reminder_due and not permission_pending)):
            health_message_id = base.send(_source_health_message('error', source_error))
            alerted = True
            last_notice = now.isoformat()
        state = {
            'schema_version': SCHEMA_VERSION,
            'effr': None,
            'meetings': [],
            'classification': {
                'market_source_stale': True,
                'market_source_error': source_error,
            },
            'source': None,
            'market_data_basis': None,
            'official_settlement_date': None,
            'last_validated_at_utc': None,
            'last_good_snapshot': _last_good_snapshot(old),
            'source_status': ('CME FedWatch 공식 API 미연결 — 금리확률판정 보류'
                              if permission_pending else
                              '최신성 검증 실패 — 과거값 격리·신규 판정 중지'),
            'source_error': source_error,
            'source_error_streak': streak,
            'source_error_kind': reason_kind,
            'source_health_alerted': alerted,
            'last_health_alert_at_utc': last_notice,
            'last_health_message_id': health_message_id or old.get('last_health_message_id'),
        }
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

    recovery_message_id = None
    if old.get('source_health_alerted'):
        if '판정 유보' in str(snap.get('probability_source_status') or ''):
            recovery_message_id = base.send(_partial_recovery_message(snap))
        else:
            recovery_message_id = base.send(_source_health_message('recovery'))

    if base.FORCE or (not first and changed):
        base.send(message_v3(snap, cls))

    validated_at = datetime.now(timezone.utc).isoformat()
    good = {
        'effr': snap['effr'],
        'meetings': snap['meetings'],
        'classification': cls,
        'source': snap['url'],
        'market_data_basis': snap.get('market_data_basis') or snap.get('source_kind'),
        'official_settlement_date': snap.get('official_settlement_date'),
        'forecast_reporting_date': snap.get('forecast_reporting_date'),
        'source_api_url': snap.get('source_api_url'),
        'probability_source_status': snap.get('probability_source_status'),
        'probability_source_error': snap.get('probability_source_error'),
        'last_validated_at_utc': validated_at,
    }
    base.save_state({
        'schema_version': SCHEMA_VERSION,
        **good,
        'last_good_snapshot': good,
        'source_status': '시장원천 최신성·연준 공식범위 교차검증 통과',
        'source_error': None,
        'source_error_streak': 0,
        'source_error_kind': None,
        'source_health_alerted': False,
        'last_health_alert_at_utc': None,
        'last_health_message_id': recovery_message_id or old.get('last_health_message_id'),
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
