import unittest
from types import SimpleNamespace

from service.graph.embedding_loader import DocumentEmbeddingLoader


class _FakeNeo4j:
    def __init__(self, rows):
        self.rows = list(rows)
        self.write_calls = []

    def run_read(self, _query, _params=None):
        return list(self.rows)

    def run_write(self, query, params=None):
        payload = params or {}
        self.write_calls.append((query, payload))
        if "UNWIND $rows AS row" in query:
            return {"properties_set": len(payload.get("rows") or [])}
        return {}


class _FakeModels:
    def __init__(self, vectors):
        self.vectors = [list(vector) for vector in vectors]
        self.calls = []

    def embed_content(self, *, model, contents, config=None):
        if isinstance(contents, str):
            content_rows = [contents]
        else:
            content_rows = list(contents or [])
        self.calls.append(
            {
                "model": model,
                "content_count": len(content_rows),
                "config": config,
            }
        )
        vectors = [self.vectors.pop(0) for _ in content_rows]
        return SimpleNamespace(
            embeddings=[SimpleNamespace(values=vector) for vector in vectors],
        )


class _FakeClient:
    def __init__(self, vectors):
        self.models = _FakeModels(vectors)


class TestDocumentEmbeddingLoader(unittest.TestCase):
    def test_sync_incremental_skips_without_api_key(self):
        fake_neo4j = _FakeNeo4j([])
        loader = DocumentEmbeddingLoader(
            neo4j_client=fake_neo4j,
            output_dimension=3,
        )
        loader.client = None

        result = loader.sync_incremental(limit=10)
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "missing_gemini_embedding_api_key")

    def test_sync_incremental_embeds_documents(self):
        fake_neo4j = _FakeNeo4j(
            [
                {
                    "doc_id": "te:100",
                    "title": "US inflation cools",
                    "title_ko": None,
                    "description": "CPI slowed month over month",
                    "description_ko": None,
                    "text": "",
                    "embedding_text_hash": None,
                }
            ]
        )
        loader = DocumentEmbeddingLoader(
            neo4j_client=fake_neo4j,
            output_dimension=3,
            batch_size=8,
            max_text_chars=500,
        )
        loader.client = _FakeClient([[0.1, 0.2, 0.3]])

        result = loader.sync_incremental(limit=10)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["candidate_docs"], 1)
        self.assertEqual(result["embedded_docs"], 1)
        self.assertEqual(result["failed_docs"], 0)

        upsert_calls = [
            (query, payload)
            for query, payload in fake_neo4j.write_calls
            if "UNWIND $rows AS row" in query
        ]
        self.assertEqual(len(upsert_calls), 1)
        rows = upsert_calls[0][1].get("rows") or []
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["doc_id"], "te:100")
        self.assertEqual(len(rows[0]["embedding"]), 3)


if __name__ == "__main__":
    unittest.main()
