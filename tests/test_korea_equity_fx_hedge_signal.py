"""실제 NDF 포지션 미확인 상태에서 주가·환율 동행 경보를 검증한다."""
from __future__ import annotations
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import korea_equity_fx_hedge_signal as s

NOW = dt.datetime.fromisoformat("2026-10-28T11:11:00+09:00")


def valid_data(kospi=5.94, fx=1335.8, prior=1323.7):
    market = {"snapshot": {
        "usdkrw": {
            "date": "2026-10-28", "value": fx,
            "prev_date": "2026-10-27", "prev_value": prior,
            "comparison_valid": True,
        },
        "foreign_flow": {
            "date": "2026-10-28", "daily_eok": 6425,
            "finality": "잠정",
        },
    }}
    sector = {"date": "2026-10-28", "latest": {
        "checked_at": "2026-10-28T11:10:09+09:00",
        "market_phase": "정규장",
        "kospi_pct": kospi,
        "fx": {
            "date": "2026-10-28", "value": fx, "prev_close": prior,
            "comparison_basis": "서울외환시장 15:30 USD/KRW 종가",
            "source": "https://api.stock.naver.com/marketindex/exchange/FX_USDKRW/prices?page=1&pageSize=5",
            "prev_close_source": "https://ksureapi.einfomax.co.kr/v2/datafeed/ksure/fxview?id=20261027154547713",
            "basis_error": None,
        },
    }}
    return market, sector


class VerifiedCrossAssetSignals(unittest.TestCase):
    def test_2026_oct28_stock_and_fx_up_stage2(self):
        market, rotation = valid_data()
        obs, reason = s.validate(market, rotation, NOW)
        self.assertEqual(reason, "검증 완료")
        self.assertEqual(s.classify(obs), ("동반상승", 2))
        self.assertAlmostEqual(obs["fx_change_krw"], 12.1)
        self.assertTrue(s.should_alert({}, obs, ("동반상승", 2)))
        self.assertIn("NDF 순매수·순매도 금액", s.render(obs, ("동반상승", 2)))
        self.assertIn("실제 헤지 여부 미확인", s.render(obs, ("동반상승", 2)))

    def test_stock_down_fx_down_may_be_unwind_but_not_confirmed(self):
        market, rotation = valid_data(kospi=-3.8, fx=1315.5)
        market["snapshot"]["usdkrw"]["value"] = 1315.5
        obs, _ = s.validate(market, rotation, NOW)
        self.assertEqual(s.classify(obs), ("동반하락", 1))
        self.assertIn("실제 거래 미확인", s.render(obs, ("동반하락", 1)))

    def test_normal_inverse_moves_not_novel(self):
        market, rotation = valid_data(kospi=5, fx=1316)
        obs, _ = s.validate(market, rotation, NOW)
        self.assertIsNone(s.classify(obs))

    def test_market_phase_must_be_live(self):
        market, rotation = valid_data()
        rotation["latest"]["market_phase"] = "장마감"
        obs, _ = s.validate(market, rotation, NOW)
        self.assertIsNone(obs)

    def test_missing_prior_close_and_mismatch_fail_closed(self):
        market, rotation = valid_data()
        market["snapshot"]["usdkrw"]["comparison_valid"] = False
        self.assertIsNone(s.validate(market, rotation, NOW)[0])
        market["snapshot"]["usdkrw"]["comparison_valid"] = True
        rotation["latest"]["fx"]["prev_close"] = 1340.0
        self.assertIsNone(s.validate(market, rotation, NOW)[0])

    def test_market_data_age_no_stale(self):
        market, rotation = valid_data()
        rotation["latest"]["checked_at"] = "2026-10-28T09:00:00+09:00"
        self.assertIsNone(s.validate(market, rotation, NOW)[0])

    def test_escalation_and_idempotency(self):
        market, rotation = valid_data()
        obs, _ = s.validate(market, rotation, NOW)
        key2 = s.dedupe_key(obs, ("동반상승", 2))
        old = {"seen_keys": [key2]}
        self.assertFalse(s.should_alert(old, obs, ("동반상승", 2)))
        self.assertFalse(s.should_alert(old, obs, ("동반상승", 1)))
        key1 = s.dedupe_key(obs, ("동반상승", 1))
        self.assertTrue(s.should_alert({"seen_keys": [key1]}, obs, ("동반상승", 2)))

    def test_execution_pending_state_write_once(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p1 = root / "market.json"
            p2 = root / "rotation.json"
            alert = root / "alert.html"
            status = root / "status.md"
            market, rotation = valid_data()
            p1.write_text(json.dumps(market), encoding="utf-8")
            p2.write_text(json.dumps(rotation), encoding="utf-8")
            with patch.object(s, "MARKET_PENDING", p1), patch.object(s, "ROTATION_PENDING", p2), (
                patch.object(s, "ALERT", alert)
            ), patch.object(s, "STATUS", status):
                self.assertTrue(s.run(NOW))
                content = alert.read_text(encoding="utf-8")
                self.assertIn("동반상승", content)
                saved = json.loads(p1.read_text(encoding="utf-8"))
                self.assertEqual(len(saved["equity_fx_hedge_signal"]["seen_keys"]), 1)
                self.assertFalse(saved["equity_fx_hedge_signal"]["last_signal"]["ndf_signed_flow_verified"])
                self.assertFalse(s.run(NOW))
                self.assertEqual(alert.read_text(encoding="utf-8"), content)


if __name__ == "__main__":
    unittest.main()
