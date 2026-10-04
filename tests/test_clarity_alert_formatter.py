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

    def test_sec_innovation_exemption_is_specific_and_not_generic(self):
        event = {
            "source": "SEC 보도자료",
            "event_type": "SEC·CFTC 공식 규칙·해석·집행지침",
            "title": "SEC Issues “Innovation Exemption” to Facilitate the Trading of Tokenized NMS Stock and Request for Comment",
            "url": "https://www.sec.gov/newsroom/press-releases/2026-90-sec-issues-innovation-exemption-facilitate-trading-tokenized-nms-stock-request-comment",
            "date": "Thu, 17 Sep 2026 08:55:00 -0400",
            "detail": "The Commission issued temporary, conditional exemptive relief to Tokenized Securities Venues to trade tokenized NMS stock.",
        }
        rendered = "\\n".join(MOD.build_chunks([event]))
        self.assertIn("5년 한시", rendered)
        self.assertIn("합성형 토큰", rendered)
        self.assertIn("Robinhood", rendered)
        self.assertIn("Securitize", rendered)
        self.assertIn("발행회사", rendered)
        self.assertIn("2026년 9월 17일 21:55 KST", rendered)

    def test_sec_crypto_custody_release_and_statements_dedupe_to_one_primary_event(self):
        events = [
            {
                "source": "SEC 발언·성명",
                "event_type": "SEC·CFTC 공식 규칙·해석·집행지침",
                "title": "Roller Coaster Ride: Statement on Proposed Adviser and Regulated Fund Custody Rules; Crypto Custody Rules",
                "url": "https://www.sec.gov/newsroom/speeches-statements/peirce-statement-proposed-amendments-custody-rules-100126",
                "date": "Thu, 01 Oct 2026 15:59:13 -0400",
                "detail": "Commissioner Hester M. Peirce",
            },
            {
                "source": "SEC 발언·성명",
                "event_type": "SEC·CFTC 공식 규칙·해석·집행지침",
                "title": "Statement on Proposal to Address the Custody of Crypto Assets Under the Investment Advisers Act and the Investment Company Act",
                "url": "https://www.sec.gov/newsroom/speeches-statements/atkins-crypto-custody-100126-statement-proposal-address-custody-crypto-assets-under-investment-advisers-act-investment-company",
                "date": "Thu, 01 Oct 2026 16:00:02 -0400",
                "detail": "Chairman Paul S. Atkins",
            },
            {
                "source": "SEC 보도자료",
                "event_type": "SEC·CFTC 공식 규칙·해석·집행지침",
                "title": "SEC Proposal Would Address How Investment Advisers and Funds Can Custody Crypto Assets Under the Federal Securities Laws",
                "url": "https://www.sec.gov/newsroom/press-releases/2026-100-sec-proposal-would-address-how-investment-advisers-funds-can-custody-crypto-assets-under-federal",
                "date": "Thu, 01 Oct 2026 12:16:07 -0400",
                "detail": "The Securities and Exchange Commission today proposed new rules and amendments to provide a tailored framework for the custody of crypto assets for registered investment advisers and regulated funds.",
            },
        ]
        now = dt.datetime(2026, 10, 2, 8, 0, tzinfo=ZoneInfo("America/New_York"))
        filtered = MOD.filter_alertable_events(events, now=now)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["source"], "SEC 보도자료")
        self.assertEqual(filtered[0]["semantic_event"], "sec_crypto_custody_s7_2026_35")
        title, body = MOD.localize_event(filtered[0])
        self.assertIn("암호자산 수탁 규칙 개정안", title)
        self.assertIn("self-custody(자체 수탁)", body)
        self.assertIn("S7-2026-35", body)
        self.assertNotIn("롤러코스터", title)

    def test_custody_federal_register_milestone_uses_exact_comment_deadline(self):
        event = {
            "source": "SEC Federal Register 제안규칙",
            "event_type": "SEC·CFTC 공식 규칙·해석·집행지침",
            "federal_register_type": "Proposed Rule",
            "title": "Adviser and Regulated Fund Custody Rules; Crypto Custody Rules",
            "url": "https://www.federalregister.gov/example",
            "date": "2026-10-05",
            "detail": (
                "SEC custody proposal. Document Number: 2026-99999 | "
                "Publication Date: 2026-10-05 | Comments Close: 2026-12-04"
            ),
        }
        title, body = MOD.localize_event(event)
        self.assertIn("암호자산 수탁 규칙", title)
        self.assertIn("2026-12-04", body)
        self.assertIn("2026-99999", body)

    def test_custody_investment_lines_include_coinbase_and_circle_trust_paths(self):
        event = {
            "source": "SEC 보도자료",
            "event_type": "SEC·CFTC 공식 규칙·해석·집행지침",
            "title": "SEC Proposal Would Address How Investment Advisers and Funds Can Custody Crypto Assets Under the Federal Securities Laws",
            "url": "https://www.sec.gov/example",
            "date": "2026-10-01",
            "detail": "registered investment advisers regulated funds custody crypto assets",
        }
        rendered = "\n".join(MOD.investment_lines(event))
        self.assertIn("Coinbase Custody Trust Company", rendered)
        self.assertIn("Circle Internet Trust Company LLC", rendered)
        self.assertIn("제3자 기관자산 수탁 서비스의 실제 제공·매출 연결은 아직 공식 확인", rendered)

    def test_custody_final_rule_is_not_described_as_proposal(self):
        event = {
            "source": "SEC Federal Register 최종규칙",
            "event_type": "SEC·CFTC 공식 규칙·해석·집행지침",
            "federal_register_type": "Final Rule",
            "title": "Adviser and Regulated Fund Custody Rules; Crypto Custody Rules",
            "url": "https://www.federalregister.gov/final",
            "date": "2027-03-01",
            "detail": "Document Number: 2027-12345 | Publication Date: 2027-03-01 | Effective Date: 2027-04-01",
        }
        title, body = MOD.localize_event(event)
        self.assertIn("최종규칙 확정", title)
        self.assertIn("시행일은 2027-04-01", body)
        self.assertNotIn("개정안 제안", title)
        summary = MOD.core_summary(event)
        self.assertIn("최종 확정", summary)

    def test_sec_3x_btc_eth_etp_approval_is_specific_and_not_spot(self):
        event = {
            "source": "SEC 거래소 규칙 승인명령",
            "event_type": "SEC 거래소 상장·거래 승인",
            "title": "Order Granting Approval of a Proposed Rule Change to List and Trade Shares of the 3x Gold ETF, 3x Silver ETF, 3x Bitcoin ETF, 3x Ether ETF, 3x Crude Oil ETF, and 3x Natural Gas ETF",
            "url": "https://www.sec.gov/files/rules/sro/cboebzx/2026/34-106577.pdf",
            "date": "Oct 2, 2026",
            "detail": "Release No. 34-106577 File No. SR-CboeBZX-2026-065",
        }
        self.assertTrue(MOD.is_sec_3x_crypto_etp_approval(event))
        title, body = MOD.localize_event(event)
        self.assertIn("BITH·ETHK", title)
        self.assertIn("CME 비트코인·이더 선물", body)
        self.assertIn("실제 거래개시는 VS Trust 등록서류 효력", body)
        invest = "\n".join(MOD.investment_lines(event))
        self.assertIn("BITH·ETHK 티커는 VS Trust S-1에서 이미 확인", invest)
        self.assertNotIn("2026-10-18", invest)
        summary = MOD.core_summary(event)
        self.assertIn("현물 BTC·ETH 3배 보유 승인이 아니며", summary)
        self.assertIn("VS Trust 등록서류 효력", summary)

    def test_3x_approval_is_not_misclassified_as_proposed_rule(self):
        event = {
            "source": "SEC 거래소 규칙 승인명령",
            "event_type": "SEC 거래소 상장·거래 승인",
            "title": "Order Granting Approval of a Proposed Rule Change to List and Trade Shares of the 3x Bitcoin ETF and 3x Ether ETF",
            "url": "https://www.sec.gov/example",
            "date": "Oct 2, 2026",
            "detail": "Release No. 34-106577 File No. SR-CboeBZX-2026-065",
        }
        self.assertEqual(MOD.rule_stage(event), "approval_order")

    def test_oira_prerule_classifier_is_boolean_and_does_not_capture_sec_custody(self):
        custody = {
            "source": "SEC 보도자료",
            "event_type": "SEC·CFTC 공식 규칙·해석·집행지침",
            "title": "SEC Proposal Would Address How Investment Advisers and Funds Can Custody Crypto Assets",
            "detail": "registered investment advisers regulated funds custody crypto assets",
        }
        self.assertIs(MOD.is_oira_prerule(custody), False)

    def test_registration_effect_has_distinct_interpretation(self):
        event = {
            "source": "SEC EDGAR — VS Trust",
            "event_type": "3배 BTC·ETH ETP 등록 효력 발생",
            "title": "VS Trust BITH·ETHK registration statement effective",
            "url": "https://www.sec.gov/example",
            "date": "2026-10-05",
            "detail": "Form EFFECT; File No. 333-999999; BITH/ETHK",
        }
        self.assertTrue(MOD.is_vs_trust_3x_registration_effect(event))
        title, body = MOD.localize_event(event)
        self.assertIn("등록서류 효력 발생", title)
        self.assertIn("실제 Cboe 첫 거래", body)
        self.assertEqual(MOD.rule_stage(event), "registration_effective")

    def test_volatility_shares_product_listing_is_distinct_launch_stage(self):
        event = {
            "source": "Volatility Shares 공식 상품목록",
            "event_type": "3배 BTC·ETH ETP 실제 상품목록·거래개시 추적",
            "title": "BITH 3x Bitcoin ETF / ETHK 3x Ether ETF",
            "url": "https://www.volatilityshares.com/etf-product-list.php",
            "date": "2026-10-20",
            "detail": "BITH issuer product page listed; inception 10/20/2026 | ETHK issuer product page listed; inception 10/20/2026",
        }
        self.assertTrue(MOD.is_volatility_3x_crypto_launch(event))
        title, body = MOD.localize_event(event)
        self.assertIn("설정일 확인", title)
        self.assertIn("BITH(3x Bitcoin ETF)", body)
        self.assertIn("ETHK(3x Ether ETF)", body)
        self.assertIn("10/20/2026", body)
        invest = "\n".join(MOD.investment_lines(event))
        self.assertIn("첫 5거래일 AUM", invest)

    def test_sec_3x_crypto_etp_approval_is_specific_and_not_called_trading_live(self):
        event = {
            "source": "SEC 거래소 규칙 승인명령",
            "event_type": "SEC 암호자산 ETP 상장 승인",
            "title": "Order Granting Approval of a Proposed Rule Change to List and Trade Shares of the 3x Gold ETF, 3x Silver ETF, 3x Bitcoin ETF, 3x Ether ETF, 3x Crude Oil ETF, and 3x Natural Gas ETF",
            "url": "https://www.sec.gov/files/rules/sro/cboebzx/2026/34-106577.pdf",
            "date": "2026-10-02",
            "detail": "Release No. 34-106577 | File No. SR-CboeBZX-2026-065",
        }
        title, body = MOD.localize_event(event)
        self.assertIn("3x Bitcoin·3x Ether", title)
        self.assertIn("하루 수익률의 3배", body)
        self.assertIn("즉시 거래를 시작했다는 뜻은 아닙니다", body)
        rendered = "\n".join(MOD.investment_lines(event))
        self.assertIn("2026-10-18", rendered)
        self.assertIn("등록신고서 효력", rendered)
        self.assertIn("복리·변동성", MOD.core_summary(event))

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

    def test_proposed_rule_with_word_adopted_in_background_is_still_proposed(self):
        event = {
            "source": "SEC Federal Register 제안규칙",
            "event_type": "SEC·CFTC 제안규칙",
            "federal_register_type": "Proposed Rule",
            "title": "Digital Asset Proposed Framework",
            "url": "https://www.federalregister.gov/example",
            "date": "2026-09-10",
            "detail": "The Commission proposes a digital asset framework. A related rule was adopted in 2010.",
        }
        rendered = "\n".join(MOD.build_chunks([event]))
        self.assertIn("이 문서는 제안규칙입니다", rendered)
        self.assertNotIn("규칙 초안이 아니라 최종 규칙이 확정", rendered)
        self.assertIn("최종 의무가 확정된 것은 아니며", rendered)
        self.assertIn("의견수렴 뒤 내용이 바뀔 수 있습니다", rendered)

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
