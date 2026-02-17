"""
Real-estate query API.

전략:
- 상세 거래는 MySQL 원본 테이블(`kr_real_estate_transactions`)에서 조회
- 월/지역 집계는 Neo4j(`RealEstateMonthlySummary`)에서 조회
- Neo4j 실패 시 MySQL 집계 테이블(`kr_real_estate_monthly_summary`)로 자동 폴백
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from service.database.db import get_db_connection
from service.graph.neo4j_client import get_neo4j_client

logger = logging.getLogger(__name__)

DEFAULT_PROPERTY_TYPE = "apartment"
DEFAULT_TRANSACTION_TYPE = "sale"

router = APIRouter(prefix="/macro/real-estate", tags=["macro-real-estate"])


class RealEstateQueryResponse(BaseModel):
    view: Literal["detail", "monthly", "region"]
    source: str
    start_ym: str
    end_ym: str
    property_type: str
    transaction_type: str
    lawd_codes: List[str] = Field(default_factory=list)
    limit: int
    offset: int
    total: int
    rows: List[Dict[str, Any]] = Field(default_factory=list)
    fallback_used: bool = False
    meta: Dict[str, Any] = Field(default_factory=dict)


def _parse_ym_to_first_day(ym: str) -> date:
    if ym is None:
        raise ValueError("YYYYMM is required")
    normalized = str(ym).strip()
    if len(normalized) != 6 or not normalized.isdigit():
        raise ValueError(f"Invalid YYYYMM format: {ym}")
    return datetime.strptime(normalized, "%Y%m").date().replace(day=1)


def _next_month(dt: date) -> date:
    if dt.month == 12:
        return dt.replace(year=dt.year + 1, month=1)
    return dt.replace(month=dt.month + 1)


def _validate_ym_range(start_ym: str, end_ym: str) -> Tuple[date, date]:
    start_month = _parse_ym_to_first_day(start_ym)
    end_month = _parse_ym_to_first_day(end_ym)
    if start_month > end_month:
        raise ValueError(f"start_ym must be <= end_ym: {start_ym} > {end_ym}")
    return start_month, _next_month(end_month)


def _parse_lawd_codes(raw_codes: Optional[str]) -> List[str]:
    if not raw_codes:
        return []
    parsed: List[str] = []
    for token in raw_codes.split(","):
        code = token.strip()
        if not code:
            continue
        if len(code) != 5 or not code.isdigit():
            raise ValueError(f"Invalid LAWD_CD (must be 5 digits): {code}")
        parsed.append(code)
    return sorted(set(parsed))


def _serialize_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _serialize_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{key: _serialize_value(val) for key, val in row.items()} for row in rows]


def _build_lawd_filter_sql(column_expr: str, lawd_codes: List[str]) -> Tuple[str, List[str]]:
    if not lawd_codes:
        return "", []
    placeholders = ", ".join(["%s"] * len(lawd_codes))
    return f" AND {column_expr} IN ({placeholders}) ", list(lawd_codes)


def fetch_rdb_transactions(
    *,
    start_ym: str,
    end_ym: str,
    property_type: str,
    transaction_type: str,
    lawd_codes: List[str],
    limit: int,
    offset: int,
    include_metadata: bool,
) -> Tuple[List[Dict[str, Any]], int]:
    start_month, end_month_exclusive = _validate_ym_range(start_ym, end_ym)
    where_lawd, lawd_params = _build_lawd_filter_sql("LEFT(region_code, 5)", lawd_codes)
    base_params: List[Any] = [
        start_month,
        end_month_exclusive,
        property_type,
        transaction_type,
    ]
    base_params.extend(lawd_params)

    count_query = f"""
        SELECT COUNT(*) AS total
        FROM kr_real_estate_transactions
        WHERE contract_date IS NOT NULL
          AND contract_date >= %s
          AND contract_date < %s
          AND property_type = %s
          AND transaction_type = %s
          {where_lawd}
    """

    metadata_column = ", metadata_json" if include_metadata else ""
    data_query = f"""
        SELECT
          id,
          source,
          source_record_id,
          country_code,
          region_code,
          LEFT(region_code, 5) AS lawd_cd,
          property_type,
          transaction_type,
          contract_date,
          effective_date,
          published_at,
          as_of_date,
          price,
          deposit,
          monthly_rent,
          area_m2,
          floor_no,
          build_year,
          JSON_UNQUOTE(JSON_EXTRACT(metadata_json, '$.aptNm')) AS apt_name,
          JSON_UNQUOTE(JSON_EXTRACT(metadata_json, '$.umdNm')) AS umd_name,
          JSON_UNQUOTE(JSON_EXTRACT(metadata_json, '$.jibun')) AS jibun
          {metadata_column}
        FROM kr_real_estate_transactions
        WHERE contract_date IS NOT NULL
          AND contract_date >= %s
          AND contract_date < %s
          AND property_type = %s
          AND transaction_type = %s
          {where_lawd}
        ORDER BY contract_date DESC, id DESC
        LIMIT %s OFFSET %s
    """

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(count_query, tuple(base_params))
        count_row = cursor.fetchone() or {"total": 0}
        total = int(count_row.get("total", 0))

        data_params = list(base_params) + [limit, offset]
        cursor.execute(data_query, tuple(data_params))
        rows = cursor.fetchall() or []

    if include_metadata:
        for row in rows:
            payload = row.get("metadata_json")
            if isinstance(payload, str):
                try:
                    row["metadata_json"] = json.loads(payload)
                except json.JSONDecodeError:
                    row["metadata_json"] = payload

    return _serialize_rows(rows), total


def _build_summary_where_sql(
    *,
    start_ym: str,
    end_ym: str,
    property_type: str,
    transaction_type: str,
    lawd_codes: List[str],
) -> Tuple[str, List[Any]]:
    where_parts = [
        "stat_ym >= %s",
        "stat_ym <= %s",
        "property_type = %s",
        "transaction_type = %s",
    ]
    params: List[Any] = [start_ym, end_ym, property_type, transaction_type]
    if lawd_codes:
        placeholders = ", ".join(["%s"] * len(lawd_codes))
        where_parts.append(f"lawd_cd IN ({placeholders})")
        params.extend(lawd_codes)
    return " AND ".join(where_parts), params


def _fetch_mysql_monthly_summary(
    *,
    start_ym: str,
    end_ym: str,
    property_type: str,
    transaction_type: str,
    lawd_codes: List[str],
    limit: int,
    offset: int,
    aggregate_by_region: bool,
) -> Tuple[List[Dict[str, Any]], int]:
    where_sql, params = _build_summary_where_sql(
        start_ym=start_ym,
        end_ym=end_ym,
        property_type=property_type,
        transaction_type=transaction_type,
        lawd_codes=lawd_codes,
    )

    if aggregate_by_region:
        count_query = f"""
            SELECT COUNT(*) AS total
            FROM (
                SELECT lawd_cd
                FROM kr_real_estate_monthly_summary
                WHERE {where_sql}
                GROUP BY lawd_cd
            ) AS region_counts
        """
        data_query = f"""
            SELECT
              lawd_cd,
              SUM(tx_count) AS tx_count,
              SUM(total_price) AS total_price,
              CASE
                WHEN SUM(tx_count) > 0 THEN SUM(total_price) / SUM(tx_count)
                ELSE NULL
              END AS avg_price,
              MIN(min_price) AS min_price,
              MAX(max_price) AS max_price,
              COUNT(*) AS month_points,
              MIN(stat_ym) AS min_stat_ym,
              MAX(stat_ym) AS max_stat_ym
            FROM kr_real_estate_monthly_summary
            WHERE {where_sql}
            GROUP BY lawd_cd
            ORDER BY total_price DESC, lawd_cd ASC
            LIMIT %s OFFSET %s
        """
    else:
        count_query = f"""
            SELECT COUNT(*) AS total
            FROM kr_real_estate_monthly_summary
            WHERE {where_sql}
        """
        data_query = f"""
            SELECT
              stat_ym,
              lawd_cd,
              country_code,
              property_type,
              transaction_type,
              tx_count,
              avg_price,
              avg_price_per_m2,
              avg_area_m2,
              min_price,
              max_price,
              total_price,
              as_of_date
            FROM kr_real_estate_monthly_summary
            WHERE {where_sql}
            ORDER BY stat_ym DESC, lawd_cd ASC
            LIMIT %s OFFSET %s
        """

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(count_query, tuple(params))
        count_row = cursor.fetchone() or {"total": 0}
        total = int(count_row.get("total", 0))

        data_params = list(params) + [limit, offset]
        cursor.execute(data_query, tuple(data_params))
        rows = cursor.fetchall() or []

    return _serialize_rows(rows), total


def _build_summary_where_cypher(
    *,
    start_ym: str,
    end_ym: str,
    property_type: str,
    transaction_type: str,
    lawd_codes: List[str],
) -> Tuple[str, Dict[str, Any]]:
    conditions = [
        "m.stat_ym >= $start_ym",
        "m.stat_ym <= $end_ym",
        "m.property_type = $property_type",
        "m.transaction_type = $transaction_type",
    ]
    params: Dict[str, Any] = {
        "start_ym": start_ym,
        "end_ym": end_ym,
        "property_type": property_type,
        "transaction_type": transaction_type,
    }
    if lawd_codes:
        conditions.append("m.lawd_cd IN $lawd_codes")
        params["lawd_codes"] = lawd_codes
    return " AND ".join(conditions), params


def _fetch_graph_monthly_summary(
    *,
    start_ym: str,
    end_ym: str,
    property_type: str,
    transaction_type: str,
    lawd_codes: List[str],
    limit: int,
    offset: int,
) -> Tuple[List[Dict[str, Any]], int]:
    client = get_neo4j_client()
    where_clause, params = _build_summary_where_cypher(
        start_ym=start_ym,
        end_ym=end_ym,
        property_type=property_type,
        transaction_type=transaction_type,
        lawd_codes=lawd_codes,
    )

    count_query = f"""
    MATCH (:RealEstateRegion)-[:HAS_MONTHLY_SUMMARY]->(m:RealEstateMonthlySummary)
    WHERE {where_clause}
    RETURN count(m) AS total
    """
    total_rows = client.run_read(count_query, params) or [{"total": 0}]
    total = int(total_rows[0].get("total", 0))

    data_params = dict(params)
    data_params["limit"] = int(limit)
    data_params["offset"] = int(offset)
    data_query = f"""
    MATCH (:RealEstateRegion)-[:HAS_MONTHLY_SUMMARY]->(m:RealEstateMonthlySummary)
    WHERE {where_clause}
    RETURN
      m.stat_ym AS stat_ym,
      m.lawd_cd AS lawd_cd,
      m.country_code AS country_code,
      m.property_type AS property_type,
      m.transaction_type AS transaction_type,
      toInteger(m.tx_count) AS tx_count,
      toFloat(m.avg_price) AS avg_price,
      toFloat(m.avg_price_per_m2) AS avg_price_per_m2,
      toFloat(m.avg_area_m2) AS avg_area_m2,
      toInteger(m.min_price) AS min_price,
      toInteger(m.max_price) AS max_price,
      toInteger(m.total_price) AS total_price,
      CASE WHEN m.as_of_date IS NULL THEN null ELSE toString(m.as_of_date) END AS as_of_date
    ORDER BY m.stat_ym DESC, m.lawd_cd ASC
    SKIP $offset LIMIT $limit
    """
    rows = client.run_read(data_query, data_params) or []
    return _serialize_rows(rows), total


def _fetch_graph_region_rollup(
    *,
    start_ym: str,
    end_ym: str,
    property_type: str,
    transaction_type: str,
    lawd_codes: List[str],
    limit: int,
    offset: int,
) -> Tuple[List[Dict[str, Any]], int]:
    client = get_neo4j_client()
    where_clause, params = _build_summary_where_cypher(
        start_ym=start_ym,
        end_ym=end_ym,
        property_type=property_type,
        transaction_type=transaction_type,
        lawd_codes=lawd_codes,
    )

    count_query = f"""
    MATCH (:RealEstateRegion)-[:HAS_MONTHLY_SUMMARY]->(m:RealEstateMonthlySummary)
    WHERE {where_clause}
    RETURN count(DISTINCT m.lawd_cd) AS total
    """
    total_rows = client.run_read(count_query, params) or [{"total": 0}]
    total = int(total_rows[0].get("total", 0))

    data_params = dict(params)
    data_params["limit"] = int(limit)
    data_params["offset"] = int(offset)
    data_query = f"""
    MATCH (:RealEstateRegion)-[:HAS_MONTHLY_SUMMARY]->(m:RealEstateMonthlySummary)
    WHERE {where_clause}
    WITH
      m.lawd_cd AS lawd_cd,
      sum(toInteger(m.tx_count)) AS tx_count,
      sum(toInteger(coalesce(m.total_price, 0))) AS total_price,
      min(toInteger(m.min_price)) AS min_price,
      max(toInteger(m.max_price)) AS max_price,
      count(m) AS month_points,
      min(m.stat_ym) AS min_stat_ym,
      max(m.stat_ym) AS max_stat_ym
    RETURN
      lawd_cd,
      tx_count,
      total_price,
      CASE WHEN tx_count > 0 THEN toFloat(total_price) / tx_count ELSE null END AS avg_price,
      min_price,
      max_price,
      month_points,
      min_stat_ym,
      max_stat_ym
    ORDER BY total_price DESC, lawd_cd ASC
    SKIP $offset LIMIT $limit
    """
    rows = client.run_read(data_query, data_params) or []
    return _serialize_rows(rows), total


def _fetch_monthly_with_fallback(
    *,
    aggregate_by_region: bool,
    start_ym: str,
    end_ym: str,
    property_type: str,
    transaction_type: str,
    lawd_codes: List[str],
    limit: int,
    offset: int,
) -> Tuple[List[Dict[str, Any]], int, str, bool, Dict[str, Any]]:
    try:
        if aggregate_by_region:
            rows, total = _fetch_graph_region_rollup(
                start_ym=start_ym,
                end_ym=end_ym,
                property_type=property_type,
                transaction_type=transaction_type,
                lawd_codes=lawd_codes,
                limit=limit,
                offset=offset,
            )
        else:
            rows, total = _fetch_graph_monthly_summary(
                start_ym=start_ym,
                end_ym=end_ym,
                property_type=property_type,
                transaction_type=transaction_type,
                lawd_codes=lawd_codes,
                limit=limit,
                offset=offset,
            )
        return rows, total, "neo4j_monthly_summary", False, {}
    except Exception as graph_error:
        logger.warning(
            "Real-estate graph query failed. Fallback to MySQL summary table: %s",
            graph_error,
            exc_info=True,
        )
        rows, total = _fetch_mysql_monthly_summary(
            start_ym=start_ym,
            end_ym=end_ym,
            property_type=property_type,
            transaction_type=transaction_type,
            lawd_codes=lawd_codes,
            limit=limit,
            offset=offset,
            aggregate_by_region=aggregate_by_region,
        )
        return (
            rows,
            total,
            "mysql_monthly_summary_fallback",
            True,
            {"graph_error": str(graph_error)},
        )


def execute_real_estate_query(
    *,
    view: Literal["detail", "monthly", "region"],
    start_ym: str,
    end_ym: str,
    lawd_codes_csv: Optional[str],
    property_type: str,
    transaction_type: str,
    limit: int,
    offset: int,
    include_metadata: bool,
) -> RealEstateQueryResponse:
    _validate_ym_range(start_ym, end_ym)
    lawd_codes = _parse_lawd_codes(lawd_codes_csv)

    normalized_property_type = (property_type or DEFAULT_PROPERTY_TYPE).strip().lower()
    normalized_transaction_type = (transaction_type or DEFAULT_TRANSACTION_TYPE).strip().lower()

    if view == "detail":
        rows, total = fetch_rdb_transactions(
            start_ym=start_ym,
            end_ym=end_ym,
            property_type=normalized_property_type,
            transaction_type=normalized_transaction_type,
            lawd_codes=lawd_codes,
            limit=limit,
            offset=offset,
            include_metadata=include_metadata,
        )
        return RealEstateQueryResponse(
            view=view,
            source="mysql_transactions",
            start_ym=start_ym,
            end_ym=end_ym,
            property_type=normalized_property_type,
            transaction_type=normalized_transaction_type,
            lawd_codes=lawd_codes,
            limit=limit,
            offset=offset,
            total=total,
            rows=rows,
        )

    aggregate_by_region = view == "region"
    rows, total, source, fallback_used, meta = _fetch_monthly_with_fallback(
        aggregate_by_region=aggregate_by_region,
        start_ym=start_ym,
        end_ym=end_ym,
        property_type=normalized_property_type,
        transaction_type=normalized_transaction_type,
        lawd_codes=lawd_codes,
        limit=limit,
        offset=offset,
    )
    return RealEstateQueryResponse(
        view=view,
        source=source,
        start_ym=start_ym,
        end_ym=end_ym,
        property_type=normalized_property_type,
        transaction_type=normalized_transaction_type,
        lawd_codes=lawd_codes,
        limit=limit,
        offset=offset,
        total=total,
        rows=rows,
        fallback_used=fallback_used,
        meta=meta,
    )


@router.get("", response_model=RealEstateQueryResponse)
async def query_real_estate(
    view: Literal["detail", "monthly", "region"] = Query(
        default="monthly",
        description="detail=RDB 원본, monthly=Graph 월집계, region=Graph 지역집계",
    ),
    start_ym: str = Query(..., description="조회 시작월 YYYYMM"),
    end_ym: str = Query(..., description="조회 종료월 YYYYMM"),
    lawd_codes: Optional[str] = Query(default=None, description="LAWD_CD CSV (예: 11110,41135)"),
    property_type: str = Query(default=DEFAULT_PROPERTY_TYPE),
    transaction_type: str = Query(default=DEFAULT_TRANSACTION_TYPE),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    include_metadata: bool = Query(default=False, description="view=detail일 때 metadata_json 포함"),
):
    try:
        return execute_real_estate_query(
            view=view,
            start_ym=start_ym,
            end_ym=end_ym,
            lawd_codes_csv=lawd_codes,
            property_type=property_type,
            transaction_type=transaction_type,
            limit=limit,
            offset=offset,
            include_metadata=include_metadata,
        )
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    except HTTPException:
        raise
    except Exception as err:
        logger.error("Real-estate unified query failed: %s", err, exc_info=True)
        raise HTTPException(status_code=500, detail="Real-estate query failed") from err


@router.get("/detail", response_model=RealEstateQueryResponse)
async def query_real_estate_detail(
    start_ym: str = Query(..., description="조회 시작월 YYYYMM"),
    end_ym: str = Query(..., description="조회 종료월 YYYYMM"),
    lawd_codes: Optional[str] = Query(default=None, description="LAWD_CD CSV"),
    property_type: str = Query(default=DEFAULT_PROPERTY_TYPE),
    transaction_type: str = Query(default=DEFAULT_TRANSACTION_TYPE),
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    include_metadata: bool = Query(default=False, description="metadata_json 포함"),
):
    return await query_real_estate(
        view="detail",
        start_ym=start_ym,
        end_ym=end_ym,
        lawd_codes=lawd_codes,
        property_type=property_type,
        transaction_type=transaction_type,
        limit=limit,
        offset=offset,
        include_metadata=include_metadata,
    )


@router.get("/monthly", response_model=RealEstateQueryResponse)
async def query_real_estate_monthly(
    start_ym: str = Query(..., description="조회 시작월 YYYYMM"),
    end_ym: str = Query(..., description="조회 종료월 YYYYMM"),
    lawd_codes: Optional[str] = Query(default=None, description="LAWD_CD CSV"),
    property_type: str = Query(default=DEFAULT_PROPERTY_TYPE),
    transaction_type: str = Query(default=DEFAULT_TRANSACTION_TYPE),
    limit: int = Query(default=5000, ge=1, le=20000),
    offset: int = Query(default=0, ge=0),
):
    return await query_real_estate(
        view="monthly",
        start_ym=start_ym,
        end_ym=end_ym,
        lawd_codes=lawd_codes,
        property_type=property_type,
        transaction_type=transaction_type,
        limit=limit,
        offset=offset,
        include_metadata=False,
    )


@router.get("/regions", response_model=RealEstateQueryResponse)
async def query_real_estate_regions(
    start_ym: str = Query(..., description="조회 시작월 YYYYMM"),
    end_ym: str = Query(..., description="조회 종료월 YYYYMM"),
    lawd_codes: Optional[str] = Query(default=None, description="LAWD_CD CSV"),
    property_type: str = Query(default=DEFAULT_PROPERTY_TYPE),
    transaction_type: str = Query(default=DEFAULT_TRANSACTION_TYPE),
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
):
    return await query_real_estate(
        view="region",
        start_ym=start_ym,
        end_ym=end_ym,
        lawd_codes=lawd_codes,
        property_type=property_type,
        transaction_type=transaction_type,
        limit=limit,
        offset=offset,
        include_metadata=False,
    )
