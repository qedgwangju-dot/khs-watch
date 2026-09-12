#!/usr/bin/env python3
import argparse
import hashlib

import war_peace_reconstruction_watch_gulf_diplomacy as prev

watch = prev.watch
runner = prev.runner
base = prev.base
guard = prev.guard

_prev_score = watch.score_item
_prev_item_id = watch.item_id
_prev_topic_label = watch.topic_label
_prev_verdict = guard._verdict
_prev_color = prev._color

# 호르무즈 협상 기대와 별개로, 실제 재개방을 막는 조건·거부 신호를 고신호로 추적한다.
CONSTRAINT_QUERIES = [
    'site:tasnimnews.com Iran Oman Hormuz will not reopen southern route remain closed when:7d',
    'site:tasnimnews.ir Iran Oman Hormuz reopening southern route closed when:7d',
    'site:reuters.com Iran Oman no signed Hormuz deal Monday control fees when:3d',
    '(Iran OR 이란) (Oman OR 오만) (Hormuz OR 호르무즈) (will not reopen OR remain closed OR no signed deal OR 재개방하지 OR 폐쇄 유지 OR 서명 합의) when:7d',
    '(Iran OR 이란) (southern route OR southern channel OR 남부 항로) (closed OR closure OR 폐쇄) (Hormuz OR 호르무즈) when:7d',
]
watch.QUERIES = CONSTRAINT_QUERIES + list(watch.QUERIES)

IRAN_TERMS = ('iran','iranian','tehran','이란','테헤란')
OMAN_TERMS = ('oman','omani','오만')
HORMUZ_TERMS = ('hormuz','strait of hormuz','호르무즈')
NO_REOPEN_TERMS = (
    'will not reopen','would not reopen','not reopen','will remain closed','remain closed','remains closed',
    'reopening is not automatic','does not mean reopening','does not mean the reopening',
    '재개방되지 않을','재개방하지 않을','재개방을 의미하지 않','자동 재개방이 아니','폐쇄 상태를 유지',
)
SOUTH_ROUTE_TERMS = ('southern route','southern channel','southern shipping route','남부 항로','남쪽 항로','남부 통항로')
CLOSE_TERMS = ('closed','closure','remain closed','kept closed','폐쇄','폐쇄 유지','닫힌 상태')
NO_DEAL_TERMS = (
    'no signed deal','no signed agreement','will not result in a signed agreement','not result in a signed agreement',
    'no agreement expected','서명 합의가 나오지','서명된 합의가 나오지','합의 서명은 기대하지','서명 합의 불발',
)
CONTROL_TERMS = ('control over the strait','control of the strait','strait control','해협 통제권','호르무즈 통제권')
FEE_TERMS = ('collect fees','charge fees','shipping fees','transit fees','선박 요금','통항료','통행료')
US_DEMAND_TERMS = ('us demand','u.s. demand','american demand','미국의 요구','미국 요구')
BAHRAIN_ABSENT_TERMS = ('bahrain will not participate','bahrain not participate','bahrain will not attend','바레인 불참','바레인이 참석하지')


def _text(row):
    return ' '.join([
        row.get('title_original',''), row.get('title_ko',''), row.get('description',''),
        row.get('article_text',''), ' '.join(row.get('signals_ko',[])),
    ]).lower()


def _has(t, terms):
    return any(k in t for k in terms)


def _marks(row):
    t = _text(row)
    if not (_has(t, IRAN_TERMS) and _has(t, HORMUZ_TERMS)):
        return []

    marks = []
    if _has(t, NO_REOPEN_TERMS):
        marks.append('호르무즈완전재개방거부')
    if _has(t, SOUTH_ROUTE_TERMS) and _has(t, CLOSE_TERMS):
        marks.append('남부항로폐쇄유지')
    if _has(t, OMAN_TERMS) and _has(t, NO_DEAL_TERMS):
        marks.append('오만회담서명합의불발전망')
    if _has(t, CONTROL_TERMS):
        marks.append('이란해협통제권요구')
    if _has(t, FEE_TERMS):
        marks.append('이란통항료요구')
    if _has(t, US_DEMAND_TERMS) and ('남부항로폐쇄유지' in marks or '호르무즈완전재개방거부' in marks):
        marks.append('미국요구와충돌')
    if _has(t, BAHRAIN_ABSENT_TERMS):
        marks.append('바레인회담불참')
    return sorted(set(marks))


def _strong(marks):
    return any(m in marks for m in (
        '호르무즈완전재개방거부','남부항로폐쇄유지','오만회담서명합의불발전망',
        '이란해협통제권요구','이란통항료요구','미국요구와충돌','바레인회담불참',
    ))


def _signals(marks):
    out = []
    if '호르무즈완전재개방거부' in marks:
        out.append('이란: 오만과의 합의가 호르무즈 해협의 자동·완전 재개방을 뜻하지 않는다는 기존 조건선 유지')
    if '남부항로폐쇄유지' in marks:
        out.append('이란: 미국이 요구하는 기존 남부 항로의 폐쇄 유지 요구 — 임시 통항회랑 협상과 별개 제약')
    if '오만회담서명합의불발전망' in marks:
        out.append('이란 고위 당국자: 오만 회담에서 호르무즈 서명 합의가 나오지 않을 전망 — 일정화 기대보다 실행 난도 상승')
    if '이란해협통제권요구' in marks:
        out.append('이란의 호르무즈 통제권 요구가 합의 병목으로 부상')
    if '이란통항료요구' in marks:
        out.append('이란의 선박 통항료·요금 요구가 오만 측 입장과 충돌하는지 추적')
    if '미국요구와충돌' in marks:
        out.append('미국의 자유항행·기존 항로 요구와 이란의 남부 항로 폐쇄 조건이 정면 충돌')
    if '바레인회담불참' in marks:
        out.append('바레인 불참 신호 — GCC 전체 공조·대표성 약화 여부 확인')
    return out


def score_item(row, now):
    marks = _marks(row)
    if not marks:
        return _prev_score(row, now)

    row['hormuz_constraint_marks'] = marks
    sig = _signals(marks)
    if sig:
        row['signals_ko'] = list(dict.fromkeys(sig + list(row.get('signals_ko', []))))

    score = 52 if _strong(marks) else 36
    age = watch.age_minutes(row, now)
    if age is not None:
        if age <= 30: score += 8
        elif age <= 180: score += 5
        elif age <= 720: score += 2
    tags = ['종전·협상','협상제약','재개방제약']
    row['forced_tags'] = list(dict.fromkeys(list(row.get('forced_tags', [])) + tags))
    return score, tags

watch.score_item = score_item


def item_id(row):
    marks = _marks(row)
    stage = [m for m in marks if _strong([m])]
    if not stage:
        return _prev_item_id(row)
    # 같은 제약이 다른 매체에 재전돼도 단계별 1회만 알림.
    key = 'iran-oman-hormuz-constraint-2026|' + '|'.join(sorted(stage))
    return hashlib.sha256(key.encode()).hexdigest()[:20]

watch.item_id = item_id


def topic_label(row):
    if _marks(row):
        return '이란·오만·호르무즈'
    return _prev_topic_label(row)

watch.topic_label = topic_label


def _color(row):
    marks = _marks(row)
    if marks:
        # 협상 제약은 공격도 휴전·재건도 아니므로 빨강/초록을 억지로 붙이지 않는다.
        return ''
    return _prev_color(row)

# 기존 색상 체인에는 영향 없이 제약 기사만 무색 + 경고 문구로 처리.
prev._color = _color
prev.houthi._color = _color
prev.houthi.recovery._color = _color
prev.houthi.final_guard._final_color = _color
guard._enhanced_body_color = _color
guard.prev._strict_body_color = _color
guard.prev.core._body_color = _color


def _is_constraint(row):
    return bool(_marks(row))


def _verdict(items):
    constraints = [x for x in items if _is_constraint(x)]
    others = [x for x in items if x not in constraints]
    if constraints and not others:
        marks = {m for x in constraints for m in _marks(x)}
        if '오만회담서명합의불발전망' in marks:
            stage = '회담은 예정돼 있지만 서명 합의 가능성은 낮아진 단계 — 외교 일정과 실제 재개방을 분리해야 함'
        elif '남부항로폐쇄유지' in marks or '호르무즈완전재개방거부' in marks:
            stage = '재개방 조건 충돌 단계 — 오만 임시 회랑 논의가 곧 해협 완전 재개방을 뜻하지 않음'
        else:
            stage = '협상 세부조건 충돌 단계 — 통제권·요금·참석국 이견 확인 필요'
        return (
            '<b>투자 판정</b>\n'
            '- <b>핵심:</b> ⚠️ 호르무즈 협상은 진행되지만 이란의 재개방 조건·남부 항로 폐쇄 요구가 실행을 제약\n'
            f'- <b>현재 단계:</b> {stage}\n'
            '- <b>시장:</b> 유가·해운·보험 위험프리미엄이 협상 기대만으로 빠르게 정상화되기 어려움\n'
            '- <b>다음:</b> 9월 14일 실제 회담 → 공식 합의문 → 남부 항로 처리 → 새 통항회랑 시행 → 실제 통항량 회복'
        )
    if constraints:
        base_text = _prev_verdict(others)
        return base_text + '\n- <b>⚠️ 재개방 제약:</b> 이란의 남부 항로 폐쇄·완전 재개방 거부 조건은 협상 기대와 별도로 추적'
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
