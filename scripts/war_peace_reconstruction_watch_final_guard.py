#!/usr/bin/env python3
import argparse
import re
import urllib.parse

import war_peace_reconstruction_watch_relevance_guard as prev
import war_peace_reconstruction_watch_bodycolor_strict as colorcore

watch = prev.watch
runner = prev.runner
base = prev.base
_prev_build_alert = watch.build_alert


def _norm_url(row):
    url = (row.get('resolved_url') or row.get('link') or '').strip()
    if not url:
        return ''
    try:
        p = urllib.parse.urlparse(url)
        host = p.netloc.lower().replace('www.', '')
        path = re.sub(r'/+$', '', p.path or '/')
        return f'{host}{path}'.lower()
    except Exception:
        return url.lower()


def _is_mixed_roundup(row):
    url = (row.get('resolved_url') or row.get('link') or '').lower()
    title = ' '.join([
        row.get('title_original',''), row.get('title_ko',''), row.get('description','')
    ]).lower()
    if '/podcasts/' in url:
        return True
    roundup_terms = (
        'morning bid', 'daily briefing', 'what you need to know', 'news roundup',
        'podcast', '팟캐스트', '뉴스 브리핑', '오늘의 주요 뉴스',
    )
    # 혼합형 브리핑은 전쟁 사건 하나가 아니라 여러 주제를 묶으므로 핵심 변화에서 제외한다.
    return any(k in title for k in roundup_terms)


def _dedupe_and_filter(items):
    out = []
    seen_urls = set()
    seen_titles = set()
    for row in items:
        if row.get('relevance_rejected'):
            continue
        if _is_mixed_roundup(row):
            row['final_rejected_reason'] = '혼합형 팟캐스트·뉴스요약'
            continue

        key_url = _norm_url(row)
        title = re.sub(r'\W+', ' ', (row.get('title_original') or row.get('title_ko') or '').lower()).strip()
        key_title = title[:220]

        # 같은 실제 URL은 번역문구가 달라도 한 사건으로 합친다.
        if key_url and key_url in seen_urls:
            continue
        if key_title and key_title in seen_titles:
            continue

        if key_url:
            seen_urls.add(key_url)
        if key_title:
            seen_titles.add(key_title)
        out.append(row)
    return out


def _strip_old_verdict(text):
    marker = '<b>투자 판정</b>'
    pos = text.find(marker)
    if pos != -1:
        return text[:pos].rstrip()
    return text.rstrip()


def _actual_colors(items):
    colors = []
    for row in items:
        try:
            c = colorcore._strict_body_color(row)
        except Exception:
            c = ''
        if c:
            colors.append(c)
    return colors


def _verdict(items):
    colors = _actual_colors(items)
    red = 'red' in colors
    green = 'green' in colors

    if red and not green:
        return (
            '<b>투자 판정</b>\n'
            '- <b>핵심:</b> 신규 변화의 중심은 실제 공격·확전\n'
            '- <b>현재 단계:</b> 군사행동·확전 지속 단계 — 휴전·협상 진전은 이번 변화에서 확인되지 않음\n'
            '- <b>시장:</b> 유가·해운·보험 위험프리미엄 상승 압력 / 위험자산 변동성 확대 가능\n'
            '- <b>다음:</b> 추가 공격·보복 → 피해 규모 → 실제 교전 강도 변화'
        )
    if green and not red:
        return (
            '<b>투자 판정</b>\n'
            '- <b>핵심:</b> 신규 변화의 중심은 휴전·종전·재건 진전\n'
            '- <b>현재 단계:</b> 협상·완화 진행 단계 — 공식 합의와 실제 이행 여부를 분리 확인\n'
            '- <b>시장:</b> 완화 진전 시 유가·전쟁 위험프리미엄 하락 가능\n'
            '- <b>다음:</b> 공식 합의문 → 실제 이행 → 후속 회담·재건 일정'
        )
    if red and green:
        return (
            '<b>투자 판정</b>\n'
            '- <b>핵심:</b> 공격·확전과 휴전·재건 신호가 동시에 존재\n'
            '- <b>현재 단계:</b> 혼재 단계 — 협상 발언보다 실제 교전 감소·합의 이행이 우선\n'
            '- <b>시장:</b> 완화 기대와 확전 위험이 충돌해 유가·위험자산 변동성 확대 가능\n'
            '- <b>다음:</b> 실제 교전 감소 여부 → 공식 합의 → 위반·보복 여부'
        )
    return (
        '<b>투자 판정</b>\n'
        '- <b>핵심:</b> 전쟁·휴전 방향을 확정할 실제 행동 변화는 확인되지 않음\n'
        '- <b>현재 단계:</b> 방향성 미확인 — 정책·해설·시장기사와 실제 사건을 분리\n'
        '- <b>시장:</b> 별도 군사·휴전 행동 확인 전 방향성 판정 보류\n'
        '- <b>다음:</b> 공식 행동·합의·공격 발생 여부 재확인'
    )


def build_alert(items, markets, now):
    filtered = _dedupe_and_filter(items)
    if not filtered:
        return ''

    text = _prev_build_alert(filtered, markets, now)
    text = _strip_old_verdict(text)
    text = text.rstrip() + '\n\n' + _verdict(filtered)
    return text.strip()[:4000] + '\n'


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
