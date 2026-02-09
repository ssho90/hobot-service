import sys
import types
import unittest
from unittest.mock import patch

neo4j_stub = types.ModuleType("neo4j")


class _StubGraphDatabase:
    @staticmethod
    def driver(*args, **kwargs):
        raise RuntimeError("Neo4j driver should not be used in unit tests")


neo4j_stub.GraphDatabase = _StubGraphDatabase
neo4j_stub.Driver = object
sys.modules.setdefault("neo4j", neo4j_stub)

from service.graph.news_loader import NewsLoader
from service.graph.nel.nel_pipeline import EntityMention, NELResult
from service.graph.schemas.extraction_schema import (
    Claim,
    ConfidenceLevel,
    Event,
    Evidence,
    ExtractionResult,
    Fact,
    Link,
    LinkType,
    SentimentType,
)


class StubNeo4jClient:
    def __init__(self):
        self.write_calls = []

    def run_write(self, query, params=None):
        self.write_calls.append((query, params or {}))
        return {
            "nodes_created": 1,
            "nodes_deleted": 0,
            "relationships_created": 1,
            "relationships_deleted": 0,
            "properties_set": 1,
            "constraints_added": 0,
            "indexes_added": 0,
        }


class StubNELPipeline:
    def process_with_llm_mentions(self, text, llm_entities):
        mentions = [
            EntityMention(
                text="Fed",
                start_pos=0,
                end_pos=3,
                entity_type="institution",
                canonical_id="ORG_FED",
                canonical_name="Federal Reserve",
                confidence=0.9,
            )
        ]
        return NELResult(
            mentions=mentions,
            resolved_count=1,
            unresolved_count=0,
            resolution_rate=1.0,
        )


class StubExtractor:
    client = object()

    def extract(self, doc_id, article_text, title=""):
        evidence_fact = Evidence(
            evidence_text="Fed kept rates unchanged while inflation cooled.",
            confidence=ConfidenceLevel.HIGH,
        )
        evidence_claim = Evidence(
            evidence_text="Analysts said policy stays restrictive for longer.",
            confidence=ConfidenceLevel.MEDIUM,
        )
        result = ExtractionResult(
            doc_id=doc_id,
            model_name="stub-model",
            extractor_version="test",
            events=[
                Event(
                    event_name="Fed rate decision",
                    event_type="policy",
                    related_themes=["inflation"],
                    impact_level="high",
                )
            ],
            facts=[
                Fact(
                    fact_text="Fed held rates steady.",
                    fact_type="policy_action",
                    entities_mentioned=["Fed"],
                    evidences=[evidence_fact],
                )
            ],
            claims=[
                Claim(
                    claim_text="Rates may stay higher for longer.",
                    claim_type="analysis",
                    sentiment=SentimentType.NEGATIVE,
                    evidences=[evidence_claim],
                )
            ],
            links=[
                Link(
                    source_type="Event",
                    source_ref="Fed rate decision",
                    target_type="Theme",
                    target_ref="inflation",
                    link_type=LinkType.AFFECTS,
                    strength=0.8,
                    evidence=evidence_claim,
                )
            ],
        )
        result.generate_all_evidence_ids()
        return result


class StubExtractorWithoutClient:
    client = None

    def extract(self, doc_id, article_text, title=""):
        raise AssertionError("extract should not be called when client is missing")


class TestPhaseBGraphIngestion(unittest.TestCase):
    def _build_loader(self):
        loader = NewsLoader.__new__(NewsLoader)
        loader.neo4j_client = StubNeo4jClient()
        loader.nel_pipeline = StubNELPipeline()
        return loader

    def test_extract_and_persist_writes_graph_nodes(self):
        loader = self._build_loader()
        fake_module = types.ModuleType("service.graph.news_extractor")
        fake_module.get_news_extractor = lambda: StubExtractor()

        news_list = [
            {
                "doc_id": "te:1",
                "title": "Fed keeps rates unchanged",
                "description": "Inflation remains sticky.",
                "text": "Fed keeps rates unchanged and inflation cools gradually.",
                "published_at": "2026-02-07T01:00:00",
                "country_code": "US",
            }
        ]

        with patch.dict(sys.modules, {"service.graph.news_extractor": fake_module}):
            result = loader.extract_and_persist(news_list)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["success_docs"], 1)
        self.assertGreater(len(loader.neo4j_client.write_calls), 4)

        joined_queries = "\n".join(call[0] for call in loader.neo4j_client.write_calls)
        self.assertIn("MERGE (ev:Event", joined_queries)
        self.assertIn("MERGE (evi:Evidence", joined_queries)
        self.assertIn("MERGE (ev)-[r:AFFECTS]->(i)", joined_queries)

    def test_extract_and_persist_skips_without_gemini_client(self):
        loader = self._build_loader()
        fake_module = types.ModuleType("service.graph.news_extractor")
        fake_module.get_news_extractor = lambda: StubExtractorWithoutClient()

        with patch.dict(sys.modules, {"service.graph.news_extractor": fake_module}):
            result = loader.extract_and_persist(
                [{"doc_id": "te:1", "title": "t", "text": "x"}]
            )

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "missing_gemini_api_key")
        self.assertEqual(len(loader.neo4j_client.write_calls), 0)


if __name__ == "__main__":
    unittest.main()
