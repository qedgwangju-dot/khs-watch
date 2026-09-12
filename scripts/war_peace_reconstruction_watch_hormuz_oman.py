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

HORMUZ_QUERIES = [
    'site:tass.com Iran Oman Hormuz southern route closed US demand when:2d',
    'site:reuters.com Iran Oman Hormuz signed deal southern route closed when:2d',
    'site:fm.gov.om Iran Hormuz temporary corridor safe navigation when:30d',
    'site:tasnimnews.ir Hormuz Oman southern route closed US conditions when:30d',
    '(Iran OR 이란) (Oman OR 오만) (Hormuz OR 호르무즈) (southern route OR 남부 항로 OR southern lane OR 남부 항행로) (closed OR 폐쇄 OR reopen OR 재개방) when:7d',
]
watch.QUERIES = HORMUZ_QUERIES + list(watch.QUERIES)

IRAN_TERMS = ('iran','iranian','이란')
OMAN_TERMS = ('oman','omani','오만')
HORMUZ_TERMS = ('hormuz','strait of hormuz','호르무즈')
CLOSED_TERMS = ('will remain closed','remain closed','stays closed','stay closed','not reopen','will not reopen','폐쇄 유지','폐쇄될 것','재개방되지','재개방하지')
SOUTH_TERMS = ('southern route','southern lane','omani route','oman route','남부 항로','남부항로','오만 항로','남부 항행로')
US_DEMAND_TERMS = ('us demand','u.s. demand','washington wants','united states wants','미국의 재개방 요구','미국 요구','미국이 요구')
NO_DEAL_TERMS = ('no signed deal','no agreement expected','not result in a signed agreement','signed agreement is not expected','서명 합의는 없','최종 합의는 없','합의 서명은 없')
TEMP_CORRIDOR_TERMS = ('temporary corridor','temporary navigational corridor','joint temporary navigational corridor','임시 통항 회랑','임시 항행 회랑','임시 회랑')
SAFE_NAV_TERMS = ('safe navigation','resumption of safe navigation','restore safe navigation','안전 항행','안전한 항행','항행 재개')


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
    if _has(t, US_DEMAND_TERMS):
        marks.append('미국재개방요구충돌')
    if _has(t, NO_DEAL_TERMS):
        marks.append('최종합의미완료')
    if _has(t, OMAN_TERMS) and _has(t, TEMP_CORRIDOR_TERMS):
        marks.append('임시회랑프레임워크')
    if _has(t, OMAN_TERMS) and _has(t, SAFE_NAV_TERMS):
        marks.append('오만안전항행추진')
    return sorted(set(marks))


def _signals(row, marks):
    out = []
    if '호르무즈폐쇄지속' in marks:
        out.append('이란 측: 호르무즈 해협의 전면 재개방은 아직 불가 — 미국의 조건 이행과 새 통항 체계 수용을 요구')
    if '남부항로폐쇄' in marks:
        out.append('이란 측: 미국이 이용을 요구해온 오만 연안 남부 항로는 새 체계 아래 폐쇄 대상')
    if '최종합의미완료' in marks:
        out.append('최신 협상은 계속 중이며 최종 서명 합의는 아직 미완료 — 이란 측 입장과 상호 합의를 구분')
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
        score = 58
        tags = ['호르무즈','통항제한','에너지위험']
    elif '최종합의미완료' in marks:
        score = 48
        tags = ['호르무즈','협상지연']
    elif '임시회랑프레임워크' in marks or '오만안전항행추진' in marks:
        score = 44
        tags = ['호르무즈','종전·협상']
    else:
        return _prev_score(row, now)
    src = ' '.join([row.get('source',''), row.get('link','')]).lower()
    if any(k in src for k in ('reuters','fm.gov.om','tass','tasnim')):
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
    stages = [m for m in marks if m in ('호르무즈폐쇄지속','남부항로폐쇄','최종합의미완료','임시회랑프레임워크','오만안전항행추진')]
    if not stages:
        return _prev_item_id(row)
    key = 'iran-oman-hormuz-route|' + '|'.join(sorted(stages))
    return hashlib.sha256(key.encode()).hexdigest()[:20]

watch.item_id = item_id


def topic_label(row):
    if _marks(row):
        return '이란·오만·호르무즈'
    return _prev_topic_label(row)

watch.topic_label = topic_label


def _verdict(items):
    hm = [x for x in items if _marks(x)]
    others = [x for x in items if x not in hm]
    if hm and not others:
        marks = {m for x in hm for m in _marks(x)}
        if '호르무즈폐쇄지속' in marks or '남부항로폐쇄' in marks:
            return (
                '<b>투자 판정</b>\n'
                '- <b>핵심:</b> 이란은 전면 재개방·미국 주도 남부 항로를 거부 — 해협 정상화 기대 후퇴\n'
                '- <b>현재 단계:</b> 이란 측 조건부 폐쇄 입장 / 오만은 임시 회랑·안전 항행 복원 추진 — 최종 공동합의와 구분\n'
                '- <b>시장:</b> 통항 제한 지속 시 원유·LNG·해운·보험 위험프리미엄 상방\n'
                '- <b>다음:</b> 9월 14일 오만 회담 → 서명 합의 여부 → 남부 항로·임시 회랑 실제 통항량'
            )
        if '최종합의미완료' in marks:
            return (
                '<b>투자 판정</b>\n'
                '- <b>핵심:</b> 호르무즈 협상은 진행 중이지만 최종 서명 합의는 아직 없음\n'
                '- <b>현재 단계:</b> 이란·오만·GCC 협상 단계 — 실제 재개방 확정 아님\n'
                '- <b>시장:</b> 외교 기대와 물류 차질이 병존해 유가·운임 변동성 지속\n'
                '- <b>다음:</b> 공동성명 → 시행일 → 실제 선박 통항량·보험료 확인'
            )
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
