import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import samsung_hbm_watch as s


class HBMTranslationDedupeTests(unittest.TestCase):
    def test_futunn_title_is_rendered_in_korean(self):
        event = {
            "title": "Report: Samsung may double its HBM4/HBM4E production next year, with the product mix rising from 40% to 80%",
            "source": "news.futunn.com",
            "published_at_kst": "2026-09-21T17:20:50+09:00",
            "direct_link": "https://news.futunn.com/example",
        }
        title = s.korean_evidence_title(event, "삼성 HBM 생산능력·증산 계획 변화")
        self.assertIn("삼성전자", title)
        self.assertIn("2배", title)
        self.assertIn("40%", title)
        self.assertIn("80%", title)
        self.assertNotIn("Report:", title)

    def test_republisher_same_capacity_event_has_same_state_signature(self):
        original = {
            "title": "[단독] 삼성전자, 내년 HBM4·4E 생산 2배 늘린다",
            "description": "",
            "source": "sedaily.com",
            "published_at_kst": "2026-09-20T16:33:51+09:00",
        }
        repost = {
            "title": "Report: Samsung may double its HBM4/HBM4E production next year, with the product mix rising from 40% to 80%",
            "description": "",
            "source": "news.futunn.com",
            "published_at_kst": "2026-09-21T17:20:50+09:00",
        }
        key_a, sig_a, _ = s.event_state_descriptor(original)
        key_b, sig_b, _ = s.event_state_descriptor(repost)
        self.assertEqual(key_a, key_b)
        self.assertEqual(sig_a, sig_b)


if __name__ == "__main__":
    unittest.main()
