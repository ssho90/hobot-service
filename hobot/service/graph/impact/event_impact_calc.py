"""
Phase C-1: Event Window Impact 계산 모듈.
"""

import logging
from datetime import date
from typing import Any, Dict, Iterable, Optional

from ..neo4j_client import get_neo4j_client

logger = logging.getLogger(__name__)


class EventImpactCalculator:
    """Event -> EconomicIndicator 관계에 observed_delta를 채운다."""

    def __init__(self, neo4j_client=None):
        self.neo4j_client = neo4j_client or get_neo4j_client()

    def calculate_for_window(
        self,
        window_days: int = 7,
        feature_name: str = "delta_1d",
        baseline_method: str = "mean_prev_window",
        fallback_max_gap_days: int = 120,
        as_of_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        as_of_value = (as_of_date or date.today()).isoformat()

        feature_query = """
        MATCH (ev:Event)-[r:AFFECTS]->(i:EconomicIndicator)
        WHERE ev.event_time IS NOT NULL
        WITH ev, r, i, date(ev.event_time) AS event_date
        MATCH (i)-[:HAS_OBSERVATION]->(o_prev:IndicatorObservation)-[:HAS_FEATURE]->(f_prev:DerivedFeature {feature_name: $feature_name})
        WHERE o_prev.obs_date < event_date
          AND o_prev.obs_date >= event_date - duration({days: $window_days})
        WITH ev, r, i, event_date, avg(f_prev.value) AS baseline_value
        MATCH (i)-[:HAS_OBSERVATION]->(o_post:IndicatorObservation)-[:HAS_FEATURE]->(f_post:DerivedFeature {feature_name: $feature_name})
        WHERE o_post.obs_date >= event_date
          AND o_post.obs_date < event_date + duration({days: $window_days})
        WITH r, baseline_value, avg(f_post.value) AS post_value
        WHERE baseline_value IS NOT NULL AND post_value IS NOT NULL
        SET r.observed_delta = post_value - baseline_value,
            r.window_days = $window_days,
            r.baseline_method = $baseline_method,
            r.as_of = date($as_of),
            r.method = "event_window_feature"
        """

        raw_query = """
        MATCH (ev:Event)-[r:AFFECTS]->(i:EconomicIndicator)
        WHERE ev.event_time IS NOT NULL
          AND r.observed_delta IS NULL
        WITH ev, r, i, date(ev.event_time) AS event_date
        MATCH (i)-[:HAS_OBSERVATION]->(o_prev:IndicatorObservation)
        WHERE o_prev.obs_date < event_date
          AND o_prev.obs_date >= event_date - duration({days: $window_days})
        WITH ev, r, i, event_date, avg(o_prev.value) AS baseline_value
        MATCH (i)-[:HAS_OBSERVATION]->(o_post:IndicatorObservation)
        WHERE o_post.obs_date >= event_date
          AND o_post.obs_date < event_date + duration({days: $window_days})
        WITH r, baseline_value, avg(o_post.value) AS post_value
        WHERE baseline_value IS NOT NULL AND post_value IS NOT NULL
        SET r.observed_delta = post_value - baseline_value,
            r.window_days = $window_days,
            r.baseline_method = $baseline_method + "_raw_observation",
            r.as_of = date($as_of),
            r.method = "event_window_raw"
        """

        nearest_fallback_query = """
        MATCH (ev:Event)-[r:AFFECTS]->(i:EconomicIndicator)
        WHERE ev.event_time IS NOT NULL
          AND r.observed_delta IS NULL
        WITH ev, r, i, date(ev.event_time) AS event_date
        MATCH (i)-[:HAS_OBSERVATION]->(o_prev:IndicatorObservation)
        WHERE o_prev.obs_date < event_date
        WITH ev, r, i, event_date, max(o_prev.obs_date) AS prev_date
        MATCH (i)-[:HAS_OBSERVATION]->(o_post:IndicatorObservation)
        WHERE o_post.obs_date >= event_date
        WITH r, i, event_date, prev_date, min(o_post.obs_date) AS post_date
        WHERE prev_date IS NOT NULL AND post_date IS NOT NULL
          AND duration.between(prev_date, event_date).days <= $fallback_max_gap_days
          AND duration.between(event_date, post_date).days <= $fallback_max_gap_days
        MATCH (i)-[:HAS_OBSERVATION]->(prev_obs:IndicatorObservation {obs_date: prev_date})
        MATCH (i)-[:HAS_OBSERVATION]->(post_obs:IndicatorObservation {obs_date: post_date})
        WHERE prev_obs.value IS NOT NULL AND post_obs.value IS NOT NULL
        SET r.observed_delta = post_obs.value - prev_obs.value,
            r.window_days = duration.between(prev_date, post_date).days,
            r.baseline_method = "nearest_observation",
            r.as_of = date($as_of),
            r.method = "event_nearest_obs",
            r.prev_obs_date = prev_date,
            r.post_obs_date = post_date
        """

        latest_proxy_query = """
        MATCH (ev:Event)-[r:AFFECTS]->(i:EconomicIndicator)
        WHERE r.observed_delta IS NULL
        MATCH (i)-[:HAS_OBSERVATION]->(o:IndicatorObservation)
        WITH r, i, o ORDER BY o.obs_date DESC
        WITH r, i, collect(o)[0..2] AS last_obs
        WHERE size(last_obs) = 2
          AND last_obs[0].value IS NOT NULL
          AND last_obs[1].value IS NOT NULL
        SET r.observed_delta = last_obs[0].value - last_obs[1].value,
            r.window_days = duration.between(last_obs[1].obs_date, last_obs[0].obs_date).days,
            r.baseline_method = "latest_pair_proxy",
            r.as_of = date($as_of),
            r.method = "event_proxy_latest_pair",
            r.prev_obs_date = last_obs[1].obs_date,
            r.post_obs_date = last_obs[0].obs_date
        """

        params = {
            "window_days": window_days,
            "feature_name": feature_name,
            "baseline_method": baseline_method,
            "fallback_max_gap_days": fallback_max_gap_days,
            "as_of": as_of_value,
        }

        feature_result = self.neo4j_client.run_write(feature_query, params)
        raw_result = self.neo4j_client.run_write(raw_query, params)
        nearest_result = self.neo4j_client.run_write(nearest_fallback_query, params)
        latest_proxy_result = self.neo4j_client.run_write(latest_proxy_query, params)

        logger.info(
            "[EventImpact] window=%s feature_updates=%s raw_updates=%s nearest_updates=%s proxy_updates=%s",
            window_days,
            feature_result.get("properties_set", 0),
            raw_result.get("properties_set", 0),
            nearest_result.get("properties_set", 0),
            latest_proxy_result.get("properties_set", 0),
        )

        return {
            "window_days": window_days,
            "feature_result": feature_result,
            "raw_result": raw_result,
            "nearest_result": nearest_result,
            "latest_proxy_result": latest_proxy_result,
        }

    def calculate_for_all_windows(
        self,
        windows: Iterable[int] = (3, 7, 14),
        feature_name: str = "delta_1d",
        as_of_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        results: Dict[str, Any] = {}
        for window in windows:
            try:
                results[str(window)] = self.calculate_for_window(
                    window_days=window,
                    feature_name=feature_name,
                    as_of_date=as_of_date,
                )
            except Exception as exc:
                logger.exception("[EventImpact] Failed on window=%s", window)
                results[str(window)] = {"error": str(exc)}
        return results


def run_event_impact_calculation(windows: Iterable[int] = (3, 7, 14)) -> Dict[str, Any]:
    calculator = EventImpactCalculator()
    return calculator.calculate_for_all_windows(windows=windows)
