"""
Admin macro indicator health snapshot utilities.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from service.database.db import get_db_connection
from service.macro_trading.collectors.fred_collector import FRED_INDICATORS

logger = logging.getLogger(__name__)

FREQUENCY_TO_INTERVAL_HOURS: Dict[str, int] = {
    "hourly": 1,
    "daily": 24,
    "weekly": 24 * 7,
    "monthly": 24 * 31,
    "quarterly": 24 * 92,
    "yearly": 24 * 366,
}

# Korean macro indicators share the same registry used by KR collectors.
# Connectors are available in phase2 (ECOS/KOSIS/FRED bridge), but runtime still
# depends on API key/environment readiness.
KR_INDICATOR_REGISTRY: List[Dict[str, Any]] = [
    {
        "code": "KR_BASE_RATE",
        "name": "Korea Base Rate",
        "description": "Bank of Korea policy rate",
        "country": "KR",
        "source": "ECOS",
        "frequency": "monthly",
        "unit": "%",
        "collection_enabled": True,
    },
    {
        "code": "KR_CPI",
        "name": "Korea Consumer Price Index",
        "description": "Korean CPI (headline)",
        "country": "KR",
        "source": "KOSIS",
        "frequency": "monthly",
        "unit": "Index",
        "collection_enabled": True,
    },
    {
        "code": "KR_UNEMPLOYMENT",
        "name": "Korea Unemployment Rate",
        "description": "Korean unemployment rate",
        "country": "KR",
        "source": "KOSIS",
        "frequency": "monthly",
        "unit": "%",
        "collection_enabled": True,
    },
    {
        "code": "KR_USDKRW",
        "name": "USD/KRW Exchange Rate",
        "description": "US dollar to Korean won exchange rate",
        "country": "KR",
        "source": "FRED",
        "frequency": "daily",
        "unit": "KRW",
        "collection_enabled": True,
    },
    {
        "code": "KR_HOUSE_PRICE_INDEX",
        "name": "Korea Housing Sale Price Index",
        "description": "REB/KOSIS sale price index",
        "country": "KR",
        "source": "KOSIS",
        "frequency": "monthly",
        "unit": "Index",
        "collection_enabled": True,
    },
    {
        "code": "KR_JEONSE_PRICE_RATIO",
        "name": "Korea Jeonse-to-Sale Price Ratio",
        "description": "REB/KOSIS jeonse ratio",
        "country": "KR",
        "source": "KOSIS",
        "frequency": "monthly",
        "unit": "%",
        "collection_enabled": True,
    },
    {
        "code": "KR_UNSOLD_HOUSING",
        "name": "Korea Unsold Housing Inventory",
        "description": "MOLIT/KOSIS unsold housing stock",
        "country": "KR",
        "source": "KOSIS",
        "frequency": "monthly",
        "unit": "count",
        "collection_enabled": True,
    },
    {
        "code": "KR_HOUSING_SUPPLY_APPROVAL",
        "name": "Korea Housing Supply (Permits/Approvals)",
        "description": "MOLIT/KOSIS housing supply flow",
        "country": "KR",
        "source": "KOSIS",
        "frequency": "monthly",
        "unit": "count",
        "collection_enabled": True,
    },
]

KR_CORPORATE_REGISTRY: List[Dict[str, Any]] = [
    {
        "code": "TIER1_CORPORATE_EVENT_SYNC",
        "name": "Tier-1 Corporate Event Sync Health",
        "description": "KR/US Tier-1 표준 이벤트 동기화 배치 상태",
        "country": "KR",
        "source": "INTERNAL",
        "frequency": "daily",
        "unit": "%",
        "storage": "corporate",
        "collection_enabled": True,
    },
    {
        "code": "KR_TOP50_ENTITY_REGISTRY",
        "name": "KR Top50 Entity Registry",
        "description": "KR 기업 canonical registry 최신성",
        "country": "KR",
        "source": "INTERNAL",
        "frequency": "daily",
        "unit": "count",
        "storage": "corporate",
        "collection_enabled": True,
    },
    {
        "code": "KR_TOP50_TIER_STATE",
        "name": "KR Top50 Tier State",
        "description": "KR Tier-1 상태 저장 최신성",
        "country": "KR",
        "source": "INTERNAL",
        "frequency": "daily",
        "unit": "count",
        "storage": "corporate",
        "collection_enabled": True,
    },
    {
        "code": "KR_TOP50_UNIVERSE_SNAPSHOT",
        "name": "KR Top50 Universe Snapshot",
        "description": "Top50 고정 유니버스 최신 스냅샷 상태",
        "country": "KR",
        "source": "INTERNAL",
        "frequency": "monthly",
        "unit": "count",
        "storage": "corporate",
        "collection_enabled": True,
    },
    {
        "code": "KR_TOP50_DAILY_OHLCV",
        "name": "KR Top50 Daily OHLCV",
        "description": "KR Top50 일별 OHLCV 최신 거래일 적재 상태",
        "country": "KR",
        "source": "INTERNAL",
        "frequency": "daily",
        "unit": "count",
        "storage": "corporate",
        "collection_enabled": True,
    },
    {
        "code": "KR_TOP50_CORP_CODE_MAPPING_VALIDATION",
        "name": "KR Top50 CorpCode Mapping Validation",
        "description": "Top50 스냅샷과 DART corp_code 매핑 정합성 검증 상태",
        "country": "KR",
        "source": "INTERNAL",
        "frequency": "daily",
        "unit": "issue_count",
        "storage": "corporate",
        "collection_enabled": True,
    },
    {
        "code": "KR_DART_DPLUS1_SLA",
        "name": "KR DART D+1 Ingestion SLA",
        "description": "실적 공시 대비 재무 반영 지연(D+1) 준수 여부",
        "country": "KR",
        "source": "INTERNAL",
        "frequency": "daily",
        "unit": "issue_count",
        "storage": "corporate",
        "collection_enabled": True,
    },
    {
        "code": "KR_TOP50_EARNINGS_WATCH_SUCCESS_RATE",
        "name": "KR Top50 Earnings Watch Success Rate",
        "description": "KR Top50 실적 감시 배치 일간 성공률",
        "country": "KR",
        "source": "INTERNAL",
        "frequency": "daily",
        "unit": "%",
        "storage": "corporate",
        "collection_enabled": True,
    },
    {
        "code": "KR_DART_CORP_CODES",
        "name": "KR DART Corp Code Cache",
        "description": "Open DART 기업코드 캐시 최신성",
        "country": "KR",
        "source": "DART",
        "frequency": "monthly",
        "unit": "count",
        "storage": "corporate",
        "collection_enabled": True,
    },
    {
        "code": "KR_DART_FINANCIALS_Q1",
        "name": "KR DART Financials (Q1)",
        "description": "Open DART 1분기 재무 주요계정",
        "country": "KR",
        "source": "DART",
        "frequency": "quarterly",
        "unit": "count",
        "storage": "corporate",
        "collection_enabled": True,
    },
    {
        "code": "KR_DART_FINANCIALS_H1",
        "name": "KR DART Financials (H1)",
        "description": "Open DART 반기 재무 주요계정",
        "country": "KR",
        "source": "DART",
        "frequency": "quarterly",
        "unit": "count",
        "storage": "corporate",
        "collection_enabled": True,
    },
    {
        "code": "KR_DART_FINANCIALS_Q3",
        "name": "KR DART Financials (Q3)",
        "description": "Open DART 3분기 재무 주요계정",
        "country": "KR",
        "source": "DART",
        "frequency": "quarterly",
        "unit": "count",
        "storage": "corporate",
        "collection_enabled": True,
    },
    {
        "code": "KR_DART_FINANCIALS_Y",
        "name": "KR DART Financials (Annual)",
        "description": "Open DART 사업보고서 재무 주요계정",
        "country": "KR",
        "source": "DART",
        "frequency": "yearly",
        "unit": "count",
        "storage": "corporate",
        "collection_enabled": True,
    },
    {
        "code": "KR_DART_DISCLOSURE_EARNINGS",
        "name": "KR DART Earnings Disclosures",
        "description": "Open DART 실적 공시 이벤트 수집",
        "country": "KR",
        "source": "DART",
        "frequency": "daily",
        "unit": "count",
        "storage": "corporate",
        "collection_enabled": True,
    },
    {
        "code": "KR_DART_EARNINGS_EXPECTATION",
        "name": "KR Earnings Expectations",
        "description": "실적 기대값(actual/expected 비교용) 적재 상태",
        "country": "KR",
        "source": "INTERNAL",
        "frequency": "quarterly",
        "unit": "count",
        "storage": "corporate",
        "collection_enabled": True,
    },
    {
        "code": "KR_REAL_ESTATE_TRANSACTIONS",
        "name": "KR Real Estate Transactions",
        "description": "국내 실거래 원천 row 최신 적재 상태",
        "country": "KR",
        "source": "MOLIT",
        "frequency": "daily",
        "unit": "count",
        "storage": "corporate",
        "collection_enabled": True,
    },
    {
        "code": "KR_REAL_ESTATE_MONTHLY_SUMMARY",
        "name": "KR Real Estate Monthly Summary",
        "description": "국내 실거래 월간 집계 최신 적재 상태",
        "country": "KR",
        "source": "MOLIT",
        "frequency": "daily",
        "unit": "count",
        "storage": "corporate",
        "collection_enabled": True,
    },
]

GRAPH_REGISTRY: List[Dict[str, Any]] = [
    {
        "code": "EQUITY_GRAPH_PROJECTION_SYNC",
        "name": "Equity Graph Projection Sync",
        "description": "주식 Projection(RDB->Neo4j) 동기화 실행 및 지연 상태",
        "country": "GLOBAL",
        "source": "INTERNAL",
        "frequency": "daily",
        "unit": "%",
        "storage": "corporate",
        "collection_enabled": True,
    },
    {
        "code": "GRAPH_NEWS_EXTRACTION_SYNC",
        "name": "Graph News Extraction Sync",
        "description": "뉴스 동기화+추출+임베딩 배치 실행 성공률",
        "country": "GLOBAL",
        "source": "INTERNAL",
        "frequency": "hourly",
        "unit": "%",
        "storage": "corporate",
        "collection_enabled": True,
    },
    {
        "code": "GRAPH_RAG_PHASE5_WEEKLY_REPORT",
        "name": "Graph RAG Phase5 Weekly Regression",
        "description": "Phase5 회귀 주간 집계 실행 상태",
        "country": "GLOBAL",
        "source": "INTERNAL",
        "frequency": "weekly",
        "unit": "%",
        "storage": "corporate",
        "collection_enabled": True,
    },
    {
        "code": "GRAPH_DOCUMENT_EMBEDDING_COVERAGE",
        "name": "Graph Document Embedding Coverage",
        "description": "Document 노드 임베딩 커버리지(%)",
        "country": "GLOBAL",
        "source": "NEO4J",
        "frequency": "hourly",
        "unit": "%",
        "storage": "graph",
        "collection_enabled": True,
    },
    {
        "code": "GRAPH_RAG_VECTOR_INDEX_READY",
        "name": "Graph RAG Vector Index Readiness",
        "description": "Neo4j vector index(document_text_embedding_idx) 상태",
        "country": "GLOBAL",
        "source": "NEO4J",
        "frequency": "hourly",
        "unit": "flag",
        "storage": "graph",
        "collection_enabled": True,
    },
]

PIPELINE_REGISTRY: List[Dict[str, Any]] = [
    {
        "code": "ECONOMIC_NEWS_STREAM",
        "name": "Economic News Stream",
        "description": "economic_news 수집 파이프라인 최신 적재 상태",
        "country": "GLOBAL",
        "source": "INTERNAL",
        "frequency": "hourly",
        "unit": "count",
        "storage": "corporate",
        "collection_enabled": True,
    },
    {
        "code": "TIER1_CORPORATE_EVENT_FEED",
        "name": "Tier-1 Corporate Event Feed",
        "description": "corporate_event_feed 최신 적재 상태",
        "country": "GLOBAL",
        "source": "INTERNAL",
        "frequency": "hourly",
        "unit": "count",
        "storage": "corporate",
        "collection_enabled": True,
    },
]

US_CORPORATE_REGISTRY: List[Dict[str, Any]] = [
    {
        "code": "US_TOP50_ENTITY_REGISTRY",
        "name": "US Top50 Entity Registry",
        "description": "US 기업 canonical registry 최신성",
        "country": "US",
        "source": "INTERNAL",
        "frequency": "daily",
        "unit": "count",
        "storage": "corporate",
        "collection_enabled": True,
    },
    {
        "code": "US_TOP50_TIER_STATE",
        "name": "US Top50 Tier State",
        "description": "US Tier-1 상태 저장 최신성",
        "country": "US",
        "source": "INTERNAL",
        "frequency": "daily",
        "unit": "count",
        "storage": "corporate",
        "collection_enabled": True,
    },
    {
        "code": "US_TOP50_UNIVERSE_SNAPSHOT",
        "name": "US Top50 Universe Snapshot",
        "description": "US Top50 유니버스 최신 스냅샷 상태",
        "country": "US",
        "source": "INTERNAL",
        "frequency": "monthly",
        "unit": "count",
        "storage": "corporate",
        "collection_enabled": True,
    },
    {
        "code": "US_TOP50_DAILY_OHLCV",
        "name": "US Top50 Daily OHLCV",
        "description": "US Top50 일별 OHLCV 최신 거래일 적재 상태",
        "country": "US",
        "source": "INTERNAL",
        "frequency": "daily",
        "unit": "count",
        "storage": "corporate",
        "collection_enabled": True,
    },
    {
        "code": "US_TOP50_FINANCIALS",
        "name": "US Top50 Financial Statements",
        "description": "yfinance 기반 미국 Top50 재무제표(연간/분기)",
        "country": "US",
        "source": "YFINANCE",
        "frequency": "quarterly",
        "unit": "count",
        "storage": "corporate",
        "collection_enabled": True,
    },
    {
        "code": "US_SEC_CIK_MAPPING",
        "name": "US SEC CIK Mapping Cache",
        "description": "SEC ticker/cik 매핑 최신성",
        "country": "US",
        "source": "SEC",
        "frequency": "monthly",
        "unit": "count",
        "storage": "corporate",
        "collection_enabled": True,
    },
    {
        "code": "US_TOP50_EARNINGS_EVENTS_CONFIRMED",
        "name": "US Top50 Earnings Events (Confirmed)",
        "description": "SEC 확정 실적 이벤트(8-K/10-Q/10-K)",
        "country": "US",
        "source": "SEC",
        "frequency": "daily",
        "unit": "count",
        "storage": "corporate",
        "collection_enabled": True,
    },
    {
        "code": "US_TOP50_EARNINGS_EVENTS_EXPECTED",
        "name": "US Top50 Earnings Events (Expected)",
        "description": "yfinance 실적 발표 예정 이벤트",
        "country": "US",
        "source": "YFINANCE",
        "frequency": "daily",
        "unit": "count",
        "storage": "corporate",
        "collection_enabled": True,
    },
    {
        "code": "US_TOP50_EARNINGS_WATCH_SUCCESS_RATE",
        "name": "US Top50 Earnings Watch Success Rate",
        "description": "US Top50 실적 감시 배치 일간 성공률",
        "country": "US",
        "source": "INTERNAL",
        "frequency": "daily",
        "unit": "%",
        "storage": "corporate",
        "collection_enabled": True,
    },
]

RUN_HEALTH_JOB_CODES = {
    "KR_TOP50_EARNINGS_WATCH_SUCCESS_RATE",
    "US_TOP50_EARNINGS_WATCH_SUCCESS_RATE",
    "TIER1_CORPORATE_EVENT_SYNC",
    "GRAPH_NEWS_EXTRACTION_SYNC",
    "EQUITY_GRAPH_PROJECTION_SYNC",
    "GRAPH_RAG_PHASE5_WEEKLY_REPORT",
}


def _frequency_to_interval_hours(frequency: str) -> int:
    return FREQUENCY_TO_INTERVAL_HOURS.get((frequency or "").lower(), 24)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _safe_int_env(name: str, default: int) -> int:
    return _safe_int(os.getenv(name), default)


def _safe_float_env(name: str, default: float) -> float:
    return _safe_float(os.getenv(name), default)


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_iso(value: Any) -> Optional[str]:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None


def _build_us_registry() -> List[Dict[str, Any]]:
    registry: List[Dict[str, Any]] = []
    for code, info in FRED_INDICATORS.items():
        registry.append(
            {
                "code": code,
                "name": info.get("name", code),
                "description": info.get("name", code),
                "country": "US",
                "source": "FRED",
                "frequency": info.get("frequency", "daily"),
                "unit": info.get("unit", ""),
                "collection_enabled": True,
            }
        )
    return registry


def _load_latest_fred_rows() -> Dict[str, Dict[str, Any]]:
    latest_rows: Dict[str, Dict[str, Any]] = {}

    query = """
        SELECT
            t1.indicator_code,
            t1.date AS last_observation_date,
            t1.value AS latest_value,
            t1.created_at AS last_collected_at
        FROM fred_data t1
        INNER JOIN (
            SELECT indicator_code, MAX(date) AS max_date
            FROM fred_data
            GROUP BY indicator_code
        ) t2
          ON t1.indicator_code = t2.indicator_code
         AND t1.date = t2.max_date
    """

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            for row in cursor.fetchall():
                latest_rows[row["indicator_code"]] = row
    except Exception as exc:
        logger.warning("Failed to load latest FRED rows for indicator health: %s", exc)

    return latest_rows


def _load_latest_corporate_rows() -> Dict[str, Dict[str, Any]]:
    latest_rows: Dict[str, Dict[str, Any]] = {}

    query_map: Dict[str, Dict[str, str]] = {
        "US_TOP50_ENTITY_REGISTRY": {
            "table": "corporate_entity_registry",
            "query": """
            SELECT
                MAX(DATE(updated_at)) AS last_observation_date,
                MAX(updated_at) AS last_collected_at,
                COUNT(*) AS latest_value
            FROM corporate_entity_registry
            WHERE country_code = 'US'
              AND is_active = 1
        """,
        },
        "US_TOP50_TIER_STATE": {
            "table": "corporate_tier_state",
            "query": """
            SELECT
                MAX(as_of_date) AS last_observation_date,
                MAX(updated_at) AS last_collected_at,
                COUNT(*) AS latest_value
            FROM corporate_tier_state
            WHERE country_code = 'US'
              AND tier_level = 1
              AND is_active = 1
              AND as_of_date = (
                  SELECT MAX(as_of_date)
                  FROM corporate_tier_state
                  WHERE country_code = 'US'
                    AND tier_level = 1
                    AND is_active = 1
              )
        """,
        },
        "US_TOP50_UNIVERSE_SNAPSHOT": {
            "table": "us_top50_universe_snapshot",
            "query": """
            SELECT
                MAX(latest.snapshot_date) AS last_observation_date,
                MAX(latest.updated_at) AS last_collected_at,
                COUNT(*) AS latest_value
            FROM us_top50_universe_snapshot latest
            WHERE latest.market = 'US'
              AND latest.snapshot_date = (
                  SELECT MAX(snapshot_date)
                  FROM us_top50_universe_snapshot
                  WHERE market = 'US'
              )
        """,
        },
        "US_TOP50_DAILY_OHLCV": {
            "table": "us_top50_daily_ohlcv",
            "query": """
            SELECT
                MAX(latest.trade_date) AS last_observation_date,
                MAX(latest.updated_at) AS last_collected_at,
                COUNT(*) AS latest_value,
                COUNT(DISTINCT latest.symbol) AS symbol_count
            FROM us_top50_daily_ohlcv latest
            WHERE latest.market = 'US'
              AND latest.trade_date = (
                  SELECT MAX(trade_date)
                  FROM us_top50_daily_ohlcv
                  WHERE market = 'US'
              )
        """,
        },
        "US_TOP50_FINANCIALS": {
            "table": "us_corporate_financials",
            "query": """
            SELECT
                MAX(period_end_date) AS last_observation_date,
                MAX(updated_at) AS last_collected_at,
                COUNT(*) AS latest_value
            FROM us_corporate_financials
        """,
        },
        "US_SEC_CIK_MAPPING": {
            "table": "us_sec_cik_mapping",
            "query": """
            SELECT
                MAX(DATE(updated_at)) AS last_observation_date,
                MAX(updated_at) AS last_collected_at,
                COUNT(*) AS latest_value
            FROM us_sec_cik_mapping
        """,
        },
        "US_TOP50_EARNINGS_EVENTS_CONFIRMED": {
            "table": "us_corporate_earnings_events",
            "query": """
            SELECT
                MAX(event_date) AS last_observation_date,
                MAX(updated_at) AS last_collected_at,
                COUNT(*) AS latest_value
            FROM us_corporate_earnings_events
            WHERE event_status = 'confirmed'
        """,
        },
        "US_TOP50_EARNINGS_EVENTS_EXPECTED": {
            "table": "us_corporate_earnings_events",
            "query": """
            SELECT
                MAX(event_date) AS last_observation_date,
                MAX(updated_at) AS last_collected_at,
                COUNT(*) AS latest_value
            FROM us_corporate_earnings_events
            WHERE event_status = 'expected'
        """,
        },
        "US_TOP50_EARNINGS_WATCH_SUCCESS_RATE": {
            "table": "macro_collection_run_reports",
            "query": """
            SELECT
                latest.report_date AS last_observation_date,
                latest.last_run_finished_at AS last_collected_at,
                CASE
                    WHEN (latest.success_count + latest.failure_count) > 0
                        THEN ROUND((latest.success_count * 100.0) / (latest.success_count + latest.failure_count), 2)
                    WHEN latest.success_run_count > 0
                        THEN 100
                    ELSE 0
                END AS latest_value,
                latest.run_count,
                latest.success_run_count,
                latest.failed_run_count,
                latest.success_count,
                latest.failure_count,
                latest.last_status,
                latest.last_error,
                latest.details_json
            FROM macro_collection_run_reports latest
            WHERE latest.job_code = 'US_TOP50_EARNINGS_WATCH'
            ORDER BY latest.report_date DESC, latest.updated_at DESC
            LIMIT 1
        """,
        },
        "GRAPH_NEWS_EXTRACTION_SYNC": {
            "table": "macro_collection_run_reports",
            "query": """
            SELECT
                latest.report_date AS last_observation_date,
                latest.last_run_finished_at AS last_collected_at,
                CASE
                    WHEN (latest.success_count + latest.failure_count) > 0
                        THEN ROUND((latest.success_count * 100.0) / (latest.success_count + latest.failure_count), 2)
                    WHEN latest.success_run_count > 0
                        THEN 100
                    ELSE 0
                END AS latest_value,
                latest.run_count,
                latest.success_run_count,
                latest.failed_run_count,
                latest.success_count,
                latest.failure_count,
                latest.last_status,
                latest.last_error,
                latest.details_json
            FROM macro_collection_run_reports latest
            WHERE latest.job_code = 'GRAPH_NEWS_EXTRACTION_SYNC'
            ORDER BY latest.report_date DESC, latest.updated_at DESC
            LIMIT 1
        """,
        },
        "EQUITY_GRAPH_PROJECTION_SYNC": {
            "table": "macro_collection_run_reports",
            "query": """
            SELECT
                latest.report_date AS last_observation_date,
                latest.last_run_finished_at AS last_collected_at,
                CASE
                    WHEN (latest.success_count + latest.failure_count) > 0
                        THEN ROUND((latest.success_count * 100.0) / (latest.success_count + latest.failure_count), 2)
                    WHEN latest.success_run_count > 0
                        THEN 100
                    ELSE 0
                END AS latest_value,
                latest.run_count,
                latest.success_run_count,
                latest.failed_run_count,
                latest.success_count,
                latest.failure_count,
                latest.last_status,
                latest.last_error,
                latest.details_json
            FROM macro_collection_run_reports latest
            WHERE latest.job_code = 'EQUITY_GRAPH_PROJECTION_SYNC'
            ORDER BY latest.report_date DESC, latest.updated_at DESC
            LIMIT 1
        """,
        },
        "GRAPH_RAG_PHASE5_WEEKLY_REPORT": {
            "table": "macro_collection_run_reports",
            "query": """
            SELECT
                latest.report_date AS last_observation_date,
                latest.last_run_finished_at AS last_collected_at,
                CASE
                    WHEN (latest.success_count + latest.failure_count) > 0
                        THEN ROUND((latest.success_count * 100.0) / (latest.success_count + latest.failure_count), 2)
                    WHEN latest.success_run_count > 0
                        THEN 100
                    ELSE 0
                END AS latest_value,
                latest.run_count,
                latest.success_run_count,
                latest.failed_run_count,
                latest.success_count,
                latest.failure_count,
                latest.last_status,
                latest.last_error,
                latest.details_json
            FROM macro_collection_run_reports latest
            WHERE latest.job_code = 'GRAPH_RAG_PHASE5_WEEKLY_REPORT'
            ORDER BY latest.report_date DESC, latest.updated_at DESC
            LIMIT 1
        """,
        },
        "TIER1_CORPORATE_EVENT_SYNC": {
            "table": "macro_collection_run_reports",
            "query": """
            SELECT
                latest.report_date AS last_observation_date,
                latest.last_run_finished_at AS last_collected_at,
                CASE
                    WHEN (latest.success_count + latest.failure_count) > 0
                        THEN ROUND((latest.success_count * 100.0) / (latest.success_count + latest.failure_count), 2)
                    WHEN latest.success_run_count > 0
                        THEN 100
                    ELSE 0
                END AS latest_value,
                latest.run_count,
                latest.success_run_count,
                latest.failed_run_count,
                latest.success_count,
                latest.failure_count,
                latest.last_status,
                latest.last_error,
                latest.details_json
            FROM macro_collection_run_reports latest
            WHERE latest.job_code = 'TIER1_CORPORATE_EVENT_SYNC'
            ORDER BY latest.report_date DESC, latest.updated_at DESC
            LIMIT 1
        """,
        },
        "ECONOMIC_NEWS_STREAM": {
            "table": "economic_news",
            "query": """
            SELECT
                MAX(DATE(COALESCE(latest.observed_at, latest.release_date, latest.published_at, latest.created_at))) AS last_observation_date,
                MAX(latest.updated_at) AS last_collected_at,
                COUNT(*) AS latest_value,
                COUNT(DISTINCT COALESCE(latest.source_type, latest.source, 'unknown')) AS source_count,
                COUNT(DISTINCT COALESCE(latest.category, 'unknown')) AS category_count
            FROM economic_news latest
            WHERE DATE(COALESCE(latest.observed_at, latest.release_date, latest.published_at, latest.created_at)) = (
                SELECT MAX(DATE(COALESCE(observed_at, release_date, published_at, created_at)))
                FROM economic_news
            )
        """,
        },
        "TIER1_CORPORATE_EVENT_FEED": {
            "table": "corporate_event_feed",
            "query": """
            SELECT
                MAX(latest.event_date) AS last_observation_date,
                MAX(latest.updated_at) AS last_collected_at,
                COUNT(*) AS latest_value,
                COUNT(DISTINCT latest.symbol) AS symbol_count,
                COUNT(DISTINCT latest.country_code) AS country_count
            FROM corporate_event_feed latest
            WHERE latest.event_date = (
                SELECT MAX(event_date)
                FROM corporate_event_feed
            )
        """,
        },
        "KR_TOP50_ENTITY_REGISTRY": {
            "table": "corporate_entity_registry",
            "query": """
            SELECT
                MAX(DATE(updated_at)) AS last_observation_date,
                MAX(updated_at) AS last_collected_at,
                COUNT(*) AS latest_value
            FROM corporate_entity_registry
            WHERE country_code = 'KR'
              AND is_active = 1
        """,
        },
        "KR_TOP50_TIER_STATE": {
            "table": "corporate_tier_state",
            "query": """
            SELECT
                MAX(as_of_date) AS last_observation_date,
                MAX(updated_at) AS last_collected_at,
                COUNT(*) AS latest_value
            FROM corporate_tier_state
            WHERE country_code = 'KR'
              AND tier_level = 1
              AND is_active = 1
              AND as_of_date = (
                  SELECT MAX(as_of_date)
                  FROM corporate_tier_state
                  WHERE country_code = 'KR'
                    AND tier_level = 1
                    AND is_active = 1
              )
        """,
        },
        "KR_TOP50_UNIVERSE_SNAPSHOT": {
            "table": "kr_top50_universe_snapshot",
            "query": """
            SELECT
                MAX(latest.snapshot_date) AS last_observation_date,
                MAX(latest.updated_at) AS last_collected_at,
                COUNT(*) AS latest_value
            FROM kr_top50_universe_snapshot latest
            WHERE latest.market = 'KOSPI'
              AND latest.snapshot_date = (
                  SELECT MAX(snapshot_date)
                  FROM kr_top50_universe_snapshot
                  WHERE market = 'KOSPI'
              )
        """,
        },
        "KR_TOP50_DAILY_OHLCV": {
            "table": "kr_top50_daily_ohlcv",
            "query": """
            SELECT
                MAX(latest.trade_date) AS last_observation_date,
                MAX(latest.updated_at) AS last_collected_at,
                COUNT(*) AS latest_value,
                COUNT(DISTINCT latest.stock_code) AS symbol_count
            FROM kr_top50_daily_ohlcv latest
            WHERE latest.market = 'KOSPI'
              AND latest.trade_date = (
                  SELECT MAX(trade_date)
                  FROM kr_top50_daily_ohlcv
                  WHERE market = 'KOSPI'
              )
        """,
        },
        "KR_TOP50_CORP_CODE_MAPPING_VALIDATION": {
            "table": "kr_corp_code_mapping_reports",
            "query": """
            SELECT
                latest.report_date AS last_observation_date,
                latest.updated_at AS last_collected_at,
                (
                    latest.snapshot_missing_corp_count
                    + latest.snapshot_missing_in_dart_count
                    + latest.snapshot_corp_code_mismatch_count
                    + latest.dart_duplicate_stock_count
                ) AS latest_value
            FROM kr_corp_code_mapping_reports latest
            WHERE latest.market = 'KOSPI'
            ORDER BY latest.report_date DESC, latest.updated_at DESC
            LIMIT 1
        """,
        },
        "KR_DART_DPLUS1_SLA": {
            "table": "kr_dart_dplus1_sla_reports",
            "query": """
            SELECT
                latest.report_date AS last_observation_date,
                latest.updated_at AS last_collected_at,
                latest.violated_sla_count AS latest_value,
                latest.checked_event_count,
                latest.met_sla_count,
                latest.violated_sla_count,
                latest.missing_financial_count,
                latest.late_financial_count,
                latest.status
            FROM kr_dart_dplus1_sla_reports latest
            WHERE latest.market = 'KOSPI'
            ORDER BY latest.report_date DESC, latest.updated_at DESC
            LIMIT 1
        """,
        },
        "KR_TOP50_EARNINGS_WATCH_SUCCESS_RATE": {
            "table": "macro_collection_run_reports",
            "query": """
            SELECT
                latest.report_date AS last_observation_date,
                latest.last_run_finished_at AS last_collected_at,
                CASE
                    WHEN (latest.success_count + latest.failure_count) > 0
                        THEN ROUND((latest.success_count * 100.0) / (latest.success_count + latest.failure_count), 2)
                    WHEN latest.success_run_count > 0
                        THEN 100
                    ELSE 0
                END AS latest_value,
                latest.run_count,
                latest.success_run_count,
                latest.failed_run_count,
                latest.success_count,
                latest.failure_count,
                latest.last_status,
                latest.last_error,
                latest.details_json
            FROM macro_collection_run_reports latest
            WHERE latest.job_code = 'KR_TOP50_EARNINGS_WATCH'
            ORDER BY latest.report_date DESC, latest.updated_at DESC
            LIMIT 1
        """,
        },
        "KR_DART_CORP_CODES": {
            "table": "kr_dart_corp_codes",
            "query": """
            SELECT
                MAX(DATE(updated_at)) AS last_observation_date,
                MAX(updated_at) AS last_collected_at,
                COUNT(*) AS latest_value
            FROM kr_dart_corp_codes
        """,
        },
        "KR_DART_FINANCIALS_Q1": {
            "table": "kr_corporate_financials",
            "query": """
            SELECT
                MAX(as_of_date) AS last_observation_date,
                MAX(updated_at) AS last_collected_at,
                COUNT(*) AS latest_value
            FROM kr_corporate_financials
            WHERE reprt_code = '11013'
        """,
        },
        "KR_DART_FINANCIALS_H1": {
            "table": "kr_corporate_financials",
            "query": """
            SELECT
                MAX(as_of_date) AS last_observation_date,
                MAX(updated_at) AS last_collected_at,
                COUNT(*) AS latest_value
            FROM kr_corporate_financials
            WHERE reprt_code = '11012'
        """,
        },
        "KR_DART_FINANCIALS_Q3": {
            "table": "kr_corporate_financials",
            "query": """
            SELECT
                MAX(as_of_date) AS last_observation_date,
                MAX(updated_at) AS last_collected_at,
                COUNT(*) AS latest_value
            FROM kr_corporate_financials
            WHERE reprt_code = '11014'
        """,
        },
        "KR_DART_FINANCIALS_Y": {
            "table": "kr_corporate_financials",
            "query": """
            SELECT
                MAX(as_of_date) AS last_observation_date,
                MAX(updated_at) AS last_collected_at,
                COUNT(*) AS latest_value
            FROM kr_corporate_financials
            WHERE reprt_code = '11011'
        """,
        },
        "KR_DART_DISCLOSURE_EARNINGS": {
            "table": "kr_corporate_disclosures",
            "query": """
            SELECT
                MAX(rcept_dt) AS last_observation_date,
                MAX(updated_at) AS last_collected_at,
                COUNT(*) AS latest_value
            FROM kr_corporate_disclosures
            WHERE is_earnings_event = 1
               OR event_type IN ('earnings_announcement', 'periodic_report')
               OR report_nm LIKE '%%분기보고서%%'
               OR report_nm LIKE '%%반기보고서%%'
               OR report_nm LIKE '%%사업보고서%%'
        """,
        },
        "KR_DART_EARNINGS_EXPECTATION": {
            "table": "kr_corporate_earnings_expectations",
            "query": """
            SELECT
                MAX(expected_as_of_date) AS last_observation_date,
                MAX(updated_at) AS last_collected_at,
                COUNT(*) AS latest_value
            FROM kr_corporate_earnings_expectations
        """,
        },
        "KR_REAL_ESTATE_TRANSACTIONS": {
            "table": "kr_real_estate_transactions",
            "query": """
            SELECT
                MAX(latest.contract_date) AS last_observation_date,
                MAX(latest.updated_at) AS last_collected_at,
                COUNT(*) AS latest_value,
                COUNT(DISTINCT LEFT(latest.region_code, 5)) AS region_count
            FROM kr_real_estate_transactions latest
            WHERE latest.contract_date = (
                SELECT MAX(contract_date)
                FROM kr_real_estate_transactions
            )
        """,
        },
        "KR_REAL_ESTATE_MONTHLY_SUMMARY": {
            "table": "kr_real_estate_monthly_summary",
            "query": """
            SELECT
                MAX(latest.as_of_date) AS last_observation_date,
                MAX(latest.updated_at) AS last_collected_at,
                COUNT(*) AS latest_value,
                COUNT(DISTINCT latest.lawd_cd) AS region_count
            FROM kr_real_estate_monthly_summary latest
            WHERE latest.stat_ym = (
                SELECT MAX(stat_ym)
                FROM kr_real_estate_monthly_summary
            )
        """,
        },
    }

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SHOW TABLES")
            existing_tables = {
                str(value)
                for row in cursor.fetchall()
                for value in row.values()
                if value is not None
            }
            for code, spec in query_map.items():
                table_name = spec["table"]
                query = spec["query"]
                if table_name not in existing_tables:
                    continue
                try:
                    cursor.execute(query)
                    row = cursor.fetchone() or {}
                    normalized_row = dict(row)
                    normalized_row["last_observation_date"] = row.get("last_observation_date")
                    normalized_row["last_collected_at"] = row.get("last_collected_at")
                    normalized_row["latest_value"] = row.get("latest_value")
                    latest_rows[code] = normalized_row
                except Exception as query_exc:
                    logger.warning("Failed to load corporate indicator row(%s): %s", code, query_exc)
    except Exception as exc:
        logger.warning("Failed to load corporate indicator rows: %s", exc)

    return latest_rows


def _load_latest_graph_rows() -> Dict[str, Dict[str, Any]]:
    latest_rows: Dict[str, Dict[str, Any]] = {}
    vector_index_name = (
        str(os.getenv("GRAPH_RAG_VECTOR_INDEX_NAME") or "document_text_embedding_idx").strip()
        or "document_text_embedding_idx"
    )
    try:
        from service.graph.neo4j_client import get_neo4j_client

        client = get_neo4j_client()
        rows = client.run_read(
            """
            MATCH (d:Document)
            RETURN count(d) AS total_docs,
                   sum(CASE WHEN d.text_embedding IS NOT NULL THEN 1 ELSE 0 END) AS embedded_docs,
                   sum(CASE WHEN coalesce(d.embedding_status, '') = 'failed' THEN 1 ELSE 0 END) AS failed_docs,
                   max(d.embedding_updated_at) AS last_collected_at,
                   max(coalesce(d.updated_at, d.published_at)) AS last_observation_date
            """
        )
        row = rows[0] if rows else {}
        total_docs = int(row.get("total_docs") or 0)
        embedded_docs = int(row.get("embedded_docs") or 0)
        failed_docs = int(row.get("failed_docs") or 0)
        coverage_pct = round((embedded_docs * 100.0 / total_docs), 2) if total_docs > 0 else 0.0

        latest_rows["GRAPH_DOCUMENT_EMBEDDING_COVERAGE"] = {
            "last_observation_date": row.get("last_observation_date"),
            "last_collected_at": row.get("last_collected_at"),
            "latest_value": coverage_pct,
            "total_docs": total_docs,
            "embedded_docs": embedded_docs,
            "failed_docs": failed_docs,
        }

        index_row: Dict[str, Any] = {}
        try:
            index_rows = client.run_read(
                """
                SHOW VECTOR INDEXES
                YIELD name, state, populationPercent
                WHERE name = $index_name
                RETURN name, state, populationPercent
                LIMIT 1
                """,
                {"index_name": vector_index_name},
            )
            if index_rows:
                index_row = dict(index_rows[0])
        except Exception:
            try:
                index_rows = client.run_read(
                    """
                    SHOW INDEXES
                    YIELD name, type, state, populationPercent
                    WHERE name = $index_name AND type = 'VECTOR'
                    RETURN name, state, populationPercent
                    LIMIT 1
                    """,
                    {"index_name": vector_index_name},
                )
                if index_rows:
                    index_row = dict(index_rows[0])
            except Exception as index_exc:
                logger.warning("Failed to load vector index status: %s", index_exc)

        index_state = str(index_row.get("state") or "missing").upper()
        population_percent = _as_float(index_row.get("populationPercent"))
        latest_rows["GRAPH_RAG_VECTOR_INDEX_READY"] = {
            "last_observation_date": date.today(),
            "last_collected_at": datetime.now(),
            "latest_value": 1 if index_state == "ONLINE" else 0,
            "index_state": index_state,
            "population_percent": population_percent,
            "index_name": vector_index_name,
        }
    except Exception as exc:
        logger.warning("Failed to load graph indicator rows: %s", exc)

    return latest_rows


def _normalize_expectation_source(source: Any) -> str:
    normalized = str(source or "").strip().lower()
    if normalized in {"feed", "consensus_feed"}:
        return "feed"
    if normalized in {"auto_baseline", "baseline"}:
        return "baseline"
    if normalized in {"manual", "admin", "user"}:
        return "manual"
    return normalized or "unknown"


def _parse_json_object(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _normalize_run_health_status(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"healthy", "warning", "failed"}:
        return normalized
    if normalized in {"warn", "degraded", "stale"}:
        return "warning"
    if normalized in {"error", "fatal"}:
        return "failed"
    return ""


def _derive_graph_news_sync_health(row: Dict[str, Any]) -> tuple[str, str]:
    details = _parse_json_object(row.get("details_json"))
    explicit_status = _normalize_run_health_status(row.get("last_status"))
    if explicit_status == "failed":
        return "failed", "last_status=failed"

    extraction_success_docs = _safe_int(details.get("extraction_success_docs"))
    extraction_failed_docs = _safe_int(details.get("extraction_failed_docs"))
    embedding_success_docs = _safe_int(details.get("embedding_embedded_docs"))
    embedding_failed_docs = _safe_int(details.get("embedding_failed_docs"))
    success_count = max(
        _safe_int(row.get("success_count")),
        extraction_success_docs + embedding_success_docs,
    )
    failure_count = max(
        _safe_int(row.get("failure_count")),
        extraction_failed_docs + embedding_failed_docs,
    )
    total_count = success_count + failure_count
    failure_rate_pct = (failure_count * 100.0 / total_count) if total_count > 0 else 0.0

    warn_failure_count = max(_safe_int_env("GRAPH_NEWS_SYNC_WARN_FAILURE_COUNT", 10), 1)
    fail_failure_count = max(
        _safe_int_env("GRAPH_NEWS_SYNC_FAIL_FAILURE_COUNT", 50),
        warn_failure_count,
    )
    warn_failure_rate_pct = max(
        _safe_float_env("GRAPH_NEWS_SYNC_WARN_FAILURE_RATE_PCT", 5.0),
        0.0,
    )
    fail_failure_rate_pct = max(
        _safe_float_env("GRAPH_NEWS_SYNC_FAIL_FAILURE_RATE_PCT", 20.0),
        warn_failure_rate_pct,
    )

    sync_failed = bool(details.get("sync_failed"))
    embedding_status = str(details.get("embedding_status") or "").strip().lower()

    if (
        sync_failed
        or failure_count >= fail_failure_count
        or failure_rate_pct >= fail_failure_rate_pct
    ):
        return (
            "failed",
            f"failure_count={failure_count}, failure_rate={failure_rate_pct:.1f}%",
        )

    if (
        explicit_status == "warning"
        or embedding_status in {"failed", "partial_success"}
        or failure_count >= warn_failure_count
        or failure_rate_pct >= warn_failure_rate_pct
    ):
        return (
            "warning",
            f"failure_count={failure_count}, failure_rate={failure_rate_pct:.1f}%",
        )

    return "healthy", f"failure_count={failure_count}, failure_rate={failure_rate_pct:.1f}%"


def _derive_run_health_status(code: str, row: Dict[str, Any]) -> tuple[str, str]:
    if code == "GRAPH_NEWS_EXTRACTION_SYNC":
        return _derive_graph_news_sync_health(row)

    explicit_status = _normalize_run_health_status(row.get("last_status"))
    if explicit_status:
        return explicit_status, f"last_status={explicit_status}"

    success_count = _safe_int(row.get("success_count"))
    failure_count = _safe_int(row.get("failure_count"))
    if failure_count <= 0:
        return "healthy", "failure_count=0"
    if success_count <= 0:
        return "failed", f"success_count={success_count}, failure_count={failure_count}"
    return "warning", f"success_count={success_count}, failure_count={failure_count}"


def _load_latest_expectation_source_breakdown() -> Optional[str]:
    query = """
        SELECT expected_source, COUNT(*) AS cnt
        FROM kr_corporate_earnings_expectations
        WHERE COALESCE(expected_as_of_date, DATE(updated_at)) = (
            SELECT MAX(COALESCE(expected_as_of_date, DATE(updated_at)))
            FROM kr_corporate_earnings_expectations
        )
        GROUP BY expected_source
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
    except Exception as exc:
        logger.warning("Failed to load expectation source breakdown: %s", exc)
        return None

    if not rows:
        return None

    buckets: Dict[str, int] = {
        "feed": 0,
        "baseline": 0,
        "manual": 0,
    }
    other_count = 0
    for row in rows:
        source_bucket = _normalize_expectation_source(row.get("expected_source"))
        count = int(row.get("cnt") or 0)
        if source_bucket in buckets:
            buckets[source_bucket] += count
        else:
            other_count += count

    parts: List[str] = []
    for key in ("feed", "baseline", "manual"):
        parts.append(f"{key}:{buckets[key]}")
    if other_count > 0:
        parts.append(f"other:{other_count}")
    return " / ".join(parts)


def _coerce_reference_timestamp(
    last_collected_at: Optional[datetime], last_observation_date: Optional[date]
) -> Optional[datetime]:
    def _normalize_datetime(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value
        try:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        except Exception:
            return value.replace(tzinfo=None)

    def _parse_datetime(value: Any) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return _normalize_datetime(value)
        if isinstance(value, date):
            return datetime.combine(value, time.min)
        if hasattr(value, "to_pydatetime"):
            try:
                converted = value.to_pydatetime()
                if isinstance(converted, datetime):
                    return _normalize_datetime(converted)
                if isinstance(converted, date):
                    return datetime.combine(converted, time.min)
            except Exception:
                pass
        if hasattr(value, "to_native"):
            try:
                converted = value.to_native()
                if isinstance(converted, datetime):
                    return _normalize_datetime(converted)
                if isinstance(converted, date):
                    return datetime.combine(converted, time.min)
            except Exception:
                pass
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            if text.endswith("Z"):
                text = f"{text[:-1]}+00:00"
            match = re.match(
                r"^(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2})(\.\d+)?([+-]\d{2}:\d{2})?$",
                text,
            )
            if match:
                prefix, frac, tz_text = match.groups()
                if frac:
                    frac = f".{frac[1:7]}"
                text = f"{prefix}{frac or ''}{tz_text or ''}"
            try:
                parsed = datetime.fromisoformat(text)
                return _normalize_datetime(parsed)
            except ValueError:
                pass
            try:
                parsed_date = date.fromisoformat(text[:10])
                return datetime.combine(parsed_date, time.min)
            except ValueError:
                return None
        if hasattr(value, "isoformat"):
            try:
                return _parse_datetime(value.isoformat())
            except Exception:
                return None
        return None

    reference_at = _parse_datetime(last_collected_at)
    observation_dt = _parse_datetime(last_observation_date)
    if observation_dt is not None:
        if reference_at is None or observation_dt > reference_at:
            reference_at = observation_dt

    return reference_at


def _build_health(
    reference_at: Optional[datetime],
    expected_interval_hours: int,
    collection_enabled: bool,
    *,
    frequency: str = "",
    now_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    # Most DB timestamps are stored in UTC-naive form.
    # Use UTC-naive "now" by default to avoid systematic +9h lag overestimation
    # when the app server runs in KST.
    current_time = now_at or datetime.now(timezone.utc).replace(tzinfo=None)

    if not collection_enabled:
        return {
            "health": "disabled",
            "lag_hours": None,
            "stale_threshold_hours": None,
            "is_stale": False,
        }

    if reference_at is None:
        return {
            "health": "missing",
            "lag_hours": None,
            "stale_threshold_hours": expected_interval_hours,
            "is_stale": False,
        }

    grace_hours = max(6, int(expected_interval_hours * 0.5))
    stale_threshold_hours = expected_interval_hours + grace_hours
    # Daily indicators are typically not published on weekends.
    # Add weekend grace so stale alert does not fire for expected non-business-day gaps.
    if (frequency or "").lower() == "daily" and current_time.weekday() >= 5:
        stale_threshold_hours += 48

    lag_hours = max(0.0, (current_time - reference_at).total_seconds() / 3600)
    is_stale = lag_hours > stale_threshold_hours

    return {
        "health": "stale" if is_stale else "healthy",
        "lag_hours": round(lag_hours, 1),
        "stale_threshold_hours": stale_threshold_hours,
        "is_stale": is_stale,
    }


def _summarize(indicators: List[Dict[str, Any]]) -> Dict[str, Any]:
    health_keys = ("healthy", "stale", "missing", "disabled")

    summary: Dict[str, Any] = {
        "total": len(indicators),
    }
    for key in health_keys:
        summary[key] = sum(1 for indicator in indicators if indicator["health"] == key)

    by_country: Dict[str, Dict[str, int]] = {}
    for country in sorted({item["country"] for item in indicators}):
        country_items = [item for item in indicators if item["country"] == country]
        country_summary = {"total": len(country_items)}
        for key in health_keys:
            country_summary[key] = sum(
                1 for indicator in country_items if indicator["health"] == key
            )
        by_country[country] = country_summary

    summary["by_country"] = by_country
    return summary


def get_macro_indicator_health_snapshot() -> Dict[str, Any]:
    registry = (
        _build_us_registry()
        + KR_INDICATOR_REGISTRY
        + US_CORPORATE_REGISTRY
        + KR_CORPORATE_REGISTRY
        + PIPELINE_REGISTRY
        + GRAPH_REGISTRY
    )
    fred_latest_rows = _load_latest_fred_rows()
    corporate_latest_rows = _load_latest_corporate_rows()
    graph_latest_rows = _load_latest_graph_rows()
    expectation_source_breakdown = _load_latest_expectation_source_breakdown()

    indicators: List[Dict[str, Any]] = []
    for item in registry:
        code = item["code"]
        source = item["source"]
        collection_enabled = bool(item.get("collection_enabled", True))
        expected_interval_hours = _frequency_to_interval_hours(item.get("frequency", "daily"))

        storage = str(item.get("storage") or "fred").lower()
        if storage == "corporate":
            row = corporate_latest_rows.get(code)
        elif storage == "graph":
            row = graph_latest_rows.get(code)
        else:
            # KR/US macro indicators are persisted into fred_data canonical table.
            row = fred_latest_rows.get(code)
        last_observation_date = row.get("last_observation_date") if row else None
        last_collected_at = row.get("last_collected_at") if row else None
        latest_value = row.get("latest_value") if row else None

        reference_at = _coerce_reference_timestamp(last_collected_at, last_observation_date)
        health = _build_health(
            reference_at,
            expected_interval_hours,
            collection_enabled,
            frequency=item.get("frequency", ""),
        )
        run_health_status: Optional[str] = None
        run_health_reason: Optional[str] = None
        if row and code in RUN_HEALTH_JOB_CODES:
            run_health_status, run_health_reason = _derive_run_health_status(code, row)
            if run_health_status in {"warning", "failed"} and health.get("health") == "healthy":
                health = {
                    **health,
                    "health": "stale",
                    "is_stale": True,
                }

        note = ""
        if not collection_enabled:
            note = "Collector not connected yet"
        elif row is None:
            note = "No collected data found"
        elif code == "KR_DART_EARNINGS_EXPECTATION" and expectation_source_breakdown:
            note = f"최근 소스 {expectation_source_breakdown}"
        elif code == "KR_DART_DPLUS1_SLA":
            checked_event_count = int(row.get("checked_event_count") or 0)
            met_sla_count = int(row.get("met_sla_count") or 0)
            violated_sla_count = int(row.get("violated_sla_count") or 0)
            missing_financial_count = int(row.get("missing_financial_count") or 0)
            late_financial_count = int(row.get("late_financial_count") or 0)
            status = str(row.get("status") or "").strip()
            note_parts = [
                f"점검대상 {checked_event_count}건",
                f"준수/위반 {met_sla_count}/{violated_sla_count}",
                f"미수집 {missing_financial_count}건",
                f"지연반영 {late_financial_count}건",
            ]
            if status:
                note_parts.append(f"상태 {status}")
            note = ", ".join(note_parts)
        elif code in {"KR_TOP50_DAILY_OHLCV", "US_TOP50_DAILY_OHLCV"}:
            symbol_count = int(row.get("symbol_count") or 0)
            note = f"최근 거래일 커버리지 {symbol_count}종목"
        elif code == "ECONOMIC_NEWS_STREAM":
            source_count = int(row.get("source_count") or 0)
            category_count = int(row.get("category_count") or 0)
            latest_count = int(row.get("latest_value") or 0)
            note = f"최근 관측일 {latest_count}건, 소스 {source_count}개, 카테고리 {category_count}개"
        elif code == "TIER1_CORPORATE_EVENT_FEED":
            symbol_count = int(row.get("symbol_count") or 0)
            country_count = int(row.get("country_count") or 0)
            latest_count = int(row.get("latest_value") or 0)
            note = f"최근 이벤트일 {latest_count}건, 종목 {symbol_count}개, 국가 {country_count}개"
        elif code == "KR_REAL_ESTATE_TRANSACTIONS":
            region_count = int(row.get("region_count") or 0)
            latest_count = int(row.get("latest_value") or 0)
            note = f"최근 계약일 {latest_count}건, 지역 {region_count}개"
        elif code == "KR_REAL_ESTATE_MONTHLY_SUMMARY":
            region_count = int(row.get("region_count") or 0)
            latest_count = int(row.get("latest_value") or 0)
            note = f"최근 통계월 {latest_count}건, 지역 {region_count}개"
        elif code in RUN_HEALTH_JOB_CODES:
            run_count = int(row.get("run_count") or 0)
            success_run_count = int(row.get("success_run_count") or 0)
            failed_run_count = int(row.get("failed_run_count") or 0)
            success_count = int(row.get("success_count") or 0)
            failure_count = int(row.get("failure_count") or 0)
            total_count = success_count + failure_count
            note_parts = [
                f"일간 실행 {run_count}회",
                f"성공/실패 {success_run_count}/{failed_run_count}",
            ]
            if total_count > 0:
                note_parts.append(f"요청 성공 {success_count}/{total_count}")
            if run_health_status:
                note_parts.append(f"실행상태 {run_health_status}")
            elif str(row.get("last_status") or "").strip():
                note_parts.append(f"최근상태 {str(row.get('last_status') or '').strip()}")
            last_error = str(row.get("last_error") or "").strip()
            if last_error:
                note_parts.append(f"최근오류 {last_error[:80]}")
            if code == "TIER1_CORPORATE_EVENT_SYNC":
                details = _parse_json_object(row.get("details_json"))
                health_status = str(details.get("health_status") or "").strip()
                retry_failure_count = int(details.get("retry_failure_count") or 0)
                dlq_recorded_count = int(details.get("dlq_recorded_count") or 0)
                normalized_rows = int(details.get("normalized_rows") or 0)
                if normalized_rows > 0:
                    note_parts.append(f"표준이벤트 {normalized_rows}건")
                note_parts.append(f"재시도실패/DLQ {retry_failure_count}/{dlq_recorded_count}")
                if health_status:
                    note_parts.append(f"헬스상태 {health_status}")
            elif code == "GRAPH_NEWS_EXTRACTION_SYNC":
                details = _parse_json_object(row.get("details_json"))
                extraction_success_docs = int(details.get("extraction_success_docs") or 0)
                extraction_failed_docs = int(details.get("extraction_failed_docs") or 0)
                embedding_success_docs = int(details.get("embedding_embedded_docs") or 0)
                embedding_failed_docs = int(details.get("embedding_failed_docs") or 0)
                embedding_status = str(details.get("embedding_status") or "").strip()
                sync_documents = int(details.get("sync_documents") or 0)
                if sync_documents > 0:
                    note_parts.append(f"동기화 문서 {sync_documents}건")
                note_parts.append(f"추출 성공/실패 {extraction_success_docs}/{extraction_failed_docs}")
                note_parts.append(f"임베딩 성공/실패 {embedding_success_docs}/{embedding_failed_docs}")
                if embedding_status:
                    note_parts.append(f"임베딩상태 {embedding_status}")
            elif code == "EQUITY_GRAPH_PROJECTION_SYNC":
                details = _parse_json_object(row.get("details_json"))
                lag_hours = _as_float(details.get("lag_hours"))
                latest_graph_date = str(details.get("latest_graph_date") or "").strip()
                max_trade_date = str(details.get("max_trade_date") or "").strip()
                max_event_date = str(details.get("max_event_date") or "").strip()
                projection_health_status = str(details.get("projection_health_status") or "").strip()
                if lag_hours is None:
                    note_parts.append("lag unavailable")
                else:
                    note_parts.append(f"lag {lag_hours:.1f}h")
                if latest_graph_date:
                    note_parts.append(f"최신 그래프일 {latest_graph_date}")
                if max_trade_date:
                    note_parts.append(f"max_trade {max_trade_date}")
                if max_event_date:
                    note_parts.append(f"max_event {max_event_date}")
                if projection_health_status:
                    note_parts.append(f"projection상태 {projection_health_status}")
            elif code == "GRAPH_RAG_PHASE5_WEEKLY_REPORT":
                details = _parse_json_object(row.get("details_json"))
                total_runs = int(details.get("total_runs") or 0)
                warning_runs = int(details.get("warning_runs") or 0)
                failed_runs = int(details.get("failed_runs") or 0)
                avg_pass_rate_pct = _as_float(details.get("avg_pass_rate_pct"))
                routing_mismatch_count = int(details.get("routing_mismatch_count") or 0)
                avg_structured_citation_count = _as_float(
                    details.get("avg_structured_citation_count")
                )
                status_reason = str(details.get("status_reason") or "").strip()
                top_failure_categories = details.get("top_failure_categories")
                top_failed_cases = details.get("top_failed_cases")
                if total_runs > 0:
                    note_parts.append(f"주간 집계 {total_runs}회")
                    note_parts.append(f"경고/실패 {warning_runs}/{failed_runs}")
                if avg_pass_rate_pct is not None:
                    note_parts.append(f"평균통과율 {avg_pass_rate_pct:.2f}%")
                note_parts.append(f"routing_mismatch {routing_mismatch_count}건")
                if avg_structured_citation_count is not None:
                    note_parts.append(
                        f"평균 structured_citation {avg_structured_citation_count:.3f}"
                    )
                if isinstance(top_failure_categories, list) and top_failure_categories:
                    first_failure = top_failure_categories[0]
                    if isinstance(first_failure, dict):
                        category_name = str(first_failure.get("category") or "").strip()
                        category_count = int(first_failure.get("count") or 0)
                        if category_name:
                            note_parts.append(f"Top실패 {category_name}:{category_count}")
                if isinstance(top_failed_cases, list) and top_failed_cases:
                    first_case = top_failed_cases[0]
                    if isinstance(first_case, dict):
                        first_case_id = str(first_case.get("case_id") or "").strip()
                        first_case_count = int(first_case.get("count") or 0)
                        if first_case_id:
                            note_parts.append(f"Top케이스 {first_case_id}:{first_case_count}")
                if status_reason:
                    note_parts.append(f"상태사유 {status_reason}")
            if run_health_reason:
                note_parts.append(f"판정근거 {run_health_reason}")
            note = ", ".join(note_parts)
        elif code == "GRAPH_DOCUMENT_EMBEDDING_COVERAGE":
            total_docs = int(row.get("total_docs") or 0)
            embedded_docs = int(row.get("embedded_docs") or 0)
            failed_docs = int(row.get("failed_docs") or 0)
            note = f"임베딩 {embedded_docs}/{total_docs}건, 실패 {failed_docs}건"
        elif code == "GRAPH_RAG_VECTOR_INDEX_READY":
            index_name = str(row.get("index_name") or "document_text_embedding_idx")
            index_state = str(row.get("index_state") or "missing")
            population_percent = _as_float(row.get("population_percent"))
            if population_percent is None:
                note = f"인덱스 {index_name}, 상태 {index_state}"
            else:
                note = f"인덱스 {index_name}, 상태 {index_state}, 구축률 {population_percent:.1f}%"

        latest_source = None
        if code == "KR_DART_EARNINGS_EXPECTATION":
            latest_source = expectation_source_breakdown

        indicators.append(
            {
                "code": code,
                "name": item["name"],
                "description": item["description"],
                "country": item["country"],
                "source": source,
                "frequency": item.get("frequency", ""),
                "unit": item.get("unit", ""),
                "collection_enabled": collection_enabled,
                "expected_interval_hours": expected_interval_hours,
                "last_observation_date": _to_iso(last_observation_date),
                "last_collected_at": _to_iso(last_collected_at),
                "latest_value": _as_float(latest_value),
                "health": health["health"],
                "lag_hours": health["lag_hours"],
                "stale_threshold_hours": health["stale_threshold_hours"],
                "is_stale": health["is_stale"],
                "note": note,
                "latest_source": latest_source,
                "run_health_status": run_health_status,
                "run_health_reason": run_health_reason,
            }
        )

    health_priority = {"stale": 0, "missing": 1, "disabled": 2, "healthy": 3}
    indicators.sort(
        key=lambda item: (
            health_priority.get(item["health"], 9),
            item["country"],
            item["code"],
        )
    )

    return {
        "generated_at": datetime.now().isoformat(),
        "summary": _summarize(indicators),
        "indicators": indicators,
    }
