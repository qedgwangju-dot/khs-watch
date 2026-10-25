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
    def test_official_bok_real_wording_no_retail_cbdc(self):
        scope = watch.cbdc_claim_scope(
            "프로젝트 한강의 기관용 디지털화폐, 일반인용 CBDC와 어떻게 다를까",
            "한국은행은 일반인을 대상으로 CBDC를 도입 또는 발행할 계획이 없고 관련 실험도 진행하지 않는다.",
            BOK,
        )
        self.assertTrue(scope["retail_cbdc_no_plan_statement"])
        self.assertFalse(scope["2030_target_is_issued_money"])

    def test_unrelated_gov_subsidy_not_classed_as_cbdc(self):
        self.assertFalse(watch.document_title_is_relevant(
            "국고보조금 지급사업 추진 일정 변경"
        ))
        self.assertEqual(
            watch.cbdc_claim_scope(
                "국고보조금 지급사업 추진 일정 변경",
                "정부의 일반 보조금 집행 일정",
                "Korea Policy Briefing stablecoin search",
            ), {}
        )

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

    def test_cbdc_alert_title_never_relabels_bank_deposit_as_stablecoin_law(self):
        scope = watch.cbdc_claim_scope(
            "프로젝트 한강 예금토큰 국고금 집행",
            "2030년 국고금 4분의 1 목표, 300억원 보조금 집행",
            BOK,
        )
        title = watch.cbdc_display_title(scope)
        self.assertIn("2030년 25%", title)
        self.assertNotIn("스테이블코인 법안", title)
        self.assertNotIn("182조 발행", title)

    def test_old_official_march_policy_does_not_realert_in_october(self):
        title = "국고보조금 예금토큰 지급 시범사업 공식 시행"
        listing = f'<a href="/portal/bbs/B0000347/view.do?nttId=20260319">{title}</a>'
        detail = official_html(
            title, "2026.03.19",
            "2026년 300억원 EV 충전 보조금 예금토큰 시범. 2030년까지 25% 목표.",
        )
        with patch.object(watch, "fetch_text", return_value=(detail, None)):
            self.assertEqual(watch.parse_links(listing, BOK, URL, NOW), [])


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

    def test_crypto_tax_report_never_counts_as_enacted_law(self):
        now = dt.datetime(2026, 10, 25, 15, 5, tzinfo=ZoneInfo("Asia/Seoul"))
        sedaily = (
            "Presidential Office Decides to Delay Crypto Tax Again. "
            "Published 2026.10.25, presidential office decided to postpone "
            "crypto tax scheduled Jan 2027. CARF from 2029."
        )
        coinness = (
            "October 25, 2026. South Korea presidential office decides to delay "
            "crypto tax again. 2029."
        )
        nts = (
            "가상자산은 소득세법 개정에 따라 '27.1.1. 이후 양도·대여분부터 "
            "기타소득으로 분리과세됩니다."
        )
        a = watch.crypto_tax_report_candidate(sedaily, coinness, nts, now)
        self.assertIsNotNone(a)
        self.assertEqual(a["crypto_tax_stage"], "reported_position_not_enacted")
        self.assertEqual(a["crypto_tax_legal_effective_date"], "2027-01-01")
        self.assertEqual(a["status"], "언론 보도 · 법 개정 전")
        self.assertTrue(a["crypto_tax_guidance_rechecked"])
        self.assertFalse("공포 완료" in a["summary"])
        self.assertIn("2029", a["summary"])
        self.assertIn("2030", a["summary"])
        from khs_policy_alert_explainer import ensure_explained
        ensure_explained(a)
        self.assertIn("통과·공포", a["counter"])
        self.assertNotIn("원화 스테이블코인", a["policy_plain_summary"])

    def test_crypto_tax_report_missing_or_stale_sources_do_not_alert(self):
        now = dt.datetime(2026, 10, 25, 15, 5, tzinfo=ZoneInfo("Asia/Seoul"))
        self.assertIsNone(watch.crypto_tax_report_candidate(
            "<h1>Bitcoin crypto tax presidential office 2029</h1>",
            "", "", now
        ))
        old = dt.datetime(2026, 10, 30, 9, 0, tzinfo=ZoneInfo("Asia/Seoul"))
        valid = (
            "Published 2026.10.25 presidential office delays crypto tax "
            "until 2029. postpone the Jan 2027 tax."
        )
        self.assertIsNone(watch.crypto_tax_report_candidate(valid, None, None, old))

    def test_nts_guidance_changes_only_after_real_date_shift(self):
        now = dt.datetime(2026, 10, 25, 15, 5, tzinfo=ZoneInfo("Asia/Seoul"))
        old = (
            "가상자산은 소득세법 개정('24.12.)에 따라 '27.1.1. "
            "이후 양도·대여분부터 기타소득으로 분리과세됩니다."
        )
        new = (
            "가상자산은 소득세법 개정에 따라 '29.1.1. "
            "이후 양도·대여분부터 기타소득으로 분리과세됩니다."
        )
        self.assertEqual(watch.crypto_tax_guidance_stage(old), "2027-01-01")
        self.assertIsNone(watch.crypto_tax_guidance_update_candidate(old,now))
        changed = watch.crypto_tax_guidance_update_candidate(new,now)
        self.assertIsNotNone(changed)
        self.assertEqual(changed["crypto_tax_stage"], "nts_guidance_changed_2029-01-01")
        self.assertIn("국회·공포 교차확인 전",changed["status"])
        self.assertNotIn("법 개정 확정",changed["status"])

    def test_nts_unrelated_carf_year_does_not_trigger_new_tax_effective_date(self):
        now = dt.datetime(2026,10,25,15,5,tzinfo=ZoneInfo("Asia/Seoul"))
        p = (
            "미국 2029년 CARF 가입 일정 안내. 가상자산 소득세는 "
            "소득세법 개정에 따라 '27.1.1. 이후 양도분부터 분리과세."
        )
        self.assertEqual(watch.crypto_tax_guidance_stage(p),"2027-01-01")
        self.assertIsNone(watch.crypto_tax_guidance_update_candidate(p,now))
        self.assertIsNone(watch.crypto_tax_guidance_update_candidate(
            "국세청 공지: CARF 2029년 참여 일정", now
        ))

    def test_crypto_tax_semantic_key_does_not_duplicate_reprint(self):
        base = {
            "domestic_stablecoin_policy_watch": True,
            "crypto_tax_policy_watch": True,
            "crypto_tax_stage": "reported_position_not_enacted",
            "title": "가상자산 과세 재유예 방향 보도 · 법률 개정 미확정",
        }
        first = {**base, "link": watch.CRYPTO_TAX_PRIMARY_REPORT, "fingerprint": "news1"}
        reprint = {**base, "link": watch.CRYPTO_TAX_SECONDARY_REPORT, "fingerprint": "news2"}
        self.assertEqual(watch.semantic_key(first), watch.semantic_key(reprint))
        self.assertNotEqual(
            watch.semantic_key(first),
            watch.semantic_key({"domestic_stablecoin_policy_watch": True, "title": "프로젝트 한강 국고금"})
        )
        self.assertEqual(len(watch.merge_policy_duplicates([first, reprint])), 1)

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
