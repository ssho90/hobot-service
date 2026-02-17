import unittest
import sys
import types
from datetime import date

neo4j_stub = types.ModuleType("neo4j")


class _StubGraphDatabase:
    @staticmethod
    def driver(*args, **kwargs):
        raise RuntimeError("Neo4j driver should not be used in unit tests")


neo4j_stub.GraphDatabase = _StubGraphDatabase
neo4j_stub.Driver = object
sys.modules.setdefault("neo4j", neo4j_stub)

from service.graph.impact.quality_metrics import PhaseCQualityMetrics


class StubNeo4jClient:
    def __init__(self):
        self.read_calls = []
        self.write_calls = []

    def run_read(self, query, params=None):
        self.read_calls.append((query, params or {}))

        if "phase_c_country_quality_rows" in query:
            return [
                {"node_type": "Document", "country": "United States", "country_code": "US", "count": 90},
                {"node_type": "Document", "country": "United States", "country_code": "", "count": 5},
                {"node_type": "Event", "country": "South Korea", "country_code": "KR", "count": 40},
                {"node_type": "Event", "country": "China", "country_code": "CN", "count": 3},
                {"node_type": "Event", "country": "Mars", "country_code": "KR", "count": 2},
            ]

        if "phase_c_country_quality_missing_samples" in query:
            return [
                {"node_type": "Document", "country_raw": "United States", "count": 4},
                {"node_type": "Event", "country_raw": "South Korea", "count": 2},
            ]

        if "count(CASE WHEN r.observed_delta IS NOT NULL" in query:
            return [{"total": 10, "filled": 8, "pct": 80.0}]

        if "percentileCont(r.weight, 0.5)" in query:
            return [{"window_days": 30, "count": 10, "min_weight": 0.1, "median_weight": 0.5, "max_weight": 0.9}]

        if "abs(r.observed_delta) >= $threshold" in query:
            return [{"event_id": "EVT_1", "indicator_code": "CPI", "observed_delta": 2.3, "window_days": 30, "as_of": "2026-02-15"}]

        if "phase_c_country_backfill_missing_counts" in query:
            return [{"missing_documents": 5, "missing_events": 4, "missing_calls": 3}]

        if "phase_c_country_backfill_document_missing_raw" in query:
            return [
                {"country_raw": "United States", "count": 3},
                {"country_raw": "Mars", "count": 2},
            ]

        if "phase_c_country_backfill_event_missing_raw" in query:
            return [
                {"country_raw": "South Korea", "count": 2},
                {"country_raw": "Commodity", "count": 1},
            ]

        if "phase_c_country_backfill_call_missing_raw" in query:
            return [
                {"country_raw": "US", "count": 1},
            ]

        if "phase_c_indicator_freshness_report" in query:
            return [
                {
                    "indicator_code": "DGS10",
                    "frequency": "daily",
                    "latest_obs_date": date(2026, 2, 15),
                    "latest_as_of_date": date(2026, 2, 15),
                    "latest_published_at": "2026-02-15T00:00:00",
                    "total_observations": 100,
                },
                {
                    "indicator_code": "CPIAUCSL",
                    "frequency": "monthly",
                    "latest_obs_date": date(2025, 12, 31),
                    "latest_as_of_date": date(2026, 1, 15),
                    "latest_published_at": "2026-01-15T00:00:00",
                    "total_observations": 40,
                },
            ]

        if "phase_c_indicator_missing_rate_report" in query:
            return [
                {
                    "indicator_code": "DGS10",
                    "frequency": "daily",
                    "observed_dates": [date(2026, 2, 13), date(2026, 2, 14), date(2026, 2, 15)],
                },
                {
                    "indicator_code": "WALCL",
                    "frequency": "weekly",
                    "observed_dates": [date(2026, 2, 10)],
                },
            ]

        return []

    def run_write(self, query, params=None):
        self.write_calls.append((query, params or {}))
        return {"nodes_created": 1, "properties_set": 8}


class TestPhaseCQualityMetrics(unittest.TestCase):
    def test_country_mapping_quality_report(self):
        client = StubNeo4jClient()
        metrics = PhaseCQualityMetrics(neo4j_client=client)

        report = metrics.country_mapping_quality_report(allowed_country_codes=("US", "KR"))

        self.assertEqual(report["total_nodes"], 140)
        self.assertEqual(report["ok"], 130)
        self.assertEqual(report["missing_country_code"], 5)
        self.assertEqual(report["out_of_scope_country_code"], 3)
        self.assertEqual(report["country_mismatch"], 2)
        self.assertGreater(report["mapping_accuracy_pct"], 90.0)

    def test_persist_weekly_country_quality_snapshot(self):
        client = StubNeo4jClient()
        metrics = PhaseCQualityMetrics(neo4j_client=client)

        result = metrics.persist_weekly_country_quality_snapshot(snapshot_date=date(2026, 2, 15))

        self.assertEqual(result["snapshot_date"], "2026-02-15")
        self.assertEqual(len(client.write_calls), 1)
        query = client.write_calls[0][0]
        self.assertIn("phase_c_country_quality_snapshot", query)

    def test_collect_summary_includes_country_quality(self):
        client = StubNeo4jClient()
        metrics = PhaseCQualityMetrics(neo4j_client=client)

        summary = metrics.collect_summary()

        self.assertIn("country_quality", summary)
        self.assertEqual(summary["country_quality"]["missing_country_code"], 5)
        self.assertIn("indicator_freshness", summary)
        self.assertIn("indicator_missing_rate", summary)

    def test_backfill_country_codes_executes_all_stages(self):
        client = StubNeo4jClient()
        metrics = PhaseCQualityMetrics(neo4j_client=client)

        result = metrics.backfill_country_codes(sample_limit=100)

        self.assertIn("before", result)
        self.assertIn("after", result)
        self.assertEqual(result["document"]["mapped_raw_values"], 1)
        self.assertEqual(result["document"]["unmapped_raw_values"], 1)
        self.assertEqual(result["event_from_self"]["mapped_raw_values"], 2)
        self.assertEqual(result["graphrag_call"]["mapped_raw_values"], 1)

        joined_queries = "\n".join(call[0] for call in client.write_calls)
        self.assertIn("phase_c_country_backfill_document_apply", joined_queries)
        self.assertIn("phase_c_country_backfill_event_apply", joined_queries)
        self.assertIn("phase_c_country_backfill_call_apply", joined_queries)
        self.assertIn("phase_c_country_backfill_event_infer_from_document", joined_queries)

    def test_indicator_freshness_report_flags_stale(self):
        client = StubNeo4jClient()
        metrics = PhaseCQualityMetrics(neo4j_client=client)

        report = metrics.indicator_freshness_report(as_of_date=date(2026, 2, 15))

        self.assertEqual(report["as_of_date"], "2026-02-15")
        self.assertEqual(len(report["rows"]), 2)
        stale_codes = {item["indicator_code"] for item in report["stale_indicators"]}
        self.assertIn("CPIAUCSL", stale_codes)
        self.assertNotIn("DGS10", stale_codes)

    def test_indicator_missing_rate_report_computes_rates(self):
        client = StubNeo4jClient()
        metrics = PhaseCQualityMetrics(neo4j_client=client)

        report = metrics.indicator_missing_rate_report(window_days=7, as_of_date=date(2026, 2, 15))

        self.assertEqual(report["window_days"], 7)
        self.assertEqual(len(report["rows"]), 2)
        self.assertGreaterEqual(report["avg_missing_rate_pct"], 0.0)
        top_code = report["top_missing_indicators"][0]["indicator_code"]
        self.assertEqual(top_code, "DGS10")


if __name__ == "__main__":
    unittest.main()
