import unittest
from datetime import datetime
import sys
import types

neo4j_stub = types.ModuleType("neo4j")


class _StubGraphDatabase:
    @staticmethod
    def driver(*args, **kwargs):
        raise RuntimeError("Neo4j driver should not be used in unit tests")


neo4j_stub.GraphDatabase = _StubGraphDatabase
neo4j_stub.Driver = object
sys.modules.setdefault("neo4j", neo4j_stub)

from service.graph.rag.context_api import (
    GraphRagContextRequest,
    build_graph_rag_context,
    parse_time_range_days,
)


class StubNeo4jClient:
    def __init__(self):
        self.read_calls = []

    def run_read(self, query, params=None):
        self.read_calls.append((query, params or {}))

        if "phase_d_top_themes" in query:
            return [{"theme_id": "growth", "doc_count": 10}]

        if "phase_d_indicator_candidates" in query:
            return [{"indicator_code": "DGS10"}]

        if "phase_d_events" in query:
            return [
                {
                    "event_id": "EVT_001",
                    "event_type": "economic_event",
                    "summary": "US CPI came in above expectations.",
                    "event_time": datetime(2026, 2, 7, 10, 0, 0),
                    "country": "US",
                    "theme_ids": ["inflation"],
                    "indicator_codes": ["CPIAUCSL"],
                }
            ]

        if "phase_d_documents_by_question_terms" in query:
            return [
                {
                    "doc_id": "te:5762",
                    "title": "Dollar Holds Near 2-Week High",
                    "url": "https://tradingeconomics.com/united-states/currency",
                    "source": "TradingEconomics Stream",
                    "country": "United States",
                    "category": "Currency",
                    "published_at": datetime(2026, 2, 6, 11, 7, 6),
                    "event_ids": [],
                    "theme_ids": [],
                    "matched_terms": ["kevin", "warsh", "kevin warsh"],
                }
            ]

        if "phase_d_documents" in query:
            return [
                {
                    "doc_id": "te:100",
                    "title": "US CPI Tops Forecasts",
                    "url": "https://example.com/cpi",
                    "source": "TE",
                    "country": "US",
                    "published_at": datetime(2026, 2, 7, 11, 0, 0),
                    "event_ids": ["EVT_001"],
                    "theme_ids": ["inflation"],
                }
            ]

        if "phase_d_stories" in query:
            return [
                {
                    "story_id": "story_001",
                    "title": "Inflation narrative",
                    "story_date": datetime(2026, 2, 7, 0, 0, 0),
                    "theme_id": "inflation",
                    "doc_ids": ["te:100"],
                }
            ]

        if "phase_d_evidences" in query:
            return [
                {
                    "evidence_id": "EVID_1",
                    "text": "Inflation accelerated in January.",
                    "doc_id": "te:100",
                    "doc_url": "https://example.com/cpi",
                    "doc_title": "US CPI Tops Forecasts",
                    "published_at": datetime(2026, 2, 7, 11, 0, 0),
                    "support_labels": ["Fact"],
                    "event_id": "EVT_001",
                    "claim_id": None,
                }
            ]

        if "phase_d_theme_meta" in query:
            return [
                {"theme_id": "inflation", "name": "Inflation", "description": "Price pressure"},
                {"theme_id": "growth", "name": "Growth", "description": "Economic growth"},
            ]

        if "phase_d_indicator_meta" in query:
            return [
                {"indicator_code": "CPIAUCSL", "name": "CPI", "unit": "index"},
                {"indicator_code": "DGS10", "name": "10Y Yield", "unit": "%"},
            ]

        return []


class TestPhaseDContextApi(unittest.TestCase):
    def test_build_graph_context_includes_nodes_links_evidences(self):
        client = StubNeo4jClient()
        request = GraphRagContextRequest(
            question="최근 인플레이션 리스크를 높인 이벤트는?",
            time_range="7d",
            country="US",
            as_of_date="2026-02-07",
        )

        result = build_graph_rag_context(request=request, neo4j_client=client)

        node_ids = {node.id for node in result.nodes}
        link_types = {link.type for link in result.links}

        self.assertIn("event:EVT_001", node_ids)
        self.assertIn("document:te:100", node_ids)
        self.assertIn("theme:inflation", node_ids)
        self.assertIn("AFFECTS", link_types)
        self.assertEqual(len(result.evidences), 1)
        self.assertEqual(result.meta["matched_theme_ids"], ["inflation"])
        self.assertEqual(result.meta["window_days"], 7)

    def test_generic_question_uses_recent_theme_fallback(self):
        client = StubNeo4jClient()
        request = GraphRagContextRequest(
            question="최근 매크로 내러티브를 요약해줘",
            time_range="30d",
            as_of_date="2026-02-07",
        )

        result = build_graph_rag_context(request=request, neo4j_client=client)

        self.assertIn("growth", result.meta["matched_theme_ids"])
        self.assertGreaterEqual(len(result.suggested_queries), 1)

        call_queries = "\n".join(query for query, _ in client.read_calls)
        self.assertIn("phase_d_top_themes", call_queries)

    def test_parse_time_range_rejects_invalid_value(self):
        with self.assertRaises(ValueError):
            parse_time_range_days("14d")

    def test_person_name_question_includes_keyword_matched_document(self):
        client = StubNeo4jClient()
        request = GraphRagContextRequest(
            question="kevin warsh가 새로운 연준 의장으로 임명 됐는데, 어떤 미국 주가에 영향이 있을까?",
            time_range="30d",
            country="United States",
            as_of_date="2026-02-08",
        )

        result = build_graph_rag_context(request=request, neo4j_client=client)
        node_ids = {node.id for node in result.nodes}
        self.assertIn("document:te:5762", node_ids)
        self.assertIn("kevin warsh", result.meta.get("question_terms", []))


if __name__ == "__main__":
    unittest.main()
