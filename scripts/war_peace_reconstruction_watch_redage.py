#!/usr/bin/env python3
import argparse
import re

import war_peace_reconstruction_watch_compact as prev

watch = prev.watch
runner = prev.runner
base = prev.base

_prev_build_alert = watch.build_alert


def _highlight_relative_age(text):
    """Telegram 일반 메시지는 글자색 지정이 안 되므로 경과시간에만 빨간 표시를 붙여 강조한다."""
    text = re.sub(r"(?<!🟥 )(<b>\d{1,5}분 전</b>)", r"🟥 \1", text)
    text = re.sub(r"(?<!🟥 )(?<!<b>)(\d{1,5}분 전)(?!</b>)", r"🟥 <b>\1</b>", text)
    return text


def redage_build_alert(items, markets, now):
    return _highlight_relative_age(_prev_build_alert(items, markets, now))


watch.build_alert = redage_build_alert


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
