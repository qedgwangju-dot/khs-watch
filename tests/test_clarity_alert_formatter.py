import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "clarity_alert_formatter", ROOT / "scripts" / "clarity_alert_formatter.py"
)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class ClarityFormatterTest(unittest.TestCase):
    def test_sec_regulation_crypto_assets_is_korean_clickable_and_investment_specific(self):
        event = {
            "source": "SEC 보도자료",
            "event_type": "SEC·CFTC 공식 규칙·해석·집행지침",
            "title": "SEC Proposes New Regulation Crypto Assets",
            "url": "https://www.sec.gov/newsroom/press-releases/2026-76-sec-proposes-new-regulation-crypto-assets",
            "date": "Tue, 18 Aug 2026 13:15:48 -0400",
            "detail": "The Securities and Exchange Commission today announced that it proposed new rules, titled Regulation Crypto Assets, that would create a clear and fit-for-purpose framework for certain investment contracts involving crypto assets.",
        }
        chunks = MOD.build_chunks([event])
        rendered = "\n".join(chunks)
        self.assertIn("SEC, 암호자산 관련 투자계약", rendered)
        self.assertIn("쉽게 말하면", rendered)
        self.assertIn('<a href="https://www.sec.gov/newsroom/press-releases/2026-76-sec-proposes-new-regulation-crypto-assets">원문</a>', rendered)
        self.assertNotIn("The Securities and Exchange Commission today announced", rendered)
        self.assertIn("<b>핵심 한 줄 요약</b>", rendered)
        self.assertIn("돈 버는 능력·할인율은 개선 방향", rendered)
        self.assertIn("Coinbase", rendered)
        self.assertIn("최대 실패 경로", rendered)
        self.assertNotIn("새 공식 변화가 있을 때만 알리고", rendered)
        self.assertNotIn("링크는 ‘원문’ 글자에 연결합니다", rendered)
        self.assertLessEqual(max(map(len, chunks)), 3900)

    def test_schedule_change_summary_only_marks_timeline_as_changed(self):
        event = {
            "source": "상원 본회의",
            "event_type": "상원 본회의 일정",
            "title": "Senate schedules consideration of H.R. 3633",
            "url": "https://www.senate.gov/",
            "date": "2026-09-14",
            "detail": "The Senate scheduled consideration of H.R. 3633.",
        }
        summary = MOD.core_summary(event)
        self.assertIn("시간표만 가시화", summary)
        self.assertIn("돈 버는 능력은 바뀌지 않았고", summary)
        self.assertIn("표결 연기", summary)


if __name__ == "__main__":
    unittest.main()
