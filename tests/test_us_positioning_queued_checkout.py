"""A queued digest must see the previous run's confirmed delivery state."""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from us_positioning_delivery import daily_digest_due


@unittest.skipUnless(shutil.which("git"), "git is required for the checkout regression")
class QueuedCheckoutTests(unittest.TestCase):
    def test_queued_retry_reads_confirmed_state_from_latest_main(self):
        workflow = (ROOT / ".github/workflows/us-positioning-telegram-watch.yml").read_text(encoding="utf-8")
        checkout = workflow.split("      - name: Checkout\n", 1)[1].split("\n      - name:", 1)[0]
        self.assertRegex(checkout, r"(?m)^\s+ref:\s*main\s*$")
        self.assertRegex(workflow, r"(?m)^\s+cancel-in-progress:\s*false\s*$")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            remote = root / "remote.git"
            writer = root / "writer"
            queued = root / "queued"

            def git(*args, cwd=None):
                return subprocess.run(
                    ["git", *map(str, args)], cwd=cwd, check=True,
                    capture_output=True, text=True,
                ).stdout.strip()

            git("init", "--bare", "--initial-branch=main", remote)
            git("clone", "--quiet", remote, writer)
            git("config", "user.email", "test@example.invalid", cwd=writer)
            git("config", "user.name", "Checkout regression", cwd=writer)
            state_path = writer / "data/us_positioning_state.json"
            state_path.parent.mkdir()
            state_path.write_text(json.dumps({"daily_digest_sent_date_kst": "2026-10-28"}), encoding="utf-8")
            git("add", "data/us_positioning_state.json", cwd=writer)
            git("commit", "--quiet", "-m", "Before scheduled retry", cwd=writer)
            git("push", "--quiet", "origin", "main", cwd=writer)
            event_sha = git("rev-parse", "HEAD", cwd=writer)

            # The first run confirms delivery while the second run is queued.
            state_path.write_text(json.dumps({"daily_digest_sent_date_kst": "2026-10-29"}), encoding="utf-8")
            git("commit", "--quiet", "-am", "Confirmed delivery", cwd=writer)
            git("push", "--quiet", "origin", "main", cwd=writer)
            confirmed_sha = git("rev-parse", "HEAD", cwd=writer)

            git("clone", "--quiet", "--no-checkout", "--branch", "main", remote, queued)
            git("checkout", "--quiet", "--detach", event_sha, cwd=queued)
            event_state = json.loads((queued / "data/us_positioning_state.json").read_text(encoding="utf-8"))
            self.assertTrue(daily_digest_due(event_state, "2026-10-29"))

            # ref: main resolves after the queue and therefore sees that receipt.
            git("checkout", "--quiet", "--detach", "origin/main", cwd=queued)
            self.assertEqual(git("rev-parse", "HEAD", cwd=queued), confirmed_sha)
            confirmed_state = json.loads((queued / "data/us_positioning_state.json").read_text(encoding="utf-8"))
            self.assertFalse(daily_digest_due(confirmed_state, "2026-10-29"))
            self.assertTrue(daily_digest_due(confirmed_state, "2026-10-30"))


if __name__ == "__main__":
    unittest.main()
