import os
import unittest
from unittest.mock import Mock, patch

import schedule

from service.macro_trading import scheduler


class TestUSTop50EarningsScheduler(unittest.TestCase):
    def tearDown(self):
        schedule.clear()

    def test_run_us_top50_earnings_hotpath_calls_collector(self):
        fake_collector = Mock()
        fake_collector.collect_earnings_events.return_value = {
            "target_symbol_count": 1,
            "expected_rows": 2,
            "confirmed_rows": 1,
            "upserted_rows": 3,
            "failed_symbols": [],
        }
        with patch(
            "service.macro_trading.scheduler.get_us_corporate_collector",
            return_value=fake_collector,
        ):
            result = scheduler.run_us_top50_earnings_hotpath(
                symbols=["AAPL"],
                max_symbol_count=5,
                include_expected=True,
                include_confirmed=True,
                lookback_days=5,
                lookahead_days=30,
            )

        self.assertEqual(result["upserted_rows"], 3)
        self.assertEqual(fake_collector.collect_earnings_events.call_count, 1)
        call_kwargs = fake_collector.collect_earnings_events.call_args.kwargs
        self.assertEqual(call_kwargs["symbols"], ["AAPL"])
        self.assertEqual(call_kwargs["max_symbol_count"], 5)
        self.assertEqual(call_kwargs["lookback_days"], 5)
        self.assertEqual(call_kwargs["lookahead_days"], 30)

    def test_run_us_top50_earnings_hotpath_extends_universe_with_grace_symbols(self):
        fake_collector = Mock()
        fake_collector.collect_earnings_events.return_value = {
            "target_symbol_count": 3,
            "expected_rows": 4,
            "confirmed_rows": 2,
            "upserted_rows": 6,
            "failed_symbols": [],
        }
        with patch(
            "service.macro_trading.scheduler.get_us_corporate_collector",
            return_value=fake_collector,
        ), patch(
            "service.macro_trading.scheduler._resolve_country_tier_symbols_with_grace",
            return_value=["MSFT", "NVDA"],
        ):
            result = scheduler.run_us_top50_earnings_hotpath(
                symbols=["AAPL"],
                max_symbol_count=1,
                use_grace_universe=True,
                grace_max_symbol_count=5,
            )

        kwargs = fake_collector.collect_earnings_events.call_args.kwargs
        self.assertEqual(kwargs["symbols"], ["AAPL", "MSFT", "NVDA"])
        self.assertEqual(kwargs["max_symbol_count"], 5)
        self.assertTrue(result["grace_universe_enabled"])
        self.assertEqual(result["grace_symbol_count"], 2)
        self.assertEqual(result["effective_max_symbol_count"], 5)

    def test_run_us_top50_earnings_hotpath_from_env(self):
        with patch.dict(
            os.environ,
            {
                "US_TOP50_FIXED_SYMBOLS": "AAPL,MSFT",
                "US_TOP50_EARNINGS_WATCH_MAX_SYMBOL_COUNT": "12",
                "US_TOP50_EARNINGS_INCLUDE_EXPECTED": "0",
                "US_TOP50_EARNINGS_INCLUDE_CONFIRMED": "1",
                "US_TOP50_EARNINGS_WATCH_LOOKBACK_DAYS": "2",
                "US_TOP50_EARNINGS_WATCH_LOOKAHEAD_DAYS": "45",
                "US_SEC_MAPPING_REFRESH": "0",
                "US_SEC_MAPPING_MAX_AGE_DAYS": "14",
            },
            clear=False,
        ), patch(
            "service.macro_trading.scheduler.run_us_top50_earnings_hotpath",
            return_value={"status": "ok"},
        ) as run_mock, patch(
            "service.macro_trading.scheduler._record_collection_run_report"
        ):
            result = scheduler.run_us_top50_earnings_hotpath_from_env()

        self.assertEqual(result["status"], "ok")
        kwargs = run_mock.call_args.kwargs
        self.assertEqual(kwargs["symbols"], ["AAPL", "MSFT"])
        self.assertEqual(kwargs["max_symbol_count"], 12)
        self.assertFalse(kwargs["include_expected"])
        self.assertTrue(kwargs["include_confirmed"])
        self.assertEqual(kwargs["lookback_days"], 2)
        self.assertEqual(kwargs["lookahead_days"], 45)
        self.assertFalse(kwargs["refresh_sec_mapping"])
        self.assertEqual(kwargs["sec_mapping_max_age_days"], 14)

    def test_run_us_top50_earnings_hotpath_from_env_records_success_report(self):
        with patch.dict(
            os.environ,
            {
                "US_TOP50_FIXED_SYMBOLS": "AAPL,MSFT,GOOG",
            },
            clear=False,
        ), patch(
            "service.macro_trading.scheduler.run_us_top50_earnings_hotpath",
            return_value={
                "target_symbol_count": 3,
                "failed_symbols": [{"symbol": "MSFT", "reason": "http_error:500"}],
                "api_requests": 3,
                "expected_rows": 4,
                "confirmed_rows": 2,
            },
        ), patch(
            "service.macro_trading.scheduler._record_collection_run_report"
        ) as report_mock:
            scheduler.run_us_top50_earnings_hotpath_from_env()

        self.assertEqual(report_mock.call_count, 1)
        kwargs = report_mock.call_args.kwargs
        self.assertEqual(kwargs["job_code"], scheduler.US_TOP50_EARNINGS_WATCH_JOB_CODE)
        self.assertEqual(kwargs["success_count"], 2)
        self.assertEqual(kwargs["failure_count"], 1)
        self.assertTrue(kwargs["run_success"])

    def test_run_us_top50_earnings_hotpath_from_env_records_failure_report(self):
        with patch(
            "service.macro_trading.scheduler.run_us_top50_earnings_hotpath",
            side_effect=RuntimeError("forced failure"),
        ), patch(
            "service.macro_trading.scheduler._record_collection_run_report"
        ) as report_mock:
            with self.assertRaises(RuntimeError):
                scheduler.run_us_top50_earnings_hotpath_from_env()

        self.assertEqual(report_mock.call_count, 1)
        kwargs = report_mock.call_args.kwargs
        self.assertEqual(kwargs["job_code"], scheduler.US_TOP50_EARNINGS_WATCH_JOB_CODE)
        self.assertEqual(kwargs["success_count"], 0)
        self.assertEqual(kwargs["failure_count"], 1)
        self.assertFalse(kwargs["run_success"])

    def test_setup_us_top50_earnings_scheduler_registers_job(self):
        schedule.clear()
        with patch.dict(
            os.environ,
            {
                "US_TOP50_EARNINGS_WATCH_ENABLED": "1",
                "US_TOP50_EARNINGS_WATCH_INTERVAL_MINUTES": "7",
            },
            clear=False,
        ):
            scheduler.setup_us_top50_earnings_scheduler()

        jobs = [job for job in schedule.get_jobs() if "us_top50_earnings_watch" in job.tags]
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].interval, 7)
        self.assertEqual(jobs[0].unit, "minutes")

    def test_setup_us_top50_earnings_scheduler_default_interval_is_5(self):
        schedule.clear()
        with patch.dict(
            os.environ,
            {
                "US_TOP50_EARNINGS_WATCH_ENABLED": "1",
            },
            clear=True,
        ):
            scheduler.setup_us_top50_earnings_scheduler()

        jobs = [job for job in schedule.get_jobs() if "us_top50_earnings_watch" in job.tags]
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].interval, 5)
        self.assertEqual(jobs[0].unit, "minutes")


if __name__ == "__main__":
    unittest.main()
