import unittest
from datetime import date, datetime
from unittest.mock import patch

from service.macro_trading.rebalancing import target_retriever


class _FakeCursor:
    def __init__(self, fetchone_results):
        self._fetchone_results = list(fetchone_results)

    def execute(self, *_args, **_kwargs):
        return None

    def fetchone(self):
        if not self._fetchone_results:
            return None
        return self._fetchone_results.pop(0)


class _FakeConnection:
    def __init__(self, fetchone_results):
        self._cursor = _FakeCursor(fetchone_results)

    def cursor(self):
        return self._cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class TestRebalancingTargetRetriever(unittest.TestCase):
    def test_get_current_target_data_prefers_effective_target_snapshot(self):
        effective_row = {
            "target_payload_json": {
                "mp_id": "MP-4",
                "target_allocation": {
                    "Stocks": 20.0,
                    "Bonds": 50.0,
                    "Alternatives": 20.0,
                    "Cash": 10.0,
                },
                "sub_mp": {"stocks": "Eq-D"},
                "sub_mp_details_snapshot": {
                    "stocks": {
                        "sub_mp_id": "Eq-D",
                        "etf_details": [{"ticker": "QQQ", "weight": 1.0}],
                    }
                },
            },
            "effective_from_date": date(2026, 3, 9),
        }

        with patch(
            "service.macro_trading.rebalancing.target_retriever.get_db_connection",
            return_value=_FakeConnection([effective_row]),
        ):
            result = target_retriever.get_current_target_data()

        self.assertEqual(result["mp_target"]["stocks"], 20.0)
        self.assertEqual(
            result["sub_mp_details"]["stocks"]["etf_details"][0]["ticker"],
            "QQQ",
        )
        self.assertEqual(result["decision_date"], date(2026, 3, 9))

    def test_get_current_target_data_falls_back_to_latest_decision_snapshot(self):
        latest_row = {
            "target_allocation": {
                "mp_id": "MP-3",
                "target_allocation": {
                    "Stocks": 30.0,
                    "Bonds": 40.0,
                    "Alternatives": 20.0,
                    "Cash": 10.0,
                },
                "sub_mp": {"bonds": "Bnd-L"},
                "sub_mp_details_snapshot": {
                    "bonds": {
                        "sub_mp_id": "Bnd-L",
                        "etf_details": [{"ticker": "TLT", "weight": 1.0}],
                    }
                },
            },
            "decision_date": datetime(2026, 3, 7, 8, 35, 0),
        }

        with patch(
            "service.macro_trading.rebalancing.target_retriever.get_db_connection",
            return_value=_FakeConnection([None, latest_row]),
        ):
            result = target_retriever.get_current_target_data()

        self.assertEqual(result["mp_target"]["bonds"], 40.0)
        self.assertEqual(
            result["sub_mp_details"]["bonds"]["etf_details"][0]["ticker"],
            "TLT",
        )
        self.assertEqual(result["decision_date"], datetime(2026, 3, 7, 8, 35, 0))
