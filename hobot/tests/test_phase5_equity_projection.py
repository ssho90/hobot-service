import sys
import types
import unittest
from datetime import date

neo4j_stub = types.ModuleType("neo4j")


class _StubGraphDatabase:
    @staticmethod
    def driver(*args, **kwargs):
        raise RuntimeError("Neo4j driver should not be used in unit tests")


neo4j_stub.GraphDatabase = _StubGraphDatabase
neo4j_stub.Driver = object
sys.modules.setdefault("neo4j", neo4j_stub)

from service.graph.equity_loader import EquityProjectionLoader


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
            "properties_set": 6,
            "constraints_added": 0,
            "indexes_added": 0,
        }

    def run_read(self, query, params=None):
        self.read_calls.append((query, params or {}))
        return [
            {
                "company_count": 2,
                "daily_bar_count": 4,
                "earnings_event_count": 1,
                "universe_snapshot_count": 2,
                "min_trade_date": "2026-02-18",
                "max_trade_date": "2026-02-19",
                "min_event_date": "2026-02-19",
                "max_event_date": "2026-02-19",
            }
        ]


class TestPhase5EquityProjection(unittest.TestCase):
    def test_upsert_universe_snapshot_direction(self):
        client = StubNeo4jClient()
        loader = EquityProjectionLoader(neo4j_client=client)
        rows = [
            {
                "country_code": "KR",
                "security_id": "KR:005930",
                "native_code": "005930",
                "market": "KOSPI",
                "snapshot_date": "2026-02-01",
                "rank_position": 1,
                "company_name": "삼성전자",
                "corp_code": "00126380",
                "source_url": "internal://kr-top50",
                "snapshot_key": "KR:005930:2026-02-01",
            }
        ]

        result = loader.upsert_universe_snapshots(rows)

        self.assertEqual(result["rows"], 1)
        self.assertEqual(len(client.write_calls), 1)
        query = client.write_calls[0][0]
        self.assertIn("MERGE (c)-[r:IN_UNIVERSE {snapshot_key: row.snapshot_key}]->(u)", query)

    def test_upsert_daily_bar_direction(self):
        client = StubNeo4jClient()
        loader = EquityProjectionLoader(neo4j_client=client)
        rows = [
            {
                "country_code": "US",
                "security_id": "US:AAPL",
                "native_code": "AAPL",
                "market": "US",
                "trade_date": "2026-02-19",
                "bar_key": "US:AAPL:2026-02-19",
                "open_price": 180.1,
                "high_price": 182.0,
                "low_price": 179.6,
                "close_price": 181.3,
                "adjusted_close": 181.3,
                "volume": 10123456,
                "source": "yfinance",
                "source_ref": "AAPL",
                "as_of_date": "2026-02-19",
            }
        ]

        result = loader.upsert_daily_bars(rows)

        self.assertEqual(result["rows"], 1)
        self.assertEqual(len(client.write_calls), 1)
        query = client.write_calls[0][0]
        self.assertIn("MERGE (c)-[:HAS_DAILY_BAR]->(b)", query)

    def test_sync_projection_no_data(self):
        client = StubNeo4jClient()
        loader = EquityProjectionLoader(neo4j_client=client)
        loader.ensure_graph_schema = lambda: {"constraints_added": 1}
        loader.fetch_universe_snapshots = lambda **kwargs: []
        loader.fetch_daily_bars = lambda **kwargs: []
        loader.fetch_earnings_events = lambda **kwargs: []

        result = loader.sync_projection(
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 19),
            country_codes=("KR", "US"),
        )

        self.assertEqual(result["status"], "no_data")
        self.assertEqual(result["row_counts"]["company_rows"], 0)
        self.assertEqual(result["row_counts"]["daily_bar_rows"], 0)
        self.assertEqual(result["schema_result"]["constraints_added"], 1)


if __name__ == "__main__":
    unittest.main()

