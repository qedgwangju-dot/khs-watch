#!/usr/bin/env python3
import argparse
import hashlib

import war_peace_reconstruction_watch_disaster_recovery as prev

watch = prev.watch
runner = prev.runner
base = prev.base
guard = prev.guard

_prev_score = watch.score_item
_prev_item_id = watch.item_id
_prev_verdict = guard._verdict

OFFICIAL_HOSTS = ('mofa.go.kr', 'korea.kr', 'gov.kr')


def _official(row):
    blob = ' '.join([
        row.get('source',''), row.get('link',''), row.get('resolved_url',''),
    ]).lower()
    return any(h in blob for h in OFFICIAL_HOSTS) or '외교부' in blob


def _strong_kdrt(row):
    marks = prev._disaster_marks(row)
    return any(m in marks for m in (
        'KDRT재건복구임무확정','KDRT재건복구파견','KDRT재건복구현장투입',
    ))


def score_item(row, now):
    score, tags = _prev_score(row, now)
    if score < 0 or not _strong_kdrt(row):
        return score, tags

    sig = list(row.get('signals_ko', []))
    if _official(row):
        row['disaster_verification'] = 'official'
        sig.insert(0, '외교부·정부 공식자료로 KDRT 재건·복구 단계 확인')
        score += 10
    else:
        row['disaster_verification'] = 'media'
        sig.insert(0, '언론 보도 단계 — KDRT 재건·복구 임무는 외교부 공식 발표 후 최종 확정')
    row['signals_ko'] = list(dict.fromkeys(sig))
    return score, tags

watch.score_item = score_item


def item_id(row):
    base_id = _prev_item_id(row)
    if not _strong_kdrt(row):
        return base_id
    level = 'official' if _official(row) else 'media'
    return hashlib.sha256((base_id + '|verification|' + level).encode()).hexdigest()[:20]

watch.item_id = item_id


def _verdict(items):
    text = _prev_verdict(items)
    disaster_items = [x for x in items if prev._is_disaster_recovery(x)]
    if not disaster_items:
        return text
    kdrt = [x for x in disaster_items if _strong_kdrt(x)]
    if not kdrt:
        return text
    if any(_official(x) for x in kdrt):
        note = '- <b>검증 수준:</b> 외교부·정부 공식 확인 포함'
    else:
        note = '- <b>검증 수준:</b> 언론 확인 — 외교부 공식 발표 전까지 임무 확정은 잠정'
    return text + '\n' + note

guard._verdict = _verdict


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
