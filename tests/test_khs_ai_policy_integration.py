"""Offline contracts across official collectors, policy rendering and receipts.

All persistence is redirected to a temporary directory.  The future actions
below are synthetic regression inputs, not claims about congressional action.
"""

import contextlib
import datetime as dt
import importlib
import io
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from scripts import khs_policy_seen_finalize as finalizer
from scripts import khs_policy_telegram_formatter as formatter
from scripts import khs_trusted_policy_news_watch as host
from tests.test_khs_bis_remote_rule import BODY as BIS_BODY, META as BIS_META

# The host supports direct-script and module imports; patch its actual modules.
ndaa = importlib.import_module(host.collect_ndaa_items.__module__)
bis = importlib.import_module(host.collect_current_bis_items.__module__)
NOW = dt.datetime(2026, 11, 18, 15, tzinfo=ZoneInfo("Asia/Seoul"))
BASELINE = """<h1>Chairmen Mast, Moolenaar, and Crawford Send Second Request to
Jensen Huang and NVIDIA to Brief Congress on the Chinese Intelligence Asset</h1>
<time>November 12, 2026</time><p>This situation is a prime example of why Congress
must immediately pass the AI OVERWATCH Act, Chip Security Act, MATCH Act, and
Remote Access Security Act in the NDAA.</p>"""
FCC_TITLE = "Trump's China data center curb advances despite Amazon, Google, Meta lobbying"
FCC_URL = "https://www.reuters.com/world/trumps-china-data-center-curb-advances-despite-amazon-google-meta-lobbying-2026-11-17/"
FCC_BODY = (
    "WASHINGTON, Nov 17 (Reuters) - The Trump administration plans to press ahead "
    "despite industry lobbying from Amazon, Google and Meta. "
    "The FCC is seeking to ban imports of new models of Chinese optical transceivers. "
    "Counterpoint Research says Chinese firms hold two-thirds of the global optical transceiver market. "
    "Coherent and Lumentum lack the scale to replace Chinese supply."
)


def rasa_status(day="2026-11-16", action="Passed House."):
    return f"""<billStatus><bill><congress>119</congress><type>HR</type>
    <number>2683</number><title>Remote Access Security Act</title>
    <latestAction><actionDate>{day}</actionDate><text>{action}</text></latestAction>
    <actions><item><actionDate>{day}</actionDate><actionCode>H37100</actionCode>
    <sourceSystem><name>House floor actions</name></sourceSystem><text>{action}</text>
    </item></actions></bill></billStatus>"""


def confirmed_delivery(title):
    return {
        "status": "confirmed", "sent": 1, "confirmed_at_kst": NOW.isoformat(),
        "sent_titles": [{"route": "policy", "title": title}],
        "message_ids": [{"route": "policy", "message_id": 123}],
    }


class AiPolicyIntegrationTests(unittest.TestCase):
    def setUp(self):
        # Unexpected live IO must fail immediately, including formatter FX IO.
        self.network = patch("urllib.request.urlopen", side_effect=AssertionError("offline test attempted network"))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.rules = {rule.key: rule for rule in host.STORY_RULES}
        self.ndaa_rule = self.rules[host.NDAA_KEY]
        self.bis_rule = self.rules[host.BIS_GPU_REMOTE_KEY]
        self.fcc_rule = self.rules[host.FCC_OPTICS_RULE]
        self.ndaa_item = ndaa.baseline_item(BASELINE, NOW)
        self.bis_item = bis.make_item(deepcopy(BIS_META), BIS_BODY, NOW, inspection=True)
        raw = '<script type="application/ld+json">' + json.dumps({
            "@type": "NewsArticle", "headline": FCC_TITLE,
            "datePublished": "2026-11-17T11:02:23+00:00", "articleBody": FCC_BODY,
        }) + "</script>"
        self.fcc_item = host.verified_fcc_optics_followup(FCC_URL, FCC_TITLE, raw, NOW)
        self.assertIsNotNone(self.ndaa_item)
        self.assertIsNotNone(self.bis_item)
        self.assertIsNotNone(self.fcc_item)
        self.alerts = [self.alert(rule, item) for rule, item in (
            (self.ndaa_rule, self.ndaa_item), (self.bis_rule, self.bis_item),
            (self.fcc_rule, self.fcc_item),
        )]

    @staticmethod
    def alert(rule, item):
        return {
            "rule": rule, "items": [item],
            "fingerprint": host.story_event_fingerprint(rule, [item]),
            "legacy_fingerprint": host.fingerprint(rule, [item]),
        }

    @contextlib.contextmanager
    def temporary_pipeline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            out, data = root / "out", root / "data"
            out.mkdir()
            data.mkdir()
            paths = {
                "OUT_DIR": out, "DATA_DIR": data,
                "SEEN_PATH": data / "seen.json", "ALERT_PATH": out / "alert.md",
                "TITLE_PATH": out / "title.txt", "ALERTS_JSON_PATH": out / "alerts.json",
                "AI_FORCE_ALERT_PATH": out / "ai.md", "AI_FORCE_TITLE_PATH": out / "ai.txt",
            }
            with patch.multiple(host, **paths), patch.multiple(
                finalizer, TRUSTED_ALERTS_PATH=paths["ALERTS_JSON_PATH"],
                TRUSTED_TITLE_PATH=paths["TITLE_PATH"], TRUSTED_STATE_PATH=paths["SEEN_PATH"],
            ), contextlib.redirect_stdout(io.StringIO()):
                yield paths

    def test_three_families_and_reuters_mirrors_have_independent_event_groups(self):
        keys = [host.semantic_policy_event_key(alert["items"][0]) for alert in self.alerts]
        self.assertEqual(len(set(keys)), 3)
        self.assertIn("package-urged-2026-11-12", keys[0])
        self.assertIn("official-public-inspection-2026-23529", keys[1])
        self.assertEqual(keys[2], host.FCC_OPTICS_FOLLOWUP)
        self.assertEqual(len({alert["fingerprint"] for alert in self.alerts}), 3)
        self.assertEqual(len(host.dedupe_alerts_for_display(self.alerts)), 3)
        for alert in self.alerts:
            with self.subTest(rule=alert["rule"].key):
                mirror = deepcopy(alert["items"][0])
                mirror.update(title="A different publisher headline for the same verified event",
                              source="Same-event mirror", published_kst=NOW.isoformat())
                groups = host.alert_item_groups(alert["rule"], alert["items"] + [mirror])
                self.assertEqual(len(groups), 1)
                self.assertEqual(host.story_event_fingerprint(alert["rule"], [mirror]), alert["fingerprint"])
        fcc_seen = {self.alerts[2]["fingerprint"]: {"key": self.fcc_rule.key}}
        self.assertFalse(host.unseen_items_for_rule(self.fcc_rule, [self.fcc_item], fcc_seen))
        for alert in self.alerts[:2]:
            self.assertEqual(host.unseen_items_for_rule(alert["rule"], alert["items"], fcc_seen), alert["items"])

    def test_mixed_bundle_preserves_stages_and_passes_production_format_validation(self):
        statuses = [host.alert_confirmation_status(alert["rule"], alert["items"])[0] for alert in self.alerts]
        self.assertEqual(statuses, ["공식 확인", "공식 공개열람", "공식 확인 전"])
        profiles = [host.item_story_profile(alert["rule"], alert["items"]) for alert in self.alerts]
        self.assertIn("촉구", profiles[0]["stage"])
        self.assertIn("제정 확인 아님", profiles[0]["stage"])
        self.assertIn("효력 발생 확인 전", profiles[1]["stage"])
        self.assertIsNone(self.bis_item["bis_rule_effective_date"])
        self.assertIn("최종 규칙·발효일은 확인되지 않았습니다", profiles[2]["stage"])
        body = host.render_alert_bundle(self.alerts, NOW)
        self.assertIn("공식 확인·확인 전 혼합 정책 뉴스 3건 확인", body)
        for index, (profile, status) in enumerate(zip(profiles, statuses), 1):
            self.assertIn(f"{index}. [상·{status}] {profile['title']}", body)
        self.assertIn("RASA 제정", body)
        self.assertIn("12,000,000", body)
        self.assertIn("3분의 2", body)
        title, formatted = formatter.format_policy_message("신뢰외신 정책 워치", body, now=NOW)
        self.assertEqual(formatter.validate_final_policy_message(title, formatted), [])
        self.assertTrue(formatter.prepare_telegram_messages(title, formatted))
        # Formatting must preserve the legal-stage caveats, not just fit Telegram.
        for stage in ("제정 확인 아님", "효력 발생 확인 전", "최종 규칙·발효일은 확인되지 않았습니다"):
            self.assertIn(stage, formatted)

    def test_collection_does_not_consume_candidates_and_receipt_commits_only_selected_three(self):
        spec = ndaa.BILL_SPECS[0]
        parsed = ndaa.parse_bill_status(rasa_status(), spec, NOW)
        action, failure = ndaa._action_item(parsed, Mock(side_effect=AssertionError("unexpected body fetch")))
        self.assertIsNone(failure)
        items_by_rule = {
            self.ndaa_rule.key: [action, self.ndaa_item],
            self.bis_rule.key: [self.bis_item], self.fcc_rule.key: [self.fcc_item],
        }
        original = {"untouched-event": {"key": "unrelated-rule", "first_seen_kst": "2026-01-01"}}
        with self.temporary_pipeline() as paths, patch.object(host, "now_kst", return_value=NOW), patch.object(
            host, "STORY_RULES", [self.ndaa_rule, self.bis_rule, self.fcc_rule]
        ), patch.object(host, "collect_rule_items", side_effect=lambda rule, now: deepcopy(items_by_rule[rule.key])):
            paths["SEEN_PATH"].write_text(json.dumps({"seen": original}), encoding="utf-8")
            self.assertEqual(host.main(), 0)
            first = json.loads(paths["ALERTS_JSON_PATH"].read_text(encoding="utf-8"))
            self.assertEqual(len(first), 3)
            selected_keys = {event["fingerprint"] for event in first}
            self.assertEqual(len(selected_keys), 3)
            fourth = self.alerts[2]
            self.assertNotIn(fourth["fingerprint"], selected_keys)
            state = json.loads(paths["SEEN_PATH"].read_text(encoding="utf-8"))
            self.assertEqual(state["seen"], original)
            title = paths["TITLE_PATH"].read_text(encoding="utf-8").strip()
            self.assertIn("외 2건", title)
            finalizer.finalize_confirmed_outbound_alert(confirmed_delivery(title))
            state = json.loads(paths["SEEN_PATH"].read_text(encoding="utf-8"))
            self.assertEqual(set(state["seen"]), set(original) | selected_keys)
            self.assertEqual(state["seen"]["untouched-event"], original["untouched-event"])
            self.assertTrue(host.unseen_items_for_rule(self.fcc_rule, [self.fcc_item], state["seen"]))
            for event in first:
                self.assertEqual(state["seen"][event["fingerprint"]]["first_seen_kst"], NOW.isoformat())
                self.assertFalse(host.unseen_items_for_rule(self.rules[event["key"]], event["items"], state["seen"]))
            # A second collection must still produce the actual fourth event.
            self.assertEqual(host.main(), 0)
            second = json.loads(paths["ALERTS_JSON_PATH"].read_text(encoding="utf-8"))
            self.assertEqual([event["fingerprint"] for event in second], [fourth["fingerprint"]])
            self.assertEqual(json.loads(paths["SEEN_PATH"].read_text(encoding="utf-8"))["seen"], state["seen"])

    def test_receipt_requires_exact_title_policy_route_and_positive_integer_id(self):
        with self.temporary_pipeline() as paths:
            title = "신뢰외신 정책 워치: 검증용 3건"
            paths["TITLE_PATH"].write_text(title + "\n", encoding="utf-8")
            events = [{"key": alert["rule"].key, "title": alert["rule"].title,
                       "fingerprint": alert["fingerprint"], "items": alert["items"]}
                      for alert in self.alerts]
            # Defensive finalizer cap also applies to older four-event artifacts.
            events.append({**events[0], "fingerprint": "undisplayed-fourth-event"})
            paths["ALERTS_JSON_PATH"].write_text(json.dumps(events), encoding="utf-8")
            original = {"seen": {"preserved": {"key": "existing"}}, "updated_at_kst": "unchanged"}
            paths["SEEN_PATH"].write_text(json.dumps(original), encoding="utf-8")
            before = paths["SEEN_PATH"].read_bytes()
            invalid = [
                {"status": "pending"}, {"sent_titles": []},
                {"sent_titles": [{"route": "policy", "title": title + " different"}]},
                {"sent_titles": [{"route": "another-lane", "title": title}]},
                {"message_ids": []},
                {"message_ids": [{"route": "another-lane", "message_id": 123}]},
            ] + [{"message_ids": [{"route": "policy", "message_id": value}]}
                 for value in (None, 0, -1, True, "123", 1.5)]
            for overrides in invalid:
                with self.subTest(receipt=overrides):
                    receipt = confirmed_delivery(title)
                    receipt.update(overrides)
                    finalizer.finalize_confirmed_outbound_alert(receipt)
                    self.assertEqual(paths["SEEN_PATH"].read_bytes(), before)
            finalizer.finalize_confirmed_outbound_alert(confirmed_delivery(title))
            saved = json.loads(paths["SEEN_PATH"].read_text(encoding="utf-8"))
            self.assertEqual(set(saved["seen"]), {"preserved"} | {event["fingerprint"] for event in events[:3]})
            self.assertNotIn(events[3]["fingerprint"], saved["seen"])

    def test_future_or_unavailable_official_ndaa_action_cannot_create_enactment_alert(self):
        spec = ndaa.BILL_SPECS[0]
        for failure_mode in ("future_action", "unavailable"):
            with self.subTest(failure_mode=failure_mode):
                def fetch(url, timeout=8):
                    self.assertEqual(timeout, 8)
                    if url == ndaa.BASELINE_URL:
                        return BASELINE
                    self.assertEqual(url, spec.url)
                    if failure_mode == "unavailable":
                        raise OSError("fixture official source unavailable")
                    return rasa_status("2026-12-25", "Became Public Law No: 119-999.")

                with patch.object(ndaa, "BILL_SPECS", (spec,)), patch.object(host, "fetch_text", side_effect=fetch), patch.object(
                    host, "record_policy_source_failure"
                ) as health, contextlib.redirect_stdout(io.StringIO()):
                    items = host.collect_rule_items(self.ndaa_rule, NOW)
                self.assertEqual([item["ndaa_event_key"] for item in items], ["package-urged-2026-11-12"])
                self.assertEqual(health.call_count, 1)
                self.assertIn("future" if failure_mode == "future_action" else "unavailable", health.call_args.kwargs["error"])
                self.assertIn("제정 확인 아님", host.render_alert(self.ndaa_rule, items, NOW))

    def test_public_inspection_does_not_become_effective_when_scheduled_date_passes(self):
        later = NOW + dt.timedelta(days=4)
        item = bis.make_item(deepcopy(BIS_META), BIS_BODY, later, inspection=True)
        self.assertIsNotNone(item)
        self.assertEqual(host.story_event_fingerprint(self.bis_rule, [item]), self.alerts[1]["fingerprint"])
        self.assertIsNone(item["bis_rule_effective_date"])
        self.assertEqual(host.alert_confirmation_status(self.bis_rule, [item])[0], "공식 공개열람")
        rendered = host.render_alert(self.bis_rule, [item], later)
        self.assertIn("효력 발생 확인 전", rendered)
        self.assertNotIn("효력일 도달 확인", rendered)


if __name__ == "__main__":
    unittest.main()
