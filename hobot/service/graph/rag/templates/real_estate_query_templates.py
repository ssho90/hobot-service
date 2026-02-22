"""Real estate domain SQL/Cypher template specs."""

from __future__ import annotations

from typing import Any, Dict, List


REAL_ESTATE_SQL_TEMPLATE_SPECS: List[Dict[str, Any]] = [
    {
        "template_id": "real_estate.sql.latest_monthly_summary.v1",
        "table": "kr_real_estate_monthly_summary",
        "date_candidates": ("stat_ym", "summary_month", "obs_date", "date"),
        "region_candidates": ("lawd_cd", "region_code", "sigungu_code", "sido_code"),
        "select_candidates": (
            "stat_ym",
            "lawd_cd",
            "property_type",
            "transaction_type",
            "tx_count",
            "avg_price",
            "avg_price_per_m2",
            "as_of_date",
        ),
        "required_params": (),
    },
    {
        "template_id": "real_estate.sql.latest_transactions.v1",
        "table": "kr_real_estate_transactions",
        "date_candidates": ("contract_date", "trade_date", "date"),
        "region_candidates": ("region_code", "region_name", "sigungu_code", "sido_code"),
        "select_candidates": (
            "region_code",
            "property_type",
            "transaction_type",
            "contract_date",
            "price",
            "area_m2",
            "as_of_date",
        ),
        "required_params": (),
    },
]


REAL_ESTATE_GRAPH_TEMPLATE_SPEC: Dict[str, str] = {
    "template_id": "real_estate.cypher.summary_count.v1",
    "query": "MATCH (r:RealEstateMonthlySummary) RETURN count(r) AS metric_value",
    "metric_key": "real_estate_summaries",
}


__all__ = ["REAL_ESTATE_SQL_TEMPLATE_SPECS", "REAL_ESTATE_GRAPH_TEMPLATE_SPEC"]
