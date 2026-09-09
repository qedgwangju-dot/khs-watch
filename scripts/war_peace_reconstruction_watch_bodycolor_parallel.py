#!/usr/bin/env python3
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

import war_peace_reconstruction_watch_bodycolor as prev

watch = prev.watch
runner = prev.runner
base = prev.base


def _safe_enrich(row):
    try:
        prev._enrich_body(row)
    except Exception:
        pass


def build_alert(items, markets, now):
    # 5분 주기 감시를 유지하기 위해 최종 후보 원문 본문을 동시에 조회한다.
    targets = list(items[:8])
    if targets:
        with ThreadPoolExecutor(max_workers=min(8, len(targets))) as ex:
            futures = [ex.submit(_safe_enrich, row) for row in targets]
            for fut in as_completed(futures):
                try:
                    fut.result()
                except Exception:
                    pass

    # bodycolor 모듈의 순차 build_alert를 다시 호출하지 않고,
    # 그 이전 실제 메시지 생성기 → 본문기준 색상 재적용 순서로 처리한다.
    text = prev._prev_build_alert(items, markets, now)
    return prev._reapply_colors(text, items).strip()[:4000] + "\n"


watch.build_alert = build_alert


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--finalize", action="store_true")
    ap.add_argument("--telegram-test", action="store_true")
    args = ap.parse_args()
    if args.finalize:
        watch.finalize()
        return
    if args.telegram_test:
        base._write_inline_test()
    else:
        watch.run(test=False)
    runner.verify_alert(test_mode=False)


if __name__ == "__main__":
    main()
