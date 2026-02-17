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

    def test_kr_country_filter_propagates_in_qa_context(self):
        client = StubNeo4jClient()
        request = GraphRagContextRequest(
            question="현재 한국 부동산 시장 요약해줘",
            time_range="30d",
            country="KR",
            as_of_date="2026-02-08",
        )

        result = build_graph_rag_context(request=request, neo4j_client=client)
        self.assertEqual(result.meta.get("country"), "KR")

        country_params = [params.get("country") for _, params in client.read_calls if isinstance(params, dict)]
        self.assertIn("KR", country_params)

    def test_country_code_filter_populates_normalized_params(self):
        client = StubNeo4jClient()
        request = GraphRagContextRequest(
            question="미국 금리 경로 요약해줘",
            time_range="30d",
            country_code="US",
            as_of_date="2026-02-08",
        )

        result = build_graph_rag_context(request=request, neo4j_client=client)
        self.assertEqual(result.meta.get("country_code"), "US")
        self.assertEqual(result.meta.get("resolved_country_code"), "US")

        params_list = [params for _, params in client.read_calls if isinstance(params, dict)]
        self.assertTrue(any(params.get("country_code") == "US" for params in params_list))

    def test_build_graph_context_rejects_out_of_scope_country(self):
        client = StubNeo4jClient()
        request = GraphRagContextRequest(
            question="일본 금리 경로 요약해줘",
            time_range="30d",
            country_code="JP",
            as_of_date="2026-02-08",
        )
        with self.assertRaises(ValueError):
            build_graph_rag_context(request=request, neo4j_client=client)

    def test_scope_violation_warning_added_to_meta(self):
        client = StubNeo4jClient()
        original_run_read = client.run_read

        def run_read_with_scope_violation(query, params=None):
            if "phase_d_events" in query:
                return [
                    {
                        "event_id": "EVT_CN_1",
                        "event_type": "policy",
                        "summary": "CN policy event",
                        "event_time": datetime(2026, 2, 7, 10, 0, 0),
                        "country": "China",
                        "country_code": "CN",
                        "theme_ids": ["growth"],
                        "indicator_codes": ["DGS10"],
                    }
                ]
            if "phase_d_documents" in query:
                return [
                    {
                        "doc_id": "te:cn-1",
                        "title": "CN growth update",
                        "url": "https://example.com/cn",
                        "source": "TE",
                        "country": "China",
                        "country_code": "CN",
                        "category": "Macro",
                        "published_at": datetime(2026, 2, 7, 11, 0, 0),
                        "event_ids": ["EVT_CN_1"],
                        "theme_ids": ["growth"],
                    }
                ]
            return original_run_read(query, params)

        client.run_read = run_read_with_scope_violation

        request = GraphRagContextRequest(
            question="미국 성장 리스크 요약",
            time_range="30d",
            country_code="US",
            as_of_date="2026-02-08",
        )
        result = build_graph_rag_context(request=request, neo4j_client=client)

        warnings = result.meta.get("scope_warnings", [])
        violation_counts = result.meta.get("scope_violation_counts", {})

        self.assertTrue(any("범위 외 데이터" in message for message in warnings))
        self.assertGreaterEqual(violation_counts.get("out_of_scope_country_code", 0), 1)


if __name__ == "__main__":
    unittest.main()
