"""Delivery/checkpoint adapter for the existing HBM workflow; no new bot or schedule.

A durable in-flight journal is written BEFORE each Telegram call. An ambiguous
network failure is quarantined, never blindly retried. Source states are promoted
only after every chunk is acknowledged. Each route checkpoints independently.
"""
from __future__ import annotations
import argparse
import base64
import copy
import hashlib
import html
from html.parser import HTMLParser
import json
import os
import pathlib
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'out'
ROUTES = {
    'samsung': ('data/samsung_hbm_watch_state.json', 'out/samsung_hbm_alert.html', ''),
    'rubin': ('data/rubin_hbm_watch_state.json', 'out/rubin_hbm_alert.md', 'out/rubin_hbm_pending_state.json'),
    'skhynix': ('data/skhynix_us_memory_watch_state.json', 'out/skhynix_us_memory_alert.html', ''),
}
EXPECTED = 'khs88798879887988798879_bot'


def now():
    return datetime.now(ZoneInfo('Asia/Seoul')).isoformat(timespec='seconds')


def read(path, default=None):
    p = pathlib.Path(path)
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else copy.deepcopy(default or {})


def write(path, value):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(p)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def guard(value):
    body = json.dumps(value, ensure_ascii=False)
    for name in ('KCS_DATA_GO_SERVICE_KEY', 'TELEGRAM_BOT_TOKEN', 'GITHUB_TOKEN'):
        key = os.getenv(name, '').strip()
        variants = {key, urllib.parse.unquote(key), urllib.parse.quote(key, safe='')}
        if any(k and k in body for k in variants):
            raise RuntimeError('credential detected; checkpoint blocked')


class Repository:
    def __init__(self):
        self.repo = os.environ['GITHUB_REPOSITORY']
        self.token = os.environ['GITHUB_TOKEN']

    def request(self, method, path, payload=None):
        req = urllib.request.Request(
            'https://api.github.com/repos/' + self.repo + '/' + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={'Authorization': 'Bearer ' + self.token, 'Accept': 'application/vnd.github+json',
                     'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'hbm-delivery-checkpoint'}, method=method)
        try:
            with urllib.request.urlopen(req, timeout=35) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            raise RuntimeError('repository checkpoint HTTP ' + str(e.code)) from None
        except Exception:
            raise RuntimeError('repository checkpoint unavailable') from None

    def current(self, path):
        obj = self.request('GET', 'contents/' + path + '?ref=main')
        return obj['sha'], json.loads(base64.b64decode(obj['content']))

    def checkpoint(self, path, expected, desired):
        guard(desired)
        for _ in range(3):
            sha, remote = self.current(path)
            if digest(remote) == digest(desired):
                write(ROOT / path, desired)
                return
            if digest(remote) != digest(expected):
                raise RuntimeError('state changed concurrently; refusing stale overwrite: ' + path)
            encoded = base64.b64encode((json.dumps(desired, ensure_ascii=False, indent=2) + '\n').encode()).decode()
            try:
                result = self.request('PUT', 'contents/' + path, {
                    'message': 'Checkpoint HBM delivery state [skip ci]', 'content': encoded,
                    'sha': sha, 'branch': 'main'})
            except RuntimeError:
                # A PUT response can be lost after the server committed it.
                # Re-read and accept only an exact match; never force-overwrite.
                continue
            write(ROOT / path, desired)
            print('hbm_checkpoint_ok path=' + path + ' commit=' + result['commit']['sha'])
            return
        raise RuntimeError('state checkpoint failed after bounded retries: ' + path)


def api(method, payload=None):
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
    if not token:
        raise RuntimeError('HBM Telegram token missing')
    data = urllib.parse.urlencode(payload).encode() if payload else None
    req = urllib.request.Request('https://api.telegram.org/bot' + token + '/' + method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            result = json.load(r)
    except urllib.error.HTTPError as exc:
        raise RuntimeError('Telegram HTTP ' + str(exc.code)) from None
    except Exception:
        raise RuntimeError('Telegram response uncertain; automatic retry blocked') from None
    if not result.get('ok'):
        raise RuntimeError('Telegram rejected request')
    return result['result']


def route_check():
    identity = api('getMe')
    if identity.get('username', '').lower() != EXPECTED.lower():
        raise RuntimeError('unexpected Telegram bot; delivery blocked')
    if not os.environ.get('TELEGRAM_CHAT_ID', '').strip():
        raise RuntimeError('HBM Telegram chat missing')
    print('telegram_route_valid=true bot=@' + EXPECTED)


class HTMLBalance(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.stack = []
    def handle_starttag(self, tag, attrs):
        self.stack.append((tag, self.get_starttag_text()))
    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1][0] != tag:
            raise ValueError('unbalanced Telegram HTML')
        self.stack.pop()


def chunks(text, limit=3600):
    """Keep nested anchors/expandable quotes balanced across chunk boundaries."""
    if not text.strip():
        return []
    parser, result, current = HTMLBalance(), [], ''
    for line in text.splitlines():
        if len(line.encode('utf-16-le')) // 2 > limit - 180:
            raise ValueError('single alert line exceeds safe Telegram length; not truncated')
        closing = ''.join('</' + tag + '>' for tag, _ in reversed(parser.stack))
        candidate = current + ('\n' if current else '') + line
        if len((candidate + closing).encode('utf-16-le')) // 2 > limit:
            result.append(current + closing)
            current = ''.join(raw for _, raw in parser.stack) + line
        else:
            current = candidate
        parser.feed(line)
    parser.close()
    if parser.stack:
        raise ValueError('unclosed Telegram HTML')
    if current.strip():
        result.append(current)
    for part in result:
        if len(part.encode('utf-16-le')) // 2 > 4096:
            raise ValueError('Telegram chunk too large')
    return result


def promote(candidate, before):
    # Keep independent lead-time metadata rather than deleting it with a
    # collector pending-state document that lacks those fields.
    result = copy.deepcopy(before)
    result.pop('_delivery', None)
    result.update(candidate)
    result.pop('_delivery', None)
    return result


def transact(repo, path, before, candidate, text, send=api):
    candidate = promote(candidate, before)
    if not text.strip():
        candidate['delivery_check'] = {'checked_at_kst': now(), 'status': 'no_message_due'}
        repo.checkpoint(path, before, candidate)
        return {'status': 'no_message_due', 'message_ids': []}
    journal = {
        'id': digest({'text': text, 'candidate': candidate}), 'status': 'queued',
        'created_at_kst': now(), 'chunks': chunks(text), 'next_chunk': 0,
        'message_ids': [], 'candidate': candidate,
    }
    queued = copy.deepcopy(before)
    queued['_delivery'] = journal
    repo.checkpoint(path, before, queued)
    return resume_one(repo, path, queued, send)


def resume_one(repo, path, state, send=api):
    journal = copy.deepcopy(state.get('_delivery') or {})
    if not journal:
        return {'status': 'no_pending_delivery'}
    if journal.get('status') in ('in_flight', 'uncertain'):
        raise RuntimeError('unconfirmed prior send; duplicate prevention hold: ' + path)
    current = copy.deepcopy(state)
    for index in range(int(journal['next_chunk']), len(journal['chunks'])):
        moving = copy.deepcopy(current)
        moving['_delivery']['status'] = 'in_flight'
        moving['_delivery']['attempt_at_kst'] = now()
        repo.checkpoint(path, current, moving)
        current = moving
        try:
            result = send('sendMessage', {
                'chat_id': os.environ.get('TELEGRAM_CHAT_ID', ''), 'text': journal['chunks'][index],
                'parse_mode': 'HTML', 'disable_web_page_preview': 'true'})
            if not isinstance(result.get('message_id'), int):
                raise RuntimeError('Telegram acknowledgement lacks message_id')
        except Exception as exc:
            held = copy.deepcopy(current)
            held['_delivery']['status'] = 'uncertain'
            held['_delivery']['error_type'] = type(exc).__name__
            repo.checkpoint(path, current, held)
            raise RuntimeError('delivery not acknowledged; state not promoted: ' + path) from None
        done = copy.deepcopy(current)
        done['_delivery']['message_ids'].append(result['message_id'])
        done['_delivery']['next_chunk'] = index + 1
        done['_delivery']['status'] = 'partial'
        repo.checkpoint(path, current, done)
        current = done
    receipt = {'status': 'confirmed', 'bot_username': EXPECTED,
               'message_ids': current['_delivery']['message_ids'], 'confirmed_at_kst': now(),
               'payload_hash': digest(journal['chunks'])}
    final = promote(journal['candidate'], current)
    final['last_successful_delivery_kst'] = receipt['confirmed_at_kst']
    final['telegram_message_ids'] = receipt['message_ids']
    final['telegram_message_id'] = receipt['message_ids'][-1]
    final['bot_username'] = EXPECTED
    final['delivery_receipt'] = receipt
    final['delivery_check'] = {'checked_at_kst': now(), 'status': 'confirmed'}
    repo.checkpoint(path, current, final)
    return receipt


def begin():
    repo = Repository()
    for name, (path, _, _) in ROUTES.items():
        _, state = repo.current(path)
        write(ROOT / path, state)
        if state.get('_delivery'):
            result = resume_one(repo, path, state)
            print('resumed=' + name + ' status=' + result['status'])
            _, state = repo.current(path)
            write(ROOT / path, state)
        write(OUT / ('hbm_before_' + name + '.json'), state)
    print('hbm_transaction_baselines_ready=true')


def finish(name):
    path, alert, pending = ROUTES[name]
    before = read(OUT / ('hbm_before_' + name + '.json'))
    if not (OUT / ('hbm_before_' + name + '.json')).exists():
        raise RuntimeError('transaction baseline missing')
    candidate_path = ROOT / (pending or path)
    if not candidate_path.exists():
        raise RuntimeError('collector did not produce pending state: ' + name)
    candidate = read(candidate_path)
    if name == 'rubin':
        local = read(ROOT / path)
        if 'ai_component_leadtime' in local:
            candidate['ai_component_leadtime'] = local['ai_component_leadtime']
    write(OUT / ('hbm_candidate_' + name + '.json'), candidate)
    # Working-tree mutations from the old collector are not a committed delivery.
    write(ROOT / path, before)
    text = (ROOT / alert).read_text(encoding='utf-8') if (ROOT / alert).exists() else ''
    guard({'state': candidate, 'text': text})
    receipt = transact(Repository(), path, before, candidate, text)
    write(OUT / (name + '_hbm_delivery_receipt.json'), receipt)
    print(name + '_hbm_delivery_status=' + receipt['status'] + ' message_ids=' + str(receipt.get('message_ids', [])))


def run_collectors():
    """Separate failures: one bad collector cannot prevent another's checkpoint."""
    errors = []
    for name, commands in (
        ('rubin', [['scripts/rubin_hbm_watch.py'], ['scripts/rubin_hbm_pretty.py'], ['scripts/rubin_hbm_leverage.py'], ['scripts/ai_component_leadtime_watch.py']]),
        ('skhynix', [['scripts/skhynix_us_memory_watch.py']]),
        ('samsung', [['scripts/hbm_memory_axes.py']]),
    ):
        try:
            for args in commands:
                if ('pretty' in args[0] or 'leverage' in args[0]) and not (OUT / 'rubin_hbm_alert.md').exists():
                    continue
                subprocess.run(['python', *args], cwd=ROOT, check=True, timeout=440)
            finish(name)
        except Exception as exc:
            # Do not include URL-bearing exception strings in state/log output.
            errors.append(name + ':' + type(exc).__name__)
            path = ROUTES[name][0]
            _, latest = Repository().current(path)
            write(ROOT / path, latest)
    write(OUT / 'hbm_delivery_summary.json', {'checked_at_kst': now(), 'errors': errors})
    if errors:
        raise RuntimeError('HBM routes require review: ' + ','.join(errors))


if __name__ == '__main__':
    OUT.mkdir(exist_ok=True)
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['check', 'begin', 'run'])
    action = p.parse_args().action
    if action == 'check':
        route_check()
    elif action == 'begin':
        begin()
    else:
        run_collectors()
