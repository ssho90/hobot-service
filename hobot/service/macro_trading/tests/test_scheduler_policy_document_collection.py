import os
import unittest
from unittest.mock import Mock, patch

import schedule

from service.macro_trading import scheduler


class TestPolicyDocumentCollectionScheduler(unittest.TestCase):
    def tearDown(self):
        schedule.clear()

    def test_collect_policy_documents_calls_collector(self):
        fake_collector = Mock()
        fake_collector.collect_recent_documents.return_value = {
            "status": "ok",
            "normalized_rows": 3,
            "db_affected": 3,
            "failed_source_count": 0,
        }
        with patch.dict(os.environ, {"POLICY_DOC_LOOKBACK_HOURS": "96"}, clear=False), patch(
            "service.macro_trading.scheduler.get_policy_document_collector",
            return_value=fake_collector,
        ):
            result = scheduler.collect_policy_documents()

        self.assertEqual(result["status"], "ok")
        self.assertEqual(fake_collector.collect_recent_documents.call_count, 1)
        kwargs = fake_collector.collect_recent_documents.call_args.kwargs
        self.assertEqual(kwargs["hours"], 96)

    def test_setup_policy_document_scheduler_registers_job(self):
        schedule.clear()
        with patch.dict(
            os.environ,
            {
                "POLICY_DOC_COLLECTION_ENABLED": "1",
                "POLICY_DOC_COLLECTION_INTERVAL_MINUTES": "30",
            },
            clear=False,
        ):
            scheduler.setup_policy_document_scheduler()

        jobs = [job for job in schedule.get_jobs() if "policy_document_collection" in job.tags]
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].unit, "minutes")
        self.assertEqual(jobs[0].interval, 30)

    def test_setup_policy_document_scheduler_disabled(self):
        schedule.clear()
        with patch.dict(
            os.environ,
            {"POLICY_DOC_COLLECTION_ENABLED": "0"},
            clear=False,
        ):
            scheduler.setup_policy_document_scheduler()

        jobs = [job for job in schedule.get_jobs() if "policy_document_collection" in job.tags]
        self.assertEqual(len(jobs), 0)

    def test_collect_kr_housing_policy_documents_filters_sources(self):
        fake_collector = Mock()
        fake_collector.collect_recent_documents.return_value = {
            "status": "ok",
            "normalized_rows": 2,
            "db_affected": 2,
            "failed_source_count": 0,
        }
        with patch.dict(os.environ, {"KR_HOUSING_POLICY_DOC_LOOKBACK_HOURS": "240"}, clear=False), patch(
            "service.macro_trading.scheduler.get_policy_document_collector",
            return_value=fake_collector,
        ):
            result = scheduler.collect_kr_housing_policy_documents()

        self.assertEqual(result["status"], "ok")
        kwargs = fake_collector.collect_recent_documents.call_args.kwargs
        self.assertEqual(kwargs["hours"], 240)
        source_keys = {source.key for source in kwargs["sources"]}
        self.assertEqual(
            source_keys,
            {"molit_housing_policy", "kreb_housing_policy", "khf_housing_policy"},
        )

    def test_setup_kr_housing_policy_document_scheduler_registers_job(self):
        schedule.clear()
        with patch.dict(
            os.environ,
            {
                "KR_HOUSING_POLICY_DOC_COLLECTION_ENABLED": "1",
                "KR_HOUSING_POLICY_DOC_COLLECTION_INTERVAL_MINUTES": "45",
            },
            clear=False,
        ):
            scheduler.setup_kr_housing_policy_document_scheduler()

        jobs = [
            job
            for job in schedule.get_jobs()
            if "kr_housing_policy_document_collection" in job.tags
        ]
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].unit, "minutes")
        self.assertEqual(jobs[0].interval, 45)


if __name__ == "__main__":
    unittest.main()
