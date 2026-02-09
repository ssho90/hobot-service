import unittest
from datetime import date
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

from service.graph.monitoring.graphrag_metrics import GraphRagApiCallLogger, GraphRagMonitoringMetrics


class StubNeo4jClient:
    def __init__(self):
        self.read_calls = []
        self.write_calls = []

    def run_write(self, query, params=None):
        self.write_calls.append((query, params or {}))
        return {
            "nodes_created": 1,
            "relationships_created": 0,
            "properties_set": 10,
        }

    def run_read(self, query, params=None):
        self.read_calls.append((query, params or {}))
        if "phase_d5_quality_metrics" in query:
            return [{
                "total_calls": 100,
                "success_calls": 92,
                "error_calls": 8,
                "cited_calls": 88,
                "evidence_link_rate_pct": 95.6522,
                "api_error_rate_pct": 8.0,
            }]
        if "phase_d5_reproducibility_metrics" in query:
            return [{
                "groups": 10,
                "repeated_runs": 34,
                "stable_runs": 28,
                "reproducibility_pct": 82.3529,
            }]
        if "phase_d5_consistency_metrics" in query:
            return [{
                "repeated_questions": 12,
                "repeated_runs": 40,
                "dominant_runs": 31,
                "consistency_pct": 77.5,
            }]
        if "phase_d5_performance_metrics" in query:
            return [{
                "avg_duration_ms": 1450.5,
                "p50_duration_ms": 1300.0,
                "p95_duration_ms": 2600.0,
                "max_duration_ms": 3900.0,
                "avg_node_count": 68.4,
                "p95_node_count": 140.0,
                "avg_link_count": 152.3,
                "p95_link_count": 320.0,
            }]
        return []


class TestPhaseDMonitoring(unittest.TestCase):
    def test_logger_writes_graph_rag_call_node(self):
        client = StubNeo4jClient()
        logger = GraphRagApiCallLogger(neo4j_client=client)
        result = logger.log_call(
            question="최근 인플레이션 리스크는?",
            time_range="30d",
            country="US",
            as_of_date=date(2026, 2, 7),
            model="gemini-3-pro-preview",
            status="success",
            duration_ms=1234,
            evidence_count=5,
            node_count=77,
            link_count=180,
            response_text="인플레이션 압력이 유지되고 있습니다.",
            analysis_run_id="ar_test",
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(len(client.write_calls), 1)
        query = client.write_calls[0][0]
        self.assertIn("phase_d5_log_graphrag_call", query)

    def test_metrics_summary_collects_all_sections(self):
        client = StubNeo4jClient()
        metrics = GraphRagMonitoringMetrics(neo4j_client=client)
        summary = metrics.collect_summary(days=7)

        self.assertEqual(summary["window_days"], 7)
        self.assertEqual(summary["quality"]["total_calls"], 100)
        self.assertEqual(summary["quality"]["error_calls"], 8)
        self.assertGreater(summary["reproducibility"]["reproducibility_pct"], 80.0)
        self.assertGreater(summary["consistency"]["consistency_pct"], 70.0)
        self.assertGreater(summary["performance"]["p95_duration_ms"], 2000.0)
        self.assertEqual(len(client.read_calls), 4)


if __name__ == "__main__":
    unittest.main()

