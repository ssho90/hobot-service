import os
import unittest
from unittest.mock import Mock, patch

import schedule

from service.macro_trading import scheduler


class TestUSKRTierStateScheduler(unittest.TestCase):
    def tearDown(self):
        schedule.clear()

    def test_sync_uskr_tier_state_calls_collector(self):
        fake_collector = Mock()
        fake_collector.sync_tier1_state.return_value = {
            "kr_source_count": 50,
            "us_source_count": 50,
            "db_affected_total": 100,
        }
        with patch(
            "service.macro_trading.scheduler.get_corporate_tier_collector",
            return_value=fake_collector,
        ):
            result = scheduler.sync_uskr_tier_state(
                kr_market="KOSPI",
                kr_limit=50,
                us_limit=50,
            )

        self.assertEqual(result["db_affected_total"], 100)
        self.assertEqual(fake_collector.sync_tier1_state.call_count, 1)

    def test_sync_uskr_tier_state_from_env(self):
        with patch.dict(
            os.environ,
            {
                "USKR_TIER_STATE_KR_MARKET": "KOSPI",
                "USKR_TIER_STATE_KR_LIMIT": "40",
                "USKR_TIER_STATE_US_LIMIT": "45",
                "US_TOP50_FIXED_SYMBOLS": "AAPL,MSFT",
            },
            clear=False,
        ), patch(
            "service.macro_trading.scheduler.sync_uskr_tier_state",
            return_value={"status": "ok"},
        ) as run_mock:
            result = scheduler.sync_uskr_tier_state_from_env()

        self.assertEqual(result["status"], "ok")
        kwargs = run_mock.call_args.kwargs
        self.assertEqual(kwargs["kr_market"], "KOSPI")
        self.assertEqual(kwargs["kr_limit"], 40)
        self.assertEqual(kwargs["us_limit"], 45)
        self.assertEqual(kwargs["us_symbols"], ["AAPL", "MSFT"])

    def test_setup_uskr_tier_state_scheduler_registers_job(self):
        schedule.clear()
        with patch.dict(
            os.environ,
            {
                "USKR_TIER_STATE_ENABLED": "1",
                "USKR_TIER_STATE_SCHEDULE_TIME": "07:05",
            },
            clear=False,
        ):
            scheduler.setup_uskr_tier_state_scheduler()

        jobs = [job for job in schedule.get_jobs() if "uskr_tier_state_daily" in job.tags]
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].unit, "days")
        self.assertEqual(str(jobs[0].at_time), "07:05:00")


if __name__ == "__main__":
    unittest.main()
