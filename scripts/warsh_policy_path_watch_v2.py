#!/usr/bin/env python3
import html
import warsh_policy_path_watch as base

def message_v2(snap, cls):
    sep=cls.get('sep'); bal=cls.get('balance')
    extra=float(cls.get('extra_bp') or 0.0)
    eq=extra/25.0
    lines=[
        '<b>[Warsh 금리경로 종합]</b>',
        '',
        '<b>한눈에 보기</b>',
        f"• <b>시장 판정</b>: {html.escape(cls['verdict'])}",
        f"• <b>현재 공식 기준</b>: {cls['baseline_rate']:.3f}% ({html.escape(cls['baseline_kind'])})",
        f"• <b>연말 시장 기대</b>: {cls['yearend_market_rate']:.3f}% → 현재보다 {extra:+.1f}bp",
        f"  ↳ +25bp 인상 {eq:.2f}회 상당의 <b>확률가중 평균</b>",
    ]
    if sep:
        lines += [
            f"• <b>연준 점도표</b>: 2026년 말 {sep['yearend']:.3f}% · 2027년 말 {sep['nextyear']:.3f}%",
            f"• <b>시장-점도표 차이</b>: {cls['market_sep_gap_bp']:+.1f}bp → {html.escape(cls['sep_read'])}",
        ]
    if bal:
        lines += [f"• <b>대차대조표</b>: {html.escape(cls['tightening_mix'])}"]

    lines += ['', '<b>쉽게 말하면</b>']
    if extra < 6.25:
        lines.append('• 시장은 현재 인상 이후 추가 인상을 거의 가격에 넣지 않고 있습니다.')
    elif extra < 31.25:
        lines.append('• 시장은 현재 인상 이후 <b>추가 1회 인상 가능성</b>을 가격에 넣고 있습니다.')
    else:
        lines.append('• 시장은 <b>추가 1회를 상당 부분 반영</b>하고 있으며, 두 번째 추가 인상 가능성도 일부 가격에 넣고 있습니다.')
    if sep:
        sep_extra=float(cls.get('sep_extra_bp') or 0.0)
        lines.append(f"• 연준 점도표는 현재 공식 기준보다 연말 금리를 약 {sep_extra:+.1f}bp 높게 봅니다. 이는 대략 +25bp 1회에 가까운 공식 중앙경로입니다.")
        lines.append('• 점도표는 약속이 아니라 참가자 전망의 중앙값입니다. 시장선물과 반드시 같아야 하는 값이 아닙니다.')
    if bal:
        if '충분한 준비금' in (bal.get('mode') or ''):
            lines.append('• 현재 공식 조합은 <b>정책금리 긴축 + 충분한 준비금 유지</b>입니다. “금리 대신 QT”로 읽지 않습니다.')
        else:
            lines.append('• 대차대조표가 실제 총량축소형 QT로 바뀌었는지는 시행지침과 H.4.1을 따로 확인합니다.')

    lines += ['', '<b>회의별 시장 경로</b>']
    for m in snap['meetings'][:4]:
        p=float(m['hike25_prob']); ch=float(m.get('change_bp') or 0.0)
        lines.append(
            f"• {base.ko_date(m['date'])} | +25bp 인상 확률 {p:.0f}% | "
            f"확률가중 기대 {ch:+.1f}bp | 회의 후 금리 {m['post_rate']:.3f}%"
        )

    lines += [
        '',
        '<b>숫자 읽는 법</b>',
        '• <b>확률 %</b>와 <b>금리변화 bp</b>는 다른 숫자입니다.',
        '• 예: +25bp 인상 확률 80% → 확률가중 기대폭은 약 +20bp입니다. “80% = 80bp”가 아닙니다.',
        '• 1bp = 0.01%포인트입니다.',
        '',
        '<b>다음 확인</b>',
        '• 다음 회의뿐 아니라 12월·2027년 경로가 함께 더 올라가는지',
        '• 2년물이 추가긴축 기대를 유지하는지',
        '• 연준 점도표와 시장의 괴리가 10bp 이상 더 벌어지는지',
        '• 대차대조표가 충분한 준비금 유지에서 실제 총량축소형 QT로 바뀌는지',
        '',
        '<b>원천</b>',
    ]
    src=[base.link('연방기금금리 선물 기반 경로',snap['url']),base.link('CME FedWatch 방법론',base.CME_URL),base.link('연준 FOMC 일정',base.FED_CALENDAR)]
    if sep and sep.get('url'): src.append(base.link('연준 경제전망·점도표',sep['url']))
    if bal and bal.get('url'): src.append(base.link('연준 FOMC 시행지침',bal['url']))
    if bal and bal.get('h41_url'): src.append(base.link('연준 H.4.1',bal['h41_url']))
    lines.append(' · '.join(src))
    return '\n'.join(lines)

base.message=message_v2
if __name__=='__main__':
    base.main()
