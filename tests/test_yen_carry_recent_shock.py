import unittest

from yen_carry_recent_shock import calculate


class RecentShockTests(unittest.TestCase):
    def points(self, prices, step=300.0):
        start = 1_800_000_000.0 - (len(prices) - 1) * step
        return [(start + i * step, float(px)) for i, px in enumerate(prices)]

    def test_current_shock_when_fast_drop_is_still_running(self):
        # Last 15 minutes fall about 1%, so this must remain a current/orange shock.
        prices = [100.4] * 15 + [100.2, 100.0, 99.6, 99.2]
        snap = calculate(self.points(prices))
        self.assertTrue(snap.current_shock)
        self.assertFalse(snap.recent_shock)

    def test_recent_shock_survives_partial_rebound(self):
        # Shock: 100 -> 98.8 (-1.2%), then partial rebound to 99.2.
        prices = [99.8, 100.0, 99.9, 99.7, 99.4, 99.0, 98.8, 98.9, 99.0, 99.1, 99.2,
                  99.2, 99.2, 99.2, 99.2, 99.2, 99.2, 99.2, 99.2]
        snap = calculate(self.points(prices))
        self.assertFalse(snap.current_shock)
        self.assertTrue(snap.recent_shock)
        self.assertLessEqual(snap.max_drawdown_pct, -1.0)
        self.assertGreater(snap.current_rebound_pct, 0.2)
        self.assertLessEqual(snap.current_vs_peak_pct, -0.5)

    def test_recent_shock_clears_after_most_of_move_is_recovered(self):
        prices = [99.8, 100.0, 99.9, 99.6, 99.2, 98.8, 98.9, 99.1, 99.3, 99.5, 99.7,
                  99.7, 99.7, 99.7, 99.7, 99.7, 99.7, 99.7, 99.7]
        snap = calculate(self.points(prices))
        self.assertFalse(snap.current_shock)
        self.assertFalse(snap.recent_shock)

    def test_old_shock_outside_90_minutes_is_ignored(self):
        # Early shock is outside the final 90-minute window.
        prices = [100.0, 98.7, 99.0, 99.4, 99.6, 99.8, 99.9, 100.0, 100.0, 100.0,
                  100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0,
                  100.0, 100.0, 100.0, 100.0]
        snap = calculate(self.points(prices))
        self.assertFalse(snap.current_shock)
        self.assertFalse(snap.recent_shock)


if __name__ == "__main__":
    unittest.main()
