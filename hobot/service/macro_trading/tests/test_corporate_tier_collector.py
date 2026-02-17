import unittest
from datetime import date

from service.macro_trading.collectors.corporate_tier_collector import (
    CorporateTierCollector,
    DEFAULT_TIER_SOURCE_KR,
)


class TestCorporateTierCollector(unittest.TestCase):
    def test_build_tier_rows_normalizes_payload(self):
        rows = CorporateTierCollector.build_tier_rows(
            as_of_date=date(2026, 2, 17),
            source_rows=[
                {
                    "country_code": "KR",
                    "market": "KOSPI",
                    "symbol": "005930",
                    "company_name": "삼성전자",
                    "corp_code": "00126380",
                    "membership_rank": 1,
                    "snapshot_date": date(2026, 2, 1),
                    "source_metadata": {"foo": "bar"},
                }
            ],
            tier_level=1,
            tier_source=DEFAULT_TIER_SOURCE_KR,
        )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["country_code"], "KR")
        self.assertEqual(row["symbol"], "005930")
        self.assertEqual(row["tier_level"], 1)
        self.assertEqual(row["tier_label"], "tier1")
        self.assertEqual(row["tier_source"], DEFAULT_TIER_SOURCE_KR)
        self.assertEqual(row["membership_rank"], 1)
        self.assertEqual(str(row["snapshot_date"]), "2026-02-01")


if __name__ == "__main__":
    unittest.main()
