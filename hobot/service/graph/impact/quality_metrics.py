"""
Phase C-5: 데이터 품질/모니터링 지표 수집.
"""

import logging
from typing import Any, Dict, List

from ..neo4j_client import get_neo4j_client

logger = logging.getLogger(__name__)


class PhaseCQualityMetrics:
    """Phase C 운영 지표를 Neo4j에서 집계한다."""

    def __init__(self, neo4j_client=None):
        self.neo4j_client = neo4j_client or get_neo4j_client()

    def affects_observed_delta_coverage(self) -> Dict[str, Any]:
        query = """
        MATCH ()-[r:AFFECTS]->()
        WITH count(r) AS total,
             count(CASE WHEN r.observed_delta IS NOT NULL THEN 1 END) AS filled
        RETURN total, filled,
               CASE WHEN total = 0 THEN 0.0 ELSE toFloat(filled) / total * 100 END AS pct
        """
        rows = self.neo4j_client.run_read(query)
        return rows[0] if rows else {"total": 0, "filled": 0, "pct": 0.0}

    def affects_weight_distribution(self) -> List[Dict[str, Any]]:
        query = """
        MATCH ()-[r:AFFECTS]->()
        WHERE r.weight IS NOT NULL
        RETURN r.window_days AS window_days,
               count(r) AS count,
               min(r.weight) AS min_weight,
               percentileCont(r.weight, 0.5) AS median_weight,
               max(r.weight) AS max_weight
        ORDER BY window_days
        """
        return self.neo4j_client.run_read(query)

    def observed_delta_spikes(self, threshold: float = 2.0, limit: int = 20) -> List[Dict[str, Any]]:
        query = """
        MATCH (ev:Event)-[r:AFFECTS]->(i:EconomicIndicator)
        WHERE r.observed_delta IS NOT NULL
          AND abs(r.observed_delta) >= $threshold
        RETURN ev.event_id AS event_id,
               i.indicator_code AS indicator_code,
               r.observed_delta AS observed_delta,
               r.window_days AS window_days,
               r.as_of AS as_of
        ORDER BY abs(r.observed_delta) DESC
        LIMIT $limit
        """
        return self.neo4j_client.run_read(query, {"threshold": threshold, "limit": limit})

    def collect_summary(self) -> Dict[str, Any]:
        coverage = self.affects_observed_delta_coverage()
        distribution = self.affects_weight_distribution()
        spikes = self.observed_delta_spikes()
        summary = {
            "coverage": coverage,
            "weight_distribution": distribution,
            "spikes": spikes,
        }
        logger.info("[PhaseCMetrics] %s", summary)
        return summary

