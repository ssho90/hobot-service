import unittest
from datetime import date, timedelta

from service.graph.rag.agents.live_executor import (
    _build_equity_ohlcv_analysis,
    _build_real_estate_trend_analysis,
    _fetch_existing_tables,
    _fetch_table_columns,
    _prioritize_sql_specs,
    _resolve_region_scope_label,
)


class _CursorStub:
    def __init__(self, rows):
        self._rows = rows
        self.last_query = None
        self.last_params = None

    def execute(self, query, params):
        self.last_query = query
        self.last_params = params

    def fetchall(self):
        return self._rows


class _SequentialCursorStub:
    def __init__(self, rows_by_call):
        self._rows_by_call = list(rows_by_call)
        self.execute_calls = []

    def execute(self, query, params):
        self.execute_calls.append((query, params))

    def fetchall(self):
        if not self._rows_by_call:
            return []
        return self._rows_by_call.pop(0)


class _RequestStub:
    def __init__(self, property_type="apartment"):
        self.property_type = property_type


class TestPhaseDLiveExecutor(unittest.TestCase):
    def test_prioritize_sql_specs_prefers_us_tables_for_us_single_stock(self):
        specs = [
            {"template_id": "equity.sql.latest_kr_ohlcv.v1", "table": "kr_top50_daily_ohlcv"},
            {"template_id": "equity.sql.latest_us_ohlcv.v1", "table": "us_top50_daily_ohlcv"},
            {"template_id": "equity.sql.latest_kr_financials.v1", "table": "kr_corporate_financials"},
            {"template_id": "equity.sql.latest_us_financials.v1", "table": "us_corporate_financials"},
        ]
        ordered = _prioritize_sql_specs(
            specs,
            available_tables={
                "kr_top50_daily_ohlcv",
                "us_top50_daily_ohlcv",
                "kr_corporate_financials",
                "us_corporate_financials",
            },
            preferred_country_code="US",
            selected_type="us_single_stock",
            focus_symbol="AAPL",
        )
        ordered_tables = [spec.get("table") for spec in ordered]
        self.assertEqual(ordered_tables[0], "us_top50_daily_ohlcv")
        self.assertIn("us_corporate_financials", ordered_tables[:2])

    def test_prioritize_sql_specs_prefers_kr_tables_for_numeric_symbol(self):
        specs = [
            {"template_id": "equity.sql.latest_us_ohlcv.v1", "table": "us_top50_daily_ohlcv"},
            {"template_id": "equity.sql.latest_kr_ohlcv.v1", "table": "kr_top50_daily_ohlcv"},
        ]
        ordered = _prioritize_sql_specs(
            specs,
            available_tables={"kr_top50_daily_ohlcv", "us_top50_daily_ohlcv"},
            preferred_country_code=None,
            selected_type="market_summary",
            focus_symbol="005930",
        )
        ordered_tables = [spec.get("table") for spec in ordered]
        self.assertEqual(ordered_tables[0], "kr_top50_daily_ohlcv")

    def test_fetch_existing_tables_supports_uppercase_dict_keys(self):
        cursor = _CursorStub(
            [
                {"TABLE_NAME": "kr_real_estate_monthly_summary"},
                {"TABLE_NAME": "kr_real_estate_transactions"},
            ]
        )
        result = _fetch_existing_tables(
            cursor,
            ["kr_real_estate_monthly_summary", "kr_real_estate_transactions"],
        )
        self.assertEqual(
            result,
            ["kr_real_estate_monthly_summary", "kr_real_estate_transactions"],
        )

    def test_fetch_table_columns_supports_uppercase_dict_keys(self):
        cursor = _CursorStub(
            [
                {"COLUMN_NAME": "stat_ym"},
                {"COLUMN_NAME": "lawd_cd"},
                {"COLUMN_NAME": "tx_count"},
            ]
        )
        result = _fetch_table_columns(cursor, "kr_real_estate_monthly_summary")
        self.assertEqual(result, ["stat_ym", "lawd_cd", "tx_count"])

    def test_resolve_region_scope_label_converts_lawd_code_to_name(self):
        self.assertEqual(_resolve_region_scope_label("48250"), "경남 김해시")

    def test_build_real_estate_trend_analysis_returns_12m_summary(self):
        cursor = _SequentialCursorStub(
            [
                [
                    {"stat_ym": "202601", "tx_count": 300, "weighted_avg_price": 230000000},
                    {"stat_ym": "202512", "tx_count": 280, "weighted_avg_price": 224000000},
                    {"stat_ym": "202511", "tx_count": 270, "weighted_avg_price": 220000000},
                    {"stat_ym": "202510", "tx_count": 260, "weighted_avg_price": 218000000},
                    {"stat_ym": "202509", "tx_count": 250, "weighted_avg_price": 216000000},
                    {"stat_ym": "202508", "tx_count": 245, "weighted_avg_price": 214000000},
                ]
            ]
        )
        result = _build_real_estate_trend_analysis(
            cursor=cursor,
            table_name="kr_real_estate_monthly_summary",
            columns=["stat_ym", "lawd_cd", "property_type", "tx_count", "avg_price"],
            date_column="stat_ym",
            region_column="lawd_cd",
            region_code="48250",
            request=_RequestStub(property_type="apartment"),
        )
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("status"), "ok")
        self.assertEqual(result.get("scope_label"), "경남 김해시")
        self.assertEqual(result.get("months_available"), 6)
        self.assertEqual(result.get("latest_month"), "202601")
        self.assertEqual(result.get("earliest_month"), "202508")
        self.assertIsNotNone(result.get("price_change_pct_vs_start"))
        self.assertIsNotNone(result.get("tx_change_pct_vs_start"))

    def test_build_equity_ohlcv_analysis_returns_ma_and_earnings_reaction(self):
        start = date(2025, 7, 1)
        ohlcv_rows = []
        for offset in range(160):
            trade_date = start + timedelta(days=offset)
            close_value = 100.0 + float(offset) * 0.8
            ohlcv_rows.append(
                {
                    "trade_date": trade_date,
                    "close_value": close_value,
                    "volume_value": 100000 + offset * 20,
                }
            )
        ohlcv_rows_desc = list(reversed(ohlcv_rows))
        earnings_rows = [
            {"event_date": date(2025, 11, 3)},
            {"event_date": date(2025, 9, 5)},
        ]
        cursor = _SequentialCursorStub([ohlcv_rows_desc, earnings_rows])

        result = _build_equity_ohlcv_analysis(
            cursor=cursor,
            table_name="us_top50_daily_ohlcv",
            columns=["trade_date", "symbol", "close_price", "volume"],
            date_column="trade_date",
            security_id_column=None,
            focus_security_id=None,
            symbol_column="symbol",
            focus_symbol="AAPL",
            country_code="US",
        )

        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("status"), "ok")
        self.assertGreaterEqual(int(result.get("bars_available") or 0), 120)
        moving_averages = result.get("moving_averages") or {}
        self.assertIsNotNone(moving_averages.get("ma20"))
        self.assertIsNotNone(moving_averages.get("ma60"))
        self.assertIsNotNone(moving_averages.get("ma120"))
        trend = result.get("trend") or {}
        self.assertEqual(trend.get("short_term"), "상승")
        self.assertIn("return_20d_pct", (result.get("returns") or {}))

        earnings_reaction = result.get("earnings_reaction") or {}
        self.assertEqual(earnings_reaction.get("status"), "ok")
        self.assertGreaterEqual(int(earnings_reaction.get("event_count") or 0), 1)
        self.assertIsNotNone(earnings_reaction.get("latest_event_day_pct_from_pre_close"))

    def test_build_equity_ohlcv_analysis_requires_symbol_filter(self):
        cursor = _SequentialCursorStub([[]])
        result = _build_equity_ohlcv_analysis(
            cursor=cursor,
            table_name="us_top50_daily_ohlcv",
            columns=["trade_date", "symbol", "close_price", "volume"],
            date_column="trade_date",
            security_id_column=None,
            focus_security_id=None,
            symbol_column="symbol",
            focus_symbol=None,
            country_code="US",
        )
        self.assertEqual(result.get("status"), "degraded")
        self.assertEqual(result.get("reason"), "focus_filter_missing")


if __name__ == "__main__":
    unittest.main()
