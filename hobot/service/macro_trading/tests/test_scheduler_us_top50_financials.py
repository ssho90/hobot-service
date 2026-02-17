import os
import unittest
from unittest.mock import Mock, patch

import schedule

from service.macro_trading import scheduler


class TestUSTop50FinancialsScheduler(unittest.TestCase):
    def tearDown(self):
        schedule.clear()

    def test_run_us_top50_financials_hotpath_calls_collector(self):
        fake_collector = Mock()
        fake_collector.collect_financials.return_value = {
            "fetched_rows": 10,
            "upserted_rows": 10,
            "failed_symbols": [],
        }
        with patch(
            "service.macro_trading.scheduler.get_us_corporate_collector",
            return_value=fake_collector,
        ):
            result = scheduler.run_us_top50_financials_hotpath(
                symbols=["AAPL"],
                max_symbol_count=5,
                max_periods_per_statement=4,
            )

        self.assertEqual(result["upserted_rows"], 10)
        self.assertEqual(fake_collector.collect_financials.call_count, 1)
        kwargs = fake_collector.collect_financials.call_args.kwargs
        self.assertEqual(kwargs["symbols"], ["AAPL"])
        self.assertEqual(kwargs["max_symbol_count"], 5)
        self.assertEqual(kwargs["max_periods_per_statement"], 4)

    def test_run_us_top50_financials_hotpath_extends_universe_with_grace_symbols(self):
        fake_collector = Mock()
        fake_collector.collect_financials.return_value = {
            "fetched_rows": 20,
            "upserted_rows": 20,
            "failed_symbols": [],
        }
        with patch(
            "service.macro_trading.scheduler.get_us_corporate_collector",
            return_value=fake_collector,
        ), patch(
            "service.macro_trading.scheduler._resolve_country_tier_symbols_with_grace",
            return_value=["MSFT", "NVDA"],
        ):
            result = scheduler.run_us_top50_financials_hotpath(
                symbols=["AAPL"],
                max_symbol_count=1,
                use_grace_universe=True,
                grace_max_symbol_count=5,
            )

        kwargs = fake_collector.collect_financials.call_args.kwargs
        self.assertEqual(kwargs["symbols"], ["AAPL", "MSFT", "NVDA"])
        self.assertEqual(kwargs["max_symbol_count"], 5)
        self.assertTrue(result["grace_universe_enabled"])
        self.assertEqual(result["grace_symbol_count"], 2)
        self.assertEqual(result["effective_max_symbol_count"], 5)

    def test_run_us_top50_financials_hotpath_from_env(self):
        with patch.dict(
            os.environ,
            {
                "US_TOP50_FIXED_SYMBOLS": "AAPL,MSFT",
                "US_TOP50_FINANCIALS_MAX_SYMBOL_COUNT": "9",
                "US_TOP50_FINANCIALS_MAX_PERIODS_PER_STATEMENT": "6",
                "US_SEC_MAPPING_REFRESH": "0",
                "US_SEC_MAPPING_MAX_AGE_DAYS": "14",
            },
            clear=False,
        ), patch(
            "service.macro_trading.scheduler.run_us_top50_financials_hotpath",
            return_value={"status": "ok"},
        ) as run_mock:
            result = scheduler.run_us_top50_financials_hotpath_from_env()

        self.assertEqual(result["status"], "ok")
        kwargs = run_mock.call_args.kwargs
        self.assertEqual(kwargs["symbols"], ["AAPL", "MSFT"])
        self.assertEqual(kwargs["max_symbol_count"], 9)
        self.assertEqual(kwargs["max_periods_per_statement"], 6)
        self.assertFalse(kwargs["refresh_sec_mapping"])
        self.assertEqual(kwargs["sec_mapping_max_age_days"], 14)

    def test_setup_us_top50_financials_scheduler_registers_job(self):
        schedule.clear()
        with patch.dict(
            os.environ,
            {
                "US_TOP50_FINANCIALS_ENABLED": "1",
                "US_TOP50_FINANCIALS_SCHEDULE_TIME": "06:55",
            },
            clear=False,
        ):
            scheduler.setup_us_top50_financials_scheduler()

        jobs = [job for job in schedule.get_jobs() if "us_top50_financials_daily" in job.tags]
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].unit, "days")
        self.assertEqual(str(jobs[0].at_time), "06:55:00")


if __name__ == "__main__":
    unittest.main()
