#!/usr/bin/env python3
import argparse
import re

import war_peace_reconstruction_watch_axiosfeed as prev

watch = prev.watch
runner = prev.runner
base = prev.base

_prev_build_alert = watch.build_alert

# 알림 하단에 각 기능 모듈이 투자판정 문장을 계속 덧붙이면서 길어지는 문제를 막는다.
# 핵심 변화 본문은 그대로 두고, 협상 내용/투자 판정/반대 신호/다음 확인은 최종 단계에서
# 한 번만 다시 만들어 최대 3줄로 고정한다.
TAIL_MARKERS = (
    '<b>협상 내용</b>',
    '<b>투자 판정</b>',
    '<b>반대 신호</b>',
    '<b>다음 확인</b>',
)

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
    # 제목 아래 메타데이터에서 판정에 도움되지 않는 내부 태그만 제거한다.
    for token in LOW_VALUE_META:
        text = text.replace(f' · {token}', '')
    # 공백성 구분자가 중복되면 정리.
    text = re.sub(r'( · ){2,}', ' · ', text)
    return text


def _three_line_verdict(items):
    t = _all_text(items)

    winter = any(k in t for k in ('겨울긴장완화', 'winter de-escalation', '겨울철 긴장 완화', '에너지공격완화'))
    reciprocal = any(k in t for k in ('행동완화', '상호 자제', '모스크바 공격 중단', '키이우 공격 중단', '72시간 공습'))
    newideas = any(k in t for k in ('새종전아이디어', 'new ideas', '새 종전 아이디어', '새로운 아이디어'))
    escalation = any(k in t for k in ('확전', '공습 재개', '미사일', 'drone attack', 'missile'))
    reconstruction = any(k in t for k in ('재건', 'reconstruction', 'rebuild'))

    if winter:
        core = '겨울 완화는 아직 협의 단계 — 에너지 공격 자제·러시아 수용 여부가 핵심'
        nxt = '러시아 수용 → 적용 기간·범위 → 실제 공격 감소 확인'
    elif reciprocal:
        core = '양측 공습중단의 실제 이행 여부가 종전 신뢰도를 결정'
        nxt = '공습중단 이행 → 후속 회담 → 휴전 문안 확인'
    elif newideas:
        core = '미국의 새 종전안이 러·우 양측 수용 단계로 넘어가는지가 핵심'
        nxt = '후속·3자 회담 일정 → 합의 문안 공개 여부 확인'
    elif reconstruction:
        core = '재건 기대보다 재원 확정 → 입찰 → 본계약 전환이 실적 연결의 핵심'
        nxt = '재건 재원 → 사업목록 → 입찰·본계약 확인'
    else:
        core = '발언보다 실제 행동·합의 문안·후속 일정의 변화가 핵심'
        nxt = '공식 발표 → 실제 이행 → 다음 협상 일정 확인'

    if escalation:
        market = '완화 진전 시 유가·위험프리미엄↓ / 공습 재확대 시 즉시 되돌림'
    else:
        market = '완화 진전 시 유가·위험프리미엄↓ / 달러·금리 안정 시 위험선호↑'

    return (
        '<b>투자 판정</b>\n'
        f'- <b>핵심:</b> {core}\n'
        f'- <b>시장:</b> {market}\n'
        f'- <b>다음:</b> {nxt}'
    )


def final_build_alert(items, markets, now):
    text = _prev_build_alert(items, markets, now)
    text = _strip_old_tail(text)
    text = _compact_metadata(text)
    text = text.rstrip() + '\n\n' + _three_line_verdict(items)
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
