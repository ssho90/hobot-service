import unittest
from datetime import datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_REPLAY_REGRESSION_PATH = Path(__file__).resolve().parents[1] / "replay_regression.py"
_REPLAY_REGRESSION_SPEC = spec_from_file_location("replay_regression_under_test", _REPLAY_REGRESSION_PATH)
assert _REPLAY_REGRESSION_SPEC and _REPLAY_REGRESSION_SPEC.loader
replay_regression = module_from_spec(_REPLAY_REGRESSION_SPEC)
_REPLAY_REGRESSION_SPEC.loader.exec_module(replay_regression)


class TestReplayRegression(unittest.TestCase):
    def test_generate_report_calculates_switch_rates_and_whipsaw(self):
        history_rows = [
            {
                "decision_date": "2025-11-20 09:00:00",
                "target_allocation": {
                    "mp_id": "MP-1",
                    "sub_mp": {"stocks": "Eq-A", "bonds": "Bnd-N", "alternatives": "Alt-I", "cash": "Cash-N"},
                },
            },
            {
                "decision_date": "2025-12-01 09:00:00",
                "target_allocation": {
                    "mp_id": "MP-2",
                    "sub_mp": {
                        "stocks_sub_mp": "Eq-D",
                        "bonds_sub_mp": "Bnd-S",
                        "alternatives_sub_mp": "Alt-C",
                        "cash_sub_mp": "Cash-N",
                    },
                },
            },
            {
                "decision_date": "2025-12-20 09:00:00",
                "target_allocation": {
                    "mp_id": "MP-1",
                    "sub_mp": {
                        "stocks": {"sub_mp_id": "Eq-A"},
                        "bonds": {"sub_mp_id": "Bnd-L"},
                        "alternatives": {"sub_mp_id": "Alt-C"},
                        "cash": {"sub_mp_id": "Cash-N"},
                    },
                },
            },
            {
                "decision_date": "2026-01-15 09:00:00",
                "target_allocation": {
                    "mp_id": "MP-1",
                    "sub_mp": {"stocks": "Eq-A", "bonds": "Bnd-L", "alternatives": "Alt-C", "cash": "Cash-N"},
                },
            },
            {
                "decision_date": "2026-02-01 09:00:00",
                "target_allocation": {
                    "mp_id": "MP-3",
                    "sub_mp": {"stocks": "Eq-N", "bonds": "Bnd-S", "alternatives": "Alt-G", "cash": "Cash-N"},
                },
            },
        ]

        report = replay_regression.generate_historical_replay_report(
            days=90,
            history_rows=history_rows,
            now=datetime(2026, 2, 10, 0, 0, 0),
        )
        metrics = report["metrics"]

        self.assertEqual(metrics["decision_count"], 5)
        self.assertEqual(metrics["mp_change_count"], 3)
        self.assertEqual(metrics["mp_transition_count"], 4)
        self.assertAlmostEqual(metrics["mp_change_rate"], 0.75)
        self.assertEqual(metrics["whipsaw_count"], 1)
        self.assertEqual(metrics["whipsaw_triplet_count"], 3)
        self.assertAlmostEqual(metrics["whipsaw_rate"], 0.3333, places=4)

        self.assertAlmostEqual(metrics["sub_mp_change_rate"]["stocks"], 0.75)
        self.assertAlmostEqual(metrics["sub_mp_change_rate"]["bonds"], 0.75)
        self.assertAlmostEqual(metrics["sub_mp_change_rate"]["alternatives"], 0.5)
        self.assertAlmostEqual(metrics["sub_mp_change_rate"]["cash"], 0.0)
        self.assertAlmostEqual(metrics["overall_sub_mp_change_rate"], 0.5)

    def test_generate_report_handles_single_decision(self):
        history_rows = [
            {
                "decision_date": "2026-02-01 09:00:00",
                "target_allocation": {"mp_id": "MP-3", "sub_mp": {"stocks": "Eq-N"}},
            }
        ]

        report = replay_regression.generate_historical_replay_report(
            days=90,
            history_rows=history_rows,
            now=datetime(2026, 2, 10, 0, 0, 0),
        )
        metrics = report["metrics"]

        self.assertEqual(metrics["decision_count"], 1)
        self.assertEqual(metrics["mp_change_count"], 0)
        self.assertEqual(metrics["mp_transition_count"], 0)
        self.assertEqual(metrics["mp_change_rate"], 0.0)
        self.assertEqual(metrics["whipsaw_count"], 0)
        self.assertEqual(metrics["whipsaw_triplet_count"], 0)
        self.assertEqual(metrics["whipsaw_rate"], 0.0)

    def test_generate_report_filters_out_of_lookback_window(self):
        history_rows = [
            {
                "decision_date": "2025-01-10 09:00:00",
                "target_allocation": {"mp_id": "MP-1", "sub_mp": {"stocks": "Eq-A"}},
            },
            {
                "decision_date": "2026-02-01 09:00:00",
                "target_allocation": {"mp_id": "MP-2", "sub_mp": {"stocks": "Eq-D"}},
            },
        ]

        report = replay_regression.generate_historical_replay_report(
            days=90,
            history_rows=history_rows,
            now=datetime(2026, 2, 10, 0, 0, 0),
        )
        metrics = report["metrics"]

        self.assertEqual(metrics["decision_count"], 1)
        self.assertEqual(report["first_decision_date"], "2026-02-01 09:00:00")
        self.assertEqual(report["last_decision_date"], "2026-02-01 09:00:00")


if __name__ == "__main__":
    unittest.main()
