#!/usr/bin/env python3
from pathlib import Path
import re

watcher = Path('scripts/honam_semiconductor_watch.py')
text = watcher.read_text(encoding='utf-8')

# Broaden local-topic recognition so titles such as
# '반도체 10만 명대 정주 수요 예고…전남광주시, 주거정책 다시 짠다'
# are not dropped merely because the title omits the exact phrase '호남권 반도체'.
new_relevant = '''def relevant(item):
    text = f"{item['title']} {item['description']}"
    low = text.lower()
    has_explicit_topic = any(term.lower() in low for term in TOPIC_TERMS)
    local_terms = ["전남광주", "전남광주시", "광주", "광산구", "산정지구", "송정역", "상무", "군공항"]
    has_local_semiconductor_topic = "반도체" in low and any(term in low for term in local_terms)
    has_topic = has_explicit_topic or has_local_semiconductor_topic
    stages = detect_stages(text)
    if not has_topic or not stages:
        return False, stages
    if not broad_material_enough(text, stages):
        return False, stages
    return True, stages


'''
pattern = re.compile(r'def relevant\(item\):\n.*?(?=def impact\(text: str, stages\) -> str:)', re.S)
if not pattern.search(text):
    raise SystemExit('relevant() block not found')
text = pattern.sub(new_relevant, text, count=1)

anchor = '    \'"전남광주" 반도체 주거정책 정주 수요\',\n'
extra = "    '전남광주 반도체 주거정책 정주 주택',\n    '광주 반도체 정주 주거 배후도시',\n"
if anchor in text and extra not in text:
    text = text.replace(anchor, anchor + extra, 1)

watcher.write_text(text, encoding='utf-8')

workflow = Path('.github/workflows/honam-semiconductor-watch-telegram.yml')
wf = workflow.read_text(encoding='utf-8')
wf = wf.replace('name: Honam Semiconductor Jangrok Telegram Watch', 'name: Honam Semiconductor Project Telegram Watch', 1)

new_persist = '''      - name: Persist state
        if: success() && (hashFiles('out/honam_semiconductor_alert.json') == '' || hashFiles('out/honam_semiconductor_telegram_confirmed.json') != '')
        run: |
          cp out/honam_semiconductor_pending_state.json /tmp/honam_semiconductor_watch_state.json
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          pushed=0
          for attempt in 1 2 3 4; do
            git fetch origin main
            git reset --hard origin/main
            mkdir -p data
            cp /tmp/honam_semiconductor_watch_state.json data/honam_semiconductor_watch_state.json
            git add data/honam_semiconductor_watch_state.json
            if git diff --cached --quiet; then
              echo "Honam watcher state unchanged"
              pushed=1
              break
            fi
            git commit -m "Record Honam semiconductor watch state"
            if git push origin HEAD:main; then
              pushed=1
              break
            fi
            echo "State push raced with another commit; retrying ($attempt/4)"
            sleep $((attempt * 2))
          done
          if [ "$pushed" != "1" ]; then
            echo "Failed to persist Honam watcher state after retries"
            exit 1
          fi

'''
wf_pattern = re.compile(r'      - name: Persist state\n.*?(?=      - name: Upload verification artifacts\n)', re.S)
if not wf_pattern.search(wf):
    raise SystemExit('Persist state block not found')
wf = wf_pattern.sub(new_persist, wf, count=1)
workflow.write_text(wf, encoding='utf-8')

print('patched=true')
