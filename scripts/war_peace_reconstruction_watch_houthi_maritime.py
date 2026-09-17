#!/usr/bin/env python3
import argparse
import hashlib

import war_peace_reconstruction_watch_disaster_verify as prev

watch = prev.watch
runner = prev.runner
base = prev.base
guard = prev.guard
recovery = prev.prev
final_guard = recovery.prev

_prev_score = watch.score_item
_prev_item_id = watch.item_id
_prev_topic_label = watch.topic_label
_prev_color = recovery._color
_prev_verdict = guard._verdict

# 후티의 바브엘만데브 군사·해상 변화와 사우디-오만-Ansar Allah 휴전 중재를 함께 추적한다.
MARITIME_QUERIES = [
    'site:reuters.com (Houthis OR Houthi) (Mokha OR Mocha OR Bab el-Mandeb OR Hanish OR Perim OR Mayyun OR Dhubab) (seized OR captured OR blockade OR shipping OR navigation) when:12h',
    'site:apnews.com (Houthis OR Houthi) (Mokha OR Mocha OR Bab el-Mandeb) (captured OR seized OR shipping OR blockade) when:12h',
    '(후티 OR Houthis) (목하 OR 모카 OR Mokha OR Mocha OR 바브엘만데브 OR Bab el-Mandeb) (점령 OR 장악 OR 진입 OR 봉쇄 OR 공격 OR 항행) when:12h',
    '(Houthis OR 후티) (Hanish OR 하니시 OR Perim OR 페림 OR Mayyun OR 마이윤 OR Dhubab OR 두바브) (advance OR seize OR capture OR 진격 OR 점령 OR 장악) when:12h',
    'site:maritime.dot.gov (Red Sea OR Bab el Mandeb) Houthi attacks commercial vessels 2026',
    'site:reuters.com Saudi Oman (Houthi OR Houthis OR "Ansar Allah") (mediation OR truce OR ceasefire OR talks) when:2d',
    'site:apnews.com Saudi Oman (Houthi OR Houthis OR "Ansar Allah") (mediation OR truce OR ceasefire OR talks) when:2d',
    'site:fm.gov.om Saudi Yemen (Houthi OR "Ansar Allah") (mediation OR ceasefire OR truce OR talks) when:7d',
    'site:spa.gov.sa Oman Yemen Houthi (mediation OR ceasefire OR truce OR talks) when:7d',
    '(Saudi OR Saudi Arabia OR السعودية OR 사우디) (Oman OR عمان OR 오만) (Houthi OR Houthis OR "Ansar Allah" OR أنصار الله OR 후티 OR 안사르 알라) (mediation OR mediator OR truce OR ceasefire OR هدنة OR وساطة OR 중재 OR 휴전) when:2d',
    '(Houthi OR Houthis OR "Ansar Allah" OR أنصار الله OR 후티 OR 안사르 알라) ("two-week truce" OR "two week truce" OR "two-week ceasefire" OR "two week ceasefire" OR "2-week truce" OR "2-week ceasefire" OR "هدنة لمدة أسبوعين" OR "هدنة أسبوعين" OR 2주 휴전) when:7d',
    '(Saudi OR السعودية OR 사우디) (Houthi OR "Ansar Allah" OR أنصار الله OR 후티) (humanitarian demands OR humanitarian files OR humanitarian requirements OR المطالب الإنسانية OR الملفات الإنسانية OR 인도적 요구 OR 인도적 사안) (Oman OR عمان OR 오만) when:7d',
    '(Saudi OR السعودية OR 사우디) (Houthi OR "Ansar Allah" OR أنصار الله OR 후티) (weekend OR "end of this week" OR نهاية الأسبوع OR 이번 주말 OR 주말) (agreement OR announce OR announcement OR اتفاق OR إعلان OR 합의 OR 발표) when:7d',
]
watch.QUERIES = MARITIME_QUERIES + list(watch.QUERIES)

HOUTHI_TERMS = ('houthi', 'houthis', 'ansarallah', 'ansar allah', 'أنصار الله', 'الحوثي', 'الحوثيين', '후티', '안사르알라', '안사르 알라')
MOKHA_TERMS = ('mokha', 'mocha', 'al-makha', 'al mokha', '목하', '모카')
BAB_TERMS = ('bab el-mandeb', 'bab al-mandab', 'bab el mandeb', 'bab al mandab', '바브엘만데브', '바브 알만데브')
ISLAND_APPROACH_TERMS = ('hanish', '하니시', 'perim', '페림', 'mayyun', '마이윤', 'dhubab', '두바브')
CAPTURE_TERMS = ('captured', 'seized', 'took control', 'entered the port', 'entered mokha', '점령', '장악', '함락', '진입')
ADVANCE_TERMS = ('advance', 'advanced', 'advancing', 'push toward', 'pushes toward', '진격', '접근', '밀고 내려', '남하')
BLOCKADE_TERMS = ('naval blockade', 'blockade', 'shipping blockade', '봉쇄', '해상 봉쇄', '항행 금지')
ATTACK_SHIPPING_TERMS = ('attack on shipping', 'attacks on shipping', 'attacked ship', 'attacked ships', 'attacked vessel', 'attacked vessels', 'targeted shipping', 'targeted vessels', '선박 공격', '상선 공격', '유조선 공격', '해운 공격')
SAFE_CLAIM_TERMS = ('freedom of navigation', 'navigation is safe', 'safe and uninterrupted', 'shipping is safe', 'international trade is safe', '항해의 자유', '항행은 안전', '항해는 안전', '안전하고 중단 없이', '국제 무역은 안전')
SAUDI_TARGET_TERMS = ('saudi ships', 'saudi shipping', 'saudi vessels', '사우디 선박', '사우디 해운')
SAUDI_TERMS = ('saudi', 'saudi arabia', 'riyadh', 'السعودية', 'الرياض', '사우디', '리야드')
OMAN_TERMS = ('oman', 'omani', 'muscat', 'عمان', 'مسقط', '오만', '무스카트')
MEDIATION_TERMS = ('mediation', 'mediate', 'mediator', 'asked oman to mediate', 'requested oman to mediate', 'oman-mediated', 'وساطة', 'التوسط', 'طلبت من عمان', '중재', '중재 요청', '오만에 중재')
TRUCE_TERMS = ('truce', 'ceasefire', 'cease-fire', 'وقف إطلاق النار', 'هدنة', '휴전', '정전')
TWO_WEEK_TERMS = ('two-week', 'two week', '2-week', '2 week', 'two weeks', 'for two weeks', 'أسبوعين', 'اسبوعين', 'لمدة أسبوعين', '2주', '2주간')
HUMANITARIAN_TERMS = ('humanitarian demand', 'humanitarian demands', 'humanitarian file', 'humanitarian files', 'humanitarian requirement', 'humanitarian requirements', 'humanitarian issue', 'humanitarian issues', 'المطالب الإنسانية', 'الملفات الإنسانية', 'المتطلبات الإنسانية', 'إنسانية', '인도적 요구', '인도적 사안', '인도주의', '인도적 문제')
DISCUSS_TERMS = ('discuss', 'discussing', 'discussion', 'negotiate', 'negotiation', 'address', 'talks', 'بحث', 'مناقشة', 'التفاوض', '논의', '협의', '협상')
WEEKEND_TERMS = ('by the weekend', 'this weekend', 'by end of this week', 'by the end of this week', 'weekend', 'نهاية الأسبوع', 'بحلول نهاية الأسبوع', '이번 주말', '주말까지')
ANNOUNCE_TERMS = ('announce', 'announcement', 'agreement announcement', 'deal announcement', 'expected agreement', 'target agreement', 'إعلان', 'اتفاق', 'إعلان الاتفاق', '합의 발표', '발표 목표', '합의 목표')
ACCEPT_TERMS = ('accepted', 'agreed to', 'agrees to', 'approved', 'وافق', 'وافقت', 'قبِل', 'قبل', '수용', '동의')
REJECT_TERMS = ('rejected', 'refused', 'rejects', 'رفض', 'ترفض', '거부', '거절')
TRUSTED_DIPLOMACY_SOURCES = ('reuters', 'apnews', 'fm.gov.om', 'spa.gov.sa', 'osesgy', 'unmissions.org', 'saba.ye', 'ansarollah', 'almasirah')


def _text(row):
    return ' '.join([
        row.get('title_original', ''), row.get('title_ko', ''), row.get('description', ''),
        row.get('article_text', ''), ' '.join(row.get('signals_ko', [])),
    ]).lower()


def _source(row):
    return ' '.join([row.get('source', ''), row.get('link', ''), row.get('resolved_url', '')]).lower()


def _has(t, terms):
    return any(k in t for k in terms)


def _trusted_diplomacy(row):
    return any(k in _source(row) for k in TRUSTED_DIPLOMACY_SOURCES)


def _maritime_marks(row):
    t = _text(row)
    marks = []
    houthi = _has(t, HOUTHI_TERMS)
    mokha = _has(t, MOKHA_TERMS)
    bab = _has(t, BAB_TERMS)
    approach = _has(t, ISLAND_APPROACH_TERMS)

    if not houthi:
        return marks

    if mokha and _has(t, ADVANCE_TERMS) and not _has(t, CAPTURE_TERMS):
        marks.append('후티목하접근')
    if mokha and _has(t, CAPTURE_TERMS):
        marks.append('후티목하점령')
    if approach and _has(t, ADVANCE_TERMS + CAPTURE_TERMS):
        marks.append('후티바브접근통제강화')
    if (bab or mokha or approach) and _has(t, BLOCKADE_TERMS):
        marks.append('후티해상봉쇄')
    if (bab or mokha or approach) and _has(t, ATTACK_SHIPPING_TERMS):
        marks.append('후티선박공격')
    if _has(t, SAFE_CLAIM_TERMS):
        marks.append('후티항행안전주장')
    if _has(t, SAUDI_TARGET_TERMS) and _has(t, BLOCKADE_TERMS + ATTACK_SHIPPING_TERMS):
        marks.append('사우디선박선별위협')

    saudi = _has(t, SAUDI_TERMS)
    oman = _has(t, OMAN_TERMS)
    truce = _has(t, TRUCE_TERMS)
    if saudi and oman and _has(t, MEDIATION_TERMS):
        marks.append('사우디오만중재요청')
    if truce and _has(t, TWO_WEEK_TERMS):
        marks.append('2주임시휴전안')
    if _has(t, HUMANITARIAN_TERMS) and _has(t, DISCUSS_TERMS):
        marks.append('인도적요구포괄협의')
    if _has(t, WEEKEND_TERMS) and _has(t, ANNOUNCE_TERMS):
        marks.append('주말합의발표목표')
    if truce and _has(t, ACCEPT_TERMS) and _trusted_diplomacy(row):
        marks.append('후티휴전수용')
    if truce and _has(t, REJECT_TERMS) and _trusted_diplomacy(row):
        marks.append('후티휴전거부')
    return sorted(set(marks))


def _strong_red(marks):
    return any(m in marks for m in (
        '후티목하접근', '후티목하점령', '후티바브접근통제강화', '후티해상봉쇄', '후티선박공격', '사우디선박선별위협', '후티휴전거부',
    ))


def _diplomacy_marks(marks):
    return [m for m in marks if m in (
        '사우디오만중재요청', '2주임시휴전안', '인도적요구포괄협의', '주말합의발표목표', '후티휴전수용', '후티휴전거부',
    )]


def _signals(marks, trusted=False):
    out = []
    if '후티목하점령' in marks:
        out.append('후티가 전략항 목하를 점령 — 바브엘만데브 접근 통제력이 한 단계 상승')
    elif '후티목하접근' in marks:
        out.append('후티가 목하·바브엘만데브 방향으로 진격 — 전략 해협 접근 단계')
    if '후티바브접근통제강화' in marks:
        out.append('하니시·페림·마이윤·두바브 등 바브엘만데브 접근축 통제 확대 여부 추적')
    if '후티해상봉쇄' in marks:
        out.append('후티의 해상 봉쇄·항행 제한 행동 확인 — 선언과 실제 집행을 분리 추적')
    if '후티선박공격' in marks:
        out.append('상선·유조선 공격이 실제 발생 — 통항량·보험료·우회운항 변화 확인')
    if '사우디선박선별위협' in marks:
        out.append('전체 국제항행과 사우디 연계 선박을 구분 — 선별 봉쇄·공격 위험')
    if '후티항행안전주장' in marks:
        if _strong_red(marks):
            out.append('후티는 항행 안전을 주장하지만 영토 장악·봉쇄·공격 행동과 괴리 — 발언보다 실제 행동 우선')
        else:
            out.append('후티의 항행 안전 주장은 단독으로 완화 신호로 인정하지 않음 — 실제 통항량·공격 여부 교차확인')
    if '사우디오만중재요청' in marks:
        out.append('사우디가 오만을 통해 Ansar Allah와의 중재·휴전 채널을 가동한다는 신호 — 군사 대응과 별개로 협상축이 열리는 단계')
    if '2주임시휴전안' in marks:
        out.append('2주 임시 휴전안 보도 — 정식 장기 휴전이 아니라 인도적·정치 협상을 위한 시간제한형 정전안으로 구분')
    if '인도적요구포괄협의' in marks:
        out.append('인도적 요구 전반을 협의 대상으로 묶는 신호 — 공항·항만·급여·봉쇄·민간 피해 등 실제 조건 공개 여부 추적')
    if '주말합의발표목표' in marks:
        out.append('이번 주말까지 합의 발표를 목표로 한다는 일정 신호 — 목표 시한과 실제 합의 발표를 구분해 추적')
    if '후티휴전수용' in marks:
        out.append('Ansar Allah 측 휴전 수용·동의 확인 — 제안 단계에서 양측 합의 단계로 상승')
    if '후티휴전거부' in marks:
        out.append('Ansar Allah 측 휴전 거부·조건 불충족 확인 — 협상 후퇴 및 사우디-후티 확전 재개 위험')
    if _diplomacy_marks(marks):
        if trusted:
            out.append('확정 수준: Reuters·AP·오만 외교부·사우디 국영통신·유엔·당사자 계열 원천 중 하나에서 확인된 보도')
        else:
            out.append('확정 수준: 중재안·기간·발표 목표는 공식 확인 전 보도 단계 — 확정 휴전으로 표시하지 않음')
    return out


def score_item(row, now):
    marks = _maritime_marks(row)
    if not marks:
        return _prev_score(row, now)

    row['houthi_maritime_marks'] = marks
    trusted = _trusted_diplomacy(row)
    sig = _signals(marks, trusted=trusted)
    if sig:
        row['signals_ko'] = list(dict.fromkeys(sig + list(row.get('signals_ko', []))))

    dmarks = _diplomacy_marks(marks)
    if dmarks:
        if '후티휴전거부' in marks:
            score = 100
            tags = ['예멘·후티', '협상후퇴', '확전위험']
        elif '후티휴전수용' in marks:
            score = 100
            tags = ['예멘·후티', '휴전', '양측확인']
        elif '2주임시휴전안' in marks or '주말합의발표목표' in marks:
            score = 96
            tags = ['예멘·후티', '휴전협상', '오만중재']
        elif '사우디오만중재요청' in marks:
            score = 93
            tags = ['예멘·후티', '중재', '오만']
        else:
            score = 90
            tags = ['예멘·후티', '인도협상']
        if trusted:
            score += 3
        age = watch.age_minutes(row, now)
        if age is not None and age <= 60:
            score += 1
        row['forced_tags'] = list(dict.fromkeys(list(row.get('forced_tags', [])) + tags))
        return min(score, 100), tags

    if _strong_red(marks):
        score = 48
        age = watch.age_minutes(row, now)
        if age is not None:
            if age <= 30: score += 8
            elif age <= 180: score += 5
            elif age <= 720: score += 2
        return score, ['확전', '해상병목']

    if marks == ['후티항행안전주장']:
        row['houthi_safe_claim_only'] = True
        return -200, []

    return _prev_score(row, now)

watch.score_item = score_item


def item_id(row):
    base_id = _prev_item_id(row)
    marks = _maritime_marks(row)
    diplomacy = _diplomacy_marks(marks)
    if diplomacy:
        # 같은 중재 단계가 여러 매체에서 반복돼도 단계별 1회만 알린다.
        key = 'saudi-oman-ansarallah-diplomacy-2026|' + '|'.join(sorted(diplomacy))
        return hashlib.sha256(key.encode()).hexdigest()[:20]
    stage = [m for m in marks if m in (
        '후티목하접근', '후티목하점령', '후티바브접근통제강화', '후티해상봉쇄', '후티선박공격',
    )]
    if not stage:
        return base_id
    return hashlib.sha256((base_id + '|houthi-maritime|' + '|'.join(stage)).encode()).hexdigest()[:20]

watch.item_id = item_id


def topic_label(row):
    marks = _maritime_marks(row)
    if _diplomacy_marks(marks):
        return '예멘·사우디·오만 · Ansar Allah 휴전중재'
    if marks:
        return '예멘·후티·바브엘만데브'
    return _prev_topic_label(row)

watch.topic_label = topic_label


def _color(row):
    marks = _maritime_marks(row)
    if '후티휴전거부' in marks or _strong_red(marks):
        return 'red'
    if '후티휴전수용' in marks:
        return 'green'
    if _diplomacy_marks(marks):
        # 중재 요청·휴전 제안·발표 목표는 아직 합의가 아니므로 초록으로 과장하지 않는다.
        return ''
    if marks == ['후티항행안전주장']:
        return ''
    return _prev_color(row)

recovery._color = _color
final_guard._final_color = _color
guard._enhanced_body_color = _color
guard.prev._strict_body_color = _color
guard.prev.core._body_color = _color


def _is_houthi_event(row):
    return bool(_maritime_marks(row))


def _verdict(items):
    diplomatic = [x for x in items if _diplomacy_marks(_maritime_marks(x))]
    maritime = [x for x in items if _is_houthi_event(x) and _strong_red(_maritime_marks(x)) and x not in diplomatic]
    others = [x for x in items if x not in diplomatic and x not in maritime]

    if diplomatic:
        marks = {m for x in diplomatic for m in _maritime_marks(x)}
        if '후티휴전거부' in marks:
            current = '🔴 Ansar Allah가 휴전안을 거부하거나 핵심 조건 미충족을 선언 — 협상 후퇴 단계'
        elif '후티휴전수용' in marks:
            current = '🟢 Ansar Allah의 휴전 수용 확인 — 중재 제안에서 양측 합의 단계로 상승'
        elif '2주임시휴전안' in marks or '주말합의발표목표' in marks:
            current = '🟡 2주 임시휴전·합의 발표 시한이 제시된 협상 진전 단계 — 아직 정식 합의·발효는 아님'
        else:
            current = '🟡 사우디가 오만을 통한 Ansar Allah 중재 채널을 가동하는 단계 — 휴전 합의 전'
        block = (
            '<b>투자 판정</b>\n'
            f'- <b>현재 판정:</b> {current}\n'
            '- <b>핵심:</b> 사우디-후티 군사충돌과 별개로 오만 중재축이 실제 열리는지 추적. 기간·인도적 조건·발표 시한은 공식 확인 전에는 미확정으로 표시\n'
            '- <b>시장:</b> 합의가 진전되면 바브엘만데브·Yanbu 경로의 해운·전쟁보험·원유 물류 위험프리미엄 완화 가능 / 결렬 시 반대\n'
            '- <b>다음:</b> 오만·사우디 공식 확인 → Ansar Allah 수용 여부 → 2주 휴전 발효 시각 → 인도적 조건 공개 → 이번 주말 실제 합의 발표'
        )
        if maritime:
            block += '\n- <b>병행 위험:</b> 협상 중에도 후티의 목하·바브엘만데브 군사 행동은 별도 🔴 확전 신호로 유지'
        return block

    if maritime and not others:
        marks = {m for x in maritime for m in _maritime_marks(x)}
        if '후티목하점령' in marks:
            stage = '목하 점령·바브엘만데브 접근 통제 강화 단계 — 국제항행 전면중단은 아직 미확인'
        elif '후티선박공격' in marks or '후티해상봉쇄' in marks:
            stage = '해상 봉쇄·선박 공격 단계 — 실제 통항량과 선별 표적 여부 확인 필요'
        else:
            stage = '바브엘만데브 접근 전선 확대 단계 — 목하·섬·연안 통제 변화 확인'
        return (
            '<b>투자 판정</b>\n'
            '- <b>핵심:</b> 후티의 항행 안전 발언보다 목하·바브엘만데브의 실제 영토 장악·봉쇄·선박 공격 행동을 우선 판정\n'
            f'- <b>현재 단계:</b> {stage}\n'
            '- <b>시장:</b> 홍해 운임·전쟁보험·유조선 위험프리미엄 상승 가능 / 사우디 Yanbu 우회수출 경로 병목 여부가 핵심\n'
            '- <b>다음:</b> 두바브·페림/마이윤·하니시 통제 → 실제 선박 공격 → 바브엘만데브 통항량 감소 → 해운사 우회운항 확대'
        )
    if maritime:
        return _prev_verdict(others) + '\n- <b>홍해 병목:</b> 후티의 목하·바브엘만데브 통제 확대는 별도 🔴 확전 신호로 병행 추적'
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
