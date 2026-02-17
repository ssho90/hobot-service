import unittest
from datetime import date
from unittest.mock import patch

import pandas as pd

from service.macro_trading.collectors.us_corporate_collector import (
    USCorporateCollector,
    _safe_float,
)


class TestUSCorporateCollector(unittest.TestCase):
    def test_safe_float_rejects_nan_and_inf(self):
        self.assertIsNone(_safe_float(float("nan")))
        self.assertIsNone(_safe_float(float("inf")))
        self.assertIsNone(_safe_float(float("-inf")))

    def test_sec_headers_do_not_force_host(self):
        collector = USCorporateCollector(db_connection_factory=lambda: None)
        headers = collector._sec_headers()
        self.assertIn("User-Agent", headers)
        self.assertNotIn("Host", headers)

    def test_extract_sec_earnings_events_filters_non_earnings_8k(self):
        collector = USCorporateCollector(db_connection_factory=lambda: None)
        payload = {
            "filings": {
                "recent": {
                    "accessionNumber": ["0000123456-26-000001", "0000123456-26-000002"],
                    "form": ["8-K", "8-K"],
                    "filingDate": ["2026-02-14", "2026-02-15"],
                    "acceptanceDateTime": ["20260214120000", "20260215120000"],
                    "reportDate": ["2026-02-13", "2026-02-14"],
                    "primaryDocument": ["a8k.htm", "b8k.htm"],
                    "items": ["2.02 Results of Operations", "1.01 Entry into Material Definitive Agreement"],
                    "primaryDocDescription": ["Earnings release", "Contract disclosure"],
                }
            }
        }

        rows = collector.extract_sec_earnings_events(
            symbol="AAPL",
            cik="320193",
            submission_payload=payload,
            as_of_date=date(2026, 2, 17),
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["event_status"], "confirmed")
        self.assertEqual(rows[0]["event_type"], "sec_8k_earnings")
        self.assertEqual(rows[0]["source_ref"], "0000123456-26-000001")

    def test_extract_financial_rows_from_frame(self):
        collector = USCorporateCollector(db_connection_factory=lambda: None)
        frame = pd.DataFrame(
            {
                pd.Timestamp("2025-09-30"): [10_000, 2_000],
                pd.Timestamp("2025-06-30"): [9_000, None],
            },
            index=["Total Revenue", "Operating Income"],
        )

        rows = collector.extract_financial_rows_from_frame(
            symbol="AAPL",
            cik="320193",
            company_name="Apple Inc.",
            statement_type="income_statement",
            statement_cadence="quarterly",
            frame=frame,
            currency="USD",
            as_of_date=date(2026, 2, 17),
            max_periods_per_statement=4,
        )

        self.assertEqual(len(rows), 3)
        first = rows[0]
        self.assertEqual(first["symbol"], "AAPL")
        self.assertEqual(first["statement_type"], "income_statement")
        self.assertEqual(first["statement_cadence"], "quarterly")
        self.assertIn(first["fiscal_period"], {"Q2", "Q3"})
        self.assertEqual(first["currency"], "USD")
        self.assertIn(first["account_key"], {"total_revenue", "operating_income"})

    def test_collect_financials_aggregates_summary(self):
        collector = USCorporateCollector(db_connection_factory=lambda: None)
        fake_rows = [
            {
                "symbol": "AAPL",
                "cik": "0000320193",
                "company_name": "Apple Inc.",
                "statement_type": "income_statement",
                "statement_cadence": "annual",
                "period_end_date": date(2025, 9, 30),
                "fiscal_year": "2025",
                "fiscal_period": "FY",
                "account_key": "total_revenue",
                "account_label": "Total Revenue",
                "value_numeric": 391_035_000_000.0,
                "currency": "USD",
                "unit": "USD",
                "source": "yfinance",
                "source_ref": "AAPL:income_statement:annual:2025-09-30:total_revenue",
                "as_of_date": date(2026, 2, 17),
                "metadata_json": "{}",
            }
        ]
        with patch.object(collector, "ensure_tables"), patch.object(
            collector,
            "resolve_target_symbols",
            return_value=["AAPL"],
        ), patch.object(
            collector,
            "refresh_sec_cik_mapping",
            return_value={"cache_hit": True},
        ), patch.object(
            collector,
            "load_symbol_mapping_rows",
            return_value={"AAPL": {"cik": "0000320193", "company_name": "Apple Inc."}},
        ), patch.object(
            collector,
            "fetch_financial_rows_from_yfinance",
            return_value={
                "rows": fake_rows,
                "rows_by_statement": {"income_statement:annual": 1},
                "rows_by_symbol": {"AAPL": 1},
                "failed_symbols": [],
            },
        ), patch.object(
            collector,
            "upsert_financial_rows",
            return_value=1,
        ):
            result = collector.collect_financials(
                symbols=["AAPL"],
                max_symbol_count=1,
            )

        self.assertEqual(result["target_symbol_count"], 1)
        self.assertEqual(result["fetched_rows"], 1)
        self.assertEqual(result["upserted_rows"], 1)
        self.assertEqual(result["rows_by_statement"]["income_statement:annual"], 1)
        self.assertEqual(result["rows_by_symbol"]["AAPL"], 1)

    def test_build_top50_snapshot_diff(self):
        collector = USCorporateCollector(db_connection_factory=lambda: None)
        latest_date = date(2026, 2, 1)
        previous_date = date(2026, 1, 1)
        latest_rows = [
            {"symbol": "AAPL", "company_name": "Apple", "rank_position": 1},
            {"symbol": "MSFT", "company_name": "Microsoft", "rank_position": 2},
            {"symbol": "NVDA", "company_name": "NVIDIA", "rank_position": 3},
        ]
        previous_rows = [
            {"symbol": "MSFT", "company_name": "Microsoft", "rank_position": 1},
            {"symbol": "AAPL", "company_name": "Apple", "rank_position": 2},
            {"symbol": "TSLA", "company_name": "Tesla", "rank_position": 3},
        ]

        with patch.object(collector, "ensure_tables"), patch.object(
            collector,
            "load_recent_top50_snapshot_dates",
            return_value=[latest_date, previous_date],
        ), patch.object(
            collector,
            "load_top50_snapshot_rows_by_date",
            side_effect=[latest_rows, previous_rows],
        ):
            result = collector.build_top50_snapshot_diff(market="US", limit=50)

        self.assertEqual(result["latest_snapshot_date"], "2026-02-01")
        self.assertEqual(result["previous_snapshot_date"], "2026-01-01")
        self.assertEqual(result["added_count"], 1)
        self.assertEqual(result["removed_count"], 1)
        self.assertEqual(result["rank_changed_count"], 2)
        self.assertEqual(result["added_symbols"][0]["symbol"], "NVDA")
        self.assertEqual(result["removed_symbols"][0]["symbol"], "TSLA")


if __name__ == "__main__":
    unittest.main()
