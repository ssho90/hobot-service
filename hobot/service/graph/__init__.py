"""
Macro Knowledge Graph (MKG) Module
Phase A: 그래프 데이터 관리
"""
from .neo4j_client import Neo4jClient, get_neo4j_client
from .seed_data import run_all_seeds, seed_constraints, seed_themes, seed_indicators, seed_entities, verify_seed
from .indicator_loader import IndicatorLoader, sync_all_indicators
from .derived_feature_calc import DerivedFeatureCalculator, calculate_all_derived_features
from .news_loader import (
    NewsLoader,
    sync_news,
    sync_news_with_extraction,
    backfill_news_extractions,
    backfill_events_and_affects,
)
from .impact import EventImpactCalculator, AffectsWeightRecalculator, PhaseCQualityMetrics
from .stats import CorrelationEdgeGenerator
from .story import StoryClusterer
from .scheduler import PhaseCWeeklyBatchRunner, run_phase_c_weekly_jobs
from .state import AnalysisRunWriter, MacroStateGenerator, generate_macro_state
from .monitoring import GraphRagApiCallLogger, GraphRagMonitoringMetrics
from .rag import (
    GraphRagAnswerRequest,
    GraphRagAnswerResponse,
    GraphRagContextBuilder,
    GraphRagContextRequest,
    GraphRagContextResponse,
    build_graph_rag_context,
    generate_graph_rag_answer,
)

__all__ = [
    # Neo4j Client
    "Neo4jClient",
    "get_neo4j_client",
    # Seed Data (A-1 ~ A-4)
    "run_all_seeds",
    "seed_constraints",
    "seed_themes", 
    "seed_indicators",
    "seed_entities",
    "verify_seed",
    # Indicator Loader (A-5)
    "IndicatorLoader",
    "sync_all_indicators",
    # Derived Features (A-6)
    "DerivedFeatureCalculator",
    "calculate_all_derived_features",
    # News Loader (A-8)
    "NewsLoader",
    "sync_news",
    "sync_news_with_extraction",
    "backfill_news_extractions",
    "backfill_events_and_affects",
    # Phase C
    "EventImpactCalculator",
    "AffectsWeightRecalculator",
    "PhaseCQualityMetrics",
    "CorrelationEdgeGenerator",
    "StoryClusterer",
    "PhaseCWeeklyBatchRunner",
    "run_phase_c_weekly_jobs",
    # Phase D State
    "MacroStateGenerator",
    "AnalysisRunWriter",
    "generate_macro_state",
    # Phase D Monitoring
    "GraphRagApiCallLogger",
    "GraphRagMonitoringMetrics",
    # Phase D
    "GraphRagContextBuilder",
    "GraphRagContextRequest",
    "GraphRagContextResponse",
    "build_graph_rag_context",
    "GraphRagAnswerRequest",
    "GraphRagAnswerResponse",
    "generate_graph_rag_answer",
]
