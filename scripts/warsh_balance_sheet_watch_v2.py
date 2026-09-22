#!/usr/bin/env python3
import html
import warsh_balance_sheet_watch as base

def summary_message_v2(cur,impl,task,regime,four,reason):
    qt = 'QT' in (impl.get('mode') or '') or '총량 축소' in (impl.get('mode') or '')
    lines=[
        '<b>[Warsh 연준 대차대조표 변화]</b>',
        f"기준: H.4.1 {cur.get('date') or '확인 필요'} · 시행지침 {impl.get('date') or '확인 필요'}",
        '',
        '<b>한눈에 보기</b>',
        f"• <b>QT 판정</b>: {'총량축소형 QT 명시' if qt else '현재는 총량축소형 QT 아님'}",
        f"• <b>공식 정책</b>: {html.escape(impl['mode'])}",
        f"• <b>실제 자산 흐름</b>: {html.escape(regime)}",
        f"• <b>이번 변화</b>: {html.escape(reason)}",
        '',
        '<b>현재 숫자</b>',
        f"• 총자산 {base.usd_level(cur['total_assets'])} · 주간 {base.usd_week_change(cur['total_assets_weekly'])}",
        f"• 미 국채 {base.usd_level(cur['treasury'])} · 단기국채 {base.usd_level(cur['bills'])}",
        f"• 주택저당증권(MBS) {base.usd_level(cur['mbs'])}",
        f"• 은행 준비금 {base.usd_level(cur['reserves'])} · 주간 {base.usd_week_change(cur['reserves_weekly'])}",
    ]
    if four:
        lines.append(f"• 최근 4주: 총자산 {base.bn_change(four['total_assets'])} · 준비금 {base.bn_change(four['reserves'])} · 보유증권 {base.bn_change(four['securities'])}")

    lines += ['', '<b>쉽게 말하면</b>']
    if not qt and '충분한 준비금' in (impl.get('mode') or ''):
        lines += [
            '• 연준은 미 국채 원금을 계속 재투자하고, 기관채·주택저당증권 원금도 단기국채로 재투자합니다.',
            '• 필요하면 단기국채·잔존 3년 이하 국채를 더 사서 <b>준비금을 충분하게 유지</b>합니다.',
            '• 따라서 주택저당증권이 줄어든다는 이유만으로 “QT 재개”라고 부르지 않습니다. 현재는 <b>자산 구성 전환</b>에 가깝습니다.',
        ]
    else:
        lines += [
            '• 총량축소형 QT는 재투자 중단·상환한도·보유자산 축소 같은 공식 문구와 실제 총자산·보유증권·준비금 감소가 함께 확인돼야 합니다.',
        ]

    lines += [
        '',
        '<b>정확도 가드</b>',
        '• <b>MBS 감소 = QT</b>로 자동 판정하지 않습니다.',
        '• <b>총자산 1주 감소 = 구조적 QT</b>로도 판정하지 않습니다. 여러 주의 흐름을 같이 봅니다.',
        '• 대차대조표 태스크포스의 연구·권고는 FOMC가 채택하기 전까지는 정책이 아니라 <b>검토 단계</b>입니다.',
        '',
        '<b>다음 확인</b>',
        '• H.4.1에서 총자산·보유증권·준비금이 여러 주 동반 감소하는지',
        '• FOMC 시행지침에서 재투자 중단·상환한도·보유자산 축소 문구가 생기는지',
        '• Repo·준비금 시장에 유동성 부족 신호가 나타나는지',
        '',
        '<b>원천</b>',
        f"{base.link('연준 H.4.1',cur['url'])} · {base.link('FOMC 시행지침',impl['url'])} · {base.link('연준 대차대조표 태스크포스',task['url'])}",
    ]
    return '\n'.join(lines)

base.summary_message=summary_message_v2
if __name__=='__main__':
    base.main()
