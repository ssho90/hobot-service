import sys
import types
import unittest

neo4j_stub = types.ModuleType("neo4j")


class _StubGraphDatabase:
    @staticmethod
    def driver(*args, **kwargs):
        raise RuntimeError("Neo4j driver should not be used in unit tests")


neo4j_stub.GraphDatabase = _StubGraphDatabase
neo4j_stub.Driver = object
sys.modules.setdefault("neo4j", neo4j_stub)

from service.graph.real_estate_loader import RealEstateSummaryLoader


class StubNeo4jClient:
    def __init__(self):
        self.write_calls = []
        self.read_calls = []

    def run_write(self, query, params=None):
        self.write_calls.append((query, params or {}))
        return {
            "nodes_created": 2,
            "nodes_deleted": 0,
            "relationships_created": 1,
            "relationships_deleted": 0,
            "properties_set": 8,
            "constraints_added": 0,
            "indexes_added": 0,
        }

    def run_read(self, query, params=None):
        self.read_calls.append((query, params or {}))
        return [{"summary_nodes": 3, "month_count": 2, "region_count": 2, "min_ym": "202401", "max_ym": "202402"}]


class TestPhase2RealEstateGraphSync(unittest.TestCase):
    def test_upsert_to_neo4j_batches(self):
        client = StubNeo4jClient()
        loader = RealEstateSummaryLoader(neo4j_client=client)
        rows = [
            {
                "summary_key": "KR:11110:202401:apartment:sale",
                "stat_ym": "202401",
                "obs_date": "2024-01-01",
                "lawd_cd": "11110",
                "country_code": "KR",
                "property_type": "apartment",
                "transaction_type": "sale",
                "tx_count": 10,
                "avg_price": 100000.0,
                "avg_price_per_m2": 1200.0,
                "avg_area_m2": 84.0,
                "min_price": 50000,
                "max_price": 180000,
                "total_price": 1000000,
                "as_of_date": "2026-02-15",
            },
            {
                "summary_key": "KR:11140:202401:apartment:sale",
                "stat_ym": "202401",
                "obs_date": "2024-01-01",
                "lawd_cd": "11140",
                "country_code": "KR",
                "property_type": "apartment",
                "transaction_type": "sale",
                "tx_count": 7,
                "avg_price": 90000.0,
                "avg_price_per_m2": 1100.0,
                "avg_area_m2": 81.0,
                "min_price": 45000,
                "max_price": 170000,
                "total_price": 630000,
                "as_of_date": "2026-02-15",
            },
            {
                "summary_key": "KR:11110:202402:apartment:sale",
                "stat_ym": "202402",
                "obs_date": "2024-02-01",
                "lawd_cd": "11110",
                "country_code": "KR",
                "property_type": "apartment",
                "transaction_type": "sale",
                "tx_count": 8,
                "avg_price": 102000.0,
                "avg_price_per_m2": 1220.0,
                "avg_area_m2": 83.5,
                "min_price": 60000,
                "max_price": 185000,
                "total_price": 816000,
                "as_of_date": "2026-02-15",
            },
        ]

        result = loader.upsert_to_neo4j(rows, batch_size=2)

        self.assertEqual(result["rows"], 3)
        self.assertEqual(len(client.write_calls), 2)
        joined_query = "\n".join(call[0] for call in client.write_calls)
        self.assertIn("MERGE (r:RealEstateRegion", joined_query)
        self.assertIn("MERGE (m:RealEstateMonthlySummary", joined_query)
        self.assertIn("MERGE (r)-[:HAS_MONTHLY_SUMMARY]->(m)", joined_query)

    def test_sync_monthly_summary_no_data(self):
        client = StubNeo4jClient()
        loader = RealEstateSummaryLoader(neo4j_client=client)
        loader.ensure_graph_schema = lambda: {"constraints_added": 1}
        loader.fetch_from_mysql = lambda **kwargs: []

        result = loader.sync_monthly_summary(
            start_ym="202401",
            end_ym="202402",
            property_type="apartment",
            transaction_type="sale",
        )

        self.assertEqual(result["status"], "no_data")
        self.assertEqual(result["rows_fetched"], 0)
        self.assertEqual(result["schema_result"]["constraints_added"], 1)


if __name__ == "__main__":
    unittest.main()

