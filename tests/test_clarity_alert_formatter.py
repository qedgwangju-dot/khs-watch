import datetime as dt
import importlib.util
import pathlib
import unittest
from zoneinfo import ZoneInfo

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
        self.assertIn("Coinbase", rendered)
        self.assertIn("최대 실패 경로", rendered)
        self.assertIn("공식 날짜(한국시간): 2026년 8월 19일 02:15 KST", rendered)
        self.assertNotIn("Tue, 18 Aug 2026 13:15:48 -0400", rendered)
        self.assertLessEqual(max(map(len, chunks)), 3900)

    def test_date_only_is_shown_in_korean_calendar_format(self):
        event = {
            "source": "상원 은행위원회",
            "event_type": "표결 결과",
            "title": "Chairman Scott, Senate Banking Committee Advance Clarity Act in Historic Bipartisan Vote",
            "url": "https://www.banking.senate.gov/vote",
            "date": "May 14, 2026",
            "detail": "The bill advanced 15-9 and now moves to the Senate floor.",
        }
        rendered = "\n".join(MOD.build_chunks([event]))
        self.assertIn("공식 날짜: 2026년 5월 14일", rendered)
        self.assertNotIn("May 14, 2026", rendered)

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

    def test_old_may_14_rediscovery_is_not_alertable_in_august(self):
        events = [{
            "source": "상원 은행위원회",
            "event_type": "표결 결과",
            "title": "Chairman Scott, Senate Banking Committee Advance Clarity Act in Historic Bipartisan Vote",
            "url": "https://www.banking.senate.gov/example",
            "date": "May 14, 2026",
            "detail": "The bill advanced 15-9.",
        }]
        now = dt.datetime(2026, 8, 22, 9, 0, tzinfo=ZoneInfo("America/New_York"))
        self.assertEqual(MOD.filter_alertable_events(events, now=now), [])

    def test_same_day_markup_and_vote_are_one_event_and_vote_wins(self):
        events = [
            {
                "source": "상원 은행위원회",
                "event_type": "위원회 표결·마크업",
                "title": "Chairman Scott Leads Historic Markup of Digital Asset Market Structure Legislation",
                "url": "https://www.banking.senate.gov/markup",
                "date": "May 14, 2026",
                "detail": "Markup convened.",
            },
            {
                "source": "상원 은행위원회",
                "event_type": "표결 결과",
                "title": "Chairman Scott, Senate Banking Committee Advance Clarity Act in Historic Bipartisan Vote",
                "url": "https://www.banking.senate.gov/vote",
                "date": "May 14, 2026",
                "detail": "The bill advanced 15-9 and now moves to the Senate floor.",
            },
        ]
        now = dt.datetime(2026, 5, 14, 18, 0, tzinfo=ZoneInfo("America/New_York"))
        filtered = MOD.filter_alertable_events(events, now=now)
        self.assertEqual(len(filtered), 1)
        self.assertIn("Bipartisan Vote", filtered[0]["title"])

    def test_warren_remarks_and_security_advisory_are_context_not_vote_events(self):
        events = [
            {
                "source": "상원 은행위원회",
                "event_type": "표결 결과",
                "title": "National Security Advisory: Clarity Act Fails to Address Key Vulnerabilities Exploited by Criminals, Terrorists, and Foreign Adversaries",
                "url": "https://www.banking.senate.gov/advisory",
                "date": "May 14, 2026",
                "detail": "The Committee will debate and vote on the Clarity Act.",
            },
            {
                "source": "상원 은행위원회",
                "event_type": "표결 결과",
                "title": "Senator Warren Opening Remarks at Committee Mark Up of the Clarity Act",
                "url": "https://www.banking.senate.gov/remarks",
                "date": "May 14, 2026",
                "detail": "Opening remarks during markup.",
            },
        ]
        now = dt.datetime(2026, 5, 14, 18, 0, tzinfo=ZoneInfo("America/New_York"))
        self.assertEqual(MOD.filter_alertable_events(events, now=now), [])


if __name__ == "__main__":
    unittest.main()
