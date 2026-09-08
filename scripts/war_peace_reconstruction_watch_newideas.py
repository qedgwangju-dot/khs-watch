#!/usr/bin/env python3
import argparse
import hashlib

import war_peace_reconstruction_watch_allies as prev

watch = prev.watch
runner = prev.runner
base = prev.base

NEW_IDEA_QUERIES = [
    'site:reuters.com Zelenskiy ("decent ideas" OR "worthwhile ideas") (Witkoff OR Kushner OR "US envoys") "peace talks" when:24h',
    'site:reuters.com Witkoff Kushner Zelenskiy Kyiv ("new ideas" OR "new proposal" OR "new trilateral talks" OR "encouraged" OR "decent ideas" OR "worthwhile ideas") when:24h',
    'site:reuters.com (Kremlin OR Peskov) ("does not rule out" OR "not rule out" OR restart OR resume) (trilateral OR "peace talks") Ukraine US when:48h',
    'site:fnnews.com (크렘린궁 OR 페스코프) (3자협상 OR 3자 협상 OR 3자회담 OR 3자 회담) (재개 OR 가능성 OR "배제 안해") when:48h',
    '(Kremlin OR Peskov OR 크렘린궁 OR 페스코프) ("restart peace talks" OR "resume peace talks" OR "trilateral talks" OR 3자협상 OR 3자 회담) (Ukraine OR 우크라이나) when:48h',
    '(Zelenskiy OR Zelensky OR 젤렌스키) ("resume negotiations" OR "resume peace talks" OR "ready for talks" OR "willing to resume" OR 협상 재개 OR 종전 협상 재개) when:48h',
    '(Zelenskiy OR Zelensky OR 젤렌스키) ("decent ideas" OR "worthwhile ideas" OR 합리적인 제안 OR 괜찮은 아이디어) (Witkoff OR Kushner OR 미국 특사 OR 미 특사) when:24h',
    '(Zelenskiy OR Zelensky OR 젤렌스키) (Turkey OR UAE OR Switzerland OR 터키 OR UAE OR 스위스) (trilateral OR 3자 OR 삼자) (peace OR 평화 OR 종전) when:24h',
    '(Zelenskiy OR Zelensky OR 젤렌스키) (grain OR energy infrastructure OR prisoner exchange OR 곡물 OR 에너지 인프라 OR 포로 교환) (peace talks OR 평화 회담 OR 종전 협상) when:24h',
    'site:yna.co.kr 젤렌스키 (윗코프 OR 위트코프 OR 쿠슈너) (새 아이디어 OR 합리적인 제안 OR 새로운 아이디어 OR 돌파구 OR 종전안 OR 추가 회의) when:24h',
    '(젤렌스키 OR Zelenskiy OR Zelensky) (윗코프 OR 위트코프 OR Witkoff OR 쿠슈너 OR Kushner OR 미국 특사) (새 아이디어 OR 새로운 아이디어 OR new ideas OR decent ideas OR worthwhile ideas OR 종전안 OR 돌파구 OR 추가 협상) when:24h',
]
watch.QUERIES = NEW_IDEA_QUERIES + list(watch.QUERIES)

_prev_google_news = watch.google_news
_prev_score = watch.score_item
_prev_item_id = watch.item_id
_prev_build_alert = watch.build_alert


def _text(row):
    return ' '.join([
        row.get('title_ko', ''),
        row.get('title_original', ''),
        row.get('description', ''),
        ' '.join(row.get('signals_ko', [])),
        ' '.join(row.get('forced_tags', [])),
    ]).lower()


def _newidea_signals(row):
    text = _text(row)
    signals, marks = [], []

    zelensky = any(k in text for k in ('zelensky','zelenskiy','젤렌스키','kyiv','키이우','키예프'))
    us_envoy = any(k in text for k in (
        'witkoff','윗코프','위트코프','kushner','쿠슈너',
        'us envoy','u.s. envoy','us envoys','u.s. envoys','미국 특사','미 특사',
    ))
    kremlin = any(k in text for k in ('kremlin','크렘린궁','크렘린','peskov','페스코프'))
    trilateral = any(k in text for k in (
        'trilateral talks','trilateral meeting','trilateral negotiations','3자 협상','3자협상','3자 회담','3자회담','삼자 협상','삼자 회담',
    ))
    restart = any(k in text for k in (
        'restart peace talks','restart talks','resume peace talks','resume talks','resume negotiations',
        'does not rule out','not rule out','open to restarting','open to resuming',
        '협상 재개','회담 재개','재개 가능성','배제하지 않','배제 안해','열려 있',
    ))

    ua_context = zelensky and us_envoy

    if zelensky and any(k in text for k in (
        'ready to resume negotiations','ready for negotiations','willing to resume negotiations',
        'willing to resume talks','open to resuming talks','resume peace talks','resume negotiations',
        '종전 협상 재개 의사','종전협상 재개 의사','협상 재개 의사','협상 재개 준비',
        '평화 협상 재개','평화협상 재개','회담 재개 의사',
    )):
        signals.append('젤렌스키 측이 종전·평화 협상 재개 의사를 공개적으로 확인')
        marks.append('젤렌스키협상재개의사')

    if kremlin and trilateral and restart:
        signals.append('크렘린궁: 러시아·미국·우크라이나 3자 종전협상 재개 가능성을 배제하지 않음')
        marks.append('크렘린3자재개가능')

    if ua_context and any(k in text for k in (
        'decent ideas','worthwhile ideas','decent, worthwhile ideas',
        '합리적인 제안','합리적 제안','괜찮은 아이디어','검토할 가치가 있는','가치 있는 아이디어',
    )):
        signals.append('젤렌스키: 미국 특사들이 평화 회담을 위한 합리적·검토할 가치가 있는 제안을 제시')
        marks.append('합리적평화제안')

    if ua_context and any(k in text for k in ('new ideas','new idea','new proposal','진전된 새로운 아이디어','새 아이디어','새로운 아이디어','새로운 안')):
        signals.append('미국 특사단, 러시아·우크라이나 접촉 뒤 새 종전 아이디어를 제시')
        marks.append('새종전아이디어')

    if ua_context and any(k in text for k in ('very substantive','substantive and important','매우 실질적','실질적이고 중요한','중요한 논의')):
        signals.append('미·우 회담이 장시간 실질 협상 단계로 진행')
        marks.append('실질협상')

    if any(k in text for k in ('no breakthrough','no concrete breakthrough','돌파구 못 찾아','돌파구는 못','no breakthrough was reached')):
        signals.append('협상 재개에도 즉각적인 종전 돌파구는 아직 없음')
        marks.append('돌파구없음')

    if (ua_context or kremlin or zelensky) and any(k in text for k in (
        'new trilateral talks','trilateral talks','trilateral summit','3자 회담','삼자 회담',
        '새 회담','another meeting','회의를 또 열기로','다음 회의','prepare trilateral','preparing trilateral',
    )):
        signals.append('후속 3자 협상·회담이 실제 준비 단계로 이동하는지 확인')
        marks.append('3자회담준비')

    # 한 기사 안에서 우크라이나의 협상 재개 의사와 러시아의 3자 협상 개방이 함께 확인되면 단계 상승.
    if '젤렌스키협상재개의사' in marks and '크렘린3자재개가능' in marks:
        signals.append('협상 단계 상승: 우크라이나와 러시아 양측 모두 미국 중재 협상 재개 가능성을 열어둠')
        marks.append('양측협상의사확인')

    places = []
    for eng, ko in (('turkey','터키'),('uae','UAE'),('united arab emirates','UAE'),('switzerland','스위스')):
        if eng in text or ko.lower() in text:
            if ko not in places:
                places.append(ko)
    if places and any(k in text for k in ('trilateral','3자','삼자','summit','회담')):
        signals.append('차기 회담 후보지: ' + '·'.join(places))
        marks.append('회담후보지')

    grain = any(k in text for k in ('grain shipment','grain shipments','grain export','곡물 수송','곡물 운송','곡물 수출'))
    energy = any(k in text for k in ('energy infrastructure','energy facilit','에너지 인프라','에너지 시설'))
    if grain or energy:
        agenda = []
        if grain:
            agenda.append('곡물 수송')
        if energy:
            agenda.append('에너지 인프라')
        signals.append('후속 협상 실무 의제에 ' + '·'.join(agenda) + ' 포함')
        marks.append('실무의제')

    if any(k in text for k in ('prisoner exchange','prisoner exchanges','pow exchange','prisoners of war','포로 교환','포로교환')):
        signals.append('포로 교환 확대·가속도 후속 합의 가능성을 확인할 항목')
        marks.append('포로교환')

    if any(k in text for k in (
        'meet trump','meeting with trump','meet with president trump','later in september','late september',
        '트럼프와 회동','트럼프 회동','9월 후반','9월 말',
    )):
        signals.append('젤렌스키의 9월 후반 Trump 회동이 다음 고위급 촉발 요인')
        marks.append('트럼프후속회동')

    if any(k in text for k in ('winter air defence','winter air defense','air defence package','air defense package','겨울 방공','방공 지원 패키지')):
        signals.append('평화 협상과 별개로 겨울철 방공 지원 패키지도 병행 논의')
        marks.append('겨울방공지원')

    if any(k in text for k in ('war could continue until winter','전쟁 겨울까지','겨울까지 전쟁')):
        signals.append('젤렌스키는 조기 종전에 여전히 신중 — 전쟁이 겨울까지 이어질 가능성 언급')
        marks.append('조기종전신중')

    return list(dict.fromkeys(signals)), sorted(set(marks))


def newidea_google_news(query):
    rows, err = _prev_google_news(query)
    for row in rows:
        signals, marks = _newidea_signals(row)
        if not marks:
            continue
        row['signals_ko'] = list(dict.fromkeys(signals + list(row.get('signals_ko', []))))
        row['newidea_marks'] = marks
        row['forced_tags'] = list(dict.fromkeys(list(row.get('forced_tags', [])) + ['종전·협상','협상내용','휴전·평화']))
        row['deep_signal'] = True
    return rows, err


watch.google_news = newidea_google_news


def newidea_score_item(x, now):
    score, tags = _prev_score(x, now)
    signals, marks = _newidea_signals(x)
    if marks:
        if '양측협상의사확인' in marks:
            score += 72
        elif '크렘린3자재개가능' in marks:
            score += 58
        elif '젤렌스키협상재개의사' in marks:
            score += 54
        elif '합리적평화제안' in marks:
            score += 50
        elif '새종전아이디어' in marks:
            score += 36
        else:
            score += 20
        if '3자회담준비' in marks:
            score += 16
        if '실무의제' in marks:
            score += 10
        if '포로교환' in marks:
            score += 8
        if '트럼프후속회동' in marks:
            score += 8
        if '돌파구없음' in marks:
            score += 8
        src = (x.get('source') or '').lower()
        if any(k in src for k in ('reuters','president of ukraine','president.gov.ua','kremlin','크렘린','연합뉴스','yonhap','뉴스1','news1','파이낸셜뉴스','fnnews')):
            score += 10
        tags = sorted(set(tags + ['종전·협상','협상내용','휴전·평화']))
        x['newidea_marks'] = marks
        if signals:
            x['signals_ko'] = list(dict.fromkeys(signals + list(x.get('signals_ko', []))))
            x['deep_signal'] = True
    return score, tags


watch.score_item = newidea_score_item


def newidea_item_id(x):
    base_id = _prev_item_id(x)
    _, marks = _newidea_signals(x)
    if not marks:
        return base_id
    # 제안→우크라이나 재개의사→러시아 3자협상 개방→양측 확인 순으로 단계가 높아지면 후속 알림 허용.
    important = [m for m in marks if m in (
        '합리적평화제안','새종전아이디어','젤렌스키협상재개의사','크렘린3자재개가능','양측협상의사확인',
        '3자회담준비','회담후보지','실무의제','포로교환','트럼프후속회동','겨울방공지원','돌파구없음','조기종전신중',
    )]
    key = base_id + '|newideas-v3|' + '|'.join(important)
    return hashlib.sha256(key.encode('utf-8')).hexdigest()[:20]


watch.item_id = newidea_item_id


def _inject_newideas(text, items):
    marks = set()
    for x in items:
        _, m = _newidea_signals(x)
        marks.update(m)
    if not marks:
        return text

    rows = []
    if '양측협상의사확인' in marks or ('젤렌스키협상재개의사' in marks and '크렘린3자재개가능' in marks):
        rows.append('- <b>단계 상승:</b> 우크라이나와 러시아 양측 모두 미국 중재 협상 재개 가능성을 열어둠')
    else:
        if '젤렌스키협상재개의사' in marks:
            rows.append('- <b>우크라이나:</b> 젤렌스키 측이 종전·평화 협상 재개 의사를 확인')
        if '크렘린3자재개가능' in marks:
            rows.append('- <b>러시아:</b> 크렘린궁이 러·미·우 3자 협상 재개 가능성을 배제하지 않음')
    if '합리적평화제안' in marks:
        rows.append('- <b>제안:</b> 젤렌스키가 미국 특사단의 평화회담 아이디어를 합리적·검토할 가치가 있다고 평가')
    elif '새종전아이디어' in marks:
        rows.append('- <b>제안:</b> 미국 특사단이 새 종전 아이디어를 제시')
    if '3자회담준비' in marks:
        rows.append('- <b>현재 단계:</b> 후속 3자 협상 준비 가능성 — 개최 확정·합의 문안은 아직 별개')
    if '회담후보지' in marks:
        rows.append('- <b>후보지:</b> 터키·UAE·스위스 등 실제 개최지 확정 여부 확인')
    if '실무의제' in marks:
        rows.append('- <b>의제:</b> 곡물 수송·에너지 인프라 등 실무 합의 가능성 확인')
    if '포로교환' in marks:
        rows.append('- <b>인도주의:</b> 포로 교환 확대·가속 여부 확인')
    if '트럼프후속회동' in marks:
        rows.append('- <b>다음:</b> 9월 후반 Zelenskiy–Trump 회동이 다음 고위급 촉발 요인')
    if '돌파구없음' in marks:
        rows.append('- <b>제약:</b> 즉각적인 종전 돌파구는 아직 확인되지 않음')

    marker = '<b>투자 판정</b>\n'
    pos = text.find(marker)
    if pos != -1:
        insert = pos + len(marker)
        return text[:insert] + '\n'.join(rows[:8]) + '\n' + text[insert:]
    return text


def newidea_build_alert(items, markets, now):
    text = _prev_build_alert(items, markets, now)
    return _inject_newideas(text, items).strip()[:4000] + '\n'


watch.build_alert = newidea_build_alert


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
