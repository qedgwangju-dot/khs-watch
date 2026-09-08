#!/usr/bin/env python3
import argparse
import hashlib
import re

import war_peace_reconstruction_watch_counterstrike as prev

watch = prev.watch
runner = prev.runner
base = prev.base

QUERIES = [
    'site:reuters.com Ukraine overnight missiles drones Air Force Kyiv September 8 2026 when:6h',
    '(Ukraine OR 우크라이나) (overnight attack OR 야간 공격) (missiles OR 미사일) (drones OR 드론) (Air Force OR 공군) when:6h',
    'site:reuters.com Saudi energy ministry southern region energy facilities utilities Houthis September 8 2026 when:6h',
    'site:spa.gov.sa energy facilities utilities southern region targeted Houthis September 8 2026 when:6h',
    '(Saudi OR 사우디) (energy facilities OR energy infrastructure OR 에너지 시설) (Houthis OR Houthi OR 후티) when:6h',
    '(Saudi Energy Ministry OR 사우디 에너지부 OR وزارة الطاقة) (fires OR حرائق OR 화재) (temporary suspension OR توقف مؤقت OR 일시 중단) when:6h',
    '(Aramco OR 아람코) (Jazan OR Jizan OR 자잔 OR 지잔) (hit OR struck OR attack OR 피격 OR 공격) when:12h',
    '(Brent OR 브렌트) (98 OR "$98" OR 98달러) (Saudi OR Houthis OR 사우디 OR 후티) when:6h',
]
watch.QUERIES = QUERIES + list(watch.QUERIES)

_prev_google_news = watch.google_news
_prev_score = watch.score_item
_prev_item_id = watch.item_id
_prev_build_alert = watch.build_alert

ATTACK_COLOR_WORDS = (
    '공격', '공습', '폭격', '포격', '피격', '미사일', '드론', '무인기', '확전',
    'attack', 'airstrike', 'air strike', 'bombard', 'shelling', 'struck', 'missile', 'drone',
)
ACTIVE_ATTACK_PHRASES = (
    '공격 지속', '공격 재개', '공습 지속', '공습 재개', '미사일 공격', '드론 공격', '무인기 공격',
    '폭격 지속', '포격 지속', '피격', '공격받', '공격을 받',
    'attack continues', 'attacks continue', 'attack resumed', 'attacks resumed', 'missile attack',
    'drone attack', 'airstrike', 'air strike', 'shelling', 'struck', 'was hit', 'were hit',
)
GREEN_COLOR_WORDS = (
    '재건', '복구', '휴전', '정전', '종전', '평화', '평화합의', '평화 합의', '평화협정', '평화 협정',
    '협상', '회담', '긴장 완화', '완화 조치', '공격 자제', '공격 중단', '공습 중단', '상호 공격 자제',
    'ceasefire', 'truce', 'reconstruction', 'rebuild', 'rebuilding', 'peace agreement', 'peace deal',
    'peace talks', 'negotiations', 'trilateral talks', 'de-escalation', 'deescalation',
)
DEESCALATION_PHRASES = (
    '공격 자제', '공격 중단', '공습 중단', '공격을 자제', '공격을 중단', '상호 공격 자제',
    '긴장 완화', '완화 조치', '단계적 완화', '교전 중단', '적대행위 중단',
    'halt attacks', 'halted attacks', 'stop attacks', 'stopping attacks', 'pause attacks',
    'restraint on attacks', 'de-escalation', 'deescalation',
)
ACTIVE_ATTACK_MARKS = {
    '러시아대규모복합공격', '사우디에너지공격', '화재확인', '운영일시중단',
    '자잔FT미확정', '자잔확인필요',
}


def _text(row):
    return ' '.join([
        row.get('title_ko',''), row.get('title_original',''), row.get('description',''),
        ' '.join(row.get('signals_ko',[])), ' '.join(row.get('forced_tags',[])),
    ]).lower()


def _event_color(row):
    """실제 공격은 빨강, 휴전·종전·재건·공격중단은 초록으로 분류한다."""
    t = _text(row)
    active_marks = set(row.get('barrage_energy_marks', [])) & ACTIVE_ATTACK_MARKS
    if active_marks:
        return 'red'

    # '공격 중단/자제'처럼 공격이라는 단어가 들어가도 의미는 완화이므로 초록 우선.
    if any(k in t for k in DEESCALATION_PHRASES):
        return 'green'

    # 실제 공격의 발생·지속·재개를 명시한 경우에는 평화협상 문맥이 함께 있어도 빨강.
    if any(k in t for k in ACTIVE_ATTACK_PHRASES):
        return 'red'

    # 협상·휴전·종전·재건 신호는 초록.
    if any(k in t for k in GREEN_COLOR_WORDS):
        return 'green'

    # 마지막으로 일반 공격 키워드만 남은 경우 빨강.
    if any(k in t for k in ATTACK_COLOR_WORDS):
        return 'red'
    return ''


def _prefix_item_markers(text, items):
    """최종 제목이 중간 래퍼에서 바뀌어도 기사 번호를 기준으로 🔴/🟢를 강제 부착한다."""
    lines = text.splitlines()
    for idx, row in enumerate(items[:8], 1):
        color = _event_color(row)
        if not color:
            continue
        marker = '🔴' if color == 'red' else '🟢'
        # 최종 출력은 보통 '[속보] <b>1. ...</b>' 또는 '[후속] <b>1. ...</b>' 형태다.
        patterns = (
            re.compile(rf'<b>{idx}\.\s'),
            re.compile(rf'^\[[^\]]+\]\s*(?:<b>)?{idx}\.\s'),
            re.compile(rf'^(?:🟥|🟧|🟨)?\s*(?:<b>)?{idx}\.\s'),
        )
        for j, line in enumerate(lines):
            if any(p.search(line) for p in patterns):
                if not line.lstrip().startswith(('🔴', '🟢')):
                    lines[j] = f'{marker} {line}'
                break
    return '\n'.join(lines)


def _apply_color_markers(text, items):
    """Telegram 일반 메시지는 글자색을 지정할 수 없어 🔴/🟢 아이콘으로 분류한다."""
    classes = {_event_color(x) for x in items}
    classes.discard('')
    if not classes:
        return text

    badges = []
    if 'red' in classes:
        badges.append('🔴 <b>공격·확전</b>')
    if 'green' in classes:
        badges.append('🟢 <b>재건·휴전</b>')
    badge_line = '  |  '.join(badges)

    # 제목 바로 아래에는 이번 알림에 실제 포함된 분류만 표시한다.
    lines = text.splitlines()
    if lines:
        lines.insert(1, badge_line)
        text = '\n'.join(lines)
    else:
        text = badge_line

    # 제목 문자열 치환 대신 기사 번호 기준으로 개별 마커를 강제 부착한다.
    return _prefix_item_markers(text, items)


def _signals(row):
    t = _text(row)
    signals, marks = [], []

    ukr = any(k in t for k in ('ukraine','ukrainian','우크라이나'))
    russia = any(k in t for k in ('russia','russian','러시아'))
    missile = any(k in t for k in ('missile','미사일'))
    drone = any(k in t for k in ('drone','uav','드론','무인기'))
    overnight = any(k in t for k in ('overnight','night attack','야간','밤사이','밤새'))
    airforce = any(k in t for k in ('air force','공군'))
    if ukr and russia and missile and drone and (overnight or airforce):
        signals.append('러시아의 대규모 미사일·드론 복합 공격 — 종전 협상과 별개로 군사 압박 지속')
        marks.append('러시아대규모복합공격')
        if '166' in t:
            signals.append('드론 166기 수치는 우크라이나 공군 원문과 최신 보도 교차확인 후 확정 표기')
            marks.append('166검증필요')

    saudi = any(k in t for k in ('saudi','사우디','السعودية'))
    energy = any(k in t for k in ('energy facilit','energy infrastructure','oil facilit','에너지 시설','에너지 인프라','석유 시설','منشآت','مرافق قطاع الطاقة'))
    houthi = any(k in t for k in ('houthi','houthis','후티','الحوث'))
    south = any(k in t for k in ('southern region','jazan','jizan','abha','khamis mushait','najran','남부지역','남부 지역','지잔','자잔','아브하','나지란','المنطقة الجنوبية'))
    ministry = any(k in t for k in ('saudi energy ministry','ministry of energy','사우디 에너지부','وزارة الطاقة'))
    fires = any(k in t for k in ('fires','fire','화재','حرائق'))
    tempstop = any(k in t for k in ('temporary suspension','temporarily suspended','temporary halt','operational suspension','일시 중단','가동 중단','توقف مؤقت'))
    injured73 = '73' in t and any(k in t for k in ('injured','wounded','부상','مصاب'))

    if saudi and energy and south and (houthi or ministry):
        signals.append('사우디 남부 에너지 시설 피격 확인 — 공급 차질 여부가 유가 핵심')
        marks.append('사우디에너지공격')
        if ministry:
            marks.append('에너지부확인')
        if fires:
            signals.append('사우디 에너지부: 복수 현장 화재 발생')
            marks.append('화재확인')
        if tempstop:
            signals.append('사우디 에너지부: 일부 운영 일시 중단 확인')
            marks.append('운영일시중단')
        if injured73:
            signals.append('사우디 주도 연합군: 최소 73명 부상')
            marks.append('73명부상')

    aramco = any(k in t for k in ('aramco','아람코'))
    jazan = any(k in t for k in ('jazan','jizan','자잔','지잔'))
    ft = any(k in t for k in ('financial times','ft ','파이낸셜타임스'))
    unverified = any(k in t for k in ('not immediately able to verify','could not verify','unable to verify','not independently verified','검증하지 못','독립 확인되지'))
    no_comment = any(k in t for k in ('has not commented','no comment','not commented','논평하지','공식 논평'))
    if aramco and jazan and any(k in t for k in ('hit','struck','attack','피격','공격')):
        if ft or unverified or no_comment:
            signals.append('아람코 자잔 석유시설 피격은 FT 보도 단계 — Reuters 독립 확인·아람코 공식 논평 전까지 미확정')
            marks.append('자잔FT미확정')
        else:
            signals.append('아람코 자잔 석유시설 피격 여부 후속 공식 확인 필요')
            marks.append('자잔확인필요')

    brent = any(k in t for k in ('brent','브렌트'))
    if brent and saudi and houthi and ('98' in t or '$98' in t or '98달러' in t):
        signals.append('브렌트유 약 98달러까지 상승 — 사우디 에너지 시설 공격 위험프리미엄 반영')
        marks.append('브렌트98')

    return list(dict.fromkeys(signals)), sorted(set(marks))


def google_news(query):
    rows, err = _prev_google_news(query)
    for row in rows:
        sig, marks = _signals(row)
        if marks:
            row['signals_ko'] = list(dict.fromkeys(sig + list(row.get('signals_ko',[]))))
            row['barrage_energy_marks'] = marks
            row['forced_tags'] = list(dict.fromkeys(list(row.get('forced_tags',[])) + ['확전','에너지위험']))
            row['deep_signal'] = True
    return rows, err

watch.google_news = google_news


def score_item(x, now):
    score, tags = _prev_score(x, now)
    sig, marks = _signals(x)
    if marks:
        if '사우디에너지공격' in marks:
            score += 48
        if '에너지부확인' in marks:
            score += 12
        if '운영일시중단' in marks:
            score += 10
        if '73명부상' in marks:
            score += 8
        if '러시아대규모복합공격' in marks:
            score += 42
        if '브렌트98' in marks:
            score += 24
        if '자잔FT미확정' in marks:
            score += 8
        src = (x.get('source') or '').lower()
        if any(k in src for k in ('reuters','saudi press agency','spa','ukrainian air force','associated press','ap news')):
            score += 10
        tags = sorted(set(tags + ['확전','에너지위험']))
        x['barrage_energy_marks'] = marks
        if sig:
            x['signals_ko'] = list(dict.fromkeys(sig + list(x.get('signals_ko',[]))))
    return score, tags

watch.score_item = score_item


def item_id(x):
    base_id = _prev_item_id(x)
    _, marks = _signals(x)
    if not marks:
        return base_id
    # 공식확인/운영중단/실명시설 확인 단계가 바뀌면 후속 알림
    important = [m for m in marks if m in ('사우디에너지공격','에너지부확인','화재확인','운영일시중단','73명부상','자잔FT미확정','자잔확인필요','브렌트98','러시아대규모복합공격')]
    return hashlib.sha256((base_id+'|barrage-energy|'+'|'.join(important)).encode()).hexdigest()[:20]

watch.item_id = item_id


def build_alert(items, markets, now):
    text = _prev_build_alert(items, markets, now)
    marks = set()
    for x in items:
        _, m = _signals(x); marks.update(m)
    if marks:
        marker = '<b>투자 판정</b>\n'
        pos = text.find(marker)
        if pos != -1:
            head = text[:pos].rstrip()
            if '사우디에너지공격' in marks:
                status = []
                if '운영일시중단' in marks:
                    status.append('일부 운영 일시중단 확인')
                if '73명부상' in marks:
                    status.append('73명 부상')
                if '자잔FT미확정' in marks:
                    status.append('아람코 자잔 실명은 아직 FT 보도 단계')
                core_suffix = ' / '.join(status) if status else '피해 규모 평가 중'
                core = f'사우디 남부 에너지시설 피격 확인 — {core_suffix}'
                market = '브렌트 98달러 부근 위험프리미엄 반영 / 실제 생산·수송 감소 확인 시 추가 상승 압력'
                nxt = '피격 시설 실명 → 가동중단 시간·처리량 감소 → 아람코 공식 확인·사우디 보복 확인'
            elif '러시아대규모복합공격' in marks:
                core = '3자회담 조율과 별개로 대규모 미사일·드론 공격 지속 — 군사적 완화는 아직 미확인'
                market = '방공 소모·민간 피해 확대는 종전 기대를 제약하고 유럽 방산 수요를 지지'
                nxt = '공식 발사·격추 수치 → 피해 규모 → 러·우 후속 보복과 협상 영향 확인'
            else:
                core = '에너지·군사 확전 신호가 종전 기대와 동시에 진행 중'
                market = '유가·위험프리미엄 상승 여부와 위험자산 되돌림 확인'
                nxt = '공식 피해·가동 차질·후속 공격 확인'
            tail = (
                '<b>투자 판정</b>\n'
                f'- <b>핵심:</b> {core}\n'
                f'- <b>시장:</b> {market}\n'
                f'- <b>다음:</b> {nxt}'
            )
            text = (head+'\n\n'+tail).strip()

    text = _apply_color_markers(text, items)
    return text.strip()[:4000]+'\n'

watch.build_alert = build_alert


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
