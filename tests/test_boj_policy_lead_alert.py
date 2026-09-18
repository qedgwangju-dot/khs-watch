import datetime as dt
import sys
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from boj_policy_lead_alert import (
    Item,
    build,
    classify,
    enrich_decision_context,
    extract_rate,
    extract_vote,
    signal_signature,
    should_alert,
    verified_event_signals,
    verified_press_conference_signals,
)

KST = ZoneInfo("Asia/Seoul")


class BojPolicyPathAlertTests(unittest.TestCase):
    def mk(self, title, desc="", source="Reuters", hour=0):
        return Item(
            title=title,
            source=source,
            link="https://example.com",
            published=dt.datetime(2026, 9, 18, 12 + hour, tzinfo=KST),
            description=desc,
        )

    def test_expected_25bp_with_conditional_guidance_stays_yellow(self):
        signal = classify(
            self.mk(
                "BOJ raises interest rates to 1.25% in 25 basis-point move - Reuters",
                "The BOJ said it would continue to raise interest rates if the outlook is realised, "
                "while the timing and pace will depend on economic and price risks. "
                "Financial conditions will remain accommodative.",
            )
        )
        self.assertIsNotNone(signal)
        self.assertEqual(signal.event_type, "decision")
        self.assertEqual(signal.level, 1)
        self.assertAlmostEqual(signal.policy_rate, 1.25)
        self.assertEqual(signal.hike_bp, 25)
        self.assertTrue(signal.further_hikes)
        self.assertTrue(signal.conditional_pace)
        self.assertTrue(signal.accommodative)

    def test_title_only_press_conference_is_suppressed_until_policy_content_arrives(self):
        sparse = classify(
            self.mk(
                "BOJ Governor Ueda's comments at news conference - Reuters",
                "",
                hour=3,
            )
        )
        state = {
            "last_signal_key": "decision-key",
            "last_alert_at_kst": "2026-09-18T13:00:00+09:00",
            "last_published_at_kst": "2026-09-18T12:23:00+09:00",
            "signature": {
                "event_type": "decision",
                "level": 1,
                "policy_rate": 1.25,
                "hike_bp": 25,
            },
        }
        ok, reason = should_alert(
            sparse,
            state,
            dt.datetime(2026, 9, 18, 17, 10, tzinfo=KST),
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "회견 본문 정책경로 확인 전")

    def test_press_conference_layout_is_scan_first_without_empty_unknown_blocks(self):
        signal = verified_press_conference_signals(
            dt.datetime(2026, 9, 18, 17, 20, tzinfo=KST)
        )[0]
        market = {
            "event_time": dt.datetime(2026, 9, 18, 15, 30, tzinfo=KST),
            "usd_jpy_event": {
                "change_pct": 0.4,
                "reference_price": 157.0,
                "latest_price": 157.628,
            },
            "nikkei_event": {
                "change_pct": 0.5,
                "reference_price": 64800.0,
                "latest_price": 65124.0,
            },
            "nasdaq_future_event": {
                "change_pct": 0.3,
                "reference_price": 29800.0,
                "latest_price": 29889.4,
            },
            "usd_jpy": {
                "price": 157.628,
                "m15": 0.1,
                "m30": 0.2,
            },
            "nikkei": {
                "price": 65124.0,
                "change_pct": 1.2,
                "fresh": False,
            },
            "nasdaq_future": {
                "price": 29889.4,
                "change_pct": 0.5,
                "fresh": True,
            },
            "jgb2": {
                "value": 1.868,
                "date": "2026/9/17",
                "change_bp": 1.6,
                "note": "장중 반응 판정에는 사용하지 않음",
            },
        }
        _, body, _ = build(
            signal,
            "정책 가이던스 핵심 문구 변화",
            dt.datetime(2026, 9, 18, 17, 20, tzinfo=KST),
            market,
        )
        self.assertIn("【한눈에 보기】", body)
        self.assertIn("【정책경로】", body)
        self.assertIn("【시장 반응 | 이벤트 이후】", body)
        self.assertIn("직전 결정: 1.00% → 1.25% (+25bp)", body)
        self.assertIn("USD/JPY: +0.40%", body)
        self.assertNotIn("정책 표결: 새 명시적 표결 수치 미확인", body)
        self.assertNotIn("가이던스 체크", body)

    def test_verified_ueta_press_conference_signal_is_complete(self):
        signals = verified_press_conference_signals(
            dt.datetime(2026, 9, 18, 17, 20, tzinfo=KST)
        )
        self.assertEqual(len(signals), 1)
        signal = signals[0]
        self.assertEqual(signal.event_type, "press_conference")
        self.assertEqual(signal.level, 1)
        self.assertTrue(signal.hawkish_tail_50bp)
        self.assertTrue(signal.further_hikes)
        self.assertTrue(signal.conditional_pace)
        self.assertTrue(signal.neutral_rate)
        self.assertTrue(signal.inflation_upside)
        self.assertTrue(signal.stabilize_underlying_around_2)
        self.assertIn("조건부 꼬리위험", signal.note)

    def test_ueta_press_conference_keeps_50bp_as_conditional_tail(self):
        signal = classify(
            self.mk(
                "BOJ Governor Ueda's comments at news conference - Reuters",
                "On 50-bp or back-to-back rate hikes, Ueda said that depends on how price "
                "conditions develop and various possibilities should not be ruled out. "
                "As for the pace of future rate hikes, there is no pre-set idea and the Bank "
                "will determine policy at each policy meeting. The neutral rate is hard to "
                "pinpoint. Underlying inflation is approaching 2% and the Bank wants underlying "
                "inflation to stabilise at 2%.",
                hour=3,
            )
        )
        self.assertEqual(signal.event_type, "press_conference")
        self.assertEqual(signal.level, 1)
        self.assertTrue(signal.hawkish_tail_50bp)
        self.assertTrue(signal.further_hikes)
        self.assertTrue(signal.conditional_pace)
        self.assertTrue(signal.neutral_rate)
        self.assertTrue(signal.stabilize_underlying_around_2)
        self.assertIn("조건부 꼬리위험", signal.note)

    def test_faster_next_meeting_signal_is_orange(self):
        signal = classify(
            self.mk(
                "BOJ Governor Ueda says next meeting could bring another rate hike - Reuters",
                "The central bank may raise rates faster if underlying inflation and upside risks persist.",
            )
        )
        self.assertIsNotNone(signal)
        self.assertEqual(signal.event_type, "press_conference")
        self.assertEqual(signal.level, 2)

    def test_surprise_half_point_is_red(self):
        signal = classify(
            self.mk(
                "BOJ raises policy rate to 1.50% in 50 basis-point move - Reuters",
                "The surprise half-point hike was approved at the policy meeting.",
            )
        )
        self.assertIsNotNone(signal)
        self.assertEqual(signal.level, 3)

    def test_pause_signal_is_green(self):
        signal = classify(
            self.mk(
                "BOJ Governor Ueda says no rush for further rate hike - Reuters",
                "The bank can wait and see before raising rates again.",
            )
        )
        self.assertIsNotNone(signal)
        self.assertEqual(signal.level, 0)

    def test_vote_parser(self):
        self.assertEqual(extract_vote("The decision passed by a 7-2 vote."), (7, 2))
        self.assertEqual(extract_vote("No vote count was provided."), (None, None))

    def test_widely_expected_decision_marks_expected_move(self):
        signal = classify(
            self.mk(
                "BOJ raises interest rates to 1.25% in widely expected 25 basis-point move - Reuters",
                "The quarter-point increase was widely expected.",
            )
        )
        self.assertTrue(signal.expected_move)
        self.assertEqual(signal.level, 1)

    def test_dovish_dissent_direction_is_recorded(self):
        signal = classify(
            self.mk(
                "BOJ raises interest rates to 1.25% in 25 basis-point move - Reuters",
                "The decision passed by a 7-2 vote. Asada and Sato dissented against the hike "
                "and preferred to keep rates unchanged.",
            )
        )
        self.assertEqual(signal.dissent_direction, "hold")
        self.assertEqual(signal.dissenters, ("아사다", "사토"))

    def test_hawkish_dissent_direction_is_recorded(self):
        signal = classify(
            self.mk(
                "BOJ raises interest rates to 1.25% in 25 basis-point move - Reuters",
                "One member called for a 50 basis-point hike and dissented.",
            )
        )
        self.assertEqual(signal.dissent_direction, "larger_hike")

    def test_separate_economic_assessment_vote_requires_same_sentence(self):
        signal = classify(
            self.mk(
                "BOJ raises interest rates to 1.25% in 25 basis-point move - Reuters",
                "The policy decision passed 7-2. The economic assessment passed 7-2 as "
                "members debated whether underlying inflation had already exceeded 2%.",
            )
        )
        self.assertEqual((signal.assessment_vote_for, signal.assessment_vote_against), (7, 2))
        self.assertIn("2%", signal.assessment_view)

    def test_policy_vote_is_not_copied_into_economic_assessment(self):
        signal = classify(
            self.mk(
                "BOJ raises interest rates to 1.25% in 25 basis-point move - Reuters",
                "The decision passed by a 7-2 vote. Underlying inflation is close to 2%.",
            )
        )
        self.assertIsNone(signal.assessment_vote_for)
        self.assertIsNone(signal.assessment_vote_against)

    def test_sparse_current_decision_is_filled_from_verified_event_context(self):
        sparse = classify(
            self.mk(
                "BOJ raises interest rates to 31-year high in widely expected move - Reuters",
                "The move was widely expected.",
                hour=0,
            )
        )
        merged = enrich_decision_context([sparse])[0]
        self.assertAlmostEqual(merged.policy_rate, 1.25)
        self.assertEqual(merged.hike_bp, 25)
        self.assertEqual((merged.vote_for, merged.vote_against), (7, 2))
        self.assertEqual(merged.dissent_direction, "hold")
        self.assertEqual(merged.dissenters, ("아사다", "사토"))
        self.assertTrue(merged.expected_move)
        self.assertTrue(merged.hawkish_tail_50bp)
        self.assertTrue(merged.further_hikes)
        self.assertTrue(merged.conditional_pace)
        self.assertTrue(merged.accommodative)
        self.assertTrue(merged.inflation_upside)
        self.assertTrue(merged.risk_channels)
        self.assertIsNone(merged.assessment_vote_for)
        self.assertIsNone(merged.assessment_vote_against)

    def test_verified_event_fallback_does_not_apply_to_future_meeting(self):
        future = Item(
            title="BOJ raises interest rates in expected move - Reuters",
            source="Reuters",
            link="https://example.com/future",
            published=dt.datetime(2026, 10, 30, 12, 0, tzinfo=KST),
            description="The move was widely expected.",
        )
        signal = classify(future)
        merged = enrich_decision_context([signal])[0]
        self.assertIsNone(merged.policy_rate)
        self.assertIsNone(merged.vote_for)
        self.assertIsNone(merged.dissent_direction)

    def test_decision_context_merges_actual_dissent_but_not_predecision_hawkish_tail(self):
        base = classify(
            self.mk(
                "BOJ raises interest rates in widely expected move - Reuters",
                "The quarter-point move was widely expected.",
                hour=0,
            )
        )
        actual = classify(
            self.mk(
                "BOJ raised interest rates to 1.25% after 7-2 vote - Reuters",
                "Asada and Sato dissented against the hike and preferred to keep rates unchanged. "
                "The move was 25 basis points.",
                hour=1,
            )
        )
        tail = classify(
            self.mk(
                "BOJ faces internal calls for a 50 basis-point hike before policy meeting - Reuters",
                "Some hawkish voices had discussed a half-point move as an upside tail risk.",
                hour=-1,
            )
        )
        merged = [
            x for x in enrich_decision_context([base, actual, tail])
            if x.title == base.title
        ][0]
        self.assertAlmostEqual(merged.policy_rate, 1.25)
        self.assertEqual(merged.hike_bp, 25)
        self.assertEqual((merged.vote_for, merged.vote_against), (7, 2))
        self.assertEqual(merged.dissent_direction, "hold")
        self.assertEqual(merged.dissenters, ("아사다", "사토"))
        self.assertTrue(merged.expected_move)
        self.assertTrue(merged.hawkish_tail_50bp)

    def test_risk_asset_message_is_conditional_for_expected_hike_with_hold_dissent(self):
        signal = classify(
            self.mk(
                "BOJ raises interest rates to 1.25% in widely expected 25 basis-point move - Reuters",
                "The decision passed by a 7-2 vote. Asada and Sato dissented against the hike "
                "and preferred to keep rates unchanged.",
            )
        )
        title, body, _ = build(
            signal,
            "test",
            dt.datetime(2026, 9, 18, 13, 0, tzinfo=KST),
            None,
        )
        self.assertIn("위험자산 의미: 부담 완화 가능", body)
        self.assertIn("USD/JPY · Nikkei 225 · Nasdaq 100 선물 · JGB 2년물 · FX 변동성", body)
        self.assertTrue(title.startswith("🏦"))

    def test_rate_parser(self):
        self.assertEqual(extract_rate("The policy rate was raised to 1.25%."), 1.25)

    def test_event_type_change_realerts(self):
        decision = classify(
            self.mk(
                "BOJ raises interest rates to 1.25% in 25 basis-point move - Reuters",
                "The timing and pace will depend on the outlook.",
            )
        )
        conference = classify(
            self.mk(
                "BOJ Governor Ueda press conference focuses on rate path - Reuters",
                "The timing and pace will depend on the outlook.",
                hour=1,
            )
        )
        state = {
            "last_signal_key": decision.key,
            "last_alert_at_kst": "2026-09-18T12:10:00+09:00",
            "signature": signal_signature(decision),
        }
        ok, reason = should_alert(
            conference,
            state,
            dt.datetime(2026, 9, 18, 13, 5, tzinfo=KST),
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "새 공식 정책 이벤트")

    def test_official_statement_sets_detail_verification_flag(self):
        signal = classify(
            self.mk(
                "Statement on Monetary Policy",
                "The Bank will continue to raise the policy interest rate while examining the "
                "timing and pace. Price pressures have started to spill over into consumer prices.",
                source="Bank of Japan",
            )
        )
        self.assertTrue(signal.official_statement_detail_verified)

    def test_statement_tracks_inflation_regime_shift_and_outlook_dissent(self):
        signal = classify(
            self.mk(
                "Statement on Monetary Policy",
                "The Bank will continue to raise the policy interest rate. The timing and pace "
                "will depend on the outlook. Price pressures have started to spill over into "
                "consumer prices. CPI inflation is expected to be clearly above 2 percent in "
                "the second half of fiscal 2026. It is important to stabilise underlying CPI "
                "inflation at a level around 2 percent. Takata opposed the description regarding "
                "the outlook for prices, and Tamura opposed the description regarding the outlook "
                "for underlying inflation, considering underlying inflation had already reached "
                "the price stability target.",
                source="Bank of Japan",
            )
        )
        self.assertTrue(signal.further_hikes)
        self.assertTrue(signal.conditional_pace)
        self.assertTrue(signal.inflation_spillover)
        self.assertTrue(signal.cpi_h2_clearly_above_2)
        self.assertTrue(signal.stabilize_underlying_around_2)
        self.assertEqual(signal.outlook_dissenters, ("다카타", "다무라"))
        self.assertIn("2% 목표", signal.outlook_dissent_view)

    def test_outlook_wording_dissent_is_separate_from_policy_dissent(self):
        signal = classify(
            self.mk(
                "Statement on Monetary Policy",
                "Takata opposed the description regarding the outlook for prices and Tamura "
                "opposed the description regarding the outlook for underlying inflation. "
                "Underlying inflation had already reached the price stability target.",
                source="Bank of Japan",
            )
        )
        self.assertIsNone(signal.dissent_direction)
        self.assertEqual(signal.dissenters, ("다카타", "다무라"))
        self.assertEqual(signal.outlook_dissenters, ("다카타", "다무라"))

    def test_verified_event_signal_has_complete_current_decision(self):
        signals = verified_event_signals(dt.datetime(2026, 9, 18, 13, 40, tzinfo=KST))
        self.assertEqual(len(signals), 1)
        signal = signals[0]
        self.assertAlmostEqual(signal.policy_rate, 1.25)
        self.assertEqual(signal.hike_bp, 25)
        self.assertEqual((signal.vote_for, signal.vote_against), (7, 2))
        self.assertEqual(signal.dissent_direction, "hold")
        self.assertEqual(signal.dissenters, ("아사다", "사토"))
        self.assertTrue(signal.expected_move)
        self.assertTrue(signal.hawkish_tail_50bp)
        self.assertTrue(signal.inflation_spillover)
        self.assertTrue(signal.cpi_h2_clearly_above_2)
        self.assertTrue(signal.stabilize_underlying_around_2)
        self.assertEqual(signal.outlook_dissenters, ("다카타", "다무라"))

    def test_older_market_path_cannot_roll_back_after_decision(self):
        stale = classify(
            Item(
                title="BOJ set to raise interest rates to 31-year high as inflation risks loom - Reuters",
                source="Reuters",
                link="https://example.com/stale",
                published=dt.datetime(2026, 9, 16, 11, 49, tzinfo=KST),
                description="The BOJ is expected to raise rates.",
            )
        )
        state = {
            "last_signal_key": "latest-decision",
            "last_alert_at_kst": "2026-09-18T13:00:00+09:00",
            "last_published_at_kst": "2026-09-18T12:01:00+09:00",
            "signature": {
                "event_type": "decision",
                "level": 1,
                "policy_rate": 1.25,
                "hike_bp": 25,
            },
        }
        ok, reason = should_alert(
            stale,
            state,
            dt.datetime(2026, 9, 18, 13, 40, tzinfo=KST),
        )
        self.assertFalse(ok)
        self.assertIn("오래된 보도", reason)

    def test_provisional_statement_detail_does_not_alert_before_official_verification(self):
        signal = verified_event_signals(dt.datetime(2026, 9, 18, 14, 0, tzinfo=KST))[0]
        previous = signal_signature(signal)
        previous["outlook_dissenters"] = []
        previous["outlook_dissent_view"] = None
        state = {
            "last_signal_key": "older-provisional-key",
            "last_alert_at_kst": "2026-09-18T13:00:00+09:00",
            "last_published_at_kst": "2026-09-18T12:23:00+09:00",
            "signature": previous,
        }
        ok, reason = should_alert(
            signal,
            state,
            dt.datetime(2026, 9, 18, 14, 0, tzinfo=KST),
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "정책경로 실질 변화 없음")

    def test_official_statement_verification_change_alerts(self):
        official = classify(
            self.mk(
                "Statement on Monetary Policy",
                "The Bank will continue to raise the policy interest rate while examining the "
                "timing and pace. Price pressures have started to spill over into consumer prices.",
                source="Bank of Japan",
            )
        )
        previous = signal_signature(official)
        previous["official_statement_detail_verified"] = False
        state = {
            "last_signal_key": "provisional-key",
            "last_alert_at_kst": "2026-09-18T13:00:00+09:00",
            "last_published_at_kst": official.published.isoformat(),
            "signature": previous,
        }
        ok, reason = should_alert(
            official,
            state,
            dt.datetime(2026, 9, 18, 14, 0, tzinfo=KST),
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "BOJ 공식 성명 상세 검증상태 변화")

    def test_same_key_with_new_official_guidance_is_re_evaluated(self):
        base = classify(
            self.mk(
                "Statement on Monetary Policy",
                "The Bank will continue to raise the policy interest rate. "
                "The timing and pace will depend on economic and price risks. "
                "Financial conditions will remain accommodative.",
                source="Bank of Japan",
            )
        )
        self.assertTrue(base.official_statement_detail_verified)
        previous = signal_signature(base)
        previous["further_hikes"] = False
        previous["conditional_pace"] = False
        previous["accommodative"] = False
        state = {
            "last_signal_key": base.key,
            "last_alert_at_kst": "2026-09-18T13:00:00+09:00",
            "last_published_at_kst": base.published.isoformat(),
            "signature": previous,
        }
        ok, reason = should_alert(
            base,
            state,
            dt.datetime(2026, 9, 18, 14, 0, tzinfo=KST),
        )
        self.assertTrue(ok)
        self.assertIn("가이던스", reason)

    def test_same_signature_is_suppressed_inside_cooldown(self):
        signal = classify(
            self.mk(
                "BOJ raises interest rates to 1.25% in 25 basis-point move - Reuters",
                "The timing and pace will depend on the outlook.",
            )
        )
        state = {
            "last_signal_key": "different-key",
            "last_alert_at_kst": "2026-09-18T12:10:00+09:00",
            "signature": signal_signature(signal),
        }
        ok, reason = should_alert(
            signal,
            state,
            dt.datetime(2026, 9, 18, 13, 0, tzinfo=KST),
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "정책경로 실질 변화 없음")

    def test_official_statement_is_decision(self):
        signal = classify(
            self.mk(
                "Statement on Monetary Policy",
                source="Bank of Japan",
            )
        )
        self.assertIsNotNone(signal)
        self.assertEqual(signal.event_type, "decision")


if __name__ == "__main__":
    unittest.main()
