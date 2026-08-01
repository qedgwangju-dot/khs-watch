from __future__ import annotations

# 이 파일 변경은 main 병합 시 엔캐리 경보의 1회 연결 시험을 실행한다.
import datetime as dt
import json
import os
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import yen_carry_alert as yca  # noqa: E402


class YenCarryAlertTests(unittest.TestCase):
    def setUp(self) -> None:
        self.current = dt.datetime(2026, 8, 3, 1, 0, tzinfo=dt.timezone.utc)

    def quote(self, spec: yca.SymbolSpec, price: float, change_pct: float, minutes_old: int = 5) -> yca.Quote:
        previous_close = price / (1 + change_pct / 100)
        observed = self.current - dt.timedelta(minutes=minutes_old)
        return yca.Quote(
            symbol=spec.symbol,
            label=spec.label,
            kind=spec.kind,
            price=price,
            previous_close=previous_close,
            change_pct=change_pct,
            timestamp_utc=observed.isoformat().replace("+00:00", "Z"),
            timestamp_epoch=observed.timestamp(),
        )

    def test_thresholds(self) -> None:
        self.assertEqual(yca.determine_stage(154.0, -2.0, -2.0), 1)
        self.assertEqual(yca.determine_stage(152.0, -3.0, -3.0), 2)
        self.assertEqual(yca.determine_stage(153.0, -1.99, -4.0), 0)

    def test_future_fallback(self) -> None:
        cash = self.quote(yca.SYMBOLS["nasdaq_cash"], 25000, -2.2, minutes_old=180)
        future = self.quote(yca.SYMBOLS["nasdaq_future"], 29000, -2.4, minutes_old=5)
        selected = yca.choose_cash_or_future(cash, [future], self.current, 150, 240)
        self.assertIsNotNone(selected)
        self.assertEqual(selected.symbol, "NQ=F")

    def test_alert_entry_and_duplicate_suppression(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = pathlib.Path(temp)
            state_path = temp_path / "state.json"
            original_cwd = pathlib.Path.cwd()
            os.chdir(temp_path)
            try:
                quote_map = {
                    "JPY=X": self.quote(yca.SYMBOLS["usd_jpy"], 153.8, -1.2),
                    "^IXIC": self.quote(yca.SYMBOLS["nasdaq_cash"], 25000, -2.4),
                    "^N225": self.quote(yca.SYMBOLS["nikkei_cash"], 49000, -2.2),
                    "NQ=F": self.quote(yca.SYMBOLS["nasdaq_future"], 29000, -2.5),
                    "NIY=F": self.quote(yca.SYMBOLS["nikkei_future_1"], 49000, -2.3),
                    "NKD=F": self.quote(yca.SYMBOLS["nikkei_future_2"], 49000, -2.3),
                }

                def fetcher(spec: yca.SymbolSpec) -> yca.Quote:
                    return quote_map[spec.symbol]

                first = yca.run(current=self.current, fetcher=fetcher, state_path=state_path)
                self.assertTrue(first["alerted"])
                self.assertTrue(yca.PENDING_STATE_PATH.exists())
                self.assertTrue(yca.ALERT_BODY_PATH.exists())

                self.assertFalse(yca.finalize_state(state_path))
                self.assertFalse(state_path.exists())

                yca.TELEGRAM_CONFIRMED_PATH.write_text("{}\n", encoding="utf-8")
                self.assertTrue(yca.finalize_state(state_path))
                self.assertEqual(json.loads(state_path.read_text(encoding="utf-8"))["stage"], 1)

                second = yca.run(current=self.current + dt.timedelta(minutes=15), fetcher=fetcher, state_path=state_path)
                self.assertFalse(second["alerted"])
            finally:
                os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
