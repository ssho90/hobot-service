"""
Admin macro indicator health snapshot utilities.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time
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


def _frequency_to_interval_hours(frequency: str) -> int:
    return FREQUENCY_TO_INTERVAL_HOURS.get((frequency or "").lower(), 24)


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
                latest.last_error
            FROM macro_collection_run_reports latest
            WHERE latest.job_code = 'US_TOP50_EARNINGS_WATCH'
            ORDER BY latest.report_date DESC, latest.updated_at DESC
            LIMIT 1
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
                latest.last_error
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


def _normalize_expectation_source(source: Any) -> str:
    normalized = str(source or "").strip().lower()
    if normalized in {"feed", "consensus_feed"}:
        return "feed"
    if normalized in {"auto_baseline", "baseline"}:
        return "baseline"
    if normalized in {"manual", "admin", "user"}:
        return "manual"
    return normalized or "unknown"


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
    reference_at = last_collected_at if isinstance(last_collected_at, datetime) else None

    if isinstance(last_observation_date, date):
        observation_dt = datetime.combine(last_observation_date, time.min)
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
    current_time = now_at or datetime.now()

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
    )
    fred_latest_rows = _load_latest_fred_rows()
    corporate_latest_rows = _load_latest_corporate_rows()
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
        elif code in {"KR_TOP50_EARNINGS_WATCH_SUCCESS_RATE", "US_TOP50_EARNINGS_WATCH_SUCCESS_RATE"}:
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
            last_status = str(row.get("last_status") or "").strip()
            if last_status and last_status != "healthy":
                note_parts.append(f"최근상태 {last_status}")
            last_error = str(row.get("last_error") or "").strip()
            if last_error:
                note_parts.append(f"최근오류 {last_error[:80]}")
            note = ", ".join(note_parts)

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
