"""Macro domain SQL/Cypher template specs."""

from __future__ import annotations

from typing import Any, Dict, List


MACRO_SQL_TEMPLATE_SPECS: List[Dict[str, Any]] = [
    {
        "template_id": "macro.sql.latest_fred_observations.v1",
        "table": "fred_data",
        "date_candidates": ("obs_date", "date", "observation_date"),
        "select_candidates": ("indicator_code", "obs_date", "value", "unit", "as_of_date"),
        "required_params": (),
    },
    {
        "template_id": "macro.sql.latest_ecos_observations.v1",
        "table": "ecos_data",
        "date_candidates": ("obs_date", "date", "observation_date"),
        "select_candidates": ("indicator_code", "obs_date", "value", "unit", "as_of_date"),
        "required_params": (),
    },
    {
        "template_id": "macro.sql.latest_kosis_observations.v1",
        "table": "kosis_data",
        "date_candidates": ("obs_date", "date", "observation_date"),
        "select_candidates": ("indicator_code", "obs_date", "value", "unit", "as_of_date"),
        "required_params": (),
    },
]


MACRO_GRAPH_TEMPLATE_SPEC: Dict[str, str] = {
    "template_id": "macro.cypher.indicator_observation_count.v1",
    "query": "MATCH (o:IndicatorObservation) RETURN count(o) AS metric_value",
    "metric_key": "indicator_observations",
}


__all__ = ["MACRO_SQL_TEMPLATE_SPECS", "MACRO_GRAPH_TEMPLATE_SPEC"]
