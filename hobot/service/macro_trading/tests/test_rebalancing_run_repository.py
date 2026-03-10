import unittest

from service.macro_trading.rebalancing.run_repository import (
    build_daily_sliced_trades,
    calculate_today_slice_quantity,
)


class TestRebalancingRunRepository(unittest.TestCase):
    def test_calculate_today_slice_quantity_uses_ceiling_division(self):
        self.assertEqual(calculate_today_slice_quantity(10, 5), 2)
        self.assertEqual(calculate_today_slice_quantity(9, 5), 2)
        self.assertEqual(calculate_today_slice_quantity(1, 5), 1)

    def test_build_daily_sliced_trades_preserves_action_and_marks_slice_metadata(self):
        sliced = build_daily_sliced_trades(
            [
                {"ticker": "QQQ", "action": "BUY", "quantity": 9, "diff": 9},
                {"ticker": "TLT", "action": "SELL", "quantity": 4, "diff": -4},
            ],
            remaining_execution_days=5,
        )

        self.assertEqual(len(sliced), 2)
        self.assertEqual(sliced[0]["ticker"], "QQQ")
        self.assertEqual(sliced[0]["quantity"], 2)
        self.assertEqual(sliced[0]["diff"], 2)
        self.assertEqual(sliced[0]["planned_total_quantity"], 9)
        self.assertEqual(sliced[1]["ticker"], "TLT")
        self.assertEqual(sliced[1]["quantity"], 1)
        self.assertEqual(sliced[1]["diff"], -1)
        self.assertEqual(sliced[1]["remaining_execution_days"], 5)
