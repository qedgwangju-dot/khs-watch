from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import yen_carry_alert_enrich as enrich  # noqa: E402
import yen_sector_reaction as reaction  # noqa: E402


class YenCarryAlertEnrichTests(unittest.TestCase):
    def test_calculate_24h_change_and_range(self) -> None:
        start = 1_800_000_000
        timestamps = [start, start + 43_200, start + 86_400]
        closes = [160.0, 157.0, 156.0]
        payload = {
            "chart": {
                "result": [
                    {
                        "timestamp": timestamps,
                        "indicators": {"quote": [{"close": closes}]},
                    }
                ]
            }
        }
        change_pct, low, high, span = enrich.calculate_24h(payload)
        self.assertAlmostEqual(change_pct, -2.5)
        self.assertEqual(low, 156.0)
        self.assertEqual(high, 160.0)
        self.assertEqual(span, 4.0)

    def test_insert_line_after_usd_jpy(self) -> None:
        body = (
            "조회 시각: 2026-08-02 00:00:00 KST\n"
            "USD/JPY: 156.000 (-1.00%)\n"
            "Nasdaq: -2.00%\n"
        )
        line = (
            "USD/JPY 24시간: -2.50% · 저가 156.000 · "
            "고가 160.000 · 범위 4.000엔"
        )
        result = enrich.insert_line(body, line)
        lines = result.splitlines()
        self.assertEqual(lines[2], line)

    def test_fast_alert_marks_sector_effect_as_short_term(self) -> None:
        block = enrich.sector_impact_block(
            {"stage": 1, "fast_stage": 1, "sustained_stage": 0}
        )
        self.assertIn("급변 직후 영향", block)
        self.assertIn("실제 실적 영향은 엔고의 지속 여부", block)
        self.assertIn("일본 부담: 자동차·전자·기계", block)
        self.assertIn("한국 반도체: 직접 영향 제한적", block)

    def test_sustained_alert_marks_profit_effect_as_more_relevant(self) -> None:
        block = enrich.sector_impact_block(
            {"stage": 2, "fast_stage": 0, "sustained_stage": 2}
        )
        self.assertIn("판정 강도: 강함", block)
        self.assertIn("지속 엔고 영향", block)
        self.assertIn("매출 환산·수입 원가", block)
        self.assertIn("전력·항공·유통·식품", block)

    def test_insert_sector_block_is_idempotent_and_before_disclaimer(self) -> None:
        body = (
            "조회 시각: 2026-08-03 18:00:00 KST\n"
            "최종 판정: 1단계\n\n"
            f"{enrich.FINAL_MARKER}\n"
        )
        block = enrich.sector_impact_block(
            {"stage": 1, "fast_stage": 1, "sustained_stage": 0}
        )
        first = enrich.insert_sector_block(body, block)
        second = enrich.insert_sector_block(first, block)
        self.assertEqual(first, second)
        self.assertEqual(second.count(enrich.SECTOR_HEADING), 1)
        self.assertLess(
            second.index(enrich.SECTOR_HEADING),
            second.index(enrich.FINAL_MARKER),
        )


class YenSectorReactionTests(unittest.TestCase):
    def result(
        self,
        key: str,
        relative: float,
        *,
        expected: int = 1,
        significant: bool = True,
        status: str = "장중",
    ) -> reaction.SectorResult:
        aligned = significant and expected != 0 and relative * expected > 0
        contrary = significant and expected != 0 and relative * expected < 0
        return reaction.SectorResult(
            key=key,
            name=key,
            country="JP",
            role="role",
            expected_sign=expected,
            timeframe="30분",
            sector_change_pct=relative + 0.2,
            benchmark_change_pct=0.2,
            relative_pct=relative,
            sigma_pct=0.2,
            zscore=relative / 0.2,
            significant=significant,
            aligned=aligned if expected else None,
            contrary=contrary if expected else None,
            breadth_pct=66.7,
            market_status=status,
            data_epoch=1_785_700_000.0,
            component_prices={"X": 100.0},
            benchmark_price=100.0,
            source="test",
        )

    def patch_paths(self, root: pathlib.Path) -> dict[str, pathlib.Path]:
        paths = {
            "FX_ALERT_TITLE": root / "out/title.txt",
            "FX_ALERT_JSON": root / "out/fx.json",
            "FX_ALERT_BODY": root / "out/fx.md",
            "FX_STATE_PATH": root / "data/state.json",
            "FX_PENDING_STATE_PATH": root / "out/pending.json",
            "FX_SUMMARY_PATH": root / "out/summary.md",
        }
        patchers = [mock.patch.object(reaction, name, value) for name, value in paths.items()]
        for patcher in patchers:
            patcher.start()
        self.addCleanup(lambda: [patcher.stop() for patcher in reversed(patchers)])
        return paths

    def test_confidence_requires_broad_confirmation(self) -> None:
        aligned = [
            self.result("a", 1.0),
            self.result("b", 0.9),
            self.result("c", -1.1, expected=-1),
        ]
        self.assertEqual(reaction.confidence_label(aligned), "높음")
        mixed = aligned[:2] + [self.result("d", -1.0, expected=1)]
        self.assertEqual(reaction.confidence_label(mixed), "혼재")
        self.assertEqual(reaction.confidence_label(aligned[:1]), "미확인")

    def test_observed_block_uses_market_relative_return(self) -> None:
        block = reaction.observed_sector_block(
            [self.result("일본 자동차", -1.2, expected=-1)],
            {},
        )
        self.assertIn("TOPIX·KOSPI", block)
        self.assertIn("상대 -1.20%p", block)
        self.assertIn("예상 방향 확인", block)
        self.assertIn("환율이 유일한 원인", block)

    def test_replacement_is_idempotent(self) -> None:
        body = (
            "조회 시각: now\n\n산업·업종 영향\n기존 설명\n\n"
            + reaction.FINAL_MARKER
            + "\n"
        )
        block = "산업·업종 영향\n실제 반응"
        first = reaction.replace_sector_block(body, block)
        second = reaction.replace_sector_block(first, block)
        self.assertEqual(first, second)
        self.assertEqual(first.count(reaction.SECTOR_HEADING), 1)

    def test_new_event_arms_followups_only_while_market_is_open(self) -> None:
        current = dt.datetime(2026, 8, 3, 1, 0, tzinfo=dt.timezone.utc)
        fx = {
            "stage": 1,
            "checked_at_kst": "2026-08-03T10:00:00+09:00",
            "move": {"latest_price": 155.0},
        }
        event = reaction.new_event(
            fx,
            [self.result("jp_auto", -1.0, expected=-1, status="장중")],
            current,
        )
        self.assertFalse(event["thirty_done"])
        self.assertFalse(event["close_done"])

        closed = reaction.new_event(
            {**fx, "checked_at_kst": "2026-08-03T19:00:00+09:00"},
            [self.result("jp_auto", -1.0, expected=-1, status="종가")],
            dt.datetime(2026, 8, 3, 10, 0, tzinfo=dt.timezone.utc),
        )
        self.assertTrue(closed["thirty_done"])
        self.assertTrue(closed["close_done"])

    def test_immediate_measurement_is_added_to_existing_fx_pending_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            paths = self.patch_paths(root)
            paths["FX_ALERT_JSON"].parent.mkdir(parents=True, exist_ok=True)
            paths["FX_ALERT_JSON"].write_text(
                json.dumps(
                    {
                        "stage": 1,
                        "checked_at_kst": "2026-08-03T10:00:00+09:00",
                        "move": {"latest_price": 155.0},
                    }
                ),
                encoding="utf-8",
            )
            paths["FX_ALERT_BODY"].write_text(
                "조회 시각: now\n\n산업·업종 영향\n기존\n\n"
                + reaction.FINAL_MARKER
                + "\n",
                encoding="utf-8",
            )
            paths["FX_PENDING_STATE_PATH"].write_text(
                json.dumps({"stage": 1, "last_alert_price": 155.0}),
                encoding="utf-8",
            )
            results = [self.result("jp_auto", -1.0, expected=-1)]
            with mock.patch.object(
                reaction,
                "capture_snapshot",
                return_value=(results, {}, {}),
            ):
                output = reaction.process(
                    dt.datetime(2026, 8, 3, 1, 0, tzinfo=dt.timezone.utc)
                )
            self.assertEqual(output["mode"], "new_fx_alert")
            pending = json.loads(
                paths["FX_PENDING_STATE_PATH"].read_text(encoding="utf-8")
            )
            self.assertEqual(pending["stage"], 1)
            self.assertIn("sector_reaction", pending)
            self.assertIn(
                "실제 업종 반응",
                paths["FX_ALERT_BODY"].read_text(encoding="utf-8"),
            )

    def test_completed_followup_archives_learning_case(self) -> None:
        state = {
            "sector_reaction": {
                "event_id": "x",
                "thirty_done": True,
                "close_done": True,
            },
            "sector_reaction_history": [],
        }
        archived = reaction.archive_if_complete(state)
        self.assertIsNone(archived["sector_reaction"])
        self.assertEqual(
            archived["sector_reaction_history"][0]["status"],
            "completed",
        )


if __name__ == "__main__":
    unittest.main()
