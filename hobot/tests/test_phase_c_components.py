import unittest
from datetime import date, datetime, timedelta
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

from service.graph.impact.affects_recalc_batch import AffectsWeightRecalculator
from service.graph.impact.event_impact_calc import EventImpactCalculator
from service.graph.stats.correlation_generator import CorrelationEdgeGenerator
from service.graph.story.story_clusterer import StoryClusterer


class StubNeo4jClient:
    def __init__(self):
        self.write_calls = []
        self.read_calls = []

    def run_write(self, query, params=None):
        self.write_calls.append((query, params or {}))
        return {
            "nodes_created": 0,
            "relationships_created": 1,
            "properties_set": 2,
        }

    def run_read(self, query, params=None):
        self.read_calls.append((query, params or {}))
        if "MATCH (i:EconomicIndicator)-[:HAS_OBSERVATION]->(o:IndicatorObservation)" in query:
            start = date(2026, 1, 1)
            rows = []
            for idx in range(40):
                obs_date = start + timedelta(days=idx)
                rows.append({"code": "AAA", "obs_date": obs_date, "value": float(idx)})
                rows.append({"code": "BBB", "obs_date": obs_date, "value": float(idx) * 2.0})
            return rows
        if "MATCH (d:Document)-[:ABOUT_THEME]->(t:MacroTheme)" in query:
            published = datetime(2026, 2, 6, 10, 0, 0)
            return [
                {"doc_id": "d1", "title": "alpha", "published_at": published, "theme_id": "inflation"},
                {"doc_id": "d2", "title": "beta", "published_at": published, "theme_id": "inflation"},
                {"doc_id": "d3", "title": "gamma", "published_at": published, "theme_id": "inflation"},
            ]
        return []


class TestPhaseCComponents(unittest.TestCase):
    def test_event_impact_runs_two_updates(self):
        client = StubNeo4jClient()
        calc = EventImpactCalculator(neo4j_client=client)
        result = calc.calculate_for_window(window_days=7, as_of_date=date(2026, 2, 7))

        self.assertEqual(result["window_days"], 7)
        self.assertEqual(len(client.write_calls), 4)

    def test_affects_recalc_runs_with_snapshot(self):
        client = StubNeo4jClient()
        recalc = AffectsWeightRecalculator(neo4j_client=client)
        result = recalc.recalculate(window_days=90, as_of_date=date(2026, 2, 7))

        self.assertEqual(result["window_days"], 90)
        self.assertEqual(len(client.write_calls), 2)

    def test_correlation_generator_creates_edges(self):
        client = StubNeo4jClient()
        generator = CorrelationEdgeGenerator(neo4j_client=client)
        result = generator.generate_edges(
            window_days=180,
            corr_threshold=0.8,
            lead_threshold=0.6,
            max_lag_days=3,
            min_points=20,
            top_k_pairs=5,
            as_of_date=date(2026, 2, 7),
        )

        self.assertGreaterEqual(result["correlation_edges"], 1)
        self.assertGreaterEqual(result["lead_edges"], 1)
        self.assertEqual(len(client.write_calls), 2)

    def test_story_clusterer_creates_story(self):
        client = StubNeo4jClient()
        clusterer = StoryClusterer(neo4j_client=client)
        result = clusterer.cluster_recent_documents(
            window_days=7,
            bucket_days=3,
            min_docs_per_story=3,
            as_of_date=date(2026, 2, 7),
        )

        self.assertEqual(result["stories_created"], 1)
        self.assertEqual(len(client.write_calls), 2)


if __name__ == "__main__":
    unittest.main()
