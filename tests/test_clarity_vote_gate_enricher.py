import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("clarity_vote_gate_enricher", ROOT / "scripts" / "clarity_vote_gate_enricher.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class ClarityVoteGateEnricherTest(unittest.TestCase):
    def test_gate_block_is_scan_first_and_no_italics(self):
        block = MOD.build_gate_block({
            "procedure": "H.R.3633 motion to proceed cloture",
            "official_time_kst": "2026-09-16T03:15:00+09:00",
            "votes_required": 60,
            "whip_count_status": "공식 확정표 미공개 — 정당 의석수로 추정하지 않음",
            "final_draft_context": "126건 수정 + 윤리 절충 + community bank 방어장치",
            "main_bottlenecks": ["실제 60표 확보", "stablecoin rewards"],
        })
        self.assertIn("2026년 9월 16일 03:15 KST", block)
        self.assertIn("60표", block)
        self.assertIn("정당 의석수로 추정하지 않음", block)
        self.assertNotIn("<i>", block)
        self.assertNotIn("<em>", block)

    def test_market_context_shows_macro_controls(self):
        block = MOD.build_gate_block({
            "official_time_kst": "2026-09-16T03:15:00+09:00",
            "votes_required": 60,
            "market_reaction": {
                "BTC": {"change_pct": 1.2},
                "COIN": {"change_pct": 3.4},
                "Nasdaq": {"change_pct": 0.5},
                "DXY": {"change_pct": -0.2},
            },
        })
        self.assertIn("표결창 실측 시장 반응", block)
        self.assertIn("원인 분리", block)
        self.assertIn("Nasdaq", block)
        self.assertIn("DXY", block)


if __name__ == "__main__":
    unittest.main()
