#!/usr/bin/env python3
"""Render published balance changes without inferring a transfer or trade."""
import json
from pathlib import Path

alert_path = Path('out/kofia_liquidity_alert.html')
state_path = Path('out/kofia_liquidity_pending_state.json')
text = alert_path.read_text(encoding='utf-8')
state = json.loads(state_path.read_text(encoding='utf-8'))
v = state['values']

# Preserve the actual published comparison dates even for legacy input text.
ref = state['reference_dates']
def day_label(value):
    return f"{int(value[4:6])}/{int(value[6:8])}"
comparison = f"• 비교 기준: 1D {day_label(ref[1])} → {day_label(ref[0])} / 5D {day_label(ref[5])} → {day_label(ref[0])}"
if not any(line.startswith('• 비교 기준:') for line in text.splitlines()):
    text = text.replace('<b>무엇이 달라졌나</b>', comparison + '\n• 1D는 직전 공표일, 5D는 최근 5개 공표구간의 잔액 차이\n\n<b>무엇이 달라졌나</b>')

critical_dates = [state['dates'][k] for k in ('deposit','mmf','cma','credit')]
if state.get('alignment_ready') is not True or len(set(critical_dates)) != 1:
    raise RuntimeError(f"KOFIA critical-date quality gate failed before interpretation: {critical_dates}")
if state.get('snapshot_date') != critical_dates[0]:
    raise RuntimeError(
        f"KOFIA snapshot_date mismatch: snapshot={state.get('snapshot_date')} dates={critical_dates}"
    )

def jo(raw_million):
    return raw_million / 1_000_000

def fmt(raw_million):
    x = jo(raw_million)
    return f"{x:+.2f}조"

dep1, dep5 = v['deposit']['d1'], v['deposit']['d5']
mmf1, mmf5 = v['mmf']['d1'], v['mmf']['d5']
cma1, cma5 = v['cma']['d1'], v['cma']['d5']
cr1, cr5 = v['credit']['d1'], v['credit']['d5']

# 방향 판정용 최소 유의 변화. 단순 +/- 부호만으로 +0.01조를 '증가 추세'라고
# 과대해석하지 않는다: 최소 0.05조 또는 잔액의 0.05% 중 큰 값.
def mat(key):
    level = abs(v[key]['value'])
    return max(50_000, level * 0.0005)

def direction(change, key):
    threshold = mat(key)
    if abs(change) < threshold:
        return '보합'
    return '증가' if change > 0 else '감소'

def arrow(change, key):
    d = direction(change, key)
    return '↑' if d == '증가' else '↓' if d == '감소' else '≈'

# 1D 큰 변동 기준은 기존 경보 기준을 그대로 유지.
thresholds = [
    ('투자자예탁금', dep1, 2_000_000, '±2조'),
    ('MMF', mmf1, 3_000_000, '±3조'),
    ('CMA', cma1, 2_000_000, '±2조'),
    ('신용융자', cr1, 500_000, '±0.5조'),
]
triggered = [f"{name} {fmt(value)}(경보 기준 {label} 이상)" for name, value, threshold, label in thresholds if abs(value) >= threshold]
trigger_line = '• <b>큰 변동 항목</b>: ' + (' / '.join(triggered) if triggered else '1D 큰 변동 기준을 넘은 항목 없음')
trigger_line += ' (기준: 예탁금 ±2조 / MMF ±3조 / CMA ±2조 / 신용융자 ±0.5조)'

# 당일 자금 방향은 예탁금·MMF만 보지 않고 CMA와 신용융자까지 같이 읽는다.
cash_line = (
    f"• <b>자금 방향</b>: 예탁금 {fmt(dep1)}{arrow(dep1,'deposit')} · "
    f"MMF {fmt(mmf1)}{arrow(mmf1,'mmf')} · "
    f"CMA {fmt(cma1)}{arrow(cma1,'cma')} · "
    f"신용융자 {fmt(cr1)}{arrow(cr1,'credit')} → "
)
if direction(mmf1,'mmf') == '감소' and direction(dep1,'deposit') == '감소' and direction(cma1,'cma') == '증가':
    cash_line += (
        "MMF 설정원본이 감소했지만 투자자예탁금은 오히려 줄고 CMA는 늘었습니다. "
        "MMF 감소분의 이동 목적지는 이 잔액 통계로 확인되지 않습니다."
    )
elif direction(dep1,'deposit') == '증가' and direction(mmf1,'mmf') == '감소':
    cash_line += (
        "투자자예탁금은 늘고 MMF 설정원본은 줄었습니다. "
        "잔액 변화만으로 주식 순매수·신규 자금 유입·이동 목적지를 확인할 수 없습니다."
    )
elif direction(dep1,'deposit') == '감소' and direction(mmf1,'mmf') == '증가':
    cash_line += (
        "주식 매수 대기자금은 줄고 단기금융상품 주차자금은 늘어난 방향입니다. "
        "같은 돈의 직접 이동으로 단정하지 않습니다."
    )
else:
    cash_line += "네 항목의 방향이 완전히 정렬되지 않아 단일한 위험선호 신호로 보지 않습니다."

# 5개 공표구간은 '지속성'과 수급의 질을 함께 본다.
persistence_line = (
    f"• <b>지속성</b>: 5D 예탁금 {fmt(dep5)}{arrow(dep5,'deposit')} · "
    f"MMF {fmt(mmf5)}{arrow(mmf5,'mmf')} · "
    f"CMA {fmt(cma5)}{arrow(cma5,'cma')} · "
    f"신용융자 {fmt(cr5)}{arrow(cr5,'credit')} → "
)
def mmf_today_context(current_direction, five_day_direction):
    # Explicit 3x3 state matrix: never equate a flat five-day trend with
    # an increase or decrease merely because the daily sign is known.
    if current_direction == '증가':
        if five_day_direction == '증가':
            return "당일에도 MMF가 증가해 5개 공표구간 누적 증가 방향과 일치합니다."
        if five_day_direction == '감소':
            return "당일 MMF가 증가했으나 5개 공표구간 누적 감소 흐름과는 반대입니다."
        return "당일 MMF가 증가했지만 5개 공표구간 기준으로는 보합입니다."
    if current_direction == '감소':
        if five_day_direction == '증가':
            return "당일 MMF는 감소해 5개 공표구간 누적 증가 방향과 반대로 움직였습니다."
        if five_day_direction == '감소':
            return "당일 MMF도 감소해 5개 공표구간 누적 감소 방향과 일치합니다."
        return "당일 MMF는 감소했지만 5개 공표구간 기준으로는 보합입니다."
    return "당일 MMF는 유의미한 증감 없이 보합입니다."

# Guard all three possible daily outcomes before live message construction.
assert '당일에도 MMF가 증가' in mmf_today_context('증가','증가')
assert '당일 MMF는 감소' in mmf_today_context('감소','증가')
assert '보합' in mmf_today_context('보합','증가')

if direction(dep5,'deposit') == '감소' and direction(mmf5,'mmf') == '증가' and direction(cr5,'credit') == '증가':
    persistence_line += (
        "최근 5개 공표구간에는 투자자예탁금이 감소하고 MMF·신용융자는 늘었습니다. "
        + mmf_today_context(direction(mmf1,'mmf'), direction(mmf5,'mmf'))
    )
else:
    persistence_line += (
        "1D와 5D 방향을 함께 봐 일시 반전인지 지속 추세인지 구분합니다. "
        + mmf_today_context(direction(mmf1,'mmf'), direction(mmf5,'mmf'))
    )

cma_dir_1 = direction(cma1,'cma')
cma_dir_5 = direction(cma5,'cma')
if cma_dir_5 == '보합':
    cma_meaning = "5개 공표구간 기준 사실상 보합이라 추세 신호로 보지 않습니다."
elif cma_dir_1 == '보합':
    cma_meaning = f"당일 변화는 제한적이지만 최근 5개 공표구간에는 {cma_dir_5} 방향입니다."
elif cma_dir_1 == cma_dir_5:
    cma_meaning = f"단기와 5개 공표구간 모두 {cma_dir_5} 방향입니다."
else:
    cma_meaning = "단기와 5개 공표구간 방향이 엇갈려 추세가 뚜렷하지 않습니다."
cma_line = f"• <b>CMA</b>: 1D {fmt(cma1)}{arrow(cma1,'cma')} · 5D {fmt(cma5)}{arrow(cma5,'cma')} → {cma_meaning}"

cr_dir_5 = direction(cr5,'credit')
if cr_dir_5 == '증가':
    leverage_line = f"• <b>레버리지</b>: 신용융자 1D {fmt(cr1)}{arrow(cr1,'credit')} · 5D {fmt(cr5)}↑ → 최근 5개 공표구간 신용융자 잔액이 증가했습니다."
elif cr_dir_5 == '감소':
    leverage_line = f"• <b>레버리지</b>: 신용융자 1D {fmt(cr1)}{arrow(cr1,'credit')} · 5D {fmt(cr5)}↓ → 최근 5개 공표구간 신용융자 잔액이 감소했습니다."
else:
    leverage_line = f"• <b>레버리지</b>: 신용융자 1D {fmt(cr1)}{arrow(cr1,'credit')} · 5D {fmt(cr5)}≈ → 신용융자 잔액 변화는 제한적입니다."

# 종합은 당일의 '수급의 질'과 5D 추세를 분리해서 판정한다.
dep1_dir = direction(dep1,'deposit')
mmf1_dir = direction(mmf1,'mmf')
cma1_dir = direction(cma1,'cma')
cr1_dir = direction(cr1,'credit')
dep5_dir = direction(dep5,'deposit')
mmf5_dir = direction(mmf5,'mmf')
cr5_dir = direction(cr5,'credit')
mmf_flow_caution = (
    "다만 MMF 증가분이 주식에서 빠져나간 동일 자금이라고 단정하지 않습니다."
    if mmf5_dir == '증가' else
    "다만 MMF의 변화분을 주식시장 자금과 동일 자금의 직접 이동으로 단정하지 않습니다."
)

if dep1_dir == '증가' and cma1_dir == '증가' and mmf1_dir == '감소' and cr1_dir == '감소':
    summary_line = (
        f"• <b>종합</b>: <b>당일 현금성 잔액 개선 조합</b>으로 관찰합니다. "
        f"투자자예탁금 {fmt(dep1)}와 CMA {fmt(cma1)}가 늘고, MMF는 {fmt(mmf1)} 감소했으며 신용융자는 {fmt(cr1)} 감소했습니다. "
        "신용융자 외 차입과 실제 주식 매매자금은 이 통계로 확인되지 않습니다. "
        f"다만 5D 투자자예탁금은 아직 {fmt(dep5)}라 최근 5개 공표구간 전체 추세가 완전히 반전됐다고 보기는 이릅니다."
    )
elif dep5_dir == '감소' and cr5_dir == '증가':
    summary_line = (
        f"• <b>종합</b>: 5D 기준 투자자예탁금은 {fmt(dep5)}, 신용융자는 {fmt(cr5)} 변했습니다. "
        f"MMF는 {fmt(mmf5)}, CMA는 {fmt(cma5)}입니다. "
        "예탁금 감소와 신용융자 잔액 증가가 함께 관찰돼 신용거래 확대 부담을 점검할 조합입니다. 실제 주식 순매수·개별 투자자의 레버리지 비율은 별도 확인이 필요합니다. "
        + mmf_flow_caution
    )
elif dep5_dir == '증가' and cr5_dir != '증가':
    summary_line = (
        "• <b>종합</b>: 투자자예탁금은 늘고 신용융자 잔액 증가는 제한적인 현금성 잔액 개선 조합입니다."
    )
else:
    summary_line = (
        "• <b>종합</b>: 당일과 5개 공표구간의 방향이 아직 완전히 일치하지 않습니다. "
        "당일 현금성 매수여력 변화와 5D 예탁금 추세를 분리해 보고, 다음 공식값에서 같은 방향이 이어지는지 확인합니다."
    )

new_section = '\n'.join([
    '<b>현재 판정</b>',
    trigger_line,
    cash_line,
    persistence_line,
    cma_line,
    leverage_line,
    summary_line,
])

# Independent final output guard: direction claims must match the raw
# signed KOFIA values. Fail before Telegram rather than transmit nonsense.
mmf_day_dir = direction(mmf1, 'mmf')
mmf_five_dir = direction(mmf5, 'mmf')
assert mmf_today_context(mmf_day_dir, mmf_five_dir) in new_section, "MMF day-vs-five-day commentary missing"
if mmf_day_dir == '증가':
    forbidden = ('당일 MMF 급감', '당일 MMF 감소', '당일 MMF 유출', '당일 MMF는 감소')
elif mmf_day_dir == '감소':
    forbidden = ('당일 MMF 급증', '당일 MMF 증가', '당일 MMF 유입', '당일에도 MMF가 증가')
else:
    forbidden = ('당일 MMF 급감', '당일 MMF 급증')
conflicting = [term for term in forbidden if term in new_section]
if conflicting:
    raise RuntimeError(f"KOFIA directional text inconsistent with MMF 1D={fmt(mmf1)}: {conflicting}")

start_marker = '<b>현재 판정</b>'
end_marker = '<b>검증</b>'
start = text.index(start_marker)
end = text.index(end_marker, start)
text = text[:start] + new_section + '\n\n' + text[end:]

# 괄호 설명은 사용자가 요청한 MMF와 CMA에만 붙인다.
text = text.replace('MMF 설정원본 <b>', 'MMF 설정원본(단기금융상품에 투자하는 펀드의 투자원금 기준 규모) <b>')
text = text.replace('CMA 잔고 <b>', 'CMA 잔고(증권사 현금관리계좌에 머무는 단기자금) <b>')

alert_path.write_text(text, encoding='utf-8')
print('detailed_liquidity_interpretation_applied=true')
print(f"directional_narrative_guard=true mmf_1d={fmt(mmf1)} mmf_direction={mmf_day_dir} mmf_5d={fmt(mmf5)}")
print(trigger_line.replace('<b>', '').replace('</b>', ''))
print(summary_line.replace('<b>', '').replace('</b>', ''))
