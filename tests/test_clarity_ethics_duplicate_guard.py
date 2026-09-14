import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "clarity_ethics_duplicate_guard", ROOT / "scripts" / "clarity_ethics_duplicate_guard.py"
)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class ClarityEthicsDuplicateGuardTest(unittest.TestCase):
    def test_rediscovered_ethics_breakthrough_is_dropped_after_first_send(self):
        events = [
            {"event_type": "행정부·핵심 당사자 통과 촉구 — 윤리 합의 진전", "title": "same event, different headline"},
            {"event_type": "표결 결과", "title": "new vote"},
        ]
        state = {"seen_signatures": ["already-sent"]}
        kept = MOD.filter_duplicates(events, state)
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["event_type"], "표결 결과")

    def test_first_ethics_breakthrough_is_kept(self):
        events = [{"event_type": "행정부·핵심 당사자 통과 촉구 — 윤리 합의 진전"}]
        self.assertEqual(MOD.filter_duplicates(events, {"seen_signatures": []}), events)


if __name__ == "__main__":
    unittest.main()
