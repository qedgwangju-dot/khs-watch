import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import nvidia_exec_signal_watch as w


class NvidiaExecCapitalReturnTests(unittest.TestCase):
    def sample_text(self):
        return (
            "NVIDIA today announced that its Board of Directors has authorized an additional "
            "$150 billion under the company's existing share repurchase program, increasing "
            "the total remaining amount authorized to $235 billion. "
            "The company expects to execute the total remaining program through fiscal year 2028."
        )

    def test_classify_buyback_as_capital_return(self):
        self.assertEqual(w.classify(self.sample_text()), "capital_return")

    def test_extract_current_buyback_numbers(self):
        cap = w.extract_capital_return(self.sample_text())
        self.assertEqual(cap["additional_authorization_usd_b"], 150.0)
        self.assertEqual(cap["remaining_authorization_usd_b"], 235.0)
        self.assertEqual(cap["execution_through_fy"], 2028)
        self.assertIsNone(cap["actual_repurchase_usd_b"])

    def test_authorization_is_not_misread_as_actual_repurchase(self):
        cap = w.extract_capital_return(self.sample_text())
        self.assertIsNone(cap["actual_repurchase_usd_b"])

    def test_fact_key_dedupes_same_buyback_numbers(self):
        a = w.fact_key("capital_return", self.sample_text())
        b = w.fact_key("capital_return", self.sample_text() + " NVIDIA confidence statement.")
        self.assertEqual(a, b)

    def test_partial_republisher_same_total_and_horizon_has_same_fact_key(self):
        full = self.sample_text()
        partial = (
            "NVIDIA increased its share repurchase authorization. "
            "The total remaining amount authorized is $235 billion through fiscal year 2028."
        )
        self.assertEqual(w.fact_key("capital_return", full), w.fact_key("capital_return", partial))

    def test_partial_republisher_does_not_change_known_capital_state(self):
        current = {
            "additional_authorization_usd_b": 150.0,
            "remaining_authorization_usd_b": 235.0,
            "execution_through_fy": 2028,
        }
        cap = w.extract_capital_return(
            "NVIDIA total remaining share repurchase authorization is $235 billion through fiscal year 2028."
        )
        self.assertFalse(w.capital_state_changes(current, cap))

    def test_different_authorization_gets_different_fact_key(self):
        a = w.fact_key("capital_return", self.sample_text())
        b = w.fact_key(
            "capital_return",
            "NVIDIA authorized an additional $160 billion and raised the total remaining amount to $245 billion through fiscal year 2028.",
        )
        self.assertNotEqual(a, b)

    def test_preserve_confirmed_delivery_across_quiet_run(self):
        previous = {
            "last_successful_delivery_kst": "2026-09-28T20:27:56+09:00",
            "telegram_message_id": 159,
            "bot_username": "khs88798879887988798879_bot",
            "delivery_receipt": {"status": "confirmed", "message_id": 159},
        }
        now = w.datetime(2026, 9, 29, 8, 41, tzinfo=w.ZoneInfo("Asia/Seoul"))
        out = w.preserve_runtime_audit({"updated_at_kst": now.isoformat()}, previous, now, event_name="push")
        self.assertEqual(out["telegram_message_id"], 159)
        self.assertEqual(out["last_successful_delivery_kst"], "2026-09-28T20:27:56+09:00")
        self.assertEqual(out["delivery_receipt"]["status"], "confirmed")

    def test_schedule_run_records_gap_without_erasing_delivery(self):
        previous = {
            "last_schedule_check_kst": "2026-09-29T08:26:00+09:00",
            "last_successful_delivery_kst": "2026-09-28T20:27:56+09:00",
            "telegram_message_id": 159,
        }
        now = w.datetime(2026, 9, 29, 8, 41, tzinfo=w.ZoneInfo("Asia/Seoul"))
        out = w.preserve_runtime_audit({}, previous, now, event_name="schedule")
        self.assertEqual(out["last_schedule_check_kst"], "2026-09-29T08:41:00+09:00")
        self.assertEqual(out["schedule_gap_minutes"], 15.0)
        self.assertEqual(out["telegram_message_id"], 159)

    def test_alert_explicitly_separates_authorization_and_execution(self):
        e = {
            "id": "x",
            "kind": "capital_return",
            "fact_key": w.fact_key("capital_return", self.sample_text()),
            "title": "NVIDIA share repurchase authorization increase",
            "description": self.sample_text(),
            "source": "NVIDIA Investor Relations",
            "published_at_kst": "2026-09-28T20:00:00+09:00",
            "direct_link": "https://investor.nvidia.com/",
            "rank": 100,
        }
        out = w.build_alert([e], w.datetime(2026, 9, 28, 20, 0, tzinfo=w.ZoneInfo("Asia/Seoul")))
        self.assertIn("$150 billion", out)
        self.assertIn("$235 billion", out)
        self.assertIn("FY28", out)
        self.assertIn("승인한도는 실제 매입 완료액이 아닙니다", out)
        self.assertIn("$99.3 billion", out)
        self.assertIn("$19.7 billion", out)
        self.assertIn("$39.8 billion", out)


class NvidiaScienceFollowupTests(unittest.TestCase):
    def test_official_science_deployment_is_detected_with_iso_date(self):
        # An actual issuer release (not a syndicated headline) must advance
        # beyond the baseline; old double-escaped date regex dropped it.
        url = "https://nvidianews.nvidia.com/news/nvidia-genesis-mission-quantum-deployment"
        listing = f'<a href="{url}">New issuer release</a>'
        article = (
            '<html><h1>NVIDIA Deploys Quantum Systems for Genesis Mission</h1>'
            '<meta property="article:published_time" content="2026-10-13T12:00:00Z">'
            '<p>NVIDIA quantum Genesis Mission deployment now installed.</p></html>'
        )
        def fake_fetch(target, timeout=18):
            if target == w.OFFICIAL_PRESS_RELEASES:
                return listing.encode("utf-8")
            if target == url:
                return article.encode("utf-8")
            raise OSError("Other issuer source intentionally unavailable")
        with patch.object(w, "fetch", side_effect=fake_fetch):
            events = w._official_science_events()
        matches = [e for e in events if e.get("kind") == "science_execution"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["published_at_kst"][:10], "2026-10-13")
        self.assertEqual(matches[0]["direct_link"], url)


if __name__ == "__main__":
    unittest.main()
