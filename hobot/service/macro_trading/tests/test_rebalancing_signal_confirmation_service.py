import unittest
from unittest.mock import patch

from service.macro_trading.rebalancing.signal_confirmation_service import (
    DEFAULT_STRATEGY_PROFILE_ID,
    build_signal_confirmation_assertions,
    extract_signal_confirmation_fixture,
    register_strategy_decision_signal,
)


class TestRebalancingSignalConfirmationService(unittest.TestCase):
    def test_register_strategy_decision_signal_uses_common_tracker_path(self):
        payload = {
            "mp_id": "MP-4",
            "target_allocation": {
                "Stocks": 20.0,
                "Bonds": 50.0,
                "Alternatives": 20.0,
                "Cash": 10.0,
            },
        }

        with patch(
            "service.macro_trading.rebalancing.signal_confirmation_service.track_signal_observation",
            return_value={
                "business_date": "2026-03-10",
                "candidate_status": "PENDING",
                "consecutive_days": 1,
                "effective_target_signature": "sig-1",
                "promoted": False,
            },
        ) as mocked_track:
            result = register_strategy_decision_signal(
                cursor=object(),
                strategy_profile_id="",
                decision_id=11,
                decision_date="2026-03-10T08:35:00",
                target_payload=payload,
            )

        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["strategy_profile_id"], DEFAULT_STRATEGY_PROFILE_ID)
        self.assertEqual(result["decision_id"], 11)

        kwargs = mocked_track.call_args.kwargs
        self.assertEqual(kwargs["strategy_profile_id"], DEFAULT_STRATEGY_PROFILE_ID)
        self.assertEqual(kwargs["target_payload"]["target_allocation"]["stocks"], 20.0)
        self.assertEqual(kwargs["decision_date"].isoformat(), "2026-03-10T08:35:00")

    def test_extract_signal_confirmation_fixture_supports_direct_target_payload(self):
        fixture = {
            "target_payload": {
                "mp_id": "MP-4",
                "target_allocation": {
                    "Stocks": 20.0,
                    "Bonds": 50.0,
                    "Alternatives": 20.0,
                    "Cash": 10.0,
                },
            }
        }

        extracted = extract_signal_confirmation_fixture(fixture)

        self.assertEqual(extracted["target_payload"]["mp_id"], "MP-4")

    def test_build_signal_confirmation_assertions_compares_expected_fields(self):
        fixture = {
            "expected": {
                "signal_confirmation": {
                    "candidate_status": "PENDING",
                    "consecutive_days": 2,
                    "promoted": False,
                }
            }
        }
        result = {
            "candidate_status": "PENDING",
            "consecutive_days": 2,
            "promoted": True,
        }

        assertions = build_signal_confirmation_assertions(
            session_id="session-1",
            business_date="2026-03-10",
            result=result,
            fixture_payload=fixture,
        )

        self.assertEqual(len(assertions), 3)
        self.assertEqual(assertions[0]["status"], "PASSED")
        self.assertEqual(assertions[1]["status"], "PASSED")
        self.assertEqual(assertions[2]["status"], "FAILED")
