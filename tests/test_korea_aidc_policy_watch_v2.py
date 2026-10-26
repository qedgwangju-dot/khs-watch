"""AIDC 알림은 기사 발행이 아니라 검증된 정책·사업 상태 변화로 판정한다."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts import korea_aidc_policy_watch as base
from scripts import korea_aidc_policy_watch_v2 as v2


def row(title, *, official=False, url="https://www.mt.co.kr/test", day="Wed, 21 Oct 2026 07:00:00 GMT"):
    return {
        "title": title,
        "publisher": "과학기술정보통신부" if official else "머니투데이",
        "source": "과학기술정보통신부" if official else "국내 주요 언론",
        "official": official,
        "url": url,
        "published": day,
        "category": "AIDC 특별법",
        "stage": 2,
    }


BODY = (
    "인공지능 데이터센터 AIDC 산업의 세액공제 실효성 논란이 제기됐다. "
    "자가 소비 조건에 의해 코로케이션 임대형 사업자가 제외될 수 있다는 산업계 의견이 나왔다. "
    "발표에서는 15% 세액공제를 언급했고, 이는 기업이 요구한 개선안으로 아직 정부가 세법을 바꾼 것은 아니다. "
    "인공지능 데이터센터 시설 인정 기준은 가속기 랙 전력밀도와 냉각 전력, "
    "데이터센터 시설 내 AI 장비 전력 비중을 반영할 가능성이 있다고 설명했다. "
    "업계는 전력 계통 연결 요건과 실제 착공 시점을 함께 개선해야 한다고 주장했다. "
    "또한 사업자는 설계전력과 냉각설비를 갖추고 실제 전원 인가 및 인허가를 확보해야 한다. "
    "정부의 하위법령 제정 단계와 산업계 개선 요청은 서로 다른 상태로 구분해 판단해야 한다. "
)


class AIDCSemanticRegression(unittest.TestCase):
    def test_tax_policy_articles_group_by_topic_not_headline_or_date(self):
        a = row("AIDC 특별법 실효성 논란 세액공제 의미 살펴야")
        b = row("AIDC 세액공제 자가소비 인정 범위 논란",
                day="Thu, 22 Oct 2026 07:00:00 GMT")
        self.assertEqual(v2.semantic_key(a), "aidc|tax-credit|eligibility")
        self.assertEqual(v2.semantic_key(a), v2.semantic_key(b))

    def test_unknown_news_is_not_a_new_policy_event(self):
        a = row("AIDC 산업에 새로운 관심 집중")
        a["event_key"] = v2.semantic_key(a)
        a["article_body"] = BODY
        self.assertEqual(a["event_key"], "aidc|unclassified")
        self.assertEqual(v2.event_level(a), 0)
        self.assertFalse(v2.verify_change(a)[0])
        self.assertNotIn("새로 확인된 변화:", "\n".join(v2.fact_lines(a)[0]))

    def test_article_body_is_required_for_notification(self):
        a = row("AIDC 특별법 세액공제 실효성 논란")
        a["event_key"] = v2.semantic_key(a)
        a["article_body"] = ""
        ok, reason = v2.verify_change(a)
        self.assertFalse(ok)
        self.assertIn("본문", reason)

    def test_industry_tax_request_is_not_automatic_law_change(self):
        a = row("AIDC 특별법 세액공제 실효성 논란")
        a["event_key"] = v2.semantic_key(a)
        a["article_body"] = BODY
        self.assertTrue(v2.verify_change(a)[0])
        self.assertEqual(v2.event_level(a), 20)
        output = v2.render(a)
        self.assertIn("산업계 세제 개선 요구", output)
        self.assertIn("15%", output)
        self.assertIn("정부의 공식 적용대상 변경", output)
        self.assertNotIn("새로 확인된 변화: AIDC", output)

    def test_legal_stage_requires_official_verified_domain(self):
        title = "AIDC 특별법 시행령 확정"
        a = row(title, official=True, url="https://news.google.com/rss/articles/id")
        a["event_key"] = v2.semantic_key(a)
        a["article_body"] = BODY + " 정부는 시행령을 공포했다."
        self.assertFalse(v2.verify_change(a)[0])
        a["url"] = "https://www.msit.go.kr/bbs/view.do?foo=123"
        self.assertTrue(v2.verify_change(a)[0])

    def test_anti_hoarding_requires_actual_numeric_evidence(self):
        a = row("AIDC 알박기 논란 93%가 데이터센터")
        a["event_key"] = v2.semantic_key(a)
        a["article_body"] = BODY
        self.assertFalse(v2.verify_change(a)[0])
        a["article_body"] = BODY + " 신청 67.4GW, 데이터센터 62.8GW, 신청 비중 93%."
        self.assertTrue(v2.verify_change(a)[0])

    def test_timeline_does_not_call_rss_reindex_a_publication(self):
        a = row("AIDC 특별법 하위법령 논의")
        a["event_key"] = "aidc|subordinate-rules-design"
        a["timeline_evidence"] = {
            "published": "2026-09-09T09:00:00+09:00",
            "modified": "2026-09-10T09:00:00+09:00",
            "effective": "2027-03-10T00:00:00+09:00",
            "published_source": "원문 메타정보",
        }
        a["rss_published"] = "Wed, 21 Oct 2026 07:00:00 GMT"
        rendered = v2.render(a)
        self.assertIn("원문 게시일</b>  2026년 9월 9일", rendered)
        self.assertIn("원문 수정일</b>  2026년 9월 10일", rendered)
        self.assertIn("법령 시행일</b>  2027년 3월 10일", rendered)
        self.assertIn("검색 노출일(게시일과 다름)", rendered)
        self.assertNotIn("<b>발표일</b>  2026년 10월 21일", rendered)

    def test_project_plan_does_not_become_automatic_groundbreaking(self):
        a = row("SGC에너지 군산 AIDC 최대 300MW 계획")
        a["event_key"] = v2.semantic_key(a)
        a["article_body"] = BODY + " SGC에너지는 군산에서 1단계 60MW 시설 투자 계획을 발표했다."
        self.assertTrue(v2.verify_change(a)[0])
        new, _, _ = v2.fact_lines(a)
        self.assertIn("계획", new[0])
        self.assertNotIn("착공을 시작점", new[0])

    def test_multiple_verified_events_are_not_marked_sent_in_one_run(self):
        first = row("AIDC 알박기 법 개정 매매 제한")
        second = row("AIDC 알박기 93% 신청물량")
        first["id"] = "first"
        second["id"] = "second"
        mock_session = Mock()
        mock_session.get.return_value.text = "<rss/>"
        mock_session.get.return_value.raise_for_status.return_value = None
        with tempfile.TemporaryDirectory() as td, \
             patch.object(v2, "OUT", Path(td)), \
             patch.object(v2, "ALERT", Path(td) / "alert.txt"), \
             patch.object(v2, "PENDING", Path(td) / "pending.json"), \
             patch.object(v2, "META", Path(td) / "meta.json"), \
             patch.object(v2, "STATUS", Path(td) / "status.md"), \
             patch.object(v2.base, "RSS_SOURCES", (("언론", False, "https://example.com/rss"),)), \
             patch.object(v2, "EXTRA_RSS_SOURCES", ()), \
             patch.object(v2.base, "load_state", return_value={
                 "initialized": True, "dedupe_version": 4,
                 "updated_at": "2026-10-20T09:00:00+00:00", "seen_events": {},
             }), \
             patch.object(v2.requests, "Session", return_value=mock_session), \
             patch.object(v2.base, "parse_rss", return_value=[first, second]), \
             patch.object(v2, "enrich", side_effect=lambda r, sess: {**r, "article_body": BODY}), \
             patch.object(v2, "verify_change", return_value=(True, "verified")):
            self.assertEqual(v2.main(), 0)
            pending = json.loads((Path(td) / "pending.json").read_text(encoding="utf-8"))
            self.assertEqual(pending["eligible_backlog_count"], 1)
            self.assertEqual(len(pending["seen_events"]), 1)
            self.assertTrue((Path(td) / "alert.txt").exists())


    def test_20261023_ecosystem_source_titles_share_one_event(self):
        a = row("AIDC 생태계 지원 방안 발표…인허가 간소화와 2000억원 신규사업")
        b = row("막히던 인허가 한꺼번에…정부 AIDC 규제 완화·2000억원 투입",
                day="Sat, 24 Oct 2026 07:00:00 GMT")
        a["official"] = True
        a["url"] = "https://www.korea.kr/briefing/pressReleaseView.do?newsId=156786291"
        self.assertEqual(v2.semantic_key(a), "aidc|ecosystem-support|government-proposal")
        self.assertEqual(v2.semantic_key(a), v2.semantic_key(b))
        self.assertEqual(v2.event_level(a), v2.event_level(b))
        self.assertEqual(v2.event_level(a), 30)

    def test_ecosystem_policy_requires_full_evidence_and_not_budget_approval(self):
        a = row("인공지능 데이터센터(AIDC) 생태계 지원 방안 발표", official=True,
                url="https://www.korea.kr/briefing/pressReleaseView.do?newsId=156786291")
        a["event_key"] = v2.semantic_key(a)
        a["article_body"] = (
            "2026년 10월 23일 대통령 주재 제2차 규제합리화위원회가 AIDC 인공지능 데이터센터 "
            "생태계 지원방안을 발표하였다. 2027년 정부안으로 2,000억원 신규 국산화 연구개발·실증을 "
            "추진하며 과학기술정보통신부가 인허가 일괄처리와 전담 창구 개선을 추진한다. "
            "2027년 상반기 AIDC 특구 지정을 추진하고 주민 상생계획을 필수요건으로 포함할 예정이다. "
            "전산실·냉각·전력 무인설비 규제 완화를 추진하나 예산안은 아직 국회 최종 확정 단계가 아니다. "
            "AIDC 구축 사업자의 지역 인허가를 간소화하고 국산 소부장 기술의 검증·실증을 도울 계획이다."
        )
        self.assertTrue(v2.verify_change(a)[0])
        news, delta, invest = v2.fact_lines(a)
        self.assertIn("정부 예산안", " ".join(news))
        self.assertIn("전원 인가", " ".join(delta))
        self.assertIn("2,000억원", v2.render(a))

        b = dict(a, article_body="AIDC 사업 지원이 활발하다." * 3)
        self.assertFalse(v2.verify_change(b)[0])

    def test_zone_future_plan_never_equals_real_designation(self):
        a = row("AIDC 특구 지정 계획 발표", official=True,
                url="https://www.korea.kr/briefing/pressReleaseView.do?newsId=156786291")
        a["event_key"] = v2.semantic_key(a)
        a["article_body"] = BODY + " 정부는 2027년 상반기 AIDC 특구를 지정할 예정이다."
        self.assertEqual(a["event_key"], "aidc|special-zone")
        self.assertFalse(v2.verify_change(a)[0])
        a["article_body"] = BODY + " 정부는 전남 지역을 AIDC 특구로 지정했다. 지정 고시를 공표했다."
        self.assertTrue(v2.verify_change(a)[0])

    def test_budget_draft_not_misclassified_as_enacted(self):
        draft = row("AIDC 국산화 2000억 예산안 추진")
        self.assertNotEqual(v2.semantic_key(draft), "aidc|ecosystem-support|budget-enacted")
        enacted = row("AIDC 국산화 2000억 예산 국회 확정", official=True,
                      url="https://www.korea.kr/briefing/pressReleaseView.do?newsId=156786291")
        enacted["event_key"] = v2.semantic_key(enacted)
        enacted["article_body"] = BODY + " 국회 본회의 통과 및 예산 확정으로 AIDC 국산화 사업비 2000억원이 최종 확정됐다."
        self.assertEqual(enacted["event_key"], "aidc|ecosystem-support|budget-enacted")
        self.assertTrue(v2.verify_change(enacted)[0])


if __name__ == "__main__":
    unittest.main()
