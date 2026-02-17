import os
import unittest
from unittest.mock import Mock, patch

import schedule

from service.macro_trading import scheduler


class TestUSKREntityRegistryScheduler(unittest.TestCase):
    def tearDown(self):
        schedule.clear()

    def test_sync_uskr_corporate_entity_registry_calls_collector(self):
        fake_collector = Mock()
        fake_collector.sync_from_tier1.return_value = {
            "source_row_count": 100,
            "registry_upsert_affected": 100,
            "alias_upsert_affected": 260,
        }
        with patch(
            "service.macro_trading.scheduler.get_corporate_entity_collector",
            return_value=fake_collector,
        ):
            result = scheduler.sync_uskr_corporate_entity_registry(
                countries=["KR", "US"],
                tier_level=1,
                source="tier1_sync",
            )

        self.assertEqual(result["source_row_count"], 100)
        self.assertEqual(fake_collector.sync_from_tier1.call_count, 1)

    def test_sync_uskr_corporate_entity_registry_from_env(self):
        with patch.dict(
            os.environ,
            {
                "USKR_ENTITY_REGISTRY_COUNTRIES": "KR,US",
                "USKR_ENTITY_REGISTRY_TIER_LEVEL": "1",
                "USKR_ENTITY_REGISTRY_SOURCE": "tier1_sync",
            },
            clear=False,
        ), patch(
            "service.macro_trading.scheduler.sync_uskr_corporate_entity_registry",
            return_value={"status": "ok"},
        ) as run_mock:
            result = scheduler.sync_uskr_corporate_entity_registry_from_env()

        self.assertEqual(result["status"], "ok")
        kwargs = run_mock.call_args.kwargs
        self.assertEqual(kwargs["countries"], ["KR", "US"])
        self.assertEqual(kwargs["tier_level"], 1)
        self.assertEqual(kwargs["source"], "tier1_sync")

    def test_setup_uskr_entity_registry_scheduler_registers_job(self):
        schedule.clear()
        with patch.dict(
            os.environ,
            {
                "USKR_ENTITY_REGISTRY_ENABLED": "1",
                "USKR_ENTITY_REGISTRY_SCHEDULE_TIME": "07:10",
            },
            clear=False,
        ):
            scheduler.setup_uskr_entity_registry_scheduler()

        jobs = [job for job in schedule.get_jobs() if "uskr_entity_registry_daily" in job.tags]
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].unit, "days")
        self.assertEqual(str(jobs[0].at_time), "07:10:00")


if __name__ == "__main__":
    unittest.main()

