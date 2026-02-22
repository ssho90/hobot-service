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

        if "phase_d_documents_for_us_single_stock" in query:
            return [
                {
                    "doc_id": "te:pltr-1",
                    "title": "Palantir jumps after earnings beat",
                    "url": "https://example.com/pltr",
                    "source": "TE",
                    "country": "United States",
                    "country_code": "US",
                    "category": "Stock Market",
                    "published_at": datetime(2026, 2, 7, 15, 0, 0),
                    "event_ids": ["EVT_001"],
                    "theme_ids": ["growth"],
                    "matched_terms": ["pltr", "palantir"],
                    "stock_focus_score": 2,
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

    def test_build_graph_context_filters_dangling_links(self):
        client = StubNeo4jClient()
        original_run_read = client.run_read

        def run_read_with_dangling_link(query, params=None):
            if "phase_d_events" in query:
                return []
            if "phase_d_documents_for_us_single_stock" in query:
                return [
                    {
                        "doc_id": "te:pltr-dangling",
                        "title": "Palantir mention with missing event",
                        "url": "https://example.com/pltr-dangling",
                        "source": "TE",
                        "country": "United States",
                        "country_code": "US",
                        "category": "Stock Market",
                        "published_at": datetime(2026, 2, 7, 15, 0, 0),
                        "event_ids": ["EVT_MISSING"],
                        "theme_ids": ["growth"],
                        "matched_terms": ["pltr"],
                        "stock_focus_score": 1,
                    }
                ]
            return original_run_read(query, params)

        client.run_read = run_read_with_dangling_link

        request = GraphRagContextRequest(
            question="팔란티어 전망 어때?",
            time_range="30d",
            country_code="US",
            route_type="us_single_stock",
            focus_symbols=["PLTR"],
            as_of_date="2026-02-08",
        )
        result = build_graph_rag_context(request=request, neo4j_client=client)

        node_ids = {node.id for node in result.nodes}
        self.assertTrue(node_ids)
        self.assertTrue(result.links)
        self.assertTrue(
            all(link.source in node_ids and link.target in node_ids for link in result.links)
        )
        self.assertNotIn("event:EVT_MISSING", node_ids)
        self.assertTrue(
            all(link.target != "event:EVT_MISSING" for link in result.links)
        )

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

    def test_real_estate_route_defaults_country_to_kr_when_scope_missing(self):
        client = StubNeo4jClient()
        request = GraphRagContextRequest(
            question="부동산 가격 전망 해줘",
            time_range="30d",
            route_type="real_estate_detail",
            as_of_date="2026-02-08",
        )

        result = build_graph_rag_context(request=request, neo4j_client=client)
        self.assertEqual(result.meta.get("resolved_country_code"), "KR")

        params_list = [params for _, params in client.read_calls if isinstance(params, dict)]
        self.assertTrue(
            any(
                params.get("country_code") == "KR"
                or params.get("country_codes") == ["KR"]
                for params in params_list
            )
        )

    def test_kr_hint_question_defaults_country_to_kr_without_route(self):
        client = StubNeo4jClient()
        request = GraphRagContextRequest(
            question="한국 주가랑 부동산 분위기 요약해줘",
            time_range="30d",
            as_of_date="2026-02-08",
        )

        result = build_graph_rag_context(request=request, neo4j_client=client)
        self.assertEqual(result.meta.get("resolved_country_code"), "KR")

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

    def test_us_kr_country_scope_expands_to_country_codes(self):
        client = StubNeo4jClient()
        request = GraphRagContextRequest(
            question="미국과 한국 금리/환율 비교해줘",
            time_range="30d",
            country_code="US-KR",
            as_of_date="2026-02-08",
        )

        result = build_graph_rag_context(request=request, neo4j_client=client)
        self.assertEqual(result.meta.get("resolved_country_code"), "US-KR")
        self.assertEqual(result.meta.get("parsed_scope", {}).get("compare_mode"), "country_compare")

        params_list = [params for _, params in client.read_calls if isinstance(params, dict)]
        self.assertTrue(any(params.get("country_codes") == ["KR", "US"] for params in params_list))

    def test_scope_parser_populates_compare_mode_region_property(self):
        client = StubNeo4jClient()
        request = GraphRagContextRequest(
            question="서울 아파트 매매 추이 비교",
            time_range="30d",
            country_code="KR",
            as_of_date="2026-02-08",
        )
        result = build_graph_rag_context(request=request, neo4j_client=client)
        parsed_scope = result.meta.get("parsed_scope", {})
        parsed_region_codes = set(str(parsed_scope.get("region_code") or "").split(","))
        self.assertIn("11110", parsed_region_codes)
        self.assertIn("11740", parsed_region_codes)
        self.assertEqual(parsed_scope.get("property_type"), "apartment_sale")
        self.assertEqual(parsed_scope.get("compare_mode"), "single")

    def test_region_scope_expands_admin_query_to_lawd_code_set(self):
        client = StubNeo4jClient()
        request = GraphRagContextRequest(
            question="성남시와 수원시 아파트 매매 비교",
            time_range="30d",
            country_code="KR",
            as_of_date="2026-02-08",
        )
        result = build_graph_rag_context(request=request, neo4j_client=client)
        parsed_scope = result.meta.get("parsed_scope", {})
        parsed_region_codes = set(str(parsed_scope.get("region_code") or "").split(","))

        # 성남시(수정/중원/분당) + 수원시(장안/권선/팔달/영통)
        expected_codes = {"41131", "41133", "41135", "41111", "41113", "41115", "41117"}
        self.assertTrue(expected_codes.issubset(parsed_region_codes))
        self.assertEqual(parsed_scope.get("compare_mode"), "region_compare")

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

    def test_us_single_stock_route_fetches_stock_focused_documents(self):
        client = StubNeo4jClient()
        request = GraphRagContextRequest(
            question="팔란티어 주가 어때?",
            time_range="30d",
            country_code="US",
            route_type="us_single_stock",
            focus_symbols=["PLTR"],
            focus_companies=["Palantir"],
            as_of_date="2026-02-08",
        )

        result = build_graph_rag_context(request=request, neo4j_client=client)
        node_ids = {node.id for node in result.nodes}
        self.assertIn("document:te:pltr-1", node_ids)
        self.assertEqual(result.meta.get("parsed_scope", {}).get("route_type"), "us_single_stock")
        self.assertIn("PLTR", result.meta.get("parsed_scope", {}).get("focus_symbols", []))

        call_queries = "\n".join(query for query, _ in client.read_calls)
        self.assertIn("phase_d_documents_for_us_single_stock", call_queries)

    def test_stock_focus_fetches_stock_documents_even_without_us_single_stock_route(self):
        client = StubNeo4jClient()
        request = GraphRagContextRequest(
            question="팔란티어 하락 이유를 설명해줘",
            time_range="30d",
            route_type="explain_drop",
            focus_symbols=["PLTR"],
            focus_companies=["Palantir"],
            as_of_date="2026-02-08",
        )

        result = build_graph_rag_context(request=request, neo4j_client=client)
        node_ids = {node.id for node in result.nodes}
        self.assertIn("document:te:pltr-1", node_ids)
        self.assertEqual(result.meta.get("resolved_country_code"), "US")
        self.assertGreaterEqual(result.meta.get("retrieval", {}).get("stock_focus_docs", 0), 1)

        stock_params = [
            params
            for query, params in client.read_calls
            if "phase_d_documents_for_us_single_stock" in query
        ]
        self.assertTrue(stock_params)
        self.assertEqual(stock_params[0].get("country_codes"), ["US"])

    def test_theme_keyword_fallback_backfills_documents_when_theme_links_are_sparse(self):
        client = StubNeo4jClient()
        original_run_read = client.run_read

        def run_read_with_theme_keyword_fallback(query, params=None):
            if "phase_d_events" in query:
                return [
                    {
                        "event_id": "EVT_R1",
                        "event_type": "policy",
                        "summary": "Rates repricing",
                        "event_time": datetime(2026, 2, 19, 9, 0, 0),
                        "country": "United States",
                        "country_code": "US",
                        "theme_ids": ["rates"],
                        "indicator_codes": ["FEDFUNDS"],
                    }
                ]
            if "phase_d_documents" in query and "phase_d_documents_by" not in query:
                return []
            if "phase_d_documents_by_fulltext" in query:
                return []
            if "phase_d_documents_by_theme_keywords" in query:
                return [
                    {
                        "doc_id": "te:rates-fresh",
                        "title": "US rates outlook firms after labor data",
                        "url": "https://example.com/rates-fresh",
                        "source": "TE",
                        "country": "United States",
                        "country_code": "US",
                        "category": "Stock Market",
                        "published_at": datetime(2026, 2, 19, 15, 0, 0),
                        "event_ids": ["EVT_R1"],
                        "theme_ids": [],
                        "matched_terms": ["rates", "fomc"],
                    }
                ]
            if "phase_d_evidences" in query:
                return [
                    {
                        "evidence_id": "EVID_R1",
                        "text": "Markets delayed expectations for Fed rate cuts after jobs data.",
                        "doc_id": "te:rates-fresh",
                        "doc_url": "https://example.com/rates-fresh",
                        "doc_title": "US rates outlook firms after labor data",
                        "published_at": datetime(2026, 2, 19, 15, 0, 0),
                        "support_labels": ["Fact"],
                        "event_id": "EVT_R1",
                        "claim_id": None,
                    }
                ]
            return original_run_read(query, params)

        client.run_read = run_read_with_theme_keyword_fallback

        request = GraphRagContextRequest(
            question="금리 리스크가 자산배분에 주는 경로를 설명해줘.",
            time_range="30d",
            country_code="US",
            as_of_date="2026-02-20",
        )
        result = build_graph_rag_context(request=request, neo4j_client=client)

        self.assertGreaterEqual(result.meta.get("retrieval", {}).get("theme_keyword_docs", 0), 1)
        self.assertIn("document:te:rates-fresh", {node.id for node in result.nodes})

    def test_us_single_stock_symbol_expands_company_terms_and_defaults_us_scope(self):
        client = StubNeo4jClient()
        original_run_read = client.run_read
        stock_query_params = {}
        stock_query_text = ""

        def run_read_with_symbol_sensitive_stock_focus(query, params=None):
            nonlocal stock_query_text
            if "phase_d_documents_for_us_single_stock" in query:
                stock_query_text = query
                stock_query_params.update(params or {})
                query_terms = [str(item).lower() for item in (params or {}).get("query_terms") or []]
                if "msft" in query_terms and "microsoft" in query_terms:
                    return [
                        {
                            "doc_id": "te:msft-1",
                            "title": "US Stocks Lower, Microsoft Tumbles",
                            "url": "https://example.com/msft",
                            "source": "TE",
                            "country": "United States",
                            "country_code": "US",
                            "category": "Stock Market",
                            "published_at": datetime(2026, 2, 7, 12, 0, 0),
                            "event_ids": [],
                            "theme_ids": ["growth"],
                            "matched_terms": ["msft", "microsoft"],
                            "stock_focus_score": 2,
                        }
                    ]
                return []
            return original_run_read(query, params)

        client.run_read = run_read_with_symbol_sensitive_stock_focus

        request = GraphRagContextRequest(
            question="MSFT 주가 전망 어때?",
            time_range="30d",
            route_type="us_single_stock",
            focus_symbols=["MSFT"],
            as_of_date="2026-02-08",
        )
        result = build_graph_rag_context(request=request, neo4j_client=client)

        query_terms = [str(item).lower() for item in stock_query_params.get("query_terms") or []]
        self.assertIn("msft", query_terms)
        self.assertIn("microsoft", query_terms)
        self.assertEqual(stock_query_params.get("country_codes"), ["US"])
        self.assertIn("EntityAlias", stock_query_text)

        node_ids = {node.id for node in result.nodes}
        self.assertIn("document:te:msft-1", node_ids)
        self.assertIn("microsoft", [item.lower() for item in result.meta.get("parsed_scope", {}).get("focus_companies", [])])
        self.assertGreaterEqual(result.meta.get("retrieval", {}).get("stock_focus_docs", 0), 1)


if __name__ == "__main__":
    unittest.main()
