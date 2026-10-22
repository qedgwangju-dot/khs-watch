import datetime as dt
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import khs_domestic_stablecoin_policy_watch as watch


NOW = dt.datetime(2026, 10, 22, 13, 52, tzinfo=ZoneInfo("Asia/Seoul"))
BOK = "Bank of Korea CBDC and deposit-token blog"
URL = "https://www.bok.or.kr/portal/bbs/B0000347/list.do?menuNo=201106"


def official_html(title, date, body):
    return f"<h1>{title}</h1> 등록일 {date} 한국은행 {body}"


class CbdcOfficialPolicyWatch(unittest.TestCase):
    def test_182_trillion_is_math_not_issuance(self):
        title = "프로젝트 한강과 국고금 집행 정책"
        body = (
            "2030년까지 국고금 4분의 1을 디지털화폐로 집행하는 목표. "
            "전기차 충전 보조금 300억원을 예금토큰으로 시범집행. "
            "예금토큰은 보조금 사용처를 지정한다."
        )
        scope = watch.cbdc_claim_scope(title, body, BOK)
        self.assertTrue(scope["2030_treasury_target_25pct"])
        self.assertFalse(scope["182_trillion_is_issuance"])
        self.assertFalse(scope["2030_target_is_issued_money"])
        self.assertTrue(scope["300eok_pilot_amount"])
        self.assertTrue(scope["purpose_restriction_limited_to_program"])
        self.assertFalse(scope["implemented_for_all_citizen_spending"])

    def test_retail_cbdc_non_adoption_stays_separate(self):
        scope = watch.cbdc_claim_scope(
            "프로젝트 한강 일반인용 CBDC와 차이",
            "한국은행은 일반인용 CBDC를 도입 또는 발행할 계획이 없으며 기관용 CBDC와 예금토큰만 시험",
            BOK,
        )
        self.assertTrue(scope["retail_cbdc_no_plan_statement"])
        self.assertFalse(scope["182_trillion_is_issuance"])

    def test_lookalike_sites_and_generic_links_rejected(self):
        self.assertFalse(watch.document_title_is_relevant("파일다운로드"))
        self.assertFalse(watch.document_title_is_relevant("중수청, 본청·6개 지방청으로 출범"))
        self.assertTrue(watch.document_title_is_relevant("프로젝트 한강 2단계 예금토큰 지급결제 확대"))
        self.assertFalse(watch.cbdc_claim_scope("프로젝트 한강", "182조 발행!", "Private blog"))
        html = (
            '<a href="https://evil.bok.or.kr/news">프로젝트 한강 CBDC 공식 발표</a>'
            '<a href="/comm/getFile?x=1">예금토큰 지급결제 보도자료</a>'
        )
        with patch.object(watch, "fetch_text", return_value=(html, None)):
            self.assertEqual(watch.parse_links(html, BOK, URL, NOW), [])

    def test_publication_date_requires_current_original_document(self):
        title = "프로젝트 한강 2단계 예금토큰 지급결제 확대"
        recent = official_html(title, "2026.10.22", "한은은 예금토큰 실거래를 확대한다고 발표했다")
        stale = official_html(title, "2026.03.19", "2030년 국고금 집행 25%를 목표")
        self.assertEqual(watch.official_document_date(title, watch.clean_text(recent)).date(), NOW.date())
        self.assertEqual(watch.official_document_date(title, watch.clean_text(stale)).date(), dt.date(2026,3,19))

    def test_recent_genuine_bok_document_discovered_not_sidebars(self):
        title = "프로젝트 한강 2단계 예금토큰 지급결제 확대"
        listing = f'<a href="/portal/bbs/B0000347/view.do?nttId=99999999">{title}</a>'
        detail = official_html(
            title,
            "2026.10.22",
            "한국은행 프로젝트 한강 예금토큰 실거래 테스트 지급결제 확대를 공식 발표",
        )
        with patch.object(watch, "fetch_text", return_value=(detail, None)):
            actual = watch.parse_links(listing, BOK, URL, NOW)
        self.assertEqual(len(actual), 1)
        self.assertTrue(actual[0]["cbdc_policy_watch"])
        self.assertEqual(actual[0]["published_kst"][:10], "2026-10-22")
        self.assertEqual(actual[0]["importance"], "상") if "상용화" in detail else None

    def test_failed_source_never_becomes_official_event(self):
        title = "프로젝트 한강 예금토큰 결제 변경"
        listing = f'<a href="/portal/bbs/B0000347/view.do?nttId=8">{title}</a>'
        with patch.object(watch, "fetch_text", return_value=(None, "HTTP 403")):
            self.assertEqual(watch.parse_links(listing, BOK, URL, NOW), [])

    def test_different_official_events_not_collapsed(self):
        base = dict(domestic_stablecoin_policy_watch=True, cbdc_policy_watch=True, published_kst=NOW.isoformat())
        a = dict(base, title="공식 문서", original_title="프로젝트 한강 예금토큰 실거래 확대", link="https://www.bok.or.kr/a", fingerprint="a")
        b = dict(base, title="공식 문서", original_title="프로젝트 한강 보조금 결제 범위 변경", link="https://www.bok.or.kr/b", fingerprint="b")
        a_copy = dict(a, link="https://www.fsc.go.kr/c", fingerprint="c")
        self.assertNotEqual(watch.semantic_key(a), watch.semantic_key(b))
        merged = watch.merge_policy_duplicates([a, b, a_copy])
        self.assertEqual(len(merged), 2)
        self.assertEqual(len(merged[0]["source_links"]), 2)


if __name__ == "__main__":
    unittest.main()
