"""
Phase C-2: AFFECTS 동적 가중치 재계산 배치.
"""

import logging
from datetime import date
from typing import Any, Dict, Iterable, Optional

from ..neo4j_client import get_neo4j_client

logger = logging.getLogger(__name__)


class AffectsWeightRecalculator:
    """관측된 delta를 기반으로 AFFECTS.weight를 재계산한다."""

    def __init__(self, neo4j_client=None):
        self.neo4j_client = neo4j_client or get_neo4j_client()

    def recalculate(
        self,
        window_days: int = 90,
        min_events: int = 3,
        as_of_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        as_of_value = (as_of_date or date.today()).isoformat()

        recalc_query = """
        MATCH (ev:Event)-[r:AFFECTS]->(i:EconomicIndicator)
        WHERE r.observed_delta IS NOT NULL
          AND ev.event_time IS NOT NULL
          AND date(ev.event_time) >= date($as_of) - duration({days: $window_days})
          AND date(ev.event_time) <= date($as_of)
        WITH i, collect(r) AS rels, count(r) AS event_count, avg(r.observed_delta) AS avg_delta, stDev(r.observed_delta) AS sd
        WHERE event_count >= $min_events
        UNWIND rels AS rel
        WITH rel, event_count, avg_delta, sd,
             CASE WHEN sd IS NULL OR sd = 0 THEN avg_delta ELSE avg_delta / sd END AS z_score
        SET rel.weight = round((1.0 / (1.0 + exp(-z_score))) * 1000.0) / 1000.0,
            rel.polarity = CASE
                WHEN avg_delta > 0 THEN "positive"
                WHEN avg_delta < 0 THEN "negative"
                ELSE "neutral"
            END,
            rel.support_count = event_count,
            rel.window_days = $window_days,
            rel.as_of = date($as_of),
            rel.method = "rolling_" + toString($window_days) + "d"
        """

        snapshot_query = """
        MATCH (ev:Event)-[r:AFFECTS]->(i:EconomicIndicator)
        WHERE r.method = "rolling_" + toString($window_days) + "d"
          AND r.as_of = date($as_of)
        WITH i, count(r) AS rel_count, avg(r.weight) AS avg_weight, avg(r.observed_delta) AS avg_delta
        MERGE (s:AffectsSnapshot {snapshot_key: i.indicator_code + ":" + $as_of + ":" + toString($window_days)})
        SET s.indicator_code = i.indicator_code,
            s.window_days = $window_days,
            s.as_of = date($as_of),
            s.avg_weight = avg_weight,
            s.avg_delta = avg_delta,
            s.rel_count = rel_count,
            s.created_at = datetime()
        MERGE (s)-[:FOR_INDICATOR]->(i)
        """

        params = {
            "window_days": window_days,
            "min_events": min_events,
            "as_of": as_of_value,
        }

        recalc_result = self.neo4j_client.run_write(recalc_query, params)
        snapshot_result = self.neo4j_client.run_write(snapshot_query, params)

        logger.info(
            "[AffectsRecalc] window=%s recalc_props=%s snapshot_nodes=%s",
            window_days,
            recalc_result.get("properties_set", 0),
            snapshot_result.get("nodes_created", 0),
        )

        return {
            "window_days": window_days,
            "recalc_result": recalc_result,
            "snapshot_result": snapshot_result,
        }

    def recalculate_for_windows(
        self,
        windows: Iterable[int] = (90, 180),
        min_events: int = 3,
        as_of_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        results: Dict[str, Any] = {}
        for window in windows:
            try:
                results[str(window)] = self.recalculate(
                    window_days=window,
                    min_events=min_events,
                    as_of_date=as_of_date,
                )
            except Exception as exc:
                logger.exception("[AffectsRecalc] Failed on window=%s", window)
                results[str(window)] = {"error": str(exc)}
        return results


def run_affects_recalculation(windows: Iterable[int] = (90, 180)) -> Dict[str, Any]:
    recalc = AffectsWeightRecalculator()
    return recalc.recalculate_for_windows(windows=windows)

