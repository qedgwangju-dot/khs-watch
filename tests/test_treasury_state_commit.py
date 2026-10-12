"""Exercise the exact workflow state step using local bare Git remotes only."""
from pathlib import Path
import json
import os
import shlex
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/treasury-foreign-demand-telegram-alert.yml'
STATE = 'data/treasury_foreign_demand_state.json'


def state_step():
    section = WORKFLOW.read_text().split('      - name: Commit state\n', 1)[1]
    section = section.split('\n      - name:', 1)[0]
    return textwrap.dedent(section.split('        run: |\n', 1)[1])


class TreasuryStateCommitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.remote = self.root/'remote.git'
        self.runner = self.root/'runner'
        self.writer = self.root/'writer'
        self.env = {'PATH': os.environ['PATH'], 'HOME': str(self.root), 'LANG': 'C',
                    'LC_ALL': 'C', 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
                    'GIT_ALLOW_PROTOCOL': 'file', 'GIT_TERMINAL_PROMPT': '0'}
        self.git(self.root, 'init', '--bare', '--initial-branch=main', str(self.remote))
        self.git(self.root, 'clone', str(self.remote), str(self.runner))
        self.identity(self.runner)
        (self.runner/'data').mkdir()
        self.write_state(self.runner, {'last_tic_month': '2026-07', 'last_checked_kst': 'old'})
        (self.runner/'other.json').write_text('{"history":["initial"]}\n')
        self.git(self.runner, 'add', '.')
        self.git(self.runner, 'commit', '-m', 'base')
        self.git(self.runner, 'push', 'origin', 'main')
        self.git(self.root, 'clone', str(self.remote), str(self.writer))
        self.identity(self.writer)
        self.base = self.git(self.runner, 'rev-parse', 'HEAD').stdout.strip()

    def tearDown(self):
        self.temp.cleanup()

    def git(self, cwd, *args, check=True):
        return subprocess.run(['git', *args], cwd=cwd, env=self.env, check=check,
                              capture_output=True, text=True)

    def identity(self, cwd):
        self.git(cwd, 'config', 'user.name', 'offline-test')
        self.git(cwd, 'config', 'user.email', 'offline@example.invalid')

    def write_state(self, cwd, value):
        (cwd/STATE).write_text(json.dumps(value, sort_keys=True)+'\n')

    def origin_file(self, name):
        return self.git(self.remote, 'show', 'main:'+name).stdout

    def run_step(self, prefix=""):
        # Elide only backoff time. Everything else is the exact production shell.
        return subprocess.run(['bash', '--noprofile', '--norc', '-e', '-o', 'pipefail', '-c',
                               'sleep() { :; }\n'+prefix+state_step()], cwd=self.runner, env=self.env,
                              capture_output=True, text=True, timeout=15)

    def race_hook(self, count=1, same_state=False):
        hook = self.runner/'.git/hooks/pre-push'
        target = STATE if same_state else 'other.json'
        value = '{"last_tic_month":"2026-08","last_checked_kst":"remote-newer"}' if same_state else '{"history":["initial","concurrent"]}'
        hook.write_text(f'''#!/bin/bash
set -eu
counter={shlex.quote(str(self.root/'push-count'))}
n=0
if [ -f "$counter" ]; then n=$(cat "$counter"); fi
n=$((n+1)); echo "$n" > "$counter"
if [ "$n" -le {count} ]; then
  git -C {shlex.quote(str(self.writer))} pull --rebase origin main >/dev/null
  printf '%s\\n' {shlex.quote(value)} > {shlex.quote(str(self.writer/target))}
  echo "$n" > {shlex.quote(str(self.writer/'race-counter.txt'))}
  git -C {shlex.quote(str(self.writer))} add -- {shlex.quote(target)} race-counter.txt
  git -C {shlex.quote(str(self.writer))} commit -m "concurrent-$n" >/dev/null
  git -C {shlex.quote(str(self.writer))} push origin main >/dev/null
fi
''')
        hook.chmod(0o755)

    def test_no_change_makes_no_commit_or_push(self):
        self.race_hook()
        result = self.run_step()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git(self.remote, 'rev-parse', 'main').stdout.strip(), self.base)
        self.assertFalse((self.root/'push-count').exists())

    def test_push_race_rebases_single_state_commit_preserving_other_state(self):
        updated = {'last_tic_month':'2026-07', 'last_checked_kst':'local-new'}
        self.write_state(self.runner, updated)
        self.race_hook(count=1)
        result = self.run_step()
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertIn('attempt=2', result.stdout)
        self.assertEqual(json.loads(self.origin_file(STATE)), updated)
        self.assertEqual(json.loads(self.origin_file('other.json'))['history'], ['initial','concurrent'])
        messages = self.git(self.remote, 'log', '--format=%s', 'main').stdout
        self.assertEqual(messages.count('Update Treasury foreign demand state'), 1)
        changes = self.git(self.remote, 'diff-tree', '--no-commit-id', '--name-only', '-r', 'main').stdout.strip()
        self.assertEqual(changes, STATE)

    def test_observed_github_cannot_lock_ref_is_retryable(self):
        self.write_state(self.runner, {'last_tic_month':'2026-07', 'last_checked_kst':'local-new'})
        marker = shlex.quote(str(self.root/'injected-race'))
        prefix = f"""git() {{
          if [ "$1" = push ] && [ ! -f {marker} ]; then
            touch {marker}
            echo " ! [remote rejected] HEAD -> main (cannot lock ref 'refs/heads/main': is at 7e35453 but expected 977cf60)" >&2
            return 1
          fi
          command git "$@"
        }}
"""
        result = self.run_step(prefix)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertIn('attempt=2', result.stdout)
        self.assertEqual(json.loads(self.origin_file(STATE))['last_checked_kst'], 'local-new')
        self.assertEqual(self.git(self.remote,'log','--format=%s','main').stdout.count('Update Treasury foreign demand state'),1)

    def test_same_state_conflict_aborts_without_overwrite_or_resend(self):
        self.write_state(self.runner, {'last_tic_month':'2026-07', 'last_checked_kst':'local-new'})
        self.race_hook(count=1, same_state=True)
        result = self.run_step()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('treasury_state_rebase_failed=true', result.stderr)
        self.assertEqual(json.loads(self.origin_file(STATE))['last_tic_month'], '2026-08')
        self.assertEqual((self.root/'push-count').read_text().strip(), '1')
        self.assertFalse((self.runner/'.git/rebase-merge').exists())
        self.assertEqual(json.loads((self.runner/STATE).read_text())['last_checked_kst'], 'local-new')

    def test_three_races_stop_at_exact_retry_bound(self):
        self.write_state(self.runner, {'last_tic_month':'2026-07', 'last_checked_kst':'local-new'})
        self.race_hook(count=3)
        result = self.run_step()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('treasury_state_push_failed_after_retries=true', result.stderr)
        self.assertEqual((self.root/'push-count').read_text().strip(), '3')
        self.assertEqual(json.loads(self.origin_file(STATE))['last_checked_kst'], 'old')
        self.assertEqual(self.origin_file('race-counter.txt').strip(), '3')

    def test_non_race_failure_not_retried(self):
        self.write_state(self.runner, {'last_tic_month':'2026-07', 'last_checked_kst':'local-new'})
        hook = self.runner/'.git/hooks/pre-push'
        hook.write_text('#!/bin/bash\necho authentication-policy-failure >&2\nexit 1\n')
        hook.chmod(0o755)
        result = self.run_step()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('treasury_state_push_nonretryable=true', result.stderr)
        self.assertEqual(self.git(self.remote, 'rev-parse', 'main').stdout.strip(), self.base)

    def test_unrelated_staged_file_rejected(self):
        self.write_state(self.runner, {'last_checked_kst':'local-new'})
        (self.runner/'unexpected.txt').write_text('do not publish')
        self.git(self.runner,'add','unexpected.txt')
        result = self.run_step()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('contains_unexpected_files', result.stderr)
        self.assertEqual(self.git(self.remote, 'rev-parse', 'main').stdout.strip(), self.base)

    def test_retry_block_cannot_send_or_recollect_and_pr_is_isolated(self):
        step = state_step()
        self.assertNotIn('python', step)
        self.assertNotIn('telegram', step.lower())
        self.assertNotIn('--force', step)
        self.assertNotIn('reset --hard', step)
        workflow = WORKFLOW.read_text()
        self.assertIn('  push:\n    branches: [main]', workflow)
        self.assertIn("github.ref == 'refs/heads/main'", workflow)
        pr = workflow.split('  offline-state-regression:',1)[1].split('  monitor:',1)[0]
        self.assertIn('contents: read', pr)
        self.assertIn('persist-credentials: false', pr)
        self.assertNotIn('secrets.', pr)
        self.assertIn("format('treasury-foreign-demand-pr-{0}'", workflow)


if __name__ == '__main__':
    unittest.main()
