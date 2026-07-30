from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from models import Document
from database import Database
from parsers.currency_parser import convert_to_krw
from parsers.investment_parser import parse_document
from notifier import _telegram_text


class TrackerTests(unittest.TestCase):
    def test_official_named_fund_is_confirmed(self):
        finding = parse_document(Document("official", "u", "Acme SVIC 82호 투자", "2026-07-30", "공동개발", True, 1.0))[0]
        self.assertEqual(finding.related_fund, "SVIC 82호")
        self.assertEqual(finding.fund_confirmation_status, "confirmed")

    def test_unnamed_fund_stays_candidate(self):
        finding = parse_document(Document("official", "u", "Acme Samsung Ventures investment", "2026-07-30", "", True, 1.0))[0]
        self.assertEqual(finding.fund_confirmation_status, "candidate")

    def test_unknown_fx_is_not_invented(self):
        value = convert_to_krw(Decimal("100"), "USD", None, None)
        self.assertIsNone(value.amount_krw)
        self.assertEqual(value.formula, "환율 미확인")

    def test_failure_counter_persists_and_reaches_three(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Database(str(Path(tmp) / "failure.sqlite3"))
            try:
                self.assertEqual([db.source_failed("dart", "down") for _ in range(4)], [1, 2, 3, 4])
                db.source_succeeded("dart")
                self.assertEqual(db.source_failed("dart", "down"), 1)
            finally:
                db.close()

    def test_telegram_message_is_clearly_separated(self):
        text = _telegram_text({
            "type": "svic_finding",
            "company": "Acme",
            "event": "confirmed_investment",
            "summary": "공식 투자 발표",
            "sources": ["https://example.invalid/official"],
        })
        self.assertTrue(text.startswith("🔎 [SVIC 82·83 신규 공식자료]"))
        self.assertIn("https://example.invalid/official", text)

    def test_same_sample_is_silent_on_second_run(self):
        # Some Windows security products briefly retain SQLite handles after a
        # subprocess exits; test assertions remain authoritative in that case.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            env = os.environ | {
                "SVIC_DB_PATH": str(Path(tmp) / "state.sqlite3"),
                "SVIC_OUTPUT_DIR": str(Path(tmp) / "out"),
                "SVIC_RAW_DIR": str(Path(tmp) / "raw"),
            }
            cmd = [sys.executable, "main.py", "--sample", "tests/fixtures/new_documents.json"]
            first = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
            second = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn('"new_alerts": 1', first.stdout)
            self.assertIn('"new_alerts": 0', second.stdout)
            with sqlite3.connect(env["SVIC_DB_PATH"]) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0], 1)
                self.assertIsNotNone(conn.execute("SELECT value FROM meta WHERE key='last_success_at'").fetchone())


if __name__ == "__main__":
    unittest.main()
