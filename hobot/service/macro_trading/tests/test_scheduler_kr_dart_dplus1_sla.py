import os
import unittest
from unittest.mock import Mock, patch

import schedule

from service.macro_trading import scheduler


class TestKRDartDplus1SlaScheduler(unittest.TestCase):
    def tearDown(self):
        schedule.clear()

    def test_validate_kr_dart_disclosure_dplus1_sla_calls_collector(self):
        fake_collector = Mock()
        fake_collector.validate_dart_disclosure_dplus1_sla.return_value = {
            "status": "healthy",
            "checked_event_count": 12,
            "violated_sla_count": 0,
        }
        with patch(
            "service.macro_trading.scheduler.get_kr_corporate_collector",
            return_value=fake_collector,
        ):
            result = scheduler.validate_kr_dart_disclosure_dplus1_sla(
                market="KOSPI",
                top_limit=50,
                lookback_days=30,
                persist=True,
            )

        self.assertEqual(result["status"], "healthy")
        self.assertEqual(fake_collector.validate_dart_disclosure_dplus1_sla.call_count, 1)
        kwargs = fake_collector.validate_dart_disclosure_dplus1_sla.call_args.kwargs
        self.assertEqual(kwargs["market"], "KOSPI")
        self.assertEqual(kwargs["top_limit"], 50)
        self.assertEqual(kwargs["lookback_days"], 30)
        self.assertTrue(kwargs["persist"])

    def test_validate_kr_dart_disclosure_dplus1_sla_from_env(self):
        with patch.dict(
            os.environ,
            {
                "KR_DART_DPLUS1_SLA_MARKET": "KOSPI",
                "KR_DART_DPLUS1_SLA_TOP_LIMIT": "40",
                "KR_DART_DPLUS1_SLA_LOOKBACK_DAYS": "14",
                "KR_DART_DPLUS1_SLA_PERSIST": "0",
            },
            clear=False,
        ), patch(
            "service.macro_trading.scheduler.validate_kr_dart_disclosure_dplus1_sla",
            return_value={"status": "ok"},
        ) as run_mock:
            result = scheduler.validate_kr_dart_disclosure_dplus1_sla_from_env()

        self.assertEqual(result["status"], "ok")
        kwargs = run_mock.call_args.kwargs
        self.assertEqual(kwargs["market"], "KOSPI")
        self.assertEqual(kwargs["top_limit"], 40)
        self.assertEqual(kwargs["lookback_days"], 14)
        self.assertFalse(kwargs["persist"])

    def test_setup_kr_dart_dplus1_sla_scheduler_registers_job(self):
        schedule.clear()
        with patch.dict(
            os.environ,
            {
                "KR_DART_DPLUS1_SLA_ENABLED": "1",
                "KR_DART_DPLUS1_SLA_SCHEDULE_TIME": "06:25",
            },
            clear=False,
        ):
            scheduler.setup_kr_dart_dplus1_sla_scheduler()

        jobs = [job for job in schedule.get_jobs() if "kr_dart_dplus1_sla_daily" in job.tags]
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].unit, "days")
        self.assertEqual(str(jobs[0].at_time), "06:25:00")


if __name__ == "__main__":
    unittest.main()
