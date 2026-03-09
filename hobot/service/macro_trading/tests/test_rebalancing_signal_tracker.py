import unittest

from service.macro_trading.rebalancing.signal_tracker import (
    build_signal_bundle,
    calculate_consecutive_observation_days,
    normalize_sub_mp_payload,
)


class TestRebalancingSignalTracker(unittest.TestCase):
    def test_build_signal_bundle_changes_when_snapshot_composition_changes(self):
        payload = {
            "mp_id": "MP-4",
            "target_allocation": {
                "Stocks": 20.0,
                "Bonds": 50.0,
                "Alternatives": 20.0,
                "Cash": 10.0,
            },
            "sub_mp": {
                "stocks": "Eq-D",
                "bonds": "Bnd-L",
            },
            "sub_mp_details_snapshot": {
                "stocks": {
                    "sub_mp_id": "Eq-D",
                    "etf_details": [
                        {"ticker": "QQQ", "weight": 0.7},
                        {"ticker": "VTV", "weight": 0.3},
                    ],
                },
                "bonds": {
                    "sub_mp_id": "Bnd-L",
                    "etf_details": [
                        {"ticker": "TLT", "weight": 1.0},
                    ],
                },
            },
        }

        changed_payload = {
            **payload,
            "sub_mp_details_snapshot": {
                **payload["sub_mp_details_snapshot"],
                "stocks": {
                    "sub_mp_id": "Eq-D",
                    "etf_details": [
                        {"ticker": "QQQ", "weight": 0.6},
                        {"ticker": "VTV", "weight": 0.4},
                    ],
                },
            },
        }

        baseline = build_signal_bundle(payload)
        changed = build_signal_bundle(changed_payload)

        self.assertNotEqual(
            baseline["sub_mp_signatures"]["stocks"],
            changed["sub_mp_signatures"]["stocks"],
        )
        self.assertNotEqual(
            baseline["effective_target_signature"],
            changed["effective_target_signature"],
        )

    def test_calculate_consecutive_observation_days_counts_latest_streak_only(self):
        rows = [
            {"effective_target_signature_candidate": "sig-a"},
            {"effective_target_signature_candidate": "sig-a"},
            {"effective_target_signature_candidate": "sig-b"},
            {"effective_target_signature_candidate": "sig-a"},
        ]

        consecutive_days = calculate_consecutive_observation_days(rows, "sig-a")

        self.assertEqual(consecutive_days, 2)

    def test_normalize_sub_mp_payload_accepts_legacy_and_normalized_keys(self):
        normalized = normalize_sub_mp_payload(
            {
                "stocks_sub_mp": "Eq-D",
                "bonds": "Bnd-L",
                "alternatives_sub_mp": "Alt-I",
                "cash": "Cash-N",
            }
        )

        self.assertEqual(
            normalized,
            {
                "stocks": "Eq-D",
                "bonds": "Bnd-L",
                "alternatives": "Alt-I",
                "cash": "Cash-N",
            },
        )
