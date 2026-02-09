"""
Phase C-3: Indicator ↔ Indicator 통계 엣지 생성.
"""

import logging
import math
from datetime import date, timedelta
from itertools import combinations
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..neo4j_client import get_neo4j_client

logger = logging.getLogger(__name__)


class CorrelationEdgeGenerator:
    """시계열 관측치 기반으로 CORRELATED_WITH / LEADS 관계를 만든다."""

    def __init__(self, neo4j_client=None):
        self.neo4j_client = neo4j_client or get_neo4j_client()

    @staticmethod
    def _pearson(values_x: List[float], values_y: List[float]) -> float:
        if len(values_x) != len(values_y) or len(values_x) < 2:
            return 0.0
        mean_x = sum(values_x) / len(values_x)
        mean_y = sum(values_y) / len(values_y)
        numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(values_x, values_y))
        denom_x = math.sqrt(sum((x - mean_x) ** 2 for x in values_x))
        denom_y = math.sqrt(sum((y - mean_y) ** 2 for y in values_y))
        if denom_x == 0 or denom_y == 0:
            return 0.0
        return numerator / (denom_x * denom_y)

    @classmethod
    def _best_lead_lag(
        cls,
        values_x: List[float],
        values_y: List[float],
        max_lag_days: int,
    ) -> Tuple[int, float]:
        best_lag = 0
        best_score = 0.0

        for lag in range(1, max_lag_days + 1):
            if len(values_x) <= lag or len(values_y) <= lag:
                break

            x_leads = cls._pearson(values_x[:-lag], values_y[lag:])
            if abs(x_leads) > abs(best_score):
                best_lag = lag
                best_score = x_leads

            y_leads = cls._pearson(values_x[lag:], values_y[:-lag])
            if abs(y_leads) > abs(best_score):
                best_lag = -lag
                best_score = y_leads

        return best_lag, best_score

    def _fetch_series(
        self,
        window_days: int,
        as_of_date: Optional[date] = None,
    ) -> Dict[str, Dict[date, float]]:
        end_date = as_of_date or date.today()
        start_date = end_date - timedelta(days=window_days)

        query = """
        MATCH (i:EconomicIndicator)-[:HAS_OBSERVATION]->(o:IndicatorObservation)
        WHERE o.obs_date >= date($start_date)
          AND o.obs_date <= date($end_date)
          AND o.value IS NOT NULL
        RETURN i.indicator_code AS code,
               o.obs_date AS obs_date,
               o.value AS value
        """
        rows = self.neo4j_client.run_read(
            query,
            {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
        )

        series: Dict[str, Dict[date, float]] = {}
        for row in rows:
            code = row["code"]
            obs_date = row["obs_date"]
            value = row["value"]
            if code not in series:
                series[code] = {}
            series[code][obs_date] = float(value)
        return series

    def generate_edges(
        self,
        window_days: int = 180,
        corr_threshold: float = 0.6,
        lead_threshold: float = 0.5,
        max_lag_days: int = 7,
        min_points: int = 30,
        top_k_pairs: int = 60,
        min_corr_edges: int = 30,
        as_of_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        as_of_value = (as_of_date or date.today()).isoformat()
        series = self._fetch_series(window_days=window_days, as_of_date=as_of_date)

        correlation_candidates: List[Dict[str, Any]] = []
        all_corr_pairs: List[Dict[str, Any]] = []
        lead_candidates: List[Dict[str, Any]] = []

        for code_a, code_b in combinations(sorted(series.keys()), 2):
            common_dates = sorted(set(series[code_a]).intersection(series[code_b]))
            if len(common_dates) < min_points:
                continue

            x = [series[code_a][d] for d in common_dates]
            y = [series[code_b][d] for d in common_dates]

            corr = self._pearson(x, y)
            all_corr_pairs.append(
                {
                    "code_a": code_a,
                    "code_b": code_b,
                    "corr": round(corr, 6),
                }
            )
            if abs(corr) >= corr_threshold:
                correlation_candidates.append(
                    {
                        "code_a": code_a,
                        "code_b": code_b,
                        "corr": round(corr, 6),
                    }
                )

            lag, lag_score = self._best_lead_lag(x, y, max_lag_days=max_lag_days)
            if lag == 0 or abs(lag_score) < lead_threshold:
                continue

            if lag > 0:
                source_code = code_a
                target_code = code_b
                lag_days = lag
            else:
                source_code = code_b
                target_code = code_a
                lag_days = abs(lag)

            lead_candidates.append(
                {
                    "source_code": source_code,
                    "target_code": target_code,
                    "lag_days": lag_days,
                    "score": round(lag_score, 6),
                }
            )

        all_corr_pairs.sort(key=lambda item: abs(item["corr"]), reverse=True)
        correlation_candidates.sort(key=lambda item: abs(item["corr"]), reverse=True)
        lead_candidates.sort(key=lambda item: abs(item["score"]), reverse=True)

        correlation_pairs = correlation_candidates[:top_k_pairs]
        if len(correlation_pairs) < min_corr_edges:
            fallback_pairs = [item for item in all_corr_pairs if item not in correlation_pairs]
            needed = min(min_corr_edges - len(correlation_pairs), max(top_k_pairs - len(correlation_pairs), 0))
            if needed > 0:
                correlation_pairs = correlation_pairs + fallback_pairs[:needed]

        lead_pairs = lead_candidates[:top_k_pairs]

        corr_query = """
        UNWIND $pairs AS pair
        MATCH (a:EconomicIndicator {indicator_code: pair.code_a})
        MATCH (b:EconomicIndicator {indicator_code: pair.code_b})
        MERGE (a)-[r:CORRELATED_WITH]->(b)
        SET r.corr = pair.corr,
            r.window_days = $window_days,
            r.as_of = date($as_of),
            r.method = "pearson"
        """
        lead_query = """
        UNWIND $pairs AS pair
        MATCH (a:EconomicIndicator {indicator_code: pair.source_code})
        MATCH (b:EconomicIndicator {indicator_code: pair.target_code})
        MERGE (a)-[r:LEADS]->(b)
        SET r.lag_days = pair.lag_days,
            r.score = pair.score,
            r.window_days = $window_days,
            r.as_of = date($as_of),
            r.method = "lead_lag_corr"
        """

        corr_result: Dict[str, Any] = {"relationships_created": 0, "properties_set": 0}
        lead_result: Dict[str, Any] = {"relationships_created": 0, "properties_set": 0}

        if correlation_pairs:
            corr_result = self.neo4j_client.run_write(
                corr_query,
                {"pairs": correlation_pairs, "window_days": window_days, "as_of": as_of_value},
            )

        if lead_pairs:
            lead_result = self.neo4j_client.run_write(
                lead_query,
                {"pairs": lead_pairs, "window_days": window_days, "as_of": as_of_value},
            )

        logger.info(
            "[CorrelationGen] corr=%s leads=%s",
            len(correlation_pairs),
            len(lead_pairs),
        )

        return {
            "window_days": window_days,
            "correlation_edges": len(correlation_pairs),
            "lead_edges": len(lead_pairs),
            "corr_result": corr_result,
            "lead_result": lead_result,
            "corr_sample": correlation_pairs[:5],
            "lead_sample": lead_pairs[:5],
        }


def run_correlation_generation(window_days: int = 180) -> Dict[str, Any]:
    generator = CorrelationEdgeGenerator()
    return generator.generate_edges(window_days=window_days)
