import sys
import types
import unittest
from datetime import date

import pandas as pd

neo4j_stub = types.ModuleType("neo4j")


class _StubGraphDatabase:
    @staticmethod
    def driver(*args, **kwargs):
        raise RuntimeError("Neo4j driver should not be used in unit tests")


neo4j_stub.GraphDatabase = _StubGraphDatabase
neo4j_stub.Driver = object
sys.modules.setdefault("neo4j", neo4j_stub)

from service.graph.derived_feature_calc import DerivedFeatureCalculator


class TestPhase2MultiFrequencyAlignment(unittest.TestCase):
    def test_merge_asof_daily_anchor_uses_backward_fill(self):
        series_map = {
            "DGS10": pd.Series(
                [4.0, 4.1, 4.2],
                index=pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
            ),
            "CPIAUCSL": pd.Series(
                [300.0, 301.0],
                index=pd.to_datetime(["2025-12-31", "2026-01-31"]),
            ),
        }

        merged = DerivedFeatureCalculator.merge_asof_daily_anchor(
            series_by_indicator=series_map,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 3),
        )

        self.assertEqual(len(merged), 3)
        self.assertEqual(merged["CPIAUCSL"].tolist(), [300.0, 300.0, 300.0])
        self.assertEqual(merged["DGS10"].tolist(), [4.0, 4.1, 4.2])

    def test_merge_asof_daily_anchor_keeps_nan_before_first_release(self):
        series_map = {
            "WALCL": pd.Series(
                [8000.0],
                index=pd.to_datetime(["2026-01-05"]),
            )
        }

        merged = DerivedFeatureCalculator.merge_asof_daily_anchor(
            series_by_indicator=series_map,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 6),
        )

        self.assertTrue(pd.isna(merged.loc[0, "WALCL"]))
        self.assertTrue(pd.isna(merged.loc[3, "WALCL"]))
        self.assertEqual(float(merged.loc[4, "WALCL"]), 8000.0)
        self.assertEqual(float(merged.loc[5, "WALCL"]), 8000.0)

    def test_monthly_release_delay_uses_last_published_value_only(self):
        series_map = {
            "KR_HOUSE_PRICE_INDEX": pd.Series(
                [100.0, 101.0, 102.0],
                index=pd.to_datetime(["2025-12-31", "2026-01-31", "2026-02-28"]),
            )
        }

        merged = DerivedFeatureCalculator.merge_asof_daily_anchor(
            series_by_indicator=series_map,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 15),
        )

        self.assertEqual(len(merged), 15)
        self.assertTrue((merged["KR_HOUSE_PRICE_INDEX"] == 101.0).all())
        self.assertNotIn(102.0, merged["KR_HOUSE_PRICE_INDEX"].tolist())


if __name__ == "__main__":
    unittest.main()
