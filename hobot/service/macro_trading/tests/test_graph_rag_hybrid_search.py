import os
import unittest
from unittest.mock import patch

from service.graph.rag.context_api import GraphRagContextBuilder


class _FakeNeo4j:
    def run_read(self, _query, _params=None):
        return []


class TestGraphRagHybridSearch(unittest.TestCase):
    def test_embed_query_vector_returns_none_without_api_key(self):
        with patch.dict(
            os.environ,
            {
                "GEMINI_EMBEDDING_API_KEY": "",
                "GEMINI_API_KEY": "",
                "GOOGLE_API_KEY": "",
            },
            clear=False,
        ):
            builder = GraphRagContextBuilder(neo4j_client=_FakeNeo4j())
            vector = builder._embed_query_vector("미국 금리 전망")
        self.assertIsNone(vector)

    def test_merge_hybrid_documents_prioritizes_vector_similarity(self):
        builder = GraphRagContextBuilder(neo4j_client=_FakeNeo4j())
        builder.bm25_weight = 0.0
        builder.vector_weight = 1.0
        builder.fallback_weight = 0.0

        base_documents = [
            {
                "doc_id": "doc_a",
                "title": "A",
                "event_ids": ["e1"],
                "theme_ids": ["rates"],
                "published_at": "2026-02-18T10:00:00",
            }
        ]
        keyword_documents = [
            {
                "doc_id": "doc_a",
                "title": "A",
                "event_ids": ["e1"],
                "theme_ids": ["rates"],
                "fulltext_score": 4.0,
                "published_at": "2026-02-18T10:00:00",
            }
        ]
        vector_documents = [
            {
                "doc_id": "doc_b",
                "title": "B",
                "event_ids": ["e2"],
                "theme_ids": ["inflation"],
                "vector_score": 0.92,
                "published_at": "2026-02-18T11:00:00",
            }
        ]

        merged, meta = builder._merge_hybrid_documents(
            base_documents=base_documents,
            keyword_documents=keyword_documents,
            fallback_documents=[],
            vector_documents=vector_documents,
            limit=10,
        )

        self.assertEqual(merged[0]["doc_id"], "doc_b")
        self.assertIn("vector", merged[0]["retrieval_sources"])
        self.assertEqual(meta["vector_docs"], 1)
        self.assertEqual(meta["bm25_docs"], 1)


if __name__ == "__main__":
    unittest.main()
