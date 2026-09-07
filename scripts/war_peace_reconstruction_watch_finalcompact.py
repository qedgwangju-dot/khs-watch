#!/usr/bin/env python3
import argparse
import re

import war_peace_reconstruction_watch_axiosfeed as prev

watch = prev.watch
runner = prev.runner
base = prev.base

_prev_build_alert = watch.build_alert

# 원칙: 내용을 무조건 줄이지 않는다.
# 같은 사건의 핵심 사실은 본문에 유지하고, 하단 해석만 중복을 제거해
# '핵심 → 현재 단계 → 시장 → 다음' 순서로 한 번만 보여준다.
TAIL_MARKERS = (
    '<b>협상 내용</b>',
    '<b>투자 판정</b>',
    '<b>반대 신호</b>',
    '<b>다음 확인</b>',
)

# 사용자에게 의미가 약한 내부 분류 태그만 숨긴다. 사건 자체의 의미 태그는 유지한다.
LOW_VALUE_META = (
    '본문형 신호', '시간표', '일정구체화', '유럽참여', '정치일정',
    '행동확인', '협상내용',
)


def _all_text(items):
    parts = []
    for x in items:
        parts.extend([
            x.get('title_ko', ''), x.get('title_original', ''), x.get('description', ''),
            ' '.join(x.get('signals_ko', [])), ' '.join(x.get('forced_tags', [])),
            ' '.join(x.get('tags', [])),
        ])
    return ' '.join(parts).lower()


def _strip_old_tail(text):
    positions = [text.find(m) for m in TAIL_MARKERS if text.find(m) != -1]
    if positions:
        text = text[:min(positions)].rstrip()
    return text


def _compact_metadata(text):
    for token in LOW_VALUE_META:
        text = text.replace(f' · {token}', '')
    text = re.sub(r'( · ){2,}', ' · ', text)
    return text


def _readable_verdict(items):
    t = _all_text(items)

    winter = any(k in t for k in ('겨울긴장완화', 'winter de-escalation', '겨울철 긴장 완화', '에너지공격완화'))
    reciprocal = any(k in t for k in ('행동완화', '상호 자제', '모스크바 공격 중단', '키이우 공격 중단', '72시간 공습'))
    newideas = any(k in t for k in ('새종전아이디어', 'new ideas', '새 종전 아이디어', '새로운 아이디어'))
    allies = any(k in t for k in ('영프독참여', '유럽참여', '영국·프랑스·독일', 'national security advisers'))
    escalation = any(k in t for k in ('확전', '공습 재개', '미사일', 'drone attack', 'missile', '병력 증강'))
    reconstruction = any(k in t for k in ('재건', 'reconstruction', 'rebuild'))

    # 핵심은 서로 다른 정보가 실제로 함께 있을 때만 한 줄 안에서 묶어 보여준다.
    core_parts = []
    if winter:
        core_parts.append('미국이 겨울철 긴장 완화·에너지 공격 자제 방안을 모색')
    if newideas:
        core_parts.append('모스크바 협의의 새 종전 아이디어를 키이우에 전달')
    if reciprocal:
        core_parts.append('양측 수도 공격 자제·공습중단의 실제 이행이 중요')
    if allies:
        core_parts.append('영·프·독도 협상 구조에 참여')
    if reconstruction and not core_parts:
        core_parts.append('재건 기대보다 재원·사업목록·입찰 확정이 중요')
    if not core_parts:
        core_parts.append('발언보다 실제 행동·합의 문안·후속 일정 변화가 중요')

    # 너무 긴 나열이 되지 않게 핵심은 최대 2개 문장으로 묶되, 나머지 사실은 본문에 남아 있다.
    core = ' / '.join(core_parts[:2])

    if winter:
        stage = '탐색·협의 단계 — 러시아 수용, 적용 범위·기간은 아직 확인 필요'
        nxt = '러시아 수용 여부 → 적용 범위·기간 → 실제 공격 감소·위반 여부'
    elif reciprocal:
        stage = '행동 완화 단계 — 공습중단이 실제로 지켜지는지 확인 필요'
        nxt = '공습중단 이행 → 후속 회담 → 휴전 문안'
    elif newideas:
        stage = '새 제안 전달 단계 — 양측 수용·공식 합의는 아직 별개'
        nxt = '후속·3자 회담 일정 → 합의 문안 공개'
    elif reconstruction:
        stage = '재건 기대 단계 — 재원·입찰·본계약 전까지 매출 확정 아님'
        nxt = '재건 재원 → 사업목록 → 입찰 → 본계약'
    else:
        stage = '협상 진행 단계 — 공식 합의와 실제 이행 여부를 분리 확인'
        nxt = '공식 발표 → 실제 이행 → 다음 협상 일정'

    if escalation:
        market = '완화 진전 시 유가·위험프리미엄↓ / 공습·미사일 재확대 시 되돌림'
    else:
        market = '완화 진전 시 유가·위험프리미엄↓ / 달러·금리 안정 동반 시 위험선호↑'

    return (
        '<b>투자 판정</b>\n'
        f'- <b>핵심:</b> {core}\n'
        f'- <b>현재 단계:</b> {stage}\n'
        f'- <b>시장:</b> {market}\n'
        f'- <b>다음:</b> {nxt}'
    )


def final_build_alert(items, markets, now):
    text = _prev_build_alert(items, markets, now)
    text = _strip_old_tail(text)
    text = _compact_metadata(text)
    text = text.rstrip() + '\n\n' + _readable_verdict(items)
    return text.strip()[:4000] + '\n'


watch.build_alert = final_build_alert


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--finalize', action='store_true')
    ap.add_argument('--telegram-test', action='store_true')
    args = ap.parse_args()
    if args.finalize:
        watch.finalize()
        return
    if args.telegram_test:
        base._write_inline_test()
    else:
        watch.run(test=False)
    runner.verify_alert(test_mode=False)


if __name__ == '__main__':
    main()
