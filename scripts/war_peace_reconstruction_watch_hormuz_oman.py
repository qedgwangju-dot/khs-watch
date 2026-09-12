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

# 호르무즈 협상 기대와 별개로 실제 재개방을 막는 이란의 조건·거부 신호를 추적한다.
HORMUZ_QUERIES = [
    'site:tasnimnews.com Iran Oman Hormuz reopen southern route closed when:30d',
    'site:tasnimnews.ir Iran Oman Hormuz reopen southern route closed when:30d',
    'site:reuters.com Iran Oman Hormuz signed deal control fees Monday when:3d',
    'site:fm.gov.om Iran Hormuz temporary corridor safe navigation when:30d',
    '(Iran OR 이란) (Oman OR 오만) (Hormuz OR 호르무즈) (southern route OR 남부 항로 OR southern lane OR 남부 항행로) (closed OR 폐쇄 OR reopen OR 재개방) when:7d',
    '(Iran OR 이란) (Hormuz OR 호르무즈) (will not reopen OR remain closed OR no signed deal OR 재개방되지 않을 OR 폐쇄 유지 OR 서명 합의) when:7d',
]
watch.QUERIES = HORMUZ_QUERIES + list(watch.QUERIES)

IRAN_TERMS = ('iran','iranian','tehran','이란','테헤란')
OMAN_TERMS = ('oman','omani','오만')
HORMUZ_TERMS = ('hormuz','strait of hormuz','호르무즈')
CLOSED_TERMS = (
    'will remain closed','remain closed','remains closed','stays closed','stay closed','not reopen','will not reopen','would not reopen',
    'reopening is not automatic','does not mean reopening','does not mean the reopening',
    '폐쇄 유지','폐쇄될 것','폐쇄 상태를 유지','재개방되지','재개방하지','재개방을 의미하지','자동 재개방이 아니',
)
SOUTH_TERMS = (
    'southern route','southern lane','southern channel','southern shipping route','omani route','oman route',
    '남부 항로','남부항로','남부 항행로','남부 통항로','오만 항로',
)
US_DEMAND_TERMS = (
    'us demand','u.s. demand','american demand','washington wants','united states wants',
    '미국의 재개방 요구','미국의 요구','미국 요구','미국이 요구',
)
NO_DEAL_TERMS = (
    'no signed deal','no signed agreement','no agreement expected','signed agreement is not expected',
    'will not result in a signed agreement','not result in a signed agreement','no deal expected',
    '서명 합의는 없','서명 합의가 나오지','서명된 합의가 나오지','합의 서명은 기대하지','최종 합의는 없','합의 서명은 없','서명 합의 불발',
)
TEMP_CORRIDOR_TERMS = (
    'temporary corridor','temporary navigational corridor','joint temporary navigational corridor',
    '임시 통항 회랑','임시 항행 회랑','임시 회랑',
)
SAFE_NAV_TERMS = ('safe navigation','resumption of safe navigation','restore safe navigation','안전 항행','안전한 항행','항행 재개')
CONTROL_TERMS = ('control over the strait','control of the strait','strait control','해협 통제권','호르무즈 통제권')
FEE_TERMS = ('collect fees','charge fees','shipping fees','transit fees','선박 요금','통항료','통행료')
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
    if _has(t, CLOSED_TERMS):
        marks.append('호르무즈폐쇄지속')
    if _has(t, SOUTH_TERMS) and _has(t, CLOSED_TERMS):
        marks.append('남부항로폐쇄')
    if _has(t, US_DEMAND_TERMS) and ('호르무즈폐쇄지속' in marks or '남부항로폐쇄' in marks):
        marks.append('미국재개방요구충돌')
    if _has(t, NO_DEAL_TERMS):
        marks.append('최종합의미완료')
    if _has(t, CONTROL_TERMS):
        marks.append('이란통제권요구')
    if _has(t, FEE_TERMS):
        marks.append('이란통항료요구')
    if _has(t, BAHRAIN_ABSENT_TERMS):
        marks.append('바레인회담불참')
    if _has(t, OMAN_TERMS) and _has(t, TEMP_CORRIDOR_TERMS):
        marks.append('임시회랑프레임워크')
    if _has(t, OMAN_TERMS) and _has(t, SAFE_NAV_TERMS):
        marks.append('오만안전항행추진')
    return sorted(set(marks))


def _constraint(marks):
    return any(m in marks for m in (
        '호르무즈폐쇄지속','남부항로폐쇄','미국재개방요구충돌','최종합의미완료',
        '이란통제권요구','이란통항료요구','바레인회담불참',
    ))


def _signals(row, marks):
    out = []
    if '호르무즈폐쇄지속' in marks:
        out.append('이란 측: 오만과의 합의가 호르무즈의 자동·완전 재개방을 뜻하지 않는다는 조건선 유지')
    if '남부항로폐쇄' in marks:
        out.append('이란 측: 미국이 이용을 요구해온 남부 항로는 폐쇄 유지 요구 — 임시 회랑 협상과 별도 제약')
    if '미국재개방요구충돌' in marks:
        out.append('미국의 자유항행·기존 남부 항로 요구와 이란의 폐쇄 조건이 정면 충돌')
    if '최종합의미완료' in marks:
        out.append('이란 고위 당국자: 오만 회담에서도 서명 합의가 나오지 않을 전망 — 회담 일정과 실제 재개방을 분리 확인')
    if '이란통제권요구' in marks:
        out.append('이란의 호르무즈 통제권 요구가 합의 병목으로 부상')
    if '이란통항료요구' in marks:
        out.append('이란의 선박 통항료·요금 요구가 오만 측 입장과 충돌하는지 추적')
    if '바레인회담불참' in marks:
        out.append('바레인 불참 신호 — GCC 전체 공조·대표성 약화 여부 확인')
    if '임시회랑프레임워크' in marks or '오만안전항행추진' in marks:
        out.append('오만 공식입장: 임시 통항 회랑과 안전 항행 복원을 추진 — 전면 폐쇄를 공동 합의했다는 의미는 아님')
    return out


def score_item(row, now):
    marks = _marks(row)
    if not marks:
        return _prev_score(row, now)
    sig = _signals(row, marks)
    if sig:
        row['signals_ko'] = list(dict.fromkeys(sig + list(row.get('signals_ko', []))))
    row['hormuz_oman_marks'] = marks

    if '남부항로폐쇄' in marks or '호르무즈폐쇄지속' in marks:
        score = 62
        tags = ['호르무즈','협상제약','재개방제약','에너지위험']
    elif '최종합의미완료' in marks:
        score = 56
        tags = ['호르무즈','협상제약','재개방제약']
    elif '이란통제권요구' in marks or '이란통항료요구' in marks or '바레인회담불참' in marks:
        score = 50
        tags = ['호르무즈','협상제약']
    elif '임시회랑프레임워크' in marks or '오만안전항행추진' in marks:
        score = 44
        tags = ['호르무즈','종전·협상']
    else:
        return _prev_score(row, now)

    src = ' '.join([row.get('source',''), row.get('link',''), row.get('resolved_url','')]).lower()
    if any(k in src for k in ('reuters','fm.gov.om','tasnim')):
        score += 8
    age = watch.age_minutes(row, now)
    if age is not None:
        if age <= 30: score += 8
        elif age <= 180: score += 5
        elif age <= 720: score += 2
    row['forced_tags'] = list(dict.fromkeys(list(row.get('forced_tags', [])) + tags))
    return score, sorted(set(tags))

watch.score_item = score_item


def item_id(row):
    marks = _marks(row)
    stages = [m for m in marks if m in (
        '호르무즈폐쇄지속','남부항로폐쇄','미국재개방요구충돌','최종합의미완료',
        '이란통제권요구','이란통항료요구','바레인회담불참','임시회랑프레임워크','오만안전항행추진',
    )]
    if not stages:
        return _prev_item_id(row)
    # 같은 제약을 여러 매체가 재전해도 단계별 1회만 알린다.
    key = 'iran-oman-hormuz-route|' + '|'.join(sorted(stages))
    return hashlib.sha256(key.encode()).hexdigest()[:20]

watch.item_id = item_id


def topic_label(row):
    if _marks(row):
        return '이란·오만·호르무즈'
    return _prev_topic_label(row)

watch.topic_label = topic_label


def _color(row):
    marks = _marks(row)
    if _constraint(marks):
        # 협상 제약은 실제 공격도 휴전·재건도 아니므로 빨강/초록을 억지로 붙이지 않는다.
        return ''
    return _prev_color(row)

# 최종 개별 기사 색상과 투자 판정이 동일한 의미체계를 사용하도록 연결한다.
prev._color = _color
prev.houthi._color = _color
prev.houthi.recovery._color = _color
prev.houthi.final_guard._final_color = _color
guard._enhanced_body_color = _color
guard.prev._strict_body_color = _color
guard.prev.core._body_color = _color


def _verdict(items):
    hm = [x for x in items if _marks(x)]
    others = [x for x in items if x not in hm]
    if hm and not others:
        marks = {m for x in hm for m in _marks(x)}
        if '호르무즈폐쇄지속' in marks or '남부항로폐쇄' in marks:
            return (
                '<b>투자 판정</b>\n'
                '- <b>핵심:</b> ⚠️ 이란은 전면 재개방·미국 주도 남부 항로를 거부 — 협상 일정과 실제 해협 정상화를 분리해야 함\n'
                '- <b>현재 단계:</b> 재개방 조건 충돌 단계 — 오만은 임시 회랑·안전 항행 복원을 추진하지만 자동 재개방은 아님\n'
                '- <b>시장:</b> 통항 제한 지속 시 원유·LNG·해운·보험 위험프리미엄 상방\n'
                '- <b>다음:</b> 9월 14일 오만 회담 → 서명 합의 여부 → 남부 항로 처리 → 임시 회랑 실제 통항량'
            )
        if '최종합의미완료' in marks:
            return (
                '<b>투자 판정</b>\n'
                '- <b>핵심:</b> ⚠️ 호르무즈 협상은 진행 중이지만 오만 회담에서도 서명 합의가 나오지 않을 가능성이 높아짐\n'
                '- <b>현재 단계:</b> 협상 일정화와 실행 제약이 동시에 존재 — 실제 재개방 확정 아님\n'
                '- <b>시장:</b> 외교 기대와 물류 차질이 병존해 유가·운임 변동성 지속\n'
                '- <b>다음:</b> 실제 회담 → 공동성명 → 시행일 → 남부 항로·통항량·보험료 확인'
            )
        if _constraint(marks):
            return (
                '<b>투자 판정</b>\n'
                '- <b>핵심:</b> ⚠️ 호르무즈 협상의 통제권·통항료·참석국 조건이 실행 병목으로 남아 있음\n'
                '- <b>현재 단계:</b> 세부조건 충돌 단계 — 일정 자체보다 최종 합의문이 중요\n'
                '- <b>시장:</b> 공급 정상화 기대를 선반영하기 이른 단계\n'
                '- <b>다음:</b> 공식 참석국 → 합의문 → 실제 항로 시행 → 통항량 회복'
            )
    if hm and others:
        return _prev_verdict(others) + '\n- <b>⚠️ 재개방 제약:</b> 이란의 남부 항로 폐쇄·완전 재개방 거부·서명합의 불발 전망을 협상 기대와 별도로 추적'
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
