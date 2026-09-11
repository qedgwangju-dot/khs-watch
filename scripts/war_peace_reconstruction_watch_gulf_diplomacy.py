#!/usr/bin/env python3
import argparse
import hashlib

import war_peace_reconstruction_watch_aluminium_supply as prev

watch = prev.watch
runner = prev.runner
base = prev.base
guard = prev.guard

_prev_score = watch.score_item
_prev_item_id = watch.item_id
_prev_topic_label = watch.topic_label
_prev_verdict = guard._verdict

# FT 보도 → 오만·GCC 공식 일정 → 실제 개최 → 공동성명 → 실물 통항 회복을 단계별로 추적한다.
DIPLOMACY_QUERIES = [
    'site:ft.com (Iran OR Iranian) (Gulf states OR GCC) (Salalah OR Oman) (Hormuz OR shipping) when:2d',
    'site:fm.gov.om (Iran OR Iranian) (GCC OR Gulf states OR Salalah) (Hormuz OR navigation OR meeting) when:7d',
    'site:gcc-sg.org (Iran OR Iranian) (Salalah OR Oman OR Hormuz) when:7d',
    '(Iran OR 이란) (GCC OR 걸프협력회의 OR Gulf states OR 걸프 국가) (Salalah OR 살랄라) (meeting OR talks OR 외무장관 OR 회담) when:3d',
    '(Strait of Hormuz OR 호르무즈) (temporary agreement OR interim agreement OR temporary corridor OR 임시 합의 OR 통항 회랑) (GCC OR Gulf states OR 걸프) when:3d',
]
watch.QUERIES = DIPLOMACY_QUERIES + list(watch.QUERIES)

IRAN_TERMS = ('iran','iranian','araghchi','이란','아락치')
GCC_TERMS = ('gulf cooperation council','gcc','gulf states','six-member gulf','걸프협력회의','걸프 국가','걸프국')
SALALAH_TERMS = ('salalah','살랄라')
HORMUZ_TERMS = ('strait of hormuz','hormuz','호르무즈')
SCHEDULE_TERMS = (
    'scheduled to be held','scheduled for','set to meet','plan to meet','plans to meet','will meet','on monday','monday',
    'september 14','sept. 14','14 september','9월 14일','월요일','열릴 예정','회담 예정','만날 예정','개최 예정',
)
HELD_TERMS = ('met in salalah','meeting was held','held talks','convened in salalah','gathered in salalah','살랄라에서 회담','회담 개최','회의 개최','회담이 열렸다','만났다')
OUTCOME_TERMS = ('joint statement','temporary agreement','interim agreement','temporary corridor','shipping corridor','safe navigation','freedom of navigation','공동성명','임시 합의','임시 통항','항행 회랑','통항 회랑','안전 항행')
FLOW_TERMS = ('shipping resumed','traffic increased','transit increased','strait reopened','flows recovered','통항 재개','운항 재개','통항량 증가','항행 정상화','물동량 회복')
DELAY_TERMS = ('postponed','cancelled','canceled','called off','연기','취소','무산')
NOT_FINAL_TERMS = ('details were not finalised','details were not finalized','not finalised','not finalized','세부사항은 아직 확정되지','세부 사항 미확정','최종 확정 전')
ATTENDANCE_TERMS = ('states had confirmed','some states confirmed','countries had confirmed','참석을 확정','일부 국가 참석 확정','일부 국가들이 참석을 확정')
OFFICIAL_HOSTS = ('fm.gov.om','gcc-sg.org','omannews.gov.om')


def _text(row):
    return ' '.join([
        row.get('title_original',''), row.get('title_ko',''), row.get('description',''),
        row.get('article_text',''), ' '.join(row.get('signals_ko',[])),
    ]).lower()


def _has(t, terms):
    return any(k in t for k in terms)


def _official(row):
    blob = ' '.join([row.get('source',''), row.get('link',''), row.get('resolved_url','')]).lower()
    return any(h in blob for h in OFFICIAL_HOSTS) or 'oman foreign ministry' in blob or '오만 외교부' in blob


def _marks(row):
    t = _text(row)
    if not (_has(t, IRAN_TERMS) and _has(t, GCC_TERMS) and (_has(t, SALALAH_TERMS) or _has(t, HORMUZ_TERMS))):
        return []

    marks = []
    if _has(t, DELAY_TERMS):
        marks.append('살랄라회담연기취소')
    if _has(t, HELD_TERMS):
        marks.append('살랄라회담실제개최')
    elif _has(t, SCHEDULE_TERMS) and _has(t, SALALAH_TERMS):
        marks.append('살랄라회담공식일정' if _official(row) else '살랄라회담FT일정화')
    if _has(t, ATTENDANCE_TERMS):
        marks.append('GCC참석확인')
    if _has(t, NOT_FINAL_TERMS):
        marks.append('세부사항미확정')
    if _has(t, OUTCOME_TERMS):
        marks.append('호르무즈임시합의')
    if _has(t, FLOW_TERMS):
        marks.append('호르무즈실물통항회복')
    return sorted(set(marks))


def _positive(marks):
    return any(m in marks for m in ('살랄라회담FT일정화','살랄라회담공식일정','살랄라회담실제개최','호르무즈임시합의','호르무즈실물통항회복'))


def _signals(row, marks):
    out = []
    if '살랄라회담FT일정화' in marks:
        out.append('FT 복수 소식통: 이란 외무장관과 GCC 외교장관들이 9월 14일 월요일 오만 살랄라에서 회담 예정')
        out.append('검증 수준: FT 복수 소식통 확인 — 오만·GCC 공식 일정 공지 대기')
    if '살랄라회담공식일정' in marks:
        out.append('오만·GCC 공식자료로 살랄라 이란-GCC 외무장관 회담 일정 확인 — 보도 단계에서 공식확정 단계로 상승')
    if 'GCC참석확인' in marks:
        out.append('일부 GCC 국가 참석 확인 — 전체 6개국 참석자·직급은 후속 공식명단 확인 필요')
    if '세부사항미확정' in marks:
        out.append('세부사항은 아직 최종 확정 전 — 회담 취소·연기 가능성을 별도 추적')
    if '살랄라회담실제개최' in marks:
        out.append('살랄라 이란-GCC 회담 실제 개최 — 일정 신호에서 실행 단계로 상승')
    if '호르무즈임시합의' in marks:
        out.append('호르무즈 임시 통항 합의·공동성명 신호 — 문안·적용기간·통항 규칙 확인 필요')
    if '호르무즈실물통항회복' in marks:
        out.append('호르무즈 실제 선박 통항 회복 확인 — 외교 합의가 실물 물류로 전환되는 단계')
    if '살랄라회담연기취소' in marks:
        out.append('살랄라 회담 연기·취소 신호 — 외교 일정 후퇴, 기존 완화 기대 재평가 필요')
    return out


def score_item(row, now):
    marks = _marks(row)
    if not marks:
        return _prev_score(row, now)

    row['gulf_diplomacy_marks'] = marks
    sig = _signals(row, marks)
    if sig:
        row['signals_ko'] = list(dict.fromkeys(sig + list(row.get('signals_ko', []))))

    if '살랄라회담연기취소' in marks:
        score = 44
        tags = ['종전·협상','협상지연']
    elif '호르무즈실물통항회복' in marks:
        score = 62
        tags = ['종전·협상','휴전·평화','행동완화']
    elif '호르무즈임시합의' in marks:
        score = 58
        tags = ['종전·협상','휴전·평화','행동완화']
    elif '살랄라회담실제개최' in marks:
        score = 54
        tags = ['종전·협상','휴전·평화']
    elif '살랄라회담공식일정' in marks:
        score = 50
        tags = ['종전·협상','휴전·평화']
    elif '살랄라회담FT일정화' in marks:
        score = 44
        tags = ['종전·협상','휴전·평화']
    else:
        return _prev_score(row, now)

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
        '살랄라회담FT일정화','살랄라회담공식일정','살랄라회담실제개최','호르무즈임시합의','호르무즈실물통항회복','살랄라회담연기취소',
    )]
    if not stages:
        return _prev_item_id(row)
    # 같은 회담을 여러 매체가 재전해도 단계별 1회만 알린다.
    key = 'iran-gcc-salalah-2026-09-14|' + '|'.join(sorted(stages))
    return hashlib.sha256(key.encode()).hexdigest()[:20]

watch.item_id = item_id


def topic_label(row):
    if _marks(row):
        return '이란·GCC·호르무즈'
    return _prev_topic_label(row)

watch.topic_label = topic_label

# 기존 최종 색상 안전장치 체인에 살랄라 외교단계만 추가한다.
houthi = prev.prev
_prev_color = houthi._color


def _color(row):
    marks = _marks(row)
    if '살랄라회담연기취소' in marks:
        return ''
    if _positive(marks):
        headline = ' '.join([row.get('title_original',''), row.get('title_ko',''), row.get('description','')]).lower()
        attack_now = any(k in headline for k in ('missile attack','drone attack','airstrike','retaliatory attack','공습','미사일 공격','드론 공격','보복 공격','피격','사망','부상'))
        if not attack_now:
            return 'green'
    return _prev_color(row)

houthi._color = _color
houthi.recovery._color = _color
houthi.final_guard._final_color = _color
guard._enhanced_body_color = _color
guard.prev._strict_body_color = _color
guard.prev.core._body_color = _color


def _is_diplomacy(row):
    return bool(_marks(row))


def _verdict(items):
    dip = [x for x in items if _is_diplomacy(x)]
    others = [x for x in items if x not in dip]
    if dip and not others:
        marks = {m for x in dip for m in _marks(x)}
        if '살랄라회담연기취소' in marks:
            return (
                '<b>투자 판정</b>\n'
                '- <b>핵심:</b> 살랄라 이란-GCC 회담 일정이 후퇴 — 기존 호르무즈 완화 기대 재평가 필요\n'
                '- <b>현재 단계:</b> 협상 일정 지연 단계 — 실제 공격·봉쇄 변화와 별도 확인\n'
                '- <b>시장:</b> 유가·해운·전쟁보험 위험프리미엄 재확대 가능\n'
                '- <b>다음:</b> 새 회담 일정 → 공식 참석국 → 임시 통항 합의 여부'
            )
        if '호르무즈실물통항회복' in marks:
            stage = '실물 이행 단계 — 외교 합의가 실제 선박 통항 회복으로 연결'
            nxt = '통항량 지속 회복 → 보험료·운임 하락 → 원유·LNG 수출 정상화'
        elif '호르무즈임시합의' in marks:
            stage = '합의 문안 단계 — 임시 통항 회랑의 기간·규칙·미국 수용 여부 확인'
            nxt = '공동성명 세부문안 → 실제 시행일 → 선박 통항량 회복'
        elif '살랄라회담실제개최' in marks:
            stage = '실제 회담 개최 단계 — 공동성명·임시 통항 합의가 다음 확인점'
            nxt = '공동성명 → 임시 통항 회랑 → 미국·이란 수용 → 실제 물류 회복'
        elif '살랄라회담공식일정' in marks:
            stage = '공식 일정 확정 단계 — 참석국·의제·대표급 확인 필요'
            nxt = '9월 14일 실제 개최 → 공동성명 → 임시 통항 합의'
        else:
            stage = 'FT 복수 소식통 일정화 단계 — 오만·GCC 공식 공지는 아직 대기'
            nxt = '오만·GCC 공식 일정 → 참석국 명단 → 실제 개최 → 공동성명'
        return (
            '<b>투자 판정</b>\n'
            '- <b>핵심:</b> 이란·GCC 외교가 막연한 대화 가능성에서 날짜·장소가 있는 살랄라 회담 단계로 상승\n'
            f'- <b>현재 단계:</b> {stage}\n'
            '- <b>시장:</b> 회담 자체보다 호르무즈 임시 통항 합의와 실제 선박 통항 회복이 유가·해운·보험 위험프리미엄을 낮추는 핵심\n'
            f'- <b>다음:</b> {nxt}'
        )
    if dip:
        return _prev_verdict(others) + '\n- <b>이란·GCC 외교:</b> 살랄라 회담 일정화→공식확정→개최→합의→실물 통항 회복을 별도 🟢 단계로 추적'
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
