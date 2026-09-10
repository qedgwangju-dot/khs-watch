#!/usr/bin/env python3
import argparse
import hashlib
import re

import war_peace_reconstruction_watch_final_color_guard as prev

watch = prev.watch
runner = prev.runner
base = prev.base
guard = prev.guard

_prev_score = watch.score_item
_prev_item_id = watch.item_id
_prev_topic_label = watch.topic_label
_prev_final_color = prev._final_color
_prev_verdict = guard._verdict

# 자연재난 전체를 넓게 긁지 않고, 한국 KDRT·정부/공식 재건 실행 신호와
# 네팔의 재건·복구 단계 상승만 좁게 추적한다.
DISASTER_QUERIES = [
    'site:ytn.co.kr (KDRT OR 해외긴급구호대) (네팔 OR Nepal) (재건 OR 복구 OR 재건복구 OR 복구팀 OR 2진) when:1d',
    'site:mofa.go.kr (KDRT OR 해외긴급구호대) (재건 OR 복구 OR 피해복구 OR 일상 회복 OR 2진) when:2d',
    'site:yna.co.kr (KDRT OR 해외긴급구호대) (네팔 OR Nepal) (재건 OR 복구 OR 피해복구 OR 2진) when:1d',
    '(KDRT OR 대한민국 해외긴급구호대) (재건 OR 복구 OR reconstruction OR recovery) (파견 OR 도착 OR 출국 OR 투입 OR 착수) when:1d',
    '(네팔 OR Nepal) (홍수 OR flood) (재건 OR 복구 OR reconstruction OR recovery) (예산 OR 기금 OR funding OR tender OR 입찰 OR 착공) when:2d',
]
watch.QUERIES = DISASTER_QUERIES + list(watch.QUERIES)

DISASTER_ACTORS = (
    'kdrt', '대한민국 해외긴급구호대', '해외긴급구호대', 'korea disaster relief team',
)
NEPAL_TERMS = ('nepal', '네팔', 'rasuwa', '라수와', 'kathmandu', '카트만두')
DISASTER_TERMS = ('flood', '홍수', '대홍수', 'disaster', '재난', '산사태', 'landslide')
RECOVERY_TERMS = (
    'reconstruction', 'rebuild', 'rebuilding', 'recovery team', 'recovery mission', 'restoration',
    '재건', '복구', '재건·복구', '재건 복구', '복구팀', '재건팀', '피해복구', '일상 회복',
)
PLAN_TERMS = ('준비 중', '준비중', '추진', '검토', '계획', 'preparing', 'plans to', 'considering')
MISSION_CONFIRMED_TERMS = (
    '재건 복구팀', '재건·복구팀', '재건 복구 임무', '재건·복구 임무', '복구팀으로',
    'reconstruction team', 'recovery team', 'reconstruction mission', 'recovery mission',
)
DEPLOY_TERMS = (
    '출국', '파견', '현지 투입', '투입 예정', '도착 예정', '내일 도착', '오늘 도착', '출발',
    'depart', 'departing', 'deploy', 'deployed', 'deployment', 'arrive', 'arriving', 'arrival',
)
ARRIVED_TERMS = ('도착했다', '도착해', '현지 도착', '활동 시작', '복구 착수', '작업 착수', 'arrived', 'began work', 'started work')
FUNDING_TERMS = ('예산', '기금', '지원금', 'funding', 'fund', '재건비', 'reconstruction cost')
EXECUTION_TERMS = ('입찰', '조달', '계약', '수주', '착공', 'tender', 'procurement', 'contract', 'construction start')


def _text(row):
    return ' '.join([
        row.get('title_original',''), row.get('title_ko',''), row.get('description',''),
        row.get('article_text',''), ' '.join(row.get('signals_ko',[])),
    ]).lower()


def _has_any(t, terms):
    return any(k in t for k in terms)


def _disaster_marks(row):
    t = _text(row)
    marks = []
    actor = _has_any(t, DISASTER_ACTORS)
    nepal = _has_any(t, NEPAL_TERMS)
    disaster = _has_any(t, DISASTER_TERMS)
    recovery = _has_any(t, RECOVERY_TERMS)

    # KDRT 재건·복구 전환은 일반 수색 2진 기사와 분리한다.
    if actor and nepal and recovery:
        if _has_any(t, MISSION_CONFIRMED_TERMS):
            marks.append('KDRT재건복구임무확정')
        elif _has_any(t, PLAN_TERMS):
            marks.append('KDRT재건복구검토')
        if _has_any(t, DEPLOY_TERMS):
            marks.append('KDRT재건복구파견')
        if _has_any(t, ARRIVED_TERMS):
            marks.append('KDRT재건복구현장투입')

    # 네팔 재건이 실제 돈·입찰·착공으로 이동할 때만 별도 고신호로 취급한다.
    if nepal and disaster and recovery and _has_any(t, FUNDING_TERMS):
        marks.append('네팔재건재원구체화')
    if nepal and disaster and recovery and _has_any(t, EXECUTION_TERMS):
        marks.append('네팔재건사업집행')
    return sorted(set(marks))


def _is_disaster_recovery(row):
    return bool(_disaster_marks(row))


def _signals(marks):
    out = []
    if 'KDRT재건복구현장투입' in marks:
        out.append('KDRT 2진 재건·복구팀이 현장 도착·활동 시작 단계로 상승')
    elif 'KDRT재건복구파견' in marks:
        out.append('KDRT 2진 재건·복구 임무가 파견·도착 예정 단계로 구체화')
    elif 'KDRT재건복구임무확정' in marks:
        out.append('KDRT 2진 임무가 수색 중심에서 재건·복구 중심으로 전환 확인')
    elif 'KDRT재건복구검토' in marks:
        out.append('KDRT 2진의 재건·복구 전환 검토 단계 — 임무 확정 전')
    if '네팔재건재원구체화' in marks:
        out.append('네팔 재난 재건 재원·지원 규모가 구체화 — 실제 사업목록·집행 여부 추적')
    if '네팔재건사업집행' in marks:
        out.append('네팔 재건이 입찰·조달·계약·착공 단계로 이동 — 실제 매출 연결 구간')
    return out


def score_item(row, now):
    marks = _disaster_marks(row)
    if not marks:
        return _prev_score(row, now)

    row['disaster_recovery_marks'] = marks
    sig = _signals(marks)
    if sig:
        row['signals_ko'] = list(dict.fromkeys(sig + list(row.get('signals_ko', []))))

    # 재건·복구 임무가 명확하지 않은 단순 KDRT 2진 준비/수색 기사는 강제 승격하지 않는다.
    strong = any(m in marks for m in (
        'KDRT재건복구임무확정','KDRT재건복구파견','KDRT재건복구현장투입',
        '네팔재건재원구체화','네팔재건사업집행',
    ))
    if not strong:
        return _prev_score(row, now)

    score = 36
    age = watch.age_minutes(row, now)
    if age is not None:
        if age <= 30: score += 8
        elif age <= 180: score += 5
        elif age <= 720: score += 2
    row['forced_tags'] = list(dict.fromkeys(list(row.get('forced_tags', [])) + ['재건','재난복구']))
    return score, ['재건','재난복구']

watch.score_item = score_item


def item_id(row):
    base_id = _prev_item_id(row)
    marks = _disaster_marks(row)
    stage = [m for m in marks if m in (
        'KDRT재건복구검토','KDRT재건복구임무확정','KDRT재건복구파견','KDRT재건복구현장투입',
        '네팔재건재원구체화','네팔재건사업집행',
    )]
    if not stage:
        return base_id
    return hashlib.sha256((base_id + '|disaster-recovery|' + '|'.join(stage)).encode()).hexdigest()[:20]

watch.item_id = item_id


def topic_label(row):
    if _is_disaster_recovery(row):
        return '네팔·재난재건'
    return _prev_topic_label(row)

watch.topic_label = topic_label


def _color(row):
    marks = _disaster_marks(row)
    if marks:
        # 재난 복구·재건은 사용자의 기존 규칙상 초록 계열.
        return 'green'
    return _prev_final_color(row)

# 개별 기사와 최종 투자판정이 같은 색상 함수를 사용하도록 전부 연결한다.
prev._final_color = _color
guard._enhanced_body_color = _color
guard.prev._strict_body_color = _color
guard.prev.core._body_color = _color


def _disaster_only(items):
    return items and all(_is_disaster_recovery(x) for x in items)


def _verdict(items):
    disaster_items = [x for x in items if _is_disaster_recovery(x)]
    war_items = [x for x in items if not _is_disaster_recovery(x)]
    if disaster_items and not war_items:
        marks = {m for x in disaster_items for m in _disaster_marks(x)}
        if '네팔재건사업집행' in marks:
            stage = '사업 집행 단계 — 입찰·조달·계약·착공의 실제 사업 전환 확인'
            nxt = '발주기관·사업목록 → 입찰 → 계약금액 → 착공·매출 인식'
        elif 'KDRT재건복구현장투입' in marks:
            stage = '현장 복구 실행 단계 — 인력·장비 투입과 실제 복구 범위 확인'
            nxt = '현장 투입 → 복구 대상·기간 → 정부·국제기구 재원 → 사업 발주'
        elif 'KDRT재건복구파견' in marks:
            stage = '재건·복구팀 파견 단계 — 도착 후 임무 범위와 현장 투입 확인'
            nxt = '현지 도착 → 임무 범위 → 복구 대상·기간 → 후속 재건 사업'
        else:
            stage = '재건·복구 전환 단계 — 계획에서 실제 집행으로 이동하는지 확인'
            nxt = '임무 확정 → 파견·도착 → 현장 복구 → 재원·사업목록'
        return (
            '<b>투자 판정</b>\n'
            '- <b>핵심:</b> 전쟁 휴전이 아니라 자연재난의 재건·복구 실행 신호\n'
            f'- <b>현재 단계:</b> {stage}\n'
            '- <b>시장:</b> 단기 금융시장 영향보다 전력·수자원·도로·주택 복구 발주 여부가 핵심\n'
            f'- <b>다음:</b> {nxt}'
        )
    if disaster_items and war_items:
        # 서로 다른 지역축을 하나의 '휴전 신호'로 오해하지 않게 명시한다.
        base_text = _prev_verdict(war_items)
        return base_text + '\n- <b>재난 재건:</b> 네팔 KDRT·재건복구 실행 신호는 전쟁·휴전과 별도 축으로 추적'
    return _prev_verdict(items)

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
