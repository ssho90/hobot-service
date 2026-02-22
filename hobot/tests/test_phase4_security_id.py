import unittest

from service.graph.rag.agents.live_executor import _build_sql_query
from service.graph.rag.security_id import build_equity_focus_identifiers


class _Request:
    def __init__(self, country_code=None):
        self.country_code = country_code


class TestPhase4SecurityId(unittest.TestCase):
    def test_build_equity_focus_identifiers_us_symbol(self):
        route_decision = {
            "selected_type": "us_single_stock",
            "matched_symbols": ["aapl"],
        }
        result = build_equity_focus_identifiers(route_decision, _Request(country_code="US"))
        self.assertEqual(result.get("country_code"), "US")
        self.assertEqual(result.get("native_code"), "AAPL")
        self.assertEqual(result.get("security_id"), "US:AAPL")
        self.assertEqual(result.get("focus_symbol"), "AAPL")

    def test_build_equity_focus_identifiers_kr_numeric_code(self):
        route_decision = {
            "selected_type": "us_single_stock",
            "matched_symbols": ["5930"],
        }
        result = build_equity_focus_identifiers(route_decision, _Request(country_code="KR"))
        self.assertEqual(result.get("country_code"), "KR")
        self.assertEqual(result.get("native_code"), "005930")
        self.assertEqual(result.get("security_id"), "KR:005930")
        self.assertEqual(result.get("focus_symbol"), "005930")

    def test_build_equity_focus_identifiers_security_id_input(self):
        route_decision = {
            "matched_symbols": ["KR:005930"],
        }
        result = build_equity_focus_identifiers(route_decision, _Request(country_code="US"))
        self.assertEqual(result.get("country_code"), "KR")
        self.assertEqual(result.get("native_code"), "005930")
        self.assertEqual(result.get("security_id"), "KR:005930")
        self.assertEqual(result.get("focus_symbol"), "005930")

    def test_build_sql_query_prefers_security_id_filter(self):
        query, params = _build_sql_query(
            table_name="us_top50_daily_ohlcv",
            columns=["security_id", "symbol", "trade_date", "close"],
            date_column="trade_date",
            select_columns=["security_id", "symbol", "trade_date", "close"],
            security_id_column="security_id",
            focus_security_id="US:AAPL",
            symbol_column="symbol",
            focus_symbol="AAPL",
            region_column=None,
            region_code=None,
        )
        self.assertIn("WHERE `security_id` = %s", query)
        self.assertNotIn("`symbol` = %s", query)
        self.assertEqual(params, ("US:AAPL",))

    def test_build_sql_query_symbol_fallback_when_security_id_missing(self):
        query, params = _build_sql_query(
            table_name="kr_top50_daily_ohlcv",
            columns=["stock_code", "trade_date", "close"],
            date_column="trade_date",
            select_columns=["stock_code", "trade_date", "close"],
            security_id_column=None,
            focus_security_id=None,
            symbol_column="stock_code",
            focus_symbol="005930",
            region_column=None,
            region_code=None,
        )
        self.assertIn("WHERE `stock_code` = %s", query)
        self.assertEqual(params, ("005930",))


if __name__ == "__main__":
    unittest.main()
