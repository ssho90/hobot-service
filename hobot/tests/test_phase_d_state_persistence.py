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

from service.graph.state.macro_state_generator import AnalysisRunWriter, MacroStateGenerator


class StubNeo4jClient:
    def __init__(self):
        self.read_calls = []
        self.write_calls = []

    def run_read(self, query, params=None):
        self.read_calls.append((query, params or {}))
        if "RETURN t.theme_id AS theme_id" in query:
            return [
                {"theme_id": "inflation", "theme_name": "Inflation", "doc_count": 15},
                {"theme_id": "rates", "theme_name": "Rates", "doc_count": 10},
            ]
        if "MATCH (i:EconomicIndicator)" in query and "CALL {" in query:
            return [
                {"indicator_code": "CPIAUCSL", "feature_name": "pct_change_1d", "value": 1.2, "obs_date": "2026-02-07"},
                {"indicator_code": "DGS10", "feature_name": "delta_1d", "value": -0.05, "obs_date": "2026-02-07"},
            ]
        return []

    def run_write(self, query, params=None):
        self.write_calls.append((query, params or {}))
        return {
            "nodes_created": 0,
            "relationships_created": 1,
            "properties_set": 3,
        }


class TestPhaseDStatePersistence(unittest.TestCase):
    def test_generate_macro_state_writes_theme_and_signal_links(self):
        client = StubNeo4jClient()
        generator = MacroStateGenerator(neo4j_client=client)
        result = generator.generate_macro_state(
            as_of_date=date(2026, 2, 7),
            theme_window_days=14,
            top_themes=2,
            top_signals=2,
        )

        self.assertEqual(result["as_of"], "2026-02-07")
        self.assertEqual(len(result["themes"]), 2)
        self.assertEqual(len(result["signals"]), 2)
        self.assertGreaterEqual(len(client.write_calls), 4)

        joined_queries = "\n".join(call[0] for call in client.write_calls)
        self.assertIn("MERGE (ms:MacroState", joined_queries)
        self.assertIn("DOMINANT_THEME", joined_queries)
        self.assertIn("HAS_SIGNAL", joined_queries)

    def test_analysis_run_writer_persists_run_and_links(self):
        client = StubNeo4jClient()
        writer = AnalysisRunWriter(neo4j_client=client)
        result = writer.persist_run(
            question="최근 인플레이션 리스크는?",
            response_text="인플레이션 압력이 높아졌습니다.",
            model="gemini-3-pro-preview",
            as_of_date=date(2026, 2, 7),
            citations=[
                {"evidence_id": "EVID_1", "node_ids": ["event:EVT_001", "document:te:100"]},
                {"evidence_id": "EVID_2", "node_ids": ["theme:inflation"]},
            ],
            impact_pathways=[
                {"event_id": "EVT_001", "theme_id": "inflation", "indicator_code": "CPIAUCSL"},
            ],
            duration_ms=3210,
        )

        self.assertTrue(result["run_id"].startswith("ar_"))
        self.assertEqual(result["counts"]["evidences"], 2)
        self.assertGreaterEqual(result["counts"]["events"], 1)
        self.assertGreaterEqual(result["counts"]["themes"], 1)
        self.assertGreaterEqual(result["counts"]["documents"], 1)

        joined_queries = "\n".join(call[0] for call in client.write_calls)
        self.assertIn("CREATE (ar:AnalysisRun", joined_queries)
        self.assertIn("USED_EVIDENCE", joined_queries)
        self.assertIn("USED_NODE", joined_queries)


if __name__ == "__main__":
    unittest.main()

