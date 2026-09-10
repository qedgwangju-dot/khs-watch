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

# 후티의 바브엘만데브 접근·목하 점령·해상봉쇄와 실제 통항을 별도 고신호로 추적.
MARITIME_QUERIES = [
    'site:reuters.com (Houthis OR Houthi) (Mokha OR Mocha OR Bab el-Mandeb OR Hanish OR Perim OR Mayyun OR Dhubab) (seized OR captured OR blockade OR shipping OR navigation) when:12h',
    'site:apnews.com (Houthis OR Houthi) (Mokha OR Mocha OR Bab el-Mandeb) (captured OR seized OR shipping OR blockade) when:12h',
    '(후티 OR Houthis) (목하 OR 모카 OR Mokha OR Mocha OR 바브엘만데브 OR Bab el-Mandeb) (점령 OR 장악 OR 진입 OR 봉쇄 OR 공격 OR 항행) when:12h',
    '(Houthis OR 후티) (Hanish OR 하니시 OR Perim OR 페림 OR Mayyun OR 마이윤 OR Dhubab OR 두바브) (advance OR seize OR capture OR 진격 OR 점령 OR 장악) when:12h',
    'site:maritime.dot.gov (Red Sea OR Bab el Mandeb) Houthi attacks commercial vessels 2026',
]
watch.QUERIES = MARITIME_QUERIES + list(watch.QUERIES)

HOUTHI_TERMS = ('houthi', 'houthis', 'ansarallah', '후티', '안사르알라')
MOKHA_TERMS = ('mokha', 'mocha', 'al-makha', 'al mokha', '목하', '모카')
BAB_TERMS = ('bab el-mandeb', 'bab al-mandab', 'bab el mandeb', 'bab al mandab', '바브엘만데브', '바브 알만데브')
ISLAND_APPROACH_TERMS = ('hanish', '하니시', 'perim', '페림', 'mayyun', '마이윤', 'dhubab', '두바브')
CAPTURE_TERMS = ('captured', 'seized', 'took control', 'entered the port', 'entered mokha', '점령', '장악', '함락', '진입')
ADVANCE_TERMS = ('advance', 'advanced', 'advancing', 'push toward', 'pushes toward', '진격', '접근', '밀고 내려', '남하')
BLOCKADE_TERMS = ('naval blockade', 'blockade', 'shipping blockade', '봉쇄', '해상 봉쇄', '항행 금지')
ATTACK_SHIPPING_TERMS = ('attack on shipping', 'attacks on shipping', 'attacked ship', 'attacked ships', 'attacked vessel', 'attacked vessels', 'targeted shipping', 'targeted vessels', '선박 공격', '상선 공격', '유조선 공격', '해운 공격')
SAFE_CLAIM_TERMS = ('freedom of navigation', 'navigation is safe', 'safe and uninterrupted', 'shipping is safe', 'international trade is safe', '항해의 자유', '항행은 안전', '항해는 안전', '안전하고 중단 없이', '국제 무역은 안전')
SAUDI_TARGET_TERMS = ('saudi ships', 'saudi shipping', 'saudi vessels', '사우디 선박', '사우디 해운')


def _text(row):
    return ' '.join([
        row.get('title_original', ''), row.get('title_ko', ''), row.get('description', ''),
        row.get('article_text', ''), ' '.join(row.get('signals_ko', [])),
    ]).lower()


def _has(t, terms):
    return any(k in t for k in terms)


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
    return sorted(set(marks))


def _strong_red(marks):
    return any(m in marks for m in (
        '후티목하접근', '후티목하점령', '후티바브접근통제강화', '후티해상봉쇄', '후티선박공격', '사우디선박선별위협',
    ))


def _signals(marks):
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
    return out


def score_item(row, now):
    marks = _maritime_marks(row)
    if not marks:
        return _prev_score(row, now)

    row['houthi_maritime_marks'] = marks
    sig = _signals(marks)
    if sig:
        row['signals_ko'] = list(dict.fromkeys(sig + list(row.get('signals_ko', []))))

    if _strong_red(marks):
        score = 48
        age = watch.age_minutes(row, now)
        if age is not None:
            if age <= 30: score += 8
            elif age <= 180: score += 5
            elif age <= 720: score += 2
        return score, ['확전', '해상병목']

    # '항행은 안전' 같은 단독 주장만으로는 휴전·완화 알림으로 승격하지 않는다.
    if marks == ['후티항행안전주장']:
        row['houthi_safe_claim_only'] = True
        return -200, []

    return _prev_score(row, now)

watch.score_item = score_item


def item_id(row):
    base_id = _prev_item_id(row)
    marks = _maritime_marks(row)
    stage = [m for m in marks if m in (
        '후티목하접근', '후티목하점령', '후티바브접근통제강화', '후티해상봉쇄', '후티선박공격',
    )]
    if not stage:
        return base_id
    return hashlib.sha256((base_id + '|houthi-maritime|' + '|'.join(stage)).encode()).hexdigest()[:20]

watch.item_id = item_id


def topic_label(row):
    if _maritime_marks(row):
        return '예멘·후티·바브엘만데브'
    return _prev_topic_label(row)

watch.topic_label = topic_label


def _color(row):
    marks = _maritime_marks(row)
    if _strong_red(marks):
        return 'red'
    # 안전 주장만으로 초록 금지. 기존 색상 함수가 다른 실제 사건을 확인한 경우에만 그 판정을 사용.
    if marks == ['후티항행안전주장']:
        return ''
    return _prev_color(row)

# 모든 개별 기사·최종 판정에서 동일한 최종 색상 함수를 사용.
recovery._color = _color
final_guard._final_color = _color
guard._enhanced_body_color = _color
guard.prev._strict_body_color = _color
guard.prev.core._body_color = _color


def _is_houthi_maritime(row):
    return bool(_maritime_marks(row))


def _verdict(items):
    maritime = [x for x in items if _is_houthi_maritime(x) and _strong_red(_maritime_marks(x))]
    others = [x for x in items if x not in maritime]
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
