import unittest
from unittest.mock import patch

from service.macro_trading import scheduler


class TestKRTop50EarningsHotpath(unittest.TestCase):
    def test_hotpath_triggers_immediate_fundamentals_on_new_events(self):
        disclosure_summary = {
            "new_earnings_events": [
                {
                    "rcept_no": "20260215000111",
                    "corp_code": "00126380",
                    "period_year": "2025",
                    "fiscal_quarter": 4,
                },
                {
                    "rcept_no": "20260215000112",
                    "corp_code": "00164779",
                    "period_year": "2025",
                    "fiscal_quarter": 4,
                },
                {
                    "rcept_no": "20260215000113",
                    "corp_code": "00123456",
                    "period_year": "2026",
                    "fiscal_quarter": 1,
                },
            ]
        }

        with patch(
            "service.macro_trading.scheduler.collect_kr_corporate_disclosure_events",
            return_value=disclosure_summary,
        ) as disclosure_mock, patch(
            "service.macro_trading.scheduler.collect_kr_corporate_fundamentals",
            side_effect=[
                {"db_affected": 12},
                {"db_affected": 8},
            ],
        ) as fundamentals_mock:
            result = scheduler.run_kr_top50_earnings_hotpath(
                lookback_days=1,
                max_corp_count=50,
                per_corp_max_pages=2,
                immediate_fundamentals=True,
            )

        self.assertEqual(disclosure_mock.call_count, 1)
        self.assertEqual(fundamentals_mock.call_count, 2)
        self.assertTrue(result["fundamentals_triggered"])
        self.assertEqual(result["new_earnings_event_count"], 3)
        self.assertEqual(result["fundamentals_trigger_groups"], 2)
        self.assertEqual(result["fundamentals_total_db_affected"], 20)

        first_call = fundamentals_mock.call_args_list[0].kwargs
        second_call = fundamentals_mock.call_args_list[1].kwargs
        self.assertEqual(first_call["bsns_year"], "2025")
        self.assertEqual(first_call["reprt_code"], "11011")
        self.assertEqual(first_call["corp_codes"], ["00126380", "00164779"])
        self.assertEqual(second_call["bsns_year"], "2026")
        self.assertEqual(second_call["reprt_code"], "11013")
        self.assertEqual(second_call["corp_codes"], ["00123456"])

    def test_hotpath_skips_when_new_events_are_absent(self):
        with patch(
            "service.macro_trading.scheduler.collect_kr_corporate_disclosure_events",
            return_value={"new_earnings_events": []},
        ) as disclosure_mock, patch(
            "service.macro_trading.scheduler.collect_kr_corporate_fundamentals",
        ) as fundamentals_mock:
            result = scheduler.run_kr_top50_earnings_hotpath(
                lookback_days=1,
                immediate_fundamentals=True,
            )

        self.assertEqual(disclosure_mock.call_count, 1)
        fundamentals_mock.assert_not_called()
        self.assertFalse(result["fundamentals_triggered"])
        self.assertEqual(result["fundamentals_trigger_groups"], 0)

    def test_hotpath_skips_when_immediate_fundamentals_disabled(self):
        with patch(
            "service.macro_trading.scheduler.collect_kr_corporate_disclosure_events",
            return_value={
                "new_earnings_events": [
                    {
                        "rcept_no": "20260215000999",
                        "corp_code": "00126380",
                        "period_year": "2025",
                        "fiscal_quarter": 4,
                    }
                ]
            },
        ) as disclosure_mock, patch(
            "service.macro_trading.scheduler.collect_kr_corporate_fundamentals",
        ) as fundamentals_mock:
            result = scheduler.run_kr_top50_earnings_hotpath(
                lookback_days=1,
                immediate_fundamentals=False,
            )

        self.assertEqual(disclosure_mock.call_count, 1)
        fundamentals_mock.assert_not_called()
        self.assertFalse(result["fundamentals_triggered"])
        self.assertEqual(result["new_earnings_event_count"], 1)

    def test_hotpath_uses_grace_corp_codes_for_disclosure_scope(self):
        with patch(
            "service.macro_trading.scheduler._resolve_kr_corp_codes_from_tier_with_grace",
            return_value=["00126380", "00164779"],
        ), patch(
            "service.macro_trading.scheduler.collect_kr_corporate_disclosure_events",
            return_value={"new_earnings_events": []},
        ) as disclosure_mock:
            result = scheduler.run_kr_top50_earnings_hotpath(
                lookback_days=1,
                max_corp_count=50,
                use_grace_universe=True,
                grace_lookback_days=365,
                grace_max_symbol_count=150,
            )

        kwargs = disclosure_mock.call_args.kwargs
        self.assertEqual(kwargs["corp_codes"], ["00126380", "00164779"])
        self.assertEqual(kwargs["max_corp_count"], 2)
        self.assertTrue(result["grace_universe_enabled"])
        self.assertEqual(result["grace_corp_code_count"], 2)
        self.assertEqual(result["grace_lookback_days"], 365)


class TestKRTop50EarningsSchedulerDefaults(unittest.TestCase):
    def tearDown(self):
        scheduler.schedule.clear()

    def test_setup_uses_default_5_min_interval(self):
        scheduler.schedule.clear()
        with patch.dict(
            "os.environ",
            {
                "KR_TOP50_EARNINGS_WATCH_ENABLED": "1",
            },
            clear=True,
        ):
            scheduler.setup_kr_top50_earnings_scheduler()

        jobs = [
            job for job in scheduler.schedule.get_jobs() if "kr_top50_earnings_watch" in job.tags
        ]
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].interval, 5)
        self.assertEqual(jobs[0].unit, "minutes")


class TestKRTop50EarningsEnvWrapper(unittest.TestCase):
    def test_from_env_records_success_report(self):
        with patch.dict(
            "os.environ",
            {
                "KR_TOP50_EARNINGS_WATCH_LOOKBACK_DAYS": "1",
            },
            clear=False,
        ), patch(
            "service.macro_trading.scheduler.run_kr_top50_earnings_hotpath",
            return_value={
                "new_earnings_event_count": 2,
                "fundamentals_triggered": True,
                "fundamentals_trigger_groups": 1,
                "disclosure": {
                    "api_requests": 10,
                    "failed_requests": 2,
                },
            },
        ), patch(
            "service.macro_trading.scheduler._record_collection_run_report"
        ) as report_mock:
            result = scheduler.run_kr_top50_earnings_hotpath_from_env()

        self.assertEqual(result["new_earnings_event_count"], 2)
        self.assertEqual(report_mock.call_count, 1)
        kwargs = report_mock.call_args.kwargs
        self.assertEqual(kwargs["job_code"], scheduler.KR_TOP50_EARNINGS_WATCH_JOB_CODE)
        self.assertEqual(kwargs["success_count"], 8)
        self.assertEqual(kwargs["failure_count"], 2)
        self.assertTrue(kwargs["run_success"])

    def test_from_env_records_failure_report(self):
        with patch(
            "service.macro_trading.scheduler.run_kr_top50_earnings_hotpath",
            side_effect=RuntimeError("forced failure"),
        ), patch(
            "service.macro_trading.scheduler._record_collection_run_report"
        ) as report_mock:
            with self.assertRaises(RuntimeError):
                scheduler.run_kr_top50_earnings_hotpath_from_env()

        self.assertEqual(report_mock.call_count, 1)
        kwargs = report_mock.call_args.kwargs
        self.assertEqual(kwargs["job_code"], scheduler.KR_TOP50_EARNINGS_WATCH_JOB_CODE)
        self.assertEqual(kwargs["success_count"], 0)
        self.assertEqual(kwargs["failure_count"], 1)
        self.assertFalse(kwargs["run_success"])


if __name__ == "__main__":
    unittest.main()
