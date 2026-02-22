"""Ontology domain SQL/Cypher template specs."""

from __future__ import annotations

from typing import Any, Dict, List


ONTOLOGY_SQL_TEMPLATE_SPECS: List[Dict[str, Any]] = [
    {
        "template_id": "ontology.sql.latest_news_documents.v1",
        "table": "economic_news",
        "date_candidates": ("published_at", "event_date", "created_at"),
        "select_candidates": ("id", "title", "published_at", "source"),
        "required_params": (),
    },
    {
        "template_id": "ontology.sql.latest_corporate_events.v1",
        "table": "corporate_event_feed",
        "date_candidates": ("event_date", "published_at", "created_at"),
        "select_candidates": ("id", "event_type", "event_date", "title", "source"),
        "required_params": (),
    },
]


ONTOLOGY_GRAPH_TEMPLATE_SPEC: Dict[str, str] = {
    "template_id": "ontology.cypher.evidence_count.v1",
    "query": "MATCH (e:Evidence) RETURN count(e) AS metric_value",
    "metric_key": "evidences",
}


__all__ = ["ONTOLOGY_SQL_TEMPLATE_SPECS", "ONTOLOGY_GRAPH_TEMPLATE_SPEC"]
