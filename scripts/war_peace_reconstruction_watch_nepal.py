#!/usr/bin/env python3
import argparse
import hashlib

import war_peace_reconstruction_watch_allies as prev

watch = prev.watch
runner = prev.runner
base = prev.base

NEPAL_RECON_QUERIES = [
    'site:mofa.go.kr 네팔 재건 복구 조현 홍수 지원 when:48h',
    'site:mofa.gov.np South Korea Nepal reconstruction rehabilitation Cho Hyun flood when:48h',
    'site:reuters.com South Korea Nepal reconstruction flood Cho Hyun when:48h',
    'site:yna.co.kr 네팔 재건 한국 정부 조현 홍수 when:48h',
    '(South Korea OR 한국) Nepal (reconstruction OR rehabilitation OR rebuilding OR 재건 OR 복구) flood when:48h',
]
watch.QUERIES = NEPAL_RECON_QUERIES + list(watch.QUERIES)

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


def _nepal_recon_signals(row):
    text = _text(row)
    signals, marks = [], []
    if not any(k in text for k in ('nepal', '네팔')):
        return signals, marks
    if not any(k in text for k in ('south korea', 'republic of korea', '한국', '대한민국', 'cho hyun', '조현')):
        return signals, marks

    recon = any(k in text for k in ('reconstruction', 'rehabilitation', 'rebuilding', 'post-disaster reconstruction', 'post flood reconstruction', '재건', '복구'))
    if recon:
        signals.append('한국 정부, 네팔 홍수 이후 재건·복구 지원 의향 확인')
        marks.append('재건지원의향')

    if any(k in text for k in ('build back better', 'resilient', 'durable infrastructure', '회복탄력', '회복력', '견고한 인프라')):
        signals.append('네팔은 더 안전하고 회복력 있는 인프라 중심의 재건을 우선')
        marks.append('회복력인프라')

    if any(k in text for k in ('usd 1 million', '$1 million', '1 million', '100만달러', '100만 달러')):
        signals.append('기존 긴급 인도지원 100만달러는 재건 예산과 별도')
        marks.append('긴급지원100만달러')

    if any(k in text for k in ('44-member', '44 member', '44명', 'kdrt', 'korea disaster relief team', '대한민국 해외긴급구호대')):
        signals.append('대한민국 해외긴급구호대 44명 파견은 수색·구조 단계')
        marks.append('긴급구호대44명')

    if any(k in text for k in ('financial assistance', 'international financial assistance', 'climate finance', '국제 금융', '국제사회 금융지원', '기후 금융')):
        signals.append('한국은 네팔의 국제 재건·기후재원 확보 지원 의사도 표명')
        marks.append('국제재원지원')

    if any(k in text for k in ('hydropower', 'hydroelectric', 'roads', 'bridges', '수력발전', '도로', '교량')):
        signals.append('피해 복구 대상은 도로·교량·수력발전 인프라까지 확장 가능')
        marks.append('인프라복구')

    return list(dict.fromkeys(signals)), sorted(set(marks))


def nepal_google_news(query):
    rows, err = _prev_google_news(query)
    for row in rows:
        signals, marks = _nepal_recon_signals(row)
        if not marks:
            continue
        row['signals_ko'] = list(dict.fromkeys(signals + list(row.get('signals_ko', []))))
        row['nepal_recon_marks'] = marks
        row['forced_tags'] = list(dict.fromkeys(list(row.get('forced_tags', [])) + ['네팔', '재난·재건', '한국지원']))
        row['deep_signal'] = True
    return rows, err


watch.google_news = nepal_google_news


def nepal_score_item(x, now):
    score, tags = _prev_score(x, now)
    signals, marks = _nepal_recon_signals(x)
    if marks:
        score += 34
        if '재건지원의향' in marks:
            score += 12
        src = (x.get('source') or '').lower()
        if any(k in src for k in ('mofa', 'ministry of foreign affairs', 'reuters', 'yonhap', '연합뉴스', 'radio nepal')):
            score += 10
        tags = sorted(set(tags + ['네팔', '재난·재건', '한국지원']))
        x['nepal_recon_marks'] = marks
        if signals:
            x['signals_ko'] = list(dict.fromkeys(signals + list(x.get('signals_ko', []))))
            x['deep_signal'] = True
    return score, tags


watch.score_item = nepal_score_item


def nepal_item_id(x):
    base_id = _prev_item_id(x)
    _, marks = _nepal_recon_signals(x)
    if not marks:
        return base_id
    key = base_id + '|nepalrecon|' + '|'.join(marks)
    return hashlib.sha256(key.encode('utf-8')).hexdigest()[:20]


watch.item_id = nepal_item_id


def _inject_nepal_stage(text, items):
    marks = set()
    for x in items:
        _, m = _nepal_recon_signals(x)
        marks.update(m)
    if not marks:
        return text

    rows = []
    if '재건지원의향' in marks:
        rows.append('- <b>단계:</b> 한국 정부의 재건·복구 지원 의향 확인')
    if '긴급지원100만달러' in marks:
        rows.append('- <b>확정:</b> 긴급 인도지원 100만달러 — 재건 예산과는 별도')
    if '긴급구호대44명' in marks:
        rows.append('- <b>현장:</b> 해외긴급구호대 44명은 수색·구조 단계')
    rows.append('- <b>미확정:</b> 재건 사업비·발주처·입찰·한국기업 수주는 아직 미공개')
    if '국제재원지원' in marks:
        rows.append('- <b>다음:</b> 국제 재원조달 → 피해복구 사업목록 → 입찰·본계약 확인')
    else:
        rows.append('- <b>다음:</b> 피해복구 사업목록 → 예산·재원 → 입찰·본계약 확인')

    block = '<b>재건 단계</b>\n' + '\n'.join(rows[:5]) + '\n'
    markers = ('\n<b>시장 파급</b>\n', '\n<b>시장 반응</b>\n', '\n<b>투자 판정</b>\n')
    positions = [text.find(m) for m in markers if text.find(m) != -1]
    if positions:
        pos = min(positions)
        return text[:pos].rstrip() + '\n\n' + block + text[pos:].lstrip('\n')
    return text.rstrip() + '\n\n' + block


def nepal_build_alert(items, markets, now):
    text = _prev_build_alert(items, markets, now)
    return _inject_nepal_stage(text, items).strip()[:4000] + '\n'


watch.build_alert = nepal_build_alert


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
