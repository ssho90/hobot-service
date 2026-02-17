import unittest
from datetime import date

from service.macro_trading.collectors.corporate_entity_collector import (
    CorporateEntityCollector,
    DEFAULT_ENTITY_SYNC_SOURCE,
)


class TestCorporateEntityCollector(unittest.TestCase):
    def test_build_registry_rows_normalizes_country_symbol(self):
        tier_rows = [
            {
                "as_of_date": date(2026, 2, 17),
                "country_code": "kr",
                "market": "kospi",
                "symbol": "005930",
                "company_name": "삼성전자",
                "corp_code": "00126380",
                "cik": None,
                "tier_level": 1,
                "tier_source": "kr_top50_snapshot",
                "membership_rank": 1,
                "metadata_json": "{}",
            },
            {
                "as_of_date": date(2026, 2, 17),
                "country_code": "US",
                "market": "US",
                "symbol": "brk-b",
                "company_name": "Berkshire Hathaway",
                "corp_code": None,
                "cik": "1067983",
                "tier_level": 1,
                "tier_source": "us_top50_fixed",
                "membership_rank": 9,
                "metadata_json": "{}",
            },
        ]
        rows = CorporateEntityCollector.build_registry_rows(tier_rows)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["country_code"], "KR")
        self.assertEqual(rows[0]["symbol"], "005930")
        self.assertEqual(rows[1]["country_code"], "US")
        self.assertEqual(rows[1]["symbol"], "BRK-B")
        self.assertEqual(rows[1]["cik"], "0001067983")

    def test_build_alias_rows_includes_symbol_company_and_codes(self):
        registry_rows = [
            {
                "country_code": "KR",
                "symbol": "005930",
                "company_name": "삼성전자",
                "corp_code": "00126380",
                "cik": None,
                "latest_as_of_date": date(2026, 2, 17),
            },
            {
                "country_code": "US",
                "symbol": "BRK-B",
                "company_name": "Berkshire Hathaway",
                "corp_code": None,
                "cik": "0001067983",
                "latest_as_of_date": date(2026, 2, 17),
            },
        ]
        rows = CorporateEntityCollector.build_alias_rows(
            registry_rows,
            source=DEFAULT_ENTITY_SYNC_SOURCE,
        )
        key_set = {
            (row["country_code"], row["symbol"], row["alias_type"], row["alias_normalized"])
            for row in rows
        }
        self.assertIn(("KR", "005930", "symbol", "005930"), key_set)
        self.assertIn(("KR", "005930", "company_name", "삼성전자"), key_set)
        self.assertIn(("KR", "005930", "corp_code", "00126380"), key_set)
        self.assertIn(("US", "BRK-B", "symbol", "brkb"), key_set)
        self.assertIn(("US", "BRK-B", "symbol_compact", "brkb"), key_set)
        self.assertIn(("US", "BRK-B", "company_name", "berkshirehathaway"), key_set)
        self.assertIn(("US", "BRK-B", "cik", "0001067983"), key_set)


if __name__ == "__main__":
    unittest.main()

