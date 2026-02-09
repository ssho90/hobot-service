"""
Phase C 주간 배치 진입점.
"""

import logging
from datetime import date
from typing import Any, Dict, Iterable, Optional

from ..impact.affects_recalc_batch import AffectsWeightRecalculator
from ..impact.event_impact_calc import EventImpactCalculator
from ..impact.quality_metrics import PhaseCQualityMetrics
from ..stats.correlation_generator import CorrelationEdgeGenerator
from ..story.story_clusterer import StoryClusterer

logger = logging.getLogger(__name__)


class PhaseCWeeklyBatchRunner:
    """Phase C 배치를 순서대로 실행한다."""

    def __init__(
        self,
        impact_calculator: Optional[EventImpactCalculator] = None,
        affects_recalculator: Optional[AffectsWeightRecalculator] = None,
        correlation_generator: Optional[CorrelationEdgeGenerator] = None,
        story_clusterer: Optional[StoryClusterer] = None,
        metrics_collector: Optional[PhaseCQualityMetrics] = None,
    ):
        self.impact_calculator = impact_calculator or EventImpactCalculator()
        self.affects_recalculator = affects_recalculator or AffectsWeightRecalculator()
        self.correlation_generator = correlation_generator or CorrelationEdgeGenerator()
        self.story_clusterer = story_clusterer or StoryClusterer()
        self.metrics_collector = metrics_collector or PhaseCQualityMetrics()

    def run(
        self,
        as_of_date: Optional[date] = None,
        impact_windows: Iterable[int] = (3, 7, 14),
        weight_windows: Iterable[int] = (90, 180),
        correlation_window_days: int = 180,
        story_window_days: int = 14,
    ) -> Dict[str, Any]:
        as_of_value = as_of_date or date.today()
        logger.info("[PhaseCWeeklyBatch] start as_of=%s", as_of_value.isoformat())

        event_impact_result = self.impact_calculator.calculate_for_all_windows(
            windows=impact_windows,
            as_of_date=as_of_value,
        )
        affects_result = self.affects_recalculator.recalculate_for_windows(
            windows=weight_windows,
            as_of_date=as_of_value,
        )
        correlation_result = self.correlation_generator.generate_edges(
            window_days=correlation_window_days,
            min_corr_edges=30,
            as_of_date=as_of_value,
        )
        story_result = self.story_clusterer.cluster_recent_documents(
            window_days=story_window_days,
            min_story_count=10,
            as_of_date=as_of_value,
        )
        metrics_result = self.metrics_collector.collect_summary()

        final_result = {
            "as_of": as_of_value.isoformat(),
            "event_impact": event_impact_result,
            "affects_recalc": affects_result,
            "correlation": correlation_result,
            "story_cluster": story_result,
            "metrics": metrics_result,
        }
        logger.info("[PhaseCWeeklyBatch] complete")
        return final_result


def run_phase_c_weekly_jobs(as_of_date: Optional[date] = None) -> Dict[str, Any]:
    runner = PhaseCWeeklyBatchRunner()
    return runner.run(as_of_date=as_of_date)
