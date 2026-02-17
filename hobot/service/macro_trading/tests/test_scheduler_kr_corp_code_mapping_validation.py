import os
import unittest
from unittest.mock import Mock, patch

import schedule

from service.macro_trading import scheduler


class TestKRCorpCodeMappingValidationScheduler(unittest.TestCase):
    def tearDown(self):
        schedule.clear()

    def test_validate_kr_top50_corp_code_mapping_calls_collector(self):
        fake_collector = Mock()
        fake_collector.validate_top50_corp_code_mapping.return_value = {
            "status": "healthy",
            "snapshot_row_count": 50,
            "snapshot_missing_corp_count": 0,
        }
        with patch(
            "service.macro_trading.scheduler.get_kr_corporate_collector",
            return_value=fake_collector,
        ):
            result = scheduler.validate_kr_top50_corp_code_mapping(
                market="KOSPI",
                top_limit=50,
                persist=True,
            )

        self.assertEqual(result["status"], "healthy")
        self.assertEqual(fake_collector.validate_top50_corp_code_mapping.call_count, 1)
        kwargs = fake_collector.validate_top50_corp_code_mapping.call_args.kwargs
        self.assertEqual(kwargs["market"], "KOSPI")
        self.assertEqual(kwargs["top_limit"], 50)
        self.assertTrue(kwargs["persist"])

    def test_validate_kr_top50_corp_code_mapping_from_env(self):
        with patch.dict(
            os.environ,
            {
                "KR_CORP_MAPPING_VALIDATION_MARKET": "KOSPI",
                "KR_CORP_MAPPING_VALIDATION_TOP_LIMIT": "40",
                "KR_CORP_MAPPING_VALIDATION_PERSIST": "0",
            },
            clear=False,
        ), patch(
            "service.macro_trading.scheduler.validate_kr_top50_corp_code_mapping",
            return_value={"status": "ok"},
        ) as run_mock:
            result = scheduler.validate_kr_top50_corp_code_mapping_from_env()

        self.assertEqual(result["status"], "ok")
        kwargs = run_mock.call_args.kwargs
        self.assertEqual(kwargs["market"], "KOSPI")
        self.assertEqual(kwargs["top_limit"], 40)
        self.assertFalse(kwargs["persist"])

    def test_setup_kr_corp_code_mapping_validation_scheduler_registers_job(self):
        schedule.clear()
        with patch.dict(
            os.environ,
            {
                "KR_CORP_MAPPING_VALIDATION_ENABLED": "1",
                "KR_CORP_MAPPING_VALIDATION_SCHEDULE_TIME": "06:20",
            },
            clear=False,
        ):
            scheduler.setup_kr_corp_code_mapping_validation_scheduler()

        jobs = [job for job in schedule.get_jobs() if "kr_corp_mapping_validation_daily" in job.tags]
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].unit, "days")
        self.assertEqual(str(jobs[0].at_time), "06:20:00")


if __name__ == "__main__":
    unittest.main()

