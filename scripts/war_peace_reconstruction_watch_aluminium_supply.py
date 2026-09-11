#!/usr/bin/env python3
import argparse
import hashlib
import re

import war_peace_reconstruction_watch_houthi_maritime as prev

watch = prev.watch
runner = prev.runner
base = prev.base
guard = prev.guard

_prev_score = watch.score_item
_prev_item_id = watch.item_id
_prev_topic_label = watch.topic_label
_prev_verdict = guard._verdict

AL_QUERIES = [
    'site:media.ega.ae Al Taweelah aluminium restoration cells restart production 2026 when:3d',
    'site:albasmelter.com aluminium shutdown restart Lines 1 2 3 Hormuz 2026 when:7d',
    'site:reuters.com aluminium Middle East war EGA Alba Hormuz supply disruption price inventories premium when:2d',
    '(aluminium OR aluminum OR 알루미늄) (EGA OR Al Taweelah OR Alba OR Bahrain OR 걸프) (restart OR shutdown OR restoration OR force majeure OR 재가동 OR 감산 OR 복구 OR 공급차질) when:2d',
    '(LME aluminium OR LME aluminum OR LME 알루미늄) (inventory OR stocks OR premium OR high OR low OR 재고 OR 프리미엄 OR 신고가 OR 최저) when:2d',
]
watch.QUERIES = AL_QUERIES + list(watch.QUERIES)

AL_TERMS = ('aluminium','aluminum','알루미늄')
EGA_TERMS = ('ega','emirates global aluminium','emirates global aluminum','al taweelah','알 타윌라','알타윌라')
ALBA_TERMS = ('alba','aluminium bahrain','aluminum bahrain','바레인 알루미늄')
SUPPLY_TERMS = ('supply disruption','supply disruptions','shortage','production cut','shutdown','restart','restoration','force majeure','공급 차질','공급차질','감산','가동 중단','재가동','복구','강제불가항력')
PRICE_TERMS = ('lme','price','prices','premium','premiums','inventory','inventories','stocks','four-year high','record high','36-year low','가격','프리미엄','재고','신고가','최고가','최저')
REPRINT_TERMS = ('middle east conflict','middle east war','중동 분쟁','중동 전쟁')


def _text(row):
    return ' '.join([
        row.get('title_original',''), row.get('title_ko',''), row.get('description',''),
        row.get('article_text',''), ' '.join(row.get('signals_ko',[])),
    ]).lower()


def _has(t, terms):
    return any(k in t for k in terms)


def _percent(t):
    m = re.search(r'\b(\d{1,3})\s*%', t)
    if not m:
        return None
    try:
        v = int(m.group(1))
        return v if 0 <= v <= 100 else None
    except Exception:
        return None


def _al_marks(row):
    t = _text(row)
    if not _has(t, AL_TERMS):
        return []
    marks = []

    if _has(t, EGA_TERMS):
        if 'restarted' in t or 'restart' in t or '재가동' in t or 'restoration' in t or '복구' in t:
            p = _percent(t)
            if p is not None:
                marks.append(f'EGA재가동{p}')
            else:
                marks.append('EGA복구변화')
        if 'q1 2027' in t or '2027년 1분기' in t:
            marks.append('EGA정상화일정')
        if 'aed 1.5 billion' in t or '1.5 billion dirham' in t or '15억디르함' in t or '$400 million' in t:
            marks.append('EGA복구설비투자')

    if _has(t, ALBA_TERMS):
        if ('lines 1, 2 and 3' in t or 'lines 1 2 and 3' in t or '1·2·3' in t or '1, 2, 3라인' in t) and ('shutdown' in t or '정지' in t or '중단' in t):
            marks.append('Alba19감산')
        if ('restart' in t or 'restarted' in t or '재가동' in t) and ('line' in t or '라인' in t):
            marks.append('Alba재가동')

    if 'force majeure' in t or '강제불가항력' in t:
        marks.append('알루미늄강제불가항력')

    if _has(t, PRICE_TERMS) and _has(t, REPRINT_TERMS):
        if 'four-year high' in t or '4-year high' in t or '4년' in t and ('고점' in t or '최고' in t):
            marks.append('LME4년고점')
        if '36-year low' in t or '36년' in t and ('최저' in t or '저점' in t):
            marks.append('LME재고36년저점')
        if not marks:
            marks.append('중동알루미늄동일데이터재보도')

    if _has(t, SUPPLY_TERMS) and not marks:
        marks.append('알루미늄공급차질일반')
    return sorted(set(marks))


def _strong(marks):
    return any(
        m.startswith('EGA재가동') or m in (
            'EGA복구변화','EGA정상화일정','EGA복구설비투자','Alba19감산','Alba재가동',
            '알루미늄강제불가항력','LME4년고점','LME재고36년저점'
        ) for m in marks
    )


def _signals(marks):
    out = []
    ega = [m for m in marks if m.startswith('EGA재가동')]
    if ega:
        pct = ega[0].replace('EGA재가동','')
        out.append(f'EGA Al Taweelah 전해 셀 재가동률 {pct}% — 이전 단계 대비 실제 생산복구 진행 여부 확인')
    if 'EGA정상화일정' in marks:
        out.append('EGA 완전 생산 정상화 목표는 2027년 1분기 — 일정 앞당김·지연 여부가 가격 프리미엄 핵심')
    if 'EGA복구설비투자' in marks:
        out.append('EGA Al Taweelah 복구 설비투자 약 15억디르함(4억달러) — 2026~2027년 집행')
    if 'Alba19감산' in marks:
        out.append('Alba 1·2·3라인 통제 정지 — 총 생산능력의 19%가 영향')
    if 'Alba재가동' in marks:
        out.append('Alba 정지 라인 재가동 신호 — 걸프 공급부족 완화 여부 확인')
    if '알루미늄강제불가항력' in marks:
        out.append('알루미늄 공급망 강제불가항력 선언 — 계약·납기·현물 프리미엄 단계 상승')
    if 'LME4년고점' in marks:
        out.append('LME 알루미늄 4년 고점권 — 전쟁발 공급부족이 가격에 재반영되는지 확인')
    if 'LME재고36년저점' in marks:
        out.append('LME 알루미늄 재고 36년 저점권 — 물리적 재고 부족이 가격상승을 지지')
    if '중동알루미늄동일데이터재보도' in marks:
        out.append('SANA·Vietnam.vn 계열 동일 공급충격 재보도 — 신규 실물 변화가 없으면 중복 알림 제외')
    return out


def score_item(row, now):
    marks = _al_marks(row)
    if not marks:
        return _prev_score(row, now)

    row['aluminium_supply_marks'] = marks
    sig = _signals(marks)
    if sig:
        row['signals_ko'] = list(dict.fromkeys(sig + list(row.get('signals_ko', []))))

    # 동일 데이터 재보도·일반 가격 기사만으로 새 속보를 만들지 않는다.
    if marks == ['중동알루미늄동일데이터재보도'] or marks == ['알루미늄공급차질일반']:
        row['aluminium_rebroadcast_only'] = True
        return -180, []

    if _strong(marks):
        score = 42
        age = watch.age_minutes(row, now)
        if age is not None:
            if age <= 30: score += 8
            elif age <= 180: score += 5
            elif age <= 720: score += 2
        return score, ['시장파급','알루미늄공급']
    return _prev_score(row, now)

watch.score_item = score_item


def item_id(row):
    base_id = _prev_item_id(row)
    marks = _al_marks(row)
    stage = [m for m in marks if _strong([m])]
    if not stage:
        if marks and all(m in ('중동알루미늄동일데이터재보도','알루미늄공급차질일반') for m in marks):
            return hashlib.sha256(b'aluminium-middle-east-rebroadcast-bundle-2026').hexdigest()[:20]
        return base_id
    return hashlib.sha256((base_id + '|aluminium|' + '|'.join(stage)).encode()).hexdigest()[:20]

watch.item_id = item_id


def topic_label(row):
    if _al_marks(row):
        return '중동·알루미늄 공급망'
    return _prev_topic_label(row)

watch.topic_label = topic_label


def _is_aluminium(row):
    return bool(_al_marks(row))


def _verdict(items):
    al_items = [x for x in items if _is_aluminium(x) and _strong(_al_marks(x))]
    others = [x for x in items if x not in al_items]
    if al_items and not others:
        marks = {m for x in al_items for m in _al_marks(x)}
        easing = any(m.startswith('EGA재가동') or m == 'Alba재가동' for m in marks)
        if easing:
            core = '중동 알루미늄 공급망이 복구 단계로 이동 — 재가동 속도가 가격 프리미엄 완화의 핵심'
            nxt = 'EGA 재가동률 50%·75% → Alba 재가동 → 호르무즈 정상화 → LME 재고 반등'
        else:
            core = '중동 전쟁이 알루미늄 실물 공급을 제약 — 제련소 감산·물류·재고가 가격 상방의 핵심'
            nxt = '추가 감산·강제불가항력 → LME 가격·현물 프리미엄 → 재고 → 대체 공급 확대'
        return (
            '<b>투자 판정</b>\n'
            f'- <b>핵심:</b> {core}\n'
            '- <b>현재 단계:</b> 전쟁의 실물 원자재 공급파급 단계 — 기사 재보도보다 실제 가동률·재고·프리미엄 변화 우선\n'
            '- <b>시장:</b> 1차 제련사는 가격상승 수혜 가능 / 압연·압출·박 가공사는 원재료 판가 전가 속도가 마진 핵심\n'
            f'- <b>다음:</b> {nxt}'
        )
    if al_items:
        return _prev_verdict(others) + '\n- <b>알루미늄 공급망:</b> 중동 제련소 가동률·LME 재고·현물 프리미엄 변화를 별도 시장파급 축으로 추적'
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
