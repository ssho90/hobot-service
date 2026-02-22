import os
import unittest
from unittest.mock import Mock, patch

import schedule

from service.macro_trading import scheduler


class TestTier1CorporateEventSyncScheduler(unittest.TestCase):
    def tearDown(self):
        schedule.clear()

    def test_sync_tier1_corporate_events_calls_collector(self):
        fake_collector = Mock()
        fake_collector.sync_tier1_events.return_value = {
            "status": "ok",
            "kr_event_count": 10,
            "us_event_count": 20,
            "normalized_rows": 30,
            "db_affected": 30,
        }
        with patch(
            "service.macro_trading.scheduler.get_corporate_event_collector",
            return_value=fake_collector,
        ):
            result = scheduler.sync_tier1_corporate_events(
                lookback_days=45,
                kr_market="KOSPI",
                kr_top_limit=40,
                us_market="US",
                us_top_limit=50,
                include_us_expected=False,
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(fake_collector.sync_tier1_events.call_count, 1)
        kwargs = fake_collector.sync_tier1_events.call_args.kwargs
        self.assertEqual(kwargs["lookback_days"], 45)
        self.assertEqual(kwargs["kr_market"], "KOSPI")
        self.assertEqual(kwargs["kr_top_limit"], 40)
        self.assertEqual(kwargs["us_market"], "US")
        self.assertEqual(kwargs["us_top_limit"], 50)
        self.assertFalse(kwargs["include_us_expected"])
        self.assertTrue(kwargs["include_kr_ir_news"])
        self.assertIsNone(kwargs["kr_ir_feed_urls"])

    def test_sync_tier1_corporate_events_from_env(self):
        with patch.dict(
            os.environ,
            {
                "TIER1_EVENT_SYNC_LOOKBACK_DAYS": "21",
                "TIER1_EVENT_SYNC_KR_MARKET": "KOSPI",
                "TIER1_EVENT_SYNC_KR_TOP_LIMIT": "35",
                "TIER1_EVENT_SYNC_US_MARKET": "US",
                "TIER1_EVENT_SYNC_US_TOP_LIMIT": "45",
                "TIER1_EVENT_SYNC_INCLUDE_US_EXPECTED": "0",
                "TIER1_EVENT_SYNC_INCLUDE_KR_IR_NEWS": "1",
                "TIER1_EVENT_SYNC_KR_IR_FEED_URLS": "https://example.com/kr-ir-1.xml, https://example.com/kr-ir-2.xml",
            },
            clear=False,
        ), patch(
            "service.macro_trading.scheduler.sync_tier1_corporate_events",
            return_value={
                "status": "ok",
                "normalized_rows": 8,
                "retry_failure_count": 0,
                "dlq_recorded_count": 0,
            },
        ) as run_mock:
            with patch("service.macro_trading.scheduler._record_collection_run_report") as report_mock:
                result = scheduler.sync_tier1_corporate_events_from_env()

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["health_status"], "healthy")
        kwargs = run_mock.call_args.kwargs
        self.assertEqual(kwargs["lookback_days"], 21)
        self.assertEqual(kwargs["kr_market"], "KOSPI")
        self.assertEqual(kwargs["kr_top_limit"], 35)
        self.assertEqual(kwargs["us_market"], "US")
        self.assertEqual(kwargs["us_top_limit"], 45)
        self.assertFalse(kwargs["include_us_expected"])
        self.assertTrue(kwargs["include_kr_ir_news"])
        self.assertEqual(
            kwargs["kr_ir_feed_urls"],
            ["https://example.com/kr-ir-1.xml", "https://example.com/kr-ir-2.xml"],
        )
        self.assertEqual(report_mock.call_count, 1)
        report_kwargs = report_mock.call_args.kwargs
        self.assertEqual(report_kwargs["job_code"], scheduler.TIER1_CORPORATE_EVENT_SYNC_JOB_CODE)
        self.assertEqual(report_kwargs["status_override"], "healthy")
        self.assertTrue(report_kwargs["run_success"])

    def test_sync_tier1_corporate_events_from_env_marks_warn(self):
        with patch.dict(
            os.environ,
            {
                "TIER1_EVENT_SYNC_WARN_RETRY_FAILURE_COUNT": "1",
                "TIER1_EVENT_SYNC_DEGRADED_RETRY_FAILURE_COUNT": "3",
                "TIER1_EVENT_SYNC_WARN_DLQ_RECORDED_COUNT": "1",
                "TIER1_EVENT_SYNC_DEGRADED_DLQ_RECORDED_COUNT": "3",
            },
            clear=False,
        ), patch(
            "service.macro_trading.scheduler.sync_tier1_corporate_events",
            return_value={
                "status": "ok",
                "normalized_rows": 15,
                "retry_failure_count": 1,
                "dlq_recorded_count": 0,
            },
        ):
            with patch("service.macro_trading.scheduler._record_collection_run_report") as report_mock:
                result = scheduler.sync_tier1_corporate_events_from_env()

        self.assertEqual(result["health_status"], "warn")
        self.assertEqual(report_mock.call_count, 1)
        report_kwargs = report_mock.call_args.kwargs
        self.assertEqual(report_kwargs["status_override"], "warning")
        self.assertTrue(report_kwargs["run_success"])
        self.assertEqual(report_kwargs["failure_count"], 1)

    def test_sync_tier1_corporate_events_from_env_marks_degraded(self):
        with patch.dict(
            os.environ,
            {
                "TIER1_EVENT_SYNC_WARN_RETRY_FAILURE_COUNT": "1",
                "TIER1_EVENT_SYNC_DEGRADED_RETRY_FAILURE_COUNT": "3",
                "TIER1_EVENT_SYNC_WARN_DLQ_RECORDED_COUNT": "1",
                "TIER1_EVENT_SYNC_DEGRADED_DLQ_RECORDED_COUNT": "3",
            },
            clear=False,
        ), patch(
            "service.macro_trading.scheduler.sync_tier1_corporate_events",
            return_value={
                "status": "ok",
                "normalized_rows": 4,
                "retry_failure_count": 3,
                "dlq_recorded_count": 0,
            },
        ):
            with patch("service.macro_trading.scheduler._record_collection_run_report") as report_mock:
                result = scheduler.sync_tier1_corporate_events_from_env()

        self.assertEqual(result["health_status"], "degraded")
        self.assertEqual(report_mock.call_count, 1)
        report_kwargs = report_mock.call_args.kwargs
        self.assertEqual(report_kwargs["status_override"], "failed")
        self.assertFalse(report_kwargs["run_success"])
        self.assertEqual(report_kwargs["failure_count"], 3)

    def test_setup_tier1_corporate_event_sync_scheduler_registers_job(self):
        schedule.clear()
        with patch.dict(
            os.environ,
            {
                "TIER1_EVENT_SYNC_ENABLED": "1",
                "TIER1_EVENT_SYNC_INTERVAL_MINUTES": "20",
            },
            clear=False,
        ):
            scheduler.setup_tier1_corporate_event_sync_scheduler()

        jobs = [job for job in schedule.get_jobs() if "tier1_corporate_event_sync" in job.tags]
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].unit, "minutes")
        self.assertEqual(jobs[0].interval, 20)


if __name__ == "__main__":
    unittest.main()
