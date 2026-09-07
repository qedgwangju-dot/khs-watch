#!/usr/bin/env python3
import argparse
import hashlib

import war_peace_reconstruction_watch_allies as prev

watch = prev.watch
runner = prev.runner
base = prev.base

NEW_IDEA_QUERIES = [
    'site:reuters.com Witkoff Zelenskiy Kyiv ("new ideas" OR "new proposal" OR "new trilateral talks" OR "encouraged") when:24h',
    'site:yna.co.kr 젤렌스키 윗코프 (새 아이디어 OR 새로운 아이디어 OR 돌파구 OR 종전안 OR 추가 회의) when:24h',
    '(젤렌스키 OR Zelenskiy OR Zelensky) (윗코프 OR 위트코프 OR Witkoff) (새 아이디어 OR 새로운 아이디어 OR new ideas OR 종전안 OR 돌파구 OR 추가 협상) when:24h',
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
    ]).lower()


def _newidea_signals(row):
    text = _text(row)
    signals, marks = [], []
    context = any(k in text for k in ('witkoff','윗코프','위트코프')) and any(k in text for k in ('zelensky','zelenskiy','젤렌스키','kyiv','키이우','키예프'))
    if not context:
        return signals, marks

    if any(k in text for k in ('new ideas','new idea','new proposal','진전된 새로운 아이디어','새 아이디어','새로운 아이디어','새로운 안')):
        signals.append('윗코프, 모스크바 협의에서 나온 새 종전 아이디어를 키이우에 전달')
        marks.append('새종전아이디어')
    if any(k in text for k in ('very substantive','substantive and important','매우 실질적','실질적이고 중요한','중요한 논의')):
        signals.append('미·우 키이우 회담이 장시간 실질 협상 단계로 진행')
        marks.append('실질협상')
    if any(k in text for k in ('no breakthrough','no concrete breakthrough','돌파구 못 찾아','돌파구는 못','breakthrough was achieved')):
        signals.append('장시간 회담에도 즉각적인 종전 돌파구는 아직 없음')
        marks.append('돌파구없음')
    if any(k in text for k in ('new trilateral talks','trilateral talks','3자 회담','삼자 회담','새 회담','another meeting','회의를 또 열기로','다음 회의')):
        signals.append('후속 협상·3자 회담 일정으로 이어지는지 확인')
        marks.append('후속회담')
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
        row['forced_tags'] = list(dict.fromkeys(list(row.get('forced_tags', [])) + ['종전·협상','협상내용']))
        row['deep_signal'] = True
    return rows, err


watch.google_news = newidea_google_news


def newidea_score_item(x, now):
    score, tags = _prev_score(x, now)
    signals, marks = _newidea_signals(x)
    if marks:
        score += 36 if '새종전아이디어' in marks else 20
        if '돌파구없음' in marks:
            score += 8
        src = (x.get('source') or '').lower()
        if any(k in src for k in ('reuters','연합뉴스','yonhap')):
            score += 8
        tags = sorted(set(tags + ['종전·협상','협상내용']))
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
    key = base_id + '|newideas|' + '|'.join(marks)
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
    if '새종전아이디어' in marks:
        rows.append('- <b>제안:</b> 모스크바에서 논의한 새 종전 아이디어를 키이우에 전달')
    if '실질협상' in marks:
        rows.append('- <b>회담:</b> 미·우 장시간 실질 협상 진행')
    if '돌파구없음' in marks:
        rows.append('- <b>판정:</b> 즉각적 돌파구는 아직 없음')
    if '후속회담' in marks:
        rows.append('- <b>다음:</b> 새 3자·후속 회담 일정 발표 여부 확인')
    marker = '<b>투자 판정</b>\n'
    pos = text.find(marker)
    if pos != -1:
        insert = pos + len(marker)
        return text[:insert] + '\n'.join(rows[:4]) + '\n' + text[insert:]
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
