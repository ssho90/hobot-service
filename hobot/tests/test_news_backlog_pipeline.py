import sys
import types
import unittest
from unittest.mock import MagicMock

neo4j_stub = types.ModuleType("neo4j")


class _StubGraphDatabase:
    @staticmethod
    def driver(*args, **kwargs):
        raise RuntimeError("Neo4j driver should not be used in unit tests")


neo4j_stub.GraphDatabase = _StubGraphDatabase
neo4j_stub.Driver = object
sys.modules.setdefault("neo4j", neo4j_stub)

from service.graph.news_loader import NewsLoader


class TestNewsBacklogPipeline(unittest.TestCase):
    def _build_loader(self) -> NewsLoader:
        return NewsLoader.__new__(NewsLoader)

    def test_backlog_pipeline_aggregates_batches(self):
        loader = self._build_loader()
        loader.sync_news = MagicMock(
            return_value={"status": "success", "documents": 123}
        )
        loader.fetch_extraction_candidates = MagicMock(
            side_effect=[
                [
                    {"doc_id": "te:1", "title": "a", "text": "x"},
                    {"doc_id": "te:2", "title": "b", "text": "y"},
                ],
                [{"doc_id": "te:3", "title": "c", "text": "z"}],
                [],
            ]
        )
        loader.extract_and_persist = MagicMock(
            side_effect=[
                {
                    "status": "success",
                    "processed_docs": 2,
                    "success_docs": 1,
                    "failed_docs": 1,
                    "skipped_docs": 0,
                    "failed_doc_ids": ["te:2"],
                    "write_result": {"nodes_created": 2, "relationships_created": 3},
                },
                {
                    "status": "success",
                    "processed_docs": 1,
                    "success_docs": 1,
                    "failed_docs": 0,
                    "skipped_docs": 0,
                    "failed_doc_ids": [],
                    "write_result": {"nodes_created": 1, "properties_set": 5},
                },
            ]
        )

        result = loader.sync_news_with_extraction_backlog(
            sync_limit=100,
            sync_days=7,
            extraction_batch_size=2,
            max_extraction_batches=5,
            retry_failed_after_minutes=120,
            extraction_progress_log_interval=10,
        )

        extraction = result["extraction"]
        self.assertEqual(extraction["batches"], 2)
        self.assertEqual(extraction["processed_docs"], 3)
        self.assertEqual(extraction["success_docs"], 2)
        self.assertEqual(extraction["failed_docs"], 1)
        self.assertEqual(extraction["stop_reason"], "no_candidates")
        self.assertEqual(extraction["failed_doc_ids"], ["te:2"])
        self.assertEqual(extraction["write_result"]["nodes_created"], 3)
        self.assertEqual(extraction["write_result"]["relationships_created"], 3)
        self.assertEqual(extraction["write_result"]["properties_set"], 5)
        self.assertEqual(loader.fetch_extraction_candidates.call_count, 3)
        self.assertEqual(loader.extract_and_persist.call_count, 2)

    def test_backlog_pipeline_stops_when_extractor_unavailable(self):
        loader = self._build_loader()
        loader.sync_news = MagicMock(
            return_value={"status": "success", "documents": 20}
        )
        loader.fetch_extraction_candidates = MagicMock(
            return_value=[{"doc_id": "te:1", "title": "a", "text": "x"}]
        )
        loader.extract_and_persist = MagicMock(
            return_value={
                "status": "skipped",
                "reason": "missing_gemini_api_key",
                "processed_docs": 0,
                "success_docs": 0,
                "failed_docs": 0,
                "skipped_docs": 0,
                "failed_doc_ids": [],
                "write_result": {},
            }
        )

        result = loader.sync_news_with_extraction_backlog(
            extraction_batch_size=1,
            max_extraction_batches=3,
        )

        extraction = result["extraction"]
        self.assertEqual(extraction["status"], "skipped")
        self.assertEqual(extraction["stop_reason"], "missing_gemini_api_key")
        self.assertEqual(extraction["batches"], 1)
        self.assertEqual(loader.fetch_extraction_candidates.call_count, 1)
        self.assertEqual(loader.extract_and_persist.call_count, 1)


if __name__ == "__main__":
    unittest.main()
