import os
import unittest
from unittest.mock import patch

from service.macro_trading import scheduler


class TestGraphNewsEmbeddingScheduler(unittest.TestCase):
    def test_run_graph_news_extraction_sync_calls_embedding(self):
        fake_sync_result = {
            "status": "success",
            "sync_result": {"documents": 200},
            "extraction": {
                "batches": 2,
                "success_docs": 40,
                "failed_docs": 1,
                "skipped_docs": 0,
                "stop_reason": "max_batches_reached",
            },
        }

        with patch.dict(
            os.environ,
            {
                "GRAPH_NEWS_EMBEDDING_ENABLED": "1",
                "GRAPH_NEWS_EMBEDDING_LIMIT": "123",
                "GRAPH_NEWS_EMBEDDING_RETRY_FAILED_AFTER_MINUTES": "77",
            },
            clear=False,
        ), patch(
            "service.macro_trading.scheduler.sync_news_with_extraction_backlog",
            return_value=fake_sync_result,
        ), patch(
            "service.macro_trading.scheduler.sync_document_embeddings",
            return_value={"status": "success", "embedded_docs": 12},
        ) as embedding_mock, patch(
            "service.macro_trading.scheduler._record_collection_run_report",
        ) as report_mock:
            result = scheduler.run_graph_news_extraction_sync()

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["embedding"]["status"], "success")
        self.assertEqual(result["embedding"]["embedded_docs"], 12)
        embedding_mock.assert_called_once_with(
            limit=123,
            retry_failed_after_minutes=77,
        )
        report_mock.assert_called_once()
        self.assertEqual(
            report_mock.call_args.kwargs["job_code"],
            scheduler.GRAPH_NEWS_EXTRACTION_SYNC_JOB_CODE,
        )
        self.assertTrue(report_mock.call_args.kwargs["run_success"])

    def test_run_graph_news_extraction_sync_skips_embedding_when_disabled(self):
        fake_sync_result = {
            "status": "success",
            "sync_result": {"documents": 10},
            "extraction": {
                "batches": 1,
                "success_docs": 5,
                "failed_docs": 0,
                "skipped_docs": 0,
                "stop_reason": "no_candidates",
            },
        }

        with patch.dict(
            os.environ,
            {
                "GRAPH_NEWS_EMBEDDING_ENABLED": "0",
            },
            clear=False,
        ), patch(
            "service.macro_trading.scheduler.sync_news_with_extraction_backlog",
            return_value=fake_sync_result,
        ), patch(
            "service.macro_trading.scheduler.sync_document_embeddings",
        ) as embedding_mock, patch(
            "service.macro_trading.scheduler._record_collection_run_report",
        ) as report_mock:
            result = scheduler.run_graph_news_extraction_sync()

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["embedding"]["status"], "disabled")
        embedding_mock.assert_not_called()
        report_mock.assert_called_once()
        self.assertEqual(
            report_mock.call_args.kwargs["job_code"],
            scheduler.GRAPH_NEWS_EXTRACTION_SYNC_JOB_CODE,
        )

    def test_run_graph_news_extraction_sync_records_failure_report_on_exception(self):
        with patch(
            "service.macro_trading.scheduler.sync_news_with_extraction_backlog",
            side_effect=RuntimeError("sync failed"),
        ), patch(
            "service.macro_trading.scheduler._record_collection_run_report",
        ) as report_mock:
            with self.assertRaises(RuntimeError):
                scheduler.run_graph_news_extraction_sync.__wrapped__()

        report_mock.assert_called_once()
        self.assertEqual(
            report_mock.call_args.kwargs["job_code"],
            scheduler.GRAPH_NEWS_EXTRACTION_SYNC_JOB_CODE,
        )
        self.assertFalse(report_mock.call_args.kwargs["run_success"])


if __name__ == "__main__":
    unittest.main()
