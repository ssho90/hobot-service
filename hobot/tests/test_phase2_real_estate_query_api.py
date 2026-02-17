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

from service.macro_trading.real_estate_api import execute_real_estate_query


class TestPhase2RealEstateQueryApi(unittest.TestCase):
    def test_detail_query_uses_rdb_source(self):
        with patch(
            "service.macro_trading.real_estate_api.fetch_rdb_transactions",
            return_value=([{"id": 1, "lawd_cd": "11110"}], 1),
        ) as mock_fetch:
            response = execute_real_estate_query(
                view="detail",
                start_ym="202501",
                end_ym="202502",
                lawd_codes_csv="11110",
                property_type="apartment",
                transaction_type="sale",
                limit=100,
                offset=0,
                include_metadata=False,
            )

        self.assertEqual(response.source, "mysql_transactions")
        self.assertFalse(response.fallback_used)
        self.assertEqual(response.total, 1)
        self.assertEqual(response.rows[0]["lawd_cd"], "11110")
        mock_fetch.assert_called_once()

    def test_monthly_query_falls_back_to_mysql(self):
        with patch(
            "service.macro_trading.real_estate_api._fetch_graph_monthly_summary",
            side_effect=RuntimeError("graph unavailable"),
        ) as mock_graph, patch(
            "service.macro_trading.real_estate_api._fetch_mysql_monthly_summary",
            return_value=([{"stat_ym": "202501", "lawd_cd": "11110"}], 1),
        ) as mock_mysql:
            response = execute_real_estate_query(
                view="monthly",
                start_ym="202501",
                end_ym="202502",
                lawd_codes_csv="11110",
                property_type="apartment",
                transaction_type="sale",
                limit=100,
                offset=0,
                include_metadata=False,
            )

        self.assertEqual(response.source, "mysql_monthly_summary_fallback")
        self.assertTrue(response.fallback_used)
        self.assertIn("graph_error", response.meta)
        self.assertEqual(response.total, 1)
        self.assertEqual(response.rows[0]["lawd_cd"], "11110")
        mock_graph.assert_called_once()
        mock_mysql.assert_called_once()

    def test_region_query_prefers_graph(self):
        with patch(
            "service.macro_trading.real_estate_api._fetch_graph_region_rollup",
            return_value=([{"lawd_cd": "41135", "tx_count": 120}], 1),
        ) as mock_graph:
            response = execute_real_estate_query(
                view="region",
                start_ym="202501",
                end_ym="202502",
                lawd_codes_csv=None,
                property_type="apartment",
                transaction_type="sale",
                limit=100,
                offset=0,
                include_metadata=False,
            )

        self.assertEqual(response.source, "neo4j_monthly_summary")
        self.assertFalse(response.fallback_used)
        self.assertEqual(response.total, 1)
        self.assertEqual(response.rows[0]["lawd_cd"], "41135")
        mock_graph.assert_called_once()

    def test_invalid_lawd_code_raises(self):
        with self.assertRaises(ValueError):
            execute_real_estate_query(
                view="monthly",
                start_ym="202501",
                end_ym="202502",
                lawd_codes_csv="1111X",
                property_type="apartment",
                transaction_type="sale",
                limit=100,
                offset=0,
                include_metadata=False,
            )

    def test_invalid_ym_range_raises(self):
        with self.assertRaises(ValueError):
            execute_real_estate_query(
                view="monthly",
                start_ym="202503",
                end_ym="202502",
                lawd_codes_csv=None,
                property_type="apartment",
                transaction_type="sale",
                limit=100,
                offset=0,
                include_metadata=False,
            )


if __name__ == "__main__":
    unittest.main()
