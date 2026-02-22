"""Equity domain SQL/Cypher template specs."""

from __future__ import annotations

from typing import Any, Dict, List


EQUITY_SQL_TEMPLATE_SPECS: List[Dict[str, Any]] = [
    {
        "template_id": "equity.sql.latest_kr_ohlcv.v1",
        "table": "kr_top50_daily_ohlcv",
        "date_candidates": ("trade_date", "date"),
        "security_id_candidates": ("security_id",),
        "symbol_candidates": ("stock_code", "symbol", "ticker", "native_code"),
        "select_candidates": (
            "security_id",
            "stock_code",
            "symbol",
            "trade_date",
            "open_price",
            "high_price",
            "low_price",
            "close_price",
            "adjusted_close",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ),
        "required_params": ("symbol",),
    },
    {
        "template_id": "equity.sql.latest_us_ohlcv.v1",
        "table": "us_top50_daily_ohlcv",
        "date_candidates": ("trade_date", "date"),
        "security_id_candidates": ("security_id",),
        "symbol_candidates": ("symbol", "ticker", "stock_code", "native_code"),
        "select_candidates": (
            "security_id",
            "symbol",
            "ticker",
            "trade_date",
            "open_price",
            "high_price",
            "low_price",
            "close_price",
            "adjusted_close",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ),
        "required_params": ("symbol",),
    },
    {
        "template_id": "equity.sql.latest_kr_financials.v1",
        "table": "kr_corporate_financials",
        "date_candidates": ("period_end_date", "report_date", "fiscal_date"),
        "security_id_candidates": ("security_id",),
        "symbol_candidates": ("stock_code", "symbol", "native_code"),
        "select_candidates": (
            "security_id",
            "stock_code",
            "period_end_date",
            "revenue",
            "operating_income",
            "net_income",
            "as_of_date",
        ),
        "required_params": ("symbol",),
    },
    {
        "template_id": "equity.sql.latest_us_financials.v1",
        "table": "us_corporate_financials",
        "date_candidates": ("period_end_date", "report_date", "fiscal_date"),
        "security_id_candidates": ("security_id",),
        "symbol_candidates": ("symbol", "ticker", "native_code"),
        "select_candidates": (
            "security_id",
            "symbol",
            "period_end_date",
            "revenue",
            "operating_income",
            "net_income",
            "as_of_date",
        ),
        "required_params": ("symbol",),
    },
]


EQUITY_GRAPH_TEMPLATE_SPEC: Dict[str, str] = {
    "template_id": "equity.cypher.document_count.v1",
    "query": "MATCH (d:Document) RETURN count(d) AS metric_value",
    "metric_key": "documents",
}


__all__ = ["EQUITY_SQL_TEMPLATE_SPECS", "EQUITY_GRAPH_TEMPLATE_SPEC"]
